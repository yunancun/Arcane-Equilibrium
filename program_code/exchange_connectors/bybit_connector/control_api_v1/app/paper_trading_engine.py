from __future__ import annotations

"""
OpenClaw Paper Trading Engine / 纸上交易引擎
OpenClaw 模拟交易核心引擎 — 状态管理 + 订单生命周期 + 成交模拟 + 余额/持仓投影

MODULE_NOTE (中文):
  本模块实现完整的纸上交易引擎，基于 K 章骨架设计（7 状态生命周期 + 5 个投影函数 + 6 个适配器接口）。
  所有交易数据均为模拟，绝不与 Bybit 真实 API 交互。Paper state 独立于主控制状态文件。

MODULE_NOTE (English):
  This module implements the complete paper trading engine, based on K-chapter skeleton designs
  (7-state lifecycle + 5 projection functions + 6 adapter interfaces).
  All trading data is simulated. Never interacts with real Bybit APIs.
  Paper state is fully isolated from the main control state file.
"""

# DEPRECATED(R-07): Core matching/execution migrated to Rust openclaw_engine.
#   Rust: openclaw_engine/src/paper_state.rs + intent_processor.rs (tick processing, order matching, fill execution)
#   Stays in Python: PaperStateStore I/O, session lifecycle (start/stop/reset), 7-state machine, REST API integration
#   DO NOT DELETE — 23+ importers depend on this module. Remove after R-07 grey-period.

import copy
import hashlib
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .protective_order_manager import ProtectiveOrderManager
from .utils.time_utils import now_ms

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Constants / 常量
# ═══════════════════════════════════════════════════════════════════════════════

# Paper order lifecycle states (from K chapter skeleton)
# 纸上订单生命周期状态（来自 K 章骨架）
ORDER_STATE_CREATED = "paper_order_created"
ORDER_STATE_SUBMITTED = "paper_order_submitted"
ORDER_STATE_WORKING = "paper_order_working"
ORDER_STATE_PARTIALLY_FILLED = "paper_order_partially_filled"
ORDER_STATE_FILLED = "paper_order_filled"
ORDER_STATE_CANCELED = "paper_order_canceled"
ORDER_STATE_REJECTED = "paper_order_rejected"

TERMINAL_STATES = {ORDER_STATE_FILLED, ORDER_STATE_CANCELED, ORDER_STATE_REJECTED}
ACTIVE_STATES = {ORDER_STATE_WORKING, ORDER_STATE_PARTIALLY_FILLED}

# Valid state transitions (from K chapter skeleton - 8 edges)
VALID_TRANSITIONS: dict[str, set[str]] = {
    ORDER_STATE_CREATED: {ORDER_STATE_SUBMITTED},
    ORDER_STATE_SUBMITTED: {ORDER_STATE_WORKING, ORDER_STATE_REJECTED},
    ORDER_STATE_WORKING: {ORDER_STATE_PARTIALLY_FILLED, ORDER_STATE_FILLED, ORDER_STATE_CANCELED},
    ORDER_STATE_PARTIALLY_FILLED: {ORDER_STATE_FILLED, ORDER_STATE_CANCELED},
}

# ═══════════════════════════════════════════════════════════════════════════════
# Batch 10: OMS SM-03 Integration / OMS SM-03 串联
# Configuration switch to enable/disable OMS SM-03 enforcement.
# 配置开关：启用/禁用 OMS SM-03 强制执行。回退路径：设 False 恢复旧 7 态。
# ═══════════════════════════════════════════════════════════════════════════════
OMS_SM03_ENABLED: bool = True  # Set False to fall back to legacy 7-state lifecycle

# Session states
SESSION_INACTIVE = "inactive"
SESSION_ACTIVE = "active"
SESSION_PAUSED = "paused"
SESSION_COMPLETED = "completed"

# Order types / 订单类型
ORDER_TYPE_MARKET = "market"
ORDER_TYPE_LIMIT = "limit"
ORDER_TYPE_CONDITIONAL = "conditional"  # Triggered when price hits trigger_price

# Order sides
SIDE_BUY = "Buy"
SIDE_SELL = "Sell"

# Time in Force / 有效期类型
TIF_GTC = "GTC"            # Good-Till-Cancelled（默认）
TIF_IOC = "IOC"            # Immediate-or-Cancel
TIF_FOK = "FOK"            # Fill-or-Kill
TIF_POST_ONLY = "PostOnly"  # Cancel if would fill immediately (guarantees maker fee)

VALID_TIF = {TIF_GTC, TIF_IOC, TIF_FOK, TIF_POST_ONLY}

# Order flags / 订单标记
FLAG_REDUCE_ONLY = "reduce_only"    # Only reduce position, never increase
FLAG_POST_ONLY = "post_only"        # Same as TIF_POST_ONLY, alternative expression

# Trigger price types (for conditional orders) / 触发价类型
TRIGGER_BY_LAST_PRICE = "LastPrice"
TRIGGER_BY_MARK_PRICE = "MarkPrice"
TRIGGER_BY_INDEX_PRICE = "IndexPrice"

# Product categories / 产品品类
CATEGORY_SPOT = "spot"
CATEGORY_LINEAR = "linear"
CATEGORY_INVERSE = "inverse"
CATEGORY_OPTION = "option"

# Fee rates (Bybit perpetual linear defaults)
# 费率（Bybit 永续线性合约默认值）
DEFAULT_TAKER_FEE_RATE = 0.00055   # 0.055%
DEFAULT_MAKER_FEE_RATE = 0.0002    # 0.02%

# Simulated slippage for market orders
# 市場單模擬滑點（默認值，低流動性品種或無成交量數據時使用）
DEFAULT_SLIPPAGE_RATE = 0.0005  # 0.05%

# Dynamic slippage tiers based on 24h USD turnover (more realistic Paper simulation)
# 動態滑點分級（基於 24h 成交額），讓 Paper PnL 更貼近實際交易成本
# BTC/ETH 等大幣種滑點極低 (~1 bps)，小幣種可達 30 bps
SLIPPAGE_TIERS: list[tuple[float, float]] = [
    (1_000_000_000, 0.0001),   # >$1B turnover: 1 bps (BTC/ETH)
    (100_000_000,   0.0002),   # >$100M: 2 bps
    (10_000_000,    0.0005),   # >$10M: 5 bps (same as old default)
    (1_000_000,     0.0015),   # >$1M: 15 bps
    (0,             0.0030),   # <$1M: 30 bps (illiquid alts)
]


def compute_dynamic_slippage(volume_24h: float) -> float:
    """
    Return slippage rate based on 24h trading volume.
    根據 24h 成交量返回對應的滑點率。

    Higher volume = tighter spread = lower slippage.
    成交量越大，價差越小，滑點越低。
    Falls back to DEFAULT_SLIPPAGE_RATE if volume is non-positive.
    """
    if volume_24h <= 0:
        return DEFAULT_SLIPPAGE_RATE
    for threshold, rate in SLIPPAGE_TIERS:
        if volume_24h >= threshold:
            return rate
    return DEFAULT_SLIPPAGE_RATE

# Default initial paper balance
DEFAULT_INITIAL_BALANCE_USDT = 10000.0


# ═══════════════════════════════════════════════════════════════════════════════
# Utility / 工具函数
# ═══════════════════════════════════════════════════════════════════════════════

def gen_order_id() -> str:
    return f"pord:{uuid.uuid4().hex[:12]}"


def gen_fill_id() -> str:
    return f"pfil:{uuid.uuid4().hex[:12]}"


def gen_session_id() -> str:
    return f"psess:{uuid.uuid4().hex[:8]}"


# ═══════════════════════════════════════════════════════════════════════════════
# Paper State Store / 纸上交易状态存储
# ═══════════════════════════════════════════════════════════════════════════════

def build_default_paper_state() -> dict[str, Any]:
    """Build the default paper trading state / 构建默认纸上交易状态"""
    return {
        "meta": {
            "state_version": "paper_v1",
            "revision": 0,
            "created_ts_ms": now_ms(),
            "updated_ts_ms": now_ms(),
        },
        "session": {
            "session_id": None,
            "session_state": SESSION_INACTIVE,
            "started_ts_ms": None,
            "paused_ts_ms": None,
            "stopped_ts_ms": None,
            "initial_paper_balance_usdt": DEFAULT_INITIAL_BALANCE_USDT,
            "current_paper_balance_usdt": DEFAULT_INITIAL_BALANCE_USDT,
            "peak_balance_usdt": DEFAULT_INITIAL_BALANCE_USDT,
            "daily_start_balance_usdt": DEFAULT_INITIAL_BALANCE_USDT,
            "daily_start_date": "",
            "session_halted": False,
            "session_halt_reason": None,
        },
        "orders": [],
        "positions": {},
        "fills": [],
        "audit_trail": [],
        "pnl": {
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "closed_position_pnl": 0.0,  # PnL from fully closed positions
            "total_fees_paid": 0.0,
            "total_ai_cost": 0.0,
            "net_realized_pnl": 0.0,     # realized_pnl minus fees / 扣费后净实现盈亏
            "net_paper_pnl": 0.0,
        },
        "shadow_decisions": [],
        "risk": {},
    }


class PaperStateStore:
    """
    Isolated state store for paper trading / 纸上交易专用隔离状态存储

    Uses the same pattern as JsonStateStore but with a separate file.
    复用 JsonStateStore 模式但使用独立文件。
    """

    def __init__(self, file_path: str) -> None:
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._lock = threading.RLock()
        # In-memory cache: avoids re-reading from disk on every tick.
        # 內存緩存：避免每次 tick 都從磁碟讀取。
        self._cache: dict[str, Any] | None = None
        # Debounced disk write: tick() calls mutate() many times per second,
        # but actual disk I/O only happens every WRITE_INTERVAL_S seconds.
        # 防抖磁碟寫入：tick() 每秒多次 mutate()，但磁碟 I/O 最多每 5 秒一次。
        self._WRITE_INTERVAL_S = 5.0
        self._last_disk_write_ts: float = 0.0
        self._dirty = False
        if not self.file_path.exists():
            self.write(build_default_paper_state(), force=True)

    def read(self) -> dict[str, Any]:
        with self._lock:
            if self._cache is not None:
                return copy.deepcopy(self._cache)
            with self.file_path.open("r", encoding="utf-8") as handle:
                self._cache = json.load(handle)
                return copy.deepcopy(self._cache)

    def write(self, state: dict[str, Any], force: bool = False) -> dict[str, Any]:
        import tempfile
        with self._lock:
            state["meta"]["revision"] = state["meta"].get("revision", 0) + 1
            state["meta"]["updated_ts_ms"] = now_ms()
            self._cache = state
            self._dirty = True

            # Debounce: skip disk write if interval hasn't elapsed (unless forced)
            # 防抖：如果間隔未達到則跳過磁碟寫入（除非強制）
            _now = time.time()
            if not force and (_now - self._last_disk_write_ts) < self._WRITE_INTERVAL_S:
                return state

            # Atomic write: write to temp file then rename (crash-safe)
            # 原子写入：先写临时文件再重命名（崩溃安全）
            dir_path = self.file_path.parent
            fd, tmp_path = tempfile.mkstemp(dir=str(dir_path), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(state, handle, ensure_ascii=False, indent=2)
                os.chmod(tmp_path, 0o600)
                os.replace(tmp_path, str(self.file_path))
                self._last_disk_write_ts = _now
                self._dirty = False
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            return state

    def flush(self) -> None:
        """Force write cached state to disk / 強制將緩存狀態寫入磁碟"""
        with self._lock:
            if self._cache is not None and self._dirty:
                self.write(self._cache, force=True)

    def mutate(self, mutator) -> dict[str, Any]:
        # Read a copy of current state (briefly acquires lock)
        current = self.read()
        # Run mutator WITHOUT holding lock — allows concurrent reads during computation.
        # 在不持鎖的情況下執行 mutator — 允許計算期間併發讀取。
        mutated = mutator(current)
        # Briefly lock to write result back
        with self._lock:
            return self.write(mutated)


# ═══════════════════════════════════════════════════════════════════════════════
# Paper Order Lifecycle Engine / 纸上订单生命周期引擎
# (Implements K chapter 7-state lifecycle)
# ═══════════════════════════════════════════════════════════════════════════════

def _transition_order(order: dict, new_state: str, *, oms_sm=None) -> dict:
    """
    Validate and execute a state transition on a paper order.
    Batch 10: If OMS SM-03 is enabled and oms_sm is provided, the transition
    is also validated and synced through the 11-state OMS lifecycle.
    """
    current = order["state"]
    valid_next = VALID_TRANSITIONS.get(current, set())
    if new_state not in valid_next:
        raise ValueError(
            f"Invalid transition: {current} → {new_state}. "
            f"Valid targets: {valid_next}"
        )

    # Batch 10: OMS SM-03 enforcement — sync transition to 11-state lifecycle
    # Paper 7-state maps to OMS 11-state with intermediate steps:
    #   Paper CREATED→SUBMITTED  ≡ OMS CREATED→PENDING→APPROVED→SUBMITTED
    #   Paper SUBMITTED→WORKING  ≡ OMS SUBMITTED→WORKING
    #   Paper SUBMITTED→REJECTED ≡ OMS SUBMITTED→REJECTED (or PENDING→REJECTED)
    #   Paper WORKING→FILLED     ≡ OMS WORKING→FILLED
    #   Paper WORKING→CANCELED   ≡ OMS WORKING→CANCELED
    if OMS_SM03_ENABLED and oms_sm is not None:
        oms_order_id = order.get("oms_order_id")
        if oms_order_id:
            try:
                from .oms_state_machine import OMSStateMachine, OrderState as OmsOrderState, OrderInitiator
                target_oms = OMSStateMachine.map_from_paper_state(new_state)

                # For CREATED→SUBMITTED, we need to drive through PENDING→APPROVED→SUBMITTED
                if current == ORDER_STATE_CREATED and new_state == ORDER_STATE_SUBMITTED:
                    oms_sm.submit_for_approval(oms_order_id, initiator=OrderInitiator.SYSTEM,
                                                reason="paper_engine_submit")
                    oms_sm.approve(oms_order_id, initiator=OrderInitiator.AUTHORIZATION_SM,
                                   reason="paper_engine_auto_approve")
                    oms_sm.send_to_venue(oms_order_id, initiator=OrderInitiator.SYSTEM,
                                          reason="paper_engine_send")
                elif current == ORDER_STATE_SUBMITTED and new_state == ORDER_STATE_REJECTED:
                    # OMS is already in SUBMITTED state, transition to REJECTED
                    oms_sm.reject(oms_order_id, initiator=OrderInitiator.SYSTEM,
                                  reason=f"paper_engine_reject:{order.get('reject_reason', '')}")
                else:
                    # Direct 1:1 mapping for remaining transitions
                    oms_sm.transition(
                        oms_order_id,
                        target_oms,
                        initiator=OrderInitiator.SYSTEM,
                        reason=f"paper_engine_sync:{current}→{new_state}",
                    )
                order["oms_state"] = target_oms.value
            except ValueError as e:
                # SM-03 rejected the transition — fail-closed
                logger.warning(
                    "OMS SM-03 rejected transition %s→%s for %s: %s",
                    current, new_state, order.get("order_id"), e,
                )
                raise ValueError(
                    f"OMS SM-03 rejected: {current} → {new_state}. Reason: {e}"
                ) from e
            except Exception as e:
                # Unexpected error — fail-closed (do NOT proceed with the paper transition)
                logger.error(
                    "OMS SM-03 sync error for %s: %s — fail-closed",
                    order.get("order_id"), e,
                )
                raise ValueError(
                    f"OMS SM-03 sync error: {e} — fail-closed"
                ) from e

    order["state"] = new_state
    order["updated_ts_ms"] = now_ms()
    order["state_history"].append({
        "from": current,
        "to": new_state,
        "ts_ms": order["updated_ts_ms"],
    })
    return order


def create_paper_order(
    symbol: str,
    side: str,
    order_type: str,
    qty: float,
    price: float | None = None,
    leverage: float = 1.0,
    *,
    time_in_force: str = TIF_GTC,
    reduce_only: bool = False,
    trigger_price: float | None = None,
    trigger_by: str = TRIGGER_BY_LAST_PRICE,
    take_profit: float | None = None,
    stop_loss: float | None = None,
    tp_trigger_by: str = TRIGGER_BY_LAST_PRICE,
    sl_trigger_by: str = TRIGGER_BY_LAST_PRICE,
    category: str = CATEGORY_LINEAR,
    strategy_name: str = "",
) -> dict[str, Any]:
    """
    Create a new paper order object / 创建纸上订单对象

    Supports: market, limit, conditional orders with optional TP/SL.
    支持：市价、限价、条件触发单，可附加止盈止损。

    This only creates the order in 'paper_order_created' state.
    Submission and lifecycle processing happen in subsequent steps.
    """
    valid_types = (ORDER_TYPE_MARKET, ORDER_TYPE_LIMIT, ORDER_TYPE_CONDITIONAL)
    if side not in (SIDE_BUY, SIDE_SELL):
        raise ValueError(f"Invalid side: {side}. Must be '{SIDE_BUY}' or '{SIDE_SELL}'")
    if order_type not in valid_types:
        raise ValueError(f"Invalid order_type: {order_type}. Must be one of {valid_types}")
    if order_type == ORDER_TYPE_LIMIT and price is None:
        raise ValueError("Limit orders require a price")
    if order_type == ORDER_TYPE_CONDITIONAL and trigger_price is None:
        raise ValueError("Conditional orders require a trigger_price")
    if qty <= 0:
        raise ValueError("Quantity must be positive")
    if time_in_force not in VALID_TIF:
        time_in_force = TIF_GTC

    ts = now_ms()
    order: dict[str, Any] = {
        "order_id": gen_order_id(),
        "symbol": symbol,
        "side": side,
        "order_type": order_type,
        "qty": qty,
        "filled_qty": 0.0,
        "remaining_qty": qty,
        "price": price,
        "avg_fill_price": None,
        "leverage": leverage,
        "state": ORDER_STATE_CREATED,
        "created_ts_ms": ts,
        "updated_ts_ms": ts,
        "state_history": [{"from": None, "to": ORDER_STATE_CREATED, "ts_ms": ts}],
        "fills": [],
        "is_simulated": True,
        "data_source": "paper_engine_v1",
        # New fields / 新增字段
        "time_in_force": time_in_force,
        "reduce_only": reduce_only,
        "category": category,
        "strategy_name": strategy_name,
    }

    # Conditional order fields / 条件单字段
    if order_type == ORDER_TYPE_CONDITIONAL:
        order["trigger_price"] = trigger_price
        order["trigger_by"] = trigger_by
        order["triggered"] = False

    # TP/SL attachment / 止盈止损附加
    if take_profit is not None or stop_loss is not None:
        order["tp_sl"] = {
            "take_profit": take_profit,
            "stop_loss": stop_loss,
            "tp_trigger_by": tp_trigger_by,
            "sl_trigger_by": sl_trigger_by,
        }

    return order


# ═══════════════════════════════════════════════════════════════════════════════
# Fill Simulation / 成交模拟
# ═══════════════════════════════════════════════════════════════════════════════

def compute_fill_price(
    order: dict,
    market_price: float,
    slippage_rate: float = DEFAULT_SLIPPAGE_RATE,
) -> float:
    """
    Compute the fill price for an order / 计算订单的成交价格

    Market orders: market_price + slippage (adverse direction)
    Limit orders: limit price (no slippage, since it's a resting order)
    """
    if order["order_type"] == ORDER_TYPE_MARKET:
        if order["side"] == SIDE_BUY:
            return market_price * (1 + slippage_rate)
        else:
            return market_price * (1 - slippage_rate)
    else:
        return order["price"]


def compute_fee(
    fill_qty: float,
    fill_price: float,
    is_taker: bool = True,
    taker_rate: float = DEFAULT_TAKER_FEE_RATE,
    maker_rate: float = DEFAULT_MAKER_FEE_RATE,
) -> float:
    """Compute trading fee for a fill / 计算成交手续费"""
    notional = fill_qty * fill_price
    rate = taker_rate if is_taker else maker_rate
    return notional * rate


def compute_partial_fill_qty(
    order: dict,
    market_price: float,
    rng: Any = None,
) -> float:
    """
    Simulate partial fill quantity for limit orders based on price cross depth.
    根据价格穿越深度模拟限价单部分成交数量。

    Deep cross (>0.5%) → full fill. Shallow cross → probabilistic partial fill.
    深穿（>0.5%）→ 全部成交。浅穿 → 概率性部分成交。

    Args:
        rng: Optional random.Random instance for deterministic testing.
             可选的 random.Random 实例，用于测试确定性。
    """
    import random as _random
    r = rng or _random

    remaining = order["remaining_qty"]
    limit_price = order["price"]
    if limit_price <= 0 or remaining <= 0:
        return remaining

    # Dust check: if remaining < 1% of original qty, fill it all at once.
    # Prevents geometric-decay fragmentation (25-30 fills per order).
    # 尾量检查：剩余量 < 原始数量 1% 时一次性全部成交，防止几何衰减碎片化。
    if remaining <= order["qty"] * 0.01:
        return remaining

    if order["side"] == SIDE_BUY:
        cross_pct = (limit_price - market_price) / limit_price
    else:
        cross_pct = (market_price - limit_price) / limit_price

    cross_pct = max(cross_pct, 0.0)

    if cross_pct >= 0.005:
        fill_fraction = 1.0
    elif cross_pct >= 0.001:
        fill_fraction = r.uniform(0.5, 1.0)
    else:
        fill_fraction = r.uniform(0.3, 0.7)

    fill_qty = remaining * fill_fraction
    min_fill = remaining * 0.1
    fill_qty = max(fill_qty, min_fill)
    return min(fill_qty, remaining)


def should_fill_limit_order(order: dict, market_price: float) -> bool:
    """
    Check if a limit order should be filled at the current market price.
    检查限价单是否应在当前市场价下成交。

    Buy limit: fills when market_price <= limit_price
    Sell limit: fills when market_price >= limit_price
    """
    if order["order_type"] != ORDER_TYPE_LIMIT:
        return False
    if order["state"] not in ACTIVE_STATES:
        return False
    if order["side"] == SIDE_BUY:
        return market_price <= order["price"]
    else:
        return market_price >= order["price"]


def execute_fill(
    order: dict,
    fill_qty: float,
    fill_price: float,
    fee: float,
) -> dict[str, Any]:
    """
    Execute a fill on an order and return fill record / 执行成交并返回成交记录

    Updates order state (filled_qty, remaining_qty, avg_fill_price, state).
    """
    fill_id = gen_fill_id()
    ts = now_ms()

    # Update order quantities
    order["filled_qty"] += fill_qty
    order["remaining_qty"] = order["qty"] - order["filled_qty"]

    # Update avg fill price (weighted average)
    if order["avg_fill_price"] is None:
        order["avg_fill_price"] = fill_price
    else:
        total_filled = order["filled_qty"]
        prev_filled = total_filled - fill_qty
        order["avg_fill_price"] = (
            (order["avg_fill_price"] * prev_filled + fill_price * fill_qty) / total_filled
        )

    # Create fill record
    fill_record = {
        "fill_id": fill_id,
        "order_id": order["order_id"],
        "symbol": order["symbol"],
        "side": order["side"],
        "qty": fill_qty,
        "price": fill_price,
        "fee": fee,
        "notional": fill_qty * fill_price,
        "ts_ms": ts,
        "is_simulated": True,
    }
    order["fills"].append(fill_record)

    # Transition state
    if order["remaining_qty"] <= 1e-10:
        order["remaining_qty"] = 0.0
        _transition_order(order, ORDER_STATE_FILLED)
    elif order["state"] == ORDER_STATE_WORKING:
        _transition_order(order, ORDER_STATE_PARTIALLY_FILLED)

    return fill_record


# ═══════════════════════════════════════════════════════════════════════════════
# Position / Balance Projection / 持仓与余额投影
# (Implements K chapter projection_surface)
# ═══════════════════════════════════════════════════════════════════════════════

def project_position_after_fill(
    positions: dict[str, Any],
    symbol: str,
    side: str,
    fill_qty: float,
    fill_price: float,
    category: str = "linear",
    strategy_name: str = "",
) -> tuple[dict[str, Any], float]:
    """
    Project position state after a fill / 投影成交后的持仓状态

    Handles: opening new position, adding to position, reducing position, flipping position.
    Returns: (positions, close_pnl) — close_pnl is realized PnL from closing (0 if opening/adding).
    category: Bybit API category ("linear"/"spot"/"inverse") — stored on position for downstream use.
    """
    pos = positions.get(symbol)
    close_pnl = 0.0

    if pos is None:
        # New position
        positions[symbol] = {
            "symbol": symbol,
            "side": side,
            "qty": fill_qty,
            "avg_entry_price": fill_price,
            "unrealized_pnl": 0.0,
            "realized_pnl": 0.0,
            "opened_ts_ms": now_ms(),
            "updated_ts_ms": now_ms(),
            "is_simulated": True,
            "category": category,
            "strategy_name": strategy_name,
            # AI attention tax tracking / AI 注意力税追踪
            "holding_cost": {
                "financial_cost_usd": 0.0,
                "ai_cost_attributed_usd": 0.0,
                "total_holding_cost_usd": 0.0,
                "estimated_remaining_edge_usd": 0.0,
                "cost_edge_ratio": 0.0,
                "cost_efficiency_grade": "A",
                "hourly_ai_burn_rate_usd": 0.003,
            },
        }
        return positions, close_pnl

    pos["updated_ts_ms"] = now_ms()

    # Float tolerance for quantity comparisons / 数量比较的浮点容差
    _QTY_EPS = 1e-10

    if pos["side"] == side:
        # Same direction: add to position (average up/down)
        total_qty = pos["qty"] + fill_qty
        pos["avg_entry_price"] = (
            (pos["avg_entry_price"] * pos["qty"] + fill_price * fill_qty) / total_qty
        )
        pos["qty"] = total_qty
    else:
        # Opposite direction: reduce or flip
        # Use tolerance-based comparison instead of exact float equality
        # 使用容差比较代替精确浮点数相等
        diff = pos["qty"] - fill_qty
        if diff > _QTY_EPS:
            # Partial close
            close_pnl = _compute_close_pnl(pos, fill_qty, fill_price)
            pos["realized_pnl"] += close_pnl
            pos["qty"] = diff  # Use subtraction result directly
        elif abs(diff) <= _QTY_EPS:
            # Full close (within tolerance)
            close_pnl = _compute_close_pnl(pos, pos["qty"], fill_price)
            pos["realized_pnl"] += close_pnl
            del positions[symbol]
            return positions, close_pnl
        else:
            # Flip: close existing + open opposite
            # close_pnl is returned and accumulated by caller into closed_position_pnl.
            # New position starts with realized_pnl=0 to avoid double-counting.
            # 翻转：平旧仓 + 开反向仓。close_pnl 由调用方累加到 closed_position_pnl，
            # 新仓位 realized_pnl=0 避免双重计算。
            close_pnl = _compute_close_pnl(pos, pos["qty"], fill_price)
            remaining = fill_qty - pos["qty"]
            positions[symbol] = {
                "symbol": symbol,
                "side": side,
                "qty": remaining,
                "avg_entry_price": fill_price,
                "unrealized_pnl": 0.0,
                "realized_pnl": 0.0,
                "opened_ts_ms": now_ms(),
                "updated_ts_ms": now_ms(),
                "is_simulated": True,
                # SPOT-2 FIX: 翻转路径保留原持仓的 category，避免丢失品类信息
                # SPOT-2 FIX: Preserve category from existing position during flip;
                # fallback to "linear" if original position lacked the field.
                "category": pos.get("category", "linear"),
                "holding_cost": {
                    "financial_cost_usd": 0.0,
                    "ai_cost_attributed_usd": 0.0,
                    "total_holding_cost_usd": 0.0,
                    "estimated_remaining_edge_usd": 0.0,
                    "cost_edge_ratio": 0.0,
                    "cost_efficiency_grade": "A",
                    "hourly_ai_burn_rate_usd": 0.003,
                },
            }

    return positions, close_pnl


def _compute_close_pnl(pos: dict, close_qty: float, close_price: float) -> float:
    """
    Compute realized PnL for closing a position.
    计算平仓实现盈亏。

    Two formulas depending on contract category:
    根据合约品类使用不同公式：

    Linear / Spot (USDT-margined):
      Long PnL  = (close_price - entry_price) * qty   [quote currency, e.g. USDT]
      Short PnL = (entry_price - close_price) * qty

    Inverse (coin-margined, e.g. BTCUSD):
      Long PnL  = qty * (1/entry_price - 1/close_price)  [base currency, e.g. BTC]
      Short PnL = qty * (1/close_price - 1/entry_price)
      Zero-division guard: entry <= 0 or close <= 0 → return 0.0
      除零保護：entry 或 close 價格 ≤ 0 時返回 0.0，不拋異常

    Numerical validation / 數值驗證:
      Long  qty=100, entry=50000, close=55000 → 100*(1/50000-1/55000) ≈ 0.0001818 BTC
      Short qty=100, entry=50000, close=45000 → 100*(1/45000-1/50000) ≈ 0.0002222 BTC
    """
    # Determine contract category; default to "linear" for backward compatibility
    # 讀取合約品類；預設為 "linear" 以向後兼容
    category = pos.get("category", "linear")

    entry = pos["avg_entry_price"]

    if category == "inverse":
        # Inverse (coin-margined): PnL denominated in base currency (e.g. BTC)
        # 幣本位合約：PnL 以基礎幣計價（如 BTC）
        # Fail-closed: return 0.0 on zero-price to avoid ZeroDivisionError
        # fail-closed 除零保護：價格為 0 時返回 0.0
        if entry <= 0.0 or close_price <= 0.0:
            return 0.0
        if pos["side"] == SIDE_BUY:
            return close_qty * (1.0 / entry - 1.0 / close_price)
        else:
            return close_qty * (1.0 / close_price - 1.0 / entry)
    else:
        # Linear / Spot (USDT-margined): PnL denominated in quote currency (e.g. USDT)
        # U 本位 / 現貨合約：PnL 以計價幣計價（如 USDT）
        if pos["side"] == SIDE_BUY:
            return (close_price - entry) * close_qty
        else:
            return (entry - close_price) * close_qty


def project_balance_after_fill(
    current_balance: float,
    side: str,
    fill_qty: float,
    fill_price: float,
    fee: float,
    leverage: float = 1.0,
) -> float:
    """
    Project balance after a fill / 投影成交后的余额

    For perpetual contracts, margin is notional / leverage.
    Fee is always deducted.
    """
    # Fee is always deducted
    new_balance = current_balance - fee
    # Note: for perpetual contracts, margin is locked/released separately.
    # In paper trading, we track the balance reduction from fees and realized PnL.
    # Unrealized PnL is computed from mark price and doesn't affect balance until close.
    return new_balance


def project_fee_and_cash_impact(
    fill_qty: float,
    fill_price: float,
    is_taker: bool,
    taker_rate: float = DEFAULT_TAKER_FEE_RATE,
    maker_rate: float = DEFAULT_MAKER_FEE_RATE,
) -> dict[str, float]:
    """Compute fee and cash impact for a fill / 计算成交费用及现金影响"""
    fee = compute_fee(fill_qty, fill_price, is_taker, taker_rate, maker_rate)
    notional = fill_qty * fill_price
    return {
        "fee": fee,
        "notional": notional,
        "fee_rate": taker_rate if is_taker else maker_rate,
    }


def update_unrealized_pnl(
    positions: dict[str, Any],
    market_prices: dict[str, float],
) -> dict[str, Any]:
    """
    Update unrealized PnL for all positions based on current market prices.
    根据当前市场价格更新所有持仓的未实现盈亏。

    Two formulas depending on contract category:
    根据合约品类使用不同公式：

    Linear / Spot (USDT-margined):
      Long  unrealized = (mark_price - entry_price) * qty   [USDT]
      Short unrealized = (entry_price - mark_price) * qty

    Inverse (coin-margined, e.g. BTCUSD):
      Long  unrealized = qty * (1/entry_price - 1/mark_price)  [BTC]
      Short unrealized = qty * (1/mark_price - 1/entry_price)
      Zero-division guard: entry <= 0 or mark_price <= 0 → unrealized_pnl = 0.0
      除零保護：entry 或 mark_price ≤ 0 時設為 0.0，不拋異常
    """
    for symbol, pos in positions.items():
        price = market_prices.get(symbol)
        if price is None:
            continue

        # Determine contract category; default to "linear" for backward compatibility
        # 讀取合約品類；預設為 "linear" 以向後兼容
        category = pos.get("category", "linear")
        entry = pos["avg_entry_price"]

        if category == "inverse":
            # Inverse (coin-margined): unrealized PnL in base currency (e.g. BTC)
            # 幣本位合約：未實現 PnL 以基礎幣計價（如 BTC）
            # Fail-closed: set to 0.0 on zero-price to avoid ZeroDivisionError
            # fail-closed 除零保護：價格為 0 時設為 0.0
            if entry <= 0.0 or price <= 0.0:
                pos["unrealized_pnl"] = 0.0
            elif pos["side"] == SIDE_BUY:
                pos["unrealized_pnl"] = pos["qty"] * (1.0 / entry - 1.0 / price)
            else:
                pos["unrealized_pnl"] = pos["qty"] * (1.0 / price - 1.0 / entry)
        else:
            # Linear / Spot: unrealized PnL in quote currency (e.g. USDT)
            # U 本位 / 現貨：未實現 PnL 以計價幣計價（如 USDT）
            if pos["side"] == SIDE_BUY:
                pos["unrealized_pnl"] = (price - entry) * pos["qty"]
            else:
                pos["unrealized_pnl"] = (entry - price) * pos["qty"]

        pos["updated_ts_ms"] = now_ms()
    return positions


# ═══════════════════════════════════════════════════════════════════════════════
# Paper State → Reconciliation Format Adapter / 纸上状态 → 对账格式转换
# ═══════════════════════════════════════════════════════════════════════════════

def _paper_state_to_recon_format(state: dict[str, Any]) -> dict[str, Any]:
    """
    Convert internal paper state to reconciliation engine format / 将内部纸上状态转换为对账格式

    Expected format for reconciliation engine:
    - snapshot_ts_ms: int — timestamp in milliseconds
    - orders: list[dict] — order snapshots
    - positions: dict[str, dict] — positions keyed by symbol
    - fills: list[dict] — execution records
    - balances: dict[str, float] — asset balances (e.g., USDT)
    """
    return {
        "snapshot_ts_ms": state.get("meta", {}).get("updated_ts_ms", now_ms()),
        "orders": state.get("orders", []),
        "positions": state.get("positions", {}),
        "fills": state.get("fills", []),
        "balances": {"USDT": state.get("session", {}).get("current_paper_balance_usdt", 0.0)},
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Batch 10: OMS SM-03 Post-Fill Reconciliation Helper
# ═══════════════════════════════════════════════════════════════════════════════

def _oms_complete_reconciliation(order: dict, oms_sm) -> None:
    """
    After a paper order is FILLED, drive OMS SM-03 from current OMS state through
    FILLED → RECONCILING → COMPLETED lifecycle.

    Since execute_fill() is a standalone function that doesn't know about OMS,
    we first catch up the OMS state to FILLED (if needed), then drive reconciliation.
    """
    if not OMS_SM03_ENABLED or oms_sm is None:
        return
    oms_order_id = order.get("oms_order_id")
    if not oms_order_id:
        return
    try:
        from .oms_state_machine import OrderInitiator, OrderState as OmsOrderState

        # Catch up OMS to FILLED if not already there
        # (execute_fill doesn't sync OMS, so OMS may still be at WORKING)
        oms_dict = oms_sm.get(oms_order_id)
        if oms_dict:
            current_oms = oms_dict.get("state", "")
            if current_oms == "WORKING":
                oms_sm.fill(oms_order_id, initiator=OrderInitiator.EXECUTION_VENUE,
                           reason="paper_fill_sync")
            elif current_oms == "PARTIALLY_FILLED":
                oms_sm.fill(oms_order_id, initiator=OrderInitiator.EXECUTION_VENUE,
                           reason="paper_fill_sync")
            # If already FILLED, skip

        oms_sm.begin_reconciliation(
            oms_order_id,
            initiator=OrderInitiator.RECONCILIATION_ENGINE,
            reason="paper_fill_auto_reconcile",
        )
        oms_sm.reconciliation_pass(
            oms_order_id,
            initiator=OrderInitiator.RECONCILIATION_ENGINE,
            reason="paper_fill_verified",
        )
        order["oms_state"] = "COMPLETED"
    except Exception as e:
        # Non-fatal: reconciliation is a verification step, not a blocker for paper fills
        logger.warning("OMS post-fill reconciliation failed for %s: %s", oms_order_id, e)
        order["oms_reconciliation_error"] = str(e)


# ═══════════════════════════════════════════════════════════════════════════════
# submit_order mutator sub-functions (module-level, called by mutator closure)
# submit_order mutator 子函数（模块级别，由 mutator 闭包调用）
# ═══════════════════════════════════════════════════════════════════════════════
# Mutator return protocol / Mutator 返回協議:
#   return state  → early exit (rejection/error), mutator dispatcher returns immediately
#   return None   → continue to next step, mutator dispatcher proceeds
# ═══════════════════════════════════════════════════════════════════════════════


def _mutator_validate_order(
    state: dict,
    result: dict,
    order: dict,
    symbol: str,
    side: str,
    qty: float,
    price: float | None,
    leverage: float,
    order_type: str,
    category: str,
    market_prices: dict[str, float] | None,
    engine: "PaperTradingEngine",
    _oms: Any,
) -> dict | None:
    """
    Validation phase of submit_order mutator: governance, risk, margin checks.
    submit_order mutator 的验证阶段：治理、风控、保证金检查。

    Returns state if order should be rejected (early return), or None to continue.
    如果订单应被拒绝则返回 state（提前返回），否则返回 None 以继续。
    """
    sess = state["session"]

    # Transition: created → submitted
    _transition_order(order, ORDER_STATE_SUBMITTED, oms_sm=_oms)

    # Governance Hub authorization check (H0 gate) / 治理集線器授權檢查（H0 门）
    # P0-1 FIX: GovernanceHub=None → fail-closed REJECT (DOC-01 §5.6)
    # GovernanceHub 为 None → fail-closed 拒绝
    if engine._governance_hub is None:
        logger.error(
            "governance_hub is None — fail-closed REJECT: %s %s",
            symbol, side
        )
        _transition_order(order, ORDER_STATE_REJECTED, oms_sm=_oms)
        order["reject_reason"] = "governance_hub_unavailable"
        state["orders"].append(order)
        result["order"] = order
        result["rejected_reason"] = "governance_hub_unavailable"
        engine._audit(state, "order_governance_rejected",
                    f"{symbol} {side} governance_hub unavailable — fail-closed")
        return state

    if engine._governance_hub:
        try:
            if not engine._governance_hub.is_authorized():
                _transition_order(order, ORDER_STATE_REJECTED, oms_sm=_oms)
                order["reject_reason"] = "governance_not_authorized"
                state["orders"].append(order)
                result["order"] = order
                result["rejected_reason"] = "governance_not_authorized"
                engine._audit(state, "order_governance_rejected", f"{symbol} {side} not authorized by governance")
                return state
        except Exception as exc:
            _transition_order(order, ORDER_STATE_REJECTED, oms_sm=_oms)
            order["reject_reason"] = "governance_check_error"
            state["orders"].append(order)
            result["order"] = order
            result["rejected_reason"] = "governance_check_error"
            engine._audit(state, "order_governance_error",
                        f"{symbol} {side} governance error: {exc} — fail-closed")
            return state

    # Risk manager pre-order check / 风控管理器下单前检查
    if engine.risk_manager:
        price_est = price or (market_prices or {}).get(symbol, 0)
        allowed, reason = engine.risk_manager.check_order_allowed(
            state, symbol, side, qty, price_est, leverage,
            category=category,
            market_prices=market_prices,
        )
        if not allowed:
            _transition_order(order, ORDER_STATE_REJECTED, oms_sm=_oms)
            order["reject_reason"] = reason
            state["orders"].append(order)
            result["order"] = order
            result["rejected_reason"] = reason
            engine._audit(state, "order_risk_rejected", f"{symbol} {side} qty={qty} reason={reason}")
            return state

    # Pre-trade risk check: sufficient balance for margin + fees?
    # 开仓前风控：余额是否足够覆盖保证金 + 手续费？
    price_estimate = price or (market_prices or {}).get(symbol, 0)
    notional = qty * price_estimate
    # SPOT-3 FIX: 现货品类不使用杠杆保证金，名义价值即所需保证金（全额）
    if category == CATEGORY_SPOT:
        required_margin = notional
    else:
        required_margin = notional / leverage if leverage > 0 else notional
    estimated_fee = compute_fee(qty, price_estimate)
    required_total = required_margin + estimated_fee
    if sess["current_paper_balance_usdt"] < required_total:
        _transition_order(order, ORDER_STATE_REJECTED, oms_sm=_oms)
        order["reject_reason"] = "insufficient_margin"
        state["orders"].append(order)
        result["order"] = order
        result["rejected_reason"] = "insufficient_margin"
        engine._audit(state, "order_rejected", f"{symbol} {side} qty={qty} reason=insufficient_margin need={required_total:.2f} have={sess['current_paper_balance_usdt']:.2f}")
        return state

    # Check session halted / 检查 session 是否已熔断
    if sess.get("session_halted"):
        _transition_order(order, ORDER_STATE_REJECTED, oms_sm=_oms)
        order["reject_reason"] = "session_halted"
        state["orders"].append(order)
        result["order"] = order
        result["rejected_reason"] = "session_halted"
        engine._audit(state, "order_rejected", f"{symbol} {side} reason=session_halted")
        return state

    # Governance Hub lease acquisition / 治理集線器租約獲取（在進入 WORKING 前檢查）
    if engine._governance_hub:
        try:
            lease_id = engine._governance_hub.acquire_lease(order["order_id"], scope={"symbol": symbol, "side": side})
            if not lease_id:
                _transition_order(order, ORDER_STATE_REJECTED, oms_sm=_oms)
                order["reject_reason"] = "governance_lease_denied"
                state["orders"].append(order)
                result["order"] = order
                result["rejected_reason"] = "governance_lease_denied"
                engine._audit(state, "order_governance_lease_denied",
                            f"{symbol} {side} lease denied — fail-closed")
                return state
            order["governance_lease_id"] = lease_id
            engine._audit(state, "governance_lease_acquired",
                        f"{order['order_id']} lease={lease_id}")

            # TTL close-loop: verify the lease has not expired (TOCTOU guard)
            lease_obj = engine._governance_hub.get_lease(lease_id)
            if lease_obj is not None and not lease_obj.is_within_valid_window:
                engine._governance_hub.drive_lease_expiry()
                _transition_order(order, ORDER_STATE_REJECTED, oms_sm=_oms)
                order["reject_reason"] = "governance_lease_expired"
                state["orders"].append(order)
                result["order"] = order
                result["rejected_reason"] = "governance_lease_expired"
                engine._audit(state, "order_governance_lease_expired",
                            f"{symbol} {side} lease={lease_id} expired before execution — fail-closed")
                return state
        except Exception as exc:
            _transition_order(order, ORDER_STATE_REJECTED, oms_sm=_oms)
            order["reject_reason"] = "governance_lease_error"
            state["orders"].append(order)
            result["order"] = order
            result["rejected_reason"] = "governance_lease_error"
            engine._audit(state, "order_governance_lease_error",
                        f"{symbol} {side} lease error: {exc} — fail-closed")
            return state

    # Validation passed — return None to signal continuation
    return None


def _mutator_execute_order(
    state: dict,
    result: dict,
    order: dict,
    symbol: str,
    side: str,
    qty: float,
    price: float | None,
    leverage: float,
    order_type: str,
    time_in_force: str,
    category: str,
    market_prices: dict[str, float] | None,
    engine: "PaperTradingEngine",
    _oms: Any,
) -> dict | None:
    """
    Execution phase of submit_order mutator: TIF enforcement, fills, position updates.
    submit_order mutator 的执行阶段：TIF 执行、成交、持仓更新。

    Returns state for early return, or None to continue to post-execution.
    提前返回时返回 state，否则返回 None 继续后续处理。
    """
    sess = state["session"]

    # Transition: submitted → working
    _transition_order(order, ORDER_STATE_WORKING, oms_sm=_oms)
    state["orders"].append(order)
    result["order"] = order
    engine._audit(state, "order_submitted", f"{order['order_id']} {symbol} {side} {order_type} qty={qty}")

    # TIF enforcement for limit orders / 限价单 TIF 执行
    if order_type == ORDER_TYPE_LIMIT and market_prices and symbol in market_prices:
        mp = market_prices[symbol]
        would_fill = should_fill_limit_order(order, mp)

        if time_in_force == TIF_POST_ONLY and would_fill:
            _transition_order(order, ORDER_STATE_CANCELED, oms_sm=_oms)
            order["cancel_reason"] = "post_only_would_fill"
            result["order"] = order
            result["rejected_reason"] = "post_only_would_fill"
            engine._audit(state, "order_post_only_canceled", f"{symbol} {side} limit would fill immediately")
            return state

        if time_in_force == TIF_FOK:
            if would_fill:
                fill_price = compute_fill_price(order, mp, slippage_rate=engine._get_slippage(symbol))
                fee = compute_fee(qty, fill_price, is_taker=False)
                fill_record = execute_fill(order, qty, fill_price, fee)
                state["fills"].append(fill_record)
                result["fills"].append(fill_record)
                _, close_pnl = project_position_after_fill(state["positions"], symbol, side, qty, fill_price)
                state["pnl"]["closed_position_pnl"] += close_pnl
                result["close_pnl"] += close_pnl
                sess["current_paper_balance_usdt"] = project_balance_after_fill(
                    sess["current_paper_balance_usdt"], side, qty, fill_price, fee, leverage
                )
                # Create protective order for newly opened position
                if engine._protective_order_manager and symbol in state["positions"]:
                    try:
                        from .protective_order_manager import ProtectiveOrderSide, ProtectiveOrderType
                        if side == SIDE_BUY:
                            pom_side = ProtectiveOrderSide.LONG_POSITION
                        else:
                            pom_side = ProtectiveOrderSide.SHORT_POSITION
                        engine._protective_order_manager.create_protective_order(
                            symbol=symbol,
                            side=pom_side,
                            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
                            entry_price=fill_price,
                            trigger_price_pct=2.0,
                            quantity=qty,
                        )
                        engine._audit(state, "protective_order_created", f"{symbol} {side} qty={qty}")
                    except Exception as e:
                        logger.error("Failed to create protective order: %s (non-fatal for paper)", e)
                engine._audit(state, "fok_filled", f"{order['order_id']} price={fill_price:.4f}")
            else:
                _transition_order(order, ORDER_STATE_CANCELED, oms_sm=_oms)
                order["cancel_reason"] = "fok_not_fillable"
                engine._audit(state, "fok_canceled", f"{order['order_id']} price not crossed")
            return state

        if time_in_force == TIF_IOC:
            if would_fill:
                fill_price = compute_fill_price(order, mp, slippage_rate=engine._get_slippage(symbol))
                fee = compute_fee(qty, fill_price, is_taker=False)
                fill_record = execute_fill(order, qty, fill_price, fee)
                state["fills"].append(fill_record)
                result["fills"].append(fill_record)
                _, close_pnl = project_position_after_fill(state["positions"], symbol, side, qty, fill_price)
                state["pnl"]["closed_position_pnl"] += close_pnl
                result["close_pnl"] += close_pnl
                sess["current_paper_balance_usdt"] = project_balance_after_fill(
                    sess["current_paper_balance_usdt"], side, qty, fill_price, fee, leverage
                )
                # Create protective order for newly opened position
                if engine._protective_order_manager and symbol in state["positions"]:
                    try:
                        from .protective_order_manager import ProtectiveOrderSide, ProtectiveOrderType
                        if side == SIDE_BUY:
                            pom_side = ProtectiveOrderSide.LONG_POSITION
                        else:
                            pom_side = ProtectiveOrderSide.SHORT_POSITION
                        engine._protective_order_manager.create_protective_order(
                            symbol=symbol,
                            side=pom_side,
                            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
                            entry_price=fill_price,
                            trigger_price_pct=2.0,
                            quantity=qty,
                        )
                        engine._audit(state, "protective_order_created", f"{symbol} {side} qty={qty}")
                    except Exception as e:
                        logger.error("Failed to create protective order: %s (non-fatal for paper)", e)
                engine._audit(state, "ioc_filled", f"{order['order_id']} price={fill_price:.4f}")
            else:
                _transition_order(order, ORDER_STATE_CANCELED, oms_sm=_oms)
                order["cancel_reason"] = "ioc_not_fillable"
                engine._audit(state, "ioc_canceled", f"{order['order_id']} price not crossed")
            return state

    # For market orders: immediate fill (dynamic slippage per symbol)
    # 市場單立即成交（依幣種動態滑點）
    if order_type == ORDER_TYPE_MARKET and market_prices and symbol in market_prices:
        mp = market_prices[symbol]
        fill_price = compute_fill_price(order, mp, slippage_rate=engine._get_slippage(symbol))
        fee = compute_fee(qty, fill_price, is_taker=True)
        fill_record = execute_fill(order, qty, fill_price, fee)
        state["fills"].append(fill_record)
        result["fills"].append(fill_record)

        # Governance Hub lease release / 治理集線器租約釋放
        if engine._governance_hub and "governance_lease_id" in order:
            try:
                engine._governance_hub.release_lease(order["governance_lease_id"], consumed=True)
                engine._audit(state, "governance_lease_released", f"{order['order_id']} consumed=true")
            except Exception:
                import logging as _log
                _log.warning("Governance lease release failed (non-fatal) / 租約釋放失敗（非致命）")

        # Update position (pass category + strategy_name so new positions record their source)
        _, close_pnl = project_position_after_fill(state["positions"], symbol, side, qty, fill_price, category=category, strategy_name=order.get("strategy_name", ""))
        state["pnl"]["closed_position_pnl"] += close_pnl
        result["close_pnl"] += close_pnl

        # Create protective order for newly opened position
        if engine._protective_order_manager and symbol in state["positions"]:
            try:
                from .protective_order_manager import ProtectiveOrderSide, ProtectiveOrderType
                if side == SIDE_BUY:
                    pom_side = ProtectiveOrderSide.LONG_POSITION
                else:
                    pom_side = ProtectiveOrderSide.SHORT_POSITION
                engine._protective_order_manager.create_protective_order(
                    symbol=symbol,
                    side=pom_side,
                    order_type=ProtectiveOrderType.HARD_STOP_LOSS,
                    entry_price=fill_price,
                    trigger_price_pct=2.0,  # 2% below entry
                    quantity=qty,
                )
                engine._audit(state, "protective_order_created", f"{symbol} {side} qty={qty}")
            except Exception as e:
                logger.error("Failed to create protective order: %s (non-fatal for paper)", e)

        # Update balance
        sess["current_paper_balance_usdt"] = project_balance_after_fill(
            sess["current_paper_balance_usdt"], side, qty, fill_price, fee, leverage
        )

        # Update PnL
        engine._recompute_pnl(state)
        engine._audit(state, "order_filled", f"{order['order_id']} price={fill_price:.4f} fee={fee:.6f}")

        # Batch 10: OMS SM-03 post-fill reconciliation (FILLED→RECONCILING→COMPLETED)
        _oms_complete_reconciliation(order, _oms)

    # C2 fix: If market order could not be filled immediately (no market price), reject it
    if order_type == ORDER_TYPE_MARKET and order["state"] == ORDER_STATE_WORKING:
        _transition_order(order, ORDER_STATE_REJECTED, oms_sm=_oms)
        order["reject_reason"] = "no_market_price"
        result["order"] = order
        result["rejected_reason"] = "no_market_price"
        engine._audit(state, "order_rejected", f"{symbol} {side} market order: no market price available")
        return state

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# tick mutator sub-functions (module-level, called by mutator closure)
# tick mutator 子函数（模块级别，由 mutator 闭包调用）
# ═══════════════════════════════════════════════════════════════════════════════


def _mutator_tick_update_prices(
    state: dict,
    market_prices: dict[str, float],
    engine: "PaperTradingEngine",
) -> None:
    """
    Update unrealized PnL from current market prices.
    从当前市价更新未实现 PnL。
    """
    update_unrealized_pnl(state["positions"], market_prices)
    engine._recompute_pnl(state)


def _mutator_tick_check_fills(
    state: dict,
    tick_result: dict,
    market_prices: dict[str, float],
    engine: "PaperTradingEngine",
) -> None:
    """
    Check conditional triggers and limit order fills against current market prices.
    检查条件单触发和限价单成交（对比当前市价）。
    """
    sess = state["session"]

    for order in state["orders"]:
        if order["state"] not in ACTIVE_STATES:
            continue

        symbol = order["symbol"]
        mp = market_prices.get(symbol)
        if mp is None:
            continue
        otype = order["order_type"]

        # ── Conditional order trigger check / 条件单触发检查 ──
        if otype == ORDER_TYPE_CONDITIONAL and not order.get("triggered"):
            tp = order.get("trigger_price")
            if tp is not None:
                triggered = False
                if order["side"] == SIDE_BUY and mp >= tp:
                    triggered = True
                elif order["side"] == SIDE_SELL and mp <= tp:
                    triggered = True
                if triggered:
                    order["triggered"] = True
                    fill_qty = order["remaining_qty"]
                    fill_price = compute_fill_price(
                        {**order, "order_type": ORDER_TYPE_MARKET}, mp,
                        slippage_rate=engine._get_slippage(symbol),
                    )
                    fee = compute_fee(fill_qty, fill_price, is_taker=True)
                    fill_record = execute_fill(order, fill_qty, fill_price, fee)
                    state["fills"].append(fill_record)
                    tick_result["fills"].append(fill_record)
                    tick_result["orders_filled"] += 1
                    _, close_pnl = project_position_after_fill(
                        state["positions"], symbol, order["side"], fill_qty, fill_price
                    )
                    state["pnl"]["closed_position_pnl"] += close_pnl
                    sess["current_paper_balance_usdt"] = project_balance_after_fill(
                        sess["current_paper_balance_usdt"], order["side"],
                        fill_qty, fill_price, fee, order.get("leverage", 1.0)
                    )
                    engine._audit(state, "conditional_triggered", f"{order['order_id']} trigger={tp} market={mp:.2f}")
                    if engine.risk_manager and close_pnl != 0:
                        engine.risk_manager.record_fill_result(close_pnl)
                        engine.risk_manager.clear_trailing_stop(symbol)
            continue

        # ── Limit order fill check / 限价单成交检查 ──
        if otype == ORDER_TYPE_LIMIT and should_fill_limit_order(order, mp):
            fill_qty = compute_partial_fill_qty(order, mp, rng=engine._partial_fill_rng)
            fill_price = compute_fill_price(order, mp, slippage_rate=engine._get_slippage(symbol))
            fee = compute_fee(fill_qty, fill_price, is_taker=False)
            fill_record = execute_fill(order, fill_qty, fill_price, fee)
            state["fills"].append(fill_record)
            tick_result["fills"].append(fill_record)
            tick_result["orders_filled"] += 1

            _, close_pnl = project_position_after_fill(
                state["positions"], symbol, order["side"], fill_qty, fill_price
            )
            state["pnl"]["closed_position_pnl"] += close_pnl
            sess["current_paper_balance_usdt"] = project_balance_after_fill(
                sess["current_paper_balance_usdt"], order["side"],
                fill_qty, fill_price, fee, order.get("leverage", 1.0)
            )
            engine._audit(state, "limit_fill", f"{order['order_id']} price={fill_price:.4f}")
            if engine.risk_manager and close_pnl != 0:
                engine.risk_manager.record_fill_result(close_pnl)
                if symbol not in state["positions"]:
                    engine.risk_manager.clear_trailing_stop(symbol)


def _mutator_tick_check_stops(
    state: dict,
    tick_result: dict,
    market_prices: dict[str, float],
    engine: "PaperTradingEngine",
) -> None:
    """
    Check order-level TP/SL, auto-cancel stale orders, risk manager tick checks,
    session drawdown circuit breaker, protective orders, reconciliation flag.
    检查订单级止盈止损、自动取消过期订单、风控 tick 检查、
    session 回撤熔断、保护性订单、对账标记。
    """
    sess = state["session"]

    # ── Order-level TP/SL check / 订单级止盈止损检查 ──
    for order in state["orders"]:
        if order["state"] not in TERMINAL_STATES:
            continue
        if order["state"] != ORDER_STATE_FILLED:
            continue
        tp_sl = order.get("tp_sl")
        if not tp_sl or tp_sl.get("_triggered"):
            continue
        symbol = order["symbol"]
        pos = state["positions"].get(symbol)
        if not pos:
            continue
        mp = market_prices.get(symbol)
        if mp is None:
            continue

        tp_price = tp_sl.get("take_profit")
        sl_price = tp_sl.get("stop_loss")
        triggered_reason = None

        if tp_price is not None:
            if (pos["side"] == SIDE_BUY and mp >= tp_price) or \
               (pos["side"] == SIDE_SELL and mp <= tp_price):
                triggered_reason = f"order_tp_{tp_price}"

        if sl_price is not None and triggered_reason is None:
            if (pos["side"] == SIDE_BUY and mp <= sl_price) or \
               (pos["side"] == SIDE_SELL and mp >= sl_price):
                triggered_reason = f"order_sl_{sl_price}"

        if triggered_reason:
            tp_sl["_triggered"] = True
            close_side = SIDE_SELL if pos["side"] == SIDE_BUY else SIDE_BUY
            close_qty = pos["qty"]
            _slip = engine._get_slippage(symbol)
            fp = mp * (1 + _slip) if close_side == SIDE_BUY else mp * (1 - _slip)
            fee = compute_fee(close_qty, fp, is_taker=True)
            close_order = create_paper_order(symbol, close_side, ORDER_TYPE_MARKET, close_qty)
            _transition_order(close_order, ORDER_STATE_SUBMITTED)
            _transition_order(close_order, ORDER_STATE_WORKING)
            fill_record = execute_fill(close_order, close_qty, fp, fee)
            state["orders"].append(close_order)
            state["fills"].append(fill_record)
            tick_result["fills"].append(fill_record)
            _, close_pnl = project_position_after_fill(
                state["positions"], symbol, close_side, close_qty, fp
            )
            state["pnl"]["closed_position_pnl"] += close_pnl
            sess["current_paper_balance_usdt"] = project_balance_after_fill(
                sess["current_paper_balance_usdt"], close_side, close_qty, fp, fee, 1.0
            )
            engine._audit(state, "tp_sl_triggered", f"{order['order_id']} {triggered_reason}")
            if engine.risk_manager:
                engine.risk_manager.record_fill_result(close_pnl)
                engine.risk_manager.clear_trailing_stop(symbol)
            engine._sync_close_to_demo(symbol, close_side, close_qty, f"tp_sl:{triggered_reason}")

    # Auto-cancel stale working orders (TTL: 24 hours)
    now_ms_val = now_ms()
    ORDER_TTL_MS = 86_400_000
    for order in state.get("orders", []):
        if order.get("state") in ACTIVE_STATES:
            created = order.get("created_ts_ms", 0)
            if created > 0 and (now_ms_val - created) > ORDER_TTL_MS:
                _transition_order(order, ORDER_STATE_CANCELED)
                order["cancel_reason"] = "ttl_expired"
                engine._audit(state, "order_ttl_canceled", f"{order.get('symbol')} {order.get('side')} order expired after 24h")

    # Risk manager tick checks / 风控管理器 tick 检查
    if engine.risk_manager:
        engine.risk_manager.record_market_prices_for_portfolio_risk(market_prices)
        close_orders = engine.risk_manager.check_positions_on_tick(state, market_prices)
        for co in close_orders:
            sym = co["symbol"]
            pos = state["positions"].get(sym)
            if not pos:
                continue
            close_side = SIDE_SELL if pos["side"] == SIDE_BUY else SIDE_BUY
            close_qty = co.get("qty", pos["qty"])
            mp = market_prices.get(sym)
            if mp is None:
                continue
            _slip = engine._get_slippage(sym)
            if close_side == SIDE_BUY:
                fp = mp * (1 + _slip)
            else:
                fp = mp * (1 - _slip)
            fee = compute_fee(close_qty, fp, is_taker=True)
            close_order = create_paper_order(sym, close_side, ORDER_TYPE_MARKET, close_qty)
            _transition_order(close_order, ORDER_STATE_SUBMITTED)
            _transition_order(close_order, ORDER_STATE_WORKING)
            fill_record = execute_fill(close_order, close_qty, fp, fee)
            state["orders"].append(close_order)
            state["fills"].append(fill_record)
            tick_result["fills"].append(fill_record)
            _, close_pnl = project_position_after_fill(
                state["positions"], sym, close_side, close_qty, fp
            )
            state["pnl"]["closed_position_pnl"] += close_pnl
            sess["current_paper_balance_usdt"] = project_balance_after_fill(
                sess["current_paper_balance_usdt"], close_side, close_qty, fp, fee, 1.0
            )
            engine._audit(state, "risk_auto_close", f"{sym} reason={co['reason']}")
            engine.risk_manager.record_fill_result(close_pnl)
            engine.risk_manager.clear_trailing_stop(sym)
            engine._sync_close_to_demo(sym, close_side, close_qty, f"risk_auto_close:{co['reason']}")

        # T3.03: Check protective orders on tick (last line of defense)
        if engine._protective_order_manager:
            try:
                market_state = {sym: {"price": p} for sym, p in market_prices.items()}
                pom_result = engine._protective_order_manager.check_triggers(market_state)
                if pom_result and pom_result.triggered_orders:
                    for trig_order in pom_result.triggered_orders:
                        engine._audit(state, "protective_order_triggered",
                            f"{trig_order.symbol} type={trig_order.order_type.value} trigger_price={trig_order.trigger_price}")
            except Exception as e:
                logger.error("ProtectiveOrderManager check_triggers error: %s (non-fatal)", e)

        # T7.04: Periodic reconciliation flag (actual HTTP runs OUTSIDE mutator)
        if engine._governance_hub:
            now_ms_recon = now_ms()
            last_recon = getattr(engine, '_last_reconciliation_ms', 0)
            if now_ms_recon - last_recon >= 60_000:
                tick_result["_needs_reconciliation"] = True
                engine._last_reconciliation_ms = now_ms_recon

        # Session drawdown circuit breaker
        peak = sess.get("peak_balance_usdt", sess.get("initial_paper_balance_usdt", 0))
        current = sess.get("current_paper_balance_usdt", 0)
        if peak > 0:
            dd_pct = ((peak - current) / peak) * 100
            if dd_pct >= engine.risk_manager.config.max_session_drawdown_pct:
                if not sess.get("session_halted"):
                    sess["session_halted"] = True
                    sess["session_halt_reason"] = f"max_drawdown_{dd_pct:.1f}pct"
                    engine._audit(state, "session_halted", f"drawdown={dd_pct:.1f}%")
                    if engine._change_audit_log:
                        try:
                            from .change_audit_log import ChangeType
                            engine._change_audit_log.record_change(
                                change_type=ChangeType.STATE_CHANGE,
                                who="system",
                                what="Session halted due to drawdown limit exceeded",
                                reason=f"Drawdown {dd_pct:.1f}% exceeded limit {engine.risk_manager.config.max_session_drawdown_pct:.1f}%",
                                new_value={"session_halted": True, "halt_reason": sess["session_halt_reason"]},
                                affected_components=["PaperTradingEngine", "RiskManager"],
                                auto_approve=True,
                            )
                        except Exception as e:
                            logger.error("Failed to record session halt in audit log: %s (non-fatal)", e)

        # Re-recompute PnL after risk closes
        if close_orders:
            engine._recompute_pnl(state)

        # Persist risk state
        state["risk"] = engine.risk_manager.get_risk_state_for_persistence()


# ═══════════════════════════════════════════════════════════════════════════════
# Paper Trading Session Manager / 纸上交易 Session 管理器
# ═══════════════════════════════════════════════════════════════════════════════

class PaperTradingEngine:
    """
    Top-level paper trading engine / 纸上交易引擎顶层管理器

    Coordinates: session lifecycle, order management, fill simulation, PnL tracking.
    协调：session 生命周期、订单管理、成交模拟、PnL 跟踪。

    Safety invariant: never imports or calls any Bybit API client.
    安全不变量：绝不 import 或调用任何 Bybit API client。
    """

    def __init__(self, store: PaperStateStore, risk_manager: Any = None, *, partial_fill_rng: Any = None) -> None:
        self.store = store
        self.risk_manager = risk_manager  # Optional RiskManager for pre-order + tick checks
        self._partial_fill_rng = partial_fill_rng  # Pass random.Random(seed) for deterministic tests
        self._governance_hub = None  # Optional GovernanceHub for governance integration
        self._protective_order_manager = None  # Optional ProtectiveOrderManager for local triggers
        self._change_audit_log = None  # Optional ChangeAuditLog for audit trail
        self._last_reconciliation_ms = 0  # T4.01: Track last periodic reconciliation time
        self._demo_connector = None  # T7.01: Optional BybitDemoConnector for demo API integration
        self._demo_sync = None  # T7.04: Optional BybitDemoSync for demo state snapshots
        self._learning_tier_gate = None  # T9A.01: Optional LearningTierGate for analyst agent evolution
        self._oms_sm = None  # Batch 10: Optional OMS State Machine (SM-03) for 11-state lifecycle
        # Dynamic slippage cache: symbol → slippage rate (updated from WS volume data)
        # 動態滑點緩存：幣種 → 滑點率（由 WS 成交量數據更新）
        self._slippage_cache: dict[str, float] = {}

    def _read(self) -> dict[str, Any]:
        return self.store.read()

    def get_state(self) -> dict[str, Any]:
        """
        Public read-only access to current paper state.
        公开的只读状态访问接口，供外部模块使用（替代直接访问 _read()）。
        """
        return self.store.read()

    def _audit(self, state: dict, action: str, detail: str = "") -> None:
        state["audit_trail"].append({
            "action": action,
            "detail": detail,
            "ts_ms": now_ms(),
        })
        # Cap audit trail at 500 entries
        if len(state["audit_trail"]) > 500:
            state["audit_trail"] = state["audit_trail"][-500:]

    def update_slippage_cache(self, symbol_volumes: dict[str, float]) -> None:
        """
        Update per-symbol slippage rates from volume data.
        從成交量數據更新各幣種的動態滑點率。

        Called by PipelineBridge on_tick with WS volume_24h data.
        由 PipelineBridge 在 on_tick 中傳入 WS 的 volume_24h 數據。
        """
        for symbol, vol in symbol_volumes.items():
            self._slippage_cache[symbol] = compute_dynamic_slippage(vol)

    def _get_slippage(self, symbol: str) -> float:
        """
        Get slippage rate for a symbol (falls back to DEFAULT_SLIPPAGE_RATE).
        獲取幣種的滑點率（無數據時回退到默認值）。
        """
        return self._slippage_cache.get(symbol, DEFAULT_SLIPPAGE_RATE)

    def set_governance_hub(self, hub: Any) -> None:
        """Inject GovernanceHub for governance state machine integration / 注入治理集線器"""
        self._governance_hub = hub

    def set_change_audit_log(self, cal: Any) -> None:
        """Inject ChangeAuditLog for audit trail tracking / 注入变更审计日志"""
        self._change_audit_log = cal

    def set_protective_order_manager(self, pom: Any) -> None:
        """Inject ProtectiveOrderManager for automatic stop-loss / 注入保護性訂單管理器"""
        self._protective_order_manager = pom

    def set_demo_connector(self, connector: Any) -> None:
        """Inject BybitDemoConnector for demo API integration / 注入 Demo 连接器"""
        self._demo_connector = connector

    def _sync_close_to_demo(self, symbol: str, close_side: str, close_qty: float, reason: str) -> None:
        """
        Sync a Paper-internal close (risk_auto_close / tp_sl) to Bybit Demo.
        將 Paper 引擎內部平倉同步到 Bybit Demo。

        Paper Engine has internal close paths that bypass PipelineBridge:
        - RiskManager.check_positions_on_tick() → risk_auto_close
        - TP/SL trigger on filled orders → tp_sl_triggered
        This helper ensures Demo mirrors Paper's position changes.
        此方法確保 Demo 與 Paper 的持倉變化保持同步。

        Non-fatal: Demo failure does not block Paper close (fail-open for local safety).
        非致命：Demo 失敗不阻塞 Paper 平倉（本地安全優先）。
        """
        if not self._demo_connector or not self._demo_connector.is_enabled:
            return
        try:
            from .bybit_demo_connector import round_qty_for_exchange
            demo_qty = round_qty_for_exchange(close_qty)
            if demo_qty <= 0:
                return
            result = self._demo_connector.submit_order(
                symbol=symbol, side=close_side, order_type="Market",
                qty=demo_qty, reduce_only=True,
            )
            if result.get("retCode") == 0:
                logger.info(
                    "Demo close synced (%s): %s %s qty=%.6f / Demo 平倉已同步",
                    reason, symbol, close_side, demo_qty,
                )
            else:
                logger.warning(
                    "Demo close FAILED (%s): %s reason=%s — Paper/Demo DIVERGED / "
                    "Demo 平倉失敗，數據已分歧",
                    reason, symbol, result.get("retMsg"),
                )
        except Exception as e:
            logger.warning(
                "Demo close error (%s): %s %s (non-fatal) / Demo 平倉異常",
                reason, symbol, e,
            )

    def _close_all_demo_positions(self, paper_positions: dict[str, Any]) -> None:
        """
        Close all Demo positions when engine stops.
        引擎停止時平掉 Demo 所有倉位。

        Two-pass approach: first close positions known to Paper, then query Demo
        API for any remaining diverged positions and close those too.
        雙遍歷：先根據 Paper 持倉平，再查 Demo API 平殘留倉位。
        """
        closed_symbols: set[str] = set()

        # Pass 1: Close positions known to Paper (use stored category for correct routing)
        # 第一遍：根據 Paper 持倉平倉，使用記錄的 category 確保路由正確
        for symbol, pos in paper_positions.items():
            pos_side = pos.get("side", "Buy")
            close_side = "Sell" if pos_side == "Buy" else "Buy"
            qty = pos.get("qty", 0)
            cat = pos.get("category", "linear")  # Use stored category, default linear
            if qty <= 0:
                continue
            try:
                from .bybit_demo_connector import round_qty_for_exchange
                demo_qty = round_qty_for_exchange(qty, category=cat)
                if demo_qty <= 0:
                    continue
                # Spot cannot use reduce_only (spot has no short concept in Bybit UTA)
                # 現貨不能帶 reduce_only（Bybit UTA 現貨無空倉概念）
                _reduce = cat != "spot"
                result = self._demo_connector.submit_order(
                    symbol=symbol, side=close_side, order_type="Market",
                    qty=demo_qty, category=cat, reduce_only=_reduce,
                )
                if result.get("retCode") == 0:
                    closed_symbols.add(symbol)
                    logger.info("Session stop — Demo closed [%s]: %s %s qty=%s", cat, symbol, close_side, demo_qty)
                else:
                    logger.warning("Session stop — Demo close failed [%s]: %s reason=%s", cat, symbol, result.get("retMsg"))
            except Exception as e:
                logger.warning("Session stop — Demo close error [%s]: %s %s (non-fatal)", cat, symbol, e)

        # Pass 2: Query Demo API for any remaining diverged positions across ALL categories.
        # 第二遍：查詢所有品類的 Demo 倉位，確保 spot/linear/inverse 殘留均被清倉。
        # Spot positions use regular sell (no reduce_only); linear/inverse use reduce_only.
        # 現貨使用普通賣出（無 reduce_only）；線性/反向使用 reduce_only。
        for _cat in ("linear", "spot", "inverse"):
            try:
                demo_positions = self._demo_connector.get_positions(category=_cat)
                pos_list = demo_positions.get("result", {}).get("list", [])
                for dp in pos_list:
                    sym = dp.get("symbol", "")
                    size = float(dp.get("size", 0))
                    if sym in closed_symbols or size <= 0:
                        continue
                    demo_side = dp.get("side", "")
                    close_side = "Buy" if demo_side == "Sell" else "Sell"
                    # Spot: no reduce_only (spot has no short positions, just sell the asset)
                    # 現貨：不帶 reduce_only（現貨只需賣出資產即可）
                    _reduce = _cat != "spot"
                    try:
                        result = self._demo_connector.submit_order(
                            symbol=sym, side=close_side, order_type="Market",
                            qty=size, category=_cat, reduce_only=_reduce,
                        )
                        if result.get("retCode") == 0:
                            closed_symbols.add(sym)
                            logger.info(
                                "Session stop — Demo DIVERGED [%s] closed: %s %s qty=%s",
                                _cat, sym, close_side, size,
                            )
                        else:
                            logger.warning(
                                "Session stop — Demo diverged close failed [%s]: %s reason=%s",
                                _cat, sym, result.get("retMsg"),
                            )
                    except Exception as e:
                        logger.warning("Session stop — Demo diverged close error [%s]: %s %s", _cat, sym, e)
            except Exception as e:
                logger.warning("Session stop — Could not query Demo positions [%s]: %s (non-fatal)", _cat, e)

    def set_demo_sync(self, sync: Any) -> None:
        """Inject BybitDemoSync for demo state snapshots / 注入 Demo 同步器"""
        self._demo_sync = sync

    def set_learning_tier_gate(self, gate: Any) -> None:
        """Inject LearningTierGate for analyst agent evolution / 注入学习等级门控"""
        self._learning_tier_gate = gate

    def set_oms_sm(self, oms_sm: Any) -> None:
        """
        Batch 10: Inject OMS State Machine (SM-03) for 11-state lifecycle enforcement.
        注入 OMS 状态机（SM-03）用于 11 态生命周期强制执行。

        When OMS_SM03_ENABLED=True, every paper order state transition is validated
        against SM-03 and synced to its 11-state lifecycle. If SM-03 rejects a
        transition, the paper engine refuses it too (fail-closed).
        """
        self._oms_sm = oms_sm
        logger.info("OMS SM-03 injected into PaperTradingEngine (enabled=%s)", OMS_SM03_ENABLED)

    def _check_tier_capability(self, capability: str) -> bool:
        """
        T11.02: Check if the current learning tier permits a capability.
        检查当前学习层级是否允许指定能力。

        Returns True if allowed or gate not configured (backward-compatible).
        """
        gate = self._learning_tier_gate
        if gate is None:
            return True
        try:
            method = getattr(gate, capability, None)
            if method is None:
                return True
            return bool(method())
        except Exception:
            return False  # Fail-closed

    # ── Session Management / Session 管理 ──

    def start_session(
        self,
        initial_balance: float = DEFAULT_INITIAL_BALANCE_USDT,
    ) -> dict[str, Any]:
        """Start a new paper trading session / 开始新的纸上交易 session"""
        def mutator(state):
            if state["session"]["session_state"] == SESSION_ACTIVE:
                raise ValueError("Session already active. Stop it before starting a new one.")
            state = build_default_paper_state()
            state["session"]["session_id"] = gen_session_id()
            state["session"]["session_state"] = SESSION_ACTIVE
            state["session"]["started_ts_ms"] = now_ms()
            state["session"]["initial_paper_balance_usdt"] = initial_balance
            state["session"]["current_paper_balance_usdt"] = initial_balance
            state["session"]["peak_balance_usdt"] = initial_balance
            self._audit(state, "session_start", f"balance={initial_balance}")
            # Persist risk manager state / 持久化风控状态
            if self.risk_manager:
                state["risk"] = self.risk_manager.get_risk_state_for_persistence()
            return state
        return self.store.mutate(mutator)

    def pause_session(self) -> dict[str, Any]:
        """Pause the current session / 暂停当前 session"""
        def mutator(state):
            if state["session"]["session_state"] != SESSION_ACTIVE:
                raise ValueError(f"Cannot pause: session is {state['session']['session_state']}")
            state["session"]["session_state"] = SESSION_PAUSED
            state["session"]["paused_ts_ms"] = now_ms()
            self._audit(state, "session_pause")
            return state
        return self.store.mutate(mutator)

    def resume_session(self) -> dict[str, Any]:
        """Resume a paused session / 恢复已暂停的 session"""
        def mutator(state):
            if state["session"]["session_state"] != SESSION_PAUSED:
                raise ValueError(f"Cannot resume: session is {state['session']['session_state']}")
            state["session"]["session_state"] = SESSION_ACTIVE
            state["session"]["paused_ts_ms"] = None
            self._audit(state, "session_resume")
            return state
        return self.store.mutate(mutator)

    def stop_session(self) -> dict[str, Any]:
        """Stop the current session and finalize PnL / 停止 session 并结算 PnL"""
        def mutator(state):
            sess = state["session"]
            if sess["session_state"] not in (SESSION_ACTIVE, SESSION_PAUSED):
                raise ValueError(f"Cannot stop: session is {sess['session_state']}")

            # Cancel all working orders
            for order in state["orders"]:
                if order["state"] in ACTIVE_STATES:
                    _transition_order(order, ORDER_STATE_CANCELED)

            # ── Cancel all Demo orders before closing positions ──
            # 停止引擎時先取消 Demo 所有掛單（普通單+條件止損單），再平倉
            if self._demo_connector and self._demo_connector.is_enabled:
                try:
                    cancel_summary = self._demo_connector.cancel_all_orders()
                    total = cancel_summary.get("regular_canceled", 0) + cancel_summary.get("conditional_canceled", 0)
                    if total > 0:
                        logger.info(
                            "Session stop — Demo orders canceled: %d regular + %d conditional",
                            cancel_summary.get("regular_canceled", 0),
                            cancel_summary.get("conditional_canceled", 0),
                        )
                        self._audit(state, "demo_orders_canceled",
                                    f"regular={cancel_summary.get('regular_canceled', 0)} "
                                    f"conditional={cancel_summary.get('conditional_canceled', 0)}")
                except Exception as e:
                    logger.warning("Session stop — Demo cancel orders error: %s (non-fatal)", e)

                # ── Close all Demo positions ──
                # 平掉 Demo 所有倉位，防止幽靈倉殘留
                self._close_all_demo_positions(state.get("positions", {}))

            # Finalize PnL
            self._recompute_pnl(state)
            sess["session_state"] = SESSION_COMPLETED
            sess["stopped_ts_ms"] = now_ms()
            self._audit(state, "session_stop", f"net_pnl={state['pnl']['net_paper_pnl']:.4f}")

            # T7.04: Governance Hub reconciliation with demo state / 治理集線器對賬
            if self._governance_hub:
                try:
                    paper_snap = _paper_state_to_recon_format(state)
                    demo_snap = None
                    if self._demo_sync:
                        try:
                            demo_snap = self._demo_sync.get_current_snapshot()
                        except Exception as e:
                            logger.error("Demo snapshot failed: %s", e)
                    self._governance_hub.reconcile(paper_snap, demo_state=demo_snap)
                    self._audit(state, "governance_reconciliation", "session_stop reconciliation triggered")
                except Exception:
                    logger.warning("Governance reconciliation failed (non-fatal) / 對賬失敗（非致命）")

            if self.risk_manager:
                state["risk"] = self.risk_manager.get_risk_state_for_persistence()
            return state
        result = self.store.mutate(mutator)
        self.store.flush()  # stop_session: force disk write / 停止會話：強制寫磁碟
        return result

    def get_session_status(self) -> dict[str, Any]:
        """Get current session status / 获取 session 状态"""
        state = self._read()
        return {
            "session": state["session"],
            "pnl": state["pnl"],
            "order_count": len(state["orders"]),
            "active_order_count": len([o for o in state["orders"] if o["state"] in ACTIVE_STATES]),
            "position_count": len(state["positions"]),
            "fill_count": len(state["fills"]),
            "is_simulated": True,
            "data_category": "paper_simulated",
        }

    # ── Order Management / 订单管理 ──

    def submit_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        qty: float,
        price: float | None = None,
        leverage: float = 1.0,
        market_prices: dict[str, float] | None = None,
        *,
        time_in_force: str = TIF_GTC,
        reduce_only: bool = False,
        trigger_price: float | None = None,
        trigger_by: str = TRIGGER_BY_LAST_PRICE,
        take_profit: float | None = None,
        stop_loss: float | None = None,
        category: str = CATEGORY_LINEAR,
        strategy_name: str = "",
    ) -> dict[str, Any]:
        """
        Submit a paper order / 提交纸上订单

        Supports market, limit, conditional orders with optional TP/SL.
        For market orders, immediate fill is attempted if market_prices provided.
        """
        result = {"order": None, "fills": [], "rejected_reason": None, "close_pnl": 0.0}

        # T11.02: LearningTierGate enforcement — order submission requires L3+ (can_auto_deploy_to_paper)
        if not self._check_tier_capability("can_auto_deploy_to_paper"):
            result["rejected_reason"] = "Learning tier too low for autonomous order submission (requires L3+)"
            return result

        def mutator(state):
            """Thin dispatcher: validate → execute → return state.
            薄调度器：验证 → 执行 → 返回 state。"""
            sess = state["session"]
            if sess["session_state"] != SESSION_ACTIVE:
                raise ValueError(f"Cannot submit order: session is {sess['session_state']}")

            order = create_paper_order(
                symbol, side, order_type, qty, price, leverage,
                time_in_force=time_in_force,
                reduce_only=reduce_only,
                trigger_price=trigger_price,
                trigger_by=trigger_by,
                take_profit=take_profit,
                stop_loss=stop_loss,
                category=category,
                strategy_name=strategy_name,
            )

            # Batch 10: Register order in OMS SM-03 if enabled
            _oms = self._oms_sm if (OMS_SM03_ENABLED and getattr(self, '_oms_sm', None)) else None
            if _oms is not None:
                try:
                    oms_order_id = _oms.create_order(
                        symbol=symbol,
                        side=side,
                        order_type=order_type,
                        qty=qty,
                        price=price,
                        created_by="paper_engine",
                        metadata={"paper_engine": True, "leverage": leverage, "paper_order_id": order["order_id"]},
                    )
                    order["oms_order_id"] = oms_order_id
                    order["oms_state"] = "CREATED"
                except Exception as e:
                    logger.error("OMS SM-03 create_order failed: %s — fail-closed", e)
                    order["reject_reason"] = f"oms_create_failed: {e}"
                    order["state"] = ORDER_STATE_REJECTED
                    state["orders"].append(order)
                    result["order"] = order
                    result["rejected_reason"] = f"oms_create_failed: {e}"
                    self._audit(state, "order_oms_create_failed", f"{symbol} {side} OMS error: {e}")
                    return state

            # Phase 1: Validate order (governance, risk, margin)
            # 阶段 1：验证订单（治理、风控、保证金）
            rejected = _mutator_validate_order(
                state, result, order, symbol, side, qty, price, leverage,
                order_type, category, market_prices, self, _oms,
            )
            if rejected is not None:
                return rejected

            # Phase 2: Execute order (TIF enforcement, fills, position updates)
            # 阶段 2：执行订单（TIF 执行、成交、持仓更新）
            early_return = _mutator_execute_order(
                state, result, order, symbol, side, qty, price, leverage,
                order_type, time_in_force, category, market_prices, self, _oms,
            )
            if early_return is not None:
                return early_return

            return state

        self.store.mutate(mutator)
        return result

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        """Cancel a working paper order / 取消 working 状态的纸上订单"""
        result = {"success": False, "reason": ""}

        # T11.02: LearningTierGate enforcement — cancel requires L3+ (same as submit)
        if not self._check_tier_capability("can_auto_deploy_to_paper"):
            result["reason"] = "Learning tier too low for order cancellation (requires L3+)"
            return result

        def mutator(state):
            for order in state["orders"]:
                if order["order_id"] == order_id:
                    if order["state"] not in ACTIVE_STATES:
                        result["reason"] = f"Cannot cancel: order is {order['state']}"
                        return state
                    _transition_order(order, ORDER_STATE_CANCELED)
                    result["success"] = True
                    self._audit(state, "order_canceled", order_id)
                    return state
            result["reason"] = "Order not found"
            return state

        self.store.mutate(mutator)
        return result

    def get_orders(self, state_filter: str | None = None) -> list[dict]:
        """Get all paper orders, optionally filtered by state / 获取纸上订单列表"""
        state = self._read()
        orders = state["orders"]
        if state_filter:
            orders = [o for o in orders if o["state"] == state_filter]
        return orders

    def get_positions(self) -> dict[str, Any]:
        """Get current paper positions / 获取当前纸上持仓"""
        return self._read()["positions"]

    def get_fills(self, limit: int = 50) -> list[dict]:
        """Get fill history / 获取成交历史"""
        state = self._read()
        return state["fills"][-limit:]

    def get_pnl(self) -> dict[str, Any]:
        """Get paper PnL summary / 获取纸上 PnL 汇总"""
        return self._read()["pnl"]

    def get_audit_trail(self, limit: int = 100) -> list[dict]:
        """Get audit trail / 获取审计记录"""
        state = self._read()
        return state["audit_trail"][-limit:]

    # ── Fill Simulation Tick / 成交模拟 Tick ──

    def tick(self, market_prices: dict[str, float]) -> dict[str, Any]:
        """
        Run one fill simulation tick / 执行一次成交模拟 tick

        Checks all working/partially-filled limit orders against current market prices.
        Returns summary of fills executed during this tick.
        """
        tick_result = {"fills": [], "orders_filled": 0, "tick_ts_ms": now_ms()}

        # T11.02: LearningTierGate enforcement — market observation requires L1+ (can_record_observations)
        if not self._check_tier_capability("can_record_observations"):
            return tick_result  # Silent no-op at L0 (gate not yet initialized to L1)

        def mutator(state):
            """Thin dispatcher: check fills → update prices → check stops → return state.
            薄调度器：检查成交 → 更新价格 → 检查止损 → 返回 state。
            Order matches original: fills first, then unrealized PnL update, then risk checks.
            顺序与原始一致：先成交，再更新未实现 PnL，最后风控检查。"""
            sess = state["session"]
            if sess["session_state"] != SESSION_ACTIVE:
                return state

            # Phase 1: Check conditional triggers and limit order fills
            # 阶段 1：检查条件单触发和限价单成交
            _mutator_tick_check_fills(state, tick_result, market_prices, self)

            # Phase 2: Update unrealized PnL from current market prices
            # 阶段 2：从当前市价更新未实现 PnL（必须在风控检查前执行）
            _mutator_tick_update_prices(state, market_prices, self)

            # Phase 3: Check TP/SL, stale orders, risk manager, drawdown breaker
            # 阶段 3：检查止盈止损、过期订单、风控、回撤熔断
            _mutator_tick_check_stops(state, tick_result, market_prices, self)

            return state

        self.store.mutate(mutator)

        # T7.04: Run reconciliation OUTSIDE mutator to avoid holding _lock during HTTP.
        # T7.04：在 mutator 外部執行對賬，避免持鎖時做 HTTP 調用。
        if tick_result.pop("_needs_reconciliation", False):
            import threading as _recon_threading
            def _run_reconciliation():
                try:
                    paper_snap = _paper_state_to_recon_format(self.store.read())
                    demo_snap = None
                    if self._demo_sync:
                        try:
                            demo_snap = self._demo_sync.get_current_snapshot()
                        except Exception as e:
                            logger.error("Demo snapshot failed: %s", e)
                    recon_report = self._governance_hub.reconcile(paper_snap, demo_state=demo_snap)
                    if recon_report.get("ok") is False:
                        logger.warning("Reconciliation warning: %s", recon_report.get("reason", "unknown"))
                except Exception as e:
                    logger.error("Periodic reconciliation error: %s (non-fatal)", e)
            _recon_threading.Thread(target=_run_reconciliation, daemon=True, name="recon-tick").start()

        return tick_result

    # ── PnL Computation / PnL 计算 ──

    def _recompute_pnl(self, state: dict) -> None:
        """Recompute PnL summary from fills and positions / 从成交和持仓重算 PnL"""
        pnl = state["pnl"]

        # Realized PnL = sum of open position realized + fully closed position PnL
        realized = pnl.get("closed_position_pnl", 0.0)
        for pos in state["positions"].values():
            realized += pos.get("realized_pnl", 0.0)
        pnl["realized_pnl"] = realized

        # Unrealized PnL
        unrealized = 0.0
        for pos in state["positions"].values():
            unrealized += pos.get("unrealized_pnl", 0.0)
        pnl["unrealized_pnl"] = unrealized

        # Total fees
        total_fees = sum(f.get("fee", 0.0) for f in state["fills"])
        pnl["total_fees_paid"] = total_fees

        # Net realized PnL (after deducting all fees) / 净实现盈亏（扣除全部手续费）
        pnl["net_realized_pnl"] = realized - total_fees

        # Aggregate AI attention cost from open positions' holding_cost
        # / 从持仓 holding_cost 汇总 AI 注意力成本
        total_ai_cost = sum(
            p.get("holding_cost", {}).get("ai_cost_attributed_usd", 0.0)
            for p in state["positions"].values()
        )
        pnl["total_ai_cost"] = total_ai_cost

        # Net paper PnL
        pnl["net_paper_pnl"] = (
            pnl["realized_pnl"]
            + pnl["unrealized_pnl"]
            - pnl["total_fees_paid"]
            - total_ai_cost
        )

        # Update balance to reflect realized PnL
        initial = state["session"]["initial_paper_balance_usdt"]
        state["session"]["current_paper_balance_usdt"] = (
            initial + pnl["realized_pnl"] - pnl["total_fees_paid"]
        )

        # Track peak balance for drawdown calculation / 跟踪峰值余额（用于回撤计算）
        current = state["session"]["current_paper_balance_usdt"]
        peak = state["session"].get("peak_balance_usdt", initial)
        if current > peak:
            state["session"]["peak_balance_usdt"] = current

        # Cap orders and fills lists to prevent unbounded growth / 限制列表长度防止无限增长
        # Keep terminal orders (filled/canceled/rejected) capped; active orders always kept
        # Note: fills are trimmed to max_fills (2000) independently of orders (500 terminal).
        # This means some orders may reference fill IDs that have been evicted from the fills list.
        # This is acceptable for paper trading; a full audit should use the exported state file.
        # 注意：fills 独立于 orders 裁剪，部分 order 可能引用已被裁剪的 fill_id。
        # 纸上交易可接受；完整审计请使用导出的状态文件。
        max_terminal_orders = 500
        max_fills = 2000
        if len(state["orders"]) > max_terminal_orders + 50:
            active = [o for o in state["orders"] if o.get("state") not in TERMINAL_STATES]
            terminal = [o for o in state["orders"] if o.get("state") in TERMINAL_STATES]
            state["orders"] = active + terminal[-max_terminal_orders:]
        if len(state["fills"]) > max_fills:
            state["fills"] = state["fills"][-max_fills:]

    # ── Data Export / 数据导出 ──

    def export_session(self) -> dict[str, Any]:
        """Export complete session data for analysis / 导出完整 session 数据供分析"""
        state = self._read()
        return {
            "export_ts_ms": now_ms(),
            "session": state["session"],
            "orders": state["orders"],
            "positions": state["positions"],
            "fills": state["fills"],
            "pnl": state["pnl"],
            "shadow_decisions": state.get("shadow_decisions", []),
            "audit_trail": state["audit_trail"],
            "meta": state["meta"],
            "is_simulated": True,
            "data_category": "paper_simulated",
        }
