from __future__ import annotations

import pytest

from ml_training.registry_serving_contract import (
    ADVISORY_READY,
    INVALID,
    PENDING_SCHEMA,
    PIT_DATASET_MANIFEST_SCHEMA_VERSION,
    REGISTRY_SERVING_CONTRACT_FIELD,
    REGISTRY_SERVING_CONTRACT_SCHEMA_VERSION,
    RegistryServingContractError,
    attach_registry_serving_contract,
    compute_registry_serving_contract_hash,
    extract_registry_serving_contract,
    validate_registry_serving_contract,
)


def _valid_contract(**overrides) -> dict:
    contract = {
        "schema_version": REGISTRY_SERVING_CONTRACT_SCHEMA_VERSION,
        "serving_mode": "advisory_only",
        "not_authority": True,
        "symlink_authority": False,
        "promotion_serving_ready": False,
        "dataset_manifest_schema_version": PIT_DATASET_MANIFEST_SCHEMA_VERSION,
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


def test_valid_registry_serving_contract_passes_and_hash_is_stable() -> None:
    contract = _valid_contract()

    validation = validate_registry_serving_contract(contract)

    assert validation.advisory_ready is True
    assert validation.verdict == ADVISORY_READY
    assert validation.reason == "ok"

    reordered = dict(reversed(list(contract.items())))
    assert compute_registry_serving_contract_hash(contract) == (
        compute_registry_serving_contract_hash(reordered)
    )


def test_extract_reads_canonical_field_only() -> None:
    contract = _valid_contract()

    assert extract_registry_serving_contract(
        {REGISTRY_SERVING_CONTRACT_FIELD: contract}
    ) == contract
    assert extract_registry_serving_contract({"serving_contract": contract}) is None


def test_missing_dataset_manifest_hash_is_pending_schema() -> None:
    contract = _valid_contract()
    contract.pop("dataset_manifest_hash")
    contract["contract_hash"] = compute_registry_serving_contract_hash(contract)

    validation = validate_registry_serving_contract(contract)

    assert validation.advisory_ready is False
    assert validation.verdict == PENDING_SCHEMA
    assert validation.reason == "dataset_manifest_hash_missing"


@pytest.mark.parametrize(
    ("override", "reason"),
    (
        ({}, "dataset_manifest_schema_version_missing"),
        (
            {"dataset_manifest_schema_version": "pit_dataset_manifest_v2"},
            "dataset_manifest_schema_version_unknown",
        ),
    ),
)
def test_dataset_manifest_schema_version_is_required(
    override: dict,
    reason: str,
) -> None:
    contract = _valid_contract()
    if override:
        contract.update(override)
    else:
        contract.pop("dataset_manifest_schema_version")
    contract["contract_hash"] = compute_registry_serving_contract_hash(contract)

    validation = validate_registry_serving_contract(contract)

    assert validation.advisory_ready is False
    assert validation.verdict == PENDING_SCHEMA
    assert validation.reason == reason


def test_partial_artifact_hashes_are_invalid() -> None:
    contract = _valid_contract()
    contract["artifact_hashes"] = {"q50": "3" * 64}
    contract["contract_hash"] = compute_registry_serving_contract_hash(contract)

    validation = validate_registry_serving_contract(contract)

    assert validation.advisory_ready is False
    assert validation.verdict == INVALID
    assert validation.reason == "artifact_hashes_missing_quantiles:q10,q90"


def test_extra_artifact_hashes_are_invalid() -> None:
    contract = _valid_contract()
    contract["artifact_hashes"] = {
        "q10": "2" * 64,
        "q50": "3" * 64,
        "q90": "4" * 64,
        "q99": "5" * 64,
    }
    contract["contract_hash"] = compute_registry_serving_contract_hash(contract)

    validation = validate_registry_serving_contract(contract)

    assert validation.advisory_ready is False
    assert validation.verdict == INVALID
    assert validation.reason == "artifact_hashes_extra_quantiles:q99"


def test_extra_top_level_field_is_invalid_and_cannot_attach() -> None:
    contract = _valid_contract()
    contract["notes"] = "x"
    contract["contract_hash"] = compute_registry_serving_contract_hash(contract)

    validation = validate_registry_serving_contract(contract)

    assert validation.advisory_ready is False
    assert validation.verdict == INVALID
    assert validation.reason == "top_level_fields_unknown:notes"
    with pytest.raises(
        RegistryServingContractError,
        match="top_level_fields_unknown:notes",
    ):
        attach_registry_serving_contract({"verdict": "shadow_only"}, contract)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    (
        ("missingness_policy", {"nan_sentinel": -999.0}, "missingness_policy_not_string"),
        ("units", ["prediction:bps"], "units_not_string"),
        ("side_handling", "", "side_handling_empty"),
    ),
)
def test_policy_fields_must_be_non_empty_strings(
    field: str,
    value: object,
    reason: str,
) -> None:
    contract = _valid_contract(**{field: value})

    validation = validate_registry_serving_contract(contract)

    assert validation.advisory_ready is False
    assert validation.verdict == INVALID
    assert validation.reason == reason


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    (
        ("promotion_serving_ready", True, "promotion_serving_ready_not_false"),
        ("symlink_authority", True, "symlink_authority_not_false"),
        ("not_authority", False, "not_authority_not_true"),
    ),
)
def test_authority_boundary_flags_are_invalid(
    field: str,
    value: bool,
    reason: str,
) -> None:
    contract = _valid_contract(**{field: value})

    validation = validate_registry_serving_contract(contract)

    assert validation.advisory_ready is False
    assert validation.verdict == INVALID
    assert validation.reason == reason


def test_order_allowed_alias_is_invalid() -> None:
    contract = _valid_contract()
    contract["answers"] = {"order_allowed": True}
    contract["contract_hash"] = compute_registry_serving_contract_hash(contract)

    validation = validate_registry_serving_contract(contract)

    assert validation.advisory_ready is False
    assert validation.verdict == INVALID
    assert validation.authority_boundary_violation is True
    assert validation.reason == "authority_boundary_violation:answers.order_allowed"


def test_contract_hash_mismatch_is_invalid() -> None:
    contract = _valid_contract()
    contract["contract_hash"] = "0" * 64

    validation = validate_registry_serving_contract(contract)

    assert validation.advisory_ready is False
    assert validation.verdict == INVALID
    assert validation.reason == "contract_hash_mismatch"


def test_attach_copies_and_attaches_only_valid_contract() -> None:
    report = {"verdict": "shadow_only", "metrics": {"brier": 0.2}}
    contract = _valid_contract()

    attached = attach_registry_serving_contract(report, contract)

    assert attached is not report
    assert attached["metrics"] is not report["metrics"]
    assert attached[REGISTRY_SERVING_CONTRACT_FIELD] == contract
    assert REGISTRY_SERVING_CONTRACT_FIELD not in report

    invalid = _valid_contract(promotion_serving_ready=True)
    with pytest.raises(RegistryServingContractError):
        attach_registry_serving_contract(report, invalid)
    assert REGISTRY_SERVING_CONTRACT_FIELD not in report
