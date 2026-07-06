from __future__ import annotations

from ml_training.pit_dataset_manifest import (
    DATASET_READY,
    INVALID,
    PENDING_SCHEMA,
    PIT_DATASET_MANIFEST_FIELD,
    PIT_DATASET_MANIFEST_SCHEMA_VERSION,
    RESEARCH_ONLY,
    compute_pit_dataset_manifest_hash,
    extract_pit_dataset_manifest,
    validate_pit_dataset_manifest,
)


def _valid_manifest(**overrides) -> dict:
    manifest = {
        "schema_version": PIT_DATASET_MANIFEST_SCHEMA_VERSION,
        "verdict": DATASET_READY,
        "dataset_id": "pit-grid-eth-buy-20260706",
        "dataset_role": "supervised_training",
        "as_of_ts": "2026-07-06T12:00:00Z",
        "point_in_time": True,
        "future_data_allowed": False,
        "candidate_scope": {
            "candidate_id": "grid_trading|ETHUSDT|Buy",
            "strategy_name": "grid_trading",
            "symbol": "ETHUSDT",
            "side": "Buy",
            "engine_mode": "demo",
        },
        "source_query": {
            "query_id": "learning_rows_grid_eth_buy_20260706T120000Z",
            "query_hash": "a" * 64,
            "query_params_hash": "b" * 64,
            "start_ts": "2026-07-01T00:00:00Z",
            "end_ts": "2026-07-06T11:59:00Z",
            "query_text_hash": "c" * 64,
        },
        "row_set": {
            "row_count": 128,
            "row_ids_hash": "d" * 64,
            "dataset_hash": "e" * 64,
            "min_ts": "2026-07-01T00:00:00Z",
            "max_ts": "2026-07-06T11:59:00Z",
            "schema_hash": "f" * 64,
        },
        "feature_lineage": {
            "feature_schema_version": "features_v3",
            "feature_schema_hash": "1" * 64,
            "feature_definition_hash": "2" * 64,
            "feature_names_hash": "3" * 64,
        },
        "label_lineage": {
            "label_schema_hash": "4" * 64,
            "label_config_hash": "5" * 64,
            "outcome_cutoff_ts": "2026-07-06T12:00:00Z",
        },
        "split_lineage": {
            "split_id": "cpcv-grid-eth-buy-v1",
            "split_hash": "6" * 64,
            "embargo_bars": 12,
            "purge_bars": 4,
            "train_row_ids_hash": "7" * 64,
            "validation_row_ids_hash": "8" * 64,
            "test_row_ids_hash": "9" * 64,
        },
        "leakage_evidence": {
            "leakage_report_hash": "a" * 64,
            "fold_preprocessing_stats_hash": "b" * 64,
            "overlap_count": 0,
        },
        "matched_controls": {
            "matched_control_artifact_hash": "c" * 64,
            "matched_control_row_ids_hash": "d" * 64,
            "matched_control_count": 16,
        },
        "row_backed_fill_source": {
            "fill_source_artifact_hash": "e" * 64,
            "fill_row_ids_hash": "f" * 64,
            "fill_id_field": "fill_id",
            "order_link_id_field": "order_link_id",
            "context_id_field": "context_id",
        },
        "rebuild_evidence": {
            "status": "rebuild_hash_match",
            "original_row_count": 128,
            "rebuilt_row_count": 128,
            "original_row_ids_hash": "d" * 64,
            "rebuilt_row_ids_hash": "d" * 64,
            "original_dataset_hash": "e" * 64,
            "rebuilt_dataset_hash": "e" * 64,
        },
        "provenance": {
            "code_commit": "a" * 40,
            "rust_build_sha": "b" * 40,
            "source_hashes": {
                "proof_packet_contract": "c" * 64,
                "feature_builder": "d" * 64,
            },
            "input_artifact_hashes": {
                "proof_packet_manifest": "e" * 64,
                "probe_ledger": "f" * 64,
            },
        },
    }
    _deep_update(manifest, overrides)
    manifest["manifest_hash"] = compute_pit_dataset_manifest_hash(manifest)
    return manifest


def _deep_update(target: dict, updates: dict) -> None:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


def test_valid_manifest_passes_and_is_dataset_ready() -> None:
    validation = validate_pit_dataset_manifest(_valid_manifest())

    assert validation.dataset_ready is True
    assert validation.verdict == DATASET_READY
    assert validation.reason == "ok"


def test_extract_reads_canonical_field_only() -> None:
    manifest = _valid_manifest()

    assert extract_pit_dataset_manifest({PIT_DATASET_MANIFEST_FIELD: manifest}) == manifest
    assert extract_pit_dataset_manifest({"dataset_manifest": manifest}) is None


def test_manifest_hash_is_key_order_stable_and_mismatch_invalid() -> None:
    manifest_a = _valid_manifest()
    manifest_b = {
        "provenance": dict(reversed(list(manifest_a["provenance"].items()))),
        "rebuild_evidence": dict(reversed(list(manifest_a["rebuild_evidence"].items()))),
        "row_backed_fill_source": dict(
            reversed(list(manifest_a["row_backed_fill_source"].items()))
        ),
        "matched_controls": dict(reversed(list(manifest_a["matched_controls"].items()))),
        "leakage_evidence": dict(reversed(list(manifest_a["leakage_evidence"].items()))),
        "split_lineage": dict(reversed(list(manifest_a["split_lineage"].items()))),
        "label_lineage": dict(reversed(list(manifest_a["label_lineage"].items()))),
        "feature_lineage": dict(reversed(list(manifest_a["feature_lineage"].items()))),
        "row_set": dict(reversed(list(manifest_a["row_set"].items()))),
        "source_query": dict(reversed(list(manifest_a["source_query"].items()))),
        "candidate_scope": dict(reversed(list(manifest_a["candidate_scope"].items()))),
        "future_data_allowed": manifest_a["future_data_allowed"],
        "point_in_time": manifest_a["point_in_time"],
        "as_of_ts": manifest_a["as_of_ts"],
        "dataset_role": manifest_a["dataset_role"],
        "dataset_id": manifest_a["dataset_id"],
        "verdict": manifest_a["verdict"],
        "schema_version": manifest_a["schema_version"],
    }
    assert compute_pit_dataset_manifest_hash(manifest_a) == compute_pit_dataset_manifest_hash(
        manifest_b
    )

    manifest_a["manifest_hash"] = "0" * 64
    validation = validate_pit_dataset_manifest(manifest_a)

    assert validation.dataset_ready is False
    assert validation.verdict == INVALID
    assert validation.reason == "manifest_hash_mismatch"


def test_missing_lineage_and_control_sections_return_pending_schema() -> None:
    for section in ("feature_lineage", "matched_controls", "row_backed_fill_source"):
        manifest = _valid_manifest()
        manifest.pop(section)

        validation = validate_pit_dataset_manifest(manifest)

        assert validation.dataset_ready is False
        assert validation.verdict == PENDING_SCHEMA
        assert validation.reason == f"{section}_missing"


def test_query_with_now_or_max_age_days_is_research_only() -> None:
    for source_query in (
        {"query_text": "SELECT * FROM learning_rows WHERE ts < now()"},
        {"max_age_days": 7},
    ):
        manifest = _valid_manifest(source_query=source_query)

        validation = validate_pit_dataset_manifest(manifest)

        assert validation.dataset_ready is False
        assert validation.verdict == RESEARCH_ONLY
        assert validation.reason.startswith("source_query_unpinned_relative_window:")


def test_rebuild_mismatch_is_invalid() -> None:
    manifest = _valid_manifest(rebuild_evidence={"rebuilt_dataset_hash": "0" * 64})

    validation = validate_pit_dataset_manifest(manifest)

    assert validation.dataset_ready is False
    assert validation.verdict == INVALID
    assert validation.reason == "rebuild_evidence_dataset_hash_mismatch"


def test_max_ts_after_as_of_ts_is_invalid() -> None:
    manifest = _valid_manifest(row_set={"max_ts": "2026-07-06T12:00:01Z"})

    validation = validate_pit_dataset_manifest(manifest)

    assert validation.dataset_ready is False
    assert validation.verdict == INVALID
    assert validation.reason == "row_set_max_ts_after_as_of_ts"


def test_authority_expansion_is_invalid() -> None:
    manifest = _valid_manifest()
    manifest["answers"] = {"order_authority_granted": True}

    validation = validate_pit_dataset_manifest(manifest)

    assert validation.dataset_ready is False
    assert validation.verdict == INVALID
    assert validation.authority_boundary_violation is True
    assert validation.reason == "authority_boundary_violation:answers.order_authority_granted"


def test_secret_like_text_is_invalid() -> None:
    manifest = _valid_manifest()
    manifest["notes"] = "DATABASE_URL=postgresql://user:pass@example.invalid/db"

    validation = validate_pit_dataset_manifest(manifest)

    assert validation.dataset_ready is False
    assert validation.verdict == INVALID
    assert validation.secret_leak_detected is True
    assert validation.reason == "secret_like_text_present:notes"
