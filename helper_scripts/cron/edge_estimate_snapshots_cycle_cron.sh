#!/usr/bin/env bash
# edge_estimate_snapshots_cycle_cron.sh — recurring V059 snapshot wrapper
#
# Suggested cron entry, installed manually by the operator:
#   12 * * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw \
#       $HOME/BybitOpenClaw/srv/helper_scripts/cron/edge_estimate_snapshots_cycle_cron.sh
#
# This wrapper writes only learning.edge_estimate_snapshots from existing
# settings/edge_estimates*.json files. It skips Bybit instruments-info and
# strategy freeze-log work from the one-shot REF-21 helper.

set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/edge_estimate_snapshots_cycle_cron.log"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/edge_estimate_snapshots_cycle_cron.lock.d"

mkdir -p "$LOG_DIR" "$LOCK_ROOT"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

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

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: edge snapshot cycle already running (lock held)" >> "$LOG"
    exit 0
fi
release_lock() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap release_lock EXIT INT TERM

if [[ ! -f "${BASE}/helper_scripts/db/ref21_backfill_v058_v059.py" ]]; then
    echo "[$(ts)] ERROR: ref21_backfill_v058_v059.py not found under BASE=${BASE}" >> "$LOG"
    exit 1
fi

cd "$BASE"

echo "[$(ts)] === edge_estimate_snapshots cycle start (BASE=$BASE) ===" >> "$LOG"

if python3 helper_scripts/db/ref21_backfill_v058_v059.py \
        --skip-instruments \
        --skip-freeze-log \
        --actor edge_estimate_snapshots_cycle \
        --apply >> "$LOG" 2>&1; then
    echo "[$(ts)] === edge_estimate_snapshots cycle end OK ===" >> "$LOG"
    exit 0
fi

rc=$?
echo "[$(ts)] === edge_estimate_snapshots cycle end FAIL rc=${rc} ===" >> "$LOG"
exit "$rc"
