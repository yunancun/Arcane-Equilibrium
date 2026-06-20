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
        price_source="fixture",
    )
    assert report["verdict"]["status"] == STATUS_INSUFFICIENT_SAMPLE
    assert report["counts"]["snapshot_rows"] == 3
    assert report["counts"]["delta_rows"] == 2
    assert report["counts"]["joined_rows"] == 2
    assert report["counts"]["bucket_delta_counts"][BUCKET_EVENT_REG] == 2


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


def test_source_has_readonly_pg_and_no_trading_tokens():
    src = Path(harness.__file__).read_text(encoding="utf-8")
    assert "set_session(readonly=True)" in src
    for banned in ("create_order", "place_order", "OPENCLAW_ALLOW_MAINNET", "authorization.json"):
        assert banned not in src
