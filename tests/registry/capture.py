"""Refresh catalog.json from a live registry.

    python3 tests/registry/capture.py [--server https://cvcpkg.org] [NAME ...]

It fetches GET /v1/packages/{name} for each name and keeps the fields cypkg
shows, so the fixture registry serves real rows. Stdlib only.
"""

import argparse
import json
import pathlib
import urllib.parse
import urllib.request

NAMES = ["ari", "assimp", "cvcpkg", "libpng", "sqlite", "zlib", "zstd"]
KEEP = [
    "name", "version", "platform", "arch", "build_type", "link", "size_bytes",
    "published_at", "description", "homepage", "license", "tags", "org",
    "required_deps", "yanked", "archive_url", "sha256",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="https://cvcpkg.org")
    ap.add_argument("names", nargs="*", default=NAMES)
    a = ap.parse_args()
    rows = []
    for name in a.names:
        url = f"{a.server}/v1/packages/{urllib.parse.quote(name)}"
        with urllib.request.urlopen(url, timeout=30) as r:
            for p in json.load(r)["packages"]:
                rows.append({k: p.get(k) for k in KEEP})
    rows.sort(key=lambda p: (p["name"], p["published_at"]), reverse=False)
    out = pathlib.Path(__file__).with_name("catalog.json")
    out.write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(rows)} rows from {len(a.names)} packages -> {out}")


if __name__ == "__main__":
    main()
