#!/bin/sh
# Run cypkg's test layers in order, stopping at the first that fails.
#
#   tests/run.sh          1-3: check, units, functions, modules, snapshot, interactive (no tmux:
#                         interactive is skipped), integration (cvcpkg-server can't be installed:
#                         skipped)
#   tests/run.sh --live   ... and 4: the contract check against https://cvcpkg.org
#
# With ARI_WEB and CHROME set, it also runs 3c: the browser build in headless Chrome.
#
# ARI names the ari to run. Until the transfix/libcvc PRs that .github/workflows/test.yml lists
# merge, that is an ari built from libcvc master with them merged in, as that workflow builds it.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

layer() {
  echo "== $1"
  shift
  set +e
  "$@"
  status=$?
  set -e
  if [ $status -eq 77 ]; then echo "skipped"; return 0; fi
  [ $status -eq 0 ] || { echo "== failed: $*"; exit 1; }
}

layer "1. static: ari check on every document" "$here/check.sh"
layer "2a. units: each view over seeded state" "$here/unit.sh"
layer "2b. functions: ari test on lib.ari's functions" "$here/lib.sh"
layer "2c. modules: ari test on each module, mounted alone" "$here/modules.sh"
layer "3a. whole document: snapshots against the fixture registry" "$here/snapshot.sh"
layer "3b. whole document: real keys in tmux, FTXUI and tvision" "$here/interactive.sh"
# The browser build, when ARI_WEB (ari's wasm page: ari.html, ari.js, ari.wasm, ...) and CHROME are
# set; CI's browser job runs it.
if [ -n "${ARI_WEB:-}" ] && [ -n "${CHROME:-}" ]; then
  site=$(mktemp -d)
  layer "3c. browser: the wasm page in headless Chrome" sh -c \
    '"$1/../tools/site.sh" "$2" "$3" >/dev/null && node "$1/browser.mjs" --site "$3" --chrome "$4"' \
    _ "$here" "$ARI_WEB" "$site" "$CHROME"
  rm -rf "$site"
fi
# A real registry: cvcpkg-server installed into a venv, filled with test packages. Skipped when it
# can't be installed (it needs the network, or CVCPKG_VENV naming a venv that has it).
layer "3d. integration: a local cvcpkg-server, seeded with test packages" "$here/integration.sh"
if [ "${1:-}" = --live ]; then
  layer "4. contract: the live registry against what cypkg reads" python3 -I "$here/contract.py"
fi
echo "== all passed"
