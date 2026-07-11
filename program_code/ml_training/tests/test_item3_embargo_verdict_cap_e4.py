"""E4 驗證 — Item 3「embargo fail-open 封頂裁決」。
E4 verification for Item 3: when embargo is NOT enforced (trainer fail-open
silently disabled it on thin data), the acceptance-report verdict must be
CAPPED at shadow_only and can never be should_ship, and the boundary
label-realization overlap count must be surfaced in the report.

WHY THIS FILE EXISTS (為什麼另立 E4 檔):
  Item 3 的修復點在 quantile_reports.generate_acceptance_report 的 verdict 尾段
  (embargo_enforced=False 且 verdict==should_ship → 封頂 shadow_only)。此邏輯是純
  Python + numpy，完全不需 lightgbm/sklearn，故可在 Mac 直接跑真邏輯（非 mock）。
  本檔專測「verdict 函式在 embargo_enforced=False 時 verdict <= shadow_only」這條
  acceptance，並在 embargo_enforced=True 設對照組確保封頂只在「未強制」時生效
  （否則斷言變 vacuous）。

METHOD (方法):
  直接構造 QuantileTrainingResult（不呼叫任何訓練），設定 embargo_enforced 與
  embargo_overlap_count，餵進真正的 generate_acceptance_report，斷言 verdict 的
  序級與 report 的 overlap 欄位。零 IO、零 runtime、零 DB。
"""

from __future__ import annotations

import pytest

from program_code.ml_training.quantile_reports import (
    SAMPLE_GATE_PROD,
    SAMPLE_GATE_SHADOW,
    VERDICT_NO_SHIP,
    VERDICT_SHADOW,
    VERDICT_SHIP,
    generate_acceptance_report,
)
from program_code.ml_training.quantile_trainer import (
    EmbargoConfig,
    PerQuantileMetrics,
    QuantileTrainingConfig,
    QuantileTrainingResult,
)

# verdict 序級：should_ship(2) > shadow_only(1) > no_ship(0)。
# 「verdict <= shadow_only」= rank <= 1 = 不得為 should_ship。
_VERDICT_RANK = {VERDICT_NO_SHIP: 0, VERDICT_SHADOW: 1, VERDICT_SHIP: 2}


def _make_metrics(
    pinball_skill: float = 0.30,
    coverage_error_pp: float = 1.5,
    linear_qr_pinball_skill: float = 0.10,
    alpha: float = 0.50,
) -> PerQuantileMetrics:
    return PerQuantileMetrics(
        alpha=alpha,
        pinball_loss=0.5,
        pinball_loss_baseline_constant=1.0,
        pinball_skill=pinball_skill,
        empirical_coverage=alpha,
        coverage_error_pp=coverage_error_pp,
        best_iteration=50,
        n_train=400,
        n_holdout=100,
        linear_qr_pinball_loss=0.9,
        linear_qr_pinball_skill=linear_qr_pinball_skill,
    )


def _make_result(
    n_labeled: int,
    *,
    all_gates_passing: bool = True,
    embargo_enforced: bool = True,
    embargo_overlap_count: int = 0,
) -> QuantileTrainingResult:
    """構造成功的 QuantileTrainingResult；all_gates_passing 決定五個 metric gate 的
    通過與否，embargo_enforced / embargo_overlap_count 模擬 trainer 的 fail-open 狀態。"""
    skill = 0.30 if all_gates_passing else 0.05
    cov_err = 1.5 if all_gates_passing else 5.0
    linear_skill = 0.10 if all_gates_passing else 0.28
    crossing = 0.005 if all_gates_passing else 0.05
    lift_point = 2.0 if all_gates_passing else 1.0
    ci_lower = 1.6 if all_gates_passing else 0.8
    ci_upper = 2.4
    return QuantileTrainingResult(
        success=True,
        strategy_name="ma_crossover",
        engine_mode="demo",
        feature_names=["f0", "f1", "f2"],
        n_samples_total=n_labeled,
        n_samples_labeled=n_labeled,
        n_holdout=100,
        n_validation=25,
        n_calibration=25,
        n_test=50,
        models={"q10": object(), "q50": object(), "q90": object()},
        per_quantile_metrics={
            "q10": _make_metrics(skill, cov_err, linear_skill, 0.10),
            "q50": _make_metrics(skill, cov_err, linear_skill, 0.50),
            "q90": _make_metrics(skill, cov_err, linear_skill, 0.90),
        },
        decile_lift_point=lift_point,
        decile_lift_ci_lower=ci_lower,
        decile_lift_ci_upper=ci_upper,
        crossing_rate=crossing,
        feature_schema_hash="sha256:" + "0" * 16,
        feature_definition_hash="sha256:" + "1" * 16,
        embargo_config=EmbargoConfig(embargo_hours=24, holdout_tail_days=7.0),
        embargo_enforced=embargo_enforced,
        embargo_overlap_count=embargo_overlap_count,
    )


# ──────────────── 核心 acceptance：embargo_enforced=False → verdict <= shadow_only ────────────────

@pytest.mark.parametrize(
    "n_labeled, gates_pass",
    [
        (SAMPLE_GATE_SHADOW - 1, True),    # thin data → no_ship 桶（設計 acceptance 的「thin-data run」）
        (SAMPLE_GATE_SHADOW - 1, False),
        (SAMPLE_GATE_SHADOW + 50, True),   # mid 桶 → shadow_only
        (SAMPLE_GATE_SHADOW + 50, False),
        (SAMPLE_GATE_PROD + 50, True),     # full 桶 + 全 gate 過 → 本應 should_ship，須被封頂
        (SAMPLE_GATE_PROD + 50, False),    # full 桶 + gate 有失 → 已是 shadow
    ],
)
def test_embargo_not_enforced_caps_verdict_at_shadow_only(n_labeled, gates_pass):
    """embargo_enforced=False 時，任何樣本桶 / gate 組合下 verdict 都 <= shadow_only
    （絕不 should_ship）。這是 Item 3 的 acceptance 主張。"""
    cfg = QuantileTrainingConfig()
    res = _make_result(
        n_labeled,
        all_gates_passing=gates_pass,
        embargo_enforced=False,
        embargo_overlap_count=7,
    )
    report = generate_acceptance_report(res, cfg, include_train_serve_harness=False)
    verdict = report["verdict"]
    assert _VERDICT_RANK[verdict] <= _VERDICT_RANK[VERDICT_SHADOW], (
        f"embargo_enforced=False 應封頂 <= shadow_only，實得 {verdict} "
        f"(n_labeled={n_labeled}, gates_pass={gates_pass})"
    )
    assert verdict != VERDICT_SHIP


def test_full_sample_all_gates_pass_but_embargo_off_is_capped_to_shadow():
    """關鍵情境：full 樣本 + 五 gate 全過（本應 should_ship），因 embargo_enforced=False
    被硬性封頂到 shadow_only，且 reason 誠實揭露未強制 + overlap 計數。"""
    cfg = QuantileTrainingConfig()
    res = _make_result(
        SAMPLE_GATE_PROD + 50,
        all_gates_passing=True,
        embargo_enforced=False,
        embargo_overlap_count=11,
    )
    report = generate_acceptance_report(res, cfg, include_train_serve_harness=False)
    # 五個 metric gate 本身全過（證明封頂不是因 gate 失敗，而是因 embargo 未強制）。
    assert report["all_hard_gates_pass"] is True
    assert report["verdict"] == VERDICT_SHADOW
    assert "embargo NOT enforced" in report["verdict_reason"]
    assert "boundary_overlap=11" in report["verdict_reason"]


def test_thin_data_embargo_off_stays_no_ship():
    """設計 acceptance 逐字：thin-data run + embargo_enforced=False → verdict <= shadow_only
    （此處 no_ship，封頂邏輯不得把 no_ship 升級）。"""
    cfg = QuantileTrainingConfig()
    res = _make_result(
        SAMPLE_GATE_SHADOW - 10,
        all_gates_passing=True,
        embargo_enforced=False,
        embargo_overlap_count=3,
    )
    report = generate_acceptance_report(res, cfg, include_train_serve_harness=False)
    assert report["verdict"] == VERDICT_NO_SHIP
    assert _VERDICT_RANK[report["verdict"]] <= _VERDICT_RANK[VERDICT_SHADOW]


# ──────────────── overlap 計數落 report ────────────────

def test_overlap_count_present_in_report():
    """acceptance 第二半：boundary label-realization overlap count 出現在 report。"""
    cfg = QuantileTrainingConfig()
    res = _make_result(
        SAMPLE_GATE_PROD + 50,
        all_gates_passing=True,
        embargo_enforced=False,
        embargo_overlap_count=42,
    )
    report = generate_acceptance_report(res, cfg, include_train_serve_harness=False)
    assert "embargo_boundary_overlap_count" in report
    assert report["embargo_boundary_overlap_count"] == 42
    assert report["embargo_enforced"] is False


# ──────────────── 對照組：封頂只在「未強制」時生效（否則斷言 vacuous） ────────────────

def test_control_embargo_enforced_full_sample_ships():
    """對照：embargo_enforced=True + full 樣本 + 全 gate 過 → 正常 should_ship。
    證明 Item 3 的封頂只針對 embargo_enforced=False，未過度封鎖合法 ship 路徑。"""
    cfg = QuantileTrainingConfig()
    res = _make_result(
        SAMPLE_GATE_PROD + 50,
        all_gates_passing=True,
        embargo_enforced=True,
        embargo_overlap_count=0,
    )
    report = generate_acceptance_report(res, cfg, include_train_serve_harness=False)
    assert report["verdict"] == VERDICT_SHIP
    assert report["embargo_enforced"] is True
    assert "embargo NOT enforced" not in report["verdict_reason"]
