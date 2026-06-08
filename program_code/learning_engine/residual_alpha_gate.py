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

# 用倉內已審核的 DsrGate / PboGate 取代本檔手寫（且有誤）的 PSR/DSR/PBO。
# 為什麼：手寫 _normal_approx_psr 是純 mean-t→Φ（丟掉 skew/kurtosis，對加密幣
# 左偏厚尾高估顯著性）、_deflated_psr 是 Bonferroni cliff（K>=10 飽和到 0，非真
# DSR）、_probability_of_backtest_overfit 是 peer-mean 比例（非 CSCV）。DsrGate
# 提供 Bailey-Lopez de Prado 2014 真 PSR(含 skew/kurt)+ 真 DSR(E[max SR_k])；
# PboGate.compute_pbo 提供 CSCV PBO 與 insufficient_power 判定。匯入沿用本套件
# 既有 fallback pattern（package import 失敗時退 learning_engine 平面路徑直跑）。
try:  # 套件式 import（app runtime）
    from program_code.learning_engine.dsr_gate import DsrGate as _DsrGate
    from program_code.learning_engine.pbo_gate import compute_pbo as _cscv_pbo
except ModuleNotFoundError:  # pragma: no cover - 直跑 fallback
    from learning_engine.dsr_gate import DsrGate as _DsrGate  # type: ignore
    from learning_engine.pbo_gate import compute_pbo as _cscv_pbo  # type: ignore


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
DEFAULT_PERMUTATION_N: int = 2000
DEFAULT_MAX_PERM_P_VALUE: float = 0.05
# permutation 需至少 2 個 eval 點才有非退化的 sign-flip 虛無分布；不足回 None→defer。
_MIN_PERMUTATION_OBSERVATIONS: int = 2
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
    # Gap C：sign-flip permutation 虛無檢定（model-free，residual α mean≠0）。
    # 預設 OFF（backward-compat）；只有 Stage-0R orchestrator 顯式開啟才生效，
    # report 才會帶 perm 欄位、reason 才會進 blocking。permutation_seed=None 時由
    # factor_panel_hash 推導（reproducible / hash-stable）。
    permutation_enabled: bool = False
    permutation_n: int = DEFAULT_PERMUTATION_N
    permutation_seed: int | None = None
    max_perm_p_value: float = DEFAULT_MAX_PERM_P_VALUE


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
    # Gap C permutation 結果。預設 None/0/False；permutation 未啟用時 to_dict()
    # 不輸出這三個欄位，確保與 Gap C 前 report dict / hash **byte-identical**。
    perm_p_value: float | None = None
    perm_iterations: int = 0
    permutation_applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        """回傳 JSON-safe dict，供 evidence artifact 或 audit surface 使用。

        為什麼條件輸出 perm 欄位（§5.6 hash byte-identity 硬約束）：當 permutation
        未啟用（``permutation_applied`` False）時，輸出必須與 Gap C 前完全一致，否則
        bridge ``_canonical_sha256`` / drar report_hash / registry hash 會漂移，
        source-contract 的 4 處交叉比對全失準。故未啟用時剔除 perm_p_value /
        perm_iterations / permutation_applied 三個 key。啟用時三 writer 都對同一份
        最終 to_dict() 取 hash，保持一致。
        """
        raw = asdict(self)
        # permutation_applied 永遠是內部旗標，不進 canonical report payload。
        raw.pop("permutation_applied", None)
        if not self.permutation_applied:
            raw.pop("perm_p_value", None)
            raw.pop("perm_iterations", None)
        # 先 _json_safe（NaN/Inf→None、tuple→list），再 _normalize_zeros 抹平 -0.0：
        # 保證 canonical report 永不帶 -0.0，使進 PG jsonb 前後 bytes 一致（見
        # _normalize_zeros docstring 的 hash byte-identity 說明）。
        return _normalize_zeros(_json_safe(raw))


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
        psr_raw, dsr_raw = _psr_dsr_via_gate(eval_y, protocol)
        psr_residual, dsr_residual = _psr_dsr_via_gate(residual_eval, protocol)
        pbo_raw, pbo_residual, pbo_report_reasons, pbo_blocking_reasons = _compute_pbo(
            eval_y=eval_y,
            residual_eval=residual_eval,
            factor_prediction=eval_x @ beta,
            protocol=protocol,
        )

        # Gap C：sign-flip permutation 虛無檢定（預設 OFF）。只在 residual_eval 上
        # 做（PIT：不重算 factor、不引入窗外資料）；seed 綁 factor_panel_hash → 可重現。
        perm_p_value: float | None = None
        perm_iterations = 0
        perm_blocking_reasons: list[str] = []
        if protocol.permutation_enabled:
            perm_seed = (
                protocol.permutation_seed
                if protocol.permutation_seed is not None
                else _permutation_seed_from_hash(factor_panel_hash)
            )
            perm_p_value, perm_iterations = _permutation_residual_alpha(
                residual_eval, n_perm=protocol.permutation_n, seed=perm_seed
            )
            perm_blocking_reasons = _permutation_reasons(perm_p_value, protocol)

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
        report_reasons = _dedupe(
            [*verdict_reasons, *pbo_report_reasons, *perm_blocking_reasons]
        )
        blocking_reasons = _dedupe(
            [*verdict_reasons, *pbo_blocking_reasons, *perm_blocking_reasons]
        )
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
            perm_p_value=perm_p_value,
            perm_iterations=perm_iterations,
            permutation_applied=protocol.permutation_enabled,
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
        # permutation 參數只在啟用時校驗，避免對既有未設這些欄位的 caller 引入
        # 新例外（backward-compat / 行為中性）。
        if protocol.permutation_enabled:
            if protocol.permutation_n < 1:
                raise ValueError("permutation_n must be >= 1")
            if not 0.0 <= protocol.max_perm_p_value <= 1.0:
                raise ValueError("max_perm_p_value must be in [0, 1]")


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


def _psr_dsr_via_gate(
    returns: np.ndarray,
    protocol: ResidualAlphaProtocol,
) -> tuple[float | None, float | None]:
    """用倉內 vetted DsrGate 算真 PSR(含 skew/kurtosis) + 真 DSR(E[max SR_k])。

    為什麼：取代手寫 _normal_approx_psr（純 mean-t→Φ，丟 skew/kurt，對加密幣
    左偏厚尾高估顯著性）與 _deflated_psr（Bonferroni cliff，K>=10 飽和到 0）。
    回 (psr, dsr)；資料退化（n<2 或 std≈0）時回退化機率（保留舊行為），避免
    DsrGate 對 sqrt(T-1)/std 的數值要求 crash。
    """
    n = len(returns)
    if n <= 0:
        return None, None
    benchmark = _from_bps(protocol.psr_benchmark_bps, protocol.return_unit)
    mean = float(np.mean(returns))
    if n < 2:
        p = _degenerate_probability(mean, benchmark)
        return p, p
    std = float(np.std(returns, ddof=1))
    if std <= _EPSILON:
        # 常數序列：Sharpe 無定義；mean 與 benchmark 的關係直接決定機率。
        p = _degenerate_probability(mean, benchmark)
        return p, p
    observed_sharpe = (mean - benchmark) / std
    skew, ex_kurt = _sample_moments(returns)
    res = _DsrGate().compute_dsr(
        observed_sharpe=observed_sharpe,
        n_trials=protocol.n_trials,
        n_observations=n,
        skew=skew,
        excess_kurtosis=ex_kurt,
    )
    # honor DsrGate 的 P3-01 insufficient_observations 守衛（min_observations
    # 預設 30）：樣本不足時 PSR(sqrt(T-1)) / DSR 在低 N 會過度樂觀。回 None 讓
    # contract 因 metric_missing 而 defer（fail-closed），不依賴下游 PBO
    # power gate 兜底（E2 LOW-1：避免低 N DSR 過度樂觀的潛在 footgun）。
    if res.insufficient_observations:
        return None, None
    # psr_at_threshold = 真 PSR(0)、deflated_sharpe = 真 DSR(E[max SR_k])。
    return float(res.psr_at_threshold), float(res.deflated_sharpe)


def _sample_moments(returns: np.ndarray) -> tuple[float, float]:
    """以 population z-moments 回 (skew γ3, excess kurtosis γ4-3)。

    為什麼用 population（ddof=0）標準化：與 Bailey-Lopez de Prado PSR 公式的
    γ3 / γ4 定義一致；n<3 或常數序列回 (0, 0)（高斯預設，不做不可信的高階矩）。
    """
    n = len(returns)
    if n < 3:
        return 0.0, 0.0
    mean = float(np.mean(returns))
    std = float(np.std(returns))  # population ddof=0
    if std <= _EPSILON:
        return 0.0, 0.0
    z = (np.asarray(returns, dtype=np.float64) - mean) / std
    return float(np.mean(z ** 3)), float(np.mean(z ** 4) - 3.0)


def _degenerate_probability(mean: float, benchmark: float) -> float:
    if mean > benchmark:
        return 1.0
    if mean < benchmark:
        return 0.0
    return 0.5


def _permutation_seed_from_hash(factor_panel_hash: str) -> int:
    """從 factor_panel_hash 推導確定性 seed（reproducible / hash-stable）。

    為什麼綁 factor_panel_hash：同一份對齊資料 → 同一 hash → 同一 seed → 同一
    p-value，故 report 可重現、re-run 不漂移（§5.5）。取 hash 前 16 hex（64-bit）
    再對 2**32 取模，落在 numpy default_rng 接受的種子範圍。
    """
    digest = hashlib.sha256(str(factor_panel_hash).encode("utf-8")).hexdigest()
    return int(digest[:16], 16) % (2**32)


def _permutation_residual_alpha(
    residual_eval: np.ndarray,
    *,
    n_perm: int,
    seed: int,
) -> tuple[float | None, int]:
    """sign-flip permutation：model-free 檢定「residual α mean 是否可區別於 0」。

    虛無：residual_eval 的符號對稱（mean=0）。每次迭代隨機翻轉每個 eval 點的符號、
    重算 mean，p = ``|permuted mean| >= |observed mean|`` 的比例。只在**已殘差化的
    eval 序列**上做（PIT：不重算 factor、不引入窗外資料；sign-flip 保持 eval-窗成員
    不變）。確定性 seed → 可重現。

    回 ``(p_value, iterations)``；eval 點 < ``_MIN_PERMUTATION_OBSERVATIONS`` 或
    n_perm<1 或序列含非 finite → ``(None, 0)``（caller 視為 insufficient → defer，
    非 fail）。observed mean 恰為 0（退化）時回 ``(1.0, n_perm)``（無從區別於 0）。
    """
    arr = np.asarray(residual_eval, dtype=np.float64)
    n = int(arr.size)
    if n < _MIN_PERMUTATION_OBSERVATIONS or n_perm < 1:
        return None, 0
    if not np.all(np.isfinite(arr)):
        return None, 0
    observed = abs(float(np.mean(arr)))
    if observed <= _EPSILON:
        # mean≈0：本來就和虛無無法區別 → p=1（最保守），不必跑迭代。
        return 1.0, int(n_perm)
    rng = np.random.default_rng(int(seed))
    # 向量化 sign-flip：每次迭代對 n 個點各以 0.5 機率翻號。
    signs = rng.integers(0, 2, size=(int(n_perm), n)).astype(np.float64) * 2.0 - 1.0
    permuted_means = np.abs((signs * arr).mean(axis=1))
    hits = int(np.count_nonzero(permuted_means >= observed - _EPSILON))
    p_value = hits / float(n_perm)
    return p_value, int(n_perm)


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

    pbo_raw_val = _pbo_via_cscv(eval_y, raw_peers)
    pbo_res_val = _pbo_via_cscv(residual_eval, residual_peers)
    # insufficient_power（含 T<s_slices nan、total_trades 不足 320、組合數 < min_K）
    # 任一成立即 defer：CSCV 樣本檢定力不足時不得宣稱 PBO evidence。沿用既有
    # pbo_not_computed defer 流程（_is_defer_only_reason），保守不放寬。
    if pbo_raw_val is None or pbo_res_val is None:
        reasons.append("pbo_insufficient_power")
        return None, None, _dedupe(reasons), ["pbo_insufficient_power"]

    return (pbo_raw_val, pbo_res_val, _dedupe(reasons), [])


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


def _pbo_via_cscv(
    candidate: np.ndarray,
    peers: list[np.ndarray],
) -> float | None:
    """用倉內 vetted PboGate.compute_pbo（CSCV）算真 PBO。

    為什麼：取代手寫 _probability_of_backtest_overfit（只是 peer-mean 比例，
    非 Bailey-Borwein-LdP-Zhu 2014 CSCV）。[candidate, *peers] 至少 2 條序列
    （caller 已保證 peers 非空），滿足 CSCV ranking 需求。insufficient_power
    （T<s_slices 回 nan、或 total_trades/組合數不足）或非 finite → 回 None，由
    caller 走 defer 流程，CSCV 檢定力不足時不得宣稱 PBO evidence。
    """
    res = _cscv_pbo([candidate, *peers])
    if res.insufficient_power or not math.isfinite(res.pbo):
        return None
    return float(res.pbo)


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


def _permutation_reasons(
    perm_p_value: float | None,
    protocol: ResidualAlphaProtocol,
) -> list[str]:
    """permutation 的 blocking reason（mirror psr/dsr 的 not_computed vs below split）。

    perm_p_value is None（eval n 不足）→ ``perm_p_value_not_computed``（defer-only，
    非 alpha 證偽，與 pbo_not_computed 同類）；> max_perm_p_value（虛無無法拒絕）→
    ``perm_p_value_above_threshold``（genuine fail，流入 verdict）。
    """
    if perm_p_value is None:
        return ["perm_p_value_not_computed"]
    if perm_p_value > protocol.max_perm_p_value:
        return ["perm_p_value_above_threshold"]
    return []


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
        # CSCV 檢定力不足（T<s_slices / total_trades / 組合數）→ defer，非 hard fail，
        # 與 pbo_not_computed 同類：缺 PBO evidence 但非 alpha 證偽。
        "pbo_insufficient_power",
        # permutation eval n 不足 → defer（insufficient n），非 alpha 證偽；與
        # pbo_not_computed 同類。p>threshold 的 perm_p_value_above_threshold 不在此
        # → 屬 genuine fail，流入 verdict（mirror psr/dsr below_threshold）。
        "perm_p_value_not_computed",
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


def _normalize_zeros(value: Any) -> Any:
    """遞迴把 IEEE-754 負零（-0.0）正規化為正零（0.0）。

    為什麼（hash byte-identity 硬約束）：弱/共線 factor 的 np.mean / 回歸係數可能
    產出 -0.0（例如 residual_mean_bps = _to_bps(np.mean(...))、beta_loadings[f] =
    float(beta[idx])）。registry hash 在進 PG 前對 in-memory report 算（residual_
    hidden_oos_bridge._canonical_sha256），但 PostgreSQL jsonb **會丟掉浮點符號位**
    （-0.0 讀回變 0.0）；source-contract 在 jsonb 讀回後重算 hash
    （candidate_evidence_source_contract:399），於是 -0.0 → 0.0 造成 registry_hash
    != expected_hash → residual_alpha_report_hash_mismatch → 候選被誤判 INVALID。
    在 canonical report 的唯一表示（ResidualEdgeReport.to_dict）這個 chokepoint 抹平
    -0.0，使「進 jsonb 前」與「jsonb 讀回後」的 report bytes 完全相同，三 writer
    （bridge canonical / drar report_hash / registry residual hash）與 source-contract
    重算皆 hash 同一份 bytes。PG jsonb 不會正規化其他任何欄位（MIT 真 PG round-trip
    驗證），故此單點修復即收口。
    `x == 0.0` 對 +0.0 與 -0.0 皆為 True；`x + 0.0` 強制收斂到 +0.0（且對非零浮點與
    NaN/Inf 不變，但 NaN/Inf 已先被 _json_safe 轉 None）。
    """
    if isinstance(value, float):
        return value + 0.0 if value == 0.0 else value
    if isinstance(value, dict):
        return {key: _normalize_zeros(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_zeros(item) for item in value]
    return value
