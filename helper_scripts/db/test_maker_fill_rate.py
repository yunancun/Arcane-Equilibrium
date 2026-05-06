#!/usr/bin/env python3
"""Tests for [33] maker_fill_rate.
[33] maker_fill_rate 單元測試。
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_HELPER_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)
_SRV_ROOT = os.path.dirname(_HELPER_SCRIPTS_DIR)
sys.path.insert(0, _SRV_ROOT)

from helper_scripts.db.passive_wait_healthcheck.checks_execution import (  # noqa: E402
    check_grid_trading_lifecycle_drift,
    check_maker_fill_rate,
)


def _make_cursor(
    summary: tuple[int, int, float | None, int, int] | None,
    strategy_rows: list[tuple[str, int, int, float]] | None = None,
) -> MagicMock:
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.rollback = MagicMock()
    cur.fetchone.return_value = summary
    cur.fetchall.return_value = strategy_rows or []
    return cur


def _make_grid_lifecycle_cursor(
    lifecycle_rows: list[tuple[str, int, float, float, float, float]],
    cohort_row: tuple[int, int, int, float | None, float | None],
    reentry_rows: list[tuple[str, int, int, float]],
) -> MagicMock:
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.rollback = MagicMock()
    cur.fetchone.side_effect = [(True,), cohort_row]
    cur.fetchall.side_effect = [lifecycle_rows, reentry_rows]
    return cur


_LIFECYCLE_GLOBAL_FAIL_MIX = [
    ("demo", 12, 14.5, 15.0, 1.0, 10.0),
    ("live_demo", 7, 4.2, 5.0, 0.7, 7.0),
]

_LOW_REENTRY_ROWS = [
    ("demo", 12, 2, 0.1667),
    ("live_demo", 7, 3, 0.4286),
]


class TestMakerFillRate(unittest.TestCase):
    def test_no_fills_passes(self) -> None:
        status, msg = check_maker_fill_rate(_make_cursor((0, 0, None, 0, 0)))
        self.assertEqual(status, "PASS")
        self.assertIn("entry_fills=0", msg)

    def test_fee_drop_above_target_passes(self) -> None:
        cur = _make_cursor(
            (100, 70, 0.00032, 95, 0),
            [("grid_trading", 100, 70, 0.00032)],
        )

        status, msg = check_maker_fill_rate(cur)

        self.assertEqual(status, "PASS")
        self.assertIn("fee_drop=65.7%", msg)
        self.assertIn("maker_like=70/100", msg)
        self.assertIn("grid_trading", msg)

    def test_below_fee_drop_target_warns(self) -> None:
        status, msg = check_maker_fill_rate(
            _make_cursor((100, 10, 0.00052, 98, 0))
        )

        self.assertEqual(status, "WARN")
        self.assertIn("below G2-01", msg)
        self.assertIn("fee_drop=8.6%", msg)

    def test_small_sample_warns_even_when_fee_drop_good(self) -> None:
        status, msg = check_maker_fill_rate(_make_cursor((12, 12, 0.00020, 12, 0)))

        self.assertEqual(status, "WARN")
        self.assertIn("insufficient sample", msg)

    def test_query_error_warns(self) -> None:
        cur = _make_cursor((100, 70, 0.00032, 95, 0))
        cur.execute.side_effect = RuntimeError("boom")

        status, msg = check_maker_fill_rate(cur)

        self.assertEqual(status, "WARN")
        self.assertIn("query failed", msg)
        self.assertIn("RuntimeError", msg)

    def test_sql_uses_fills_orders_fee_and_liquidity_role(self) -> None:
        cur = _make_cursor((100, 70, 0.00032, 95, 0))

        check_maker_fill_rate(cur)

        sql_text = "\n".join(call.args[0] for call in cur.execute.call_args_list)
        self.assertIn("FROM trading.fills f", sql_text)
        self.assertIn("LEFT JOIN trading.orders o", sql_text)
        self.assertIn("f.fee_rate", sql_text)
        self.assertIn("f.liquidity_role", sql_text)
        self.assertIn("o.order_type", sql_text)
        self.assertIn("f.entry_context_id IS NULL", sql_text)
        self.assertIn("f.exit_reason IS NULL", sql_text)
        self.assertIn("f.order_id NOT LIKE 'oc_risk_", sql_text)


class TestGridLifecycleDrift(unittest.TestCase):
    def test_common_cohort_passes_even_when_global_symbol_mix_fails(self) -> None:
        cur = _make_grid_lifecycle_cursor(
            _LIFECYCLE_GLOBAL_FAIL_MIX,
            (3, 5, 7, 1.53, 2.98),
            _LOW_REENTRY_ROWS,
        )

        status, msg = check_grid_trading_lifecycle_drift(cur)

        self.assertEqual(status, "PASS")
        self.assertIn("global_ratio=0.29", msg)
        self.assertIn("cohort_ratio=1.53", msg)

    def test_common_cohort_ratio_below_fail_fails(self) -> None:
        cur = _make_grid_lifecycle_cursor(
            _LIFECYCLE_GLOBAL_FAIL_MIX,
            (2, 5, 7, 0.29, 0.29),
            _LOW_REENTRY_ROWS,
        )

        status, msg = check_grid_trading_lifecycle_drift(cur)

        self.assertEqual(status, "FAIL")
        self.assertIn("cohort_lifetime_ratio=0.29", msg)

    def test_global_lifetime_fail_with_insufficient_cohort_warns(self) -> None:
        cur = _make_grid_lifecycle_cursor(
            _LIFECYCLE_GLOBAL_FAIL_MIX,
            (0, 0, 0, None, None),
            _LOW_REENTRY_ROWS,
        )

        status, msg = check_grid_trading_lifecycle_drift(cur)

        self.assertEqual(status, "WARN")
        self.assertIn("cohort sample insufficient", msg)
        self.assertIn("global_ratio=0.29", msg)

    def test_insufficient_lifecycle_sample_warns_not_passes(self) -> None:
        cur = _make_grid_lifecycle_cursor(
            [("demo", 4, 14.5, 15.0, 1.0, 10.0)],
            (0, 0, 0, None, None),
            [],
        )

        status, msg = check_grid_trading_lifecycle_drift(cur)

        self.assertEqual(status, "WARN")
        self.assertIn("insufficient demo baseline", msg)

    def test_reentry_sql_uses_entry_only_fill_predicate(self) -> None:
        cur = _make_grid_lifecycle_cursor(
            _LIFECYCLE_GLOBAL_FAIL_MIX,
            (3, 5, 7, 1.53, 2.98),
            _LOW_REENTRY_ROWS,
        )

        check_grid_trading_lifecycle_drift(cur)

        sql_text = "\n".join(call.args[0] for call in cur.execute.call_args_list)
        self.assertIn("FROM trading.fills f", sql_text)
        self.assertIn("f.strategy_name = 'grid_trading'", sql_text)
        self.assertIn("f.entry_context_id IS NULL", sql_text)
        self.assertIn("f.exit_reason IS NULL", sql_text)
        self.assertIn("f.order_id NOT LIKE 'oc_risk_", sql_text)


if __name__ == "__main__":
    unittest.main()
