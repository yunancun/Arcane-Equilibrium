#!/usr/bin/env bash
# outcome_backfiller_live_cron.sh - V074 live-lane decision_outcomes wrapper
#
# Suggested cron entry, installed manually by the operator:
#   42 2 * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw \
#       $HOME/BybitOpenClaw/srv/helper_scripts/cron/outcome_backfiller_live_cron.sh
#
# Source-only wrapper. It is not installed or run by this migration/task.

set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/outcome_backfiller_live_cron.log"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/outcome_backfiller_live_cron.lock.d"

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
export OPENCLAW_DATABASE_URL="postgresql://${PG_USER}:${PG_PASS}@${PG_HOST}:${PG_PORT}/${PG_DB}"
export PYTHONPATH="${BASE}/program_code:${BASE}:${PYTHONPATH:-}"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: outcome backfiller live cron already running (lock held)" >> "$LOG"
    exit 0
fi
release_lock() {
    local rc=$?
    rmdir "$LOCK_DIR" 2>/dev/null || true
    return "$rc"
}
trap release_lock EXIT INT TERM

if [[ ! -f "${BASE}/helper_scripts/db/outcome_backfiller_live.py" ]]; then
    echo "[$(ts)] ERROR: outcome_backfiller_live.py not found under BASE=${BASE}" >> "$LOG"
    exit 1
fi

BATCH_SIZE="${OPENCLAW_OUTCOME_BACKFILL_BATCH_SIZE:-2000}"
ENGINE_MODES="${OPENCLAW_OUTCOME_BACKFILL_ENGINE_MODES:-live,live_demo}"
DRY_RUN_ARGS=()
case "${OPENCLAW_OUTCOME_BACKFILL_DRY_RUN:-0}" in
    1|true|TRUE|yes|YES|on|ON)
        DRY_RUN_ARGS=(--dry-run)
        ;;
esac

cd "$BASE"

echo "[$(ts)] === outcome_backfiller_live start (modes=$ENGINE_MODES batch=$BATCH_SIZE) ===" >> "$LOG"

if python3 helper_scripts/db/outcome_backfiller_live.py \
        --dsn "$OPENCLAW_DATABASE_URL" \
        --engine-mode "$ENGINE_MODES" \
        --batch-size "$BATCH_SIZE" \
        ${DRY_RUN_ARGS[@]+"${DRY_RUN_ARGS[@]}"} >> "$LOG" 2>&1; then
    echo "[$(ts)] === outcome_backfiller_live end OK ===" >> "$LOG"
    exit 0
fi

rc=$?
echo "[$(ts)] === outcome_backfiller_live end FAIL rc=${rc} ===" >> "$LOG"
exit "$rc"
