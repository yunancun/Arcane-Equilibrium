#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
I1-A / Decision lease schema
中文：
- 定义 decision lease 的正式 schema 与 guard snapshot 模板
- 明确当前阶段仅允许 no-emit / no-authority 的 schema 建模
- I1 的目标是完成结构设计，不是发放执行权限

English:
- Define the formal decision-lease schema and guard-snapshot template
- Explicitly keep the current stage in no-emit / no-authority schema-only mode
- The goal of I1 is structure design, not execution authorization
"""

import time

from bybit_h_stage_common import read_json_if_exists, unique_list, write_report
from bybit_path_policy import get_thought_gate_runtime_dir

BASE = get_thought_gate_runtime_dir()

H1_GOV_PATH = BASE / "bybit_ai_governed_decision_latest.json"
H5_AUDIT_PATH = BASE / "bybit_ai_cost_governance_final_audit_latest.json"
H1_AUDIT_PATH = BASE / "bybit_thought_gate_final_audit_latest.json"

PREFIX = "bybit_decision_lease_schema"


def main() -> None:
    now_ms = int(time.time() * 1000)

    gov = read_json_if_exists(H1_GOV_PATH)
    h5 = read_json_if_exists(H5_AUDIT_PATH)
    h1 = read_json_if_exists(H1_AUDIT_PATH)

    governance_guards = gov.get("governance_guards") or {}
    governed_observation = gov.get("governed_observation") or {}
    h5_summary = h5.get("audit_summary") or {}
    h1_summary = h1.get("audit_summary") or {}

    warning_flags = unique_list(
        (h5.get("warning_flags") or [])
    )

    blocking_reasons = []
    if h1_summary.get("h1_stage_closed") is not True:
        blocking_reasons.append("h1_not_closed")
    if h5_summary.get("h5_stage_closed") is not True:
        blocking_reasons.append("h5_not_closed")
    if h5_summary.get("ready_for_i1") is not True:
        blocking_reasons.append("h5_not_ready_for_i1")
    if governance_guards.get("system_mode") != "read_only":
        blocking_reasons.append("system_mode_not_read_only")
    if governance_guards.get("execution_state") != "disabled":
        blocking_reasons.append("execution_state_not_disabled")
    if governance_guards.get("execution_authority") != "not_granted":
        blocking_reasons.append("execution_authority_not_protected")
    if governance_guards.get("decision_lease_emitted") is not False:
        blocking_reasons.append("unexpected_decision_lease_emitted")
    if governed_observation.get("analysis_mode") != "observation_only":
        blocking_reasons.append("analysis_mode_not_observation_only")

    schema_ok = not blocking_reasons

    lease_schema_definition = {
        "schema_name": "bybit_decision_lease",
        "schema_version": "v1",
        "execution_authority_required": "granted",
        "required_fields": [
            "lease_id",
            "lease_version",
            "exchange",
            "symbol",
            "decision_type",
            "action_side",
            "confidence_0_to_1",
            "edge_assessment_bps",
            "issued_at_ms",
            "expires_at_ms",
            "execution_authority",
            "decision_lease_emitted",
            "route_plan",
            "provider_target",
            "model_name",
            "guard_snapshot",
        ],
        "timing_constraints": {
            "min_ttl_ms": 1000,
            "max_ttl_ms": 30000,
        },
        "hard_disqualifiers": [
            "system_mode != read_only/controlled_execution_transition",
            "execution_state != explicitly_enabled",
            "execution_authority != granted",
            "decision_lease_emitted != true_on_issue_path_only",
            "missing_guard_snapshot",
            "expired_lease",
        ],
        "operator_review_required_before_emit": True,
    }

    lease_template = {
        "lease_id": None,
        "lease_version": "v1",
        "exchange": "bybit",
        "symbol": None,
        "decision_type": "governed_trade_lease",
        "action_side": None,
        "confidence_0_to_1": None,
        "edge_assessment_bps": None,
        "issued_at_ms": None,
        "expires_at_ms": None,
        "execution_authority": "not_granted",
        "decision_lease_emitted": False,
        "route_plan": None,
        "provider_target": None,
        "model_name": None,
        "guard_snapshot": {
            "system_mode": "read_only",
            "execution_state": "disabled",
            "operator_review_required": True,
        },
    }

    schema_runtime_view = {
        "schema_only_mode": True,
        "lease_emit_allowed_now": False,
        "execution_authority": governance_guards.get("execution_authority"),
        "decision_lease_emitted": governance_guards.get("decision_lease_emitted"),
        "live_execution_allowed": governance_guards.get("live_execution_allowed"),
        "operator_review_required": governance_guards.get("operator_review_required"),
    }

    schema_state = (
        "decision_lease_schema_ready_no_emit_soft_warn"
        if schema_ok and warning_flags else
        "decision_lease_schema_ready_no_emit"
        if schema_ok else
        "decision_lease_schema_blocked"
    )

    report = {
        "schema_type": "bybit_decision_lease_schema",
        "schema_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "I1-A",
        "schema_ok": schema_ok,
        "source_refs": {
            "ai_governed_decision_path": str(H1_GOV_PATH),
            "ai_cost_governance_final_audit_path": str(H5_AUDIT_PATH),
            "thought_gate_final_audit_path": str(H1_AUDIT_PATH),
        },
        "governance_guards": governance_guards,
        "governed_observation_summary": {
            "analysis_mode": governed_observation.get("analysis_mode"),
            "market_regime": governed_observation.get("market_regime"),
            "action_bias": governed_observation.get("action_bias"),
            "confidence_0_to_1": governed_observation.get("confidence_0_to_1"),
            "edge_assessment_bps": governed_observation.get("edge_assessment_bps"),
        },
        "lease_schema_definition": lease_schema_definition,
        "lease_template": lease_template,
        "schema_runtime_view": schema_runtime_view,
        "warning_flags": warning_flags,
        "blocking_reasons": blocking_reasons,
        "schema_state": schema_state,
        "allow_progress_to_i1b_final_audit": schema_ok,
        "recommended_action": (
            "may_progress_to_i1b_final_audit"
            if schema_ok else
            "inspect_i1a_decision_lease_schema_blockers"
        ),
        "operator_message": (
            "I1-A decision lease schema ready. 当前仅完成 lease schema 建模，不发放 execution lease。"
            if schema_ok else
            "I1-A decision lease schema blocked."
        ),
    }

    write_report(PREFIX, report)


if __name__ == "__main__":
    main()
