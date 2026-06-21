#!/usr/bin/env bash
# install_cost_gate_learning_lane_cron.sh - idempotent installer for the
# artifact-only cost-gate demo-learning refresh/review cron.
#
# Installs one active hourly line at minute 27. Apply is gated by
# OPENCLAW_COST_GATE_LEARNING_CRON_APPLY=1 so a normal run is a dry-run preview.
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "ERROR: install_cost_gate_learning_lane_cron.sh requires Linux runtime (current: $(uname -s))." >&2
    exit 2
fi

OPENCLAW_BASE_DIR="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
OPENCLAW_DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
OPENCLAW_COST_GATE_LEARNING_MATERIALIZE_REJECTS="${OPENCLAW_COST_GATE_LEARNING_MATERIALIZE_REJECTS:-1}"
OPENCLAW_COST_GATE_LEARNING_APPEND_MATERIALIZED_REJECTS="${OPENCLAW_COST_GATE_LEARNING_APPEND_MATERIALIZED_REJECTS:-1}"
OPENCLAW_COST_GATE_LEARNING_APPEND_OUTCOMES="${OPENCLAW_COST_GATE_LEARNING_APPEND_OUTCOMES:-1}"
OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES="${OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES:-0}"
OPENCLAW_COST_GATE_LEARNING_CRON_MINUTES="${OPENCLAW_COST_GATE_LEARNING_CRON_MINUTES:-27}"

WRAPPER="$OPENCLAW_BASE_DIR/helper_scripts/cron/cost_gate_learning_lane_cron.sh"
MARKER="cost_gate_learning_lane_cron.sh"

if [[ "${1:-}" == "--remove" ]]; then
    if ! crontab -l 2>/dev/null | grep -q "$MARKER"; then
        echo "NO-OP: no cost_gate_learning_lane cron entry found."
        exit 0
    fi
    echo "------- entries to remove -------"
    crontab -l | grep "$MARKER"
    echo "---------------------------------"
    if [[ "${OPENCLAW_COST_GATE_LEARNING_CRON_APPLY:-0}" != "1" ]]; then
        echo "DRY-RUN: not modifying crontab. Set OPENCLAW_COST_GATE_LEARNING_CRON_APPLY=1 to actually remove."
        exit 0
    fi
    crontab -l | grep -v "$MARKER" | crontab -
    echo "REMOVED: cost_gate_learning_lane cron entry."
    exit 0
fi

if [[ ! -x "$WRAPPER" ]]; then
    echo "ERROR: wrapper not executable: $WRAPPER" >&2
    exit 5
fi
mkdir -p "$OPENCLAW_DATA_DIR/logs"

if crontab -l 2>/dev/null | grep -q "$MARKER"; then
    echo "SKIP: existing cost_gate_learning_lane cron entry detected; not installing (use --remove first)." >&2
    crontab -l | grep "$MARKER" >&2
    exit 0
fi

_validate_cron_env_value() {
    local name="$1"
    local value="$2"
    if [[ -z "$value" ]]; then
        echo "ERROR: cron env value empty: ${name}" >&2
        exit 6
    fi
    if [[ ${#value} -gt 200 ]]; then
        echo "ERROR: cron env value too long (>200 chars): ${name}=${value}" >&2
        exit 6
    fi
    if [[ "$value" =~ [[:space:]%[:cntrl:]\"\'\\\$\`] ]]; then
        echo "ERROR: cron-conflict character in ${name}=${value}" >&2
        exit 6
    fi
}

_validate_bool01() {
    local name="$1"
    local value="$2"
    if [[ ! "$value" =~ ^[01]$ ]]; then
        echo "ERROR: ${name} must be 0 or 1: ${value}" >&2
        exit 6
    fi
}

_validate_cron_minute_list() {
    local name="$1"
    local value="$2"
    if [[ ! "$value" =~ ^[0-9]+(,[0-9]+)*$ ]]; then
        echo "ERROR: ${name} must be comma-separated minute integers: ${value}" >&2
        exit 6
    fi
    IFS=',' read -ra _minutes <<< "$value"
    local minute
    for minute in "${_minutes[@]}"; do
        if (( 10#$minute < 0 || 10#$minute > 59 )); then
            echo "ERROR: ${name} minute out of range 0..59: ${minute}" >&2
            exit 6
        fi
    done
}

_validate_bool01 "OPENCLAW_COST_GATE_LEARNING_APPEND_OUTCOMES" "$OPENCLAW_COST_GATE_LEARNING_APPEND_OUTCOMES"
_validate_bool01 "OPENCLAW_COST_GATE_LEARNING_MATERIALIZE_REJECTS" "$OPENCLAW_COST_GATE_LEARNING_MATERIALIZE_REJECTS"
_validate_bool01 "OPENCLAW_COST_GATE_LEARNING_APPEND_MATERIALIZED_REJECTS" "$OPENCLAW_COST_GATE_LEARNING_APPEND_MATERIALIZED_REJECTS"
_validate_bool01 "OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES" "$OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES"
_validate_cron_minute_list "OPENCLAW_COST_GATE_LEARNING_CRON_MINUTES" "$OPENCLAW_COST_GATE_LEARNING_CRON_MINUTES"
_validate_cron_env_value "OPENCLAW_BASE_DIR" "$OPENCLAW_BASE_DIR"
_validate_cron_env_value "OPENCLAW_DATA_DIR" "$OPENCLAW_DATA_DIR"
_validate_cron_env_value "OPENCLAW_COST_GATE_LEARNING_MATERIALIZE_REJECTS" "$OPENCLAW_COST_GATE_LEARNING_MATERIALIZE_REJECTS"
_validate_cron_env_value "OPENCLAW_COST_GATE_LEARNING_APPEND_MATERIALIZED_REJECTS" "$OPENCLAW_COST_GATE_LEARNING_APPEND_MATERIALIZED_REJECTS"
_validate_cron_env_value "OPENCLAW_COST_GATE_LEARNING_APPEND_OUTCOMES" "$OPENCLAW_COST_GATE_LEARNING_APPEND_OUTCOMES"
_validate_cron_env_value "OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES" "$OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES"
_validate_cron_env_value "WRAPPER" "$WRAPPER"

ENV_PREFIX="OPENCLAW_BASE_DIR=${OPENCLAW_BASE_DIR} OPENCLAW_DATA_DIR=${OPENCLAW_DATA_DIR} OPENCLAW_COST_GATE_LEARNING_MATERIALIZE_REJECTS=${OPENCLAW_COST_GATE_LEARNING_MATERIALIZE_REJECTS} OPENCLAW_COST_GATE_LEARNING_APPEND_MATERIALIZED_REJECTS=${OPENCLAW_COST_GATE_LEARNING_APPEND_MATERIALIZED_REJECTS} OPENCLAW_COST_GATE_LEARNING_APPEND_OUTCOMES=${OPENCLAW_COST_GATE_LEARNING_APPEND_OUTCOMES} OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES=${OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES}"
ENTRY="${OPENCLAW_COST_GATE_LEARNING_CRON_MINUTES} * * * * ${ENV_PREFIX} ${WRAPPER} >> ${OPENCLAW_DATA_DIR}/logs/cost_gate_learning_lane_cron.cron.log 2>&1"

echo "------- proposed crontab entry -------"
echo "$ENTRY"
echo "--------------------------------------"
echo "Schedule minutes: $OPENCLAW_COST_GATE_LEARNING_CRON_MINUTES UTC minutes"
echo "Artifacts: $OPENCLAW_DATA_DIR/cost_gate_learning_lane/"
echo "Status log: $OPENCLAW_DATA_DIR/logs/cost_gate_learning_lane.log"
echo "Heartbeat: $OPENCLAW_DATA_DIR/cron_heartbeat/cost_gate_learning_lane.last_fire"
echo "Rollback: $0 --remove (with OPENCLAW_COST_GATE_LEARNING_CRON_APPLY=1)"
echo "Boundary: artifact-only JSONL/JSON refresh; readonly PG; no order authority or Cost Gate relaxation"

if [[ "${OPENCLAW_COST_GATE_LEARNING_CRON_APPLY:-0}" != "1" ]]; then
    echo
    echo "DRY-RUN: not modifying crontab."
    echo "Set OPENCLAW_COST_GATE_LEARNING_CRON_APPLY=1 to actually install."
    exit 0
fi

( crontab -l 2>/dev/null; echo "$ENTRY" ) | crontab -
echo "INSTALLED: cost_gate_learning_lane cron entry added. Verify with: crontab -l | grep cost_gate_learning_lane"
