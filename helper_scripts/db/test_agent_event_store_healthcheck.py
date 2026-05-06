#!/usr/bin/env python3
"""Unit tests for passive_wait_healthcheck `[52]` agent event-store row proof."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_HELPER_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)
_SRV_ROOT = os.path.dirname(_HELPER_SCRIPTS_DIR)
sys.path.insert(0, _SRV_ROOT)

from helper_scripts.db.passive_wait_healthcheck.checks_agent_events import (  # noqa: E402
    check_52_agent_event_store_rows,
)


def _cur(fetchone_rows: list[tuple]) -> MagicMock:
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.rollback = MagicMock()
    cur.fetchone.side_effect = fetchone_rows
    return cur


class TestAgentEventStoreHealthcheck(unittest.TestCase):
    def setUp(self) -> None:
        self._old_env = dict(os.environ)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._old_env)

    def test_disabled_env_pass_skips_without_query(self) -> None:
        os.environ.pop("OPENCLAW_AGENT_EVENT_STORE_ENABLED", None)
        cur = _cur([])

        status, msg = check_52_agent_event_store_rows(cur)

        self.assertEqual(status, "PASS")
        self.assertIn("disabled", msg)
        cur.execute.assert_not_called()

    def test_enabled_all_recent_rows_pass(self) -> None:
        os.environ["OPENCLAW_AGENT_EVENT_STORE_ENABLED"] = "1"
        cur = _cur([(True,), (True,), (True,), (2,), (6,), (1,)])

        status, msg = check_52_agent_event_store_rows(cur)

        self.assertEqual(status, "PASS", msg)
        self.assertIn("messages=2", msg)
        self.assertIn("state_changes=6", msg)
        self.assertIn("ai_invocations=1", msg)

    def test_enabled_missing_table_warn_by_default(self) -> None:
        os.environ["OPENCLAW_AGENT_EVENT_STORE_ENABLED"] = "1"
        cur = _cur([(True,), (False,), (True,)])

        status, msg = check_52_agent_event_store_rows(cur)

        self.assertEqual(status, "WARN")
        self.assertIn("agent.state_changes", msg)

    def test_required_missing_table_fails(self) -> None:
        os.environ["OPENCLAW_AGENT_EVENT_STORE_ENABLED"] = "1"
        os.environ["OPENCLAW_AGENT_EVENT_STORE_HEALTH_REQUIRED"] = "1"
        cur = _cur([(True,), (False,), (True,)])

        status, msg = check_52_agent_event_store_rows(cur)

        self.assertEqual(status, "FAIL")
        self.assertIn("agent.state_changes", msg)

    def test_enabled_zero_recent_rows_warn_by_default(self) -> None:
        os.environ["OPENCLAW_AGENT_EVENT_STORE_ENABLED"] = "1"
        cur = _cur([(True,), (True,), (True,), (1,), (0,), (0,)])

        status, msg = check_52_agent_event_store_rows(cur)

        self.assertEqual(status, "WARN")
        self.assertIn("zero=agent.state_changes,agent.ai_invocations", msg)

    def test_required_zero_recent_rows_fails(self) -> None:
        os.environ["OPENCLAW_AGENT_EVENT_STORE_ENABLED"] = "1"
        os.environ["OPENCLAW_AGENT_EVENT_STORE_HEALTH_REQUIRED"] = "1"
        cur = _cur([(True,), (True,), (True,), (1,), (0,), (1,)])

        status, msg = check_52_agent_event_store_rows(cur)

        self.assertEqual(status, "FAIL")
        self.assertIn("zero=agent.state_changes", msg)

    def test_sql_contract_is_read_only(self) -> None:
        os.environ["OPENCLAW_AGENT_EVENT_STORE_ENABLED"] = "1"
        cur = _cur([(True,), (True,), (True,), (1,), (1,), (1,)])

        check_52_agent_event_store_rows(cur)

        sql_text = "\n".join(str(call.args[0]) for call in cur.execute.call_args_list)
        self.assertIn("to_regclass", sql_text)
        self.assertIn("agent.messages", sql_text)
        self.assertIn("agent.state_changes", sql_text)
        self.assertIn("agent.ai_invocations", sql_text)
        self.assertNotIn("INSERT ", sql_text.upper())
        self.assertNotIn("UPDATE ", sql_text.upper())
        self.assertNotIn("DELETE ", sql_text.upper())


if __name__ == "__main__":
    unittest.main()
