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
import warnings
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
        cost_tracker: Optional[Any] = None,
    ):
        self.config = config or StrategistConfig()
        self.bus = message_bus
        self._ollama = ollama_client
        self._audit_callback = audit_callback
        self.state = AgentState.INITIALIZING
        self._lock = threading.Lock()

        # cost_tracker: injected externally; None = no budget tracking
        # cost_tracker：外部注入；None 表示不做預算追蹤（fail-open）
        self.cost_tracker = cost_tracker

        # H1 cooldown: per-symbol last-intel timestamp for 30-second dedup
        # H1 冷卻期記錄：每個幣種上次情報時間戳，30 秒內重複信號跳過 AI
        self._h1_cooldown: Dict[str, float] = {}

        # Truth Source Registry: injected externally for pattern-driven weight updates
        # 知識登記表：外部注入，用於模式洞察驅動的策略權重更新（Principle 7 隔離）
        self._truth_registry: Optional[Any] = None

        # Strategy preference weights: 1.0 = neutral, >1.0 = preferred, <1.0 = avoid
        # 策略偏好權重：1.0=中性，>1.0=偏好，<1.0=迴避。範圍限幅 [0.2, 2.0]
        self._strategy_preference_weights: Dict[str, float] = {}

        # L2 result cache: stores background L2 evaluation results for use in next decision cycle.
        # L2 結果快取：儲存後台 L2 評估結果，供下次決策週期使用（避免 L2 計算資源浪費）。
        # Key: symbol string; Value: dict with "evaluation", "timestamp", "intel_id".
        # TTL: 3600s (1 hour) — L2 results become stale after this window.
        # 鍵：幣種字串；值：包含 evaluation/timestamp/intel_id 的字典。TTL 1 小時。
        self._l2_result_cache: Dict[str, Dict[str, Any]] = {}
        self._l2_cache_lock = threading.Lock()
        self._L2_CACHE_TTL_S: float = 3600.0  # 1 hour / 1 小時
        self._L2_CACHE_MAX_SIZE: int = 200  # cap to prevent unbounded growth / 上限防止無限增長

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
            # H1 ThoughtGate skip counters / H1 思考閘門跳過計數器
            "h1_budget_skip": 0,
            "h1_complexity_skip": 0,
            "h1_cooldown_skip": 0,
            # H4 output validation counter / H4 輸出驗證拒絕計數器
            "h4_validation_fail": 0,
            # H5 Ollama cost tracking counter / H5 Ollama 調用計數
            "ollama_calls_tracked": 0,
            # L2 cache counters / L2 快取計數器
            "l2_cache_stored": 0,
            "l2_cache_hit": 0,
            "l2_cache_expired": 0,
            "l2_cache_weight_applied": 0,
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

    # ── H1 ThoughtGate Methods / H1 思考閘門方法 ──
    # All three methods are synchronous — required by MessageBus callback constraint.
    # 全部同步方法 — MessageBus 回調不可使用 await，此處嚴格遵守。

    def _h1_check_budget(self) -> bool:
        """
        H1 budget check: return True if AI call is affordable.
        H1 預算檢查：若 AI 調用在預算內則返回 True，否則降級到啟發式評估。

        If cost_tracker is None, fail-open and allow AI call.
        若 cost_tracker 為 None，fail-open 允許 AI 調用（向後兼容無預算追蹤部署）。

        If cost_tracker.check_daily_budget() returns (False, _), budget is exceeded.
        若 check_daily_budget() 返回 (False, _)，表示預算已超，降級到啟發式。
        """
        if self.cost_tracker is None:
            # fail-open: no tracker means no budget constraint
            # fail-open：無追蹤器表示無預算限制
            return True
        try:
            allowed, _ = self.cost_tracker.check_daily_budget()
            return allowed
        except Exception:
            # fail-open: tracker error must not block evaluation
            # fail-open：追蹤器異常不得阻止評估
            return True

    def _h1_complexity_score(self, intel: Any) -> float:
        """
        H1 complexity scoring: rule-based, synchronous, no AI calls.
        H1 複雜度評分：純規則，同步執行，不調用 AI。

        Returns 0.0–1.0. Score < 0.3 means signal is too simple for AI evaluation.
        返回 0.0–1.0。分數 < 0.3 表示信號過於簡單，不值得調用 AI。

        Base score from Scout's relevance_score; boosted by multi-symbol and urgency.
        基礎分數來自 Scout 的 relevance_score；多幣種或高緊迫度時加分。
        """
        score = intel.relevance_score  # base from Scout / Scout 基礎分數
        # Boost for multiple symbols: broader market signals warrant AI attention
        # 多幣種加分：較廣泛的市場信號值得 AI 關注
        if len(intel.symbols) > 3:
            score = min(1.0, score + 0.2)
        # Boost for high-urgency metadata signals
        # 高緊迫度元數據加分
        if getattr(intel, "metadata", {}).get("urgency") == "high":
            score = min(1.0, score + 0.2)
        return score

    # Capacity cap for _h1_cooldown: prevent unbounded growth in multi-symbol scenarios.
    # _h1_cooldown 容量上限：防止掃描大量幣種時字典無限增長（記憶體安全保護）。
    _H1_COOLDOWN_MAX_SIZE: int = 1000

    def _h1_check_cooldown(self, intel: Any) -> bool:
        """
        H1 cooldown check: return True if symbol is not in cooldown window.
        H1 冷卻期檢查：同一符號 30 秒內重複信號跳過 AI，避免頻繁調用。

        Returns True if AI call is allowed, False if any symbol is in cooldown.
        若任意幣種在冷卻期內則返回 False（跳過 AI）；否則更新時間戳並返回 True。

        TD-4: Capacity protection — when dict exceeds _H1_COOLDOWN_MAX_SIZE, evict
        all expired entries first (entries older than 30s cooldown window). This is
        preferred over hard LRU eviction because expired entries carry no business
        value and cleaning them is semantically correct.
        TD-4: 容量保護 — 字典超過 _H1_COOLDOWN_MAX_SIZE 時，先清理所有已過期條目
        （超過 30 秒冷卻窗口的條目）。優先選擇過期清理而非 LRU 強制淘汰，
        因為過期條目已無業務價值，清理行為語義正確。
        """
        now = time.time()

        # TD-4: Capacity guard — evict expired entries before inserting new ones.
        # Triggered only when at cap to keep hot-path cost minimal.
        # TD-4: 容量守衛 — 超過上限時才執行過期清理，保持熱路徑開銷最小。
        if len(self._h1_cooldown) >= self._H1_COOLDOWN_MAX_SIZE:
            # Collect keys to evict: entries older than 30s cooldown window.
            # 收集要清理的鍵：超過 30 秒冷卻窗口的條目。
            expired_keys = [
                sym for sym, ts in self._h1_cooldown.items()
                if now - ts >= 30.0
            ]
            for sym in expired_keys:
                del self._h1_cooldown[sym]
            if expired_keys:
                logger.debug(
                    "TD-4 _h1_cooldown evicted %d expired entries, size now %d / "
                    "已清理 %d 個過期條目，當前大小 %d",
                    len(expired_keys), len(self._h1_cooldown),
                    len(expired_keys), len(self._h1_cooldown),
                )

        for symbol in intel.symbols:
            last = self._h1_cooldown.get(symbol, 0.0)
            if now - last < 30.0:
                # Symbol still in cooldown window — skip AI
                # 幣種仍在冷卻期 — 跳過 AI
                return False
        # All symbols passed cooldown check — update timestamps
        # 所有幣種通過冷卻期檢查 — 更新時間戳
        for symbol in intel.symbols:
            self._h1_cooldown[symbol] = now
        return True

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

        # ── L2 cache check: use previous L2 background result if available ──
        # L2 快取檢查：若之前的 L2 後台評估已完成且未過期，直接使用其結果
        # APR01-MEDIUM-9: This is the consumption side of the L2 cache — previous L2 background
        # threads stored results that we now retrieve, ensuring L2 compute is not wasted.
        # APR01-MEDIUM-9：這是 L2 快取的消費端 — 之前的 L2 後台線程儲存了結果，
        # 現在我們檢索它們，確保 L2 計算資源不被浪費。
        l2_cached = None
        for sym in intel.symbols:
            l2_cached = self._check_l2_cache(sym)
            if l2_cached is not None:
                break
        if l2_cached is not None:
            # Use cached L2 result directly — skip H1 gate and model routing
            # 直接使用快取的 L2 結果 — 跳過 H1 閘門和模型路由
            evaluation = l2_cached
            logger.info(
                "Using cached L2 result for %s (confidence=%.2f) / 使用快取 L2 結果",
                intel.symbols, evaluation.confidence,
            )
        else:
            # ── H1 ThoughtGate: pre-AI determination gate (synchronous, no await) ──
            # H1 思考閘門：AI 調用前的確定性判斷，全部同步執行，符合 MessageBus 回調限制。
            # CC 原則 6：should_call_ai=False 時必須走啟發式評估，不可直接 allow-all 或 return。
            should_call_ai = True

            if not self._h1_check_budget():
                with self._lock:
                    self._stats["h1_budget_skip"] += 1
                should_call_ai = False

            if should_call_ai and self._h1_complexity_score(intel) < 0.3:
                with self._lock:
                    self._stats["h1_complexity_skip"] += 1
                should_call_ai = False

            if should_call_ai and not self._h1_check_cooldown(intel):
                with self._lock:
                    self._stats["h1_cooldown_skip"] += 1
                should_call_ai = False

            if not should_call_ai:
                # Principle 6: fail-closed means use conservative heuristic, NOT allow-all
                # 原則 6：失敗默認收縮 — 降級用啟發式評估，不可直接放行（allow-all 等於失去治理）
                evaluation = _heuristic_evaluate(intel, self.config)
                with self._lock:
                    self._stats["heuristic_evaluations"] += 1
            else:
                # H3 ModelRouter: select model tier based on signal complexity
                # H3 模型路由：根據信號複雜度選擇模型層，平衡速度與精度
                model_tier = self._h3_route_model(intel)
                if model_tier == "l2":
                    # L2 must run in background thread — cannot block synchronous on_tick callback
                    # L2 必須在後台線程執行，避免阻塞 MessageBus 的同步 on_tick 回調
                    threading.Thread(
                        target=self._evaluate_edge_l2,
                        args=(intel,),
                        daemon=True,
                    ).start()
                    # Use heuristic as immediate result; L2 result cached for next cycle
                    # 立即使用啟發式結果；L2 結果快取供下次週期使用
                    evaluation = _heuristic_evaluate(intel, self.config)
                    with self._lock:
                        self._stats["heuristic_evaluations"] += 1
                else:
                    # L1 runs synchronously with timeout — acceptable blocking window
                    # L1 同步執行，有 timeout 保護，阻塞時間可接受
                    try:
                        evaluation = self._evaluate_edge(intel)
                    except Exception as _edge_exc:
                        # fail-closed: any unexpected error in evaluate_edge → heuristic fallback
                        # fail-closed：evaluate_edge 任何異常 → 啟發式回退，不得拋出到外層
                        logger.warning(
                            "_evaluate_edge raised %s, falling back to heuristic / "
                            "_evaluate_edge 拋出 %s，回退到啟發式",
                            type(_edge_exc).__name__, type(_edge_exc).__name__,
                        )
                        with self._lock:
                            self._stats["errors"] += 1
                            self._stats["heuristic_evaluations"] += 1
                        evaluation = _heuristic_evaluate(intel, self.config)

                # H5 light: record Ollama call for cost tracking (Ollama is free, track call count)
                # H5 輕量版：記錄 Ollama 調用以追蹤調用次數（Ollama 免費，僅計次）
                # Uses record_call() if available; cost tracking failure must never block execution.
                # 使用 record_call()（若存在）；成本追蹤失敗不得阻塞執行。
                if self.cost_tracker is not None and model_tier != "l2":
                    try:
                        _record = getattr(self.cost_tracker, "record_call", None)
                        if _record is not None:
                            _record(model="l1_9b", cost_usd=0.0)
                    except Exception as e:
                        # TD-3: Log cost tracking failures instead of silently swallowing them.
                        # H5 成本記錄失敗不應靜默忽略，改為 warning 日誌以便追蹤問題。
                        logger.warning(
                            "H5 cost record failed for model l1_9b: %s / H5 成本記錄失敗", e
                        )

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
            # Apply strategy preference weight learned from TruthSourceRegistry (Principle 12)
            # 應用來自 TruthSourceRegistry 學習所得的策略偏好權重（原則 12 持續進化）
            # Weight > 1.0 = preferred by backtest evidence; < 1.0 = avoid.
            # 權重 > 1.0 表示回測證據偏好；< 1.0 表示應迴避。
            # Strategy key: try symbol-level first, then "strategist_ai" / "strategist_heuristic"
            # 策略鍵：先嘗試幣種級別，再用 evaluation.source 對應的策略名稱
            strategy_key = f"{evaluation.source}_{symbol}" if evaluation.source else symbol
            weight = self._strategy_preference_weights.get(strategy_key, None)
            if weight is None:
                # Fallback to source-based strategy key (e.g. "strategist_ai" or "strategist_heuristic")
                # 回退到基於 source 的策略鍵
                source_key = "strategist_ai" if evaluation.source == "ai" else "strategist_heuristic"
                weight = self._strategy_preference_weights.get(source_key, 1.0)
            # Clamp adjusted_confidence to [0.0, 1.0]; weight range is [0.2, 2.0] (enforced by _apply_pattern_insight)
            # 限幅 adjusted_confidence 至 [0.0, 1.0]；權重範圍 [0.2, 2.0] 由 _apply_pattern_insight 保證
            adjusted_confidence = min(1.0, evaluation.confidence * weight)
            if adjusted_confidence != evaluation.confidence:
                logger.debug(
                    "Strategy weight applied for %s: %.2f × %.2f = %.2f / "
                    "策略偏好權重已應用：原始置信度 %.2f × 權重 %.2f = 調整後 %.2f",
                    symbol, evaluation.confidence, weight, adjusted_confidence,
                    evaluation.confidence, weight, adjusted_confidence,
                )
            # Use weight-adjusted confidence for TradeIntent; raw confidence preserved in metadata
            # 使用調整後的置信度構建 TradeIntent；原始置信度保留在 metadata 以便審計
            intent = TradeIntent(
                symbol=symbol,
                strategy="strategist_ai" if evaluation.source == "ai" else "strategist_heuristic",
                direction=direction,
                size=self.config.default_size,
                confidence=adjusted_confidence,  # weight-adjusted / 經策略偏好權重調整
                thesis=f"Scout intel: {intel.content[:100]}",
                invalidation_condition=f"Edge confidence drops below {self.config.min_confidence}",
                data_quality=intel.data_quality,
                metadata={
                    "intel_id": intel.intel_id,
                    "evaluation_source": evaluation.source,
                    "evaluation_reason": evaluation.reason,
                    "raw_confidence": evaluation.confidence,       # original pre-weight / 調整前原始值
                    "strategy_weight": weight,                     # applied weight / 實際乘數
                    "shadow": self.config.shadow,
                },
            )

            if self.config.shadow:
                # Shadow mode: log only, do not dispatch / 影子模式：仅记录
                with self._lock:
                    self._stats["intents_shadow_logged"] += 1
                self._audit("shadow_intent", intent.to_dict())
                logger.info(
                    "SHADOW intent: %s %s %s conf=%.2f (raw=%.2f weight=%.2f) / "
                    "影子 intent: %s %s 調整置信度=%.2f",
                    symbol, direction, evaluation.source,
                    adjusted_confidence, evaluation.confidence, weight,
                    symbol, direction, adjusted_confidence,
                )
            else:
                # Live mode: send intent to Guardian via bus (MessageBus is the authoritative path)
                # 实时模式：通过总线将 intent 发送给 Guardian（MessageBus 是权威路径）
                with self._lock:
                    # DEPRECATED: direct collect path — intent already sent via MessageBus below (TD-2)
                    # 已廢棄：直接收集路徑 — intent 已通過下方的 MessageBus 發送，不應重複入隊
                    # Do not add to _pending_intents; collect path is being phased out (TD-2)
                    # 不應加入 _pending_intents；collect 路徑正在逐步廢棄（TD-2）
                    # DEPRECATED: self._pending_intents.append(intent)
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
                    "TradeIntent produced: %s %s %s conf=%.2f (raw=%.2f weight=%.2f) / "
                    "TradeIntent 已產出：調整置信度=%.2f",
                    symbol, direction, evaluation.source,
                    adjusted_confidence, evaluation.confidence, weight,
                    adjusted_confidence,
                )

    def _handle_risk_verdict(self, message: AgentMessage) -> None:
        """Handle Guardian's risk verdict feedback / 处理 Guardian 风险裁决反馈"""
        self._audit("risk_verdict_received", message.payload)
        logger.info("Received risk verdict: %s", message.payload.get("result", "unknown"))

    def set_truth_registry(self, registry: Any) -> None:
        """
        Inject TruthSourceRegistry for pattern-driven strategy weight updates.
        注入知識登記表，供模式洞察更新策略偏好權重使用。

        Principle 7: registry only influences recommendation weights,
        never modifies strategy parameters or risk thresholds directly.
        原則 7：登記表只影響建議權重，不直接修改策略參數或風控閾值。
        """
        self._truth_registry = registry

    def _apply_pattern_insight(self, insight_payload: dict) -> None:
        """
        Apply pattern insight to update strategy preference weights.
        將模式洞察應用到策略偏好權重更新。

        Queries active claims from registry for current regime,
        adjusts weights by ±0.1 × confidence, clamped to [0.2, 2.0].
        從登記表查詢當前 regime 的有效聲明，按 ±0.1×信度調整權重，限幅 [0.2, 2.0]。

        Fail-open: any error → log warning, leave weights unchanged.
        失敗開放：任何異常 → 記錄警告，不改變現有權重。
        """
        if self._truth_registry is None:
            return
        try:
            # Pass regime=None to get all active claims regardless of regime
            # 傳入 regime=None 以取得所有有效聲明，不限制 regime 過濾
            claims = self._truth_registry.get_active_claims(
                regime=None, min_confidence=0.5
            )
            for claim in claims:
                strategy = claim.applies_to_strategy
                if strategy == "all":
                    continue
                current = self._strategy_preference_weights.get(strategy, 1.0)
                # winning patterns → increase weight, losing → decrease
                # 贏家模式 → 增加權重，輸家模式 → 降低權重
                delta = 0.1 * claim.confidence
                if "losing" in claim.pattern_text.lower():
                    delta = -delta
                new_weight = max(0.2, min(2.0, current + delta))
                self._strategy_preference_weights[strategy] = new_weight
        except Exception as e:
            logger.warning("_apply_pattern_insight failed (fail-open): %s", e)

    def _handle_pattern_insight(self, message: AgentMessage) -> None:
        """Handle Analyst's pattern insight feedback / 处理 Analyst 模式洞察反馈"""
        self._audit("pattern_insight_received", message.payload)
        logger.info("Received pattern insight from Analyst")
        self._apply_pattern_insight(message.payload)

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

    # ── H3 ModelRouter + L2 Background Evaluation / H3 模型路由 + L2 背景評估 ──

    def _h3_route_model(self, intel: Any) -> str:
        """
        H3 ModelRouter: select model tier based on signal complexity.
        H3 模型路由：根據信號複雜度選擇模型層，平衡速度與精度。

        Returns: 'l1_9b' | 'l1_27b' | 'l2'
        - l1_9b  → complexity < 0.5  (fast, simple signals)
        - l1_27b → 0.5 <= complexity < 0.8 (moderate complexity)
        - l2     → complexity >= 0.8  (high complexity, runs in background thread)

        L2 MUST be dispatched in threading.Thread to avoid blocking on_tick.
        L2 必須在 threading.Thread 中執行，不可阻塞 on_tick 主線程。
        """
        complexity = self._h1_complexity_score(intel)
        if complexity >= 0.8:
            return "l2"
        elif complexity >= 0.5:
            return "l1_27b"
        else:
            return "l1_9b"

    def _evaluate_edge_l2(self, intel: Any) -> None:
        """
        Async L2 evaluation executed in a background daemon thread.
        Results are cached per-symbol so the next decision cycle can benefit from
        the deeper L2 analysis (APR01-MEDIUM-9 fix: previously results were discarded).
        在後台 daemon 線程執行的 L2 深度評估。
        結果按幣種快取，供下次決策週期使用（APR01-MEDIUM-9 修復：之前結果被完全丟棄）。

        This method must NEVER be called from the main on_tick callback path.
        此方法絕對不能從 on_tick 主回調路徑直接調用。

        Cache flow / 快取流程：
        1. L2 completes → result stored in _l2_result_cache[symbol]
        2. Next _handle_intel() for same symbol → _check_l2_cache() finds cached result
        3. Cached L2 evaluation replaces heuristic/L1 evaluation if still within TTL
        4. High-confidence L2 results also update _strategy_preference_weights
        """
        try:
            result = self._evaluate_edge(intel)
            logger.info(
                "L2 async result for %s: has_edge=%s confidence=%.2f / L2 異步結果",
                intel.symbols, result.has_edge, result.confidence,
            )
            # Store L2 result in cache for each symbol — next decision cycle can use it.
            # 將 L2 結果存入快取（按幣種），下次決策週期可使用深度 AI 分析結果。
            self._store_l2_result(intel, result)
        except Exception as e:
            # Log and swallow — background thread must not crash
            # 記錄並吞掉異常 — 後台線程不得崩潰
            logger.warning("L2 async evaluation failed: %s", type(e).__name__)

    def _store_l2_result(self, intel: Any, evaluation: EdgeEvaluation) -> None:
        """
        Store L2 background evaluation result in per-symbol cache.
        將 L2 後台評估結果存入按幣種的快取。

        Also updates _strategy_preference_weights when L2 provides high-confidence
        directional signal — this is the primary value-capture mechanism for L2 compute.
        當 L2 提供高信心方向性信號時，同步更新策略偏好權重 — 這是 L2 計算資源的主要價值捕獲機制。

        Thread-safe: uses dedicated _l2_cache_lock (separate from main _lock to avoid contention).
        線程安全：使用專用 _l2_cache_lock（與主 _lock 分離以避免競爭）。

        Fail-open: any error in cache storage does not affect system behavior.
        失敗開放：快取儲存的任何異常不影響系統行為。
        """
        try:
            now = time.time()
            cache_entry = {
                "evaluation": evaluation,
                "timestamp": now,
                "intel_id": getattr(intel, "intel_id", "unknown"),
            }

            with self._l2_cache_lock:
                # Capacity guard: evict expired entries when at cap
                # 容量守衛：超過上限時清理過期條目
                if len(self._l2_result_cache) >= self._L2_CACHE_MAX_SIZE:
                    expired = [
                        k for k, v in self._l2_result_cache.items()
                        if now - v["timestamp"] >= self._L2_CACHE_TTL_S
                    ]
                    for k in expired:
                        del self._l2_result_cache[k]

                for symbol in getattr(intel, "symbols", []):
                    self._l2_result_cache[symbol] = cache_entry

            with self._lock:
                self._stats["l2_cache_stored"] += 1

            # High-confidence L2 results update strategy preference weights
            # 高信心 L2 結果更新策略偏好權重（原則 12：持續進化）
            if evaluation.has_edge and evaluation.confidence >= 0.6:
                self._apply_l2_weight_update(intel, evaluation)

            logger.debug(
                "L2 result cached for %s (confidence=%.2f, has_edge=%s) / "
                "L2 結果已快取（信心=%.2f，有邊際=%s）",
                getattr(intel, "symbols", []), evaluation.confidence,
                evaluation.has_edge, evaluation.confidence, evaluation.has_edge,
            )
        except Exception as e:
            # Fail-open: cache write failure must not affect system
            # 失敗開放：快取寫入失敗不影響系統運作
            logger.warning("_store_l2_result failed (fail-open): %s / L2 快取寫入失敗", e)

    def _apply_l2_weight_update(self, intel: Any, evaluation: EdgeEvaluation) -> None:
        """
        Update strategy preference weights based on high-confidence L2 evaluation.
        根據高信心 L2 評估更新策略偏好權重。

        L2 is the deepest AI analysis tier — its high-confidence results carry more
        signal than L1 heuristics, so weight adjustments are ±0.15 (vs ±0.1 for pattern insights).
        L2 是最深層的 AI 分析 — 高信心結果比 L1 啟發式攜帶更多信號，
        因此權重調整為 ±0.15（相比模式洞察的 ±0.1 更大）。

        Weight range clamped to [0.2, 2.0] consistent with _apply_pattern_insight.
        權重範圍限幅 [0.2, 2.0]，與 _apply_pattern_insight 一致。
        """
        try:
            for symbol in getattr(intel, "symbols", []):
                strategy_key = f"ai_{symbol}"
                with self._lock:
                    current = self._strategy_preference_weights.get(strategy_key, 1.0)
                    # L2 confirmed edge → boost weight; L2 rejected → reduce weight
                    # L2 確認有邊際 → 提高權重；L2 拒絕 → 降低權重
                    delta = 0.15 * evaluation.confidence if evaluation.has_edge else -0.1
                    new_weight = max(0.2, min(2.0, current + delta))
                    self._strategy_preference_weights[strategy_key] = new_weight
                    self._stats["l2_cache_weight_applied"] += 1
                logger.debug(
                    "L2 weight update for %s: %.2f → %.2f (delta=%.3f) / "
                    "L2 權重更新：%.2f → %.2f",
                    strategy_key, current, new_weight, delta, current, new_weight,
                )
        except Exception as e:
            # Fail-open: weight update failure must not crash background thread
            # 失敗開放：權重更新失敗不得崩潰後台線程
            logger.warning("_apply_l2_weight_update failed (fail-open): %s", e)

    def _check_l2_cache(self, symbol: str) -> Optional[EdgeEvaluation]:
        """
        Check if a valid (non-expired) L2 result exists for this symbol.
        檢查此幣種是否有尚未過期的 L2 快取結果。

        Returns the cached EdgeEvaluation if found and within TTL, else None.
        若找到且在 TTL 內則返回快取的 EdgeEvaluation，否則返回 None。

        Fail-open: any error reading cache → return None (proceed without L2 input).
        失敗開放：讀取快取的任何異常 → 返回 None（不使用 L2 輸入繼續）。
        """
        try:
            now = time.time()
            with self._l2_cache_lock:
                entry = self._l2_result_cache.get(symbol)
                if entry is None:
                    return None
                age = now - entry["timestamp"]
                if age >= self._L2_CACHE_TTL_S:
                    # Expired — remove and return None
                    # 已過期 — 移除並返回 None
                    del self._l2_result_cache[symbol]
                    with self._lock:
                        self._stats["l2_cache_expired"] += 1
                    return None
                with self._lock:
                    self._stats["l2_cache_hit"] += 1
                return entry["evaluation"]
        except Exception as e:
            # Fail-open: cache read failure → proceed without L2
            # 失敗開放：快取讀取失敗 → 不使用 L2 繼續
            logger.warning("_check_l2_cache failed (fail-open): %s / L2 快取讀取失敗", e)
            return None

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

    def _validate_ai_output(self, parsed: dict) -> bool:
        """
        H4 validation: verify AI output structure before constructing EdgeEvaluation.
        H4 輸出驗證：在構造 EdgeEvaluation 前確認 AI 輸出結構完整且合理。

        Returns True if valid, False if output should be rejected (fallback to heuristic).
        返回 True 表示有效，False 表示應拒絕並降級到啟發式評估。

        Principle 6: reject → heuristic, never allow-all.
        原則 6：拒絕時走啟發式，不可直接放行（allow-all 等於放棄治理）。

        Validates:
        - parsed must be a dict (not list, string, None, etc.)
        - 'confidence' key must be present (primary safety-critical field)
        - confidence must be a numeric type
        - confidence must be in [0.0, 1.0] range
        驗證項目：
        - parsed 必須是 dict（不可是 list、string、None 等）
        - 必須包含 'confidence' 鍵（主要安全關鍵字段）
        - confidence 必須是數值型別
        - confidence 必須在 [0.0, 1.0] 範圍內
        """
        if not isinstance(parsed, dict):
            return False
        if "confidence" not in parsed:
            return False
        confidence = parsed.get("confidence", -1)
        if not isinstance(confidence, (int, float)):
            return False
        if not (0.0 <= float(confidence) <= 1.0):
            return False
        return True

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

            # H4: Validate AI output structure — principle 6: invalid → heuristic, never allow-all
            # H4 輸出驗證：結構不合格則降級啟發式，根原則 6（失敗默認收縮）
            if not self._validate_ai_output(result):
                logger.warning(
                    "H4 validation failed for AI output (missing/invalid confidence), "
                    "falling back to heuristic / H4 驗證失敗，降級到啟發式"
                )
                with self._lock:
                    self._stats["h4_validation_fail"] = self._stats.get("h4_validation_fail", 0) + 1
                    self._stats["heuristic_evaluations"] += 1
                return _heuristic_evaluate(intel, self.config)

            has_edge = bool(result.get("has_edge", False))
            confidence = float(result.get("confidence", 0.0))
            reason = str(result.get("reason", "AI evaluation"))

            # H5: Record Ollama call for cost/resource awareness (principle 13)
            # H5 成本感知：記錄 Ollama 調用，支持 AI 使用效果評估（根原則 13）
            if self.cost_tracker is not None:
                try:
                    record_fn = getattr(self.cost_tracker, "record_ollama_call", None)
                    if record_fn is not None:
                        record_fn(model="l1_9b", duration_ms=latency_ms)
                    with self._lock:
                        self._stats["ollama_calls_tracked"] += 1
                except Exception:
                    # Cost recording failure must not block execution — principle 13 is observational
                    # 成本記錄失敗不可阻擋執行，根原則 13 是觀察性要求
                    logger.warning("cost_tracker.record_ollama_call failed, non-fatal / 成本記錄失敗，非致命")

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
        [DEPRECATED] Collect and clear pending intents (called by PipelineBridge).
        This method is deprecated as of TD-2. Intents are now routed exclusively via
        MessageBus (TRADE_INTENT → GuardianAgent → ExecutorAgent). This method always
        returns an empty list to prevent double-submission of intents.

        [已廢棄] 收集並清除待處理的 intents（原由 PipelineBridge 調用）。
        自 TD-2 起此方法已廢棄。Intent 現在完全通過 MessageBus 路由
        （TRADE_INTENT → GuardianAgent → ExecutorAgent）。
        此方法始終返回空列表，以防止 intent 雙重提交。

        Reason for deprecation / 廢棄原因：
          shadow=False 時 intent 走了兩條路徑（MessageBus + collect），導致同一個 intent 雙重提交。
          TD-2 廢棄此收集路徑，保留 MessageBus 作為唯一授權路徑。

        Returns / 返回：
          [] — Always empty; callers should rely on MessageBus for intent delivery.
               始終為空；呼叫者應依賴 MessageBus 進行 intent 傳遞。
        """
        # Emit deprecation warning so callers (e.g. PipelineBridge) can be updated
        # 發出廢棄警告，通知呼叫方（如 PipelineBridge）更新
        warnings.warn(
            "collect_pending_intents() is deprecated; intents are now routed via MessageBus (TD-2)",
            DeprecationWarning,
            stacklevel=2,
        )
        # Return empty list for backward compatibility — do not drain _pending_intents
        # 返回空列表以向後兼容 — 不再清空 _pending_intents（該列表現已始終為空）
        return []

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
            stats = {
                "role": AgentRole.STRATEGIST.value,
                "state": self.state.value,
                "shadow": self.config.shadow,
                "pending_intents": len(self._pending_intents),
                "strategy_preference_weights": dict(self._strategy_preference_weights),
                **dict(self._stats),
            }
        # L2 cache size is read under its own lock to avoid holding both locks
        # L2 快取大小使用專用鎖讀取，避免同時持有兩把鎖
        with self._l2_cache_lock:
            stats["l2_cache_size"] = len(self._l2_result_cache)
        return stats

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
