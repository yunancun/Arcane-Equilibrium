"""
Batch 7 — StrategistAgent: AI-enhanced signal evaluation + TradeIntent production
====================================================================================
Governance refs: EX-06 §4, DOC-04 §G Multi-Agent

MODULE_NOTE (中文):
  StrategistAgent 是 5-Agent 体系中的"策略大脑"。
  職責：
  1. 消費 ScoutAgent 產出的 IntelObject 情報
  2. 調用 Qwen 3.5 (judge_edge) 評估信號是否有交易優勢
  3. Ollama 不可用時回退到本地啟發式規則（fail-closed：不可放行未評估信號）
  4. 產出 TradeIntent 供 Guardian 審查
  5. Shadow 模式：僅記錄到審計日誌，不產出 intent 到下游

  §14.1 重構：H1 ThoughtGate / H3 ModelRouter / H4 Validator 已拆分到同目錄獨立模組，
  本文件僅保留編排邏輯（orchestrator）和策略偏好/regime 權重管理。

  安全不變量：
  - system_mode = read_only 不變
  - fail-closed：異常時默認拒絕
  - 所有決策寫入審計日誌
  - Shadow 模式下不產出任何實際 intent

MODULE_NOTE (English):
  StrategistAgent is the "strategy brain" in the 5-Agent system.
  Responsibilities:
  1. Consume IntelObject intelligence from ScoutAgent
  2. Call Qwen 3.5 (judge_edge) to evaluate signal edge quality
  3. Fall back to local heuristics when Ollama unavailable (fail-closed)
  4. Produce TradeIntent for Guardian review
  5. Shadow mode: log to audit only, do not produce downstream intents

  §14.1 refactor: H1 ThoughtGate / H3 ModelRouter / H4 Validator extracted to
  same-directory modules. This file is now a thin orchestrator plus strategy
  preference / regime weight management.

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
from typing import Any, Callable, Dict, List, Optional

from .base_agent import BaseAgent
from .h1_thought_gate import H1ThoughtGate
from .h4_validator import validate_ai_output
from .llm_call_wrapper import call_ollama_judge_edge, ollama_is_available
from .model_router import ModelRouter
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
from .strategist_fast_channel import build_emergency_intents
from .strategist_models import (  # noqa: F401 — re-export for backward compatibility
    EdgeEvaluation,
    StrategistConfig,
    _heuristic_evaluate,
    _parse_sentiment,
)
from .utils.time_utils import now_ms

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# StrategistAgent / 策略師代理
# ═══════════════════════════════════════════════════════════════════════════════

class StrategistAgent(BaseAgent):
    """EX-06 §4 — AI-enhanced strategy evaluation agent.

    Consumes IntelObject from Scout, evaluates signal quality via Qwen 3.5
    (or heuristic fallback), and produces TradeIntent for Guardian review.

    消費 Scout 的 IntelObject，通過 Qwen 3.5（或啟發式回退）評估信號質量，
    產出 TradeIntent 供 Guardian 審查。

    Key constraints:
    - Cannot bypass Guardian review (EX-06 §4.3)
    - Cannot modify risk parameters (only Guardian can)
    - Cannot directly place orders (must go via Executor)
    - fail-closed: errors → reject signal

    Delegates to:
    - H1ThoughtGate: pre-AI deterministic gate (budget/complexity/cooldown)
    - ModelRouter: H3 model tier routing + L2 background evaluation + L2 cache
    - h4_validator.validate_ai_output: H4 AI output structure validation
    委託模組：
    - H1ThoughtGate：AI 前確定性閘門（預算/複雜度/冷卻期）
    - ModelRouter：H3 模型層路由 + L2 後台評估 + L2 快取
    - h4_validator.validate_ai_output：H4 AI 輸出結構驗證
    """

    # E5-P1-4: class-level role so BaseAgent sees correct value pre-__init__.
    # E5-P1-4：類級 role，讓 BaseAgent 在 __init__ 前看到正確值。
    role = AgentRole.STRATEGIST

    # C4: Regime-aware strategy selection preference multipliers.
    # C4: Regime 感知策略選擇偏好倍率。
    # Backward-compatible class attribute — actual cap lives in H1ThoughtGate
    # 向後兼容的類屬性 — 實際上限在 H1ThoughtGate 中
    _H1_COOLDOWN_MAX_SIZE: int = 1000

    _REGIME_STRATEGY_PREFERENCES: Dict[str, Dict[str, float]] = {
        "trending_up": {"ma_crossover": 1.2, "bb_breakout": 1.1, "grid_trading": 0.8},
        "trending_down": {"ma_crossover": 1.2, "bb_breakout": 1.1, "grid_trading": 0.8},
        "ranging": {"grid_trading": 1.3, "bollinger_reversion": 1.2, "ma_crossover": 0.8},
        "volatile": {"bollinger_reversion": 1.1, "funding_rate_arb": 1.0, "grid_trading": 0.7},
        "unknown": {},  # no preference adjustment for unknown regime / 未知 regime 不調整
    }

    def __init__(
        self,
        *,
        config: Optional[StrategistConfig] = None,
        message_bus: Optional[MessageBus] = None,
        ollama_client: Optional[Any] = None,
        audit_callback: Optional[Callable] = None,
        cost_tracker: Optional[Any] = None,
    ):
        super().__init__(
            role=AgentRole.STRATEGIST,
            message_bus=message_bus,
            audit_callback=audit_callback,
            cost_tracker=cost_tracker,
        )
        self.config = config or StrategistConfig()
        self._ollama = ollama_client

        # cost_tracker already set by BaseAgent.__init__ (self.cost_tracker).
        # cost_tracker 已由 BaseAgent.__init__ 設置（self.cost_tracker）。
        # Kept as a local alias for backwards compatibility with any test that
        # reads .cost_tracker directly (None = no budget tracking / fail-open).
        # 保留為別名以向後兼容直接讀 .cost_tracker 的測試（None = 不追蹤）。

        # Delegate: H1 ThoughtGate — pre-AI deterministic gate
        # 委託：H1 思考閘門 — AI 調用前的確定性判斷
        self._h1_gate = H1ThoughtGate(cost_tracker=cost_tracker)

        # Backward compat: expose _h1_cooldown via delegate
        # 向後兼容：通過委託暴露 _h1_cooldown
        self._h1_cooldown = self._h1_gate.cooldown_dict

        # Delegate: H3 ModelRouter — model tier routing + L2 cache
        # 委託：H3 模型路由 — 模型層選擇 + L2 快取管理
        self._model_router = ModelRouter()

        # Inject budget checker for L1.5/L2 routing / 注入預算檢查器用於 L1.5/L2 路由
        # Budget checker is injected externally via set_budget_manager()
        # 預算檢查器通過 set_budget_manager() 外部注入
        self._budget_manager: Optional[Any] = None  # Set via set_budget_manager()

        # Truth Source Registry: injected externally for pattern-driven weight updates
        # 知識登記表：外部注入，用於模式洞察驅動的策略權重更新（Principle 7 隔離）
        self._truth_registry: Optional[Any] = None

        # Strategy preference weights: 1.0 = neutral, >1.0 = preferred, <1.0 = avoid
        # 策略偏好權重：1.0=中性，>1.0=偏好，<1.0=迴避。範圍限幅 [0.2, 2.0]
        self._strategy_preference_weights: Dict[str, float] = {}

        # C4: Current detected market regime for regime-aware strategy selection.
        # C4: 當前偵測到的市場 regime，用於 regime 感知策略選擇。
        self._current_regime: str = "unknown"

        # Pending intents buffer (collected by PipelineBridge)
        # 待處理 intent 緩衝區（由 PipelineBridge 收集）
        self._pending_intents: List[TradeIntent] = []

        # Stats / 統計
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
            # L1.5 evaluation counter / L1.5 評估計數器
            "l1_5_evaluations": 0,
            # H5 Ollama cost tracking counter / H5 Ollama 調用計數
            "ollama_calls_tracked": 0,
            # L2 cache counters / L2 快取計數器
            "l2_cache_stored": 0,
            "l2_cache_hit": 0,
            "l2_cache_expired": 0,
            "l2_cache_weight_applied": 0,
        }

        # Evaluation log (recent evaluations for diagnostics)
        # 評估日誌（最近的評估結果，用於診斷）
        self._eval_log: List[Dict[str, Any]] = []
        self._max_eval_log = 100

        # V2: Dual-track mechanism / 雙軌機制
        # Fast channel: deterministic risk rules (<10ms) / 快速通道：確定性風控規則
        # Normal channel: AI-evaluated signals (2-8s) / 正常通道：AI 評估信號
        self._emergency_mode = threading.Event()  # Atomic flag for fast channel / 快速通道原子標誌
        self._normal_queue: List[TradeIntent] = []  # Normal channel pending queue / 正常通道待處理隊列

        # V2: CognitiveModulator integration / 認知門檻調製整合
        # Injected externally; None = no cognitive modulation (bypass)
        # 外部注入；None = 不做認知調製（跳過）
        self._cognitive_modulator: Optional[Any] = None

        # 3-3: Last knowledge_update extracted from AI response (thread-safe via _lock)
        # 3-3：從 AI 回答中提取的最新 knowledge_update（通過 _lock 線程安全）
        self._last_knowledge_update: Optional[Any] = None

    # ── Lifecycle / 生命週期 ──
    # pause() inherited from BaseAgent. start/stop override to preserve the
    # original info log string (Strategist's start log includes shadow flag).
    # pause() 繼承自 BaseAgent；start/stop 覆蓋保留原有 info log（含 shadow 標誌）。

    def start(self) -> None:
        """Start the agent / 啟動代理"""
        super().start()
        logger.info("StrategistAgent started (shadow=%s) / 策略師代理已啟動 (shadow=%s)",
                     self.config.shadow, self.config.shadow)

    def stop(self) -> None:
        """Stop the agent / 停止代理"""
        super().stop()
        logger.info("StrategistAgent stopped / 策略師代理已停止")

    # ── Message Handler / 消息處理 ──

    def on_message(self, message: AgentMessage) -> None:
        """
        Handle incoming messages from MessageBus.
        處理來自消息總線的入站消息。
        """
        if self.state != AgentState.RUNNING:
            logger.debug("StrategistAgent not running, ignoring message / 策略師未運行，忽略消息")
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
        處理來自 Scout 的 IntelObject → 評估 edge → 可選產出 TradeIntent。

        Orchestration only — delegates H1/H3/H4 to extracted modules.
        僅做編排 — H1/H3/H4 委託給拆分模組。
        """
        # V2: Emergency mode check — discard normal channel intents during emergency
        # 緊急模式檢查 — 緊急時期丟棄正常通道 intent
        if self._emergency_mode.is_set():
            logger.debug(
                "Normal channel intel discarded (emergency mode active) / "
                "正常通道情報已丟棄（緊急模式）"
            )
            return

        with self._lock:
            self._stats["intel_received"] += 1

        payload = message.payload
        if not payload:
            logger.warning("Empty intel payload / 空情報負載")
            return

        # Reconstruct IntelObject from payload / 從負載重建 IntelObject
        try:
            intel = IntelObject(
                intel_id=payload.get("intel_id", f"intel_{uuid.uuid4().hex[:12]}"),
                source=payload.get("source", "unknown"),
                timestamp_ms=payload.get("timestamp_ms", now_ms()),
                freshness_seconds=payload.get("freshness_seconds", 0),
                data_quality=DataQualityLevel(payload.get("data_quality", "fact")),
                sentiment=_parse_sentiment(payload.get("sentiment", "neutral")),
                relevance_score=float(payload.get("relevance_score", 0.0)),
                content=payload.get("content", ""),
                symbols=payload.get("symbols", []),
                metadata=payload.get("metadata", {}),
            )
        except Exception as e:
            logger.error("Failed to parse IntelObject: %s / 解析 IntelObject 失敗: %s", e, e)
            with self._lock:
                self._stats["errors"] += 1
            return

        # C4: Apply regime-aware strategy weights if regime info is available in metadata.
        # C4: 若 metadata 中含有 regime 信息，應用 regime 感知策略權重。
        regime = intel.metadata.get("regime") if isinstance(intel.metadata, dict) else None
        if regime and isinstance(regime, str) and regime != self._current_regime:
            self._apply_regime_weights(regime)

        # Check minimum relevance / 檢查最低相關性
        if intel.relevance_score < self.config.min_relevance:
            logger.debug("Intel below relevance threshold: %.2f < %.2f",
                         intel.relevance_score, self.config.min_relevance)
            return

        # Check age / 檢查年齡
        age_seconds = max(0, (now_ms() - intel.timestamp_ms) / 1000)
        if age_seconds > self.config.max_intel_age_seconds:
            logger.debug("Intel too old: %.0fs > %ds", age_seconds, self.config.max_intel_age_seconds)
            return

        # ── L2 cache check: use previous L2 background result if available ──
        # L2 快取檢查：若之前的 L2 後台評估已完成且未過期，直接使用其結果
        l2_cached = None
        for sym in intel.symbols:
            l2_cached = self._model_router.check_l2_cache(sym, self._stats)
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
            # H1 思考閘門：AI 調用前的確定性判斷（委託給 H1ThoughtGate 模組）
            should_call_ai = self._h1_gate.check(intel, self._stats)

            if not should_call_ai:
                # Principle 6: fail-closed means use conservative heuristic, NOT allow-all
                # 原則 6：失敗默認收縮 — 降級用啟發式評估，不可直接放行
                evaluation = _heuristic_evaluate(intel, self.config)
                with self._lock:
                    self._stats["heuristic_evaluations"] += 1
            else:
                # H3 ModelRouter: select model tier based on signal complexity
                # H3 模型路由：根據信號複雜度選擇模型層（委託給 ModelRouter 模組）
                complexity = self._h1_gate.complexity_score(intel)
                # Build routing context for L1.5/L2 upgrade decisions
                # 構建路由上下文用於 L1.5/L2 升級決策
                route_context = self._build_route_context(intel)
                model_tier = self._model_router.route(complexity, context=route_context)
                if model_tier == "l2":
                    # L2 must run in background thread — cannot block synchronous on_tick callback
                    # L2 必須在後台線程執行，避免阻塞 MessageBus 的同步 on_tick 回調
                    self._model_router.run_l2_background(
                        intel,
                        evaluate_fn=self._evaluate_edge,
                        weight_update_fn=self._apply_l2_weight_update,
                    )
                    # Use heuristic as immediate result; L2 result cached for next cycle
                    # 立即使用啟發式結果；L2 結果快取供下次週期使用
                    evaluation = _heuristic_evaluate(intel, self.config)
                    with self._lock:
                        self._stats["heuristic_evaluations"] += 1
                elif model_tier == "l1_5":
                    # L1.5: Claude Sonnet — synchronous with timeout
                    # L1.5：Claude Sonnet — 同步調用帶超時
                    try:
                        evaluation = self._evaluate_edge_l1_5(intel)
                        with self._lock:
                            self._stats["l1_5_evaluations"] = (
                                self._stats.get("l1_5_evaluations", 0) + 1
                            )
                    except Exception as _l15_exc:
                        logger.warning(
                            "L1.5 evaluation failed, falling back to L1: %s / "
                            "L1.5 評估失敗，回退到 L1: %s",
                            type(_l15_exc).__name__, type(_l15_exc).__name__,
                        )
                        evaluation = self._evaluate_edge(intel)
                else:
                    # L1 (l1_9b / l1_27b) runs synchronously with timeout
                    # L1 同步執行，有 timeout 保護，阻塞時間可接受
                    try:
                        evaluation = self._evaluate_edge(intel)
                    except Exception as _edge_exc:
                        # fail-closed: any unexpected error → heuristic fallback
                        # fail-closed：任何異常 → 啟發式回退
                        logger.warning(
                            "_evaluate_edge raised %s, falling back to heuristic / "
                            "_evaluate_edge 拋出 %s，回退到啟發式",
                            type(_edge_exc).__name__, type(_edge_exc).__name__,
                        )
                        with self._lock:
                            self._stats["errors"] += 1
                            self._stats["heuristic_evaluations"] += 1
                        evaluation = _heuristic_evaluate(intel, self.config)

                # H5 light: record Ollama call for cost tracking
                # H5 輕量版：記錄 Ollama 調用以追蹤調用次數
                if self.cost_tracker is not None and model_tier != "l2":
                    try:
                        _record = getattr(self.cost_tracker, "record_call", None)
                        if _record is not None:
                            _record(provider="ollama", model="l1_9b", cost_usd=0.0)
                    except Exception as e:
                        logger.warning(
                            "H5 cost record failed for model l1_9b: %s / H5 成本記錄失敗", e
                        )

        with self._lock:
            self._stats["intel_evaluated"] += 1

        # Log evaluation / 記錄評估
        eval_record = {
            "intel_id": intel.intel_id,
            "symbols": intel.symbols,
            "relevance": intel.relevance_score,
            "sentiment": intel.sentiment.value if hasattr(intel.sentiment, 'value') else str(intel.sentiment),
            "evaluation": evaluation.to_dict(),
            "timestamp_ms": now_ms(),
        }
        with self._lock:
            self._eval_log.append(eval_record)
            if len(self._eval_log) > self._max_eval_log:
                self._eval_log = self._eval_log[-self._max_eval_log:]

        # Audit / 審計
        self._audit("edge_evaluation", eval_record)

        if not evaluation.has_edge:
            with self._lock:
                self._stats["evaluations_rejected"] += 1
            logger.info("No edge detected for %s (reason: %s) / 未檢測到交易優勢",
                        intel.symbols, evaluation.reason)
            return

        # V2: Apply CognitiveModulator threshold if available / 應用認知調製門檻
        conf_floor, _qty_ceil = self._apply_cognitive_modulation(evaluation.confidence)
        if evaluation.confidence < conf_floor:
            with self._lock:
                self._stats["evaluations_rejected"] += 1
            logger.info(
                "Edge confidence too low: %.2f < %.2f (cognitive floor) / "
                "Edge 置信度過低（認知門檻）",
                evaluation.confidence, conf_floor,
            )
            return

        # Produce TradeIntent(s) for each symbol / 為每個交易對產出 TradeIntent
        self._produce_intents(intel, evaluation)

    def _produce_intents(self, intel: IntelObject, evaluation: EdgeEvaluation) -> None:
        """
        Build and dispatch TradeIntent for each symbol in the intel.
        為情報中的每個幣種構建並分發 TradeIntent。

        Applies strategy preference weights and dispatches via MessageBus or shadow log.
        應用策略偏好權重，通過 MessageBus 或影子日誌分發。
        """
        from .multi_agent_framework import SentimentScore
        direction = "long" if intel.sentiment == SentimentScore.POSITIVE else "short"

        for symbol in intel.symbols:
            # Apply strategy preference weight (Principle 12: continuous evolution)
            # 應用策略偏好權重（原則 12：持續進化）
            strategy_key = f"{evaluation.source}_{symbol}" if evaluation.source else symbol
            weight = self._strategy_preference_weights.get(strategy_key, None)
            if weight is None:
                source_key = "strategist_ai" if evaluation.source == "ai" else "strategist_heuristic"
                weight = self._strategy_preference_weights.get(source_key, 1.0)
            adjusted_confidence = min(1.0, evaluation.confidence * weight)
            if adjusted_confidence != evaluation.confidence:
                logger.debug(
                    "Strategy weight applied for %s: %.2f × %.2f = %.2f / "
                    "策略偏好權重已應用：原始置信度 %.2f × 權重 %.2f = 調整後 %.2f",
                    symbol, evaluation.confidence, weight, adjusted_confidence,
                    evaluation.confidence, weight, adjusted_confidence,
                )

            intent = TradeIntent(
                symbol=symbol,
                strategy="strategist_ai" if evaluation.source == "ai" else "strategist_heuristic",
                direction=direction,
                size=self.config.default_size,
                confidence=adjusted_confidence,
                thesis=f"Scout intel: {intel.content[:100]}",
                invalidation_condition=f"Edge confidence drops below {self.config.min_confidence}",
                data_quality=intel.data_quality,
                metadata={
                    "intel_id": intel.intel_id,
                    "evaluation_source": evaluation.source,
                    "evaluation_reason": evaluation.reason,
                    "raw_confidence": evaluation.confidence,
                    "strategy_weight": weight,
                    "shadow": self.config.shadow,
                },
            )

            if self.config.shadow:
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
                with self._lock:
                    self._stats["intents_produced"] += 1
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

    # ── Risk / Pattern / Directive Handlers ──

    def _handle_risk_verdict(self, message: AgentMessage) -> None:
        """Handle Guardian's risk verdict feedback / 處理 Guardian 風險裁決反饋"""
        self._audit("risk_verdict_received", message.payload)
        logger.info("Received risk verdict: %s", message.payload.get("result", "unknown"))

    def _handle_pattern_insight(self, message: AgentMessage) -> None:
        """Handle Analyst's pattern insight feedback / 處理 Analyst 模式洞察反饋"""
        self._audit("pattern_insight_received", message.payload)
        logger.info("Received pattern insight from Analyst")
        self._apply_pattern_insight(message.payload)

    def _handle_directive(self, message: AgentMessage) -> None:
        """Handle Conductor system directive / 處理 Conductor 系統指令"""
        directive_type = message.payload.get("directive_type", "")
        if directive_type == "shadow_on":
            self.config.shadow = True
            logger.info("StrategistAgent shadow mode ON / 策略師影子模式開啟")
        elif directive_type == "shadow_off":
            self.config.shadow = False
            logger.info("StrategistAgent shadow mode OFF / 策略師影子模式關閉")
        self._audit("directive_received", message.payload)

    # ── Truth Registry + Strategy Preference Weights ──

    def set_budget_manager(self, budget_manager: Any) -> None:
        """
        Inject APIBudgetManager for L1.5/L2 budget checking.
        注入 APIBudgetManager 用於 L1.5/L2 預算檢查。

        Wires up a lambda budget_checker into ModelRouter so that route()
        can gate L1.5/L2 upgrades based on remaining API budget.
        將 lambda 預算檢查器接入 ModelRouter，使 route() 可根據剩餘
        API 預算閘控 L1.5/L2 升級。
        """
        self._budget_manager = budget_manager
        self._model_router.set_budget_checker(
            lambda tier: budget_manager.can_call(tier)
        )
        logger.info("APIBudgetManager injected into StrategistAgent / API 預算管理器已注入")

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

        Queries active claims from registry, adjusts weights by ±0.1 × confidence,
        clamped to [0.2, 2.0]. Fail-open: any error → log warning, leave weights unchanged.
        從登記表查詢有效聲明，按 ±0.1×信度調整權重，限幅 [0.2, 2.0]。
        失敗開放：任何異常 → 記錄警告，不改變現有權重。
        """
        if self._truth_registry is None:
            return
        try:
            claims = self._truth_registry.get_active_claims(
                regime=None, min_confidence=0.5
            )
            for claim in claims:
                strategy = claim.applies_to_strategy
                if strategy == "all":
                    continue
                current = self._strategy_preference_weights.get(strategy, 1.0)
                delta = 0.1 * claim.confidence
                if "losing" in claim.pattern_text.lower():
                    delta = -delta
                new_weight = max(0.2, min(2.0, current + delta))
                self._strategy_preference_weights[strategy] = new_weight
        except Exception as e:
            logger.warning("_apply_pattern_insight failed (fail-open): %s", e)

    def get_strategy_weight(self, strategy_name: str) -> float:
        """
        0A-1: Return the current preference weight for a strategy.
        返回某策略的當前偏好權重。

        Used by PipelineBridge to apply learning feedback to strategy signals.
        Normalizes strategy name for lookup (strips symbol suffix, lowercases).
        供 PipelineBridge 在策略信號上應用學習反饋。
        對策略名稱標準化（去除 symbol 後綴，小寫化）。

        Args:
            strategy_name: Strategy identifier (e.g. "MACrossover_BTCUSDT" or "ma_crossover").

        Returns:
            Weight in [0.2, 2.0]. Default 1.0 (neutral) if no pattern data.
        """
        # Normalize: strip symbol suffix (e.g. "MACrossover_BTCUSDT" → "macrossover")
        # 標準化：去除 symbol 後綴
        base_name = strategy_name.split("_")[0].lower() if strategy_name else ""
        # Also try common name mappings / 嘗試常見名稱映射
        name_variants = [
            strategy_name,
            base_name,
            strategy_name.lower(),
        ]
        with self._lock:
            for variant in name_variants:
                w = self._strategy_preference_weights.get(variant)
                if w is not None:
                    return w
        return 1.0

    def _apply_regime_weights(self, regime: str) -> None:
        """
        C4: Apply regime-aware strategy preference multipliers.
        C4: 應用 regime 感知策略偏好倍率。

        Resets all weights to 1.0 then applies new regime multipliers to prevent
        oscillation drift from repeated multiply→clamp cycles.
        重置所有權重為 1.0 再應用新 regime 倍率，防止反覆 multiply→clamp 漂移。
        """
        self._current_regime = regime
        prefs = self._REGIME_STRATEGY_PREFERENCES.get(regime, {})
        if not prefs:
            return

        try:
            with self._lock:
                for key in self._strategy_preference_weights:
                    self._strategy_preference_weights[key] = 1.0
                for strategy_name, multiplier in prefs.items():
                    new_weight = max(0.2, min(2.0, multiplier))
                    self._strategy_preference_weights[strategy_name] = new_weight
            logger.debug(
                "C4: Regime weights applied for regime=%s: %s / "
                "Regime 權重已應用：regime=%s",
                regime, prefs, regime,
            )
        except Exception as e:
            logger.warning("_apply_regime_weights failed (fail-open): %s", e)

    def _apply_l2_weight_update(self, intel: Any, evaluation: EdgeEvaluation) -> None:
        """
        Update strategy preference weights based on high-confidence L2 evaluation.
        根據高信心 L2 評估更新策略偏好權重。

        Called by ModelRouter as weight_update_fn callback when L2 result has
        has_edge=True and confidence >= 0.6. Weight adjustment ±0.15, clamped [0.2, 2.0].
        由 ModelRouter 作為 weight_update_fn 回調調用。權重調整 ±0.15，限幅 [0.2, 2.0]。
        """
        try:
            for symbol in getattr(intel, "symbols", []):
                strategy_key = f"ai_{symbol}"
                with self._lock:
                    current = self._strategy_preference_weights.get(strategy_key, 1.0)
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
            logger.warning("_apply_l2_weight_update failed (fail-open): %s", e)

    # ── Route Context + L1.5 Evaluation / 路由上下文 + L1.5 評估 ──

    def _build_route_context(self, intel: Any) -> dict:
        """
        Build context dict for ModelRouter L1.5/L2 upgrade decisions.
        構建上下文字典用於 ModelRouter L1.5/L2 升級判斷。

        Extracts relevant fields from intel metadata so ModelRouter
        can decide whether to upgrade from L1 to L1.5 or L2.
        從 intel metadata 提取相關欄位，供 ModelRouter 判斷是否
        從 L1 升級到 L1.5 或 L2。

        Returns:
            dict with keys matching ModelRouter.route() context spec
        """
        metadata = intel.metadata if isinstance(intel.metadata, dict) else {}
        return {
            "confidence": getattr(intel, "relevance_score", 0.5),
            "amount_pct": metadata.get("position_pct", 0.0),
            "cusum_triggered": metadata.get("cusum_triggered", False),
            "daily_vol_pct": metadata.get("daily_vol_pct", 0.0),
            "is_new_symbol": metadata.get("is_new_symbol", False),
            "weekly_pnl_pct": metadata.get("weekly_pnl_pct", 0.0),
            "param_sharpe_change_pct": metadata.get("param_sharpe_change_pct", 0.0),
        }

    def _evaluate_edge_l1_5(self, intel: Any) -> EdgeEvaluation:
        """L1.5 eval with Claude→TSR closed loop (3-3). / L1.5 Claude→TSR 閉環（3-3）。"""
        try:
            with self._lock:
                self._last_knowledge_update = None
            evaluation = self._evaluate_edge(intel)
            with self._lock:
                ku = self._last_knowledge_update
                self._last_knowledge_update = None
            if ku and self._truth_registry:
                self._process_knowledge_update(ku, source="cloud_api")
            if self._budget_manager:
                try:
                    self._budget_manager.record_call("l1_5", 0.02)
                except Exception:
                    pass
            return evaluation
        except Exception as e:
            logger.warning("L1.5 eval failed, fallback to L1: %s", e)
            return self._evaluate_edge(intel)

    def _process_knowledge_update(self, knowledge_update: Any, source: str = "cloud_api") -> None:
        """Write knowledge_update to TSR (3-3). Principle 10: AI=INFERENCE, caps: cloud 0.90, ai 0.85.
        將 knowledge_update 寫入 TSR（3-3）。原則 10：AI=推斷。上限：cloud 0.90, ai 0.85。"""
        if not self._truth_registry:
            return
        items = knowledge_update if isinstance(knowledge_update, list) else [knowledge_update]
        cap = 0.90 if source == "cloud_api" else 0.85
        written = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            pattern = item.get("pattern", item.get("claim", ""))[:200]  # Security: cap length / 安全：截斷長度
            if not pattern:
                continue
            try:
                conf = min(float(item.get("confidence", 0.5)), cap)
                obs_count = max(1, min(10000, int(item.get("observation_count", 1))))  # Clamp 1-10000
                self._truth_registry.register_claim(
                    pattern_text=pattern, evidence_source="ai",
                    observation_count=obs_count,
                    confidence=conf, applies_to_regime=item.get("regime", "all"),
                    applies_to_strategy=item.get("strategy", "all"),
                )
                written += 1
                logger.info("TSR write: '%s' (conf=%.2f, src=%s)", pattern[:50], conf, source)
            except Exception as exc:
                logger.warning("TSR write failed: %s", exc)
        if written:
            self._audit("knowledge_update", {"count": written, "source": source})

    # ── Prompt Construction / Prompt 構建 ──

    def _build_prompt_context(self, intel: IntelObject) -> str:
        """
        V2: Build structured JSON prompt context for Ollama evaluation.
        V2：構建結構化 JSON prompt 上下文供 Ollama 評估。

        Includes cognitive modulator state and dream engine insights
        when available, per Cognitive Adaptation Spec §6.2.
        包含認知調製器狀態和蒙特卡洛洞察（若可用），
        依據認知自適應 SPEC §6.2。

        Returns:
            JSON-formatted context string prefixed with evaluation instruction
            帶評估指令前綴的 JSON 格式上下文字串
        """
        # Base intel context / 基礎情報上下文
        context_dict: dict = {
            "symbols": intel.symbols,
            "source": intel.source,
            "sentiment": intel.sentiment.value if hasattr(intel.sentiment, "value") else str(intel.sentiment),
            "relevance": round(intel.relevance_score, 2),
            "data_quality": intel.data_quality.value if hasattr(intel.data_quality, "value") else str(intel.data_quality),
            "freshness_s": intel.freshness_seconds,
            "content": intel.content[:500],
            "regime": self._current_regime,
        }

        # V2: CognitiveModulator state (if connected)
        # 認知調製器狀態（若已連接）
        if self._cognitive_modulator is not None:
            try:
                cog_params = self._cognitive_modulator.get_current_params()
                context_dict["cognitive"] = {
                    "confidence_floor": round(cog_params.get("confidence_floor", 0.6), 3),
                    "qty_ceiling": round(cog_params.get("qty_ceiling", 1.0), 3),
                    "stoploss_multiplier": round(cog_params.get("stoploss_multiplier", 1.0), 3),
                }
            except Exception:
                pass  # No cognitive data available — skip silently / 無認知數據，靜默跳過

        # V2: DreamEngine insights (if available via cognitive modulator)
        # 蒙特卡洛洞察（若可用）
        if self._cognitive_modulator is not None:
            try:
                dream_data = getattr(self._cognitive_modulator, "last_dream_summary", None)
                if dream_data and isinstance(dream_data, dict):
                    context_dict["dream_insights"] = {
                        "suggested_params": dream_data.get("suggested_params"),
                        "confidence": dream_data.get("confidence"),
                    }
            except Exception:
                pass  # No dream data — skip silently / 無蒙特卡洛數據，靜默跳過

        # 3-3: Include high-confidence TSR claims in prompt (closed loop)
        # 3-3：在 prompt 中包含高信度 TSR 聲明（閉環）
        if self._truth_registry:
            try:
                active = self._truth_registry.get_active_claims(min_confidence=0.5)
                if active:
                    context_dict["tsr_claims"] = [
                        {"pattern": c.pattern_text, "confidence": c.confidence,
                         "level": c.cognitive_level.value if hasattr(c.cognitive_level, "value") else str(c.cognitive_level)}
                        for c in active[:5]
                    ]
            except Exception:
                pass  # TSR query failure is non-critical / TSR 查詢失敗非關鍵

        # Format as structured text for LLM / 格式化為 LLM 的結構化文本
        try:
            context_json = json.dumps(context_dict, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError):
            # Fallback to plain text if JSON serialization fails
            # JSON 序列化失敗時回退到純文字
            return (
                f"Symbol(s): {', '.join(intel.symbols)}\n"
                f"Source: {intel.source}\n"
                f"Sentiment: {context_dict['sentiment']}\n"
                f"Relevance: {context_dict['relevance']}\n"
                f"Content: {intel.content[:500]}"
            )

        # Prefix with evaluation instruction for judge_edge()
        # 為 judge_edge() 加上評估指令前綴
        return (
            "Evaluate this trading signal. Respond in JSON: "
            '{"has_edge":bool,"confidence":0-1,"reason":"..."}. '
            "Consider cognitive state if present.\n\n"
            + context_json
        )

    # ── Edge Evaluation / Edge 評估 ──

    def _evaluate_edge(self, intel: IntelObject) -> EdgeEvaluation:
        """
        Evaluate whether intel contains a tradeable edge.
        評估情報是否包含可交易優勢。

        Strategy: 1. Try Ollama/Qwen 3.5 judge_edge() first
        2. If unavailable/error → fallback to local heuristic
        3. Never return has_edge=True without evaluation (fail-closed)
        """
        # E5-P1-4: Ollama availability check routed via llm_call_wrapper.
        # E5-P1-4：Ollama 可用性檢查統一走 llm_call_wrapper。
        if ollama_is_available(self._ollama):
            try:
                return self._ai_evaluate(intel)
            except Exception as e:
                logger.warning("AI evaluation failed, falling back to heuristic: %s / AI 評估失敗: %s", e, e)
                with self._lock:
                    self._stats["errors"] += 1

        with self._lock:
            self._stats["heuristic_evaluations"] += 1
        return _heuristic_evaluate(intel, self.config)

    def _ai_evaluate(self, intel: IntelObject) -> EdgeEvaluation:
        """
        Evaluate edge using Qwen 3.5 via judge_edge().
        使用 Qwen 3.5 的 judge_edge() 評估 edge。
        """
        start = time.time()

        # V2: Use structured JSON prompt with cognitive/dream fields
        # V2：使用含認知/蒙特卡洛欄位的結構化 JSON prompt
        context = self._build_prompt_context(intel)

        # E5-P1-4: routed via llm_call_wrapper.call_ollama_judge_edge
        # (thin pass-through — identical call semantics, preserves fail-closed).
        # E5-P1-4：通過 llm_call_wrapper.call_ollama_judge_edge（語義完全等同）。
        response = call_ollama_judge_edge(self._ollama, context)
        latency_ms = (time.time() - start) * 1000

        with self._lock:
            self._stats["ai_evaluations"] += 1

        if not response.success:
            logger.warning("judge_edge returned unsuccessful: %s / judge_edge 返回失敗", response.error)
            with self._lock:
                self._stats["heuristic_evaluations"] += 1
            return _heuristic_evaluate(intel, self.config)

        # Parse JSON response / 解析 JSON 響應
        try:
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            result = json.loads(text)

            # H4: Validate AI output structure — delegate to h4_validator module
            # H4 輸出驗證 — 委託給 h4_validator 模組
            if not validate_ai_output(result):
                logger.warning(
                    "H4 validation failed for AI output, "
                    "falling back to heuristic / H4 驗證失敗，降級到啟發式"
                )
                with self._lock:
                    self._stats["h4_validation_fail"] = self._stats.get("h4_validation_fail", 0) + 1
                    self._stats["heuristic_evaluations"] += 1
                return _heuristic_evaluate(intel, self.config)

            has_edge = bool(result.get("has_edge", False))
            confidence = float(result.get("confidence", 0.0))
            reason = str(result.get("reason", "AI evaluation"))

            # 3-3: Stash knowledge_update for L1.5 TSR write-back
            # 3-3：暫存 knowledge_update 供 L1.5 寫回 TSR
            ku = result.get("knowledge_update")
            if ku:
                with self._lock:
                    self._last_knowledge_update = ku

            # H5: Record Ollama call for cost/resource awareness (principle 13)
            # H5 成本感知：記錄 Ollama 調用（根原則 13）
            if self.cost_tracker is not None:
                try:
                    record_fn = getattr(self.cost_tracker, "record_call", None)
                    if record_fn is not None:
                        record_fn(provider="ollama", model="l1_9b", duration_ms=latency_ms, cost_usd=0.0)
                    with self._lock:
                        self._stats["ollama_calls_tracked"] += 1
                except Exception:
                    logger.warning("cost_tracker.record_call failed, non-fatal / 成本記錄失敗，非致命")

            return EdgeEvaluation(
                has_edge=has_edge,
                confidence=confidence,
                reason=reason,
                source="ai",
                latency_ms=latency_ms,
            )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("Failed to parse judge_edge response: %s / 解析 judge_edge 響應失敗: %s", e, e)
            return EdgeEvaluation(
                has_edge=False,
                confidence=0.0,
                reason=f"AI response parse error: {e}",
                source="ai_parse_error",
                latency_ms=latency_ms,
            )

    # ── Intent Collection (DEPRECATED) / Intent 收集（已廢棄）──

    def collect_pending_intents(self) -> List[TradeIntent]:
        """
        [DEPRECATED] Collect and clear pending intents (called by PipelineBridge).
        [已廢棄] 收集並清除待處理的 intents。

        Always returns empty list — intents are now routed exclusively via MessageBus.
        始終返回空列表 — intent 現在完全通過 MessageBus 路由。
        """
        warnings.warn(
            "collect_pending_intents() is deprecated; intents are now routed via MessageBus (TD-2)",
            DeprecationWarning,
            stacklevel=2,
        )
        return []

    # ── Backward-compatible H1/H4 method stubs ──
    # These thin wrappers preserve the old method signatures for any external callers.
    # 這些薄包裝保留舊方法簽名，供任何外部調用者使用。

    def _h1_check_budget(self) -> bool:
        """Backward-compatible delegator to H1ThoughtGate / 向後兼容委託"""
        return self._h1_gate._check_budget()

    def _h1_complexity_score(self, intel: Any) -> float:
        """Backward-compatible delegator to H1ThoughtGate / 向後兼容委託"""
        return self._h1_gate.complexity_score(intel)

    def _h1_check_cooldown(self, intel: Any) -> bool:
        """Backward-compatible delegator to H1ThoughtGate / 向後兼容委託"""
        return self._h1_gate._check_cooldown(intel)

    def _validate_ai_output(self, parsed: dict) -> bool:
        """Backward-compatible delegator to h4_validator / 向後兼容委託"""
        return validate_ai_output(parsed)

    def _h3_route_model(self, intel: Any) -> str:
        """Backward-compatible delegator to ModelRouter / 向後兼容委託"""
        complexity = self._h1_gate.complexity_score(intel)
        route_context = self._build_route_context(intel)
        return self._model_router.route(complexity, context=route_context)

    # ── V2: Dual-track Fast Channel / 雙軌快速通道 ──

    def handle_fast_channel(self, trigger: str, symbols: list[str] | None = None) -> List[TradeIntent]:
        """
        V2 Fast channel: deterministic risk-driven actions (<10ms).
        V2 快速通道：確定性風控驅動的行動（<10ms）。

        Triggers: risk_governor >= DEFENSIVE -> reduce_all / close_all / flash_crash
        觸發條件：risk_governor >= DEFENSIVE -> 減倉/全平/閃崩保護

        Sets _emergency_mode flag to block normal channel, then generates
        pre-defined intents. Normal channel checks this flag before emitting.
        設置 _emergency_mode 標誌阻斷正常通道，然後生成預定義 intent。
        正常通道在發射前檢查此標誌。

        Args:
            trigger: Action type — "reduce_all" / "close_all" / "flash_crash"
            symbols: Specific symbols to act on (None = all)

        Returns:
            List of emergency TradeIntents
        """
        # Set emergency mode — blocks normal channel
        # 設置緊急模式 — 阻斷正常通道
        self._emergency_mode.set()

        with self._lock:
            # Clear normal channel queue (stale intents are dangerous during emergency)
            # 清空正常通道隊列（緊急時期過期 intent 是危險的）
            self._normal_queue.clear()

            # Delegate intent construction to extracted module
            # 委託提取的模組構建 intent
            target_symbols = symbols or []
            emergency_intents = build_emergency_intents(
                trigger=trigger,
                symbols=target_symbols,
                TradeIntent=TradeIntent,
            )

            self._pending_intents.extend(emergency_intents)
            self._stats["intents_produced"] += len(emergency_intents)

            logger.warning(
                "Fast channel triggered: %s, %d intents generated / "
                "快速通道觸發：%s，生成 %d 個 intent",
                trigger, len(emergency_intents), trigger, len(emergency_intents),
            )

            return emergency_intents

    def clear_emergency_mode(self) -> None:
        """
        V2: Clear emergency mode after fast channel actions are processed.
        V2：快速通道行動處理完畢後清除緊急模式。

        Normal channel resumes accepting signals after this call.
        此調用後正常通道恢復接收信號。
        """
        self._emergency_mode.clear()
        logger.info("Emergency mode cleared, normal channel resumed / 緊急模式清除，正常通道恢復")

    # ── V2: CognitiveModulator Integration / 認知調製器整合 ──

    def set_cognitive_modulator(self, modulator: Any) -> None:
        """
        V2: Inject CognitiveModulator for decision threshold adjustment.
        V2：注入 CognitiveModulator 用於決策門檻調整。

        Principle: cognitive modulation != capability restriction (see root principle derivative).
        原則：認知調製 != 能力限制（見根原則衍生準則）。
        """
        self._cognitive_modulator = modulator
        logger.info(
            "CognitiveModulator injected into StrategistAgent / "
            "認知調製器已注入 StrategistAgent"
        )

    def _apply_cognitive_modulation(self, confidence: float) -> tuple[float, float]:
        """
        V2: Apply CognitiveModulator thresholds to confidence and qty.
        V2：應用認知門檻調製到信心和倉位。

        Returns (adjusted_min_confidence, qty_ceiling_multiplier).
        返回 (調整後最低信心門檻, 倉位上限乘數)。

        If no modulator is injected, returns default config values (bypass).
        若未注入調製器，返回默認配置值（跳過）。
        """
        if self._cognitive_modulator is None:
            return (self.config.min_confidence, 1.0)

        try:
            params = self._cognitive_modulator.get_current_params()
            conf_floor = params.get("confidence_floor", self.config.min_confidence)
            qty_ceil = params.get("qty_ceiling", 1.0)
            return (conf_floor, qty_ceil)
        except Exception as e:
            logger.warning(
                "CognitiveModulator error, using defaults: %s / "
                "認知調製器錯誤，使用默認值: %s", e, e,
            )
            return (self.config.min_confidence, 1.0)

    # ── Audit / 審計 ──
    # _audit() inherited from BaseAgent (prefixes event with role.value = "strategist").
    # _audit() 繼承自 BaseAgent（前綴為 role.value = "strategist"）。

    # ── Status / 狀態 ──

    def get_stats(self) -> Dict[str, Any]:
        """Get agent statistics / 獲取代理統計"""
        with self._lock:
            stats = {
                "role": AgentRole.STRATEGIST.value,
                "state": self.state.value,
                "shadow": self.config.shadow,
                "pending_intents": len(self._pending_intents),
                "strategy_preference_weights": dict(self._strategy_preference_weights),
                # V2: dual-track + cognitive modulator status / 雙軌 + 認知調製狀態
                "emergency_mode_active": self._emergency_mode.is_set(),
                "normal_queue_size": len(self._normal_queue),
                "cognitive_modulator_connected": self._cognitive_modulator is not None,
                **dict(self._stats),
            }
        # L2 cache size from ModelRouter's own lock
        # L2 快取大小從 ModelRouter 的專用鎖讀取
        stats["l2_cache_size"] = self._model_router.cache_size
        return stats

    def get_recent_evaluations(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent edge evaluations for diagnostics / 獲取最近的 edge 評估用於診斷"""
        with self._lock:
            return list(self._eval_log[-limit:])
