"""Tests for cost-gate demo learning-lane policy artifacts."""

from __future__ import annotations

import datetime as dt
import json
import math
import os
from pathlib import Path
import subprocess

from alpha_discovery_throughput.discovery_loop import build_discovery_plan
from alpha_discovery_throughput.runtime_runner import collect_cost_gate_learning_lane_arm
from cost_gate_learning_lane.policy import (
    DEMO_LEARNING_LANE_SCHEMA_VERSION,
    LearningLanePolicyConfig,
    build_plan_from_file,
    build_plan_from_payload,
)
from cost_gate_learning_lane.historical_review import (
    HISTORICAL_REVIEW_SCHEMA_VERSION,
    HistoricalScorecardReviewConfig,
    build_historical_scorecard_review,
    build_historical_scorecard_review_from_file,
)
from cost_gate_learning_lane.outcome_writer import (
    ProbeOutcomeConfig,
    build_blocked_signal_outcome_records,
    build_probe_outcome_records,
    read_price_observations,
)
from cost_gate_learning_lane.outcome_refresh import (
    OutcomeRefreshSelection,
    build_cost_gate_outcome_refresh_batch,
    build_price_rows_from_pg_for_refresh,
    refresh_cost_gate_outcomes_from_price_rows,
)
from cost_gate_learning_lane.outcome_review import (
    BlockedOutcomeReviewConfig,
    build_blocked_signal_outcome_review,
)
from cost_gate_learning_lane.false_negative_candidate_packet import (
    build_false_negative_candidate_packet,
    render_false_negative_candidate_packet_markdown,
)
from cost_gate_learning_lane.false_negative_operator_review import (
    APPROVED_FOR_PREFLIGHT_STATUS as FALSE_NEGATIVE_APPROVED_FOR_PREFLIGHT_STATUS,
    PENDING_OPERATOR_REVIEW_STATUS as FALSE_NEGATIVE_PENDING_OPERATOR_REVIEW_STATUS,
    build_false_negative_operator_review,
    expected_false_negative_operator_review_typed_confirm,
)
from cost_gate_learning_lane.learning_ssot_decision import (
    build_learning_ssot_decision,
    render_markdown as render_learning_ssot_decision_markdown,
)
from cost_gate_learning_lane.status import (
    ACTIVATION_PREFLIGHT_SCHEMA_VERSION,
    REQUIRED_SOURCE_RELATIVE_PATHS,
    build_cost_gate_learning_lane_activation_preflight,
    main as cost_gate_status_main,
    summarize_cost_gate_learning_lane_ledger,
    summarize_cost_gate_learning_lane_writer_config,
    summarize_cost_gate_learning_lane_writer_process,
    summarize_cost_gate_learning_lane_source,
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
from cost_gate_learning_lane.reject_materializer import (
    RejectMaterializerConfig,
    append_materialized_records_to_ledger,
    build_cost_gate_reject_feature_sql,
    build_materialized_reject_ledger_batch,
    pipeline_snapshot_recent_intents_to_feature_rows,
    reject_feature_row_to_event,
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
    summarize_side_cell_runtime_state,
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
            "horizon_stability_scorecard": {
                "schema_version": "cost_gate_reject_horizon_stability_v1",
                "status": "MULTI_HORIZON_PROFIT_LEARNING_CANDIDATES_PRESENT",
                "next_trigger": (
                    "operator_review_multi_horizon_side_cells_for_bounded_demo_learning_lane"
                ),
                "horizons_minutes": [15, 60],
                "top_side_cells": [
                    {
                        "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                        "status": "CANDIDATE_MULTI_HORIZON_STABLE",
                        "reason": (
                            "side_cell_clears_learning_thresholds_on_multiple_horizons"
                        ),
                        "candidate_horizons": [15, 60],
                        "best_horizon_minutes": 60,
                        "best_avg_net_bps": 97.9788,
                        "best_net_positive_pct": 86.01,
                    },
                    {
                        "side_cell_key": "ma_crossover|NEARUSDT|Sell",
                        "status": "CANDIDATE_HORIZON_SPECIFIC",
                        "reason": (
                            "side_cell_clears_learning_thresholds_on_one_horizon_only"
                        ),
                        "candidate_horizons": [60],
                        "best_horizon_minutes": 60,
                        "best_avg_net_bps": 16.2197,
                        "best_net_positive_pct": 99.95,
                    },
                ],
            },
            "rows": rows,
        },
    }


def _sealed_horizon_replay_packet(*, status: str = "SEALED_HORIZON_REPLAY_READY_FOR_OPERATOR_REVIEW") -> dict:
    passed = status == "SEALED_HORIZON_REPLAY_READY_FOR_OPERATOR_REVIEW"
    failed_gates = [] if passed else ["avg_net_floor_met"]
    return {
        "schema_version": "horizon_specific_sealed_replay_packet_v1",
        "generated_at_utc": "2026-06-22T03:31:40+00:00",
        "status": status,
        "next_action": (
            "operator_review_sealed_replay_then_wait_for_learning_stack_outcome_accumulation"
            if passed
            else "rerun_or_repair_horizon_replay_artifacts_before_any_probe_review"
        ),
        "selection": {
            "candidate_rank": 1,
            "requested_side_cell_key": None,
            "selected": {
                "rank": 1,
                "side_cell_key": "ma_crossover|BTCUSDT|Sell",
                "candidate_status": "RETIMING_CANDIDATE",
                "best_horizon_minutes": 240,
                "primary_horizon_minutes": 60,
                "primary_horizon_action": "BLOCK_CONFIRMED",
                "required_next_gate": (
                    "sealed_horizon_specific_replay_before_bounded_demo_probe"
                ),
            },
        },
        "source": {
            "horizon_packet": {
                "path": "/tmp/openclaw/horizon_edge_amplification_latest.json",
                "sha256": "horizon-sha",
                "schema_version": "horizon_edge_amplification_packet_v1",
                "generated_at_utc": "2026-06-22T03:31:38+00:00",
            },
            "replay_counterfactual": {
                "path": "/tmp/openclaw/cost_gate_reject_counterfactual_latest.json",
                "sha256": "counterfactual-sha",
                "schema_version": "cost_gate_reject_counterfactual_v2",
                "generated_at_utc": "2026-06-22T03:16:07+00:00",
            },
        },
        "replay_evaluation": {
            "side_cell_key": "ma_crossover|BTCUSDT|Sell",
            "best_horizon": {
                "source": "horizon_stability_scorecard",
                "horizon_minutes": 240,
                "learning_lane_action": "LEARNING_PROBE_CANDIDATE",
                "sample_count_for_gate": 13819,
                "avg_net_bps": 31.8707,
                "p50_gross_bps": 51.4448,
                "net_positive_pct": 81.94,
                "candidate_edge_amplification_vs_primary_bps": 73.6814,
            },
            "primary_horizon": {
                "horizon_minutes": 60,
                "learning_lane_action": "BLOCK_CONFIRMED",
                "avg_net_bps": -41.8107,
                "sample_count_for_gate": 16515,
            },
            "failed_gate_names": failed_gates,
            "gates": [
                {"name": "avg_net_floor_met", "passed": passed},
            ],
        },
        "answers": {
            "sealed_replay_passed": passed,
            "retiming_candidate_revalidated": passed,
            "operator_review_ready": passed,
            "requires_learning_stack_accumulation": True,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "global_boundaries": {
            "order_authority": "NOT_GRANTED",
            "probe_authority": "NOT_GRANTED",
            "main_cost_gate_adjustment": "NONE",
            "runtime_mutation": "NONE",
            "promotion_evidence": False,
        },
    }


def _activation_preflight_for_ssot(
    *,
    ledger_rows: int = 100,
    blocked_outcomes: int = 40,
    writer_enabled: bool = False,
    process_writer_enabled: bool = False,
) -> dict:
    return {
        "schema_version": "cost_gate_demo_learning_lane_activation_preflight_v1",
        "generated_at_utc": "2026-06-24T04:30:00+00:00",
        "status": "BLOCKED_OUTCOMES_ACCUMULATING",
        "reason": "blocked_signal_outcomes_present_but_review_gate_not_cleared",
        "answers": {
            "currently_accumulating_evidence": ledger_rows > 0,
            "runtime_writer_enabled": writer_enabled,
            "runtime_writer_process_enabled": process_writer_enabled,
            "activation_ready": True,
        },
        "ledger": {
            "ledger_path": "/tmp/openclaw/cost_gate_learning_lane/probe_ledger.jsonl",
            "ledger_status": "BLOCKED_SIGNAL_OUTCOMES_PRESENT",
            "ledger_total_rows": ledger_rows,
            "admission_decision_count": max(ledger_rows - blocked_outcomes, 0),
            "captured_reject_count": max(ledger_rows - blocked_outcomes, 0),
            "blocked_signal_outcome_count": blocked_outcomes,
            "proof_excluded_probe_outcome_count": 0,
        },
        "writer_config": {
            "writer_config_status": (
                "WRITER_ENABLED" if writer_enabled else "WRITER_DISABLED_OR_UNSET"
            ),
            "writer_enabled": writer_enabled,
        },
        "writer_process": {
            "writer_process_checked": True,
            "writer_process_status": (
                "WRITER_ENABLED"
                if process_writer_enabled
                else "WRITER_DISABLED_OR_UNSET"
            ),
            "writer_process_enabled": process_writer_enabled,
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


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
    )


def _git_output(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
    )
    return proc.stdout.strip()


def _write_required_source_files(repo: Path) -> None:
    for rel in REQUIRED_SOURCE_RELATIVE_PATHS:
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".sh":
            path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            path.chmod(0o755)
        else:
            path.write_text('"""fixture source file."""\n', encoding="utf-8")


def _init_source_repo_with_origin(tmp_path: Path) -> tuple[Path, Path]:
    remote = tmp_path / "remote.git"
    repo = tmp_path / "repo"
    remote.mkdir()
    repo.mkdir()
    _git(remote, "init", "--bare")
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    _write_required_source_files(repo)
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-u", "origin", "main")
    return repo, remote


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
    assert plan["source"]["probe_candidate_ranking_source"] == "derived_from_scorecard_rows"
    assert plan["source"]["profit_opportunity_ranking_status"] == (
        "PROFIT_LEARNING_CANDIDATES_PRESENT"
    )
    assert plan["source"]["horizon_stability_status"] == (
        "MULTI_HORIZON_PROFIT_LEARNING_CANDIDATES_PRESENT"
    )
    assert plan["source"]["horizon_stability_horizons_minutes"] == [15, 60]
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
    assert plan["probe_candidates"][0]["profit_priority_score"] is not None
    assert plan["probe_candidates"][0]["profit_priority_tier"] == (
        "HIGH_PRIORITY_BOUNDED_DEMO_LEARNING"
    )
    assert plan["probe_candidates"][0]["horizon_stability"] == {
        "status": "CANDIDATE_MULTI_HORIZON_STABLE",
        "reason": "side_cell_clears_learning_thresholds_on_multiple_horizons",
        "candidate_horizons": [15, 60],
        "best_horizon_minutes": 60,
        "best_avg_net_bps": 97.9788,
        "best_net_positive_pct": 86.01,
    }
    assert all(
        row["guardrails"]["main_cost_gate_adjustment"] == "NONE"
        for row in plan["probe_candidates"]
    )
    assert plan["do_not_probe_side_cells"][0]["side_cell_key"] == (
        "ma_crossover|BTCUSDT|Buy"
    )
    assert plan["data_coverage_tasks"][0]["side_cell_key"] == "grid_trading|OPUSDT|Sell"


def test_policy_plan_promotes_passed_sealed_horizon_replay_into_learning_candidate():
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 22, 4, tzinfo=dt.timezone.utc),
        cfg=LearningLanePolicyConfig(max_probe_side_cells=1, max_total_probe_orders=3),
        horizon_sealed_replay=_sealed_horizon_replay_packet(),
    )

    assert plan["status"] == "READY_FOR_DEMO_LEARNING_PROBE"
    assert plan["gate_status"] == "OPERATOR_REVIEW"
    assert plan["main_cost_gate_adjustment"] == "NONE"
    assert plan["order_authority"] == "NOT_GRANTED"
    assert plan["source"]["horizon_sealed_replay_status"] == (
        "SEALED_HORIZON_REPLAY_READY_FOR_OPERATOR_REVIEW"
    )
    assert plan["source"]["horizon_sealed_replay_source_error"] is None
    assert plan["source"]["horizon_sealed_replay_side_cell_key"] == (
        "ma_crossover|BTCUSDT|Sell"
    )
    assert plan["source"]["horizon_sealed_replay_best_horizon_minutes"] == 240

    candidate = plan["probe_candidates"][0]
    assert candidate["side_cell_key"] == "ma_crossover|BTCUSDT|Sell"
    assert candidate["source_kind"] == "horizon_specific_sealed_replay"
    assert candidate["outcome_horizon_minutes"] == 240
    assert candidate["learning_outcome_horizon_minutes"] == 240
    assert candidate["probe_proposal"]["outcome_horizon_minutes"] == 240
    assert candidate["probe_proposal"]["learning_outcome_horizon_minutes"] == 240
    assert (
        candidate["probe_proposal"]["requires_candidate_horizon_outcome_logging"]
        is True
    )
    assert candidate["sealed_horizon_replay"]["best_avg_net_bps"] == 31.8707
    assert candidate["sealed_horizon_replay"]["failed_gate_names"] == []
    assert candidate["guardrails"]["main_cost_gate_adjustment"] == "NONE"
    assert candidate["guardrails"]["notional_or_qty_not_granted_by_artifact"] is True
    assert "ma_crossover|BTCUSDT|Sell" not in [
        row["side_cell_key"] for row in plan["do_not_probe_side_cells"]
    ]
    assert "record_candidate_summary_and_horizon_in_learning_ledger" in (
        plan["required_runtime_wiring"]
    )
    assert "refresh_blocked_signal_outcomes_at_candidate_horizon" in (
        plan["required_runtime_wiring"]
    )


def test_policy_plan_ignores_blocked_sealed_horizon_replay_packet():
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 22, 4, tzinfo=dt.timezone.utc),
        cfg=LearningLanePolicyConfig(max_probe_side_cells=1, max_total_probe_orders=3),
        horizon_sealed_replay=_sealed_horizon_replay_packet(
            status="SEALED_HORIZON_REPLAY_BLOCKED"
        ),
    )

    assert plan["source"]["horizon_sealed_replay_source_error"] == (
        "horizon_sealed_replay_not_ready"
    )
    assert plan["source"]["horizon_sealed_replay_failed_gate_names"] == [
        "avg_net_floor_met"
    ]
    assert [row["side_cell_key"] for row in plan["probe_candidates"]] == [
        "ma_crossover|ETHUSDT|Sell"
    ]


def test_policy_plan_prefers_profit_opportunity_ranking_when_present():
    payload = _scorecard_payload()
    scorecard = payload["learning_lane_scorecard"]
    scorecard["profit_opportunity_ranking"] = {
        "schema_version": "cost_gate_profit_opportunity_ranking_v1",
        "status": "PROFIT_LEARNING_CANDIDATES_PRESENT",
        "next_trigger": "operator_review_top_ranked_side_cells_for_bounded_demo_learning_lane",
        "top_side_cells": [
            {
                "side_cell_key": "ma_crossover|NEARUSDT|Sell",
                "strategy_name": "ma_crossover",
                "symbol": "NEARUSDT",
                "side": "Sell",
                "reject_reason_code": "cost_gate_js_demo_negative_edge",
                "learning_lane_action": "LEARNING_PROBE_CANDIDATE",
                "learning_lane_reason": "avg_net_positive_and_median_gross_clears_friction",
                "priority_tier": "HIGH_PRIORITY_BOUNDED_DEMO_LEARNING",
                "priority_score": 88.0,
                "priority_components": {"hit_rate_score": 25.0},
                "n": 244,
                "avg_net_bps": 16.2197,
                "p50_gross_bps": 13.2,
                "p90_gross_bps": 31.0,
                "net_positive_pct": 99.95,
                "next_action": "operator_review_ranked_side_cell_for_bounded_demo_learning_lane",
                "order_authority": "NOT_GRANTED",
                "main_cost_gate_adjustment": "NONE",
                "promotion_evidence": False,
            },
            {
                "side_cell_key": "grid_trading|FILUSDT|Buy",
                "strategy_name": "grid_trading",
                "symbol": "FILUSDT",
                "side": "Buy",
                "reject_reason_code": "cost_gate_js_demo_negative_edge",
                "learning_lane_action": "LEARNING_PROBE_CANDIDATE",
                "priority_tier": "COLLECT_MORE_SAMPLE",
                "priority_score": 99.0,
                "n": 57,
                "avg_net_bps": 58.9223,
                "p50_gross_bps": 81.5493,
                "net_positive_pct": 75.44,
                "next_action": "continue_collecting_reject_counterfactual_samples",
                "order_authority": "NOT_GRANTED",
                "main_cost_gate_adjustment": "NONE",
                "promotion_evidence": False,
            },
            {
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "strategy_name": "ma_crossover",
                "symbol": "ETHUSDT",
                "side": "Sell",
                "reject_reason_code": "cost_gate_js_demo_negative_edge",
                "learning_lane_action": "LEARNING_PROBE_CANDIDATE",
                "learning_lane_reason": "avg_net_positive_and_median_gross_clears_friction",
                "priority_tier": "MEDIUM_PRIORITY_BOUNDED_DEMO_LEARNING",
                "priority_score": 70.0,
                "priority_components": {"avg_net_score": 25.0},
                "n": 486,
                "avg_net_bps": 97.9788,
                "p50_gross_bps": 49.421,
                "p90_gross_bps": 211.0,
                "net_positive_pct": 86.01,
                "next_action": "operator_review_ranked_side_cell_for_bounded_demo_learning_lane",
                "order_authority": "NOT_GRANTED",
                "main_cost_gate_adjustment": "NONE",
                "promotion_evidence": False,
            },
        ],
    }

    plan = build_plan_from_payload(
        payload,
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
        cfg=LearningLanePolicyConfig(max_probe_side_cells=3, max_total_probe_orders=6),
    )

    assert plan["source"]["probe_candidate_ranking_source"] == "profit_opportunity_ranking"
    assert plan["source"]["profit_opportunity_ranking_status"] == (
        "PROFIT_LEARNING_CANDIDATES_PRESENT"
    )
    assert [row["side_cell_key"] for row in plan["probe_candidates"]] == [
        "ma_crossover|NEARUSDT|Sell",
        "ma_crossover|ETHUSDT|Sell",
    ]
    assert "grid_trading|FILUSDT|Buy" not in [
        row["side_cell_key"] for row in plan["probe_candidates"]
    ]
    assert plan["probe_candidates"][0]["profit_priority_score"] == 88.0
    assert plan["probe_candidates"][0]["profit_priority_tier"] == (
        "HIGH_PRIORITY_BOUNDED_DEMO_LEARNING"
    )
    assert plan["probe_candidates"][0]["guardrails"]["main_cost_gate_adjustment"] == "NONE"
    assert plan["order_authority"] == "NOT_GRANTED"


def test_policy_and_historical_review_use_effective_sample_gate() -> None:
    payload = _scorecard_payload()
    scorecard = payload["learning_lane_scorecard"]
    duplicate_inflated = {
        "side_cell_key": "dup_signal|SOLUSDT|Buy",
        "strategy_name": "dup_signal",
        "symbol": "SOLUSDT",
        "side": "Buy",
        "reject_reason_code": "cost_gate_js_demo_negative_edge",
        "learning_lane_action": "LEARNING_PROBE_CANDIDATE",
        "learning_lane_reason": "avg_net_positive_and_median_gross_clears_friction",
        "priority_tier": "HIGH_PRIORITY_BOUNDED_DEMO_LEARNING",
        "priority_score": 99.0,
        "priority_components": {"sample_score": 25.0},
        "n": 500,
        "sample_count_for_gate": 3,
        "distinct_ts": 3,
        "rows_per_distinct_ts": 166.6667,
        "timespan_minutes": 2.0,
        "avg_net_bps": 60.0,
        "p50_gross_bps": 70.0,
        "p90_gross_bps": 100.0,
        "net_positive_pct": 99.0,
        "order_authority": "NOT_GRANTED",
        "main_cost_gate_adjustment": "NONE",
        "promotion_evidence": False,
    }
    valid_candidate = {
        "side_cell_key": "ma_crossover|NEARUSDT|Sell",
        "strategy_name": "ma_crossover",
        "symbol": "NEARUSDT",
        "side": "Sell",
        "reject_reason_code": "cost_gate_js_demo_negative_edge",
        "learning_lane_action": "LEARNING_PROBE_CANDIDATE",
        "learning_lane_reason": "avg_net_positive_and_median_gross_clears_friction",
        "priority_tier": "MEDIUM_PRIORITY_BOUNDED_DEMO_LEARNING",
        "priority_score": 70.0,
        "priority_components": {"hit_rate_score": 25.0},
        "n": 244,
        "sample_count_for_gate": 244,
        "distinct_ts": 244,
        "rows_per_distinct_ts": 1.0,
        "timespan_minutes": 243.0,
        "avg_net_bps": 16.2197,
        "p50_gross_bps": 13.2,
        "p90_gross_bps": 31.0,
        "net_positive_pct": 99.95,
        "order_authority": "NOT_GRANTED",
        "main_cost_gate_adjustment": "NONE",
        "promotion_evidence": False,
    }
    scorecard["rows"] = [duplicate_inflated, valid_candidate]
    scorecard["probe_candidates"] = [duplicate_inflated, valid_candidate]
    scorecard["profit_opportunity_ranking"] = {
        "schema_version": "cost_gate_profit_opportunity_ranking_v1",
        "status": "PROFIT_LEARNING_CANDIDATES_PRESENT",
        "top_side_cells": [duplicate_inflated, valid_candidate],
    }

    plan = build_plan_from_payload(
        payload,
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
        cfg=LearningLanePolicyConfig(max_probe_side_cells=2, max_total_probe_orders=4),
    )
    review = build_historical_scorecard_review(
        payload,
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
        cfg=HistoricalScorecardReviewConfig(max_side_cells=2),
    )

    assert [row["side_cell_key"] for row in plan["probe_candidates"]] == [
        "ma_crossover|NEARUSDT|Sell"
    ]
    assert plan["probe_candidates"][0]["sample_count_for_gate"] == 244
    assert plan["probe_candidates"][0]["n"] == 244
    assert [row["side_cell_key"] for row in review["historical_probe_candidates"]] == [
        "ma_crossover|NEARUSDT|Sell"
    ]
    assert review["historical_probe_candidates"][0]["sample_count_for_gate"] == 244
    assert "dup_signal|SOLUSDT|Buy" not in [
        row["side_cell_key"] for row in plan["probe_candidates"]
    ]


def test_historical_scorecard_review_prioritizes_candidates_without_authority():
    review = build_historical_scorecard_review(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
        cfg=HistoricalScorecardReviewConfig(max_side_cells=4),
    )

    assert review["schema_version"] == HISTORICAL_REVIEW_SCHEMA_VERSION
    assert review["status"] == "HISTORICAL_COUNTERFACTUAL_CANDIDATES_PRESENT"
    assert review["runtime_evidence_status"] == "NOT_RUNTIME_LEDGER_EVIDENCE"
    assert review["runtime_evidence_required_before_probe_authority"] is True
    assert review["promotion_evidence"] is False
    assert review["order_authority"] == "NOT_GRANTED"
    assert review["main_cost_gate_adjustment"] == "NONE"
    assert [row["side_cell_key"] for row in review["historical_probe_candidates"]] == [
        "ma_crossover|ETHUSDT|Sell",
        "ma_crossover|NEARUSDT|Sell",
    ]
    assert review["historical_keep_blocked_side_cells"][0]["side_cell_key"] == (
        "ma_crossover|BTCUSDT|Buy"
    )


def test_historical_scorecard_review_waits_on_stale_scorecard(tmp_path: Path):
    path = tmp_path / "scorecard.json"
    path.write_text(
        json.dumps(_scorecard_payload("2026-06-20T00:00:00+00:00")),
        encoding="utf-8",
    )

    review = build_historical_scorecard_review_from_file(
        path,
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
        cfg=HistoricalScorecardReviewConfig(max_scorecard_age_hours=6),
    )

    assert review["status"] == "WAIT_FOR_HISTORICAL_SCORECARD_REFRESH"
    assert review["reason"] == "stale_scorecard"
    assert review["historical_candidate_side_cell_count"] == 0
    assert review["historical_probe_candidates"] == []
    assert review["order_authority"] == "NOT_GRANTED"


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


def test_alpha_discovery_does_not_mark_cost_gate_plan_ready_without_runtime_ledger(
    tmp_path: Path,
):
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

    assert discovery["arms"][0]["action"] == "RUN_READ_ONLY_CAPTURE"
    assert discovery["arms"][0]["reason"] == "cost_gate_learning_loop_not_seen"
    assert scorecard["status"] == "NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED"
    assert row["arm_id"] == "cost_gate_demo_learning_lane"
    assert row["blocker_class"] == "data_coverage"
    assert row["primary_blocker"] == "cost_gate_learning_loop_not_running"
    assert row["next_trigger"] == (
        "sync_source_install_learning_lane_cron_enable_runtime_writer_then_observe_reject_rows"
    )
    assert row["operator_actionable"] is False
    assert row["engineering_actionable"] is True
    assert row["main_cost_gate_adjustment"] == "NONE"
    assert row["order_authority"] == "NOT_GRANTED"
    assert row["ledger_status"] == "MISSING"
    assert row["learning_loop_status"] == "NOT_SEEN"
    assert row["learning_loop_heartbeat_present"] is False
    assert row["admission_decision_count"] == 0
    assert row["probe_candidates"][0]["side_cell_key"] == "ma_crossover|ETHUSDT|Sell"


def test_alpha_discovery_blocks_cost_gate_probe_when_source_not_activation_ready(
    tmp_path: Path,
):
    data_dir = tmp_path / "data"
    repo_root = tmp_path / "not_git_repo"
    repo_root.mkdir()
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
        repo_root=repo_root,
        expected_head="249b2ebd",
    )
    discovery = build_discovery_plan(
        [arm],
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )
    row = discovery["profitability_blocker_scorecard"]["arms"][0]

    assert discovery["arms"][0]["action"] == "BLOCK"
    assert discovery["arms"][0]["reason"] == (
        "cost_gate_learning_lane_source_not_activation_ready"
    )
    assert row["blocker_class"] == "source_health"
    assert row["primary_blocker"] == "cost_gate_learning_lane_source_not_activation_ready"
    assert row["next_trigger"] == (
        "sync_runtime_source_to_expected_head_before_cost_gate_learning_activation"
    )
    assert row["operator_actionable"] is False
    assert row["engineering_actionable"] is True
    assert row["learning_lane_source_activation_ready"] is False
    assert row["learning_lane_source_activation_status"] == "MISSING_FILES"
    assert row["learning_lane_git_status"] == "NOT_GIT_REPO"
    assert row["learning_lane_expected_head_status"] == "UNKNOWN_HEAD"
    assert row["ledger_status"] == "MISSING"


def test_alpha_discovery_routes_historical_cost_gate_candidates_to_runtime_capture(
    tmp_path: Path,
):
    data_dir = tmp_path
    scorecard = _scorecard_payload()
    plan = build_plan_from_payload(
        scorecard,
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
    )
    plan_path = data_dir / "cost_gate_learning_lane" / "demo_learning_lane_plan_latest.json"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    scorecard_path = (
        data_dir
        / "cost_gate_counterfactual"
        / "cost_gate_reject_counterfactual_latest.json"
    )
    scorecard_path.parent.mkdir(parents=True)
    scorecard_path.write_text(json.dumps(scorecard), encoding="utf-8")

    arm = collect_cost_gate_learning_lane_arm(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )
    discovery = build_discovery_plan(
        [arm],
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )
    row = discovery["profitability_blocker_scorecard"]["arms"][0]

    assert discovery["arms"][0]["action"] == "RUN_READ_ONLY_CAPTURE"
    assert discovery["arms"][0]["reason"] == (
        "historical_cost_gate_counterfactual_candidates_need_runtime_capture"
    )
    assert row["blocker_class"] == "data_coverage"
    assert row["primary_blocker"] == "historical_cost_gate_candidates_not_runtime_verified"
    assert row["next_trigger"] == (
        "enable_runtime_writer_to_accumulate_reject_outcomes_for_historical_candidates"
    )
    assert row["operator_actionable"] is False
    assert row["engineering_actionable"] is True
    assert row["ledger_status"] == "MISSING"
    assert row["historical_scorecard_review_status"] == (
        "HISTORICAL_COUNTERFACTUAL_CANDIDATES_PRESENT"
    )
    assert row["historical_candidate_side_cell_count"] == 2
    assert row["historical_counterfactual_is_runtime_evidence"] is False
    assert row["order_authority"] == "NOT_GRANTED"
    assert row["main_cost_gate_adjustment"] == "NONE"


def test_alpha_discovery_surfaces_learning_loop_running_without_ledger_rows(
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
    (lane_dir / "reject_materializer_latest.json").write_text(
        json.dumps({
            "schema_version": "cost_gate_reject_materializer_v1",
            "generated_at_utc": "2026-06-21T11:04:00Z",
            "status": "MATERIALIZED_REJECT_ROWS_PRESENT",
            "input_feature_row_count": 20,
            "materialized_record_count": 20,
            "appended_record_count": 0,
            "decision_counts": {"SIDE_CELL_NOT_SELECTED": 20},
        }),
        encoding="utf-8",
    )
    heartbeat = data_dir / "cron_heartbeat" / "cost_gate_learning_lane.last_fire"
    heartbeat.parent.mkdir(parents=True)
    heartbeat.write_text("", encoding="utf-8")
    heartbeat_ts = dt.datetime(2026, 6, 21, 11, 4, tzinfo=dt.timezone.utc).timestamp()
    os.utime(heartbeat, (heartbeat_ts, heartbeat_ts))
    log = data_dir / "logs" / "cost_gate_learning_lane.log"
    log.parent.mkdir(parents=True)
    log.write_text(
        json.dumps({
            "ts_utc": "2026-06-21T11:04:00Z",
            "check": "cost_gate_learning_lane",
            "ledger_row_count": 0,
            "refresh_scorecard": True,
            "scorecard_rc": 0,
            "scorecard_status": "LEARNING_LANE_PROBE_CANDIDATES_PRESENT",
            "scorecard_probe_candidate_count": 2,
            "scorecard_horizon_stability_status": (
                "MULTI_HORIZON_PROFIT_LEARNING_CANDIDATES_PRESENT"
            ),
            "scorecard_horizon_stability_next_trigger": (
                "operator_review_multi_horizon_side_cells_for_bounded_demo_learning_lane"
            ),
            "scorecard_horizon_stability_horizons": [15, 60],
            "refresh_plan": True,
            "plan_rc": 0,
            "plan_policy_status": "READY_FOR_DEMO_LEARNING_PROBE",
            "plan_gate_status": "OPERATOR_REVIEW",
            "plan_selected_probe_candidate_count": 2,
            "refresh_rc": 0,
            "review_rc": 0,
            "review_status": "NO_BLOCKED_SIGNAL_OUTCOMES",
            "review_next_trigger": (
                "run_cost_gate_outcome_refresh_for_blocked_signal_outcomes"
            ),
        })
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

    assert discovery["arms"][0]["action"] == "RUN_READ_ONLY_CAPTURE"
    assert discovery["arms"][0]["reason"] == "cost_gate_learning_loop_running_no_ledger_rows"
    assert row["primary_blocker"] == "cost_gate_learning_loop_running_but_no_reject_rows"
    assert row["next_trigger"] == (
        "verify_runtime_ledger_writer_enabled_or_wait_for_cost_gate_rejects"
    )
    assert row["ledger_status"] == "MISSING"
    assert row["learning_loop_status"] == "RUNNING_NO_LEDGER_ROWS"
    assert row["learning_loop_heartbeat_present"] is True
    assert row["learning_loop_last_ledger_row_count"] == 0
    assert row["learning_loop_refresh_scorecard_enabled"] is True
    assert row["learning_loop_last_scorecard_rc"] == 0
    assert row["learning_loop_last_scorecard_status"] == (
        "LEARNING_LANE_PROBE_CANDIDATES_PRESENT"
    )
    assert row["learning_loop_last_scorecard_probe_candidate_count"] == 2
    assert row["learning_loop_last_scorecard_horizon_stability_status"] == (
        "MULTI_HORIZON_PROFIT_LEARNING_CANDIDATES_PRESENT"
    )
    assert row["learning_loop_last_scorecard_horizon_stability_next_trigger"] == (
        "operator_review_multi_horizon_side_cells_for_bounded_demo_learning_lane"
    )
    assert row["learning_loop_last_scorecard_horizon_stability_horizons"] == [15, 60]
    assert row["learning_loop_refresh_plan_enabled"] is True
    assert row["learning_loop_last_plan_rc"] == 0
    assert row["learning_loop_last_plan_policy_status"] == (
        "READY_FOR_DEMO_LEARNING_PROBE"
    )
    assert row["learning_loop_last_plan_selected_probe_candidate_count"] == 2
    assert row["learning_loop_last_materializer_status"] == (
        "MATERIALIZED_REJECT_ROWS_PRESENT"
    )
    assert row["learning_loop_last_materializer_input_feature_row_count"] == 20
    assert row["learning_loop_last_materialized_record_count"] == 20
    assert row["learning_loop_last_appended_materialized_record_count"] == 0
    assert row["learning_loop_last_materializer_decision_counts"] == {
        "SIDE_CELL_NOT_SELECTED": 20,
    }
    assert row["learning_loop_materializer_latest_error"] is None
    assert row["learning_loop_last_review_status"] == "NO_BLOCKED_SIGNAL_OUTCOMES"


def test_learning_loop_status_falls_back_to_review_artifact_for_top_review_fields(
    tmp_path: Path,
):
    data_dir = tmp_path
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
    )
    lane_dir = data_dir / "cost_gate_learning_lane"
    log_dir = data_dir / "logs"
    lane_dir.mkdir(parents=True)
    log_dir.mkdir(parents=True)
    (lane_dir / "demo_learning_lane_plan_latest.json").write_text(
        json.dumps(plan),
        encoding="utf-8",
    )
    (lane_dir / "blocked_outcome_review_latest.json").write_text(
        json.dumps(
            {
                "schema_version": (
                    "cost_gate_demo_learning_lane_blocked_outcome_review_v3"
                ),
                "status": "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT",
                "next_trigger": (
                    "operator_review_blocked_outcome_scorecard_before_demo_probe_authority"
                ),
                "top_side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "top_side_cell_learning_diagnosis": (
                    "FALSE_NEGATIVE_CANDIDATE_AFTER_COST"
                ),
                "top_side_cell_cost_gate_escape_recommendation": (
                    "operator_review_bounded_probe_authority_without_global_gate_lowering"
                ),
                "top_side_cell_wrongful_block_score": 3.444444,
                "top_side_cell_net_cost_cushion_bps": 5.166667,
                "top_review_candidate_side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "top_review_candidate_learning_diagnosis": (
                    "FALSE_NEGATIVE_CANDIDATE_AFTER_COST"
                ),
                "top_review_candidate_cost_gate_escape_recommendation": (
                    "operator_review_bounded_probe_authority_without_global_gate_lowering"
                ),
                "top_review_candidate_wrongful_block_score": 3.444444,
                "top_review_candidate_net_cost_cushion_bps": 5.166667,
            }
        ),
        encoding="utf-8",
    )
    (log_dir / "cost_gate_learning_lane.log").write_text(
        json.dumps(
            {
                "ts_utc": "2026-06-21T11:00:00Z",
                "check": "cost_gate_learning_lane",
                "scorecard_rc": 0,
                "plan_rc": 0,
                "materializer_rc": 0,
                "refresh_rc": 0,
                "review_rc": 0,
                "ledger_row_count": 3,
                "review_status": "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT",
                "review_next_trigger": (
                    "operator_review_blocked_outcome_scorecard_before_demo_probe_authority"
                ),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    arm = collect_cost_gate_learning_lane_arm(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )
    detail = arm["detail"]

    assert detail["learning_loop_last_review_status"] == (
        "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT"
    )
    assert detail["learning_loop_last_review_top_side_cell_key"] == (
        "ma_crossover|ETHUSDT|Sell"
    )
    assert detail["learning_loop_last_review_top_wrongful_block_score"] == 3.444444
    assert detail["learning_loop_last_review_top_learning_diagnosis"] == (
        "FALSE_NEGATIVE_CANDIDATE_AFTER_COST"
    )
    assert detail[
        "learning_loop_last_review_top_cost_gate_escape_recommendation"
    ] == "operator_review_bounded_probe_authority_without_global_gate_lowering"
    assert detail["learning_loop_last_review_top_candidate_side_cell_key"] == (
        "ma_crossover|ETHUSDT|Sell"
    )
    assert detail["learning_loop_last_review_top_candidate_learning_diagnosis"] == (
        "FALSE_NEGATIVE_CANDIDATE_AFTER_COST"
    )


def test_activation_preflight_reports_not_accumulating_without_runtime_artifacts(
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

    preflight = build_cost_gate_learning_lane_activation_preflight(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )

    assert preflight["schema_version"] == ACTIVATION_PREFLIGHT_SCHEMA_VERSION
    assert preflight["status"] == "NOT_ACCUMULATING"
    assert preflight["reason"] == "plan_present_but_writer_cron_or_ledger_not_observed"
    assert preflight["answers"]["has_accumulated_ledger_rows"] is False
    assert preflight["answers"]["currently_accumulating_evidence"] is False
    assert preflight["answers"]["cost_gate_rejects_recorded"] is False
    assert preflight["answers"]["silent_drop_risk"] is True
    assert preflight["ledger"]["ledger_status"] == "MISSING"
    assert preflight["learning_loop"]["learning_loop_status"] == "NOT_SEEN"
    assert preflight["plan"]["main_cost_gate_adjustment"] == "NONE"
    assert preflight["plan"]["order_authority"] == "NOT_GRANTED"
    assert "probe_ledger_jsonl" in preflight["missing_links"]


def test_activation_preflight_cli_writes_json_output(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    out = tmp_path / "activation_preflight_latest.json"
    repo_root, _remote = _init_source_repo_with_origin(tmp_path)
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    plan = build_plan_from_payload(
        _scorecard_payload(generated_at=now.isoformat()),
        now_utc=now,
    )
    lane_dir = data_dir / "cost_gate_learning_lane"
    lane_dir.mkdir(parents=True)
    (lane_dir / "demo_learning_lane_plan_latest.json").write_text(
        json.dumps(plan),
        encoding="utf-8",
    )

    rc = cost_gate_status_main(
        [
            "--data-dir",
            str(data_dir),
            "--repo-root",
            str(repo_root),
            "--json-output",
            str(out),
        ]
    )

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 0
    assert payload["schema_version"] == ACTIVATION_PREFLIGHT_SCHEMA_VERSION
    assert payload["status"] == "NOT_ACCUMULATING"
    assert payload["answers"]["activation_ready"] is False
    assert payload["boundary"].startswith("read-only activation preflight only")


def test_activation_preflight_rejects_recent_policy_artifact_when_policy_waits(
    tmp_path: Path,
):
    data_dir = tmp_path
    waiting_plan = build_plan_from_payload(
        _scorecard_payload(generated_at="2026-06-19T00:00:00+00:00"),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
    )
    lane_dir = data_dir / "cost_gate_learning_lane"
    lane_dir.mkdir(parents=True)
    (lane_dir / "demo_learning_lane_plan_latest.json").write_text(
        json.dumps(waiting_plan),
        encoding="utf-8",
    )

    preflight = build_cost_gate_learning_lane_activation_preflight(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )

    assert waiting_plan["status"] == "WAIT_FOR_SCORECARD_REFRESH"
    assert preflight["status"] == "PLAN_NOT_READY"
    assert preflight["plan"]["plan_status"] == "POLICY_NOT_READY"
    assert preflight["plan"]["plan_reason"] == (
        "plan_policy_status_WAIT_FOR_SCORECARD_REFRESH"
    )
    assert preflight["plan"]["plan_policy_status"] == "WAIT_FOR_SCORECARD_REFRESH"
    assert "demo_learning_lane_plan_latest" in preflight["activation_blockers"]


def test_activation_preflight_requires_selected_probe_candidates_in_plan(
    tmp_path: Path,
):
    data_dir = tmp_path
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
    )
    plan["selected_probe_candidate_count"] = 0
    plan["probe_candidates"] = []
    lane_dir = data_dir / "cost_gate_learning_lane"
    lane_dir.mkdir(parents=True)
    (lane_dir / "demo_learning_lane_plan_latest.json").write_text(
        json.dumps(plan),
        encoding="utf-8",
    )

    preflight = build_cost_gate_learning_lane_activation_preflight(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )

    assert preflight["status"] == "PLAN_NOT_READY"
    assert preflight["plan"]["plan_status"] == "NO_SELECTED_CANDIDATES"
    assert preflight["plan"]["plan_reason"] == "plan_has_no_selected_probe_candidates"
    assert "demo_learning_lane_plan_latest" in preflight["activation_blockers"]


def test_activation_preflight_surfaces_historical_scorecard_candidates(
    tmp_path: Path,
):
    data_dir = tmp_path
    scorecard = _scorecard_payload()
    plan = build_plan_from_payload(
        scorecard,
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
    )
    lane_dir = data_dir / "cost_gate_learning_lane"
    lane_dir.mkdir(parents=True)
    (lane_dir / "demo_learning_lane_plan_latest.json").write_text(
        json.dumps(plan),
        encoding="utf-8",
    )
    scorecard_path = (
        data_dir
        / "cost_gate_counterfactual"
        / "cost_gate_reject_counterfactual_latest.json"
    )
    scorecard_path.parent.mkdir(parents=True)
    scorecard_path.write_text(json.dumps(scorecard), encoding="utf-8")

    preflight = build_cost_gate_learning_lane_activation_preflight(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )

    assert preflight["status"] == "NOT_ACCUMULATING"
    assert preflight["answers"]["historical_counterfactual_review_available"] is True
    assert preflight["answers"]["historical_counterfactual_candidates_present"] is True
    assert preflight["answers"]["historical_counterfactual_is_runtime_evidence"] is False
    assert preflight["historical_review"]["historical_scorecard_review_status"] == (
        "HISTORICAL_COUNTERFACTUAL_CANDIDATES_PRESENT"
    )
    assert preflight["historical_review"]["historical_candidate_side_cell_count"] == 2
    assert preflight["historical_review"]["historical_scorecard_review"][
        "order_authority"
    ] == "NOT_GRANTED"


def test_writer_config_reports_enabled_env_file_paths(tmp_path: Path):
    data_dir = tmp_path / "data"
    plan_path = tmp_path / "runtime_plan.json"
    ledger_path = tmp_path / "runtime_ledger.jsonl"
    env_file = tmp_path / "runtime.env"
    env_file.write_text(
        "\n".join(
            [
                'export OPENCLAW_DEMO_LEARNING_LANE_WRITER="true"',
                f"OPENCLAW_DEMO_LEARNING_LANE_PLAN={plan_path}",
                f"OPENCLAW_DEMO_LEARNING_LANE_LEDGER='{ledger_path}'",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = summarize_cost_gate_learning_lane_writer_config(
        data_dir,
        env_file=env_file,
        require_writer_enabled=True,
    )

    assert config["writer_config_status"] == "ENABLED"
    assert config["writer_enabled"] is True
    assert config["writer_required_for_activation"] is True
    assert config["writer_env_source"] == "env_file"
    assert config["plan_path"] == str(plan_path)
    assert config["plan_path_source"] == "env_override"
    assert config["ledger_path"] == str(ledger_path)
    assert config["ledger_path_source"] == "env_override"


def test_writer_config_reports_invalid_enable_value(tmp_path: Path):
    config = summarize_cost_gate_learning_lane_writer_config(
        tmp_path,
        env={"OPENCLAW_DEMO_LEARNING_LANE_WRITER": "maybe"},
    )

    assert config["writer_config_status"] == "INVALID"
    assert config["writer_enabled"] is None
    assert config["writer_bool_error"] == "invalid_bool"


def test_activation_preflight_can_require_runtime_writer_enabled(tmp_path: Path):
    repo, _remote = _init_source_repo_with_origin(tmp_path)
    data_dir = tmp_path / "data"
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
    env_file = tmp_path / "runtime.env"
    env_file.write_text(
        "OPENCLAW_DEMO_LEARNING_LANE_WRITER=0\n",
        encoding="utf-8",
    )

    preflight = build_cost_gate_learning_lane_activation_preflight(
        data_dir,
        repo_root=repo,
        runtime_env_file=env_file,
        require_writer_enabled=True,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )

    assert preflight["writer_config"]["writer_config_status"] == "DISABLED"
    assert preflight["answers"]["runtime_writer_enabled"] is False
    assert preflight["answers"]["runtime_writer_config_required"] is True
    assert preflight["answers"]["writer_disabled_or_unset_drop_risk"] is True
    assert "runtime_writer_not_enabled" in preflight["activation_blockers"]
    assert preflight["answers"]["activation_ready"] is False


def test_activation_preflight_accepts_runtime_writer_enabled_env_file(tmp_path: Path):
    repo, _remote = _init_source_repo_with_origin(tmp_path)
    data_dir = tmp_path / "data"
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
    env_file = tmp_path / "runtime.env"
    env_file.write_text(
        "OPENCLAW_DEMO_LEARNING_LANE_WRITER=1\n",
        encoding="utf-8",
    )

    preflight = build_cost_gate_learning_lane_activation_preflight(
        data_dir,
        repo_root=repo,
        runtime_env_file=env_file,
        require_writer_enabled=True,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )

    assert preflight["writer_config"]["writer_config_status"] == "ENABLED"
    assert preflight["answers"]["runtime_writer_enabled"] is True
    assert preflight["answers"]["runtime_writer_config_required"] is True
    assert preflight["answers"]["writer_disabled_or_unset_drop_risk"] is False
    assert "runtime_writer_not_enabled" not in preflight["activation_blockers"]


def test_writer_process_reports_enabled_proc_environ_paths(tmp_path: Path):
    data_dir = tmp_path / "data"
    proc_env = tmp_path / "environ"
    proc_env.write_bytes(
        b"OPENCLAW_DEMO_LEARNING_LANE_WRITER=1\0"
        b"OPENCLAW_DEMO_LEARNING_LANE_PLAN=/tmp/runtime_plan.json\0"
        b"OPENCLAW_DEMO_LEARNING_LANE_LEDGER=/tmp/runtime_ledger.jsonl\0"
    )

    process = summarize_cost_gate_learning_lane_writer_process(
        data_dir,
        proc_environ_file=proc_env,
        require_writer_enabled=True,
    )

    assert process["writer_process_checked"] is True
    assert process["writer_process_status"] == "ENABLED"
    assert process["writer_process_enabled"] is True
    assert process["writer_env_value"] == "1"
    assert process["plan_path"] == "/tmp/runtime_plan.json"
    assert process["ledger_path"] == "/tmp/runtime_ledger.jsonl"


def test_writer_process_reports_unreadable_proc_environ(tmp_path: Path):
    process = summarize_cost_gate_learning_lane_writer_process(
        tmp_path,
        proc_environ_file=tmp_path / "missing-environ",
        require_writer_enabled=True,
    )

    assert process["writer_process_checked"] is False
    assert process["writer_process_status"] == "PROC_ENVIRON_UNREADABLE"
    assert process["writer_process_enabled"] is None
    assert process["proc_environ_error"] == "missing"


def test_writer_process_auto_detect_reports_not_found(tmp_path: Path):
    proc_root = tmp_path / "proc"
    shell_proc = proc_root / "101"
    shell_proc.mkdir(parents=True)
    shell_proc.joinpath("cmdline").write_bytes(
        b"bash\0-c\0pgrep -af openclaw-engine\0"
    )

    process = summarize_cost_gate_learning_lane_writer_process(
        tmp_path,
        auto_detect_engine_pid=True,
        proc_root=proc_root,
        require_writer_enabled=True,
    )

    assert process["writer_process_checked"] is False
    assert process["writer_process_status"] == "ENGINE_PROCESS_NOT_FOUND"
    assert process["writer_process_reason"] == "openclaw_engine_process_not_found"
    assert process["engine_pid_detection_status"] == "NOT_FOUND"
    assert process["engine_pid_candidate_count"] == 0


def test_writer_process_auto_detects_exact_openclaw_engine_cmdline(tmp_path: Path):
    proc_root = tmp_path / "proc"
    fake_shell = proc_root / "101"
    fake_shell.mkdir(parents=True)
    fake_shell.joinpath("cmdline").write_bytes(
        b"bash\0-c\0pgrep -af openclaw-engine\0"
    )
    fake_engine = proc_root / "202"
    fake_engine.mkdir()
    fake_engine.joinpath("cmdline").write_bytes(
        b"rust/target/release/openclaw-engine\0"
    )
    fake_engine.joinpath("environ").write_bytes(
        b"OPENCLAW_DEMO_LEARNING_LANE_WRITER=1\0"
    )

    process = summarize_cost_gate_learning_lane_writer_process(
        tmp_path,
        auto_detect_engine_pid=True,
        proc_root=proc_root,
    )

    assert process["engine_pid_detection_status"] == "FOUND"
    assert process["engine_pid_candidate_count"] == 1
    assert process["engine_pid_detected"] == 202
    assert process["engine_pid"] == 202
    assert process["writer_process_status"] == "ENABLED"
    assert process["writer_process_enabled"] is True


def test_activation_preflight_can_require_running_process_writer_enabled(
    tmp_path: Path,
):
    repo, _remote = _init_source_repo_with_origin(tmp_path)
    data_dir = tmp_path / "data"
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
    env_file = tmp_path / "runtime.env"
    env_file.write_text(
        "OPENCLAW_DEMO_LEARNING_LANE_WRITER=1\n",
        encoding="utf-8",
    )
    proc_env = tmp_path / "environ"
    proc_env.write_bytes(b"OPENCLAW_DEMO_LEARNING_LANE_WRITER=0\0")

    preflight = build_cost_gate_learning_lane_activation_preflight(
        data_dir,
        repo_root=repo,
        runtime_env_file=env_file,
        runtime_proc_environ=proc_env,
        require_writer_enabled=True,
        require_process_writer_enabled=True,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )

    assert preflight["answers"]["runtime_writer_enabled"] is True
    assert preflight["answers"]["runtime_writer_process_checked"] is True
    assert preflight["answers"]["runtime_writer_process_enabled"] is False
    assert preflight["answers"]["runtime_writer_process_status"] == "DISABLED"
    assert preflight["answers"]["running_engine_writer_disabled_or_unset_drop_risk"] is True
    assert "runtime_writer_not_enabled" not in preflight["activation_blockers"]
    assert "running_engine_writer_not_enabled" in preflight["activation_blockers"]


def test_activation_preflight_can_auto_detect_disabled_running_process(
    tmp_path: Path,
):
    repo, _remote = _init_source_repo_with_origin(tmp_path)
    data_dir = tmp_path / "data"
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
    proc_root = tmp_path / "proc"
    engine_proc = proc_root / "303"
    engine_proc.mkdir(parents=True)
    engine_proc.joinpath("cmdline").write_bytes(
        b"/home/ncyu/BybitOpenClaw/srv/rust/target/release/openclaw-engine\0"
    )
    engine_proc.joinpath("environ").write_bytes(
        b"OPENCLAW_DEMO_LEARNING_LANE_WRITER=0\0"
    )

    preflight = build_cost_gate_learning_lane_activation_preflight(
        data_dir,
        repo_root=repo,
        auto_detect_engine_pid=True,
        proc_root=proc_root,
        require_process_writer_enabled=True,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )

    assert preflight["writer_process"]["engine_pid_detection_status"] == "FOUND"
    assert preflight["writer_process"]["engine_pid_detected"] == 303
    assert preflight["answers"]["runtime_writer_process_checked"] is True
    assert preflight["answers"]["runtime_writer_process_status"] == "DISABLED"
    assert "running_engine_writer_not_enabled" in preflight["activation_blockers"]


def test_activation_preflight_requires_process_check_when_requested(tmp_path: Path):
    repo, _remote = _init_source_repo_with_origin(tmp_path)
    data_dir = tmp_path / "data"
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

    preflight = build_cost_gate_learning_lane_activation_preflight(
        data_dir,
        repo_root=repo,
        require_process_writer_enabled=True,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )

    assert preflight["writer_process"]["writer_process_status"] == "NOT_CHECKED"
    assert preflight["answers"]["runtime_writer_process_checked"] is False
    assert preflight["answers"]["runtime_writer_process_enabled"] is False
    assert preflight["answers"]["running_engine_writer_disabled_or_unset_drop_risk"] is True
    assert "running_engine_writer_not_enabled" in preflight["activation_blockers"]


def test_activation_preflight_reports_loop_running_without_ledger_rows(
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
    heartbeat = data_dir / "cron_heartbeat" / "cost_gate_learning_lane.last_fire"
    heartbeat.parent.mkdir(parents=True)
    heartbeat.write_text("", encoding="utf-8")
    heartbeat_ts = dt.datetime(2026, 6, 21, 11, 4, tzinfo=dt.timezone.utc).timestamp()
    os.utime(heartbeat, (heartbeat_ts, heartbeat_ts))
    log = data_dir / "logs" / "cost_gate_learning_lane.log"
    log.parent.mkdir(parents=True)
    log.write_text(
        json.dumps({
            "ts_utc": "2026-06-21T11:04:00Z",
            "check": "cost_gate_learning_lane",
            "ledger_row_count": 0,
            "refresh_scorecard": True,
            "scorecard_rc": 0,
            "scorecard_status": "LEARNING_LANE_PROBE_CANDIDATES_PRESENT",
            "scorecard_probe_candidate_count": 2,
            "scorecard_horizon_stability_status": (
                "MULTI_HORIZON_PROFIT_LEARNING_CANDIDATES_PRESENT"
            ),
            "scorecard_horizon_stability_next_trigger": (
                "operator_review_multi_horizon_side_cells_for_bounded_demo_learning_lane"
            ),
            "scorecard_horizon_stability_horizons": [15, 60],
            "refresh_plan": True,
            "plan_rc": 0,
            "plan_policy_status": "READY_FOR_DEMO_LEARNING_PROBE",
            "plan_gate_status": "OPERATOR_REVIEW",
            "plan_selected_probe_candidate_count": 2,
            "materialize_rejects": True,
            "append_materialized_rejects": False,
            "materializer_rc": 0,
            "materializer_status": "MATERIALIZED_REJECT_ROWS_PRESENT",
            "materializer_input_feature_row_count": 20,
            "materializer_materialized_record_count": 20,
            "materializer_appended_record_count": 0,
            "materializer_decision_counts": {"SIDE_CELL_NOT_SELECTED": 20},
            "refresh_rc": 0,
            "review_rc": 0,
            "review_status": "NO_BLOCKED_SIGNAL_OUTCOMES",
        })
        + "\n",
        encoding="utf-8",
    )

    preflight = build_cost_gate_learning_lane_activation_preflight(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )

    assert preflight["status"] == "LOOP_RUNNING_NO_LEDGER_ROWS"
    assert preflight["reason"] == "learning_loop_recent_but_no_probe_ledger_rows"
    assert preflight["learning_loop"]["learning_loop_status"] == "RUNNING_NO_LEDGER_ROWS"
    assert preflight["learning_loop"]["learning_loop_refresh_scorecard_enabled"] is True
    assert preflight["learning_loop"]["learning_loop_last_scorecard_rc"] == 0
    assert preflight["learning_loop"]["learning_loop_last_scorecard_status"] == (
        "LEARNING_LANE_PROBE_CANDIDATES_PRESENT"
    )
    assert preflight["learning_loop"][
        "learning_loop_last_scorecard_probe_candidate_count"
    ] == 2
    assert preflight["learning_loop"][
        "learning_loop_last_scorecard_horizon_stability_status"
    ] == "MULTI_HORIZON_PROFIT_LEARNING_CANDIDATES_PRESENT"
    assert preflight["learning_loop"][
        "learning_loop_last_scorecard_horizon_stability_next_trigger"
    ] == "operator_review_multi_horizon_side_cells_for_bounded_demo_learning_lane"
    assert preflight["learning_loop"][
        "learning_loop_last_scorecard_horizon_stability_horizons"
    ] == [15, 60]
    assert preflight["learning_loop"]["learning_loop_refresh_plan_enabled"] is True
    assert preflight["learning_loop"]["learning_loop_last_plan_rc"] == 0
    assert preflight["learning_loop"]["learning_loop_last_plan_policy_status"] == (
        "READY_FOR_DEMO_LEARNING_PROBE"
    )
    assert preflight["learning_loop"][
        "learning_loop_last_plan_selected_probe_candidate_count"
    ] == 2
    assert preflight["learning_loop"]["learning_loop_last_materializer_status"] == (
        "MATERIALIZED_REJECT_ROWS_PRESENT"
    )
    assert preflight["learning_loop"]["learning_loop_last_materialized_record_count"] == 20
    assert preflight["learning_loop"][
        "learning_loop_last_appended_materialized_record_count"
    ] == 0
    assert preflight["learning_loop"]["learning_loop_last_materializer_decision_counts"] == {
        "SIDE_CELL_NOT_SELECTED": 20,
    }
    assert preflight["answers"]["reject_materializer_ran"] is True
    assert preflight["answers"]["reject_materializer_enabled"] is True
    assert preflight["answers"]["reject_materializer_append_enabled"] is False
    assert preflight["answers"]["reject_materializer_latest_available"] is False
    assert preflight["answers"]["reject_materializer_materialized_records"] == 20
    assert preflight["answers"]["reject_materializer_appended_records"] == 0
    assert preflight["answers"]["silent_drop_risk"] is True
    assert "runtime_ledger_writer_or_recent_cost_gate_reject_rows" in preflight["missing_links"]


def test_activation_preflight_treats_plan_refresh_failure_as_loop_error(
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
    log = data_dir / "logs" / "cost_gate_learning_lane.log"
    log.parent.mkdir(parents=True)
    log.write_text(
        json.dumps({
            "ts_utc": "2026-06-21T11:04:00Z",
            "check": "cost_gate_learning_lane",
            "ledger_row_count": 0,
            "refresh_scorecard": True,
            "scorecard_rc": 0,
            "refresh_plan": True,
            "plan_rc": 7,
            "materialize_rejects": True,
            "append_materialized_rejects": True,
            "materializer_rc": 0,
            "refresh_rc": 0,
            "review_rc": 0,
            "review_status": "NO_BLOCKED_SIGNAL_OUTCOMES",
        })
        + "\n",
        encoding="utf-8",
    )

    preflight = build_cost_gate_learning_lane_activation_preflight(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )

    assert preflight["status"] == "LEARNING_LOOP_ERROR"
    assert preflight["learning_loop"]["learning_loop_status"] == "ERROR"
    assert preflight["learning_loop"]["learning_loop_last_plan_rc"] == 7
    assert preflight["learning_loop"]["learning_loop_reason"] == (
        "cost_gate_learning_scorecard_plan_materializer_refresh_review_or_"
        "bounded_authorization_failed"
    )
    assert "cost_gate_learning_lane_cron_health" in preflight["missing_links"]


def test_activation_preflight_treats_scorecard_refresh_failure_as_loop_error(
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
    log = data_dir / "logs" / "cost_gate_learning_lane.log"
    log.parent.mkdir(parents=True)
    log.write_text(
        json.dumps({
            "ts_utc": "2026-06-21T11:04:00Z",
            "check": "cost_gate_learning_lane",
            "ledger_row_count": 0,
            "refresh_scorecard": True,
            "scorecard_rc": 9,
            "refresh_plan": True,
            "plan_rc": 0,
            "materialize_rejects": True,
            "append_materialized_rejects": True,
            "materializer_rc": 0,
            "refresh_rc": 0,
            "review_rc": 0,
            "review_status": "NO_BLOCKED_SIGNAL_OUTCOMES",
        })
        + "\n",
        encoding="utf-8",
    )

    preflight = build_cost_gate_learning_lane_activation_preflight(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )

    assert preflight["status"] == "LEARNING_LOOP_ERROR"
    assert preflight["learning_loop"]["learning_loop_status"] == "ERROR"
    assert preflight["learning_loop"]["learning_loop_last_scorecard_rc"] == 9
    assert preflight["learning_loop"]["learning_loop_reason"] == (
        "cost_gate_learning_scorecard_plan_materializer_refresh_review_or_"
        "bounded_authorization_failed"
    )
    assert "cost_gate_learning_lane_cron_health" in preflight["missing_links"]


def test_activation_preflight_routes_admission_only_ledger_to_outcome_refresh(
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
    log = data_dir / "logs" / "cost_gate_learning_lane.log"
    log.parent.mkdir(parents=True)
    log.write_text(
        json.dumps({
            "ts_utc": "2026-06-21T11:04:00Z",
            "ledger_row_count": 1,
            "refresh_rc": 0,
            "review_rc": 0,
            "review_status": "NO_BLOCKED_SIGNAL_OUTCOMES",
        })
        + "\n",
        encoding="utf-8",
    )

    preflight = build_cost_gate_learning_lane_activation_preflight(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )

    assert preflight["status"] == "ADMISSION_ONLY_NEEDS_OUTCOME_REFRESH"
    assert preflight["answers"]["has_accumulated_ledger_rows"] is True
    assert preflight["answers"]["currently_accumulating_evidence"] is True
    assert preflight["answers"]["cost_gate_rejects_recorded"] is True
    assert preflight["answers"]["silent_drop_risk"] is False
    assert preflight["ledger"]["ledger_status"] == "ADMISSION_ROWS_PRESENT"
    assert preflight["next_actions"] == [
        "run_cost_gate_outcome_refresh_for_blocked_signal_outcomes"
    ]


def test_activation_preflight_routes_capture_error_rows_to_writer_config_fix(
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
                "schema_version": "cost_gate_demo_learning_lane_adapter_v1",
                "record_type": "probe_capture_error",
                "generated_at_utc": "2026-06-21T11:02:00+00:00",
                "attempt_id": "ctx-demo-ma_crossover-ETHUSDT-1782037200000",
                "decision": "ADMISSION_NOT_EVALUATED",
                "allowed_to_submit_order": False,
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "event": _selected_reject_event(),
                "runtime_state": {"risk_state": "NORMAL"},
                "capture_error": "read plan /tmp/openclaw/cost_gate_learning_lane/demo_learning_lane_plan_latest.json failed: missing",
                "reason": "runtime_admission_evaluation_failed",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    preflight = build_cost_gate_learning_lane_activation_preflight(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )

    assert preflight["status"] == "CAPTURE_ERRORS_NEED_OPERATOR_FIX"
    assert preflight["reason"] == "rejects_captured_but_admission_evaluation_failed"
    assert preflight["answers"]["has_accumulated_ledger_rows"] is True
    assert preflight["answers"]["cost_gate_rejects_recorded"] is True
    assert preflight["answers"]["admission_evaluation_errors_recorded"] is True
    assert preflight["answers"]["silent_drop_risk"] is False
    assert preflight["ledger"]["ledger_status"] == "CAPTURE_ERRORS_PRESENT"
    assert preflight["ledger"]["capture_error_count"] == 1
    assert preflight["ledger"]["captured_reject_count"] == 1
    assert preflight["ledger"]["latest_admission_decision"] == "ADMISSION_NOT_EVALUATED"
    assert "read plan" in preflight["ledger"]["latest_capture_error"]
    assert "demo_learning_lane_plan_or_writer_config" in preflight["missing_links"]


def test_activation_preflight_surfaces_blocked_outcome_review_candidate(
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
    # F1:30 個 distinct entry(n_eff=30 ≥ 預註冊 §3 E1 門檻;每日 5 個、1h 間距
    # 非重疊,跨 6 UTC 日過 E2/E3),avg 維持 11.5(tight-positive 循環值,BH 過)。
    _blocked_fixture_rows = [
        (
            f"blocked-{index + 1}",
            f"2026-06-21T13:{index:02d}:00+00:00",
            net + 4.0,
            net,
        )
        for index, net in enumerate([12.5, 11.5, 10.5, 12.0, 11.0] * 6)
    ]
    ledger_rows = [
        {
            "record_type": "blocked_signal_outcome",
            "cost_model_version": "conservative_v1",
            "generated_at_utc": generated_at,
            "attempt_id": attempt_id,
            "side_cell_key": "ma_crossover|ETHUSDT|Sell",
            "strategy_name": "ma_crossover",
            "symbol": "ETHUSDT",
            "side": "Sell",
            "entry_ts_ms": (
                1_781_956_800_000
                - (index // 5) * 86_400_000
                + (index % 5) * 3_600_000
            ),
            "gross_bps": gross,
            "cost_bps": 4.0,
            "realized_net_bps": net,
            "horizon_minutes": 60,
        }
        for index, (attempt_id, generated_at, gross, net) in enumerate(
            _blocked_fixture_rows
        )
    ]
    (lane_dir / "probe_ledger.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in ledger_rows),
        encoding="utf-8",
    )

    preflight = build_cost_gate_learning_lane_activation_preflight(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 14, 30, tzinfo=dt.timezone.utc),
    )

    assert preflight["status"] == "REVIEW_CANDIDATE_OPERATOR_REVIEW"
    assert preflight["answers"]["blocked_signal_outcomes_recorded"] is True
    assert preflight["answers"]["blocked_signal_profitability_review_available"] is True
    assert preflight["ledger"]["blocked_signal_outcome_review_status"] == (
        "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT"
    )
    assert preflight["ledger"]["blocked_signal_outcome_review_schema_version"] == (
        "cost_gate_demo_learning_lane_blocked_outcome_review_v5"
    )
    assert preflight["ledger"]["blocked_signal_top_review_side_cell_key"] == (
        "ma_crossover|ETHUSDT|Sell"
    )
    assert preflight["ledger"]["blocked_signal_top_review_candidate_side_cell_key"] == (
        "ma_crossover|ETHUSDT|Sell"
    )
    # P2-8/F1:tight-positive [12.5,11.5,10.5,12.0,11.0](通過 BH-FDR、n_eff=5),
    # avg=11.5 → cushion=11.5、wrongful_block_score=11.5(sample_factor=1)。
    assert round(
        preflight["ledger"]["blocked_signal_top_review_wrongful_block_score"],
        6,
    ) == 11.5
    assert round(
        preflight["ledger"]["blocked_signal_top_review_net_cost_cushion_bps"],
        6,
    ) == 11.5
    assert preflight["next_actions"] == [
        "operator_review_blocked_outcome_scorecard_before_demo_probe_authority"
    ]


def test_activation_preflight_fails_closed_when_source_files_missing(
    tmp_path: Path,
):
    data_dir = tmp_path / "data"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
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

    preflight = build_cost_gate_learning_lane_activation_preflight(
        data_dir,
        repo_root=repo_root,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )

    assert preflight["status"] == "SOURCE_NOT_READY"
    assert preflight["source"]["source_ready"] is False
    assert preflight["source"]["source_status"] == "MISSING_FILES"
    assert "source_sync" in preflight["missing_links"]


def test_source_summary_blocks_activation_when_checkout_dirty(tmp_path: Path):
    repo, _remote = _init_source_repo_with_origin(tmp_path)
    dirty_path = repo / "helper_scripts/research/cost_gate_learning_lane/status.py"
    dirty_path.write_text('"""dirty fixture source file."""\n', encoding="utf-8")

    source = summarize_cost_gate_learning_lane_source(repo)

    assert source["source_status"] == "READY"
    assert source["source_ready"] is True
    assert source["source_activation_status"] == "DIRTY"
    assert source["source_activation_ready"] is False
    assert source["git_status"] == "DIRTY"
    assert source["git_dirty_path_count"] == 1
    assert source["git_behind_count"] == 0
    assert source["source_reconcile_required"] is True
    assert source["source_reconcile_status"] == "DIRTY_PATH_REVIEW_REQUIRED"
    assert source["source_reconcile_reasons"] == ["dirty_or_untracked_paths_present"]
    assert source["source_reconcile_next_actions"] == [
        "operator_review_dirty_paths_before_sync",
        "preserve_or_discard_runtime_local_changes",
        "rerun_activation_preflight_after_reconcile",
    ]
    assert source["git_dirty_status_counts"] == {"M": 1}
    assert source["source_reconcile_dirty_manifest"] == [
        {
            "status_code": "M",
            "path": "helper_scripts/research/cost_gate_learning_lane/status.py",
            "old_path": None,
            "category": "tracked_change",
            "action_hint": "review_tracked_change_before_runtime_source_sync",
        }
    ]


def test_source_summary_blocks_activation_when_checkout_behind_upstream(
    tmp_path: Path,
):
    repo, remote = _init_source_repo_with_origin(tmp_path)
    other = tmp_path / "other"
    subprocess.run(
        ["git", "clone", "--branch", "main", str(remote), str(other)],
        check=True,
        text=True,
        capture_output=True,
    )
    _git(other, "config", "user.email", "test@example.invalid")
    _git(other, "config", "user.name", "Test User")
    extra = other / "extra.txt"
    extra.write_text("new upstream commit\n", encoding="utf-8")
    _git(other, "add", "extra.txt")
    _git(other, "commit", "-m", "upstream")
    _git(other, "push", "origin", "main")
    _git(repo, "fetch", "origin")

    source = summarize_cost_gate_learning_lane_source(repo)

    assert source["source_status"] == "READY"
    assert source["source_ready"] is True
    assert source["source_activation_status"] == "BEHIND_UPSTREAM"
    assert source["source_activation_ready"] is False
    assert source["git_status"] == "BEHIND_UPSTREAM"
    assert source["git_ahead_count"] == 0
    assert source["git_behind_count"] == 1
    assert source["source_reconcile_required"] is True
    assert source["source_reconcile_status"] == "SOURCE_SYNC_REQUIRED"
    assert source["source_reconcile_reasons"] == ["checkout_behind_upstream"]
    assert source["source_reconcile_next_actions"] == [
        "sync_runtime_source_to_pm_approved_head",
        "rerun_activation_preflight_after_reconcile",
    ]
    assert source["source_reconcile_dirty_manifest"] == []


def test_source_summary_honors_expected_head_when_checkout_matches(
    tmp_path: Path,
):
    repo, _remote = _init_source_repo_with_origin(tmp_path)
    head = _git_output(repo, "rev-parse", "HEAD")

    source = summarize_cost_gate_learning_lane_source(repo, expected_head=head[:12])

    assert source["source_status"] == "READY"
    assert source["source_activation_status"] == "SYNCED_CLEAN"
    assert source["source_activation_ready"] is True
    assert source["git_status"] == "SYNCED_CLEAN"
    assert source["expected_head_status"] == "MATCH"
    assert source["expected_head_matches"] is True
    assert source["source_reconcile_required"] is False
    assert source["source_reconcile_status"] == "SOURCE_RECONCILE_NOT_REQUIRED"
    assert source["source_reconcile_next_actions"] == ["no_source_reconcile_required"]


def test_source_summary_blocks_activation_when_expected_head_mismatches(
    tmp_path: Path,
):
    repo, _remote = _init_source_repo_with_origin(tmp_path)

    source = summarize_cost_gate_learning_lane_source(
        repo,
        expected_head="deadbee",
    )

    assert source["source_status"] == "READY"
    assert source["source_activation_status"] == "EXPECTED_HEAD_MISMATCH"
    assert source["source_activation_ready"] is False
    assert source["git_status"] == "EXPECTED_HEAD_MISMATCH"
    assert source["expected_head_status"] == "MISMATCH"
    assert source["expected_head_matches"] is False
    assert source["expected_head_error"] == (
        "current_git_head_does_not_match_expected_head"
    )


def test_activation_preflight_reports_expected_head_mismatch_blocker(
    tmp_path: Path,
):
    data_dir = tmp_path / "data"
    repo, _remote = _init_source_repo_with_origin(tmp_path)
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

    preflight = build_cost_gate_learning_lane_activation_preflight(
        data_dir,
        repo_root=repo,
        expected_head="deadbee",
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )

    assert preflight["source"]["expected_head_status"] == "MISMATCH"
    assert preflight["answers"]["runtime_source_ready_for_activation"] is False
    assert "expected_source_head_mismatch" in preflight["activation_blockers"]
    assert "source_checkout_not_synced_clean" in preflight["activation_blockers"]


def test_alpha_discovery_keeps_stale_cost_gate_plan_as_source_health_blocker(
    tmp_path: Path,
):
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
        now_utc=dt.datetime(2026, 6, 23, 11, 5, tzinfo=dt.timezone.utc),
        max_age_seconds=60,
    )
    discovery = build_discovery_plan(
        [arm],
        now_utc=dt.datetime(2026, 6, 23, 11, 5, tzinfo=dt.timezone.utc),
    )
    row = discovery["profitability_blocker_scorecard"]["arms"][0]

    assert discovery["arms"][0]["action"] == "BLOCK"
    assert discovery["arms"][0]["reason"] == "source_not_healthy"
    assert row["blocker_class"] == "source_health"
    assert row["primary_blocker"] == "source_not_healthy:stale_artifact"


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
                "cost_model_version": "conservative_v1",
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

    assert discovery["arms"][0]["action"] == "RUN_READ_ONLY_CAPTURE"
    assert discovery["arms"][0]["reason"] == "cost_gate_blocked_outcomes_below_review_gate"
    assert discovery["profitability_blocker_scorecard"]["status"] == (
        "NO_ACTIONABLE_ALPHA_WAIT_OR_SAMPLE_GATED"
    )
    assert row["blocker_class"] == "sample_gate"
    assert row["primary_blocker"] == "cost_gate_blocked_signal_outcomes_accumulating"
    assert row["next_trigger"] == (
        "continue_recording_and_refreshing_blocked_signal_outcomes"
    )
    assert row["ledger_status"] == "BLOCKED_SIGNAL_OUTCOMES_PRESENT"
    assert row["admission_decision_count"] == 1
    assert row["order_authority_not_granted_count"] == 1
    assert row["blocked_signal_outcome_count"] == 1
    assert row["blocked_signal_positive_outcome_count"] == 1
    assert row["avg_blocked_signal_outcome_net_bps"] == 12.5
    assert row["blocked_signal_net_positive_pct"] == 100.0
    assert row["blocked_signal_outcome_review_status"] == (
        "COLLECT_MORE_BLOCKED_SIGNAL_OUTCOMES"
    )
    assert row["blocked_signal_outcome_review"]["review_candidate_side_cell_count"] == 0


def test_alpha_discovery_surfaces_cost_gate_capture_errors(tmp_path: Path):
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
                "schema_version": "cost_gate_demo_learning_lane_adapter_v1",
                "record_type": "probe_capture_error",
                "generated_at_utc": "2026-06-21T11:02:00+00:00",
                "attempt_id": "ctx-demo-ma_crossover-ETHUSDT-1782037200000",
                "decision": "ADMISSION_NOT_EVALUATED",
                "allowed_to_submit_order": False,
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "event": _selected_reject_event(),
                "runtime_state": {"risk_state": "NORMAL"},
                "capture_error": "parse plan /tmp/openclaw/cost_gate_learning_lane/demo_learning_lane_plan_latest.json failed: expected value",
                "reason": "runtime_admission_evaluation_failed",
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

    assert discovery["arms"][0]["action"] == "RUN_READ_ONLY_CAPTURE"
    assert discovery["arms"][0]["reason"] == "cost_gate_capture_errors_present"
    assert row["blocker_class"] == "data_coverage"
    assert row["primary_blocker"] == (
        "cost_gate_rejects_captured_but_admission_not_evaluated"
    )
    assert row["next_trigger"] == "inspect_demo_learning_lane_plan_and_writer_config"
    assert row["ledger_status"] == "CAPTURE_ERRORS_PRESENT"
    assert row["capture_error_count"] == 1
    assert row["captured_reject_count"] == 1
    assert "parse plan" in row["latest_capture_error"]


def test_alpha_discovery_routes_positive_blocked_outcome_review_candidate(
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
    ledger_rows = [
        {
            "record_type": "probe_admission_decision",
            "generated_at_utc": "2026-06-21T11:02:00+00:00",
            "attempt_id": "ctx-demo-ma_crossover-ETHUSDT-admission",
            "decision": "ORDER_AUTHORITY_NOT_GRANTED",
            "allowed_to_submit_order": False,
            "side_cell_key": "ma_crossover|ETHUSDT|Sell",
            "event": _selected_reject_event(),
        },
        # F1:30 個 distinct entry(n_eff=30 ≥ 預註冊 §3 E1 門檻;每日 5 個、1h
        # 間距非重疊,跨 6 UTC 日過 E2/E3),avg 維持 11.5(tight-positive 循環值,BH 過)。
        *[
            {
                "record_type": "blocked_signal_outcome",
                "cost_model_version": "conservative_v1",
                "generated_at_utc": f"2026-06-21T13:{index:02d}:00+00:00",
                "attempt_id": f"blocked-{index + 1}",
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "strategy_name": "ma_crossover",
                "symbol": "ETHUSDT",
                "side": "Sell",
                "source_admission_decision": "ORDER_AUTHORITY_NOT_GRANTED",
                "entry_ts_ms": (
                    1_781_956_800_000
                    - (index // 5) * 86_400_000
                    + (index % 5) * 3_600_000
                ),
                "gross_bps": net + 4.0,
                "cost_bps": 4.0,
                "realized_net_bps": net,
                "horizon_minutes": 60,
            }
            for index, net in enumerate([12.5, 11.5, 10.5, 12.0, 11.0] * 6)
        ],
    ]
    (lane_dir / "probe_ledger.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in ledger_rows),
        encoding="utf-8",
    )
    review = build_blocked_signal_outcome_review(
        ledger_rows,
        now_utc=dt.datetime(2026, 6, 21, 14, 20, tzinfo=dt.timezone.utc),
    )
    packet = build_false_negative_candidate_packet(
        review,
        now_utc=dt.datetime(2026, 6, 21, 14, 21, tzinfo=dt.timezone.utc),
        source_path=lane_dir / "blocked_outcome_review_latest.json",
    )
    (lane_dir / "blocked_outcome_review_latest.json").write_text(
        json.dumps(review),
        encoding="utf-8",
    )
    (lane_dir / "false_negative_candidate_packet_latest.json").write_text(
        json.dumps(packet),
        encoding="utf-8",
    )
    false_negative_review = build_false_negative_operator_review(
        false_negative_candidate_packet=packet,
        source_path=lane_dir / "false_negative_candidate_packet_latest.json",
        decision="defer",
        now_utc=dt.datetime(2026, 6, 21, 14, 22, tzinfo=dt.timezone.utc),
    )
    (lane_dir / "false_negative_operator_review_latest.json").write_text(
        json.dumps(false_negative_review),
        encoding="utf-8",
    )

    arm = collect_cost_gate_learning_lane_arm(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 14, 30, tzinfo=dt.timezone.utc),
    )
    discovery = build_discovery_plan(
        [arm],
        now_utc=dt.datetime(2026, 6, 21, 14, 30, tzinfo=dt.timezone.utc),
    )
    row = discovery["profitability_blocker_scorecard"]["arms"][0]

    assert discovery["arms"][0]["action"] == "READY_FOR_PROBE"
    assert discovery["arms"][0]["reason"] == "cost_gate_false_negative_candidate_packet_ready"
    assert discovery["profitability_blocker_scorecard"]["status"] == (
        "ACTIONABLE_PROBE_READY"
    )
    assert row["blocker_class"] == "probe_ready"
    assert row["primary_blocker"] == (
        "cost_gate_false_negative_candidates_need_operator_review"
    )
    assert row["next_trigger"] == (
        "operator_review_ranked_false_negative_candidates_before_bounded_demo_probe_authority"
    )
    assert row["blocked_signal_outcome_review_status"] == (
        "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT"
    )
    assert row["blocked_signal_outcome_review"]["review_candidate_side_cell_count"] == 1
    assert row["blocked_signal_outcome_review"]["top_side_cells"][0]["status"] == (
        "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE"
    )
    assert row["blocked_signal_outcome_review_schema_version"] == (
        "cost_gate_demo_learning_lane_blocked_outcome_review_v5"
    )
    assert row["blocked_signal_top_review_side_cell_key"] == (
        "ma_crossover|ETHUSDT|Sell"
    )
    assert row["blocked_signal_top_review_candidate_side_cell_key"] == (
        "ma_crossover|ETHUSDT|Sell"
    )
    # P2-8/F1:tight-positive [12.5,11.5,10.5,12.0,11.0](BH 過、n_eff=5),avg=11.5。
    assert round(row["blocked_signal_top_review_wrongful_block_score"], 6) == 11.5
    assert round(row["blocked_signal_top_review_net_cost_cushion_bps"], 6) == 11.5


def test_alpha_discovery_blocks_when_blocked_outcome_review_fails_thresholds(
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
    # F1:補 distinct entry_ts(n_eff=3 ≥ min_outcomes,統計面可算;閾值仍不過)。
    ledger_rows = [
        {
            "record_type": "blocked_signal_outcome",
            "cost_model_version": "conservative_v1",
            "generated_at_utc": "2026-06-21T12:15:00+00:00",
            "attempt_id": "blocked-1",
            "side_cell_key": "ma_crossover|ETHUSDT|Sell",
            "strategy_name": "ma_crossover",
            "symbol": "ETHUSDT",
            "side": "Sell",
            "entry_ts_ms": 1_781_956_800_000,
            "realized_net_bps": -3.0,
        },
        {
            "record_type": "blocked_signal_outcome",
            "cost_model_version": "conservative_v1",
            "generated_at_utc": "2026-06-21T13:15:00+00:00",
            "attempt_id": "blocked-2",
            "side_cell_key": "ma_crossover|ETHUSDT|Sell",
            "strategy_name": "ma_crossover",
            "symbol": "ETHUSDT",
            "side": "Sell",
            "entry_ts_ms": 1_781_960_400_000,
            "realized_net_bps": -1.0,
        },
        {
            "record_type": "blocked_signal_outcome",
            "cost_model_version": "conservative_v1",
            "generated_at_utc": "2026-06-21T14:15:00+00:00",
            "attempt_id": "blocked-3",
            "side_cell_key": "ma_crossover|ETHUSDT|Sell",
            "strategy_name": "ma_crossover",
            "symbol": "ETHUSDT",
            "side": "Sell",
            "entry_ts_ms": 1_781_964_000_000,
            "realized_net_bps": 0.5,
        },
    ]
    (lane_dir / "probe_ledger.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in ledger_rows),
        encoding="utf-8",
    )

    arm = collect_cost_gate_learning_lane_arm(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 14, 30, tzinfo=dt.timezone.utc),
    )
    discovery = build_discovery_plan(
        [arm],
        now_utc=dt.datetime(2026, 6, 21, 14, 30, tzinfo=dt.timezone.utc),
    )
    row = discovery["profitability_blocker_scorecard"]["arms"][0]

    assert discovery["arms"][0]["action"] == "BLOCK"
    assert discovery["arms"][0]["reason"] == (
        "cost_gate_blocked_outcomes_confirm_current_block"
    )
    assert discovery["profitability_blocker_scorecard"]["status"] == (
        "NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED"
    )
    assert row["blocker_class"] == "rejected_no_edge"
    assert row["primary_blocker"] == (
        "cost_gate_blocked_signal_outcomes_confirm_current_block"
    )
    assert row["next_trigger"] == "keep_cost_gate_blocked_for_reviewed_side_cells"
    assert row["operator_actionable"] is False
    assert row["engineering_actionable"] is False
    assert row["blocked_signal_outcome_review_status"] == (
        "NO_DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE"
    )


def test_alpha_discovery_routes_cost_wall_blocked_outcomes_to_edge_amplification(
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
    ledger_rows = [
        {
            "record_type": "blocked_signal_outcome",
            "cost_model_version": "conservative_v1",
            "generated_at_utc": "2026-06-21T12:15:00+00:00",
            "attempt_id": "blocked-1",
            "side_cell_key": "ma_crossover|ETHUSDT|Sell",
            "strategy_name": "ma_crossover",
            "symbol": "ETHUSDT",
            "side": "Sell",
            "entry_ts_ms": 1_781_956_800_000,
            "gross_bps": 3.5,
            "cost_bps": 4.0,
            "realized_net_bps": -0.5,
        },
        {
            "record_type": "blocked_signal_outcome",
            "cost_model_version": "conservative_v1",
            "generated_at_utc": "2026-06-21T13:15:00+00:00",
            "attempt_id": "blocked-2",
            "side_cell_key": "ma_crossover|ETHUSDT|Sell",
            "strategy_name": "ma_crossover",
            "symbol": "ETHUSDT",
            "side": "Sell",
            "entry_ts_ms": 1_781_960_400_000,
            "gross_bps": 2.5,
            "cost_bps": 4.0,
            "realized_net_bps": -1.5,
        },
        {
            "record_type": "blocked_signal_outcome",
            "cost_model_version": "conservative_v1",
            "generated_at_utc": "2026-06-21T14:15:00+00:00",
            "attempt_id": "blocked-3",
            "side_cell_key": "ma_crossover|ETHUSDT|Sell",
            "strategy_name": "ma_crossover",
            "symbol": "ETHUSDT",
            "side": "Sell",
            "entry_ts_ms": 1_781_964_000_000,
            "gross_bps": 5.0,
            "cost_bps": 4.0,
            "realized_net_bps": 1.0,
        },
    ]
    (lane_dir / "probe_ledger.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in ledger_rows),
        encoding="utf-8",
    )

    arm = collect_cost_gate_learning_lane_arm(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 14, 30, tzinfo=dt.timezone.utc),
    )
    discovery = build_discovery_plan(
        [arm],
        now_utc=dt.datetime(2026, 6, 21, 14, 30, tzinfo=dt.timezone.utc),
    )
    row = discovery["profitability_blocker_scorecard"]["arms"][0]

    assert discovery["arms"][0]["action"] == "RUN_READ_ONLY_CAPTURE"
    assert discovery["arms"][0]["reason"] == (
        "cost_gate_blocked_outcomes_need_edge_amplification"
    )
    assert row["blocker_class"] == "cost_wall"
    assert row["primary_blocker"] == (
        "cost_gate_blocked_signal_edge_amplification_required"
    )
    assert row["next_trigger"] == "amplify_edge_or_reduce_friction_for_same_side_cell"
    assert row["engineering_actionable"] is True
    assert row["operator_actionable"] is False
    assert row["blocked_signal_top_review_learning_diagnosis"] == (
        "GROSS_EDGE_POSITIVE_COST_CUSHION_INSUFFICIENT"
    )
    assert row["blocked_signal_review_edge_amplification_required_side_cell_count"] == 1


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

    assert discovery["arms"][0]["action"] == "RUN_READ_ONLY_CAPTURE"
    assert discovery["arms"][0]["reason"] == "cost_gate_admission_rows_without_refresh_loop"
    assert discovery["profitability_blocker_scorecard"]["status"] == (
        "NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED"
    )
    assert row["blocker_class"] == "data_coverage"
    assert row["primary_blocker"] == (
        "cost_gate_rejects_recorded_but_outcome_refresh_loop_not_running"
    )
    assert row["next_trigger"] == (
        "install_learning_lane_cron_or_run_outcome_refresh"
    )
    assert row["ledger_status"] == "ADMISSION_ROWS_PRESENT"
    assert row["admission_decision_count"] == 1
    assert row["blocked_signal_outcome_count"] == 0


def test_learning_lane_status_proof_excludes_unattributed_probe_outcomes(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "probe_ledger.jsonl"
    ledger.write_text(
        json.dumps(
            {
                "record_type": "probe_outcome",
                "generated_at_utc": "2026-06-21T12:00:00+00:00",
                "attempt_id": "attempt-unattributed-1",
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "strategy_name": "unattributed:bybit_auto",
                "outcome_source": "demo_fill_execution",
                "order_id": "bybit-unmatched-1",
                "exec_id": "exec-unmatched-1",
                "realized_net_bps": 25.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    summary = summarize_cost_gate_learning_lane_ledger(ledger)

    assert summary["ledger_status"] == "PROBE_OUTCOMES_PROOF_EXCLUDED"
    assert summary["raw_probe_outcome_count"] == 1
    assert summary["probe_outcome_count"] == 0
    assert summary["proof_eligible_probe_outcome_count"] == 0
    assert summary["proof_excluded_probe_outcome_count"] == 1
    assert summary["proof_exclusion_present"] is True
    assert summary["proof_exclusion_reason_counts"]["unattributed_strategy_name"] == 1
    assert summary["avg_probe_outcome_net_bps"] is None


def test_learning_ssot_decision_uses_artifact_ledger_as_current_ssot() -> None:
    packet = build_learning_ssot_decision(
        activation_preflight=_activation_preflight_for_ssot(),
        now_utc=dt.datetime(2026, 6, 24, 4, 45, tzinfo=dt.timezone.utc),
    )
    markdown = render_learning_ssot_decision_markdown(packet)

    assert packet["schema_version"] == "cost_gate_learning_ssot_decision_v1"
    assert packet["status"] == "ARTIFACT_LEDGER_CURRENT_SSOT"
    assert packet["current_learning_ssot"] == "artifact_probe_ledger_jsonl"
    assert packet["ssot_decision"]["artifact_probe_ledger_is_current_ssot"] is True
    assert packet["ssot_decision"]["pg_backed_ledger_is_current_ssot"] is False
    assert packet["migration_gates"]["authority_boundary_preserved"] is True
    assert packet["migration_gates"]["artifact_ledger_status"] == (
        "BLOCKED_SIGNAL_OUTCOMES_PRESENT"
    )
    assert packet["migration_gates"]["artifact_ledger_path"] == (
        "/tmp/openclaw/cost_gate_learning_lane/probe_ledger.jsonl"
    )
    assert packet["migration_gates"]["pg_backed_cutover_ready"] is False
    assert packet["migration_gates"]["pg_backed_schema_verified"] is False
    assert packet["migration_gates"]["pg_backed_writer_idempotency_verified"] is False
    assert packet["migration_gates"]["pg_backed_reconstruction_verified"] is False
    assert packet["migration_gates"]["pg_probe_performed"] is False
    assert packet["answers"]["global_cost_gate_lowering_recommended"] is False
    assert packet["answers"]["main_cost_gate_adjustment"] == "NONE"
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["active_runtime_probe_authority"] is False
    assert packet["answers"]["active_runtime_order_authority"] is False
    assert packet["answers"]["operator_authorization_object_emitted"] is False
    assert packet["answers"]["promotion_evidence"] is False
    assert packet["answers"]["pg_write_required"] is False
    assert packet["answers"]["pg_write_performed"] is False
    assert packet["answers"]["bybit_call_required"] is False
    assert packet["answers"]["order_submission_performed"] is False
    assert "Current SSOT" in markdown
    assert "no PG query/write" in markdown


def test_learning_ssot_decision_does_not_treat_writer_flag_as_pg_ready() -> None:
    packet = build_learning_ssot_decision(
        activation_preflight=_activation_preflight_for_ssot(
            writer_enabled=True,
            process_writer_enabled=True,
        ),
        now_utc=dt.datetime(2026, 6, 24, 4, 45, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "PG_BACKED_LEDGER_MIGRATION_REVIEW_REQUIRED"
    assert packet["current_learning_ssot"] == "artifact_probe_ledger_jsonl"
    assert packet["ssot_decision"]["pg_backed_ledger_is_current_ssot"] is False
    assert packet["migration_gates"]["pg_backed_cutover_ready"] is False
    assert packet["migration_gates"]["pg_backed_learning_ledger_observed"] is False
    assert packet["migration_gates"]["pg_probe_performed"] is False
    assert packet["migration_gates"]["runtime_writer_config_enabled"] is True
    assert packet["migration_gates"]["runtime_writer_process_enabled"] is True
    assert "operator_review_pg_backed_cost_gate_learning_ledger_contract_before_ssot_cutover" in (
        packet["next_actions"]
    )


def test_learning_ssot_decision_fails_closed_without_activation_preflight() -> None:
    packet = build_learning_ssot_decision(
        activation_preflight=None,
        now_utc=dt.datetime(2026, 6, 24, 4, 45, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "SSOT_INPUT_MISSING"
    assert packet["current_learning_ssot"] == "NONE"
    assert packet["ssot_decision"]["artifact_probe_ledger_is_current_ssot"] is False
    assert packet["ssot_decision"]["pg_backed_ledger_is_current_ssot"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["next_actions"] == [
        "refresh_cost_gate_learning_lane_activation_preflight"
    ]


def test_learning_ssot_decision_fails_closed_on_authority_bearing_input() -> None:
    activation = _activation_preflight_for_ssot()
    activation["answers"]["probe_authority_granted"] = True

    packet = build_learning_ssot_decision(
        activation_preflight=activation,
        now_utc=dt.datetime(2026, 6, 24, 4, 45, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["reason"] == "input_artifact_claimed_authority_or_cost_gate_mutation"
    assert packet["current_learning_ssot"] == "NONE"
    assert packet["ssot_decision"]["artifact_probe_ledger_is_current_ssot"] is False
    assert packet["migration_gates"]["authority_boundary_preserved"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["promotion_evidence"] is False
    assert packet["next_actions"][0] == (
        "discard_authority_bearing_input_and_rerun_source_only_ssot_decision"
    )


def test_learning_ssot_decision_surfaces_proof_exclusion_before_cutover() -> None:
    packet = build_learning_ssot_decision(
        activation_preflight=_activation_preflight_for_ssot(),
        bounded_result_review={
            "schema_version": "bounded_demo_probe_result_review_v1",
            "generated_at_utc": "2026-06-24T04:40:00+00:00",
            "status": "STOP_BOUNDED_DEMO_PROBE_REALIZED_EDGE_FAILED",
            "probe_result_summary": {
                "completed_probe_outcome_count": 2,
                "proof_eligible_probe_outcome_count": 1,
                "proof_excluded_probe_outcome_count": 1,
            },
            "answers": {
                "proof_exclusion_present": True,
                "promotion_evidence": False,
            },
        },
        now_utc=dt.datetime(2026, 6, 24, 4, 45, tzinfo=dt.timezone.utc),
    )

    assert packet["result_review"]["proof_exclusion_present"] is True
    assert packet["next_actions"][0] == (
        "repair_or_quarantine_proof_excluded_fill_lineage_before_any_ssot_cutover"
    )
    assert packet["answers"]["promotion_evidence"] is False


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


def _btc_sell_reject_event() -> dict:
    return {
        "strategy_name": "ma_crossover",
        "symbol": "BTCUSDT",
        "side": "Sell",
        "reject_reason_code": "cost_gate_js_demo_negative_edge",
        "engine_mode": "live_demo",
        "ts_ms": 1_782_037_200_000,
        "context_id": "ctx-demo-ma_crossover-BTCUSDT-1782037200000",
        "signal_id": "sig-demo-ma_crossover-BTCUSDT-1782037200000",
    }


def _add_runtime_operator_authorization(
    plan: dict,
    *,
    expires_at: str = "2026-06-21T12:00:00+00:00",
    side_cell_key: str = "ma_crossover|ETHUSDT|Sell",
    max_authorized_probe_orders: int = 2,
) -> dict:
    plan["operator_authorization"] = {
        "schema_version": "bounded_demo_probe_operator_authorization_v1",
        "status": "BOUNDED_DEMO_PROBE_AUTHORIZED",
        "authorization_id": "auth-demo-runtime-001",
        "operator_id": "operator-test",
        "side_cell_key": side_cell_key,
        "expires_at_utc": expires_at,
        "authority_path_readiness_status": (
            "AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW"
        ),
        "main_cost_gate_adjustment": "NONE",
        "order_authority": ORDER_AUTHORITY_GRANTED,
        "max_authorized_probe_orders": max_authorized_probe_orders,
        "probe_authority_granted": True,
        "order_authority_granted": True,
        "promotion_evidence": False,
    }
    return plan


def _runtime_plan(
    *,
    order_authority: str = "NOT_GRANTED",
    include_operator_authorization: bool | None = None,
    authorization_expires_at: str = "2026-06-21T12:00:00+00:00",
) -> dict:
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
        cfg=LearningLanePolicyConfig(max_probe_side_cells=2, max_total_probe_orders=4),
    )
    plan["order_authority"] = order_authority
    should_include = (
        order_authority == ORDER_AUTHORITY_GRANTED
        if include_operator_authorization is None
        else include_operator_authorization
    )
    if should_include:
        _add_runtime_operator_authorization(plan, expires_at=authorization_expires_at)
    return plan


def _sealed_runtime_plan(*, order_authority: str = "NOT_GRANTED") -> dict:
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 22, 4, tzinfo=dt.timezone.utc),
        cfg=LearningLanePolicyConfig(max_probe_side_cells=1, max_total_probe_orders=3),
        horizon_sealed_replay=_sealed_horizon_replay_packet(),
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


def test_runtime_adapter_carries_sealed_candidate_summary_into_ledger():
    decision = evaluate_probe_admission(
        _sealed_runtime_plan(),
        _btc_sell_reject_event(),
        now_utc=dt.datetime(2026, 6, 22, 4, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )

    assert decision["decision"] == "ORDER_AUTHORITY_NOT_GRANTED"
    assert decision["allowed_to_submit_order"] is False
    assert decision["candidate_summary"]["source_kind"] == (
        "horizon_specific_sealed_replay"
    )
    assert decision["candidate_summary"]["outcome_horizon_minutes"] == 240
    assert decision["candidate_summary"]["sealed_horizon_replay"]["best_avg_net_bps"] == (
        31.8707
    )

    record = build_ledger_record(decision)
    assert record["decision"] == "ORDER_AUTHORITY_NOT_GRANTED"
    assert record["candidate_summary"]["outcome_horizon_minutes"] == 240
    assert record["candidate_summary"]["sealed_horizon_replay"]["sample_count_for_gate"] == (
        13819
    )


def test_runtime_adapter_admits_only_when_plan_and_adapter_explicitly_authorize():
    missing_authorization = evaluate_probe_admission(
        _runtime_plan(
            order_authority=ORDER_AUTHORITY_GRANTED,
            include_operator_authorization=False,
        ),
        _selected_reject_event(),
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )
    assert missing_authorization["decision"] == "OPERATOR_AUTHORIZATION_INVALID"
    assert (
        missing_authorization["reason"]
        == "operator_authorization_missing_for_order_authority"
    )

    expired_authorization = evaluate_probe_admission(
        _runtime_plan(
            order_authority=ORDER_AUTHORITY_GRANTED,
            authorization_expires_at="2026-06-21T10:59:00+00:00",
        ),
        _selected_reject_event(),
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )
    assert expired_authorization["decision"] == "OPERATOR_AUTHORIZATION_INVALID"
    assert expired_authorization["reason"] == "operator_authorization_expired"

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
    # P1-2a:realized_net_bps 語義升級為保守成本;舊 4.0 常數的淨值移到 net_bps_optimistic。
    assert round(outcome["net_bps_optimistic"], 6) == 96.0


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
    # P1-2a:舊 4.0 常數的淨值移到 net_bps_optimistic;realized_net_bps 為保守權威淨值。
    assert round(outcome["net_bps_optimistic"], 6) == -54.0


def test_blocked_signal_outcome_uses_candidate_specific_horizon_from_ledger():
    not_granted = evaluate_probe_admission(
        _sealed_runtime_plan(),
        _btc_sell_reject_event(),
        now_utc=dt.datetime(2026, 6, 22, 4, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )
    ledger = [build_ledger_record(not_granted)]

    outcomes = build_blocked_signal_outcome_records(
        ledger,
        [
            {"symbol": "BTCUSDT", "ts_ms": 1_782_037_200_000, "close": 100_000.0},
            {"symbol": "BTCUSDT", "ts_ms": 1_782_051_600_000, "close": 99_000.0},
        ],
        now_utc=dt.datetime(2026, 6, 22, 8, 11, tzinfo=dt.timezone.utc),
        cfg=ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0),
    )

    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome["record_type"] == "blocked_signal_outcome"
    assert outcome["horizon_minutes"] == 240
    assert outcome["default_horizon_minutes"] == 60
    assert outcome["candidate_summary"]["outcome_horizon_minutes"] == 240
    assert round(outcome["gross_bps"], 6) == 100.0
    # P1-2a:舊 4.0 常數的淨值移到 net_bps_optimistic。
    assert round(outcome["net_bps_optimistic"], 6) == 96.0


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
        "cost_model_version": "conservative_v1",
        "attempt_id": _selected_reject_event()["context_id"],
    }
    assert required_price_observation_windows(ledger + [completed]) == []


def test_price_observation_windows_use_candidate_specific_horizon_from_ledger():
    not_granted = evaluate_probe_admission(
        _sealed_runtime_plan(),
        _btc_sell_reject_event(),
        now_utc=dt.datetime(2026, 6, 22, 4, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )
    ledger = [build_ledger_record(not_granted)]

    windows = required_price_observation_windows(
        ledger,
        cfg=PriceObservationBuildConfig(horizon_minutes=60, max_entry_delay_ms=300_000),
    )

    assert len(windows) == 1
    window = windows[0]
    assert window["side_cell_key"] == "ma_crossover|BTCUSDT|Sell"
    assert window["horizon_minutes"] == 240
    assert window["default_horizon_minutes"] == 60
    assert window["exit_target_ts_ms"] == 1_782_051_600_000
    assert window["end_ts_ms"] == 1_782_051_600_000 + 300_000
    assert window["candidate_summary"]["outcome_horizon_minutes"] == 240


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


def test_outcome_refresh_dry_run_append_and_idempotent_blocked_signal_rows(
    tmp_path: Path,
):
    ledger_path = tmp_path / "probe_ledger.jsonl"
    not_granted = evaluate_probe_admission(
        _runtime_plan(),
        _selected_reject_event(),
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )
    append_jsonl_ledger(ledger_path, build_ledger_record(not_granted))
    price_rows = [
        {"symbol": "ETHUSDT", "ts_ms": 1_782_037_200_000, "close": 2000.0},
        {"symbol": "ETHUSDT", "ts_ms": 1_782_040_800_000, "close": 2010.0},
    ]
    selection = OutcomeRefreshSelection(record_blocked_outcomes=True)
    outcome_cfg = ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0)
    now = dt.datetime(2026, 6, 21, 12, 11, tzinfo=dt.timezone.utc)

    dry_run = refresh_cost_gate_outcomes_from_price_rows(
        ledger_path,
        price_rows,
        now_utc=now,
        selection=selection,
        outcome_cfg=outcome_cfg,
        append_ledger=False,
    )

    assert dry_run["record_type"] == "cost_gate_outcome_refresh_batch"
    assert dry_run["append_requested"] is False
    assert dry_run["appended_to_ledger"] is False
    assert dry_run["blocked_signal_outcome_count"] == 1
    assert dry_run["outcome_count"] == 1
    assert len(read_jsonl_ledger(ledger_path)) == 1

    appended = refresh_cost_gate_outcomes_from_price_rows(
        ledger_path,
        price_rows,
        now_utc=now,
        selection=selection,
        outcome_cfg=outcome_cfg,
        append_ledger=True,
    )
    rows = read_jsonl_ledger(ledger_path)

    assert appended["append_requested"] is True
    assert appended["appended_to_ledger"] is True
    assert appended["appended_outcome_count"] == 1
    assert len(rows) == 2
    assert rows[1]["record_type"] == "blocked_signal_outcome"
    assert rows[1]["promotion_evidence"] is False
    # P1-2a:舊 4.0 常數的淨值移到 net_bps_optimistic。
    assert round(rows[1]["net_bps_optimistic"], 6) == -54.0

    rerun = refresh_cost_gate_outcomes_from_price_rows(
        ledger_path,
        price_rows,
        now_utc=now,
        selection=selection,
        outcome_cfg=outcome_cfg,
        append_ledger=True,
    )
    assert rerun["window_count"] == 0
    assert rerun["outcome_count"] == 0
    assert rerun["appended_outcome_count"] == 0
    assert len(read_jsonl_ledger(ledger_path)) == 2


def test_outcome_refresh_pg_price_rows_feed_batch_without_duplicate_queries():
    not_granted = evaluate_probe_admission(
        _runtime_plan(),
        _selected_reject_event(),
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )
    ledger = [build_ledger_record(not_granted)]
    selection = OutcomeRefreshSelection(record_blocked_outcomes=True)
    outcome_cfg = ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0)
    conn = _FakeKlineConn(
        {
            "ETHUSDT": [
                ("ETHUSDT", 1_782_037_200_000, 2000.0),
                ("ETHUSDT", 1_782_040_800_000, 2010.0),
            ],
        }
    )

    price_rows = build_price_rows_from_pg_for_refresh(
        ledger,
        selection=selection,
        outcome_cfg=outcome_cfg,
        timeframe="1m",
        conn=conn,
    )
    batch = build_cost_gate_outcome_refresh_batch(
        ledger,
        price_rows,
        now_utc=dt.datetime(2026, 6, 21, 12, 11, tzinfo=dt.timezone.utc),
        selection=selection,
        outcome_cfg=outcome_cfg,
        price_source="pg_market_klines",
    )

    assert [params[0] for _sql, params in conn.executions] == ["ETHUSDT"]
    assert batch["price_source"] == "pg_market_klines"
    assert batch["price_observation_count"] == 2
    assert batch["blocked_signal_outcome_count"] == 1
    assert batch["observations"][0]["source"] == "pg_market_klines"
    assert batch["observations"][0]["timeframe"] == "1m"

    completed = ledger + [
        {
            "record_type": "blocked_signal_outcome",
            "cost_model_version": "conservative_v1",
            "attempt_id": _selected_reject_event()["context_id"],
        }
    ]
    no_window_conn = _FakeKlineConn({"ETHUSDT": []})
    assert build_price_rows_from_pg_for_refresh(
        completed,
        selection=selection,
        outcome_cfg=outcome_cfg,
        timeframe="1m",
        conn=no_window_conn,
    ) == []
    assert no_window_conn.executions == []


def test_blocked_signal_outcome_review_scorecard_is_conservative():
    scorecard = build_blocked_signal_outcome_review(
        [
            {
                "record_type": "blocked_signal_outcome",
                "cost_model_version": "conservative_v1",
                "generated_at_utc": "2026-06-21T12:15:00+00:00",
                "attempt_id": "blocked-1",
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "strategy_name": "ma_crossover",
                "symbol": "ETHUSDT",
                "side": "Sell",
                "entry_ts_ms": 1_781_956_800_000,
                "gross_bps": 16.5,
                "cost_bps": 4.0,
                "realized_net_bps": 12.5,
                "horizon_minutes": 60,
            },
            {
                "record_type": "blocked_signal_outcome",
                "cost_model_version": "conservative_v1",
                "generated_at_utc": "2026-06-21T13:15:00+00:00",
                "attempt_id": "blocked-2",
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "strategy_name": "ma_crossover",
                "symbol": "ETHUSDT",
                "side": "Sell",
                "entry_ts_ms": 1_781_960_400_000,
                "gross_bps": 8.0,
                "cost_bps": 4.0,
                "realized_net_bps": 4.0,
                "horizon_minutes": 60,
            },
            {
                "record_type": "blocked_signal_outcome",
                "cost_model_version": "conservative_v1",
                "generated_at_utc": "2026-06-21T14:15:00+00:00",
                "attempt_id": "blocked-3",
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "strategy_name": "ma_crossover",
                "symbol": "ETHUSDT",
                "side": "Sell",
                "entry_ts_ms": 1_781_964_000_000,
                "gross_bps": 3.0,
                "cost_bps": 4.0,
                "realized_net_bps": -1.0,
                "horizon_minutes": 60,
            },
        ],
        now_utc=dt.datetime(2026, 6, 21, 14, 30, tzinfo=dt.timezone.utc),
        cfg=BlockedOutcomeReviewConfig(
            min_outcomes_per_side_cell=3,
            # F1:n_eff=3 fixture,n_eff 門檻對齊到 3;E2/E3 天數欄放到不攔
            # (1 日/100%)—— 本測驗的是 BH 撤下路徑,不是 eligibility 攔截
            # (eligibility 本體由 evidence methodology F1 測試組以默認值直測)。
            min_effective_entries_per_side_cell=3,
            min_distinct_entry_utc_days=1,
            max_top_entry_day_share_pct=100.0,
            min_avg_net_bps=0.0,
            min_net_positive_pct=60.0,
        ),
    )

    # P2-8(b):n=3 高變異數 cell 通過保守閾值但不過 BH-FDR(q=0.10)→ 撤下候選,
    # 改標 EXPLORATION_CANDIDATE_BH_FDR_NOT_PASSED(這是方法學重設計的預期結果:
    # 立案需 BH pass,marginal 小樣本只可作 exploration 排序)。
    assert scorecard["status"] == "NO_DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE"
    assert scorecard["schema_version"] == (
        "cost_gate_demo_learning_lane_blocked_outcome_review_v5"
    )
    assert scorecard["review_candidate_side_cell_count"] == 0
    assert scorecard["promotion_evidence"] is False
    assert scorecard["order_authority"] == "NOT_GRANTED"
    side_cell = scorecard["top_side_cells"][0]
    assert side_cell["status"] == "EXPLORATION_CANDIDATE_BH_FDR_NOT_PASSED"
    assert side_cell["bh_fdr_pass"] is False
    assert side_cell["review_candidate"] is False
    assert side_cell["outcome_count"] == 3
    assert round(side_cell["avg_net_bps"], 6) == 5.166667
    assert round(side_cell["avg_gross_bps"], 6) == 9.166667
    assert side_cell["avg_cost_bps"] == 4.0
    assert round(side_cell["net_positive_pct"], 6) == 66.666667
    assert side_cell["gross_positive_pct"] == 100.0
    assert round(side_cell["net_cost_cushion_bps"], 6) == 5.166667
    assert round(side_cell["net_positive_margin_pct"], 6) == 6.666667
    assert side_cell["sample_margin_count"] == 0
    # wrongful_block_score 為排序分數(不受 BH 影響),margins 不變仍 3.44。
    assert round(side_cell["wrongful_block_score"], 6) == 3.444444
    assert side_cell["review_rank"] == 1
    # BH 撤下候選後不再有 bounded probe rank。
    assert side_cell["bounded_demo_probe_review_rank"] is None
    assert side_cell["horizon_minutes"] == [60]
    assert side_cell["horizon_counts"] == {"60": 3}
    assert side_cell["dominant_horizon_minutes"] == 60
    assert scorecard["top_side_cell_key"] == "ma_crossover|ETHUSDT|Sell"
    # 非候選 → 診斷落 BLOCK_CONFIRMED_AFTER_COST(review_candidate=False 路徑)。
    assert side_cell["learning_diagnosis"] == "BLOCK_CONFIRMED_AFTER_COST"
    assert scorecard["top_review_candidate_side_cell_key"] is None
    assert scorecard["false_negative_candidate_count"] == 0
    assert round(scorecard["max_wrongful_block_score"], 6) == 3.444444

    insufficient = build_blocked_signal_outcome_review(
        [
            {
                "record_type": "blocked_signal_outcome",
                "cost_model_version": "conservative_v1",
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "realized_net_bps": 12.5,
            }
        ],
        cfg=BlockedOutcomeReviewConfig(min_outcomes_per_side_cell=3),
    )
    assert insufficient["status"] == "COLLECT_MORE_BLOCKED_SIGNAL_OUTCOMES"
    assert insufficient["review_candidate_side_cell_count"] == 0
    assert insufficient["top_side_cells"][0]["learning_diagnosis"] == (
        "SAMPLE_INSUFFICIENT"
    )
    assert insufficient["top_side_cells"][0]["cost_gate_escape_recommendation"] == (
        "continue_recording_same_side_cell_blocked_signal_outcomes"
    )


def test_blocked_signal_outcome_review_separates_cost_wall_from_no_edge():
    scorecard = build_blocked_signal_outcome_review(
        [
            {
                "record_type": "blocked_signal_outcome",
                "cost_model_version": "conservative_v1",
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "strategy_name": "ma_crossover",
                "symbol": "ETHUSDT",
                "side": "Sell",
                "entry_ts_ms": 1_781_956_800_000,
                "gross_bps": 3.5,
                "cost_bps": 4.0,
                "realized_net_bps": -0.5,
            },
            {
                "record_type": "blocked_signal_outcome",
                "cost_model_version": "conservative_v1",
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "strategy_name": "ma_crossover",
                "symbol": "ETHUSDT",
                "side": "Sell",
                "entry_ts_ms": 1_781_960_400_000,
                "gross_bps": 2.5,
                "cost_bps": 4.0,
                "realized_net_bps": -1.5,
            },
            {
                "record_type": "blocked_signal_outcome",
                "cost_model_version": "conservative_v1",
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "strategy_name": "ma_crossover",
                "symbol": "ETHUSDT",
                "side": "Sell",
                "entry_ts_ms": 1_781_964_000_000,
                "gross_bps": 5.0,
                "cost_bps": 4.0,
                "realized_net_bps": 1.0,
            },
        ],
        cfg=BlockedOutcomeReviewConfig(min_outcomes_per_side_cell=3),
    )

    side_cell = scorecard["top_side_cells"][0]
    assert scorecard["status"] == "NO_DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE"
    assert side_cell["status"] == "KEEP_COST_GATE_BLOCKED"
    assert side_cell["learning_diagnosis"] == (
        "GROSS_EDGE_POSITIVE_COST_CUSHION_INSUFFICIENT"
    )
    assert side_cell["cost_gate_escape_recommendation"] == (
        "amplify_edge_or_reduce_friction_for_same_side_cell"
    )
    assert side_cell["edge_amplification_required"] is True
    assert side_cell["false_negative_candidate"] is False
    assert scorecard["edge_amplification_required_side_cell_count"] == 1
    assert scorecard["false_negative_candidate_count"] == 0


def test_false_negative_candidate_packet_ranks_cost_gate_escape_paths():
    scorecard = build_blocked_signal_outcome_review(
        [
            {
                "record_type": "blocked_signal_outcome",
                "cost_model_version": "conservative_v1",
                "generated_at_utc": "2026-06-21T12:15:00+00:00",
                "attempt_id": "fn-1",
                "side_cell_key": "grid_trading|AVAXUSDT|Sell",
                "strategy_name": "grid_trading",
                "symbol": "AVAXUSDT",
                "side": "Sell",
                "entry_ts_ms": 1_781_956_800_000,
                "gross_bps": 12.0,
                "cost_bps": 4.0,
                "realized_net_bps": 8.0,
                "horizon_minutes": 60,
            },
            {
                "record_type": "blocked_signal_outcome",
                "cost_model_version": "conservative_v1",
                "generated_at_utc": "2026-06-21T13:15:00+00:00",
                "attempt_id": "fn-2",
                "side_cell_key": "grid_trading|AVAXUSDT|Sell",
                "strategy_name": "grid_trading",
                "symbol": "AVAXUSDT",
                "side": "Sell",
                "entry_ts_ms": 1_781_960_400_000,
                "gross_bps": 11.0,
                "cost_bps": 4.0,
                "realized_net_bps": 7.0,
                "horizon_minutes": 60,
            },
            {
                "record_type": "blocked_signal_outcome",
                "cost_model_version": "conservative_v1",
                "generated_at_utc": "2026-06-21T14:15:00+00:00",
                "attempt_id": "fn-3",
                "side_cell_key": "grid_trading|AVAXUSDT|Sell",
                "strategy_name": "grid_trading",
                "symbol": "AVAXUSDT",
                "side": "Sell",
                "entry_ts_ms": 1_781_964_000_000,
                "gross_bps": 10.0,
                "cost_bps": 4.0,
                "realized_net_bps": 6.0,
                "horizon_minutes": 60,
            },
            {
                "record_type": "blocked_signal_outcome",
                "cost_model_version": "conservative_v1",
                "generated_at_utc": "2026-06-21T12:15:00+00:00",
                "attempt_id": "edge-1",
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "strategy_name": "ma_crossover",
                "symbol": "ETHUSDT",
                "side": "Sell",
                "entry_ts_ms": 1_781_967_600_000,
                "gross_bps": 3.5,
                "cost_bps": 4.0,
                "realized_net_bps": -0.5,
                "horizon_minutes": 60,
            },
            {
                "record_type": "blocked_signal_outcome",
                "cost_model_version": "conservative_v1",
                "generated_at_utc": "2026-06-21T13:15:00+00:00",
                "attempt_id": "edge-2",
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "strategy_name": "ma_crossover",
                "symbol": "ETHUSDT",
                "side": "Sell",
                "entry_ts_ms": 1_781_971_200_000,
                "gross_bps": 2.5,
                "cost_bps": 4.0,
                "realized_net_bps": -1.5,
                "horizon_minutes": 60,
            },
            {
                "record_type": "blocked_signal_outcome",
                "cost_model_version": "conservative_v1",
                "generated_at_utc": "2026-06-21T14:15:00+00:00",
                "attempt_id": "edge-3",
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "strategy_name": "ma_crossover",
                "symbol": "ETHUSDT",
                "side": "Sell",
                "entry_ts_ms": 1_781_974_800_000,
                "gross_bps": 5.0,
                "cost_bps": 4.0,
                "realized_net_bps": 1.0,
                "horizon_minutes": 60,
            },
        ],
        cfg=BlockedOutcomeReviewConfig(
            min_outcomes_per_side_cell=3,
            # F1:n_eff=3 同日 fixture,n_eff/天數欄對齊到不攔(候選/成本牆分流
            # 語義本測;E2/E3 eligibility 本體由 evidence methodology 測試組直測)。
            min_effective_entries_per_side_cell=3,
            min_distinct_entry_utc_days=1,
            max_top_entry_day_share_pct=100.0,
        ),
        now_utc=dt.datetime(2026, 6, 21, 15, 0, tzinfo=dt.timezone.utc),
    )

    packet = build_false_negative_candidate_packet(
        scorecard,
        now_utc=dt.datetime(2026, 6, 21, 15, 5, tzinfo=dt.timezone.utc),
    )

    assert packet["schema_version"] == "cost_gate_false_negative_candidate_packet_v1"
    assert packet["status"] == (
        "COST_GATE_FALSE_NEGATIVE_CANDIDATES_READY_FOR_OPERATOR_REVIEW"
    )
    assert packet["summary"]["false_negative_candidate_count"] == 1
    assert packet["summary"]["edge_amplification_candidate_count"] == 1
    assert packet["answers"]["operator_review_ready"] is True
    assert packet["answers"]["engineering_actionable"] is True
    assert packet["answers"]["global_cost_gate_lowering_recommended"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["promotion_evidence"] is False
    top_false_negative = packet["ranked_false_negative_candidates"][0]
    assert top_false_negative["side_cell_key"] == "grid_trading|AVAXUSDT|Sell"
    assert top_false_negative["candidate_class"] == "false_negative_after_cost"
    assert top_false_negative["operator_review_required"] is True
    assert top_false_negative["false_negative_rank"] == 1
    assert top_false_negative["required_net_uplift_bps"] == 0.0
    assert top_false_negative["next_action"] == (
        "operator_review_bounded_probe_authority_without_global_gate_lowering"
    )
    top_edge = packet["edge_amplification_candidates"][0]
    assert top_edge["side_cell_key"] == "ma_crossover|ETHUSDT|Sell"
    assert top_edge["candidate_class"] == "edge_amplification_required"
    assert top_edge["engineering_actionable"] is True
    assert top_edge["edge_amplification_rank"] == 1
    assert top_edge["required_net_uplift_bps"] == 0.3333
    assert top_edge["next_action"] == (
        "amplify_edge_or_reduce_friction_for_same_side_cell"
    )
    markdown = render_false_negative_candidate_packet_markdown(packet)
    assert "grid_trading|AVAXUSDT|Sell" in markdown
    assert "ma_crossover|ETHUSDT|Sell" in markdown


def _false_negative_candidate_packet_fixture() -> dict:
    scorecard = build_blocked_signal_outcome_review(
        [
            {
                "record_type": "blocked_signal_outcome",
                "cost_model_version": "conservative_v1",
                "generated_at_utc": "2026-06-21T12:15:00+00:00",
                "attempt_id": "fn-1",
                "side_cell_key": "grid_trading|AVAXUSDT|Sell",
                "strategy_name": "grid_trading",
                "symbol": "AVAXUSDT",
                "side": "Sell",
                "entry_ts_ms": 1_781_956_800_000,
                "gross_bps": 12.0,
                "cost_bps": 4.0,
                "realized_net_bps": 8.0,
                "horizon_minutes": 60,
            },
            {
                "record_type": "blocked_signal_outcome",
                "cost_model_version": "conservative_v1",
                "generated_at_utc": "2026-06-21T13:15:00+00:00",
                "attempt_id": "fn-2",
                "side_cell_key": "grid_trading|AVAXUSDT|Sell",
                "strategy_name": "grid_trading",
                "symbol": "AVAXUSDT",
                "side": "Sell",
                "entry_ts_ms": 1_781_960_400_000,
                "gross_bps": 7.0,
                "cost_bps": 4.0,
                "realized_net_bps": 3.0,
                "horizon_minutes": 60,
            },
            {
                "record_type": "blocked_signal_outcome",
                "cost_model_version": "conservative_v1",
                "generated_at_utc": "2026-06-21T14:15:00+00:00",
                "attempt_id": "fn-3",
                "side_cell_key": "grid_trading|AVAXUSDT|Sell",
                "strategy_name": "grid_trading",
                "symbol": "AVAXUSDT",
                "side": "Sell",
                "entry_ts_ms": 1_781_964_000_000,
                "gross_bps": 6.0,
                "cost_bps": 4.0,
                "realized_net_bps": 2.0,
                "horizon_minutes": 60,
            },
        ],
        cfg=BlockedOutcomeReviewConfig(
            min_outcomes_per_side_cell=3,
            # F1:n_eff=3 同日 fixture,n_eff/天數欄對齊到不攔(候選/成本牆分流
            # 語義本測;E2/E3 eligibility 本體由 evidence methodology 測試組直測)。
            min_effective_entries_per_side_cell=3,
            min_distinct_entry_utc_days=1,
            max_top_entry_day_share_pct=100.0,
        ),
        now_utc=dt.datetime(2026, 6, 21, 15, 0, tzinfo=dt.timezone.utc),
    )
    return build_false_negative_candidate_packet(
        scorecard,
        now_utc=dt.datetime(2026, 6, 21, 15, 5, tzinfo=dt.timezone.utc),
    )


def _standing_demo_authorization_fixture(**overrides) -> dict:
    payload = {
        "schema_version": "standing_demo_operator_authorization_v1",
        "generated_at_utc": "2026-06-21T15:06:00+00:00",
        "status": "STANDING_DEMO_AUTHORIZATION_ACTIVE",
        "standing_authorization_id": "standing-demo-fn-review-001",
        "operator_id": "pm",
        "environment": "demo",
        "scope": "demo_api_only_bounded_probe",
        "demo_only": True,
        "candidate_scoping_required": True,
        "candidate": {
            "side_cell_key": "grid_trading|AVAXUSDT|Sell",
            "strategy_name": "grid_trading",
            "symbol": "AVAXUSDT",
            "side": "Sell",
            "outcome_horizon_minutes": 60,
        },
        "max_authorized_probe_orders_per_candidate": 2,
        "expires_at_utc": "2026-06-21T18:00:00+00:00",
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
    payload.update(overrides)
    return payload


def test_false_negative_operator_review_defers_without_authority():
    packet = _false_negative_candidate_packet_fixture()
    review = build_false_negative_operator_review(
        false_negative_candidate_packet=packet,
        now_utc=dt.datetime(2026, 6, 21, 15, 10, tzinfo=dt.timezone.utc),
    )

    assert review["schema_version"] == "cost_gate_false_negative_operator_review_v1"
    assert review["status"] == FALSE_NEGATIVE_PENDING_OPERATOR_REVIEW_STATUS
    assert review["selected_side_cell_key"] == "grid_trading|AVAXUSDT|Sell"
    assert review["selected_false_negative_rank"] == 1
    assert review["operator_review_approved_for_preflight"] is False
    assert review["answers"]["bounded_demo_probe_preflight_approved"] is False
    assert review["answers"]["review_grants_runtime_authority"] is False
    assert review["answers"]["bounded_demo_probe_authorized"] is False
    assert review["answers"]["global_cost_gate_lowering_recommended"] is False
    assert review["answers"]["probe_authority_granted"] is False
    assert review["answers"]["order_authority_granted"] is False
    assert review["answers"]["promotion_evidence"] is False
    assert review["typed_confirm_expected"] == (
        "approve_cost_gate_false_negative_preflight:"
        "grid_trading|AVAXUSDT|Sell:1"
    )
    assert all(gate["passed"] for gate in review["gates"][:4])


def test_false_negative_operator_review_consumes_standing_demo_envelope():
    packet = _false_negative_candidate_packet_fixture()
    review = build_false_negative_operator_review(
        false_negative_candidate_packet=packet,
        standing_demo_authorization=_standing_demo_authorization_fixture(),
        decision="defer",
        now_utc=dt.datetime(2026, 6, 21, 15, 10, tzinfo=dt.timezone.utc),
    )

    assert review["status"] == FALSE_NEGATIVE_APPROVED_FOR_PREFLIGHT_STATUS
    assert review["decision"] == "approve-preflight"
    assert review["operator_id"] == "pm"
    assert review["operator_review_approval_source"] == "standing_demo_authorization"
    assert review["operator_review_approved_for_preflight"] is True
    assert review["answers"]["standing_demo_authorization_consumed"] is True
    assert review["answers"]["standing_demo_authorization_valid"] is True
    assert review["answers"]["bounded_demo_probe_preflight_approved"] is True
    assert review["answers"]["review_grants_runtime_authority"] is False
    assert review["answers"]["bounded_demo_probe_authorized"] is False
    assert review["answers"]["probe_authority_granted"] is False
    assert review["answers"]["order_authority_granted"] is False
    assert review["answers"]["promotion_evidence"] is False


def test_false_negative_operator_review_explicit_approval_accepts_standing_demo_envelope():
    packet = _false_negative_candidate_packet_fixture()
    review = build_false_negative_operator_review(
        false_negative_candidate_packet=packet,
        standing_demo_authorization=_standing_demo_authorization_fixture(),
        decision="approve-preflight",
        now_utc=dt.datetime(2026, 6, 21, 15, 10, tzinfo=dt.timezone.utc),
    )

    assert review["status"] == FALSE_NEGATIVE_APPROVED_FOR_PREFLIGHT_STATUS
    assert review["decision"] == "approve-preflight"
    assert review["operator_id"] == "pm"
    assert review["operator_review_approval_source"] == "standing_demo_authorization"
    assert review["typed_confirm_provided"] is False
    assert review["typed_confirm_matches"] is False
    assert review["operator_review_approved_for_preflight"] is True
    assert review["answers"]["standing_demo_authorization_valid"] is True
    assert review["answers"]["standing_demo_authorization_consumed"] is True
    assert review["answers"]["bounded_demo_probe_preflight_approved"] is True
    assert review["answers"]["review_grants_runtime_authority"] is False
    assert review["answers"]["bounded_demo_probe_authorized"] is False
    assert review["answers"]["probe_authority_granted"] is False
    assert review["answers"]["order_authority_granted"] is False
    assert review["answers"]["promotion_evidence"] is False
    assert review["standing_demo_authorization"]["risk_cap_lineage"]["valid"] is True
    assert (
        review["standing_demo_authorization"]["risk_cap_lineage"]["resolved_cap_usdt"]
        == 955.24342626
    )


def test_false_negative_operator_review_wrong_typed_confirm_overrides_standing_demo_envelope():
    packet = _false_negative_candidate_packet_fixture()
    review = build_false_negative_operator_review(
        false_negative_candidate_packet=packet,
        standing_demo_authorization=_standing_demo_authorization_fixture(),
        decision="approve-preflight",
        typed_confirm="approve_cost_gate_false_negative_preflight:wrong:1",
        now_utc=dt.datetime(2026, 6, 21, 15, 10, tzinfo=dt.timezone.utc),
    )

    assert review["status"] == "TYPED_CONFIRM_REQUIRED"
    assert review["operator_review_approval_source"] is None
    assert review["operator_review_approved_for_preflight"] is False
    assert review["answers"]["standing_demo_authorization_valid"] is False
    assert review["answers"]["standing_demo_authorization_consumed"] is False
    assert "standing_demo_authorization_valid_for_preflight_review" not in review[
        "blocking_gates"
    ]
    assert "typed_confirm_matches" in review["blocking_gates"]
    assert review["answers"]["bounded_demo_probe_preflight_approved"] is False
    assert review["answers"]["bounded_demo_probe_authorized"] is False
    assert review["answers"]["order_authority_granted"] is False


def test_false_negative_operator_review_rejects_contaminated_standing_demo_envelope():
    packet = _false_negative_candidate_packet_fixture()
    standing = _standing_demo_authorization_fixture(
        environment="mainnet",
        demo_only=False,
        answers={
            "demo_only": False,
            "candidate_scoping_required": True,
            "live_authority_granted": True,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "promotion_evidence": False,
        },
    )
    review = build_false_negative_operator_review(
        false_negative_candidate_packet=packet,
        standing_demo_authorization=standing,
        decision="defer",
        now_utc=dt.datetime(2026, 6, 21, 15, 10, tzinfo=dt.timezone.utc),
    )

    assert review["status"] == "STANDING_DEMO_AUTHORIZATION_INVALID_FOR_PREFLIGHT_REVIEW"
    assert "standing_demo_authorization_valid_for_preflight_review" in review[
        "blocking_gates"
    ]
    assert review["operator_review_approved_for_preflight"] is False
    assert review["answers"]["standing_demo_authorization_valid"] is False
    assert review["answers"]["bounded_demo_probe_authorized"] is False
    assert review["answers"]["order_authority_granted"] is False


def test_false_negative_operator_review_requires_exact_approval_phrase():
    packet = _false_negative_candidate_packet_fixture()
    missing = build_false_negative_operator_review(
        false_negative_candidate_packet=packet,
        decision="approve-preflight",
        operator_id="pm",
        typed_confirm="wrong",
        now_utc=dt.datetime(2026, 6, 21, 15, 10, tzinfo=dt.timezone.utc),
    )
    assert missing["status"] == "TYPED_CONFIRM_REQUIRED"
    assert missing["operator_review_approved_for_preflight"] is False
    assert missing["probe_authority_granted"] is False
    assert missing["order_authority_granted"] is False

    top = packet["ranked_false_negative_candidates"][0]
    typed_confirm = expected_false_negative_operator_review_typed_confirm(
        top["side_cell_key"],
        top["false_negative_rank"],
    )
    approved = build_false_negative_operator_review(
        false_negative_candidate_packet=packet,
        decision="approve-preflight",
        operator_id="pm",
        typed_confirm=typed_confirm,
        now_utc=dt.datetime(2026, 6, 21, 15, 10, tzinfo=dt.timezone.utc),
    )
    assert approved["status"] == FALSE_NEGATIVE_APPROVED_FOR_PREFLIGHT_STATUS
    assert approved["operator_review_approved_for_preflight"] is True
    assert approved["answers"]["bounded_demo_probe_preflight_approved"] is True
    assert approved["answers"]["review_grants_runtime_authority"] is False
    assert approved["answers"]["bounded_demo_probe_authorized"] is False
    assert approved["probe_authority_granted"] is False
    assert approved["order_authority_granted"] is False
    assert approved["promotion_evidence"] is False
    assert approved["next_actions"][0] == (
        "build_candidate_matched_bounded_demo_probe_preflight_for_approved_false_negative"
    )


def test_false_negative_operator_review_defer_preserves_existing_fresh_approval():
    packet = _false_negative_candidate_packet_fixture()
    top = packet["ranked_false_negative_candidates"][0]
    typed_confirm = expected_false_negative_operator_review_typed_confirm(
        top["side_cell_key"],
        top["false_negative_rank"],
    )
    approved = build_false_negative_operator_review(
        false_negative_candidate_packet=packet,
        decision="approve-preflight",
        operator_id="pm",
        typed_confirm=typed_confirm,
        now_utc=dt.datetime(2026, 6, 21, 15, 10, tzinfo=dt.timezone.utc),
    )

    preserved = build_false_negative_operator_review(
        false_negative_candidate_packet=packet,
        existing_operator_review=approved,
        decision="defer",
        review_note="cron-default-defer-refresh",
        now_utc=dt.datetime(2026, 6, 21, 15, 15, tzinfo=dt.timezone.utc),
    )

    assert preserved["status"] == FALSE_NEGATIVE_APPROVED_FOR_PREFLIGHT_STATUS
    assert preserved["decision"] == "approve-preflight"
    assert preserved["operator_review_approved_for_preflight"] is True
    assert preserved["answers"]["bounded_demo_probe_preflight_approved"] is True
    assert preserved["answers"]["review_grants_runtime_authority"] is False
    assert preserved["answers"]["bounded_demo_probe_authorized"] is False
    assert preserved["answers"]["probe_authority_granted"] is False
    assert preserved["answers"]["order_authority_granted"] is False
    assert preserved["answers"]["promotion_evidence"] is False
    assert preserved["defer_refresh_preserved_existing_approval"] is True
    assert preserved["defer_refresh_decision"] == "defer"
    assert preserved["defer_refresh_note"] == "cron-default-defer-refresh"


def test_false_negative_operator_review_defer_does_not_preserve_stale_approval():
    packet = _false_negative_candidate_packet_fixture()
    top = packet["ranked_false_negative_candidates"][0]
    typed_confirm = expected_false_negative_operator_review_typed_confirm(
        top["side_cell_key"],
        top["false_negative_rank"],
    )
    approved = build_false_negative_operator_review(
        false_negative_candidate_packet=packet,
        decision="approve-preflight",
        operator_id="pm",
        typed_confirm=typed_confirm,
        now_utc=dt.datetime(2026, 6, 21, 15, 10, tzinfo=dt.timezone.utc),
    )
    packet["generated_at_utc"] = "2026-06-22T16:00:00+00:00"

    deferred = build_false_negative_operator_review(
        false_negative_candidate_packet=packet,
        existing_operator_review=approved,
        decision="defer",
        now_utc=dt.datetime(2026, 6, 22, 16, 11, tzinfo=dt.timezone.utc),
    )

    assert deferred["status"] == FALSE_NEGATIVE_PENDING_OPERATOR_REVIEW_STATUS
    assert deferred["operator_review_approved_for_preflight"] is False
    assert deferred["answers"]["bounded_demo_probe_preflight_approved"] is False
    assert "defer_refresh_preserved_existing_approval" not in deferred


def test_false_negative_operator_review_defer_does_not_mask_current_authority_violation():
    packet = _false_negative_candidate_packet_fixture()
    top = packet["ranked_false_negative_candidates"][0]
    typed_confirm = expected_false_negative_operator_review_typed_confirm(
        top["side_cell_key"],
        top["false_negative_rank"],
    )
    approved = build_false_negative_operator_review(
        false_negative_candidate_packet=packet,
        decision="approve-preflight",
        operator_id="pm",
        typed_confirm=typed_confirm,
        now_utc=dt.datetime(2026, 6, 21, 15, 10, tzinfo=dt.timezone.utc),
    )
    packet["answers"]["probe_authority_granted"] = True

    review = build_false_negative_operator_review(
        false_negative_candidate_packet=packet,
        existing_operator_review=approved,
        decision="defer",
        now_utc=dt.datetime(2026, 6, 21, 15, 15, tzinfo=dt.timezone.utc),
    )

    assert review["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert review["blocking_gates"][0] == "authority_boundary_preserved"
    assert review["operator_review_approved_for_preflight"] is False
    assert review["answers"]["bounded_demo_probe_preflight_approved"] is False
    assert review["answers"]["probe_authority_granted"] is False
    assert review["answers"]["order_authority_granted"] is False
    assert "defer_refresh_preserved_existing_approval" not in review


def test_false_negative_operator_review_defer_does_not_preserve_mismatched_approval():
    packet = _false_negative_candidate_packet_fixture()
    top = packet["ranked_false_negative_candidates"][0]
    typed_confirm = expected_false_negative_operator_review_typed_confirm(
        top["side_cell_key"],
        top["false_negative_rank"],
    )
    approved = build_false_negative_operator_review(
        false_negative_candidate_packet=packet,
        decision="approve-preflight",
        operator_id="pm",
        typed_confirm=typed_confirm,
        now_utc=dt.datetime(2026, 6, 21, 15, 10, tzinfo=dt.timezone.utc),
    )
    approved["selected_side_cell_key"] = "grid_trading|ETHUSDT|Sell"

    review = build_false_negative_operator_review(
        false_negative_candidate_packet=packet,
        existing_operator_review=approved,
        decision="defer",
        now_utc=dt.datetime(2026, 6, 21, 15, 15, tzinfo=dt.timezone.utc),
    )

    assert review["status"] == FALSE_NEGATIVE_PENDING_OPERATOR_REVIEW_STATUS
    assert review["operator_review_approved_for_preflight"] is False
    assert review["answers"]["bounded_demo_probe_preflight_approved"] is False
    assert review["answers"]["review_grants_runtime_authority"] is False
    assert "defer_refresh_preserved_existing_approval" not in review


def test_false_negative_operator_review_blocks_authority_bearing_input():
    packet = _false_negative_candidate_packet_fixture()
    packet["answers"]["probe_authority_granted"] = True
    review = build_false_negative_operator_review(
        false_negative_candidate_packet=packet,
        now_utc=dt.datetime(2026, 6, 21, 15, 10, tzinfo=dt.timezone.utc),
    )

    assert review["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert review["blocking_gates"][0] == "authority_boundary_preserved"
    assert review["operator_review_approved_for_preflight"] is False
    assert review["answers"]["probe_authority_granted"] is False
    assert review["answers"]["order_authority_granted"] is False


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


def test_runtime_adapter_counts_proof_excluded_outcomes_aligned_with_rust() -> None:
    # LOW-3(operator 2026-07-05 裁定 Python 對齊 Rust):禁用判準不再對 proof-excluded
    # row 過濾。Rust 權威側 demo_learning_lane.rs::summarize_side_cell_runtime_state
    # 只保留 record_type=="probe_outcome" 且 realized_net_bps 有限的 row(filter_map+
    # is_finite),不看 strategy_name/lineage。此 unattributed 且缺 lineage 的 fill-backed
    # row(realized_net_bps=-25.0,有限)在 Rust 側會被納入 count,故 Python 對齊後亦納入,
    # 兩側 completed_outcome_count 逐值一致=1,且因 avg=-25<0 觸發 UCB pure-mean 禁用。
    # 對比前一版斷言(completed_outcome_count==0、不禁用)已被 operator 裁定推翻。
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
    proof_excluded_outcome = {
        "record_type": "probe_outcome",
        "generated_at_utc": "2026-06-21T12:11:00+00:00",
        "attempt_id": _selected_reject_event()["context_id"],
        "side_cell_key": "ma_crossover|ETHUSDT|Sell",
        "strategy_name": "unattributed:bybit_auto",
        "outcome_source": "demo_fill_execution",
        "order_id": "bybit-unmatched-1",
        "exec_id": "exec-unmatched-1",
        "realized_net_bps": -25.0,
    }

    # probe_proposal.max_probe_orders 取大值(_candidate_max_orders 讀此路徑),確保
    # remaining>0,不被 probe_budget_exhausted 先攔,使禁用純由 UCB pure-mean(n=1,
    # avg=-25<0)主導。
    runtime_state = summarize_side_cell_runtime_state(
        {
            "side_cell_key": "ma_crossover|ETHUSDT|Sell",
            "probe_proposal": {"max_probe_orders": 100},
        },
        [*ledger, proof_excluded_outcome],
        now_ms=1_782_046_800_000,
        cfg=RuntimeAdmissionConfig(min_failed_outcomes_to_disable=1),
    )
    decision = evaluate_probe_admission(
        _runtime_plan(order_authority=ORDER_AUTHORITY_GRANTED),
        {
            **_selected_reject_event(),
            "context_id": "ctx-demo-ma_crossover-ETHUSDT-1782046800000",
            "ts_ms": 1_782_046_800_000,
        },
        ledger_rows=[*ledger, proof_excluded_outcome],
        now_utc=dt.datetime(2026, 6, 21, 14, 0, tzinfo=dt.timezone.utc),
        cfg=RuntimeAdmissionConfig(min_failed_outcomes_to_disable=1),
        adapter_enabled=True,
    )

    # 對齊 Rust:realized_net_bps 有限的 probe_outcome 全數計入禁用判準,不 proof-exclude。
    # runtime_state 直調用大 budget(max_probe_orders=100),禁用純由 UCB pure-mean 主導。
    assert runtime_state["raw_completed_outcome_count"] == 1
    assert runtime_state["completed_outcome_count"] == 1
    assert runtime_state["avg_realized_net_bps"] == -25.0
    assert runtime_state["disabled"] is True
    assert runtime_state["disable_reason"] == "realized_probe_outcomes_fail_learning_threshold"
    # 診斷欄位仍如實報告 proof-exclusion(透明度,不影響禁用判準)。
    assert runtime_state["proof_eligible_completed_outcome_count"] == 0
    assert runtime_state["proof_excluded_completed_outcome_count"] == 1
    assert runtime_state["proof_exclusion_present"] is True
    assert runtime_state["proof_exclusion_reason_counts"]["unattributed_strategy_name"] == 1
    # decision 路徑 candidate budget=2(來自 scorecard),此處僅驗 count 已對齊 Rust=1
    # (不驗 disable_reason,因 remaining/budget 與 UCB 的優先級由 plan budget 決定)。
    assert decision["runtime_state"]["completed_outcome_count"] == 1
    assert decision["runtime_state"]["proof_excluded_completed_outcome_count"] == 1


def _rust_realized_net_bps_reference(rows: list[dict]) -> list[float]:
    """逐值鏡像 Rust demo_learning_lane.rs::summarize_side_cell_runtime_state 的
    realized_net_bps 構造:record_type=="probe_outcome" → filter_map(realized_net_bps)
    → is_finite。不看 strategy_name / lineage / proof_exclusion。作為對拍基準。"""
    out: list[float] = []
    for row in rows:
        if row.get("record_type") != "probe_outcome":
            continue
        raw = row.get("realized_net_bps")
        if raw is None or isinstance(raw, bool):
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            out.append(value)
    return out


def test_runtime_adapter_completed_count_matches_rust_filter_on_fill_backed_rows() -> None:
    # 對拍證明:對含 fill 證據(exec_id/order_id)但 proof-excluded 的 row,Python 的
    # completed_outcome_count 必與 Rust filter 基準(_rust_realized_net_bps_reference)逐值一致。
    # 混入:合格 row、unattributed 缺 lineage row、缺 realized_net_bps row、NaN row。
    key = "ma_crossover|ETHUSDT|Sell"
    rows = [
        {"record_type": "probe_outcome", "side_cell_key": key, "realized_net_bps": -30.0},
        {
            "record_type": "probe_outcome",
            "side_cell_key": key,
            "strategy_name": "unattributed:bybit_auto",
            "exec_id": "exec-x1",
            "order_id": "ord-x1",
            "realized_net_bps": -40.0,
        },
        {"record_type": "probe_outcome", "side_cell_key": key},  # 無 realized → 兩側皆排除
        {"record_type": "probe_outcome", "side_cell_key": key, "realized_net_bps": float("nan")},
        {"record_type": "side_cell_disabled", "side_cell_key": key},  # 非 outcome
    ]
    expected = _rust_realized_net_bps_reference(rows)
    assert expected == [-30.0, -40.0]  # 合格 + fill-backed(proof-excluded)皆計入,NaN/缺失排除

    state = summarize_side_cell_runtime_state(
        {"side_cell_key": key, "probe_proposal": {"max_probe_orders": 100}},
        rows,
        now_ms=1_782_046_800_000,
        cfg=RuntimeAdmissionConfig(min_failed_outcomes_to_disable=8),
    )
    assert state["completed_outcome_count"] == len(expected) == 2
    assert state["avg_realized_net_bps"] == sum(expected) / len(expected)
    # 診斷欄位(不影響上方對齊 Rust 的判準 count):4 個 probe_outcome 中,fill-backed
    # unattributed row(缺 lineage)、缺 realized_net_bps row、NaN row 各計一次 proof-excluded=3;
    # proof-eligible=raw(4)−excluded(3)=1。fill-backed row 雖 proof-excluded 仍計入判準。
    assert state["raw_completed_outcome_count"] == 4
    assert state["proof_excluded_completed_outcome_count"] == 3
    assert state["proof_eligible_completed_outcome_count"] == 1


def test_runtime_adapter_normalizes_cost_gate_negative_reason_text():
    assert normalize_reject_reason_code(
        "cost_gate(JS-demo): negative edge -15.2 bps blocked"
    ) == "cost_gate_js_demo_negative_edge"
    assert normalize_reject_reason_code(
        "rejected:cost_gate(JS-demo): estimated=-2.74bps < 0 — blocked / 負估計阻擋"
    ) == "cost_gate_js_demo_negative_edge"


def test_reject_materializer_builds_blocked_admission_rows_from_feature_rows():
    event_ts_ms = 1_782_037_200_000
    feature_rows = [
        {
            "ts_ms": event_ts_ms,
            "context_id": "ctx-materialized-eth",
            "engine_mode": "live_demo",
            "strategy_name": "ma_crossover",
            "symbol": "ethusdt",
            "side": -1,
            "reject_reason_code": "cost_gate_js_demo_negative_edge",
            "last_price": 2000.0,
        },
        {
            "ts_ms": event_ts_ms,
            "context_id": "ctx-already-present",
            "engine_mode": "live_demo",
            "strategy_name": "ma_crossover",
            "symbol": "ETHUSDT",
            "side": "Sell",
            "reject_reason_code": "cost_gate_js_demo_negative_edge",
            "last_price": 2000.0,
        },
    ]
    batch = build_materialized_reject_ledger_batch(
        _runtime_plan(),
        feature_rows,
        existing_ledger_rows=[
            {
                "record_type": "probe_admission_decision",
                "attempt_id": "ctx-already-present",
            }
        ],
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
    )

    assert batch["schema_version"] == "cost_gate_reject_materializer_v1"
    assert batch["status"] == "MATERIALIZED_REJECT_ROWS_PRESENT"
    assert batch["input_feature_row_count"] == 2
    assert batch["materialized_record_count"] == 1
    assert batch["skipped_existing_attempt_count"] == 1
    assert batch["decision_counts"] == {"ORDER_AUTHORITY_NOT_GRANTED": 1}
    record = batch["records"][0]
    assert record["record_type"] == "probe_admission_decision"
    assert record["attempt_id"] == "ctx-materialized-eth"
    assert record["decision"] == "ORDER_AUTHORITY_NOT_GRANTED"
    assert record["allowed_to_submit_order"] is False
    assert record["source"] == "materialized_from_pg_decision_features"
    assert record["event"]["side"] == "Sell"
    assert record["event"]["symbol"] == "ETHUSDT"
    assert record["event"]["last_price"] == 2000.0

    outcomes = build_blocked_signal_outcome_records(
        [record],
        [
            {"symbol": "ETHUSDT", "ts_ms": event_ts_ms, "close": 2000.0},
            {"symbol": "ETHUSDT", "ts_ms": event_ts_ms + 3_600_000, "close": 1980.0},
        ],
        now_utc=dt.datetime(2026, 6, 21, 12, 11, tzinfo=dt.timezone.utc),
        cfg=ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0),
    )
    assert len(outcomes) == 1
    assert outcomes[0]["source_admission_decision"] == "ORDER_AUTHORITY_NOT_GRANTED"
    assert outcomes[0]["promotion_evidence"] is False
    assert outcomes[0]["realized_net_bps"] > 0.0


def test_reject_materializer_append_is_explicit_and_readable(tmp_path: Path):
    batch = build_materialized_reject_ledger_batch(
        _runtime_plan(),
        [
            {
                "ts_ms": 1_782_037_200_000,
                "context_id": "ctx-materialized-append",
                "engine_mode": "live_demo",
                "strategy_name": "ma_crossover",
                "symbol": "ETHUSDT",
                "side": "Sell",
                "reject_reason_code": "cost_gate_js_demo_negative_edge",
            }
        ],
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
    )
    ledger = tmp_path / "probe_ledger.jsonl"
    assert append_materialized_records_to_ledger(ledger, batch) == 1
    assert batch["append_requested"] is True
    assert batch["appended_to_ledger"] is True

    rows = read_jsonl_ledger(ledger)
    assert len(rows) == 1
    assert rows[0]["attempt_id"] == "ctx-materialized-append"
    assert rows[0]["decision"] == "ORDER_AUTHORITY_NOT_GRANTED"


def test_reject_materializer_materializes_recent_pipeline_snapshot_rejects():
    rows = pipeline_snapshot_recent_intents_to_feature_rows(
        {
            "trading_mode": "demo",
            "recent_intents": [
                {
                    "timestamp_ms": 1_782_245_279_951,
                    "result": "rejected:cost_gate(JS-demo): estimated=-2.74bps < 0",
                    "intent": {
                        "strategy": "ma_crossover",
                        "symbol": "ethusdt",
                        "intent_type": "open_short",
                        "limit_price": 2000.5,
                    },
                },
                {
                    "timestamp_ms": 1_782_245_279_952,
                    "result": "rejected:cost_gate(JS-demo): atr unavailable",
                    "intent": {
                        "strategy": "ma_crossover",
                        "symbol": "ETHUSDT",
                        "is_long": True,
                    },
                },
            ],
        },
        engine_modes=("demo",),
        snapshot_path=Path("/tmp/openclaw/pipeline_snapshot.json"),
    )

    assert len(rows) == 1
    assert rows[0]["context_id"].startswith(
        "snapshot|1782245279951|ma_crossover|ETHUSDT|Sell|2000.5"
    )
    assert rows[0]["engine_mode"] == "demo"
    assert rows[0]["side"] == "Sell"
    assert rows[0]["reject_reason_code"] == "cost_gate_js_demo_negative_edge"
    assert rows[0]["last_price"] == 2000.5
    assert rows[0]["_materializer_source"] == "pipeline_snapshot_recent_intents"

    batch = build_materialized_reject_ledger_batch(
        _runtime_plan(),
        rows,
        now_utc=dt.datetime(2026, 6, 21, 12, 0, tzinfo=dt.timezone.utc),
    )

    assert batch["materialized_record_count"] == 1
    record = batch["records"][0]
    assert record["source"] == "materialized_from_pipeline_snapshot_recent_intents"
    assert record["source_schema"] == "pipeline_snapshot.recent_intents"
    assert record["source_snapshot_path"] == "/tmp/openclaw/pipeline_snapshot.json"
    assert record["event"]["symbol"] == "ETHUSDT"
    assert record["event"]["side"] == "Sell"
    assert record["decision"] == "ORDER_AUTHORITY_NOT_GRANTED"
    assert record["allowed_to_submit_order"] is False


def test_reject_materializer_skips_snapshot_duplicate_when_pg_event_exists():
    ts_ms = 1_782_245_279_951
    batch = build_materialized_reject_ledger_batch(
        _runtime_plan(),
        [
            {
                "ts_ms": ts_ms,
                "context_id": "snapshot|duplicate",
                "engine_mode": "demo",
                "strategy_name": "ma_crossover",
                "symbol": "ETHUSDT",
                "side": "Sell",
                "reject_reason_code": "cost_gate_js_demo_negative_edge",
                "_materializer_source": "pipeline_snapshot_recent_intents",
            }
        ],
        existing_ledger_rows=[
            {
                "record_type": "probe_admission_decision",
                "attempt_id": "ctx-pg-real",
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "event": {
                    "strategy_name": "ma_crossover",
                    "symbol": "ETHUSDT",
                    "side": "Sell",
                    "ts_ms": ts_ms,
                },
            }
        ],
        now_utc=dt.datetime(2026, 6, 21, 12, 0, tzinfo=dt.timezone.utc),
    )

    assert batch["materialized_record_count"] == 0
    assert batch["skipped_existing_attempt_count"] == 1
    assert batch["skipped_existing_event_key_count"] == 1


def test_reject_materializer_sql_is_cost_gate_negative_edge_readonly_shape():
    sql, params = build_cost_gate_reject_feature_sql(
        RejectMaterializerConfig(engine_modes=("demo",), lookback_hours=4, limit=123)
    )
    assert "FROM learning.decision_features f" in sql
    assert "LEFT JOIN trading.decision_context_snapshots d" in sql
    assert "f.reject_reason_code LIKE 'cost_gate%%'" in sql
    assert "f.reject_reason_code LIKE '%%negative_edge%%'" in sql
    assert "LIMIT %s" in sql
    assert params == [["demo"], 4, 123]


def test_reject_feature_row_to_event_normalizes_side_symbol_and_ts():
    event = reject_feature_row_to_event(
        {
            "ts": dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
            "context_id": "ctx-normalized",
            "engine_mode": "LIVE_DEMO",
            "strategy_name": "ma_crossover",
            "symbol": "ethusdt",
            "side": -1,
            "reject_reason_code": "cost_gate_js_demo_negative_edge",
            "last_price": "2000.5",
        }
    )
    assert event["symbol"] == "ETHUSDT"
    assert event["side"] == "Sell"
    assert event["engine_mode"] == "live_demo"
    assert event["ts_ms"] == 1_782_040_200_000
    assert event["last_price"] == 2000.5
