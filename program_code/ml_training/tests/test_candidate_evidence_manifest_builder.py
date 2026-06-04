from __future__ import annotations

from ml_training.candidate_evidence_manifest import (
    CANDIDATE_EVIDENCE_MANIFEST_FIELD,
    CANDIDATE_EVIDENCE_MANIFEST_SCHEMA_VERSION,
    INVALID,
    PENDING_SCHEMA,
    PROMOTION_READY,
    RESEARCH_ONLY,
    compute_candidate_evidence_manifest_hash,
)
from ml_training.candidate_evidence_manifest_builder import (
    build_candidate_evidence_manifest_from_source,
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


def _valid_manifest(**overrides) -> dict:
    manifest = {
        "schema_version": CANDIDATE_EVIDENCE_MANIFEST_SCHEMA_VERSION,
        "verdict": PROMOTION_READY,
        "candidate_id": "candidate-alpha-1",
        "family_id": "family-alpha",
        "spec_hash": "a" * 64,
        "replay_experiment_id": "replay-exp-1",
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


def _source_row_from_fields(**payload_overrides) -> dict:
    payload = {
        "candidate_id": "candidate-alpha-1",
        "candidate_family_id": "family-alpha",
        "signal_spec_hash": "a" * 64,
        "hidden_oos": {
            "split_hash": "b" * 64,
            "window_start": "2026-05-01T00:00:00Z",
            "window_end": "2026-05-08T00:00:00Z",
            "embargo": "1d",
            "trial_count": 12,
            "passes": True,
        },
    }
    payload.update(payload_overrides)
    return {
        "id": 12,
        "replay_experiment_id": "replay-exp-1",
        "manifest_hash": bytes.fromhex("c" * 64),
        "payload": payload,
    }


def test_builder_passes_through_canonical_payload_manifest():
    manifest = _valid_manifest()

    build = build_candidate_evidence_manifest_from_source(
        source_row={"payload": {CANDIDATE_EVIDENCE_MANIFEST_FIELD: manifest}},
        residual_report=_valid_residual_alpha_report(),
    )

    assert build.validation.promotion_ready is True
    assert build.manifest == manifest
    assert build.source == "payload_manifest"


def test_builder_source_row_manifest_has_priority_over_payload_manifest():
    row_manifest = _valid_manifest()
    row_manifest["manifest_hash"] = "0" * 64
    payload_manifest = _valid_manifest(candidate_id="payload-candidate")

    build = build_candidate_evidence_manifest_from_source(
        source_row={
            CANDIDATE_EVIDENCE_MANIFEST_FIELD: row_manifest,
            "payload": {CANDIDATE_EVIDENCE_MANIFEST_FIELD: payload_manifest},
        },
        residual_report=_valid_residual_alpha_report(),
    )

    assert build.manifest is None
    assert build.validation.verdict == INVALID
    assert build.validation.reason == "manifest_hash_mismatch"
    assert build.source == "source_row_manifest"


def test_builder_creates_manifest_only_from_explicit_source_fields():
    build = build_candidate_evidence_manifest_from_source(
        source_row=_source_row_from_fields(),
        residual_report=_valid_residual_alpha_report(),
    )

    assert build.validation.promotion_ready is True
    assert build.manifest is not None
    assert build.manifest["candidate_id"] == "candidate-alpha-1"
    assert build.manifest["family_id"] == "family-alpha"
    assert build.manifest["replay_manifest_hash"] == "c" * 64
    assert build.manifest["manifest_hash"] != "c" * 64
    assert build.manifest["manifest_hash"] == compute_candidate_evidence_manifest_hash(
        build.manifest
    )


def test_builder_does_not_accept_alias_manifest():
    build = build_candidate_evidence_manifest_from_source(
        source_row={
            "payload": {
                "evidence_manifest": _valid_manifest(),
            }
        },
        residual_report=_valid_residual_alpha_report(),
    )

    assert build.manifest is None
    assert build.validation.verdict == PENDING_SCHEMA
    assert build.validation.promotion_ready is False


def test_builder_does_not_promote_from_lineage_replay_id():
    row = _source_row_from_fields()
    row.pop("replay_experiment_id")
    row["payload"]["lineage"] = {
        "replay_experiment_id": "lineage-only-replay",
        "manifest_hash": "d" * 64,
    }

    build = build_candidate_evidence_manifest_from_source(
        source_row=row,
        residual_report=_valid_residual_alpha_report(),
    )

    assert build.manifest is None
    assert build.validation.verdict == PENDING_SCHEMA
    assert build.validation.reason == "replay_experiment_id_missing"


def test_builder_missing_replay_manifest_hash_downgrades():
    row = _source_row_from_fields()
    row.pop("manifest_hash")

    build = build_candidate_evidence_manifest_from_source(
        source_row=row,
        residual_report=_valid_residual_alpha_report(),
    )

    assert build.manifest is None
    assert build.validation.verdict == PENDING_SCHEMA
    assert build.validation.reason == "replay_manifest_hash_missing"
    assert build.validation.lineage_downgraded is True


def test_builder_missing_hidden_oos_is_pending_schema():
    row = _source_row_from_fields()
    row["payload"].pop("hidden_oos")

    build = build_candidate_evidence_manifest_from_source(
        source_row=row,
        residual_report=_valid_residual_alpha_report(),
    )

    assert build.manifest is None
    assert build.validation.verdict == PENDING_SCHEMA
    assert build.validation.reason == "hidden_oos_missing"


def test_builder_reused_hidden_oos_is_research_only():
    row = _source_row_from_fields(
        hidden_oos={
            "split_hash": "b" * 64,
            "window_start": "2026-05-01T00:00:00Z",
            "window_end": "2026-05-08T00:00:00Z",
            "embargo": "1d",
            "trial_count": 12,
            "opened_for_iteration": True,
        }
    )

    build = build_candidate_evidence_manifest_from_source(
        source_row=row,
        residual_report=_valid_residual_alpha_report(),
    )

    assert build.manifest is None
    assert build.validation.verdict == RESEARCH_ONLY
    assert build.validation.reason == "hidden_oos_reused"


def test_builder_missing_residual_report_is_invalid():
    build = build_candidate_evidence_manifest_from_source(
        source_row=_source_row_from_fields(),
        residual_report=None,
    )

    assert build.manifest is None
    assert build.validation.verdict == INVALID
    assert build.validation.reason == "residual_alpha:not_dict"
