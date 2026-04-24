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
# ============================================================================
set -e
SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
BASE_DIR="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
PG_PASS=$(grep '^POSTGRES_PASSWORD=' "$SECRETS_ROOT/environment_files/basic_system_services.env" 2>/dev/null | cut -d= -f2-)
export OPENCLAW_DATABASE_URL="postgresql://trading_admin:${PG_PASS}@127.0.0.1:5432/trading_ai"
VENV="$BASE_DIR/program_code/exchange_connectors/bybit_connector/control_api_v1/.venv/bin/activate"
LOG_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/passive_wait_healthcheck_cron.log"
{
  echo
  echo "==== $(date '+%Y-%m-%d %H:%M:%S %Z') ===="
  source "$VENV" 2>/dev/null
  cd "$BASE_DIR"
  python3 helper_scripts/db/passive_wait_healthcheck.py
  EXIT=$?
  echo "---- exit=$EXIT ----"
} >> "$LOG_FILE" 2>&1
