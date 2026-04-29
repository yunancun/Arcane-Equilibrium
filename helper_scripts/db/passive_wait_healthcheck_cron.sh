#!/usr/bin/env bash
# ============================================================================
# MODULE_NOTE
# ============================================================================
# 6h cron wrapper for passive_wait_healthcheck.py (CLAUDE.md §七 強制).
# 6h cron 包裝器，跑被動等待 healthcheck（CLAUDE.md §七 強制）。
#
# Sources POSTGRES_PASSWORD from secrets env file → builds OPENCLAW_DATABASE_URL,
# activates control_api_v1 venv (psycopg2 needed), then runs the healthcheck.
# Logs append to $OPENCLAW_DATA_DIR/passive_wait_healthcheck_cron.log (default
# /tmp/openclaw/passive_wait_healthcheck_cron.log on Linux).
#
# 從 secrets env 檔抓 POSTGRES_PASSWORD → 構造 OPENCLAW_DATABASE_URL，啟用
# control_api_v1 venv（需 psycopg2），再跑 healthcheck。日誌追加到
# $OPENCLAW_DATA_DIR/passive_wait_healthcheck_cron.log。
#
# Crontab entry / Crontab 條目：
#   0 */6 * * * /home/ncyu/BybitOpenClaw/srv/helper_scripts/db/passive_wait_healthcheck_cron.sh
#
# Setup history / 設置歷史：Wave 1 G6-02 closeout, 2026-04-24.
# F7 self-check (2026-04-29): verify this exact cron run printed [22]-[29]
# so stale BASE_DIR / wrong worktree drift fails loudly instead of silently.
# ============================================================================
set -e
SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
BASE_DIR="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
LOCK_ROOT="${OPENCLAW_DATA_DIR:-/tmp/openclaw}/locks"
LOCK_DIR="$LOCK_ROOT/passive_wait_healthcheck_cron.lock.d"
RUN_LOG=""
mkdir -p "$LOCK_ROOT"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "[SKIP] passive_wait_healthcheck cron already running (lock held)" >&2
  exit 0
fi
release_lock() {
  if [ -n "$RUN_LOG" ]; then
    rm -f "$RUN_LOG" 2>/dev/null || true
  fi
  rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap release_lock EXIT INT TERM

PG_PASS=$(grep '^POSTGRES_PASSWORD=' "$SECRETS_ROOT/environment_files/basic_system_services.env" 2>/dev/null | cut -d= -f2-)
export OPENCLAW_DATABASE_URL="postgresql://trading_admin:${PG_PASS}@127.0.0.1:5432/trading_ai"
VENV="$BASE_DIR/program_code/exchange_connectors/bybit_connector/control_api_v1/.venv/bin/activate"
LOG_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/passive_wait_healthcheck_cron.log"
RUN_LOG="$(mktemp "$LOG_DIR/passive_wait_healthcheck_cron.XXXXXX")"
EXIT=0
{
  echo
  echo "==== $(date '+%Y-%m-%d %H:%M:%S %Z') ===="
  if [ -f "$VENV" ]; then
    source "$VENV" 2>/dev/null || echo "[WARN] venv activation failed: $VENV"
  else
    echo "[WARN] venv not found: $VENV"
  fi
  if cd "$BASE_DIR"; then
    set +e
    python3 helper_scripts/db/passive_wait_healthcheck.py
    EXIT=$?
    set -e
  else
    echo "[FAIL] cannot cd to BASE_DIR=$BASE_DIR"
    EXIT=1
  fi
  echo "---- exit=$EXIT ----"
} > "$RUN_LOG" 2>&1

cat "$RUN_LOG" >> "$LOG_FILE"

F7_MISSING=""
for CHECK_ID in 22 23 24 25 26 27 28 29; do
  if ! grep -q "\\[$CHECK_ID\\]" "$RUN_LOG"; then
    F7_MISSING="$F7_MISSING [$CHECK_ID]"
  fi
done
if [ -n "$F7_MISSING" ]; then
  echo "[FAIL] F7 cron self-check missing check ids:$F7_MISSING (base_dir=$BASE_DIR)" >> "$LOG_FILE"
  EXIT=1
else
  echo "[OK] F7 cron self-check saw [22]-[29] in current run (base_dir=$BASE_DIR)" >> "$LOG_FILE"
fi

exit "$EXIT"
