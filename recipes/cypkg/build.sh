#!/usr/bin/env bash
# cypkg: install the documents and the launchers. Nothing to compile.
set -euo pipefail

: "${CVC_SOURCE_DIR:?CVC_SOURCE_DIR must be set}"   # the cypkg repo root (vendored)
: "${CVC_INSTALL_DIR:?CVC_INSTALL_DIR must be set}"

SHARE="${CVC_INSTALL_DIR}/share/cypkg"
DOC="${CVC_INSTALL_DIR}/share/doc/cypkg"
install -d "${CVC_INSTALL_DIR}/bin" "${SHARE}" "${DOC}"
install -m 0755 "${CVC_SOURCE_DIR}/bin/cypkg" "${CVC_INSTALL_DIR}/bin/cypkg"
install -m 0644 "${CVC_SOURCE_DIR}/bin/cypkg.cmd" "${CVC_INSTALL_DIR}/bin/cypkg.cmd"
for f in "${CVC_SOURCE_DIR}"/share/cypkg/*.ari; do
  install -m 0644 "$f" "${SHARE}/"
done
install -m 0644 "${CVC_SOURCE_DIR}/LICENSE" "${CVC_SOURCE_DIR}/README.md" "${DOC}/"
echo "cvcpkg: installed cypkg's documents -> ${SHARE}, launchers -> ${CVC_INSTALL_DIR}/bin"
