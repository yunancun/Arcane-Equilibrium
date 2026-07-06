"""Tests for quantile_reports acceptance report verdict logic.
quantile_reports 驗收報告裁決邏輯測試。"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from program_code.ml_training.quantile_reports import (
    SAMPLE_GATE_PROD,
    SAMPLE_GATE_SHADOW,
    THRESH_COVERAGE_ERROR_PP_MAX,
    THRESH_CROSSING_RATE_MAX,
    THRESH_DECILE_LIFT_CI_LOWER_MIN,
    THRESH_DECILE_LIFT_POINT_MIN,
    THRESH_LGBM_VS_LINEAR_QR_MIN_DIFF,
    THRESH_PINBALL_SKILL_MIN,
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
    n_labeled: int = 600,
    all_gates_passing: bool = True,
) -> QuantileTrainingResult:
    """Craft a canonical-success result; caller mutates to simulate gate failures.
    構造經典成功結果；呼叫端變更以模擬 gate 失敗。"""
    skill = 0.30 if all_gates_passing else 0.05
    cov_err = 1.5 if all_gates_passing else 5.0
    linear_skill = 0.10 if all_gates_passing else 0.28
    crossing = 0.005 if all_gates_passing else 0.05
    lift_point = 2.0 if all_gates_passing else 1.0
    ci_lower = 1.6 if all_gates_passing else 0.8
    ci_upper = 2.4
    result = QuantileTrainingResult(
        success=True,
        strategy_name="ma_crossover",
        engine_mode="demo",
        feature_names=["f0", "f1", "f2"],
        n_samples_total=n_labeled,
        n_samples_labeled=n_labeled,
        n_holdout=100,
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
        embargo_config=EmbargoConfig(n_folds=5, embargo_hours=24, holdout_tail_days=7.0),
    )
    return result


# ──────────────── verdict routing ────────────────

def test_verdict_no_ship_when_sample_below_shadow_gate():
    cfg = QuantileTrainingConfig()
    res = _make_result(n_labeled=SAMPLE_GATE_SHADOW - 1, all_gates_passing=True)
    report = generate_acceptance_report(res, cfg, include_train_serve_harness=False)
    assert report["verdict"] == VERDICT_NO_SHIP


def test_verdict_shadow_when_sample_between_gates_even_with_metrics_passing():
    cfg = QuantileTrainingConfig()
    res = _make_result(n_labeled=SAMPLE_GATE_SHADOW + 50, all_gates_passing=True)
    report = generate_acceptance_report(res, cfg, include_train_serve_harness=False)
    assert report["verdict"] == VERDICT_SHADOW


def test_verdict_ship_when_full_sample_and_all_gates_pass():
    cfg = QuantileTrainingConfig()
    res = _make_result(n_labeled=SAMPLE_GATE_PROD + 50, all_gates_passing=True)
    report = generate_acceptance_report(res, cfg, include_train_serve_harness=False)
    assert report["verdict"] == VERDICT_SHIP
    assert report["all_hard_gates_pass"] is True


def test_verdict_downgrades_to_shadow_when_gates_fail_despite_full_sample():
    cfg = QuantileTrainingConfig()
    res = _make_result(n_labeled=SAMPLE_GATE_PROD + 50, all_gates_passing=False)
    report = generate_acceptance_report(res, cfg, include_train_serve_harness=False)
    assert report["verdict"] == VERDICT_SHADOW
    assert report["all_hard_gates_pass"] is False


# ──────────────── P1-3 label composition gate ────────────────

def test_label_composition_gate_absent_passes_as_unavailable():
    """composition 未提供（dry-run / 舊呼叫端）→ gate pass 且標 unavailable，
    不影響既有 5 gate 全通過的 ship 裁決（向後相容）。"""
    cfg = QuantileTrainingConfig()
    res = _make_result(n_labeled=SAMPLE_GATE_PROD + 50, all_gates_passing=True)
    report = generate_acceptance_report(res, cfg, include_train_serve_harness=False)
    assert report["gates"]["label_composition"]["passed"] is True
    assert report["gates"]["label_composition"]["source"] == "unavailable"
    assert report["verdict"] == VERDICT_SHIP


def test_label_composition_gate_synthetic_present_downgrades_to_shadow():
    """synthetic_share > 0（過濾退化）即使 5 metric gate 全過也封頂 shadow_only。
    這是 P1-3 的 fail-closed 核心：合成 label 混入 = 不可 ship。"""
    cfg = QuantileTrainingConfig()
    res = _make_result(n_labeled=SAMPLE_GATE_PROD + 50, all_gates_passing=True)
    composition = {
        "n_total": 1000, "n_informative": 900, "n_synthetic_reject": 100,
        "synthetic_share": 0.1, "zeros_share": 0.1,
        "top_close_tags": [["<null>", 900], ["rejected_governance", 100]],
    }
    report = generate_acceptance_report(
        res, cfg, include_train_serve_harness=False, label_composition=composition,
    )
    assert report["gates"]["label_composition"]["passed"] is False
    assert report["all_hard_gates_pass"] is False
    assert report["verdict"] == VERDICT_SHADOW
    assert "label_composition" in report["verdict_reason"]


def test_label_composition_gate_high_zeros_share_downgrades_to_shadow():
    """zeros_share > 0.5（常數 0 標籤 = 常數預測器指紋）即使無合成 label 也封頂。"""
    cfg = QuantileTrainingConfig()
    res = _make_result(n_labeled=SAMPLE_GATE_PROD + 50, all_gates_passing=True)
    composition = {
        "n_total": 1000, "n_informative": 1000, "n_synthetic_reject": 0,
        "synthetic_share": 0.0, "zeros_share": 0.6,
        "top_close_tags": [["<null>", 1000]],
    }
    report = generate_acceptance_report(
        res, cfg, include_train_serve_harness=False, label_composition=composition,
    )
    assert report["gates"]["label_composition"]["passed"] is False
    assert report["verdict"] == VERDICT_SHADOW


def test_label_composition_gate_clean_passes():
    """synthetic_share == 0 且 zeros_share ≤ 0.5 → gate pass，落 report 供溯源。"""
    cfg = QuantileTrainingConfig()
    res = _make_result(n_labeled=SAMPLE_GATE_PROD + 50, all_gates_passing=True)
    composition = {
        "n_total": 1000, "n_informative": 1000, "n_synthetic_reject": 0,
        "synthetic_share": 0.0, "zeros_share": 0.2,
        "top_close_tags": [["<null>", 1000]],
    }
    report = generate_acceptance_report(
        res, cfg, include_train_serve_harness=False, label_composition=composition,
    )
    assert report["gates"]["label_composition"]["passed"] is True
    assert report["verdict"] == VERDICT_SHIP
    assert report["label_composition"] == composition


# ──────────────── individual gate behaviour ────────────────

def test_gate_pinball_skill_threshold_exact_boundary():
    cfg = QuantileTrainingConfig()
    res = _make_result(n_labeled=SAMPLE_GATE_PROD + 10)
    # Set all three skills to exactly the threshold (strict > not >=).
    # 所有分位 skill 卡在閾值（嚴格 > 而非 >=）。
    for m in res.per_quantile_metrics.values():
        m.pinball_skill = THRESH_PINBALL_SKILL_MIN
    report = generate_acceptance_report(res, cfg, include_train_serve_harness=False)
    assert report["gates"]["pinball_skill"]["passed"] is False


def test_gate_coverage_uses_post_cqr_when_provided():
    cfg = QuantileTrainingConfig()
    res = _make_result(n_labeled=SAMPLE_GATE_PROD + 10)
    # Pre-CQR says gates fail (5pp err); post-CQR says 1pp — report must pass.
    # pre-CQR 看 5pp 失敗；post-CQR 看 1pp 應通過。
    for m in res.per_quantile_metrics.values():
        m.coverage_error_pp = 5.0
    post_coverage = {
        "q10": (0.10, 1.0),
        "q50": (0.50, 1.0),
        "q90": (0.90, 1.0),
    }
    report = generate_acceptance_report(
        res, cfg, post_cqr_coverage=post_coverage, include_train_serve_harness=False,
    )
    assert report["gates"]["coverage_error"]["passed"] is True
    for key in ("q10", "q50", "q90"):
        assert report["gates"]["coverage_error"]["per_quantile"][key]["source"] == "post_cqr"


def test_gate_linear_qr_unavailable_treated_as_pass():
    cfg = QuantileTrainingConfig()
    res = _make_result(n_labeled=SAMPLE_GATE_PROD + 10)
    # Simulate sklearn-absent training environment.
    # 模擬 sklearn 缺席環境。
    for m in res.per_quantile_metrics.values():
        m.linear_qr_pinball_skill = None
    report = generate_acceptance_report(res, cfg, include_train_serve_harness=False)
    floor = report["gates"]["lgbm_vs_linear_qr"]
    assert floor["passed"] is True
    for key in ("q10", "q50", "q90"):
        assert floor["per_quantile"][key]["source"] == "unavailable"


def test_gate_decile_lift_requires_both_point_and_ci():
    cfg = QuantileTrainingConfig()
    res = _make_result(n_labeled=SAMPLE_GATE_PROD + 10)
    # Point estimate below threshold even with wide CI → fail.
    # 點估計低於閾值即便 CI 寬 → fail。
    res.decile_lift_point = THRESH_DECILE_LIFT_POINT_MIN - 0.1
    res.decile_lift_ci_lower = THRESH_DECILE_LIFT_CI_LOWER_MIN + 0.1
    report = generate_acceptance_report(res, cfg, include_train_serve_harness=False)
    assert report["gates"]["decile_lift"]["passed"] is False


def test_training_error_short_circuits_to_no_ship():
    cfg = QuantileTrainingConfig()
    res = QuantileTrainingResult(
        success=False, error="lgb fit failed: synthetic",
        strategy_name="x", engine_mode="demo",
        n_samples_total=1000, n_samples_labeled=1000,
    )
    report = generate_acceptance_report(res, cfg, include_train_serve_harness=False)
    assert report["verdict"] == VERDICT_NO_SHIP
    assert "training failed" in report["verdict_reason"]


# ──────────────── persistence + harness ────────────────

def test_acceptance_report_json_persistence(tmp_path: Path):
    cfg = QuantileTrainingConfig()
    res = _make_result(n_labeled=SAMPLE_GATE_PROD + 50)
    out = tmp_path / "report.json"
    report = generate_acceptance_report(
        res, cfg, output_path=str(out), include_train_serve_harness=False,
    )
    assert out.exists()
    with out.open() as f:
        loaded = json.load(f)
    assert loaded["verdict"] == report["verdict"]


def test_acceptance_report_defaults_to_not_contract_bound_pit_binding():
    cfg = QuantileTrainingConfig()
    res = _make_result(n_labeled=SAMPLE_GATE_PROD + 50)

    report = generate_acceptance_report(res, cfg, include_train_serve_harness=False)

    assert report["pit_dataset_manifest"] is None
    binding = report["pit_dataset_manifest_binding"]
    assert binding["schema_version"] == "training_pit_manifest_binding_v1"
    assert binding["contract_bound_run"] is False
    assert binding["status"] == "not_contract_bound"
    assert binding["validation_verdict"] == "not_required"
    assert binding["validation_reason"] == "not_contract_bound"
    assert binding["runtime_mutation_performed"] is False
    assert binding["db_write_performed"] is False
    assert binding["exchange_private_read_performed"] is False
    assert binding["order_or_probe_performed"] is False
    assert binding["live_or_mainnet_performed"] is False


def test_acceptance_report_attaches_pit_manifest_and_binding(tmp_path: Path):
    cfg = QuantileTrainingConfig()
    res = _make_result(n_labeled=SAMPLE_GATE_PROD + 50)
    manifest = {"schema_version": "pit_dataset_manifest_v1", "manifest_hash": "a" * 64}
    binding = {
        "schema_version": "training_pit_manifest_binding_v1",
        "contract_bound_run": True,
        "status": "dataset_ready",
        "manifest_hash": "a" * 64,
        "manifest_path": str(tmp_path / "manifest.json"),
        "validation_verdict": "dataset_ready",
        "validation_reason": "ok",
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
    out = tmp_path / "report.json"

    report = generate_acceptance_report(
        res,
        cfg,
        output_path=str(out),
        include_train_serve_harness=False,
        pit_dataset_manifest=manifest,
        pit_dataset_manifest_binding=binding,
        persist_required=True,
    )

    loaded = json.loads(out.read_text())
    assert report["pit_dataset_manifest"] == manifest
    assert report["pit_dataset_manifest_binding"] == binding
    assert loaded["pit_dataset_manifest"] == manifest
    assert loaded["pit_dataset_manifest_binding"] == binding


def test_acceptance_report_required_persist_failure_preserves_existing_final(
    monkeypatch, tmp_path: Path,
):
    cfg = QuantileTrainingConfig()
    res = _make_result(n_labeled=SAMPLE_GATE_PROD + 50)
    out = tmp_path / "report.json"
    old_payload = '{"old": true}'
    out.write_text(old_payload, encoding="utf-8")
    seen = {"same_dir": False, "tmp_name": ""}

    def failing_dump(_report, file_obj, *args, **kwargs):
        tmp_path_seen = Path(file_obj.name)
        seen["same_dir"] = tmp_path_seen.parent == out.parent
        seen["tmp_name"] = tmp_path_seen.name
        file_obj.write('{"partial":')
        raise OSError("synthetic json dump failure")

    monkeypatch.setattr(
        "program_code.ml_training.quantile_reports.json.dump",
        failing_dump,
    )

    with pytest.raises(RuntimeError, match="acceptance_report_persist_failed:OSError"):
        generate_acceptance_report(
            res,
            cfg,
            output_path=str(out),
            include_train_serve_harness=False,
            persist_required=True,
        )

    assert out.read_text(encoding="utf-8") == old_payload
    assert seen["same_dir"] is True
    assert seen["tmp_name"] != out.name


def test_acceptance_report_optional_persist_failure_preserves_existing_final(
    monkeypatch, tmp_path: Path,
):
    cfg = QuantileTrainingConfig()
    res = _make_result(n_labeled=SAMPLE_GATE_PROD + 50)
    out = tmp_path / "report.json"
    old_payload = '{"old": true}'
    out.write_text(old_payload, encoding="utf-8")

    def failing_dump(_report, file_obj, *args, **kwargs):
        file_obj.write('{"partial":')
        raise OSError("synthetic json dump failure")

    monkeypatch.setattr(
        "program_code.ml_training.quantile_reports.json.dump",
        failing_dump,
    )

    report = generate_acceptance_report(
        res,
        cfg,
        output_path=str(out),
        include_train_serve_harness=False,
    )

    assert report["verdict"] == VERDICT_SHIP
    assert out.read_text(encoding="utf-8") == old_payload


def test_train_serve_harness_shape():
    """Harness shipped only when lightgbm available (booster.predict callable).
    仰賴 lightgbm 的 harness；缺失則 skip。"""
    lgb = pytest.importorskip("lightgbm")
    # Build a tiny real booster so predict() works.
    # 建立微型真實 booster 供 predict() 使用。
    rng = np.random.default_rng(0)
    n, nf = 200, 5
    X = rng.standard_normal((n, nf)).astype(np.float32)
    y = X[:, 0] + rng.standard_normal(n) * 0.1
    ds = lgb.Dataset(X, label=y)
    booster = lgb.train({"objective": "quantile", "alpha": 0.5, "verbose": -1}, ds, num_boost_round=10)

    cfg = QuantileTrainingConfig()
    res = _make_result(n_labeled=SAMPLE_GATE_PROD + 50)
    res.models = {"q10": booster, "q50": booster, "q90": booster}
    res.feature_names = [f"f{i}" for i in range(nf)]

    report = generate_acceptance_report(
        res, cfg, include_train_serve_harness=True, harness_n_samples=100,
    )
    harness = report["train_serve_harness"]
    assert harness["n_features"] == nf
    assert harness["n_samples"] == 100
    assert len(harness["samples"]) == 100
    assert set(harness["predictions"].keys()) == {"q10", "q50", "q90"}
    assert len(harness["predictions"]["q50"]) == 100
