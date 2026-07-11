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
import os
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

# P1-3 (2026-07-04) label 組成硬 gate 閾值：
#   - synthetic_share 修後期望恆 0（SQL 邊界已排除 rejected_governance），
#     > 0 即代表訓練集過濾退化，fail-closed 封頂 shadow_only。
#   - zeros_share 是退化偵測器：>0.5 表示標籤一半以上恰為 0（常數預測器指紋，
#     07-04 實證 pinball skill 恆 0 / coverage 恆 1 即此形態）。
THRESH_LABEL_SYNTHETIC_SHARE_MAX = 0.0
THRESH_LABEL_ZEROS_SHARE_MAX = 0.5


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


def _check_label_composition(
    label_composition: Optional[Dict[str, Any]],
) -> Tuple[bool, Dict[str, Any]]:
    """P1-3 label 組成硬 gate：synthetic_share == 0 且 zeros_share ≤ 0.5。

    為什麼 fail-closed：合成 reject label（99.97% 佔比實測）會訓練出常數預測器
    卻拿到「百萬樣本」假象；本 gate 讓退化在 verdict 層被封頂 shadow_only，
    不能 ship。composition 缺席（dry-run / 舊呼叫端）→ 視為未評估，回 pass 並
    標 source=unavailable（與 lgbm_vs_linear_qr 的 sklearn 缺席慣例對齊）。
    """
    if not label_composition:
        return True, {"source": "unavailable"}
    synthetic_share = float(label_composition.get("synthetic_share", 0.0))
    zeros_share = float(label_composition.get("zeros_share", 0.0))
    passed = (
        synthetic_share <= THRESH_LABEL_SYNTHETIC_SHARE_MAX
        and zeros_share <= THRESH_LABEL_ZEROS_SHARE_MAX
    )
    return passed, {
        "synthetic_share": synthetic_share,
        "zeros_share": zeros_share,
        "synthetic_share_max": THRESH_LABEL_SYNTHETIC_SHARE_MAX,
        "zeros_share_max": THRESH_LABEL_ZEROS_SHARE_MAX,
        "passed": passed,
    }


# Per-gate metric provenance markers (Q4 / MIT Item-1 re-review)。
#   three_way 下 ship-gate 指標取自未污染的 test 分區 → OOS。
#   two_way_shadow_capped 退路下，CQR fit+evaluate 與 early-stopping+回報「共用同一
#   holdout」→ 每道 gate 的指標其實是 in-sample（近乎完美的 coverage 可能只是自我
#   評估的假象）。把此事實直接蓋進每個 gate detail dict，讓人快速掃 shadow report
#   時不會把 in-sample 的漂亮數字誤讀成真 OOS 表現。
GATE_METRIC_SOURCE_OOS = "oos_test_partition"
GATE_METRIC_SOURCE_IN_SAMPLE_TWO_WAY = "post_cqr_in_sample_two_way"


def _stamp_gate_metric_provenance(
    gates: Dict[str, Dict[str, Any]],
    partition_mode: str,
) -> None:
    """把 in-sample-ness 蓋進每個 gate detail dict（Q4）。

    為什麼用 metric_partition_source 這個獨立 key（而非覆寫既有 `source`）：coverage /
      lgbm_vs_linear_qr 的 per_quantile 及 label_composition 的 gate 級 `source` 已有
      各自語義（post_cqr/pre_cqr/unavailable），覆寫會毀既有欄；獨立 key 不衝突且明示。
    無論 mode 都蓋（two_way→in_sample、three_way→oos），使報告永遠自證來源，而非只在
      退路時才標，避免「沒標＝OOS」的隱含推斷歧義。
    """
    two_way = partition_mode == "two_way_shadow_capped"
    marker = (
        GATE_METRIC_SOURCE_IN_SAMPLE_TWO_WAY if two_way else GATE_METRIC_SOURCE_OOS
    )
    for gate_detail in gates.values():
        if isinstance(gate_detail, dict):
            gate_detail["metric_partition_source"] = marker
            gate_detail["in_sample"] = two_way


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
    label_composition: Optional[Dict[str, Any]] = None,
    pit_dataset_manifest: Optional[Dict[str, Any]] = None,
    pit_dataset_manifest_binding: Optional[Dict[str, Any]] = None,
    persist_required: bool = False,
) -> Dict[str, Any]:
    """Assemble per-gate metrics + overall verdict (ship / shadow / no_ship).

    Inputs:
      result — QuantileTrainingResult from train_quantile_trio.
      config — QuantileTrainingConfig used for training (echoed into report).
      cqr_offsets — optional {"q10": δ, "q50": δ, "q90": δ} from CQR fit.
      post_cqr_coverage — optional {"q10": (emp, err_pp), ...} after applying CQR.
      output_path — if provided, JSON-serialize report here.
      include_train_serve_harness — produce 1000 random vectors + preds for CC T7.
      label_composition — P1-3 訓練集 label 組成（parquet_etl.build_label_composition
        產出）；提供時作為第六道硬 gate（synthetic_share == 0 且 zeros_share ≤ 0.5，
        fail → verdict 封頂 shadow_only）並原樣寫入 report。
      pit_dataset_manifest / pit_dataset_manifest_binding — WP2.1 source-only
        PIT manifest contract metadata. Non-contract-bound callers omit them and
        receive an explicit not_contract_bound binding.
      persist_required — True 時 output_path 寫入失敗會 fail-loud；僅供
        contract-bound training gate 使用，舊呼叫端維持 fail-soft。

    Returns dict with all gate metrics, sample-size bucket, final verdict.
    Verdict logic:
      n_labeled < 200                        → no_ship
      200 ≤ n_labeled < 500                  → shadow_only (regardless of metrics)
      n_labeled ≥ 500 AND all hard gates     → should_ship
      n_labeled ≥ 500 AND any gate fails     → shadow_only (downgrade)
      then two post-caps (never upgrade no_ship, only cap should_ship):
      embargo NOT enforced                   → cap should_ship → shadow_only
      partition_mode == two_way_shadow_capped→ cap should_ship → shadow_only (MIT Item 1)
    裁決邏輯見上；JSON 持久化可選。two-way 退路（sub-floor holdout）封頂 shadow_only。
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
        # 反洩漏三分 holdout 的分區列數 + 指標來源標記（claim-0002 HIGH）：
        #   three_way 下 ship_gate_metric_source="test_partition"，明示所有 ship-gate 指標
        #   （pinball_skill / coverage_error / decile_lift / crossing / CQR-後-coverage）
        #   一律取自未被 early-stopping 選模型或 CQR 校準觸碰的 test 分區。
        # MIT Item 1 修訂：trainer 可能因 holdout 太小走 two_way_shadow_capped 退路，此時
        #   來源標記為 "holdout_two_way_shadow_capped"（單一 holdout 三角色共用），且下方
        #   verdict 會據 partition_mode 硬性封頂 shadow_only。故此欄改為由 result 溯源，
        #   不再寫死；partition_mode 一併落 report 供稽核（getattr 保留舊呼叫端相容）。
        "n_validation": int(result.n_validation),
        "n_calibration": int(result.n_calibration),
        "n_test": int(result.n_test),
        "ship_gate_metric_source": getattr(
            result, "ship_gate_metric_source", "test_partition",
        ),
        "partition_mode": getattr(result, "partition_mode", "three_way"),
        "embargo_config": asdict(result.embargo_config) if result.embargo_config else None,
        # embargo 意圖配置（embargo_config）之外，另記本次是否「實際」執行 embargo：
        # 樣本不足時 trainer fail-open 靜默停用，此欄使 report 誠實反映 runtime 事實。
        "embargo_enforced": bool(result.embargo_enforced),
        # 邊界 label-realization 重疊計數（trainer 記錄）：因 embargo 未強制而殘留在
        #   訓練集、落在 holdout 起點 embargo 窗內的 train 列數。>0 且
        #   embargo_enforced=False 代表邊界洩漏風險，下方 verdict 據此封頂 shadow_only。
        "embargo_boundary_overlap_count": int(getattr(result, "embargo_overlap_count", 0)),
        "training_success": bool(result.success),
        "training_error": result.error or None,
        # P1-3：label 組成永遠落 report（None = 呼叫端未提供，如 dry-run），
        # 供 MIT/E4 驗收溯源（top_close_tags / informative vs synthetic 記帳）。
        "label_composition": label_composition,
        "pit_dataset_manifest": pit_dataset_manifest,
        "pit_dataset_manifest_binding": (
            pit_dataset_manifest_binding
            if pit_dataset_manifest_binding is not None
            else {
                "schema_version": "training_pit_manifest_binding_v1",
                "contract_bound_run": False,
                "status": "not_contract_bound",
                "manifest_hash": "",
                "manifest_path": "",
                "validation_verdict": "not_required",
                "validation_reason": "not_contract_bound",
                "not_authority": True,
                "runtime_mutation_performed": False,
                "db_write_performed": False,
                "exchange_private_read_performed": False,
                "order_or_probe_performed": False,
                "live_or_mainnet_performed": False,
                "cost_gate_change_performed": False,
                "deploy_performed": False,
                "secret_access_performed": False,
            }
        ),
    }

    if not result.success:
        report["verdict"] = VERDICT_NO_SHIP
        report["verdict_reason"] = f"training failed: {result.error}"
        return _maybe_persist(report, output_path, persist_required=persist_required)

    # Sample-size bucket first (short-circuit for small n).
    bucket = _sample_size_bucket(result.n_samples_labeled)
    report["sample_bucket"] = bucket

    # Per-gate evaluations (five metric gates + P1-3 label composition gate).
    skill_pass, skill_detail = _check_pinball_skill(result)
    coverage_pass, coverage_detail = _check_coverage_error(result, post_cqr_coverage)
    lift_pass, lift_detail = _check_decile_lift(result)
    crossing_pass, crossing_detail = _check_crossing(result)
    floor_pass, floor_detail = _check_lgbm_vs_linear_qr(result)
    composition_pass, composition_detail = _check_label_composition(label_composition)

    report["gates"] = {
        "pinball_skill": {"passed": skill_pass, **skill_detail},
        "coverage_error": {"passed": coverage_pass, **coverage_detail},
        "decile_lift": {"passed": lift_pass, **lift_detail},
        "crossing_rate": {"passed": crossing_pass, **crossing_detail},
        "lgbm_vs_linear_qr": {"passed": floor_pass, **floor_detail},
        "label_composition": {"passed": composition_pass, **composition_detail},
    }
    # Q4：把每道 gate 的指標來源（OOS test 分區 vs two-way 退路的 in-sample 共用 holdout）
    #   直接蓋進 gate detail，讓 shadow report 不會被誤讀成真 OOS。partition_mode 由
    #   result 溯源（與 top-level ship_gate_metric_source / partition_mode 一致）。
    _stamp_gate_metric_provenance(
        report["gates"], getattr(result, "partition_mode", "three_way"),
    )
    all_hard_gates_pass = all([
        skill_pass, coverage_pass, lift_pass, crossing_pass, floor_pass, composition_pass,
    ])
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
                    ("label_composition", composition_pass),
                ) if not passed
            ]
            reason = f"sample ≥ prod but gate(s) failed: {failed} → downgrade to shadow"

    # embargo fail-open 封頂裁決：embargo_enforced=False 表示 trainer 因 embargo 後
    #   樣本不足而 fail-open 停用 embargo（見 quantile_trainer.train_quantile_trio），
    #   此時 embargo_boundary_overlap_count 筆 train 列的 label 實現窗與 holdout 邊界
    #   重疊，ship-gate 指標可能因洩漏而樂觀偏誤。
    # 為什麼硬性封頂：先前 verdict 完全「忽略」embargo_enforced，等於在已知邊界洩漏
    #   風險下仍可宣告 should_ship —— 不得如此。此處封頂至 shadow_only（no_ship 維持
    #   no_ship，永不升級），並於 reason 留下 overlap 計數誠實揭露，不得靜默丟棄
    #   embargo（冷審計 R2 MIT[MEDIUM] Item 3）。
    overlap_count = int(getattr(result, "embargo_overlap_count", 0))
    if not result.embargo_enforced and verdict == VERDICT_SHIP:
        verdict = VERDICT_SHADOW
        reason = (
            f"{reason}; embargo NOT enforced "
            f"(boundary_overlap={overlap_count}) → capped at shadow_only"
        )

    # two-way 退路封頂裁決（MIT Item 1 修訂）：partition_mode == "two_way_shadow_capped"
    #   表示 trainer 因尾段 holdout 太小無法三分，退回「train + 單一 holdout」，該單一
    #   holdout 同時被 early-stopping / CQR / 回報共用 = 潛在洩漏。ship gate 絕不得消費
    #   可能洩漏的兩分指標 → 硬性封頂 shadow_only（no_ship 維持 no_ship，永不升級）。
    # 為什麼與 §6.5 一致而非冗餘：sub-floor 樣本通常落在 §6.5 的 no_ship / shadow band，
    #   但當時間窗恰使大樣本 run 也 sub-floor（holdout 落在兩分區間）時，§6.5 可能給
    #   should_ship —— 此封頂即在該情境下防止 ship gate 採信兩分指標（防禦縱深）。
    partition_mode = getattr(result, "partition_mode", "three_way")
    if partition_mode == "two_way_shadow_capped" and verdict == VERDICT_SHIP:
        verdict = VERDICT_SHADOW
        reason = (
            f"{reason}; two-way holdout fallback (sub-floor split, "
            f"metrics from shared single holdout) → capped at shadow_only"
        )

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

    return _maybe_persist(report, output_path, persist_required=persist_required)


def _maybe_persist(
    report: Dict[str, Any],
    output_path: Optional[str],
    *,
    persist_required: bool = False,
) -> Dict[str, Any]:
    """JSON-serialize report to output_path if provided; fail-soft.
    提供 output_path 時 JSON 持久化；預設失敗不中斷。persist_required=True 時
    fail-loud，供 contract-bound PIT gate 使用。"""
    if not output_path:
        if persist_required:
            raise RuntimeError("acceptance_report_output_path_required")
        return report
    try:
        path = Path(output_path)
        _atomic_write_json(path, report)
        logger.info("acceptance report persisted: %s", output_path)
    except Exception as e:  # noqa: BLE001
        if persist_required:
            raise RuntimeError(f"acceptance_report_persist_failed:{type(e).__name__}") from e
        logger.warning("acceptance report persist failed (non-fatal): %s", e)
    return report


def _atomic_write_json(path: Path, report: Dict[str, Any]) -> None:
    """先寫同目錄暫存 JSON，完整成功後才替換 final artifact。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.{id(report)}.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
        tmp_path.replace(path)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise
