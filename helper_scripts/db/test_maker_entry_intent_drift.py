#!/usr/bin/env python3
"""Tests for [32] maker_entry_intent_drift.
[32] maker_entry_intent_drift 單元測試。
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_HELPER_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)
_SRV_ROOT = os.path.dirname(_HELPER_SCRIPTS_DIR)
sys.path.insert(0, _SRV_ROOT)

from helper_scripts.db.passive_wait_healthcheck.checks_execution import (  # noqa: E402
    check_intent_signal_attribution,
    check_maker_entry_intent_drift,
)


def _make_cursor(rows: list[tuple[str, str, str, int]]) -> MagicMock:
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.rollback = MagicMock()
    cur.fetchall.return_value = rows
    return cur


class TestMakerEntryIntentDrift(unittest.TestCase):
    def _run_with_toml(
        self,
        toml_text: str,
        rows: list[tuple[str, str, str, int]],
        live_toml_text: str | None = "",
    ) -> tuple[str, str]:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / "settings"
            settings.mkdir(parents=True)
            (settings / "strategy_params_demo.toml").write_text(
                toml_text, encoding="utf-8"
            )
            if live_toml_text is not None:
                (settings / "strategy_params_live.toml").write_text(
                    live_toml_text, encoding="utf-8"
                )
            with patch.dict(os.environ, {"OPENCLAW_BASE_DIR": tmp}, clear=False):
                return check_maker_entry_intent_drift(_make_cursor(rows))

    def test_market_intent_for_maker_strategy_fails(self) -> None:
        toml = """
[grid_trading]
active = true
use_maker_entry = true

[ma_crossover]
active = true
use_maker_entry = true
"""
        status, msg = self._run_with_toml(toml, [("demo", "grid_trading", "market", 3)])
        self.assertEqual(status, "FAIL")
        self.assertIn("demo/grid_trading", msg)
        self.assertIn("market=3", msg)

    def test_live_market_intent_for_maker_strategy_fails(self) -> None:
        live_toml = """
[grid_trading]
active = true
use_maker_entry = true
"""
        status, msg = self._run_with_toml(
            "",
            [("live", "grid_trading", "market", 6)],
            live_toml_text=live_toml,
        )
        self.assertEqual(status, "FAIL")
        self.assertIn("live/grid_trading", msg)
        self.assertIn("market=6", msg)

    def test_limit_intents_pass(self) -> None:
        toml = """
[grid_trading]
active = true
use_maker_entry = true
"""
        status, msg = self._run_with_toml(toml, [("demo", "grid_trading", "limit", 5)])
        self.assertEqual(status, "PASS")
        self.assertIn("limit=5", msg)

    def test_no_recent_intents_passes(self) -> None:
        toml = """
[grid_trading]
active = true
use_maker_entry = true
"""
        status, msg = self._run_with_toml(toml, [])
        self.assertEqual(status, "PASS")
        self.assertIn("no entry intents", msg)

    def test_fresh_restart_limits_query_window(self) -> None:
        toml = """
[grid_trading]
active = true
use_maker_entry = true
"""
        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / "settings"
            settings.mkdir(parents=True)
            (settings / "strategy_params_demo.toml").write_text(
                toml, encoding="utf-8"
            )
            (settings / "strategy_params_live.toml").write_text("", encoding="utf-8")
            cur = _make_cursor([])
            with patch.dict(os.environ, {"OPENCLAW_BASE_DIR": tmp}, clear=False):
                with patch(
                    "helper_scripts.db.passive_wait_healthcheck.checks_execution."
                    "_engine_process_age_minutes",
                    return_value=(5.0, "ok"),
                ):
                    status, msg = check_maker_entry_intent_drift(cur)

        self.assertEqual(status, "PASS")
        self.assertIn("5.0m post-restart", msg)
        self.assertEqual(cur.execute.call_args.args[1][-1], 5.0)

    def test_missing_toml_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"OPENCLAW_BASE_DIR": tmp}, clear=False):
                status, msg = check_maker_entry_intent_drift(_make_cursor([]))
        self.assertEqual(status, "WARN")
        self.assertIn("TOML read unavailable", msg)


class TestIntentSignalAttribution(unittest.TestCase):
    def _cursor(self, attribution_row: tuple[int, int, int, int]) -> MagicMock:
        cur = MagicMock()
        cur.connection = MagicMock()
        cur.connection.rollback = MagicMock()
        cur.fetchone.side_effect = [(True, True), attribution_row]
        return cur

    def test_linked_recent_intents_pass(self) -> None:
        status, msg = check_intent_signal_attribution(self._cursor((3, 0, 0, 0)))
        self.assertEqual(status, "PASS")
        self.assertIn("attribution chain linked", msg)

    def test_empty_signal_id_fails(self) -> None:
        status, msg = check_intent_signal_attribution(self._cursor((3, 1, 0, 0)))
        self.assertEqual(status, "FAIL")
        self.assertIn("empty_signal_id=1", msg)

    def test_no_recent_exchange_intents_passes(self) -> None:
        status, msg = check_intent_signal_attribution(self._cursor((0, 0, 0, 0)))
        self.assertEqual(status, "PASS")
        self.assertIn("no recent exchange intents", msg)


if __name__ == "__main__":
    unittest.main()
