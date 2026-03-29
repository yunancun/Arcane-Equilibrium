from __future__ import annotations

"""
Paper Trading Engine + API Tests / 纸上交易引擎与 API 测试

Tests cover:
  - Paper state store isolation
  - Order lifecycle state transitions (7 states, 8 edges)
  - Fill simulation (market + limit)
  - Balance/position projection
  - Session state machine
  - Safety guards (simulated label, no real Bybit interaction)
  - API route authorization and behavior
"""

import importlib
import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures / 测试夹具
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def paper_engine():
    """Create an isolated PaperTradingEngine with temp state file."""
    from app.paper_trading_engine import PaperStateStore, PaperTradingEngine

    tmpdir = tempfile.mkdtemp(prefix="openclaw_paper_test_")
    store = PaperStateStore(os.path.join(tmpdir, "paper_state.json"))
    return PaperTradingEngine(store)


@pytest.fixture
def active_engine(paper_engine):
    """Engine with an active session."""
    paper_engine.start_session(initial_balance=10000.0)
    return paper_engine


def build_api_client():
    """Build a TestClient with isolated state files."""
    tmpdir = tempfile.mkdtemp(prefix="openclaw_paper_api_test_")
    os.environ["OPENCLAW_STATE_FILE"] = os.path.join(tmpdir, "state.json")
    os.environ["OPENCLAW_PAPER_STATE_FILE"] = os.path.join(tmpdir, "paper_state.json")
    os.environ["OPENCLAW_API_TOKEN"] = "test-token"

    from app import main as main_module
    importlib.reload(main_module)

    # Also reload paper trading routes to pick up new env
    from app import paper_trading_routes
    importlib.reload(paper_trading_routes)
    importlib.reload(main_module)

    return TestClient(main_module.app)


def auth_headers():
    return {"Authorization": "Bearer test-token"}


# ═══════════════════════════════════════════════════════════════════════════════
# Engine Unit Tests / 引擎单元测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestPaperStateStore:
    """Paper state store isolation and basic operations."""

    def test_creates_default_state(self, paper_engine):
        state = paper_engine._read()
        assert state["meta"]["state_version"] == "paper_v1"
        assert state["session"]["session_state"] == "inactive"
        assert state["session"]["current_paper_balance_usdt"] == 10000.0

    def test_state_file_is_isolated(self, paper_engine):
        """Paper state file is separate from main state."""
        main_state_path = os.environ.get("OPENCLAW_STATE_FILE", "")
        paper_path = str(paper_engine.store.file_path)
        assert paper_path != main_state_path


class TestSessionLifecycle:
    """Session state machine: inactive → active → paused → active → completed."""

    def test_start_session(self, paper_engine):
        state = paper_engine.start_session(initial_balance=5000.0)
        assert state["session"]["session_state"] == "active"
        assert state["session"]["initial_paper_balance_usdt"] == 5000.0
        assert state["session"]["session_id"].startswith("psess:")

    def test_pause_session(self, active_engine):
        state = active_engine.pause_session()
        assert state["session"]["session_state"] == "paused"

    def test_resume_session(self, active_engine):
        active_engine.pause_session()
        state = active_engine.resume_session()
        assert state["session"]["session_state"] == "active"

    def test_stop_session(self, active_engine):
        state = active_engine.stop_session()
        assert state["session"]["session_state"] == "completed"
        assert state["session"]["stopped_ts_ms"] is not None

    def test_cannot_start_when_active(self, active_engine):
        with pytest.raises(ValueError, match="already active"):
            active_engine.start_session()

    def test_cannot_pause_when_inactive(self, paper_engine):
        with pytest.raises(ValueError, match="Cannot pause"):
            paper_engine.pause_session()

    def test_cannot_resume_when_active(self, active_engine):
        with pytest.raises(ValueError, match="Cannot resume"):
            active_engine.resume_session()

    def test_stop_cancels_working_orders(self, active_engine):
        active_engine.submit_order("BTCUSDT", "Buy", "limit", 0.1, price=50000.0)
        state = active_engine.stop_session()
        order = state["orders"][0]
        assert order["state"] == "paper_order_canceled"


class TestOrderLifecycle:
    """Order lifecycle: 7 states, 8 edges from K chapter skeleton."""

    def test_market_order_fills_immediately(self, active_engine):
        result = active_engine.submit_order(
            "BTCUSDT", "Buy", "market", 0.01,
            market_prices={"BTCUSDT": 60000.0},
        )
        assert result["order"]["state"] == "paper_order_filled"
        assert len(result["fills"]) == 1
        assert result["fills"][0]["qty"] == 0.01

    def test_limit_order_stays_working(self, active_engine):
        result = active_engine.submit_order(
            "BTCUSDT", "Buy", "limit", 0.01, price=50000.0,
        )
        assert result["order"]["state"] == "paper_order_working"
        assert len(result["fills"]) == 0

    def test_limit_buy_fills_when_price_drops(self, active_engine):
        active_engine.submit_order("BTCUSDT", "Buy", "limit", 0.01, price=50000.0)
        tick = active_engine.tick({"BTCUSDT": 49000.0})
        assert tick["orders_filled"] == 1

    def test_limit_sell_fills_when_price_rises(self, active_engine):
        # First buy to have a position
        active_engine.submit_order(
            "BTCUSDT", "Buy", "market", 0.01,
            market_prices={"BTCUSDT": 60000.0},
        )
        # Place limit sell
        active_engine.submit_order("BTCUSDT", "Sell", "limit", 0.01, price=65000.0)
        tick = active_engine.tick({"BTCUSDT": 66000.0})
        assert tick["orders_filled"] == 1

    def test_limit_order_no_fill_wrong_direction(self, active_engine):
        active_engine.submit_order("BTCUSDT", "Buy", "limit", 0.01, price=50000.0)
        tick = active_engine.tick({"BTCUSDT": 55000.0})
        assert tick["orders_filled"] == 0

    def test_cancel_working_order(self, active_engine):
        result = active_engine.submit_order("BTCUSDT", "Buy", "limit", 0.01, price=50000.0)
        order_id = result["order"]["order_id"]
        cancel_result = active_engine.cancel_order(order_id)
        assert cancel_result["success"] is True

    def test_cannot_cancel_filled_order(self, active_engine):
        result = active_engine.submit_order(
            "BTCUSDT", "Buy", "market", 0.01,
            market_prices={"BTCUSDT": 60000.0},
        )
        order_id = result["order"]["order_id"]
        cancel_result = active_engine.cancel_order(order_id)
        assert cancel_result["success"] is False

    def test_reject_insufficient_margin(self, paper_engine):
        """Reject order when balance < required_margin + fee"""
        paper_engine.start_session(initial_balance=0.0001)
        result = paper_engine.submit_order(
            "BTCUSDT", "Buy", "market", 100.0,
            market_prices={"BTCUSDT": 60000.0},
        )
        assert result["rejected_reason"] == "insufficient_margin"
        assert result["order"]["state"] == "paper_order_rejected"

    def test_cannot_submit_when_session_inactive(self, paper_engine):
        with pytest.raises(ValueError, match="Cannot submit"):
            paper_engine.submit_order("BTCUSDT", "Buy", "market", 0.01)

    def test_order_has_simulated_flag(self, active_engine):
        result = active_engine.submit_order(
            "BTCUSDT", "Buy", "market", 0.01,
            market_prices={"BTCUSDT": 60000.0},
        )
        assert result["order"]["is_simulated"] is True
        assert result["order"]["data_source"] == "paper_engine_v1"


class TestPositionProjection:
    """Position and balance projection after fills."""

    def test_buy_creates_long_position(self, active_engine):
        active_engine.submit_order(
            "BTCUSDT", "Buy", "market", 0.05,
            market_prices={"BTCUSDT": 60000.0},
        )
        positions = active_engine.get_positions()
        assert "BTCUSDT" in positions
        assert positions["BTCUSDT"]["side"] == "Buy"
        assert positions["BTCUSDT"]["qty"] == 0.05

    def test_sell_creates_short_position(self, active_engine):
        active_engine.submit_order(
            "BTCUSDT", "Sell", "market", 0.05,
            market_prices={"BTCUSDT": 60000.0},
        )
        positions = active_engine.get_positions()
        assert positions["BTCUSDT"]["side"] == "Sell"

    def test_same_direction_adds_to_position(self, active_engine):
        active_engine.submit_order(
            "BTCUSDT", "Buy", "market", 0.05,
            market_prices={"BTCUSDT": 60000.0},
        )
        active_engine.submit_order(
            "BTCUSDT", "Buy", "market", 0.03,
            market_prices={"BTCUSDT": 62000.0},
        )
        positions = active_engine.get_positions()
        assert positions["BTCUSDT"]["qty"] == 0.08

    def test_opposite_direction_closes_position(self, active_engine):
        active_engine.submit_order(
            "BTCUSDT", "Buy", "market", 0.05,
            market_prices={"BTCUSDT": 60000.0},
        )
        active_engine.submit_order(
            "BTCUSDT", "Sell", "market", 0.05,
            market_prices={"BTCUSDT": 62000.0},
        )
        positions = active_engine.get_positions()
        assert "BTCUSDT" not in positions

    def test_partial_close(self, active_engine):
        active_engine.submit_order(
            "BTCUSDT", "Buy", "market", 0.10,
            market_prices={"BTCUSDT": 60000.0},
        )
        active_engine.submit_order(
            "BTCUSDT", "Sell", "market", 0.04,
            market_prices={"BTCUSDT": 62000.0},
        )
        positions = active_engine.get_positions()
        assert positions["BTCUSDT"]["qty"] == pytest.approx(0.06)

    def test_unrealized_pnl_updates(self, active_engine):
        active_engine.submit_order(
            "BTCUSDT", "Buy", "market", 0.01,
            market_prices={"BTCUSDT": 60000.0},
        )
        active_engine.tick({"BTCUSDT": 65000.0})
        positions = active_engine.get_positions()
        # Approximate: (65000 - 60030) * 0.01 ≈ 49.7 (with slippage in entry)
        assert positions["BTCUSDT"]["unrealized_pnl"] > 0

    def test_balance_deducts_fees(self, active_engine):
        active_engine.submit_order(
            "BTCUSDT", "Buy", "market", 0.01,
            market_prices={"BTCUSDT": 60000.0},
        )
        status = active_engine.get_session_status()
        # Balance should be less than initial due to fees
        assert status["session"]["current_paper_balance_usdt"] < 10000.0


class TestPnLComputation:
    """PnL tracking and computation."""

    def test_pnl_tracks_fees(self, active_engine):
        active_engine.submit_order(
            "BTCUSDT", "Buy", "market", 0.01,
            market_prices={"BTCUSDT": 60000.0},
        )
        pnl = active_engine.get_pnl()
        assert pnl["total_fees_paid"] > 0

    def test_pnl_net_includes_fees(self, active_engine):
        active_engine.submit_order(
            "BTCUSDT", "Buy", "market", 0.01,
            market_prices={"BTCUSDT": 60000.0},
        )
        pnl = active_engine.get_pnl()
        # Just fees, no PnL yet, so net should be negative
        assert pnl["net_paper_pnl"] < 0

    def test_profitable_round_trip(self, active_engine):
        active_engine.submit_order(
            "BTCUSDT", "Buy", "market", 0.01,
            market_prices={"BTCUSDT": 60000.0},
        )
        active_engine.submit_order(
            "BTCUSDT", "Sell", "market", 0.01,
            market_prices={"BTCUSDT": 65000.0},
        )
        pnl = active_engine.get_pnl()
        # Rough: (65000*0.9995 - 60000*1.0005) * 0.01 - fees ≈ positive
        assert pnl["realized_pnl"] > 0


class TestAuditTrail:
    """Audit trail tracking."""

    def test_session_start_logged(self, paper_engine):
        paper_engine.start_session()
        trail = paper_engine.get_audit_trail()
        assert any(e["action"] == "session_start" for e in trail)

    def test_order_submit_logged(self, active_engine):
        active_engine.submit_order(
            "BTCUSDT", "Buy", "market", 0.01,
            market_prices={"BTCUSDT": 60000.0},
        )
        trail = active_engine.get_audit_trail()
        assert any(e["action"] == "order_submitted" for e in trail)


class TestDataExport:
    """Session data export."""

    def test_export_has_required_fields(self, active_engine):
        active_engine.submit_order(
            "BTCUSDT", "Buy", "market", 0.01,
            market_prices={"BTCUSDT": 60000.0},
        )
        export = active_engine.export_session()
        assert export["is_simulated"] is True
        assert export["data_category"] == "paper_simulated"
        assert "session" in export
        assert "orders" in export
        assert "positions" in export
        assert "fills" in export
        assert "pnl" in export


# ═══════════════════════════════════════════════════════════════════════════════
# API Route Tests / API 路由测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestPaperTradingAPI:
    """API route integration tests."""

    def test_session_start_via_api(self):
        client = build_api_client()
        r = client.post(
            "/api/v1/paper/session/start",
            headers=auth_headers(),
            json={"initial_balance": 5000.0},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["is_simulated"] is True
        assert data["data"]["session"]["session_state"] == "active"

    def test_session_status_via_api(self):
        client = build_api_client()
        client.post("/api/v1/paper/session/start", headers=auth_headers(), json={})
        r = client.get("/api/v1/paper/session/status", headers=auth_headers())
        assert r.status_code == 200
        assert r.json()["data"]["is_simulated"] is True

    def test_order_submit_via_api(self):
        client = build_api_client()
        client.post("/api/v1/paper/session/start", headers=auth_headers(), json={})
        r = client.post(
            "/api/v1/paper/order/submit",
            headers=auth_headers(),
            json={
                "symbol": "BTCUSDT",
                "side": "Buy",
                "order_type": "limit",
                "qty": 0.01,
                "price": 50000.0,
            },
        )
        assert r.status_code == 200

    def test_get_orders_via_api(self):
        client = build_api_client()
        client.post("/api/v1/paper/session/start", headers=auth_headers(), json={})
        r = client.get("/api/v1/paper/orders", headers=auth_headers())
        assert r.status_code == 200
        assert "orders" in r.json()["data"]

    def test_get_positions_via_api(self):
        client = build_api_client()
        client.post("/api/v1/paper/session/start", headers=auth_headers(), json={})
        r = client.get("/api/v1/paper/positions", headers=auth_headers())
        assert r.status_code == 200

    def test_get_pnl_via_api(self):
        client = build_api_client()
        client.post("/api/v1/paper/session/start", headers=auth_headers(), json={})
        r = client.get("/api/v1/paper/pnl", headers=auth_headers())
        assert r.status_code == 200

    def test_tick_via_api(self):
        client = build_api_client()
        client.post("/api/v1/paper/session/start", headers=auth_headers(), json={})
        r = client.post(
            "/api/v1/paper/tick",
            headers=auth_headers(),
            json={"market_prices": {"BTCUSDT": 60000.0}},
        )
        assert r.status_code == 200

    def test_e1_observation_fires_on_tick_close(self, active_engine):
        """E1 fix (Session 12): observations must be written for positions closed
        via engine.tick() (risk_auto_close, time stop) not just via submit_order().
        E1 修复：通过 tick 路径平仓（风控自动平仓/时间止损）也必须触发观察记录。"""
        import types, sys, os

        # Add program_code to path so local_model_tools is importable
        _ctrl = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _prog = os.path.dirname(os.path.dirname(os.path.dirname(_ctrl)))
        for p in (_ctrl, _prog):
            if p not in sys.path:
                sys.path.insert(0, p)

        from app.pipeline_bridge import PipelineBridge

        # Minimal mocks for dependencies not used by on_tick_result
        km = types.SimpleNamespace(on_price_event=lambda e: None, get_tracked_symbols=lambda: [])
        ie = types.SimpleNamespace(get_indicators=lambda s, tf: None)
        orch = types.SimpleNamespace(
            dispatch_tick=lambda s, p, t: None,
            collect_pending_intents=lambda: [],
            on_signal=lambda sig: None,
        )

        bridge = PipelineBridge(km, ie, None, orch, active_engine,
                                auto_submit_intents=False)
        bridge.activate()

        observations = []
        bridge.set_observation_writer(lambda **kw: observations.append(kw))

        # Simulate a tracked position (as if strategy's Buy market order already opened it)
        bridge._open_positions["test_strategy:BTCUSDT"] = {
            "symbol": "BTCUSDT",
            "strategy_name": "test_strategy",
            "side": "long",
            "entry_price": 60000.0,
            "qty": 0.001,
            "entry_ts_ms": 0,
            "regime": "trending",
        }

        # Simulate tick_result from engine.tick() with a risk_auto_close Sell fill
        tick_result = {
            "orders_filled": 1,
            "fills": [{
                "fill_id": "test_fill_001",
                "symbol": "BTCUSDT",
                "side": "Sell",
                "qty": 0.001,
                "price": 60100.0,
                "fee": 0.033,
                "notional": 60.1,
                "ts_ms": 9999999999,
                "is_simulated": True,
            }],
        }

        bridge.on_tick_result(tick_result)

        assert len(observations) == 1, (
            f"Expected 1 E1 observation from tick close, got {len(observations)}"
        )
        obs = observations[0]
        assert obs["symbol"] == "BTCUSDT"
        assert obs["strategy_name"] == "test_strategy"
        assert obs["regime"] == "trending"
        # close_pnl = (60100-60000)*0.001 - 0.033 = 0.1 - 0.033 = 0.067
        assert abs(obs["close_pnl"] - 0.067) < 0.001, f"Unexpected pnl: {obs['close_pnl']}"
        assert "test_strategy:BTCUSDT" not in bridge._open_positions

    def test_e1_observation_not_fired_for_open_fills(self, active_engine):
        """on_tick_result must NOT fire E1 for same-side (opening) fills."""
        import types, sys, os

        _ctrl = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _prog = os.path.dirname(os.path.dirname(os.path.dirname(_ctrl)))
        for p in (_ctrl, _prog):
            if p not in sys.path:
                sys.path.insert(0, p)

        from app.pipeline_bridge import PipelineBridge

        km = types.SimpleNamespace(on_price_event=lambda e: None, get_tracked_symbols=lambda: [])
        ie = types.SimpleNamespace(get_indicators=lambda s, tf: None)
        orch = types.SimpleNamespace(
            dispatch_tick=lambda s, p, t: None,
            collect_pending_intents=lambda: [],
            on_signal=lambda sig: None,
        )
        bridge = PipelineBridge(km, ie, None, orch, active_engine,
                                auto_submit_intents=False)
        bridge.activate()

        observations = []
        bridge.set_observation_writer(lambda **kw: observations.append(kw))

        bridge._open_positions["test_strategy:BTCUSDT"] = {
            "symbol": "BTCUSDT", "strategy_name": "test_strategy",
            "side": "long", "entry_price": 60000.0, "qty": 0.001,
            "entry_ts_ms": 0, "regime": "trending",
        }

        # Buy fill = opening direction for a long → must NOT trigger E1
        tick_result = {
            "orders_filled": 1,
            "fills": [{"symbol": "BTCUSDT", "side": "Buy", "qty": 0.001,
                        "price": 60100.0, "fee": 0.001, "notional": 60.1}],
        }
        bridge.on_tick_result(tick_result)
        assert len(observations) == 0, "E1 must not fire for opening fills"

    def test_fill_fragmentation_dust_check(self, active_engine):
        """Fill fragmentation fix (Session 12): limit order completes in ≤10 fills,
        not 25-30. Remaining qty < 1% of original gets filled at once.
        碎片化修复：限价单应在 ≤10 次成交内完成，而非 25-30 次。"""
        import random
        rng = random.Random(42)
        from app.paper_trading_engine import compute_partial_fill_qty
        order = {"qty": 0.01, "remaining_qty": 0.01, "price": 60000.0, "side": "Buy"}
        fills = 0
        while order["remaining_qty"] > 0:
            fill = compute_partial_fill_qty(order, 59500.0, rng=rng)
            order["remaining_qty"] -= fill
            fills += 1
            if fills > 50:
                break  # prevent infinite loop in case fix is broken
        assert fills <= 10, f"Expected ≤10 fills, got {fills} (fragmentation bug still present)"

    def test_export_via_api(self):
        client = build_api_client()
        client.post("/api/v1/paper/session/start", headers=auth_headers(), json={})
        r = client.get("/api/v1/paper/export", headers=auth_headers())
        assert r.status_code == 200
        assert r.json()["data"]["is_simulated"] is True

    def test_auth_required(self):
        client = build_api_client()
        r = client.get("/api/v1/paper/session/status")
        assert r.status_code in (401, 403, 422)

    def test_session_lifecycle_via_api(self):
        client = build_api_client()
        # Start
        r = client.post("/api/v1/paper/session/start", headers=auth_headers(), json={})
        assert r.status_code == 200
        # Pause
        r = client.post("/api/v1/paper/session/pause", headers=auth_headers())
        assert r.status_code == 200
        # Resume
        r = client.post("/api/v1/paper/session/resume", headers=auth_headers())
        assert r.status_code == 200
        # Stop
        r = client.post("/api/v1/paper/session/stop", headers=auth_headers())
        assert r.status_code == 200
        assert r.json()["data"]["session"]["session_state"] == "completed"
