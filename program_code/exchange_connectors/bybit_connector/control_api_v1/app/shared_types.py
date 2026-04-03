"""
shared_types.py — Python/Rust IPC 共享類型定義
Shared type definitions mirroring the Rust openclaw_types crate 1:1.

MODULE_NOTE:
    [中文] 定義 Python 與 Rust 之間 IPC 通信的共享類型。遷移期間，原始定義與此模組共存；
           遷移完成後，所有代碼統一從此模組導入。
    [English] Central Python definitions of types shared between Python and Rust via IPC.
              During migration both original definitions and shared_types co-exist.
              After migration, all code imports from shared_types exclusively.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum, IntEnum
from typing import Any

__all__ = [
    "RiskLevel", "RiskInitiator", "OrderState", "OrderInitiator",
    "H0GateConfig", "H0GateHealthSnapshot", "H0GateRiskSnapshot",
    "H0GateCheckResult", "StopConfig", "PriceEvent",
]


# ---------------------------------------------------------------------------
# Enums / 枚舉
# ---------------------------------------------------------------------------

class RiskLevel(IntEnum):
    """風險等級 (0=正常 → 5=人工審查) / Risk level from normal to manual review."""
    NORMAL = 0
    CAUTIOUS = 1
    REDUCED = 2
    DEFENSIVE = 3
    CIRCUIT_BREAKER = 4
    MANUAL_REVIEW = 5


class RiskInitiator(str, Enum):
    """風險狀態變更的發起者 / Initiator of a risk-level change."""
    RISK_GOVERNOR = "RiskGovernor"
    OPERATOR = "Operator"
    INCIDENT_POLICY = "IncidentPolicy"
    HEALTH_MONITOR = "HealthMonitor"
    EXPIRY_GUARDIAN = "ExpiryGuardian"


class OrderState(str, Enum):
    """訂單生命週期狀態 / Order lifecycle state."""
    CREATED = "CREATED"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    SUBMITTED = "SUBMITTED"
    WORKING = "WORKING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    RECONCILING = "RECONCILING"
    COMPLETED = "COMPLETED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"


class OrderInitiator(str, Enum):
    """訂單發起方 / Entity that initiated the order."""
    OPERATOR = "Operator"
    AI_AGENT = "AIAgent"
    SYSTEM = "System"
    EXECUTION_VENUE = "ExecutionVenue"
    AUTHORIZATION_SM = "AuthorizationSM"
    RECONCILIATION_ENGINE = "ReconciliationEngine"
    RISK_GOVERNOR = "RiskGovernor"


# ---------------------------------------------------------------------------
# Dataclasses / 資料類
# ---------------------------------------------------------------------------

@dataclass
class H0GateConfig:
    """H0 閘門配置 / H0 gate configuration thresholds."""
    max_data_age_ms: int = 1000
    max_cpu_pct: float = 90.0
    min_memory_mb: int = 1024
    max_db_latency_ms: float = 100.0
    max_network_loss_pct: float = 5.0
    allowed_categories: frozenset = field(default_factory=lambda: frozenset({"linear", "inverse", "spot"}))
    max_open_positions: int = 10
    max_total_exposure_pct: float = 90.0
    health_snapshot_max_age_ms: int = 30_000
    shadow_mode: bool = False

    def to_json(self) -> str:
        """序列化為 JSON / Serialize to JSON string."""
        d = asdict(self)
        d["allowed_categories"] = sorted(d["allowed_categories"])
        return json.dumps(d)

    @classmethod
    def from_json(cls, raw: str) -> H0GateConfig:
        """從 JSON 反序列化 / Deserialize from JSON string."""
        d = json.loads(raw)
        d["allowed_categories"] = frozenset(d["allowed_categories"])
        return cls(**d)


@dataclass
class H0GateHealthSnapshot:
    """H0 系統健康快照 / H0 system health snapshot."""
    cpu_pct: float = 0.0
    memory_available_mb: int = 9999
    db_latency_ms: float = 0.0
    network_loss_pct: float = 0.0
    snapshot_ts_ms: int = 0

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> H0GateHealthSnapshot:
        return cls(**json.loads(raw))


@dataclass
class H0GateRiskSnapshot:
    """H0 風控快照 / H0 risk snapshot."""
    open_position_count: int = 0
    total_exposure_pct: float = 0.0
    cooldown_until_ts_ms: int = 0
    kill_switch_active: bool = False
    snapshot_ts_ms: int = 0

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> H0GateRiskSnapshot:
        return cls(**json.loads(raw))


@dataclass
class H0GateCheckResult:
    """H0 單項檢查結果 / H0 single gate check result."""
    allowed: bool
    reason: str
    check_name: str
    latency_us: int = 0

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> H0GateCheckResult:
        return cls(**json.loads(raw))


@dataclass
class StopConfig:
    """止損配置 / Stop-loss configuration."""
    hard_stop_pct: float = 5.0
    trailing_stop_pct: float | None = None
    time_stop_hours: float | None = None
    atr_multiplier: float | None = None  # ATR-based stop multiplier / ATR 倍數止損

    def validate(self) -> None:
        """驗證參數合法性 / Validate all parameters are positive when set."""
        if self.hard_stop_pct <= 0:
            raise ValueError(f"hard_stop_pct must be > 0, got {self.hard_stop_pct}")
        if self.trailing_stop_pct is not None and self.trailing_stop_pct <= 0:
            raise ValueError(f"trailing_stop_pct must be > 0, got {self.trailing_stop_pct}")
        if self.time_stop_hours is not None and self.time_stop_hours <= 0:
            raise ValueError(f"time_stop_hours must be > 0, got {self.time_stop_hours}")
        if self.atr_multiplier is not None and self.atr_multiplier <= 0:
            raise ValueError(f"atr_multiplier must be > 0, got {self.atr_multiplier}")

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> StopConfig:
        return cls(**json.loads(raw))


# ---------------------------------------------------------------------------
# Slot-based class / 插槽類
# ---------------------------------------------------------------------------

class PriceEvent:
    """
    即時價格事件（高頻，使用 __slots__ 節省記憶體）
    Real-time price event. Uses __slots__ for memory efficiency in hot path.
    """
    __slots__ = (
        "symbol", "last_price", "mark_price", "index_price",
        "best_bid", "best_ask", "volume_24h", "turnover_24h",
        "price_change_pct_24h", "high_24h", "low_24h",
        "ts_ms", "receive_ts_ms",
    )

    def __init__(
        self, symbol: str, last_price: float,
        mark_price: float | None = None, index_price: float | None = None,
        best_bid: float | None = None, best_ask: float | None = None,
        volume_24h: float | None = None, turnover_24h: float | None = None,
        price_change_pct_24h: float | None = None,
        high_24h: float | None = None, low_24h: float | None = None,
        ts_ms: int = 0, receive_ts_ms: int = 0,
    ):
        self.symbol = symbol
        self.last_price = last_price
        self.mark_price = mark_price
        self.index_price = index_price
        self.best_bid = best_bid
        self.best_ask = best_ask
        self.volume_24h = volume_24h
        self.turnover_24h = turnover_24h
        self.price_change_pct_24h = price_change_pct_24h
        self.high_24h = high_24h
        self.low_24h = low_24h
        self.ts_ms = ts_ms
        self.receive_ts_ms = receive_ts_ms

    def to_dict(self) -> dict[str, Any]:
        """轉為字典 / Convert to dictionary."""
        return {s: getattr(self, s) for s in self.__slots__}

    def to_json(self) -> str:
        """序列化為 JSON / Serialize to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, raw: str) -> PriceEvent:
        """從 JSON 反序列化 / Deserialize from JSON string."""
        return cls(**json.loads(raw))
