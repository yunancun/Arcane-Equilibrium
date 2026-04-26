#!/usr/bin/env python3
"""Tests for ``[21] check_paper_state_dust_inventory`` healthcheck.
``[21] check_paper_state_dust_inventory`` healthcheck 單元測試。

MODULE_NOTE (EN): Standalone unittest sibling for the
PAPER-STATE-DUST-INVENTORY-MONITOR healthcheck (PM Tier 7 Track 2,
2026-04-26). Mirrors ``helper_scripts/canary/test_canary.py`` pattern
(unittest stdlib + sys.path.insert) so it runs without pytest infra
on Mac dev / Linux runtime / CI without a Postgres instance — the
cursor is mocked via ``unittest.mock.MagicMock``.

Verifies the three-state PASS / WARN / FAIL verdict per PA Track 3
§7.4 ready-to-deploy SQL spec (commit ``dd4d64a``):
  * dust_spiral_count = 0 → PASS
  * 1 ≤ dust_spiral_count ≤ 10 AND distinct_dust_symbols < 3 → WARN
  * dust_spiral_count > 10 OR distinct_dust_symbols ≥ 3 → FAIL
Plus boundary cases (10 = WARN; 11 = FAIL; 3 distinct = FAIL),
fail-soft on cursor returning None (PG anomaly), and SQL contract
(strategy_name LIKE pattern + 1h window + engine_mode IN whitelist).

Run:
  python3 helper_scripts/db/test_paper_state_dust_inventory.py
or:
  python3 -m unittest helper_scripts.db.test_paper_state_dust_inventory

MODULE_NOTE (中): PAPER-STATE-DUST-INVENTORY-MONITOR healthcheck
（PM Tier 7 Track 2，2026-04-26）standalone unittest sibling，對齊
``helper_scripts/canary/test_canary.py`` pattern（unittest stdlib +
sys.path.insert），無 pytest infra 也能跑、無 Postgres 也能跑（cursor
用 MagicMock）。

驗證 PA Track 3 §7.4 三態 verdict（commit ``dd4d64a``）：
  * dust_spiral_count = 0 → PASS
  * 1-10 + distinct < 3 → WARN
  * > 10 OR ≥3 distinct → FAIL
含邊界（10=WARN、11=FAIL、3 distinct=FAIL）+ cursor 回 None 時
fail-soft + SQL contract（LIKE pattern + 1h 窗 + engine_mode 白名單）。

Run:
  python3 helper_scripts/db/test_paper_state_dust_inventory.py
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock

# Path setup so we can import the package as a module.
# 路徑設定使我們可以用 package module 形式 import。
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_HELPER_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)
_SRV_ROOT = os.path.dirname(_HELPER_SCRIPTS_DIR)
sys.path.insert(0, _SRV_ROOT)

from helper_scripts.db.passive_wait_healthcheck.checks_engine import (  # noqa: E402
    check_paper_state_dust_inventory,
)


class TestPaperStateDustInventoryVerdict(unittest.TestCase):
    """三態 verdict 路徑覆蓋 / Three-state verdict path coverage."""

    def _make_cursor(self, dust_count: int, distinct_symbols: int) -> MagicMock:
        """Create a MagicMock cursor returning the given (count, distinct) tuple.
        建 MagicMock cursor，fetchone 回給定的 (count, distinct) tuple。"""
        cur = MagicMock()
        cur.fetchone.return_value = (dust_count, distinct_symbols)
        return cur

    def test_zero_dust_returns_pass(self) -> None:
        """dust_spiral_count = 0 → PASS (Gate 1 USD floor working).
        dust_count = 0 → PASS（Gate 1 USD floor 工作中）。"""
        cur = self._make_cursor(0, 0)
        status, msg = check_paper_state_dust_inventory(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("dust_spiral_count=0", msg)
        self.assertIn("Gate 1 USD floor suppressing", msg)

    def test_low_dust_count_returns_warn(self) -> None:
        """1 ≤ dust ≤ 10 AND distinct < 3 → WARN (investigate threshold).
        1-10 + distinct < 3 → WARN（投資調查門檻）。"""
        cur = self._make_cursor(5, 2)
        status, msg = check_paper_state_dust_inventory(cur)
        self.assertEqual(status, "WARN")
        self.assertIn("dust_spiral_count=5", msg)
        self.assertIn("distinct_symbols=2", msg)
        self.assertIn("dust path activity appearing", msg)

    def test_count_exactly_one_returns_warn(self) -> None:
        """Lower boundary count=1 → WARN.
        下邊界 count=1 → WARN。"""
        cur = self._make_cursor(1, 1)
        status, _msg = check_paper_state_dust_inventory(cur)
        self.assertEqual(status, "WARN")

    def test_count_exactly_ten_returns_warn(self) -> None:
        """Upper-WARN boundary count=10 + distinct=2 → WARN
        (count > 10 escalates, count = 10 still WARN).
        WARN 上邊界 count=10 + distinct=2 → WARN（>10 才 escalate）。"""
        cur = self._make_cursor(10, 2)
        status, _msg = check_paper_state_dust_inventory(cur)
        self.assertEqual(status, "WARN")

    def test_count_eleven_returns_fail(self) -> None:
        """count = 11 (>10) → FAIL regardless of distinct.
        count = 11 (>10) → FAIL（不論 distinct）。"""
        cur = self._make_cursor(11, 1)
        status, msg = check_paper_state_dust_inventory(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("Gate 1 not suppressing", msg)

    def test_high_dust_count_returns_fail(self) -> None:
        """dust_spiral_count > 10 → FAIL (Gate 1 not suppressing).
        dust > 10 → FAIL（Gate 1 沒擋住）。"""
        cur = self._make_cursor(50, 5)
        status, msg = check_paper_state_dust_inventory(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("dust_spiral_count=50", msg)
        self.assertIn("EXIT-FEATURES-FIX A1/A3/B1 regression", msg)

    def test_distinct_symbols_three_returns_fail(self) -> None:
        """distinct_symbols ≥ 3 → FAIL even with low count.
        distinct ≥ 3 → FAIL（即使 count 低）。"""
        cur = self._make_cursor(3, 3)
        status, msg = check_paper_state_dust_inventory(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("distinct_symbols=3", msg)

    def test_distinct_symbols_two_with_low_count_returns_warn(self) -> None:
        """distinct = 2 AND count ≤ 10 → WARN (just inside WARN band).
        distinct=2 + count<=10 → WARN（剛進 WARN 帶內）。"""
        cur = self._make_cursor(8, 2)
        status, _msg = check_paper_state_dust_inventory(cur)
        self.assertEqual(status, "WARN")


class TestPaperStateDustInventoryFailSoft(unittest.TestCase):
    """Fail-soft contract 守則（per PA §8 跨 env hard requirement）."""

    def test_cursor_returning_none_returns_warn(self) -> None:
        """Cursor.fetchone() = None (PG anomaly) → WARN, never raise.
        cursor.fetchone() = None（PG 異常）→ WARN，不 raise。"""
        cur = MagicMock()
        cur.fetchone.return_value = None
        status, msg = check_paper_state_dust_inventory(cur)
        self.assertEqual(status, "WARN")
        self.assertIn("PG / cursor anomaly", msg)

    def test_cursor_returning_null_columns_treats_as_zero(self) -> None:
        """Cursor row with None columns treated as 0 (defensive cast).
        Cursor row 含 None 欄位視為 0（防禦性轉型）。"""
        cur = MagicMock()
        cur.fetchone.return_value = (None, None)
        status, msg = check_paper_state_dust_inventory(cur)
        self.assertEqual(status, "PASS")  # Coerced to (0, 0) → PASS path
        self.assertIn("dust_spiral_count=0", msg)


class TestPaperStateDustInventorySqlContract(unittest.TestCase):
    """SQL contract 守則 — 確認 LIKE pattern + 1h 窗 + engine_mode 白名單."""

    def test_sql_uses_like_pattern_for_fast_track(self) -> None:
        """SQL must use LIKE 'risk_close:fast_track%' (not exact match) so
        future fast_track sub-tags are caught automatically.
        SQL 必須用 LIKE 'risk_close:fast_track%'（非 exact match），自動覆蓋
        未來 fast_track 子 tag。"""
        cur = MagicMock()
        cur.fetchone.return_value = (0, 0)
        check_paper_state_dust_inventory(cur)
        sql_used = cur.execute.call_args[0][0]
        self.assertIn("LIKE 'risk_close:fast_track%'", sql_used)
        # Defensive: ensure exact match isn't accidentally introduced
        # 防禦：確保未來不會誤改成 exact match
        self.assertNotIn("= 'risk_close:fast_track_reduce_half'", sql_used)

    def test_sql_uses_one_hour_window(self) -> None:
        """SQL window = 1 hour (PA spec; matches MIT §6 #6 cadence).
        SQL 窗口 = 1 小時（PA spec；符合 MIT §6 #6 節奏）。"""
        cur = MagicMock()
        cur.fetchone.return_value = (0, 0)
        check_paper_state_dust_inventory(cur)
        sql_used = cur.execute.call_args[0][0]
        self.assertIn("now() - interval '1 hour'", sql_used)

    def test_sql_filters_engine_mode_whitelist(self) -> None:
        """SQL must filter engine_mode IN ('demo','live','live_demo') —
        excludes paper engine noise per PA §7.4 +1.
        SQL 必須過濾 engine_mode IN ('demo','live','live_demo')，per PA §7.4
        排除 paper engine 噪音。"""
        cur = MagicMock()
        cur.fetchone.return_value = (0, 0)
        check_paper_state_dust_inventory(cur)
        sql_used = cur.execute.call_args[0][0]
        self.assertIn("engine_mode IN ('demo', 'live', 'live_demo')", sql_used)
        # Defensive: paper must not slip into the whitelist
        # 防禦：paper 不可進白名單
        self.assertNotIn("'paper'", sql_used)

    def test_sql_uses_filter_clauses_for_realized_pnl_zero(self) -> None:
        """SQL must use COUNT FILTER (WHERE realized_pnl=0) for both
        dust_spiral_count and distinct_dust_symbols — single-roundtrip
        compute per PA Track 3 §7.4.
        SQL 必須對 dust_spiral_count + distinct_dust_symbols 都用 COUNT
        FILTER (WHERE realized_pnl=0)，per PA §7.4 單次 round-trip。"""
        cur = MagicMock()
        cur.fetchone.return_value = (0, 0)
        check_paper_state_dust_inventory(cur)
        sql_used = cur.execute.call_args[0][0]
        self.assertIn("FILTER (WHERE realized_pnl = 0)", sql_used)
        # Both COUNT(*) and COUNT(DISTINCT symbol) must exist with the FILTER
        # 兩個 COUNT 都要有 FILTER 子句
        self.assertIn("COUNT(*) FILTER", sql_used)
        self.assertIn("COUNT(DISTINCT symbol) FILTER", sql_used)


if __name__ == "__main__":
    unittest.main()
