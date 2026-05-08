#!/usr/bin/env python3
"""Tests for [40] realized edge acceptance healthcheck."""

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
    check_realized_edge_acceptance,
)


def _cursor(
    *,
    aggregate_row: tuple[int, int, float],
    per_engine_bad_rows: list[tuple[str, str, str, int, float]] | None = None,
    combined_bad_rows: list[tuple[str, str, str, int, float]] | None = None,
    maker_row: tuple[int, int, float] = (60, 45, 0.00030),
) -> MagicMock:
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.rollback = MagicMock()
    cur.fetchone.side_effect = [
        (True,),
        aggregate_row,
        maker_row,
    ]
    cur.fetchall.side_effect = [
        per_engine_bad_rows or [],
        combined_bad_rows or [],
    ]
    return cur


class TestRealizedEdgeAcceptance(unittest.TestCase):
    def test_combined_demo_livedemo_negative_cell_fails(self) -> None:
        status, msg = check_realized_edge_acceptance(
            _cursor(
                aggregate_row=(32, 10, -51.57),
                combined_bad_rows=[
                    ("demo+live_demo", "grid_trading", "LABUSDT", 17, -78.76)
                ],
            )
        )

        self.assertEqual(status, "FAIL")
        self.assertIn("negative cells still active across demo/live_demo", msg)
        self.assertIn("demo+live_demo/grid_trading/LABUSDT n=17 avg=-78.76bps", msg)

    def test_overall_negative_warns_without_bad_cell(self) -> None:
        status, msg = check_realized_edge_acceptance(
            _cursor(aggregate_row=(32, 10, -3.0))
        )

        self.assertEqual(status, "WARN")
        self.assertIn("avg_net -3.00bps <= target", msg)

    def test_acceptance_passes_when_edge_and_execution_meet_targets(self) -> None:
        status, msg = check_realized_edge_acceptance(
            _cursor(aggregate_row=(40, 25, 8.0), maker_row=(60, 55, 0.00025))
        )

        self.assertEqual(status, "PASS")
        self.assertIn("acceptance guard within target", msg)


if __name__ == "__main__":
    unittest.main()
