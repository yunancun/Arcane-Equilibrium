#!/usr/bin/env bash
# cron_observer_cycle.sh — Run full observer cycle + auto-bridge to runtime snapshot
# 运行完整观察者循环 + 自动桥接到运行时快照
#
# Add to crontab: */5 * * * * bash /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron_observer_cycle.sh >> /home/ncyu/BybitOpenClaw/srv/log_files/observer_cron.log 2>&1
#
set -euo pipefail

REPO="/home/ncyu/BybitOpenClaw/srv"
VENV="$REPO/program_code/exchange_connectors/bybit_connector/control_api_v1/.venv/bin/python3"
OBSERVER="$REPO/program_code/exchange_connectors/bybit_connector/readonly_observer_pipeline/bybit_full_readonly_observer_cycle.py"
BRIDGE="$REPO/program_code/exchange_connectors/bybit_connector/control_api_v1/app/auto_bridge_observer_to_runtime_snapshot.py"

TS=$(date '+%Y-%m-%d %H:%M:%S')
echo "[$TS] Starting observer cycle..."

# Run observer cycle (may fail if Bybit API is down — that's OK, just log)
if $VENV "$OBSERVER" 2>&1; then
    echo "[$TS] Observer cycle complete"
else
    echo "[$TS] Observer cycle failed (non-fatal)"
fi

# Run auto-bridge if the script exists
if [[ -f "$BRIDGE" ]]; then
    if $VENV "$BRIDGE" 2>&1; then
        echo "[$TS] Auto-bridge complete"
    else
        echo "[$TS] Auto-bridge failed (non-fatal)"
    fi
fi

echo "[$TS] Cron cycle done"
