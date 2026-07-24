from __future__ import annotations

import base64
import copy
import hashlib
import json
from collections.abc import Mapping
from functools import lru_cache

import pytest

import program_code.ml_training.alr_trusted_fit_handshake as handshake

from ml_training.alr_challenger_fit_capture_attestation import (
    build_alr_challenger_fit_capture_attestation_contract,
    validate_alr_challenger_fit_capture_attestation_contract,
)
from ml_training.alr_challenger_training_result_contract import (
    build_alr_challenger_training_result_contract,
)
from ml_training.tests.test_alr_challenger_fit_capture_attestation import (
    _fit_capture,
)
from ml_training.tests.test_alr_challenger_training_result_contract import (
    _observation,
)

from program_code.ml_training.alr_trusted_fit_handshake import (
    ACTIVE,
    ACCEPTED_IN_PROGRESS,
    AUDIENCE_MISMATCH,
    AUTHENTICATED_UNCONSUMED,
    CANONICAL_BYTES_INVALID,
    DURABLE_CONSUMPTION_CONFLICT,
    DURABLE_CONSUMPTION_REQUIRED,
    EXACT_REPLAY,
    FAILED_AFTER_START,
    INVALID,
    NONCE_REPLAY_CONFLICT,
    POLICY_OR_KEY_REJECTED,
    RECEIPT_OUTCOME_INVALID,
    RECEIPT_REQUEST_BINDING_MISMATCH,
    RECEIPT_SIGNATURE_INVALID,
    RECEIPT_TIME_INVALID,
    RECONCILE_REQUIRED,
    REJECTED_PRE_FIT,
    REQUEST_SIGNATURE_INVALID,
    RUNNER_TARGET_MISMATCH,
    RETIRED,
    REQUEST_SIGNATURE_DOMAIN,
    STATUS,
    SUCCEEDED,
    TERMINAL,
    TERMINAL_RECEIPT_SIGNATURE_DOMAIN,
    VALID,
    V159_INNER_SIGNATURE_DOMAIN,
    V159_INNER_SIGNATURE_INVALID,
    EXTERNAL_HOST_UNCHECKED,
    build_isolated_fit_execution_response,
    build_key_status_overlay,
    build_trust_policy_snapshot,
    build_trusted_fit_execution_request,
    build_trusted_fit_request_payload,
    canonical_outer_json_bytes,
    canonical_v159_jsonb_text_bytes,
    classify_response_replay,
    classify_request_replay,
    domain_hash,
    parse_canonical_outer_json,
    parse_canonical_v159_jsonb_text_bytes,
    request_signature_preimage,
    strict_base64url_decode,
    terminal_receipt_signature_preimage,
    validate_key_status_overlay,
    validate_isolated_fit_execution_response,
    validate_trusted_fit_execution_request,
    validate_trusted_fit_request_bytes,
    verify_isolated_fit_response,
    v159_inner_signature_preimage,
)


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _h(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def test_public_api_exports_frozen_usage_and_failure_code_surface() -> None:
    expected = {
        "HANDSHAKE_SIGNING_USAGE",
        "STRUCTURE_INVALID",
        "REQUEST_SIGNATURE_INVALID",
        "REQUEST_NOT_YET_VALID",
        "REQUEST_EXPIRED",
        "AUDIENCE_MISMATCH",
        "POLICY_OR_KEY_REJECTED",
        "RUNNER_TARGET_MISMATCH",
        "RECEIPT_SIGNATURE_INVALID",
        "RECEIPT_REQUEST_BINDING_MISMATCH",
        "RECEIPT_TIME_INVALID",
        "RECEIPT_OUTCOME_INVALID",
        "EXECUTION_CLAIM_MISMATCH",
        "V159_INNER_SIGNATURE_INVALID",
        "V159_INNER_RECEIPT_MISMATCH",
        "AUTHORITY_MISMATCH",
        "RECONCILE_REQUIRED",
        "DURABLE_CONSUMPTION_REQUIRED",
    }

    assert expected <= set(handshake.__all__)


def _result_contract_domain_hash(domain: str, value: object) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(
        b"alr_challenger_training_result_contract_v1\x00"
        + domain.encode("ascii")
        + b"\x00"
        + canonical
    ).hexdigest()


def _timestamp(second: int) -> str:
    return f"2026-07-12T12:00:{second:02d}.000000Z"


def _key_entry(
    *,
    generation: int = 7,
    key_id: str = "issuer.test.key-7",
    byte_offset: int = 0,
) -> dict:
    public_key = bytes((value + byte_offset) % 256 for value in range(32))
    return {
        "issuer_id": "issuer.test",
        "key_id": key_id,
        "generation": generation,
        "algorithm": "ed25519",
        "usage": "ALR_TRUSTED_FIT_HANDSHAKE_SIGNING",
        "public_key_base64url": _b64url(public_key),
        "public_key_digest": hashlib.sha256(public_key).hexdigest(),
    }


@lru_cache(maxsize=1)
def _base_fit_fixture() -> tuple[dict, dict]:
    result, capture = _fit_capture()
    return copy.deepcopy(result), copy.deepcopy(capture)


def _base_fit_fixture_copy() -> tuple[dict, dict]:
    result, capture = _base_fit_fixture()
    return copy.deepcopy(result), copy.deepcopy(capture)


class _ExplodingMapping(Mapping):
    def __getitem__(self, _key):
        raise KeyError

    def __iter__(self):
        raise RuntimeError("deliberate-mapping-failure")

    def __len__(self) -> int:
        return 1


class _RetiredAsActiveOverlay(dict):
    def get(self, key, default=None):
        if key == "status":
            return ACTIVE
        return super().get(key, default)


def _request(
    *,
    max_wall_seconds: int = 120,
    max_training_rows: int = 1_000,
    allowed_keys: list[dict] | None = None,
    signing_key_id: str = "issuer.test.key-7",
) -> tuple[dict, dict, dict]:
    base_result, raw_capture = _base_fit_fixture_copy()
    keys = [_key_entry()] if allowed_keys is None else copy.deepcopy(allowed_keys)
    policy = build_trust_policy_snapshot(
        policy_id="policy.test",
        epoch=11,
        audience="alr.fit.runner.test",
        allowed_keys=keys,
        retired_key_verification_allowed=True,
    )
    expected_inputs = copy.deepcopy(base_result["expected_training_inputs"])
    admission = {
        "training_contract": copy.deepcopy(
            base_result["admission"]["training_contract"]
        ),
        "qualified_receipt_read": copy.deepcopy(
            base_result["admission"]["qualified_receipt_read"]
        ),
        "durable_receipt_hash": expected_inputs["durable_receipt_hash"],
        "training_key_hash": expected_inputs["training_key_hash"],
        "training_contract_hash": expected_inputs["training_contract_hash"],
        "qualified_receipt_binding_hash": base_result["admission"][
            "qualified_receipt_binding_hash"
        ],
    }
    execution_contract = {
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
    resource_budget = {
        "max_wall_seconds": max_wall_seconds,
        "max_cpu_seconds": 90,
        "max_memory_bytes": 100_000_000,
        "max_artifact_bytes": 100_000,
        "max_training_rows": max_training_rows,
        "max_external_requests": 0,
        "max_api_cost_usd": 0,
    }
    runner_target = {
        "schema_version": "alr_isolated_runner_target_policy_v1",
        "producer_kind": "isolated_challenger_fit_runner",
        "producer_id": raw_capture["runner_identity"]["producer_id"],
        "runner_source_hash": hashlib.sha256(
            raw_capture["runner_identity"]["runner_source_material"]
        ).hexdigest(),
        "measurement_hash": _h("measurement"),
        "isolation_class": "process_no_network_no_persistence",
        "capability_class": "fit_only_no_authority",
        "output_contract_hash": _h("output-contract"),
    }
    payload = build_trusted_fit_request_payload(
        admission=admission,
        expected_training_inputs=expected_inputs,
        execution_contract=execution_contract,
        resource_budget=resource_budget,
        request_nonce="ab" * 32,
        request_generation=3,
        requester_id="alr.pm.test",
        issuer_id="issuer.test",
        audience="alr.fit.runner.test",
        trust_policy_snapshot=policy,
        signing_key_id=signing_key_id,
        runner_target_policy=runner_target,
        issued_at=_timestamp(0),
        not_before=_timestamp(1),
        accept_by=_timestamp(10),
        complete_by=_timestamp(50),
    )
    request = build_trusted_fit_execution_request(
        payload,
        signature=_b64url(b"r" * 64),
    )
    selected = next(key for key in keys if key["key_id"] == signing_key_id)
    return request, policy, copy.deepcopy(selected)


def test_handshake_rejects_malformed_learning_runtime_digest() -> None:
    # LR1(S2.2A):handshake 綁定。expected_training_inputs.learning_runtime_digest 不是
    # sha256: 前綴 digest → learning_runtime_digest_invalid(在 admission parity 檢查之前觸發)。
    from program_code.ml_training.alr_trusted_fit_handshake import (
        AlrTrustedFitHandshakeError,
        _validated_expected_inputs,
    )

    base_result, _ = _base_fit_fixture_copy()
    expected = copy.deepcopy(base_result["expected_training_inputs"])
    assert "learning_runtime_digest" in expected
    expected["learning_runtime_digest"] = "not-a-sha256-digest"
    with pytest.raises(
        AlrTrustedFitHandshakeError, match="learning_runtime_digest_invalid"
    ):
        _validated_expected_inputs(expected, base_result["admission"])


def _runner_identity(request: dict) -> dict:
    target = request["signed_payload"]["runner_target_policy"]
    raw_runner = _base_fit_fixture_copy()[1]["runner_identity"]
    identity = {
        "schema_version": "alr_isolated_runner_identity_v1",
        "producer_kind": target["producer_kind"],
        "producer_id": target["producer_id"],
        "runner_version": raw_runner["runner_version"],
        "runner_source_hash": target["runner_source_hash"],
        "host_identity_hash": hashlib.sha256(
            raw_runner["host_identity_material"]
        ).hexdigest(),
        "environment_identity_hash": hashlib.sha256(
            raw_runner["environment_identity_material"]
        ).hexdigest(),
        "process_identity_hash": hashlib.sha256(
            raw_runner["process_identity_material"]
        ).hexdigest(),
        "measurement_hash": target["measurement_hash"],
        "isolation_class": target["isolation_class"],
        "capability_class": target["capability_class"],
        "output_contract_hash": target["output_contract_hash"],
        "invocation_id": request["request_hash"],
        "captured_at": _timestamp(5),
    }
    identity["runner_identity_hash"] = domain_hash(
        "actual_runner_identity", identity
    )
    return identity


def _response_payload(outcome: str, *, request: dict | None = None) -> dict:
    if request is None:
        request = _request()[0]
    request_payload = request["signed_payload"]
    common = {
        "schema_version": "alr_isolated_fit_execution_receipt_v1",
        "response_kind": STATUS if outcome == ACCEPTED_IN_PROGRESS else TERMINAL,
        "outcome": outcome,
        "request_hash": request["request_hash"],
        "attempt_id": request["request_hash"],
        "nonce_digest": request_payload["nonce_digest"],
        "request_generation": request_payload["request_generation"],
        "audience": request_payload["audience"],
        "issuer_id": request_payload["issuer_id"],
        "trust_policy_id": request_payload["trust_policy_id"],
        "trust_policy_snapshot_digest": request_payload[
            "trust_policy_snapshot_digest"
        ],
        "trust_policy_epoch": request_payload["trust_policy_epoch"],
        "signature_algorithm": "ed25519",
        "signing_key_id": request_payload["signing_key_id"],
        "runner_target_policy_hash": request_payload["runner_target_policy_hash"],
        "actual_runner_identity": _runner_identity(request),
        "accepted_at": _timestamp(5),
        "no_authority": copy.deepcopy(request["no_authority"]),
        "authority_counters": copy.deepcopy(request["authority_counters"]),
    }
    if outcome == ACCEPTED_IN_PROGRESS:
        return {
            **common,
            "status_generation": 1,
            "status_issued_at": _timestamp(6),
            "status_expires_at": _timestamp(30),
            "stage_observations": {
                "request_accepted": True,
                "actual_inputs_consumed": False,
                "fit_started": False,
                "fit_completed": False,
                "artifacts_written": False,
                "artifact_readback_completed": False,
                "onnx_semantic_validation_completed": False,
            },
        }
    terminal = {
        **common,
        "issuer_verified_at": _timestamp(30),
        "receipt_expires_at": _timestamp(45),
        "automatic_retry_allowed": False,
        "persistence_allowed": False,
    }
    if outcome == REJECTED_PRE_FIT:
        return {
            **terminal,
            "v159_success_projection_allowed": False,
            "rejected_at": _timestamp(20),
            "failure_phase": "PRE_FIT_ADMISSION",
            "failure_code": "RUNNER_TARGET_UNAVAILABLE",
            "actual_inputs_consumed": False,
            "fit_started": False,
            "model_training_performed": False,
            "result_observation": None,
            "inner_receipt_bytes_base64url": None,
            "inner_receipt_digest_sha256": None,
        }
    if outcome == FAILED_AFTER_START:
        return {
            **terminal,
            "v159_success_projection_allowed": False,
            "fit_started_at": _timestamp(8),
            "failure_observed_at": _timestamp(25),
            "fit_completed_at": None,
            "captured_at": None,
            "failure_phase": "FIT_EXECUTION",
            "failure_code": "FIT_EXECUTION_FAILED",
            "stage_observations": {
                "request_accepted": True,
                "actual_inputs_consumed": True,
                "fit_started": True,
                "fit_completed": False,
                "artifacts_written": False,
                "artifact_readback_completed": False,
                "onnx_semantic_validation_completed": False,
            },
            "result_observation": None,
            "inner_receipt_bytes_base64url": None,
            "inner_receipt_digest_sha256": None,
        }
    raise AssertionError(outcome)


def _fit_contract_for_request(
    request: dict,
    *,
    fit_completed_at: str = "2026-07-12T12:00:10.530865Z",
) -> dict:
    base_result, raw_capture = _base_fit_fixture_copy()
    observation = _observation()
    observation["attempt_id"] = request["request_hash"]
    observation["fit_started_at"] = _timestamp(8)
    observation["fit_completed_at"] = fit_completed_at
    result = build_alr_challenger_training_result_contract(
        base_result["admission"]["qualified_receipt_read"],
        training_contract=base_result["admission"]["training_contract"],
        observation=observation,
    )
    raw_capture["attempt_id"] = request["request_hash"]
    raw_capture["fit_started_at"] = observation["fit_started_at"]
    raw_capture["fit_completed_at"] = observation["fit_completed_at"]
    raw_capture["runner_identity"]["invocation_id"] = request["request_hash"]
    raw_capture["runner_identity"]["captured_at"] = _timestamp(22)
    contract = build_alr_challenger_fit_capture_attestation_contract(
        result,
        fit_capture=raw_capture,
    )
    assert validate_alr_challenger_fit_capture_attestation_contract(contract).valid
    return contract


def _success_payload(
    request: dict | None = None,
    *,
    fit_completed_at: str = "2026-07-12T12:00:10.530865Z",
) -> tuple[dict, dict, bytes]:
    if request is None:
        request = _request()[0]
    fit_contract = _fit_contract_for_request(
        request,
        fit_completed_at=fit_completed_at,
    )
    fit = fit_contract["fit_capture"]
    result = fit_contract["result_contract"]
    submitted = result["submitted_observation"]
    actual = fit["actual_training_inputs"]
    payload = _response_payload(REJECTED_PRE_FIT, request=request)
    for field in (
        "rejected_at",
        "failure_phase",
        "failure_code",
        "actual_inputs_consumed",
        "fit_started",
        "model_training_performed",
    ):
        payload.pop(field)
    payload["outcome"] = SUCCEEDED
    payload["v159_success_projection_allowed"] = True
    payload["fit_started_at"] = fit["fit_started_at"]
    payload["fit_completed_at"] = fit["fit_completed_at"]
    payload["captured_at"] = fit["runner_identity"]["captured_at"]

    expected = request["signed_payload"]["expected_training_inputs"]
    ordered_artifact_set_hash = fit["model_artifact_set_hash"]
    subject = {
        "durable_receipt_hash": expected["durable_receipt_hash"],
        "training_key_hash": expected["training_key_hash"],
        "result_hash": fit_contract["result_hash"],
        "fit_capture_hash": fit_contract["fit_capture_hash"],
        "candidate_attestation_hash": fit_contract["attestation_hash"],
        "training_run_hash": result["training_run_hash"],
        "challenger_hash": result["challenger_hash"],
        "runner_identity_hash": fit["runner_identity"]["runner_identity_hash"],
        "actual_input_material_set_hash": actual["material_set_hash"],
        "ordered_artifact_set_hash": ordered_artifact_set_hash,
    }
    claims = {
        "actual_inputs_consumed": True,
        "actual_fit_executed": True,
        "model_training_performed": True,
        "artifact_readback_completed": True,
        "onnx_semantic_validation_passed": True,
    }
    observation = {
        "source_head": actual["source_head"],
        "actual_inputs": {
            "dataset_hash": actual["actual_dataset_hash"],
            "row_ids_hash": actual["actual_row_ids_hash"],
            "split_hash": actual["actual_split_hash"],
            "code_manifest_hash": actual["actual_code_manifest_hash"],
            "training_config_hash": actual["actual_training_config_hash"],
            "feature_schema_hash": actual["actual_feature_schema_hash"],
            "label_schema_hash": actual["actual_label_schema_hash"],
            "training_rows": actual["actual_training_rows"],
        },
        "model": {
            "model_schema_version": submitted["model_schema_version"],
            "metrics_hash": submitted["metrics_hash"],
            "resource_usage_hash": submitted["resource_usage_hash"],
        },
        "fit_started_at": payload["fit_started_at"],
        "fit_completed_at": payload["fit_completed_at"],
        "artifacts": {
            item["quantile"]: {
                "artifact_hash": item["artifact_hash"],
                "artifact_size_bytes": item["artifact_size_bytes"],
            }
            for item in fit["artifact_readback"]
        },
    }
    inner = {
        "schema_version": "alr_fit_execution_signed_receipt_v1",
        "evidence_tier": "PLATFORM_OR_EXTERNAL_ATTESTED",
        "claim_kind": "ALR_FIT_EXECUTION_ATTESTATION_V1",
        "authentication_status": "SIGNATURE_VERIFIED_BY_TRUST_POLICY",
        "subject": copy.deepcopy(subject),
        "claims": copy.deepcopy(claims),
        "result_observation": copy.deepcopy(observation),
        "authentication": {
            "issuer_id": payload["issuer_id"],
            "trust_policy_id": payload["trust_policy_id"],
            "signature_key_id": payload["signing_key_id"],
            "signature_algorithm": "ed25519",
            "signature": _b64url(b"i" * 64),
        },
        "verified_at": payload["issuer_verified_at"],
        "expires_at": payload["receipt_expires_at"],
        "no_authority": copy.deepcopy(payload["no_authority"]),
        "authority_counters": copy.deepcopy(payload["authority_counters"]),
    }
    inner_bytes = canonical_v159_jsonb_text_bytes(inner)
    payload.update(
        {
            "v159_subject": subject,
            "v159_claims": claims,
            "result_observation": observation,
            "resource_observation": copy.deepcopy(
                submitted["resource_observation"]
            ),
            "actual_input_material_set_hash": subject[
                "actual_input_material_set_hash"
            ],
            "ordered_artifact_set_hash": ordered_artifact_set_hash,
            "fit_capture_contract": fit_contract,
            "inner_receipt_bytes_base64url": _b64url(inner_bytes),
            "inner_receipt_digest_sha256": hashlib.sha256(inner_bytes).hexdigest(),
        }
    )
    return payload, inner, inner_bytes


def test_outer_canonical_json_profile_is_frozen() -> None:
    value = {"z": [True, None, "é"], "a": {"bb": 2, "a": 1}}

    assert canonical_outer_json_bytes(value) == (
        b'{"a":{"a":1,"bb":2},"z":[true,null,"\\u00e9"]}'
    )


def test_outer_canonical_json_rejects_non_ascii_keys() -> None:
    with pytest.raises(ValueError, match=CANONICAL_BYTES_INVALID):
        canonical_outer_json_bytes({"é": 1})


@pytest.mark.parametrize(
    "raw",
    [
        b'{"a":1,"a":1}',
        b'{"b":2, "a":1}',
        b'{"a":NaN}',
        b'[]',
    ],
)
def test_outer_parser_rejects_duplicate_noncanonical_or_nonobject_bytes(
    raw: bytes,
) -> None:
    with pytest.raises(ValueError, match=CANONICAL_BYTES_INVALID):
        parse_canonical_outer_json(raw, max_bytes=1024)


def test_outer_parser_converts_deep_json_recursion_to_canonical_error() -> None:
    raw = b'{"a":' * 2_000 + b"0" + b"}" * 2_000
    with pytest.raises(ValueError, match=CANONICAL_BYTES_INVALID):
        parse_canonical_outer_json(raw, max_bytes=len(raw))


def test_strict_base64url_rejects_padding_whitespace_and_wrong_decoded_size() -> None:
    encoded = _b64url(b"x" * 64)
    assert len(encoded) == 86
    assert strict_base64url_decode(encoded, expected_bytes=64, max_bytes=64) == b"x" * 64

    for mutated in (encoded + "=", encoded + "\n", encoded[:-1] + "+", _b64url(b"x" * 63)):
        with pytest.raises(ValueError, match=CANONICAL_BYTES_INVALID):
            strict_base64url_decode(mutated, expected_bytes=64, max_bytes=64)


def test_three_signature_preimages_are_domain_separated_and_length_bound() -> None:
    payload = {"schema_version": "fixture_v1", "value": 7}
    request = request_signature_preimage(payload)
    terminal = terminal_receipt_signature_preimage(payload)
    inner = v159_inner_signature_preimage(
        {
            "schema_version": "alr_fit_execution_signed_receipt_v1",
            "authentication": {
                "issuer_id": "issuer.test",
                "trust_policy_id": "policy.test",
                "signature_key_id": "key.test",
                "signature_algorithm": "ed25519",
                "signature": _b64url(b"s" * 64),
            },
        }
    )

    assert request.startswith(REQUEST_SIGNATURE_DOMAIN + b"\x00")
    assert terminal.startswith(TERMINAL_RECEIPT_SIGNATURE_DOMAIN + b"\x00")
    assert inner.startswith(V159_INNER_SIGNATURE_DOMAIN + b"\x00")
    assert len({request, terminal, inner}) == 3

    payload_bytes = canonical_outer_json_bytes(payload)
    offset = len(REQUEST_SIGNATURE_DOMAIN) + 1
    assert int.from_bytes(request[offset : offset + 8], "big") == len(payload_bytes)
    assert request[offset + 8 :] == payload_bytes


def test_domain_hash_uses_the_frozen_handshake_namespace() -> None:
    payload = {"b": 2, "a": 1}
    canonical = b'{"a":1,"b":2}'
    expected = hashlib.sha256(
        b"alr_trusted_fit_handshake_v1\x00"
        + b"fixture"
        + b"\x00"
        + len(canonical).to_bytes(8, "big")
        + canonical
    ).hexdigest()

    assert domain_hash("fixture", payload) == expected
    assert domain_hash("fixture.changed", payload) != expected


def test_signature_preimage_snapshots_input_before_serializing() -> None:
    payload = {"schema_version": "fixture_v1", "nested": {"value": 1}}
    original = copy.deepcopy(payload)
    preimage = request_signature_preimage(payload)
    payload["nested"]["value"] = 2

    assert preimage == request_signature_preimage(original)
    assert preimage != request_signature_preimage(payload)


def test_canonicalizer_rejects_raw_bytes_nonfinite_and_non_string_keys() -> None:
    for value in (
        {"raw": b"secret"},
        {"nan": float("nan")},
        {1: "not-a-string-key"},
    ):
        with pytest.raises((TypeError, ValueError)):
            canonical_outer_json_bytes(value)


def test_outer_parser_round_trip_preserves_exact_scalar_types() -> None:
    value = {"false": False, "integer": 1, "string": "1"}
    raw = canonical_outer_json_bytes(value)

    parsed = parse_canonical_outer_json(raw, max_bytes=len(raw))

    assert parsed == value
    assert type(parsed["false"]) is bool
    assert type(parsed["integer"]) is int
    assert type(parsed["string"]) is str
    assert json.loads(raw) == value


def test_request_builder_binds_identity_policy_resources_and_zero_authority() -> None:
    request, policy, _key = _request()
    payload = request["signed_payload"]

    assert request["request_hash"] == domain_hash("request_signed_payload", payload)
    assert request["attempt_id"] == request["request_hash"]
    assert request["invocation_id"] == request["request_hash"]
    assert payload["nonce_digest"] == hashlib.sha256(
        b"alr_trusted_fit_handshake_v1\x00nonce\x00" + bytes.fromhex("ab" * 32)
    ).hexdigest()
    assert payload["trust_policy_snapshot_digest"] == domain_hash(
        "trust_policy_snapshot", policy
    )
    assert payload["allowed_signing_key_set_digest"] == domain_hash(
        "allowed_key_set", policy["allowed_keys"]
    )
    assert payload["execution_contract_hash"] == domain_hash(
        "execution_contract", payload["execution_contract"]
    )
    assert payload["resource_budget_hash"] == domain_hash(
        "resource_budget", payload["resource_budget"]
    )
    assert payload["runner_target_policy_hash"] == domain_hash(
        "runner_target_policy", payload["runner_target_policy"]
    )
    assert payload["admission"]["qualified_receipt_binding_hash"] == (
        _result_contract_domain_hash(
            "qualified_receipt_read",
            payload["admission"]["qualified_receipt_read"],
        )
    )
    assert payload["admission"]["training_contract_hash"] == payload[
        "admission"
    ]["training_contract"]["contract_hash"]
    assert request["dispatch_allowed"] is False
    assert request["training_allowed"] is False
    assert request["persistence_allowed"] is False
    assert all(value is False for value in request["no_authority"].values())
    assert all(type(value) is int and value == 0 for value in request["authority_counters"].values())

    validation = validate_trusted_fit_execution_request(request)
    assert validation.valid is True
    assert validation.verdict == VALID
    assert validation.request_hash == request["request_hash"]


@pytest.mark.parametrize(
    ("mutator", "reason"),
    [
        (lambda value: value.update({"unknown": True}), "request_fields_invalid"),
        (
            lambda value: value["signed_payload"].update({"request_generation": True}),
            "request_generation_invalid",
        ),
        (lambda value: value.update({"attempt_id": _h("wrong")}), "request_identity_mismatch"),
        (
            lambda value: value["signed_payload"]["resource_budget"].update(
                {"max_external_requests": 1}
            ),
            "resource_budget_invalid",
        ),
        (
            lambda value: value["no_authority"].update({"trading_authority": True}),
            "no_authority_invalid",
        ),
        (
            lambda value: value["authentication"].update(
                {"signature": value["authentication"]["signature"] + "="}
            ),
            "signature_invalid",
        ),
    ],
)
def test_request_validation_bites_structural_and_identity_mutations(
    mutator,
    reason: str,
) -> None:
    request, _policy, _key = _request()
    mutated = copy.deepcopy(request)
    mutator(mutated)

    validation = validate_trusted_fit_execution_request(mutated)

    assert validation.valid is False
    assert validation.verdict == INVALID
    assert reason in validation.reasons


def test_request_rejects_forged_qualified_receipt_binding() -> None:
    request, _policy, _key = _request()
    payload = request["signed_payload"]
    payload["admission"]["qualified_receipt_binding_hash"] = _h("forged-binding")
    request_hash = domain_hash("request_signed_payload", payload)
    request["request_hash"] = request_hash
    request["attempt_id"] = request_hash
    request["invocation_id"] = request_hash

    validation = validate_trusted_fit_execution_request(request)

    assert validation.valid is False
    assert "qualified_receipt_binding_hash_mismatch" in validation.reasons


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_wall_seconds", 120.0),
        ("max_cpu_seconds", 90.0),
        ("max_memory_bytes", 100_000_000.0),
        ("max_artifact_bytes", 100_000.0),
        ("max_training_rows", 1_000.0),
        ("max_external_requests", -0.0),
        ("max_api_cost_usd", -0.0),
    ],
)
def test_resource_budget_rejects_float_encodings(field: str, value: float) -> None:
    request, _policy, _key = _request()
    payload = request["signed_payload"]
    payload["resource_budget"][field] = value
    payload["resource_budget_hash"] = domain_hash(
        "resource_budget", payload["resource_budget"]
    )
    request_hash = domain_hash("request_signed_payload", payload)
    request["request_hash"] = request_hash
    request["attempt_id"] = request_hash
    request["invocation_id"] = request_hash

    validation = validate_trusted_fit_execution_request(request)

    assert validation.valid is False
    assert "resource_budget_invalid" in validation.reasons


def test_request_builders_snapshot_mutable_inputs() -> None:
    request, policy, _key = _request()
    frozen = canonical_outer_json_bytes(request)
    policy["allowed_keys"][0]["key_id"] = "mutated"

    assert canonical_outer_json_bytes(request) == frozen


def test_request_replay_is_exact_and_conflicts_fail_closed() -> None:
    request, _policy, _key = _request()
    exact = copy.deepcopy(request)
    divergent_nonce = copy.deepcopy(request)
    divergent_nonce["signed_payload"]["requester_id"] = "alr.other.test"
    divergent_nonce["request_hash"] = domain_hash(
        "request_signed_payload", divergent_nonce["signed_payload"]
    )
    divergent_nonce["attempt_id"] = divergent_nonce["request_hash"]
    divergent_nonce["invocation_id"] = divergent_nonce["request_hash"]
    other_request = copy.deepcopy(request)
    other_request["signed_payload"]["request_nonce"] = "cd" * 32
    other_request["signed_payload"]["nonce_digest"] = hashlib.sha256(
        b"alr_trusted_fit_handshake_v1\x00nonce\x00" + bytes.fromhex("cd" * 32)
    ).hexdigest()
    other_request["signed_payload"]["request_generation"] = 4
    other_request["request_hash"] = domain_hash(
        "request_signed_payload", other_request["signed_payload"]
    )
    other_request["attempt_id"] = other_request["request_hash"]
    other_request["invocation_id"] = other_request["request_hash"]

    assert classify_request_replay(request, exact) == EXACT_REPLAY
    assert classify_request_replay(request, divergent_nonce) == NONCE_REPLAY_CONFLICT
    assert classify_request_replay(request, other_request) == DURABLE_CONSUMPTION_CONFLICT

    alternate_envelope = copy.deepcopy(other_request)
    admission = alternate_envelope["signed_payload"]["admission"]
    admission["qualified_receipt_read"]["receipt"]["created_at"] = (
        "2026-07-12T11:59:59+00:00"
    )
    admission["qualified_receipt_binding_hash"] = _result_contract_domain_hash(
        "qualified_receipt_read",
        admission["qualified_receipt_read"],
    )
    alternate_hash = domain_hash(
        "request_signed_payload", alternate_envelope["signed_payload"]
    )
    alternate_envelope["request_hash"] = alternate_hash
    alternate_envelope["attempt_id"] = alternate_hash
    alternate_envelope["invocation_id"] = alternate_hash
    assert validate_trusted_fit_execution_request(alternate_envelope).valid
    assert (
        classify_request_replay(request, alternate_envelope)
        == DURABLE_CONSUMPTION_CONFLICT
    )



def test_key_status_overlay_intersects_pinned_policy_and_current_time() -> None:
    request, policy, key = _request()
    overlay = build_key_status_overlay(
        key_entry=key,
        trust_policy_snapshot_digest=request["signed_payload"][
            "trust_policy_snapshot_digest"
        ],
        status=ACTIVE,
        observed_at=_timestamp(2),
        valid_until=_timestamp(40),
        provider_evidence_digest=_h("provider-evidence"),
    )

    accepted = validate_key_status_overlay(
        overlay,
        trust_policy_snapshot=policy,
        adjudicated_at=_timestamp(20),
        for_new_signature=True,
    )
    assert accepted.valid is True
    assert accepted.verdict == VALID

    stale = copy.deepcopy(overlay)
    stale["valid_until"] = _timestamp(19)
    stale["overlay_digest"] = domain_hash(
        "key_status_overlay", {key: value for key, value in stale.items() if key != "overlay_digest"}
    )
    assert validate_key_status_overlay(
        stale,
        trust_policy_snapshot=policy,
        adjudicated_at=_timestamp(20),
        for_new_signature=True,
    ).valid is False


def test_retired_key_is_verification_only_and_policy_bounded() -> None:
    request, policy, key = _request()
    overlay = build_key_status_overlay(
        key_entry=key,
        trust_policy_snapshot_digest=request["signed_payload"][
            "trust_policy_snapshot_digest"
        ],
        status=RETIRED,
        observed_at=_timestamp(2),
        valid_until=_timestamp(40),
        provider_evidence_digest=_h("provider-evidence"),
    )

    assert validate_key_status_overlay(
        overlay,
        trust_policy_snapshot=policy,
        adjudicated_at=_timestamp(20),
        for_new_signature=False,
    ).valid is True
    assert validate_key_status_overlay(
        overlay,
        trust_policy_snapshot=policy,
        adjudicated_at=_timestamp(20),
        for_new_signature=True,
    ).valid is False

    disallow = copy.deepcopy(policy)
    disallow["retired_key_verification_allowed"] = False
    assert validate_key_status_overlay(
        overlay,
        trust_policy_snapshot=disallow,
        adjudicated_at=_timestamp(20),
        for_new_signature=False,
    ).valid is False


def test_handshake_signing_key_usage_is_explicit_and_closed() -> None:
    request, _policy, key = _request()
    assert key["usage"] == "ALR_TRUSTED_FIT_HANDSHAKE_SIGNING"
    overlay = build_key_status_overlay(
        key_entry=key,
        trust_policy_snapshot_digest=request["signed_payload"][
            "trust_policy_snapshot_digest"
        ],
        status=ACTIVE,
        observed_at=_timestamp(2),
        valid_until=_timestamp(40),
        provider_evidence_digest=_h("provider-evidence"),
    )
    assert overlay["usage"] == "ALR_TRUSTED_FIT_HANDSHAKE_SIGNING"

    wrong = copy.deepcopy(key)
    wrong["usage"] = "UNRELATED_SIGNING"
    with pytest.raises(ValueError, match="key_usage_invalid"):
        build_trust_policy_snapshot(
            policy_id="policy.test",
            epoch=11,
            audience="alr.fit.runner.test",
            allowed_keys=[wrong],
            retired_key_verification_allowed=True,
        )


def test_overlay_rejects_non_digest_provider_evidence_even_if_self_hash_matches() -> None:
    request, policy, key = _request()
    overlay = build_key_status_overlay(
        key_entry=key,
        trust_policy_snapshot_digest=request["signed_payload"][
            "trust_policy_snapshot_digest"
        ],
        status=ACTIVE,
        observed_at=_timestamp(2),
        valid_until=_timestamp(40),
        provider_evidence_digest=_h("provider-evidence"),
    )
    overlay["provider_evidence_digest"] = {"forged": True}
    overlay["overlay_digest"] = domain_hash(
        "key_status_overlay",
        {key: value for key, value in overlay.items() if key != "overlay_digest"},
    )

    validation = validate_key_status_overlay(
        overlay,
        trust_policy_snapshot=policy,
        adjudicated_at=_timestamp(20),
        for_new_signature=False,
    )

    assert validation.valid is False
    assert "provider_evidence_digest_invalid" in validation.reasons


def test_verifier_binds_overlay_to_the_request_signing_key() -> None:
    first = _key_entry()
    second = _key_entry(
        generation=8,
        key_id="issuer.test.key-8",
        byte_offset=32,
    )
    request, policy, selected = _request(allowed_keys=[first, second])
    assert selected["key_id"] == first["key_id"]
    response = build_isolated_fit_execution_response(
        _response_payload(REJECTED_PRE_FIT, request=request),
        signature=_b64url(b"t" * 64),
    )
    wrong_overlay = build_key_status_overlay(
        key_entry=second,
        trust_policy_snapshot_digest=request["signed_payload"][
            "trust_policy_snapshot_digest"
        ],
        status=ACTIVE,
        observed_at=_timestamp(2),
        valid_until=_timestamp(40),
        provider_evidence_digest=_h("provider-evidence"),
    )

    result = verify_isolated_fit_response(
        canonical_outer_json_bytes(request),
        canonical_outer_json_bytes(response),
        expected_audience="alr.fit.runner.test",
        adjudicated_at=_timestamp(30),
        key_status_overlay=wrong_overlay,
        synthetic_signature_verifier=_synthetic_signature_verifier,
    )

    assert result.valid is False
    assert result.code == POLICY_OR_KEY_REJECTED
    assert "overlay_request_key_mismatch" in result.reasons


def test_overlay_generation_rejects_bool_even_when_policy_generation_is_one() -> None:
    key = _key_entry(generation=1)
    request, policy, _selected = _request(allowed_keys=[key])
    overlay = build_key_status_overlay(
        key_entry=key,
        trust_policy_snapshot_digest=request["signed_payload"][
            "trust_policy_snapshot_digest"
        ],
        status=ACTIVE,
        observed_at=_timestamp(2),
        valid_until=_timestamp(40),
        provider_evidence_digest=_h("provider-evidence"),
    )
    overlay["generation"] = True
    overlay["overlay_digest"] = domain_hash(
        "key_status_overlay",
        {key: value for key, value in overlay.items() if key != "overlay_digest"},
    )

    validation = validate_key_status_overlay(
        overlay,
        trust_policy_snapshot=policy,
        adjudicated_at=_timestamp(20),
        for_new_signature=False,
    )

    assert validation.valid is False
    assert "overlay_key_mismatch" in validation.reasons


def test_verifier_rejects_retired_key_without_authenticated_effective_cutoff() -> None:
    request, policy, key = _request()
    response = build_isolated_fit_execution_response(
        _response_payload(REJECTED_PRE_FIT),
        signature=_b64url(b"t" * 64),
    )
    retired = build_key_status_overlay(
        key_entry=key,
        trust_policy_snapshot_digest=request["signed_payload"][
            "trust_policy_snapshot_digest"
        ],
        status=RETIRED,
        observed_at=_timestamp(10),
        valid_until=_timestamp(40),
        provider_evidence_digest=_h("provider-evidence"),
    )

    result = verify_isolated_fit_response(
        canonical_outer_json_bytes(request),
        canonical_outer_json_bytes(response),
        expected_audience="alr.fit.runner.test",
        adjudicated_at=_timestamp(30),
        key_status_overlay=retired,
        synthetic_signature_verifier=_synthetic_signature_verifier,
    )

    assert result.valid is False
    assert result.code == POLICY_OR_KEY_REJECTED
    assert "retired_key_effective_time_unavailable" in result.reasons


def test_verifier_uses_one_overlay_snapshot_without_status_toctou() -> None:
    request, policy, key = _request()
    response = build_isolated_fit_execution_response(
        _response_payload(REJECTED_PRE_FIT),
        signature=_b64url(b"t" * 64),
    )
    retired = build_key_status_overlay(
        key_entry=key,
        trust_policy_snapshot_digest=request["signed_payload"][
            "trust_policy_snapshot_digest"
        ],
        status=RETIRED,
        observed_at=_timestamp(10),
        valid_until=_timestamp(40),
        provider_evidence_digest=_h("provider-evidence"),
    )
    deceptive = _RetiredAsActiveOverlay(retired)
    assert validate_key_status_overlay(
        deceptive,
        trust_policy_snapshot=policy,
        adjudicated_at=_timestamp(30),
        for_new_signature=False,
    ).valid

    result = verify_isolated_fit_response(
        canonical_outer_json_bytes(request),
        canonical_outer_json_bytes(response),
        expected_audience="alr.fit.runner.test",
        adjudicated_at=_timestamp(30),
        key_status_overlay=deceptive,
        synthetic_signature_verifier=_synthetic_signature_verifier,
    )

    assert result.valid is False
    assert result.code == POLICY_OR_KEY_REJECTED
    assert "retired_key_effective_time_unavailable" in result.reasons


@pytest.mark.parametrize(
    "outcome",
    [ACCEPTED_IN_PROGRESS, REJECTED_PRE_FIT, FAILED_AFTER_START],
)
def test_response_union_accepts_only_closed_status_and_terminal_branches(
    outcome: str,
) -> None:
    payload = _response_payload(outcome)
    response = build_isolated_fit_execution_response(
        payload,
        signature=_b64url(b"t" * 64),
    )

    validation = validate_isolated_fit_execution_response(response)

    assert validation.valid is True
    assert validation.verdict == VALID
    assert response["response_kind"] == payload["response_kind"]
    assert response["outcome"] == outcome


@pytest.mark.parametrize(
    ("outcome", "mutator", "reason"),
    [
        (
            ACCEPTED_IN_PROGRESS,
            lambda value: value.update({"response_kind": TERMINAL}),
            "response_kind_outcome_mismatch",
        ),
        (
            ACCEPTED_IN_PROGRESS,
            lambda value: value["stage_observations"].update({"fit_completed": True}),
            "stage_observations_nonmonotonic",
        ),
        (
            REJECTED_PRE_FIT,
            lambda value: value.update({"fit_started": True}),
            "rejected_pre_fit_claims_invalid",
        ),
        (
            FAILED_AFTER_START,
            lambda value: value.update(
                {"inner_receipt_bytes_base64url": _b64url(b"{}")}
            ),
            "failed_after_start_v159_projection_invalid",
        ),
        (
            FAILED_AFTER_START,
            lambda value: value.update({"automatic_retry_allowed": True}),
            "automatic_retry_invalid",
        ),
        (
            FAILED_AFTER_START,
            lambda value: value.update({"fit_completed_at": _timestamp(20)}),
            "failed_after_start_stage_evidence_mismatch",
        ),
        (
            FAILED_AFTER_START,
            lambda value: value["stage_observations"].update(
                {"fit_completed": True}
            ),
            "failed_after_start_stage_evidence_mismatch",
        ),
        (
            FAILED_AFTER_START,
            lambda value: value.update({"result_observation": {"partial": True}}),
            "failed_after_start_result_observation_invalid",
        ),
        (
            FAILED_AFTER_START,
            lambda value: value.update({"failure_phase": "ONNX_VALIDATION"}),
            "failed_after_start_failure_pair_invalid",
        ),
        (
            FAILED_AFTER_START,
            lambda value: value.update(
                {
                    "failure_phase": "ARTIFACT_READBACK",
                    "failure_code": "ARTIFACT_READBACK_FAILED",
                }
            ),
            "failed_after_start_stage_evidence_mismatch",
        ),
        (
            REJECTED_PRE_FIT,
            lambda value: value.update({"unknown": 1}),
            "response_payload_fields_invalid",
        ),
    ],
)
def test_response_union_mutation_bites_branch_exclusivity(
    outcome: str,
    mutator,
    reason: str,
) -> None:
    payload = _response_payload(outcome)
    mutator(payload)
    response = {
        "schema_version": "alr_isolated_fit_execution_receipt_v1",
        "response_kind": payload["response_kind"],
        "outcome": payload["outcome"],
        "signed_payload": payload,
        "authentication": {
            "algorithm": "ed25519",
            "key_id": payload["signing_key_id"],
            "signature": _b64url(b"t" * 64),
        },
        "no_authority": copy.deepcopy(payload["no_authority"]),
        "authority_counters": copy.deepcopy(payload["authority_counters"]),
    }

    validation = validate_isolated_fit_execution_response(response)

    assert validation.valid is False
    assert reason in validation.reasons


def test_response_request_binding_rejects_wrong_attempt_or_invocation() -> None:
    request, _policy, _key = _request()
    payload = _response_payload(REJECTED_PRE_FIT)
    payload["attempt_id"] = _h("wrong")
    payload["actual_runner_identity"]["invocation_id"] = _h("wrong")

    response = {
        "schema_version": "alr_isolated_fit_execution_receipt_v1",
        "response_kind": payload["response_kind"],
        "outcome": payload["outcome"],
        "signed_payload": payload,
        "authentication": {
            "algorithm": "ed25519",
            "key_id": payload["signing_key_id"],
            "signature": _b64url(b"t" * 64),
        },
        "no_authority": copy.deepcopy(payload["no_authority"]),
        "authority_counters": copy.deepcopy(payload["authority_counters"]),
    }
    validation = validate_isolated_fit_execution_response(
        response,
        request=request,
    )

    assert validation.valid is False
    assert "receipt_request_binding_mismatch" in validation.reasons


def test_succeeded_response_binds_byte_exact_v159_inner_projection() -> None:
    payload, inner, inner_bytes = _success_payload()
    response = build_isolated_fit_execution_response(
        payload,
        signature=_b64url(b"t" * 64),
    )

    validation = validate_isolated_fit_execution_response(response)

    assert validation.valid is True
    assert parse_canonical_v159_jsonb_text_bytes(
        inner_bytes,
        max_bytes=1_048_576,
    ) == inner
    assert v159_inner_signature_preimage(inner).startswith(
        V159_INNER_SIGNATURE_DOMAIN + b"\x00"
    )


@pytest.mark.parametrize(
    ("mutator", "reason"),
    [
        (
            lambda payload, inner: payload["v159_subject"].update(
                {"result_hash": _h("wrong")}
            ),
            "v159_inner_receipt_mismatch",
        ),
        (
            lambda payload, inner: payload["v159_claims"].update(
                {"model_training_performed": False}
            ),
            "execution_claim_mismatch",
        ),
        (
            lambda payload, inner: inner["authentication"].update(
                {"signature": inner["authentication"]["signature"] + "="}
            ),
            "v159_inner_signature_invalid",
        ),
        (
            lambda payload, inner: inner["no_authority"].update(
                {"trading_authority": True}
            ),
            "authority_mismatch",
        ),
        (
            lambda payload, inner: payload.update(
                {"ordered_artifact_set_hash": _h("wrong-order")}
            ),
            "v159_inner_receipt_mismatch",
        ),
    ],
)
def test_succeeded_response_mutation_bites_inner_outer_equality(
    mutator,
    reason: str,
) -> None:
    payload, inner, _inner_bytes = _success_payload()
    mutator(payload, inner)
    if inner != parse_canonical_v159_jsonb_text_bytes(
        strict_base64url_decode(
            payload["inner_receipt_bytes_base64url"],
            max_bytes=1_048_576,
        ),
        max_bytes=1_048_576,
    ):
        inner_bytes = canonical_v159_jsonb_text_bytes(inner)
        payload["inner_receipt_bytes_base64url"] = _b64url(inner_bytes)
        payload["inner_receipt_digest_sha256"] = hashlib.sha256(inner_bytes).hexdigest()
    response = {
        "schema_version": "alr_isolated_fit_execution_receipt_v1",
        "response_kind": TERMINAL,
        "outcome": SUCCEEDED,
        "signed_payload": payload,
        "authentication": {
            "algorithm": "ed25519",
            "key_id": payload["signing_key_id"],
            "signature": _b64url(b"t" * 64),
        },
        "no_authority": copy.deepcopy(payload["no_authority"]),
        "authority_counters": copy.deepcopy(payload["authority_counters"]),
    }

    validation = validate_isolated_fit_execution_response(response)

    assert validation.valid is False
    assert reason in validation.reasons


def test_success_rejects_self_consistent_hashes_not_backed_by_fit_contract() -> None:
    payload, inner, _raw = _success_payload()
    forged = _h("self-consistent-but-unbacked-result")
    payload["v159_subject"]["result_hash"] = forged
    inner["subject"]["result_hash"] = forged
    inner_bytes = canonical_v159_jsonb_text_bytes(inner)
    payload["inner_receipt_bytes_base64url"] = _b64url(inner_bytes)
    payload["inner_receipt_digest_sha256"] = hashlib.sha256(inner_bytes).hexdigest()
    response = {
        "schema_version": "alr_isolated_fit_execution_receipt_v1",
        "response_kind": TERMINAL,
        "outcome": SUCCEEDED,
        "signed_payload": payload,
        "authentication": {
            "algorithm": "ed25519",
            "key_id": payload["signing_key_id"],
            "signature": _b64url(b"t" * 64),
        },
        "no_authority": copy.deepcopy(payload["no_authority"]),
        "authority_counters": copy.deepcopy(payload["authority_counters"]),
    }

    validation = validate_isolated_fit_execution_response(response)

    assert validation.valid is False
    assert "fit_capture_contract_binding_mismatch" in validation.reasons


def test_success_fit_elapsed_time_must_fit_signed_wall_budget() -> None:
    request = _request()[0]
    payload, _inner, _raw = _success_payload(
        request,
        fit_completed_at=_timestamp(20),
    )
    assert payload["resource_observation"]["wall_time_microseconds"] == 2_530_865

    with pytest.raises(ValueError, match="resource_wall_time_mismatch"):
        build_isolated_fit_execution_response(
            payload,
            signature=_b64url(b"t" * 64),
        )


def test_v159_jsonb_parser_rejects_semantically_equal_noncanonical_bytes() -> None:
    _payload, _inner, inner_bytes = _success_payload()
    mutated = inner_bytes.replace(b'": ', b'":', 1)

    with pytest.raises(ValueError, match=CANONICAL_BYTES_INVALID):
        parse_canonical_v159_jsonb_text_bytes(mutated, max_bytes=1_048_576)


def _overlay_for(request: dict, policy: dict, key: dict) -> dict:
    return build_key_status_overlay(
        key_entry=key,
        trust_policy_snapshot_digest=request["signed_payload"][
            "trust_policy_snapshot_digest"
        ],
        status=ACTIVE,
        observed_at=_timestamp(2),
        valid_until=_timestamp(40),
        provider_evidence_digest=_h("provider-evidence"),
    )


def _synthetic_signature_verifier(
    label: str,
    public_key: bytes,
    signature: bytes,
    preimage: bytes,
) -> bool:
    expected_signatures = {
        "request": b"r" * 64,
        "terminal": b"t" * 64,
        "v159_inner": b"i" * 64,
    }
    expected_domains = {
        "request": REQUEST_SIGNATURE_DOMAIN,
        "terminal": TERMINAL_RECEIPT_SIGNATURE_DOMAIN,
        "v159_inner": V159_INNER_SIGNATURE_DOMAIN,
    }
    return (
        public_key == bytes(range(32))
        and signature == expected_signatures[label]
        and preimage.startswith(expected_domains[label] + b"\x00")
    )


def test_raw_request_interface_preserves_canonical_and_duplicate_key_evidence() -> None:
    request, _policy, _key = _request()
    raw = canonical_outer_json_bytes(request)

    assert validate_trusted_fit_request_bytes(raw).valid is True
    assert validate_trusted_fit_request_bytes(b'{"a":1,"a":1}').valid is False
    assert validate_trusted_fit_request_bytes(raw.replace(b'":', b'": ', 1)).valid is False


@pytest.mark.parametrize("outcome", [REJECTED_PRE_FIT, FAILED_AFTER_START, SUCCEEDED])
def test_synthetic_pure_verifier_is_permanently_capped_below_production_trust(
    outcome: str,
) -> None:
    request, policy, key = _request()
    payload = _success_payload()[0] if outcome == SUCCEEDED else _response_payload(outcome)
    response = build_isolated_fit_execution_response(
        payload,
        signature=_b64url(b"t" * 64),
    )

    result = verify_isolated_fit_response(
        canonical_outer_json_bytes(request),
        canonical_outer_json_bytes(response),
        expected_audience="alr.fit.runner.test",
        adjudicated_at=_timestamp(30),
        key_status_overlay=_overlay_for(request, policy, key),
        synthetic_signature_verifier=_synthetic_signature_verifier,
    )

    assert result.valid is True
    assert result.code == DURABLE_CONSUMPTION_REQUIRED
    assert result.verdict == EXTERNAL_HOST_UNCHECKED
    assert result.verdict != AUTHENTICATED_UNCONSUMED
    assert result.fixture_signatures_matched is True
    assert result.signatures_valid is False
    assert result.capability_authenticity == EXTERNAL_HOST_UNCHECKED
    assert result.persistence_allowed is False
    assert result.authority_granted is False
    assert result.model_training_performed_claim == "NOT_ESTABLISHED"
    assert result.durable_consumption_required is False


def test_backend_absence_fails_closed_instead_of_trusting_overlay_labels() -> None:
    request, policy, key = _request()
    response = build_isolated_fit_execution_response(
        _response_payload(REJECTED_PRE_FIT),
        signature=_b64url(b"t" * 64),
    )

    result = verify_isolated_fit_response(
        canonical_outer_json_bytes(request),
        canonical_outer_json_bytes(response),
        expected_audience="alr.fit.runner.test",
        adjudicated_at=_timestamp(30),
        key_status_overlay=_overlay_for(request, policy, key),
        synthetic_signature_verifier=None,
    )

    assert result.valid is False
    assert result.code == POLICY_OR_KEY_REJECTED
    assert result.verdict == EXTERNAL_HOST_UNCHECKED
    assert result.signatures_valid is False


def test_request_and_terminal_signature_mutations_map_to_distinct_codes() -> None:
    request, policy, key = _request()
    response = build_isolated_fit_execution_response(
        _response_payload(REJECTED_PRE_FIT),
        signature=_b64url(b"t" * 64),
    )
    overlay = _overlay_for(request, policy, key)

    bad_request = copy.deepcopy(request)
    bad_request["authentication"]["signature"] = _b64url(b"x" * 64)
    request_result = verify_isolated_fit_response(
        canonical_outer_json_bytes(bad_request),
        canonical_outer_json_bytes(response),
        expected_audience="alr.fit.runner.test",
        adjudicated_at=_timestamp(30),
        key_status_overlay=overlay,
        synthetic_signature_verifier=_synthetic_signature_verifier,
    )
    assert request_result.code == REQUEST_SIGNATURE_INVALID

    bad_response = copy.deepcopy(response)
    bad_response["authentication"]["signature"] = _b64url(b"x" * 64)
    response_result = verify_isolated_fit_response(
        canonical_outer_json_bytes(request),
        canonical_outer_json_bytes(bad_response),
        expected_audience="alr.fit.runner.test",
        adjudicated_at=_timestamp(30),
        key_status_overlay=overlay,
        synthetic_signature_verifier=_synthetic_signature_verifier,
    )
    assert response_result.code == RECEIPT_SIGNATURE_INVALID
    assert response_result.fixture_signatures_matched is False


def test_malformed_request_signature_maps_to_request_signature_invalid() -> None:
    request, policy, key = _request()
    request["authentication"]["signature"] = "malformed"

    result = verify_isolated_fit_response(
        canonical_outer_json_bytes(request),
        None,
        expected_audience="alr.fit.runner.test",
        adjudicated_at=_timestamp(30),
        key_status_overlay=_overlay_for(request, policy, key),
        synthetic_signature_verifier=_synthetic_signature_verifier,
    )

    assert result.code == REQUEST_SIGNATURE_INVALID


def test_invalid_expected_audience_maps_to_audience_mismatch() -> None:
    request, policy, key = _request()

    result = verify_isolated_fit_response(
        canonical_outer_json_bytes(request),
        None,
        expected_audience="INVALID AUDIENCE",
        adjudicated_at=_timestamp(30),
        key_status_overlay=_overlay_for(request, policy, key),
        synthetic_signature_verifier=_synthetic_signature_verifier,
    )

    assert result.code == AUDIENCE_MISMATCH


def test_request_signature_precedes_audience_semantics() -> None:
    request, policy, key = _request()
    request["authentication"]["signature"] = _b64url(b"x" * 64)

    result = verify_isolated_fit_response(
        canonical_outer_json_bytes(request),
        None,
        expected_audience="other.audience",
        adjudicated_at=_timestamp(30),
        key_status_overlay=_overlay_for(request, policy, key),
        synthetic_signature_verifier=_synthetic_signature_verifier,
    )

    assert result.code == REQUEST_SIGNATURE_INVALID


def test_outer_signature_precedes_runner_binding_semantics() -> None:
    request, policy, key = _request()
    payload = _response_payload(REJECTED_PRE_FIT)
    payload["actual_runner_identity"]["measurement_hash"] = _h(
        "wrong-measurement"
    )
    unsigned = copy.deepcopy(payload["actual_runner_identity"])
    unsigned.pop("runner_identity_hash")
    payload["actual_runner_identity"]["runner_identity_hash"] = domain_hash(
        "actual_runner_identity", unsigned
    )
    response = build_isolated_fit_execution_response(
        payload,
        signature=_b64url(b"x" * 64),
    )

    result = verify_isolated_fit_response(
        canonical_outer_json_bytes(request),
        canonical_outer_json_bytes(response),
        expected_audience="alr.fit.runner.test",
        adjudicated_at=_timestamp(30),
        key_status_overlay=_overlay_for(request, policy, key),
        synthetic_signature_verifier=_synthetic_signature_verifier,
    )

    assert result.code == RECEIPT_SIGNATURE_INVALID


def test_response_time_precedes_authority_in_public_failure_code() -> None:
    request, policy, key = _request()
    response = build_isolated_fit_execution_response(
        _response_payload(ACCEPTED_IN_PROGRESS),
        signature=_b64url(b"t" * 64),
    )
    response["signed_payload"]["status_expires_at"] = _timestamp(5)
    response["signed_payload"]["no_authority"]["trading_authority"] = True
    response["no_authority"]["trading_authority"] = True

    result = verify_isolated_fit_response(
        canonical_outer_json_bytes(request),
        canonical_outer_json_bytes(response),
        expected_audience="alr.fit.runner.test",
        adjudicated_at=_timestamp(4),
        key_status_overlay=_overlay_for(request, policy, key),
        synthetic_signature_verifier=_synthetic_signature_verifier,
    )

    assert result.code == "RECEIPT_TIME_INVALID"


def test_cross_request_time_precedes_authority_in_public_failure_code() -> None:
    request, policy, key = _request()
    response = build_isolated_fit_execution_response(
        _response_payload(REJECTED_PRE_FIT),
        signature=_b64url(b"t" * 64),
    )
    response["signed_payload"]["no_authority"]["trading_authority"] = True
    response["no_authority"]["trading_authority"] = True
    overlay = build_key_status_overlay(
        key_entry=key,
        trust_policy_snapshot_digest=request["signed_payload"][
            "trust_policy_snapshot_digest"
        ],
        status=ACTIVE,
        observed_at=_timestamp(2),
        valid_until=_timestamp(50),
        provider_evidence_digest=_h("provider-evidence"),
    )

    result = verify_isolated_fit_response(
        canonical_outer_json_bytes(request),
        canonical_outer_json_bytes(response),
        expected_audience="alr.fit.runner.test",
        adjudicated_at=_timestamp(46),
        key_status_overlay=overlay,
        synthetic_signature_verifier=_synthetic_signature_verifier,
    )

    assert result.code == RECEIPT_TIME_INVALID


def test_malformed_outer_signature_maps_to_receipt_signature_invalid() -> None:
    request, policy, key = _request()
    response = build_isolated_fit_execution_response(
        _response_payload(REJECTED_PRE_FIT),
        signature=_b64url(b"t" * 64),
    )
    response["authentication"]["signature"] = "malformed"

    result = verify_isolated_fit_response(
        canonical_outer_json_bytes(request),
        canonical_outer_json_bytes(response),
        expected_audience="alr.fit.runner.test",
        adjudicated_at=_timestamp(30),
        key_status_overlay=_overlay_for(request, policy, key),
        synthetic_signature_verifier=_synthetic_signature_verifier,
    )

    assert result.code == RECEIPT_SIGNATURE_INVALID


def test_intrinsic_response_time_failure_maps_to_receipt_time_invalid() -> None:
    request, policy, key = _request()
    response = build_isolated_fit_execution_response(
        _response_payload(ACCEPTED_IN_PROGRESS),
        signature=_b64url(b"t" * 64),
    )
    response["signed_payload"]["status_expires_at"] = _timestamp(5)

    result = verify_isolated_fit_response(
        canonical_outer_json_bytes(request),
        canonical_outer_json_bytes(response),
        expected_audience="alr.fit.runner.test",
        adjudicated_at=_timestamp(4),
        key_status_overlay=_overlay_for(request, policy, key),
        synthetic_signature_verifier=_synthetic_signature_verifier,
    )

    assert result.code == "RECEIPT_TIME_INVALID"


def test_runner_target_drift_maps_to_runner_target_mismatch() -> None:
    request, policy, key = _request()
    payload = _response_payload(REJECTED_PRE_FIT)
    payload["actual_runner_identity"]["measurement_hash"] = _h(
        "wrong-measurement"
    )
    unsigned = copy.deepcopy(payload["actual_runner_identity"])
    unsigned.pop("runner_identity_hash")
    payload["actual_runner_identity"]["runner_identity_hash"] = domain_hash(
        "actual_runner_identity", unsigned
    )
    response = build_isolated_fit_execution_response(
        payload,
        signature=_b64url(b"t" * 64),
    )

    result = verify_isolated_fit_response(
        canonical_outer_json_bytes(request),
        canonical_outer_json_bytes(response),
        expected_audience="alr.fit.runner.test",
        adjudicated_at=_timestamp(30),
        key_status_overlay=_overlay_for(request, policy, key),
        synthetic_signature_verifier=_synthetic_signature_verifier,
    )

    assert result.code == "RUNNER_TARGET_MISMATCH"


def test_runner_target_attestation_cannot_be_captured_after_acceptance() -> None:
    payload = _response_payload(REJECTED_PRE_FIT)
    payload["actual_runner_identity"]["captured_at"] = _timestamp(31)
    unsigned = copy.deepcopy(payload["actual_runner_identity"])
    unsigned.pop("runner_identity_hash")
    payload["actual_runner_identity"]["runner_identity_hash"] = domain_hash(
        "actual_runner_identity", unsigned
    )

    with pytest.raises(ValueError, match="runner_capture_time_invalid"):
        build_isolated_fit_execution_response(
            payload,
            signature=_b64url(b"t" * 64),
        )


def test_runner_target_attestation_cannot_predate_request_validity() -> None:
    request, policy, key = _request()
    payload = _response_payload(REJECTED_PRE_FIT, request=request)
    payload["actual_runner_identity"]["captured_at"] = _timestamp(0)
    unsigned = copy.deepcopy(payload["actual_runner_identity"])
    unsigned.pop("runner_identity_hash")
    payload["actual_runner_identity"]["runner_identity_hash"] = domain_hash(
        "actual_runner_identity", unsigned
    )
    response = build_isolated_fit_execution_response(
        payload,
        signature=_b64url(b"t" * 64),
    )

    result = verify_isolated_fit_response(
        canonical_outer_json_bytes(request),
        canonical_outer_json_bytes(response),
        expected_audience="alr.fit.runner.test",
        adjudicated_at=_timestamp(30),
        key_status_overlay=_overlay_for(request, policy, key),
        synthetic_signature_verifier=_synthetic_signature_verifier,
    )

    assert result.code == RECEIPT_TIME_INVALID


def test_inner_signature_mutation_maps_only_to_v159_inner_code() -> None:
    request, policy, key = _request()
    payload, inner, _raw = _success_payload()
    inner["authentication"]["signature"] = _b64url(b"x" * 64)
    inner_bytes = canonical_v159_jsonb_text_bytes(inner)
    payload["inner_receipt_bytes_base64url"] = _b64url(inner_bytes)
    payload["inner_receipt_digest_sha256"] = hashlib.sha256(inner_bytes).hexdigest()
    response = build_isolated_fit_execution_response(
        payload,
        signature=_b64url(b"t" * 64),
    )

    result = verify_isolated_fit_response(
        canonical_outer_json_bytes(request),
        canonical_outer_json_bytes(response),
        expected_audience="alr.fit.runner.test",
        adjudicated_at=_timestamp(30),
        key_status_overlay=_overlay_for(request, policy, key),
        synthetic_signature_verifier=_synthetic_signature_verifier,
    )

    assert result.code == V159_INNER_SIGNATURE_INVALID
    assert result.fixture_signatures_matched is False


def test_inner_signature_precedes_success_semantic_failure_code() -> None:
    request, policy, key = _request()
    payload, inner, _raw = _success_payload(request)
    response = build_isolated_fit_execution_response(
        payload,
        signature=_b64url(b"t" * 64),
    )
    inner["authentication"]["signature"] = _b64url(b"x" * 64)
    inner_bytes = canonical_v159_jsonb_text_bytes(inner)
    response["signed_payload"]["inner_receipt_bytes_base64url"] = _b64url(
        inner_bytes
    )
    response["signed_payload"]["inner_receipt_digest_sha256"] = hashlib.sha256(
        inner_bytes
    ).hexdigest()
    response["signed_payload"]["v159_claims"][
        "model_training_performed"
    ] = False

    result = verify_isolated_fit_response(
        canonical_outer_json_bytes(request),
        canonical_outer_json_bytes(response),
        expected_audience="alr.fit.runner.test",
        adjudicated_at=_timestamp(30),
        key_status_overlay=_overlay_for(request, policy, key),
        synthetic_signature_verifier=_synthetic_signature_verifier,
    )

    assert result.code == V159_INNER_SIGNATURE_INVALID
    assert result.fixture_signatures_matched is False


def test_fit_runner_lineage_mismatch_maps_to_runner_target_code() -> None:
    request, policy, key = _request()
    payload, _inner, _raw = _success_payload(request)
    response = build_isolated_fit_execution_response(
        payload,
        signature=_b64url(b"t" * 64),
    )
    runner = response["signed_payload"]["actual_runner_identity"]
    runner["runner_version"] = "2.0.0"
    unsigned = copy.deepcopy(runner)
    unsigned.pop("runner_identity_hash")
    runner["runner_identity_hash"] = domain_hash(
        "actual_runner_identity", unsigned
    )

    result = verify_isolated_fit_response(
        canonical_outer_json_bytes(request),
        canonical_outer_json_bytes(response),
        expected_audience="alr.fit.runner.test",
        adjudicated_at=_timestamp(30),
        key_status_overlay=_overlay_for(request, policy, key),
        synthetic_signature_verifier=_synthetic_signature_verifier,
    )

    assert result.code == RUNNER_TARGET_MISMATCH


def test_response_structure_precedes_runner_semantics_in_public_code() -> None:
    request, policy, key = _request()
    response = build_isolated_fit_execution_response(
        _response_payload(REJECTED_PRE_FIT, request=request),
        signature=_b64url(b"t" * 64),
    )
    response["signed_payload"]["unknown_signed_field"] = "forbidden"
    runner = response["signed_payload"]["actual_runner_identity"]
    runner["measurement_hash"] = _h("wrong-measurement")
    unsigned = copy.deepcopy(runner)
    unsigned.pop("runner_identity_hash")
    runner["runner_identity_hash"] = domain_hash(
        "actual_runner_identity", unsigned
    )

    result = verify_isolated_fit_response(
        canonical_outer_json_bytes(request),
        canonical_outer_json_bytes(response),
        expected_audience="alr.fit.runner.test",
        adjudicated_at=_timestamp(30),
        key_status_overlay=_overlay_for(request, policy, key),
        synthetic_signature_verifier=_synthetic_signature_verifier,
    )

    assert result.code == RECEIPT_OUTCOME_INVALID


def test_missing_or_noncanonical_response_requires_reconciliation() -> None:
    request, policy, key = _request()
    kwargs = {
        "expected_audience": "alr.fit.runner.test",
        "adjudicated_at": _timestamp(30),
        "key_status_overlay": _overlay_for(request, policy, key),
        "synthetic_signature_verifier": _synthetic_signature_verifier,
    }

    missing = verify_isolated_fit_response(
        canonical_outer_json_bytes(request),
        None,
        **kwargs,
    )
    malformed = verify_isolated_fit_response(
        canonical_outer_json_bytes(request),
        b'{"response_kind":"TERMINAL", "outcome":"SUCCEEDED"}',
        **kwargs,
    )

    assert missing.code == RECONCILE_REQUIRED
    assert malformed.code == RECONCILE_REQUIRED
    assert missing.persistence_allowed is False
    assert malformed.authority_granted is False


def test_request_before_not_before_returns_request_not_yet_valid() -> None:
    request, _policy, key = _request()
    overlay = build_key_status_overlay(
        key_entry=key,
        trust_policy_snapshot_digest=request["signed_payload"][
            "trust_policy_snapshot_digest"
        ],
        status=ACTIVE,
        observed_at=_timestamp(0),
        valid_until=_timestamp(40),
        provider_evidence_digest=_h("provider-evidence"),
    )

    result = verify_isolated_fit_response(
        canonical_outer_json_bytes(request),
        None,
        expected_audience="alr.fit.runner.test",
        adjudicated_at=_timestamp(0),
        key_status_overlay=overlay,
        synthetic_signature_verifier=_synthetic_signature_verifier,
    )

    assert result.valid is False
    assert result.code == "REQUEST_NOT_YET_VALID"


def test_signed_local_only_states_are_not_runner_outcomes() -> None:
    for forbidden in (RECONCILE_REQUIRED, "EXPIRED_UNCLAIMED"):
        payload = _response_payload(REJECTED_PRE_FIT)
        payload["outcome"] = forbidden
        response = {
            "schema_version": "alr_isolated_fit_execution_receipt_v1",
            "response_kind": TERMINAL,
            "outcome": forbidden,
            "signed_payload": payload,
            "authentication": {
                "algorithm": "ed25519",
                "key_id": payload["signing_key_id"],
                "signature": _b64url(b"t" * 64),
            },
            "no_authority": copy.deepcopy(payload["no_authority"]),
            "authority_counters": copy.deepcopy(payload["authority_counters"]),
        }
        validation = validate_isolated_fit_execution_response(response)
        assert validation.valid is False
        assert "response_outcome_invalid" in validation.reasons


def test_response_replay_is_exact_or_permanent_conflict() -> None:
    response = build_isolated_fit_execution_response(
        _response_payload(REJECTED_PRE_FIT),
        signature=_b64url(b"t" * 64),
    )
    divergent = copy.deepcopy(response)
    divergent["signed_payload"]["failure_code"] = "REQUEST_REJECTED"

    assert classify_response_replay(response, copy.deepcopy(response)) == EXACT_REPLAY
    assert classify_response_replay(response, divergent) == DURABLE_CONSUMPTION_CONFLICT


def test_replay_classifiers_reject_malformed_operands_before_exactness() -> None:
    with pytest.raises(ValueError, match="request_replay_invalid"):
        classify_request_replay({}, {})
    with pytest.raises(ValueError, match="response_replay_invalid"):
        classify_response_replay({}, {})


def test_response_replay_allows_monotonic_status_and_terminal_progression() -> None:
    first = build_isolated_fit_execution_response(
        _response_payload(ACCEPTED_IN_PROGRESS),
        signature=_b64url(b"t" * 64),
    )
    next_payload = _response_payload(ACCEPTED_IN_PROGRESS)
    next_payload["status_generation"] = 2
    next_payload["status_issued_at"] = _timestamp(7)
    next_payload["stage_observations"]["actual_inputs_consumed"] = True
    second = build_isolated_fit_execution_response(
        next_payload,
        signature=_b64url(b"u" * 64),
    )
    rejected = build_isolated_fit_execution_response(
        _response_payload(REJECTED_PRE_FIT),
        signature=_b64url(b"t" * 64),
    )
    failed = build_isolated_fit_execution_response(
        _response_payload(FAILED_AFTER_START),
        signature=_b64url(b"t" * 64),
    )

    assert classify_response_replay(first, second) == "MONOTONIC_STATUS_ADVANCE"
    assert classify_response_replay(first, rejected) == "TERMINAL_ADVANCE"
    assert classify_response_replay(second, rejected) == DURABLE_CONSUMPTION_CONFLICT
    assert classify_response_replay(second, failed) == "TERMINAL_ADVANCE"
    assert classify_response_replay(rejected, second) == DURABLE_CONSUMPTION_CONFLICT

    regressed = copy.deepcopy(second)
    regressed["signed_payload"]["status_generation"] = 1
    assert classify_response_replay(second, regressed) == DURABLE_CONSUMPTION_CONFLICT

    regressed_time_payload = copy.deepcopy(next_payload)
    regressed_time_payload["status_generation"] = 3
    regressed_time_payload["status_issued_at"] = _timestamp(6)
    regressed_time = build_isolated_fit_execution_response(
        regressed_time_payload,
        signature=_b64url(b"v" * 64),
    )
    assert (
        classify_response_replay(second, regressed_time)
        == DURABLE_CONSUMPTION_CONFLICT
    )

    late_payload = copy.deepcopy(next_payload)
    late_payload["status_generation"] = 3
    late_payload["status_issued_at"] = _timestamp(31)
    late_payload["status_expires_at"] = _timestamp(40)
    late_payload["stage_observations"]["fit_started"] = True
    late_status = build_isolated_fit_execution_response(
        late_payload,
        signature=_b64url(b"v" * 64),
    )
    assert (
        classify_response_replay(late_status, failed)
        == DURABLE_CONSUMPTION_CONFLICT
    )


def test_request_rejects_expected_rows_above_signed_resource_budget() -> None:
    request, _policy, _key = _request()
    payload = request["signed_payload"]
    payload["resource_budget"]["max_training_rows"] = 1
    payload["resource_budget_hash"] = domain_hash(
        "resource_budget", payload["resource_budget"]
    )
    request_hash = domain_hash("request_signed_payload", payload)
    request["request_hash"] = request_hash
    request["attempt_id"] = request_hash
    request["invocation_id"] = request_hash

    validation = validate_trusted_fit_execution_request(request)

    assert validation.valid is False
    assert "resource_training_rows_exceeded" in validation.reasons


@pytest.mark.parametrize(
    ("outcome", "issued_field"),
    [
        (ACCEPTED_IN_PROGRESS, "status_issued_at"),
        (REJECTED_PRE_FIT, "issuer_verified_at"),
    ],
)
def test_verifier_rejects_responses_issued_after_adjudication(
    outcome: str,
    issued_field: str,
) -> None:
    request, policy, key = _request()
    payload = _response_payload(outcome)
    payload[issued_field] = _timestamp(31)
    if outcome == ACCEPTED_IN_PROGRESS:
        payload["status_expires_at"] = _timestamp(40)
    response = build_isolated_fit_execution_response(
        payload,
        signature=_b64url(b"t" * 64),
    )

    result = verify_isolated_fit_response(
        canonical_outer_json_bytes(request),
        canonical_outer_json_bytes(response),
        expected_audience="alr.fit.runner.test",
        adjudicated_at=_timestamp(30),
        key_status_overlay=_overlay_for(request, policy, key),
        synthetic_signature_verifier=_synthetic_signature_verifier,
    )

    assert result.valid is False
    assert result.code == "RECEIPT_TIME_INVALID"


def test_success_accepts_existing_fit_capture_runner_identity_without_rehashing() -> None:
    payload, _inner, _raw = _success_payload()
    fit_contract = payload["fit_capture_contract"]
    assert validate_alr_challenger_fit_capture_attestation_contract(
        fit_contract
    ).valid
    fit_runner = fit_contract["fit_capture"]["runner_identity"]

    response = build_isolated_fit_execution_response(
        payload,
        signature=_b64url(b"t" * 64),
    )

    assert response["signed_payload"]["v159_subject"][
        "runner_identity_hash"
    ] == fit_runner["runner_identity_hash"]
    assert payload["actual_runner_identity"]["runner_identity_hash"] != fit_runner[
        "runner_identity_hash"
    ]


def test_success_rejects_authenticated_runner_fit_runner_splice() -> None:
    payload, _inner, _raw = _success_payload()
    payload["actual_runner_identity"]["host_identity_hash"] = _h("other-host")
    unsigned = copy.deepcopy(payload["actual_runner_identity"])
    unsigned.pop("runner_identity_hash")
    payload["actual_runner_identity"]["runner_identity_hash"] = domain_hash(
        "actual_runner_identity", unsigned
    )

    with pytest.raises(ValueError, match="fit_runner_identity_mismatch"):
        build_isolated_fit_execution_response(
            payload,
            signature=_b64url(b"t" * 64),
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["signed_payload"]["admission"].pop("durable_receipt_hash"),
        lambda value: value["signed_payload"].update({"trust_policy_snapshot": {}}),
        lambda value: value["signed_payload"].update({"runner_target_policy": []}),
        lambda value: value.update({"authentication": None}),
    ],
)
def test_public_request_validator_is_total_over_malformed_structures(mutation) -> None:
    request, _policy, _key = _request()
    mutation(request)

    validation = validate_trusted_fit_execution_request(request)

    assert validation.valid is False
    assert validation.verdict == INVALID


def test_public_request_validator_contains_custom_mapping_exceptions() -> None:
    validation = validate_trusted_fit_execution_request(_ExplodingMapping())

    assert validation.valid is False
    assert validation.verdict == INVALID


def test_overlay_rejects_revoked_and_overlong_current_windows() -> None:
    request, policy, key = _request()
    revoked = build_key_status_overlay(
        key_entry=key,
        trust_policy_snapshot_digest=request["signed_payload"][
            "trust_policy_snapshot_digest"
        ],
        status="REVOKED",
        observed_at="2026-07-12T12:00:00.000000Z",
        valid_until="2026-07-12T12:01:00.000000Z",
        provider_evidence_digest=_h("provider"),
    )
    overlong = build_key_status_overlay(
        key_entry=key,
        trust_policy_snapshot_digest=request["signed_payload"][
            "trust_policy_snapshot_digest"
        ],
        status=ACTIVE,
        observed_at="2026-07-12T12:00:00.000000Z",
        valid_until="2026-07-12T12:06:00.000000Z",
        provider_evidence_digest=_h("provider"),
    )

    for overlay in (revoked, overlong):
        validation = validate_key_status_overlay(
            overlay,
            trust_policy_snapshot=policy,
            adjudicated_at="2026-07-12T12:00:30.000000Z",
            for_new_signature=False,
        )
        assert validation.valid is False


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload["result_observation"]["actual_inputs"].update(
            {"dataset_hash": _h("wrong-dataset")}
        ),
        lambda payload: payload["resource_observation"].update(
            {"peak_memory_bytes": 2_000_000}
        ),
    ],
)
def test_success_verifier_rejects_input_or_resource_budget_drift(mutator) -> None:
    request, policy, key = _request()
    payload, inner, _raw = _success_payload()
    mutator(payload)
    if payload["result_observation"] != inner["result_observation"]:
        inner["result_observation"] = copy.deepcopy(payload["result_observation"])
        inner_bytes = canonical_v159_jsonb_text_bytes(inner)
        payload["inner_receipt_bytes_base64url"] = _b64url(inner_bytes)
        payload["inner_receipt_digest_sha256"] = hashlib.sha256(inner_bytes).hexdigest()
    with pytest.raises(ValueError, match="fit_capture_contract_binding_mismatch"):
        build_isolated_fit_execution_response(
            payload,
            signature=_b64url(b"t" * 64),
        )


def test_success_contract_rejects_any_external_request_observation() -> None:
    payload, _inner, _raw = _success_payload()
    payload["resource_observation"]["external_request_count"] = 1

    with pytest.raises(ValueError, match="fit_capture_contract_binding_mismatch"):
        build_isolated_fit_execution_response(
            payload,
            signature=_b64url(b"t" * 64),
        )


def test_signed_in_progress_is_authenticated_fixture_but_still_reconcile_required() -> None:
    request, policy, key = _request()
    response = build_isolated_fit_execution_response(
        _response_payload(ACCEPTED_IN_PROGRESS),
        signature=_b64url(b"t" * 64),
    )

    result = verify_isolated_fit_response(
        canonical_outer_json_bytes(request),
        canonical_outer_json_bytes(response),
        expected_audience="alr.fit.runner.test",
        adjudicated_at=_timestamp(20),
        key_status_overlay=_overlay_for(request, policy, key),
        synthetic_signature_verifier=_synthetic_signature_verifier,
    )

    assert result.code == RECONCILE_REQUIRED
    assert result.terminal is False
    assert result.persistence_allowed is False
