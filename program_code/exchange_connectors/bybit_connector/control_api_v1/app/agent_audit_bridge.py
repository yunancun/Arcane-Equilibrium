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
import time
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Warning throttle for fail-open path / Fail-open 警告節流
# ═══════════════════════════════════════════════════════════════════════════════
#
# Background / 背景:
#   If ChangeAuditLog.record_change(...) fails (e.g., DB outage), every
#   _audit(...) call would emit a WARNING. Under the engine's ~50 ticks/sec
#   workload × 5 agents × multiple audit events per decision cycle, a DB
#   outage would flood operator logs within seconds.
#
#   當 ChangeAuditLog.record_change(...) 失敗（例如 DB 中斷）時，每次 _audit(...)
#   都會打 WARNING。在 ~50 ticks/sec × 5 agents × 每決策週期多個審計事件的
#   負載下，DB 中斷幾秒內就會灌滿 operator logs。
#
# Design / 設計:
#   - Throttle WARNING to at most 1 per ``_WARN_THROTTLE_SECONDS`` per
#     (role, event_class) key. Operator still sees a repeating signal if the
#     DB stays down, just not a flood.
#   - Always emit DEBUG for throttled-out events so post-mortem traces are
#     complete when DEBUG logging is enabled.
#   - 60-second default chosen as a balance: long enough to prevent flood
#     but short enough that a 5-min DB outage produces ~5 warnings (obviously
#     visible) rather than 10s of thousands.
#   - ``_WARN_THROTTLE_SECONDS`` is module-level to make future operator
#     tuning trivial (grep-findable knob).
#
# Tuning knob / 可調旋鈕:
#   _WARN_THROTTLE_SECONDS — change here if operator wants more/less warnings.
#   No runtime config binding on purpose: this is a log-hygiene setting, not
#   a trading parameter, and hot-reloading logging throttles is not worth
#   the IPC surface area. If you want to change it, edit this constant and
#   restart the control_api service.
_WARN_THROTTLE_SECONDS: float = 60.0

# Keyed by (role_name, event_class_str); value is monotonic timestamp of last WARN.
# See thread-safety discussion in make_agent_audit_callback docstring — no lock.
# 以 (role_name, event_class_str) 為鍵；值為最後一次 WARN 的 monotonic 時間戳。
# 執行緒安全討論見 make_agent_audit_callback docstring — 無鎖。
_LAST_WARN_AT: Dict[Tuple[str, str], float] = {}


def _reset_warn_throttle() -> None:
    """
    Reset the warning throttle state (test helper).
    重置 warning 節流狀態（測試輔助）。

    Mirrors the ``_reset_winsorize_counter`` pattern in
    ``ml_training/realized_edge_stats.py``. Underscore prefix = internal /
    test-only; intentionally not in ``__all__``.
    仿照 ``ml_training/realized_edge_stats.py`` 的 ``_reset_winsorize_counter``
    模式。底線前綴 = 內部 / 僅測試用；故意不列入 ``__all__``。
    """
    _LAST_WARN_AT.clear()


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
        - record_change raises               → swallowed + throttled warning log
        The wrapped agent's _audit call ALWAYS returns None without side effects
        if the bridge cannot persist. Audit loss is preferred over trade disruption.

    Thread-safety / 執行緒安全:
        The returned ``_callback`` is SAFE for concurrent invocation from
        multiple agent threads (Scout / Strategist / Guardian / Analyst /
        Executor each run on their own thread under the 5-Agent framework).

        返回的 ``_callback`` 可在多個 agent 執行緒中並發呼叫是安全的
        （5-Agent 框架下 Scout / Strategist / Guardian / Analyst / Executor
        各自運行於獨立執行緒）。

        Correctness properties / 正確性保證:
          1. ``ChangeAuditLog.record_change(...)`` is itself thread-safe:
             verified by ``threading.RLock()`` (``_lock``) guarding all
             mutating sections in ``change_audit_log.py`` (record_change /
             approve / reject / snapshot / rollback paths). The bridge relies
             on this — it does NOT add a redundant outer lock on the fast path.
             ``ChangeAuditLog.record_change(...)`` 本身為執行緒安全：
             ``change_audit_log.py`` 所有會變更狀態的區段皆以 ``threading.RLock()``
             (``_lock``) 保護（record_change / approve / reject / snapshot /
             rollback 等）。本橋接依賴該保證，熱路徑上不加冗餘外層鎖。

          2. Fail-open exception handling (``except Exception``) ensures no
             partial-write corruption escapes back into the agent's main
             path; a failed bridge call is equivalent to a dropped audit row,
             never a half-written record nor a raised exception.
             失敗開放的 ``except Exception`` 確保不會有半寫狀態回流至 agent 主路徑；
             橋接失敗等同於 audit row 被丟棄，絕不會出現半寫記錄或向上拋異常。

          3. The module-level ``_LAST_WARN_AT`` throttle dict used by the
             warning log path is NOT protected by a lock. This is an
             intentional design choice: the throttle is approximate — under
             a race, worst case is a duplicate warning (or one warning missed
             by a few microseconds). Last-write-wins on a (role, event_class)
             timestamp is acceptable since the dict key set is small (<20
             tuples for the 5 agents) and CPython dict writes to existing
             keys are atomic at the C level. No correctness invariant
             depends on strict monotonicity of ``_LAST_WARN_AT[key]``.
             模組級 ``_LAST_WARN_AT`` 節流字典（warning log 路徑使用）未加鎖。
             此為有意設計：節流本就是近似的 —— race condition 下最壞情況為
             重複 warning 一次（或漏印一次僅差幾微秒）。以 (role, event_class)
             為鍵的時間戳「後寫者勝」可接受，因鍵空間小（5 agents 下 <20 tuple），
             且 CPython 對既有 key 的 dict 寫入在 C 層面為原子操作。
             無任何正確性不變式依賴 ``_LAST_WARN_AT[key]`` 的嚴格單調性。

        No runtime Lock is added to the bridge itself — the hot path remains
        lock-free. This keeps per-tick overhead minimal under the expected
        5-Agent × ~50 ticks/sec workload.
        橋接本身不引入任何 runtime Lock —— 熱路徑保持無鎖，使得 5-Agent ×
        ~50 ticks/sec 的預期負載下每 tick 開銷最小。
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
            #
            # Throttle WARNING to at most 1 per _WARN_THROTTLE_SECONDS per
            # (role, event_class). This prevents log flood under DB outage
            # while still surfacing a visible signal every throttle window.
            # DEBUG is always emitted so post-mortem traces are complete.
            #
            # 節流 WARNING：每 _WARN_THROTTLE_SECONDS 每 (role, event_class)
            # 最多印一次。防止 DB 中斷時 log 被灌爆，同時每節流窗口仍有可見訊號。
            # DEBUG 永遠印，確保事後追查 trace 完整。
            event_class = _classify_event(event_type)
            key = (role_name, event_class)
            now = time.monotonic()
            last_at = _LAST_WARN_AT.get(key, 0.0)
            if now - last_at >= _WARN_THROTTLE_SECONDS:
                _LAST_WARN_AT[key] = now  # race-tolerant (see module docstring)
                logger.warning(
                    "agent_audit_bridge: record_change failed (non-fatal) "
                    "role=%s event=%s err=%s / 橋接失敗（非致命，每 %.0fs 限印一次）",
                    role_name, event_type, e, _WARN_THROTTLE_SECONDS,
                )
            else:
                logger.debug(
                    "agent_audit_bridge: record_change failed (throttled) "
                    "role=%s event=%s err=%s / 橋接失敗（已節流，%.1fs since last WARN）",
                    role_name, event_type, e, now - last_at,
                )

    return _callback


__all__ = ["make_agent_audit_callback"]
