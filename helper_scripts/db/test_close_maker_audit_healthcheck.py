#!/usr/bin/env python3
"""Unit tests for Phase 1b close-maker V094 healthchecks [70]-[74]."""

from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_HELPER_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)
_SRV_ROOT = os.path.dirname(_HELPER_SCRIPTS_DIR)
sys.path.insert(0, _SRV_ROOT)

from helper_scripts.db.passive_wait_healthcheck.checks_close_maker_audit import (  # noqa: E402
    REQUIRED_ENV,
    check_close_maker_fallback_null_ladder,
    check_close_maker_fill_rate,
    check_close_maker_rate_limit_backoff_coverage,
    check_close_maker_reject_samples,
    check_close_maker_zero_spine_lineage,
)


SCHEMA_READY = (True, True, True, True, True, True, True, True, True)
SCHEMA_MISSING_V094 = (True, True, True, True, True, True, True, False, False)


def _cur(
    fetchone_rows: list[tuple] | None = None,
    fetchall_rows: list[list[tuple]] | None = None,
) -> MagicMock:
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.rollback = MagicMock()
    cur.fetchone.side_effect = fetchone_rows or []
    cur.fetchall.side_effect = fetchall_rows or []
    return cur


class TestCloseMakerAuditHealthchecks(unittest.TestCase):
    """Close-maker audit healthcheck unit coverage."""

    def setUp(self) -> None:
        self._old_env = dict(os.environ)
        os.environ.pop(REQUIRED_ENV, None)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._old_env)

    def test_fill_rate_wilson_pass_warn_fail_classification(self) -> None:
        cases = [
            ("PASS", [("demo", 100, 70)], "PASS"),
            ("WARN", [("demo", 100, 55)], "WARN"),
            ("FAIL", [("demo", 100, 30)], "FAIL"),
            ("WARN", [("demo", 10, 9)], "NEUTRAL_LOW_SAMPLE"),
        ]
        for expected_status, main_rows, expected_msg in cases:
            with self.subTest(expected_status=expected_status, main_rows=main_rows):
                cur = _cur(
                    fetchone_rows=[SCHEMA_READY],
                    fetchall_rows=[
                        main_rows,
                        [],
                        [("demo", "grid_trading", "BTCUSDT", 42, 30, 12)],
                    ],
                )

                status, msg = check_close_maker_fill_rate(cur)

                self.assertEqual(status, expected_status)
                self.assertIn(expected_msg, msg)
                self.assertIn("ac18_fallback_to_taker_rate=", msg)
                self.assertIn("stratified_weak_cells=demo/grid_trading/BTCUSDT", msg)
                self.assertIn("wilson95=", msg)

    def test_fill_rate_includes_ac18_fallback_to_taker_wilson_subcheck(self) -> None:
        cases = [
            ("PASS", [("demo", 100, 96)], "PASS"),
            ("WARN", [("demo", 100, 92)], "WARN"),
            ("FAIL", [("demo", 100, 88)], "FAIL"),
        ]
        for expected_status, ac18_rows, expected_msg in cases:
            with self.subTest(ac18_rows=ac18_rows):
                cur = _cur(
                    fetchone_rows=[SCHEMA_READY],
                    fetchall_rows=[
                        [("demo", 100, 80)],
                        ac18_rows,
                        [("demo", "grid_trading", "BTCUSDT", 42, 30, 12)],
                    ],
                )

                status, msg = check_close_maker_fill_rate(cur)

                self.assertEqual(status, expected_status)
                self.assertIn("ac18_fallback_to_taker_rate=demo:", msg)
                self.assertIn(expected_msg, msg)

    def test_zero_spine_lineage_guard(self) -> None:
        cases = [
            ("PASS", 0, "spine-free"),
            ("WARN", 3, "small close spine leakage"),
            ("FAIL", 6, "invariant broken"),
        ]
        for expected_status, spine_rows, expected_msg in cases:
            with self.subTest(spine_rows=spine_rows):
                cur = _cur(
                    fetchone_rows=[
                        SCHEMA_READY,
                        (True,),
                        (12,),
                        (spine_rows,),
                    ]
                )

                status, msg = check_close_maker_zero_spine_lineage(cur)

                self.assertEqual(status, expected_status)
                self.assertIn(expected_msg, msg)
                self.assertIn(f"spine_close_rows_24h={spine_rows}", msg)

    def test_fallback_null_ladder_and_reject_samples(self) -> None:
        pass_cur = _cur(
            fetchone_rows=[SCHEMA_READY, (20, 0, 0, 20, 20, 0)],
            fetchall_rows=[
                [("demo", "grid_trading", "BTCUSDT", 2, 1, 0, 3)],
            ],
        )
        status, msg = check_close_maker_fallback_null_ladder(pass_cur)
        self.assertEqual(status, "PASS")
        self.assertIn("completeness_ratio=1.00000", msg)
        self.assertIn("reject_samples_by_cell=demo/grid_trading/BTCUSDT", msg)

        fail_cur = _cur(
            fetchone_rows=[SCHEMA_READY, (20, 1, 0, 20, 20, 0)],
            fetchall_rows=[[]],
        )
        status, msg = check_close_maker_fallback_null_ladder(fail_cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("false_attempt_reason_n=1", msg)
        self.assertIn("NULL ladder violation", msg)

    def test_rate_limit_backoff_scope_and_global_pause_coverage(self) -> None:
        cases = [
            ("PASS", (0, 20, 0, 0, 0), "healthy"),
            ("WARN", (1, 20, 0, 0, 0), "pressure elevated"),
            ("FAIL", (0, 2, 1, 0, 1), "scope coverage broken"),
            ("FAIL", (6, 2, 0, 0, 0), "exceeds fail threshold"),
        ]
        for expected_status, row, expected_msg in cases:
            with self.subTest(row=row):
                cur = _cur(fetchone_rows=[SCHEMA_READY, row])

                status, msg = check_close_maker_rate_limit_backoff_coverage(cur)

                self.assertEqual(status, expected_status)
                self.assertIn(expected_msg, msg)

    def test_reject_samples_healthcheck(self) -> None:
        pass_cur = _cur(fetchone_rows=[SCHEMA_READY], fetchall_rows=[[("demo", 20, 1, 1)]])
        status, msg = check_close_maker_reject_samples(pass_cur)
        self.assertEqual(status, "PASS")
        self.assertIn("reject sample coverage present", msg)

        fail_cur = _cur(fetchone_rows=[SCHEMA_READY], fetchall_rows=[[("demo", 20, 0, 1)]])
        status, msg = check_close_maker_reject_samples(fail_cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("missing PostOnly or max-pending reject samples", msg)

        warn_cur = _cur(fetchone_rows=[SCHEMA_READY], fetchall_rows=[[]])
        status, msg = check_close_maker_reject_samples(warn_cur)
        self.assertEqual(status, "WARN")
        self.assertIn("NEUTRAL_LOW_SAMPLE", msg)

    def test_missing_v094_schema_warns_until_expected_then_fails(self) -> None:
        warn_cur = _cur(fetchone_rows=[SCHEMA_MISSING_V094, (False,)])
        status, msg = check_close_maker_fill_rate(warn_cur)
        self.assertEqual(status, "WARN")
        self.assertIn("NEEDS_SCHEMA", msg)

        fail_cur = _cur(fetchone_rows=[SCHEMA_MISSING_V094, (True,), (True,)])
        status, msg = check_close_maker_fill_rate(fail_cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("V094_EXPECTED_SCHEMA_MISSING", msg)

    def test_runner_registration_has_no_duplicate_ids_or_labels(self) -> None:
        runner_path = (
            Path(_SRV_ROOT)
            / "helper_scripts"
            / "db"
            / "passive_wait_healthcheck"
            / "runner.py"
        )
        text = runner_path.read_text(encoding="utf-8")
        full_run_text = text.split("results: list[tuple[str, str, str]] = []")[-1]
        registrations = re.findall(r'results\.append\(\("(\[[^\]]+\]) ([^"]+)"', full_run_text)

        ids = [item[0] for item in registrations]
        labels = [item[1] for item in registrations]
        self.assertEqual(len(ids), len(set(ids)), "duplicate healthcheck id registration")
        self.assertEqual(len(labels), len(set(labels)), "duplicate healthcheck label registration")

        mapping = dict(registrations)
        self.assertEqual(mapping["[70]"], "close_maker_fill_rate")
        self.assertEqual(mapping["[71]"], "close_maker_zero_spine_lineage")
        self.assertEqual(mapping["[72]"], "close_maker_fallback_null_ladder")
        self.assertEqual(mapping["[73]"], "close_maker_rate_limit_backoff_coverage")
        self.assertEqual(mapping["[74]"], "close_maker_reject_samples")
        self.assertNotEqual(mapping["[64]"], "close_maker_rate_limit_backoff_coverage")
        self.assertNotEqual(mapping["[65]"], "close_maker_fallback_null_ladder")


if __name__ == "__main__":
    unittest.main()
