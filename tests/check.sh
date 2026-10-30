#!/bin/sh
# Load every document with `ari check` and fail on any warning: YAML errors, unknown functions
# (the DSL has no min, max, cond or list?, for example), a bad args: block, an unknown unit.
#
#   tests/check.sh
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ari=${ARI:-ari}
fail=0
for doc in "$here"/../share/cypkg/*.ari "$here"/unit/*.ari; do
  name=${doc#"$here"/}; name=${name#../}
  # --net: main.ari requires the network. check sends no request.
  if out=$("$ari" check --net "$doc" 2>&1) && [ -z "$out" ]; then echo "ok   $name"
  else echo "FAIL $name"; printf '%s\n' "$out"; fail=1; fi
done
exit $fail
