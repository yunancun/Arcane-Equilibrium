"""Pure, non-authoritative challenger post-fit observation contract.

The public builder only binds caller-submitted observations to an exact
qualified training receipt.  It does not prove that a fit occurred, parse or
publish model files, call PostgreSQL, or grant registry, serving, promotion, or
trading authority.  A trusted runner attestation and a forward persistence
schema binding are deliberately required before the observation can become a
durable training result.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from ml_training.alr_challenger_repository import (
    AlrChallengerRepositoryError,
    validate_qualified_training_receipt_read,
)
from ml_training.alr_challenger_training_contract import (
    validate_alr_challenger_training_contract,
)


ALR_CHALLENGER_TRAINING_RESULT_CONTRACT_SCHEMA_VERSION = (
    "alr_challenger_training_result_contract_v1"
)
POST_FIT_OBSERVATION_SCHEMA_VERSION = "alr_challenger_post_fit_observation_v1"
ONNX_IO_DESCRIPTOR_SCHEMA_VERSION = "alr_challenger_onnx_io_descriptor_v1"
OBSERVED_TRAINER_SPEC_SCHEMA_VERSION = "alr_challenger_observed_trainer_spec_v1"

EXECUTION_EVIDENCE_REQUIRED = "EXECUTION_EVIDENCE_REQUIRED"
NOT_ESTABLISHED = "NOT_ESTABLISHED"
UNVERIFIED = "UNVERIFIED"
INVALID = "INVALID"

_CONTRACT_KIND = "POST_FIT_RESULT_OBSERVATION"
_REASON = "trusted_fit_attestation_and_v158_schema_binding_required"
_QUANTILES = ("q10", "q50", "q90")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_ATTEMPT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,127}$")
_MODEL_SCHEMA_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,127}$")
_TENSOR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$")
_METRIC_KEY_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_IMPLEMENTATION_VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z_.+-]{0,63}$")
_UTC_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$"
)
_MAX_STRUCTURE_DEPTH = 64
_MAX_STRUCTURE_NODES = 50_000
_FORBIDDEN_METRIC_TERMS = (
    "authority",
    "deploy",
    "exchange",
    "hash",
    "live",
    "mainnet",
    "order",
    "password",
    "path",
    "probe",
    "promotion",
    "runtime",
    "secret",
    "serving",
    "symlink",
    "token",
)
_OBSERVATION_FIELDS = {
    "schema_version",
    "attempt_id",
    "trainer_spec",
    "seed",
    "fit_started_at",
    "fit_completed_at",
    "model_schema_version",
    "artifacts",
    "metrics",
    "resource_observation",
}
_TRAINER_SPEC_FIELDS = {
    "schema_version",
    "implementation",
    "implementation_version",
    "algorithm",
    "quantiles",
    "parameters",
}
_TRAINER_PARAMETER_FIELDS = {
    "num_leaves",
    "learning_rate",
    "n_estimators",
    "early_stopping_rounds",
    "min_data_in_leaf",
    "feature_fraction",
    "bagging_fraction",
    "bagging_freq",
    "lambda_l2",
    "label_window_hours",
    "decay_halflife_days",
    "bootstrap_iterations",
    "bootstrap_seed",
    "parameter_schema_version",
}
_TRAINER_DECIMAL_PARAMETER_FIELDS = {
    "learning_rate",
    "feature_fraction",
    "bagging_fraction",
    "lambda_l2",
    "label_window_hours",
    "decay_halflife_days",
}
_ARTIFACT_INPUT_FIELDS = {"format", "model_bytes", "io_descriptor"}
_IO_DESCRIPTOR_FIELDS = {
    "schema_version",
    "input_tensor_name",
    "input_dtype",
    "input_rank",
    "output_tensor_name",
    "output_dtype",
    "output_rank",
}
_RESOURCE_FIELDS = {
    "wall_time_microseconds",
    "cpu_time_microseconds",
    "peak_memory_bytes",
    "total_artifact_bytes",
    "training_rows",
    "external_request_count",
    "api_cost_microusd",
}
_EXPECTED_INPUT_FIELDS = {
    "training_contract_hash",
    "durable_receipt_hash",
    "training_key_hash",
    "source_head",
    "dataset_hash",
    "row_ids_hash",
    "split_hash",
    "code_manifest_hash",
    "training_config_hash",
    "feature_schema_hash",
    "label_schema_hash",
    "training_rows",
}
_ARTIFACT_OUTPUT_FIELDS = {
    "quantile",
    "format",
    "artifact_hash",
    "artifact_size_bytes",
    "io_descriptor",
    "io_descriptor_hash",
    "observation_claim",
}
_SUBMITTED_OBSERVATION_FIELDS = {
    "schema_version",
    "observation_claim",
    "attempt_id",
    "trainer_spec",
    "trainer_spec_claim",
    "trainer_spec_hash",
    "seed",
    "seed_claim",
    "fit_started_at",
    "fit_completed_at",
    "model_schema_version",
    "artifacts",
    "metrics",
    "metrics_claim",
    "metrics_hash",
    "resource_observation",
    "resource_claim",
    "resource_usage_hash",
}
_ADMISSION_FIELDS = {
    "training_contract",
    "qualified_receipt_read",
    "qualified_receipt_binding_hash",
}
_CONTRACT_FIELDS = {
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
_EVIDENCE_OBLIGATIONS = {
    "actual_dataset_rehash_required": True,
    "actual_row_ids_rehash_required": True,
    "actual_split_rehash_required": True,
    "actual_code_rehash_required": True,
    "effective_config_rehash_required": True,
    "actual_feature_schema_rehash_required": True,
    "actual_label_schema_rehash_required": True,
    "exact_source_head_required": True,
    "trusted_fit_attestation_required": True,
    "observed_trainer_spec_attestation_required": True,
    "observed_seed_attestation_required": True,
    "result_hash_attestation_binding_required": True,
    "artifact_readback_required": True,
    "onnx_semantic_validation_required": True,
    "durable_attestation_schema_required": True,
}


@dataclass(frozen=True)
class AlrChallengerTrainingResultContractValidation:
    valid: bool
    verdict: str
    reason: str
    reasons: tuple[str, ...]


class AlrChallengerTrainingResultContractError(ValueError):
    """An observation cannot form the closed source-only result contract."""


def build_alr_challenger_training_result_contract(
    qualified_receipt_read: Mapping[str, Any],
    *,
    training_contract: Mapping[str, Any],
    observation: Mapping[str, Any],
) -> dict[str, Any]:
    """Build one deterministic, explicitly unestablished observation envelope."""

    contract_snapshot = _validated_training_contract(training_contract)
    try:
        receipt_read = validate_qualified_training_receipt_read(
            qualified_receipt_read,
            training_contract=contract_snapshot,
        )
    except AlrChallengerRepositoryError as exc:
        raise AlrChallengerTrainingResultContractError(
            "qualified_receipt_read_invalid:" + str(exc)
        ) from exc
    if receipt_read["status"] != "FOUND":
        raise AlrChallengerTrainingResultContractError(
            "qualified_receipt_not_found"
        )

    expected_inputs = _expected_training_inputs(contract_snapshot, receipt_read)
    submitted, artifact_bytes = _normalize_observation(
        observation,
        training_contract=contract_snapshot,
        expected_inputs=expected_inputs,
    )
    receipt_binding_hash = _domain_hash(
        "qualified_receipt_read",
        receipt_read,
    )
    admission = {
        "training_contract": copy.deepcopy(contract_snapshot),
        "qualified_receipt_read": copy.deepcopy(receipt_read),
        "qualified_receipt_binding_hash": receipt_binding_hash,
    }
    training_run_hash = _training_run_hash(
        admission=admission,
        submitted=submitted,
    )
    artifact_hashes = {
        quantile: hashlib.sha256(artifact_bytes[quantile]).hexdigest()
        for quantile in _QUANTILES
    }
    model_artifact_set_hash = _model_artifact_set_hash(artifact_hashes)
    challenger_hash = _challenger_hash(
        training_run_hash=training_run_hash,
        model_artifact_set_hash=model_artifact_set_hash,
        submitted=submitted,
    )

    result: dict[str, Any] = {
        "schema_version": ALR_CHALLENGER_TRAINING_RESULT_CONTRACT_SCHEMA_VERSION,
        "contract_kind": _CONTRACT_KIND,
        "status": EXECUTION_EVIDENCE_REQUIRED,
        "reason": _REASON,
        "execution_claim": NOT_ESTABLISHED,
        "model_training_performed_claim": NOT_ESTABLISHED,
        "persistence_allowed": False,
        "attestation_required": True,
        "v158_persistence_schema_required": True,
        "admission": admission,
        "expected_training_inputs": expected_inputs,
        "submitted_observation": submitted,
        "evidence_obligations": copy.deepcopy(_EVIDENCE_OBLIGATIONS),
        "training_run_hash": training_run_hash,
        "model_artifact_set_hash": model_artifact_set_hash,
        "challenger_hash": challenger_hash,
        "no_authority": copy.deepcopy(contract_snapshot["no_authority"]),
        "authority_counters": copy.deepcopy(
            contract_snapshot["authority_counters"]
        ),
    }
    result["result_hash"] = compute_alr_challenger_training_result_hash(result)
    validation = validate_alr_challenger_training_result_contract(result)
    if not validation.valid:
        raise AlrChallengerTrainingResultContractError(validation.reason)
    return result


def compute_alr_challenger_training_result_hash(
    contract: Mapping[str, Any],
) -> str:
    """Compute the final observation identity that a future attestation binds."""

    payload = _snapshot_mapping(
        contract,
        not_mapping_reason="result_contract_not_mapping",
        snapshot_reason="result_contract_snapshot_invalid",
    )
    payload.pop("result_hash", None)
    return _domain_hash("result", payload)


def validate_alr_challenger_training_result_contract(
    contract: Any,
) -> AlrChallengerTrainingResultContractValidation:
    """Validate a closed envelope without upgrading its evidence class."""

    try:
        return _validate_alr_challenger_training_result_contract(contract)
    except Exception as exc:
        return _invalid(
            "result_contract_validation_failed:" + type(exc).__name__
        )


def _validate_alr_challenger_training_result_contract(
    contract: Any,
) -> AlrChallengerTrainingResultContractValidation:
    """Internal validator; the public seam converts every ordinary failure."""

    if not isinstance(contract, Mapping):
        return _invalid("result_contract_not_mapping")
    try:
        snapshot = _snapshot_mapping(
            contract,
            not_mapping_reason="result_contract_not_mapping",
            snapshot_reason="result_contract_snapshot_invalid",
        )
    except AlrChallengerTrainingResultContractError as exc:
        return _invalid(str(exc))

    reasons: list[str] = []
    if set(snapshot) != _CONTRACT_FIELDS:
        reasons.append("result_contract_fields_invalid")
    fixed_values = {
        "schema_version": ALR_CHALLENGER_TRAINING_RESULT_CONTRACT_SCHEMA_VERSION,
        "contract_kind": _CONTRACT_KIND,
        "status": EXECUTION_EVIDENCE_REQUIRED,
        "reason": _REASON,
        "execution_claim": NOT_ESTABLISHED,
        "model_training_performed_claim": NOT_ESTABLISHED,
        "persistence_allowed": False,
        "attestation_required": True,
        "v158_persistence_schema_required": True,
    }
    for field, expected in fixed_values.items():
        if not _same_scalar(snapshot.get(field), expected):
            reasons.append(field + "_invalid")

    admission = snapshot.get("admission")
    expected_inputs: dict[str, Any] | None = None
    validated_training_contract: dict[str, Any] | None = None
    expected_no_authority: Mapping[str, Any] | None = None
    expected_authority_counters: Mapping[str, Any] | None = None
    if not isinstance(admission, Mapping) or set(admission) != _ADMISSION_FIELDS:
        reasons.append("admission_invalid")
    else:
        training_contract = admission.get("training_contract")
        receipt_read = admission.get("qualified_receipt_read")
        try:
            validated_contract = _validated_training_contract(training_contract)
            validated_read = validate_qualified_training_receipt_read(
                receipt_read,
                training_contract=validated_contract,
            )
            if validated_read["status"] != "FOUND":
                raise AlrChallengerTrainingResultContractError(
                    "qualified_receipt_not_found"
                )
            expected_inputs = _expected_training_inputs(
                validated_contract,
                validated_read,
            )
            expected_no_authority = validated_contract["no_authority"]
            expected_authority_counters = validated_contract[
                "authority_counters"
            ]
            validated_training_contract = validated_contract
        except (AlrChallengerTrainingResultContractError, AlrChallengerRepositoryError) as exc:
            reasons.append("admission_invalid:" + str(exc))
        else:
            if admission.get("qualified_receipt_binding_hash") != _domain_hash(
                "qualified_receipt_read",
                validated_read,
            ):
                reasons.append("qualified_receipt_binding_hash_mismatch")

    claimed_inputs = snapshot.get("expected_training_inputs")
    if (
        expected_inputs is None
        or not isinstance(claimed_inputs, Mapping)
        or set(claimed_inputs) != _EXPECTED_INPUT_FIELDS
        or dict(claimed_inputs) != expected_inputs
    ):
        reasons.append("expected_training_inputs_invalid")

    submitted = snapshot.get("submitted_observation")
    if expected_inputs is None:
        reasons.append("submitted_observation_unverifiable")
    else:
        reasons.extend(
            _submitted_observation_reasons(
                submitted,
                expected_inputs=expected_inputs,
                training_contract=validated_training_contract,
            )
        )

    if snapshot.get("evidence_obligations") != _EVIDENCE_OBLIGATIONS:
        reasons.append("evidence_obligations_invalid")
    if (
        expected_no_authority is None
        or not _canonical_equal(
            snapshot.get("no_authority"),
            expected_no_authority,
        )
        or not _all_false(snapshot.get("no_authority"))
    ):
        reasons.append("no_authority_invalid")
    if (
        expected_authority_counters is None
        or not _canonical_equal(
            snapshot.get("authority_counters"),
            expected_authority_counters,
        )
        or not _all_zero(snapshot.get("authority_counters"))
    ):
        reasons.append("authority_counters_invalid")

    if isinstance(admission, Mapping) and isinstance(submitted, Mapping):
        try:
            expected_run = _training_run_hash(
                admission=admission,
                submitted=submitted,
            )
        except AlrChallengerTrainingResultContractError:
            reasons.append("training_run_hash_uncomputable")
        else:
            if snapshot.get("training_run_hash") != expected_run:
                reasons.append("training_run_hash_mismatch")
    elif not _is_hash(snapshot.get("training_run_hash")):
        reasons.append("training_run_hash_invalid")

    artifact_hashes = _artifact_hashes_from_submitted(submitted)
    if artifact_hashes is None:
        reasons.append("model_artifact_set_hash_unverifiable")
    else:
        expected_set_hash = _model_artifact_set_hash(artifact_hashes)
        if snapshot.get("model_artifact_set_hash") != expected_set_hash:
            reasons.append("model_artifact_set_hash_mismatch")

    if (
        isinstance(submitted, Mapping)
        and _is_hash(snapshot.get("training_run_hash"))
        and _is_hash(snapshot.get("model_artifact_set_hash"))
    ):
        try:
            expected_challenger = _challenger_hash(
                training_run_hash=snapshot["training_run_hash"],
                model_artifact_set_hash=snapshot["model_artifact_set_hash"],
                submitted=submitted,
            )
        except AlrChallengerTrainingResultContractError:
            reasons.append("challenger_hash_uncomputable")
        else:
            if snapshot.get("challenger_hash") != expected_challenger:
                reasons.append("challenger_hash_mismatch")
    elif not _is_hash(snapshot.get("challenger_hash")):
        reasons.append("challenger_hash_invalid")

    if _is_hash(snapshot.get("result_hash")):
        try:
            expected_result = compute_alr_challenger_training_result_hash(snapshot)
        except AlrChallengerTrainingResultContractError:
            reasons.append("result_hash_uncomputable")
        else:
            if snapshot["result_hash"] != expected_result:
                reasons.append("result_hash_mismatch")
    else:
        reasons.append("result_hash_invalid")

    if reasons:
        return _invalid(reasons[0], reasons)
    return AlrChallengerTrainingResultContractValidation(
        valid=True,
        verdict=EXECUTION_EVIDENCE_REQUIRED,
        reason="ok",
        reasons=(),
    )


def _validated_training_contract(value: Any) -> dict[str, Any]:
    snapshot = _snapshot_mapping(
        value,
        not_mapping_reason="training_contract_not_mapping",
        snapshot_reason="training_contract_snapshot_invalid",
    )
    validation = validate_alr_challenger_training_contract(snapshot)
    if not validation.valid:
        raise AlrChallengerTrainingResultContractError(
            "training_contract_invalid:" + validation.reason
        )
    return snapshot


def _expected_training_inputs(
    training_contract: Mapping[str, Any],
    receipt_read: Mapping[str, Any],
) -> dict[str, Any]:
    receipt = _required_mapping(receipt_read.get("receipt"), "receipt_invalid")
    payload = _required_mapping(
        receipt.get("canonical_payload"),
        "receipt_canonical_payload_invalid",
    )
    code = _required_mapping(training_contract.get("code_manifest"), "code_invalid")
    return {
        "training_contract_hash": training_contract["contract_hash"],
        "durable_receipt_hash": receipt["durable_receipt_hash"],
        "training_key_hash": receipt["training_key_hash"],
        "source_head": code["source_head"],
        "dataset_hash": payload["dataset_hash"],
        "row_ids_hash": payload["row_ids_hash"],
        "split_hash": payload["split_hash"],
        "code_manifest_hash": payload["code_manifest_hash"],
        "training_config_hash": payload["training_config_hash"],
        "feature_schema_hash": payload["feature_schema_hash"],
        "label_schema_hash": payload["label_schema_hash"],
        "training_rows": payload["training_rows"],
    }


def _normalize_observation(
    value: Any,
    *,
    training_contract: Mapping[str, Any],
    expected_inputs: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, bytes]]:
    observation = _snapshot_mapping(
        value,
        not_mapping_reason="observation_not_mapping",
        snapshot_reason="observation_snapshot_invalid",
    )
    if set(observation) != _OBSERVATION_FIELDS:
        raise AlrChallengerTrainingResultContractError(
            "observation_fields_invalid"
        )
    if observation.get("schema_version") != POST_FIT_OBSERVATION_SCHEMA_VERSION:
        raise AlrChallengerTrainingResultContractError(
            "observation_schema_version_invalid"
        )
    attempt_id = observation.get("attempt_id")
    if not isinstance(attempt_id, str) or not _ATTEMPT_ID_RE.fullmatch(attempt_id):
        raise AlrChallengerTrainingResultContractError("attempt_id_invalid")
    trainer_spec = _normalize_trainer_spec(
        observation.get("trainer_spec"),
        training_contract=training_contract,
    )
    seed = _normalize_seed(
        observation.get("seed"),
        training_contract=training_contract,
    )
    started = _canonical_utc_timestamp(
        observation.get("fit_started_at"),
        "fit_started_at_invalid",
    )
    completed = _canonical_utc_timestamp(
        observation.get("fit_completed_at"),
        "fit_completed_at_invalid",
    )
    if completed < started:
        raise AlrChallengerTrainingResultContractError(
            "fit_completed_before_started"
        )
    model_schema = observation.get("model_schema_version")
    if not isinstance(model_schema, str) or not _MODEL_SCHEMA_RE.fullmatch(
        model_schema
    ):
        raise AlrChallengerTrainingResultContractError(
            "model_schema_version_invalid"
        )

    artifacts_input = observation.get("artifacts")
    if not isinstance(artifacts_input, Mapping) or set(artifacts_input) != set(
        _QUANTILES
    ):
        raise AlrChallengerTrainingResultContractError(
            "artifact_quantile_set_invalid"
        )
    artifact_bytes: dict[str, bytes] = {}
    artifacts: list[dict[str, Any]] = []
    artifact_hashes: set[str] = set()
    for quantile in _QUANTILES:
        raw = artifacts_input.get(quantile)
        if not isinstance(raw, Mapping) or set(raw) != _ARTIFACT_INPUT_FIELDS:
            raise AlrChallengerTrainingResultContractError(
                f"artifact_{quantile}_fields_invalid"
            )
        if raw.get("format") != "onnx":
            raise AlrChallengerTrainingResultContractError(
                f"artifact_{quantile}_format_invalid"
            )
        model_bytes = raw.get("model_bytes")
        if type(model_bytes) is not bytes or not model_bytes:
            raise AlrChallengerTrainingResultContractError(
                f"artifact_{quantile}_bytes_invalid"
            )
        byte_snapshot = bytes(model_bytes)
        artifact_hash = hashlib.sha256(byte_snapshot).hexdigest()
        if artifact_hash in artifact_hashes:
            raise AlrChallengerTrainingResultContractError(
                "artifact_hashes_not_distinct"
            )
        artifact_hashes.add(artifact_hash)
        descriptor = _normalize_io_descriptor(raw.get("io_descriptor"))
        artifact_bytes[quantile] = byte_snapshot
        artifacts.append(
            {
                "quantile": quantile,
                "format": "onnx",
                "artifact_hash": artifact_hash,
                "artifact_size_bytes": len(byte_snapshot),
                "io_descriptor": descriptor,
                "io_descriptor_hash": _domain_hash(
                    "onnx_io_descriptor",
                    {"quantile": quantile, "descriptor": descriptor},
                ),
                "observation_claim": UNVERIFIED,
            }
        )

    metrics = _normalize_metrics(observation.get("metrics"))
    total_artifact_bytes = sum(len(item) for item in artifact_bytes.values())
    resources = _normalize_resources(
        observation.get("resource_observation"),
        training_contract=training_contract,
        expected_inputs=expected_inputs,
        total_artifact_bytes=total_artifact_bytes,
    )
    submitted = {
        "schema_version": POST_FIT_OBSERVATION_SCHEMA_VERSION,
        "observation_claim": UNVERIFIED,
        "attempt_id": attempt_id,
        "trainer_spec": trainer_spec,
        "trainer_spec_claim": UNVERIFIED,
        "trainer_spec_hash": _domain_hash(
            "trainer_spec_observation",
            trainer_spec,
        ),
        "seed": seed,
        "seed_claim": UNVERIFIED,
        "fit_started_at": observation["fit_started_at"],
        "fit_completed_at": observation["fit_completed_at"],
        "model_schema_version": model_schema,
        "artifacts": artifacts,
        "metrics": metrics,
        "metrics_claim": UNVERIFIED,
        "metrics_hash": _domain_hash("metrics_observation", metrics),
        "resource_observation": resources,
        "resource_claim": UNVERIFIED,
        "resource_usage_hash": _domain_hash(
            "resource_observation",
            resources,
        ),
    }
    return submitted, artifact_bytes


def _normalize_io_descriptor(value: Any) -> dict[str, Any]:
    descriptor = _snapshot_mapping(
        value,
        not_mapping_reason="io_descriptor_not_mapping",
        snapshot_reason="io_descriptor_snapshot_invalid",
    )
    if set(descriptor) != _IO_DESCRIPTOR_FIELDS:
        raise AlrChallengerTrainingResultContractError(
            "io_descriptor_fields_invalid"
        )
    if descriptor.get("schema_version") != ONNX_IO_DESCRIPTOR_SCHEMA_VERSION:
        raise AlrChallengerTrainingResultContractError(
            "io_descriptor_schema_version_invalid"
        )
    for field in ("input_tensor_name", "output_tensor_name"):
        item = descriptor.get(field)
        if not isinstance(item, str) or not _TENSOR_NAME_RE.fullmatch(item):
            raise AlrChallengerTrainingResultContractError(field + "_invalid")
    for field in ("input_dtype", "output_dtype"):
        if descriptor.get(field) not in {"float32", "float64", "int64"}:
            raise AlrChallengerTrainingResultContractError(field + "_invalid")
    for field in ("input_rank", "output_rank"):
        item = descriptor.get(field)
        if isinstance(item, bool) or not isinstance(item, int) or not 1 <= item <= 8:
            raise AlrChallengerTrainingResultContractError(field + "_invalid")
    return descriptor


def _normalize_trainer_spec(
    value: Any,
    *,
    training_contract: Mapping[str, Any],
) -> dict[str, Any]:
    spec = _snapshot_mapping(
        value,
        not_mapping_reason="trainer_spec_not_mapping",
        snapshot_reason="trainer_spec_snapshot_invalid",
    )
    if set(spec) != _TRAINER_SPEC_FIELDS:
        raise AlrChallengerTrainingResultContractError(
            "trainer_spec_fields_invalid"
        )
    if spec.get("schema_version") != OBSERVED_TRAINER_SPEC_SCHEMA_VERSION:
        raise AlrChallengerTrainingResultContractError(
            "trainer_spec_schema_version_invalid"
        )
    if spec.get("implementation") != "lightgbm":
        raise AlrChallengerTrainingResultContractError(
            "trainer_spec_implementation_invalid"
        )
    implementation_version = spec.get("implementation_version")
    if not isinstance(implementation_version, str) or not (
        _IMPLEMENTATION_VERSION_RE.fullmatch(implementation_version)
    ):
        raise AlrChallengerTrainingResultContractError(
            "trainer_spec_implementation_version_invalid"
        )
    config = _required_mapping(
        training_contract.get("training_config"),
        "training_config_invalid",
    )
    if spec.get("algorithm") != config.get("algorithm"):
        raise AlrChallengerTrainingResultContractError(
            "trainer_spec_algorithm_mismatch"
        )
    if not isinstance(spec.get("quantiles"), list) or spec["quantiles"] != list(
        _QUANTILES
    ):
        raise AlrChallengerTrainingResultContractError(
            "trainer_spec_quantiles_mismatch"
        )
    parameters = spec.get("parameters")
    if not isinstance(parameters, Mapping) or set(parameters) != (
        _TRAINER_PARAMETER_FIELDS
    ):
        raise AlrChallengerTrainingResultContractError(
            "trainer_spec_parameter_fields_invalid"
        )
    expected_parameters = _expected_trainer_parameters(config)
    if not _canonical_equal(parameters, expected_parameters):
        raise AlrChallengerTrainingResultContractError(
            "trainer_spec_parameters_mismatch"
        )
    spec["parameters"] = expected_parameters
    return spec


def _normalize_seed(
    value: Any,
    *,
    training_contract: Mapping[str, Any],
) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not (
        0 <= value <= 9_223_372_036_854_775_807
    ):
        raise AlrChallengerTrainingResultContractError("seed_invalid")
    config = _required_mapping(
        training_contract.get("training_config"),
        "training_config_invalid",
    )
    parameters = _required_mapping(
        config.get("parameters"),
        "training_parameters_invalid",
    )
    if value != parameters.get("bootstrap_seed"):
        raise AlrChallengerTrainingResultContractError("seed_mismatch")
    return value


def _expected_trainer_parameters(
    training_config: Mapping[str, Any],
) -> dict[str, Any]:
    source = _required_mapping(
        training_config.get("parameters"),
        "training_parameters_invalid",
    )
    expected: dict[str, Any] = {}
    for field in _TRAINER_PARAMETER_FIELDS:
        source_field = (
            "schema_version" if field == "parameter_schema_version" else field
        )
        item = source.get(source_field)
        expected[field] = (
            _exact_decimal_from_number(item)
            if field in _TRAINER_DECIMAL_PARAMETER_FIELDS
            else copy.deepcopy(item)
        )
    return expected


def _exact_decimal_from_number(value: Any) -> dict[str, int]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AlrChallengerTrainingResultContractError(
            "trainer_parameter_number_invalid"
        )
    decimal_value = Decimal(str(value))
    sign, digits, exponent = decimal_value.as_tuple()
    coefficient = 0
    for digit in digits:
        coefficient = coefficient * 10 + digit
    if sign:
        coefficient = -coefficient
    if exponent > 0:
        coefficient *= 10**exponent
        scale = 0
    else:
        scale = -exponent
    while coefficient != 0 and scale > 0 and coefficient % 10 == 0:
        coefficient //= 10
        scale -= 1
    if coefficient == 0:
        scale = 0
    return {"coefficient": coefficient, "scale": scale}


def _normalize_metrics(value: Any) -> dict[str, dict[str, int]]:
    if not isinstance(value, Mapping) or not value or len(value) > 128:
        raise AlrChallengerTrainingResultContractError("metrics_invalid")
    if not all(
        isinstance(key, str) and bool(_METRIC_KEY_RE.fullmatch(key))
        for key in value
    ):
        raise AlrChallengerTrainingResultContractError("metric_key_invalid")
    normalized: dict[str, dict[str, int]] = {}
    for key in sorted(value):
        if any(term in key for term in _FORBIDDEN_METRIC_TERMS):
            raise AlrChallengerTrainingResultContractError(
                "metric_key_forbidden:" + key
            )
        item = value[key]
        if not isinstance(item, Mapping) or set(item) != {
            "coefficient",
            "scale",
        }:
            raise AlrChallengerTrainingResultContractError(
                "metric_exact_decimal_invalid:" + key
            )
        coefficient = item.get("coefficient")
        scale = item.get("scale")
        if isinstance(coefficient, bool) or not isinstance(coefficient, int):
            raise AlrChallengerTrainingResultContractError(
                "metric_coefficient_invalid:" + key
            )
        if isinstance(scale, bool) or not isinstance(scale, int) or not 0 <= scale <= 18:
            raise AlrChallengerTrainingResultContractError(
                "metric_scale_invalid:" + key
            )
        if coefficient == 0 and scale != 0 or (
            coefficient != 0 and scale > 0 and coefficient % 10 == 0
        ):
            raise AlrChallengerTrainingResultContractError(
                "metric_exact_decimal_not_canonical:" + key
            )
        normalized[key] = {"coefficient": coefficient, "scale": scale}
    return normalized


def _normalize_resources(
    value: Any,
    *,
    training_contract: Mapping[str, Any],
    expected_inputs: Mapping[str, Any],
    total_artifact_bytes: int,
) -> dict[str, int]:
    if not isinstance(value, Mapping) or set(value) != _RESOURCE_FIELDS:
        raise AlrChallengerTrainingResultContractError(
            "resource_observation_fields_invalid"
        )
    resources = _snapshot_mapping(
        value,
        not_mapping_reason="resource_observation_not_mapping",
        snapshot_reason="resource_observation_snapshot_invalid",
    )
    for field in _RESOURCE_FIELDS:
        item = resources.get(field)
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise AlrChallengerTrainingResultContractError(
                "resource_observation_invalid:" + field
            )
    if resources["training_rows"] <= 0:
        raise AlrChallengerTrainingResultContractError(
            "resource_training_rows_invalid"
        )
    if resources["training_rows"] != expected_inputs["training_rows"]:
        raise AlrChallengerTrainingResultContractError(
            "resource_training_rows_mismatch"
        )
    if resources["total_artifact_bytes"] != total_artifact_bytes:
        raise AlrChallengerTrainingResultContractError(
            "resource_artifact_bytes_mismatch"
        )
    if resources["external_request_count"] != 0:
        raise AlrChallengerTrainingResultContractError(
            "resource_external_requests_not_zero"
        )
    if resources["api_cost_microusd"] != 0:
        raise AlrChallengerTrainingResultContractError(
            "resource_api_cost_not_zero"
        )
    config = _required_mapping(
        training_contract.get("training_config"),
        "training_config_invalid",
    )
    budget = _required_mapping(config.get("resource_budget"), "resource_budget_invalid")
    limits = {
        "wall_time_microseconds": budget["max_wall_seconds"] * 1_000_000,
        "cpu_time_microseconds": budget["max_cpu_seconds"] * 1_000_000,
        "peak_memory_bytes": budget["max_memory_bytes"],
        "total_artifact_bytes": budget["max_artifact_bytes"],
        "training_rows": budget["max_training_rows"],
    }
    for field, limit in limits.items():
        if resources[field] > limit:
            raise AlrChallengerTrainingResultContractError(
                "resource_budget_exceeded:" + field
            )
    return resources


def _submitted_observation_reasons(
    value: Any,
    *,
    expected_inputs: Mapping[str, Any],
    training_contract: Mapping[str, Any],
) -> list[str]:
    if not isinstance(value, Mapping) or set(value) != _SUBMITTED_OBSERVATION_FIELDS:
        return ["submitted_observation_fields_invalid"]
    reasons: list[str] = []
    fixed = {
        "schema_version": POST_FIT_OBSERVATION_SCHEMA_VERSION,
        "observation_claim": UNVERIFIED,
        "trainer_spec_claim": UNVERIFIED,
        "seed_claim": UNVERIFIED,
        "metrics_claim": UNVERIFIED,
        "resource_claim": UNVERIFIED,
    }
    for field, expected in fixed.items():
        if value.get(field) != expected:
            reasons.append(field + "_invalid")
    attempt_id = value.get("attempt_id")
    if not isinstance(attempt_id, str) or not _ATTEMPT_ID_RE.fullmatch(attempt_id):
        reasons.append("attempt_id_invalid")
    try:
        trainer_spec = _normalize_trainer_spec(
            value.get("trainer_spec"),
            training_contract=training_contract,
        )
    except AlrChallengerTrainingResultContractError as exc:
        reasons.append(str(exc))
    else:
        if value.get("trainer_spec_hash") != _domain_hash(
            "trainer_spec_observation",
            trainer_spec,
        ):
            reasons.append("trainer_spec_hash_mismatch")
    try:
        _normalize_seed(
            value.get("seed"),
            training_contract=training_contract,
        )
    except AlrChallengerTrainingResultContractError as exc:
        reasons.append(str(exc))
    try:
        started = _canonical_utc_timestamp(
            value.get("fit_started_at"),
            "fit_started_at_invalid",
        )
        completed = _canonical_utc_timestamp(
            value.get("fit_completed_at"),
            "fit_completed_at_invalid",
        )
        if completed < started:
            reasons.append("fit_completed_before_started")
    except AlrChallengerTrainingResultContractError as exc:
        reasons.append(str(exc))
    model_schema = value.get("model_schema_version")
    if not isinstance(model_schema, str) or not _MODEL_SCHEMA_RE.fullmatch(
        model_schema
    ):
        reasons.append("model_schema_version_invalid")

    artifacts = value.get("artifacts")
    total_artifact_bytes = 0
    if not isinstance(artifacts, list) or len(artifacts) != 3:
        reasons.append("submitted_artifacts_invalid")
    else:
        seen_hashes: set[str] = set()
        for index, quantile in enumerate(_QUANTILES):
            artifact = artifacts[index]
            if not isinstance(artifact, Mapping) or set(artifact) != _ARTIFACT_OUTPUT_FIELDS:
                reasons.append(f"submitted_artifact_{quantile}_fields_invalid")
                continue
            if artifact.get("quantile") != quantile:
                reasons.append("submitted_artifact_order_invalid")
            if artifact.get("format") != "onnx":
                reasons.append(f"submitted_artifact_{quantile}_format_invalid")
            artifact_hash = artifact.get("artifact_hash")
            if not _is_hash(artifact_hash):
                reasons.append(f"submitted_artifact_{quantile}_hash_invalid")
            elif artifact_hash in seen_hashes:
                reasons.append("submitted_artifact_hashes_not_distinct")
            else:
                seen_hashes.add(artifact_hash)
            size = artifact.get("artifact_size_bytes")
            if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
                reasons.append(f"submitted_artifact_{quantile}_size_invalid")
            else:
                total_artifact_bytes += size
            if artifact.get("observation_claim") != UNVERIFIED:
                reasons.append(
                    f"submitted_artifact_{quantile}_claim_invalid"
                )
            try:
                descriptor = _normalize_io_descriptor(artifact.get("io_descriptor"))
            except AlrChallengerTrainingResultContractError as exc:
                reasons.append(f"submitted_artifact_{quantile}:" + str(exc))
            else:
                expected_descriptor_hash = _domain_hash(
                    "onnx_io_descriptor",
                    {"quantile": quantile, "descriptor": descriptor},
                )
                if artifact.get("io_descriptor_hash") != expected_descriptor_hash:
                    reasons.append(
                        f"submitted_artifact_{quantile}_descriptor_hash_mismatch"
                    )

    try:
        metrics = _normalize_metrics(value.get("metrics"))
    except AlrChallengerTrainingResultContractError as exc:
        reasons.append(str(exc))
    else:
        if value.get("metrics_hash") != _domain_hash(
            "metrics_observation",
            metrics,
        ):
            reasons.append("metrics_hash_mismatch")

    resources = value.get("resource_observation")
    try:
        normalized_resources = _normalize_resources(
            resources,
            training_contract=training_contract,
            expected_inputs=expected_inputs,
            total_artifact_bytes=total_artifact_bytes,
        )
    except AlrChallengerTrainingResultContractError as exc:
        reasons.append(str(exc))
    else:
        if value.get("resource_usage_hash") != _domain_hash(
            "resource_observation",
            normalized_resources,
        ):
            reasons.append("resource_usage_hash_mismatch")
    return reasons


def _training_run_hash(
    *,
    admission: Mapping[str, Any],
    submitted: Mapping[str, Any],
) -> str:
    return _domain_hash(
        "training_run_observation",
        {
            "training_contract_hash": _required_mapping(
                admission.get("training_contract"),
                "training_contract_invalid",
            ).get("contract_hash"),
            "qualified_receipt_binding_hash": admission.get(
                "qualified_receipt_binding_hash"
            ),
            "attempt_id": submitted.get("attempt_id"),
            "trainer_spec_hash": submitted.get("trainer_spec_hash"),
            "seed": submitted.get("seed"),
            "fit_started_at": submitted.get("fit_started_at"),
            "fit_completed_at": submitted.get("fit_completed_at"),
            "model_schema_version": submitted.get("model_schema_version"),
            "execution_claim": NOT_ESTABLISHED,
        },
    )


def _challenger_hash(
    *,
    training_run_hash: str,
    model_artifact_set_hash: str,
    submitted: Mapping[str, Any],
) -> str:
    return _domain_hash(
        "challenger_observation",
        {
            "training_run_hash": training_run_hash,
            "model_artifact_set_hash": model_artifact_set_hash,
            "model_schema_version": submitted.get("model_schema_version"),
            "artifacts": copy.deepcopy(submitted.get("artifacts")),
            "execution_claim": NOT_ESTABLISHED,
        },
    )


def _artifact_hashes_from_submitted(value: Any) -> dict[str, str] | None:
    if not isinstance(value, Mapping):
        return None
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, Sequence) or isinstance(
        artifacts, (str, bytes, bytearray)
    ) or len(artifacts) != 3:
        return None
    result: dict[str, str] = {}
    for index, quantile in enumerate(_QUANTILES):
        artifact = artifacts[index]
        if not isinstance(artifact, Mapping) or artifact.get("quantile") != quantile:
            return None
        artifact_hash = artifact.get("artifact_hash")
        if not _is_hash(artifact_hash):
            return None
        result[quantile] = artifact_hash
    return result


def _model_artifact_set_hash(artifact_hashes: Mapping[str, str]) -> str:
    payload = "".join(
        f"{quantile}={artifact_hashes[quantile]}\n" for quantile in _QUANTILES
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _canonical_utc_timestamp(value: Any, reason: str) -> datetime:
    if not isinstance(value, str) or not _UTC_TIMESTAMP_RE.fullmatch(value):
        raise AlrChallengerTrainingResultContractError(reason)
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise AlrChallengerTrainingResultContractError(reason) from exc
    return parsed


def _domain_hash(domain: str, value: Any) -> str:
    prefix = (
        ALR_CHALLENGER_TRAINING_RESULT_CONTRACT_SCHEMA_VERSION
        + "\0"
        + domain
        + "\0"
    ).encode("utf-8")
    return hashlib.sha256(prefix + _canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise AlrChallengerTrainingResultContractError(
            "canonical_payload_invalid"
        ) from exc


def _required_mapping(value: Any, reason: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AlrChallengerTrainingResultContractError(reason)
    return value


def _snapshot_mapping(
    value: Any,
    *,
    not_mapping_reason: str,
    snapshot_reason: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AlrChallengerTrainingResultContractError(not_mapping_reason)
    try:
        snapshot = _bounded_snapshot(value, reason=snapshot_reason)
    except AlrChallengerTrainingResultContractError:
        raise
    except Exception as exc:
        raise AlrChallengerTrainingResultContractError(snapshot_reason) from exc
    if not isinstance(snapshot, dict):
        raise AlrChallengerTrainingResultContractError(snapshot_reason)
    return snapshot


def _bounded_snapshot(value: Any, *, reason: str) -> Any:
    remaining = [_MAX_STRUCTURE_NODES]
    active_containers: set[int] = set()

    def snapshot(current: Any, depth: int) -> Any:
        if depth > _MAX_STRUCTURE_DEPTH:
            raise AlrChallengerTrainingResultContractError(
                reason + ":depth_exceeded"
            )
        if remaining[0] <= 0:
            raise AlrChallengerTrainingResultContractError(
                reason + ":node_limit_exceeded"
            )
        remaining[0] -= 1

        if current is None or isinstance(current, (bool, int, float, str, bytes)):
            return current
        if isinstance(current, bytearray):
            return bytearray(current)
        if isinstance(current, Mapping):
            identity = id(current)
            if identity in active_containers:
                raise AlrChallengerTrainingResultContractError(
                    reason + ":circular_reference"
                )
            active_containers.add(identity)
            result: dict[Any, Any] = {}
            try:
                iterator = iter(current.items())
                while True:
                    try:
                        key, child = next(iterator)
                    except StopIteration:
                        break
                    copied_key = snapshot(key, depth + 1)
                    copied_child = snapshot(child, depth + 1)
                    try:
                        result[copied_key] = copied_child
                    except (TypeError, ValueError) as exc:
                        raise AlrChallengerTrainingResultContractError(
                            reason + ":mapping_key_invalid"
                        ) from exc
            finally:
                active_containers.remove(identity)
            return result
        if isinstance(current, Sequence) and not isinstance(
            current, (str, bytes, bytearray)
        ):
            identity = id(current)
            if identity in active_containers:
                raise AlrChallengerTrainingResultContractError(
                    reason + ":circular_reference"
                )
            active_containers.add(identity)
            result_items: list[Any] = []
            try:
                iterator = iter(current)
                while True:
                    try:
                        child = next(iterator)
                    except StopIteration:
                        break
                    result_items.append(snapshot(child, depth + 1))
            finally:
                active_containers.remove(identity)
            return tuple(result_items) if isinstance(current, tuple) else result_items
        raise AlrChallengerTrainingResultContractError(
            reason + ":unsupported_type"
        )

    return snapshot(value, 0)


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and bool(_HASH_RE.fullmatch(value))


def _same_scalar(actual: Any, expected: Any) -> bool:
    if isinstance(expected, bool):
        return actual is expected
    return actual == expected and type(actual) is type(expected)


def _canonical_equal(first: Any, second: Any) -> bool:
    try:
        return _canonical_json(first) == _canonical_json(second)
    except AlrChallengerTrainingResultContractError:
        return False


def _all_false(value: Any) -> bool:
    return isinstance(value, Mapping) and bool(value) and all(
        item is False for item in value.values()
    )


def _all_zero(value: Any) -> bool:
    return isinstance(value, Mapping) and bool(value) and all(
        isinstance(item, int) and not isinstance(item, bool) and item == 0
        for item in value.values()
    )


def _invalid(
    reason: str,
    reasons: Sequence[str] | None = None,
) -> AlrChallengerTrainingResultContractValidation:
    return AlrChallengerTrainingResultContractValidation(
        valid=False,
        verdict=INVALID,
        reason=reason,
        reasons=tuple(reasons or (reason,)),
    )


__all__ = [
    "ALR_CHALLENGER_TRAINING_RESULT_CONTRACT_SCHEMA_VERSION",
    "EXECUTION_EVIDENCE_REQUIRED",
    "INVALID",
    "NOT_ESTABLISHED",
    "OBSERVED_TRAINER_SPEC_SCHEMA_VERSION",
    "ONNX_IO_DESCRIPTOR_SCHEMA_VERSION",
    "POST_FIT_OBSERVATION_SCHEMA_VERSION",
    "UNVERIFIED",
    "AlrChallengerTrainingResultContractError",
    "AlrChallengerTrainingResultContractValidation",
    "build_alr_challenger_training_result_contract",
    "compute_alr_challenger_training_result_hash",
    "validate_alr_challenger_training_result_contract",
]
