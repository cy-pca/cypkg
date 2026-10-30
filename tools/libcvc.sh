#!/bin/sh
# Check out libcvc at REF with open PRs merged on top, as cypkg's CI builds ari from it.
#
#   tools/libcvc.sh DIR REF [PR...]
#
# It fetches recent history only (enough for the PRs' merge bases; a blobless clone can't fetch
# the objects a PR's merge needs) and merges each PR in order. A PR that has merged is skipped:
# libcvc squash-merges, so ask the API (with gh) rather than trusting ancestry. A conflict that
# tools/libcvc-resolve.py recognises is resolved; any other fails. The last line printed is
# tree=<the merged source tree's hash>, which CI caches builds by.
set -eu
[ $# -ge 2 ] || { echo "usage: $0 DIR REF [PR...]" >&2; exit 2; }
dir=$1 ref=$2
shift 2
resolve=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/libcvc-resolve.py
since="60 days ago"

rm -rf "$dir"
git init --quiet "$dir"
cd "$dir"
git remote add origin https://github.com/transfix/libcvc.git
git fetch --quiet --shallow-since="$since" origin "$ref"
git checkout --quiet FETCH_HEAD
git config user.name "cypkg CI"
git config user.email "cypkg-ci@users.noreply.github.com"
for pr in "$@"; do
  if command -v gh >/dev/null 2>&1 \
     && [ "$(gh api "repos/transfix/libcvc/pulls/$pr" --jq .merged 2>/dev/null)" = true ]; then
    echo "transfix/libcvc#$pr has merged; not merging it again"
    continue
  fi
  git fetch --quiet --shallow-since="$since" origin "pull/$pr/head:pr-$pr"
  if git merge-base --is-ancestor "pr-$pr" HEAD; then
    echo "transfix/libcvc#$pr is already in"
  elif git merge --quiet --no-edit "pr-$pr" >/dev/null 2>&1; then
    echo "merged transfix/libcvc#$pr ($(git rev-parse --short "pr-$pr"))"
  elif python3 -I "$resolve" && [ -z "$(git diff --name-only --diff-filter=U)" ]; then
    git commit --quiet --no-edit
    echo "merged transfix/libcvc#$pr ($(git rev-parse --short "pr-$pr")), resolving a known conflict"
  else
    git diff --name-only --diff-filter=U
    echo "::error::transfix/libcvc#$pr doesn't merge onto $ref and the PRs before it" >&2
    exit 1
  fi
done
echo "tree=$(git rev-parse 'HEAD^{tree}')"
