from __future__ import annotations

import inspect

from ml_training import pit_dataset_manifest_builder as builder
from ml_training.pit_dataset_manifest import (
    DATASET_READY,
    INVALID,
    RESEARCH_ONLY,
    compute_pit_dataset_manifest_hash,
)
from ml_training.pit_dataset_manifest_builder import (
    build_pit_dataset_manifest_from_source,
    compute_synthetic_dataset_hash,
    compute_synthetic_row_ids_hash,
)


def _source_mapping(**overrides) -> dict:
    source = {
        "dataset_id": "pit-grid-eth-buy-20260706",
        "dataset_role": "supervised_training",
        "as_of_ts": "2026-07-06T12:00:00Z",
        "candidate_scope": {
            "candidate_id": "grid_trading|ETHUSDT|Buy",
            "strategy_name": "grid_trading",
            "symbol": "ETHUSDT",
            "side": "Buy",
            "engine_mode": "demo",
        },
        "window": {
            "start_ts": "2026-07-01T00:00:00Z",
            "end_ts": "2026-07-06T11:59:00Z",
            "min_ts": "2026-07-01T00:00:00Z",
            "max_ts": "2026-07-06T11:59:00Z",
        },
        "query": {
            "query_id": "learning_rows_grid_eth_buy_20260706T120000Z",
            "query_text": (
                "SELECT row_id, ts, feature_1, label_q50 "
                "FROM learning_rows "
                "WHERE ts >= :start_ts AND ts <= :end_ts"
            ),
            "params": {
                "start_ts": "2026-07-01T00:00:00Z",
                "end_ts": "2026-07-06T11:59:00Z",
                "candidate_id": "grid_trading|ETHUSDT|Buy",
            },
        },
        "rows": {
            "rows": [
                {
                    "row_id": "row-2",
                    "ts": "2026-07-01T00:01:00Z",
                    "feature_1": 0.24,
                    "label_q50": 1.1,
                },
                {
                    "row_id": "row-1",
                    "ts": "2026-07-01T00:00:00Z",
                    "feature_1": 0.12,
                    "label_q50": 0.7,
                },
            ]
        },
        "features": {
            "feature_schema_version": "features_v3",
            "feature_names": ["feature_1"],
            "definition": {"feature_1": "synthetic_lagged_return"},
            "schema": {"feature_1": "float"},
        },
        "labels": {
            "schema": {"label_q50": "float"},
            "config": {"horizon_bars": 12, "target": "after_cost_bps"},
            "outcome_cutoff_ts": "2026-07-06T12:00:00Z",
        },
        "splits": {
            "split_id": "cpcv-grid-eth-buy-v1",
            "train_row_ids": ["row-1"],
            "validation_row_ids": ["row-2"],
            "test_row_ids": ["row-2"],
            "embargo_bars": 12,
            "purge_bars": 4,
        },
        "leakage": {
            "report": {"checked": True, "future_features": []},
            "fold_preprocessing_stats": {"fit_scope": "train_fold_only"},
            "overlap_count": 0,
        },
        "controls": {
            "matched_control_rows": [{"row_id": "control-1"}, {"row_id": "control-2"}],
            "matched_control_count": 2,
        },
        "fills": {
            "fill_rows": [
                {
                    "fill_id": "fill-entry-1",
                    "order_link_id": "order-1",
                    "context_id": "ctx-entry-1",
                }
            ],
            "fill_id_field": "fill_id",
            "order_link_id_field": "order_link_id",
            "context_id_field": "context_id",
        },
        "provenance": {
            "code_commit": "a" * 40,
            "rust_build_sha": "b" * 40,
            "source_hashes": {
                "pit_dataset_manifest": "c" * 64,
                "feature_builder": "d" * 64,
            },
            "input_artifact_hashes": {
                "proof_packet_manifest": "e" * 64,
                "probe_ledger": "f" * 64,
            },
        },
    }
    _deep_update(source, overrides)
    return source


def _deep_update(target: dict, updates: dict) -> None:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


def test_synthetic_row_and_dataset_hashes_are_stable_across_key_order() -> None:
    rows_a = [
        {"row_id": "row-2", "ts": "2026-07-01T00:01:00Z", "feature": 2},
        {"row_id": "row-1", "ts": "2026-07-01T00:00:00Z", "feature": 1},
    ]
    rows_b = [
        {"feature": 1, "ts": "2026-07-01T00:00:00Z", "row_id": "row-1"},
        {"feature": 2, "ts": "2026-07-01T00:01:00Z", "row_id": "row-2"},
    ]

    assert compute_synthetic_row_ids_hash(rows_a) == compute_synthetic_row_ids_hash(rows_b)
    assert compute_synthetic_dataset_hash(rows_a) == compute_synthetic_dataset_hash(rows_b)


def test_builder_produces_dataset_ready_manifest_from_explicit_source_mapping() -> None:
    build = build_pit_dataset_manifest_from_source(_source_mapping())

    assert build.validation.dataset_ready is True
    assert build.validation.verdict == DATASET_READY
    assert build.validation.reason == "ok"
    assert build.manifest is not None
    assert build.manifest["manifest_hash"] == compute_pit_dataset_manifest_hash(
        build.manifest
    )
    assert build.manifest["row_set"]["row_ids_hash"] == compute_synthetic_row_ids_hash(
        _source_mapping()["rows"]["rows"]
    )
    assert build.downgrade_reason is None


def test_rebuild_mismatch_is_not_dataset_ready() -> None:
    source = _source_mapping(
        rows={
            "rebuilt_rows": [
                {
                    "row_id": "row-1",
                    "ts": "2026-07-01T00:00:00Z",
                    "feature_1": 0.12,
                    "label_q50": 0.7,
                }
            ]
        }
    )

    build = build_pit_dataset_manifest_from_source(source)

    assert build.validation.dataset_ready is False
    assert build.validation.verdict == INVALID
    assert build.validation.reason == "rebuild_evidence_status_not_rebuild_hash_match"
    assert build.manifest is not None


def test_unpinned_query_is_not_dataset_ready() -> None:
    source = _source_mapping(
        query={
            "query_text": "SELECT * FROM learning_rows WHERE ts < now()",
            "params": {"max_age_days": 7},
            "max_age_days": 7,
        }
    )

    build = build_pit_dataset_manifest_from_source(source)

    assert build.validation.dataset_ready is False
    assert build.validation.verdict == RESEARCH_ONLY
    assert build.validation.reason.startswith("source_query_unpinned_relative_window:")
    assert build.manifest is not None


def test_builder_source_does_not_use_env_db_runtime_or_file_reads() -> None:
    source = inspect.getsource(builder)
    forbidden_tokens = (
        "os.environ",
        "getenv(",
        "open(",
        "pathlib",
        "sqlite",
        "psycopg",
        "subprocess",
        "requests",
        "urllib",
        "socket",
    )

    assert not any(token in source for token in forbidden_tokens)
