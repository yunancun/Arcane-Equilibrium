"""Tests for sealed horizon cost-gate learning evidence packets."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import pytest

from alpha_discovery_throughput.profitability_path_scorecard import (
    build_profitability_path_scorecard,
)
from helper_scripts.research.tests.candidate_lineage_v2_test_support import (
    attach_candidate_lineage_v2,
)
from cost_gate_learning_lane.outcome_review import (
    BlockedOutcomeReviewConfig,
    build_blocked_signal_outcome_review,
    build_research_compatibility_blocked_signal_outcome_review_no_authority,
)
from cost_gate_learning_lane.runtime_adapter import read_jsonl_ledger
from cost_gate_learning_lane import (
    sealed_horizon_learning_evidence as sealed_horizon_module,
)
from cost_gate_learning_lane.sealed_horizon_learning_evidence import (
    SEALED_HORIZON_LEARNING_EVIDENCE_SCHEMA_VERSION,
    SealedHorizonLearningEvidenceConfig,
    _read_json_or_jsonl_rows,
    _run_from_args,
    _write_jsonl,
    build_sealed_horizon_learning_evidence_packet,
    build_sealed_horizon_learning_evidence_from_rows,
    build_sealed_horizon_reject_feature_sql,
    find_sealed_horizon_candidate,
    select_default_sealed_horizon_candidate,
)


def _sealed_plan() -> dict:
    return {
        "schema_version": "cost_gate_demo_learning_lane_plan_v1",
        "generated_at_utc": "2026-06-22T04:00:00+00:00",
        "status": "READY_FOR_DEMO_LEARNING_PROBE",
        "gate_status": "OPERATOR_REVIEW",
        "main_cost_gate_adjustment": "NONE",
        "learning_gate_adjustment": "SIDE_CELL_DEMO_PROBE_ONLY_AFTER_ADAPTER_WIRING",
        "order_authority": "NOT_GRANTED",
        "selected_probe_candidate_count": 1,
        "probe_candidates": [
            {
                "side_cell_key": "ma_crossover|BTCUSDT|Sell",
                "strategy_name": "ma_crossover",
                "symbol": "BTCUSDT",
                "side": "Sell",
                "reject_reason_code": "cost_gate_js_demo_negative_edge",
                "source_kind": "horizon_specific_sealed_replay",
                "learning_lane_action": "LEARNING_PROBE_CANDIDATE",
                "learning_lane_reason": (
                    "sealed_horizon_replay_revalidated_retiming_candidate"
                ),
                "outcome_horizon_minutes": 240,
                "learning_outcome_horizon_minutes": 240,
                "sealed_horizon_replay": {
                    "schema_version": "horizon_specific_sealed_replay_packet_v1",
                    "status": "SEALED_HORIZON_REPLAY_READY_FOR_OPERATOR_REVIEW",
                    "side_cell_key": "ma_crossover|BTCUSDT|Sell",
                    "best_horizon_minutes": 240,
                    "best_avg_net_bps": 31.8707,
                    "best_net_positive_pct": 81.94,
                    "failed_gate_names": [],
                },
                "horizon_stability": {
                    "status": "MIXED_HORIZON_RESPONSE",
                    "best_horizon_minutes": 240,
                    "primary_horizon_minutes": 60,
                },
                "probe_proposal": {
                    "mode": "demo_only_learning_probe",
                    "max_probe_orders": 2,
                    "cooldown_minutes": 30,
                    "requires_runtime_policy_adapter": True,
                    "requires_probe_attempt_logging": True,
                    "requires_probe_outcome_logging": True,
                    "requires_candidate_horizon_outcome_logging": True,
                    "outcome_horizon_minutes": 240,
                    "learning_outcome_horizon_minutes": 240,
                },
                "guardrails": {
                    "main_cost_gate_adjustment": "NONE",
                    "may_bypass_main_live_gate": False,
                    "demo_only": True,
                    "notional_or_qty_not_granted_by_artifact": True,
                    "paper_not_promotion_evidence": True,
                },
            }
        ],
    }


def _expected_cost_artifact() -> dict:
    statistics = {
        "n": 500,
        "mean_abs": 2.0,
        "mean_signed": 1.0,
        "q50": 1.0,
        "q75": 4.0,
        "q90": 8.0,
        "cvar90": 8.0,
        "thin_sample": False,
    }
    return {
        "schema_version": "cost_gate_slippage_quantile_artifact_v2",
        "asof": "2026-07-10T12:00:00+00:00",
        "window_days": 90,
        "n_total_global": 500,
        "symbols": [{"symbol": "ZZZGLOBALUSDT", **statistics}],
        "global": statistics,
        "boundary": (
            "slippage quantile artifact only; PG source is read-only SELECT-only; "
            "no PG write, Bybit call, order, config, risk, auth, or runtime mutation"
        ),
    }


def _eligible_cohort(
    *,
    symbol: str,
    side: str,
    nets: tuple[float, ...],
    context_prefix: str,
) -> list[dict]:
    first_entry = dt.datetime(2026, 7, 4, 12, tzinfo=dt.timezone.utc)
    rows = []
    for index in range(30):
        net_bps = nets[index % len(nets)]
        entry = first_entry + dt.timedelta(days=index // 5, hours=index % 5)
        captured_at_ms = int(entry.timestamp() * 1_000)
        rows.append(
            attach_candidate_lineage_v2(
                {
                    "record_type": "blocked_signal_outcome",
                    "generated_at_utc": entry.isoformat(),
                    "entry_ts_ms": captured_at_ms,
                    "realized_net_bps": net_bps,
                    "gross_bps": net_bps + 15.0,
                    "cost_bps": 15.0,
                    "cost_model_version": "conservative_v1",
                },
                context_id=f"{context_prefix}-{index:02d}",
                captured_at_ms=captured_at_ms,
                strategy_name="ma_crossover",
                symbol=symbol,
                side=side,
                as_of_utc_date="2026-07-10",
            )
        )
    return rows


def test_sealed_jsonl_io_does_not_use_whole_file_text_helpers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "rows.jsonl"
    output = tmp_path / "output.jsonl"
    rows = [{"row": index} for index in range(3)]
    source.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    def forbid_read_text(*_args, **_kwargs):
        raise AssertionError("JSONL input must stream instead of read_text")

    monkeypatch.setattr(Path, "read_text", forbid_read_text)
    assert _read_json_or_jsonl_rows(source) == rows

    def forbid_write_text(*_args, **_kwargs):
        raise AssertionError("JSONL output must stream instead of write_text")

    monkeypatch.setattr(Path, "write_text", forbid_write_text)
    _write_jsonl(output, rows)
    with output.open("r", encoding="utf-8") as handle:
        assert [json.loads(line) for line in handle] == rows


def test_sealed_cli_uses_bounded_projections_and_dry_run_review_overlay(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plan = _sealed_plan()
    plan["generated_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    plan_path = tmp_path / "plan.json"
    source_rows = tmp_path / "source_rows.jsonl"
    source_prices = tmp_path / "source_prices.jsonl"
    source_rows_output = tmp_path / "source_rows_output.jsonl"
    ledger = tmp_path / "probe_ledger.jsonl"
    output = tmp_path / "sealed.json"
    review_output = tmp_path / "review.json"
    event_ts = int(
        dt.datetime(2026, 7, 15, 12, tzinfo=dt.timezone.utc).timestamp()
        * 1_000
    )
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    source_rows.write_text(
        json.dumps(
            {
                "ts": "2026-07-15T12:00:00+00:00",
                "ts_ms": event_ts,
                "context_id": "ctx-bounded-cli",
                "engine_mode": "demo",
                "strategy_name": "ma_crossover",
                "symbol": "BTCUSDT",
                "side": "Sell",
                "reject_reason_code": "cost_gate_js_demo_negative_edge",
                "last_price": 100.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    source_prices.write_text(
        json.dumps(
            {
                "symbol": "BTCUSDT",
                "ts_ms": event_ts + 240 * 60_000,
                "close": 99.0,
                "timeframe": "1m",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    ledger.write_text("", encoding="utf-8")

    def forbid_full_partition_reader(*_args, **_kwargs):
        raise AssertionError("production sealed CLI must not materialize full ledger")

    monkeypatch.setattr(
        sealed_horizon_module,
        "read_learning_ledger_partitions",
        forbid_full_partition_reader,
        raising=False,
    )
    packet = _run_from_args(
        argparse.Namespace(
            plan=plan_path,
            side_cell_key="ma_crossover|BTCUSDT|Sell",
            ledger=ledger,
            source_pg=False,
            source_rows=source_rows,
            price_source_pg=False,
            source_prices=source_prices,
            output=output,
            review_output=review_output,
            source_rows_output=source_rows_output,
            append_ledger=False,
            engine_modes=["demo", "live_demo"],
            lookback_hours=72,
            limit=500_000,
            maturity_buffer_minutes=0,
            horizon_minutes=60,
            outcome_cost_bps=4.0,
            max_entry_delay_ms=5 * 60_000,
            pg_timeframe="1m",
            pg_statement_timeout_ms=180_000,
            max_plan_age_hours=48,
            min_failed_outcomes_to_disable=8,
            min_outcome_net_positive_pct=50.0,
            min_avg_net_bps=0.0,
            min_review_outcomes_per_side_cell=1,
            min_review_effective_entries_per_side_cell=1,
            min_review_distinct_entry_utc_days=1,
            max_review_top_entry_day_share_pct=100.0,
            min_review_avg_net_bps=0.0,
            min_review_net_positive_pct=1.0,
            print_json=False,
        )
    )

    assert packet["materialization"]["raw_materialized_record_count"] == 1
    assert packet["outcomes"]["raw_blocked_signal_outcome_count"] == 1
    assert review_output.exists()
    assert (
        json.loads(review_output.read_text(encoding="utf-8"))[
            "source_ledger_row_count"
        ]
        == 1
    )
    assert ledger.read_text(encoding="utf-8") == ""


def test_sealed_horizon_reject_sql_filters_exact_mature_side_cell() -> None:
    plan = _sealed_plan()
    candidate = find_sealed_horizon_candidate(plan, "ma_crossover|BTCUSDT|Sell")
    cfg = SealedHorizonLearningEvidenceConfig(
        engine_modes=("demo",),
        lookback_hours=12,
        limit=123,
        maturity_buffer_minutes=5,
    )

    sql, params = build_sealed_horizon_reject_feature_sql(candidate, cfg)

    assert "f.ts <= now() - (%s::int * interval '1 minute')" in sql
    assert params == [
        ["demo"],
        12,
        245,
        "cost_gate_js_demo_negative_edge",
        "ma_crossover",
        "BTCUSDT",
        -1,
        123,
    ]


def test_default_sealed_horizon_candidate_selects_plan_replay_candidate() -> None:
    plan = _sealed_plan()
    plan["probe_candidates"].insert(
        0,
        {
            "side_cell_key": "ma_crossover|ETHUSDT|Sell",
            "source_kind": "legacy_scorecard_candidate",
        },
    )

    candidate = select_default_sealed_horizon_candidate(plan)

    assert candidate["side_cell_key"] == "ma_crossover|BTCUSDT|Sell"
    assert candidate["source_kind"] == "horizon_specific_sealed_replay"
    assert candidate["outcome_horizon_minutes"] == 240


def test_sealed_horizon_learning_evidence_records_240m_blocked_outcome(tmp_path) -> None:
    plan = _sealed_plan()
    event_ts = int(
        dt.datetime(2026, 6, 22, 0, 0, tzinfo=dt.timezone.utc).timestamp() * 1000
    )
    exit_ts = event_ts + 240 * 60_000
    feature_rows = [
        {
            "ts": "2026-06-22T00:00:00+00:00",
            "ts_ms": event_ts,
            "context_id": "ctx-demo-BTCUSDT-1",
            "engine_mode": "demo",
            "strategy_name": "ma_crossover",
            "symbol": "BTCUSDT",
            "side": "Sell",
            "reject_reason_code": "cost_gate_js_demo_negative_edge",
            "last_price": 100.0,
        }
    ]
    price_rows = [
        {
            "symbol": "BTCUSDT",
            "ts_ms": exit_ts,
            "close": 99.0,
            "timeframe": "1m",
        }
    ]
    ledger = tmp_path / "sealed_ledger.jsonl"
    cfg = SealedHorizonLearningEvidenceConfig(
        min_review_outcomes_per_side_cell=1,
        # F1:單筆 240m outcome fixture(n_eff=1),n_eff/天數欄顯式對齊到不攔
        # (單日單 entry;E2/E3 eligibility 本體由 evidence methodology 測試組直測)。
        min_review_effective_entries_per_side_cell=1,
        min_review_distinct_entry_utc_days=1,
        max_review_top_entry_day_share_pct=100.0,
        min_review_net_positive_pct=1.0,
    )

    packet, materialized, outcome_batch, review = (
        build_sealed_horizon_learning_evidence_from_rows(
            plan=plan,
            side_cell_key="ma_crossover|BTCUSDT|Sell",
            feature_rows=feature_rows,
            price_rows=price_rows,
            ledger_path=ledger,
            cfg=cfg,
            append_ledger=True,
            now_utc=dt.datetime(2026, 6, 22, 5, tzinfo=dt.timezone.utc),
        )
    )

    assert packet["schema_version"] == SEALED_HORIZON_LEARNING_EVIDENCE_SCHEMA_VERSION
    assert packet["status"] == "NO_QUALIFIED_LINEAGE_BLOCKED_SIGNAL_OUTCOMES"
    assert packet["answers"] == {
        "sealed_candidate_materialized": False,
        "blocked_signal_outcomes_recorded": False,
        "candidate_clears_operator_review_gate": False,
        "global_cost_gate_lowering_recommended": False,
        "main_cost_gate_adjustment": "NONE",
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "promotion_evidence": False,
    }
    assert materialized["decision_counts"] == {"ORDER_AUTHORITY_NOT_GRANTED": 1}
    assert packet["materialization"]["raw_materialized_record_count"] == 1
    assert outcome_batch["blocked_signal_outcome_count"] == 1
    assert packet["outcomes"]["raw_blocked_signal_outcome_count"] == 1
    assert packet["outcomes"]["blocked_signal_outcome_count"] == 0
    outcome = outcome_batch["blocked_signal_outcomes"][0]
    assert outcome["horizon_minutes"] == 240
    assert outcome["default_horizon_minutes"] == 60
    assert outcome["gross_bps"] == pytest.approx(100.0)
    # P1-2a:舊 4.0 常數的淨值移到 net_bps_optimistic;realized_net_bps 為保守權威淨值
    # (無分位 artifact → toml_tier 30bps fallback → cost≈92.3 → net≈7.7)。
    assert outcome["net_bps_optimistic"] == pytest.approx(96.0)
    assert review["top_side_cell_key"] is None
    assert len(read_jsonl_ledger(ledger)) == 2


def test_sealed_packet_quarantines_invalid_positive_lineage_from_outcome_metrics(
    tmp_path,
) -> None:
    plan = _sealed_plan()
    candidate = find_sealed_horizon_candidate(
        plan,
        "ma_crossover|BTCUSDT|Sell",
    )
    qualified = _eligible_cohort(
        symbol="BTCUSDT",
        side="Sell",
        nets=(9.0, 10.0, 11.0),
        context_prefix="ctx-sealed-qualified",
    )
    invalid = attach_candidate_lineage_v2(
        {
            "record_type": "blocked_signal_outcome",
            "realized_net_bps": 10_000.0,
            "gross_bps": 10_015.0,
            "cost_bps": 15.0,
            "cost_model_version": "conservative_v1",
        },
        context_id="ctx-sealed-invalid-positive",
        strategy_name="ma_crossover",
        symbol="ETHUSDT",
        side="Buy",
        as_of_utc_date="2026-07-10",
    )
    invalid["side_cell_key"] = "ma_crossover|ETHUSDT|Sell"
    review_cfg = BlockedOutcomeReviewConfig(
        min_outcomes_per_side_cell=1,
        min_effective_entries_per_side_cell=1,
        min_distinct_entry_utc_days=1,
        max_top_entry_day_share_pct=100.0,
        min_net_positive_pct=1.0,
    )
    baseline_review = build_blocked_signal_outcome_review(
        qualified,
        cfg=review_cfg,
        slippage_quantiles=_expected_cost_artifact(),
        now_utc=dt.datetime(2026, 7, 10, 18, tzinfo=dt.timezone.utc),
    )
    attacked_review = build_blocked_signal_outcome_review(
        [*qualified, invalid],
        cfg=review_cfg,
        slippage_quantiles=_expected_cost_artifact(),
        now_utc=dt.datetime(2026, 7, 10, 18, tzinfo=dt.timezone.utc),
    )

    def packet(rows, review):
        return build_sealed_horizon_learning_evidence_packet(
            plan=plan,
            candidate=candidate,
            feature_row_count=len(rows),
            materializer_batch={
                "records": [
                    {
                        "decision": "ORDER_AUTHORITY_NOT_GRANTED",
                        "side_cell_key": row.get("side_cell_key"),
                    }
                    for row in rows
                ],
                "materialized_record_count": len(rows),
                "appended_record_count": 0,
            },
            outcome_batch={
                "blocked_signal_outcomes": rows,
                "blocked_signal_outcome_count": len(rows),
                "appended_outcome_count": 0,
                "window_count": len(rows),
                "price_observation_count": len(rows),
                "horizon_minutes": 60,
            },
            review=review,
            ledger_path=tmp_path / "sealed_attack.jsonl",
            generated_at_utc=dt.datetime(
                2026, 7, 10, 18, tzinfo=dt.timezone.utc
            ),
        )

    baseline = packet(qualified, baseline_review)
    attacked = packet([*qualified, invalid], attacked_review)

    assert attacked["status"] == baseline["status"]
    assert attacked["review"] == baseline["review"]
    assert attacked["outcomes"]["blocked_signal_outcome_count"] == 30
    assert attacked["outcomes"]["outcome_count"] == 30
    assert attacked["outcomes"]["avg_net_bps"] == 10.0
    assert attacked["outcomes"]["net_positive_pct"] == 100.0
    assert attacked["answers"] == baseline["answers"]
    assert attacked["answers"]["candidate_clears_operator_review_gate"] is True
    assert attacked["outcomes"]["raw_blocked_signal_outcome_count"] == 31
    assert attacked["outcomes"]["raw_outcome_count"] == 31
    assert attacked["outcomes"]["raw_avg_net_bps"] == pytest.approx(10_300.0 / 31)
    assert attacked["materialization"]["input_feature_row_count"] == 30
    assert attacked["materialization"]["materialized_record_count"] == 30
    assert attacked["materialization"]["decision_counts"] == {
        "ORDER_AUTHORITY_NOT_GRANTED": 30
    }
    assert attacked["materialization"]["all_order_authority_not_granted"] is True
    assert attacked["materialization"]["raw_materialized_record_count"] == 31

    counterfactual = {
        "friction_bps": 4.0,
        "learning_lane_scorecard": {
            "profit_opportunity_ranking": {"top_side_cells": []},
            "horizon_stability_scorecard": {
                "top_side_cells": [
                    {
                        "side_cell_key": candidate["side_cell_key"],
                        "status": "MIXED_HORIZON_RESPONSE",
                        "candidate_horizons": [240],
                        "block_confirmed_horizons": [60],
                        "observed_horizons": [60, 240],
                        "best_horizon_minutes": 240,
                    }
                ]
            },
        },
    }
    sealed_replay = {
        "schema_version": "horizon_specific_sealed_replay_packet_v1",
        "status": "SEALED_HORIZON_REPLAY_READY_FOR_OPERATOR_REVIEW",
        "selection": {
            "selected": {
                "side_cell_key": candidate["side_cell_key"],
                "best_horizon_minutes": 240,
                "primary_horizon_minutes": 60,
            }
        },
        "replay_evaluation": {
            "failed_gate_names": [],
            "best_horizon": {"horizon_minutes": 240},
            "primary_horizon": {"horizon_minutes": 60},
        },
        "answers": {
            "sealed_replay_passed": True,
            "global_cost_gate_lowering_recommended": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
    }
    strict_scorecard = build_profitability_path_scorecard(
        cost_gate_counterfactual=counterfactual,
        horizon_sealed_replay=sealed_replay,
        horizon_learning_evidence=attacked,
        now_utc=dt.datetime(2026, 7, 10, 18, tzinfo=dt.timezone.utc),
    )
    strict_path = {
        row["path_id"]: row for row in strict_scorecard["top_paths"]
    }[f"horizon_edge_amplification:{candidate['side_cell_key']}"]
    assert strict_path["status"] == (
        "SEALED_HORIZON_LEARNING_EVIDENCE_READY_FOR_OPERATOR_REVIEW"
    )
    assert strict_path["evidence"]["sealed_learning_input_feature_row_count"] == 30
    assert strict_path["evidence"]["sealed_learning_materialized_record_count"] == 30
    assert strict_path["evidence"]["sealed_learning_blocked_signal_outcome_count"] == 30
    assert strict_path["evidence"]["sealed_learning_avg_net_bps"] == 10.0
    assert not any(
        key.startswith("sealed_learning_raw_")
        for key in strict_path["evidence"]
    )

    compatibility_review = (
        build_research_compatibility_blocked_signal_outcome_review_no_authority(
            [*qualified, invalid],
            cfg=review_cfg,
            now_utc=dt.datetime(2026, 7, 10, 18, tzinfo=dt.timezone.utc),
        )
    )
    assert compatibility_review["authority_eligible"] is False
    assert compatibility_review["operator_review_eligible"] is False
    compatibility_review["side_cell_key"] = candidate["side_cell_key"]
    compatibility_scorecard = build_profitability_path_scorecard(
        cost_gate_counterfactual=counterfactual,
        horizon_sealed_replay=sealed_replay,
        horizon_learning_evidence=compatibility_review,
        now_utc=dt.datetime(2026, 7, 10, 18, tzinfo=dt.timezone.utc),
    )
    compatibility_path = {
        row["path_id"]: row for row in compatibility_scorecard["top_paths"]
    }[f"horizon_edge_amplification:{candidate['side_cell_key']}"]
    assert compatibility_path["status"] == (
        "SEALED_HORIZON_REPLAY_READY_FOR_LEARNING_ACCUMULATION"
    )
    assert compatibility_path["evidence"][
        "sealed_learning_operator_review_ready"
    ] is False


def test_sealed_packet_scopes_counts_metrics_and_materialization_to_candidate(
    tmp_path,
) -> None:
    plan = _sealed_plan()
    candidate = find_sealed_horizon_candidate(
        plan,
        "ma_crossover|BTCUSDT|Sell",
    )
    selected = _eligible_cohort(
        symbol="BTCUSDT",
        side="Sell",
        nets=(-9.0, -10.0, -11.0),
        context_prefix="ctx-sealed-selected-scoped",
    )
    other_rows = _eligible_cohort(
        symbol="ETHUSDT",
        side="Buy",
        nets=(100.0, 150.0, 200.0),
        context_prefix="ctx-sealed-other-scoped",
    )
    rows = [*selected, *other_rows]
    review = build_blocked_signal_outcome_review(
        rows,
        cfg=BlockedOutcomeReviewConfig(
            min_outcomes_per_side_cell=1,
            min_effective_entries_per_side_cell=1,
            min_distinct_entry_utc_days=1,
            max_top_entry_day_share_pct=100.0,
            min_net_positive_pct=1.0,
        ),
        slippage_quantiles=_expected_cost_artifact(),
        now_utc=dt.datetime(2026, 7, 10, 18, tzinfo=dt.timezone.utc),
    )

    packet = build_sealed_horizon_learning_evidence_packet(
        plan=plan,
        candidate=candidate,
        feature_row_count=len(rows),
        materializer_batch={
            "records": [
                {
                    "decision": "ORDER_AUTHORITY_NOT_GRANTED",
                    "side_cell_key": row.get("side_cell_key"),
                }
                for row in rows
            ],
            "materialized_record_count": len(rows),
            "appended_record_count": len(rows),
        },
        outcome_batch={
            "blocked_signal_outcomes": rows,
            "blocked_signal_outcome_count": len(rows),
            "appended_outcome_count": len(rows),
            "window_count": len(rows),
            "price_observation_count": len(rows),
            "horizon_minutes": 60,
        },
        review=review,
        ledger_path=tmp_path / "sealed_scoped.jsonl",
        generated_at_utc=dt.datetime(
            2026, 7, 10, 18, tzinfo=dt.timezone.utc
        ),
    )

    assert review["blocked_signal_outcome_count"] == 60
    assert packet["materialization"]["input_feature_row_count"] == 30
    assert packet["materialization"]["materialized_record_count"] == 30
    assert packet["materialization"]["appended_record_count"] == 30
    assert packet["materialization"]["qualified_outcome_row_count"] == 30
    assert packet["outcomes"]["blocked_signal_outcome_count"] == 30
    assert packet["outcomes"]["outcome_count"] == 30
    assert packet["outcomes"]["avg_net_bps"] == -10.0
    assert packet["outcomes"]["avg_gross_bps"] == 5.0
    assert packet["outcomes"]["net_positive_pct"] == 0.0
    assert packet["outcomes"]["min_net_bps"] == -11.0
    assert packet["outcomes"]["max_net_bps"] == -9.0
    assert packet["review"]["top_side_cell_key"] == candidate["side_cell_key"]
    assert packet["review"]["blocked_signal_outcome_count"] == 30
    assert packet["answers"]["sealed_candidate_materialized"] is True
    assert packet["answers"]["candidate_clears_operator_review_gate"] is False


def test_sealed_packet_accepts_selected_candidate_that_is_not_global_top(
    tmp_path,
) -> None:
    plan = _sealed_plan()
    candidate = find_sealed_horizon_candidate(
        plan,
        "ma_crossover|BTCUSDT|Sell",
    )
    rows = [
        *_eligible_cohort(
            symbol="BTCUSDT",
            side="Sell",
            nets=(9.0, 10.0, 11.0),
            context_prefix="ctx-sealed-non-top-selected",
        ),
        *_eligible_cohort(
            symbol="ETHUSDT",
            side="Buy",
            nets=(99.0, 100.0, 101.0),
            context_prefix="ctx-sealed-non-top-global",
        ),
    ]
    review = build_blocked_signal_outcome_review(
        rows,
        cfg=BlockedOutcomeReviewConfig(
            min_outcomes_per_side_cell=1,
            min_effective_entries_per_side_cell=1,
            min_distinct_entry_utc_days=1,
            max_top_entry_day_share_pct=100.0,
            min_net_positive_pct=1.0,
        ),
        slippage_quantiles=_expected_cost_artifact(),
        now_utc=dt.datetime(2026, 7, 10, 18, tzinfo=dt.timezone.utc),
    )
    selected_review_row = next(
        row
        for row in review["top_side_cells"]
        if row["side_cell_key"] == candidate["side_cell_key"]
    )
    assert selected_review_row["review_candidate"] is True
    assert selected_review_row["review_rank"] > 1

    packet = build_sealed_horizon_learning_evidence_packet(
        plan=plan,
        candidate=candidate,
        feature_row_count=len(rows),
        materializer_batch={
            "records": [
                {
                    "decision": "ORDER_AUTHORITY_NOT_GRANTED",
                    "side_cell_key": row.get("side_cell_key"),
                }
                for row in rows
            ],
            "materialized_record_count": len(rows),
            "appended_record_count": 0,
        },
        outcome_batch={
            "blocked_signal_outcomes": rows,
            "blocked_signal_outcome_count": len(rows),
            "appended_outcome_count": 0,
            "window_count": len(rows),
            "price_observation_count": len(rows),
            "horizon_minutes": 60,
        },
        review=review,
        ledger_path=tmp_path / "sealed_non_top.jsonl",
        generated_at_utc=dt.datetime(
            2026, 7, 10, 18, tzinfo=dt.timezone.utc
        ),
    )

    assert review["top_side_cell_key"] != candidate["side_cell_key"]
    assert packet["review"]["top_side_cell_key"] == candidate["side_cell_key"]
    assert packet["answers"]["candidate_clears_operator_review_gate"] is True


def test_sealed_packet_requires_selected_identity_for_materialization_counts(
    tmp_path,
) -> None:
    plan = _sealed_plan()
    candidate = find_sealed_horizon_candidate(
        plan,
        "ma_crossover|BTCUSDT|Sell",
    )
    selected = _eligible_cohort(
        symbol="BTCUSDT",
        side="Sell",
        nets=(9.0, 10.0, 11.0),
        context_prefix="ctx-sealed-materializer-identity",
    )
    review = build_blocked_signal_outcome_review(
        selected,
        cfg=BlockedOutcomeReviewConfig(
            min_outcomes_per_side_cell=1,
            min_effective_entries_per_side_cell=1,
            min_distinct_entry_utc_days=1,
            max_top_entry_day_share_pct=100.0,
            min_net_positive_pct=1.0,
        ),
        slippage_quantiles=_expected_cost_artifact(),
        now_utc=dt.datetime(2026, 7, 10, 18, tzinfo=dt.timezone.utc),
    )

    def packet(materializer_batch):
        return build_sealed_horizon_learning_evidence_packet(
            plan=plan,
            candidate=candidate,
            feature_row_count=2,
            materializer_batch=materializer_batch,
            outcome_batch={
                "blocked_signal_outcomes": selected,
                "blocked_signal_outcome_count": 30,
                "appended_outcome_count": 0,
                "window_count": 30,
                "price_observation_count": 30,
                "horizon_minutes": 60,
            },
            review=review,
            ledger_path=tmp_path / "sealed_materializer_identity.jsonl",
            generated_at_utc=dt.datetime(
                2026, 7, 10, 18, tzinfo=dt.timezone.utc
            ),
        )

    other_only = packet(
        {
            "records": [
                {
                    "decision": "ORDER_AUTHORITY_NOT_GRANTED",
                    "side_cell_key": "ma_crossover|ETHUSDT|Buy",
                }
            ],
            "materialized_record_count": 1,
            "appended_record_count": 1,
        }
    )
    assert other_only["materialization"]["input_feature_row_count"] == 0
    assert other_only["materialization"]["materialized_record_count"] == 0
    assert other_only["materialization"]["appended_record_count"] == 0
    assert other_only["materialization"]["decision_counts"] == {}
    assert other_only["materialization"]["all_order_authority_not_granted"] is False
    assert other_only["materialization"]["raw_materialized_record_count"] == 1
    assert other_only["answers"]["sealed_candidate_materialized"] is False
    assert other_only["outcomes"]["blocked_signal_outcome_count"] == 30

    partial_append = packet(
        {
            "records": [
                {
                    "decision": "ORDER_AUTHORITY_NOT_GRANTED",
                    "side_cell_key": candidate["side_cell_key"],
                },
                {
                    "decision": "ORDER_AUTHORITY_NOT_GRANTED",
                    "side_cell_key": "ma_crossover|ETHUSDT|Buy",
                },
            ],
            "materialized_record_count": 2,
            "appended_record_count": 1,
        }
    )
    assert partial_append["materialization"]["materialized_record_count"] == 1
    assert partial_append["materialization"]["appended_record_count"] == 0
    assert partial_append["answers"]["sealed_candidate_materialized"] is True


def test_sealed_packet_uses_full_strict_lookup_for_rank_beyond_display_cap(
    tmp_path,
) -> None:
    plan = _sealed_plan()
    candidate = find_sealed_horizon_candidate(
        plan,
        "ma_crossover|BTCUSDT|Sell",
    )
    selected = _eligible_cohort(
        symbol="BTCUSDT",
        side="Sell",
        nets=(9.0, 10.0, 11.0),
        context_prefix="ctx-sealed-rank-beyond-cap-selected",
    )
    higher_ranked = [
        row
        for index in range(17)
        for row in _eligible_cohort(
            symbol=f"ALT{index:02d}USDT",
            side="Buy",
            nets=tuple(100.0 + index + jitter for jitter in (-1.0, 0.0, 1.0)),
            context_prefix=f"ctx-sealed-rank-beyond-cap-{index:02d}",
        )
    ]
    rows = [*selected, *higher_ranked]
    review_cfg = BlockedOutcomeReviewConfig(
        min_outcomes_per_side_cell=1,
        min_effective_entries_per_side_cell=1,
        min_distinct_entry_utc_days=1,
        max_top_entry_day_share_pct=100.0,
        min_net_positive_pct=1.0,
    )
    review = build_blocked_signal_outcome_review(
        rows,
        cfg=review_cfg,
        slippage_quantiles=_expected_cost_artifact(),
        now_utc=dt.datetime(2026, 7, 10, 18, tzinfo=dt.timezone.utc),
    )

    assert len(review["top_side_cells"]) == 16
    assert not any(
        row["side_cell_key"] == candidate["side_cell_key"]
        for row in review["top_side_cells"]
    )
    selected_lookup = review["strict_side_cell_reviews_by_key"][
        candidate["side_cell_key"]
    ]
    assert selected_lookup["review_rank"] > 16
    assert selected_lookup["review_candidate"] is True

    packet = build_sealed_horizon_learning_evidence_packet(
        plan=plan,
        candidate=candidate,
        feature_row_count=1,
        materializer_batch={
            "records": [
                {
                    "decision": "ORDER_AUTHORITY_NOT_GRANTED",
                    "side_cell_key": candidate["side_cell_key"],
                }
            ],
            "materialized_record_count": 1,
            "appended_record_count": 1,
        },
        outcome_batch={
            "blocked_signal_outcomes": rows,
            "blocked_signal_outcome_count": len(rows),
            "appended_outcome_count": 0,
            "window_count": len(rows),
            "price_observation_count": len(rows),
            "horizon_minutes": 60,
        },
        review=review,
        ledger_path=tmp_path / "sealed_rank_beyond_cap.jsonl",
        generated_at_utc=dt.datetime(
            2026, 7, 10, 18, tzinfo=dt.timezone.utc
        ),
    )
    assert packet["review"]["top_side_cell_key"] == candidate["side_cell_key"]
    assert packet["outcomes"]["blocked_signal_outcome_count"] == 30
    assert packet["answers"]["candidate_clears_operator_review_gate"] is True

    compatibility = (
        build_research_compatibility_blocked_signal_outcome_review_no_authority(
            rows,
            cfg=review_cfg,
            now_utc=dt.datetime(2026, 7, 10, 18, tzinfo=dt.timezone.utc),
        )
    )
    assert "strict_side_cell_reviews_by_key" not in compatibility


def test_non_sealed_candidate_is_rejected() -> None:
    plan = _sealed_plan()
    plan["probe_candidates"][0]["source_kind"] = None

    with pytest.raises(ValueError, match="not a sealed horizon replay candidate"):
        find_sealed_horizon_candidate(plan, "ma_crossover|BTCUSDT|Sell")


def test_default_sealed_horizon_candidate_requires_sealed_replay() -> None:
    plan = _sealed_plan()
    plan["probe_candidates"][0]["source_kind"] = None

    with pytest.raises(ValueError, match="sealed horizon candidate not found"):
        select_default_sealed_horizon_candidate(plan)
