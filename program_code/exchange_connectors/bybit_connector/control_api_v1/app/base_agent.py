"""
E5-P1-4 — BaseAgent: shared lifecycle + audit + cost-tracking skeleton for 5-Agent system
==========================================================================================
Governance refs: EX-06 §1, DOC-04 §G Multi-Agent, DOC-01 §5.15

MODULE_NOTE (中文):
  BaseAgent 是 5-Agent 体系（Scout / Strategist / Guardian / Analyst / Executor）
  的公共骨架。只抽離真正重複的部分，不改變任何具體 Agent 的行為、路由、或 prompt。

  抽離內容：
  1. lifecycle：start() / pause() / stop() 三個一行方法
  2. audit：_audit() 封裝，帶 role-prefix 的審計事件名（strategist_/guardian_/...）
  3. cost_tracker 安全記錄：_record_llm_call() 包裝 provider/model/usd 記錄，
     所有異常均 swallow + log，保持 fail-open（對交易安全無影響）
  4. get_stats() 基底字段（role + state），子類 extend 自己的 _stats
  5. 公共 __init__ 字段：state / _lock / bus / _audit_callback

  保留給子類：
  - on_message() 路由（每個 Agent 的 MessageType 不同）
  - 具體業務邏輯（review_intent / produce_intel / analyze_trade / execute_order / ...）
  - LLM 調用（委託給 llm_call_wrapper 模組）

  零行為改動原則：
  - BaseAgent 不新增任何 public method
  - 所有既有 method signature 完全保留
  - 審計前綴（role.value）與舊的 hard-coded 字串一致

MODULE_NOTE (English):
  BaseAgent is a shared skeleton for the 5-Agent system (Scout / Strategist /
  Guardian / Analyst / Executor). Only truly duplicated surface is extracted;
  no behavior, routing, or prompt is changed.

  Extracted surface:
  1. lifecycle: start() / pause() / stop() — identical 3-line methods
  2. audit: _audit() wrapper with role-prefixed event name
  3. Safe cost tracker recording: _record_llm_call() encapsulates provider/model/usd
     accounting with fail-open exception swallow + log (never affects trading)
  4. get_stats() base fields (role + state); subclasses extend their own _stats
  5. Common __init__ fields: state / _lock / bus / _audit_callback

  Left to subclasses:
  - on_message() routing (each Agent handles different MessageType)
  - Domain logic (review_intent / produce_intel / analyze_trade / execute_order / ...)
  - LLM invocation (delegated to llm_call_wrapper module)

  Zero-behavior-change principle:
  - BaseAgent adds no new public methods
  - All existing method signatures preserved
  - Audit prefix (role.value) matches the previously hard-coded strings
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

if TYPE_CHECKING:  # pragma: no cover — annotations only, avoids circular import
    # Type-only imports so BaseAgent can be defined in multi_agent_framework
    # (where ScoutAgent lives) without a module-level cycle.
    # 僅用於類型註解；避免與 multi_agent_framework 形成模組級循環 import。
    from .multi_agent_framework import AgentRole, AgentState, MessageBus  # noqa: F401

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# BaseAgent / 5-Agent 公共基類
# ═══════════════════════════════════════════════════════════════════════════════

class BaseAgent:
    """
    Shared skeleton for the 5 Agents (Scout/Strategist/Guardian/Analyst/Executor).
    5-Agent 系統的公共骨架類。

    Subclasses MUST:
      - Set `self.role` to an AgentRole value (used by _audit prefix and get_stats)
        將 self.role 設為 AgentRole 值（被 _audit 前綴和 get_stats 使用）
      - Call BaseAgent.__init__(...) from their own __init__
        在自己的 __init__ 中調用 BaseAgent.__init__(...)
      - Implement on_message() (dispatch is agent-specific / 分發是 agent 特定的)

    Subclasses MAY:
      - Override start() / pause() / stop() for custom lifecycle hooks
      - Extend get_stats() by returning super().get_stats() merged with own fields
      - Access self.cost_tracker directly (same ref as passed to __init__)
    """

    # Default role; concrete subclasses MUST override via class attr or in __init__.
    # Set lazily inside __init__ to sidestep the multi_agent_framework module cycle.
    # 默認 role；具體子類必須覆蓋。延遲在 __init__ 中設置，避免循環 import。
    role: "AgentRole"  # type: ignore[name-defined]

    def __init__(
        self,
        *,
        role: Optional["AgentRole"] = None,  # type: ignore[name-defined]
        message_bus: Optional["MessageBus"] = None,  # type: ignore[name-defined]
        audit_callback: Optional[Callable] = None,
        cost_tracker: Optional[Any] = None,
    ) -> None:
        """
        Initialize common Agent fields.
        初始化公共 Agent 字段。

        role: Agent role enum; if None, falls back to class attr `role`.
              Agent 角色枚舉；None 時回退到類屬性 role。
        message_bus: Optional MessageBus for inter-agent communication.
                     可選的 MessageBus 用於 agent 間通信。
        audit_callback: Optional callable (event_type: str, data: Any) -> None.
                        可選回調，簽名 (event_type: str, data: Any) -> None。
        cost_tracker: Optional object exposing record_call(provider, model, ...).
                      可選對象，需提供 record_call(provider, model, ...) 方法。
        """
        # Lazy import to avoid module-level circular import with multi_agent_framework.
        # 延遲 import 避免與 multi_agent_framework 的模組級循環。
        from .multi_agent_framework import AgentState as _AgentState

        # Allow per-instance override; fall back to class attribute (subclasses set it).
        # 允許實例級覆蓋；回退到子類類屬性。
        if role is not None:
            self.role = role

        self.bus = message_bus
        self._audit_callback = audit_callback
        self.cost_tracker = cost_tracker

        self.state = _AgentState.INITIALIZING
        self._lock: threading.Lock = threading.Lock()

        # Subclasses populate their own _stats dict in their __init__.
        # 子類在自己的 __init__ 中填充 _stats 字典。
        # BaseAgent provides the attribute so get_stats() never KeyErrors.
        # BaseAgent 提供該屬性，確保 get_stats() 不會 KeyError。
        self._stats: Dict[str, Any] = {}

    # ── Lifecycle / 生命週期 ──

    def start(self) -> None:
        """
        Transition to RUNNING. / 切換到 RUNNING 狀態。

        Intentionally bare (no logging) to preserve per-agent log semantics.
        Subclasses that previously logged "started" continue to do so via their
        own start() which calls super().start() first.
        刻意不打日誌，保留各 Agent 原有的 log 行為。原本有 log 的子類在自己的
        start() 中呼叫 super().start() 後再 log。
        """
        from .multi_agent_framework import AgentState as _AgentState
        self.state = _AgentState.RUNNING

    def pause(self) -> None:
        """Transition to PAUSED. / 切換到 PAUSED 狀態。"""
        from .multi_agent_framework import AgentState as _AgentState
        self.state = _AgentState.PAUSED

    def stop(self) -> None:
        """
        Transition to STOPPED. / 切換到 STOPPED 狀態。

        Intentionally bare — see start().
        刻意不打日誌，理由同 start()。
        """
        from .multi_agent_framework import AgentState as _AgentState
        self.state = _AgentState.STOPPED

    # ── Audit / 審計 ──

    def _audit(self, event_type: str, data: Any) -> None:
        """
        Write an audit record via the injected callback.
        通過注入的回調寫入審計記錄。

        Event type is prefixed with role (e.g. "strategist_edge_evaluation").
        事件類型以 role 作為前綴（如 "strategist_edge_evaluation"）。

        fail-open: callback exceptions are swallowed and logged at DEBUG level
        so audit failures never break the live trading pipeline.
        失敗開放：回調異常被吞掉並以 DEBUG 級別記錄，審計失敗絕不中斷交易管線。
        """
        if self._audit_callback is None:
            return
        try:
            self._audit_callback(f"{self.role.value}_{event_type}", data)
        except Exception as e:  # noqa: BLE001 — fail-open by design / 設計上失敗開放
            logger.debug("Audit callback error: %s", e)

    # ── Cost-tracker helper / 成本追蹤輔助 ──

    def _record_llm_call(
        self,
        *,
        provider: str,
        model: str,
        duration_ms: float = 0.0,
        cost_usd: float = 0.0,
        prompt_tokens: int = 0,
    ) -> None:
        """
        Safely record an LLM call into cost_tracker, swallowing any exceptions.
        安全地向 cost_tracker 記錄一次 LLM 調用，吞掉所有異常。

        Preserves the exact semantics previously open-coded in StrategistAgent:
        calls `cost_tracker.record_call(provider, model, duration_ms, cost_usd,
        prompt_tokens)` when available; otherwise silently no-ops.
        保留原先在 StrategistAgent 中手寫的語義：存在時調用 record_call(...)；
        否則靜默跳過。

        This is a pure helper — it does NOT decide whether to call (caller must
        gate on their own routing logic). cost_tracker=None means "no budget
        tracking" (fail-open).
        此為純輔助方法 — 不決定是否調用（調用者用自己的路由邏輯閘控）。
        cost_tracker=None 表示「不追蹤預算」（fail-open）。
        """
        if self.cost_tracker is None:
            return
        try:
            record_fn = getattr(self.cost_tracker, "record_call", None)
            if record_fn is None:
                return
            record_fn(
                provider=provider,
                model=model,
                duration_ms=duration_ms,
                cost_usd=cost_usd,
                prompt_tokens=prompt_tokens,
            )
        except Exception as e:  # noqa: BLE001 — non-fatal per principle 13 infra
            logger.warning(
                "cost_tracker.record_call failed for %s/%s: %s / "
                "成本記錄失敗（非致命）：%s/%s",
                provider, model, e, provider, model,
            )

    # ── Status / 狀態 ──

    def get_stats(self) -> Dict[str, Any]:
        """
        Return base status dict: role + state + shallow copy of _stats.
        返回基礎狀態字典：role + state + _stats 的淺拷貝。

        Subclasses typically override to merge additional fields, e.g.::

            def get_stats(self):
                with self._lock:
                    return {**super().get_stats(), "pending_intents": len(...)}

        子類通常覆蓋以合併額外字段。
        """
        with self._lock:
            return {
                "role": self.role.value,
                "state": self.state.value,
                **dict(self._stats),
            }
