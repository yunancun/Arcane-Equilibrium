"""Focused tests for Paper fill-history pagination."""

from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
from typing import Any

from app import paper_trading_routes as routes


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


class _FakeConn:
    def __init__(self, cursor: _FakeCursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def _install_fake_db(monkeypatch, cursor: _FakeCursor) -> None:
    fake_db = types.SimpleNamespace(
        get_conn=lambda: _FakeConn(cursor),
        put_conn=lambda conn: None,
    )
    monkeypatch.setitem(sys.modules, "app.db_pool", fake_db)
    import app  # noqa: PLC0415
    monkeypatch.setattr(app, "db_pool", fake_db, raising=False)


def test_paper_fills_pg_paginates_with_limit_plus_one(monkeypatch):
    ts = datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc)
    cursor = _FakeCursor([
        (ts, "OPUSDT", "Sell", 100.0, 0.4051, 0.08, -0.72, "grid_trading")
        for _ in range(101)
    ])
    _install_fake_db(monkeypatch, cursor)

    result = routes.get_fills(limit=100, offset=200, actor=object())
    data = result["data"]

    assert data["source"] == "pg_trading_fills"
    assert data["count"] == 100
    assert data["limit"] == 100
    assert data["offset"] == 200
    assert data["has_more"] is True
    assert data["next_offset"] == 300
    assert "LIMIT %s OFFSET %s" in cursor.sql
    assert cursor.params == ("paper", 101, 200)
