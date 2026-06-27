from __future__ import annotations

import datetime as dt

from cost_gate_learning_lane import (
    current_candidate_decision_lease_guardian_gate_evidence as mod,
)


NOW = dt.datetime(2026, 6, 27, 4, 40, tzinfo=dt.timezone.utc)
GEN = dt.datetime(2026, 6, 27, 4, 39, tzinfo=dt.timezone.utc)
SIDE_CELL = "grid_trading|AVAXUSDT|Sell"


def _candidate(**overrides) -> dict:
    payload = {
        "side_cell_key": SIDE_CELL,
        "strategy_name": "grid_trading",
        "symbol": "AVAXUSDT",
        "side": "Sell",
        "outcome_horizon_minutes": 60,
    }
    payload.update(overrides)
    return payload


def _admission_review(**overrides) -> dict:
    payload = {
        "schema_version": mod.ADMISSION_REVIEW_SCHEMA_VERSION,
        "generated_at_utc": GEN.isoformat(),
        "status": mod.ADMISSION_REVIEW_BLOCKED_STATUS,
        "candidate": _candidate(),
        "source_blockers": [],
        "authority_contamination_reasons": [],
        "risk_semantics": {
            "gui_risk_config_is_source_of_truth": True,
            "gui_p1_risk_trade_pct": 10.0,
            "per_trade_risk_pct_fraction": 0.1,
            "position_size_max_pct": 25.0,
            "resolved_cap_usdt": 955.24342626,
            "rounded_notional_usdt": 954.6264,
            "local_10_usdt_cap_is_global_risk_authority": False,
            "bounded_probe_local_cap_usdt_is_authority": False,
        },
        "admission_envelope_preview": {
            "candidate": _candidate(),
            "risk_limits": {
                "per_order_cap_usdt": 955.24342626,
                "per_trade_risk_pct_fraction": 0.1,
                "per_trade_risk_pct_display": 10.0,
                "position_size_max_pct": 25.0,
            },
            "order_shape": {
                "rounded_notional_usdt": 954.6264,
                "rounded_qty": 145.7,
                "limit_price": 6.552,
            },
            "runtime_admission_ready": False,
            "order_admission_ready": False,
        },
        "answers": {
            "review_contract_ready": True,
            "runtime_admission_ready": False,
            "order_admission_ready": False,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "order_authority_granted": False,
            "probe_authority_granted": False,
            "order_submission_performed": False,
            "runtime_mutation_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "live_authority_granted": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
    }
    payload.update(overrides)
    return payload


def _sizing_proposal(**overrides) -> dict:
    payload = {
        "schema_version": mod.SIZING_PROPOSAL_SCHEMA_VERSION,
        "generated_at_utc": GEN.isoformat(),
        "status": mod.SIZING_PROPOSAL_READY_STATUS,
        "candidate": _candidate(),
        "source_blockers": [],
        "authority_contamination_reasons": [],
        "risk_context": {
            "gui_risk_config_is_source_of_truth": True,
            "risk_source_of_truth": "GUI-backed Rust RiskConfig",
            "cap_source": "current_candidate_envelope.cap_resolution.resolved_cap_usdt",
            "account_equity_usdt": 9552.43426257,
            "gui_resolved_cap_usdt": 955.24342626,
            "per_trade_risk_pct_fraction": 0.1,
            "per_trade_risk_pct_display": 10.0,
            "position_size_max_pct": 25.0,
            "single_position_budget_usdt": 2388.10856564,
            "guardian_risk_level": "CAUTIOUS",
            "guardian_position_size_multiplier": 0.7,
            "guardian_adjusted_cap_usdt": 668.67039838,
            "original_rounded_notional_usdt": 954.6264,
            "local_10_usdt_cap_is_global_risk_authority": False,
        },
        "sizing_proposal": {
            "limit_price": 6.552,
            "qty_step": 0.1,
            "min_notional": 5.0,
            "max_qty_under_guardian_cap": 102.0,
            "max_qty_under_effective_cap": 102.0,
            "single_position_budget_usdt": 2388.10856564,
            "effective_single_order_cap_usdt": 668.67039838,
            "proposed_rounded_qty": 102.0,
            "proposed_rounded_notional_usdt": 668.304,
            "original_rounded_qty": 145.7,
            "original_rounded_notional_usdt": 954.6264,
            "notional_lte_guardian_adjusted_cap": True,
            "notional_lte_gui_resolved_cap": True,
            "notional_lte_single_position_budget": True,
            "notional_lte_effective_single_order_cap": True,
            "notional_gte_min_notional": True,
            "runtime_admission_ready": False,
            "order_admission_ready": False,
        },
        "answers": {
            "review_contract_ready": True,
            "runtime_admission_ready": False,
            "order_admission_ready": False,
            "decision_lease_acquire_performed": False,
            "decision_lease_release_performed": False,
            "order_submission_performed": False,
            "runtime_mutation_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "live_authority_granted": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
    }
    payload.update(overrides)
    return payload


def _snapshot(
    *,
    risk_level: str = "Normal",
    lease_list: list[dict] | None = None,
    multiplier: float = 1.0,
    new_entries_allowed: bool = True,
    answers: dict | None = None,
    nested_constraints: bool = False,
) -> dict:
    base_answers = {
        "runtime_readonly_ipc_call_performed": True,
        "decision_lease_acquire_performed": False,
        "decision_lease_release_performed": False,
        "order_submission_performed": False,
        "runtime_mutation_performed": False,
        "live_authority_granted": False,
        "main_cost_gate_adjustment": "NONE",
    }
    if answers:
        base_answers.update(answers)
    leases = lease_list if lease_list is not None else []
    risk_result = {
        "level": risk_level,
        "new_entries_allowed": new_entries_allowed,
        "position_size_multiplier": multiplier,
        "reduce_only": False,
        "active_de_risking": False,
        "emergency_stops": False,
        "requires_operator": False,
    }
    if nested_constraints:
        risk_result = {
            "level": risk_level,
            "constraints": {
                "new_entries_allowed": new_entries_allowed,
                "position_size_multiplier": multiplier,
                "reduce_only": False,
                "active_de_risking": False,
                "emergency_stops": False,
                "requires_operator": False,
            },
        }
    return {
        "schema_version": mod.RUNTIME_GOVERNANCE_IPC_SNAPSHOT_SCHEMA_VERSION,
        "generated_at_utc": GEN.isoformat(),
        "status": "RUNTIME_GOVERNANCE_IPC_READONLY_SNAPSHOT_READY",
        "methods": {
            "governance.get_status": {
                "ok": True,
                "result": {
                    "enabled": True,
                    "mode": "Normal",
                    "risk_level": risk_level,
                    "auth_effective_count": 2,
                    "auth_pending_approval": 0,
                    "lease_live_count": len(leases),
                    "oms_active_count": 0,
                },
            },
            "governance.list_leases": {"ok": True, "result": leases},
            "governance.get_risk_state": {
                "ok": True,
                "result": risk_result,
            },
        },
        "answers": base_answers,
    }


def _active_lease(**overrides) -> dict:
    payload = {
        "lease_id": "lease-current-avax",
        "state": "ACTIVE",
        "candidate": _candidate(),
        "scope": "demo_api_only_bounded_probe",
        "environment": "demo",
        "demo_only": True,
        "expires_at_utc": "2026-06-27T04:50:00+00:00",
    }
    payload.update(overrides)
    return payload


def _packet(**overrides) -> dict:
    kwargs = {
        "admission_review": _admission_review(),
        "runtime_governance_snapshot": _snapshot(),
        "now_utc": NOW,
    }
    kwargs.update(overrides)
    return mod.build_current_candidate_decision_lease_guardian_gate_evidence(**kwargs)


def test_cautious_risk_with_proposed_sizing_removes_notional_breach_only() -> None:
    packet = _packet(
        sizing_proposal=_sizing_proposal(),
        runtime_governance_snapshot=_snapshot(
            risk_level="Cautious",
            multiplier=0.7,
            lease_list=[],
            nested_constraints=True,
        ),
    )

    assert packet["status"] == mod.BLOCKED_BY_LOSS_CONTROL_STATUS
    assert packet["risk_context"]["sizing_source"] == "guardian_adjusted_sizing_proposal"
    assert packet["risk_context"]["single_position_budget_usdt"] == 2388.10856564
    assert packet["risk_context"]["effective_single_order_cap_usdt"] == 668.67039838
    assert packet["risk_context"]["rounded_qty"] == 102.0
    assert packet["risk_context"]["rounded_notional_usdt"] == 668.304
    guardian = packet["guardian_risk_gate_artifact"]
    assert guardian["sizing_source"] == "guardian_adjusted_sizing_proposal"
    assert guardian["risk_limits"]["rounded_qty"] == 102.0
    assert guardian["risk_limits"]["single_position_budget_usdt"] == 2388.10856564
    assert guardian["risk_limits"]["effective_single_order_cap_usdt"] == 668.67039838
    assert guardian["risk_limits"]["rounded_notional_usdt"] == 668.304
    assert guardian["risk_limits"]["original_rounded_notional_usdt"] == 954.6264
    assert guardian["risk_limits"]["rounded_notional_lte_guardian_adjusted_cap"] is True
    assert "guardian_risk_state_not_normal" in guardian["blocking_reasons"]
    assert "rounded_notional_exceeds_guardian_adjusted_cap" not in guardian[
        "blocking_reasons"
    ]
    assert "decision_lease_valid" in packet["runtime_admission_blockers"]
    assert "guardian_risk_gate_valid" in packet["runtime_admission_blockers"]
    assert packet["answers"]["decision_lease_acquire_performed"] is False
    assert packet["answers"]["order_submission_performed"] is False


def test_empty_lease_list_and_cautious_risk_blocks_with_adjusted_cap() -> None:
    packet = _packet(
        runtime_governance_snapshot=_snapshot(
            risk_level="Cautious",
            multiplier=0.7,
            lease_list=[],
            nested_constraints=True,
        )
    )

    assert packet["status"] == mod.BLOCKED_BY_LOSS_CONTROL_STATUS
    assert packet["runtime_admission_blockers"] == [
        "decision_lease_valid",
        "guardian_risk_gate_valid",
    ]
    decision = packet["decision_lease_gate_artifact"]
    guardian = packet["guardian_risk_gate_artifact"]
    assert decision["status"] == mod.DECISION_LEASE_NOT_READY_STATUS
    assert "decision_lease_missing" in decision["blocking_reasons"]
    assert "lease_live_count_zero" in decision["blocking_reasons"]
    assert guardian["status"] == mod.GUARDIAN_RISK_GATE_NOT_READY_STATUS
    assert guardian["risk_level"] == "CAUTIOUS"
    assert round(guardian["risk_limits"]["guardian_adjusted_cap_usdt"], 12) == 668.670398382
    assert "guardian_risk_state_not_normal" in guardian["blocking_reasons"]
    assert "rounded_notional_exceeds_guardian_adjusted_cap" in guardian[
        "blocking_reasons"
    ]
    assert packet["answers"]["decision_lease_acquire_performed"] is False
    assert packet["answers"]["order_submission_performed"] is False


def test_active_matching_demo_lease_and_normal_guardian_emit_pass_artifacts() -> None:
    packet = _packet(
        runtime_governance_snapshot=_snapshot(
            risk_level="Normal",
            multiplier=1.0,
            lease_list=[_active_lease()],
        )
    )

    assert packet["status"] == mod.READY_NO_ORDER_STATUS
    assert packet["runtime_admission_blockers"] == []
    decision = packet["decision_lease_gate_artifact"]
    guardian = packet["guardian_risk_gate_artifact"]
    assert decision["schema_version"] == mod.DECISION_LEASE_GATE_SCHEMA_VERSION
    assert decision["status"] == mod.DECISION_LEASE_ACTIVE_STATUS
    assert decision["valid_for_current_candidate"] is True
    assert decision["decision_lease_acquire_performed"] is False
    assert guardian["schema_version"] == mod.GUARDIAN_RISK_GATE_SCHEMA_VERSION
    assert guardian["status"] == mod.GUARDIAN_RISK_GATE_PASS_STATUS
    assert guardian["valid_for_current_candidate"] is True
    assert guardian["cap_usdt"] == 955.24342626
    assert packet["answers"]["runtime_admission_ready"] is False
    assert packet["answers"]["order_admission_ready"] is False


def test_authority_contamination_in_input_blocks_evidence_packet() -> None:
    admission = _admission_review(
        answers={
            "review_contract_ready": True,
            "runtime_admission_ready": False,
            "order_admission_ready": False,
            "order_submission_performed": True,
        }
    )

    packet = _packet(
        admission_review=admission,
        runtime_governance_snapshot=_snapshot(lease_list=[_active_lease()]),
    )

    assert packet["status"] == mod.AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert any(
        reason.endswith("answers.order_submission_performed_true")
        for reason in packet["authority_contamination_reasons"]
    )
    assert packet["answers"]["runtime_admission_ready"] is False
    assert packet["answers"]["order_admission_ready"] is False


def test_mismatched_lease_candidate_does_not_clear_decision_gate() -> None:
    packet = _packet(
        runtime_governance_snapshot=_snapshot(
            lease_list=[
                _active_lease(
                    candidate=_candidate(
                        side_cell_key="grid_trading|ETHUSDT|Buy",
                        symbol="ETHUSDT",
                        side="Buy",
                    )
                )
            ],
        )
    )

    assert packet["status"] == mod.BLOCKED_BY_LOSS_CONTROL_STATUS
    decision = packet["decision_lease_gate_artifact"]
    assert decision["valid_for_current_candidate"] is False
    assert "current_candidate_active_demo_decision_lease_missing" in decision[
        "blocking_reasons"
    ]
    assert decision["examined_leases"][0]["candidate_matches"] is False
