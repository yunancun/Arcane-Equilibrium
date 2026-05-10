from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any

import pytest


_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_CONTROL_API_DIR = os.path.dirname(_TEST_DIR)
if _CONTROL_API_DIR not in sys.path:
    sys.path.insert(0, _CONTROL_API_DIR)


def test_fetch_pnl_series_aggregates_fills_fees_and_funding(monkeypatch) -> None:
    from app import pnl_series

    fixed_now = 1_700_000_000
    bucket_sec = 1_800
    start_epoch = int((fixed_now - 3_600) // bucket_sec) * bucket_sec
    trade_bucket = start_epoch + bucket_sec

    class Cursor:
        def __init__(self) -> None:
            self.calls = 0

        def __enter__(self) -> "Cursor":
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def execute(self, _sql: str, _params: tuple[Any, ...] | None = None) -> None:
            self.calls += 1

        def fetchone(self) -> tuple[bool]:
            return (True,)

        def fetchall(self) -> list[tuple[Any, ...]]:
            if self.calls == 1:
                return [
                    (
                        datetime.fromtimestamp(trade_bucket, tz=timezone.utc),
                        2,
                        3.0,
                        0.5,
                    )
                ]
            if self.calls == 3:
                return [(datetime.fromtimestamp(trade_bucket, tz=timezone.utc), -0.25)]
            return []

    class Conn:
        def cursor(self) -> Cursor:
            return Cursor()

    returned: list[Conn] = []
    conn = Conn()
    monkeypatch.setattr(pnl_series.time, "time", lambda: fixed_now)
    monkeypatch.setattr(pnl_series.db_pool, "get_conn", lambda: conn)
    monkeypatch.setattr(pnl_series.db_pool, "put_conn", lambda c: returned.append(c))

    out = pnl_series.fetch_pnl_series(["demo"], range_key="1h", bucket_sec=bucket_sec)

    assert out["available"] is True
    assert out["range"] == "1h"
    assert out["bucket_sec"] == bucket_sec
    assert out["fills"] == 2
    assert out["window_gross_pnl"] == 3.0
    assert out["window_fees"] == 0.5
    assert out["window_funding_pnl"] == -0.25
    assert out["window_net_pnl"] == 2.25
    trade_point = next(p for p in out["points"] if p["fills"] == 2)
    assert trade_point["net_pnl"] == 2.25
    assert trade_point["cumulative_net_pnl"] == 2.25
    assert returned == [conn]


def test_fetch_pnl_series_clamps_dense_custom_bucket(monkeypatch) -> None:
    from app import pnl_series

    monkeypatch.setattr(pnl_series.db_pool, "get_conn", lambda: None)

    out = pnl_series.fetch_pnl_series(["demo"], range_key="30d", bucket_sec=60)

    assert out["available"] is False
    assert out["range"] == "30d"
    assert out["bucket_sec"] > 60
    assert out["range_sec"] / out["bucket_sec"] <= 520


@pytest.mark.asyncio
async def test_demo_pnl_series_route_uses_demo_mode(monkeypatch) -> None:
    from app import pnl_series
    from app import strategy_ai_routes

    captured: list[tuple[list[str], str, int | None]] = []

    def fake_fetch(modes, *, range_key="24h", bucket_sec=None):
        captured.append((list(modes), range_key, bucket_sec))
        return {"available": True, "range": range_key, "bucket_sec": bucket_sec, "points": []}

    monkeypatch.setattr(pnl_series, "fetch_pnl_series", fake_fetch)

    out = await strategy_ai_routes.get_demo_pnl_series(range_key="7d", bucket_sec=3600, actor=None)

    assert captured == [(["demo"], "7d", 3600)]
    assert out["data"]["range"] == "7d"


def test_live_pnl_series_route_uses_endpoint_specific_db_mode(monkeypatch) -> None:
    from app import live_session_account_routes as routes
    from app import live_session_routes as core
    from app import pnl_series

    captured: list[tuple[list[str], str, int | None]] = []

    def fake_fetch(modes, *, range_key="24h", bucket_sec=None):
        captured.append((list(modes), range_key, bucket_sec))
        return {"available": True, "range": range_key, "bucket_sec": bucket_sec, "points": []}

    monkeypatch.setattr(routes, "_phantom_view_guard", lambda: None)
    monkeypatch.setattr(core, "_get_live_engine_kind", lambda: "live")
    monkeypatch.setattr(core, "_resolve_live_endpoint_label", lambda: "live_demo")
    monkeypatch.setattr(pnl_series, "fetch_pnl_series", fake_fetch)

    out = routes.get_live_pnl_series(range_key="6h", bucket_sec=900, actor=None)

    assert captured == [(["live_demo"], "6h", 900)]
    assert out["data"]["range"] == "6h"
