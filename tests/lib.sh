#!/bin/sh
# Unit-test share/cypkg/lib.ari's functions with `ari test`: every document in tests/lib/.
#
#   tests/lib.sh [--tap]
#
# No network and no fixture: each test calls functions and asserts on their values. Needs an ari
# with `functions:` (transfix/libcvc#900) and `ari test` (#896). ARI names the ari to run.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
"${ARI:-ari}" test ${1:+"$1"} --timeout 30 "$here"/lib/*.ari
