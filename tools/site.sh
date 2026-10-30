#!/bin/sh
# Assemble cypkg's browser build: ari's xterm.js page plus cypkg's documents, in the layout a
# registry serves at /apps/cypkg/.
#
#   tools/site.sh ARI_WEB OUT
#
# ARI_WEB holds ari's wasm page: ari.html, ari.js, ari.wasm, ari-web.js, ari-web.css and xterm/
# (transfix/libcvc#887 builds them; the arigl-web package will ship them). OUT/apps/cypkg/ gets
# those, share/cypkg/*.ari and web/ariadne.config.json, which pins the document to main.ari, turns
# the network on for the page's own origin only, and passes --server {origin}: cypkg talks to the
# registry that serves it. index.html is a copy of ari.html, so /apps/cypkg/ opens the terminal.
set -eu
[ $# -eq 2 ] || { echo "usage: $0 ARI_WEB OUT" >&2; exit 2; }
web=$1
out=$2/apps/cypkg
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
for f in ari.html ari.js ari.wasm ari-web.js ari-web.css; do
  [ -f "$web/$f" ] || { echo "$web has no $f: is it ari's wasm page?" >&2; exit 1; }
done
[ -d "$web/xterm" ] || { echo "$web has no xterm/" >&2; exit 1; }
rm -rf "$out"
mkdir -p "$out"
cp "$web"/ari.html "$web"/ari.js "$web"/ari.wasm "$web"/ari-web.js "$web"/ari-web.css "$out/"
cp -R "$web/xterm" "$out/xterm"
cp "$web/ari.html" "$out/index.html"
cp "$root"/share/cypkg/*.ari "$out/"
cp "$root/web/ariadne.config.json" "$out/"
echo "$out"
