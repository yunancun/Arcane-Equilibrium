"""AEG-S3 panel exporter tests."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aeg_s3_funding_revive import builder as funding_builder
from aeg_s3_oi_delta import builder as oi_builder
from aeg_s3_panel_export import builder as export_builder


def _price_rows(symbols: list[str], days: int) -> list[dict]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for i in range(days + 2):
        ts = base + timedelta(days=i + 1)
        for j, symbol in enumerate(symbols):
            drift = 1.002 if j < 2 else 0.998
            rows.append({
                "symbol": symbol,
                "ts_utc": ts.isoformat(),
                "date": (base + timedelta(days=i)).date().isoformat(),
                "close": 100.0 * (drift ** i),
            })
    return rows


def _oi_rows(symbols: list[str], days: int) -> list[dict]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for i in range(days):
        for j, symbol in enumerate(symbols):
            rows.append({
                "symbol": symbol,
                "ts_utc": (base + timedelta(days=i, hours=23)).isoformat(),
                "date": (base + timedelta(days=i)).date().isoformat(),
                "open_interest": 1_000.0 + (i * 20.0 if j < 2 else -i * 20.0) + j,
                "interval_time": "1h",
                "category": "linear",
            })
    return rows


def _funding_rows() -> tuple[list[dict], list[dict], list[dict]]:
    base = datetime(2026, 4, 1, tzinfo=timezone.utc)
    symbol = "FUNDUSDT"
    price_rows = [
        {
            "symbol": symbol,
            "ts_utc": (base + timedelta(days=i + 1)).isoformat(),
            "date": (base + timedelta(days=i)).date().isoformat(),
            "close": 100.0 + max(0, i - 6) * 0.2,
        }
        for i in range(10)
    ]
    funding = [-1.0, 0.0, 1.0, -1.0, 0.0, -3.0, -0.5, -0.2]
    rows = [
        {
            "symbol": symbol,
            "funding_ts": (base + timedelta(days=i)).isoformat(),
            "date": (base + timedelta(days=i)).date().isoformat(),
            "funding_rate": funding[i] / 10_000.0,
            "funding_interval_minutes": 480,
            "category": "linear",
        }
        for i in range(len(funding))
    ]
    regimes = [
        {"symbol": symbol, "date": (base + timedelta(days=i)).date().isoformat(), "regime": "chop"}
        for i in range(10)
    ]
    return price_rows, rows, regimes


def _regime_rows(symbols: list[str], days: int) -> list[dict]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        {"symbol": symbol, "date": (base + timedelta(days=i)).date().isoformat(), "regime": "chop"}
        for i in range(days + 2)
        for symbol in symbols
    ]


def test_exported_oi_panel_is_consumed_by_oi_delta_producer():
    symbols = ["AAUSDT", "BBUSDT", "CCUSDT", "DDUSDT"]
    panel, summary = export_builder.build_daily_oi_delta_panel(
        price_rows=_price_rows(symbols, 50),
        oi_rows=_oi_rows(symbols, 50),
        regime_rows=_regime_rows(symbols, 50),
        run_id="accepted_run",
    )

    assert summary["row_count"] == 200
    assert summary["rejected_row_count"] == 0
    evidence, ev_summary = oi_builder.build_oi_delta_evidence(
        panel,
        source_path="oi_delta_panel.jsonl",
        run_id="oi",
        lookback_hours=24,
        horizon_hours=24,
        cost_bps=1.0,
        k_trials=16,
        min_symbols=4,
        tail_frac=0.25,
        default_regime="chop",
    )
    assert ev_summary["sample_count"] >= 30
    assert evidence["samples"][0]["gross_bps"] > 0


def test_exported_funding_panel_is_consumed_by_funding_revive_producer():
    prices, funding_rows, regimes = _funding_rows()
    panel, summary = export_builder.build_funding_revive_panel(
        price_rows=prices,
        funding_rows=funding_rows,
        regime_rows=regimes,
        run_id="accepted_run",
    )

    assert summary["row_count"] == len(funding_rows)
    evidence, ev_summary = funding_builder.build_funding_revive_evidence(
        panel,
        source_path="funding_revive_panel.jsonl",
        run_id="funding",
        lookback_points=5,
        horizon_hours=24,
        stress_z=2.0,
        exit_z=1.0,
        cost_bps=1.0,
        k_trials=16,
        default_regime="chop",
    )
    assert ev_summary["sample_count"] == 1
    assert evidence["samples"][0]["side"] == "long"


def test_missing_price_and_regime_reject_fail_closed():
    panel, summary = export_builder.build_daily_oi_delta_panel(
        price_rows=[],
        oi_rows=[{
            "symbol": "MISSUSDT",
            "ts_utc": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
            "open_interest": 10.0,
            "category": "linear",
        }],
        regime_rows=[],
        run_id="accepted_run",
    )
    assert panel == []
    assert summary["reject_reasons"] == {"missing_price": 1}

    prices, funding_rows, _regimes = _funding_rows()
    funding_panel, funding_summary = export_builder.build_funding_revive_panel(
        price_rows=prices,
        funding_rows=funding_rows,
        regime_rows=[],
        run_id="accepted_run",
    )
    assert funding_panel == []
    assert funding_summary["reject_reasons"] == {"missing_regime": len(funding_rows)}


def test_write_jsonl_and_summary(tmp_path):
    rows = [{"symbol": "BTCUSDT", "ts_utc": "2026-01-01T00:00:00+00:00", "price": 1.0}]
    path = export_builder.write_jsonl(tmp_path / "panel.jsonl", rows)
    loaded = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert loaded == rows

    summary = export_builder.combined_summary({"row_count": 1, "rejected_row_count": 0}, run_id="r")
    summary_path = export_builder.write_json(tmp_path / "summary.json", summary)
    assert json.loads(summary_path.read_text(encoding="utf-8"))["total_rows"] == 1


def test_static_no_runtime_or_mutating_route():
    pkg = Path(__file__).resolve().parents[1] / "aeg_s3_panel_export"
    code = "\n".join(path.read_text(encoding="utf-8") for path in pkg.glob("*.py"))
    forbidden = (
        "control_api_v1",
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
        "OPENCLAW_ALLOW_MAINNET",
        "execution_authority",
        "wss://stream.bybit.com",
        "urlopen",
    )
    for needle in forbidden:
        assert needle not in code
