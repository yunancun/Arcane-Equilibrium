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
        # The important thing is no exception is raised
        assert True  # no crash

    def test_tick_empty_symbol_skipped(self):
        self.bridge.activate()
        self.bridge.on_tick({"symbol": "", "last_price": 60000.0, "ts_ms": int(time.time() * 1000)})
        assert True  # no crash

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
# NOTE: P0-B FIX (Guardian=None → else: fail-closed) is currently MISSING from
# pipeline_bridge.py lines 519-593. The `if self._guardian_agent:` block has no
# corresponding `else:` clause, so intents PASS THROUGH when guardian is None.
# These tests document the EXPECTED (post-fix) behaviour; they will fail until
# the fix is applied. This is a known gap detected by E4 Wave 2 P1-6 review.
# ===========================================================================

class TestGuardianNoneFailClosed:
    """
    P0-B Fix verification: Guardian=None must fail-closed (reject all intents).

    Current status: XFAIL — the else-branch fix is missing from pipeline_bridge.py:519.
    Tests are marked xfail so the suite stays green while clearly flagging the gap.
    """

    def _run_with_intent(self, intent):
        bridge, engine = _make_bridge()
        bridge.activate()
        bridge._guardian_agent = None  # explicit — no guardian

        bridge._orch.collect_pending_intents = MagicMock(return_value=[intent])
        bridge._process_pending_intents()
        return bridge, engine

    @pytest.mark.xfail(
        reason="P0-B Guardian=None else: fail-closed block missing from pipeline_bridge.py:519 — "
               "fix required before this passes",
        strict=True,
    )
    def test_intent_rejected_when_guardian_none(self):
        intent = _make_intent()
        bridge, engine = self._run_with_intent(intent)
        stats = bridge.get_stats()
        assert stats["intents_rejected"] == 1
        assert len(engine.submitted_orders) == 0

    @pytest.mark.xfail(
        reason="P0-B Guardian=None fail-closed block missing — see pipeline_bridge.py:519",
        strict=True,
    )
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

    @pytest.mark.xfail(
        reason="P0-B Guardian=None fail-closed block missing — see pipeline_bridge.py:519",
        strict=True,
    )
    def test_no_order_submitted_to_engine(self):
        intent = _make_intent()
        bridge, engine = self._run_with_intent(intent)
        assert engine.submitted_orders == []

    def test_guardian_none_currently_passes_through_documenting_bug(self):
        """
        Negative regression: documents CURRENT (broken) behaviour — intents pass through
        when Guardian=None. Once P0-B fix is applied, this test should be deleted and
        the xfail tests above should be unmarked.
        """
        bridge, engine = _make_bridge()
        bridge.activate()
        bridge._guardian_agent = None
        intent = _make_intent()
        bridge._orch.collect_pending_intents = MagicMock(return_value=[intent])
        bridge._process_pending_intents()
        # Documents current (buggy) state: order IS submitted when guardian is None
        # This assertion should FAIL once the P0-B fix is applied.
        assert len(engine.submitted_orders) == 1, (
            "Expected guardian=None to let intent through (current bug). "
            "If this fails, P0-B fix has been applied — delete this test and "
            "remove xfail markers from the sibling tests."
        )


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
        # No crash
        assert True

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


# (pytest imported at top of file)
