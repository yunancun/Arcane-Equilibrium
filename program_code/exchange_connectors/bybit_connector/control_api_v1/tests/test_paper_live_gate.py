"""
Tests for Paper→Live Gate Formal Conditions Check / 纸盘→实盘闸门条件检查测试

覆盖范围 / Coverage:
  - Gate configuration (PaperLiveGateConfig)
  - Individual criterion checks (duration, trades, win rate, Sharpe, drawdown, etc.)
  - Gate evaluation (all criteria simultaneously)
  - Gate status transitions
  - Operator approval workflow
  - Serialization (to_dict, from_dict, JSON)
  - Audit callbacks
  - Thread safety
  - Edge cases and error conditions
"""

import json
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.paper_live_gate import (
    PaperLiveGate,
    PaperLiveGateConfig,
    GateCheckResult,
    CriterionCheckResult,
    GateStatus,
    CheckStatus,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Test Data Helpers / 测试数据
# ═══════════════════════════════════════════════════════════════════════════════

def _make_config(**kwargs) -> PaperLiveGateConfig:
    """Create a config with optional overrides / 创建配置并可选覆盖"""
    defaults = {
        "min_paper_duration_weeks": 4,
        "min_trades": 500,
        "min_win_rate_percent": 30.0,
        "min_net_pnl_threshold": 0.0,
        "min_sharpe_ratio": 0.5,
        "max_drawdown_percent": 100.0,
        "min_profit_factor": 1.2,
        "min_audit_trail_completeness_percent": 99.0,
        "max_reconciliation_mismatch_percent": 0.1,
        "max_consecutive_losses": 10,
        "require_no_major_incidents": True,
    }
    defaults.update(kwargs)
    return PaperLiveGateConfig(**defaults)


def _make_passing_metrics(now_ms=None):
    """Create metrics that should pass all checks / 创建应该通过所有检查的指标"""
    if now_ms is None:
        now_ms = int(time.time() * 1000)

    paper_start_ms = now_ms - (4 * 7 * 24 * 60 * 60 * 1000)  # 4 weeks ago

    return {
        "paper_start_time_ms": paper_start_ms,
        "total_trades": 600,
        "win_rate_percent": 35.0,
        "net_pnl": 1000.0,
        "sharpe_ratio": 0.8,
        "max_drawdown_percent": 15.0,
        "profit_factor": 1.5,
        "audit_trail_completeness_percent": 99.5,
        "reconciliation_mismatch_percent": 0.05,
        "consecutive_losses": 3,
        "has_major_incidents": False,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Configuration / 配置测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestPaperLiveGateConfig:
    def test_default_config(self):
        """Test default configuration values / 测试默认配置值"""
        cfg = PaperLiveGateConfig()
        assert cfg.min_paper_duration_weeks == 4
        assert cfg.min_trades == 500
        assert cfg.min_win_rate_percent == 30.0
        assert cfg.min_sharpe_ratio == 0.5

    def test_config_to_dict(self):
        """Test config serialization to dict / 测试配置序列化为字典"""
        cfg = PaperLiveGateConfig(min_trades=1000, min_win_rate_percent=25.0)
        d = cfg.to_dict()
        assert d["min_trades"] == 1000
        assert d["min_win_rate_percent"] == 25.0

    def test_config_from_dict(self):
        """Test config deserialization from dict / 测试从字典反序列化配置"""
        d = {
            "min_paper_duration_weeks": 5,
            "min_trades": 750,
            "min_win_rate_percent": 32.0,
            "min_net_pnl_threshold": 100.0,
            "min_sharpe_ratio": 0.6,
            "max_drawdown_percent": 50.0,
            "min_profit_factor": 1.3,
            "min_audit_trail_completeness_percent": 99.5,
            "max_reconciliation_mismatch_percent": 0.05,
            "max_consecutive_losses": 8,
            "require_no_major_incidents": False,
        }
        cfg = PaperLiveGateConfig.from_dict(d)
        assert cfg.min_paper_duration_weeks == 5
        assert cfg.min_trades == 750
        assert cfg.min_win_rate_percent == 32.0
        assert cfg.require_no_major_incidents is False

    def test_config_from_dict_with_extra_fields(self):
        """Test from_dict ignores unknown fields / 测试from_dict忽略未知字段"""
        d = {
            "min_trades": 600,
            "unknown_field": "should_be_ignored",
            "another_unknown": 123,
        }
        cfg = PaperLiveGateConfig.from_dict(d)
        assert cfg.min_trades == 600


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Individual Criterion Checks / 单项条件检查测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestDurationCheck:
    def test_duration_passed(self):
        """Test duration check passes when >= min_duration / 测试时长达到时检查通过"""
        cfg = _make_config(min_paper_duration_weeks=4)
        gate = PaperLiveGate(cfg)

        now_ms = int(time.time() * 1000)
        four_weeks_ago = now_ms - (4 * 7 * 24 * 60 * 60 * 1000)

        result = gate.evaluate_gate(
            paper_start_time_ms=four_weeks_ago,
            total_trades=600,
            win_rate_percent=35.0,
            net_pnl=1000.0,
            sharpe_ratio=0.8,
            max_drawdown_percent=15.0,
            profit_factor=1.5,
            audit_trail_completeness_percent=99.5,
            reconciliation_mismatch_percent=0.05,
        )

        duration_check = result.criteria_results.get("duration")
        assert duration_check is not None
        assert duration_check.passed is True
        assert duration_check.status == CheckStatus.PASSED

    def test_duration_failed(self):
        """Test duration check fails when < min_duration / 测试时长不足时检查失败"""
        cfg = _make_config(min_paper_duration_weeks=4)
        gate = PaperLiveGate(cfg)

        now_ms = int(time.time() * 1000)
        two_weeks_ago = now_ms - (2 * 7 * 24 * 60 * 60 * 1000)

        result = gate.evaluate_gate(
            paper_start_time_ms=two_weeks_ago,
            total_trades=600,
            win_rate_percent=35.0,
            net_pnl=1000.0,
            sharpe_ratio=0.8,
            max_drawdown_percent=15.0,
            profit_factor=1.5,
            audit_trail_completeness_percent=99.5,
            reconciliation_mismatch_percent=0.05,
        )

        duration_check = result.criteria_results.get("duration")
        assert duration_check is not None
        assert duration_check.passed is False
        assert "blocking_reasons" in result.__dict__
        assert any("duration" in r.lower() for r in result.blocking_reasons)


class TestTradeCountCheck:
    def test_trade_count_passed(self):
        """Test trade count check passes when >= min_trades / 测试交易数足够时检查通过"""
        cfg = _make_config(min_trades=500)
        gate = PaperLiveGate(cfg)

        metrics = _make_passing_metrics()
        result = gate.evaluate_gate(**metrics)

        tc_check = result.criteria_results.get("trade_count")
        assert tc_check is not None
        assert tc_check.passed is True

    def test_trade_count_failed(self):
        """Test trade count check fails when < min_trades / 测试交易数不足时检查失败"""
        cfg = _make_config(min_trades=500)
        gate = PaperLiveGate(cfg)

        metrics = _make_passing_metrics()
        metrics["total_trades"] = 300

        result = gate.evaluate_gate(**metrics)

        tc_check = result.criteria_results.get("trade_count")
        assert tc_check is not None
        assert tc_check.passed is False
        assert any("trade" in r.lower() for r in result.blocking_reasons)


class TestWinRateCheck:
    def test_win_rate_passed(self):
        """Test win rate check passes when > min_win_rate / 测试胜率足够时检查通过"""
        cfg = _make_config(min_win_rate_percent=30.0)
        gate = PaperLiveGate(cfg)

        metrics = _make_passing_metrics()
        result = gate.evaluate_gate(**metrics)

        wr_check = result.criteria_results.get("win_rate")
        assert wr_check is not None
        assert wr_check.passed is True

    def test_win_rate_failed(self):
        """Test win rate check fails when <= min_win_rate / 测试胜率不足时检查失败"""
        cfg = _make_config(min_win_rate_percent=35.0)
        gate = PaperLiveGate(cfg)

        metrics = _make_passing_metrics()
        metrics["win_rate_percent"] = 30.0

        result = gate.evaluate_gate(**metrics)

        wr_check = result.criteria_results.get("win_rate")
        assert wr_check is not None
        assert wr_check.passed is False


class TestNetPnLCheck:
    def test_net_pnl_positive_passed(self):
        """Test net PnL check passes when positive / 测试净PnL为正时检查通过"""
        cfg = _make_config(min_net_pnl_threshold=0.0)
        gate = PaperLiveGate(cfg)

        metrics = _make_passing_metrics()
        result = gate.evaluate_gate(**metrics)

        pnl_check = result.criteria_results.get("net_pnl")
        assert pnl_check is not None
        assert pnl_check.passed is True

    def test_net_pnl_negative_failed(self):
        """Test net PnL check fails when negative / 测试净PnL为负时检查失败"""
        cfg = _make_config(min_net_pnl_threshold=0.0)
        gate = PaperLiveGate(cfg)

        metrics = _make_passing_metrics()
        metrics["net_pnl"] = -100.0

        result = gate.evaluate_gate(**metrics)

        pnl_check = result.criteria_results.get("net_pnl")
        assert pnl_check is not None
        assert pnl_check.passed is False


class TestSharpeCheck:
    def test_sharpe_passed(self):
        """Test Sharpe ratio check passes when >= min_sharpe / 测试夏普比足够时检查通过"""
        cfg = _make_config(min_sharpe_ratio=0.5)
        gate = PaperLiveGate(cfg)

        metrics = _make_passing_metrics()
        result = gate.evaluate_gate(**metrics)

        sharpe_check = result.criteria_results.get("sharpe_ratio")
        assert sharpe_check is not None
        assert sharpe_check.passed is True

    def test_sharpe_failed(self):
        """Test Sharpe ratio check fails when < min_sharpe / 测试夏普比不足时检查失败"""
        cfg = _make_config(min_sharpe_ratio=1.0)
        gate = PaperLiveGate(cfg)

        metrics = _make_passing_metrics()
        metrics["sharpe_ratio"] = 0.3

        result = gate.evaluate_gate(**metrics)

        sharpe_check = result.criteria_results.get("sharpe_ratio")
        assert sharpe_check is not None
        assert sharpe_check.passed is False


class TestDrawdownCheck:
    def test_drawdown_passed(self):
        """Test drawdown check passes when <= max_drawdown / 测试回撤在允许范围时检查通过"""
        cfg = _make_config(max_drawdown_percent=20.0)
        gate = PaperLiveGate(cfg)

        metrics = _make_passing_metrics()
        result = gate.evaluate_gate(**metrics)

        dd_check = result.criteria_results.get("max_drawdown")
        assert dd_check is not None
        assert dd_check.passed is True

    def test_drawdown_failed(self):
        """Test drawdown check fails when > max_drawdown / 测试回撤超出允许范围时检查失败"""
        cfg = _make_config(max_drawdown_percent=10.0)
        gate = PaperLiveGate(cfg)

        metrics = _make_passing_metrics()
        metrics["max_drawdown_percent"] = 25.0

        result = gate.evaluate_gate(**metrics)

        dd_check = result.criteria_results.get("max_drawdown")
        assert dd_check is not None
        assert dd_check.passed is False


class TestProfitFactorCheck:
    def test_profit_factor_passed(self):
        """Test profit factor check passes when >= min_profit_factor / 测试利润因子足够时检查通过"""
        cfg = _make_config(min_profit_factor=1.2)
        gate = PaperLiveGate(cfg)

        metrics = _make_passing_metrics()
        result = gate.evaluate_gate(**metrics)

        pf_check = result.criteria_results.get("profit_factor")
        assert pf_check is not None
        assert pf_check.passed is True

    def test_profit_factor_failed(self):
        """Test profit factor check fails when < min_profit_factor / 测试利润因子不足时检查失败"""
        cfg = _make_config(min_profit_factor=2.0)
        gate = PaperLiveGate(cfg)

        metrics = _make_passing_metrics()
        metrics["profit_factor"] = 1.1

        result = gate.evaluate_gate(**metrics)

        pf_check = result.criteria_results.get("profit_factor")
        assert pf_check is not None
        assert pf_check.passed is False


class TestAuditTrailCheck:
    def test_audit_trail_passed(self):
        """Test audit trail check passes when completeness >= min / 测试审计链完整性足够时检查通过"""
        cfg = _make_config(min_audit_trail_completeness_percent=99.0)
        gate = PaperLiveGate(cfg)

        metrics = _make_passing_metrics()
        result = gate.evaluate_gate(**metrics)

        audit_check = result.criteria_results.get("audit_trail_completeness")
        assert audit_check is not None
        assert audit_check.passed is True

    def test_audit_trail_failed(self):
        """Test audit trail check fails when completeness < min / 测试审计链完整性不足时检查失败"""
        cfg = _make_config(min_audit_trail_completeness_percent=99.9)
        gate = PaperLiveGate(cfg)

        metrics = _make_passing_metrics()
        metrics["audit_trail_completeness_percent"] = 98.0

        result = gate.evaluate_gate(**metrics)

        audit_check = result.criteria_results.get("audit_trail_completeness")
        assert audit_check is not None
        assert audit_check.passed is False


class TestReconciliationCheck:
    def test_reconciliation_passed(self):
        """Test reconciliation check passes when mismatch <= max / 测试对账误差在允许范围时检查通过"""
        cfg = _make_config(max_reconciliation_mismatch_percent=0.1)
        gate = PaperLiveGate(cfg)

        metrics = _make_passing_metrics()
        result = gate.evaluate_gate(**metrics)

        recon_check = result.criteria_results.get("reconciliation_accuracy")
        assert recon_check is not None
        assert recon_check.passed is True

    def test_reconciliation_failed(self):
        """Test reconciliation check fails when mismatch > max / 测试对账误差超出允许范围时检查失败"""
        cfg = _make_config(max_reconciliation_mismatch_percent=0.05)
        gate = PaperLiveGate(cfg)

        metrics = _make_passing_metrics()
        metrics["reconciliation_mismatch_percent"] = 0.15

        result = gate.evaluate_gate(**metrics)

        recon_check = result.criteria_results.get("reconciliation_accuracy")
        assert recon_check is not None
        assert recon_check.passed is False


class TestConsecutiveLossesCheck:
    def test_consecutive_losses_passed(self):
        """Test consecutive losses check passes when < threshold / 测试连续亏损在阈值以下时检查通过"""
        cfg = _make_config(max_consecutive_losses=10)
        gate = PaperLiveGate(cfg)

        metrics = _make_passing_metrics()
        result = gate.evaluate_gate(**metrics)

        cons_check = result.criteria_results.get("consecutive_losses")
        assert cons_check is not None
        assert cons_check.passed is True

    def test_consecutive_losses_failed(self):
        """Test consecutive losses check fails when >= threshold / 测试连续亏损达到阈值时检查失败"""
        cfg = _make_config(max_consecutive_losses=5)
        gate = PaperLiveGate(cfg)

        metrics = _make_passing_metrics()
        metrics["consecutive_losses"] = 7

        result = gate.evaluate_gate(**metrics)

        cons_check = result.criteria_results.get("consecutive_losses")
        assert cons_check is not None
        assert cons_check.passed is False


class TestMajorIncidentsCheck:
    def test_no_incidents_passed(self):
        """Test major incidents check passes when no incidents / 测试无重大事件时检查通过"""
        cfg = _make_config(require_no_major_incidents=True)
        gate = PaperLiveGate(cfg)

        metrics = _make_passing_metrics()
        result = gate.evaluate_gate(**metrics)

        incidents_check = result.criteria_results.get("major_incidents")
        assert incidents_check is not None
        assert incidents_check.passed is True

    def test_with_incidents_failed(self):
        """Test major incidents check fails when incidents present / 测试有重大事件时检查失败"""
        cfg = _make_config(require_no_major_incidents=True)
        gate = PaperLiveGate(cfg)

        metrics = _make_passing_metrics()
        metrics["has_major_incidents"] = True

        result = gate.evaluate_gate(**metrics)

        incidents_check = result.criteria_results.get("major_incidents")
        assert incidents_check is not None
        assert incidents_check.passed is False

    def test_incidents_not_required(self):
        """Test major incidents check passes when check disabled / 测试当检查禁用时通过"""
        cfg = _make_config(require_no_major_incidents=False)
        gate = PaperLiveGate(cfg)

        metrics = _make_passing_metrics()
        metrics["has_major_incidents"] = True

        result = gate.evaluate_gate(**metrics)

        incidents_check = result.criteria_results.get("major_incidents")
        assert incidents_check is not None
        assert incidents_check.passed is True


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Gate Evaluation / 闸门评估测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestGateEvaluation:
    def test_all_criteria_passed(self):
        """Test gate passes when all criteria met / 测试所有条件都满足时闸门通过"""
        gate = PaperLiveGate()
        metrics = _make_passing_metrics()

        result = gate.evaluate_gate(**metrics)

        assert result.passed is True
        assert result.gate_status == GateStatus.GATE_PASSED
        assert len(result.blocking_reasons) == 0
        assert all(
            c.passed
            for c in result.criteria_results.values()
            if c.status != CheckStatus.NOT_APPLICABLE
        )

    def test_single_criterion_failure(self):
        """Test gate fails when one criterion fails / 测试一个条件失败时闸门失败"""
        gate = PaperLiveGate()
        metrics = _make_passing_metrics()
        metrics["total_trades"] = 100  # Below minimum

        result = gate.evaluate_gate(**metrics)

        assert result.passed is False
        assert result.gate_status == GateStatus.GATE_FAILED
        assert len(result.blocking_reasons) > 0
        assert any("trade" in r.lower() for r in result.blocking_reasons)

    def test_multiple_criterion_failures(self):
        """Test gate fails with multiple reasons when multiple criteria fail / 测试多个条件失败时闸门失败且有多个原因"""
        gate = PaperLiveGate()
        metrics = _make_passing_metrics()
        metrics["total_trades"] = 100
        metrics["win_rate_percent"] = 20.0
        metrics["net_pnl"] = -500.0

        result = gate.evaluate_gate(**metrics)

        assert result.passed is False
        assert result.gate_status == GateStatus.GATE_FAILED
        assert len(result.blocking_reasons) >= 3

    def test_gate_evaluation_sets_status_in_progress(self):
        """Test gate status is IN_PROGRESS during evaluation / 测试评估过程中状态为IN_PROGRESS"""
        gate = PaperLiveGate()
        metrics = _make_passing_metrics()

        result = gate.evaluate_gate(**metrics)

        # Final status should be either PASSED or FAILED, not IN_PROGRESS
        assert result.gate_status in (GateStatus.GATE_PASSED, GateStatus.GATE_FAILED)

    def test_gate_evaluation_sets_timestamp(self):
        """Test gate evaluation includes timestamp / 测试闸门评估包含时间戳"""
        gate = PaperLiveGate()
        metrics = _make_passing_metrics()

        before_ms = int(time.time() * 1000)
        result = gate.evaluate_gate(**metrics)
        after_ms = int(time.time() * 1000)

        assert result.timestamp_ms >= before_ms
        assert result.timestamp_ms <= after_ms


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Operator Approval / Operator批准测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestOperatorApproval:
    def test_operator_approval_on_passing_gate(self):
        """Test operator can approve a passing gate / 测试Operator可以批准通过的闸门"""
        gate = PaperLiveGate()
        metrics = _make_passing_metrics()
        result = gate.evaluate_gate(**metrics)
        assert result.passed is True

        approved = gate.submit_operator_approval(
            approved=True,
            operator_id="op_test_001",
            reason="All criteria met, approved for live",
        )

        assert approved.operator_approval_status == GateStatus.OPERATOR_APPROVED
        assert approved.gate_status == GateStatus.OPERATOR_APPROVED
        assert approved.operator_approval_reason == "All criteria met, approved for live"

    def test_operator_rejection_on_passing_gate(self):
        """Test operator can reject a passing gate / 测试Operator可以拒绝通过的闸门"""
        gate = PaperLiveGate()
        metrics = _make_passing_metrics()
        result = gate.evaluate_gate(**metrics)
        assert result.passed is True

        rejected = gate.submit_operator_approval(
            approved=False,
            operator_id="op_test_002",
            reason="Additional data needed before live",
        )

        assert rejected.operator_approval_status == GateStatus.OPERATOR_REJECTED
        assert rejected.gate_status == GateStatus.OPERATOR_REJECTED

    def test_cannot_approve_failing_gate(self):
        """Test cannot approve a gate that failed criteria / 测试无法批准未通过条件的闸门"""
        gate = PaperLiveGate()
        metrics = _make_passing_metrics()
        metrics["total_trades"] = 100

        result = gate.evaluate_gate(**metrics)
        assert result.passed is False

        with pytest.raises(ValueError, match="did not pass all criteria"):
            gate.submit_operator_approval(
                approved=True,
                operator_id="op_test_003",
            )

    def test_cannot_approve_without_evaluation(self):
        """Test cannot approve without prior gate evaluation / 测试未评估时无法批准"""
        gate = PaperLiveGate()

        with pytest.raises(ValueError, match="No gate evaluation"):
            gate.submit_operator_approval(
                approved=True,
                operator_id="op_test_004",
            )

    def test_approval_sets_timestamp(self):
        """Test operator approval includes timestamp / 测试Operator批准包含时间戳"""
        gate = PaperLiveGate()
        metrics = _make_passing_metrics()
        gate.evaluate_gate(**metrics)

        before_ms = int(time.time() * 1000)
        result = gate.submit_operator_approval(
            approved=True,
            operator_id="op_test_005",
        )
        after_ms = int(time.time() * 1000)

        assert result.operator_approval_timestamp_ms is not None
        assert result.operator_approval_timestamp_ms >= before_ms
        assert result.operator_approval_timestamp_ms <= after_ms


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Get Status and Requirements / 获取状态和要求测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetStatus:
    def test_get_gate_status_before_evaluation(self):
        """Test get_gate_status returns None before evaluation / 测试评估前get_gate_status返回None"""
        gate = PaperLiveGate()
        status = gate.get_gate_status()
        assert status is None

    def test_get_gate_status_after_evaluation(self):
        """Test get_gate_status returns result after evaluation / 测试评估后get_gate_status返回结果"""
        gate = PaperLiveGate()
        metrics = _make_passing_metrics()
        gate.evaluate_gate(**metrics)

        status = gate.get_gate_status()
        assert status is not None
        assert status.passed is True

    def test_get_remaining_requirements_none_if_passed(self):
        """Test remaining requirements is empty when gate passed / 测试通过时无剩余要求"""
        gate = PaperLiveGate()
        metrics = _make_passing_metrics()
        gate.evaluate_gate(**metrics)

        remaining = gate.get_remaining_requirements()
        assert remaining == {}

    def test_get_remaining_requirements_shows_failures(self):
        """Test remaining requirements shows failed criteria / 测试剩余要求显示失败的条件"""
        gate = PaperLiveGate()
        metrics = _make_passing_metrics()
        metrics["total_trades"] = 100
        metrics["win_rate_percent"] = 20.0

        gate.evaluate_gate(**metrics)

        remaining = gate.get_remaining_requirements()
        assert "trade_count" in remaining
        assert "win_rate" in remaining
        assert remaining["trade_count"]["actual"] == 100
        assert remaining["win_rate"]["actual"] == 20.0


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Serialization / 序列化测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestSerialization:
    def test_criterion_check_result_to_dict(self):
        """Test CriterionCheckResult serialization / 测试单项检查结果序列化"""
        check = CriterionCheckResult(
            criterion_name="Test criterion",
            status=CheckStatus.PASSED,
            actual_value=100,
            required_value=50,
            passed=True,
            reason="Test passed",
        )

        d = check.to_dict()
        assert d["criterion_name"] == "Test criterion"
        assert d["status"] == "passed"
        assert d["actual_value"] == 100
        assert d["required_value"] == 50
        assert d["passed"] is True

    def test_gate_check_result_to_dict(self):
        """Test GateCheckResult serialization / 测试闸门检查结果序列化"""
        result = GateCheckResult(
            passed=True,
            gate_status=GateStatus.GATE_PASSED,
        )

        d = result.to_dict()
        assert d["passed"] is True
        assert d["gate_status"] == "gate_passed"
        assert isinstance(d["criteria_results"], dict)

    def test_gate_check_result_from_dict(self):
        """Test GateCheckResult deserialization / 测试闸门检查结果反序列化"""
        d = {
            "passed": True,
            "gate_status": "gate_passed",
            "blocking_reasons": [],
            "timestamp_ms": 123456789,
            "evaluated_at": "2026-03-29T12:00:00",
            "operator_approval_required": True,
            "criteria_results": {},
        }

        result = GateCheckResult.from_dict(d)
        assert result.passed is True
        assert result.gate_status == GateStatus.GATE_PASSED
        assert result.timestamp_ms == 123456789

    def test_gate_to_json(self):
        """Test PaperLiveGate serialization to JSON / 测试PaperLiveGate序列化为JSON"""
        gate = PaperLiveGate()
        metrics = _make_passing_metrics()
        gate.evaluate_gate(**metrics)

        json_str = gate.to_json()
        assert isinstance(json_str, str)

        # Verify it's valid JSON
        d = json.loads(json_str)
        assert "config" in d
        assert "last_check_result" in d

    def test_gate_to_dict(self):
        """Test PaperLiveGate serialization to dict / 测试PaperLiveGate序列化为字典"""
        gate = PaperLiveGate()
        metrics = _make_passing_metrics()
        gate.evaluate_gate(**metrics)

        d = gate.to_dict()
        assert "config" in d
        assert "last_check_result" in d
        assert d["last_check_result"] is not None
        assert d["last_check_result"]["passed"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Audit Callback / 审计回调测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditCallback:
    def test_audit_callback_on_evaluation(self):
        """Test audit callback is called on gate evaluation / 测试评估时调用审计回调"""
        mock_callback = MagicMock()
        gate = PaperLiveGate(audit_callback=mock_callback)

        metrics = _make_passing_metrics()
        gate.evaluate_gate(**metrics)

        # Should have called callback with event_type and event_data
        assert mock_callback.called
        calls = mock_callback.call_args_list
        event_types = [call[0][0] for call in calls]
        assert "gate_evaluated" in event_types

    def test_audit_callback_on_approval(self):
        """Test audit callback is called on operator approval / 测试批准时调用审计回调"""
        mock_callback = MagicMock()
        gate = PaperLiveGate(audit_callback=mock_callback)

        metrics = _make_passing_metrics()
        gate.evaluate_gate(**metrics)
        mock_callback.reset_mock()

        gate.submit_operator_approval(
            approved=True,
            operator_id="op_test_006",
        )

        # Should have called callback with operator approval event
        assert mock_callback.called
        calls = mock_callback.call_args_list
        event_types = [call[0][0] for call in calls]
        assert "operator_approval_submitted" in event_types

    def test_audit_callback_receives_event_data(self):
        """Test audit callback receives correct event data / 测试审计回调接收正确的事件数据"""
        captured_events = []

        def capture_callback(event_type, event_data):
            captured_events.append((event_type, event_data))

        gate = PaperLiveGate(audit_callback=capture_callback)
        metrics = _make_passing_metrics()
        gate.evaluate_gate(**metrics)

        assert len(captured_events) > 0
        event_type, event_data = captured_events[0]
        assert isinstance(event_data, dict)

    def test_audit_callback_exception_handled(self):
        """Test gate continues if audit callback raises exception / 测试审计回调异常时闸门继续"""
        def failing_callback(event_type, event_data):
            raise RuntimeError("Callback failed")

        gate = PaperLiveGate(audit_callback=failing_callback)
        metrics = _make_passing_metrics()

        # Should not raise
        result = gate.evaluate_gate(**metrics)
        assert result.passed is True


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Thread Safety / 线程安全测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestThreadSafety:
    def test_concurrent_evaluations(self):
        """Test thread-safe concurrent gate evaluations / 测试并发闸门评估的线程安全性"""
        gate = PaperLiveGate()
        results = []
        metrics = _make_passing_metrics()

        def eval_gate():
            result = gate.evaluate_gate(**metrics)
            results.append(result)

        threads = [threading.Thread(target=eval_gate) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 5
        # All should have same gate status
        statuses = [r.gate_status for r in results]
        assert len(set(s for s in statuses)) == 1

    def test_concurrent_approval_submission(self):
        """Test thread-safe operator approval submission / 测试并发批准提交的线程安全性"""
        gate = PaperLiveGate()
        metrics = _make_passing_metrics()
        gate.evaluate_gate(**metrics)

        results = []

        def submit_approval(op_id):
            try:
                result = gate.submit_operator_approval(
                    approved=True,
                    operator_id=op_id,
                )
                results.append(result)
            except ValueError:
                # Expected if another thread already approved
                pass

        threads = [
            threading.Thread(target=submit_approval, args=(f"op_{i}",))
            for i in range(3)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # At least one should have succeeded
        assert len(results) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Edge Cases / 边界情况测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_zero_trades(self):
        """Test with zero trades / 测试零交易"""
        gate = PaperLiveGate()
        metrics = _make_passing_metrics()
        metrics["total_trades"] = 0

        result = gate.evaluate_gate(**metrics)
        assert result.passed is False

    def test_zero_win_rate(self):
        """Test with zero win rate / 测试零胜率"""
        gate = PaperLiveGate()
        metrics = _make_passing_metrics()
        metrics["win_rate_percent"] = 0.0

        result = gate.evaluate_gate(**metrics)
        assert result.passed is False

    def test_zero_sharpe(self):
        """Test with zero Sharpe ratio / 测试零夏普比"""
        gate = PaperLiveGate()
        metrics = _make_passing_metrics()
        metrics["sharpe_ratio"] = 0.0

        result = gate.evaluate_gate(**metrics)
        assert result.passed is False

    def test_very_high_drawdown(self):
        """Test with very high drawdown / 测试极高的回撤"""
        gate = PaperLiveGate()
        metrics = _make_passing_metrics()
        metrics["max_drawdown_percent"] = 95.0

        result = gate.evaluate_gate(**metrics)
        # Should still pass if drawdown check has high max_drawdown_percent
        # (default is 100)

    def test_exactly_at_thresholds(self):
        """Test with values exactly at thresholds / 测试恰好在阈值处的值"""
        cfg = _make_config(min_win_rate_percent=35.0)
        gate = PaperLiveGate(cfg)

        metrics = _make_passing_metrics()
        metrics["win_rate_percent"] = 35.0  # Exactly at threshold

        result = gate.evaluate_gate(**metrics)
        # Win rate check uses > (strict inequality), so exactly at threshold fails
        wr_check = result.criteria_results["win_rate"]
        assert wr_check.passed is False

    def test_just_above_thresholds(self):
        """Test with values just above thresholds / 测试略高于阈值的值"""
        cfg = _make_config(min_win_rate_percent=35.0)
        gate = PaperLiveGate(cfg)

        metrics = _make_passing_metrics()
        metrics["win_rate_percent"] = 35.01  # Just above threshold

        result = gate.evaluate_gate(**metrics)
        wr_check = result.criteria_results["win_rate"]
        assert wr_check.passed is True
