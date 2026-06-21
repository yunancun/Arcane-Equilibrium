"""Tests for cost-gate demo learning-lane policy artifacts."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from alpha_discovery_throughput.discovery_loop import build_discovery_plan
from alpha_discovery_throughput.runtime_runner import collect_cost_gate_learning_lane_arm
from cost_gate_learning_lane.policy import (
    DEMO_LEARNING_LANE_SCHEMA_VERSION,
    LearningLanePolicyConfig,
    build_plan_from_file,
    build_plan_from_payload,
)
from cost_gate_learning_lane.runtime_adapter import (
    ADMIT_DECISION,
    ORDER_AUTHORITY_GRANTED,
    RuntimeAdmissionConfig,
    build_ledger_record,
    evaluate_probe_admission,
    normalize_reject_reason_code,
    read_jsonl_ledger,
    append_jsonl_ledger,
)


def _scorecard_payload(generated_at: str = "2026-06-21T10:00:00+00:00") -> dict:
    rows = [
        {
            "strategy_name": "ma_crossover",
            "symbol": "ETHUSDT",
            "side": "Sell",
            "reject_reason_code": "cost_gate_js_demo_negative_edge",
            "n": 486,
            "avg_gross_bps": 101.9788,
            "p50_gross_bps": 49.421,
            "p90_gross_bps": 211.0,
            "avg_net_bps": 97.9788,
            "gross_positive_pct": 90.0,
            "net_positive_pct": 86.01,
            "learning_lane_action": "LEARNING_PROBE_CANDIDATE",
            "learning_lane_reason": "avg_net_positive_and_median_gross_clears_friction",
        },
        {
            "strategy_name": "ma_crossover",
            "symbol": "NEARUSDT",
            "side": "Sell",
            "reject_reason_code": "cost_gate_js_demo_negative_edge",
            "n": 244,
            "avg_gross_bps": 20.2197,
            "p50_gross_bps": 13.2,
            "p90_gross_bps": 31.0,
            "avg_net_bps": 16.2197,
            "gross_positive_pct": 100.0,
            "net_positive_pct": 99.95,
            "learning_lane_action": "LEARNING_PROBE_CANDIDATE",
            "learning_lane_reason": "avg_net_positive_and_median_gross_clears_friction",
        },
        {
            "strategy_name": "ma_crossover",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "reject_reason_code": "cost_gate_js_demo_negative_edge",
            "n": 300,
            "avg_gross_bps": -31.7434,
            "p50_gross_bps": -29.6769,
            "p90_gross_bps": -2.0,
            "avg_net_bps": -35.7434,
            "gross_positive_pct": 2.0,
            "net_positive_pct": 0.0,
            "learning_lane_action": "BLOCK_CONFIRMED",
            "learning_lane_reason": "avg_net_nonpositive_and_low_net_positive_rate",
        },
        {
            "strategy_name": "grid_trading",
            "symbol": "OPUSDT",
            "side": "Sell",
            "reject_reason_code": "cost_gate_atr_unavailable",
            "n": 500,
            "avg_gross_bps": 8.0,
            "p50_gross_bps": 6.0,
            "p90_gross_bps": 20.0,
            "avg_net_bps": 4.0,
            "gross_positive_pct": 70.0,
            "net_positive_pct": 60.0,
            "learning_lane_action": "DATA_COVERAGE_BLOCKER",
            "learning_lane_reason": "reject_reason_requires_data_fix_not_probe",
        },
    ]
    return {
        "generated_at_utc": generated_at,
        "coverage": {"decision_features": 1000, "features_joined_outcomes": 0},
        "learning_lane_scorecard": {
            "schema_version": "cost_gate_reject_counterfactual_v2",
            "status": "LEARNING_LANE_PROBE_CANDIDATES_PRESENT",
            "outcome_path_status": "OUTCOME_PATH_STALLED_FOR_FEATURE_REJECTS",
            "action_counts": {
                "LEARNING_PROBE_CANDIDATE": 2,
                "BLOCK_CONFIRMED": 1,
                "DATA_COVERAGE_BLOCKER": 1,
            },
            "probe_candidates": rows[:2],
            "rows": rows,
        },
    }


def test_policy_plan_keeps_main_gate_closed_and_selects_only_probe_candidates():
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
        cfg=LearningLanePolicyConfig(max_probe_side_cells=4, max_total_probe_orders=4),
    )

    assert plan["schema_version"] == DEMO_LEARNING_LANE_SCHEMA_VERSION
    assert plan["status"] == "READY_FOR_DEMO_LEARNING_PROBE"
    assert plan["gate_status"] == "OPERATOR_REVIEW"
    assert plan["main_cost_gate_adjustment"] == "NONE"
    assert plan["order_authority"] == "NOT_GRANTED"
    assert plan["learning_gate_adjustment"] == (
        "SIDE_CELL_DEMO_PROBE_ONLY_AFTER_ADAPTER_WIRING"
    )
    assert [row["side_cell_key"] for row in plan["probe_candidates"]] == [
        "ma_crossover|ETHUSDT|Sell",
        "ma_crossover|NEARUSDT|Sell",
    ]
    assert {row["probe_proposal"]["mode"] for row in plan["probe_candidates"]} == {
        "demo_only_learning_probe"
    }
    assert all(
        row["guardrails"]["main_cost_gate_adjustment"] == "NONE"
        for row in plan["probe_candidates"]
    )
    assert plan["do_not_probe_side_cells"][0]["side_cell_key"] == (
        "ma_crossover|BTCUSDT|Buy"
    )
    assert plan["data_coverage_tasks"][0]["side_cell_key"] == "grid_trading|OPUSDT|Sell"


def test_policy_plan_waits_on_stale_scorecard(tmp_path: Path):
    path = tmp_path / "scorecard.json"
    path.write_text(json.dumps(_scorecard_payload("2026-06-20T00:00:00+00:00")), encoding="utf-8")

    plan = build_plan_from_file(
        path,
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
        cfg=LearningLanePolicyConfig(max_scorecard_age_hours=6),
    )

    assert plan["status"] == "WAIT_FOR_SCORECARD_REFRESH"
    assert plan["gate_status"] == "WAIT"
    assert plan["source"]["source_error"] == "stale_scorecard"
    assert plan["selected_probe_candidate_count"] == 0
    assert plan["probe_candidates"] == []
    assert plan["main_cost_gate_adjustment"] == "NONE"


def test_alpha_discovery_surfaces_cost_gate_learning_probe_ready(tmp_path: Path):
    data_dir = tmp_path
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
    )
    plan_path = data_dir / "cost_gate_learning_lane" / "demo_learning_lane_plan_latest.json"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    arm = collect_cost_gate_learning_lane_arm(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )
    discovery = build_discovery_plan(
        [arm],
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )
    scorecard = discovery["profitability_blocker_scorecard"]
    row = scorecard["arms"][0]

    assert discovery["arms"][0]["action"] == "READY_FOR_PROBE"
    assert scorecard["status"] == "ACTIONABLE_PROBE_READY"
    assert row["arm_id"] == "cost_gate_demo_learning_lane"
    assert row["primary_blocker"] == "cost_gate_learning_probe_candidates_ready"
    assert row["next_trigger"] == (
        "wire_bounded_demo_learning_lane_policy_before_any_gate_lowering"
    )
    assert row["operator_actionable"] is True
    assert row["engineering_actionable"] is True
    assert row["main_cost_gate_adjustment"] == "NONE"
    assert row["order_authority"] == "NOT_GRANTED"
    assert row["probe_candidates"][0]["side_cell_key"] == "ma_crossover|ETHUSDT|Sell"


def _selected_reject_event() -> dict:
    return {
        "strategy_name": "ma_crossover",
        "symbol": "ETHUSDT",
        "side": "Sell",
        "reject_reason_code": "cost_gate_js_demo_negative_edge",
        "engine_mode": "live_demo",
        "ts_ms": 1_782_037_200_000,
        "context_id": "ctx-demo-ma_crossover-ETHUSDT-1782037200000",
        "signal_id": "sig-demo-ma_crossover-ETHUSDT-1782037200000",
    }


def _runtime_plan(*, order_authority: str = "NOT_GRANTED") -> dict:
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
        cfg=LearningLanePolicyConfig(max_probe_side_cells=2, max_total_probe_orders=4),
    )
    plan["order_authority"] = order_authority
    return plan


def test_runtime_adapter_matches_candidate_but_keeps_current_plan_no_order_authority():
    decision = evaluate_probe_admission(
        _runtime_plan(),
        _selected_reject_event(),
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )

    assert decision["decision"] == "ORDER_AUTHORITY_NOT_GRANTED"
    assert decision["allowed_to_submit_order"] is False
    assert decision["no_order_authority"] is True
    assert decision["side_cell_key"] == "ma_crossover|ETHUSDT|Sell"
    assert decision["runtime_state"]["remaining_probe_orders"] == 2
    assert decision["plan_summary"]["main_cost_gate_adjustment"] == "NONE"
    assert decision["reason"] == "plan_matches_candidate_but_artifact_has_no_order_authority"


def test_runtime_adapter_admits_only_when_plan_and_adapter_explicitly_authorize():
    decision = evaluate_probe_admission(
        _runtime_plan(order_authority=ORDER_AUTHORITY_GRANTED),
        _selected_reject_event(),
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )

    assert decision["decision"] == ADMIT_DECISION
    assert decision["allowed_to_submit_order"] is True
    assert decision["no_order_authority"] is False


def test_runtime_adapter_blocks_unselected_side_cell_and_non_negative_cost_gate_reason():
    plan = _runtime_plan(order_authority=ORDER_AUTHORITY_GRANTED)
    unselected = {
        **_selected_reject_event(),
        "symbol": "BTCUSDT",
        "side": "Buy",
    }
    not_cost_gate_negative = {
        **_selected_reject_event(),
        "reject_reason_code": "cost_gate_atr_unavailable",
    }

    assert evaluate_probe_admission(
        plan,
        unselected,
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )["decision"] == "SIDE_CELL_NOT_SELECTED"
    assert evaluate_probe_admission(
        plan,
        not_cost_gate_negative,
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )["decision"] == "REJECT_REASON_NOT_ELIGIBLE"


def test_runtime_adapter_enforces_budget_cooldown_and_failed_outcome_disable():
    plan = _runtime_plan(order_authority=ORDER_AUTHORITY_GRANTED)
    event = _selected_reject_event()
    prior_admit = {
        "record_type": "probe_admission_decision",
        "decision": ADMIT_DECISION,
        "side_cell_key": "ma_crossover|ETHUSDT|Sell",
        "ts_ms": 1_782_039_600_000,
    }
    now = dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc)

    cooldown = evaluate_probe_admission(
        plan,
        event,
        ledger_rows=[prior_admit],
        now_utc=now,
        adapter_enabled=True,
    )
    assert cooldown["decision"] == "COOLDOWN_ACTIVE"

    exhausted = evaluate_probe_admission(
        plan,
        event,
        ledger_rows=[
            {**prior_admit, "ts_ms": 1_782_033_000_000},
            {**prior_admit, "ts_ms": 1_782_034_000_000},
        ],
        now_utc=now,
        adapter_enabled=True,
    )
    assert exhausted["decision"] == "PROBE_BUDGET_EXHAUSTED"

    failed_outcomes = evaluate_probe_admission(
        plan,
        event,
        ledger_rows=[
            {
                "record_type": "probe_outcome",
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "realized_net_bps": -8.0,
            },
            {
                "record_type": "probe_outcome",
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "realized_net_bps": -3.0,
            },
        ],
        now_utc=now,
        cfg=RuntimeAdmissionConfig(min_failed_outcomes_to_disable=2),
        adapter_enabled=True,
    )
    assert failed_outcomes["decision"] == "REALIZED_PROBE_OUTCOMES_FAIL_LEARNING_THRESHOLD"


def test_runtime_adapter_ledger_record_round_trips_jsonl(tmp_path: Path):
    path = tmp_path / "probe_ledger.jsonl"
    decision = evaluate_probe_admission(
        _runtime_plan(),
        _selected_reject_event(),
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )
    append_jsonl_ledger(path, build_ledger_record(decision))
    rows = read_jsonl_ledger(path)

    assert len(rows) == 1
    assert rows[0]["record_type"] == "probe_admission_decision"
    assert rows[0]["decision"] == "ORDER_AUTHORITY_NOT_GRANTED"
    assert rows[0]["side_cell_key"] == "ma_crossover|ETHUSDT|Sell"


def test_runtime_adapter_normalizes_cost_gate_negative_reason_text():
    assert normalize_reject_reason_code(
        "cost_gate(JS-demo): negative edge -15.2 bps blocked"
    ) == "cost_gate_js_demo_negative_edge"
