from __future__ import annotations

import copy
import datetime as dt
import hashlib
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
        "risk_cap_lineage": {
            "resolved_cap_usdt": 954.18759458,
            "risk_source_of_truth": "GUI-backed Rust RiskConfig",
        },
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


def _approval_report(tmp_path, role: str, verdict: str = "APPROVE_WITH_CONDITIONS"):
    path = tmp_path / f"{role.lower()}_review.md"
    path.write_text(
        f"STATUS: DONE\nVERDICT: {verdict}\n\n# {role} Review\n",
        encoding="utf-8",
    )
    return path


def _file_sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _compact_renewed_manifest(tmp_path, **overrides) -> tuple[dict, object, object]:
    e3_report = _approval_report(tmp_path, "E3")
    bb_report = _approval_report(tmp_path, "BB")
    payload = {
        "schema_version": "renewed_active_bbo_execution_manifest_v1",
        "generated_at_utc": GEN.isoformat(),
        "state_transition": "DONE_WITH_CONCERNS",
        "candidate": SIDE_CELL,
        "e3_report_sha256": _file_sha256(e3_report),
        "bb_report_sha256": _file_sha256(bb_report),
        "phase_a": {
            "request_count": 3,
            "status": "CURRENT_CANDIDATE_PUBLIC_QUOTE_CONSTRUCTION_REFRESH_READY_NO_ORDER",
        },
        "phase_b": {
            "request_count": 3,
            "status": "CURRENT_CANDIDATE_PUBLIC_QUOTE_CONSTRUCTION_REFRESH_READY_NO_ORDER",
        },
        "active_window": {
            "status": "CURRENT_CANDIDATE_ACTUAL_ADMISSION_BBO_LEASE_WINDOW_DONE_NO_ORDER",
            "lease_id": "lease:36701be74236",
            "actual_admission_bbo_status_during_active_window": "CURRENT_CANDIDATE_PUBLIC_QUOTE_CONSTRUCTION_REFRESH_READY_NO_ORDER",
            "gate_evidence_status_during_active_window": "CURRENT_CANDIDATE_DECISION_LEASE_GUARDIAN_GATE_READY_NO_ORDER",
            "lease_released_before_artifact": True,
        },
        "post_governance": {
            "lease_count": 0,
            "lease_live_count": 0,
            "risk_level": "NORMAL",
            "position_size_multiplier": 1.0,
        },
        "authority_boundary": {
            "order_or_probe_authority_granted": False,
            "private_or_order_endpoint_called": False,
            "db_or_pg_write": False,
            "runtime_config_service_mutation": False,
            "cost_gate_lowering": False,
            "live_or_mainnet": False,
            "proof_or_promotion_claim": False,
        },
    }
    payload.update(overrides)
    return payload, e3_report, bb_report


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
    assert packet["active_blocker_id"] == (
        "P0-CURRENT-CANDIDATE-ORDER-CAPABLE-DEMO-INVOKE-FRESH-WINDOW-RUN-GATE"
    )
    assert packet["next_blocker_id"] == packet["active_blocker_id"]
    assert packet["loss_control_blockers"] == []
    assert packet["authority_boundary_violations"] == []
    assert packet["answers"]["review_packet_ready"] is True
    assert packet["answers"]["approval_granted_by_this_packet"] is False
    assert packet["answers"]["order_submission_allowed_by_this_packet"] is False
    assert packet["requested_scope"]["future_phase_c_conditional_single_bounded_demo_order"][
        "allowed_by_this_packet"
    ] is False
    assert packet["requested_scope"]["future_phase_c_conditional_single_bounded_demo_order"][
        "max_notional_usdt_from_plan"
    ] == 954.18759777
    assert packet["requested_scope"]["future_phase_c_conditional_single_bounded_demo_order"][
        "current_standing_resolved_cap_usdt"
    ] == 954.18759458
    assert packet["requested_scope"]["future_phase_c_conditional_single_bounded_demo_order"][
        "effective_future_order_cap_usdt"
    ] == 954.18759458
    assert packet["reviews"]["bounded_demo_soak_plan"][
        "materialized_order_authority_is_input_only"
    ] is True
    assert packet["requested_scope"]["future_phase_a_public_demo_market_data"][
        "allowed_http_requests_exact"
    ] == [
        "GET /v5/market/time",
        "GET /v5/market/tickers?category=linear&symbol=ETHUSDT",
        "GET /v5/market/instruments-info?category=linear&symbol=ETHUSDT",
    ]


def test_requested_public_market_data_scope_uses_candidate_symbol() -> None:
    side_cell = "ma_crossover|NEARUSDT|Buy"
    candidate = {
        "side_cell_key": side_cell,
        "strategy_name": "ma_crossover",
        "symbol": "NEARUSDT",
        "side": "Buy",
        "outcome_horizon_minutes": 60,
    }
    packet = _packet(
        active_order_contract=_active_order_contract(candidate=candidate),
        standing_demo_authorization=_standing_auth(candidate=candidate),
        bounded_demo_soak_plan=_soak_plan(
            operator_authorization={
                **_soak_plan()["operator_authorization"],
                "side_cell_key": side_cell,
            },
            probe_candidates=[
                {
                    **candidate,
                    "guardrails": {
                        "demo_only": True,
                        "max_demo_notional_usdt_per_order": 954.18759777,
                        "main_cost_gate_adjustment": "NONE",
                        "placement_mode": "buy_near_touch_post_only_at_or_below_best_bid",
                    },
                }
            ],
        ),
        renewed_active_bbo_manifest=_renewed_manifest(candidate=side_cell),
        strict_order_fill_scan=_fill_scan(candidate=side_cell),
    )

    requests = packet["requested_scope"]["future_phase_a_public_demo_market_data"][
        "allowed_http_requests_exact"
    ]
    assert packet["status"] == mod.READY_STATUS
    assert "GET /v5/market/tickers?category=linear&symbol=NEARUSDT" in requests
    assert (
        "GET /v5/market/instruments-info?category=linear&symbol=NEARUSDT"
        in requests
    )
    assert all("ETHUSDT" not in request for request in requests)


def test_compact_renewed_manifest_shape_is_accepted(tmp_path) -> None:
    e3_report = _approval_report(tmp_path, "E3")
    bb_report = _approval_report(tmp_path, "BB")
    packet = _packet(
        e3_approval_report_path=e3_report,
        bb_approval_report_path=bb_report,
        renewed_active_bbo_manifest={
            "schema_version": "renewed_active_bbo_execution_manifest_v1",
            "generated_at_utc": GEN.isoformat(),
            "state_transition": "DONE_WITH_CONCERNS",
            "candidate": SIDE_CELL,
            "e3_report_sha256": _file_sha256(e3_report),
            "bb_report_sha256": _file_sha256(bb_report),
            "phase_a": {
                "request_count": 3,
                "status": "CURRENT_CANDIDATE_PUBLIC_QUOTE_CONSTRUCTION_REFRESH_READY_NO_ORDER",
            },
            "phase_b": {
                "request_count": 3,
                "status": "CURRENT_CANDIDATE_PUBLIC_QUOTE_CONSTRUCTION_REFRESH_READY_NO_ORDER",
            },
            "active_window": {
                "status": "CURRENT_CANDIDATE_ACTUAL_ADMISSION_BBO_LEASE_WINDOW_DONE_NO_ORDER",
                "lease_id": "lease:36701be74236",
                "actual_admission_bbo_status_during_active_window": "CURRENT_CANDIDATE_PUBLIC_QUOTE_CONSTRUCTION_REFRESH_READY_NO_ORDER",
                "gate_evidence_status_during_active_window": "CURRENT_CANDIDATE_DECISION_LEASE_GUARDIAN_GATE_READY_NO_ORDER",
                "lease_released_before_artifact": True,
            },
            "post_governance": {
                "lease_count": 0,
                "lease_live_count": 0,
                "risk_level": "NORMAL",
            },
            "authority_boundary": {
                "order_or_probe_authority_granted": False,
                "private_or_order_endpoint_called": False,
                "db_or_pg_write": False,
                "runtime_config_service_mutation": False,
                "cost_gate_lowering": False,
                "live_or_mainnet": False,
                "proof_or_promotion_claim": False,
            },
        }
    )

    assert packet["status"] == mod.READY_STATUS
    assert packet["reviews"]["renewed_no_order_active_bbo_window"]["blockers"] == []
    assert (
        packet["reviews"]["renewed_no_order_active_bbo_window"]["approval_reports"][
            "E3"
        ]["approved_with_conditions"]
        is True
    )
    assert (
        packet["reviews"]["renewed_no_order_active_bbo_window"]["approval_reports"][
            "BB"
        ]["approved_with_conditions"]
        is True
    )
    assert (
        packet["reviews"]["renewed_no_order_active_bbo_window"][
            "authority_violations"
        ]
        == []
    )


def test_compact_renewed_manifest_sha_without_report_path_blocks(tmp_path) -> None:
    e3_report = _approval_report(tmp_path, "E3")
    bb_report = _approval_report(tmp_path, "BB")
    packet = _packet(
        renewed_active_bbo_manifest={
            **_renewed_manifest(),
            "e3_decision": None,
            "bb_decision": None,
            "e3_report_sha256": _file_sha256(e3_report),
            "bb_report_sha256": _file_sha256(bb_report),
        }
    )

    assert packet["status"] == mod.BLOCKED_BY_LOSS_CONTROL_STATUS
    assert "renewed_active_bbo_e3_report_path_missing" in packet[
        "loss_control_blockers"
    ]
    assert "renewed_active_bbo_bb_report_path_missing" in packet[
        "loss_control_blockers"
    ]


def test_compact_renewed_manifest_active_answer_contamination_fails_closed(
    tmp_path,
) -> None:
    manifest, e3_report, bb_report = _compact_renewed_manifest(
        tmp_path,
        active_answers={"order_submission_performed": True},
    )

    packet = _packet(
        e3_approval_report_path=e3_report,
        bb_approval_report_path=bb_report,
        renewed_active_bbo_manifest=manifest,
    )

    assert packet["status"] == mod.AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert "renewed_active_bbo_order_submission_performed_not_false" in packet[
        "authority_boundary_violations"
    ]


def test_compact_renewed_manifest_operator_auth_authorize_fails_closed(
    tmp_path,
) -> None:
    manifest, e3_report, bb_report = _compact_renewed_manifest(tmp_path)
    manifest["authority_boundary"]["operator_auth_authorize"] = True

    packet = _packet(
        e3_approval_report_path=e3_report,
        bb_approval_report_path=bb_report,
        renewed_active_bbo_manifest=manifest,
    )

    assert packet["status"] == mod.AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert "renewed_active_bbo_operator_auth_authorize_not_false" in packet[
        "authority_boundary_violations"
    ]


def test_compact_renewed_manifest_post_governance_loss_control_blocks(
    tmp_path,
) -> None:
    manifest, e3_report, bb_report = _compact_renewed_manifest(tmp_path)
    manifest["post_governance"]["risk_level"] = "CAUTIOUS"
    manifest["post_governance"]["position_size_multiplier"] = 0.5

    packet = _packet(
        e3_approval_report_path=e3_report,
        bb_approval_report_path=bb_report,
        renewed_active_bbo_manifest=manifest,
    )

    assert packet["status"] == mod.BLOCKED_BY_LOSS_CONTROL_STATUS
    assert "renewed_active_bbo_post_governance_risk_level_not_normal" in packet[
        "loss_control_blockers"
    ]
    assert (
        "renewed_active_bbo_post_governance_position_size_multiplier_not_1"
        in packet["loss_control_blockers"]
    )


def test_side_cell_only_source_candidate_derives_symbol_for_requested_scope() -> None:
    side_cell = "ma_crossover|NEARUSDT|Buy"
    candidate = {
        "side_cell_key": side_cell,
        "strategy_name": "ma_crossover",
        "symbol": "NEARUSDT",
        "side": "Buy",
        "outcome_horizon_minutes": 60,
    }

    packet = _packet(
        active_order_contract=_active_order_contract(
            candidate={"side_cell_key": side_cell}
        ),
        standing_demo_authorization=_standing_auth(candidate=candidate),
        bounded_demo_soak_plan=_soak_plan(
            operator_authorization={
                **_soak_plan()["operator_authorization"],
                "side_cell_key": side_cell,
            },
            probe_candidates=[
                {
                    **candidate,
                    "guardrails": {
                        "demo_only": True,
                        "max_demo_notional_usdt_per_order": 954.18759777,
                        "main_cost_gate_adjustment": "NONE",
                        "placement_mode": "buy_near_touch_post_only_at_or_below_best_bid",
                    },
                }
            ],
        ),
        renewed_active_bbo_manifest=_renewed_manifest(candidate=side_cell),
        strict_order_fill_scan=_fill_scan(candidate=side_cell),
    )

    requests = packet["requested_scope"]["future_phase_a_public_demo_market_data"][
        "allowed_http_requests_exact"
    ]
    assert packet["status"] == mod.READY_STATUS
    assert packet["candidate"]["symbol"] == "NEARUSDT"
    assert "GET /v5/market/tickers?category=linear&symbol=NEARUSDT" in requests
    assert all("UNKNOWN" not in request for request in requests)


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
    assert (
        mod._check_output_authority(
            {"authority_boundary": {"operator_auth_authorize": True}}
        )
        == "$.authority_boundary.operator_auth_authorize"
    )
    assert (
        mod._check_output_authority(
            {"authority_boundary": {"order_or_probe_authority_granted": True}}
        )
        == "$.authority_boundary.order_or_probe_authority_granted"
    )
    assert (
        mod._check_output_authority(
            {"post_governance": {"runtime_mutation_allowed": True}}
        )
        == "$.post_governance.runtime_mutation_allowed"
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
