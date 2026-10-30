#!/usr/bin/env bash
# quill: install its header and its note.
set -euo pipefail
: "${CVC_SOURCE_DIR:?}" "${CVC_INSTALL_DIR:?}"
install -d "${CVC_INSTALL_DIR}/include" "${CVC_INSTALL_DIR}/share/doc/quill"
install -m 0644 "${CVC_SOURCE_DIR}/quill.h" "${CVC_INSTALL_DIR}/include/"
install -m 0644 "${CVC_SOURCE_DIR}/README" "${CVC_INSTALL_DIR}/share/doc/quill/"
