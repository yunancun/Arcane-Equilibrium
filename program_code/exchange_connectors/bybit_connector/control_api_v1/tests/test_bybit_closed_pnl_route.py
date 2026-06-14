"""Focused tests for Demo Bybit-first closed-PnL read model."""

from __future__ import annotations

import sys
import threading
import time
import types
from datetime import datetime, timezone
from typing import Any

import pytest

from app import strategy_ai_routes as routes
from app.bybit_pnl_cache import ClosedPnlCache


class _FakeCursor:
    def __init__(self, rows: list[tuple[Any, ...]]):
        self.rows = rows
        self.sql = ""
        self.params: tuple[Any, ...] = ()

    def execute(self, sql: str, params: tuple[Any, ...]):
        self.sql = sql
        self.params = params

    def fetchall(self):
        return self.rows


class _SequencedFakeCursor:
    def __init__(self, select_rows: list[list[tuple[Any, ...]]]):
        self._select_rows = list(select_rows)
        self.sql = ""
        self.params: tuple[Any, ...] = ()
        self.sqls: list[str] = []
        self.params_list: list[tuple[Any, ...]] = []
        self._current_rows: list[tuple[Any, ...]] = []

    def execute(self, sql: str, params: tuple[Any, ...]):
        self.sql = sql
        self.params = params
        if sql.strip().upper().startswith("SET "):
            return
        self.sqls.append(sql)
        self.params_list.append(params)
        self._current_rows = self._select_rows.pop(0) if self._select_rows else []

    def fetchall(self):
        return self._current_rows


class _FakeConn:
    def __init__(self, cursor: _FakeCursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


class _FakeBybitClient:
    def __init__(self, rows: list[dict[str, Any]] | None = None, exc: Exception | None = None):
        self.rows = rows or []
        self.exc = exc
        self.calls = 0

    def get_closed_pnl(
        self,
        category: str,
        symbol: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ):
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return {"category": category, "list": [dict(row) for row in self.rows[:limit]], "nextPageCursor": ""}


class _PagedFakeBybitClient:
    def __init__(self, pages: dict[str, tuple[list[dict[str, Any]], str]]):
        self.pages = pages
        self.calls: list[dict[str, Any]] = []

    def get_closed_pnl(
        self,
        category: str,
        symbol: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ):
        self.calls.append({"limit": limit, "cursor": cursor})
        rows, next_cursor = self.pages[cursor or ""]
        return {
            "category": category,
            "list": [dict(row) for row in rows[:limit]],
            "nextPageCursor": next_cursor,
        }


class _CursorModeFakeBybitClient:
    def __init__(self, pages: dict[str, tuple[list[dict[str, Any]], str]]):
        self.pages = pages
        self.calls: list[dict[str, Any]] = []

    def get_closed_pnl(
        self,
        category: str,
        symbol: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ):
        self.calls.append({
            "limit": limit,
            "cursor": cursor,
            "start_time": start_time,
            "end_time": end_time,
        })
        rows, next_cursor = self.pages[cursor or ""]
        return {
            "category": category,
            "list": [dict(row) for row in rows[:limit]],
            "nextPageCursor": next_cursor,
        }


def _install_fake_db(monkeypatch: pytest.MonkeyPatch, cursor: _FakeCursor) -> None:
    fake_db = types.SimpleNamespace(
        get_conn=lambda: _FakeConn(cursor),
        put_conn=lambda conn: None,
    )
    monkeypatch.setitem(sys.modules, "app.db_pool", fake_db)
    import app  # noqa: PLC0415
    monkeypatch.setattr(app, "db_pool", fake_db, raising=False)


@pytest.fixture(autouse=True)
def _fresh_closed_pnl_cache(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(routes, "_CLOSED_PNL_CACHE", ClosedPnlCache(ttl_sec=8.0))
    routes._clear_closed_pnl_bybit_failures()
    yield
    routes._clear_closed_pnl_bybit_failures()


@pytest.mark.asyncio
async def test_demo_closed_pnl_bybit_first_reconciles_four_strategy_sources(monkeypatch):
    cursor = _FakeCursor([("OID1", "ma_crossover", 1.05, 0.03)])
    _install_fake_db(monkeypatch, cursor)
    fake_client = _FakeBybitClient([
        {
            "orderId": "OID1",
            "orderLinkId": "oc_dm_1",
            "symbol": "OPUSDT",
            "closedPnl": "1.0",
            "openFee": "0.02",
            "closeFee": "0.03",
        },
        {"orderId": "OID2", "orderLinkId": "external-link", "symbol": "OPUSDT", "closedPnl": "-0.5"},
        {"orderId": "OID3", "orderLinkId": "oc_dm_3", "symbol": "DOGEUSDT", "closedPnl": "0.2"},
        {"orderId": "OID4", "orderLinkId": "", "symbol": "BTCUSDT", "closedPnl": "0.4"},
    ])
    monkeypatch.setattr(routes, "_get_rust_client", lambda: fake_client)
    monkeypatch.setattr(routes, "_engine_owner_strategy_map", lambda engine: {"DOGEUSDT": "grid_trading"})

    result = await routes.get_demo_closed_pnl(
        limit=4, offset=0, symbol=None, force_refresh=False, actor=object()
    )
    data = result["data"]

    assert data["source"] == "bybit_api"
    assert data["source_ts"] > 0
    assert data["cache_age"] >= 0.0
    assert data["cache_age_seconds"] >= 0.0
    assert data["count"] == 4
    assert [row["strategy_source"] for row in data["list"]] == [
        "pg_fill",
        "bybit_unknown",
        "pg_link_id",
        "bybit_unknown",
    ]
    assert [row["strategy_name"] for row in data["list"]] == [
        "ma_crossover",
        "external_manual",
        "grid_trading",
        "external_manual",
    ]
    assert data["list"][0]["pg_engine_pnl"] == 1.05
    assert data["list"][0]["pg_engine_gross_pnl"] == 1.05
    assert data["list"][0]["pg_engine_close_fee"] == 0.03
    assert data["list"][0]["bybit_gross_pnl"] == pytest.approx(1.05)
    assert data["list"][0]["authoritative_pnl"] == 1.0
    assert data["list"][0]["authoritative_pnl_source"] == "bybit_closed_pnl"
    assert data["list"][0]["learning_pnl"] == 1.0
    assert data["list"][0]["learning_pnl_source"] == "bybit_closed_pnl"
    assert data["list"][0]["pnl_source_drift_basis"] == "pg_gross_vs_bybit_gross_before_fees"
    assert data["list"][0]["pnl_source_drift_usd"] == pytest.approx(0.0)
    assert "engine_mode IN (%s, %s)" in cursor.sql
    assert cursor.params[1:] == ("demo", "live_demo")


@pytest.mark.asyncio
async def test_demo_closed_pnl_openclaw_link_without_owner_is_unknown_pending(monkeypatch):
    cursor = _FakeCursor([])
    _install_fake_db(monkeypatch, cursor)
    fake_client = _FakeBybitClient([
        {"orderId": "OID3", "orderLinkId": "oc_dm_3", "symbol": "DOGEUSDT", "closedPnl": "0.2"},
    ])
    monkeypatch.setattr(routes, "_get_rust_client", lambda: fake_client)
    monkeypatch.setattr(routes, "_engine_owner_strategy_map", lambda engine: {})

    result = await routes.get_demo_closed_pnl(
        limit=1, offset=0, symbol=None, force_refresh=False, actor=object()
    )
    data = result["data"]

    assert [row["strategy_source"] for row in data["list"]] == [
        "pg_missing_unknown_external",
    ]
    assert data["list"][0]["strategy_name"] == "unknown_pending"


@pytest.mark.asyncio
async def test_demo_closed_pnl_missing_order_link_uses_pg_time_window_strategy(monkeypatch):
    ts = datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc)
    ts_ms = int(ts.timestamp() * 1000)
    cursor = _SequencedFakeCursor([
        [],
        [(ts, "oc_close_mf_fb_dm_1770000000000_7", "OPUSDT", "Sell", 100.0, 1.05, 0.03, "grid_trading")],
    ])
    _install_fake_db(monkeypatch, cursor)
    fake_client = _FakeBybitClient([
        {
            "orderId": "BYBIT-CLOSE-1",
            "orderLinkId": "",
            "symbol": "OPUSDT",
            "closedPnl": "1.0",
            "openFee": "0.02",
            "closeFee": "0.03",
            "updatedTime": str(ts_ms + 500),
        },
    ])
    monkeypatch.setattr(routes, "_get_rust_client", lambda: fake_client)
    monkeypatch.setattr(routes, "_engine_owner_strategy_map", lambda engine: {})

    result = await routes.get_demo_closed_pnl(
        limit=1, offset=0, symbol=None, force_refresh=True, actor=object()
    )
    row = result["data"]["list"][0]

    assert row["strategy_name"] == "grid_trading"
    assert row["strategy_source"] == "pg_time_window"
    assert row["pg_engine_pnl"] == 1.05
    assert row["pnl_source_drift_usd"] == pytest.approx(0.0)
    assert row["learning_pnl"] == 1.0
    assert row["strategy_match_delta_ms"] == 500
    assert any("symbol = ANY(%s)" in sql for sql in cursor.sqls)
    assert all("INSERT" not in sql.upper() for sql in cursor.sqls)
    assert all("UPDATE" not in sql.upper() for sql in cursor.sqls)
    assert all("DELETE" not in sql.upper() for sql in cursor.sqls)


@pytest.mark.asyncio
async def test_demo_closed_pnl_live_demo_link_uses_live_demo_owner_map(monkeypatch):
    cursor = _FakeCursor([])
    _install_fake_db(monkeypatch, cursor)
    fake_client = _FakeBybitClient([
        {"orderId": "OID-LD", "orderLinkId": "oc_ld_1", "symbol": "ETHUSDT", "closedPnl": "0.7"},
    ])
    monkeypatch.setattr(routes, "_get_rust_client", lambda: fake_client)
    monkeypatch.setattr(
        routes,
        "_engine_owner_strategy_map",
        lambda engine: {"ETHUSDT": "funding_arb"} if engine == "live_demo" else {},
    )

    result = await routes.get_demo_closed_pnl(
        limit=1, offset=0, symbol=None, force_refresh=False, actor=object()
    )
    data = result["data"]

    assert data["list"][0]["strategy_source"] == "pg_link_id"
    assert data["list"][0]["strategy_name"] == "funding_arb"


@pytest.mark.asyncio
async def test_demo_closed_pnl_cursor_paginates_past_500_rows(monkeypatch):
    _install_fake_db(monkeypatch, _FakeCursor([]))
    pages: dict[str, tuple[list[dict[str, Any]], str]] = {}
    for page in range(6):
        start = page * 100
        rows = [
            {
                "orderId": f"OID-{idx}",
                "orderLinkId": "external-link",
                "symbol": "OPUSDT",
                "closedPnl": "0.1",
            }
            for idx in range(start, start + 100)
        ]
        cursor = "" if page == 0 else f"C{page}"
        next_cursor = f"C{page + 1}"
        pages[cursor] = (rows, next_cursor)
    fake_client = _PagedFakeBybitClient(pages)
    monkeypatch.setattr(routes, "_get_rust_client", lambda: fake_client)

    result = await routes.get_demo_closed_pnl(
        limit=20, offset=550, symbol=None, force_refresh=False, actor=object()
    )
    data = result["data"]

    assert len(fake_client.calls) == 6
    assert fake_client.calls[-1] == {"limit": 71, "cursor": "C5"}
    assert data["count"] == 20
    assert data["list"][0]["orderId"] == "OID-550"
    assert data["has_more"] is True
    assert data["next_offset"] == 570


@pytest.mark.asyncio
async def test_demo_closed_pnl_cursor_mode_preloads_100_with_next_cursor(monkeypatch):
    _install_fake_db(monkeypatch, _FakeCursor([]))
    first_rows = [
        {"orderId": f"OID-{idx}", "orderLinkId": "external-link", "symbol": "OPUSDT", "closedPnl": "0.1"}
        for idx in range(100)
    ]
    second_rows = [
        {"orderId": f"OID-{idx}", "orderLinkId": "external-link", "symbol": "OPUSDT", "closedPnl": "0.2"}
        for idx in range(100, 200)
    ]
    fake_client = _CursorModeFakeBybitClient({
        "": (first_rows, "C1"),
        "C1": (second_rows, ""),
    })
    monkeypatch.setattr(routes, "_get_rust_client", lambda: fake_client)

    first = await routes.get_demo_closed_pnl(
        limit=100,
        offset=0,
        cursor=None,
        symbol=None,
        force_refresh=False,
        cursor_mode=True,
        actor=object(),
    )
    first_data = first["data"]

    assert first_data["count"] == 100
    assert first_data["has_more"] is True
    assert first_data["next_cursor"]
    assert first_data["page_size"] == 50
    assert first_data["preload_limit"] == 100
    assert fake_client.calls[0]["limit"] == 100
    assert fake_client.calls[0]["cursor"] is None
    assert fake_client.calls[0]["end_time"] - fake_client.calls[0]["start_time"] <= (
        7 * 24 * 60 * 60 * 1000
    )

    second = await routes.get_demo_closed_pnl(
        limit=100,
        offset=0,
        cursor=first_data["next_cursor"],
        symbol=None,
        force_refresh=False,
        cursor_mode=True,
        actor=object(),
    )
    second_data = second["data"]

    assert second_data["count"] == 100
    assert fake_client.calls[1]["cursor"] == "C1"
    assert second_data["list"][0]["orderId"] == "OID-100"


@pytest.mark.asyncio
async def test_demo_closed_pnl_cursor_mode_pg_fallback_returns_pg_cursor(monkeypatch):
    ts = datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc)
    cursor = _FakeCursor([
        (ts, f"OID-{idx}", "OPUSDT", "Sell", 100.0, 0.4051, 0.08, -0.72, "grid_trading")
        for idx in range(101)
    ])
    _install_fake_db(monkeypatch, cursor)
    monkeypatch.setattr(routes, "_get_rust_client", lambda: None)

    result = await routes.get_demo_closed_pnl(
        limit=100,
        offset=0,
        cursor=None,
        symbol=None,
        force_refresh=False,
        cursor_mode=True,
        actor=object(),
    )
    data = result["data"]

    assert data["source"] == "pg_fallback"
    assert data["count"] == 100
    assert data["has_more"] is True
    assert data["next_cursor"]
    decoded = routes._closed_pnl_decode_cursor(data["next_cursor"])
    assert decoded["source"] == "pg"
    assert decoded["offset"] == 100
    assert decoded["engine_modes"] == ["demo", "live_demo"]


@pytest.mark.asyncio
async def test_demo_closed_pnl_second_same_query_uses_cache(monkeypatch):
    _install_fake_db(monkeypatch, _FakeCursor([]))
    fake_client = _FakeBybitClient([
        {"orderId": "OID1", "orderLinkId": "openclaw-grid-OPUSDT-001", "closedPnl": "1.0"},
    ])
    monkeypatch.setattr(routes, "_get_rust_client", lambda: fake_client)

    first = await routes.get_demo_closed_pnl(
        limit=1, offset=0, symbol=None, force_refresh=False, actor=object()
    )
    second = await routes.get_demo_closed_pnl(
        limit=1, offset=0, symbol=None, force_refresh=False, actor=object()
    )

    assert first["data"]["source"] == "bybit_api"
    assert second["data"]["source"] == "bybit_cached"
    assert fake_client.calls == 1


@pytest.mark.asyncio
async def test_demo_closed_pnl_pg_fallback_is_read_only_shape(monkeypatch):
    ts = datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc)
    cursor = _FakeCursor([
        (ts, "OID9", "OPUSDT", "Sell", 100.0, 0.4051, 0.08, -0.72, "grid_trading"),
    ])
    _install_fake_db(monkeypatch, cursor)
    monkeypatch.setattr(routes, "_get_rust_client", lambda: _FakeBybitClient(exc=RuntimeError("down")))

    result = await routes.get_demo_closed_pnl(
        limit=10, offset=0, symbol=None, force_refresh=False, actor=object()
    )
    data = result["data"]

    assert data["source"] == "pg_fallback"
    assert data["degraded_reason"].startswith("bybit_closed_pnl_unavailable")
    assert data["list"][0]["strategy_source"] == "pg_fill"
    assert "FROM trading.fills" in cursor.sql
    assert "ts >= to_timestamp(%s / 1000.0)" in cursor.sql
    assert "ts <= to_timestamp(%s / 1000.0)" in cursor.sql
    assert cursor.params[0] == "demo"
    assert cursor.params[1] == "live_demo"
    assert cursor.params[2] < cursor.params[3]
    assert cursor.params[4:] == (11, 0)
    assert "INSERT" not in cursor.sql.upper()
    assert "UPDATE" not in cursor.sql.upper()
    assert "DELETE" not in cursor.sql.upper()


@pytest.mark.asyncio
async def test_demo_closed_pnl_pg_fallback_when_client_unavailable(monkeypatch):
    ts = datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc)
    cursor = _FakeCursor([
        (ts, "OID9", "OPUSDT", "Sell", 100.0, 0.4051, 0.08, -0.72, "grid_trading"),
    ])
    _install_fake_db(monkeypatch, cursor)
    monkeypatch.setattr(routes, "_get_rust_client", lambda: None)

    result = await routes.get_demo_closed_pnl(
        limit=10, offset=0, symbol=None, force_refresh=False, actor=object()
    )
    data = result["data"]

    assert data["source"] == "pg_fallback"
    assert data["count"] == 1
    assert data["list"][0]["order_id"] == "OID9"
    assert data["bybit_failure_count_60s"] == 0
    assert data["degraded_until_ms"] is None
    assert data["degraded_reason"].startswith("bybit_client_unavailable; pg_fallback")


@pytest.mark.asyncio
async def test_demo_closed_pnl_three_bybit_failures_marks_operator_contact(monkeypatch):
    ts = datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc)
    cursor = _FakeCursor([
        (ts, "OID9", "OPUSDT", "Sell", 100.0, 0.4051, 0.08, -0.72, "grid_trading"),
    ])
    _install_fake_db(monkeypatch, cursor)
    monkeypatch.setattr(routes, "_get_rust_client", lambda: _FakeBybitClient(exc=RuntimeError("down")))

    result = None
    for _ in range(3):
        result = await routes.get_demo_closed_pnl(
            limit=10, offset=0, symbol=None, force_refresh=True, actor=object()
        )
    data = result["data"]

    assert data["source"] == "pg_fallback"
    assert data["bybit_failure_count_60s"] == 3
    assert data["degraded_until_ms"] > 0
    assert "bybit_unavailable_5min_contact_operator" in data["degraded_reason"]


@pytest.mark.asyncio
async def test_demo_fills_query_includes_live_demo_engine_mode(monkeypatch):
    cursor = _FakeCursor([])
    _install_fake_db(monkeypatch, cursor)

    result = await routes.get_demo_fills(limit=10, offset=0, side=None, actor=object())

    assert result["data"]["source"] == "pg_trading_fills"
    assert "engine_mode IN (%s, %s)" in cursor.sql
    assert cursor.params[:2] == ("demo", "live_demo")


def test_closed_pnl_cache_deduplicates_inflight_fetches():
    cache = ClosedPnlCache(ttl_sec=8.0)
    entered = threading.Event()
    release = threading.Event()
    calls = 0
    results: list[Any] = []

    def fetcher():
        nonlocal calls
        calls += 1
        entered.set()
        release.wait(timeout=2.0)
        return [{"orderId": "OID1"}]

    def worker():
        results.append(cache.get_or_fetch(("k",), fetcher))

    t1 = threading.Thread(target=worker)
    t1.start()
    assert entered.wait(timeout=2.0)
    t2 = threading.Thread(target=worker)
    t2.start()
    time.sleep(0.05)
    release.set()
    t1.join(timeout=2.0)
    t2.join(timeout=2.0)

    assert calls == 1
    assert len(results) == 2
    assert sorted(result.hit for result in results) == [False, True]
