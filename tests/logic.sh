#!/bin/sh
# Test main.ari's request logic with `ari test` (transfix/libcvc#896) against the fixture registry.
#
#   tests/logic.sh [--tap]
#
# `ari test` takes no document arguments, and the tests belong in tests/, not in the shipped
# document. So this writes a copy of main.ari beside it (for its relative import:), with the
# fixture as the server's default and tests/logic.tests.yaml appended, runs `ari test` on that
# copy, and removes it. ARI names the ari to run.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
share=$here/../share/cypkg
ari=${ARI:-ari}

tmp=$(mktemp -d)
doc=$share/.main.test.$$.ari
trap 'kill "$pid" 2>/dev/null || true; rm -rf "$tmp" "$doc"' EXIT INT TERM
python3 -I "$here/registry/fixture_registry.py" --port 0 --port-file "$tmp/port" &
pid=$!
i=0
while [ ! -s "$tmp/port" ]; do
  i=$((i + 1)); [ $i -lt 50 ] || { echo "fixture registry did not start" >&2; exit 1; }
  sleep 0.1
done
server=http://127.0.0.1:$(cat "$tmp/port")

grep -q '^tests:' "$share/main.ari" && { echo "main.ari has its own tests: block" >&2; exit 1; }
sed "s#default: \"https://cvcpkg.org\"#default: \"$server\"#" "$share/main.ari" >"$doc"
grep -q "default: \"$server\"" "$doc" || { echo "couldn't point the copy at the fixture" >&2; exit 1; }
{ echo; cat "$here/logic.tests.yaml"; } >>"$doc"

"$ari" test ${1:+"$1"} --timeout 60 --net-allow "$server" "$doc"
