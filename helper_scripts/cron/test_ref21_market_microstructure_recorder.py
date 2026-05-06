from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent / "ref21_market_microstructure_recorder.py"
spec = importlib.util.spec_from_file_location("ref21_market_microstructure_recorder", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def test_ticker_rows_parse_bbo_and_spread() -> None:
    rows = mod.ticker_rows(
        tickers=[
            {
                "symbol": "BTCUSDT",
                "lastPrice": "100",
                "markPrice": "100.2",
                "indexPrice": "100.1",
                "bid1Price": "99.9",
                "ask1Price": "100.1",
                "bid1Size": "2",
                "ask1Size": "3",
                "volume24h": "10",
                "turnover24h": "1000",
                "openInterest": "5",
            },
            {"symbol": "DOGEUSDT", "lastPrice": "1"},
        ],
        symbols={"BTCUSDT"},
        asof=datetime(2026, 5, 7, tzinfo=timezone.utc),
    )

    assert len(rows) == 1
    assert rows[0]["symbol"] == "BTCUSDT"
    assert rows[0]["best_bid"] == 99.9
    assert rows[0]["best_ask"] == 100.1
    assert abs(rows[0]["spread_bps"] - 20.0) < 1e-9


def test_orderbook_summary_row_uses_top_five_depth() -> None:
    row = mod.orderbook_summary_row(
        symbol="BTCUSDT",
        asof=datetime(2026, 5, 7, tzinfo=timezone.utc),
        limit=5,
        payload={
            "ts": 1_700_000_000_000,
            "b": [["99", "2"], ["98", "1"]],
            "a": [["101", "3"], ["102", "1"]],
        },
    )

    assert row is not None
    assert row["symbol"] == "BTCUSDT"
    assert row["ts"].isoformat() == "2023-11-14T22:13:20+00:00"
    assert row["bid_depth_5"] == 3.0
    assert row["ask_depth_5"] == 4.0
    assert abs(row["imbalance_ratio"] - (3.0 / 7.0)) < 1e-12
    assert abs(row["spread_bps"] - 200.0) < 1e-9


def test_latest_v058_symbols_falls_back_when_table_absent() -> None:
    class Cur:
        def __init__(self) -> None:
            self._fetchone = None

        def execute(self, *_args, **_kwargs) -> None:
            self._fetchone = None

        def fetchone(self):
            return self._fetchone

    assert mod.latest_v058_symbols(Cur(), category="linear", max_symbols=2) == [
        "BTCUSDT",
        "ETHUSDT",
    ]
