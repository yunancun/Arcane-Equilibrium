from __future__ import annotations

import hashlib
import json

import pytest

from ml_training.candidate_evidence_manifest import (
    CANDIDATE_EVIDENCE_MANIFEST_FIELD,
    CANDIDATE_EVIDENCE_MANIFEST_SCHEMA_VERSION,
    INVALID,
    PENDING_SCHEMA,
    PROMOTION_READY,
    RESEARCH_ONLY,
    compute_candidate_evidence_manifest_hash,
    extract_candidate_evidence_manifest,
    validate_candidate_evidence_manifest,
)
from ml_training.candidate_signal_spec import (
    SIGNAL_SPEC_SCHEMA_VERSION,
    compute_signal_spec_hash,
)


def _valid_residual_alpha_report(**overrides) -> dict:
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
        "fit_window": {"train_end": 79, "eval_start": 80},
        "coverage": {"train": 0.90, "eval": 0.85},
    }
    report.update(overrides)
    return report


def _canonical_sha256(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()


def _valid_signal_spec(**overrides) -> dict:
    spec = {
        "schema_version": SIGNAL_SPEC_SCHEMA_VERSION,
        "candidate_id": "candidate-alpha-1",
        "family_id": "family-alpha",
        "hypothesis": "funding and orderbook imbalance residual alpha",
        "horizon": {"bars": 12, "unit": "1m"},
        "inputs": ["funding_rate", "orderbook_imbalance_top5", "BTCUSDT_return"],
        "pit_contract": {
            "point_in_time": True,
            "future_data_allowed": False,
        },
        "universe_ref": {"source": "research.alpha_symbol_universe", "hash": "u"},
        "regime_ref": {"source": "research.aeg_regime_labels", "hash": "r"},
        "feature_schema": {"version": "edge17"},
        "cost_model_ref": {"source": "demo_cost_baseline", "version": "v1"},
        "residualization": {
            "method": "ols",
            "factors": ["BTCUSDT_return", "pit_universe_equal_weight_return"],
        },
        "failure_taxonomy": ["beta_edge", "cost_defeat", "data_leak"],
        "hidden_oos_policy": {"state_required": "sealed", "open_once": True},
    }
    spec.update(overrides)
    return spec


def _valid_manifest(**overrides) -> dict:
    residual_report = _valid_residual_alpha_report()
    signal_spec = _valid_signal_spec()
    manifest = {
        "schema_version": CANDIDATE_EVIDENCE_MANIFEST_SCHEMA_VERSION,
        "verdict": PROMOTION_READY,
        "candidate_id": "candidate-alpha-1",
        "family_id": "family-alpha",
        "spec_hash": compute_signal_spec_hash(signal_spec),
        "replay_experiment_id": "replay-exp-1",
        "replay_manifest_hash": "c" * 64,
        "demo_residual_alpha_report_hash": _canonical_sha256(residual_report),
        "hidden_oos": {
            "split_hash": "b" * 64,
            "window_start": "2026-05-01T00:00:00Z",
            "window_end": "2026-05-08T00:00:00Z",
            "embargo": "1d",
            "trial_count": 12,
            "passes": True,
        },
    }
    manifest.update(overrides)
    manifest["manifest_hash"] = compute_candidate_evidence_manifest_hash(manifest)
    return manifest


def test_valid_manifest_is_promotion_ready():
    validation = validate_candidate_evidence_manifest(
        _valid_manifest(),
        residual_report=_valid_residual_alpha_report(),
        signal_spec=_valid_signal_spec(),
    )

    assert validation.promotion_ready is True
    assert validation.verdict == PROMOTION_READY
    assert validation.reason == "ok"


def test_extract_reads_only_canonical_field():
    manifest = _valid_manifest()

    assert extract_candidate_evidence_manifest(
        {CANDIDATE_EVIDENCE_MANIFEST_FIELD: manifest}
    ) == manifest
    assert extract_candidate_evidence_manifest({"evidence_manifest": manifest}) is None


def test_manifest_hash_is_key_order_stable():
    manifest_a = _valid_manifest()
    manifest_b = {
        "hidden_oos": dict(reversed(list(manifest_a["hidden_oos"].items()))),
        "demo_residual_alpha_report_hash": manifest_a[
            "demo_residual_alpha_report_hash"
        ],
        "replay_manifest_hash": manifest_a["replay_manifest_hash"],
        "replay_experiment_id": manifest_a["replay_experiment_id"],
        "spec_hash": manifest_a["spec_hash"],
        "family_id": manifest_a["family_id"],
        "candidate_id": manifest_a["candidate_id"],
        "verdict": manifest_a["verdict"],
        "schema_version": manifest_a["schema_version"],
    }

    assert compute_candidate_evidence_manifest_hash(manifest_a) == (
        compute_candidate_evidence_manifest_hash(manifest_b)
    )


def test_manifest_hash_mismatch_is_invalid():
    manifest = _valid_manifest()
    manifest["manifest_hash"] = "0" * 64

    validation = validate_candidate_evidence_manifest(
        manifest,
        residual_report=_valid_residual_alpha_report(),
        signal_spec=_valid_signal_spec(),
    )

    assert validation.promotion_ready is False
    assert validation.verdict == INVALID
    assert validation.reason == "manifest_hash_mismatch"


def test_nested_manifest_hash_tamper_is_invalid():
    manifest = _valid_manifest()
    manifest["hidden_oos"]["manifest_hash"] = "nested-tamper"

    validation = validate_candidate_evidence_manifest(
        manifest,
        residual_report=_valid_residual_alpha_report(),
        signal_spec=_valid_signal_spec(),
    )

    assert validation.promotion_ready is False
    assert validation.verdict == INVALID
    assert validation.reason == "manifest_hash_mismatch"


@pytest.mark.parametrize(
    ("mutator", "expected_reason"),
    [
        (lambda manifest: manifest.pop("family_id"), "family_id_missing"),
        (lambda manifest: manifest.pop("spec_hash"), "spec_hash_missing"),
        (lambda manifest: manifest.pop("hidden_oos"), "hidden_oos_missing"),
        (
            lambda manifest: manifest.pop("replay_experiment_id"),
            "replay_experiment_id_missing",
        ),
        (
            lambda manifest: manifest.pop("replay_manifest_hash"),
            "replay_manifest_hash_missing",
        ),
        (
            lambda manifest: manifest.pop("demo_residual_alpha_report_hash"),
            "demo_residual_alpha_report_hash_missing",
        ),
        (lambda manifest: manifest.pop("manifest_hash"), "manifest_hash_missing"),
    ],
)
def test_missing_required_fields_are_pending_schema(mutator, expected_reason):
    manifest = _valid_manifest()
    mutator(manifest)

    validation = validate_candidate_evidence_manifest(
        manifest,
        residual_report=_valid_residual_alpha_report(),
        signal_spec=_valid_signal_spec(),
    )

    assert validation.promotion_ready is False
    assert validation.verdict == PENDING_SCHEMA
    assert validation.reason == expected_reason


def test_hidden_oos_reuse_is_research_only():
    manifest = _valid_manifest(
        hidden_oos={
            "split_hash": "b" * 64,
            "window_start": "2026-05-01T00:00:00Z",
            "window_end": "2026-05-08T00:00:00Z",
            "embargo": "1d",
            "trial_count": 12,
            "opened_for_iteration": True,
        }
    )

    validation = validate_candidate_evidence_manifest(
        manifest,
        residual_report=_valid_residual_alpha_report(),
        signal_spec=_valid_signal_spec(),
    )

    assert validation.promotion_ready is False
    assert validation.verdict == RESEARCH_ONLY
    assert validation.reason == "hidden_oos_reused"


def test_missing_residual_report_is_invalid():
    validation = validate_candidate_evidence_manifest(
        _valid_manifest(),
        signal_spec=_valid_signal_spec(),
    )

    assert validation.promotion_ready is False
    assert validation.verdict == INVALID
    assert validation.reason == "residual_alpha:not_dict"


def test_core_diagnostic_residual_report_is_invalid():
    validation = validate_candidate_evidence_manifest(
        _valid_manifest(),
        residual_report=_valid_residual_alpha_report(
            reasons=["pbo_missing_candidate_returns_core_diagnostic_only"],
        ),
        signal_spec=_valid_signal_spec(),
    )

    assert validation.promotion_ready is False
    assert validation.verdict == INVALID
    assert validation.reason.startswith("residual_alpha:forbidden_reason:")


def test_residual_report_hash_mismatch_is_invalid():
    validation = validate_candidate_evidence_manifest(
        _valid_manifest(),
        residual_report=_valid_residual_alpha_report(raw_mean_bps=3.0),
        signal_spec=_valid_signal_spec(),
    )

    assert validation.promotion_ready is False
    assert validation.verdict == INVALID
    assert validation.reason == "demo_residual_alpha_report_hash_mismatch"


@pytest.mark.parametrize("verdict", [RESEARCH_ONLY, PENDING_SCHEMA, INVALID])
def test_non_promotion_verdict_never_passes(verdict):
    validation = validate_candidate_evidence_manifest(
        _valid_manifest(verdict=verdict),
        residual_report=_valid_residual_alpha_report(),
        signal_spec=_valid_signal_spec(),
    )

    assert validation.promotion_ready is False
    assert validation.verdict == verdict
    assert validation.reason == f"verdict_not_promotion_ready:{verdict}"
