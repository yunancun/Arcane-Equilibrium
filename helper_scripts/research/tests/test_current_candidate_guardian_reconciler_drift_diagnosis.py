from __future__ import annotations

import datetime as dt

from cost_gate_learning_lane import (
    current_candidate_guardian_reconciler_drift_diagnosis as mod,
)


NOW = dt.datetime(2026, 6, 27, 6, 25, tzinfo=dt.timezone.utc)
GEN = dt.datetime(2026, 6, 27, 6, 24, tzinfo=dt.timezone.utc)
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
        "generated_at_utc": GEN.isoformat(),
        "status": mod.GATE_BLOCKED_STATUS,
        "candidate": _candidate(),
        "source_blockers": [],
        "authority_contamination_reasons": [],
        "runtime_admission_blockers": [
            "decision_lease_valid",
            "guardian_risk_gate_valid",
        ],
        "risk_context": {
            "gui_risk_config_is_source_of_truth": True,
            "sizing_source": "guardian_adjusted_sizing_proposal",
            "account_equity_usdt": 9552.43426257,
            "resolved_cap_usdt": 955.24342626,
            "single_position_budget_usdt": 2388.10856564,
            "effective_single_order_cap_usdt": 668.67039838,
            "guardian_adjusted_cap_usdt_from_proposal": 668.67039838,
            "rounded_qty": 102.0,
            "rounded_notional_usdt": 668.304,
            "per_trade_risk_pct_fraction": 0.1,
            "per_trade_risk_pct_display": 10.0,
            "position_size_max_pct": 25.0,
        },
        "answers": {
            "review_contract_ready": True,
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
            "promotion_evidence": False,
            "promotion_proof": False,
        },
    }
    payload.update(overrides)
    return payload


def _snapshot(
    *,
    risk_level: str = "Cautious",
    multiplier: float = 0.7,
    leases: list[dict] | None = None,
    transitions_tail: list[dict] | None = None,
    generated_at: dt.datetime = GEN,
    answers: dict | None = None,
) -> dict:
    lease_list = leases if leases is not None else []
    base_answers = {
        "runtime_readonly_ipc_call_performed": True,
        "decision_lease_acquire_performed": False,
        "decision_lease_release_performed": False,
        "order_submission_performed": False,
        "runtime_mutation_performed": False,
        "pg_write_performed": False,
        "service_restart_performed": False,
        "global_cost_gate_lowering_recommended": False,
        "live_authority_granted": False,
        "main_cost_gate_adjustment": "NONE",
    }
    if answers:
        base_answers.update(answers)
    if transitions_tail is None:
        transitions_tail = [
            {
                "from": "Cautious",
                "to": "Normal",
                "event": "reconciler_recovery",
                "initiator": "Reconciler",
                "reason_codes": ["reconciler_auto_recovery"],
                "timestamp_utc": "2026-06-27T06:20:00+00:00",
            },
            {
                "from": "Normal",
                "to": "Cautious",
                "event": "reconciler_drift",
                "initiator": "Reconciler",
                "reason_codes": ["reconciler_drift"],
                "timestamp_utc": "2026-06-27T06:22:00+00:00",
            },
        ]
    return {
        "schema_version": mod.RUNTIME_GOVERNANCE_IPC_SNAPSHOT_SCHEMA_VERSION,
        "generated_at_utc": generated_at.isoformat(),
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
                    "lease_live_count": len(lease_list),
                    "oms_active_count": 0,
                },
            },
            "governance.list_leases": {"ok": True, "result": lease_list},
            "governance.get_risk_state": {
                "ok": True,
                "result": {
                    "level": risk_level,
                    "constraints": {
                        "new_entries_allowed": True,
                        "reduce_only": False,
                        "active_de_risking": False,
                        "requires_operator": False,
                        "emergency_stops": False,
                        "position_size_multiplier": multiplier,
                    },
                    "held_ms": 99_234_385,
                    "transitions_tail": transitions_tail,
                },
            },
        },
        "answers": base_answers,
    }


def _active_lease(**overrides) -> dict:
    payload = {
        "lease_id": "lease-current-avax",
        "state": "ACTIVE",
        "candidate": _candidate(),
        "scope": "TRADE_ENTRY",
        "environment": "demo",
        "demo_only": True,
        "expires_at_utc": "2026-06-27T06:30:00+00:00",
    }
    payload.update(overrides)
    return payload


def _packet(**overrides) -> dict:
    kwargs = {
        "gate_packet": _gate_packet(),
        "runtime_governance_snapshot": _snapshot(),
        "now_utc": NOW,
    }
    kwargs.update(overrides)
    return mod.build_current_candidate_guardian_reconciler_drift_diagnosis(**kwargs)


def test_cautious_reconciler_drift_blocks_loss_control_with_gui_cap_lineage() -> None:
    packet = _packet()

    assert packet["status"] == mod.BLOCKED_BY_LOSS_CONTROL_STATUS
    assert packet["source_blockers"] == []
    assert packet["authority_contamination_reasons"] == []
    assert "guardian_risk_state_not_normal" in packet["runtime_blockers"]
    assert "guardian_reconciler_drift_active" in packet["runtime_blockers"]
    assert "reconciler_drift_after_recovery" in packet["runtime_blockers"]
    assert "active_decision_lease_missing" in packet["runtime_blockers"]
    assert packet["risk_context"]["resolved_cap_usdt"] == 955.24342626
    assert packet["risk_context"]["per_trade_risk_pct_fraction"] == 0.1
    assert packet["risk_context"]["per_trade_risk_pct_display"] == 10.0
    assert packet["risk_context"]["effective_single_order_cap_usdt"] == 668.67039838
    assert packet["answers"]["runtime_admission_ready"] is False
    assert packet["answers"]["order_submission_performed"] is False


def test_gui_ten_percent_must_resolve_from_equity_not_ten_usdt() -> None:
    gate = _gate_packet()
    gate["risk_context"]["resolved_cap_usdt"] = 10.0
    gate["risk_context"]["effective_single_order_cap_usdt"] = 10.0

    packet = _packet(gate_packet=gate)

    assert packet["status"] == mod.NOT_READY_STATUS
    assert "gui_resolved_cap_not_equity_times_per_trade_pct" in packet[
        "source_blockers"
    ]
    assert "resolved_cap_equals_gui_display_percent_not_usdt_budget" in packet[
        "source_blockers"
    ]
    assert packet["answers"]["order_authority_granted"] is False


def test_normal_snapshot_with_active_lease_is_ready_no_order() -> None:
    packet = _packet(
        runtime_governance_snapshot=_snapshot(
            risk_level="Normal",
            multiplier=1.0,
            leases=[_active_lease()],
            transitions_tail=[
                {
                    "from": "Cautious",
                    "to": "Normal",
                    "event": "reconciler_recovery",
                    "initiator": "Reconciler",
                    "reason_codes": ["reconciler_auto_recovery"],
                    "timestamp_utc": "2026-06-27T06:20:00+00:00",
                }
            ],
        )
    )

    assert packet["status"] == mod.READY_NO_ORDER_STATUS
    assert packet["runtime_blockers"] == []
    assert packet["answers"]["order_admission_ready"] is False


def test_runtime_authority_contamination_blocks_before_diagnosis() -> None:
    packet = _packet(
        runtime_governance_snapshot=_snapshot(
            answers={"order_submission_performed": True}
        )
    )

    assert packet["status"] == mod.AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert any(
        reason.endswith("answers.order_submission_performed_true")
        for reason in packet["authority_contamination_reasons"]
    )
    assert packet["answers"]["runtime_mutation_performed"] is False


def test_stale_runtime_snapshot_is_source_not_ready() -> None:
    stale_generated_at = NOW - dt.timedelta(minutes=10)
    packet = _packet(
        runtime_governance_snapshot=_snapshot(generated_at=stale_generated_at)
    )

    assert packet["status"] == mod.NOT_READY_STATUS
    assert "runtime_governance_snapshot_not_fresh" in packet["source_blockers"]
    assert packet["answers"]["decision_lease_acquire_performed"] is False
