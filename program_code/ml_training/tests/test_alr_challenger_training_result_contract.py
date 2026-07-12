from __future__ import annotations

import copy
import hashlib
import inspect
from collections.abc import Mapping, Sequence

import pytest

import ml_training.alr_challenger_training_result_contract as result_contract_module
from ml_training.alr_challenger_training_result_contract import (
    ALR_CHALLENGER_TRAINING_RESULT_CONTRACT_SCHEMA_VERSION,
    EXECUTION_EVIDENCE_REQUIRED,
    NOT_ESTABLISHED,
    AlrChallengerTrainingResultContractError,
    build_alr_challenger_training_result_contract,
    compute_alr_challenger_training_result_hash,
    validate_alr_challenger_training_result_contract,
)
from ml_training.tests.test_alr_challenger_repository import (
    _expected_payload,
    _receipt_row,
    _training_contract,
)


def _bound_inputs() -> tuple[dict, dict]:
    contract = _training_contract()
    receipt_read = {
        "status": "FOUND",
        "receipt": _receipt_row(_expected_payload(contract)),
    }
    return contract, receipt_read


def _io_descriptor() -> dict:
    return {
        "schema_version": "alr_challenger_onnx_io_descriptor_v1",
        "input_tensor_name": "features",
        "input_dtype": "float32",
        "input_rank": 2,
        "output_tensor_name": "prediction",
        "output_dtype": "float32",
        "output_rank": 1,
    }


def _trainer_spec() -> dict:
    return {
        "schema_version": "alr_challenger_observed_trainer_spec_v1",
        "implementation": "lightgbm",
        "implementation_version": "4.5.0",
        "algorithm": "lightgbm_quantile_trio",
        "quantiles": ["q10", "q50", "q90"],
        "parameters": {
            "num_leaves": 7,
            "learning_rate": {"coefficient": 5, "scale": 2},
            "n_estimators": 500,
            "early_stopping_rounds": 50,
            "min_data_in_leaf": None,
            "feature_fraction": {"coefficient": 8, "scale": 1},
            "bagging_fraction": {"coefficient": 8, "scale": 1},
            "bagging_freq": 5,
            "lambda_l2": {"coefficient": 1, "scale": 1},
            "label_window_hours": {"coefficient": 4, "scale": 0},
            "decay_halflife_days": {"coefficient": 14, "scale": 0},
            "bootstrap_iterations": 1000,
            "bootstrap_seed": 42,
            "parameter_schema_version": "v1",
        },
    }


def _observation() -> dict:
    return {
        "schema_version": "alr_challenger_post_fit_observation_v1",
        "attempt_id": "attempt-0001",
        "trainer_spec": _trainer_spec(),
        "seed": 42,
        "fit_started_at": "2026-07-11T20:00:00.123456Z",
        "fit_completed_at": "2026-07-11T20:00:02.654321Z",
        "model_schema_version": "alr-quantile-v1",
        "artifacts": {
            "q10": {
                "format": "onnx",
                "model_bytes": b"onnx-q10-fixture",
                "io_descriptor": _io_descriptor(),
            },
            "q50": {
                "format": "onnx",
                "model_bytes": b"onnx-q50-fixture",
                "io_descriptor": _io_descriptor(),
            },
            "q90": {
                "format": "onnx",
                "model_bytes": b"onnx-q90-fixture",
                "io_descriptor": _io_descriptor(),
            },
        },
        "metrics": {
            "validation_pinball_loss_q10": {"coefficient": 1234, "scale": 4},
            "validation_pinball_loss_q50": {"coefficient": 1011, "scale": 4},
            "validation_pinball_loss_q90": {"coefficient": 1199, "scale": 4},
        },
        "resource_observation": {
            "wall_time_microseconds": 2_530_865,
            "cpu_time_microseconds": 4_100_000,
            "peak_memory_bytes": 16_777_216,
            "total_artifact_bytes": 48,
            "training_rows": 128,
            "external_request_count": 0,
            "api_cost_microusd": 0,
        },
    }


def _built_contract() -> dict:
    training_contract, receipt_read = _bound_inputs()
    return build_alr_challenger_training_result_contract(
        receipt_read,
        training_contract=training_contract,
        observation=_observation(),
    )


def _rehash_result(contract: dict) -> None:
    contract["result_hash"] = compute_alr_challenger_training_result_hash(
        contract
    )


class _ExplodingDeepcopy:
    def __deepcopy__(self, _memo):
        raise RuntimeError("deliberate-deepcopy-failure")


class _GuardedInfiniteSequence(Sequence):
    def __init__(self) -> None:
        self.accesses = 0

    def __len__(self) -> int:
        return 1

    def __getitem__(self, index):
        if isinstance(index, slice):
            raise TypeError("slices_not_supported")
        self.accesses += 1
        if self.accesses > 50_005:
            raise AssertionError("sequence_was_eagerly_consumed")
        return 0


class _ExplodingItemsMapping(Mapping):
    def __getitem__(self, key):
        raise KeyError(key)

    def __iter__(self):
        return iter(())

    def __len__(self) -> int:
        return 0

    def items(self):
        raise RuntimeError("deliberate-items-failure")


def test_result_contract_public_api_accepts_only_bound_observation_inputs() -> None:
    build_parameters = inspect.signature(
        build_alr_challenger_training_result_contract
    ).parameters
    validate_parameters = inspect.signature(
        validate_alr_challenger_training_result_contract
    ).parameters

    assert tuple(build_parameters) == (
        "qualified_receipt_read",
        "training_contract",
        "observation",
    )
    assert build_parameters["training_contract"].kind is (
        inspect.Parameter.KEYWORD_ONLY
    )
    assert build_parameters["observation"].kind is inspect.Parameter.KEYWORD_ONLY
    assert tuple(validate_parameters) == ("contract",)


def test_builds_deterministic_unestablished_post_fit_observation_contract() -> None:
    training_contract, receipt_read = _bound_inputs()
    observation = _observation()
    original_training_contract = copy.deepcopy(training_contract)
    original_receipt_read = copy.deepcopy(receipt_read)
    original_observation = copy.deepcopy(observation)

    first = build_alr_challenger_training_result_contract(
        receipt_read,
        training_contract=training_contract,
        observation=observation,
    )
    second = build_alr_challenger_training_result_contract(
        copy.deepcopy(receipt_read),
        training_contract=copy.deepcopy(training_contract),
        observation=copy.deepcopy(observation),
    )

    artifact_hashes = {
        quantile: hashlib.sha256(
            observation["artifacts"][quantile]["model_bytes"]
        ).hexdigest()
        for quantile in ("q10", "q50", "q90")
    }
    expected_set_hash = hashlib.sha256(
        (
            f"q10={artifact_hashes['q10']}\n"
            f"q50={artifact_hashes['q50']}\n"
            f"q90={artifact_hashes['q90']}\n"
        ).encode("utf-8")
    ).hexdigest()

    assert first == second
    assert set(first) == {
        "schema_version",
        "contract_kind",
        "status",
        "reason",
        "execution_claim",
        "model_training_performed_claim",
        "persistence_allowed",
        "attestation_required",
        "v158_persistence_schema_required",
        "admission",
        "expected_training_inputs",
        "submitted_observation",
        "evidence_obligations",
        "training_run_hash",
        "model_artifact_set_hash",
        "challenger_hash",
        "no_authority",
        "authority_counters",
        "result_hash",
    }
    assert first["schema_version"] == (
        ALR_CHALLENGER_TRAINING_RESULT_CONTRACT_SCHEMA_VERSION
    )
    assert first["contract_kind"] == "POST_FIT_RESULT_OBSERVATION"
    assert first["status"] == EXECUTION_EVIDENCE_REQUIRED
    assert first["reason"] == (
        "trusted_fit_attestation_and_v158_schema_binding_required"
    )
    assert first["execution_claim"] == NOT_ESTABLISHED
    assert first["model_training_performed_claim"] == NOT_ESTABLISHED
    assert first["persistence_allowed"] is False
    assert first["attestation_required"] is True
    assert first["v158_persistence_schema_required"] is True
    assert first["admission"]["training_contract"] == training_contract
    assert first["admission"]["qualified_receipt_read"] == receipt_read
    assert first["expected_training_inputs"]["source_head"] == "a" * 40
    assert first["expected_training_inputs"]["dataset_hash"] == "e" * 64
    assert first["expected_training_inputs"]["training_rows"] == 128
    assert first["submitted_observation"]["observation_claim"] == "UNVERIFIED"
    assert first["submitted_observation"]["trainer_spec"] == _trainer_spec()
    assert first["submitted_observation"]["trainer_spec_claim"] == "UNVERIFIED"
    assert len(first["submitted_observation"]["trainer_spec_hash"]) == 64
    assert first["submitted_observation"]["seed"] == 42
    assert first["submitted_observation"]["seed_claim"] == "UNVERIFIED"
    assert [
        artifact["quantile"]
        for artifact in first["submitted_observation"]["artifacts"]
    ] == ["q10", "q50", "q90"]
    assert {
        artifact["quantile"]: artifact["artifact_hash"]
        for artifact in first["submitted_observation"]["artifacts"]
    } == artifact_hashes
    assert all(
        artifact["observation_claim"] == "UNVERIFIED"
        for artifact in first["submitted_observation"]["artifacts"]
    )
    assert first["model_artifact_set_hash"] == expected_set_hash
    assert first["submitted_observation"]["metrics_claim"] == "UNVERIFIED"
    assert first["submitted_observation"]["resource_claim"] == "UNVERIFIED"
    assert len(first["training_run_hash"]) == 64
    assert len(first["challenger_hash"]) == 64
    assert len(first["result_hash"]) == 64
    assert set(first["no_authority"].values()) == {False}
    assert set(first["authority_counters"].values()) == {0}
    assert first["authority_counters"]["model_fit_count"] == 0
    assert validate_alr_challenger_training_result_contract(first).valid is True
    assert b"onnx-q10-fixture" not in repr(first).encode("utf-8")
    assert training_contract == original_training_contract
    assert receipt_read == original_receipt_read
    assert observation == original_observation


def test_training_run_identity_is_pre_artifact_and_result_binds_observations() -> None:
    training_contract, receipt_read = _bound_inputs()
    baseline_observation = _observation()
    changed_artifact = copy.deepcopy(baseline_observation)
    changed_artifact["artifacts"]["q90"]["model_bytes"] = b"changed-q90-onnx"
    changed_artifact["resource_observation"]["total_artifact_bytes"] = 48
    baseline = build_alr_challenger_training_result_contract(
        receipt_read,
        training_contract=training_contract,
        observation=baseline_observation,
    )
    changed = build_alr_challenger_training_result_contract(
        receipt_read,
        training_contract=training_contract,
        observation=changed_artifact,
    )

    assert changed["training_run_hash"] == baseline["training_run_hash"]
    assert changed["model_artifact_set_hash"] != baseline["model_artifact_set_hash"]
    assert changed["challenger_hash"] != baseline["challenger_hash"]
    assert changed["result_hash"] != baseline["result_hash"]

    changed_metrics = copy.deepcopy(baseline_observation)
    changed_metrics["metrics"]["validation_pinball_loss_q50"] = {
        "coefficient": 1012,
        "scale": 4,
    }
    metrics_result = build_alr_challenger_training_result_contract(
        receipt_read,
        training_contract=training_contract,
        observation=changed_metrics,
    )
    assert metrics_result["training_run_hash"] == baseline["training_run_hash"]
    assert metrics_result["challenger_hash"] == baseline["challenger_hash"]
    assert metrics_result["result_hash"] != baseline["result_hash"]

    changed_trainer = copy.deepcopy(baseline_observation)
    changed_trainer["trainer_spec"]["implementation_version"] = "4.5.1"
    trainer_result = build_alr_challenger_training_result_contract(
        receipt_read,
        training_contract=training_contract,
        observation=changed_trainer,
    )
    assert trainer_result["training_run_hash"] != baseline["training_run_hash"]
    assert trainer_result["result_hash"] != baseline["result_hash"]


def test_builder_requires_exact_found_receipt_bound_to_full_contract() -> None:
    training_contract, receipt_read = _bound_inputs()

    with pytest.raises(
        AlrChallengerTrainingResultContractError,
        match="qualified_receipt_not_found",
    ):
        build_alr_challenger_training_result_contract(
            {"status": "NOT_FOUND", "receipt": None},
            training_contract=training_contract,
            observation=_observation(),
        )

    tampered_read = copy.deepcopy(receipt_read)
    tampered_read["receipt"]["canonical_payload"]["dataset_hash"] = "f" * 64
    with pytest.raises(
        AlrChallengerTrainingResultContractError,
        match="qualified_receipt_read_invalid:receipt_row_content_mismatch",
    ):
        build_alr_challenger_training_result_contract(
            tampered_read,
            training_contract=training_contract,
            observation=_observation(),
        )

    tampered_contract = copy.deepcopy(training_contract)
    tampered_contract["contract_hash"] = "f" * 64
    with pytest.raises(
        AlrChallengerTrainingResultContractError,
        match="training_contract_invalid:contract_hash_mismatch",
    ):
        build_alr_challenger_training_result_contract(
            receipt_read,
            training_contract=tampered_contract,
            observation=_observation(),
        )


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (
            lambda value: value.update(training_run_hash="f" * 64),
            "observation_fields_invalid",
        ),
        (
            lambda value: value.update(status="TRAINING_PERFORMED"),
            "observation_fields_invalid",
        ),
        (
            lambda value: value.update(trainer_spec_hash="f" * 64),
            "observation_fields_invalid",
        ),
        (
            lambda value: value["artifacts"]["q10"].update(
                artifact_path="runs/fake/q10.onnx"
            ),
            "artifact_q10_fields_invalid",
        ),
        (
            lambda value: value["artifacts"].pop("q90"),
            "artifact_quantile_set_invalid",
        ),
        (
            lambda value: value["artifacts"]["q90"].update(
                model_bytes=value["artifacts"]["q10"]["model_bytes"]
            ),
            "artifact_hashes_not_distinct",
        ),
        (
            lambda value: value["artifacts"]["q10"].update(
                model_bytes=bytearray(b"not-immutable")
            ),
            "artifact_q10_bytes_invalid",
        ),
        (
            lambda value: value["artifacts"]["q10"].update(format="pickle"),
            "artifact_q10_format_invalid",
        ),
        (
            lambda value: value["artifacts"]["q10"]["io_descriptor"].update(
                output_rank=True
            ),
            "output_rank_invalid",
        ),
        (
            lambda value: value.update(
                fit_started_at="2026-07-11T20:00:00+00:00"
            ),
            "fit_started_at_invalid",
        ),
        (
            lambda value: value.update(
                fit_completed_at="2026-07-11T19:59:59.000000Z"
            ),
            "fit_completed_before_started",
        ),
        (
            lambda value: value.update(model_schema_version="../unsafe"),
            "model_schema_version_invalid",
        ),
    ],
)
def test_builder_rejects_identity_status_path_and_artifact_spoofing(
    mutation,
    reason: str,
) -> None:
    training_contract, receipt_read = _bound_inputs()
    observation = _observation()
    mutation(observation)

    with pytest.raises(AlrChallengerTrainingResultContractError, match=reason):
        build_alr_challenger_training_result_contract(
            receipt_read,
            training_contract=training_contract,
            observation=observation,
        )


@pytest.mark.parametrize(
    ("metrics", "reason"),
    [
        (
            {"loss": 0.1},
            "metric_exact_decimal_invalid:loss",
        ),
        (
            {1: {"coefficient": 1, "scale": 0}},
            "metric_key_invalid",
        ),
        (
            {
                "loss": {"coefficient": 1, "scale": 0},
                2: {"coefficient": 2, "scale": 0},
            },
            "metric_key_invalid",
        ),
        (
            {"model_path": {"coefficient": 1, "scale": 0}},
            "metric_key_forbidden:model_path",
        ),
        (
            {"loss": {"coefficient": True, "scale": 0}},
            "metric_coefficient_invalid:loss",
        ),
        (
            {"loss": {"coefficient": 120, "scale": 2}},
            "metric_exact_decimal_not_canonical:loss",
        ),
    ],
)
def test_metrics_use_closed_exact_decimal_no_float_no_path_grammar(
    metrics: dict,
    reason: str,
) -> None:
    training_contract, receipt_read = _bound_inputs()
    observation = _observation()
    observation["metrics"] = metrics

    with pytest.raises(AlrChallengerTrainingResultContractError, match=reason):
        build_alr_challenger_training_result_contract(
            receipt_read,
            training_contract=training_contract,
            observation=observation,
        )


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (
            lambda value: value["trainer_spec"].update(config_hash="f" * 64),
            "trainer_spec_fields_invalid",
        ),
        (
            lambda value: value["trainer_spec"]["parameters"].update(
                learning_rate=0.05
            ),
            "trainer_spec_parameters_mismatch",
        ),
        (
            lambda value: value.update(seed=True),
            "seed_invalid",
        ),
        (
            lambda value: value.update(seed=43),
            "seed_mismatch",
        ),
    ],
)
def test_trainer_spec_and_seed_are_closed_unverified_observations(
    mutation,
    reason: str,
) -> None:
    training_contract, receipt_read = _bound_inputs()
    observation = _observation()
    mutation(observation)

    with pytest.raises(AlrChallengerTrainingResultContractError, match=reason):
        build_alr_challenger_training_result_contract(
            receipt_read,
            training_contract=training_contract,
            observation=observation,
        )


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("training_rows", True, "resource_observation_invalid:training_rows"),
        ("training_rows", 127, "resource_training_rows_mismatch"),
        ("total_artifact_bytes", 47, "resource_artifact_bytes_mismatch"),
        ("external_request_count", 1, "resource_external_requests_not_zero"),
        ("api_cost_microusd", 1, "resource_api_cost_not_zero"),
        (
            "peak_memory_bytes",
            2_147_483_649,
            "resource_budget_exceeded:peak_memory_bytes",
        ),
    ],
)
def test_resource_observation_is_exact_zero_contact_and_budget_bounded(
    field: str,
    value: object,
    reason: str,
) -> None:
    training_contract, receipt_read = _bound_inputs()
    observation = _observation()
    observation["resource_observation"][field] = value

    with pytest.raises(AlrChallengerTrainingResultContractError, match=reason):
        build_alr_challenger_training_result_contract(
            receipt_read,
            training_contract=training_contract,
            observation=observation,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.pop("admission"),
        lambda value: value["admission"].pop("training_contract"),
        lambda value: value["submitted_observation"].pop("metrics_hash"),
        lambda value: value["submitted_observation"]["artifacts"].reverse(),
    ],
)
def test_validator_fails_closed_without_throwing_on_malformed_contract(
    mutation,
) -> None:
    contract = _built_contract()
    mutation(contract)
    _rehash_result(contract)

    validation = validate_alr_challenger_training_result_contract(contract)

    assert validation.valid is False
    assert validation.verdict == "INVALID"
    assert validation.reason != "ok"


def test_validator_is_total_for_deep_and_exploding_snapshot_inputs() -> None:
    deep: dict = {}
    cursor = deep
    for _ in range(1_100):
        child: dict = {}
        cursor["child"] = child
        cursor = child

    deep_validation = validate_alr_challenger_training_result_contract(deep)
    exploding_validation = validate_alr_challenger_training_result_contract(
        {"payload": _ExplodingDeepcopy()}
    )
    mapping_validation = validate_alr_challenger_training_result_contract(
        _ExplodingItemsMapping()
    )

    assert deep_validation.valid is False
    assert deep_validation.verdict == "INVALID"
    assert "depth" in deep_validation.reason or "snapshot" in deep_validation.reason
    assert exploding_validation.valid is False
    assert exploding_validation.verdict == "INVALID"
    assert "snapshot" in exploding_validation.reason
    assert mapping_validation.valid is False
    assert mapping_validation.verdict == "INVALID"
    assert "snapshot" in mapping_validation.reason


def test_validator_bounds_wide_and_infinite_sequences_while_consuming() -> None:
    wide_validation = validate_alr_challenger_training_result_contract(
        {"payload": list(range(50_001))}
    )
    infinite = _GuardedInfiniteSequence()
    infinite_validation = validate_alr_challenger_training_result_contract(
        {"payload": infinite}
    )

    assert wide_validation.valid is False
    assert "node_limit" in wide_validation.reason
    assert infinite_validation.valid is False
    assert "node_limit" in infinite_validation.reason
    assert infinite.accesses <= 50_001


def test_builder_converts_observation_snapshot_runtime_error_to_domain_error() -> None:
    training_contract, receipt_read = _bound_inputs()
    observation = _observation()
    observation["metrics"]["exploding"] = _ExplodingDeepcopy()

    with pytest.raises(
        AlrChallengerTrainingResultContractError,
        match="observation_snapshot_invalid",
    ):
        build_alr_challenger_training_result_contract(
            receipt_read,
            training_contract=training_contract,
            observation=observation,
        )


def test_validator_rejects_rehashed_status_authority_and_metric_upgrades() -> None:
    mutations = []

    status = _built_contract()
    status["status"] = "TRAINING_PERFORMED"
    status["execution_claim"] = "ESTABLISHED"
    status["model_training_performed_claim"] = "ESTABLISHED"
    status["persistence_allowed"] = True
    _rehash_result(status)
    mutations.append(status)

    authority = _built_contract()
    authority["no_authority"]["invented_authority"] = False
    authority["authority_counters"]["invented_count"] = 0
    _rehash_result(authority)
    mutations.append(authority)

    metric = _built_contract()
    metric["submitted_observation"]["metrics"] = {"loss": 0.1}
    _rehash_result(metric)
    mutations.append(metric)

    for contract in mutations:
        assert validate_alr_challenger_training_result_contract(contract).valid is False


def test_validator_rechecks_resource_budget_after_self_consistent_rehash() -> None:
    contract = _built_contract()
    resources = contract["submitted_observation"]["resource_observation"]
    resources["peak_memory_bytes"] = 2_147_483_649
    contract["submitted_observation"]["resource_usage_hash"] = (
        result_contract_module._domain_hash("resource_observation", resources)
    )
    _rehash_result(contract)

    validation = validate_alr_challenger_training_result_contract(contract)

    assert validation.valid is False
    assert "resource_budget_exceeded:peak_memory_bytes" in validation.reasons


def test_source_contract_exposes_no_v158_writer_sql_or_legacy_argument_surface() -> None:
    contract = _built_contract()
    source = inspect.getsource(result_contract_module)

    assert "persist_alr_challenger_training_result_v1" not in source
    assert "psycopg" not in source.lower()
    assert "subprocess" not in source
    assert "artifact_path" not in contract["submitted_observation"]
    assert not any(key.startswith("actual_") for key in contract)
    assert contract["persistence_allowed"] is False
    with pytest.raises(TypeError):
        _legacy_v158_shape(**contract)


def _legacy_v158_shape(
    *,
    training_run_hash,
    durable_receipt_hash,
    training_key_hash,
    source_head,
    actual_dataset_hash,
    actual_row_ids_hash,
    actual_split_hash,
    actual_code_manifest_hash,
    actual_training_config_hash,
    actual_feature_schema_hash,
    actual_label_schema_hash,
    model_schema_version,
    actual_training_rows,
    model_artifact_set_hash,
    metrics_hash,
    resource_usage_hash,
    fit_started_at,
    fit_completed_at,
    q10_artifact_hash,
    q10_artifact_path,
    q10_artifact_size_bytes,
    q50_artifact_hash,
    q50_artifact_path,
    q50_artifact_size_bytes,
    q90_artifact_hash,
    q90_artifact_path,
    q90_artifact_size_bytes,
    challenger_hash,
):
    raise AssertionError("legacy V158 argument shape must remain unreachable")
