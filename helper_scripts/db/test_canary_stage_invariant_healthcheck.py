#!/usr/bin/env python3
"""Unit tests for passive_wait_healthcheck `[58]` graduated canary stage invariant.

Tests cover AMD-2026-05-09-03 §4.1 五語義 + TODO §5.3 invariant 11/12:
  - V080 兩表存在性 fail-closed
  - 0 stage transitions = PASS（initial state）
  - manual_promote NULL lease = FAIL（invariant 11 partial-rollout drift）
  - SM-04 ≥ L3 escalate + cohort 仍 active = FAIL（invariant 12）
  - Stage 1 提前升級 (< 50% 觀察期) = WARN（invariant 4 premature drift）
  - Stage 1/2 cohort_id 違反 strategy:symbol:env = FAIL（invariant 5）
  - Stage 3 cohort_id != 'global' = FAIL（invariant 5）
  - Metric registry 缺核心 metric = WARN（invariant 1+2 spec drift）
  - 全 invariant unbroken = PASS

純 mock-cursor 測試（無 PG dependency）；純 SELECT 契約驗證；read-only 確認。
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

from helper_scripts.db.passive_wait_healthcheck.checks_canary_stage_invariant import (  # noqa: E402
    check_58_graduated_canary_stage_invariant,
)


def _make_cur(
    fetchone_rows: list[tuple] | None = None,
    fetchall_rows: list[list[tuple]] | None = None,
) -> MagicMock:
    """Build a mock psycopg2 cursor with deterministic fetchone/fetchall sequence.

    建立 mock psycopg2 cursor，fetchone/fetchall 按 side_effect 順序回值。
    """
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.rollback = MagicMock()
    if fetchone_rows is not None:
        cur.fetchone.side_effect = fetchone_rows
    if fetchall_rows is not None:
        cur.fetchall.side_effect = fetchall_rows
    return cur


# ---------------------------------------------------------------------------
# Common cohort-row factory.
# 共用 cohort row 工廠。
# Format: (cohort_id, to_stage, transition_kind, decision_lease_id_text,
#          triggered_metric, created_at_ms)
# ---------------------------------------------------------------------------
def _cohort_row(
    cohort_id: str,
    to_stage: int,
    transition_kind: str = "auto_promote",
    decision_lease_id: str | None = None,
    triggered_metric: str | None = None,
    created_at_ms: int = 1735689600000,  # 2025-01-01 UTC ms
) -> tuple:
    return (
        cohort_id,
        to_stage,
        transition_kind,
        decision_lease_id,
        triggered_metric,
        created_at_ms,
    )


# ---------------------------------------------------------------------------
# Common metric-registry row factory.
# 共用 metric registry row 工廠。
# Format: (stage, metric_name, direction, threshold_value, window_ms, active)
# ---------------------------------------------------------------------------
def _registry_row(
    stage: int,
    metric_name: str,
    direction: str = "promote_upper",
    threshold: float = 10.0,
    window_ms: int = 24 * 60 * 60 * 1000,
    active: bool = True,
) -> tuple:
    return (stage, metric_name, direction, threshold, window_ms, active)


# Stage 1 minimum metrics per AMD §2.2
# Stage 1 最少 metrics（AMD §2.2）。
_STAGE1_MIN_REGISTRY = [
    _registry_row(1, "entry_fills"),
    _registry_row(1, "boundary_violation_count"),
]


class TestCanaryStageInvariantHealthcheck(unittest.TestCase):
    # ------------------------------------------------------------------
    # Pre-check / fail-closed paths
    # ------------------------------------------------------------------

    def test_v080_log_table_missing_fails_closed(self) -> None:
        """V080 governance.canary_stage_log 缺 → fail-closed FAIL.

        V080 governance.canary_stage_log missing → fail-closed FAIL.
        """
        cur = _make_cur(fetchone_rows=[(False, True)])

        status, msg = check_58_graduated_canary_stage_invariant(cur)

        self.assertEqual(status, "FAIL")
        self.assertIn("governance.canary_stage_log missing", msg)
        self.assertIn("V080 not applied", msg)

    def test_v080_registry_table_missing_fails_closed(self) -> None:
        """V080 governance.canary_stage_metric_registry 缺 → fail-closed FAIL.

        V080 metric_registry missing → fail-closed FAIL.
        """
        cur = _make_cur(fetchone_rows=[(True, False)])

        status, msg = check_58_graduated_canary_stage_invariant(cur)

        self.assertEqual(status, "FAIL")
        self.assertIn("canary_stage_metric_registry missing", msg)

    def test_db_pre_check_exception_fails_closed(self) -> None:
        """Pre-check query exception → fail-closed FAIL.

        Pre-check query 例外 → fail-closed FAIL.
        """
        cur = MagicMock()
        cur.connection = MagicMock()
        cur.connection.rollback = MagicMock()
        cur.execute.side_effect = Exception("connection lost")

        status, msg = check_58_graduated_canary_stage_invariant(cur)

        self.assertEqual(status, "FAIL")
        self.assertIn("table existence check failed", msg)

    # ------------------------------------------------------------------
    # Empty / initial state
    # ------------------------------------------------------------------

    def test_empty_log_table_passes_initial_state(self) -> None:
        """0 stage transitions = PASS（Stage 0 fail-closed default initial）.

        0 stage transitions → PASS (Stage 0 default initial state).
        """
        cur = _make_cur(
            fetchone_rows=[(True, True)],
            fetchall_rows=[[]],  # latest_per_cohort = empty
        )

        status, msg = check_58_graduated_canary_stage_invariant(cur)

        self.assertEqual(status, "PASS")
        self.assertIn("0 stage transitions logged", msg)
        self.assertIn("Stage 0 default", msg)

    # ------------------------------------------------------------------
    # invariant 11 — manual_promote NOT NULL lease drift
    # ------------------------------------------------------------------

    def test_manual_promote_null_lease_fails_invariant_11(self) -> None:
        """manual_promote NULL lease drift → FAIL invariant 11。

        本場景模擬 V080 PG CHECK 部分 rollout drift（理論不可達）：
        active cohort all stage 0；但 manual_null_count > 0 → FAIL。
        """
        cur = _make_cur(
            fetchone_rows=[
                (True, True),  # pre-check
                (3,),  # manual_null_count → 3 partial-rollout drift rows
            ],
            fetchall_rows=[
                # latest_per_cohort：1 cohort at Stage 0
                [_cohort_row("global", 0, "auto_rollback")],
                [],  # registry rows (empty)
                [],  # sm04_recent_rows (empty)
            ],
        )

        status, msg = check_58_graduated_canary_stage_invariant(cur)

        self.assertEqual(status, "FAIL")
        self.assertIn("manual_promote NULL-lease rows=3", msg)
        self.assertIn("invariant 11", msg)

    # ------------------------------------------------------------------
    # invariant 12 — SM-04 >= L3 escalate must rollback all to Stage 0
    # ------------------------------------------------------------------

    def test_sm04_escalate_with_active_cohort_fails_invariant_12(self) -> None:
        """SM-04 ≥ L3 escalate 24h 內 + cohort 仍 Stage ≥1 → FAIL invariant 12.

        SM-04 escalate within 24h + cohort still active → FAIL invariant 12.
        """
        cur = _make_cur(
            fetchone_rows=[
                (True, True),  # pre-check
                (0,),  # manual_null_count = 0
                (None,),  # prior_row for invariant 4 check (no prior)
            ],
            fetchall_rows=[
                # latest_per_cohort：grid_trading active in Stage 1 demo
                [_cohort_row("grid_trading:BTCUSDT:demo", 1)],
                # registry rows: stage 1 minimum present
                _STAGE1_MIN_REGISTRY,
                # sm04_recent_rows：1 incident_rollback ILIKE '%sm04%'
                [
                    (
                        "global",
                        0,
                        "sm04_l3_escalate",
                        1735689600000,
                    )
                ],
            ],
        )

        status, msg = check_58_graduated_canary_stage_invariant(cur)

        self.assertEqual(status, "FAIL")
        self.assertIn("SM-04 escalate detected in 24h", msg)
        self.assertIn("invariant 12", msg)

    def test_sm04_escalate_with_only_stage_zero_passes(self) -> None:
        """SM-04 escalate 24h 但全 cohort 都 Stage 0 → PASS（auto-rollback honored）.

        SM-04 escalate but all cohorts Stage 0 → PASS (rollback honored).
        """
        cur = _make_cur(
            fetchone_rows=[
                (True, True),  # pre-check
                (0,),  # manual_null_count = 0
            ],
            fetchall_rows=[
                # latest_per_cohort: all at Stage 0 (auto-rollback honored)
                [
                    _cohort_row(
                        "grid_trading:BTCUSDT:demo", 0, "auto_rollback"
                    ),
                    _cohort_row("global", 0, "incident_rollback"),
                ],
                # registry rows: empty (Stage 0 has no metrics)
                [],
                # sm04_recent_rows: SM-04 fired but cohorts already rolled back
                [
                    (
                        "grid_trading:BTCUSDT:demo",
                        0,
                        "sm04_l3_escalate",
                        1735689600000,
                    )
                ],
            ],
        )

        status, msg = check_58_graduated_canary_stage_invariant(cur)

        self.assertEqual(status, "PASS")
        self.assertIn("active_cohorts=0", msg)
        # SM-04 boolean is true but no active cohort = no violation
        self.assertIn("sm04_escalated_24h=True", msg)

    # ------------------------------------------------------------------
    # invariant 4 — observation period premature drift
    # ------------------------------------------------------------------

    def test_stage1_promoted_within_short_window_warns_invariant_4(self) -> None:
        """Stage 1 cohort 在 < 50% 7d 觀察期內又升級 → WARN invariant 4.

        Stage 1 promoted within < 50% (3.5d) of 7d obs period → WARN inv 4.
        """
        # prior transition was 1 hour earlier (much < 3.5d)
        # 上次 transition 在 1 小時前（遠 < 3.5d）
        prior_ms = 1735689600000 - 3600 * 1000
        cur = _make_cur(
            fetchone_rows=[
                (True, True),  # pre-check
                (0,),  # manual_null_count = 0
                (prior_ms,),  # prior_row for invariant 4 check
            ],
            fetchall_rows=[
                # latest_per_cohort: ma_crossover at Stage 2 (just promoted)
                [
                    _cohort_row(
                        "ma_crossover:ETHUSDT:demo",
                        2,
                        "auto_promote",
                        triggered_metric="entry_fills",
                        created_at_ms=1735689600000,
                    )
                ],
                # registry rows: stage 2 has all 4 minimum metrics present
                [
                    _registry_row(2, "gross_pnl_usdt"),
                    _registry_row(2, "DSR"),
                    _registry_row(2, "entry_fills"),
                    _registry_row(2, "boundary_violation_count"),
                ],
                # sm04_recent_rows: empty
                [],
            ],
        )

        status, msg = check_58_graduated_canary_stage_invariant(cur)

        self.assertEqual(status, "WARN")
        self.assertIn("invariant 4 premature drift", msg)
        self.assertIn("ma_crossover:ETHUSDT:demo", msg)

    # ------------------------------------------------------------------
    # invariant 5 — cohort scope violations
    # ------------------------------------------------------------------

    def test_stage1_cohort_id_global_fails_invariant_5(self) -> None:
        """Stage 1 cohort_id='global' → FAIL invariant 5（必為 1×1）.

        Stage 1 cohort_id='global' → FAIL invariant 5.
        """
        cur = _make_cur(
            fetchone_rows=[
                (True, True),  # pre-check
                (0,),  # manual_null_count = 0
                (None,),  # prior_row for invariant 4 (no prior)
            ],
            fetchall_rows=[
                # latest_per_cohort: VIOLATION — Stage 1 with global cohort
                [_cohort_row("global", 1)],
                _STAGE1_MIN_REGISTRY,
                [],  # sm04_recent_rows
            ],
        )

        status, msg = check_58_graduated_canary_stage_invariant(cur)

        self.assertEqual(status, "FAIL")
        self.assertIn("Stage 1/2 必為 1×1", msg)

    def test_stage3_cohort_id_not_global_fails_invariant_5(self) -> None:
        """Stage 3 cohort_id != 'global' → FAIL invariant 5（必為 active universe）.

        Stage 3 cohort_id != 'global' → FAIL invariant 5.
        """
        cur = _make_cur(
            fetchone_rows=[
                (True, True),  # pre-check
                (0,),  # manual_null_count = 0
                (None,),  # prior_row
            ],
            fetchall_rows=[
                # VIOLATION — Stage 3 with strategy-symbol cohort
                [_cohort_row("grid_trading:BTCUSDT:demo", 3)],
                # registry rows: stage 3 minimum
                [
                    _registry_row(3, "gross_pnl_usdt"),
                    _registry_row(3, "DSR"),
                    _registry_row(3, "attribution_chain_ok_ratio"),
                    _registry_row(3, "boundary_violation_count"),
                ],
                [],  # sm04_recent_rows
            ],
        )

        status, msg = check_58_graduated_canary_stage_invariant(cur)

        self.assertEqual(status, "FAIL")
        self.assertIn("Stage 3 必為 active universe", msg)

    # ------------------------------------------------------------------
    # invariant 1+2 — metric registry drift
    # ------------------------------------------------------------------

    def test_stage1_missing_metric_registry_warns(self) -> None:
        """Stage 1 active cohort 但 registry 缺 boundary_violation_count → WARN.

        Stage 1 active cohort but registry lacks core metric → WARN drift.
        """
        cur = _make_cur(
            fetchone_rows=[
                (True, True),  # pre-check
                (0,),  # manual_null_count = 0
                (None,),  # prior_row (no prior)
            ],
            fetchall_rows=[
                # Stage 1 cohort
                [_cohort_row("grid_trading:BTCUSDT:demo", 1)],
                # registry: missing boundary_violation_count (only entry_fills)
                [_registry_row(1, "entry_fills")],
                [],  # sm04_recent_rows
            ],
        )

        status, msg = check_58_graduated_canary_stage_invariant(cur)

        self.assertEqual(status, "WARN")
        self.assertIn("boundary_violation_count", msg)
        self.assertIn("spec drift signal", msg)

    # ------------------------------------------------------------------
    # All-green path
    # ------------------------------------------------------------------

    def test_all_invariants_unbroken_passes(self) -> None:
        """全 5 invariants 完整 → PASS.

        All 5 invariants unbroken → PASS.
        """
        cur = _make_cur(
            fetchone_rows=[
                (True, True),  # pre-check
                (0,),  # manual_null_count = 0
                (None,),  # prior_row (no premature transitions)
            ],
            fetchall_rows=[
                # Stage 1 cohort with proper 'strategy:symbol:env' format
                [_cohort_row("grid_trading:BTCUSDT:demo", 1)],
                _STAGE1_MIN_REGISTRY,
                [],  # sm04_recent_rows: empty = no SM-04 escalate
            ],
        )

        status, msg = check_58_graduated_canary_stage_invariant(cur)

        self.assertEqual(status, "PASS", msg=msg)
        self.assertIn("active_cohorts=1", msg)
        self.assertIn("graduated_canary_stage_invariant all 5 unbroken", msg)

    # ------------------------------------------------------------------
    # SQL contract — read-only
    # ------------------------------------------------------------------

    def test_sql_contract_is_read_only(self) -> None:
        """確認本健檢 SQL 為純 SELECT（無 INSERT/UPDATE/DELETE）.

        Verify all SQL emitted is pure SELECT (no mutation).
        """
        cur = _make_cur(
            fetchone_rows=[(True, True), (0,)],
            fetchall_rows=[[], [], []],
        )

        check_58_graduated_canary_stage_invariant(cur)

        sql_text = "\n".join(
            str(call.args[0]) for call in cur.execute.call_args_list
        )
        self.assertIn("governance.canary_stage_log", sql_text)
        self.assertIn("governance.canary_stage_metric_registry", sql_text)
        self.assertNotIn("INSERT ", sql_text.upper())
        self.assertNotIn("UPDATE ", sql_text.upper())
        self.assertNotIn("DELETE ", sql_text.upper())
        self.assertNotIn("DROP ", sql_text.upper())
        self.assertNotIn("TRUNCATE ", sql_text.upper())


if __name__ == "__main__":
    unittest.main()
