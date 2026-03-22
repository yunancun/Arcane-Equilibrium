#!/usr/bin/env bash
set -euo pipefail

while true; do
  python3 /home/ncyu/srv/program_code/exchange_connectors/bybit_connector/scripts/bybit_readonly_status_writer.py || true
  sleep 300
done
