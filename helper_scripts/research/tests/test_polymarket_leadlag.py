"""Polymarket lead-lag IC harness tests."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from polymarket_leadlag import (
    BUCKET_EVENT_REG,
    BUCKET_EVENT_REG_DIRECT,
    BUCKET_EVENT_REG_MACRO,
    BUCKET_OTHER,
    BUCKET_PRICE_TARGET,
    STATUS_INSUFFICIENT_SAMPLE,
    SYMBOL_SOURCE_ASSET_DIRECT,
    SYMBOL_SOURCE_MACRO_EVENT_REG,
)
from polymarket_leadlag import candidate_replay, replay_history
from polymarket_leadlag import harness


def _write_run(root: Path, run_id: str, ts: str, rows: list[dict]) -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(json.dumps({
        "run_id": run_id,
        "mode": "hourly-topn",
        "lane": "snapshot",
        "point_in_time": True,
        "query_set_version": "v2",
    }), encoding="utf-8")
    with open(run_dir / "snapshots.jsonl", "w", encoding="utf-8") as fh:
        for row in rows:
            payload = {
                "snapshot_ts_utc": ts,
                "query_set_version": "v2",
                "outcomes": ["Yes", "No"],
                "row_source": "public_search",
                **row,
            }
            fh.write(json.dumps(payload, sort_keys=True))
            fh.write("\n")
    return run_dir


def _price_rows(symbol: str, start: dt.datetime, prices: list[float]) -> list[dict]:
    out = []
    for i, px in enumerate(prices):
        ts = start + dt.timedelta(minutes=15 * i)
        out.append({"symbol": symbol, "ts_ms": int(ts.timestamp() * 1000), "price": px})
    return out


def test_bucket_classification_and_symbol_inference():
    price_row = {
        "question": "Will Bitcoin reach $90000 in June?",
        "event_title": "What price will Bitcoin hit in June?",
        "discovery_queries": ["tag:crypto"],
    }
    event_row = {
        "question": "Will the SEC approve a spot Ethereum ETF?",
        "event_title": "Ethereum ETF approval",
        "discovery_queries": ["kw:sec ethereum"],
    }
    assert harness.classify_bucket(price_row) == BUCKET_PRICE_TARGET
    assert harness.classify_bucket(event_row) == BUCKET_EVENT_REG
    assert harness.infer_symbol(price_row, {"BTCUSDT", "ETHUSDT"}) == "BTCUSDT"
    assert harness.infer_symbol(event_row, {"BTCUSDT", "ETHUSDT"}) == "ETHUSDT"
    assert harness.DEFAULT_SYMBOLS == ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT")
    assert harness.infer_symbol({"question": "Will Solana ETF approval happen?"}, set(harness.DEFAULT_SYMBOLS)) == "SOLUSDT"
    assert harness.infer_symbol({"question": "Will XRP lawsuit settle?"}, set(harness.DEFAULT_SYMBOLS)) == "XRPUSDT"
    assert harness.DEFAULT_MACRO_PROXY_SYMBOLS == ("BTCUSDT", "ETHUSDT")
    assert harness.infer_symbol_mappings({"question": "Will CPI increase crypto volatility?"}, set(harness.DEFAULT_SYMBOLS)) == [
        ("BTCUSDT", SYMBOL_SOURCE_MACRO_EVENT_REG),
        ("ETHUSDT", SYMBOL_SOURCE_MACRO_EVENT_REG),
    ]
    assert harness.infer_symbol_mappings({"question": "Will Bitcoin ETF approval happen?"}, set(harness.DEFAULT_SYMBOLS)) == [
        ("BTCUSDT", SYMBOL_SOURCE_ASSET_DIRECT),
    ]


def test_fixture_report_fails_closed_until_min_points(tmp_path):
    root = tmp_path / "pm"
    start = dt.datetime(2026, 6, 20, 0, 0, tzinfo=dt.timezone.utc)
    probs = [0.40, 0.46, 0.50]
    for i, prob in enumerate(probs):
        ts = (start + dt.timedelta(minutes=15 * i)).isoformat()
        _write_run(root, f"hourly-topn-{i}", ts, [{
            "market_id": "101",
            "question": "Will the SEC approve a spot Bitcoin ETF?",
            "event_title": "Bitcoin ETF approval",
            "discovery_queries": ["kw:sec bitcoin"],
            "outcome_prices": [prob, 1 - prob],
        }])
    rows, meta = harness.load_snapshot_rows(root, query_set_version="v2", mode="hourly-topn")
    price_rows = _price_rows("BTCUSDT", start, [100.0, 101.0, 102.0, 103.0, 104.0])
    report = harness.build_report(
        snapshot_rows=rows,
        snapshot_meta=meta,
        price_rows=price_rows,
        query_set_version="v2",
        mode="hourly-topn",
        symbols=("BTCUSDT",),
        horizons_minutes=(15,),
        min_points=20,
        max_align_lag_minutes=1,
        min_abs_ic=0.1,
        min_abs_t=1.0,
        max_bh_q=0.10,
        price_source="fixture",
    )
    assert report["verdict"]["status"] == STATUS_INSUFFICIENT_SAMPLE
    assert report["counts"]["snapshot_rows"] == 3
    assert report["counts"]["delta_rows"] == 2
    assert report["counts"]["feature_points"] == 4
    assert report["counts"]["joined_rows"] == 4
    assert report["counts"]["bucket_delta_counts"][BUCKET_EVENT_REG] == 2
    assert report["counts"]["feature_bucket_counts"] == {
        BUCKET_EVENT_REG: 2,
        BUCKET_EVENT_REG_DIRECT: 2,
    }
    assert report["counts"]["feature_bucket_view_counts"] == {
        "aggregate": 2,
        "source_split": 2,
    }


def test_generic_event_reg_maps_to_btc_eth_macro_proxy(tmp_path):
    root = tmp_path / "pm"
    start = dt.datetime(2026, 6, 20, 0, 0, tzinfo=dt.timezone.utc)
    for i, prob in enumerate((0.40, 0.45, 0.43)):
        ts = (start + dt.timedelta(minutes=15 * i)).isoformat()
        _write_run(root, f"hourly-topn-{i}", ts, [{
            "market_id": "macro-101",
            "question": "Will CPI increase crypto volatility?",
            "event_title": "Crypto CPI macro event",
            "discovery_queries": ["kw:cpi crypto"],
            "outcome_prices": [prob, 1 - prob],
        }])

    rows, _meta = harness.load_snapshot_rows(root, query_set_version="v2", mode="hourly-topn")
    deltas, delta_meta = harness.build_market_deltas(rows, allowed_symbols=set(harness.DEFAULT_SYMBOLS))
    features = harness.aggregate_features(deltas)
    split_features = harness.aggregate_features(deltas, include_source_splits=True)

    assert delta_meta["skipped"] == {}
    assert delta_meta["markets_with_rows"] == 1
    assert delta_meta["market_symbol_series_with_rows"] == 2
    assert delta_meta["symbol_source_counts"] == {"macro_event_reg": 6}
    assert len(deltas) == 4
    assert {(row["symbol"], row["symbol_source"]) for row in deltas} == {
        ("BTCUSDT", SYMBOL_SOURCE_MACRO_EVENT_REG),
        ("ETHUSDT", SYMBOL_SOURCE_MACRO_EVENT_REG),
    }
    assert {(row["symbol"], row["bucket"]) for row in features} == {
        ("BTCUSDT", BUCKET_EVENT_REG),
        ("ETHUSDT", BUCKET_EVENT_REG),
    }
    assert {(row["symbol"], row["bucket"], row["bucket_view"]) for row in split_features} == {
        ("BTCUSDT", BUCKET_EVENT_REG, "aggregate"),
        ("ETHUSDT", BUCKET_EVENT_REG, "aggregate"),
        ("BTCUSDT", BUCKET_EVENT_REG_MACRO, "source_split"),
        ("ETHUSDT", BUCKET_EVENT_REG_MACRO, "source_split"),
    }
    assert {row["symbol_source"] for row in split_features if row["bucket"] == BUCKET_EVENT_REG_MACRO} == {
        SYMBOL_SOURCE_MACRO_EVENT_REG,
    }


def test_event_reg_source_splits_keep_macro_and_direct_separate(tmp_path):
    root = tmp_path / "pm"
    start = dt.datetime(2026, 6, 20, 0, 0, tzinfo=dt.timezone.utc)
    for i, (direct_prob, macro_prob) in enumerate(((0.40, 0.55), (0.45, 0.58), (0.43, 0.56))):
        ts = (start + dt.timedelta(minutes=15 * i)).isoformat()
        _write_run(root, f"hourly-topn-{i}", ts, [
            {
                "market_id": "direct-btc",
                "question": "Will the SEC approve a spot Bitcoin ETF?",
                "event_title": "Bitcoin ETF approval",
                "discovery_queries": ["kw:sec bitcoin"],
                "outcome_prices": [direct_prob, 1 - direct_prob],
            },
            {
                "market_id": "macro-101",
                "question": "Will CPI increase crypto volatility?",
                "event_title": "Crypto CPI macro event",
                "discovery_queries": ["kw:cpi crypto"],
                "outcome_prices": [macro_prob, 1 - macro_prob],
            },
        ])

    rows, _meta = harness.load_snapshot_rows(root, query_set_version="v2", mode="hourly-topn")
    deltas, delta_meta = harness.build_market_deltas(rows, allowed_symbols=set(harness.DEFAULT_SYMBOLS))
    features = harness.aggregate_features(deltas, include_source_splits=True)
    latest_ts = int((start + dt.timedelta(minutes=30)).timestamp() * 1000)

    assert delta_meta["symbol_source_counts"] == {
        SYMBOL_SOURCE_ASSET_DIRECT: 3,
        SYMBOL_SOURCE_MACRO_EVENT_REG: 6,
    }
    btc_features = [
        row for row in features
        if row["snapshot_ts_ms"] == latest_ts and row["symbol"] == "BTCUSDT"
    ]
    by_bucket = {row["bucket"]: row for row in btc_features}
    assert set(by_bucket) == {BUCKET_EVENT_REG, BUCKET_EVENT_REG_DIRECT, BUCKET_EVENT_REG_MACRO}
    assert by_bucket[BUCKET_EVENT_REG]["bucket_view"] == "aggregate"
    assert by_bucket[BUCKET_EVENT_REG]["n_markets"] == 2
    assert by_bucket[BUCKET_EVENT_REG]["symbol_source_breakdown"] == {
        SYMBOL_SOURCE_ASSET_DIRECT: 1,
        SYMBOL_SOURCE_MACRO_EVENT_REG: 1,
    }
    assert by_bucket[BUCKET_EVENT_REG_DIRECT]["market_ids"] == ["direct-btc"]
    assert by_bucket[BUCKET_EVENT_REG_MACRO]["market_ids"] == ["macro-101"]


def test_unmapped_non_macro_rows_emit_compact_diagnostics(tmp_path):
    root = tmp_path / "pm"
    start = dt.datetime(2026, 6, 20, 0, 0, tzinfo=dt.timezone.utc)
    for i, prob in enumerate((0.40, 0.45)):
        ts = (start + dt.timedelta(minutes=15 * i)).isoformat()
        _write_run(root, f"hourly-topn-{i}", ts, [{
            "market_id": "base-101",
            "question": "Will Base launch a token by June 30?",
            "event_title": "Base token launch",
            "market_slug": "will-base-launch-a-token",
            "event_slug": "will-base-launch-a-token",
            "discovery_queries": ["tag:crypto|order=volume24hr|top50"],
            "outcome_prices": [prob, 1 - prob],
        }])

    rows, _meta = harness.load_snapshot_rows(root, query_set_version="v2", mode="hourly-topn")
    deltas, delta_meta = harness.build_market_deltas(rows, allowed_symbols=set(harness.DEFAULT_SYMBOLS))
    diagnostics = delta_meta["unmapped_symbol_diagnostics"]

    assert deltas == []
    assert delta_meta["skipped"] == {"unmapped_symbol": 2}
    assert diagnostics["bucket_counts"] == {"other": 2}
    assert diagnostics["top_queries"] == {"tag:crypto|order=volume24hr|top50": 2}
    assert diagnostics["examples"][0]["market_slug"] == "will-base-launch-a-token"


def test_label_readiness_marks_unmatured_forward_target(tmp_path):
    root = tmp_path / "pm"
    start = dt.datetime(2026, 6, 20, 0, 0, tzinfo=dt.timezone.utc)
    for i, prob in enumerate((0.40, 0.46)):
        ts = (start + dt.timedelta(minutes=15 * i)).isoformat()
        _write_run(root, f"hourly-topn-{i}", ts, [{
            "market_id": "101",
            "question": "Will the SEC approve a spot Bitcoin ETF?",
            "event_title": "Bitcoin ETF approval",
            "discovery_queries": ["kw:sec bitcoin"],
            "outcome_prices": [prob, 1 - prob],
        }])
    rows, meta = harness.load_snapshot_rows(root, query_set_version="v2", mode="hourly-topn")
    price_rows = _price_rows("BTCUSDT", start, [100.0, 101.0])
    report = harness.build_report(
        snapshot_rows=rows,
        snapshot_meta=meta,
        price_rows=price_rows,
        query_set_version="v2",
        mode="hourly-topn",
        symbols=("BTCUSDT",),
        horizons_minutes=(15,),
        min_points=20,
        max_align_lag_minutes=1,
        min_abs_ic=0.1,
        min_abs_t=1.0,
        max_bh_q=0.10,
        price_source="fixture",
    )

    readiness = report["counts"]["label_readiness"]
    assert report["counts"]["delta_rows"] == 1
    assert report["counts"]["feature_points"] == 2
    assert report["counts"]["joined_rows"] == 0
    assert readiness["feature_horizon_pairs"] == 2
    assert readiness["joinable_pairs"] == 0
    assert readiness["status_counts"] == {"exit_target_after_latest_price": 2}
    assert readiness["by_horizon"]["15"] == {"exit_target_after_latest_price": 2}
    assert readiness["oldest_unmatured_exit_target_utc"] == "2026-06-20T00:30:00+00:00"


def test_join_forward_returns_uses_prices_at_or_after_snapshot():
    feature = {
        "snapshot_ts_ms": int(dt.datetime(2026, 6, 20, 0, 0, 30, tzinfo=dt.timezone.utc).timestamp() * 1000),
        "snapshot_ts_utc": "2026-06-20T00:00:30+00:00",
        "bucket": BUCKET_EVENT_REG,
        "symbol": "BTCUSDT",
        "n_markets": 1,
        "mean_delta_prob_yes": 0.05,
        "mean_abs_delta_prob_yes": 0.05,
        "market_ids": ["101"],
    }
    price_rows = [
        {"symbol": "BTCUSDT", "ts_ms": int(dt.datetime(2026, 6, 20, 0, 0, tzinfo=dt.timezone.utc).timestamp() * 1000), "price": 99.0},
        {"symbol": "BTCUSDT", "ts_ms": int(dt.datetime(2026, 6, 20, 0, 1, tzinfo=dt.timezone.utc).timestamp() * 1000), "price": 100.0},
        {"symbol": "BTCUSDT", "ts_ms": int(dt.datetime(2026, 6, 20, 0, 16, tzinfo=dt.timezone.utc).timestamp() * 1000), "price": 101.0},
    ]
    joined = harness.join_forward_returns(
        [feature], price_rows, horizons_minutes=(15,), max_align_lag_minutes=2,
    )
    assert len(joined) == 1
    assert joined[0]["entry_price"] == 100.0
    assert joined[0]["exit_price"] == 101.0
    assert round(joined[0]["forward_return_bps"], 6) == 100.0


def test_join_forward_returns_adds_trailing_return_control():
    feature = {
        "snapshot_ts_ms": int(
            dt.datetime(2026, 6, 20, 0, 15, 30, tzinfo=dt.timezone.utc).timestamp()
            * 1000
        ),
        "snapshot_ts_utc": "2026-06-20T00:15:30+00:00",
        "bucket": BUCKET_EVENT_REG,
        "symbol": "BTCUSDT",
        "n_markets": 1,
        "mean_delta_prob_yes": 0.05,
        "mean_abs_delta_prob_yes": 0.05,
        "market_ids": ["101"],
    }
    price_rows = [
        {"symbol": "BTCUSDT", "ts_ms": int(dt.datetime(2026, 6, 20, 0, 0, tzinfo=dt.timezone.utc).timestamp() * 1000), "price": 100.0},
        {"symbol": "BTCUSDT", "ts_ms": int(dt.datetime(2026, 6, 20, 0, 15, tzinfo=dt.timezone.utc).timestamp() * 1000), "price": 101.0},
        {"symbol": "BTCUSDT", "ts_ms": int(dt.datetime(2026, 6, 20, 0, 16, tzinfo=dt.timezone.utc).timestamp() * 1000), "price": 102.0},
        {"symbol": "BTCUSDT", "ts_ms": int(dt.datetime(2026, 6, 20, 0, 31, tzinfo=dt.timezone.utc).timestamp() * 1000), "price": 103.0},
    ]

    joined = harness.join_forward_returns(
        [feature], price_rows, horizons_minutes=(15,), max_align_lag_minutes=2,
    )

    assert len(joined) == 1
    assert joined[0]["entry_price"] == 102.0
    assert joined[0]["exit_price"] == 103.0
    assert joined[0]["trailing_entry_price"] == 100.0
    assert joined[0]["trailing_exit_price"] == 101.0
    assert round(joined[0]["trailing_return_bps"], 6) == 100.0


def test_compute_ic_reports_overlap_adjusted_sample_floor():
    base = dt.datetime(2026, 6, 20, 0, 0, tzinfo=dt.timezone.utc)
    rows = []
    for i in range(5):
        ts_ms = int((base + dt.timedelta(minutes=15 * i)).timestamp() * 1000)
        rows.append({
            "bucket": BUCKET_EVENT_REG,
            "symbol": "BTCUSDT",
            "horizon_minutes": 60,
            "snapshot_ts_ms": ts_ms,
            "snapshot_ts_utc": harness._ms_to_iso(ts_ms),
            "mean_delta_prob_yes": float(i),
            "forward_return_bps": float(i),
        })

    result = harness.compute_ic(rows)

    assert len(result) == 1
    assert result[0]["n_points"] == 5
    assert result[0]["n_distinct_timestamps"] == 5
    assert result[0]["n_nonoverlap_timestamps"] == 2
    assert result[0]["overlap_adjusted_sample_floor"] == 2
    assert result[0]["overlap_warning"] is True
    assert result[0]["overlap_jitter_tolerance_ms"] == 5000
    assert result[0]["effective_nonoverlap_gap_ms"] == 3_595_000
    assert result[0]["median_sample_spacing_ms"] == 900_000
    assert result[0]["last_nonoverlap_snapshot_ts_utc"] == "2026-06-20T01:00:00+00:00"
    assert result[0]["hac_lag"] == 3
    assert result[0]["hac_method"] == "newey_west_slope_t_stat_bartlett"


def test_compute_ic_reports_price_feedback_control():
    base = dt.datetime(2026, 6, 20, 0, 0, tzinfo=dt.timezone.utc)
    rows = []
    forward_returns = [1.0, -1.0, 0.5, -0.5, 0.3, -0.3]
    trailing_returns = [0.0, 4.0, 8.0, 13.0, 17.0, 22.0]
    for i, (forward_ret, trailing_ret) in enumerate(zip(forward_returns, trailing_returns)):
        ts_ms = int((base + dt.timedelta(minutes=15 * i)).timestamp() * 1000)
        rows.append({
            "bucket": BUCKET_EVENT_REG,
            "symbol": "BTCUSDT",
            "horizon_minutes": 15,
            "snapshot_ts_ms": ts_ms,
            "snapshot_ts_utc": harness._ms_to_iso(ts_ms),
            "mean_delta_prob_yes": float(i),
            "forward_return_bps": forward_ret,
            "trailing_return_bps": trailing_ret,
        })

    result = harness.compute_ic(rows)

    assert len(result) == 1
    assert result[0]["past_return_control_n_points"] == 6
    assert result[0]["past_return_ic_pearson"] is not None
    assert result[0]["past_return_ic_pearson"] > 0.99
    assert result[0]["lead_lag_abs_ic_margin"] is not None
    assert result[0]["lead_lag_abs_ic_margin"] < 0
    assert result[0]["price_feedback_warning"] is True
    assert result[0]["price_feedback_warning_basis"] == "abs_past_return_ic_ge_abs_forward_ic"


def test_compute_ic_reports_partial_ic_controlling_trailing_return():
    base = dt.datetime(2026, 6, 20, 0, 0, tzinfo=dt.timezone.utc)
    rows = []
    xs = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    trailing_returns = [0.0, 2.0, 4.0, 6.0, 8.0, 11.0]
    residual_noise = [1.0, -1.0, 1.0, -1.0, 1.0, -1.0]
    for i, (xval, trailing_ret, noise) in enumerate(zip(xs, trailing_returns, residual_noise)):
        ts_ms = int((base + dt.timedelta(minutes=15 * i)).timestamp() * 1000)
        rows.append({
            "bucket": BUCKET_PRICE_TARGET,
            "symbol": "BTCUSDT",
            "horizon_minutes": 15,
            "snapshot_ts_ms": ts_ms,
            "snapshot_ts_utc": harness._ms_to_iso(ts_ms),
            "mean_delta_prob_yes": xval,
            "forward_return_bps": trailing_ret * 3.0 + noise,
            "trailing_return_bps": trailing_ret,
        })

    result = harness.compute_ic(rows)

    assert len(result) == 1
    row = result[0]
    assert row["ic_pearson"] is not None
    assert row["ic_pearson"] > 0.95
    assert row["past_return_ic_pearson"] is not None
    assert row["past_return_ic_pearson"] > 0.95
    assert row["trailing_forward_return_ic_pearson"] is not None
    assert row["trailing_forward_return_ic_pearson"] > 0.95
    assert row["partial_ic_controlling_trailing_return"] is not None
    assert abs(row["partial_ic_controlling_trailing_return"]) < 0.15
    assert row["partial_ic_abs_margin_vs_raw"] < 0
    assert row["partial_ic_retained_abs_ratio"] < 0.5
    assert row["price_feedback_partial_collapse_warning"] is True
    assert (
        row["price_feedback_partial_collapse_basis"]
        == "partial_ic_collapses_after_trailing_return_control"
    )


def test_compute_ic_tolerates_small_15m_schedule_jitter():
    base = dt.datetime(2026, 6, 20, 0, 0, tzinfo=dt.timezone.utc)
    rows = []
    for i, offset_ms in enumerate((0, 899_400, 1_799_100, 2_700_200)):
        ts_ms = int(base.timestamp() * 1000) + offset_ms
        rows.append({
            "bucket": BUCKET_EVENT_REG,
            "symbol": "BTCUSDT",
            "horizon_minutes": 15,
            "snapshot_ts_ms": ts_ms,
            "snapshot_ts_utc": harness._ms_to_iso(ts_ms),
            "mean_delta_prob_yes": float(i),
            "forward_return_bps": float(i),
        })

    result = harness.compute_ic(rows)

    assert result[0]["n_points"] == 4
    assert result[0]["n_nonoverlap_timestamps"] == 4
    assert result[0]["overlap_adjusted_sample_floor"] == 4
    assert result[0]["overlap_warning"] is False
    assert result[0]["hac_lag"] == 0


def test_compute_ic_uses_jitter_tolerance_for_60m_cadence_floor_and_hac_lag():
    base_ms = int(dt.datetime(2026, 6, 20, 0, 0, tzinfo=dt.timezone.utc).timestamp() * 1000)
    rows = []
    for i in range(5):
        ts_ms = base_ms + i * 899_500
        rows.append({
            "bucket": BUCKET_EVENT_REG,
            "symbol": "BTCUSDT",
            "horizon_minutes": 60,
            "snapshot_ts_ms": ts_ms,
            "snapshot_ts_utc": harness._ms_to_iso(ts_ms),
            "mean_delta_prob_yes": float(i),
            "forward_return_bps": float(i),
        })

    result = harness.compute_ic(rows)

    assert result[0]["n_points"] == 5
    assert result[0]["n_nonoverlap_timestamps"] == 2
    assert result[0]["overlap_adjusted_sample_floor"] == 2
    assert result[0]["overlap_warning"] is True
    assert result[0]["hac_lag"] == 3


def test_hac_gate_blocks_naive_t_candidate():
    base = dt.datetime(2026, 6, 20, 0, 0, tzinfo=dt.timezone.utc)
    xs = [
        0.4676, 0.8674, 2.079, 3.0293, 4.167, 4.7196, 5.917, 6.8497,
        7.7851, 8.8312, 9.8975, 10.9426, 11.8187, 13.0844, 13.8905,
        14.3604, 16.2381, 16.9216, 17.8513, 19.0537, 20.046, 21.0106,
        21.8291, 23.0383, 23.6925, 25.2887, 25.7469, 26.9587, 28.0038,
        29.0438, 29.9507, 31.0966, 31.2731, 32.9532, 33.9421, 34.8873,
        36.2801, 36.7787, 37.9574, 38.5666,
    ]
    ys = [
        0.5454, -4.6783, -9.0109, -1.1081, 1.0908, 0.8023, 1.2591,
        -3.2387, -6.0902, -4.1393, -10.0499, -8.1082, -12.4667,
        -10.638, -12.8201, -6.1387, -2.0017, -3.1903, -8.3625, -9.5643,
        -8.4517, -10.2816, -8.0552, -3.785, -3.2303, -3.634, -0.539,
        -0.8344, 2.3764, 1.7342, 7.0416, 6.1297, 2.7164, 3.5499, 1.9467,
        -0.4158, 0.0704, 2.9901, -3.073, -2.1868,
    ]
    rows = []
    for i, (xval, yval) in enumerate(zip(xs, ys)):
        ts_ms = int((base + dt.timedelta(minutes=15 * i)).timestamp() * 1000)
        rows.append({
            "bucket": BUCKET_EVENT_REG,
            "symbol": "BTCUSDT",
            "horizon_minutes": 60,
            "snapshot_ts_ms": ts_ms,
            "snapshot_ts_utc": harness._ms_to_iso(ts_ms),
            "mean_delta_prob_yes": xval,
            "forward_return_bps": yval,
        })

    result = harness.compute_ic(rows)
    eligible, preliminary_raw, preliminary_hac, candidates = harness._partition_ic_candidates(
        result,
        min_points=10,
        min_abs_ic=0.15,
        min_abs_t=2.0,
        max_bh_q=1.0,
    )

    assert len(eligible) == 1
    assert len(preliminary_raw) == 1
    assert abs(result[0]["t_stat"]) > 2.0
    assert result[0]["t_stat_hac"] is not None
    assert abs(result[0]["t_stat_hac"]) < 2.0
    assert len(preliminary_hac) == 0
    assert len(candidates) == 0


def test_bh_gate_separates_raw_and_controlled_candidates(tmp_path):
    root = tmp_path / "pm"
    start = dt.datetime(2026, 6, 20, 0, 0, tzinfo=dt.timezone.utc)
    deltas = [0.005 + (i % 7) * 0.001 for i in range(34)]
    probs = [0.40]
    for delta in deltas:
        probs.append(probs[-1] + delta)
    prices = [100.0]
    for i in range(35):
        if i == 0:
            ret = 0.001
        else:
            noise = 0.0002 if i % 2 else -0.00016
            ret = deltas[i - 1] * 0.03 + noise
        prices.append(prices[-1] * (1.0 + ret))
    for i, prob in enumerate(probs):
        ts = (start + dt.timedelta(minutes=15 * i)).isoformat()
        _write_run(root, f"hourly-topn-{i}", ts, [{
            "market_id": "101",
            "question": "Will the SEC approve a spot Bitcoin ETF?",
            "event_title": "Bitcoin ETF approval",
            "discovery_queries": ["kw:sec bitcoin"],
            "outcome_prices": [prob, 1 - prob],
        }])
    rows, meta = harness.load_snapshot_rows(root, query_set_version="v2", mode="hourly-topn")
    report = harness.build_report(
        snapshot_rows=rows,
        snapshot_meta=meta,
        price_rows=_price_rows("BTCUSDT", start, prices),
        query_set_version="v2",
        mode="hourly-topn",
        symbols=("BTCUSDT",),
        horizons_minutes=(15,),
        min_points=20,
        max_align_lag_minutes=1,
        min_abs_ic=0.1,
        min_abs_t=1.0,
        max_bh_q=0.0,
        price_source="fixture",
    )

    assert report["verdict"]["preliminary_raw_candidate_count"] == 2
    assert report["verdict"]["preliminary_hac_candidate_count"] == 2
    assert report["verdict"]["significance_t_stat"] == "t_stat_hac"
    assert report["verdict"]["candidate_count"] == 0
    assert report["ic_results"][0]["p_value_approx_normal"] is not None
    assert report["ic_results"][0]["bh_q_value_approx"] is not None
    assert report["ic_results"][0]["p_value_hac_approx_normal"] is not None
    assert report["ic_results"][0]["bh_q_value_hac_approx"] is not None


def test_pre_gate_hac_watchlist_is_diagnostic_not_candidate(tmp_path):
    root = tmp_path / "pm"
    start = dt.datetime(2026, 6, 20, 0, 0, tzinfo=dt.timezone.utc)
    deltas = [0.005 + (i % 7) * 0.001 for i in range(34)]
    probs = [0.40]
    for delta in deltas:
        probs.append(probs[-1] + delta)
    prices = [100.0]
    for i in range(35):
        if i == 0:
            ret = 0.001
        else:
            noise = 0.0002 if i % 2 else -0.00016
            ret = deltas[i - 1] * 0.03 + noise
        prices.append(prices[-1] * (1.0 + ret))
    for i, prob in enumerate(probs):
        ts = (start + dt.timedelta(minutes=15 * i)).isoformat()
        _write_run(root, f"hourly-topn-{i}", ts, [{
            "market_id": "101",
            "question": "Will the SEC approve a spot Bitcoin ETF?",
            "event_title": "Bitcoin ETF approval",
            "discovery_queries": ["kw:sec bitcoin"],
            "outcome_prices": [prob, 1 - prob],
        }])
    rows, meta = harness.load_snapshot_rows(root, query_set_version="v2", mode="hourly-topn")
    report = harness.build_report(
        snapshot_rows=rows,
        snapshot_meta=meta,
        price_rows=_price_rows("BTCUSDT", start, prices),
        query_set_version="v2",
        mode="hourly-topn",
        symbols=("BTCUSDT",),
        horizons_minutes=(15,),
        min_points=40,
        max_align_lag_minutes=1,
        min_abs_ic=0.1,
        min_abs_t=1.0,
        max_bh_q=1.0,
        price_source="fixture",
    )

    assert report["verdict"]["status"] == STATUS_INSUFFICIENT_SAMPLE
    assert report["verdict"]["candidate_count"] == 0
    assert report["verdict"]["pre_gate_hac_watchlist_count"] == 2
    assert report["verdict"]["pre_gate_watchlist_persistence_status"] == (
        "SINGLE_REPORT_PRE_GATE_WATCHLIST"
    )
    assert report["counts"]["pre_gate_watchlist_persistence_scorecard"]["status"] == (
        "SINGLE_REPORT_PRE_GATE_WATCHLIST"
    )
    assert report["counts"]["min_samples_remaining_to_gate"] == 6
    assert report["counts"]["sample_gate_clock"]["status"] == "WAITING_FOR_SAMPLE"
    assert (
        report["counts"]["sample_gate_clock"]["fastest_gate_ready_utc"]
        == "2026-06-20T10:15:00+00:00"
    )
    assert len(report["pre_gate_hac_watchlist"]) == 2
    watch = report["pre_gate_hac_watchlist"][0]
    assert watch["bucket"] in {BUCKET_EVENT_REG, BUCKET_EVENT_REG_DIRECT}
    assert watch["sample_gap_to_min_points"] == 6
    assert watch["gate_blocker"] == "sample_floor_below_min_points"
    assert watch["bh_q_value_hac_approx"] is not None
    assert "partial_ic_controlling_trailing_return" in watch
    assert watch["expected_gate_label_ready_utc"] == "2026-06-20T10:15:00+00:00"
    assert watch["eta_basis"] == "overlap_adjusted_floor_forecast_gap_plus_forward_horizon"
    assert watch["forecast_sample_gap_minutes"] == 15.0


def test_pre_gate_watchlist_persistence_scorecard_detects_persistent_cells():
    history = [
        {
            "created_at_utc": "2026-06-20T12:32:01+00:00",
            "pre_gate_hac_watchlist": [{
                "bucket": BUCKET_EVENT_REG,
                "symbol": "XRPUSDT",
                "horizon_minutes": 60,
                "overlap_adjusted_sample_floor": 11,
                "t_stat_hac": 2.3,
            }],
        },
        {
            "created_at_utc": "2026-06-20T12:47:01+00:00",
            "pre_gate_hac_watchlist": [{
                "bucket": BUCKET_EVENT_REG,
                "symbol": "XRPUSDT",
                "horizon_minutes": 60,
                "overlap_adjusted_sample_floor": 12,
                "t_stat_hac": 2.8,
            }],
        },
    ]
    current = [{
        "bucket": BUCKET_EVENT_REG,
        "symbol": "XRPUSDT",
        "horizon_minutes": 60,
        "overlap_adjusted_sample_floor": 13,
        "sample_gap_to_min_points": 17,
        "ic_pearson": -0.44,
        "t_stat_hac": -3.1,
        "bh_q_value_hac_approx": 0.04,
        "partial_ic_controlling_trailing_return": -0.31,
        "partial_ic_retained_abs_ratio": 0.70,
        "price_feedback_partial_collapse_warning": False,
        "expected_gate_label_ready_utc": "2026-06-20T19:52:00+00:00",
        "gate_blocker": "sample_floor_below_min_points",
    }]

    scorecard = harness.build_pre_gate_watchlist_persistence_scorecard(
        current_watchlist=current,
        history_reports=history,
        current_created_at_utc="2026-06-20T13:02:01+00:00",
    )

    assert scorecard["status"] == "PERSISTENT_PRE_GATE_WATCHLIST"
    assert scorecard["history_report_count"] == 2
    assert scorecard["reports_with_watchlist_count"] == 2
    assert scorecard["persistent_cell_count"] == 1
    top = scorecard["top_cells"][0]
    assert top["cell_key"] == "event_reg|XRPUSDT|60"
    assert top["current_consecutive_reports"] == 3
    assert top["presence_count"] == 3
    assert top["first_seen_sample_floor"] == 11
    assert top["current_sample_floor"] == 13


def test_pre_gate_watchlist_persistence_marks_low_floor_recurrence_separately():
    history = [{
        "created_at_utc": "2026-06-20T17:02:01+00:00",
        "pre_gate_hac_watchlist": [{
            "bucket": BUCKET_OTHER,
            "symbol": "BTCUSDT",
            "horizon_minutes": 240,
            "overlap_adjusted_sample_floor": 1,
            "t_stat_hac": -20.0,
        }],
    }]
    current = [{
        "bucket": BUCKET_OTHER,
        "symbol": "BTCUSDT",
        "horizon_minutes": 240,
        "overlap_adjusted_sample_floor": 1,
        "sample_gap_to_min_points": 29,
        "t_stat_hac": -24.0,
    }]

    scorecard = harness.build_pre_gate_watchlist_persistence_scorecard(
        current_watchlist=current,
        history_reports=history,
        current_created_at_utc="2026-06-20T17:17:01+00:00",
        min_points=30,
    )

    assert scorecard["status"] == "LOW_SAMPLE_RECURRING_PRE_GATE_WATCHLIST"
    assert scorecard["min_current_sample_floor_for_status"] == 8
    assert scorecard["recurring_cell_count"] == 1
    assert scorecard["floor_qualified_recurring_cell_count"] == 0
    assert scorecard["top_cells"][0]["floor_qualified_for_status"] is False


def test_recent_report_history_excludes_latest_and_keeps_dated_order(tmp_path):
    latest = tmp_path / "polymarket_leadlag_latest.json"
    latest.write_text(json.dumps({"created_at_utc": "2026-06-20T12:45:00+00:00"}), encoding="utf-8")
    older = tmp_path / "polymarket_leadlag_20260620T123000Z.json"
    newer = tmp_path / "polymarket_leadlag_20260620T124500Z.json"
    older.write_text(json.dumps({"created_at_utc": "2026-06-20T12:30:00+00:00"}), encoding="utf-8")
    newer.write_text(json.dumps({"created_at_utc": "2026-06-20T12:45:00+00:00"}), encoding="utf-8")

    reports = harness.load_recent_report_history(tmp_path, limit=1)

    assert len(reports) == 1
    assert reports[0]["created_at_utc"] == "2026-06-20T12:45:00+00:00"
    assert reports[0]["_history_path"] == str(newer)


def test_candidate_replay_builds_explicit_paper_pnl_evidence():
    start = dt.datetime(2026, 6, 20, 0, 0, tzinfo=dt.timezone.utc)
    joined = []
    for i in range(40):
        ts = start + dt.timedelta(minutes=15 * i)
        sign = 1.0 if i % 2 == 0 else -1.0
        joined.append({
            "snapshot_ts_ms": int(ts.timestamp() * 1000),
            "snapshot_ts_utc": ts.isoformat(),
            "bucket": BUCKET_PRICE_TARGET,
            "symbol": "SOLUSDT",
            "horizon_minutes": 15,
            "mean_delta_prob_yes": 0.05 * sign,
            "forward_return_bps": 10.0 * sign,
        })
    candidate = {
        "bucket": BUCKET_PRICE_TARGET,
        "symbol": "SOLUSDT",
        "horizon_minutes": 15,
        "ic_pearson": 0.8,
        "t_stat_hac": 5.0,
        "bh_q_value_hac_approx": 0.01,
    }

    evidence, summary = candidate_replay.build_candidate_replay(
        joined_rows=joined,
        candidate=candidate,
        ic_result_count=12,
        price_source="fixture",
        round_trip_cost_bps=4.0,
    )

    assert evidence["candidate_id"] == "polymarket_leadlag_price_target_SOLUSDT_15m"
    assert evidence["candidate_key"] == "polymarket_leadlag_ic|price_target|SOLUSDT|15m"
    assert evidence["strategy_family"] == "polymarket_leadlag_directional_replay"
    assert len(evidence["samples"]) == 40
    assert evidence["samples"][0]["gross_bps"] == 10.0
    assert evidence["samples"][0]["net_bps"] == 6.0
    assert evidence["source"]["execution_realism_status"] == "UNMEASURED"
    assert summary["sample_count"] == 40
    assert summary["net_bps_mean"] == 6.0
    assert summary["holdout_net_bps_mean"] == 6.0
    assert summary["cost_wall_status"] == "PAPER_REPLAY_NET_POSITIVE_EXECUTION_UNMEASURED"
    assert summary["execution_realism_status"] == "UNMEASURED"
    assert summary["selection_bias_warning"]


def _history_report(
    *,
    created_at: str,
    path: Path,
    candidate_key: str,
    samples: list[dict],
    pbo_day: str,
) -> dict:
    evidence = {
        "candidate_id": "polymarket_leadlag_price_target_SOLUSDT_15m",
        "candidate_key": candidate_key,
        "strategy_family": "polymarket_leadlag_directional_replay",
        "parameter_cell_id": "price_target|SOLUSDT|15m|rule=ic_sign_delta|threshold_q=0|cost_bps=4",
        "selected_variant": "ic_sign_delta",
        "sample_unit": "polymarket_nonoverlap_forward_window",
        "k_trials": 12,
        "samples": samples,
        "daily_returns": {"unit": "fraction", "values": {}},
        "pbo_seed": 20260620,
        "pbo_candidates": {
            "cell_a": {pbo_day: 0.001},
            "cell_b": {pbo_day: -0.0005},
        },
    }
    summary = {
        "candidate_id": evidence["candidate_id"],
        "candidate_key": candidate_key,
        "strategy_family": evidence["strategy_family"],
        "parameter_cell_id": evidence["parameter_cell_id"],
        "selected_variant": evidence["selected_variant"],
        "sample_unit": evidence["sample_unit"],
    }
    return {
        "created_at_utc": created_at,
        "_history_path": str(path),
        "candidate_replay_scorecard": {
            "status": "PAPER_REPLAY_BUILT",
            "selected_candidate_key": candidate_key,
            "selected_evidence": evidence,
            "selected_summary": summary,
        },
    }


def test_replay_history_accumulates_deduped_samples_and_pbo_days(tmp_path):
    candidate_key = "polymarket_leadlag_ic|price_target|SOLUSDT|15m"
    samples_day_1 = [
        {
            "sample_id": "s1",
            "sample_ts_utc": "2026-06-20T00:00:00+00:00",
            "regime": "unsegmented",
            "independence_bucket": "SOLUSDT:15m:1",
            "gross_bps": 10.0,
            "cost_bps": 4.0,
            "net_bps": 6.0,
            "is_oos": False,
        },
        {
            "sample_id": "s2",
            "sample_ts_utc": "2026-06-20T00:15:00+00:00",
            "regime": "unsegmented",
            "independence_bucket": "SOLUSDT:15m:2",
            "gross_bps": 8.0,
            "cost_bps": 4.0,
            "net_bps": 4.0,
            "is_oos": True,
        },
    ]
    samples_day_2 = [
        samples_day_1[1],
        {
            "sample_id": "s3",
            "sample_ts_utc": "2026-06-21T00:00:00+00:00",
            "regime": "unsegmented",
            "independence_bucket": "SOLUSDT:15m:3",
            "gross_bps": 7.0,
            "cost_bps": 4.0,
            "net_bps": 3.0,
            "is_oos": True,
        },
    ]
    reports = [
        _history_report(
            created_at="2026-06-20T01:00:00+00:00",
            path=tmp_path / "polymarket_leadlag_20260620T010000Z.json",
            candidate_key=candidate_key,
            samples=samples_day_1,
            pbo_day="2026-06-20",
        ),
        _history_report(
            created_at="2026-06-21T01:00:00+00:00",
            path=tmp_path / "polymarket_leadlag_20260621T010000Z.json",
            candidate_key=candidate_key,
            samples=samples_day_2,
            pbo_day="2026-06-21",
        ),
    ]

    scorecard = replay_history.build_history_scorecard(
        reports=reports,
        candidate_key=candidate_key,
        min_days=2,
        min_samples=3,
    )

    summary = scorecard["selected_summary"]
    evidence = scorecard["selected_evidence"]
    assert scorecard["status"] == "REPLAY_HISTORY_READY_FOR_AEG_RECHECK"
    assert summary["sample_count"] == 3
    assert summary["n_days"] == 2
    assert summary["net_bps_mean"] == 4.33333333
    assert summary["pbo_history_cell_count"] == 2
    assert summary["pbo_history_day_count"] == 2
    assert evidence["candidate_key"] == candidate_key
    assert len(evidence["samples"]) == 3
    assert evidence["daily_returns"]["values"] == {
        "2026-06-20": 0.001,
        "2026-06-21": 0.0003,
    }
    assert set(evidence["pbo_candidates"]["cell_a"]) == {"2026-06-20", "2026-06-21"}
    assert evidence["source"]["execution_realism_status"] == "UNMEASURED"


def test_replay_history_writer_outputs_aeg_compatible_evidence(tmp_path):
    candidate_key = "polymarket_leadlag_ic|price_target|SOLUSDT|15m"
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    report = _history_report(
        created_at="2026-06-20T01:00:00+00:00",
        path=report_dir / "polymarket_leadlag_20260620T010000Z.json",
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
        pbo_day="2026-06-20",
    )
    (report_dir / "polymarket_leadlag_20260620T010000Z.json").write_text(
        json.dumps(report),
        encoding="utf-8",
    )

    scorecard = replay_history.build_history_scorecard_from_report_dir(
        report_dir,
        candidate_key=candidate_key,
        min_days=1,
        min_samples=1,
    )
    written = replay_history.write_history_evidence(
        scorecard=scorecard,
        out_dir=tmp_path / "out",
        repo_root=Path(__file__).resolve().parents[3],
    )
    evidence = json.loads(Path(written["history_evidence"]).read_text(encoding="utf-8"))
    manifest = json.loads(Path(written["manifest"]).read_text(encoding="utf-8"))

    assert evidence["candidate_key"] == candidate_key
    assert evidence["samples"][0]["net_bps"] == 6.0
    assert evidence["daily_returns"]["values"] == {"2026-06-20": 0.0006}
    assert manifest["candidate_key"] == candidate_key
    assert manifest["policy"] == evidence["policy"]


def test_report_includes_candidate_replay_scorecard_for_ic_candidate(tmp_path):
    root = tmp_path / "pm"
    start = dt.datetime(2026, 6, 20, 0, 0, tzinfo=dt.timezone.utc)
    probs = [0.50]
    for i in range(12):
        probs.append(probs[-1] + (0.05 if i % 2 == 0 else -0.05))
    for i, prob in enumerate(probs):
        ts = (start + dt.timedelta(minutes=15 * i)).isoformat()
        _write_run(root, f"hourly-topn-{i}", ts, [{
            "market_id": "sol-price",
            "question": "Will Solana reach $200 this week?",
            "event_title": "Solana price target",
            "discovery_queries": ["kw:solana price"],
            "outcome_prices": [prob, 1 - prob],
        }])

    prices = [100.0]
    for i in range(len(probs) + 1):
        if i == 0:
            ret_bps = 0.0
        else:
            sign = 1.0 if (i - 1) % 2 == 0 else -1.0
            ret_bps = sign * (8.0 + (i % 3))
        prices.append(prices[-1] * (1.0 + ret_bps / 10_000.0))
    price_rows = _price_rows("SOLUSDT", start, prices)
    rows, meta = harness.load_snapshot_rows(root, query_set_version="v2", mode="hourly-topn")

    report = harness.build_report(
        snapshot_rows=rows,
        snapshot_meta=meta,
        price_rows=price_rows,
        query_set_version="v2",
        mode="hourly-topn",
        symbols=("SOLUSDT",),
        horizons_minutes=(15,),
        min_points=5,
        max_align_lag_minutes=1,
        min_abs_ic=0.1,
        min_abs_t=0.1,
        max_bh_q=1.0,
        price_source="fixture",
        candidate_replay_round_trip_cost_bps=4.0,
    )

    replay = report["candidate_replay_scorecard"]
    selected = replay["selected_summary"]
    assert report["verdict"]["candidate_count"] == 1
    assert replay["status"] == "PAPER_REPLAY_BUILT"
    assert replay["selected_candidate_key"] == "polymarket_leadlag_ic|price_target|SOLUSDT|15m"
    assert selected["sample_count"] >= 5
    assert selected["net_bps_mean"] > 0
    assert selected["round_trip_cost_bps"] == 4.0
    assert replay["selected_evidence"]["samples"]


def test_source_has_readonly_pg_and_no_trading_tokens():
    src = Path(harness.__file__).read_text(encoding="utf-8")
    assert "set_session(readonly=True)" in src
    for banned in ("create_order", "place_order", "OPENCLAW_ALLOW_MAINNET", "authorization.json"):
        assert banned not in src
