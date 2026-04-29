#!/usr/bin/env python3
"""Tests for MLDE passive healthchecks."""

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
    check_mlde_demo_applier,
    check_mlde_learning_data_contract,
    check_mlde_shadow_recommendations,
)


def _cursor(fetches: list[tuple]) -> MagicMock:
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.rollback = MagicMock()
    cur.fetchone.side_effect = fetches
    return cur


class TestMldeLearningDataContract(unittest.TestCase):
    def test_passes_when_rows_are_linucb_ready(self) -> None:
        status, msg = check_mlde_learning_data_contract(
            _cursor([(True,), (5, 5, 5, 0, 0), (2, 2, 0)])
        )
        self.assertEqual(status, "PASS")
        self.assertIn("linucb_ready=5", msg)

    def test_missing_view_fails(self) -> None:
        status, msg = check_mlde_learning_data_contract(_cursor([(False,)]))
        self.assertEqual(status, "FAIL")
        self.assertIn("V031 not applied", msg)

    def test_zero_rows_warns_during_first_window(self) -> None:
        status, msg = check_mlde_learning_data_contract(
            _cursor([(True,), (0, 0, 0, 0, 0), (0, 0, 0)])
        )
        self.assertEqual(status, "WARN")
        self.assertIn("no post-V031 MLDE training rows", msg)

    def test_legacy_missing_ids_do_not_fail_after_recent_window_is_clean(self) -> None:
        status, msg = check_mlde_learning_data_contract(
            _cursor([(True,), (100, 30, 8, 70, 4), (5, 5, 0)])
        )
        self.assertEqual(status, "PASS")
        self.assertIn("missing_ids=70", msg)
        self.assertIn("recent_30m total=5", msg)

    def test_recent_missing_ids_fail(self) -> None:
        status, msg = check_mlde_learning_data_contract(
            _cursor([(True,), (100, 30, 8, 70, 4), (5, 3, 2)])
        )
        self.assertEqual(status, "FAIL")
        self.assertIn("recent attribution ids missing", msg)


class TestMldeShadowRecommendations(unittest.TestCase):
    def test_passes_with_recent_advisory_rows(self) -> None:
        status, msg = check_mlde_shadow_recommendations(
            _cursor([(True,), (3, 2, 0)])
        )
        self.assertEqual(status, "PASS")
        self.assertIn("advisory-only boundary intact", msg)

    def test_live_applied_without_lease_fails(self) -> None:
        status, msg = check_mlde_shadow_recommendations(
            _cursor([(True,), (3, 2, 1)])
        )
        self.assertEqual(status, "FAIL")
        self.assertIn("lacks Decision Lease", msg)

    def test_no_recent_rows_warns(self) -> None:
        status, msg = check_mlde_shadow_recommendations(
            _cursor([(True,), (0, 0, 0)])
        )
        self.assertEqual(status, "WARN")
        self.assertIn("no recent MLDE shadow", msg)


class TestMldeDemoApplier(unittest.TestCase):
    def test_missing_table_fails(self) -> None:
        status, msg = check_mlde_demo_applier(_cursor([(False,)]))
        self.assertEqual(status, "FAIL")
        self.assertIn("V032 not applied", msg)

    def test_passes_with_audited_demo_application(self) -> None:
        status, msg = check_mlde_demo_applier(
            _cursor([(True,), (2, 1, 1, 0, 0)])
        )
        self.assertEqual(status, "PASS")
        self.assertIn("demo autonomy audited", msg)

    def test_live_application_without_lease_fails(self) -> None:
        status, msg = check_mlde_demo_applier(
            _cursor([(True,), (1, 0, 0, 0, 1)])
        )
        self.assertEqual(status, "FAIL")
        self.assertIn("lacks Decision Lease", msg)


if __name__ == "__main__":
    unittest.main()
