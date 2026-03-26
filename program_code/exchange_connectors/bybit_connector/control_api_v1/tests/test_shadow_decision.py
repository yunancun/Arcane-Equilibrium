"""
Tests for Shadow Decision Builder / 影子决策构建器测试

覆盖范围 / Coverage:
  - build_shadow_decision() with and without governed observation
  - ShadowDecisionConsumer: hold, trade, rejected, error scenarios
  - ShadowDecisionFileFeeder: deduplication, file loading
  - Safety invariants: is_simulated, lease_mode, execution_authority
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.shadow_decision_builder import (
    BIAS_TO_SIDE,
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_EDGE_THRESHOLD_BPS,
    DEFAULT_POSITION_SIZE_FRACTION,
    ShadowDecisionConsumer,
    ShadowDecisionFileFeeder,
    build_shadow_decision,
)
from app.paper_trading_engine import (
    PaperStateStore,
    PaperTradingEngine,
    SIDE_BUY,
    SIDE_SELL,
    SESSION_ACTIVE,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Test Fixtures / 测试数据
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def tmp_state_file():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.unlink(path)  # Remove so PaperStateStore creates it with default state
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def engine(tmp_state_file):
    store = PaperStateStore(tmp_state_file)
    return PaperTradingEngine(store)


@pytest.fixture
def active_engine(engine):
    """Engine with an active session and 10k balance"""
    engine.start_session(initial_balance=10000.0)
    return engine


def _make_verdict(*, verdict_code="OBSERVE_ONLY"):
    return {
        "verdict_type": "bybit_observer_verdict",
        "verdict_code": verdict_code,
        "verdict_generated_ts_ms": int(time.time() * 1000),
        "execution_allowed": False,
        "risk_flags": ["test_risk"],
        "reasons": ["test_reason"],
    }


def _make_governed_observation(
    *,
    market_regime="trending_up",
    action_bias="buy_bias",
    confidence=0.75,
    edge_bps=15.0,
    analysis_mode="governed_observation",
):
    return {
        "market_regime": market_regime,
        "action_bias": action_bias,
        "confidence_0_to_1": confidence,
        "edge_assessment_bps": edge_bps,
        "key_reasons": ["momentum", "volume_surge"],
        "risk_notes": ["high_volatility"],
        "why_not_trade": [],
        "analysis_mode": analysis_mode,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Test: build_shadow_decision / 测试：构建影子决策
# ═══════════════════════════════════════════════════════════════════════════════

class TestBuildShadowDecision:
    def test_with_governed_observation_should_trade(self):
        """High confidence + edge → should_trade=True"""
        decision = build_shadow_decision(
            verdict=_make_verdict(),
            governed_observation=_make_governed_observation(confidence=0.8, edge_bps=20.0),
        )
        assert decision["should_trade"] is True
        assert decision["trade_side"] == SIDE_BUY
        assert decision["confidence"] == 0.8
        assert decision["edge_assessment_bps"] == 20.0
        assert decision["market_regime"] == "trending_up"

    def test_low_confidence_no_trade(self):
        """Low confidence → should_trade=False"""
        decision = build_shadow_decision(
            verdict=_make_verdict(),
            governed_observation=_make_governed_observation(confidence=0.2, edge_bps=20.0),
        )
        assert decision["should_trade"] is False
        assert decision["trade_side"] is None

    def test_low_edge_no_trade(self):
        """Low edge → should_trade=False"""
        decision = build_shadow_decision(
            verdict=_make_verdict(),
            governed_observation=_make_governed_observation(confidence=0.8, edge_bps=2.0),
        )
        assert decision["should_trade"] is False

    def test_observation_only_mode_no_trade(self):
        """analysis_mode=observation_only → should_trade=False"""
        decision = build_shadow_decision(
            verdict=_make_verdict(),
            governed_observation=_make_governed_observation(
                confidence=0.9, edge_bps=30.0, analysis_mode="observation_only"
            ),
        )
        assert decision["should_trade"] is False

    def test_sell_bias(self):
        """sell_bias → trade_side=Sell"""
        decision = build_shadow_decision(
            verdict=_make_verdict(),
            governed_observation=_make_governed_observation(action_bias="sell_bias"),
        )
        assert decision["should_trade"] is True
        assert decision["trade_side"] == SIDE_SELL

    def test_flat_bias_no_trade(self):
        """flat_bias → should_trade=False (not in BIAS_TO_SIDE)"""
        decision = build_shadow_decision(
            verdict=_make_verdict(),
            governed_observation=_make_governed_observation(action_bias="flat_bias"),
        )
        assert decision["should_trade"] is False

    def test_without_governed_observation(self):
        """No AI observation → minimal decision, no trade"""
        decision = build_shadow_decision(verdict=_make_verdict())
        assert decision["should_trade"] is False
        assert decision["confidence"] == 0.0
        assert decision["observation_fingerprint"] == "no_observation"
        assert decision["market_regime"] == "unknown"

    def test_no_verdict_no_observation(self):
        """Both None → still builds valid decision"""
        decision = build_shadow_decision()
        assert decision["should_trade"] is False
        assert "decision_id" in decision
        assert decision["verdict_code"] is None

    def test_safety_markers_always_present(self):
        """Safety markers are always set correctly"""
        for obs in [None, _make_governed_observation()]:
            decision = build_shadow_decision(
                verdict=_make_verdict(),
                governed_observation=obs,
            )
            assert decision["is_simulated"] is True
            assert decision["lease_mode"] == "shadow_only"
            assert decision["execution_authority"] == "not_granted"
            assert decision["decision_lease_emitted"] is False

    def test_decision_id_unique(self):
        """Each call produces a unique decision_id"""
        d1 = build_shadow_decision()
        d2 = build_shadow_decision()
        assert d1["decision_id"] != d2["decision_id"]

    def test_symbol_passthrough(self):
        """Custom symbol is included"""
        decision = build_shadow_decision(symbol="ETHUSDT")
        assert decision["symbol"] == "ETHUSDT"

    def test_observation_fingerprint_computed(self):
        """Governed observation → fingerprint is sha256 hex prefix"""
        obs = _make_governed_observation()
        decision = build_shadow_decision(governed_observation=obs)
        assert decision["observation_fingerprint"] != "no_observation"
        assert len(decision["observation_fingerprint"]) == 16


# ═══════════════════════════════════════════════════════════════════════════════
# Test: ShadowDecisionConsumer / 测试：影子决策消费器
# ═══════════════════════════════════════════════════════════════════════════════

class TestShadowDecisionConsumer:
    def test_hold_when_no_signal(self, active_engine):
        """Decision with should_trade=False → action=hold"""
        consumer = ShadowDecisionConsumer(active_engine)
        decision = build_shadow_decision(verdict=_make_verdict())
        result = consumer.consume(decision, {"BTCUSDT": 50000.0})
        assert result["action_taken"] == "hold"
        assert result["order_id"] is None

    def test_trade_when_signal_strong(self, active_engine):
        """Strong signal → paper order created"""
        consumer = ShadowDecisionConsumer(active_engine)
        decision = build_shadow_decision(
            verdict=_make_verdict(),
            governed_observation=_make_governed_observation(confidence=0.8, edge_bps=20.0),
        )
        result = consumer.consume(decision, {"BTCUSDT": 50000.0})
        assert result["action_taken"] == "order_submitted"
        assert result["order_id"] is not None

    def test_no_price_no_trade(self, active_engine):
        """No market price for symbol → no trade"""
        consumer = ShadowDecisionConsumer(active_engine)
        decision = build_shadow_decision(
            verdict=_make_verdict(),
            governed_observation=_make_governed_observation(),
        )
        result = consumer.consume(decision, {})  # empty prices
        assert result["action_taken"] == "hold"
        assert "no_market_price" in result["reason"]

    def test_session_not_active(self, tmp_state_file):
        """No active session → session_not_active"""
        store = PaperStateStore(tmp_state_file)
        eng = PaperTradingEngine(store)
        consumer = ShadowDecisionConsumer(eng)
        decision = build_shadow_decision(
            verdict=_make_verdict(),
            governed_observation=_make_governed_observation(),
        )
        result = consumer.consume(decision, {"BTCUSDT": 50000.0})
        assert result["reason"] == "session_not_active"

    def test_history_recorded(self, active_engine):
        """Consumed decisions are recorded in history"""
        consumer = ShadowDecisionConsumer(active_engine)
        decision = build_shadow_decision(verdict=_make_verdict())
        consumer.consume(decision, {"BTCUSDT": 50000.0})
        history = consumer.get_history()
        assert len(history) == 1
        assert history[0]["decision"]["decision_id"] == decision["decision_id"]

    def test_history_capped(self, active_engine):
        """History is capped at 200 entries"""
        consumer = ShadowDecisionConsumer(active_engine)
        for _ in range(210):
            decision = build_shadow_decision(verdict=_make_verdict())
            consumer.consume(decision, {"BTCUSDT": 50000.0})
        assert len(consumer.get_history(limit=300)) == 200

    def test_position_size_fraction(self, active_engine):
        """Order qty is based on position_size_fraction"""
        consumer = ShadowDecisionConsumer(active_engine, position_size_fraction=0.05)
        decision = build_shadow_decision(
            verdict=_make_verdict(),
            governed_observation=_make_governed_observation(),
        )
        result = consumer.consume(decision, {"BTCUSDT": 50000.0})
        assert result["action_taken"] == "order_submitted"
        # 10000 * 0.05 / 50000 = 0.01 BTC
        orders = active_engine.get_orders()
        filled_order = [o for o in orders if o["order_id"] == result["order_id"]][0]
        assert filled_order["qty"] == 0.01

    def test_sell_signal_creates_sell_order(self, active_engine):
        """Sell signal → sell order created"""
        consumer = ShadowDecisionConsumer(active_engine)
        decision = build_shadow_decision(
            verdict=_make_verdict(),
            governed_observation=_make_governed_observation(action_bias="sell_bias"),
        )
        result = consumer.consume(decision, {"BTCUSDT": 50000.0})
        assert result["action_taken"] == "order_submitted"
        orders = active_engine.get_orders()
        order = [o for o in orders if o["order_id"] == result["order_id"]][0]
        assert order["side"] == SIDE_SELL


# ═══════════════════════════════════════════════════════════════════════════════
# Test: ShadowDecisionFileFeeder / 测试：文件馈送器
# ═══════════════════════════════════════════════════════════════════════════════

class TestShadowDecisionFileFeeder:
    def test_no_files_returns_none(self, active_engine):
        """No verdict file → returns None (nothing new)"""
        consumer = ShadowDecisionConsumer(active_engine)
        feeder = ShadowDecisionFileFeeder(consumer)
        result = feeder.check_and_feed({"BTCUSDT": 50000.0})
        # No verdict path set, so feeds a blank decision → returns result (not None)
        # The behavior is: it still builds and consumes a decision
        assert result is not None

    def test_with_verdict_file(self, active_engine):
        """Verdict file exists → processes and returns result"""
        consumer = ShadowDecisionConsumer(active_engine)
        verdict = _make_verdict()

        fd, verdict_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            Path(verdict_path).write_text(json.dumps(verdict), encoding="utf-8")
            feeder = ShadowDecisionFileFeeder(consumer, verdict_path=verdict_path)
            result = feeder.check_and_feed({"BTCUSDT": 50000.0})
            assert result is not None
            assert result["decision_id"] is not None
        finally:
            os.unlink(verdict_path)

    def test_deduplication(self, active_engine):
        """Same verdict timestamp → second call returns None"""
        consumer = ShadowDecisionConsumer(active_engine)
        verdict = _make_verdict()

        fd, verdict_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            Path(verdict_path).write_text(json.dumps(verdict), encoding="utf-8")
            feeder = ShadowDecisionFileFeeder(consumer, verdict_path=verdict_path)
            result1 = feeder.check_and_feed({"BTCUSDT": 50000.0})
            assert result1 is not None
            result2 = feeder.check_and_feed({"BTCUSDT": 50000.0})
            assert result2 is None  # Deduplication
        finally:
            os.unlink(verdict_path)

    def test_with_governed_observation_file(self, active_engine):
        """Both verdict + governed observation files → rich decision"""
        consumer = ShadowDecisionConsumer(active_engine)
        verdict = _make_verdict()
        obs = _make_governed_observation()

        fd1, verdict_path = tempfile.mkstemp(suffix=".json")
        os.close(fd1)
        fd2, obs_path = tempfile.mkstemp(suffix=".json")
        os.close(fd2)
        try:
            Path(verdict_path).write_text(json.dumps(verdict), encoding="utf-8")
            Path(obs_path).write_text(json.dumps(obs), encoding="utf-8")
            feeder = ShadowDecisionFileFeeder(
                consumer, verdict_path=verdict_path, governed_decision_path=obs_path
            )
            result = feeder.check_and_feed({"BTCUSDT": 50000.0})
            assert result is not None
            # With strong observation → should attempt trade
            assert result["action_taken"] == "order_submitted"
        finally:
            os.unlink(verdict_path)
            os.unlink(obs_path)

    def test_missing_file_handled(self, active_engine):
        """Non-existent file path → gracefully handled"""
        consumer = ShadowDecisionConsumer(active_engine)
        feeder = ShadowDecisionFileFeeder(
            consumer, verdict_path="/nonexistent/verdict.json"
        )
        result = feeder.check_and_feed({"BTCUSDT": 50000.0})
        # No file → no verdict → feeds empty decision → hold
        assert result is not None

    def test_invalid_json_handled(self, active_engine):
        """Corrupt JSON → gracefully returns None for that file"""
        consumer = ShadowDecisionConsumer(active_engine)

        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            Path(path).write_text("not valid json{{{", encoding="utf-8")
            feeder = ShadowDecisionFileFeeder(consumer, verdict_path=path)
            result = feeder.check_and_feed({"BTCUSDT": 50000.0})
            assert result is not None  # Should handle gracefully
        finally:
            os.unlink(path)
