#!/bin/sh
# Stage cvcpkg's Python client (with PyYAML and click) in share/cypkg/python/site, for the
# Prefixes window in a checkout. A cvcpkg-cp312 package (not published yet) would put the client in
# the host's own site-packages instead.
#
#   tools/stage-python.sh [PYTHON]
#
# PYTHON is the CPython the scripting host embeds (default: python3.12 beside arix on PATH, or
# $CYPKG_ARI's). It runs pip, so it needs the network. The cvcpkg it stages is the release pinned
# below, checked against its sha256.
set -eu

CVCPKG_VERSION=2.5.15
CVCPKG_SHA256=7d3f0976845cbd12527a1fa50fe955d8b9141386714195ed5f7fa2dbc5c25c8d
CVCPKG_URL=https://github.com/cy-pca/cvcpkg/archive/refs/tags/cvcpkg-v$CVCPKG_VERSION.tar.gz

here=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
site=$here/share/cypkg/python/site

py=${1:-}
if [ -z "$py" ]; then
  # Not the host itself: arix's sys.executable is arix, which pip's build subprocesses can't run
  # as python. The python3.12 beside it is the same interpreter and standard library.
  ari=${CYPKG_ARI:-$(command -v arix || true)}
  [ -n "$ari" ] || { echo "stage-python: no arix on PATH; name the python: $0 PYTHON" >&2; exit 2; }
  py=$(dirname -- "$ari")/python3.12
fi
[ -x "$py" ] || { echo "stage-python: $py isn't an executable python" >&2; exit 2; }

tmp=$(mktemp -d "${TMPDIR:-/tmp}/cypkg-stage.XXXXXX")
trap 'rm -rf "$tmp"' EXIT INT TERM
curl -sSL --retry 3 -o "$tmp/cvcpkg.tar.gz" "$CVCPKG_URL"
actual=$(sha256sum "$tmp/cvcpkg.tar.gz" | awk '{print $1}')
[ "$actual" = "$CVCPKG_SHA256" ] || {
  echo "stage-python: checksum mismatch for $CVCPKG_URL (got $actual)" >&2; exit 1; }

# Built and installed in the temporary directory, then moved: pip writes many small files, and
# that is slow on some mounts (WSL's /mnt).
"$py" -m pip install -q --disable-pip-version-check --target "$tmp/site" "$tmp/cvcpkg.tar.gz"
rm -rf "$site"
mkdir -p "$(dirname -- "$site")"
cp -R "$tmp/site" "$site"
echo "stage-python: cvcpkg $CVCPKG_VERSION, PyYAML and click -> $site"
