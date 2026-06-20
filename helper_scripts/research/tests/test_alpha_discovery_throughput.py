"""alpha_discovery_throughput focused tests."""

from __future__ import annotations

import datetime as dt
import json
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
    collect_flash_dip_execution_realism_arm,
    collect_flash_dip_arm,
    collect_flash_dip_l1_replay_arm,
    collect_polymarket_leadlag_arm,
    collect_runtime_arms,
    run_once,
)
from alpha_discovery_throughput.signal_manifest import build_signal_spec, validate_signal_manifest


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
                    "best_walk_forward_holdout_gross_candidate": {
                        "name": "symbol=ADAUSDT",
                        "holdout": {
                            "n_fill_only": 714,
                            "edge_before_fees_bps": 2.002,
                            "net_bps": -1.998,
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
    assert scorecard["top_blockers"][0]["arm_id"] == "mm_verdict_maker_edge"


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
            },
        },
    ], now_utc=dt.datetime(2026, 6, 20, 17, 10, tzinfo=dt.timezone.utc))

    row = plan["profitability_blocker_scorecard"]["arms"][0]
    assert row["blocker_class"] == "feature_family_no_edge"
    assert row["primary_blocker"] == "no_train_positive_walk_forward_feature_cell"
    assert row["secondary_blockers"][0]["blocker"] == (
        "current_maker_fee_exceeds_sample_gated_fill_sim_break_even"
    )


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

    assert result["killboard"]["is_fast_discovery_active"] is True
    assert result["killboard"]["source_present_count"] == 5
    assert result["killboard"]["ready_for_aeg_chain"] == 1
    assert result["killboard"]["block"] == 1
    latest = Path(result["written"]["latest"])
    assert latest.exists()
    loaded = json.loads(latest.read_text(encoding="utf-8"))
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
    assert (
        raw_arms["mm_verdict_maker_edge"]["detail"]["history_scorecard"]
        ["lower_fee_break_even_stability"]["status"]
    ) == "LOWER_FEE_BREAK_EVEN_REPEATS_ACROSS_WINDOWS"
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
    assert arm["detail"]["preliminary_raw_candidate_count"] == 2
    assert arm["detail"]["max_bh_q"] == 0.10
    assert plan["arms"][0]["action"] == "READY_FOR_AEG_CHAIN"
    assert plan["arms"][0]["reason"] == "artifacts_ready_and_sample_gate_met"


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
