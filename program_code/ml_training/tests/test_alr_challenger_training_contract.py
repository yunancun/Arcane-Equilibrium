from __future__ import annotations

import copy
import hashlib
import inspect
import json

import pytest

from ml_training.alr_challenger_training_contract import (
    ALR_CHALLENGER_TRAINING_CONTRACT_SCHEMA_VERSION,
    SCHEMA_REQUIRED,
    AlrChallengerTrainingContractError,
    build_alr_challenger_training_contract,
    compute_alr_challenger_training_contract_hash,
    validate_alr_challenger_training_contract,
)
from ml_training.candidate_proof_repository import (
    compute_candidate_proof_repository_receipt_hash,
    discover_candidate_proof_receipts,
)
from ml_training.candidate_proof_adapter import (
    compute_candidate_proof_adapter_hash,
    compute_selection_proof_binding_hash,
)
from ml_training.tests.test_candidate_proof_repository import (
    _Connection,
    _binding,
    _bound_ready_packet,
    _bound_reward_record,
    _bridge_row,
    _selected_projection,
)


def _ready_receipt(*, reward_count: int = 1) -> dict:
    projection = _selected_projection()
    proof = _bound_ready_packet(projection, _binding(projection))
    rewards = [
        _bound_reward_record(proof, window_id=f"window-{index}")
        for index in range(reward_count)
    ]
    batch = discover_candidate_proof_receipts(
        _Connection(
            projection,
            bridge_rows=[_bridge_row(proof, rewards)] if rewards else [],
        ),
        limit=8,
    )
    if rewards:
        return copy.deepcopy(batch["receipts"][0])
    receipt = copy.deepcopy(batch["receipts"][0])
    receipt["status"] = "READY_FOR_REWARD_VALIDATION"
    receipt["adapter_result"]["status"] = "READY_FOR_REWARD_VALIDATION"
    receipt["receipt_hash"] = compute_candidate_proof_repository_receipt_hash(receipt)
    return receipt


def _code_manifest() -> dict:
    return {
        "schema_version": "alr_challenger_code_manifest_v1",
        "source_head": "a" * 40,
        "module_hashes": {
            "pit_dataset_manifest.py": "1" * 64,
            "quantile_trainer.py": "2" * 64,
            "run_training_pipeline.py": "3" * 64,
            "model_registry.py": "4" * 64,
        },
        "dependency_lock_hash": "5" * 64,
    }


def _training_config() -> dict:
    return {
        "schema_version": "alr_challenger_training_config_v1",
        "algorithm": "lightgbm_quantile_trio",
        "quantiles": ["q10", "q50", "q90"],
        "engine_mode": "demo",
        "feature_schema_hash": "1" * 64,
        "label_schema_hash": "4" * 64,
        "parameters": {
            "num_leaves": 7,
            "learning_rate": 0.05,
            "n_estimators": 500,
            "early_stopping_rounds": 50,
            "min_data_in_leaf": None,
            "feature_fraction": 0.8,
            "bagging_fraction": 0.8,
            "bagging_freq": 5,
            "lambda_l2": 0.1,
            "label_window_hours": 4.0,
            "decay_halflife_days": 14.0,
            "bootstrap_iterations": 1000,
            "bootstrap_seed": 42,
            "schema_version": "v1",
        },
        "resource_budget": {
            "max_wall_seconds": 300,
            "max_cpu_seconds": 1200,
            "max_memory_bytes": 2_147_483_648,
            "max_artifact_bytes": 268_435_456,
            "max_training_rows": 100_000,
            "max_external_requests": 0,
            "max_api_cost_usd": 0,
        },
    }


def _rehash_receipt(receipt: dict) -> None:
    receipt["receipt_hash"] = compute_candidate_proof_repository_receipt_hash(receipt)


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _rehash_contract(contract: dict) -> None:
    contract["training_input_hash"] = _canonical_hash(contract["input_lineage"])
    code_hash = contract["code_manifest"]["code_manifest_hash"]
    config_hash = contract["training_config"]["training_config_hash"]
    contract["training_key_hash"] = _canonical_hash(
        {
            "schema_version": ALR_CHALLENGER_TRAINING_CONTRACT_SCHEMA_VERSION,
            "repository_receipt_hash": contract["repository_receipt_hash"],
            "training_input_hash": contract["training_input_hash"],
            "code_manifest_hash": code_hash,
            "training_config_hash": config_hash,
        }
    )
    contract["contract_hash"] = compute_alr_challenger_training_contract_hash(contract)


def test_builds_deterministic_schema_required_contract_from_repository_receipt() -> None:
    receipt = _ready_receipt(reward_count=2)

    first = build_alr_challenger_training_contract(
        receipt,
        code_manifest=_code_manifest(),
        training_config=_training_config(),
    )
    second = build_alr_challenger_training_contract(
        copy.deepcopy(receipt),
        code_manifest=copy.deepcopy(_code_manifest()),
        training_config=copy.deepcopy(_training_config()),
    )

    assert first == second
    assert first["schema_version"] == ALR_CHALLENGER_TRAINING_CONTRACT_SCHEMA_VERSION
    assert first["status"] == SCHEMA_REQUIRED
    assert first["reason"] == "durable_receipt_schema_required"
    assert first["source_contract_ready"] is True
    assert first["durable_receipt_required"] is True
    assert first["training_allowed"] is False
    assert first["model_training_performed"] is False
    assert first["registry_write_allowed"] is False
    assert first["runtime_or_exchange_attested"] is False
    assert first["repository_receipt_hash"] == receipt["receipt_hash"]
    assert len(first["input_lineage"]["reward_record_hashes"]) == 2
    assert first["input_lineage"]["pit_dataset_manifest_hash"] == (
        receipt["canonical_adapter_inputs"]["proof_packet"]["provenance"]
        ["pit_dataset_manifest"]["manifest_hash"]
    )
    assert first["input_lineage"]["dataset_hash"] == "e" * 64
    assert first["input_lineage"]["row_ids_hash"] == "d" * 64
    assert first["input_lineage"]["train_row_ids_hash"] == "7" * 64
    assert first["input_lineage"]["validation_row_ids_hash"] == "8" * 64
    assert first["input_lineage"]["test_row_ids_hash"] == "9" * 64
    assert first["input_lineage"]["feature_schema_hash"] == "1" * 64
    assert first["input_lineage"]["label_schema_hash"] == "4" * 64
    assert first["input_lineage"]["split_hash"] == "6" * 64
    assert first["input_lineage"]["leakage_report_hash"] == "a" * 64
    assert len(first["input_lineage"]["after_cost_label_set_hash"]) == 64
    assert len(first["training_input_hash"]) == 64
    assert len(first["training_key_hash"]) == 64
    assert first["contract_hash"] == compute_alr_challenger_training_contract_hash(first)
    assert validate_alr_challenger_training_contract(first).valid is True
    assert set(first["no_authority"].values()) == {False}
    assert set(first["authority_counters"].values()) == {0}


def test_contract_declares_isolated_no_symlink_no_legacy_registry_execution() -> None:
    contract = build_alr_challenger_training_contract(
        _ready_receipt(),
        code_manifest=_code_manifest(),
        training_config=_training_config(),
    )

    execution = contract["execution_contract"]
    assert execution == {
        "actual_dataset_rehash_required": True,
        "actual_code_rehash_required": True,
        "exact_source_head_required": True,
        "effective_config_rehash_required": True,
        "exact_split_membership_required": True,
        "actual_fit_required": True,
        "model_artifact_bytes_required": True,
        "immutable_output_directory_required": True,
        "symlink_updates_allowed": False,
        "legacy_run_training_pipeline_allowed": False,
        "legacy_model_registry_allowed": False,
        "isolated_challenger_registry_required": True,
        "serving_or_promotion_allowed": False,
    }


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        ("PENDING_EVIDENCE", "receipt_status_not_reward_ready"),
        ("NO_MATCHED_FILLS", "receipt_status_not_reward_ready"),
        ("INVALID", "receipt_status_not_reward_ready"),
    ],
)
def test_rejects_non_reward_ready_receipts(status: str, reason: str) -> None:
    receipt = _ready_receipt()
    receipt["status"] = status
    receipt["adapter_result"]["status"] = status
    _rehash_receipt(receipt)

    with pytest.raises(AlrChallengerTrainingContractError, match=reason):
        build_alr_challenger_training_contract(
            receipt,
            code_manifest=_code_manifest(),
            training_config=_training_config(),
        )


def test_rejects_missing_reward_even_when_status_is_spoofed_ready() -> None:
    receipt = _ready_receipt()
    receipt["canonical_adapter_inputs"]["reward_records"] = []
    _rehash_receipt(receipt)

    with pytest.raises(
        AlrChallengerTrainingContractError,
        match="reward_records_missing",
    ):
        build_alr_challenger_training_contract(
            receipt,
            code_manifest=_code_manifest(),
            training_config=_training_config(),
        )


def test_rejects_tampered_receipt_self_hash() -> None:
    receipt = _ready_receipt()
    receipt["receipt_hash"] = "f" * 64

    with pytest.raises(
        AlrChallengerTrainingContractError,
        match="repository_receipt_hash_mismatch",
    ):
        build_alr_challenger_training_contract(
            receipt,
            code_manifest=_code_manifest(),
            training_config=_training_config(),
        )


def test_rejects_tampered_embedded_pit_manifest() -> None:
    receipt = _ready_receipt()
    manifest = receipt["canonical_adapter_inputs"]["proof_packet"]["provenance"][
        "pit_dataset_manifest"
    ]
    manifest["row_set"]["dataset_hash"] = "0" * 64
    _rehash_receipt(receipt)

    with pytest.raises(
        AlrChallengerTrainingContractError,
        match="proof_packet:|pit_dataset_manifest:",
    ):
        build_alr_challenger_training_contract(
            receipt,
            code_manifest=_code_manifest(),
            training_config=_training_config(),
        )


def test_rejects_candidate_scope_substitution() -> None:
    receipt = _ready_receipt()
    receipt["canonical_adapter_inputs"]["proof_packet"]["candidate_identity"][
        "symbol"
    ] = "ETHUSDT"
    _rehash_receipt(receipt)

    with pytest.raises(
        AlrChallengerTrainingContractError,
        match="proof_packet:|candidate_scope",
    ):
        build_alr_challenger_training_contract(
            receipt,
            code_manifest=_code_manifest(),
            training_config=_training_config(),
        )


def test_rejects_raw_source_artifact_divergence_from_canonical_inputs() -> None:
    receipt = _ready_receipt()
    receipt["source_artifacts"]["proof_packet"]["candidate_identity"]["symbol"] = (
        "ETHUSDT"
    )
    _rehash_receipt(receipt)

    with pytest.raises(
        AlrChallengerTrainingContractError,
        match="source_artifact_proof_hash_mismatch",
    ):
        build_alr_challenger_training_contract(
            receipt,
            code_manifest=_code_manifest(),
            training_config=_training_config(),
        )


def test_rejects_exact_source_container_reward_divergence() -> None:
    receipt = _ready_receipt()
    receipt["exact_source_containers"][0]["source_artifacts"]["reward_records"] = []
    _rehash_receipt(receipt)

    with pytest.raises(
        AlrChallengerTrainingContractError,
        match="exact_source_container_0_reward_hashes_mismatch",
    ):
        build_alr_challenger_training_contract(
            receipt,
            code_manifest=_code_manifest(),
            training_config=_training_config(),
        )


def test_rejects_repository_projection_ref_divergence() -> None:
    receipt = _ready_receipt()
    receipt["repository_sources"]["projection_artifact_hash"] = "f" * 64
    _rehash_receipt(receipt)

    with pytest.raises(
        AlrChallengerTrainingContractError,
        match="repository_projection_artifact_hash_mismatch",
    ):
        build_alr_challenger_training_contract(
            receipt,
            code_manifest=_code_manifest(),
            training_config=_training_config(),
        )


def test_rejects_forged_adapter_proof_input_hash() -> None:
    receipt = _ready_receipt()
    adapter = receipt["adapter_result"]
    adapter["proof_input_hash"] = "f" * 64
    adapter["adapter_hash"] = compute_candidate_proof_adapter_hash(adapter)
    _rehash_receipt(receipt)

    with pytest.raises(
        AlrChallengerTrainingContractError,
        match="proof_input_hash_mismatch",
    ):
        build_alr_challenger_training_contract(
            receipt,
            code_manifest=_code_manifest(),
            training_config=_training_config(),
        )


def test_rejects_split_binding_and_projection_identity() -> None:
    receipt = _ready_receipt()
    binding = receipt["selection_binding"]
    binding["projection_hash"] = "f" * 64
    binding["binding_hash"] = compute_selection_proof_binding_hash(binding)
    adapter = receipt["adapter_result"]
    adapter["selection_binding"] = copy.deepcopy(binding)
    adapter["proof_input_hash"] = _canonical_hash(
        {
            "projection_refs": adapter["projection_refs"],
            "selection_binding_hash": binding["binding_hash"],
            "proof_packet_hash": adapter["proof"]["computed_proof_packet_hash"],
            "reward_record_hashes": [
                item["computed_record_hash"] for item in adapter["reward_records"]
            ],
        }
    )
    adapter["adapter_hash"] = compute_candidate_proof_adapter_hash(adapter)
    _rehash_receipt(receipt)

    with pytest.raises(
        AlrChallengerTrainingContractError,
        match="selection_binding_projection_hash_mismatch",
    ):
        build_alr_challenger_training_contract(
            receipt,
            code_manifest=_code_manifest(),
            training_config=_training_config(),
        )


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (
            lambda value: value["module_hashes"].__setitem__(
                "quantile_trainer.py", "short"
            ),
            "code_manifest_module_hash_invalid",
        ),
        (
            lambda value: value.__setitem__("source_head", "f" * 64),
            "code_manifest_source_head_invalid",
        ),
        (
            lambda value: value["module_hashes"].__setitem__(
                "unexpected.py", "f" * 64
            ),
            "code_manifest_module_set_invalid",
        ),
    ],
)
def test_rejects_malformed_or_ambiguous_code_manifest(mutate, reason: str) -> None:
    code_manifest = _code_manifest()
    mutate(code_manifest)

    with pytest.raises(AlrChallengerTrainingContractError, match=reason):
        build_alr_challenger_training_contract(
            _ready_receipt(),
            code_manifest=code_manifest,
            training_config=_training_config(),
        )


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (
            lambda value: value.__setitem__("quantiles", ["q50"]),
            "training_config_quantiles_invalid",
        ),
        (
            lambda value: value.__setitem__("feature_schema_hash", "f" * 64),
            "training_config_feature_schema_hash_mismatch",
        ),
        (
            lambda value: value["resource_budget"].__setitem__(
                "max_external_requests", 1
            ),
            "training_config_external_requests_not_zero",
        ),
        (
            lambda value: value["resource_budget"].__setitem__(
                "max_api_cost_usd", 0.01
            ),
            "training_config_api_cost_not_zero",
        ),
        (
            lambda value: value["parameters"].__setitem__(
                "promotion_allowed", True
            ),
            "authority_boundary_violation",
        ),
        (
            lambda value: value["parameters"].pop("n_estimators"),
            "training_config_parameter_set_invalid",
        ),
    ],
)
def test_rejects_training_config_mismatch_or_authority(mutate, reason: str) -> None:
    training_config = _training_config()
    mutate(training_config)

    with pytest.raises(AlrChallengerTrainingContractError, match=reason):
        build_alr_challenger_training_contract(
            _ready_receipt(),
            code_manifest=_code_manifest(),
            training_config=training_config,
        )


def test_validator_rejects_any_positive_training_or_registry_claim() -> None:
    contract = build_alr_challenger_training_contract(
        _ready_receipt(),
        code_manifest=_code_manifest(),
        training_config=_training_config(),
    )
    contract["model_training_performed"] = True
    contract["contract_hash"] = compute_alr_challenger_training_contract_hash(contract)

    validation = validate_alr_challenger_training_contract(contract)
    assert validation.valid is False
    assert validation.reason == "model_training_performed_not_false"


def test_validator_rejects_rehashed_semantically_empty_lineage() -> None:
    contract = build_alr_challenger_training_contract(
        _ready_receipt(),
        code_manifest=_code_manifest(),
        training_config=_training_config(),
    )
    contract["input_lineage"] = {}
    _rehash_contract(contract)

    validation = validate_alr_challenger_training_contract(contract)
    assert validation.valid is False
    assert validation.reason == "input_lineage_fields_invalid"


def test_validator_rejects_rehashed_config_with_external_requests() -> None:
    contract = build_alr_challenger_training_contract(
        _ready_receipt(),
        code_manifest=_code_manifest(),
        training_config=_training_config(),
    )
    config = contract["training_config"]
    config["resource_budget"]["max_external_requests"] = 7
    payload = copy.deepcopy(config)
    payload.pop("training_config_hash")
    config["training_config_hash"] = _canonical_hash(payload)
    _rehash_contract(contract)

    validation = validate_alr_challenger_training_contract(contract)
    assert validation.valid is False
    assert validation.reason.startswith("training_config_semantic_invalid:")


def test_validator_rejects_integer_boolean_aliases() -> None:
    contract = build_alr_challenger_training_contract(
        _ready_receipt(),
        code_manifest=_code_manifest(),
        training_config=_training_config(),
    )
    contract["source_contract_ready"] = 1
    contract["contract_hash"] = compute_alr_challenger_training_contract_hash(contract)

    validation = validate_alr_challenger_training_contract(contract)
    assert validation.valid is False
    assert validation.reason == "source_contract_ready_not_true"


@pytest.mark.parametrize(
    ("section", "field", "value", "reason"),
    [
        (
            "execution_contract",
            "actual_dataset_rehash_required",
            1,
            "execution_contract_invalid",
        ),
        ("no_authority", "exchange_authority", 0, "no_authority_invalid"),
        (
            "authority_counters",
            "exchange_contact_count",
            False,
            "authority_counters_invalid",
        ),
    ],
)
def test_validator_rejects_nested_bool_integer_aliases(
    section: str, field: str, value: object, reason: str
) -> None:
    contract = build_alr_challenger_training_contract(
        _ready_receipt(),
        code_manifest=_code_manifest(),
        training_config=_training_config(),
    )
    contract[section][field] = value
    contract["contract_hash"] = compute_alr_challenger_training_contract_hash(contract)

    validation = validate_alr_challenger_training_contract(contract)
    assert validation.valid is False
    assert validation.reason == reason


def test_validator_returns_invalid_for_noncanonical_nested_values() -> None:
    contract = build_alr_challenger_training_contract(
        _ready_receipt(),
        code_manifest=_code_manifest(),
        training_config=_training_config(),
    )
    contract["input_lineage"]["row_count"] = float("nan")

    validation = validate_alr_challenger_training_contract(contract)
    assert validation.valid is False
    assert validation.reason in {
        "input_lineage_row_count_invalid",
        "training_input_hash_uncomputable",
    }


def test_builder_accepts_no_caller_pit_or_raw_candidate_inputs() -> None:
    signature = inspect.signature(build_alr_challenger_training_contract)
    assert tuple(signature.parameters) == (
        "repository_receipt",
        "code_manifest",
        "training_config",
    )
    assert signature.parameters["code_manifest"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["training_config"].kind is inspect.Parameter.KEYWORD_ONLY
