#!/usr/bin/env bash
# alpha_discovery_throughput_cron.sh — artifact-only alpha discovery killboard.
#
# Runs the read-only runtime artifact runner. It only writes local discovery
# artifacts/logs/heartbeat under OPENCLAW_DATA_DIR; it does not connect to DB,
# Bybit, auth, risk, or order paths.
set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/alpha_discovery_throughput_cron.log"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/alpha_discovery_throughput_cron.lock.d"
HEARTBEAT_DIR="${DATA}/cron_heartbeat"

mkdir -p "$LOG_DIR" "$LOCK_ROOT" "$HEARTBEAT_DIR"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

export OPENCLAW_BASE_DIR="${OPENCLAW_BASE_DIR:-$BASE}"
export OPENCLAW_DATA_DIR="${OPENCLAW_DATA_DIR:-$DATA}"

if [[ -d "$LOCK_DIR" ]] && [[ -n "$(find "$LOCK_DIR" -maxdepth 0 -mmin +20 2>/dev/null)" ]]; then
    echo "[$(ts)] WARN: stale lock (>20min) cleared: $LOCK_DIR" >> "$LOG"
    rmdir "$LOCK_DIR" 2>/dev/null || true
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: alpha discovery throughput already running (lock held)" >> "$LOG"
    exit 0
fi
release_lock() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap release_lock EXIT INT TERM

touch "$HEARTBEAT_DIR/alpha_discovery_throughput.last_fire"

if [[ ! -d "$BASE/helper_scripts/research/alpha_discovery_throughput" ]]; then
    echo "[$(ts)] ERROR: alpha_discovery_throughput package not found under BASE=$BASE" >> "$LOG"
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

echo "[$(ts)] === alpha_discovery_throughput start ===" >> "$LOG"
PACKET_SCRIPT="$BASE/helper_scripts/cron/demo_learning_stack_activation_packet.py"
PACKET_DIR="$DATA/demo_learning_stack_activation_packet"
if [[ -f "$PACKET_SCRIPT" ]]; then
    mkdir -p "$PACKET_DIR"
    packet_rc=0
    "$PYBIN" "$PACKET_SCRIPT" \
        --data-dir "$DATA" \
        --repo-root "$BASE" \
        --python-bin "$PYBIN" \
        --json-output "$PACKET_DIR/demo_learning_stack_activation_packet_latest.json" \
        > "$PACKET_DIR/demo_learning_stack_activation_packet_stdout.json" 2>> "$LOG" || packet_rc=$?
    echo "[$(ts)] activation_packet_refresh rc=${packet_rc}" >> "$LOG"
else
    echo "[$(ts)] WARN: activation packet script not found: $PACKET_SCRIPT" >> "$LOG"
fi
DRY_RUN_SCRIPT="$BASE/helper_scripts/cron/demo_learning_stack_dry_run_review.py"
DRY_RUN_DIR="$DATA/demo_learning_stack_dry_run_review"
if [[ -f "$DRY_RUN_SCRIPT" ]]; then
    mkdir -p "$DRY_RUN_DIR"
    dry_run_rc=0
    "$PYBIN" "$DRY_RUN_SCRIPT" \
        --data-dir "$DATA" \
        --repo-root "$BASE" \
        --python-bin "$PYBIN" \
        --json-output "$DRY_RUN_DIR/demo_learning_stack_dry_run_review_latest.json" \
        > "$DRY_RUN_DIR/demo_learning_stack_dry_run_review_stdout.json" 2>> "$LOG" || dry_run_rc=$?
    echo "[$(ts)] dry_run_review_refresh rc=${dry_run_rc}" >> "$LOG"
else
    echo "[$(ts)] WARN: dry-run review script not found: $DRY_RUN_SCRIPT" >> "$LOG"
fi
rc=0
(
    cd "$BASE/helper_scripts/research"
    "$PYBIN" -m alpha_discovery_throughput.runtime_runner \
        --data-dir "$DATA" \
        --repo-root "$BASE" \
        --print-json
) >> "$LOG" 2>&1 || rc=$?
echo "[$(ts)] === alpha_discovery_throughput end rc=${rc} ===" >> "$LOG"

exit 0
