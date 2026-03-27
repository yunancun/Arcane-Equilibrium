#!/usr/bin/env bash
# prune_dated_files.sh — Remove dated JSON files older than N days
# 清理超过 N 天的 dated JSON 文件
# Usage: bash prune_dated_files.sh [days=7]
DAYS=${1:-7}
BASE="/home/ncyu/BybitOpenClaw/srv"
DIRS=(
    "docker_projects/trading_services/runtime/bybit/thought_gate"
    "docker_projects/trading_services/runtime/bybit/readonly_observer"
    "docker_projects/trading_services/runtime/bybit/decision_lease"
    "docker_projects/trading_services/runtime/bybit/business_events"
    "docker_projects/trading_services/runtime/bybit/local_judgment"
    "docker_projects/trading_services/runtime/bybit/trigger_model"
    "docker_projects/trading_services/verdicts/bybit"
    "docker_projects/trading_services/decision_packets/bybit"
)
TOTAL=0
for DIR in "${DIRS[@]}"; do
    FULL="$BASE/$DIR"
    if [[ -d "$FULL" ]]; then
        COUNT=$(find "$FULL" -name "*_[0-9]*.json" -mtime +$DAYS -type f | wc -l)
        if [[ $COUNT -gt 0 ]]; then
            find "$FULL" -name "*_[0-9]*.json" -mtime +$DAYS -type f -delete
            echo "Pruned $COUNT files from $DIR"
            TOTAL=$((TOTAL + COUNT))
        fi
    fi
done
echo "Total pruned: $TOTAL files older than $DAYS days"
