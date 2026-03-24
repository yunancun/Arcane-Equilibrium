#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../../../../ && pwd)"
REAL="$REPO/helper_scripts/maintenance_scripts/bybit_connector/run_h2_query_budget_full_closure.sh"

if [ ! -f "$REAL" ]; then
  echo "Canonical script not found: $REAL" >&2
  exit 1
fi

exec bash "$REAL" "$@"
