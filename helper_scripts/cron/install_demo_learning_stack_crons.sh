#!/usr/bin/env bash
# install_demo_learning_stack_crons.sh - operator-gated installer for the
# demo-learning evidence heartbeat, sealed horizon preflight refresher,
# cost-gate learning-lane cron, and stack health artifact refresher.
#
# Purpose:
#   Install the bounded learning crons as one reviewed stack, avoiding a
#   half-installed state where demo evidence, sealed preflight, or Cost Gate
#   learning runs without the health artifact that alpha-discovery consumes for
#   completion evidence.
#
# Default behavior is a dry-run preview. Crontab mutation requires
# OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=1.
#
# crontab 治理（P0-2④）：live crontab 的正本是同目錄 crontab.trade-core.template，
# 唯一被授權的 live crontab 寫入入口是 install_crontab_from_repo.sh；本檔條目的
# 任何增刪或 cadence/env 變更必須同步 template 正本，避免 render 安裝時被覆蓋。
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "ERROR: install_demo_learning_stack_crons.sh requires Linux runtime (current: $(uname -s))." >&2
    exit 2
fi

OPENCLAW_BASE_DIR="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
OPENCLAW_DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD="${OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD:-${OPENCLAW_EXPECTED_SOURCE_HEAD:-}}"
OPENCLAW_DEMO_LEARNING_STACK_PREFLIGHT="${OPENCLAW_DEMO_LEARNING_STACK_PREFLIGHT:-1}"
OPENCLAW_DEMO_LEARNING_STACK_PREINSTALL_REFRESH="${OPENCLAW_DEMO_LEARNING_STACK_PREINSTALL_REFRESH:-1}"

DEMO_INSTALLER="$OPENCLAW_BASE_DIR/helper_scripts/cron/install_demo_learning_evidence_audit_cron.sh"
SEALED_PREFLIGHT_INSTALLER="$OPENCLAW_BASE_DIR/helper_scripts/cron/install_sealed_horizon_probe_preflight_cron.sh"
SEALED_PREFLIGHT_WRAPPER="$OPENCLAW_BASE_DIR/helper_scripts/cron/sealed_horizon_probe_preflight_cron.sh"
COST_INSTALLER="$OPENCLAW_BASE_DIR/helper_scripts/cron/install_cost_gate_learning_lane_cron.sh"
HEALTH_INSTALLER="$OPENCLAW_BASE_DIR/helper_scripts/cron/install_demo_learning_stack_healthcheck_cron.sh"
COST_WRAPPER="$OPENCLAW_BASE_DIR/helper_scripts/cron/cost_gate_learning_lane_cron.sh"

_validate_bool01() {
    local name="$1"
    local value="$2"
    if [[ ! "$value" =~ ^[01]$ ]]; then
        echo "ERROR: ${name} must be 0 or 1: ${value}" >&2
        exit 6
    fi
}

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

_validate_sha_prefix() {
    local name="$1"
    local value="$2"
    if [[ -z "$value" ]]; then
        echo "ERROR: ${name} is required for stack apply/preflight." >&2
        exit 7
    fi
    if [[ ! "$value" =~ ^[0-9a-fA-F]{7,40}$ ]]; then
        echo "ERROR: ${name} must be a git SHA prefix, got: ${value}" >&2
        exit 7
    fi
}

_require_executable() {
    local path="$1"
    if [[ ! -x "$path" ]]; then
        echo "ERROR: required executable missing: $path" >&2
        exit 5
    fi
}

_source_head_preflight() {
    _validate_sha_prefix "OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD or OPENCLAW_EXPECTED_SOURCE_HEAD" "$OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD"

    local head
    head="$(git -C "$OPENCLAW_BASE_DIR" rev-parse HEAD)"
    case "$head" in
        "$OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD"*) ;;
        *)
            echo "ERROR: runtime source HEAD mismatch: head=${head} expected=${OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD}" >&2
            exit 7
            ;;
    esac

    local dirty
    dirty="$(git -C "$OPENCLAW_BASE_DIR" status --porcelain)"
    if [[ -n "$dirty" ]]; then
        echo "ERROR: runtime source is dirty; review/reconcile before installing learning stack." >&2
        printf '%s\n' "$dirty" | sed -n '1,40p' >&2
        exit 7
    fi
}

_cost_gate_plan_preflight() {
    local pybin="${OPENCLAW_PYTHON_BIN:-}"
    if [[ -z "$pybin" ]]; then
        if [[ -x "$HOME/.venv/bin/python" ]]; then
            pybin="$HOME/.venv/bin/python"
        else
            pybin="python3"
        fi
    fi
    (
        cd "$OPENCLAW_BASE_DIR"
        export PYTHONPATH="$OPENCLAW_BASE_DIR/helper_scripts/research${PYTHONPATH:+:$PYTHONPATH}"
        export OPENCLAW_DATA_DIR OPENCLAW_BASE_DIR OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD
        "$pybin" - <<'PY'
import json
import os
from pathlib import Path

from cost_gate_learning_lane.status import (
    build_cost_gate_learning_lane_activation_preflight,
)

payload = build_cost_gate_learning_lane_activation_preflight(
    Path(os.environ["OPENCLAW_DATA_DIR"]),
    repo_root=Path(os.environ["OPENCLAW_BASE_DIR"]),
    expected_head=os.environ.get("OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD") or None,
)
source = payload.get("source") or {}
plan = payload.get("plan") or {}
failures = []
if source.get("source_ready") is not True:
    failures.append("required_source_files_not_ready")
if source.get("source_activation_ready") is not True:
    failures.append(str(source.get("source_activation_status") or "source_activation_not_ready"))
if source.get("expected_head_matches") is not True:
    failures.append(str(source.get("expected_head_status") or "expected_head_not_matched"))
if plan.get("plan_status") != "READY":
    failures.append(str(plan.get("plan_status") or "plan_not_ready"))
summary = {
    "status": payload.get("status"),
    "reason": payload.get("reason"),
    "source_activation_status": source.get("source_activation_status"),
    "expected_head_status": source.get("expected_head_status"),
    "plan_status": plan.get("plan_status"),
    "plan_reason": plan.get("plan_reason"),
    "failures": failures,
    "boundary": "read-only stack preflight; no crontab edit performed by this check",
}
print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
raise SystemExit(0 if not failures else 7)
PY
    )
}

_run_preinstall_refresh() {
    echo "Running artifact-only sealed horizon preflight refresh before stack install..."
    OPENCLAW_BASE_DIR="$OPENCLAW_BASE_DIR" \
    OPENCLAW_DATA_DIR="$OPENCLAW_DATA_DIR" \
    "$SEALED_PREFLIGHT_WRAPPER"

    echo "Running read-only/artifact-only Cost Gate preinstall refresh before stack install..."
    OPENCLAW_BASE_DIR="$OPENCLAW_BASE_DIR" \
    OPENCLAW_DATA_DIR="$OPENCLAW_DATA_DIR" \
    OPENCLAW_COST_GATE_LEARNING_PREINSTALL_REFRESH_ONLY=1 \
    "$COST_WRAPPER"
}

_run_child_previews() {
    echo
    echo "=== Demo-learning evidence cron preview ==="
    OPENCLAW_BASE_DIR="$OPENCLAW_BASE_DIR" \
    OPENCLAW_DATA_DIR="$OPENCLAW_DATA_DIR" \
    OPENCLAW_DEMO_LEARNING_EVIDENCE_CRON_APPLY=0 \
    OPENCLAW_DEMO_LEARNING_EVIDENCE_EXPECTED_HEAD="$OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD" \
    OPENCLAW_EXPECTED_SOURCE_HEAD="$OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD" \
    "$DEMO_INSTALLER"

    echo
    echo "=== Sealed horizon probe preflight cron preview ==="
    OPENCLAW_BASE_DIR="$OPENCLAW_BASE_DIR" \
    OPENCLAW_DATA_DIR="$OPENCLAW_DATA_DIR" \
    OPENCLAW_SEALED_HORIZON_PREFLIGHT_CRON_APPLY=0 \
    OPENCLAW_SEALED_HORIZON_PREFLIGHT_EXPECTED_HEAD="$OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD" \
    OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD="$OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD" \
    OPENCLAW_EXPECTED_SOURCE_HEAD="$OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD" \
    "$SEALED_PREFLIGHT_INSTALLER"

    echo
    echo "=== Cost Gate learning-lane cron preview ==="
    OPENCLAW_BASE_DIR="$OPENCLAW_BASE_DIR" \
    OPENCLAW_DATA_DIR="$OPENCLAW_DATA_DIR" \
    OPENCLAW_COST_GATE_LEARNING_CRON_APPLY=0 \
    OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD="$OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD" \
    OPENCLAW_EXPECTED_SOURCE_HEAD="$OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD" \
    "$COST_INSTALLER"

    echo
    echo "=== Demo-learning stack healthcheck cron preview ==="
    OPENCLAW_BASE_DIR="$OPENCLAW_BASE_DIR" \
    OPENCLAW_DATA_DIR="$OPENCLAW_DATA_DIR" \
    OPENCLAW_DEMO_LEARNING_STACK_HEALTHCHECK_CRON_APPLY=0 \
    OPENCLAW_DEMO_LEARNING_STACK_HEALTHCHECK_EXPECTED_HEAD="$OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD" \
    OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD="$OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD" \
    OPENCLAW_EXPECTED_SOURCE_HEAD="$OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD" \
    "$HEALTH_INSTALLER"
}

_install_children() {
    OPENCLAW_BASE_DIR="$OPENCLAW_BASE_DIR" \
    OPENCLAW_DATA_DIR="$OPENCLAW_DATA_DIR" \
    OPENCLAW_DEMO_LEARNING_EVIDENCE_CRON_APPLY=1 \
    OPENCLAW_DEMO_LEARNING_EVIDENCE_EXPECTED_HEAD="$OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD" \
    OPENCLAW_EXPECTED_SOURCE_HEAD="$OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD" \
    "$DEMO_INSTALLER"

    OPENCLAW_BASE_DIR="$OPENCLAW_BASE_DIR" \
    OPENCLAW_DATA_DIR="$OPENCLAW_DATA_DIR" \
    OPENCLAW_SEALED_HORIZON_PREFLIGHT_CRON_APPLY=1 \
    OPENCLAW_SEALED_HORIZON_PREFLIGHT_EXPECTED_HEAD="$OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD" \
    OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD="$OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD" \
    OPENCLAW_EXPECTED_SOURCE_HEAD="$OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD" \
    "$SEALED_PREFLIGHT_INSTALLER"

    OPENCLAW_BASE_DIR="$OPENCLAW_BASE_DIR" \
    OPENCLAW_DATA_DIR="$OPENCLAW_DATA_DIR" \
    OPENCLAW_COST_GATE_LEARNING_CRON_APPLY=1 \
    OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD="$OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD" \
    OPENCLAW_EXPECTED_SOURCE_HEAD="$OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD" \
    "$COST_INSTALLER"

    OPENCLAW_BASE_DIR="$OPENCLAW_BASE_DIR" \
    OPENCLAW_DATA_DIR="$OPENCLAW_DATA_DIR" \
    OPENCLAW_DEMO_LEARNING_STACK_HEALTHCHECK_CRON_APPLY=1 \
    OPENCLAW_DEMO_LEARNING_STACK_HEALTHCHECK_EXPECTED_HEAD="$OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD" \
    OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD="$OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD" \
    OPENCLAW_EXPECTED_SOURCE_HEAD="$OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD" \
    "$HEALTH_INSTALLER"
}

_remove_children() {
    OPENCLAW_BASE_DIR="$OPENCLAW_BASE_DIR" \
    OPENCLAW_DATA_DIR="$OPENCLAW_DATA_DIR" \
    OPENCLAW_DEMO_LEARNING_STACK_HEALTHCHECK_CRON_APPLY="${OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY:-0}" \
    "$HEALTH_INSTALLER" --remove

    OPENCLAW_BASE_DIR="$OPENCLAW_BASE_DIR" \
    OPENCLAW_DATA_DIR="$OPENCLAW_DATA_DIR" \
    OPENCLAW_COST_GATE_LEARNING_CRON_APPLY="${OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY:-0}" \
    "$COST_INSTALLER" --remove

    OPENCLAW_BASE_DIR="$OPENCLAW_BASE_DIR" \
    OPENCLAW_DATA_DIR="$OPENCLAW_DATA_DIR" \
    OPENCLAW_SEALED_HORIZON_PREFLIGHT_CRON_APPLY="${OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY:-0}" \
    "$SEALED_PREFLIGHT_INSTALLER" --remove

    OPENCLAW_BASE_DIR="$OPENCLAW_BASE_DIR" \
    OPENCLAW_DATA_DIR="$OPENCLAW_DATA_DIR" \
    OPENCLAW_DEMO_LEARNING_EVIDENCE_CRON_APPLY="${OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY:-0}" \
    "$DEMO_INSTALLER" --remove
}

_validate_bool01 "OPENCLAW_DEMO_LEARNING_STACK_PREFLIGHT" "$OPENCLAW_DEMO_LEARNING_STACK_PREFLIGHT"
_validate_bool01 "OPENCLAW_DEMO_LEARNING_STACK_PREINSTALL_REFRESH" "$OPENCLAW_DEMO_LEARNING_STACK_PREINSTALL_REFRESH"
_validate_cron_env_value "OPENCLAW_BASE_DIR" "$OPENCLAW_BASE_DIR"
_validate_cron_env_value "OPENCLAW_DATA_DIR" "$OPENCLAW_DATA_DIR"
_require_executable "$DEMO_INSTALLER"
_require_executable "$SEALED_PREFLIGHT_INSTALLER"
_require_executable "$SEALED_PREFLIGHT_WRAPPER"
_require_executable "$COST_INSTALLER"
_require_executable "$HEALTH_INSTALLER"
_require_executable "$COST_WRAPPER"

echo "Demo learning stack installer"
echo "Base: $OPENCLAW_BASE_DIR"
echo "Data: $OPENCLAW_DATA_DIR"
echo "Expected head: ${OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD:-<required on apply/preflight>}"
echo "Apply: ${OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY:-0}"
echo "Preflight: $OPENCLAW_DEMO_LEARNING_STACK_PREFLIGHT"
echo "Preinstall refresh: $OPENCLAW_DEMO_LEARNING_STACK_PREINSTALL_REFRESH"
echo "Boundary: crontab-only stack installer plus artifact-only preinstall refresh/health status; no source sync, deploy, restart, PG write, Bybit call, order authority, probe authority, or Cost Gate relaxation"

if [[ "${1:-}" == "--remove" ]]; then
    echo
    echo "Removing healthcheck cron first, then Cost Gate learning cron, then sealed horizon preflight cron, then demo-learning evidence cron."
    _remove_children
    exit 0
fi

_run_child_previews

if [[ "${OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY:-0}" != "1" ]]; then
    echo
    echo "DRY-RUN: not modifying crontab."
    echo "Set OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=1 and OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD=<pushed-head> to install the full demo-learning cron stack."
    exit 0
fi

if [[ "$OPENCLAW_DEMO_LEARNING_STACK_PREFLIGHT" == "1" ]]; then
    _source_head_preflight
fi
if [[ "$OPENCLAW_DEMO_LEARNING_STACK_PREINSTALL_REFRESH" == "1" ]]; then
    _run_preinstall_refresh
fi
if [[ "$OPENCLAW_DEMO_LEARNING_STACK_PREFLIGHT" == "1" ]]; then
    _cost_gate_plan_preflight
fi

_install_children
echo "INSTALLED: demo-learning evidence, sealed horizon preflight, Cost Gate learning-lane, and stack healthcheck cron stack."
