#!/usr/bin/env python3
"""Tests for [14] exit_features accumulation healthcheck."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_HELPER_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)
_SRV_ROOT = os.path.dirname(_HELPER_SCRIPTS_DIR)
sys.path.insert(0, _SRV_ROOT)

from helper_scripts.db.passive_wait_healthcheck.checks_strategy import (  # noqa: E402
    check_exit_features_accumulation_rate,
)


def _cursor(
    *,
    this_week: int,
    last_week: int,
    per_strategy_rows: list[tuple[str, int]] | None = None,
    flow_row: tuple[int, int, int, int, int, int] | None = None,
) -> MagicMock:
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.rollback = MagicMock()
    cur.fetchone.side_effect = [
        (True,),
        (this_week,),
        (last_week,),
        flow_row or (0, 0, 0, 0, 0, 0),
    ]
    cur.fetchall.return_value = per_strategy_rows or []
    return cur


class TestExitFeaturesAccumulationRate(unittest.TestCase):
    def test_severe_decay_with_rejected_only_flow_names_gate_suppression(self) -> None:
        status, msg = check_exit_features_accumulation_rate(
            _cursor(
                this_week=277,
                last_week=1598,
                per_strategy_rows=[("grid_trading", 154), ("ma_crossover", 80)],
                flow_row=(4831, 0, 0, 212, 0, 212),
            )
        )

        self.assertEqual(status, "WARN")
        self.assertIn("risk/cost gates rejected all attempts", msg)
        self.assertIn("writer health is not implicated", msg)
        self.assertIn("flow_context: intents_1h=4831", msg)

    def test_severe_decay_without_gate_context_keeps_writer_diagnostic(self) -> None:
        status, msg = check_exit_features_accumulation_rate(
            _cursor(
                this_week=10,
                last_week=100,
                per_strategy_rows=[("grid_trading", 10)],
                flow_row=(5, 2, 1, 4, 2, 2),
            )
        )

        self.assertEqual(status, "WARN")
        self.assertIn("investigate fill rate + writer health", msg)
        self.assertIn("flow_context: intents_1h=5", msg)

    def test_stable_accumulation_passes(self) -> None:
        status, msg = check_exit_features_accumulation_rate(
            _cursor(
                this_week=80,
                last_week=100,
                per_strategy_rows=[("grid_trading", 80)],
            )
        )

        self.assertEqual(status, "PASS")
        self.assertIn("accumulation healthy", msg)


if __name__ == "__main__":
    unittest.main()
