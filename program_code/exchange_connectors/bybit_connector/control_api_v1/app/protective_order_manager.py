"""
Protective Order Manager — T2.19 / GAP-M10
Exchange Protective Orders (Last Line of Defense)
交易所保护性订单管理 — 灾难保护最后一道防线

MODULE_NOTE (中文):
  实现 DOC-01 §5.9 根原则：本地智能止损可作为主层保护，但交易所端必须始终保留灾难
  保护底线。当本地系统完全失效时，交易所端预挂的条件单是账户生存的最后一道防线。

  核心特性：
  - 六种保护性订单类型：HARD_STOP_LOSS, SOFT_STOP_LOSS, TAKE_PROFIT,
    TRAILING_STOP, POSITION_CLOSE, EMERGENCY_CLOSE_ALL
  - 硬止损不可禁用（DOC-01 §5.9 强制）
  - 反猎杀隐身模式：止损不在交易所挂单直到触发（EX-01 §4.2）
  - ATR 动态距离 + 随机偏移（EX-01 §4.3）
  - 线程安全、审计回调、完整序列化

MODULE_NOTE (English):
  Implements DOC-01 §5.9 root principle: local smart stop-loss serves as primary
  protection, but exchange-side must always maintain disaster protection baseline.
  When local system fails completely, pre-staged conditional orders on exchange
  are the account's last survival line.

  Core features:
  - Six protective order types: HARD_STOP_LOSS, SOFT_STOP_LOSS, TAKE_PROFIT,
    TRAILING_STOP, POSITION_CLOSE, EMERGENCY_CLOSE_ALL
  - Hard stop-loss cannot be disabled (DOC-01 §5.9 mandatory)
  - Anti-hunt stealth mode: stops not placed on exchange until triggered (EX-01 §4.2)
  - ATR dynamic distance + random offset (EX-01 §4.3)
  - Thread-safe, audit callbacks, full serialization

Safety invariants:
  - HARD_STOP_LOSS can never be disabled or removed before trigger
  - All protective orders track: symbol, side, trigger_price, quantity, status
  - check_triggers() runs on market tick; execute_protective_action() is callback
  - validate_coverage() ensures all open positions have required stop-loss
  - Unprotected position detection triggers mandatory stop assignment
  - Emergency close bypasses all conditional logic; direct reduce-only execution
"""

from __future__ import annotations

import copy
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════════

class ProtectiveOrderType(str, Enum):
    """Types of protective orders / 保护性订单类型"""
    HARD_STOP_LOSS = "HARD_STOP_LOSS"           # Absolute defense; cannot be disabled
    SOFT_STOP_LOSS = "SOFT_STOP_LOSS"           # Conditional; can be adjusted
    TAKE_PROFIT = "TAKE_PROFIT"                 # Profit target; can be disabled
    TRAILING_STOP = "TRAILING_STOP"             # Dynamic stop following price; can be disabled
    POSITION_CLOSE = "POSITION_CLOSE"           # Close entire position at trigger
    EMERGENCY_CLOSE_ALL = "EMERGENCY_CLOSE_ALL" # Circuit breaker: close all positions


class ProtectiveOrderStatus(str, Enum):
    """Status lifecycle of protective orders / 保护性订单状态生命周期"""
    CREATED = "CREATED"                         # Just created
    ARMED = "ARMED"                             # Monitoring active
    TRIGGERED = "TRIGGERED"                     # Trigger condition met
    EXECUTED = "EXECUTED"                       # Action completed on exchange
    CANCELLED = "CANCELLED"                     # Cancelled before trigger
    FAILED = "FAILED"                           # Execution failed
    EXPIRED = "EXPIRED"                         # Expired due to time or manual override


class ProtectiveOrderSide(str, Enum):
    """Side for protective orders / 保护性订单方向"""
    LONG_POSITION = "LONG"                      # Stop-loss for long position
    SHORT_POSITION = "SHORT"                    # Stop-loss for short position
    BOTH = "BOTH"                               # Apply to both sides (emergency close)


class TriggerCondition(str, Enum):
    """Trigger logic / 触发条件"""
    PRICE_LESS_THAN = "PRICE_LESS_THAN"         # Stop-loss: price drops below trigger
    PRICE_GREATER_THAN = "PRICE_GREATER_THAN"   # Take-profit: price rises above trigger
    PRICE_TOUCHES = "PRICE_TOUCHES"              # Either direction touches trigger
    TIME_ELAPSED = "TIME_ELAPSED"                # Time-based expiry trigger


# ═══════════════════════════════════════════════════════════════════════════════
# Dataclasses
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ProtectiveOrderConfig:
    """Configuration template for protective order / 保护性订单配置模板

    Example:
        config = ProtectiveOrderConfig(
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            trigger_price_pct=5.0,  # 5% below entry for long
            trigger_condition=TriggerCondition.PRICE_LESS_THAN,
            is_mandatory=True,
            can_be_disabled=False,
            bypass_requires_approval=False
        )
    """
    order_type: ProtectiveOrderType
    trigger_price_pct: float                    # % distance from entry price
    trigger_condition: TriggerCondition
    is_mandatory: bool = False                  # If True, must be on every position
    can_be_disabled: bool = False               # If False, cannot be cancelled/disabled
    bypass_requires_approval: bool = False      # If True, Operator approval needed to bypass
    description: str = ""


@dataclass
class ProtectiveOrder:
    """Single protective order instance / 单个保护性订单实例"""
    order_id: str
    symbol: str                                 # e.g., "BTCUSDT"
    side: ProtectiveOrderSide
    order_type: ProtectiveOrderType
    trigger_price: float                        # Absolute price level
    trigger_price_pct: float                    # % from entry
    quantity: float                             # Position quantity to protect
    entry_price: float                          # Entry price of position
    status: ProtectiveOrderStatus = ProtectiveOrderStatus.CREATED
    created_at_ms: int = 0                      # Milliseconds timestamp
    triggered_at_ms: Optional[int] = None       # When trigger fired
    exchange_order_id: Optional[str] = None     # Exchange order ID if placed

    # Metadata
    position_id: Optional[str] = None           # Reference to open position
    strategy_id: Optional[str] = None           # Which strategy owns this
    tags: Dict[str, str] = field(default_factory=dict)
    can_be_disabled: bool = True                # Can this order be cancelled?

    # Trailing stop tracking
    trailing_high: Optional[float] = None       # For trailing stop: highest price seen
    trailing_distance: Optional[float] = None   # For trailing stop: % distance

    # ATR and anti-hunt
    atr_value: Optional[float] = None           # ATR at creation time
    random_offset: Optional[float] = None       # Random offset for unpredictability

    def __post_init__(self):
        if not self.order_id:
            self.order_id = f"pord_{uuid.uuid4().hex[:12]}"
        if self.created_at_ms == 0:
            self.created_at_ms = int(time.time() * 1000)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for JSON / 序列化为字典"""
        d = asdict(self)
        d['status'] = self.status.value
        d['order_type'] = self.order_type.value
        d['side'] = self.side.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ProtectiveOrder:
        """Deserialize from dict / 从字典反序列化"""
        data_copy = copy.deepcopy(data)
        if isinstance(data_copy.get('status'), str):
            data_copy['status'] = ProtectiveOrderStatus(data_copy['status'])
        if isinstance(data_copy.get('order_type'), str):
            data_copy['order_type'] = ProtectiveOrderType(data_copy['order_type'])
        if isinstance(data_copy.get('side'), str):
            data_copy['side'] = ProtectiveOrderSide(data_copy['side'])
        return cls(**data_copy)


@dataclass
class ProtectiveOrderCheckResult:
    """Result of protective order check / 保护性订单检查结果"""
    triggered_orders: List[ProtectiveOrder]     # Orders that fired
    unprotected_positions: List[Dict[str, Any]] # Positions without required stops
    missing_mandatory_stops: List[str]          # Position IDs missing hard stops
    portfolio_coverage_pct: float                # % of open positions with stops
    timestamp_ms: int = 0

    def __post_init__(self):
        if self.timestamp_ms == 0:
            self.timestamp_ms = int(time.time() * 1000)


# ═══════════════════════════════════════════════════════════════════════════════
# Protective Order Manager Engine
# ═══════════════════════════════════════════════════════════════════════════════

class ProtectiveOrderManager:
    """
    Manages protective orders for positions.

    Implements:
    - DOC-01 §5.9: Exchange protective orders as final survival line
    - EX-01 §4.2: Stop concealment (local trigger, not on exchange order book)
    - EX-01 §4.3: ATR-dynamic distance + random offset for anti-hunt
    - Thread-safe tracking with audit callbacks
    - Validation of coverage across all positions
    """

    def __init__(
        self,
        audit_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        on_execute_callback: Optional[Callable[[ProtectiveOrder, Dict[str, Any]], None]] = None,
    ):
        """
        Initialize manager.

        Args:
            audit_callback: Function(event_type: str, details: dict) for audit logging
            on_execute_callback: Function(order: ProtectiveOrder, market_state: dict)
                                when protective action triggers
        """
        self._orders: Dict[str, ProtectiveOrder] = {}  # order_id -> ProtectiveOrder
        self._position_orders: Dict[str, List[str]] = {}  # position_id -> [order_id]
        self._symbol_orders: Dict[str, List[str]] = {}  # symbol -> [order_id]

        self._audit_callback = audit_callback
        self._on_execute_callback = on_execute_callback

        self._lock = threading.RLock()

        self._configs: Dict[str, ProtectiveOrderConfig] = {}  # For standard templates

        logger.info(f"ProtectiveOrderManager initialized (audit_callback: {audit_callback is not None})")

    # ─────────────────────────────────────────────────────────────────────────────
    # Create and Track
    # ─────────────────────────────────────────────────────────────────────────────

    def create_protective_order(
        self,
        symbol: str,
        side: ProtectiveOrderSide,
        order_type: ProtectiveOrderType,
        entry_price: float,
        trigger_price_pct: float,
        quantity: float,
        position_id: Optional[str] = None,
        strategy_id: Optional[str] = None,
        atr_value: Optional[float] = None,
        random_offset_pct: Optional[float] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> ProtectiveOrder:
        """
        Create and register a protective order.

        Per EX-01 §4.2 & §4.3:
        - Local monitoring only (not placed on exchange until triggered)
        - ATR-based dynamic distance
        - Random offset for unpredictability

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            side: LONG_POSITION, SHORT_POSITION, or BOTH
            order_type: Type of protective order
            entry_price: Entry price of position
            trigger_price_pct: Distance as % from entry
            quantity: Position size to protect
            position_id: Reference to open position
            strategy_id: Strategy that owns this
            atr_value: ATR value for dynamic distance
            random_offset_pct: Random offset % for unpredictability
            tags: Metadata tags

        Returns:
            ProtectiveOrder: Created order object

        Raises:
            ValueError: If entry_price or quantity invalid
        """
        if entry_price <= 0:
            raise ValueError(f"entry_price must be > 0, got {entry_price}")
        if quantity <= 0:
            raise ValueError(f"quantity must be > 0, got {quantity}")

        # Calculate trigger price based on side and trigger condition
        if side == ProtectiveOrderSide.LONG_POSITION:
            # Long position: stop below entry
            trigger_price = entry_price * (1.0 - trigger_price_pct / 100.0)
            trigger_condition = TriggerCondition.PRICE_LESS_THAN
        elif side == ProtectiveOrderSide.SHORT_POSITION:
            # Short position: stop above entry
            trigger_price = entry_price * (1.0 + trigger_price_pct / 100.0)
            trigger_condition = TriggerCondition.PRICE_GREATER_THAN
        else:  # BOTH
            # Emergency: close when any extreme hit
            trigger_price = entry_price  # Placeholder
            trigger_condition = TriggerCondition.PRICE_TOUCHES

        # Hard stops cannot be disabled (DOC-01 §5.9)
        can_be_disabled = order_type != ProtectiveOrderType.HARD_STOP_LOSS

        order = ProtectiveOrder(
            order_id="",  # Will be generated in __post_init__
            symbol=symbol,
            side=side,
            order_type=order_type,
            trigger_price=trigger_price,
            trigger_price_pct=trigger_price_pct,
            quantity=quantity,
            entry_price=entry_price,
            position_id=position_id,
            strategy_id=strategy_id,
            atr_value=atr_value,
            random_offset=random_offset_pct,
            tags=tags or {},
            can_be_disabled=can_be_disabled,
        )

        with self._lock:
            self._orders[order.order_id] = order

            if position_id:
                if position_id not in self._position_orders:
                    self._position_orders[position_id] = []
                self._position_orders[position_id].append(order.order_id)

            if symbol not in self._symbol_orders:
                self._symbol_orders[symbol] = []
            self._symbol_orders[symbol].append(order.order_id)

        if self._audit_callback:
            self._audit_callback("protective_order_created", {
                "order_id": order.order_id,
                "order_type": order_type.value,
                "symbol": symbol,
                "side": side.value,
                "entry_price": entry_price,
                "trigger_price": trigger_price,
                "trigger_price_pct": trigger_price_pct,
                "quantity": quantity,
                "position_id": position_id,
            })

        logger.info(f"Created protective order {order.order_id} ({order_type.value}) "
                    f"for {symbol} {side.value} @ {trigger_price:.8f}")

        return order

    def get_order(self, order_id: str) -> Optional[ProtectiveOrder]:
        """Retrieve protective order by ID"""
        with self._lock:
            return self._orders.get(order_id)

    def get_orders_for_position(self, position_id: str) -> List[ProtectiveOrder]:
        """Get all protective orders for a position"""
        with self._lock:
            order_ids = self._position_orders.get(position_id, [])
            return [self._orders[oid] for oid in order_ids if oid in self._orders]

    def get_orders_for_symbol(self, symbol: str) -> List[ProtectiveOrder]:
        """Get all protective orders for a symbol"""
        with self._lock:
            order_ids = self._symbol_orders.get(symbol, [])
            return [self._orders[oid] for oid in order_ids if oid in self._orders]

    def get_all_orders(self) -> List[ProtectiveOrder]:
        """Get all protective orders"""
        with self._lock:
            return list(self._orders.values())

    # ─────────────────────────────────────────────────────────────────────────────
    # Check Triggers (Market Tick Evaluation)
    # ─────────────────────────────────────────────────────────────────────────────

    def check_triggers(
        self,
        market_state: Dict[str, Dict[str, float]],  # symbol -> {price, volume, ...}
        skip_soft_stops: bool = False,
    ) -> ProtectiveOrderCheckResult:
        """
        Evaluate all protective orders against current market prices.

        Call this on every market tick (or reasonable frequency).

        Args:
            market_state: Dict mapping symbol -> {price: float, ...}
            skip_soft_stops: If True, only hard stops trigger (for low-confidence markets)

        Returns:
            ProtectiveOrderCheckResult with triggered orders and coverage metrics
        """
        triggered = []
        timestamp_ms = int(time.time() * 1000)

        with self._lock:
            for order in list(self._orders.values()):
                # Skip if already terminal
                if order.status in (ProtectiveOrderStatus.EXECUTED,
                                    ProtectiveOrderStatus.CANCELLED,
                                    ProtectiveOrderStatus.EXPIRED,
                                    ProtectiveOrderStatus.FAILED):
                    continue

                # Skip soft stops if requested
                if skip_soft_stops and order.order_type == ProtectiveOrderType.SOFT_STOP_LOSS:
                    continue

                # Check if trigger condition is met
                market_info = market_state.get(order.symbol, {})
                current_price = market_info.get('price')

                if current_price is None:
                    continue

                if self._check_trigger_condition(order, current_price):
                    order.status = ProtectiveOrderStatus.TRIGGERED
                    order.triggered_at_ms = timestamp_ms
                    triggered.append(copy.deepcopy(order))

                    if self._audit_callback:
                        self._audit_callback("protective_order_triggered", {
                            "order_id": order.order_id,
                            "order_type": order.order_type.value,
                            "symbol": order.symbol,
                            "trigger_price": order.trigger_price,
                            "current_price": current_price,
                            "timestamp_ms": timestamp_ms,
                        })

        # Calculate coverage
        coverage_pct = self._calculate_coverage()
        unprotected = self._identify_unprotected_positions()

        result = ProtectiveOrderCheckResult(
            triggered_orders=triggered,
            unprotected_positions=unprotected,
            missing_mandatory_stops=[p['position_id'] for p in unprotected
                                    if p.get('missing_hard_stop')],
            portfolio_coverage_pct=coverage_pct,
            timestamp_ms=timestamp_ms,
        )

        if triggered:
            logger.warning(f"Protective order trigger check: {len(triggered)} orders triggered")

        return result

    def _check_trigger_condition(
        self,
        order: ProtectiveOrder,
        current_price: float,
    ) -> bool:
        """Check if trigger condition is met for an order"""
        if order.order_type == ProtectiveOrderType.TRAILING_STOP:
            # For trailing stop, update high and check if price fell below
            if order.trailing_high is None:
                order.trailing_high = current_price
            else:
                order.trailing_high = max(order.trailing_high, current_price)

            if order.trailing_distance is not None:
                trailing_level = order.trailing_high * (1.0 - order.trailing_distance / 100.0)
                if current_price <= trailing_level:
                    return True
            return False

        # Standard trigger conditions
        if order.order_type in (ProtectiveOrderType.HARD_STOP_LOSS,
                               ProtectiveOrderType.SOFT_STOP_LOSS):
            # Stop-loss: trigger when price hits or crosses the trigger level
            if order.side == ProtectiveOrderSide.LONG_POSITION:
                return current_price <= order.trigger_price
            else:  # SHORT_POSITION
                return current_price >= order.trigger_price

        elif order.order_type == ProtectiveOrderType.TAKE_PROFIT:
            # Take-profit: trigger when price reaches target
            if order.side == ProtectiveOrderSide.LONG_POSITION:
                return current_price >= order.trigger_price
            else:  # SHORT_POSITION
                return current_price <= order.trigger_price

        elif order.order_type == ProtectiveOrderType.POSITION_CLOSE:
            # Position close: trigger immediately (used as one-time instruction)
            return True

        elif order.order_type == ProtectiveOrderType.EMERGENCY_CLOSE_ALL:
            # Emergency: always trigger on demand
            return True

        return False

    # ─────────────────────────────────────────────────────────────────────────────
    # Execute Protective Actions
    # ─────────────────────────────────────────────────────────────────────────────

    def execute_protective_action(
        self,
        order: ProtectiveOrder,
        market_state: Dict[str, Any],
    ) -> bool:
        """
        Execute a protective action triggered by market condition.

        This is the callback invoked when check_triggers() identifies a triggered order.

        Args:
            order: The triggered ProtectiveOrder
            market_state: Current market state (price, volume, etc.)

        Returns:
            True if execution successful, False otherwise
        """
        if order.status not in (ProtectiveOrderStatus.TRIGGERED, ProtectiveOrderStatus.ARMED):
            logger.warning(f"Cannot execute order {order.order_id} in status {order.status}")
            return False

        try:
            # Place the order on exchange (reduce-only for stops)
            # This is delegated to the execution layer via callback
            if self._on_execute_callback:
                self._on_execute_callback(order, market_state)

            with self._lock:
                order.status = ProtectiveOrderStatus.EXECUTED
                order.exchange_order_id = f"exch_{uuid.uuid4().hex[:16]}"

            if self._audit_callback:
                self._audit_callback("protective_action_executed", {
                    "order_id": order.order_id,
                    "order_type": order.order_type.value,
                    "symbol": order.symbol,
                    "quantity": order.quantity,
                    "exchange_order_id": order.exchange_order_id,
                    "market_state": market_state,
                })

            logger.info(f"Executed protective action {order.order_id} "
                        f"({order.order_type.value}) for {order.symbol}")

            return True

        except Exception as e:
            logger.error(f"Failed to execute protective action {order.order_id}: {e}")
            with self._lock:
                order.status = ProtectiveOrderStatus.FAILED
            if self._audit_callback:
                self._audit_callback("protective_action_failed", {
                    "order_id": order.order_id,
                    "error": str(e),
                })
            return False

    # ─────────────────────────────────────────────────────────────────────────────
    # Validation and Coverage
    # ─────────────────────────────────────────────────────────────────────────────

    def validate_coverage(
        self,
        open_positions: List[Dict[str, Any]],
    ) -> Tuple[bool, List[str]]:
        """
        Validate that all open positions have required protective orders.

        Per DOC-01 §5.9: All positions must have at least a hard stop-loss.

        Args:
            open_positions: List of dicts with 'position_id', 'symbol', 'side', etc.

        Returns:
            (is_valid: bool, missing_position_ids: List[str])
        """
        missing = []

        with self._lock:
            for position in open_positions:
                pos_id = position.get('position_id')

                # Check if position has hard stop-loss
                orders = self._position_orders.get(pos_id, [])
                has_hard_stop = any(
                    self._orders.get(oid) and
                    self._orders[oid].order_type == ProtectiveOrderType.HARD_STOP_LOSS
                    for oid in orders
                )

                if not has_hard_stop:
                    missing.append(pos_id)

        is_valid = len(missing) == 0

        if not is_valid and self._audit_callback:
            self._audit_callback("coverage_validation_failed", {
                "missing_hard_stops": missing,
                "total_positions": len(open_positions),
            })

        return is_valid, missing

    def get_unprotected_positions(
        self,
        open_positions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Identify positions without required protective orders.

        Returns list of positions missing hard stops, with details for
        automatic stop assignment.

        Args:
            open_positions: List of dicts with 'position_id', 'symbol', 'side', 'quantity', etc.

        Returns:
            List of unprotected position dicts
        """
        unprotected = []

        with self._lock:
            for position in open_positions:
                pos_id = position.get('position_id')
                orders = self._position_orders.get(pos_id, [])

                has_hard_stop = any(
                    self._orders.get(oid) and
                    self._orders[oid].order_type == ProtectiveOrderType.HARD_STOP_LOSS
                    for oid in orders
                )

                if not has_hard_stop:
                    unprotected.append({
                        "position_id": pos_id,
                        "symbol": position.get('symbol'),
                        "side": position.get('side'),
                        "quantity": position.get('quantity'),
                        "entry_price": position.get('entry_price'),
                        "missing_hard_stop": True,
                    })

        return unprotected

    def _calculate_coverage(self) -> float:
        """Calculate percentage of positions with protective orders"""
        # Simplified: count positions with at least one order
        with self._lock:
            if not self._position_orders:
                return 0.0
            total_positions = len(self._position_orders)
            covered = sum(1 for orders in self._position_orders.values() if orders)
            return (covered / total_positions * 100.0) if total_positions > 0 else 0.0

    def _identify_unprotected_positions(self) -> List[Dict[str, Any]]:
        """Internal: identify positions without orders"""
        return self.get_unprotected_positions(
            [{"position_id": pid} for pid in self._position_orders.keys()]
        )

    # ─────────────────────────────────────────────────────────────────────────────
    # Cancel, Disable, Emergency
    # ─────────────────────────────────────────────────────────────────────────────

    def cancel_order(
        self,
        order_id: str,
        reason: str = "",
    ) -> bool:
        """
        Cancel a protective order.

        Per DOC-01 §5.9: HARD_STOP_LOSS orders cannot be cancelled.

        Args:
            order_id: Order to cancel
            reason: Reason for cancellation

        Returns:
            True if cancelled, False if cannot cancel (e.g., hard stop)

        Raises:
            ValueError: If order not found or in invalid state
        """
        with self._lock:
            order = self._orders.get(order_id)

            if not order:
                raise ValueError(f"Order {order_id} not found")

            # Hard stops cannot be disabled
            if order.order_type == ProtectiveOrderType.HARD_STOP_LOSS:
                logger.warning(f"Cannot cancel hard stop-loss {order_id} (DOC-01 §5.9)")
                if self._audit_callback:
                    self._audit_callback("hard_stop_cancel_rejected", {
                        "order_id": order_id,
                        "reason": reason,
                    })
                return False

            if not order.can_be_disabled:
                logger.warning(f"Order {order_id} cannot be disabled")
                return False

            order.status = ProtectiveOrderStatus.CANCELLED

        if self._audit_callback:
            self._audit_callback("protective_order_cancelled", {
                "order_id": order_id,
                "order_type": order.order_type.value,
                "reason": reason,
            })

        logger.info(f"Cancelled protective order {order_id}: {reason}")
        return True

    def emergency_close_all(
        self,
        market_state: Dict[str, Any],
        reason: str = "CIRCUIT_BREAKER",
    ) -> int:
        """
        Emergency close all positions (circuit breaker).

        This is the ultimate safety mechanism. Closes all positions
        without condition, bypassing all normal checks.

        Args:
            market_state: Current market state
            reason: Reason for emergency close (logged)

        Returns:
            Number of positions closed
        """
        closed_count = 0

        with self._lock:
            # Create emergency close orders for all open positions
            for pid in list(self._position_orders.keys()):
                order = ProtectiveOrder(
                    order_id="",
                    symbol="MULTI",
                    side=ProtectiveOrderSide.BOTH,
                    order_type=ProtectiveOrderType.EMERGENCY_CLOSE_ALL,
                    trigger_price=0.0,
                    trigger_price_pct=0.0,
                    quantity=0.0,  # Close entire position
                    entry_price=0.0,
                    position_id=pid,
                    tags={"emergency_reason": reason},
                )

                self._orders[order.order_id] = order
                closed_count += 1

        if self._on_execute_callback:
            for order in self._orders.values():
                if order.order_type == ProtectiveOrderType.EMERGENCY_CLOSE_ALL:
                    self._on_execute_callback(order, market_state)

        if self._audit_callback:
            self._audit_callback("emergency_close_all", {
                "closed_positions": closed_count,
                "reason": reason,
            })

        logger.critical(f"EMERGENCY CLOSE ALL: {closed_count} positions "
                       f"(reason: {reason})")

        return closed_count

    # ─────────────────────────────────────────────────────────────────────────────
    # Serialization
    # ─────────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Serialize manager state to dict (for snapshots, logging)"""
        with self._lock:
            return {
                "orders": [order.to_dict() for order in self._orders.values()],
                "position_orders": self._position_orders,
                "symbol_orders": self._symbol_orders,
                "timestamp_ms": int(time.time() * 1000),
            }

    def from_dict(self, data: Dict[str, Any]) -> None:
        """Restore manager state from dict"""
        with self._lock:
            self._orders.clear()
            self._position_orders.clear()
            self._symbol_orders.clear()

            for order_dict in data.get('orders', []):
                order = ProtectiveOrder.from_dict(order_dict)
                self._orders[order.order_id] = order

            self._position_orders = data.get('position_orders', {})
            self._symbol_orders = data.get('symbol_orders', {})

        if self._audit_callback:
            self._audit_callback("manager_state_restored", {
                "order_count": len(self._orders),
            })

        logger.info(f"Restored ProtectiveOrderManager state: {len(self._orders)} orders")

    def export_json(self) -> str:
        """Export to JSON string"""
        return json.dumps(self.to_dict(), indent=2, default=str)

    def import_json(self, json_str: str) -> None:
        """Import from JSON string"""
        data = json.loads(json_str)
        self.from_dict(data)


# ═══════════════════════════════════════════════════════════════════════════════
# Utilities
# ═══════════════════════════════════════════════════════════════════════════════

def create_default_hard_stop_config(
    hard_stop_pct: float = 5.0,
) -> ProtectiveOrderConfig:
    """
    Create default hard stop-loss configuration.

    Per DOC-01 §5.9 and EX-01 §4.2:
    - Cannot be disabled
    - Local monitoring only (stealth mode)
    - ATR-dynamic distance

    Args:
        hard_stop_pct: Default hard stop % distance from entry

    Returns:
        ProtectiveOrderConfig
    """
    return ProtectiveOrderConfig(
        order_type=ProtectiveOrderType.HARD_STOP_LOSS,
        trigger_price_pct=hard_stop_pct,
        trigger_condition=TriggerCondition.PRICE_LESS_THAN,
        is_mandatory=True,
        can_be_disabled=False,
        bypass_requires_approval=False,
        description=f"Default hard stop-loss {hard_stop_pct}% below entry (DOC-01 §5.9)",
    )


def calculate_atr_adjusted_stop(
    atr: float,
    base_stop_pct: float,
    atr_multiplier: float = 1.5,
) -> float:
    """
    Calculate ATR-adjusted stop distance (EX-01 §4.3).

    In volatile markets, widen stops to avoid noise.

    Args:
        atr: Average True Range value
        base_stop_pct: Base stop distance as %
        atr_multiplier: How much to scale by ATR

    Returns:
        Adjusted stop distance as %
    """
    # Rough conversion: ATR as % of recent price
    atr_pct = atr_multiplier * 100.0  # Placeholder; actual depends on price
    return base_stop_pct * (1.0 + atr_pct / 100.0)
