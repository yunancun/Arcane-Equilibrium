#!/usr/bin/env bash
set -euo pipefail
REAL="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../io_and_persistence && pwd)/bybit_private_ws_listener_ctl.sh"
exec bash "$REAL" "$@"
