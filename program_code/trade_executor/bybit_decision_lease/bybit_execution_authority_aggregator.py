#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
I7 / Execution Authority Aggregator
I7 / 执行授权汇总器

Purpose / 目的
--------------
把 I6 approval bridge 的结果进一步规范成一个单点 authority view：
- 明确 policy guard 是否已满足
- 明确 operator review 是否仍 pending
- 明确 execution authority 是否已 granted
- 明确当前是否仍 shadow-only
- 明确当前绝不 live grant / 不发放实时执行授权

This stage MUST remain non-live.
本阶段必须保持非 live 模式。
"""

import json
import time
from pathlib import Path
import os
from typing import Any, Dict, List
from bybit_decision_lease_common import read_json, save_report, as_list, merged_unique

BASE = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")

I6_BRIDGE_PATH = BASE / "bybit_decision_lease_approval_bridge_latest.json"
I6_AUDIT_PATH = BASE / "bybit_decision_lease_approval_bridge_final_audit_latest.json"
I1_SCHEMA_PATH = BASE / "bybit_decision_lease_schema_latest.json"
I2_AUDIT_PATH = BASE / "bybit_decision_lease_shadow_final_audit_latest.json"
I3_AUDIT_PATH = BASE / "bybit_decision_lease_consume_final_audit_latest.json"
I4_AUDIT_PATH = BASE / "bybit_decision_lease_replay_final_audit_latest.json"
I5_AUDIT_PATH = BASE / "bybit_decision_lease_friction_final_audit_latest.json"

LATEST_PATH = BASE / "bybit_execution_authority_aggregator_latest.json"


def main() -> None:
    now_ms = int(time.time() * 1000)

    i6_bridge = read_json(I6_BRIDGE_PATH)
    i6_audit = read_json(I6_AUDIT_PATH) or {}
    i1_schema = read_json(I1_SCHEMA_PATH)
    i2_audit = read_json(I2_AUDIT_PATH) or {}
    i3_audit = read_json(I3_AUDIT_PATH) or {}
    i4_audit = read_json(I4_AUDIT_PATH) or {}
    i5_audit = read_json(I5_AUDIT_PATH) or {}

    source_errors: List[str] = []
    if i6_bridge is None:
        source_errors.append("i6_approval_bridge_missing_or_invalid")
    if i1_schema is None:
        source_errors.append("i1_decision_lease_schema_missing_or_invalid")

    request_summary = (i6_bridge or {}).get("request_summary") or {}
    bridge_view = (i6_bridge or {}).get("approval_bridge_view") or {}
    governance_guards = (i6_bridge or {}).get("governance_guards") or {}
    lease_runtime_view = (i6_bridge or {}).get("lease_runtime_view") or {}
    schema_runtime_view = (i1_schema or {}).get("schema_runtime_view") or {}
    schema_def = (i1_schema or {}).get("lease_schema_definition") or {}

    # -------- Aggregated authority prerequisites / 授权前提汇总 --------
    policy_guard_passed = bool(bridge_view.get("policy_guard_passed", False))
    operator_review_required = bool(bridge_view.get("operator_review_required", True))
    operator_review_status = bridge_view.get("operator_review_status", "unknown")

    execution_authority = (
        governance_guards.get("execution_authority")
        or lease_runtime_view.get("execution_authority")
        or schema_runtime_view.get("execution_authority")
        or "unknown"
    )
    execution_authority_required = schema_def.get("execution_authority_required", "granted")
    execution_authority_granted = execution_authority == "granted"

    lease_emit_allowed_now = bool(
        lease_runtime_view.get("lease_emit_allowed_now", schema_runtime_view.get("lease_emit_allowed_now", False))
    )
    decision_lease_emitted = bool(
        lease_runtime_view.get("decision_lease_emitted", schema_runtime_view.get("decision_lease_emitted", False))
    )
    live_execution_allowed = bool(
        lease_runtime_view.get("live_execution_allowed", schema_runtime_view.get("live_execution_allowed", False))
    )

    shadow_authority_only = True
    authority_grant_live = False

    # -------- Readiness matrix / 就绪矩阵 --------
    readiness_matrix = {
        "policy_guard_passed": policy_guard_passed,
        "operator_review_required": operator_review_required,
        "operator_review_status": operator_review_status,
        "execution_authority_required": execution_authority_required,
        "execution_authority": execution_authority,
        "execution_authority_granted": execution_authority_granted,
        "lease_emit_allowed_now": lease_emit_allowed_now,
        "decision_lease_emitted": decision_lease_emitted,
        "live_execution_allowed": live_execution_allowed,
    }

    blocking_reasons: List[str] = list(source_errors)
    if not policy_guard_passed:
        blocking_reasons.append("policy_guard_not_passed")
    if operator_review_required and operator_review_status != "approved":
        blocking_reasons.append("operator_review_not_approved")
    if execution_authority_required == "granted" and not execution_authority_granted:
        blocking_reasons.append("execution_authority_not_granted")

    # 但本阶段本来就是 shadow-only，所以虽然聚合出来这些 blocker，
    # 仍然可以“作为阶段完成”进入 I8。
    # This stage can still close in shadow-only mode even if live grant prerequisites are not satisfied.
    aggregator_ok = len(source_errors) == 0 and policy_guard_passed

    if aggregator_ok:
        aggregator_state = "execution_authority_aggregated_shadow_ready_soft_warn"
        allow_progress_to_i8_manual_approval_packet = True
        recommended_action = "may_progress_to_i8_manual_approval_packet"
    else:
        aggregator_state = "execution_authority_aggregation_blocked"
        allow_progress_to_i8_manual_approval_packet = False
        recommended_action = "inspect_i7_authority_aggregation_blockers"

    warning_flags = merged_unique(
        (i6_bridge or {}).get("warning_flags"),
        i6_audit.get("warning_flags"),
        i2_audit.get("warning_flags"),
        i3_audit.get("warning_flags"),
        i4_audit.get("warning_flags"),
        i5_audit.get("warning_flags"),
        [
            "execution_authority_aggregator_shadow_only_mode",
            "operator_review_still_pending" if operator_review_required and operator_review_status != "approved" else None,
            "execution_authority_not_granted" if not execution_authority_granted else None,
            "live_authority_grant_not_active",
        ],
    )

    report: Dict[str, Any] = {
        "aggregator_type": "bybit_execution_authority_aggregator",
        "aggregator_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "I7",
        "aggregator_ok": aggregator_ok,
        "source_refs": {
            "i6_approval_bridge_path": str(I6_BRIDGE_PATH),
            "i6_approval_bridge_final_audit_path": str(I6_AUDIT_PATH),
            "i1_decision_lease_schema_path": str(I1_SCHEMA_PATH),
            "i2_decision_lease_shadow_final_audit_path": str(I2_AUDIT_PATH),
            "i3_decision_lease_consume_final_audit_path": str(I3_AUDIT_PATH),
            "i4_decision_lease_replay_final_audit_path": str(I4_AUDIT_PATH),
            "i5_decision_lease_friction_final_audit_path": str(I5_AUDIT_PATH),
        },
        "source_integrity": {
            "i6_approval_bridge_present": i6_bridge is not None,
            "i1_decision_lease_schema_present": i1_schema is not None,
            "source_errors": source_errors,
        },
        "request_summary": {
            "provider_target": request_summary.get("provider_target"),
            "model_name": request_summary.get("model_name"),
            "selected_ai_tier": request_summary.get("selected_ai_tier"),
            "route_plan": request_summary.get("route_plan"),
        },
        "authority_model": {
            "authority_mode": "shadow_only",
            "authority_strategy": "aggregate_policy_operator_authority_without_live_grant",
            "shadow_authority_only": shadow_authority_only,
            "authority_grant_live": authority_grant_live,
        },
        "governance_guards": {
            "system_mode": governance_guards.get("system_mode"),
            "execution_state": governance_guards.get("execution_state"),
            "execution_authority": execution_authority,
            "live_execution_allowed": live_execution_allowed,
            "decision_lease_emitted": decision_lease_emitted,
            "operator_review_required": operator_review_required,
        },
        "aggregated_authority_view": readiness_matrix,
        "blocking_reasons": blocking_reasons,
        "warning_flags": warning_flags,
        "aggregator_state": aggregator_state,
        "allow_progress_to_i8_manual_approval_packet": allow_progress_to_i8_manual_approval_packet,
        "recommended_action": recommended_action,
        "operator_message": (
            "I7 execution authority aggregation built. Authority remains shadow-only and live grant is still inactive."
            if aggregator_ok else
            "I7 execution authority aggregation blocked."
        ),
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))
    save_report(report, LATEST_PATH)


if __name__ == "__main__":
    main()
