"""
Strategist history route tests (STRATEGIST-HISTORY-OBSERVABILITY-1 backend).
策略師歷史路由測試。

MODULE_NOTE (EN): Covers the three read endpoints:
  * list         — filters + limit echo + fail-closed empty rows
  * summary      — aggregate by source + zero-fallback + PG-down path
  * {id}/effect  — row lookup + 7d fills aggregate + LiveDemo widening
Uses a fake DB connection so tests are hermetic — no real PG required.

MODULE_NOTE (中): 三條路由（list / summary / {id}/effect）煙霧 + 邊界測試，
  fake DB 取代真實 PG，保持測試封閉。
"""

from __future__ import annotations

import datetime as dt
import os
import sys
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import pytest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import strategist_history_routes as sh_module  # noqa: E402
from app.main_legacy import AuthenticatedActor, current_actor  # noqa: E402
from app.strategist_history_routes import (  # noqa: E402
    _ALLOWED_ENGINE_MODES,
    _ALLOWED_SOURCES,
    _ALLOWED_STRATEGIES,
    _SEVEN_DAYS_MS,
    strategist_history_router,
)


def _viewer_actor() -> AuthenticatedActor:
    """Viewer actor stand-in for route auth override.
    覆寫 current_actor 的 viewer stub。"""
    return AuthenticatedActor(
        actor_id="test-viewer",
        actor_type="human",
        roles={"viewer"},
        scopes={"private_readonly"},
    )


class _FakeCursor:
    """Minimal cursor supporting execute / fetchall / fetchone / description.
    最小 cursor stub，支援 execute / fetchall / fetchone / description。"""

    def __init__(self, rows: list[tuple[Any, ...]], columns: list[str]) -> None:
        self._rows = rows
        self._columns = columns
        self.description = [type("Col", (), {"name": c})() for c in columns]
        self.last_sql: str | None = None
        self.last_args: tuple[Any, ...] | None = None

    def execute(self, sql: str, args: tuple[Any, ...] | None = None) -> None:
        self.last_sql = sql
        self.last_args = args

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._rows[0] if self._rows else None


class _FakeConn:
    def __init__(self, rows: list[tuple[Any, ...]], columns: list[str]) -> None:
        self._cur = _FakeCursor(rows, columns)

    def cursor(self) -> _FakeCursor:
        return self._cur


@contextmanager
def _pg_returns(rows: list[tuple[Any, ...]], columns: list[str]):
    """Patch get_pg_conn to yield a fake connection with the given rowset.
    Patch get_pg_conn 回帶 rowset 的 fake 連線。"""

    @contextmanager
    def _fake() -> Any:
        yield _FakeConn(rows, columns)

    with patch.object(sh_module, "get_pg_conn", _fake):
        yield


@contextmanager
def _pg_unavailable():
    """Patch get_pg_conn to yield None (DB offline path).
    Patch get_pg_conn 回 None，模擬 PG 不可用。"""

    @contextmanager
    def _fake() -> Any:
        yield None

    with patch.object(sh_module, "get_pg_conn", _fake):
        yield


@pytest.fixture
def client() -> TestClient:
    """FastAPI test client with the router + auth override mounted.
    掛載路由與 auth 覆寫的 FastAPI 測試 client。"""
    app = FastAPI()
    app.include_router(strategist_history_router)
    app.dependency_overrides[current_actor] = _viewer_actor
    return TestClient(app)


# ─── /api/v1/strategist/history (list) ───────────────────────────────────


def test_list_returns_200_when_pg_down(client: TestClient) -> None:
    """PG 不可用 → 200 + degraded=true + rows=[]，不 5xx。"""
    with _pg_unavailable():
        resp = client.get("/api/v1/strategist/history")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["rows"] == []
    assert body["data"]["degraded"] is True
    assert body["data"]["reason"] == "pg_unavailable"


def test_list_rejects_non_whitelisted_engine_mode(client: TestClient) -> None:
    """engine_mode 不在白名單 → 400。"""
    resp = client.get(
        "/api/v1/strategist/history", params={"engine_mode": "mainnet_live"}
    )
    assert resp.status_code == 400


def test_list_rejects_non_whitelisted_strategy(client: TestClient) -> None:
    """strategy_name 不在白名單 → 400，防 URL 注入 GROUP BY。"""
    resp = client.get(
        "/api/v1/strategist/history", params={"strategy_name": "not_a_strategy"}
    )
    assert resp.status_code == 400


def test_list_rejects_non_whitelisted_source(client: TestClient) -> None:
    """source 不在白名單 → 400。"""
    resp = client.get(
        "/api/v1/strategist/history", params={"source": "ghost_cron"}
    )
    assert resp.status_code == 400


def test_list_accepts_all_whitelisted_engine_modes(client: TestClient) -> None:
    """白名單內的每個 engine_mode 都應被接受（行為覆蓋）。"""
    for mode in _ALLOWED_ENGINE_MODES:
        with _pg_returns([], []):
            resp = client.get(
                "/api/v1/strategist/history", params={"engine_mode": mode}
            )
        assert resp.status_code == 200, f"engine_mode={mode} unexpectedly rejected"


def test_list_surfaces_rows_and_filter_echo(client: TestClient) -> None:
    """正常 row 返回 + filters echo + applied_at ISO 化。"""
    applied_at = dt.datetime(2026, 4, 23, 12, 30, 0, tzinfo=dt.timezone.utc)
    applied_at_ms = int(applied_at.timestamp() * 1000)
    row = (
        42,  # id
        "demo",  # engine_mode
        "ma_crossover",  # strategy_name
        applied_at,  # applied_at
        applied_at_ms,  # applied_at_ms
        "strategist_scheduler",  # source
        "top_deviation_pair",  # reason
        {"cooldown_ms": 50000.0},  # prev_params_json
        {"cooldown_ms": 55000.0},  # params_json
    )
    cols = [
        "id",
        "engine_mode",
        "strategy_name",
        "applied_at",
        "applied_at_ms",
        "source",
        "reason",
        "prev_params_json",
        "params_json",
    ]
    with _pg_returns([row], cols):
        resp = client.get(
            "/api/v1/strategist/history",
            params={
                "engine_mode": "demo",
                "strategy_name": "ma_crossover",
                "limit": 10,
            },
        )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["degraded"] is False
    assert data["filters"]["engine_mode"] == "demo"
    assert data["filters"]["strategy_name"] == "ma_crossover"
    assert data["limit"] == 10
    assert len(data["rows"]) == 1
    returned = data["rows"][0]
    assert returned["id"] == 42
    assert returned["source"] == "strategist_scheduler"
    assert returned["applied_at"].startswith("2026-04-23T12:30:00")
    assert returned["prev_params_json"] == {"cooldown_ms": 50000.0}
    assert returned["params_json"] == {"cooldown_ms": 55000.0}


def test_list_limit_bounds(client: TestClient) -> None:
    """limit 越界 → 422（FastAPI Query constraint 層）。"""
    with _pg_returns([], []):
        resp = client.get("/api/v1/strategist/history", params={"limit": 0})
    assert resp.status_code == 422
    with _pg_returns([], []):
        resp = client.get("/api/v1/strategist/history", params={"limit": 10_000})
    assert resp.status_code == 422


# ─── /api/v1/strategist/history/summary ──────────────────────────────────


def test_summary_zero_fallback_when_empty(client: TestClient) -> None:
    """空表 → total=0 + by_source=[] + degraded=false。"""
    with _pg_returns([], []):
        resp = client.get("/api/v1/strategist/history/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["total"] == 0
    assert body["data"]["by_source"] == []
    assert body["data"]["degraded"] is False


def test_summary_surfaces_aggregate_rows(client: TestClient) -> None:
    """多 source 聚合 → total + by_source[] 排序。"""
    first = dt.datetime(2026, 4, 20, 0, 0, 0, tzinfo=dt.timezone.utc)
    last = dt.datetime(2026, 4, 23, 12, 0, 0, tzinfo=dt.timezone.utc)
    rows = [
        ("strategist_scheduler", 17, first, last),
        ("manual_promote", 3, first, last),
    ]
    with _pg_returns(rows, ["source", "n", "first_applied_at", "last_applied_at"]):
        resp = client.get("/api/v1/strategist/history/summary")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 20
    by_source = {r["source"]: r for r in data["by_source"]}
    assert by_source["strategist_scheduler"]["n"] == 17
    assert by_source["manual_promote"]["n"] == 3
    # notes.success_ratio explains provisional semantics to the GUI.
    # notes.success_ratio 把暫時語意告訴 GUI。
    assert "success_ratio" in data["notes"]


def test_summary_degrades_when_pg_down(client: TestClient) -> None:
    """PG 不可用 → 200 + degraded=true + total=0。"""
    with _pg_unavailable():
        resp = client.get("/api/v1/strategist/history/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["degraded"] is True
    assert body["data"]["total"] == 0


def test_summary_rejects_invalid_engine_mode(client: TestClient) -> None:
    """engine_mode 白名單 → 400。"""
    resp = client.get(
        "/api/v1/strategist/history/summary",
        params={"engine_mode": "paper_testnet"},
    )
    assert resp.status_code == 400


# ─── /api/v1/strategist/history/{id}/effect ──────────────────────────────


def test_effect_404_when_row_not_found(client: TestClient) -> None:
    """列不存在 → 404。"""
    with _pg_returns([], []):
        resp = client.get("/api/v1/strategist/history/999/effect")
    assert resp.status_code == 404


def test_effect_degraded_when_pg_down(client: TestClient) -> None:
    """PG 不可用 → 200 + row=null + effect=null + degraded=true。"""
    with _pg_unavailable():
        resp = client.get("/api/v1/strategist/history/1/effect")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["degraded"] is True
    assert body["data"]["row"] is None
    assert body["data"]["effect"] is None


def test_effect_returns_row_and_7d_aggregate(client: TestClient) -> None:
    """正常路徑：row fetch + fills 7d 聚合 + window 正確計算。"""
    applied_at = dt.datetime(2026, 4, 20, 10, 0, 0, tzinfo=dt.timezone.utc)
    applied_at_ms = int(applied_at.timestamp() * 1000)
    first_fill = dt.datetime(2026, 4, 20, 11, 0, 0, tzinfo=dt.timezone.utc)
    last_fill = dt.datetime(2026, 4, 26, 9, 0, 0, tzinfo=dt.timezone.utc)

    # First call: SELECT row by id → 9-col applied_params row.
    # Second call: SELECT 7d fills aggregate → (fill_count, net_pnl,
    #     win_rate, first_fill_ts, last_fill_ts) 5-tuple.
    # 第一次查 applied_params row；第二次查 fills 7d 聚合。
    row_cols = [
        "id",
        "engine_mode",
        "strategy_name",
        "applied_at",
        "applied_at_ms",
        "source",
        "reason",
        "prev_params_json",
        "params_json",
    ]
    applied_row = (
        7,
        "demo",
        "grid_trading",
        applied_at,
        applied_at_ms,
        "manual_promote",
        "promote_from_demo",
        {"grid_step_bps": 10.0},
        {"grid_step_bps": 12.0},
    )
    effect_row = (47, 123.4, 0.57, first_fill, last_fill)

    # Two sequential SELECTs in one request → we stub both. The simplest
    # portable way is a counter-based factory that returns different
    # cursors per call.
    # 同請求兩次 SELECT → 用計數器 factory 分別回不同 cursor。
    call_count = {"n": 0}

    @contextmanager
    def _fake() -> Any:
        call_count["n"] += 1
        if call_count["n"] == 1:
            yield _FakeConn([applied_row], row_cols)
        else:
            yield _FakeConn(
                [effect_row],
                ["fill_count", "net_pnl", "win_rate", "first_fill_ts", "last_fill_ts"],
            )

    with patch.object(sh_module, "get_pg_conn", _fake):
        resp = client.get("/api/v1/strategist/history/7/effect")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["degraded"] is False
    assert data["row"]["id"] == 7
    assert data["row"]["source"] == "manual_promote"
    effect = data["effect"]
    assert effect["fill_count"] == 47
    assert pytest.approx(effect["net_pnl"], rel=1e-6) == 123.4
    assert pytest.approx(effect["win_rate"], rel=1e-6) == 0.57
    # Window = [applied_at_ms, applied_at_ms + 7d] / 7 日窗口驗證。
    assert effect["window_start_ms"] == applied_at_ms
    assert effect["window_end_ms"] == applied_at_ms + _SEVEN_DAYS_MS


def test_effect_widens_mode_filter_for_live_rows() -> None:
    """Unit test on the effect query: engine_mode='live' must widen to
    IN ('live','live_demo') so LiveDemo fills aren't dropped.
    engine_mode='live' 查詢必須擴為 IN ('live','live_demo')，避免漏 LiveDemo fill。"""
    captured: dict[str, Any] = {}

    class _CaptureCursor(_FakeCursor):
        def execute(self, sql: str, args: tuple[Any, ...] | None = None) -> None:
            captured["sql"] = sql
            captured["args"] = args
            super().execute(sql, args)

    class _CaptureConn:
        def __init__(self) -> None:
            self._cur = _CaptureCursor([(0, 0.0, 0.0, None, None)], [])

        def cursor(self) -> _CaptureCursor:
            return self._cur

    @contextmanager
    def _fake() -> Any:
        yield _CaptureConn()

    with patch.object(sh_module, "get_pg_conn", _fake):
        result, err = sh_module._fetch_effect_for_row(
            engine_mode="live",
            strategy_name="ma_crossover",
            applied_at_ms=1_700_000_000_000,
        )
    assert err is None
    assert result["fill_count"] == 0
    assert "engine_mode IN (%s, %s)" in captured["sql"]
    # first two args are (live, live_demo) — widening applied.
    # 前兩參數 (live, live_demo) — 擴寬已生效。
    assert captured["args"][0] == "live"
    assert captured["args"][1] == "live_demo"


def test_effect_keeps_single_mode_filter_for_non_live() -> None:
    """Non-live engine_mode uses `=` single-value filter (no widening).
    非 live engine_mode 保持 `=` 單值 filter。"""
    captured: dict[str, Any] = {}

    class _CaptureCursor(_FakeCursor):
        def execute(self, sql: str, args: tuple[Any, ...] | None = None) -> None:
            captured["sql"] = sql
            captured["args"] = args
            super().execute(sql, args)

    class _CaptureConn:
        def __init__(self) -> None:
            self._cur = _CaptureCursor([(0, 0.0, 0.0, None, None)], [])

        def cursor(self) -> _CaptureCursor:
            return self._cur

    @contextmanager
    def _fake() -> Any:
        yield _CaptureConn()

    with patch.object(sh_module, "get_pg_conn", _fake):
        _, err = sh_module._fetch_effect_for_row(
            engine_mode="demo",
            strategy_name="grid_trading",
            applied_at_ms=1_700_000_000_000,
        )
    assert err is None
    assert "engine_mode = %s" in captured["sql"]
    assert "engine_mode IN (%s, %s)" not in captured["sql"]
    assert captured["args"][0] == "demo"


# ─── Module-level sanity ────────────────────────────────────────────────


def test_whitelists_populated() -> None:
    """Safety net on the module-level allow-lists.
    白名單非空健全檢查。"""
    assert len(_ALLOWED_ENGINE_MODES) >= 3
    assert "demo" in _ALLOWED_ENGINE_MODES
    assert "live" in _ALLOWED_ENGINE_MODES
    assert "live_demo" in _ALLOWED_ENGINE_MODES
    assert "strategist_scheduler" in _ALLOWED_SOURCES
    assert "manual_promote" in _ALLOWED_SOURCES
    assert "ma_crossover" in _ALLOWED_STRATEGIES
    assert "grid_trading" in _ALLOWED_STRATEGIES
