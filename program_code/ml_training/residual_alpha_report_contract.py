"""
MODULE_NOTE
模塊用途：Residual alpha report 的共享契約驗證器。
主要類/函數：RESIDUAL_ALPHA_REPORT_FIELD、extract_demo_residual_alpha_report、
validate_demo_residual_alpha_report。
依賴：僅 Python 標準庫；不計算 residual alpha、不連 DB、不讀交易所。
硬邊界：promotion / LG-5 只能 pass-through 真實離線報告；缺失、core
diagnostic、PBO 缺失或任何非 finite 指標都 fail-closed。
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


RESIDUAL_ALPHA_REPORT_FIELD = "demo_residual_alpha_report"
MIN_PSR = 0.95
MIN_DSR = 0.95
MAX_PBO = 0.5
MIN_R_BETA_RETENTION = 0.5
MAX_BETA_EDGE_SHARE = 0.5
MIN_COVERAGE = 0.8

FORBIDDEN_REASON_TOKENS: tuple[str, ...] = (
    "core_diagnostic_only",
    "pbo_missing_candidate_returns_core_diagnostic_only",
    "pbo_missing_candidate_returns",
    "pbo_not_computed",
    "pbo_invalid_candidate_returns",
    "pbo_non_finite_candidate_returns",
    "pbo_candidate_returns_length_mismatch",
)


def extract_demo_residual_alpha_report(mapping: Any) -> Any:
    """從 mapping 取 canonical residual alpha report。

    P0-C 的 promotion / LG-5 gate 只接受 ``demo_residual_alpha_report``。
    alias-only payload 必須等同缺 evidence，避免繞過 canonical required
    field。
    """
    if not isinstance(mapping, Mapping):
        return None
    return mapping.get(RESIDUAL_ALPHA_REPORT_FIELD)


def validate_demo_residual_alpha_report(report: Any) -> tuple[bool, str]:
    """驗證 demo residual alpha report 是否可用於 promotion / LG-5。

    為什麼 fail-closed：此 validator 位於 promotion / approval path，不得
    現時計算 residual alpha，也不得把 core diagnostic 報告誤當真實 PBO
    evidence。回傳 reason 保持短字串，供 caller 組裝 audit/gate reason。
    """
    if not isinstance(report, dict):
        return False, "not_dict"
    if report.get("passes") is not True:
        return False, "passes_not_true"
    verdict = str(report.get("verdict") or "")
    if verdict != "pass":
        return False, f"verdict_not_pass:{verdict or 'missing'}"

    forbidden = _find_forbidden_reason(report.get("reasons"))
    if forbidden:
        return False, f"forbidden_reason:{forbidden}"

    for metric in ("pbo_raw", "pbo_residual"):
        value = _finite_float(report.get(metric))
        if value is None:
            return False, f"metric_missing:{metric}"
        if value > MAX_PBO:
            return False, f"{metric}_above_threshold"

    for metric in ("psr_raw", "psr_residual"):
        value = _finite_float(report.get(metric))
        if value is None:
            return False, f"metric_missing:{metric}"
        if value < MIN_PSR:
            return False, f"{metric}_below_threshold"

    for metric in ("dsr_raw", "dsr_residual"):
        value = _finite_float(report.get(metric))
        if value is None:
            return False, f"metric_missing:{metric}"
        if value < MIN_DSR:
            return False, f"{metric}_below_threshold"

    raw_mean = _finite_float(report.get("raw_mean_bps"))
    if raw_mean is None:
        return False, "metric_missing:raw_mean_bps"
    if raw_mean <= 0.0:
        return False, "raw_mean_non_positive"

    residual_mean = _finite_float(report.get("residual_mean_bps"))
    if residual_mean is None:
        return False, "metric_missing:residual_mean_bps"
    if residual_mean <= 0.0:
        return False, "residual_mean_non_positive"

    r_beta_retention = _finite_float(report.get("r_beta_retention"))
    if r_beta_retention is None:
        return False, "metric_missing:r_beta_retention"
    if r_beta_retention < MIN_R_BETA_RETENTION:
        return False, "r_beta_retention_below_threshold"

    beta_edge_share = _finite_float(report.get("beta_edge_share"))
    if beta_edge_share is None:
        return False, "metric_missing:beta_edge_share"
    if beta_edge_share > MAX_BETA_EDGE_SHARE:
        return False, "beta_edge_share_above_threshold"

    factor_panel_hash = str(report.get("factor_panel_hash") or "").strip()
    if not factor_panel_hash:
        return False, "factor_panel_hash_missing"

    fit_window_ok, fit_window_reason = _validate_fit_window(report.get("fit_window"))
    if not fit_window_ok:
        return False, fit_window_reason

    coverage_ok, coverage_reason = _validate_coverage(report.get("coverage"))
    if not coverage_ok:
        return False, coverage_reason

    return True, "ok"


def _finite_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def _normalize_reasons(raw_reasons: Any) -> list[str]:
    if raw_reasons is None:
        return []
    if isinstance(raw_reasons, str):
        return [raw_reasons]
    if isinstance(raw_reasons, (list, tuple, set)):
        return [str(reason) for reason in raw_reasons]
    return [str(raw_reasons)]


def _find_forbidden_reason(raw_reasons: Any) -> str | None:
    reasons = _normalize_reasons(raw_reasons)
    for reason in reasons:
        lowered = reason.lower()
        for token in sorted(FORBIDDEN_REASON_TOKENS, key=len, reverse=True):
            if token in lowered:
                return token
    return None


def _validate_fit_window(raw_window: Any) -> tuple[bool, str]:
    if not isinstance(raw_window, Mapping):
        return False, "fit_window_missing"
    if "train_end" not in raw_window or "eval_start" not in raw_window:
        return False, "fit_window_missing"
    train_end = raw_window.get("train_end")
    eval_start = raw_window.get("eval_start")
    if train_end is None or eval_start is None:
        return False, "fit_window_missing"
    try:
        prior = train_end < eval_start
    except TypeError:
        # 不可比較的 label 只保留存在性要求；計算端仍應提供 hash 和 metrics。
        return True, "ok"
    if not prior:
        return False, "fit_window_not_prior"
    return True, "ok"


def _validate_coverage(raw_coverage: Any) -> tuple[bool, str]:
    if raw_coverage is None:
        return True, "ok"
    if not isinstance(raw_coverage, Mapping):
        return False, "coverage_invalid"
    for key in ("train", "eval"):
        if key not in raw_coverage:
            continue
        value = _finite_float(raw_coverage.get(key))
        if value is None:
            return False, f"coverage_{key}_invalid"
        if value < MIN_COVERAGE:
            return False, f"coverage_{key}_below_threshold"
    return True, "ok"
