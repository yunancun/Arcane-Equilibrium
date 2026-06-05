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

import hashlib
import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Protocol, Sequence

import numpy as np

try:
    from program_code.ml_training.residual_alpha_report_contract import (
        extract_demo_residual_alpha_report,
        validate_demo_residual_alpha_report,
    )
except ModuleNotFoundError:  # pragma: no cover - direct app runtime fallback
    from ml_training.residual_alpha_report_contract import (  # type: ignore
        extract_demo_residual_alpha_report,
        validate_demo_residual_alpha_report,
    )

logger = logging.getLogger(__name__)

_RESIDUAL_ALPHA_METRIC_FIELDS: tuple[str, ...] = (
    "raw_mean_bps",
    "residual_mean_bps",
    "r_beta_retention",
    "beta_edge_share",
    "psr_raw",
    "psr_residual",
    "dsr_raw",
    "dsr_residual",
    "pbo_raw",
    "pbo_residual",
)


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
    demo_residual_alpha_report: Optional[dict[str, Any]] = None


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


def _dict_from_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _canonical_sha256(value: Any) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _extract_residual_report_from_row(row: Mapping[str, Any]) -> Optional[dict[str, Any]]:
    """從 JS row 或 row.payload pass-through 真實 residual alpha report。"""
    report = extract_demo_residual_alpha_report(row)
    if isinstance(report, dict):
        return report
    payload = _dict_from_payload(row.get("payload"))
    report = extract_demo_residual_alpha_report(payload)
    return report if isinstance(report, dict) else None


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
    residual_reports: dict[str, dict[str, Any]] = {}
    for key, row in js_results.items():
        if not isinstance(row, Mapping):
            continue
        if row.get("_proxy_from"):
            continue
        strategy, symbol = _row_strategy_symbol(key, row)
        if not strategy or not symbol:
            continue
        residual_report = _extract_residual_report_from_row(row)
        if residual_report is not None and strategy not in residual_reports:
            residual_reports[strategy] = residual_report
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
            demo_residual_alpha_report=residual_reports.get(strategy),
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


def _residual_summary_report(
    report: Optional[dict[str, Any]],
) -> tuple[bool, dict[str, Any]]:
    """回傳 residual alpha summary；缺 report 不合成 evidence。"""
    if report is None:
        return False, {
            "verdict": "missing",
            "passes": False,
            "reason": "missing",
            "reasons": ["missing"],
        }
    ok, reason = validate_demo_residual_alpha_report(report)
    if ok:
        return True, {
            "verdict": report.get("verdict"),
            "passes": True,
            "reason": "ok",
            "reasons": [],
        }
    return False, {
        "verdict": report.get("verdict") or "invalid",
        "passes": False,
        "reason": reason,
        "reasons": [reason],
    }


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


def _persist_residual_alpha_report(
    cur: Any,
    evidence: StrategyPromotionEvidence,
    *,
    source: str,
) -> Optional[str]:
    if evidence.demo_residual_alpha_report is None:
        return None
    if not _has_table(cur, "learning.demo_residual_alpha_reports"):
        return None

    report = evidence.demo_residual_alpha_report
    ok, reason = validate_demo_residual_alpha_report(report)
    if not ok:
        logger.info(
            "skip residual alpha report registry write for %s: %s",
            evidence.strategy_name,
            reason,
        )
        return None

    metrics: dict[str, float] = {}
    for field in _RESIDUAL_ALPHA_METRIC_FIELDS:
        value = _safe_float(report.get(field))
        if value is None:
            return None
        metrics[field] = value

    report_hash = _canonical_sha256(report)
    fit_window_raw = report.get("fit_window")
    coverage_raw = report.get("coverage")
    fit_window = fit_window_raw if isinstance(fit_window_raw, dict) else {}
    coverage = coverage_raw if isinstance(coverage_raw, dict) else {}
    factor_panel_hash = str(report.get("factor_panel_hash") or "").strip()
    cur.execute(
        """
        INSERT INTO learning.demo_residual_alpha_reports
            (strategy_name, engine_mode, report_hash, report_jsonb,
             raw_mean_bps, residual_mean_bps, r_beta_retention, beta_edge_share,
             psr_raw, psr_residual, dsr_raw, dsr_residual, pbo_raw, pbo_residual,
             factor_panel_hash, fit_window, coverage, source, evidence)
        VALUES
            (%s, %s, %s, %s::jsonb,
             %s, %s, %s, %s,
             %s, %s, %s, %s, %s, %s,
             %s, %s::jsonb, %s::jsonb, %s, %s::jsonb)
        ON CONFLICT (strategy_name, engine_mode, report_hash)
        DO UPDATE SET
            last_seen_ts = NOW(),
            source = EXCLUDED.source,
            evidence = EXCLUDED.evidence
        """,
        (
            evidence.strategy_name,
            evidence.engine_mode,
            report_hash,
            json.dumps(report, sort_keys=True),
            metrics["raw_mean_bps"],
            metrics["residual_mean_bps"],
            metrics["r_beta_retention"],
            metrics["beta_edge_share"],
            metrics["psr_raw"],
            metrics["psr_residual"],
            metrics["dsr_raw"],
            metrics["dsr_residual"],
            metrics["pbo_raw"],
            metrics["pbo_residual"],
            factor_panel_hash,
            json.dumps(fit_window, sort_keys=True),
            json.dumps(coverage, sort_keys=True),
            source,
            json.dumps(
                {
                    "return_unit": "bps",
                    "source": source,
                    "hash_algorithm": "sha256_canonical_json",
                },
                sort_keys=True,
            ),
        ),
    )
    return report_hash


def _persist_promotion_reports(
    cur: Any,
    evidence: StrategyPromotionEvidence,
    *,
    selection_report: Mapping[str, Any],
    tail_report: Mapping[str, Any],
    residual_report_hash: Optional[str] = None,
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
    has_residual_hash_column = _has_columns(
        cur,
        "learning",
        "promotion_pipeline",
        ("demo_residual_alpha_report_hash",),
    )

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
    selection_json = json.dumps(selection_report)
    tail_json = json.dumps(tail_report)
    if row:
        hash_set = ""
        params: tuple[Any, ...] = (selection_json, tail_json, row[0])
        if has_residual_hash_column:
            hash_set = """
                    demo_residual_alpha_report_hash = COALESCE(
                        %s,
                        demo_residual_alpha_report_hash
                    ),
            """
            params = (selection_json, tail_json, residual_report_hash, row[0])
        cur.execute(
            f"""
            UPDATE learning.promotion_pipeline
            SET demo_selection_bias_report = %s::jsonb,
                demo_tail_risk_report = %s::jsonb,
{hash_set}                updated_ts = NOW()
            WHERE pipeline_id = %s
            """,
            params,
        )
        return True

    hash_column = ""
    hash_value = ""
    params = (evidence.strategy_name, selection_json, tail_json)
    if has_residual_hash_column:
        hash_column = ", demo_residual_alpha_report_hash"
        hash_value = ", %s"
        params = (evidence.strategy_name, selection_json, tail_json, residual_report_hash)
    cur.execute(
        f"""
        INSERT INTO learning.promotion_pipeline
            (strategy_name, current_stage, demo_selection_bias_report,
             demo_tail_risk_report{hash_column}, updated_ts)
        VALUES (%s, 'LEARNING', %s::jsonb, %s::jsonb{hash_value}, NOW())
        """,
        params,
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
    residual_report_registry_rows = 0
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
                            demo_residual_alpha_report=(
                                evidence.demo_residual_alpha_report
                            ),
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
                residual_report = evidence.demo_residual_alpha_report
                if (
                    residual_report is not None
                    and hasattr(gate, "update_demo_residual_alpha_evidence")
                ):
                    residual_ok, residual_gate_report = (
                        gate.update_demo_residual_alpha_evidence(
                            strategy,
                            residual_report,
                        )
                    )
                else:
                    residual_ok, residual_gate_report = _residual_summary_report(
                        residual_report
                    )
            else:
                selection_ok, selection_report = _selection_report_without_gate(evidence)
                tail_ok, tail_report = _tail_report_without_gate(
                    evidence,
                    stress_exposures=stress_exposures,
                    n_bootstrap=n_bootstrap,
                    seed=seed,
                )
                residual_ok, residual_gate_report = _residual_summary_report(
                    evidence.demo_residual_alpha_report
                )

            residual_report_hash = None
            if cur is not None:
                try:
                    residual_report_hash = _persist_residual_alpha_report(
                        cur,
                        evidence,
                        source=source,
                    )
                    residual_report_registry_rows += int(
                        residual_report_hash is not None
                    )
                    if _persist_promotion_reports(
                        cur,
                        evidence,
                        selection_report=selection_report,
                        tail_report=tail_report,
                        residual_report_hash=residual_report_hash,
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
                "residual_missing": evidence.demo_residual_alpha_report is None,
                "residual_verdict": residual_gate_report.get("verdict"),
                "residual_passes": bool(residual_ok),
                "residual_reason": residual_gate_report.get("reason"),
                "residual_report_hash": residual_report_hash,
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
        "residual_report_registry_rows": residual_report_registry_rows,
        "updated_at": datetime.now(tz=timezone.utc).isoformat(),
        "details": details,
    }
