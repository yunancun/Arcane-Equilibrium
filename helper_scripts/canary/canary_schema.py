#!/usr/bin/env python3
"""
MODULE_NOTE (English):
  Canary JSONL schema — shared contract between Rust engine, Python shadow,
  and the comparator. Defines the per-tick record format, builder helpers,
  and validation functions.

MODULE_NOTE (中文):
  灰度 JSONL 模式 — Rust 引擎、Python 影子進程和比較器之間的共享合約。
  定義每 tick 記錄格式、構建輔助函數和驗證函數。

Usage:
  from canary_schema import CanaryRecord, validate_record
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

# ═══════════════════════════════════════════════════════════════════════════════
# Schema Version / 模式版本
# ═══════════════════════════════════════════════════════════════════════════════

SCHEMA_VERSION = "1.0.0"

# ═══════════════════════════════════════════════════════════════════════════════
# Tolerance Tiers (V3-FINAL §5.4) / 容差分級
# ═══════════════════════════════════════════════════════════════════════════════

TOLERANCE_SIMPLE = 1e-10       # SMA, EMA, balance, fees / 簡單聚合
TOLERANCE_RECURSIVE = 1e-8     # RSI, MACD, Stochastic, ADX / 遞歸指標
TOLERANCE_COMPLEX = 1e-6       # Hurst exponent / 複雜指標
BOUNDARY_THRESHOLD_PCT = 0.5   # Signal boundary exemption / 信號邊界豁免

# Field → tolerance mapping / 字段 → 容差映射
INDICATOR_TOLERANCES: dict[str, float] = {
    # Simple aggregates / 簡單聚合
    "sma_20": TOLERANCE_SIMPLE,
    "ema_12": TOLERANCE_SIMPLE,
    "volume_ratio": TOLERANCE_SIMPLE,
    # Bollinger — middle is simple, bands are derived
    "bollinger.middle": TOLERANCE_SIMPLE,
    "bollinger.upper": TOLERANCE_SIMPLE,
    "bollinger.lower": TOLERANCE_SIMPLE,
    "bollinger.bandwidth": TOLERANCE_RECURSIVE,
    "bollinger.percent_b": TOLERANCE_RECURSIVE,
    # Donchian — simple aggregates
    "donchian.upper": TOLERANCE_SIMPLE,
    "donchian.lower": TOLERANCE_SIMPLE,
    "donchian.middle": TOLERANCE_SIMPLE,
    "donchian.width": TOLERANCE_RECURSIVE,
    # Recursive indicators / 遞歸指標
    "rsi_14": TOLERANCE_RECURSIVE,
    "macd.macd": TOLERANCE_RECURSIVE,
    "macd.signal": TOLERANCE_RECURSIVE,
    "macd.histogram": TOLERANCE_RECURSIVE,
    "stochastic.k": TOLERANCE_RECURSIVE,
    "stochastic.d": TOLERANCE_RECURSIVE,
    "adx.adx": TOLERANCE_RECURSIVE,
    "adx.plus_di": TOLERANCE_RECURSIVE,
    "adx.minus_di": TOLERANCE_RECURSIVE,
    "atr.atr": TOLERANCE_RECURSIVE,
    "atr.atr_percent": TOLERANCE_RECURSIVE,
    "ewma_vol.ewma_vol": TOLERANCE_RECURSIVE,
    "kama.kama": TOLERANCE_RECURSIVE,
    "kama.efficiency_ratio": TOLERANCE_RECURSIVE,
    # Complex / 複雜
    "hurst.hurst": TOLERANCE_COMPLEX,
}

# Balance/PnL fields use simple tolerance / 餘額/PnL 字段用簡單容差
BALANCE_TOLERANCES: dict[str, float] = {
    "balance": TOLERANCE_SIMPLE,
    "peak_balance": TOLERANCE_SIMPLE,
    "total_realized_pnl": TOLERANCE_SIMPLE,
    "total_fees": TOLERANCE_SIMPLE,
    "unrealized_pnl": TOLERANCE_RECURSIVE,  # computed from prices
}


# ═══════════════════════════════════════════════════════════════════════════════
# Record Dataclasses / 記錄數據類
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class SignalRecord:
    """Per-signal record / 每信號記錄"""
    direction: str          # "Long" | "Short" | "CloseLong" | "CloseShort" | "Neutral"
    confidence: float       # 0.0-1.0
    edge_bps: float         # Expected edge in basis points / 預期收益基點
    source: str             # Signal rule name / 信號規則名稱
    reasoning: str = ""     # Human-readable explanation / 可讀解釋


@dataclass
class IntentRecord:
    """Per-order-intent record / 每意圖記錄"""
    symbol: str
    is_long: bool
    qty: float
    confidence: float       # 0.0-1.0
    strategy: str           # Strategy name / 策略名稱
    order_type: str         # "market" | "limit"
    limit_price: Optional[float] = None


@dataclass
class PositionRecord:
    """Per-position snapshot / 每持倉快照"""
    symbol: str
    is_long: bool
    qty: float
    entry_price: float
    best_price: float
    unrealized_pnl: float


@dataclass
class CanaryRecord:
    """
    One JSONL line per tick — the shared contract.
    每 tick 一行 JSONL — 共享合約。

    Both Rust engine and Python shadow emit records in this format.
    Rust 引擎和 Python 影子進程都以此格式輸出記錄。
    """
    schema_version: str
    source: str              # "rust_engine" | "python_shadow"
    tick_number: int
    timestamp_ms: int
    symbol: str
    price: float

    # Indicators (nested dict, matches IndicatorSnapshot) / 指標
    indicators: dict[str, Any] = field(default_factory=dict)

    # Signals fired this tick / 本 tick 觸發的信號
    signals: list[dict[str, Any]] = field(default_factory=list)

    # Order intents generated / 生成的訂單意圖
    order_intents: list[dict[str, Any]] = field(default_factory=list)

    # Paper trading state snapshot / 紙盤交易狀態快照
    paper_state: dict[str, Any] = field(default_factory=dict)

    # Tick statistics / Tick 統計
    stats: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize to JSON string / 序列化為 JSON 字符串"""
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, line: str) -> CanaryRecord:
        """Deserialize from JSON string / 從 JSON 字符串反序列化"""
        d = json.loads(line)
        return cls(**d)


def build_record(
    source: str,
    tick_number: int,
    timestamp_ms: int,
    symbol: str,
    price: float,
    indicators: Optional[dict] = None,
    signals: Optional[list] = None,
    order_intents: Optional[list] = None,
    paper_state: Optional[dict] = None,
    stats: Optional[dict] = None,
) -> CanaryRecord:
    """
    Build a CanaryRecord with defaults.
    構建帶默認值的 CanaryRecord。
    """
    return CanaryRecord(
        schema_version=SCHEMA_VERSION,
        source=source,
        tick_number=tick_number,
        timestamp_ms=timestamp_ms,
        symbol=symbol,
        price=price,
        indicators=indicators or {},
        signals=signals or [],
        order_intents=order_intents or [],
        paper_state=paper_state or {},
        stats=stats or {},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Validation / 驗證
# ═══════════════════════════════════════════════════════════════════════════════

REQUIRED_FIELDS = {"schema_version", "source", "tick_number", "timestamp_ms", "symbol", "price"}


def validate_record(record: dict) -> list[str]:
    """
    Validate a canary record dict. Returns list of error strings (empty = valid).
    驗證灰度記錄字典。返回錯誤字符串列表（空 = 有效）。
    """
    errors: list[str] = []

    for f in REQUIRED_FIELDS:
        if f not in record:
            errors.append(f"missing required field: {f}")

    if "source" in record and record["source"] not in ("rust_engine", "python_shadow"):
        errors.append(f"invalid source: {record['source']}")

    if "schema_version" in record and record["schema_version"] != SCHEMA_VERSION:
        errors.append(f"schema version mismatch: {record['schema_version']} != {SCHEMA_VERSION}")

    if "price" in record and not isinstance(record["price"], (int, float)):
        errors.append(f"price must be numeric, got {type(record['price'])}")

    return errors
