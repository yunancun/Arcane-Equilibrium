"""W5-E1-A unit tests for `canary_promotion_eval` Python helper + `[58a]` healthcheck.

對應 spec §8 acceptance #2 / #4 / #6（Python helper 與 Rust pure-logic / SQL 結果一致）。
覆蓋 happy / wall-clock-short / sample-floor-short / DSR-None / boundary-trip / Stage 4 demote
6 case + healthcheck V089 seed coverage WARN/PASS。

Reference:
  docs/execution_plan/2026-05-10--p1_canary_stage_criteria_1_spec.md §7.2 + §8
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

# 注入 program_code path 以 import 受測 module
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "program_code" / "exchange_connectors" / "bybit_connector"
                       / "control_api_v1"))

from app.canary_promotion_eval import (  # noqa: E402
    CanaryStageMetrics,
    PromoteVerdict,
    RollbackVerdict,
    evaluate_promote_criteria,
    evaluate_rollback_criteria,
)
from helper_scripts.db.passive_wait_healthcheck.checks_canary_stage_criteria import (  # noqa: E402
    check_58a_stage_criteria_eval,
    EXPECTED_METRIC_COUNT_PER_STAGE,
)


def happy_metrics(stage_entered_at_ms: int = 0, current_offset_d: int = 30) -> CanaryStageMetrics:
    """產生 baseline metric snapshot（全部達升級條件）。

    current_offset_d 預設 30d 對 Stage 3 happy path（>21d）;
    對 Stage 1/2 promote happy path 必 override 較短時間避免 starvation。
    """
    return CanaryStageMetrics(
        current_ts_ms=stage_entered_at_ms + current_offset_d * 24 * 60 * 60 * 1000,
        stage_entered_at_ms=stage_entered_at_ms,
        entry_fills_count=50,
        boundary_violation_count=0,
        gross_pnl_usdt=5.0,
        dsr=1.5,
        pbo=0.2,
        attribution_chain_ok_ratio=0.9,
        sm04_level=0,
    )


# ============================================================================
# evaluate_promote_criteria — Stage 1/2/3 happy + edge case
# ============================================================================


class StagePromoteTests(unittest.TestCase):
    """Test promote eligibility for stages 0..=4."""

    def test_stage0_pending_operator(self) -> None:
        """Stage 0 永不 auto-promote — 必 PENDING_OPERATOR."""
        m = happy_metrics()
        verdict, reason = evaluate_promote_criteria(stage=0, metrics=m)
        self.assertEqual(verdict, PromoteVerdict.PENDING_OPERATOR)
        self.assertIn("operator", reason)

    def test_stage4_pending_operator_even_perfect(self) -> None:
        """Stage 4 LIVE_PENDING — perfect metrics 仍 PENDING_OPERATOR."""
        m = happy_metrics()
        verdict, reason = evaluate_promote_criteria(stage=4, metrics=m)
        self.assertEqual(verdict, PromoteVerdict.PENDING_OPERATOR)
        self.assertIn("LIVE_PENDING", reason)

    def test_stage1_promote_happy_path(self) -> None:
        """Stage 1→2 全條件達成 — PROMOTE."""
        # Stage 1 happy path 用 8d (>7d wall_clock & 72h sample, <14d 不撞 starvation)
        m = CanaryStageMetrics(
            current_ts_ms=8 * 24 * 60 * 60 * 1000,
            stage_entered_at_ms=0,
            entry_fills_count=15,
            boundary_violation_count=0,
            gross_pnl_usdt=2.0,
            sm04_level=0,
        )
        verdict, _ = evaluate_promote_criteria(stage=1, metrics=m)
        self.assertEqual(verdict, PromoteVerdict.PROMOTE)

    def test_stage1_pending_when_wall_clock_short(self) -> None:
        """Stage 1 wall_clock 6d < 7d — PENDING."""
        m = CanaryStageMetrics(
            current_ts_ms=6 * 24 * 60 * 60 * 1000,
            stage_entered_at_ms=0,
            entry_fills_count=20,
            boundary_violation_count=0,
            gross_pnl_usdt=2.0,
            sm04_level=0,
        )
        verdict, reason = evaluate_promote_criteria(stage=1, metrics=m)
        self.assertEqual(verdict, PromoteVerdict.PENDING)
        self.assertIn("wall_clock", reason)

    def test_stage1_fail_starvation(self) -> None:
        """Stage 1 14d wall_clock 仍 entry_fills < 10 — FAIL (starvation)."""
        m = CanaryStageMetrics(
            current_ts_ms=15 * 24 * 60 * 60 * 1000,
            stage_entered_at_ms=0,
            entry_fills_count=5,
            boundary_violation_count=0,
            gross_pnl_usdt=0.0,
            sm04_level=0,
        )
        verdict, reason = evaluate_promote_criteria(stage=1, metrics=m)
        self.assertEqual(verdict, PromoteVerdict.FAIL)
        self.assertIn("starvation", reason)

    def test_stage2_pending_when_dsr_none(self) -> None:
        """Stage 2 DSR=None → PENDING（不 fail，等下次 cycle）— spec §3."""
        m = CanaryStageMetrics(
            current_ts_ms=15 * 24 * 60 * 60 * 1000,
            stage_entered_at_ms=0,
            entry_fills_count=40,
            boundary_violation_count=0,
            gross_pnl_usdt=2.0,
            dsr=None,
            sm04_level=0,
        )
        verdict, reason = evaluate_promote_criteria(stage=2, metrics=m)
        self.assertEqual(verdict, PromoteVerdict.PENDING)
        self.assertIn("DSR", reason)

    def test_stage3_ready_for_operator_review(self) -> None:
        """Stage 3 全條件達成 — READY_FOR_OPERATOR_REVIEW（不 auto-promote 至 4）."""
        m = happy_metrics(current_offset_d=22)  # >21d
        verdict, reason = evaluate_promote_criteria(stage=3, metrics=m)
        self.assertEqual(verdict, PromoteVerdict.READY_FOR_OPERATOR_REVIEW)
        self.assertIn("ready_for_stage_4_review", reason)


# ============================================================================
# evaluate_rollback_criteria — spec §5 表
# ============================================================================


class StageRollbackTests(unittest.TestCase):
    """Test rollback (demote) trigger detection."""

    def test_sm04_l3_demotes_all_stages_to_0(self) -> None:
        """SM-04 L3+ 跨 stage 強制 demote 至 Stage 0."""
        m = happy_metrics()
        m_with_sm04 = CanaryStageMetrics(**{**m.__dict__, "sm04_level": 3})
        for stage in (1, 2, 3, 4):
            verdict, reason, target = evaluate_rollback_criteria(stage=stage, metrics=m_with_sm04)
            self.assertEqual(verdict, RollbackVerdict.DEMOTE)
            self.assertEqual(target, 0)
            self.assertIn("SM-04", reason)

    def test_stage1_boundary_demotes_to_0(self) -> None:
        """Stage 1 任一 boundary trip → demote 至 Stage 0."""
        m = CanaryStageMetrics(**{**happy_metrics().__dict__, "boundary_violation_count": 2})
        verdict, _, target = evaluate_rollback_criteria(stage=1, metrics=m)
        self.assertEqual(verdict, RollbackVerdict.DEMOTE)
        self.assertEqual(target, 0)

    def test_stage2_pnl_lt_minus_10_demotes_to_1(self) -> None:
        """Stage 2 gross_pnl < -10 USDT → demote 至 Stage 1."""
        m = CanaryStageMetrics(**{**happy_metrics().__dict__, "gross_pnl_usdt": -15.0})
        verdict, _, target = evaluate_rollback_criteria(stage=2, metrics=m)
        self.assertEqual(verdict, RollbackVerdict.DEMOTE)
        self.assertEqual(target, 1)

    def test_stage3_attribution_lt_03_demotes_to_2(self) -> None:
        """Stage 3 attribution_chain_ok_ratio < 0.3 → demote 至 Stage 2."""
        m = CanaryStageMetrics(
            **{**happy_metrics().__dict__, "attribution_chain_ok_ratio": 0.2}
        )
        verdict, _, target = evaluate_rollback_criteria(stage=3, metrics=m)
        self.assertEqual(verdict, RollbackVerdict.DEMOTE)
        self.assertEqual(target, 2)

    def test_stage4_boundary_demotes_to_0(self) -> None:
        """Stage 4 任一 boundary failure → demote 至 Stage 0（不是 Stage 3）."""
        m = CanaryStageMetrics(**{**happy_metrics().__dict__, "boundary_violation_count": 1})
        verdict, _, target = evaluate_rollback_criteria(stage=4, metrics=m)
        self.assertEqual(verdict, RollbackVerdict.DEMOTE)
        self.assertEqual(target, 0)

    def test_stable_when_metrics_healthy(self) -> None:
        """全部 stage 配 happy metrics → STABLE."""
        m = happy_metrics()
        for stage in (0, 1, 2, 3, 4):
            verdict, _, target = evaluate_rollback_criteria(stage=stage, metrics=m)
            self.assertEqual(verdict, RollbackVerdict.STABLE, f"stage={stage}")
            self.assertIsNone(target)


# ============================================================================
# wall_clock_elapsed_ms helper
# ============================================================================


class HelperTests(unittest.TestCase):
    def test_wall_clock_clamp_at_zero_for_negative_skew(self) -> None:
        """current_ts_ms < stage_entered_at_ms (clock skew) → clamp at 0."""
        m = CanaryStageMetrics(
            current_ts_ms=100,
            stage_entered_at_ms=1000,
            entry_fills_count=0,
            boundary_violation_count=0,
            gross_pnl_usdt=0.0,
            sm04_level=0,
        )
        self.assertEqual(m.wall_clock_elapsed_ms(), 0)


# ============================================================================
# [58a] healthcheck — V089 seed coverage WARN/PASS path
# ============================================================================


class Check58aHealthcheckTests(unittest.TestCase):
    """[58a] stage_criteria_eval — V089 seed coverage 哨兵."""

    def _mock_cur(
        self,
        registry_exists: bool = True,
        stage_count_rows: list[tuple[int, int, int]] | None = None,
        cohort_log_rows: list[tuple[str, int]] | None = None,
    ) -> MagicMock:
        cur = MagicMock()
        cur.connection.rollback = MagicMock(return_value=None)
        # fetch sequence: registry_exists / stage_counts / cohort_log
        fetchone_seq = [(registry_exists,)]
        fetchall_seq = [
            stage_count_rows or [],
            cohort_log_rows or [],
        ]

        def _fetchone() -> Any:
            return fetchone_seq.pop(0) if fetchone_seq else None

        def _fetchall() -> Any:
            return fetchall_seq.pop(0) if fetchall_seq else []

        cur.fetchone = MagicMock(side_effect=_fetchone)
        cur.fetchall = MagicMock(side_effect=_fetchall)
        cur.execute = MagicMock(return_value=None)
        return cur

    def test_warn_when_v089_not_seeded(self) -> None:
        """V089 seed 完全缺 → WARN（drift detection 全 stage row count 為 0）."""
        cur = self._mock_cur(
            registry_exists=True,
            stage_count_rows=[],  # 0 rows
            cohort_log_rows=[],
        )
        status, msg = check_58a_stage_criteria_eval(cur)
        self.assertEqual(status, "WARN")
        self.assertIn("drift", msg)
        # 至少報 stage 1/2/3 缺
        self.assertIn("stage=1", msg)

    def test_warn_when_table_missing(self) -> None:
        """V080 metric_registry 表缺 → WARN（不 hard FAIL，[58] 已報主信號）."""
        cur = self._mock_cur(registry_exists=False)
        status, msg = check_58a_stage_criteria_eval(cur)
        self.assertEqual(status, "WARN")
        self.assertIn("V080 not applied", msg)

    def test_pass_when_v089_fully_seeded(self) -> None:
        """V089 seed 全達 EXPECTED → PASS."""
        # 對應 EXPECTED_METRIC_COUNT_PER_STAGE 全達
        stage_rows = [
            (stage, exp["promote"], exp["rollback"])
            for stage, exp in EXPECTED_METRIC_COUNT_PER_STAGE.items()
        ]
        cur = self._mock_cur(
            registry_exists=True,
            stage_count_rows=stage_rows,
            cohort_log_rows=[],
        )
        status, msg = check_58a_stage_criteria_eval(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("all stages V089 seeded", msg)

    def test_active_cohort_summary_attached(self) -> None:
        """有 active cohort 時 msg 含 cohort_id × stage 對應 metric 計數."""
        stage_rows = [
            (stage, exp["promote"], exp["rollback"])
            for stage, exp in EXPECTED_METRIC_COUNT_PER_STAGE.items()
        ]
        cur = self._mock_cur(
            registry_exists=True,
            stage_count_rows=stage_rows,
            cohort_log_rows=[
                ("grid_trading:BTCUSDT:demo", 2),
                ("global", 0),  # Stage 0 跳過
            ],
        )
        status, msg = check_58a_stage_criteria_eval(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("grid_trading:BTCUSDT:demo", msg)
        self.assertIn("stage=2", msg)


if __name__ == "__main__":
    unittest.main()
