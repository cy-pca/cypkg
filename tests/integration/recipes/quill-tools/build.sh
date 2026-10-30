#!/usr/bin/env bash
# quill-tools: install its one script.
set -euo pipefail
: "${CVC_SOURCE_DIR:?}" "${CVC_INSTALL_DIR:?}"
install -d "${CVC_INSTALL_DIR}/bin"
install -m 0755 "${CVC_SOURCE_DIR}/quill-cat" "${CVC_INSTALL_DIR}/bin/"
