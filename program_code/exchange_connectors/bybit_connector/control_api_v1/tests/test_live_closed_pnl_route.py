"""Focused tests for Live closed-PnL cursor-mode read model.

MODULE_NOTE
模塊用途：鎖死 GET /api/v1/live/closed-pnl（cursor 模式）handler
    get_live_closed_pnl 對 _closed_pnl_history_cursor_payload 的跨模塊呼叫契約。
背景：P2b 重構把 _closed_pnl_history_cursor_payload 從 strategy_ai_routes 抽到
    closed_pnl_pagination，新增 3 個必填注入縫（engine_owner_lookup / record_failure /
    clear_failures）。in-module demo caller 已補注入，但 live_session_account_routes 的
    跨模塊 caller 漏補 → 每次 cursor 模式 TypeError 500。本模塊補上這條無覆蓋的路徑。
不變量：Live 與 Demo「共用同一份 failure-state + owner-map」（重構前閉包語意）。
    test_live_closed_pnl_cursor_observes_strategy_ai_routes_owner_map 證明注入的 lambda
    於呼叫時解析 routes._engine_owner_strategy_map（monkeypatch 可見）；
    test_live_closed_pnl_bybit_failure_records_shared_failure_state 證明失敗計數寫進
    strategy_ai_routes 的共享 _CLOSED_PNL_BYBIT_FAILURES，而非另立 Live 專屬狀態。
依賴：app.live_session_account_routes（handler）、app.live_session_routes（core helpers）、
    app.strategy_ai_routes（共享 failure-state + owner-map 單例）。
"""

from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
from typing import Any

import pytest

from app import live_session_account_routes as live_routes
from app import live_session_routes as core
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
    """單視窗 fake：僅最近視窗回 rows，更舊視窗回空。

    為什麼只回一次：_fetch_closed_pnl_bybit_history_page 在 rows 未滿 limit 時會向前
    回溯多達 _CLOSED_PNL_MAX_WINDOWS_PER_PRELOAD 個 7 天視窗（每視窗一次 get_closed_pnl 呼叫，
    cursor=None）。若每視窗都回同一批 rows，count 會被乘上視窗數而非反映真實單視窗資料。
    """

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
        rows = self.rows if self.calls == 1 else []
        return {
            "category": category,
            "list": [dict(row) for row in rows[:limit]],
            "nextPageCursor": "",
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
def _live_view_and_fresh_state(monkeypatch: pytest.MonkeyPatch):
    """放行 phantom-view guard（視為 LiveDemo live engine）並清空共享 failure-state。

    為什麼放行：本模塊測的是 cursor payload 契約，不是 phantom-view 守衛；
    將 engine_kind 設為 live、endpoint 設為 live_demo 讓 guard 回 None 進入正常 handler。
    failure-state 清空避免測試間 _CLOSED_PNL_BYBIT_FAILURES 殘留互染。
    """
    monkeypatch.setattr(core, "_get_live_engine_kind", lambda: "live")
    monkeypatch.setattr(core, "_resolve_live_endpoint_label", lambda: "live_demo")
    monkeypatch.setattr(routes, "_CLOSED_PNL_CACHE", ClosedPnlCache(ttl_sec=8.0))
    routes._clear_closed_pnl_bybit_failures()
    yield
    routes._clear_closed_pnl_bybit_failures()


@pytest.mark.asyncio
async def test_live_closed_pnl_cursor_mode_returns_enriched_payload(monkeypatch):
    """回歸守衛：cursor 模式呼叫不再 TypeError，回傳 bybit_api 富集 payload。

    P2b 漏補注入縫前此 handler 每次 cursor 呼叫 TypeError 500；此測試是該類破壞
    再發的防線（172 既有測試漏掉本 endpoint）。
    """
    cursor = _FakeCursor([("OID1", "ma_crossover", 0.95)])
    _install_fake_db(monkeypatch, cursor)
    fake_client = _FakeBybitClient([
        {"orderId": "OID1", "orderLinkId": "oc_ld_1", "symbol": "OPUSDT", "closedPnl": "1.0"},
        {"orderId": "OID2", "orderLinkId": "external-link", "symbol": "OPUSDT", "closedPnl": "-0.5"},
    ])
    monkeypatch.setattr(core, "_get_rust_client_safe", lambda: fake_client)
    monkeypatch.setattr(routes, "_engine_owner_strategy_map", lambda engine: {})

    result = await live_routes.get_live_closed_pnl(
        limit=100,
        cursor=None,
        start_time=None,
        end_time=None,
        symbol=None,
        lookback_days=730,
        actor=object(),
    )
    data = result["data"]

    assert data["source"] == "bybit_api"
    assert data["count"] == 2
    assert data["all_history"] is True
    assert [row["orderId"] for row in data["list"]] == ["OID1", "OID2"]
    # 730 天 lookback 在 8 視窗上限前未走完歷史 → 回延續 cursor 供 GUI 續拉更舊視窗
    # （與 demo 路徑同行為，非終止）。
    assert isinstance(data["next_cursor"], str) and data["next_cursor"]
    assert routes._closed_pnl_decode_cursor(data["next_cursor"])["source"] == "bybit"
    # _live_response 包裝標記
    assert data["is_simulated"] is False
    assert data["data_category"] == "live_exchange"
    # cursor 模式查詢 live + live_demo 兩 engine_mode
    assert cursor.params[1:] == ("live", "live_demo")


@pytest.mark.asyncio
async def test_live_closed_pnl_cursor_observes_strategy_ai_routes_owner_map(monkeypatch):
    """行為保持證明：注入的 engine_owner_lookup 於呼叫時解析 routes._engine_owner_strategy_map。

    重構前本函數定義於 strategy_ai_routes、閉包讀其 owner-map；故 Live 一直「共用」該 map。
    這裡 monkeypatch routes._engine_owner_strategy_map 後 Live payload 必須觀察到該 owner，
    證明 lambda 是 call-time 解析（非 import-time 綁定）且指向共享單例。
    """
    cursor = _FakeCursor([])
    _install_fake_db(monkeypatch, cursor)
    fake_client = _FakeBybitClient([
        {"orderId": "OID-LD", "orderLinkId": "oc_ld_9", "symbol": "ETHUSDT", "closedPnl": "0.7"},
    ])
    monkeypatch.setattr(core, "_get_rust_client_safe", lambda: fake_client)
    # 僅 live_demo engine 命中 owner-map → 驗注入 lambda 確實透傳 engine 名並解析共享 map
    monkeypatch.setattr(
        routes,
        "_engine_owner_strategy_map",
        lambda engine: {"ETHUSDT": "funding_arb"} if engine == "live_demo" else {},
    )

    result = await live_routes.get_live_closed_pnl(
        limit=10,
        cursor=None,
        start_time=None,
        end_time=None,
        symbol=None,
        lookback_days=730,
        actor=object(),
    )
    data = result["data"]

    assert data["list"][0]["strategy_source"] == "pg_link_id"
    assert data["list"][0]["strategy_name"] == "funding_arb"


@pytest.mark.asyncio
async def test_live_closed_pnl_missing_order_link_uses_pg_time_window_strategy(monkeypatch):
    ts = datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc)
    ts_ms = int(ts.timestamp() * 1000)
    cursor = _SequencedFakeCursor([
        [],
        [(ts, "oc_ipc_close_lv_1770000000000_5", "BTCUSDT", "Sell", 0.01, 2.50, "ma_crossover")],
    ])
    _install_fake_db(monkeypatch, cursor)
    fake_client = _FakeBybitClient([
        {
            "orderId": "BYBIT-LIVE-CLOSE-1",
            "orderLinkId": "",
            "symbol": "BTCUSDT",
            "closedPnl": "2.40",
            "updatedTime": str(ts_ms + 250),
        },
    ])
    monkeypatch.setattr(core, "_get_rust_client_safe", lambda: fake_client)
    monkeypatch.setattr(routes, "_engine_owner_strategy_map", lambda engine: {})

    result = await live_routes.get_live_closed_pnl(
        limit=10,
        cursor=None,
        start_time=None,
        end_time=None,
        symbol=None,
        lookback_days=730,
        actor=object(),
    )
    row = result["data"]["list"][0]

    assert row["strategy_name"] == "ma_crossover"
    assert row["strategy_source"] == "pg_time_window"
    assert row["pg_engine_pnl"] == 2.50
    assert row["strategy_match_delta_ms"] == 250
    assert cursor.params_list[0][1:] == ("live", "live_demo")
    assert cursor.params_list[1][:2] == ("live", "live_demo")


@pytest.mark.asyncio
async def test_live_closed_pnl_bybit_failure_records_shared_failure_state(monkeypatch):
    """行為保持證明：Live bybit 失敗寫進 strategy_ai_routes 的共享 _CLOSED_PNL_BYBIT_FAILURES。

    注入的 record_failure 必須是 routes._record_closed_pnl_bybit_failure，不另立 Live 專屬狀態；
    失敗後 PG fallback 帶 bybit_failure_count_60s，且共享 list 長度反映該次失敗。
    """
    ts = datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc)
    cursor = _FakeCursor([
        (ts, "OID9", "OPUSDT", "Sell", 100.0, 0.4051, 0.08, -0.72, "grid_trading"),
    ])
    _install_fake_db(monkeypatch, cursor)
    monkeypatch.setattr(
        core, "_get_rust_client_safe", lambda: _FakeBybitClient(exc=RuntimeError("down"))
    )
    monkeypatch.setattr(routes, "_engine_owner_strategy_map", lambda engine: {})

    assert len(routes._CLOSED_PNL_BYBIT_FAILURES) == 0
    result = await live_routes.get_live_closed_pnl(
        limit=10,
        cursor=None,
        start_time=None,
        end_time=None,
        symbol=None,
        lookback_days=730,
        actor=object(),
    )
    data = result["data"]

    assert data["source"] == "pg_fallback"
    assert data["bybit_failure_count_60s"] == 1
    assert data["degraded_reason"].startswith("bybit_closed_pnl_unavailable")
    # 失敗計入 strategy_ai_routes 的共享單例（非 Live 專屬）
    assert len(routes._CLOSED_PNL_BYBIT_FAILURES) == 1


@pytest.mark.asyncio
async def test_live_closed_pnl_phantom_guard_short_circuits_before_cursor(monkeypatch):
    """守衛先行：Live 槽未配置時回 phantom envelope，不進 cursor payload 路徑。"""
    monkeypatch.setattr(core, "_get_live_engine_kind", lambda: "demo")
    monkeypatch.setattr(core, "_resolve_live_endpoint_label", lambda: "unconfigured")

    def _boom():  # pragma: no cover - 不應被呼叫
        raise AssertionError("rust client must not be fetched when phantom guard fires")

    monkeypatch.setattr(core, "_get_rust_client_safe", _boom)

    result = await live_routes.get_live_closed_pnl(
        limit=100,
        cursor=None,
        start_time=None,
        end_time=None,
        symbol=None,
        lookback_days=730,
        actor=object(),
    )
    data = result["data"]

    assert data["available"] is False
    assert data["error"] == "live_slot_not_configured"
