#!/bin/sh
# Assemble cypkg's browser build: the arigl-web package's three clients plus cypkg's documents and
# a landing page, in the layout a registry serves at /apps/cypkg/.
#
#   tools/site.sh ARI_WEB OUT [CONFIG]
#
# ARI_WEB is share/arigl-web/ of the single-threaded arigl-web package (4.0.9 or newer). It holds
# the three clients, each of which runs main.ari:
#   arigl     index.html, arigl-web.js, arigl-web.css, arigl.js, arigl.wasm, cvc-audio-worklet.js
#             (arigl, Dear ImGui on WebGL)
#   ari       ari.html, ari.js, ari.wasm (ari's FTXUI backend in xterm.js)
#   tvision   ari_tvision.html, ari_tvision.js, ari_tvision.wasm (ari's tvision desktop)
# and the terminal pages' ari-web.js, ari-web.css and xterm/.
#
# OUT/apps/cypkg/ gets those, with the package's index.html renamed arigl.html; web/index.html (the
# landing page, which links the three) as index.html; share/cypkg/*.ari; the package's LICENSE and
# THIRD_PARTY_NOTICES.md as .txt files; and web/ariadne.config.json, which all three pages read. It pins the
# document to main.ari, turns the network on for the page's own origin only, and passes
# --server {origin}: cypkg talks to the registry that serves it. CONFIG replaces that config:
# web/ariadne.config.pages.json is the GitHub Pages build's, which browses https://cvcpkg.org from
# another origin (so cvcpkg.org must allow it with CORS).
set -eu
[ $# -ge 2 ] && [ $# -le 3 ] || { echo "usage: $0 ARI_WEB OUT [CONFIG]" >&2; exit 2; }
web=$1
out=$2/apps/cypkg
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
config=${3:-$root/web/ariadne.config.json}
files="index.html arigl-web.js arigl-web.css arigl.js arigl.wasm cvc-audio-worklet.js
       ari.html ari.js ari.wasm ari_tvision.html ari_tvision.js ari_tvision.wasm
       ari-web.js ari-web.css LICENSE THIRD_PARTY_NOTICES.md"
for f in $files; do
  [ -f "$web/$f" ] || { echo "$web has no $f: is it arigl-web 4.0.9 or newer (wasm)?" >&2; exit 1; }
done
[ -d "$web/xterm" ] || { echo "$web has no xterm/" >&2; exit 1; }
rm -rf "$out"
mkdir -p "$out"
for f in $files; do
  case $f in
    index.html) cp "$web/$f" "$out/arigl.html" ;;
    # .txt, so a static server (GitHub Pages) sends them as text a browser shows
    LICENSE) cp "$web/$f" "$out/LICENSE.txt" ;;
    THIRD_PARTY_NOTICES.md) cp "$web/$f" "$out/THIRD_PARTY_NOTICES.txt" ;;
    *) cp "$web/$f" "$out/$f" ;;
  esac
done
cp -R "$web/xterm" "$out/xterm"
cp "$root/web/index.html" "$root/web/index.css" "$out/"
cp "$root"/share/cypkg/*.ari "$out/"
cp "$config" "$out/ariadne.config.json"
echo "$out"
