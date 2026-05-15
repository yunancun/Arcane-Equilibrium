#!/usr/bin/env python3
"""Unit tests for derived healthcheck `[Xb] pipeline_triangulation`.

The production check triangulates close fills, decision labels, and the
intent ledger. Scanner/opportunity shadow intents are intentionally high
volume, so `[Xb]` must use close-fill-linked intent contexts for the ratio
anchor while still surfacing raw scanner volume as a diagnostic.
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

from helper_scripts.db.passive_wait_healthcheck.checks_derived import (  # noqa: E402
    check_pipeline_triangulation,
)


def _cursor(
    labels_24h: int,
    intent_metrics: tuple[int, int, int, int, int],
    *,
    raw_labels_24h: int | None = None,
    rejected_governance_labels_24h: int = 0,
    close_linked_rejected_governance_24h: int = 0,
) -> MagicMock:
    """Build a psycopg2-like cursor with deterministic fetchone rows."""
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.rollback = MagicMock()
    cur.execute = MagicMock()
    cur.fetchone.side_effect = [
        (
            labels_24h,
            close_linked_rejected_governance_24h,
            labels_24h if raw_labels_24h is None else raw_labels_24h,
            rejected_governance_labels_24h,
        ),
        intent_metrics,
    ]
    return cur


class TestPipelineTriangulation(unittest.TestCase):
    def test_pass_uses_fill_linked_contexts_not_raw_scanner_intents(self) -> None:
        """Raw scanner intents can be huge while the filled context anchor is healthy."""
        cur = _cursor(
            labels_24h=23,
            intent_metrics=(
                103_628,  # raw_intents_24h
                103_613,  # scanner_opportunity_raw_24h
                23,       # close_fill_linked_intent_rows
                23,       # close_fill_linked_intent_contexts
                23,       # close_fill_contexts
            ),
        )

        status, msg = check_pipeline_triangulation(cur, close_fills_24h=24)

        self.assertEqual(status, "PASS", msg)
        self.assertIn("close_linked_labels=23", msg)
        self.assertIn("filled_intent_contexts=23", msg)
        self.assertIn("raw_intents=103628", msg)
        self.assertIn("scanner_opportunity_raw=103613", msg)
        self.assertIn("fills/intents=1.04", msg)

    def test_pass_excludes_rejected_governance_raw_labels(self) -> None:
        """Reject-path negative labels are diagnostic volume, not close-fill labels."""
        cur = _cursor(
            labels_24h=16,
            raw_labels_24h=111_992,
            rejected_governance_labels_24h=111_976,
            intent_metrics=(
                112_000,
                111_976,
                16,
                16,
                15,
            ),
        )

        status, msg = check_pipeline_triangulation(cur, close_fills_24h=15)

        self.assertEqual(status, "PASS", msg)
        self.assertIn("close_linked_labels=16", msg)
        self.assertIn("rejected_governance_raw=111976", msg)
        self.assertIn("fills/labels=0.94", msg)

    def test_fail_when_close_fills_have_no_linked_intent_contexts(self) -> None:
        """Filled trades with no matching intent context remain FAIL-grade."""
        cur = _cursor(
            labels_24h=23,
            intent_metrics=(
                103_000,
                102_000,
                0,
                0,
                23,
            ),
        )

        status, msg = check_pipeline_triangulation(cur, close_fills_24h=24)

        self.assertEqual(status, "FAIL", msg)
        self.assertIn("fills/intents=inf[FAIL]", msg)
        self.assertIn("severe pairwise divergence", msg)

    def test_warn_when_duplicate_fill_linked_intent_rows_drift(self) -> None:
        """Duplicate intent rows for the same filled contexts still warn."""
        cur = _cursor(
            labels_24h=23,
            intent_metrics=(
                120,
                0,
                92,
                23,
                23,
            ),
        )

        status, msg = check_pipeline_triangulation(cur, close_fills_24h=24)

        self.assertEqual(status, "WARN", msg)
        self.assertIn("intent_rows/contexts=4.00[WARN]", msg)
        self.assertIn("duplicate intent rows", msg)

    def test_small_close_fill_sample_skips_ratio_check(self) -> None:
        """Small samples preserve the existing PASS-skip behavior."""
        cur = _cursor(
            labels_24h=0,
            intent_metrics=(0, 0, 0, 0, 0),
        )

        status, msg = check_pipeline_triangulation(cur, close_fills_24h=4)

        self.assertEqual(status, "PASS", msg)
        self.assertIn("triangulation skipped", msg)
        cur.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
