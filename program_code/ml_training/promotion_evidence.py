"""Promotion evidence producer for DSR/PBO and portfolio tail risk.

P0-V2-NEW-3 wires the already-live promotion gates to the hourly edge-estimator
cycle. The module is intentionally side-effect controlled:

* build evidence from real James-Stein/realized-edge return series;
* update an injected PromotionGate when one is supplied;
* persist trial-ledger/report rows only when a DB connection and V079 schema
  are available.

No trading parameter, auth, order, or live-mode mutation is performed here.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Protocol, Sequence

import numpy as np

logger = logging.getLogger(__name__)


class PromotionGateLike(Protocol):
    """Narrow protocol needed from app.promotion_pipeline.PromotionGate."""

    def register_strategy(self, strategy_name: str, *args: Any, **kwargs: Any) -> Any:
        ...

    def update_demo_selection_bias_evidence(
        self,
        strategy_name: str,
        *,
        observed_sharpe: float,
        n_trials: int,
        n_observations: int,
        candidate_oos_returns: Optional[Sequence[Sequence[float]]] = None,
        trial_sharpes: Optional[Sequence[float]] = None,
    ) -> tuple[bool, dict]:
        ...

    def update_demo_tail_risk_evidence(
        self,
        strategy_name: str,
        *,
        portfolio_returns: Sequence[float],
        stress_exposures: Optional[dict[str, float]] = None,
        **kwargs: Any,
    ) -> tuple[bool, dict]:
        ...


@dataclass(frozen=True)
class CandidateEvidence:
    """One strategy candidate/cell used for PBO/CSCV evidence."""

    candidate_key: str
    returns: tuple[float, ...]
    sharpe: float
    n_observations: int
    mean_return: float


@dataclass(frozen=True)
class StrategyPromotionEvidence:
    """All promotion evidence inputs for one strategy and engine mode."""

    strategy_name: str
    engine_mode: str
    observed_sharpe: float
    n_trials: int
    n_observations: int
    trial_sharpes: tuple[float, ...]
    candidate_oos_returns: tuple[tuple[float, ...], ...]
    portfolio_returns: tuple[float, ...]
    candidates: tuple[CandidateEvidence, ...]


def _safe_float(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def _return_series_from_bps(raw_bps_series: Any) -> tuple[float, ...]:
    if raw_bps_series is None:
        return tuple()
    if not isinstance(raw_bps_series, (list, tuple)):
        return tuple()
    out: list[float] = []
    for item in raw_bps_series:
        bps = _safe_float(item)
        if bps is not None:
            out.append(bps / 10_000.0)
    return tuple(out)


def _sharpe(returns: Sequence[float]) -> float:
    arr = np.asarray(list(returns), dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    if arr.size < 2:
        return 0.0
    sigma = float(np.std(arr, ddof=1))
    if sigma <= 0.0 or not math.isfinite(sigma):
        return 0.0
    return float(np.mean(arr) / sigma)


def _row_strategy_symbol(key: Any, row: Mapping[str, Any]) -> tuple[str, str]:
    strategy = str(row.get("strategy_name") or "").strip()
    symbol = str(row.get("symbol") or "").strip()
    if (not strategy or not symbol) and isinstance(key, tuple) and len(key) >= 2:
        strategy = strategy or str(key[0])
        symbol = symbol or str(key[1])
    return strategy, symbol


def build_strategy_promotion_evidence(
    js_results: Mapping[Any, Mapping[str, Any]],
    *,
    engine_mode: str,
    min_candidate_observations: int = 2,
) -> dict[str, StrategyPromotionEvidence]:
    """Build DSR/PBO/tail-risk inputs from real James-Stein cycle results."""
    grouped: dict[str, list[CandidateEvidence]] = {}
    for key, row in js_results.items():
        if not isinstance(row, Mapping):
            continue
        if row.get("_proxy_from"):
            continue
        strategy, symbol = _row_strategy_symbol(key, row)
        if not strategy or not symbol:
            continue
        returns = _return_series_from_bps(row.get("raw_bps_series"))
        if len(returns) < min_candidate_observations:
            continue
        candidate = CandidateEvidence(
            candidate_key=symbol,
            returns=returns,
            sharpe=_sharpe(returns),
            n_observations=len(returns),
            mean_return=float(np.mean(returns)),
        )
        grouped.setdefault(strategy, []).append(candidate)

    snapshots: dict[str, StrategyPromotionEvidence] = {}
    for strategy, candidates in grouped.items():
        all_returns: list[float] = []
        for candidate in candidates:
            all_returns.extend(candidate.returns)
        if len(all_returns) < 2:
            continue
        trial_sharpes = tuple(candidate.sharpe for candidate in candidates)
        snapshots[strategy] = StrategyPromotionEvidence(
            strategy_name=strategy,
            engine_mode=engine_mode,
            observed_sharpe=_sharpe(all_returns),
            n_trials=max(1, len(trial_sharpes)),
            n_observations=len(all_returns),
            trial_sharpes=trial_sharpes,
            candidate_oos_returns=tuple(candidate.returns for candidate in candidates),
            portfolio_returns=tuple(all_returns),
            candidates=tuple(candidates),
        )
    return snapshots


def _selection_report_without_gate(
    evidence: StrategyPromotionEvidence,
) -> tuple[bool, dict[str, Any]]:
    try:
        from program_code.learning_engine.promotion_gate import (
            SelectionBiasPromotionGate,
        )
    except ModuleNotFoundError:
        from learning_engine.promotion_gate import SelectionBiasPromotionGate  # type: ignore

    try:
        result = SelectionBiasPromotionGate().evaluate(
            observed_sharpe=evidence.observed_sharpe,
            n_trials=evidence.n_trials,
            n_observations=evidence.n_observations,
            candidate_oos_returns=evidence.candidate_oos_returns,
            trial_sharpes=evidence.trial_sharpes,
        )
        report = result.to_dict()
    except Exception as exc:  # noqa: BLE001 - promotion evidence is fail-closed.
        report = {
            "verdict": "block",
            "passes": False,
            "reasons": [f"selection_bias_invalid:{exc}"],
            "dsr": None,
            "dsr_verdict": "block",
            "pbo": None,
            "pbo_verdict": "missing_cpcv_returns",
            "cpcv_protocol": "cscv",
        }
    return bool(report.get("passes")), report


def _tail_report_without_gate(
    evidence: StrategyPromotionEvidence,
    *,
    stress_exposures: Optional[Mapping[str, float]],
    n_bootstrap: int,
    seed: Optional[int],
) -> tuple[bool, dict[str, Any]]:
    try:
        from program_code.learning_engine.portfolio_var import (
            PortfolioTailRiskGate,
            PortfolioTailRiskLimits,
        )
    except ModuleNotFoundError:
        from learning_engine.portfolio_var import (  # type: ignore
            PortfolioTailRiskGate,
            PortfolioTailRiskLimits,
        )

    try:
        result = PortfolioTailRiskGate(PortfolioTailRiskLimits()).evaluate(
            evidence.portfolio_returns,
            stress_exposures=stress_exposures,
            n_bootstrap=n_bootstrap,
            seed=seed,
        )
        report = result.to_dict()
    except Exception as exc:  # noqa: BLE001 - promotion evidence is fail-closed.
        report = {
            "verdict": "block",
            "passes": False,
            "reasons": [f"tail_risk_invalid:{exc}"],
        }
    return bool(report.get("passes")), report


def _connect_dsn(dsn: str):
    import psycopg2  # type: ignore[import]

    return psycopg2.connect(dsn)


def _has_table(cur: Any, regclass_name: str) -> bool:
    cur.execute("SELECT to_regclass(%s) IS NOT NULL", (regclass_name,))
    row = cur.fetchone()
    return bool(row and row[0])


def _has_columns(cur: Any, table_schema: str, table_name: str, columns: Sequence[str]) -> bool:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
          AND column_name = ANY(%s)
        """,
        (table_schema, table_name, list(columns)),
    )
    present = {str(row[0]) for row in cur.fetchall()}
    return set(columns).issubset(present)


def _merge_trial_sharpes_from_ledger(
    cur: Any,
    evidence: StrategyPromotionEvidence,
    *,
    limit: int = 64,
) -> tuple[float, ...]:
    if not _has_table(cur, "learning.strategy_trial_ledger"):
        return evidence.trial_sharpes
    cur.execute(
        """
        SELECT observed_sharpe::float8
        FROM learning.strategy_trial_ledger
        WHERE strategy_name = %s
          AND engine_mode = %s
          AND observed_sharpe IS NOT NULL
        ORDER BY ts DESC, trial_id DESC
        LIMIT %s
        """,
        (evidence.strategy_name, evidence.engine_mode, int(limit)),
    )
    persisted = [
        float(row[0])
        for row in cur.fetchall()
        if row and _safe_float(row[0]) is not None
    ]
    merged: list[float] = []
    for value in list(evidence.trial_sharpes) + persisted:
        if math.isfinite(float(value)):
            merged.append(float(value))
    return tuple(merged[:limit])


def _persist_trial_ledger(
    cur: Any,
    evidence: StrategyPromotionEvidence,
    *,
    source: str,
) -> int:
    if not _has_table(cur, "learning.strategy_trial_ledger"):
        return 0
    rows = []
    for candidate in evidence.candidates:
        rows.append(
            (
                evidence.strategy_name,
                evidence.engine_mode,
                "edge_estimator_cycle",
                candidate.candidate_key,
                candidate.sharpe,
                candidate.n_observations,
                candidate.mean_return,
                source,
                json.dumps(
                    {
                        "return_unit": "fractional_return",
                        "source": source,
                        "n_trials_in_cycle": evidence.n_trials,
                    }
                ),
            )
        )
    if not rows:
        return 0
    cur.executemany(
        """
        INSERT INTO learning.strategy_trial_ledger
            (strategy_name, engine_mode, trial_family, candidate_key,
             observed_sharpe, n_observations, mean_return, source, evidence)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        """,
        rows,
    )
    return len(rows)


def _persist_promotion_reports(
    cur: Any,
    evidence: StrategyPromotionEvidence,
    *,
    selection_report: Mapping[str, Any],
    tail_report: Mapping[str, Any],
) -> bool:
    if not _has_table(cur, "learning.promotion_pipeline"):
        return False
    if not _has_columns(
        cur,
        "learning",
        "promotion_pipeline",
        ("demo_selection_bias_report", "demo_tail_risk_report"),
    ):
        return False

    cur.execute(
        """
        SELECT pipeline_id
        FROM learning.promotion_pipeline
        WHERE strategy_name = %s
        ORDER BY updated_ts DESC, pipeline_id DESC
        LIMIT 1
        """,
        (evidence.strategy_name,),
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            """
            UPDATE learning.promotion_pipeline
            SET demo_selection_bias_report = %s::jsonb,
                demo_tail_risk_report = %s::jsonb,
                updated_ts = NOW()
            WHERE pipeline_id = %s
            """,
            (
                json.dumps(selection_report),
                json.dumps(tail_report),
                row[0],
            ),
        )
        return True

    cur.execute(
        """
        INSERT INTO learning.promotion_pipeline
            (strategy_name, current_stage, demo_selection_bias_report,
             demo_tail_risk_report, updated_ts)
        VALUES (%s, 'LEARNING', %s::jsonb, %s::jsonb, NOW())
        """,
        (
            evidence.strategy_name,
            json.dumps(selection_report),
            json.dumps(tail_report),
        ),
    )
    return True


def push_promotion_evidence_from_js_results(
    js_results: Mapping[Any, Mapping[str, Any]],
    *,
    engine_mode: str,
    gate: Optional[PromotionGateLike] = None,
    dsn: Optional[str] = None,
    stress_exposures_by_strategy: Optional[Mapping[str, Mapping[str, float]]] = None,
    source: str = "edge_estimator_scheduler",
    n_bootstrap: int = 240,
    seed: Optional[int] = 20260509,
) -> dict[str, Any]:
    """Push promotion evidence from one JS cycle into gate and optional DB."""
    evidence_by_strategy = build_strategy_promotion_evidence(
        js_results,
        engine_mode=engine_mode,
    )
    if not evidence_by_strategy:
        return {
            "status": "skipped",
            "reason": "no_raw_return_series",
            "engine_mode": engine_mode,
            "strategies": 0,
        }

    conn = None
    if dsn:
        try:
            conn = _connect_dsn(dsn)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "promotion evidence DB connection failed (fail-soft): %s", exc
            )

    details: dict[str, dict[str, Any]] = {}
    ledger_rows = 0
    persisted_reports = 0
    selection_passes = 0
    tail_passes = 0
    try:
        cur = conn.cursor() if conn is not None else None
        for strategy, evidence in evidence_by_strategy.items():
            if cur is not None:
                try:
                    merged_trial_sharpes = _merge_trial_sharpes_from_ledger(cur, evidence)
                    if merged_trial_sharpes != evidence.trial_sharpes:
                        evidence = StrategyPromotionEvidence(
                            strategy_name=evidence.strategy_name,
                            engine_mode=evidence.engine_mode,
                            observed_sharpe=evidence.observed_sharpe,
                            n_trials=max(1, len(merged_trial_sharpes)),
                            n_observations=evidence.n_observations,
                            trial_sharpes=merged_trial_sharpes,
                            candidate_oos_returns=evidence.candidate_oos_returns,
                            portfolio_returns=evidence.portfolio_returns,
                            candidates=evidence.candidates,
                        )
                    ledger_rows += _persist_trial_ledger(cur, evidence, source=source)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "promotion evidence ledger persist failed for %s "
                        "(fail-soft): %s",
                        strategy,
                        exc,
                    )

            stress_exposures = None
            if stress_exposures_by_strategy is not None:
                stress_exposures = (
                    stress_exposures_by_strategy.get(strategy)
                    or stress_exposures_by_strategy.get("*")
                    or stress_exposures_by_strategy.get("__default__")
                )

            if gate is not None:
                gate.register_strategy(strategy)
                selection_ok, selection_report = gate.update_demo_selection_bias_evidence(
                    strategy,
                    observed_sharpe=evidence.observed_sharpe,
                    n_trials=evidence.n_trials,
                    n_observations=evidence.n_observations,
                    candidate_oos_returns=evidence.candidate_oos_returns,
                    trial_sharpes=evidence.trial_sharpes,
                )
                tail_ok, tail_report = gate.update_demo_tail_risk_evidence(
                    strategy,
                    portfolio_returns=evidence.portfolio_returns,
                    stress_exposures=dict(stress_exposures) if stress_exposures else None,
                    n_bootstrap=n_bootstrap,
                    seed=seed,
                )
            else:
                selection_ok, selection_report = _selection_report_without_gate(evidence)
                tail_ok, tail_report = _tail_report_without_gate(
                    evidence,
                    stress_exposures=stress_exposures,
                    n_bootstrap=n_bootstrap,
                    seed=seed,
                )

            if cur is not None:
                try:
                    if _persist_promotion_reports(
                        cur,
                        evidence,
                        selection_report=selection_report,
                        tail_report=tail_report,
                    ):
                        persisted_reports += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "promotion evidence report persist failed for %s "
                        "(fail-soft): %s",
                        strategy,
                        exc,
                    )

            selection_passes += int(bool(selection_ok))
            tail_passes += int(bool(tail_ok))
            details[strategy] = {
                "n_trials": evidence.n_trials,
                "n_observations": evidence.n_observations,
                "candidate_count": len(evidence.candidates),
                "selection_verdict": selection_report.get("verdict"),
                "selection_passes": bool(selection_ok),
                "tail_verdict": tail_report.get("verdict"),
                "tail_passes": bool(tail_ok),
            }

        if conn is not None:
            conn.commit()
    except Exception:
        if conn is not None:
            conn.rollback()
        raise
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    return {
        "status": "ok",
        "engine_mode": engine_mode,
        "strategies": len(evidence_by_strategy),
        "selection_passes": selection_passes,
        "tail_passes": tail_passes,
        "ledger_rows": ledger_rows,
        "persisted_reports": persisted_reports,
        "updated_at": datetime.now(tz=timezone.utc).isoformat(),
        "details": details,
    }
