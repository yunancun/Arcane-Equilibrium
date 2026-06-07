from __future__ import annotations

import pytest

from program_code.ml_training.residual_alpha_report_contract import (
    RESIDUAL_ALPHA_REPORT_FIELD,
    extract_demo_residual_alpha_report,
    validate_demo_residual_alpha_report,
)


def _valid_report(**overrides):
    report = {
        "passes": True,
        "verdict": "pass",
        "reasons": [],
        "raw_mean_bps": 2.0,
        "residual_mean_bps": 1.4,
        "r_beta_retention": 0.7,
        "beta_edge_share": 0.3,
        "psr_raw": 0.97,
        "psr_residual": 0.98,
        "dsr_raw": 0.96,
        "dsr_residual": 0.97,
        "pbo_raw": 0.20,
        "pbo_residual": 0.10,
        "factor_panel_hash": "sha256:factor-panel",
        "fit_window": {
            "train_start": "2026-01-01",
            "train_end": "2026-01-31",
            "eval_start": "2026-02-01",
            "eval_end": "2026-02-15",
        },
        "coverage": {"train": 0.90, "eval": 0.85},
    }
    report.update(overrides)
    return report


def test_valid_report_passes_and_extracts_canonical():
    report = _valid_report()
    ok, reason = validate_demo_residual_alpha_report(report)

    assert ok is True
    assert reason == "ok"
    assert extract_demo_residual_alpha_report(
        {RESIDUAL_ALPHA_REPORT_FIELD: report}
    ) is report


def test_extract_rejects_alias_only_for_gate_paths():
    report = _valid_report()

    assert extract_demo_residual_alpha_report(
        {"residual_alpha_report": report}
    ) is None


def test_missing_pbo_reason_blocks_even_when_passes_true():
    report = _valid_report(
        pbo_raw=None,
        pbo_residual=None,
        reasons=["pbo_missing_candidate_returns"],
    )

    ok, reason = validate_demo_residual_alpha_report(report)

    assert ok is False
    assert reason == "forbidden_reason:pbo_missing_candidate_returns"


def test_core_diagnostic_reason_blocks_even_when_passes_true():
    report = _valid_report(
        reasons=["pbo_missing_candidate_returns_core_diagnostic_only"],
    )

    ok, reason = validate_demo_residual_alpha_report(report)

    assert ok is False
    assert reason == (
        "forbidden_reason:"
        "pbo_missing_candidate_returns_core_diagnostic_only"
    )


@pytest.mark.parametrize(
    ("mutator", "expected_reason"),
    [
        (lambda r: r.pop("factor_panel_hash"), "factor_panel_hash_missing"),
        (lambda r: r.pop("fit_window"), "fit_window_missing"),
        (lambda r: r.pop("psr_raw"), "metric_missing:psr_raw"),
        (lambda r: r.update({"raw_mean_bps": 0.0}), "raw_mean_non_positive"),
        (
            lambda r: r.update({"fit_window": {"train_end": 10, "eval_start": 10}}),
            "fit_window_not_prior",
        ),
    ],
)
def test_passes_true_but_missing_hash_window_or_metrics_blocks(
    mutator,
    expected_reason,
):
    report = _valid_report()
    mutator(report)

    ok, reason = validate_demo_residual_alpha_report(report)

    assert ok is False
    assert reason == expected_reason


# ---- Gap C：permutation additive 校驗（backward-compat + 啟用時強制）----


def test_old_report_without_perm_field_still_validates():
    """★ backward-compat：舊 report（無 perm_p_value 欄位）必須仍可驗 → ok。"""
    report = _valid_report()
    assert "perm_p_value" not in report
    ok, reason = validate_demo_residual_alpha_report(report)
    assert ok is True
    assert reason == "ok"


def test_report_with_significant_perm_validates():
    """report 帶 perm_p_value 且顯著（<= 門檻）→ ok。"""
    report = _valid_report(perm_p_value=0.01, perm_iterations=2000)
    ok, reason = validate_demo_residual_alpha_report(report)
    assert ok is True
    assert reason == "ok"


def test_report_with_perm_above_threshold_blocks():
    """report 帶 perm_p_value 但 > 門檻 → fail（虛無無法拒絕，不得 pass）。"""
    report = _valid_report(perm_p_value=0.20, perm_iterations=2000)
    ok, reason = validate_demo_residual_alpha_report(report)
    assert ok is False
    assert reason == "perm_p_value_above_threshold"


def test_report_with_perm_none_blocks():
    """report 帶 perm_p_value=None（啟用但 insufficient n）→ metric_missing。"""
    report = _valid_report(perm_p_value=None, perm_iterations=0)
    ok, reason = validate_demo_residual_alpha_report(report)
    assert ok is False
    assert reason == "metric_missing:perm_p_value"


def test_require_permutation_flag_enforces_presence(monkeypatch):
    """REQUIRE_PERMUTATION=True 時，缺 perm_p_value 的 report → fail。"""
    from program_code.ml_training import residual_alpha_report_contract as rc

    monkeypatch.setattr(rc, "REQUIRE_PERMUTATION", True)
    report = _valid_report()  # 無 perm 欄位
    ok, reason = rc.validate_demo_residual_alpha_report(report)
    assert ok is False
    assert reason == "perm_p_value_missing"
    # 帶顯著 perm 則通過
    report2 = _valid_report(perm_p_value=0.01)
    ok2, reason2 = rc.validate_demo_residual_alpha_report(report2)
    assert ok2 is True and reason2 == "ok"
