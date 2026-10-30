#!/bin/sh
# Render cypkg's views against the fixture registry with `ari snapshot` and compare them with
# tests/expected/*.txt.
#
#   tests/snapshot.sh            check every case
#   tests/snapshot.sh --update   rewrite the expected files
#   tests/snapshot.sh --show C   print case C's frame and its warnings
#
# ARI names the ari to run (default: ari on PATH). It needs host network flags
# (transfix/libcvc#888) and the JSON verbs (transfix/libcvc#883).
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$here/..
ari=${ARI:-ari}
mode=check
only=
case ${1:-} in
  --update) mode=update ;;
  --show) mode=show; only=${2:?--show needs a case name} ;;
  '') ;;
  *) echo "usage: $0 [--update | --show CASE]" >&2; exit 2 ;;
esac

# name|document flags
cases='search_zlib|--q zlib
search_linux_static|--q zlib --platform linux --link static
search_page2|--q zlib --offset 10
search_none|--q no-such-package
package_zlib|--package zlib
package_zlib_page2|--package zlib --pkg-offset 10
package_missing|--package no-such-package'

tmp=$(mktemp -d)
trap 'kill "$pid" 2>/dev/null || true; rm -rf "$tmp"' EXIT INT TERM
python3 -I "$here/registry/fixture_registry.py" --port 0 --port-file "$tmp/port" &
pid=$!
i=0
while [ ! -s "$tmp/port" ]; do
  i=$((i + 1))
  [ $i -lt 50 ] || { echo "fixture registry did not start" >&2; exit 1; }
  sleep 0.1
done
server=http://127.0.0.1:$(cat "$tmp/port")

fail=0
printf '%s\n' "$cases" | while IFS='|' read -r name flags; do
  [ -z "$only" ] || [ "$only" = "$name" ] || continue
  # shellcheck disable=SC2086 # flags are words
  "$ari" snapshot --width 100 --height 30 --frames 3 --net-allow "$server" \
    "$root/share/cypkg/main.ari" --server "$server" $flags >"$tmp/out" 2>"$tmp/err" || {
    echo "FAIL $name: ari exited $?"; cat "$tmp/err"; exit 1; }
  # The fixture's port changes from run to run: name it, padded to the same width.
  placeholder=$(printf '%-*s' "${#server}" http://registry)
  sed "s#$server#$placeholder#" "$tmp/out" >"$tmp/frame"
  expected=$here/expected/$name.txt
  case $mode in
    show) cat "$tmp/frame"; cat "$tmp/err" >&2 ;;
    update) mkdir -p "$here/expected"; cp "$tmp/frame" "$expected"; echo "updated $name" ;;
    check)
      if [ -s "$tmp/err" ]; then echo "FAIL $name: warnings"; cat "$tmp/err"; exit 1; fi
      if cmp -s "$tmp/frame" "$expected"; then echo "ok   $name"
      else echo "FAIL $name"; diff -u "$expected" "$tmp/frame" || true; exit 1; fi ;;
  esac
done || fail=1
exit $fail
