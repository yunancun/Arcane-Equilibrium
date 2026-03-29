"""
Tests for Reconciliation Engine — EX-02 §14 / EX-04 / GAP-C1
对账引擎测试

Covers:
  - Order reconciliation (match, mismatch, missing)
  - Position reconciliation (size, side, missing)
  - Fill reconciliation (count, quantity, price)
  - Balance reconciliation (drift detection)
  - Data freshness checks
  - Overall result determination
  - Incident triggering
  - Audit callback integration
  - Thread safety
  - ScheduledReconciler lifecycle
  - Edge cases (empty states, zero positions)
"""

import sys
import threading
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.reconciliation_engine import (
    Discrepancy,
    DiscrepancyType,
    IncidentAction,
    ReconciliationConfig,
    ReconciliationEngine,
    ReconciliationReport,
    ReconciliationResult,
    ScheduledReconciler,
    Severity,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures / 测试夹具
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def config():
    return ReconciliationConfig(
        price_tolerance_pct=0.005,
        qty_tolerance_pct=0.001,
        balance_tolerance_abs=1.0,
        max_data_age_ms=60_000,
    )


@pytest.fixture
def engine(config):
    e = ReconciliationEngine(config)
    yield e
    e.close()


def _now_ms():
    return int(time.time() * 1000)


def _make_state(
    orders=None,
    positions=None,
    fills=None,
    balances=None,
    ts_ms=None,
) -> dict:
    """Helper to build a state snapshot / 构建状态快照"""
    return {
        "orders": orders or [],
        "positions": positions or {},
        "fills": fills or [],
        "balances": balances or {},
        "snapshot_ts_ms": ts_ms or _now_ms(),
    }


def _make_order(order_id, symbol="BTCUSDT", state="paper_order_filled", side="Buy", qty=1.0):
    return {
        "order_id": order_id,
        "symbol": symbol,
        "state": state,
        "side": side,
        "qty": qty,
    }


def _make_position(side="Buy", size=1.0, avg_price=50000.0):
    return {"side": side, "size": size, "avg_entry_price": avg_price}


def _make_fill(order_id, qty=1.0, price=50000.0):
    return {"order_id": order_id, "fill_qty": qty, "fill_price": price}


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Consistent State / 一致状态测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestConsistentState:
    def test_perfect_match(self, engine):
        """Identical states should produce MATCH / 完全一致应返回 MATCH"""
        orders = [_make_order("o1"), _make_order("o2")]
        positions = {"BTCUSDT": _make_position()}
        fills = [_make_fill("o1"), _make_fill("o2")]
        balances = {"USDT": 10000.0}

        paper = _make_state(orders=orders, positions=positions, fills=fills, balances=balances)
        remote = _make_state(orders=orders, positions=positions, fills=fills, balances=balances)

        report = engine.reconcile(paper, remote)
        assert report.overall_result == ReconciliationResult.MATCH
        assert report.is_consistent
        assert report.critical_count == 0

    def test_empty_states_match(self, engine):
        """Empty states should match / 空状态应一致"""
        report = engine.reconcile(_make_state(), _make_state())
        assert report.overall_result == ReconciliationResult.MATCH

    def test_report_has_id(self, engine):
        report = engine.reconcile(_make_state(), _make_state())
        assert report.report_id.startswith("recon:")

    def test_report_timestamps(self, engine):
        report = engine.reconcile(_make_state(), _make_state())
        assert report.started_at_ms > 0
        assert report.completed_at_ms >= report.started_at_ms


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Order Reconciliation / 订单对账测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestOrderReconciliation:
    def test_order_state_mismatch(self, engine):
        """Different order states should be detected / 订单状态不一致应被检测"""
        paper = _make_state(orders=[_make_order("o1", state="paper_order_filled")])
        remote = _make_state(orders=[_make_order("o1", state="paper_order_working")])

        report = engine.reconcile(paper, remote)
        assert not report.is_consistent
        order_discs = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.ORDER_STATE]
        assert len(order_discs) == 1
        assert order_discs[0].severity == Severity.CRITICAL

    def test_order_missing_on_remote(self, engine):
        """Order exists locally but not remote / 本地有远端无"""
        paper = _make_state(orders=[_make_order("o1")])
        remote = _make_state(orders=[])

        report = engine.reconcile(paper, remote)
        missing = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.ORDER_MISSING]
        assert len(missing) == 1
        assert missing[0].severity == Severity.WARNING

    def test_order_missing_locally(self, engine):
        """Order exists on remote but not locally / 远端有本地无"""
        paper = _make_state(orders=[])
        remote = _make_state(orders=[_make_order("o1")])

        report = engine.reconcile(paper, remote)
        missing = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.ORDER_MISSING]
        assert len(missing) == 1
        assert missing[0].severity == Severity.CRITICAL

    def test_bybit_state_mapping(self, engine):
        """Bybit 'New' should map to paper 'working' / Bybit New 应映射为 working"""
        paper = _make_state(orders=[_make_order("o1", state="paper_order_working")])
        remote = _make_state(orders=[_make_order("o1", state="New")])

        report = engine.reconcile(paper, remote)
        order_discs = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.ORDER_STATE]
        assert len(order_discs) == 0  # Should be treated as equivalent

    def test_multiple_orders(self, engine):
        """Multiple matching orders should all pass / 多个匹配订单应全部通过"""
        orders = [_make_order(f"o{i}", state="paper_order_filled") for i in range(5)]
        paper = _make_state(orders=orders)
        remote = _make_state(orders=orders)

        report = engine.reconcile(paper, remote)
        assert report.orders_checked == 5
        order_discs = [d for d in report.discrepancies if d.disc_type in (DiscrepancyType.ORDER_STATE, DiscrepancyType.ORDER_MISSING)]
        assert len(order_discs) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Position Reconciliation / 持仓对账测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestPositionReconciliation:
    def test_position_size_mismatch(self, engine):
        """Different position sizes should be flagged / 持仓数量不一致应被标记"""
        paper = _make_state(positions={"BTCUSDT": _make_position(size=1.0)})
        remote = _make_state(positions={"BTCUSDT": _make_position(size=0.5)})

        report = engine.reconcile(paper, remote)
        size_discs = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.POSITION_SIZE]
        assert len(size_discs) == 1
        assert size_discs[0].magnitude == 0.5

    def test_position_side_mismatch(self, engine):
        """Different position sides should be FATAL / 持仓方向不一致应为 FATAL"""
        paper = _make_state(positions={"BTCUSDT": _make_position(side="Buy", size=1.0)})
        remote = _make_state(positions={"BTCUSDT": _make_position(side="Sell", size=1.0)})

        report = engine.reconcile(paper, remote)
        side_discs = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.POSITION_SIDE]
        assert len(side_discs) == 1
        assert side_discs[0].severity == Severity.FATAL

    def test_position_missing_remotely(self, engine):
        """Position missing on remote should be CRITICAL / 远端缺失持仓应为 CRITICAL"""
        paper = _make_state(positions={"BTCUSDT": _make_position(size=1.0)})
        remote = _make_state(positions={})

        report = engine.reconcile(paper, remote)
        missing = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.POSITION_MISSING]
        assert len(missing) == 1
        assert missing[0].severity == Severity.CRITICAL

    def test_position_missing_locally(self, engine):
        """Position missing locally should be FATAL / 本地缺失持仓应为 FATAL"""
        paper = _make_state(positions={})
        remote = _make_state(positions={"BTCUSDT": _make_position(size=1.0)})

        report = engine.reconcile(paper, remote)
        missing = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.POSITION_MISSING]
        assert len(missing) == 1
        assert missing[0].severity == Severity.FATAL

    def test_zero_positions_ignored(self, engine):
        """Zero-size positions should not flag missing / 零仓位不应标记为缺失"""
        paper = _make_state(positions={"BTCUSDT": _make_position(size=0)})
        remote = _make_state(positions={})

        report = engine.reconcile(paper, remote)
        missing = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.POSITION_MISSING]
        assert len(missing) == 0

    def test_position_match(self, engine):
        """Matching positions should produce no discrepancies / 匹配持仓不应有差异"""
        pos = _make_position(size=1.0, side="Buy")
        paper = _make_state(positions={"BTCUSDT": pos})
        remote = _make_state(positions={"BTCUSDT": pos})

        report = engine.reconcile(paper, remote)
        pos_discs = [d for d in report.discrepancies if d.disc_type in (
            DiscrepancyType.POSITION_SIZE, DiscrepancyType.POSITION_SIDE, DiscrepancyType.POSITION_MISSING
        )]
        assert len(pos_discs) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Fill Reconciliation / 成交对账测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestFillReconciliation:
    def test_fill_count_mismatch(self, engine):
        """Different fill counts should be flagged / 成交笔数不同应被标记"""
        paper = _make_state(fills=[_make_fill("o1"), _make_fill("o1")])
        remote = _make_state(fills=[_make_fill("o1")])

        report = engine.reconcile(paper, remote)
        count_discs = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.FILL_COUNT]
        assert len(count_discs) == 1

    def test_fill_quantity_mismatch(self, engine):
        """Different fill quantities per order should be flagged / 订单成交量不同应被标记"""
        paper = _make_state(fills=[_make_fill("o1", qty=1.0)])
        remote = _make_state(fills=[_make_fill("o1", qty=0.5)])

        report = engine.reconcile(paper, remote)
        qty_discs = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.FILL_QUANTITY]
        assert len(qty_discs) == 1
        assert qty_discs[0].severity == Severity.CRITICAL

    def test_fill_price_deviation(self, engine):
        """Price deviations beyond tolerance should be flagged / 价格偏差超容差应被标记"""
        paper = _make_state(fills=[_make_fill("o1", qty=1.0, price=50000.0)])
        remote = _make_state(fills=[_make_fill("o1", qty=1.0, price=50500.0)])  # 1% deviation

        report = engine.reconcile(paper, remote)
        price_discs = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.FILL_PRICE]
        assert len(price_discs) == 1

    def test_fill_match(self, engine):
        """Matching fills should produce no discrepancies / 匹配成交不应有差异"""
        fills = [_make_fill("o1", qty=1.0, price=50000.0)]
        paper = _make_state(fills=fills)
        remote = _make_state(fills=fills)

        report = engine.reconcile(paper, remote)
        fill_discs = [d for d in report.discrepancies if d.disc_type in (
            DiscrepancyType.FILL_COUNT, DiscrepancyType.FILL_QUANTITY, DiscrepancyType.FILL_PRICE
        )]
        assert len(fill_discs) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Balance Reconciliation / 余额对账测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestBalanceReconciliation:
    def test_balance_drift_detected(self, engine):
        """Balance drift beyond tolerance should be flagged / 余额偏差超容差应被标记"""
        paper = _make_state(balances={"USDT": 10000.0})
        remote = _make_state(balances={"USDT": 9990.0})  # $10 drift

        report = engine.reconcile(paper, remote)
        bal_discs = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.BALANCE_DRIFT]
        assert len(bal_discs) == 1

    def test_balance_within_tolerance(self, engine):
        """Small balance drift should be ignored / 小额偏差应被忽略"""
        paper = _make_state(balances={"USDT": 10000.0})
        remote = _make_state(balances={"USDT": 10000.5})  # $0.5 drift

        report = engine.reconcile(paper, remote)
        bal_discs = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.BALANCE_DRIFT]
        assert len(bal_discs) == 0

    def test_large_balance_drift_critical(self, engine):
        """Large balance drift should be CRITICAL / 大额偏差应为 CRITICAL"""
        paper = _make_state(balances={"USDT": 10000.0})
        remote = _make_state(balances={"USDT": 9900.0})  # $100 drift

        report = engine.reconcile(paper, remote)
        bal_discs = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.BALANCE_DRIFT]
        assert len(bal_discs) == 1
        assert bal_discs[0].severity == Severity.CRITICAL


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Overall Result / 整体结果判定测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestOverallResult:
    def test_match_when_no_discrepancies(self, engine):
        report = engine.reconcile(_make_state(), _make_state())
        assert report.overall_result == ReconciliationResult.MATCH

    def test_minor_on_warning_only(self, engine):
        """Only WARNING discrepancies → MISMATCH_MINOR / 仅 WARNING 应为 MISMATCH_MINOR"""
        paper = _make_state(orders=[_make_order("o1")])
        remote = _make_state(orders=[])  # Missing on remote = WARNING

        report = engine.reconcile(paper, remote)
        assert report.overall_result == ReconciliationResult.MISMATCH_MINOR

    def test_major_on_critical(self, engine):
        """CRITICAL discrepancy → MISMATCH_MAJOR / CRITICAL 应为 MISMATCH_MAJOR"""
        paper = _make_state(positions={"BTCUSDT": _make_position(size=1.0)})
        remote = _make_state(positions={"BTCUSDT": _make_position(size=0.5)})

        report = engine.reconcile(paper, remote)
        assert report.overall_result == ReconciliationResult.MISMATCH_MAJOR

    def test_major_on_fatal(self, engine):
        """FATAL discrepancy → MISMATCH_MAJOR / FATAL 应为 MISMATCH_MAJOR"""
        paper = _make_state(positions={"BTCUSDT": _make_position(side="Buy", size=1.0)})
        remote = _make_state(positions={"BTCUSDT": _make_position(side="Sell", size=1.0)})

        report = engine.reconcile(paper, remote)
        assert report.overall_result == ReconciliationResult.MISMATCH_MAJOR
        assert not report.is_consistent


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Incident Triggering / 事件触发测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestIncidentTriggering:
    def test_freeze_on_fatal(self):
        """FATAL discrepancy should trigger FREEZE / FATAL 应触发 FREEZE"""
        incidents = []
        engine = ReconciliationEngine(
            incident_callback=lambda action, report: incidents.append(action),
        )

        paper = _make_state(positions={})
        remote = _make_state(positions={"BTCUSDT": _make_position(size=1.0)})

        report = engine.reconcile(paper, remote)
        assert IncidentAction.FREEZE_TRADING.value in report.actions_triggered
        assert len(incidents) > 0
        engine.close()

    def test_freeze_on_critical_with_auto_freeze(self):
        """CRITICAL + auto_freeze_on_critical → FREEZE / CRITICAL + 自动冻结"""
        config = ReconciliationConfig(auto_freeze_on_critical=True)
        engine = ReconciliationEngine(config)

        paper = _make_state(positions={"BTCUSDT": _make_position(size=1.0)})
        remote = _make_state(positions={"BTCUSDT": _make_position(size=0.5)})

        report = engine.reconcile(paper, remote)
        assert IncidentAction.FREEZE_TRADING.value in report.actions_triggered
        engine.close()

    def test_no_freeze_on_minor(self, engine):
        """Minor discrepancy should not trigger FREEZE / 小偏差不应冻结"""
        paper = _make_state(orders=[_make_order("o1")])
        remote = _make_state(orders=[])  # WARNING only

        report = engine.reconcile(paper, remote)
        assert IncidentAction.FREEZE_TRADING.value not in report.actions_triggered

    def test_incident_callback_receives_report(self):
        """Incident callback should receive report dict / 事件回调应收到报告"""
        received = []
        engine = ReconciliationEngine(
            incident_callback=lambda action, report: received.append((action, report)),
        )

        paper = _make_state(positions={})
        remote = _make_state(positions={"BTCUSDT": _make_position(size=1.0)})

        engine.reconcile(paper, remote)
        assert len(received) > 0
        assert "report_id" in received[0][1]
        engine.close()


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Audit Callback / 审计回调测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditCallback:
    def test_audit_emitted(self):
        """Audit callback should be invoked on each reconcile / 每次对账应发送审计"""
        audits = []
        engine = ReconciliationEngine(audit_callback=lambda r: audits.append(r))

        engine.reconcile(_make_state(), _make_state())
        assert len(audits) == 1
        assert audits[0]["event_type"] == "reconciliation_completed"
        engine.close()

    def test_audit_contains_fields(self):
        """Audit record should contain required fields / 审计记录应包含必要字段"""
        audits = []
        engine = ReconciliationEngine(audit_callback=lambda r: audits.append(r))

        engine.reconcile(_make_state(), _make_state())
        record = audits[0]
        assert "report_id" in record
        assert "overall_result" in record
        assert "discrepancy_count" in record
        assert "orders_checked" in record
        engine.close()


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Status & History / 状态与历史测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestStatusAndHistory:
    def test_status(self, engine):
        engine.reconcile(_make_state(), _make_state())
        status = engine.get_status()
        assert status["total_runs"] == 1
        assert status["total_discrepancies"] == 0

    def test_recent_reports(self, engine):
        for _ in range(3):
            engine.reconcile(_make_state(), _make_state())
        reports = engine.get_recent_reports(2)
        assert len(reports) == 2

    def test_history_limit(self):
        """History should be capped / 历史应有上限"""
        engine = ReconciliationEngine()
        engine._max_history = 5
        for _ in range(10):
            engine.reconcile(_make_state(), _make_state())
        assert len(engine._history) == 5
        engine.close()


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Thread Safety / 线程安全测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestThreadSafety:
    def test_concurrent_reconciliation(self, engine):
        """Concurrent reconciles should not corrupt state / 并发对账不应损坏状态"""
        errors = []
        runs_per_thread = 10

        def worker():
            try:
                for _ in range(runs_per_thread):
                    paper = _make_state(
                        orders=[_make_order("o1")],
                        positions={"BTCUSDT": _make_position()},
                    )
                    remote = _make_state(
                        orders=[_make_order("o1")],
                        positions={"BTCUSDT": _make_position()},
                    )
                    report = engine.reconcile(paper, remote)
                    assert report.report_id.startswith("recon:")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0
        assert engine.get_status()["total_runs"] == 50


# ═══════════════════════════════════════════════════════════════════════════════
# 11. ScheduledReconciler / 定时对账器测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestScheduledReconciler:
    def test_start_stop(self, engine):
        """Reconciler should start and stop cleanly / 定时器应干净启停"""
        reconciler = ScheduledReconciler(
            engine,
            paper_state_fn=_make_state,
            remote_state_fn=_make_state,
            interval_sec=0.2,
        )
        reconciler.start()
        assert reconciler.is_running
        time.sleep(0.3)
        reconciler.stop()
        assert not reconciler.is_running
        assert engine.get_status()["total_runs"] >= 1

    def test_detects_discrepancy_in_loop(self):
        """Scheduled reconciler should detect discrepancies / 定时器应检测到差异"""
        engine = ReconciliationEngine()

        def paper_fn():
            return _make_state(positions={"BTCUSDT": _make_position(size=1.0)})

        def remote_fn():
            return _make_state(positions={"BTCUSDT": _make_position(size=0.5)})

        reconciler = ScheduledReconciler(engine, paper_fn, remote_fn, interval_sec=0.2)
        reconciler.start()
        time.sleep(0.3)
        reconciler.stop()

        assert engine.get_status()["total_discrepancies"] > 0
        engine.close()


# ═══════════════════════════════════════════════════════════════════════════════
# 12. Edge Cases / 边界情况测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_closed_engine_raises(self, engine):
        engine.close()
        with pytest.raises(RuntimeError, match="closed"):
            engine.reconcile(_make_state(), _make_state())

    def test_discrepancy_to_dict(self):
        d = Discrepancy(
            disc_type=DiscrepancyType.ORDER_STATE,
            severity=Severity.CRITICAL,
            symbol="BTCUSDT",
            description="test",
        )
        as_dict = d.to_dict()
        assert as_dict["type"] == "ORDER_STATE"
        assert as_dict["severity"] == "CRITICAL"

    def test_report_to_dict(self, engine):
        report = engine.reconcile(_make_state(), _make_state())
        as_dict = report.to_dict()
        assert "report_id" in as_dict
        assert "overall_result" in as_dict
        assert "is_consistent" in as_dict

    def test_tolerance_edge(self, engine):
        """Values exactly at tolerance boundary / 恰好在容差边界"""
        # qty_tolerance_pct = 0.001 (0.1%), size difference = 0.001 = 0.1%
        paper = _make_state(positions={"BTCUSDT": _make_position(size=1.0)})
        remote = _make_state(positions={"BTCUSDT": _make_position(size=1.001)})

        report = engine.reconcile(paper, remote)
        size_discs = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.POSITION_SIZE]
        assert len(size_discs) == 0  # Within tolerance

    def test_stale_data_warning(self):
        """Stale snapshot should produce warning / 过时快照应产生警告"""
        config = ReconciliationConfig(max_data_age_ms=1000)
        engine = ReconciliationEngine(config)

        old_ts = _now_ms() - 5000
        paper = _make_state(ts_ms=old_ts)
        remote = _make_state()

        report = engine.reconcile(paper, remote)
        stale = [d for d in report.discrepancies if "stale" in d.description.lower()]
        assert len(stale) >= 1
        engine.close()

    def test_multiple_symbols(self, engine):
        """Multiple symbols should all be checked / 多币种应全部检查"""
        paper = _make_state(positions={
            "BTCUSDT": _make_position(size=1.0),
            "ETHUSDT": _make_position(size=10.0),
        })
        remote = _make_state(positions={
            "BTCUSDT": _make_position(size=1.0),
            "ETHUSDT": _make_position(size=10.0),
        })

        report = engine.reconcile(paper, remote)
        assert report.positions_checked == 2
        pos_discs = [d for d in report.discrepancies if d.disc_type in (
            DiscrepancyType.POSITION_SIZE, DiscrepancyType.POSITION_SIDE, DiscrepancyType.POSITION_MISSING
        )]
        assert len(pos_discs) == 0
