"""
Validation gates for realized edge estimates.

This module deliberately sits between James-Stein estimation and the runtime JSON
snapshot.  The estimator may still report a positive `shrunk_bps`, but runtime
consumers should only trade on positive edge after a minimum out-of-sample check.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from .realized_edge_stats import EdgeStats, RoundTripRecord


@dataclass(frozen=True)
class ValidationConfig:
    """Thresholds for edge estimate validation."""

    validation_history_days: int = 180
    wf_train_days: int = 90
    wf_test_days: int = 30
    wf_step_days: int = 30
    min_trust_n: int = 30
    min_oos_n: int = 30
    min_wf_windows: int = 2
    psr_min: float = 0.95
    dsr_min: float = 0.90
    bonferroni_alpha_family: float = 0.05
    benchmark_bps: float = 0.0

    @classmethod
    def for_engine_mode(cls, engine_mode: str) -> "ValidationConfig":
        """Return conservative defaults for runtime modes."""
        if engine_mode in ("live", "live_demo"):
            return cls(
                min_trust_n=100,
                min_oos_n=60,
                min_wf_windows=3,
                psr_min=0.975,
                dsr_min=0.95,
            )
        return cls()

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ValidationResult:
    """Validation verdict for a single (strategy, symbol) cell."""

    validation_passed: bool
    validation_reason: str
    wf_windows: int
    oos_n: int
    oos_mean_bps: float
    oos_sharpe: float
    psr: float
    dsr: float
    p_value_raw: float
    p_value_bonferroni: float
    m_tests: int

    def to_json_dict(self) -> dict:
        return {
            "validation_passed": self.validation_passed,
            "validation_reason": self.validation_reason,
            "wf_windows": self.wf_windows,
            "oos_n": self.oos_n,
            "oos_mean_bps": round(self.oos_mean_bps, 6),
            "oos_sharpe": round(self.oos_sharpe, 6),
            "psr": round(self.psr, 6),
            "dsr": round(self.dsr, 6),
            "p_value_raw": round(self.p_value_raw, 6),
            "p_value_bonferroni": round(self.p_value_bonferroni, 6),
            "m_tests": self.m_tests,
        }


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _finite_values(values: Iterable[float]) -> list[float]:
    return [v for v in values if math.isfinite(v)]


def _sample_mean_std(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    mean = sum(values) / len(values)
    if len(values) < 2:
        return mean, 0.0
    var = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return mean, math.sqrt(max(var, 0.0))


def _records_in_window(
    records: list[RoundTripRecord],
    start: datetime,
    end: datetime,
) -> list[RoundTripRecord]:
    return [
        r for r in records
        if r.exit_ts is not None and start <= r.exit_ts < end
    ]


def _walk_forward_oos_values(
    records: list[RoundTripRecord],
    config: ValidationConfig,
    now: Optional[datetime],
) -> tuple[list[float], int]:
    dated = [r for r in records if r.exit_ts is not None]
    if not dated:
        return [], 0
    dated.sort(key=lambda r: r.exit_ts or datetime.min.replace(tzinfo=timezone.utc))
    first_ts = dated[0].exit_ts
    last_ts = now or dated[-1].exit_ts
    if first_ts is None or last_ts is None:
        return [], 0
    if first_ts.tzinfo is None:
        first_ts = first_ts.replace(tzinfo=timezone.utc)
    if last_ts.tzinfo is None:
        last_ts = last_ts.replace(tzinfo=timezone.utc)

    train = timedelta(days=config.wf_train_days)
    test = timedelta(days=config.wf_test_days)
    step = timedelta(days=config.wf_step_days)

    values: list[float] = []
    windows = 0
    window_start = first_ts
    while window_start + train + test <= last_ts:
        train_end = window_start + train
        test_end = train_end + test
        train_recs = _records_in_window(dated, window_start, train_end)
        test_recs = _records_in_window(dated, train_end, test_end)
        if train_recs and test_recs:
            windows += 1
            values.extend(r.net_pnl_bps for r in test_recs)
        window_start += step

    return _finite_values(values), windows


def _validate_one(
    stats: EdgeStats,
    config: ValidationConfig,
    m_tests: int,
    now: Optional[datetime],
) -> ValidationResult:
    records = list(getattr(stats, "raw_records", []) or [])
    if len(records) < config.min_trust_n:
        return ValidationResult(
            validation_passed=False,
            validation_reason="insufficient_total_samples",
            wf_windows=0,
            oos_n=0,
            oos_mean_bps=0.0,
            oos_sharpe=0.0,
            psr=0.0,
            dsr=0.0,
            p_value_raw=1.0,
            p_value_bonferroni=1.0,
            m_tests=m_tests,
        )

    oos_values, wf_windows = _walk_forward_oos_values(records, config, now)
    oos_n = len(oos_values)
    mean, std = _sample_mean_std(oos_values)
    if std > 0.0 and oos_n > 1:
        oos_sharpe = (mean - config.benchmark_bps) / std
        psr = _normal_cdf(oos_sharpe * math.sqrt(oos_n))
    else:
        oos_sharpe = 0.0
        psr = 1.0 if mean > config.benchmark_bps and oos_n > 1 else 0.0
    p_raw = max(0.0, min(1.0, 1.0 - psr))
    p_bonf = min(1.0, p_raw * max(m_tests, 1))
    dsr = 1.0 - p_bonf

    reasons: list[str] = []
    if wf_windows < config.min_wf_windows:
        reasons.append("insufficient_walk_forward_windows")
    if oos_n < config.min_oos_n:
        reasons.append("insufficient_oos_samples")
    if mean <= config.benchmark_bps:
        reasons.append("non_positive_oos_mean")
    if psr < config.psr_min:
        reasons.append("psr_below_threshold")
    if dsr < config.dsr_min:
        reasons.append("dsr_below_threshold")
    if p_bonf > config.bonferroni_alpha_family:
        reasons.append("bonferroni_rejected")

    return ValidationResult(
        validation_passed=not reasons,
        validation_reason="passed" if not reasons else ",".join(reasons),
        wf_windows=wf_windows,
        oos_n=oos_n,
        oos_mean_bps=mean,
        oos_sharpe=oos_sharpe,
        psr=psr,
        dsr=dsr,
        p_value_raw=p_raw,
        p_value_bonferroni=p_bonf,
        m_tests=m_tests,
    )


def validate_edge_stats(
    stats: dict[tuple[str, str], EdgeStats],
    config: ValidationConfig,
    now: Optional[datetime] = None,
) -> tuple[dict[tuple[str, str], ValidationResult], dict]:
    """Validate all cells and return verdicts plus a compact summary."""
    m_tests = max(len(stats), 1)
    verdicts = {
        key: _validate_one(edge_stats, config, m_tests=m_tests, now=now)
        for key, edge_stats in stats.items()
    }
    passed = sum(1 for v in verdicts.values() if v.validation_passed)
    insufficient = sum(
        1 for v in verdicts.values()
        if v.validation_reason.startswith("insufficient")
        or "insufficient_" in v.validation_reason
    )
    rejected = len(verdicts) - passed - insufficient
    summary = {
        "tested_cells": len(verdicts),
        "eligible_cells": passed,
        "insufficient_cells": insufficient,
        "rejected_cells": rejected,
    }
    return verdicts, summary

