#!/usr/bin/env python3
"""Unit tests for passive healthcheck `[4] phys_lock_runtime`."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_HELPER_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)
_SRV_ROOT = os.path.dirname(_HELPER_SCRIPTS_DIR)
sys.path.insert(0, _SRV_ROOT)

from helper_scripts.db.passive_wait_healthcheck.checks_ipc_edge import (  # noqa: E402
    check_phys_lock_runtime,
)


def _cursor(*rows: tuple[int, int, object | None]) -> MagicMock:
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.rollback = MagicMock()
    cur.execute = MagicMock()
    cur.fetchone.side_effect = rows
    return cur


class TestPhysLockRuntime(unittest.TestCase):
    def test_pass_uses_exit_features_primary_signal(self) -> None:
        cur = _cursor((2, 5, datetime(2026, 5, 14, 21, 3, tzinfo=timezone.utc)))

        status, msg = check_phys_lock_runtime(cur)

        self.assertEqual(status, "PASS", msg)
        self.assertIn("exit_features phys_lock 24h=2", msg)
        self.assertIn("7d=5", msg)
        self.assertEqual(cur.execute.call_count, 1)

    def test_warn_when_exit_features_has_7d_activity_but_24h_quiet(self) -> None:
        cur = _cursor((0, 1, datetime(2026, 5, 14, 21, 3, tzinfo=timezone.utc)))

        status, msg = check_phys_lock_runtime(cur)

        self.assertEqual(status, "WARN", msg)
        self.assertIn("exit_features phys_lock 24h=0", msg)
        self.assertIn("7d=1", msg)

    def test_passes_via_legacy_fills_strategy_name_fallback(self) -> None:
        cur = _cursor(
            (0, 0, None),
            (1, 3, datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc)),
        )

        status, msg = check_phys_lock_runtime(cur)

        self.assertEqual(status, "PASS", msg)
        self.assertIn("exit_features phys_lock 7d=0", msg)
        self.assertIn("legacy fills.strategy_name phys_lock 24h=1", msg)
        self.assertIn("legacy fallback active", msg)

    def test_fails_only_when_primary_and_legacy_are_both_empty(self) -> None:
        cur = _cursor((0, 0, None), (0, 0, None))

        status, msg = check_phys_lock_runtime(cur)

        self.assertEqual(status, "FAIL", msg)
        self.assertIn("exit_features phys_lock 7d=0", msg)
        self.assertIn("legacy fills.strategy_name phys_lock 24h=0", msg)


if __name__ == "__main__":
    unittest.main()
