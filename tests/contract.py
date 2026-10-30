"""Check that a live registry still sends what cypkg reads, and that the fixture matches it.

    python3 tests/contract.py [--server https://cvcpkg.org] [--query zlib] [--package zlib]

cypkg's documents read a handful of fields from two endpoints. The fixture registry serves rows
captured earlier, so the snapshot tests can pass while the real API has moved on. This checks
the live replies against the fields and types the documents use, and the fixture's rows against
the live keys. It needs the network, so it doesn't gate a merge; run it by hand or on a
schedule. tests/integration.sh also runs it against a local cvcpkg-server, with that registry's
query and package. Stdlib only. Exits 1 on any mismatch.
"""

import argparse
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

STR, INT, LIST = str, int, list
OPT_STR = (str, type(None))
OPT_INT = (int, type(None))

# What share/cypkg/main.ari and views.ari read (search.res.*, pkg.all.*).
SEARCH = {"total": INT, "package_count": INT, "packages": LIST}
SEARCH_ROW = {"name": STR, "version": STR, "platform": STR, "arch": STR, "link": STR,
              "size_bytes": INT}
PACKAGE = {"packages": LIST}
PACKAGE_ROW = {"version": STR, "platform": STR, "arch": STR, "build_type": STR, "link": STR,
               "size_bytes": OPT_INT, "published_at": OPT_STR, "description": OPT_STR,
               "license": OPT_STR, "homepage": OPT_STR, "tags": OPT_STR}

problems = []


def get(server, path, query=None):
    url = server + path + ("?" + urllib.parse.urlencode(query) if query else "")
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, None


def check(where, obj, fields):
    if not isinstance(obj, dict):
        problems.append(f"{where}: not a JSON object")
        return
    for k, t in fields.items():
        if k not in obj:
            problems.append(f"{where}: no field {k!r}")
        elif not isinstance(obj[k], t) or isinstance(obj[k], bool):
            problems.append(f"{where}: {k!r} is {type(obj[k]).__name__}, not {t}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="https://cvcpkg.org")
    ap.add_argument("--query", default="zlib", help="a search that finds two packages or more")
    ap.add_argument("--package", default="zlib", help="a package with builds")
    a = ap.parse_args()
    s = a.server.rstrip("/")
    q, pkg = a.query, a.package

    status, d = get(s, "/v1/search", {"q": q, "limit": 10, "offset": 0, "facets": "true"})
    if status != 200:
        problems.append(f"/v1/search: HTTP {status}")
    else:
        check("/v1/search", d, SEARCH)
        for i, row in enumerate(d.get("packages") or []):
            check(f"/v1/search packages[{i}]", row, SEARCH_ROW)
        # cypkg sends facets=true because package_count is page-local without it.
        _, nf = get(s, "/v1/search", {"q": q, "limit": 10, "offset": 0, "facets": "false"})
        if nf and nf.get("package_count", 0) > d.get("package_count", 0):
            problems.append("/v1/search: package_count is larger without facets")

    status, d = get(s, f"/v1/packages/{pkg}")
    live_keys = set()
    if status != 200:
        problems.append(f"/v1/packages/{pkg}: HTTP {status}")
    else:
        check(f"/v1/packages/{pkg}", d, PACKAGE)
        rows = d.get("packages") or []
        if not rows:
            problems.append(f"/v1/packages/{pkg}: no builds")
        for i, row in enumerate(rows):
            check(f"/v1/packages/{pkg} packages[{i}]", row, PACKAGE_ROW)
            live_keys |= set(row)

    # cypkg reads an empty list as "no package named ..."; the fixture serves the same.
    status, d = get(s, "/v1/packages/cypkg-contract-no-such-package")
    if status != 200 or not isinstance(d, dict) or d.get("packages") != []:
        problems.append(f"/v1/packages/<unknown>: HTTP {status} {d!r}, not 200 with no builds")

    # The fixture's real rows must have only keys the live API still sends.
    catalog = json.loads(pathlib.Path(__file__).with_name("registry").joinpath(
        "catalog.json").read_text())
    if live_keys:
        stale = sorted(set().union(*map(set, catalog)) - live_keys)
        if stale:
            problems.append(f"tests/registry/catalog.json: keys the API no longer sends: {stale}")

    for p in problems:
        print("FAIL", p)
    if not problems:
        print(f"ok   {s} sends every field cypkg reads, and the fixture matches it")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
