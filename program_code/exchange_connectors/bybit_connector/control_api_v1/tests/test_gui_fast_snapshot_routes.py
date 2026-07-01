from __future__ import annotations

from pathlib import Path

import pytest


STATIC_DIR = Path(__file__).resolve().parents[1] / "app" / "static"


class _SnapshotReader:
    def is_engine_available(self, engine: str) -> bool:
        return engine in {"demo", "live"}

    def get_engine_snapshot(self, engine: str) -> dict:
        assert engine in {"demo", "live"}
        return {
            "recent_fills": [
                {
                    "timestamp_ms": 1_770_000_000_000,
                    "symbol": "BTCUSDT",
                    "is_long": True,
                    "qty": 0.01,
                    "price": 50000.0,
                    "fee": 0.2,
                    "realized_pnl": 1.5,
                    "strategy": "ma_crossover",
                }
            ],
            "active_orders": [
                {
                    "symbol": "BTCUSDT",
                    "order_id": "oid-1",
                    "order_status": "New",
                    "order_type": "Limit",
                }
            ],
        }

    def get_paper_state(self, engine: str) -> dict:
        assert engine in {"demo", "live"}
        return {
            "balance": 1000.0,
            "bybit_sync_balance": 1002.5,
            "initial_balance": 990.0,
            "peak_balance": 1010.0,
            "total_realized_pnl": 7.0,
            "total_fees": 1.25,
            "positions": [
                {
                    "symbol": "BTCUSDT",
                    "is_long": True,
                    "qty": 0.01,
                    "entry_price": 50000.0,
                    "best_price": 50100.0,
                    "unrealized_pnl": 1.0,
                    "owner_strategy": "ma_crossover",
                }
            ],
        }


class _EmptySnapshotReader(_SnapshotReader):
    def get_paper_state(self, engine: str) -> dict:
        assert engine == "demo"
        return {}


@pytest.mark.asyncio
async def test_demo_fast_balance_uses_snapshot_without_rest(monkeypatch) -> None:
    from app import paper_trading_routes
    from app import strategy_ai_routes as routes

    monkeypatch.setattr(paper_trading_routes, "get_rust_reader", lambda: _SnapshotReader())
    monkeypatch.setattr(
        routes,
        "_get_rust_client",
        lambda: pytest.fail("fast demo balance must not create a Bybit REST client"),
    )

    out = await routes.get_demo_balance(fast=True, actor=None)

    data = out["data"]
    assert data["read_model"] == "rust_snapshot_fast"
    assert data["totalEquity"] == 1002.5
    assert data["engine_initial_balance"] == 990.0


@pytest.mark.asyncio
async def test_demo_fast_balance_missing_snapshot_fails_closed_without_rest(monkeypatch) -> None:
    from app import paper_trading_routes
    from app import strategy_ai_routes as routes

    monkeypatch.setattr(
        paper_trading_routes,
        "get_rust_reader",
        lambda: _EmptySnapshotReader(),
    )
    monkeypatch.setattr(
        routes,
        "_get_rust_client",
        lambda: pytest.fail("fast demo balance must not fall back to Bybit REST"),
    )

    out = await routes.get_demo_balance(fast=True, actor=None)

    data = out["data"]
    assert data["source"] == "rust_engine"
    assert data["read_model"] == "rust_snapshot_fast"
    assert data["pipeline_status"] == "snapshot_unavailable"
    assert data["enabled"] is False
    assert data["totalEquity"] is None
    assert data["equity"] is None
    assert data["balance"] is None


@pytest.mark.asyncio
async def test_demo_fast_positions_uses_snapshot_without_rest(monkeypatch) -> None:
    from app import paper_trading_routes
    from app import strategy_ai_routes as routes

    monkeypatch.setattr(paper_trading_routes, "get_rust_reader", lambda: _SnapshotReader())
    monkeypatch.setattr(
        routes,
        "_get_rust_client",
        lambda: pytest.fail("fast demo positions must not create a Bybit REST client"),
    )

    out = await routes.get_demo_positions(fast=True, actor=None)

    row = out["data"]["list"][0]
    assert out["data"]["source"] == "rust_snapshot_fast"
    assert row["symbol"] == "BTCUSDT"
    assert row["side"] == "Buy"
    assert row["avgPrice"] == 50000.0
    assert row["markPrice"] == 50100.0
    assert row["owner_strategy"] == "ma_crossover"


@pytest.mark.asyncio
async def test_demo_fast_dashboard_reads_use_snapshot_without_rest_or_db(monkeypatch) -> None:
    from app import db_pool
    from app import paper_trading_routes
    from app import strategy_ai_routes as routes

    monkeypatch.setattr(paper_trading_routes, "get_rust_reader", lambda: _SnapshotReader())
    monkeypatch.setattr(
        routes,
        "_get_rust_client",
        lambda: pytest.fail("fast demo dashboard reads must not create a Bybit REST client"),
    )
    monkeypatch.setattr(
        db_pool,
        "get_conn",
        lambda: pytest.fail("fast demo dashboard reads must not borrow a PG connection"),
    )

    orders = await routes.get_demo_orders(fast=True, actor=None)
    fills = await routes.get_demo_fills(limit=200, offset=0, side=None, fast=True, actor=None)
    series = await routes.get_demo_pnl_series(range_key="24h", bucket_sec=None, fast=True, actor=None)
    metrics = await routes.get_demo_metrics(fast=True, actor=None)

    assert orders["data"]["source"] == "rust_snapshot_fast"
    assert orders["data"]["result"]["list"][0]["orderId"] == "oid-1"
    assert fills["data"]["source"] == "rust_snapshot_fast"
    assert fills["data"]["list"][0]["execQty"] == 0.01
    assert series["data"]["source"] == "rust_snapshot_fast"
    assert metrics["data"]["source"] == "rust_snapshot_fast"
    assert metrics["data"]["performance_metrics"]


@pytest.mark.asyncio
async def test_live_fast_balance_uses_snapshot_without_rest(monkeypatch) -> None:
    from app import live_session_account_routes as routes
    from app import live_session_routes as core

    monkeypatch.setattr(routes, "_phantom_view_guard", lambda: None)
    monkeypatch.setattr(core, "_get_live_engine_kind", lambda: "live")
    monkeypatch.setattr(core, "_resolve_live_endpoint_label", lambda: "live_demo")
    monkeypatch.setattr(routes, "get_rust_reader", lambda: _SnapshotReader())
    monkeypatch.setattr(
        core,
        "_get_rust_client_safe",
        lambda: pytest.fail("fast live balance must not create a Bybit REST client"),
    )

    out = await routes.get_live_balance(fast=True, actor=None)

    assert out["data"]["read_model"] == "rust_snapshot_fast"
    assert out["data"]["actual_engine_kind"] == "live"
    assert out["data"]["actual_endpoint"] == "live_demo"


@pytest.mark.asyncio
async def test_live_demo_fast_balance_uses_snapshot_without_rest(monkeypatch) -> None:
    from app import live_session_account_routes as routes
    from app import live_session_routes as core

    monkeypatch.setattr(routes, "_phantom_view_guard", lambda: None)
    monkeypatch.setattr(core, "_get_live_engine_kind", lambda: "live_demo")
    monkeypatch.setattr(core, "_resolve_live_endpoint_label", lambda: "live_demo")
    monkeypatch.setattr(routes, "get_rust_reader", lambda: _SnapshotReader())
    monkeypatch.setattr(
        core,
        "_get_rust_client_safe",
        lambda: pytest.fail("fast live-demo balance must not create a Bybit REST client"),
    )

    out = await routes.get_live_balance(fast=True, actor=None)

    assert out["data"]["read_model"] == "rust_snapshot_fast"
    assert out["data"]["actual_engine_kind"] == "live_demo"
    assert out["data"]["actual_endpoint"] == "live_demo"


def test_demo_and_live_tabs_use_fast_initial_snapshot_paths() -> None:
    demo = (STATIC_DIR / "tab-demo.html").read_text(encoding="utf-8")
    live = (
        (STATIC_DIR / "tab-live.html").read_text(encoding="utf-8")
        + "\n"
        + (STATIC_DIR / "tab-live.js").read_text(encoding="utf-8")
    )

    assert "/api/v1/strategy/demo/balance?fast=1" in demo
    assert "/api/v1/strategy/demo/positions?fast=1" in demo
    assert "/api/v1/strategy/demo/orders?fast=1" in demo
    assert "/api/v1/strategy/demo/metrics?fast=1" in demo
    assert "/api/v1/strategy/demo/pnl-series?fast=1&range=" in demo
    assert "/api/v1/strategy/demo/fills?fast=1&limit=200&offset=0" in demo
    assert "await loadDemoFills();" not in demo

    assert "/api/v1/live/balance?fast=1" in live
    assert "/api/v1/live/positions?fast=1" in live
    assert "btn-live-start-locked" in live
    assert "status_unavailable" in live


def test_sidebar_and_system_status_use_fast_balance_paths() -> None:
    console = (STATIC_DIR / "console.html").read_text(encoding="utf-8")
    system = (STATIC_DIR / "tab-system.html").read_text(encoding="utf-8")
    demo = (STATIC_DIR / "tab-demo.html").read_text(encoding="utf-8")
    paper = (STATIC_DIR / "tab-paper.html").read_text(encoding="utf-8")

    assert "api('/api/v1/live/balance?fast=1')" in console
    assert "api('/api/v1/live/balance')," not in console
    assert "api('/api/v1/strategy/demo/balance?fast=1')" in console
    assert "api('/api/v1/strategy/demo/balance')," not in console
    assert "api('/api/v1/strategy/demo/metrics?fast=1')" in console
    assert "ocApi('/api/v1/strategy/demo/balance?fast=1')" in system
    assert "ocApi('/api/v1/strategy/demo/balance?fast=1')" in demo
    assert "ocApi('/api/v1/strategy/demo/balance?fast=1')" in paper
