#!/bin/sh
# Run cypkg against a real cvcpkg registry: a local cvcpkg-server, filled with test packages.
#
#   tests/integration.sh            run every step
#   tests/integration.sh --update   ... and rewrite the expected frames, tests/integration/expected/
#
# The other layers serve cypkg captured rows from a stand-in (tests/registry/); this one starts
# cy-pca/cvcpkg's own server, so it fails when the server stops sending what cypkg reads.
#
#  1. Installs cvcpkg (the server and the client) from cy-pca/cvcpkg at CVCPKG_REF into a venv:
#     CVCPKG_VENV, kept for the next run, or one in its temp dir. When it can't, it exits 77
#     (skipped), or 1 with CVCPKG_REQUIRED=1, as CI sets.
#  2. Starts `cvcpkg-server run` on a free port, its state (SQLite, the archives) in a temp dir
#     (on /dev/shm if there is one): no database server. SQLite takes the same code path as
#     cvcpkg.org's PostgreSQL; the server's YAML backend leaves descriptions out of
#     /v1/packages/{name}.
#  3. Mints a publisher token and publishes tests/integration/recipes/ (seed.py).
#  4. tests/contract.py against it: the fields and types cypkg reads.
#  5. `ari test` on tests/integration/modules/, each module mounted alone.
#  6. `ari snapshot` frames, compared with tests/integration/expected/.
#
# ARI names the ari to run, as for tests/run.sh.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$here/..
ari=${ARI:-ari}
ref=${CVCPKG_REF:-1c373c6fc15ddb1e09552d35d5893062a345928d}
mode=check
case ${1:-} in
  --update) mode=update ;;
  '') ;;
  *) echo "usage: $0 [--update]" >&2; exit 2 ;;
esac

tmp=$(mktemp -d)
# The server's state, on a tmpfs where there is one: SQLite syncs every commit, and creating its
# tables took two minutes on a busy disk, against a tenth of a second in memory.
state=$(mktemp -d -p /dev/shm 2>/dev/null || mktemp -d)
pid=
copies=
cleanup() {
  [ -z "$pid" ] || kill "$pid" 2>/dev/null || true
  # shellcheck disable=SC2086 # the copies are words
  [ -z "$copies" ] || rm -f $copies
  rm -rf "$tmp" "$state"
}
trap cleanup EXIT
trap 'exit 1' INT TERM

# 1. cvcpkg
venv=${CVCPKG_VENV:-$tmp/venv}
if [ ! -x "$venv/bin/cvcpkg-server" ]; then
  echo "installing cvcpkg from cy-pca/cvcpkg@$ref"
  if ! { python3 -m venv "$venv" &&
         "$venv/bin/pip" install --quiet --disable-pip-version-check \
           "cvcpkg[server,db-sqlite] @ git+https://github.com/cy-pca/cvcpkg@$ref"; } \
       >"$tmp/install.log" 2>&1; then
    tail -5 "$tmp/install.log"
    echo "cvcpkg-server could not be installed"
    [ "${CVCPKG_REQUIRED:-}" = 1 ] && exit 1
    exit 77
  fi
fi

# 2. the server
mkdir -p "$tmp/home"
export CVCPKG_DATABASE_URL="sqlite+aiosqlite:///$state/registry.db"
port=$(python3 -I -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])')
server=http://127.0.0.1:$port
token=$("$venv/bin/cvcpkg-server" token create --name seed --role publisher --state-dir "$state" |
        sed -n 's/^ *\(cvctok_[A-Za-z0-9_-]*\).*/\1/p')
[ -n "$token" ] || { echo "cvcpkg-server minted no token"; exit 1; }
"$venv/bin/cvcpkg-server" run --state-dir "$state" --host 127.0.0.1 --port "$port" \
  >"$tmp/server.log" 2>&1 &
pid=$!
i=0
until python3 -I -c 'import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=2)' \
        "$server/healthz" 2>/dev/null; do
  i=$((i + 1))
  if [ $i -ge 150 ] || ! kill -0 "$pid" 2>/dev/null; then
    echo "cvcpkg-server did not start"; cat "$tmp/server.log"; exit 1
  fi
  sleep 0.2
done
echo "ok   cvcpkg-server $("$venv/bin/cvcpkg-server" --version | sed 's/.* //') at $server"

# 3. the packages. cvcpkg's own config and caches go to a scratch home.
HOME=$tmp/home python3 -I "$here/integration/seed.py" --server "$server" --token "$token" \
  --cvcpkg "$venv/bin/cvcpkg" --work "$tmp/work"

# 4. the contract
python3 -I "$here/contract.py" --server "$server" --query quill --package quill

# 5. the modules
for doc in "$here"/integration/modules/*_test.ari; do
  copy=$here/integration/modules/.$(basename "$doc" .ari).$$.ari
  sed "s#@SERVER@#$server#" "$doc" >"$copy"
  copies="$copies $copy"
done
# shellcheck disable=SC2086 # the copies are words
"$ari" test --timeout 60 --net-allow "$server" $copies

# 6. snapshots: name|document flags
cases='search_all|
search_quill|--q quill
search_quill_page2|--q quill --offset 10
search_quill_linux|--q quill --platform linux
search_none|--q no-such-package
package_quill|--package quill
package_quill_page2|--package quill --pkg-offset 10
package_bare|--package bare
package_missing|--package no-such-package'
# The port changes from run to run, and the dates are today's: name them, padded to the same width.
placeholder=$(printf '%-*s' "${#server}" http://registry)
printf '%s\n' "$cases" | while IFS='|' read -r name flags; do
  # shellcheck disable=SC2086 # flags are words
  "$ari" snapshot --width 100 --height 30 --frames 3 --net-allow "$server" \
    "$root/share/cypkg/main.ari" --server "$server" $flags >"$tmp/out" 2>"$tmp/err" || {
    echo "FAIL $name: ari exited $?"; cat "$tmp/err"; exit 1; }
  sed -e "s#$server#$placeholder#" -e 's/20[0-9][0-9]-[01][0-9]-[0-3][0-9]/yyyy-mm-dd/g' \
    "$tmp/out" >"$tmp/frame"
  expected=$here/integration/expected/$name.txt
  if [ $mode = update ]; then
    mkdir -p "$here/integration/expected"; cp "$tmp/frame" "$expected"; echo "updated $name"
  elif [ -s "$tmp/err" ]; then
    echo "FAIL $name: warnings"; cat "$tmp/err"; exit 1
  elif cmp -s "$tmp/frame" "$expected"; then
    echo "ok   $name"
  else
    echo "FAIL $name"; diff -u "$expected" "$tmp/frame" || true; exit 1
  fi
done
