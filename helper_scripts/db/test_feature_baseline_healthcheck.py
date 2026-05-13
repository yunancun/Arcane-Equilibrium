#!/usr/bin/env python3
"""Unit tests for passive_wait_healthcheck [67] feature baseline readiness."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_HELPER_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)
_SRV_ROOT = os.path.dirname(_HELPER_SCRIPTS_DIR)
sys.path.insert(0, _SRV_ROOT)

from helper_scripts.db.passive_wait_healthcheck.checks_feature_baseline import (  # noqa: E402
    FEATURE_DIM,
    EXPECTED_FEATURE_NAMES,
    check_67_feature_baseline_readiness,
)


def _cur(
    fetchone_rows: list[tuple],
    fetchall_rows: list[list[tuple]] | None = None,
) -> MagicMock:
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.rollback = MagicMock()
    cur.fetchone.side_effect = fetchone_rows
    cur.fetchall.side_effect = fetchall_rows or []
    return cur


class TestFeatureBaselineReadiness(unittest.TestCase):
    def test_feature_name_contract_has_34_names(self) -> None:
        self.assertEqual(len(EXPECTED_FEATURE_NAMES), FEATURE_DIM)
        self.assertEqual(len(set(EXPECTED_FEATURE_NAMES)), FEATURE_DIM)

    def test_pass_active_rows_and_online_vector_dim_34(self) -> None:
        cur = _cur(
            fetchone_rows=[
                (True, True),      # tables exist
                (68, 2, 34, 0),    # active rows, symbols, feature names, invalid rows
                (43, 34, 34, 0),   # online rows, min dim, max dim, bad dim rows
            ],
            fetchall_rows=[
                [],  # invalid feature names
                [],  # partial symbols
            ],
        )

        status, msg = check_67_feature_baseline_readiness(cur)

        self.assertEqual(status, "PASS", msg)
        self.assertIn("active_rows=68", msg)
        self.assertIn("feature_names=34/34", msg)
        self.assertIn("vector_dim_min=34", msg)

    def test_fail_when_active_baselines_zero(self) -> None:
        cur = _cur(
            fetchone_rows=[
                (True, True),
                (0, 0, 0, 0),
            ],
        )

        status, msg = check_67_feature_baseline_readiness(cur)

        self.assertEqual(status, "FAIL")
        self.assertIn("active feature_baselines=0", msg)
        self.assertIn("drift_events remains gated", msg)

    def test_fail_on_invalid_feature_name(self) -> None:
        cur = _cur(
            fetchone_rows=[
                (True, True),
                (68, 2, 35, 1),
            ],
            fetchall_rows=[
                [("legacy_17d_feature", 1)],
            ],
        )

        status, msg = check_67_feature_baseline_readiness(cur)

        self.assertEqual(status, "FAIL")
        self.assertIn("invalid active baseline feature names", msg)
        self.assertIn("legacy_17d_feature=1", msg)

    def test_fail_on_partial_symbol_contract(self) -> None:
        cur = _cur(
            fetchone_rows=[
                (True, True),
                (67, 2, 34, 0),
            ],
            fetchall_rows=[
                [],
                [("BTCUSDT", 33)],
            ],
        )

        status, msg = check_67_feature_baseline_readiness(cur)

        self.assertEqual(status, "FAIL")
        self.assertIn("partial active feature_baselines per symbol", msg)
        self.assertIn("BTCUSDT=33/34", msg)

    def test_fail_on_online_vector_dim_drift(self) -> None:
        cur = _cur(
            fetchone_rows=[
                (True, True),
                (68, 2, 34, 0),
                (43, 17, 34, 2),
            ],
            fetchall_rows=[
                [],
                [],
            ],
        )

        status, msg = check_67_feature_baseline_readiness(cur)

        self.assertEqual(status, "FAIL")
        self.assertIn("bad_dim_rows=2", msg)
        self.assertIn("expected every current vector to be 34-dim", msg)


if __name__ == "__main__":
    unittest.main()
