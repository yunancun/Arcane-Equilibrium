#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
I6 / Decision Lease Approval Bridge
I6 / 决策租约多角色审批桥

目标 Goal
---------
把已有的 governed observation、lease schema、I2~I5 的 shadow-only 成果，
收束成一个“审批桥视图”：
- 先确认：AI 输出已经被治理为 observation-only
- 再确认：lease 仍然只是 schema/shadow，不可 live emit
- 再把“人工复核 / execution authority / policy guard”放到同一层可审计表达
- 但本阶段仍然不授予 live approval grant

This stage intentionally stays shadow-only and non-executable.
本阶段有意保持 shadow-only，绝不赋予可执行权限。
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")

GOVERNED_DECISION_PATH = BASE / "bybit_ai_governed_decision_latest.json"
LEASE_SCHEMA_PATH = BASE / "bybit_decision_lease_schema_latest.json"
LEASE_SCHEMA_AUDIT_PATH = BASE / "bybit_decision_lease_final_audit_latest.json"
LEASE_SHADOW_AUDIT_PATH = BASE / "bybit_decision_lease_shadow_final_audit_latest.json"
LEASE_CONSUME_AUDIT_PATH = BASE / "bybit_decision_lease_consume_final_audit_latest.json"
LEASE_REPLAY_AUDIT_PATH = BASE / "bybit_decision_lease_replay_final_audit_latest.json"
LEASE_FRICTION_AUDIT_PATH = BASE / "bybit_decision_lease_friction_final_audit_latest.json"

LATEST_PATH = BASE / "bybit_decision_lease_approval_bridge_latest.json"


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def merged_unique(*parts: Any) -> List[Any]:
    out: List[Any] = []
    seen = set()
    for part in parts:
        for item in as_list(part):
            key = json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, (dict, list)) else str(item)
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
    return out


def save_report(report: Dict[str, Any], latest_path: Path) -> None:
    ts_ms = report.get("ts_ms")
    dated_path = latest_path.with_name(latest_path.stem.replace("_latest", f"_{ts_ms}") + latest_path.suffix)
    latest_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    dated_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"saved_latest={latest_path}")
    print(f"saved_dated={dated_path}")


def main() -> None:
    now_ms = int(time.time() * 1000)

    governed = read_json(GOVERNED_DECISION_PATH)
    lease_schema = read_json(LEASE_SCHEMA_PATH)

    schema_audit = read_json(LEASE_SCHEMA_AUDIT_PATH) or {}
    shadow_audit = read_json(LEASE_SHADOW_AUDIT_PATH) or {}
    consume_audit = read_json(LEASE_CONSUME_AUDIT_PATH) or {}
    replay_audit = read_json(LEASE_REPLAY_AUDIT_PATH) or {}
    friction_audit = read_json(LEASE_FRICTION_AUDIT_PATH) or {}

    source_errors: List[str] = []
    if governed is None:
        source_errors.append("ai_governed_decision_missing_or_invalid")
    if lease_schema is None:
        source_errors.append("decision_lease_schema_missing_or_invalid")

    request_summary = (governed or {}).get("request_summary") or {}
    governance_guards = (governed or {}).get("governance_guards") or {}
    governed_observation = (governed or {}).get("governed_observation") or {}

    lease_schema_definition = (lease_schema or {}).get("lease_schema_definition") or {}
    schema_runtime_view = (lease_schema or {}).get("schema_runtime_view") or {}

    # -------- 统一当前保护状态 / Unified protection state --------
    system_mode = governance_guards.get("system_mode", "unknown")
    execution_state = governance_guards.get("execution_state", "unknown")
    operator_review_required = bool(governance_guards.get("operator_review_required", True))

    execution_authority = (
        schema_runtime_view.get("execution_authority")
        or governance_guards.get("execution_authority")
        or "unknown"
    )
    live_execution_allowed = bool(
        schema_runtime_view.get("live_execution_allowed", governance_guards.get("live_execution_allowed", False))
    )
    decision_lease_emitted = bool(
        schema_runtime_view.get("decision_lease_emitted", governance_guards.get("decision_lease_emitted", False))
    )
    lease_emit_allowed_now = bool(schema_runtime_view.get("lease_emit_allowed_now", False))
    schema_only_mode = bool(schema_runtime_view.get("schema_only_mode", True))

    # -------- 本阶段桥接判断 / Bridge logic for this stage --------
    governed_observation_ready = bool((governed or {}).get("decision_ok")) and (
        governed_observation.get("analysis_mode") == "observation_only"
    )
    lease_schema_ready = bool((lease_schema or {}).get("schema_ok"))
    required_execution_authority = lease_schema_definition.get("execution_authority_required", "granted")

    policy_guard_passed = governed_observation_ready
    operator_review_status = "pending_manual_review" if operator_review_required else "not_required"
    execution_authority_status = "granted" if execution_authority == "granted" else "not_granted"
    shadow_bridge_only = True
    live_approval_grant_active = False

    blocking_reasons: List[str] = list(source_errors)
    if not governed_observation_ready:
        blocking_reasons.append("governed_observation_not_ready")
    if not lease_schema_ready:
        blocking_reasons.append("decision_lease_schema_not_ready")

    if blocking_reasons:
        bridge_ok = False
        bridge_state = "decision_lease_approval_bridge_blocked"
        allow_progress_to_i7_execution_authority_aggregator = False
        recommended_action = "inspect_i6_bridge_blockers"
        approval_quorum_state = "blocked_before_bridge"
    else:
        bridge_ok = True
        bridge_state = "decision_lease_approval_bridge_shadow_ready_soft_warn"
        allow_progress_to_i7_execution_authority_aggregator = True
        recommended_action = "may_progress_to_i7_execution_authority_aggregator"
        approval_quorum_state = "shadow_waiting_manual_and_authority"

    warning_flags = merged_unique(
        (governed or {}).get("warning_flags"),
        (lease_schema or {}).get("warning_flags"),
        schema_audit.get("warning_flags"),
        shadow_audit.get("warning_flags"),
        consume_audit.get("warning_flags"),
        replay_audit.get("warning_flags"),
        friction_audit.get("warning_flags"),
        [
            "decision_lease_approval_bridge_shadow_only_mode",
            "decision_lease_operator_review_pending" if operator_review_required else None,
            "decision_lease_execution_authority_not_granted" if execution_authority != "granted" else None,
        ],
    )
    warning_flags = [x for x in warning_flags if x is not None]

    report: Dict[str, Any] = {
        "bridge_type": "bybit_decision_lease_approval_bridge",
        "bridge_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "I6",
        "bridge_ok": bridge_ok,
        "source_refs": {
            "ai_governed_decision_path": str(GOVERNED_DECISION_PATH),
            "decision_lease_schema_path": str(LEASE_SCHEMA_PATH),
            "decision_lease_final_audit_path": str(LEASE_SCHEMA_AUDIT_PATH),
            "decision_lease_shadow_final_audit_path": str(LEASE_SHADOW_AUDIT_PATH),
            "decision_lease_consume_final_audit_path": str(LEASE_CONSUME_AUDIT_PATH),
            "decision_lease_replay_final_audit_path": str(LEASE_REPLAY_AUDIT_PATH),
            "decision_lease_friction_final_audit_path": str(LEASE_FRICTION_AUDIT_PATH),
        },
        "source_integrity": {
            "ai_governed_decision_present": governed is not None,
            "decision_lease_schema_present": lease_schema is not None,
            "source_errors": source_errors,
        },
        "request_summary": {
            "provider_target": request_summary.get("provider_target"),
            "model_name": request_summary.get("model_name"),
            "selected_ai_tier": request_summary.get("selected_ai_tier"),
            "route_plan": request_summary.get("route_plan"),
        },
        "approval_model": {
            "bridge_mode": "shadow_only",
            "approval_strategy": "policy_guard_plus_manual_review_plus_execution_authority",
            "approval_roles": [
                "policy_guard",
                "operator_review",
                "execution_authority",
            ],
            "required_execution_authority": required_execution_authority,
            "live_approval_grant_active": live_approval_grant_active,
        },
        "governance_guards": {
            "system_mode": system_mode,
            "execution_state": execution_state,
            "execution_authority": execution_authority,
            "live_execution_allowed": live_execution_allowed,
            "decision_lease_emitted": decision_lease_emitted,
            "operator_review_required": operator_review_required,
        },
        "lease_runtime_view": {
            "schema_only_mode": schema_only_mode,
            "lease_emit_allowed_now": lease_emit_allowed_now,
            "decision_lease_emitted": decision_lease_emitted,
            "live_execution_allowed": live_execution_allowed,
            "execution_authority": execution_authority,
        },
        "approval_bridge_view": {
            "governed_observation_ready": governed_observation_ready,
            "lease_schema_ready": lease_schema_ready,
            "policy_guard_passed": policy_guard_passed,
            "operator_review_required": operator_review_required,
            "operator_review_status": operator_review_status,
            "execution_authority_required": required_execution_authority,
            "execution_authority_status": execution_authority_status,
            "approval_quorum_state": approval_quorum_state,
            "shadow_bridge_only": shadow_bridge_only,
            "live_approval_grant_active": live_approval_grant_active,
        },
        "warning_flags": warning_flags,
        "blocking_reasons": blocking_reasons,
        "bridge_state": bridge_state,
        "allow_progress_to_i7_execution_authority_aggregator": allow_progress_to_i7_execution_authority_aggregator,
        "recommended_action": recommended_action,
        "operator_message": (
            "I6 approval bridge built. Lease remains shadow-only, manual review remains required, "
            "and execution authority is still not granted."
            if bridge_ok else
            "I6 approval bridge blocked. Inspect blockers before continuing."
        ),
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))
    save_report(report, LATEST_PATH)


if __name__ == "__main__":
    main()
