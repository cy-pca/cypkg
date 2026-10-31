"""A stand-in cvcpkg registry for cypkg's tests.

    python3 tests/registry/fixture_registry.py [--port 0] [--port-file FILE]

It serves the read endpoints cypkg uses, from catalog.json (see capture.py),
the way cy-pca/cvcpkg's src/cvcpkg/server/app.py does:

- GET /v1/search: q, platform, arch, build_type, link, tag, limit, offset,
  facets. Rows are builds, newest first within a name.
- GET /v1/packages/{name}: every build of one package (none for an unknown name).
- GET /v1/builders, /v1/builds (status, limit, offset), /v1/activity (limit): rows captured
  from cvcpkg.org (fleet.json).
- GET /v1/auth/whoami: a reader named fixture-tester for "Bearer <TEST_TOKEN>" or a paired
  session, else 401.
- POST /v1/auth/device and /v1/auth/device/token: device pairing (client_id cvcpkg-cli); GET
  /_approve?code=CODE[&deny] approves or denies a code, as a person would at /link.
- POST /v1/auth/revoke: ends a paired session.
- GET /v1/live/ws: the live feed, a WebSocket. After {"type":"hello","topics":[...]} it sends
  ready (and the builders snapshot for that topic), then whatever /_live publishes.
- GET /healthz.

For tests: GET /_requests lists the /v1 requests served so far (path, q, offset, facets), and
/_requests?reset=1 clears the list. GET /_live?msg=JSON publishes a live message (builder,
builders, builder_removed, builds, activity or resync) to the feeds subscribed to its topic and
applies it to what the REST endpoints serve; /_live?close=CODE closes every feed with CODE;
/_live?off=1 (or 0) makes new feeds close with 4004, as a server without live updates does; /_live
alone counts the open feeds. A query or package name starting "slow:" is answered after a
second, as if for the rest of the name, so a test can watch a request in flight.

With --port 0 it picks a free port and writes it to --port-file. With --site DIR it also serves
the files under DIR (tools/site.sh's output: /apps/cypkg/...), so the browser build and the API
share one origin, as on a real registry. Stdlib only.
"""

import argparse
import base64
import hashlib
import struct
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


# Device pairing, as cvcpkg's /v1/auth/device does it: the client registers sha256(verifier),
# someone approves the user code (here GET /_approve?code=..., where a person would sign in at
# /link), and the client collects a session with the verifier.
PAIRINGS = {}        # pairing_id -> {code, verifier_hash, approved, collected}
SESSIONS = set()     # live session access tokens
REFRESH = {}         # refresh token -> access token it renews
COUNTER = [0]


def device_start(body):
    if body.get("client_id") != "cvcpkg-cli":
        return 400, {"detail": "unknown client_id"}
    COUNTER[0] += 1
    n = COUNTER[0]
    pid, code = f"pair-{n}", f"CODE-{n:04d}"
    PAIRINGS[pid] = {"code": code, "verifier_hash": body.get("verifier_hash", ""),
                     "approved": False, "collected": False}
    return 200, {"pairing_id": pid, "user_code": code, "verification_uri": "/link",
                 "verification_uri_complete": f"/link?code={code}", "expires_in": 60,
                 "interval": 1}


def device_token(body):
    import hashlib
    p = PAIRINGS.get(body.get("pairing_id", ""))
    if p is None or p["collected"]:
        return 400, {"error": "expired_token"}
    if hashlib.sha256(body.get("verifier", "").encode()).hexdigest() != p["verifier_hash"]:
        return 400, {"error": "access_denied"}
    if p["approved"] == "denied":
        return 400, {"error": "access_denied"}
    if not p["approved"]:
        return 400, {"error": "authorization_pending", "interval": 1}
    p["collected"] = True
    COUNTER[0] += 1
    access = f"cvcses_fixture-session-{COUNTER[0]:04d}-abcdefghij"
    refresh = f"cvcref_fixture-refresh-{COUNTER[0]:04d}-abcdefghij"
    SESSIONS.add(access)
    REFRESH[refresh] = access
    return 200, {"access_token": access, "token_type": "Bearer", "expires_in": 43200,
                 "refresh_token": refresh, "refresh_expires_in": 2592000,
                 "principal": "fixture-tester", "role": "reader", "device": "cypkg"}


def approve(qs):
    code, deny = qs.get("code", [""])[0], "deny" in qs
    for p in PAIRINGS.values():
        if p["code"] == code:
            p["approved"] = "denied" if deny else True
            return 200, {"approved": not deny}
    return 404, {"detail": "no such code"}


def revoke(authorization):
    tok = authorization[len("Bearer "):] if authorization.startswith("Bearer ") else ""
    if tok not in SESSIONS:
        return 401, {"detail": "Not authenticated"}
    SESSIONS.discard(tok)
    return 200, {"revoked": 1}


def whoami(authorization):
    tok = authorization[len("Bearer "):] if authorization.startswith("Bearer ") else ""
    if tok == TEST_TOKEN:
        kind = "token"
    elif tok in SESSIONS:
        kind = "session"
    else:
        return 401, {"detail": "Not authenticated"}
    return 200, {"name": "fixture-tester", "role": "reader", "kind": kind,
                 "principal": "fixture-tester" if kind == "session" else "",
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


# ── The live feed (/v1/live/ws): a minimal RFC 6455 server, text messages only ──

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
TOPIC_OF = {"builder": "builders", "builders": "builders", "builder_removed": "builders",
            "builds": "builds", "activity": "activity"}
LIVE = []  # the open feeds
LIVE_LOCK = threading.Lock()
LIVE_OFF = [False]


class Feed:
    def __init__(self, wfile, topics):
        self.wfile = wfile
        self.topics = topics
        self.lock = threading.Lock()

    def frame(self, opcode, payload):
        n = len(payload)
        head = bytes([0x80 | opcode])
        if n < 126:
            head += bytes([n])
        elif n < 65536:
            head += bytes([126]) + struct.pack("!H", n)
        else:
            head += bytes([127]) + struct.pack("!Q", n)
        with self.lock:
            try:
                self.wfile.write(head + payload)
                self.wfile.flush()
            except OSError:
                pass

    def send(self, msg):
        self.frame(0x1, json.dumps(msg).encode())

    def close(self, code, reason=""):
        self.frame(0x8, struct.pack("!H", code) + reason.encode())


def ws_read(rfile):
    """The next whole message from a client as (opcode, payload); None at the end."""
    first, parts = None, b""
    while True:
        h = rfile.read(2)
        if len(h) < 2:
            return None
        fin, op, n = h[0] & 0x80, h[0] & 0x0F, h[1] & 0x7F
        if n == 126:
            n = struct.unpack("!H", rfile.read(2))[0]
        elif n == 127:
            n = struct.unpack("!Q", rfile.read(8))[0]
        mask = rfile.read(4) if h[1] & 0x80 else b"\0\0\0\0"
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(rfile.read(n)))
        if op >= 0x8:
            return op, data  # a control frame: close, ping or pong
        first = op if first is None else first
        parts += data
        if fin:
            return first, parts


def apply_live(msg):
    """What a published message changes in the REST endpoints' rows."""
    t = msg.get("type")
    if t == "builder":
        rows = FLEET["builders"]
        b = msg["builder"]
        at = next((i for i, x in enumerate(rows) if x["id"] == b["id"]), None)
        if at is None:
            rows.append(b)
        else:
            rows[at] = b
    elif t == "builders":
        FLEET["builders"] = list(msg["builders"])
    elif t == "builder_removed":
        FLEET["builders"] = [x for x in FLEET["builders"] if x["id"] != msg["id"]]
    elif t == "builds":
        rows = FLEET["builds"]
        for j in msg["jobs"]:
            at = next((i for i, x in enumerate(rows) if x["id"] == j["id"]), None)
            if at is None:
                rows.insert(0, j)
            else:
                rows[at] = j
    elif t == "activity":
        FLEET["activity"][:0] = msg["events"]


def publish(qs):
    one = lambda k: qs.get(k, [""])[0]
    with LIVE_LOCK:
        feeds = list(LIVE)
    if one("off"):
        LIVE_OFF[0] = one("off") == "1"
    if one("close"):
        for f in feeds:
            f.close(int(one("close")), "closed by /_live")
        return 200, {"closed": len(feeds)}
    if one("msg"):
        msg = json.loads(one("msg"))
        apply_live(msg)
        topic = TOPIC_OF.get(msg.get("type"))
        sent = 0
        for f in feeds:
            if topic is None or topic in f.topics:
                f.send(msg)
                sent += 1
        return 200, {"sent": sent}
    return 200, {"feeds": len(feeds), "topics": sorted({t for f in feeds for t in f.topics}),
                 "off": LIVE_OFF[0]}


class Handler(http.server.BaseHTTPRequestHandler):
    # HTTP/1.1: a WebSocket handshake needs it. Every reply sends its Content-Length.
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        if u.path == "/v1/live/ws":
            self.live()
            return
        if not u.path.startswith("/v1/") and u.path != "/healthz":
            hit = static(u.path)
            if hit:
                status, ctype, data = hit
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                # A strict policy, as a registry should serve the page with: no inline code or
                # style, no eval, nothing from another origin. ari's page runs under it (#887).
                # The live feed is this origin's too: name its ws:// form, which not every
                # browser counts as 'self'.
                self.send_header("Content-Security-Policy", CSP.replace(
                    "connect-src 'self'",
                    "connect-src 'self' ws://" + self.headers.get("Host", "127.0.0.1")))
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
        elif u.path == "/_approve":
            status, body = approve(urllib.parse.parse_qs(u.query))
        elif u.path == "/_live":
            status, body = publish(urllib.parse.parse_qs(u.query))
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

    def do_POST(self):
        u = urllib.parse.urlsplit(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            body = json.loads(raw) if raw else {}
        except ValueError:
            body = {}
        with REQUESTS_LOCK:
            REQUESTS.append({"path": u.path, "q": "", "offset": "", "facets": ""})
        if u.path == "/v1/auth/device":
            status, out = device_start(body)
        elif u.path == "/v1/auth/device/token":
            status, out = device_token(body)
        elif u.path == "/v1/auth/revoke":
            status, out = revoke(self.headers.get("Authorization", ""))
        else:
            status, out = 404, {"detail": "Not Found"}
        data = json.dumps(out).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def live(self):
        key = self.headers.get("Sec-WebSocket-Key")
        if self.headers.get("Upgrade", "").lower() != "websocket" or not key:
            data = b'{"detail":"a WebSocket endpoint"}'
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        accept = base64.b64encode(hashlib.sha1((key + WS_GUID).encode()).digest()).decode()
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        self.close_connection = True
        feed = Feed(self.wfile, [])
        m = ws_read(self.rfile)
        try:
            hello = json.loads(m[1]) if m and m[0] == 0x1 else {}
        except ValueError:
            hello = {}
        topics = [t for t in hello.get("topics") or [] if t in ("activity", "builders", "builds")]
        with REQUESTS_LOCK:
            REQUESTS.append({"path": "/v1/live/ws", "q": ",".join(topics), "offset": "",
                             "facets": ""})
        if hello.get("type") != "hello" or not topics:
            feed.close(4000, "expected a hello")
            return
        if LIVE_OFF[0]:
            feed.close(4004, "this server has no live updates")
            return
        feed.topics = topics
        feed.send({"type": "ready", "topics": topics, "latest_id": len(FLEET["activity"])})
        if "builders" in topics:
            feed.send({"type": "builders", "builders": FLEET["builders"]})
        with LIVE_LOCK:
            LIVE.append(feed)
        try:
            while True:
                m = ws_read(self.rfile)
                if m is None:
                    break
                if m[0] == 0x8:
                    feed.frame(0x8, m[1][:2])
                    break
                if m[0] == 0x9:
                    feed.frame(0xA, m[1])
        except OSError:
            pass
        finally:
            with LIVE_LOCK:
                if feed in LIVE:
                    LIVE.remove(feed)

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
