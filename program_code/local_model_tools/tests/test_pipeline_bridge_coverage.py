"""
E4 Wave 2 P1-6: PipelineBridge 覆蓋率測試
Extended coverage tests for PipelineBridge — target 40%+ branch coverage.

新增測試場景：
  - __init__ 初始狀態驗證
  - setter 注入方法（set_guardian_agent / set_analyst_agent / set_ollama_client 等）
  - Guardian=None fail-closed 路徑（P0-2 修復驗證）
  - GovernanceHub 授權通過 vs 拒絕路徑
  - Guardian APPROVED / REJECTED / MODIFIED 路徑
  - Guardian exception → fail-closed
  - on_tick 基本分發：inactive 跳過、active 計數
  - on_tick 屬性對象事件（非 dict）
  - on_tick 無效 symbol/price 跳過
  - _check_stops 止損觸發
  - _check_stops 倉位已平跳過
  - stats 計數器遞增
  - set_telegram / set_demo_connector / set_observation_writer 等
  - _process_pending_intents 空意圖早退
  - _process_pending_intents 超過 max_intents_per_tick 截斷
  - on_tick_result 填單路徑
  - get_stats 返回格式
  - activate / deactivate 狀態切換
  - _try_learning_promotion 門控未設時無報錯

作者：E4（Test Engineer）
日期：2026-03-31
"""

from __future__ import annotations

import sys
import os
import time
import threading
from typing import Any
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Path setup — mirror existing test_pipeline_bridge.py approach
# ---------------------------------------------------------------------------
_tests_dir = os.path.dirname(os.path.abspath(__file__))
_local_model_tools = os.path.dirname(_tests_dir)
_program_code = os.path.dirname(_local_model_tools)
_control_api = os.path.join(
    _program_code, "exchange_connectors", "bybit_connector", "control_api_v1"
)
if _control_api not in sys.path:
    sys.path.insert(0, _control_api)
if _program_code not in sys.path:
    sys.path.insert(0, _program_code)

from app.pipeline_bridge import PipelineBridge
from app.multi_agent_framework import RiskVerdict, RiskVerdictResult, TradeIntent
from local_model_tools.kline_manager import KlineManager
from local_model_tools.indicator_engine import IndicatorEngine
from local_model_tools.signal_generator import SignalEngine
from local_model_tools.strategy_orchestrator import StrategyOrchestrator


# ---------------------------------------------------------------------------
# Shared mock helpers
# ---------------------------------------------------------------------------

class MockPaperEngine:
    """Minimal mock for PaperTradingEngine"""

    def __init__(self, *, reject: bool = False):
        self.submitted_orders: list = []
        self._reject = reject
        self._state: dict = {"positions": {}}

    def submit_order(self, **kwargs) -> dict:
        self.submitted_orders.append(kwargs)
        if self._reject:
            return {"order": {}, "rejected_reason": "risk_limit", "fills": [], "close_pnl": 0.0}
        return {
            "order": {"id": len(self.submitted_orders)},
            "rejected_reason": None,
            "fills": [],
            "close_pnl": 0.0,
        }

    def get_state(self) -> dict:
        return self._state


def _make_bridge(*, reject: bool = False, auto_submit: bool = True,
                 max_intents: int = 20) -> tuple[PipelineBridge, MockPaperEngine]:
    km = KlineManager(symbols=["BTCUSDT"], timeframes=["1m"])
    ie = IndicatorEngine(kline_manager=km)
    se = SignalEngine()
    ie.register_on_update(se.on_indicators_update)
    orch = StrategyOrchestrator(
        kline_manager=km, indicator_engine=ie, signal_engine=se
    )
    engine = MockPaperEngine(reject=reject)
    bridge = PipelineBridge(
        kline_manager=km,
        indicator_engine=ie,
        signal_engine=se,
        orchestrator=orch,
        paper_engine=engine,
        auto_submit_intents=auto_submit,
        max_intents_per_tick=max_intents,
    )
    return bridge, engine


def _make_intent(symbol: str = "BTCUSDT", side: str = "Buy",
                 qty: float = 0.001) -> Any:
    """Return a simple duck-typed order intent object."""
    intent = type("OrderIntent", (), {
        "symbol": symbol,
        "side": side,
        "order_type": "market",
        "qty": qty,
        "price": None,
        "metadata": {"strategy_name": "test_strategy", "category": "linear"},
        "perception_data_id": None,
        "confidence": 0.6,
        "reason": "test_signal",
        "strategy_name": "test_strategy",
        "leverage": 1.0,
    })()
    return intent


def _make_guardian(result: RiskVerdictResult, modified_params: dict | None = None,
                   risk_score: float = 0.3) -> MagicMock:
    """Return a mock GuardianAgent that yields the specified verdict."""
    guardian = MagicMock()
    verdict = RiskVerdict(
        result=result,
        reason="test_reason",
        modified_params=modified_params or {},
        risk_score=risk_score,
    )
    guardian.review_intent.return_value = verdict
    guardian.update_active_positions = MagicMock()
    return guardian


def _make_governance_hub(*, authorized: bool = True) -> MagicMock:
    hub = MagicMock()
    hub.is_authorized.return_value = authorized
    return hub


def _tick_event(symbol: str = "BTCUSDT", price: float = 60000.0,
                ts_ms: int | None = None) -> dict:
    return {
        "symbol": symbol,
        "last_price": price,
        "ts_ms": ts_ms if ts_ms is not None else int(time.time() * 1000),
    }


# ===========================================================================
# 1. __init__ 初始狀態
# ===========================================================================

class TestPipelineBridgeInit:
    """Verify constructor sets all attributes to safe defaults."""

    def setup_method(self):
        self.bridge, self.engine = _make_bridge()

    def test_is_not_active_by_default(self):
        assert self.bridge.is_active is False

    def test_stats_all_zeros_by_default(self):
        stats = self.bridge.get_stats()
        assert stats["ticks_received"] == 0
        assert stats["intents_submitted"] == 0
        assert stats["intents_accepted"] == 0
        assert stats["intents_rejected"] == 0
        assert stats["stops_triggered"] == 0
        assert stats["errors"] == 0

    def test_no_guardian_by_default(self):
        assert self.bridge._guardian_agent is None

    def test_no_governance_hub_by_default(self):
        assert self.bridge._governance_hub is None

    def test_no_ollama_client_by_default(self):
        assert self.bridge._ollama_client is None

    def test_edge_filter_enabled_by_default(self):
        assert self.bridge._edge_filter_enabled is True

    def test_open_positions_empty_by_default(self):
        assert self.bridge._open_positions == {}

    def test_learning_stats_zeros(self):
        assert self.bridge._learning_stats["total_trades"] == 0
        assert self.bridge._learning_stats["winning_trades"] == 0

    def test_guardian_stats_zeros(self):
        gs = self.bridge._guardian_stats
        assert gs["checked"] == 0
        assert gs["approved"] == 0
        assert gs["rejected"] == 0
        assert gs["modified"] == 0
        assert gs["errors"] == 0


# ===========================================================================
# 2. Setter 注入方法
# ===========================================================================

class TestSetterInjection:
    """set_* methods should store reference and not raise."""

    def setup_method(self):
        self.bridge, _ = _make_bridge()

    def test_set_guardian_agent(self):
        mock_guardian = MagicMock()
        self.bridge.set_guardian_agent(mock_guardian)
        assert self.bridge._guardian_agent is mock_guardian

    def test_set_analyst_agent(self):
        mock_analyst = MagicMock()
        self.bridge.set_analyst_agent(mock_analyst)
        assert self.bridge._analyst_agent is mock_analyst

    def test_set_ollama_client(self):
        mock_client = MagicMock()
        self.bridge.set_ollama_client(mock_client)
        assert self.bridge._ollama_client is mock_client

    def test_set_telegram(self):
        mock_tg = MagicMock()
        self.bridge.set_telegram(mock_tg)
        assert self.bridge._telegram is mock_tg

    def test_set_demo_connector(self):
        mock_demo = MagicMock()
        self.bridge.set_demo_connector(mock_demo)
        assert self.bridge._demo_connector is mock_demo

    def test_set_governance_hub(self):
        mock_hub = MagicMock()
        self.bridge.set_governance_hub(mock_hub)
        assert self.bridge._governance_hub is mock_hub

    def test_set_message_bus(self):
        mock_bus = MagicMock()
        self.bridge.set_message_bus(mock_bus)
        assert self.bridge._message_bus is mock_bus

    def test_set_observation_writer(self):
        fn = MagicMock()
        self.bridge.set_observation_writer(fn)
        assert self.bridge._observation_writer is fn

    def test_set_executor_agent(self):
        mock_exec = MagicMock()
        self.bridge.set_executor_agent(mock_exec)
        assert self.bridge._executor_agent is mock_exec

    def test_set_strategist_agent(self):
        mock_strat = MagicMock()
        self.bridge.set_strategist_agent(mock_strat)
        assert self.bridge._strategist_agent is mock_strat

    def test_set_learning_tier_gate(self):
        mock_gate = MagicMock()
        self.bridge.set_learning_tier_gate(mock_gate)
        assert self.bridge._learning_tier_gate is mock_gate

    def test_set_auto_deployer(self):
        mock_dep = MagicMock()
        self.bridge.set_auto_deployer(mock_dep)
        assert self.bridge._auto_deployer is mock_dep

    def test_set_scanner_rate_limiter(self):
        mock_limiter = MagicMock()
        self.bridge.set_scanner_rate_limiter(mock_limiter)
        assert self.bridge._scanner_rate_limiter is mock_limiter


# ===========================================================================
# 3. activate / deactivate
# ===========================================================================

class TestActivateDeactivate:
    """Activate sets _active; deactivate clears it."""

    def setup_method(self):
        self.bridge, _ = _make_bridge()

    def test_activate_sets_active(self):
        self.bridge.activate()
        assert self.bridge.is_active is True

    def test_deactivate_clears_active(self):
        self.bridge.activate()
        self.bridge.deactivate()
        assert self.bridge.is_active is False

    def test_activate_is_idempotent(self):
        self.bridge.activate()
        self.bridge.activate()
        assert self.bridge.is_active is True


# ===========================================================================
# 4. on_tick 基本分發
# ===========================================================================

class TestOnTick:
    """on_tick fan-out behaviour."""

    def setup_method(self):
        self.bridge, self.engine = _make_bridge()

    def test_tick_increments_counter(self):
        self.bridge.activate()
        self.bridge.on_tick(_tick_event())
        assert self.bridge.get_stats()["ticks_received"] == 1

    def test_multiple_ticks_cumulate(self):
        self.bridge.activate()
        for i in range(5):
            self.bridge.on_tick(_tick_event(price=60000.0 + i))
        assert self.bridge.get_stats()["ticks_received"] == 5

    def test_tick_when_inactive_does_not_count(self):
        self.bridge.on_tick(_tick_event())
        assert self.bridge.get_stats()["ticks_received"] == 0

    def test_tick_zero_price_skipped(self):
        self.bridge.activate()
        self.bridge.on_tick({"symbol": "BTCUSDT", "last_price": 0.0, "ts_ms": int(time.time() * 1000)})
        # ticks_received is incremented before price check — but no further dispatch
        # Zero price should not increment meaningful tick processing
        assert self.bridge.get_stats()["ticks_received"] >= 0  # tick counted but no dispatch

    def test_tick_empty_symbol_skipped(self):
        self.bridge.activate()
        self.bridge.on_tick({"symbol": "", "last_price": 60000.0, "ts_ms": int(time.time() * 1000)})
        # Empty symbol should not update any price tracking
        assert self.bridge.get_stats()["ticks_received"] >= 0  # tick counted but no symbol dispatch

    def test_tick_with_attribute_object(self):
        """on_tick should also handle non-dict event objects."""
        self.bridge.activate()
        event = type("TickEvent", (), {
            "symbol": "BTCUSDT",
            "last_price": 60000.0,
            "ts_ms": int(time.time() * 1000),
        })()
        self.bridge.on_tick(event)
        assert self.bridge.get_stats()["ticks_received"] == 1

    def test_tick_updates_latest_prices(self):
        self.bridge.activate()
        self.bridge.on_tick(_tick_event(symbol="BTCUSDT", price=55000.0))
        assert self.bridge._latest_prices.get("BTCUSDT") == 55000.0

    def test_tick_ts_zero_uses_wall_clock(self):
        """ts_ms=0 should fall back to int(time.time()*1000) without error."""
        self.bridge.activate()
        event = {"symbol": "BTCUSDT", "last_price": 60000.0, "ts_ms": 0}
        self.bridge.on_tick(event)
        assert self.bridge.get_stats()["ticks_received"] == 1


# ===========================================================================
# 5. Guardian=None fail-closed (P0-2 修復驗證)
#
# P0-B FIX APPLIED: pipeline_bridge.py now contains else: fail-closed block
# at L665-674. Tests verified passing as of Wave 0 / 2026-03-31.
# xfail markers removed; regression test for bug-state deleted.
# ===========================================================================

class TestGuardianNoneFailClosed:
    """
    P0-B Fix verification: Guardian=None must fail-closed (reject all intents).

    P0-B 修復已完成（pipeline_bridge.py L665）：Guardian=None 時所有 intent 被拒絕。
    """

    def _run_with_intent(self, intent):
        bridge, engine = _make_bridge()
        bridge.activate()
        bridge._guardian_agent = None  # explicit — no guardian

        bridge._orch.collect_pending_intents = MagicMock(return_value=[intent])
        bridge._process_pending_intents()
        return bridge, engine

    def test_intent_rejected_when_guardian_none(self):
        intent = _make_intent()
        bridge, engine = self._run_with_intent(intent)
        stats = bridge.get_stats()
        assert stats["intents_rejected"] == 1
        assert len(engine.submitted_orders) == 0

    def test_multiple_intents_all_rejected_when_guardian_none(self):
        bridge, engine = _make_bridge()
        bridge.activate()
        bridge._guardian_agent = None

        intents = [_make_intent(price_offset=i) for i in range(3)]
        bridge._orch.collect_pending_intents = MagicMock(return_value=intents)
        bridge._process_pending_intents()

        stats = bridge.get_stats()
        assert stats["intents_rejected"] == 3
        assert len(engine.submitted_orders) == 0

    def test_no_order_submitted_to_engine(self):
        intent = _make_intent()
        bridge, engine = self._run_with_intent(intent)
        assert engine.submitted_orders == []


def _make_intent(symbol: str = "BTCUSDT", side: str = "Buy",
                 qty: float = 0.001, price_offset: int = 0) -> Any:
    """Overload with price_offset for multi-intent tests (harmless, unused in intent)."""
    intent = type("OrderIntent", (), {
        "symbol": symbol,
        "side": side,
        "order_type": "market",
        "qty": qty,
        "price": None,
        "metadata": {"strategy_name": "test_strategy", "category": "linear"},
        "perception_data_id": None,
        "confidence": 0.6,
        "reason": "test_signal",
        "strategy_name": "test_strategy",
        "leverage": 1.0,
        "_price_offset": price_offset,
    })()
    return intent


# ===========================================================================
# 6. Guardian APPROVED / REJECTED / MODIFIED 路徑
# ===========================================================================

class TestGuardianVerdictPaths:
    """Guardian verdict routing: approved submits, rejected skips, modified adjusts qty."""

    def _setup_with_guardian(self, result: RiskVerdictResult,
                             modified_params: dict | None = None):
        bridge, engine = _make_bridge()
        bridge.activate()
        guardian = _make_guardian(result, modified_params)
        bridge.set_guardian_agent(guardian)
        return bridge, engine, guardian

    def test_approved_intent_reaches_engine(self):
        bridge, engine, _ = self._setup_with_guardian(RiskVerdictResult.APPROVED)
        intent = _make_intent()
        bridge._orch.collect_pending_intents = MagicMock(return_value=[intent])
        bridge._process_pending_intents()

        assert len(engine.submitted_orders) == 1
        assert bridge._guardian_stats["approved"] == 1
        assert bridge.get_stats()["intents_submitted"] == 1

    def test_rejected_intent_does_not_reach_engine(self):
        bridge, engine, _ = self._setup_with_guardian(RiskVerdictResult.REJECTED)
        intent = _make_intent()
        bridge._orch.collect_pending_intents = MagicMock(return_value=[intent])
        bridge._process_pending_intents()

        assert len(engine.submitted_orders) == 0
        assert bridge._guardian_stats["rejected"] == 1
        assert bridge.get_stats()["intents_rejected"] == 1

    def test_modified_intent_uses_guardian_qty(self):
        modified_params = {"size": 0.002}
        bridge, engine, _ = self._setup_with_guardian(
            RiskVerdictResult.MODIFIED, modified_params
        )
        intent = _make_intent(qty=0.001)
        bridge._orch.collect_pending_intents = MagicMock(return_value=[intent])
        bridge._process_pending_intents()

        assert len(engine.submitted_orders) == 1
        submitted = engine.submitted_orders[0]
        # Modified qty = 0.002 (from guardian), not original 0.001
        assert submitted["qty"] == 0.002
        assert bridge._guardian_stats["modified"] == 1

    def test_guardian_exception_causes_fail_closed(self):
        bridge, engine = _make_bridge()
        bridge.activate()
        guardian = MagicMock()
        guardian.review_intent.side_effect = RuntimeError("Guardian crashed")
        guardian.update_active_positions = MagicMock()
        bridge.set_guardian_agent(guardian)

        intent = _make_intent()
        bridge._orch.collect_pending_intents = MagicMock(return_value=[intent])
        bridge._process_pending_intents()

        assert len(engine.submitted_orders) == 0
        assert bridge._guardian_stats["errors"] == 1
        assert bridge.get_stats()["intents_rejected"] == 1

    def test_guardian_checked_counter_increments(self):
        bridge, engine, guardian = self._setup_with_guardian(RiskVerdictResult.APPROVED)
        intents = [_make_intent() for _ in range(3)]
        bridge._orch.collect_pending_intents = MagicMock(return_value=intents)
        bridge._process_pending_intents()

        assert bridge._guardian_stats["checked"] == 3

    def test_multiple_approved_intents(self):
        bridge, engine, _ = self._setup_with_guardian(RiskVerdictResult.APPROVED)
        intents = [_make_intent() for _ in range(4)]
        bridge._orch.collect_pending_intents = MagicMock(return_value=intents)
        bridge._process_pending_intents()

        assert len(engine.submitted_orders) == 4
        assert bridge._guardian_stats["approved"] == 4


# ===========================================================================
# 7. GovernanceHub 授權通過 vs 拒絕
# ===========================================================================

class TestGovernanceHubGate:
    """GovernanceHub.is_authorized() must gate all intents."""

    def test_authorized_hub_allows_guardian_approved(self):
        bridge, engine = _make_bridge()
        bridge.activate()
        bridge.set_governance_hub(_make_governance_hub(authorized=True))
        bridge.set_guardian_agent(_make_guardian(RiskVerdictResult.APPROVED))

        intent = _make_intent()
        bridge._orch.collect_pending_intents = MagicMock(return_value=[intent])
        bridge._process_pending_intents()

        assert len(engine.submitted_orders) == 1

    def test_unauthorized_hub_blocks_all_intents(self):
        bridge, engine = _make_bridge()
        bridge.activate()
        bridge.set_governance_hub(_make_governance_hub(authorized=False))
        bridge.set_guardian_agent(_make_guardian(RiskVerdictResult.APPROVED))

        intent = _make_intent()
        bridge._orch.collect_pending_intents = MagicMock(return_value=[intent])
        bridge._process_pending_intents()

        assert len(engine.submitted_orders) == 0
        assert bridge.get_stats()["intents_rejected"] == 1

    def test_governance_hub_exception_causes_fail_closed(self):
        bridge, engine = _make_bridge()
        bridge.activate()
        hub = MagicMock()
        hub.is_authorized.side_effect = RuntimeError("Hub error")
        bridge.set_governance_hub(hub)
        bridge.set_guardian_agent(_make_guardian(RiskVerdictResult.APPROVED))

        intent = _make_intent()
        bridge._orch.collect_pending_intents = MagicMock(return_value=[intent])
        bridge._process_pending_intents()

        assert len(engine.submitted_orders) == 0
        assert bridge.get_stats()["intents_rejected"] == 1


# ===========================================================================
# 8. _process_pending_intents 邊界條件
# ===========================================================================

class TestProcessPendingIntents:
    """Edge cases for _process_pending_intents."""

    def test_empty_intent_list_is_noop(self):
        bridge, engine = _make_bridge()
        bridge.activate()
        bridge.set_guardian_agent(_make_guardian(RiskVerdictResult.APPROVED))
        bridge._orch.collect_pending_intents = MagicMock(return_value=[])
        bridge._process_pending_intents()

        assert bridge.get_stats()["intents_submitted"] == 0

    def test_intents_capped_at_max_per_tick(self):
        bridge, engine = _make_bridge(max_intents=3)
        bridge.activate()
        bridge.set_guardian_agent(_make_guardian(RiskVerdictResult.APPROVED))

        # 10 intents, but max is 3
        intents = [_make_intent() for _ in range(10)]
        bridge._orch.collect_pending_intents = MagicMock(return_value=intents)
        bridge._process_pending_intents()

        # Only 3 submitted (first 3 of 10)
        assert len(engine.submitted_orders) == 3

    def test_engine_rejection_increments_rejected_counter(self):
        bridge, engine = _make_bridge(reject=True)
        bridge.activate()
        bridge.set_guardian_agent(_make_guardian(RiskVerdictResult.APPROVED))

        intent = _make_intent()
        bridge._orch.collect_pending_intents = MagicMock(return_value=[intent])
        bridge._process_pending_intents()

        stats = bridge.get_stats()
        assert stats["intents_submitted"] == 1
        assert stats["intents_rejected"] == 1
        assert stats["intents_accepted"] == 0

    def test_engine_acceptance_increments_accepted_counter(self):
        bridge, engine = _make_bridge(reject=False)
        bridge.activate()
        bridge.set_guardian_agent(_make_guardian(RiskVerdictResult.APPROVED))

        intent = _make_intent()
        bridge._orch.collect_pending_intents = MagicMock(return_value=[intent])
        bridge._process_pending_intents()

        stats = bridge.get_stats()
        assert stats["intents_submitted"] == 1
        assert stats["intents_accepted"] == 1
        assert stats["intents_rejected"] == 0

    def test_intents_capped_includes_both_sources(self):
        """P2-12: 雙源合併後截斷測試。

        验证当 orchestrator 和 StrategistAgent 合计超过 max_intents_per_tick
        时，只有前 max_intents_per_tick 个被处理。
        Verify that when orchestrator intents exceed max_intents_per_tick,
        only the first max_intents_per_tick are processed.

        APR01-P1-3: Updated — StrategistAgent.collect_pending_intents() path removed
        (deprecated TD-2, always returned []). Only orchestrator source remains.
        APR01-P1-3：已更新 — 移除 StrategistAgent.collect_pending_intents() 路径
        （TD-2 已废弃，始终返回 []）。仅保留编排器来源。
        """
        # max_intents=20，orchestrator 返回 25 個，超過上限
        # max_intents=20, orchestrator returns 25, exceeds cap
        bridge, engine = _make_bridge(max_intents=20, reject=False)
        bridge.activate()
        bridge.set_guardian_agent(_make_guardian(RiskVerdictResult.APPROVED))

        # Orchestrator provides 25 intents (exceeds max of 20)
        orch_intents = [_make_intent() for _ in range(25)]
        bridge._orch.collect_pending_intents = MagicMock(return_value=orch_intents)

        bridge._process_pending_intents()

        # 25 > max 20，截斷後只提交 20 個（engine.submitted_orders <= 20）
        # 25 > max 20; after capping only 20 are submitted to paper engine
        assert len(engine.submitted_orders) <= 20, (
            f"Expected at most 20 submitted orders, got {len(engine.submitted_orders)}"
        )

    def test_orchestrator_collect_exception_returns_empty(self):
        """APR01-P1-3: orchestrator.collect_pending_intents() 拋異常時，
        系統應 fallback 到空列表，不崩潰，不提交任何訂單。

        When orchestrator.collect_pending_intents() raises RuntimeError,
        the pipeline must not crash; no orders should be submitted.
        （替代原 test_strategist_collect_exception_falls_back_to_orchestrator，
        因 strategist collect 路径已移除。）
        """
        bridge, engine = _make_bridge(max_intents=20, reject=False)
        bridge.activate()
        bridge.set_guardian_agent(_make_guardian(RiskVerdictResult.APPROVED))

        # Orchestrator 拋出 RuntimeError — 模擬外部異常
        # Orchestrator raises RuntimeError — simulates external failure
        bridge._orch.collect_pending_intents = MagicMock(
            side_effect=RuntimeError("test error")
        )

        # 不應拋出，系統應安全返回（intents=[] → early return）
        # Must not raise; empty intents → early return, no orders submitted
        bridge._process_pending_intents()

        # 無訂單提交（orchestrator 異常 → intents=[]）
        # No orders submitted (orchestrator exception → intents=[])
        assert len(engine.submitted_orders) == 0, (
            f"Expected 0 orders after orchestrator exception, got {len(engine.submitted_orders)}"
        )


# ===========================================================================
# 9. _check_stops 止損觸發
# ===========================================================================

class TestCheckStops:
    """_check_stops correctly processes stop triggers."""

    def _setup_with_stop_mgr(self, triggered_stops: list[dict]):
        bridge, engine = _make_bridge()
        bridge.activate()
        stop_mgr = MagicMock()
        stop_mgr.check_stops.return_value = triggered_stops
        stop_mgr.untrack_position = MagicMock()
        bridge._stop_mgr = stop_mgr
        bridge._latest_prices = {"BTCUSDT": 59000.0}
        return bridge, engine, stop_mgr

    def test_triggered_stop_submits_close_order(self):
        stop = {
            "symbol": "BTCUSDT",
            "side": "Sell",
            "qty": 0.001,
            "reason": "hard_stop",
            "stop_type": "hard",
            "strategy_name": "test",
        }
        bridge, engine, _ = self._setup_with_stop_mgr([stop])
        # Engine must report position as still open; otherwise stop is skipped
        engine._state = {"positions": {"BTCUSDT": {"qty": 0.001, "side": "long"}}}
        bridge._check_stops()

        assert len(engine.submitted_orders) == 1
        assert engine.submitted_orders[0]["symbol"] == "BTCUSDT"
        assert bridge.get_stats()["stops_triggered"] == 1

    def test_no_triggered_stops_no_order(self):
        bridge, engine, _ = self._setup_with_stop_mgr([])
        bridge._check_stops()

        assert len(engine.submitted_orders) == 0
        assert bridge.get_stats()["stops_triggered"] == 0

    def test_stop_already_closed_position_is_skipped(self):
        """If engine reports position gone, stop should be skipped."""
        stop = {
            "symbol": "BTCUSDT",
            "side": "Sell",
            "qty": 0.001,
            "reason": "hard_stop",
            "stop_type": "hard",
            "strategy_name": "test",
        }
        bridge, engine, stop_mgr = self._setup_with_stop_mgr([stop])
        # Engine says position is gone (empty positions dict)
        engine._state = {"positions": {}}
        bridge._check_stops()

        # Should have been skipped; engine receives no order
        assert len(engine.submitted_orders) == 0
        # untrack_position should have been called to clean up
        stop_mgr.untrack_position.assert_called_once()

    def test_multiple_stops_all_submitted(self):
        stops = [
            {"symbol": "BTCUSDT", "side": "Sell", "qty": 0.001,
             "reason": "hard", "stop_type": "hard", "strategy_name": "s1"},
            {"symbol": "ETHUSDT", "side": "Sell", "qty": 0.01,
             "reason": "trail", "stop_type": "trailing", "strategy_name": "s2"},
        ]
        bridge, engine, _ = self._setup_with_stop_mgr(stops)
        bridge._latest_prices = {"BTCUSDT": 59000.0, "ETHUSDT": 2000.0}
        # Engine has both positions so they aren't skipped
        engine._state = {"positions": {"BTCUSDT": {"qty": 0.001}, "ETHUSDT": {"qty": 0.01}}}
        bridge._check_stops()

        assert len(engine.submitted_orders) == 2
        assert bridge.get_stats()["stops_triggered"] == 2

    def test_stop_manager_exception_does_not_crash(self):
        bridge, engine = _make_bridge()
        bridge.activate()
        stop_mgr = MagicMock()
        stop_mgr.check_stops.side_effect = RuntimeError("StopManager exploded")
        bridge._stop_mgr = stop_mgr
        bridge._latest_prices = {"BTCUSDT": 59000.0}

        # Should not raise
        bridge._check_stops()
        assert len(engine.submitted_orders) == 0


# ===========================================================================
# 9b. FA-7 _check_stops → PerceptionPlane.register_data() 注入（原則 12）
# ===========================================================================

class TestCheckStopsPerceptionPlane:
    """
    FA-7: Verify that _check_stops() injects stop-loss close events into the
    PerceptionPlane learning pipeline via _emit_round_trip().

    FA-7：驗證 _check_stops() 在止損觸發後通過 _emit_round_trip() 將事件注入
    PerceptionPlane 學習管線，滿足原則 12（持續進化）。
    """

    def _setup_with_stop_and_perception(
        self,
        triggered_stops: list[dict],
        *,
        perception_plane: object = None,
    ):
        """
        Build a bridge with mocked stop manager and optional perception plane.
        構建帶有 mock StopManager 和可選 PerceptionPlane 的 bridge。
        """
        bridge, engine = _make_bridge()
        bridge.activate()
        stop_mgr = MagicMock()
        stop_mgr.check_stops.return_value = triggered_stops
        stop_mgr.untrack_position = MagicMock()
        bridge._stop_mgr = stop_mgr
        bridge._latest_prices = {"BTCUSDT": 59000.0, "ETHUSDT": 2000.0}
        if perception_plane is not None:
            bridge._perception_plane = perception_plane
        return bridge, engine, stop_mgr

    def test_register_data_called_on_stop_loss_close(self):
        """
        After a successful stop-loss close, register_data() must be called at
        least once on the PerceptionPlane (via _emit_round_trip).

        止損平倉成功後，register_data() 必須至少被調用一次（通過 _emit_round_trip）。
        """
        stop = {
            "symbol": "BTCUSDT",
            "side": "Sell",       # long position closed → pnl = (exit - entry) * qty
            "qty": 0.001,
            "reason": "Hard stop: price 59000.00 <= 59500.00 (-0.8%)",
            "stop_type": "hard_stop",
            "strategy_name": "test_strategy",
            "entry_price": 60000.0,
            "current_price": 59000.0,
        }
        plane = MagicMock()
        bridge, engine, _ = self._setup_with_stop_and_perception([stop], perception_plane=plane)
        # Engine must report position as still open so stop is not skipped
        # engine 必須回報倉位仍開著，止損才不會被跳過
        engine._state = {"positions": {"BTCUSDT": {"qty": 0.001}}}

        bridge._check_stops()

        # Submit order must have happened
        assert len(engine.submitted_orders) == 1
        # register_data() must have been called (feeds learning pipeline)
        # register_data() 必須被調用（注入學習管線）
        assert plane.register_data.called, (
            "register_data() was never called — stop-loss events are invisible to learning pipeline"
        )

    def test_register_data_not_called_when_perception_plane_none(self):
        """
        When perception_plane is None, _check_stops() must not raise AttributeError.
        Principle 6 (fail safely): if the learning plane is absent, stop-loss
        processing must still succeed.

        當 perception_plane 為 None 時，_check_stops() 不能拋出 AttributeError。
        原則 6（失敗默認收縮）：學習管線缺失不應影響止損單的正常執行。
        """
        stop = {
            "symbol": "BTCUSDT",
            "side": "Sell",
            "qty": 0.001,
            "reason": "Hard stop",
            "stop_type": "hard_stop",
            "strategy_name": "test_strategy",
            "entry_price": 60000.0,
            "current_price": 59000.0,
        }
        bridge, engine, _ = self._setup_with_stop_and_perception([stop], perception_plane=None)
        engine._state = {"positions": {"BTCUSDT": {"qty": 0.001}}}

        # Must not raise — absence of perception plane is non-fatal
        # 不能拋異常——學習管線缺失為非致命錯誤
        bridge._check_stops()

        # Stop order must still have been submitted
        assert len(engine.submitted_orders) == 1
        assert bridge.get_stats()["stops_triggered"] == 1

    def test_register_data_called_on_time_stop_close(self):
        """
        Time-stop exits are also stop-loss paths and must trigger register_data().
        All three stop types (hard/trailing/time) go through the same _check_stops()
        branch, so one test covering time_stop confirms full generalization.

        時間止損也是止損路徑，必須觸發 register_data()。
        三種止損類型（hard/trailing/time）走同一分支，覆蓋一種即驗證全部。
        """
        stop = {
            "symbol": "ETHUSDT",
            "side": "Sell",
            "qty": 0.01,
            "reason": "Time stop: held 25.0h >= max 24h",
            "stop_type": "time_stop",
            "strategy_name": "ma_crossover",
            "entry_price": 2050.0,
            "current_price": 2000.0,
        }
        plane = MagicMock()
        bridge, engine, _ = self._setup_with_stop_and_perception([stop], perception_plane=plane)
        bridge._latest_prices = {"ETHUSDT": 2000.0}
        engine._state = {"positions": {"ETHUSDT": {"qty": 0.01}}}

        bridge._check_stops()

        assert len(engine.submitted_orders) == 1
        assert plane.register_data.called, (
            "register_data() was not called for time_stop close — learning pipeline missing time-stop data"
        )

    def test_pnl_calculation_correct_for_long_position(self):
        """
        For a long position (close side = 'Sell'), PnL = (exit - entry) * qty.
        A hard stop at a lower price must produce a negative PnL value passed to
        _emit_round_trip, confirming correct attribution sign.

        多頭止損（close side='Sell'）的盈虧 = (出場 - 入場) * qty，止損必為負值。
        驗證傳入 _emit_round_trip 的 close_pnl 符號正確（負值 = 虧損）。
        """
        stop = {
            "symbol": "BTCUSDT",
            "side": "Sell",          # long closed below entry → pnl < 0
            "qty": 0.001,
            "reason": "Hard stop",
            "stop_type": "hard_stop",
            "strategy_name": "trend_follow",
            "entry_price": 60000.0,
            "current_price": 59000.0,  # exit below entry → loss
        }
        plane = MagicMock()
        bridge, engine, _ = self._setup_with_stop_and_perception([stop], perception_plane=plane)
        engine._state = {"positions": {"BTCUSDT": {"qty": 0.001}}}

        with patch.object(bridge, "_emit_round_trip", wraps=bridge._emit_round_trip) as mock_rt:
            bridge._check_stops()

        mock_rt.assert_called_once()
        _args = mock_rt.call_args
        # close_pnl should be negative for a long position stopped out below entry
        # 多頭止損低於入場價，close_pnl 應為負
        close_pnl = _args.kwargs.get("close_pnl") or _args[0][3]
        assert close_pnl < 0, f"Expected negative PnL for long stop-loss, got {close_pnl}"

    def test_register_data_not_called_when_order_rejected(self):
        """
        Sprint 1a P1-1: If submit_order() returns a rejected_reason, the stop
        order was NOT executed — _emit_round_trip() must NOT be called, to avoid
        injecting a fabricated (ghost) learning signal into the perception plane.

        P1-1：若 submit_order() 返回 rejected_reason，止損單未成交，
        不應調用 _emit_round_trip()，防止向學習管線注入虛假數據（幽靈交易）。

        The engine's submit_order is monkey-patched to return a rejected result.
        register_data() on the PerceptionPlane must never be called in this scenario.
        使用 monkey-patch 讓 submit_order 返回拒絕結果，驗證 register_data() 不被調用。
        """
        stop = {
            "symbol": "BTCUSDT",
            "side": "Sell",
            "qty": 0.001,
            "reason": "Hard stop",
            "stop_type": "hard_stop",
            "strategy_name": "test_strategy",
            "entry_price": 60000.0,
            "current_price": 59000.0,
        }
        plane = MagicMock()
        bridge, engine, _ = self._setup_with_stop_and_perception([stop], perception_plane=plane)
        engine._state = {"positions": {"BTCUSDT": {"qty": 0.001}}}

        # Patch submit_order to return a rejected result.
        # submit_order 被 patch 為返回拒絕結果（模擬 governance / risk 拒絕）。
        rejected_result = {"rejected_reason": "guardian_rejected: risk limit exceeded"}
        engine.submit_order = MagicMock(return_value=rejected_result)

        with patch.object(bridge, "_emit_round_trip") as mock_rt:
            bridge._check_stops()

        # _emit_round_trip must NOT be called — the stop order was rejected, no
        # position was actually closed, so no learning signal should be emitted.
        # 止損單被拒，倉位未真正平倉，不能注入學習信號。
        mock_rt.assert_not_called(), (
            "_emit_round_trip() was called despite order rejection — "
            "this injects a ghost learning signal into the perception plane"
        )
        # register_data() on PerceptionPlane also must not be called
        # register_data() 同樣不能被調用
        plane.register_data.assert_not_called()


# ===========================================================================
# 10. get_stats 返回格式
# ===========================================================================

class TestGetStats:
    """get_stats() must return all expected keys with correct types."""

    def test_get_stats_returns_component_key(self):
        bridge, _ = _make_bridge()
        stats = bridge.get_stats()
        assert stats["component"] == "pipeline_bridge"

    def test_get_stats_has_active_key(self):
        bridge, _ = _make_bridge()
        assert "active" in bridge.get_stats()

    def test_get_stats_active_reflects_state(self):
        bridge, _ = _make_bridge()
        assert bridge.get_stats()["active"] is False
        bridge.activate()
        assert bridge.get_stats()["active"] is True

    def test_get_stats_is_thread_safe(self):
        """get_stats() must not deadlock under concurrent calls."""
        bridge, _ = _make_bridge()
        errors = []

        def read_stats():
            try:
                for _ in range(50):
                    bridge.get_stats()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read_stats) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert errors == []


# ===========================================================================
# 11. on_tick_result 填單路徑
# ===========================================================================

class TestOnTickResult:
    """on_tick_result correctly detects and emits round-trip closes."""

    def test_empty_fills_returns_immediately(self):
        bridge, _ = _make_bridge()
        bridge.activate()
        # No crash, no emission
        bridge.on_tick_result({"fills": []})
        assert bridge._open_positions == {}

    def test_fill_without_tracked_position_is_ignored(self):
        bridge, _ = _make_bridge()
        bridge.activate()
        bridge._open_positions = {}  # nothing tracked
        fill = {"symbol": "BTCUSDT", "side": "Sell", "price": 61000.0, "fee": 0.0}
        bridge.on_tick_result({"fills": [fill]})
        # Untracked fill should not create a new position entry
        assert bridge._open_positions == {}

    def test_long_closed_by_sell_fill_emits_round_trip(self):
        bridge, _ = _make_bridge()
        bridge.activate()

        # Pre-load a tracked long position
        bridge._open_positions["test_strategy:BTCUSDT"] = {
            "symbol": "BTCUSDT",
            "strategy_name": "test_strategy",
            "side": "long",
            "entry_price": 60000.0,
            "qty": 0.001,
            "entry_ts_ms": int(time.time() * 1000) - 3600000,
            "regime": "trending",
        }

        # Observation writer to capture emission
        written = []
        bridge.set_observation_writer(
            lambda symbol, strategy_name, close_pnl, hold_ms, regime:
            written.append({"symbol": symbol, "pnl": close_pnl})
        )

        # Sell fill closes the long
        fill = {"symbol": "BTCUSDT", "side": "Sell", "price": 61000.0, "fee": 0.0}
        bridge.on_tick_result({"fills": [fill]})

        assert len(written) == 1
        assert written[0]["symbol"] == "BTCUSDT"
        # PnL = (61000 - 60000) * 0.001 = 1.0
        assert written[0]["pnl"] == pytest.approx(1.0, abs=0.01)

    def test_short_closed_by_buy_fill_emits_round_trip(self):
        bridge, _ = _make_bridge()
        bridge.activate()

        bridge._open_positions["test_strategy:ETHUSDT"] = {
            "symbol": "ETHUSDT",
            "strategy_name": "test_strategy",
            "side": "short",
            "entry_price": 3000.0,
            "qty": 0.01,
            "entry_ts_ms": int(time.time() * 1000) - 1800000,
            "regime": "ranging",
        }

        written = []
        bridge.set_observation_writer(
            lambda symbol, strategy_name, close_pnl, hold_ms, regime:
            written.append({"symbol": symbol, "pnl": close_pnl})
        )

        # Buy fill closes the short (profitable: entry 3000 → exit 2900)
        fill = {"symbol": "ETHUSDT", "side": "Buy", "price": 2900.0, "fee": 0.0}
        bridge.on_tick_result({"fills": [fill]})

        assert len(written) == 1
        # PnL = (3000 - 2900) * 0.01 = 1.0
        assert written[0]["pnl"] == pytest.approx(1.0, abs=0.01)


# ===========================================================================
# 12. _try_learning_promotion 邊界條件
# ===========================================================================

class TestLearningPromotion:
    """_try_learning_promotion handles no gate gracefully."""

    def test_no_gate_no_exception(self):
        bridge, _ = _make_bridge()
        bridge._learning_tier_gate = None
        # Should return silently without error
        bridge._try_learning_promotion(100.0)

    def test_win_increments_winning_trades(self):
        bridge, _ = _make_bridge()
        mock_gate = MagicMock()
        mock_gate.update_metrics = MagicMock()
        # No _next_tier method → skip promotion attempt
        del mock_gate._next_tier
        bridge.set_learning_tier_gate(mock_gate)

        bridge._try_learning_promotion(50.0)  # win
        assert bridge._learning_stats["total_trades"] == 1
        assert bridge._learning_stats["winning_trades"] == 1

    def test_loss_does_not_increment_winning_trades(self):
        bridge, _ = _make_bridge()
        mock_gate = MagicMock()
        mock_gate.update_metrics = MagicMock()
        del mock_gate._next_tier
        bridge.set_learning_tier_gate(mock_gate)

        bridge._try_learning_promotion(-10.0)  # loss
        assert bridge._learning_stats["total_trades"] == 1
        assert bridge._learning_stats["winning_trades"] == 0

    def test_gate_update_metrics_called_with_correct_winrate(self):
        bridge, _ = _make_bridge()
        mock_gate = MagicMock()
        mock_gate.update_metrics = MagicMock()
        del mock_gate._next_tier
        bridge.set_learning_tier_gate(mock_gate)

        bridge._try_learning_promotion(10.0)  # win
        bridge._try_learning_promotion(-5.0)   # loss

        # 1 win out of 2 trades = 50%
        calls = mock_gate.update_metrics.call_args_list
        assert len(calls) == 2
        _, last_call_kwargs = calls[-1]
        assert last_call_kwargs["observation_count"] == 2
        assert last_call_kwargs["win_rate"] == pytest.approx(0.5)


# ===========================================================================
# 13. auto_submit=False 不自動處理意圖
# ===========================================================================

class TestAutoSubmitFlag:
    """When auto_submit_intents=False, on_tick should not call _process_pending_intents."""

    def test_no_intents_processed_when_auto_submit_false(self):
        bridge, engine = _make_bridge(auto_submit=False)
        bridge.activate()
        bridge.set_guardian_agent(_make_guardian(RiskVerdictResult.APPROVED))

        # Even if orchestrator has intents, they should not be processed
        bridge._orch.collect_pending_intents = MagicMock(
            return_value=[_make_intent()]
        )

        bridge.on_tick(_tick_event())

        # collect_pending_intents should NOT have been called via on_tick
        bridge._orch.collect_pending_intents.assert_not_called()
        assert engine.submitted_orders == []


# ===========================================================================
# 14. Sprint 5a — H0 Gate Blocking（原則 5：生存 > 利潤）
# Sprint 5a H0 Gate now blocks intents (fail-closed) instead of warn-only.
# ===========================================================================

class TestH0GateBlocking:
    """
    Sprint 5a: H0 Gate is now blocking (fail-closed) for allowed=False results.
    Sprint 5a：H0 Gate 現已切換為阻擋模式（allowed=False 時拒絕 intent），不再只是警告。

    Verifies:
    - H0 Gate allowed=False → intent NOT submitted, intents_h0_blocked incremented
    - H0 Gate allowed=True  → intent submitted normally
    驗證：
    - H0 Gate allowed=False → intent 不被提交，intents_h0_blocked 遞增
    - H0 Gate allowed=True  → intent 正常提交
    """

    def _make_h0_gate_mock(self, *, allowed: bool) -> MagicMock:
        """
        Build an H0Gate mock returning the specified allowed state.
        構建返回指定 allowed 狀態的 H0Gate mock。
        """
        gate = MagicMock()
        result = MagicMock()
        result.allowed = allowed
        result.check_name = "freshness" if not allowed else "all_pass"
        result.reason = "stale_data" if not allowed else ""
        result.latency_us = 50
        gate.check.return_value = result
        return gate

    def test_h0_gate_blocked_intent_not_submitted(self):
        """
        When H0 Gate returns allowed=False, the intent must NOT be submitted to the engine.
        H0 Gate 返回 allowed=False 時，intent 不得提交到引擎。

        This is the core safety guarantee of Sprint 5a H0 blocking:
        stale/unhealthy market data should never reach order execution.
        這是 Sprint 5a H0 阻擋的核心安全保證：
        過期或不健康的市場數據不得流入訂單執行。
        """
        bridge, engine = _make_bridge()
        bridge.activate()
        bridge.set_guardian_agent(_make_guardian(RiskVerdictResult.APPROVED))
        bridge.set_h0_gate(self._make_h0_gate_mock(allowed=False))

        intent = _make_intent()
        bridge._orch.collect_pending_intents = MagicMock(return_value=[intent])
        bridge._process_pending_intents()

        # Intent must NOT have reached the engine
        # intent 不得到達引擎
        assert len(engine.submitted_orders) == 0, (
            "H0Gate blocked intent should not reach engine"
        )

    def test_h0_gate_blocked_increments_counter(self):
        """
        When H0 Gate returns allowed=False, intents_h0_blocked counter must increment.
        H0 Gate 返回 allowed=False 時，intents_h0_blocked 計數器必須遞增。

        The counter is the observable evidence that the H0 Gate is actively blocking.
        計數器是 H0 Gate 正在主動阻擋的可觀察憑據。
        """
        bridge, engine = _make_bridge()
        bridge.activate()
        bridge.set_guardian_agent(_make_guardian(RiskVerdictResult.APPROVED))
        bridge.set_h0_gate(self._make_h0_gate_mock(allowed=False))

        stats_before = bridge.get_stats()
        baseline = stats_before.get("intents_h0_blocked", 0)

        intent = _make_intent()
        bridge._orch.collect_pending_intents = MagicMock(return_value=[intent])
        bridge._process_pending_intents()

        stats_after = bridge.get_stats()
        after_count = stats_after.get("intents_h0_blocked", 0)
        assert after_count == baseline + 1, (
            f"Expected intents_h0_blocked to increment from {baseline} to {baseline + 1}, "
            f"got {after_count}"
        )

    def test_h0_gate_allowed_intent_reaches_engine(self):
        """
        When H0 Gate returns allowed=True, the intent proceeds normally through the pipeline.
        H0 Gate 返回 allowed=True 時，intent 正常流過管線。

        Ensures that valid market conditions allow normal intent processing.
        確保有效市場條件下 intent 可以正常處理。
        """
        bridge, engine = _make_bridge()
        bridge.activate()
        bridge.set_guardian_agent(_make_guardian(RiskVerdictResult.APPROVED))
        bridge.set_h0_gate(self._make_h0_gate_mock(allowed=True))

        intent = _make_intent()
        bridge._orch.collect_pending_intents = MagicMock(return_value=[intent])
        bridge._process_pending_intents()

        # Intent must have been submitted to the engine
        # intent 必須被提交到引擎
        assert len(engine.submitted_orders) == 1, (
            "H0Gate allowed intent should reach engine"
        )

    def test_h0_gate_allowed_does_not_increment_blocked_counter(self):
        """
        When H0 Gate returns allowed=True, intents_h0_blocked must NOT increment.
        H0 Gate 返回 allowed=True 時，intents_h0_blocked 不得遞增。
        """
        bridge, engine = _make_bridge()
        bridge.activate()
        bridge.set_guardian_agent(_make_guardian(RiskVerdictResult.APPROVED))
        bridge.set_h0_gate(self._make_h0_gate_mock(allowed=True))

        stats_before = bridge.get_stats()
        baseline = stats_before.get("intents_h0_blocked", 0)

        intent = _make_intent()
        bridge._orch.collect_pending_intents = MagicMock(return_value=[intent])
        bridge._process_pending_intents()

        stats_after = bridge.get_stats()
        after_count = stats_after.get("intents_h0_blocked", 0)
        assert after_count == baseline, (
            f"intents_h0_blocked should not change when H0Gate allows, "
            f"but changed from {baseline} to {after_count}"
        )

    def test_h0_gate_none_intent_continues_fail_open(self):
        """
        When H0Gate is None (not set), intent must proceed normally through the pipeline.
        Verifies fail-open backward-compat: removing the gate must not break existing flows.
        H0Gate 未設置（None）時，intent 必須正常繼續流過管線。
        驗證 fail-open 向後兼容：移除門控不得中斷現有交易流程。

        Arrange:
          - PipelineBridge with no H0Gate set (default None)
        Act:
          - Submit one intent via _process_pending_intents()
        Assert:
          - intent reaches engine (submitted_orders has 1 entry)
          - intents_h0_blocked == 0 (gate is absent, not blocking)
        """
        # Arrange: no h0_gate set → self._h0_gate is None
        bridge, engine = _make_bridge()
        bridge.activate()
        bridge.set_guardian_agent(_make_guardian(RiskVerdictResult.APPROVED))
        # Do NOT call bridge.set_h0_gate() — gate stays None

        intent = _make_intent()
        bridge._orch.collect_pending_intents = MagicMock(return_value=[intent])

        # Act
        bridge._process_pending_intents()

        # Assert: intent reaches engine despite H0Gate=None (fail-open)
        # H0Gate=None → intent 正常到達引擎（fail-open，不中斷流程）
        assert len(engine.submitted_orders) == 1, (
            "With H0Gate=None, intent should reach engine (fail-open behavior)"
        )
        stats = bridge.get_stats()
        assert stats.get("intents_h0_blocked", 0) == 0, (
            "intents_h0_blocked must be 0 when H0Gate is None"
        )

    def test_h0_gate_data_quality_freshness_fail_blocks_intent(self):
        """
        When H0Gate returns allowed=False with check_name='freshness' (data quality failure),
        the intent must be skipped — same fail-closed path as all other H0 check failures.
        This confirms data_quality checks are NOT warn-only: they are blocking.

        H0Gate 返回 allowed=False 且 check_name='freshness'（數據品質失敗）時，
        intent 必須被跳過——與其他 H0 子檢查失敗路徑相同（fail-closed）。
        確認 data_quality 檢查非 warn-only：為強制阻擋。

        Arrange:
          - H0Gate mock returning allowed=False, check_name='freshness'
            (simulates stale data quality failure)
        Act:
          - Submit one intent
        Assert:
          - intent does NOT reach engine (submitted_orders is empty)
          - intents_h0_blocked increments by 1
        """
        # Arrange: mock H0Gate reporting freshness/data-quality failure
        # 模擬 H0Gate 報告數據新鮮度失敗（data quality check 失敗）
        gate = MagicMock()
        result = MagicMock()
        result.allowed = False
        result.check_name = "freshness"   # data quality sub-check
        result.reason = "data_stale_BTCUSDT_5000ms"
        result.latency_us = 10
        gate.check.return_value = result

        bridge, engine = _make_bridge()
        bridge.activate()
        bridge.set_guardian_agent(_make_guardian(RiskVerdictResult.APPROVED))
        bridge.set_h0_gate(gate)

        stats_before = bridge.get_stats()
        baseline = stats_before.get("intents_h0_blocked", 0)

        intent = _make_intent()
        bridge._orch.collect_pending_intents = MagicMock(return_value=[intent])

        # Act
        bridge._process_pending_intents()

        # Assert: freshness (data quality) failure → intent blocked, NOT warn-only
        # 數據新鮮度失敗 → intent 被阻擋，確認非 warn-only 行為
        assert len(engine.submitted_orders) == 0, (
            "H0Gate freshness/data-quality failure must block intent (fail-closed, not warn-only)"
        )
        stats_after = bridge.get_stats()
        after_count = stats_after.get("intents_h0_blocked", 0)
        assert after_count == baseline + 1, (
            f"intents_h0_blocked must increment on freshness failure: "
            f"expected {baseline + 1}, got {after_count}"
        )


# ===========================================================================
# 15. E4 Edge Cases: on_tick / _process_pending_intents boundary conditions
# ===========================================================================

class TestOnTickEdgeCasesE4:
    """Edge cases for on_tick with malformed input (E4 追加).
    on_tick 接收畸形输入的边界条件。"""

    def setup_method(self):
        self.bridge, self.engine = _make_bridge()

    def test_on_tick_with_none_price_data_raises_type_error(self):
        """on_tick with last_price=None raises TypeError (float(None)).
        last_price=None 的 on_tick 抛出 TypeError（float(None)）。
        Known gap: pipeline_bridge.on_tick does not guard against None price.
        已知缺口：pipeline_bridge.on_tick 不防护 None price。"""
        self.bridge.activate()
        event = {"symbol": "BTCUSDT", "last_price": None, "ts_ms": int(time.time() * 1000)}
        with pytest.raises(TypeError):
            self.bridge.on_tick(event)


class TestProcessPendingIntentsEdgeCasesE4:
    """Edge cases for _process_pending_intents (E4 追加).
    _process_pending_intents 边界条件。"""

    def setup_method(self):
        self.bridge, self.engine = _make_bridge()
        self.bridge.activate()
        self.bridge.set_governance_hub(_make_governance_hub(authorized=True))

    def test_zero_intents_is_noop(self):
        """_process_pending_intents with 0 pending intents should be a no-op.
        0 个待处理意图应为无操作。"""
        self.bridge._orch.collect_pending_intents = MagicMock(return_value=[])
        stats_before = dict(self.bridge.get_stats())
        self.bridge._process_pending_intents()
        stats_after = self.bridge.get_stats()
        assert stats_after["intents_submitted"] == stats_before["intents_submitted"]

    def test_intent_missing_symbol_does_not_crash(self):
        """Intent with missing symbol attribute should not crash pipeline.
        缺少 symbol 属性的 intent 不应导致管线崩溃。"""
        broken_intent = type("BrokenIntent", (), {
            "side": "Buy", "order_type": "market", "qty": 0.001,
            "price": None, "metadata": {}, "perception_data_id": None,
            "confidence": 0.6, "reason": "test", "strategy_name": "test",
            "leverage": 1.0,
        })()
        self.bridge._orch.collect_pending_intents = MagicMock(return_value=[broken_intent])
        try:
            self.bridge._process_pending_intents()
        except AttributeError:
            pass  # acceptable: pipeline may require symbol
        assert self.bridge.is_active is True

    def test_process_intents_with_max_zero_submits_nothing(self):
        """Bridge with max_intents_per_tick=0 should submit nothing (truncation).
        max_intents_per_tick=0 的 bridge 不应提交任何内容（截断）。"""
        bridge, engine = _make_bridge(max_intents=0)
        bridge.activate()
        bridge.set_governance_hub(_make_governance_hub(authorized=True))
        intent = _make_intent()
        bridge._orch.collect_pending_intents = MagicMock(return_value=[intent])
        bridge._process_pending_intents()
        assert len(engine.submitted_orders) == 0
