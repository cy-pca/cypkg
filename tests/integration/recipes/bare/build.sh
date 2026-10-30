#!/usr/bin/env bash
# bare: install one file.
set -euo pipefail
: "${CVC_SOURCE_DIR:?}" "${CVC_INSTALL_DIR:?}"
install -d "${CVC_INSTALL_DIR}/share/bare"
printf 'bare\n' >"${CVC_INSTALL_DIR}/share/bare/NOTE"
