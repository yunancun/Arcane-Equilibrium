#!/usr/bin/env bash
# OPS-1 shadow cutover gate: verify no csrf_shadow violations in the current log window.
set -euo pipefail

WINDOW_DAYS="${OPENCLAW_CSRF_SHADOW_WINDOW_DAYS:-7}"
DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
NOW_EPOCH="$(date +%s)"
CUTOFF_EPOCH="$((NOW_EPOCH - WINDOW_DAYS * 86400))"

mtime_epoch() {
    stat -c %Y "$1" 2>/dev/null || stat -f %m "$1"
}

shopt -s nullglob
logs=(
    "$DATA_DIR/api.log"
    "$DATA_DIR/logs"/*.log
    "$DATA_DIR/logs"/*.jsonl
)

scanned=0
violations=0
for log_file in "${logs[@]}"; do
    [ -f "$log_file" ] || continue
    mtime="$(mtime_epoch "$log_file")"
    [ "$mtime" -lt "$CUTOFF_EPOCH" ] && continue
    scanned=$((scanned + 1))
    count="$(grep -c 'csrf_shadow:' "$log_file" || true)"
    violations=$((violations + count))
done

if [ "$scanned" -eq 0 ]; then
    echo "verdict=INSUFFICIENT_SAMPLE window_days=$WINDOW_DAYS scanned_logs=0 data_dir=$DATA_DIR"
    exit 2
fi
if [ "$violations" -eq 0 ]; then
    echo "verdict=PASS window_days=$WINDOW_DAYS scanned_logs=$scanned csrf_shadow=0"
    exit 0
fi

echo "verdict=FAIL window_days=$WINDOW_DAYS scanned_logs=$scanned csrf_shadow=$violations"
exit 1
