#!/usr/bin/env bash
# install_cost_gate_learning_lane_cron.sh - idempotent installer for the
# artifact-only cost-gate demo-learning refresh/review cron.
#
# Installs one active hourly line at minute 27. Apply is gated by
# OPENCLAW_COST_GATE_LEARNING_CRON_APPLY=1 so a normal run is a dry-run preview.
#
# crontab 治理（P0-2④）：live crontab 的正本是同目錄 crontab.trade-core.template，
# 唯一被授權的 live crontab 寫入入口是 install_crontab_from_repo.sh；本檔條目的
# 任何增刪或 cadence/env 變更必須同步 template 正本，避免 render 安裝時被覆蓋。
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
OPENCLAW_COST_GATE_LEARNING_INSTALL_PREFLIGHT="${OPENCLAW_COST_GATE_LEARNING_INSTALL_PREFLIGHT:-1}"
OPENCLAW_COST_GATE_LEARNING_REQUIRE_EXPECTED_HEAD="${OPENCLAW_COST_GATE_LEARNING_REQUIRE_EXPECTED_HEAD:-1}"
OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD="${OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD:-${OPENCLAW_EXPECTED_SOURCE_HEAD:-}}"

# P1-4：expected head 未由 env 顯式傳入時，從 pin 檔
# $OPENCLAW_DATA_DIR/runtime_generation/expected_source_head.json 解析（部署後
# 由 deploy/derive_expected_source_head.sh 與重啟腳本自動派生），去除歷史上把
# inline SHA 手寫進安裝命令的復發保證。env 顯式傳值時仍優先（割接兼容）。
if [[ -z "$OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD" ]]; then
    _PYBIN="${OPENCLAW_PYTHON_BIN:-}"
    if [[ -z "$_PYBIN" ]]; then
        if [[ -x "$HOME/.venv/bin/python" ]]; then _PYBIN="$HOME/.venv/bin/python"; else _PYBIN="python3"; fi
    fi
    _RESOLVED_HEAD="$(
        cd "$OPENCLAW_BASE_DIR/helper_scripts/research" 2>/dev/null &&
        PYTHONDONTWRITEBYTECODE=1 "$_PYBIN" -c '
import sys
from pathlib import Path
from cost_gate_learning_lane.source_generation import resolve_expected_source_head
r = resolve_expected_source_head(None, data_dir=Path(sys.argv[1]), env={})
# pin 檔壞（error 非 None）不回傳 head：讓下游 REQUIRE 檢查照舊 fail-close，
# 不讓損壞的 pin 檔靜默退化成「未提供」。
sys.stdout.write(r["head"] or "")
' "$OPENCLAW_DATA_DIR" 2>/dev/null
    )" || _RESOLVED_HEAD=""
    if [[ -n "$_RESOLVED_HEAD" ]]; then
        OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD="$_RESOLVED_HEAD"
        echo "Resolved expected head from pin file: $OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD"
    fi
fi

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

PYBIN="${OPENCLAW_PYTHON_BIN:-}"
if [[ -z "$PYBIN" ]]; then
    if [[ -x "$HOME/.venv/bin/python" ]]; then
        PYBIN="$HOME/.venv/bin/python"
    else
        PYBIN="python3"
    fi
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
_validate_bool01 "OPENCLAW_COST_GATE_LEARNING_INSTALL_PREFLIGHT" "$OPENCLAW_COST_GATE_LEARNING_INSTALL_PREFLIGHT"
_validate_bool01 "OPENCLAW_COST_GATE_LEARNING_REQUIRE_EXPECTED_HEAD" "$OPENCLAW_COST_GATE_LEARNING_REQUIRE_EXPECTED_HEAD"
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
echo "Apply preflight: $OPENCLAW_COST_GATE_LEARNING_INSTALL_PREFLIGHT (expected-head required: $OPENCLAW_COST_GATE_LEARNING_REQUIRE_EXPECTED_HEAD)"
echo "Rollback: $0 --remove (with OPENCLAW_COST_GATE_LEARNING_CRON_APPLY=1)"
echo "Boundary: artifact-only JSONL/JSON refresh; readonly PG; no order authority or Cost Gate relaxation"

if [[ "${OPENCLAW_COST_GATE_LEARNING_CRON_APPLY:-0}" != "1" ]]; then
    echo
    echo "DRY-RUN: not modifying crontab."
    echo "Set OPENCLAW_COST_GATE_LEARNING_CRON_APPLY=1 to actually install."
    exit 0
fi

if [[ "$OPENCLAW_COST_GATE_LEARNING_INSTALL_PREFLIGHT" == "1" ]]; then
    if [[ "$OPENCLAW_COST_GATE_LEARNING_REQUIRE_EXPECTED_HEAD" == "1" && -z "$OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD" ]]; then
        echo "ERROR: OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD or OPENCLAW_EXPECTED_SOURCE_HEAD is required when apply preflight is enabled." >&2
        exit 7
    fi
    echo "Running read-only cost-gate learning activation preflight before crontab install..."
    (
        cd "$OPENCLAW_BASE_DIR"
        export PYTHONPATH="$OPENCLAW_BASE_DIR/helper_scripts/research${PYTHONPATH:+:$PYTHONPATH}"
        export OPENCLAW_BASE_DIR OPENCLAW_DATA_DIR OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD
        "$PYBIN" - <<'PY'
import json
import os
from pathlib import Path

from cost_gate_learning_lane.status import (
    build_cost_gate_learning_lane_activation_preflight,
)

data_dir = Path(os.environ["OPENCLAW_DATA_DIR"])
repo_root = Path(os.environ["OPENCLAW_BASE_DIR"])
expected_head = os.environ.get("OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD") or None
payload = build_cost_gate_learning_lane_activation_preflight(
    data_dir,
    repo_root=repo_root,
    expected_head=expected_head,
)
source = payload.get("source") or {}
plan = payload.get("plan") or {}
failures = []
if source.get("source_ready") is not True:
    failures.append("required_source_files_not_ready")
if source.get("source_activation_ready") is not True:
    failures.append(str(source.get("source_activation_status") or "source_activation_not_ready"))
if expected_head and source.get("expected_head_matches") is not True:
    failures.append(str(source.get("expected_head_status") or "expected_head_not_matched"))
if plan.get("plan_status") != "READY":
    failures.append(str(plan.get("plan_status") or "plan_not_ready"))

summary = {
    "status": payload.get("status"),
    "reason": payload.get("reason"),
    "source_activation_status": source.get("source_activation_status"),
    "expected_head_status": source.get("expected_head_status"),
    "plan_status": plan.get("plan_status"),
    "ledger_status": (payload.get("ledger") or {}).get("ledger_status"),
    "failures": failures,
    "boundary": "read-only installer preflight; no crontab edit performed by this check",
}
print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
raise SystemExit(0 if not failures else 7)
PY
    )
fi

( crontab -l 2>/dev/null; echo "$ENTRY" ) | crontab -
echo "INSTALLED: cost_gate_learning_lane cron entry added. Verify with: crontab -l | grep cost_gate_learning_lane"
