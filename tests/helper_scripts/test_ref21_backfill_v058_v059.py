from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "helper_scripts/db/ref21_backfill_v058_v059.py"
spec = importlib.util.spec_from_file_location("ref21_backfill_v058_v059", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def test_instrument_snapshot_rows_parse_bybit_filters() -> None:
    asof = datetime(2026, 5, 7, tzinfo=timezone.utc)
    rows = mod.instrument_snapshot_rows(
        category="linear",
        asof=asof,
        status_filter="Trading",
        instruments=[
            {
                "symbol": "btcusdt",
                "status": "Trading",
                "baseCoin": "BTC",
                "quoteCoin": "USDT",
                "contractType": "LinearPerpetual",
                "launchTime": "1700000000000",
                "priceFilter": {"tickSize": "0.10"},
                "lotSizeFilter": {
                    "qtyStep": "0.001",
                    "minNotionalValue": "5",
                },
            }
        ],
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["symbol"] == "BTCUSDT"
    assert row["exchange"] == "bybit"
    assert row["category"] == "linear"
    assert row["tick_size"] == "0.10"
    assert row["qty_step"] == "0.001"
    assert row["min_notional"] == "5"
    assert row["listed_at"].isoformat() == "2023-11-14T22:13:20+00:00"
    assert row["is_delisted_at_asof"] is False
    assert row["source_uri"].endswith("category=linear&status=Trading")
    assert len(row["payload_hash"]) == 32


def test_parse_iso_datetime_accepts_iso_and_epoch_ms() -> None:
    assert (
        mod.parse_iso_datetime("2026-05-07T01:02:03+00:00").isoformat()
        == "2026-05-07T01:02:03+00:00"
    )
    assert (
        mod.parse_iso_datetime("1700000000000").isoformat()
        == "2023-11-14T22:13:20+00:00"
    )


def test_instrument_snapshot_rows_skip_symbols_outside_v058_contract() -> None:
    rows = mod.instrument_snapshot_rows(
        category="linear",
        asof=datetime(2026, 5, 7, tzinfo=timezone.utc),
        status_filter="Closed",
        instruments=[
            {
                "symbol": "BTCUSDT-08MAY26",
                "status": "Closed",
                "priceFilter": {"tickSize": "0.10"},
                "lotSizeFilter": {"qtyStep": "0.001"},
            },
            {
                "symbol": "BTCUSDT",
                "status": "Trading",
                "priceFilter": {"tickSize": "0.10"},
                "lotSizeFilter": {"qtyStep": "0.001"},
            },
        ],
    )

    assert [row["symbol"] for row in rows] == ["BTCUSDT"]


def test_parse_edge_snapshot_file_builds_v059_rows(tmp_path: Path) -> None:
    path = tmp_path / "edge_estimates.json"
    path.write_text(
        """
        {
          "_meta": {"updated_at": "2026-05-07T00:00:00+00:00"},
          "grid_trading::BTCUSDT": {
            "runtime_bps": 1.2,
            "shrunk_bps": 2.3,
            "n": 10
          }
        }
        """,
        encoding="utf-8",
    )

    asof, _meta, rows = mod.parse_edge_snapshot_file(path)

    assert asof.isoformat() == "2026-05-07T00:00:00+00:00"
    assert len(rows) == 1
    row = rows[0]
    assert row["source_tier"] == "demo_latest_json"
    assert row["symbol"] == "BTCUSDT"
    assert row["strategy"] == "grid_trading"
    assert row["regime_key"] == "global"
    assert row["cell_key"] == "default"
    assert row["estimate_payload_jsonb"]["runtime_bps"] == 1.2
    assert len(row["estimate_payload_hash"]) == 32
    assert row["retention_until"] > asof
