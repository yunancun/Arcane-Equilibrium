#!/usr/bin/env python3
"""Tests for F7 healthchecks [22]-[29] — MIT DB audit + E5 engine.log dive.
F7 healthcheck [22]-[29] 單元測試 — MIT DB audit + E5 engine.log dive。

MODULE_NOTE (EN): Standalone unittest sibling for the 8 F7
silent-regression sentinels added 2026-04-26. Mirrors
``test_paper_state_dust_inventory.py`` pattern (unittest stdlib +
sys.path.insert + ``MagicMock`` cursor) so it runs without pytest infra
on Mac dev / Linux runtime / CI without a Postgres instance.

Coverage matrix (39 tests across 8 checks; [23] +1 F7-FUP-23 SQL contract):

    [22] trading_pipeline_silent_gap          (5 tests) — DCS cliff vs fills cliff
    [23] orders_fills_consistency             (6 tests) — orders writer drop +
                                                          F7-FUP-23 unattributed audit exclude
    [24] signals_writer_freshness             (5 tests) — 4/19 silent outage fingerprint
    [25] dust_qty_distribution                (5 tests) — log10 sub-micro drift
    [26] dust_spiral_noise_in_ef              (5 tests) — ML training corpus hygiene
    [27] intents_counter_freeze               (5 tests) — intent counter wedge
    [28] phantom_fills_attribution            (5 tests) — risk_close + qty<1e-3 mis-attribute
    [29] reconciler_paper_state_divergence    (3 tests) — deferred-no-ipc placeholder

Each verdict block exercises PASS / WARN / FAIL plus a fail-soft path
(SQL exception → WARN, never raise) and at least one boundary edge case.

Run:
  python3 helper_scripts/db/test_f7_new_healthchecks.py
or from package root:
  python3 -m unittest helper_scripts.db.test_f7_new_healthchecks -v

MODULE_NOTE (中): F7 [22]-[29] 8 個 silent-regression 哨兵
（2026-04-26 新增）standalone unittest sibling，對齊
``test_paper_state_dust_inventory.py`` pattern（unittest stdlib +
sys.path.insert + MagicMock cursor）；無 pytest infra / 無 Postgres
也能跑。

Coverage matrix（合 39 tests / 8 check；[23] +1 F7-FUP-23 SQL contract）：
    [22] trading_pipeline_silent_gap          5 tests — DCS cliff vs fills cliff
    [23] orders_fills_consistency             6 tests — orders writer 漏寫 +
                                                       F7-FUP-23 unattributed audit 排除
    [24] signals_writer_freshness             5 tests — 4/19 silent outage 指紋
    [25] dust_qty_distribution                5 tests — log10 sub-micro 漂移
    [26] dust_spiral_noise_in_ef              5 tests — ML 訓練語料 hygiene
    [27] intents_counter_freeze               5 tests — intent counter 卡死
    [28] phantom_fills_attribution            5 tests — risk_close + qty<1e-3 錯歸屬
    [29] reconciler_paper_state_divergence    3 tests — deferred-no-ipc placeholder

每個 check 覆蓋 PASS / WARN / FAIL + fail-soft（SQL 例外→WARN 不 raise）+
至少一個邊界 edge case。

Run:
  python3 helper_scripts/db/test_f7_new_healthchecks.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Path setup so we can import the package as a module (匹配 sibling 風格).
# 路徑設定使我們可以用 package module 形式 import。
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_HELPER_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)
_SRV_ROOT = os.path.dirname(_HELPER_SCRIPTS_DIR)
sys.path.insert(0, _SRV_ROOT)

from helper_scripts.db.passive_wait_healthcheck.checks_engine import (  # noqa: E402
    check_trading_pipeline_silent_gap,
    check_orders_fills_consistency,
    check_dust_qty_distribution,
    check_intents_counter_freeze,
    check_phantom_fills_attribution,
    check_reconciler_paper_state_divergence,
)
from helper_scripts.db.passive_wait_healthcheck.checks_strategy import (  # noqa: E402
    check_signals_writer_freshness,
)
from helper_scripts.db.passive_wait_healthcheck.checks_derived import (  # noqa: E402
    check_dust_spiral_noise_in_ef,
)


# =============================================================================
# Helper: build a MagicMock cursor whose `connection.rollback()` is also Mock.
# Helper：建立 MagicMock cursor，連 connection.rollback() 一併 Mock 化。
# Each check_* uses defensive ``cur.connection.rollback()`` to clear poisoned
# tx state before issuing its SELECT, so we have to provide that attribute.
# 每個 check 在 SELECT 前用 defensive ``cur.connection.rollback()`` 清髒 tx，
# 因此 mock cursor 必須提供 connection 屬性。
# =============================================================================


def _make_cursor() -> MagicMock:
    """Create a MagicMock cursor with rollback-able connection attribute.
    建一個含 rollback-able connection 屬性的 MagicMock cursor。"""
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.rollback = MagicMock()
    return cur


# =============================================================================
# [22] check_trading_pipeline_silent_gap — DCS active but fills cliff.
# [22] DCS 活但下游 fill 死的盲點。
# =============================================================================


class TestTradingPipelineSilentGap(unittest.TestCase):
    """三態 verdict + schema-drift fail-soft for [22]."""

    def setUp(self) -> None:
        """Disable runtime fresh-restart grace in unit tests.
        單元測試固定關閉現場 runtime fresh-restart grace。"""
        self._engine_age_patch = patch(
            "helper_scripts.db.passive_wait_healthcheck.checks_engine._engine_process_age_minutes",
            return_value=(None, "unit-test"),
        )
        self._engine_age_patch.start()

    def tearDown(self) -> None:
        """Restore engine-age helper patch.
        還原 engine-age helper patch。"""
        self._engine_age_patch.stop()

    @staticmethod
    def _make_cursor_with_layers(
        fills_stale: float | None,
        fills_1h: int,
        intents_stale: float | None,
        intents_1h: int,
        orders_stale: float | None,
        orders_1h: int,
        risk_stale: float | None,
        risk_1h: int,
        dcs_stale: float | None,
        dcs_1h: int,
    ) -> MagicMock:
        """Mock cursor returning the 5-layer UNION ALL row tuples.
        Mock cursor 回 5 層 UNION ALL row tuples。"""
        cur = _make_cursor()
        cur.fetchall.return_value = [
            ("fills", fills_stale, fills_1h),
            ("intents", intents_stale, intents_1h),
            ("orders", orders_stale, orders_1h),
            ("risk_verdicts", risk_stale, risk_1h),
            ("decision_context_snapshots", dcs_stale, dcs_1h),
        ]
        return cur

    def test_dcs_active_fills_cliff_returns_fail(self) -> None:
        """DCS rows_1h > 100 AND fills minutes_stale > 60 → FAIL.
        DCS 活 + fills cliff > 60 min → FAIL。"""
        cur = self._make_cursor_with_layers(
            fills_stale=120.0, fills_1h=0,
            intents_stale=120.0, intents_1h=0,
            orders_stale=10.0, orders_1h=50,
            risk_stale=10.0, risk_1h=50,
            dcs_stale=2.0, dcs_1h=200,
        )
        status, msg = check_trading_pipeline_silent_gap(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("strategist active (DCS>100/h) but fills cliff>60min", msg)

    def test_dcs_active_fills_30_to_60_returns_warn(self) -> None:
        """DCS > 100 AND fills 30-60 min stale + 1h=0 → WARN (early warning).
        DCS 活 + fills cliff 30-60 min + 1h=0 → WARN（早期警告）。"""
        cur = self._make_cursor_with_layers(
            fills_stale=45.0, fills_1h=0,
            intents_stale=45.0, intents_1h=0,
            orders_stale=10.0, orders_1h=50,
            risk_stale=10.0, risk_1h=50,
            dcs_stale=2.0, dcs_1h=150,
        )
        status, msg = check_trading_pipeline_silent_gap(cur)
        self.assertEqual(status, "WARN")
        self.assertIn("early-warning of pipeline wedge", msg)

    def test_fresh_fills_returns_pass(self) -> None:
        """fills_stale < 30 → PASS regardless of DCS volume.
        fills 新鮮 → PASS（不論 DCS 流量）。"""
        cur = self._make_cursor_with_layers(
            fills_stale=2.0, fills_1h=80,
            intents_stale=2.0, intents_1h=80,
            orders_stale=2.0, orders_1h=80,
            risk_stale=2.0, risk_1h=80,
            dcs_stale=2.0, dcs_1h=200,
        )
        status, msg = check_trading_pipeline_silent_gap(cur)
        self.assertEqual(status, "PASS")
        # 訊息 still contains per-layer one-liners.
        self.assertIn("fills:", msg)
        self.assertIn("decision_context_snapshots:", msg)

    def test_dcs_quiet_returns_pass(self) -> None:
        """DCS rows_1h <= 100 (strategist quiet) → PASS even if fills stale.
        DCS 安靜 → PASS（即便 fills stale）。"""
        cur = self._make_cursor_with_layers(
            fills_stale=120.0, fills_1h=0,
            intents_stale=120.0, intents_1h=0,
            orders_stale=120.0, orders_1h=0,
            risk_stale=120.0, risk_1h=0,
            dcs_stale=120.0, dcs_1h=20,
        )
        status, _msg = check_trading_pipeline_silent_gap(cur)
        self.assertEqual(status, "PASS")

    def test_query_exception_returns_warn(self) -> None:
        """Schema drift / undefined_table → WARN fail-soft (no raise).
        Schema drift / undefined_table → WARN fail-soft（不 raise）。"""
        cur = _make_cursor()
        cur.execute.side_effect = Exception("UndefinedTable: trading.fills")
        status, msg = check_trading_pipeline_silent_gap(cur)
        self.assertEqual(status, "WARN")
        self.assertIn("silent_gap query failed", msg)


# =============================================================================
# [23] check_orders_fills_consistency — orders writer dropping rows.
# [23] orders writer 漏寫偵測。
# =============================================================================


class TestOrdersFillsConsistency(unittest.TestCase):
    """三態 verdict + total_pairs=0 + fail-soft for [23]."""

    def _make_cursor_with_row(
        self, pairs_missing: int, total_pairs: int, total_missing: int
    ) -> MagicMock:
        """Mock cursor returning the aggregate row tuple.
        Mock cursor 回 aggregate row tuple。"""
        cur = _make_cursor()
        cur.fetchone.return_value = (pairs_missing, total_pairs, total_missing)
        return cur

    def test_zero_missing_returns_pass(self) -> None:
        """pairs_with_missing_orders = 0 → PASS (consistent).
        無 pair 漏寫 → PASS（一致）。"""
        cur = self._make_cursor_with_row(0, 20, 0)
        status, msg = check_orders_fills_consistency(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("orders writer consistent with fills", msg)

    def test_low_missing_returns_warn(self) -> None:
        """1 ≤ pairs_missing ≤ 5 → WARN (transient or single pair).
        1-5 pair 漏寫 → WARN（短暫或單對）。"""
        cur = self._make_cursor_with_row(2, 20, 5)
        status, msg = check_orders_fills_consistency(cur)
        self.assertEqual(status, "WARN")
        self.assertIn("partial orders writer drop", msg)

    def test_high_missing_returns_fail(self) -> None:
        """pairs_missing > 5 → FAIL (writer broken across multiple pairs).
        pairs_missing > 5 → FAIL（writer 跨多 pair 壞）。"""
        cur = self._make_cursor_with_row(10, 30, 50)
        status, msg = check_orders_fills_consistency(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("orders writer dropping rows across >5 pairs", msg)

    def test_no_fills_in_window_returns_pass(self) -> None:
        """total_pairs = 0 (no fills in 30 min) → PASS (defer to [1]/[22]).
        30 min 內無 fill → PASS（留 [1]/[22] cliff 信號）。"""
        cur = self._make_cursor_with_row(0, 0, 0)
        status, msg = check_orders_fills_consistency(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("no fills in window", msg)

    def test_query_exception_returns_warn(self) -> None:
        """Cursor exception → WARN fail-soft.
        Cursor 例外 → WARN fail-soft。"""
        cur = _make_cursor()
        cur.execute.side_effect = Exception("UndefinedTable: trading.orders")
        status, msg = check_orders_fills_consistency(cur)
        self.assertEqual(status, "WARN")
        self.assertIn("orders_fills consistency query failed", msg)

    def test_sql_excludes_f4_unattributed_audit_rows(self) -> None:
        """F7-FUP-23: SQL must exclude F4 unattributed audit rows
        (``strategy_name LIKE 'unattributed:%'``) — they are audit-by-design
        with no corresponding ``trading.orders`` row, and would otherwise
        fabricate a false-positive FAIL after the F4 backfill runs.

        F7-FUP-23：SQL 必須排除 F4 unattributed audit row
        （``strategy_name LIKE 'unattributed:%'``）— audit-by-design 無對應
        ``trading.orders`` row，否則 F4 backfill 後會系統性產生假 FAIL。

        Contract test: assert the literal NOT LIKE filter is wired into the
        rendered SQL string captured by ``cur.execute.call_args``.
        Contract test：抓 ``cur.execute.call_args`` 的 SQL 字串斷言含
        NOT LIKE filter。"""
        # Drive the check with a benign all-PASS row so we get past the
        # rollback + execute and reach the post-execute assertions.
        # 用 benign all-PASS row 餵 check 跑完 execute，再做 SQL contract 斷言。
        cur = self._make_cursor_with_row(0, 5, 0)
        status, _ = check_orders_fills_consistency(cur)
        self.assertEqual(status, "PASS")

        # Verify SQL contract: the ``strategy_name NOT LIKE 'unattributed:%'``
        # clause must exist in the WHERE block.
        # SQL 契約驗證：WHERE 區段必須含 ``strategy_name NOT LIKE 'unattributed:%'``。
        cur.execute.assert_called_once()
        sql_text = cur.execute.call_args.args[0]
        self.assertIn(
            "f.strategy_name NOT LIKE 'unattributed:%'",
            sql_text,
            msg=(
                "F7-FUP-23 SQL contract violated — F4 unattributed audit rows "
                "must be excluded from the orders ⊇ fills LEFT JOIN. "
                "F7-FUP-23 SQL 契約違反 — F4 unattributed audit row 必須從 "
                "orders ⊇ fills LEFT JOIN 排除。"
            ),
        )


# =============================================================================
# [24] check_signals_writer_freshness — trading.signals dead-writer.
# [24] trading.signals dead-writer 偵測。
# =============================================================================


class TestSignalsWriterFreshness(unittest.TestCase):
    """三態 verdict + empty table fingerprint + missing table for [24]."""

    def setUp(self) -> None:
        """Isolate paper-disabled snapshot auto-skip from the developer/runtime host.
        隔離開發/運行主機上的 paper-disabled snapshot auto-skip。"""
        self._tmpdir = tempfile.TemporaryDirectory()
        self._env_patch = patch.dict(
            os.environ,
            {"OPENCLAW_DATA_DIR": self._tmpdir.name},
            clear=False,
        )
        self._env_patch.start()

    def tearDown(self) -> None:
        """Restore environment and remove temporary data dir.
        還原環境並刪除臨時資料目錄。"""
        self._env_patch.stop()
        self._tmpdir.cleanup()

    def _make_cursor_with_freshness(
        self, hours_stale: float | None, rows_24h: int, table_exists: bool = True
    ) -> MagicMock:
        """Mock cursor — first call returns to_regclass IS NOT NULL bool, second
        returns (hours_stale, rows_24h).
        Mock cursor — 第一次 fetchone 回表存在性，第二次回 (hours_stale, rows_24h)。"""
        cur = _make_cursor()
        cur.fetchone.side_effect = [
            (table_exists,),
            (hours_stale, rows_24h),
        ]
        return cur

    def test_fresh_writer_returns_pass(self) -> None:
        """hours_stale < 1.0 → PASS.
        hours_stale < 1.0 → PASS。"""
        cur = self._make_cursor_with_freshness(0.5, 100)
        status, msg = check_signals_writer_freshness(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("writer fresh", msg)

    def test_drift_writer_returns_warn(self) -> None:
        """hours_stale 1-6h → WARN.
        hours_stale 1-6h → WARN。"""
        cur = self._make_cursor_with_freshness(2.5, 50)
        status, msg = check_signals_writer_freshness(cur)
        self.assertEqual(status, "WARN")
        self.assertIn("writer drift 1-6h", msg)

    def test_dead_writer_returns_fail(self) -> None:
        """hours_stale > 6h → FAIL (4/19 silent outage fingerprint).
        hours_stale > 6h → FAIL（4/19 silent outage 指紋）。"""
        cur = self._make_cursor_with_freshness(72.0, 0)
        status, msg = check_signals_writer_freshness(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("writer dead >6h", msg)
        self.assertIn("2026-04-19 silent outage", msg)

    def test_empty_table_returns_fail(self) -> None:
        """max(ts) over empty table = NULL → FAIL with explicit
        "table never written to" message (4/19-style fingerprint).
        空表 max(ts)→NULL → FAIL，顯式「table never written to」（4/19 指紋）。"""
        cur = self._make_cursor_with_freshness(None, 0)
        status, msg = check_signals_writer_freshness(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("table never written to", msg)

    def test_missing_table_returns_fail(self) -> None:
        """to_regclass returns False → FAIL "V004 not applied".
        to_regclass 回 False → FAIL "V004 not applied"。"""
        cur = self._make_cursor_with_freshness(0.5, 0, table_exists=False)
        status, msg = check_signals_writer_freshness(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("V004 not applied", msg)


# =============================================================================
# [25] check_dust_qty_distribution — log10 sub-micro drift.
# [25] fills.qty 對數桶分布 sub-micro 漂移。
# =============================================================================


class TestDustQtyDistribution(unittest.TestCase):
    """三態 verdict + empty window + fail-soft for [25]."""

    def _make_cursor_with_dist(
        self, sub_micro_buckets: int, normal_buckets: int, pct_sub_micro: float
    ) -> MagicMock:
        """Mock cursor returning (sub_micro, normal, pct) row tuple.
        Mock cursor 回 (sub_micro, normal, pct) row tuple。"""
        cur = _make_cursor()
        cur.fetchone.return_value = (sub_micro_buckets, normal_buckets, pct_sub_micro)
        return cur

    def test_low_sub_micro_returns_pass(self) -> None:
        """pct_sub_micro <= 10% → PASS (Gate 1 USD floor holding).
        pct_sub_micro <= 10% → PASS（Gate 1 USD floor 工作中）。"""
        cur = self._make_cursor_with_dist(1, 5, 5.0)
        status, msg = check_dust_qty_distribution(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("Gate 1 USD floor holding", msg)

    def test_warn_band_returns_warn(self) -> None:
        """pct_sub_micro 10-30% → WARN (early warning).
        pct_sub_micro 10-30% → WARN（早期警告）。"""
        cur = self._make_cursor_with_dist(2, 5, 20.0)
        status, msg = check_dust_qty_distribution(cur)
        self.assertEqual(status, "WARN")
        self.assertIn("sub-micro fills >10%", msg)

    def test_high_sub_micro_returns_fail(self) -> None:
        """pct_sub_micro > 30% → FAIL (regression).
        pct_sub_micro > 30% → FAIL（dust spiral 復發）。"""
        cur = self._make_cursor_with_dist(4, 3, 45.0)
        status, msg = check_dust_qty_distribution(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("dust spiral re-emerged", msg)
        self.assertIn("EXIT-FEATURES-FIX A1/A3/B1 regressed", msg)

    def test_empty_window_returns_pass(self) -> None:
        """sub_micro = 0 + normal = 0 → PASS (no fills in 24h, defer).
        24h 全空 → PASS（留 [1]/[22] cliff 信號）。"""
        cur = self._make_cursor_with_dist(0, 0, 0.0)
        status, msg = check_dust_qty_distribution(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("no fills in 24h", msg)

    def test_query_exception_returns_warn(self) -> None:
        """log10 negative-input math error → WARN fail-soft.
        log10 負輸入 math error → WARN fail-soft。"""
        cur = _make_cursor()
        cur.execute.side_effect = Exception("ERROR: cannot take logarithm of zero")
        status, msg = check_dust_qty_distribution(cur)
        self.assertEqual(status, "WARN")
        self.assertIn("dust_qty distribution query failed", msg)


# =============================================================================
# [26] check_dust_spiral_noise_in_ef — ML training corpus hygiene.
# [26] learning.exit_features 中 dust spiral 雜訊 — ML hygiene 哨兵。
# =============================================================================


class TestDustSpiralNoiseInEf(unittest.TestCase):
    """三態 verdict + table-missing + fail-soft for [26]."""

    def _make_cursor_with_noise(
        self,
        noise_total: int,
        noise_24h: int,
        table_exists: bool = True,
    ) -> MagicMock:
        """Mock cursor — to_regclass first, then (total, 24h) row tuple.
        Mock cursor — 先 to_regclass，再 (total, 24h) row。"""
        cur = _make_cursor()
        cur.fetchone.side_effect = [
            (table_exists,),
            (noise_total, noise_24h),
        ]
        return cur

    def test_no_noise_returns_pass(self) -> None:
        """noise_24h <= 5 → PASS (B1 holding).
        noise_24h <= 5 → PASS（B1 工作中）。"""
        cur = self._make_cursor_with_noise(50, 3)
        status, msg = check_dust_spiral_noise_in_ef(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("B1 holding", msg)

    def test_warn_band_returns_warn(self) -> None:
        """6 ≤ noise_24h ≤ 20 → WARN (possible new sub-tag).
        6-20 → WARN（可能新 sub-tag 漏抓）。"""
        cur = self._make_cursor_with_noise(100, 12)
        status, msg = check_dust_spiral_noise_in_ef(cur)
        self.assertEqual(status, "WARN")
        self.assertIn("possible new partial-reduce sub-tag escaping B1", msg)

    def test_high_noise_returns_fail(self) -> None:
        """noise_24h > 20 → FAIL (B1 regression).
        noise_24h > 20 → FAIL（B1 regression）。"""
        cur = self._make_cursor_with_noise(500, 50)
        status, msg = check_dust_spiral_noise_in_ef(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("B1 (is_partial_reduce_tag) regression", msg)

    def test_missing_table_returns_fail(self) -> None:
        """to_regclass returns False → FAIL "V016/V019 not applied".
        to_regclass 回 False → FAIL "V016/V019 not applied"。"""
        cur = self._make_cursor_with_noise(0, 0, table_exists=False)
        status, msg = check_dust_spiral_noise_in_ef(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("V016/V019 not applied", msg)

    def test_query_exception_returns_warn(self) -> None:
        """Cursor exception → WARN fail-soft (the COUNT query raises after
        to_regclass succeeded — schema drift mid-check).
        Cursor 例外 → WARN fail-soft（to_regclass 通過後 COUNT query raise，
        check 進行中遇 schema drift）。"""
        cur = _make_cursor()
        # First execute = to_regclass (no-op via MagicMock), then fetchone
        # returns (True,) so existence guard passes. Second execute = the
        # noise-count SQL — we make THAT raise. Achieved by toggling
        # ``execute.side_effect`` to a list of [None, Exception] so each
        # call consumes the next; ``fetchone.side_effect`` is a single-element
        # list so only the existence-guard fetchone fires.
        # 第一個 execute = to_regclass（MagicMock no-op），fetchone 回 (True,)
        # 過存在性閘；第二個 execute = noise-count SQL → 讓它 raise。用
        # execute.side_effect = [None, Exception] 讓兩次呼叫依序消費；
        # fetchone.side_effect 單元素列表只在存在性閘時觸發。
        cur.fetchone.side_effect = [(True,)]
        cur.execute.side_effect = [
            None,
            Exception("UndefinedColumn: ts"),
        ]
        status, msg = check_dust_spiral_noise_in_ef(cur)
        self.assertEqual(status, "WARN")
        self.assertIn("dust_spiral noise EF query failed", msg)


# =============================================================================
# [27] check_intents_counter_freeze — intents counter not incrementing.
# [27] intents counter 30+ min 不前進。
# =============================================================================


class TestIntentsCounterFreeze(unittest.TestCase):
    """三態 verdict + never-produced + multi-mode worst-wins for [27]."""

    def setUp(self) -> None:
        """Disable runtime fresh-restart grace in unit tests.
        單元測試固定關閉現場 runtime fresh-restart grace。"""
        self._engine_age_patch = patch(
            "helper_scripts.db.passive_wait_healthcheck.checks_engine._engine_process_age_minutes",
            return_value=(None, "unit-test"),
        )
        self._engine_age_patch.start()

    def tearDown(self) -> None:
        """Restore engine-age helper patch.
        還原 engine-age helper patch。"""
        self._engine_age_patch.stop()

    def _make_cursor_with_modes(
        self,
        mode_data: list[tuple[float | None, int]],
        guardian_data: list[tuple[int, int] | None] | None = None,
    ) -> MagicMock:
        """Mock cursor rows for each mode plus slow-path Guardian/DCS probes.

        ``check_intents_counter_freeze`` now cross-checks
        ``trading.risk_verdicts`` and ``decision_context_snapshots`` when a
        mode has no recent intents. ``guardian_data`` provides the extra
        ``(verdicts_30min, dcs_30min)`` rows for those slow-path modes.

        Mock 每個 mode 的 intent row，並在 frozen slow-path 補 Guardian/DCS
        查詢結果。``guardian_data`` 依 demo/live_demo/live 順序提供
        ``(verdicts_30min, dcs_30min)``。
        """
        cur = _make_cursor()
        guardian_data = guardian_data or [None] * len(mode_data)
        rows: list[tuple[float | None, int] | tuple[int]] = []
        for idx, (m_since, n_30) in enumerate(mode_data):
            rows.append((m_since, n_30))
            if m_since is not None and n_30 == 0 and m_since > 15.0:
                verdicts_30min, dcs_30min = guardian_data[idx] or (150, 0)
                rows.append((verdicts_30min,))
                rows.append((dcs_30min,))
        cur.fetchone.side_effect = rows
        return cur

    def test_all_modes_fresh_returns_pass(self) -> None:
        """All modes minutes_since < 15 → PASS.
        所有 mode minutes_since < 15 → PASS。"""
        cur = self._make_cursor_with_modes([
            (5.0, 20),    # demo
            (5.0, 15),    # live_demo
            (None, 0),    # live (never produced)
        ])
        status, msg = check_intents_counter_freeze(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("demo:", msg)
        self.assertIn("live_demo:", msg)
        # live 從未產生 intent 一律 PASS-skip。
        self.assertIn("never produced an intent", msg)

    def test_demo_15_to_30_returns_warn(self) -> None:
        """demo minutes_since 15-30 + intents_30min=0 → WARN (counter not
        incrementing); other modes fresh.
        demo 15-30 + 0/30min → WARN（counter 不前進）；其他 mode 新鮮。"""
        cur = self._make_cursor_with_modes([
            (20.0, 0),    # demo (WARN)
            (5.0, 15),    # live_demo (PASS)
            (None, 0),    # live (never produced)
        ], guardian_data=[
            (150, 10),     # demo Guardian/DCS alive → early-warning WARN
            None,
            None,
        ])
        status, msg = check_intents_counter_freeze(cur)
        self.assertEqual(status, "WARN")
        self.assertIn("counter not incrementing 15-30min", msg)

    def test_demo_over_30_min_returns_fail(self) -> None:
        """demo minutes_since > 30 + intents_30min=0 → FAIL (frozen).
        demo > 30min + 0/30min → FAIL（counter 卡死）。"""
        cur = self._make_cursor_with_modes([
            (45.0, 0),    # demo (FAIL — frozen)
            (5.0, 15),    # live_demo (PASS)
            (None, 0),    # live (never produced)
        ], guardian_data=[
            (50, 10),      # demo DCS active but verdicts below liveness threshold
            None,
            None,
        ])
        status, msg = check_intents_counter_freeze(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("counter frozen >30min", msg)
        self.assertIn("intent persistence dropped", msg)

    def test_never_produced_does_not_fail(self) -> None:
        """All modes return NULL max(ts) (never produced) → PASS, no FAIL.
        所有 mode max(ts)=NULL（從未產生）→ PASS，不 FAIL。"""
        cur = self._make_cursor_with_modes([
            (None, 0),    # demo
            (None, 0),    # live_demo
            (None, 0),    # live
        ])
        status, msg = check_intents_counter_freeze(cur)
        self.assertEqual(status, "PASS")
        # Each mode emits explicit "never produced" verbiage.
        self.assertIn("never produced an intent", msg)

    def test_worst_wins_aggregation(self) -> None:
        """Composite status = worst across modes. demo FAIL + live_demo WARN
        → overall FAIL.
        Composite = 最差勝。demo FAIL + live_demo WARN → 整體 FAIL。"""
        cur = self._make_cursor_with_modes([
            (45.0, 0),    # demo FAIL
            (20.0, 0),    # live_demo WARN
            (None, 0),    # live PASS (never produced)
        ], guardian_data=[
            (50, 10),      # demo FAIL
            (150, 10),     # live_demo WARN
            None,
        ])
        status, msg = check_intents_counter_freeze(cur)
        self.assertEqual(status, "FAIL")
        # 兩個 mode 都應出現在 message 中。
        self.assertIn("demo:", msg)
        self.assertIn("live_demo:", msg)


# =============================================================================
# [28] check_phantom_fills_attribution — risk_close + qty<1e-3 mis-attribute.
# [28] risk_close 子-mililiter qty mis-attribution。
# =============================================================================


class TestPhantomFillsAttribution(unittest.TestCase):
    """三態 verdict + mixed FAIL/WARN + fail-soft for [28]."""

    def _make_cursor_with_pairs(self, rows: list[tuple[str, str, int]]) -> MagicMock:
        """Mock cursor returning fetchall list of (engine_mode, symbol, count).
        Mock cursor fetchall 回 [(engine_mode, symbol, count), ...]。"""
        cur = _make_cursor()
        cur.fetchall.return_value = rows
        return cur

    def test_no_phantom_pairs_returns_pass(self) -> None:
        """No rows returned → PASS (no phantom fills).
        無 row → PASS（無 phantom fill）。"""
        cur = self._make_cursor_with_pairs([])
        status, msg = check_phantom_fills_attribution(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("no phantom fills in 1h", msg)

    def test_warn_band_returns_warn(self) -> None:
        """Pair count 2-4 → WARN.
        Pair 計數 2-4 → WARN。"""
        cur = self._make_cursor_with_pairs([
            ("demo", "BTCUSDT", 3),
            ("demo", "ETHUSDT", 2),
        ])
        status, msg = check_phantom_fills_attribution(cur)
        self.assertEqual(status, "WARN")
        self.assertIn("phantom fills WARN pairs", msg)
        self.assertIn("BTCUSDT=3", msg)

    def test_fail_band_returns_fail(self) -> None:
        """Pair count >= 5 → FAIL.
        Pair 計數 >= 5 → FAIL。"""
        cur = self._make_cursor_with_pairs([
            ("demo", "BTCUSDT", 8),
            ("live_demo", "ETHUSDT", 6),
        ])
        status, msg = check_phantom_fills_attribution(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("phantom fills FAIL pairs", msg)
        self.assertIn("RCA reconciler / paper_state symbol attribution", msg)

    def test_mixed_fail_and_warn_returns_fail(self) -> None:
        """Both FAIL pair (>=5) and WARN pair (2-4) → overall FAIL with
        WARN list appended.
        混合 FAIL (>=5) + WARN (2-4) → 整體 FAIL，附加 WARN 列表。"""
        cur = self._make_cursor_with_pairs([
            ("demo", "BTCUSDT", 10),    # FAIL
            ("demo", "ETHUSDT", 3),     # WARN
        ])
        status, msg = check_phantom_fills_attribution(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("FAIL pairs", msg)
        self.assertIn("WARN pairs", msg)

    def test_query_exception_returns_warn(self) -> None:
        """Cursor exception → WARN fail-soft.
        Cursor 例外 → WARN fail-soft。"""
        cur = _make_cursor()
        cur.execute.side_effect = Exception("Connection terminated")
        status, msg = check_phantom_fills_attribution(cur)
        self.assertEqual(status, "WARN")
        self.assertIn("phantom_fills attribution query failed", msg)


# =============================================================================
# [29] check_reconciler_paper_state_divergence — deferred-no-ipc placeholder.
# [29] reconciler vs paper_state divergence — deferred-no-ipc placeholder。
# =============================================================================


class TestReconcilerPaperStateDivergence(unittest.TestCase):
    """Deferred-no-ipc placeholder behaviour for [29]."""

    def test_default_call_returns_pass_deferred(self) -> None:
        """Default call (no arg) → PASS with [deferred-no-ipc] prefix.
        預設呼叫（無 arg）→ PASS 帶 [deferred-no-ipc] 前綴。"""
        status, msg = check_reconciler_paper_state_divergence()
        self.assertEqual(status, "PASS")
        self.assertIn("[deferred-no-ipc]", msg)

    def test_message_documents_deferred_state(self) -> None:
        """PASS message must clearly mark this as a deferred placeholder so
        operator does not interpret it as real divergence-clean signal.
        PASS message 必須明確標 deferred placeholder，避免 operator 誤讀為
        真實「無分歧」信號。"""
        _status, msg = check_reconciler_paper_state_divergence()
        self.assertIn("Rust IPC method get_reconciler_status not yet exposed", msg)
        # F7 follow-up note keeps the migration path discoverable.
        # F7 follow-up 提示讓未來 IPC 升級路徑可被搜尋到。
        self.assertIn("F7 follow-up", msg)

    def test_accepts_optional_cursor_arg(self) -> None:
        """Function signature accepts an optional cursor (kept for runner
        contract uniformity); behaviour identical with or without it.
        函式簽章接受可選 cursor（保持 runner 契約一致），有無皆同行為。"""
        cur = _make_cursor()
        status, msg = check_reconciler_paper_state_divergence(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("[deferred-no-ipc]", msg)


if __name__ == "__main__":
    unittest.main()
