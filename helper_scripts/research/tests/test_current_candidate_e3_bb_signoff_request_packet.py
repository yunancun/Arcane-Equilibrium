from __future__ import annotations

import copy
import datetime as dt
import json
import sys

from cost_gate_learning_lane import (
    current_candidate_e3_bb_enablement_review_contract as contract,
)
from cost_gate_learning_lane import current_candidate_order_enablement_review as enablement
from cost_gate_learning_lane import current_candidate_e3_bb_signoff_request_packet as mod


NOW = dt.datetime(2026, 6, 27, 13, 15, tzinfo=dt.timezone.utc)
GEN = dt.datetime(2026, 6, 27, 13, 10, tzinfo=dt.timezone.utc)
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


def _contract_packet(review_path=None) -> dict:
    return contract.build_current_candidate_e3_bb_enablement_review_contract(
        order_enablement_review=_order_enablement_review(),
        candidate_side_cell_key=SIDE_CELL,
        now_utc=GEN,
        order_enablement_path=review_path,
    )


def test_request_packet_emits_inert_role_templates(tmp_path) -> None:
    review_path = tmp_path / "order_enablement.json"
    review_path.write_text(json.dumps(_order_enablement_review()), encoding="utf-8")
    packet = mod.build_current_candidate_e3_bb_signoff_request_packet(
        e3_bb_contract=_contract_packet(review_path),
        now_utc=NOW,
    )

    assert packet["status"] == mod.READY_STATUS
    assert packet["answers"]["approval_granted_by_this_packet"] is False
    assert packet["answers"]["order_capable_action_allowed"] is False
    # E3/BB 批准內容自 v739+ 起明示包含 post-approval drift 放寬條款
    assert packet["post_approval_drift_policy"] == "docs_tests_codex_exempt_v1"
    assert packet["loss_control_blockers"] == []
    assert [role["role"] for role in packet["requested_roles"]] == [
        contract.E3_ROLE,
        contract.BB_ROLE,
    ]
    for role in packet["requested_roles"]:
        template = role["signoff_template"]
        assert template["schema_version"] == contract.SIGNOFF_SCHEMA_VERSION
        assert template["decision"] == mod.TEMPLATE_DECISION
        assert role["template_is_approval"] is False
        assert template["candidate_side_cell_key"] == SIDE_CELL
        assert template["answers"]["order_submission_performed"] is False


def test_inert_templates_are_not_valid_contract_approvals(tmp_path) -> None:
    review_path = tmp_path / "order_enablement.json"
    review_path.write_text(json.dumps(_order_enablement_review()), encoding="utf-8")
    request = mod.build_current_candidate_e3_bb_signoff_request_packet(
        e3_bb_contract=_contract_packet(review_path),
        now_utc=NOW,
    )
    templates = {
        item["role"]: item["signoff_template"] for item in request["requested_roles"]
    }

    packet = contract.build_current_candidate_e3_bb_enablement_review_contract(
        order_enablement_review=_order_enablement_review(),
        e3_signoff=templates[contract.E3_ROLE],
        bb_signoff=templates[contract.BB_ROLE],
        candidate_side_cell_key=SIDE_CELL,
        now_utc=NOW,
        order_enablement_path=review_path,
    )

    assert packet["status"] == contract.SIGNOFF_REQUIRED_STATUS
    assert "e3_signoff_decision_not_approve_no_order" in packet["signoff_blockers"]
    assert "bb_signoff_decision_not_approve_no_order" in packet["signoff_blockers"]
    assert packet["answers"]["order_capable_action_allowed"] is False


def test_contract_loss_control_blocker_blocks_request() -> None:
    contract_packet = _contract_packet()
    contract_packet["loss_control_blockers"] = ["guardian_not_normal"]

    packet = mod.build_current_candidate_e3_bb_signoff_request_packet(
        e3_bb_contract=contract_packet,
        now_utc=NOW,
    )

    assert packet["status"] == mod.BLOCKED_BY_LOSS_CONTROL_STATUS
    assert "e3_bb_contract_loss_control_blockers_present" in packet[
        "loss_control_blockers"
    ]
    assert packet["answers"]["signoff_request_ready"] is False


def test_contract_authority_contamination_fails_closed() -> None:
    contract_packet = _contract_packet()
    contract_packet["answers"]["order_submission_performed"] = True

    packet = mod.build_current_candidate_e3_bb_signoff_request_packet(
        e3_bb_contract=contract_packet,
        now_utc=NOW,
    )

    assert packet["status"] == mod.AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert packet["authority_boundary_violation"].endswith(
        ".order_submission_performed"
    )
    assert packet["answers"]["order_capable_action_allowed"] is False


def test_cli_writes_request_packet_and_markdown(tmp_path, monkeypatch) -> None:
    review_path = tmp_path / "order_enablement.json"
    contract_path = tmp_path / "contract.json"
    json_output = tmp_path / "request.json"
    md_output = tmp_path / "request.md"
    review_path.write_text(json.dumps(_order_enablement_review()), encoding="utf-8")
    contract_path.write_text(json.dumps(_contract_packet(review_path)), encoding="utf-8")

    argv = [
        "current_candidate_e3_bb_signoff_request_packet",
        "--e3-bb-contract-json",
        str(contract_path),
        "--now-utc",
        NOW.isoformat(),
        "--json-output",
        str(json_output),
        "--output",
        str(md_output),
    ]
    monkeypatch.setattr(sys, "argv", copy.deepcopy(argv))

    assert mod.main() == 0
    packet = json.loads(json_output.read_text(encoding="utf-8"))
    assert packet["status"] == mod.READY_STATUS
    assert "Order-capable action allowed: `False`" in md_output.read_text(
        encoding="utf-8"
    )
