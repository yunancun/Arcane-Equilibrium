"""
MODULE_NOTE (中文):
  ScoutAgent + ScoutConfig — 5-Agent 體系中的「眼睛與耳朵」（EX-06 §3）。
  負責新聞掃描、事件日曆（Token Unlock / 上架 / 協議升級 / FOMC / CPI）、
  情緒分析、交易所異常監控；輸出 IntelObject 與 EventAlert，並標記資料品質
  （fact / inference / hypothesis）。Scout 不能產生交易信號（由 Strategist 決定）、
  不能修改風控參數（只通知 Guardian 重大事件）、不能直接呼叫交易所 API。

  G3-08-FUP-MAF-SPLIT 從 multi_agent_framework.py 抽出，維持原有所有接口；
  透過主檔 noqa: F401 re-export 保證向後相容（test / scout_routes /
  strategy_wiring legacy caller 等 ``from .multi_agent_framework import ScoutAgent``
  路徑不受影響）。模式對齊 6fac0ca (strategist split) 與 73c1f3d (cost_tracker split)。

MODULE_NOTE (English):
  ScoutAgent + ScoutConfig — the "eyes and ears" of the 5-agent system (EX-06 §3).
  Responsible for news scanning, event calendar (Token Unlock / listing / protocol
  upgrade / FOMC / CPI), sentiment analysis, exchange anomaly monitoring; emits
  IntelObject and EventAlert with data-quality marking (fact / inference /
  hypothesis). Scout CANNOT generate trade signals (Strategist decides), modify
  risk parameters (only notifies Guardian of major events), or directly call the
  exchange API for trading.

  Extracted from multi_agent_framework.py per G3-08-FUP-MAF-SPLIT; all interfaces
  preserved; backward compatibility via noqa: F401 re-export in main file (test,
  scout_routes, strategy_wiring legacy callers ``from .multi_agent_framework
  import ScoutAgent`` continue to resolve). Mirrors 6fac0ca (strategist split)
  and 73c1f3d (cost_tracker split) patterns.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

# G3-08 Phase 4 Sub-task 4-5: ScoutAgent state-change events push
# ``invalidate_h_state`` notifications to Rust h_state_cache; when env=0
# the singleton is no-op (zero overhead). Mirrors Strategist Sub-task 4-1.
# G3-08 Phase 4 Sub-task 4-5：ScoutAgent 狀態事件推送 invalidate_h_state
# 至 Rust；env=0 時 singleton 為 no-op（零負擔）。對齊 Strategist Sub-task 4-1。
from .base_agent import BaseAgent
from .h_state_invalidator import invalidate_async as _invalidate_h_state_async
from .multi_agent_framework import (
    AgentMessage,
    AgentRole,
    DataQualityLevel,
    EventAlert,
    IntelObject,
    MessageBus,
    MessageType,
    SentimentScore,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 4. Scout Agent (EX-06 §3)
# ─────────────────────────────────────────────

@dataclass
class ScoutConfig:
    """Configuration for Scout Agent."""
    news_scan_interval_minutes: int = 30
    event_calendar_lead_hours: float = 24.0
    fomc_lead_hours: float = 2.0
    token_unlock_lead_hours: float = 24.0
    relevance_threshold: float = 0.3


class ScoutAgent(BaseAgent):
    """EX-06 §3 — system's "eyes and ears".

    Responsibilities:
    - News search (every 30min via search degradation)
    - Event calendar (Token Unlock / listing / protocol upgrade / FOMC / CPI)
    - Sentiment analysis (positive / negative / neutral)
    - Exchange anomaly monitoring (large liquidation / funding rate spike / OI shift)
    - Data quality marking: fact / inference / hypothesis (§3.4)

    Scout CANNOT:
    - Generate trade signals (only provides intel, Strategist decides)
    - Modify risk parameters (only notifies Guardian of major events)
    - Directly call exchange API for trading

    Inherits BaseAgent for shared lifecycle + audit skeleton (E5-P1-4).
    繼承 BaseAgent 以共享生命週期 + 審計骨架（E5-P1-4）。
    """

    role = AgentRole.SCOUT  # Class-level role; BaseAgent exposes via self.role.value

    def __init__(
        self,
        config: Optional[ScoutConfig] = None,
        message_bus: Optional[MessageBus] = None,
        *,
        audit_callback: Optional[Callable] = None,
    ):
        # Preserve legacy positional signature (config, message_bus); BaseAgent takes kwargs.
        # audit_callback is keyword-only to avoid positional collision with legacy callers
        # such as ScoutAgent(config=..., message_bus=...) or ScoutAgent(message_bus=bus).
        # E5-FN-3-FUP-d: audit_callback is now forwarded to BaseAgent (previously
        # hardcoded to None). When strategy_wiring.py injects an agent_audit_bridge
        # callback, Scout's produce_intel / produce_event_alert call-sites write
        # append-only rows into change_audit_log (Root Principle #8 "Trade Explainability").
        # When left as None (default), behavior is identical to the pre-FUP-d era.
        # 保留舊式位置參數簽名（config, message_bus）；BaseAgent 走 kwargs。
        # audit_callback 為 keyword-only 以避免與 ScoutAgent(config=..., message_bus=...)
        # 等舊呼叫簽名的位置參數碰撞。
        # E5-FN-3-FUP-d：audit_callback 改為轉發給 BaseAgent（原本硬編碼 None）；
        # strategy_wiring.py 注入 bridge callback 後，Scout 的 produce_intel /
        # produce_event_alert 呼叫點會寫入 change_audit_log（根原則 #8「交易可解釋」）。
        # None（預設）時行為與 FUP-d 之前完全一致。
        super().__init__(
            role=AgentRole.SCOUT,
            message_bus=message_bus,
            audit_callback=audit_callback,
            cost_tracker=None,
        )
        self.config = config or ScoutConfig()
        self._intel_log: List[IntelObject] = []
        self._alert_log: List[EventAlert] = []
        self._stats = {"intel_produced": 0, "alerts_produced": 0, "scans_completed": 0}

    # Lifecycle inherited from BaseAgent (bare start/pause/stop, no logging —
    # matches pre-E5-P1-4 Scout behavior exactly).
    # 生命週期方法繼承自 BaseAgent（無 log，與 E5-P1-4 前的 Scout 行為完全一致）。

    # ── core capabilities ──

    def produce_intel(
        self,
        source: str,
        content: str,
        symbols: List[str],
        *,
        data_quality: DataQualityLevel = DataQualityLevel.FACT,
        sentiment: SentimentScore = SentimentScore.NEUTRAL,
        relevance_score: float = 0.5,
        freshness_seconds: int = 0,
        metadata: Optional[Dict] = None,
    ) -> IntelObject:
        """Create and dispatch an intel_object (§3.2).

        All outputs carry data_quality marking (§3.4).
        """
        intel = IntelObject(
            source=source,
            content=content,
            symbols=symbols,
            data_quality=data_quality,
            sentiment=sentiment,
            relevance_score=relevance_score,
            freshness_seconds=freshness_seconds,
            metadata=metadata or {},
        )

        with self._lock:
            self._intel_log.append(intel)
            self._stats["intel_produced"] += 1

        # E5-FN-3-FUP-d: append-only audit before bus routing so intel is audited
        # even when bus is None or when relevance falls below threshold.
        # Fail-open: _audit is a no-op when _audit_callback is None (BaseAgent).
        # E5-FN-3-FUP-d：在匯流排路由前先寫審計記錄，確保 bus=None 或 relevance
        # 低於閾值時 intel 仍被審計；_audit 在 _audit_callback=None 時為 no-op。
        self._audit("intel_produced", intel.to_dict())

        # Route to Strategist via bus
        if self.bus and relevance_score >= self.config.relevance_threshold:
            msg = AgentMessage(
                sender=AgentRole.SCOUT,
                receiver=AgentRole.STRATEGIST,
                message_type=MessageType.INTEL_OBJECT,
                priority=3,
                payload=intel.to_dict(),
            )
            self.bus.send(msg)

        # G3-08 Phase 4 Sub-task 4-5: intel_produced + intel_log_size moved.
        # G3-08 Phase 4 Sub-task 4-5：intel_produced 與 intel_log_size 同步遞增。
        _invalidate_h_state_async("agent.scout.intel_produced")

        return intel

    def produce_event_alert(
        self,
        event_type: str,
        severity: str,
        affected_symbols: List[str],
        *,
        event_time_ms: int = 0,
        lead_time_hours: float = 0.0,
        data_quality: DataQualityLevel = DataQualityLevel.INFERENCE,
        description: str = "",
        metadata: Optional[Dict] = None,
    ) -> EventAlert:
        """Create and dispatch an event_alert (§3.2).

        Major event alerts go to Guardian for risk tightening.
        """
        alert = EventAlert(
            event_type=event_type,
            severity=severity,
            affected_symbols=affected_symbols,
            event_time_ms=event_time_ms,
            lead_time_hours=lead_time_hours,
            data_quality=data_quality,
            description=description,
            metadata=metadata or {},
        )

        with self._lock:
            self._alert_log.append(alert)
            self._stats["alerts_produced"] += 1

        # E5-FN-3-FUP-d: append-only audit before bus routing so alerts are
        # audited even when bus is None. Fail-open when _audit_callback is None.
        # E5-FN-3-FUP-d：在匯流排路由前寫審計記錄，確保 bus=None 時 alert 仍被
        # 審計；_audit 在 _audit_callback=None 時為 no-op。
        self._audit("event_alert_produced", alert.to_dict())

        # Route to Guardian via bus
        if self.bus:
            msg = AgentMessage(
                sender=AgentRole.SCOUT,
                receiver=AgentRole.GUARDIAN,
                message_type=MessageType.EVENT_ALERT,
                priority=1 if severity in ("high", "critical") else 3,
                payload=alert.to_dict(),
            )
            self.bus.send(msg)

        # G3-08 Phase 4 Sub-task 4-5: alerts_produced + alert_log_size moved.
        # PA RFC §6.5 names this trigger ``alert_produced`` even though the
        # producer fn is ``produce_event_alert``.
        # G3-08 Phase 4 Sub-task 4-5：alerts_produced 與 alert_log_size 同步
        # 遞增。RFC §6.5 trigger 命名為 ``alert_produced``（雖函式為 produce_event_alert）。
        _invalidate_h_state_async("agent.scout.alert_produced")

        return alert

    def record_scan(self) -> None:
        """Record that a news/market scan cycle completed.
        記錄一次新聞/市場掃描週期已完成。

        G3-08 Phase 4 Sub-task 4-5: emits ``agent.scout.scan_completed``.
        PA RFC §6.5 prompt referenced ``_complete_scan`` as a placeholder
        name; the actual fn is ``record_scan`` (disposition logged in
        commit + E1 report).
        G3-08 Phase 4 Sub-task 4-5：發送 ``agent.scout.scan_completed``。
        RFC §6.5 prompt 用 ``_complete_scan`` 占位；實際函式為 ``record_scan``
        （差異記於 commit 與 E1 報告）。
        """
        with self._lock:
            self._stats["scans_completed"] += 1
        _invalidate_h_state_async("agent.scout.scan_completed")

    def get_recent_intel(self, limit: int = 20) -> List[IntelObject]:
        with self._lock:
            return list(self._intel_log[-limit:])

    def get_recent_alerts(self, limit: int = 10) -> List[EventAlert]:
        with self._lock:
            return list(self._alert_log[-limit:])

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "role": AgentRole.SCOUT.value,
                "state": self.state.value,
                **dict(self._stats),
            }

    # G3-08 Phase 4 Sub-task 4-5: Scout agent_state snapshot accessor.
    # G3-08 Phase 4 Sub-task 4-5：Scout agent 狀態 snapshot 存取器。
    def get_scout_snapshot(self) -> Dict[str, Any]:
        """Thread-safe agent-state snapshot for h_state_cache (PA RFC §2.5, 5 fields).
        Schema parity with Rust ``AgentState.stats: HashMap<String, i64>``: all
        values are int. Mirrors Strategist Sub-task 4-1 caller-side pattern.
        H state cache 用 Scout 狀態 snapshot（PA RFC §2.5，5 欄位），皆 int；
        對齊 Strategist Sub-task 4-1 caller-side pattern。

        Schema (PA RFC §2.5): intel_produced / alerts_produced /
        scans_completed (counters) + intel_log_size / alert_log_size (gauges).
        Phase 4 invariant: every value is ``int`` so Rust
        ``HashMap<String, i64>`` deserialiser accepts without coercion.
        Schema：3 計數器 + 2 gauge；Phase 4 不變式 — 所有值為 int。
        """
        with self._lock:
            return {
                "intel_produced": int(self._stats.get("intel_produced", 0)),
                "alerts_produced": int(self._stats.get("alerts_produced", 0)),
                "scans_completed": int(self._stats.get("scans_completed", 0)),
                "intel_log_size": int(len(self._intel_log)),
                "alert_log_size": int(len(self._alert_log)),
            }
