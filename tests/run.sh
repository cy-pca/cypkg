#!/bin/sh
# Run cypkg's test layers in order, stopping at the first that fails.
#
#   tests/run.sh          1-3: check, unit, logic, snapshot, interactive (skipped without tmux)
#   tests/run.sh --live   ... and 4: the contract check against https://cvcpkg.org
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
layer "2c. logic: ari test on main.ari's requests" "$here/logic.sh"
layer "3a. whole document: snapshots against the fixture registry" "$here/snapshot.sh"
layer "3b. whole document: real keys in tmux, FTXUI and tvision" "$here/interactive.sh"
if [ "${1:-}" = --live ]; then
  layer "4. contract: the live registry against what cypkg reads" python3 -I "$here/contract.py"
fi
echo "== all passed"
