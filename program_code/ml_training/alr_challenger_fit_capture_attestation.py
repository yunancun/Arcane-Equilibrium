"""Pure, non-persistent fit-capture attestation boundary for ALR challengers.

The serialized contract is deterministic structural evidence only.  It never
infers fit execution from caller bytes, self-digests, fixtures, or callable
identity.  A host may supply a non-serialized verifier capability, but this
module deliberately cannot establish that capability's authenticity.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ml_training.alr_challenger_training_result_contract import (
    NOT_ESTABLISHED,
    UNVERIFIED,
    validate_alr_challenger_training_result_contract,
)


ALR_CHALLENGER_FIT_CAPTURE_ATTESTATION_CONTRACT_SCHEMA_VERSION = (
    "alr_challenger_fit_capture_attestation_contract_v1"
)
FIT_CAPTURE_SCHEMA_VERSION = "alr_challenger_fit_capture_v1"
FIT_RUNNER_IDENTITY_SCHEMA_VERSION = "alr_challenger_fit_runner_identity_v1"
ACTUAL_TRAINING_INPUT_MATERIALS_SCHEMA_VERSION = (
    "alr_challenger_actual_training_input_materials_v1"
)
ACTUAL_TRAINING_INPUT_BINDING_SCHEMA_VERSION = (
    "alr_challenger_actual_training_input_binding_v1"
)

OUT_OF_BAND_FIT_ATTESTATION_REQUIRED = "OUT_OF_BAND_FIT_ATTESTATION_REQUIRED"
FIT_CAPTURE_ATTESTED_EPHEMERAL = "FIT_CAPTURE_ATTESTED_EPHEMERAL"
EXTERNAL_HOST_UNCHECKED = "EXTERNAL_HOST_UNCHECKED"
INVALID = "INVALID"

_CONTRACT_KIND = "FIT_CAPTURE_ATTESTATION_CANDIDATE"
_REASON = "out_of_band_host_fit_attestation_required"
_PRODUCER_KIND = "isolated_challenger_fit_runner"
_QUANTILES = ("q10", "q50", "q90")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_HEAD_RE = re.compile(r"^[0-9a-f]{40}$")
_IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,127}$")
_VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z_.+-]{0,63}$")
_UTC_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$"
)
_MAX_STRUCTURE_DEPTH = 64
_MAX_STRUCTURE_NODES = 50_000
_MAX_SINGLE_MATERIAL_BYTES = 268_435_456
_MAX_TOTAL_MATERIAL_BYTES = 536_870_912

_CONTRACT_FIELDS = {
    "schema_version",
    "contract_kind",
    "status",
    "reason",
    "execution_claim",
    "model_training_performed_claim",
    "persistence_allowed",
    "verifier_authenticity_claim",
    "result_contract",
    "result_hash",
    "fit_capture",
    "fit_capture_hash",
    "evidence_obligations",
    "no_authority",
    "authority_counters",
    "attestation_hash",
}
_FIT_CAPTURE_INPUT_FIELDS = {
    "schema_version",
    "runner_identity",
    "actual_training_inputs",
    "attempt_id",
    "trainer_spec",
    "seed",
    "fit_started_at",
    "fit_completed_at",
    "model_schema_version",
    "artifact_readback",
}
_FIT_CAPTURE_OUTPUT_FIELDS = {
    "schema_version",
    "capture_claim",
    "runner_identity",
    "actual_training_inputs",
    "attempt_id",
    "trainer_spec",
    "seed",
    "fit_started_at",
    "fit_completed_at",
    "model_schema_version",
    "artifact_readback",
    "model_artifact_set_hash",
}
_RUNNER_MATERIAL_FIELDS = (
    "runner_source_material",
    "host_identity_material",
    "environment_identity_material",
    "process_identity_material",
)
_RUNNER_INPUT_FIELDS = {
    "schema_version",
    "producer_kind",
    "producer_id",
    "runner_version",
    *_RUNNER_MATERIAL_FIELDS,
    "invocation_id",
    "captured_at",
}
_RUNNER_OUTPUT_FIELDS = {
    "schema_version",
    "identity_claim",
    "producer_kind",
    "producer_id",
    "runner_version",
    "runner_source_hash",
    "host_identity_hash",
    "environment_identity_hash",
    "process_identity_hash",
    "invocation_id",
    "captured_at",
    "material_sizes",
    "total_material_bytes",
    "runner_identity_hash",
}
_ACTUAL_MATERIAL_FIELDS = (
    "source_head_material",
    "input_lineage_material",
    "dataset_material",
    "row_ids_material",
    "split_material",
    "code_manifest_material",
    "training_config_material",
    "feature_schema_material",
    "label_schema_material",
)
_ACTUAL_INPUT_FIELDS = {
    "schema_version",
    *_ACTUAL_MATERIAL_FIELDS,
    "training_rows",
}
_ACTUAL_OUTPUT_FIELDS = {
    "schema_version",
    "material_claim",
    "source_head",
    "training_input_hash",
    "actual_dataset_hash",
    "actual_row_ids_hash",
    "actual_split_hash",
    "actual_code_manifest_hash",
    "actual_training_config_hash",
    "actual_feature_schema_hash",
    "actual_label_schema_hash",
    "actual_training_rows",
    "material_sizes",
    "total_material_bytes",
    "material_set_hash",
}
_ARTIFACT_INPUT_FIELDS = {"format", "readback_bytes", "io_descriptor"}
_ARTIFACT_OUTPUT_FIELDS = {
    "quantile",
    "format",
    "artifact_hash",
    "artifact_size_bytes",
    "io_descriptor",
    "io_descriptor_hash",
    "readback_claim",
}
_EVIDENCE_OBLIGATIONS = {
    "out_of_band_verifier_authenticity_required": True,
    "verifier_time_bound_external_required": True,
    "durable_attestation_schema_required": True,
    "trusted_filesystem_readback_required": True,
    "onnx_semantic_validation_required": True,
    "v158_result_writer_binding_required": True,
    "durable_result_readback_required": True,
    "registry_readback_required": True,
}


FitCaptureAttestationVerifier = Callable[[str, str, bytes], bool]


@dataclass(frozen=True)
class AlrChallengerFitCaptureAttestationValidation:
    valid: bool
    verdict: str
    reason: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class AlrChallengerFitCaptureVerification:
    valid: bool
    verifier_accepted: bool
    verdict: str
    reason: str
    reasons: tuple[str, ...]
    attestation_hash: str | None
    capability_authenticity: str
    fit_capture_evidence_bound: bool
    execution_claim: str
    model_training_performed_claim: str
    persistence_allowed: bool
    authority_granted: bool


class AlrChallengerFitCaptureAttestationError(ValueError):
    """A raw fit capture cannot form the bounded structural contract."""


def build_alr_challenger_fit_capture_attestation_contract(
    result_contract: Mapping[str, Any],
    *,
    fit_capture: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a deterministic candidate for out-of-band host verification."""

    result_snapshot = _validated_result_snapshot(result_contract)
    capture_snapshot = _snapshot_mapping(
        fit_capture,
        not_mapping_reason="fit_capture_not_mapping",
        snapshot_reason="fit_capture_snapshot_invalid",
    )
    normalized_capture = _normalize_fit_capture(
        capture_snapshot,
        result_contract=result_snapshot,
    )
    contract: dict[str, Any] = {
        "schema_version": (
            ALR_CHALLENGER_FIT_CAPTURE_ATTESTATION_CONTRACT_SCHEMA_VERSION
        ),
        "contract_kind": _CONTRACT_KIND,
        "status": OUT_OF_BAND_FIT_ATTESTATION_REQUIRED,
        "reason": _REASON,
        "execution_claim": NOT_ESTABLISHED,
        "model_training_performed_claim": NOT_ESTABLISHED,
        "persistence_allowed": False,
        "verifier_authenticity_claim": NOT_ESTABLISHED,
        "result_contract": result_snapshot,
        "result_hash": result_snapshot["result_hash"],
        "fit_capture": normalized_capture,
        "fit_capture_hash": _domain_hash("fit_capture", normalized_capture),
        "evidence_obligations": dict(_EVIDENCE_OBLIGATIONS),
        "no_authority": _bounded_snapshot(
            result_snapshot["no_authority"], reason="no_authority_snapshot_invalid"
        ),
        "authority_counters": _bounded_snapshot(
            result_snapshot["authority_counters"],
            reason="authority_counters_snapshot_invalid",
        ),
    }
    contract["attestation_hash"] = (
        compute_alr_challenger_fit_capture_attestation_hash(contract)
    )
    validation = validate_alr_challenger_fit_capture_attestation_contract(contract)
    if not validation.valid:
        raise AlrChallengerFitCaptureAttestationError(validation.reason)
    return contract


def compute_alr_challenger_fit_capture_attestation_hash(
    contract: Mapping[str, Any],
) -> str:
    """Compute the structural candidate identity, never execution proof."""

    snapshot = _snapshot_mapping(
        contract,
        not_mapping_reason="attestation_contract_not_mapping",
        snapshot_reason="attestation_contract_snapshot_invalid",
    )
    snapshot.pop("attestation_hash", None)
    return _domain_hash("fit_capture_attestation", snapshot)


def validate_alr_challenger_fit_capture_attestation_contract(
    contract: Any,
) -> AlrChallengerFitCaptureAttestationValidation:
    """Validate the serialized structure without upgrading its evidence class."""

    try:
        return _validate_alr_challenger_fit_capture_attestation_contract(contract)
    except Exception as exc:
        return _invalid("attestation_validation_failed:" + type(exc).__name__)


def verify_alr_challenger_fit_capture_attestation(
    contract: Any,
    *,
    out_of_band_verifier: FitCaptureAttestationVerifier | None,
) -> AlrChallengerFitCaptureVerification:
    """Ask one host capability about immutable bytes; return ephemeral state.

    Structural validation is total over bounded data.  Liveness and authenticity
    of arbitrary executable verifier code remain responsibilities of the host.
    """

    try:
        before = _snapshot_mapping(
            contract,
            not_mapping_reason="attestation_contract_not_mapping",
            snapshot_reason="attestation_contract_snapshot_invalid",
        )
    except AlrChallengerFitCaptureAttestationError as exc:
        return _verification_invalid(str(exc))
    validation = validate_alr_challenger_fit_capture_attestation_contract(before)
    if not validation.valid:
        return _verification_invalid(validation.reason, validation.reasons)

    canonical_bytes = _canonical_json(before).encode("utf-8")
    attestation_hash = before["attestation_hash"]
    if out_of_band_verifier is None:
        return _verification_required(
            attestation_hash,
            "out_of_band_verifier_missing",
        )
    try:
        outcome = out_of_band_verifier(
            ALR_CHALLENGER_FIT_CAPTURE_ATTESTATION_CONTRACT_SCHEMA_VERSION,
            attestation_hash,
            canonical_bytes,
        )
    except Exception as exc:
        return _verification_required(
            attestation_hash,
            "out_of_band_verifier_exception:" + type(exc).__name__,
        )

    try:
        after = _snapshot_mapping(
            contract,
            not_mapping_reason="attestation_contract_not_mapping",
            snapshot_reason="attestation_contract_snapshot_invalid",
        )
        after_bytes = _canonical_json(after).encode("utf-8")
    except (AlrChallengerFitCaptureAttestationError, TypeError, ValueError):
        return _verification_required(
            attestation_hash,
            "attestation_contract_mutated_during_verification",
        )
    if after_bytes != canonical_bytes or (
        compute_alr_challenger_fit_capture_attestation_hash(before)
        != attestation_hash
    ):
        return _verification_required(
            attestation_hash,
            "attestation_contract_mutated_during_verification",
        )
    if outcome is not True:
        return _verification_required(
            attestation_hash,
            "out_of_band_verifier_did_not_return_literal_true",
        )
    return AlrChallengerFitCaptureVerification(
        valid=True,
        verifier_accepted=True,
        verdict=FIT_CAPTURE_ATTESTED_EPHEMERAL,
        reason="out_of_band_verifier_accepted_ephemeral_only",
        reasons=(),
        attestation_hash=attestation_hash,
        capability_authenticity=EXTERNAL_HOST_UNCHECKED,
        fit_capture_evidence_bound=True,
        execution_claim=NOT_ESTABLISHED,
        model_training_performed_claim=NOT_ESTABLISHED,
        persistence_allowed=False,
        authority_granted=False,
    )


def _validated_result_snapshot(value: Any) -> dict[str, Any]:
    snapshot = _snapshot_mapping(
        value,
        not_mapping_reason="result_contract_not_mapping",
        snapshot_reason="result_contract_snapshot_invalid",
    )
    validation = validate_alr_challenger_training_result_contract(snapshot)
    if not validation.valid:
        raise AlrChallengerFitCaptureAttestationError(
            "result_contract_invalid:" + validation.reason
        )
    return snapshot


def _normalize_fit_capture(
    value: Mapping[str, Any],
    *,
    result_contract: Mapping[str, Any],
) -> dict[str, Any]:
    if set(value) != _FIT_CAPTURE_INPUT_FIELDS:
        raise AlrChallengerFitCaptureAttestationError(
            "fit_capture_fields_invalid"
        )
    if value.get("schema_version") != FIT_CAPTURE_SCHEMA_VERSION:
        raise AlrChallengerFitCaptureAttestationError(
            "fit_capture_schema_version_invalid"
        )
    submitted = _required_mapping(
        result_contract.get("submitted_observation"),
        "result_submitted_observation_invalid",
    )
    for field in (
        "attempt_id",
        "trainer_spec",
        "seed",
        "fit_started_at",
        "fit_completed_at",
        "model_schema_version",
    ):
        if not _typed_equal(value.get(field), submitted.get(field)):
            raise AlrChallengerFitCaptureAttestationError(
                "fit_capture_" + field + "_mismatch"
            )
    completed = _canonical_utc_timestamp(
        value.get("fit_completed_at"),
        "fit_capture_completed_at_invalid",
    )
    actual_inputs = _normalize_actual_training_inputs(
        value.get("actual_training_inputs"),
        result_contract=result_contract,
    )
    runner = _normalize_runner_identity(
        value.get("runner_identity"),
        attempt_id=str(submitted["attempt_id"]),
        fit_completed_at=completed,
    )
    artifacts, model_set_hash = _normalize_artifact_readback(
        value.get("artifact_readback"),
        result_contract=result_contract,
    )
    return {
        "schema_version": FIT_CAPTURE_SCHEMA_VERSION,
        "capture_claim": UNVERIFIED,
        "runner_identity": runner,
        "actual_training_inputs": actual_inputs,
        "attempt_id": submitted["attempt_id"],
        "trainer_spec": _bounded_snapshot(
            submitted["trainer_spec"], reason="trainer_spec_snapshot_invalid"
        ),
        "seed": submitted["seed"],
        "fit_started_at": submitted["fit_started_at"],
        "fit_completed_at": submitted["fit_completed_at"],
        "model_schema_version": submitted["model_schema_version"],
        "artifact_readback": artifacts,
        "model_artifact_set_hash": model_set_hash,
    }


def _normalize_actual_training_inputs(
    value: Any,
    *,
    result_contract: Mapping[str, Any],
) -> dict[str, Any]:
    materials = _required_mapping(value, "actual_training_inputs_not_mapping")
    if set(materials) != _ACTUAL_INPUT_FIELDS:
        raise AlrChallengerFitCaptureAttestationError(
            "actual_training_input_fields_invalid"
        )
    if materials.get("schema_version") != (
        ACTUAL_TRAINING_INPUT_MATERIALS_SCHEMA_VERSION
    ):
        raise AlrChallengerFitCaptureAttestationError(
            "actual_training_input_schema_version_invalid"
        )
    sizes = _material_sizes(materials, _ACTUAL_MATERIAL_FIELDS)
    total = sum(sizes.values())
    if total > _MAX_TOTAL_MATERIAL_BYTES:
        raise AlrChallengerFitCaptureAttestationError(
            "actual_training_input_material_total_exceeded"
        )

    admission = _required_mapping(
        result_contract.get("admission"), "result_admission_invalid"
    )
    training_contract = _required_mapping(
        admission.get("training_contract"), "training_contract_invalid"
    )
    expected = _required_mapping(
        result_contract.get("expected_training_inputs"),
        "expected_training_inputs_invalid",
    )
    source_head = bytes(materials["source_head_material"]).hex()
    if source_head != expected.get("source_head"):
        raise AlrChallengerFitCaptureAttestationError(
            "actual_source_head_mismatch"
        )

    lineage = _required_mapping(
        training_contract.get("input_lineage"), "training_input_lineage_invalid"
    )
    expected_lineage_bytes = _canonical_json(lineage).encode("utf-8")
    if materials["input_lineage_material"] != expected_lineage_bytes:
        raise AlrChallengerFitCaptureAttestationError(
            "actual_input_lineage_material_mismatch"
        )
    training_input_hash = _sha256(materials["input_lineage_material"])
    if training_input_hash != training_contract.get("training_input_hash"):
        raise AlrChallengerFitCaptureAttestationError(
            "actual_training_input_hash_mismatch"
        )

    code = dict(
        _required_mapping(training_contract.get("code_manifest"), "code_invalid")
    )
    code.pop("code_manifest_hash", None)
    config = dict(
        _required_mapping(
            training_contract.get("training_config"), "training_config_invalid"
        )
    )
    config.pop("training_config_hash", None)
    # LR1(S2.2A):finalize 綁定。先以「具名」方式綁定 attested code_manifest 的
    # learning_runtime_digest 對上 spawn 契約值——放在下方泛化的 code_manifest_material
    # 逐位元比對之前,讓 learning_runtime_digest 漂移得到專屬錯誤碼而非被泛用碼吸收。
    # (完整的位元一致仍由下方 actual_code_manifest_material_mismatch 兜底。)
    attested_code_manifest: Any = None
    try:
        parsed_code_manifest = json.loads(bytes(materials["code_manifest_material"]))
    except (TypeError, ValueError):
        parsed_code_manifest = None
    if isinstance(parsed_code_manifest, dict):
        attested_code_manifest = parsed_code_manifest
    if attested_code_manifest is not None and (
        attested_code_manifest.get("learning_runtime_digest")
        != code.get("learning_runtime_digest")
    ):
        raise AlrChallengerFitCaptureAttestationError(
            "actual_learning_runtime_digest_mismatch"
        )
    if materials["code_manifest_material"] != _canonical_json(code).encode("utf-8"):
        raise AlrChallengerFitCaptureAttestationError(
            "actual_code_manifest_material_mismatch"
        )
    if materials["training_config_material"] != _canonical_json(config).encode(
        "utf-8"
    ):
        raise AlrChallengerFitCaptureAttestationError(
            "actual_training_config_material_mismatch"
        )

    derived = {
        "actual_dataset_hash": _sha256(materials["dataset_material"]),
        "actual_row_ids_hash": _sha256(materials["row_ids_material"]),
        "actual_split_hash": _sha256(materials["split_material"]),
        "actual_code_manifest_hash": _sha256(
            materials["code_manifest_material"]
        ),
        "actual_training_config_hash": _sha256(
            materials["training_config_material"]
        ),
        "actual_feature_schema_hash": _sha256(
            materials["feature_schema_material"]
        ),
        "actual_label_schema_hash": _sha256(
            materials["label_schema_material"]
        ),
    }
    expected_fields = {
        "actual_dataset_hash": "dataset_hash",
        "actual_row_ids_hash": "row_ids_hash",
        "actual_split_hash": "split_hash",
        "actual_code_manifest_hash": "code_manifest_hash",
        "actual_training_config_hash": "training_config_hash",
        "actual_feature_schema_hash": "feature_schema_hash",
        "actual_label_schema_hash": "label_schema_hash",
    }
    for actual_field, expected_field in expected_fields.items():
        if derived[actual_field] != expected.get(expected_field):
            raise AlrChallengerFitCaptureAttestationError(
                actual_field + "_mismatch"
            )
    training_rows = materials.get("training_rows")
    if (
        isinstance(training_rows, bool)
        or not isinstance(training_rows, int)
        or training_rows <= 0
        or training_rows != expected.get("training_rows")
    ):
        raise AlrChallengerFitCaptureAttestationError(
            "actual_training_rows_mismatch"
        )
    output: dict[str, Any] = {
        "schema_version": ACTUAL_TRAINING_INPUT_BINDING_SCHEMA_VERSION,
        "material_claim": UNVERIFIED,
        "source_head": source_head,
        "training_input_hash": training_input_hash,
        **derived,
        "actual_training_rows": training_rows,
        "material_sizes": sizes,
        "total_material_bytes": total,
    }
    output["material_set_hash"] = _domain_hash(
        "actual_training_input_material_set", output
    )
    return output


def _normalize_runner_identity(
    value: Any,
    *,
    attempt_id: str,
    fit_completed_at: datetime,
) -> dict[str, Any]:
    runner = _required_mapping(value, "runner_identity_not_mapping")
    if set(runner) != _RUNNER_INPUT_FIELDS:
        raise AlrChallengerFitCaptureAttestationError(
            "runner_identity_fields_invalid"
        )
    if runner.get("schema_version") != FIT_RUNNER_IDENTITY_SCHEMA_VERSION:
        raise AlrChallengerFitCaptureAttestationError(
            "runner_identity_schema_version_invalid"
        )
    if runner.get("producer_kind") != _PRODUCER_KIND:
        raise AlrChallengerFitCaptureAttestationError(
            "runner_producer_kind_invalid"
        )
    producer_id = runner.get("producer_id")
    if not isinstance(producer_id, str) or not _IDENTIFIER_RE.fullmatch(
        producer_id
    ):
        raise AlrChallengerFitCaptureAttestationError("runner_producer_id_invalid")
    runner_version = runner.get("runner_version")
    if not isinstance(runner_version, str) or not _VERSION_RE.fullmatch(
        runner_version
    ):
        raise AlrChallengerFitCaptureAttestationError(
            "runner_version_invalid"
        )
    if runner.get("invocation_id") != attempt_id:
        raise AlrChallengerFitCaptureAttestationError(
            "runner_invocation_id_mismatch"
        )
    captured_at = _canonical_utc_timestamp(
        runner.get("captured_at"), "runner_captured_at_invalid"
    )
    if captured_at < fit_completed_at:
        raise AlrChallengerFitCaptureAttestationError(
            "runner_capture_before_fit_completed"
        )
    sizes = _material_sizes(runner, _RUNNER_MATERIAL_FIELDS)
    total = sum(sizes.values())
    if total > _MAX_TOTAL_MATERIAL_BYTES:
        raise AlrChallengerFitCaptureAttestationError(
            "runner_identity_material_total_exceeded"
        )
    output: dict[str, Any] = {
        "schema_version": FIT_RUNNER_IDENTITY_SCHEMA_VERSION,
        "identity_claim": UNVERIFIED,
        "producer_kind": _PRODUCER_KIND,
        "producer_id": producer_id,
        "runner_version": runner_version,
        "runner_source_hash": _sha256(runner["runner_source_material"]),
        "host_identity_hash": _sha256(runner["host_identity_material"]),
        "environment_identity_hash": _sha256(
            runner["environment_identity_material"]
        ),
        "process_identity_hash": _sha256(runner["process_identity_material"]),
        "invocation_id": attempt_id,
        "captured_at": runner["captured_at"],
        "material_sizes": sizes,
        "total_material_bytes": total,
    }
    output["runner_identity_hash"] = _domain_hash("runner_identity", output)
    return output


def _normalize_artifact_readback(
    value: Any,
    *,
    result_contract: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    readback = _required_mapping(value, "artifact_readback_not_mapping")
    if set(readback) != set(_QUANTILES):
        raise AlrChallengerFitCaptureAttestationError(
            "artifact_readback_quantiles_invalid"
        )
    submitted = _required_mapping(
        result_contract.get("submitted_observation"),
        "result_submitted_observation_invalid",
    )
    expected_artifacts = submitted.get("artifacts")
    if not isinstance(expected_artifacts, Sequence) or len(expected_artifacts) != 3:
        raise AlrChallengerFitCaptureAttestationError(
            "result_artifacts_invalid"
        )
    output: list[dict[str, Any]] = []
    hashes: dict[str, str] = {}
    total_bytes = 0
    for index, quantile in enumerate(_QUANTILES):
        raw = _required_mapping(
            readback.get(quantile), f"artifact_{quantile}_not_mapping"
        )
        if set(raw) != _ARTIFACT_INPUT_FIELDS:
            raise AlrChallengerFitCaptureAttestationError(
                f"artifact_{quantile}_fields_invalid"
            )
        expected = _required_mapping(
            expected_artifacts[index], f"result_artifact_{quantile}_invalid"
        )
        if raw.get("format") != "onnx" or raw.get("format") != expected.get(
            "format"
        ):
            raise AlrChallengerFitCaptureAttestationError(
                f"artifact_{quantile}_format_mismatch"
            )
        model_bytes = raw.get("readback_bytes")
        _require_material_bytes(model_bytes, f"artifact_{quantile}_readback")
        artifact_hash = _sha256(model_bytes)
        size = len(model_bytes)
        if artifact_hash != expected.get("artifact_hash"):
            raise AlrChallengerFitCaptureAttestationError(
                f"artifact_{quantile}_hash_mismatch"
            )
        if size != expected.get("artifact_size_bytes"):
            raise AlrChallengerFitCaptureAttestationError(
                f"artifact_{quantile}_size_mismatch"
            )
        descriptor = raw.get("io_descriptor")
        if not _typed_equal(descriptor, expected.get("io_descriptor")):
            raise AlrChallengerFitCaptureAttestationError(
                f"artifact_{quantile}_descriptor_mismatch"
            )
        hashes[quantile] = artifact_hash
        total_bytes += size
        output.append(
            {
                "quantile": quantile,
                "format": "onnx",
                "artifact_hash": artifact_hash,
                "artifact_size_bytes": size,
                "io_descriptor": _bounded_snapshot(
                    descriptor, reason="io_descriptor_snapshot_invalid"
                ),
                "io_descriptor_hash": expected["io_descriptor_hash"],
                "readback_claim": UNVERIFIED,
            }
        )
    resource = _required_mapping(
        submitted.get("resource_observation"), "result_resource_observation_invalid"
    )
    if total_bytes != resource.get("total_artifact_bytes"):
        raise AlrChallengerFitCaptureAttestationError(
            "artifact_readback_total_bytes_mismatch"
        )
    model_set_hash = _model_artifact_set_hash(hashes)
    if model_set_hash != result_contract.get("model_artifact_set_hash"):
        raise AlrChallengerFitCaptureAttestationError(
            "artifact_readback_set_hash_mismatch"
        )
    return output, model_set_hash


def _validate_alr_challenger_fit_capture_attestation_contract(
    contract: Any,
) -> AlrChallengerFitCaptureAttestationValidation:
    snapshot = _snapshot_mapping(
        contract,
        not_mapping_reason="attestation_contract_not_mapping",
        snapshot_reason="attestation_contract_snapshot_invalid",
    )
    reasons: list[str] = []
    if set(snapshot) != _CONTRACT_FIELDS:
        reasons.append("attestation_contract_fields_invalid")
    fixed = {
        "schema_version": (
            ALR_CHALLENGER_FIT_CAPTURE_ATTESTATION_CONTRACT_SCHEMA_VERSION
        ),
        "contract_kind": _CONTRACT_KIND,
        "status": OUT_OF_BAND_FIT_ATTESTATION_REQUIRED,
        "reason": _REASON,
        "execution_claim": NOT_ESTABLISHED,
        "model_training_performed_claim": NOT_ESTABLISHED,
        "persistence_allowed": False,
        "verifier_authenticity_claim": NOT_ESTABLISHED,
    }
    for field, expected in fixed.items():
        if not _same_scalar(snapshot.get(field), expected):
            reasons.append(field + "_invalid")

    result = snapshot.get("result_contract")
    result_validation = validate_alr_challenger_training_result_contract(result)
    if not result_validation.valid:
        reasons.append("result_contract_invalid:" + result_validation.reason)
        result_mapping: Mapping[str, Any] | None = None
    else:
        result_mapping = _required_mapping(result, "result_contract_invalid")
        if snapshot.get("result_hash") != result_mapping.get("result_hash"):
            reasons.append("result_hash_mismatch")

    fit_capture = snapshot.get("fit_capture")
    if result_mapping is None:
        reasons.append("fit_capture_unverifiable")
    else:
        reasons.extend(
            _normalized_fit_capture_reasons(
                fit_capture,
                result_contract=result_mapping,
            )
        )
        if isinstance(fit_capture, Mapping):
            expected_capture_hash = _domain_hash("fit_capture", fit_capture)
            if snapshot.get("fit_capture_hash") != expected_capture_hash:
                reasons.append("fit_capture_hash_mismatch")
        else:
            reasons.append("fit_capture_hash_unverifiable")
        if not _typed_equal(snapshot.get("no_authority"), result_mapping.get("no_authority")):
            reasons.append("no_authority_mismatch")
        if not _typed_equal(
            snapshot.get("authority_counters"),
            result_mapping.get("authority_counters"),
        ):
            reasons.append("authority_counters_mismatch")

    if not _typed_equal(
        snapshot.get("evidence_obligations"), _EVIDENCE_OBLIGATIONS
    ):
        reasons.append("evidence_obligations_invalid")
    if not _all_false(snapshot.get("no_authority")):
        reasons.append("no_authority_invalid")
    if not _all_zero(snapshot.get("authority_counters")):
        reasons.append("authority_counters_invalid")
    if _is_hash(snapshot.get("attestation_hash")):
        try:
            expected_hash = compute_alr_challenger_fit_capture_attestation_hash(
                snapshot
            )
        except AlrChallengerFitCaptureAttestationError:
            reasons.append("attestation_hash_uncomputable")
        else:
            if snapshot.get("attestation_hash") != expected_hash:
                reasons.append("attestation_hash_mismatch")
    else:
        reasons.append("attestation_hash_invalid")
    if reasons:
        return _invalid(reasons[0], reasons)
    return AlrChallengerFitCaptureAttestationValidation(
        valid=True,
        verdict=OUT_OF_BAND_FIT_ATTESTATION_REQUIRED,
        reason=_REASON,
        reasons=(),
    )


def _normalized_fit_capture_reasons(
    value: Any,
    *,
    result_contract: Mapping[str, Any],
) -> list[str]:
    if not isinstance(value, Mapping) or set(value) != _FIT_CAPTURE_OUTPUT_FIELDS:
        return ["normalized_fit_capture_fields_invalid"]
    reasons: list[str] = []
    if value.get("schema_version") != FIT_CAPTURE_SCHEMA_VERSION:
        reasons.append("normalized_fit_capture_schema_invalid")
    if value.get("capture_claim") != UNVERIFIED:
        reasons.append("normalized_fit_capture_claim_invalid")
    submitted = _required_mapping(
        result_contract.get("submitted_observation"),
        "result_submitted_observation_invalid",
    )
    for field in (
        "attempt_id",
        "trainer_spec",
        "seed",
        "fit_started_at",
        "fit_completed_at",
        "model_schema_version",
    ):
        if not _typed_equal(value.get(field), submitted.get(field)):
            reasons.append("normalized_fit_capture_" + field + "_mismatch")
    reasons.extend(_runner_output_reasons(value.get("runner_identity"), submitted))
    reasons.extend(
        _actual_input_output_reasons(
            value.get("actual_training_inputs"),
            result_contract=result_contract,
        )
    )
    expected_artifacts = submitted.get("artifacts")
    artifacts = value.get("artifact_readback")
    if (
        not isinstance(artifacts, Sequence)
        or isinstance(artifacts, (str, bytes, bytearray))
        or len(artifacts) != 3
        or not isinstance(expected_artifacts, Sequence)
        or len(expected_artifacts) != 3
    ):
        reasons.append("normalized_artifact_readback_invalid")
    else:
        hashes: dict[str, str] = {}
        for index, quantile in enumerate(_QUANTILES):
            artifact = artifacts[index]
            expected = expected_artifacts[index]
            if not isinstance(artifact, Mapping) or set(artifact) != _ARTIFACT_OUTPUT_FIELDS:
                reasons.append(f"normalized_artifact_{quantile}_fields_invalid")
                continue
            if artifact.get("quantile") != quantile:
                reasons.append("normalized_artifact_order_invalid")
            if artifact.get("readback_claim") != UNVERIFIED:
                reasons.append(f"normalized_artifact_{quantile}_claim_invalid")
            for field in (
                "format",
                "artifact_hash",
                "artifact_size_bytes",
                "io_descriptor",
                "io_descriptor_hash",
            ):
                if not _typed_equal(artifact.get(field), expected.get(field)):
                    reasons.append(
                        f"normalized_artifact_{quantile}_{field}_mismatch"
                    )
            if _is_hash(artifact.get("artifact_hash")):
                hashes[quantile] = artifact["artifact_hash"]
        if len(hashes) == 3:
            set_hash = _model_artifact_set_hash(hashes)
            if value.get("model_artifact_set_hash") != set_hash:
                reasons.append("normalized_model_artifact_set_hash_mismatch")
            if set_hash != result_contract.get("model_artifact_set_hash"):
                reasons.append("result_model_artifact_set_hash_mismatch")
    return reasons


def _runner_output_reasons(value: Any, submitted: Mapping[str, Any]) -> list[str]:
    if not isinstance(value, Mapping) or set(value) != _RUNNER_OUTPUT_FIELDS:
        return ["normalized_runner_identity_fields_invalid"]
    reasons: list[str] = []
    fixed = {
        "schema_version": FIT_RUNNER_IDENTITY_SCHEMA_VERSION,
        "identity_claim": UNVERIFIED,
        "producer_kind": _PRODUCER_KIND,
        "invocation_id": submitted.get("attempt_id"),
    }
    for field, expected in fixed.items():
        if not _same_scalar(value.get(field), expected):
            reasons.append("normalized_runner_" + field + "_invalid")
    for field in (
        "runner_source_hash",
        "host_identity_hash",
        "environment_identity_hash",
        "process_identity_hash",
        "runner_identity_hash",
    ):
        if not _is_hash(value.get(field)):
            reasons.append("normalized_runner_" + field + "_invalid")
    producer_id = value.get("producer_id")
    if not isinstance(producer_id, str) or not _IDENTIFIER_RE.fullmatch(
        producer_id
    ):
        reasons.append("normalized_runner_producer_id_invalid")
    runner_version = value.get("runner_version")
    if not isinstance(runner_version, str) or not _VERSION_RE.fullmatch(
        runner_version
    ):
        reasons.append("normalized_runner_version_invalid")
    sizes = value.get("material_sizes")
    total_material_bytes = value.get("total_material_bytes")
    if not _sizes_valid(sizes, _RUNNER_MATERIAL_FIELDS):
        reasons.append("normalized_runner_material_sizes_invalid")
    elif (
        isinstance(total_material_bytes, bool)
        or not isinstance(total_material_bytes, int)
    ):
        reasons.append("normalized_runner_total_material_bytes_invalid")
    elif total_material_bytes != sum(sizes.values()):
        reasons.append("normalized_runner_total_material_bytes_invalid")
    elif total_material_bytes > _MAX_TOTAL_MATERIAL_BYTES:
        reasons.append("normalized_runner_total_material_bytes_exceeded")
    try:
        captured = _canonical_utc_timestamp(
            value.get("captured_at"), "normalized_runner_captured_at_invalid"
        )
        completed = _canonical_utc_timestamp(
            submitted.get("fit_completed_at"), "result_completed_at_invalid"
        )
        if captured < completed:
            reasons.append("normalized_runner_capture_before_completed")
    except AlrChallengerFitCaptureAttestationError as exc:
        reasons.append(str(exc))
    unsigned = dict(value)
    claimed = unsigned.pop("runner_identity_hash", None)
    if claimed != _domain_hash("runner_identity", unsigned):
        reasons.append("normalized_runner_identity_hash_mismatch")
    return reasons


def _actual_input_output_reasons(
    value: Any,
    *,
    result_contract: Mapping[str, Any],
) -> list[str]:
    if not isinstance(value, Mapping) or set(value) != _ACTUAL_OUTPUT_FIELDS:
        return ["normalized_actual_training_input_fields_invalid"]
    reasons: list[str] = []
    if value.get("schema_version") != ACTUAL_TRAINING_INPUT_BINDING_SCHEMA_VERSION:
        reasons.append("normalized_actual_training_input_schema_invalid")
    if value.get("material_claim") != UNVERIFIED:
        reasons.append("normalized_actual_training_input_claim_invalid")
    expected = _required_mapping(
        result_contract.get("expected_training_inputs"),
        "expected_training_inputs_invalid",
    )
    admission = _required_mapping(
        result_contract.get("admission"), "result_admission_invalid"
    )
    training_contract = _required_mapping(
        admission.get("training_contract"), "training_contract_invalid"
    )
    expected_fields = {
        "source_head": expected.get("source_head"),
        "training_input_hash": training_contract.get("training_input_hash"),
        "actual_dataset_hash": expected.get("dataset_hash"),
        "actual_row_ids_hash": expected.get("row_ids_hash"),
        "actual_split_hash": expected.get("split_hash"),
        "actual_code_manifest_hash": expected.get("code_manifest_hash"),
        "actual_training_config_hash": expected.get("training_config_hash"),
        "actual_feature_schema_hash": expected.get("feature_schema_hash"),
        "actual_label_schema_hash": expected.get("label_schema_hash"),
        "actual_training_rows": expected.get("training_rows"),
    }
    for field, expected_value in expected_fields.items():
        if not _same_scalar(value.get(field), expected_value):
            reasons.append("normalized_" + field + "_mismatch")
    sizes = value.get("material_sizes")
    total_material_bytes = value.get("total_material_bytes")
    if not _sizes_valid(sizes, _ACTUAL_MATERIAL_FIELDS):
        reasons.append("normalized_actual_material_sizes_invalid")
    elif (
        isinstance(total_material_bytes, bool)
        or not isinstance(total_material_bytes, int)
    ):
        reasons.append("normalized_actual_total_material_bytes_invalid")
    elif total_material_bytes != sum(sizes.values()):
        reasons.append("normalized_actual_total_material_bytes_invalid")
    elif total_material_bytes > _MAX_TOTAL_MATERIAL_BYTES:
        reasons.append("normalized_actual_total_material_bytes_exceeded")
    unsigned = dict(value)
    claimed = unsigned.pop("material_set_hash", None)
    if claimed != _domain_hash("actual_training_input_material_set", unsigned):
        reasons.append("normalized_actual_material_set_hash_mismatch")
    return reasons


def _material_sizes(
    value: Mapping[str, Any], fields: Sequence[str]
) -> dict[str, int]:
    sizes: dict[str, int] = {}
    for field in fields:
        item = value.get(field)
        _require_material_bytes(item, field)
        sizes[field] = len(item)
    return sizes


def _require_material_bytes(value: Any, field: str) -> None:
    if type(value) is not bytes or not value:
        raise AlrChallengerFitCaptureAttestationError(
            field + "_bytes_invalid"
        )
    if len(value) > _MAX_SINGLE_MATERIAL_BYTES:
        raise AlrChallengerFitCaptureAttestationError(
            field + "_bytes_limit_exceeded"
        )


def _sizes_valid(value: Any, fields: Sequence[str]) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == set(fields)
        and all(
            isinstance(item, int)
            and not isinstance(item, bool)
            and 0 < item <= _MAX_SINGLE_MATERIAL_BYTES
            for item in value.values()
        )
    )


def _model_artifact_set_hash(hashes: Mapping[str, str]) -> str:
    payload = "".join(
        f"{quantile}={hashes[quantile]}\n" for quantile in _QUANTILES
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _canonical_utc_timestamp(value: Any, reason: str) -> datetime:
    if not isinstance(value, str) or not _UTC_TIMESTAMP_RE.fullmatch(value):
        raise AlrChallengerFitCaptureAttestationError(reason)
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise AlrChallengerFitCaptureAttestationError(reason) from exc


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _domain_hash(domain: str, value: Any) -> str:
    prefix = (
        ALR_CHALLENGER_FIT_CAPTURE_ATTESTATION_CONTRACT_SCHEMA_VERSION
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
        raise AlrChallengerFitCaptureAttestationError(
            "canonical_payload_invalid"
        ) from exc


def _required_mapping(value: Any, reason: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AlrChallengerFitCaptureAttestationError(reason)
    return value


def _snapshot_mapping(
    value: Any,
    *,
    not_mapping_reason: str,
    snapshot_reason: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AlrChallengerFitCaptureAttestationError(not_mapping_reason)
    try:
        snapshot = _bounded_snapshot(value, reason=snapshot_reason)
    except AlrChallengerFitCaptureAttestationError:
        raise
    except Exception as exc:
        raise AlrChallengerFitCaptureAttestationError(snapshot_reason) from exc
    if not isinstance(snapshot, dict):
        raise AlrChallengerFitCaptureAttestationError(snapshot_reason)
    return snapshot


def _bounded_snapshot(value: Any, *, reason: str) -> Any:
    remaining = [_MAX_STRUCTURE_NODES]
    active: set[int] = set()

    def snapshot(current: Any, depth: int) -> Any:
        if depth > _MAX_STRUCTURE_DEPTH:
            raise AlrChallengerFitCaptureAttestationError(
                reason + ":depth_exceeded"
            )
        if remaining[0] <= 0:
            raise AlrChallengerFitCaptureAttestationError(
                reason + ":node_limit_exceeded"
            )
        remaining[0] -= 1
        if current is None or isinstance(current, (bool, int, float, str, bytes)):
            return current
        if isinstance(current, Mapping):
            identity = id(current)
            if identity in active:
                raise AlrChallengerFitCaptureAttestationError(
                    reason + ":circular_reference"
                )
            active.add(identity)
            output: dict[Any, Any] = {}
            try:
                iterator = iter(current.items())
                while True:
                    try:
                        key, item = next(iterator)
                    except StopIteration:
                        break
                    copied_key = snapshot(key, depth + 1)
                    copied_item = snapshot(item, depth + 1)
                    try:
                        output[copied_key] = copied_item
                    except (TypeError, ValueError) as exc:
                        raise AlrChallengerFitCaptureAttestationError(
                            reason + ":mapping_key_invalid"
                        ) from exc
            finally:
                active.remove(identity)
            return output
        if isinstance(current, Sequence) and not isinstance(
            current, (str, bytes, bytearray)
        ):
            identity = id(current)
            if identity in active:
                raise AlrChallengerFitCaptureAttestationError(
                    reason + ":circular_reference"
                )
            active.add(identity)
            output_items: list[Any] = []
            try:
                iterator = iter(current)
                while True:
                    try:
                        item = next(iterator)
                    except StopIteration:
                        break
                    output_items.append(snapshot(item, depth + 1))
            finally:
                active.remove(identity)
            return tuple(output_items) if isinstance(current, tuple) else output_items
        raise AlrChallengerFitCaptureAttestationError(
            reason + ":unsupported_type"
        )

    return snapshot(value, 0)


def _typed_equal(first: Any, second: Any) -> bool:
    try:
        return _canonical_json(first) == _canonical_json(second)
    except AlrChallengerFitCaptureAttestationError:
        return False


def _same_scalar(actual: Any, expected: Any) -> bool:
    if isinstance(expected, bool):
        return actual is expected
    return actual == expected and type(actual) is type(expected)


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and bool(_HASH_RE.fullmatch(value))


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
) -> AlrChallengerFitCaptureAttestationValidation:
    return AlrChallengerFitCaptureAttestationValidation(
        valid=False,
        verdict=INVALID,
        reason=reason,
        reasons=tuple(reasons or (reason,)),
    )


def _verification_invalid(
    reason: str,
    reasons: Sequence[str] | None = None,
) -> AlrChallengerFitCaptureVerification:
    return AlrChallengerFitCaptureVerification(
        valid=False,
        verifier_accepted=False,
        verdict=INVALID,
        reason=reason,
        reasons=tuple(reasons or (reason,)),
        attestation_hash=None,
        capability_authenticity=EXTERNAL_HOST_UNCHECKED,
        fit_capture_evidence_bound=False,
        execution_claim=NOT_ESTABLISHED,
        model_training_performed_claim=NOT_ESTABLISHED,
        persistence_allowed=False,
        authority_granted=False,
    )


def _verification_required(
    attestation_hash: str,
    reason: str,
) -> AlrChallengerFitCaptureVerification:
    return AlrChallengerFitCaptureVerification(
        valid=True,
        verifier_accepted=False,
        verdict=OUT_OF_BAND_FIT_ATTESTATION_REQUIRED,
        reason=reason,
        reasons=(reason,),
        attestation_hash=attestation_hash,
        capability_authenticity=EXTERNAL_HOST_UNCHECKED,
        fit_capture_evidence_bound=False,
        execution_claim=NOT_ESTABLISHED,
        model_training_performed_claim=NOT_ESTABLISHED,
        persistence_allowed=False,
        authority_granted=False,
    )


__all__ = [
    "ACTUAL_TRAINING_INPUT_BINDING_SCHEMA_VERSION",
    "ACTUAL_TRAINING_INPUT_MATERIALS_SCHEMA_VERSION",
    "ALR_CHALLENGER_FIT_CAPTURE_ATTESTATION_CONTRACT_SCHEMA_VERSION",
    "EXTERNAL_HOST_UNCHECKED",
    "FIT_CAPTURE_ATTESTED_EPHEMERAL",
    "FIT_CAPTURE_SCHEMA_VERSION",
    "FIT_RUNNER_IDENTITY_SCHEMA_VERSION",
    "INVALID",
    "NOT_ESTABLISHED",
    "OUT_OF_BAND_FIT_ATTESTATION_REQUIRED",
    "AlrChallengerFitCaptureAttestationError",
    "AlrChallengerFitCaptureAttestationValidation",
    "AlrChallengerFitCaptureVerification",
    "FitCaptureAttestationVerifier",
    "build_alr_challenger_fit_capture_attestation_contract",
    "compute_alr_challenger_fit_capture_attestation_hash",
    "validate_alr_challenger_fit_capture_attestation_contract",
    "verify_alr_challenger_fit_capture_attestation",
]
