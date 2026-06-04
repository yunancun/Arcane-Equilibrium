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
