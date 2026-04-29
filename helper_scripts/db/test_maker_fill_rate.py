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


if __name__ == "__main__":
    unittest.main()
