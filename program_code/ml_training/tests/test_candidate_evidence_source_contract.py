from __future__ import annotations

import hashlib
import json

from ml_training.candidate_evidence_manifest import (
    CANDIDATE_EVIDENCE_MANIFEST_FIELD,
    CANDIDATE_EVIDENCE_MANIFEST_SCHEMA_VERSION,
    PROMOTION_READY,
    compute_candidate_evidence_manifest_hash,
)
from ml_training.candidate_evidence_source_contract import (
    build_live_candidate_evidence_from_source,
)
from ml_training.residual_alpha_report_contract import RESIDUAL_ALPHA_REPORT_FIELD


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


def _valid_manifest(**overrides) -> dict:
    residual_report = _valid_residual_alpha_report()
    manifest = {
        "schema_version": CANDIDATE_EVIDENCE_MANIFEST_SCHEMA_VERSION,
        "verdict": PROMOTION_READY,
        "candidate_id": "candidate-alpha-1",
        "family_id": "family-alpha",
        "spec_hash": "a" * 64,
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


def _source_row(**overrides) -> dict:
    row = {
        "id": 12,
        "evidence_source_tier": "calibrated_replay",
        "replay_experiment_id": "replay-exp-1",
        "manifest_hash": bytes.fromhex("c" * 64),
        "replay_registry_status": "completed",
        "replay_registry_expires_at": "2999-01-01T00:00:00+00:00",
        "replay_registry_manifest_hash": "c" * 64,
        "replay_registry_manifest_jsonb": {"registry": "manifest"},
        "replay_registry_oos_label_window_start": "2026-05-01T00:00:00Z",
        "replay_registry_oos_label_window_end": "2026-05-08T00:00:00Z",
        "replay_registry_oos_embargo_seconds": 86400,
        "replay_registry_total_candidates_k": 12,
        "payload": {
            RESIDUAL_ALPHA_REPORT_FIELD: _valid_residual_alpha_report(),
            CANDIDATE_EVIDENCE_MANIFEST_FIELD: _valid_manifest(),
        },
    }
    row.update(overrides)
    return row


def test_source_contract_accepts_row_level_replay_lineage():
    build = build_live_candidate_evidence_from_source(_source_row())

    assert build.validation.promotion_ready is True
    assert build.residual_report is not None
    assert build.manifest is not None
    assert build.source_tier == "calibrated_replay"
    assert build.replay_experiment_id == "replay-exp-1"
    assert build.replay_manifest_hash == "c" * 64


def test_source_contract_accepts_counterfactual_replay_with_registry():
    build = build_live_candidate_evidence_from_source(
        _source_row(evidence_source_tier="counterfactual_replay")
    )

    assert build.validation.promotion_ready is True
    assert build.source_tier == "counterfactual_replay"


def test_source_contract_rejects_missing_source_tier():
    row = _source_row()
    row.pop("evidence_source_tier")

    build = build_live_candidate_evidence_from_source(row)

    assert build.validation.promotion_ready is False
    assert build.validation.reason == (
        "evidence_source_tier_not_promotion_ready:missing"
    )


def test_source_contract_rejects_synthetic_source_tier():
    build = build_live_candidate_evidence_from_source(
        _source_row(evidence_source_tier="synthetic_replay")
    )

    assert build.validation.promotion_ready is False
    assert build.validation.verdict == "research_only"
    assert build.validation.reason == (
        "evidence_source_tier_not_promotion_ready:synthetic_replay"
    )


def test_source_contract_rejects_real_outcome_source_tier():
    build = build_live_candidate_evidence_from_source(
        _source_row(evidence_source_tier="real_outcome")
    )

    assert build.validation.promotion_ready is False
    assert build.validation.reason == (
        "evidence_source_tier_not_promotion_ready:real_outcome"
    )


def test_source_contract_rejects_payload_lineage_without_row_lineage():
    row = _source_row()
    row.pop("replay_experiment_id")
    row["payload"]["lineage"] = {
        "replay_experiment_id": "payload-only",
        "manifest_hash": "d" * 64,
    }

    build = build_live_candidate_evidence_from_source(row)

    assert build.validation.promotion_ready is False
    assert build.validation.reason == "source_replay_experiment_id_missing"


def test_source_contract_rejects_missing_registry_snapshot():
    row = _source_row()
    row.pop("replay_registry_manifest_jsonb")

    build = build_live_candidate_evidence_from_source(row)

    assert build.validation.promotion_ready is False
    assert build.validation.reason == "replay_registry_manifest_jsonb_missing"


def test_source_contract_rejects_registry_manifest_hash_mismatch():
    build = build_live_candidate_evidence_from_source(
        _source_row(replay_registry_manifest_hash="d" * 64)
    )

    assert build.validation.promotion_ready is False
    assert build.validation.reason == "replay_registry_manifest_hash_mismatch"


def test_source_contract_rejects_uncompleted_registry_status():
    build = build_live_candidate_evidence_from_source(
        _source_row(replay_registry_status="running")
    )

    assert build.validation.promotion_ready is False
    assert build.validation.reason == "replay_registry_status_not_completed:running"


def test_source_contract_rejects_expired_registry_snapshot():
    build = build_live_candidate_evidence_from_source(
        _source_row(replay_registry_expires_at="2000-01-01T00:00:00+00:00")
    )

    assert build.validation.promotion_ready is False
    assert build.validation.reason == "replay_registry_expired"


def test_source_contract_rejects_manifest_replay_hash_mismatch():
    manifest = _valid_manifest(replay_manifest_hash="d" * 64)

    build = build_live_candidate_evidence_from_source(
        _source_row(payload={
            RESIDUAL_ALPHA_REPORT_FIELD: _valid_residual_alpha_report(),
            CANDIDATE_EVIDENCE_MANIFEST_FIELD: manifest,
        })
    )

    assert build.validation.promotion_ready is False
    assert build.validation.reason == "replay_manifest_hash_source_mismatch"


def test_source_contract_rejects_hidden_oos_registry_window_mismatch():
    manifest = _valid_manifest(
        hidden_oos={
            "split_hash": "b" * 64,
            "window_start": "2026-06-01T00:00:00Z",
            "window_end": "2026-06-08T00:00:00Z",
            "embargo": "1d",
            "trial_count": 12,
            "passes": True,
        }
    )

    build = build_live_candidate_evidence_from_source(
        _source_row(payload={
            RESIDUAL_ALPHA_REPORT_FIELD: _valid_residual_alpha_report(),
            CANDIDATE_EVIDENCE_MANIFEST_FIELD: manifest,
        })
    )

    assert build.validation.promotion_ready is False
    assert build.validation.reason == "hidden_oos_registry_window_mismatch"
