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
from cost_gate_learning_lane.outcome_writer import (
    ProbeOutcomeConfig,
    build_blocked_signal_outcome_records,
    build_probe_outcome_records,
    read_price_observations,
)
from cost_gate_learning_lane.price_observations import (
    PriceObservationBuildConfig,
    build_price_observation_artifact,
    build_market_klines_observation_sql,
    build_price_observations_from_rows,
    fetch_market_kline_price_rows,
    required_price_observation_windows,
    write_price_observation_artifact,
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


class _FakeKlineCursor:
    description = [("symbol",), ("ts_ms",), ("close",)]

    def __init__(self, conn):
        self.conn = conn
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params):
        self.conn.executions.append((sql, params))
        self._rows = self.conn.rows_by_symbol.get(params[0], [])

    def fetchall(self):
        return self._rows


class _FakeKlineConn:
    def __init__(self, rows_by_symbol):
        self.rows_by_symbol = rows_by_symbol
        self.executions = []

    def cursor(self):
        return _FakeKlineCursor(self)


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


def test_policy_plan_waits_on_future_scorecard_timestamp():
    plan = build_plan_from_payload(
        _scorecard_payload("2026-06-21T12:00:01+00:00"),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
    )

    assert plan["status"] == "WAIT_FOR_SCORECARD_REFRESH"
    assert plan["gate_status"] == "WAIT"
    assert plan["source"]["source_error"] == "future_scorecard_generated_at"
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
    assert row["primary_blocker"] == "cost_gate_probe_candidates_ready_but_runtime_ledger_empty"
    assert row["next_trigger"] == (
        "deploy_enable_runtime_ledger_writer_then_observe_reject_rows"
    )
    assert row["operator_actionable"] is True
    assert row["engineering_actionable"] is True
    assert row["main_cost_gate_adjustment"] == "NONE"
    assert row["order_authority"] == "NOT_GRANTED"
    assert row["ledger_status"] == "MISSING"
    assert row["admission_decision_count"] == 0
    assert row["probe_candidates"][0]["side_cell_key"] == "ma_crossover|ETHUSDT|Sell"


def test_alpha_discovery_surfaces_cost_gate_ledger_progress(tmp_path: Path):
    data_dir = tmp_path
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
    )
    lane_dir = data_dir / "cost_gate_learning_lane"
    lane_dir.mkdir(parents=True)
    (lane_dir / "demo_learning_lane_plan_latest.json").write_text(
        json.dumps(plan),
        encoding="utf-8",
    )
    ledger_path = lane_dir / "probe_ledger.jsonl"
    ledger_path.write_text(
        json.dumps(
            {
                "record_type": "probe_admission_decision",
                "generated_at_utc": "2026-06-21T11:02:00+00:00",
                "attempt_id": "ctx-demo-ma_crossover-ETHUSDT-1782037200000",
                "decision": "ORDER_AUTHORITY_NOT_GRANTED",
                "allowed_to_submit_order": False,
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "event": _selected_reject_event(),
            }
        )
        + "\n"
        + json.dumps(
            {
                "record_type": "blocked_signal_outcome",
                "generated_at_utc": "2026-06-21T12:15:00+00:00",
                "attempt_id": "ctx-demo-ma_crossover-ETHUSDT-1782037200000",
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "source_admission_decision": "ORDER_AUTHORITY_NOT_GRANTED",
                "realized_net_bps": 12.5,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    arm = collect_cost_gate_learning_lane_arm(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )
    discovery = build_discovery_plan(
        [arm],
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )
    row = discovery["profitability_blocker_scorecard"]["arms"][0]

    assert row["primary_blocker"] == "cost_gate_blocked_signal_outcomes_accumulating"
    assert row["next_trigger"] == (
        "review_blocked_signal_outcomes_before_any_probe_order_authority"
    )
    assert row["ledger_status"] == "BLOCKED_SIGNAL_OUTCOMES_PRESENT"
    assert row["admission_decision_count"] == 1
    assert row["order_authority_not_granted_count"] == 1
    assert row["blocked_signal_outcome_count"] == 1
    assert row["blocked_signal_positive_outcome_count"] == 1
    assert row["avg_blocked_signal_outcome_net_bps"] == 12.5
    assert row["blocked_signal_net_positive_pct"] == 100.0


def test_alpha_discovery_routes_admission_only_ledger_to_price_observation_builder(
    tmp_path: Path,
):
    data_dir = tmp_path
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
    )
    lane_dir = data_dir / "cost_gate_learning_lane"
    lane_dir.mkdir(parents=True)
    (lane_dir / "demo_learning_lane_plan_latest.json").write_text(
        json.dumps(plan),
        encoding="utf-8",
    )
    (lane_dir / "probe_ledger.jsonl").write_text(
        json.dumps(
            {
                "record_type": "probe_admission_decision",
                "generated_at_utc": "2026-06-21T11:02:00+00:00",
                "attempt_id": "ctx-demo-ma_crossover-ETHUSDT-1782037200000",
                "decision": "ORDER_AUTHORITY_NOT_GRANTED",
                "allowed_to_submit_order": False,
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "event": _selected_reject_event(),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    arm = collect_cost_gate_learning_lane_arm(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )
    discovery = build_discovery_plan(
        [arm],
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )
    row = discovery["profitability_blocker_scorecard"]["arms"][0]

    assert row["primary_blocker"] == (
        "cost_gate_rejects_recorded_need_blocked_signal_outcomes"
    )
    assert row["next_trigger"] == (
        "build_price_observations_then_record_blocked_signal_outcomes"
    )
    assert row["ledger_status"] == "ADMISSION_ROWS_PRESENT"
    assert row["admission_decision_count"] == 1
    assert row["blocked_signal_outcome_count"] == 0


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


def test_runtime_adapter_rejects_future_plan_timestamp():
    plan = _runtime_plan(order_authority=ORDER_AUTHORITY_GRANTED)
    plan["generated_at_utc"] = "2026-06-21T12:00:01+00:00"

    decision = evaluate_probe_admission(
        plan,
        _selected_reject_event(),
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )

    assert decision["decision"] == "PLAN_STALE_OR_MISSING_GENERATED_AT"
    assert decision["allowed_to_submit_order"] is False
    assert decision["reason"] == "plan_generated_at_missing_or_too_old"


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


def test_runtime_adapter_builds_markout_outcome_only_for_admitted_probe():
    admitted = evaluate_probe_admission(
        _runtime_plan(order_authority=ORDER_AUTHORITY_GRANTED),
        {
            **_selected_reject_event(),
            "last_price": 2000.0,
        },
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )
    not_granted = evaluate_probe_admission(
        _runtime_plan(),
        _selected_reject_event(),
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )
    ledger = [build_ledger_record(admitted), build_ledger_record(not_granted)]

    outcomes = build_probe_outcome_records(
        ledger,
        [
            {"symbol": "ETHUSDT", "ts_ms": 1_782_037_200_000, "close": 2000.0},
            {"symbol": "ETHUSDT", "ts_ms": 1_782_040_800_000, "close": 1980.0},
        ],
        now_utc=dt.datetime(2026, 6, 21, 12, 11, tzinfo=dt.timezone.utc),
        cfg=ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0),
    )

    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome["record_type"] == "probe_outcome"
    assert outcome["attempt_id"] == _selected_reject_event()["context_id"]
    assert outcome["side_cell_key"] == "ma_crossover|ETHUSDT|Sell"
    assert outcome["outcome_source"] == "market_markout_proxy"
    assert outcome["promotion_evidence"] is False
    assert round(outcome["gross_bps"], 6) == 100.0
    assert round(outcome["realized_net_bps"], 6) == 96.0


def test_runtime_adapter_builds_blocked_signal_outcome_for_not_granted_reject():
    not_granted = evaluate_probe_admission(
        _runtime_plan(),
        _selected_reject_event(),
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )
    ledger = [build_ledger_record(not_granted)]

    outcomes = build_blocked_signal_outcome_records(
        ledger,
        [
            {"symbol": "ETHUSDT", "ts_ms": 1_782_037_200_000, "close": 2000.0},
            {"symbol": "ETHUSDT", "ts_ms": 1_782_040_800_000, "close": 2010.0},
        ],
        now_utc=dt.datetime(2026, 6, 21, 12, 11, tzinfo=dt.timezone.utc),
        cfg=ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0),
    )

    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome["record_type"] == "blocked_signal_outcome"
    assert outcome["source_admission_decision"] == "ORDER_AUTHORITY_NOT_GRANTED"
    assert outcome["allowed_to_submit_order"] is False
    assert outcome["outcome_source"] == "market_markout_proxy_for_blocked_signal"
    assert outcome["promotion_evidence"] is False
    assert round(outcome["gross_bps"], 6) == -50.0
    assert round(outcome["realized_net_bps"], 6) == -54.0


def test_price_observation_windows_target_unlabeled_blocked_signals_only():
    not_granted = evaluate_probe_admission(
        _runtime_plan(),
        _selected_reject_event(),
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )
    ledger = [build_ledger_record(not_granted)]

    windows = required_price_observation_windows(
        ledger,
        cfg=PriceObservationBuildConfig(horizon_minutes=60, max_entry_delay_ms=300_000),
    )

    assert len(windows) == 1
    window = windows[0]
    assert window["target_outcome_record_type"] == "blocked_signal_outcome"
    assert window["source_admission_decision"] == "ORDER_AUTHORITY_NOT_GRANTED"
    assert window["attempt_id"] == _selected_reject_event()["context_id"]
    assert window["symbol"] == "ETHUSDT"
    assert window["start_ts_ms"] == 1_782_037_200_000
    assert window["exit_target_ts_ms"] == 1_782_040_800_000
    assert window["end_ts_ms"] == 1_782_041_100_000

    completed = {
        "record_type": "blocked_signal_outcome",
        "attempt_id": _selected_reject_event()["context_id"],
    }
    assert required_price_observation_windows(ledger + [completed]) == []


def test_price_observation_builder_filters_rows_and_writes_adapter_compatible_artifact(
    tmp_path: Path,
):
    not_granted = evaluate_probe_admission(
        _runtime_plan(),
        _selected_reject_event(),
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )
    ledger = [build_ledger_record(not_granted)]
    windows = required_price_observation_windows(
        ledger,
        cfg=PriceObservationBuildConfig(horizon_minutes=60, max_entry_delay_ms=300_000),
    )
    source_rows = [
        {
            "symbol": "ETHUSDT",
            "open_time_ms": 1_782_037_140_000,
            "close_time_ms": 1_782_037_200_000,
            "close": "2000.0",
        },
        {"symbol": "ETHUSDT", "ts_ms": 1_782_040_800_000, "price": 2010.0},
        {"symbol": "ETHUSDT", "ts_ms": 1_782_040_800_000, "price": 2010.0},
        {"symbol": "ETHUSDT", "ts_ms": 1_782_041_200_000, "close": 2012.0},
        {"symbol": "BTCUSDT", "ts_ms": 1_782_040_800_000, "close": 100_000.0},
        {"symbol": "ETHUSDT", "ts_ms": 1_782_040_000_000},
    ]

    observations = build_price_observations_from_rows(source_rows, windows)

    assert observations == [
        {
            "schema_version": "cost_gate_demo_learning_lane_price_observations_v1",
            "record_type": "price_observation",
            "symbol": "ETHUSDT",
            "ts_ms": 1_782_037_200_000,
            "close": 2000.0,
            "source": "local_price_row",
        },
        {
            "schema_version": "cost_gate_demo_learning_lane_price_observations_v1",
            "record_type": "price_observation",
            "symbol": "ETHUSDT",
            "ts_ms": 1_782_040_800_000,
            "close": 2010.0,
            "source": "local_price_row",
        },
    ]

    artifact = build_price_observation_artifact(
        ledger,
        source_rows,
        now_utc=dt.datetime(2026, 6, 21, 12, 15, tzinfo=dt.timezone.utc),
        cfg=PriceObservationBuildConfig(horizon_minutes=60, max_entry_delay_ms=300_000),
    )
    assert artifact["window_count"] == 1
    assert artifact["observation_count"] == 2
    assert artifact["observations"] == observations

    json_path = tmp_path / "price_observations.json"
    jsonl_path = tmp_path / "price_observations.jsonl"
    write_price_observation_artifact(json_path, artifact)
    write_price_observation_artifact(jsonl_path, artifact)

    assert read_price_observations(json_path) == observations
    assert read_price_observations(jsonl_path) == observations


def test_price_observation_pg_adapter_is_read_only_and_feeds_observation_builder():
    sql = build_market_klines_observation_sql()
    lowered = sql.lower()
    assert "market.klines" in sql
    for token in ("insert", "update", "delete", "alter", "drop"):
        assert token not in lowered

    windows = [
        {
            "symbol": "ETHUSDT",
            "start_ts_ms": 1_782_037_200_000,
            "end_ts_ms": 1_782_041_100_000,
        },
        {
            "symbol": "BTCUSDT",
            "start_ts_ms": 1_782_037_200_000,
            "end_ts_ms": 1_782_037_260_000,
        },
    ]
    conn = _FakeKlineConn(
        {
            "ETHUSDT": [
                ("ETHUSDT", 1_782_037_200_000, 2000.0),
                ("ETHUSDT", 1_782_040_800_000, 2010.0),
            ],
            "BTCUSDT": [("BTCUSDT", 1_782_037_200_000, 100_000.0)],
        }
    )

    rows = fetch_market_kline_price_rows(conn, windows, timeframe="1m")

    assert [params[0] for _sql, params in conn.executions] == ["BTCUSDT", "ETHUSDT"]
    assert all(params[1] == "1m" for _sql, params in conn.executions)
    assert all(params[2].tzinfo == dt.timezone.utc for _sql, params in conn.executions)
    assert rows == [
        {
            "symbol": "BTCUSDT",
            "ts_ms": 1_782_037_200_000,
            "close": 100_000.0,
            "timeframe": "1m",
            "source": "pg_market_klines",
        },
        {
            "symbol": "ETHUSDT",
            "ts_ms": 1_782_037_200_000,
            "close": 2000.0,
            "timeframe": "1m",
            "source": "pg_market_klines",
        },
        {
            "symbol": "ETHUSDT",
            "ts_ms": 1_782_040_800_000,
            "close": 2010.0,
            "timeframe": "1m",
            "source": "pg_market_klines",
        },
    ]

    observations = build_price_observations_from_rows(rows, windows)
    assert observations[0]["source"] == "pg_market_klines"
    assert observations[0]["timeframe"] == "1m"


def test_runtime_adapter_outcome_rows_are_idempotent_and_feed_disable():
    admitted = evaluate_probe_admission(
        _runtime_plan(order_authority=ORDER_AUTHORITY_GRANTED),
        {
            **_selected_reject_event(),
            "last_price": 2000.0,
        },
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )
    ledger = [build_ledger_record(admitted)]
    first_outcome = build_probe_outcome_records(
        ledger,
        [
            {"symbol": "ETHUSDT", "ts_ms": 1_782_037_200_000, "close": 2000.0},
            {"symbol": "ETHUSDT", "ts_ms": 1_782_040_800_000, "close": 2010.0},
        ],
        now_utc=dt.datetime(2026, 6, 21, 12, 11, tzinfo=dt.timezone.utc),
        cfg=ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0),
    )
    assert len(first_outcome) == 1

    duplicate = build_probe_outcome_records(
        ledger + first_outcome,
        [
            {"symbol": "ETHUSDT", "ts_ms": 1_782_037_200_000, "close": 2000.0},
            {"symbol": "ETHUSDT", "ts_ms": 1_782_040_800_000, "close": 2010.0},
        ],
        now_utc=dt.datetime(2026, 6, 21, 12, 11, tzinfo=dt.timezone.utc),
        cfg=ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0),
    )
    assert duplicate == []

    disabled = evaluate_probe_admission(
        _runtime_plan(order_authority=ORDER_AUTHORITY_GRANTED),
        {
            **_selected_reject_event(),
            "context_id": "ctx-demo-ma_crossover-ETHUSDT-1782044400000",
            "ts_ms": 1_782_044_400_000,
        },
        ledger_rows=ledger + first_outcome,
        now_utc=dt.datetime(2026, 6, 21, 13, 30, tzinfo=dt.timezone.utc),
        cfg=RuntimeAdmissionConfig(min_failed_outcomes_to_disable=1),
        adapter_enabled=True,
    )
    assert disabled["decision"] == "REALIZED_PROBE_OUTCOMES_FAIL_LEARNING_THRESHOLD"
    assert disabled["runtime_state"]["completed_outcome_count"] == 1


def test_runtime_adapter_normalizes_cost_gate_negative_reason_text():
    assert normalize_reject_reason_code(
        "cost_gate(JS-demo): negative edge -15.2 bps blocked"
    ) == "cost_gate_js_demo_negative_edge"
