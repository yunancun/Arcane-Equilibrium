"""alpha_discovery_throughput focused tests."""

from __future__ import annotations

import datetime as dt
import json
import subprocess
from datetime import date, timedelta
from pathlib import Path

from aeg_candidate_metrics import builder as candidate_metrics_builder
from alpha_discovery_throughput.discovery_loop import build_discovery_plan
from alpha_discovery_throughput.edge_snapshot_adapter import build_edge_snapshot, row_is_live_grade
from alpha_discovery_throughput.execution_spine import evaluate_execution_realism
from alpha_discovery_throughput.flash_dip_ladder import build_flash_dip_ladder_packets
from alpha_discovery_throughput.packet import (
    build_candidate_packet,
    build_direct_report_from_packet,
    daily_returns_from_samples,
)
from alpha_discovery_throughput.runtime_runner import (
    build_runtime_killboard,
    collect_cost_gate_learning_lane_arm,
    collect_flash_dip_execution_realism_arm,
    collect_flash_dip_arm,
    collect_flash_dip_l1_replay_arm,
    collect_polymarket_leadlag_arm,
    collect_runtime_arms,
    run_once,
    _latest_json_line,
    _learning_summary,
)
from alpha_discovery_throughput.signal_manifest import build_signal_spec, validate_signal_manifest
from cost_gate_learning_lane.status import REQUIRED_SOURCE_RELATIVE_PATHS


def test_latest_json_line_handles_oversized_status_line(tmp_path: Path):
    path = tmp_path / "status.jsonl"
    old = {"ts_utc": "2026-06-20T18:00:00Z", "status": "old"}
    latest = {
        "ts_utc": "2026-06-20T19:43:09Z",
        "status": "latest",
        "payload": "x" * 300_000,
    }
    path.write_text(
        json.dumps(old, separators=(",", ":"))
        + "\n"
        + json.dumps(latest, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )

    row, err = _latest_json_line(path)

    assert err is None
    assert row is not None
    assert row["status"] == "latest"


def test_learning_summary_mirrors_completion_and_top_evidence_fields():
    summary = _learning_summary({
        "status": "OPERATOR_GATED_LEARNING_READY",
        "task_count": 1,
        "operator_required_count": 1,
        "runtime_mutation_required_count": 0,
        "engineering_actionable_count": 1,
        "top_task": {
            "task_id": "cost_gate_demo_learning_lane:operator_probe_review:x",
            "arm_id": "cost_gate_demo_learning_lane",
            "task_type": "operator_probe_review",
            "learning_objective": (
                "operator_review_top_blocked_signal_side_cell_before_bounded_demo_probe"
            ),
            "completion_gate": (
                "operator_authorization_recorded_and_probe_preflight_passes"
            ),
            "completion_status": "PENDING_EVIDENCE",
            "completion_evidence_required": [
                "operator_authorization_artifact_exists",
                "isolated_probe_preflight_passes",
                "candidate_specific_side_cell_or_candidate_key_evidence_present",
            ],
            "actionability": "operator_required",
            "requires_operator_authorization": True,
            "runtime_mutation_required": False,
            "side_effect_boundary": (
                "recommendation_only_no_order_authority_no_runtime_mutation"
            ),
            "next_trigger": (
                "operator_review_blocked_outcome_scorecard_before_demo_probe_authority"
            ),
            "evidence": {
                "blocked_signal_top_review_candidate_side_cell_key": (
                    "ma_crossover|ETHUSDT|Sell"
                ),
                "blocked_signal_top_review_candidate_wrongful_block_score": 3.444444,
                "blocked_signal_top_review_candidate_net_cost_cushion_bps": 5.166667,
                "demo_learning_stack_dry_run_review_operator_next_action": (
                    "operator_review_dry_run_preview_then_apply_learning_stack_if_accepted"
                ),
                "demo_learning_stack_dry_run_review_dry_run_preview_shell": (
                    "OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=0 install_stack"
                ),
                "demo_learning_stack_dry_run_review_operator_only_apply_shell": (
                    "OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=1 install_stack"
                ),
                "demo_learning_stack_dry_run_review_operator_only_rollback_shell": (
                    "OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=1 install_stack --remove"
                ),
                "demo_learning_stack_activation_packet_post_install_verification_shell": (
                    "demo_learning_stack_healthcheck.py --fail-on-not-active"
                ),
                "demo_learning_stack_dry_run_review_activation_packet_missing_cron_count": 4,
                "demo_learning_stack_dry_run_review_global_cost_gate_lowering_recommended": False,
                "demo_learning_stack_dry_run_review_order_authority_granted": False,
                "demo_learning_stack_dry_run_review_probe_authority_granted": False,
            },
        },
    })

    assert summary["top_learning_task_completion_gate"] == (
        "operator_authorization_recorded_and_probe_preflight_passes"
    )
    assert summary["top_learning_task_completion_status"] == "PENDING_EVIDENCE"
    assert summary["top_learning_task_completion_evidence_required_count"] == 3
    assert summary["top_learning_task_evidence_key_count"] == 12
    assert summary["top_learning_task_blocked_signal_top_review_candidate_side_cell_key"] == (
        "ma_crossover|ETHUSDT|Sell"
    )
    assert summary[
        "top_learning_task_blocked_signal_top_review_candidate_wrongful_block_score"
    ] == 3.444444
    assert summary[
        "top_learning_task_blocked_signal_top_review_candidate_net_cost_cushion_bps"
    ] == 5.166667
    assert summary["top_learning_task_side_effect_boundary"] == (
        "recommendation_only_no_order_authority_no_runtime_mutation"
    )
    assert summary["top_learning_task_operator_next_action"] == (
        "operator_review_dry_run_preview_then_apply_learning_stack_if_accepted"
    )
    assert summary["top_learning_task_dry_run_preview_shell"] == (
        "OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=0 install_stack"
    )
    assert summary["top_learning_task_operator_only_apply_shell"] == (
        "OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=1 install_stack"
    )
    assert summary["top_learning_task_operator_only_rollback_shell"] == (
        "OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=1 install_stack --remove"
    )
    assert summary["top_learning_task_post_install_verification_shell"] == (
        "demo_learning_stack_healthcheck.py --fail-on-not-active"
    )
    assert summary["top_learning_task_missing_cron_count"] == 4
    assert summary["top_learning_task_global_cost_gate_lowering_recommended"] is False
    assert summary["top_learning_task_order_authority_granted"] is False
    assert summary["top_learning_task_probe_authority_granted"] is False
    assert summary["top_engineering_learning_task_available"] is False
    assert summary["top_engineering_learning_task_arm_id"] is None


def test_learning_summary_exposes_parallel_engineering_task_when_operator_gate_top():
    operator_task = {
        "task_id": "cost_gate_demo_learning_lane:cost_gate_learning_activation:x",
        "arm_id": "cost_gate_demo_learning_lane",
        "task_type": "cost_gate_learning_activation",
        "learning_objective": "operator_review_learning_stack_before_cron_apply",
        "completion_gate": "learning_lane_ledger_and_blocked_outcomes_accumulating",
        "completion_status": "PENDING_EVIDENCE",
        "completion_evidence_required": [
            "demo_learning_stack_healthcheck_status:EVIDENCE_STACK_ACTIVE",
        ],
        "actionability": "operator_required",
        "requires_operator_authorization": True,
        "runtime_mutation_required": True,
        "side_effect_boundary": (
            "recommendation_only_operator_runtime_mutation_required_"
            "no_order_or_probe_authority"
        ),
        "next_trigger": (
            "operator_review_dry_run_preview_then_apply_learning_stack_if_accepted"
        ),
        "evidence": {
            "demo_learning_stack_dry_run_review_operator_next_action": (
                "operator_review_dry_run_preview_then_apply_learning_stack_if_accepted"
            ),
        },
    }
    engineering_task = {
        "task_id": "polymarket_leadlag_ic:polymarket_replay_history:y",
        "arm_id": "polymarket_leadlag_ic",
        "task_type": "polymarket_replay_history",
        "learning_objective": "collect_dated_replay_history_for_leadlag_ic",
        "completion_gate": "dated_replay_history_ready_for_aeg_recheck",
        "completion_status": "PENDING_EVIDENCE",
        "completion_evidence_required": [
            "candidate_replay_history_sample_count",
            "candidate_replay_history_n_days",
        ],
        "actionability": "engineering_actionable",
        "requires_operator_authorization": False,
        "runtime_mutation_required": False,
        "side_effect_boundary": "recommendation_only_no_order_authority_no_runtime_mutation",
        "next_trigger": "collect_more_dated_polymarket_replay_history_before_promotion",
        "evidence": {
            "candidate_replay_history_status": "INSUFFICIENT_HISTORY",
            "candidate_replay_history_sample_count": 12,
        },
    }

    summary = _learning_summary({
        "status": "OPERATOR_GATED_LEARNING_READY",
        "task_count": 2,
        "operator_required_count": 1,
        "runtime_mutation_required_count": 1,
        "engineering_actionable_count": 1,
        "top_task": operator_task,
        "tasks": [operator_task, engineering_task],
    })

    assert summary["top_learning_task_arm_id"] == "cost_gate_demo_learning_lane"
    assert summary["top_learning_task_type"] == "cost_gate_learning_activation"
    assert summary["top_learning_task_requires_operator_authorization"] is True
    assert summary["top_learning_task_runtime_mutation_required"] is True
    assert summary["top_engineering_learning_task_available"] is True
    assert summary["top_engineering_learning_task_arm_id"] == "polymarket_leadlag_ic"
    assert summary["top_engineering_learning_task_type"] == "polymarket_replay_history"
    assert summary["top_engineering_learning_task_completion_gate"] == (
        "dated_replay_history_ready_for_aeg_recheck"
    )
    assert summary[
        "top_engineering_learning_task_completion_evidence_required_count"
    ] == 2
    assert summary["top_engineering_learning_task_actionability"] == (
        "engineering_actionable"
    )
    assert (
        summary["top_engineering_learning_task_requires_operator_authorization"]
        is False
    )
    assert summary["top_engineering_learning_task_runtime_mutation_required"] is False
    assert summary["top_engineering_learning_task_side_effect_boundary"] == (
        "recommendation_only_no_order_authority_no_runtime_mutation"
    )
    assert summary["top_engineering_learning_task_next_trigger"] == (
        "collect_more_dated_polymarket_replay_history_before_promotion"
    )
    assert summary["top_engineering_learning_task_evidence_key_count"] == 2
    assert summary["top_engineering_learning_task_evidence"][
        "candidate_replay_history_sample_count"
    ] == 12


def _signal_spec(**extra):
    return build_signal_spec(
        candidate_id="candidate-x",
        family_id="family-x",
        hypothesis="funding plus orderflow residual alpha",
        horizon={"bars": 12, "unit": "1m"},
        inputs=["funding_rate", "ofi_10s", "btc_return"],
        universe_ref={"source": "research.fnd2", "hash": "u"},
        regime_ref={"source": "research.aeg_regime", "hash": "r"},
        feature_schema={"version": "v1"},
        cost_model_ref={"source": "demo_cost", "version": "v1"},
        residualization={"method": "ols", "factors": ["btc_return"]},
        failure_taxonomy=["cost_defeat", "beta_edge"],
        hidden_oos_policy={"state_required": "sealed", "open_once": True},
        extra=extra,
    )


def _samples(n: int = 64) -> list[dict]:
    rows = []
    for i in range(n):
        regime = "chop" if i < n // 2 else "bear"
        day = (date(2026, 3, 1) + timedelta(days=i)).isoformat()
        net = 8.0 + (i % 3)
        rows.append({
            "sample_id": f"s{i}",
            "sample_ts_utc": f"{day}T00:00:00Z",
            "sample_date": day,
            "symbol": "BTCUSDT",
            "regime": regime,
            "independence_bucket": f"{regime}:{i}",
            "gross_bps": net + 2.0,
            "cost_bps": 2.0,
            "net_bps": net,
            "is_oos": i % 2 == 0,
        })
    return rows


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


def _init_clean_source_repo_with_origin(tmp_path: Path) -> Path:
    remote = tmp_path / "remote.git"
    repo = tmp_path / "source"
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
    return repo


def _pbo_candidates(n_days: int = 64) -> dict[str, dict[str, float]]:
    return {
        f"cell_{cell}": {
            (date(2026, 3, 1) + timedelta(days=d)).isoformat(): 0.0001 * cell + d * 0.000001
            for d in range(n_days)
        }
        for cell in range(12)
    }


def test_signal_manifest_uses_existing_validator_and_fails_future_data():
    spec = _signal_spec()
    assert validate_signal_manifest(spec)["ok"] is True

    bad = dict(spec)
    bad["pit_contract"] = {"point_in_time": True, "future_data_allowed": True}
    bad.pop("spec_hash", None)
    verdict = validate_signal_manifest(bad)
    assert verdict["ok"] is False
    assert verdict["reason"] == "pit_contract_future_data_allowed"


def test_candidate_packet_feeds_existing_aeg_direct_rows_and_metrics():
    samples = _samples()
    packet = build_candidate_packet(
        candidate_id="candidate-x",
        strategy_family="listing_fade",
        parameter_cell_id="v0",
        selected_variant="v0",
        sample_unit="event_window",
        samples=samples,
        annualization_factor=365,
        k_trials=8,
        daily_returns=daily_returns_from_samples(samples),
        pbo_candidates=_pbo_candidates(),
        signal_spec=_signal_spec(),
    )
    report, summary = build_direct_report_from_packet(packet, run_id="packet-run")
    assert summary["sample_count"] == 64
    assert report["candidate_id"] == "candidate-x"

    rows, adapted = candidate_metrics_builder.build_candidate_metrics(
        report,
        run_id="metrics-run",
        candidate_id="candidate-x",
        strategy_family="listing_fade",
        parameter_cell_id="v0",
    )
    assert adapted["metric_status_counts"] == {"PASS": 2}
    assert {row["sample_unit"] for row in rows} == {"event_window"}


def test_execution_spine_reuses_execution_realism_gate_and_fails_low_sample():
    observations = [
        {
            "submitted": True,
            "filled": True,
            "adverse_selection_bps": 1.0 + (i % 3) * 0.1,
            "latency_ms": 100 + i,
            "participation_rate": 0.01,
            "capacity_notional_usdt": 5000,
            "slippage_bps": 1.0,
        }
        for i in range(40)
    ]
    payload = evaluate_execution_realism(
        observations=observations,
        candidate_id="candidate-x",
        strategy_family="maker_arm",
        parameter_cell_id="v0",
        order_style="maker",
        maker_fee_bps=2.0,
        taker_fee_bps=5.5,
    )
    assert payload["status"] == "PASS"
    assert payload["sample_count"] == 40

    low_n = evaluate_execution_realism(
        observations=observations[:4],
        candidate_id="candidate-x",
        strategy_family="maker_arm",
        parameter_cell_id="v0",
        order_style="maker",
        maker_fee_bps=2.0,
        taker_fee_bps=5.5,
    )
    assert low_n["status"] == "FAIL"
    assert "sample_count_below_30" in low_n["reject_reasons"]


def test_discovery_loop_waits_gate_b_watch_only_and_prioritizes_ready_chain():
    plan = build_discovery_plan([
        {
            "arm_id": "gate_b",
            "gate_status": "WATCH_ONLY",
            "sample_count": 0,
            "artifacts_ready": False,
        },
        {
            "arm_id": "funding_oi",
            "gate_status": "READY",
            "sample_count": 42,
            "artifacts_ready": True,
        },
    ], now_utc=dt.datetime(2026, 6, 19, tzinfo=dt.timezone.utc))

    assert plan["arms"][0]["arm_id"] == "funding_oi"
    assert plan["arms"][0]["action"] == "READY_FOR_AEG_CHAIN"
    assert next(row for row in plan["arms"] if row["arm_id"] == "gate_b")["action"] == "WAIT"
    assert plan["policy"] == "read_only_recommendations_no_probe_or_trade_side_effect"
    scorecard = plan["profitability_blocker_scorecard"]
    assert scorecard["status"] == "ACTIONABLE_ALPHA_REVIEW_READY"
    assert scorecard["promotion_ready_count"] == 1
    blockers = {row["arm_id"]: row for row in scorecard["arms"]}
    assert blockers["funding_oi"]["blocker_class"] == "candidate_review_ready"
    assert blockers["gate_b"]["blocker_class"] == "event_wait"


def test_discovery_loop_blocks_no_edge_survives_without_source_failure_label():
    plan = build_discovery_plan([
        {
            "arm_id": "vol_event_order_flow",
            "gate_status": "NO_EDGE_SURVIVES",
            "sample_count": 4,
            "artifacts_ready": False,
            "source_ok": True,
        },
    ], now_utc=dt.datetime(2026, 6, 19, tzinfo=dt.timezone.utc))

    assert plan["arms"][0]["action"] == "BLOCK"
    assert plan["arms"][0]["reason"] == "gate_status:no_edge_survives"
    scorecard = plan["profitability_blocker_scorecard"]
    assert scorecard["status"] == "NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED"
    assert scorecard["blocker_counts"] == {"rejected_no_edge": 1}
    assert scorecard["arms"][0]["primary_blocker"] == "gate_status:no_edge_survives"


def test_profitability_blocker_scorecard_classifies_runtime_blockers():
    plan = build_discovery_plan([
        {
            "arm_id": "gate_b_listing_fade",
            "gate_status": "WATCH_ONLY",
            "sample_count": 0,
            "artifacts_ready": False,
            "source_ok": True,
        },
        {
            "arm_id": "polymarket_leadlag_ic",
            "gate_status": "CAPTURING",
            "sample_count": 16,
            "artifacts_ready": False,
            "source_ok": True,
            "detail": {
                "min_samples_remaining_to_gate": 14,
                "sample_gate_eta_utc": "2026-06-20T19:52:03+00:00",
                "price_feedback_partial_collapse_count": 4,
                "pre_gate_hac_watchlist_count": 3,
            },
        },
        {
            "arm_id": "mm_verdict_maker_edge",
            "gate_status": "CAPTURING",
            "sample_count": 31,
            "artifacts_ready": False,
            "source_ok": True,
            "detail": {
                "walk_forward_failure_summary": {
                    "status": "NO_TRAIN_POSITIVE_CELL",
                    "candidate_count": 51,
                    "best_train_candidate": {"name": "quoted_half_spread_bps_train_p75_ge"},
                    "best_holdout_candidate": {"name": "symbol == ADAUSDT"},
                },
                "cost_wall_summary": {
                    "available": True,
                    "best_symbol_by_net_edge": "LABUSDT",
                    "best_fee_round_trip_shortfall_bps": 1.73,
                },
                "sample_gated_cost_wall_summary": {
                    "available": True,
                    "status": "SAMPLE_GATED_CURRENT_FEE_COST_WALL",
                    "best_sample_gated_net_bps": -1.73,
                    "best_sample_gated_fee_round_trip_shortfall_bps": 1.73,
                    "break_even_maker_fee_bps_per_side": 1.135,
                    "fee_reduction_needed_bps_per_side": 0.865,
                    "sample_gated_cell_count": 41,
                },
                "gross_edge_cost_decomposition": {
                    "available": True,
                    "status": "GROSS_EDGE_BELOW_CURRENT_FEE_COST_WALL",
                    "gross_positive_sample_gated_cell_count": 74,
                    "current_fee_positive_sample_gated_cell_count": 0,
                    "best_sample_gated_gross_edge_bps": 2.27,
                    "best_gross_cell_net_bps": -1.73,
                    "break_even_maker_fee_bps_per_side": 1.135,
                    "fee_reduction_needed_bps_per_side": 0.865,
                    "best_sample_gated_gross_cell": {
                        "source": "edge_scorecard",
                        "symbol": "LABUSDT",
                        "policy": "informed_skip",
                        "n_fill_only": 170,
                        "edge_before_fees_bps": 2.27,
                        "net_bps": -1.73,
                    },
                    "top_sample_gated_gross_cells": [
                        {
                            "source": "edge_scorecard",
                            "symbol": "LABUSDT",
                            "policy": "informed_skip",
                            "edge_before_fees_bps": 2.27,
                            "net_bps": -1.73,
                        },
                        {
                            "source": "walk_forward_holdout",
                            "condition": "symbol == ADAUSDT",
                            "edge_before_fees_bps": 2.002,
                            "net_bps": -1.998,
                        },
                    ],
                    "best_walk_forward_holdout_gross_candidate": {
                        "name": "symbol=ADAUSDT",
                        "holdout": {
                            "n_fill_only": 714,
                            "edge_before_fees_bps": 2.002,
                            "net_bps": -1.998,
                        },
                    },
                    "low_friction_signal_status": (
                        "LOW_FRICTION_SIGNAL_HOLDOUT_GROSS_POSITIVE_BELOW_CURRENT_FEE"
                    ),
                    "best_low_friction_signal_holdout_gross_candidate": {
                        "name": "quoted_half_spread_bps_train_p75_and_recent_trade_count_10s_train_p25",
                        "train": {
                            "source": "low_friction_signal_train",
                            "n_fill_only": 142,
                            "edge_before_fees_bps": -0.225,
                            "net_bps": -4.225,
                            "sample_gated": True,
                        },
                        "holdout": {
                            "source": "low_friction_signal_holdout",
                            "n_fill_only": 120,
                            "edge_before_fees_bps": 1.91,
                            "net_bps": -2.09,
                        },
                    },
                },
                "low_friction_signal_scorecard": {
                    "status": "LOW_FRICTION_SIGNAL_HOLDOUT_GROSS_POSITIVE_BELOW_CURRENT_FEE",
                    "train_confirmed_gross_scorecard": {
                        "status": "LOW_FRICTION_TRAIN_CONFIRMED_GROSS_BELOW_CURRENT_FEE",
                        "train_confirmed_positive_gross_count": 4,
                        "best_min_train_holdout_gross_bps": 0.63,
                        "gap_to_current_fee_round_trip_bps": 3.37,
                        "best_train_confirmed_gross_candidate": {
                            "name": (
                                "quoted_half_spread_bps_train_p90_and_"
                                "recent_trade_count_30s_train_p10"
                            ),
                            "train_edge_before_fees_bps": 0.63,
                            "holdout_edge_before_fees_bps": 1.272,
                            "min_train_holdout_gross_bps": 0.63,
                        },
                    },
                    "failure_summary": {
                        "sample_starved_current_fee_holdout_count": 2,
                        "sample_gated_holdout_gross_count": 8,
                        "train_confirmed_gross_count": 4,
                        "best_sample_starved_current_fee_holdout_candidate": {
                            "name": "quoted_half_spread_bps_train_p90_and_n1_spike",
                            "holdout_edge_before_fees_bps": 7.4,
                            "holdout_n_fill_only": 1,
                        },
                        "best_sample_gated_holdout_gross_candidate": {
                            "name": "quoted_half_spread_bps_train_p75_sample_gated",
                            "holdout_edge_before_fees_bps": 1.91,
                            "holdout_n_fill_only": 120,
                        },
                    },
                },
                "history_scorecard": {
                    "status": "HISTORY_INSUFFICIENT_WINDOWS",
                    "reason": "below_min_windows_or_dates",
                    "valid_windows": 3,
                    "distinct_window_dates": ["2026-06-20"],
                    "lower_fee_break_even_windows": 3,
                    "lower_fee_break_even_distinct_window_dates": ["2026-06-20"],
                    "repeated_lower_fee_break_even_keys": [],
                    "best_lower_fee_break_even_window": {
                        "break_even_maker_fee_bps_per_side": 1.135,
                        "cell": {
                            "key": "edge_scorecard|per_symbol_primary_queue|LABUSDT|back|informed_skip|fill_only",
                            "symbol": "LABUSDT",
                            "policy": "informed_skip",
                        },
                    },
                    "lower_fee_break_even_stability": {
                        "status": "LOWER_FEE_BREAK_EVEN_ROTATES_OR_DATE_INSUFFICIENT",
                        "reason": "distinct_dates_below_min_and_no_repeated_key",
                        "lower_fee_break_even_windows": 3,
                        "distinct_window_dates": ["2026-06-20"],
                        "repeated_key_count": 0,
                        "best_lower_fee_break_even_window": {
                            "break_even_maker_fee_bps_per_side": 1.135,
                            "cell": {"symbol": "LABUSDT", "policy": "informed_skip"},
                        },
                    },
                    "low_friction_near_miss_stability": {
                        "status": (
                            "LOW_FRICTION_NEAR_MISS_REPEATS_BUT_DATE_INSUFFICIENT"
                        ),
                        "reason": "repeated_key_but_distinct_dates_below_min",
                        "sample_gated_near_miss_windows": 3,
                        "repeated_key_count": 1,
                        "best_repeated_near_miss_key": {
                            "key": (
                                "low_friction_signal_scorecard_holdout_near_miss|"
                                "quoted_half_spread_bps_train_p75_sample_gated"
                            ),
                            "windows": 2,
                        },
                    },
                    "low_friction_near_miss_motif_stability": {
                        "status": (
                            "LOW_FRICTION_NEAR_MISS_MOTIF_REPEATS_BUT_DATE_INSUFFICIENT"
                        ),
                        "reason": "repeated_motif_but_distinct_dates_below_min",
                        "repeated_motif_count": 1,
                        "best_repeated_near_miss_motif": {
                            "motif_key": (
                                "low_friction_motif|spread_combo|recent_trade_imbalance"
                            ),
                            "windows": 3,
                            "distinct_window_dates": ["2026-06-20"],
                        },
                    },
                },
                "fee_path_feasibility": {
                    "status": "STANDARD_VIP_TIER_CAN_CLEAR_BUT_SCALE_OR_CAPITAL_GATED",
                    "break_even_maker_fee_bps_per_side": 1.135,
                    "fee_reduction_needed_bps_per_side": 0.865,
                    "first_standard_vip_tier_clearing_break_even": {"tier": "VIP5"},
                    "business_path_actionability": {
                        "status": "STANDARD_FEE_TIER_CLEARS_BUT_SCALE_OR_CAPITAL_GATED",
                        "first_clearing_tier": "VIP5",
                        "volume_gap_usd": 249_131_074.44,
                        "volume_multiplier_needed": 287.712,
                        "asset_gap_usd": 2_000_000.0,
                        "operator_action_required": (
                            "do_not_treat_lower_fee_case_as_actionable_at_current_scale"
                        ),
                    },
                },
                "mm_motif_amplification_packet": {
                    "status": (
                        "MM_MOTIF_AMPLIFICATION_REQUIRES_DISTINCT_DATE_HISTORY"
                    ),
                    "next_action": (
                        "accumulate_distinct_window_history_for_repeated_low_friction_motif"
                    ),
                    "summary": {
                        "top_motif_key": (
                            "low_friction_motif|spread_combo|recent_trade_imbalance"
                        ),
                        "top_status": "MOTIF_REPEATS_DISTINCT_DATES_INSUFFICIENT",
                        "top_bottleneck_leg": "train",
                        "top_min_train_holdout_gross_bps": 1.032,
                        "top_min_gross_gap_to_current_fee_bps": 2.968,
                        "top_required_uplift_multiple": 3.876,
                        "top_distinct_dates_remaining": 2,
                        "top_frontier_candidate_count": 2,
                        "top_frontier_best_min_gross_key": "frontier-mm-search",
                        "top_frontier_best_min_train_holdout_gross_bps": 1.2,
                        "top_frontier_gap_to_current_fee_bps": 2.8,
                        "top_frontier_experiment_focus": (
                            "lift_train_gross_edge_without_destroying_holdout_sample_gate"
                        ),
                    },
                    "top_candidate": {
                        "search_constraint": (
                            "preserve_repeated_motif_axes_and_require_train_holdout_"
                            "sample_gated_min_gross_ge_current_fee_round_trip"
                        ),
                    },
                },
            },
        },
        {
            "arm_id": "flash_dip_l1_short_exit_replay",
            "gate_status": "CAPTURING",
            "sample_count": 0,
            "artifacts_ready": False,
            "source_ok": True,
            "detail": {
                "fail_reasons": ["no_l1_rows_for_candidate_event_windows"],
                "candidate_events": 6,
                "events_missing_l1_in_event_window": 6,
                "dominant_missing_event_window_l1_relation": (
                    "candidate_window_before_symbol_l1_range"
                ),
            },
        },
        {
            "arm_id": "vol_event_order_flow",
            "gate_status": "NO_EDGE_SURVIVES",
            "sample_count": 6,
            "artifacts_ready": False,
            "source_ok": True,
        },
        {
            "arm_id": "aeg_robustness_matrix",
            "gate_status": "WAIT",
            "sample_count": 0,
            "artifacts_ready": False,
            "source_ok": True,
        },
    ], now_utc=dt.datetime(2026, 6, 20, 16, 55, tzinfo=dt.timezone.utc))

    scorecard = plan["profitability_blocker_scorecard"]
    assert scorecard["status"] == "NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED"
    assert scorecard["blocker_counts"] == {
        "cost_wall": 1,
        "sample_gate": 1,
        "data_coverage": 1,
        "event_wait": 1,
        "robustness_wait": 1,
        "rejected_no_edge": 1,
    }
    blockers = {row["arm_id"]: row for row in scorecard["arms"]}
    assert blockers["mm_verdict_maker_edge"]["blocker_class"] == "cost_wall"
    assert blockers["mm_verdict_maker_edge"]["primary_blocker"] == (
        "gross_edge_below_current_fee_no_current_fee_walk_forward_positive"
    )
    assert blockers["mm_verdict_maker_edge"]["best_sample_gated_gross_edge_bps"] == 2.27
    assert blockers["mm_verdict_maker_edge"]["best_gross_cell_net_bps"] == -1.73
    assert blockers["mm_verdict_maker_edge"]["cost_wall_escape_status"] == (
        "CURRENT_FEE_GROSS_EDGE_GAP_REQUIRES_NEW_LOW_FRICTION_SIGNAL"
    )
    assert blockers["mm_verdict_maker_edge"]["required_current_fee_gross_edge_bps"] == 4.0
    assert blockers["mm_verdict_maker_edge"]["gross_edge_gap_to_current_fee_bps"] == 1.73
    assert blockers["mm_verdict_maker_edge"]["gross_edge_multiple_to_clear_current_fee"] == 1.7621
    assert blockers["mm_verdict_maker_edge"]["next_trigger"] == (
        "search_train_confirmed_low_friction_mm_signal_with_sample_gated_gross_edge_ge_current_fee_round_trip"
    )
    assert blockers["mm_verdict_maker_edge"]["cost_wall_escape_scorecard"][
        "top_sample_gated_gross_cells"
    ][0]["symbol"] == "LABUSDT"
    assert blockers["mm_verdict_maker_edge"]["cost_wall_escape_scorecard"][
        "schema_version"
    ] == "mm_cost_wall_escape_v2"
    directive = blockers["mm_verdict_maker_edge"]["mm_signal_search_directive"]
    assert directive["schema_version"] == "mm_signal_search_directive_v1"
    assert directive["status"] == "SEARCH_REQUIRED_EDGE_UPLIFT"
    assert directive["failure_mode"] == (
        "current_fee_cost_wall_low_friction_holdout_not_train_confirmed_"
        "lower_fee_path_scale_or_capital_gated"
    )
    assert directive["status_reason"] == (
        "holdout_gross_positive_but_train_gross_non_positive"
    )
    assert directive["sample_starved_current_fee_holdout_count"] == 2
    assert (
        directive["best_sample_starved_current_fee_holdout_candidate"]["name"]
        == "quoted_half_spread_bps_train_p90_and_n1_spike"
    )
    assert directive["sample_gated_holdout_gross_count"] == 8
    assert directive["history_low_friction_near_miss_stability_status"] == (
        "LOW_FRICTION_NEAR_MISS_REPEATS_BUT_DATE_INSUFFICIENT"
    )
    assert directive["history_low_friction_near_miss_repeated_key_count"] == 1
    assert directive["history_low_friction_near_miss_motif_stability_status"] == (
        "LOW_FRICTION_NEAR_MISS_MOTIF_REPEATS_BUT_DATE_INSUFFICIENT"
    )
    assert directive["history_low_friction_near_miss_repeated_motif_count"] == 1
    assert directive["history_guided_search_constraint"] == (
        "prioritize_repeated_low_friction_near_miss_motif_then_require_"
        "distinct_date_train_holdout_confirmation"
    )
    assert directive["recommended_search_constraint"] == (
        "require_train_and_holdout_sample_gated_min_gross_ge_current_fee_round_trip"
    )
    assert directive["best_sample_gated_required_uplift_multiple"] == 1.7621
    assert (
        directive["low_friction_train_confirmed_required_uplift_multiple"]
        == 6.3492
    )
    assert directive["stable_candidate_shape_name"] == (
        "quoted_half_spread_bps_train_p90_and_recent_trade_count_30s_train_p10"
    )
    assert directive["lower_fee_path_not_actionable_now"] is True
    assert directive["motif_amplification_top_frontier_candidate_count"] == 2
    assert directive["motif_amplification_top_frontier_best_min_gross_key"] == (
        "frontier-mm-search"
    )
    assert directive["motif_amplification_top_frontier_gap_to_current_fee_bps"] == 2.8
    assert blockers["mm_verdict_maker_edge"]["mm_signal_search_status"] == (
        "SEARCH_REQUIRED_EDGE_UPLIFT"
    )
    assert blockers["mm_verdict_maker_edge"]["failure_mode"] == (
        "current_fee_cost_wall_low_friction_holdout_not_train_confirmed_"
        "lower_fee_path_scale_or_capital_gated"
    )
    assert blockers["mm_verdict_maker_edge"]["status_reason"] == (
        "holdout_gross_positive_but_train_gross_non_positive"
    )
    assert blockers["mm_verdict_maker_edge"][
        "mm_signal_search_required_gross_uplift_multiple"
    ] == 1.7621
    assert blockers["mm_verdict_maker_edge"][
        "mm_signal_search_sample_starved_current_fee_holdout_count"
    ] == 2
    assert blockers["mm_verdict_maker_edge"][
        "mm_signal_search_history_low_friction_near_miss_motif_stability_status"
    ] == "LOW_FRICTION_NEAR_MISS_MOTIF_REPEATS_BUT_DATE_INSUFFICIENT"
    assert blockers["mm_verdict_maker_edge"][
        "mm_signal_search_history_low_friction_near_miss_repeated_motif_count"
    ] == 1
    assert blockers["mm_verdict_maker_edge"][
        "mm_signal_search_history_guided_next_action"
    ] == (
        "accumulate_distinct_window_history_for_repeated_low_friction_motif_"
        "and_search_edge_uplift"
    )
    assert blockers["mm_verdict_maker_edge"][
        "mm_signal_search_motif_amplification_top_frontier_candidate_count"
    ] == 2
    assert blockers["mm_verdict_maker_edge"][
        "mm_signal_search_motif_amplification_top_frontier_best_min_gross_key"
    ] == "frontier-mm-search"
    assert blockers["mm_verdict_maker_edge"]["cost_wall_escape_scorecard"][
        "low_friction_signal_status"
    ] == "LOW_FRICTION_SIGNAL_HOLDOUT_GROSS_POSITIVE_BELOW_CURRENT_FEE"
    assert blockers["mm_verdict_maker_edge"]["cost_wall_escape_scorecard"][
        "history_low_friction_near_miss_motif_stability_status"
    ] == "LOW_FRICTION_NEAR_MISS_MOTIF_REPEATS_BUT_DATE_INSUFFICIENT"
    assert blockers["mm_verdict_maker_edge"]["low_friction_gross_stability_status"] == (
        "LOW_FRICTION_HOLDOUT_GROSS_NOT_TRAIN_CONFIRMED"
    )
    assert blockers["mm_verdict_maker_edge"]["low_friction_gross_stability_reason"] == (
        "holdout_gross_positive_but_train_gross_non_positive"
    )
    assert blockers["mm_verdict_maker_edge"]["low_friction_train_gross_edge_bps"] == -0.225
    assert blockers["mm_verdict_maker_edge"]["low_friction_holdout_gross_edge_bps"] == 1.91
    assert blockers["mm_verdict_maker_edge"][
        "low_friction_holdout_minus_train_gross_bps"
    ] == 2.135
    assert blockers["mm_verdict_maker_edge"][
        "low_friction_train_confirmed_gross_status"
    ] == "LOW_FRICTION_TRAIN_CONFIRMED_GROSS_BELOW_CURRENT_FEE"
    assert blockers["mm_verdict_maker_edge"][
        "low_friction_best_train_confirmed_min_gross_bps"
    ] == 0.63
    assert blockers["mm_verdict_maker_edge"][
        "low_friction_train_confirmed_gap_to_current_fee_bps"
    ] == 3.37
    assert blockers["mm_verdict_maker_edge"]["cost_wall_escape_scorecard"][
        "low_friction_gross_stability_scorecard"
    ]["train_confirms_gross"] is False
    assert blockers["mm_verdict_maker_edge"]["cost_wall_escape_scorecard"][
        "low_friction_best_train_confirmed_min_gross_bps"
    ] == 0.63
    assert blockers["mm_verdict_maker_edge"]["cost_wall_escape_scorecard"][
        "best_low_friction_signal_holdout_gross_candidate"
    ]["holdout"]["source"] == "low_friction_signal_holdout"
    assert blockers["mm_verdict_maker_edge"]["business_path_actionability_status"] == (
        "STANDARD_FEE_TIER_CLEARS_BUT_SCALE_OR_CAPITAL_GATED"
    )
    assert blockers["mm_verdict_maker_edge"]["lower_fee_break_even_stability_status"] == (
        "LOWER_FEE_BREAK_EVEN_ROTATES_OR_DATE_INSUFFICIENT"
    )
    assert blockers["mm_verdict_maker_edge"]["lower_fee_break_even_windows"] == 3
    assert blockers["mm_verdict_maker_edge"]["repeated_lower_fee_break_even_key_count"] == 0
    mm_secondary = blockers["mm_verdict_maker_edge"]["secondary_blockers"]
    assert [row["blocker_class"] for row in mm_secondary] == [
        "cost_wall",
        "cost_wall",
        "cost_wall",
        "fee_or_scale",
        "fee_or_scale",
    ]
    assert mm_secondary[0]["blocker"] == (
        "gross_edge_exists_but_current_fee_exceeds_break_even"
    )
    assert mm_secondary[0]["best_sample_gated_gross_edge_bps"] == 2.27
    assert mm_secondary[1]["blocker"] == (
        "current_maker_fee_exceeds_sample_gated_fill_sim_break_even"
    )
    assert mm_secondary[1]["best_sample_gated_net_bps"] == -1.73
    assert mm_secondary[2]["blocker"] == (
        "live_markout_current_maker_fee_exceeds_best_break_even"
    )
    assert mm_secondary[3]["blocker"] == (
        "lower_fee_break_even_not_stable_across_distinct_windows"
    )
    assert mm_secondary[3]["lower_fee_break_even_stability_status"] == (
        "LOWER_FEE_BREAK_EVEN_ROTATES_OR_DATE_INSUFFICIENT"
    )
    assert mm_secondary[4]["business_path_actionability_status"] == (
        "STANDARD_FEE_TIER_CLEARS_BUT_SCALE_OR_CAPITAL_GATED"
    )
    assert mm_secondary[4]["operator_action_required"] == (
        "do_not_treat_lower_fee_case_as_actionable_at_current_scale"
    )
    assert blockers["polymarket_leadlag_ic"]["sample_gate_eta_utc"] == (
        "2026-06-20T19:52:03+00:00"
    )
    assert blockers["flash_dip_l1_short_exit_replay"]["blocker_class"] == "data_coverage"
    assert blockers["aeg_robustness_matrix"]["candidate_artifact_dependency_status"] == (
        "NO_CANDIDATE_ARTIFACTS_AVAILABLE_FOR_ROBUSTNESS"
    )
    assert blockers["aeg_robustness_matrix"]["engineering_actionable"] is False
    assert blockers["aeg_robustness_matrix"]["next_trigger"] == (
        "wait_for_candidate_or_probe_artifact_before_robustness_matrix"
    )
    assert scorecard["top_blockers"][0]["arm_id"] == "mm_verdict_maker_edge"


def test_aeg_robustness_wait_becomes_actionable_only_with_upstream_candidate_artifact():
    plan = build_discovery_plan([
        {
            "arm_id": "polymarket_leadlag_ic",
            "gate_status": "READY",
            "sample_count": 35,
            "artifacts_ready": True,
            "source_ok": True,
            "detail": {"candidate_count": 1},
        },
        {
            "arm_id": "aeg_robustness_matrix",
            "gate_status": "WAIT",
            "sample_count": 0,
            "artifacts_ready": False,
            "source_ok": True,
        },
    ], now_utc=dt.datetime(2026, 6, 20, 19, 5, tzinfo=dt.timezone.utc))

    blockers = {
        row["arm_id"]: row
        for row in plan["profitability_blocker_scorecard"]["arms"]
    }
    assert blockers["polymarket_leadlag_ic"]["blocker_class"] == "data_coverage"
    assert blockers["polymarket_leadlag_ic"]["primary_blocker"] == (
        "polymarket_candidate_replay_missing"
    )
    assert blockers["polymarket_leadlag_ic"]["promotion_ready"] is False
    aeg = blockers["aeg_robustness_matrix"]
    assert aeg["candidate_artifact_dependency_status"] == (
        "CANDIDATE_ARTIFACTS_AVAILABLE_FOR_ROBUSTNESS"
    )
    assert aeg["candidate_artifact_count"] == 1
    assert aeg["engineering_actionable"] is True
    assert aeg["next_trigger"] == "feed_candidate_artifacts_into_robustness_matrix"


def test_aeg_robustness_excludes_negative_interim_polymarket_candidate():
    candidate_key = "polymarket_leadlag_ic|event_reg|BTCUSDT|15m"
    plan = build_discovery_plan([
        {
            "arm_id": "polymarket_leadlag_ic",
            "gate_status": "READY",
            "sample_count": 257,
            "artifacts_ready": True,
            "source_ok": True,
            "detail": {
                "candidate_count": 1,
                "candidate_key": candidate_key,
                "candidate_replay_status": "PAPER_REPLAY_BUILT",
                "candidate_replay_history_status": "REPLAY_HISTORY_DAYS_INSUFFICIENT",
                "candidate_replay_history_sample_count": 257,
                "candidate_replay_history_n_days": 4,
                "candidate_replay_history_min_days": 30,
                "candidate_replay_history_min_samples": 30,
                "candidate_replay_history_net_bps_mean": -2.28885355,
                "candidate_replay_history_holdout_net_bps_mean": -2.35447585,
                "candidate_replay_history_interim_edge_status": (
                    "INTERIM_NEGATIVE_NET_AND_HOLDOUT"
                ),
                "candidate_replay_history_budget_status": (
                    "EARLY_ROTATE_RECOMMENDED"
                ),
                "candidate_replay_history_recommended_next_action": (
                    "rotate_polymarket_leadlag_candidate_or_change_feature_family_"
                    "before_spending_30d_history_budget"
                ),
                "candidate_replay_history_execution_realism_status": "UNMEASURED",
            },
        },
        {
            "arm_id": "aeg_robustness_matrix",
            "gate_status": "WAIT",
            "sample_count": 0,
            "artifacts_ready": False,
            "source_ok": True,
        },
    ], now_utc=dt.datetime(2026, 6, 20, 19, 5, tzinfo=dt.timezone.utc))

    blockers = {
        row["arm_id"]: row
        for row in plan["profitability_blocker_scorecard"]["arms"]
    }
    assert blockers["polymarket_leadlag_ic"]["blocker_class"] == "rejected_no_edge"
    assert blockers["polymarket_leadlag_ic"]["primary_blocker"] == (
        "polymarket_candidate_replay_history_interim_negative_edge"
    )
    aeg = blockers["aeg_robustness_matrix"]
    assert aeg["candidate_artifact_dependency_status"] == (
        "CANDIDATE_ARTIFACTS_EXCLUDED_BY_INTERIM_EDGE"
    )
    assert aeg["candidate_artifact_count"] == 0
    assert aeg["excluded_candidate_artifact_count"] == 1
    assert aeg["engineering_actionable"] is False
    assert aeg["next_trigger"] == "wait_for_new_candidate_after_reject_or_rotate"
    excluded = aeg["candidate_artifact_dependency"]["excluded_candidate_artifacts"]
    assert excluded[0]["candidate_key"] == candidate_key
    assert excluded[0]["exclusion_reason"] == (
        "candidate_replay_history_interim_negative_edge"
    )


def test_polymarket_ready_candidate_is_downgraded_after_non_durable_aeg_matrix():
    candidate_key = "polymarket_leadlag_ic|price_target|SOLUSDT|15m"
    plan = build_discovery_plan([
        {
            "arm_id": "polymarket_leadlag_ic",
            "gate_status": "READY",
            "sample_count": 30,
            "artifacts_ready": True,
            "source_ok": True,
            "detail": {
                "candidate_count": 1,
                "candidate_key": candidate_key,
                "candidate_replay_status": "PAPER_REPLAY_BUILT",
                "candidate_replay_sample_count": 30,
                "candidate_replay_round_trip_cost_bps": 4.0,
                "candidate_replay_gross_bps_mean": 9.2,
                "candidate_replay_net_bps_mean": 5.2,
                "candidate_replay_holdout_net_bps_mean": 4.4,
                "candidate_replay_cost_wall_status": (
                    "PAPER_REPLAY_NET_POSITIVE_EXECUTION_UNMEASURED"
                ),
                "candidate_replay_execution_realism_status": "UNMEASURED",
                "candidate_replay_history_status": "REPLAY_HISTORY_DAYS_INSUFFICIENT",
                "candidate_replay_history_report_count": 3,
                "candidate_replay_history_matched_report_count": 3,
                "candidate_replay_history_sample_count": 32,
                "candidate_replay_history_n_days": 1,
                "candidate_replay_history_min_days": 30,
                "candidate_replay_history_min_samples": 30,
                "candidate_replay_history_net_bps_mean": 0.77,
                "candidate_replay_history_holdout_net_bps_mean": 6.83,
                "candidate_replay_history_pbo_day_count": 1,
                "candidate_replay_history_execution_realism_status": "UNMEASURED",
            },
        },
        {
            "arm_id": "aeg_robustness_matrix",
            "gate_status": "WAIT",
            "sample_count": 3,
            "artifacts_ready": False,
            "source_ok": True,
            "detail": {
                "run_id": "poly_matrix",
                "candidate_id": "polymarket_price_target_SOLUSDT_15m",
                "candidate_key": candidate_key,
                "final_label_counts": {"insufficient evidence": 3},
                "durable_candidate_rows": 0,
                "coverage_gate_status": "FAIL",
                "execution_realism_mode": "unverified_missing_missing",
            },
        },
    ], now_utc=dt.datetime(2026, 6, 20, 20, 5, tzinfo=dt.timezone.utc))

    scorecard = plan["profitability_blocker_scorecard"]
    blockers = {row["arm_id"]: row for row in scorecard["arms"]}
    assert scorecard["promotion_ready_count"] == 0
    assert scorecard["status"] == "NO_ACTIONABLE_ALPHA_WAIT_OR_SAMPLE_GATED"
    assert blockers["polymarket_leadlag_ic"]["blocker_class"] == "robustness_wait"
    assert blockers["polymarket_leadlag_ic"]["promotion_ready"] is False
    assert blockers["polymarket_leadlag_ic"]["primary_blocker"] == (
        "aeg_matrix_review_no_durable_candidate_rows"
    )
    assert blockers["polymarket_leadlag_ic"]["aeg_matrix_run_id"] == "poly_matrix"
    assert blockers["polymarket_leadlag_ic"]["candidate_replay_sample_count"] == 30
    assert blockers["polymarket_leadlag_ic"]["candidate_replay_net_bps_mean"] == 5.2
    assert blockers["polymarket_leadlag_ic"]["candidate_replay_cost_wall_status"] == (
        "PAPER_REPLAY_NET_POSITIVE_EXECUTION_UNMEASURED"
    )
    assert blockers["polymarket_leadlag_ic"]["candidate_replay_execution_realism_status"] == (
        "UNMEASURED"
    )
    assert blockers["polymarket_leadlag_ic"]["candidate_replay_history_status"] == (
        "REPLAY_HISTORY_DAYS_INSUFFICIENT"
    )
    assert blockers["polymarket_leadlag_ic"]["candidate_replay_history_n_days"] == 1
    assert blockers["polymarket_leadlag_ic"]["candidate_replay_history_min_days"] == 30
    assert blockers["polymarket_leadlag_ic"]["candidate_replay_history_pbo_day_count"] == 1
    assert blockers["polymarket_leadlag_ic"][
        "candidate_replay_history_execution_realism_status"
    ] == "UNMEASURED"
    assert blockers["aeg_robustness_matrix"]["candidate_artifact_dependency_status"] == (
        "CANDIDATE_ARTIFACTS_ALREADY_REVIEWED_NO_DURABLE_ROWS"
    )
    assert blockers["aeg_robustness_matrix"]["candidate_artifact_count"] == 0
    assert blockers["aeg_robustness_matrix"]["candidate_artifact_dependency"][
        "already_reviewed_candidate_artifact_count"
    ] == 1


def test_polymarket_ready_candidate_requires_replay_history_before_promotion_ready():
    plan = build_discovery_plan([
        {
            "arm_id": "polymarket_leadlag_ic",
            "gate_status": "READY",
            "sample_count": 35,
            "artifacts_ready": True,
            "source_ok": True,
            "detail": {
                "candidate_count": 1,
                "candidate_key": "polymarket_leadlag_ic|price_target|SOLUSDT|15m",
                "candidate_replay_status": "PAPER_REPLAY_BUILT",
                "candidate_replay_sample_count": 35,
                "candidate_replay_net_bps_mean": 5.2,
                "candidate_replay_holdout_net_bps_mean": 4.4,
                "candidate_replay_cost_wall_status": (
                    "PAPER_REPLAY_NET_POSITIVE_EXECUTION_UNMEASURED"
                ),
                "candidate_replay_execution_realism_status": "UNMEASURED",
                "candidate_replay_history_status": "REPLAY_HISTORY_DAYS_INSUFFICIENT",
                "candidate_replay_history_report_count": 2,
                "candidate_replay_history_matched_report_count": 2,
                "candidate_replay_history_sample_count": 35,
                "candidate_replay_history_n_days": 2,
                "candidate_replay_history_min_days": 30,
                "candidate_replay_history_min_samples": 30,
                "candidate_replay_history_pbo_day_count": 2,
                "candidate_replay_history_execution_realism_status": "UNMEASURED",
            },
        },
    ], now_utc=dt.datetime(2026, 6, 20, 20, 5, tzinfo=dt.timezone.utc))

    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    assert plan["arms"][0]["action"] == "READY_FOR_AEG_CHAIN"
    assert plan["profitability_blocker_scorecard"]["promotion_ready_count"] == 0
    assert plan["profitability_blocker_scorecard"]["status"] == (
        "NO_ACTIONABLE_ALPHA_WAIT_OR_SAMPLE_GATED"
    )
    assert blocker["blocker_class"] == "sample_gate"
    assert blocker["primary_blocker"] == "polymarket_candidate_replay_history_not_ready"
    assert blocker["candidate_replay_history_status"] == (
        "REPLAY_HISTORY_DAYS_INSUFFICIENT"
    )
    assert blocker["candidate_replay_history_n_days"] == 2
    assert blocker["candidate_replay_history_min_days"] == 30


def test_polymarket_ready_candidate_requires_execution_realism_pass_before_promotion_ready():
    plan = build_discovery_plan([
        {
            "arm_id": "polymarket_leadlag_ic",
            "gate_status": "READY",
            "sample_count": 35,
            "artifacts_ready": True,
            "source_ok": True,
            "detail": {
                "candidate_count": 1,
                "candidate_key": "polymarket_leadlag_ic|price_target|SOLUSDT|15m",
                "candidate_replay_status": "PAPER_REPLAY_BUILT",
                "candidate_replay_history_status": "REPLAY_HISTORY_READY_FOR_AEG_RECHECK",
                "candidate_replay_history_sample_count": 90,
                "candidate_replay_history_n_days": 30,
                "candidate_replay_history_min_days": 30,
                "candidate_replay_history_min_samples": 30,
                "candidate_replay_history_execution_realism_status": "FAIL",
            },
        },
    ], now_utc=dt.datetime(2026, 6, 20, 20, 5, tzinfo=dt.timezone.utc))

    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    assert plan["arms"][0]["action"] == "READY_FOR_AEG_CHAIN"
    assert plan["profitability_blocker_scorecard"]["promotion_ready_count"] == 0
    assert blocker["blocker_class"] == "robustness_wait"
    assert blocker["primary_blocker"] == "polymarket_execution_realism_not_passed"
    assert blocker["next_trigger"] == (
        "fix_or_reject_polymarket_execution_realism_before_promotion"
    )
    assert blocker["promotion_ready"] is False


def test_polymarket_ready_candidate_can_be_promotion_ready_after_replay_history_and_execution_pass():
    plan = build_discovery_plan([
        {
            "arm_id": "polymarket_leadlag_ic",
            "gate_status": "READY",
            "sample_count": 35,
            "artifacts_ready": True,
            "source_ok": True,
            "detail": {
                "candidate_count": 1,
                "candidate_key": "polymarket_leadlag_ic|price_target|SOLUSDT|15m",
                "candidate_replay_status": "PAPER_REPLAY_BUILT",
                "candidate_replay_history_status": "REPLAY_HISTORY_READY_FOR_AEG_RECHECK",
                "candidate_replay_history_sample_count": 90,
                "candidate_replay_history_n_days": 30,
                "candidate_replay_history_min_days": 30,
                "candidate_replay_history_min_samples": 30,
                "candidate_replay_history_execution_realism_status": "PASS",
            },
        },
    ], now_utc=dt.datetime(2026, 6, 20, 20, 5, tzinfo=dt.timezone.utc))

    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    assert plan["profitability_blocker_scorecard"]["promotion_ready_count"] == 1
    assert plan["profitability_blocker_scorecard"]["status"] == (
        "ACTIONABLE_ALPHA_REVIEW_READY"
    )
    assert blocker["blocker_class"] == "candidate_review_ready"
    assert blocker["primary_blocker"] == "candidate_artifacts_ready_need_aeg_chain"
    assert blocker["promotion_ready"] is True


def test_mm_no_train_positive_without_gross_decomposition_stays_feature_family():
    plan = build_discovery_plan([
        {
            "arm_id": "mm_verdict_maker_edge",
            "gate_status": "CAPTURING",
            "sample_count": 31,
            "artifacts_ready": False,
            "source_ok": True,
            "detail": {
                "walk_forward_failure_summary": {
                    "status": "NO_TRAIN_POSITIVE_CELL",
                    "candidate_count": 51,
                    "best_train_candidate": {"name": "quoted_half_spread_bps_train_p75_ge"},
                },
                "sample_gated_cost_wall_summary": {
                    "available": True,
                    "status": "SAMPLE_GATED_CURRENT_FEE_COST_WALL",
                    "best_sample_gated_net_bps": -1.73,
                    "best_sample_gated_fee_round_trip_shortfall_bps": 1.73,
                    "break_even_maker_fee_bps_per_side": 1.135,
                    "fee_reduction_needed_bps_per_side": 0.865,
                },
                "low_friction_signal_scorecard": {
                    "failure_summary": {
                        "sample_starved_current_fee_holdout_count": 0,
                        "sample_gated_holdout_gross_count": 208,
                        "train_confirmed_gross_count": 70,
                        "best_sample_gated_holdout_gross_candidate": {
                            "name": "sample_gated_below_fee",
                            "holdout_edge_before_fees_bps": 1.167,
                            "holdout_n_fill_only": 314,
                        },
                    },
                    "train_confirmed_gross_scorecard": {
                        "status": "LOW_FRICTION_TRAIN_CONFIRMED_GROSS_BELOW_CURRENT_FEE",
                        "best_min_train_holdout_gross_bps": 0.607,
                        "gap_to_current_fee_round_trip_bps": 3.393,
                    },
                },
            },
        },
    ], now_utc=dt.datetime(2026, 6, 20, 17, 10, tzinfo=dt.timezone.utc))

    row = plan["profitability_blocker_scorecard"]["arms"][0]
    assert row["blocker_class"] == "feature_family_no_edge"
    assert row["primary_blocker"] == "no_train_positive_walk_forward_feature_cell"
    assert row["secondary_blockers"][0]["blocker"] == (
        "current_maker_fee_exceeds_sample_gated_fill_sim_break_even"
    )
    assert row["mm_signal_search_status"] == "SEARCH_BLOCKED_MISSING_COST_INPUTS"
    assert (
        row["mm_signal_search_failure_mode"]
        == "missing_current_fee_or_best_sample_gated_gross_edge"
    )
    assert row["mm_signal_search_sample_starved_current_fee_holdout_count"] == 0
    assert row["mm_signal_search_sample_gated_holdout_gross_count"] == 208
    assert (
        row["mm_signal_search_best_sample_gated_holdout_gross_candidate"]["name"]
        == "sample_gated_below_fee"
    )


def test_mm_holdout_only_current_fee_positive_is_not_review_ready():
    plan = build_discovery_plan([
        {
            "arm_id": "mm_verdict_maker_edge",
            "gate_status": "CAPTURING",
            "sample_count": 31,
            "artifacts_ready": False,
            "source_ok": True,
            "detail": {
                "walk_forward_failure_summary": {
                    "status": "NO_TRAIN_POSITIVE_CELL",
                    "candidate_count": 51,
                    "best_train_candidate": {"name": "symbol=ADAUSDT"},
                },
                "sample_gated_cost_wall_summary": {
                    "available": True,
                    "status": "SAMPLE_GATED_CURRENT_FEE_COST_WALL",
                    "best_sample_gated_net_bps": -2.133,
                    "best_sample_gated_fee_round_trip_shortfall_bps": 2.133,
                    "break_even_maker_fee_bps_per_side": 2.934,
                    "fee_reduction_needed_bps_per_side": 0.0,
                },
                "gross_edge_cost_decomposition": {
                    "available": True,
                    "status": "CURRENT_FEE_GROSS_AND_NET_POSITIVE",
                    "current_fee_round_trip_bps": 4.0,
                    "current_fee_positive_sample_gated_cell_count": 1,
                    "best_sample_gated_current_fee_cell": {
                        "source": "low_friction_signal_holdout",
                        "name": (
                            "quoted_half_spread_bps_train_p90_and_"
                            "side_touch_size_delta_frac_30s_train_p90"
                        ),
                        "edge_before_fees_bps": 5.868,
                        "net_bps": 1.868,
                        "n_fill_only": 43,
                    },
                    "best_low_friction_signal_holdout_gross_candidate": {
                        "name": (
                            "quoted_half_spread_bps_train_p90_and_"
                            "side_touch_size_delta_frac_30s_train_p90"
                        ),
                        "train": {
                            "source": "low_friction_signal_train",
                            "n_fill_only": 90,
                            "edge_before_fees_bps": -0.336,
                            "net_bps": -4.336,
                            "sample_gated": True,
                        },
                        "holdout": {
                            "source": "low_friction_signal_holdout",
                            "n_fill_only": 43,
                            "edge_before_fees_bps": 5.868,
                            "net_bps": 1.868,
                            "sample_gated": True,
                        },
                    },
                },
                "low_friction_signal_scorecard": {
                    "status": "LOW_FRICTION_SIGNAL_HOLDOUT_GROSS_POSITIVE_BELOW_CURRENT_FEE",
                    "train_confirmed_gross_scorecard": {
                        "status": "LOW_FRICTION_TRAIN_CONFIRMED_GROSS_BELOW_CURRENT_FEE",
                        "train_confirmed_positive_gross_count": 44,
                        "current_fee_confirmed_count": 0,
                        "best_min_train_holdout_gross_bps": 1.402,
                        "gap_to_current_fee_round_trip_bps": 2.598,
                    },
                },
            },
        },
    ], now_utc=dt.datetime(2026, 6, 20, 21, 20, tzinfo=dt.timezone.utc))

    row = plan["profitability_blocker_scorecard"]["arms"][0]
    assert row["blocker_class"] == "feature_family_no_edge"
    assert row["primary_blocker"] == "low_friction_current_fee_holdout_not_train_confirmed"
    assert row["cost_wall_escape_status"] == "CURRENT_FEE_HOLDOUT_GROSS_NOT_TRAIN_CONFIRMED"
    assert row["mm_signal_search_status"] == "SEARCH_REQUIRED_TRAIN_CONFIRMATION"
    assert row["mm_signal_search_failure_mode"] == (
        "holdout_current_fee_candidate_not_train_confirmed"
    )
    assert row["mm_signal_search_required_gross_uplift_multiple"] is None
    assert row["best_sample_gated_current_fee_source"] == "low_friction_signal_holdout"
    assert row["low_friction_train_confirmed_current_fee_count"] == 0
    assert row["low_friction_best_train_confirmed_min_gross_bps"] == 1.402
    assert row["low_friction_train_confirmed_gap_to_current_fee_bps"] == 2.598
    assert row["next_trigger"] == (
        "search_train_confirmed_low_friction_mm_signal_with_sample_gated_gross_edge_ge_current_fee_round_trip"
    )


def test_mm_train_only_current_fee_positive_requires_walk_forward_confirmation():
    plan = build_discovery_plan([
        {
            "arm_id": "mm_verdict_maker_edge",
            "gate_status": "CAPTURING",
            "sample_count": 16,
            "artifacts_ready": False,
            "source_ok": True,
            "detail": {
                "walk_forward_failure_summary": {
                    "status": "NO_TRAIN_POSITIVE_CELL",
                    "candidate_count": 51,
                    "best_train_candidate": {"name": "symbol=ADAUSDT"},
                    "best_holdout_candidate": {"name": "symbol=ADAUSDT"},
                },
                "gross_edge_cost_decomposition": {
                    "available": True,
                    "status": "CURRENT_FEE_GROSS_AND_NET_POSITIVE",
                    "current_fee_round_trip_bps": 4.0,
                    "current_fee_positive_sample_gated_cell_count": 1,
                    "best_sample_gated_gross_edge_bps": 4.042,
                    "best_gross_cell_net_bps": 0.042,
                    "best_sample_gated_current_fee_cell": {
                        "source": "low_friction_signal_train",
                        "name": "quoted_half_spread_bps_train_p75_and_recent_l1_update_count_30s_train_p10",
                        "edge_before_fees_bps": 4.042,
                        "net_bps": 0.042,
                        "n_fill_only": 40,
                    },
                    "best_low_friction_signal_holdout_gross_candidate": {
                        "name": "quoted_half_spread_bps_train_p75_and_recent_trade_count_10s_train_p10",
                        "train": {
                            "source": "low_friction_signal_train",
                            "n_fill_only": 34,
                            "edge_before_fees_bps": 2.138,
                            "net_bps": -1.862,
                            "sample_gated": True,
                        },
                        "holdout": {
                            "source": "low_friction_signal_holdout",
                            "n_fill_only": 90,
                            "edge_before_fees_bps": 0.139,
                            "net_bps": -3.861,
                            "sample_gated": True,
                        },
                    },
                },
                "sample_gated_cost_wall_summary": {
                    "current_fee_round_trip_bps": 4.0,
                },
                "low_friction_signal_scorecard": {
                    "failure_summary": {
                        "sample_starved_current_fee_holdout_count": 0,
                        "sample_gated_holdout_gross_count": 208,
                        "train_confirmed_gross_count": 70,
                        "best_sample_gated_holdout_gross_candidate": {
                            "name": "sample_gated_below_fee",
                            "holdout_edge_before_fees_bps": 1.167,
                            "holdout_n_fill_only": 314,
                        },
                    },
                    "train_confirmed_gross_scorecard": {
                        "status": "LOW_FRICTION_TRAIN_CONFIRMED_GROSS_BELOW_CURRENT_FEE",
                        "best_min_train_holdout_gross_bps": 0.607,
                        "gap_to_current_fee_round_trip_bps": 3.393,
                    },
                },
            },
        },
    ], now_utc=dt.datetime(2026, 6, 23, 15, 40, tzinfo=dt.timezone.utc))

    row = plan["profitability_blocker_scorecard"]["arms"][0]
    assert row["blocker_class"] == "current_fee_confirmation"
    assert row["primary_blocker"] == (
        "current_fee_candidate_lacks_train_holdout_walk_forward_confirmation"
    )
    assert row["next_trigger"] == (
        "review_current_fee_positive_mm_cell_with_walk_forward_and_aeg_chain"
    )
    assert row["cost_wall_escape_status"] == "CURRENT_FEE_SAMPLE_GATED_CELL_AVAILABLE"
    assert row["current_fee_positive_sample_gated_cell_count"] == 1
    assert row["best_sample_gated_current_fee_cell"]["edge_before_fees_bps"] == 4.042
    assert row["best_sample_gated_current_fee_source"] == "low_friction_signal_train"
    assert row["mm_signal_search_status"] == "SEARCH_REQUIRED_WALK_FORWARD_CONFIRMATION"
    assert row["mm_signal_search_failure_mode"] == (
        "current_fee_candidate_lacks_train_holdout_walk_forward_confirmation"
    )
    assert row["failure_mode"] == (
        "current_fee_candidate_lacks_train_holdout_walk_forward_confirmation"
    )
    assert row["status_reason"] == (
        "train_and_holdout_gross_positive_but_at_least_one_half_below_current_fee"
    )
    assert row["mm_signal_search_sample_starved_current_fee_holdout_count"] == 0
    assert row["mm_signal_search_sample_gated_holdout_gross_count"] == 208
    assert row["mm_signal_search_required_gross_uplift_multiple"] is None


def test_mm_blocker_prefers_sample_gated_cost_wall_over_live_markout():
    plan = build_discovery_plan([
        {
            "arm_id": "mm_verdict_maker_edge",
            "gate_status": "CAPTURING",
            "sample_count": 40,
            "artifacts_ready": False,
            "source_ok": True,
            "detail": {
                "cost_wall_summary": {
                    "available": True,
                    "best_symbol_by_net_edge": "ARBUSDT",
                    "best_fee_round_trip_shortfall_bps": 0.0357,
                    "best_n_maker_fills": 1,
                },
                "sample_gated_cost_wall_summary": {
                    "available": True,
                    "status": "SAMPLE_GATED_CURRENT_FEE_COST_WALL",
                    "best_sample_gated_net_bps": -1.73,
                    "best_sample_gated_fee_round_trip_shortfall_bps": 1.73,
                    "break_even_maker_fee_bps_per_side": 1.135,
                    "fee_reduction_needed_bps_per_side": 0.865,
                    "sample_gated_cell_count": 41,
                },
            },
        },
    ], now_utc=dt.datetime(2026, 6, 20, 17, 30, tzinfo=dt.timezone.utc))

    row = plan["profitability_blocker_scorecard"]["arms"][0]
    assert row["blocker_class"] == "cost_wall"
    assert row["primary_blocker"] == (
        "current_fee_round_trip_exceeds_sample_gated_fill_sim_break_even"
    )
    assert row["best_sample_gated_fee_round_trip_shortfall_bps"] == 1.73
    assert row["sample_gated_cell_count"] == 41
    assert row["secondary_blockers"][1]["best_n_maker_fills"] == 1


def test_runtime_runner_writes_artifact_only_killboard(tmp_path):
    data = tmp_path / "openclaw"
    (data / "gate_b_watch").mkdir(parents=True)
    (data / "gate_b_watch" / "gate_b_watch_latest.json").write_text(json.dumps({
        "generated_at_utc": "2026-06-19T00:00:00+00:00",
        "status": "WATCH_ONLY",
        "candidate_counts": {"total": 21, "alertable": 0, "start_now": 0, "schedule": 0},
        "alerts_sent": 0,
    }), encoding="utf-8")

    (data / "logs").mkdir(parents=True)
    (data / "logs" / "flash_dip_death_rate.log").write_text(json.dumps({
        "ts_utc": "2026-06-19T00:00:00Z",
        "thresholds": {"min_n": 20},
        "n_closed_slots": 0,
        "n_deaths": 0,
        "death_rate_pct": None,
        "actionable": False,
        "alerted": False,
    }) + "\n", encoding="utf-8")
    (data / "logs" / "recorder_mm_verdict.log").write_text(json.dumps({
        "ts_utc": "2026-06-19T00:00:00Z",
        "thresholds": {"min_maker_fills": 30},
        "markout_n_total": 31,
        "adverse_selection_usable": True,
        "cost_wall_summary": {
            "available": True,
            "best_symbol_by_net_edge": "BTCUSDT",
            "best_fee_round_trip_shortfall_bps": -1.25,
        },
        "sample_gated_cost_wall_summary": {
            "available": True,
            "status": "SAMPLE_GATED_CURRENT_FEE_POSITIVE",
            "best_sample_gated_net_bps": 0.25,
            "best_sample_gated_fee_round_trip_shortfall_bps": -0.25,
        },
        "gross_edge_cost_decomposition": {
            "available": True,
            "status": "CURRENT_FEE_GROSS_AND_NET_POSITIVE",
            "best_sample_gated_gross_edge_bps": 4.25,
            "best_gross_cell_net_bps": 0.25,
        },
        "fee_path_feasibility": {
            "status": "CURRENT_ACCOUNT_FEE_CLEARS_BREAK_EVEN",
            "break_even_maker_fee_bps_per_side": 2.2,
            "fee_reduction_needed_bps_per_side": 0.0,
        },
        "fillsim": {
            "history_scorecard": {
                "status": "HISTORY_LOWER_FEE_ONLY",
                "lower_fee_break_even_stability": {
                    "status": "LOWER_FEE_BREAK_EVEN_REPEATS_ACROSS_WINDOWS",
                    "lower_fee_break_even_windows": 3,
                    "repeated_key_count": 1,
                },
            },
            "walk_forward_feature_scorecard": {
                "failure_summary": {
                    "status": "TRAIN_POSITIVE_HOLDOUT_DECAY",
                    "best_train_candidate": {
                        "name": "quoted_half_spread_bps_train_p75_ge",
                        "train_net_bps": 1.2,
                        "holdout_net_bps": -3.4,
                    },
                    "holdout_confirmed_count": 0,
                }
            }
        },
        "net_edge_per_symbol": {
            "BTCUSDT": {"net_edge_bps": 1.25, "n_maker_fills": 31},
        },
    }) + "\n", encoding="utf-8")
    (data / "research" / "fillsim").mkdir(parents=True)
    (data / "research" / "fillsim" / "fillsim_history_scorecard.json").write_text(
        json.dumps({
            "status": "HISTORY_LOWER_FEE_ONLY",
            "lower_fee_break_even_stability": {
                "status": "LOWER_FEE_BREAK_EVEN_REPEATS_ACROSS_WINDOWS",
                "lower_fee_break_even_windows": 3,
                "repeated_key_count": 1,
            },
            "low_friction_near_miss_stability": {
                "status": "LOW_FRICTION_NEAR_MISS_REPEATS_BUT_DATE_INSUFFICIENT",
                "repeated_key_count": 1,
            },
            "low_friction_near_miss_motif_stability": {
                "status": (
                    "LOW_FRICTION_NEAR_MISS_MOTIF_REPEATS_BUT_DATE_INSUFFICIENT"
                ),
                "repeated_motif_count": 1,
                "best_repeated_near_miss_motif": {
                    "motif_key": "low_friction_motif|spread_combo",
                    "frontier_summary": {
                        "candidate_count": 1,
                        "best_min_gross_key": "frontier-runtime",
                        "best_min_train_holdout_gross_bps": 1.1,
                        "best_min_gross_gap_to_current_fee_bps": 2.9,
                        "best_train_key": "frontier-runtime",
                        "best_train_gross_bps": 1.1,
                        "best_holdout_key": "frontier-runtime",
                        "best_holdout_gross_bps": 2.5,
                    },
                    "candidate_frontier": [{
                        "key": "frontier-runtime",
                        "min_train_holdout_gross_bps": 1.1,
                    }],
                },
            },
        }),
        encoding="utf-8",
    )

    (data / "order_flow_alpha").mkdir(parents=True)
    (data / "order_flow_alpha" / "vol_event_ledger.json").write_text(json.dumps({
        "version": 1,
        "milestones": {"ruling_3plus_fired": True},
        "events": {
            f"e{i}": {
                "direction": "upside_squeeze" if i == 0 else "downside",
                "analysis": {"survives_wall": False},
            }
            for i in range(4)
        },
    }), encoding="utf-8")

    matrix_dir = data / "alpha_history_runs" / "matrix_1"
    matrix_dir.mkdir(parents=True)
    (matrix_dir / "verdict_matrix_summary.json").write_text(json.dumps({
        "run_id": "matrix_1",
        "row_count": 6,
        "final_label_counts": {"insufficient evidence": 6},
        "coverage_gate_status": "PASS",
        "execution_realism_mode": "provided",
    }), encoding="utf-8")

    result = run_once(
        data_dir=data,
        repo_root=tmp_path,
        now_utc=dt.datetime(2026, 6, 19, 1, 0, tzinfo=dt.timezone.utc),
    )

    assert result["schema_version"] == "alpha_discovery_runtime_killboard_v10"
    assert result["killboard"]["is_fast_discovery_active"] is True
    assert result["killboard"]["source_present_count"] == 5
    assert result["killboard"]["runtime_source_activation_ready"] is False
    assert result["killboard"]["runtime_source_activation_status"] == "MISSING_FILES"
    assert result["killboard"]["runtime_source_git_status"] == "NOT_GIT_REPO"
    assert result["runtime_source"]["repo_root"] == str(tmp_path)
    assert result["killboard"]["ready_for_aeg_chain"] == 1
    assert result["killboard"]["promotion_ready_count"] == 1
    assert result["killboard"]["promotion_ready_candidate_found"] is True
    assert result["killboard"]["aeg_candidate_artifact_found"] is True
    assert result["killboard"]["actionable_alpha_found"] is False
    assert result["killboard"]["block"] == 1
    assert result["killboard"]["learning_worklist_status"] == "PROMOTION_REVIEW_READY"
    assert result["killboard"]["learning_task_count"] == len(
        result["learning_worklist"]["tasks"]
    )
    assert result["killboard"]["learning_task_count"] >= 5
    assert result["killboard"]["learning_promotion_ready_count"] == 1
    assert result["killboard"]["top_learning_task_arm_id"] == "mm_verdict_maker_edge"
    assert result["killboard"]["top_learning_task_type"] == "promotion_review"
    assert result["killboard"]["top_learning_task_completion_gate"] == (
        "formal_aeg_qc_mit_review_verdict_recorded"
    )
    assert result["killboard"]["top_learning_task_completion_status"] == (
        "PENDING_EVIDENCE"
    )
    assert result["killboard"]["top_learning_task_completion_evidence_required_count"] == 3
    assert result["killboard"]["top_learning_task_actionability"] == (
        "engineering_actionable"
    )
    assert result["killboard"]["top_learning_task_side_effect_boundary"] == (
        "recommendation_only_no_order_authority_no_runtime_mutation"
    )
    assert result["killboard"]["top_learning_task_evidence_key_count"] > 0
    assert isinstance(result["killboard"]["top_learning_task_evidence"], dict)
    assert result["killboard"]["top_engineering_learning_task_available"] is True
    assert result["killboard"]["top_engineering_learning_task_arm_id"] == (
        "mm_verdict_maker_edge"
    )
    assert result["killboard"]["top_engineering_learning_task_type"] == (
        "promotion_review"
    )
    assert result["killboard"]["top_engineering_learning_task_completion_gate"] == (
        "formal_aeg_qc_mit_review_verdict_recorded"
    )
    assert result["killboard"]["top_engineering_learning_task_actionability"] == (
        "engineering_actionable"
    )
    assert (
        result["killboard"][
            "top_engineering_learning_task_requires_operator_authorization"
        ]
        is False
    )
    assert (
        result["killboard"]["top_engineering_learning_task_runtime_mutation_required"]
        is False
    )
    assert result["killboard"]["top_engineering_learning_task_side_effect_boundary"] == (
        "recommendation_only_no_order_authority_no_runtime_mutation"
    )
    assert result["killboard"]["top_engineering_learning_task_evidence_key_count"] > 0
    assert result["learning_worklist"]["top_task"]["task_type"] == "promotion_review"
    latest = Path(result["written"]["latest"])
    assert latest.exists()
    loaded = json.loads(latest.read_text(encoding="utf-8"))
    assert loaded["learning_worklist"] == loaded["discovery_plan"]["learning_worklist"]
    arms = {row["arm_id"]: row for row in loaded["discovery_plan"]["arms"]}
    raw_arms = {row["arm_id"]: row for row in loaded["arms_raw"]}
    assert arms["mm_verdict_maker_edge"]["action"] == "READY_FOR_AEG_CHAIN"
    assert raw_arms["mm_verdict_maker_edge"]["detail"]["cost_wall_summary"]["best_symbol_by_net_edge"] == "BTCUSDT"
    assert raw_arms["mm_verdict_maker_edge"]["detail"]["sample_gated_cost_wall_summary"]["status"] == (
        "SAMPLE_GATED_CURRENT_FEE_POSITIVE"
    )
    assert raw_arms["mm_verdict_maker_edge"]["detail"]["gross_edge_cost_decomposition"]["status"] == (
        "CURRENT_FEE_GROSS_AND_NET_POSITIVE"
    )
    assert raw_arms["mm_verdict_maker_edge"]["detail"]["fee_path_feasibility"]["status"] == (
        "CURRENT_ACCOUNT_FEE_CLEARS_BREAK_EVEN"
    )
    assert raw_arms["mm_verdict_maker_edge"]["detail"]["history_scorecard"]["status"] == (
        "HISTORY_LOWER_FEE_ONLY"
    )
    assert raw_arms["mm_verdict_maker_edge"]["detail"]["history_scorecard_source"] == (
        "canonical_fillsim_history_scorecard"
    )
    assert (
        raw_arms["mm_verdict_maker_edge"]["detail"]["history_scorecard"]
        ["lower_fee_break_even_stability"]["status"]
    ) == "LOWER_FEE_BREAK_EVEN_REPEATS_ACROSS_WINDOWS"
    assert (
        raw_arms["mm_verdict_maker_edge"]["detail"]["history_scorecard"][
            "low_friction_near_miss_motif_stability"
        ]["status"]
        == "LOW_FRICTION_NEAR_MISS_MOTIF_REPEATS_BUT_DATE_INSUFFICIENT"
    )
    motif_packet = raw_arms["mm_verdict_maker_edge"]["detail"][
        "mm_motif_amplification_packet"
    ]
    assert motif_packet["schema_version"] == "mm_motif_amplification_packet_v1"
    assert motif_packet["status"] == (
        "MM_MOTIF_AMPLIFICATION_REQUIRES_DISTINCT_DATE_HISTORY"
    )
    assert motif_packet["summary"]["top_motif_key"] == (
        "low_friction_motif|spread_combo"
    )
    assert motif_packet["summary"]["top_frontier_candidate_count"] == 1
    assert motif_packet["summary"]["top_frontier_best_min_gross_key"] == (
        "frontier-runtime"
    )
    assert raw_arms["mm_verdict_maker_edge"]["detail"]["walk_forward_failure_summary"]["status"] == (
        "TRAIN_POSITIVE_HOLDOUT_DECAY"
    )
    assert arms["gate_b_listing_fade"]["action"] == "WAIT"
    assert arms["vol_event_order_flow"]["reason"] == "gate_status:no_edge_survives"
    scorecard = loaded["discovery_plan"]["profitability_blocker_scorecard"]
    scorecard_arms = {row["arm_id"]: row for row in scorecard["arms"]}
    assert loaded["profitability_blocker_scorecard"] == scorecard
    assert scorecard["status"] == "ACTIONABLE_ALPHA_REVIEW_READY"
    assert scorecard_arms["mm_verdict_maker_edge"]["blocker_class"] == "candidate_review_ready"
    assert scorecard_arms["vol_event_order_flow"]["blocker_class"] == "rejected_no_edge"
    history = Path(result["written"]["history"])
    history_row = json.loads(history.read_text(encoding="utf-8").splitlines()[-1])
    assert history_row["learning_worklist_status"] == "PROMOTION_REVIEW_READY"
    assert history_row["top_learning_task_type"] == "promotion_review"
    assert history_row["top_learning_task_arm_id"] == "mm_verdict_maker_edge"
    assert history_row["top_learning_task_completion_gate"] == (
        "formal_aeg_qc_mit_review_verdict_recorded"
    )
    assert history_row["top_learning_task_completion_status"] == "PENDING_EVIDENCE"
    assert history_row["top_learning_task_completion_evidence_required_count"] == 3
    assert history_row["top_learning_task_side_effect_boundary"] == (
        "recommendation_only_no_order_authority_no_runtime_mutation"
    )
    assert history_row["top_learning_task_evidence_key_count"] > 0
    assert history_row["top_engineering_learning_task_available"] is True
    assert history_row["top_engineering_learning_task_arm_id"] == (
        "mm_verdict_maker_edge"
    )
    assert history_row["top_engineering_learning_task_type"] == "promotion_review"
    assert history_row["top_engineering_learning_task_completion_gate"] == (
        "formal_aeg_qc_mit_review_verdict_recorded"
    )
    assert history_row["top_engineering_learning_task_actionability"] == (
        "engineering_actionable"
    )
    assert (
        history_row["top_engineering_learning_task_requires_operator_authorization"]
        is False
    )
    assert (
        history_row["top_engineering_learning_task_runtime_mutation_required"]
        is False
    )
    assert history_row["top_engineering_learning_task_side_effect_boundary"] == (
        "recommendation_only_no_order_authority_no_runtime_mutation"
    )
    assert history_row["top_engineering_learning_task_evidence_key_count"] > 0


def test_runtime_runner_requires_trusted_source_for_actionable_alpha(tmp_path):
    data = tmp_path / "openclaw"
    (data / "logs").mkdir(parents=True)
    (data / "logs" / "recorder_mm_verdict.log").write_text(json.dumps({
        "ts_utc": "2026-06-19T00:00:00Z",
        "thresholds": {"min_maker_fills": 30},
        "markout_n_total": 31,
        "adverse_selection_usable": True,
        "cost_wall_summary": {
            "available": True,
            "best_symbol_by_net_edge": "BTCUSDT",
            "best_fee_round_trip_shortfall_bps": -1.25,
        },
        "sample_gated_cost_wall_summary": {
            "available": True,
            "status": "SAMPLE_GATED_CURRENT_FEE_POSITIVE",
            "best_sample_gated_net_bps": 0.25,
        },
        "gross_edge_cost_decomposition": {
            "available": True,
            "status": "CURRENT_FEE_GROSS_AND_NET_POSITIVE",
            "best_sample_gated_gross_edge_bps": 4.25,
            "best_gross_cell_net_bps": 0.25,
        },
        "fee_path_feasibility": {
            "status": "CURRENT_ACCOUNT_FEE_CLEARS_BREAK_EVEN",
            "break_even_maker_fee_bps_per_side": 2.2,
        },
        "net_edge_per_symbol": {
            "BTCUSDT": {"net_edge_bps": 1.25, "n_maker_fills": 31},
        },
    }) + "\n", encoding="utf-8")
    repo = _init_clean_source_repo_with_origin(tmp_path)
    head = _git_output(repo, "rev-parse", "HEAD")

    result = run_once(
        data_dir=data,
        repo_root=repo,
        expected_head=head[:12],
        now_utc=dt.datetime(2026, 6, 19, 1, 0, tzinfo=dt.timezone.utc),
    )

    assert result["killboard"]["runtime_source_activation_ready"] is True
    assert result["killboard"]["runtime_source_activation_status"] == "SYNCED_CLEAN"
    assert result["killboard"]["runtime_source_expected_head_status"] == "MATCH"
    assert result["killboard"]["promotion_ready_count"] == 1
    assert result["killboard"]["promotion_ready_candidate_found"] is True
    assert result["killboard"]["actionable_alpha_found"] is True
    assert result["killboard"]["learning_worklist_status"] == "PROMOTION_REVIEW_READY"
    assert result["killboard"]["top_learning_task_type"] == "promotion_review"


def test_runtime_runner_blocks_stale_mm_verdict_status(tmp_path):
    data = tmp_path / "openclaw"
    (data / "logs").mkdir(parents=True)
    (data / "logs" / "recorder_mm_verdict.log").write_text(json.dumps({
        "ts_utc": "2026-06-17T21:45:03Z",
        "thresholds": {"min_maker_fills": 30},
        "markout_n_total": 31,
        "adverse_selection_usable": True,
        "net_edge_per_symbol": {
            "BTCUSDT": {"net_edge_bps": 1.25, "n_maker_fills": 31},
        },
    }) + "\n", encoding="utf-8")

    arms = collect_runtime_arms(
        data_dir=data,
        now_utc=dt.datetime(2026, 6, 19, 22, 30, tzinfo=dt.timezone.utc),
    )
    mm_arm = next(arm for arm in arms if arm["arm_id"] == "mm_verdict_maker_edge")
    plan = build_discovery_plan([mm_arm], now_utc=dt.datetime(2026, 6, 19, 22, 30, tzinfo=dt.timezone.utc))

    assert mm_arm["source_ok"] is False
    assert mm_arm["source_error"] == "stale_artifact"
    assert mm_arm["gate_status"] == "SOURCE_FAILURE"
    assert mm_arm["detail"]["age_seconds"] > 36 * 60 * 60
    assert plan["arms"][0]["action"] == "BLOCK"
    assert plan["arms"][0]["reason"] == "source_not_healthy"


def test_runtime_runner_blocks_stale_flash_dip_death_rate_status(tmp_path):
    data = tmp_path / "openclaw"
    (data / "logs").mkdir(parents=True)
    (data / "logs" / "flash_dip_death_rate.log").write_text(json.dumps({
        "ts_utc": "2026-06-17T04:53:01Z",
        "thresholds": {"min_n": 20},
        "n_closed_slots": 24,
        "n_deaths": 0,
        "death_rate_pct": 0.0,
        "actionable": True,
        "alerted": False,
    }) + "\n", encoding="utf-8")

    arm = collect_flash_dip_arm(
        data,
        now_utc=dt.datetime(2026, 6, 19, 22, 30, tzinfo=dt.timezone.utc),
    )
    plan = build_discovery_plan([arm], now_utc=dt.datetime(2026, 6, 19, 22, 30, tzinfo=dt.timezone.utc))

    assert arm["source_ok"] is False
    assert arm["source_error"] == "stale_artifact"
    assert arm["gate_status"] == "SOURCE_FAILURE"
    assert arm["artifacts_ready"] is False
    assert arm["detail"]["age_seconds"] > 36 * 60 * 60
    assert plan["arms"][0]["action"] == "BLOCK"
    assert plan["arms"][0]["reason"] == "source_not_healthy"


def _write_demo_learning_evidence_latest(
    data: Path,
    *,
    status: str,
    generated_at: str = "2026-06-21T18:00:00+00:00",
    reason: str = "test reason",
    next_action: str = "test_next_action",
    cost_gate_rejects_recorded: bool = False,
    observation_only: bool = False,
    learning_data_flow_stale: bool = False,
    order_flow_starved: bool = False,
    recommendation_status: str | None = None,
    recommendation_next_action: str | None = None,
    learning_gate_adjustment: str | None = None,
    runtime_preflight_blocking: bool = False,
    runtime_source_activation_ready: bool | None = True,
    runtime_source_activation_status: str | None = "SYNCED_CLEAN",
    runtime_activation_blockers: list[str] | None = None,
) -> Path:
    path = data / "demo_learning_evidence" / "demo_learning_evidence_audit_latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    default_recommendation_status = (
        "BOUNDED_LEARNING_LANE_ACTIVATION_RECOMMENDED"
        if order_flow_starved
        else "ORDER_TO_FILL_DIAGNOSIS_BEFORE_COST_GATE_CHANGE"
        if cost_gate_rejects_recorded
        else "NO_COST_GATE_ADJUSTMENT_RECOMMENDED"
    )
    default_recommendation_next_action = (
        "activate_cost_gate_learning_lane_then_operator_review_bounded_demo_probe"
        if order_flow_starved
        else "diagnose_demo_order_to_fill_gap_before_cost_gate_changes"
    )
    default_learning_gate_adjustment = (
        "ENABLE_LEDGER_AND_OUTCOME_REVIEW_FIRST"
        if order_flow_starved
        else "NONE_DIAGNOSE_ORDER_TO_FILL_FIRST"
    )
    path.write_text(json.dumps({
        "schema_version": "demo_learning_evidence_audit_v1",
        "generated_at_utc": generated_at,
        "classification": {
            "status": status,
            "reason": reason,
            "next_action": next_action,
            "answers": {
                "cost_gate_rejects_recorded_in_pg": cost_gate_rejects_recorded,
                "demo_observation_only_contexts_active": observation_only,
                "candidate_or_reject_data_accumulating": cost_gate_rejects_recorded,
                "learning_lane_ledger_rows_present": False,
                "learning_lane_currently_accumulating_evidence": False,
                "blocked_outcome_review_candidate_present": False,
                "order_flow_silent_drop_risk": False,
                "recent_order_flow_present": (
                    not order_flow_starved and cost_gate_rejects_recorded
                ),
                "recent_fill_evidence_present": False,
                "order_flow_evidence_starved": order_flow_starved,
                "learning_data_flow_fresh": not learning_data_flow_stale,
                "learning_data_flow_stale": learning_data_flow_stale,
                "bounded_demo_learning_lane_recommended": (
                    cost_gate_rejects_recorded and not runtime_preflight_blocking
                ),
                "runtime_preflight_blocking_cost_gate_adjustment": (
                    runtime_preflight_blocking
                ),
            },
            "key_counts": {
                "decision_context_snapshots": 1200,
                "risk_verdicts": 24155 if cost_gate_rejects_recorded else 0,
                "rejected_decision_features": 24152 if cost_gate_rejects_recorded else 0,
                "orders": 3 if cost_gate_rejects_recorded else 0,
                "fills": 0,
                "learning_ledger_rows": 0,
                "blocked_signal_outcomes": 0,
                "order_flow_evidence_status": (
                    "COST_GATE_REJECT_WALL_NO_ORDER_FLOW_EVIDENCE"
                    if order_flow_starved
                    else "DEMO_ORDER_FLOW_PRESENT_NO_FILL_EVIDENCE"
                    if cost_gate_rejects_recorded
                    else "NO_ORDER_FLOW_EVIDENCE"
                ),
                "order_flow_evidence_reason": "fixture order-flow evidence",
                "order_flow_evidence_next_action": (
                    "activate_cost_gate_learning_lane_then_operator_review_bounded_demo_probe"
                    if order_flow_starved
                    else "diagnose_demo_order_to_fill_gap_before_alpha_promotion"
                ),
                "cost_gate_adjustment_recommendation_status": (
                    recommendation_status or default_recommendation_status
                ),
                "cost_gate_adjustment_recommendation_reason": (
                    "fixture Cost Gate recommendation"
                ),
                "cost_gate_adjustment_recommendation_next_action": (
                    recommendation_next_action or default_recommendation_next_action
                ),
                "cost_gate_learning_gate_adjustment": (
                    learning_gate_adjustment or default_learning_gate_adjustment
                ),
                "cost_gate_adjustment_runtime_preflight_blocking": (
                    runtime_preflight_blocking
                ),
                "cost_gate_adjustment_runtime_activation_ready": (
                    not runtime_preflight_blocking
                ),
                "cost_gate_adjustment_runtime_activation_blockers": (
                    runtime_activation_blockers or []
                ),
                "cost_gate_adjustment_runtime_source_activation_ready": (
                    runtime_source_activation_ready
                ),
                "cost_gate_adjustment_runtime_source_activation_status": (
                    runtime_source_activation_status
                ),
                "data_flow_freshness_status": (
                    "LEARNING_DATA_FLOW_STALE"
                    if learning_data_flow_stale
                    else "LEARNING_DATA_FLOW_FRESH"
                ),
                "latest_learning_stage": "risk_verdicts",
                "latest_learning_ts_utc": "2026-06-21T20:47:59+00:00",
                "latest_learning_age_seconds": 8461 if learning_data_flow_stale else 60,
            },
        },
        "order_stall_scorecard": {
            "classification": {
                "status": "COST_GATE_REJECTING_ALL_RECENT_ATTEMPTS"
                if cost_gate_rejects_recorded
                else "OBSERVATION_ONLY_CONTEXTS_ACTIVE",
            },
        },
        "cost_gate_learning_preflight": {
            "status": "NOT_ACCUMULATING",
        },
    }), encoding="utf-8")
    return path


def _write_demo_learning_stack_healthcheck_latest(
    data: Path,
    *,
    status: str,
    reason: str,
    next_action: str,
    ts_utc: str = "2026-06-21T18:04:00+00:00",
    source_ready: bool = True,
    stack_installed: bool = False,
    demo_cron_entry_present: bool = False,
    sealed_preflight_cron_entry_present: bool = False,
    cost_cron_entry_present: bool = False,
    healthcheck_cron_entry_present: bool = False,
    heartbeats_recent: bool = False,
    demo_heartbeat_recent: bool = False,
    sealed_preflight_heartbeat_recent: bool = False,
    cost_heartbeat_recent: bool = False,
    statuses_recent: bool = False,
    demo_status_recent: bool = False,
    sealed_preflight_status_recent: bool = False,
    cost_status_recent: bool = False,
    latest_artifacts_present: bool = False,
    sealed_preflight_present: bool = False,
    bounded_reviews_present: bool = False,
    bounded_result_review_present: bool = False,
    bounded_execution_realism_review_present: bool = False,
    ledger_rows_present: bool = False,
    blocked_outcomes_present: bool = False,
) -> Path:
    path = (
        data
        / "demo_learning_stack_healthcheck"
        / "demo_learning_stack_healthcheck_latest.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": "demo_learning_stack_healthcheck_v1",
        "ts_utc": ts_utc,
        "status": status,
        "reason": reason,
        "next_action": next_action,
        "answers": {
            "source_ready": source_ready,
            "stack_installed": stack_installed,
            "demo_learning_evidence_cron_entry_present": demo_cron_entry_present,
            "sealed_horizon_probe_preflight_cron_entry_present": (
                sealed_preflight_cron_entry_present
            ),
            "cost_gate_learning_lane_cron_entry_present": cost_cron_entry_present,
            "demo_learning_stack_healthcheck_cron_entry_present": (
                healthcheck_cron_entry_present
            ),
            "heartbeats_recent": heartbeats_recent,
            "demo_learning_evidence_heartbeat_recent": demo_heartbeat_recent,
            "sealed_horizon_probe_preflight_heartbeat_recent": (
                sealed_preflight_heartbeat_recent
            ),
            "cost_gate_learning_lane_heartbeat_recent": cost_heartbeat_recent,
            "statuses_recent": statuses_recent,
            "demo_learning_evidence_status_recent": demo_status_recent,
            "sealed_horizon_probe_preflight_status_recent": (
                sealed_preflight_status_recent
            ),
            "cost_gate_learning_lane_status_recent": cost_status_recent,
            "latest_artifacts_present": latest_artifacts_present,
            "sealed_horizon_probe_preflight_present": sealed_preflight_present,
            "bounded_probe_reviews_present": bounded_reviews_present,
            "bounded_probe_result_review_present": bounded_result_review_present,
            "bounded_probe_execution_realism_review_present": (
                bounded_execution_realism_review_present
            ),
            "bounded_probe_result_review_status": None,
            "bounded_probe_execution_realism_review_status": None,
            "bounded_probe_result_review_skip_reason": None,
            "bounded_probe_execution_realism_review_skip_reason": None,
            "cost_gate_learning_ledger_rows_present": ledger_rows_present,
            "blocked_signal_outcomes_present": blocked_outcomes_present,
            "blocked_outcome_review_present": blocked_outcomes_present,
            "demo_learning_evidence_classification_status": (
                "PG_REJECTS_RECORDED_LEARNING_LANE_NOT_ACCUMULATING"
            ),
            "cost_gate_learning_review_status": None,
        },
    }), encoding="utf-8")
    return path


def _write_demo_learning_stack_activation_packet_latest(
    data: Path,
    *,
    status: str,
    reason: str,
    operator_next_action: str,
    generated_at: str = "2026-06-21T18:04:00+00:00",
    install_review_ready: bool = True,
    missing_crons: list[str] | None = None,
    healthcheck_status: str = "NOT_INSTALLED",
    cost_gate_activation_status: str = "REVIEW_CANDIDATE_OPERATOR_REVIEW",
) -> Path:
    path = (
        data
        / "demo_learning_stack_activation_packet"
        / "demo_learning_stack_activation_packet_latest.json"
    )
    missing = missing_crons or [
        "demo_learning_evidence",
        "sealed_horizon_probe_preflight",
        "cost_gate_learning_lane",
        "demo_learning_stack_healthcheck",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": "demo_learning_stack_activation_packet_v1",
        "generated_at_utc": generated_at,
        "status": status,
        "reason": reason,
        "operator_next_action": operator_next_action,
        "missing_links": [f"cron:{name}" for name in missing],
        "install_review_ready": install_review_ready,
        "answers": {
            "source_ready": True,
            "stack_installed": False,
            "missing_cron_count": len(missing),
            "missing_crons": missing,
            "sealed_horizon_probe_preflight_present": True,
            "bounded_probe_reviews_present": False,
            "cost_gate_activation_ready": True,
            "runtime_writer_enabled": False,
            "global_cost_gate_lowering_recommended": False,
            "order_authority_granted": False,
            "probe_authority_granted": False,
            "promotion_proof": False,
        },
        "planned_stack": {
            "cron_count": 4,
            "crons": [],
            "healthcheck_status": healthcheck_status,
            "cost_gate_activation_status": cost_gate_activation_status,
        },
        "profitability_path": {
            "cost_gate_escape_thesis": (
                "collect rejected demo signals and compare matched blocked outcomes"
            ),
            "edge_amplification_levers": [
                "side_cell_filtering",
                "horizon_retiming",
                "low_friction_execution_filtering",
            ],
            "next_profit_gate_after_activation": (
                "bounded_probe_result_review_and_execution_realism_review_with_matched_controls"
            ),
        },
        "operator_commands": {
            "dry_run_preview": {
                "shell": "OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=0 install_stack",
                "mutates_crontab": False,
            },
            "operator_only_apply": {
                "shell": "OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=1 install_stack",
                "mutates_crontab": True,
                "requires_operator_approval": True,
            },
            "operator_only_rollback": {
                "shell": "OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=1 install_stack --remove",
                "mutates_crontab": True,
                "requires_operator_approval": True,
            },
            "post_install_verification": {
                "shell": "python3 demo_learning_stack_healthcheck.py --fail-on-not-active",
                "mutates_crontab": False,
            },
        },
    }), encoding="utf-8")
    return path


def _write_demo_learning_stack_dry_run_review_latest(
    data: Path,
    *,
    status: str,
    reason: str,
    operator_next_action: str,
    generated_at: str = "2026-06-21T18:04:30+00:00",
    passed: bool = True,
) -> Path:
    path = (
        data
        / "demo_learning_stack_dry_run_review"
        / "demo_learning_stack_dry_run_review_latest.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": "demo_learning_stack_dry_run_review_v1",
        "generated_at_utc": generated_at,
        "status": status,
        "reason": reason,
        "operator_next_action": operator_next_action,
        "expected_head": "abc1234",
        "activation_packet_status": "READY_FOR_OPERATOR_DRY_RUN",
        "activation_packet_missing_cron_count": 4,
        "dry_run_preview_shell": (
            "OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=0 install_stack"
        ),
        "operator_only_apply_shell": (
            "OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=1 install_stack"
        ),
        "operator_only_rollback_shell": (
            "OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=1 install_stack --remove"
        ),
        "answers": {
            "dry_run_preview_executed": True,
            "dry_run_preview_passed": passed,
            "crontab_mutated": False,
            "operator_apply_required": passed,
            "global_cost_gate_lowering_recommended": False,
            "order_authority_granted": False,
            "probe_authority_granted": False,
            "promotion_proof": False,
        },
        "dry_run_preview": {
            "executed": True,
            "returncode": 0 if passed else 13,
            "run_error": None,
            "stdout_tail": "DRY-RUN: not modifying crontab.",
            "stderr_tail": "",
            "forced_apply_gate": "0",
            "preinstall_refresh": "0",
            "mutates_crontab": False,
        },
    }), encoding="utf-8")
    return path


def _write_profit_learning_decision_packet_latest(
    data: Path,
    *,
    status: str,
    reason: str,
    next_actions: list[str],
    generated_at: str = "2026-06-21T18:04:00+00:00",
    review_candidate: bool = False,
    sealed_horizon_candidate: bool = False,
) -> Path:
    path = (
        data
        / "cost_gate_learning_lane"
        / "profit_learning_decision_packet_latest.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    top_cell = {
        "side_cell_key": "ma_crossover|ETHUSDT|Sell",
        "strategy_name": "ma_crossover",
        "symbol": "ETHUSDT",
        "side": "Sell",
        "learning_lane_action": "LEARNING_PROBE_CANDIDATE",
        "priority_score": 82.5,
        "n": 486,
        "avg_net_bps": 97.9,
        "net_positive_pct": 86.0,
        "order_authority": "NOT_GRANTED",
        "main_cost_gate_adjustment": "NONE",
        "promotion_evidence": False,
    }
    payload = {
        "schema_version": "cost_gate_profit_learning_decision_packet_v1",
        "generated_at_utc": generated_at,
        "status": status,
        "reason": reason,
        "next_actions": next_actions,
        "answers": {
            "demo_data_flow_seen": True,
            "cost_gate_rejects_recorded": True,
            "silent_drop_risk": False,
            "counterfactual_scorecard_available": status != "RUN_REJECT_COUNTERFACTUAL",
            "counterfactual_learning_candidates_present": True,
            "bounded_plan_ready": status != "BUILD_OR_REFRESH_BOUNDED_LEARNING_PLAN",
            "activation_or_stack_health_available": status not in {
                "RUN_LEARNING_LANE_ACTIVATION_PREFLIGHT",
            },
            "blocked_outcome_review_available": review_candidate,
            "blocked_outcome_review_candidates_present": review_candidate,
            "sealed_horizon_learning_evidence_available": sealed_horizon_candidate,
            "sealed_horizon_learning_evidence_candidates_present": (
                sealed_horizon_candidate
            ),
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "data_flow": {
            "status": "RECENT_WINDOW_EMPTY_COST_GATE_REJECT_WALL",
            "broad_cost_gate_rejects": 2696,
        },
        "counterfactual": {
            "scorecard_status": "LEARNING_LANE_PROBE_CANDIDATES_PRESENT",
            "profit_opportunity_ranking_status": "PROFIT_LEARNING_CANDIDATES_PRESENT",
            "horizon_stability_status": (
                "MULTI_HORIZON_PROFIT_LEARNING_CANDIDATES_PRESENT"
            ),
            "candidate_count": 1,
            "top_side_cells": [top_cell],
        },
        "plan": {
            "status": "READY_FOR_DEMO_LEARNING_PROBE",
            "gate_status": "OPERATOR_REVIEW",
            "selected_probe_candidate_count": 1,
            "ready": True,
        },
        "activation": {"status": "DATA_ACCUMULATING", "next_actions": []},
        "blocked_review": {
            "status": (
                "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT"
                if review_candidate
                else None
            ),
            "candidate_count": 1 if review_candidate else 0,
        },
    }
    if sealed_horizon_candidate:
        payload["sealed_horizon_learning_evidence"] = {
            "status": "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT",
            "side_cell_key": "ma_crossover|ETHUSDT|Sell",
            "source_kind": "horizon_specific_sealed_replay",
            "outcome_horizon_minutes": 240,
            "blocked_signal_outcome_count": 16515,
            "avg_gross_bps": 7.0511,
            "avg_net_bps": 3.0511,
            "net_positive_pct": 68.5619,
            "review_candidate_side_cell_count": 1,
            "review_ready": True,
            "top_side_cell_status": "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE",
        }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_profitability_path_scorecard_latest(
    data: Path,
    *,
    generated_at: str = "2026-06-21T18:04:45+00:00",
    next_move_runtime_mutation_required: bool = False,
) -> Path:
    path = (
        data
        / "alpha_discovery_throughput"
        / "profitability_path_scorecard_latest.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": "alpha_profitability_path_scorecard_v1",
        "generated_at_utc": generated_at,
        "status": "PROFITABILITY_PATHS_PRESENT_BUT_EXECUTION_EVIDENCE_MISSING",
        "summary": {
            "path_count": 4,
            "cost_gate_crossing_candidate_count": 2,
            "top_path_id": "horizon_edge_amplification:ma_crossover|BTCUSDT|Sell",
            "top_path_status": "SEALED_HORIZON_PREFLIGHT_REQUIRES_OPERATOR_REVIEW",
            "top_path_next_action": "operator_review_sealed_horizon_probe_preflight",
        },
        "answers": {
            "profitability_proven": False,
            "cost_gate_crossing_candidates_present": True,
            "alpha_or_edge_amplification_paths_present": True,
            "autonomous_learning_loop_accumulating": True,
            "bounded_demo_probe_preflight_ready": False,
            "bounded_demo_probe_shadow_placement_improves_touchability": True,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "profitability_engineering_closure": {
            "schema_version": "profitability_engineering_closure_v1",
            "status": "COST_GATE_ESCAPE_PREFLIGHT_BLOCKED_BY_OPERATOR_REVIEW",
            "profit_thesis": (
                "Cross Cost Gate with bounded side-cell horizon probes, not a global gate cut."
            ),
            "leading_path_id": "horizon_edge_amplification:ma_crossover|BTCUSDT|Sell",
            "leading_path_status": "SEALED_HORIZON_PREFLIGHT_REQUIRES_OPERATOR_REVIEW",
            "leading_path_class": "horizon_retiming_or_side_cell_filter",
            "leading_candidate_key": "ma_crossover|BTCUSDT|Sell",
            "proof_gates_remaining": [
                "operator records sealed-horizon review without granting order/probe authority"
            ],
            "proof_gate_count_remaining": 1,
            "next_actions": [
                "operator_review_sealed_horizon_probe_preflight",
                "continue_low_friction_mm_and_external_alpha_search",
            ],
            "cost_gate_root_blockers": [
                {
                    "source": "sealed_horizon_probe_preflight",
                    "gate": "operator_sealed_horizon_review_recorded",
                    "status": "PENDING_OPERATOR_REVIEW",
                    "reason": "operator review must approve preflight review without granting authority",
                    "next_action": "operator_review_sealed_horizon_probe_preflight",
                }
            ],
            "primary_cost_gate_root_blocker": {
                "source": "sealed_horizon_probe_preflight",
                "gate": "operator_sealed_horizon_review_recorded",
                "status": "PENDING_OPERATOR_REVIEW",
                "reason": "operator review must approve preflight review without granting authority",
                "next_action": "operator_review_sealed_horizon_probe_preflight",
            },
            "profitability_next_move": {
                "schema_version": "profitability_next_move_v1",
                "status": "COST_GATE_ESCAPE_PREFLIGHT_BLOCKED_BY_OPERATOR_REVIEW",
                "move_class": "operator_reviews_sealed_horizon_edge_before_probe",
                "primary_objective": "turn blocked-signal edge into bounded demo probe learning evidence",
                "recommended_action": "operator_review_sealed_horizon_probe_preflight",
                "edge_snapshot": {
                    "path_id": "horizon_edge_amplification:ma_crossover|BTCUSDT|Sell",
                    "path_class": "horizon_retiming_or_side_cell_filter",
                    "candidate_key": "ma_crossover|BTCUSDT|Sell",
                    "current_edge_bps": 9.0,
                    "cost_threshold_bps": 4.0,
                    "edge_above_cost_bps": 5.0,
                },
                "runtime_mutation_required": next_move_runtime_mutation_required,
            },
            "cost_gate_escape_strategy": {
                "method": "bounded_side_cell_horizon_probe_after_preflight",
                "global_cost_gate_lowering": False,
                "main_cost_gate_adjustment": "NONE",
                "probe_authority_granted": False,
                "order_authority_granted": False,
                "promotion_evidence": False,
                "sealed_horizon_probe_preflight_status": "OPERATOR_REVIEW_REQUIRED",
                "bounded_probe_operator_authorization_status": (
                    "SEALED_HORIZON_PREFLIGHT_NOT_READY"
                ),
                "bounded_probe_operator_authorization_decision": "defer",
                "bounded_probe_operator_authorization_blocking_gate_count": 1,
                "bounded_probe_operator_authorization_blocking_gates": [
                    "sealed_horizon_preflight_ready"
                ],
                "bounded_probe_operator_authorization_ready_for_review": False,
                "bounded_probe_operator_authorization_object_emitted": False,
                "bounded_probe_operator_authorization_active_runtime_probe_authority": False,
                "bounded_probe_operator_authorization_active_runtime_order_authority": False,
                "bounded_probe_result_review_status": "NO_PROBE_OUTCOMES_RECORDED",
                "bounded_probe_shadow_placement_status": (
                    "SHADOW_PLACEMENT_TOUCHABILITY_IMPROVED_SAMPLE_MISMATCH"
                ),
                "bounded_probe_execution_realism_review_status": (
                    "NO_EXECUTION_REALISM_GAP_TO_REVIEW"
                ),
            },
            "edge_amplification_levers": [
                {
                    "path_class": "horizon_retiming_or_side_cell_filter",
                    "status": "SEALED_HORIZON_PREFLIGHT_REQUIRES_OPERATOR_REVIEW",
                    "path_count": 1,
                    "top_path_id": (
                        "horizon_edge_amplification:ma_crossover|BTCUSDT|Sell"
                    ),
                    "top_candidate_key": "ma_crossover|BTCUSDT|Sell",
                    "required_next_gate": (
                        "operator_review_recorded_without_granting_order_or_probe_authority"
                    ),
                    "next_action": "operator_review_sealed_horizon_probe_preflight",
                }
            ],
            "edge_amplification_backlog": [
                {
                    "path_class": "horizon_retiming_or_side_cell_filter",
                    "candidate_key": "ma_crossover|BTCUSDT|Sell",
                    "edge_above_cost_bps": 5.0,
                    "next_action": "operator_review_sealed_horizon_probe_preflight",
                }
            ],
        },
        "operator_read": {
            "do_not_lower_global_cost_gate": True,
            "profitability_next_move": {
                "schema_version": "profitability_next_move_v1",
                "status": "COST_GATE_ESCAPE_PREFLIGHT_BLOCKED_BY_OPERATOR_REVIEW",
                "move_class": "operator_reviews_sealed_horizon_edge_before_probe",
                "primary_objective": "turn blocked-signal edge into bounded demo probe learning evidence",
                "recommended_action": "operator_review_sealed_horizon_probe_preflight",
                "runtime_mutation_required": next_move_runtime_mutation_required,
            },
            "recommended_engineering_sequence": [
                "operator_review_sealed_horizon_probe_preflight",
                "continue_low_friction_mm_and_external_alpha_search",
            ],
        },
    }), encoding="utf-8")
    return path


def _write_sealed_horizon_probe_preflight_latest(
    data: Path,
    *,
    status: str = "OPERATOR_REVIEW_AND_PRODUCTION_LEARNING_LANE_REQUIRED",
    generated_at: str = "2026-06-21T18:04:30+00:00",
) -> Path:
    path = (
        data
        / "cost_gate_learning_lane"
        / "sealed_horizon_probe_preflight_latest.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    blocking_gates: list[str]
    if status == "OPERATOR_REVIEW_AND_PRODUCTION_LEARNING_LANE_REQUIRED":
        blocking_gates = [
            "operator_sealed_horizon_review_recorded",
            "production_learning_lane_accumulating",
        ]
    elif status == "PRODUCTION_LEARNING_LANE_NOT_READY":
        blocking_gates = ["production_learning_lane_accumulating"]
    else:
        blocking_gates = []
    payload = {
        "schema_version": "sealed_horizon_bounded_demo_probe_preflight_v1",
        "generated_at_utc": generated_at,
        "status": status,
        "reason": ";".join(blocking_gates)
        or "all_pre_authorization_gates_passed_without_authority_grant",
        "side_cell_key": "ma_crossover|ETHUSDT|Sell",
        "outcome_horizon_minutes": 240,
        "blocking_gate_count": len(blocking_gates),
        "blocking_gates": blocking_gates,
        "next_actions": [
            "operator_review_sealed_horizon_learning_evidence_before_bounded_demo_probe",
            "sync_runtime_source_then_enable_learning_lane_writer_after_operator_review",
        ],
        "answers": {
            "sealed_horizon_evidence_ready": True,
            "decision_packet_aligned": True,
            "operator_review_recorded": not any(
                gate == "operator_sealed_horizon_review_recorded"
                for gate in blocking_gates
            ),
            "production_learning_lane_accumulating": not any(
                gate == "production_learning_lane_accumulating"
                for gate in blocking_gates
            ),
            "ready_for_operator_bounded_demo_probe_authorization": (
                status == "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION"
            ),
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_sealed_horizon_operator_review_latest(
    data: Path,
    *,
    status: str = "PENDING_OPERATOR_REVIEW",
    decision: str = "defer",
    generated_at: str = "2026-06-21T18:04:40+00:00",
) -> Path:
    path = (
        data
        / "cost_gate_learning_lane"
        / "sealed_horizon_operator_review_latest.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "sealed_horizon_operator_review_v1",
        "generated_at_utc": generated_at,
        "status": status,
        "reason": decision,
        "decision": decision,
        "operator_id": None,
        "review_scope": "preflight_review_only_not_probe_authorization",
        "side_cell_key": "ma_crossover|ETHUSDT|Sell",
        "outcome_horizon_minutes": 240,
        "operator_review_approved": False,
        "main_cost_gate_adjustment": "NONE",
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "promotion_evidence": False,
        "blocking_gate_count": 0,
        "blocking_gates": [],
        "next_actions": [
            "operator_review_sealed_horizon_preflight_before_bounded_demo_probe"
        ],
        "answers": {
            "operator_review_approved": False,
            "sealed_horizon_evidence_ready": True,
            "sealed_horizon_probe_preflight_aligned": True,
            "review_grants_runtime_authority": False,
            "bounded_demo_probe_authorized": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_bounded_probe_result_review_latest(
    data: Path,
    *,
    status: str,
    generated_at: str = "2026-06-21T18:04:45+00:00",
    evidence_quality_status: str | None = None,
    matched_control_count: int | None = None,
    matched_control_avg_net_bps: float = 1.0,
) -> Path:
    path = (
        data
        / "cost_gate_learning_lane"
        / "bounded_probe_result_review_latest.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    if evidence_quality_status is None:
        evidence_quality_status = (
            "REALIZED_EDGE_FAILED"
            if status == "STOP_BOUNDED_DEMO_PROBE_REALIZED_EDGE_FAILED"
            else "LEARNING_REVIEW_WITH_MATCHED_CONTROL_COMPARISON"
        )
    if matched_control_count is None:
        matched_control_count = 0 if "MISSING" in evidence_quality_status else 3
    avg_net = -1.2 if status == "STOP_BOUNDED_DEMO_PROBE_REALIZED_EDGE_FAILED" else 2.5
    net_positive = 33.3 if status == "STOP_BOUNDED_DEMO_PROBE_REALIZED_EDGE_FAILED" else 100.0
    probe_minus_control = (
        avg_net - matched_control_avg_net_bps
        if matched_control_count
        else None
    )
    probe_edge_capture_ratio = (
        round(avg_net / matched_control_avg_net_bps, 4)
        if matched_control_count and matched_control_avg_net_bps > 0.0
        else None
    )
    probe_execution_gap_bps = (
        round(-probe_minus_control, 4)
        if probe_minus_control is not None and probe_minus_control < 0.0
        else None
    )
    execution_realism_gap = (
        evidence_quality_status == "PROBE_UNDERPERFORMS_MATCHED_CONTROL_EXECUTION_GAP"
    )
    next_action = (
        "stop_probe_and_keep_cost_gate_blocked_for_this_side_cell"
        if status == "STOP_BOUNDED_DEMO_PROBE_REALIZED_EDGE_FAILED"
        else "record_matched_blocked_signal_outcomes_for_same_side_cell_and_horizon"
        if evidence_quality_status == "CONTROL_COMPARISON_MISSING"
        else "operator_review_probe_learning_results_before_any_promotion_or_gate_change"
    )
    if execution_realism_gap:
        next_action = (
            "investigate_probe_execution_realism_slippage_and_timing_before_cost_gate_review"
        )
    payload = {
        "schema_version": "bounded_demo_probe_result_review_v1",
        "generated_at_utc": generated_at,
        "status": status,
        "reason": "fixture_bounded_probe_result_review",
        "side_cell_key": "ma_crossover|ETHUSDT|Sell",
        "probe_result_summary": {
            "admitted_probe_attempt_count": 3,
            "completed_probe_outcome_count": 3,
            "positive_probe_outcome_count": 1
            if status == "STOP_BOUNDED_DEMO_PROBE_REALIZED_EDGE_FAILED"
            else 3,
            "avg_realized_gross_bps": avg_net + 4.0,
            "avg_realized_net_bps": avg_net,
            "net_positive_pct": net_positive,
            "first_review_outcome_floor": 3,
            "learning_review_outcome_floor": 10,
        },
        "evidence_quality": {
            "schema_version": "bounded_demo_probe_evidence_quality_v1",
            "status": evidence_quality_status,
            "reason": "fixture_evidence_quality",
            "matched_control_required": True,
            "matched_control_present": matched_control_count > 0,
            "matched_control_outcome_count": matched_control_count,
            "matched_control_avg_net_bps": matched_control_avg_net_bps
            if matched_control_count
            else None,
            "matched_control_net_positive_pct": 66.7 if matched_control_count else None,
            "probe_minus_control_avg_net_bps": probe_minus_control,
            "probe_edge_capture_ratio": probe_edge_capture_ratio,
            "probe_execution_gap_bps": probe_execution_gap_bps,
            "probe_outperforms_matched_control": (
                matched_control_count > 0 and avg_net > matched_control_avg_net_bps
            ),
            "execution_realism_gap": execution_realism_gap,
            "anecdote_risk": evidence_quality_status
            in {
                "CONTROL_COMPARISON_MISSING",
                "MATCHED_CONTROL_SAMPLE_BELOW_FIRST_REVIEW_FLOOR",
            },
            "promotion_evidence": False,
        },
        "answers": {
            "authority_boundary_preserved": True,
            "operator_review_required": True,
            "continue_probe_without_operator_review_allowed": False,
            "stop_probe_recommended": (
                status == "STOP_BOUNDED_DEMO_PROBE_REALIZED_EDGE_FAILED"
            ),
            "learning_review_candidate": (
                status == "LEARNING_REVIEW_CANDIDATE_OPERATOR_REVIEW_REQUIRED"
            ),
            "matched_control_comparison_present": matched_control_count > 0,
            "anecdote_risk": evidence_quality_status
            in {
                "CONTROL_COMPARISON_MISSING",
                "MATCHED_CONTROL_SAMPLE_BELOW_FIRST_REVIEW_FLOOR",
            },
            "execution_realism_gap": execution_realism_gap,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "next_actions": [next_action],
        "design": {
            "status": "READY_FOR_SEPARATE_OPERATOR_AUTHORIZATION",
            "side_cell_key": "ma_crossover|ETHUSDT|Sell",
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_bounded_probe_execution_realism_review_latest(
    data: Path,
    *,
    status: str = "EXECUTION_REALISM_GAP_DIAGNOSED_REPAIR_REQUIRED",
    generated_at: str = "2026-06-21T18:04:50+00:00",
    primary_hypothesis: str = "fill_backed_execution_missing",
    next_action: str = "record_fill_backed_probe_execution_rows_or_l1_replay_before_cost_gate_review",
) -> Path:
    path = (
        data
        / "cost_gate_learning_lane"
        / "bounded_probe_execution_realism_review_latest.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "bounded_demo_probe_execution_realism_review_v1",
        "generated_at_utc": generated_at,
        "status": status,
        "reason": "fixture_bounded_probe_execution_realism_review",
        "side_cell_key": "ma_crossover|ETHUSDT|Sell",
        "candidate": {
            "strategy_name": "ma_crossover",
            "symbol": "ETHUSDT",
            "side": "Sell",
            "outcome_horizon_minutes": 240,
        },
        "source_result_review": {
            "schema_version": "bounded_demo_probe_result_review_v1",
            "status": "FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED",
            "evidence_quality_status": (
                "PROBE_UNDERPERFORMS_MATCHED_CONTROL_EXECUTION_GAP"
            ),
            "generated_at_utc": generated_at,
            "probe_edge_capture_ratio": 0.8333,
            "probe_execution_gap_bps": 0.5,
            "probe_minus_control_avg_net_bps": -0.5,
        },
        "probe_execution_summary": {
            "count": 3,
            "avg_net_bps": 2.5,
            "avg_gross_bps": 6.5,
            "avg_cost_bps": 4.0,
            "avg_entry_delay_ms": 120000.0,
            "fill_backed_outcome_count": 0,
            "proxy_outcome_count": 3,
            "fill_backed_pct": 0.0,
        },
        "matched_control_execution_summary": {
            "count": 3,
            "avg_net_bps": 3.0,
            "avg_gross_bps": 7.0,
            "avg_cost_bps": 4.0,
            "avg_entry_delay_ms": 0.0,
            "fill_backed_outcome_count": 3,
            "proxy_outcome_count": 0,
            "fill_backed_pct": 100.0,
        },
        "gap_decomposition": {
            "net_capture_gap_bps": 0.5,
            "gross_capture_gap_bps": 0.5,
            "cost_or_slippage_gap_bps": 0.0,
            "entry_delay_gap_ms": 120000.0,
        },
        "execution_gap_hypotheses": [
            {
                "kind": primary_hypothesis,
                "severity": "HIGH",
                "next_action": next_action,
            }
        ],
        "answers": {
            "authority_boundary_preserved": True,
            "execution_realism_gap_confirmed": (
                status == "EXECUTION_REALISM_GAP_DIAGNOSED_REPAIR_REQUIRED"
            ),
            "fill_backed_probe_execution_available": False,
            "cost_gate_or_operator_review_allowed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "next_actions": [next_action],
        "boundary": "artifact-only bounded demo-probe execution-realism review",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_bounded_probe_shadow_placement_impact_latest(
    data: Path,
    *,
    status: str = "SHADOW_PLACEMENT_TOUCHABILITY_IMPROVED_SAMPLE_MISMATCH",
    generated_at: str = "2026-06-21T18:04:55+00:00",
    candidate_matched_order_count: int = 0,
    candidate_matched_submit_count: int = 0,
) -> Path:
    path = (
        data
        / "cost_gate_learning_lane"
        / "bounded_probe_shadow_placement_impact_latest.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    next_actions = [
        "operator_review_mechanical_touchability_before_rust_patch",
        "collect_candidate_matched_bounded_demo_probe_evidence_after_authorization",
    ]
    if status == "SHADOW_PLACEMENT_TOUCHABILITY_REPAIR_EFFECTIVE_FOR_MATCHED_SAMPLE":
        next_actions = [
            "operator_review_existing_rust_authority_path_patch",
            "run_bounded_demo_probe_then_refresh_fill_lineage_and_execution_realism",
        ]
    payload = {
        "schema_version": "bounded_demo_probe_shadow_placement_impact_v1",
        "generated_at_utc": generated_at,
        "status": status,
        "reason": "fixture_bounded_probe_shadow_placement_impact",
        "candidate": {
            "strategy_name": "ma_crossover",
            "symbol": "ETHUSDT",
            "side": "Sell",
            "side_cell_key": "ma_crossover|ETHUSDT|Sell",
            "outcome_horizon_minutes": 240,
        },
        "shadow_summary": {
            "reviewed_order_count": 6,
            "shadow_submit_count": 6,
            "shadow_skip_count": 0,
            "candidate_matched_order_count": candidate_matched_order_count,
            "candidate_matched_submit_count": candidate_matched_submit_count,
            "future_bbo_would_cross_shadow_limit_count": 4,
            "status_counts": {"SHADOW_SUBMIT_NEAR_TOUCH": 6},
            "max_original_best_touch_gap_bps": 1530.6074,
            "max_shadow_initial_touch_gap_bps": 58.2092,
            "avg_shadow_initial_touch_gap_bps": 17.0489,
            "max_gap_reduction_bps": 1522.1026,
            "avg_gap_reduction_bps": 1200.0,
            "sample_scope": (
                "candidate_matched_runtime_sample"
                if candidate_matched_order_count
                else "current_demo_order_flow_not_candidate_matched"
            ),
        },
        "answers": {
            "shadow_placement_improves_touchability": True,
            "candidate_matched_runtime_sample_present": (
                candidate_matched_order_count > 0
            ),
            "candidate_specific_alpha_proof": False,
            "runtime_mutation_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "next_actions": next_actions,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_bounded_probe_operator_authorization_latest(
    data: Path,
    *,
    status: str = "READY_FOR_OPERATOR_AUTHORIZATION_REVIEW",
    generated_at: str = "2026-06-21T18:04:40+00:00",
) -> Path:
    path = (
        data
        / "cost_gate_learning_lane"
        / "bounded_probe_operator_authorization_latest.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "bounded_demo_probe_operator_authorization_packet_v1",
        "generated_at_utc": generated_at,
        "status": status,
        "reason": "defer",
        "decision": "defer",
        "review_scope": "operator_authorization_artifact_only_not_plan_mutation",
        "candidate": {
            "side_cell_key": "ma_crossover|ETHUSDT|Sell",
            "strategy_name": "ma_crossover",
            "symbol": "ETHUSDT",
            "side": "Sell",
            "outcome_horizon_minutes": 240,
        },
        "source_candidate_max_probe_orders": 3,
        "requested_max_authorized_probe_orders": None,
        "operator_authorization": None,
        "blocking_gate_count": 0,
        "blocking_gates": [],
        "next_actions": [
            "operator_may_authorize_bounded_demo_probe_with_exact_typed_confirm",
            "do_not_edit_plan_or_enable_writer_until_authorization_artifact_is_reviewed",
        ],
        "typed_confirm_expected": (
            "authorize_bounded_demo_probe:ma_crossover|ETHUSDT|Sell:0:"
        ),
        "typed_confirm_matches": False,
        "answers": {
            "ready_for_operator_authorization_review": (
                status == "READY_FOR_OPERATOR_AUTHORIZATION_REVIEW"
            ),
            "bounded_demo_probe_authorized": False,
            "operator_authorization_object_emitted": False,
            "plan_mutation_performed": False,
            "writer_enabled": False,
            "order_submission_performed": False,
            "runtime_mutation_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "promotion_evidence": False,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "probe_authority_granted_in_authorization_object": False,
            "order_authority_granted_in_authorization_object": False,
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_cost_gate_arm_uses_demo_learning_evidence_for_pg_reject_gap(tmp_path):
    data = tmp_path / "openclaw"
    artifact = _write_demo_learning_evidence_latest(
        data,
        status="PG_REJECTS_RECORDED_LEARNING_LANE_NOT_ACCUMULATING",
        reason="PG records Cost Gate rejects but runtime learning ledger is empty",
        next_action="enable_bounded_cost_gate_learning_lane_after_operator_review",
        cost_gate_rejects_recorded=True,
    )

    arm = collect_cost_gate_learning_lane_arm(
        data,
        now_utc=dt.datetime(2026, 6, 21, 18, 5, tzinfo=dt.timezone.utc),
    )
    plan = build_discovery_plan(
        [arm],
        now_utc=dt.datetime(2026, 6, 21, 18, 5, tzinfo=dt.timezone.utc),
    )

    assert arm["detail"]["demo_learning_evidence_source_path"] == str(artifact)
    assert arm["detail"]["demo_learning_evidence_status"] == (
        "PG_REJECTS_RECORDED_LEARNING_LANE_NOT_ACCUMULATING"
    )
    assert arm["detail"]["ledger_status"] == "MISSING"
    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    assert blocker["primary_blocker"] == (
        "demo_cost_gate_rejects_recorded_but_learning_lane_not_accumulating"
    )
    assert blocker["next_trigger"] == (
        "enable_bounded_cost_gate_learning_lane_after_operator_review"
    )
    assert blocker["demo_learning_evidence_cost_gate_rejects_recorded_in_pg"] is True
    assert blocker["demo_learning_evidence_risk_verdicts"] == 24155
    assert blocker["engineering_actionable"] is True


def test_cost_gate_arm_uses_demo_learning_stack_healthcheck_for_not_installed(tmp_path):
    data = tmp_path / "openclaw"
    artifact = _write_demo_learning_stack_healthcheck_latest(
        data,
        status="NOT_INSTALLED",
        reason="one_or_both_demo_learning_stack_crons_missing",
        next_action="install_stack_after_operator_source_reconcile",
    )

    now = dt.datetime(2026, 6, 21, 18, 5, tzinfo=dt.timezone.utc)
    arm = collect_cost_gate_learning_lane_arm(data, now_utc=now)
    plan = build_discovery_plan([arm], now_utc=now)

    assert arm["detail"]["demo_learning_stack_healthcheck_source_path"] == str(artifact)
    assert arm["detail"]["demo_learning_stack_healthcheck_status"] == "NOT_INSTALLED"
    assert arm["detail"]["demo_learning_stack_stack_installed"] is False
    assert (
        arm["detail"][
            "demo_learning_stack_sealed_horizon_probe_preflight_cron_entry_present"
        ]
        is False
    )
    assert arm["detail"]["demo_learning_stack_source_ready"] is True
    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    assert blocker["primary_blocker"] == "demo_learning_stack_not_installed"
    assert blocker["next_trigger"] == "install_stack_after_operator_source_reconcile"
    assert blocker["demo_learning_stack_healthcheck_status"] == "NOT_INSTALLED"
    assert blocker["demo_learning_stack_stack_installed"] is False
    assert blocker["demo_learning_stack_cost_gate_learning_ledger_rows_present"] is False
    assert blocker["engineering_actionable"] is True


def test_cost_gate_arm_uses_activation_packet_for_operator_dry_run(tmp_path):
    data = tmp_path / "openclaw"
    _write_demo_learning_stack_healthcheck_latest(
        data,
        status="NOT_INSTALLED",
        reason="one_or_more_demo_learning_stack_crons_missing",
        next_action="install_stack_after_operator_source_reconcile",
    )
    artifact = _write_demo_learning_stack_activation_packet_latest(
        data,
        status="READY_FOR_OPERATOR_DRY_RUN",
        reason="source_ready_but_one_or_more_stack_crons_missing",
        operator_next_action=(
            "run_dry_run_preview_then_apply_only_if_installer_preflight_passes"
        ),
    )

    now = dt.datetime(2026, 6, 21, 18, 5, tzinfo=dt.timezone.utc)
    arm = collect_cost_gate_learning_lane_arm(data, now_utc=now)
    plan = build_discovery_plan([arm], now_utc=now)

    assert arm["detail"]["demo_learning_stack_activation_packet_source_path"] == (
        str(artifact)
    )
    assert arm["detail"]["demo_learning_stack_activation_packet_status"] == (
        "READY_FOR_OPERATOR_DRY_RUN"
    )
    assert arm["detail"]["demo_learning_stack_activation_packet_missing_cron_count"] == 4
    assert arm["detail"][
        "demo_learning_stack_activation_packet_global_cost_gate_lowering_recommended"
    ] is False
    assert arm["detail"][
        "demo_learning_stack_activation_packet_order_authority_granted"
    ] is False
    assert arm["detail"][
        "demo_learning_stack_activation_packet_probe_authority_granted"
    ] is False

    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    assert blocker["primary_blocker"] == (
        "demo_learning_stack_activation_packet_ready_for_operator_dry_run"
    )
    assert blocker["next_trigger"] == (
        "run_dry_run_preview_then_apply_only_if_installer_preflight_passes"
    )
    assert blocker["demo_learning_stack_activation_packet_install_review_ready"] is True
    assert blocker["demo_learning_stack_activation_packet_missing_crons"] == [
        "demo_learning_evidence",
        "sealed_horizon_probe_preflight",
        "cost_gate_learning_lane",
        "demo_learning_stack_healthcheck",
    ]
    assert blocker[
        "demo_learning_stack_activation_packet_dry_run_preview_shell"
    ].startswith("OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=0")
    assert blocker[
        "demo_learning_stack_activation_packet_operator_only_apply_shell"
    ].startswith("OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=1")
    assert blocker[
        "demo_learning_stack_activation_packet_global_cost_gate_lowering_recommended"
    ] is False
    assert blocker[
        "demo_learning_stack_activation_packet_order_authority_granted"
    ] is False
    assert blocker[
        "demo_learning_stack_activation_packet_probe_authority_granted"
    ] is False

    task = plan["learning_worklist"]["top_task"]
    assert task["task_type"] == "cost_gate_learning_activation"
    assert task["learning_objective"] == (
        "review_demo_learning_stack_activation_packet_and_run_dry_run_"
        "before_any_cron_install"
    )
    assert task["requires_operator_authorization"] is True
    assert task["runtime_mutation_required"] is True
    assert task["evidence"]["demo_learning_stack_activation_packet_status"] == (
        "READY_FOR_OPERATOR_DRY_RUN"
    )
    assert task["evidence"][
        "demo_learning_stack_activation_packet_order_authority_granted"
    ] is False
    assert task["evidence"][
        "demo_learning_stack_activation_packet_probe_authority_granted"
    ] is False


def test_cost_gate_arm_uses_dry_run_review_after_activation_packet(tmp_path):
    data = tmp_path / "openclaw"
    _write_demo_learning_stack_activation_packet_latest(
        data,
        status="READY_FOR_OPERATOR_DRY_RUN",
        reason="source_ready_but_one_or_more_stack_crons_missing",
        operator_next_action=(
            "run_dry_run_preview_then_apply_only_if_installer_preflight_passes"
        ),
    )
    artifact = _write_demo_learning_stack_dry_run_review_latest(
        data,
        status="DRY_RUN_PREVIEW_PASSED_OPERATOR_APPLY_REVIEW_REQUIRED",
        reason="installer_dry_run_preview_passed_without_crontab_mutation",
        operator_next_action=(
            "operator_review_dry_run_preview_then_apply_learning_stack_if_accepted"
        ),
        passed=True,
    )

    now = dt.datetime(2026, 6, 21, 18, 5, tzinfo=dt.timezone.utc)
    arm = collect_cost_gate_learning_lane_arm(data, now_utc=now)
    plan = build_discovery_plan([arm], now_utc=now)

    assert arm["detail"]["demo_learning_stack_dry_run_review_source_path"] == (
        str(artifact)
    )
    assert arm["detail"]["demo_learning_stack_dry_run_review_status"] == (
        "DRY_RUN_PREVIEW_PASSED_OPERATOR_APPLY_REVIEW_REQUIRED"
    )
    assert arm["detail"][
        "demo_learning_stack_dry_run_review_dry_run_preview_passed"
    ] is True
    assert arm["detail"]["demo_learning_stack_dry_run_review_crontab_mutated"] is False
    assert arm["detail"][
        "demo_learning_stack_dry_run_review_global_cost_gate_lowering_recommended"
    ] is False
    assert arm["detail"][
        "demo_learning_stack_dry_run_review_order_authority_granted"
    ] is False
    assert arm["detail"][
        "demo_learning_stack_dry_run_review_probe_authority_granted"
    ] is False

    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    assert blocker["primary_blocker"] == (
        "demo_learning_stack_dry_run_preview_passed_operator_apply_review_required"
    )
    assert blocker["next_trigger"] == (
        "operator_review_dry_run_preview_then_apply_learning_stack_if_accepted"
    )
    assert blocker["operator_actionable"] is True
    assert blocker[
        "demo_learning_stack_dry_run_review_dry_run_preview_passed"
    ] is True
    assert blocker["demo_learning_stack_dry_run_review_forced_apply_gate"] == "0"
    assert blocker["demo_learning_stack_dry_run_review_mutates_crontab"] is False

    task = plan["learning_worklist"]["top_task"]
    assert task["task_type"] == "cost_gate_learning_activation"
    assert task["learning_objective"] == (
        "operator_review_learning_stack_dry_run_preview_before_cron_apply"
    )
    assert task["requires_operator_authorization"] is True
    assert task["runtime_mutation_required"] is True
    assert task["evidence"]["demo_learning_stack_dry_run_review_status"] == (
        "DRY_RUN_PREVIEW_PASSED_OPERATOR_APPLY_REVIEW_REQUIRED"
    )
    assert task["evidence"][
        "demo_learning_stack_dry_run_review_operator_apply_required"
    ] is True
    assert task["evidence"][
        "demo_learning_stack_dry_run_review_order_authority_granted"
    ] is False
    assert task["evidence"][
        "demo_learning_stack_dry_run_review_probe_authority_granted"
    ] is False


def test_cost_gate_blocked_review_candidate_supersedes_dry_run_apply_gate():
    now = dt.datetime(2026, 6, 21, 18, 10, tzinfo=dt.timezone.utc)
    arm = {
        "arm_id": "cost_gate_demo_learning_lane",
        "gate_status": "OPERATOR_REVIEW",
        "sample_count": 2,
        "artifacts_ready": False,
        "source_ok": True,
        "source_path": (
            "/tmp/openclaw/cost_gate_learning_lane/"
            "demo_learning_lane_plan_latest.json"
        ),
        "detail": {
            "plan_status": "READY_FOR_DEMO_LEARNING_PROBE",
            "main_cost_gate_adjustment": "NONE",
            "order_authority": "NOT_GRANTED",
            "selected_probe_candidate_count": 2,
            "blocked_signal_outcome_count": 22419,
            "blocked_signal_positive_outcome_count": 14117,
            "blocked_signal_net_positive_pct": 62.9698,
            "blocked_signal_outcome_review_schema_version": (
                "cost_gate_demo_learning_lane_blocked_outcome_review_v2"
            ),
            "blocked_signal_outcome_review_status": (
                "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT"
            ),
            "blocked_signal_outcome_review_reason": (
                "one_or_more_blocked_side_cells_clear_review_thresholds"
            ),
            "blocked_signal_outcome_review_next_trigger": (
                "operator_review_blocked_outcome_scorecard_before_demo_probe_authority"
            ),
            "blocked_signal_top_review_candidate_side_cell_key": (
                "ma_crossover|ETHUSDT|Sell"
            ),
            "blocked_signal_top_review_candidate_wrongful_block_score": (
                75.49272112494981
            ),
            "blocked_signal_top_review_candidate_net_cost_cushion_bps": (
                37.746360562474905
            ),
            "learning_loop_last_scorecard_horizon_stability_status": (
                "SINGLE_HORIZON_ONLY"
            ),
            "learning_loop_last_scorecard_horizon_stability_horizons": [
                60,
            ],
            "profit_learning_counterfactual_horizon_stability_status": (
                "MULTI_HORIZON_PROFIT_LEARNING_CANDIDATES_PRESENT"
            ),
            "profit_learning_top_side_cells": [
                {
                    "candidate_key": "ma_crossover|ETHUSDT|Sell",
                    "horizon_status": "CANDIDATE_MULTI_HORIZON_STABLE",
                    "candidate_horizons_minutes": [15, 30, 60, 120, 240],
                    "best_horizon_minutes": 120,
                    "current_edge_bps": 121.1121,
                }
            ],
            "demo_learning_stack_dry_run_review_present": True,
            "demo_learning_stack_dry_run_review_source_ok": True,
            "demo_learning_stack_dry_run_review_status": (
                "DRY_RUN_PREVIEW_PASSED_OPERATOR_APPLY_REVIEW_REQUIRED"
            ),
            "demo_learning_stack_dry_run_review_dry_run_preview_passed": True,
            "demo_learning_stack_dry_run_review_crontab_mutated": False,
            "demo_learning_stack_dry_run_review_order_authority_granted": False,
            "demo_learning_stack_dry_run_review_probe_authority_granted": False,
            "demo_learning_stack_dry_run_review_global_cost_gate_lowering_recommended": (
                False
            ),
        },
    }

    plan = build_discovery_plan([arm], now_utc=now)

    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    assert blocker["primary_blocker"] == (
        "cost_gate_blocked_signal_outcomes_need_demo_probe_authority_review"
    )
    assert blocker["next_trigger"] == (
        "operator_review_blocked_outcome_scorecard_before_demo_probe_authority"
    )
    assert blocker["operator_actionable"] is True
    assert blocker["blocked_signal_top_review_candidate_side_cell_key"] == (
        "ma_crossover|ETHUSDT|Sell"
    )
    assert blocker["demo_learning_stack_dry_run_review_status"] == (
        "DRY_RUN_PREVIEW_PASSED_OPERATOR_APPLY_REVIEW_REQUIRED"
    )
    assert blocker["demo_learning_stack_dry_run_review_order_authority_granted"] is False
    assert blocker["demo_learning_stack_dry_run_review_probe_authority_granted"] is False

    task = plan["learning_worklist"]["top_task"]
    assert task["task_type"] == "operator_probe_review"
    assert task["learning_objective"] == (
        "operator_review_multi_horizon_blocked_signal_side_cell_before_bounded_demo_probe"
    )
    assert task["requires_operator_authorization"] is True
    assert task["runtime_mutation_required"] is False
    assert task["evidence"]["blocked_signal_top_review_candidate_side_cell_key"] == (
        "ma_crossover|ETHUSDT|Sell"
    )
    assert task["evidence"][
        "learning_loop_last_scorecard_horizon_stability_status"
    ] == "SINGLE_HORIZON_ONLY"
    assert task["evidence"][
        "profit_learning_counterfactual_horizon_stability_status"
    ] == "MULTI_HORIZON_PROFIT_LEARNING_CANDIDATES_PRESENT"
    assert task["evidence"]["profit_learning_top_side_cells"][0][
        "best_horizon_minutes"
    ] == 120
    assert task["evidence"][
        "demo_learning_stack_dry_run_review_order_authority_granted"
    ] is False
    assert task["evidence"][
        "demo_learning_stack_dry_run_review_probe_authority_granted"
    ] is False


def test_cost_gate_arm_uses_stack_healthcheck_for_missing_bounded_reviews(tmp_path):
    data = tmp_path / "openclaw"
    artifact = _write_demo_learning_stack_healthcheck_latest(
        data,
        status="BOUNDED_PROBE_REVIEW_ARTIFACTS_MISSING",
        reason="bounded_probe_result_or_execution_realism_review_latest_missing_or_unreadable",
        next_action="rerun_cost_gate_learning_lane_cron_after_sealed_preflight_refresh",
        stack_installed=True,
        demo_cron_entry_present=True,
        sealed_preflight_cron_entry_present=True,
        cost_cron_entry_present=True,
        healthcheck_cron_entry_present=True,
        heartbeats_recent=True,
        demo_heartbeat_recent=True,
        sealed_preflight_heartbeat_recent=True,
        cost_heartbeat_recent=True,
        statuses_recent=True,
        demo_status_recent=True,
        sealed_preflight_status_recent=True,
        cost_status_recent=True,
        latest_artifacts_present=True,
        sealed_preflight_present=True,
        bounded_reviews_present=False,
        bounded_result_review_present=False,
        bounded_execution_realism_review_present=True,
        ledger_rows_present=True,
        blocked_outcomes_present=True,
    )

    now = dt.datetime(2026, 6, 21, 18, 5, tzinfo=dt.timezone.utc)
    arm = collect_cost_gate_learning_lane_arm(data, now_utc=now)
    plan = build_discovery_plan([arm], now_utc=now)

    assert arm["detail"]["demo_learning_stack_healthcheck_source_path"] == str(artifact)
    assert arm["detail"]["demo_learning_stack_bounded_probe_reviews_present"] is False
    assert arm["detail"]["demo_learning_stack_bounded_probe_result_review_present"] is False
    assert (
        arm["detail"][
            "demo_learning_stack_sealed_horizon_probe_preflight_cron_entry_present"
        ]
        is True
    )
    assert (
        arm["detail"][
            "demo_learning_stack_sealed_horizon_probe_preflight_heartbeat_recent"
        ]
        is True
    )
    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    assert blocker["primary_blocker"] == (
        "bounded_probe_review_artifacts_missing_for_learning_stack"
    )
    assert blocker["next_trigger"] == (
        "rerun_cost_gate_learning_lane_cron_after_sealed_preflight_refresh"
    )
    assert blocker["demo_learning_stack_bounded_probe_reviews_present"] is False
    assert (
        blocker[
            "demo_learning_stack_sealed_horizon_probe_preflight_cron_entry_present"
        ]
        is True
    )
    assert blocker["demo_learning_stack_blocked_signal_outcomes_present"] is True
    assert blocker["engineering_actionable"] is True


def test_cost_gate_arm_surfaces_fresh_reject_wall_without_order_flow(tmp_path):
    data = tmp_path / "openclaw"
    _write_demo_learning_evidence_latest(
        data,
        status="PG_REJECTS_RECORDED_LEARNING_LANE_NOT_ACCUMULATING",
        reason="PG records Cost Gate rejects but runtime learning ledger is empty",
        next_action="enable_bounded_cost_gate_learning_lane_after_operator_review",
        cost_gate_rejects_recorded=True,
        order_flow_starved=True,
    )

    now = dt.datetime(2026, 6, 21, 18, 5, tzinfo=dt.timezone.utc)
    arm = collect_cost_gate_learning_lane_arm(data, now_utc=now)
    plan = build_discovery_plan([arm], now_utc=now)

    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    assert blocker["primary_blocker"] == (
        "demo_cost_gate_reject_wall_no_order_flow_evidence"
    )
    assert blocker["next_trigger"] == (
        "activate_cost_gate_learning_lane_then_operator_review_bounded_demo_probe"
    )
    assert blocker["demo_learning_evidence_order_flow_evidence_status"] == (
        "COST_GATE_REJECT_WALL_NO_ORDER_FLOW_EVIDENCE"
    )
    assert blocker["demo_learning_evidence_order_flow_evidence_starved"] is True
    assert blocker[
        "demo_learning_evidence_cost_gate_adjustment_recommendation_status"
    ] == "BOUNDED_LEARNING_LANE_ACTIVATION_RECOMMENDED"
    assert blocker["demo_learning_evidence_cost_gate_learning_gate_adjustment"] == (
        "ENABLE_LEDGER_AND_OUTCOME_REVIEW_FIRST"
    )
    assert blocker["engineering_actionable"] is True


def test_cost_gate_arm_surfaces_source_sync_recommendation_before_learning_lane(tmp_path):
    data = tmp_path / "openclaw"
    _write_demo_learning_evidence_latest(
        data,
        status="RUNTIME_PREFLIGHT_BLOCKS_COST_GATE_LEARNING_ADJUSTMENT",
        reason="runtime source checkout is not activation-ready",
        next_action=(
            "sync_runtime_source_to_expected_head_before_cost_gate_learning_activation"
        ),
        cost_gate_rejects_recorded=True,
        order_flow_starved=True,
        recommendation_status="RUNTIME_SOURCE_SYNC_REQUIRED_BEFORE_COST_GATE_CHANGE",
        recommendation_next_action=(
            "sync_runtime_source_to_expected_head_before_cost_gate_learning_activation"
        ),
        learning_gate_adjustment="NONE_SYNC_RUNTIME_SOURCE_FIRST",
        runtime_preflight_blocking=True,
        runtime_source_activation_ready=False,
        runtime_source_activation_status="DIRTY_OR_BEHIND",
        runtime_activation_blockers=["source_checkout_not_synced_clean"],
    )

    now = dt.datetime(2026, 6, 21, 18, 5, tzinfo=dt.timezone.utc)
    arm = collect_cost_gate_learning_lane_arm(data, now_utc=now)
    plan = build_discovery_plan([arm], now_utc=now)

    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    assert blocker["primary_blocker"] == (
        "demo_cost_gate_reject_wall_no_order_flow_evidence"
    )
    assert blocker["next_trigger"] == (
        "sync_runtime_source_to_expected_head_before_cost_gate_learning_activation"
    )
    assert blocker[
        "demo_learning_evidence_cost_gate_adjustment_recommendation_status"
    ] == "RUNTIME_SOURCE_SYNC_REQUIRED_BEFORE_COST_GATE_CHANGE"
    assert blocker[
        "demo_learning_evidence_cost_gate_adjustment_runtime_preflight_blocking"
    ] is True
    assert blocker[
        "demo_learning_evidence_cost_gate_adjustment_runtime_source_activation_ready"
    ] is False
    assert blocker[
        "demo_learning_evidence_cost_gate_adjustment_runtime_activation_blockers"
    ] == ["source_checkout_not_synced_clean"]
    assert blocker["demo_learning_evidence_cost_gate_learning_gate_adjustment"] == (
        "NONE_SYNC_RUNTIME_SOURCE_FIRST"
    )


def test_cost_gate_arm_keeps_observation_only_demo_from_probe_readiness(tmp_path):
    data = tmp_path / "openclaw"
    _write_demo_learning_evidence_latest(
        data,
        status="OBSERVATION_TELEMETRY_ACTIVE_NO_ACTIONABLE_LEDGER",
        reason="demo signal observation telemetry is active but no reject evidence exists",
        next_action="wait_for_candidate_rejects_or_verify_strategy_candidate_producer",
        observation_only=True,
    )

    arm = collect_cost_gate_learning_lane_arm(
        data,
        now_utc=dt.datetime(2026, 6, 21, 18, 5, tzinfo=dt.timezone.utc),
    )
    plan = build_discovery_plan(
        [arm],
        now_utc=dt.datetime(2026, 6, 21, 18, 5, tzinfo=dt.timezone.utc),
    )

    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    assert blocker["blocker_class"] == "data_coverage"
    assert blocker["primary_blocker"] == (
        "demo_observation_telemetry_active_no_actionable_reject_evidence"
    )
    assert blocker["next_trigger"] == (
        "wait_for_candidate_rejects_or_verify_strategy_candidate_producer"
    )
    assert blocker["demo_learning_evidence_observation_only_contexts_active"] is True


def test_cost_gate_arm_blocks_stale_demo_learning_data_flow(tmp_path):
    data = tmp_path / "openclaw"
    _write_demo_learning_evidence_latest(
        data,
        status="DEMO_LEARNING_DATA_FLOW_STALE",
        generated_at="2026-06-21T23:09:00+00:00",
        reason="latest candidate/reject/order-flow timestamp is stale",
        next_action="restore_demo_data_flow_before_cost_gate_learning_activation",
        cost_gate_rejects_recorded=True,
        learning_data_flow_stale=True,
    )

    now = dt.datetime(2026, 6, 21, 23, 10, tzinfo=dt.timezone.utc)
    arm = collect_cost_gate_learning_lane_arm(
        data,
        now_utc=now,
    )
    plan = build_discovery_plan(
        [arm],
        now_utc=now,
    )

    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    assert blocker["action"] == "WAIT"
    assert blocker["primary_blocker"] == "demo_learning_data_flow_stale"
    assert blocker["next_trigger"] == (
        "restore_demo_data_flow_before_cost_gate_learning_activation"
    )
    assert blocker["demo_learning_evidence_data_flow_freshness_status"] == (
        "LEARNING_DATA_FLOW_STALE"
    )
    assert blocker["demo_learning_evidence_latest_learning_age_seconds"] == 8461
    assert blocker["engineering_actionable"] is True


def test_cost_gate_arm_uses_profit_learning_packet_for_counterfactual_gap(tmp_path):
    data = tmp_path / "openclaw"
    artifact = _write_profit_learning_decision_packet_latest(
        data,
        status="RUN_REJECT_COUNTERFACTUAL",
        reason="cost_gate_rejects_are_recorded_but_counterfactual_scorecard_missing",
        next_actions=["run_cost_gate_reject_counterfactual_multi_horizon_scorecard"],
    )

    now = dt.datetime(2026, 6, 21, 18, 5, tzinfo=dt.timezone.utc)
    arm = collect_cost_gate_learning_lane_arm(data, now_utc=now)
    plan = build_discovery_plan([arm], now_utc=now)

    assert arm["detail"]["profit_learning_decision_packet_source_path"] == str(artifact)
    assert arm["detail"]["profit_learning_decision_packet_status"] == (
        "RUN_REJECT_COUNTERFACTUAL"
    )
    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    assert blocker["primary_blocker"] == (
        "profit_learning_reject_counterfactual_required"
    )
    assert blocker["next_trigger"] == (
        "run_cost_gate_reject_counterfactual_multi_horizon_scorecard"
    )
    assert blocker["profit_learning_cost_gate_rejects_recorded"] is True
    assert blocker["profit_learning_silent_drop_risk"] is False
    assert blocker["profit_learning_order_authority_granted"] is False
    assert blocker["profit_learning_main_cost_gate_adjustment"] == "NONE"


def test_cost_gate_profit_packet_probe_candidate_reaches_worklist(tmp_path):
    data = tmp_path / "openclaw"
    _write_profit_learning_decision_packet_latest(
        data,
        status="OPERATOR_REVIEW_DEMO_PROBE_CANDIDATES",
        reason="blocked_signal_outcomes_clear_review_thresholds",
        next_actions=[
            "operator_review_blocked_outcome_scorecard_before_probe_authority"
        ],
        review_candidate=True,
    )

    now = dt.datetime(2026, 6, 21, 18, 5, tzinfo=dt.timezone.utc)
    arm = collect_cost_gate_learning_lane_arm(data, now_utc=now)
    plan = build_discovery_plan([arm], now_utc=now)
    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    worklist = plan["learning_worklist"]
    task = worklist["top_task"]

    assert blocker["blocker_class"] == "probe_ready"
    assert blocker["primary_blocker"] == (
        "profit_learning_demo_probe_candidates_need_operator_review"
    )
    assert blocker["operator_actionable"] is True
    assert blocker["profit_learning_blocked_outcome_review_candidates_present"] is True
    assert blocker["profit_learning_top_side_cells"][0]["side_cell_key"] == (
        "ma_crossover|ETHUSDT|Sell"
    )
    assert worklist["status"] == "OPERATOR_GATED_LEARNING_READY"
    assert task["task_type"] == "operator_probe_review"
    assert task["learning_objective"] == (
        "operator_review_profit_learning_decision_packet_before_bounded_demo_probe"
    )
    assert task["requires_operator_authorization"] is True
    assert task["runtime_mutation_required"] is False
    assert task["evidence"]["profit_learning_decision_packet_status"] == (
        "OPERATOR_REVIEW_DEMO_PROBE_CANDIDATES"
    )
    assert task["evidence"]["profit_learning_top_side_cells"][0]["side_cell_key"] == (
        "ma_crossover|ETHUSDT|Sell"
    )
    assert task["evidence"]["profit_learning_order_authority_granted"] is False


def test_cost_gate_profitability_path_scorecard_reaches_learning_surfaces(tmp_path):
    data = tmp_path / "openclaw"
    artifact = _write_profitability_path_scorecard_latest(data)
    review_artifact = _write_sealed_horizon_operator_review_latest(data)
    _write_profit_learning_decision_packet_latest(
        data,
        status="RUN_REJECT_COUNTERFACTUAL",
        reason="cost_gate_rejects_are_recorded_but_counterfactual_scorecard_missing",
        next_actions=["run_cost_gate_reject_counterfactual_multi_horizon_scorecard"],
    )

    now = dt.datetime(2026, 6, 21, 18, 5, tzinfo=dt.timezone.utc)
    arm = collect_cost_gate_learning_lane_arm(data, now_utc=now)
    plan = build_discovery_plan([arm], now_utc=now)
    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    task = plan["learning_worklist"]["top_task"]

    assert arm["detail"]["profitability_path_scorecard_source_path"] == str(artifact)
    assert arm["detail"]["profitability_path_scorecard_status"] == (
        "PROFITABILITY_PATHS_PRESENT_BUT_EXECUTION_EVIDENCE_MISSING"
    )
    assert arm["detail"]["sealed_horizon_operator_review_source_path"] == str(
        review_artifact
    )
    assert arm["detail"]["sealed_horizon_operator_review_status"] == (
        "PENDING_OPERATOR_REVIEW"
    )
    assert arm["detail"]["sealed_horizon_operator_review_decision"] == "defer"
    assert arm["detail"]["sealed_horizon_operator_review_approved"] is False
    assert arm["detail"][
        "sealed_horizon_operator_review_review_grants_runtime_authority"
    ] is False
    assert arm["detail"]["sealed_horizon_operator_review_order_authority_granted"] is False
    assert arm["detail"]["profitability_engineering_closure_status"] == (
        "COST_GATE_ESCAPE_PREFLIGHT_BLOCKED_BY_OPERATOR_REVIEW"
    )
    assert arm["detail"]["profitability_global_cost_gate_lowering_recommended"] is False
    assert arm["detail"]["profitability_order_authority_granted"] is False
    assert arm["detail"]["profitability_promotion_evidence"] is False
    assert arm["detail"]["profitability_next_move_recommended_action"] == (
        "operator_review_sealed_horizon_probe_preflight"
    )
    assert arm["detail"]["profitability_next_move_edge_above_cost_bps"] == 5.0
    assert (
        arm["detail"]["profitability_next_move_runtime_mutation_required"] is False
    )
    assert arm["detail"]["profitability_primary_cost_gate_root_blocker"]["gate"] == (
        "operator_sealed_horizon_review_recorded"
    )

    assert blocker["profitability_leading_candidate_key"] == (
        "ma_crossover|BTCUSDT|Sell"
    )
    assert blocker["profitability_proof_gate_count_remaining"] == 1
    assert blocker["profitability_global_cost_gate_lowering_recommended"] is False
    assert blocker["profitability_cost_gate_escape_order_authority_granted"] is False
    assert blocker["profitability_cost_gate_escape_probe_authority_granted"] is False
    assert blocker["profitability_cost_gate_escape_promotion_evidence"] is False
    assert blocker[
        "profitability_cost_gate_escape_operator_authorization_status"
    ] == "SEALED_HORIZON_PREFLIGHT_NOT_READY"
    assert blocker[
        "profitability_cost_gate_escape_operator_authorization_object_emitted"
    ] is False
    assert blocker["profitability_next_move_recommended_action"] == (
        "operator_review_sealed_horizon_probe_preflight"
    )
    assert blocker["profitability_next_move_runtime_mutation_required"] is False
    assert blocker["profitability_edge_amplification_backlog"][0][
        "edge_above_cost_bps"
    ] == 5.0

    assert task["evidence"]["profitability_engineering_closure_status"] == (
        "COST_GATE_ESCAPE_PREFLIGHT_BLOCKED_BY_OPERATOR_REVIEW"
    )
    assert task["evidence"]["profitability_leading_candidate_key"] == (
        "ma_crossover|BTCUSDT|Sell"
    )
    assert task["evidence"]["profitability_next_actions"][0] == (
        "operator_review_sealed_horizon_probe_preflight"
    )
    assert task["evidence"]["profitability_order_authority_granted"] is False
    assert task["evidence"][
        "profitability_cost_gate_escape_operator_authorization_status"
    ] == "SEALED_HORIZON_PREFLIGHT_NOT_READY"
    assert task["evidence"]["profitability_next_move_recommended_action"] == (
        "operator_review_sealed_horizon_probe_preflight"
    )
    assert (
        task["evidence"]["profitability_next_move_runtime_mutation_required"] is False
    )


def test_runtime_killboard_mirrors_profitability_closure(tmp_path):
    data = tmp_path / "openclaw"
    repo = _init_clean_source_repo_with_origin(tmp_path)
    _write_profitability_path_scorecard_latest(data)
    _write_sealed_horizon_operator_review_latest(data)
    _write_profit_learning_decision_packet_latest(
        data,
        status="RUN_REJECT_COUNTERFACTUAL",
        reason="cost_gate_rejects_are_recorded_but_counterfactual_scorecard_missing",
        next_actions=["run_cost_gate_reject_counterfactual_multi_horizon_scorecard"],
    )

    killboard = build_runtime_killboard(
        data_dir=data,
        repo_root=repo,
        now_utc=dt.datetime(2026, 6, 21, 18, 5, tzinfo=dt.timezone.utc),
    )

    kb = killboard["killboard"]
    assert kb["profitability_path_scorecard_status"] == (
        "PROFITABILITY_PATHS_PRESENT_BUT_EXECUTION_EVIDENCE_MISSING"
    )
    assert kb["profitability_engineering_closure_status"] == (
        "COST_GATE_ESCAPE_PREFLIGHT_BLOCKED_BY_OPERATOR_REVIEW"
    )
    assert kb["profitability_leading_candidate_key"] == (
        "ma_crossover|BTCUSDT|Sell"
    )
    assert kb["profitability_proof_gate_count_remaining"] == 1
    assert kb["profitability_global_cost_gate_lowering_recommended"] is False
    assert kb["profitability_order_authority_granted"] is False
    assert kb["profitability_promotion_evidence"] is False
    assert kb[
        "profitability_cost_gate_escape_operator_authorization_status"
    ] == "SEALED_HORIZON_PREFLIGHT_NOT_READY"
    assert kb[
        "profitability_cost_gate_escape_operator_authorization_object_emitted"
    ] is False
    assert kb["profitability_next_move_recommended_action"] == (
        "operator_review_sealed_horizon_probe_preflight"
    )
    assert kb["profitability_next_move_candidate_key"] == "ma_crossover|BTCUSDT|Sell"
    assert kb["profitability_next_move_edge_above_cost_bps"] == 5.0
    assert kb["profitability_next_move_runtime_mutation_required"] is False
    assert kb["sealed_horizon_operator_review_status"] == "PENDING_OPERATOR_REVIEW"
    assert kb["sealed_horizon_operator_review_decision"] == "defer"
    assert kb["sealed_horizon_operator_review_approved"] is False
    assert kb["sealed_horizon_operator_review_review_grants_runtime_authority"] is False
    assert kb["sealed_horizon_operator_review_order_authority_granted"] is False


def test_runtime_killboard_carries_profitability_runtime_mutation_required(tmp_path):
    data = tmp_path / "openclaw"
    repo = _init_clean_source_repo_with_origin(tmp_path)
    artifact = _write_profitability_path_scorecard_latest(
        data,
        next_move_runtime_mutation_required=True,
    )
    _write_demo_learning_stack_activation_packet_latest(
        data,
        status="READY_FOR_OPERATOR_DRY_RUN",
        reason="source_ready_but_one_or_more_stack_crons_missing",
        operator_next_action=(
            "run_dry_run_preview_then_apply_only_if_installer_preflight_passes"
        ),
    )
    _write_demo_learning_stack_dry_run_review_latest(
        data,
        status="DRY_RUN_PREVIEW_PASSED_OPERATOR_APPLY_REVIEW_REQUIRED",
        reason="installer_dry_run_preview_passed_without_crontab_mutation",
        operator_next_action=(
            "operator_review_dry_run_preview_then_apply_learning_stack_if_accepted"
        ),
    )
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    root_blocker = {
        "source": "demo_learning_stack_dry_run_review",
        "gate": "demo_learning_stack_operator_apply_required",
        "status": "DRY_RUN_PREVIEW_PASSED_OPERATOR_APPLY_REVIEW_REQUIRED",
        "reason": "installer_dry_run_preview_passed_without_crontab_mutation",
        "next_action": (
            "operator_review_dry_run_preview_then_apply_learning_stack_if_accepted"
        ),
        "runtime_mutation_required": True,
    }
    closure = payload["profitability_engineering_closure"]
    closure["status"] = "DEMO_LEARNING_STACK_ACTIVATION_REQUIRED"
    closure["cost_gate_root_blockers"] = [root_blocker]
    closure["primary_cost_gate_root_blocker"] = root_blocker
    closure["profitability_next_move"]["status"] = (
        "DEMO_LEARNING_STACK_ACTIVATION_REQUIRED"
    )
    closure["profitability_next_move"]["move_class"] = (
        "activate_sustainable_demo_learning_stack"
    )
    closure["profitability_next_move"]["recommended_action"] = (
        "operator_review_dry_run_preview_then_apply_learning_stack_if_accepted"
    )
    operator_next_move = payload["operator_read"]["profitability_next_move"]
    operator_next_move["status"] = "DEMO_LEARNING_STACK_ACTIVATION_REQUIRED"
    operator_next_move["move_class"] = "activate_sustainable_demo_learning_stack"
    operator_next_move["recommended_action"] = (
        "operator_review_dry_run_preview_then_apply_learning_stack_if_accepted"
    )
    artifact.write_text(json.dumps(payload), encoding="utf-8")

    killboard = build_runtime_killboard(
        data_dir=data,
        repo_root=repo,
        now_utc=dt.datetime(2026, 6, 21, 18, 5, tzinfo=dt.timezone.utc),
    )

    kb = killboard["killboard"]
    tasks = {
        row["arm_id"]: row
        for row in killboard["learning_worklist"]["tasks"]
    }
    task = tasks["cost_gate_demo_learning_lane"]

    assert kb["profitability_next_move_runtime_mutation_required"] is True
    assert kb["top_learning_task_side_effect_boundary"] == (
        "recommendation_only_operator_runtime_mutation_required_"
        "no_order_or_probe_authority"
    )
    assert kb["top_learning_task_next_trigger"] == (
        "operator_review_dry_run_preview_then_apply_learning_stack_if_accepted"
    )
    assert kb["top_learning_task_primary_blocker"] == (
        "demo_learning_stack_operator_apply_required"
    )
    assert kb["top_learning_task_operator_next_action"] == (
        "operator_review_dry_run_preview_then_apply_learning_stack_if_accepted"
    )
    assert "OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=0" in (
        kb["top_learning_task_dry_run_preview_shell"]
    )
    assert "OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=1" in (
        kb["top_learning_task_operator_only_apply_shell"]
    )
    assert "--remove" in kb["top_learning_task_operator_only_rollback_shell"]
    assert "demo_learning_stack_healthcheck.py" in (
        kb["top_learning_task_post_install_verification_shell"]
    )
    assert kb["top_learning_task_missing_cron_count"] == 4
    assert kb["top_learning_task_missing_crons"] == [
        "demo_learning_evidence",
        "sealed_horizon_probe_preflight",
        "cost_gate_learning_lane",
        "demo_learning_stack_healthcheck",
    ]
    assert kb["top_learning_task_global_cost_gate_lowering_recommended"] is False
    assert kb["top_learning_task_order_authority_granted"] is False
    assert kb["top_learning_task_probe_authority_granted"] is False
    assert task["task_type"] == "cost_gate_learning_activation"
    assert task["primary_blocker"] == "demo_learning_stack_operator_apply_required"
    assert task["requires_operator_authorization"] is True
    assert task["runtime_mutation_required"] is True
    assert task["side_effect_boundary"] == (
        "recommendation_only_operator_runtime_mutation_required_"
        "no_order_or_probe_authority"
    )
    assert (
        task["evidence"]["profitability_next_move_runtime_mutation_required"] is True
    )


def test_cost_gate_profit_packet_sealed_horizon_candidate_reaches_worklist(tmp_path):
    data = tmp_path / "openclaw"
    _write_profit_learning_decision_packet_latest(
        data,
        status="OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE",
        reason=(
            "sealed_horizon_learning_evidence_clears_review_thresholds;"
            "production_learning_lane_activation_still_requires_operator_control"
        ),
        next_actions=[
            "operator_review_sealed_horizon_learning_evidence_before_bounded_demo_probe",
            "activate_or_repair_cost_gate_learning_lane_stack_before_runtime_probe",
        ],
        sealed_horizon_candidate=True,
    )

    now = dt.datetime(2026, 6, 21, 18, 5, tzinfo=dt.timezone.utc)
    arm = collect_cost_gate_learning_lane_arm(data, now_utc=now)
    plan = build_discovery_plan([arm], now_utc=now)
    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    task = plan["learning_worklist"]["top_task"]

    assert blocker["blocker_class"] == "probe_ready"
    assert blocker["primary_blocker"] == (
        "profit_learning_sealed_horizon_demo_probe_candidate_needs_operator_review"
    )
    assert blocker["operator_actionable"] is True
    assert blocker["profit_learning_sealed_horizon_learning_evidence_candidates_present"] is True
    assert blocker["profit_learning_sealed_horizon_side_cell_key"] == (
        "ma_crossover|ETHUSDT|Sell"
    )
    assert blocker["profit_learning_sealed_horizon_outcome_horizon_minutes"] == 240
    assert blocker["profit_learning_sealed_horizon_avg_net_bps"] == 3.0511
    assert blocker["profit_learning_order_authority_granted"] is False
    assert blocker["profit_learning_main_cost_gate_adjustment"] == "NONE"

    assert plan["learning_worklist"]["status"] == "OPERATOR_GATED_LEARNING_READY"
    assert task["task_type"] == "operator_probe_review"
    assert task["learning_objective"] == (
        "operator_review_sealed_horizon_learning_evidence_before_bounded_demo_probe"
    )
    assert task["requires_operator_authorization"] is True
    assert task["runtime_mutation_required"] is False
    assert task["evidence"]["profit_learning_decision_packet_status"] == (
        "OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE"
    )
    assert task["evidence"]["profit_learning_sealed_horizon_review_ready"] is True
    assert task["evidence"]["profit_learning_sealed_horizon_avg_net_bps"] == 3.0511
    assert task["evidence"]["profit_learning_order_authority_granted"] is False


def test_cost_gate_sealed_horizon_probe_preflight_supersedes_packet(tmp_path):
    data = tmp_path / "openclaw"
    _write_profit_learning_decision_packet_latest(
        data,
        status="OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE",
        reason="sealed_horizon_learning_evidence_clears_review_thresholds",
        next_actions=[
            "operator_review_sealed_horizon_learning_evidence_before_bounded_demo_probe"
        ],
        sealed_horizon_candidate=True,
    )
    _write_sealed_horizon_probe_preflight_latest(data)

    now = dt.datetime(2026, 6, 21, 18, 5, tzinfo=dt.timezone.utc)
    arm = collect_cost_gate_learning_lane_arm(data, now_utc=now)
    plan = build_discovery_plan([arm], now_utc=now)
    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    task = plan["learning_worklist"]["top_task"]

    assert blocker["blocker_class"] == "probe_ready"
    assert blocker["primary_blocker"] == (
        "sealed_horizon_probe_preflight_requires_operator_review_and_learning_lane"
    )
    assert blocker["sealed_horizon_probe_preflight_status"] == (
        "OPERATOR_REVIEW_AND_PRODUCTION_LEARNING_LANE_REQUIRED"
    )
    assert blocker["sealed_horizon_probe_preflight_blocking_gates"] == [
        "operator_sealed_horizon_review_recorded",
        "production_learning_lane_accumulating",
    ]
    assert blocker["sealed_horizon_probe_preflight_order_authority_granted"] is False
    assert blocker["sealed_horizon_probe_preflight_probe_authority_granted"] is False
    assert blocker["sealed_horizon_probe_preflight_main_cost_gate_adjustment"] == "NONE"

    assert task["learning_objective"] == (
        "operator_review_sealed_horizon_preflight_and_activate_production_learning_lane"
    )
    assert task["evidence"]["sealed_horizon_probe_preflight_operator_review_recorded"] is False
    assert task["evidence"][
        "sealed_horizon_probe_preflight_production_lane_accumulating"
    ] is False
    assert task["evidence"]["sealed_horizon_probe_preflight_blocking_gate_count"] == 2


def test_bounded_probe_operator_authorization_packet_drives_operator_review(tmp_path):
    data = tmp_path / "openclaw"
    _write_profit_learning_decision_packet_latest(
        data,
        status="OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE",
        reason="sealed_horizon_learning_evidence_clears_review_thresholds",
        next_actions=[
            "operator_review_sealed_horizon_learning_evidence_before_bounded_demo_probe"
        ],
        sealed_horizon_candidate=True,
    )
    _write_sealed_horizon_probe_preflight_latest(
        data,
        status="READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION",
    )
    _write_bounded_probe_operator_authorization_latest(data)

    now = dt.datetime(2026, 6, 21, 18, 5, tzinfo=dt.timezone.utc)
    arm = collect_cost_gate_learning_lane_arm(data, now_utc=now)
    plan = build_discovery_plan([arm], now_utc=now)
    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    task = plan["learning_worklist"]["top_task"]

    assert arm["detail"]["bounded_probe_operator_authorization_present"] is True
    assert arm["detail"]["bounded_probe_operator_authorization_status"] == (
        "READY_FOR_OPERATOR_AUTHORIZATION_REVIEW"
    )
    assert arm["detail"]["bounded_probe_operator_authorization_object_emitted"] is False
    assert (
        arm["detail"][
            "bounded_probe_operator_authorization_active_runtime_order_authority"
        ]
        is False
    )

    assert blocker["blocker_class"] == "probe_ready"
    assert blocker["primary_blocker"] == (
        "bounded_probe_operator_authorization_ready_for_operator_review"
    )
    assert blocker["next_trigger"] == (
        "operator_may_authorize_bounded_demo_probe_with_exact_typed_confirm"
    )
    assert blocker["operator_actionable"] is True
    assert blocker["bounded_probe_operator_authorization_source_candidate_max_probe_orders"] == 3
    assert blocker["bounded_probe_operator_authorization_object_emitted"] is False
    assert (
        blocker["bounded_probe_operator_authorization_active_runtime_order_authority"]
        is False
    )
    assert blocker["bounded_probe_operator_authorization_main_cost_gate_adjustment"] == (
        "NONE"
    )
    assert blocker["bounded_probe_operator_authorization_promotion_evidence"] is False

    assert task["task_type"] == "operator_probe_review"
    assert task["learning_objective"] == (
        "operator_review_bounded_demo_probe_authorization_packet"
    )
    assert task["requires_operator_authorization"] is True
    assert task["runtime_mutation_required"] is False
    assert task["evidence"]["bounded_probe_operator_authorization_ready_for_review"] is True
    assert task["evidence"]["bounded_probe_operator_authorization_object_emitted"] is False
    assert (
        task["evidence"][
            "bounded_probe_operator_authorization_active_runtime_order_authority"
        ]
        is False
    )


def test_cost_gate_bounded_probe_result_review_supersedes_preflight(tmp_path):
    data = tmp_path / "openclaw"
    _write_profit_learning_decision_packet_latest(
        data,
        status="OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE",
        reason="sealed_horizon_learning_evidence_clears_review_thresholds",
        next_actions=[
            "operator_may_authorize_minimal_rust_authority_bounded_demo_probe_separately"
        ],
        sealed_horizon_candidate=True,
    )
    _write_sealed_horizon_probe_preflight_latest(
        data,
        status="READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION",
    )
    _write_bounded_probe_result_review_latest(
        data,
        status="STOP_BOUNDED_DEMO_PROBE_REALIZED_EDGE_FAILED",
    )

    now = dt.datetime(2026, 6, 21, 18, 5, tzinfo=dt.timezone.utc)
    arm = collect_cost_gate_learning_lane_arm(data, now_utc=now)
    plan = build_discovery_plan([arm], now_utc=now)
    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    task = plan["learning_worklist"]["top_task"]

    assert blocker["blocker_class"] == "rejected_no_edge"
    assert blocker["primary_blocker"] == (
        "bounded_probe_result_review_realized_edge_failed_keep_cost_gate_blocked"
    )
    assert blocker["bounded_probe_result_review_status"] == (
        "STOP_BOUNDED_DEMO_PROBE_REALIZED_EDGE_FAILED"
    )
    assert blocker["bounded_probe_result_review_completed_probe_outcome_count"] == 3
    assert blocker["bounded_probe_result_review_avg_realized_net_bps"] == -1.2
    assert blocker["bounded_probe_result_review_stop_probe_recommended"] is True
    assert blocker["bounded_probe_result_review_order_authority_granted"] is False
    assert blocker["bounded_probe_result_review_main_cost_gate_adjustment"] == "NONE"
    assert blocker["bounded_probe_result_review_evidence_quality_status"] == (
        "REALIZED_EDGE_FAILED"
    )
    assert task["task_type"] == "reject_or_archive"
    assert task["evidence"]["bounded_probe_result_review_stop_probe_recommended"] is True


def test_shadow_placement_impact_drives_placement_repair_task(tmp_path):
    data = tmp_path / "openclaw"
    _write_profit_learning_decision_packet_latest(
        data,
        status="OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE",
        reason="sealed_horizon_learning_evidence_clears_review_thresholds",
        next_actions=[
            "operator_may_authorize_minimal_rust_authority_bounded_demo_probe_separately"
        ],
        sealed_horizon_candidate=True,
    )
    _write_sealed_horizon_probe_preflight_latest(
        data,
        status="READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION",
    )
    _write_bounded_probe_shadow_placement_impact_latest(data)

    now = dt.datetime(2026, 6, 21, 18, 5, tzinfo=dt.timezone.utc)
    arm = collect_cost_gate_learning_lane_arm(data, now_utc=now)
    plan = build_discovery_plan([arm], now_utc=now)
    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    task = plan["learning_worklist"]["top_task"]

    assert arm["detail"]["bounded_probe_shadow_placement_impact_status"] == (
        "SHADOW_PLACEMENT_TOUCHABILITY_IMPROVED_SAMPLE_MISMATCH"
    )
    assert blocker["blocker_class"] == "execution_realism"
    assert blocker["primary_blocker"] == (
        "bounded_probe_shadow_placement_candidate_sample_missing"
    )
    assert blocker["next_trigger"] == (
        "operator_review_mechanical_touchability_before_rust_patch"
    )
    assert blocker["bounded_probe_shadow_placement_submit_count"] == 6
    assert blocker["bounded_probe_shadow_placement_candidate_matched_order_count"] == 0
    assert blocker["bounded_probe_shadow_placement_max_gap_reduction_bps"] == 1522.1026
    assert blocker["bounded_probe_shadow_placement_candidate_specific_alpha_proof"] is False
    assert blocker["bounded_probe_shadow_placement_order_authority_granted"] is False
    assert task["task_type"] == "bounded_probe_placement_repair"
    assert task["learning_objective"] == (
        "make_bounded_demo_probe_orders_touchable_then_collect_candidate_matched_fill_lineage"
    )
    assert task["requires_operator_authorization"] is True
    assert task["runtime_mutation_required"] is False
    assert task["evidence"]["bounded_probe_shadow_placement_sample_scope"] == (
        "current_demo_order_flow_not_candidate_matched"
    )
    assert task["evidence"][
        "bounded_probe_shadow_placement_candidate_specific_alpha_proof"
    ] is False


def test_positive_bounded_probe_result_without_control_stays_data_coverage(tmp_path):
    data = tmp_path / "openclaw"
    _write_profit_learning_decision_packet_latest(
        data,
        status="OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE",
        reason="sealed_horizon_learning_evidence_clears_review_thresholds",
        next_actions=[
            "operator_may_authorize_minimal_rust_authority_bounded_demo_probe_separately"
        ],
        sealed_horizon_candidate=True,
    )
    _write_sealed_horizon_probe_preflight_latest(
        data,
        status="READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION",
    )
    _write_bounded_probe_result_review_latest(
        data,
        status="FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED",
        evidence_quality_status="CONTROL_COMPARISON_MISSING",
        matched_control_count=0,
    )

    now = dt.datetime(2026, 6, 21, 18, 5, tzinfo=dt.timezone.utc)
    arm = collect_cost_gate_learning_lane_arm(data, now_utc=now)
    plan = build_discovery_plan([arm], now_utc=now)
    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    task = plan["learning_worklist"]["top_task"]

    assert blocker["blocker_class"] == "data_coverage"
    assert blocker["primary_blocker"] == (
        "bounded_probe_result_review_needs_matched_blocked_signal_control"
    )
    assert blocker["next_trigger"] == (
        "record_matched_blocked_signal_outcomes_for_same_side_cell_and_horizon"
    )
    assert blocker["bounded_probe_result_review_evidence_quality_status"] == (
        "CONTROL_COMPARISON_MISSING"
    )
    assert blocker["bounded_probe_result_review_anecdote_risk"] is True
    assert task["requires_operator_authorization"] is False
    assert task["evidence"]["bounded_probe_result_review_matched_control_outcome_count"] == 0


def test_positive_bounded_probe_under_captures_control_requires_execution_review(tmp_path):
    data = tmp_path / "openclaw"
    _write_profit_learning_decision_packet_latest(
        data,
        status="OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE",
        reason="sealed_horizon_learning_evidence_clears_review_thresholds",
        next_actions=[
            "operator_may_authorize_minimal_rust_authority_bounded_demo_probe_separately"
        ],
        sealed_horizon_candidate=True,
    )
    _write_sealed_horizon_probe_preflight_latest(
        data,
        status="READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION",
    )
    _write_bounded_probe_result_review_latest(
        data,
        status="FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED",
        evidence_quality_status="PROBE_UNDERPERFORMS_MATCHED_CONTROL_EXECUTION_GAP",
        matched_control_count=3,
        matched_control_avg_net_bps=3.0,
    )

    now = dt.datetime(2026, 6, 21, 18, 5, tzinfo=dt.timezone.utc)
    arm = collect_cost_gate_learning_lane_arm(data, now_utc=now)
    plan = build_discovery_plan([arm], now_utc=now)
    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    task = plan["learning_worklist"]["top_task"]

    assert blocker["blocker_class"] == "execution_realism"
    assert blocker["primary_blocker"] == (
        "bounded_probe_execution_realism_review_required"
    )
    assert blocker["next_trigger"] == (
        "refresh_bounded_probe_execution_realism_review"
    )
    assert blocker["operator_actionable"] is False
    assert blocker["engineering_actionable"] is True
    assert blocker["bounded_probe_result_review_probe_edge_capture_ratio"] == 0.8333
    assert blocker["bounded_probe_result_review_probe_execution_gap_bps"] == 0.5
    assert blocker["bounded_probe_result_review_execution_realism_gap"] is True
    assert blocker["bounded_probe_execution_realism_review_present"] is False
    assert task["task_type"] == "bounded_probe_execution_realism"
    assert task["learning_objective"] == (
        "measure_probe_slippage_timing_and_fill_quality_against_matched_control_edge"
    )
    assert task["requires_operator_authorization"] is False
    assert task["runtime_mutation_required"] is False
    assert task["evidence"]["bounded_probe_result_review_execution_realism_gap"] is True
    assert task["evidence"]["bounded_probe_execution_realism_review_present"] is False


def test_positive_bounded_probe_execution_review_drives_repair_task(tmp_path):
    data = tmp_path / "openclaw"
    _write_profit_learning_decision_packet_latest(
        data,
        status="OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE",
        reason="sealed_horizon_learning_evidence_clears_review_thresholds",
        next_actions=[
            "operator_may_authorize_minimal_rust_authority_bounded_demo_probe_separately"
        ],
        sealed_horizon_candidate=True,
    )
    _write_sealed_horizon_probe_preflight_latest(
        data,
        status="READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION",
    )
    _write_bounded_probe_result_review_latest(
        data,
        status="FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED",
        evidence_quality_status="PROBE_UNDERPERFORMS_MATCHED_CONTROL_EXECUTION_GAP",
        matched_control_count=3,
        matched_control_avg_net_bps=3.0,
    )
    _write_bounded_probe_execution_realism_review_latest(data)

    now = dt.datetime(2026, 6, 21, 18, 5, tzinfo=dt.timezone.utc)
    arm = collect_cost_gate_learning_lane_arm(data, now_utc=now)
    plan = build_discovery_plan([arm], now_utc=now)
    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    task = plan["learning_worklist"]["top_task"]

    assert blocker["blocker_class"] == "execution_realism"
    assert blocker["primary_blocker"] == (
        "bounded_probe_execution_realism_gap_diagnosed_repair_required"
    )
    assert blocker["next_trigger"] == (
        "record_fill_backed_probe_execution_rows_or_l1_replay_before_cost_gate_review"
    )
    assert blocker["bounded_probe_execution_realism_review_status"] == (
        "EXECUTION_REALISM_GAP_DIAGNOSED_REPAIR_REQUIRED"
    )
    assert blocker["bounded_probe_execution_realism_review_primary_hypothesis"] == (
        "fill_backed_execution_missing"
    )
    assert blocker["bounded_probe_execution_realism_review_net_capture_gap_bps"] == 0.5
    assert blocker["bounded_probe_execution_realism_review_probe_fill_backed_pct"] == 0.0
    assert blocker[
        "bounded_probe_execution_realism_review_cost_gate_or_operator_review_allowed"
    ] is False
    assert task["task_type"] == "bounded_probe_execution_realism"
    assert task["requires_operator_authorization"] is False
    assert task["runtime_mutation_required"] is False
    assert task["evidence"][
        "bounded_probe_execution_realism_review_primary_hypothesis"
    ] == "fill_backed_execution_missing"
    assert task["evidence"]["bounded_probe_execution_realism_review_net_capture_gap_bps"] == 0.5
    assert task["evidence"][
        "bounded_probe_execution_realism_review_cost_gate_or_operator_review_allowed"
    ] is False


def _write_polymarket_leadlag_latest(data: Path, payload: dict) -> Path:
    path = data / "research" / "polymarket_leadlag" / "polymarket_leadlag_latest.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "created_at_utc": "2026-06-20T12:00:00+00:00",
        "query_set_version": "v2",
        "mode": "hourly-topn",
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "horizons_minutes": [15, 60, 240],
        "price_source": "pg:market.klines:1m",
        "verdict": {
            "status": "INSUFFICIENT_SAMPLE",
            "reason": "max joined IC points 0 below min_points 30",
            "candidate_count": 0,
            "promotion_boundary": "research_context_only_not_signal_or_promotion_proof",
        },
        "counts": {
            "snapshot_rows": 860,
            "snapshot_distinct_timestamps": 1,
            "delta_rows": 0,
            "joined_rows": 0,
            "price_rows": 32,
        },
        "ic_results": [],
        **payload,
    }), encoding="utf-8")
    return path


def _write_polymarket_replay_report(
    data: Path,
    *,
    stamp: str,
    created_at: str,
    candidate_key: str,
    samples: list[dict],
) -> Path:
    path = data / "research" / "polymarket_leadlag" / f"polymarket_leadlag_{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "created_at_utc": created_at,
        "candidate_replay_scorecard": {
            "status": "PAPER_REPLAY_BUILT",
            "selected_candidate_key": candidate_key,
            "selected_summary": {
                "candidate_id": "polymarket_leadlag_price_target_SOLUSDT_15m",
                "candidate_key": candidate_key,
                "strategy_family": "polymarket_leadlag_directional_replay",
                "parameter_cell_id": "price_target|SOLUSDT|15m|rule=ic_sign_delta|threshold_q=0|cost_bps=4",
                "selected_variant": "ic_sign_delta",
                "sample_unit": "polymarket_nonoverlap_forward_window",
            },
            "selected_evidence": {
                "candidate_id": "polymarket_leadlag_price_target_SOLUSDT_15m",
                "candidate_key": candidate_key,
                "strategy_family": "polymarket_leadlag_directional_replay",
                "parameter_cell_id": "price_target|SOLUSDT|15m|rule=ic_sign_delta|threshold_q=0|cost_bps=4",
                "selected_variant": "ic_sign_delta",
                "sample_unit": "polymarket_nonoverlap_forward_window",
                "k_trials": 12,
                "samples": samples,
                "daily_returns": {"unit": "fraction", "values": {}},
                "pbo_candidates": {
                    "cell_a": {created_at[:10]: 0.001},
                    "cell_b": {created_at[:10]: -0.0005},
                },
            },
        },
    }), encoding="utf-8")
    return path


def test_polymarket_leadlag_arm_captures_insufficient_sample(tmp_path):
    data = tmp_path / "openclaw"
    _write_polymarket_leadlag_latest(data, {
        "counts": {
            "snapshot_rows": 860,
            "snapshot_distinct_timestamps": 5,
            "delta_rows": 400,
            "joined_rows": 120,
            "price_rows": 320,
            "max_ic_points": 12,
            "max_overlap_adjusted_ic_points": 0,
            "label_readiness": {
                "feature_horizon_pairs": 18,
                "joinable_pairs": 0,
                "status_counts": {"exit_target_after_latest_price": 18},
                "by_horizon": {"15": {"exit_target_after_latest_price": 6}},
                "oldest_unmatured_exit_target_utc": "2026-06-20T12:22:00+00:00",
            },
        },
    })

    arm = collect_polymarket_leadlag_arm(
        data,
        now_utc=dt.datetime(2026, 6, 20, 12, 30, tzinfo=dt.timezone.utc),
    )
    plan = build_discovery_plan([arm], now_utc=dt.datetime(2026, 6, 20, 12, 30, tzinfo=dt.timezone.utc))

    assert arm["gate_status"] == "CAPTURING"
    assert arm["source_ok"] is True
    assert arm["sample_count"] == 0
    assert arm["artifacts_ready"] is False
    assert arm["detail"]["verdict_status"] == "INSUFFICIENT_SAMPLE"
    assert arm["detail"]["snapshot_rows"] == 860
    assert arm["detail"]["label_joinable_pairs"] == 0
    assert arm["detail"]["label_status_counts"] == {"exit_target_after_latest_price": 18}
    assert arm["detail"]["oldest_unmatured_exit_target_utc"] == "2026-06-20T12:22:00+00:00"
    assert arm["detail"]["promotion_boundary"] == "research_context_only_not_signal_or_promotion_proof"
    assert plan["arms"][0]["action"] == "RUN_READ_ONLY_CAPTURE"
    assert plan["arms"][0]["reason"] == "sample_count_below_gate"


def test_polymarket_leadlag_arm_ready_only_for_candidate_review_with_sample(tmp_path):
    data = tmp_path / "openclaw"
    _write_polymarket_leadlag_latest(data, {
        "verdict": {
            "status": "IC_CANDIDATE_REVIEW_REQUIRED",
            "reason": "one or more bucket/symbol/horizon IC cells pass preliminary thresholds",
            "candidate_count": 1,
            "preliminary_raw_candidate_count": 2,
            "max_bh_q": 0.10,
            "promotion_boundary": "research_context_only_not_signal_or_promotion_proof",
        },
        "counts": {
            "snapshot_rows": 26000,
            "snapshot_distinct_timestamps": 36,
            "delta_rows": 1200,
            "feature_points": 180,
            "feature_bucket_counts": {
                "event_reg": 90,
                "event_reg_direct": 40,
                "event_reg_macro": 50,
            },
            "feature_bucket_view_counts": {"aggregate": 90, "source_split": 90},
            "price_feedback_summary": {
                "cells_with_control": 2,
                "warning_count": 1,
                "max_abs_past_return_ic": 0.41,
                "partial_control_cells": 2,
                "raw_to_partial_collapse_count": 1,
                "max_abs_partial_ic_controlling_trailing_return": 0.12,
                "warning_cells": [{"bucket": "event_reg", "symbol": "BTCUSDT"}],
            },
            "joined_rows": 105,
            "price_rows": 9000,
            "max_ic_points": 35,
            "max_overlap_adjusted_ic_points": 35,
        },
        "ic_results": [
            {
                "bucket": "event_reg",
                "symbol": "BTCUSDT",
                "horizon_minutes": 60,
                "n_points": 35,
                "ic_pearson": 0.22,
                "t_stat": 2.1,
            }
        ],
        "candidates": [{
            "bucket": "event_reg",
            "symbol": "BTCUSDT",
            "horizon_minutes": 60,
            "n_points": 35,
            "ic_pearson": 0.22,
            "t_stat_hac": 2.5,
        }],
        "candidate_replay_scorecard": {
            "status": "PAPER_REPLAY_BUILT",
            "selected_summary": {
                "candidate_id": "polymarket_leadlag_event_reg_BTCUSDT_60m",
                "parameter_cell_id": (
                    "event_reg|BTCUSDT|60m|rule=ic_sign_delta|"
                    "threshold_q=0|cost_bps=4"
                ),
                "sample_count": 35,
                "round_trip_cost_bps": 4.0,
                "gross_bps_mean": 9.5,
                "net_bps_mean": 5.5,
                "holdout_net_bps_mean": 4.8,
                "cost_wall_status": "PAPER_REPLAY_NET_POSITIVE_EXECUTION_UNMEASURED",
                "execution_realism_status": "UNMEASURED",
            },
        },
    })

    arm = collect_polymarket_leadlag_arm(
        data,
        now_utc=dt.datetime(2026, 6, 20, 12, 30, tzinfo=dt.timezone.utc),
    )
    plan = build_discovery_plan([arm], now_utc=dt.datetime(2026, 6, 20, 12, 30, tzinfo=dt.timezone.utc))

    assert arm["gate_status"] == "READY"
    assert arm["artifacts_ready"] is True
    assert arm["sample_count"] == 35
    assert arm["detail"]["max_ic_points"] == 35
    assert arm["detail"]["max_overlap_adjusted_ic_points"] == 35
    assert arm["detail"]["candidate_count"] == 1
    assert arm["detail"]["candidate_key"] == "polymarket_leadlag_ic|event_reg|BTCUSDT|60m"
    assert arm["detail"]["candidate_replay_status"] == "PAPER_REPLAY_BUILT"
    assert arm["detail"]["candidate_replay_sample_count"] == 35
    assert arm["detail"]["candidate_replay_net_bps_mean"] == 5.5
    assert arm["detail"]["candidate_replay_cost_wall_status"] == (
        "PAPER_REPLAY_NET_POSITIVE_EXECUTION_UNMEASURED"
    )
    assert arm["detail"]["candidate_replay_history_status"] == "NO_REPLAY_HISTORY"
    assert arm["detail"]["preliminary_raw_candidate_count"] == 2
    assert arm["detail"]["max_bh_q"] == 0.10
    assert plan["arms"][0]["action"] == "READY_FOR_AEG_CHAIN"
    assert plan["arms"][0]["reason"] == "artifacts_ready_and_sample_gate_met"
    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    assert plan["profitability_blocker_scorecard"]["promotion_ready_count"] == 0
    assert plan["profitability_blocker_scorecard"]["status"] == (
        "NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED"
    )
    assert blocker["blocker_class"] == "data_coverage"
    assert blocker["primary_blocker"] == "polymarket_candidate_replay_history_missing"
    assert blocker["next_trigger"] == (
        "collect_dated_polymarket_replay_history_before_aeg_promotion"
    )
    assert blocker["promotion_ready"] is False
    assert blocker["candidate_replay_status"] == "PAPER_REPLAY_BUILT"
    assert blocker["candidate_replay_history_status"] == "NO_REPLAY_HISTORY"


def test_runtime_killboard_separates_polymarket_candidate_artifact_from_actionable_alpha(tmp_path):
    data = tmp_path / "openclaw"
    _write_polymarket_leadlag_latest(data, {
        "verdict": {
            "status": "IC_CANDIDATE_REVIEW_REQUIRED",
            "reason": "one candidate",
            "candidate_count": 1,
            "promotion_boundary": "research_context_only_not_signal_or_promotion_proof",
        },
        "counts": {
            "snapshot_rows": 26000,
            "snapshot_distinct_timestamps": 36,
            "joined_rows": 105,
            "max_overlap_adjusted_ic_points": 35,
        },
        "candidates": [{
            "bucket": "event_reg",
            "symbol": "BTCUSDT",
            "horizon_minutes": 60,
            "n_points": 35,
            "t_stat_hac": 2.5,
        }],
        "candidate_replay_scorecard": {
            "status": "PAPER_REPLAY_BUILT",
            "selected_summary": {
                "candidate_id": "polymarket_leadlag_event_reg_BTCUSDT_60m",
                "parameter_cell_id": "event_reg|BTCUSDT|60m|rule=ic_sign_delta",
                "sample_count": 35,
                "net_bps_mean": 5.5,
                "execution_realism_status": "UNMEASURED",
            },
        },
    })

    result = run_once(
        data_dir=data,
        repo_root=tmp_path,
        now_utc=dt.datetime(2026, 6, 20, 12, 30, tzinfo=dt.timezone.utc),
    )

    assert result["killboard"]["ready_for_aeg_chain"] == 1
    assert result["killboard"]["aeg_candidate_artifact_found"] is True
    assert result["killboard"]["promotion_ready_count"] == 0
    assert result["killboard"]["actionable_alpha_found"] is False
    scorecard = result["profitability_blocker_scorecard"]
    blockers = {row["arm_id"]: row for row in scorecard["arms"]}
    assert blockers["polymarket_leadlag_ic"]["blocker_class"] == "data_coverage"
    assert blockers["polymarket_leadlag_ic"]["primary_blocker"] == (
        "polymarket_candidate_replay_history_missing"
    )


def test_polymarket_leadlag_arm_surfaces_replay_history(tmp_path):
    data = tmp_path / "openclaw"
    candidate_key = "polymarket_leadlag_ic|price_target|SOLUSDT|15m"
    _write_polymarket_leadlag_latest(data, {
        "verdict": {
            "status": "IC_CANDIDATE_REVIEW_REQUIRED",
            "reason": "candidate",
            "candidate_count": 1,
        },
        "counts": {
            "max_overlap_adjusted_ic_points": 30,
        },
        "ic_results": [{"n_points": 30, "overlap_adjusted_sample_floor": 30}],
        "candidates": [{
            "bucket": "price_target",
            "symbol": "SOLUSDT",
            "horizon_minutes": 15,
        }],
    })
    _write_polymarket_replay_report(
        data,
        stamp="20260620T010000Z",
        created_at="2026-06-20T01:00:00+00:00",
        candidate_key=candidate_key,
        samples=[{
            "sample_id": "s1",
            "sample_ts_utc": "2026-06-20T00:00:00+00:00",
            "regime": "unsegmented",
            "independence_bucket": "SOLUSDT:15m:1",
            "gross_bps": 10.0,
            "cost_bps": 4.0,
            "net_bps": 6.0,
            "is_oos": True,
        }],
    )
    _write_polymarket_replay_report(
        data,
        stamp="20260621T010000Z",
        created_at="2026-06-21T01:00:00+00:00",
        candidate_key=candidate_key,
        samples=[{
            "sample_id": "s2",
            "sample_ts_utc": "2026-06-21T00:00:00+00:00",
            "regime": "unsegmented",
            "independence_bucket": "SOLUSDT:15m:2",
            "gross_bps": 8.0,
            "cost_bps": 4.0,
            "net_bps": 4.0,
            "is_oos": True,
        }],
    )

    arm = collect_polymarket_leadlag_arm(
        data,
        now_utc=dt.datetime(2026, 6, 20, 12, 30, tzinfo=dt.timezone.utc),
    )

    detail = arm["detail"]
    assert detail["candidate_replay_history_status"] == "REPLAY_HISTORY_DAYS_INSUFFICIENT"
    assert detail["candidate_replay_history_report_count"] == 2
    assert detail["candidate_replay_history_matched_report_count"] == 2
    assert detail["candidate_replay_history_sample_count"] == 2
    assert detail["candidate_replay_history_n_days"] == 2
    assert detail["candidate_replay_history_min_days"] == 30
    assert detail["candidate_replay_history_days_remaining"] == 28
    assert detail["candidate_replay_history_earliest_ready_date"] == "2026-07-19"
    assert detail["candidate_replay_history_net_bps_mean"] == 5.0
    assert detail["candidate_replay_history_interim_edge_status"] == (
        "INSUFFICIENT_SAMPLES_FOR_INTERIM_EDGE"
    )
    assert detail["candidate_replay_history_budget_status"] == (
        "CONTINUE_HISTORY_ACCUMULATION"
    )
    assert detail["candidate_replay_history_pbo_day_count"] == 2
    assert detail["candidate_replay_history_execution_realism_status"] == "UNMEASURED"


def test_polymarket_leadlag_negative_interim_history_rotates_candidate(tmp_path):
    data = tmp_path / "openclaw"
    candidate_key = "polymarket_leadlag_ic|event_reg|BTCUSDT|15m"
    _write_polymarket_leadlag_latest(data, {
        "verdict": {
            "status": "IC_CANDIDATE_REVIEW_REQUIRED",
            "reason": "candidate",
            "candidate_count": 1,
        },
        "counts": {
            "max_overlap_adjusted_ic_points": 30,
        },
        "ic_results": [{"n_points": 30, "overlap_adjusted_sample_floor": 30}],
        "candidates": [{
            "bucket": "event_reg",
            "symbol": "BTCUSDT",
            "horizon_minutes": 15,
        }],
    })
    for offset in range(3):
        day = dt.date(2026, 6, 20) + dt.timedelta(days=offset)
        samples = []
        for idx in range(10):
            samples.append({
                "sample_id": f"s{offset}-{idx}",
                "sample_ts_utc": f"{day.isoformat()}T00:{idx:02d}:00+00:00",
                "regime": "unsegmented",
                "independence_bucket": f"BTCUSDT:15m:{offset}:{idx}",
                "gross_bps": 1.0,
                "cost_bps": 4.0,
                "net_bps": -3.0,
                "is_oos": True,
            })
        _write_polymarket_replay_report(
            data,
            stamp=f"{day.strftime('%Y%m%d')}T010000Z",
            created_at=f"{day.isoformat()}T01:00:00+00:00",
            candidate_key=candidate_key,
            samples=samples,
        )

    arm = collect_polymarket_leadlag_arm(
        data,
        now_utc=dt.datetime(2026, 6, 20, 12, 30, tzinfo=dt.timezone.utc),
    )
    plan = build_discovery_plan(
        [arm],
        now_utc=dt.datetime(2026, 6, 20, 12, 30, tzinfo=dt.timezone.utc),
    )

    detail = arm["detail"]
    assert detail["candidate_replay_history_status"] == (
        "REPLAY_HISTORY_DAYS_INSUFFICIENT"
    )
    assert detail["candidate_replay_history_sample_count"] == 30
    assert detail["candidate_replay_history_n_days"] == 3
    assert detail["candidate_replay_history_net_bps_mean"] == -3.0
    assert detail["candidate_replay_history_holdout_net_bps_mean"] == -3.0
    assert detail["candidate_replay_history_interim_edge_status"] == (
        "INTERIM_NEGATIVE_NET_AND_HOLDOUT"
    )
    assert detail["candidate_replay_history_budget_status"] == (
        "EARLY_ROTATE_RECOMMENDED"
    )

    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    assert blocker["blocker_class"] == "rejected_no_edge"
    assert blocker["primary_blocker"] == (
        "polymarket_candidate_replay_history_interim_negative_edge"
    )
    assert blocker["engineering_actionable"] is False
    assert blocker["next_trigger"] == (
        "rotate_polymarket_leadlag_candidate_or_change_feature_family_"
        "before_spending_30d_history_budget"
    )
    task = plan["learning_worklist"]["top_task"]
    assert task["task_type"] == "reject_or_archive"
    assert task["actionability"] == "parked"
    assert task["evidence"]["candidate_replay_history_budget_status"] == (
        "EARLY_ROTATE_RECOMMENDED"
    )


def test_polymarket_leadlag_arm_blocks_stale_report(tmp_path):
    data = tmp_path / "openclaw"
    _write_polymarket_leadlag_latest(data, {
        "created_at_utc": "2026-06-20T00:00:00+00:00",
        "ic_results": [{"n_points": 35}],
    })

    arm = collect_polymarket_leadlag_arm(
        data,
        now_utc=dt.datetime(2026, 6, 20, 12, 30, tzinfo=dt.timezone.utc),
    )
    plan = build_discovery_plan([arm], now_utc=dt.datetime(2026, 6, 20, 12, 30, tzinfo=dt.timezone.utc))

    assert arm["gate_status"] == "SOURCE_FAILURE"
    assert arm["source_ok"] is False
    assert arm["source_error"] == "stale_artifact"
    assert arm["detail"]["age_seconds"] > 6 * 60 * 60
    assert plan["arms"][0]["action"] == "BLOCK"
    assert plan["arms"][0]["reason"] == "source_not_healthy"


def test_polymarket_leadlag_arm_uses_overlap_adjusted_sample_count(tmp_path):
    data = tmp_path / "openclaw"
    _write_polymarket_leadlag_latest(data, {
        "counts": {
            "snapshot_rows": 26000,
            "snapshot_distinct_timestamps": 36,
            "delta_rows": 1200,
            "feature_points": 180,
            "feature_bucket_counts": {
                "event_reg": 90,
                "event_reg_direct": 40,
                "event_reg_macro": 50,
            },
            "feature_bucket_view_counts": {"aggregate": 90, "source_split": 90},
            "price_feedback_summary": {
                "cells_with_control": 2,
                "warning_count": 1,
                "max_abs_past_return_ic": 0.41,
                "partial_control_cells": 2,
                "raw_to_partial_collapse_count": 1,
                "max_abs_partial_ic_controlling_trailing_return": 0.12,
                "warning_cells": [{"bucket": "event_reg", "symbol": "BTCUSDT"}],
            },
            "joined_rows": 105,
            "price_rows": 9000,
            "max_ic_points": 35,
            "max_overlap_adjusted_ic_points": 12,
            "min_samples_remaining_to_gate": 18,
            "sample_gate_clock": {
                "status": "WAITING_FOR_SAMPLE",
                "fastest_gate_ready_utc": "2026-06-20T19:52:01+00:00",
                "min_samples_remaining_to_gate": 18,
                "cells": [{
                    "bucket": "event_reg",
                    "symbol": "BTCUSDT",
                    "horizon_minutes": 240,
                    "expected_gate_label_ready_utc": "2026-06-20T19:52:01+00:00",
                }],
            },
            "pre_gate_watchlist_persistence_scorecard": {
                "status": "PERSISTENT_PRE_GATE_WATCHLIST",
                "recurring_cell_count": 1,
                "persistent_cell_count": 1,
                "floor_qualified_recurring_cell_count": 0,
                "floor_qualified_persistent_cell_count": 0,
                "top_cells": [{
                    "cell_key": "event_reg|BTCUSDT|240",
                    "bucket": "event_reg",
                    "symbol": "BTCUSDT",
                    "horizon_minutes": 240,
                    "current_consecutive_reports": 3,
                    "presence_count": 3,
                }],
            },
        },
        "verdict": {
            "status": "INSUFFICIENT_SAMPLE",
            "reason": "max overlap-adjusted IC points 12 below min_points 30",
            "candidate_count": 0,
            "pre_gate_hac_watchlist_count": 1,
            "pre_gate_watchlist_persistence_status": "PERSISTENT_PRE_GATE_WATCHLIST",
            "pre_gate_watchlist_recurring_cell_count": 1,
            "pre_gate_watchlist_persistent_cell_count": 1,
            "price_feedback_warning_count": 1,
            "price_feedback_partial_collapse_count": 1,
            "promotion_boundary": "research_context_only_not_signal_or_promotion_proof",
        },
        "pre_gate_hac_watchlist": [{
            "bucket": "event_reg",
            "symbol": "BTCUSDT",
            "horizon_minutes": 240,
            "overlap_adjusted_sample_floor": 12,
            "sample_gap_to_min_points": 18,
            "t_stat_hac": 2.7,
            "bh_q_value_hac_approx": 0.04,
            "gate_blocker": "sample_floor_below_min_points",
        }],
        "ic_results": [
            {
                "bucket": "event_reg",
                "symbol": "BTCUSDT",
                "horizon_minutes": 240,
                "n_points": 35,
                "overlap_adjusted_sample_floor": 12,
                "ic_pearson": 0.22,
                "t_stat": 2.1,
            }
        ],
    })

    arm = collect_polymarket_leadlag_arm(
        data,
        now_utc=dt.datetime(2026, 6, 20, 12, 30, tzinfo=dt.timezone.utc),
    )
    plan = build_discovery_plan([arm], now_utc=dt.datetime(2026, 6, 20, 12, 30, tzinfo=dt.timezone.utc))

    assert arm["sample_count"] == 12
    assert arm["detail"]["max_ic_points"] == 35
    assert arm["detail"]["max_overlap_adjusted_ic_points"] == 12
    assert arm["detail"]["feature_points"] == 180
    assert arm["detail"]["feature_bucket_counts"]["event_reg_macro"] == 50
    assert arm["detail"]["feature_bucket_view_counts"] == {"aggregate": 90, "source_split": 90}
    assert arm["detail"]["min_samples_remaining_to_gate"] == 18
    assert arm["detail"]["sample_gate_status"] == "WAITING_FOR_SAMPLE"
    assert arm["detail"]["sample_gate_eta_utc"] == "2026-06-20T19:52:01+00:00"
    assert arm["detail"]["sample_gate_clock"]["cells"][0]["symbol"] == "BTCUSDT"
    assert arm["detail"]["pre_gate_hac_watchlist_count"] == 1
    assert arm["detail"]["pre_gate_watchlist_persistence_status"] == (
        "PERSISTENT_PRE_GATE_WATCHLIST"
    )
    assert arm["detail"]["pre_gate_watchlist_recurring_cell_count"] == 1
    assert arm["detail"]["pre_gate_watchlist_persistent_cell_count"] == 1
    assert arm["detail"]["pre_gate_watchlist_persistence_scorecard"]["top_cells"][0]["cell_key"] == (
        "event_reg|BTCUSDT|240"
    )
    assert arm["detail"]["price_feedback_warning_count"] == 1
    assert arm["detail"]["price_feedback_partial_collapse_count"] == 1
    assert arm["detail"]["price_feedback_summary"]["warning_count"] == 1
    assert arm["detail"]["price_feedback_summary"]["raw_to_partial_collapse_count"] == 1
    assert arm["detail"]["best_pre_gate_hac_watch"]["gate_blocker"] == "sample_floor_below_min_points"
    assert plan["arms"][0]["action"] == "RUN_READ_ONLY_CAPTURE"
    assert plan["arms"][0]["reason"] == "sample_count_below_gate"
    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    assert blocker["pre_gate_watchlist_persistence_status"] == "PERSISTENT_PRE_GATE_WATCHLIST"
    assert blocker["best_persistent_pre_gate_cell"]["cell_key"] == "event_reg|BTCUSDT|240"
    assert blocker["sample_gate_recheck_status"] == "PERSISTENT_PRE_GATE_WAIT_SAMPLE"
    assert blocker["next_trigger"] == "continue_polymarket_capture_until_sample_gate_eta"


def test_polymarket_leadlag_routes_zero_joined_rows_to_label_maturity_wait(tmp_path):
    data = tmp_path / "openclaw"
    _write_polymarket_leadlag_latest(data, {
        "created_at_utc": "2026-06-20T22:02:00+00:00",
        "counts": {
            "snapshot_rows": 2685,
            "snapshot_distinct_timestamps": 3,
            "delta_rows": 2061,
            "feature_points": 26,
            "joined_rows": 0,
            "price_rows": 1100,
            "max_overlap_adjusted_ic_points": 0,
            "min_samples_remaining_to_gate": 30,
            "label_readiness": {
                "feature_horizon_pairs": 78,
                "joinable_pairs": 0,
                "status_counts": {"exit_target_after_latest_price": 78},
                "oldest_unmatured_exit_target_utc": "2026-06-20T22:07:01+00:00",
            },
        },
        "verdict": {
            "status": "INSUFFICIENT_SAMPLE",
            "reason": "max overlap-adjusted IC points 0 below min_points 30",
            "candidate_count": 0,
            "promotion_boundary": "research_context_only_not_signal_or_promotion_proof",
        },
    })

    arm = collect_polymarket_leadlag_arm(
        data,
        now_utc=dt.datetime(2026, 6, 20, 22, 3, tzinfo=dt.timezone.utc),
    )
    plan = build_discovery_plan(
        [arm],
        now_utc=dt.datetime(2026, 6, 20, 22, 3, tzinfo=dt.timezone.utc),
    )

    assert arm["detail"]["snapshot_rows"] == 2685
    assert arm["detail"]["label_status_counts"] == {"exit_target_after_latest_price": 78}
    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    assert blocker["blocker_class"] == "sample_gate"
    assert blocker["primary_blocker"] == "label_horizon_not_matured"
    assert blocker["joined_rows"] == 0
    assert blocker["label_status_counts"] == {"exit_target_after_latest_price": 78}
    assert blocker["oldest_unmatured_exit_target_utc"] == "2026-06-20T22:07:01+00:00"
    assert blocker["next_trigger"] == (
        "rerun_polymarket_leadlag_after_label_maturity_then_alpha_discovery"
    )


def test_polymarket_leadlag_routes_matured_label_wait_to_price_catchup(tmp_path):
    data = tmp_path / "openclaw"
    _write_polymarket_leadlag_latest(data, {
        "created_at_utc": "2026-06-20T22:07:53+00:00",
        "counts": {
            "snapshot_rows": 3555,
            "snapshot_distinct_timestamps": 4,
            "delta_rows": 3066,
            "feature_points": 39,
            "joined_rows": 0,
            "price_rows": 1100,
            "max_overlap_adjusted_ic_points": 0,
            "min_samples_remaining_to_gate": 30,
            "label_readiness": {
                "feature_horizon_pairs": 117,
                "joinable_pairs": 0,
                "latest_feature_ts_utc": "2026-06-20T22:07:01.434000+00:00",
                "latest_price_ts_utc_by_symbol": {
                    "BTCUSDT": "2026-06-20T22:06:00+00:00",
                    "ETHUSDT": "2026-06-20T22:06:00+00:00",
                },
                "status_counts": {
                    "entry_target_after_latest_price": 39,
                    "exit_target_after_latest_price": 78,
                },
                "oldest_unmatured_exit_target_utc": "2026-06-20T22:07:01.150000+00:00",
                "newest_unmatured_exit_target_utc": "2026-06-21T01:54:29.853000+00:00",
            },
        },
    })

    arm = collect_polymarket_leadlag_arm(
        data,
        now_utc=dt.datetime(2026, 6, 20, 22, 8, tzinfo=dt.timezone.utc),
    )
    plan = build_discovery_plan(
        [arm],
        now_utc=dt.datetime(2026, 6, 20, 22, 8, tzinfo=dt.timezone.utc),
    )

    assert arm["detail"]["latest_price_ts_utc_by_symbol"] == {
        "BTCUSDT": "2026-06-20T22:06:00+00:00",
        "ETHUSDT": "2026-06-20T22:06:00+00:00",
    }
    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    assert blocker["primary_blocker"] == "price_data_not_caught_up_to_label_target"
    assert blocker["latest_price_ts_utc_by_symbol"]["BTCUSDT"] == (
        "2026-06-20T22:06:00+00:00"
    )
    assert blocker["latest_feature_ts_utc"] == "2026-06-20T22:07:01.434000+00:00"
    assert blocker["next_trigger"] == (
        "wait_for_price_data_to_cover_oldest_label_target_then_rerun_polymarket_leadlag"
    )


def test_polymarket_leadlag_near_gate_recheck_scorecard_routes_to_eta_recompute(tmp_path):
    data = tmp_path / "openclaw"
    _write_polymarket_leadlag_latest(data, {
        "created_at_utc": "2026-06-20T18:47:00+00:00",
        "counts": {
            "max_overlap_adjusted_ic_points": 25,
            "min_samples_remaining_to_gate": 5,
            "sample_gate_clock": {
                "status": "WAITING_FOR_SAMPLE",
                "min_points": 30,
                "max_overlap_adjusted_sample_floor": 25,
                "min_samples_remaining_to_gate": 5,
                "fastest_gate_ready_utc": "2026-06-20T19:52:01+00:00",
            },
            "pre_gate_watchlist_persistence_scorecard": {
                "status": "PERSISTENT_PRE_GATE_WATCHLIST",
                "recurring_cell_count": 4,
                "persistent_cell_count": 3,
                "floor_qualified_recurring_cell_count": 3,
                "floor_qualified_persistent_cell_count": 2,
                "top_cells": [{
                    "cell_key": "price_target|SOLUSDT|15",
                    "bucket": "price_target",
                    "symbol": "SOLUSDT",
                    "horizon_minutes": 15,
                    "current_sample_floor": 25,
                    "sample_gap_to_min_points": 5,
                    "current_consecutive_reports": 4,
                    "presence_count": 4,
                }],
            },
        },
        "verdict": {
            "status": "INSUFFICIENT_SAMPLE",
            "reason": "max overlap-adjusted IC points 25 below min_points 30",
            "candidate_count": 0,
            "pre_gate_hac_watchlist_count": 5,
            "pre_gate_watchlist_persistence_status": "PERSISTENT_PRE_GATE_WATCHLIST",
            "pre_gate_watchlist_recurring_cell_count": 4,
            "pre_gate_watchlist_persistent_cell_count": 3,
            "pre_gate_watchlist_floor_qualified_recurring_cell_count": 3,
            "pre_gate_watchlist_floor_qualified_persistent_cell_count": 2,
            "promotion_boundary": "research_context_only_not_signal_or_promotion_proof",
        },
        "pre_gate_hac_watchlist": [{
            "bucket": "price_target",
            "symbol": "SOLUSDT",
            "horizon_minutes": 15,
            "overlap_adjusted_sample_floor": 25,
            "sample_gap_to_min_points": 5,
            "t_stat_hac": 6.5,
            "bh_q_value_hac_approx": 0.000001,
            "gate_blocker": "sample_floor_below_min_points",
        }],
        "ic_results": [{
            "bucket": "price_target",
            "symbol": "SOLUSDT",
            "horizon_minutes": 15,
            "n_points": 25,
            "overlap_adjusted_sample_floor": 25,
            "ic_pearson": 0.21,
            "t_stat": 6.5,
        }],
    })

    arm = collect_polymarket_leadlag_arm(
        data,
        now_utc=dt.datetime(2026, 6, 20, 18, 54, tzinfo=dt.timezone.utc),
    )
    plan = build_discovery_plan([arm], now_utc=dt.datetime(2026, 6, 20, 18, 54, tzinfo=dt.timezone.utc))

    recheck = arm["detail"]["sample_gate_recheck_scorecard"]
    assert recheck["status"] == "PERSISTENT_PRE_GATE_NEAR_SAMPLE_GATE_WAIT_ETA"
    assert recheck["recheck_actionable"] is False
    assert recheck["floor_qualified_persistent_cell_count"] == 2
    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    assert blocker["sample_gate_recheck_status"] == (
        "PERSISTENT_PRE_GATE_NEAR_SAMPLE_GATE_WAIT_ETA"
    )
    assert blocker["next_trigger"] == (
        "rerun_polymarket_leadlag_ic_after_sample_gate_eta_then_alpha_discovery"
    )
    assert blocker["sample_gate_recheck_scorecard"]["min_samples_remaining_to_gate"] == 5


def test_runtime_runner_marks_flash_dip_no_touch_capture(tmp_path):
    data = tmp_path / "openclaw"
    (data / "logs").mkdir(parents=True)
    (data / "logs" / "flash_dip_death_rate.log").write_text(json.dumps({
        "ts_utc": "2026-06-20T00:53:01Z",
        "thresholds": {"min_n": 20},
        "n_closed_slots": 0,
        "n_deaths": 0,
        "death_rate_pct": None,
        "actionable": False,
        "alerted": False,
    }) + "\n", encoding="utf-8")
    (data / "logs" / "flash_dip_touchability.log").write_text(json.dumps({
        "ts_utc": "2026-06-20T01:10:00Z",
        "true_order_count": 18,
        "order_labeled_count": 19,
        "strategy_mismatch_count": 1,
        "touched_count": 0,
        "touch_rate_pct": 0.0,
        "median_ref_to_limit_bps": 1600.0,
        "median_closest_miss_bps": 1500.0,
        "max_closest_miss_bps": 1762.7,
        "current_k_pct": 15.0,
        "deepest_candidate_k_with_touch_pct": 6.0,
        "k_ladder": [
            {"k_pct": 2.0, "true_order_count": 18, "touched_count": 4, "touch_rate_pct": 22.2222},
            {"k_pct": 6.0, "true_order_count": 18, "touched_count": 1, "touch_rate_pct": 5.5556},
            {"k_pct": 15.0, "true_order_count": 18, "touched_count": 0, "touch_rate_pct": 0.0},
        ],
    }) + "\n", encoding="utf-8")
    (data / "logs" / "flash_dip_l1_short_exit_replay.log").write_text(json.dumps({
        "ts_utc": "2026-06-20T01:20:00Z",
        "check": "flash_dip_l1_short_exit_replay",
        "artifact_path": "/tmp/openclaw/research/tail_dislocation_meanrev/replay.json",
        "latest_path": "/tmp/openclaw/research/tail_dislocation_meanrev/latest.json",
        "sha256": "abc123",
        "verdict_status": "L1_SHORT_EXIT_INSUFFICIENT_SAMPLE",
        "fail_reasons": ["no_l1_rows_for_candidate_window"],
        "candidate_events": 3,
        "candidate_days": 1,
        "candidate_symbols": ["APTUSDT", "ATOMUSDT", "AVAXUSDT"],
        "l1_rows_post_filter": 0,
        "trade_rows": 608227,
        "symbols_with_l1": [],
        "symbols_missing_l1": ["APTUSDT", "ATOMUSDT", "AVAXUSDT"],
        "event_window_maker_timeout_minutes": 1440,
        "events_with_l1_in_event_window": 0,
        "events_missing_l1_in_event_window": 3,
        "days_with_l1_in_event_window": 0,
        "days_missing_l1_in_event_window": 1,
        "event_window_l1_relation_counts": {"no_symbol_l1_rows": 3},
        "dominant_missing_event_window_l1_relation": "no_symbol_l1_rows",
        "gate_exit_measured": 0,
        "gate_distinct_exit_days": 0,
        "gate_annret": None,
        "gate_maxdd": None,
        "boundary": "counterfactual_only_not_promotion_evidence",
    }) + "\n", encoding="utf-8")
    (data / "logs" / "flash_dip_execution_realism.log").write_text(json.dumps({
        "ts_utc": "2026-06-20T01:18:00Z",
        "check": "flash_dip_execution_realism",
        "artifact_path": "/tmp/openclaw/research/tail_dislocation_meanrev/realism.json",
        "latest_path": "/tmp/openclaw/research/tail_dislocation_meanrev/realism_latest.json",
        "sha256": "def456",
        "candidate_label": "K6_N2_C3_nf0.005",
        "k_pct": 6.0,
        "verdict_status": "EXECUTION_REALISM_BLOCKED",
        "fail_reasons": ["gate_buffer_nonpositive_annret"],
        "gate_buffer_bps": 10.0,
        "gate_filled": 68,
        "gate_distinct_days": 38,
        "gate_annret": -0.0255,
        "gate_maxdd": 0.0081,
        "short_exit_status": "SHORT_EXIT_RESEARCH_SIGNAL",
        "best_short_exit_horizon": "240m",
        "best_short_exit_annret": 0.0132,
        "best_short_exit_n_filled": 68,
        "best_short_exit_days": 38,
        "boundary": "counterfactual_only_not_promotion_evidence",
    }) + "\n", encoding="utf-8")

    arm = collect_flash_dip_arm(
        data,
        now_utc=dt.datetime(2026, 6, 20, 1, 30, tzinfo=dt.timezone.utc),
    )
    plan = build_discovery_plan([arm], now_utc=dt.datetime(2026, 6, 20, 1, 30, tzinfo=dt.timezone.utc))

    assert arm["gate_status"] == "CAPTURING_NO_TOUCH"
    assert arm["sample_count"] == 0
    assert arm["artifacts_ready"] is False
    assert arm["detail"]["touchability"]["true_order_count"] == 18
    assert arm["detail"]["touchability"]["strategy_mismatch_count"] == 1
    assert arm["detail"]["touchability"]["current_k_pct"] == 15.0
    assert arm["detail"]["touchability"]["deepest_candidate_k_with_touch_pct"] == 6.0
    assert arm["detail"]["touchability"]["k_ladder"][0]["k_pct"] == 2.0
    action_scorecard = arm["detail"]["touchability"]["action_scorecard"]
    assert action_scorecard["status"] == "SHALLOW_REPRICE_RESEARCH_BAND_PRESENT"
    assert action_scorecard["research_candidate_k_pct"] == 6.0
    assert action_scorecard["research_candidate_touched_count"] == 1
    assert action_scorecard["touchable_lower_k_count"] == 2
    l1_replay = arm["detail"]["l1_short_exit_replay"]
    assert l1_replay["source_ok"] is True
    assert l1_replay["verdict_status"] == "L1_SHORT_EXIT_INSUFFICIENT_SAMPLE"
    assert l1_replay["fail_reasons"] == ["no_l1_rows_for_candidate_window"]
    assert l1_replay["l1_rows_post_filter"] == 0
    assert l1_replay["trade_rows"] == 608227
    assert l1_replay["events_missing_l1_in_event_window"] == 3
    assert l1_replay["event_window_l1_relation_counts"] == {"no_symbol_l1_rows": 3}
    assert l1_replay["dominant_missing_event_window_l1_relation"] == "no_symbol_l1_rows"
    assert l1_replay["boundary"] == "counterfactual_only_not_promotion_evidence"
    execution_realism = arm["detail"]["execution_realism"]
    assert execution_realism["source_ok"] is True
    assert execution_realism["verdict_status"] == "EXECUTION_REALISM_BLOCKED"
    assert execution_realism["short_exit_status"] == "SHORT_EXIT_RESEARCH_SIGNAL"
    assert execution_realism["best_short_exit_horizon"] == "240m"
    assert plan["arms"][0]["action"] == "RUN_READ_ONLY_CAPTURE"
    assert plan["arms"][0]["reason"] == "sample_count_below_gate"
    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    assert blocker["next_trigger"] == (
        "run_shallow_k_execution_realism_then_l1_replay_before_any_retune"
    )
    assert blocker["research_candidate_k_pct"] == 6.0
    assert blocker["research_candidate_touched_count"] == 1


def test_flash_dip_execution_realism_arm_preserves_short_exit_research_path(tmp_path):
    data = tmp_path / "openclaw"
    (data / "logs").mkdir(parents=True)
    (data / "logs" / "flash_dip_execution_realism.log").write_text(json.dumps({
        "ts_utc": "2026-06-20T01:18:00Z",
        "check": "flash_dip_execution_realism",
        "candidate_label": "K6_N2_C3_nf0.005",
        "k_pct": 6.0,
        "verdict_status": "EXECUTION_REALISM_BLOCKED",
        "fail_reasons": ["gate_buffer_nonpositive_annret"],
        "gate_buffer_bps": 10.0,
        "gate_filled": 68,
        "gate_distinct_days": 38,
        "gate_annret": -0.0255,
        "gate_maxdd": 0.0081,
        "short_exit_status": "SHORT_EXIT_RESEARCH_SIGNAL",
        "best_short_exit_horizon": "240m",
        "best_short_exit_annret": 0.0132,
        "best_short_exit_n_filled": 68,
        "best_short_exit_days": 38,
        "boundary": "counterfactual_only_not_promotion_evidence",
    }) + "\n", encoding="utf-8")

    arm = collect_flash_dip_execution_realism_arm(
        data,
        now_utc=dt.datetime(2026, 6, 20, 1, 30, tzinfo=dt.timezone.utc),
    )
    plan = build_discovery_plan([arm], now_utc=dt.datetime(2026, 6, 20, 1, 30, tzinfo=dt.timezone.utc))

    assert arm["gate_status"] == "CAPTURING"
    assert arm["sample_count"] == 68
    assert arm["artifacts_ready"] is False
    assert plan["arms"][0]["action"] == "WAIT"
    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    assert blocker["blocker_class"] == "data_coverage"
    assert blocker["primary_blocker"] == (
        "daily_exit_execution_realism_blocked_short_exit_needs_l1_replay"
    )
    assert blocker["next_trigger"] == (
        "run_l1_short_exit_replay_with_candidate_window_coverage_before_any_retune"
    )
    assert blocker["best_short_exit_horizon"] == "240m"
    assert blocker["best_short_exit_annret"] == 0.0132


def test_flash_dip_execution_realism_inherits_l1_historical_wait_actionability(tmp_path):
    data = tmp_path / "openclaw"
    (data / "logs").mkdir(parents=True)
    (data / "logs" / "flash_dip_execution_realism.log").write_text(json.dumps({
        "ts_utc": "2026-06-20T01:18:00Z",
        "check": "flash_dip_execution_realism",
        "candidate_label": "K6_N2_C3_nf0.005",
        "k_pct": 6.0,
        "verdict_status": "EXECUTION_REALISM_BLOCKED",
        "fail_reasons": ["gate_buffer_nonpositive_annret"],
        "gate_buffer_bps": 10.0,
        "gate_filled": 68,
        "gate_distinct_days": 38,
        "gate_annret": -0.0255,
        "gate_maxdd": 0.0081,
        "short_exit_status": "SHORT_EXIT_RESEARCH_SIGNAL",
        "best_short_exit_horizon": "240m",
        "best_short_exit_annret": 0.0132,
        "best_short_exit_n_filled": 68,
        "best_short_exit_days": 38,
    }) + "\n", encoding="utf-8")
    (data / "logs" / "flash_dip_l1_short_exit_replay.log").write_text(json.dumps({
        "ts_utc": "2026-06-20T01:20:00Z",
        "check": "flash_dip_l1_short_exit_replay",
        "verdict_status": "L1_SHORT_EXIT_INSUFFICIENT_SAMPLE",
        "fail_reasons": ["no_l1_rows_for_candidate_event_windows"],
        "candidate_events": 6,
        "events_missing_l1_in_event_window": 6,
        "dominant_missing_event_window_l1_relation": "candidate_window_before_symbol_l1_range",
        "coverage_action_status": "HISTORICAL_CANDIDATES_BEFORE_L1_CAPTURE_WAIT_NEXT_CANDIDATE",
        "coverage_action_reason": "candidate_windows_end_before_symbol_l1_capture_starts",
        "coverage_action_scorecard": {
            "status": "HISTORICAL_CANDIDATES_BEFORE_L1_CAPTURE_WAIT_NEXT_CANDIDATE",
            "reason": "candidate_windows_end_before_symbol_l1_capture_starts",
            "engineering_actionable": False,
            "next_trigger": "wait_for_next_flash_dip_candidate_after_l1_capture_start_then_replay",
        },
    }) + "\n", encoding="utf-8")

    arm = collect_flash_dip_execution_realism_arm(
        data,
        now_utc=dt.datetime(2026, 6, 20, 1, 30, tzinfo=dt.timezone.utc),
    )
    plan = build_discovery_plan([arm], now_utc=dt.datetime(2026, 6, 20, 1, 30, tzinfo=dt.timezone.utc))

    dependent = arm["detail"]["dependent_l1_short_exit_replay"]
    assert dependent["coverage_action_status"] == (
        "HISTORICAL_CANDIDATES_BEFORE_L1_CAPTURE_WAIT_NEXT_CANDIDATE"
    )
    assert dependent["engineering_actionable"] is False
    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    assert blocker["engineering_actionable"] is False
    assert blocker["next_trigger"] == (
        "wait_for_next_flash_dip_candidate_after_l1_capture_start_then_replay"
    )
    assert blocker["dependent_l1_coverage_action_status"] == (
        "HISTORICAL_CANDIDATES_BEFORE_L1_CAPTURE_WAIT_NEXT_CANDIDATE"
    )
    assert blocker["dependent_l1_engineering_actionable"] is False


def test_flash_dip_execution_realism_rejects_when_no_short_exit_signal(tmp_path):
    data = tmp_path / "openclaw"
    (data / "logs").mkdir(parents=True)
    (data / "logs" / "flash_dip_execution_realism.log").write_text(json.dumps({
        "ts_utc": "2026-06-20T01:18:00Z",
        "candidate_label": "K6_N2_C3_nf0.005",
        "verdict_status": "EXECUTION_REALISM_BLOCKED",
        "fail_reasons": ["gate_buffer_nonpositive_annret"],
        "gate_annret": -0.0255,
        "short_exit_status": "NO_SHORT_EXIT_RESEARCH_SIGNAL",
    }) + "\n", encoding="utf-8")

    arm = collect_flash_dip_execution_realism_arm(
        data,
        now_utc=dt.datetime(2026, 6, 20, 1, 30, tzinfo=dt.timezone.utc),
    )
    plan = build_discovery_plan([arm], now_utc=dt.datetime(2026, 6, 20, 1, 30, tzinfo=dt.timezone.utc))

    assert arm["gate_status"] == "REJECTED"
    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    assert blocker["blocker_class"] == "rejected_no_edge"
    assert blocker["primary_blocker"] == (
        "execution_realism_blocked_without_short_exit_research_signal"
    )


def test_runtime_runner_keeps_stale_flash_dip_touchability_non_blocking(tmp_path):
    data = tmp_path / "openclaw"
    (data / "logs").mkdir(parents=True)
    (data / "logs" / "flash_dip_death_rate.log").write_text(json.dumps({
        "ts_utc": "2026-06-20T00:53:01Z",
        "thresholds": {"min_n": 20},
        "n_closed_slots": 0,
        "n_deaths": 0,
        "death_rate_pct": None,
        "actionable": False,
        "alerted": False,
    }) + "\n", encoding="utf-8")
    (data / "logs" / "flash_dip_touchability.log").write_text(json.dumps({
        "ts_utc": "2026-06-18T00:10:00Z",
        "true_order_count": 18,
        "touched_count": 0,
    }) + "\n", encoding="utf-8")

    arm = collect_flash_dip_arm(
        data,
        now_utc=dt.datetime(2026, 6, 20, 1, 30, tzinfo=dt.timezone.utc),
    )

    assert arm["source_ok"] is True
    assert arm["gate_status"] == "CAPTURING"
    assert arm["detail"]["touchability"]["source_ok"] is False
    assert arm["detail"]["touchability"]["source_error"] == "stale_artifact"


def test_flash_dip_l1_replay_arm_surfaces_coverage_hole_as_capture(tmp_path):
    data = tmp_path / "openclaw"
    (data / "logs").mkdir(parents=True)
    (data / "logs" / "flash_dip_l1_short_exit_replay.log").write_text(json.dumps({
        "ts_utc": "2026-06-20T01:20:00Z",
        "verdict_status": "L1_SHORT_EXIT_INSUFFICIENT_SAMPLE",
        "fail_reasons": ["no_l1_rows_for_candidate_event_windows", "gate_horizon_sample_below_min_filled"],
        "candidate_events": 6,
        "candidate_days": 2,
        "l1_rows_post_filter": 173749,
        "trade_rows": 2757781,
        "symbols_with_l1": ["APTUSDT", "ATOMUSDT", "AVAXUSDT", "INJUSDT", "NEARUSDT"],
        "symbols_missing_l1": [],
        "event_window_maker_timeout_minutes": 1440,
        "events_with_l1_in_event_window": 0,
        "events_missing_l1_in_event_window": 6,
        "days_with_l1_in_event_window": 0,
        "days_missing_l1_in_event_window": 2,
        "event_window_l1_relation_counts": {"candidate_window_before_symbol_l1_range": 6},
        "dominant_missing_event_window_l1_relation": "candidate_window_before_symbol_l1_range",
        "coverage_action_status": "HISTORICAL_CANDIDATES_BEFORE_L1_CAPTURE_WAIT_NEXT_CANDIDATE",
        "coverage_action_reason": "candidate_windows_end_before_symbol_l1_capture_starts",
        "coverage_action_scorecard": {
            "status": "HISTORICAL_CANDIDATES_BEFORE_L1_CAPTURE_WAIT_NEXT_CANDIDATE",
            "reason": "candidate_windows_end_before_symbol_l1_capture_starts",
            "next_trigger": "wait_for_next_flash_dip_candidate_after_l1_capture_start_then_replay",
            "engineering_actionable": False,
            "events_missing_l1_in_event_window": 6,
            "l1_gap_hours": {"n": 6, "p50": 12.0},
        },
        "gate_exit_measured": 0,
        "gate_distinct_exit_days": 0,
    }) + "\n", encoding="utf-8")

    arm = collect_flash_dip_l1_replay_arm(
        data,
        now_utc=dt.datetime(2026, 6, 20, 1, 30, tzinfo=dt.timezone.utc),
    )
    plan = build_discovery_plan([arm], now_utc=dt.datetime(2026, 6, 20, 1, 30, tzinfo=dt.timezone.utc))

    assert arm["gate_status"] == "CAPTURING"
    assert arm["source_ok"] is True
    assert arm["sample_count"] == 0
    assert arm["artifacts_ready"] is False
    assert arm["detail"]["fail_reasons"][0] == "no_l1_rows_for_candidate_event_windows"
    assert arm["detail"]["l1_rows_post_filter"] == 173749
    assert arm["detail"]["events_missing_l1_in_event_window"] == 6
    assert arm["detail"]["event_window_l1_relation_counts"] == {
        "candidate_window_before_symbol_l1_range": 6,
    }
    assert arm["detail"]["dominant_missing_event_window_l1_relation"] == (
        "candidate_window_before_symbol_l1_range"
    )
    assert arm["detail"]["coverage_action_status"] == (
        "HISTORICAL_CANDIDATES_BEFORE_L1_CAPTURE_WAIT_NEXT_CANDIDATE"
    )
    assert plan["arms"][0]["action"] == "RUN_READ_ONLY_CAPTURE"
    blocker = plan["profitability_blocker_scorecard"]["arms"][0]
    assert blocker["coverage_action_status"] == (
        "HISTORICAL_CANDIDATES_BEFORE_L1_CAPTURE_WAIT_NEXT_CANDIDATE"
    )
    assert blocker["engineering_actionable"] is False
    assert blocker["next_trigger"] == (
        "wait_for_next_flash_dip_candidate_after_l1_capture_start_then_replay"
    )


def test_flash_dip_l1_replay_arm_ready_only_after_conditional_pass_sample_gate(tmp_path):
    data = tmp_path / "openclaw"
    (data / "logs").mkdir(parents=True)
    (data / "logs" / "flash_dip_l1_short_exit_replay.log").write_text(json.dumps({
        "ts_utc": "2026-06-20T01:20:00Z",
        "verdict_status": "L1_SHORT_EXIT_CONDITIONAL_PASS",
        "fail_reasons": [],
        "candidate_events": 45,
        "candidate_days": 24,
        "l1_rows_post_filter": 250000,
        "trade_rows": 700000,
        "gate_exit_measured": 35,
        "gate_distinct_exit_days": 22,
        "gate_annret": 0.03,
        "gate_maxdd": 0.02,
    }) + "\n", encoding="utf-8")

    arm = collect_flash_dip_l1_replay_arm(
        data,
        now_utc=dt.datetime(2026, 6, 20, 1, 30, tzinfo=dt.timezone.utc),
    )
    plan = build_discovery_plan([arm], now_utc=dt.datetime(2026, 6, 20, 1, 30, tzinfo=dt.timezone.utc))

    assert arm["gate_status"] == "READY"
    assert arm["artifacts_ready"] is True
    assert arm["sample_count"] == 35
    assert plan["arms"][0]["action"] == "READY_FOR_AEG_CHAIN"
    assert plan["arms"][0]["reason"] == "artifacts_ready_and_sample_gate_met"


def test_flash_dip_l1_replay_arm_blocks_stale_status(tmp_path):
    data = tmp_path / "openclaw"
    (data / "logs").mkdir(parents=True)
    (data / "logs" / "flash_dip_l1_short_exit_replay.log").write_text(json.dumps({
        "ts_utc": "2026-06-18T01:20:00Z",
        "verdict_status": "L1_SHORT_EXIT_CONDITIONAL_PASS",
        "gate_exit_measured": 35,
    }) + "\n", encoding="utf-8")

    arm = collect_flash_dip_l1_replay_arm(
        data,
        now_utc=dt.datetime(2026, 6, 20, 14, 0, tzinfo=dt.timezone.utc),
    )
    plan = build_discovery_plan([arm], now_utc=dt.datetime(2026, 6, 20, 14, 0, tzinfo=dt.timezone.utc))

    assert arm["gate_status"] == "SOURCE_FAILURE"
    assert arm["source_ok"] is False
    assert arm["source_error"] == "stale_artifact"
    assert plan["arms"][0]["action"] == "BLOCK"
    assert plan["arms"][0]["reason"] == "source_not_healthy"


def test_edge_snapshot_adapter_only_promotes_durable_non_bull_concrete_rows():
    durable = {
        "final_label": "durable-alpha candidate",
        "strategy_family": "flash_dip_buy",
        "symbol": "BTCUSDT",
        "regime": "bear",
        "net_bps": 7.5,
        "n_independent": 35,
        "psr_0": 0.97,
        "dsr_k": 0.96,
        "pbo": 0.20,
        "reject_reasons": "[]",
        "parameter_cell_id": "k15",
    }
    bull = {**durable, "symbol": "ETHUSDT", "regime": "bull"}
    aggregate = {**durable, "symbol": "__AGGREGATE__"}
    rejected = {**durable, "symbol": "SOLUSDT", "reject_reasons": json.dumps(["cost_wall"])}

    assert row_is_live_grade(durable) is True
    assert row_is_live_grade(bull) is False
    snapshot = build_edge_snapshot(
        [durable, bull, aggregate, rejected],
        now_utc=dt.datetime(2026, 6, 19, tzinfo=dt.timezone.utc),
    )
    assert snapshot["_meta"]["n_cells"] == 1
    assert snapshot["flash_dip_buy::BTCUSDT"]["runtime_bps"] == 7.5
    assert "flash_dip_buy::ETHUSDT" not in snapshot
    assert snapshot["_meta"]["updated_at"].startswith("2026-06-19T00:00:00")


def test_flash_dip_ladder_builds_counterfactual_packets_not_promotion_proof():
    rows = [
        {
            "symbol": "BTCUSDT",
            "date": "2026-06-01",
            "regime": "bear",
            "prior_close": 100.0,
            "forward_low": 84.0,
            "exit_close": 95.0,
            "is_oos": True,
        },
        {
            "symbol": "ETHUSDT",
            "date": "2026-06-02",
            "regime": "chop",
            "prior_close": 100.0,
            "forward_low": 93.0,
            "exit_close": 98.0,
            "is_oos": False,
        },
    ]
    packets, summary = build_flash_dip_ladder_packets(rows=rows, k_pcts=[5, 15], cost_bps=4.0)

    assert len(packets) == 2
    assert summary["promotion_blocker"] == "counterfactual_only_not_promotion_evidence"
    k15 = next(packet for packet in packets if packet["parameter_cell_id"] == "k_15pct")
    assert k15["evidence_tier"] == "counterfactual_replay"
    assert k15["promotion_blocker"] == "counterfactual_only_not_promotion_evidence"
    assert len(k15["samples"]) == 1
    report, direct_summary = build_direct_report_from_packet(k15, run_id="flash-dip-ladder")
    assert direct_summary["sample_count"] == 1
    assert report["candidate_id"].endswith("k_15pct")


def test_alpha_discovery_throughput_static_no_runtime_or_db_write_route():
    pkg = Path(__file__).resolve().parents[1] / "alpha_discovery_throughput"
    code = "\n".join(path.read_text(encoding="utf-8") for path in pkg.glob("*.py"))
    forbidden = (
        "psycopg2",
        "asyncpg",
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
        "OPENCLAW_ALLOW_MAINNET",
        "execution_authority",
        "authorization.json",
    )
    for needle in forbidden:
        assert needle not in code
