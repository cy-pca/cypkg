#!/bin/sh
# Test each module on its own with `ari test`: every document in tests/modules/ mounts one module
# (search.ari, package.ari) against the fixture registry.
#
#   tests/modules.sh [--tap]
#
# `ari test` takes no document arguments, so this writes a copy of each test document beside it
# (for its relative load:), with the fixture's URL in place of @SERVER@, and removes it after.
# ARI names the ari to run.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ari=${ARI:-ari}

tmp=$(mktemp -d)
copies=
trap 'kill "$pid" 2>/dev/null || true; rm -rf "$tmp"; [ -z "$copies" ] || rm -f $copies' EXIT INT TERM
python3 -I "$here/registry/fixture_registry.py" --port 0 --port-file "$tmp/port" &
pid=$!
i=0
while [ ! -s "$tmp/port" ]; do
  i=$((i + 1)); [ $i -lt 50 ] || { echo "fixture registry did not start" >&2; exit 1; }
  sleep 0.1
done
server=http://127.0.0.1:$(cat "$tmp/port")

for doc in "$here"/modules/*_test.ari; do
  copy=$here/modules/.$(basename "$doc" .ari).$$.ari
  sed "s#@SERVER@#$server#" "$doc" >"$copy"
  copies="$copies $copy"
done
# Signed in with the fixture's test token, as bin/cypkg --token-env does: ari takes it from the
# environment, and a policy line binds it to the fixture's origin. Documents that want an anonymous
# run say so (auth.signed_in "0"); account_test.ari asks the host.
printf 'allow %s\ncredential cvcpkg %s\n' "$server" "$server" >"$tmp/policy"
token=$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import fixture_registry as f; print(f.TEST_TOKEN)' "$here/registry")
# shellcheck disable=SC2086 # the copies are words
CYPKG_TEST_TOKEN=$token "$ari" test ${1:+"$1"} --timeout 60 --net-policy "$tmp/policy" \
  --credential-env cvcpkg=CYPKG_TEST_TOKEN $copies
