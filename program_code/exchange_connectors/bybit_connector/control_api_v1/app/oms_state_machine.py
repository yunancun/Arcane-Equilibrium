"""
OMS State Machine Supplement — EX-02 / GAP-H1
OMS 订单执行状态机补充 — 11 状态完整生命周期

MODULE_NOTE (中文):
  扩展 Paper Trading Engine 的 7 状态生命周期为完整 11 状态 OMS 生命周期。
  新增 4 个关键状态：PENDING、APPROVED、RECONCILING、COMPLETED。
  - PENDING/APPROVED: 与授权状态机 (T2.01) 协调的预执行审批
  - RECONCILING: 关键安全闸门 — paper↔demo 持仓一致性验证
  - COMPLETED: 通过对账验证的最终状态

MODULE_NOTE (English):
  Extends the 7-state Paper Trading Engine lifecycle to a full 11-state OMS lifecycle.
  Adds 4 critical states: PENDING, APPROVED, RECONCILING, COMPLETED.
  - PENDING/APPROVED: Pre-execution vetting via authorization state machine (T2.01)
  - RECONCILING: Critical safety gate — paper↔demo position consistency check
  - COMPLETED: Final verified state after reconciliation

Safety invariant:
  - 所有订单必须通过 PENDING→APPROVED 授权流
  - FILLED 后必须进入 RECONCILING（不可跳过）
  - RECONCILING 失败→REJECTED 或冻结处理
  - 终态不可逆转
"""

from __future__ import annotations

import copy
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Enums / 枚举
# ═══════════════════════════════════════════════════════════════════════════════

class OrderState(str, Enum):
    """Full 11-state OMS lifecycle / 完整 11 状态 OMS 生命周期"""
    # Pre-execution states / 执行前状态
    CREATED = "CREATED"
    PENDING = "PENDING"             # Awaiting authorization / 等待授权
    APPROVED = "APPROVED"           # Authorization granted / 授权通过
    # Execution states / 执行中状态
    SUBMITTED = "SUBMITTED"         # Sent to execution venue / 已提交
    WORKING = "WORKING"             # Active on book / 挂单中
    PARTIALLY_FILLED = "PARTIALLY_FILLED"  # Partial fills / 部分成交
    FILLED = "FILLED"               # Fully filled / 完全成交
    # Post-execution states / 执行后状态
    RECONCILING = "RECONCILING"     # Position sync verification / 持仓同步验证
    COMPLETED = "COMPLETED"         # Reconciliation passed / 对账通过（终态）
    # Terminal states / 终止状态
    CANCELED = "CANCELED"           # Canceled / 已取消
    REJECTED = "REJECTED"           # Rejected / 已拒绝


class OrderEvent(str, Enum):
    """Events triggering OMS state transitions / OMS 状态转换事件"""
    SUBMIT_FOR_APPROVAL = "SUBMIT_FOR_APPROVAL"       # Created → Pending
    APPROVE = "APPROVE"                                 # Pending → Approved
    REJECT_AUTHORIZATION = "REJECT_AUTHORIZATION"       # Pending → Rejected
    SEND_TO_VENUE = "SEND_TO_VENUE"                    # Approved → Submitted
    ACKNOWLEDGE = "ACKNOWLEDGE"                         # Submitted → Working
    REJECT_BY_VENUE = "REJECT_BY_VENUE"                # Submitted → Rejected
    PARTIAL_FILL = "PARTIAL_FILL"                      # Working → PartiallyFilled
    FILL = "FILL"                                       # Working/PartiallyFilled → Filled
    CANCEL = "CANCEL"                                   # Active states → Canceled
    BEGIN_RECONCILIATION = "BEGIN_RECONCILIATION"       # Filled → Reconciling
    RECONCILIATION_PASS = "RECONCILIATION_PASS"        # Reconciling → Completed
    RECONCILIATION_FAIL = "RECONCILIATION_FAIL"        # Reconciling → Rejected
    EXPIRE = "EXPIRE"                                   # Time-based expiry


class OrderInitiator(str, Enum):
    """Who can initiate OMS transitions / 谁可以发起 OMS 转换"""
    OPERATOR = "Operator"
    AI_AGENT = "AIAgent"
    SYSTEM = "System"                    # Internal system events
    EXECUTION_VENUE = "ExecutionVenue"   # Exchange/demo fills
    AUTHORIZATION_SM = "AuthorizationSM" # Authorization state machine
    RECONCILIATION_ENGINE = "ReconciliationEngine"
    RISK_GOVERNOR = "RiskGovernor"


# ═══════════════════════════════════════════════════════════════════════════════
# Transition Rules / 转换规则
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class OMSTransitionRule:
    """A single valid OMS state transition / 单条有效 OMS 转换规则"""
    from_state: OrderState
    to_state: OrderState
    event: OrderEvent
    allowed_initiators: frozenset[OrderInitiator]
    requires_approval: bool = False
    description: str = ""


# Full 11-state transition table
# 完整 11 状态转换表
OMS_TRANSITION_RULES: dict[tuple[OrderState, OrderState], OMSTransitionRule] = {}

_rules = [
    # Pre-execution flow / 执行前流程
    OMSTransitionRule(
        OrderState.CREATED, OrderState.PENDING,
        OrderEvent.SUBMIT_FOR_APPROVAL,
        frozenset({OrderInitiator.AI_AGENT, OrderInitiator.OPERATOR, OrderInitiator.SYSTEM}),
        description="Submit order for authorization review / 提交订单进行授权审核",
    ),
    OMSTransitionRule(
        OrderState.PENDING, OrderState.APPROVED,
        OrderEvent.APPROVE,
        frozenset({OrderInitiator.AUTHORIZATION_SM, OrderInitiator.OPERATOR}),
        description="Authorization approved / 授权通过",
    ),
    OMSTransitionRule(
        OrderState.PENDING, OrderState.REJECTED,
        OrderEvent.REJECT_AUTHORIZATION,
        frozenset({OrderInitiator.AUTHORIZATION_SM, OrderInitiator.OPERATOR, OrderInitiator.RISK_GOVERNOR}),
        description="Authorization rejected / 授权拒绝",
    ),
    OMSTransitionRule(
        OrderState.PENDING, OrderState.CANCELED,
        OrderEvent.CANCEL,
        frozenset({OrderInitiator.OPERATOR, OrderInitiator.AI_AGENT, OrderInitiator.SYSTEM}),
        description="Cancel pending order / 取消待审批订单",
    ),
    # Execution flow / 执行流程
    OMSTransitionRule(
        OrderState.APPROVED, OrderState.SUBMITTED,
        OrderEvent.SEND_TO_VENUE,
        frozenset({OrderInitiator.SYSTEM, OrderInitiator.OPERATOR}),
        description="Send approved order to execution venue / 将已批准订单发送至执行场所",
    ),
    OMSTransitionRule(
        OrderState.APPROVED, OrderState.CANCELED,
        OrderEvent.CANCEL,
        frozenset({OrderInitiator.OPERATOR, OrderInitiator.AI_AGENT, OrderInitiator.RISK_GOVERNOR}),
        description="Cancel approved order before sending / 发送前取消已批准订单",
    ),
    OMSTransitionRule(
        OrderState.SUBMITTED, OrderState.WORKING,
        OrderEvent.ACKNOWLEDGE,
        frozenset({OrderInitiator.EXECUTION_VENUE, OrderInitiator.SYSTEM}),
        description="Venue acknowledged order / 执行场所确认订单",
    ),
    OMSTransitionRule(
        OrderState.SUBMITTED, OrderState.REJECTED,
        OrderEvent.REJECT_BY_VENUE,
        frozenset({OrderInitiator.EXECUTION_VENUE, OrderInitiator.SYSTEM}),
        description="Venue rejected order / 执行场所拒绝订单",
    ),
    OMSTransitionRule(
        OrderState.WORKING, OrderState.PARTIALLY_FILLED,
        OrderEvent.PARTIAL_FILL,
        frozenset({OrderInitiator.EXECUTION_VENUE, OrderInitiator.SYSTEM}),
        description="Partial fill received / 收到部分成交",
    ),
    OMSTransitionRule(
        OrderState.WORKING, OrderState.FILLED,
        OrderEvent.FILL,
        frozenset({OrderInitiator.EXECUTION_VENUE, OrderInitiator.SYSTEM}),
        description="Order fully filled / 订单完全成交",
    ),
    OMSTransitionRule(
        OrderState.WORKING, OrderState.CANCELED,
        OrderEvent.CANCEL,
        frozenset({OrderInitiator.OPERATOR, OrderInitiator.AI_AGENT, OrderInitiator.SYSTEM, OrderInitiator.RISK_GOVERNOR}),
        description="Cancel working order / 取消挂单",
    ),
    OMSTransitionRule(
        OrderState.PARTIALLY_FILLED, OrderState.FILLED,
        OrderEvent.FILL,
        frozenset({OrderInitiator.EXECUTION_VENUE, OrderInitiator.SYSTEM}),
        description="Remaining quantity filled / 剩余数量成交",
    ),
    OMSTransitionRule(
        OrderState.PARTIALLY_FILLED, OrderState.CANCELED,
        OrderEvent.CANCEL,
        frozenset({OrderInitiator.OPERATOR, OrderInitiator.AI_AGENT, OrderInitiator.SYSTEM, OrderInitiator.RISK_GOVERNOR}),
        description="Cancel partially filled order / 取消部分成交订单",
    ),
    # Post-execution flow / 执行后流程
    OMSTransitionRule(
        OrderState.FILLED, OrderState.RECONCILING,
        OrderEvent.BEGIN_RECONCILIATION,
        frozenset({OrderInitiator.SYSTEM, OrderInitiator.RECONCILIATION_ENGINE}),
        description="Begin position reconciliation / 开始持仓对账",
    ),
    OMSTransitionRule(
        OrderState.RECONCILING, OrderState.COMPLETED,
        OrderEvent.RECONCILIATION_PASS,
        frozenset({OrderInitiator.RECONCILIATION_ENGINE, OrderInitiator.SYSTEM}),
        description="Reconciliation passed — position consistent / 对账通过 — 持仓一致",
    ),
    OMSTransitionRule(
        OrderState.RECONCILING, OrderState.REJECTED,
        OrderEvent.RECONCILIATION_FAIL,
        frozenset({OrderInitiator.RECONCILIATION_ENGINE, OrderInitiator.SYSTEM, OrderInitiator.OPERATOR}),
        description="Reconciliation failed — position mismatch / 对账失败 — 持仓不一致",
    ),
]

for rule in _rules:
    OMS_TRANSITION_RULES[(rule.from_state, rule.to_state)] = rule

# Terminal states — no outgoing transitions
TERMINAL_STATES: frozenset[OrderState] = frozenset({
    OrderState.COMPLETED,
    OrderState.CANCELED,
    OrderState.REJECTED,
})

# Active states — can still be worked on
ACTIVE_STATES: frozenset[OrderState] = frozenset({
    OrderState.PENDING,
    OrderState.APPROVED,
    OrderState.SUBMITTED,
    OrderState.WORKING,
    OrderState.PARTIALLY_FILLED,
    OrderState.RECONCILING,
})

# Forbidden transitions (explicit safety constraints)
# 禁止转换（显式安全约束）
FORBIDDEN_TRANSITIONS: frozenset[tuple[OrderState, OrderState]] = frozenset({
    # Cannot skip authorization / 不可跳过授权
    (OrderState.CREATED, OrderState.SUBMITTED),
    (OrderState.CREATED, OrderState.WORKING),
    (OrderState.CREATED, OrderState.APPROVED),
    # Cannot skip reconciliation / 不可跳过对账
    (OrderState.FILLED, OrderState.COMPLETED),
    # Terminal states cannot exit / 终态不可退出
    (OrderState.COMPLETED, OrderState.CREATED),
    (OrderState.COMPLETED, OrderState.RECONCILING),
    (OrderState.CANCELED, OrderState.CREATED),
    (OrderState.CANCELED, OrderState.PENDING),
    (OrderState.REJECTED, OrderState.CREATED),
    (OrderState.REJECTED, OrderState.PENDING),
    # Cannot go backwards in execution / 不可在执行中倒退
    (OrderState.WORKING, OrderState.SUBMITTED),
    (OrderState.FILLED, OrderState.WORKING),
})


# ═══════════════════════════════════════════════════════════════════════════════
# Order Object / 订单对象
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class OMSOrder:
    """Extended order object with full 11-state lifecycle / 扩展订单对象"""
    order_id: str = ""
    symbol: str = ""
    side: str = ""          # Buy / Sell
    order_type: str = ""    # market / limit / conditional
    qty: float = 0.0
    price: Optional[float] = None
    state: OrderState = OrderState.CREATED
    created_at_ms: int = 0
    updated_at_ms: int = 0
    created_by: str = ""
    approved_by: str = ""
    reconciliation_result: str = ""
    transition_history: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.order_id:
            self.order_id = f"oms:{uuid.uuid4().hex[:12]}"
        now = int(time.time() * 1000)
        if not self.created_at_ms:
            self.created_at_ms = now
        if not self.updated_at_ms:
            self.updated_at_ms = now

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def is_active(self) -> bool:
        return self.state in ACTIVE_STATES

    @property
    def is_pre_execution(self) -> bool:
        return self.state in (OrderState.CREATED, OrderState.PENDING, OrderState.APPROVED)

    @property
    def is_reconciling(self) -> bool:
        return self.state == OrderState.RECONCILING

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "qty": self.qty,
            "price": self.price,
            "state": self.state.value,
            "created_at_ms": self.created_at_ms,
            "updated_at_ms": self.updated_at_ms,
            "created_by": self.created_by,
            "approved_by": self.approved_by,
            "reconciliation_result": self.reconciliation_result,
            "transition_count": len(self.transition_history),
            "is_terminal": self.is_terminal,
            "is_active": self.is_active,
            "metadata": self.metadata,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# State Machine Engine / 状态机引擎
# ═══════════════════════════════════════════════════════════════════════════════

class OMSStateMachine:
    """
    Full 11-state OMS state machine engine.
    完整 11 状态 OMS 状态机引擎。

    Thread-safe, with guard conditions, audit callback, and persistence support.
    线程安全，带守卫条件、审计回调和持久化支持。

    Usage:
        sm = OMSStateMachine(audit_callback=pipeline.make_callback("oms"))
        oid = sm.create_order(symbol="BTCUSDT", side="Buy", qty=0.1, order_type="limit", price=50000)
        sm.submit_for_approval(oid, initiator=OrderInitiator.AI_AGENT)
        sm.approve(oid, initiator=OrderInitiator.AUTHORIZATION_SM)
        sm.send_to_venue(oid, initiator=OrderInitiator.SYSTEM)
        sm.acknowledge(oid, initiator=OrderInitiator.EXECUTION_VENUE)
        sm.fill(oid, initiator=OrderInitiator.EXECUTION_VENUE)
        sm.begin_reconciliation(oid, initiator=OrderInitiator.RECONCILIATION_ENGINE)
        sm.reconciliation_pass(oid, initiator=OrderInitiator.RECONCILIATION_ENGINE)
    """

    def __init__(
        self,
        audit_callback: Optional[Callable[[dict], None]] = None,
    ) -> None:
        self._orders: dict[str, OMSOrder] = {}
        self._lock = threading.Lock()
        self._audit_callback = audit_callback
        self._closed = False

    # ───────────────────────────────────────────────────────────────────────
    # Order Creation / 订单创建
    # ───────────────────────────────────────────────────────────────────────

    def create_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        order_type: str = "limit",
        price: Optional[float] = None,
        created_by: str = "",
        metadata: Optional[dict] = None,
    ) -> str:
        """Create a new order in CREATED state / 创建新订单"""
        with self._lock:
            order = OMSOrder(
                symbol=symbol,
                side=side,
                qty=qty,
                order_type=order_type,
                price=price,
                created_by=created_by,
                metadata=metadata or {},
            )
            self._orders[order.order_id] = order
            return order.order_id

    # ───────────────────────────────────────────────────────────────────────
    # Transition Engine / 转换引擎
    # ───────────────────────────────────────────────────────────────────────

    def transition(
        self,
        order_id: str,
        target_state: OrderState,
        initiator: OrderInitiator,
        reason: str = "",
        extra_data: Optional[dict] = None,
    ) -> None:
        """
        Execute a state transition with full validation.
        执行带完整验证的状态转换。

        Raises:
            KeyError: Order not found
            ValueError: Invalid transition (forbidden, not in table, wrong initiator)
        """
        with self._lock:
            if order_id not in self._orders:
                raise KeyError(f"Order {order_id} not found")

            order = self._orders[order_id]
            from_state = order.state
            key = (from_state, target_state)

            # Check forbidden
            if key in FORBIDDEN_TRANSITIONS:
                raise ValueError(
                    f"Forbidden transition: {from_state.value} → {target_state.value}"
                )

            # Check valid
            if key not in OMS_TRANSITION_RULES:
                raise ValueError(
                    f"Transition {from_state.value} → {target_state.value} not in transition table"
                )

            rule = OMS_TRANSITION_RULES[key]

            # Check initiator
            if initiator not in rule.allowed_initiators:
                raise ValueError(
                    f"Initiator {initiator.value} not allowed for "
                    f"{from_state.value} → {target_state.value}"
                )

            # Execute transition
            now_ms = int(time.time() * 1000)
            transition_id = f"otx:{uuid.uuid4().hex[:12]}"

            order.transition_history.append({
                "transition_id": transition_id,
                "from_state": from_state.value,
                "to_state": target_state.value,
                "initiator": initiator.value,
                "reason": reason,
                "timestamp_ms": now_ms,
            })

            order.state = target_state
            order.updated_at_ms = now_ms

            # Track approval
            if target_state == OrderState.APPROVED:
                order.approved_by = initiator.value
            if target_state == OrderState.COMPLETED:
                order.reconciliation_result = "PASS"
            if target_state == OrderState.REJECTED and from_state == OrderState.RECONCILING:
                order.reconciliation_result = "FAIL"

            # Audit
            if self._audit_callback:
                try:
                    self._audit_callback({
                        "transition_id": transition_id,
                        "order_id": order_id,
                        "event_type": f"oms_{from_state.value}_to_{target_state.value}".lower(),
                        "from_state": from_state.value,
                        "to_state": target_state.value,
                        "initiator": initiator.value,
                        "reason": reason,
                        "symbol": order.symbol,
                        "timestamp_ms": now_ms,
                        **(extra_data or {}),
                    })
                except Exception as e:
                    logger.error("OMS audit callback error: %s", e)

    # ───────────────────────────────────────────────────────────────────────
    # Convenience Methods / 便捷方法
    # ───────────────────────────────────────────────────────────────────────

    def submit_for_approval(self, order_id: str, initiator: OrderInitiator, reason: str = "") -> None:
        """CREATED → PENDING"""
        self.transition(order_id, OrderState.PENDING, initiator, reason)

    def approve(self, order_id: str, initiator: OrderInitiator, reason: str = "") -> None:
        """PENDING → APPROVED"""
        self.transition(order_id, OrderState.APPROVED, initiator, reason)

    def reject(self, order_id: str, initiator: OrderInitiator, reason: str = "") -> None:
        """Any rejectable state → REJECTED"""
        self.transition(order_id, OrderState.REJECTED, initiator, reason)

    def send_to_venue(self, order_id: str, initiator: OrderInitiator, reason: str = "") -> None:
        """APPROVED → SUBMITTED"""
        self.transition(order_id, OrderState.SUBMITTED, initiator, reason)

    def acknowledge(self, order_id: str, initiator: OrderInitiator, reason: str = "") -> None:
        """SUBMITTED → WORKING"""
        self.transition(order_id, OrderState.WORKING, initiator, reason)

    def partial_fill(self, order_id: str, initiator: OrderInitiator, reason: str = "") -> None:
        """WORKING → PARTIALLY_FILLED"""
        self.transition(order_id, OrderState.PARTIALLY_FILLED, initiator, reason)

    def fill(self, order_id: str, initiator: OrderInitiator, reason: str = "") -> None:
        """WORKING/PARTIALLY_FILLED → FILLED"""
        self.transition(order_id, OrderState.FILLED, initiator, reason)

    def cancel(self, order_id: str, initiator: OrderInitiator, reason: str = "") -> None:
        """Active state → CANCELED"""
        self.transition(order_id, OrderState.CANCELED, initiator, reason)

    def begin_reconciliation(self, order_id: str, initiator: OrderInitiator, reason: str = "") -> None:
        """FILLED → RECONCILING"""
        self.transition(order_id, OrderState.RECONCILING, initiator, reason)

    def reconciliation_pass(self, order_id: str, initiator: OrderInitiator, reason: str = "") -> None:
        """RECONCILING → COMPLETED"""
        self.transition(order_id, OrderState.COMPLETED, initiator, reason)

    def reconciliation_fail(self, order_id: str, initiator: OrderInitiator, reason: str = "") -> None:
        """RECONCILING → REJECTED"""
        self.transition(order_id, OrderState.REJECTED, initiator, reason)

    # ───────────────────────────────────────────────────────────────────────
    # Queries / 查询
    # ───────────────────────────────────────────────────────────────────────

    def get(self, order_id: str) -> Optional[dict]:
        """Get order as dict (copy) / 获取订单副本"""
        with self._lock:
            order = self._orders.get(order_id)
            return order.to_dict() if order else None

    def get_by_state(self, state: OrderState) -> list[dict]:
        """Get all orders in a given state / 获取指定状态的所有订单"""
        with self._lock:
            return [
                o.to_dict() for o in self._orders.values()
                if o.state == state
            ]

    def get_active_orders(self) -> list[dict]:
        """Get all non-terminal orders / 获取所有活跃订单"""
        with self._lock:
            return [o.to_dict() for o in self._orders.values() if o.is_active]

    def get_reconciling_orders(self) -> list[dict]:
        """Get all orders in RECONCILING state / 获取所有对账中订单"""
        return self.get_by_state(OrderState.RECONCILING)

    def get_pending_approval(self) -> list[dict]:
        """Get all orders awaiting approval / 获取所有待审批订单"""
        return self.get_by_state(OrderState.PENDING)

    def status_summary(self) -> dict[str, int]:
        """Count orders by state / 按状态统计订单数"""
        with self._lock:
            summary: dict[str, int] = {}
            for order in self._orders.values():
                key = order.state.value
                summary[key] = summary.get(key, 0) + 1
            return summary

    # ───────────────────────────────────────────────────────────────────────
    # Paper Engine State Mapping / Paper Engine 状态映射
    # ───────────────────────────────────────────────────────────────────────

    @staticmethod
    def map_from_paper_state(paper_state: str) -> OrderState:
        """
        Map Paper Trading Engine state string to OMS OrderState.
        将 Paper Trading Engine 状态字符串映射为 OMS OrderState。
        """
        mapping = {
            "paper_order_created": OrderState.CREATED,
            "paper_order_submitted": OrderState.SUBMITTED,
            "paper_order_working": OrderState.WORKING,
            "paper_order_partially_filled": OrderState.PARTIALLY_FILLED,
            "paper_order_filled": OrderState.FILLED,
            "paper_order_canceled": OrderState.CANCELED,
            "paper_order_rejected": OrderState.REJECTED,
        }
        result = mapping.get(paper_state)
        if result is None:
            raise ValueError(f"Unknown paper state: {paper_state}")
        return result

    @staticmethod
    def map_to_paper_state(oms_state: OrderState) -> str:
        """
        Map OMS OrderState back to Paper Trading Engine state string.
        将 OMS OrderState 映射回 Paper Trading Engine 状态字符串。

        Note: PENDING, APPROVED, RECONCILING, COMPLETED have no direct paper equivalent.
        """
        mapping = {
            OrderState.CREATED: "paper_order_created",
            OrderState.SUBMITTED: "paper_order_submitted",
            OrderState.WORKING: "paper_order_working",
            OrderState.PARTIALLY_FILLED: "paper_order_partially_filled",
            OrderState.FILLED: "paper_order_filled",
            OrderState.CANCELED: "paper_order_canceled",
            OrderState.REJECTED: "paper_order_rejected",
        }
        result = mapping.get(oms_state)
        if result is None:
            raise ValueError(
                f"OMS state {oms_state.value} has no paper engine equivalent "
                f"(new state added by T2.05)"
            )
        return result

    # ───────────────────────────────────────────────────────────────────────
    # Persistence / 持久化
    # ───────────────────────────────────────────────────────────────────────

    def export_state(self) -> dict:
        """Export full state for persistence / 导出完整状态"""
        with self._lock:
            return {
                "orders": {
                    oid: {
                        "order_id": o.order_id,
                        "symbol": o.symbol,
                        "side": o.side,
                        "order_type": o.order_type,
                        "qty": o.qty,
                        "price": o.price,
                        "state": o.state.value,
                        "created_at_ms": o.created_at_ms,
                        "updated_at_ms": o.updated_at_ms,
                        "created_by": o.created_by,
                        "approved_by": o.approved_by,
                        "reconciliation_result": o.reconciliation_result,
                        "transition_history": copy.deepcopy(o.transition_history),
                        "metadata": copy.deepcopy(o.metadata),
                    }
                    for oid, o in self._orders.items()
                },
                "exported_at_ms": int(time.time() * 1000),
            }

    def import_state(self, data: dict) -> int:
        """Import state from persistence / 从持久化导入状态"""
        with self._lock:
            orders_data = data.get("orders", {})
            count = 0
            for oid, odata in orders_data.items():
                order = OMSOrder(
                    order_id=odata["order_id"],
                    symbol=odata.get("symbol", ""),
                    side=odata.get("side", ""),
                    order_type=odata.get("order_type", ""),
                    qty=odata.get("qty", 0),
                    price=odata.get("price"),
                    state=OrderState(odata["state"]),
                    created_at_ms=odata.get("created_at_ms", 0),
                    updated_at_ms=odata.get("updated_at_ms", 0),
                    created_by=odata.get("created_by", ""),
                    approved_by=odata.get("approved_by", ""),
                    reconciliation_result=odata.get("reconciliation_result", ""),
                    transition_history=odata.get("transition_history", []),
                    metadata=odata.get("metadata", {}),
                )
                self._orders[oid] = order
                count += 1
            return count

    def close(self) -> None:
        """Shut down / 关闭"""
        with self._lock:
            self._closed = True
