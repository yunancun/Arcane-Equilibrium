#!/usr/bin/env bash
# start_paper_trading.sh — Auto-start paper trading after API server is ready
# 自动启动纸上交易（API 服务器就绪后）
#
# Usage: bash start_paper_trading.sh
# Can be called from systemd ExecStartPost or cron @reboot
#
# Requires: OPENCLAW_API_TOKEN environment variable or .secrets/api_token file

set -euo pipefail

# ── Configuration / 配置 ──
API_BASE="http://127.0.0.1:8000"
MAX_WAIT_SEC=60
POLL_INTERVAL=2

# ── Resolve API token / 解析 API Token ──
if [[ -z "${OPENCLAW_API_TOKEN:-}" ]]; then
    TOKEN_FILE="$HOME/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/.secrets/api_token"
    if [[ -f "$TOKEN_FILE" ]]; then
        OPENCLAW_API_TOKEN=$(cat "$TOKEN_FILE")
    else
        echo "ERROR: No API token found. Set OPENCLAW_API_TOKEN or create $TOKEN_FILE"
        exit 1
    fi
fi

AUTH="Authorization: Bearer $OPENCLAW_API_TOKEN"

# ── Helper: API call / API 调用辅助 ──
api_get() {
    curl -s -H "$AUTH" "${API_BASE}$1" 2>/dev/null
}

api_post() {
    curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" "${API_BASE}$1" ${2:+-d "$2"} 2>/dev/null
}

# ── Step 0: Wait for API server / 等待 API 服务器就绪 ──
echo "[0/5] Waiting for API server at $API_BASE..."
elapsed=0
while ! curl -s -o /dev/null -w "%{http_code}" "${API_BASE}/api/v1/system/health" 2>/dev/null | grep -q "200\|401"; do
    sleep $POLL_INTERVAL
    elapsed=$((elapsed + POLL_INTERVAL))
    if [[ $elapsed -ge $MAX_WAIT_SEC ]]; then
        echo "ERROR: API server not ready after ${MAX_WAIT_SEC}s"
        exit 1
    fi
done
echo "  API server ready (${elapsed}s)"

# ── Step 1: Check/Start paper session / 检查/启动 paper session ──
echo "[1/5] Checking paper session..."
SESSION_STATUS=$(api_get "/api/v1/paper/session/status" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('data', {}).get('session_state', 'none'))
except: print('none')
" 2>/dev/null)

if [[ "$SESSION_STATUS" != "active" ]]; then
    echo "  Starting paper session (initial_balance=100000, matching Bybit Demo)..."
    api_post "/api/v1/paper/session/start" '{"initial_balance": 100000}'
    sleep 1
else
    echo "  Paper session already active"
fi

# ── Step 2: Start market feed / 启动行情流 ──
echo "[2/5] Starting market data feed..."
FEED_STATUS=$(api_get "/api/v1/paper/market-feed/status" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('data', {}).get('dispatcher_running', False))
except: print('False')
" 2>/dev/null)

if [[ "$FEED_STATUS" != "True" ]]; then
    api_post "/api/v1/paper/market-feed/start" '{"symbols": ["BTCUSDT", "ETHUSDT"]}'
    echo "  Market feed started"
    sleep 3
else
    echo "  Market feed already running"
fi

# ── Step 3: Activate strategies / 激活策略 ──
echo "[3/5] Activating strategies..."
for STRATEGY in "Grid_Trading" "MA_Crossover" "BB_Reversion" "FundingRate_Arb" "BB_Breakout"; do
    RESULT=$(api_post "/api/v1/strategy/${STRATEGY}/activate" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('data', {}).get('action', 'failed'))
except: print('failed')
" 2>/dev/null)
    echo "  ${STRATEGY}: ${RESULT}"
done

# ── Step 4: Trigger kline bootstrap / 触发 K线历史引导 ──
echo "[4/5] Note: Kline bootstrap runs automatically when pipeline bridge activates"
echo "  Indicators will be available after sufficient klines accumulate"

# ── Step 5: Verify / 验证 ──
echo "[5/5] Verifying system status..."
echo "  Paper session: $(api_get '/api/v1/paper/session/status' | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('data', {}).get('session_state', 'unknown'))
except: print('unknown')
" 2>/dev/null)"
echo "  Market feed: $(api_get '/api/v1/paper/market-feed/status' | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print('running' if d.get('data', {}).get('dispatcher_running') else 'stopped')
except: print('unknown')
" 2>/dev/null)"
echo "  Strategies: $(api_get '/api/v1/strategy/list' | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    strategies = d.get('data', {}).get('strategies', [])
    active = [s['strategy'] for s in strategies if s.get('state') == 'active']
    print(', '.join(active) if active else 'none active')
except: print('unknown')
" 2>/dev/null)"

echo ""
echo "Paper trading startup complete / 纸上交易启动完成"
