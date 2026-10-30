#!/bin/sh
# Drive cypkg with real keys, in a tmux pane, on each terminal backend.
#
#   tests/interactive.sh [ftxui|tvision ...]    (default: both)
#
# `ari snapshot` can't send input and always lays out with FTXUI, so this is what checks typing,
# focus, the buttons, and the tvision desktop. It runs bin/cypkg against the fixture registry and,
# after each step, waits for the screen to show what the step should. ARI names the ari to run.
# Needs tmux.
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$here/..
ari=${ARI:-ari}
command -v tmux >/dev/null || { echo "skip: tmux is not installed"; exit 77; }
[ $# -gt 0 ] || set -- ftxui tvision

tmp=$(mktemp -d)
session=cypkg-test-$$
trap 'tmux kill-session -t "$session" 2>/dev/null || true; kill "$pid" 2>/dev/null || true; rm -rf "$tmp"' EXIT INT TERM
python3 -I "$here/registry/fixture_registry.py" --port 0 --port-file "$tmp/port" &
pid=$!
i=0
while [ ! -s "$tmp/port" ]; do
  i=$((i + 1)); [ $i -lt 50 ] || { echo "fixture registry did not start" >&2; exit 1; }
  sleep 0.1
done
server=http://127.0.0.1:$(cat "$tmp/port")

screen() { tmux capture-pane -p -t "$session"; }
keys() { tmux send-keys -t "$session" "$@"; sleep 0.25; }
type_text() { tmux send-keys -t "$session" -l "$1"; sleep 0.25; }
# wait_for STEP PATTERN: the screen matches the extended regex PATTERN within 10 s.
wait_for() {
  n=0
  until screen | grep -q -E -- "$2"; do
    n=$((n + 1))
    if [ $n -ge 100 ]; then
      echo "FAIL $backend: $1: the screen never showed /$2/"; screen; return 1
    fi
    sleep 0.1
  done
  echo "ok   $backend: $1"
}

fail=0
for backend in "$@"; do
  flag=
  [ "$backend" = tvision ] && flag=--tvision
  tmux kill-session -t "$session" 2>/dev/null || true
  tmux new-session -d -s "$session" -x 100 -y 30 \
    "CYPKG_ARI='$ari' '$root/bin/cypkg' $flag --server '$server' 2>'$tmp/err'; echo \"exit \$?\" >'$tmp/exit'; sleep 30"
  (
    wait_for "starts on every build" 'builds 1-10 of 196, 10 packages'
    keys Tab; type_text zstd; keys Enter
    wait_for "Enter in the search field searches" 'builds 1-10 of 25, 1 package([^s]|$)'
    keys Tab; keys Right
    wait_for "a platform filter searches again" 'Platform: < linux >'
    wait_for "... and shows only that platform" 'builds 1-5 of 5, 1 package([^s]|$)'
    keys Tab; keys Tab; keys Tab; keys Enter
    wait_for "Open shows the package" 'package: zstd'
    wait_for "... with its install line" 'install: cvcpkg install zstd'
    wait_for "... and its first builds" 'builds 1-10 of 25'
    keys Tab; keys Tab; keys Enter
    wait_for "Next pages the builds" 'builds 11-20 of 25'
    keys Enter
    wait_for "... to the last page" 'builds 21-25 of 25'
    keys Tab; keys Enter
    wait_for "Back returns to the search" 'Search: \[zstd\]'
    wait_for "... with its filters kept" 'builds 1-5 of 5, 1 package([^s]|$)'
    keys C-c
    n=0
    while [ ! -s "$tmp/exit" ]; do
      n=$((n + 1)); [ $n -lt 50 ] || { echo "FAIL $backend: Ctrl-C did not quit"; exit 1; }
      sleep 0.1
    done
    [ "$(cat "$tmp/exit")" = "exit 0" ] || { echo "FAIL $backend: Ctrl-C exited with $(cat "$tmp/exit")"; exit 1; }
    echo "ok   $backend: Ctrl-C quits"
    if [ -s "$tmp/err" ]; then echo "FAIL $backend: warnings"; cat "$tmp/err"; exit 1; fi
  ) || fail=1
  rm -f "$tmp/exit" "$tmp/err"
done
exit $fail
