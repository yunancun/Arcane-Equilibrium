from __future__ import annotations

import datetime as dt

from cost_gate_learning_lane import (
    current_candidate_decision_lease_no_order_validation as mod,
)


NOW = dt.datetime(2026, 6, 27, 6, 10, tzinfo=dt.timezone.utc)
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


def _gate_packet(**overrides) -> dict:
    payload = {
        "schema_version": mod.GATE_PACKET_SCHEMA_VERSION,
        "generated_at_utc": NOW.isoformat(),
        "status": mod.GATE_BLOCKED_STATUS,
        "candidate": _candidate(),
        "runtime_admission_blockers": [
            "decision_lease_valid",
            "guardian_risk_gate_valid",
        ],
        "source_blockers": [],
        "authority_contamination_reasons": [],
        "risk_context": {
            "gui_risk_config_is_source_of_truth": True,
            "sizing_source": "guardian_adjusted_sizing_proposal",
            "account_equity_usdt": 9552.43426257,
            "resolved_cap_usdt": 955.24342626,
            "single_position_budget_usdt": 2388.10856564,
            "effective_single_order_cap_usdt": 668.67039838,
            "rounded_qty": 102.0,
            "rounded_notional_usdt": 668.304,
            "per_trade_risk_pct_fraction": 0.1,
            "per_trade_risk_pct_display": 10.0,
            "position_size_max_pct": 25.0,
        },
        "answers": {
            "runtime_admission_ready": False,
            "order_admission_ready": False,
            "decision_lease_acquire_performed": False,
            "decision_lease_release_performed": False,
            "decision_lease_emitted": False,
            "order_submission_performed": False,
            "runtime_mutation_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "live_authority_granted": False,
        },
    }
    payload.update(overrides)
    return payload


def _sizing_proposal(**overrides) -> dict:
    payload = {
        "schema_version": mod.SIZING_PROPOSAL_SCHEMA_VERSION,
        "generated_at_utc": NOW.isoformat(),
        "status": mod.SIZING_READY_STATUS,
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
            "guardian_adjusted_cap_usdt": 668.67039838,
            "local_10_usdt_cap_is_global_risk_authority": False,
        },
        "sizing_proposal": {
            "proposed_rounded_qty": 102.0,
            "proposed_rounded_notional_usdt": 668.304,
            "single_position_budget_usdt": 2388.10856564,
            "effective_single_order_cap_usdt": 668.67039838,
            "notional_lte_guardian_adjusted_cap": True,
            "notional_lte_gui_resolved_cap": True,
            "notional_lte_single_position_budget": True,
            "notional_lte_effective_single_order_cap": True,
            "notional_gte_min_notional": True,
            "runtime_admission_ready": False,
            "order_admission_ready": False,
        },
        "answers": {
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


def test_dry_run_validates_gui_derived_sizing_without_mutation() -> None:
    packet = mod.build_current_candidate_decision_lease_no_order_validation(
        gate_packet=_gate_packet(),
        sizing_proposal=_sizing_proposal(),
        run=False,
        now_utc=NOW,
    )

    assert packet["status"] == mod.DRY_RUN_READY_STATUS
    assert packet["source_blockers"] == []
    assert packet["answers"]["governance_lease_mutation_performed"] is False
    assert packet["answers"]["decision_lease_acquire_performed"] is False
    assert packet["answers"]["order_submission_performed"] is False
    assert packet["risk_context"]["single_position_budget_usdt"] == 2388.10856564
    assert packet["risk_context"]["effective_single_order_cap_usdt"] == 668.67039838


def test_explicit_run_acquires_releases_and_requires_no_residual_lease() -> None:
    calls: list[tuple[str, dict]] = []

    async def dispatcher(method: str, params: dict, timeout: float) -> dict:  # noqa: ARG001
        calls.append((method, dict(params)))
        if method == "governance.acquire_lease":
            return {"lease_id": "lease:test-avax", "outcome": "Active"}
        if method == "governance.get_lease":
            get_count = sum(1 for call_method, _ in calls if call_method == method)
            if get_count == 1:
                return {
                    "lease_id": "lease:test-avax",
                    "state": "ACTIVE",
                    "scope": "TRADE_ENTRY",
                }
            return {}
        if method == "governance.release_lease":
            return {"ok": True}
        raise AssertionError(method)

    packet = mod.build_current_candidate_decision_lease_no_order_validation(
        gate_packet=_gate_packet(),
        sizing_proposal=_sizing_proposal(),
        run=True,
        require_env=False,
        now_utc=NOW,
        dispatcher=dispatcher,
    )

    assert packet["status"] == mod.DONE_STATUS
    assert packet["runtime_blockers"] == []
    assert packet["answers"]["governance_lease_mutation_performed"] is True
    assert packet["answers"]["decision_lease_acquire_performed"] is True
    assert packet["answers"]["decision_lease_release_performed"] is True
    assert packet["answers"]["lease_released_before_artifact"] is True
    assert packet["answers"]["runtime_admission_ready"] is False
    assert packet["answers"]["order_admission_ready"] is False
    assert packet["decision_lease_validation"]["released_outcome"] == "Failed"
    release_call = [params for method, params in calls if method == "governance.release_lease"][0]
    assert release_call["outcome"] == "Failed"


def test_residual_lease_after_release_blocks_runtime_validation() -> None:
    async def dispatcher(method: str, params: dict, timeout: float) -> dict:  # noqa: ARG001
        if method == "governance.acquire_lease":
            return {"lease_id": "lease:test-avax", "outcome": "Active"}
        if method == "governance.get_lease":
            return {"lease_id": "lease:test-avax", "state": "ACTIVE"}
        if method == "governance.release_lease":
            return {"ok": True}
        raise AssertionError(method)

    packet = mod.build_current_candidate_decision_lease_no_order_validation(
        gate_packet=_gate_packet(),
        sizing_proposal=_sizing_proposal(),
        run=True,
        require_env=False,
        now_utc=NOW,
        dispatcher=dispatcher,
    )

    assert packet["status"] == mod.BLOCKED_BY_RUNTIME_STATUS
    assert "lease_still_fetchable_after_release" in packet["runtime_blockers"]
    assert packet["answers"]["order_submission_performed"] is False


def test_authority_contamination_blocks_before_mutating_lease() -> None:
    gate = _gate_packet(
        answers={
            "runtime_admission_ready": False,
            "order_admission_ready": True,
            "order_submission_performed": False,
            "runtime_mutation_performed": False,
            "main_cost_gate_adjustment": "NONE",
        }
    )

    packet = mod.build_current_candidate_decision_lease_no_order_validation(
        gate_packet=gate,
        sizing_proposal=_sizing_proposal(),
        run=True,
        require_env=False,
        now_utc=NOW,
    )

    assert packet["status"] == mod.AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert any(
        reason.endswith("answers.order_admission_ready_true")
        for reason in packet["authority_contamination_reasons"]
    )
    assert packet["answers"]["governance_lease_mutation_performed"] is False


def test_effective_cap_must_match_min_gui_single_position_guardian() -> None:
    proposal = _sizing_proposal()
    proposal["sizing_proposal"]["effective_single_order_cap_usdt"] = 955.24342626

    packet = mod.build_current_candidate_decision_lease_no_order_validation(
        gate_packet=_gate_packet(),
        sizing_proposal=proposal,
        run=False,
        now_utc=NOW,
    )

    assert packet["status"] == mod.SOURCE_NOT_READY_STATUS
    assert "sizing_proposal_effective_cap_mismatch_gate_packet" in packet["source_blockers"]
    assert "effective_cap_not_min_of_gui_single_position_guardian" in packet[
        "source_blockers"
    ]
