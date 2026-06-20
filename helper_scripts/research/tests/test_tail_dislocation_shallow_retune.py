"""Focused tests for the FlashDip shallow-K retune screen."""

from __future__ import annotations

import datetime as dt
import json

import pytest

import screen as base
import shallow_retune_screen as srs
import shallow_retune_adversarial as adv
import shallow_retune_execution_realism as execr
import shallow_retune_l1_short_exit_replay as l1replay


def _bars(symbol: str, *, n: int = 16) -> list[dict]:
    rows = []
    start = dt.date(2026, 1, 1)
    for i in range(n):
        day = start + dt.timedelta(days=i)
        close = 100.0 + i * 0.2
        # Every third day dips through K2 but not through K6, then reverts.
        low = close * (0.975 if i % 3 == 1 else 0.995)
        rows.append({
            "date": day.isoformat(),
            "open": close,
            "high": close * 1.02,
            "low": low,
            "close": close,
            "turnover": 1000.0,
            "_symbol": symbol,
        })
    return rows


def test_research_gate_requires_shallow_k_and_notional_cap():
    base_cell = {
        "k": 0.04,
        "notional_frac": 0.03,
        "positive_expectancy": True,
        "day_clustered_significant": True,
        "survivable_maxdd": True,
    }
    ok = srs.research_gate_status(
        base_cell,
        candidate_k_grid=(0.02, 0.03, 0.04, 0.05, 0.06),
        max_research_notional_frac=0.03,
    )
    assert ok["full_history_research_gate_pass"] is True

    ref_k = dict(base_cell, k=0.15)
    assert srs.research_gate_status(
        ref_k,
        candidate_k_grid=(0.02, 0.03, 0.04, 0.05, 0.06),
        max_research_notional_frac=0.03,
    )["fail_reasons"] == ["reference_k_not_shallow_candidate"]

    too_large = dict(base_cell, notional_frac=0.10)
    assert "notional_frac_above_research_cap" in srs.research_gate_status(
        too_large,
        candidate_k_grid=(0.02, 0.03, 0.04, 0.05, 0.06),
        max_research_notional_frac=0.03,
    )["fail_reasons"]


def test_report_marks_counterfactual_boundary_and_runtime_touch_context(tmp_path):
    touch_path = tmp_path / "flash_dip_touchability.log"
    touch_path.write_text(json.dumps({
        "check": "flash_dip_touchability",
        "current_k_pct": 15,
        "deepest_candidate_k_with_touch_pct": 6,
    }) + "\n")

    merged = {
        "BTCUSDT": _bars("BTCUSDT"),
        "AAAUSDT": _bars("AAAUSDT"),
    }
    btc_fwd, btc_regime = base.build_btc_helpers(merged["BTCUSDT"])
    report = srs.run_report_from_merged(
        merged,
        funding={},
        btc_fwd=btc_fwd,
        btc_regime=btc_regime,
        meta={"n_symbols": 2, "n_rest_cached": 0, "global_first": "2026-01-01", "global_last": "2026-01-16"},
        candidate_k_grid=(0.02,),
        reference_k_grid=(),
        hold_grid=(1,),
        cap_grid=(1,),
        notional_grid=(0.02,),
        max_finalists=1,
        touchability_path=str(touch_path),
    )

    assert report["params"]["candidate_k_pct_grid"] == [2.0]
    assert report["runtime_touchability_context"]["source_ok"] is True
    assert report["runtime_touchability_context"]["latest"]["deepest_candidate_k_with_touch_pct"] == 6
    assert len(report["grid"]) == 1
    assert report["grid"][0]["evidence_boundary"] == "counterfactual_only_not_promotion_evidence"
    assert "promotion_boundary" in report["verdict"]


def _candidate_for_adversarial_gate(*, death2=True, death3=True, dsr_eff=True, dsr_full=True):
    return {
        "g1_regime_attribution": {
            "full_day_clustered_boot_t": 3.0,
            "full_day_clustered_ci95": [0.01, 0.02],
            "leave_one_crash_out": [
                {"removed_rank": "top-1", "survives": True},
                {"removed_rank": "luna+ftx_named", "survives": True},
            ],
        },
        "g2_death_spiral_fixed_notional": {
            "death_spiral_mc": [
                {"cond_death_rate_per_entry": 0.02, "survivable_p95": death2},
                {"cond_death_rate_per_entry": 0.03, "survivable_p95": death3},
            ],
        },
        "g3_dsr": {
            "dsr_survives_effective_n": dsr_eff,
            "dsr_survives_full_trials": dsr_full,
        },
    }


def test_adversarial_gate_distinguishes_conditional_from_strong():
    assert adv.candidate_label(0.04, 2, 3, 0.03) == "K4_N2_C3_nf0.03"

    strong = adv.adversarial_gate_status(
        _candidate_for_adversarial_gate(),
        pbo={"pbo": 0.20},
    )
    assert strong["conditional_adversarial_candidate"] is True
    assert strong["strong_adversarial_candidate"] is True

    conditional = adv.adversarial_gate_status(
        _candidate_for_adversarial_gate(death3=False, dsr_full=False),
        pbo={"pbo": 0.40},
    )
    assert conditional["conditional_adversarial_candidate"] is True
    assert conditional["strong_adversarial_candidate"] is False
    assert "g2_death3pct_p95_fail" in conditional["fail_reasons"]
    assert "g3_dsr_full_trials_fail" in conditional["fail_reasons"]


def test_adversarial_gate_blocks_overfit_or_death2_failure():
    death_fail = adv.adversarial_gate_status(
        _candidate_for_adversarial_gate(death2=False),
        pbo={"pbo": 0.20},
    )
    assert death_fail["conditional_adversarial_candidate"] is False
    assert "g2_death2pct_p95_fail" in death_fail["fail_reasons"]

    pbo_fail = adv.adversarial_gate_status(
        _candidate_for_adversarial_gate(),
        pbo={"pbo": 0.75},
    )
    assert pbo_fail["conditional_adversarial_candidate"] is False
    assert "g3_pbo_overfit" in pbo_fail["fail_reasons"]


def test_intraday_fill_assessment_requires_through_buffer():
    event = {
        "symbol": "AAAUSDT",
        "entry_date": "2026-01-02",
        "exit_date": "2026-01-04",
        "entry_level": 95.0,
        "net_taker": 0.01,
        "net_maker": 0.012,
        "gross": 0.016,
    }
    bars = [
        {"open_ts_ms": 1767312000000, "low": 95.10, "high": 95.40, "close": 95.20},
        {"open_ts_ms": 1767312060000, "low": 94.98, "high": 95.20, "close": 95.05},
        {"open_ts_ms": 1767312360000, "low": 94.94, "high": 95.80, "close": 95.70},
    ]

    touch = execr.intraday_fill_assessment(event, bars, buffer_bps=0.0, markout_minutes=(5,))
    assert touch is not None
    assert touch["through_bps"] == pytest.approx(2.105263, rel=1e-6)
    assert touch["markout_bps@5m"] == pytest.approx(73.6842105, rel=1e-6)
    assert touch["short_exit_net_taker@5m"] == pytest.approx(
        73.6842105 / 10000.0 - 0.0002 - 0.00055,
        rel=1e-6,
    )

    five_bps = execr.intraday_fill_assessment(event, bars, buffer_bps=5.0, markout_minutes=(5,))
    assert five_bps is not None
    assert five_bps["first_fill_bar_low"] == pytest.approx(94.94)

    too_deep = execr.intraday_fill_assessment(event, bars, buffer_bps=10.0, markout_minutes=(5,))
    assert too_deep is None


def test_execution_realism_gate_separates_sample_and_hard_fail():
    rows = [
        {
            "execution_buffer_bps": 0.0,
            "n_filled_proxy": 40,
            "n_distinct_filled_days": 25,
            "fixed_notional": {"annualized_return": 0.02, "max_drawdown": 0.05},
        },
        {
            "execution_buffer_bps": 10.0,
            "n_filled_proxy": 35,
            "n_distinct_filled_days": 22,
            "fixed_notional": {"annualized_return": 0.01, "max_drawdown": 0.10},
        },
    ]
    ok = execr.execution_realism_gate(rows, gate_buffer_bps=10.0, min_filled=30, min_days=20)
    assert ok["status"] == "EXECUTION_REALISM_CONDITIONAL_PASS"

    sample_fail = execr.execution_realism_gate(rows, gate_buffer_bps=25.0, min_filled=30, min_days=20)
    assert sample_fail["status"] == "EXECUTION_REALISM_INSUFFICIENT_SAMPLE"
    assert "gate_buffer_missing" in sample_fail["fail_reasons"]

    rows[1]["fixed_notional"] = {"annualized_return": -0.01, "max_drawdown": 0.10}
    hard = execr.execution_realism_gate(rows, gate_buffer_bps=10.0, min_filled=30, min_days=20)
    assert hard["status"] == "EXECUTION_REALISM_BLOCKED"
    assert "gate_buffer_nonpositive_annret" in hard["fail_reasons"]


def test_short_exit_opportunity_summary_is_research_only():
    rows = [
        {
            "execution_buffer_bps": 10.0,
            "n_filled_proxy": 35,
            "n_distinct_filled_days": 22,
            "short_exit_horizons": {
                "15m": {
                    "mean_net_taker_per_trade": 0.001,
                    "pct_positive": 0.6,
                    "fixed_notional": {"annualized_return": 0.05, "max_drawdown": 0.02},
                },
                "60m": {
                    "mean_net_taker_per_trade": -0.001,
                    "pct_positive": 0.4,
                    "fixed_notional": {"annualized_return": -0.02, "max_drawdown": 0.03},
                },
            },
        },
        {
            "execution_buffer_bps": 25.0,
            "n_filled_proxy": 10,
            "n_distinct_filled_days": 8,
            "short_exit_horizons": {
                "15m": {
                    "mean_net_taker_per_trade": 0.01,
                    "pct_positive": 0.9,
                    "fixed_notional": {"annualized_return": 0.50, "max_drawdown": 0.01},
                },
            },
        },
    ]

    summary = execr.short_exit_opportunity_summary(rows, min_filled=30, min_days=20)
    assert summary["status"] == "SHORT_EXIT_RESEARCH_SIGNAL"
    assert summary["best"]["execution_buffer_bps"] == 10.0
    assert summary["best"]["horizon"] == "15m"
    assert "research-only" in summary["boundary"]


def _ts_ms(hour: int, minute: int = 0) -> int:
    ts = dt.datetime(2026, 1, 2, hour, minute, tzinfo=dt.timezone.utc)
    return int(ts.timestamp() * 1000)


def test_l1_limit_buy_replay_requires_queue_consumption_before_short_exit():
    event = {
        "symbol": "AAAUSDT",
        "entry_date": "2026-01-02",
        "entry_level": 100.0,
    }
    l1_rows = [
        {"ts_ms": _ts_ms(0, 0), "best_bid": 101.0, "best_ask": 101.1, "bid_size": 5.0},
        {"ts_ms": _ts_ms(0, 1), "best_bid": 100.0, "best_ask": 100.1, "bid_size": 10.0},
        {"ts_ms": _ts_ms(0, 3), "best_bid": 100.0, "best_ask": 100.1, "bid_size": 3.0},
        {"ts_ms": _ts_ms(4, 3), "best_bid": 102.0, "best_ask": 102.1, "bid_size": 8.0},
    ]
    trades = [
        {"ts_ms": _ts_ms(0, 2), "side": "Sell", "price": 100.0, "qty": 3.0},
        {"ts_ms": _ts_ms(0, 3), "side": "Sell", "price": 100.0, "qty": 7.0},
    ]

    back = l1replay.replay_limit_buy_short_exit(
        event,
        l1_rows,
        trades,
        queue_ahead_frac=1.0,
        horizon_minutes=(240,),
        maker_timeout_minutes=24 * 60,
    )
    assert back["fill_status"] == "FILLED"
    assert back["fill_outcome"] == "queue_fill"
    assert back["fill_ts_ms"] == _ts_ms(0, 3)
    assert back["short_exit"]["240m"]["net_taker"] == pytest.approx(0.02 - 0.0002 - 0.00055)

    front = l1replay.replay_limit_buy_short_exit(
        event,
        l1_rows,
        trades,
        queue_ahead_frac=0.0,
        horizon_minutes=(240,),
        maker_timeout_minutes=24 * 60,
    )
    assert front["fill_ts_ms"] == _ts_ms(0, 2)


def test_l1_limit_buy_replay_distinguishes_adverse_through():
    event = {
        "symbol": "AAAUSDT",
        "entry_date": "2026-01-02",
        "entry_level": 100.0,
    }
    l1_rows = [
        {"ts_ms": _ts_ms(0, 0), "best_bid": 101.0, "best_ask": 101.2, "bid_size": 5.0},
        {"ts_ms": _ts_ms(0, 5), "best_bid": 99.5, "best_ask": 99.7, "bid_size": 7.0},
        {"ts_ms": _ts_ms(1, 5), "best_bid": 98.0, "best_ask": 98.1, "bid_size": 9.0},
    ]
    out = l1replay.replay_limit_buy_short_exit(
        event,
        l1_rows,
        trade_rows=[],
        queue_ahead_frac=1.0,
        horizon_minutes=(60,),
        maker_timeout_minutes=24 * 60,
    )

    assert out["fill_status"] == "FILLED"
    assert out["fill_outcome"] == "book_through_fill"
    assert out["short_exit"]["60m"]["net_taker"] == pytest.approx(-0.02 - 0.0002 - 0.00055)


def test_l1_short_exit_gate_separates_sample_from_hard_fail():
    rows = [
        {
            "queue_ahead_frac": 1.0,
            "horizons": {
                "240m": {
                    "n_exit_measured": 35,
                    "n_distinct_exit_days": 22,
                    "fixed_notional": {"annualized_return": 0.02, "max_drawdown": 0.01},
                },
            },
        },
    ]
    ok = l1replay.l1_short_exit_gate(
        rows,
        gate_queue_ahead_frac=1.0,
        gate_horizon_minutes=240,
        min_filled=30,
        min_days=20,
    )
    assert ok["status"] == "L1_SHORT_EXIT_CONDITIONAL_PASS"

    sample = l1replay.l1_short_exit_gate(
        rows,
        gate_queue_ahead_frac=1.0,
        gate_horizon_minutes=240,
        min_filled=50,
        min_days=20,
    )
    assert sample["status"] == "L1_SHORT_EXIT_INSUFFICIENT_SAMPLE"

    rows[0]["horizons"]["240m"]["fixed_notional"] = {"annualized_return": -0.01, "max_drawdown": 0.01}
    hard = l1replay.l1_short_exit_gate(
        rows,
        gate_queue_ahead_frac=1.0,
        gate_horizon_minutes=240,
        min_filled=30,
        min_days=20,
    )
    assert hard["status"] == "L1_SHORT_EXIT_BLOCKED"
    assert "gate_horizon_nonpositive_annret" in hard["fail_reasons"]


def test_l1_coverage_reasons_downgrade_only_when_candidate_l1_is_missing():
    gate = {
        "status": "L1_SHORT_EXIT_CONDITIONAL_PASS",
        "fail_reasons": [],
    }
    events = [
        {"symbol": "AAAUSDT", "entry_date": "2026-01-02"},
        {"symbol": "BBBUSDT", "entry_date": "2026-01-02"},
    ]

    no_l1 = l1replay.l1_candidate_coverage_summary(events, {})
    no_l1_gate = l1replay.apply_l1_coverage_reasons(gate, no_l1)
    assert no_l1["symbols_missing_l1"] == ["AAAUSDT", "BBBUSDT"]
    assert no_l1_gate["status"] == "L1_SHORT_EXIT_INSUFFICIENT_SAMPLE"
    assert no_l1_gate["fail_reasons"][0] == "no_l1_rows_for_candidate_window"

    partial_l1 = l1replay.l1_candidate_coverage_summary(
        events,
        {"AAAUSDT": [{"ts_ms": _ts_ms(0)}]},
    )
    partial_gate = l1replay.apply_l1_coverage_reasons(gate, partial_l1)
    assert partial_l1["symbols_with_l1"] == ["AAAUSDT"]
    assert partial_l1["symbols_missing_l1"] == ["BBBUSDT"]
    assert partial_gate["status"] == "L1_SHORT_EXIT_INSUFFICIENT_SAMPLE"
    assert partial_gate["fail_reasons"][0] == "partial_l1_symbol_coverage"

    full_l1 = l1replay.l1_candidate_coverage_summary(
        events,
        {
            "AAAUSDT": [{"ts_ms": _ts_ms(0)}],
            "BBBUSDT": [{"ts_ms": _ts_ms(0)}],
        },
    )
    assert l1replay.apply_l1_coverage_reasons(gate, full_l1) == gate


def test_l1_coverage_reasons_detect_event_window_hole_when_symbol_l1_exists():
    gate = {
        "status": "L1_SHORT_EXIT_CONDITIONAL_PASS",
        "fail_reasons": [],
    }
    events = [
        {"symbol": "AAAUSDT", "entry_date": "2026-01-02", "entry_level": 100.0},
        {"symbol": "BBBUSDT", "entry_date": "2026-01-02", "entry_level": 200.0},
    ]

    broad_l1_without_event_window_rows = l1replay.l1_candidate_coverage_summary(
        events,
        {
            "AAAUSDT": [{"ts_ms": _ts_ms(1)}],
            "BBBUSDT": [{"ts_ms": _ts_ms(2)}],
        },
        maker_timeout_minutes=10,
    )
    covered_gate = l1replay.apply_l1_coverage_reasons(gate, broad_l1_without_event_window_rows)

    assert broad_l1_without_event_window_rows["symbols_missing_l1"] == []
    assert broad_l1_without_event_window_rows["n_events_with_l1_in_event_window"] == 0
    assert broad_l1_without_event_window_rows["n_events_missing_l1_in_event_window"] == 2
    assert broad_l1_without_event_window_rows["event_window_l1_relation_counts"] == {
        "candidate_window_before_symbol_l1_range": 2,
    }
    assert broad_l1_without_event_window_rows["events_missing_l1_in_event_window_sample"][0]["l1_relation"] == (
        "candidate_window_before_symbol_l1_range"
    )
    assert covered_gate["status"] == "L1_SHORT_EXIT_INSUFFICIENT_SAMPLE"
    assert covered_gate["fail_reasons"][0] == "no_l1_rows_for_candidate_event_windows"


def test_l1_coverage_reasons_detect_partial_event_window_coverage():
    gate = {
        "status": "L1_SHORT_EXIT_CONDITIONAL_PASS",
        "fail_reasons": [],
    }
    events = [
        {"symbol": "AAAUSDT", "entry_date": "2026-01-02", "entry_level": 100.0},
        {"symbol": "BBBUSDT", "entry_date": "2026-01-02", "entry_level": 200.0},
    ]

    partial_event_l1 = l1replay.l1_candidate_coverage_summary(
        events,
        {
            "AAAUSDT": [{"ts_ms": _ts_ms(0, 5)}],
            "BBBUSDT": [{"ts_ms": _ts_ms(2)}],
        },
        maker_timeout_minutes=10,
    )
    partial_gate = l1replay.apply_l1_coverage_reasons(gate, partial_event_l1)

    assert partial_event_l1["symbols_missing_l1"] == []
    assert partial_event_l1["n_events_with_l1_in_event_window"] == 1
    assert partial_event_l1["n_events_missing_l1_in_event_window"] == 1
    assert partial_event_l1["event_window_l1_rows_by_symbol_date"] == {
        "AAAUSDT:2026-01-02": 1,
        "BBBUSDT:2026-01-02": 0,
    }
    assert partial_event_l1["event_window_l1_relation_counts"] == {
        "candidate_window_before_symbol_l1_range": 1,
        "covered": 1,
    }
    assert partial_event_l1["event_window_l1_relation_by_symbol_date"] == {
        "AAAUSDT:2026-01-02": "covered",
        "BBBUSDT:2026-01-02": "candidate_window_before_symbol_l1_range",
    }
    assert partial_gate["status"] == "L1_SHORT_EXIT_INSUFFICIENT_SAMPLE"
    assert partial_gate["fail_reasons"][0] == "partial_l1_event_window_coverage"


def test_l1_candidate_coverage_splits_event_window_timing_holes():
    gate = {
        "status": "L1_SHORT_EXIT_CONDITIONAL_PASS",
        "fail_reasons": [],
    }
    events = [
        {"symbol": "AAAUSDT", "entry_date": "2026-01-02", "entry_level": 100.0},
        {"symbol": "BBBUSDT", "entry_date": "2026-01-02", "entry_level": 200.0},
        {"symbol": "CCCUSDT", "entry_date": "2026-01-02", "entry_level": 300.0},
        {"symbol": "DDDUSDT", "entry_date": "2026-01-02", "entry_level": 400.0},
    ]

    coverage = l1replay.l1_candidate_coverage_summary(
        events,
        {
            "AAAUSDT": [{"ts_ms": _ts_ms(1)}],
            "BBBUSDT": [{"ts_ms": _ts_ms(0) - 60 * 60 * 1000}],
            "CCCUSDT": [
                {"ts_ms": _ts_ms(0) - 60 * 60 * 1000},
                {"ts_ms": _ts_ms(1)},
            ],
            "DDDUSDT": [{"ts_ms": _ts_ms(0, 5)}],
        },
        maker_timeout_minutes=10,
    )
    covered_gate = l1replay.apply_l1_coverage_reasons(gate, coverage)

    assert coverage["event_window_l1_relation_counts"] == {
        "candidate_window_after_symbol_l1_range": 1,
        "candidate_window_before_symbol_l1_range": 1,
        "candidate_window_overlaps_symbol_l1_range_but_empty": 1,
        "covered": 1,
    }
    assert coverage["event_window_l1_relation_by_symbol_date"] == {
        "AAAUSDT:2026-01-02": "candidate_window_before_symbol_l1_range",
        "BBBUSDT:2026-01-02": "candidate_window_after_symbol_l1_range",
        "CCCUSDT:2026-01-02": "candidate_window_overlaps_symbol_l1_range_but_empty",
        "DDDUSDT:2026-01-02": "covered",
    }
    missing = {
        row["symbol"]: row
        for row in coverage["events_missing_l1_in_event_window_sample"]
    }
    assert missing["AAAUSDT"]["l1_gap_hours"] == pytest.approx(50 / 60)
    assert missing["BBBUSDT"]["l1_gap_hours"] == pytest.approx(1.0)
    assert missing["CCCUSDT"]["l1_gap_hours"] is None
    assert covered_gate["status"] == "L1_SHORT_EXIT_INSUFFICIENT_SAMPLE"
    assert covered_gate["fail_reasons"][0] == "partial_l1_event_window_coverage"
