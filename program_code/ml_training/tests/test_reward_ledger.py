from __future__ import annotations

import copy

import pytest

from ml_training.demo_mutation_envelope import (
    APPLICATION_STATUS_DRY_RUN,
    build_demo_mutation_envelope,
    compute_demo_mutation_envelope_hash,
)
from ml_training.pit_dataset_manifest import (
    DATASET_READY,
    PIT_DATASET_MANIFEST_SCHEMA_VERSION,
    compute_pit_dataset_manifest_hash,
)
from ml_training.proof_packet_contract import (
    NO_MATCHED_FILLS,
    PROOF_PACKET_SCHEMA_VERSION,
    PROOF_READY,
    compute_proof_packet_hash,
)
from ml_training.registry_serving_contract import (
    PIT_DATASET_MANIFEST_SCHEMA_VERSION as REGISTRY_PIT_SCHEMA_VERSION,
    REGISTRY_SERVING_CONTRACT_SCHEMA_VERSION,
    compute_registry_serving_contract_hash,
)
from ml_training.reward_ledger import (
    INVALID,
    PENDING_SCHEMA,
    REWARD_LEDGER_FIELD,
    REWARD_LEDGER_SCHEMA_VERSION,
    REWARD_RECORD_READY,
    REGISTRY_OPTIONAL_REASON_EXECUTION_REWARD,
    RewardLedgerError,
    build_reward_record_from_proof_and_mutation,
    compute_reward_record_hash,
    dedupe_reward_records,
    extract_reward_record,
    validate_reward_batch,
    validate_reward_record,
)


_DEFAULT = object()


def _valid_pit_manifest(**overrides) -> dict:
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
            "source_hashes": {"feature_builder": "c" * 64},
            "input_artifact_hashes": {"probe_ledger": "d" * 64},
        },
    }
    _deep_update(manifest, overrides)
    manifest["manifest_hash"] = compute_pit_dataset_manifest_hash(manifest)
    return manifest


def _valid_proof_packet(**overrides) -> dict:
    packet = {
        "schema_version": PROOF_PACKET_SCHEMA_VERSION,
        "verdict": PROOF_READY,
        "candidate_identity": {
            "candidate_id": "grid_trading|ETHUSDT|Buy",
            "strategy_name": "grid_trading",
            "symbol": "ETHUSDT",
            "side": "Buy",
            "context_id": "ctx-entry-1",
        },
        "execution_identity": {
            "candidate_matched": True,
            "order_link_id": "oc_dm_1782040200000_1_0deadbeef",
            "fill_ids": ["fill-entry-1", "fill-exit-1"],
            "entry_context_id": "ctx-entry-1",
            "exit_context_id": "ctx-exit-1",
            "liquidity_role": "mixed",
            "fill_records": [
                {
                    "fill_id": "fill-entry-1",
                    "outcome_source": "candidate_matched_demo_fill",
                }
            ],
        },
        "cost_identity": {
            "maker_fee_bps": 2.0,
            "taker_fee_bps": 5.5,
            "slippage_bps": 0.4,
            "spread_bps": 1.1,
            "funding_bps": -0.2,
            "markout_bps": 3.8,
            "realized_net_pnl_bps": 4.2,
            "realized_net_pnl_usdt": 0.42,
        },
        "controls": {
            "matched_control_ids": ["control-1", "control-2"],
            "regime_labels": {"trend": "sideways", "volatility": "medium"},
            "oos_split": {"split_hash": "b" * 64, "hidden_oos": True},
            "proof_exclusions": [],
        },
        "provenance": {
            "code_commit": "a" * 40,
            "rust_build_sha": "c" * 40,
            "source_hashes": {"probe_ledger": "d" * 64},
            "input_artifact_hashes": {"standing_envelope": "e" * 64},
            "pit_dataset_manifest": _valid_pit_manifest(),
        },
    }
    _deep_update(packet, overrides)
    packet["proof_packet_hash"] = compute_proof_packet_hash(packet)
    return packet


def _no_fill_packet() -> dict:
    packet = {
        "schema_version": PROOF_PACKET_SCHEMA_VERSION,
        "verdict": NO_MATCHED_FILLS,
        "candidate_identity": {
            "candidate_id": "grid_trading|ETHUSDT|Buy",
            "strategy_name": "grid_trading",
            "symbol": "ETHUSDT",
            "side": "Buy",
            "context_id": "ctx-entry-1",
        },
        "no_fill_diagnosis": {
            "blocker_code": "NO_MATCHED_FILLS_AFTER_AUTHORIZED_WINDOW",
            "observed_window_start": "2026-07-06T10:00:00Z",
            "observed_window_end": "2026-07-06T10:05:00Z",
            "attempted_order_count": 2,
        },
        "provenance": {
            "code_commit": "a" * 40,
            "rust_build_sha": "c" * 40,
            "source_hashes": {"probe_ledger": "d" * 64},
            "input_artifact_hashes": {"window_packet": "e" * 64},
        },
    }
    packet["proof_packet_hash"] = compute_proof_packet_hash(packet)
    return packet


def _valid_envelope(proof_packet: dict, **overrides) -> dict:
    args = {
        "source_proposal_or_recommendation_id": "mlde-shadow-rec-123",
        "source_payload": {
            "recommendation_id": "mlde-shadow-rec-123",
            "candidate_id": "grid_trading|ETHUSDT|Buy",
            "strategy_name": "grid_trading",
            "symbol": "ETHUSDT",
            "side": "Buy",
        },
        "application_type": "strategy_params",
        "target": "grid_trading",
        "previous_snapshot": {"conf_scale": 1.0, "cooldown_ms": 120_000},
        "proposed_patch": {"conf_scale": 1.05},
        "max_delta_policy": {
            "policy_id": "demo_mutation_max_delta_policy_v1",
            "max_delta_pct": 0.10,
        },
        "governance_verdict": {
            "verdict": "approved_for_review",
            "review_allowed": True,
            "governance_packet_hash": "a" * 64,
        },
        "rollback_handle": {
            "rollback_id": "rollback-demo-123",
            "available": True,
            "snapshot_hash": "b" * 64,
        },
        "ipc_response": {"status": "applied", "result": {"accepted": True}},
        "ipc_response_status": "applied",
        "post_change_review": {
            "status": "passed",
            "review_hash": "c" * 64,
        },
        "proof_linkage": {
            "valid": True,
            "proof_packet_hash": proof_packet["proof_packet_hash"],
        },
    }
    args.update(overrides)
    envelope = build_demo_mutation_envelope(**args)
    envelope["source"].update(
        {
            "candidate_id": "grid_trading|ETHUSDT|Buy",
            "strategy_name": "grid_trading",
            "symbol": "ETHUSDT",
            "side": "Buy",
        }
    )
    envelope["envelope_sha256"] = compute_demo_mutation_envelope_hash(envelope)
    return envelope


def _valid_effect_window(**overrides) -> dict:
    window = {
        "window_id": "effect:grid_trading|ETHUSDT|Buy:2026-07-06T10:00:00Z:2026-07-06T10:05:00Z",
        "start_ts": "2026-07-06T10:00:00Z",
        "end_ts": "2026-07-06T10:05:00Z",
        "observation_count": 2,
        "window_source": "offline_fixture",
        "point_in_time": True,
    }
    _deep_update(window, overrides)
    return window


def _valid_registry_contract(**overrides) -> dict:
    contract = {
        "schema_version": REGISTRY_SERVING_CONTRACT_SCHEMA_VERSION,
        "serving_mode": "advisory_only",
        "not_authority": True,
        "symlink_authority": False,
        "promotion_serving_ready": False,
        "dataset_manifest_schema_version": REGISTRY_PIT_SCHEMA_VERSION,
        "dataset_manifest_hash": "a" * 64,
        "label_schema_hash": "b" * 64,
        "feature_schema_hash": "c" * 64,
        "feature_definition_hash": "d" * 64,
        "split_hash": "e" * 64,
        "leakage_report_hash": "f" * 64,
        "serving_config_hash": "1" * 64,
        "missingness_policy": "nan_sentinel=-999;unknown_category=reject",
        "units": "edge_prediction=bps;horizon=bars",
        "side_handling": "allowed_sides=Buy,Sell;side_feature_required=true",
        "artifact_hashes": {
            "q10": "sha256:" + "2" * 64,
            "q50": "3" * 64,
            "q90": "sha256:" + "4" * 64,
        },
        "quantile_trio": ["q10", "q50", "q90"],
    }
    _deep_update(contract, overrides)
    contract["contract_hash"] = compute_registry_serving_contract_hash(contract)
    return contract


def _deep_update(target: dict, updates: dict) -> None:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


def _build_record(**kwargs) -> dict:
    proof = kwargs.pop("proof_packet", None) or _valid_proof_packet()
    envelope = kwargs.pop("demo_mutation_envelope", None) or _valid_envelope(proof)
    window = kwargs.pop("effect_window", None) or _valid_effect_window()
    registry = kwargs.pop("registry_serving_contract", _DEFAULT)
    if registry is _DEFAULT and kwargs.get("registry_required", True) is True:
        registry = _valid_registry_contract()
    return build_reward_record_from_proof_and_mutation(
        proof_packet=proof,
        demo_mutation_envelope=envelope,
        effect_window=window,
        registry_serving_contract=registry,
        **kwargs,
    )


def test_happy_path_builds_deterministic_reward_record() -> None:
    proof = _valid_proof_packet()
    envelope = _valid_envelope(proof)

    record = _build_record(proof_packet=proof, demo_mutation_envelope=envelope)
    rebuilt = _build_record(proof_packet=copy.deepcopy(proof), demo_mutation_envelope=copy.deepcopy(envelope))

    assert record == rebuilt
    assert record["schema_version"] == REWARD_LEDGER_SCHEMA_VERSION
    assert record["verdict"] == REWARD_RECORD_READY
    assert record["reward"]["net_pnl_bps"] == proof["cost_identity"]["realized_net_pnl_bps"]
    assert record["reward"]["net_pnl_usdt"] == proof["cost_identity"]["realized_net_pnl_usdt"]
    assert record["reward"]["no_fill_reward"] is False
    assert record["lineage"]["proof_packet_hash"] == proof["proof_packet_hash"]
    assert record["lineage"]["mutation_envelope_hash"] == envelope["envelope_sha256"]
    assert record["lineage"]["pit_dataset_manifest_hash"] == (
        proof["provenance"]["pit_dataset_manifest"]["manifest_hash"]
    )
    assert record["lineage"]["registry_required"] is True
    assert record["lineage"]["registry_serving_contract_hash"]
    assert record["lineage"]["registry_optional_reason"] == ""
    assert record["source_artifacts"]["proof_packet"] == proof
    assert record["source_artifacts"]["demo_mutation_envelope"] == envelope
    assert record["source_artifacts"]["registry_serving_contract"]["contract_hash"] == (
        record["lineage"]["registry_serving_contract_hash"]
    )
    assert all(value is False for value in record["no_authority"].values())
    assert record["record_hash"] == compute_reward_record_hash(record)

    validation = validate_reward_record(record)
    assert validation.reward_ready is True
    assert validation.reason == "ok"


def test_hash_is_key_order_stable_and_detects_mutation() -> None:
    record = _build_record()
    reordered = dict(reversed(list(record.items())))

    assert compute_reward_record_hash(record) == compute_reward_record_hash(reordered)

    record["reward"]["net_pnl_bps"] = 99.0
    validation = validate_reward_record(record)

    assert validation.reward_ready is False
    assert validation.reason in {
        "reward_net_pnl_bps_cost_identity_mismatch",
        "record_hash_mismatch",
    }


def test_validator_rejects_forged_lineage_even_after_record_hash_recomputed() -> None:
    record = _build_record()
    record["lineage"]["proof_packet_hash"] = "f" * 64
    record["lineage"]["mutation_envelope_hash"] = "e" * 64
    record["lineage"]["pit_dataset_manifest_hash"] = "d" * 64
    record["lineage"]["registry_serving_contract_hash"] = "c" * 64
    record["record_hash"] = compute_reward_record_hash(record)

    validation = validate_reward_record(record)

    assert validation.reward_ready is False
    assert "lineage_proof_packet_hash_source_mismatch" in validation.reasons
    assert "lineage_mutation_envelope_hash_source_mismatch" in validation.reasons
    assert "lineage_pit_dataset_manifest_hash_source_mismatch" in validation.reasons
    assert "lineage_registry_serving_contract_hash_source_mismatch" in validation.reasons


def test_validator_rejects_mutated_source_artifact_after_record_hash_recomputed() -> None:
    record = _build_record()
    record["source_artifacts"]["proof_packet"]["provenance"]["pit_dataset_manifest"]["row_set"][
        "row_count"
    ] = 999
    record["record_hash"] = compute_reward_record_hash(record)

    validation = validate_reward_record(record)

    assert validation.reward_ready is False
    assert "source_artifacts_pit_dataset_manifest_hash_mismatch" in validation.reasons


def test_invalid_proof_packet_rejected_before_reward_record() -> None:
    proof = _valid_proof_packet()
    proof["candidate_identity"]["symbol"] = "BTCUSDT"
    proof["proof_packet_hash"] = compute_proof_packet_hash(proof)

    with pytest.raises(RewardLedgerError, match="proof_packet_not_proof_ready"):
        _build_record(proof_packet=proof, demo_mutation_envelope=_valid_envelope(proof))


def test_no_fill_packet_never_becomes_reward() -> None:
    proof = _no_fill_packet()
    envelope = _valid_envelope(proof)

    with pytest.raises(RewardLedgerError, match="proof_packet_no_matched_fills"):
        _build_record(proof_packet=proof, demo_mutation_envelope=envelope)


def test_candidate_mismatch_rejected() -> None:
    proof = _valid_proof_packet(
        candidate_identity={"candidate_id": "grid_trading|BTCUSDT|Buy", "symbol": "BTCUSDT"},
    )
    envelope = _valid_envelope(proof)

    with pytest.raises(RewardLedgerError, match="proof_packet_not_proof_ready"):
        _build_record(proof_packet=proof, demo_mutation_envelope=envelope)


def test_proof_excluded_cleanup_rejected() -> None:
    proof = _valid_proof_packet(
        controls={"proof_exclusions": ["cleanup_fill"]},
    )
    envelope = _valid_envelope(proof)

    with pytest.raises(RewardLedgerError, match="proof_packet_not_proof_ready"):
        _build_record(proof_packet=proof, demo_mutation_envelope=envelope)


@pytest.mark.parametrize("engine_mode", ["paper", "live", "live_demo", "mainnet"])
def test_non_demo_or_live_envelope_rejected(engine_mode: str) -> None:
    proof = _valid_proof_packet()
    envelope = _valid_envelope(proof, engine_mode=engine_mode)

    with pytest.raises(RewardLedgerError, match="demo_mutation_envelope_not_countable"):
        _build_record(proof_packet=proof, demo_mutation_envelope=envelope)


@pytest.mark.parametrize(
    "envelope_kwargs",
    [
        {"application_status": APPLICATION_STATUS_DRY_RUN},
        {"dry_run": True},
        {"dedupe": True},
        {"post_change_review": None},
        {
            "max_delta_policy": {
                "policy_id": "demo_mutation_max_delta_policy_v1",
                "max_delta_pct": None,
            }
        },
    ],
)
def test_audit_only_dry_run_dedupe_non_countable_rejected(envelope_kwargs: dict) -> None:
    proof = _valid_proof_packet()
    envelope = _valid_envelope(proof, **envelope_kwargs)

    with pytest.raises(RewardLedgerError, match="demo_mutation_envelope_not_countable"):
        _build_record(proof_packet=proof, demo_mutation_envelope=envelope)


def test_proof_linkage_mismatch_rejected() -> None:
    proof = _valid_proof_packet()
    envelope = _valid_envelope(proof)
    envelope["proof_linkage"]["proof_packet_hash"] = "f" * 64
    envelope["envelope_sha256"] = compute_demo_mutation_envelope_hash(envelope)

    with pytest.raises(RewardLedgerError, match="proof_linkage_proof_packet_hash_mismatch"):
        _build_record(proof_packet=proof, demo_mutation_envelope=envelope)


def test_source_candidate_field_mismatch_rejected() -> None:
    proof = _valid_proof_packet()
    envelope = _valid_envelope(proof)
    envelope["source"]["symbol"] = "BTCUSDT"
    envelope["envelope_sha256"] = compute_demo_mutation_envelope_hash(envelope)

    with pytest.raises(RewardLedgerError, match="source_symbol_mismatch"):
        _build_record(proof_packet=proof, demo_mutation_envelope=envelope)


def test_missing_pit_lineage_rejected() -> None:
    proof = _valid_proof_packet()
    proof["provenance"].pop("pit_dataset_manifest")
    proof["proof_packet_hash"] = compute_proof_packet_hash(proof)
    envelope = _valid_envelope(proof)

    with pytest.raises(RewardLedgerError, match="proof_packet_not_proof_ready"):
        _build_record(proof_packet=proof, demo_mutation_envelope=envelope)


def test_registry_contract_missing_by_default_rejected() -> None:
    proof = _valid_proof_packet()
    envelope = _valid_envelope(proof)

    with pytest.raises(RewardLedgerError, match="registry_lineage_missing"):
        _build_record(
            proof_packet=proof,
            demo_mutation_envelope=envelope,
            registry_serving_contract=None,
        )


def test_registry_required_true_missing_rejected() -> None:
    proof = _valid_proof_packet()
    envelope = _valid_envelope(proof)
    window = _valid_effect_window(registry_required=True)

    with pytest.raises(RewardLedgerError, match="registry_lineage_missing"):
        _build_record(
            proof_packet=proof,
            demo_mutation_envelope=envelope,
            effect_window=window,
            registry_serving_contract=None,
        )


def test_registry_required_false_needs_explicit_allowed_reason() -> None:
    proof = _valid_proof_packet()
    envelope = _valid_envelope(proof)

    with pytest.raises(RewardLedgerError, match="registry_optional_reason_missing_or_unknown"):
        _build_record(
            proof_packet=proof,
            demo_mutation_envelope=envelope,
            registry_serving_contract=None,
            registry_required=False,
        )


def test_registry_required_false_with_allowed_reason_is_execution_only_reward() -> None:
    proof = _valid_proof_packet()
    envelope = _valid_envelope(proof)

    record = _build_record(
        proof_packet=proof,
        demo_mutation_envelope=envelope,
        registry_serving_contract=None,
        registry_required=False,
        registry_optional_reason=REGISTRY_OPTIONAL_REASON_EXECUTION_REWARD,
    )

    assert record["lineage"]["registry_required"] is False
    assert record["lineage"]["registry_serving_contract_hash"] == ""
    assert record["lineage"]["registry_optional_reason"] == (
        REGISTRY_OPTIONAL_REASON_EXECUTION_REWARD
    )
    assert validate_reward_record(record).reward_ready is True


def test_registry_optional_rejects_effect_window_registry_required_marker() -> None:
    proof = _valid_proof_packet()
    envelope = _valid_envelope(proof)

    with pytest.raises(RewardLedgerError, match="registry_optional_source_contract_bound"):
        _build_record(
            proof_packet=proof,
            demo_mutation_envelope=envelope,
            effect_window=_valid_effect_window(registry_required=True),
            registry_serving_contract=None,
            registry_required=False,
            registry_optional_reason=REGISTRY_OPTIONAL_REASON_EXECUTION_REWARD,
        )


def test_registry_optional_rejects_acceptance_contract_bound_marker() -> None:
    proof = _valid_proof_packet()
    envelope = _valid_envelope(proof)

    with pytest.raises(RewardLedgerError, match="registry_optional_source_contract_bound"):
        _build_record(
            proof_packet=proof,
            demo_mutation_envelope=envelope,
            acceptance_report_ref={
                "acceptance_report_id": "acceptance-grid-eth-buy-1",
                "contract_bound": True,
            },
            registry_serving_contract=None,
            registry_required=False,
            registry_optional_reason=REGISTRY_OPTIONAL_REASON_EXECUTION_REWARD,
        )


def test_validator_rejects_forged_optional_record_with_contract_bound_source_artifact() -> None:
    record = _build_record(
        registry_serving_contract=None,
        registry_required=False,
        registry_optional_reason=REGISTRY_OPTIONAL_REASON_EXECUTION_REWARD,
    )
    record["source_artifacts"]["acceptance_report_ref"] = {
        "acceptance_report_id": "acceptance-grid-eth-buy-1",
        "contract_bound": True,
    }
    record["record_hash"] = compute_reward_record_hash(record)

    validation = validate_reward_record(record)

    assert validation.reward_ready is False
    assert any(
        reason.startswith("registry_optional_source_contract_bound:")
        for reason in validation.reasons
    )


def test_registry_contract_hash_attached_when_required() -> None:
    proof = _valid_proof_packet()
    envelope = _valid_envelope(proof)
    registry = _valid_registry_contract()

    record = _build_record(
        proof_packet=proof,
        demo_mutation_envelope=envelope,
        effect_window=_valid_effect_window(registry_required=True),
        registry_serving_contract=registry,
        registry_required=True,
    )

    assert record["lineage"]["registry_serving_contract_hash"] == registry["contract_hash"]
    assert record["lineage"]["registry_required"] is True
    assert record["lineage"]["registry_optional_reason"] == ""
    assert validate_reward_record(record).reward_ready is True


@pytest.mark.parametrize(
    "artifact_update",
    [
        {"proof_packet": {"orderAuthorityGranted": True}},
        {"demo_mutation_envelope": {"metadata": {"runtimeMutationAllowed": True}}},
        {"effect_window": {"privateReadAllowed": True}},
        {"acceptance_report_ref": {"registry_required": True, "promotionAllowed": "yes"}},
    ],
)
def test_authority_alias_rejected_anywhere(artifact_update: dict) -> None:
    proof = _valid_proof_packet()
    envelope = _valid_envelope(proof)
    window = _valid_effect_window()
    acceptance_report_ref = None
    if "proof_packet" in artifact_update:
        proof.update(artifact_update["proof_packet"])
        proof["proof_packet_hash"] = compute_proof_packet_hash(proof)
        envelope = _valid_envelope(proof)
    if "demo_mutation_envelope" in artifact_update:
        envelope.update(artifact_update["demo_mutation_envelope"])
        envelope["envelope_sha256"] = compute_demo_mutation_envelope_hash(envelope)
    if "effect_window" in artifact_update:
        window.update(artifact_update["effect_window"])
    if "acceptance_report_ref" in artifact_update:
        acceptance_report_ref = artifact_update["acceptance_report_ref"]

    with pytest.raises(RewardLedgerError, match="authority_boundary_violation"):
        _build_record(
            proof_packet=proof,
            demo_mutation_envelope=envelope,
            effect_window=window,
            acceptance_report_ref=acceptance_report_ref,
            registry_serving_contract=_valid_registry_contract()
            if acceptance_report_ref
            else None,
        )


def test_reward_record_validator_rejects_authority_alias() -> None:
    record = _build_record()
    record["metadata"] = {"orderAuthorityGranted": True}
    record["record_hash"] = compute_reward_record_hash(record)

    validation = validate_reward_record(record)

    assert validation.reward_ready is False
    assert validation.verdict == INVALID
    assert validation.authority_boundary_violation is True
    assert validation.reason.startswith("authority_boundary_violation:")


def test_effect_window_must_be_closed_and_point_in_time() -> None:
    proof = _valid_proof_packet()
    envelope = _valid_envelope(proof)

    with pytest.raises(RewardLedgerError, match="effect_window_point_in_time_not_true"):
        _build_record(
            proof_packet=proof,
            demo_mutation_envelope=envelope,
            effect_window=_valid_effect_window(point_in_time=False),
        )

    with pytest.raises(RewardLedgerError, match="effect_window_not_closed_forward"):
        _build_record(
            proof_packet=proof,
            demo_mutation_envelope=envelope,
            effect_window=_valid_effect_window(
                start_ts="2026-07-06T10:05:00Z",
                end_ts="2026-07-06T10:00:00Z",
            ),
        )


def test_extract_reads_canonical_field_only() -> None:
    record = _build_record()

    assert extract_reward_record({REWARD_LEDGER_FIELD: record}) == record
    assert extract_reward_record({"reward_record": record}) is None


def test_batch_validation_and_source_only_dedupe() -> None:
    record = _build_record()
    duplicate = copy.deepcopy(record)

    assert len(dedupe_reward_records([record, duplicate])) == 1

    validation = validate_reward_batch([record, duplicate])
    assert validation.reward_ready is False
    assert validation.verdict == INVALID
    assert "record[1]:record_id_duplicate" in validation.reasons


def test_missing_required_record_fields_are_pending_schema() -> None:
    record = _build_record()
    record["lineage"].pop("pit_dataset_manifest_hash")
    record["record_hash"] = compute_reward_record_hash(record)

    validation = validate_reward_record(record)

    assert validation.reward_ready is False
    assert validation.verdict == PENDING_SCHEMA
    assert validation.reason == "lineage_pit_dataset_manifest_hash_missing_or_malformed"
