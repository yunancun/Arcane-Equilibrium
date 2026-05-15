#!/usr/bin/env python3
"""Unit tests for passive_wait_healthcheck `[55]` Agent Spine lineage readiness."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_HELPER_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)
_SRV_ROOT = os.path.dirname(_HELPER_SCRIPTS_DIR)
sys.path.insert(0, _SRV_ROOT)


def _load_isolated_module():
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
    return mod


checks_agent_spine_mod = _load_isolated_module()
check_55_agent_decision_spine_lineage = (
    checks_agent_spine_mod.check_55_agent_decision_spine_lineage
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


def _healthy_cur() -> MagicMock:
    return _cur(
        [
            (True,),
            (True,),
            (True,),
            (5, 5),
            (4, 4),
            (1, 1),
            (1, 1, 1, 1, 0, 0, 1, 1, 1, 0, 0),
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


class TestAgentSpineHealthcheck(unittest.TestCase):
    def setUp(self) -> None:
        self._old_env = dict(os.environ)
        os.environ["OPENCLAW_AGENT_SPINE_CHANNEL_MONITOR"] = "0"

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
                (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
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
                (1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0),
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
                # 11-tuple: complete=1, idem=1, lease=1, report=1,
                # bad_quality=0, bad_value_quality=0,
                # chains_with_real_fill_report=1, plan_order_fill=1,
                # full_plan_fill=1, full_missing=0, partial=0
                (1, 1, 1, 1, 0, 0, 1, 1, 1, 0, 0),
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
        self.assertIn("chains_with_full_plan_fill=1", msg)
        self.assertIn("full_plan_fills_missing_report=0", msg)
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
                (1, 1, 1, 1, 0, 0, 1, 1, 1, 0, 0),
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

    # ── Caveat 1+2 fix 後 case：value-realism + state_changes + full-fill gate ──

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
                (1, 1, 1, 1, 0, 0, 1, 1, 1, 0, 0),
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
                (1, 1, 1, 1, 0, 5, 0, 1, 1, 0, 0),
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

    def test_no_full_fills_does_not_warn_on_low_real_fill_ratio(self) -> None:
        # 場景：100 chains 都有 stub ExecutionReport，但沒有任何交易所 fill。
        # 舊版 50% heuristic 會因 chains_with_real_fill_report=0 誤報；新版
        # 只對 Rust fully_filled 契約已達成的 plan_order_fill 要求真實 ER。
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
                # bad_value_quality=0 chains_with_real_fill_report=0
                # plan_order_fill=0 full_plan_fill=0 full_missing=0 partial=0
                (100, 100, 100, 100, 0, 0, 0, 0, 0, 0, 0),
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

        self.assertEqual(status, "PASS", msg)
        self.assertIn("LINEAGE_READY_NOT_WINDOW_PASS", msg)
        self.assertIn("chains_with_real_fill_report=0", msg)
        self.assertIn("chains_with_full_plan_fill=0", msg)

    def test_full_plan_fill_missing_report_warns(self) -> None:
        # 場景：92 條 plan order 已達 fully_filled 門檻，但只有 90 條真實 ER。
        # 這才是 [55] 現在應該攔的 fill-lineage invariant。
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
                # bad_value_quality=0 real_fill_report=90 plan_order_fill=95
                # full_plan_fill=92 full_missing=2 partial=3
                (100, 100, 100, 100, 0, 0, 90, 95, 92, 2, 3),
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
        self.assertIn("BLOCKED_REAL_FILL_REPORT_MISSING", msg)
        self.assertIn("full_plan_fills_missing_report=2", msg)
        self.assertIn("partial_plan_fill_chains=3", msg)

    def test_channel_metrics_first_sample_baselines_without_warning(self) -> None:
        os.environ["OPENCLAW_AGENT_SPINE_CLIENT_ENABLED"] = "1"
        os.environ["OPENCLAW_AGENT_SPINE_CHANNEL_MONITOR"] = "1"
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["OPENCLAW_DATA_DIR"] = tmpdir
            cur = _healthy_cur()
            metrics = {
                "status": "ok",
                "drop_total": 10,
                "retry_success_total": 4,
                "retry_fail_total": 0,
                "final_loss_approx_total": 6,
            }

            with patch.object(
                checks_agent_spine_mod,
                "_query_rust_spine_channel_metrics",
                return_value=metrics,
            ):
                status, msg = check_55_agent_decision_spine_lineage(cur)

            self.assertEqual(status, "PASS", msg)
            self.assertIn("channel_metrics=baseline", msg)
            self.assertIn("drop_semantics=initial_try_send_failures_not_final_loss", msg)
            state_path = (
                Path(tmpdir)
                / "status"
                / checks_agent_spine_mod.CHANNEL_METRICS_STATE_FILE
            )
            self.assertTrue(state_path.exists())

    def test_channel_metrics_initial_fail_rate_warns_without_calling_final_loss(self) -> None:
        os.environ["OPENCLAW_AGENT_SPINE_CLIENT_ENABLED"] = "1"
        os.environ["OPENCLAW_AGENT_SPINE_CHANNEL_MONITOR"] = "1"
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["OPENCLAW_DATA_DIR"] = tmpdir
            state_dir = Path(tmpdir) / "status"
            state_dir.mkdir(parents=True)
            state_path = state_dir / checks_agent_spine_mod.CHANNEL_METRICS_STATE_FILE
            state_path.write_text(
                json.dumps(
                    {
                        "sampled_at_unix_ms": int((time.time() - 60.0) * 1000),
                        "drop_total": 10,
                        "retry_success_total": 4,
                        "retry_fail_total": 0,
                        "final_loss_approx_total": 6,
                    }
                )
            )
            cur = _healthy_cur()
            metrics = {
                "status": "ok",
                "drop_total": 16,
                "retry_success_total": 10,
                "retry_fail_total": 0,
                "final_loss_approx_total": 6,
            }

            with patch.object(
                checks_agent_spine_mod,
                "_query_rust_spine_channel_metrics",
                return_value=metrics,
            ):
                status, msg = check_55_agent_decision_spine_lineage(cur)

            self.assertEqual(status, "WARN", msg)
            self.assertIn("channel_metrics=pressure_warn", msg)
            self.assertIn("drop_delta=6", msg)
            self.assertIn("final_loss_approx_delta=0", msg)
            self.assertIn("drop_semantics=initial_try_send_failures_not_final_loss", msg)

    def test_channel_metrics_retry_fail_delta_warns(self) -> None:
        os.environ["OPENCLAW_AGENT_SPINE_CLIENT_ENABLED"] = "1"
        os.environ["OPENCLAW_AGENT_SPINE_CHANNEL_MONITOR"] = "1"
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["OPENCLAW_DATA_DIR"] = tmpdir
            state_dir = Path(tmpdir) / "status"
            state_dir.mkdir(parents=True)
            state_path = state_dir / checks_agent_spine_mod.CHANNEL_METRICS_STATE_FILE
            state_path.write_text(
                json.dumps(
                    {
                        "sampled_at_unix_ms": int((time.time() - 60.0) * 1000),
                        "drop_total": 10,
                        "retry_success_total": 4,
                        "retry_fail_total": 0,
                        "final_loss_approx_total": 6,
                    }
                )
            )
            cur = _healthy_cur()
            metrics = {
                "status": "ok",
                "drop_total": 10,
                "retry_success_total": 4,
                "retry_fail_total": 1,
                "final_loss_approx_total": 6,
            }

            with patch.object(
                checks_agent_spine_mod,
                "_query_rust_spine_channel_metrics",
                return_value=metrics,
            ):
                status, msg = check_55_agent_decision_spine_lineage(cur)

            self.assertEqual(status, "WARN", msg)
            self.assertIn("channel_metrics=retry_fail_warn", msg)
            self.assertIn("retry_fail_delta=1", msg)


if __name__ == "__main__":
    unittest.main()
