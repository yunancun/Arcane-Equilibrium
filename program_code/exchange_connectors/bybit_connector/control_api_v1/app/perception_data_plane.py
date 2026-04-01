"""
MODULE_NOTE (中文):
  感知数据平面（Perception Data Plane），为所有 Agent 提供统一的数据注册与查询接口。
  每条数据强制标注认知层级（fact/inference/hypothesis）和新鲜度（FRESH→EXPIRED），
  未标注的推断数据禁止进入决策链。支持数据质量评估、Agent 访问控制、漂移检测。
  属于治理层（T2.11），是原则 8（交易可解释）和原则 10（认知诚实）的数据基础设施。

MODULE_NOTE (English):
  Perception Data Plane providing a unified data registration and query interface for all agents.
  Every data entry must carry a cognitive level tag (fact/inference/hypothesis) and freshness
  tracking (FRESH->EXPIRED); unmarked inferences are blocked from the decision chain.
  Supports data quality assessment, agent-level access control, and drift detection.
  Part of the governance layer (T2.11); data infrastructure for Principle 8 (trade explainability)
  and Principle 10 (cognitive honesty).

T2.11 — Perception Data Plane: Fact/Inference Marking (GAP-M2)
===============================================================
Governance refs: EX-07 §1-§8, DOC-01 §5.10 (Root Principle #8)
Implements:
  - Data source taxonomy with cognitive level (fact/inference/hypothesis)
  - Freshness tracking (FRESH/RECENT/STALE/EXPIRED) per EX-07 TABLE 2
  - Data quality assessment (completeness, consistency, latency, source_reliability)
  - Unmarked inference cannot enter decision chain (EX-07 §1 core principle)
  - Data-quality-driven risk degradation (EX-07 §2.3)
  - Agent data access control (EX-07 §6 TABLE 5)
  - Drift protection (EX-07 §7)
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Callable, Dict, List, Optional, Tuple


# ─────────────────────────────────────────────
# 1. Enums
# ─────────────────────────────────────────────

class CognitiveLevel(str, Enum):
    """EX-07 §1 / DOC-01 §5.10 — three cognitive levels.

    Core principle: exchange API data = fact,
    AI-processed or search-obtained data = inference.
    Unmarked inference MUST NOT enter decision chain.
    """
    FACT = "fact"
    INFERENCE = "inference"
    HYPOTHESIS = "hypothesis"


class Freshness(str, Enum):
    """EX-07 §2.1 TABLE 2 — data freshness levels."""
    FRESH = "fresh"        # < 5 min
    RECENT = "recent"      # 5-30 min
    STALE = "stale"        # 30 min - 2 hours
    EXPIRED = "expired"    # > 2 hours


class DataSourceType(str, Enum):
    """EX-07 §1 TABLE 1 — data source categories."""
    EXCHANGE_REST = "exchange_rest"        # Bybit REST API → fact
    EXCHANGE_WS = "exchange_ws"            # Bybit WebSocket → fact
    SEARCH_PERPLEXITY = "search_perplexity"  # Perplexity → inference
    SEARCH_WEB = "search_web"              # DuckDuckGo etc → inference
    LOCAL_OLLAMA = "local_ollama"          # Ollama sentiment → inference
    EVENT_CALENDAR = "event_calendar"      # Crypto events → fact+inference
    LOCAL_INDICATOR = "local_indicator"    # MA/RSI/BB etc → fact (computed)
    LEARNING_HISTORY = "learning_history"  # Analyst patterns → inference


# Default cognitive level for each source type (EX-07 TABLE 1)
SOURCE_COGNITIVE_DEFAULTS: Dict[DataSourceType, CognitiveLevel] = {
    DataSourceType.EXCHANGE_REST: CognitiveLevel.FACT,
    DataSourceType.EXCHANGE_WS: CognitiveLevel.FACT,
    DataSourceType.SEARCH_PERPLEXITY: CognitiveLevel.INFERENCE,
    DataSourceType.SEARCH_WEB: CognitiveLevel.INFERENCE,
    DataSourceType.LOCAL_OLLAMA: CognitiveLevel.INFERENCE,
    DataSourceType.EVENT_CALENDAR: CognitiveLevel.INFERENCE,  # conservative default
    DataSourceType.LOCAL_INDICATOR: CognitiveLevel.FACT,
    DataSourceType.LEARNING_HISTORY: CognitiveLevel.INFERENCE,
}


class DegradationAction(str, Enum):
    """EX-07 §2.3 — risk degradation actions triggered by data quality."""
    NONE = "none"
    NO_NEW_ENTRY = "no_new_entry"     # STALE price → no new positions
    CAUTIOUS = "cautious"              # EXPIRED price → CAUTIOUS mode
    REDUCED = "reduced"                # WS disconnect > 5min → REDUCED
    DEFENSIVE = "defensive"            # REST 3x failure → DEFENSIVE


# Freshness thresholds in seconds
FRESHNESS_THRESHOLDS = {
    Freshness.FRESH: 300,        # < 5 min
    Freshness.RECENT: 1800,      # < 30 min
    Freshness.STALE: 7200,       # < 2 hours
    # Anything beyond STALE is EXPIRED
}


# ─────────────────────────────────────────────
# 2. Data Quality
# ─────────────────────────────────────────────

@dataclass
class DataQuality:
    """EX-07 §2.2 — multi-dimensional data quality assessment."""
    completeness: float = 1.0    # 0.0-1.0 (e.g. K-line gaps)
    consistency: float = 1.0     # 0.0-1.0 (REST vs WS deviation)
    latency_ms: int = 0          # Exchange-to-system latency
    source_reliability: float = 1.0  # Bybit API(1.0) > third-party(0.7) > news(0.5)

    @property
    def overall_score(self) -> float:
        """Weighted quality score."""
        return (
            self.completeness * 0.3
            + self.consistency * 0.3
            + (1.0 - min(self.latency_ms / 5000.0, 1.0)) * 0.2
            + self.source_reliability * 0.2
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "completeness": self.completeness,
            "consistency": self.consistency,
            "latency_ms": self.latency_ms,
            "source_reliability": self.source_reliability,
            "overall_score": round(self.overall_score, 4),
        }


# ─────────────────────────────────────────────
# 3. Perception Data Object
# ─────────────────────────────────────────────

@dataclass
class PerceptionDataObject:
    """Core data object in the Perception Plane.

    Every piece of data entering the system MUST be wrapped in this
    object with explicit cognitive_level marking.

    EX-07 §1: "任何 inference 不得在未标记的情况下进入决策链"
    """
    data_id: str = field(default_factory=lambda: f"pdo_{uuid.uuid4().hex[:12]}")
    source_type: DataSourceType = DataSourceType.EXCHANGE_REST
    source_detail: str = ""  # URL, API endpoint, etc.
    cognitive_level: CognitiveLevel = CognitiveLevel.FACT
    freshness: Freshness = Freshness.FRESH
    fetched_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    data_quality: DataQuality = field(default_factory=DataQuality)
    content: Any = None  # The actual data payload
    symbols: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Marking provenance
    marked_by: str = ""     # Who set the cognitive level
    marking_reason: str = "" # Why this level was assigned

    def is_decision_eligible(self) -> bool:
        """Check if this data can enter the decision chain.

        EX-07 §1: unmarked data cannot enter.
        EX-07 §2.3: EXPIRED data is discarded.
        """
        if not self.cognitive_level:
            return False
        if self.freshness == Freshness.EXPIRED:
            return False
        return True

    def refresh_freshness(self) -> Freshness:
        """Recalculate freshness based on current time."""
        age_seconds = (int(time.time() * 1000) - self.fetched_at_ms) / 1000.0
        if age_seconds < FRESHNESS_THRESHOLDS[Freshness.FRESH]:
            self.freshness = Freshness.FRESH
        elif age_seconds < FRESHNESS_THRESHOLDS[Freshness.RECENT]:
            self.freshness = Freshness.RECENT
        elif age_seconds < FRESHNESS_THRESHOLDS[Freshness.STALE]:
            self.freshness = Freshness.STALE
        else:
            self.freshness = Freshness.EXPIRED
        return self.freshness

    def to_dict(self) -> Dict[str, Any]:
        return {
            "data_id": self.data_id,
            "source_type": self.source_type.value,
            "source_detail": self.source_detail,
            "cognitive_level": self.cognitive_level.value,
            "freshness": self.freshness.value,
            "fetched_at_ms": self.fetched_at_ms,
            "data_quality": self.data_quality.to_dict(),
            "symbols": list(self.symbols),
            "marked_by": self.marked_by,
            "marking_reason": self.marking_reason,
            "is_decision_eligible": self.is_decision_eligible(),
        }


# ─────────────────────────────────────────────
# 4. Agent Data Access Matrix (EX-07 §6 TABLE 5)
# ─────────────────────────────────────────────

class AccessLevel(str, Enum):
    NONE = "none"
    READ = "read"
    READ_WRITE = "read_write"


# Data categories mapped to agent access (EX-07 TABLE 5)
# Key: (agent_role, data_category) → AccessLevel
AGENT_DATA_ACCESS: Dict[Tuple[str, str], AccessLevel] = {
    # Scout: no account/position access (prevent position bias in intelligence)
    ("scout", "exchange_price"): AccessLevel.READ,
    ("scout", "exchange_account"): AccessLevel.NONE,
    ("scout", "search_results"): AccessLevel.READ_WRITE,
    ("scout", "trade_intent"): AccessLevel.NONE,
    ("scout", "risk_params_p2"): AccessLevel.NONE,
    ("scout", "risk_params_p0p1"): AccessLevel.NONE,
    ("scout", "learning_records"): AccessLevel.NONE,
    ("scout", "orders_fills"): AccessLevel.NONE,

    # Strategist
    ("strategist", "exchange_price"): AccessLevel.READ,
    ("strategist", "exchange_account"): AccessLevel.READ,
    ("strategist", "search_results"): AccessLevel.READ,
    ("strategist", "trade_intent"): AccessLevel.READ_WRITE,
    ("strategist", "risk_params_p2"): AccessLevel.READ,
    ("strategist", "risk_params_p0p1"): AccessLevel.READ,
    ("strategist", "learning_records"): AccessLevel.READ,
    ("strategist", "orders_fills"): AccessLevel.READ,

    # Guardian
    ("guardian", "exchange_price"): AccessLevel.READ,
    ("guardian", "exchange_account"): AccessLevel.READ,
    ("guardian", "search_results"): AccessLevel.READ,
    ("guardian", "trade_intent"): AccessLevel.READ,
    ("guardian", "risk_params_p2"): AccessLevel.READ_WRITE,
    ("guardian", "risk_params_p0p1"): AccessLevel.READ,
    ("guardian", "learning_records"): AccessLevel.READ,
    ("guardian", "orders_fills"): AccessLevel.READ,

    # Analyst
    ("analyst", "exchange_price"): AccessLevel.READ,
    ("analyst", "exchange_account"): AccessLevel.READ,
    ("analyst", "search_results"): AccessLevel.READ,
    ("analyst", "trade_intent"): AccessLevel.READ,
    ("analyst", "risk_params_p2"): AccessLevel.READ,
    ("analyst", "risk_params_p0p1"): AccessLevel.READ,
    ("analyst", "learning_records"): AccessLevel.READ_WRITE,
    ("analyst", "orders_fills"): AccessLevel.READ,

    # Executor: no search results access (only executes, doesn't judge)
    ("executor", "exchange_price"): AccessLevel.READ,
    ("executor", "exchange_account"): AccessLevel.READ,
    ("executor", "search_results"): AccessLevel.NONE,
    ("executor", "trade_intent"): AccessLevel.READ,
    ("executor", "risk_params_p2"): AccessLevel.READ,
    ("executor", "risk_params_p0p1"): AccessLevel.READ,
    ("executor", "learning_records"): AccessLevel.NONE,
    ("executor", "orders_fills"): AccessLevel.READ_WRITE,
}

# Data categories list
DATA_CATEGORIES = [
    "exchange_price", "exchange_account", "search_results",
    "trade_intent", "risk_params_p2", "risk_params_p0p1",
    "learning_records", "orders_fills",
]


def check_data_access(
    agent_role: str, data_category: str, write: bool = False
) -> bool:
    """EX-07 §6 — check if an agent can access a data category.

    Args:
        agent_role: scout/strategist/guardian/analyst/executor
        data_category: one of DATA_CATEGORIES
        write: True if write access needed, False for read-only
    """
    key = (agent_role.lower(), data_category.lower())
    level = AGENT_DATA_ACCESS.get(key, AccessLevel.NONE)
    if level == AccessLevel.NONE:
        return False
    if write and level == AccessLevel.READ:
        return False
    return True


# ─────────────────────────────────────────────
# 5. Perception Plane Engine
# ─────────────────────────────────────────────

@dataclass
class DriftWarning:
    """EX-07 §7 — drift protection warning."""
    warning_id: str = field(default_factory=lambda: f"drift_{uuid.uuid4().hex[:8]}")
    drift_type: str = ""
    description: str = ""
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    severity: str = "warning"  # warning / critical

    def to_dict(self) -> Dict[str, Any]:
        return {
            "warning_id": self.warning_id,
            "drift_type": self.drift_type,
            "description": self.description,
            "timestamp_ms": self.timestamp_ms,
            "severity": self.severity,
        }


class PerceptionPlane:
    """EX-07 — central data governance engine.

    Core responsibility: ensure all data flowing into the system has
    explicit source, freshness, cognitive level marking, and quality assessment.

    Exchange data = FACT.
    AI-processed / search data = INFERENCE.
    Unmarked data CANNOT enter decision chain.
    """

    def __init__(self, *, audit_callback: Optional[Callable] = None):
        self._lock = threading.Lock()
        self._data_store: Dict[str, PerceptionDataObject] = {}
        self._drift_warnings: List[DriftWarning] = []
        self._audit_callback = audit_callback
        self._stats = {
            "objects_registered": 0,
            "objects_rejected": 0,
            "facts": 0,
            "inferences": 0,
            "hypotheses": 0,
            "drift_warnings": 0,
            "access_denied": 0,
        }

    def register_data(
        self,
        source_type: DataSourceType,
        content: Any,
        *,
        source_detail: str = "",
        cognitive_level: Optional[CognitiveLevel] = None,
        symbols: Optional[List[str]] = None,
        data_quality: Optional[DataQuality] = None,
        marked_by: str = "",
        marking_reason: str = "",
        metadata: Optional[Dict] = None,
    ) -> Optional[PerceptionDataObject]:
        """Register data into the perception plane.

        If cognitive_level is not provided, uses the source type default.
        Checks for drift: if source is exchange but marked as hypothesis,
        that's suspicious. If source is search but marked as fact, that's drift.
        """
        # Apply default cognitive level from source taxonomy
        if cognitive_level is None:
            cognitive_level = SOURCE_COGNITIVE_DEFAULTS.get(
                source_type, CognitiveLevel.INFERENCE
            )

        # Drift check: search data marked as fact
        if (
            source_type
            in (
                DataSourceType.SEARCH_PERPLEXITY,
                DataSourceType.SEARCH_WEB,
                DataSourceType.LOCAL_OLLAMA,
            )
            and cognitive_level == CognitiveLevel.FACT
        ):
            self._record_drift(
                "inference_as_fact",
                f"Source {source_type.value} data marked as FACT — "
                f"search/AI data should be INFERENCE (EX-07 §7)",
                severity="critical",
            )
            # Override to INFERENCE (enforce the rule)
            cognitive_level = CognitiveLevel.INFERENCE

        pdo = PerceptionDataObject(
            source_type=source_type,
            source_detail=source_detail,
            cognitive_level=cognitive_level,
            data_quality=data_quality or DataQuality(),
            content=content,
            symbols=symbols or [],
            marked_by=marked_by,
            marking_reason=marking_reason,
            metadata=metadata or {},
        )
        pdo.refresh_freshness()

        with self._lock:
            self._data_store[pdo.data_id] = pdo
            self._stats["objects_registered"] += 1
            if cognitive_level == CognitiveLevel.FACT:
                self._stats["facts"] += 1
            elif cognitive_level == CognitiveLevel.INFERENCE:
                self._stats["inferences"] += 1
            else:
                self._stats["hypotheses"] += 1

        if self._audit_callback:
            try:
                self._audit_callback("data_registered", pdo.to_dict())
            except Exception:
                pass

        return pdo

    def get_data(
        self, data_id: str, *, agent_role: Optional[str] = None
    ) -> Optional[PerceptionDataObject]:
        """Retrieve data, optionally checking agent access rights."""
        with self._lock:
            pdo = self._data_store.get(data_id)

        if pdo is None:
            return None

        # Agent access check (EX-07 §6)
        if agent_role:
            category = self._source_to_category(pdo.source_type)
            if not check_data_access(agent_role, category, write=False):
                with self._lock:
                    self._stats["access_denied"] += 1
                return None

        return pdo

    def get_decision_eligible_data(
        self,
        *,
        symbols: Optional[List[str]] = None,
        source_type: Optional[DataSourceType] = None,
        min_quality: float = 0.0,
    ) -> List[PerceptionDataObject]:
        """Get all data eligible for the decision chain.

        EX-07 §1: only marked + non-expired data.
        """
        with self._lock:
            candidates = list(self._data_store.values())

        result = []
        for pdo in candidates:
            pdo.refresh_freshness()
            if not pdo.is_decision_eligible():
                continue
            if symbols and not any(s in pdo.symbols for s in symbols):
                continue
            if source_type and pdo.source_type != source_type:
                continue
            if pdo.data_quality.overall_score < min_quality:
                continue
            result.append(pdo)

        return result

    def assess_degradation(
        self,
        data_category: str = "price",
        *,
        ws_disconnect_seconds: int = 0,
        rest_consecutive_failures: int = 0,
    ) -> DegradationAction:
        """EX-07 §2.3 — determine risk degradation from data quality.

        Returns the appropriate degradation action.
        """
        # REST API failures
        if rest_consecutive_failures >= 3:
            return DegradationAction.DEFENSIVE

        # WebSocket disconnection
        if ws_disconnect_seconds > 300:  # > 5 min
            return DegradationAction.REDUCED
        if ws_disconnect_seconds > 30:   # > 30 sec → rely on REST polling
            return DegradationAction.NO_NEW_ENTRY

        # Check freshness of price data
        if data_category == "price":
            with self._lock:
                price_data = [
                    pdo
                    for pdo in self._data_store.values()
                    if pdo.source_type
                    in (DataSourceType.EXCHANGE_REST, DataSourceType.EXCHANGE_WS)
                    and "price" in pdo.metadata.get("data_type", "price")
                ]

            if price_data:
                latest = max(price_data, key=lambda p: p.fetched_at_ms)
                latest.refresh_freshness()
                if latest.freshness == Freshness.EXPIRED:
                    return DegradationAction.CAUTIOUS
                if latest.freshness == Freshness.STALE:
                    return DegradationAction.NO_NEW_ENTRY

        return DegradationAction.NONE

    def validate_for_decision(
        self, data_id: str
    ) -> Tuple[bool, str]:
        """Validate that data can enter the decision chain.

        Returns (eligible, reason).
        """
        with self._lock:
            pdo = self._data_store.get(data_id)

        if pdo is None:
            return (False, "Data not found in perception plane")

        pdo.refresh_freshness()

        if not pdo.cognitive_level:
            with self._lock:
                self._stats["objects_rejected"] += 1
            return (False, "No cognitive level marking — cannot enter decision chain (EX-07 §1)")

        if pdo.freshness == Freshness.EXPIRED:
            with self._lock:
                self._stats["objects_rejected"] += 1
            return (False, f"Data expired (age > 2h) — discarded per EX-07 §2.1")

        if pdo.data_quality.overall_score < 0.3:
            return (False, "Data quality too low for decision use")

        return (True, f"Eligible: {pdo.cognitive_level.value}, freshness={pdo.freshness.value}")

    # ── Drift Protection (EX-07 §7) ──

    def _record_drift(
        self, drift_type: str, description: str, severity: str = "warning"
    ) -> DriftWarning:
        warning = DriftWarning(
            drift_type=drift_type,
            description=description,
            severity=severity,
        )
        with self._lock:
            self._drift_warnings.append(warning)
            self._stats["drift_warnings"] += 1
        return warning

    def check_drift(self) -> List[DriftWarning]:
        """Return accumulated drift warnings."""
        with self._lock:
            return list(self._drift_warnings)

    # ── Helpers ──

    @staticmethod
    def _source_to_category(source_type: DataSourceType) -> str:
        """Map source type to data access category for EX-07 §6."""
        mapping = {
            DataSourceType.EXCHANGE_REST: "exchange_account",
            DataSourceType.EXCHANGE_WS: "exchange_price",
            DataSourceType.SEARCH_PERPLEXITY: "search_results",
            DataSourceType.SEARCH_WEB: "search_results",
            DataSourceType.LOCAL_OLLAMA: "search_results",
            DataSourceType.EVENT_CALENDAR: "search_results",
            DataSourceType.LOCAL_INDICATOR: "exchange_price",
            DataSourceType.LEARNING_HISTORY: "learning_records",
        }
        return mapping.get(source_type, "exchange_price")

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "total_objects": len(self._data_store),
                **dict(self._stats),
            }


# ─────────────────────────────────────────────
# 6. Helper: Freshness Calculator
# ─────────────────────────────────────────────

def calculate_freshness(fetched_at_ms: int) -> Freshness:
    """Calculate freshness level from fetch timestamp (EX-07 TABLE 2)."""
    age_seconds = (int(time.time() * 1000) - fetched_at_ms) / 1000.0
    if age_seconds < FRESHNESS_THRESHOLDS[Freshness.FRESH]:
        return Freshness.FRESH
    if age_seconds < FRESHNESS_THRESHOLDS[Freshness.RECENT]:
        return Freshness.RECENT
    if age_seconds < FRESHNESS_THRESHOLDS[Freshness.STALE]:
        return Freshness.STALE
    return Freshness.EXPIRED
