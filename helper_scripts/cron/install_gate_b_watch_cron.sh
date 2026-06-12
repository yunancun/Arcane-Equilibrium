#!/usr/bin/env bash
# install_gate_b_watch_cron.sh — Gate-B watcher cron idempotent installer.
#
# Default is dry-run. Set OPENCLAW_GATE_B_WATCH_CRON_APPLY=1 on Linux runtime
# to add/remove the crontab entry.
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "ERROR: install_gate_b_watch_cron.sh requires Linux runtime (current: $(uname -s))." >&2
    echo "       Run through ssh trade-core." >&2
    exit 2
fi

OPENCLAW_BASE_DIR="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
OPENCLAW_DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"

WRAPPER="$OPENCLAW_BASE_DIR/helper_scripts/cron/gate_b_watch_cron.sh"
MARKER="gate_b_watch_cron.sh"

if [[ "${1:-}" == "--remove" ]]; then
    if ! crontab -l 2>/dev/null | grep -q "$MARKER"; then
        echo "NO-OP: no gate_b_watch cron entry found."
        exit 0
    fi
    echo "------- entries to remove -------"
    crontab -l | grep "$MARKER"
    echo "---------------------------------"
    if [[ "${OPENCLAW_GATE_B_WATCH_CRON_APPLY:-0}" != "1" ]]; then
        echo "DRY-RUN: not modifying crontab. Set OPENCLAW_GATE_B_WATCH_CRON_APPLY=1 to remove."
        exit 0
    fi
    crontab -l | grep -v "$MARKER" | crontab -
    echo "REMOVED: gate_b_watch cron entry."
    exit 0
fi

if [[ ! -x "$WRAPPER" ]]; then
    echo "ERROR: wrapper not executable: $WRAPPER" >&2
    exit 5
fi
mkdir -p "$OPENCLAW_DATA_DIR/logs"

if crontab -l 2>/dev/null | grep -q "$MARKER"; then
    echo "SKIP: existing gate_b_watch cron entry detected; not installing (use --remove first)." >&2
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
        echo "       Disallowed: space / % / control / quote / backslash / \$ / backtick" >&2
        exit 6
    fi
}

_validate_cron_env_value "OPENCLAW_BASE_DIR" "$OPENCLAW_BASE_DIR"
_validate_cron_env_value "OPENCLAW_DATA_DIR" "$OPENCLAW_DATA_DIR"
_validate_cron_env_value "WRAPPER" "$WRAPPER"

ENTRY="12,42 * * * * OPENCLAW_BASE_DIR=${OPENCLAW_BASE_DIR} OPENCLAW_DATA_DIR=${OPENCLAW_DATA_DIR} ${WRAPPER} >> ${OPENCLAW_DATA_DIR}/logs/gate_b_watch_cron.cron.log 2>&1"

echo "------- proposed crontab entry -------"
echo "$ENTRY"
echo "--------------------------------------"
echo "Schedule: 12,42 * * * * (every 30 minutes, offset from announcement sentinel)"
echo "Heartbeat: $OPENCLAW_DATA_DIR/cron_heartbeat/gate_b_watch.last_fire"
echo "State: $OPENCLAW_DATA_DIR/gate_b_watch_state.json"
echo "Latest artifact: $OPENCLAW_DATA_DIR/gate_b_watch/gate_b_watch_latest.json"
echo "Rollback: $0 --remove (with OPENCLAW_GATE_B_WATCH_CRON_APPLY=1)"

if [[ "${OPENCLAW_GATE_B_WATCH_CRON_APPLY:-0}" != "1" ]]; then
    echo
    echo "DRY-RUN: not modifying crontab."
    echo "Set OPENCLAW_GATE_B_WATCH_CRON_APPLY=1 to actually install."
    echo
    echo "Pre-apply checks:"
    echo "  python3 $OPENCLAW_BASE_DIR/helper_scripts/canary/gate_b_watch.py --once --dry-run --data-dir /tmp/gate_b_watch_drill"
    echo "  $WRAPPER"
    exit 0
fi

( crontab -l 2>/dev/null; echo "$ENTRY" ) | crontab -
echo "INSTALLED: gate_b_watch cron entry added. Verify with: crontab -l | grep gate_b_watch"
