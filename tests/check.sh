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
# state-get gives text (or nil), and (str x) of text quotes it: (str (state-get k)) is "\"1\""
# where "1" was meant. A card's Details sent /v1/builders/"1" that way, which cvcpkg.org refuses
# (422). Use the text itself; (str ...) is for numbers.
if hits=$(grep -n '(str (state-get' "$here"/../share/cypkg/*.ari); then
  echo "FAIL (str (state-get ...)) quotes the text it gives:"; printf '%s\n' "$hits"; fail=1
else echo "ok   no (str (state-get ...)) in share/cypkg"; fi
exit $fail
