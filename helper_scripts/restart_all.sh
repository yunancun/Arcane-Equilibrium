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
    # Load PG password from secrets (cross-platform: no hardcoded credentials)
    local pg_pass
    pg_pass=$(grep POSTGRES_PASSWORD "$HOME/BybitOpenClaw/secrets/environment_files/basic_system_services.env" 2>/dev/null | cut -d= -f2-)
    # Load IPC HMAC secret for Live pipeline authentication
    # 載入 IPC HMAC 密鑰（Live 管線 HMAC 認證必需）
    local ipc_secret
    ipc_secret=$(cat "$HOME/BybitOpenClaw/secrets/environment_files/ipc_secret.txt" 2>/dev/null || echo "")
    OPENCLAW_DATA_DIR=/tmp/openclaw OPENCLAW_CANARY_MODE=1 \
        OPENCLAW_DATABASE_URL="postgresql://trading_admin:${pg_pass}@127.0.0.1:5432/trading_ai" \
        OPENCLAW_IPC_SECRET="${ipc_secret}" \
        nohup rust/target/release/openclaw-engine > /tmp/openclaw/engine.log 2>&1 &
    echo "    PID: $!"
}

restart_api() {
    echo ">>> Stopping API server..."
    lsof -ti :8000 | xargs kill -9 2>/dev/null || true
    sleep 2
    echo ">>> Starting API server ($WORKERS workers)..."
    # Pass DB URL to API server for metrics DB fallback (fills query).
    # 傳遞 DB URL 給 API 以支持指標 DB 降級（成交查詢）。
    local pg_pass
    pg_pass=$(grep POSTGRES_PASSWORD "$HOME/BybitOpenClaw/secrets/environment_files/basic_system_services.env" 2>/dev/null | cut -d= -f2-)
    cd program_code/exchange_connectors/bybit_connector/control_api_v1
    # Load IPC HMAC secret for API-side HMAC verification
    # 載入 IPC HMAC 密鑰（API 端 HMAC 驗證）
    local ipc_secret
    ipc_secret=$(cat "$HOME/BybitOpenClaw/secrets/environment_files/ipc_secret.txt" 2>/dev/null || echo "")
    OPENCLAW_DATABASE_URL="postgresql://trading_admin:${pg_pass}@127.0.0.1:5432/trading_ai" \
        OPENCLAW_IPC_SECRET="${ipc_secret}" \
        .venv/bin/python3 .venv/bin/uvicorn app.main:app \
        --host 0.0.0.0 --port 8000 --workers "$WORKERS" &
    cd - > /dev/null
}

ensure_docker_network() {
    # Ensure Grafana can reach PG (different Docker networks by default)
    # 確保 Grafana 能訪問 PG（默認在不同 Docker 網絡）
    if docker inspect trading_postgres >/dev/null 2>&1 && docker inspect trading_grafana >/dev/null 2>&1; then
        docker network connect basic_system_services_default trading_postgres 2>/dev/null || true
    fi
}

wait_and_verify() {
    ensure_docker_network
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
