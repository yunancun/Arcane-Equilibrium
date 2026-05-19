#!/usr/bin/env bash
# halt_audit_pg_writer_cron.sh — P0-ENGINE-HALTSESSION-STUCK-FIX Layer A Round 2
# MUST-FIX-3 Round 2（2026-05-19/20）：tail halt_audit.log JSONL →
# INSERT learning.governance_audit_log per spec §3.8 / §3.9。
#
# Suggested cron entry, installed manually by the operator:
#   * * * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw \
#       $HOME/BybitOpenClaw/srv/helper_scripts/cron/halt_audit_pg_writer_cron.sh
#
# 為什麼 cron（1min interval）而非 daemon：
#   - halt 事件頻率極低（理論最壞 < 數十次/天），1min latency 對 7d operator
#     query 影響可忽略
#   - 對齊 sibling cron pattern（outcome_backfiller_live_cron / wave9_collector）
#     更易監管、無常駐進程崩潰風險
#   - 失敗自動下次重試；cursor state file 保證冪等
#
# Source-only wrapper. 不自動 install；operator 確認 V098 已 land 後手動加 cron。
set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/halt_audit_pg_writer_cron.log"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/halt_audit_pg_writer_cron.lock.d"

mkdir -p "$LOG_DIR" "$LOCK_ROOT"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

# 讀 secret env file（與 sibling cron 對齊）
SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
ENV_FILE="$SECRETS_ROOT/environment_files/basic_system_services.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "[$(ts)] FATAL: env file missing: $ENV_FILE" | tee -a "$LOG" >&2
    exit 2
fi

PG_PASS=$(grep '^POSTGRES_PASSWORD=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_USER=$(grep '^POSTGRES_USER=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_DB=$(grep '^POSTGRES_DB=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_HOST=$(grep '^POSTGRES_HOST=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_PORT=$(grep '^POSTGRES_PORT=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_HOST="${PG_HOST:-127.0.0.1}"
PG_PORT="${PG_PORT:-5432}"

if [[ -z "$PG_PASS" || -z "$PG_USER" || -z "$PG_DB" ]]; then
    echo "[$(ts)] FATAL: PG creds incomplete in $ENV_FILE" | tee -a "$LOG" >&2
    exit 2
fi

export PG_HOST PG_PORT PG_DB PG_USER PG_PASSWORD="$PG_PASS"
export OPENCLAW_DATABASE_URL="postgresql://redacted@${PG_HOST}:${PG_PORT}/${PG_DB}"
export OPENCLAW_BASE_DIR="${OPENCLAW_BASE_DIR:-$BASE}"
export OPENCLAW_DATA_DIR="${OPENCLAW_DATA_DIR:-$DATA}"
export PYTHONPATH="${BASE}/program_code:${BASE}:${PYTHONPATH:-}"

# 鎖：避免 cron 過載（1min interval + 上輪未跑完）
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: halt_audit_pg_writer already running (lock held)" >> "$LOG"
    exit 0
fi
release_lock() {
    local rc=$?
    rmdir "$LOCK_DIR" 2>/dev/null || true
    return "$rc"
}
trap release_lock EXIT INT TERM

if [[ ! -f "${BASE}/helper_scripts/canary/halt_audit_pg_writer.py" ]]; then
    echo "[$(ts)] ERROR: halt_audit_pg_writer.py not found under BASE=${BASE}" >> "$LOG"
    exit 1
fi

cd "$BASE"

echo "[$(ts)] === halt_audit_pg_writer start ===" >> "$LOG"

if python3 helper_scripts/canary/halt_audit_pg_writer.py >> "$LOG" 2>&1; then
    echo "[$(ts)] === halt_audit_pg_writer end OK ===" >> "$LOG"
    exit 0
fi

rc=$?
echo "[$(ts)] === halt_audit_pg_writer end FAIL rc=${rc} ===" >> "$LOG"
exit "$rc"
