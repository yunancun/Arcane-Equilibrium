#!/usr/bin/env python3
"""Unit tests for passive_wait_healthcheck `[55]` Agent Spine lineage readiness."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_HELPER_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)
_SRV_ROOT = os.path.dirname(_HELPER_SCRIPTS_DIR)
sys.path.insert(0, _SRV_ROOT)

from helper_scripts.db.passive_wait_healthcheck.checks_agent_spine import (  # noqa: E402
    check_55_agent_decision_spine_lineage,
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


class TestAgentSpineHealthcheck(unittest.TestCase):
    def setUp(self) -> None:
        self._old_env = dict(os.environ)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._old_env)

    def test_disabled_env_warns_with_mag082_readiness(self) -> None:
        os.environ.pop("OPENCLAW_AGENT_SPINE_CLIENT_ENABLED", None)
        cur = _cur([])

        status, msg = check_55_agent_decision_spine_lineage(cur)

        self.assertEqual(status, "WARN")
        self.assertIn("disabled", msg)
        self.assertIn("MAG-082 readiness=DISABLED", msg)
        cur.execute.assert_not_called()

    def test_required_disabled_env_fails(self) -> None:
        os.environ.pop("OPENCLAW_AGENT_SPINE_CLIENT_ENABLED", None)
        os.environ["OPENCLAW_AGENT_SPINE_HEALTH_REQUIRED"] = "1"
        cur = _cur([])

        status, msg = check_55_agent_decision_spine_lineage(cur)

        self.assertEqual(status, "FAIL")
        self.assertIn("MAG-082 readiness=DISABLED", msg)

    def test_enabled_missing_table_warn_by_default(self) -> None:
        os.environ["OPENCLAW_AGENT_SPINE_CLIENT_ENABLED"] = "1"
        cur = _cur([(True,), (False,), (True,)])

        status, msg = check_55_agent_decision_spine_lineage(cur)

        self.assertEqual(status, "WARN")
        self.assertIn("BLOCKED_SCHEMA_MISSING", msg)
        self.assertIn("agent.decision_edges", msg)

    def test_enabled_empty_warn_by_default(self) -> None:
        os.environ["OPENCLAW_AGENT_SPINE_CLIENT_ENABLED"] = "1"
        cur = _cur(
            [
                (True,),
                (True,),
                (True,),
                (0, 0),
                (0, 0),
                (0, 0),
            ]
        )

        status, msg = check_55_agent_decision_spine_lineage(cur)

        self.assertEqual(status, "WARN")
        self.assertIn("enabled but empty", msg)
        self.assertIn("BLOCKED_ENABLED_EMPTY", msg)
        self.assertIn("objects=0/0", msg)

    def test_required_empty_fails(self) -> None:
        os.environ["OPENCLAW_AGENT_SPINE_CLIENT_ENABLED"] = "1"
        os.environ["OPENCLAW_AGENT_SPINE_HEALTH_REQUIRED"] = "1"
        cur = _cur(
            [
                (True,),
                (True,),
                (True,),
                (0, 0),
                (0, 0),
                (0, 0),
            ]
        )

        status, msg = check_55_agent_decision_spine_lineage(cur)

        self.assertEqual(status, "FAIL")
        self.assertIn("BLOCKED_ENABLED_EMPTY", msg)

    def test_enabled_historical_but_no_recent_warns(self) -> None:
        os.environ["OPENCLAW_AGENT_SPINE_CLIENT_ENABLED"] = "1"
        cur = _cur(
            [
                (True,),
                (True,),
                (True,),
                (0, 5),
                (0, 4),
                (0, 2),
            ]
        )

        status, msg = check_55_agent_decision_spine_lineage(cur)

        self.assertEqual(status, "WARN")
        self.assertIn("BLOCKED_NO_RECENT_LINEAGE", msg)
        self.assertIn("objects=0/5", msg)

    def test_enabled_missing_core_type_warns(self) -> None:
        os.environ["OPENCLAW_AGENT_SPINE_CLIENT_ENABLED"] = "1"
        cur = _cur(
            [
                (True,),
                (True,),
                (True,),
                (3, 3),
                (2, 2),
                (1, 1),
                (0, 0, 0, 0, 0),
            ],
            [
                [
                    ("strategy_signal", 1),
                    ("strategist_decision", 1),
                    ("execution_plan", 1),
                ]
            ],
        )

        status, msg = check_55_agent_decision_spine_lineage(cur)

        self.assertEqual(status, "WARN")
        self.assertIn("BLOCKED_INCOMPLETE", msg)
        self.assertIn("guardian_verdict", msg)

    def test_enabled_complete_core_without_report_warns(self) -> None:
        os.environ["OPENCLAW_AGENT_SPINE_CLIENT_ENABLED"] = "1"
        cur = _cur(
            [
                (True,),
                (True,),
                (True,),
                (4, 4),
                (3, 3),
                (1, 1),
                (1, 1, 0, 0, 0),
            ],
            [
                [
                    ("strategy_signal", 1),
                    ("strategist_decision", 1),
                    ("guardian_verdict", 1),
                    ("execution_plan", 1),
                ]
            ],
        )

        status, msg = check_55_agent_decision_spine_lineage(cur)

        self.assertEqual(status, "WARN")
        self.assertIn("BLOCKED_REPORTS_PENDING", msg)
        self.assertIn("chains_with_idempotency=1", msg)

    def test_enabled_complete_lineage_passes(self) -> None:
        os.environ["OPENCLAW_AGENT_SPINE_CLIENT_ENABLED"] = "1"
        cur = _cur(
            [
                (True,),
                (True,),
                (True,),
                (5, 5),
                (4, 4),
                (1, 1),
                (1, 1, 1, 1, 0),
            ],
            [
                [
                    ("strategy_signal", 1),
                    ("strategist_decision", 1),
                    ("guardian_verdict", 1),
                    ("execution_plan", 1),
                    ("execution_report", 1),
                ]
            ],
        )

        status, msg = check_55_agent_decision_spine_lineage(cur)

        self.assertEqual(status, "PASS", msg)
        self.assertIn("LINEAGE_READY_NOT_WINDOW_PASS", msg)
        self.assertIn("chains_with_report=1", msg)

    def test_sql_contract_is_read_only(self) -> None:
        os.environ["OPENCLAW_AGENT_SPINE_CLIENT_ENABLED"] = "1"
        cur = _cur(
            [
                (True,),
                (True,),
                (True,),
                (5, 5),
                (4, 4),
                (1, 1),
                (1, 1, 1, 1, 0),
            ],
            [
                [
                    ("strategy_signal", 1),
                    ("strategist_decision", 1),
                    ("guardian_verdict", 1),
                    ("execution_plan", 1),
                    ("execution_report", 1),
                ]
            ],
        )

        check_55_agent_decision_spine_lineage(cur)

        sql_text = "\n".join(str(call.args[0]) for call in cur.execute.call_args_list)
        self.assertIn("to_regclass", sql_text)
        self.assertIn("agent.decision_objects", sql_text)
        self.assertIn("agent.decision_edges", sql_text)
        self.assertIn("agent.execution_idempotency_keys", sql_text)
        self.assertNotIn("INSERT ", sql_text.upper())
        self.assertNotIn("UPDATE ", sql_text.upper())
        self.assertNotIn("DELETE ", sql_text.upper())


if __name__ == "__main__":
    unittest.main()
