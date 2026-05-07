#!/usr/bin/env python3
"""Unit tests for scanner opportunity shadow healthcheck `[51]`.
Scanner opportunity shadow healthcheck `[51]` 單元測試。

The check is intentionally observational: it verifies row-proof coverage from
scanner snapshots into intents and MLDE labels, then evaluates calibration once
enough realized outcomes exist. It must not behave like a trading gate.
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

from helper_scripts.db.passive_wait_healthcheck.checks_scanner_market import (  # noqa: E402
    OPPORTUNITY_SHADOW_MIN_LABEL_SAMPLE,
    OPPORTUNITY_SHADOW_MIN_POSITIVE_LCB_SAMPLE,
    OPPORTUNITY_SHADOW_MIN_REJECTED_SAMPLE,
    check_scanner_opportunity_shadow_acceptance,
)


_TABLES_OK = [(True,), (True,), (True,), (True,), (True,)]


def _build_cur(
    fetchone_rows: list[tuple],
    fetchall_rows: list[tuple] | list[list[tuple]] | None = None,
) -> MagicMock:
    """Build a psycopg2-like cursor for `[51]` tests."""
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.rollback = MagicMock()
    cur.fetchone.side_effect = fetchone_rows
    if fetchall_rows is None:
        cur.fetchall.return_value = []
    elif fetchall_rows and isinstance(fetchall_rows[0], list):
        cur.fetchall.side_effect = fetchall_rows
    else:
        cur.fetchall.return_value = fetchall_rows
    return cur


class TestScannerOpportunityShadowAcceptance(unittest.TestCase):
    """Verdict paths for coverage, low-label warmup, and calibration failure."""

    def test_warn_when_required_table_missing(self) -> None:
        cur = _build_cur([(False,), (True,), (True,), (True,), (True,)])
        status, msg = check_scanner_opportunity_shadow_acceptance(cur)
        self.assertEqual(status, "WARN")
        self.assertIn("trading.scanner_snapshots missing", msg)

    def test_fail_when_snapshot_opportunity_coverage_regresses(self) -> None:
        cur = _build_cur(
            [
                *_TABLES_OK,
                (100, 80, 3),  # route_n, opportunity_n, scan_n
                (4, 4),  # scanner intents, opportunity intents
                (OPPORTUNITY_SHADOW_MIN_LABEL_SAMPLE, 2, 0, -10.0, None, None, -10.0, None),
                (0, 0, None, None, None),
            ]
        )
        status, msg = check_scanner_opportunity_shadow_acceptance(cur)
        self.assertEqual(status, "FAIL", msg)
        self.assertIn("snapshot opportunity coverage below", msg)
        self.assertIn("80/100", msg)

    def test_fail_when_intent_opportunity_coverage_regresses(self) -> None:
        cur = _build_cur(
            [
                *_TABLES_OK,
                (100, 100, 3),
                (10, 8),  # scanner intents, opportunity intents
                (OPPORTUNITY_SHADOW_MIN_LABEL_SAMPLE, 2, 0, -5.0, None, None, -5.0, None),
                (0, 0, None, None, None),
            ]
        )
        status, msg = check_scanner_opportunity_shadow_acceptance(cur)
        self.assertEqual(status, "FAIL", msg)
        self.assertIn("intent opportunity coverage below", msg)
        self.assertIn("8/10", msg)

    def test_warn_low_label_sample_is_not_false_fail(self) -> None:
        cur = _build_cur(
            [
                *_TABLES_OK,
                (340, 340, 6),
                (4, 4),
                (OPPORTUNITY_SHADOW_MIN_LABEL_SAMPLE - 1, 2, 0, -31.8, 27.9, None, -55.7, 0.22),
                (0, 0, None, None, None),
            ]
        )
        status, msg = check_scanner_opportunity_shadow_acceptance(cur)
        self.assertEqual(status, "WARN", msg)
        self.assertIn("insufficient labeled outcomes", msg)
        self.assertIn("340/340", msg)

    def test_pass_when_shadow_coverage_and_calibration_are_healthy(self) -> None:
        cur = _build_cur(
            [
                *_TABLES_OK,
                (200, 200, 4),
                (12, 12),
                (30, 14, 14, 6.5, 18.0, 18.0, -2.0, 0.42),
                (0, 0, None, None, None),
            ]
        )
        status, msg = check_scanner_opportunity_shadow_acceptance(cur)
        self.assertEqual(status, "PASS", msg)
        self.assertIn("opportunity shadow contract healthy", msg)
        self.assertIn("positive_avg=18.00bps", msg)

    def test_fail_when_positive_lcb_bucket_is_realized_negative(self) -> None:
        cur = _build_cur(
            [
                *_TABLES_OK,
                (200, 200, 4),
                (12, 12),
                (
                    40,
                    OPPORTUNITY_SHADOW_MIN_POSITIVE_LCB_SAMPLE,
                    OPPORTUNITY_SHADOW_MIN_POSITIVE_LCB_SAMPLE,
                    -12.0,
                    -8.0,
                    -8.0,
                    -15.0,
                    -0.30,
                ),
                (0, 0, None, None, None),
            ],
            [
                (
                    "grid_trading",
                    "ETHUSDT",
                    OPPORTUNITY_SHADOW_MIN_POSITIVE_LCB_SAMPLE,
                    -8.0,
                    12.5,
                )
            ],
        )
        status, msg = check_scanner_opportunity_shadow_acceptance(cur)
        self.assertEqual(status, "FAIL", msg)
        self.assertIn("positive opportunity LCB realized negative", msg)
        self.assertIn("grid_trading/ETHUSDT", msg)

    def test_warn_when_only_exploration_positive_lcb_is_negative(self) -> None:
        cur = _build_cur(
            [
                *_TABLES_OK,
                (200, 200, 4),
                (12, 12),
                (
                    40,
                    OPPORTUNITY_SHADOW_MIN_POSITIVE_LCB_SAMPLE,
                    0,
                    -12.0,
                    -8.0,
                    None,
                    -15.0,
                    -0.30,
                ),
                (0, 0, None, None, None),
            ],
            [],
        )
        status, msg = check_scanner_opportunity_shadow_acceptance(cur)
        self.assertEqual(status, "WARN", msg)
        self.assertIn("exploration positive LCB bucket is negative", msg)

    def test_warn_when_positive_lcb_rejects_were_profitable_counterfactuals(self) -> None:
        cur = _build_cur(
            [
                *_TABLES_OK,
                (200, 200, 4),
                (12, 12),
                (30, 14, 14, 6.5, 18.0, 18.0, -2.0, 0.42),
                (8, 8, 11.5, 11.5, 0.51),
            ],
            [
                [],
                [
                    (
                        "grid_trading",
                        "ETHUSDT",
                        "opportunity_positive",
                        OPPORTUNITY_SHADOW_MIN_REJECTED_SAMPLE,
                        12.5,
                        8.0,
                    )
                ],
            ],
        )
        status, msg = check_scanner_opportunity_shadow_acceptance(cur)
        self.assertEqual(status, "WARN", msg)
        self.assertIn("positive scanner LCB was rejected", msg)
        self.assertIn("grid_trading/ETHUSDT", msg)
        self.assertIn("hint=opportunity_positive", msg)

    def test_sql_contract_reads_shadow_paths_without_mutation(self) -> None:
        cur = _build_cur(
            [
                *_TABLES_OK,
                (10, 10, 1),
                (0, 0),
                (0, 0, 0, None, None, None, None, None),
                (0, 0, None, None, None),
            ]
        )
        check_scanner_opportunity_shadow_acceptance(cur)
        sql_text = "\n".join(str(call.args[0]) for call in cur.execute.call_args_list)
        self.assertIn("strategy_judgments", sql_text)
        self.assertIn("jsonb_typeof(details->'scanner') = 'object'", sql_text)
        self.assertIn("details #> '{scanner,opportunity}'", sql_text)
        self.assertIn("metadata #>> '{scanner,opportunity,opportunity_lcb_bps}'", sql_text)
        self.assertIn("trading.risk_verdicts", sql_text)
        self.assertIn("trading.decision_outcomes", sql_text)
        self.assertIn(
            "details #> '{scanner,opportunity,components,expected_execution_cost_bps}'",
            sql_text,
        )
        self.assertNotIn("INSERT ", sql_text.upper())
        self.assertNotIn("UPDATE ", sql_text.upper())
        self.assertNotIn("DELETE ", sql_text.upper())


if __name__ == "__main__":
    unittest.main()
