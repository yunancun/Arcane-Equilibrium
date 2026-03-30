"""
Batch 7 — StrategistAgent: AI-enhanced signal evaluation + TradeIntent production
====================================================================================
Governance refs: EX-06 §4, DOC-04 §G Multi-Agent

MODULE_NOTE (中文):
  StrategistAgent 是 5-Agent 体系中的"策略大脑"。
  职责：
  1. 消费 ScoutAgent 产出的 IntelObject 情报
  2. 调用 Qwen 3.5 (judge_edge) 评估信号是否有交易优势
  3. Ollama 不可用时回退到本地启发式规则（fail-closed：不可放行未评估信号）
  4. 产出 TradeIntent 供 Guardian 审查
  5. Shadow 模式：仅记录到审计日志，不产出 intent 到下游

  安全不变量：
  - system_mode = read_only 不变
  - fail-closed：异常时默认拒绝
  - 所有决策写入审计日志
  - Shadow 模式下不产出任何实际 intent

MODULE_NOTE (English):
  StrategistAgent is the "strategy brain" in the 5-Agent system.
  Responsibilities:
  1. Consume IntelObject intelligence from ScoutAgent
  2. Call Qwen 3.5 (judge_edge) to evaluate signal edge quality
  3. Fall back to local heuristics when Ollama unavailable (fail-closed: never pass unevaluated signals)
  4. Produce TradeIntent for Guardian review
  5. Shadow mode: log to audit only, do not produce downstream intents

  Safety invariants:
  - system_mode = read_only (unchanged)
  - fail-closed: reject by default on error
  - All decisions written to audit log
  - Shadow mode produces no actual intents
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .multi_agent_framework import (
    AgentMessage,
    AgentRole,
    AgentState,
    DataQualityLevel,
    IntelObject,
    MessageBus,
    MessageType,
    TradeIntent,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration / 配置
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class StrategistConfig:
    """Configuration for StrategistAgent / StrategistAgent 配置"""
    # Minimum confidence threshold to produce a TradeIntent
    # 产出 TradeIntent 的最低置信度阈值
    min_confidence: float = 0.4
    # Minimum relevance score from Scout intel to consider
    # Scout 情报的最低相关性分数
    min_relevance: float = 0.3
    # Maximum age of intel to evaluate (seconds)
    # 情报的最大可接受年龄（秒）
    max_intel_age_seconds: int = 300
    # Default position size (BTC)
    # 默认仓位大小
    default_size: float = 0.001
    # Shadow mode: log only, do not produce intents to bus
    # 影子模式：仅记录日志，不产出 intent 到消息总线
    shadow: bool = True
    # Maximum pending intents to buffer
    # 最大待处理 intent 缓冲数
    max_pending_intents: int = 50
    # Heuristic thresholds for fallback evaluation
    # 回退评估的启发式阈值
    heuristic_min_relevance: float = 0.6
    heuristic_min_freshness: int = 120  # seconds


# ═══════════════════════════════════════════════════════════════════════════════
# Heuristic Edge Evaluation (Ollama fallback) / 启发式 Edge 评估（Ollama 回退）
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class EdgeEvaluation:
    """Result of edge evaluation (AI or heuristic) / Edge 评估结果"""
    has_edge: bool = False
    confidence: float = 0.0
    reason: str = ""
    source: str = "unknown"  # "ai" or "heuristic"
    latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_edge": self.has_edge,
            "confidence": self.confidence,
            "reason": self.reason,
            "source": self.source,
            "latency_ms": self.latency_ms,
        }


def _heuristic_evaluate(intel: IntelObject, config: StrategistConfig) -> EdgeEvaluation:
    """
    Local heuristic edge evaluation — used when Ollama is unavailable.
    本地启发式 edge 评估 — Ollama 不可用时使用。

    This is deliberately conservative (fail-closed).
    刻意保守（fail-closed）。
    """
    start = time.time()

    # Rule 1: Relevance must be high enough / 相关性必须足够高
    if intel.relevance_score < config.heuristic_min_relevance:
        return EdgeEvaluation(
            has_edge=False,
            confidence=0.0,
            reason=f"Relevance too low: {intel.relevance_score:.2f} < {config.heuristic_min_relevance}",
            source="heuristic",
            latency_ms=(time.time() - start) * 1000,
        )

    # Rule 2: Data must be fresh / 数据必须新鲜
    if intel.freshness_seconds > config.heuristic_min_freshness:
        return EdgeEvaluation(
            has_edge=False,
            confidence=0.0,
            reason=f"Intel too stale: {intel.freshness_seconds}s > {config.heuristic_min_freshness}s",
            source="heuristic",
            latency_ms=(time.time() - start) * 1000,
        )

    # Rule 3: Data quality must be FACT or INFERENCE (not HYPOTHESIS)
    # 数据质量必须是 FACT 或 INFERENCE（不是 HYPOTHESIS）
    if intel.data_quality == DataQualityLevel.HYPOTHESIS:
        return EdgeEvaluation(
            has_edge=False,
            confidence=0.0,
            reason="HYPOTHESIS-quality intel rejected by heuristic",
            source="heuristic",
            latency_ms=(time.time() - start) * 1000,
        )

    # Rule 4: Sentiment must be directional (not NEUTRAL) / 情绪必须有方向性
    from .multi_agent_framework import SentimentScore
    if intel.sentiment == SentimentScore.NEUTRAL:
        return EdgeEvaluation(
            has_edge=False,
            confidence=0.0,
            reason="Neutral sentiment — no directional edge",
            source="heuristic",
            latency_ms=(time.time() - start) * 1000,
        )

    # Rule 5: Must have at least one symbol / 必须至少有一个交易对
    if not intel.symbols:
        return EdgeEvaluation(
            has_edge=False,
            confidence=0.0,
            reason="No symbols in intel",
            source="heuristic",
            latency_ms=(time.time() - start) * 1000,
        )

    # Passed all heuristic checks — conservative confidence
    # 通过所有启发式检查 — 保守置信度
    confidence = min(intel.relevance_score * 0.7, 0.6)  # Cap at 0.6 for heuristic
    return EdgeEvaluation(
        has_edge=True,
        confidence=confidence,
        reason="Heuristic: high relevance + fresh + directional sentiment",
        source="heuristic",
        latency_ms=(time.time() - start) * 1000,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# StrategistAgent / 策略师代理
# ═══════════════════════════════════════════════════════════════════════════════

class StrategistAgent:
    """EX-06 §4 — AI-enhanced strategy evaluation agent.

    Consumes IntelObject from Scout, evaluates signal quality via Qwen 3.5
    (or heuristic fallback), and produces TradeIntent for Guardian review.

    消费 Scout 的 IntelObject，通过 Qwen 3.5（或启发式回退）评估信号质量，
    产出 TradeIntent 供 Guardian 审查。

    Key constraints:
    - Cannot bypass Guardian review (EX-06 §4.3)
    - Cannot modify risk parameters (only Guardian can)
    - Cannot directly place orders (must go via Executor)
    - fail-closed: errors → reject signal
    """

    def __init__(
        self,
        *,
        config: Optional[StrategistConfig] = None,
        message_bus: Optional[MessageBus] = None,
        ollama_client: Optional[Any] = None,
        audit_callback: Optional[Callable] = None,
    ):
        self.config = config or StrategistConfig()
        self.bus = message_bus
        self._ollama = ollama_client
        self._audit_callback = audit_callback
        self.state = AgentState.INITIALIZING
        self._lock = threading.Lock()

        # Pending intents buffer (collected by PipelineBridge)
        # 待处理 intent 缓冲区（由 PipelineBridge 收集）
        self._pending_intents: List[TradeIntent] = []

        # Stats / 统计
        self._stats = {
            "intel_received": 0,
            "intel_evaluated": 0,
            "intents_produced": 0,
            "intents_shadow_logged": 0,
            "ai_evaluations": 0,
            "heuristic_evaluations": 0,
            "evaluations_rejected": 0,
            "errors": 0,
        }

        # Evaluation log (recent evaluations for diagnostics)
        # 评估日志（最近的评估结果，用于诊断）
        self._eval_log: List[Dict[str, Any]] = []
        self._max_eval_log = 100

    # ── Lifecycle / 生命周期 ──

    def start(self) -> None:
        """Start the agent / 启动代理"""
        self.state = AgentState.RUNNING
        logger.info("StrategistAgent started (shadow=%s) / 策略师代理已启动 (shadow=%s)",
                     self.config.shadow, self.config.shadow)

    def pause(self) -> None:
        """Pause the agent / 暂停代理"""
        self.state = AgentState.PAUSED

    def stop(self) -> None:
        """Stop the agent / 停止代理"""
        self.state = AgentState.STOPPED
        logger.info("StrategistAgent stopped / 策略师代理已停止")

    # ── Message Handler / 消息处理 ──

    def on_message(self, message: AgentMessage) -> None:
        """
        Handle incoming messages from MessageBus.
        处理来自消息总线的入站消息。

        Called by MessageBus when a message is delivered to STRATEGIST role.
        当消息被递送到 STRATEGIST 角色时由 MessageBus 调用。
        """
        if self.state != AgentState.RUNNING:
            logger.debug("StrategistAgent not running, ignoring message / 策略师未运行，忽略消息")
            return

        if message.message_type == MessageType.INTEL_OBJECT:
            self._handle_intel(message)
        elif message.message_type == MessageType.RISK_VERDICT:
            self._handle_risk_verdict(message)
        elif message.message_type == MessageType.PATTERN_INSIGHT:
            self._handle_pattern_insight(message)
        elif message.message_type == MessageType.SYSTEM_DIRECTIVE:
            self._handle_directive(message)
        else:
            logger.debug("StrategistAgent ignoring message type: %s", message.message_type)

    def _handle_intel(self, message: AgentMessage) -> None:
        """
        Process an IntelObject from Scout → evaluate edge → optionally produce TradeIntent.
        处理来自 Scout 的 IntelObject → 评估 edge → 可选产出 TradeIntent。
        """
        with self._lock:
            self._stats["intel_received"] += 1

        payload = message.payload
        if not payload:
            logger.warning("Empty intel payload / 空情报负载")
            return

        # Reconstruct IntelObject from payload / 从负载重建 IntelObject
        try:
            intel = IntelObject(
                intel_id=payload.get("intel_id", f"intel_{uuid.uuid4().hex[:12]}"),
                source=payload.get("source", "unknown"),
                timestamp_ms=payload.get("timestamp_ms", int(time.time() * 1000)),
                freshness_seconds=payload.get("freshness_seconds", 0),
                data_quality=DataQualityLevel(payload.get("data_quality", "fact")),
                sentiment=_parse_sentiment(payload.get("sentiment", "neutral")),
                relevance_score=float(payload.get("relevance_score", 0.0)),
                content=payload.get("content", ""),
                symbols=payload.get("symbols", []),
                metadata=payload.get("metadata", {}),
            )
        except Exception as e:
            logger.error("Failed to parse IntelObject: %s / 解析 IntelObject 失败: %s", e, e)
            with self._lock:
                self._stats["errors"] += 1
            return

        # Check minimum relevance / 检查最低相关性
        if intel.relevance_score < self.config.min_relevance:
            logger.debug("Intel below relevance threshold: %.2f < %.2f",
                         intel.relevance_score, self.config.min_relevance)
            return

        # Check age / 检查年龄
        age_seconds = max(0, (int(time.time() * 1000) - intel.timestamp_ms) / 1000)
        if age_seconds > self.config.max_intel_age_seconds:
            logger.debug("Intel too old: %.0fs > %ds", age_seconds, self.config.max_intel_age_seconds)
            return

        # Evaluate edge / 评估 edge
        evaluation = self._evaluate_edge(intel)

        with self._lock:
            self._stats["intel_evaluated"] += 1

        # Log evaluation / 记录评估
        eval_record = {
            "intel_id": intel.intel_id,
            "symbols": intel.symbols,
            "relevance": intel.relevance_score,
            "sentiment": intel.sentiment.value if hasattr(intel.sentiment, 'value') else str(intel.sentiment),
            "evaluation": evaluation.to_dict(),
            "timestamp_ms": int(time.time() * 1000),
        }
        with self._lock:
            self._eval_log.append(eval_record)
            if len(self._eval_log) > self._max_eval_log:
                self._eval_log = self._eval_log[-self._max_eval_log:]

        # Audit / 审计
        self._audit("edge_evaluation", eval_record)

        if not evaluation.has_edge:
            with self._lock:
                self._stats["evaluations_rejected"] += 1
            logger.info("No edge detected for %s (reason: %s) / 未检测到交易优势",
                        intel.symbols, evaluation.reason)
            return

        if evaluation.confidence < self.config.min_confidence:
            with self._lock:
                self._stats["evaluations_rejected"] += 1
            logger.info("Edge confidence too low: %.2f < %.2f / Edge 置信度过低",
                        evaluation.confidence, self.config.min_confidence)
            return

        # Produce TradeIntent(s) for each symbol / 为每个交易对产出 TradeIntent
        from .multi_agent_framework import SentimentScore
        direction = "long" if intel.sentiment == SentimentScore.POSITIVE else "short"

        for symbol in intel.symbols:
            intent = TradeIntent(
                symbol=symbol,
                strategy="strategist_ai" if evaluation.source == "ai" else "strategist_heuristic",
                direction=direction,
                size=self.config.default_size,
                confidence=evaluation.confidence,
                thesis=f"Scout intel: {intel.content[:100]}",
                invalidation_condition=f"Edge confidence drops below {self.config.min_confidence}",
                data_quality=intel.data_quality,
                metadata={
                    "intel_id": intel.intel_id,
                    "evaluation_source": evaluation.source,
                    "evaluation_reason": evaluation.reason,
                    "shadow": self.config.shadow,
                },
            )

            if self.config.shadow:
                # Shadow mode: log only, do not dispatch / 影子模式：仅记录
                with self._lock:
                    self._stats["intents_shadow_logged"] += 1
                self._audit("shadow_intent", intent.to_dict())
                logger.info(
                    "SHADOW intent: %s %s %s conf=%.2f / 影子 intent: %s %s",
                    symbol, direction, evaluation.source,
                    evaluation.confidence, symbol, direction,
                )
            else:
                # Live mode: buffer intent + send to Guardian via bus
                # 实时模式：缓冲 intent + 通过总线发送给 Guardian
                with self._lock:
                    if len(self._pending_intents) < self.config.max_pending_intents:
                        self._pending_intents.append(intent)
                    self._stats["intents_produced"] += 1

                # Send TRADE_INTENT to Guardian for review / 发送 TRADE_INTENT 给 Guardian 审查
                if self.bus:
                    msg = AgentMessage(
                        sender=AgentRole.STRATEGIST,
                        receiver=AgentRole.GUARDIAN,
                        message_type=MessageType.TRADE_INTENT,
                        priority=3,
                        payload=intent.to_dict(),
                    )
                    self.bus.send(msg)

                self._audit("intent_produced", intent.to_dict())
                logger.info(
                    "TradeIntent produced: %s %s %s conf=%.2f / TradeIntent 已产出",
                    symbol, direction, evaluation.source, evaluation.confidence,
                )

    def _handle_risk_verdict(self, message: AgentMessage) -> None:
        """Handle Guardian's risk verdict feedback / 处理 Guardian 风险裁决反馈"""
        self._audit("risk_verdict_received", message.payload)
        logger.info("Received risk verdict: %s", message.payload.get("result", "unknown"))

    def _handle_pattern_insight(self, message: AgentMessage) -> None:
        """Handle Analyst's pattern insight feedback / 处理 Analyst 模式洞察反馈"""
        self._audit("pattern_insight_received", message.payload)
        logger.info("Received pattern insight from Analyst")

    def _handle_directive(self, message: AgentMessage) -> None:
        """Handle Conductor system directive / 处理 Conductor 系统指令"""
        directive_type = message.payload.get("directive_type", "")
        if directive_type == "shadow_on":
            self.config.shadow = True
            logger.info("StrategistAgent shadow mode ON / 策略师影子模式开启")
        elif directive_type == "shadow_off":
            self.config.shadow = False
            logger.info("StrategistAgent shadow mode OFF / 策略师影子模式关闭")
        self._audit("directive_received", message.payload)

    # ── Edge Evaluation / Edge 评估 ──

    def _evaluate_edge(self, intel: IntelObject) -> EdgeEvaluation:
        """
        Evaluate whether intel contains a tradeable edge.
        评估情报是否包含可交易优势。

        Strategy:
        1. Try Ollama/Qwen 3.5 judge_edge() first
        2. If Ollama unavailable or errors → fallback to local heuristic
        3. Never return has_edge=True without evaluation (fail-closed)
        """
        # Try AI evaluation first / 先尝试 AI 评估
        if self._ollama and self._ollama.is_available():
            try:
                return self._ai_evaluate(intel)
            except Exception as e:
                logger.warning("AI evaluation failed, falling back to heuristic: %s / AI 评估失败，回退到启发式: %s", e, e)
                with self._lock:
                    self._stats["errors"] += 1

        # Fallback to heuristic / 回退到启发式
        with self._lock:
            self._stats["heuristic_evaluations"] += 1
        return _heuristic_evaluate(intel, self.config)

    def _ai_evaluate(self, intel: IntelObject) -> EdgeEvaluation:
        """
        Evaluate edge using Qwen 3.5 via judge_edge().
        使用 Qwen 3.5 的 judge_edge() 评估 edge。
        """
        start = time.time()

        # Build market context for judge_edge / 构建 judge_edge 的市场上下文
        context = (
            f"Symbol(s): {', '.join(intel.symbols)}\n"
            f"Source: {intel.source}\n"
            f"Sentiment: {intel.sentiment.value if hasattr(intel.sentiment, 'value') else intel.sentiment}\n"
            f"Relevance: {intel.relevance_score:.2f}\n"
            f"Data quality: {intel.data_quality.value if hasattr(intel.data_quality, 'value') else intel.data_quality}\n"
            f"Freshness: {intel.freshness_seconds}s ago\n"
            f"Content: {intel.content[:500]}"
        )

        response = self._ollama.judge_edge(context)
        latency_ms = (time.time() - start) * 1000

        with self._lock:
            self._stats["ai_evaluations"] += 1

        if not response.success:
            logger.warning("judge_edge returned unsuccessful: %s / judge_edge 返回失败", response.error)
            # Fail-closed: fall back to heuristic / fail-closed：回退到启发式
            with self._lock:
                self._stats["heuristic_evaluations"] += 1
            return _heuristic_evaluate(intel, self.config)

        # Parse JSON response / 解析 JSON 响应
        try:
            # Try to extract JSON from response text
            text = response.text.strip()
            # Handle potential markdown code blocks
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            result = json.loads(text)
            has_edge = bool(result.get("has_edge", False))
            confidence = float(result.get("confidence", 0.0))
            reason = str(result.get("reason", "AI evaluation"))

            return EdgeEvaluation(
                has_edge=has_edge,
                confidence=confidence,
                reason=reason,
                source="ai",
                latency_ms=latency_ms,
            )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("Failed to parse judge_edge response: %s / 解析 judge_edge 响应失败: %s", e, e)
            # Fail-closed: cannot parse AI output → reject / fail-closed：无法解析 AI 输出 → 拒绝
            return EdgeEvaluation(
                has_edge=False,
                confidence=0.0,
                reason=f"AI response parse error: {e}",
                source="ai_parse_error",
                latency_ms=latency_ms,
            )

    # ── Intent Collection (for PipelineBridge) / Intent 收集 ──

    def collect_pending_intents(self) -> List[TradeIntent]:
        """
        Collect and clear pending intents (called by PipelineBridge).
        收集并清除待处理的 intents（由 PipelineBridge 调用）。
        """
        with self._lock:
            intents = list(self._pending_intents)
            self._pending_intents.clear()
        return intents

    # ── Audit / 审计 ──

    def _audit(self, event_type: str, data: Any) -> None:
        """Write audit record / 写入审计记录"""
        if self._audit_callback:
            try:
                self._audit_callback(f"strategist_{event_type}", data)
            except Exception as e:
                logger.debug("Audit callback error: %s", e)

    # ── Status / 状态 ──

    def get_stats(self) -> Dict[str, Any]:
        """Get agent statistics / 获取代理统计"""
        with self._lock:
            return {
                "role": AgentRole.STRATEGIST.value,
                "state": self.state.value,
                "shadow": self.config.shadow,
                "pending_intents": len(self._pending_intents),
                **dict(self._stats),
            }

    def get_recent_evaluations(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent edge evaluations for diagnostics / 获取最近的 edge 评估用于诊断"""
        with self._lock:
            return list(self._eval_log[-limit:])


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers / 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_sentiment(value: str) -> Any:
    """Parse sentiment string to SentimentScore enum / 解析情绪字符串为 SentimentScore 枚举"""
    from .multi_agent_framework import SentimentScore
    try:
        return SentimentScore(value)
    except (ValueError, KeyError):
        return SentimentScore.NEUTRAL
