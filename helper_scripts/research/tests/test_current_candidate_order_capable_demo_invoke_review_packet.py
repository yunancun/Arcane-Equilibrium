from __future__ import annotations

import copy
import datetime as dt
import json
import sys

from cost_gate_learning_lane import bounded_probe_active_order_wiring_contract as wiring
from cost_gate_learning_lane import (
    current_candidate_order_capable_demo_invoke_review_packet as mod,
)


NOW = dt.datetime(2026, 7, 1, 4, 0, tzinfo=dt.timezone.utc)
GEN = dt.datetime(2026, 7, 1, 3, 55, tzinfo=dt.timezone.utc)
SIDE_CELL = "grid_trading|ETHUSDT|Buy"


def _candidate() -> dict:
    return {
        "side_cell_key": SIDE_CELL,
        "strategy_name": "grid_trading",
        "symbol": "ETHUSDT",
        "side": "Buy",
        "outcome_horizon_minutes": 60,
    }


def _active_order_contract(**overrides) -> dict:
    payload = {
        "schema_version": wiring.ACTIVE_ORDER_WIRING_CONTRACT_SCHEMA_VERSION,
        "generated_at_utc": GEN.isoformat(),
        "status": wiring.READY_STATUS,
        "candidate": _candidate(),
        "source_contract": {
            "all_requirements_present": True,
            "missing_requirements": [],
        },
        "answers": {
            "source_contract_ready_for_e3_bb_review": True,
            "active_order_submission_ready": True,
            "source_patch_required": False,
            "active_runtime_order_authority": False,
            "active_runtime_probe_authority": False,
            "order_authority_granted": False,
            "probe_authority_granted": False,
            "order_submission_performed": False,
            "pg_write_performed": False,
            "runtime_mutation_performed": False,
            "live_authority_granted": False,
            "main_cost_gate_adjustment": "NONE",
            "promotion_proof": False,
        },
    }
    payload.update(overrides)
    return payload


def _standing_auth(**overrides) -> dict:
    payload = {
        "schema_version": "standing_demo_operator_authorization_v1",
        "generated_at_utc": GEN.isoformat(),
        "status": "STANDING_DEMO_AUTHORIZATION_ACTIVE",
        "demo_only": True,
        "environment": "demo",
        "expires_at_utc": "2026-07-01T09:02:17.250395+00:00",
        "candidate": _candidate(),
        "answers": {
            "demo_only": True,
            "candidate_scoping_required": True,
            "active_runtime_order_authority": False,
            "active_runtime_probe_authority": False,
            "order_authority_granted": False,
            "probe_authority_granted": False,
            "order_submission_performed": False,
            "runtime_mutation_performed": False,
            "live_authority_granted": False,
            "main_cost_gate_adjustment": "NONE",
            "promotion_proof": False,
        },
    }
    payload.update(overrides)
    return payload


def _soak_plan(**overrides) -> dict:
    payload = {
        "schema_version": "cost_gate_demo_learning_lane_plan_v1",
        "generated_at_utc": GEN.isoformat(),
        "status": "READY_FOR_DEMO_LEARNING_PROBE",
        "main_cost_gate_adjustment": "NONE",
        "order_authority": "DEMO_LEARNING_PROBE_GRANTED",
        "operator_authorization": {
            "schema_version": "bounded_demo_probe_operator_authorization_v1",
            "status": "BOUNDED_DEMO_PROBE_AUTHORIZED",
            "side_cell_key": SIDE_CELL,
            "expires_at_utc": "2026-07-01T09:02:17.250395+00:00",
            "max_authorized_probe_orders": 2,
            "main_cost_gate_adjustment": "NONE",
            "order_authority_granted": True,
            "probe_authority_granted": True,
            "promotion_evidence": False,
        },
        "probe_candidates": [
            {
                **_candidate(),
                "guardrails": {
                    "demo_only": True,
                    "max_demo_notional_usdt_per_order": 954.18759777,
                    "main_cost_gate_adjustment": "NONE",
                    "placement_mode": "buy_near_touch_post_only_at_or_below_best_bid",
                },
            }
        ],
    }
    payload.update(overrides)
    return payload


def _renewed_manifest(**overrides) -> dict:
    payload = {
        "schema_version": "renewed_active_bbo_execution_manifest_v1",
        "generated_at_utc": GEN.isoformat(),
        "state_transition": "DONE_WITH_CONCERNS",
        "candidate": SIDE_CELL,
        "active_status": "CURRENT_CANDIDATE_ACTUAL_ADMISSION_BBO_LEASE_WINDOW_DONE_NO_ORDER",
        "e3_decision": "APPROVE_WITH_CONDITIONS",
        "bb_decision": "APPROVE_WITH_CONDITIONS",
        "phase_a_request_count": 3,
        "phase_b_request_count": 3,
        "active_window": {
            "lease_id": "lease:36701be74236",
            "lease_scope": "TRADE_ENTRY",
            "lease_ttl_seconds": 5.0,
            "release_ok": True,
            "lease_released_before_artifact": True,
        },
        "active_answers": {
            "bybit_call_performed": True,
            "bybit_public_market_data_call_performed": True,
            "public_quote_capture_performed": True,
            "decision_lease_acquire_performed": True,
            "decision_lease_release_performed": True,
            "governance_lease_mutation_performed": True,
            "fresh_actual_admission_bbo_and_gate_ready_during_window": True,
            "gate_evidence_ready_during_active_window": True,
            "lease_released_before_artifact": True,
            "order_submission_performed": False,
            "order_cancel_performed": False,
            "order_modify_performed": False,
            "bybit_private_call_performed": False,
            "pg_write_performed": False,
            "runtime_mutation_performed": False,
            "service_restart_performed": False,
            "cost_gate_lowering_performed": False,
            "live_authority_granted": False,
            "mainnet_authority_granted": False,
            "main_cost_gate_adjustment": "NONE",
            "promotion_proof": False,
        },
        "post_governance_summary": {
            "lease_count": 0,
            "lease_live_count": 0,
            "risk_level": "NORMAL",
            "position_size_multiplier": 1.0,
        },
    }
    payload.update(overrides)
    return payload


def _fill_scan(**overrides) -> dict:
    payload = {
        "candidate": SIDE_CELL,
        "candidate_matched_actual_order_fill_evidence_present": False,
    }
    payload.update(overrides)
    return payload


def _packet(**overrides) -> dict:
    kwargs = {
        "active_order_contract": _active_order_contract(),
        "standing_demo_authorization": _standing_auth(),
        "bounded_demo_soak_plan": _soak_plan(),
        "renewed_active_bbo_manifest": _renewed_manifest(),
        "strict_order_fill_scan": _fill_scan(),
        "now_utc": NOW,
        "source_head": "8cc4284d66487279a453076159f57a8cb22474b3",
        "runtime_head": "e16d3323cb58a549262f6bfa6f1ef48ca140aea0",
    }
    kwargs.update(overrides)
    return mod.build_order_capable_demo_invoke_review_packet(**kwargs)


def test_ready_packet_keeps_order_submission_denied() -> None:
    packet = _packet()

    assert packet["status"] == mod.READY_STATUS
    assert packet["candidate"]["side_cell_key"] == SIDE_CELL
    assert packet["loss_control_blockers"] == []
    assert packet["authority_boundary_violations"] == []
    assert packet["answers"]["review_packet_ready"] is True
    assert packet["answers"]["approval_granted_by_this_packet"] is False
    assert packet["answers"]["order_submission_allowed_by_this_packet"] is False
    assert packet["requested_scope"]["future_phase_c_conditional_single_bounded_demo_order"][
        "allowed_by_this_packet"
    ] is False
    assert packet["reviews"]["bounded_demo_soak_plan"][
        "materialized_order_authority_is_input_only"
    ] is True


def test_expired_standing_auth_blocks_review_packet() -> None:
    packet = _packet(
        standing_demo_authorization=_standing_auth(
            expires_at_utc="2026-07-01T04:05:00+00:00"
        )
    )

    assert packet["status"] == mod.BLOCKED_BY_LOSS_CONTROL_STATUS
    assert "standing_demo_auth_expired_or_too_close_to_expiry" in packet[
        "loss_control_blockers"
    ]
    assert packet["answers"]["review_packet_ready"] is False


def test_source_contract_authority_contamination_fails_closed() -> None:
    contract = _active_order_contract()
    contract["answers"]["order_submission_performed"] = True

    packet = _packet(active_order_contract=contract)

    assert packet["status"] == mod.AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert "active_order_contract_order_submission_performed_not_false" in packet[
        "authority_boundary_violations"
    ]
    assert packet["answers"]["order_submission_allowed_by_this_packet"] is False


def test_renewed_manifest_order_or_private_contamination_fails_closed() -> None:
    manifest = _renewed_manifest()
    manifest["active_answers"]["bybit_private_call_performed"] = True
    manifest["active_answers"]["order_submission_performed"] = True

    packet = _packet(renewed_active_bbo_manifest=manifest)

    assert packet["status"] == mod.AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert "renewed_active_bbo_bybit_private_call_performed_not_false" in packet[
        "authority_boundary_violations"
    ]
    assert "renewed_active_bbo_order_submission_performed_not_false" in packet[
        "authority_boundary_violations"
    ]


def test_existing_candidate_matched_fill_evidence_blocks_new_invoke_packet() -> None:
    packet = _packet(
        strict_order_fill_scan=_fill_scan(
            candidate_matched_actual_order_fill_evidence_present=True
        )
    )

    assert packet["status"] == mod.BLOCKED_BY_LOSS_CONTROL_STATUS
    assert "candidate_matched_order_fill_evidence_already_present_review_first" in packet[
        "loss_control_blockers"
    ]


def test_missing_source_contract_timestamp_blocks_freshness_gate() -> None:
    contract = _active_order_contract()
    contract.pop("generated_at_utc")

    packet = _packet(active_order_contract=contract)

    assert packet["status"] == mod.BLOCKED_BY_LOSS_CONTROL_STATUS
    assert "active_order_contract_generated_at_missing_or_invalid" in packet[
        "loss_control_blockers"
    ]


def test_invalid_renewed_manifest_timestamp_blocks_freshness_gate() -> None:
    manifest = _renewed_manifest(generated_at_utc="not-a-timestamp")

    packet = _packet(renewed_active_bbo_manifest=manifest)

    assert packet["status"] == mod.BLOCKED_BY_LOSS_CONTROL_STATUS
    assert "renewed_active_bbo_manifest_generated_at_missing_or_invalid" in packet[
        "loss_control_blockers"
    ]


def test_output_authority_checker_catches_packet_scope_aliases() -> None:
    assert (
        mod._check_output_authority(
            {
                "requested_scope": {
                    "review_packet_itself": {"order_endpoint_allowed": True}
                }
            }
        )
        == "$.requested_scope.review_packet_itself.order_endpoint_allowed"
    )
    assert (
        mod._check_output_authority(
            {
                "requested_scope": {
                    "future_phase_c_conditional_single_bounded_demo_order": {
                        "allowed_by_this_packet": True
                    }
                }
            }
        )
        == "$.requested_scope.future_phase_c_conditional_single_bounded_demo_order.allowed_by_this_packet"
    )


def test_cli_writes_packet_and_markdown(tmp_path, monkeypatch) -> None:
    active_path = tmp_path / "active_order_contract.json"
    auth_path = tmp_path / "standing_auth.json"
    plan_path = tmp_path / "soak_plan.json"
    renewed_path = tmp_path / "renewed_manifest.json"
    scan_path = tmp_path / "fill_scan.json"
    output_json = tmp_path / "request.json"
    output_md = tmp_path / "request.md"
    active_path.write_text(json.dumps(_active_order_contract()), encoding="utf-8")
    auth_path.write_text(json.dumps(_standing_auth()), encoding="utf-8")
    plan_path.write_text(json.dumps(_soak_plan()), encoding="utf-8")
    renewed_path.write_text(json.dumps(_renewed_manifest()), encoding="utf-8")
    scan_path.write_text(json.dumps(_fill_scan()), encoding="utf-8")

    argv = [
        "current_candidate_order_capable_demo_invoke_review_packet",
        "--active-order-contract-json",
        str(active_path),
        "--standing-demo-authorization-json",
        str(auth_path),
        "--bounded-demo-soak-plan-json",
        str(plan_path),
        "--renewed-active-bbo-manifest-json",
        str(renewed_path),
        "--strict-order-fill-scan-json",
        str(scan_path),
        "--now-utc",
        NOW.isoformat(),
        "--json-output",
        str(output_json),
        "--output",
        str(output_md),
    ]
    monkeypatch.setattr(sys, "argv", copy.deepcopy(argv))

    assert mod.main() == 0
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    assert packet["status"] == mod.READY_STATUS
    assert "Order submission allowed by this packet: `False`" in output_md.read_text(
        encoding="utf-8"
    )
