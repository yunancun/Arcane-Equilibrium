#!/usr/bin/env python3
"""Unit tests for passive_wait_healthcheck `[55]` Agent Spine lineage readiness."""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from unittest.mock import MagicMock

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_HELPER_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)
_SRV_ROOT = os.path.dirname(_HELPER_SCRIPTS_DIR)
sys.path.insert(0, _SRV_ROOT)


def _load_isolated_check_55():
    # 用 importlib spec 直接 load checks_agent_spine 模塊，繞過 package __init__.py
    # 的 runner import chain（W1 panel_aggregator IMPL 在不同 wave 進行中，
    # 其 import 在 runner.py 被預先寫入但對應 check 函數尚未 land，會觸發
    # ImportError pre-existing breakage；此測試 SoT 不應被 wave 間 in-progress
    # IMPL 影響）。
    spec_path = os.path.join(
        _HELPER_SCRIPTS_DIR,
        "db",
        "passive_wait_healthcheck",
        "checks_agent_spine.py",
    )
    spec = importlib.util.spec_from_file_location(
        "checks_agent_spine_isolated",
        spec_path,
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.check_55_agent_decision_spine_lineage


check_55_agent_decision_spine_lineage = _load_isolated_check_55()


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

    def test_runtime_mode_shadow_enables_check(self) -> None:
        os.environ.pop("OPENCLAW_AGENT_SPINE_CLIENT_ENABLED", None)
        os.environ["OPENCLAW_AGENT_SPINE_RUNTIME_MODE"] = "shadow"
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
        self.assertIn("BLOCKED_ENABLED_EMPTY", msg)
        self.assertTrue(cur.execute.called)

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
                (0, 0, 0, 0, 0, 0, 0),
                (0,),
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
                (1, 1, 0, 0, 0, 0, 0),
                (0,),
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
                # 7-tuple: complete=1, idem=1, lease=1, report=1, bad_quality=0,
                #          bad_value_quality=0, chains_with_real_fill_report=1
                (1, 1, 1, 1, 0, 0, 1),
                # state_changes_24h>0
                (5,),
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
        self.assertIn("bad_report_value_quality=0", msg)
        self.assertIn("chains_with_real_fill_report=1", msg)
        self.assertIn("state_changes_24h=5", msg)

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
                (1, 1, 1, 1, 0, 0, 1),
                (5,),
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
        self.assertIn("agent.decision_state_changes", sql_text)
        self.assertIn("fill_completion", sql_text)
        self.assertNotIn("INSERT ", sql_text.upper())
        self.assertNotIn("UPDATE ", sql_text.upper())
        self.assertNotIn("DELETE ", sql_text.upper())

    # ── Caveat 1+2 fix 後新加 3 case：value-realism + state_changes gate ──

    def test_state_changes_empty_blocks_after_pass_path(self) -> None:
        # 場景：complete chain + idempotency + lease + report 全 OK，
        # bad_report_quality=0，但 state_changes_24h=0 → BLOCKED_STATE_CHANGES_EMPTY
        # 對應 PA Caveat 1：producer 沒接 caller。
        os.environ["OPENCLAW_AGENT_SPINE_CLIENT_ENABLED"] = "1"
        cur = _cur(
            [
                (True,),
                (True,),
                (True,),
                (5, 5),
                (4, 4),
                (1, 1),
                (1, 1, 1, 1, 0, 0, 1),
                # state_changes_24h = 0 觸發新 gate
                (0,),
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

        self.assertEqual(status, "WARN")
        self.assertIn("BLOCKED_STATE_CHANGES_EMPTY", msg)
        self.assertIn("state_changes_24h=0", msg)

    def test_bad_report_value_quality_blocks_with_cutoff(self) -> None:
        # 場景：cutoff 之後有 5 條 stub real-fill row（filled_qty=0 或 liq_role=unknown）
        # → bad_report_value_quality=5 觸發 BLOCKED_REPORT_VALUE_QUALITY
        # 對應 PA Caveat 2：value-realism gate（Rust FIX-2 未部署或 deploy 後有 stub row 漏掉）。
        os.environ["OPENCLAW_AGENT_SPINE_CLIENT_ENABLED"] = "1"
        # 模擬 operator 已設 cutoff env var
        os.environ["OPENCLAW_AGENT_SPINE_VALUE_QUALITY_CUTOFF_TS"] = "2026-05-11T00:00:00+02"
        cur = _cur(
            [
                (True,),
                (True,),
                (True,),
                (5, 5),
                (4, 4),
                (1, 1),
                # complete=1 idem=1 lease=1 report=1 bad_quality=0
                # bad_value_quality=5 chains_with_real_fill_report=0
                (1, 1, 1, 1, 0, 5, 0),
                (10,),
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

        self.assertEqual(status, "WARN")
        self.assertIn("BLOCKED_REPORT_VALUE_QUALITY", msg)
        self.assertIn("bad_report_value_quality=5", msg)
        self.assertIn("value_quality_cutoff=2026-05-11T00:00:00+02", msg)

    def test_real_fill_propagation_partial_warns(self) -> None:
        # 場景：100 chains，但 chains_with_real_fill_report=10（< 50% 門檻=50）
        # → WARN_REAL_FILL_PROPAGATION_PARTIAL
        # 對應 PA §3.3 階段性 partial gate（real-fill propagation 還在累積）。
        os.environ["OPENCLAW_AGENT_SPINE_CLIENT_ENABLED"] = "1"
        cur = _cur(
            [
                (True,),
                (True,),
                (True,),
                (500, 500),
                (400, 400),
                (100, 100),
                # complete=100 idem=100 lease=100 report=100 bad_quality=0
                # bad_value_quality=0 chains_with_real_fill_report=10 (10% < 50%)
                (100, 100, 100, 100, 0, 0, 10),
                (500,),
            ],
            [
                [
                    ("strategy_signal", 100),
                    ("strategist_decision", 100),
                    ("guardian_verdict", 100),
                    ("execution_plan", 100),
                    ("execution_report", 100),
                ]
            ],
        )

        status, msg = check_55_agent_decision_spine_lineage(cur)

        self.assertEqual(status, "WARN")
        self.assertIn("WARN_REAL_FILL_PROPAGATION_PARTIAL", msg)
        self.assertIn("chains_with_real_fill_report=10", msg)


if __name__ == "__main__":
    unittest.main()
