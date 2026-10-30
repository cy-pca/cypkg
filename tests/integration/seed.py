"""Publish cypkg's integration-test packages to a local cvcpkg-server.

    python3 tests/integration/seed.py --server URL --token TOKEN --cvcpkg BIN --work DIR

It packs each recipe under tests/integration/recipes/ with `cvcpkg pack`, publishes the bundles
with `cvcpkg publish`, then publishes quill's bundle again through POST /v1/publish as more builds
(other platforms, architectures and link modes) with the metadata the server recorded for it. A
build machine tags a bundle with its own platform and arch only, so that is the one way to give
one package builds for several. What it publishes (SEED below) is what tests/integration/ asserts.

The registry orders a package's builds newest first, and records the time to the second, so it
waits for the next second before each of quill's builds: the order is the order below, reversed.
Stdlib only, besides the cvcpkg it is given.
"""

import argparse
import json
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

HERE = pathlib.Path(__file__).parent
RECIPES = HERE / "recipes"

# quill's builds after the two `cvcpkg publish`es (1.3.0 and 1.4.2, both any/noarch), oldest first:
# (platform, arch, build_type, link). With them it has 12 builds, so its builds page has two
# pages of 10.
QUILL_BUILDS = [
    ("linux", "x86_64", "release", "shared"),
    ("linux", "x86_64", "release", "static"),
    ("linux", "arm64", "release", "shared"),
    ("macos", "x86_64", "release", "shared"),
    ("macos", "arm64", "release", "shared"),
    ("windows", "x86_64", "release", "shared"),
    ("windows", "x86_64", "debug", "shared"),
    ("freebsd", "x86_64", "release", "shared"),
    ("wasm", "wasm32", "release", "static"),
    ("wasi", "wasm32", "release", "static"),
]


def run(*cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit(f"seed: {' '.join(map(str, cmd))} exited {p.returncode}\n{p.stdout}{p.stderr}")
    return p.stdout


def get(server, path):
    with urllib.request.urlopen(server + path, timeout=30) as r:
        return json.load(r)


def next_second():
    """Sleep into the next wall-clock second, so the next publish has a later published_at."""
    time.sleep(1.0 - time.time() % 1.0 + 0.05)


def publish_api(server, token, archive, row, build):
    """POST /v1/publish: archive as one more build, a (platform, arch, build_type, link), with
    the metadata of row, a build the server already has."""
    platform, arch, build_type, link = build
    query = {
        "name": row["name"], "version": row["version"], "platform": platform, "arch": arch,
        "build_type": build_type, "link": link, "recipe_version": row["recipe_version"],
        "description": row["description"], "homepage": row["homepage"],
        "license": row["license"], "maintainer": row["maintainer"], "tags": row["tags"],
    }
    boundary = uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            f"filename=\"{archive.name}\"\r\nContent-Type: application/octet-stream\r\n\r\n"
            ).encode() + archive.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{server}/v1/publish?{urllib.parse.urlencode(query)}", data=body, method="POST",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        urllib.request.urlopen(req, timeout=60).read()
    except urllib.error.HTTPError as e:
        sys.exit(f"seed: publishing {row['name']} as {'/'.join(build)}: HTTP {e.code} "
                 f"{e.read().decode(errors='replace')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", required=True)
    ap.add_argument("--token", required=True)
    ap.add_argument("--cvcpkg", required=True, help="the cvcpkg command to pack and publish with")
    ap.add_argument("--work", required=True, help="a directory for build prefixes and bundles")
    a = ap.parse_args()
    server = a.server.rstrip("/")
    work = pathlib.Path(a.work)
    dist = work / "dist"
    recipes = ["--local", "--no-default-recipes", "--recipes-dir", str(RECIPES),
               "--platform", "any", "--output-dir", str(dist)]

    def pack(name, *extra):
        out = run(a.cvcpkg, "pack", name, *recipes, *extra)
        return dist / next(line.split()[2] for line in out.splitlines()
                           if line.startswith("cvcpkg: packed "))

    def publish(archive):
        run(a.cvcpkg, "publish", str(archive), "--server", server, "--token", a.token)

    bundles = {name: pack(name, "--prefix", str(work / f"prefix-{name}"))
               for name in ("quill", "quill-tools", "bare")}
    # An older quill, from the same files.
    old_quill = pack("quill", "--from-prefix", str(work / "prefix-quill"),
                     "--version-override", "1.3.0", "--cvc-revision", "1")

    publish(bundles["bare"])
    publish(bundles["quill-tools"])
    publish(old_quill)
    next_second()
    publish(bundles["quill"])
    row = next(r for r in get(server, "/v1/packages/quill")["packages"]
               if r["version"].startswith("1.4.2"))
    for build in QUILL_BUILDS:
        next_second()
        publish_api(server, a.token, bundles["quill"], row, build)

    total = get(server, "/v1/search?limit=1&facets=true")["total"]
    print(f"seed: published {total} builds to {server}")


if __name__ == "__main__":
    main()
