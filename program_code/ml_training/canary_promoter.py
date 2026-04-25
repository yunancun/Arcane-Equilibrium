"""Canary auto-promote evaluator (G4-03 Phase A, 2026-04-25).
Canary 自動晉升評估器（G4-03 Phase A）。

MODULE_NOTE (EN): Phase A scaffolding for the auto-promote cron deferred
  by INFRA-PREBUILD-1 Part B (canary draft 2026-04-23). Reads
  `learning.model_registry` rows in `canary_status='shadow'` or
  `'promoting'`, applies the eligibility gates from the draft, and
  EITHER prints a Hold/Promote/Retire decision (dry_run) OR calls the
  existing `model_registry.transition_canary_status` state machine.

  DEFAULT-OFF: behind env var `OPENCLAW_AUTO_PROMOTE_ENABLED=1`. Operator
  must explicitly opt in. `dry_run=True` bypasses the env gate so the
  operator can preview decisions safely without touching DB rows.

  Threshold values are PLACEHOLDERS from the draft (60% / 500 obs / 7d).
  Real numbers come from Phase 2 dry-run data when shadow first fires
  on demo. Override via `CanaryThresholds(...)` constructor.

  Wiring: not auto-scheduled. Use `helper_scripts/db/canary_promote_runner.py`
  for manual / cron invocation. Phase B (cron + alert channel + per-strategy
  override YAML) deferred to Phase 4 second-half per draft §Auto-promote cron.

MODULE_NOTE (中): G4-03 Phase A 框架；INFRA-PREBUILD-1 Part B 延後的
  auto-promote cron 落地。掃 `learning.model_registry` 中
  shadow/promoting rows，套用 draft §Phase-gated promotion criteria 的
  eligibility gate，回 `Hold | Promote | Retire` 決策；dry_run=True 預覽，
  否則呼叫 `transition_canary_status` 推進狀態機。預設 disabled，operator
  需設 `OPENCLAW_AUTO_PROMOTE_ENABLED=1` opt-in。閾值為 draft 占位值，
  Phase 2 dry-run 後再校準。

Spec:
  docs/references/2026-04-23--model_canary_promotion_rules_draft.md
  program_code/ml_training/model_registry.py (transition_canary_status)
  sql/migrations/V023__model_registry.sql (state machine CHECK)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, List, Optional, Tuple

from program_code.ml_training.model_registry import (
    CANARY_PROMOTING,
    CANARY_PRODUCTION,
    CANARY_REJECTED,
    CANARY_SHADOW,
    VERDICT_NO_SHIP,
    VERDICT_SHADOW_ONLY,
    VERDICT_SHOULD_SHIP,
    transition_canary_status,
)

logger = logging.getLogger(__name__)


class CanaryDecision(str, Enum):
    """Evaluator decision per registry row.
    每筆 registry row 的決策結果。
    """
    HOLD = "hold"  # criteria not yet met; leave row alone
    PROMOTE = "promote"  # criteria met for next state transition
    RETIRE = "retire"  # criteria failed → reject


@dataclass(frozen=True)
class CanaryThresholds:
    """Eligibility gate thresholds — draft placeholders.
    閾值（draft 占位值，Phase 2 dry-run 後校準）。
    """
    # shadow → promoting
    shadow_min_age_days: float = 1.0  # row must be ≥1d old (operator review window)
    shadow_min_training_samples: int = 200  # hard minimum from quantile_reports.py
    shadow_eligible_verdicts: Tuple[str, ...] = (VERDICT_SHOULD_SHIP, VERDICT_SHADOW_ONLY)

    # promoting → production
    promoting_min_observations: int = 500  # decision_shadow_exits row count
    promoting_min_age_days: float = 7.0  # ≥7 consecutive days of shadow data
    promoting_min_agreement_pct: float = 0.60  # 60% threshold from draft

    # any → rejected (auto-retire trigger)
    promoting_max_disagreement_window_days: float = 3.0
    promoting_min_agreement_pct_strict: float = 0.40  # <40% after 3d → reject

    @classmethod
    def from_env(cls) -> "CanaryThresholds":
        """Read overrides from env vars (e.g. OPENCLAW_CANARY_SHADOW_MIN_AGE_DAYS).
        從 env 讀覆寫值；缺失則用預設。
        """
        def _f(name: str, default: float) -> float:
            v = os.environ.get(name)
            try:
                return float(v) if v else default
            except (TypeError, ValueError):
                return default
        def _i(name: str, default: int) -> int:
            v = os.environ.get(name)
            try:
                return int(v) if v else default
            except (TypeError, ValueError):
                return default
        return cls(
            shadow_min_age_days=_f("OPENCLAW_CANARY_SHADOW_MIN_AGE_DAYS", cls.shadow_min_age_days),
            shadow_min_training_samples=_i(
                "OPENCLAW_CANARY_SHADOW_MIN_SAMPLES", cls.shadow_min_training_samples
            ),
            promoting_min_observations=_i(
                "OPENCLAW_CANARY_PROMOTING_MIN_OBS", cls.promoting_min_observations
            ),
            promoting_min_age_days=_f(
                "OPENCLAW_CANARY_PROMOTING_MIN_AGE_DAYS", cls.promoting_min_age_days
            ),
            promoting_min_agreement_pct=_f(
                "OPENCLAW_CANARY_PROMOTING_MIN_AGREEMENT", cls.promoting_min_agreement_pct
            ),
        )


@dataclass
class EvaluationResult:
    """Per-row decision + audit trail.
    每筆 row 的決策 + 推理理由。
    """
    row_id: int
    strategy: str
    engine_mode: str
    quantile: str
    current_status: str
    decision: CanaryDecision
    target_status: Optional[str]  # None for HOLD
    reasons: List[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def is_auto_promote_enabled() -> bool:
    """Default-OFF env gate. Operator must explicitly opt in.
    預設關，operator 需 opt-in。
    """
    return os.environ.get("OPENCLAW_AUTO_PROMOTE_ENABLED", "").strip() in ("1", "true", "yes")


def _query_shadow_observations(
    cur,
    *,
    strategy: str,
    engine_mode: str,
    since_ts: datetime,
) -> Tuple[int, int]:
    """Return (total_observations, agreed_count) from learning.decision_shadow_exits.
    回 (總觀測數, agree 數) — agreement_pct = agreed / total。
    """
    cur.execute(
        """
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE disagreed = FALSE) AS agreed
        FROM learning.decision_shadow_exits
        WHERE strategy_name = %s
          AND engine_mode = %s
          AND ts >= %s
        """,
        (strategy, engine_mode, since_ts),
    )
    row = cur.fetchone()
    if row is None:
        return (0, 0)
    return (int(row[0] or 0), int(row[1] or 0))


def evaluate_canary_eligibility(
    row: dict,
    cur,
    thresholds: CanaryThresholds,
    now: datetime,
) -> EvaluationResult:
    """Evaluate a single registry row against the gate.
    對單筆 registry row 套用 eligibility gate。

    `row` is a dict with keys: id, strategy, engine_mode, quantile,
    canary_status, verdict, train_date, training_sample_size, created_at.
    """
    rid = int(row["id"])
    strategy = str(row["strategy"])
    engine_mode = str(row["engine_mode"])
    quantile = str(row["quantile"])
    current = str(row["canary_status"])
    verdict = str(row.get("verdict") or "")
    train_date = row.get("train_date")
    sample_size = int(row.get("training_sample_size") or 0)
    created_at = row.get("created_at")

    res = EvaluationResult(
        row_id=rid,
        strategy=strategy,
        engine_mode=engine_mode,
        quantile=quantile,
        current_status=current,
        decision=CanaryDecision.HOLD,
        target_status=None,
        metrics={"verdict": verdict, "training_sample_size": sample_size},
    )

    # Terminal states: no-op.
    # 終態：跳過。
    if current in (CANARY_PRODUCTION, CANARY_REJECTED, "retired"):
        res.reasons.append(f"current_status={current!r} is terminal/no-op")
        return res

    if current == CANARY_SHADOW:
        # shadow → promoting eligibility (draft §Phase 2 shadow → promoting).
        # shadow → promoting 入門檻。
        if verdict not in thresholds.shadow_eligible_verdicts:
            res.reasons.append(
                f"verdict={verdict!r} not in eligible set "
                f"{thresholds.shadow_eligible_verdicts}"
            )
            return res
        if sample_size < thresholds.shadow_min_training_samples:
            res.reasons.append(
                f"training_sample_size={sample_size} < min "
                f"{thresholds.shadow_min_training_samples}"
            )
            return res
        # row age check (draft: ≥1 day to allow operator review of acceptance_report)
        if isinstance(created_at, datetime):
            age_days = (now - created_at).total_seconds() / 86400.0
            res.metrics["age_days"] = round(age_days, 3)
            if age_days < thresholds.shadow_min_age_days:
                res.reasons.append(
                    f"row age {age_days:.2f}d < min {thresholds.shadow_min_age_days}d"
                )
                return res
        else:
            res.reasons.append("created_at unavailable; cannot enforce age gate")
            return res

        res.decision = CanaryDecision.PROMOTE
        res.target_status = CANARY_PROMOTING
        res.reasons.append(
            f"shadow eligible: verdict={verdict}, samples={sample_size}, "
            f"age={res.metrics.get('age_days')}d"
        )
        return res

    if current == CANARY_PROMOTING:
        # promoting → production OR promoting → rejected based on agreement window.
        # 依 agreement 視窗決定升級或拒絕。
        if not isinstance(created_at, datetime):
            res.reasons.append("created_at unavailable; cannot enforce promoting gates")
            return res
        age_days = (now - created_at).total_seconds() / 86400.0
        res.metrics["age_days"] = round(age_days, 3)

        # Reject branch: agreement collapse in early window.
        # 拒絕分支：早期視窗 agreement 崩。
        if age_days >= thresholds.promoting_max_disagreement_window_days:
            since_3d = now - timedelta(days=thresholds.promoting_max_disagreement_window_days)
            total_3d, agreed_3d = _query_shadow_observations(
                cur, strategy=strategy, engine_mode=engine_mode, since_ts=since_3d
            )
            if total_3d > 0:
                agreement_3d = agreed_3d / total_3d
                res.metrics["agreement_3d"] = round(agreement_3d, 4)
                res.metrics["observations_3d"] = total_3d
                if agreement_3d < thresholds.promoting_min_agreement_pct_strict:
                    res.decision = CanaryDecision.RETIRE
                    res.target_status = CANARY_REJECTED
                    res.reasons.append(
                        f"3d agreement {agreement_3d:.2%} < strict floor "
                        f"{thresholds.promoting_min_agreement_pct_strict:.0%} "
                        f"(n={total_3d}); auto-reject"
                    )
                    return res

        # Promote branch: full window thresholds met.
        if age_days < thresholds.promoting_min_age_days:
            res.reasons.append(
                f"promoting age {age_days:.2f}d < min "
                f"{thresholds.promoting_min_age_days}d"
            )
            return res
        since_full = now - timedelta(days=thresholds.promoting_min_age_days)
        total, agreed = _query_shadow_observations(
            cur, strategy=strategy, engine_mode=engine_mode, since_ts=since_full
        )
        res.metrics["observations_full_window"] = total
        if total < thresholds.promoting_min_observations:
            res.reasons.append(
                f"observations {total} < min "
                f"{thresholds.promoting_min_observations}"
            )
            return res
        agreement = agreed / total if total > 0 else 0.0
        res.metrics["agreement_full_window"] = round(agreement, 4)
        if agreement < thresholds.promoting_min_agreement_pct:
            res.reasons.append(
                f"agreement {agreement:.2%} < min "
                f"{thresholds.promoting_min_agreement_pct:.0%}"
            )
            return res

        res.decision = CanaryDecision.PROMOTE
        res.target_status = CANARY_PRODUCTION
        res.reasons.append(
            f"promoting eligible: agreement={agreement:.2%}, n={total}, "
            f"age={age_days:.2f}d"
        )
        return res

    # Unknown status → no-op.
    res.reasons.append(f"unknown current_status={current!r}; no-op")
    return res


def _apply_transition(result: EvaluationResult, dsn: Optional[str] = None) -> bool:
    """Call transition_canary_status with retirement_reason for retire/reject paths.
    呼叫狀態機；retire/reject 帶 retirement_reason。
    """
    if result.decision is CanaryDecision.HOLD or result.target_status is None:
        return False
    reason = "; ".join(result.reasons) if result.decision is CanaryDecision.RETIRE else None
    return transition_canary_status(
        row_id=result.row_id,
        to_status=result.target_status,
        retirement_reason=reason,
        dsn=dsn,
    )


def auto_promote_eligible_models(
    *,
    dsn: Optional[str] = None,
    thresholds: Optional[CanaryThresholds] = None,
    dry_run: bool = True,
    now: Optional[datetime] = None,
) -> List[EvaluationResult]:
    """Scan registry, evaluate every shadow/promoting row, optionally apply.
    掃 registry，評估每筆 shadow/promoting row，可選擇套用。

    `dry_run=True` (default) bypasses the env gate so operators can preview
    decisions safely. `dry_run=False` requires `is_auto_promote_enabled()`
    OR explicit env var; otherwise no transitions are applied (still returns
    the evaluation list for visibility).

    dry_run=True 預設，bypass env gate；dry_run=False 需 is_auto_promote_enabled()
    才實際呼叫狀態機。
    """
    if thresholds is None:
        thresholds = CanaryThresholds.from_env()
    if now is None:
        now = datetime.now(timezone.utc)

    # Lazy import to keep psycopg dep optional during pytest collection.
    # 延遲 import 讓 pytest 採集階段不依賴 psycopg。
    from program_code.ml_training.model_registry import _connect

    conn = _connect(dsn)
    if conn is None:
        logger.warning("auto_promote_eligible_models: DB unavailable; returning empty")
        return []

    out: List[EvaluationResult] = []
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, strategy, engine_mode, quantile, canary_status, verdict,
                       train_date, training_sample_size, created_at
                FROM learning.model_registry
                WHERE canary_status IN (%s, %s)
                ORDER BY id ASC
                """,
                (CANARY_SHADOW, CANARY_PROMOTING),
            )
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            for row in rows:
                result = evaluate_canary_eligibility(row, cur, thresholds, now)
                out.append(result)
                if dry_run:
                    continue
                if not is_auto_promote_enabled():
                    logger.info(
                        "auto_promote: env gate not set; skipping apply for row_id=%d",
                        result.row_id,
                    )
                    continue
                if result.decision is CanaryDecision.HOLD:
                    continue
                ok = _apply_transition(result, dsn=dsn)
                logger.info(
                    "auto_promote: row_id=%d %s → %s applied=%s",
                    result.row_id, result.current_status,
                    result.target_status, ok,
                )
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass

    return out
