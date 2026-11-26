#!/bin/sh
# Load every document with `ari check` and fail on any warning: YAML errors, unknown functions
# (the DSL has no min, max, cond or list?, for example), a bad args: block, an unknown unit.
#
#   tests/check.sh
#
# The documents with a python: block (prefixes.ari, and mainx.ari, which loads it) need a
# scripting host: they are checked with ARIX when it names an arix, and skipped otherwise (the
# stock ari warns on any python: block).
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ari=${ARI:-ari}
arix=${ARIX:-}
fail=0
for doc in "$here"/../share/cypkg/*.ari "$here"/unit/*.ari; do
  name=${doc#"$here"/}; name=${name#../}
  host=$ari
  if grep -q '^python:' "$doc" || [ "$(basename -- "$doc")" = mainx.ari ]; then
    if [ -z "$arix" ]; then echo "skip $name (python: set ARIX to check it)"; continue; fi
    host=$arix
  fi
  # --net: main.ari requires the network. check sends no request.
  if out=$("$host" check --net "$doc" 2>&1) && [ -z "$out" ]; then echo "ok   $name"
  else echo "FAIL $name"; printf '%s\n' "$out"; fail=1; fi
done
exit $fail
