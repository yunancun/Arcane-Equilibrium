from __future__ import annotations
import base64
import copy
import hashlib
import json
import math
import re
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from ml_training.alr_challenger_fit_capture_attestation import validate_alr_challenger_fit_capture_attestation_contract
from ml_training.alr_challenger_repository import AlrChallengerRepositoryError, validate_qualified_training_receipt_read
from ml_training.alr_challenger_training_contract import validate_alr_challenger_training_contract
CANONICAL_BYTES_INVALID = 'CANONICAL_BYTES_INVALID'
(VALID, INVALID, ACTIVE, RETIRED, EXACT_REPLAY, NONCE_REPLAY_CONFLICT, DURABLE_CONSUMPTION_CONFLICT, NEW_REQUEST, MONOTONIC_STATUS_ADVANCE, TERMINAL_ADVANCE, STATUS, TERMINAL, ACCEPTED_IN_PROGRESS, SUCCEEDED, REJECTED_PRE_FIT, FAILED_AFTER_START, AUTHENTICATED_UNCONSUMED, EXTERNAL_HOST_UNCHECKED, NOT_ESTABLISHED) = 'VALID INVALID ACTIVE RETIRED EXACT_REPLAY NONCE_REPLAY_CONFLICT DURABLE_CONSUMPTION_CONFLICT NEW_REQUEST MONOTONIC_STATUS_ADVANCE TERMINAL_ADVANCE STATUS TERMINAL ACCEPTED_IN_PROGRESS SUCCEEDED REJECTED_PRE_FIT FAILED_AFTER_START AUTHENTICATED_UNCONSUMED EXTERNAL_HOST_UNCHECKED NOT_ESTABLISHED'.split()
(STRUCTURE_INVALID, REQUEST_SIGNATURE_INVALID, REQUEST_NOT_YET_VALID, REQUEST_EXPIRED, AUDIENCE_MISMATCH, POLICY_OR_KEY_REJECTED, RUNNER_TARGET_MISMATCH, RECEIPT_SIGNATURE_INVALID, RECEIPT_REQUEST_BINDING_MISMATCH, RECEIPT_TIME_INVALID, RECEIPT_OUTCOME_INVALID, EXECUTION_CLAIM_MISMATCH, V159_INNER_SIGNATURE_INVALID, V159_INNER_RECEIPT_MISMATCH, AUTHORITY_MISMATCH, RECONCILE_REQUIRED, DURABLE_CONSUMPTION_REQUIRED) = 'STRUCTURE_INVALID REQUEST_SIGNATURE_INVALID REQUEST_NOT_YET_VALID REQUEST_EXPIRED AUDIENCE_MISMATCH POLICY_OR_KEY_REJECTED RUNNER_TARGET_MISMATCH RECEIPT_SIGNATURE_INVALID RECEIPT_REQUEST_BINDING_MISMATCH RECEIPT_TIME_INVALID RECEIPT_OUTCOME_INVALID EXECUTION_CLAIM_MISMATCH V159_INNER_SIGNATURE_INVALID V159_INNER_RECEIPT_MISMATCH AUTHORITY_MISMATCH RECONCILE_REQUIRED DURABLE_CONSUMPTION_REQUIRED'.split()
TRUST_POLICY_SCHEMA_VERSION = 'alr_fit_trust_policy_snapshot_v1'
KEY_STATUS_OVERLAY_SCHEMA_VERSION = 'alr_fit_trust_key_status_overlay_v1'
REQUEST_SCHEMA_VERSION = 'alr_trusted_fit_execution_request_v1'
RESPONSE_SCHEMA_VERSION = 'alr_isolated_fit_execution_receipt_v1'
REQUEST_SIGNATURE_DOMAIN = b'ALR_TRUSTED_FIT_REQUEST_V1'
V159_INNER_SIGNATURE_DOMAIN = b'ALR_V159_INNER_FIT_RECEIPT_V1'
TERMINAL_RECEIPT_SIGNATURE_DOMAIN = b'ALR_ISOLATED_FIT_TERMINAL_RECEIPT_V1'
HANDSHAKE_SIGNING_USAGE = 'ALR_TRUSTED_FIT_HANDSHAKE_SIGNING'
_HASH_NAMESPACE = b'alr_trusted_fit_handshake_v1\x00'
_BASE64URL_RE = re.compile('^[A-Za-z0-9_-]+$')
_HASH_RE = re.compile('^[0-9a-f]{64}$')
_HEAD_RE = re.compile('^[0-9a-f]{40}$')
# LR1(S2.2A):scoped learning identity(== learning_runtime_manifest.self_digest)。
_LEARNING_RUNTIME_DIGEST_RE = re.compile('^sha256:[0-9a-f]{64}$')
_IDENTIFIER_RE = re.compile('^[a-z0-9][a-z0-9_.:-]{0,127}$')
_NONCE_RE = re.compile('^[0-9a-f]{64}$')
_UTC_TIMESTAMP_RE = re.compile('^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}\\.\\d{6}Z$')
_MAX_STRUCTURE_DEPTH = 64
_MAX_STRUCTURE_NODES = 50000

def _fields(names: str) -> frozenset[str]:
    return frozenset(names.split())
_KEY_FIELDS = _fields('issuer_id key_id generation algorithm usage public_key_base64url public_key_digest')
_TRUST_POLICY_FIELDS = _fields('schema_version policy_id epoch audience allowed_keys retired_key_verification_allowed')
_OVERLAY_FIELDS = _fields('schema_version evidence_tier issuer_id trust_policy_snapshot_digest key_id public_key_digest algorithm usage generation status observed_at valid_until provider_evidence_digest overlay_digest')
_ADMISSION_FIELDS = _fields('training_contract qualified_receipt_read durable_receipt_hash training_key_hash training_contract_hash qualified_receipt_binding_hash')
_EXPECTED_INPUT_FIELDS = _fields('training_contract_hash durable_receipt_hash training_key_hash source_head learning_runtime_digest dataset_hash row_ids_hash split_hash code_manifest_hash training_config_hash feature_schema_hash label_schema_hash training_rows')
_EXECUTION_TRUE = _fields('actual_dataset_rehash_required actual_code_rehash_required exact_source_head_required effective_config_rehash_required exact_split_membership_required actual_fit_required model_artifact_bytes_required immutable_output_directory_required isolated_challenger_registry_required')
_EXECUTION_FALSE = _fields('symlink_updates_allowed legacy_run_training_pipeline_allowed legacy_model_registry_allowed serving_or_promotion_allowed')
_EXECUTION_CONTRACT = {**dict.fromkeys(_EXECUTION_TRUE, True), **dict.fromkeys(_EXECUTION_FALSE, False)}
_RESOURCE_BUDGET_FIELDS = _fields('max_wall_seconds max_cpu_seconds max_memory_bytes max_artifact_bytes max_training_rows max_external_requests max_api_cost_usd')
_POSITIVE_RESOURCE_FIELDS = _fields('max_wall_seconds max_cpu_seconds max_memory_bytes max_artifact_bytes max_training_rows')
_RUNNER_TARGET_FIELDS = _fields('schema_version producer_kind producer_id runner_source_hash measurement_hash isolation_class capability_class output_contract_hash')
_REQUEST_PAYLOAD_FIELDS = _fields('schema_version admission expected_training_inputs execution_contract execution_contract_hash resource_budget resource_budget_hash request_nonce nonce_digest request_generation requester_id issuer_id audience trust_policy_id trust_policy_snapshot trust_policy_snapshot_digest trust_policy_epoch allowed_signing_key_set_digest signature_algorithm signing_key_id runner_target_policy runner_target_policy_hash issued_at not_before accept_by complete_by output_obligations no_authority authority_counters')
_REQUEST_FIELDS = _fields('schema_version signed_payload request_hash attempt_id invocation_id authentication status dispatch_allowed training_allowed persistence_allowed no_authority authority_counters')
_REQUEST_AUTHENTICATION_FIELDS = _fields('algorithm key_id signature')
_RESPONSE_FIELDS = _fields('schema_version response_kind outcome signed_payload authentication no_authority authority_counters')
_RESPONSE_AUTHENTICATION_FIELDS = _REQUEST_AUTHENTICATION_FIELDS
_RESPONSE_COMMON_FIELDS = _fields('schema_version response_kind outcome request_hash attempt_id nonce_digest request_generation audience issuer_id trust_policy_id trust_policy_snapshot_digest trust_policy_epoch signature_algorithm signing_key_id runner_target_policy_hash actual_runner_identity accepted_at no_authority authority_counters')
_STATUS_FIELDS = _RESPONSE_COMMON_FIELDS | _fields('status_generation status_issued_at status_expires_at stage_observations')
_TERMINAL_COMMON_FIELDS = _RESPONSE_COMMON_FIELDS | _fields('issuer_verified_at receipt_expires_at automatic_retry_allowed persistence_allowed v159_success_projection_allowed')
_REJECTED_PRE_FIT_FIELDS = _TERMINAL_COMMON_FIELDS | _fields('rejected_at failure_phase failure_code actual_inputs_consumed fit_started model_training_performed result_observation inner_receipt_bytes_base64url inner_receipt_digest_sha256')
_FAILED_AFTER_START_FIELDS = _TERMINAL_COMMON_FIELDS | _fields('fit_started_at failure_observed_at fit_completed_at captured_at failure_phase failure_code stage_observations result_observation inner_receipt_bytes_base64url inner_receipt_digest_sha256')
_SUCCEEDED_FIELDS = _TERMINAL_COMMON_FIELDS | _fields('fit_started_at fit_completed_at captured_at v159_subject v159_claims result_observation resource_observation actual_input_material_set_hash ordered_artifact_set_hash fit_capture_contract inner_receipt_bytes_base64url inner_receipt_digest_sha256')
_RUNNER_IDENTITY_FIELDS = _fields('schema_version producer_kind producer_id runner_version runner_source_hash host_identity_hash environment_identity_hash process_identity_hash measurement_hash isolation_class capability_class output_contract_hash invocation_id captured_at runner_identity_hash')
_STAGE_FIELDS = _fields('request_accepted actual_inputs_consumed fit_started fit_completed artifacts_written artifact_readback_completed onnx_semantic_validation_completed')
_PRE_FIT_FAILURE_PHASES = {'PRE_FIT_ADMISSION', 'PRE_FIT_RESOURCE', 'PRE_FIT_POLICY'}
_PRE_FIT_FAILURE_CODES = _fields('REQUEST_REJECTED RESOURCE_UNAVAILABLE RUNNER_TARGET_UNAVAILABLE REQUEST_EXPIRED_BEFORE_CLAIM INPUT_ADMISSION_REJECTED')
_AFTER_START_FAILURE_PHASES = _fields('INPUT_CONSUMPTION FIT_EXECUTION ARTIFACT_WRITE ARTIFACT_READBACK ONNX_VALIDATION OUTPUT_CONTRACT')
_AFTER_START_FAILURE_CODES = _fields('FIT_EXECUTION_FAILED RESOURCE_LIMIT_EXCEEDED ARTIFACT_WRITE_FAILED ARTIFACT_READBACK_FAILED ONNX_VALIDATION_FAILED OUTPUT_CONTRACT_FAILED')
_AFTER_START_FAILURE_PAIRS = {'INPUT_CONSUMPTION': {'RESOURCE_LIMIT_EXCEEDED'}, 'FIT_EXECUTION': {'FIT_EXECUTION_FAILED', 'RESOURCE_LIMIT_EXCEEDED'}, 'ARTIFACT_WRITE': {'ARTIFACT_WRITE_FAILED', 'RESOURCE_LIMIT_EXCEEDED'}, 'ARTIFACT_READBACK': {'ARTIFACT_READBACK_FAILED'}, 'ONNX_VALIDATION': {'ONNX_VALIDATION_FAILED'}, 'OUTPUT_CONTRACT': {'OUTPUT_CONTRACT_FAILED'}}
_KEY_STATUSES = _fields('ACTIVE RETIRED REVOKED COMPROMISED EXPIRED UNKNOWN AMBIGUOUS')
_V159_FIELDS = _fields('schema_version evidence_tier claim_kind authentication_status subject claims result_observation authentication verified_at expires_at no_authority authority_counters')
_V159_SUBJECT_FIELDS = _fields('durable_receipt_hash training_key_hash result_hash fit_capture_hash candidate_attestation_hash training_run_hash challenger_hash runner_identity_hash actual_input_material_set_hash ordered_artifact_set_hash')
_V159_CLAIM_FIELDS = _fields('actual_inputs_consumed actual_fit_executed model_training_performed artifact_readback_completed onnx_semantic_validation_passed')
_V159_OBSERVATION_FIELDS = _fields('source_head actual_inputs model fit_started_at fit_completed_at artifacts')
_V159_ACTUAL_INPUT_FIELDS = _fields('dataset_hash row_ids_hash split_hash code_manifest_hash training_config_hash feature_schema_hash label_schema_hash training_rows')
_V159_MODEL_FIELDS = _fields('model_schema_version metrics_hash resource_usage_hash')
_V159_ARTIFACT_FIELDS = _fields('artifact_hash artifact_size_bytes')
_V159_AUTHENTICATION_FIELDS = _fields('issuer_id trust_policy_id signature_key_id signature_algorithm signature')
_RESOURCE_OBSERVATION_FIELDS = _fields('wall_time_microseconds cpu_time_microseconds peak_memory_bytes total_artifact_bytes training_rows external_request_count api_cost_microusd')
_NO_AUTHORITY = dict.fromkeys(_fields('exchange_authority trading_authority order_or_probe_authority decision_lease_authority cost_gate_authority proof_authority serving_authority promotion_authority latest_authority runtime_mutation_authority database_write_authority symlink_authority'), False)
_AUTHORITY_COUNTERS = dict.fromkeys(_fields('exchange_contact_count trading_action_count order_or_probe_count decision_lease_count cost_gate_change_count proof_claim_count serving_or_promotion_count runtime_mutation_count database_write_count symlink_update_count model_fit_count'), 0)
_OUTPUT_OBLIGATIONS = {'quantiles': ['q10', 'q50', 'q90'], 'onnx_semantic_validation_required': True, 'immutable_artifact_readback_required': True, 'v159_complete_bundle_required': True, 'external_request_count_required': 0, 'api_cost_microusd_required': 0}

@dataclass(frozen=True)
class AlrTrustedFitHandshakeValidation:
    valid: bool
    verdict: str
    reason: str
    reasons: tuple[str, ...]
    request_hash: str | None = None

@dataclass(frozen=True)
class AlrTrustedFitHandshakeVerification:
    valid: bool
    code: str
    verdict: str
    reasons: tuple[str, ...]
    request_hash: str | None
    response_kind: str | None
    outcome: str | None
    terminal: bool
    fixture_signatures_matched: bool
    signatures_valid: bool
    capability_authenticity: str
    persistence_allowed: bool
    authority_granted: bool
    model_training_performed_claim: str
    durable_consumption_required: bool
SyntheticSignatureVerifier = Callable[[str, bytes, bytes, bytes], bool]

class AlrTrustedFitHandshakeError(ValueError):
    pass

def build_trust_policy_snapshot(*, policy_id: str, epoch: int, audience: str, allowed_keys: list[Mapping[str, Any]], retired_key_verification_allowed: bool) -> dict[str, Any]:
    normalized_keys = [_normalize_key_entry(value) for value in allowed_keys]
    if not normalized_keys or len(normalized_keys) > 64:
        raise AlrTrustedFitHandshakeError('allowed_keys_invalid')
    normalized_keys.sort(key=_key_sort_key)
    if len({(item['issuer_id'], item['key_id']) for item in normalized_keys}) != len(normalized_keys):
        raise AlrTrustedFitHandshakeError('allowed_keys_conflict')
    snapshot = {'schema_version': TRUST_POLICY_SCHEMA_VERSION, 'policy_id': _identifier(policy_id, 'policy_id_invalid'), 'epoch': _positive_int(epoch, 'policy_epoch_invalid'), 'audience': _identifier(audience, 'policy_audience_invalid'), 'allowed_keys': normalized_keys, 'retired_key_verification_allowed': _literal_bool(retired_key_verification_allowed, 'retired_key_policy_invalid')}
    _validate_trust_policy_snapshot(snapshot)
    return copy.deepcopy(snapshot)

def build_key_status_overlay(*, key_entry: Mapping[str, Any], trust_policy_snapshot_digest: str, status: str, observed_at: str, valid_until: str, provider_evidence_digest: str) -> dict[str, Any]:
    key = _normalize_key_entry(key_entry)
    overlay: dict[str, Any] = {'schema_version': KEY_STATUS_OVERLAY_SCHEMA_VERSION, 'evidence_tier': 'PLATFORM_OR_EXTERNAL_ATTESTED', 'issuer_id': key['issuer_id'], 'trust_policy_snapshot_digest': _hash(trust_policy_snapshot_digest, 'trust_policy_snapshot_digest_invalid'), 'key_id': key['key_id'], 'public_key_digest': key['public_key_digest'], 'algorithm': 'ed25519', 'usage': HANDSHAKE_SIGNING_USAGE, 'generation': key['generation'], 'status': _key_status(status), 'observed_at': _timestamp(observed_at, 'overlay_observed_at_invalid'), 'valid_until': _timestamp(valid_until, 'overlay_valid_until_invalid'), 'provider_evidence_digest': _hash(provider_evidence_digest, 'provider_evidence_digest_invalid')}
    overlay['overlay_digest'] = domain_hash('key_status_overlay', overlay)
    return copy.deepcopy(overlay)

def validate_key_status_overlay(overlay: Any, *, trust_policy_snapshot: Mapping[str, Any], adjudicated_at: str, for_new_signature: bool) -> AlrTrustedFitHandshakeValidation:
    reasons: list[str] = []
    try:
        snapshot = _snapshot_mapping(overlay, 'overlay_not_mapping')
        policy = _snapshot_mapping(trust_policy_snapshot, 'trust_policy_snapshot_not_mapping')
        _validate_trust_policy_snapshot(policy)
        adjudicated = _parse_timestamp(_timestamp(adjudicated_at, 'adjudicated_at_invalid'))
    except AlrTrustedFitHandshakeError as exc:
        return _invalid_validation(str(exc))
    if set(snapshot) != _OVERLAY_FIELDS:
        reasons.append('overlay_fields_invalid')
    if snapshot.get('schema_version') != KEY_STATUS_OVERLAY_SCHEMA_VERSION:
        reasons.append('overlay_schema_invalid')
    if snapshot.get('evidence_tier') != 'PLATFORM_OR_EXTERNAL_ATTESTED':
        reasons.append('overlay_evidence_tier_invalid')
    if not _is_hash(snapshot.get('provider_evidence_digest')):
        reasons.append('provider_evidence_digest_invalid')
    unsigned = {key: value for (key, value) in snapshot.items() if key != 'overlay_digest'}
    if snapshot.get('overlay_digest') != domain_hash('key_status_overlay', unsigned):
        reasons.append('overlay_digest_invalid')
    policy_digest = domain_hash('trust_policy_snapshot', policy)
    if snapshot.get('trust_policy_snapshot_digest') != policy_digest:
        reasons.append('overlay_policy_mismatch')
    matching = [key for key in policy['allowed_keys'] if all((_typed_equal(key[field], snapshot.get(field)) for field in ('issuer_id', 'key_id', 'generation', 'algorithm', 'usage', 'public_key_digest')))]
    if len(matching) != 1:
        reasons.append('overlay_key_mismatch')
    try:
        observed = _parse_timestamp(_timestamp(snapshot.get('observed_at'), 'overlay_observed_at_invalid'))
        valid_until_dt = _parse_timestamp(_timestamp(snapshot.get('valid_until'), 'overlay_valid_until_invalid'))
        if not observed <= adjudicated < valid_until_dt:
            reasons.append('overlay_time_invalid')
        if (valid_until_dt - observed).total_seconds() > 300:
            reasons.append('overlay_lifetime_invalid')
    except AlrTrustedFitHandshakeError as exc:
        reasons.append(str(exc))
    status = snapshot.get('status')
    if status == ACTIVE:
        pass
    elif status == RETIRED:
        if for_new_signature is not False or policy.get('retired_key_verification_allowed') is not True:
            reasons.append('retired_key_not_eligible')
    else:
        reasons.append('key_status_rejected')
    if type(for_new_signature) is not bool:
        reasons.append('signature_use_invalid')
    if reasons:
        return _invalid_validation(*reasons)
    return _valid_validation()

def build_trusted_fit_request_payload(*, admission: Mapping[str, Any], expected_training_inputs: Mapping[str, Any], execution_contract: Mapping[str, Any], resource_budget: Mapping[str, Any], request_nonce: str, request_generation: int, requester_id: str, issuer_id: str, audience: str, trust_policy_snapshot: Mapping[str, Any], signing_key_id: str, runner_target_policy: Mapping[str, Any], issued_at: str, not_before: str, accept_by: str, complete_by: str) -> dict[str, Any]:
    admission_snapshot = _validated_admission(admission)
    expected = _validated_expected_inputs(expected_training_inputs, admission_snapshot)
    execution = _validated_execution_contract(execution_contract)
    resources = _validated_resource_budget(resource_budget)
    policy = _snapshot_mapping(trust_policy_snapshot, 'trust_policy_snapshot_invalid')
    _validate_trust_policy_snapshot(policy)
    requester = _identifier(requester_id, 'requester_id_invalid')
    issuer = _identifier(issuer_id, 'issuer_id_invalid')
    target_audience = _identifier(audience, 'audience_invalid')
    if target_audience != policy['audience']:
        raise AlrTrustedFitHandshakeError('audience_policy_mismatch')
    key_id = _identifier(signing_key_id, 'signing_key_id_invalid')
    signing_keys = [key for key in policy['allowed_keys'] if key['issuer_id'] == issuer and key['key_id'] == key_id]
    if len(signing_keys) != 1:
        raise AlrTrustedFitHandshakeError('signing_key_not_pinned')
    runner_target = _validated_runner_target(runner_target_policy)
    nonce = _nonce(request_nonce)
    timestamps = [_timestamp(issued_at, 'issued_at_invalid'), _timestamp(not_before, 'not_before_invalid'), _timestamp(accept_by, 'accept_by_invalid'), _timestamp(complete_by, 'complete_by_invalid')]
    parsed_times = [_parse_timestamp(value) for value in timestamps]
    if not parsed_times[0] <= parsed_times[1] <= parsed_times[2] < parsed_times[3]:
        raise AlrTrustedFitHandshakeError('request_time_order_invalid')
    payload = {'schema_version': REQUEST_SCHEMA_VERSION, 'admission': admission_snapshot, 'expected_training_inputs': expected, 'execution_contract': execution, 'execution_contract_hash': domain_hash('execution_contract', execution), 'resource_budget': resources, 'resource_budget_hash': domain_hash('resource_budget', resources), 'request_nonce': nonce, 'nonce_digest': _nonce_digest(nonce), 'request_generation': _positive_int(request_generation, 'request_generation_invalid'), 'requester_id': requester, 'issuer_id': issuer, 'audience': target_audience, 'trust_policy_id': policy['policy_id'], 'trust_policy_snapshot': policy, 'trust_policy_snapshot_digest': domain_hash('trust_policy_snapshot', policy), 'trust_policy_epoch': policy['epoch'], 'allowed_signing_key_set_digest': domain_hash('allowed_key_set', policy['allowed_keys']), 'signature_algorithm': 'ed25519', 'signing_key_id': key_id, 'runner_target_policy': runner_target, 'runner_target_policy_hash': domain_hash('runner_target_policy', runner_target), 'issued_at': timestamps[0], 'not_before': timestamps[1], 'accept_by': timestamps[2], 'complete_by': timestamps[3], 'output_obligations': copy.deepcopy(_OUTPUT_OBLIGATIONS), 'no_authority': copy.deepcopy(_NO_AUTHORITY), 'authority_counters': copy.deepcopy(_AUTHORITY_COUNTERS)}
    reasons = _request_payload_reasons(payload)
    if reasons:
        raise AlrTrustedFitHandshakeError(reasons[0])
    return copy.deepcopy(payload)

def build_trusted_fit_execution_request(signed_payload: Mapping[str, Any], *, signature: str) -> dict[str, Any]:
    payload = _snapshot_mapping(signed_payload, 'request_payload_not_mapping')
    reasons = _request_payload_reasons(payload)
    if reasons:
        raise AlrTrustedFitHandshakeError(reasons[0])
    strict_base64url_decode(signature, expected_bytes=64, max_bytes=64)
    request_hash = domain_hash('request_signed_payload', payload)
    request = {'schema_version': REQUEST_SCHEMA_VERSION, 'signed_payload': payload, 'request_hash': request_hash, 'attempt_id': request_hash, 'invocation_id': request_hash, 'authentication': {'algorithm': 'ed25519', 'key_id': payload['signing_key_id'], 'signature': signature}, 'status': 'EXTERNAL_DISPATCH_AUTHORIZATION_REQUIRED', 'dispatch_allowed': False, 'training_allowed': False, 'persistence_allowed': False, 'no_authority': copy.deepcopy(_NO_AUTHORITY), 'authority_counters': copy.deepcopy(_AUTHORITY_COUNTERS)}
    validation = validate_trusted_fit_execution_request(request)
    if not validation.valid:
        raise AlrTrustedFitHandshakeError(validation.reason)
    return copy.deepcopy(request)

def validate_trusted_fit_execution_request(request: Any) -> AlrTrustedFitHandshakeValidation:
    try:
        snapshot = _snapshot_mapping(request, 'request_not_mapping')
    except AlrTrustedFitHandshakeError as exc:
        return _invalid_validation(str(exc))
    reasons: list[str] = []
    if set(snapshot) != _REQUEST_FIELDS:
        reasons.append('request_fields_invalid')
    payload = snapshot.get('signed_payload')
    if isinstance(payload, Mapping):
        payload_snapshot = copy.deepcopy(dict(payload))
        reasons.extend(_request_payload_reasons(payload_snapshot))
    else:
        payload_snapshot = {}
        reasons.append('request_payload_not_mapping')
    request_hash = None
    try:
        request_hash = domain_hash('request_signed_payload', payload_snapshot)
    except (AlrTrustedFitHandshakeError, TypeError, ValueError):
        reasons.append('request_hash_invalid')
    if request_hash is not None and (snapshot.get('request_hash') != request_hash or snapshot.get('attempt_id') != request_hash or snapshot.get('invocation_id') != request_hash):
        reasons.append('request_identity_mismatch')
    authentication = snapshot.get('authentication')
    if not isinstance(authentication, Mapping) or set(authentication) != _REQUEST_AUTHENTICATION_FIELDS:
        reasons.append('request_authentication_invalid')
    else:
        if authentication.get('algorithm') != 'ed25519' or authentication.get('algorithm') != payload_snapshot.get('signature_algorithm') or authentication.get('key_id') != payload_snapshot.get('signing_key_id'):
            reasons.append('request_authentication_invalid')
        try:
            strict_base64url_decode(authentication.get('signature'), expected_bytes=64, max_bytes=64)
        except AlrTrustedFitHandshakeError:
            reasons.append('signature_invalid')
    fixed = {'schema_version': REQUEST_SCHEMA_VERSION, 'status': 'EXTERNAL_DISPATCH_AUTHORIZATION_REQUIRED', 'dispatch_allowed': False, 'training_allowed': False, 'persistence_allowed': False}
    for (field, expected) in fixed.items():
        if not _typed_equal(snapshot.get(field), expected):
            reasons.append(field + '_invalid')
    if not _typed_equal(snapshot.get('no_authority'), _NO_AUTHORITY):
        reasons.append('no_authority_invalid')
    if not _typed_equal(snapshot.get('authority_counters'), _AUTHORITY_COUNTERS):
        reasons.append('authority_counters_invalid')
    if reasons:
        return _invalid_validation(*_dedupe(reasons), request_hash=request_hash)
    return _valid_validation(request_hash=request_hash)

def validate_trusted_fit_request_bytes(raw_request: Any) -> AlrTrustedFitHandshakeValidation:
    try:
        request = parse_canonical_outer_json(raw_request, max_bytes=1048576)
    except AlrTrustedFitHandshakeError:
        return _invalid_validation(CANONICAL_BYTES_INVALID)
    return validate_trusted_fit_execution_request(request)

def classify_request_replay(existing: Any, candidate: Any) -> str:
    before = _snapshot_mapping(existing, 'existing_request_invalid')
    after = _snapshot_mapping(candidate, 'candidate_request_invalid')
    if not validate_trusted_fit_execution_request(before).valid or not validate_trusted_fit_execution_request(after).valid:
        raise AlrTrustedFitHandshakeError('request_replay_invalid')
    if canonical_outer_json_bytes(before) == canonical_outer_json_bytes(after):
        return EXACT_REPLAY
    before_payload = _snapshot_mapping(before.get('signed_payload'), 'existing_request_payload_invalid')
    after_payload = _snapshot_mapping(after.get('signed_payload'), 'candidate_request_payload_invalid')
    if before_payload.get('request_nonce') == after_payload.get('request_nonce') or before_payload.get('nonce_digest') == after_payload.get('nonce_digest') or before.get('request_hash') == after.get('request_hash'):
        return NONCE_REPLAY_CONFLICT
    before_admission = before_payload['admission']
    after_admission = after_payload['admission']
    if all(_typed_equal(before_admission[field], after_admission[field]) for field in (
        'durable_receipt_hash', 'training_key_hash'
    )):
        return DURABLE_CONSUMPTION_CONFLICT
    return NEW_REQUEST

def classify_response_replay(existing: Any, candidate: Any) -> str:
    (before, after) = (_snapshot_mapping(value, 'response_replay_invalid') for value in (existing, candidate))
    if not validate_isolated_fit_execution_response(before).valid or not validate_isolated_fit_execution_response(after).valid:
        raise AlrTrustedFitHandshakeError('response_replay_invalid')
    if canonical_outer_json_bytes(before) == canonical_outer_json_bytes(after):
        return EXACT_REPLAY
    (old, new) = (before['signed_payload'], after['signed_payload'])
    if old['request_hash'] != new['request_hash']:
        return NEW_REQUEST
    if any((not _typed_equal(old.get(field), new.get(field)) for field in _RESPONSE_COMMON_FIELDS - {'response_kind', 'outcome'})) or old['response_kind'] != STATUS:
        return DURABLE_CONSUMPTION_CONFLICT
    if new['response_kind'] == TERMINAL:
        if _parse_timestamp(new['issuer_verified_at']) < _parse_timestamp(old['status_issued_at']):
            return DURABLE_CONSUMPTION_CONFLICT
        old_stages = old['stage_observations']
        if new['outcome'] == REJECTED_PRE_FIT and any(
            old_stages[field] is True for field in _STAGE_FIELDS - {'request_accepted'}
        ):
            return DURABLE_CONSUMPTION_CONFLICT
        if new['outcome'] == FAILED_AFTER_START and any(
            old_stages[field] is True and new['stage_observations'][field] is not True
            for field in _STAGE_FIELDS
        ):
            return DURABLE_CONSUMPTION_CONFLICT
        return TERMINAL_ADVANCE
    (old_stages, new_stages) = (old['stage_observations'], new['stage_observations'])
    if new['status_generation'] > old['status_generation'] and _parse_timestamp(
        new['status_issued_at']
    ) > _parse_timestamp(old['status_issued_at']) and all((old_stages[field] is not True or new_stages[field] is True for field in _STAGE_FIELDS)):
        return MONOTONIC_STATUS_ADVANCE
    return DURABLE_CONSUMPTION_CONFLICT

def build_isolated_fit_execution_response(signed_payload: Mapping[str, Any], *, signature: str) -> dict[str, Any]:
    payload = _snapshot_mapping(signed_payload, 'response_payload_not_mapping')
    reasons = _response_payload_reasons(payload)
    if reasons:
        raise AlrTrustedFitHandshakeError(reasons[0])
    strict_base64url_decode(signature, expected_bytes=64, max_bytes=64)
    response = {'schema_version': RESPONSE_SCHEMA_VERSION, 'response_kind': payload['response_kind'], 'outcome': payload['outcome'], 'signed_payload': payload, 'authentication': {'algorithm': 'ed25519', 'key_id': payload['signing_key_id'], 'signature': signature}, 'no_authority': copy.deepcopy(_NO_AUTHORITY), 'authority_counters': copy.deepcopy(_AUTHORITY_COUNTERS)}
    if len(canonical_outer_json_bytes(response)) > 2097152:
        raise AlrTrustedFitHandshakeError('response_bytes_too_large')
    validation = validate_isolated_fit_execution_response(response)
    if not validation.valid:
        raise AlrTrustedFitHandshakeError(validation.reason)
    return copy.deepcopy(response)

def validate_isolated_fit_execution_response(response: Any, *, request: Mapping[str, Any] | None=None) -> AlrTrustedFitHandshakeValidation:
    try:
        snapshot = _snapshot_mapping(response, 'response_not_mapping')
    except AlrTrustedFitHandshakeError as exc:
        return _invalid_validation(str(exc))
    reasons: list[str] = []
    if set(snapshot) != _RESPONSE_FIELDS:
        reasons.append('response_fields_invalid')
    payload = snapshot.get('signed_payload')
    if isinstance(payload, Mapping):
        payload_snapshot = copy.deepcopy(dict(payload))
        reasons.extend(_response_payload_reasons(payload_snapshot))
    else:
        payload_snapshot = {}
        reasons.append('response_payload_not_mapping')
    if snapshot.get('schema_version') != RESPONSE_SCHEMA_VERSION:
        reasons.append('response_schema_invalid')
    for field in ('response_kind', 'outcome'):
        if snapshot.get(field) != payload_snapshot.get(field) or type(snapshot.get(field)) is not str:
            reasons.append('response_envelope_binding_invalid')
    authentication = snapshot.get('authentication')
    if not isinstance(authentication, Mapping) or set(authentication) != _RESPONSE_AUTHENTICATION_FIELDS:
        reasons.append('response_authentication_invalid')
    else:
        if authentication.get('algorithm') != 'ed25519' or authentication.get('algorithm') != payload_snapshot.get('signature_algorithm') or authentication.get('key_id') != payload_snapshot.get('signing_key_id'):
            reasons.append('response_authentication_invalid')
        try:
            strict_base64url_decode(authentication.get('signature'), expected_bytes=64, max_bytes=64)
        except AlrTrustedFitHandshakeError:
            reasons.append('signature_invalid')
    if not _typed_equal(snapshot.get('no_authority'), _NO_AUTHORITY):
        reasons.append('no_authority_invalid')
    if not _typed_equal(snapshot.get('authority_counters'), _AUTHORITY_COUNTERS):
        reasons.append('authority_counters_invalid')
    if request is not None:
        request_validation = validate_trusted_fit_execution_request(request)
        if not request_validation.valid:
            reasons.append('bound_request_invalid')
        elif not _runner_target_matches(payload_snapshot, request):
            reasons.append('runner_target_mismatch')
        elif not _response_matches_request(payload_snapshot, request):
            reasons.append('receipt_request_binding_mismatch')
    request_hash = payload_snapshot.get('request_hash')
    if reasons:
        return _invalid_validation(*_dedupe(reasons), request_hash=request_hash)
    return _valid_validation(request_hash=request_hash)

def verify_isolated_fit_response(raw_request: Any, raw_response: Any | None, *, expected_audience: str, adjudicated_at: str, key_status_overlay: Mapping[str, Any], synthetic_signature_verifier: SyntheticSignatureVerifier | None) -> AlrTrustedFitHandshakeVerification:
    request_hash: str | None = None
    response: dict[str, Any] | None = None
    fixture_matched = False

    def fail(code: str, *reasons: str) -> AlrTrustedFitHandshakeVerification:
        return _verification_failure(code, *reasons, request_hash=request_hash, response_kind=None if response is None else response.get('response_kind'), outcome=None if response is None else response.get('outcome'), fixture_signatures_matched=fixture_matched)
    try:
        request = parse_canonical_outer_json(raw_request, max_bytes=1048576)
    except AlrTrustedFitHandshakeError:
        return fail(STRUCTURE_INVALID, CANONICAL_BYTES_INVALID)
    request_validation = validate_trusted_fit_execution_request(request)
    if not request_validation.valid:
        request_hash = request_validation.request_hash
        if request_validation.reasons == ('signature_invalid',):
            return fail(REQUEST_SIGNATURE_INVALID, 'signature_invalid')
        return fail(STRUCTURE_INVALID, *request_validation.reasons)
    request_hash = request['request_hash']
    policy = request['signed_payload']['trust_policy_snapshot']
    key = _pinned_key_for_request(request)
    if key is None or synthetic_signature_verifier is None:
        return fail(POLICY_OR_KEY_REJECTED, 'production_ed25519_backend_unavailable')
    public_key = strict_base64url_decode(key['public_key_base64url'], expected_bytes=32, max_bytes=32)
    request_signature = strict_base64url_decode(request['authentication']['signature'], expected_bytes=64, max_bytes=64)
    if not _fixture_signature_matches(synthetic_signature_verifier, 'request', public_key, request_signature, request_signature_preimage(request['signed_payload'])):
        return fail(REQUEST_SIGNATURE_INVALID, 'synthetic_request_signature_mismatch')
    fixture_matched = True
    try:
        adjudicated = _parse_timestamp(_timestamp(adjudicated_at, 'adjudicated_at_invalid'))
    except AlrTrustedFitHandshakeError as exc:
        return fail(RECEIPT_TIME_INVALID, str(exc))
    try:
        _identifier(expected_audience, 'expected_audience_invalid')
    except AlrTrustedFitHandshakeError as exc:
        return fail(AUDIENCE_MISMATCH, str(exc))
    try:
        overlay_snapshot = _snapshot_mapping(key_status_overlay, 'overlay_not_mapping')
    except AlrTrustedFitHandshakeError as exc:
        return fail(POLICY_OR_KEY_REJECTED, str(exc))
    overlay_validation = validate_key_status_overlay(overlay_snapshot, trust_policy_snapshot=policy, adjudicated_at=adjudicated_at, for_new_signature=False)
    if not overlay_validation.valid:
        return fail(POLICY_OR_KEY_REJECTED, *overlay_validation.reasons)
    key = _pinned_key_for_request(request)
    if key is not None and (not all((_typed_equal(key[field], overlay_snapshot.get(field)) for field in ('issuer_id', 'key_id', 'generation', 'algorithm', 'usage', 'public_key_digest')))):
        return fail(POLICY_OR_KEY_REJECTED, 'overlay_request_key_mismatch')
    if overlay_snapshot.get('status') == RETIRED:
        return fail(POLICY_OR_KEY_REJECTED, 'retired_key_effective_time_unavailable')
    if expected_audience != request['signed_payload']['audience']:
        return fail(AUDIENCE_MISMATCH, 'expected_audience_mismatch')
    if adjudicated < _parse_timestamp(request['signed_payload']['not_before']):
        return fail(REQUEST_NOT_YET_VALID, 'request_not_yet_valid')
    if raw_response is None:
        return fail(RECONCILE_REQUIRED, 'response_missing')
    try:
        response = parse_canonical_outer_json(raw_response, max_bytes=2097152)
    except AlrTrustedFitHandshakeError:
        return fail(RECONCILE_REQUIRED, CANONICAL_BYTES_INVALID)
    try:
        payload, terminal_signature = _response_outer_signature_material(response, request)
    except AlrTrustedFitHandshakeError as exc:
        fixture_matched = False
        return fail(RECEIPT_SIGNATURE_INVALID, str(exc))
    if not _fixture_signature_matches(synthetic_signature_verifier, 'terminal', public_key, terminal_signature, terminal_receipt_signature_preimage(payload)):
        fixture_matched = False
        return fail(RECEIPT_SIGNATURE_INVALID, 'synthetic_terminal_signature_mismatch')
    response_validation = validate_isolated_fit_execution_response(response, request=request)
    pre_inner_code = _response_pre_inner_failure_code(response_validation.reasons)
    if pre_inner_code is not None:
        return fail(pre_inner_code, *response_validation.reasons)
    if not _response_time_matches_request(payload, request, adjudicated):
        return fail(RECEIPT_TIME_INVALID, 'response_time_request_window_mismatch')
    if response['outcome'] == SUCCEEDED:
        inner_signature_matched = _v159_inner_fixture_signature_matches(payload, public_key, synthetic_signature_verifier)
        if inner_signature_matched is False:
            fixture_matched = False
            return fail(V159_INNER_SIGNATURE_INVALID, 'synthetic_v159_inner_signature_mismatch')
    if not response_validation.valid:
        return fail(_response_failure_code(response_validation.reasons), *response_validation.reasons)
    if response['response_kind'] != TERMINAL:
        return fail(RECONCILE_REQUIRED, 'signed_status_is_nonterminal')
    return AlrTrustedFitHandshakeVerification(valid=True, code=DURABLE_CONSUMPTION_REQUIRED, verdict=EXTERNAL_HOST_UNCHECKED, reasons=('synthetic_fixture_cannot_establish_platform_trust',), request_hash=request_hash, response_kind=response['response_kind'], outcome=response['outcome'], terminal=True, fixture_signatures_matched=True, signatures_valid=False, capability_authenticity=EXTERNAL_HOST_UNCHECKED, persistence_allowed=False, authority_granted=False, model_training_performed_claim=NOT_ESTABLISHED, durable_consumption_required=False)

def canonical_outer_json_bytes(value: Any) -> bytes:
    try:
        _validate_json_tree(value, ascii_strings=False)
        return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    except AlrTrustedFitHandshakeError:
        raise
    except Exception as exc:
        raise AlrTrustedFitHandshakeError(CANONICAL_BYTES_INVALID) from exc

def parse_canonical_outer_json(raw: Any, *, max_bytes: int) -> dict[str, Any]:
    if type(raw) is not bytes or type(max_bytes) is not int or max_bytes < 2 or (not 2 <= len(raw) <= max_bytes):
        raise AlrTrustedFitHandshakeError(CANONICAL_BYTES_INVALID)

    def reject_duplicates(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for (key, value) in items:
            if key in result:
                raise AlrTrustedFitHandshakeError(CANONICAL_BYTES_INVALID)
            result[key] = value
        return result
    try:
        parsed = json.loads(raw.decode('utf-8'), object_pairs_hook=reject_duplicates, parse_constant=lambda _value: _raise_canonical_error())
    except AlrTrustedFitHandshakeError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, RecursionError) as exc:
        raise AlrTrustedFitHandshakeError(CANONICAL_BYTES_INVALID) from exc
    if not isinstance(parsed, dict):
        raise AlrTrustedFitHandshakeError(CANONICAL_BYTES_INVALID)
    if canonical_outer_json_bytes(parsed) != raw:
        raise AlrTrustedFitHandshakeError(CANONICAL_BYTES_INVALID)
    return parsed

def strict_base64url_decode(value: Any, *, expected_bytes: int | None=None, max_bytes: int) -> bytes:
    if type(value) is not str or not value or _BASE64URL_RE.fullmatch(value) is None or ('=' in value) or (type(max_bytes) is not int) or (max_bytes < 1) or (expected_bytes is not None and (type(expected_bytes) is not int or expected_bytes < 0)):
        raise AlrTrustedFitHandshakeError(CANONICAL_BYTES_INVALID)
    if len(value) > (max_bytes + 2) // 3 * 4:
        raise AlrTrustedFitHandshakeError(CANONICAL_BYTES_INVALID)
    try:
        decoded = base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise AlrTrustedFitHandshakeError(CANONICAL_BYTES_INVALID) from exc
    if len(decoded) > max_bytes or (expected_bytes is not None and len(decoded) != expected_bytes):
        raise AlrTrustedFitHandshakeError(CANONICAL_BYTES_INVALID)
    if _base64url_encode(decoded) != value:
        raise AlrTrustedFitHandshakeError(CANONICAL_BYTES_INVALID)
    return decoded

def domain_hash(domain: str, payload: Any) -> str:
    if type(domain) is not str or not domain or (not domain.isascii()) or ('\x00' in domain):
        raise AlrTrustedFitHandshakeError(CANONICAL_BYTES_INVALID)
    canonical = canonical_outer_json_bytes(payload)
    preimage = _HASH_NAMESPACE + domain.encode('ascii') + b'\x00' + len(canonical).to_bytes(8, 'big') + canonical
    return hashlib.sha256(preimage).hexdigest()

def _accepted_result_domain_hash(domain: str, payload: Any) -> str:
    if type(domain) is not str or not domain.isascii() or (not domain):
        raise AlrTrustedFitHandshakeError(CANONICAL_BYTES_INVALID)
    prefix = ('alr_challenger_training_result_contract_v1\x00' + domain + '\x00').encode('ascii')
    return hashlib.sha256(prefix + canonical_outer_json_bytes(payload)).hexdigest()

def request_signature_preimage(signed_payload: Mapping[str, Any]) -> bytes:
    return _signature_preimage(REQUEST_SIGNATURE_DOMAIN, signed_payload, inner=False)

def terminal_receipt_signature_preimage(signed_payload: Mapping[str, Any]) -> bytes:
    return _signature_preimage(TERMINAL_RECEIPT_SIGNATURE_DOMAIN, signed_payload, inner=False)

def v159_inner_signature_preimage(receipt_projection: Mapping[str, Any]) -> bytes:
    if not isinstance(receipt_projection, Mapping):
        raise AlrTrustedFitHandshakeError(CANONICAL_BYTES_INVALID)
    unsigned = copy.deepcopy(dict(receipt_projection))
    authentication = unsigned.get('authentication')
    if not isinstance(authentication, Mapping) or 'signature' not in authentication:
        raise AlrTrustedFitHandshakeError(CANONICAL_BYTES_INVALID)
    auth_without_signature = copy.deepcopy(dict(authentication))
    auth_without_signature.pop('signature', None)
    unsigned['authentication'] = auth_without_signature
    return _signature_preimage(V159_INNER_SIGNATURE_DOMAIN, unsigned, inner=True)

def canonical_v159_jsonb_text_bytes(value: Any) -> bytes:
    try:
        _validate_json_tree(value, ascii_strings=True)
        ordered = _pg_ordered(value)
        return json.dumps(ordered, ensure_ascii=True, sort_keys=False, separators=(', ', ': '), allow_nan=False).encode('utf-8')
    except AlrTrustedFitHandshakeError:
        raise
    except Exception as exc:
        raise AlrTrustedFitHandshakeError(CANONICAL_BYTES_INVALID) from exc

def parse_canonical_v159_jsonb_text_bytes(raw: Any, *, max_bytes: int) -> dict[str, Any]:
    if type(raw) is not bytes or type(max_bytes) is not int or max_bytes < 2 or (not 2 <= len(raw) <= max_bytes):
        raise AlrTrustedFitHandshakeError(CANONICAL_BYTES_INVALID)

    def reject_duplicates(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for (key, value) in items:
            if key in result:
                raise AlrTrustedFitHandshakeError(CANONICAL_BYTES_INVALID)
            result[key] = value
        return result
    try:
        parsed = json.loads(raw.decode('utf-8'), object_pairs_hook=reject_duplicates, parse_constant=lambda _value: _raise_canonical_error())
    except AlrTrustedFitHandshakeError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, RecursionError) as exc:
        raise AlrTrustedFitHandshakeError(CANONICAL_BYTES_INVALID) from exc
    if not isinstance(parsed, dict) or canonical_v159_jsonb_text_bytes(parsed) != raw:
        raise AlrTrustedFitHandshakeError(CANONICAL_BYTES_INVALID)
    return parsed

def _signature_preimage(domain: bytes, payload: Mapping[str, Any], *, inner: bool) -> bytes:
    if not isinstance(payload, Mapping):
        raise AlrTrustedFitHandshakeError(CANONICAL_BYTES_INVALID)
    snapshot = copy.deepcopy(dict(payload))
    canonical = canonical_v159_jsonb_text_bytes(snapshot) if inner else canonical_outer_json_bytes(snapshot)
    return domain + b'\x00' + len(canonical).to_bytes(8, 'big') + canonical

def _validate_json_tree(value: Any, *, ascii_strings: bool) -> None:
    active: set[int] = set()
    nodes = 0

    def visit(node: Any, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if depth > _MAX_STRUCTURE_DEPTH or nodes > _MAX_STRUCTURE_NODES:
            raise AlrTrustedFitHandshakeError(CANONICAL_BYTES_INVALID)
        if node is None or type(node) in (bool, int):
            return
        if type(node) is float:
            if not math.isfinite(node):
                raise AlrTrustedFitHandshakeError(CANONICAL_BYTES_INVALID)
            return
        if type(node) is str:
            if ascii_strings and (not node.isascii()):
                raise AlrTrustedFitHandshakeError(CANONICAL_BYTES_INVALID)
            return
        if isinstance(node, Mapping):
            identity = id(node)
            if identity in active:
                raise AlrTrustedFitHandshakeError(CANONICAL_BYTES_INVALID)
            active.add(identity)
            try:
                for (key, child) in node.items():
                    if type(key) is not str or not key.isascii():
                        raise AlrTrustedFitHandshakeError(CANONICAL_BYTES_INVALID)
                    visit(child, depth + 1)
            finally:
                active.remove(identity)
            return
        if type(node) is list:
            identity = id(node)
            if identity in active:
                raise AlrTrustedFitHandshakeError(CANONICAL_BYTES_INVALID)
            active.add(identity)
            try:
                for child in node:
                    visit(child, depth + 1)
            finally:
                active.remove(identity)
            return
        raise AlrTrustedFitHandshakeError(CANONICAL_BYTES_INVALID)
    visit(value, 0)

def _pg_ordered(value: Any) -> Any:
    if isinstance(value, Mapping):
        result: OrderedDict[str, Any] = OrderedDict()
        keys = sorted(value, key=lambda item: (len(item.encode('utf-8')), item.encode('utf-8')))
        for key in keys:
            result[key] = _pg_ordered(value[key])
        return result
    if type(value) is list:
        return [_pg_ordered(item) for item in value]
    return value

def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode('ascii').rstrip('=')

def _normalize_key_entry(value: Any) -> dict[str, Any]:
    snapshot = _snapshot_mapping(value, 'key_entry_not_mapping')
    if set(snapshot) != _KEY_FIELDS:
        raise AlrTrustedFitHandshakeError('key_entry_fields_invalid')
    public_key = strict_base64url_decode(snapshot.get('public_key_base64url'), expected_bytes=32, max_bytes=32)
    public_key_digest = hashlib.sha256(public_key).hexdigest()
    if snapshot.get('public_key_digest') != public_key_digest:
        raise AlrTrustedFitHandshakeError('public_key_digest_invalid')
    if snapshot.get('algorithm') != 'ed25519':
        raise AlrTrustedFitHandshakeError('signature_algorithm_invalid')
    if snapshot.get('usage') != HANDSHAKE_SIGNING_USAGE:
        raise AlrTrustedFitHandshakeError('key_usage_invalid')
    return {'issuer_id': _identifier(snapshot.get('issuer_id'), 'issuer_id_invalid'), 'key_id': _identifier(snapshot.get('key_id'), 'key_id_invalid'), 'generation': _positive_int(snapshot.get('generation'), 'key_generation_invalid'), 'algorithm': 'ed25519', 'usage': HANDSHAKE_SIGNING_USAGE, 'public_key_base64url': _base64url_encode(public_key), 'public_key_digest': public_key_digest}

def _validate_trust_policy_snapshot(value: Any) -> None:
    snapshot = _snapshot_mapping(value, 'trust_policy_snapshot_not_mapping')
    if set(snapshot) != _TRUST_POLICY_FIELDS:
        raise AlrTrustedFitHandshakeError('trust_policy_snapshot_fields_invalid')
    if snapshot.get('schema_version') != TRUST_POLICY_SCHEMA_VERSION:
        raise AlrTrustedFitHandshakeError('trust_policy_snapshot_schema_invalid')
    _identifier(snapshot.get('policy_id'), 'policy_id_invalid')
    _positive_int(snapshot.get('epoch'), 'policy_epoch_invalid')
    _identifier(snapshot.get('audience'), 'policy_audience_invalid')
    _literal_bool(snapshot.get('retired_key_verification_allowed'), 'retired_key_policy_invalid')
    keys = snapshot.get('allowed_keys')
    if type(keys) is not list or not keys or len(keys) > 64:
        raise AlrTrustedFitHandshakeError('allowed_keys_invalid')
    normalized = [_normalize_key_entry(key) for key in keys]
    if normalized != sorted(normalized, key=_key_sort_key):
        raise AlrTrustedFitHandshakeError('allowed_keys_not_canonical')
    if len({(item['issuer_id'], item['key_id']) for item in normalized}) != len(normalized):
        raise AlrTrustedFitHandshakeError('allowed_keys_conflict')

def _key_sort_key(value: Mapping[str, Any]) -> tuple[Any, ...]:
    return (value['issuer_id'], value['key_id'], value['generation'], value['algorithm'], value['public_key_digest'])

def _validated_admission(value: Any) -> dict[str, Any]:
    snapshot = _snapshot_mapping(value, 'admission_not_mapping')
    if set(snapshot) != _ADMISSION_FIELDS:
        raise AlrTrustedFitHandshakeError('admission_fields_invalid')
    contract = _snapshot_mapping(snapshot.get('training_contract'), 'training_contract_not_mapping')
    validation = validate_alr_challenger_training_contract(contract)
    if not validation.valid:
        raise AlrTrustedFitHandshakeError('training_contract_invalid')
    try:
        receipt_read = validate_qualified_training_receipt_read(snapshot.get('qualified_receipt_read'), training_contract=contract)
    except AlrChallengerRepositoryError as exc:
        raise AlrTrustedFitHandshakeError('qualified_receipt_read_invalid') from exc
    if receipt_read.get('status') != 'FOUND' or not isinstance(receipt_read.get('receipt'), Mapping):
        raise AlrTrustedFitHandshakeError('qualified_receipt_not_found')
    receipt = receipt_read['receipt']
    derived = {'training_contract_hash': contract['contract_hash'], 'durable_receipt_hash': receipt['durable_receipt_hash'], 'training_key_hash': receipt['training_key_hash'], 'qualified_receipt_binding_hash': _accepted_result_domain_hash('qualified_receipt_read', receipt_read)}
    for (field, expected) in derived.items():
        if not _typed_equal(snapshot.get(field), expected):
            reason = 'qualified_receipt_binding_hash_mismatch' if field == 'qualified_receipt_binding_hash' else field + '_mismatch'
            raise AlrTrustedFitHandshakeError(reason)
    return {'training_contract': contract, 'qualified_receipt_read': copy.deepcopy(receipt_read), **derived}

def _validated_expected_inputs(value: Any, admission: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = _snapshot_mapping(value, 'expected_training_inputs_not_mapping')
    if set(snapshot) != _EXPECTED_INPUT_FIELDS:
        raise AlrTrustedFitHandshakeError('expected_training_inputs_fields_invalid')
    result: dict[str, Any] = {}
    for field in sorted(
        _EXPECTED_INPUT_FIELDS
        - {'source_head', 'training_rows', 'learning_runtime_digest'}
    ):
        result[field] = _hash(snapshot.get(field), field + '_invalid')
    head = snapshot.get('source_head')
    if type(head) is not str or _HEAD_RE.fullmatch(head) is None:
        raise AlrTrustedFitHandshakeError('source_head_invalid')
    result['source_head'] = head
    # LR1(S2.2A):learning_runtime_digest 是 sha256: 前綴 digest,非 64-hex hash。
    learning_runtime_digest = snapshot.get('learning_runtime_digest')
    if type(learning_runtime_digest) is not str or (
        _LEARNING_RUNTIME_DIGEST_RE.fullmatch(learning_runtime_digest) is None
    ):
        raise AlrTrustedFitHandshakeError('learning_runtime_digest_invalid')
    result['learning_runtime_digest'] = learning_runtime_digest
    result['training_rows'] = _positive_int(snapshot.get('training_rows'), 'training_rows_invalid')
    parity = {'training_contract_hash': 'training_contract_hash', 'durable_receipt_hash': 'durable_receipt_hash', 'training_key_hash': 'training_key_hash'}
    for (expected_field, admission_field) in parity.items():
        if result[expected_field] != admission.get(admission_field):
            raise AlrTrustedFitHandshakeError('admission_input_mismatch')
    return result

def _validated_execution_contract(value: Any) -> dict[str, Any]:
    snapshot = _snapshot_mapping(value, 'execution_contract_not_mapping')
    if not _typed_equal(snapshot, _EXECUTION_CONTRACT):
        raise AlrTrustedFitHandshakeError('execution_contract_invalid')
    return copy.deepcopy(_EXECUTION_CONTRACT)

def _validated_resource_budget(value: Any) -> dict[str, Any]:
    snapshot = _snapshot_mapping(value, 'resource_budget_not_mapping')
    if set(snapshot) != _RESOURCE_BUDGET_FIELDS:
        raise AlrTrustedFitHandshakeError('resource_budget_invalid')
    if any((type(snapshot.get(field)) is not int or snapshot[field] <= 0 for field in _POSITIVE_RESOURCE_FIELDS)):
        raise AlrTrustedFitHandshakeError('resource_budget_invalid')
    for field in ('max_external_requests', 'max_api_cost_usd'):
        if type(snapshot.get(field)) is not int or snapshot[field] != 0:
            raise AlrTrustedFitHandshakeError('resource_budget_invalid')
    return copy.deepcopy(snapshot)

def _validated_runner_target(value: Any) -> dict[str, Any]:
    snapshot = _snapshot_mapping(value, 'runner_target_policy_not_mapping')
    if set(snapshot) != _RUNNER_TARGET_FIELDS:
        raise AlrTrustedFitHandshakeError('runner_target_policy_fields_invalid')
    if snapshot.get('schema_version') != 'alr_isolated_runner_target_policy_v1':
        raise AlrTrustedFitHandshakeError('runner_target_policy_schema_invalid')
    result = copy.deepcopy(snapshot)
    for field in ('producer_kind', 'producer_id', 'isolation_class', 'capability_class'):
        result[field] = _identifier(snapshot.get(field), field + '_invalid')
    for field in ('runner_source_hash', 'measurement_hash', 'output_contract_hash'):
        result[field] = _hash(snapshot.get(field), field + '_invalid')
    return result

def _request_payload_reasons(value: Any) -> list[str]:
    try:
        snapshot = _snapshot_mapping(value, 'request_payload_not_mapping')
    except AlrTrustedFitHandshakeError as exc:
        return [str(exc)]
    reasons: list[str] = []
    if set(snapshot) != _REQUEST_PAYLOAD_FIELDS:
        reasons.append('request_payload_fields_invalid')
    if snapshot.get('schema_version') != REQUEST_SCHEMA_VERSION:
        reasons.append('request_payload_schema_invalid')
    try:
        admission = _validated_admission(snapshot.get('admission'))
    except AlrTrustedFitHandshakeError as exc:
        admission = {}
        reasons.append(str(exc))
    try:
        expected = _validated_expected_inputs(snapshot.get('expected_training_inputs'), admission)
    except AlrTrustedFitHandshakeError as exc:
        expected = {}
        reasons.append(str(exc))
    try:
        execution = _validated_execution_contract(snapshot.get('execution_contract'))
        if snapshot.get('execution_contract_hash') != domain_hash('execution_contract', execution):
            reasons.append('execution_contract_hash_invalid')
    except AlrTrustedFitHandshakeError as exc:
        reasons.append(str(exc))
    resources: dict[str, Any] = {}
    try:
        resources = _validated_resource_budget(snapshot.get('resource_budget'))
        if snapshot.get('resource_budget_hash') != domain_hash('resource_budget', resources):
            reasons.append('resource_budget_hash_invalid')
    except AlrTrustedFitHandshakeError as exc:
        reasons.append(str(exc))
    try:
        nonce = _nonce(snapshot.get('request_nonce'))
        if snapshot.get('nonce_digest') != _nonce_digest(nonce):
            reasons.append('nonce_digest_invalid')
    except AlrTrustedFitHandshakeError as exc:
        reasons.append(str(exc))
    try:
        _positive_int(snapshot.get('request_generation'), 'request_generation_invalid')
    except AlrTrustedFitHandshakeError as exc:
        reasons.append(str(exc))
    for field in ('requester_id', 'issuer_id', 'audience', 'trust_policy_id', 'signing_key_id'):
        try:
            _identifier(snapshot.get(field), field + '_invalid')
        except AlrTrustedFitHandshakeError as exc:
            reasons.append(str(exc))
    policy: dict[str, Any] = {}
    try:
        policy = _snapshot_mapping(snapshot.get('trust_policy_snapshot'), 'trust_policy_snapshot_not_mapping')
        _validate_trust_policy_snapshot(policy)
        if snapshot.get('trust_policy_snapshot_digest') != domain_hash('trust_policy_snapshot', policy):
            reasons.append('trust_policy_snapshot_digest_invalid')
        if snapshot.get('allowed_signing_key_set_digest') != domain_hash('allowed_key_set', policy['allowed_keys']):
            reasons.append('allowed_signing_key_set_digest_invalid')
        if snapshot.get('trust_policy_id') != policy['policy_id']:
            reasons.append('trust_policy_id_mismatch')
        if snapshot.get('trust_policy_epoch') != policy['epoch'] or type(snapshot.get('trust_policy_epoch')) is not int:
            reasons.append('trust_policy_epoch_mismatch')
        if snapshot.get('audience') != policy['audience']:
            reasons.append('audience_policy_mismatch')
        matching = [key for key in policy['allowed_keys'] if key['issuer_id'] == snapshot.get('issuer_id') and key['key_id'] == snapshot.get('signing_key_id') and (key['algorithm'] == snapshot.get('signature_algorithm'))]
        if len(matching) != 1:
            reasons.append('signing_key_not_pinned')
    except AlrTrustedFitHandshakeError as exc:
        reasons.append(str(exc))
    if snapshot.get('signature_algorithm') != 'ed25519':
        reasons.append('signature_algorithm_invalid')
    try:
        runner = _validated_runner_target(snapshot.get('runner_target_policy'))
        if snapshot.get('runner_target_policy_hash') != domain_hash('runner_target_policy', runner):
            reasons.append('runner_target_policy_hash_invalid')
    except AlrTrustedFitHandshakeError as exc:
        reasons.append(str(exc))
    parsed_times: list[datetime] = []
    for field in ('issued_at', 'not_before', 'accept_by', 'complete_by'):
        try:
            parsed_times.append(_parse_timestamp(_timestamp(snapshot.get(field), field + '_invalid')))
        except AlrTrustedFitHandshakeError as exc:
            reasons.append(str(exc))
    if len(parsed_times) == 4 and (not parsed_times[0] <= parsed_times[1] <= parsed_times[2] < parsed_times[3]):
        reasons.append('request_time_order_invalid')
    if not _typed_equal(snapshot.get('output_obligations'), _OUTPUT_OBLIGATIONS):
        reasons.append('output_obligations_invalid')
    if not _typed_equal(snapshot.get('no_authority'), _NO_AUTHORITY):
        reasons.append('no_authority_invalid')
    if not _typed_equal(snapshot.get('authority_counters'), _AUTHORITY_COUNTERS):
        reasons.append('authority_counters_invalid')
    if admission and expected:
        for field in ('training_contract_hash', 'durable_receipt_hash', 'training_key_hash'):
            if expected[field] != admission[field]:
                reasons.append('admission_input_mismatch')
    if expected and resources and (expected['training_rows'] > resources['max_training_rows']):
        reasons.append('resource_training_rows_exceeded')
    return _dedupe(reasons)

def _response_payload_reasons(value: Any) -> list[str]:
    try:
        snapshot = _snapshot_mapping(value, 'response_payload_not_mapping')
    except AlrTrustedFitHandshakeError as exc:
        return [str(exc)]
    reasons: list[str] = []
    outcome = snapshot.get('outcome')
    response_kind = snapshot.get('response_kind')
    if outcome == ACCEPTED_IN_PROGRESS:
        expected_fields = _STATUS_FIELDS
        expected_kind = STATUS
    elif outcome == REJECTED_PRE_FIT:
        expected_fields = _REJECTED_PRE_FIT_FIELDS
        expected_kind = TERMINAL
    elif outcome == FAILED_AFTER_START:
        expected_fields = _FAILED_AFTER_START_FIELDS
        expected_kind = TERMINAL
    elif outcome == SUCCEEDED:
        expected_fields = _SUCCEEDED_FIELDS
        expected_kind = TERMINAL
    else:
        expected_fields = set()
        expected_kind = None
        reasons.append('response_outcome_invalid')
    if set(snapshot) != expected_fields:
        reasons.append('response_payload_fields_invalid')
    if response_kind != expected_kind:
        reasons.append('response_kind_outcome_mismatch')
    if snapshot.get('schema_version') != RESPONSE_SCHEMA_VERSION:
        reasons.append('response_payload_schema_invalid')
    for field in ('request_hash', 'attempt_id', 'nonce_digest', 'trust_policy_snapshot_digest', 'runner_target_policy_hash'):
        if not _is_hash(snapshot.get(field)):
            reasons.append(field + '_invalid')
    if snapshot.get('attempt_id') != snapshot.get('request_hash'):
        reasons.append('response_attempt_id_mismatch')
    for field in ('audience', 'issuer_id', 'trust_policy_id', 'signing_key_id'):
        try:
            _identifier(snapshot.get(field), field + '_invalid')
        except AlrTrustedFitHandshakeError as exc:
            reasons.append(str(exc))
    for field in ('request_generation', 'trust_policy_epoch'):
        try:
            _positive_int(snapshot.get(field), field + '_invalid')
        except AlrTrustedFitHandshakeError as exc:
            reasons.append(str(exc))
    if snapshot.get('signature_algorithm') != 'ed25519':
        reasons.append('signature_algorithm_invalid')
    runner: dict[str, Any] = {}
    try:
        runner = _validated_runner_identity(snapshot.get('actual_runner_identity'))
        if runner['invocation_id'] != snapshot.get('request_hash'):
            reasons.append('runner_invocation_mismatch')
    except AlrTrustedFitHandshakeError as exc:
        reasons.append(str(exc))
    try:
        accepted_at = _parse_timestamp(_timestamp(snapshot.get('accepted_at'), 'accepted_at_invalid'))
    except AlrTrustedFitHandshakeError as exc:
        accepted_at = None
        reasons.append(str(exc))
    if runner and accepted_at is not None and _parse_timestamp(
        runner['captured_at']
    ) > accepted_at:
        reasons.append('runner_capture_time_invalid')
    if not _typed_equal(snapshot.get('no_authority'), _NO_AUTHORITY):
        reasons.append('no_authority_invalid')
    if not _typed_equal(snapshot.get('authority_counters'), _AUTHORITY_COUNTERS):
        reasons.append('authority_counters_invalid')
    if outcome == ACCEPTED_IN_PROGRESS:
        try:
            _positive_int(snapshot.get('status_generation'), 'status_generation_invalid')
        except AlrTrustedFitHandshakeError as exc:
            reasons.append(str(exc))
        try:
            status_issued = _parse_timestamp(_timestamp(snapshot.get('status_issued_at'), 'status_issued_at_invalid'))
            status_expires = _parse_timestamp(_timestamp(snapshot.get('status_expires_at'), 'status_expires_at_invalid'))
            if accepted_at is not None and (not accepted_at <= status_issued < status_expires):
                reasons.append('status_time_invalid')
        except AlrTrustedFitHandshakeError as exc:
            reasons.append(str(exc))
        reasons.extend(_stage_observation_reasons(snapshot.get('stage_observations')))
    elif outcome in {SUCCEEDED, REJECTED_PRE_FIT, FAILED_AFTER_START}:
        try:
            verified_at = _parse_timestamp(_timestamp(snapshot.get('issuer_verified_at'), 'issuer_verified_at_invalid'))
            receipt_expires = _parse_timestamp(_timestamp(snapshot.get('receipt_expires_at'), 'receipt_expires_at_invalid'))
            if not verified_at < receipt_expires:
                reasons.append('receipt_expiry_invalid')
        except AlrTrustedFitHandshakeError as exc:
            verified_at = None
            reasons.append(str(exc))
        if snapshot.get('automatic_retry_allowed') is not False:
            reasons.append('automatic_retry_invalid')
        if snapshot.get('persistence_allowed') is not False:
            reasons.append('persistence_invalid')
        expected_projection = outcome == SUCCEEDED
        if snapshot.get('v159_success_projection_allowed') is not expected_projection:
            reasons.append('v159_success_projection_invalid')
        if outcome == SUCCEEDED:
            reasons.extend(_succeeded_payload_reasons(snapshot, accepted_at, verified_at))
        elif outcome == REJECTED_PRE_FIT:
            if snapshot.get('failure_phase') not in _PRE_FIT_FAILURE_PHASES or snapshot.get('failure_code') not in _PRE_FIT_FAILURE_CODES:
                reasons.append('rejected_pre_fit_failure_invalid')
            if not all((snapshot.get(field) is False for field in ('actual_inputs_consumed', 'fit_started', 'model_training_performed'))):
                reasons.append('rejected_pre_fit_claims_invalid')
            if any((snapshot.get(field) is not None for field in ('result_observation', 'inner_receipt_bytes_base64url', 'inner_receipt_digest_sha256'))):
                reasons.append('rejected_pre_fit_v159_projection_invalid')
            try:
                rejected_at = _parse_timestamp(_timestamp(snapshot.get('rejected_at'), 'rejected_at_invalid'))
                if accepted_at is not None and verified_at is not None and (not accepted_at <= rejected_at <= verified_at):
                    reasons.append('rejected_at_order_invalid')
            except AlrTrustedFitHandshakeError as exc:
                reasons.append(str(exc))
        else:
            if snapshot.get('failure_phase') not in _AFTER_START_FAILURE_PHASES or snapshot.get('failure_code') not in _AFTER_START_FAILURE_CODES:
                reasons.append('failed_after_start_failure_invalid')
            elif snapshot.get('failure_code') not in _AFTER_START_FAILURE_PAIRS[snapshot['failure_phase']]:
                reasons.append('failed_after_start_failure_pair_invalid')
            reasons.extend(_stage_observation_reasons(snapshot.get('stage_observations')))
            stages = snapshot.get('stage_observations')
            if not isinstance(stages, Mapping) or not all((stages.get(field) is True for field in ('request_accepted', 'actual_inputs_consumed', 'fit_started'))):
                reasons.append('failed_after_start_claims_invalid')
            if isinstance(stages, Mapping):
                if stages.get('fit_completed') is not (snapshot.get('fit_completed_at') is not None) or stages.get('artifacts_written') is not (snapshot.get('captured_at') is not None):
                    reasons.append('failed_after_start_stage_evidence_mismatch')
                phase_stages = {
                    'FIT_EXECUTION': {'fit_completed': False},
                    'ARTIFACT_WRITE': {'fit_completed': True, 'artifacts_written': False},
                    'ARTIFACT_READBACK': {'fit_completed': True, 'artifacts_written': True, 'artifact_readback_completed': False},
                    'ONNX_VALIDATION': {'fit_completed': True, 'artifacts_written': True, 'artifact_readback_completed': True, 'onnx_semantic_validation_completed': False},
                    'OUTPUT_CONTRACT': {'onnx_semantic_validation_completed': True},
                }.get(snapshot.get('failure_phase'), {})
                if any(stages.get(field) is not expected for field, expected in phase_stages.items()):
                    reasons.append('failed_after_start_stage_evidence_mismatch')
            if snapshot.get('result_observation') is not None:
                reasons.append('failed_after_start_result_observation_invalid')
            if any((snapshot.get(field) is not None for field in ('inner_receipt_bytes_base64url', 'inner_receipt_digest_sha256'))):
                reasons.append('failed_after_start_v159_projection_invalid')
            try:
                fit_started_at = _parse_timestamp(_timestamp(snapshot.get('fit_started_at'), 'fit_started_at_invalid'))
                failure_observed = _parse_timestamp(_timestamp(snapshot.get('failure_observed_at'), 'failure_observed_at_invalid'))
                if accepted_at is not None and verified_at is not None and (not accepted_at <= fit_started_at <= failure_observed <= verified_at):
                    reasons.append('failed_after_start_time_invalid')
                previous = fit_started_at
                for field in ('fit_completed_at', 'captured_at'):
                    current_value = snapshot.get(field)
                    if current_value is None:
                        continue
                    current = _parse_timestamp(_timestamp(current_value, field + '_invalid'))
                    if current < previous or current > failure_observed:
                        reasons.append('failed_after_start_time_invalid')
                    previous = current
            except AlrTrustedFitHandshakeError as exc:
                reasons.append(str(exc))
    return _dedupe(reasons)

def _fit_contract_projection(value: Any, request_hash: Any) -> dict[str, Any]:
    contract = _snapshot_mapping(value, 'fit_capture_contract_not_mapping')
    validation = validate_alr_challenger_fit_capture_attestation_contract(contract)
    if not validation.valid:
        raise AlrTrustedFitHandshakeError('fit_capture_contract_invalid')
    (result, fit) = (contract['result_contract'], contract['fit_capture'])
    (submitted, actual) = (result['submitted_observation'], fit['actual_training_inputs'])
    runner = fit['runner_identity']
    if not all((value == request_hash for value in (submitted['attempt_id'], fit['attempt_id'], runner['invocation_id']))):
        raise AlrTrustedFitHandshakeError('fit_capture_request_identity_mismatch')
    artifacts = {item['quantile']: {'artifact_hash': item['artifact_hash'], 'artifact_size_bytes': item['artifact_size_bytes']} for item in fit['artifact_readback']}
    expected = result['expected_training_inputs']
    subject = {'durable_receipt_hash': expected['durable_receipt_hash'], 'training_key_hash': expected['training_key_hash'], 'result_hash': contract['result_hash'], 'fit_capture_hash': contract['fit_capture_hash'], 'candidate_attestation_hash': contract['attestation_hash'], 'training_run_hash': result['training_run_hash'], 'challenger_hash': result['challenger_hash'], 'runner_identity_hash': runner['runner_identity_hash'], 'actual_input_material_set_hash': actual['material_set_hash'], 'ordered_artifact_set_hash': fit['model_artifact_set_hash']}
    observation = {'source_head': actual['source_head'], 'actual_inputs': {'dataset_hash': actual['actual_dataset_hash'], 'row_ids_hash': actual['actual_row_ids_hash'], 'split_hash': actual['actual_split_hash'], 'code_manifest_hash': actual['actual_code_manifest_hash'], 'training_config_hash': actual['actual_training_config_hash'], 'feature_schema_hash': actual['actual_feature_schema_hash'], 'label_schema_hash': actual['actual_label_schema_hash'], 'training_rows': actual['actual_training_rows']}, 'model': {'model_schema_version': submitted['model_schema_version'], 'metrics_hash': submitted['metrics_hash'], 'resource_usage_hash': submitted['resource_usage_hash']}, 'fit_started_at': fit['fit_started_at'], 'fit_completed_at': fit['fit_completed_at'], 'artifacts': artifacts}
    admission = {'training_contract': result['admission']['training_contract'], 'qualified_receipt_read': result['admission']['qualified_receipt_read'], 'durable_receipt_hash': expected['durable_receipt_hash'], 'training_key_hash': expected['training_key_hash'], 'training_contract_hash': expected['training_contract_hash'], 'qualified_receipt_binding_hash': result['admission']['qualified_receipt_binding_hash']}
    return {'contract': contract, 'subject': subject, 'observation': observation, 'resource_observation': submitted['resource_observation'], 'admission': admission, 'expected_training_inputs': expected, 'fit_runner_identity': runner, 'fit_started_at': fit['fit_started_at'], 'fit_completed_at': fit['fit_completed_at'], 'captured_at': runner['captured_at']}

def _succeeded_payload_reasons(snapshot: Mapping[str, Any], accepted_at: datetime | None, verified_at: datetime | None) -> list[str]:
    reasons: list[str] = []
    claims = snapshot.get('v159_claims')
    if not isinstance(claims, Mapping) or set(claims) != _V159_CLAIM_FIELDS or (not all((claims.get(field) is True for field in _V159_CLAIM_FIELDS))):
        reasons.append('execution_claim_mismatch')
    subject = snapshot.get('v159_subject')
    if not isinstance(subject, Mapping) or set(subject) != _V159_SUBJECT_FIELDS or any((not _is_hash(subject.get(field)) for field in _V159_SUBJECT_FIELDS)):
        reasons.append('v159_inner_receipt_mismatch')
    try:
        fit_projection = _fit_contract_projection(snapshot.get('fit_capture_contract'), snapshot.get('request_hash'))
    except AlrTrustedFitHandshakeError as exc:
        fit_projection = {}
        reasons.append(str(exc))
    if fit_projection:
        projection_pairs = ((snapshot.get('v159_subject'), fit_projection['subject']), (snapshot.get('result_observation'), fit_projection['observation']), (snapshot.get('resource_observation'), fit_projection['resource_observation']), (snapshot.get('fit_started_at'), fit_projection['fit_started_at']), (snapshot.get('fit_completed_at'), fit_projection['fit_completed_at']), (snapshot.get('captured_at'), fit_projection['captured_at']), (snapshot.get('actual_input_material_set_hash'), fit_projection['subject']['actual_input_material_set_hash']), (snapshot.get('ordered_artifact_set_hash'), fit_projection['subject']['ordered_artifact_set_hash']), (snapshot.get('no_authority'), fit_projection['contract']['no_authority']), (snapshot.get('authority_counters'), fit_projection['contract']['authority_counters']))
        if not all((_typed_equal(left, right) for (left, right) in projection_pairs)):
            reasons.append('fit_capture_contract_binding_mismatch')
        actual_runner = snapshot.get('actual_runner_identity')
        fit_runner = fit_projection['fit_runner_identity']
        stable_runner_fields = (
            'producer_kind', 'producer_id', 'runner_version', 'runner_source_hash',
            'host_identity_hash', 'environment_identity_hash',
            'process_identity_hash', 'invocation_id'
        )
        if not isinstance(actual_runner, Mapping) or any(
            not _typed_equal(actual_runner.get(field), fit_runner.get(field))
            for field in stable_runner_fields
        ):
            reasons.append('fit_runner_identity_mismatch')
    try:
        inner_bytes = strict_base64url_decode(snapshot.get('inner_receipt_bytes_base64url'), max_bytes=1048576)
        if len(inner_bytes) < 2 or hashlib.sha256(inner_bytes).hexdigest() != snapshot.get('inner_receipt_digest_sha256'):
            reasons.append('v159_inner_receipt_mismatch')
        inner = parse_canonical_v159_jsonb_text_bytes(inner_bytes, max_bytes=1048576)
        reasons.extend(_v159_inner_reasons(inner))
    except AlrTrustedFitHandshakeError:
        inner = {}
        reasons.append('v159_inner_receipt_mismatch')
    if inner:
        equality_pairs = ((snapshot.get('v159_subject'), inner.get('subject')), (snapshot.get('v159_claims'), inner.get('claims')), (snapshot.get('result_observation'), inner.get('result_observation')), (snapshot.get('issuer_id'), _nested(inner, 'authentication', 'issuer_id')), (snapshot.get('trust_policy_id'), _nested(inner, 'authentication', 'trust_policy_id')), (snapshot.get('signing_key_id'), _nested(inner, 'authentication', 'signature_key_id')), (snapshot.get('signature_algorithm'), _nested(inner, 'authentication', 'signature_algorithm')), (snapshot.get('issuer_verified_at'), inner.get('verified_at')), (snapshot.get('receipt_expires_at'), inner.get('expires_at')), (snapshot.get('no_authority'), inner.get('no_authority')), (snapshot.get('authority_counters'), inner.get('authority_counters')))
        if not all((_typed_equal(left, right) for (left, right) in equality_pairs)):
            reasons.append('v159_inner_receipt_mismatch')
    if isinstance(subject, Mapping):
        if snapshot.get('actual_input_material_set_hash') != subject.get('actual_input_material_set_hash') or snapshot.get('ordered_artifact_set_hash') != subject.get('ordered_artifact_set_hash'):
            reasons.append('v159_inner_receipt_mismatch')
    try:
        fit_started = _parse_timestamp(_timestamp(snapshot.get('fit_started_at'), 'fit_started_at_invalid'))
        fit_completed = _parse_timestamp(_timestamp(snapshot.get('fit_completed_at'), 'fit_completed_at_invalid'))
        captured = _parse_timestamp(_timestamp(snapshot.get('captured_at'), 'captured_at_invalid'))
        if accepted_at is not None and verified_at is not None and (not accepted_at <= fit_started <= fit_completed <= captured <= verified_at):
            reasons.append('succeeded_time_invalid')
        elapsed = fit_completed - fit_started
        elapsed_microseconds = (
            elapsed.days * 86400000000
            + elapsed.seconds * 1000000
            + elapsed.microseconds
        )
        resources = snapshot.get('resource_observation')
        if not isinstance(resources, Mapping) or resources.get('wall_time_microseconds') != elapsed_microseconds:
            reasons.append('resource_wall_time_mismatch')
    except AlrTrustedFitHandshakeError as exc:
        reasons.append(str(exc))
    observation = snapshot.get('result_observation')
    if isinstance(observation, Mapping):
        if observation.get('fit_started_at') != snapshot.get('fit_started_at') or observation.get('fit_completed_at') != snapshot.get('fit_completed_at'):
            reasons.append('v159_inner_receipt_mismatch')
        ordered_hash = _ordered_artifact_set_hash(observation.get('artifacts'))
        if ordered_hash != snapshot.get('ordered_artifact_set_hash'):
            reasons.append('v159_inner_receipt_mismatch')
    if not _valid_resource_observation(snapshot.get('resource_observation')):
        reasons.append('resource_observation_invalid')
    return _dedupe(reasons)

def _v159_inner_reasons(value: Any) -> list[str]:
    if not isinstance(value, Mapping) or set(value) != _V159_FIELDS:
        return ['v159_inner_receipt_mismatch']
    reasons: list[str] = []
    fixed = {'schema_version': 'alr_fit_execution_signed_receipt_v1', 'evidence_tier': 'PLATFORM_OR_EXTERNAL_ATTESTED', 'claim_kind': 'ALR_FIT_EXECUTION_ATTESTATION_V1', 'authentication_status': 'SIGNATURE_VERIFIED_BY_TRUST_POLICY'}
    if any((not _typed_equal(value.get(field), expected) for (field, expected) in fixed.items())):
        reasons.append('v159_inner_receipt_mismatch')
    subject = value.get('subject')
    if not isinstance(subject, Mapping) or set(subject) != _V159_SUBJECT_FIELDS or any((not _is_hash(subject.get(field)) for field in _V159_SUBJECT_FIELDS)):
        reasons.append('v159_inner_receipt_mismatch')
    claims = value.get('claims')
    if not isinstance(claims, Mapping) or set(claims) != _V159_CLAIM_FIELDS or (not all((claims.get(field) is True for field in _V159_CLAIM_FIELDS))):
        reasons.append('execution_claim_mismatch')
    reasons.extend(_v159_observation_reasons(value.get('result_observation')))
    authentication = value.get('authentication')
    if not isinstance(authentication, Mapping) or set(authentication) != _V159_AUTHENTICATION_FIELDS:
        reasons.append('v159_inner_receipt_mismatch')
    else:
        for field in ('issuer_id', 'trust_policy_id', 'signature_key_id'):
            try:
                _identifier(authentication.get(field), field + '_invalid')
            except AlrTrustedFitHandshakeError:
                reasons.append('v159_inner_receipt_mismatch')
        if authentication.get('signature_algorithm') != 'ed25519':
            reasons.append('v159_inner_signature_invalid')
        try:
            strict_base64url_decode(authentication.get('signature'), expected_bytes=64, max_bytes=64)
        except AlrTrustedFitHandshakeError:
            reasons.append('v159_inner_signature_invalid')
    try:
        verified = _parse_timestamp(_timestamp(value.get('verified_at'), 'verified_at_invalid'))
        expires = _parse_timestamp(_timestamp(value.get('expires_at'), 'expires_at_invalid'))
        if not verified < expires:
            reasons.append('v159_inner_receipt_mismatch')
    except AlrTrustedFitHandshakeError:
        reasons.append('v159_inner_receipt_mismatch')
    if not _typed_equal(value.get('no_authority'), _NO_AUTHORITY) or not _typed_equal(value.get('authority_counters'), _AUTHORITY_COUNTERS):
        reasons.append('authority_mismatch')
    return _dedupe(reasons)

def _v159_observation_reasons(value: Any) -> list[str]:
    if not isinstance(value, Mapping) or set(value) != _V159_OBSERVATION_FIELDS:
        return ['v159_inner_receipt_mismatch']
    reasons: list[str] = []
    if type(value.get('source_head')) is not str or _HEAD_RE.fullmatch(value['source_head']) is None:
        reasons.append('v159_inner_receipt_mismatch')
    actual = value.get('actual_inputs')
    if not isinstance(actual, Mapping) or set(actual) != _V159_ACTUAL_INPUT_FIELDS:
        reasons.append('v159_inner_receipt_mismatch')
    elif any((not _is_hash(actual.get(field)) for field in _V159_ACTUAL_INPUT_FIELDS - {'training_rows'})) or type(actual.get('training_rows')) is not int or actual['training_rows'] <= 0:
        reasons.append('v159_inner_receipt_mismatch')
    model = value.get('model')
    if not isinstance(model, Mapping) or set(model) != _V159_MODEL_FIELDS:
        reasons.append('v159_inner_receipt_mismatch')
    else:
        try:
            _identifier(model.get('model_schema_version'), 'model_schema_version_invalid')
        except AlrTrustedFitHandshakeError:
            reasons.append('v159_inner_receipt_mismatch')
        if not _is_hash(model.get('metrics_hash')) or not _is_hash(model.get('resource_usage_hash')):
            reasons.append('v159_inner_receipt_mismatch')
    for field in ('fit_started_at', 'fit_completed_at'):
        try:
            _timestamp(value.get(field), field + '_invalid')
        except AlrTrustedFitHandshakeError:
            reasons.append('v159_inner_receipt_mismatch')
    if _ordered_artifact_set_hash(value.get('artifacts')) is None:
        reasons.append('v159_inner_receipt_mismatch')
    return _dedupe(reasons)

def _ordered_artifact_set_hash(value: Any) -> str | None:
    if not isinstance(value, Mapping) or set(value) != {'q10', 'q50', 'q90'}:
        return None
    hashes: list[str] = []
    for quantile in ('q10', 'q50', 'q90'):
        artifact = value.get(quantile)
        if not isinstance(artifact, Mapping) or set(artifact) != _V159_ARTIFACT_FIELDS or (not _is_hash(artifact.get('artifact_hash'))) or (type(artifact.get('artifact_size_bytes')) is not int) or (artifact['artifact_size_bytes'] <= 0):
            return None
        hashes.append(artifact['artifact_hash'])
    if len(set(hashes)) != 3:
        return None
    return hashlib.sha256(f'q10={hashes[0]}\nq50={hashes[1]}\nq90={hashes[2]}\n'.encode('ascii')).hexdigest()

def _valid_resource_observation(value: Any) -> bool:
    if not isinstance(value, Mapping) or set(value) != _RESOURCE_OBSERVATION_FIELDS:
        return False
    if any((type(value.get(field)) is not int or value[field] < 0 for field in value)):
        return False
    return value['wall_time_microseconds'] > 0 and value['cpu_time_microseconds'] > 0 and (value['peak_memory_bytes'] > 0) and (value['total_artifact_bytes'] > 0) and (value['training_rows'] > 0) and (value['external_request_count'] == 0) and (value['api_cost_microusd'] == 0)

def _nested(value: Mapping[str, Any], outer: str, inner: str) -> Any:
    nested = value.get(outer)
    return nested.get(inner) if isinstance(nested, Mapping) else None

def _validated_runner_identity(value: Any) -> dict[str, Any]:
    snapshot = _snapshot_mapping(value, 'actual_runner_identity_not_mapping')
    if set(snapshot) != _RUNNER_IDENTITY_FIELDS:
        raise AlrTrustedFitHandshakeError('actual_runner_identity_fields_invalid')
    if snapshot.get('schema_version') != 'alr_isolated_runner_identity_v1':
        raise AlrTrustedFitHandshakeError('actual_runner_identity_schema_invalid')
    for field in ('producer_kind', 'producer_id', 'runner_version', 'isolation_class', 'capability_class'):
        _identifier(snapshot.get(field), field + '_invalid')
    for field in ('runner_source_hash', 'host_identity_hash', 'environment_identity_hash', 'process_identity_hash', 'measurement_hash', 'output_contract_hash', 'invocation_id', 'runner_identity_hash'):
        _hash(snapshot.get(field), field + '_invalid')
    _timestamp(snapshot.get('captured_at'), 'runner_captured_at_invalid')
    unsigned = {key: value for (key, value) in snapshot.items() if key != 'runner_identity_hash'}
    if snapshot['runner_identity_hash'] != domain_hash('actual_runner_identity', unsigned):
        raise AlrTrustedFitHandshakeError('runner_identity_hash_invalid')
    return snapshot

def _stage_observation_reasons(value: Any) -> list[str]:
    if not isinstance(value, Mapping) or set(value) != _STAGE_FIELDS:
        return ['stage_observations_invalid']
    ordered = ('request_accepted', 'actual_inputs_consumed', 'fit_started', 'fit_completed', 'artifacts_written', 'artifact_readback_completed', 'onnx_semantic_validation_completed')
    values = [value.get(field) for field in ordered]
    if any((type(item) is not bool for item in values)):
        return ['stage_observations_invalid']
    seen_false = False
    for item in values:
        if item is False:
            seen_false = True
        elif seen_false:
            return ['stage_observations_nonmonotonic']
    if values[0] is not True:
        return ['stage_observations_invalid']
    return []

def _runner_target_matches(payload: Mapping[str, Any], request: Mapping[str, Any]) -> bool:
    runner = payload.get('actual_runner_identity')
    target = _nested(request, 'signed_payload', 'runner_target_policy')
    if not isinstance(runner, Mapping) or not isinstance(target, Mapping):
        return False
    return all((_typed_equal(runner.get(field), target.get(field)) for field in ('producer_kind', 'producer_id', 'runner_source_hash', 'measurement_hash', 'isolation_class', 'capability_class', 'output_contract_hash')))

def _response_matches_request(payload: Mapping[str, Any], request: Mapping[str, Any]) -> bool:
    request_payload = request['signed_payload']
    pairs = ((payload.get('request_hash'), request.get('request_hash')), (payload.get('attempt_id'), request.get('request_hash')), (payload.get('nonce_digest'), request_payload.get('nonce_digest')), (payload.get('request_generation'), request_payload.get('request_generation')), (payload.get('audience'), request_payload.get('audience')), (payload.get('issuer_id'), request_payload.get('issuer_id')), (payload.get('trust_policy_id'), request_payload.get('trust_policy_id')), (payload.get('trust_policy_snapshot_digest'), request_payload.get('trust_policy_snapshot_digest')), (payload.get('trust_policy_epoch'), request_payload.get('trust_policy_epoch')), (payload.get('signature_algorithm'), request_payload.get('signature_algorithm')), (payload.get('signing_key_id'), request_payload.get('signing_key_id')), (payload.get('runner_target_policy_hash'), request_payload.get('runner_target_policy_hash')))
    if not all((_typed_equal(left, right) for (left, right) in pairs)):
        return False
    runner = payload.get('actual_runner_identity')
    if not isinstance(runner, Mapping) or not _runner_target_matches(payload, request):
        return False
    runner_pairs = ((runner.get('invocation_id'), request.get('request_hash')),)
    if not all((_typed_equal(left, right) for (left, right) in runner_pairs)):
        return False
    if payload.get('outcome') != SUCCEEDED:
        return True
    subject = payload.get('v159_subject')
    observation = payload.get('result_observation')
    expected = request_payload.get('expected_training_inputs')
    resources = payload.get('resource_observation')
    budget = request_payload.get('resource_budget')
    if not all((isinstance(value, Mapping) for value in (subject, observation, expected, resources, budget))):
        return False
    try:
        fit_projection = _fit_contract_projection(payload.get('fit_capture_contract'), request.get('request_hash'))
    except AlrTrustedFitHandshakeError:
        return False
    if not _typed_equal(fit_projection['admission'], request_payload.get('admission')) or not _typed_equal(fit_projection['expected_training_inputs'], expected):
        return False
    if subject.get('durable_receipt_hash') != expected.get('durable_receipt_hash') or subject.get('training_key_hash') != expected.get('training_key_hash') or observation.get('source_head') != expected.get('source_head'):
        return False
    actual = observation.get('actual_inputs')
    if not isinstance(actual, Mapping):
        return False
    for field in _V159_ACTUAL_INPUT_FIELDS:
        if not _typed_equal(actual.get(field), expected.get(field)):
            return False
    artifacts = observation.get('artifacts')
    if not isinstance(artifacts, Mapping):
        return False
    total_artifact_bytes = sum((artifact.get('artifact_size_bytes', -1) for artifact in artifacts.values() if isinstance(artifact, Mapping)))
    return resources.get('training_rows') == expected.get('training_rows') and resources.get('training_rows') <= budget.get('max_training_rows') and (resources.get('external_request_count') == 0) and (resources.get('api_cost_microusd') == 0) and (resources.get('wall_time_microseconds') <= budget.get('max_wall_seconds') * 1000000) and (resources.get('cpu_time_microseconds') <= budget.get('max_cpu_seconds') * 1000000) and (resources.get('peak_memory_bytes') <= budget.get('max_memory_bytes')) and (resources.get('total_artifact_bytes') == total_artifact_bytes) and (total_artifact_bytes <= budget.get('max_artifact_bytes')) and ((_parse_timestamp(payload['fit_completed_at']) - _parse_timestamp(payload['fit_started_at'])).total_seconds() <= budget.get('max_wall_seconds'))

def _pinned_key_for_request(request: Mapping[str, Any]) -> Mapping[str, Any] | None:
    payload = request['signed_payload']
    policy = payload['trust_policy_snapshot']
    matches = [key for key in policy['allowed_keys'] if key['issuer_id'] == payload['issuer_id'] and key['key_id'] == payload['signing_key_id'] and (key['algorithm'] == 'ed25519')]
    return matches[0] if len(matches) == 1 else None

def _fixture_signature_matches(verifier: SyntheticSignatureVerifier, label: str, public_key: bytes, signature: bytes, preimage: bytes) -> bool:
    try:
        return verifier(label, public_key, signature, preimage) is True
    except Exception:
        return False

def _v159_inner_fixture_signature_matches(payload: Mapping[str, Any], public_key: bytes, verifier: SyntheticSignatureVerifier) -> bool | None:
    try:
        inner_bytes = strict_base64url_decode(payload.get('inner_receipt_bytes_base64url'), max_bytes=1048576)
        inner = parse_canonical_v159_jsonb_text_bytes(inner_bytes, max_bytes=1048576)
    except AlrTrustedFitHandshakeError:
        return None
    try:
        authentication = _snapshot_mapping(inner.get('authentication'), 'v159_inner_authentication_invalid')
        inner_signature = strict_base64url_decode(authentication.get('signature'), expected_bytes=64, max_bytes=64)
        preimage = v159_inner_signature_preimage(inner)
    except AlrTrustedFitHandshakeError:
        return False
    return _fixture_signature_matches(verifier, 'v159_inner', public_key, inner_signature, preimage)

def _response_outer_signature_material(response: Mapping[str, Any], request: Mapping[str, Any]) -> tuple[dict[str, Any], bytes]:
    try:
        payload = _snapshot_mapping(response.get('signed_payload'), 'response_signature_payload_invalid')
        authentication = _snapshot_mapping(response.get('authentication'), 'response_authentication_invalid')
    except Exception as exc:
        if isinstance(exc, AlrTrustedFitHandshakeError):
            raise
        raise AlrTrustedFitHandshakeError('response_authentication_invalid') from exc
    if set(authentication) != _RESPONSE_AUTHENTICATION_FIELDS or authentication.get('algorithm') != 'ed25519' or authentication.get('key_id') != _nested(request, 'signed_payload', 'signing_key_id'):
        raise AlrTrustedFitHandshakeError('response_authentication_invalid')
    try:
        signature = strict_base64url_decode(authentication.get('signature'), expected_bytes=64, max_bytes=64)
        terminal_receipt_signature_preimage(payload)
    except AlrTrustedFitHandshakeError as exc:
        raise AlrTrustedFitHandshakeError('response_signature_invalid') from exc
    return (payload, signature)

def _response_pre_inner_failure_code(reasons: tuple[str, ...]) -> str | None:
    if not reasons:
        return None
    if 'signature_invalid' in reasons or 'response_authentication_invalid' in reasons:
        return RECEIPT_SIGNATURE_INVALID
    structural_reasons = {
        'response_fields_invalid', 'response_payload_not_mapping',
        'response_payload_fields_invalid', 'response_schema_invalid',
        'response_payload_schema_invalid', 'response_envelope_binding_invalid',
        'response_kind_outcome_mismatch', 'response_outcome_invalid',
        'bound_request_invalid',
    }
    if any(reason in structural_reasons for reason in reasons):
        return RECEIPT_OUTCOME_INVALID
    if 'receipt_request_binding_mismatch' in reasons or 'fit_capture_request_identity_mismatch' in reasons:
        return RECEIPT_REQUEST_BINDING_MISMATCH
    if any(('time' in reason or 'expiry' in reason or reason.endswith('_at_invalid') for reason in reasons)):
        return RECEIPT_TIME_INVALID
    runner_reasons = {
        'runner_target_mismatch', 'fit_runner_identity_mismatch',
        'runner_invocation_mismatch', 'runner_identity_hash_invalid',
        'actual_runner_identity_not_mapping',
        'actual_runner_identity_fields_invalid',
        'actual_runner_identity_schema_invalid',
    }
    if any(reason in runner_reasons or reason.startswith('actual_runner_') for reason in reasons):
        return RUNNER_TARGET_MISMATCH
    return None

def _response_failure_code(reasons: tuple[str, ...]) -> str:
    if 'signature_invalid' in reasons or 'response_authentication_invalid' in reasons:
        return RECEIPT_SIGNATURE_INVALID
    if 'receipt_request_binding_mismatch' in reasons or 'fit_capture_request_identity_mismatch' in reasons:
        return RECEIPT_REQUEST_BINDING_MISMATCH
    if any(('time' in reason or 'expiry' in reason or reason.endswith('_at_invalid') for reason in reasons)):
        return RECEIPT_TIME_INVALID
    if any((reason in {'runner_target_mismatch', 'fit_runner_identity_mismatch', 'runner_invocation_mismatch', 'runner_identity_hash_invalid'} or reason.startswith('actual_runner_') for reason in reasons)):
        return RUNNER_TARGET_MISMATCH
    if 'v159_inner_signature_invalid' in reasons:
        return V159_INNER_SIGNATURE_INVALID
    if 'v159_inner_receipt_mismatch' in reasons:
        return V159_INNER_RECEIPT_MISMATCH
    if 'execution_claim_mismatch' in reasons:
        return EXECUTION_CLAIM_MISMATCH
    if any(('authority' in reason for reason in reasons)):
        return AUTHORITY_MISMATCH
    return RECEIPT_OUTCOME_INVALID

def _response_time_matches_request(payload: Mapping[str, Any], request: Mapping[str, Any], adjudicated: datetime) -> bool:
    try:
        request_payload = request['signed_payload']
        not_before = _parse_timestamp(request_payload['not_before'])
        accept_by = _parse_timestamp(request_payload['accept_by'])
        complete_by = _parse_timestamp(request_payload['complete_by'])
        accepted = _parse_timestamp(payload['accepted_at'])
        if not not_before <= accepted <= accept_by:
            return False
        runner = payload['actual_runner_identity']
        if not isinstance(runner, Mapping) or not not_before <= _parse_timestamp(runner['captured_at']) <= accepted:
            return False
        if payload['response_kind'] == STATUS:
            return _parse_timestamp(payload['status_issued_at']) <= adjudicated < _parse_timestamp(payload['status_expires_at']) <= complete_by
        if not _parse_timestamp(payload['issuer_verified_at']) <= adjudicated < _parse_timestamp(payload['receipt_expires_at']):
            return False
        if payload['outcome'] == SUCCEEDED:
            return _parse_timestamp(payload['fit_started_at']) <= accept_by and _parse_timestamp(payload['fit_completed_at']) <= complete_by
        if payload['outcome'] == REJECTED_PRE_FIT:
            return _parse_timestamp(payload['rejected_at']) <= complete_by
        return _parse_timestamp(payload['failure_observed_at']) <= complete_by
    except (KeyError, TypeError, ValueError):
        return False

def _verification_failure(code: str, *reasons: str, request_hash: str | None=None, response_kind: str | None=None, outcome: str | None=None, fixture_signatures_matched: bool=False) -> AlrTrustedFitHandshakeVerification:
    return AlrTrustedFitHandshakeVerification(valid=False, code=code, verdict=EXTERNAL_HOST_UNCHECKED, reasons=tuple(reasons) or (code,), request_hash=request_hash, response_kind=response_kind, outcome=outcome, terminal=response_kind == TERMINAL, fixture_signatures_matched=fixture_signatures_matched, signatures_valid=False, capability_authenticity=EXTERNAL_HOST_UNCHECKED, persistence_allowed=False, authority_granted=False, model_training_performed_claim=NOT_ESTABLISHED, durable_consumption_required=False)

def _snapshot_mapping(value: Any, reason: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AlrTrustedFitHandshakeError(reason)
    try:
        snapshot = copy.deepcopy(dict(value))
        canonical_outer_json_bytes(snapshot)
    except Exception as exc:
        raise AlrTrustedFitHandshakeError(reason) from exc
    return snapshot

def _identifier(value: Any, reason: str) -> str:
    if type(value) is not str or _IDENTIFIER_RE.fullmatch(value) is None:
        raise AlrTrustedFitHandshakeError(reason)
    return value

def _hash(value: Any, reason: str) -> str:
    if type(value) is not str or _HASH_RE.fullmatch(value) is None:
        raise AlrTrustedFitHandshakeError(reason)
    return value

def _is_hash(value: Any) -> bool:
    return type(value) is str and _HASH_RE.fullmatch(value) is not None

def _positive_int(value: Any, reason: str) -> int:
    if type(value) is not int or value <= 0:
        raise AlrTrustedFitHandshakeError(reason)
    return value

def _literal_bool(value: Any, reason: str) -> bool:
    if type(value) is not bool:
        raise AlrTrustedFitHandshakeError(reason)
    return value

def _nonce(value: Any) -> str:
    if type(value) is not str or _NONCE_RE.fullmatch(value) is None:
        raise AlrTrustedFitHandshakeError('request_nonce_invalid')
    return value

def _nonce_digest(nonce: str) -> str:
    return hashlib.sha256(_HASH_NAMESPACE + b'nonce\x00' + bytes.fromhex(nonce)).hexdigest()

def _timestamp(value: Any, reason: str) -> str:
    if type(value) is not str or _UTC_TIMESTAMP_RE.fullmatch(value) is None:
        raise AlrTrustedFitHandshakeError(reason)
    try:
        _parse_timestamp(value)
    except (ValueError, OverflowError) as exc:
        raise AlrTrustedFitHandshakeError(reason) from exc
    return value

def _parse_timestamp(value: str) -> datetime:
    return datetime.strptime(value, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc)

def _key_status(value: Any) -> str:
    if type(value) is not str or value not in _KEY_STATUSES:
        raise AlrTrustedFitHandshakeError('key_status_invalid')
    return value

def _typed_equal(first: Any, second: Any) -> bool:
    if type(first) is not type(second):
        return False
    if isinstance(first, Mapping):
        if set(first) != set(second):
            return False
        return all((_typed_equal(first[key], second[key]) for key in first))
    if type(first) is list:
        return len(first) == len(second) and all((_typed_equal(left, right) for (left, right) in zip(first, second)))
    return first == second

def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result

def _invalid_validation(*reasons: str, request_hash: str | None=None) -> AlrTrustedFitHandshakeValidation:
    normalized = tuple((reason for reason in reasons if reason)) or ('invalid',)
    return AlrTrustedFitHandshakeValidation(valid=False, verdict=INVALID, reason=normalized[0], reasons=normalized, request_hash=request_hash)

def _valid_validation(*, request_hash: str | None=None) -> AlrTrustedFitHandshakeValidation:
    return AlrTrustedFitHandshakeValidation(valid=True, verdict=VALID, reason='validated', reasons=(), request_hash=request_hash)

def _raise_canonical_error() -> Any:
    raise AlrTrustedFitHandshakeError(CANONICAL_BYTES_INVALID)
__all__ = '\nACTIVE ACCEPTED_IN_PROGRESS AUDIENCE_MISMATCH AUTHENTICATED_UNCONSUMED AUTHORITY_MISMATCH\nAlrTrustedFitHandshakeError AlrTrustedFitHandshakeValidation AlrTrustedFitHandshakeVerification\nCANONICAL_BYTES_INVALID DURABLE_CONSUMPTION_CONFLICT DURABLE_CONSUMPTION_REQUIRED EXACT_REPLAY\nEXECUTION_CLAIM_MISMATCH EXTERNAL_HOST_UNCHECKED FAILED_AFTER_START HANDSHAKE_SIGNING_USAGE INVALID\nKEY_STATUS_OVERLAY_SCHEMA_VERSION NEW_REQUEST NONCE_REPLAY_CONFLICT NOT_ESTABLISHED POLICY_OR_KEY_REJECTED\nRECEIPT_OUTCOME_INVALID RECEIPT_REQUEST_BINDING_MISMATCH RECEIPT_SIGNATURE_INVALID RECEIPT_TIME_INVALID\nRECONCILE_REQUIRED REJECTED_PRE_FIT REQUEST_EXPIRED REQUEST_NOT_YET_VALID REQUEST_SCHEMA_VERSION\nREQUEST_SIGNATURE_DOMAIN REQUEST_SIGNATURE_INVALID RESPONSE_SCHEMA_VERSION RETIRED RUNNER_TARGET_MISMATCH\nSTATUS STRUCTURE_INVALID SUCCEEDED TERMINAL TERMINAL_RECEIPT_SIGNATURE_DOMAIN TRUST_POLICY_SCHEMA_VERSION VALID\nV159_INNER_RECEIPT_MISMATCH V159_INNER_SIGNATURE_DOMAIN V159_INNER_SIGNATURE_INVALID\nbuild_key_status_overlay build_isolated_fit_execution_response build_trust_policy_snapshot\nbuild_trusted_fit_execution_request build_trusted_fit_request_payload canonical_outer_json_bytes\ncanonical_v159_jsonb_text_bytes classify_request_replay classify_response_replay domain_hash\nparse_canonical_outer_json parse_canonical_v159_jsonb_text_bytes request_signature_preimage\nstrict_base64url_decode terminal_receipt_signature_preimage validate_key_status_overlay\nvalidate_isolated_fit_execution_response validate_trusted_fit_execution_request validate_trusted_fit_request_bytes\nverify_isolated_fit_response v159_inner_signature_preimage\n'.split()
