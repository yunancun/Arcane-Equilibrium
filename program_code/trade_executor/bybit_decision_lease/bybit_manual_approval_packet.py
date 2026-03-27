#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
I8 / Manual Approval Packet
I8 / 人工审批封装层

Purpose / 目的
--------------
把当前 thought-gate、lease shadow、authority aggregation 的结果，
整理成一个 review-only 的审批包，供后续人工确认使用。

Important / 重要约束
--------------------
- 本阶段只生成 review packet，不发放 live execution authority
- 不允许把此文件视为执行授权
- 仍然必须保持 read_only / disabled / not_granted
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List
from bybit_decision_lease_common import read_json, save_report, as_list, merged_unique

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")

I7_AGG_PATH = BASE / "bybit_execution_authority_aggregator_latest.json"
I7_AUDIT_PATH = BASE / "bybit_execution_authority_aggregator_final_audit_latest.json"
H1_GOV_PATH = BASE / "bybit_ai_governed_decision_latest.json"
I2_SHADOW_PATH = BASE / "bybit_decision_lease_shadow_latest.json"
I5_FRICTION_PATH = BASE / "bybit_decision_lease_friction_latest.json"

LATEST_PATH = BASE / "bybit_manual_approval_packet_latest.json"


def first_not_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def main() -> None:
    now_ms = int(time.time() * 1000)

    i7_agg = read_json(I7_AGG_PATH)
    i7_audit = read_json(I7_AUDIT_PATH) or {}
    h1_gov = read_json(H1_GOV_PATH)
    i2_shadow = read_json(I2_SHADOW_PATH) or {}
    i5_friction = read_json(I5_FRICTION_PATH) or {}

    source_errors: List[str] = []
    if i7_agg is None:
        source_errors.append("i7_execution_authority_aggregator_missing_or_invalid")
    if h1_gov is None:
        source_errors.append("h1_governed_decision_missing_or_invalid")

    i7_summary = (i7_agg or {}).get("request_summary") or {}
    i7_authority_model = (i7_agg or {}).get("authority_model") or {}
    i7_guards = (i7_agg or {}).get("governance_guards") or {}
    i7_view = (i7_agg or {}).get("aggregated_authority_view") or {}
    h1_observation = (h1_gov or {}).get("governed_observation") or {}

    audit_summary = i7_audit.get("audit_summary") or {}
    i7_stage_closed = bool(audit_summary.get("i7_stage_closed", False))

    current_ttl_ms = first_not_none(
        ((i5_friction.get("decision_output") or {}).get("current_ttl_ms")),
        ((i2_shadow.get("shadow_issue_view") or {}).get("ttl_ms")),
        ((i2_shadow.get("lease_shadow_view") or {}).get("ttl_ms")),
    )
    recommended_ttl_ms = first_not_none(
        ((i5_friction.get("decision_output") or {}).get("recommended_ttl_ms")),
        ((i5_friction.get("adaptive_ttl_view") or {}).get("recommended_ttl_ms")),
    )
    recommended_consume_slack_ms = first_not_none(
        ((i5_friction.get("decision_output") or {}).get("recommended_consume_slack_ms")),
        ((i2_shadow.get("shadow_issue_view") or {}).get("consume_slack_ms")),
        ((i2_shadow.get("lease_shadow_view") or {}).get("consume_slack_ms")),
    )
    latency_ms = first_not_none(
        ((i5_friction.get("metrics_view") or {}).get("latency_ms")),
        ((i5_friction.get("friction_metrics") or {}).get("latency_ms")),
    )

    packet_for_review_only = True
    approval_submit_live = False

    operator_review_required = bool(i7_guards.get("operator_review_required", True))
    execution_authority = i7_guards.get("execution_authority", "unknown")

    packet_ok = (len(source_errors) == 0) and i7_stage_closed and bool(h1_gov.get("decision_ok", False))

    operator_checklist = [
        "确认 system_mode 仍为 read_only，execution_state 仍为 disabled。",
        "确认当前 packet 仅用于人工审批与记录，不代表 live execution permission。",
        "确认 AI 输出仅为 governed observation，action_bias 不能直接等价为下单指令。",
        "确认 execution_authority 仍为 not_granted，live grant 未开启。",
        "确认如未来要进入 live path，必须额外经过独立授权与新鲜度检查。",
    ]

    packet_runtime_view = {
        "packet_for_review_only": packet_for_review_only,
        "approval_submit_live": approval_submit_live,
        "operator_review_required": operator_review_required,
        "execution_authority": execution_authority,
        "live_execution_allowed": bool(i7_guards.get("live_execution_allowed", False)),
        "decision_lease_emitted": bool(i7_guards.get("decision_lease_emitted", False)),
        "shadow_authority_only": bool(i7_authority_model.get("shadow_authority_only", True)),
    }

    manual_review_packet = {
        "packet_mode": "review_only_shadow",
        "candidate_summary": {
            "analysis_mode": h1_observation.get("analysis_mode"),
            "market_regime": h1_observation.get("market_regime"),
            "action_bias": h1_observation.get("action_bias"),
            "confidence_0_to_1": h1_observation.get("confidence_0_to_1"),
            "edge_assessment_bps": h1_observation.get("edge_assessment_bps"),
            "key_reasons": h1_observation.get("key_reasons"),
            "risk_notes": h1_observation.get("risk_notes"),
            "why_not_trade": h1_observation.get("why_not_trade"),
        },
        "authority_snapshot": {
            "policy_guard_passed": i7_view.get("policy_guard_passed"),
            "operator_review_required": i7_view.get("operator_review_required"),
            "operator_review_status": i7_view.get("operator_review_status"),
            "execution_authority_required": i7_view.get("execution_authority_required"),
            "execution_authority": i7_view.get("execution_authority"),
            "execution_authority_granted": i7_view.get("execution_authority_granted"),
            "lease_emit_allowed_now": i7_view.get("lease_emit_allowed_now"),
            "decision_lease_emitted": i7_view.get("decision_lease_emitted"),
            "live_execution_allowed": i7_view.get("live_execution_allowed"),
        },
        "lease_shadow_snapshot": {
            "current_ttl_ms": current_ttl_ms,
            "recommended_ttl_ms": recommended_ttl_ms,
            "recommended_consume_slack_ms": recommended_consume_slack_ms,
            "latency_ms": latency_ms,
        },
        "operator_checklist": operator_checklist,
    }

    blocking_reasons: List[str] = list(source_errors)
    if not i7_stage_closed:
        blocking_reasons.append("i7_stage_not_closed")
    if not bool(h1_gov.get("decision_ok", False)):
        blocking_reasons.append("h1_governed_decision_not_ready")

    if packet_ok:
        packet_state = "manual_approval_packet_shadow_ready_soft_warn"
        allow_progress_to_i9_operator_ack = True
        recommended_action = "may_progress_to_i9_operator_ack"
    else:
        packet_state = "manual_approval_packet_blocked"
        allow_progress_to_i9_operator_ack = False
        recommended_action = "inspect_i8_manual_approval_packet_blockers"

    warning_flags = merged_unique(
        (i7_agg or {}).get("warning_flags"),
        (i2_shadow or {}).get("warning_flags"),
        (i5_friction or {}).get("warning_flags"),
        [
            "manual_approval_packet_review_only_mode",
            "manual_approval_packet_live_submit_inactive",
            "operator_review_pending" if operator_review_required else None,
            "execution_authority_not_granted" if execution_authority != "granted" else None,
        ],
    )

    report: Dict[str, Any] = {
        "packet_type": "bybit_manual_approval_packet",
        "packet_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "I8",
        "packet_ok": packet_ok,
        "source_refs": {
            "i7_execution_authority_aggregator_path": str(I7_AGG_PATH),
            "i7_execution_authority_aggregator_final_audit_path": str(I7_AUDIT_PATH),
            "h1_governed_decision_path": str(H1_GOV_PATH),
            "i2_decision_lease_shadow_path": str(I2_SHADOW_PATH),
            "i5_decision_lease_friction_path": str(I5_FRICTION_PATH),
        },
        "source_integrity": {
            "i7_execution_authority_aggregator_present": i7_agg is not None,
            "h1_governed_decision_present": h1_gov is not None,
            "source_errors": source_errors,
        },
        "request_summary": {
            "provider_target": i7_summary.get("provider_target"),
            "model_name": i7_summary.get("model_name"),
            "selected_ai_tier": i7_summary.get("selected_ai_tier"),
            "route_plan": i7_summary.get("route_plan"),
        },
        "packet_runtime_view": packet_runtime_view,
        "manual_review_packet": manual_review_packet,
        "blocking_reasons": blocking_reasons,
        "warning_flags": warning_flags,
        "packet_state": packet_state,
        "allow_progress_to_i9_operator_ack": allow_progress_to_i9_operator_ack,
        "recommended_action": recommended_action,
        "operator_message": (
            "I8 manual approval packet built. Packet is review-only and does not grant live execution authority."
            if packet_ok else
            "I8 manual approval packet blocked."
        ),
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))
    save_report(report, LATEST_PATH)


if __name__ == "__main__":
    main()
