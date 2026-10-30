"""A stand-in cvcpkg registry for cypkg's tests.

    python3 tests/registry/fixture_registry.py [--port 0] [--port-file FILE]

It serves the read endpoints cypkg uses, from catalog.json (see capture.py),
the way cy-pca/cvcpkg's src/cvcpkg/server/app.py does:

- GET /v1/search: q, platform, arch, build_type, link, tag, limit, offset,
  facets. Rows are builds, newest first within a name.
- GET /v1/packages/{name}: every build of one package.
- GET /healthz.

With --port 0 it picks a free port and writes it to --port-file. Stdlib only.
"""

import argparse
import collections
import http.server
import json
import pathlib
import urllib.parse

CATALOG = json.loads(pathlib.Path(__file__).with_name("catalog.json").read_text())
FACETS = {
    "platforms": "platform", "archs": "arch", "build_types": "build_type",
    "links": "link",
}


def ordered(rows):
    rows = sorted(rows, key=lambda p: p["published_at"], reverse=True)
    return sorted(rows, key=lambda p: p["name"])


def search(qs):
    one = lambda k: qs.get(k, [""])[0]
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
        "total_size_bytes": sum(p["size_bytes"] for p in rows),
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


def package(name):
    rows = ordered(p for p in CATALOG if p["name"] == name)
    if not rows:
        return 404, {"detail": f"package {name!r} not found"}
    return 200, {"total": len(rows), "packages": rows}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        if u.path == "/v1/search":
            status, body = search(urllib.parse.parse_qs(u.query))
        elif u.path.startswith("/v1/packages/"):
            status, body = package(urllib.parse.unquote(u.path[len("/v1/packages/"):]))
        elif u.path == "/healthz":
            status, body = 200, {"status": "ok"}
        else:
            status, body = 404, {"detail": "Not Found"}
        data = json.dumps(body).encode()
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
    a = ap.parse_args()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    if a.port_file:
        pathlib.Path(a.port_file).write_text(str(server.server_address[1]))
    server.serve_forever()


if __name__ == "__main__":
    main()
