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

import copy
import hashlib
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
DEFAULT_SLIPPAGE_RATE = 0.0005  # 0.05%

# Default initial paper balance
DEFAULT_INITIAL_BALANCE_USDT = 10000.0


# ═══════════════════════════════════════════════════════════════════════════════
# Utility / 工具函数
# ═══════════════════════════════════════════════════════════════════════════════

def now_ms() -> int:
    return int(time.time() * 1000)


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
        if not self.file_path.exists():
            self.write(build_default_paper_state())

    def read(self) -> dict[str, Any]:
        with self._lock:
            with self.file_path.open("r", encoding="utf-8") as handle:
                return json.load(handle)

    def write(self, state: dict[str, Any]) -> dict[str, Any]:
        import tempfile
        with self._lock:
            state["meta"]["revision"] = state["meta"].get("revision", 0) + 1
            state["meta"]["updated_ts_ms"] = now_ms()
            # Atomic write: write to temp file then rename (crash-safe)
            # 原子写入：先写临时文件再重命名（崩溃安全）
            dir_path = self.file_path.parent
            fd, tmp_path = tempfile.mkstemp(dir=str(dir_path), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(state, handle, ensure_ascii=False, indent=2)
                os.chmod(tmp_path, 0o600)
                os.replace(tmp_path, str(self.file_path))
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            return state

    def mutate(self, mutator) -> dict[str, Any]:
        with self._lock:
            current = self.read()
            mutated = mutator(copy.deepcopy(current))
            return self.write(mutated)


# ═══════════════════════════════════════════════════════════════════════════════
# Paper Order Lifecycle Engine / 纸上订单生命周期引擎
# (Implements K chapter 7-state lifecycle)
# ═══════════════════════════════════════════════════════════════════════════════

def _transition_order(order: dict, new_state: str) -> dict:
    """Validate and execute a state transition on a paper order."""
    current = order["state"]
    valid_next = VALID_TRANSITIONS.get(current, set())
    if new_state not in valid_next:
        raise ValueError(
            f"Invalid transition: {current} → {new_state}. "
            f"Valid targets: {valid_next}"
        )
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
    if order["remaining_qty"] <= 0:
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
) -> tuple[dict[str, Any], float]:
    """
    Project position state after a fill / 投影成交后的持仓状态

    Handles: opening new position, adding to position, reducing position, flipping position.
    Returns: (positions, close_pnl) — close_pnl is realized PnL from closing (0 if opening/adding).
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

    if pos["side"] == side:
        # Same direction: add to position (average up/down)
        total_qty = pos["qty"] + fill_qty
        pos["avg_entry_price"] = (
            (pos["avg_entry_price"] * pos["qty"] + fill_price * fill_qty) / total_qty
        )
        pos["qty"] = total_qty
    else:
        # Opposite direction: reduce or flip
        if fill_qty < pos["qty"]:
            # Partial close
            close_pnl = _compute_close_pnl(pos, fill_qty, fill_price)
            pos["realized_pnl"] += close_pnl
            pos["qty"] -= fill_qty
        elif fill_qty == pos["qty"]:
            # Full close
            close_pnl = _compute_close_pnl(pos, fill_qty, fill_price)
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
    """Compute realized PnL for closing a position / 计算平仓实现盈亏"""
    if pos["side"] == SIDE_BUY:
        return (close_price - pos["avg_entry_price"]) * close_qty
    else:
        return (pos["avg_entry_price"] - close_price) * close_qty


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
    """
    for symbol, pos in positions.items():
        price = market_prices.get(symbol)
        if price is None:
            continue
        if pos["side"] == SIDE_BUY:
            pos["unrealized_pnl"] = (price - pos["avg_entry_price"]) * pos["qty"]
        else:
            pos["unrealized_pnl"] = (pos["avg_entry_price"] - price) * pos["qty"]
        pos["updated_ts_ms"] = now_ms()
    return positions


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

            # Finalize PnL
            self._recompute_pnl(state)
            sess["session_state"] = SESSION_COMPLETED
            sess["stopped_ts_ms"] = now_ms()
            self._audit(state, "session_stop", f"net_pnl={state['pnl']['net_paper_pnl']:.4f}")
            if self.risk_manager:
                state["risk"] = self.risk_manager.get_risk_state_for_persistence()
            return state
        return self.store.mutate(mutator)

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
    ) -> dict[str, Any]:
        """
        Submit a paper order / 提交纸上订单

        Supports market, limit, conditional orders with optional TP/SL.
        For market orders, immediate fill is attempted if market_prices provided.
        """
        result = {"order": None, "fills": [], "rejected_reason": None}

        def mutator(state):
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
            )

            # Transition: created → submitted
            _transition_order(order, ORDER_STATE_SUBMITTED)

            # Risk manager pre-order check / 风控管理器下单前检查
            if self.risk_manager:
                price_est = price or (market_prices or {}).get(symbol, 0)
                allowed, reason = self.risk_manager.check_order_allowed(
                    state, symbol, side, qty, price_est, leverage,
                    category=category,
                    market_prices=market_prices,
                )
                if not allowed:
                    _transition_order(order, ORDER_STATE_REJECTED)
                    order["reject_reason"] = reason
                    state["orders"].append(order)
                    result["order"] = order
                    result["rejected_reason"] = reason
                    self._audit(state, "order_risk_rejected", f"{symbol} {side} qty={qty} reason={reason}")
                    return state

            # Pre-trade risk check: sufficient balance for margin + fees?
            # 开仓前风控：余额是否足够覆盖保证金 + 手续费？
            price_estimate = price or (market_prices or {}).get(symbol, 0)
            notional = qty * price_estimate
            required_margin = notional / leverage if leverage > 0 else notional
            estimated_fee = compute_fee(qty, price_estimate)
            required_total = required_margin + estimated_fee
            if sess["current_paper_balance_usdt"] < required_total:
                _transition_order(order, ORDER_STATE_REJECTED)
                order["reject_reason"] = "insufficient_margin"
                state["orders"].append(order)
                result["order"] = order
                result["rejected_reason"] = "insufficient_margin"
                self._audit(state, "order_rejected", f"{symbol} {side} qty={qty} reason=insufficient_margin need={required_total:.2f} have={sess['current_paper_balance_usdt']:.2f}")
                return state

            # Check session halted / 检查 session 是否已熔断
            if sess.get("session_halted"):
                _transition_order(order, ORDER_STATE_REJECTED)
                order["reject_reason"] = "session_halted"
                state["orders"].append(order)
                result["order"] = order
                result["rejected_reason"] = "session_halted"
                self._audit(state, "order_rejected", f"{symbol} {side} reason=session_halted")
                return state

            # Transition: submitted → working
            _transition_order(order, ORDER_STATE_WORKING)
            state["orders"].append(order)
            result["order"] = order
            self._audit(state, "order_submitted", f"{order['order_id']} {symbol} {side} {order_type} qty={qty}")

            # For market orders: immediate fill
            if order_type == ORDER_TYPE_MARKET and market_prices and symbol in market_prices:
                mp = market_prices[symbol]
                fill_price = compute_fill_price(order, mp)
                fee = compute_fee(qty, fill_price, is_taker=True)
                fill_record = execute_fill(order, qty, fill_price, fee)
                state["fills"].append(fill_record)
                result["fills"].append(fill_record)

                # Update position
                _, close_pnl = project_position_after_fill(state["positions"], symbol, side, qty, fill_price)
                state["pnl"]["closed_position_pnl"] += close_pnl

                # Update balance
                sess["current_paper_balance_usdt"] = project_balance_after_fill(
                    sess["current_paper_balance_usdt"], side, qty, fill_price, fee, leverage
                )

                # Update PnL
                self._recompute_pnl(state)
                self._audit(state, "order_filled", f"{order['order_id']} price={fill_price:.4f} fee={fee:.6f}")

            # C2 fix: If market order could not be filled immediately (no market price), reject it
            # Market orders stuck in WORKING will never fill via tick(), so reject now.
            if order_type == ORDER_TYPE_MARKET and order["state"] == ORDER_STATE_WORKING:
                _transition_order(order, ORDER_STATE_REJECTED)
                order["reject_reason"] = "no_market_price"
                result["order"] = order
                result["rejected_reason"] = "no_market_price"
                self._audit(state, "order_rejected", f"{symbol} {side} market order: no market price available")
                return state

            return state

        self.store.mutate(mutator)
        return result

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        """Cancel a working paper order / 取消 working 状态的纸上订单"""
        result = {"success": False, "reason": ""}

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

        def mutator(state):
            sess = state["session"]
            if sess["session_state"] != SESSION_ACTIVE:
                return state

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
                            # Conditional becomes market fill at trigger
                            fill_qty = order["remaining_qty"]
                            fill_price = compute_fill_price(
                                {**order, "order_type": ORDER_TYPE_MARKET}, mp
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
                            self._audit(state, "conditional_triggered", f"{order['order_id']} trigger={tp} market={mp:.2f}")
                            if self.risk_manager and close_pnl != 0:
                                self.risk_manager.record_fill_result(close_pnl)
                                self.risk_manager.clear_trailing_stop(symbol)
                    continue

                # ── Limit order fill check / 限价单成交检查 ──
                if otype == ORDER_TYPE_LIMIT and should_fill_limit_order(order, mp):
                    fill_qty = compute_partial_fill_qty(order, mp, rng=self._partial_fill_rng)
                    fill_price = compute_fill_price(order, mp)
                    # Resting limit orders are always maker fee / 挂单限价单始终 maker 费率
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
                    self._audit(state, "limit_fill", f"{order['order_id']} price={fill_price:.4f}")
                    if self.risk_manager and close_pnl != 0:
                        self.risk_manager.record_fill_result(close_pnl)
                        if symbol not in state["positions"]:
                            self.risk_manager.clear_trailing_stop(symbol)

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
                    fp = mp * (1 + DEFAULT_SLIPPAGE_RATE) if close_side == SIDE_BUY else mp * (1 - DEFAULT_SLIPPAGE_RATE)
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
                    self._audit(state, "tp_sl_triggered", f"{order['order_id']} {triggered_reason}")
                    if self.risk_manager:
                        self.risk_manager.record_fill_result(close_pnl)
                        self.risk_manager.clear_trailing_stop(symbol)

            # Update unrealized PnL
            update_unrealized_pnl(state["positions"], market_prices)
            self._recompute_pnl(state)

            # Risk manager tick checks / 风控管理器 tick 检查
            if self.risk_manager:
                close_orders = self.risk_manager.check_positions_on_tick(state, market_prices)
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
                    # Market close with slippage
                    if close_side == SIDE_BUY:
                        fp = mp * (1 + DEFAULT_SLIPPAGE_RATE)
                    else:
                        fp = mp * (1 - DEFAULT_SLIPPAGE_RATE)
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
                    self._audit(state, "risk_auto_close", f"{sym} reason={co['reason']}")
                    self.risk_manager.record_fill_result(close_pnl)
                    self.risk_manager.clear_trailing_stop(sym)

                # Session drawdown circuit breaker
                peak = sess.get("peak_balance_usdt", sess.get("initial_paper_balance_usdt", 0))
                current = sess.get("current_paper_balance_usdt", 0)
                if peak > 0:
                    dd_pct = ((peak - current) / peak) * 100
                    if dd_pct >= self.risk_manager.config.max_session_drawdown_pct:
                        if not sess.get("session_halted"):
                            sess["session_halted"] = True
                            sess["session_halt_reason"] = f"max_drawdown_{dd_pct:.1f}pct"
                            self._audit(state, "session_halted", f"drawdown={dd_pct:.1f}%")

                # Re-recompute PnL after risk closes
                if close_orders:
                    self._recompute_pnl(state)

                # Persist risk state
                state["risk"] = self.risk_manager.get_risk_state_for_persistence()

            return state

        self.store.mutate(mutator)
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

        # Net paper PnL
        pnl["net_paper_pnl"] = (
            pnl["realized_pnl"]
            + pnl["unrealized_pnl"]
            - pnl["total_fees_paid"]
            - pnl.get("total_ai_cost", 0.0)
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
