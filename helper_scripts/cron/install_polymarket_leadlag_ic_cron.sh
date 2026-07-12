#!/usr/bin/env bash
# install_polymarket_leadlag_ic_cron.sh - idempotent installer for the
# Polymarket lead-lag IC refresh cron.
#
# Installs one active hourly line at minute 17, after polymarket_axis hourly
# top-N normally runs at minute 7. For artifact-only accelerated evidence
# capture, set OPENCLAW_POLYMARKET_LEADLAG_CRON_MINUTES=2,17,32,47 after
# installing the collector at 7,22,37,52. Apply is gated by
# OPENCLAW_POLYMARKET_LEADLAG_CRON_APPLY=1.
#
# crontab 治理（P0-2④）：live crontab 的正本是同目錄 crontab.trade-core.template，
# 唯一被授權的 live crontab 寫入入口是 install_crontab_from_repo.sh；本檔條目的
# 任何增刪或 cadence/env 變更必須同步 template 正本，避免 render 安裝時被覆蓋。
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "ERROR: install_polymarket_leadlag_ic_cron.sh requires Linux runtime (current: $(uname -s))." >&2
    exit 2
fi

OPENCLAW_BASE_DIR="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
OPENCLAW_DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
OPENCLAW_POLYMARKET_LEADLAG_QUERY_SET="${OPENCLAW_POLYMARKET_LEADLAG_QUERY_SET:-${OPENCLAW_POLYMARKET_QUERY_SET:-v2}}"
OPENCLAW_POLYMARKET_LEADLAG_SYMBOLS="${OPENCLAW_POLYMARKET_LEADLAG_SYMBOLS:-BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT}"
OPENCLAW_POLYMARKET_LEADLAG_MIN_POINTS="${OPENCLAW_POLYMARKET_LEADLAG_MIN_POINTS:-30}"
OPENCLAW_POLYMARKET_LEADLAG_CRON_MINUTES="${OPENCLAW_POLYMARKET_LEADLAG_CRON_MINUTES:-17}"

WRAPPER="$OPENCLAW_BASE_DIR/helper_scripts/cron/polymarket_leadlag_ic_cron.sh"
MARKER="polymarket_leadlag_ic_cron.sh"

if [[ "${1:-}" == "--remove" ]]; then
    if ! crontab -l 2>/dev/null | grep -q "$MARKER"; then
        echo "NO-OP: no polymarket_leadlag_ic cron entry found."
        exit 0
    fi
    echo "------- entries to remove -------"
    crontab -l | grep "$MARKER"
    echo "---------------------------------"
    if [[ "${OPENCLAW_POLYMARKET_LEADLAG_CRON_APPLY:-0}" != "1" ]]; then
        echo "DRY-RUN: not modifying crontab. Set OPENCLAW_POLYMARKET_LEADLAG_CRON_APPLY=1 to actually remove."
        exit 0
    fi
    crontab -l | grep -v "$MARKER" | crontab -
    echo "REMOVED: polymarket_leadlag_ic cron entry."
    exit 0
fi

if [[ ! -x "$WRAPPER" ]]; then
    echo "ERROR: wrapper not executable: $WRAPPER" >&2
    exit 5
fi
mkdir -p "$OPENCLAW_DATA_DIR/logs"

if crontab -l 2>/dev/null | grep -q "$MARKER"; then
    echo "SKIP: existing polymarket_leadlag_ic cron entry detected; not installing (use --remove first)." >&2
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

case "$OPENCLAW_POLYMARKET_LEADLAG_QUERY_SET" in
    v1|v2) ;;
    *)
        echo "ERROR: OPENCLAW_POLYMARKET_LEADLAG_QUERY_SET must be v1 or v2." >&2
        exit 6
        ;;
esac
_validate_int "OPENCLAW_POLYMARKET_LEADLAG_MIN_POINTS" "$OPENCLAW_POLYMARKET_LEADLAG_MIN_POINTS"
_validate_cron_minute_list "OPENCLAW_POLYMARKET_LEADLAG_CRON_MINUTES" "$OPENCLAW_POLYMARKET_LEADLAG_CRON_MINUTES"
_validate_cron_env_value "OPENCLAW_BASE_DIR" "$OPENCLAW_BASE_DIR"
_validate_cron_env_value "OPENCLAW_DATA_DIR" "$OPENCLAW_DATA_DIR"
_validate_cron_env_value "OPENCLAW_POLYMARKET_LEADLAG_QUERY_SET" "$OPENCLAW_POLYMARKET_LEADLAG_QUERY_SET"
_validate_cron_env_value "OPENCLAW_POLYMARKET_LEADLAG_SYMBOLS" "$OPENCLAW_POLYMARKET_LEADLAG_SYMBOLS"
_validate_cron_env_value "OPENCLAW_POLYMARKET_LEADLAG_MIN_POINTS" "$OPENCLAW_POLYMARKET_LEADLAG_MIN_POINTS"
_validate_cron_env_value "WRAPPER" "$WRAPPER"

ENV_PREFIX="OPENCLAW_BASE_DIR=${OPENCLAW_BASE_DIR} OPENCLAW_DATA_DIR=${OPENCLAW_DATA_DIR} OPENCLAW_POLYMARKET_LEADLAG_QUERY_SET=${OPENCLAW_POLYMARKET_LEADLAG_QUERY_SET} OPENCLAW_POLYMARKET_LEADLAG_SYMBOLS=${OPENCLAW_POLYMARKET_LEADLAG_SYMBOLS} OPENCLAW_POLYMARKET_LEADLAG_MIN_POINTS=${OPENCLAW_POLYMARKET_LEADLAG_MIN_POINTS}"
ENTRY="${OPENCLAW_POLYMARKET_LEADLAG_CRON_MINUTES} * * * * ${ENV_PREFIX} ${WRAPPER} >> ${OPENCLAW_DATA_DIR}/logs/polymarket_leadlag_ic_cron.cron.log 2>&1"

echo "------- proposed crontab entry -------"
echo "$ENTRY"
echo "--------------------------------------"
echo "Schedule minutes: $OPENCLAW_POLYMARKET_LEADLAG_CRON_MINUTES UTC minutes, after polymarket_axis collector cadence"
echo "Artifacts: $OPENCLAW_DATA_DIR/research/polymarket_leadlag/"
echo "Heartbeat: $OPENCLAW_DATA_DIR/cron_heartbeat/polymarket_leadlag_ic.last_fire"
echo "Rollback: $0 --remove (with OPENCLAW_POLYMARKET_LEADLAG_CRON_APPLY=1)"

if [[ "${OPENCLAW_POLYMARKET_LEADLAG_CRON_APPLY:-0}" != "1" ]]; then
    echo
    echo "DRY-RUN: not modifying crontab."
    echo "Set OPENCLAW_POLYMARKET_LEADLAG_CRON_APPLY=1 to actually install."
    exit 0
fi

( crontab -l 2>/dev/null; echo "$ENTRY" ) | crontab -
echo "INSTALLED: polymarket_leadlag_ic cron entry added. Verify with: crontab -l | grep polymarket_leadlag_ic"
