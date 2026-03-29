"""
Reconciliation Engine — EX-02 §14 / EX-04 / GAP-C1
对账引擎 — 纸上交易 vs Demo/交易所 一致性判定

MODULE_NOTE (中文):
  实现 EX-02 §14 规范的正式对账层：
  - 比对本地 (Paper) 与外部 (Demo/Exchange) 的订单、持仓、成交状态
  - 标记差异类型、严重等级和影响范围
  - 触发事件：冻结、人工审核、自动修正
  - 与审计持久化层 (T2.06) 集成
  - 线程安全设计

MODULE_NOTE (English):
  Implements the formal reconciliation layer per EX-02 §14:
  - Compare local (Paper) vs external (Demo/Exchange) order, position, fill state
  - Mark discrepancy type, severity, and scope
  - Trigger incidents: freeze, manual review, auto-correction
  - Integrates with Audit Persistence (T2.06)
  - Thread-safe design

Safety invariant:
  - 对账不会修改任何交易状态，只产生判定和事件
  - 发现不一致时优先保护账户（冻结 > 继续执行）
  - 永远不跳过对账（EX-02 §14 核心原则）
"""

from __future__ import annotations

import copy
import logging
import os
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

class ReconciliationResult(str, Enum):
    """Outcome of a reconciliation check / 对账检查结果"""
    MATCH = "MATCH"                    # 完全一致
    MISMATCH_MINOR = "MISMATCH_MINOR"  # 小偏差（容差内）
    MISMATCH_MAJOR = "MISMATCH_MAJOR"  # 重大不一致
    MISSING_LOCAL = "MISSING_LOCAL"    # 本地缺失，远端存在
    MISSING_REMOTE = "MISSING_REMOTE"  # 远端缺失，本地存在
    STALE_DATA = "STALE_DATA"         # 数据过时，无法判定
    ERROR = "ERROR"                    # 对账过程出错


class DiscrepancyType(str, Enum):
    """Classification of discovered discrepancies / 差异分类"""
    ORDER_STATE = "ORDER_STATE"           # 订单状态不一致
    ORDER_MISSING = "ORDER_MISSING"       # 订单缺失
    POSITION_SIZE = "POSITION_SIZE"       # 持仓数量不一致
    POSITION_SIDE = "POSITION_SIDE"       # 持仓方向不一致
    POSITION_MISSING = "POSITION_MISSING" # 持仓缺失
    FILL_COUNT = "FILL_COUNT"             # 成交笔数不一致
    FILL_PRICE = "FILL_PRICE"             # 成交价格偏差
    FILL_QUANTITY = "FILL_QUANTITY"        # 成交数量不一致
    BALANCE_DRIFT = "BALANCE_DRIFT"       # 余额偏差
    UNKNOWN = "UNKNOWN"                   # 未分类


class Severity(str, Enum):
    """Severity of a discrepancy / 差异严重等级"""
    INFO = "INFO"          # 可忽略（容差内微小偏差）
    WARNING = "WARNING"    # 需关注但不阻断
    CRITICAL = "CRITICAL"  # 必须立即处理
    FATAL = "FATAL"        # 系统应冻结


class IncidentAction(str, Enum):
    """Actions triggered by reconciliation incidents / 事件触发动作"""
    LOG_ONLY = "LOG_ONLY"              # 仅记录
    ALERT = "ALERT"                    # 发送警报
    FREEZE_TRADING = "FREEZE_TRADING"  # 冻结交易
    MANUAL_REVIEW = "MANUAL_REVIEW"    # 需人工审核
    AUTO_CORRECT = "AUTO_CORRECT"      # 自动修正（仅限安全场景）


# ═══════════════════════════════════════════════════════════════════════════════
# Data Classes / 数据类
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ReconciliationConfig:
    """Configuration for reconciliation engine / 对账引擎配置"""
    # Tolerance for price comparison (relative, e.g. 0.001 = 0.1%)
    price_tolerance_pct: float = 0.005
    # Tolerance for quantity comparison (relative)
    qty_tolerance_pct: float = 0.001
    # Tolerance for balance comparison (absolute, in USDT)
    balance_tolerance_abs: float = 1.0
    # Maximum age (ms) for data to be considered fresh
    max_data_age_ms: int = 60_000
    # Auto-freeze on CRITICAL or higher
    auto_freeze_on_critical: bool = True
    # Maximum discrepancies before forcing freeze
    max_discrepancies_before_freeze: int = 5
    # Enable auto-correction for safe scenarios
    enable_auto_correct: bool = False


@dataclass
class Discrepancy:
    """A single discrepancy found during reconciliation / 单条差异记录"""
    discrepancy_id: str = ""
    disc_type: DiscrepancyType = DiscrepancyType.UNKNOWN
    severity: Severity = Severity.INFO
    symbol: str = ""
    description: str = ""
    local_value: Any = None
    remote_value: Any = None
    magnitude: float = 0.0
    recommended_action: IncidentAction = IncidentAction.LOG_ONLY
    detected_at_ms: int = 0

    def __post_init__(self):
        if not self.discrepancy_id:
            self.discrepancy_id = f"disc:{uuid.uuid4().hex[:12]}"
        if not self.detected_at_ms:
            self.detected_at_ms = int(time.time() * 1000)

    def to_dict(self) -> dict:
        return {
            "discrepancy_id": self.discrepancy_id,
            "type": self.disc_type.value,
            "severity": self.severity.value,
            "symbol": self.symbol,
            "description": self.description,
            "local_value": self.local_value,
            "remote_value": self.remote_value,
            "magnitude": self.magnitude,
            "recommended_action": self.recommended_action.value,
            "detected_at_ms": self.detected_at_ms,
        }


@dataclass
class ReconciliationReport:
    """Result of a full reconciliation cycle / 完整对账周期报告"""
    report_id: str = ""
    started_at_ms: int = 0
    completed_at_ms: int = 0
    overall_result: ReconciliationResult = ReconciliationResult.MATCH
    discrepancies: list = field(default_factory=list)
    orders_checked: int = 0
    positions_checked: int = 0
    fills_checked: int = 0
    actions_triggered: list = field(default_factory=list)
    paper_snapshot_ts_ms: int = 0
    remote_snapshot_ts_ms: int = 0

    def __post_init__(self):
        if not self.report_id:
            self.report_id = f"recon:{uuid.uuid4().hex[:12]}"
        if not self.started_at_ms:
            self.started_at_ms = int(time.time() * 1000)

    @property
    def is_consistent(self) -> bool:
        return self.overall_result in (
            ReconciliationResult.MATCH,
            ReconciliationResult.MISMATCH_MINOR,
        )

    @property
    def critical_count(self) -> int:
        return sum(
            1 for d in self.discrepancies
            if d.severity in (Severity.CRITICAL, Severity.FATAL)
        )

    def to_dict(self) -> dict:
        return {
            "report_id": self.report_id,
            "started_at_ms": self.started_at_ms,
            "completed_at_ms": self.completed_at_ms,
            "overall_result": self.overall_result.value,
            "is_consistent": self.is_consistent,
            "discrepancies": [d.to_dict() for d in self.discrepancies],
            "discrepancy_count": len(self.discrepancies),
            "critical_count": self.critical_count,
            "orders_checked": self.orders_checked,
            "positions_checked": self.positions_checked,
            "fills_checked": self.fills_checked,
            "actions_triggered": self.actions_triggered,
            "paper_snapshot_ts_ms": self.paper_snapshot_ts_ms,
            "remote_snapshot_ts_ms": self.remote_snapshot_ts_ms,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Reconciliation Engine / 对账引擎
# ═══════════════════════════════════════════════════════════════════════════════

class ReconciliationEngine:
    """
    Core reconciliation engine — compares paper vs demo/exchange state.
    核心对账引擎 — 比对纸上交易与 Demo/交易所状态。

    EX-02 §14 principles:
    - OMS/Execution cannot skip reconciliation
    - Account preservation > execution completion
    - Enter reconciling state on any uncertainty
    - Formal consistency judgment required

    Usage:
        engine = ReconciliationEngine(config, audit_callback=pipeline.make_callback("reconciliation"))
        report = engine.reconcile(paper_state, remote_state)
        if not report.is_consistent:
            # trigger freeze / manual review
    """

    def __init__(
        self,
        config: Optional[ReconciliationConfig] = None,
        audit_callback: Optional[Callable[[dict], None]] = None,
        incident_callback: Optional[Callable[[str, dict], None]] = None,
    ) -> None:
        self._config = config or ReconciliationConfig()
        self._audit_callback = audit_callback
        self._incident_callback = incident_callback
        self._lock = threading.Lock()
        self._history: list[ReconciliationReport] = []
        self._max_history = 1000
        self._total_runs = 0
        self._total_discrepancies = 0
        self._total_incidents = 0
        self._closed = False

    # ───────────────────────────────────────────────────────────────────────
    # Public API / 公开接口
    # ───────────────────────────────────────────────────────────────────────

    def reconcile(
        self,
        paper_state: dict,
        remote_state: dict,
    ) -> ReconciliationReport:
        """
        Run a full reconciliation cycle.
        执行完整对账周期。

        Args:
            paper_state: Local paper trading snapshot
                Expected keys: orders (list), positions (dict), fills (list),
                               snapshot_ts_ms (int), balances (dict)
            remote_state: Demo/exchange snapshot
                Same structure as paper_state

        Returns:
            ReconciliationReport with all discrepancies and actions
        """
        with self._lock:
            if self._closed:
                raise RuntimeError("ReconciliationEngine is closed")

            report = ReconciliationReport(
                paper_snapshot_ts_ms=paper_state.get("snapshot_ts_ms", 0),
                remote_snapshot_ts_ms=remote_state.get("snapshot_ts_ms", 0),
            )

            try:
                # 1. Check data freshness / 检查数据新鲜度
                freshness_issues = self._check_freshness(paper_state, remote_state)
                if freshness_issues:
                    report.discrepancies.extend(freshness_issues)

                # 2. Reconcile orders / 对账订单
                order_discs = self._reconcile_orders(
                    paper_state.get("orders", []),
                    remote_state.get("orders", []),
                )
                report.discrepancies.extend(order_discs)
                report.orders_checked = max(
                    len(paper_state.get("orders", [])),
                    len(remote_state.get("orders", [])),
                )

                # 3. Reconcile positions / 对账持仓
                pos_discs = self._reconcile_positions(
                    paper_state.get("positions", {}),
                    remote_state.get("positions", {}),
                )
                report.discrepancies.extend(pos_discs)
                report.positions_checked = max(
                    len(paper_state.get("positions", {})),
                    len(remote_state.get("positions", {})),
                )

                # 4. Reconcile fills / 对账成交
                fill_discs = self._reconcile_fills(
                    paper_state.get("fills", []),
                    remote_state.get("fills", []),
                )
                report.discrepancies.extend(fill_discs)
                report.fills_checked = max(
                    len(paper_state.get("fills", [])),
                    len(remote_state.get("fills", [])),
                )

                # 5. Reconcile balances / 对账余额
                bal_discs = self._reconcile_balances(
                    paper_state.get("balances", {}),
                    remote_state.get("balances", {}),
                )
                report.discrepancies.extend(bal_discs)

                # 6. Determine overall result / 判定整体结果
                report.overall_result = self._determine_overall_result(report.discrepancies)

                # 7. Determine and trigger actions / 判定并触发动作
                actions = self._determine_actions(report)
                report.actions_triggered = actions
                self._execute_actions(actions, report)

            except Exception as e:
                logger.error("Reconciliation error: %s", e)
                report.overall_result = ReconciliationResult.ERROR
                report.discrepancies.append(Discrepancy(
                    disc_type=DiscrepancyType.UNKNOWN,
                    severity=Severity.CRITICAL,
                    description=f"Reconciliation engine error: {e}",
                    recommended_action=IncidentAction.FREEZE_TRADING,
                ))

            report.completed_at_ms = int(time.time() * 1000)

            # Update stats / 更新统计
            self._total_runs += 1
            self._total_discrepancies += len(report.discrepancies)
            self._history.append(report)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

            # Audit / 审计
            self._emit_audit(report)

            return report

    def get_recent_reports(self, count: int = 10) -> list[dict]:
        """Get recent reconciliation reports / 获取最近的对账报告"""
        with self._lock:
            return [r.to_dict() for r in self._history[-count:]]

    def get_status(self) -> dict:
        """Engine status / 引擎状态"""
        with self._lock:
            last = self._history[-1].to_dict() if self._history else None
            return {
                "total_runs": self._total_runs,
                "total_discrepancies": self._total_discrepancies,
                "total_incidents": self._total_incidents,
                "history_size": len(self._history),
                "last_report": last,
                "config": {
                    "price_tolerance_pct": self._config.price_tolerance_pct,
                    "qty_tolerance_pct": self._config.qty_tolerance_pct,
                    "balance_tolerance_abs": self._config.balance_tolerance_abs,
                    "max_data_age_ms": self._config.max_data_age_ms,
                    "auto_freeze_on_critical": self._config.auto_freeze_on_critical,
                },
                "closed": self._closed,
            }

    def close(self) -> None:
        """Shut down the engine / 关闭引擎"""
        with self._lock:
            self._closed = True

    # ───────────────────────────────────────────────────────────────────────
    # Order Reconciliation / 订单对账
    # ───────────────────────────────────────────────────────────────────────

    def _reconcile_orders(
        self,
        paper_orders: list[dict],
        remote_orders: list[dict],
    ) -> list[Discrepancy]:
        """Compare paper orders vs remote orders / 比对纸上订单与远端订单"""
        discs: list[Discrepancy] = []

        paper_by_id = {o.get("order_id", ""): o for o in paper_orders}
        remote_by_id = {o.get("order_id", o.get("orderId", "")): o for o in remote_orders}

        all_ids = set(paper_by_id.keys()) | set(remote_by_id.keys())

        for oid in all_ids:
            p_order = paper_by_id.get(oid)
            r_order = remote_by_id.get(oid)

            if p_order and not r_order:
                discs.append(Discrepancy(
                    disc_type=DiscrepancyType.ORDER_MISSING,
                    severity=Severity.WARNING,
                    symbol=p_order.get("symbol", ""),
                    description=f"Order {oid} exists locally but not on remote",
                    local_value=p_order.get("state", "unknown"),
                    remote_value=None,
                    recommended_action=IncidentAction.ALERT,
                ))
            elif r_order and not p_order:
                discs.append(Discrepancy(
                    disc_type=DiscrepancyType.ORDER_MISSING,
                    severity=Severity.CRITICAL,
                    symbol=r_order.get("symbol", ""),
                    description=f"Order {oid} exists on remote but not locally",
                    local_value=None,
                    remote_value=r_order.get("state", r_order.get("orderStatus", "unknown")),
                    recommended_action=IncidentAction.MANUAL_REVIEW,
                ))
            else:
                # Both exist — compare state
                p_state = p_order.get("state", "")
                r_state = r_order.get("state", r_order.get("orderStatus", ""))

                if not self._states_equivalent(p_state, r_state):
                    discs.append(Discrepancy(
                        disc_type=DiscrepancyType.ORDER_STATE,
                        severity=Severity.CRITICAL,
                        symbol=p_order.get("symbol", ""),
                        description=f"Order {oid} state mismatch: local={p_state}, remote={r_state}",
                        local_value=p_state,
                        remote_value=r_state,
                        recommended_action=IncidentAction.MANUAL_REVIEW,
                    ))

        return discs

    def _states_equivalent(self, paper_state: str, remote_state: str) -> bool:
        """
        Check if paper state and remote state are equivalent.
        检查纸上状态与远端状态是否等价。

        Handles different naming conventions between Paper Engine and Bybit API.
        """
        # Normalize: strip prefix, lowercase
        def normalize(s: str) -> str:
            s = s.lower().replace("paper_order_", "").replace("paper_", "")
            # Bybit API status mapping
            mapping = {
                "new": "working",
                "partiallyfilled": "partially_filled",
                "partiallyfilledcanceled": "canceled",
                "deactivated": "canceled",
                "triggered": "working",
                "untriggered": "submitted",
            }
            return mapping.get(s, s)

        return normalize(paper_state) == normalize(remote_state)

    # ───────────────────────────────────────────────────────────────────────
    # Position Reconciliation / 持仓对账
    # ───────────────────────────────────────────────────────────────────────

    def _reconcile_positions(
        self,
        paper_positions: dict,
        remote_positions: dict,
    ) -> list[Discrepancy]:
        """
        Compare paper positions vs remote positions.
        比对纸上持仓与远端持仓。

        paper_positions: {symbol: {side, size, avg_entry_price, ...}}
        remote_positions: {symbol: {side, size, avgPrice, ...}}
        """
        discs: list[Discrepancy] = []

        all_symbols = set(paper_positions.keys()) | set(remote_positions.keys())

        for sym in all_symbols:
            p_pos = paper_positions.get(sym)
            r_pos = remote_positions.get(sym)

            if p_pos and not r_pos:
                p_size = float(p_pos.get("size", p_pos.get("qty", 0)))
                if p_size > 0:
                    discs.append(Discrepancy(
                        disc_type=DiscrepancyType.POSITION_MISSING,
                        severity=Severity.CRITICAL,
                        symbol=sym,
                        description=f"Position {sym} exists locally (size={p_size}) but not on remote",
                        local_value=p_size,
                        remote_value=0,
                        magnitude=p_size,
                        recommended_action=IncidentAction.MANUAL_REVIEW,
                    ))
            elif r_pos and not p_pos:
                r_size = float(r_pos.get("size", r_pos.get("qty", 0)))
                if r_size > 0:
                    discs.append(Discrepancy(
                        disc_type=DiscrepancyType.POSITION_MISSING,
                        severity=Severity.FATAL,
                        symbol=sym,
                        description=f"Position {sym} exists on remote (size={r_size}) but not locally",
                        local_value=0,
                        remote_value=r_size,
                        magnitude=r_size,
                        recommended_action=IncidentAction.FREEZE_TRADING,
                    ))
            else:
                # Both exist — compare size and side
                p_size = float(p_pos.get("size", p_pos.get("qty", 0)))
                r_size = float(r_pos.get("size", r_pos.get("qty", 0)))
                p_side = p_pos.get("side", "")
                r_side = r_pos.get("side", "")

                # Side check
                if p_side.lower() != r_side.lower() and (p_size > 0 or r_size > 0):
                    discs.append(Discrepancy(
                        disc_type=DiscrepancyType.POSITION_SIDE,
                        severity=Severity.FATAL,
                        symbol=sym,
                        description=f"Position {sym} side mismatch: local={p_side}, remote={r_side}",
                        local_value=p_side,
                        remote_value=r_side,
                        recommended_action=IncidentAction.FREEZE_TRADING,
                    ))

                # Size check
                if not self._within_tolerance(p_size, r_size, self._config.qty_tolerance_pct):
                    magnitude = abs(p_size - r_size)
                    severity = Severity.CRITICAL if magnitude > 0 else Severity.WARNING
                    discs.append(Discrepancy(
                        disc_type=DiscrepancyType.POSITION_SIZE,
                        severity=severity,
                        symbol=sym,
                        description=f"Position {sym} size mismatch: local={p_size}, remote={r_size}",
                        local_value=p_size,
                        remote_value=r_size,
                        magnitude=magnitude,
                        recommended_action=IncidentAction.MANUAL_REVIEW,
                    ))

        return discs

    # ───────────────────────────────────────────────────────────────────────
    # Fill Reconciliation / 成交对账
    # ───────────────────────────────────────────────────────────────────────

    def _reconcile_fills(
        self,
        paper_fills: list[dict],
        remote_fills: list[dict],
    ) -> list[Discrepancy]:
        """Compare paper fills vs remote fills / 比对纸上成交与远端成交"""
        discs: list[Discrepancy] = []

        # Count-level check
        if len(paper_fills) != len(remote_fills):
            diff = abs(len(paper_fills) - len(remote_fills))
            severity = Severity.CRITICAL if diff > 2 else Severity.WARNING
            discs.append(Discrepancy(
                disc_type=DiscrepancyType.FILL_COUNT,
                severity=severity,
                description=(
                    f"Fill count mismatch: local={len(paper_fills)}, "
                    f"remote={len(remote_fills)}"
                ),
                local_value=len(paper_fills),
                remote_value=len(remote_fills),
                magnitude=float(diff),
                recommended_action=IncidentAction.MANUAL_REVIEW if severity == Severity.CRITICAL else IncidentAction.ALERT,
            ))

        # Match fills by order_id + sequence for detailed comparison
        paper_by_order = self._group_fills_by_order(paper_fills)
        remote_by_order = self._group_fills_by_order(remote_fills)

        for oid in set(paper_by_order.keys()) | set(remote_by_order.keys()):
            p_fills = paper_by_order.get(oid, [])
            r_fills = remote_by_order.get(oid, [])

            # Aggregate comparison for this order
            p_total_qty = sum(self._extract_fill_qty(f) for f in p_fills)
            r_total_qty = sum(self._extract_fill_qty(f) for f in r_fills)

            if not self._within_tolerance(p_total_qty, r_total_qty, self._config.qty_tolerance_pct):
                discs.append(Discrepancy(
                    disc_type=DiscrepancyType.FILL_QUANTITY,
                    severity=Severity.CRITICAL,
                    description=f"Fill quantity mismatch for order {oid}: local={p_total_qty}, remote={r_total_qty}",
                    local_value=p_total_qty,
                    remote_value=r_total_qty,
                    magnitude=abs(p_total_qty - r_total_qty),
                    recommended_action=IncidentAction.MANUAL_REVIEW,
                ))

            # Average fill price comparison
            if p_fills and r_fills:
                p_avg = self._weighted_avg_price(p_fills)
                r_avg = self._weighted_avg_price(r_fills)
                if p_avg > 0 and r_avg > 0:
                    if not self._within_tolerance(p_avg, r_avg, self._config.price_tolerance_pct):
                        discs.append(Discrepancy(
                            disc_type=DiscrepancyType.FILL_PRICE,
                            severity=Severity.WARNING,
                            description=f"Fill price deviation for order {oid}: local={p_avg:.4f}, remote={r_avg:.4f}",
                            local_value=p_avg,
                            remote_value=r_avg,
                            magnitude=abs(p_avg - r_avg),
                            recommended_action=IncidentAction.LOG_ONLY,
                        ))

        return discs

    def _group_fills_by_order(self, fills: list[dict]) -> dict[str, list[dict]]:
        """Group fills by order_id / 按订单 ID 分组成交"""
        grouped: dict[str, list[dict]] = {}
        for f in fills:
            oid = f.get("order_id", f.get("orderId", "unknown"))
            grouped.setdefault(oid, []).append(f)
        return grouped

    def _weighted_avg_price(self, fills: list[dict]) -> float:
        """Calculate quantity-weighted average fill price / 计算加权平均成交价"""
        total_value = 0.0
        total_qty = 0.0
        for f in fills:
            qty = float(f.get("qty", f.get("fill_qty", f.get("execQty", 0))))
            price = float(f.get("price", f.get("fill_price", f.get("execPrice", 0))))
            total_value += qty * price
            total_qty += qty
        return total_value / total_qty if total_qty > 0 else 0.0

    def _extract_fill_qty(self, f: dict) -> float:
        """Extract fill quantity from a fill dict, trying multiple key conventions."""
        for key in ("qty", "fill_qty", "execQty"):
            if key in f:
                return float(f[key])
        return 0.0

    # ───────────────────────────────────────────────────────────────────────
    # Balance Reconciliation / 余额对账
    # ───────────────────────────────────────────────────────────────────────

    def _reconcile_balances(
        self,
        paper_balances: dict,
        remote_balances: dict,
    ) -> list[Discrepancy]:
        """Compare paper balances vs remote balances / 比对余额"""
        discs: list[Discrepancy] = []

        for coin in set(paper_balances.keys()) | set(remote_balances.keys()):
            p_bal = float(paper_balances.get(coin, 0))
            r_bal = float(remote_balances.get(coin, 0))

            diff = abs(p_bal - r_bal)
            if diff > self._config.balance_tolerance_abs:
                severity = Severity.CRITICAL if diff > self._config.balance_tolerance_abs * 10 else Severity.WARNING
                discs.append(Discrepancy(
                    disc_type=DiscrepancyType.BALANCE_DRIFT,
                    severity=severity,
                    symbol=coin,
                    description=f"Balance drift for {coin}: local={p_bal:.4f}, remote={r_bal:.4f}",
                    local_value=p_bal,
                    remote_value=r_bal,
                    magnitude=diff,
                    recommended_action=IncidentAction.ALERT if severity == Severity.WARNING else IncidentAction.MANUAL_REVIEW,
                ))

        return discs

    # ───────────────────────────────────────────────────────────────────────
    # Freshness Check / 新鲜度检查
    # ───────────────────────────────────────────────────────────────────────

    def _check_freshness(
        self,
        paper_state: dict,
        remote_state: dict,
    ) -> list[Discrepancy]:
        """Check if data is fresh enough for reliable reconciliation / 检查数据是否够新"""
        discs: list[Discrepancy] = []
        now_ms = int(time.time() * 1000)

        p_ts = paper_state.get("snapshot_ts_ms", 0)
        r_ts = remote_state.get("snapshot_ts_ms", 0)

        if p_ts and (now_ms - p_ts) > self._config.max_data_age_ms:
            discs.append(Discrepancy(
                disc_type=DiscrepancyType.UNKNOWN,
                severity=Severity.WARNING,
                description=f"Paper state snapshot is stale: age={(now_ms - p_ts)}ms",
                local_value=p_ts,
                recommended_action=IncidentAction.ALERT,
            ))

        if r_ts and (now_ms - r_ts) > self._config.max_data_age_ms:
            discs.append(Discrepancy(
                disc_type=DiscrepancyType.UNKNOWN,
                severity=Severity.WARNING,
                description=f"Remote state snapshot is stale: age={(now_ms - r_ts)}ms",
                remote_value=r_ts,
                recommended_action=IncidentAction.ALERT,
            ))

        return discs

    # ───────────────────────────────────────────────────────────────────────
    # Result Determination / 结果判定
    # ───────────────────────────────────────────────────────────────────────

    def _determine_overall_result(
        self,
        discrepancies: list[Discrepancy],
    ) -> ReconciliationResult:
        """Determine overall reconciliation result from discrepancies / 从差异判定整体结果"""
        if not discrepancies:
            return ReconciliationResult.MATCH

        max_severity = max(d.severity for d in discrepancies)

        if max_severity == Severity.FATAL:
            return ReconciliationResult.MISMATCH_MAJOR
        elif max_severity == Severity.CRITICAL:
            return ReconciliationResult.MISMATCH_MAJOR
        elif max_severity == Severity.WARNING:
            return ReconciliationResult.MISMATCH_MINOR
        else:
            return ReconciliationResult.MISMATCH_MINOR

    def _determine_actions(self, report: ReconciliationReport) -> list[str]:
        """Determine what actions to take based on reconciliation result / 判定应采取的动作"""
        actions: list[str] = []

        if report.overall_result == ReconciliationResult.MATCH:
            return actions

        fatal_count = sum(1 for d in report.discrepancies if d.severity == Severity.FATAL)
        critical_count = report.critical_count

        if fatal_count > 0:
            actions.append(IncidentAction.FREEZE_TRADING.value)
            actions.append(IncidentAction.MANUAL_REVIEW.value)
        elif critical_count > 0 and self._config.auto_freeze_on_critical:
            actions.append(IncidentAction.FREEZE_TRADING.value)
        elif len(report.discrepancies) >= self._config.max_discrepancies_before_freeze:
            actions.append(IncidentAction.FREEZE_TRADING.value)

        if critical_count > 0:
            actions.append(IncidentAction.ALERT.value)

        # Deduplicate
        return list(dict.fromkeys(actions))

    def _execute_actions(self, actions: list[str], report: ReconciliationReport) -> None:
        """Execute triggered actions / 执行触发的动作"""
        if not actions:
            return

        self._total_incidents += 1

        if self._incident_callback:
            for action in actions:
                try:
                    self._incident_callback(action, report.to_dict())
                except Exception as e:
                    logger.error("Incident callback error for %s: %s", action, e)

    # ───────────────────────────────────────────────────────────────────────
    # Audit / 审计
    # ───────────────────────────────────────────────────────────────────────

    def _emit_audit(self, report: ReconciliationReport) -> None:
        """Emit audit record for this reconciliation run / 发送审计记录"""
        if self._audit_callback:
            try:
                self._audit_callback({
                    "event_type": "reconciliation_completed",
                    "report_id": report.report_id,
                    "overall_result": report.overall_result.value,
                    "discrepancy_count": len(report.discrepancies),
                    "critical_count": report.critical_count,
                    "actions_triggered": report.actions_triggered,
                    "orders_checked": report.orders_checked,
                    "positions_checked": report.positions_checked,
                    "fills_checked": report.fills_checked,
                    "duration_ms": report.completed_at_ms - report.started_at_ms,
                })
            except Exception as e:
                logger.error("Audit callback error: %s", e)

    # ───────────────────────────────────────────────────────────────────────
    # Helpers / 工具函数
    # ───────────────────────────────────────────────────────────────────────

    def _within_tolerance(self, a: float, b: float, tolerance_pct: float) -> bool:
        """Check if two values are within relative tolerance / 检查两值是否在容差内"""
        if a == 0 and b == 0:
            return True
        if a == 0 or b == 0:
            return False
        return abs(a - b) / max(abs(a), abs(b)) <= tolerance_pct


# ═══════════════════════════════════════════════════════════════════════════════
# Scheduled Reconciliation Runner / 定时对账运行器
# ═══════════════════════════════════════════════════════════════════════════════

class ScheduledReconciler:
    """
    Runs reconciliation on a configurable interval.
    按配置间隔运行对账。

    Usage:
        def get_paper(): return paper_engine.export_state()
        def get_remote(): return demo_connector.get_state()

        reconciler = ScheduledReconciler(engine, get_paper, get_remote, interval_sec=30)
        reconciler.start()
        ...
        reconciler.stop()
    """

    def __init__(
        self,
        engine: ReconciliationEngine,
        paper_state_fn: Callable[[], dict],
        remote_state_fn: Callable[[], dict],
        interval_sec: float = 30.0,
    ) -> None:
        self._engine = engine
        self._paper_fn = paper_state_fn
        self._remote_fn = remote_state_fn
        self._interval = interval_sec
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start scheduled reconciliation / 启动定时对账"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="reconciler")
        self._thread.start()
        logger.info("ScheduledReconciler started (interval=%.1fs)", self._interval)

    def stop(self) -> None:
        """Stop scheduled reconciliation / 停止定时对账"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=self._interval + 2)
            self._thread = None
        logger.info("ScheduledReconciler stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    def _loop(self) -> None:
        """Main reconciliation loop / 对账主循环"""
        while self._running:
            try:
                paper = self._paper_fn()
                remote = self._remote_fn()
                report = self._engine.reconcile(paper, remote)
                if not report.is_consistent:
                    logger.warning(
                        "Reconciliation mismatch: %s (%d discrepancies)",
                        report.overall_result.value,
                        len(report.discrepancies),
                    )
            except Exception as e:
                logger.error("Scheduled reconciliation error: %s", e)

            # Sleep in small increments for responsive shutdown
            elapsed = 0.0
            while self._running and elapsed < self._interval:
                time.sleep(min(1.0, self._interval - elapsed))
                elapsed += 1.0
