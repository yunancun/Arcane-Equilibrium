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

  G3-08 Phase 4 重構（2026-04-26）：
    本檔再拆 16 method 至 3 sibling 以維持 §九 800 行警告線：
      - strategist_edge_eval.py：6 fn（_evaluate_edge / _ai_evaluate /
        _evaluate_edge_l1_5 / _build_prompt_context / _process_knowledge_update /
        _build_route_context）
      - strategist_weights.py：6 fn（set_budget_manager / set_truth_registry /
        _apply_pattern_insight / get_strategy_weight / _apply_regime_weights /
        _apply_l2_weight_update）
      - strategist_cognitive.py：4 fn（handle_fast_channel / clear_emergency_mode /
        set_cognitive_modulator / _apply_cognitive_modulation）
    全部 16 method 在本檔保留為 1-line delegator，向後兼容所有 callsite + test
    patch path。主檔保留 ctor / class attrs / 生命週期 / 消息處理 / _handle_intel
    編排 / _produce_intents / status accessors / 既有 BWD compat（H1/H4/H3 stubs）。

  G3-08 Phase 4 P3（2026-04-28）：
    主檔 933 → ≤800 LOC slim — 在不破 BWD compat 前提下：
      (a) 16 個既有 delegator 壓縮為單行 def（去 docstring，header 區段已說明）;
      (b) 多搬 2 個方法 body 至 sibling 並各保 1-line delegator：
          - ``_produce_intents`` body → strategist_edge_eval.py（intent 構建+派發）;
          - ``record_trade_outcome`` body → strategist_cognitive.py（LOSSES-WIRING
            counter，與 tick_cognitive_modulator 共處同檔，語意凝聚度高）;
      (c) ``_handle_intel`` 5 個 early-return 點補 ``_invalidate_h_state_async``
          hint（E2 4-1 NIT-1 LOW），讓 h_state cache 對 intel 拒絕事件保鮮。
    BWD compat：``agent._produce_intents`` / ``agent.record_trade_outcome`` 仍為
    bound method（test ``MagicMock(wraps=agent.method)`` 無感）；``patch(
    "app.strategist_agent.X")`` patch path 因 re-export 完整保留。

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

  G3-08 Phase 4 refactor (2026-04-26):
    Further split 16 methods into 3 siblings to keep §九 800-line warning line:
      - strategist_edge_eval.py: 6 fn (edge evaluation + prompt construction)
      - strategist_weights.py: 6 fn (weight management + dependency injection)
      - strategist_cognitive.py: 4 fn (V2 fast channel + cognitive modulator)
    All 16 methods preserved here as 1-line delegators for backward compatibility
    with every callsite + test patch path. Main file keeps ctor / class attrs /
    lifecycle / message handlers / _handle_intel orchestration / _produce_intents /
    status accessors / existing BWD compat (H1/H4/H3 stubs).

  Safety invariants:
  - system_mode = read_only (unchanged)
  - fail-closed: reject by default on error
  - All decisions written to audit log
  - Shadow mode produces no actual intents
"""

from __future__ import annotations

import logging
import threading
import uuid
import warnings
from typing import Any, Callable, Dict, List, Optional

from .base_agent import BaseAgent
from .h1_thought_gate import H1ThoughtGate
from .h4_validator import validate_ai_output
# G3-08 Phase 4 Sub-task 4-1 — Strategist agent_state invalidation hint
# (also reused by Phase 3 Sub-task 3-2 H4 path in strategist_edge_eval).
# env-gated no-op when OPENCLAW_H_STATE_GATEWAY != "1".
# G3-08 Phase 4 Sub-task 4-1 — Strategist agent_state 失效提示
# （Phase 3 Sub-task 3-2 H4 路徑於 strategist_edge_eval 也用）。env=非 "1" 時 no-op。
from .h_state_invalidator import invalidate_async as _invalidate_h_state_async
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
# G3-08 Phase 4 — sibling re-exports for backward compatibility.
# G3-08 Phase 4 — sibling 重新導出以維持向後兼容。
from .strategist_cognitive import (  # noqa: F401 — re-export for tests / patches
    _apply_cognitive_modulation as _sc_apply_cognitive_modulation,
    clear_emergency_mode as _sc_clear_emergency_mode,
    handle_fast_channel as _sc_handle_fast_channel,
    record_trade_outcome as _sc_record_trade_outcome,
    set_cognitive_modulator as _sc_set_cognitive_modulator,
    tick_cognitive_modulator as _sc_tick_cognitive_modulator,
)
from .strategist_edge_eval import (  # noqa: F401 — re-export for tests / patches
    _ai_evaluate as _se_ai_evaluate,
    _build_prompt_context as _se_build_prompt_context,
    _build_route_context as _se_build_route_context,
    _evaluate_edge as _se_evaluate_edge,
    _evaluate_edge_l1_5 as _se_evaluate_edge_l1_5,
    _process_knowledge_update as _se_process_knowledge_update,
    _produce_intents as _se_produce_intents,
)
from .strategist_models import (  # noqa: F401 — re-export for backward compatibility
    EdgeEvaluation,
    StrategistConfig,
    _heuristic_evaluate,
    _parse_sentiment,
)
from .strategist_weights import (  # noqa: F401 — re-export for tests / patches
    _apply_l2_weight_update as _sw_apply_l2_weight_update,
    _apply_pattern_insight as _sw_apply_pattern_insight,
    _apply_regime_weights as _sw_apply_regime_weights,
    get_strategy_weight as _sw_get_strategy_weight,
    set_budget_manager as _sw_set_budget_manager,
    set_truth_registry as _sw_set_truth_registry,
)
from .utils.time_utils import now_ms

logger = logging.getLogger(__name__)


# G8-01 W1 FIX-B (PA RFC §3.1 Option γ)：CognitiveModulator tick 頻率。
# Strategist intel 流量約 ~5/min（per RFC §10），N=10 → 每 ~2 min 一次 update。
# 既保留 modulator EMA 平滑時效（α=0.3 → ~3-4 cycle 收斂），又避免 hot path 壓力。
# G8-01 W1 FIX-B (PA RFC §3.1 Option γ): CognitiveModulator tick cadence.
# Strategist intel volume ~5/min (per RFC §10); N=10 → ~one update every 2 min.
# Preserves modulator EMA convergence (α=0.3 → ~3-4 cycles) without hot-path cost.
_COGNITIVE_TICK_INTERVAL = 10


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
    - strategist_edge_eval / strategist_weights / strategist_cognitive (G3-08 Phase 4)
    委託模組：
    - H1ThoughtGate：AI 前確定性閘門（預算/複雜度/冷卻期）
    - ModelRouter：H3 模型層路由 + L2 後台評估 + L2 快取
    - h4_validator.validate_ai_output：H4 AI 輸出結構驗證
    - strategist_edge_eval / strategist_weights / strategist_cognitive（G3-08 Phase 4）
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
        self._h1_gate = H1ThoughtGate(cost_tracker=cost_tracker)  # rename hazard, see h_state_query_handler.py:356; G3-08-PHASE-4-STRATEGIST-SPLIT 修

        # Backward compat: expose _h1_cooldown via delegate
        # 向後兼容：通過委託暴露 _h1_cooldown
        self._h1_cooldown = self._h1_gate.cooldown_dict

        # Delegate: H3 ModelRouter — model tier routing + L2 cache
        # 委託：H3 模型路由 — 模型層選擇 + L2 快取管理
        self._model_router = ModelRouter()  # rename hazard, see h_state_query_handler.py:358; G3-08-PHASE-4-STRATEGIST-SPLIT 修

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
            # G8-01-FUP-LOSSES-WIRING: consecutive-loss counter consumed by
            # ``tick_cognitive_modulator``. Updated by ``record_trade_outcome()``
            # via Analyst → Strategist callback path (set in strategy_wiring.py).
            # Pre-FUP this key was missing → modulator always saw 0 → modulator
            # state stuck at base values (RFC §3.1 acknowledged limitation).
            # G8-01-FUP-LOSSES-WIRING：``tick_cognitive_modulator`` 消費的連續虧損
            # 計數器，由 ``record_trade_outcome()`` 透過 Analyst → Strategist
            # callback 路徑更新（接線於 strategy_wiring.py）。FUP 前此 key 不存在
            # → modulator 永遠看到 0 → state 卡 base value（RFC §3.1 acknowledged）。
            "consecutive_losses": 0,
            # G8-01-FUP-LOSSES-WIRING: total trade outcomes observed (wins + losses).
            # Diagnostic only — proves the callback actually fired.
            # G8-01-FUP-LOSSES-WIRING：已觀察的總交易結果數（贏 + 輸）。
            # 純診斷用 —— 證明 callback 確實有觸發。
            "trade_outcomes_observed": 0,
            # H1 ThoughtGate skip counters / H1 思考閘門跳過計數器
            "h1_budget_skip": 0,
            "h1_complexity_skip": 0,
            "h1_cooldown_skip": 0,
            # H4 output validation counters / H4 輸出驗證計數器
            # G3-08 Phase 3 Sub-task 3-2 補 validation_pass（pre-G3-08 silent gap）。
            # G3-08 Phase 3 Sub-task 3-2 added validation_pass (pre-G3-08 silent gap).
            "h4_validation_fail": 0,
            "h4_validation_pass": 0,
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

        # GUI heartbeat contract: ms-epoch of most recent observable activity
        # (start / on_message / _handle_intel). 0 means never active. The
        # roster helper prefers ``_last_heartbeat_ms_from_eval_log`` when an
        # eval log entry exists (precise "actually evaluated"), and falls back
        # to this field when the eval log is empty (e.g. all intel gated by H1
        # or rejected before evaluation). Read by
        # ``agents_routes_helpers._build_strategist_card``.
        # GUI 心跳契約：最近一次可觀察活動（start / on_message / _handle_intel）的
        # ms-epoch。0 表示從未活動。Roster helper 優先用
        # ``_last_heartbeat_ms_from_eval_log``（精確的「真評估了」），eval log
        # 為空（如 H1 全 gate / 評估前拒絕）時才回退到此欄位。
        self._last_heartbeat_ms: int = 0

    # ── Lifecycle / 生命週期 ──
    # pause() inherited from BaseAgent. start/stop override to preserve the
    # original info log string (Strategist's start log includes shadow flag).
    # pause() 繼承自 BaseAgent；start/stop 覆蓋保留原有 info log（含 shadow 標誌）。

    def start(self) -> None:
        """Start the agent / 啟動代理"""
        super().start()
        # GUI heartbeat contract: stamp on lifecycle start so the roster card
        # leaves "never active" the moment the agent enters RUNNING (the
        # eval-log path requires actual evaluations, which may not happen for
        # several scan cycles after start).
        # GUI 心跳契約：start() 即蓋章；eval log 路徑需真評估（啟動後可能多
        # 個 scan cycle 才出現），用此欄位讓卡片立即離「從未活動」。
        self._last_heartbeat_ms = now_ms()
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
        # GUI heartbeat contract (M-1 strict): only RUNNING agents stamp.
        # CLAUDE.md 原則 #10 認知誠實 > debug 便利：stopped agent 蓋章 = GUI 矛盾。
        # eval_log 真停滯時 last_hb_ms_from_eval_log → None，stats fallback 為 0
        # → ISO=None → GUI 紅 chip 正確反映 stopped 狀態。
        # GUI 心跳契約（M-1 嚴格化）：僅 RUNNING agent 蓋章；非 RUNNING 不蓋章。
        if self.state != AgentState.RUNNING:
            logger.debug("StrategistAgent not running, ignoring message / 策略師未運行，忽略消息")
            return
        self._last_heartbeat_ms = now_ms()

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

        G3-08 Phase 4 P3 (E2 4-1 NIT-1 LOW): every early-return point also fires
        a no-op-when-disabled h_state hint, so the cache reflects rejection
        events (relevance/age/parse-failure) — not just successful evaluations.
        G3-08 Phase 4 P3（E2 4-1 NIT-1 LOW）：每個 early-return 點同步發出失效
        提示（env=0 時 no-op），使 h_state cache 對拒絕事件保鮮，而非只反映成功路徑。
        """
        # GUI heartbeat contract: _handle_intel is the canonical observable
        # activity for Strategist (direct callers from Conductor / pipeline
        # bypass on_message). Stamped before any early return so even gated
        # intel registers a heartbeat.
        # GUI 心跳契約：_handle_intel 是 Strategist 的標準觀察活動；
        # Conductor/pipeline 直呼者繞過 on_message。蓋章先於任何 early return，
        # 使被 gate 的 intel 仍登記心跳。
        self._last_heartbeat_ms = now_ms()
        # V2: Emergency mode check — discard normal channel intents during emergency
        # 緊急模式檢查 — 緊急時期丟棄正常通道 intent
        if self._emergency_mode.is_set():
            logger.debug(
                "Normal channel intel discarded (emergency mode active) / "
                "正常通道情報已丟棄（緊急模式）"
            )
            _invalidate_h_state_async("agent.strategist.emergency_discard")
            return

        with self._lock:
            self._stats["intel_received"] += 1
            _intel_count = self._stats["intel_received"]

        # G8-01 W1 FIX-B (PA RFC §3.1 Option γ)：
        # 每 N=10 個 intel 觸發一次 CognitiveModulator tick — 解 BUG-B（
        # production 0 caller，modulator 永遠卡在 ctor base value）。
        # 放在 intel_received 增量之後、任何 return 之前，確保 unconditional fire；
        # tick 自身 fail-soft（exception 只 warn 不污染 hot path）。
        # G8-01 W1 FIX-B (PA RFC §3.1 Option γ):
        # Tick CognitiveModulator every N=10 intel events — fixes BUG-B
        # (zero production callers leaving modulator stuck at ctor base values).
        # Placed after intel_received increment and before any early return so
        # firing is unconditional; the tick itself is fail-soft (exceptions
        # only warn-log, never poison the hot path).
        if _intel_count % _COGNITIVE_TICK_INTERVAL == 0:
            _sc_tick_cognitive_modulator(self)

        payload = message.payload
        if not payload:
            logger.warning("Empty intel payload / 空情報負載")
            _invalidate_h_state_async("agent.strategist.empty_payload")
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
            _invalidate_h_state_async("agent.strategist.parse_error")
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
            _invalidate_h_state_async("agent.strategist.relevance_skip")
            return

        # Check age / 檢查年齡
        age_seconds = max(0, (now_ms() - intel.timestamp_ms) / 1000)
        if age_seconds > self.config.max_intel_age_seconds:
            logger.debug("Intel too old: %.0fs > %ds", age_seconds, self.config.max_intel_age_seconds)
            _invalidate_h_state_async("agent.strategist.age_skip")
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
        # G3-08 Phase 4 Sub-task 4-1: hint outside _lock; env=0 no-op.
        # G3-08 Phase 4 Sub-task 4-1：於鎖外送出失效提示；env=0 no-op。
        _invalidate_h_state_async("agent.strategist.intel_handled")

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
        """Backward-compatible delegator to strategist_edge_eval / 向後兼容委託"""
        return _se_produce_intents(self, intel, evaluation)

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

    # ──────────────────────────────────────────────────────────────────────
    # Sibling delegators (G3-08 Phase 4 + Phase 4 P3 LOC slim)
    # Sibling 委託器（G3-08 Phase 4 + Phase 4 P3 LOC 瘦身）
    # ──────────────────────────────────────────────────────────────────────
    # 18 method bodies live in 3 sibling modules:
    #   strategist_edge_eval.py / strategist_weights.py / strategist_cognitive.py
    # Methods below preserve original bound-method signatures so:
    #   1. callsite ``self.method(...)`` paths inside _handle_intel keep working;
    #   2. test patch ``agent.method = MagicMock(wraps=agent.method)`` keeps
    #      finding a real bound method to wrap (instance lookup falls through
    #      to class attr, which is the delegator below);
    #   3. ``patch("app.strategist_agent.X")`` keeps resolving via re-exports
    #      at module load (see top-of-file ``from .strategist_X import …``).
    # G3-08 Phase 4 P3 (2026-04-28): compressed each delegator to 1-line
    # ``def … return …`` (header + per-sibling docstring already explain
    # responsibilities — the delegator itself is mechanical glue).
    #
    # 18 method body 移至 3 sibling 模組，本檔保留原 bound-method signature 為：
    #   1. _handle_intel 內 ``self.method(...)`` callsite 持續可用；
    #   2. test ``agent.method = MagicMock(wraps=agent.method)`` 仍能找到真實
    #      bound method 來 wrap（instance lookup fallback 到 class attr，即下
    #      方的 delegator）；
    #   3. ``patch("app.strategist_agent.X")`` 透過頂部 re-export 解析。
    # G3-08 Phase 4 P3（2026-04-28）：每個 delegator 壓縮為單行 def，header 與
    # sibling 自身的 docstring 已說明職責，delegator 本身只是機械 glue。

    # ── Truth Registry + Strategy Preference Weights → strategist_weights ──
    def set_budget_manager(self, budget_manager: Any) -> None: return _sw_set_budget_manager(self, budget_manager)  # noqa: E704
    def set_truth_registry(self, registry: Any) -> None: return _sw_set_truth_registry(self, registry)  # noqa: E704
    def _apply_pattern_insight(self, insight_payload: dict) -> None: return _sw_apply_pattern_insight(self, insight_payload)  # noqa: E704
    def get_strategy_weight(self, strategy_name: str) -> float: return _sw_get_strategy_weight(self, strategy_name)  # noqa: E704
    def _apply_regime_weights(self, regime: str) -> None: return _sw_apply_regime_weights(self, regime)  # noqa: E704
    def _apply_l2_weight_update(self, intel: Any, evaluation: EdgeEvaluation) -> None: return _sw_apply_l2_weight_update(self, intel, evaluation)  # noqa: E704

    # ── Route Context + Edge Evaluation + Prompt + L1.5 → strategist_edge_eval ──
    def _build_route_context(self, intel: Any) -> dict: return _se_build_route_context(self, intel)  # noqa: E704
    def _evaluate_edge_l1_5(self, intel: Any) -> EdgeEvaluation: return _se_evaluate_edge_l1_5(self, intel)  # noqa: E704
    def _process_knowledge_update(self, knowledge_update: Any, source: str = "cloud_api") -> None: return _se_process_knowledge_update(self, knowledge_update, source)  # noqa: E704
    def _build_prompt_context(self, intel: IntelObject) -> str: return _se_build_prompt_context(self, intel)  # noqa: E704
    def _evaluate_edge(self, intel: IntelObject) -> EdgeEvaluation: return _se_evaluate_edge(self, intel)  # noqa: E704
    def _ai_evaluate(self, intel: IntelObject) -> EdgeEvaluation: return _se_ai_evaluate(self, intel)  # noqa: E704

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

    # ── Backward-compatible H1/H4/H3 method stubs (compressed delegators) ──
    # 1-line wrappers preserving original method signatures for external callers.
    # 1-line 包裝保留原方法簽名，供任何外部調用者使用。
    def _h1_check_budget(self) -> bool: return self._h1_gate._check_budget()  # noqa: E704
    def _h1_complexity_score(self, intel: Any) -> float: return self._h1_gate.complexity_score(intel)  # noqa: E704
    def _h1_check_cooldown(self, intel: Any) -> bool: return self._h1_gate._check_cooldown(intel)  # noqa: E704
    def _validate_ai_output(self, parsed: dict) -> bool: return validate_ai_output(parsed)  # noqa: E704
    def get_h1_snapshot(self) -> Dict[str, Any]: return self._h1_gate.get_h1_snapshot()  # noqa: E704
    def get_h3_snapshot(self) -> Dict[str, Any]: return self._model_router.get_h3_snapshot()  # noqa: E704

    def _h3_route_model(self, intel: Any) -> str:
        # H3 path needs both complexity + route_context; not a 1-line glue.
        # H3 路徑需 complexity + route_context 兩步，非單純 1-line glue。
        complexity = self._h1_gate.complexity_score(intel)
        route_context = self._build_route_context(intel)
        return self._model_router.route(complexity, context=route_context)

    # ── V2: Dual-track Fast Channel + Cognitive Modulator → strategist_cognitive ──
    def handle_fast_channel(self, trigger: str, symbols: list[str] | None = None) -> List[TradeIntent]: return _sc_handle_fast_channel(self, trigger, symbols)  # noqa: E704
    def clear_emergency_mode(self) -> None: return _sc_clear_emergency_mode(self)  # noqa: E704
    def set_cognitive_modulator(self, modulator: Any) -> None: return _sc_set_cognitive_modulator(self, modulator)  # noqa: E704
    def _apply_cognitive_modulation(self, confidence: float) -> tuple[float, float]: return _sc_apply_cognitive_modulation(self, confidence)  # noqa: E704

    # G8-01-FUP-LOSSES-WIRING: trade outcome ingress for CognitiveModulator's
    # consecutive_losses input — wired in strategy_wiring.py to
    # AnalystAgent.set_strategist_loss_callback so every IPC-driven trade
    # analysis advances the counter. Body lifted to strategist_cognitive.py in
    # G3-08 Phase 4 P3 to keep main file under §九 800-line warning.
    # G8-01-FUP-LOSSES-WIRING：CognitiveModulator consecutive_losses 輸入入口，
    # strategy_wiring.py 接 AnalystAgent.set_strategist_loss_callback。Body 於
    # G3-08 Phase 4 P3 移至 strategist_cognitive.py（§九 800 行警告線）。
    def record_trade_outcome(self, net_pnl: float) -> None: return _sc_record_trade_outcome(self, net_pnl)  # noqa: E704

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
                # GUI heartbeat contract: ms-epoch surfaced for roster card.
                # The card prefers eval-log derived heartbeat (precise) and
                # falls back to this when the eval log is empty.
                # GUI 心跳契約：給 roster card 用；卡片優先用 eval log 取，
                # eval log 為空時回退用此欄位。
                "last_heartbeat_ms": int(self._last_heartbeat_ms),
                **dict(self._stats),
            }
        # L2 cache size from ModelRouter's own lock
        # L2 快取大小從 ModelRouter 的專用鎖讀取
        stats["l2_cache_size"] = self._model_router.cache_size
        return stats

    # G3-08 Phase 3 Sub-task 3-2: H4 state snapshot for h_state_cache.
    # G3-08 Phase 3 Sub-task 3-2：給 h_state_cache 用的 H4 狀態 snapshot。
    def get_h4_snapshot(self) -> Dict[str, Any]:
        """H4 validation stats snapshot / H4 驗證統計 snapshot.

        Schema (PA design §5.2 H4ValidationStats parity): validation_fail (int,
        rejected count / 拒絕次數), validation_pass (int, accepted count /
        通過次數). H4 stats caller-side because h4_validator is stateless;
        Phase 3 Sub-task 3-2 補 validation_pass（G3-08 前 silent gap）.
        Pure-read, only acquires self._lock; safe from any thread / 任何線程安全.
        """
        with self._lock:
            return {
                "validation_fail": int(self._stats.get("h4_validation_fail", 0)),
                "validation_pass": int(self._stats.get("h4_validation_pass", 0)),
            }

    # G3-08 Phase 4 Sub-task 4-1: Strategist agent_state snapshot accessor.
    # G3-08 Phase 4 Sub-task 4-1：Strategist agent 狀態 snapshot 存取器。
    def get_strategist_snapshot(self) -> Dict[str, Any]:
        """Thread-safe agent-state snapshot for h_state_cache (PA RFC §2.1, 11 fields).
        Schema parity with Rust ``AgentState.stats: HashMap<String, i64>``: all
        values are int or bool→int (no float / string). Pure-read, takes only
        self._lock; safe from any thread.
        H state cache 用 Strategist 狀態 snapshot（PA RFC §2.1，11 欄位）。
        對齊 Rust ``AgentState.stats: HashMap<String, i64>``，皆 int 或 bool→int。
        純讀、只取 self._lock，任何線程安全。
        """
        with self._lock:
            return {
                "intel_received": int(self._stats.get("intel_received", 0)),
                "intel_evaluated": int(self._stats.get("intel_evaluated", 0)),
                "intents_produced": int(self._stats.get("intents_produced", 0)),
                "intents_shadow_logged": int(self._stats.get("intents_shadow_logged", 0)),
                "evaluations_rejected": int(self._stats.get("evaluations_rejected", 0)),
                "ai_evaluations": int(self._stats.get("ai_evaluations", 0)),
                "heuristic_evaluations": int(self._stats.get("heuristic_evaluations", 0)),
                "errors": int(self._stats.get("errors", 0)),
                "pending_intents": int(len(self._pending_intents)),
                "emergency_mode_active": int(bool(self._emergency_mode.is_set())),
                "cognitive_modulator_connected": int(self._cognitive_modulator is not None),
            }

    def get_recent_evaluations(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent edge evaluations for diagnostics / 獲取最近的 edge 評估用於診斷"""
        with self._lock:
            return list(self._eval_log[-limit:])

    # ── Public scan-interval accessor (H-2) / 公開掃描間隔存取器（H-2）──

    def get_scan_interval_seconds(self) -> int:
        """Return the current EMA-smoothed scan interval in seconds.
        回傳目前 EMA 平滑後的 scan_interval（秒）。

        Public delegate to ``self._cognitive_modulator.get_scan_interval_seconds()``
        introduced for plan ``aa-nifty-walrus.md`` Wave T1: external readers
        (e.g. ``agents_routes.py``) MUST go through this method instead of
        reaching into the private ``_cognitive_modulator`` attribute directly
        (E2 round-2 finding H-2). Behaviour:

        * ``_cognitive_modulator`` not yet injected (cold-start before
          ``set_cognitive_modulator`` runs) → return ``60`` (the
          ``CognitiveModulator`` default base value, kept in lock-step with
          ``_DEFAULT_SCAN_INTERVAL_S`` in ``agents_routes_helpers``).
        * Modulator raises (defensive) → return ``60`` (fail-closed; do not
          let a heart-beat math glitch crash a read-only GUI poll).

        為 plan ``aa-nifty-walrus.md`` Wave T1 新增的對外存取器。其他模組
        （例如 ``agents_routes.py``）讀 scan_interval **必須**走此方法，
        不可直接用 ``_cognitive_modulator`` 私有屬性（E2 round-2 H-2）。
        行為：未注入或例外 → 回 60（CognitiveModulator 預設 base，
        與 ``agents_routes_helpers._DEFAULT_SCAN_INTERVAL_S`` 對齊）。
        """
        modulator = self._cognitive_modulator
        if modulator is None:
            # Cold start: agent constructed but cognitive_modulator not yet
            # injected (set_cognitive_modulator runs later in strategy_wiring).
            # 冷啟：agent 已建構但 cognitive_modulator 尚未注入。
            return 60
        try:
            interval = modulator.get_scan_interval_seconds()
        except Exception:  # noqa: BLE001 — defensive
            # Modulator raised — fall back to base default rather than
            # propagating to a read-only GUI route (CLAUDE.md §二 原則 #6).
            # modulator 例外 — 回後備值，避傳到 read-only GUI route。
            return 60
        if not isinstance(interval, (int, float)):
            return 60
        return max(int(interval), 1)
