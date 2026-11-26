"""cypkg's bridge to cvcpkg's own installer, for the Prefixes window (share/cypkg/prefixes.ari).

The scripting hosts (arix, ariglx) run this in their embedded Python: prefixes.ari's ``python:``
block imports it, and the functions marked ``export`` below become the document's functions
(``(pkg-installed PREFIX)``, ``(pkg-install PREFIX NAMES ...)``, ...). It drives cvcpkg's library
(the same building blocks ``cvcpkg install``, ``uninstall`` and ``list --installed`` use, with
no click context), so a prefix cypkg changes is one the cvcpkg CLI reads, and the other way round.

- Plain values in and out: dicts, lists, strings and numbers. A failure raises ``RuntimeError``
  with a sentence for the window (the document catches it as a PythonError).
- The long calls (plan, install, remove) are async: they run on the host's pool while the calling
  program waits, so the window keeps drawing. install and remove post progress ("3/10 zlib
  1.3.1+cvc.6") through ``call.post`` and stop between packages when ``call.cancelled()``.
- One job a prefix at a time (a lock per prefix), and never the prefix the running host was
  loaded from: overwriting a library the process has mapped (libcvc, libpython) crashes it.
- Quiet: cvcpkg's logger gets a NullHandler, and the few library prints are swallowed, so nothing
  lands on the terminal the window is drawn in.

The cvcpkg it imports is any on the host's sys.path: one staged in share/cypkg/python/site
(tools/stage-python.sh, for a checkout), or later the cvcpkg-cp312 package (not published yet) in
the prefix the host runs from (lib/python3.12/site-packages, beside pycvc). Without one, ``pkg-client`` says so and the window shows
it. Under plain ``python``, ``export`` is a no-op, so the functions can be called directly.

The host runs this from the top document's ``python:`` block (mainx.ari): a ``load:``ed module's
own block doesn't run yet (ARIADNE.md §11), and the exports are the host's functions, which the
mounted prefixes.ari calls.
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import os
import sys
import threading
from pathlib import Path

try:  # the scripting hosts' export; plain python has none
    from _arihost import export  # type: ignore
except ImportError:  # pragma: no cover - depends on the host
    try:
        from pycvc.ari import export  # type: ignore
    except ImportError:

        def export(fn=None, **_kw):
            return fn if fn is not None else (lambda f: f)


logging.getLogger("cvcpkg").addHandler(logging.NullHandler())
logging.getLogger("cvcpkg").propagate = False

PUBLIC = "https://cvcpkg.org"

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
_cancels: set[str] = set()  # prefixes whose running install was asked to stop


# ── helpers ──────────────────────────────────────────────────────────────────────────────────


def _path(prefix: str) -> Path:
    p = Path(str(prefix)).expanduser()
    if not str(prefix).strip():
        raise RuntimeError("Name a prefix: a directory to install into.")
    if not p.is_absolute():
        raise RuntimeError(f"A prefix is a full path, not {prefix!r}.")
    return p


def _key(p: Path) -> str:
    return os.path.normcase(str(p.resolve()))


def _lock_for(p: Path) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(_key(p), threading.Lock())


def _lockfile(p: Path) -> Path:
    return p / "share" / "libcvc-deps" / "lockfile.yaml"


@export(name="pkg-host-prefix")
def host_prefix() -> str:
    """The prefix the running host's Python came from: never one to install into."""
    return str(Path(sys.prefix).resolve())


def _guard(p: Path) -> None:
    if _key(p) == os.path.normcase(host_prefix()):
        raise RuntimeError(
            "That is the prefix cypkg itself runs from; installing into it would replace the "
            "libraries this window is using. Pick another prefix."
        )


@contextlib.contextmanager
def _quiet():
    """Swallow what cvcpkg's library prints (a catalog note, a signature line)."""
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        yield


def _use_server(server: str) -> None:
    """cvcpkg's client reads its registry from the environment: the public one by default; a
    standalone registry serves its public packages too (CVCPKG_ROOT_URL)."""
    s = (server or "").rstrip("/")
    if not s or s == PUBLIC:
        os.environ.pop("CVCPKG_SERVER_URL", None)
        os.environ.pop("CVCPKG_ROOT_URL", None)
    else:
        os.environ["CVCPKG_SERVER_URL"] = s
        os.environ["CVCPKG_ROOT_URL"] = s


@export(name="pkg-client")
def client() -> dict:
    """The cvcpkg client this bridge drives: ``ok`` and its version, or, when this Python has
    none, a sentence saying how to get one (the window shows it in place of the installer)."""
    try:
        import cvcpkg
    except ImportError:
        return {"ok": False, "version": "",
                "message": "cvcpkg's Python client isn't importable in this host's Python: "
                           "stage one with cypkg's tools/stage-python.sh."}
    return {"ok": True, "version": str(getattr(cvcpkg, "__version__", "")), "message": ""}


def _fail(what: str, exc: BaseException) -> RuntimeError:
    msg = str(exc).strip() or exc.__class__.__name__
    return RuntimeError(f"{what}: {msg}")


# ── what's installed ─────────────────────────────────────────────────────────────────────────


@export(name="pkg-installed")
def installed(prefix: str) -> dict:
    """What a prefix holds, from its lockfile: its platform, arch, config and link, and a row per
    package (name, version, size in bytes, and whether it was built from source). A directory
    with no lockfile, or none at all, comes back empty (``exists`` says which)."""
    p = _path(prefix)
    out = {"prefix": str(p), "exists": p.is_dir(), "lockfile": False, "platform": "", "arch": "",
           "config": "", "link": "", "packages": [], "host": _key(p) == os.path.normcase(host_prefix())}
    lp = _lockfile(p)
    if not lp.is_file():
        return out
    from cvcpkg.lockfile import Lockfile

    try:
        lock = Lockfile.read(lp)
    except Exception as exc:  # SchemaError, YAML errors
        raise _fail("Couldn't read the prefix's lockfile", exc) from exc
    out.update(lockfile=True, platform=lock.platform, arch=lock.arch, config=lock.config,
               link=lock.link,
               packages=[{"name": b.name, "version": b.version, "size": int(b.size_bytes or 0),
                          "source": b.source_release == "source-build"}
                         for b in sorted(lock.bundles, key=lambda b: b.name)])
    return out


# ── planning: what an install would bring ────────────────────────────────────────────────────


def _resolve(names: list, server: str, config: str, link: str):
    from cvcpkg.builder import _detect_arch_for_platform
    from cvcpkg.cache import default_cache_dir
    from cvcpkg.catalog import catalog_entries, fetch_authoritative_catalog
    from cvcpkg.manifest import parse_component_spec
    from cvcpkg.platform import detect_platform, is_static_only_platform
    from cvcpkg.resolver import resolve

    _use_server(server)
    plat = detect_platform()
    arc = _detect_arch_for_platform(plat)
    if is_static_only_platform(plat):
        link = "static"
    with _quiet():
        cat = fetch_authoritative_catalog(cache_dir=default_cache_dir())
    entries = catalog_entries(cat, platform=plat, arch=arc, build_type=config, link=link,
                              trust_mirror=None)
    candidates: dict[str, list] = {}
    for e in entries:
        candidates.setdefault(e.name, []).append(e)
    provided = {p for e in entries for p in (e.provides or [])}
    reqs = [parse_component_spec(str(s)) for s in names if str(s).strip()]
    if not reqs:
        raise RuntimeError("Pick a package to install.")
    missing = [r.name for r in reqs if r.name not in candidates and r.name not in provided]
    if missing:
        raise RuntimeError(f"Not in the catalog for {plat}/{arc} {config} {link}: "
                           + ", ".join(sorted(missing)))
    with _quiet():
        res = resolve(reqs, candidates)  # dependencies followed (the default; 2.5.10 has no flag)
    return plat, arc, link, cat, res.picked


@export(name="pkg-plan", is_async=True)
def plan(prefix: str, names: list, server: str = "", config: str = "release",
         link: str = "shared") -> dict:
    """What installing ``names`` (with their dependencies) into the prefix would do: a row per
    package with its version, size and action ("install", "upgrade from V", or "same"), and how
    much would be downloaded."""
    p = _path(prefix)
    try:
        plat, arc, link, _cat, picked = _resolve(names, server, config, link)
    except RuntimeError:
        raise
    except Exception as exc:
        raise _fail("Couldn't plan the install", exc) from exc
    have = {r["name"]: r["version"] for r in installed(str(p))["packages"]}
    rows, download = [], 0
    for name in sorted(picked):
        e = picked[name]
        if name not in have:
            action = "install"
        elif have[name] == e.version:
            action = "same"
        else:
            action = f"upgrade from {have[name]}"
        if action != "same":
            download += int(e.size_bytes or 0)
        rows.append({"name": name, "version": e.version, "size": int(e.size_bytes or 0),
                     "action": action})
    return {"platform": plat, "arch": arc, "config": config, "link": link, "packages": rows,
            "download": download}


# ── installing ───────────────────────────────────────────────────────────────────────────────


@export(name="pkg-install", is_async=True, with_call=True)
def install(call, prefix: str, names: list, server: str = "", config: str = "release",
            link: str = "shared") -> dict:
    """Install ``names`` and their dependencies into the prefix (made if it isn't there), as
    ``cvcpkg install`` does: each bundle downloaded (cache first), its sha256 checked, unpacked,
    then the lockfile (merged with what was there), the CMake config and the activation scripts.
    Progress goes to ``<name>.progress``; a cancel stops between packages, and what was installed
    by then is still recorded."""
    from cvcpkg import __version__
    from cvcpkg.activate import write_activate_scripts
    from cvcpkg.cache import default_cache_dir
    from cvcpkg.cmake_config import write_cmake_config
    from cvcpkg.installer import install_entry
    from cvcpkg.lockfile import LockEntry, Lockfile

    p = _path(prefix)
    _guard(p)
    lock = _lock_for(p)
    if not lock.acquire(blocking=False):
        raise RuntimeError("Another job is changing this prefix; wait for it to finish.")
    try:
        try:
            plat, arc, link, cat, picked = _resolve(names, server, config, link)
        except RuntimeError:
            raise
        except Exception as exc:
            raise _fail("Couldn't plan the install", exc) from exc
        p.mkdir(parents=True, exist_ok=True)
        cache = default_cache_dir()
        _cancels.discard(_key(p))
        order = sorted(picked)
        done: list = []
        cancelled = False
        for i, name in enumerate(order):
            if (call is not None and call.cancelled()) or _key(p) in _cancels:
                cancelled = True
                _cancels.discard(_key(p))
                break
            e = picked[name]
            if call is not None:
                call.post(f"{i + 1}/{len(order)} {name} {e.version}")
            try:
                with _quiet():
                    install_entry(e, p, cache, verify_signatures=False, require_signatures=False,
                                  target_platform=plat)
            except Exception as exc:
                _record(p, plat, arc, config, link, cat, done)
                raise _fail(f"Couldn't install {name} {e.version}", exc) from exc
            done.append(LockEntry(name=e.name, version=e.version,
                                  upstream_version=e.upstream_version,
                                  source_release=e.source_release, sha256=e.sha256,
                                  size_bytes=e.size_bytes, archive_url=e.archive_url))
        _record(p, plat, arc, config, link, cat, done)
        if done:
            with _quiet(), contextlib.suppress(OSError):
                write_cmake_config(p, __version__)
            with _quiet(), contextlib.suppress(Exception):
                write_activate_scripts(p, platform=plat)
            with _quiet(), contextlib.suppress(Exception):
                from cvcpkg.host_tools import strip_host_tools

                strip_host_tools(p, keep=False)
        _remember(p)
        if call is not None:
            call.post("")
        return {"installed": [f"{d.name} {d.version}" for d in done], "cancelled": cancelled,
                "of": len(order)}
    finally:
        lock.release()


def _record(p: Path, plat, arc, config, link, cat, done: list) -> None:
    """Write the lockfile: what was installed now, merged with what the prefix had."""
    if not done:
        return
    from cvcpkg.lockfile import Lockfile

    lk = Lockfile(platform=plat, arch=arc, config=config, link=link,
                  catalog_revision=cat.get("revision", 0) if isinstance(cat, dict) else 0,
                  bundles=list(done))
    lp = _lockfile(p)
    if lp.is_file():
        with contextlib.suppress(Exception):
            lk = lk.merge(Lockfile.read(lp))
    lk.write(lp)


@export(name="pkg-cancel")
def cancel(prefix: str) -> bool:
    """Ask the install running on ``prefix`` to stop after the package it is on (the window's
    Cancel). What it installed by then stays, and is in the lockfile."""
    _cancels.add(_key(_path(prefix)))
    return True


# ── removing ─────────────────────────────────────────────────────────────────────────────────


@export(name="pkg-remove", is_async=True, with_call=True)
def remove(call, prefix: str, names: list, cascade: bool = False) -> dict:
    """Remove ``names`` from the prefix, as ``cvcpkg uninstall`` does: refused when other
    packages need them, unless ``cascade``, which removes those too. Files another package still
    ships stay. Returns what went, and any file that couldn't be removed."""
    from cvcpkg.cache import default_cache_dir
    from cvcpkg.lockfile import Lockfile
    from cvcpkg.uninstaller import (dependent_closure, execute_removal, fetch_removal_archive,
                                    load_installed, plan_removal)

    p = _path(prefix)
    _guard(p)
    lp = _lockfile(p)
    if not lp.is_file():
        raise RuntimeError("This prefix has no lockfile: cvcpkg installed nothing there.")
    lock = _lock_for(p)
    if not lock.acquire(blocking=False):
        raise RuntimeError("Another job is changing this prefix; wait for it to finish.")
    try:
        lk = Lockfile.read(lp)
        have = {b.name for b in lk.bundles}
        targets = {str(n) for n in names if str(n).strip()}
        if not targets:
            raise RuntimeError("Pick a package to remove.")
        missing = sorted(targets - have)
        if missing:
            raise RuntimeError("Not installed here: " + ", ".join(missing))
        cache = default_cache_dir()
        if call is not None:
            call.post("reading what each package installed")
        with _quiet():
            pkgs = load_installed(lk, cache, recipe_dirs=None)
        closure = dependent_closure(set(targets), pkgs)
        extra = sorted(closure - targets)
        if extra and not cascade:
            raise RuntimeError("Other packages need them: " + ", ".join(extra)
                               + ". Remove those too (Remove with dependents), or keep them.")
        removal = {n: pkgs[n] for n in closure}
        kept = {n: v for n, v in pkgs.items() if n not in removal}
        for n, pkg in removal.items():
            if getattr(pkg, "source_built", False):
                raise RuntimeError(f"{n} was built from source here; cvcpkg can't remove it.")
            if pkg.archive is None:
                if call is not None:
                    call.post(f"fetching {n}'s file list")
                with _quiet():
                    fetch_removal_archive(pkg, lk, cache)
        rplan = plan_removal(removal, kept, lk.platform)
        if call is not None:
            call.post(f"removing {len(removal)} package(s)")
        res = execute_removal(p, [f for n in removal for f in rplan.remove[n]])
        lk.bundles = [b for b in lk.bundles if b.name not in removal]
        lk.write(lp)
        if call is not None:
            call.post("")
        return {"removed": sorted(removal), "files": int(res.removed),
                "failed": [f"{path}: {why}" for path, why in res.failed]}
    except RuntimeError:
        raise
    except Exception as exc:
        raise _fail("Couldn't remove", exc) from exc
    finally:
        lock.release()


# ── prefixes you've used ─────────────────────────────────────────────────────────────────────


def _store() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "cypkg" / "prefixes.json"


def _remember(p: Path) -> None:
    with contextlib.suppress(OSError, ValueError):
        known = recent()
        s = str(p)
        known = [s] + [k for k in known if k != s]
        f = _store()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(known[:20], indent=1), encoding="utf-8")


@export(name="pkg-recent")
def recent() -> list:
    """The prefixes cypkg installed into, most recent first (``~/.config/cypkg/prefixes.json``)."""
    try:
        data = json.loads(_store().read_text(encoding="utf-8"))
        return [str(x) for x in data if isinstance(x, str)]
    except (OSError, ValueError):
        return []


@export(name="pkg-remember")
def remember(prefix: str) -> list:
    """Put ``prefix`` first among the prefixes you've used, and return them."""
    _remember(_path(prefix))
    return recent()
