from __future__ import annotations

from pathlib import Path

import pytest


STATIC_DIR = Path(__file__).resolve().parents[1] / "app" / "static"


class _SnapshotReader:
    def is_engine_available(self, engine: str) -> bool:
        return engine in {"demo", "live"}

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


def test_demo_and_live_tabs_use_fast_initial_snapshot_paths() -> None:
    demo = (STATIC_DIR / "tab-demo.html").read_text(encoding="utf-8")
    live = (STATIC_DIR / "tab-live.html").read_text(encoding="utf-8")

    assert "/api/v1/strategy/demo/balance?fast=1" in demo
    assert "/api/v1/strategy/demo/positions?fast=1" in demo
    assert "await loadDemoFills();" not in demo

    assert "/api/v1/live/balance?fast=1" in live
    assert "/api/v1/live/positions?fast=1" in live
    assert "btn-live-start-locked" in live
    assert "status_unavailable" in live
