#!/bin/bash
# restart_all.sh — 重啟 Rust 引擎 + API server
# Usage: bash helper_scripts/restart_all.sh [--engine-only|--api-only]

set -e
cd "$(dirname "$0")/.."
WORKERS="${OPENCLAW_API_WORKERS:-4}"

restart_engine() {
    echo ">>> Stopping Rust engine..."
    pkill -f "openclaw-engine" 2>/dev/null || true
    sleep 2
    echo ">>> Starting Rust engine..."
    OPENCLAW_DATA_DIR=/tmp/openclaw OPENCLAW_CANARY_MODE=1 \
        nohup rust/target/release/openclaw-engine > /tmp/openclaw/engine.log 2>&1 &
    echo "    PID: $!"
}

restart_api() {
    echo ">>> Stopping API server..."
    lsof -ti :8000 | xargs kill -9 2>/dev/null || true
    sleep 2
    echo ">>> Starting API server ($WORKERS workers)..."
    cd program_code/exchange_connectors/bybit_connector/control_api_v1
    .venv/bin/python3 .venv/bin/uvicorn app.main:app \
        --host 0.0.0.0 --port 8000 --workers "$WORKERS" &
    cd - > /dev/null
}

wait_and_verify() {
    echo ">>> Waiting 10s for startup..."
    sleep 10
    echo "=== Engine ==="
    python3 helper_scripts/canary/engine_watchdog.py \
        --data-dir /tmp/openclaw --stale-threshold 45 --grace-period 120 --status 2>&1 || true
    echo "=== Ticks ==="
    python3 -c "import json;s=json.load(open('/tmp/openclaw/pipeline_snapshot.json'));print('ticks:', s['stats']['total_ticks'], 'fills:', s['stats']['total_fills'], 'paused:', s.get('paper_paused'))" 2>&1 || true
}

case "${1:-all}" in
    --engine-only) restart_engine; wait_and_verify ;;
    --api-only)    restart_api; sleep 3; echo "API server restarted" ;;
    *)             restart_engine; restart_api; wait_and_verify ;;
esac
