"""Polymarket lead-lag IC harness tests."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from polymarket_leadlag import (
    BUCKET_EVENT_REG,
    BUCKET_PRICE_TARGET,
    STATUS_INSUFFICIENT_SAMPLE,
)
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
        ("BTCUSDT", "macro_event_reg"),
        ("ETHUSDT", "macro_event_reg"),
    ]
    assert harness.infer_symbol_mappings({"question": "Will Bitcoin ETF approval happen?"}, set(harness.DEFAULT_SYMBOLS)) == [
        ("BTCUSDT", "asset_direct"),
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
    assert report["counts"]["joined_rows"] == 2
    assert report["counts"]["bucket_delta_counts"][BUCKET_EVENT_REG] == 2


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

    assert delta_meta["skipped"] == {}
    assert delta_meta["markets_with_rows"] == 1
    assert delta_meta["market_symbol_series_with_rows"] == 2
    assert delta_meta["symbol_source_counts"] == {"macro_event_reg": 6}
    assert len(deltas) == 4
    assert {(row["symbol"], row["symbol_source"]) for row in deltas} == {
        ("BTCUSDT", "macro_event_reg"),
        ("ETHUSDT", "macro_event_reg"),
    }
    assert {(row["symbol"], row["bucket"]) for row in features} == {
        ("BTCUSDT", BUCKET_EVENT_REG),
        ("ETHUSDT", BUCKET_EVENT_REG),
    }


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
    assert report["counts"]["feature_points"] == 1
    assert report["counts"]["joined_rows"] == 0
    assert readiness["feature_horizon_pairs"] == 1
    assert readiness["joinable_pairs"] == 0
    assert readiness["status_counts"] == {"exit_target_after_latest_price": 1}
    assert readiness["by_horizon"]["15"] == {"exit_target_after_latest_price": 1}
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

    assert report["verdict"]["preliminary_raw_candidate_count"] == 1
    assert report["verdict"]["preliminary_hac_candidate_count"] == 1
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
    assert report["verdict"]["pre_gate_hac_watchlist_count"] == 1
    assert report["counts"]["min_samples_remaining_to_gate"] == 6
    assert report["counts"]["sample_gate_clock"]["status"] == "WAITING_FOR_SAMPLE"
    assert (
        report["counts"]["sample_gate_clock"]["fastest_gate_ready_utc"]
        == "2026-06-20T10:15:00+00:00"
    )
    assert len(report["pre_gate_hac_watchlist"]) == 1
    watch = report["pre_gate_hac_watchlist"][0]
    assert watch["sample_gap_to_min_points"] == 6
    assert watch["gate_blocker"] == "sample_floor_below_min_points"
    assert watch["bh_q_value_hac_approx"] is not None
    assert watch["expected_gate_label_ready_utc"] == "2026-06-20T10:15:00+00:00"
    assert watch["eta_basis"] == "overlap_adjusted_floor_forecast_gap_plus_forward_horizon"
    assert watch["forecast_sample_gap_minutes"] == 15.0


def test_source_has_readonly_pg_and_no_trading_tokens():
    src = Path(harness.__file__).read_text(encoding="utf-8")
    assert "set_session(readonly=True)" in src
    for banned in ("create_order", "place_order", "OPENCLAW_ALLOW_MAINNET", "authorization.json"):
        assert banned not in src
