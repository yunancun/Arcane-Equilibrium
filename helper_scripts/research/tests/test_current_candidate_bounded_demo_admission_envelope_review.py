from __future__ import annotations

import datetime as dt

from cost_gate_learning_lane import (
    current_candidate_bounded_demo_admission_envelope_review as mod,
)


NOW = dt.datetime(2026, 6, 27, 2, 45, tzinfo=dt.timezone.utc)
GEN = dt.datetime(2026, 6, 27, 2, 40, tzinfo=dt.timezone.utc)
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


def _answers(**overrides) -> dict:
    payload = {
        "source_only_research_artifact": True,
        "bounded_demo_probe_authorized": False,
        "operator_authorization_object_emitted": False,
        "decision_lease_emitted": False,
        "active_runtime_probe_authority": False,
        "active_runtime_order_authority": False,
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "bybit_call_performed": False,
        "bybit_private_call_performed": False,
        "bybit_public_market_data_call_performed": False,
        "order_submission_performed": False,
        "order_admission_ready": False,
        "runtime_admission_ready": False,
        "pg_query_performed": False,
        "pg_write_performed": False,
        "runtime_mutation_performed": False,
        "service_restart_performed": False,
        "global_cost_gate_lowering_recommended": False,
        "main_cost_gate_adjustment": "NONE",
        "live_authority_granted": False,
        "promotion_evidence": False,
        "promotion_proof": False,
    }
    payload.update(overrides)
    return payload


def _cap_resolution(**overrides) -> dict:
    payload = {
        "account_equity_artifact_accepted": True,
        "account_equity_artifact_blocking_reasons": [],
        "account_equity_usdt": 9552.43426257,
        "blocking_reasons": [],
        "bounded_probe_local_cap_usdt_is_authority": False,
        "cap_resolved": True,
        "gui_risk_config_is_authority": True,
        "max_order_notional_usdt": 0.0,
        "per_trade_budget_usdt": 955.24342626,
        "per_trade_risk_pct_display": 10.0,
        "per_trade_risk_pct_fraction": 0.1,
        "position_size_max_pct": 25.0,
        "resolved_cap_usdt": 955.24342626,
        "risk_source_of_truth": "GUI-backed Rust RiskConfig",
        "single_position_budget_usdt": 2388.10856564,
        "source": "GUI Risk tab -> Rust RiskConfig limits",
    }
    payload.update(overrides)
    return payload


def _current_envelope(**overrides) -> dict:
    payload = {
        "schema_version": mod.CURRENT_ENVELOPE_SCHEMA_VERSION,
        "generated_at_utc": GEN.isoformat(),
        "status": mod.CURRENT_ENVELOPE_READY_STATUS,
        "candidate": _candidate(),
        "cap_resolution": _cap_resolution(),
        "summary": {
            "current_candidate_no_order_refresh_envelope_ready": True,
            "resolved_cap_usdt": 955.24342626,
            "gui_p1_risk_trade_pct": 10.0,
            "local_10_usdt_cap_is_global_risk_authority": False,
            "network_call_performed": False,
            "order_admission_ready": False,
        },
        "answers": _answers(
            current_candidate_no_order_refresh_envelope_ready=True,
        ),
    }
    payload.update(overrides)
    return payload


def _handoff(**overrides) -> dict:
    payload = {
        "schema_version": mod.HANDOFF_SCHEMA_VERSION,
        "generated_at_utc": GEN.isoformat(),
        "status": mod.HANDOFF_READY_STATUS,
        "reason": "handoff_ready_no_order",
        "candidate": _candidate(),
        "gates": {
            "artifacts_fresh": True,
            "bbo_fresh_at_capture": True,
            "candidate_alignment": True,
            "cap_from_gui_resolved_equity": True,
            "construction_constructible_under_cap": True,
            "handoff_ready_no_order": True,
            "no_authority_contamination": True,
            "order_admission_ready": False,
            "public_quote_public_only": True,
            "runtime_admission_ready": False,
            "schema_status_ready": True,
        },
        "admission_envelope_preview": {
            "schema_version": mod.HANDOFF_PREVIEW_SCHEMA_VERSION,
            "status": "READY_FOR_SEPARATE_RUNTIME_ADMISSION_REVIEW",
            "candidate": _candidate(),
            "sizing": {
                "cap_usdt": 955.24342626,
                "cap_source": mod.GUI_CAP_SOURCE,
                "limit_price": 6.552,
                "rounded_qty": 145.7,
                "rounded_notional_usdt": 954.6264,
                "placement_mode": "sell_near_touch_post_only_at_or_above_best_ask",
            },
            "market": {
                "best_bid": 6.551,
                "best_ask": 6.552,
                "bbo_age_ms_at_capture": 497.462,
                "max_fresh_bbo_age_ms": 1000,
            },
            "required_next_gates": [
                "bounded_demo_authorization_object_required",
                "decision_lease_required",
                "guardian_risk_gate_required",
                "rust_authority_path_required",
                "fresh_bbo_refresh_required_at_actual_order_admission",
            ],
            "runtime_admission_ready": False,
            "order_admission_ready": False,
            "boundary": "preview only; no order/probe/live authority",
        },
        "runtime_admission_blockers": [
            "bounded_demo_authorization_object_required",
            "decision_lease_required",
            "guardian_risk_gate_required",
            "rust_authority_path_required",
            "fresh_bbo_refresh_required_at_actual_order_admission",
        ],
        "blocking_gates": [],
        "answers": _answers(handoff_ready_no_order=True),
    }
    payload.update(overrides)
    return payload


def _review(**overrides) -> dict:
    kwargs = {
        "handoff": _handoff(),
        "current_envelope": _current_envelope(),
        "now_utc": NOW,
    }
    kwargs.update(overrides)
    return mod.build_current_candidate_bounded_demo_admission_envelope_review(
        **kwargs
    )


def _standing_eth_authorization() -> dict:
    return {
        "schema_version": "standing_demo_operator_authorization_v1",
        "generated_at_utc": GEN.isoformat(),
        "status": "STANDING_DEMO_AUTHORIZATION_ACTIVE",
        "standing_authorization_id": "standing-demo-eth",
        "operator_id": "operator-test",
        "environment": "demo",
        "scope": "demo_api_only_bounded_probe",
        "demo_only": True,
        "candidate_scoping_required": True,
        "candidate": {
            "side_cell_key": "grid_trading|ETHUSDT|Buy",
            "strategy_name": "grid_trading",
            "symbol": "ETHUSDT",
            "side": "Buy",
            "outcome_horizon_minutes": 60,
        },
        "max_authorized_probe_orders_per_candidate": 2,
        "expires_at_utc": "2026-06-27T11:12:52+00:00",
        "answers": {
            "demo_only": True,
            "candidate_scoping_required": True,
            "live_authority_granted": False,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "promotion_evidence": False,
        },
    }


def _bounded_authorization() -> dict:
    return {
        "schema_version": mod.BOUNDED_AUTH_PACKET_SCHEMA_VERSION,
        "generated_at_utc": GEN.isoformat(),
        "status": mod.BOUNDED_PROBE_AUTHORIZED_STATUS,
        "candidate": _candidate(),
        "main_cost_gate_adjustment": "NONE",
        "operator_authorization": {
            "schema_version": mod.BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SCHEMA_VERSION,
            "status": mod.BOUNDED_PROBE_AUTHORIZED_STATUS,
            "authorization_id": "auth-current-avax",
            "operator_id": "operator-test",
            "side_cell_key": SIDE_CELL,
            "expires_at_utc": "2026-06-27T03:30:00+00:00",
            "authority_path_readiness_status": mod.AUTHORITY_PATH_PATCH_READY_STATUS,
            "main_cost_gate_adjustment": "NONE",
            "order_authority": mod.ORDER_AUTHORITY_GRANTED,
            "max_authorized_probe_orders": 1,
            "probe_authority_granted": True,
            "order_authority_granted": True,
            "promotion_evidence": False,
        },
        "answers": {
            "bounded_demo_probe_authorized": True,
            "operator_authorization_object_emitted": True,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "live_authority_granted": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
    }


def _decision_lease_gate(**overrides) -> dict:
    payload = {
        "schema_version": mod.DECISION_LEASE_GATE_SCHEMA_VERSION,
        "generated_at_utc": GEN.isoformat(),
        "status": mod.DECISION_LEASE_ACTIVE_STATUS,
        "source": mod.RUNTIME_GOVERNANCE_IPC_SNAPSHOT_SOURCE,
        "environment": "demo",
        "demo_only": True,
        "candidate": _candidate(),
        "lease_id": "lease-current-avax",
        "decision_lease_id": "lease-current-avax",
        "expires_at_utc": "2026-06-27T03:20:00+00:00",
        "blocking_reasons": [],
        "valid_for_current_candidate": True,
        "runtime_admission_ready": False,
        "order_admission_ready": False,
        "decision_lease_acquire_performed": False,
        "decision_lease_release_performed": False,
    }
    payload.update(overrides)
    return payload


def _guardian_risk_gate(**overrides) -> dict:
    payload = {
        "schema_version": mod.GUARDIAN_RISK_GATE_SCHEMA_VERSION,
        "generated_at_utc": GEN.isoformat(),
        "status": mod.GUARDIAN_RISK_GATE_PASS_STATUS,
        "source": mod.RUNTIME_GOVERNANCE_IPC_SNAPSHOT_SOURCE,
        "environment": "demo",
        "candidate": _candidate(),
        "risk_level": "NORMAL",
        "new_entries_allowed": True,
        "reduce_only": False,
        "active_de_risking": False,
        "requires_operator": False,
        "emergency_stops": False,
        "position_size_multiplier": 1.0,
        "effective_position_size_multiplier": 1.0,
        "cap_usdt": 955.24342626,
        "risk_limits": {
            "gui_resolved_cap_usdt": 955.24342626,
            "guardian_adjusted_cap_usdt": 955.24342626,
            "rounded_notional_usdt": 954.6264,
            "rounded_notional_lte_guardian_adjusted_cap": True,
        },
        "blocking_reasons": [],
        "valid_for_current_candidate": True,
        "runtime_admission_ready": False,
        "order_admission_ready": False,
    }
    payload.update(overrides)
    return payload


def _rust_authority_path() -> dict:
    return {
        "schema_version": mod.PATCH_READINESS_SCHEMA_VERSION,
        "generated_at_utc": GEN.isoformat(),
        "status": mod.AUTHORITY_PATH_PATCH_READY_STATUS,
        "candidate": _candidate(),
        "answers": {
            "rust_near_touch_authority_adapter_present": True,
            "rust_authority_path_wiring_present": True,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
        },
    }


def test_gui_cap_lineage_ready_but_runtime_admission_blocked_by_loss_controls() -> None:
    review = _review()

    assert review["schema_version"] == mod.SCHEMA_VERSION
    assert review["status"] == mod.BLOCKED_BY_LOSS_CONTROL_STATUS
    assert review["answers"]["review_contract_ready"] is True
    assert review["answers"]["runtime_admission_ready"] is False
    assert review["answers"]["order_admission_ready"] is False
    assert review["risk_semantics"]["gui_p1_risk_trade_pct"] == 10.0
    assert review["risk_semantics"]["resolved_cap_usdt"] == 955.24342626
    assert review["risk_semantics"]["local_10_usdt_cap_is_global_risk_authority"] is False
    assert (
        review["admission_envelope_preview"]["risk_limits"]["per_order_cap_usdt"]
        == 955.24342626
    )
    assert "bounded_demo_authorization_object_valid" in review["runtime_admission_blockers"]
    assert "decision_lease_valid" in review["runtime_admission_blockers"]
    assert "fresh_bbo_refresh_at_actual_admission" in review["runtime_admission_blockers"]


def test_local_ten_usdt_cap_source_blocks_before_loss_control_review() -> None:
    handoff = _handoff()
    handoff["admission_envelope_preview"]["sizing"]["cap_usdt"] = 10.0
    handoff["admission_envelope_preview"]["sizing"][
        "cap_source"
    ] = "bounded_probe_local_cap_usdt"

    review = _review(handoff=handoff)

    assert review["status"] == mod.NOT_READY_STATUS
    assert "handoff_cap_source_not_gui_resolved_cap" in review["source_blockers"]
    assert "handoff_cap_mismatch_current_envelope_resolved_cap" in review["source_blockers"]
    assert review["answers"]["order_admission_ready"] is False


def test_gui_risk_fraction_must_not_be_display_percent() -> None:
    envelope = _current_envelope(
        cap_resolution=_cap_resolution(per_trade_risk_pct_fraction=10.0)
    )

    review = _review(current_envelope=envelope)

    assert review["status"] == mod.NOT_READY_STATUS
    assert "per_trade_risk_pct_fraction_not_fraction" in review["source_blockers"]
    assert review["answers"]["order_authority_granted"] is False


def test_standing_demo_authorization_candidate_mismatch_is_loss_control_blocker() -> None:
    review = _review(standing_demo_authorization=_standing_eth_authorization())

    assert review["status"] == mod.BLOCKED_BY_LOSS_CONTROL_STATUS
    assert "standing_demo_authorization_valid_if_supplied" in review["runtime_admission_blockers"]
    assert (
        review["standing_demo_authorization"]["valid_for_candidate_scoped_authorization"]
        is False
    )
    assert review["standing_demo_authorization"]["candidate_scope_matches"] is False


def test_authority_contamination_blocks_review() -> None:
    envelope = _current_envelope(
        answers=_answers(
            current_candidate_no_order_refresh_envelope_ready=True,
            order_submission_performed=True,
        )
    )

    review = _review(current_envelope=envelope)

    assert review["status"] == mod.AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert any(
        reason.endswith("answers.order_submission_performed_true")
        for reason in review["authority_contamination_reasons"]
    )
    assert review["answers"]["runtime_admission_ready"] is False


def test_bounded_authorization_input_does_not_override_missing_runtime_gates() -> None:
    review = _review(bounded_authorization=_bounded_authorization())

    assert review["status"] == mod.BLOCKED_BY_LOSS_CONTROL_STATUS
    bounded_gate = {
        gate["name"]: gate["passed"] for gate in review["admission_gates"]
    }["bounded_demo_authorization_object_valid"]
    assert bounded_gate is True
    assert "bounded_demo_authorization_object_valid" not in review["runtime_admission_blockers"]
    assert "decision_lease_valid" in review["runtime_admission_blockers"]
    assert review["answers"]["operator_authorization_object_emitted"] is False
    assert review["answers"]["order_admission_ready"] is False


def test_generic_fake_lease_and_guardian_json_do_not_clear_runtime_gates() -> None:
    review = _review(
        bounded_authorization=_bounded_authorization(),
        decision_lease={
            "generated_at_utc": GEN.isoformat(),
            "status": "ACTIVE",
            "lease_id": "fake-lease",
            "candidate": _candidate(),
            "demo_only": True,
            "expires_at_utc": "2026-06-27T03:20:00+00:00",
            "order_admission_ready": False,
        },
        guardian_risk_gate={
            "generated_at_utc": GEN.isoformat(),
            "status": "PASS",
            "environment": "demo",
            "candidate": _candidate(),
            "cap_usdt": 955.0,
            "order_admission_ready": False,
        },
    )

    assert review["status"] == mod.BLOCKED_BY_LOSS_CONTROL_STATUS
    assert "decision_lease_valid" in review["runtime_admission_blockers"]
    assert "guardian_risk_gate_valid" in review["runtime_admission_blockers"]
    assert review["decision_lease"]["schema_version"] is None
    assert review["decision_lease"]["valid_for_current_candidate"] is False
    assert review["guardian_risk_gate"]["schema_version"] is None
    assert review["guardian_risk_gate"]["valid_for_current_candidate"] is False


def test_schema_gate_evidence_clears_lease_and_guardian_but_fresh_bbo_still_blocks() -> None:
    review = _review(
        bounded_authorization=_bounded_authorization(),
        decision_lease=_decision_lease_gate(),
        guardian_risk_gate=_guardian_risk_gate(),
        rust_authority_path=_rust_authority_path(),
    )

    assert review["status"] == mod.BLOCKED_BY_LOSS_CONTROL_STATUS
    assert review["decision_lease"]["valid_for_current_candidate"] is True
    assert review["guardian_risk_gate"]["valid_for_current_candidate"] is True
    assert review["rust_authority_path"]["valid_for_current_candidate_review"] is True
    assert review["runtime_admission_blockers"] == [
        "fresh_bbo_refresh_at_actual_admission"
    ]
    assert review["answers"]["runtime_admission_ready"] is False
    assert review["answers"]["order_admission_ready"] is False
