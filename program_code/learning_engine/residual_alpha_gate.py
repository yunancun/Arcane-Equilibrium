"""Residual alpha gate — 純數學 beta 殘差門控。

本模組只做離線數學評估：0 DB、0 Bybit、0 runtime order path。輸入候選
報酬與 point-in-time factor panel，先在 train/prior window 擬合 factor beta，
再只用該 beta 對 OOS/eval window 計算 residual alpha。
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any, Hashable, Literal, Mapping, Sequence

import numpy as np


ReturnUnit = Literal["bps", "fraction"]
ResidualAlphaVerdict = Literal["pass", "fail", "defer_data"]


DEFAULT_REQUIRED_FACTORS: tuple[str, ...] = ("btc", "market")
DEFAULT_MIN_COVERAGE: float = 0.8
DEFAULT_MIN_TRAIN_OBSERVATIONS: int = 30
DEFAULT_MIN_EVAL_OBSERVATIONS: int = 10
DEFAULT_MIN_R_BETA_RETENTION: float = 0.5
DEFAULT_MAX_BETA_EDGE_SHARE: float = 0.5
DEFAULT_MIN_PSR: float = 0.95
DEFAULT_MIN_DSR: float = 0.95
DEFAULT_MAX_PBO: float = 0.5
_EPSILON: float = 1e-12


MODULE_NOTE = """\
模塊用途：離線 residual alpha evidence gate；用 train/prior beta 評估 eval residual edge。
主要類/函數：ResidualAlphaProtocol、ResidualAlphaGate.evaluate()、ResidualEdgeReport、evaluate_residual_alpha()。
依賴：僅 Python 標準庫與 numpy；不連 DB、不讀 Bybit、不依賴 runtime state。
硬邊界：只有 train/eval fit_window 內資料可影響 verdict/hash/report；窗口外 future row/NaN 不得污染結果。invalid window、範圍內非 finite row、duplicate timestamp、coverage 不足、或統計 evidence 缺失都 fail/defer，不得視為 promotion_ready。
"""


@dataclass(frozen=True)
class TimestampedReturn:
    """候選 timestamped return；value 單位由 protocol.return_unit 指定。"""

    timestamp: Hashable
    value: float


@dataclass(frozen=True)
class ResidualAlphaFitWindow:
    """train/prior 與 OOS/eval window。

    train_end 必須早於 eval_start；此門控不允許用 full-sample beta。
    """

    train_start: Hashable
    train_end: Hashable
    eval_start: Hashable
    eval_end: Hashable
    label: str = "single_prior"

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "train_start": _timestamp_for_report(self.train_start),
            "train_end": _timestamp_for_report(self.train_end),
            "eval_start": _timestamp_for_report(self.eval_start),
            "eval_end": _timestamp_for_report(self.eval_end),
        }


@dataclass(frozen=True)
class ResidualAlphaProtocol:
    """Residual beta 評估協議。

    return_unit 適用於 candidate returns 與 factor returns；輸出均轉成 bps。
    candidate_oos_returns 是 PBO 的 peer-candidate OOS returns；缺失時預設
    不得 promotion-ready。allow_missing_pbo_for_core_tests 只給 unit/core
    diagnostic 使用，不得作 promotion evidence。
    """

    fit_window: ResidualAlphaFitWindow
    required_factors: tuple[str, ...] = DEFAULT_REQUIRED_FACTORS
    return_unit: ReturnUnit = "bps"
    min_coverage: float = DEFAULT_MIN_COVERAGE
    min_train_observations: int = DEFAULT_MIN_TRAIN_OBSERVATIONS
    min_eval_observations: int = DEFAULT_MIN_EVAL_OBSERVATIONS
    min_r_beta_retention: float = DEFAULT_MIN_R_BETA_RETENTION
    max_beta_edge_share: float = DEFAULT_MAX_BETA_EDGE_SHARE
    min_psr: float = DEFAULT_MIN_PSR
    min_dsr: float = DEFAULT_MIN_DSR
    max_pbo: float = DEFAULT_MAX_PBO
    n_trials: int = 1
    psr_benchmark_bps: float = 0.0
    candidate_oos_returns: Sequence[Any] | None = None
    allow_missing_pbo_for_core_tests: bool = False


@dataclass(frozen=True)
class ResidualEdgeReport:
    """Residual alpha gate 報告。

    beta_loadings 以輸入 return unit 的同單位回歸估計；factor 與 candidate
    同單位時，factor beta 為無量綱。`_intercept_bps` 只作診斷，不從 OOS
    residual 扣除，避免把 train alpha 當成 beta 替 true alpha 清掉。
    """

    raw_mean_bps: float
    residual_mean_bps: float
    r_beta_retention: float
    beta_edge_share: float
    beta_loadings: dict[str, float]
    r_squared: float
    psr_raw: float | None
    psr_residual: float | None
    dsr_raw: float | None
    dsr_residual: float | None
    pbo_raw: float | None
    pbo_residual: float | None
    coverage: dict[str, float | int]
    verdict: ResidualAlphaVerdict
    reasons: tuple[str, ...]
    factor_panel_hash: str
    fit_window: dict[str, Any]
    passes: bool

    def to_dict(self) -> dict[str, Any]:
        """回傳 JSON-safe dict，供 evidence artifact 或 audit surface 使用。"""
        return _json_safe(asdict(self))


class ResidualAlphaGate:
    """評估 raw edge 是否主要來自 BTC/market beta。

    Interface:
        evaluate(candidate_returns, factor_panel, protocol) -> ResidualEdgeReport

    支援的輸入形狀：
      - candidate_returns: Sequence[TimestampedReturn]、Sequence[(ts, value)]、
        Sequence[{"timestamp": ts, "return_bps": value}]，或 Mapping[ts, value]。
      - factor_panel: Mapping[factor_name, Mapping[ts, value]]、
        Mapping[ts, Mapping[factor_name, value]]，或 row sequence。
    """

    def evaluate(
        self,
        candidate_returns: Mapping[Hashable, float] | Sequence[Any],
        factor_panel: Mapping[Any, Any] | Sequence[Any],
        protocol: ResidualAlphaProtocol,
    ) -> ResidualEdgeReport:
        self._validate_protocol(protocol)

        fit_window = protocol.fit_window
        window_reasons = _fit_window_reasons(fit_window)
        candidate, candidate_errors = _parse_candidate_returns(
            candidate_returns,
            fit_window,
        )
        factors, factor_errors = _parse_factor_panel(
            factor_panel,
            protocol.required_factors,
            fit_window,
        )
        reasons: list[str] = [*window_reasons, *candidate_errors, *factor_errors]

        train_ts = [
            ts for ts in sorted(candidate, key=_sort_key)
            if _contains(ts, fit_window.train_start, fit_window.train_end)
        ]
        eval_ts = [
            ts for ts in sorted(candidate, key=_sort_key)
            if _contains(ts, fit_window.eval_start, fit_window.eval_end)
        ]
        aligned_train_ts = [
            ts for ts in train_ts
            if _has_required_factor_values(factors, protocol.required_factors, ts)
        ]
        aligned_eval_ts = [
            ts for ts in eval_ts
            if _has_required_factor_values(factors, protocol.required_factors, ts)
        ]

        coverage = _build_coverage(
            train_count=len(train_ts),
            eval_count=len(eval_ts),
            aligned_train_count=len(aligned_train_ts),
            aligned_eval_count=len(aligned_eval_ts),
        )
        if coverage["train"] < protocol.min_coverage:
            reasons.append("train_coverage_below_min")
        if coverage["eval"] < protocol.min_coverage:
            reasons.append("eval_coverage_below_min")
        if len(aligned_train_ts) < protocol.min_train_observations:
            reasons.append("train_observations_below_min")
        if len(aligned_eval_ts) < protocol.min_eval_observations:
            reasons.append("eval_observations_below_min")

        factor_panel_hash = _hash_factor_rows(
            factors=factors,
            timestamps=(*aligned_train_ts, *aligned_eval_ts),
            required_factors=protocol.required_factors,
            return_unit=protocol.return_unit,
        )

        # 資料品質不足時仍回完整 report，但不做不可信的 beta 推論。
        if reasons:
            verdict: ResidualAlphaVerdict = (
                "fail"
                if _has_hard_failure(reasons)
                else "defer_data"
            )
            return ResidualEdgeReport(
                raw_mean_bps=0.0,
                residual_mean_bps=0.0,
                r_beta_retention=0.0,
                beta_edge_share=1.0,
                beta_loadings={factor: 0.0 for factor in protocol.required_factors},
                r_squared=0.0,
                psr_raw=None,
                psr_residual=None,
                dsr_raw=None,
                dsr_residual=None,
                pbo_raw=None,
                pbo_residual=None,
                coverage=coverage,
                verdict=verdict,
                reasons=tuple(_dedupe(reasons)),
                factor_panel_hash=factor_panel_hash,
                fit_window=fit_window.to_dict(),
                passes=False,
            )

        train_y = np.asarray([candidate[ts] for ts in aligned_train_ts], dtype=np.float64)
        eval_y = np.asarray([candidate[ts] for ts in aligned_eval_ts], dtype=np.float64)
        train_x = _factor_matrix(factors, protocol.required_factors, aligned_train_ts)
        eval_x = _factor_matrix(factors, protocol.required_factors, aligned_eval_ts)

        intercept, beta = _fit_factor_beta(train_y, train_x)
        train_pred = intercept + train_x @ beta
        r_squared = _r_squared(train_y, train_pred)

        # residual alpha 只扣 factor beta，不扣 train intercept，避免把 alpha 清掉。
        residual_eval = eval_y - eval_x @ beta
        raw_mean_bps = _to_bps(float(np.mean(eval_y)), protocol.return_unit)
        residual_mean_bps = _to_bps(float(np.mean(residual_eval)), protocol.return_unit)

        r_beta_retention = _safe_ratio(residual_mean_bps, raw_mean_bps)
        beta_edge_share = _safe_beta_edge_share(raw_mean_bps, residual_mean_bps)
        psr_raw = _normal_approx_psr(eval_y, protocol)
        psr_residual = _normal_approx_psr(residual_eval, protocol)
        dsr_raw = _deflated_psr(psr_raw, protocol.n_trials)
        dsr_residual = _deflated_psr(psr_residual, protocol.n_trials)
        pbo_raw, pbo_residual, pbo_report_reasons, pbo_blocking_reasons = _compute_pbo(
            eval_y=eval_y,
            residual_eval=residual_eval,
            factor_prediction=eval_x @ beta,
            protocol=protocol,
        )

        verdict_reasons = _metric_reasons(
            raw_mean_bps=raw_mean_bps,
            residual_mean_bps=residual_mean_bps,
            r_beta_retention=r_beta_retention,
            beta_edge_share=beta_edge_share,
            psr_raw=psr_raw,
            psr_residual=psr_residual,
            dsr_raw=dsr_raw,
            dsr_residual=dsr_residual,
            pbo_raw=pbo_raw,
            pbo_residual=pbo_residual,
            protocol=protocol,
        )
        report_reasons = _dedupe([*verdict_reasons, *pbo_report_reasons])
        blocking_reasons = _dedupe([*verdict_reasons, *pbo_blocking_reasons])
        verdict = _verdict_from_blocking_reasons(blocking_reasons)
        beta_loadings = {
            factor: float(beta[idx])
            for idx, factor in enumerate(protocol.required_factors)
        }
        beta_loadings["_intercept_bps"] = _to_bps(float(intercept), protocol.return_unit)

        return ResidualEdgeReport(
            raw_mean_bps=raw_mean_bps,
            residual_mean_bps=residual_mean_bps,
            r_beta_retention=r_beta_retention,
            beta_edge_share=beta_edge_share,
            beta_loadings=beta_loadings,
            r_squared=r_squared,
            psr_raw=psr_raw,
            psr_residual=psr_residual,
            dsr_raw=dsr_raw,
            dsr_residual=dsr_residual,
            pbo_raw=pbo_raw,
            pbo_residual=pbo_residual,
            coverage=coverage,
            verdict=verdict,
            reasons=tuple(report_reasons),
            factor_panel_hash=factor_panel_hash,
            fit_window=fit_window.to_dict(),
            passes=verdict == "pass",
        )

    def _validate_protocol(self, protocol: ResidualAlphaProtocol) -> None:
        if not protocol.required_factors:
            raise ValueError("required_factors must not be empty")
        if protocol.return_unit not in ("bps", "fraction"):
            raise ValueError("return_unit must be 'bps' or 'fraction'")
        if not 0.0 < protocol.min_coverage <= 1.0:
            raise ValueError("min_coverage must be in (0, 1]")
        if protocol.min_train_observations < 1:
            raise ValueError("min_train_observations must be >= 1")
        if protocol.min_eval_observations < 1:
            raise ValueError("min_eval_observations must be >= 1")
        if not 0.0 <= protocol.min_psr <= 1.0:
            raise ValueError("min_psr must be in [0, 1]")
        if not 0.0 <= protocol.min_dsr <= 1.0:
            raise ValueError("min_dsr must be in [0, 1]")
        if not 0.0 <= protocol.max_pbo <= 1.0:
            raise ValueError("max_pbo must be in [0, 1]")
        if protocol.n_trials < 1:
            raise ValueError("n_trials must be >= 1")
        if not math.isfinite(protocol.psr_benchmark_bps):
            raise ValueError("psr_benchmark_bps must be finite")


def evaluate_residual_alpha(
    candidate_returns: Mapping[Hashable, float] | Sequence[Any],
    factor_panel: Mapping[Any, Any] | Sequence[Any],
    protocol: ResidualAlphaProtocol,
) -> ResidualEdgeReport:
    """便捷函式：以預設 ResidualAlphaGate 評估 residual alpha。"""

    return ResidualAlphaGate().evaluate(candidate_returns, factor_panel, protocol)


def _parse_candidate_returns(
    candidate_returns: Mapping[Hashable, float] | Sequence[Any],
    fit_window: ResidualAlphaFitWindow,
) -> tuple[dict[Hashable, float], list[str]]:
    parsed: dict[Hashable, float] = {}
    reasons: list[str] = []

    rows: Sequence[Any]
    if isinstance(candidate_returns, Mapping):
        rows = list(candidate_returns.items())
    else:
        rows = candidate_returns

    for row in rows:
        try:
            timestamp = _extract_candidate_timestamp(row)
        except (KeyError, TypeError, ValueError):
            reasons.append("invalid_candidate_return_row")
            continue
        if not _in_fit_scope(timestamp, fit_window):
            continue
        try:
            _, value = _extract_return_row(row)
        except (KeyError, TypeError, ValueError):
            reasons.append("invalid_candidate_return_row")
            continue
        if timestamp in parsed:
            reasons.append("duplicate_candidate_timestamp")
            continue
        numeric = _coerce_float(value)
        if numeric is None:
            reasons.append("non_finite_candidate_return")
            continue
        parsed[timestamp] = numeric

    if not parsed:
        reasons.append("candidate_returns_empty")
    return parsed, _dedupe(reasons)


def _parse_factor_panel(
    factor_panel: Mapping[Any, Any] | Sequence[Any],
    required_factors: Sequence[str],
    fit_window: ResidualAlphaFitWindow,
) -> tuple[dict[Hashable, dict[str, float]], list[str]]:
    reasons: list[str] = []
    parsed: dict[Hashable, dict[str, float]] = {}

    if isinstance(factor_panel, Mapping):
        if all(factor in factor_panel for factor in required_factors):
            _parse_factor_name_mapping(
                factor_panel,
                required_factors,
                fit_window,
                parsed,
                reasons,
            )
        else:
            for timestamp, row in factor_panel.items():
                if _in_fit_scope(timestamp, fit_window):
                    _add_factor_row(timestamp, row, required_factors, parsed, reasons)
    else:
        seen_timestamps: set[Hashable] = set()
        for row in factor_panel:
            try:
                timestamp = _extract_timestamp(row)
            except (KeyError, TypeError, ValueError):
                reasons.append("invalid_factor_row")
                continue
            if not _in_fit_scope(timestamp, fit_window):
                continue
            if timestamp in seen_timestamps:
                reasons.append("duplicate_factor_timestamp")
                continue
            seen_timestamps.add(timestamp)
            _add_factor_row(timestamp, row, required_factors, parsed, reasons)

    if not parsed:
        reasons.append("factor_panel_empty")
    return parsed, _dedupe(reasons)


def _parse_factor_name_mapping(
    factor_panel: Mapping[Any, Any],
    required_factors: Sequence[str],
    fit_window: ResidualAlphaFitWindow,
    parsed: dict[Hashable, dict[str, float]],
    reasons: list[str],
) -> None:
    for factor in required_factors:
        series = factor_panel.get(factor)
        if not isinstance(series, Mapping):
            reasons.append("invalid_factor_series")
            continue
        for timestamp, value in series.items():
            if not _in_fit_scope(timestamp, fit_window):
                continue
            numeric = _coerce_float(value)
            if numeric is None:
                reasons.append("non_finite_factor_return")
                continue
            parsed.setdefault(timestamp, {})[factor] = numeric


def _add_factor_row(
    timestamp: Hashable,
    row: Any,
    required_factors: Sequence[str],
    parsed: dict[Hashable, dict[str, float]],
    reasons: list[str],
) -> None:
    values = parsed.setdefault(timestamp, {})
    for factor in required_factors:
        try:
            value = _extract_factor_value(row, factor)
        except (KeyError, TypeError, ValueError):
            continue
        numeric = _coerce_float(value)
        if numeric is None:
            reasons.append("non_finite_factor_return")
            continue
        values[factor] = numeric


def _extract_return_row(row: Any) -> tuple[Hashable, Any]:
    if isinstance(row, TimestampedReturn):
        return row.timestamp, row.value
    if isinstance(row, Mapping):
        timestamp = _extract_timestamp(row)
        for key in ("return_bps", "return_fraction", "return", "value"):
            if key in row:
                return timestamp, row[key]
        raise KeyError("return value missing")
    if isinstance(row, Sequence) and not isinstance(row, (str, bytes)) and len(row) >= 2:
        return row[0], row[1]
    raise TypeError("unsupported return row")


def _extract_candidate_timestamp(row: Any) -> Hashable:
    if isinstance(row, TimestampedReturn):
        return row.timestamp
    return _extract_timestamp(row)


def _extract_timestamp(row: Any) -> Hashable:
    if isinstance(row, Mapping):
        for key in ("timestamp", "ts", "time"):
            if key in row:
                return row[key]
        raise KeyError("timestamp missing")
    if isinstance(row, Sequence) and not isinstance(row, (str, bytes)) and len(row) >= 2:
        return row[0]
    raise TypeError("unsupported timestamp row")


def _extract_factor_value(row: Any, factor: str) -> Any:
    if isinstance(row, Mapping):
        return row[factor]
    if isinstance(row, Sequence) and not isinstance(row, (str, bytes)) and len(row) >= 2:
        values = row[1]
        if isinstance(values, Mapping):
            return values[factor]
    raise TypeError("unsupported factor row")


def _coerce_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def _contains(timestamp: Hashable, start: Hashable, end: Hashable) -> bool:
    try:
        return start <= timestamp <= end  # type: ignore[operator]
    except TypeError:
        return False


def _in_fit_scope(timestamp: Hashable, fit_window: ResidualAlphaFitWindow) -> bool:
    return _contains(
        timestamp,
        fit_window.train_start,
        fit_window.train_end,
    ) or _contains(
        timestamp,
        fit_window.eval_start,
        fit_window.eval_end,
    )


def _is_ordered_or_equal(start: Hashable, end: Hashable) -> bool:
    try:
        return start <= end  # type: ignore[operator]
    except TypeError:
        return False


def _is_strictly_ordered(left: Hashable, right: Hashable) -> bool:
    try:
        return left < right  # type: ignore[operator]
    except TypeError:
        return False


def _fit_window_reasons(fit_window: ResidualAlphaFitWindow) -> list[str]:
    reasons: list[str] = []
    if not _is_ordered_or_equal(fit_window.train_start, fit_window.train_end):
        reasons.append("train_window_invalid")
    if not _is_ordered_or_equal(fit_window.eval_start, fit_window.eval_end):
        reasons.append("eval_window_invalid")
    if not _is_strictly_ordered(fit_window.train_end, fit_window.eval_start):
        reasons.append("fit_window_not_prior")
    return reasons


def _sort_key(timestamp: Hashable) -> tuple[str, str]:
    return (type(timestamp).__name__, _timestamp_for_report(timestamp))


def _timestamp_for_report(timestamp: Hashable) -> str:
    isoformat = getattr(timestamp, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    return str(timestamp)


def _has_required_factor_values(
    factors: Mapping[Hashable, Mapping[str, float]],
    required_factors: Sequence[str],
    timestamp: Hashable,
) -> bool:
    row = factors.get(timestamp)
    if row is None:
        return False
    return all(factor in row for factor in required_factors)


def _build_coverage(
    *,
    train_count: int,
    eval_count: int,
    aligned_train_count: int,
    aligned_eval_count: int,
) -> dict[str, float | int]:
    total = train_count + eval_count
    aligned_total = aligned_train_count + aligned_eval_count
    return {
        "train": _safe_count_ratio(aligned_train_count, train_count),
        "eval": _safe_count_ratio(aligned_eval_count, eval_count),
        "overall": _safe_count_ratio(aligned_total, total),
        "train_rows": train_count,
        "eval_rows": eval_count,
        "aligned_train_rows": aligned_train_count,
        "aligned_eval_rows": aligned_eval_count,
    }


def _safe_count_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


def _factor_matrix(
    factors: Mapping[Hashable, Mapping[str, float]],
    required_factors: Sequence[str],
    timestamps: Sequence[Hashable],
) -> np.ndarray:
    return np.asarray(
        [
            [factors[timestamp][factor] for factor in required_factors]
            for timestamp in timestamps
        ],
        dtype=np.float64,
    )


def _fit_factor_beta(y: np.ndarray, x: np.ndarray) -> tuple[float, np.ndarray]:
    design = np.column_stack([np.ones(len(y), dtype=np.float64), x])
    coef, *_ = np.linalg.lstsq(design, y, rcond=None)
    intercept = float(coef[0])
    beta = np.asarray(coef[1:], dtype=np.float64)
    return intercept, beta


def _r_squared(y: np.ndarray, y_pred: np.ndarray) -> float:
    total = float(np.sum((y - float(np.mean(y))) ** 2))
    if total <= _EPSILON:
        return 0.0
    residual = float(np.sum((y - y_pred) ** 2))
    score = 1.0 - residual / total
    return max(0.0, min(1.0, score))


def _to_bps(value: float, return_unit: ReturnUnit) -> float:
    if return_unit == "fraction":
        return value * 10000.0
    return value


def _safe_ratio(numerator: float, denominator: float) -> float:
    if abs(denominator) <= _EPSILON:
        return 0.0
    return numerator / denominator


def _safe_beta_edge_share(raw_mean_bps: float, residual_mean_bps: float) -> float:
    if abs(raw_mean_bps) <= _EPSILON:
        return 1.0
    return (raw_mean_bps - residual_mean_bps) / abs(raw_mean_bps)


def _from_bps(value: float, return_unit: ReturnUnit) -> float:
    if return_unit == "fraction":
        return value / 10000.0
    return value


def _normal_approx_psr(
    returns: np.ndarray,
    protocol: ResidualAlphaProtocol,
) -> float | None:
    if len(returns) <= 0:
        return None
    benchmark = _from_bps(protocol.psr_benchmark_bps, protocol.return_unit)
    mean = float(np.mean(returns))
    if len(returns) < 2:
        return _degenerate_probability(mean, benchmark)
    std = float(np.std(returns, ddof=1))
    if std <= _EPSILON:
        return _degenerate_probability(mean, benchmark)
    z_score = (mean - benchmark) / (std / math.sqrt(float(len(returns))))
    return _normal_cdf(z_score)


def _degenerate_probability(mean: float, benchmark: float) -> float:
    if mean > benchmark:
        return 1.0
    if mean < benchmark:
        return 0.0
    return 0.5


def _normal_cdf(z_score: float) -> float:
    probability = 0.5 * (1.0 + math.erf(z_score / math.sqrt(2.0)))
    return max(0.0, min(1.0, probability))


def _deflated_psr(psr: float | None, n_trials: int) -> float | None:
    if psr is None:
        return None
    adjusted_failure = min(1.0, (1.0 - psr) * float(n_trials))
    return max(0.0, min(1.0, 1.0 - adjusted_failure))


def _compute_pbo(
    *,
    eval_y: np.ndarray,
    residual_eval: np.ndarray,
    factor_prediction: np.ndarray,
    protocol: ResidualAlphaProtocol,
) -> tuple[float | None, float | None, list[str], list[str]]:
    if protocol.candidate_oos_returns is None:
        reason = (
            "pbo_missing_candidate_returns_core_diagnostic_only"
            if protocol.allow_missing_pbo_for_core_tests
            else "pbo_missing_candidate_returns"
        )
        blocking = [] if protocol.allow_missing_pbo_for_core_tests else [reason]
        return None, None, [reason], blocking

    raw_peers: list[np.ndarray] = []
    residual_peers: list[np.ndarray] = []
    reasons: list[str] = []
    expected_len = len(eval_y)
    for peer in protocol.candidate_oos_returns:
        raw_values, peer_reasons = _coerce_pbo_peer(
            peer,
            expected_len=expected_len,
            fit_window=protocol.fit_window,
        )
        reasons.extend(peer_reasons)
        if raw_values is None:
            continue
        raw_peers.append(raw_values)
        # 最小近似：在同一 eval factor path 上扣掉候選 prior-fit beta proxy；
        # 正式 CPCV/peer beta 可在後續版本取代。
        residual_peers.append(raw_values - factor_prediction)

    if not raw_peers or not residual_peers:
        reasons.append("pbo_not_computed")
        return None, None, _dedupe(reasons), ["pbo_not_computed"]

    return (
        _probability_of_backtest_overfit(eval_y, raw_peers),
        _probability_of_backtest_overfit(residual_eval, residual_peers),
        _dedupe(reasons),
        [],
    )


def _coerce_pbo_peer(
    peer: Any,
    *,
    expected_len: int,
    fit_window: ResidualAlphaFitWindow,
) -> tuple[np.ndarray | None, list[str]]:
    if isinstance(peer, Mapping):
        items = [
            item[1]
            for item in sorted(peer.items(), key=lambda item: _sort_key(item[0]))
            if _contains(item[0], fit_window.eval_start, fit_window.eval_end)
        ]
    elif isinstance(peer, Sequence) and not isinstance(peer, (str, bytes)):
        items = list(peer)
    else:
        return None, ["pbo_invalid_candidate_returns"]
    parsed: list[float] = []
    reasons: list[str] = []
    for item in items:
        if isinstance(item, Mapping) or (
            isinstance(item, Sequence)
            and not isinstance(item, (str, bytes))
            and len(item) >= 2
        ):
            try:
                timestamp = _extract_candidate_timestamp(item)
            except (KeyError, TypeError, ValueError):
                reasons.append("pbo_invalid_candidate_returns")
                continue
            if not _contains(timestamp, fit_window.eval_start, fit_window.eval_end):
                continue
            try:
                _, item = _extract_return_row(item)
            except (KeyError, TypeError, ValueError):
                reasons.append("pbo_invalid_candidate_returns")
                continue
        numeric = _coerce_float(item)
        if numeric is None:
            reasons.append("pbo_non_finite_candidate_returns")
            continue
        parsed.append(numeric)

    if len(parsed) != expected_len:
        reasons.append("pbo_candidate_returns_length_mismatch")
        return None, _dedupe(reasons)
    return np.asarray(parsed, dtype=np.float64), _dedupe(reasons)


def _probability_of_backtest_overfit(
    observed: np.ndarray,
    peers: Sequence[np.ndarray],
) -> float:
    observed_mean = float(np.mean(observed))
    peer_means = [float(np.mean(peer)) for peer in peers]
    if not peer_means:
        return 1.0
    not_outperforming = sum(1 for peer_mean in peer_means if peer_mean >= observed_mean)
    return float(not_outperforming) / float(len(peer_means))


def _metric_reasons(
    *,
    raw_mean_bps: float,
    residual_mean_bps: float,
    r_beta_retention: float,
    beta_edge_share: float,
    psr_raw: float | None,
    psr_residual: float | None,
    dsr_raw: float | None,
    dsr_residual: float | None,
    pbo_raw: float | None,
    pbo_residual: float | None,
    protocol: ResidualAlphaProtocol,
) -> list[str]:
    reasons: list[str] = []
    metrics = (raw_mean_bps, residual_mean_bps, r_beta_retention, beta_edge_share)
    if not all(math.isfinite(metric) for metric in metrics):
        reasons.append("non_finite_metric")
        return reasons
    if raw_mean_bps <= 0.0:
        reasons.append("raw_mean_non_positive")
    if raw_mean_bps > 0.0 and residual_mean_bps <= 0.0:
        reasons.append("raw_positive_residual_non_positive")
    if r_beta_retention < protocol.min_r_beta_retention:
        reasons.append("r_beta_retention_below_threshold")
    if beta_edge_share > protocol.max_beta_edge_share:
        reasons.append("beta_edge_share_above_threshold")
    if psr_raw is None:
        reasons.append("psr_raw_not_computed")
    elif psr_raw < protocol.min_psr:
        reasons.append("psr_raw_below_threshold")
    if psr_residual is None:
        reasons.append("psr_residual_not_computed")
    elif psr_residual < protocol.min_psr:
        reasons.append("psr_residual_below_threshold")
    if dsr_raw is None:
        reasons.append("dsr_raw_not_computed")
    elif dsr_raw < protocol.min_dsr:
        reasons.append("dsr_raw_below_threshold")
    if dsr_residual is None:
        reasons.append("dsr_residual_not_computed")
    elif dsr_residual < protocol.min_dsr:
        reasons.append("dsr_residual_below_threshold")
    if pbo_raw is not None and pbo_raw > protocol.max_pbo:
        reasons.append("pbo_raw_above_threshold")
    if pbo_residual is not None and pbo_residual > protocol.max_pbo:
        reasons.append("pbo_residual_above_threshold")
    return _dedupe(reasons)


def _hash_factor_rows(
    *,
    factors: Mapping[Hashable, Mapping[str, float]],
    timestamps: Sequence[Hashable],
    required_factors: Sequence[str],
    return_unit: ReturnUnit,
) -> str:
    rows: list[dict[str, Any]] = []
    for timestamp in sorted(timestamps, key=_sort_key):
        if not _has_required_factor_values(factors, required_factors, timestamp):
            continue
        rows.append(
            {
                "timestamp": _timestamp_for_report(timestamp),
                "factors": {
                    factor: format(float(factors[timestamp][factor]), ".17g")
                    for factor in required_factors
                },
            }
        )
    payload = {
        "return_unit": return_unit,
        "required_factors": list(required_factors),
        "rows": rows,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _verdict_from_blocking_reasons(
    blocking_reasons: Sequence[str],
) -> ResidualAlphaVerdict:
    if not blocking_reasons:
        return "pass"
    if all(_is_defer_only_reason(reason) for reason in blocking_reasons):
        return "defer_data"
    return "fail"


def _is_defer_only_reason(reason: str) -> bool:
    return reason in {
        "pbo_missing_candidate_returns",
        "pbo_not_computed",
    }


def _has_hard_failure(reasons: Sequence[str]) -> bool:
    hard_prefixes = (
        "non_finite_",
        "invalid_",
        "duplicate_",
        "fit_window_not_prior",
        "train_window_invalid",
        "eval_window_invalid",
        "candidate_returns_empty",
        "factor_panel_empty",
    )
    return any(reason.startswith(hard_prefixes) for reason in reasons)


def _dedupe(reasons: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for reason in reasons:
        if reason in seen:
            continue
        seen.add(reason)
        deduped.append(reason)
    return deduped


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value
