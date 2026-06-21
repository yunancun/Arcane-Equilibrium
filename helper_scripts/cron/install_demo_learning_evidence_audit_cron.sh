#!/usr/bin/env bash
# install_demo_learning_evidence_audit_cron.sh - idempotent installer for the
# artifact-only demo learning evidence heartbeat.
#
# Installs a twice-hourly line at minutes 7 and 37. Apply is gated by
# OPENCLAW_DEMO_LEARNING_EVIDENCE_CRON_APPLY=1, so a normal run is a dry-run preview.
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "ERROR: install_demo_learning_evidence_audit_cron.sh requires Linux runtime (current: $(uname -s))." >&2
    exit 2
fi

OPENCLAW_BASE_DIR="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
OPENCLAW_DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
OPENCLAW_DEMO_LEARNING_EVIDENCE_ENGINE_MODES="${OPENCLAW_DEMO_LEARNING_EVIDENCE_ENGINE_MODES:-demo,live_demo}"
OPENCLAW_DEMO_LEARNING_EVIDENCE_LOOKBACK_HOURS="${OPENCLAW_DEMO_LEARNING_EVIDENCE_LOOKBACK_HOURS:-24}"
OPENCLAW_DEMO_LEARNING_EVIDENCE_TOP_LIMIT="${OPENCLAW_DEMO_LEARNING_EVIDENCE_TOP_LIMIT:-20}"
OPENCLAW_DEMO_LEARNING_EVIDENCE_REQUIRE_WRITER_ENABLED="${OPENCLAW_DEMO_LEARNING_EVIDENCE_REQUIRE_WRITER_ENABLED:-0}"
OPENCLAW_DEMO_LEARNING_EVIDENCE_REQUIRE_PROCESS_WRITER_ENABLED="${OPENCLAW_DEMO_LEARNING_EVIDENCE_REQUIRE_PROCESS_WRITER_ENABLED:-0}"
OPENCLAW_DEMO_LEARNING_EVIDENCE_AUTO_DETECT_ENGINE_PID="${OPENCLAW_DEMO_LEARNING_EVIDENCE_AUTO_DETECT_ENGINE_PID:-0}"
OPENCLAW_DEMO_LEARNING_EVIDENCE_CRON_MINUTES="${OPENCLAW_DEMO_LEARNING_EVIDENCE_CRON_MINUTES:-7,37}"

WRAPPER="$OPENCLAW_BASE_DIR/helper_scripts/cron/demo_learning_evidence_audit_cron.sh"
MARKER="demo_learning_evidence_audit_cron.sh"

if [[ "${1:-}" == "--remove" ]]; then
    if ! crontab -l 2>/dev/null | grep -q "$MARKER"; then
        echo "NO-OP: no demo_learning_evidence_audit cron entry found."
        exit 0
    fi
    echo "------- entries to remove -------"
    crontab -l | grep "$MARKER"
    echo "---------------------------------"
    if [[ "${OPENCLAW_DEMO_LEARNING_EVIDENCE_CRON_APPLY:-0}" != "1" ]]; then
        echo "DRY-RUN: not modifying crontab. Set OPENCLAW_DEMO_LEARNING_EVIDENCE_CRON_APPLY=1 to actually remove."
        exit 0
    fi
    existing_crontab="$(crontab -l 2>/dev/null || true)"
    filtered_crontab="$(printf '%s\n' "$existing_crontab" | grep -v "$MARKER" || true)"
    printf '%s\n' "$filtered_crontab" | crontab -
    echo "REMOVED: demo_learning_evidence_audit cron entry."
    exit 0
fi

if [[ ! -x "$WRAPPER" ]]; then
    echo "ERROR: wrapper not executable: $WRAPPER" >&2
    exit 5
fi
mkdir -p "$OPENCLAW_DATA_DIR/logs"

if crontab -l 2>/dev/null | grep -q "$MARKER"; then
    echo "SKIP: existing demo_learning_evidence_audit cron entry detected; not installing (use --remove first)." >&2
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

_validate_int() {
    local name="$1"
    local value="$2"
    if [[ ! "$value" =~ ^[0-9]+$ ]]; then
        echo "ERROR: ${name} must be an integer: ${value}" >&2
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

_append_env_if_set() {
    local name="$1"
    local value="$2"
    if [[ -n "$value" ]]; then
        _validate_cron_env_value "$name" "$value"
        ENV_PREFIX="${ENV_PREFIX} ${name}=${value}"
    fi
}

_validate_int "OPENCLAW_DEMO_LEARNING_EVIDENCE_LOOKBACK_HOURS" "$OPENCLAW_DEMO_LEARNING_EVIDENCE_LOOKBACK_HOURS"
_validate_int "OPENCLAW_DEMO_LEARNING_EVIDENCE_TOP_LIMIT" "$OPENCLAW_DEMO_LEARNING_EVIDENCE_TOP_LIMIT"
_validate_bool01 "OPENCLAW_DEMO_LEARNING_EVIDENCE_REQUIRE_WRITER_ENABLED" "$OPENCLAW_DEMO_LEARNING_EVIDENCE_REQUIRE_WRITER_ENABLED"
_validate_bool01 "OPENCLAW_DEMO_LEARNING_EVIDENCE_REQUIRE_PROCESS_WRITER_ENABLED" "$OPENCLAW_DEMO_LEARNING_EVIDENCE_REQUIRE_PROCESS_WRITER_ENABLED"
_validate_bool01 "OPENCLAW_DEMO_LEARNING_EVIDENCE_AUTO_DETECT_ENGINE_PID" "$OPENCLAW_DEMO_LEARNING_EVIDENCE_AUTO_DETECT_ENGINE_PID"
_validate_cron_minute_list "OPENCLAW_DEMO_LEARNING_EVIDENCE_CRON_MINUTES" "$OPENCLAW_DEMO_LEARNING_EVIDENCE_CRON_MINUTES"
_validate_cron_env_value "OPENCLAW_BASE_DIR" "$OPENCLAW_BASE_DIR"
_validate_cron_env_value "OPENCLAW_DATA_DIR" "$OPENCLAW_DATA_DIR"
_validate_cron_env_value "OPENCLAW_DEMO_LEARNING_EVIDENCE_ENGINE_MODES" "$OPENCLAW_DEMO_LEARNING_EVIDENCE_ENGINE_MODES"
_validate_cron_env_value "OPENCLAW_DEMO_LEARNING_EVIDENCE_LOOKBACK_HOURS" "$OPENCLAW_DEMO_LEARNING_EVIDENCE_LOOKBACK_HOURS"
_validate_cron_env_value "OPENCLAW_DEMO_LEARNING_EVIDENCE_TOP_LIMIT" "$OPENCLAW_DEMO_LEARNING_EVIDENCE_TOP_LIMIT"
_validate_cron_env_value "WRAPPER" "$WRAPPER"

ENV_PREFIX="OPENCLAW_BASE_DIR=${OPENCLAW_BASE_DIR} OPENCLAW_DATA_DIR=${OPENCLAW_DATA_DIR} OPENCLAW_DEMO_LEARNING_EVIDENCE_ENGINE_MODES=${OPENCLAW_DEMO_LEARNING_EVIDENCE_ENGINE_MODES} OPENCLAW_DEMO_LEARNING_EVIDENCE_LOOKBACK_HOURS=${OPENCLAW_DEMO_LEARNING_EVIDENCE_LOOKBACK_HOURS} OPENCLAW_DEMO_LEARNING_EVIDENCE_TOP_LIMIT=${OPENCLAW_DEMO_LEARNING_EVIDENCE_TOP_LIMIT} OPENCLAW_DEMO_LEARNING_EVIDENCE_REQUIRE_WRITER_ENABLED=${OPENCLAW_DEMO_LEARNING_EVIDENCE_REQUIRE_WRITER_ENABLED} OPENCLAW_DEMO_LEARNING_EVIDENCE_REQUIRE_PROCESS_WRITER_ENABLED=${OPENCLAW_DEMO_LEARNING_EVIDENCE_REQUIRE_PROCESS_WRITER_ENABLED} OPENCLAW_DEMO_LEARNING_EVIDENCE_AUTO_DETECT_ENGINE_PID=${OPENCLAW_DEMO_LEARNING_EVIDENCE_AUTO_DETECT_ENGINE_PID}"
_append_env_if_set "OPENCLAW_DEMO_LEARNING_EVIDENCE_EXPECTED_HEAD" "${OPENCLAW_DEMO_LEARNING_EVIDENCE_EXPECTED_HEAD:-}"
_append_env_if_set "OPENCLAW_EXPECTED_SOURCE_HEAD" "${OPENCLAW_EXPECTED_SOURCE_HEAD:-}"
_append_env_if_set "OPENCLAW_DEMO_LEARNING_EVIDENCE_RUNTIME_ENV_FILE" "${OPENCLAW_DEMO_LEARNING_EVIDENCE_RUNTIME_ENV_FILE:-}"
_append_env_if_set "OPENCLAW_DEMO_LEARNING_EVIDENCE_ENGINE_PID" "${OPENCLAW_DEMO_LEARNING_EVIDENCE_ENGINE_PID:-}"
_append_env_if_set "OPENCLAW_DEMO_LEARNING_EVIDENCE_RUNTIME_PROC_ENVIRON" "${OPENCLAW_DEMO_LEARNING_EVIDENCE_RUNTIME_PROC_ENVIRON:-}"

ENTRY="${OPENCLAW_DEMO_LEARNING_EVIDENCE_CRON_MINUTES} * * * * ${ENV_PREFIX} ${WRAPPER} >> ${OPENCLAW_DATA_DIR}/logs/demo_learning_evidence_audit_cron.cron.log 2>&1"

echo "------- proposed crontab entry -------"
echo "$ENTRY"
echo "--------------------------------------"
echo "Schedule minutes: $OPENCLAW_DEMO_LEARNING_EVIDENCE_CRON_MINUTES UTC minutes"
echo "Artifacts: $OPENCLAW_DATA_DIR/demo_learning_evidence/"
echo "Status log: $OPENCLAW_DATA_DIR/logs/demo_learning_evidence_audit.log"
echo "Heartbeat: $OPENCLAW_DATA_DIR/cron_heartbeat/demo_learning_evidence_audit.last_fire"
echo "Rollback: $0 --remove (with OPENCLAW_DEMO_LEARNING_EVIDENCE_CRON_APPLY=1)"
echo "Boundary: artifact-only Markdown/JSON heartbeat; readonly PG; no order authority or Cost Gate relaxation"

if [[ "${OPENCLAW_DEMO_LEARNING_EVIDENCE_CRON_APPLY:-0}" != "1" ]]; then
    echo
    echo "DRY-RUN: not modifying crontab."
    echo "Set OPENCLAW_DEMO_LEARNING_EVIDENCE_CRON_APPLY=1 to actually install."
    exit 0
fi

( crontab -l 2>/dev/null; echo "$ENTRY" ) | crontab -
echo "INSTALLED: demo_learning_evidence_audit cron entry added. Verify with: crontab -l | grep demo_learning_evidence_audit"
