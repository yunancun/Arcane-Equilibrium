"""
W1-T3 — strategy_read_routes / fills endpoint exit_reason passthrough tests.
W1-T3 — strategy_read_routes / fills 端點 exit_reason passthrough 測試。

MODULE_NOTE (EN):
  Pinning the GUI passthrough contract for ``GET /api/v1/strategy/data/fills/recent``
  per PA design 2026-04-29 §1.2 / §4 W1-T3 — the SELECT must return the
  V033 ``exit_reason`` column alongside ``strategy_name``. Fake DB stub keeps
  these tests hermetic (no real PG required).

  PA report: docs/CCAgentWorkSpace/PA/workspace/reports/
             2026-04-29--strategy_name_attribution_cleanup_design.md

MODULE_NOTE (中):
  W1-T3 GUI passthrough contract pinning — fills 端點 SELECT 必須包含 V033
  ``exit_reason`` 欄位。fake DB 保持封閉測試（不需真實 PG）。
"""

from __future__ import annotations

import os
import sys
from typing import Any
from unittest.mock import patch

import pytest

# ── PATH SETUP ─────────────────────────────────────────────────────────────
_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

os.environ.setdefault("OPENCLAW_API_TOKEN", "test-token")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import strategy_read_routes as srr_module  # noqa: E402
from app.strategy_wiring import phase2_router  # noqa: E402


# ── Fake DB infrastructure / 假 DB 基建 ───────────────────────────────────


class _FakeCursor:
    """Minimal cursor capturing executed SQL + args; returns canned rows.
    最小 cursor，記錄執行的 SQL + args；回 canned rows。"""

    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows
        self.last_sql: str | None = None
        self.last_args: tuple[Any, ...] | None = None

    def execute(self, sql: str, args: tuple[Any, ...] | None = None) -> None:
        self.last_sql = sql
        self.last_args = args

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows


class _FakeConn:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._cur = _FakeCursor(rows)

    def cursor(self) -> _FakeCursor:
        return self._cur


# ── Test fixtures / 測試固件 ──────────────────────────────────────────────


@pytest.fixture
def client() -> TestClient:
    """FastAPI test client mounting only the phase2_router for hermetic test.
    僅掛 phase2_router 的 FastAPI client，封閉測試。"""
    app = FastAPI()
    app.include_router(phase2_router)
    return TestClient(app)


# ── Tests / 測試 ──────────────────────────────────────────────────────────


def test_recent_fills_returns_exit_reason_in_select(client: TestClient) -> None:
    """[W1-T3] SELECT must include ``exit_reason`` column (V033 addition).
    Captures the executed SQL and asserts column appears in select-list.

    [W1-T3] SELECT 必含 ``exit_reason`` 欄位（V033 新增）。捕獲執行的 SQL
    並驗 column 在 select-list 中出現。
    """
    captured: dict[str, Any] = {}

    class _CaptureCursor(_FakeCursor):
        def execute(self, sql: str, args: tuple[Any, ...] | None = None) -> None:
            captured["sql"] = sql
            captured["args"] = args
            super().execute(sql, args)

    class _CaptureConn:
        def __init__(self) -> None:
            self._cur = _CaptureCursor([])

        def cursor(self) -> _CaptureCursor:
            return self._cur

    fake_conn = _CaptureConn()

    with patch.object(srr_module, "_get_pg_conn", return_value=fake_conn), \
         patch.object(srr_module, "_put_pg_conn", lambda c: None):
        resp = client.get("/api/v1/strategy/data/fills/recent")

    assert resp.status_code == 200
    # SQL select-list must include exit_reason (W1-T3 contract).
    # SQL select-list 必含 exit_reason（W1-T3 契約）。
    sql = captured["sql"] or ""
    assert "exit_reason" in sql, f"exit_reason missing from SELECT: {sql}"
    # strategy_name must remain (entry-strategy enum field).
    # strategy_name 必保留（entry strategy enum 欄位）。
    assert "strategy_name" in sql, f"strategy_name missing from SELECT: {sql}"


def test_recent_fills_response_includes_exit_reason_field(client: TestClient) -> None:
    """[W1-T3] Response JSON must surface ``exit_reason`` per fill row when
    DB returns 10-tuple (ts/fill_id/symbol/side/qty/price/fee/realized_pnl/
    strategy_name/exit_reason).

    [W1-T3] response JSON 必為每筆 fill row 暴露 ``exit_reason`` 欄位
    （DB 回 10-tuple）。
    """
    import datetime as dt

    sample_rows = [
        # Close fill: strategy_name=enum, exit_reason=dynamic trace.
        # close fill：strategy_name=enum、exit_reason=動態 trace。
        (
            dt.datetime(2026, 4, 29, 12, 0, 0, tzinfo=dt.timezone.utc),
            "fill_001",
            "BTCUSDT",
            "Sell",
            0.001,
            65000.0,
            0.0357,
            10.5,
            "grid_trading",
            "grid_close_long",
        ),
        # Entry fill: strategy_name=enum, exit_reason=NULL.
        # entry fill：strategy_name=enum、exit_reason=NULL。
        (
            dt.datetime(2026, 4, 29, 11, 30, 0, tzinfo=dt.timezone.utc),
            "fill_002",
            "ETHUSDT",
            "Buy",
            0.05,
            3500.0,
            0.0962,
            0.0,
            "ma_crossover",
            None,
        ),
    ]

    fake_conn = _FakeConn(sample_rows)

    with patch.object(srr_module, "_get_pg_conn", return_value=fake_conn), \
         patch.object(srr_module, "_put_pg_conn", lambda c: None):
        resp = client.get("/api/v1/strategy/data/fills/recent")

    assert resp.status_code == 200
    body = resp.json()
    # _envelope wraps response → look at .data.fills.
    # _envelope 包裝 → 從 .data.fills 取。
    fills = body.get("data", {}).get("fills") or body.get("fills") or []
    assert len(fills) == 2, f"expected 2 fills, got {len(fills)}"

    # Close fill carries the exit_reason trace.
    # close fill 帶 exit_reason trace。
    close = fills[0]
    assert close["strategy"] == "grid_trading"
    assert close["exit_reason"] == "grid_close_long"

    # Entry fill exit_reason is None / null (entry path).
    # entry fill exit_reason 為 None（entry path）。
    entry = fills[1]
    assert entry["strategy"] == "ma_crossover"
    assert entry["exit_reason"] is None


def test_recent_fills_with_symbol_filter_includes_exit_reason(
    client: TestClient,
) -> None:
    """[W1-T3] Symbol-filtered branch (``WHERE symbol=%s``) also includes
    ``exit_reason`` in SELECT — verify both code branches stay aligned.

    [W1-T3] symbol-filter 分支（``WHERE symbol=%s``）的 SELECT 也必含
    ``exit_reason`` — 驗兩個 code 路徑同步。
    """
    captured: dict[str, Any] = {}

    class _CaptureCursor(_FakeCursor):
        def execute(self, sql: str, args: tuple[Any, ...] | None = None) -> None:
            captured["sql"] = sql
            captured["args"] = args
            super().execute(sql, args)

    class _CaptureConn:
        def __init__(self) -> None:
            self._cur = _CaptureCursor([])

        def cursor(self) -> _CaptureCursor:
            return self._cur

    fake_conn = _CaptureConn()

    with patch.object(srr_module, "_get_pg_conn", return_value=fake_conn), \
         patch.object(srr_module, "_put_pg_conn", lambda c: None):
        resp = client.get("/api/v1/strategy/data/fills/recent?symbol=BTCUSDT&limit=10")

    assert resp.status_code == 200
    sql = captured["sql"] or ""
    assert "exit_reason" in sql, f"exit_reason missing from symbol-filter SQL: {sql}"
    assert "WHERE symbol = %s" in sql, f"symbol filter clause missing: {sql}"
    # First arg = symbol (uppercased by handler? — endpoint passes through raw).
    # 第一個參數 = symbol。
    assert captured["args"] == ("BTCUSDT", 10)


def test_recent_fills_db_unavailable_fail_closed(client: TestClient) -> None:
    """[W1-T3] DB unavailable → 503 + fail-closed empty fills (regression
    guard for the existing ``_get_pg_conn() is None`` path).

    [W1-T3] DB 不可用 → 503 + fail-closed 空 fills（既有
    ``_get_pg_conn() is None`` 路徑的 regression guard）。
    """
    with patch.object(srr_module, "_get_pg_conn", return_value=None):
        resp = client.get("/api/v1/strategy/data/fills/recent")

    assert resp.status_code == 503
    body = resp.json()
    assert body.get("error") == "database_unavailable"
    assert body.get("fills") == []
