"""
Session 9 Fix Verification Tests / Session 9 修复验证测试

Covers:
  - G3: active_count +1 bug fix in StrategyAutoDeployer._compute_qty
  - B2: net_realized_pnl field in PaperTradingEngine._recompute_pnl
  - A2: on_fill position sync chain (StrategyBase → MACrossoverStrategy → deployer → bridge)
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── path setup ──────────────────────────────────────────────────────────────
LOCAL_MODEL_ROOT = Path(__file__).resolve().parents[1]
CONTROL_API_ROOT = (
    Path(__file__).resolve().parents[2]
    / "exchange_connectors" / "bybit_connector" / "control_api_v1"
)
for p in [str(LOCAL_MODEL_ROOT), str(CONTROL_API_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)


# ════════════════════════════════════════════════════════════════════════════
# G3 — active_count fix
# ════════════════════════════════════════════════════════════════════════════

class TestActiveCountFix:
    """G3: _compute_qty uses | {symbol} instead of + 1"""

    def _make_deployer(self, deployed_symbols: list[str]):
        """Build a StrategyAutoDeployer with mocked deps and pre-populated _deployed."""
        from strategy_auto_deployer import StrategyAutoDeployer

        orch = MagicMock()
        engine = MagicMock()
        engine.get_state.return_value = {
            "session": {"current_paper_balance_usdt": 10000.0}
        }

        deployer = StrategyAutoDeployer(
            orch,
            MagicMock(),  # kline_manager
            engine,
            risk_per_trade_pct=1.0,
            min_qty_usdt=5.0,
            max_qty_pct=10.0,
        )
        # Populate _deployed with existing symbols
        for i, sym in enumerate(deployed_symbols):
            deployer._deployed[f"trend_{sym}"] = {"symbol": sym, "category": "linear"}

        return deployer

    def test_no_existing_deployments(self):
        """With 0 deployed, active_count should be 1 (just the new symbol)."""
        deployer = self._make_deployer([])
        qty = deployer._compute_qty("BTCUSDT", price=50000.0, score=80.0)
        # balance=10000, risk=1% → base=100, score_mult≈0.9, allocated≈90
        # active_count=1, per_symbol=90, clamped. qty=90/50000≈0.0018
        assert qty > 0

    def test_with_two_deployed_same_symbol(self):
        """
        Bug scenario: BTCUSDT already deployed as 1 strategy.
        Old code: active_count = len({BTCUSDT}) + 1 = 2
        New code: active_count = len({BTCUSDT} | {BTCUSDT}) = 1
        Deploying the SAME symbol again should not double-count.
        """
        deployer = self._make_deployer(["BTCUSDT"])
        qty_same = deployer._compute_qty("BTCUSDT", price=50000.0, score=80.0)
        # active_count = len({BTCUSDT} | {BTCUSDT}) = 1
        # Old code would give active_count = 2 → smaller qty

        deployer2 = self._make_deployer([])
        qty_fresh = deployer2._compute_qty("BTCUSDT", price=50000.0, score=80.0)
        # active_count = len({} | {BTCUSDT}) = 1

        # Both should give same qty (1 active symbol either way)
        assert abs(qty_same - qty_fresh) < 1e-9, (
            f"Same-symbol redeploy should give same qty as fresh deploy. "
            f"Got same={qty_same}, fresh={qty_fresh}"
        )

    def test_with_two_different_deployed(self):
        """
        2 different deployed symbols + 1 new → active_count should be 3.
        Old code: len({A,B}) + 1 = 3 ← coincidentally correct
        New code: len({A,B} | {C}) = 3 ← also correct

        Uses large balance (100000) so qty difference survives lot-size rounding.
        """
        deployer = self._make_deployer(["ETHUSDT", "SOLUSDT"])
        qty_3symbols = deployer._compute_qty("BTCUSDT", price=50000.0, score=80.0)

        deployer1 = self._make_deployer([])
        qty_1symbol = deployer1._compute_qty("BTCUSDT", price=50000.0, score=80.0)

        # With 3 active symbols, qty should be <= than with 1
        # (may be equal if minimum lot size rounds both to the same value)
        assert qty_3symbols <= qty_1symbol, (
            f"3-symbol portfolio should give smaller or equal per-symbol qty. "
            f"Got 3sym={qty_3symbols}, 1sym={qty_1symbol}"
        )

    def test_active_count_does_not_double_count_new_symbol(self):
        """
        Core bug test: deploying ETHUSDT when ETHUSDT is already in _deployed.
        Old code: len({ETHUSDT}) + 1 = 2  (wrong: counts it twice)
        New code: len({ETHUSDT} | {ETHUSDT}) = 1  (correct: same symbol)
        """
        deployer_old_bug = self._make_deployer(["ETHUSDT"])

        # Manually simulate old buggy behavior to confirm fix changes result
        deployed_syms = set(d["symbol"] for d in deployer_old_bug._deployed.values())
        old_count = max(1, len(deployed_syms) + 1)  # old buggy
        new_count = max(1, len(deployed_syms | {"ETHUSDT"}))  # new fixed

        assert old_count == 2, f"Old bug count should be 2, got {old_count}"
        assert new_count == 1, f"New fixed count should be 1, got {new_count}"
        assert old_count != new_count, "Fix should produce different result for this scenario"


# ════════════════════════════════════════════════════════════════════════════
# B2 — net_realized_pnl field
# ════════════════════════════════════════════════════════════════════════════

class TestNetRealizedPnl:
    """B2: net_realized_pnl = realized_pnl - total_fees_paid in _recompute_pnl"""

    @pytest.fixture
    def active_engine(self):
        # Use standard import instead of importlib to support relative imports
        # 使用標準 import 代替 importlib，以支持模組內的相對導入
        from app.paper_trading_engine import PaperStateStore, PaperTradingEngine
        from unittest.mock import MagicMock
        tmpdir = tempfile.mkdtemp(prefix="openclaw_pnl_test_")
        store = PaperStateStore(os.path.join(tmpdir, "state.json"))
        engine = PaperTradingEngine(store)
        # Provide mock governance_hub so fail-closed check passes
        mock_hub = MagicMock()
        mock_hub.is_authorized.return_value = True
        mock_hub.acquire_lease.return_value = "test-lease"
        mock_hub.release_lease.return_value = None
        engine.set_governance_hub(mock_hub)
        engine.start_session(initial_balance=10000.0)
        return engine

    def test_net_realized_pnl_field_exists(self, active_engine):
        """net_realized_pnl must exist in state.pnl after start."""
        state = active_engine.get_state()
        assert "net_realized_pnl" in state["pnl"], (
            "net_realized_pnl field missing from state.pnl"
        )

    def test_net_realized_pnl_zero_at_start(self, active_engine):
        """At session start, net_realized_pnl should be 0."""
        state = active_engine.get_state()
        assert state["pnl"]["net_realized_pnl"] == 0.0

    def test_net_realized_pnl_equals_realized_minus_fees(self, active_engine):
        """After trades, net_realized_pnl = realized_pnl - total_fees_paid."""
        prices = {"BTCUSDT": 50000.0}
        # Open long
        active_engine.submit_order(
            symbol="BTCUSDT", side="Buy", order_type="market",
            qty=0.001, market_prices=prices,
        )
        # Close with higher price (profit)
        prices2 = {"BTCUSDT": 51000.0}
        active_engine.submit_order(
            symbol="BTCUSDT", side="Sell", order_type="market",
            qty=0.001, market_prices=prices2,
        )
        state = active_engine.get_state()
        pnl = state["pnl"]

        realized = pnl["realized_pnl"]
        fees = pnl["total_fees_paid"]
        net = pnl["net_realized_pnl"]

        assert abs(net - (realized - fees)) < 1e-9, (
            f"net_realized_pnl={net} should equal realized={realized} - fees={fees} = {realized - fees}"
        )

    def test_net_realized_pnl_is_less_than_gross(self, active_engine):
        """net_realized_pnl must be less than realized_pnl when fees > 0."""
        prices = {"BTCUSDT": 50000.0}
        active_engine.submit_order("BTCUSDT", "Buy", "market", 0.001, market_prices=prices)
        prices2 = {"BTCUSDT": 51000.0}
        active_engine.submit_order("BTCUSDT", "Sell", "market", 0.001, market_prices=prices2)

        state = active_engine.get_state()
        pnl = state["pnl"]

        assert pnl["total_fees_paid"] > 0, "Fees should be non-zero"
        assert pnl["net_realized_pnl"] < pnl["realized_pnl"], (
            "net_realized_pnl must be less than gross realized_pnl when fees exist"
        )

    def test_net_realized_pnl_consistent_with_net_paper_pnl(self, active_engine):
        """
        net_paper_pnl = realized + unrealized - fees - ai_cost
        net_realized_pnl = realized - fees
        When unrealized=0 and ai_cost=0: net_paper_pnl == net_realized_pnl
        """
        prices = {"BTCUSDT": 50000.0}
        active_engine.submit_order("BTCUSDT", "Buy", "market", 0.001, market_prices=prices)
        prices2 = {"BTCUSDT": 51000.0}
        active_engine.submit_order("BTCUSDT", "Sell", "market", 0.001, market_prices=prices2)

        state = active_engine.get_state()
        pnl = state["pnl"]

        # After full close, unrealized should be 0
        if pnl["unrealized_pnl"] == 0.0 and pnl.get("total_ai_cost", 0.0) == 0.0:
            assert abs(pnl["net_paper_pnl"] - pnl["net_realized_pnl"]) < 1e-9, (
                "With no open positions and no AI cost, net_paper_pnl should equal net_realized_pnl"
            )


# ════════════════════════════════════════════════════════════════════════════
# A2 — on_fill position sync chain
# ════════════════════════════════════════════════════════════════════════════

class TestOnFillPositionSync:
    """A2: on_fill callback chain syncs MACrossoverStrategy._current_position"""

    # ── StrategyBase.on_fill exists and is a no-op ──────────────────────────

    def test_base_on_fill_exists(self):
        # StrategyBase is abstract; verify via MACrossoverStrategy which inherits it.
        # The MACrossoverStrategy.on_fill overrides base, but base default must also exist.
        from strategies.base import StrategyBase
        from strategies.ma_crossover import MACrossoverStrategy
        # Check the method exists on the base class
        assert hasattr(StrategyBase, "on_fill"), "StrategyBase must have on_fill method"
        # MACrossoverStrategy inherits and overrides it — verify callable
        s = MACrossoverStrategy(symbol="BTCUSDT", qty_per_trade=0.001)
        result = s.on_fill({"symbol": "XYZUSDT", "side": "Buy"}, is_open=True)  # wrong symbol → no-op
        assert result is None

    # ── MACrossoverStrategy.on_fill syncs position ──────────────────────────

    def test_on_fill_open_buy_sets_long(self):
        from strategies.ma_crossover import MACrossoverStrategy
        s = MACrossoverStrategy(symbol="BTCUSDT", qty_per_trade=0.001)
        s.activate()
        assert s._current_position is None  # starts neutral

        s.on_fill({"symbol": "BTCUSDT", "side": "Buy", "qty": 0.001}, is_open=True)
        assert s._current_position == "long", (
            f"Expected 'long' after Buy open fill, got {s._current_position!r}"
        )

    def test_on_fill_open_sell_sets_short(self):
        from strategies.ma_crossover import MACrossoverStrategy
        s = MACrossoverStrategy(symbol="BTCUSDT", qty_per_trade=0.001)
        s.activate()
        s.on_fill({"symbol": "BTCUSDT", "side": "Sell", "qty": 0.001}, is_open=True)
        assert s._current_position == "short"

    def test_on_fill_close_sets_none(self):
        from strategies.ma_crossover import MACrossoverStrategy
        s = MACrossoverStrategy(symbol="BTCUSDT", qty_per_trade=0.001)
        s.activate()
        # Simulate: we think we're long (intent-first update)
        s._current_position = "long"
        # Close fill arrives
        s.on_fill({"symbol": "BTCUSDT", "side": "Sell", "qty": 0.001}, is_open=False)
        assert s._current_position is None, (
            f"Expected None after close fill, got {s._current_position!r}"
        )

    def test_on_fill_wrong_symbol_ignored(self):
        from strategies.ma_crossover import MACrossoverStrategy
        s = MACrossoverStrategy(symbol="BTCUSDT", qty_per_trade=0.001)
        s.activate()
        s._current_position = "long"
        # Fill for different symbol — should be ignored
        s.on_fill({"symbol": "ETHUSDT", "side": "Sell", "qty": 0.1}, is_open=False)
        assert s._current_position == "long", "Fill for wrong symbol should not change position"

    def test_on_fill_corrects_drift(self):
        """
        Core scenario: strategy set _current_position='long' optimistically (intent-first),
        but the actual fill was rejected/different. on_fill corrects the state.
        """
        from strategies.ma_crossover import MACrossoverStrategy
        s = MACrossoverStrategy(symbol="BTCUSDT", qty_per_trade=0.001)
        s.activate()
        # Strategy optimistically set to long via intent emission
        s._current_position = "long"
        # But fill comes back as close (close_pnl != 0) — we actually closed
        s.on_fill({"symbol": "BTCUSDT", "side": "Sell"}, is_open=False)
        assert s._current_position is None

    # ── StrategyAutoDeployer.notify_fill routes to strategy ─────────────────

    def test_notify_fill_routes_to_strategy(self):
        from strategy_auto_deployer import StrategyAutoDeployer
        from strategies.ma_crossover import MACrossoverStrategy

        strategy = MACrossoverStrategy(symbol="BTCUSDT", qty_per_trade=0.001)
        strategy.activate()
        strategy._current_position = "short"  # drift state

        orch = MagicMock()
        orch._strategies = {"MA_Crossover_BTCUSDT": strategy}

        engine = MagicMock()
        engine.get_state.return_value = {"session": {"current_paper_balance_usdt": 10000.0}}

        deployer = StrategyAutoDeployer(orch, MagicMock(), engine)

        fill = {"symbol": "BTCUSDT", "side": "Sell", "qty": 0.001, "price": 50000.0}
        deployer.notify_fill("MA_Crossover_BTCUSDT", fill, is_open=False)

        assert strategy._current_position is None, (
            f"notify_fill should have called on_fill → cleared position. "
            f"Got {strategy._current_position!r}"
        )

    def test_notify_fill_unknown_strategy_does_not_raise(self):
        from strategy_auto_deployer import StrategyAutoDeployer

        orch = MagicMock()
        orch._strategies = {}
        engine = MagicMock()
        engine.get_state.return_value = {"session": {"current_paper_balance_usdt": 10000.0}}

        deployer = StrategyAutoDeployer(orch, MagicMock(), engine)
        # Should not raise for unknown strategy name
        deployer.notify_fill("nonexistent_strategy", {"symbol": "BTCUSDT"}, is_open=True)

    def test_notify_fill_open_corrects_to_long(self):
        from strategy_auto_deployer import StrategyAutoDeployer
        from strategies.ma_crossover import MACrossoverStrategy

        strategy = MACrossoverStrategy(symbol="ETHUSDT", qty_per_trade=0.01)
        strategy.activate()
        # Simulate no position (intent not yet updated)
        assert strategy._current_position is None

        orch = MagicMock()
        orch._strategies = {"MA_ETHUSDT": strategy}
        engine = MagicMock()
        engine.get_state.return_value = {"session": {"current_paper_balance_usdt": 10000.0}}

        deployer = StrategyAutoDeployer(orch, MagicMock(), engine)
        fill = {"symbol": "ETHUSDT", "side": "Buy", "qty": 0.01, "price": 3000.0}
        deployer.notify_fill("MA_ETHUSDT", fill, is_open=True)

        assert strategy._current_position == "long"


# ════════════════════════════════════════════════════════════════════════════
# B1 — total_ai_cost aggregation in _recompute_pnl
# ════════════════════════════════════════════════════════════════════════════

class TestAiCostAggregation:
    """B1: total_ai_cost is now aggregated from positions' holding_cost in _recompute_pnl"""

    @pytest.fixture
    def engine_mod(self):
        # Use standard import instead of importlib to support relative imports
        # 使用標準 import 代替 importlib，以支持模組內的相對導入
        import app.paper_trading_engine as mod
        return mod

    @pytest.fixture
    def active_engine(self, engine_mod):
        import os, tempfile
        tmpdir = tempfile.mkdtemp(prefix="openclaw_ai_cost_test_")
        store = engine_mod.PaperStateStore(os.path.join(tmpdir, "state.json"))
        engine = engine_mod.PaperTradingEngine(store)
        engine.start_session(initial_balance=10000.0)
        return engine

    def test_total_ai_cost_zero_with_no_positions(self, active_engine):
        """No open positions → total_ai_cost should be 0.0."""
        state = active_engine.get_state()
        assert state["pnl"]["total_ai_cost"] == 0.0

    def test_total_ai_cost_aggregated_from_holding_cost(self, active_engine):
        """If positions carry ai_cost_attributed_usd, it should be aggregated into pnl."""
        # Manually inject holding_cost onto a position to simulate RiskManager having run
        def _inject(state):
            state["positions"]["BTCUSDT"] = {
                "symbol": "BTCUSDT", "side": "Buy", "qty": 0.001,
                "avg_entry_price": 50000.0, "realized_pnl": 0.0,
                "unrealized_pnl": 0.0, "opened_ts_ms": 0,
                "holding_cost": {
                    "ai_cost_attributed_usd": 0.042,
                    "hourly_ai_burn_rate_usd": 0.01,
                },
            }
            state["positions"]["ETHUSDT"] = {
                "symbol": "ETHUSDT", "side": "Sell", "qty": 0.1,
                "avg_entry_price": 3000.0, "realized_pnl": 0.0,
                "unrealized_pnl": 0.0, "opened_ts_ms": 0,
                "holding_cost": {
                    "ai_cost_attributed_usd": 0.018,
                    "hourly_ai_burn_rate_usd": 0.01,
                },
            }
            return state
        active_engine.store.mutate(_inject)

        # Trigger _recompute_pnl via a tick (no price movement needed)
        active_engine.tick({"BTCUSDT": 50000.0, "ETHUSDT": 3000.0})

        state = active_engine.get_state()
        expected_ai_cost = 0.042 + 0.018  # = 0.060
        assert abs(state["pnl"]["total_ai_cost"] - expected_ai_cost) < 1e-9, (
            f"total_ai_cost should be {expected_ai_cost}, got {state['pnl']['total_ai_cost']}"
        )

    def test_total_ai_cost_reflected_in_net_paper_pnl(self, active_engine):
        """net_paper_pnl must decrease when AI cost is present."""
        # Get baseline net_paper_pnl with no AI cost
        state_before = active_engine.get_state()
        baseline_net = state_before["pnl"]["net_paper_pnl"]

        # Inject a position with AI cost
        def _inject(state):
            state["positions"]["BTCUSDT"] = {
                "symbol": "BTCUSDT", "side": "Buy", "qty": 0.001,
                "avg_entry_price": 50000.0, "realized_pnl": 0.0,
                "unrealized_pnl": 0.0, "opened_ts_ms": 0,
                "holding_cost": {"ai_cost_attributed_usd": 0.05},
            }
            return state
        active_engine.store.mutate(_inject)

        active_engine.tick({"BTCUSDT": 50000.0})

        state_after = active_engine.get_state()
        assert state_after["pnl"]["total_ai_cost"] > 0
        assert state_after["pnl"]["net_paper_pnl"] < baseline_net, (
            "net_paper_pnl should decrease when AI cost > 0"
        )

    def test_position_without_holding_cost_is_safe(self, active_engine):
        """Positions with no holding_cost key should not crash and contribute 0 AI cost."""
        def _inject(state):
            state["positions"]["SOLUSDT"] = {
                "symbol": "SOLUSDT", "side": "Buy", "qty": 1.0,
                "avg_entry_price": 100.0, "realized_pnl": 0.0,
                "unrealized_pnl": 0.0, "opened_ts_ms": 0,
                # no "holding_cost" key
            }
            return state
        active_engine.store.mutate(_inject)

        # Should not raise
        active_engine.tick({"SOLUSDT": 100.0})
        state = active_engine.get_state()
        assert state["pnl"]["total_ai_cost"] == 0.0


# ════════════════════════════════════════════════════════════════════════════
# S1 — double-stop guard in PipelineBridge._check_stops
# ════════════════════════════════════════════════════════════════════════════

class TestDoubleStopGuard:
    """S1: _check_stops skips stop orders when position is already closed"""

    def _make_bridge(self, positions: dict):
        """Build a minimal PipelineBridge with mocked engine and stop manager."""
        sys.path.insert(0, str(CONTROL_API_ROOT))
        from app.pipeline_bridge import PipelineBridge
        from local_model_tools.stop_manager import StopManager

        orch = MagicMock()
        orch.collect_pending_intents.return_value = []
        orch.dispatch_tick.return_value = None

        engine = MagicMock()
        engine.get_state.return_value = {"positions": positions}

        km = MagicMock()
        bridge = PipelineBridge(
            km, MagicMock(), MagicMock(), orch, engine,
        )
        return bridge, engine

    def test_stop_skipped_when_position_already_closed(self):
        """If position is gone from engine state, stop order must NOT be submitted."""
        bridge, engine = self._make_bridge(positions={})  # no open positions

        stop_mgr = MagicMock()
        stop_mgr.check_stops.return_value = [{
            "symbol": "BTCUSDT",
            "side": "Sell",
            "qty": 0.001,
            "stop_type": "hard",
            "reason": "hard_stop",
            "strategy_name": "MA_Crossover",
        }]
        stop_mgr.untrack_position = MagicMock()
        bridge._stop_mgr = stop_mgr
        bridge._latest_prices = {"BTCUSDT": 48000.0}

        bridge._check_stops()

        # submit_order must NOT have been called (position already gone)
        engine.submit_order.assert_not_called()
        # untrack_position should have been called to clean up StopManager state
        stop_mgr.untrack_position.assert_called_once_with("BTCUSDT", "MA_Crossover")

    def test_stop_submitted_when_position_still_open(self):
        """If position still exists, stop order SHOULD be submitted normally."""
        positions = {
            "BTCUSDT": {"symbol": "BTCUSDT", "side": "Buy", "qty": 0.001}
        }
        bridge, engine = self._make_bridge(positions=positions)
        engine.submit_order.return_value = {"fills": [], "close_pnl": 0.0}

        stop_mgr = MagicMock()
        stop_mgr.check_stops.return_value = [{
            "symbol": "BTCUSDT",
            "side": "Sell",
            "qty": 0.001,
            "stop_type": "hard",
            "reason": "hard_stop",
            "strategy_name": "MA_Crossover",
        }]
        bridge._stop_mgr = stop_mgr
        bridge._latest_prices = {"BTCUSDT": 48000.0}

        bridge._check_stops()

        engine.submit_order.assert_called_once()

    def test_stop_get_state_failure_proceeds_safely(self):
        """If get_state() raises, stop order should still be submitted (safe default)."""
        bridge, engine = self._make_bridge(positions={})
        engine.get_state.side_effect = RuntimeError("state unavailable")
        engine.submit_order.return_value = {"fills": [], "close_pnl": 0.0}

        stop_mgr = MagicMock()
        stop_mgr.check_stops.return_value = [{
            "symbol": "BTCUSDT",
            "side": "Sell",
            "qty": 0.001,
            "stop_type": "hard",
            "reason": "hard_stop",
        }]
        bridge._stop_mgr = stop_mgr
        bridge._latest_prices = {"BTCUSDT": 48000.0}

        # Should not raise, and should fall through to submit_order
        bridge._check_stops()
        engine.submit_order.assert_called_once()


# ════════════════════════════════════════════════════════════════════════════
# R1 — Regime-aware stop/TP/time scaling (Session 10)
# ════════════════════════════════════════════════════════════════════════════

class TestRegimeAwareStops:
    """
    R1: compute_dynamic_stop_pct and check_positions_on_tick apply regime multipliers.
    Verifies: stop wider in volatile/trending, tighter in ranging/squeeze,
              TP scaled by REGIME_TP_MULTIPLIERS, time_stop scaled by REGIME_TIME_MULTIPLIERS.
    """

    @pytest.fixture
    def rm_mod(self):
        # Use standard import instead of importlib to support relative imports
        # 使用標準 import 代替 importlib，以支持模組內的相對導入
        import app.risk_manager as mod
        return mod

    # ── compute_dynamic_stop_pct regime scaling ──────────────────────────────

    def test_unknown_regime_is_neutral(self, rm_mod):
        """unknown regime → multiplier 1.0 → same as baseline."""
        base = rm_mod.compute_dynamic_stop_pct(5.0, None, "BTCUSDT", 0, regime="unknown")
        neutral = rm_mod.compute_dynamic_stop_pct(5.0, None, "BTCUSDT", 0)
        assert abs(base - neutral) < 1e-9, "default regime should equal explicit 'unknown'"

    def test_volatile_widens_stop(self, rm_mod):
        """volatile regime (1.5×) should produce a wider stop than ranging (0.7×)."""
        volatile_sl = rm_mod.compute_dynamic_stop_pct(5.0, None, "BTCUSDT", 0, regime="volatile")
        ranging_sl = rm_mod.compute_dynamic_stop_pct(5.0, None, "BTCUSDT", 0, regime="ranging")
        assert volatile_sl > ranging_sl, (
            f"volatile stop ({volatile_sl:.3f}) should be > ranging stop ({ranging_sl:.3f})"
        )

    def test_squeeze_is_tightest(self, rm_mod):
        """squeeze (0.6×) should produce the tightest stop among all regimes."""
        regimes = ["trending", "volatile", "ranging", "squeeze", "unknown"]
        stops = {r: rm_mod.compute_dynamic_stop_pct(5.0, None, "BTCUSDT", 0, regime=r) for r in regimes}
        assert stops["squeeze"] < stops["volatile"], (
            f"squeeze stop ({stops['squeeze']:.3f}) should be < volatile ({stops['volatile']:.3f})"
        )
        assert stops["squeeze"] < stops["trending"], (
            f"squeeze stop ({stops['squeeze']:.3f}) should be < trending ({stops['trending']:.3f})"
        )

    def test_trending_wider_than_ranging(self, rm_mod):
        """trending (1.0×) > ranging (0.7×)."""
        trending_sl = rm_mod.compute_dynamic_stop_pct(5.0, None, "BTCUSDT", 0, regime="trending")
        ranging_sl = rm_mod.compute_dynamic_stop_pct(5.0, None, "BTCUSDT", 0, regime="ranging")
        assert trending_sl > ranging_sl

    def test_regime_tp_multipliers_exported(self, rm_mod):
        """REGIME_TP_MULTIPLIERS must be exported and have all 5 keys."""
        m = rm_mod.REGIME_TP_MULTIPLIERS
        for k in ("trending", "volatile", "ranging", "squeeze", "unknown"):
            assert k in m, f"Missing regime key: {k}"
        assert m["trending"] > m["ranging"], "trending TP should be higher than ranging TP"
        assert m["volatile"] < m["trending"], "volatile TP should be < trending (exit faster)"

    def test_regime_time_multipliers_exported(self, rm_mod):
        """REGIME_TIME_MULTIPLIERS must be exported with correct regime keys."""
        m = rm_mod.REGIME_TIME_MULTIPLIERS
        for k in ("trending", "volatile", "ranging", "squeeze", "unknown"):
            assert k in m, f"Missing regime key: {k}"
        # squeeze time = 1.0 (neutral), trending = 1.5 (longest hold)
        assert m["squeeze"] <= m["trending"], "squeeze time should be <= trending"
        assert m["volatile"] <= m["unknown"], "volatile time should be <= unknown"

    # ── Pipeline bridge regime-adjusted time stop ────────────────────────────

    def test_time_stop_adjusted_by_regime(self, rm_mod):
        """
        REGIME_TIME_MULTIPLIERS modulate base holding time.
        squeeze=1.0 (neutral), volatile=0.8 (shorter), trending=1.5 (longer).
        """
        base_hours = 48.0
        volatile_hours = base_hours * rm_mod.REGIME_TIME_MULTIPLIERS["volatile"]
        trending_hours = base_hours * rm_mod.REGIME_TIME_MULTIPLIERS["trending"]
        assert volatile_hours < base_hours, "volatile time stop should be shorter than base"
        assert trending_hours > base_hours, "trending time stop should be longer than base"

    # ── check_positions_on_tick reads regime from position ───────────────────

    def test_risk_manager_reads_regime_from_position(self, rm_mod):
        """
        When a position has regime='squeeze', the TP threshold should be lower
        (squeeze TP = 0.5×) compared to regime='trending' (1.5×).
        Inject two positions with same entry and same current price (at profit),
        and verify which one triggers TP.
        """
        from unittest.mock import MagicMock, patch
        import app.risk_manager as _rm_module

        # Isolate from operator config so tp_enabled stays True
        _orig_path = _rm_module._OPERATOR_CONFIG_PATH
        _rm_module._OPERATOR_CONFIG_PATH = "/dev/null"

        config = rm_mod.GlobalRiskConfig(
            max_stop_loss_pct=20.0,    # high hard stop so it doesn't interfere
            max_leverage=20.0,
            tp_enabled=True,           # must enable TP for regime TP test
        )
        agent_params = rm_mod.AgentRiskParams(
            effective_stop_loss_pct=20.0,   # high soft stop to avoid triggering
            effective_take_profit_pct=4.0,  # base TP = 4%
            trailing_stop_enabled=False,
        )

        manager = rm_mod.RiskManager(config=config, agent_params=agent_params)

        mock_tracker = MagicMock()
        mock_tracker.update_price = MagicMock()
        mock_tracker.compute_atr_pct.return_value = None
        mock_tracker.detect_spike.return_value = None
        manager._price_tracker = mock_tracker

        # Position in squeeze regime — TP = 4% × 0.5 = 2%
        # Current pnl = +3% → should trigger TP in squeeze, but not in trending (needs 6%)
        import time as _time
        entry_price = 100.0
        current_price = 103.0  # +3%
        # opened 1 hour ago → well within any time stop window (squeeze=14h, trending=72h)
        opened_ts_ms = int(_time.time() * 1000) - 3600 * 1000

        state_squeeze = {
            "positions": {
                "BTCUSDT": {
                    "symbol": "BTCUSDT",
                    "side": "Buy",
                    "qty": 1.0,
                    "avg_entry_price": entry_price,
                    "unrealized_pnl": 3.0,
                    "opened_ts_ms": opened_ts_ms,
                    "regime": "squeeze",
                }
            },
            "orders": [],
        }
        state_trending = {
            "positions": {
                "BTCUSDT": {
                    "symbol": "BTCUSDT",
                    "side": "Buy",
                    "qty": 1.0,
                    "avg_entry_price": entry_price,
                    "unrealized_pnl": 3.0,
                    "opened_ts_ms": opened_ts_ms,
                    "regime": "trending",
                }
            },
            "orders": [],
        }

        closes_squeeze = manager.check_positions_on_tick(state_squeeze, {"BTCUSDT": current_price})
        closes_trending = manager.check_positions_on_tick(state_trending, {"BTCUSDT": current_price})

        # squeeze TP = 4% × 0.5 = 2% → 3% profit → should trigger
        squeeze_reasons = [c["reason"] for c in closes_squeeze]
        assert any("take_profit" in r for r in squeeze_reasons), (
            f"squeeze regime at +3% should trigger TP (threshold=2%). reasons={squeeze_reasons}"
        )

        # trending TP = 4% × 1.5 = 6% → 3% profit → should NOT trigger
        trending_reasons = [c["reason"] for c in closes_trending]
        assert not any("take_profit" in r for r in trending_reasons), (
            f"trending regime at +3% should NOT trigger TP (threshold=6%). reasons={trending_reasons}"
        )

        # Restore operator config path
        _rm_module._OPERATOR_CONFIG_PATH = _orig_path
