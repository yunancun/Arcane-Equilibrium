from __future__ import annotations

import copy
import datetime as dt
import json
import sys

from cost_gate_learning_lane import (
    current_candidate_e3_bb_enablement_review_contract as mod,
)
from cost_gate_learning_lane import current_candidate_order_enablement_review as enablement


NOW = dt.datetime(2026, 6, 27, 12, 45, tzinfo=dt.timezone.utc)
GEN = dt.datetime(2026, 6, 27, 12, 40, tzinfo=dt.timezone.utc)
SIDE_CELL = "grid_trading|AVAXUSDT|Sell"
ORDER_REVIEW_SHA = "a" * 64


def _order_enablement_review(**overrides) -> dict:
    payload = {
        "schema_version": enablement.SCHEMA_VERSION,
        "generated_at_utc": GEN.isoformat(),
        "status": enablement.READY_FOR_E3_BB_STATUS,
        "reason": "source_runtime_no_order_evidence_ready_for_e3_bb_enablement_review",
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
    payload.update(overrides)
    return payload


def _answers(**overrides) -> dict:
    payload = {
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
    payload.update(overrides)
    return payload


def _signoff(role: str, **overrides) -> dict:
    payload = {
        "schema_version": mod.SIGNOFF_SCHEMA_VERSION,
        "generated_at_utc": GEN.isoformat(),
        "role": role,
        "decision": mod.APPROVE_DECISION,
        "candidate_side_cell_key": SIDE_CELL,
        "order_enablement_review_sha256": ORDER_REVIEW_SHA,
        "answers": _answers(),
    }
    payload.update(overrides)
    return payload


def _packet(**overrides) -> dict:
    kwargs = {
        "order_enablement_review": _order_enablement_review(),
        "candidate_side_cell_key": SIDE_CELL,
        "now_utc": NOW,
    }
    kwargs.update(overrides)
    return mod.build_current_candidate_e3_bb_enablement_review_contract(**kwargs)


def test_missing_e3_bb_signoffs_requires_signoff_without_order_authority() -> None:
    packet = _packet()

    assert packet["status"] == mod.SIGNOFF_REQUIRED_STATUS
    assert packet["loss_control_blockers"] == []
    assert "e3_signoff_missing" in packet["signoff_blockers"]
    assert "bb_signoff_missing" in packet["signoff_blockers"]
    assert packet["answers"]["e3_bb_signoff_contract_ready"] is True
    assert packet["answers"]["e3_bb_review_approved_no_order"] is False
    assert packet["answers"]["order_capable_action_allowed"] is False
    assert packet["required_signoff_contract"]["decision"] == mod.APPROVE_DECISION
    assert packet["order_enablement_review"]["per_trade_risk_pct_fraction"] == 0.1
    assert packet["order_enablement_review"]["per_trade_budget_usdt"] > 10.0


def test_valid_e3_and_bb_signoffs_approve_only_no_order_review(tmp_path) -> None:
    review_path = tmp_path / "order_enablement.json"
    review_path.write_text(json.dumps(_order_enablement_review()), encoding="utf-8")
    sha = mod._sha256(review_path)

    packet = mod.build_current_candidate_e3_bb_enablement_review_contract(
        order_enablement_review=_order_enablement_review(),
        e3_signoff=_signoff(mod.E3_ROLE, order_enablement_review_sha256=sha),
        bb_signoff=_signoff(mod.BB_ROLE, order_enablement_review_sha256=sha),
        candidate_side_cell_key=SIDE_CELL,
        now_utc=NOW,
        order_enablement_path=review_path,
    )

    assert packet["status"] == mod.APPROVED_NO_ORDER_STATUS
    assert packet["signoff_blockers"] == []
    assert packet["answers"]["e3_bb_review_approved_no_order"] is True
    assert packet["answers"]["order_capable_action_allowed"] is False
    assert packet["answers"]["allowed_to_submit_order"] is False
    assert "active_bounded_demo_decision_lease" in packet[
        "required_same_window_gates_before_order_capable_action"
    ]


def test_signoff_authority_contamination_fails_closed() -> None:
    e3 = _signoff(mod.E3_ROLE)
    e3["answers"]["order_submission_performed"] = True

    packet = _packet(e3_signoff=e3, bb_signoff=_signoff(mod.BB_ROLE))

    assert packet["status"] == mod.AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert packet["authority_boundary_violation"].endswith(
        ".order_submission_performed"
    )
    assert packet["answers"]["order_capable_action_allowed"] is False


def test_order_enablement_review_must_keep_gui_percent_semantics() -> None:
    review = _order_enablement_review()
    review["admission_review"]["per_trade_risk_pct_fraction"] = 10.0
    review["admission_review"]["per_trade_budget_usdt"] = 10.0

    packet = _packet(order_enablement_review=review)

    assert packet["status"] == mod.BLOCKED_BY_LOSS_CONTROL_STATUS
    assert "per_trade_risk_pct_fraction_not_0_1" in packet[
        "loss_control_blockers"
    ]
    assert "per_trade_budget_not_equity_resolved" in packet["loss_control_blockers"]
    assert packet["answers"]["order_capable_action_allowed"] is False


def test_stale_order_enablement_review_blocks_loss_control() -> None:
    packet = _packet(
        now_utc=NOW + dt.timedelta(hours=1),
        max_artifact_age_seconds=60,
    )

    assert packet["status"] == mod.BLOCKED_BY_LOSS_CONTROL_STATUS
    assert "order_enablement_review_stale" in packet["loss_control_blockers"]
    assert packet["answers"]["order_capable_action_allowed"] is False


def test_cli_writes_contract_artifacts_with_signoff_required(tmp_path, monkeypatch) -> None:
    review_path = tmp_path / "order_enablement.json"
    json_output = tmp_path / "contract.json"
    md_output = tmp_path / "contract.md"
    review_path.write_text(json.dumps(_order_enablement_review()), encoding="utf-8")

    argv = [
        "current_candidate_e3_bb_enablement_review_contract",
        "--order-enable-review-json",
        str(review_path),
        "--candidate-side-cell-key",
        SIDE_CELL,
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

    assert packet["status"] == mod.SIGNOFF_REQUIRED_STATUS
    assert packet["answers"]["order_capable_action_allowed"] is False
    assert "Order-capable action allowed: `False`" in md_output.read_text(
        encoding="utf-8"
    )
