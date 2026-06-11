"""checks_alpha_wealth_fdr `[83]`-`[87]` 單元測試（P4 E1-C）。

隔離鐵則：fake cursor 注入、0 真 DSN、0 連線。
核心斷言：V138 表不存在 → 一律 PASS-skip 不 FAIL（部署順序容忍）；
五軸閾值語義（MIT 4a/N-3/4b + QC QN-1）。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 以 package 形式 import（runner 同款相對 import 需要 package 上下文）。
_HC_PARENT = Path(__file__).resolve().parents[1]  # helper_scripts/db
if str(_HC_PARENT) not in sys.path:
    sys.path.insert(0, str(_HC_PARENT))

from passive_wait_healthcheck import checks_alpha_wealth_fdr as hc  # noqa: E402


class _FakeConn:
    def __init__(self):
        self.rollbacks = 0

    def rollback(self):
        self.rollbacks += 1


class _FakeCursor:
    """routes = [(sql 子串, rows)]，首配優先；無配 → []。"""

    def __init__(self, routes):
        self.routes = routes
        self.connection = _FakeConn()
        self.executed: list[str] = []
        self._pending: list[tuple] = []

    def execute(self, sql, params=None):
        text = " ".join(sql.split())
        self.executed.append(text)
        for key, rows in self.routes:
            if key in text:
                self._pending = list(rows)
                return
        self._pending = []

    def fetchone(self):
        return self._pending[0] if self._pending else None

    def fetchall(self):
        return list(self._pending)


def _cur_fdr(present: bool, count_rows):
    """V138 兩表 regclass + 後續 count 查詢的腳本化 cursor。"""
    return _FakeCursor([
        ("to_regclass('research.alpha_wealth_ledger')", [(present,)]),
        ("to_regclass('learning.hidden_oos_state_registry')", [(present,)]),
        ("SELECT count(*)", [(count_rows,)]),
    ])


def test_all_five_skip_when_tables_absent():
    """V138/V132 未部署 → PASS-skip 不 FAIL（dispatch 鐵則）。"""
    for fn in (
        hc.check_83_alpha_wealth_family_cardinality,
        hc.check_84_alpha_wealth_orphan_refund,
        hc.check_85_alpha_wealth_refund_amount_mismatch,
        hc.check_86_pre_reg_cross_family_duplicate_spec,
        hc.check_87_hidden_oos_state_regression,
    ):
        cur = _cur_fdr(False, 999)  # count 即使有值也不該被讀到
        status, msg = fn(cur)
        assert status == "PASS", f"{fn.__name__} must SKIP-PASS when absent"
        assert "SKIP" in msg
        assert cur.connection.rollbacks >= 1  # 前置 rollback 慣例


def test_83_family_cardinality_thresholds():
    s, m = hc.check_83_alpha_wealth_family_cardinality(_cur_fdr(True, 3))
    assert s == "PASS"
    s, m = hc.check_83_alpha_wealth_family_cardinality(_cur_fdr(True, 10))
    assert s == "WARN" and "boundary" in m
    s, m = hc.check_83_alpha_wealth_family_cardinality(_cur_fdr(True, 11))
    assert s == "FAIL" and "mFDR" in m


def test_84_orphan_refund():
    s, _ = hc.check_84_alpha_wealth_orphan_refund(_cur_fdr(True, 0))
    assert s == "PASS"
    s, m = hc.check_84_alpha_wealth_orphan_refund(_cur_fdr(True, 2))
    assert s == "FAIL" and "orphan_refunds=2" in m


def test_85_refund_amount_mismatch():
    s, _ = hc.check_85_alpha_wealth_refund_amount_mismatch(_cur_fdr(True, 0))
    assert s == "PASS"
    s, m = hc.check_85_alpha_wealth_refund_amount_mismatch(_cur_fdr(True, 1))
    assert s == "FAIL" and "phi=1.0" in m


def test_86_cross_family_dup_is_warn_not_fail():
    """MIT 4b：帳務 sound → 觀測級 WARN，永不 FAIL。"""
    s, _ = hc.check_86_pre_reg_cross_family_duplicate_spec(_cur_fdr(True, 0))
    assert s == "PASS"
    s, m = hc.check_86_pre_reg_cross_family_duplicate_spec(_cur_fdr(True, 3))
    assert s == "WARN" and "cross_family_duplicate_specs=3" in m


def test_87_state_regression():
    s, _ = hc.check_87_hidden_oos_state_regression(_cur_fdr(True, 0))
    assert s == "PASS"
    s, m = hc.check_87_hidden_oos_state_regression(_cur_fdr(True, 1))
    assert s == "FAIL" and "QN-1" in m


def test_87_skips_independently_of_fdr_tables():
    """[87] 只依賴 V132 存在性（與 V138 部署解耦）。"""
    cur = _FakeCursor([
        ("to_regclass('learning.hidden_oos_state_registry')", [(False,)]),
    ])
    s, m = hc.check_87_hidden_oos_state_regression(cur)
    assert s == "PASS" and "SKIP" in m


def test_checks_are_read_only():
    """五軸全唯讀：執行軌跡 0 INSERT/UPDATE/DELETE token。"""
    for fn in (
        hc.check_83_alpha_wealth_family_cardinality,
        hc.check_84_alpha_wealth_orphan_refund,
        hc.check_85_alpha_wealth_refund_amount_mismatch,
        hc.check_86_pre_reg_cross_family_duplicate_spec,
        hc.check_87_hidden_oos_state_regression,
    ):
        cur = _cur_fdr(True, 1)
        fn(cur)
        for sql in cur.executed:
            up = sql.upper()
            assert not any(t in up for t in ("INSERT ", "UPDATE ", "DELETE ")), (
                f"{fn.__name__} executed non-read SQL: {sql}"
            )
