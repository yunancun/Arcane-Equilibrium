#!/usr/bin/env python3
"""Tests for blocked_symbols_7d_counterfactual.py."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

_THIS_DIR = Path(os.path.abspath(__file__)).parent
_SRV_ROOT = _THIS_DIR.parents[1]
sys.path.insert(0, str(_SRV_ROOT))

from helper_scripts.db.audit.blocked_symbols_7d_counterfactual import (  # noqa: E402
    AuditRow,
    iter_cells,
    load_registry,
    render_markdown,
    _values_sql,
)


class TestBlockedSymbolsCounterfactual(unittest.TestCase):
    def test_registry_expands_to_current_frozen_cells(self) -> None:
        cells = iter_cells(load_registry())

        self.assertEqual(len(cells), 21)
        self.assertIn(("grid_trading", "BILLUSDT"), {(c.strategy, c.symbol) for c in cells})
        self.assertIn(("ma_crossover", "LABUSDT"), {(c.strategy, c.symbol) for c in cells})

    def test_values_sql_uses_only_placeholders_for_cells(self) -> None:
        cells = iter_cells(load_registry())[:2]
        sql, params = _values_sql(cells)

        self.assertEqual(sql, "(%s, %s), (%s, %s)")
        self.assertEqual(len(params), 4)

    def test_markdown_surfaces_missing_rejected_outcome_power(self) -> None:
        report = render_markdown(
            [
                AuditRow(
                    strategy="ma_crossover",
                    symbol="LABUSDT",
                    fills=16,
                    entries=16,
                    exits=0,
                    net_pnl_usdt=-18.2,
                    gross_pnl_usdt=-17.6,
                    fees_usdt=0.6,
                    rejected_n=2772,
                    rejected_outcome_n=0,
                    avg_outcome_24h=None,
                    first_seen="",
                    last_seen="",
                )
            ],
            days=7,
        )

        self.assertIn("no_rejected_outcome_labels", report)
        self.assertIn("New blocked cells need an RFC", report)


if __name__ == "__main__":
    unittest.main()
