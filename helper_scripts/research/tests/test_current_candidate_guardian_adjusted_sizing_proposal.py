from __future__ import annotations

import datetime as dt

from cost_gate_learning_lane import (
    current_candidate_guardian_adjusted_sizing_proposal as mod,
)


NOW = dt.datetime(2026, 6, 27, 5, 15, tzinfo=dt.timezone.utc)
GEN = dt.datetime(2026, 6, 27, 5, 10, tzinfo=dt.timezone.utc)
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
            "account_equity_usdt": 9552.43426257,
            "bounded_probe_local_cap_usdt_is_authority": False,
            "cap_source": "current_candidate_envelope.cap_resolution.resolved_cap_usdt",
            "gui_p1_risk_trade_pct": 10.0,
            "gui_percent_semantics": (
                "GUI 10.0% means per_trade_risk_pct=0.1; local 10 USDT "
                "bounded-probe diagnostics cannot become runtime admission cap"
            ),
            "gui_risk_config_is_source_of_truth": True,
            "local_10_usdt_cap_is_global_risk_authority": False,
            "per_trade_risk_pct_fraction": 0.1,
            "position_size_max_pct": 25.0,
            "resolved_cap_usdt": 955.24342626,
            "rounded_notional_usdt": 954.6264,
        },
        "admission_envelope_preview": {
            "candidate": _candidate(),
            "risk_limits": {
                "account_equity_usdt": 9552.43426257,
                "bounded_probe_local_cap_usdt_is_authority": False,
                "cap_source": "current_candidate_envelope.cap_resolution.resolved_cap_usdt",
                "local_10_usdt_cap_is_global_risk_authority": False,
                "per_order_cap_usdt": 955.24342626,
                "per_trade_risk_pct_display": 10.0,
                "per_trade_risk_pct_fraction": 0.1,
                "position_size_max_pct": 25.0,
                "risk_source_of_truth": "GUI-backed Rust RiskConfig",
                "single_position_budget_usdt": 2388.10856564,
            },
            "order_shape": {
                "limit_price": 6.552,
                "notional_lte_gui_resolved_cap": True,
                "placement_mode": "sell_near_touch_post_only_at_or_above_best_ask",
                "rounded_notional_usdt": 954.6264,
                "rounded_qty": 145.7,
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
            "bounded_demo_probe_authorized": False,
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


def _gate_evidence(
    *,
    adjusted_cap_usdt: float = 668.6703983819999,
    guardian_risk_level: str = "CAUTIOUS",
    candidate: dict | None = None,
    **overrides,
) -> dict:
    payload = {
        "schema_version": mod.GATE_EVIDENCE_SCHEMA_VERSION,
        "generated_at_utc": GEN.isoformat(),
        "status": mod.GATE_EVIDENCE_BLOCKED_STATUS,
        "candidate": candidate or _candidate(),
        "guardian_risk_gate_artifact": {
            "schema_version": "current_candidate_guardian_risk_gate_evidence_v1",
            "generated_at_utc": GEN.isoformat(),
            "status": "GUARDIAN_RISK_GATE_NOT_READY",
            "source": "runtime_governance_ipc_readonly_snapshot",
            "environment": "demo",
            "candidate": candidate or _candidate(),
            "risk_level": guardian_risk_level,
            "new_entries_allowed": True,
            "reduce_only": False,
            "active_de_risking": False,
            "requires_operator": False,
            "emergency_stops": False,
            "position_size_multiplier": 0.7,
            "effective_position_size_multiplier": 0.7,
            "cap_usdt": adjusted_cap_usdt,
            "risk_limits": {
                "gui_resolved_cap_usdt": 955.24342626,
                "guardian_adjusted_cap_usdt": adjusted_cap_usdt,
                "rounded_notional_usdt": 954.6264,
                "rounded_notional_lte_guardian_adjusted_cap": False,
            },
            "blocking_reasons": [
                "guardian_risk_state_not_normal",
                "rounded_notional_exceeds_guardian_adjusted_cap",
            ],
            "valid_for_current_candidate": False,
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
        },
    }
    payload.update(overrides)
    return payload


def _construction_preview(**overrides) -> dict:
    payload = {
        "schema_version": mod.CONSTRUCTION_PREVIEW_SCHEMA_VERSION,
        "generated_at_utc": GEN.isoformat(),
        "status": mod.CONSTRUCTION_PREVIEW_READY_STATUS,
        "candidate": _candidate(),
        "construction": {
            "best_ask": 6.552,
            "best_bid": 6.551,
            "blocking_reasons": [],
            "cap_usdt": 955.24342626,
            "constructible": True,
            "limit_price": 6.552,
            "min_notional": 5.0,
            "placement_mode": "sell_near_touch_post_only_at_or_above_best_ask",
            "qty_step": 0.1,
            "reference_price": 6.551,
            "rounded_notional_usdt": 954.6264,
            "rounded_qty": 145.7,
            "tick_size": 0.001,
        },
        "answers": {
            "bybit_call_performed": True,
            "bybit_public_market_data_call_performed": True,
            "network_call_performed": True,
            "order_submission_performed": False,
            "runtime_mutation_performed": False,
            "order_admission_ready": False,
        },
    }
    payload.update(overrides)
    return payload


def _packet(**overrides) -> dict:
    kwargs = {
        "admission_review": _admission_review(),
        "gate_evidence": _gate_evidence(),
        "construction_preview": _construction_preview(),
        "now_utc": NOW,
        "source_head": "source-sha",
        "runtime_head": "runtime-sha",
    }
    kwargs.update(overrides)
    return mod.build_current_candidate_guardian_adjusted_sizing_proposal(**kwargs)


def test_ready_proposal_uses_gui_percent_cap_then_guardian_multiplier() -> None:
    packet = _packet()
    sizing = packet["sizing_proposal"]
    risk = packet["risk_context"]

    assert packet["schema_version"] == mod.SCHEMA_VERSION
    assert packet["status"] == mod.READY_STATUS
    assert packet["blocking_gates"] == []
    assert risk["gui_risk_config_is_source_of_truth"] is True
    assert risk["risk_source_of_truth"] == "GUI-backed Rust RiskConfig"
    assert risk["cap_source"] == "current_candidate_envelope.cap_resolution.resolved_cap_usdt"
    assert risk["account_equity_usdt"] == 9552.43426257
    assert risk["per_trade_risk_pct_fraction"] == 0.1
    assert risk["per_trade_risk_pct_display"] == 10.0
    assert risk["position_size_max_pct"] == 25.0
    assert risk["single_position_budget_usdt"] == 2388.10856564
    assert (
        risk["effective_single_order_cap_basis"]
        == "min(gui_per_trade_cap_usdt, gui_max_single_position_budget_usdt, guardian_adjusted_cap_usdt)"
    )
    assert risk["gui_resolved_cap_usdt"] == 955.24342626
    assert risk["guardian_adjusted_cap_usdt"] == 668.67039838
    assert risk["local_10_usdt_cap_is_global_risk_authority"] is False
    assert sizing["original_rounded_qty"] == 145.7
    assert sizing["original_rounded_notional_usdt"] == 954.6264
    assert sizing["single_position_budget_usdt"] == 2388.10856564
    assert sizing["effective_single_order_cap_usdt"] == 668.67039838
    assert sizing["max_qty_under_effective_cap"] == 102.0
    assert sizing["proposed_rounded_qty"] == 102.0
    assert sizing["proposed_rounded_notional_usdt"] == 668.304
    assert sizing["notional_lte_guardian_adjusted_cap"] is True
    assert sizing["notional_lte_gui_resolved_cap"] is True
    assert sizing["notional_lte_single_position_budget"] is True
    assert sizing["notional_lte_effective_single_order_cap"] is True
    assert sizing["notional_gte_min_notional"] is True
    assert sizing["runtime_admission_ready"] is False
    assert sizing["order_admission_ready"] is False
    assert packet["answers"]["decision_lease_acquire_performed"] is False
    assert packet["answers"]["order_submission_performed"] is False
    assert "guardian_risk_gate_valid_for_proposed_sizing" in packet[
        "required_next_gates_before_order_capable_action"
    ]


def test_normal_guardian_proposal_uses_current_gui_cap_without_forced_reduction() -> None:
    gate = _gate_evidence(
        adjusted_cap_usdt=955.24342626,
        guardian_risk_level="NORMAL",
    )
    gate["guardian_risk_gate_artifact"].update(
        {
            "status": "GUARDIAN_RISK_GATE_PASS",
            "risk_level": "NORMAL",
            "position_size_multiplier": 1.0,
            "effective_position_size_multiplier": 1.0,
            "cap_usdt": 955.24342626,
            "blocking_reasons": [],
            "valid_for_current_candidate": True,
        }
    )
    gate["guardian_risk_gate_artifact"]["risk_limits"].update(
        {
            "guardian_adjusted_cap_usdt": 955.24342626,
            "rounded_notional_lte_guardian_adjusted_cap": True,
        }
    )

    packet = _packet(gate_evidence=gate)
    sizing = packet["sizing_proposal"]
    risk = packet["risk_context"]

    assert packet["status"] == mod.READY_STATUS
    assert packet["blocking_gates"] == []
    assert risk["guardian_risk_level"] == "NORMAL"
    assert risk["guardian_position_size_multiplier"] == 1.0
    assert risk["gui_resolved_cap_usdt"] == 955.24342626
    assert risk["guardian_adjusted_cap_usdt"] == 955.24342626
    assert sizing["effective_single_order_cap_usdt"] == 955.24342626
    assert sizing["proposed_rounded_qty"] == 145.7
    assert sizing["proposed_rounded_notional_usdt"] == 954.6264
    assert sizing["qty_delta"] == 0.0
    assert sizing["notional_delta_usdt"] == 0.0
    assert sizing["notional_lte_guardian_adjusted_cap"] is True
    assert sizing["notional_lte_gui_resolved_cap"] is True
    assert sizing["notional_lte_single_position_budget"] is True
    assert sizing["notional_lte_effective_single_order_cap"] is True
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["order_submission_performed"] is False


def test_local_ten_usdt_construction_cap_blocks_proposal() -> None:
    construction = _construction_preview(
        construction={
            "cap_usdt": 10.0,
            "constructible": True,
            "limit_price": 6.552,
            "min_notional": 5.0,
            "qty_step": 0.1,
            "rounded_notional_usdt": 9.1728,
            "rounded_qty": 1.4,
            "tick_size": 0.001,
        }
    )

    packet = _packet(construction_preview=construction)

    assert packet["status"] == mod.NOT_READY_STATUS
    assert "admission_risk_cap_mismatch_construction_cap" in packet["source_blockers"]
    assert packet["answers"]["order_admission_ready"] is False


def test_gui_max_single_position_budget_can_be_the_effective_cap() -> None:
    admission = _admission_review()
    admission["risk_semantics"]["position_size_max_pct"] = 6.0
    admission["admission_envelope_preview"]["risk_limits"][
        "position_size_max_pct"
    ] = 6.0
    admission["admission_envelope_preview"]["risk_limits"][
        "single_position_budget_usdt"
    ] = 573.14605575

    packet = _packet(admission_review=admission)
    sizing = packet["sizing_proposal"]

    assert packet["status"] == mod.READY_STATUS
    assert packet["source_blockers"] == []
    assert packet["risk_context"]["single_position_budget_usdt"] == 573.14605575
    assert sizing["effective_single_order_cap_usdt"] == 573.14605575
    assert sizing["proposed_rounded_qty"] == 87.4
    assert sizing["proposed_rounded_notional_usdt"] == 572.6448
    assert sizing["notional_lte_single_position_budget"] is True
    assert sizing["notional_lte_effective_single_order_cap"] is True


def test_gui_risk_fraction_must_not_be_display_percent() -> None:
    admission = _admission_review()
    admission["risk_semantics"]["per_trade_risk_pct_fraction"] = 10.0
    admission["admission_envelope_preview"]["risk_limits"][
        "per_trade_risk_pct_fraction"
    ] = 10.0

    packet = _packet(admission_review=admission)

    assert packet["status"] == mod.NOT_READY_STATUS
    assert "per_trade_risk_pct_fraction_not_fraction" in packet["source_blockers"]
    assert packet["answers"]["order_authority_granted"] is False


def test_guardian_adjusted_cap_below_min_notional_blocks_sizing() -> None:
    packet = _packet(gate_evidence=_gate_evidence(adjusted_cap_usdt=4.0))

    assert packet["status"] == mod.NOT_READY_STATUS
    assert "guardian_adjusted_cap_below_min_executable_notional" in packet[
        "source_blockers"
    ]
    assert "proposed_notional_below_min_notional" in packet["source_blockers"]
    assert packet["answers"]["runtime_admission_ready"] is False


def test_candidate_mismatch_blocks_proposal() -> None:
    packet = _packet(
        gate_evidence=_gate_evidence(
            candidate=_candidate(
                side_cell_key="grid_trading|ETHUSDT|Buy",
                symbol="ETHUSDT",
                side="Buy",
            )
        )
    )

    assert packet["status"] == mod.NOT_READY_STATUS
    assert "candidate_alignment_failed" in packet["source_blockers"]


def test_authority_contamination_blocks_proposal() -> None:
    admission = _admission_review()
    admission["answers"]["order_submission_performed"] = True

    packet = _packet(admission_review=admission)

    assert packet["status"] == mod.AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert any(
        reason.endswith("answers.order_submission_performed_true")
        for reason in packet["authority_contamination_reasons"]
    )
    assert packet["answers"]["order_submission_performed"] is False
