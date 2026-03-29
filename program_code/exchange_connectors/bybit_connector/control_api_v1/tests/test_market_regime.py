"""
Tests for Market Regime Formal Dataclass — DOC-03 / GAP-M6
市场体制形式化数据类测试

Covers:
  - MarketRegime enum and properties
  - RegimeConfidence mapping (enum + float)
  - RegimeTimeframe enum
  - MarketRegimeSnapshot dataclass creation, serialization, properties
  - RegimeTransition record creation and serialization
  - MarketRegimeTracker update_regime, get_current_regime, get_regime_history
  - Multi-timeframe conflict detection (EX-06 §6.4)
  - Thread safety
  - Edge cases and validation
  - JSON serialization round-tripping
"""

import sys
import threading
import time
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.market_regime import (
    MarketRegime,
    MarketRegimeSnapshot,
    RegimeConfidence,
    RegimeTimeframe,
    RegimeTransition,
    MarketRegimeTracker,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def tracker():
    """Fresh MarketRegimeTracker for each test."""
    return MarketRegimeTracker()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. MarketRegime Enum / 市场体制枚举
# ═══════════════════════════════════════════════════════════════════════════════


class TestMarketRegimeEnum:
    def test_all_regimes_defined(self):
        """All 9 regimes from spec."""
        regimes = list(MarketRegime)
        assert len(regimes) == 9
        assert MarketRegime.TRENDING_UP in regimes
        assert MarketRegime.TRENDING_DOWN in regimes
        assert MarketRegime.RANGING in regimes
        assert MarketRegime.SQUEEZE in regimes
        assert MarketRegime.HIGH_VOLATILITY in regimes
        assert MarketRegime.LOW_VOLATILITY in regimes
        assert MarketRegime.BREAKOUT in regimes
        assert MarketRegime.REVERSAL in regimes
        assert MarketRegime.UNKNOWN in regimes

    def test_regime_values_are_strings(self):
        """Regimes have string values (DOC-03 naming)."""
        assert MarketRegime.TRENDING_UP.value == "trending_up"
        assert MarketRegime.RANGING.value == "ranging"

    def test_regime_comparison(self):
        """Can compare regime enums."""
        assert MarketRegime.TRENDING_UP == MarketRegime.TRENDING_UP
        assert MarketRegime.TRENDING_UP != MarketRegime.TRENDING_DOWN


# ═══════════════════════════════════════════════════════════════════════════════
# 2. RegimeConfidence / 置信度
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegimeConfidence:
    def test_confidence_enum_exists(self):
        """RegimeConfidence has HIGH, MEDIUM, LOW."""
        assert RegimeConfidence.HIGH.value == "high"
        assert RegimeConfidence.MEDIUM.value == "medium"
        assert RegimeConfidence.LOW.value == "low"

    def test_confidence_float_mapping_high(self):
        """Float > 0.75 → HIGH."""
        snapshot = MarketRegimeSnapshot(
            symbol="BTCUSDT",
            regime=MarketRegime.TRENDING_UP,
            confidence=0.85,
            timeframe=RegimeTimeframe.M5,
        )
        assert snapshot.confidence_level == RegimeConfidence.HIGH
        assert snapshot.is_high_confidence is True
        assert snapshot.is_medium_confidence is False
        assert snapshot.is_low_confidence is False

    def test_confidence_float_mapping_medium(self):
        """Float 0.5-0.75 → MEDIUM."""
        snapshot = MarketRegimeSnapshot(
            symbol="BTCUSDT",
            regime=MarketRegime.RANGING,
            confidence=0.62,
            timeframe=RegimeTimeframe.H1,
        )
        assert snapshot.confidence_level == RegimeConfidence.MEDIUM
        assert snapshot.is_medium_confidence is True
        assert snapshot.is_high_confidence is False

    def test_confidence_float_mapping_low(self):
        """Float < 0.5 → LOW."""
        snapshot = MarketRegimeSnapshot(
            symbol="BTCUSDT",
            regime=MarketRegime.UNKNOWN,
            confidence=0.3,
            timeframe=RegimeTimeframe.H4,
        )
        assert snapshot.confidence_level == RegimeConfidence.LOW
        assert snapshot.is_low_confidence is True

    def test_confidence_boundary_75(self):
        """Boundary: 0.75 is MEDIUM, >0.75 is HIGH."""
        low_boundary = MarketRegimeSnapshot(confidence=0.75)
        high_boundary = MarketRegimeSnapshot(confidence=0.750001)
        assert low_boundary.confidence_level == RegimeConfidence.MEDIUM
        assert high_boundary.confidence_level == RegimeConfidence.HIGH

    def test_confidence_boundary_50(self):
        """Boundary: 0.5 is MEDIUM, <0.5 is LOW."""
        medium_boundary = MarketRegimeSnapshot(confidence=0.5)
        low_boundary = MarketRegimeSnapshot(confidence=0.49999)
        assert medium_boundary.confidence_level == RegimeConfidence.MEDIUM
        assert low_boundary.confidence_level == RegimeConfidence.LOW


# ═══════════════════════════════════════════════════════════════════════════════
# 3. RegimeTimeframe / 时间框架
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegimeTimeframe:
    def test_all_timeframes(self):
        """All 5 timeframes defined."""
        tfs = list(RegimeTimeframe)
        assert len(tfs) == 5
        assert RegimeTimeframe.M5 in tfs
        assert RegimeTimeframe.M15 in tfs
        assert RegimeTimeframe.H1 in tfs
        assert RegimeTimeframe.H4 in tfs
        assert RegimeTimeframe.D1 in tfs

    def test_timeframe_values(self):
        """Timeframe values match canonical names."""
        assert RegimeTimeframe.M5.value == "M5"
        assert RegimeTimeframe.H1.value == "H1"
        assert RegimeTimeframe.D1.value == "D1"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. MarketRegimeSnapshot Dataclass / 市场体制快照数据类
# ═══════════════════════════════════════════════════════════════════════════════


class TestMarketRegimeSnapshot:
    def test_snapshot_creation_minimal(self):
        """Create snapshot with minimal fields."""
        snapshot = MarketRegimeSnapshot(
            symbol="BTCUSDT",
            regime=MarketRegime.TRENDING_UP,
            confidence=0.82,
        )
        assert snapshot.symbol == "BTCUSDT"
        assert snapshot.regime == MarketRegime.TRENDING_UP
        assert snapshot.confidence == 0.82
        assert snapshot.detected_at_ms > 0
        assert snapshot.timeframe == RegimeTimeframe.M5  # Default

    def test_snapshot_auto_timestamp(self):
        """Snapshot auto-generates detected_at_ms."""
        before = int(time.time() * 1000)
        snapshot = MarketRegimeSnapshot(symbol="ETHUSDT", regime=MarketRegime.RANGING)
        after = int(time.time() * 1000)
        assert before <= snapshot.detected_at_ms <= after + 100

    def test_snapshot_with_full_fields(self):
        """Snapshot with all supported fields."""
        indicators = {"sma_20": 12345.6, "rsi": 68.2}
        volume_profile = {"high": 0.6, "normal": 0.4}
        metadata = {"data_points_used": 100, "lookback_bars": 50}

        snapshot = MarketRegimeSnapshot(
            symbol="BTCUSDT",
            regime=MarketRegime.SQUEEZE,
            confidence=0.71,
            timeframe=RegimeTimeframe.H4,
            atr_value=450.0,
            volatility_percentile=35,
            volume_profile=volume_profile,
            supporting_indicators=indicators,
            metadata=metadata,
        )
        assert snapshot.symbol == "BTCUSDT"
        assert snapshot.atr_value == 450.0
        assert snapshot.volatility_percentile == 35
        assert snapshot.volume_profile["high"] == 0.6
        assert snapshot.supporting_indicators["rsi"] == 68.2
        assert snapshot.metadata["lookback_bars"] == 50

    def test_snapshot_confidence_clamping(self):
        """Confidence is NOT clamped in snapshot (tracker does it)."""
        # Snapshot itself doesn't clamp, but MarketRegimeTracker.update_regime does
        snapshot = MarketRegimeSnapshot(confidence=0.85)
        assert snapshot.confidence == 0.85

    def test_snapshot_to_dict(self):
        """Snapshot serializes to dict."""
        snapshot = MarketRegimeSnapshot(
            symbol="BTCUSDT",
            regime=MarketRegime.TRENDING_UP,
            confidence=0.85,
            timeframe=RegimeTimeframe.H1,
        )
        d = snapshot.to_dict()
        assert d["symbol"] == "BTCUSDT"
        assert d["regime"] == "trending_up"  # Enum value
        assert d["confidence"] == 0.85
        assert d["timeframe"] == "H1"
        assert d["confidence_level"] == "high"

    def test_snapshot_to_json(self):
        """Snapshot serializes to JSON."""
        snapshot = MarketRegimeSnapshot(
            symbol="ETHUSDT",
            regime=MarketRegime.RANGING,
            confidence=0.62,
        )
        json_str = snapshot.to_json()
        assert isinstance(json_str, str)
        parsed = json.loads(json_str)
        assert parsed["symbol"] == "ETHUSDT"
        assert parsed["regime"] == "ranging"

    def test_snapshot_from_dict(self):
        """Snapshot deserializes from dict."""
        d = {
            "symbol": "BTCUSDT",
            "regime": "trending_up",
            "confidence": 0.80,
            "timeframe": "H4",
            "detected_at_ms": 1000000,
            "atr_value": 500.0,
            "volatility_percentile": 70,
            "volume_profile": {},
            "supporting_indicators": {},
            "metadata": {},
        }
        snapshot = MarketRegimeSnapshot.from_dict(d)
        assert snapshot.symbol == "BTCUSDT"
        assert snapshot.regime == MarketRegime.TRENDING_UP
        assert snapshot.confidence == 0.80
        assert snapshot.timeframe == RegimeTimeframe.H4
        assert snapshot.detected_at_ms == 1000000

    def test_snapshot_json_roundtrip(self):
        """JSON serialization roundtrips without loss."""
        original = MarketRegimeSnapshot(
            symbol="BNBUSDT",
            regime=MarketRegime.BREAKOUT,
            confidence=0.76,
            timeframe=RegimeTimeframe.M15,
            atr_value=12.5,
            volatility_percentile=88,
            supporting_indicators={"bb_width": 250},
        )
        json_str = original.to_json()
        restored = MarketRegimeSnapshot.from_json(json_str)
        assert restored.symbol == original.symbol
        assert restored.regime == original.regime
        assert restored.confidence == original.confidence
        assert restored.timeframe == original.timeframe
        assert restored.supporting_indicators == original.supporting_indicators


# ═══════════════════════════════════════════════════════════════════════════════
# 5. RegimeTransition / 体制转换记录
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegimeTransition:
    def test_transition_creation(self):
        """Create transition record."""
        transition = RegimeTransition(
            from_regime=MarketRegime.RANGING,
            to_regime=MarketRegime.TRENDING_UP,
            symbol="BTCUSDT",
            timeframe=RegimeTimeframe.H1,
            trigger_reason="bollinger_breakout",
            trigger_confidence=0.79,
        )
        assert transition.from_regime == MarketRegime.RANGING
        assert transition.to_regime == MarketRegime.TRENDING_UP
        assert transition.symbol == "BTCUSDT"
        assert transition.trigger_reason == "bollinger_breakout"
        assert transition.transition_id.startswith("rt:")
        assert transition.transition_at_ms > 0

    def test_transition_to_dict(self):
        """Transition serializes to dict."""
        transition = RegimeTransition(
            from_regime=MarketRegime.RANGING,
            to_regime=MarketRegime.SQUEEZE,
            symbol="ETHUSDT",
            timeframe=RegimeTimeframe.M5,
            trigger_reason="volatility_contraction",
        )
        d = transition.to_dict()
        assert d["from_regime"] == "ranging"
        assert d["to_regime"] == "squeeze"
        assert d["symbol"] == "ETHUSDT"
        assert d["trigger_reason"] == "volatility_contraction"

    def test_transition_from_dict(self):
        """Transition deserializes from dict."""
        d = {
            "transition_id": "rt:abc123",
            "from_regime": "trending_down",
            "to_regime": "reversal",
            "transition_at_ms": 2000000,
            "timeframe": "H4",
            "symbol": "BNBUSDT",
            "trigger_reason": "rsi_divergence",
            "trigger_confidence": 0.68,
            "metadata": {},
        }
        transition = RegimeTransition.from_dict(d)
        assert transition.from_regime == MarketRegime.TRENDING_DOWN
        assert transition.to_regime == MarketRegime.REVERSAL
        assert transition.symbol == "BNBUSDT"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. MarketRegimeTracker / 市场体制追踪器
# ═══════════════════════════════════════════════════════════════════════════════


class TestMarketRegimeTracker:
    def test_tracker_creation(self):
        """Create fresh tracker."""
        tracker = MarketRegimeTracker()
        assert tracker is not None
        stats = tracker.get_stats()
        assert stats["updates"] == 0
        assert stats["transitions"] == 0

    def test_update_regime_creates_snapshot(self, tracker):
        """Update regime creates snapshot."""
        is_transition, trans = tracker.update_regime(
            symbol="BTCUSDT",
            regime=MarketRegime.TRENDING_UP,
            confidence=0.82,
            timeframe=RegimeTimeframe.H1,
            atr_value=450.0,
            volatility_percentile=75,
        )
        assert is_transition is False  # No previous state
        assert trans is None
        stats = tracker.get_stats()
        assert stats["updates"] == 1

    def test_update_regime_detects_transition(self, tracker):
        """Update detects when regime changes."""
        # First update
        is_trans_1, trans_1 = tracker.update_regime(
            symbol="BTCUSDT",
            regime=MarketRegime.TRENDING_UP,
            confidence=0.80,
            timeframe=RegimeTimeframe.H1,
        )
        assert is_trans_1 is False
        assert trans_1 is None

        # Second update: regime changes
        is_trans_2, trans_2 = tracker.update_regime(
            symbol="BTCUSDT",
            regime=MarketRegime.RANGING,
            confidence=0.70,
            timeframe=RegimeTimeframe.H1,
            trigger_reason="volatility_contraction",
        )
        assert is_trans_2 is True
        assert trans_2 is not None
        assert trans_2.from_regime == MarketRegime.TRENDING_UP
        assert trans_2.to_regime == MarketRegime.RANGING
        assert trans_2.trigger_reason == "volatility_contraction"

        stats = tracker.get_stats()
        assert stats["updates"] == 2
        assert stats["transitions"] == 1

    def test_update_regime_same_regime_no_transition(self, tracker):
        """Update with same regime doesn't create transition."""
        tracker.update_regime(
            symbol="BTCUSDT",
            regime=MarketRegime.TRENDING_UP,
            confidence=0.82,
            timeframe=RegimeTimeframe.H1,
        )
        is_trans, trans = tracker.update_regime(
            symbol="BTCUSDT",
            regime=MarketRegime.TRENDING_UP,
            confidence=0.85,  # Changed confidence, same regime
            timeframe=RegimeTimeframe.H1,
        )
        assert is_trans is False
        assert trans is None

    def test_update_regime_different_timeframes(self, tracker):
        """Same symbol, different timeframes are independent."""
        tracker.update_regime(
            symbol="BTCUSDT",
            regime=MarketRegime.TRENDING_UP,
            confidence=0.82,
            timeframe=RegimeTimeframe.M5,
        )
        tracker.update_regime(
            symbol="BTCUSDT",
            regime=MarketRegime.RANGING,
            confidence=0.70,
            timeframe=RegimeTimeframe.H1,
        )
        m5 = tracker.get_current_regime("BTCUSDT", RegimeTimeframe.M5)
        h1 = tracker.get_current_regime("BTCUSDT", RegimeTimeframe.H1)
        assert m5.regime == MarketRegime.TRENDING_UP
        assert h1.regime == MarketRegime.RANGING

    def test_get_current_regime_not_found(self, tracker):
        """Get non-existent regime returns None."""
        snapshot = tracker.get_current_regime("BTCUSDT", RegimeTimeframe.M5)
        assert snapshot is None

    def test_get_all_current_regimes(self, tracker):
        """Get all regimes for a symbol."""
        tracker.update_regime("BTCUSDT", MarketRegime.TRENDING_UP, 0.80, RegimeTimeframe.M5)
        tracker.update_regime("BTCUSDT", MarketRegime.RANGING, 0.70, RegimeTimeframe.H1)
        tracker.update_regime("BTCUSDT", MarketRegime.SQUEEZE, 0.65, RegimeTimeframe.H4)

        all_regimes = tracker.get_all_current_regimes("BTCUSDT")
        assert len(all_regimes) == 3
        assert all_regimes[RegimeTimeframe.M5].regime == MarketRegime.TRENDING_UP
        assert all_regimes[RegimeTimeframe.H1].regime == MarketRegime.RANGING
        assert all_regimes[RegimeTimeframe.H4].regime == MarketRegime.SQUEEZE

    def test_get_regime_history(self, tracker):
        """Get transition history."""
        tracker.update_regime("BTCUSDT", MarketRegime.TRENDING_UP, 0.80, RegimeTimeframe.H1)
        tracker.update_regime("BTCUSDT", MarketRegime.RANGING, 0.70, RegimeTimeframe.H1)
        tracker.update_regime("BTCUSDT", MarketRegime.SQUEEZE, 0.65, RegimeTimeframe.H1)

        history = tracker.get_regime_history("BTCUSDT", RegimeTimeframe.H1)
        assert len(history) == 2  # 2 transitions
        # Most recent first
        assert history[0].to_regime == MarketRegime.SQUEEZE
        assert history[1].to_regime == MarketRegime.RANGING

    def test_regime_history_limit(self, tracker):
        """Regime history respects limit parameter."""
        for i in range(5):
            tracker.update_regime(
                "BTCUSDT",
                MarketRegime.TRENDING_UP if i % 2 == 0 else MarketRegime.RANGING,
                0.80,
                RegimeTimeframe.M5,
            )

        # All transitions
        all_history = tracker.get_regime_history("BTCUSDT", RegimeTimeframe.M5, limit=100)
        assert len(all_history) == 4

        # Limited to 2
        limited = tracker.get_regime_history("BTCUSDT", RegimeTimeframe.M5, limit=2)
        assert len(limited) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Multi-timeframe Conflict Detection (EX-06 §6.4) / 多时间框架冲突检测
# ═══════════════════════════════════════════════════════════════════════════════


class TestMultiTimeframeConflictDetection:
    def test_no_conflict_single_timeframe(self, tracker):
        """No conflict with only one timeframe."""
        tracker.update_regime("BTCUSDT", MarketRegime.TRENDING_UP, 0.80, RegimeTimeframe.M5)
        conflict = tracker.detect_multi_timeframe_conflict("BTCUSDT")
        assert conflict is None

    def test_no_conflict_aligned_regimes(self, tracker):
        """No conflict when regimes align."""
        tracker.update_regime("BTCUSDT", MarketRegime.TRENDING_UP, 0.80, RegimeTimeframe.M5)
        tracker.update_regime("BTCUSDT", MarketRegime.TRENDING_UP, 0.78, RegimeTimeframe.H1)
        tracker.update_regime("BTCUSDT", MarketRegime.TRENDING_UP, 0.82, RegimeTimeframe.H4)
        conflict = tracker.detect_multi_timeframe_conflict("BTCUSDT")
        assert conflict is None

    def test_directional_conflict_trending_divergence(self, tracker):
        """Detects H4 up vs M5 down conflict."""
        tracker.update_regime("BTCUSDT", MarketRegime.TRENDING_DOWN, 0.80, RegimeTimeframe.M5)
        tracker.update_regime("BTCUSDT", MarketRegime.TRENDING_UP, 0.78, RegimeTimeframe.H1)
        tracker.update_regime("BTCUSDT", MarketRegime.TRENDING_UP, 0.82, RegimeTimeframe.H4)

        conflict = tracker.detect_multi_timeframe_conflict("BTCUSDT")
        assert conflict is not None
        assert conflict["conflict_type"] == "directional_divergence"
        assert "M5" in conflict["trending_down_timeframes"]

    def test_trend_range_conflict(self, tracker):
        """Detects trend vs range conflict."""
        tracker.update_regime("BTCUSDT", MarketRegime.TRENDING_UP, 0.80, RegimeTimeframe.M5)
        tracker.update_regime("BTCUSDT", MarketRegime.TRENDING_UP, 0.78, RegimeTimeframe.H1)
        tracker.update_regime("BTCUSDT", MarketRegime.RANGING, 0.76, RegimeTimeframe.H4)

        conflict = tracker.detect_multi_timeframe_conflict("BTCUSDT")
        assert conflict is not None
        assert conflict["conflict_type"] == "trend_range_divergence"
        assert "H4" in str(conflict["ranging_timeframes"])

    def test_conflict_confidence_threshold(self, tracker):
        """Conflict detection respects confidence threshold."""
        # High confidence on H1 trend, low confidence on H4 range
        tracker.update_regime("BTCUSDT", MarketRegime.TRENDING_UP, 0.82, RegimeTimeframe.H1)
        tracker.update_regime("BTCUSDT", MarketRegime.RANGING, 0.40, RegimeTimeframe.H4)

        # With strict threshold, no conflict (H4 too low conf)
        conflict = tracker.detect_multi_timeframe_conflict("BTCUSDT", confidence_threshold=0.70)
        assert conflict is None

        # With loose threshold, conflict detected
        conflict = tracker.detect_multi_timeframe_conflict("BTCUSDT", confidence_threshold=0.30)
        assert conflict is not None

    def test_conflict_stats_tracked(self, tracker):
        """Conflict detections tracked in stats."""
        tracker.update_regime("BTCUSDT", MarketRegime.TRENDING_UP, 0.80, RegimeTimeframe.M5)
        tracker.update_regime("BTCUSDT", MarketRegime.TRENDING_DOWN, 0.80, RegimeTimeframe.H1)

        tracker.detect_multi_timeframe_conflict("BTCUSDT")
        stats = tracker.get_stats()
        assert stats["conflicts_detected"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Serialization / 序列化
# ═══════════════════════════════════════════════════════════════════════════════


class TestMarketRegimeTrackerSerialization:
    def test_tracker_to_dict(self, tracker):
        """Tracker serializes to dict."""
        tracker.update_regime("BTCUSDT", MarketRegime.TRENDING_UP, 0.80, RegimeTimeframe.H1)
        tracker.update_regime("BTCUSDT", MarketRegime.RANGING, 0.70, RegimeTimeframe.H1)

        d = tracker.to_dict()
        assert "current_regimes" in d
        assert "transition_history" in d
        assert "stats" in d
        assert len(d["current_regimes"]) == 1
        assert len(d["transition_history"]) == 1

    def test_tracker_to_json(self, tracker):
        """Tracker serializes to JSON."""
        tracker.update_regime("BTCUSDT", MarketRegime.TRENDING_UP, 0.82, RegimeTimeframe.M5)
        json_str = tracker.to_json()
        assert isinstance(json_str, str)
        parsed = json.loads(json_str)
        assert "current_regimes" in parsed

    def test_tracker_from_dict(self):
        """Tracker deserializes from dict."""
        original = MarketRegimeTracker()
        original.update_regime("BTCUSDT", MarketRegime.TRENDING_UP, 0.80, RegimeTimeframe.H1)
        original.update_regime("BTCUSDT", MarketRegime.RANGING, 0.70, RegimeTimeframe.H1)

        d = original.to_dict()

        restored = MarketRegimeTracker()
        restored.from_dict(d)

        # Verify state
        snapshot = restored.get_current_regime("BTCUSDT", RegimeTimeframe.H1)
        assert snapshot.regime == MarketRegime.RANGING
        history = restored.get_regime_history("BTCUSDT", RegimeTimeframe.H1)
        assert len(history) == 1

    def test_tracker_json_roundtrip(self):
        """JSON roundtrip preserves full state."""
        original = MarketRegimeTracker()
        original.update_regime("BTCUSDT", MarketRegime.TRENDING_UP, 0.85, RegimeTimeframe.M5)
        original.update_regime("ETHUSDT", MarketRegime.SQUEEZE, 0.65, RegimeTimeframe.H4)

        json_str = original.to_json()
        restored = MarketRegimeTracker.from_json(json_str)

        btc_snap = restored.get_current_regime("BTCUSDT", RegimeTimeframe.M5)
        eth_snap = restored.get_current_regime("ETHUSDT", RegimeTimeframe.H4)
        assert btc_snap.regime == MarketRegime.TRENDING_UP
        assert eth_snap.regime == MarketRegime.SQUEEZE


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Thread Safety / 线程安全性
# ═══════════════════════════════════════════════════════════════════════════════


class TestThreadSafety:
    def test_concurrent_updates(self):
        """Concurrent updates don't corrupt state."""
        tracker = MarketRegimeTracker()
        results = []
        errors = []

        def update_worker(symbol, regime_int):
            try:
                for i in range(10):
                    regime = list(MarketRegime)[regime_int % 9]
                    tracker.update_regime(
                        symbol=symbol,
                        regime=regime,
                        confidence=0.70 + (i * 0.01),
                        timeframe=RegimeTimeframe.M5,
                    )
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(5):
            t = threading.Thread(target=update_worker, args=(f"COIN{i}USDT", i))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0
        stats = tracker.get_stats()
        assert stats["updates"] > 0

    def test_concurrent_reads(self):
        """Concurrent reads don't block or corrupt."""
        tracker = MarketRegimeTracker()
        tracker.update_regime("BTCUSDT", MarketRegime.TRENDING_UP, 0.80, RegimeTimeframe.H1)

        results = []
        errors = []

        def read_worker():
            try:
                for _ in range(20):
                    snapshot = tracker.get_current_regime("BTCUSDT", RegimeTimeframe.H1)
                    results.append(snapshot)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read_worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 100
        assert all(r.regime == MarketRegime.TRENDING_UP for r in results)


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Edge Cases / 边界情况
# ═══════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_confidence_boundary_values(self, tracker):
        """Confidence can be any float in 0-1 range."""
        tracker.update_regime("BTCUSDT", MarketRegime.TRENDING_UP, 0.0, RegimeTimeframe.M5)
        tracker.update_regime("BTCUSDT", MarketRegime.RANGING, 1.0, RegimeTimeframe.H1)

        m5 = tracker.get_current_regime("BTCUSDT", RegimeTimeframe.M5)
        h1 = tracker.get_current_regime("BTCUSDT", RegimeTimeframe.H1)
        assert m5.confidence == 0.0
        assert h1.confidence == 1.0

    def test_empty_symbol(self, tracker):
        """Empty symbol allowed (edge case handling)."""
        tracker.update_regime("", MarketRegime.TRENDING_UP, 0.80, RegimeTimeframe.M5)
        snapshot = tracker.get_current_regime("", RegimeTimeframe.M5)
        assert snapshot is not None
        assert snapshot.symbol == ""

    def test_many_symbols_multiframe(self, tracker):
        """Many symbols with multiple timeframes."""
        symbols = [f"COIN{i}USDT" for i in range(20)]
        for symbol in symbols:
            for tf in RegimeTimeframe:
                tracker.update_regime(
                    symbol=symbol,
                    regime=MarketRegime.TRENDING_UP,
                    confidence=0.75,
                    timeframe=tf,
                )

        stats = tracker.get_stats()
        assert stats["updates"] == 100  # 20 symbols * 5 timeframes

        # Verify random access
        snap = tracker.get_current_regime("COIN15USDT", RegimeTimeframe.H4)
        assert snap is not None
        assert snap.regime == MarketRegime.TRENDING_UP

    def test_history_max_length(self):
        """History respects max length."""
        tracker = MarketRegimeTracker(max_history_per_symbol_tf=10)
        for i in range(20):
            regime = MarketRegime.TRENDING_UP if i % 2 == 0 else MarketRegime.RANGING
            tracker.update_regime("BTCUSDT", regime, 0.75, RegimeTimeframe.M5)

        history = tracker.get_regime_history("BTCUSDT", RegimeTimeframe.M5, limit=100)
        # Should have max 10 transitions (starting from empty, we get transitions on updates 2-20)
        assert len(history) <= 10

    def test_stats_reset(self, tracker):
        """Stats can be reset."""
        tracker.update_regime("BTCUSDT", MarketRegime.TRENDING_UP, 0.80, RegimeTimeframe.M5)
        tracker.update_regime("BTCUSDT", MarketRegime.RANGING, 0.70, RegimeTimeframe.M5)

        stats_before = tracker.get_stats()
        assert stats_before["updates"] == 2
        assert stats_before["transitions"] == 1

        tracker.reset_stats()
        stats_after = tracker.get_stats()
        assert stats_after["updates"] == 0
        assert stats_after["transitions"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Integration / 集成测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestIntegration:
    def test_realistic_market_flow(self, tracker):
        """Realistic multi-timeframe market flow."""
        # Market starts ranging on all timeframes
        for tf in [RegimeTimeframe.M5, RegimeTimeframe.M15, RegimeTimeframe.H1]:
            tracker.update_regime("BTCUSDT", MarketRegime.RANGING, 0.70, tf)

        # M5 shows breakout first
        tracker.update_regime(
            "BTCUSDT",
            MarketRegime.BREAKOUT,
            0.75,
            RegimeTimeframe.M5,
            trigger_reason="resistance_broken",
        )

        # M15 follows
        tracker.update_regime(
            "BTCUSDT",
            MarketRegime.TRENDING_UP,
            0.80,
            RegimeTimeframe.M15,
            trigger_reason="momentum_build",
        )

        # H1 slower to confirm
        tracker.update_regime(
            "BTCUSDT",
            MarketRegime.TRENDING_UP,
            0.78,
            RegimeTimeframe.H1,
            trigger_reason="higher_high",
        )

        # No conflict now
        conflict = tracker.detect_multi_timeframe_conflict("BTCUSDT")
        assert conflict is None

        # Verify history
        m5_history = tracker.get_regime_history("BTCUSDT", RegimeTimeframe.M5)
        assert len(m5_history) == 1
        assert m5_history[0].from_regime == MarketRegime.RANGING
        assert m5_history[0].to_regime == MarketRegime.BREAKOUT
