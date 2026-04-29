#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# OpenClaw Daily Paper Trading Report / 每日纸盘交易报告
# Batch 12: Cron UTC 0:00 → Collect metrics → Format → Telegram
#
# MODULE_NOTE (中文):
#   每日自动采集 Paper Trading 指标，格式化后推送到 Telegram。
#   Cron 触发：0 0 * * * /path/to/cron_daily_report.sh
#   环境变量：TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, OPENCLAW_API_BASE
#
# MODULE_NOTE (English):
#   Daily automated Paper Trading metrics collection and Telegram push.
#   Cron trigger: 0 0 * * * /path/to/cron_daily_report.sh
#   Env vars: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, OPENCLAW_API_BASE
#
# Installation / 安装:
#   chmod +x cron_daily_report.sh
#   crontab -e
#   0 0 * * * /path/to/helper_scripts/cron_daily_report.sh >> /var/log/openclaw_daily_report.log 2>&1
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

# ─── Configuration / 配置 ───────────────────────────────────────
API_BASE="${OPENCLAW_API_BASE:-http://127.0.0.1:8000/api/v1}"
BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
CHAT_ID="${TELEGRAM_CHAT_ID:-}"
DATE_STR=$(date -u +"%Y-%m-%d")
TIMESTAMP=$(date -u +"%Y-%m-%d %H:%M:%S UTC")

# SW-006 (Batch E): overlap lock for cron wrapper (portable mkdir lock).
# SW-006（Batch E）：cron 包裝器重疊執行鎖（可攜式 mkdir 鎖）。
LOCK_ROOT="${OPENCLAW_DATA_DIR:-/tmp/openclaw}/locks"
LOCK_DIR="$LOCK_ROOT/cron_daily_report.lock.d"
mkdir -p "$LOCK_ROOT"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[${TIMESTAMP}] SKIP: cron_daily_report already running (lock held)."
    exit 0
fi
release_lock() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
TELEGRAM_CONFIG=""
TELEGRAM_PAYLOAD=""
cleanup() {
    release_lock
    [[ -n "$TELEGRAM_CONFIG" ]] && rm -f "$TELEGRAM_CONFIG"
    [[ -n "$TELEGRAM_PAYLOAD" ]] && rm -f "$TELEGRAM_PAYLOAD"
}
trap cleanup EXIT INT TERM

# ─── Validate env vars / 验证环境变量 ───────────────────────────
if [[ -z "$BOT_TOKEN" || -z "$CHAT_ID" ]]; then
    echo "[${TIMESTAMP}] WARN: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set. Skipping report."
    echo "[${TIMESTAMP}] 警告：TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID 未设置，跳过报告推送。"
    exit 0
fi

TELEGRAM_CONFIG=$(mktemp "${TMPDIR:-/tmp}/openclaw-telegram-curl.XXXXXX")
TELEGRAM_PAYLOAD=$(mktemp "${TMPDIR:-/tmp}/openclaw-telegram-payload.XXXXXX")
chmod 600 "$TELEGRAM_CONFIG" "$TELEGRAM_PAYLOAD"
printf 'url = "https://api.telegram.org/bot%s/sendMessage"\n' "$BOT_TOKEN" > "$TELEGRAM_CONFIG"
printf 'request = "POST"\n' >> "$TELEGRAM_CONFIG"
printf 'header = "Content-Type: application/json"\n' >> "$TELEGRAM_CONFIG"
unset BOT_TOKEN

# ─── Helper function: Fetch from API with timeout ───────────────
fetch_api() {
    local endpoint="$1"
    local url="${API_BASE}${endpoint}"

    if ! response=$(curl -s -m 10 "$url" 2>&1); then
        echo "error" "curl failed"
        return 1
    fi

    echo "$response"
    return 0
}

# ─── Helper function: Safe jq extract ──────────────────────────
safe_jq() {
    local json="$1"
    local path="$2"
    local default="${3:-N/A}"

    if ! result=$(echo "$json" | jq -r "$path" 2>/dev/null); then
        echo "$default"
    else
        [[ "$result" == "null" ]] && echo "$default" || echo "$result"
    fi
}

# ─── Main logic / 主逻辑 ──────────────────────────────────────────

echo "[${TIMESTAMP}] Starting daily report collection..."
echo "[${TIMESTAMP}] 开始采集每日报告..."

# Fetch paper trading summary
echo "[${TIMESTAMP}] Fetching paper trading summary from ${API_BASE}/paper/session/summary"
paper_data=$(fetch_api "/paper/session/summary" || echo '{}')

if [[ "$paper_data" == "error"* ]] || [[ -z "$paper_data" ]]; then
    echo "[${TIMESTAMP}] ERROR: Unable to fetch paper trading summary. API unreachable or timeout."
    echo "[${TIMESTAMP}] 错误：无法采集纸盘交易摘要，API 不可达或超时。"
    exit 0
fi

# Fetch governance status
echo "[${TIMESTAMP}] Fetching governance status from ${API_BASE}/governance/status"
gov_data=$(fetch_api "/governance/status" || echo '{}')

# ─── Parse metrics using jq ───────────────────────────────────────
win_count=$(safe_jq "$paper_data" '.metrics.win_count // 0')
loss_count=$(safe_jq "$paper_data" '.metrics.loss_count // 0')
total_pnl=$(safe_jq "$paper_data" '.metrics.total_pnl // "0.00"')
max_drawdown=$(safe_jq "$paper_data" '.metrics.max_drawdown // "0.00"')
sharpe_ratio=$(safe_jq "$paper_data" '.metrics.sharpe_ratio // "N/A"')
active_positions=$(safe_jq "$paper_data" '.metrics.active_positions_count // 0')

# Calculate win rate
if (( $(echo "$win_count + $loss_count > 0" | bc -l) )); then
    total_trades=$(( win_count + loss_count ))
    win_rate=$(echo "scale=2; $win_count * 100 / $total_trades" | bc)
else
    win_rate="0.00"
    total_trades=0
fi

# ─── Format Telegram message ──────────────────────────────────────
MSG="📊 *OpenClaw Daily Report* - ${DATE_STR}

*纸盘交易摘要 / Paper Trading Summary:*
• Trades Executed / 已执行交易: ${total_trades}
• Wins / 胜场: ${win_count}
• Losses / 负场: ${loss_count}
• Win Rate / 胜率: ${win_rate}%
• Total PnL / 总收益: \$${total_pnl}
• Max Drawdown / 最大回撤: ${max_drawdown}%
• Sharpe Ratio / 夏普比率: ${sharpe_ratio}
• Active Positions / 活跃持仓: ${active_positions}

*Governance Status / 治理状态:*
$(safe_jq "$gov_data" '.status' 'N/A')

Report generated at ${TIMESTAMP}"

# ─── Send via Telegram Bot API ────────────────────────────────────
jq -n \
    --arg chat_id "$CHAT_ID" \
    --arg text "$MSG" \
    '{chat_id: $chat_id, text: $text, parse_mode: "Markdown"}' > "$TELEGRAM_PAYLOAD"

echo "[${TIMESTAMP}] Sending Telegram message..."
if telegram_response=$(curl -s -m 10 --config "$TELEGRAM_CONFIG" --data-binary "@$TELEGRAM_PAYLOAD" 2>&1); then

    if echo "$telegram_response" | jq -e '.ok' &>/dev/null; then
        echo "[${TIMESTAMP}] SUCCESS: Daily report sent to Telegram."
        echo "[${TIMESTAMP}] 成功：每日报告已推送到 Telegram。"
        exit 0
    else
        error_msg=$(echo "$telegram_response" | jq -r '.description // "unknown error"')
        echo "[${TIMESTAMP}] WARN: Telegram send failed: ${error_msg}"
        echo "[${TIMESTAMP}] 警告：Telegram 推送失败：${error_msg}"
        exit 0
    fi
else
    echo "[${TIMESTAMP}] WARN: Telegram API call failed or timeout."
    echo "[${TIMESTAMP}] 警告：Telegram API 调用失败或超时。"
    exit 0
fi
