from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import json
from collections.abc import Mapping, Sequence

import pytest

import ml_training.alr_challenger_fit_capture_attestation as attestation_module

from ml_training.alr_challenger_training_contract import (
    build_alr_challenger_training_contract,
)
from ml_training.alr_challenger_training_result_contract import (
    build_alr_challenger_training_result_contract,
)
from ml_training.candidate_proof_repository import (
    discover_candidate_proof_receipts,
)
from ml_training.pit_dataset_manifest import compute_pit_dataset_manifest_hash
from ml_training.proof_packet_contract import compute_proof_packet_hash
from ml_training.tests.test_alr_challenger_repository import (
    _expected_payload,
    _receipt_row,
)
from ml_training.tests.test_alr_challenger_training_contract import (
    _code_manifest,
    _training_config,
)
from ml_training.tests.test_alr_challenger_training_result_contract import (
    _observation,
)
from ml_training.tests.test_candidate_proof_adapter import (
    _binding,
    _bound_reward_record,
    _selected_projection,
)
from ml_training.tests.test_candidate_proof_repository import (
    _Connection,
    _bridge_row,
)
from ml_training.tests.test_proof_packet_contract import _valid_packet

from ml_training.alr_challenger_fit_capture_attestation import (
    ALR_CHALLENGER_FIT_CAPTURE_ATTESTATION_CONTRACT_SCHEMA_VERSION,
    EXTERNAL_HOST_UNCHECKED,
    FIT_CAPTURE_ATTESTED_EPHEMERAL,
    OUT_OF_BAND_FIT_ATTESTATION_REQUIRED,
    AlrChallengerFitCaptureAttestationError,
    build_alr_challenger_fit_capture_attestation_contract,
    compute_alr_challenger_fit_capture_attestation_hash,
    validate_alr_challenger_fit_capture_attestation_contract,
    verify_alr_challenger_fit_capture_attestation,
)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _domain_hash(domain: str, value: object) -> str:
    prefix = (
        "alr_challenger_fit_capture_attestation_contract_v1"
        + "\0"
        + domain
        + "\0"
    ).encode("utf-8")
    return hashlib.sha256(prefix + _canonical_bytes(value)).hexdigest()


def _rehash_candidate(contract: dict) -> None:
    runner = contract["fit_capture"]["runner_identity"]
    unsigned_runner = copy.deepcopy(runner)
    unsigned_runner.pop("runner_identity_hash", None)
    runner["runner_identity_hash"] = _domain_hash(
        "runner_identity", unsigned_runner
    )
    actual = contract["fit_capture"]["actual_training_inputs"]
    unsigned_actual = copy.deepcopy(actual)
    unsigned_actual.pop("material_set_hash", None)
    actual["material_set_hash"] = _domain_hash(
        "actual_training_input_material_set", unsigned_actual
    )
    contract["fit_capture_hash"] = _domain_hash(
        "fit_capture", contract["fit_capture"]
    )
    contract["attestation_hash"] = (
        compute_alr_challenger_fit_capture_attestation_hash(contract)
    )


def _raw_training_materials() -> dict[str, bytes]:
    return {
        "dataset_material": b"actual-dataset-material-v1",
        "row_ids_material": b"actual-row-ids-material-v1",
        "split_material": b"actual-split-material-v1",
        "feature_schema_material": b"actual-feature-schema-material-v1",
        "label_schema_material": b"actual-label-schema-material-v1",
    }


def _material_bound_result_contract() -> tuple[dict, dict, dict]:
    materials = _raw_training_materials()
    projection = _selected_projection()
    binding = _binding(projection)
    proof = _valid_packet()
    proof["candidate_identity"].update(
        {
            "candidate_id": binding["candidate_id"],
            "context_id": binding["context_id"],
            "symbol": "BTCUSDT",
        }
    )
    proof["execution_identity"]["entry_context_id"] = binding["context_id"]
    manifest = proof["provenance"]["pit_dataset_manifest"]
    manifest["candidate_scope"].update(
        {
            "candidate_id": binding["candidate_id"],
            "symbol": "BTCUSDT",
        }
    )
    dataset_hash = _sha256(materials["dataset_material"])
    row_ids_hash = _sha256(materials["row_ids_material"])
    split_hash = _sha256(materials["split_material"])
    feature_schema_hash = _sha256(materials["feature_schema_material"])
    label_schema_hash = _sha256(materials["label_schema_material"])
    manifest["row_set"].update(
        {
            "dataset_hash": dataset_hash,
            "row_ids_hash": row_ids_hash,
        }
    )
    manifest["rebuild_evidence"].update(
        {
            "original_dataset_hash": dataset_hash,
            "rebuilt_dataset_hash": dataset_hash,
            "original_row_ids_hash": row_ids_hash,
            "rebuilt_row_ids_hash": row_ids_hash,
        }
    )
    manifest["split_lineage"]["split_hash"] = split_hash
    manifest["feature_lineage"]["feature_schema_hash"] = feature_schema_hash
    manifest["label_lineage"]["label_schema_hash"] = label_schema_hash
    manifest["manifest_hash"] = compute_pit_dataset_manifest_hash(manifest)
    proof["provenance"]["input_artifact_hashes"].update(
        {
            "candidate_projection_artifact_hash": projection["artifact"][
                "artifact_hash"
            ],
            "candidate_projection_decision_hash": projection["decision"][
                "decision_hash"
            ],
            "candidate_projection_handoff_hash": binding["handoff_hash"],
        }
    )
    proof["proof_packet_hash"] = compute_proof_packet_hash(proof)
    rewards = [
        _bound_reward_record(proof, window_id="window-0"),
        _bound_reward_record(proof, window_id="window-1"),
    ]
    repository_receipt = discover_candidate_proof_receipts(
        _Connection(
            projection,
            bridge_rows=[_bridge_row(proof, rewards)],
        ),
        limit=8,
    )["receipts"][0]

    training_config = _training_config()
    training_config["feature_schema_hash"] = feature_schema_hash
    training_config["label_schema_hash"] = label_schema_hash
    training_contract = build_alr_challenger_training_contract(
        repository_receipt,
        code_manifest=_code_manifest(),
        training_config=training_config,
    )
    receipt_read = {
        "status": "FOUND",
        "receipt": _receipt_row(_expected_payload(training_contract)),
    }
    observation = _observation()
    result_contract = build_alr_challenger_training_result_contract(
        receipt_read,
        training_contract=training_contract,
        observation=observation,
    )

    code_payload = copy.deepcopy(training_contract["code_manifest"])
    code_payload.pop("code_manifest_hash")
    config_payload = copy.deepcopy(training_contract["training_config"])
    config_payload.pop("training_config_hash")
    actual_inputs = {
        "schema_version": "alr_challenger_actual_training_input_materials_v1",
        "source_head_material": bytes.fromhex(
            training_contract["code_manifest"]["source_head"]
        ),
        "input_lineage_material": _canonical_bytes(
            training_contract["input_lineage"]
        ),
        **materials,
        "code_manifest_material": _canonical_bytes(code_payload),
        "training_config_material": _canonical_bytes(config_payload),
        "training_rows": training_contract["input_lineage"]["row_count"],
    }
    return result_contract, observation, actual_inputs


def _fit_capture() -> tuple[dict, dict]:
    result_contract, observation, actual_inputs = (
        _material_bound_result_contract()
    )
    capture = {
        "schema_version": "alr_challenger_fit_capture_v1",
        "runner_identity": {
            "schema_version": "alr_challenger_fit_runner_identity_v1",
            "producer_kind": "isolated_challenger_fit_runner",
            "producer_id": "local-alr-fit-runner",
            "runner_version": "runner-v1",
            "runner_source_material": b"runner-source-material-v1",
            "host_identity_material": b"host-identity-material-v1",
            "environment_identity_material": b"environment-identity-material-v1",
            "process_identity_material": b"process-identity-material-v1",
            "invocation_id": observation["attempt_id"],
            "captured_at": "2026-07-11T20:00:02.700000Z",
        },
        "actual_training_inputs": actual_inputs,
        "attempt_id": observation["attempt_id"],
        "trainer_spec": copy.deepcopy(observation["trainer_spec"]),
        "seed": observation["seed"],
        "fit_started_at": observation["fit_started_at"],
        "fit_completed_at": observation["fit_completed_at"],
        "model_schema_version": observation["model_schema_version"],
        "artifact_readback": {
            quantile: {
                "format": observation["artifacts"][quantile]["format"],
                "readback_bytes": bytes(
                    observation["artifacts"][quantile]["model_bytes"]
                ),
                "io_descriptor": copy.deepcopy(
                    observation["artifacts"][quantile]["io_descriptor"]
                ),
            }
            for quantile in ("q10", "q50", "q90")
        },
    }
    return result_contract, capture


def _contains_raw_bytes(value: object) -> bool:
    if isinstance(value, (bytes, bytearray)):
        return True
    if isinstance(value, dict):
        return any(
            _contains_raw_bytes(key) or _contains_raw_bytes(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_raw_bytes(item) for item in value)
    return False


def test_fit_capture_attestation_public_api_is_narrow_and_source_only() -> None:
    assert (
        ALR_CHALLENGER_FIT_CAPTURE_ATTESTATION_CONTRACT_SCHEMA_VERSION
        == "alr_challenger_fit_capture_attestation_contract_v1"
    )
    assert (
        OUT_OF_BAND_FIT_ATTESTATION_REQUIRED
        == "OUT_OF_BAND_FIT_ATTESTATION_REQUIRED"
    )
    assert FIT_CAPTURE_ATTESTED_EPHEMERAL == "FIT_CAPTURE_ATTESTED_EPHEMERAL"
    assert tuple(
        inspect.signature(
            build_alr_challenger_fit_capture_attestation_contract
        ).parameters
    ) == ("result_contract", "fit_capture")
    assert tuple(
        inspect.signature(
            compute_alr_challenger_fit_capture_attestation_hash
        ).parameters
    ) == ("contract",)
    assert tuple(
        inspect.signature(
            validate_alr_challenger_fit_capture_attestation_contract
        ).parameters
    ) == ("contract",)
    assert tuple(
        inspect.signature(
            verify_alr_challenger_fit_capture_attestation
        ).parameters
    ) == ("contract", "out_of_band_verifier")


def test_builds_deterministic_unestablished_fit_capture_candidate() -> None:
    result_contract, fit_capture = _fit_capture()
    original_result = copy.deepcopy(result_contract)
    original_capture = copy.deepcopy(fit_capture)

    first = build_alr_challenger_fit_capture_attestation_contract(
        result_contract,
        fit_capture=fit_capture,
    )
    second = build_alr_challenger_fit_capture_attestation_contract(
        copy.deepcopy(result_contract),
        fit_capture=copy.deepcopy(fit_capture),
    )

    assert first == second
    assert set(first) == {
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
    assert first["schema_version"] == (
        "alr_challenger_fit_capture_attestation_contract_v1"
    )
    assert first["contract_kind"] == "FIT_CAPTURE_ATTESTATION_CANDIDATE"
    assert first["status"] == OUT_OF_BAND_FIT_ATTESTATION_REQUIRED
    assert first["reason"] == "out_of_band_host_fit_attestation_required"
    assert first["execution_claim"] == "NOT_ESTABLISHED"
    assert first["model_training_performed_claim"] == "NOT_ESTABLISHED"
    assert first["persistence_allowed"] is False
    assert first["verifier_authenticity_claim"] == "NOT_ESTABLISHED"
    assert first["result_contract"] == result_contract
    assert first["result_hash"] == result_contract["result_hash"]
    actual = first["fit_capture"]["actual_training_inputs"]
    raw_actual = fit_capture["actual_training_inputs"]
    assert actual["source_head"] == raw_actual["source_head_material"].hex()
    assert actual["training_input_hash"] == result_contract[
        "admission"
    ]["training_contract"]["training_input_hash"]
    for raw_field, derived_field in (
        ("dataset_material", "actual_dataset_hash"),
        ("row_ids_material", "actual_row_ids_hash"),
        ("split_material", "actual_split_hash"),
        ("feature_schema_material", "actual_feature_schema_hash"),
        ("label_schema_material", "actual_label_schema_hash"),
    ):
        assert actual[derived_field] == _sha256(raw_actual[raw_field])
    assert actual["actual_training_rows"] == 128
    artifacts = first["fit_capture"]["artifact_readback"]
    assert [item["quantile"] for item in artifacts] == ["q10", "q50", "q90"]
    assert all(item["readback_claim"] == "UNVERIFIED" for item in artifacts)
    assert first["fit_capture"]["model_artifact_set_hash"] == result_contract[
        "model_artifact_set_hash"
    ]
    assert first["fit_capture"]["capture_claim"] == "UNVERIFIED"
    assert first["evidence_obligations"][
        "out_of_band_verifier_authenticity_required"
    ] is True
    assert first["evidence_obligations"][
        "verifier_time_bound_external_required"
    ] is True
    assert first["evidence_obligations"][
        "durable_attestation_schema_required"
    ] is True
    assert set(first["no_authority"].values()) == {False}
    assert set(first["authority_counters"].values()) == {0}
    assert first["attestation_hash"] == (
        compute_alr_challenger_fit_capture_attestation_hash(first)
    )
    assert validate_alr_challenger_fit_capture_attestation_contract(first).valid
    assert _contains_raw_bytes(first) is False
    assert b"actual-dataset-material-v1" not in repr(first).encode("utf-8")
    assert b"onnx-q10-fixture" not in repr(first).encode("utf-8")
    assert result_contract == original_result
    assert fit_capture == original_capture


@pytest.mark.parametrize(
    "field",
    [
        "source_head_material",
        "input_lineage_material",
        "dataset_material",
        "row_ids_material",
        "split_material",
        "code_manifest_material",
        "training_config_material",
        "feature_schema_material",
        "label_schema_material",
    ],
)
def test_every_actual_training_material_is_rehashed_and_bound(field: str) -> None:
    result_contract, fit_capture = _fit_capture()
    fit_capture["actual_training_inputs"][field] += b"-tampered"

    with pytest.raises(
        AlrChallengerFitCaptureAttestationError,
        match="mismatch",
    ):
        build_alr_challenger_fit_capture_attestation_contract(
            result_contract,
            fit_capture=fit_capture,
        )


def test_hash_only_actual_input_and_boolean_row_count_fail_closed() -> None:
    result_contract, fit_capture = _fit_capture()
    fit_capture["actual_training_inputs"]["dataset_material"] = (
        result_contract["expected_training_inputs"]["dataset_hash"]
    )

    with pytest.raises(
        AlrChallengerFitCaptureAttestationError,
        match="dataset_material_bytes_invalid",
    ):
        build_alr_challenger_fit_capture_attestation_contract(
            result_contract,
            fit_capture=fit_capture,
        )

    result_contract, fit_capture = _fit_capture()
    fit_capture["actual_training_inputs"]["training_rows"] = True
    with pytest.raises(
        AlrChallengerFitCaptureAttestationError,
        match="actual_training_rows_mismatch",
    ):
        build_alr_challenger_fit_capture_attestation_contract(
            result_contract,
            fit_capture=fit_capture,
        )


@pytest.mark.parametrize(
    ("surface", "field", "value"),
    [
        ("capture", "execution_claim", "ESTABLISHED"),
        ("runner_identity", "trusted", True),
        ("actual_training_inputs", "actual_dataset_hash", "a" * 64),
        ("artifact_q10", "artifact_hash", "a" * 64),
    ],
)
def test_caller_cannot_supply_claim_hash_status_or_trust_surfaces(
    surface: str,
    field: str,
    value: object,
) -> None:
    result_contract, fit_capture = _fit_capture()
    if surface == "capture":
        target = fit_capture
    elif surface == "artifact_q10":
        target = fit_capture["artifact_readback"]["q10"]
    else:
        target = fit_capture[surface]
    target[field] = value

    with pytest.raises(
        AlrChallengerFitCaptureAttestationError,
        match="fields_invalid",
    ):
        build_alr_challenger_fit_capture_attestation_contract(
            result_contract,
            fit_capture=fit_capture,
        )


def test_validator_rejects_self_consistent_invalid_runner_identity() -> None:
    result_contract, fit_capture = _fit_capture()
    contract = build_alr_challenger_fit_capture_attestation_contract(
        result_contract,
        fit_capture=fit_capture,
    )
    contract["fit_capture"]["runner_identity"]["producer_id"] = "../escape"
    _rehash_candidate(contract)

    validation = validate_alr_challenger_fit_capture_attestation_contract(
        contract
    )

    assert validation.valid is False
    assert "producer_id" in validation.reason


@pytest.mark.parametrize(
    "surface",
    ["runner_identity", "actual_training_inputs"],
)
def test_validator_rejects_self_consistent_over_budget_material_sizes(
    surface: str,
) -> None:
    result_contract, fit_capture = _fit_capture()
    contract = build_alr_challenger_fit_capture_attestation_contract(
        result_contract,
        fit_capture=fit_capture,
    )
    binding = contract["fit_capture"][surface]
    binding["material_sizes"] = {
        key: 268_435_456 for key in binding["material_sizes"]
    }
    binding["total_material_bytes"] = sum(binding["material_sizes"].values())
    _rehash_candidate(contract)

    validation = validate_alr_challenger_fit_capture_attestation_contract(
        contract
    )

    assert validation.valid is False
    assert "total_material_bytes" in validation.reason


@pytest.mark.parametrize(
    "surface",
    ["runner_identity", "actual_training_inputs"],
)
def test_validator_rejects_numeric_alias_for_total_material_bytes(
    surface: str,
) -> None:
    result_contract, fit_capture = _fit_capture()
    contract = build_alr_challenger_fit_capture_attestation_contract(
        result_contract,
        fit_capture=fit_capture,
    )
    binding = contract["fit_capture"][surface]
    binding["total_material_bytes"] = float(binding["total_material_bytes"])
    _rehash_candidate(contract)

    validation = validate_alr_challenger_fit_capture_attestation_contract(
        contract
    )

    assert validation.valid is False
    assert "total_material_bytes" in validation.reason


@pytest.mark.parametrize("numeric_alias", [1, 1.0])
def test_validator_rejects_numeric_alias_for_evidence_obligation_boolean(
    numeric_alias: int | float,
) -> None:
    result_contract, fit_capture = _fit_capture()
    contract = build_alr_challenger_fit_capture_attestation_contract(
        result_contract,
        fit_capture=fit_capture,
    )
    contract["evidence_obligations"][
        "durable_attestation_schema_required"
    ] = numeric_alias
    _rehash_candidate(contract)

    validation = validate_alr_challenger_fit_capture_attestation_contract(
        contract
    )

    assert validation.valid is False
    assert "evidence_obligations" in validation.reason


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("attempt_id", "different-attempt"),
        ("seed", 43),
        ("fit_started_at", "2026-07-11T20:00:00.123457Z"),
        ("fit_completed_at", "2026-07-11T20:00:02.654322Z"),
        ("model_schema_version", "different-model-schema"),
    ],
)
def test_fit_capture_scalar_observations_must_match_result_exactly(
    field: str,
    value: object,
) -> None:
    result_contract, fit_capture = _fit_capture()
    fit_capture[field] = value

    with pytest.raises(
        AlrChallengerFitCaptureAttestationError,
        match=field + "_mismatch",
    ):
        build_alr_challenger_fit_capture_attestation_contract(
            result_contract,
            fit_capture=fit_capture,
        )


def test_trainer_spec_and_runner_capture_are_exactly_bound() -> None:
    result_contract, fit_capture = _fit_capture()
    fit_capture["trainer_spec"]["implementation_version"] = "other"
    with pytest.raises(
        AlrChallengerFitCaptureAttestationError,
        match="trainer_spec_mismatch",
    ):
        build_alr_challenger_fit_capture_attestation_contract(
            result_contract,
            fit_capture=fit_capture,
        )

    result_contract, fit_capture = _fit_capture()
    fit_capture["runner_identity"]["invocation_id"] = "different-attempt"
    with pytest.raises(
        AlrChallengerFitCaptureAttestationError,
        match="runner_invocation_id_mismatch",
    ):
        build_alr_challenger_fit_capture_attestation_contract(
            result_contract,
            fit_capture=fit_capture,
        )

    result_contract, fit_capture = _fit_capture()
    fit_capture["runner_identity"]["captured_at"] = (
        "2026-07-11T20:00:02.000000Z"
    )
    with pytest.raises(
        AlrChallengerFitCaptureAttestationError,
        match="runner_capture_before_fit_completed",
    ):
        build_alr_challenger_fit_capture_attestation_contract(
            result_contract,
            fit_capture=fit_capture,
        )


@pytest.mark.parametrize("quantile", ["q10", "q50", "q90"])
def test_every_artifact_readback_byte_and_descriptor_is_bound(
    quantile: str,
) -> None:
    result_contract, fit_capture = _fit_capture()
    fit_capture["artifact_readback"][quantile]["readback_bytes"] += b"tamper"
    with pytest.raises(
        AlrChallengerFitCaptureAttestationError,
        match=f"artifact_{quantile}_hash_mismatch",
    ):
        build_alr_challenger_fit_capture_attestation_contract(
            result_contract,
            fit_capture=fit_capture,
        )

    result_contract, fit_capture = _fit_capture()
    fit_capture["artifact_readback"][quantile]["io_descriptor"][
        "output_rank"
    ] = 2
    with pytest.raises(
        AlrChallengerFitCaptureAttestationError,
        match=f"artifact_{quantile}_descriptor_mismatch",
    ):
        build_alr_challenger_fit_capture_attestation_contract(
            result_contract,
            fit_capture=fit_capture,
        )


@pytest.mark.parametrize("change", ["missing", "extra"])
def test_artifact_readback_quantile_set_is_exact(change: str) -> None:
    result_contract, fit_capture = _fit_capture()
    if change == "missing":
        fit_capture["artifact_readback"].pop("q10")
    else:
        fit_capture["artifact_readback"]["q99"] = copy.deepcopy(
            fit_capture["artifact_readback"]["q90"]
        )

    with pytest.raises(
        AlrChallengerFitCaptureAttestationError,
        match="artifact_readback_quantiles_invalid",
    ):
        build_alr_challenger_fit_capture_attestation_contract(
            result_contract,
            fit_capture=fit_capture,
        )


def test_verifier_is_called_once_only_after_structural_validation() -> None:
    result_contract, fit_capture = _fit_capture()
    contract = build_alr_challenger_fit_capture_attestation_contract(
        result_contract,
        fit_capture=fit_capture,
    )
    calls: list[tuple[str, str, bytes]] = []

    def verifier(kind: str, digest: str, payload: bytes) -> bool:
        calls.append((kind, digest, payload))
        return True

    result = verify_alr_challenger_fit_capture_attestation(
        contract,
        out_of_band_verifier=verifier,
    )

    assert result.valid is True
    assert result.verifier_accepted is True
    assert result.verdict == FIT_CAPTURE_ATTESTED_EPHEMERAL
    assert result.reason == "out_of_band_verifier_accepted_ephemeral_only"
    assert result.capability_authenticity == EXTERNAL_HOST_UNCHECKED
    assert result.fit_capture_evidence_bound is True
    assert result.execution_claim == "NOT_ESTABLISHED"
    assert result.model_training_performed_claim == "NOT_ESTABLISHED"
    assert result.persistence_allowed is False
    assert result.authority_granted is False
    assert len(calls) == 1
    kind, digest, payload = calls[0]
    assert kind == "alr_challenger_fit_capture_attestation_contract_v1"
    assert digest == contract["attestation_hash"]
    assert type(payload) is bytes
    assert json.loads(payload) == contract

    invalid = copy.deepcopy(contract)
    invalid["status"] = "FIT_PERFORMED"
    calls.clear()
    rejected = verify_alr_challenger_fit_capture_attestation(
        invalid,
        out_of_band_verifier=verifier,
    )
    assert rejected.valid is False
    assert rejected.verifier_accepted is False
    assert calls == []


class _TruthyVerifierResult:
    def __bool__(self) -> bool:
        return True


@pytest.mark.parametrize(
    "outcome",
    [False, None, 1, _TruthyVerifierResult()],
)
def test_verifier_requires_literal_true_and_never_grants_authority(
    outcome: object,
) -> None:
    result_contract, fit_capture = _fit_capture()
    contract = build_alr_challenger_fit_capture_attestation_contract(
        result_contract,
        fit_capture=fit_capture,
    )

    result = verify_alr_challenger_fit_capture_attestation(
        contract,
        out_of_band_verifier=lambda *_args: outcome,
    )

    assert result.valid is True
    assert result.verifier_accepted is False
    assert result.verdict == OUT_OF_BAND_FIT_ATTESTATION_REQUIRED
    assert result.fit_capture_evidence_bound is False
    assert result.execution_claim == "NOT_ESTABLISHED"
    assert result.model_training_performed_claim == "NOT_ESTABLISHED"
    assert result.persistence_allowed is False
    assert result.authority_granted is False


def test_missing_exception_and_mutating_verifiers_fail_closed() -> None:
    result_contract, fit_capture = _fit_capture()
    contract = build_alr_challenger_fit_capture_attestation_contract(
        result_contract,
        fit_capture=fit_capture,
    )

    missing = verify_alr_challenger_fit_capture_attestation(
        contract,
        out_of_band_verifier=None,
    )
    assert missing.reason == "out_of_band_verifier_missing"

    def exploding(*_args: object) -> bool:
        raise RuntimeError("must-not-leak")

    failed = verify_alr_challenger_fit_capture_attestation(
        contract,
        out_of_band_verifier=exploding,
    )
    assert failed.verifier_accepted is False
    assert failed.reason == "out_of_band_verifier_exception:RuntimeError"
    assert "must-not-leak" not in repr(failed)

    mutable = copy.deepcopy(contract)

    def mutating(*_args: object) -> bool:
        mutable["status"] = "MUTATED"
        return True

    mutated = verify_alr_challenger_fit_capture_attestation(
        mutable,
        out_of_band_verifier=mutating,
    )
    assert mutated.verifier_accepted is False
    assert mutated.reason == "attestation_contract_mutated_during_verification"


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


def test_public_validator_is_total_over_deep_wide_cyclic_and_exploding_inputs() -> None:
    deep: dict = {}
    cursor = deep
    for _ in range(70):
        child: dict = {}
        cursor["child"] = child
        cursor = child
    cyclic: dict = {}
    cyclic["self"] = cyclic
    infinite = _GuardedInfiniteSequence()
    malformed = [
        None,
        [],
        deep,
        cyclic,
        {"wide": [0] * 50_001},
        {"infinite": infinite},
        _ExplodingItemsMapping(),
    ]

    for value in malformed:
        validation = validate_alr_challenger_fit_capture_attestation_contract(
            value
        )
        assert validation.valid is False
        assert validation.verdict == "INVALID"
        assert validation.reason
    assert infinite.accesses <= 50_005


def test_builder_bounds_infinite_capture_before_normalization() -> None:
    result_contract, fit_capture = _fit_capture()
    infinite = _GuardedInfiniteSequence()
    fit_capture["runner_identity"] = infinite

    with pytest.raises(
        AlrChallengerFitCaptureAttestationError,
        match="node_limit_exceeded",
    ):
        build_alr_challenger_fit_capture_attestation_contract(
            result_contract,
            fit_capture=fit_capture,
        )
    assert infinite.accesses <= 50_005


def test_module_has_no_persistence_runtime_or_execution_import_surface() -> None:
    tree = ast.parse(inspect.getsource(attestation_module))
    imported_roots: set[str] = set()
    called_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            called_names.add(node.func.id)

    assert imported_roots.isdisjoint(
        {
            "lightgbm",
            "onnxruntime",
            "pathlib",
            "psycopg",
            "psycopg2",
            "sqlalchemy",
            "subprocess",
        }
    )
    assert called_names.isdisjoint({"eval", "exec", "open"})
