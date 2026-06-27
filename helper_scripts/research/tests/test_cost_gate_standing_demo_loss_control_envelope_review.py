from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import subprocess

from cost_gate_learning_lane.standing_demo_loss_control_envelope_review import (
    AUTHORITY_BOUNDARY_VIOLATION_STATUS,
    DEFAULT_MATERIALIZATION_PATH,
    DEFAULT_STANDING_ENV_VAR,
    LOSS_CONTROL_LIMIT_INVALID_STATUS,
    MATERIALIZATION_ENV_VAR_INVALID_STATUS,
    MATERIALIZATION_PATH_INVALID_STATUS,
    READY_STATUS,
    SELECTION_REQUIRED_STATUS,
    build_standing_demo_loss_control_envelope_review,
    render_markdown,
)


NOW = dt.datetime(2026, 6, 27, 0, 10, tzinfo=dt.timezone.utc)
SIDE_CELL = "grid_trading|AVAXUSDT|Sell"


def _candidate_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "side_cell_key": SIDE_CELL,
        "false_negative_rank": 1,
        "strategy_names": ["grid_trading"],
        "symbols": ["AVAXUSDT"],
        "sides": ["Sell"],
        "horizon_minutes": [60],
        "dominant_horizon_minutes": 60,
        "outcome_count": 48,
        "avg_gross_bps": 77.55,
        "avg_net_bps": 73.55,
        "avg_cost_bps": 4.0,
        "net_positive_pct": 100.0,
        "net_cost_cushion_bps": 73.55,
        "wrongful_block_score": 147.10,
        "candidate_class": "false_negative_after_cost",
        "learning_diagnosis": "cost_gate_false_negative_after_cost",
        "status": "FALSE_NEGATIVE_AFTER_COST_REVIEWABLE",
        "reason": "after_cost_edge_survives_current_gate",
        "next_action": "operator_review_ranked_false_negative_candidate",
        "operator_review_required": True,
        "risk_cap_lineage": {
            "risk_source_of_truth": "GUI-backed Rust RiskConfig",
            "cap_source": "current_candidate_envelope.cap_resolution.resolved_cap_usdt",
            "account_equity_usdt": 9552.43426257,
            "per_trade_risk_pct_display": 10.0,
            "per_trade_risk_pct_fraction": 0.1,
            "position_size_max_pct": 25.0,
            "resolved_cap_usdt": 955.24342626,
            "rounded_notional_usdt": 954.6264,
            "single_position_budget_usdt": 2388.10856564,
            "bounded_probe_local_cap_usdt_is_authority": False,
            "local_10_usdt_cap_is_global_risk_authority": False,
        },
        "global_cost_gate_lowering_recommended": False,
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "promotion_evidence": False,
    }
    row.update(overrides)
    return row


def _candidate_packet(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "cost_gate_false_negative_candidate_packet_v1",
        "generated_at_utc": "2026-06-27T00:00:00+00:00",
        "status": "COST_GATE_FALSE_NEGATIVE_CANDIDATES_READY_FOR_OPERATOR_REVIEW",
        "reason": "blocked_side_cells_clear_after_cost_review_thresholds",
        "summary": {
            "ranked_candidate_count": 1,
            "false_negative_candidate_count": 1,
            "edge_amplification_candidate_count": 0,
            "top_false_negative_side_cell_key": SIDE_CELL,
        },
        "answers": {
            "false_negative_candidates_present": True,
            "operator_review_ready": True,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "ranked_false_negative_candidates": [_candidate_row()],
        "boundary": "artifact-only no-authority fixture",
    }
    payload.update(overrides)
    return payload


def test_ready_review_builds_valid_candidate_scoped_envelope_without_runtime_mutation() -> None:
    review = build_standing_demo_loss_control_envelope_review(
        false_negative_candidate_packet=_candidate_packet(),
        selected_side_cell_key=SIDE_CELL,
        operator_id="operator-test",
        now_utc=NOW,
    )
    markdown = render_markdown(review)

    assert review["status"] == READY_STATUS
    assert review["summary"]["review_ready_no_runtime_mutation"] is True
    assert review["answers"]["runtime_mutation_performed"] is False
    assert review["answers"]["standing_envelope_materialized"] is False
    assert review["answers"]["bounded_demo_probe_authorized"] is False
    assert review["answers"]["operator_authorization_object_emitted"] is False
    assert review["answers"]["order_authority_granted"] is False
    assert review["answers"]["global_cost_gate_lowering_recommended"] is False

    envelope = review["envelope_preview"]
    assert envelope["schema_version"] == "standing_demo_operator_authorization_v1"
    assert envelope["status"] == "STANDING_DEMO_AUTHORIZATION_ACTIVE"
    assert envelope["operator_id"] == "operator-test"
    assert envelope["environment"] == "demo"
    assert envelope["scope"] == "demo_api_only_bounded_probe"
    assert envelope["candidate"] == {
        "side_cell_key": SIDE_CELL,
        "strategy_name": "grid_trading",
        "symbol": "AVAXUSDT",
        "side": "Sell",
        "outcome_horizon_minutes": 60,
    }
    assert envelope["max_authorized_probe_orders_per_candidate"] == 2
    assert envelope["risk_cap_lineage"]["per_trade_risk_pct_fraction"] == 0.1
    assert envelope["risk_cap_lineage"]["per_trade_risk_pct_display"] == 10.0
    assert envelope["risk_cap_lineage"]["resolved_cap_usdt"] == 955.24342626
    assert (
        envelope["risk_cap_lineage"]["local_10_usdt_cap_is_global_risk_authority"]
        is False
    )
    assert review["standing_demo_authorization_validation"][
        "valid_for_candidate_scoped_authorization"
    ] is True
    assert review["materialization_plan"]["proposed_env_var"] == DEFAULT_STANDING_ENV_VAR
    assert review["materialization_plan"][
        "runtime_mutation_performed_by_this_helper"
    ] is False
    assert "OPENCLAW_COST_GATE_BOUNDED_PROBE_OPERATOR_AUTHORIZATION_DECISION=authorize" in (
        review["materialization_plan"]["future_apply_steps_require_e3_review"][2]
    )
    assert "Standing Demo Loss-Control Envelope Review" in markdown


def test_authority_contamination_blocks_and_omits_envelope() -> None:
    packet = _candidate_packet(
        answers={
            "false_negative_candidates_present": True,
            "operator_review_ready": True,
            "global_cost_gate_lowering_recommended": True,
            "main_cost_gate_adjustment": "LOWER",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        }
    )

    review = build_standing_demo_loss_control_envelope_review(
        false_negative_candidate_packet=packet,
        selected_side_cell_key=SIDE_CELL,
        operator_id="operator-test",
        now_utc=NOW,
    )

    assert review["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert "authority_boundary_preserved" in review["blocking_gates"]
    assert review["envelope_preview"] == {}
    assert review["materialization_plan"] == {}
    assert review["answers"]["runtime_mutation_performed"] is False
    assert review["answers"]["order_authority_granted"] is False


def test_invalid_materialization_path_blocks_review() -> None:
    review = build_standing_demo_loss_control_envelope_review(
        false_negative_candidate_packet=_candidate_packet(),
        selected_side_cell_key=SIDE_CELL,
        operator_id="operator-test",
        standing_demo_authorization_output_path=Path(
            "/Users/ncyu/secrets/standing_demo_operator_authorization.json"
        ),
        now_utc=NOW,
    )

    assert review["status"] == MATERIALIZATION_PATH_INVALID_STATUS
    assert "materialization_path_valid" in review["blocking_gates"]
    assert review["envelope_preview"] == {}


def test_invalid_env_var_blocks_review() -> None:
    review = build_standing_demo_loss_control_envelope_review(
        false_negative_candidate_packet=_candidate_packet(),
        selected_side_cell_key=SIDE_CELL,
        operator_id="operator-test",
        standing_demo_authorization_env_var=(
            "OPENCLAW_COST_GATE_BOUNDED_PROBE_OPERATOR_AUTHORIZATION_DECISION"
        ),
        now_utc=NOW,
    )

    assert review["status"] == MATERIALIZATION_ENV_VAR_INVALID_STATUS
    assert "materialization_env_var_valid" in review["blocking_gates"]
    assert review["envelope_preview"] == {}


def test_unbounded_probe_cap_blocks_review() -> None:
    review = build_standing_demo_loss_control_envelope_review(
        false_negative_candidate_packet=_candidate_packet(),
        selected_side_cell_key=SIDE_CELL,
        operator_id="operator-test",
        max_authorized_probe_orders=10,
        now_utc=NOW,
    )

    assert review["status"] == LOSS_CONTROL_LIMIT_INVALID_STATUS
    assert "loss_control_limits_valid" in review["blocking_gates"]
    assert review["envelope_preview"] == {}


def test_missing_explicit_side_cell_blocks_selection() -> None:
    review = build_standing_demo_loss_control_envelope_review(
        false_negative_candidate_packet=_candidate_packet(),
        selected_side_cell_key="grid_trading|MISSING|Sell",
        operator_id="operator-test",
        now_utc=NOW,
    )

    assert review["status"] == SELECTION_REQUIRED_STATUS
    assert "candidate_selected" in review["blocking_gates"]
    assert review["envelope_preview"] == {}


def test_cli_refuses_to_write_review_packet_to_runtime_envelope_path(
    tmp_path: Path,
) -> None:
    packet_path = tmp_path / "candidate_packet.json"
    packet_path.write_text(json.dumps(_candidate_packet()), encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = "helper_scripts/research"

    result = subprocess.run(
        [
            "python3",
            "-m",
            "cost_gate_learning_lane.standing_demo_loss_control_envelope_review",
            "--false-negative-candidate-packet-json",
            str(packet_path),
            "--selected-side-cell-key",
            SIDE_CELL,
            "--operator-id",
            "operator-test",
            "--json-output",
            str(DEFAULT_MATERIALIZATION_PATH),
        ],
        cwd=Path(__file__).resolve().parents[3],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "refusing to write review output to proposed runtime authorization path" in (
        result.stderr
    )
