#!/usr/bin/env bash
# REF-21 recurring V058 symbol-universe recorder.
#
# Suggested cron:
#   20 * * * * "$OPENCLAW_BASE_DIR/helper_scripts/cron/ref21_symbol_universe_snapshot_cron.sh"
#
# This records Bybit public instruments-info into market.symbol_universe_snapshots
# only. It deliberately skips governance.strategy_freeze_log and V059 edge cells;
# those are strategy/config freeze surfaces, not hourly universe heartbeats.

set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
LOG_DIR="${DATA}/logs"
LOCK_ROOT="${DATA}/locks"
LOG="${LOG_DIR}/ref21_symbol_universe_snapshot.log"
SENTINEL="${DATA}/ref21_symbol_universe_snapshot_last_run"

mkdir -p "$LOG_DIR" "$LOCK_ROOT"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

LOCK_DIR="${LOCK_ROOT}/ref21_symbol_universe_snapshot.lock.d"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: ref21 symbol universe snapshot already running" >> "$LOG"
    exit 0
fi
release_lock() { rmdir "$LOCK_DIR" 2>/dev/null || true; }
trap release_lock EXIT INT TERM

ENV_FILE="${SECRETS_ROOT}/environment_files/basic_system_services.env"
if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

PY="${OPENCLAW_PYTHON:-}"
if [[ -z "$PY" ]]; then
    if [[ -x "${BASE}/venvs/mac_dev/bin/python" ]]; then
        PY="${BASE}/venvs/mac_dev/bin/python"
    else
        PY="python3"
    fi
fi

CATEGORIES="${OPENCLAW_REF21_V058_CATEGORIES:-linear}"
STATUSES="${OPENCLAW_REF21_V058_STATUSES:-Trading,PreLaunch,Delivering,Closed}"
RPS="${OPENCLAW_REF21_V058_RPS:-2}"
ACTOR="${OPENCLAW_REF21_V058_ACTOR:-ref21_v058_recorder}"

echo "[$(ts)] START: REF-21 V058 universe snapshot categories=${CATEGORIES} statuses=${STATUSES}" >> "$LOG"

"$PY" "${BASE}/helper_scripts/db/ref21_backfill_v058_v059.py" \
    --apply \
    --skip-edge \
    --skip-freeze-log \
    --actor "$ACTOR" \
    --categories "$CATEGORIES" \
    --instrument-statuses "$STATUSES" \
    --rps "$RPS" >> "$LOG" 2>&1

touch "$SENTINEL"
echo "[$(ts)] DONE: REF-21 V058 universe snapshot" >> "$LOG"
