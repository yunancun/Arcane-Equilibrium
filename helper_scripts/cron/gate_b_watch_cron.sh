#!/usr/bin/env bash
# gate_b_watch_cron.sh — Gate-B public-window watcher cron wrapper.
#
# Runs the alert-only Gate-B watcher. It writes local state/artifacts and may
# emit alerts; it never starts the Gate-B probe or touches trading/runtime/DB
# paths.
set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/gate_b_watch_cron.log"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/gate_b_watch_cron.lock.d"
HEARTBEAT_DIR="${DATA}/cron_heartbeat"

mkdir -p "$LOG_DIR" "$LOCK_ROOT" "$HEARTBEAT_DIR"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

export OPENCLAW_BASE_DIR="${OPENCLAW_BASE_DIR:-$BASE}"
export OPENCLAW_DATA_DIR="${OPENCLAW_DATA_DIR:-$DATA}"

if [[ -d "$LOCK_DIR" ]] && [[ -n "$(find "$LOCK_DIR" -maxdepth 0 -mmin +45 2>/dev/null)" ]]; then
    echo "[$(ts)] WARN: stale lock (>45min) cleared: $LOCK_DIR" >> "$LOG"
    rmdir "$LOCK_DIR" 2>/dev/null || true
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: gate_b_watch already running (lock held)" >> "$LOG"
    exit 0
fi
release_lock() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap release_lock EXIT INT TERM

touch "$HEARTBEAT_DIR/gate_b_watch.last_fire"

SCRIPT="$BASE/helper_scripts/canary/gate_b_watch.py"
if [[ ! -f "$SCRIPT" ]]; then
    echo "[$(ts)] ERROR: gate_b_watch.py not found under BASE=$BASE" >> "$LOG"
    exit 0
fi

PYBIN="${OPENCLAW_PYTHON_BIN:-}"
if [[ -z "$PYBIN" ]]; then
    if [[ -x "$HOME/.venv/bin/python" ]]; then
        PYBIN="$HOME/.venv/bin/python"
    else
        PYBIN="python3"
    fi
fi

echo "[$(ts)] === gate_b_watch start ===" >> "$LOG"
rc=0
"$PYBIN" "$SCRIPT" --once --data-dir "$DATA" >> "$LOG" 2>&1 || rc=$?
echo "[$(ts)] === gate_b_watch end rc=${rc} ===" >> "$LOG"

exit 0
