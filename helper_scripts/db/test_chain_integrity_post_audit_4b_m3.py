#!/usr/bin/env python3
"""Unit tests for `[65] check_chain_integrity_post_audit_4b_m3`.

[65] check_chain_integrity_post_audit_4b_m3 單元測試。

Spec source: MIT W6-1 RFC verdict §6 + Sprint N+0 closure memory chain
integrity 真相 section。Test cover：
  * PASS：global ratio ≥ 95% + per-strategy 全 ≥ 95%
  * PASS：global ratio = 100% (empirical baseline)
  * WARN：global ratio 80-95% (drift 偵測)
  * WARN：global PASS 但 per-strategy < 95%（global 過閾值 + per-strategy
    drift annotation）
  * WARN_LOW_SAMPLE：global total < 30 (verdict 不可靠)
  * FAIL：global ratio < 80% (producer broken)
  * FAIL：trading.fills 不存在
  * FAIL：learning.decision_features 不存在
  * Per-strategy probe failure 不降級 global verdict (best-effort annotation)
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

from helper_scripts.db.passive_wait_healthcheck.checks_derived_ml_hygiene import (  # noqa: E402
    check_chain_integrity_post_audit_4b_m3,
    CHAIN_INTEGRITY_MIN_SAMPLE,
    W_AUDIT_4B_M3_PRODUCER_DEPLOY_TS_UTC,
)


def _cur(
    fetchone_rows: list[tuple],
    fetchall_rows: list[list[tuple]] | None = None,
) -> MagicMock:
    """Build a mock cursor with side_effect-driven fetchone/fetchall.

    建造 mock cursor，fetchone / fetchall 用 side_effect drive。

    Args:
        fetchone_rows: list of (row_tuple) returned in order.
        fetchall_rows: list of (list of row_tuple) returned in order.
    """
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.rollback = MagicMock()
    cur.fetchone.side_effect = fetchone_rows
    cur.fetchall.side_effect = fetchall_rows or [[]]
    return cur


class TestChainIntegrityPostAudit4bM3(unittest.TestCase):
    """Test [65] chain_integrity_post_audit_4b_m3 healthcheck.

    [65] chain_integrity_post_audit_4b_m3 健康檢查測試。
    """

    # ────────────────────────────────────────────────────────────────────
    # PASS cases
    # ────────────────────────────────────────────────────────────────────

    def test_pass_global_100_percent_baseline(self) -> None:
        """post-M3 baseline: 92/92 = 100% chain integrity should PASS.

        post-M3 baseline 92/92 = 100% chain integrity 應 PASS。
        """
        cur = _cur(
            fetchone_rows=[
                # Existence guard: trading.fills + learning.decision_features
                (True, True),
                # Sub-query 1 global: total=92, in_df=92
                (92, 92),
            ],
            fetchall_rows=[
                # Sub-query 2 per-strategy: 全 100%
                [
                    ("grid_trading", 73, 73),
                    ("ma_crossover", 17, 17),
                    ("bb_breakout", 2, 2),
                ],
            ],
        )
        status, msg = check_chain_integrity_post_audit_4b_m3(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("100.0%", msg)
        self.assertIn("n=92", msg)
        self.assertIn("in_df=92", msg)
        self.assertIn("chain integrity holding", msg)
        self.assertNotIn("per_strategy_drift", msg)

    def test_pass_global_95_5_percent_late_arriving(self) -> None:
        """global ratio 95.5% should PASS (容忍 5% late row).

        global ratio 95.5% 應 PASS（容忍 5% late row）。
        """
        cur = _cur(
            fetchone_rows=[
                (True, True),
                # 191 / 200 = 95.5%
                (200, 191),
            ],
            fetchall_rows=[
                [
                    ("grid_trading", 100, 96),  # 96.0%
                    ("ma_crossover", 100, 95),  # 95.0% — 邊界 PASS
                ],
            ],
        )
        status, msg = check_chain_integrity_post_audit_4b_m3(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("95.5%", msg)

    def test_pass_global_exactly_at_threshold(self) -> None:
        """global ratio exactly = 95.0% should PASS (>= threshold).

        global ratio = 95.0% 應 PASS（>= 閾值）。
        """
        cur = _cur(
            fetchone_rows=[
                (True, True),
                # 95 / 100 = 95.0% boundary
                (100, 95),
            ],
            fetchall_rows=[
                [("grid_trading", 100, 95)],  # = threshold
            ],
        )
        status, msg = check_chain_integrity_post_audit_4b_m3(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("95.0%", msg)

    # ────────────────────────────────────────────────────────────────────
    # WARN cases
    # ────────────────────────────────────────────────────────────────────

    def test_warn_global_90_percent_drift(self) -> None:
        """global ratio 90% (80-95% range) should WARN — drift detected.

        global ratio 90%（80-95% 範圍）應 WARN — drift 偵測。
        """
        cur = _cur(
            fetchone_rows=[
                (True, True),
                # 90 / 100 = 90.0%
                (100, 90),
            ],
            fetchall_rows=[
                [("grid_trading", 100, 90)],  # 90.0% per-strategy drift
            ],
        )
        status, msg = check_chain_integrity_post_audit_4b_m3(cur)
        self.assertEqual(status, "WARN")
        self.assertIn("90.0%", msg)
        self.assertIn("chain drift detected", msg)
        # WARN includes per-strategy annotation since 90 < 95 per-strategy
        self.assertIn("per_strategy_drift", msg)
        self.assertIn("grid_trading=90/100", msg)

    def test_warn_global_pass_but_per_strategy_drift(self) -> None:
        """global PASS (≥95%) but a strategy < 95% should downgrade to WARN.

        global PASS（≥95%）但某策略 < 95% 應降為 WARN。
        """
        cur = _cur(
            fetchone_rows=[
                (True, True),
                # 96 / 100 = 96.0% global PASS threshold
                (100, 96),
            ],
            fetchall_rows=[
                [
                    ("grid_trading", 80, 80),     # 100% PASS
                    ("ma_crossover", 20, 16),     # 80.0% per-strategy drift
                ],
            ],
        )
        status, msg = check_chain_integrity_post_audit_4b_m3(cur)
        self.assertEqual(status, "WARN")
        self.assertIn("96.0%", msg)
        self.assertIn("global PASS but", msg)
        self.assertIn("ma_crossover=16/20", msg)

    def test_warn_low_sample(self) -> None:
        """post-M3 fills_w_entry < 30 should WARN_LOW_SAMPLE — verdict unreliable.

        post-M3 fills_w_entry < 30 應 WARN_LOW_SAMPLE — verdict 不可靠。
        """
        cur = _cur(
            fetchone_rows=[
                (True, True),
                # total=10 < CHAIN_INTEGRITY_MIN_SAMPLE=30
                (10, 10),
            ],
            fetchall_rows=[],  # not reached
        )
        status, msg = check_chain_integrity_post_audit_4b_m3(cur)
        self.assertEqual(status, "WARN")
        self.assertIn("LOW_SAMPLE", msg)
        self.assertIn("post-M3 fills_w_entry=10", msg)
        self.assertIn(f"need >={CHAIN_INTEGRITY_MIN_SAMPLE}", msg)

    def test_warn_low_sample_at_boundary(self) -> None:
        """post-M3 fills_w_entry = 29 (1 below boundary) should WARN_LOW_SAMPLE.

        post-M3 fills_w_entry = 29（邊界下 1）應 WARN_LOW_SAMPLE。
        """
        cur = _cur(
            fetchone_rows=[
                (True, True),
                (29, 29),
            ],
            fetchall_rows=[],
        )
        status, msg = check_chain_integrity_post_audit_4b_m3(cur)
        self.assertEqual(status, "WARN")
        self.assertIn("LOW_SAMPLE", msg)

    # ────────────────────────────────────────────────────────────────────
    # FAIL cases
    # ────────────────────────────────────────────────────────────────────

    def test_fail_global_70_percent_producer_broken(self) -> None:
        """global ratio 70% (< 80%) should FAIL — producer broken.

        global ratio 70%（< 80%）應 FAIL — producer broken。
        """
        cur = _cur(
            fetchone_rows=[
                (True, True),
                # 70 / 100 = 70.0%
                (100, 70),
            ],
            fetchall_rows=[
                [("grid_trading", 100, 70)],
            ],
        )
        status, msg = check_chain_integrity_post_audit_4b_m3(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("70.0%", msg)
        self.assertIn("significant chain drift", msg)
        self.assertIn("post-M3 producer broken", msg)

    def test_fail_global_zero_percent(self) -> None:
        """global ratio 0% (orphan all) should FAIL.

        global ratio 0%（全 orphan）應 FAIL。
        """
        cur = _cur(
            fetchone_rows=[
                (True, True),
                # 0 / 100 = 0%
                (100, 0),
            ],
            fetchall_rows=[
                [("grid_trading", 100, 0)],
            ],
        )
        status, msg = check_chain_integrity_post_audit_4b_m3(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("0.0%", msg)

    def test_fail_trading_fills_missing(self) -> None:
        """trading.fills missing should FAIL — schema not initialized.

        trading.fills 缺應 FAIL — schema 未初始化。
        """
        cur = _cur(
            fetchone_rows=[
                # trading.fills=False, decision_features irrelevant
                (False, False),
            ],
        )
        status, msg = check_chain_integrity_post_audit_4b_m3(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("trading.fills missing", msg)

    def test_fail_decision_features_missing(self) -> None:
        """learning.decision_features missing should FAIL — V019 not applied.

        learning.decision_features 缺應 FAIL — V019 未套用。
        """
        cur = _cur(
            fetchone_rows=[
                # trading.fills=True, decision_features=False
                (True, False),
            ],
        )
        status, msg = check_chain_integrity_post_audit_4b_m3(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("learning.decision_features missing", msg)
        self.assertIn("V019 not applied", msg)

    def test_fail_existence_query_exception(self) -> None:
        """Existence guard query exception should FAIL.

        存在性守衛 query exception 應 FAIL。
        """
        cur = MagicMock()
        cur.connection = MagicMock()
        cur.connection.rollback = MagicMock()
        cur.execute.side_effect = RuntimeError("connection lost")

        status, msg = check_chain_integrity_post_audit_4b_m3(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("table existence check failed", msg)

    def test_fail_global_query_exception(self) -> None:
        """Global chain query exception should FAIL.

        Global chain query exception 應 FAIL。
        """
        cur = MagicMock()
        cur.connection = MagicMock()
        cur.connection.rollback = MagicMock()
        # First execute (existence guard) returns OK; fetchone returns (True, True)
        # Second execute (global query) raises
        execute_call_count = {"n": 0}

        def execute_side_effect(*args, **kwargs):
            execute_call_count["n"] += 1
            if execute_call_count["n"] == 1:
                return None  # existence guard succeeds
            raise RuntimeError("disk full")

        cur.execute.side_effect = execute_side_effect
        cur.fetchone.side_effect = [(True, True)]

        status, msg = check_chain_integrity_post_audit_4b_m3(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("global chain query failed", msg)

    # ────────────────────────────────────────────────────────────────────
    # Best-effort per-strategy probe (annotate but don't downgrade)
    # ────────────────────────────────────────────────────────────────────

    def test_per_strategy_probe_failure_does_not_downgrade(self) -> None:
        """Per-strategy probe failure should annotate but not change verdict.

        Per-strategy probe 失敗應只附 annotation，不改 verdict。
        """
        cur = MagicMock()
        cur.connection = MagicMock()
        cur.connection.rollback = MagicMock()

        # Sequence:
        #   execute 1: existence guard → OK
        #   execute 2: global query → OK
        #   execute 3: per-strategy → raise
        execute_call_count = {"n": 0}

        def execute_side_effect(*args, **kwargs):
            execute_call_count["n"] += 1
            if execute_call_count["n"] in (1, 2):
                return None
            raise RuntimeError("statement timeout")

        cur.execute.side_effect = execute_side_effect
        # fetchone: existence (True, True) → global (100, 96)
        cur.fetchone.side_effect = [(True, True), (100, 96)]
        cur.fetchall.side_effect = [[]]  # unused due to exception

        status, msg = check_chain_integrity_post_audit_4b_m3(cur)
        # global 96% PASS — per-strategy probe failure does not downgrade
        self.assertEqual(status, "PASS")
        self.assertIn("per_strategy_probe_failed", msg)
        self.assertIn("RuntimeError", msg)

    # ────────────────────────────────────────────────────────────────────
    # Per-strategy with small samples (skip noise)
    # ────────────────────────────────────────────────────────────────────

    def test_small_sample_per_strategy_skipped(self) -> None:
        """Per-strategy with total < 5 should be skipped (noise filter).

        Per-strategy total < 5 應跳過（noise filter）。
        """
        cur = _cur(
            fetchone_rows=[
                (True, True),
                # 100 / 100 = 100% global PASS
                (100, 100),
            ],
            fetchall_rows=[
                [
                    ("grid_trading", 90, 90),  # 100%
                    ("ma_crossover", 8, 8),    # 100%
                    ("funding_arb", 2, 0),     # 0%, but n=2 < 5, should be skipped
                ],
            ],
        )
        status, msg = check_chain_integrity_post_audit_4b_m3(cur)
        # funding_arb should be skipped (n=2 < 5), so no per_strategy_drift
        self.assertEqual(status, "PASS")
        self.assertNotIn("per_strategy_drift", msg)

    def test_warn_per_strategy_drift_with_global_pass(self) -> None:
        """Per-strategy 94% (just below 95) with global PASS triggers WARN.

        Per-strategy 94%（剛低 95）global PASS 觸發 WARN。
        """
        cur = _cur(
            fetchone_rows=[
                (True, True),
                # 198 / 200 = 99.0% global PASS
                (200, 198),
            ],
            fetchall_rows=[
                [
                    ("grid_trading", 100, 100),  # 100% PASS
                    ("ma_crossover", 100, 94),   # 94% just below per-strategy threshold
                ],
            ],
        )
        status, msg = check_chain_integrity_post_audit_4b_m3(cur)
        self.assertEqual(status, "WARN")
        self.assertIn("global PASS but 1 strategy", msg)
        self.assertIn("ma_crossover=94/100", msg)
        self.assertIn("(94.0%)", msg)

    # ────────────────────────────────────────────────────────────────────
    # Era timestamp constant integrity
    # ────────────────────────────────────────────────────────────────────

    def test_era_timestamp_constant_matches_spec(self) -> None:
        """W_AUDIT_4B_M3_PRODUCER_DEPLOY_TS_UTC must match MIT empirical 2026-05-09 09:22 UTC.

        W_AUDIT_4B_M3_PRODUCER_DEPLOY_TS_UTC 必對應 MIT empirical 2026-05-09 09:22 UTC。
        """
        self.assertEqual(
            W_AUDIT_4B_M3_PRODUCER_DEPLOY_TS_UTC, "2026-05-09 09:22:00",
            "[65] era timestamp must match MIT W6-1 RFC verdict §6 + Sprint N+0 "
            "memory empirical baseline",
        )

    def test_era_timestamp_in_message(self) -> None:
        """Verdict message must include era timestamp for governance audit trail.

        Verdict message 必含 era timestamp（governance audit trail）。
        """
        cur = _cur(
            fetchone_rows=[
                (True, True),
                (100, 100),
            ],
            fetchall_rows=[
                [("grid_trading", 100, 100)],
            ],
        )
        _, msg = check_chain_integrity_post_audit_4b_m3(cur)
        self.assertIn(W_AUDIT_4B_M3_PRODUCER_DEPLOY_TS_UTC, msg)
        self.assertIn("UTC", msg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
