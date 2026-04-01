"""
test_strategy_auto_deployer.py — Unit tests for StrategyAutoDeployer
策略自動部署器單元測試 — 覆蓋部署/卸載/槽位限制/資本計算/線程安全

MODULE_NOTE (中文):
  驗證 StrategyAutoDeployer 的核心邏輯，重點涵蓋：
  1. 策略部署基礎（deploy → 狀態追蹤）
  2. 重複部署冪等性（同 symbol+category 不重複部署）
  3. max_symbols 槽位上限執行
  4. 智能再平衡（弱倉驅逐 + 高分新機會替換）
  5. 連續虧損自動暫停（G1 規則）
  6. 資本計算（動態 qty + 邊界保護）
  7. 釘選幣種（pinned symbols 始終部署、不被驅逐）
  8. 線程安全（並發 deploy/undeploy）
  9. 狀態報告（get_deployed / get_stats）

MODULE_NOTE (English):
  Validates StrategyAutoDeployer core logic, focusing on:
  1. Basic deployment (deploy → state tracking)
  2. Duplicate deploy idempotency (same symbol+category not re-deployed)
  3. max_symbols slot limit enforcement
  4. Smart rebalancing (weak position eviction + high-score replacement)
  5. Consecutive loss auto-pause (G1 rule)
  6. Capital computation (dynamic qty + boundary protection)
  7. Pinned symbols (always deployed, never evicted)
  8. Thread safety (concurrent deploy/undeploy)
  9. Status reporting (get_deployed / get_stats)

Safety invariant:
  - 所有測試使用 mock，零真實交易/網絡調用 / All tests use mocks, zero real trades.
"""

from __future__ import annotations

import threading
import time
import pytest
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

from local_model_tools.strategy_auto_deployer import StrategyAutoDeployer, CATEGORY_PRIORITY_BONUS


# =============================================================================
# Patch paths — strategies are imported locally inside _deploy_strategy(),
# so we must patch them at their source module, not at the deployer module.
# 策略類在 _deploy_strategy() 內部局部導入，需在源模組上 patch。
# =============================================================================

_PATCH_MA = "local_model_tools.strategies.ma_crossover.MACrossoverStrategy"
_PATCH_BOLL = "local_model_tools.strategies.bollinger_reversion.BollingerReversionStrategy"
_PATCH_FUNDING = "local_model_tools.strategies.funding_rate_arb.FundingRateArbStrategy"
_PATCH_GRID = "local_model_tools.strategies.grid_trading.GridTradingStrategy"
_PATCH_BREAKOUT = "local_model_tools.strategies.bb_breakout.BBBreakoutStrategy"


# =============================================================================
# Helpers / 測試輔助函數
# =============================================================================

@dataclass
class FakeOpportunity:
    """
    Mock opportunity object matching MarketScanner output.
    模擬 MarketScanner 產出的機會物件。
    """
    symbol: str = "ETHUSDT"
    score: float = 80.0
    category: str = "trend"
    price: float = 3000.0
    price_change_pct_24h: float = 2.5
    api_category: str = "linear"
    reason: str = "Test opportunity"


def _make_mock_strategy():
    """Create a mock strategy with required attributes / 建立帶必要屬性的 mock 策略"""
    s = MagicMock()
    s.name = "MockStrategy"
    s._default_metadata = {}
    return s


def _make_deployer(
    max_symbols: int = 25,
    balance: float = 10000.0,
    pinned_symbols: list[str] | None = None,
    reserved_slots: dict[str, int] | None = None,
) -> tuple[StrategyAutoDeployer, MagicMock, MagicMock, MagicMock]:
    """
    Create a StrategyAutoDeployer with fully mocked dependencies.
    建立帶完整 mock 依賴的 StrategyAutoDeployer。

    Returns: (deployer, mock_orchestrator, mock_kline_manager, mock_paper_engine)
    """
    orch = MagicMock()
    km = MagicMock()
    km.get_tracked_symbols.return_value = set()
    km.get_timeframes.return_value = ["15"]
    engine = MagicMock()
    engine.get_state.return_value = {
        "session": {"current_paper_balance_usdt": balance},
        "positions": {},
        "market_feed": {},
    }

    deployer = StrategyAutoDeployer(
        orchestrator=orch,
        kline_manager=km,
        paper_engine=engine,
        max_symbols=max_symbols,
        pinned_symbols=pinned_symbols,
        reserved_slots=reserved_slots,
    )
    return deployer, orch, km, engine


# =============================================================================
# Test Class: Deployment Basics / 部署基礎測試
# =============================================================================

class TestDeploymentBasics:
    """
    Basic deployment and state tracking tests.
    基礎部署與狀態追蹤測試。
    """

    @patch(_PATCH_MA, return_value=_make_mock_strategy())
    def test_deploy_single_strategy(self, mock_ma_cls):
        """Deploy one trend strategy, verify tracked in _deployed / 部署一個趨勢策略並驗證追蹤"""
        deployer, orch, km, _ = _make_deployer()

        opp = FakeOpportunity(symbol="BTCUSDT", category="trend", score=75.0, price=50000.0)
        deployer.on_scan_results([opp])

        deployed = deployer.get_deployed()
        assert len(deployed) == 1
        assert deployed[0]["symbol"] == "BTCUSDT"
        assert deployed[0]["category"] == "trend"
        orch.register_strategy.assert_called_once()
        orch.activate_strategy.assert_called_once()

    @patch(_PATCH_FUNDING, return_value=_make_mock_strategy())
    def test_deploy_funding_arb(self, mock_arb_cls):
        """Deploy a funding_arb strategy / 部署 funding_arb 策略"""
        deployer, orch, km, _ = _make_deployer()

        opp = FakeOpportunity(symbol="ETHUSDT", category="funding_arb", score=90.0, price=3000.0)
        deployer.on_scan_results([opp])

        deployed = deployer.get_deployed()
        assert len(deployed) == 1
        assert deployed[0]["category"] == "funding_arb"

    @patch(_PATCH_MA, return_value=_make_mock_strategy())
    def test_duplicate_deploy_idempotent(self, mock_ma_cls):
        """Deploying same symbol+category twice should not create duplicate / 重複部署冪等"""
        deployer, orch, km, _ = _make_deployer()

        opp = FakeOpportunity(symbol="BTCUSDT", category="trend", score=75.0, price=50000.0)
        deployer.on_scan_results([opp])
        deployer.on_scan_results([opp])

        deployed = deployer.get_deployed()
        assert len(deployed) == 1, "Same symbol+category should not be deployed twice"

    @patch(_PATCH_BOLL, return_value=_make_mock_strategy())
    @patch(_PATCH_MA, return_value=_make_mock_strategy())
    def test_deploy_different_categories_same_symbol(self, mock_ma, mock_boll):
        """
        Same symbol with different categories should create separate deployments.
        同一 symbol 不同 category 應各自獨立部署。
        """
        deployer, orch, km, _ = _make_deployer()

        opp_trend = FakeOpportunity(symbol="BTCUSDT", category="trend", score=75.0, price=50000.0)
        opp_reversion = FakeOpportunity(symbol="BTCUSDT", category="reversion", score=65.0, price=50000.0)
        deployer.on_scan_results([opp_trend, opp_reversion])

        deployed = deployer.get_deployed()
        assert len(deployed) == 2
        categories = {d["category"] for d in deployed}
        assert categories == {"trend", "reversion"}

    def test_unknown_category_skipped(self):
        """Unknown category should produce no deployment / 未知 category 不部署"""
        deployer, orch, km, _ = _make_deployer()

        opp = FakeOpportunity(symbol="XYZUSDT", category="unknown_strat", score=99.0, price=1.0)
        deployer.on_scan_results([opp])

        deployed = deployer.get_deployed()
        assert len(deployed) == 0


# =============================================================================
# Test Class: Symbol Limit / 槽位上限測試
# =============================================================================

class TestSymbolLimit:
    """
    Verify max_symbols enforcement and smart rebalancing.
    驗證 max_symbols 上限執行與智能再平衡。
    """

    @patch(_PATCH_MA, return_value=_make_mock_strategy())
    def test_max_symbols_enforced(self, mock_ma_cls):
        """
        When max_symbols is reached, low-score opportunities are rejected.
        當槽位已滿時，低分機會被拒絕。
        """
        deployer, orch, km, _ = _make_deployer(max_symbols=2)

        opps = [
            FakeOpportunity(symbol="BTCUSDT", category="trend", score=80.0, price=50000.0),
            FakeOpportunity(symbol="ETHUSDT", category="trend", score=70.0, price=3000.0),
            FakeOpportunity(symbol="SOLUSDT", category="trend", score=50.0, price=100.0),
        ]
        deployer.on_scan_results(opps)

        deployed = deployer.get_deployed()
        deployed_symbols = {d["symbol"] for d in deployed}
        # max_symbols=2, so at most 2 unique symbols deployed
        assert len(deployed_symbols) <= 2

    @patch(_PATCH_MA, return_value=_make_mock_strategy())
    def test_rebalance_replaces_weak_position(self, mock_ma_cls):
        """
        High-score new opportunity replaces weakest existing position.
        高分新機會可以替換最弱現有持倉。
        """
        deployer, orch, km, engine = _make_deployer(max_symbols=1)

        # Deploy first strategy
        opp1 = FakeOpportunity(symbol="BTCUSDT", category="trend", score=60.0, price=50000.0)
        deployer.on_scan_results([opp1])
        assert len(deployer.get_deployed()) == 1

        # Setup: existing position with a loss (low keep-score)
        engine.get_state.return_value = {
            "session": {"current_paper_balance_usdt": 10000.0},
            "positions": {
                "BTCUSDT": {
                    "side": "Buy",
                    "qty": 0.01,
                    "avg_entry_price": 50000.0,
                    "unrealized_pnl": -500.0,
                    "mark_price": 45000.0,
                    "created_ts_ms": int(time.time() * 1000) - 20 * 3_600_000,
                },
            },
            "market_feed": {},
        }
        engine.submit_order.return_value = {"status": "filled"}

        # New high-score opportunity should trigger rebalance
        opp2 = FakeOpportunity(symbol="SOLUSDT", category="trend", score=150.0, price=100.0)
        deployer.on_scan_results([opp2])

        deployed_symbols = {d["symbol"] for d in deployer.get_deployed()}
        assert "SOLUSDT" in deployed_symbols
        stats = deployer.get_stats()
        assert stats["rebalance_triggered"] >= 1


# =============================================================================
# Test Class: Stale Strategy Removal / 過期策略移除
# =============================================================================

class TestStaleRemoval:
    """
    Test remove_stale_strategies cleanup.
    測試過期策略移除功能。
    """

    @patch(_PATCH_MA, return_value=_make_mock_strategy())
    def test_remove_stale_strategies(self, mock_ma_cls):
        """Strategies for symbols no longer active should be removed / 不再活躍的 symbol 策略應被移除"""
        deployer, orch, km, _ = _make_deployer()

        opp = FakeOpportunity(symbol="BTCUSDT", category="trend", score=75.0, price=50000.0)
        deployer.on_scan_results([opp])
        assert len(deployer.get_deployed()) == 1

        deployer.remove_stale_strategies(active_symbols={"ETHUSDT"})
        assert len(deployer.get_deployed()) == 0

        stats = deployer.get_stats()
        assert stats["strategies_removed"] >= 1

    @patch(_PATCH_MA, return_value=_make_mock_strategy())
    def test_remove_stale_keeps_active(self, mock_ma_cls):
        """Active symbols should not be removed / 活躍的 symbol 不被移除"""
        deployer, orch, km, _ = _make_deployer()

        opp = FakeOpportunity(symbol="BTCUSDT", category="trend", score=75.0, price=50000.0)
        deployer.on_scan_results([opp])
        deployer.remove_stale_strategies(active_symbols={"BTCUSDT"})
        assert len(deployer.get_deployed()) == 1


# =============================================================================
# Test Class: Consecutive Loss Auto-Pause / 連續虧損自動暫停
# =============================================================================

class TestConsecutiveLossAutoPause:
    """
    G1 rule: auto-pause after MAX_CONSECUTIVE_LOSSES.
    G1 規則：連續虧損超過閾值後自動暫停策略。
    """

    def test_consecutive_losses_auto_pause(self):
        """Strategy paused after 10 consecutive losses / 連續 10 次虧損後自動暫停"""
        deployer, orch, km, _ = _make_deployer()
        strategy_name = "MA_Crossover_BTCUSDT"

        for i in range(10):
            deployer.on_trade_result(strategy_name, close_pnl=-10.0)

        orch.pause_strategy.assert_called_once_with(strategy_name)
        assert deployer._stats["strategies_auto_paused"] == 1

    def test_win_resets_loss_counter(self):
        """A winning trade resets the consecutive loss counter / 盈利交易重置虧損計數"""
        deployer, orch, km, _ = _make_deployer()
        strategy_name = "MA_Crossover_BTCUSDT"

        for _ in range(5):
            deployer.on_trade_result(strategy_name, close_pnl=-10.0)
        # Win should reset
        deployer.on_trade_result(strategy_name, close_pnl=50.0)

        assert deployer._consecutive_losses.get(strategy_name) is None

        # Continue losing — should not pause at 5 more (total 5, not 10)
        for _ in range(4):
            deployer.on_trade_result(strategy_name, close_pnl=-10.0)
        orch.pause_strategy.assert_not_called()

    def test_breakeven_resets_counter(self):
        """Zero PnL (breakeven) also resets counter / 零 PnL 也重置計數"""
        deployer, orch, km, _ = _make_deployer()
        strategy_name = "test_strat"

        for _ in range(5):
            deployer.on_trade_result(strategy_name, close_pnl=-10.0)
        deployer.on_trade_result(strategy_name, close_pnl=0.0)

        assert deployer._consecutive_losses.get(strategy_name) is None


# =============================================================================
# Test Class: Capital Computation / 資本計算
# =============================================================================

class TestCapitalComputation:
    """
    Verify qty calculation logic and boundary protection.
    驗證倉位大小計算邏輯與邊界保護。
    """

    def test_compute_qty_basic(self):
        """Basic qty calculation with default parameters / 基本 qty 計算"""
        deployer, _, _, _ = _make_deployer(balance=10000.0)
        qty = deployer._compute_qty("BTCUSDT", price=50000.0, score=100.0)
        assert qty > 0
        # With 10k balance, 3% risk, 5% stop -> $600/0.05=$12000 notional
        # score 100 -> mult=1.0 -> $12000 allocated -> but capped at max_qty_pct(10%)=$1000
        # qty = 1000/50000 = 0.02
        assert qty == pytest.approx(0.02, abs=0.005)

    def test_compute_qty_zero_price(self):
        """Zero price should return minimum qty safely / 零價格安全返回最小 qty"""
        deployer, _, _, _ = _make_deployer(balance=10000.0)
        qty = deployer._compute_qty("BTCUSDT", price=0.0, score=50.0)
        # balance>0 but price<=0 -> min_qty_usdt/max(price,1) = 10/1 = 10
        assert qty == pytest.approx(10.0, abs=0.1)

    def test_compute_qty_zero_balance(self):
        """Zero balance should still return a valid small qty / 零餘額仍返回有效小 qty"""
        deployer, _, _, engine = _make_deployer(balance=0.0)
        engine.get_state.return_value = {
            "session": {"current_paper_balance_usdt": 0.0},
            "positions": {},
        }
        qty = deployer._compute_qty("ETHUSDT", price=3000.0, score=50.0)
        assert qty > 0, "Should return minimum qty even with zero balance"

    def test_compute_dynamic_qty_uses_deployed_score(self):
        """compute_dynamic_qty should use the original deployment score / 動態 qty 使用原始部署分數"""
        deployer, _, _, _ = _make_deployer(balance=10000.0)
        # Manually inject a deployed entry
        deployer._deployed["trend_BTCUSDT"] = {
            "symbol": "BTCUSDT",
            "category": "trend",
            "strategy_name": "MA_Crossover_BTCUSDT",
            "score": 150.0,
            "deployed_ts_ms": int(time.time() * 1000),
        }
        qty = deployer.compute_dynamic_qty("BTCUSDT", price=50000.0)
        # Score 150 -> higher multiplier -> larger qty than default score=50
        qty_default = deployer._compute_qty("BTCUSDT", price=50000.0, score=50.0)
        assert qty >= qty_default

    def test_compute_qty_high_score_bonus(self):
        """Higher score should produce larger position / 高分應產生更大倉位"""
        deployer, _, _, _ = _make_deployer(balance=10000.0)
        qty_low = deployer._compute_qty("ETHUSDT", price=3000.0, score=50.0)
        qty_high = deployer._compute_qty("ETHUSDT", price=3000.0, score=200.0)
        assert qty_high >= qty_low


# =============================================================================
# Test Class: Pinned Symbols / 釘選幣種
# =============================================================================

class TestPinnedSymbols:
    """
    Pinned symbols should be auto-deployed on first scan and never evicted.
    釘選幣種應在首次掃描時自動部署，且不被再平衡驅逐。
    """

    @patch(_PATCH_MA, return_value=_make_mock_strategy())
    def test_pinned_symbols_deployed_on_first_scan(self, mock_ma_cls):
        """Pinned symbols deployed even with empty scan results / 空掃描結果也部署釘選幣種"""
        deployer, orch, km, _ = _make_deployer(pinned_symbols=["BTCUSDT", "ETHUSDT"])

        deployer.on_scan_results([])

        deployed_symbols = {d["symbol"] for d in deployer.get_deployed()}
        assert "BTCUSDT" in deployed_symbols
        assert "ETHUSDT" in deployed_symbols

    @patch(_PATCH_MA, return_value=_make_mock_strategy())
    def test_pinned_not_evicted_by_rebalance(self, mock_ma_cls):
        """Pinned symbols should not be evicted by find_weakest_position / 釘選幣種不被驅逐"""
        deployer, orch, km, engine = _make_deployer(
            max_symbols=2, pinned_symbols=["BTCUSDT"],
        )

        # Simulate positions — BTCUSDT with bad loss but pinned
        engine.get_state.return_value = {
            "session": {"current_paper_balance_usdt": 10000.0},
            "positions": {
                "BTCUSDT": {
                    "side": "Buy", "qty": 0.01, "avg_entry_price": 50000.0,
                    "unrealized_pnl": -2000.0, "created_ts_ms": 0,
                },
            },
            "market_feed": {},
        }

        weakest_sym, _ = deployer._find_weakest_position()
        assert weakest_sym != "BTCUSDT", "Pinned symbol must not be evicted"

    @patch(_PATCH_MA, return_value=_make_mock_strategy())
    def test_pinned_deployed_only_once(self, mock_ma_cls):
        """Pinned symbols should only be deployed on the first scan / 釘選幣種僅首次掃描部署"""
        deployer, orch, km, _ = _make_deployer(pinned_symbols=["BTCUSDT"])

        deployer.on_scan_results([])
        deployer.on_scan_results([])

        deployed = deployer.get_deployed()
        btc_deployments = [d for d in deployed if d["symbol"] == "BTCUSDT"]
        assert len(btc_deployments) == 1


# =============================================================================
# Test Class: Edge Cases / 邊界用例
# =============================================================================

class TestEdgeCases:
    """
    Edge cases: pump/dump filtering, no engine, pipeline bridge registration.
    邊界用例：暴漲暴跌過濾、無引擎、pipeline bridge 登記。
    """

    @patch(_PATCH_MA, return_value=_make_mock_strategy())
    def test_pump_dump_filter_skips_extreme_change(self, mock_ma_cls):
        """
        Trend strategy should not deploy for symbols with >40% daily change.
        日漲跌幅超過 40% 的幣不部署趨勢策略（暴漲暴跌過濾）。
        """
        deployer, orch, km, _ = _make_deployer()

        opp = FakeOpportunity(
            symbol="MEMEUSDT", category="trend", score=90.0,
            price=0.01, price_change_pct_24h=55.0,
        )
        deployer.on_scan_results([opp])
        assert len(deployer.get_deployed()) == 0

    @patch(_PATCH_MA, return_value=_make_mock_strategy())
    def test_negative_pump_dump_filter(self, mock_ma_cls):
        """Negative extreme daily change (-50%) also filtered / 負極端日漲跌幅也被過濾"""
        deployer, orch, km, _ = _make_deployer()

        opp = FakeOpportunity(
            symbol="CRASHUSDT", category="trend", score=90.0,
            price=1.0, price_change_pct_24h=-55.0,
        )
        deployer.on_scan_results([opp])
        assert len(deployer.get_deployed()) == 0

    def test_no_engine_returns_empty_positions(self):
        """With no paper engine, open positions should be empty / 無引擎時持倉為空"""
        orch = MagicMock()
        km = MagicMock()
        km.get_tracked_symbols.return_value = set()
        deployer = StrategyAutoDeployer(orch, km, paper_engine=None)
        assert deployer._get_open_positions() == {}

    def test_no_engine_get_balance_default(self):
        """With no paper engine, balance should default to 10000 / 無引擎時餘額預設 10000"""
        orch = MagicMock()
        km = MagicMock()
        km.get_tracked_symbols.return_value = set()
        deployer = StrategyAutoDeployer(orch, km, paper_engine=None)
        assert deployer._get_balance() == 10000.0

    @patch(_PATCH_MA, return_value=_make_mock_strategy())
    def test_pipeline_bridge_registration(self, mock_ma_cls):
        """Deploy should call pipeline_bridge.register_symbol_category / 部署時應登記品類"""
        deployer, orch, km, _ = _make_deployer()
        mock_bridge = MagicMock()
        deployer.set_pipeline_bridge(mock_bridge)

        opp = FakeOpportunity(symbol="BTCUSDT", category="trend", api_category="spot", price=50000.0)
        deployer.on_scan_results([opp])

        mock_bridge.register_symbol_category.assert_called_once_with("BTCUSDT", "spot")

    @patch(_PATCH_MA, return_value=_make_mock_strategy())
    def test_pipeline_bridge_failure_non_blocking(self, mock_ma_cls):
        """Pipeline bridge registration failure must not block deployment / 登記失敗不阻斷部署"""
        deployer, orch, km, _ = _make_deployer()
        mock_bridge = MagicMock()
        mock_bridge.register_symbol_category.side_effect = RuntimeError("bridge error")
        deployer.set_pipeline_bridge(mock_bridge)

        opp = FakeOpportunity(symbol="BTCUSDT", category="trend", price=50000.0)
        deployer.on_scan_results([opp])

        # Deployment should still succeed despite bridge error
        assert len(deployer.get_deployed()) == 1

    @patch(_PATCH_MA, return_value=_make_mock_strategy())
    def test_api_category_injected_for_non_linear(self, mock_ma_cls):
        """Non-linear api_category should be injected into strategy metadata / 非 linear 品類注入策略元數據"""
        mock_strat = _make_mock_strategy()
        mock_ma_cls.return_value = mock_strat
        deployer, orch, km, _ = _make_deployer()

        opp = FakeOpportunity(symbol="BTCUSDT", category="trend", api_category="spot", price=50000.0)
        deployer.on_scan_results([opp])

        assert mock_strat._default_metadata.get("category") == "spot"


# =============================================================================
# Test Class: Status Reporting / 狀態報告
# =============================================================================

class TestStatusReporting:
    """
    Verify get_deployed() and get_stats() output.
    驗證狀態查詢 API 的輸出格式。
    """

    def test_get_stats_initial(self):
        """Initial stats should be all zeros / 初始統計應全為零"""
        deployer, _, _, _ = _make_deployer()
        stats = deployer.get_stats()
        assert stats["component"] == "strategy_auto_deployer"
        assert stats["deployed_count"] == 0
        assert stats["strategies_deployed"] == 0
        assert stats["strategies_removed"] == 0
        assert stats["scan_callbacks_received"] == 0

    @patch(_PATCH_MA, return_value=_make_mock_strategy())
    def test_stats_after_deploy(self, mock_ma_cls):
        """Stats should reflect deployment / 統計應反映部署狀態"""
        deployer, _, _, _ = _make_deployer()

        opp = FakeOpportunity(symbol="BTCUSDT", category="trend", price=50000.0)
        deployer.on_scan_results([opp])

        stats = deployer.get_stats()
        assert stats["deployed_count"] == 1
        assert stats["strategies_deployed"] == 1
        assert stats["scan_callbacks_received"] == 1
        assert "BTCUSDT" in stats["deployed_symbols"]

    def test_get_deployed_returns_copy(self):
        """get_deployed should return a copy, not internal reference / 返回副本非內部引用"""
        deployer, _, _, _ = _make_deployer()
        deployer._deployed["test"] = {"symbol": "TEST", "category": "trend"}
        result = deployer.get_deployed()
        result.clear()
        # Internal state should be unaffected
        assert len(deployer._deployed) == 1


# =============================================================================
# Test Class: Thread Safety / 線程安全
# =============================================================================

class TestThreadSafety:
    """
    Concurrent operations should not corrupt state.
    並發操作不應損壞狀態。
    """

    def test_concurrent_on_trade_result(self):
        """Multiple threads calling on_trade_result should not crash / 多線程 on_trade_result 不崩潰"""
        deployer, orch, _, _ = _make_deployer()
        errors: list[Exception] = []

        def worker(strategy_name: str, pnl: float, count: int):
            try:
                for _ in range(count):
                    deployer.on_trade_result(strategy_name, pnl)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=worker, args=("strat_A", -5.0, 50)),
            threading.Thread(target=worker, args=("strat_B", 10.0, 50)),
            threading.Thread(target=worker, args=("strat_A", 20.0, 50)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0, f"Thread safety violation: {errors}"

    @patch(_PATCH_MA, return_value=_make_mock_strategy())
    def test_concurrent_scan_and_remove(self, mock_ma_cls):
        """Concurrent on_scan_results and remove_stale should not crash / 並發掃描+移除不崩潰"""
        deployer, orch, km, _ = _make_deployer()
        errors: list[Exception] = []

        def scan_worker():
            try:
                for i in range(20):
                    opp = FakeOpportunity(symbol=f"SYM{i}USDT", category="trend", price=100.0)
                    deployer.on_scan_results([opp])
            except Exception as e:
                errors.append(e)

        def remove_worker():
            try:
                for _ in range(20):
                    deployer.remove_stale_strategies(active_symbols=set())
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=scan_worker)
        t2 = threading.Thread(target=remove_worker)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert len(errors) == 0, f"Thread safety violation: {errors}"


# =============================================================================
# Test Class: Position Scoring / 持倉評分
# =============================================================================

class TestPositionScoring:
    """
    Verify _score_existing_position logic.
    驗證現有持倉評分邏輯。
    """

    def test_profitable_position_high_score(self):
        """Profitable position should score above 50 / 盈利持倉分數應高於 50"""
        deployer, _, _, _ = _make_deployer()
        pos = {
            "qty": 1.0, "avg_entry_price": 100.0,
            "unrealized_pnl": 5.0,  # 5% profit
            "created_ts_ms": int(time.time() * 1000),
        }
        score = deployer._score_existing_position("ETHUSDT", pos)
        assert score > 50.0

    def test_deep_loss_position_low_score(self):
        """Deep loss position should score well below 50 / 深度虧損持倉分數應遠低於 50"""
        deployer, _, _, _ = _make_deployer()
        pos = {
            "qty": 1.0, "avg_entry_price": 100.0,
            "unrealized_pnl": -10.0,  # -10% loss
            "created_ts_ms": int(time.time() * 1000) - 10 * 3_600_000,
        }
        score = deployer._score_existing_position("ETHUSDT", pos)
        assert score < 30.0

    def test_score_clamped_0_to_100(self):
        """Score must always be in [0, 100] / 分數必須在 [0, 100] 範圍內"""
        deployer, _, _, _ = _make_deployer()
        # Extreme loss
        pos = {
            "qty": 1.0, "avg_entry_price": 100.0,
            "unrealized_pnl": -500.0,
            "created_ts_ms": 0,
        }
        score = deployer._score_existing_position("ETHUSDT", pos)
        assert 0.0 <= score <= 100.0

    def test_neutral_position_near_baseline(self):
        """Zero PnL position should score near 50 / 零 PnL 持倉分數應接近 50"""
        deployer, _, _, _ = _make_deployer()
        pos = {
            "qty": 1.0, "avg_entry_price": 100.0,
            "unrealized_pnl": 0.0,
            "created_ts_ms": int(time.time() * 1000),
        }
        score = deployer._score_existing_position("ETHUSDT", pos)
        assert 45.0 <= score <= 55.0


# =============================================================================
# Test Class: Reserved Slots / 預留槽位
# =============================================================================

class TestReservedSlots:
    """
    Reserved slots per api_category should guarantee capacity.
    每個 api_category 的預留槽位應保證容量。
    """

    @patch(_PATCH_BOLL, return_value=_make_mock_strategy())
    @patch(_PATCH_MA, return_value=_make_mock_strategy())
    def test_reserved_slot_allows_deploy_when_full(self, mock_ma, mock_boll):
        """
        Even when max_symbols reached, a reserved-slot category can still deploy.
        即使總槽位已滿，預留品類仍可部署。
        """
        deployer, orch, km, _ = _make_deployer(
            max_symbols=1,
            reserved_slots={"spot": 2},
        )

        # Fill with a linear trend strategy
        opp_linear = FakeOpportunity(
            symbol="BTCUSDT", category="trend", score=80.0,
            price=50000.0, api_category="linear",
        )
        deployer.on_scan_results([opp_linear])
        assert len(deployer.get_deployed()) == 1

        # Spot opportunity should still deploy thanks to reserved slot
        opp_spot = FakeOpportunity(
            symbol="AAVEUSDT", category="reversion", score=60.0,
            price=200.0, api_category="spot",
        )
        deployer.on_scan_results([opp_spot])

        deployed = deployer.get_deployed()
        symbols = {d["symbol"] for d in deployed}
        assert "AAVEUSDT" in symbols, "Reserved slot should allow spot deployment even when full"


# =============================================================================
# Test Class: Notify Fill / 成交通知
# =============================================================================

class TestNotifyFill:
    """
    Verify notify_fill routes fills back to strategies.
    驗證成交通知路由回策略。
    """

    def test_notify_fill_routes_to_strategy(self):
        """Fill should be routed to the strategy's on_fill / 成交應路由到策略的 on_fill"""
        deployer, orch, _, _ = _make_deployer()
        mock_strategy = MagicMock()
        orch._strategies = {"MA_Crossover_BTCUSDT": mock_strategy}

        fill = {"symbol": "BTCUSDT", "qty": 0.01, "price": 50000.0}
        deployer.notify_fill("MA_Crossover_BTCUSDT", fill, is_open=True)

        mock_strategy.on_fill.assert_called_once_with(fill, True)

    def test_notify_fill_missing_strategy_no_crash(self):
        """Missing strategy should not crash / 缺少策略不應崩潰"""
        deployer, orch, _, _ = _make_deployer()
        orch._strategies = {}

        # Should not raise
        deployer.notify_fill("nonexistent_strat", {"qty": 1}, is_open=False)


# =============================================================================
# Test Class: Category Priority / 品類優先級
# =============================================================================

class TestCategoryPriority:
    """
    Verify CATEGORY_PRIORITY_BONUS ordering in deployment.
    驗證品類優先級加分對部署順序的影響。
    """

    def test_priority_bonus_values(self):
        """Funding arb should have highest priority bonus / funding_arb 應有最高優先級"""
        assert CATEGORY_PRIORITY_BONUS["funding_arb"] > CATEGORY_PRIORITY_BONUS["grid"]
        assert CATEGORY_PRIORITY_BONUS["grid"] > CATEGORY_PRIORITY_BONUS["trend"]
        assert CATEGORY_PRIORITY_BONUS["trend"] == 0
