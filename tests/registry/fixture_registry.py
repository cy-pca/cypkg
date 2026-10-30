"""A stand-in cvcpkg registry for cypkg's tests.

    python3 tests/registry/fixture_registry.py [--port 0] [--port-file FILE]

It serves the read endpoints cypkg uses, from catalog.json (see capture.py),
the way cy-pca/cvcpkg's src/cvcpkg/server/app.py does:

- GET /v1/search: q, platform, arch, build_type, link, tag, limit, offset,
  facets. Rows are builds, newest first within a name.
- GET /v1/packages/{name}: every build of one package (none for an unknown name).
- GET /v1/builders, /v1/builds (status, limit, offset), /v1/activity (limit): rows captured
  from cvcpkg.org (fleet.json).
- GET /v1/auth/whoami: a reader named fixture-tester for "Bearer <TEST_TOKEN>", else 401.
- GET /healthz.

For tests: GET /_requests lists the /v1 requests served so far (path, q, offset, facets), and
/_requests?reset=1 clears the list. A query or package name starting "slow:" is answered after a
second, as if for the rest of the name, so a test can watch a request in flight.

With --port 0 it picks a free port and writes it to --port-file. With --site DIR it also serves
the files under DIR (tools/site.sh's output: /apps/cypkg/...), so the browser build and the API
share one origin, as on a real registry. Stdlib only.
"""

import argparse
import threading
import time
import collections
import http.server
import json
import mimetypes
import pathlib
import urllib.parse

SITE = None  # --site: a directory of static files, or None
CSP = ("default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; "
       "connect-src 'self'; img-src 'self' data: blob:")
TYPES = {".wasm": "application/wasm", ".js": "text/javascript", ".mjs": "text/javascript",
         ".css": "text/css", ".html": "text/html; charset=utf-8", ".json": "application/json",
         ".ari": "text/plain; charset=utf-8", ".map": "application/json"}

HERE = pathlib.Path(__file__).parent
# Real rows (capture.py), then synthetic edge cases (edge.json).
CATALOG = json.loads((HERE / "catalog.json").read_text()) + json.loads(
    (HERE / "edge.json").read_text())["rows"]

# Builders, builds and activity captured from cvcpkg.org (fleet.json), for those windows.
FLEET = json.loads((HERE / "fleet.json").read_text())
# The API token tests sign in with (an env var the launcher hands to ari; never a real token).
TEST_TOKEN = "cvctok_fixture-test-token-0123456789"

# Faults, chosen by the query or package name, for the error paths.
FAULTS = {
    "fault-500": (500, {"detail": "internal error"}),
    "fault-badjson": (200, "<html>not json</html>"),
    "fault-shape": (200, {"total": 3, "packages": "not a list"}),
    "fault-empty": (200, {"total": 0, "packages": []}),
}
FACETS = {
    "platforms": "platform", "archs": "arch", "build_types": "build_type",
    "links": "link",
}


def ordered(rows):
    rows = sorted(rows, key=lambda p: p["published_at"] or "", reverse=True)
    return sorted(rows, key=lambda p: p["name"])


REQUESTS = []
REQUESTS_LOCK = threading.Lock()


def slow(name):
    """The name without a "slow:" prefix, after a second's wait when it had one."""
    if name.startswith("slow:"):
        time.sleep(1.0)
        return name[len("slow:"):]
    return name


def search(qs):
    if qs.get("q", [""])[0].startswith("slow:"):
        qs = dict(qs, q=[slow(qs["q"][0])])
    one = lambda k: qs.get(k, [""])[0]
    if one("q") in FAULTS:
        return FAULTS[one("q")]
    q = one("q").lower()
    rows = [
        p for p in CATALOG
        if not p.get("yanked")
        and (not q or q in p["name"].lower() or q in (p.get("tags") or "").lower()
             or q in (p.get("description") or "").lower())
        and all(not one(k) or p[k] == one(k) for k in ("platform", "arch", "build_type", "link"))
        and (not one("tag") or one("tag") in (p.get("tags") or "").split(","))
    ]
    rows = ordered(rows)
    limit = max(0, min(200, int(one("limit") or 50)))
    offset = max(0, int(one("offset") or 0))
    page = rows[offset:offset + limit]
    reply = {
        "total": len(rows),
        # As the server does: over every match with facets, over the page without.
        "package_count": len({p["name"] for p in (rows if one("facets") != "false" else page)}),
        "total_size_bytes": sum(p["size_bytes"] or 0 for p in rows),
        "packages": page,
        "limit": limit,
        "offset": offset,
        "query": one("q"),
    }
    if one("facets") != "false":
        reply["facets"] = {
            facet: [{"value": v, "count": n}
                    for v, n in collections.Counter(p[key] for p in rows).most_common()]
            for facet, key in FACETS.items()
        }
    return 200, reply


def builders():
    return 200, {"total": len(FLEET["builders"]), "builders": FLEET["builders"]}


def builds(qs):
    one = lambda k: qs.get(k, [""])[0]
    rows = [j for j in FLEET["builds"] if not one("status") or j["status"] == one("status")]
    limit = max(1, min(1000, int(one("limit") or 100)))
    offset = max(0, int(one("offset") or 0))
    return 200, {"total": len(rows), "jobs": rows[offset:offset + limit]}


def activity(qs):
    limit = max(1, int(qs.get("limit", ["50"])[0] or 50))
    ev = FLEET["activity"][:limit]
    return 200, {"events": ev, "total": len(FLEET["activity"]),
                 "max_id": max((e["id"] for e in FLEET["activity"]), default=0)}


def whoami(authorization):
    if authorization != "Bearer " + TEST_TOKEN:
        return 401, {"detail": "Not authenticated"}
    return 200, {"name": "fixture-tester", "role": "reader", "kind": "token", "principal": "",
                 "email": "tester@example.org", "issuer": "", "subject": "",
                 "device": "fixture-tester", "session_id": None, "expires_at": "",
                 "orgs": [{"slug": "cvc", "role": "member"}]}


def package(name):
    name = slow(name)
    if name in FAULTS:
        return FAULTS[name]
    # As cvcpkg.org does: an unknown name is 200 with no builds, not 404 (tests/contract.py).
    rows = ordered(p for p in CATALOG if p["name"] == name)
    return 200, {"total": len(rows), "packages": rows}


def static(path):
    """(status, content type, bytes) for a file under SITE, or None."""
    if SITE is None:
        return None
    rel = urllib.parse.unquote(path).lstrip("/")
    f = (SITE / rel).resolve()
    if f.is_dir():
        f = f / "index.html"
    if SITE not in f.parents or not f.is_file():
        return None
    ctype = TYPES.get(f.suffix) or mimetypes.guess_type(f.name)[0] or "application/octet-stream"
    return 200, ctype, f.read_bytes()


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        if not u.path.startswith("/v1/") and u.path != "/healthz":
            hit = static(u.path)
            if hit:
                status, ctype, data = hit
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                # A strict policy, as a registry should serve the page with: no inline code or
                # style, no eval, nothing from another origin. ari's page runs under it (#887).
                self.send_header("Content-Security-Policy", CSP)
                self.end_headers()
                self.wfile.write(data)
                return
        if u.path.startswith("/v1/"):
            q = urllib.parse.parse_qs(u.query)
            with REQUESTS_LOCK:
                REQUESTS.append({"path": u.path, "q": q.get("q", [""])[0],
                                 "offset": q.get("offset", [""])[0],
                                 "facets": q.get("facets", [""])[0]})
        if u.path == "/_requests":
            with REQUESTS_LOCK:
                status, body = 200, {"requests": list(REQUESTS)}
                if "reset" in urllib.parse.parse_qs(u.query):
                    REQUESTS.clear()
        elif u.path == "/v1/search":
            status, body = search(urllib.parse.parse_qs(u.query))
        elif u.path == "/v1/builders":
            status, body = builders()
        elif u.path == "/v1/builds":
            status, body = builds(urllib.parse.parse_qs(u.query))
        elif u.path == "/v1/activity":
            status, body = activity(urllib.parse.parse_qs(u.query))
        elif u.path == "/v1/auth/whoami":
            status, body = whoami(self.headers.get("Authorization", ""))
        elif u.path.startswith("/v1/packages/"):
            status, body = package(urllib.parse.unquote(u.path[len("/v1/packages/"):]))
        elif u.path == "/healthz":
            status, body = 200, {"status": "ok"}
        else:
            status, body = 404, {"detail": "Not Found"}
        data = (body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--port-file")
    ap.add_argument("--site", help="also serve the static files under this directory")
    a = ap.parse_args()
    global SITE
    SITE = pathlib.Path(a.site).resolve() if a.site else None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    if a.port_file:
        pathlib.Path(a.port_file).write_text(str(server.server_address[1]))
    server.serve_forever()


if __name__ == "__main__":
    main()
