"""
Market Regime Formal Dataclass — DOC-03 / GAP-M6
市场体制形式化数据类

MODULE_NOTE (中文):
  实现 DOC-03 字段与状态规范 v1.1 § 6.3 市场体制枚举，以及 GAP-M6 的完整市场体制检测系统：
  - MarketRegime 枚举：TRENDING_UP, TRENDING_DOWN, RANGING, SQUEEZE, HIGH_VOLATILITY,
    LOW_VOLATILITY, BREAKOUT, REVERSAL, UNKNOWN
  - RegimeConfidence：置信度分级（HIGH, MEDIUM, LOW）或浮点 0-1
  - RegimeTimeframe：多时间框架支持（M5, M15, H1, H4, D1）
  - MarketRegimeSnapshot：市场体制快照数据类，包含 symbol, regime, confidence,
    timeframe, detected_at_ms, volatility_percentile, atr_value, volume_profile,
    supporting_indicators(dict), metadata
  - RegimeTransition：体制转换记录，from_regime, to_regime, transition_at_ms, trigger_reason
  - MarketRegimeTracker：多时间框架体制检测、历史追踪、跨时间框架冲突检测（EX-06 §6.4）
  - 线程安全设计，支持序列化

MODULE_NOTE (English):
  Implements DOC-03 Field & State Specification v1.1 § 6.3 market regime enum +
  complete market regime detection system (GAP-M6):
  - MarketRegime enum: TRENDING_UP, TRENDING_DOWN, RANGING, SQUEEZE, HIGH_VOLATILITY,
    LOW_VOLATILITY, BREAKOUT, REVERSAL, UNKNOWN
  - RegimeConfidence: confidence grading (HIGH, MEDIUM, LOW) and float 0-1 semantics
  - RegimeTimeframe: multi-timeframe support (M5, M15, H1, H4, D1)
  - MarketRegimeSnapshot: regime snapshot dataclass with symbol, regime, confidence,
    timeframe, detected_at_ms, volatility_percentile, atr_value, volume_profile,
    supporting_indicators(dict), metadata
  - RegimeTransition: regime transition record with from_regime, to_regime,
    transition_at_ms, trigger_reason
  - MarketRegimeTracker: multi-timeframe regime detection, history tracking,
    cross-timeframe conflict detection (EX-06 §6.4)
  - Thread-safe design, serialization support

Safety Invariant:
  - Regime changes must be recorded with timestamp and reason
  - Multi-timeframe conflicts must be explicitly detected (EX-06 §6.4)
  - Confidence ≤ 0.5 must not trigger automatic strategy changes
  - Regime state is read-only from external modules (writes via update_regime only)
  - Serialization must preserve enum semantics across JSON roundtrips
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Enums / 枚举
# ═══════════════════════════════════════════════════════════════════════════════


class MarketRegime(str, Enum):
    """
    Market regime types per DOC-03 § 6.3.
    市场体制类型（DOC-03 § 6.3）
    """
    TRENDING_UP = "trending_up"           # Strong uptrend with momentum
    TRENDING_DOWN = "trending_down"       # Strong downtrend with momentum
    RANGING = "ranging"                   # Price oscillating in defined boundaries
    SQUEEZE = "squeeze"                   # Contracting volatility, pending breakout
    HIGH_VOLATILITY = "high_volatility"   # Large price swings without clear direction
    LOW_VOLATILITY = "low_volatility"     # Compressed volatility, low movement
    BREAKOUT = "breakout"                 # Breaking out of range/resistance
    REVERSAL = "reversal"                 # Potential reversal patterns detected
    UNKNOWN = "unknown"                   # Insufficient data or conflicting signals


class RegimeConfidence(str, Enum):
    """
    Confidence level for regime classification.
    体制识别置信度级别

    Mapping to float values:
      HIGH (0.75-1.0) → >0.75
      MEDIUM (0.5-0.75) → 0.5-0.75
      LOW (0.0-0.5) → <0.5
    """
    HIGH = "high"       # confidence_score > 0.75
    MEDIUM = "medium"   # 0.5 <= confidence_score <= 0.75
    LOW = "low"         # confidence_score < 0.5


class RegimeTimeframe(str, Enum):
    """
    Multi-timeframe regime detection windows per DOC-04 § 9.
    多时间框架体制检测窗口（DOC-04 § 9）
    """
    M5 = "M5"     # 5-minute candles
    M15 = "M15"   # 15-minute candles
    H1 = "H1"     # 1-hour candles
    H4 = "H4"     # 4-hour candles
    D1 = "D1"     # Daily candles


# ═══════════════════════════════════════════════════════════════════════════════
# Market Regime Snapshot / 市场体制快照
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class MarketRegimeSnapshot:
    """
    Formal market regime snapshot — the canonical regime state object.
    正式市场体制快照 — 规范的体制状态对象。

    Per DOC-03 § 6, this is a derived (推导值) object based on market data.
    Represents the detected market regime at a specific point in time across
    a chosen timeframe.
    """

    # Core identification / 核心标识
    symbol: str = ""                           # e.g. "BTCUSDT"
    regime: MarketRegime = MarketRegime.UNKNOWN
    confidence: float = 0.0                    # 0.0 to 1.0, per RegimeConfidence mapping

    # Timeframe context / 时间框架上下文
    timeframe: RegimeTimeframe = RegimeTimeframe.M5

    # Timestamp / 时间戳（UTC epoch_ms, per DOC-03 § 1.6）
    detected_at_ms: int = 0

    # Market metrics / 市场指标
    volatility_percentile: float = 0.0         # 0-100, where we are in historical vol distribution
    atr_value: float = 0.0                     # ATR absolute value
    volume_profile: Dict[str, float] = field(default_factory=dict)  # e.g. {"high": 0.6, "normal": 0.4}

    # Supporting indicators / 支持指标
    supporting_indicators: Dict[str, Any] = field(default_factory=dict)
    # Examples:
    #   "sma_20": 12345.6
    #   "sma_50": 12340.2
    #   "rsi": 65.2
    #   "bollinger_upper": 12500
    #   "bollinger_lower": 12200
    #   "volume_ma": 450000

    # Metadata / 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Examples:
    #   "data_points_used": 100
    #   "lookback_bars": 50
    #   "regime_duration_bars": 25
    #   "triggers_algo_threshold": True

    def __post_init__(self):
        """Auto-generate timestamp if not provided."""
        if not self.detected_at_ms:
            self.detected_at_ms = int(time.time() * 1000)

    @property
    def confidence_level(self) -> RegimeConfidence:
        """Map float confidence to RegimeConfidence enum."""
        if self.confidence > 0.75:
            return RegimeConfidence.HIGH
        elif self.confidence >= 0.5:
            return RegimeConfidence.MEDIUM
        else:
            return RegimeConfidence.LOW

    @property
    def is_high_confidence(self) -> bool:
        """True if confidence_level == HIGH."""
        return self.confidence > 0.75

    @property
    def is_medium_confidence(self) -> bool:
        """True if confidence_level == MEDIUM."""
        return 0.5 <= self.confidence <= 0.75

    @property
    def is_low_confidence(self) -> bool:
        """True if confidence_level == LOW."""
        return self.confidence < 0.5

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict with enum names."""
        d = asdict(self)
        d["regime"] = self.regime.value
        d["timeframe"] = self.timeframe.value
        d["confidence_level"] = self.confidence_level.value
        return d

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MarketRegimeSnapshot:
        """Deserialize from dict."""
        d = data.copy()
        d["regime"] = MarketRegime(d.get("regime", "unknown"))
        d["timeframe"] = RegimeTimeframe(d.get("timeframe", "M5"))
        d.pop("confidence_level", None)  # Remove computed field
        return cls(**d)

    @classmethod
    def from_json(cls, json_str: str) -> MarketRegimeSnapshot:
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)


# ═══════════════════════════════════════════════════════════════════════════════
# Regime Transition / 体制转换
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class RegimeTransition:
    """
    Formal regime transition record.
    正式体制转换记录。

    Records every detected regime change with timing and reason.
    """

    transition_id: str = ""                    # Auto-generated
    from_regime: MarketRegime = MarketRegime.UNKNOWN
    to_regime: MarketRegime = MarketRegime.UNKNOWN
    transition_at_ms: int = 0
    timeframe: RegimeTimeframe = RegimeTimeframe.M5
    symbol: str = ""

    # Reason for transition / 转换原因
    trigger_reason: str = ""                   # e.g., "volatility_spike", "breakout_detected"
    trigger_confidence: float = 0.0            # Confidence of the trigger

    # Additional context / 额外上下文
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Auto-generate ID and timestamp."""
        if not self.transition_id:
            self.transition_id = f"rt:{uuid.uuid4().hex[:12]}"
        if not self.transition_at_ms:
            self.transition_at_ms = int(time.time() * 1000)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "transition_id": self.transition_id,
            "from_regime": self.from_regime.value,
            "to_regime": self.to_regime.value,
            "transition_at_ms": self.transition_at_ms,
            "timeframe": self.timeframe.value,
            "symbol": self.symbol,
            "trigger_reason": self.trigger_reason,
            "trigger_confidence": self.trigger_confidence,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RegimeTransition:
        """Deserialize from dict."""
        d = data.copy()
        d["from_regime"] = MarketRegime(d.get("from_regime", "unknown"))
        d["to_regime"] = MarketRegime(d.get("to_regime", "unknown"))
        d["timeframe"] = RegimeTimeframe(d.get("timeframe", "M5"))
        return cls(**d)


# ═══════════════════════════════════════════════════════════════════════════════
# Market Regime Tracker / 市场体制追踪器
# ═══════════════════════════════════════════════════════════════════════════════


class MarketRegimeTracker:
    """
    Multi-timeframe market regime tracker with conflict detection.
    多时间框架市场体制追踪器，带冲突检测。

    Responsibilities:
      1. Maintain current regime snapshot per symbol/timeframe
      2. Record regime transitions with reasons
      3. Detect multi-timeframe conflicts (EX-06 §6.4)
      4. Query regime history
      5. Thread-safe read/write operations

    Usage:
        tracker = MarketRegimeTracker()

        # Update regime on new signal
        tracker.update_regime(
            symbol="BTCUSDT",
            regime=MarketRegime.TRENDING_UP,
            confidence=0.82,
            timeframe=RegimeTimeframe.H1,
            atr_value=450.0,
            volatility_percentile=75,
            supporting_indicators={"sma_20": 12345, "rsi": 68}
        )

        # Get current regime
        snapshot = tracker.get_current_regime("BTCUSDT", RegimeTimeframe.H1)

        # Check for cross-timeframe conflicts
        conflict = tracker.detect_multi_timeframe_conflict("BTCUSDT")
        if conflict:
            logger.warning("Multi-timeframe conflict: %s", conflict)
    """

    def __init__(self, max_history_per_symbol_tf: int = 1000):
        """
        Args:
            max_history_per_symbol_tf: Max transition records per symbol/timeframe.
        """
        self._lock = threading.RLock()

        # Current regimes per symbol/timeframe
        self._current_regimes: Dict[Tuple[str, RegimeTimeframe], MarketRegimeSnapshot] = {}

        # Transition history per symbol/timeframe
        self._transition_history: Dict[
            Tuple[str, RegimeTimeframe], deque
        ] = {}

        self._max_history = max_history_per_symbol_tf
        self._stats = {
            "updates": 0,
            "transitions": 0,
            "conflicts_detected": 0,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Update / Mutation / 更新
    # ─────────────────────────────────────────────────────────────────────────

    def update_regime(
        self,
        symbol: str,
        regime: MarketRegime,
        confidence: float,
        timeframe: RegimeTimeframe = RegimeTimeframe.M5,
        atr_value: float = 0.0,
        volatility_percentile: float = 0.0,
        volume_profile: Optional[Dict[str, float]] = None,
        supporting_indicators: Optional[Dict[str, Any]] = None,
        trigger_reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[RegimeTransition]]:
        """
        Update regime for a symbol/timeframe pair.

        Returns:
            (is_new_transition, transition_record_if_changed)
        """
        with self._lock:
            key = (symbol, timeframe)

            # Create new snapshot
            snapshot = MarketRegimeSnapshot(
                symbol=symbol,
                regime=regime,
                confidence=max(0.0, min(1.0, confidence)),  # Clamp 0-1
                timeframe=timeframe,
                atr_value=atr_value,
                volatility_percentile=volatility_percentile,
                volume_profile=volume_profile or {},
                supporting_indicators=supporting_indicators or {},
                metadata=metadata or {},
            )

            is_transition = False
            transition_record = None

            # Check if this is a regime change
            old_snapshot = self._current_regimes.get(key)
            if old_snapshot and old_snapshot.regime != regime:
                is_transition = True
                transition_record = RegimeTransition(
                    from_regime=old_snapshot.regime,
                    to_regime=regime,
                    timeframe=timeframe,
                    symbol=symbol,
                    trigger_reason=trigger_reason or "unknown",
                    trigger_confidence=snapshot.confidence,
                )

                # Record transition
                if key not in self._transition_history:
                    self._transition_history[key] = deque(maxlen=self._max_history)
                self._transition_history[key].append(transition_record)
                self._stats["transitions"] += 1

            # Update current regime
            self._current_regimes[key] = snapshot
            self._stats["updates"] += 1

            return is_transition, transition_record

    # ─────────────────────────────────────────────────────────────────────────
    # Query / 查询
    # ─────────────────────────────────────────────────────────────────────────

    def get_current_regime(
        self, symbol: str, timeframe: RegimeTimeframe = RegimeTimeframe.M5
    ) -> Optional[MarketRegimeSnapshot]:
        """Get current regime snapshot for symbol/timeframe."""
        with self._lock:
            return self._current_regimes.get((symbol, timeframe))

    def get_all_current_regimes(self, symbol: str) -> Dict[RegimeTimeframe, MarketRegimeSnapshot]:
        """Get current regimes across all timeframes for a symbol."""
        with self._lock:
            result = {}
            for tf in RegimeTimeframe:
                snapshot = self._current_regimes.get((symbol, tf))
                if snapshot:
                    result[tf] = snapshot
            return result

    def get_regime_history(
        self,
        symbol: str,
        timeframe: RegimeTimeframe = RegimeTimeframe.M5,
        limit: int = 100,
    ) -> List[RegimeTransition]:
        """Get recent transition history (most recent first)."""
        with self._lock:
            key = (symbol, timeframe)
            if key not in self._transition_history:
                return []
            history = list(self._transition_history[key])
            return history[-limit:][::-1] if history else []

    # ─────────────────────────────────────────────────────────────────────────
    # Multi-timeframe Conflict Detection (EX-06 §6.4) / 多时间框架冲突检测
    # ─────────────────────────────────────────────────────────────────────────

    def detect_multi_timeframe_conflict(
        self, symbol: str, confidence_threshold: float = 0.7
    ) -> Optional[Dict[str, Any]]:
        """
        Detect conflicting regime signals across timeframes (EX-06 §6.4).

        Returns:
            Dict with conflict details if detected, else None.

        Conflict scenarios:
          - H4 trending_up but M5 trending_down (both high confidence)
          - H1 ranging but M15 breakout (conflicting momentum)
          - Different volatility assessment across timeframes
        """
        with self._lock:
            regimes = self.get_all_current_regimes(symbol)
            if len(regimes) < 2:
                return None  # Need at least 2 timeframes to detect conflict

            # Collect high-confidence regimes
            high_conf_regimes = {
                tf: snapshot
                for tf, snapshot in regimes.items()
                if snapshot.confidence >= confidence_threshold
            }

            if len(high_conf_regimes) < 2:
                return None  # Not enough high-confidence signals to conflict

            # Check for directional conflicts (trending vs ranging/unknown)
            trending_up = [
                (tf, snap) for tf, snap in high_conf_regimes.items()
                if snap.regime == MarketRegime.TRENDING_UP
            ]
            trending_down = [
                (tf, snap) for tf, snap in high_conf_regimes.items()
                if snap.regime == MarketRegime.TRENDING_DOWN
            ]
            ranging = [
                (tf, snap) for tf, snap in high_conf_regimes.items()
                if snap.regime == MarketRegime.RANGING
            ]

            # Conflict: some timeframes trending up, others trending down (high conf both)
            if trending_up and trending_down:
                self._stats["conflicts_detected"] += 1
                return {
                    "symbol": symbol,
                    "conflict_type": "directional_divergence",
                    "trending_up_timeframes": [tf.value for tf, _ in trending_up],
                    "trending_down_timeframes": [tf.value for tf, _ in trending_down],
                    "detected_at_ms": int(time.time() * 1000),
                    "severity": "high",
                }

            # Conflict: some trending, others ranging (caution zone)
            if (trending_up or trending_down) and ranging:
                self._stats["conflicts_detected"] += 1
                trending = trending_up or trending_down
                direction = "up" if trending_up else "down"
                return {
                    "symbol": symbol,
                    "conflict_type": "trend_range_divergence",
                    "trending_direction": direction,
                    "trending_timeframes": [tf.value for tf, _ in trending],
                    "ranging_timeframes": [tf.value for tf, _ in ranging],
                    "detected_at_ms": int(time.time() * 1000),
                    "severity": "medium",
                }

            return None

    # ─────────────────────────────────────────────────────────────────────────
    # Stats / 统计
    # ─────────────────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get internal statistics."""
        with self._lock:
            return dict(self._stats)

    def reset_stats(self) -> None:
        """Reset statistics counters."""
        with self._lock:
            for key in self._stats:
                self._stats[key] = 0

    # ─────────────────────────────────────────────────────────────────────────
    # Serialization / 序列化
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Serialize current state to dict."""
        with self._lock:
            current = {}
            for (symbol, tf), snapshot in self._current_regimes.items():
                key = f"{symbol}:{tf.value}"
                current[key] = snapshot.to_dict()

            history = {}
            for (symbol, tf), transitions in self._transition_history.items():
                key = f"{symbol}:{tf.value}"
                history[key] = [t.to_dict() for t in transitions]

            return {
                "current_regimes": current,
                "transition_history": history,
                "stats": dict(self._stats),
            }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())

    def from_dict(self, data: Dict[str, Any]) -> None:
        """Restore state from dict (destructive)."""
        with self._lock:
            self._current_regimes.clear()
            self._transition_history.clear()

            for key_str, snapshot_dict in data.get("current_regimes", {}).items():
                parts = key_str.split(":", 1)
                if len(parts) == 2:
                    symbol, tf_str = parts
                    snapshot = MarketRegimeSnapshot.from_dict(snapshot_dict)
                    self._current_regimes[(symbol, snapshot.timeframe)] = snapshot

            for key_str, transitions_dicts in data.get("transition_history", {}).items():
                parts = key_str.split(":", 1)
                if len(parts) == 2:
                    symbol, tf_str = parts
                    tf = RegimeTimeframe(tf_str)
                    history_deque = deque(maxlen=self._max_history)
                    for t_dict in transitions_dicts:
                        history_deque.append(RegimeTransition.from_dict(t_dict))
                    self._transition_history[(symbol, tf)] = history_deque

            if "stats" in data:
                self._stats.update(data["stats"])

    @classmethod
    def from_json(cls, json_str: str) -> MarketRegimeTracker:
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        tracker = cls()
        tracker.from_dict(data)
        return tracker
