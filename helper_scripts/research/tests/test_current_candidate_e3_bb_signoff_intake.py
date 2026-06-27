from __future__ import annotations

import copy
import datetime as dt
import json
import sys

from cost_gate_learning_lane import (
    current_candidate_e3_bb_enablement_review_contract as contract,
)
from cost_gate_learning_lane import current_candidate_e3_bb_signoff_intake as mod
from cost_gate_learning_lane import current_candidate_e3_bb_signoff_request_packet as request
from cost_gate_learning_lane import current_candidate_order_enablement_review as enablement


NOW = dt.datetime(2026, 6, 27, 13, 40, tzinfo=dt.timezone.utc)
GEN = dt.datetime(2026, 6, 27, 13, 35, tzinfo=dt.timezone.utc)
SIDE_CELL = "grid_trading|AVAXUSDT|Sell"


def _order_enablement_review() -> dict:
    return {
        "schema_version": enablement.SCHEMA_VERSION,
        "generated_at_utc": GEN.isoformat(),
        "status": enablement.READY_FOR_E3_BB_STATUS,
        "candidate": {
            "requested_side_cell_key": SIDE_CELL,
            "observed_side_cell_keys": [SIDE_CELL],
        },
        "loss_control_blockers": [],
        "authority_boundary_violation": None,
        "admission_review": {
            "status": enablement.ADMISSION_READY_STATUS,
            "candidate": SIDE_CELL,
            "gui_risk_config_is_source_of_truth": True,
            "gui_p1_risk_trade_pct": 10.0,
            "per_trade_risk_pct_fraction": 0.1,
            "per_trade_budget_usdt": 955.1369426,
            "single_position_budget_usdt": 2387.84235651,
            "max_order_notional_usdt": 0.0,
            "effective_single_order_cap_usdt": 955.1369426,
            "position_size_max_pct": 25.0,
            "local_10_usdt_cap_is_authority": False,
            "blockers": [],
        },
        "governance_review": {
            "status": enablement.GOVERNANCE_READY_STATUS,
            "risk_level": "NORMAL",
            "position_size_multiplier": 1.0,
            "lease_live_count": 0,
            "lease_count": 0,
            "blockers": [],
        },
        "deploy_review": {
            "status": enablement.DEPLOY_READY_STATUS,
            "runtime_head": "e8b5c77b171547f0660765cd6e4a9c77f391d70a",
            "OPENCLAW_ALLOW_MAINNET": "0",
            "OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED": "",
            "OPENCLAW_DEMO_LEARNING_LANE_WRITER": "",
            "blockers": [],
        },
        "answers": {
            "e3_bb_enablement_review_ready": True,
            "order_capable_action_allowed": False,
            "allowed_to_submit_order": False,
            "order_submission_performed": False,
            "adapter_enablement_performed": False,
            "writer_enablement_performed": False,
            "decision_lease_acquire_performed": False,
            "decision_lease_release_performed": False,
            "pg_write_performed": False,
            "cost_gate_lowering_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "live_authority_granted": False,
            "mainnet_authority_granted": False,
            "promotion_evidence": False,
            "promotion_proof": False,
            "profit_proof": False,
        },
    }


def _request_packet(review_path) -> dict:
    contract_packet = contract.build_current_candidate_e3_bb_enablement_review_contract(
        order_enablement_review=_order_enablement_review(),
        candidate_side_cell_key=SIDE_CELL,
        now_utc=GEN,
        order_enablement_path=review_path,
    )
    return request.build_current_candidate_e3_bb_signoff_request_packet(
        e3_bb_contract=contract_packet,
        now_utc=GEN,
    )


def _answers() -> dict:
    return {
        "order_capable_action_allowed": False,
        "allowed_to_submit_order": False,
        "order_submission_performed": False,
        "adapter_enablement_performed": False,
        "writer_enablement_performed": False,
        "decision_lease_acquire_performed": False,
        "decision_lease_release_performed": False,
        "bybit_call_performed": False,
        "pg_query_performed": False,
        "pg_write_performed": False,
        "cost_gate_lowering_performed": False,
        "live_authority_granted": False,
        "mainnet_authority_granted": False,
        "main_cost_gate_adjustment": "NONE",
        "promotion_proof": False,
        "profit_proof": False,
    }


def _signoff(role: str, review_sha: str) -> dict:
    return {
        "schema_version": contract.SIGNOFF_SCHEMA_VERSION,
        "generated_at_utc": GEN.isoformat(),
        "role": role,
        "decision": contract.APPROVE_DECISION,
        "candidate_side_cell_key": SIDE_CELL,
        "order_enablement_review_sha256": review_sha,
        "answers": _answers(),
    }


def test_missing_signoffs_remains_no_order_missing(tmp_path) -> None:
    review_path = tmp_path / "order_enablement.json"
    request_path = tmp_path / "request.json"
    review_path.write_text(json.dumps(_order_enablement_review()), encoding="utf-8")
    request_path.write_text(json.dumps(_request_packet(review_path)), encoding="utf-8")

    packet = mod.build_current_candidate_e3_bb_signoff_intake(
        order_enablement_review=_order_enablement_review(),
        signoff_request_packet=_request_packet(review_path),
        search_paths=[tmp_path],
        now_utc=NOW,
        order_enablement_path=review_path,
        request_path=request_path,
    )

    assert packet["status"] == mod.SIGNOFFS_MISSING_STATUS
    assert "e3_signoff_missing" in packet["signoff_blockers"]
    assert "bb_signoff_missing" in packet["signoff_blockers"]
    assert packet["answers"]["signoffs_found_and_validated"] is False
    assert packet["answers"]["order_capable_action_allowed"] is False


def test_valid_e3_bb_signoffs_are_located_and_approved_no_order(tmp_path) -> None:
    review_path = tmp_path / "order_enablement.json"
    request_path = tmp_path / "request.json"
    review_path.write_text(json.dumps(_order_enablement_review()), encoding="utf-8")
    request_path.write_text(json.dumps(_request_packet(review_path)), encoding="utf-8")
    review_sha = mod._sha256(review_path)
    (tmp_path / "e3_signoff.json").write_text(
        json.dumps(_signoff(contract.E3_ROLE, review_sha)), encoding="utf-8"
    )
    (tmp_path / "bb_signoff.json").write_text(
        json.dumps(_signoff(contract.BB_ROLE, review_sha)), encoding="utf-8"
    )

    packet = mod.build_current_candidate_e3_bb_signoff_intake(
        order_enablement_review=_order_enablement_review(),
        signoff_request_packet=_request_packet(review_path),
        search_paths=[tmp_path],
        now_utc=NOW,
        order_enablement_path=review_path,
        request_path=request_path,
    )

    assert packet["status"] == mod.APPROVED_NO_ORDER_STATUS
    assert packet["signoff_blockers"] == []
    assert packet["answers"]["e3_bb_review_approved_no_order"] is True
    assert packet["answers"]["order_capable_action_allowed"] is False
    assert packet["contract_review"]["status"] == contract.APPROVED_NO_ORDER_STATUS


def test_inert_templates_are_ignored_as_missing_signoffs(tmp_path) -> None:
    review_path = tmp_path / "order_enablement.json"
    request_path = tmp_path / "request.json"
    review_path.write_text(json.dumps(_order_enablement_review()), encoding="utf-8")
    request_packet = _request_packet(review_path)
    request_path.write_text(json.dumps(request_packet), encoding="utf-8")
    for role_packet in request_packet["requested_roles"]:
        (tmp_path / f"{role_packet['role'].lower()}_template.json").write_text(
            json.dumps(role_packet["signoff_template"]), encoding="utf-8"
        )

    packet = mod.build_current_candidate_e3_bb_signoff_intake(
        order_enablement_review=_order_enablement_review(),
        signoff_request_packet=request_packet,
        search_paths=[tmp_path],
        now_utc=NOW,
        order_enablement_path=review_path,
        request_path=request_path,
    )

    assert packet["status"] == mod.SIGNOFFS_MISSING_STATUS
    assert "e3_signoff_decision_not_approve_no_order" in packet["signoff_blockers"]
    assert "bb_signoff_decision_not_approve_no_order" in packet["signoff_blockers"]
    assert packet["answers"]["order_capable_action_allowed"] is False


def test_request_claiming_approval_fails_closed(tmp_path) -> None:
    review_path = tmp_path / "order_enablement.json"
    request_path = tmp_path / "request.json"
    review_path.write_text(json.dumps(_order_enablement_review()), encoding="utf-8")
    request_packet = _request_packet(review_path)
    request_packet["answers"]["approval_granted_by_this_packet"] = True
    request_path.write_text(json.dumps(request_packet), encoding="utf-8")

    packet = mod.build_current_candidate_e3_bb_signoff_intake(
        order_enablement_review=_order_enablement_review(),
        signoff_request_packet=request_packet,
        search_paths=[tmp_path],
        now_utc=NOW,
        order_enablement_path=review_path,
        request_path=request_path,
    )

    assert packet["status"] == mod.AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert packet["authority_boundary_violation"].endswith(
        ".approval_granted_by_this_packet"
    )
    assert packet["answers"]["order_capable_action_allowed"] is False


def test_cli_writes_missing_status_artifacts(tmp_path, monkeypatch) -> None:
    review_path = tmp_path / "order_enablement.json"
    request_path = tmp_path / "request.json"
    json_output = tmp_path / "intake.json"
    md_output = tmp_path / "intake.md"
    review_path.write_text(json.dumps(_order_enablement_review()), encoding="utf-8")
    request_path.write_text(json.dumps(_request_packet(review_path)), encoding="utf-8")

    argv = [
        "current_candidate_e3_bb_signoff_intake",
        "--order-enable-review-json",
        str(review_path),
        "--signoff-request-json",
        str(request_path),
        "--signoff-search-path",
        str(tmp_path),
        "--now-utc",
        NOW.isoformat(),
        "--json-output",
        str(json_output),
        "--output",
        str(md_output),
    ]
    monkeypatch.setattr(sys, "argv", copy.deepcopy(argv))

    assert mod.main() == 1
    packet = json.loads(json_output.read_text(encoding="utf-8"))
    assert packet["status"] == mod.SIGNOFFS_MISSING_STATUS
    assert "Order-capable action allowed: `False`" in md_output.read_text(
        encoding="utf-8"
    )
