"""
test_strategy_auto_deployer.py — Unit tests for StrategyAutoDeployer
策略自動部署器單元測試 — 覆蓋連續虧損/資本計算/持倉評分/成交通知/品類優先級

MODULE_NOTE (中文):
  DEAD-PY-3 清理後僅保留仍有效的測試：
  - 連續虧損自動暫停 (G1 rule)
  - 資本計算 (動態 qty + 邊界保護)
  - 持倉評分 (_score_existing_position)
  - 成交通知路由 (notify_fill)
  - 品類優先級常量
  - 狀態報告 (get_stats / get_deployed)
  - 線程安全 (concurrent on_trade_result)

  已移除的測試：部署/掃描/槽位/釘選/再平衡/過期移除 — 均依賴
  已刪除的 Python 策略類或已 stub 的 on_scan_results()。
  Rust ScannerRunner + openclaw_engine 負責策略部署。

MODULE_NOTE (English):
  After DEAD-PY-3, only tests for still-live functionality are kept:
  - Consecutive loss auto-pause, capital computation, position scoring,
    notify_fill routing, category priority, status reporting, thread safety.
  Removed: deploy/scan/slot/pinned/rebalance/stale removal tests — all
  depend on deleted Python strategy classes or stubbed on_scan_results().

Safety invariant:
  - All tests use mocks, zero real trades / 所有測試使用 mock，零真實交易。
"""

from __future__ import annotations

import threading
import time
import pytest
from unittest.mock import MagicMock

from local_model_tools.strategy_auto_deployer import StrategyAutoDeployer, CATEGORY_PRIORITY_BONUS


# =============================================================================
# Helpers / 測試輔助函數
# =============================================================================

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
        assert qty == pytest.approx(0.02, abs=0.005)

    def test_compute_qty_zero_price(self):
        """Zero price should return minimum qty safely / 零價格安全返回最小 qty"""
        deployer, _, _, _ = _make_deployer(balance=10000.0)
        qty = deployer._compute_qty("BTCUSDT", price=0.0, score=50.0)
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
        qty_default = deployer._compute_qty("BTCUSDT", price=50000.0, score=50.0)
        assert qty >= qty_default

    def test_compute_qty_high_score_bonus(self):
        """Higher score should produce larger position / 高分應產生更大倉位"""
        deployer, _, _, _ = _make_deployer(balance=10000.0)
        qty_low = deployer._compute_qty("ETHUSDT", price=3000.0, score=50.0)
        qty_high = deployer._compute_qty("ETHUSDT", price=3000.0, score=200.0)
        assert qty_high >= qty_low


# =============================================================================
# Test Class: Edge Cases (still-live subset) / 邊界用例（仍存活的子集）
# =============================================================================

class TestEdgeCases:
    """
    Edge cases for non-scan functionality.
    非掃描功能的邊界用例。
    """

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

    def test_get_deployed_returns_copy(self):
        """get_deployed should return a copy, not internal reference / 返回副本非內部引用"""
        deployer, _, _, _ = _make_deployer()
        deployer._deployed["test"] = {"symbol": "TEST", "category": "trend"}
        result = deployer.get_deployed()
        result.clear()
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
            "unrealized_pnl": 5.0,
            "created_ts_ms": int(time.time() * 1000),
        }
        score = deployer._score_existing_position("ETHUSDT", pos)
        assert score > 50.0

    def test_deep_loss_position_low_score(self):
        """Deep loss position should score well below 50 / 深度虧損持倉分數應遠低於 50"""
        deployer, _, _, _ = _make_deployer()
        pos = {
            "qty": 1.0, "avg_entry_price": 100.0,
            "unrealized_pnl": -10.0,
            "created_ts_ms": int(time.time() * 1000) - 10 * 3_600_000,
        }
        score = deployer._score_existing_position("ETHUSDT", pos)
        assert score < 30.0

    def test_score_clamped_0_to_100(self):
        """Score must always be in [0, 100] / 分數必須在 [0, 100] 範圍內"""
        deployer, _, _, _ = _make_deployer()
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
# Test Class: Notify Fill / 成交通知
# =============================================================================

class TestNotifyFill:
    """
    Verify notify_fill routes fills back to strategies.
    驗證成交通知路由回策略。
    """

    def test_notify_fill_routes_to_strategy(self):
        """Fill should be routed to the registered strategy / 成交應路由到已註冊策略"""
        deployer, orch, _, _ = _make_deployer()
        mock_strat = MagicMock()
        orch._strategies = {"test_strat": mock_strat}
        deployer.notify_fill("test_strat", {"price": 100}, is_open=True)
        mock_strat.on_fill.assert_called_once_with({"price": 100}, True)

    def test_notify_fill_missing_strategy_no_crash(self):
        """Fill for unknown strategy should not crash / 未知策略的成交不崩潰"""
        deployer, orch, _, _ = _make_deployer()
        orch._strategies = {}
        deployer.notify_fill("nonexistent", {"price": 100}, is_open=False)
        # No exception raised — success


# =============================================================================
# Test Class: Category Priority / 品類優先級
# =============================================================================

class TestCategoryPriority:
    """
    Verify CATEGORY_PRIORITY_BONUS constant values.
    驗證品類優先級加成常量。
    """

    def test_priority_bonus_values(self):
        """funding_arb should have highest bonus / funding_arb 應有最高加成"""
        assert CATEGORY_PRIORITY_BONUS["funding_arb"] > CATEGORY_PRIORITY_BONUS["trend"]
        assert CATEGORY_PRIORITY_BONUS["grid"] > CATEGORY_PRIORITY_BONUS["trend"]
        assert CATEGORY_PRIORITY_BONUS["funding_arb"] > CATEGORY_PRIORITY_BONUS["grid"]
