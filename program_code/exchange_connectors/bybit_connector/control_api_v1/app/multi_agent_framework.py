"""
MODULE_NOTE (中文):
  5-Agent 多智能体框架核心模块（Scout / Strategist / Guardian / Analyst / Executor + Conductor 编排）。
  实现结构化 Agent 间消息协议（MessageBus 发布/订阅）、冲突仲裁（Guardian 永远优先于 Strategist）、
  Agent 生命周期管理（INITIALIZING→RUNNING→DEGRADED→PAUSED→STOPPED）以及数据质量标记（fact/inference/hypothesis）。
  属于治理层（Governance T2.07），是原则 15（多 Agent 协作）的底层基础设施。

MODULE_NOTE (English):
  Core 5-agent multi-agent framework (Scout / Strategist / Guardian / Analyst / Executor + Conductor orchestration).
  Implements structured inter-agent message protocol (MessageBus pub/sub), conflict arbitration (Guardian always
  wins over Strategist), agent lifecycle management (INITIALIZING->RUNNING->DEGRADED->PAUSED->STOPPED), and
  data quality marking (fact/inference/hypothesis). Part of the governance layer (T2.07); foundational
  infrastructure for Principle 15 (multi-agent collaboration).

T2.07 — Scout Agent + Conductor Framework (GAP-H2)
===================================================
Governance refs: EX-06 §2-§10, DOC-04 §G Multi-Agent
Implements:
  - Structured inter-agent message protocol (EX-06 §8)
  - Scout Agent: intel_object + event_alert output (EX-06 §3)
  - Conductor/Orchestrator: task distribution, conflict arbitration,
    resource allocation, agent lifecycle (EX-06 §2)
  - 5-role agent architecture: Scout, Strategist, Guardian, Analyst, Executor
  - Conflict resolution: Guardian always wins over Strategist (EX-06 §9)
  - Resource-constrained mode: single model multi-role (EX-06 §10)
  - Data quality marking: fact / inference / hypothesis (EX-06 §3.4)
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 1. Enums
# ─────────────────────────────────────────────

class AgentRole(str, Enum):
    """EX-06 §1 — five agent roles + conductor."""
    SCOUT = "scout"
    STRATEGIST = "strategist"
    GUARDIAN = "guardian"
    ANALYST = "analyst"
    EXECUTOR = "executor"
    CONDUCTOR = "conductor"  # OpenClaw orchestrator, not a 6th agent


class MessageType(str, Enum):
    """EX-06 §8.2 — structured inter-agent message types."""
    INTEL_OBJECT = "intel_object"         # Scout → Strategist
    EVENT_ALERT = "event_alert"           # Scout → Guardian
    TRADE_INTENT = "trade_intent"         # Strategist → Guardian
    RISK_VERDICT = "risk_verdict"         # Guardian → Strategist
    APPROVED_INTENT = "approved_intent"   # Strategist → Executor
    EXECUTION_REPORT = "execution_report" # Executor → Analyst
    ROUND_TRIP_COMPLETE = "round_trip_complete"  # Executor → Analyst
    PATTERN_INSIGHT = "pattern_insight"   # Analyst → Strategist
    RISK_PATTERN = "risk_pattern"         # Analyst → Guardian
    STRATEGY_PROPOSAL = "strategy_proposal"  # Analyst → OpenClaw
    SYSTEM_DIRECTIVE = "system_directive" # OpenClaw → All


class DataQualityLevel(str, Enum):
    """EX-06 §3.4 — cognitive level marking (aligns DOC-01 §5.10)."""
    FACT = "fact"              # Exchange API confirmed data
    INFERENCE = "inference"    # Derived from multiple facts
    HYPOTHESIS = "hypothesis"  # Limited-information guess


class SentimentScore(str, Enum):
    """EX-06 §3.1 — sentiment classification."""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class RiskVerdictResult(str, Enum):
    """EX-06 §8.2 — Guardian review outcomes."""
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"


class AgentState(str, Enum):
    """Agent lifecycle states (EX-06 §2.3)."""
    INITIALIZING = "initializing"
    RUNNING = "running"
    DEGRADED = "degraded"
    PAUSED = "paused"
    STOPPED = "stopped"


class ResourcePriority(IntEnum):
    """EX-06 §9 TABLE 4 — AI compute priority."""
    GUARDIAN = 0          # Highest
    SCOUT_URGENT = 1
    STRATEGIST = 2
    ANALYST = 3
    SCOUT_ROUTINE = 4    # Lowest


# ─────────────────────────────────────────────
# 2. Structured Message Objects
# ─────────────────────────────────────────────

@dataclass
class AgentMessage:
    """EX-06 §8.1 — base structured communication object.

    All inter-agent communication must use structured objects,
    not free text. Every message has sender/receiver/timestamp/type/priority.
    """
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    sender: AgentRole = AgentRole.CONDUCTOR
    receiver: AgentRole = AgentRole.CONDUCTOR
    message_type: MessageType = MessageType.SYSTEM_DIRECTIVE
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    priority: int = 5  # 0=highest, 9=lowest
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "sender": self.sender.value,
            "receiver": self.receiver.value,
            "message_type": self.message_type.value,
            "timestamp_ms": self.timestamp_ms,
            "priority": self.priority,
            "payload": self.payload,
        }


@dataclass
class IntelObject:
    """EX-06 §3.2 — Scout's structured intelligence output."""
    intel_id: str = field(default_factory=lambda: f"intel_{uuid.uuid4().hex[:12]}")
    source: str = ""
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    freshness_seconds: int = 0
    data_quality: DataQualityLevel = DataQualityLevel.FACT
    sentiment: SentimentScore = SentimentScore.NEUTRAL
    relevance_score: float = 0.0  # 0.0 to 1.0
    content: str = ""
    symbols: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intel_id": self.intel_id,
            "source": self.source,
            "timestamp_ms": self.timestamp_ms,
            "freshness_seconds": self.freshness_seconds,
            "data_quality": self.data_quality.value,
            "sentiment": self.sentiment.value,
            "relevance_score": self.relevance_score,
            "content": self.content,
            "symbols": list(self.symbols),
            "metadata": dict(self.metadata),
        }


@dataclass
class EventAlert:
    """EX-06 §3.2 — Scout's major event alert."""
    alert_id: str = field(default_factory=lambda: f"alert_{uuid.uuid4().hex[:12]}")
    event_type: str = ""  # e.g. "fomc", "token_unlock", "protocol_upgrade", "cpi"
    severity: str = "medium"  # low / medium / high / critical
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    event_time_ms: int = 0  # When the event will occur
    lead_time_hours: float = 0.0
    affected_symbols: List[str] = field(default_factory=list)
    data_quality: DataQualityLevel = DataQualityLevel.INFERENCE
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "event_type": self.event_type,
            "severity": self.severity,
            "timestamp_ms": self.timestamp_ms,
            "event_time_ms": self.event_time_ms,
            "lead_time_hours": self.lead_time_hours,
            "affected_symbols": list(self.affected_symbols),
            "data_quality": self.data_quality.value,
            "description": self.description,
            "metadata": dict(self.metadata),
        }


@dataclass
class TradeIntent:
    """EX-06 §4.2 — Strategist's structured trade intent."""
    intent_id: str = field(default_factory=lambda: f"intent_{uuid.uuid4().hex[:12]}")
    symbol: str = ""
    strategy: str = ""
    direction: str = ""  # "long" / "short"
    size: float = 0.0
    params: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0  # 0.0 to 1.0
    thesis: str = ""
    invalidation_condition: str = ""
    data_quality: DataQualityLevel = DataQualityLevel.INFERENCE
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "symbol": self.symbol,
            "strategy": self.strategy,
            "direction": self.direction,
            "size": self.size,
            "params": dict(self.params),
            "confidence": self.confidence,
            "thesis": self.thesis,
            "invalidation_condition": self.invalidation_condition,
            "data_quality": self.data_quality.value,
            "metadata": dict(self.metadata),
        }


@dataclass
class RiskModification:
    """P2 Guardian modification output.

    The field names intentionally describe bounded risk adjustments only.
    They do not carry symbol or direction authority.
    """
    field: str
    action: str
    modified_value: Any
    original_value: Any = None
    unit: str = ""
    reason_code: str = ""
    reason: str = ""
    evidence_refs: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "action": self.action,
            "original_value": self.original_value,
            "modified_value": self.modified_value,
            "unit": self.unit,
            "reason_code": self.reason_code,
            "reason": self.reason,
            "evidence_refs": list(self.evidence_refs),
            "metadata": dict(self.metadata),
        }


@dataclass
class RiskVerdict:
    """EX-06 §5/§8.2 — Guardian's review conclusion."""
    verdict_id: str = field(default_factory=lambda: f"verdict_{uuid.uuid4().hex[:12]}")
    intent_id: str = ""  # references TradeIntent
    result: RiskVerdictResult = RiskVerdictResult.REJECTED
    reason: str = ""
    modified_params: Dict[str, Any] = field(default_factory=dict)
    p2_modifications: List[Dict[str, Any]] = field(default_factory=list)
    risk_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict_id": self.verdict_id,
            "intent_id": self.intent_id,
            "result": self.result.value,
            "reason": self.reason,
            "modified_params": dict(self.modified_params),
            "p2_modifications": [dict(item) for item in self.p2_modifications],
            "risk_score": self.risk_score,
            "metadata": dict(self.metadata),
        }


# ─────────────────────────────────────────────
# 3. Message Bus (Inter-Agent Communication)
# ─────────────────────────────────────────────

# Valid communication routes (EX-06 §8.2 TABLE 3)
VALID_ROUTES: Dict[Tuple[AgentRole, AgentRole], List[MessageType]] = {
    (AgentRole.SCOUT, AgentRole.STRATEGIST): [MessageType.INTEL_OBJECT],
    (AgentRole.SCOUT, AgentRole.GUARDIAN): [MessageType.EVENT_ALERT],
    (AgentRole.STRATEGIST, AgentRole.GUARDIAN): [MessageType.TRADE_INTENT],
    (AgentRole.GUARDIAN, AgentRole.STRATEGIST): [MessageType.RISK_VERDICT],
    (AgentRole.STRATEGIST, AgentRole.EXECUTOR): [MessageType.APPROVED_INTENT],
    (AgentRole.EXECUTOR, AgentRole.ANALYST): [
        MessageType.EXECUTION_REPORT,
        MessageType.ROUND_TRIP_COMPLETE,
    ],
    (AgentRole.ANALYST, AgentRole.STRATEGIST): [MessageType.PATTERN_INSIGHT],
    (AgentRole.ANALYST, AgentRole.GUARDIAN): [MessageType.RISK_PATTERN],
    (AgentRole.ANALYST, AgentRole.CONDUCTOR): [MessageType.STRATEGY_PROPOSAL],
    # Conductor can broadcast to all
    (AgentRole.CONDUCTOR, AgentRole.SCOUT): [MessageType.SYSTEM_DIRECTIVE],
    (AgentRole.CONDUCTOR, AgentRole.STRATEGIST): [MessageType.SYSTEM_DIRECTIVE],
    (AgentRole.CONDUCTOR, AgentRole.GUARDIAN): [MessageType.SYSTEM_DIRECTIVE],
    (AgentRole.CONDUCTOR, AgentRole.ANALYST): [MessageType.SYSTEM_DIRECTIVE],
    (AgentRole.CONDUCTOR, AgentRole.EXECUTOR): [MessageType.SYSTEM_DIRECTIVE],
}


class MessageBus:
    """Thread-safe inter-agent message bus with audit trail.

    EX-06 §8.1: all communication must be through structured objects,
    persisted for audit.
    """

    def __init__(
        self,
        *,
        audit_callback: Optional[Callable] = None,
        message_sink: Optional[Callable[[AgentMessage], None]] = None,
    ):
        self._lock = threading.Lock()
        self._messages: List[AgentMessage] = []
        self._subscribers: Dict[AgentRole, List[Callable]] = {}
        self._audit_callback = audit_callback
        self._message_sink = message_sink

    def validate_route(
        self, sender: AgentRole, receiver: AgentRole, msg_type: MessageType
    ) -> bool:
        """Check if this communication route is valid per EX-06 TABLE 3."""
        route = (sender, receiver)
        allowed = VALID_ROUTES.get(route, [])
        return msg_type in allowed

    def send(self, message: AgentMessage) -> bool:
        """Send a structured message. Returns True if delivered."""
        if not self.validate_route(
            message.sender, message.receiver, message.message_type
        ):
            return False

        with self._lock:
            self._messages.append(message)
            if self._audit_callback:
                try:
                    self._audit_callback(
                        "message_sent", message.to_dict()
                    )
                except Exception:
                    pass

            # Copy subscriber list inside lock; invoke outside to avoid
            # holding the lock during potentially slow callbacks (A8 fix).
            # 在锁内复制订阅者列表；在锁外调用，避免慢回调阻塞整个 bus。
            subscribers = list(self._subscribers.get(message.receiver, []))
            message_sink = self._message_sink

        # Durable sink is advisory observability only: DB failures must not
        # block delivery to subscribers.
        # 持久化 sink 僅作觀測；DB 失敗不得阻塞 subscriber delivery。
        if message_sink:
            try:
                message_sink(message)
            except Exception as e:
                logger.warning("MessageBus message_sink error: %s", e)

        # Notify subscribers outside the lock — each callback wrapped in
        # try/except so one failing subscriber cannot block others.
        # 在锁外通知订阅者 — 每个回调独立 try/except，单个失败不影响其余。
        for cb in subscribers:
            try:
                cb(message)
            except Exception as e:
                logger.warning("MessageBus subscriber error: %s", e)

        return True

    def subscribe(self, role: AgentRole, callback: Callable) -> None:
        """Register a handler for messages delivered to *role*."""
        with self._lock:
            self._subscribers.setdefault(role, []).append(callback)

    def set_message_sink(self, callback: Optional[Callable[[AgentMessage], None]]) -> None:
        """Install or clear an advisory durable sink for delivered messages."""
        with self._lock:
            self._message_sink = callback

    def get_messages(
        self,
        *,
        receiver: Optional[AgentRole] = None,
        msg_type: Optional[MessageType] = None,
        since_ms: int = 0,
    ) -> List[AgentMessage]:
        """Query message history."""
        with self._lock:
            result = list(self._messages)
        if receiver:
            result = [m for m in result if m.receiver == receiver]
        if msg_type:
            result = [m for m in result if m.message_type == msg_type]
        if since_ms:
            result = [m for m in result if m.timestamp_ms >= since_ms]
        return result

    @property
    def total_messages(self) -> int:
        with self._lock:
            return len(self._messages)


# ─────────────────────────────────────────────
# 4. Scout Agent (EX-06 §3) — moved to scout_agent.py for §九 LOC budget
# ─────────────────────────────────────────────
# G3-08-FUP-MAF-SPLIT: ScoutConfig + ScoutAgent moved to dedicated scout_agent.py
# (per PA RFC). Re-export so existing call-sites (test files, scout_routes.py,
# strategy_wiring.py legacy callers, ai_service.py docstring refs) continue to
# work via ``from .multi_agent_framework import ScoutAgent, ScoutConfig`` path.
# G3-08-FUP-MAF-SPLIT：ScoutConfig + ScoutAgent 遷至 scout_agent.py（per PA RFC）。
# 透過 re-export 維持既有呼叫點（test、scout_routes、strategy_wiring 舊 caller、
# ai_service docstring）的 ``from .multi_agent_framework import ScoutAgent`` 路徑可用。
#
# 為避免「scout_agent → maf → scout_agent」循環 import（scout_agent 在 module
# load 期需 from .multi_agent_framework import 諸 enum/dataclass），這裡用 PEP 562
# module-level ``__getattr__`` 延遲解析：當且僅當外部首次 attribute lookup
# (``maf.ScoutAgent`` / ``from maf import ScoutAgent``) 時才 import scout_agent，
# 此時 maf module body 已執行完，所有 enum/dataclass 全部 ready。
# To avoid the ``scout_agent -> maf -> scout_agent`` circular import (scout_agent
# needs maf's enums/dataclasses at module load time), we use PEP 562 module-level
# ``__getattr__`` for lazy resolution: scout_agent is imported only on first
# attribute lookup, by which point maf's module body has fully executed.
def __getattr__(name: str):  # noqa: D401 — PEP 562 lazy re-export
    if name in ("ScoutAgent", "ScoutConfig"):
        from . import scout_agent as _scout_module  # local import breaks cycle
        value = getattr(_scout_module, name)
        globals()[name] = value  # cache so subsequent lookups skip __getattr__
        return value
    if name in ("AgentInfo", "Conductor"):
        from . import multi_agent_conductor as _conductor_module
        value = getattr(_conductor_module, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ─────────────────────────────────────────────
# 5. Conflict Arbitration (EX-06 §9)
# ─────────────────────────────────────────────

# Arbitration result
@dataclass
class ArbitrationResult:
    winner: AgentRole
    decision: str  # "guardian_veto", "guardian_tighten", "strategist_autonomy", etc.
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "winner": self.winner.value,
            "decision": self.decision,
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }


def arbitrate_conflict(
    scenario: str,
    strategist_action: Optional[Dict] = None,
    guardian_action: Optional[Dict] = None,
) -> ArbitrationResult:
    """EX-06 §9 TABLE 4 — conflict resolution.

    Core principle: Guardian's risk conclusion ALWAYS overrides
    Strategist's trade intent. Safety > Profit.

    Supported scenarios:
    - "open_vs_tighten": Strategist wants open, Guardian says tighten
    - "scout_bearish_strategist_bullish": Scout bearish, Strategist bullish
    - "analyst_vs_strategist": Analyst suggests, Strategist disagrees
    - "executor_anomaly": Executor reports anomaly, Guardian wants circuit-breaker
    - "resource_contention": Multiple agents request AI compute
    """
    if scenario == "open_vs_tighten":
        return ArbitrationResult(
            winner=AgentRole.GUARDIAN,
            decision="guardian_veto",
            reason="Guardian wins — risk control priority over profit (EX-06 §9)",
        )

    if scenario == "scout_bearish_strategist_bullish":
        return ArbitrationResult(
            winner=AgentRole.GUARDIAN,
            decision="guardian_tighten",
            reason="Guardian intervenes — at minimum tighten risk params (EX-06 §9)",
        )

    if scenario == "analyst_vs_strategist":
        return ArbitrationResult(
            winner=AgentRole.STRATEGIST,
            decision="strategist_autonomy",
            reason="Analyst suggestion recorded but not forced — Strategist has strategy autonomy (EX-06 §9)",
        )

    if scenario == "executor_anomaly":
        return ArbitrationResult(
            winner=AgentRole.GUARDIAN,
            decision="guardian_circuit_breaker",
            reason="Guardian wins — can trigger CIRCUIT_BREAKER on execution anomaly (EX-06 §9)",
        )

    if scenario == "resource_contention":
        # Priority: Guardian > Scout(urgent) > Strategist > Analyst > Scout(routine)
        return ArbitrationResult(
            winner=AgentRole.CONDUCTOR,
            decision="conductor_priority_allocation",
            reason="Conductor allocates by priority: Guardian > Scout(urgent) > Strategist > Analyst > Scout(routine) (EX-06 §9)",
        )

    return ArbitrationResult(
        winner=AgentRole.CONDUCTOR,
        decision="conductor_default",
        reason=f"Unknown scenario '{scenario}' — Conductor makes default call",
    )


# ─────────────────────────────────────────────
# 6. Agent Registry + Conductor
# ─────────────────────────────────────────────
# AgentInfo and Conductor live in multi_agent_conductor.py and are lazily
# re-exported by __getattr__ above to preserve legacy import paths.
