from __future__ import annotations

import datetime as dt

from cost_gate_learning_lane import (
    current_candidate_active_decision_lease_gate_window as mod,
)


NOW = dt.datetime(2026, 6, 27, 7, 15, tzinfo=dt.timezone.utc)
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
        "schema_version": mod.gate_evidence.ADMISSION_REVIEW_SCHEMA_VERSION,
        "generated_at_utc": NOW.isoformat(),
        "status": mod.gate_evidence.ADMISSION_REVIEW_BLOCKED_STATUS,
        "candidate": _candidate(),
        "source_blockers": [],
        "authority_contamination_reasons": [],
        "risk_semantics": {
            "gui_risk_config_is_source_of_truth": True,
            "gui_p1_risk_trade_pct": 10.0,
            "per_trade_risk_pct_fraction": 0.1,
            "position_size_max_pct": 25.0,
            "resolved_cap_usdt": 955.24342626,
            "rounded_notional_usdt": 668.304,
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
                "rounded_notional_usdt": 668.304,
                "rounded_qty": 102.0,
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


def _gate_packet(**overrides) -> dict:
    payload = {
        "schema_version": mod.lease_validation.GATE_PACKET_SCHEMA_VERSION,
        "generated_at_utc": NOW.isoformat(),
        "status": mod.lease_validation.GATE_BLOCKED_STATUS,
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
        "schema_version": mod.lease_validation.SIZING_PROPOSAL_SCHEMA_VERSION,
        "generated_at_utc": NOW.isoformat(),
        "status": mod.lease_validation.SIZING_READY_STATUS,
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


def _status_payload(lease_count: int) -> dict:
    return {
        "enabled": True,
        "mode": "Normal",
        "risk_level": "Normal",
        "auth_effective_count": 2,
        "auth_pending_approval": 0,
        "lease_live_count": lease_count,
        "oms_active_count": 0,
    }


def _risk_state_payload() -> dict:
    return {
        "level": "Normal",
        "new_entries_allowed": True,
        "position_size_multiplier": 1.0,
        "reduce_only": False,
        "active_de_risking": False,
        "emergency_stops": False,
        "requires_operator": False,
    }


def test_dry_run_validates_source_without_acquiring_lease() -> None:
    packet = mod.build_current_candidate_active_decision_lease_gate_window(
        admission_review=_admission_review(),
        gate_packet=_gate_packet(),
        sizing_proposal=_sizing_proposal(),
        run=False,
        now_utc=NOW,
    )

    assert packet["status"] == mod.DRY_RUN_READY_STATUS
    assert packet["source_blockers"] == []
    assert packet["answers"]["governance_lease_mutation_performed"] is False
    assert packet["answers"]["decision_lease_acquire_performed"] is False
    assert packet["risk_context"]["resolved_cap_usdt"] == 955.24342626
    assert packet["risk_context"]["single_position_budget_usdt"] == 2388.10856564


def test_explicit_run_validates_gate_during_active_window_then_releases() -> None:
    calls: list[str] = []

    async def dispatcher(method: str, params: dict, timeout: float) -> dict | list:  # noqa: ARG001
        calls.append(method)
        if method == "governance.acquire_lease":
            return {"lease_id": "lease:test-active", "outcome": "Active"}
        if method == "governance.get_status":
            return _status_payload(lease_count=1)
        if method == "governance.list_leases":
            return [
                {
                    "lease_id": "lease:test-active",
                    "state": "ACTIVE",
                    "scope": "TRADE_ENTRY",
                    "environment": "demo",
                    "demo_only": True,
                    "expires_at_utc": "2026-06-27T07:20:00+00:00",
                }
            ]
        if method == "governance.get_risk_state":
            return _risk_state_payload()
        if method == "governance.release_lease":
            return {"ok": True}
        raise AssertionError(method)

    packet = mod.build_current_candidate_active_decision_lease_gate_window(
        admission_review=_admission_review(),
        gate_packet=_gate_packet(),
        sizing_proposal=_sizing_proposal(),
        run=True,
        require_env=False,
        now_utc=NOW,
        dispatcher=dispatcher,
    )

    assert packet["status"] == mod.DONE_STATUS
    assert packet["runtime_blockers"] == []
    assert calls[0] == "governance.acquire_lease"
    assert calls[-1] == "governance.release_lease"
    assert packet["answers"]["decision_lease_acquire_performed"] is True
    assert packet["answers"]["decision_lease_release_performed"] is True
    assert packet["answers"]["runtime_admission_ready_after_release"] is False
    assert packet["answers"]["order_submission_performed"] is False
    nested = packet["active_window_gate_evidence"]
    assert nested["status"] == mod.gate_evidence.READY_NO_ORDER_STATUS
    assert nested["decision_lease_gate_artifact"]["valid_for_current_candidate"] is True
    assert nested["guardian_risk_gate_artifact"]["valid_for_current_candidate"] is True
    leases = packet["active_runtime_governance_snapshot"]["methods"][
        "governance.list_leases"
    ]["result"]
    assert leases[0]["candidate"]["side_cell_key"] == SIDE_CELL
    assert leases[0]["metadata"]["metadata_enriched_by_helper"] is True


def test_source_contamination_blocks_before_acquire() -> None:
    calls: list[str] = []

    async def dispatcher(method: str, params: dict, timeout: float) -> dict:  # noqa: ARG001
        calls.append(method)
        raise AssertionError("dispatcher should not be called")

    gate = _gate_packet(
        answers={
            "runtime_admission_ready": False,
            "order_admission_ready": True,
            "decision_lease_acquire_performed": False,
            "decision_lease_release_performed": False,
            "order_submission_performed": False,
            "runtime_mutation_performed": False,
            "main_cost_gate_adjustment": "NONE",
            "live_authority_granted": False,
        }
    )
    packet = mod.build_current_candidate_active_decision_lease_gate_window(
        admission_review=_admission_review(),
        gate_packet=gate,
        sizing_proposal=_sizing_proposal(),
        run=True,
        require_env=False,
        now_utc=NOW,
        dispatcher=dispatcher,
    )

    assert packet["status"] == mod.SOURCE_NOT_READY_STATUS
    assert "source_preflight_authority_boundary_violation" in packet["source_blockers"]
    assert packet["answers"]["decision_lease_acquire_performed"] is False
    assert calls == []


def test_release_failure_blocks_runtime_result() -> None:
    async def dispatcher(method: str, params: dict, timeout: float) -> dict | list:  # noqa: ARG001
        if method == "governance.acquire_lease":
            return {"lease_id": "lease:test-active", "outcome": "Active"}
        if method == "governance.get_status":
            return _status_payload(lease_count=1)
        if method == "governance.list_leases":
            return [{"lease_id": "lease:test-active", "state": "ACTIVE"}]
        if method == "governance.get_risk_state":
            return _risk_state_payload()
        if method == "governance.release_lease":
            return {"ok": False}
        raise AssertionError(method)

    packet = mod.build_current_candidate_active_decision_lease_gate_window(
        admission_review=_admission_review(),
        gate_packet=_gate_packet(),
        sizing_proposal=_sizing_proposal(),
        run=True,
        require_env=False,
        now_utc=NOW,
        dispatcher=dispatcher,
    )

    assert packet["status"] == mod.BLOCKED_BY_RUNTIME_STATUS
    assert "lease_release_failed" in packet["runtime_blockers"]
    assert packet["answers"]["decision_lease_acquire_performed"] is True
    assert packet["answers"]["decision_lease_release_performed"] is False
    assert packet["answers"]["order_submission_performed"] is False
