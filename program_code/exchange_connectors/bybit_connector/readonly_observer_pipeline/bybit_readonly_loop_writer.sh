#!/usr/bin/env bash
set -euo pipefail

# XP-1: Use env var with auto-detection fallback / 环境变量优先，回退自动推导
_SRV="${OPENCLAW_SRV_ROOT:-$(cd "$(dirname "$0")/../../../../.." && pwd)}"

while true; do
  python3 "$_SRV/program_code/exchange_connectors/bybit_connector/scripts/bybit_readonly_status_writer.py" || true
  sleep 300
done
