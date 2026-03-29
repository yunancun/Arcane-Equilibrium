"""
Paper → Live Gate Formal Conditions Check / 纸盘→实盘闸门正式条件检查
Implementation of GAP-M4 per DOC-08 §11

MODULE_NOTE (中文):
  本模块实现从 Paper Trading 到 Supervised Live 的正式闸门系统：
  - PaperLiveGateConfig：闸门条件配置（时长、交易量、胜率、夏普比、回撤等）
  - GateCheckResult：闸门检查结果（通过/失败、各项条件检查结果、阻止原因、时间戳）
  - PaperLiveGate：闸门引擎，evaluate_gate() 检查所有条件
  - 各项单独检查方法：check_duration, check_trade_count, check_win_rate, check_sharpe,
    check_drawdown, check_profit_factor, check_reconciliation_pass, check_risk_incidents
  - Operator 批准要求：闸门通过仅是必要条件，不充分；Operator 必须明确批准
  - 线程安全、审计回调、序列化支持

MODULE_NOTE (English):
  Implements Paper→Live gate per DOC-08 §11:
  - PaperLiveGateConfig: gate criteria configuration
  - GateCheckResult: gate check results (passed bool, per-criterion results dict,
    blocking reasons list, timestamp)
  - PaperLiveGate engine: evaluate_gate() checks all conditions
  - Individual checks: duration, trade count, win rate, Sharpe, drawdown, profit factor,
    reconciliation, risk incidents
  - Operator approval required: gate pass is necessary but not sufficient
  - Thread-safe, audit callback support, serialization

Governance reference:
  EX-05 §4.1: Paper deployment autonomous, Live promotion gated
  DOC-08 §11: Paper→Live gate conditions (4 weeks + 500 trades + positive PnL +
    >30% win rate + Sharpe >0.5 + health checks + operator approval)
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Enums / 枚举
# ═══════════════════════════════════════════════════════════════════════════════

class GateStatus(Enum):
    """Status of the gate evaluation / 闸门评估状态"""
    NOT_EVALUATED = "not_evaluated"
    IN_PROGRESS = "in_progress"
    GATE_PASSED = "gate_passed"
    GATE_FAILED = "gate_failed"
    OPERATOR_APPROVAL_PENDING = "operator_approval_pending"
    OPERATOR_APPROVED = "operator_approved"
    OPERATOR_REJECTED = "operator_rejected"


class CheckStatus(Enum):
    """Status of individual criterion check / 单项条件检查状态"""
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration / 配置
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class PaperLiveGateConfig:
    """
    Configuration for Paper→Live gate criteria.
    纸盘→实盘闸门条件配置。

    Based on DOC-08 §11 and EX-05 §4.1.
    """
    # Paper trading duration / 纸盘交易时长
    min_paper_duration_weeks: int = 4

    # Trade volume / 交易量
    min_trades: int = 500

    # Profitability / 盈利能力
    min_win_rate_percent: float = 30.0  # > 30% win rate after fees / 含手续费后 > 30% 胜率
    min_net_pnl_threshold: float = 0.0   # Must be positive / 必须为正

    # Risk metrics / 风控指标
    min_sharpe_ratio: float = 0.5
    max_drawdown_percent: float = 100.0  # No hard limit in current phase / 当前阶段未设硬上限

    # Profitability quality / 盈利质量
    min_profit_factor: float = 1.2  # avg_win / avg_loss, or 1.2 if no losing trades / 平均赢/平均损或无亏损时为1.2

    # System health / 系统健康度
    min_audit_trail_completeness_percent: float = 99.0
    max_reconciliation_mismatch_percent: float = 0.1

    # Risk incidents / 风险事件
    max_consecutive_losses: int = 10  # Auto-pause threshold / 自动暂停阈值
    require_no_major_incidents: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict / 序列化为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PaperLiveGateConfig:
        """Deserialize from dict / 从字典反序列化"""
        # Only use known fields
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


# ═══════════════════════════════════════════════════════════════════════════════
# Check Result / 检查结果
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class CriterionCheckResult:
    """Result of a single criterion check / 单项条件检查结果"""
    criterion_name: str
    status: CheckStatus
    actual_value: Any = None
    required_value: Any = None
    passed: bool = False
    reason: Optional[str] = None
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_name": self.criterion_name,
            "status": self.status.value,
            "actual_value": self.actual_value,
            "required_value": self.required_value,
            "passed": self.passed,
            "reason": self.reason,
            "timestamp_ms": self.timestamp_ms,
        }


@dataclass
class GateCheckResult:
    """
    Result of complete gate evaluation.
    完整闸门评估结果。
    """
    passed: bool
    gate_status: GateStatus
    criteria_results: dict[str, CriterionCheckResult] = field(default_factory=dict)
    blocking_reasons: list[str] = field(default_factory=list)
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    operator_approval_required: bool = True
    operator_approval_status: Optional[GateStatus] = None
    operator_approval_reason: Optional[str] = None
    operator_approval_timestamp_ms: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "gate_status": self.gate_status.value,
            "criteria_results": {
                k: v.to_dict() for k, v in self.criteria_results.items()
            },
            "blocking_reasons": self.blocking_reasons,
            "timestamp_ms": self.timestamp_ms,
            "evaluated_at": self.evaluated_at,
            "operator_approval_required": self.operator_approval_required,
            "operator_approval_status": self.operator_approval_status.value
                if self.operator_approval_status else None,
            "operator_approval_reason": self.operator_approval_reason,
            "operator_approval_timestamp_ms": self.operator_approval_timestamp_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GateCheckResult:
        """Deserialize from dict / 从字典反序列化"""
        gate_status = GateStatus(data.get("gate_status", "not_evaluated"))
        result = cls(passed=data.get("passed", False), gate_status=gate_status)
        result.blocking_reasons = data.get("blocking_reasons", [])
        result.timestamp_ms = data.get("timestamp_ms", int(time.time() * 1000))
        result.evaluated_at = data.get("evaluated_at", "")
        result.operator_approval_required = data.get("operator_approval_required", True)

        if data.get("operator_approval_status"):
            result.operator_approval_status = GateStatus(data["operator_approval_status"])
        result.operator_approval_reason = data.get("operator_approval_reason")
        result.operator_approval_timestamp_ms = data.get("operator_approval_timestamp_ms")

        # Deserialize criterion results
        for k, v in data.get("criteria_results", {}).items():
            crit = CriterionCheckResult(
                criterion_name=v.get("criterion_name", k),
                status=CheckStatus(v.get("status", "pending")),
                actual_value=v.get("actual_value"),
                required_value=v.get("required_value"),
                passed=v.get("passed", False),
                reason=v.get("reason"),
                timestamp_ms=v.get("timestamp_ms", int(time.time() * 1000)),
            )
            result.criteria_results[k] = crit

        return result


# ═══════════════════════════════════════════════════════════════════════════════
# Paper→Live Gate Engine / 纸盘→实盘闸门引擎
# ═══════════════════════════════════════════════════════════════════════════════

class PaperLiveGate:
    """
    Gate evaluation engine for Paper→Live promotion.
    纸盘→实盘晋升闸门评估引擎。

    Thread-safe. Supports audit callback for compliance tracking.
    """

    def __init__(
        self,
        config: PaperLiveGateConfig = None,
        audit_callback: Optional[Callable[[str, dict[str, Any]], None]] = None,
    ):
        """
        Initialize gate engine.

        Args:
            config: Gate criteria configuration / 闸门条件配置
            audit_callback: Callback for audit events (event_type, event_data) / 审计回调
        """
        self.config = config or PaperLiveGateConfig()
        self.audit_callback = audit_callback
        self._lock = threading.Lock()
        self._last_check_result: Optional[GateCheckResult] = None
        self._operator_approval: Optional[GateCheckResult] = None

    def evaluate_gate(
        self,
        paper_start_time_ms: int,
        total_trades: int,
        win_rate_percent: float,
        net_pnl: float,
        sharpe_ratio: float,
        max_drawdown_percent: float,
        profit_factor: float,
        audit_trail_completeness_percent: float,
        reconciliation_mismatch_percent: float,
        consecutive_losses: int = 0,
        has_major_incidents: bool = False,
    ) -> GateCheckResult:
        """
        Evaluate all gate conditions.
        评估所有闸门条件。

        Returns GateCheckResult with per-criterion details and overall pass/fail.

        Args:
            paper_start_time_ms: Paper trading start timestamp / 纸盘交易开始时间戳(毫秒)
            total_trades: Number of completed round-trip trades / 已完成的往返交易数
            win_rate_percent: Win rate percentage after fees / 含手续费后的胜率百分比
            net_pnl: Net PnL after all costs / 含所有成本后的净PnL
            sharpe_ratio: Sharpe ratio / 夏普比
            max_drawdown_percent: Maximum drawdown percentage / 最大回撤百分比
            profit_factor: Average win / Average loss (or 1.2 if no losses) / 平均赢/平均损
            audit_trail_completeness_percent: % of operations with audit records / 有审计记录的操作百分比
            reconciliation_mismatch_percent: % of mismatches in reconciliation / 对账不匹配的百分比
            consecutive_losses: Current consecutive loss count / 当前连续亏损数
            has_major_incidents: Whether major incidents occurred / 是否发生重大事件

        Returns:
            GateCheckResult with all criterion results and overall gate status
        """
        with self._lock:
            result = GateCheckResult(
                passed=False,
                gate_status=GateStatus.IN_PROGRESS,
            )

            # Perform all checks / 执行所有检查
            self._check_duration(paper_start_time_ms, result)
            self._check_trade_count(total_trades, result)
            self._check_win_rate(win_rate_percent, result)
            self._check_net_pnl(net_pnl, result)
            self._check_sharpe(sharpe_ratio, result)
            self._check_drawdown(max_drawdown_percent, result)
            self._check_profit_factor(profit_factor, result)
            self._check_audit_trail(audit_trail_completeness_percent, result)
            self._check_reconciliation(reconciliation_mismatch_percent, result)
            self._check_consecutive_losses(consecutive_losses, result)
            self._check_major_incidents(has_major_incidents, result)

            # Aggregate results / 聚合结果
            all_passed = all(
                c.passed for c in result.criteria_results.values()
                if c.status != CheckStatus.NOT_APPLICABLE
            )

            result.passed = all_passed
            result.gate_status = (
                GateStatus.GATE_PASSED if all_passed
                else GateStatus.GATE_FAILED
            )

            # Determine operator approval requirement / 确定是否需要Operator批准
            if all_passed:
                result.operator_approval_required = True
                result.operator_approval_status = GateStatus.OPERATOR_APPROVAL_PENDING

            self._last_check_result = result
            self._emit_audit("gate_evaluated", result.to_dict())

            return result

    def get_gate_status(self) -> Optional[GateCheckResult]:
        """Get last gate evaluation result / 获取最后一次闸门评估结果"""
        with self._lock:
            return self._last_check_result

    def get_remaining_requirements(self) -> dict[str, Any]:
        """
        Get remaining requirements if gate not yet passed.
        获取尚未满足的要求。
        """
        if not self._last_check_result:
            return {
                "status": "not_evaluated",
                "message": "Gate not yet evaluated",
            }

        result = self._last_check_result
        remaining = {}

        for name, check in result.criteria_results.items():
            if not check.passed and check.status != CheckStatus.NOT_APPLICABLE:
                remaining[name] = {
                    "actual": check.actual_value,
                    "required": check.required_value,
                    "reason": check.reason,
                }

        return remaining

    def submit_operator_approval(
        self,
        approved: bool,
        operator_id: str,
        reason: Optional[str] = None,
    ) -> GateCheckResult:
        """
        Submit operator approval decision.
        提交Operator批准决定。

        Args:
            approved: True to approve, False to reject / True批准，False拒绝
            operator_id: Operator identifier for audit trail / Operator标识用于审计
            reason: Approval or rejection reason / 批准或拒绝的原因

        Returns:
            Updated GateCheckResult
        """
        with self._lock:
            if not self._last_check_result:
                raise ValueError("No gate evaluation to approve")

            if not self._last_check_result.passed:
                raise ValueError("Cannot approve gate that did not pass all criteria")

            result = self._last_check_result

            if approved:
                result.operator_approval_status = GateStatus.OPERATOR_APPROVED
                result.gate_status = GateStatus.OPERATOR_APPROVED
            else:
                result.operator_approval_status = GateStatus.OPERATOR_REJECTED
                result.gate_status = GateStatus.OPERATOR_REJECTED

            result.operator_approval_reason = reason
            result.operator_approval_timestamp_ms = int(time.time() * 1000)

            self._operator_approval = result
            self._emit_audit(
                "operator_approval_submitted",
                {
                    "operator_id": operator_id,
                    "approved": approved,
                    "reason": reason,
                    "timestamp_ms": result.operator_approval_timestamp_ms,
                },
            )

            return result

    # ═════════════════════════════════════════════════════════════════════════
    # Individual Criterion Checks / 单项条件检查
    # ═════════════════════════════════════════════════════════════════════════

    def _check_duration(
        self,
        paper_start_time_ms: int,
        result: GateCheckResult,
    ) -> None:
        """Check minimum paper trading duration / 检查最少纸盘交易时长"""
        now_ms = int(time.time() * 1000)
        duration_ms = now_ms - paper_start_time_ms
        duration_weeks = duration_ms / (1000 * 60 * 60 * 24 * 7)

        passed = duration_weeks >= self.config.min_paper_duration_weeks

        result.criteria_results["duration"] = CriterionCheckResult(
            criterion_name="Paper trading duration",
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            actual_value=round(duration_weeks, 2),
            required_value=self.config.min_paper_duration_weeks,
            passed=passed,
            reason=(
                f"Paper trading duration: {duration_weeks:.2f} weeks >= "
                f"{self.config.min_paper_duration_weeks} weeks"
                if passed
                else f"Paper trading duration: {duration_weeks:.2f} weeks < "
                f"{self.config.min_paper_duration_weeks} weeks required"
            ),
        )

        if not passed:
            result.blocking_reasons.append(
                f"Paper duration insufficient: {duration_weeks:.2f} weeks, "
                f"need {self.config.min_paper_duration_weeks} weeks"
            )

    def _check_trade_count(
        self,
        total_trades: int,
        result: GateCheckResult,
    ) -> None:
        """Check minimum number of trades / 检查最少交易数"""
        passed = total_trades >= self.config.min_trades

        result.criteria_results["trade_count"] = CriterionCheckResult(
            criterion_name="Minimum trade count",
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            actual_value=total_trades,
            required_value=self.config.min_trades,
            passed=passed,
            reason=(
                f"Total trades: {total_trades} >= {self.config.min_trades}"
                if passed
                else f"Total trades: {total_trades} < {self.config.min_trades}"
            ),
        )

        if not passed:
            result.blocking_reasons.append(
                f"Insufficient trades: {total_trades}, need {self.config.min_trades}"
            )

    def _check_win_rate(
        self,
        win_rate_percent: float,
        result: GateCheckResult,
    ) -> None:
        """Check minimum win rate / 检查最少胜率"""
        passed = win_rate_percent > self.config.min_win_rate_percent

        result.criteria_results["win_rate"] = CriterionCheckResult(
            criterion_name="Minimum win rate",
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            actual_value=round(win_rate_percent, 2),
            required_value=self.config.min_win_rate_percent,
            passed=passed,
            reason=(
                f"Win rate: {win_rate_percent:.2f}% > {self.config.min_win_rate_percent}%"
                if passed
                else f"Win rate: {win_rate_percent:.2f}% <= {self.config.min_win_rate_percent}%"
            ),
        )

        if not passed:
            result.blocking_reasons.append(
                f"Win rate too low: {win_rate_percent:.2f}%, "
                f"need > {self.config.min_win_rate_percent}%"
            )

    def _check_net_pnl(
        self,
        net_pnl: float,
        result: GateCheckResult,
    ) -> None:
        """Check net PnL is positive / 检查净PnL为正"""
        passed = net_pnl > self.config.min_net_pnl_threshold

        result.criteria_results["net_pnl"] = CriterionCheckResult(
            criterion_name="Positive net PnL",
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            actual_value=round(net_pnl, 2),
            required_value=self.config.min_net_pnl_threshold,
            passed=passed,
            reason=(
                f"Net PnL: {net_pnl:.2f} > {self.config.min_net_pnl_threshold}"
                if passed
                else f"Net PnL: {net_pnl:.2f} <= {self.config.min_net_pnl_threshold}"
            ),
        )

        if not passed:
            result.blocking_reasons.append(
                f"Net PnL not positive: {net_pnl:.2f}"
            )

    def _check_sharpe(
        self,
        sharpe_ratio: float,
        result: GateCheckResult,
    ) -> None:
        """Check minimum Sharpe ratio / 检查最少夏普比"""
        passed = sharpe_ratio >= self.config.min_sharpe_ratio

        result.criteria_results["sharpe_ratio"] = CriterionCheckResult(
            criterion_name="Minimum Sharpe ratio",
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            actual_value=round(sharpe_ratio, 2),
            required_value=self.config.min_sharpe_ratio,
            passed=passed,
            reason=(
                f"Sharpe ratio: {sharpe_ratio:.2f} >= {self.config.min_sharpe_ratio}"
                if passed
                else f"Sharpe ratio: {sharpe_ratio:.2f} < {self.config.min_sharpe_ratio}"
            ),
        )

        if not passed:
            result.blocking_reasons.append(
                f"Sharpe ratio too low: {sharpe_ratio:.2f}, "
                f"need >= {self.config.min_sharpe_ratio}"
            )

    def _check_drawdown(
        self,
        max_drawdown_percent: float,
        result: GateCheckResult,
    ) -> None:
        """Check maximum drawdown / 检查最大回撤"""
        passed = max_drawdown_percent <= self.config.max_drawdown_percent

        result.criteria_results["max_drawdown"] = CriterionCheckResult(
            criterion_name="Maximum drawdown",
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            actual_value=round(max_drawdown_percent, 2),
            required_value=self.config.max_drawdown_percent,
            passed=passed,
            reason=(
                f"Max drawdown: {max_drawdown_percent:.2f}% <= "
                f"{self.config.max_drawdown_percent}%"
                if passed
                else f"Max drawdown: {max_drawdown_percent:.2f}% > "
                f"{self.config.max_drawdown_percent}%"
            ),
        )

        if not passed:
            result.blocking_reasons.append(
                f"Drawdown exceeded: {max_drawdown_percent:.2f}%, "
                f"limit {self.config.max_drawdown_percent}%"
            )

    def _check_profit_factor(
        self,
        profit_factor: float,
        result: GateCheckResult,
    ) -> None:
        """Check profit factor (avg win / avg loss) / 检查利润因子(平均赢/平均损)"""
        passed = profit_factor >= self.config.min_profit_factor

        result.criteria_results["profit_factor"] = CriterionCheckResult(
            criterion_name="Minimum profit factor",
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            actual_value=round(profit_factor, 2),
            required_value=self.config.min_profit_factor,
            passed=passed,
            reason=(
                f"Profit factor: {profit_factor:.2f} >= {self.config.min_profit_factor}"
                if passed
                else f"Profit factor: {profit_factor:.2f} < {self.config.min_profit_factor}"
            ),
        )

        if not passed:
            result.blocking_reasons.append(
                f"Profit factor too low: {profit_factor:.2f}, "
                f"need >= {self.config.min_profit_factor}"
            )

    def _check_audit_trail(
        self,
        completeness_percent: float,
        result: GateCheckResult,
    ) -> None:
        """Check audit trail completeness / 检查审计链完整性"""
        passed = completeness_percent >= self.config.min_audit_trail_completeness_percent

        result.criteria_results["audit_trail_completeness"] = CriterionCheckResult(
            criterion_name="Audit trail completeness",
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            actual_value=round(completeness_percent, 2),
            required_value=self.config.min_audit_trail_completeness_percent,
            passed=passed,
            reason=(
                f"Audit trail completeness: {completeness_percent:.2f}% >= "
                f"{self.config.min_audit_trail_completeness_percent}%"
                if passed
                else f"Audit trail completeness: {completeness_percent:.2f}% < "
                f"{self.config.min_audit_trail_completeness_percent}%"
            ),
        )

        if not passed:
            result.blocking_reasons.append(
                f"Audit trail incomplete: {completeness_percent:.2f}%, "
                f"need >= {self.config.min_audit_trail_completeness_percent}%"
            )

    def _check_reconciliation(
        self,
        mismatch_percent: float,
        result: GateCheckResult,
    ) -> None:
        """Check reconciliation accuracy / 检查对账精度"""
        passed = mismatch_percent <= self.config.max_reconciliation_mismatch_percent

        result.criteria_results["reconciliation_accuracy"] = CriterionCheckResult(
            criterion_name="Reconciliation accuracy",
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            actual_value=round(mismatch_percent, 4),
            required_value=self.config.max_reconciliation_mismatch_percent,
            passed=passed,
            reason=(
                f"Reconciliation mismatch: {mismatch_percent:.4f}% <= "
                f"{self.config.max_reconciliation_mismatch_percent}%"
                if passed
                else f"Reconciliation mismatch: {mismatch_percent:.4f}% > "
                f"{self.config.max_reconciliation_mismatch_percent}%"
            ),
        )

        if not passed:
            result.blocking_reasons.append(
                f"Reconciliation mismatches: {mismatch_percent:.4f}%, "
                f"max {self.config.max_reconciliation_mismatch_percent}%"
            )

    def _check_consecutive_losses(
        self,
        consecutive_losses: int,
        result: GateCheckResult,
    ) -> None:
        """Check consecutive losses don't exceed threshold / 检查连续亏损未超阈值"""
        passed = consecutive_losses < self.config.max_consecutive_losses

        result.criteria_results["consecutive_losses"] = CriterionCheckResult(
            criterion_name="Consecutive losses threshold",
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            actual_value=consecutive_losses,
            required_value=self.config.max_consecutive_losses,
            passed=passed,
            reason=(
                f"Consecutive losses: {consecutive_losses} < "
                f"{self.config.max_consecutive_losses}"
                if passed
                else f"Consecutive losses: {consecutive_losses} >= "
                f"{self.config.max_consecutive_losses}"
            ),
        )

        if not passed:
            result.blocking_reasons.append(
                f"Consecutive losses threshold breached: {consecutive_losses} >= "
                f"{self.config.max_consecutive_losses}"
            )

    def _check_major_incidents(
        self,
        has_major_incidents: bool,
        result: GateCheckResult,
    ) -> None:
        """Check no major incidents occurred / 检查无重大事件"""
        passed = not has_major_incidents or not self.config.require_no_major_incidents

        result.criteria_results["major_incidents"] = CriterionCheckResult(
            criterion_name="No major incidents",
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            actual_value=has_major_incidents,
            required_value=False if self.config.require_no_major_incidents else None,
            passed=passed,
            reason=(
                "No major incidents detected" if passed
                else "Major incident(s) detected in paper trading"
            ),
        )

        if not passed:
            result.blocking_reasons.append(
                "Major incident(s) detected during paper trading"
            )

    # ═════════════════════════════════════════════════════════════════════════
    # Audit and Serialization / 审计和序列化
    # ═════════════════════════════════════════════════════════════════════════

    def _emit_audit(self, event_type: str, event_data: dict[str, Any]) -> None:
        """Emit audit event / 发出审计事件"""
        if self.audit_callback:
            try:
                self.audit_callback(event_type, event_data)
            except Exception as e:
                logger.warning(f"Audit callback failed: {e}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize gate state to dict / 序列化闸门状态为字典"""
        return {
            "config": self.config.to_dict(),
            "last_check_result": (
                self._last_check_result.to_dict()
                if self._last_check_result
                else None
            ),
            "operator_approval": (
                self._operator_approval.to_dict()
                if self._operator_approval
                else None
            ),
        }

    def to_json(self) -> str:
        """Serialize to JSON / 序列化为JSON"""
        return json.dumps(self.to_dict(), indent=2)
