#!/usr/bin/env bash
# install_sealed_horizon_probe_preflight_cron.sh - idempotent installer for
# the artifact-only sealed horizon bounded-probe preflight refresher.
#
# Installs one hourly line at minute 22. Apply is gated by
# OPENCLAW_SEALED_HORIZON_PREFLIGHT_CRON_APPLY=1, so a normal run is a
# dry-run preview.
#
# crontab 治理（P0-2④）：live crontab 的正本是同目錄 crontab.trade-core.template，
# 唯一被授權的 live crontab 寫入入口是 install_crontab_from_repo.sh；本檔條目的
# 任何增刪或 cadence/env 變更必須同步 template 正本，避免 render 安裝時被覆蓋。
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "ERROR: install_sealed_horizon_probe_preflight_cron.sh requires Linux runtime (current: $(uname -s))." >&2
    exit 2
fi

OPENCLAW_BASE_DIR="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
OPENCLAW_DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
OPENCLAW_SEALED_HORIZON_PREFLIGHT_CRON_MINUTES="${OPENCLAW_SEALED_HORIZON_PREFLIGHT_CRON_MINUTES:-22}"
OPENCLAW_SEALED_HORIZON_PREFLIGHT_REQUIRE_EXPECTED_HEAD="${OPENCLAW_SEALED_HORIZON_PREFLIGHT_REQUIRE_EXPECTED_HEAD:-1}"
OPENCLAW_SEALED_HORIZON_PREFLIGHT_EXPECTED_HEAD="${OPENCLAW_SEALED_HORIZON_PREFLIGHT_EXPECTED_HEAD:-${OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD:-${OPENCLAW_EXPECTED_SOURCE_HEAD:-}}}"
OPENCLAW_SEALED_HORIZON_PREFLIGHT_MAX_ARTIFACT_AGE_HOURS="${OPENCLAW_SEALED_HORIZON_PREFLIGHT_MAX_ARTIFACT_AGE_HOURS:-24}"

WRAPPER="$OPENCLAW_BASE_DIR/helper_scripts/cron/sealed_horizon_probe_preflight_cron.sh"
MARKER="sealed_horizon_probe_preflight_cron.sh"

if [[ "${1:-}" == "--remove" ]]; then
    if ! crontab -l 2>/dev/null | grep -q "$MARKER"; then
        echo "NO-OP: no sealed_horizon_probe_preflight cron entry found."
        exit 0
    fi
    echo "------- entries to remove -------"
    crontab -l | grep "$MARKER"
    echo "---------------------------------"
    if [[ "${OPENCLAW_SEALED_HORIZON_PREFLIGHT_CRON_APPLY:-0}" != "1" ]]; then
        echo "DRY-RUN: not modifying crontab. Set OPENCLAW_SEALED_HORIZON_PREFLIGHT_CRON_APPLY=1 to actually remove."
        exit 0
    fi
    existing_crontab="$(crontab -l 2>/dev/null || true)"
    filtered_crontab="$(printf '%s\n' "$existing_crontab" | grep -v "$MARKER" || true)"
    printf '%s\n' "$filtered_crontab" | crontab -
    echo "REMOVED: sealed_horizon_probe_preflight cron entry."
    exit 0
fi

if [[ ! -x "$WRAPPER" ]]; then
    echo "ERROR: wrapper not executable: $WRAPPER" >&2
    exit 5
fi
mkdir -p "$OPENCLAW_DATA_DIR/logs"

if crontab -l 2>/dev/null | grep -q "$MARKER"; then
    echo "SKIP: existing sealed_horizon_probe_preflight cron entry detected; not installing (use --remove first)." >&2
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

_validate_sha_prefix() {
    local name="$1"
    local value="$2"
    if [[ ! "$value" =~ ^[0-9a-fA-F]{7,40}$ ]]; then
        echo "ERROR: ${name} must be a git SHA prefix, got: ${value}" >&2
        exit 7
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

_validate_bool01 "OPENCLAW_SEALED_HORIZON_PREFLIGHT_REQUIRE_EXPECTED_HEAD" "$OPENCLAW_SEALED_HORIZON_PREFLIGHT_REQUIRE_EXPECTED_HEAD"
_validate_cron_minute_list "OPENCLAW_SEALED_HORIZON_PREFLIGHT_CRON_MINUTES" "$OPENCLAW_SEALED_HORIZON_PREFLIGHT_CRON_MINUTES"
_validate_int "OPENCLAW_SEALED_HORIZON_PREFLIGHT_MAX_ARTIFACT_AGE_HOURS" "$OPENCLAW_SEALED_HORIZON_PREFLIGHT_MAX_ARTIFACT_AGE_HOURS"
_validate_cron_env_value "OPENCLAW_BASE_DIR" "$OPENCLAW_BASE_DIR"
_validate_cron_env_value "OPENCLAW_DATA_DIR" "$OPENCLAW_DATA_DIR"
_validate_cron_env_value "OPENCLAW_SEALED_HORIZON_PREFLIGHT_MAX_ARTIFACT_AGE_HOURS" "$OPENCLAW_SEALED_HORIZON_PREFLIGHT_MAX_ARTIFACT_AGE_HOURS"
_validate_cron_env_value "WRAPPER" "$WRAPPER"
if [[ -n "$OPENCLAW_SEALED_HORIZON_PREFLIGHT_EXPECTED_HEAD" ]]; then
    _validate_sha_prefix "OPENCLAW_SEALED_HORIZON_PREFLIGHT_EXPECTED_HEAD" "$OPENCLAW_SEALED_HORIZON_PREFLIGHT_EXPECTED_HEAD"
fi

ENV_PREFIX="OPENCLAW_BASE_DIR=${OPENCLAW_BASE_DIR} OPENCLAW_DATA_DIR=${OPENCLAW_DATA_DIR} OPENCLAW_SEALED_HORIZON_PREFLIGHT_MAX_ARTIFACT_AGE_HOURS=${OPENCLAW_SEALED_HORIZON_PREFLIGHT_MAX_ARTIFACT_AGE_HOURS}"
_append_env_if_set "OPENCLAW_SEALED_HORIZON_PREFLIGHT_EXPECTED_HEAD" "$OPENCLAW_SEALED_HORIZON_PREFLIGHT_EXPECTED_HEAD"
_append_env_if_set "OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD" "${OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD:-}"
_append_env_if_set "OPENCLAW_EXPECTED_SOURCE_HEAD" "${OPENCLAW_EXPECTED_SOURCE_HEAD:-}"

ENTRY="${OPENCLAW_SEALED_HORIZON_PREFLIGHT_CRON_MINUTES} * * * * ${ENV_PREFIX} ${WRAPPER} >> ${OPENCLAW_DATA_DIR}/logs/sealed_horizon_probe_preflight_cron.cron.log 2>&1"

echo "------- proposed crontab entry -------"
echo "$ENTRY"
echo "--------------------------------------"
echo "Schedule minutes: $OPENCLAW_SEALED_HORIZON_PREFLIGHT_CRON_MINUTES UTC minutes"
echo "Artifacts: $OPENCLAW_DATA_DIR/cost_gate_learning_lane/sealed_horizon_probe_preflight_latest.{json,md}"
echo "Status log: $OPENCLAW_DATA_DIR/logs/sealed_horizon_probe_preflight.log"
echo "Heartbeat: $OPENCLAW_DATA_DIR/cron_heartbeat/sealed_horizon_probe_preflight.last_fire"
echo "Apply expected-head required: $OPENCLAW_SEALED_HORIZON_PREFLIGHT_REQUIRE_EXPECTED_HEAD"
echo "Rollback: $0 --remove (with OPENCLAW_SEALED_HORIZON_PREFLIGHT_CRON_APPLY=1)"
echo "Boundary: artifact-only sealed horizon preflight refresh; no crontab write without apply, PG/Bybit/order/runtime mutation, probe authority, or Cost Gate relaxation"

if [[ "${OPENCLAW_SEALED_HORIZON_PREFLIGHT_CRON_APPLY:-0}" != "1" ]]; then
    echo
    echo "DRY-RUN: not modifying crontab."
    echo "Set OPENCLAW_SEALED_HORIZON_PREFLIGHT_CRON_APPLY=1 to actually install."
    exit 0
fi

if [[ "$OPENCLAW_SEALED_HORIZON_PREFLIGHT_REQUIRE_EXPECTED_HEAD" == "1" && -z "$OPENCLAW_SEALED_HORIZON_PREFLIGHT_EXPECTED_HEAD" ]]; then
    echo "ERROR: OPENCLAW_SEALED_HORIZON_PREFLIGHT_EXPECTED_HEAD, OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD, or OPENCLAW_EXPECTED_SOURCE_HEAD is required on apply." >&2
    exit 7
fi

( crontab -l 2>/dev/null; echo "$ENTRY" ) | crontab -
echo "INSTALLED: sealed_horizon_probe_preflight cron entry added. Verify with: crontab -l | grep sealed_horizon_probe_preflight"
