#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../../../../ && pwd)"
REAL="$REPO/helper_scripts/maintenance_scripts/bybit_connector/repair_h2_h4_then_h5_truth.sh"

if [ ! -f "$REAL" ]; then
  echo "Canonical script not found: $REAL" >&2
  exit 1
fi

exec bash "$REAL" "$@"
