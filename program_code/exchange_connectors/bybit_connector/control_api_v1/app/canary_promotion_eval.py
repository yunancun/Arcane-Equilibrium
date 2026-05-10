"""W5-E1-A P1-CANARY-STAGE-CRITERIA-1 — Python promote / rollback evaluator。

MODULE_NOTE:
  W5-E1-A spec
    `docs/execution_plan/2026-05-10--p1_canary_stage_criteria_1_spec.md`
  §7.2 Python 端 promote/rollback evaluator helper。Rust 端 pure-logic 在
  `rust/openclaw_engine/src/config/canary_promotion.rs`；Python 端鏡像
  Rust 公式（參數 + threshold + verdict 一致），方便 shadow_mode_provider
  stage-aware 路徑跨語言對齊（per spec §8 acceptance #4：cohort grid_trading
  × BTCUSDT × demo Python helper 跑出 PromoteVerdict 與 [58] SQL 結果一致）。

  使用模式：
    from .canary_promotion_eval import (
        CanaryStageMetrics, PromoteVerdict, RollbackVerdict,
        evaluate_promote_criteria, evaluate_rollback_criteria,
    )
    metrics = CanaryStageMetrics(
        current_ts_ms=int(time.time() * 1000),
        stage_entered_at_ms=stage_entered_ms,
        entry_fills_count=42,
        boundary_violation_count=0,
        gross_pnl_usdt=3.2,
        dsr=1.1, pbo=0.3, attribution_chain_ok_ratio=0.85,
        sm04_level=0,
    )
    verdict = evaluate_promote_criteria(stage=2, metrics=metrics)

  與 Rust 端公式對齊（per spec §2-§5）：
    - Stage 0 / Stage 4 永不 auto-promote
    - Stage 1→2: wall_clock ≥ 7d AND entry_fills ≥ 10 AND boundary=0 AND sample ≥ 72h
    - Stage 2→3: wall_clock ≥ 14d AND entry_fills ≥ 30 AND gross_pnl > -5
                 AND DSR > 0.5 AND boundary=0 AND sample ≥ 168h
    - Stage 3→4: wall_clock ≥ 21d AND gross_pnl > 0 AND DSR > 0 AND PBO ≤ 0.5
                 AND attribution_chain_ok ≥ 0.7 AND boundary=0 → ReadyForOperatorReview
    - Rollback: spec §5 表，sm04_level ≥ 3 跨 stage 強制 demote 至 Stage 0

  fail-soft 不變式：
    - DSR / PBO / attribution_chain_ok_ratio = None → Pending（不 fail）
    - 任何輸入 metric 異常（NaN / inf）由上游 caller 過濾，本 evaluator 不檢查

  Reference: docs/governance_dev/amendments/2026-05-09--AMD-2026-05-09-03-graduated-canary-default.md
             rust/openclaw_engine/src/config/canary_promotion.rs（Rust mirror）
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# 觀察期常數 — 與 Rust canary_promotion.rs 對齊
# ---------------------------------------------------------------------------

STAGE1_WALL_CLOCK_MS: int = 7 * 24 * 60 * 60 * 1000      # 604800000
STAGE2_WALL_CLOCK_MS: int = 14 * 24 * 60 * 60 * 1000     # 1209600000
STAGE3_WALL_CLOCK_MS: int = 21 * 24 * 60 * 60 * 1000     # 1814400000

STAGE1_SAMPLE_FLOOR_MS: int = 72 * 60 * 60 * 1000        # 259200000
STAGE2_SAMPLE_FLOOR_MS: int = 7 * 24 * 60 * 60 * 1000    # 604800000

# Promote thresholds
STAGE1_ENTRY_FILLS_MIN: int = 10
STAGE2_ENTRY_FILLS_MIN: int = 30
STAGE2_GROSS_PNL_FLOOR_USDT: float = -5.0
STAGE2_DSR_FLOOR: float = 0.5
STAGE3_ATTRIBUTION_RATIO_FLOOR: float = 0.7
STAGE3_PBO_CEILING: float = 0.5

# Demote thresholds
STAGE2_PNL_DEMOTE_FLOOR_USDT: float = -10.0
STAGE3_PNL_DEMOTE_FLOOR_USDT: float = -20.0
STAGE3_ATTRIBUTION_DEMOTE_FLOOR: float = 0.3


# ---------------------------------------------------------------------------
# Inputs / Outputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CanaryStageMetrics:
    """Cohort metric snapshot；Rust 端 mirror。

    所有 ts 為 ms epoch（i64 in Rust，Python int）。
    DSR / PBO / attribution_chain_ok_ratio = None → Pending（等下次 cycle）。
    """

    current_ts_ms: int
    stage_entered_at_ms: int
    entry_fills_count: int
    boundary_violation_count: int
    gross_pnl_usdt: float
    dsr: Optional[float] = None
    pbo: Optional[float] = None
    attribution_chain_ok_ratio: Optional[float] = None
    sm04_level: int = 0  # 0=normal, 1..=4 escalating; ≥3 強制 demote

    def wall_clock_elapsed_ms(self) -> int:
        """Wall-clock elapsed (ms)；負值 clamp 至 0（防 clock skew race）。"""
        return max(0, self.current_ts_ms - self.stage_entered_at_ms)


class PromoteVerdict(Enum):
    """Stage promotion 判定結果；Rust 端 mirror。"""

    PROMOTE = "promote"
    PENDING = "pending"
    FAIL = "fail"
    PENDING_OPERATOR = "pending_operator"
    READY_FOR_OPERATOR_REVIEW = "ready_for_operator_review"


class RollbackVerdict(Enum):
    """Stage rollback 判定結果；Rust 端 mirror。"""

    STABLE = "stable"
    DEMOTE = "demote"


# ---------------------------------------------------------------------------
# 核心 API
# ---------------------------------------------------------------------------


def evaluate_promote_criteria(
    stage: int,
    metrics: CanaryStageMetrics,
) -> Tuple[PromoteVerdict, str]:
    """W5-E1-A spec §7.2 — 對 (stage, metrics) 評估 promote eligibility。

    Args:
        stage: 當前 canary stage (0..=4)
        metrics: cohort metric snapshot

    Returns:
        (verdict, reason) — verdict 為 PromoteVerdict enum，reason 為人讀說明
        （GUI surface 顯示 + healthcheck msg 用）
    """
    if stage == 0:
        return (
            PromoteVerdict.PENDING_OPERATOR,
            "Stage 0 fail-closed default; operator must Settings tab toggle to Stage 1 "
            "(spec §1 + AMD §2.2)",
        )
    if stage == 1:
        return _evaluate_stage1_promote(metrics)
    if stage == 2:
        return _evaluate_stage2_promote(metrics)
    if stage == 3:
        return _evaluate_stage3_promote(metrics)
    if stage == 4:
        return (
            PromoteVerdict.PENDING_OPERATOR,
            "Stage 4 LIVE_PENDING; no auto-promote (spec §4 + AMD §2.2 — operator + "
            "signed authorization + Decision Lease + 5-gate live boundary required)",
        )
    return (
        PromoteVerdict.PENDING,
        f"unknown stage={stage}; expected 0..=4 — fail-soft Pending",
    )


def _evaluate_stage1_promote(
    metrics: CanaryStageMetrics,
) -> Tuple[PromoteVerdict, str]:
    """Stage 1→2 promote eval（per spec §2.1）。"""
    elapsed = metrics.wall_clock_elapsed_ms()

    # 14d 仍 entry_fills < 10 = Fail（spec §2.5 stage_1_starvation）
    if (
        elapsed >= 14 * 24 * 60 * 60 * 1000
        and metrics.entry_fills_count < STAGE1_ENTRY_FILLS_MIN
    ):
        return (
            PromoteVerdict.FAIL,
            f"Stage 1 starvation: entry_fills={metrics.entry_fills_count}<{STAGE1_ENTRY_FILLS_MIN} "
            f"after wall_clock={elapsed}ms (>14d); operator review required (spec §2.5)",
        )

    # boundary trip → promote 路徑直接 reject
    if metrics.boundary_violation_count > 0:
        return (
            PromoteVerdict.PENDING,
            f"boundary_violation_count={metrics.boundary_violation_count}>0; "
            "rollback path active (spec §2.4)",
        )

    if elapsed < STAGE1_WALL_CLOCK_MS:
        return (
            PromoteVerdict.PENDING,
            f"wall_clock={elapsed}ms<7d; need {STAGE1_WALL_CLOCK_MS - elapsed} more ms "
            "(spec §2.1)",
        )

    if elapsed < STAGE1_SAMPLE_FLOOR_MS:
        return (
            PromoteVerdict.PENDING,
            "stage_entered <72h; sample_floor not met (spec §2.3)",
        )

    if metrics.entry_fills_count < STAGE1_ENTRY_FILLS_MIN:
        return (
            PromoteVerdict.PENDING,
            f"entry_fills={metrics.entry_fills_count}<{STAGE1_ENTRY_FILLS_MIN}; "
            "need more cohort fills (spec §2.1)",
        )

    return (PromoteVerdict.PROMOTE, "Stage 1 → 2 all criteria met (spec §2.1)")


def _evaluate_stage2_promote(
    metrics: CanaryStageMetrics,
) -> Tuple[PromoteVerdict, str]:
    """Stage 2→3 promote eval（per spec §3）。"""
    elapsed = metrics.wall_clock_elapsed_ms()

    # 28d 仍未達升級條件 = Fail
    if elapsed >= 28 * 24 * 60 * 60 * 1000 and (
        metrics.entry_fills_count < STAGE2_ENTRY_FILLS_MIN
        or metrics.gross_pnl_usdt <= STAGE2_GROSS_PNL_FLOOR_USDT
    ):
        return (
            PromoteVerdict.FAIL,
            f"Stage 2 starvation: entry_fills={metrics.entry_fills_count} "
            f"gross_pnl={metrics.gross_pnl_usdt} after wall_clock={elapsed}ms (>28d); "
            "operator review required (spec §3)",
        )

    if metrics.boundary_violation_count > 0:
        return (
            PromoteVerdict.PENDING,
            f"boundary_violation_count={metrics.boundary_violation_count}>0; "
            "rollback path active (spec §3)",
        )

    if elapsed < STAGE2_WALL_CLOCK_MS:
        return (
            PromoteVerdict.PENDING,
            f"wall_clock={elapsed}ms<14d; need {STAGE2_WALL_CLOCK_MS - elapsed} more ms "
            "(spec §3)",
        )

    if elapsed < STAGE2_SAMPLE_FLOOR_MS:
        return (
            PromoteVerdict.PENDING,
            "stage_entered <168h(7d); sample_floor not met (spec §3)",
        )

    if metrics.entry_fills_count < STAGE2_ENTRY_FILLS_MIN:
        return (
            PromoteVerdict.PENDING,
            f"entry_fills={metrics.entry_fills_count}<{STAGE2_ENTRY_FILLS_MIN}; "
            "need more cohort fills (spec §3)",
        )

    if metrics.gross_pnl_usdt <= STAGE2_GROSS_PNL_FLOOR_USDT:
        return (
            PromoteVerdict.PENDING,
            f"gross_pnl={metrics.gross_pnl_usdt}USDT<={STAGE2_GROSS_PNL_FLOOR_USDT}USDT "
            "(spec §3 floor)",
        )

    if metrics.dsr is None:
        return (
            PromoteVerdict.PENDING,
            "DSR=None; W-AUDIT-6 pipeline not yet computed (spec §3 PROMOTE PENDING)",
        )

    if metrics.dsr <= STAGE2_DSR_FLOOR:
        return (
            PromoteVerdict.PENDING,
            f"DSR={metrics.dsr}<={STAGE2_DSR_FLOOR} (spec §3 floor)",
        )

    return (PromoteVerdict.PROMOTE, "Stage 2 → 3 all criteria met (spec §3)")


def _evaluate_stage3_promote(
    metrics: CanaryStageMetrics,
) -> Tuple[PromoteVerdict, str]:
    """Stage 3→4 promote eval（per spec §4）。

    spec §4 明示 Stage 4 不 auto-promote — 全條件達成後回 ReadyForOperatorReview。
    """
    elapsed = metrics.wall_clock_elapsed_ms()

    if metrics.boundary_violation_count > 0:
        return (
            PromoteVerdict.PENDING,
            f"boundary_violation_count={metrics.boundary_violation_count}>0; "
            "rollback path active (spec §4)",
        )

    if elapsed < STAGE3_WALL_CLOCK_MS:
        return (
            PromoteVerdict.PENDING,
            f"wall_clock={elapsed}ms<21d; need {STAGE3_WALL_CLOCK_MS - elapsed} more ms "
            "(spec §4)",
        )

    if metrics.gross_pnl_usdt <= 0.0:
        return (
            PromoteVerdict.PENDING,
            f"gross_pnl={metrics.gross_pnl_usdt}USDT<=0 (spec §4 must be strictly positive)",
        )

    if metrics.dsr is None:
        return (
            PromoteVerdict.PENDING,
            "DSR=None; W-AUDIT-6 pipeline not yet computed (spec §4 PASS required)",
        )

    if metrics.dsr <= 0.0:
        return (
            PromoteVerdict.PENDING,
            f"DSR={metrics.dsr}<=0; spec §4 requires DSR PASS",
        )

    if metrics.pbo is None:
        return (
            PromoteVerdict.PENDING,
            "PBO=None; W-AUDIT-6 pipeline not yet computed (spec §4)",
        )

    if metrics.pbo > STAGE3_PBO_CEILING:
        return (
            PromoteVerdict.PENDING,
            f"PBO={metrics.pbo}>{STAGE3_PBO_CEILING} (spec §4 ceiling)",
        )

    if metrics.attribution_chain_ok_ratio is None:
        return (
            PromoteVerdict.PENDING,
            "attribution_chain_ok_ratio=None; [55] healthcheck not yet computed (spec §4)",
        )

    if metrics.attribution_chain_ok_ratio < STAGE3_ATTRIBUTION_RATIO_FLOOR:
        return (
            PromoteVerdict.PENDING,
            f"attribution_chain_ok_ratio={metrics.attribution_chain_ok_ratio}<"
            f"{STAGE3_ATTRIBUTION_RATIO_FLOOR} (spec §4 floor)",
        )

    return (
        PromoteVerdict.READY_FOR_OPERATOR_REVIEW,
        f"Stage 3→4 all criteria met (wall_clock={elapsed}ms gross_pnl={metrics.gross_pnl_usdt}USDT "
        f"DSR={metrics.dsr} PBO={metrics.pbo} attribution_chain_ok={metrics.attribution_chain_ok_ratio}); "
        "GUI surface 'ready_for_stage_4_review' awaiting operator + signed authorization + "
        "Decision Lease + 5-gate live boundary (spec §4 + AMD §2.2)",
    )


def evaluate_rollback_criteria(
    stage: int,
    metrics: CanaryStageMetrics,
) -> Tuple[RollbackVerdict, str, Optional[int]]:
    """W5-E1-A spec §7.2 — 對 (stage, metrics) 評估是否 demote。

    per spec §5 表：每 stage 列舉 OR-trigger，任一 trip 即 fall back 1 stage（Stage 4 直回 0）。

    Args:
        stage: 當前 canary stage (0..=4)
        metrics: cohort metric snapshot

    Returns:
        (verdict, reason, target_stage) — verdict 為 RollbackVerdict enum；
        target_stage = 必 demote 至的 stage int（STABLE 時 None）
    """
    # SM-04 ≥ L3 跨 stage hard demote 至 Stage 0（per AMD §3.2 + spec §2.4 第 3 條）
    if metrics.sm04_level >= 3:
        return (
            RollbackVerdict.DEMOTE,
            f"SM-04 escalate level={metrics.sm04_level}>=3; demote across all cohorts to "
            "Stage 0 (AMD §3.2 + spec §2.4)",
            0,
        )

    if stage == 0:
        return (RollbackVerdict.STABLE, "Stage 0 already at fail-closed default", None)
    if stage == 1:
        return _evaluate_stage1_rollback(metrics)
    if stage == 2:
        return _evaluate_stage2_rollback(metrics)
    if stage == 3:
        return _evaluate_stage3_rollback(metrics)
    if stage == 4:
        return _evaluate_stage4_rollback(metrics)
    return (
        RollbackVerdict.STABLE,
        f"unknown stage={stage}; expected 0..=4 — fail-soft Stable",
        None,
    )


def _evaluate_stage1_rollback(
    metrics: CanaryStageMetrics,
) -> Tuple[RollbackVerdict, str, Optional[int]]:
    """Stage 1→0 rollback eval（per spec §5 第 1 列）。"""
    if metrics.boundary_violation_count > 0:
        return (
            RollbackVerdict.DEMOTE,
            f"boundary_violation_count={metrics.boundary_violation_count}>0; "
            "demote Stage 1→0 (spec §5)",
            0,
        )
    return (RollbackVerdict.STABLE, "Stage 1 metrics within bounds", None)


def _evaluate_stage2_rollback(
    metrics: CanaryStageMetrics,
) -> Tuple[RollbackVerdict, str, Optional[int]]:
    """Stage 2→1 rollback eval（per spec §5 第 2 列）。"""
    if metrics.gross_pnl_usdt < STAGE2_PNL_DEMOTE_FLOOR_USDT:
        return (
            RollbackVerdict.DEMOTE,
            f"gross_pnl={metrics.gross_pnl_usdt}USDT<{STAGE2_PNL_DEMOTE_FLOOR_USDT}USDT; "
            "demote Stage 2→1 (spec §5)",
            1,
        )
    if metrics.dsr is not None and metrics.dsr < 0.0:
        return (
            RollbackVerdict.DEMOTE,
            f"DSR={metrics.dsr}<0; demote Stage 2→1 (spec §5)",
            1,
        )
    if metrics.boundary_violation_count > 0:
        return (
            RollbackVerdict.DEMOTE,
            f"boundary_violation_count={metrics.boundary_violation_count}>0; "
            "demote Stage 2→1 (spec §5 — Stage 1 trigger cascading)",
            1,
        )
    return (RollbackVerdict.STABLE, "Stage 2 metrics within bounds", None)


def _evaluate_stage3_rollback(
    metrics: CanaryStageMetrics,
) -> Tuple[RollbackVerdict, str, Optional[int]]:
    """Stage 3→2 rollback eval（per spec §5 第 3 列）。"""
    if metrics.gross_pnl_usdt < STAGE3_PNL_DEMOTE_FLOOR_USDT:
        return (
            RollbackVerdict.DEMOTE,
            f"gross_pnl={metrics.gross_pnl_usdt}USDT<{STAGE3_PNL_DEMOTE_FLOOR_USDT}USDT; "
            "demote Stage 3→2 (spec §5)",
            2,
        )
    if metrics.dsr is not None and metrics.dsr < 0.0:
        return (
            RollbackVerdict.DEMOTE,
            f"DSR={metrics.dsr}<0; demote Stage 3→2 (spec §5)",
            2,
        )
    if (
        metrics.attribution_chain_ok_ratio is not None
        and metrics.attribution_chain_ok_ratio < STAGE3_ATTRIBUTION_DEMOTE_FLOOR
    ):
        return (
            RollbackVerdict.DEMOTE,
            f"attribution_chain_ok_ratio={metrics.attribution_chain_ok_ratio}<"
            f"{STAGE3_ATTRIBUTION_DEMOTE_FLOOR}; demote Stage 3→2 (spec §5)",
            2,
        )
    return (RollbackVerdict.STABLE, "Stage 3 metrics within bounds", None)


def _evaluate_stage4_rollback(
    metrics: CanaryStageMetrics,
) -> Tuple[RollbackVerdict, str, Optional[int]]:
    """Stage 4→0 rollback eval（per spec §5 第 4 列；任一 boundary 失敗 = Stage 0）。"""
    if metrics.boundary_violation_count > 0:
        return (
            RollbackVerdict.DEMOTE,
            f"boundary_violation_count={metrics.boundary_violation_count}>0; "
            "Stage 4 cancel_token shutdown — demote 4→0 (spec §5)",
            0,
        )
    return (RollbackVerdict.STABLE, "Stage 4 metrics within bounds", None)
