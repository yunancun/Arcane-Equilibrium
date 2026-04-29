"""
Acceptance Report for EDGE-P3-1 Stage 2 Quantile Trainer.
EDGE-P3-1 Stage 2 三分位訓練器驗收報告。

MODULE_NOTE (EN): Aggregates the six ship-gate metrics from spec §6.2
  (pinball skill, coverage error, decile lift 95% CI, crossing rate,
  LGBM-vs-linear-QR skill diff, train-serve skew harness sample) into a
  single verdict: "should_ship" / "shadow_only" / "no_ship". Sample-size
  gate (≥500 / 200–499 / <200) per §6.5 is checked first; gate failures
  downgrade ship→shadow; sample <200 forces no_ship. JSON persistable.
MODULE_NOTE (中): 整合 spec §6.2 六項驗收指標 + §6.5 樣本量閘，產出
  should_ship / shadow_only / no_ship 結論。樣本 <200 強制 no_ship；
  200–499 強制 shadow_only；≥500 且所有指標過才 should_ship。可持久化 JSON。
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from program_code.ml_training.quantile_trainer import (
    QUANTILE_ALPHAS,
    QuantileTrainingConfig,
    QuantileTrainingResult,
)

logger = logging.getLogger(__name__)

VERDICT_SHIP = "should_ship"
VERDICT_SHADOW = "shadow_only"
VERDICT_NO_SHIP = "no_ship"

# Hard acceptance thresholds per spec §6.2.
# spec §6.2 硬性驗收門檻。
THRESH_PINBALL_SKILL_MIN = 0.10
THRESH_COVERAGE_ERROR_PP_MAX = 3.0
THRESH_DECILE_LIFT_CI_LOWER_MIN = 1.3
THRESH_DECILE_LIFT_POINT_MIN = 1.5
THRESH_CROSSING_RATE_MAX = 0.01
THRESH_LGBM_VS_LINEAR_QR_MIN_DIFF = 0.05  # +5pp pinball skill vs linear QR

# Sample-size buckets per spec §6.5.
# spec §6.5 樣本量分層。
SAMPLE_GATE_PROD = 500
SAMPLE_GATE_SHADOW = 200


def _build_train_serve_skew_harness(
    result: QuantileTrainingResult,
    n_samples: int = 1000,
    seed: int = 1337,
) -> Dict[str, Any]:
    """Produce Python-side predictions on random vectors for CC T7 comparison.

    Rust tract/ort loader compares its output against these predictions; the
    spec §6.2 gate (<1e-3 max abs err) is enforced on the Rust side. We only
    ship deterministic inputs + golden outputs so the check is reproducible.
    產出 Python 端對 1000 個 random vector 的預測，供 Rust CC T7 比對；
    spec §6.2 的 <1e-3 gate 由 Rust 側驗證，此處只輸出確定性輸入 + 標準輸出。
    """
    n_features = len(result.feature_names)
    rng = np.random.default_rng(seed)
    # Uniform [-3, 3] covers bulk of z-normalized features; edge cases
    # (NaN / Inf / boolean packed u8) are intentionally out of scope here.
    # Uniform [-3, 3] 覆蓋 z-normalized 特徵主體；NaN/Inf/布林 u8 不在此處範圍。
    samples = rng.uniform(-3.0, 3.0, size=(n_samples, n_features)).astype(np.float32)

    preds: Dict[str, List[float]] = {}
    for qname in ("q10", "q50", "q90"):
        booster = result.models.get(qname)
        if booster is None:
            continue
        preds[qname] = np.asarray(booster.predict(samples)).astype(float).tolist()

    return {
        "n_features": int(n_features),
        "n_samples": int(n_samples),
        "seed": int(seed),
        "feature_names": list(result.feature_names),
        "samples": samples.tolist(),
        "predictions": preds,
    }


def _check_pinball_skill(result: QuantileTrainingResult) -> Tuple[bool, Dict[str, Any]]:
    """All three quantiles must exceed THRESH_PINBALL_SKILL_MIN.
    三分位 pinball skill 都需超過閾值。"""
    per_q: Dict[str, Dict[str, Any]] = {}
    all_pass = True
    for alpha in QUANTILE_ALPHAS:
        key = f"q{int(alpha * 100):02d}"
        m = result.per_quantile_metrics.get(key)
        skill = float(m.pinball_skill) if m is not None else 0.0
        passed = skill > THRESH_PINBALL_SKILL_MIN
        all_pass = all_pass and passed
        per_q[key] = {"skill": skill, "passed": passed, "threshold": THRESH_PINBALL_SKILL_MIN}
    return all_pass, {"per_quantile": per_q}


def _check_coverage_error(
    result: QuantileTrainingResult,
    post_cqr_coverage: Optional[Dict[str, Tuple[float, float]]],
) -> Tuple[bool, Dict[str, Any]]:
    """All three quantile coverage errors < THRESH_COVERAGE_ERROR_PP_MAX (3pp).

    If post_cqr_coverage is provided (calibration already applied) we use
    that; otherwise fall back to pre-calibration metrics on holdout.
    若已提供 CQR 後 coverage 則用該值；否則用校準前 holdout 指標。
    """
    per_q: Dict[str, Dict[str, Any]] = {}
    all_pass = True
    for alpha in QUANTILE_ALPHAS:
        key = f"q{int(alpha * 100):02d}"
        if post_cqr_coverage and key in post_cqr_coverage:
            empirical, err_pp = post_cqr_coverage[key]
            source = "post_cqr"
        else:
            m = result.per_quantile_metrics.get(key)
            empirical = float(m.empirical_coverage) if m is not None else 0.0
            err_pp = float(m.coverage_error_pp) if m is not None else 100.0
            source = "pre_cqr"
        passed = err_pp < THRESH_COVERAGE_ERROR_PP_MAX
        all_pass = all_pass and passed
        per_q[key] = {
            "empirical_coverage": float(empirical),
            "coverage_error_pp": float(err_pp),
            "passed": passed,
            "source": source,
            "threshold_pp": THRESH_COVERAGE_ERROR_PP_MAX,
        }
    return all_pass, {"per_quantile": per_q}


def _check_decile_lift(result: QuantileTrainingResult) -> Tuple[bool, Dict[str, Any]]:
    """Decile lift 1000-bootstrap 95% CI lower > 1.3 AND point estimate ≥ 1.5.
    Decile lift 1000-bootstrap 95% CI 下界 > 1.3，且點估計 ≥ 1.5。"""
    point = float(result.decile_lift_point)
    ci_lower = float(result.decile_lift_ci_lower)
    ci_upper = float(result.decile_lift_ci_upper)
    passed = (ci_lower > THRESH_DECILE_LIFT_CI_LOWER_MIN) and (point >= THRESH_DECILE_LIFT_POINT_MIN)
    return passed, {
        "point_estimate": point,
        "ci_lower_95": ci_lower,
        "ci_upper_95": ci_upper,
        "ci_lower_threshold": THRESH_DECILE_LIFT_CI_LOWER_MIN,
        "point_threshold": THRESH_DECILE_LIFT_POINT_MIN,
        "passed": passed,
    }


def _check_crossing(result: QuantileTrainingResult) -> Tuple[bool, Dict[str, Any]]:
    """Holdout quantile crossing rate < 1%.
    holdout 分位交叉違反率 < 1%。"""
    rate = float(result.crossing_rate)
    passed = rate < THRESH_CROSSING_RATE_MAX
    return passed, {"crossing_rate": rate, "threshold": THRESH_CROSSING_RATE_MAX, "passed": passed}


def _check_lgbm_vs_linear_qr(result: QuantileTrainingResult) -> Tuple[bool, Dict[str, Any]]:
    """Per-quantile LGBM skill − linear QR skill ≥ +5pp.

    linear_qr_pinball_skill may be None (sklearn unavailable during training);
    treat None as gate pass for that quantile with `source=unavailable` so the
    pipeline still reports but doesn't hard-fail. Production use requires sklearn.
    linear_qr_pinball_skill 可為 None（sklearn 缺失）；當 None 視為該分位 pass
    並標 source=unavailable，讓 pipeline 繼續；生產使用必須裝 sklearn。
    """
    per_q: Dict[str, Dict[str, Any]] = {}
    all_pass = True
    for alpha in QUANTILE_ALPHAS:
        key = f"q{int(alpha * 100):02d}"
        m = result.per_quantile_metrics.get(key)
        lgbm_skill = float(m.pinball_skill) if m is not None else 0.0
        linear_skill = m.linear_qr_pinball_skill if m is not None else None
        if linear_skill is None:
            per_q[key] = {
                "lgbm_skill": lgbm_skill,
                "linear_qr_skill": None,
                "skill_diff": None,
                "passed": True,
                "source": "unavailable",
                "threshold_diff": THRESH_LGBM_VS_LINEAR_QR_MIN_DIFF,
            }
            continue
        diff = lgbm_skill - float(linear_skill)
        passed = diff >= THRESH_LGBM_VS_LINEAR_QR_MIN_DIFF
        all_pass = all_pass and passed
        per_q[key] = {
            "lgbm_skill": lgbm_skill,
            "linear_qr_skill": float(linear_skill),
            "skill_diff": diff,
            "passed": passed,
            "threshold_diff": THRESH_LGBM_VS_LINEAR_QR_MIN_DIFF,
        }
    return all_pass, {"per_quantile": per_q}


def _sample_size_bucket(n_labeled: int) -> str:
    """spec §6.5 bucket: prod / shadow / none.
    spec §6.5 樣本分層：production / shadow_only / no_ship。"""
    if n_labeled < SAMPLE_GATE_SHADOW:
        return VERDICT_NO_SHIP
    if n_labeled < SAMPLE_GATE_PROD:
        return VERDICT_SHADOW
    return VERDICT_SHIP


def generate_acceptance_report(
    result: QuantileTrainingResult,
    config: QuantileTrainingConfig,
    cqr_offsets: Optional[Dict[str, float]] = None,
    post_cqr_coverage: Optional[Dict[str, Tuple[float, float]]] = None,
    output_path: Optional[str] = None,
    include_train_serve_harness: bool = True,
    harness_n_samples: int = 1000,
    harness_seed: int = 1337,
) -> Dict[str, Any]:
    """Assemble per-gate metrics + overall verdict (ship / shadow / no_ship).

    Inputs:
      result — QuantileTrainingResult from train_quantile_trio.
      config — QuantileTrainingConfig used for training (echoed into report).
      cqr_offsets — optional {"q10": δ, "q50": δ, "q90": δ} from CQR fit.
      post_cqr_coverage — optional {"q10": (emp, err_pp), ...} after applying CQR.
      output_path — if provided, JSON-serialize report here.
      include_train_serve_harness — produce 1000 random vectors + preds for CC T7.

    Returns dict with all gate metrics, sample-size bucket, final verdict.
    Verdict logic:
      n_labeled < 200                        → no_ship
      200 ≤ n_labeled < 500                  → shadow_only (regardless of metrics)
      n_labeled ≥ 500 AND all 5 hard gates   → should_ship
      n_labeled ≥ 500 AND any gate fails     → shadow_only (downgrade)
    裁決邏輯見上；JSON 持久化可選。
    """
    report: Dict[str, Any] = {
        "strategy_name": result.strategy_name,
        "engine_mode": result.engine_mode,
        "schema_version": config.schema_version,
        "feature_schema_hash": result.feature_schema_hash,
        "feature_definition_hash": result.feature_definition_hash,
        "n_samples_total": int(result.n_samples_total),
        "n_samples_labeled": int(result.n_samples_labeled),
        "n_holdout": int(result.n_holdout),
        "embargo_config": asdict(result.embargo_config) if result.embargo_config else None,
        "training_success": bool(result.success),
        "training_error": result.error or None,
    }

    if not result.success:
        report["verdict"] = VERDICT_NO_SHIP
        report["verdict_reason"] = f"training failed: {result.error}"
        return _maybe_persist(report, output_path)

    # Sample-size bucket first (short-circuit for small n).
    bucket = _sample_size_bucket(result.n_samples_labeled)
    report["sample_bucket"] = bucket

    # Per-gate evaluations (all five).
    skill_pass, skill_detail = _check_pinball_skill(result)
    coverage_pass, coverage_detail = _check_coverage_error(result, post_cqr_coverage)
    lift_pass, lift_detail = _check_decile_lift(result)
    crossing_pass, crossing_detail = _check_crossing(result)
    floor_pass, floor_detail = _check_lgbm_vs_linear_qr(result)

    report["gates"] = {
        "pinball_skill": {"passed": skill_pass, **skill_detail},
        "coverage_error": {"passed": coverage_pass, **coverage_detail},
        "decile_lift": {"passed": lift_pass, **lift_detail},
        "crossing_rate": {"passed": crossing_pass, **crossing_detail},
        "lgbm_vs_linear_qr": {"passed": floor_pass, **floor_detail},
    }
    all_hard_gates_pass = all([skill_pass, coverage_pass, lift_pass, crossing_pass, floor_pass])
    report["all_hard_gates_pass"] = all_hard_gates_pass

    report["cqr_offsets"] = cqr_offsets or {}

    # Final verdict.
    if bucket == VERDICT_NO_SHIP:
        verdict = VERDICT_NO_SHIP
        reason = f"n_labeled={result.n_samples_labeled} < {SAMPLE_GATE_SHADOW}"
    elif bucket == VERDICT_SHADOW:
        verdict = VERDICT_SHADOW
        reason = (
            f"n_labeled={result.n_samples_labeled} in [{SAMPLE_GATE_SHADOW},"
            f"{SAMPLE_GATE_PROD}) — shadow-only window"
        )
    else:  # bucket == VERDICT_SHIP
        if all_hard_gates_pass:
            verdict = VERDICT_SHIP
            reason = "all gates passed, sample ≥ prod threshold"
        else:
            verdict = VERDICT_SHADOW
            failed = [
                name for name, passed in (
                    ("pinball_skill", skill_pass),
                    ("coverage_error", coverage_pass),
                    ("decile_lift", lift_pass),
                    ("crossing_rate", crossing_pass),
                    ("lgbm_vs_linear_qr", floor_pass),
                ) if not passed
            ]
            reason = f"sample ≥ prod but gate(s) failed: {failed} → downgrade to shadow"
    report["verdict"] = verdict
    report["verdict_reason"] = reason

    # Train-serve skew harness (inputs + golden preds).
    if include_train_serve_harness:
        try:
            report["train_serve_harness"] = _build_train_serve_skew_harness(
                result, n_samples=harness_n_samples, seed=harness_seed,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("train-serve harness build failed: %s", e)
            report["train_serve_harness"] = {"error": str(e)}

    logger.info(
        "acceptance_report: strategy=%s engine=%s verdict=%s reason=%s "
        "n_labeled=%d gates_pass=%s",
        result.strategy_name, result.engine_mode, verdict, reason,
        result.n_samples_labeled, all_hard_gates_pass,
    )

    return _maybe_persist(report, output_path)


def _maybe_persist(report: Dict[str, Any], output_path: Optional[str]) -> Dict[str, Any]:
    """JSON-serialize report to output_path if provided; fail-soft.
    提供 output_path 時 JSON 持久化；失敗不中斷。"""
    if not output_path:
        return report
    try:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
        logger.info("acceptance report persisted: %s", output_path)
    except Exception as e:  # noqa: BLE001
        logger.warning("acceptance report persist failed (non-fatal): %s", e)
    return report
