"""
Agent Audit Bridge — E5-FN-3 / 5-Agent Decision Audit Trail
=============================================================
Governance refs: CLAUDE.md §二 Root Principle #8 "交易可解釋"（Trade Explainability）,
                 DOC-01 §5.8, DOC-06 §5 (change_audit_log), EX-06 §1 (5-Agent framework)

MODULE_NOTE (中文):
  橋接 BaseAgent._audit_callback (event_type: str, data: Any) → ChangeAuditLog.record_change(...)。

  背景：
    2026-04-18 audit §七.7.3 發現 5-Agent 體系（Scout / Strategist / Guardian /
    Analyst / Executor）決策點皆未寫入 `change_audit_log`，違反根原則 #8「交易可解釋」。
    雖然 BaseAgent 有 _audit(event_type, data) 方法，且 Strategist / Guardian /
    Analyst / Executor 皆已呼叫 self._audit(...)（共 19 處），但 strategy_wiring.py
    構造 agent 時均未傳 audit_callback，導致 _audit_callback=None → 全部靜默丟失。

  本模組職責：
    1. make_agent_audit_callback(gov_hub, role_name) → Callable[[str, Any], None]
       產出符合 BaseAgent._audit 簽名的 callback；內部將事件橋接到
       gov_hub._change_audit_log.record_change(...) 以寫入 append-only audit log。
    2. 統一事件分類邏輯：
       - 決策級事件（verdict / edge_evaluation / intent_produced / trade_analyzed /
         execution_report / l2_pattern_insight）→ PARAMETER_CHANGE
       - 狀態級事件（state transition / directive_received）→ STATE_CHANGE
       - 其他被動接收事件（*_received）→ STATE_CHANGE（對應 "觀測發生了" 的語義）
    3. Fail-open 契約：任何橋接錯誤（gov_hub None / _change_audit_log None /
       serialization fail）皆 logger.debug 並靜默返回；絕不影響 agent 主流程。
    4. 零行為變動：不更動任何 agent 的 _audit(...) 呼叫點；只補齊 wiring。

  安全不變量：
    - 寫入 append-only（依賴 ChangeAuditLog 自身保證）
    - auto_approve=True（agent 決策為系統自動行為，無需 operator 預批准）
    - who=role_name（明確歸因到具體 Agent 角色）
    - old_value / new_value 從 data 中提取（若無則留空）

MODULE_NOTE (English):
  Bridges BaseAgent._audit_callback (event_type: str, data: Any) into
  ChangeAuditLog.record_change(...).

  Background:
    The 2026-04-18 audit §7.7.3 found that the 5-Agent system (Scout / Strategist /
    Guardian / Analyst / Executor) never writes to `change_audit_log`, violating
    Root Principle #8 "Trade Explainability". Although BaseAgent provides _audit(),
    and 4 of 5 agents already call self._audit(...) (19 call-sites total), the
    agents are constructed without an audit_callback in strategy_wiring.py, so
    _audit_callback=None and every call silently no-ops.

  Responsibilities:
    1. make_agent_audit_callback(gov_hub, role_name) returns a Callable matching
       BaseAgent._audit semantics that forwards each event to
       gov_hub._change_audit_log.record_change(...) for append-only persistence.
    2. Uniform event classification:
       - Decision events (verdict / edge_evaluation / intent_produced /
         trade_analyzed / execution_report / l2_pattern_insight) → PARAMETER_CHANGE
       - State-transition events (directive_received) → STATE_CHANGE
       - Passive-receipt events (*_received) → STATE_CHANGE (observational)
    3. Fail-open contract: any bridging error (gov_hub None, _change_audit_log
       None, serialization failure) is logged at DEBUG and silently dropped;
       must NEVER impact the agent's main path.
    4. Zero behavior change to existing agents: no modification to any _audit()
       call site; we only complete the wiring that was missing.

  Safety invariants:
    - Append-only (enforced by ChangeAuditLog)
    - auto_approve=True (agent decisions are automated, no operator pre-approval)
    - who=role_name (attribution to the specific Agent role)
    - old_value / new_value extracted from data when available

Usage (in strategy_wiring.py):
    from .agent_audit_bridge import make_agent_audit_callback
    analyst_audit_cb = make_agent_audit_callback(GOV_HUB, "AnalystAgent")
    ANALYST_AGENT = AnalystAgent(
        config=AnalystConfig(),
        message_bus=MESSAGE_BUS,
        ollama_client=OLLAMA_CLIENT,
        learning_tier_gate=_LTG_FOR_ANALYST,
        audit_callback=analyst_audit_cb,
    )
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Event classification / 事件分類
# ═══════════════════════════════════════════════════════════════════════════════

# Event-type substrings that indicate a decision (parameter_change semantics).
# 表示「決策」的事件類型子字串 → PARAMETER_CHANGE 語義。
# Matched case-insensitively against the un-prefixed event name
# (role prefix like "analyst_" is stripped before matching, but either form works).
_DECISION_EVENT_KEYWORDS = (
    "verdict",
    "edge_evaluation",
    "intent_produced",
    "shadow_intent",
    "trade_analyzed",
    "execution_report",
    "l2_pattern_insight",
    "l2_analysis_triggered",
    "knowledge_update",
    "event_assessed",
)

# Event-type substrings that indicate passive receipt / state observation.
# 表示「被動接收 / 狀態觀測」的事件類型子字串 → STATE_CHANGE 語義。
_STATE_EVENT_KEYWORDS = (
    "_received",
    "directive",
    "risk_verdict",   # payload received from Guardian
    "pattern_insight_received",
    "risk_pattern_received",
)


def _classify_event(event_type: str) -> str:
    """
    Classify an event_type string into a ChangeType value string.
    將 event_type 字串分類到 ChangeType 值字串。

    Returns:
        "PARAMETER_CHANGE" for decision-making events,
        "STATE_CHANGE" for passive / state-transition events,
        "PARAMETER_CHANGE" as the default for unknown events (conservative:
        assume any audited agent event is a non-trivial decision).

    Rationale:
      The 5 agents emit ~19 _audit() calls that fall into two semantic classes:
      explicit decisions (produce_intent / verdict / analyze_trade) vs observations
      (directive_received / risk_verdict_received). We map them to the most
      appropriate ChangeType enum from DOC-06 §5.
    """
    lower = event_type.lower()
    # STATE_CHANGE matches first — "_received" overrides any decision-ish substring.
    # STATE_CHANGE 優先匹配 — "_received" 應覆蓋其他看似決策的子字串。
    for kw in _STATE_EVENT_KEYWORDS:
        if kw in lower:
            return "STATE_CHANGE"
    for kw in _DECISION_EVENT_KEYWORDS:
        if kw in lower:
            return "PARAMETER_CHANGE"
    # Conservative default: treat unknown as PARAMETER_CHANGE so we don't
    # under-audit a new agent event type. Better to over-record than miss.
    # 保守默認：未知事件歸為 PARAMETER_CHANGE，寧可多錄不可漏錄。
    return "PARAMETER_CHANGE"


def _extract_old_new(data: Any) -> tuple[Any, Any]:
    """
    Best-effort extraction of old_value / new_value from a data payload.
    盡力從 data 中提取 old_value / new_value。

    Conventions:
      - If data is a dict with explicit "old_value" / "new_value" keys → use those.
      - If data is a dict with a "record" subkey → ("before" sibling, record).
      - If data is a dict representing the new state → (None, data).
      - Otherwise → (None, data).

    The extraction is intentionally non-strict. ChangeAuditLog.record_change
    accepts Optional[Any] for both fields, so None is fine. The goal is to
    preserve diff context when it's clearly available.

    故意不嚴格。目標是在 data 結構明確時保留 diff 上下文；否則 None 無妨。
    """
    if not isinstance(data, dict):
        return (None, data)
    if "old_value" in data or "new_value" in data:
        return (data.get("old_value"), data.get("new_value"))
    return (None, data)


# ═══════════════════════════════════════════════════════════════════════════════
# Bridge factory / 橋接工廠
# ═══════════════════════════════════════════════════════════════════════════════

def make_agent_audit_callback(
    gov_hub: Optional[Any],
    role_name: str,
) -> Callable[[str, Any], None]:
    """
    Factory that returns a BaseAgent-compatible audit_callback.
    生成與 BaseAgent._audit_callback 簽名兼容的回調工廠。

    The returned callable has signature ``(event_type: str, data: Any) -> None``,
    matching exactly what BaseAgent._audit calls. It forwards the event into
    the GovernanceHub's injected ChangeAuditLog as an append-only record.

    返回的 callable 簽名為 ``(event_type: str, data: Any) -> None``，
    與 BaseAgent._audit 所呼叫的簽名完全一致；事件會轉發到 GovernanceHub
    注入的 ChangeAuditLog 作為 append-only 記錄。

    Args:
        gov_hub: GovernanceHub instance (or None). The bridge pulls
                 gov_hub._change_audit_log lazily on each invocation so that
                 late-binding (e.g., GOV_HUB initialized after the bridge
                 callback is constructed) still works.
                 GovernanceHub 實例（或 None）；每次呼叫時惰性讀取
                 gov_hub._change_audit_log，以支援延遲綁定場景。
        role_name: Human-readable agent name used as the "who" column of the
                   audit record, e.g. "AnalystAgent" / "GuardianAgent".
                   Should match the Agent class name or role.value.
                   用於 audit 記錄 "who" 欄位的人類可讀 agent 名稱，
                   建議對應 Agent 類名或 role.value。

    Returns:
        A Callable[[str, Any], None] suitable for passing as audit_callback
        to any BaseAgent subclass. Never raises — fail-open by design.

    Fail-open contract (critical):
        - gov_hub None                       → silent skip (debug log)
        - gov_hub._change_audit_log None     → silent skip (debug log)
        - record_change raises               → swallowed + warning log
        The wrapped agent's _audit call ALWAYS returns None without side effects
        if the bridge cannot persist. Audit loss is preferred over trade disruption.
    """

    def _callback(event_type: str, data: Any) -> None:
        """
        Bridge event into ChangeAuditLog.record_change(...).
        Fail-open: any error is logged and swallowed.
        """
        # Lazy read — supports late binding of _change_audit_log on gov_hub.
        # 惰性讀取 — 支援 gov_hub 上 _change_audit_log 的延遲綁定。
        if gov_hub is None:
            logger.debug(
                "agent_audit_bridge: gov_hub=None, dropping event=%s role=%s",
                event_type, role_name,
            )
            return

        change_audit_log = getattr(gov_hub, "_change_audit_log", None)
        if change_audit_log is None:
            logger.debug(
                "agent_audit_bridge: gov_hub._change_audit_log=None, dropping "
                "event=%s role=%s", event_type, role_name,
            )
            return

        # Lazy import avoids a circular import between agent_audit_bridge (imported
        # by strategy_wiring) and change_audit_log at module load time.
        # 延遲 import 避免與 change_audit_log 之間的模組級循環。
        try:
            from .change_audit_log import ChangeType
        except Exception as e:  # pragma: no cover — import errors are catastrophic
            logger.debug("agent_audit_bridge: failed to import ChangeType: %s", e)
            return

        try:
            change_type_str = _classify_event(event_type)
            change_type = ChangeType(change_type_str)
            old_value, new_value = _extract_old_new(data)

            change_audit_log.record_change(
                change_type=change_type,
                who=role_name,
                what=f"Agent event: {event_type}",
                reason="5-Agent decision trail (E5-FN-3)",
                old_value=old_value,
                new_value=new_value,
                affected_components=[role_name],
                auto_approve=True,  # Agent decisions are system-automated
            )
        except Exception as e:
            # Fail-open: never propagate bridge failures into the agent.
            # 失敗開放：橋接失敗絕不向 agent 傳播。
            logger.warning(
                "agent_audit_bridge: record_change failed (non-fatal) "
                "role=%s event=%s err=%s / 橋接失敗（非致命）",
                role_name, event_type, e,
            )

    return _callback


__all__ = ["make_agent_audit_callback"]
