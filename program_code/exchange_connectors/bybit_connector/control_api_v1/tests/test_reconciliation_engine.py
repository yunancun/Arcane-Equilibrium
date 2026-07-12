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
    map_report_to_escalation,
)


class TestMapReportToEscalation:
    """map_report_to_escalation 唯一映射（reconcile Path B §4）。

    為什麼要看 discrepancies[].severity：overall_result 把 FATAL 與 CRITICAL 都塌成
    MISMATCH_MAJOR,單看 overall 無法分辨「凍結」與「降風控」。
    """

    def test_match_returns_none(self):
        assert map_report_to_escalation({"overall_result": "MATCH", "discrepancies": []}) is None

    def test_empty_dict_defaults_to_none(self):
        assert map_report_to_escalation({}) is None

    def test_warning_only_is_minor(self):
        report = {"overall_result": "MISMATCH_MINOR", "discrepancies": [{"severity": "WARNING"}]}
        assert map_report_to_escalation(report) == "MISMATCH_MINOR"

    def test_critical_disc_is_major(self):
        report = {"overall_result": "MISMATCH_MAJOR", "discrepancies": [{"severity": "CRITICAL"}]}
        assert map_report_to_escalation(report) == "MISMATCH_MAJOR"

    def test_major_overall_without_disc_is_major(self):
        report = {"overall_result": "MISMATCH_MAJOR", "discrepancies": []}
        assert map_report_to_escalation(report) == "MISMATCH_MAJOR"

    def test_fatal_disc_beats_critical(self):
        # overall 仍為 MISMATCH_MAJOR,但存在 FATAL 差異 → 必須升為 FATAL。
        report = {
            "overall_result": "MISMATCH_MAJOR",
            "discrepancies": [{"severity": "CRITICAL"}, {"severity": "FATAL"}],
        }
        assert map_report_to_escalation(report) == "FATAL"

    def test_real_report_to_dict_roundtrip(self):
        # 用引擎真報告驗證：遠端多一個持倉 → FATAL POSITION_MISSING → token=FATAL。
        report = ReconciliationReport(overall_result=ReconciliationResult.MISMATCH_MAJOR)
        report.discrepancies.append(
            Discrepancy(disc_type=DiscrepancyType.POSITION_MISSING, severity=Severity.FATAL)
        )
        assert map_report_to_escalation(report.to_dict()) == "FATAL"

    # ── E4 追加：E2/CC flagged 的邊界案例（2b）——證明映射對髒輸入 fail-safe,不崩、不誤升 ──

    def test_disc_missing_severity_key_does_not_crash(self):
        # 差異 dict 缺 "severity" 鍵：str(d.get("severity","")).upper() → "" ,不 KeyError;
        # overall=MISMATCH_MAJOR 仍走 major 分支。證明缺鍵不會炸也不會誤升為 FATAL。
        report = {"overall_result": "MISMATCH_MAJOR", "discrepancies": [{}]}
        assert map_report_to_escalation(report) == "MISMATCH_MAJOR"

    def test_unknown_garbage_severity_string_treated_as_non_critical(self):
        # 未知/垃圾 severity 字串不得被當成 CRITICAL/FATAL（否則會誤升級)。
        report = {"overall_result": "MISMATCH_MINOR", "discrepancies": [{"severity": "BOGUS_SEV"}]}
        assert map_report_to_escalation(report) == "MISMATCH_MINOR"

    def test_unknown_overall_result_defaults_to_minor(self):
        # 未知 overall_result（非 MATCH、非 MISMATCH_MAJOR)且無 CRITICAL/FATAL → 最保守 MINOR。
        report = {"overall_result": "WHO_KNOWS", "discrepancies": []}
        assert map_report_to_escalation(report) == "MISMATCH_MINOR"

    def test_mixed_severities_critical_beats_warning(self):
        # 混合嚴重度取最嚴重：WARNING + CRITICAL → MISMATCH_MAJOR（CRITICAL 勝 WARNING)。
        report = {
            "overall_result": "MISMATCH_MAJOR",
            "discrepancies": [{"severity": "WARNING"}, {"severity": "CRITICAL"}],
        }
        assert map_report_to_escalation(report) == "MISMATCH_MAJOR"

    def test_error_overall_with_critical_disc_maps_major(self):
        # overall_result=="ERROR" 路徑（引擎內部異常會塞一條 CRITICAL UNKNOWN 差異)：
        # 設計上由 route fail-closed 短路不進本函數,但即便進來也不得崩,且映為非 None 升級。
        report = ReconciliationReport(overall_result=ReconciliationResult.ERROR)
        report.discrepancies.append(
            Discrepancy(disc_type=DiscrepancyType.UNKNOWN, severity=Severity.CRITICAL)
        )
        assert map_report_to_escalation(report.to_dict()) == "MISMATCH_MAJOR"

    def test_error_overall_empty_disc_maps_minor(self):
        # ERROR overall 但無差異 → 落到最保守 MINOR(仍非 None,誠實反映 non-MATCH)。
        report = {"overall_result": "ERROR", "discrepancies": []}
        assert map_report_to_escalation(report) == "MISMATCH_MINOR"


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


@pytest.fixture
def order_engine():
    """啟用訂單對賬的引擎(v2.B 後 reconcile_orders 預設 False,訂單對賬改為 opt-in)。

    本 fixture 顯式開啟以回歸驗證舊 _reconcile_orders 行為;無此旗標的預設引擎不再對賬訂單。
    """
    e = ReconciliationEngine(ReconciliationConfig(reconcile_orders=True))
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
    # v2.B：訂單對賬預設關閉,以下用 order_engine(reconcile_orders=True)回歸驗證舊行為。
    def test_order_state_mismatch(self, order_engine):
        """Different order states should be detected / 订单状态不一致应被检测"""
        paper = _make_state(orders=[_make_order("o1", state="paper_order_filled")])
        remote = _make_state(orders=[_make_order("o1", state="paper_order_working")])

        report = order_engine.reconcile(paper, remote)
        assert not report.is_consistent
        order_discs = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.ORDER_STATE]
        assert len(order_discs) == 1
        assert order_discs[0].severity == Severity.CRITICAL

    def test_order_missing_on_remote(self, order_engine):
        """Order exists locally but not remote / 本地有远端无"""
        paper = _make_state(orders=[_make_order("o1")])
        remote = _make_state(orders=[])

        report = order_engine.reconcile(paper, remote)
        missing = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.ORDER_MISSING]
        assert len(missing) == 1
        assert missing[0].severity == Severity.WARNING

    def test_order_missing_locally(self, order_engine):
        """Order exists on remote but not locally / 远端有本地无"""
        paper = _make_state(orders=[])
        remote = _make_state(orders=[_make_order("o1")])

        report = order_engine.reconcile(paper, remote)
        missing = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.ORDER_MISSING]
        assert len(missing) == 1
        assert missing[0].severity == Severity.CRITICAL

    def test_bybit_state_mapping(self, order_engine):
        """Bybit 'New' should map to paper 'working' / Bybit New 应映射为 working"""
        paper = _make_state(orders=[_make_order("o1", state="paper_order_working")])
        remote = _make_state(orders=[_make_order("o1", state="New")])

        report = order_engine.reconcile(paper, remote)
        order_discs = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.ORDER_STATE]
        assert len(order_discs) == 0  # Should be treated as equivalent

    def test_multiple_orders(self, order_engine):
        """Multiple matching orders should all pass / 多个匹配订单应全部通过"""
        orders = [_make_order(f"o{i}", state="paper_order_filled") for i in range(5)]
        paper = _make_state(orders=orders)
        remote = _make_state(orders=orders)

        report = order_engine.reconcile(paper, remote)
        assert report.orders_checked == 5
        order_discs = [d for d in report.discrepancies if d.disc_type in (DiscrepancyType.ORDER_STATE, DiscrepancyType.ORDER_MISSING)]
        assert len(order_discs) == 0

    # ── v2.B 新增：預設範圍排除(reconcile_orders=False)+ opt-in 回歸 ──────────────

    def test_orders_excluded_by_default_no_flag_and_checked_zero(self, engine):
        """預設引擎(reconcile_orders=False):遠端有訂單、本地無 → 0 ORDER_* 差異 + orders_checked==0。

        v2.B 核心:交易所是掛單唯一權威,訂單不入對賬範圍 → 不得因遠端掛單誤報。
        """
        paper = _make_state(orders=[])
        remote = _make_state(orders=[_make_order("remote_only_1"), _make_order("remote_only_2")])

        report = engine.reconcile(paper, remote)
        order_discs = [
            d for d in report.discrepancies
            if d.disc_type in (DiscrepancyType.ORDER_STATE, DiscrepancyType.ORDER_MISSING)
        ]
        assert len(order_discs) == 0
        assert report.orders_checked == 0
        # 無其他差異 → 整體仍 MATCH(訂單被完全排除)。
        assert report.overall_result == ReconciliationResult.MATCH
        # C1(CC):MATCH 產物必須自我揭露訂單是「排除」而非「對賬乾淨」。
        assert report.orders_scope == "excluded:exchange-authoritative"
        assert report.to_dict()["orders_scope"] == "excluded:exchange-authoritative"
        # QC 可見性:遠端 2 張掛單雖不對賬,仍記錄觀察數供 operator 可見。
        assert report.remote_orders_observed == 2
        assert report.to_dict()["remote_orders_observed"] == 2

    def test_reconcile_orders_true_restores_old_behavior(self, order_engine):
        """回歸守衛:reconcile_orders=True 時遠端多一單仍應報 CRITICAL ORDER_MISSING + orders_checked>0。"""
        paper = _make_state(orders=[])
        remote = _make_state(orders=[_make_order("o1")])

        report = order_engine.reconcile(paper, remote)
        missing = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.ORDER_MISSING]
        assert len(missing) == 1
        assert missing[0].severity == Severity.CRITICAL
        assert report.orders_checked == 1
        # opt-in 路徑:orders_scope 標記為 reconciled(與排除路徑對照)。
        assert report.orders_scope == "reconciled"


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

    # ── v2.C 新增：窗口對齊 + 空本地跳過筆數檢查 ──────────────────────────────

    def test_windowed_fills_exclude_out_of_window_remote(self, engine):
        """遠端早於本地時間窗的舊成交被排除 → 不誤報 FILL_COUNT。

        本地 1 筆(帶 timestamp_ms),遠端 = 1 筆同窗 + 1 筆遠早於窗口 → 窗口化後 1==1。
        """
        now = _now_ms()
        paper = _make_state(fills=[
            {"symbol": "ATOMUSDT", "side": "Buy", "qty": 0.1, "price": 10.0, "timestamp_ms": now},
        ])
        remote = _make_state(fills=[
            {"symbol": "ATOMUSDT", "side": "Buy", "execQty": 0.1, "execPrice": 10.0, "execTime": now + 100},
            {"symbol": "OLDUSDT", "side": "Buy", "execQty": 5.0, "execPrice": 1.0, "execTime": now - 10_000_000},
        ])

        report = engine.reconcile(paper, remote)
        count_discs = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.FILL_COUNT]
        assert len(count_discs) == 0
        # 窗口內 ATOMUSDT 兩端聚合量一致 → 無 FILL_QUANTITY。
        qty_discs = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.FILL_QUANTITY]
        assert len(qty_discs) == 0

    def test_empty_local_fills_skips_count_check(self, engine):
        """本地無成交 → 跳過筆數檢查:遠端 50 筆也不得報 FILL_COUNT。"""
        now = _now_ms()
        remote_fills = [
            {"symbol": "BTCUSDT", "side": "Buy", "execQty": 1.0, "execPrice": 50000.0, "execTime": now}
            for _ in range(50)
        ]
        paper = _make_state(fills=[])
        remote = _make_state(fills=remote_fills)

        report = engine.reconcile(paper, remote)
        fill_discs = [d for d in report.discrepancies if d.disc_type in (
            DiscrepancyType.FILL_COUNT, DiscrepancyType.FILL_QUANTITY, DiscrepancyType.FILL_PRICE
        )]
        assert len(fill_discs) == 0

    def test_populated_both_in_window_still_flags_real_qty_mismatch(self, engine):
        """守衛:兩端皆有且在窗口內時,真實聚合量不符仍必須報 FILL_QUANTITY(不得被窗口弱化)。"""
        now = _now_ms()
        paper = _make_state(fills=[
            {"symbol": "BTCUSDT", "side": "Buy", "qty": 1.0, "price": 50000.0, "timestamp_ms": now},
        ])
        remote = _make_state(fills=[
            {"symbol": "BTCUSDT", "side": "Buy", "execQty": 0.5, "execPrice": 50000.0, "execTime": now},
        ])

        report = engine.reconcile(paper, remote)
        qty_discs = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.FILL_QUANTITY]
        assert len(qty_discs) == 1
        assert qty_discs[0].severity == Severity.CRITICAL


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

    def test_minor_on_warning_only(self, order_engine):
        """Only WARNING discrepancies → MISMATCH_MINOR / 仅 WARNING 应为 MISMATCH_MINOR

        用 order_engine:本地有單、遠端無 = WARNING 級 ORDER_MISSING(v2.B 後訂單對賬需 opt-in)。
        """
        paper = _make_state(orders=[_make_order("o1")])
        remote = _make_state(orders=[])  # Missing on remote = WARNING

        report = order_engine.reconcile(paper, remote)
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


# ═══════════════════════════════════════════════════════════════════════════════
# 13. Boundary / Malicious Input Tests — FA-2 審計補充
#     邊界值輸入驗證測試（惡意 paper_state 是否正確升級風控）
# ═══════════════════════════════════════════════════════════════════════════════

class TestBoundaryInputValidation:
    """
    FA-2 audit: verify that malicious / corrupted paper_state inputs
    escalate to FATAL severity and trigger FREEZE_TRADING rather than
    being silently accepted or downgraded to WARNING.

    FA-2 審計：驗證惡意/損壞的 paper_state 輸入能正確升級為 FATAL 嚴重等級
    並觸發 FREEZE_TRADING，不會被靜默接受或降級為 WARNING。
    """

    # ── BUG-1 fix: NaN qty in position (both-sides-present path) ──────────

    def test_position_nan_qty_local_is_fatal(self, engine):
        """
        BUG-1: qty=NaN local, remote=1.0 → must be FATAL + FREEZE_TRADING.
        修復前：NaN > 0 = False → WARNING（不觸發 FREEZE），現在應為 FATAL。
        """
        paper = _make_state(positions={"BTCUSDT": {"side": "Buy", "size": float("nan"), "avg_entry_price": 50000}})
        remote = _make_state(positions={"BTCUSDT": _make_position(side="Buy", size=1.0)})

        report = engine.reconcile(paper, remote)
        pos_discs = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.POSITION_SIZE]
        assert len(pos_discs) == 1
        assert pos_discs[0].severity == Severity.FATAL, (
            "NaN local qty must escalate to FATAL, not WARNING"
        )
        assert IncidentAction.FREEZE_TRADING.value in report.actions_triggered

    def test_position_nan_qty_remote_is_fatal(self, engine):
        """
        BUG-1: local=1.0, remote qty=NaN → must be FATAL + FREEZE_TRADING.
        """
        paper = _make_state(positions={"BTCUSDT": _make_position(side="Buy", size=1.0)})
        remote = _make_state(positions={"BTCUSDT": {"side": "Buy", "size": float("nan")}})

        report = engine.reconcile(paper, remote)
        pos_discs = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.POSITION_SIZE]
        assert len(pos_discs) == 1
        assert pos_discs[0].severity == Severity.FATAL
        assert IncidentAction.FREEZE_TRADING.value in report.actions_triggered

    def test_position_inf_qty_is_fatal(self, engine):
        """
        qty=inf local → must be FATAL + FREEZE_TRADING (not just CRITICAL).
        """
        paper = _make_state(positions={"BTCUSDT": {"side": "Buy", "size": float("inf")}})
        remote = _make_state(positions={"BTCUSDT": _make_position(side="Buy", size=1.0)})

        report = engine.reconcile(paper, remote)
        pos_discs = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.POSITION_SIZE]
        assert len(pos_discs) == 1
        assert pos_discs[0].severity == Severity.FATAL
        assert IncidentAction.FREEZE_TRADING.value in report.actions_triggered

    # ── BUG-1 (continued): extreme negative qty in both-sides-present path ─

    def test_position_negative_qty_both_sides_is_fatal(self, engine):
        """
        BUG-1 extension: qty=-999999 with remote present → FATAL + FREEZE.
        Both paper and remote exist, so it goes through the size-comparison path.
        """
        paper = _make_state(positions={"BTCUSDT": {"side": "Buy", "size": -999999}})
        remote = _make_state(positions={"BTCUSDT": _make_position(side="Buy", size=1.0)})

        report = engine.reconcile(paper, remote)
        pos_discs = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.POSITION_SIZE]
        assert len(pos_discs) == 1
        assert pos_discs[0].severity == Severity.FATAL
        assert IncidentAction.FREEZE_TRADING.value in report.actions_triggered

    # ── BUG-3 fix: negative qty when position only exists locally ──────────

    def test_position_negative_qty_local_only_is_fatal(self, engine):
        """
        BUG-3: qty=-999999 local, remote has no position for that symbol.
        修復前：p_size > 0 = False → 不報告任何差異，現在應為 FATAL + FREEZE。
        """
        paper = _make_state(positions={"BTCUSDT": {"side": "Buy", "size": -999999}})
        remote = _make_state(positions={})

        report = engine.reconcile(paper, remote)
        missing_discs = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.POSITION_MISSING]
        assert len(missing_discs) == 1, (
            "Negative local qty must still report POSITION_MISSING (data corruption)"
        )
        assert missing_discs[0].severity == Severity.FATAL
        assert IncidentAction.FREEZE_TRADING.value in report.actions_triggered

    def test_position_nan_qty_local_only_is_fatal(self, engine):
        """
        NaN local qty with no remote counterpart → FATAL + FREEZE.
        """
        paper = _make_state(positions={"BTCUSDT": {"side": "Buy", "size": float("nan")}})
        remote = _make_state(positions={})

        report = engine.reconcile(paper, remote)
        missing_discs = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.POSITION_MISSING]
        assert len(missing_discs) == 1
        assert missing_discs[0].severity == Severity.FATAL
        assert IncidentAction.FREEZE_TRADING.value in report.actions_triggered

    # ── BUG-2 fix: NaN balance silently accepted ───────────────────────────

    def test_balance_nan_is_critical(self, engine):
        """
        BUG-2: balance=NaN → abs(NaN - real) = NaN → NaN > threshold = False
        → was silently accepted. Now must raise CRITICAL + ALERT.
        修復前：NaN 差值比較永遠為 False，餘額異常被靜默接受。
        """
        paper = _make_state(balances={"USDT": float("nan")})
        remote = _make_state(balances={"USDT": 10000.0})

        report = engine.reconcile(paper, remote)
        bal_discs = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.BALANCE_DRIFT]
        assert len(bal_discs) == 1, (
            "NaN balance must be detected, not silently pass tolerance check"
        )
        assert bal_discs[0].severity == Severity.CRITICAL
        # auto_freeze_on_critical is True by default → FREEZE expected
        assert IncidentAction.FREEZE_TRADING.value in report.actions_triggered

    def test_balance_inf_is_critical(self, engine):
        """
        balance=inf remote → must raise CRITICAL.
        """
        paper = _make_state(balances={"USDT": 10000.0})
        remote = _make_state(balances={"USDT": float("inf")})

        report = engine.reconcile(paper, remote)
        bal_discs = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.BALANCE_DRIFT]
        assert len(bal_discs) == 1
        assert bal_discs[0].severity == Severity.CRITICAL

    def test_balance_negative_inf_is_critical(self, engine):
        """
        balance=-inf → must raise CRITICAL (isinf covers both signs).
        """
        paper = _make_state(balances={"USDT": float("-inf")})
        remote = _make_state(balances={"USDT": 10000.0})

        report = engine.reconcile(paper, remote)
        bal_discs = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.BALANCE_DRIFT]
        assert len(bal_discs) == 1
        assert bal_discs[0].severity == Severity.CRITICAL

    # ── Regression: existing valid behaviour unchanged ─────────────────────

    def test_valid_negative_remote_remote_only_ignored(self, engine):
        """
        Remote position with size=0 still ignored (no change to zero-filter).
        零倉位邊界不應受修復影響。
        """
        paper = _make_state(positions={})
        remote = _make_state(positions={"BTCUSDT": _make_position(size=0)})

        report = engine.reconcile(paper, remote)
        missing = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.POSITION_MISSING]
        assert len(missing) == 0

    def test_normal_position_large_qty_still_critical_not_fatal(self, engine):
        """
        Legitimate large qty mismatch (positive, finite) → CRITICAL, not FATAL.
        合法的大額倉位差異不應被誤升級為 FATAL。
        """
        paper = _make_state(positions={"BTCUSDT": _make_position(size=999999.0)})
        remote = _make_state(positions={"BTCUSDT": _make_position(size=1.0)})

        report = engine.reconcile(paper, remote)
        pos_discs = [d for d in report.discrepancies if d.disc_type == DiscrepancyType.POSITION_SIZE]
        assert len(pos_discs) == 1
        assert pos_discs[0].severity == Severity.CRITICAL, (
            "Large but valid positive qty mismatch should remain CRITICAL, not FATAL"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 14. v2 端到端 MATCH-reachability（waves B+C）
# ═══════════════════════════════════════════════════════════════════════════════

class TestV2MatchReachability:
    """驗證 waves B(訂單範圍排除)+ C(成交窗口對齊)後可達乾淨 MATCH。

    模擬 wave-A(Rust 引擎凍結殘塵)已生效:0.1 殘塵同時存在於本地與遠端(both-exist within
    tolerance)。訂單以預設 reconcile_orders=False 排除,成交以本地時間窗過濾遠端。
    注意:真實 runtime 的端到端 MATCH 仍依賴 wave-A(引擎凍結殘塵)+ operator 於 runtime
    清理既有殘塵;本測試以 fixture 假設該前置已滿足,只證 Python 對賬層在該狀態下判 MATCH。
    """

    def test_end_to_end_match_orders_excluded_fills_windowed(self, engine):
        now = _now_ms()
        # wave-A 凍結後:本地與遠端皆持有 0.1 殘塵(方向、量一致)。
        positions = {"ATOMUSDT": {"side": "Buy", "size": 0.1, "avg_entry_price": 10.0}}
        paper = _make_state(
            positions=positions,
            balances={"USDT": 1000.0},
            orders=[],  # 本地無掛單
            fills=[{"symbol": "ATOMUSDT", "side": "Buy", "qty": 0.1, "price": 10.0, "timestamp_ms": now}],
            ts_ms=now,
        )
        remote = _make_state(
            positions=positions,
            balances={"USDT": 1000.0},
            # 遠端有掛單 + 窗口外舊成交 —— 皆不得造成差異(訂單排除、成交窗口化)。
            orders=[_make_order("remote_conditional_stop", state="Untriggered")],
            fills=[
                {"symbol": "ATOMUSDT", "side": "Buy", "execQty": 0.1, "execPrice": 10.0, "execTime": now + 50},
                {"symbol": "OLDUSDT", "side": "Buy", "execQty": 9.0, "execPrice": 2.0, "execTime": now - 5_000_000},
            ],
            ts_ms=now,
        )

        report = engine.reconcile(paper, remote)
        assert report.overall_result == ReconciliationResult.MATCH
        assert report.is_consistent
        assert report.critical_count == 0
        assert report.orders_checked == 0
        assert len(report.discrepancies) == 0
        # C1(CC):此 MATCH 必須揭露訂單是排除於範圍外,不得被讀成「訂單已對賬乾淨」;
        # 遠端那張條件單雖不對賬,仍以 remote_orders_observed 保持可見(QC)。
        assert report.orders_scope == "excluded:exchange-authoritative"
        assert report.remote_orders_observed == 1
