#!/bin/sh
# Render each view unit test (tests/unit/*.ari) with `ari snapshot`, no network, and compare it
# with tests/unit/expected/. Any warning fails the run.
#
#   tests/unit.sh [--update | --show NAME]
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ari=${ARI:-ari}
mode=check
only=
case ${1:-} in
  --update) mode=update ;;
  --show) mode=show; only=${2:?--show needs a test name} ;;
  '') ;;
  *) echo "usage: $0 [--update | --show NAME]" >&2; exit 2 ;;
esac
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT INT TERM
fail=0
for doc in "$here"/unit/*.ari; do
  name=$(basename "$doc" .ari)
  [ -z "$only" ] || [ "$only" = "$name" ] || continue
  "$ari" snapshot --width 100 --height 30 --frames 2 "$doc" >"$tmp/frame" 2>"$tmp/err" || {
    echo "FAIL $name: ari exited $?"; cat "$tmp/err"; fail=1; continue; }
  expected=$here/unit/expected/$name.txt
  case $mode in
    show) cat "$tmp/frame"; cat "$tmp/err" >&2 ;;
    update) cp "$tmp/frame" "$expected"; echo "updated $name" ;;
    check)
      if [ -s "$tmp/err" ]; then echo "FAIL $name: warnings"; cat "$tmp/err"; fail=1
      elif cmp -s "$tmp/frame" "$expected"; then echo "ok   $name"
      else echo "FAIL $name"; diff -u "$expected" "$tmp/frame" || true; fail=1; fi ;;
  esac
done
exit $fail
