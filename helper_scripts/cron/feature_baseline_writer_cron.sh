#!/usr/bin/env bash
# feature_baseline_writer_cron.sh — W-AUDIT-4b runtime apply wrapper
#
# Suggested cron entry, installed manually by the operator:
#   41 4 * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw \
#       $HOME/BybitOpenClaw/srv/helper_scripts/cron/feature_baseline_writer_cron.sh
#
# This wrapper is intentionally narrow: it runs the Rust feature_baseline_writer
# with OPENCLAW_FEATURE_BASELINE_APPLY=1, never with CLI apply/force flags. The
# writer still defaults to dry-run unless that env gate is present.

set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/feature_baseline_writer_cron.log"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/feature_baseline_writer_cron.lock.d"

mkdir -p "$LOG_DIR" "$LOCK_ROOT"

# Cron heartbeat sentinel — P1-CRON-INSTALL-WAVE-1（2026-05-18）。
# touch-at-start：「cron 被排程觸發」的證據，由 healthcheck [78] 監測 mtime。
HEARTBEAT_DIR="${DATA}/cron_heartbeat"
mkdir -p "$HEARTBEAT_DIR" 2>/dev/null || true
touch "$HEARTBEAT_DIR/feature_baseline_writer.last_fire" 2>/dev/null || true

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
export OPENCLAW_FEATURE_BASELINE_APPLY=1

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: feature baseline writer already running (lock held)" >> "$LOG"
    exit 0
fi
release_lock() {
    local rc=$?
    rmdir "$LOCK_DIR" 2>/dev/null || true
    return "$rc"
}
trap release_lock EXIT INT TERM

if [[ ! -d "$BASE/rust" ]]; then
    echo "[$(ts)] ERROR: rust workspace not found under BASE=${BASE}" >> "$LOG"
    exit 1
fi

ARGS=(
    --lookback-days "${OPENCLAW_FEATURE_BASELINE_LOOKBACK_DAYS:-180}"
    --window-days "${OPENCLAW_FEATURE_BASELINE_WINDOW_DAYS:-30}"
    --step-days "${OPENCLAW_FEATURE_BASELINE_STEP_DAYS:-7}"
    --bins "${OPENCLAW_FEATURE_BASELINE_BINS:-10}"
)
if [[ -n "${OPENCLAW_FEATURE_BASELINE_SYMBOL:-}" ]]; then
    ARGS+=(--symbol "$OPENCLAW_FEATURE_BASELINE_SYMBOL")
fi

echo "[$(ts)] === feature baseline writer start (BASE=$BASE lookback=${OPENCLAW_FEATURE_BASELINE_LOOKBACK_DAYS:-180}d) ===" >> "$LOG"

WRITER_RELEASE="$BASE/rust/target/release/feature_baseline_writer"
WRITER_DEBUG="$BASE/rust/target/debug/feature_baseline_writer"
if [[ -x "$WRITER_RELEASE" ]]; then
    "$WRITER_RELEASE" "${ARGS[@]}" >> "$LOG" 2>&1
elif [[ -x "$WRITER_DEBUG" ]]; then
    "$WRITER_DEBUG" "${ARGS[@]}" >> "$LOG" 2>&1
else
    (
        cd "$BASE/rust"
        cargo run -q -p openclaw_engine --bin feature_baseline_writer -- "${ARGS[@]}"
    ) >> "$LOG" 2>&1
fi

PY="${OPENCLAW_PYTHON:-${BASE}/program_code/exchange_connectors/bybit_connector/control_api_v1/.venv/bin/python3}"
if [[ ! -x "$PY" ]]; then
    PY="python3"
fi

if "$PY" "$BASE/helper_scripts/db/feature_baseline_healthcheck.py" >> "$LOG" 2>&1; then
    echo "[$(ts)] === feature baseline writer end OK ===" >> "$LOG"
    exit 0
fi

rc=$?
echo "[$(ts)] === feature baseline writer end FAIL healthcheck_rc=${rc} ===" >> "$LOG"
exit "$rc"
