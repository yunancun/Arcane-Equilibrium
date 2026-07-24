"""Source-only admission contract for a future isolated ALR challenger trainer.

This module deliberately performs no fit, file read, database access, registry
write, symlink update, serving action, or promotion.  It accepts only the
repository-derived ``candidate_proof_repository_receipt_v1`` shape and binds
its canonical proof/reward/PIT lineage to an explicit code manifest, effective
training configuration, and resource budget.

The current repository receipt is intentionally non-durable.  Therefore a
successfully built contract has ``status=SCHEMA_REQUIRED`` and cannot authorize
training.  A forward schema plus a repository recheck must convert this source
contract into a durable admission before any trainer may emit
``model_training_performed=true``.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ml_training.candidate_proof_adapter import (
    READY_FOR_REWARD_VALIDATION,
    SELECTION_PROOF_BINDING_SCHEMA_VERSION,
    compute_candidate_proof_adapter_hash,
    compute_selection_proof_binding_hash,
    derive_selected_candidate_proof_identity,
)
from ml_training.candidate_proof_repository import (
    RECEIPT_SCHEMA_VERSION,
    compute_candidate_proof_repository_receipt_hash,
)
from ml_training.pit_dataset_manifest import (
    compute_pit_dataset_manifest_hash,
    validate_pit_dataset_manifest,
)
from ml_training.proof_packet_contract import (
    PROOF_READY,
    compute_proof_packet_hash,
    validate_proof_packet,
)
from ml_training.reward_ledger import (
    REWARD_KIND_AFTER_COST_REALIZED_DEMO,
    compute_reward_record_hash,
    validate_reward_record,
)


ALR_CHALLENGER_TRAINING_CONTRACT_SCHEMA_VERSION = (
    "alr_challenger_training_contract_v1"
)
CODE_MANIFEST_SCHEMA_VERSION = "alr_challenger_code_manifest_v1"
TRAINING_CONFIG_SCHEMA_VERSION = "alr_challenger_training_config_v1"

SCHEMA_REQUIRED = "SCHEMA_REQUIRED"
INVALID = "INVALID"

_REQUIRED_MODULE_HASHES = (
    "pit_dataset_manifest.py",
    "quantile_trainer.py",
    "run_training_pipeline.py",
    "model_registry.py",
)
_REQUIRED_QUANTILES = ("q10", "q50", "q90")
_PROJECTION_REF_FIELDS = {
    "projection_hash",
    "artifact_kind",
    "artifact_hash",
    "decision_hash",
    "source_set_hash",
    "handoff_hash",
    "durable_receipt_status",
}
_SELECTION_BINDING_FIELDS = {
    "schema_version",
    "projection_hash",
    "artifact_hash",
    "decision_hash",
    "source_set_hash",
    "handoff_hash",
    "candidate_id",
    "context_id",
    "selected_candidate",
    "binding_hash",
}
_REQUIRED_TRAINING_PARAMETER_KEYS = {
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
    "schema_version",
}
_RESOURCE_BUDGET_KEYS = {
    "max_wall_seconds",
    "max_cpu_seconds",
    "max_memory_bytes",
    "max_artifact_bytes",
    "max_training_rows",
    "max_external_requests",
    "max_api_cost_usd",
}
_POSITIVE_RESOURCE_KEYS = {
    "max_wall_seconds",
    "max_cpu_seconds",
    "max_memory_bytes",
    "max_artifact_bytes",
    "max_training_rows",
}
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_HEAD_RE = re.compile(r"^[0-9a-f]{40}$")
# LR1(S2.2A):spawn 綁定的 scoped learning identity(== learning_runtime_manifest.self_digest)。
_LEARNING_RUNTIME_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

_NO_AUTHORITY = {
    "exchange_authority": False,
    "trading_authority": False,
    "order_or_probe_authority": False,
    "decision_lease_authority": False,
    "cost_gate_authority": False,
    "proof_authority": False,
    "serving_authority": False,
    "promotion_authority": False,
    "latest_authority": False,
    "runtime_mutation_authority": False,
    "database_write_authority": False,
    "symlink_authority": False,
}
_AUTHORITY_COUNTERS = {
    "exchange_contact_count": 0,
    "trading_action_count": 0,
    "order_or_probe_count": 0,
    "decision_lease_count": 0,
    "cost_gate_change_count": 0,
    "proof_claim_count": 0,
    "serving_or_promotion_count": 0,
    "runtime_mutation_count": 0,
    "database_write_count": 0,
    "symlink_update_count": 0,
    "model_fit_count": 0,
}
_EXECUTION_CONTRACT = {
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

_AUTHORITY_TRUE_KEYS = {
    "cost_gate_change_performed",
    "cost_gate_lowering_allowed",
    "db_write_allowed",
    "db_write_performed",
    "deploy_allowed",
    "deploy_performed",
    "exchange_contact_performed",
    "exchange_private_read_performed",
    "latest_authority_granted",
    "live_allowed",
    "live_authority_granted",
    "live_enabled",
    "mainnet_allowed",
    "mainnet_enabled",
    "order_allowed",
    "order_authority_granted",
    "order_or_probe_performed",
    "private_read_allowed",
    "probe_allowed",
    "probe_authority_granted",
    "promotion_allowed",
    "promotion_authority_granted",
    "promotion_enabled",
    "runtime_mutation_allowed",
    "runtime_mutation_performed",
    "secret_access_allowed",
    "serving_authority_granted",
    "serving_reload_allowed",
    "symlink_allowed",
    "symlink_promotion_allowed",
}
_AUTHORITY_TERMS = (
    "cost_gate",
    "database_write",
    "db_write",
    "deploy",
    "exchange",
    "latest",
    "live",
    "mainnet",
    "order",
    "private_read",
    "probe",
    "promotion",
    "runtime",
    "serving",
    "symlink",
)
_AUTHORITY_ACTION_TERMS = (
    "allow",
    "author",
    "change",
    "deploy",
    "enable",
    "grant",
    "lower",
    "mutat",
    "perform",
    "promot",
    "reload",
    "update",
    "write",
)
_SENSITIVE_KEY_RE = re.compile(
    r"(?:^|_)(?:api_key|password|private_key|secret|token)(?:$|_)", re.IGNORECASE
)

_CONTRACT_FIELDS = {
    "schema_version",
    "status",
    "reason",
    "source_contract_ready",
    "durable_receipt_required",
    "training_allowed",
    "model_training_performed",
    "registry_write_allowed",
    "runtime_or_exchange_attested",
    "repository_receipt_hash",
    "input_lineage",
    "code_manifest",
    "training_config",
    "execution_contract",
    "training_input_hash",
    "training_key_hash",
    "no_authority",
    "authority_counters",
    "contract_hash",
}
_INPUT_LINEAGE_FIELDS = {
    "projection_artifact_hash",
    "projection_hash",
    "decision_hash",
    "handoff_hash",
    "source_set_hash",
    "selection_binding_hash",
    "proof_input_hash",
    "proof_packet_hash",
    "reward_record_hashes",
    "pit_dataset_manifest_hash",
    "after_cost_label_set_hash",
    "repository_source_artifact_hashes",
    "repository_projection_edge_hashes",
    "repository_outcome_bridge_artifact_hashes",
    "dataset_hash",
    "row_ids_hash",
    "row_count",
    "train_row_ids_hash",
    "validation_row_ids_hash",
    "test_row_ids_hash",
    "feature_schema_hash",
    "feature_definition_hash",
    "label_schema_hash",
    "label_config_hash",
    "split_hash",
    "leakage_report_hash",
    "fold_preprocessing_stats_hash",
    "evidence_set_hash",
}


@dataclass(frozen=True)
class AlrChallengerTrainingContractValidation:
    valid: bool
    verdict: str
    reason: str
    reasons: tuple[str, ...]
    authority_boundary_violation: bool = False


class AlrChallengerTrainingContractError(ValueError):
    """A source artifact cannot become a challenger-training admission."""


def build_alr_challenger_training_contract(
    repository_receipt: Mapping[str, Any],
    *,
    code_manifest: Mapping[str, Any],
    training_config: Mapping[str, Any],
    expected_learning_runtime_digest: str | None = None,
) -> dict[str, Any]:
    """Bind repository evidence to a non-executable challenger training key.

    No raw candidate, proof packet, reward list, or PIT manifest parameter is
    accepted.  Those inputs must be reconstructed from the repository receipt.
    The result is schema-required by construction and is never training or
    registry authority.

    LR1(S2.2A):spawn 綁定。``learning_runtime_digest`` 恆為 code_manifest 的必填欄位且
    格式受驗(這一段本身即 fail-closed)。當提供 ``expected_learning_runtime_digest``
    (reviewed 的 learning_runtime_manifest.self_digest)時,兩者必須完全相符;不符即
    fit 被 quarantine,拒絕 spawn。

    刻意的 opt-in polarity(``expected_learning_runtime_digest=None`` 時「不」拒絕):
    S2.2A 是 source-only,production 不會呼叫本 builder;等值交叉檢查所需的 pin 由 S2.2B
    的 call-site wiring 恆定供給(屆時每次 spawn 都帶 pin)。此處不預設從 checkout 反推
    pin,是為了讓既有以 fake code_manifest 建約的測試/呼叫者不被強制做全倉建置。
    """

    receipt = _validate_repository_receipt(repository_receipt)
    proof = _mapping(
        _mapping(receipt["canonical_adapter_inputs"]).get("proof_packet")
    )
    rewards = _reward_records(receipt)
    manifest = _mapping(_mapping(proof.get("provenance")).get("pit_dataset_manifest"))

    normalized_code = _validate_code_manifest(code_manifest)
    if expected_learning_runtime_digest is not None and (
        normalized_code["learning_runtime_digest"] != expected_learning_runtime_digest
    ):
        raise AlrChallengerTrainingContractError("learning_runtime_digest_mismatch")
    normalized_config = _validate_training_config(
        training_config,
        feature_schema_hash=_required_hash(
            _mapping(manifest.get("feature_lineage")).get("feature_schema_hash"),
            "pit_feature_schema_hash",
        ),
        label_schema_hash=_required_hash(
            _mapping(manifest.get("label_lineage")).get("label_schema_hash"),
            "pit_label_schema_hash",
        ),
    )

    code_manifest_hash = _canonical_sha256(normalized_code)
    training_config_hash = _canonical_sha256(normalized_config)
    code_with_hash = copy.deepcopy(normalized_code)
    code_with_hash["code_manifest_hash"] = code_manifest_hash
    config_with_hash = copy.deepcopy(normalized_config)
    config_with_hash["training_config_hash"] = training_config_hash

    input_lineage = _input_lineage(receipt, proof, rewards, manifest)
    training_input_hash = _canonical_sha256(input_lineage)
    training_key_hash = _canonical_sha256(
        {
            "schema_version": ALR_CHALLENGER_TRAINING_CONTRACT_SCHEMA_VERSION,
            "repository_receipt_hash": receipt["receipt_hash"],
            "training_input_hash": training_input_hash,
            "code_manifest_hash": code_manifest_hash,
            "training_config_hash": training_config_hash,
        }
    )

    contract: dict[str, Any] = {
        "schema_version": ALR_CHALLENGER_TRAINING_CONTRACT_SCHEMA_VERSION,
        "status": SCHEMA_REQUIRED,
        "reason": "durable_receipt_schema_required",
        "source_contract_ready": True,
        "durable_receipt_required": True,
        "training_allowed": False,
        "model_training_performed": False,
        "registry_write_allowed": False,
        "runtime_or_exchange_attested": False,
        "repository_receipt_hash": receipt["receipt_hash"],
        "input_lineage": input_lineage,
        "code_manifest": code_with_hash,
        "training_config": config_with_hash,
        "execution_contract": dict(_EXECUTION_CONTRACT),
        "training_input_hash": training_input_hash,
        "training_key_hash": training_key_hash,
        "no_authority": dict(_NO_AUTHORITY),
        "authority_counters": dict(_AUTHORITY_COUNTERS),
    }
    contract["contract_hash"] = compute_alr_challenger_training_contract_hash(
        contract
    )
    validation = validate_alr_challenger_training_contract(contract)
    if not validation.valid:
        raise AlrChallengerTrainingContractError(validation.reason)
    return contract


def compute_alr_challenger_training_contract_hash(
    contract: Mapping[str, Any],
) -> str:
    payload = copy.deepcopy(dict(contract))
    payload.pop("contract_hash", None)
    return _canonical_sha256(payload)


def validate_alr_challenger_training_contract(
    contract: Any,
) -> AlrChallengerTrainingContractValidation:
    if not isinstance(contract, Mapping):
        return _invalid("training_contract_not_mapping")

    reasons: list[str] = []
    if contract.get("schema_version") != ALR_CHALLENGER_TRAINING_CONTRACT_SCHEMA_VERSION:
        reasons.append("training_contract_schema_version_invalid")
    unknown = sorted(str(key) for key in set(contract) - _CONTRACT_FIELDS)
    missing = sorted(_CONTRACT_FIELDS - set(contract))
    if unknown:
        reasons.append("training_contract_fields_unknown:" + ",".join(unknown))
    if missing:
        reasons.append("training_contract_fields_missing:" + ",".join(missing))

    expected_scalars = {
        "status": SCHEMA_REQUIRED,
        "reason": "durable_receipt_schema_required",
        "source_contract_ready": True,
        "durable_receipt_required": True,
        "training_allowed": False,
        "model_training_performed": False,
        "registry_write_allowed": False,
        "runtime_or_exchange_attested": False,
    }
    scalar_reasons = {
        "status": "training_contract_status_not_schema_required",
        "reason": "training_contract_reason_invalid",
        "source_contract_ready": "source_contract_ready_not_true",
        "durable_receipt_required": "durable_receipt_required_not_true",
        "training_allowed": "training_allowed_not_false",
        "model_training_performed": "model_training_performed_not_false",
        "registry_write_allowed": "registry_write_allowed_not_false",
        "runtime_or_exchange_attested": "runtime_or_exchange_attested_not_false",
    }
    for key, expected in expected_scalars.items():
        if isinstance(expected, bool):
            invalid_scalar = contract.get(key) is not expected
        else:
            invalid_scalar = contract.get(key) != expected
        if invalid_scalar:
            reasons.append(scalar_reasons[key])

    if not _typed_mapping_equal(contract.get("execution_contract"), _EXECUTION_CONTRACT):
        reasons.append("execution_contract_invalid")
    if not _typed_mapping_equal(contract.get("no_authority"), _NO_AUTHORITY):
        reasons.append("no_authority_invalid")
    if not _typed_mapping_equal(
        contract.get("authority_counters"), _AUTHORITY_COUNTERS
    ):
        reasons.append("authority_counters_invalid")

    for field in (
        "repository_receipt_hash",
        "training_input_hash",
        "training_key_hash",
        "contract_hash",
    ):
        if not _is_hash(contract.get(field)):
            reasons.append(f"{field}_invalid")

    lineage = contract.get("input_lineage")
    if not isinstance(lineage, Mapping):
        reasons.append("input_lineage_invalid")
    else:
        try:
            _validate_input_lineage_contract(lineage)
        except AlrChallengerTrainingContractError as exc:
            reasons.append(str(exc))
        if _is_hash(contract.get("training_input_hash")):
            try:
                computed_input_hash = _canonical_sha256(lineage)
            except AlrChallengerTrainingContractError:
                reasons.append("training_input_hash_uncomputable")
            else:
                if computed_input_hash != contract.get("training_input_hash"):
                    reasons.append("training_input_hash_mismatch")

    code = contract.get("code_manifest")
    config = contract.get("training_config")
    if not isinstance(code, Mapping):
        reasons.append("code_manifest_invalid")
    else:
        claimed = code.get("code_manifest_hash")
        code_payload = copy.deepcopy(dict(code))
        code_payload.pop("code_manifest_hash", None)
        try:
            normalized_code = _validate_code_manifest(code_payload)
        except AlrChallengerTrainingContractError as exc:
            reasons.append("code_manifest_semantic_invalid:" + str(exc))
        else:
            if normalized_code != code_payload:
                reasons.append("code_manifest_semantic_normalization_mismatch")
        try:
            computed_code_hash = _canonical_sha256(code_payload)
        except AlrChallengerTrainingContractError:
            reasons.append("code_manifest_hash_uncomputable")
        else:
            if not _is_hash(claimed) or computed_code_hash != claimed:
                reasons.append("code_manifest_hash_mismatch")
    if not isinstance(config, Mapping):
        reasons.append("training_config_invalid")
    else:
        claimed = config.get("training_config_hash")
        config_payload = copy.deepcopy(dict(config))
        config_payload.pop("training_config_hash", None)
        if isinstance(lineage, Mapping):
            feature_hash = lineage.get("feature_schema_hash")
            label_hash = lineage.get("label_schema_hash")
        else:
            feature_hash = None
            label_hash = None
        try:
            normalized_config = _validate_training_config(
                config_payload,
                feature_schema_hash=str(feature_hash or ""),
                label_schema_hash=str(label_hash or ""),
            )
        except AlrChallengerTrainingContractError as exc:
            reasons.append("training_config_semantic_invalid:" + str(exc))
        else:
            if normalized_config != config_payload:
                reasons.append("training_config_semantic_normalization_mismatch")
        try:
            computed_config_hash = _canonical_sha256(config_payload)
        except AlrChallengerTrainingContractError:
            reasons.append("training_config_hash_uncomputable")
        else:
            if not _is_hash(claimed) or computed_config_hash != claimed:
                reasons.append("training_config_hash_mismatch")

    if (
        isinstance(code, Mapping)
        and isinstance(config, Mapping)
        and isinstance(lineage, Mapping)
        and _is_hash(contract.get("repository_receipt_hash"))
        and _is_hash(contract.get("training_input_hash"))
    ):
        try:
            expected_key = _canonical_sha256(
                {
                    "schema_version": ALR_CHALLENGER_TRAINING_CONTRACT_SCHEMA_VERSION,
                    "repository_receipt_hash": contract["repository_receipt_hash"],
                    "training_input_hash": contract["training_input_hash"],
                    "code_manifest_hash": code.get("code_manifest_hash"),
                    "training_config_hash": config.get("training_config_hash"),
                }
            )
        except AlrChallengerTrainingContractError:
            reasons.append("training_key_hash_uncomputable")
        else:
            if contract.get("training_key_hash") != expected_key:
                reasons.append("training_key_hash_mismatch")

    if _is_hash(contract.get("contract_hash")):
        try:
            computed = compute_alr_challenger_training_contract_hash(contract)
        except (TypeError, ValueError, AlrChallengerTrainingContractError):
            reasons.append("contract_hash_uncomputable")
        else:
            if contract.get("contract_hash") != computed:
                reasons.append("contract_hash_mismatch")

    violations = _authority_violations(contract)
    if violations:
        reasons.extend(
            "authority_boundary_violation:" + item for item in violations
        )

    if reasons:
        return _invalid(
            reasons[0],
            reasons,
            authority_boundary_violation=bool(violations),
        )
    return AlrChallengerTrainingContractValidation(
        valid=True,
        verdict=SCHEMA_REQUIRED,
        reason="ok",
        reasons=(),
    )


def _validate_repository_receipt(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AlrChallengerTrainingContractError("repository_receipt_not_mapping")
    receipt = copy.deepcopy(dict(value))
    if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        raise AlrChallengerTrainingContractError("repository_receipt_schema_invalid")

    claimed_hash = receipt.get("receipt_hash")
    if not _is_hash(claimed_hash):
        raise AlrChallengerTrainingContractError("repository_receipt_hash_invalid")
    if compute_candidate_proof_repository_receipt_hash(receipt) != claimed_hash:
        raise AlrChallengerTrainingContractError("repository_receipt_hash_mismatch")
    if receipt.get("status") != READY_FOR_REWARD_VALIDATION:
        raise AlrChallengerTrainingContractError("receipt_status_not_reward_ready")

    durability = _mapping(receipt.get("durability"))
    if durability.get("receipt_persisted") is not False:
        raise AlrChallengerTrainingContractError("repository_receipt_persistence_claim")
    if durability.get("runtime_or_exchange_attested") is not False:
        raise AlrChallengerTrainingContractError("repository_receipt_runtime_claim")
    if durability.get("source_container") != "HASH_VALIDATED_APPEND_ONLY_ROW":
        raise AlrChallengerTrainingContractError("repository_source_container_invalid")
    if not _all_false(receipt.get("no_authority")):
        raise AlrChallengerTrainingContractError("repository_receipt_authority_invalid")
    if not _all_zero(receipt.get("authority_counters")):
        raise AlrChallengerTrainingContractError("repository_receipt_counters_invalid")

    adapter = _mapping(receipt.get("adapter_result"))
    if adapter.get("status") != READY_FOR_REWARD_VALIDATION:
        raise AlrChallengerTrainingContractError("adapter_status_not_reward_ready")
    claimed_adapter_hash = adapter.get("adapter_hash")
    if (
        not _is_hash(claimed_adapter_hash)
        or compute_candidate_proof_adapter_hash(adapter) != claimed_adapter_hash
    ):
        raise AlrChallengerTrainingContractError("adapter_hash_mismatch")
    if not _is_hash(adapter.get("proof_input_hash")):
        raise AlrChallengerTrainingContractError("proof_input_hash_invalid")
    if not _all_false(adapter.get("no_authority")) or not _all_zero(
        adapter.get("authority_counters")
    ):
        raise AlrChallengerTrainingContractError("adapter_authority_invalid")

    binding = _mapping(receipt.get("selection_binding"))
    if adapter.get("selection_binding") != binding:
        raise AlrChallengerTrainingContractError("selection_binding_adapter_mismatch")
    if set(binding) != _SELECTION_BINDING_FIELDS:
        raise AlrChallengerTrainingContractError("selection_binding_fields_invalid")
    if binding.get("schema_version") != SELECTION_PROOF_BINDING_SCHEMA_VERSION:
        raise AlrChallengerTrainingContractError("selection_binding_schema_invalid")
    if (
        not _is_hash(binding.get("binding_hash"))
        or compute_selection_proof_binding_hash(binding) != binding.get("binding_hash")
    ):
        raise AlrChallengerTrainingContractError("selection_binding_hash_mismatch")
    if receipt.get("projection_refs") != adapter.get("projection_refs"):
        raise AlrChallengerTrainingContractError("projection_refs_adapter_mismatch")
    projection_refs = _mapping(receipt.get("projection_refs"))
    if set(projection_refs) != _PROJECTION_REF_FIELDS:
        raise AlrChallengerTrainingContractError("projection_refs_fields_invalid")
    if projection_refs.get("artifact_kind") != "learning_target":
        raise AlrChallengerTrainingContractError("projection_artifact_kind_invalid")
    for field in (
        "projection_hash",
        "artifact_hash",
        "decision_hash",
        "source_set_hash",
        "handoff_hash",
    ):
        if not _is_hash(projection_refs.get(field)):
            raise AlrChallengerTrainingContractError(
                "projection_refs_" + field + "_invalid"
            )
        if binding.get(field) != projection_refs.get(field):
            raise AlrChallengerTrainingContractError(
                "selection_binding_" + field + "_mismatch"
            )
    selected_candidate = binding.get("selected_candidate")
    if not isinstance(selected_candidate, Mapping):
        raise AlrChallengerTrainingContractError(
            "selection_binding_selected_candidate_invalid"
        )
    try:
        selected_identity = derive_selected_candidate_proof_identity(
            selected_candidate
        )
    except ValueError as exc:
        raise AlrChallengerTrainingContractError(
            "selection_binding_selected_candidate_identity_invalid"
        ) from exc
    for field, expected in selected_identity.items():
        if binding.get(field) != expected:
            raise AlrChallengerTrainingContractError(
                "selection_binding_" + field + "_mismatch"
            )
    if projection_refs.get("durable_receipt_status") != "unverified_source_only":
        raise AlrChallengerTrainingContractError("projection_durability_claim_invalid")
    if receipt.get("projection_identity_status") != (
        "RECONSTRUCTED_FROM_HASH_VALIDATED_ROWS"
    ):
        raise AlrChallengerTrainingContractError("projection_identity_status_invalid")
    if receipt.get("original_ephemeral_projection_hash_attested") is not False:
        raise AlrChallengerTrainingContractError(
            "original_ephemeral_projection_attestation_invalid"
        )

    canonical_inputs = _mapping(receipt.get("canonical_adapter_inputs"))
    if canonical_inputs.get("normalization") != (
        "REWARD_RECORDS_SORTED_BY_COMPUTED_DECLARED_AND_PAYLOAD_HASH"
    ):
        raise AlrChallengerTrainingContractError("canonical_input_normalization_invalid")
    proof = canonical_inputs.get("proof_packet")
    if not isinstance(proof, Mapping):
        raise AlrChallengerTrainingContractError("proof_packet_missing")
    proof_validation = validate_proof_packet(proof)
    if not proof_validation.proof_ready or proof_validation.verdict != PROOF_READY:
        raise AlrChallengerTrainingContractError(
            "proof_packet:" + proof_validation.reason
        )
    proof_hash = compute_proof_packet_hash(proof)
    if proof.get("proof_packet_hash") != proof_hash:
        raise AlrChallengerTrainingContractError("proof_packet_hash_mismatch")
    proof_input_hashes = _mapping(
        _mapping(proof.get("provenance")).get("input_artifact_hashes")
    )
    proof_projection_fields = {
        "candidate_projection_artifact_hash": "artifact_hash",
        "candidate_projection_decision_hash": "decision_hash",
        "candidate_projection_handoff_hash": "handoff_hash",
    }
    for proof_field, projection_field in proof_projection_fields.items():
        if proof_input_hashes.get(proof_field) != projection_refs.get(
            projection_field
        ):
            raise AlrChallengerTrainingContractError(
                "proof_packet_" + proof_field + "_mismatch"
            )

    rewards = canonical_inputs.get("reward_records")
    if not isinstance(rewards, list) or not rewards:
        raise AlrChallengerTrainingContractError("reward_records_missing")
    computed_reward_hashes: list[str] = []
    for index, record in enumerate(rewards):
        validation = validate_reward_record(record)
        if not validation.reward_ready:
            raise AlrChallengerTrainingContractError(
                f"reward_record_{index}:" + validation.reason
            )
        record_hash = compute_reward_record_hash(record)
        if record.get("record_hash") != record_hash:
            raise AlrChallengerTrainingContractError(
                f"reward_record_{index}_hash_mismatch"
            )
        computed_reward_hashes.append(record_hash)
    if computed_reward_hashes != sorted(computed_reward_hashes):
        raise AlrChallengerTrainingContractError("reward_records_not_canonical")

    repository_sources = _mapping(receipt.get("repository_sources"))
    projection_refs = _mapping(receipt.get("projection_refs"))
    if repository_sources.get("projection_artifact_hash") != projection_refs.get(
        "artifact_hash"
    ):
        raise AlrChallengerTrainingContractError(
            "repository_projection_artifact_hash_mismatch"
        )
    if repository_sources.get("proof_packet_hash") != proof_hash:
        raise AlrChallengerTrainingContractError("repository_proof_hash_mismatch")
    if repository_sources.get("reward_record_hashes") != computed_reward_hashes:
        raise AlrChallengerTrainingContractError("repository_reward_hashes_mismatch")
    proof_summary = _mapping(adapter.get("proof"))
    if proof_summary.get("computed_proof_packet_hash") != proof_hash:
        raise AlrChallengerTrainingContractError("adapter_proof_hash_mismatch")
    reward_summaries = adapter.get("reward_records")
    if not isinstance(reward_summaries, list) or [
        _mapping(item).get("computed_record_hash") for item in reward_summaries
    ] != computed_reward_hashes:
        raise AlrChallengerTrainingContractError("adapter_reward_hashes_mismatch")
    expected_proof_input_hash = _canonical_sha256(
        {
            "projection_refs": projection_refs,
            "selection_binding_hash": binding["binding_hash"],
            "proof_packet_hash": proof_hash,
            "reward_record_hashes": computed_reward_hashes,
        }
    )
    if adapter.get("proof_input_hash") != expected_proof_input_hash:
        raise AlrChallengerTrainingContractError("proof_input_hash_mismatch")

    source_artifacts = _mapping(receipt.get("source_artifacts"))
    source_proof = source_artifacts.get("proof_packet")
    if not isinstance(source_proof, Mapping) or compute_proof_packet_hash(
        source_proof
    ) != proof_hash:
        raise AlrChallengerTrainingContractError(
            "source_artifact_proof_hash_mismatch"
        )
    source_rewards = source_artifacts.get("reward_records")
    if not isinstance(source_rewards, list) or not all(
        isinstance(item, Mapping) for item in source_rewards
    ):
        raise AlrChallengerTrainingContractError("source_artifact_rewards_invalid")
    if sorted(compute_reward_record_hash(item) for item in source_rewards) != sorted(
        computed_reward_hashes
    ):
        raise AlrChallengerTrainingContractError(
            "source_artifact_reward_hashes_mismatch"
        )

    exact_containers = receipt.get("exact_source_containers")
    if not isinstance(exact_containers, list) or not exact_containers:
        raise AlrChallengerTrainingContractError("exact_source_containers_missing")
    repository_container_hashes = repository_sources.get(
        "outcome_bridge_artifact_hashes"
    )
    if not isinstance(repository_container_hashes, list) or not all(
        _is_hash(item) for item in repository_container_hashes
    ):
        raise AlrChallengerTrainingContractError(
            "repository_outcome_bridge_artifact_hashes_invalid"
        )
    observed_container_hashes: list[str] = []
    for index, container in enumerate(exact_containers):
        if not isinstance(container, Mapping):
            raise AlrChallengerTrainingContractError(
                f"exact_source_container_{index}_invalid"
            )
        container_hash = container.get("outcome_bridge_artifact_hash")
        if not _is_hash(container_hash):
            raise AlrChallengerTrainingContractError(
                f"exact_source_container_{index}_artifact_hash_invalid"
            )
        observed_container_hashes.append(str(container_hash))
        container_source = _mapping(container.get("source_artifacts"))
        container_proof = container_source.get("proof_packet")
        if not isinstance(container_proof, Mapping) or compute_proof_packet_hash(
            container_proof
        ) != proof_hash:
            raise AlrChallengerTrainingContractError(
                f"exact_source_container_{index}_proof_hash_mismatch"
            )
        container_rewards = container_source.get("reward_records")
        if not isinstance(container_rewards, list) or not all(
            isinstance(item, Mapping) for item in container_rewards
        ):
            raise AlrChallengerTrainingContractError(
                f"exact_source_container_{index}_rewards_invalid"
            )
        if sorted(
            compute_reward_record_hash(item) for item in container_rewards
        ) != sorted(computed_reward_hashes):
            raise AlrChallengerTrainingContractError(
                f"exact_source_container_{index}_reward_hashes_mismatch"
            )
    if observed_container_hashes != repository_container_hashes:
        raise AlrChallengerTrainingContractError(
            "repository_outcome_bridge_artifact_hashes_mismatch"
        )

    manifest = _mapping(_mapping(proof.get("provenance")).get("pit_dataset_manifest"))
    pit_validation = validate_pit_dataset_manifest(manifest)
    if not pit_validation.dataset_ready:
        raise AlrChallengerTrainingContractError(
            "pit_dataset_manifest:" + pit_validation.reason
        )
    pit_hash = compute_pit_dataset_manifest_hash(manifest)
    if manifest.get("manifest_hash") != pit_hash:
        raise AlrChallengerTrainingContractError("pit_dataset_manifest_hash_mismatch")

    _validate_candidate_scope(binding, proof, rewards, manifest)
    for index, record in enumerate(rewards):
        lineage = _mapping(_mapping(record).get("lineage"))
        if lineage.get("proof_packet_hash") != proof_hash:
            raise AlrChallengerTrainingContractError(
                f"reward_record_{index}_proof_hash_mismatch"
            )
        if lineage.get("pit_dataset_manifest_hash") != pit_hash:
            raise AlrChallengerTrainingContractError(
                f"reward_record_{index}_pit_hash_mismatch"
            )
        reward = _mapping(_mapping(record).get("reward"))
        if reward.get("reward_kind") != REWARD_KIND_AFTER_COST_REALIZED_DEMO:
            raise AlrChallengerTrainingContractError(
                f"reward_record_{index}_not_after_cost_realized_demo"
            )
        if reward.get("no_fill_reward") is not False:
            raise AlrChallengerTrainingContractError(
                f"reward_record_{index}_no_fill_reward_invalid"
            )

    return receipt


def _validate_candidate_scope(
    binding: Mapping[str, Any],
    proof: Mapping[str, Any],
    rewards: Sequence[Mapping[str, Any]],
    manifest: Mapping[str, Any],
) -> None:
    proof_candidate = _mapping(proof.get("candidate_identity"))
    pit_candidate = _mapping(manifest.get("candidate_scope"))
    if binding.get("candidate_id") != proof_candidate.get("candidate_id"):
        raise AlrChallengerTrainingContractError("candidate_scope_candidate_id_mismatch")
    if binding.get("context_id") != proof_candidate.get("context_id"):
        raise AlrChallengerTrainingContractError("candidate_scope_context_id_mismatch")
    for field in ("candidate_id", "strategy_name", "symbol", "side"):
        if proof_candidate.get(field) != pit_candidate.get(field):
            raise AlrChallengerTrainingContractError(
                "candidate_scope_" + field + "_mismatch"
            )
    if pit_candidate.get("engine_mode") != "demo":
        raise AlrChallengerTrainingContractError("candidate_scope_engine_mode_not_demo")
    for index, record in enumerate(rewards):
        reward_candidate = _mapping(record.get("candidate_identity"))
        for field in ("candidate_id", "context_id", "strategy_name", "symbol", "side"):
            if reward_candidate.get(field) != proof_candidate.get(field):
                raise AlrChallengerTrainingContractError(
                    f"reward_record_{index}_candidate_scope_{field}_mismatch"
                )


def _validate_code_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AlrChallengerTrainingContractError("code_manifest_not_mapping")
    manifest = copy.deepcopy(dict(value))
    expected_fields = {
        "schema_version",
        "source_head",
        "module_hashes",
        "dependency_lock_hash",
        # LR1(S2.2A):新增 scoped learning identity;整倉 HEAD 已降為遙測。
        "learning_runtime_digest",
    }
    if set(manifest) != expected_fields:
        raise AlrChallengerTrainingContractError("code_manifest_fields_invalid")
    if manifest.get("schema_version") != CODE_MANIFEST_SCHEMA_VERSION:
        raise AlrChallengerTrainingContractError("code_manifest_schema_invalid")
    if not isinstance(
        manifest.get("learning_runtime_digest"), str
    ) or not _LEARNING_RUNTIME_DIGEST_RE.fullmatch(manifest["learning_runtime_digest"]):
        raise AlrChallengerTrainingContractError(
            "code_manifest_learning_runtime_digest_invalid"
        )
    if not isinstance(manifest.get("source_head"), str) or not _GIT_HEAD_RE.fullmatch(
        manifest["source_head"]
    ):
        raise AlrChallengerTrainingContractError("code_manifest_source_head_invalid")
    module_hashes = manifest.get("module_hashes")
    if not isinstance(module_hashes, Mapping) or set(module_hashes) != set(
        _REQUIRED_MODULE_HASHES
    ):
        raise AlrChallengerTrainingContractError("code_manifest_module_set_invalid")
    normalized_hashes: dict[str, str] = {}
    for module in _REQUIRED_MODULE_HASHES:
        value_hash = module_hashes.get(module)
        if not _is_hash(value_hash):
            raise AlrChallengerTrainingContractError(
                "code_manifest_module_hash_invalid:" + module
            )
        normalized_hashes[module] = str(value_hash)
    if not _is_hash(manifest.get("dependency_lock_hash")):
        raise AlrChallengerTrainingContractError(
            "code_manifest_dependency_lock_hash_invalid"
        )
    manifest["module_hashes"] = normalized_hashes
    violations = _authority_violations(manifest)
    if violations:
        raise AlrChallengerTrainingContractError(
            "authority_boundary_violation:" + violations[0]
        )
    _canonical_sha256(manifest)
    return manifest


def _validate_training_config(
    value: Any,
    *,
    feature_schema_hash: str,
    label_schema_hash: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AlrChallengerTrainingContractError("training_config_not_mapping")
    config = copy.deepcopy(dict(value))
    expected_fields = {
        "schema_version",
        "algorithm",
        "quantiles",
        "engine_mode",
        "feature_schema_hash",
        "label_schema_hash",
        "parameters",
        "resource_budget",
    }
    if set(config) != expected_fields:
        raise AlrChallengerTrainingContractError("training_config_fields_invalid")
    if config.get("schema_version") != TRAINING_CONFIG_SCHEMA_VERSION:
        raise AlrChallengerTrainingContractError("training_config_schema_invalid")
    if config.get("algorithm") != "lightgbm_quantile_trio":
        raise AlrChallengerTrainingContractError("training_config_algorithm_invalid")
    if tuple(config.get("quantiles", ())) != _REQUIRED_QUANTILES:
        raise AlrChallengerTrainingContractError("training_config_quantiles_invalid")
    if config.get("engine_mode") != "demo":
        raise AlrChallengerTrainingContractError("training_config_engine_mode_not_demo")
    if config.get("feature_schema_hash") != feature_schema_hash:
        raise AlrChallengerTrainingContractError(
            "training_config_feature_schema_hash_mismatch"
        )
    if config.get("label_schema_hash") != label_schema_hash:
        raise AlrChallengerTrainingContractError(
            "training_config_label_schema_hash_mismatch"
        )
    violations = _authority_violations(config)
    if violations:
        raise AlrChallengerTrainingContractError(
            "authority_boundary_violation:" + violations[0]
        )
    parameters = config.get("parameters")
    if not isinstance(parameters, Mapping):
        raise AlrChallengerTrainingContractError("training_config_parameters_invalid")
    if set(parameters) != _REQUIRED_TRAINING_PARAMETER_KEYS:
        raise AlrChallengerTrainingContractError(
            "training_config_parameter_set_invalid"
        )
    for key in (
        "num_leaves",
        "n_estimators",
        "early_stopping_rounds",
        "bootstrap_iterations",
    ):
        if not _is_positive_int(parameters.get(key)):
            raise AlrChallengerTrainingContractError(
                "training_config_parameter_invalid:" + key
            )
    for key in ("bagging_freq", "bootstrap_seed"):
        if not _is_nonnegative_int(parameters.get(key)):
            raise AlrChallengerTrainingContractError(
                "training_config_parameter_invalid:" + key
            )
    min_data_in_leaf = parameters.get("min_data_in_leaf")
    if min_data_in_leaf is not None and not _is_positive_int(min_data_in_leaf):
        raise AlrChallengerTrainingContractError(
            "training_config_parameter_invalid:min_data_in_leaf"
        )
    for key in (
        "learning_rate",
        "label_window_hours",
        "decay_halflife_days",
    ):
        if not _is_positive_number(parameters.get(key)):
            raise AlrChallengerTrainingContractError(
                "training_config_parameter_invalid:" + key
            )
    for key in ("feature_fraction", "bagging_fraction"):
        item = parameters.get(key)
        if not _is_positive_number(item) or float(item) > 1.0:
            raise AlrChallengerTrainingContractError(
                "training_config_parameter_invalid:" + key
            )
    lambda_l2 = parameters.get("lambda_l2")
    if not _is_nonnegative_number(lambda_l2):
        raise AlrChallengerTrainingContractError(
            "training_config_parameter_invalid:lambda_l2"
        )
    if parameters["early_stopping_rounds"] >= parameters["n_estimators"]:
        raise AlrChallengerTrainingContractError(
            "training_config_parameter_invalid:early_stopping_rounds"
        )
    if not isinstance(parameters.get("schema_version"), str) or not str(
        parameters["schema_version"]
    ).strip():
        raise AlrChallengerTrainingContractError(
            "training_config_parameter_invalid:schema_version"
        )
    budget = config.get("resource_budget")
    if not isinstance(budget, Mapping) or set(budget) != _RESOURCE_BUDGET_KEYS:
        raise AlrChallengerTrainingContractError("training_config_resource_budget_invalid")
    for key in _POSITIVE_RESOURCE_KEYS:
        item = budget.get(key)
        if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
            raise AlrChallengerTrainingContractError(
                "training_config_resource_budget_invalid:" + key
            )
    external_requests = budget.get("max_external_requests")
    if isinstance(external_requests, bool) or external_requests != 0:
        raise AlrChallengerTrainingContractError(
            "training_config_external_requests_not_zero"
        )
    api_cost = budget.get("max_api_cost_usd")
    if isinstance(api_cost, bool) or not isinstance(api_cost, (int, float)):
        raise AlrChallengerTrainingContractError("training_config_api_cost_invalid")
    if not math.isfinite(float(api_cost)) or float(api_cost) != 0.0:
        raise AlrChallengerTrainingContractError("training_config_api_cost_not_zero")
    _canonical_sha256(config)
    return config


def _validate_input_lineage_contract(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != _INPUT_LINEAGE_FIELDS:
        raise AlrChallengerTrainingContractError("input_lineage_fields_invalid")
    scalar_hash_fields = {
        "projection_artifact_hash",
        "projection_hash",
        "decision_hash",
        "handoff_hash",
        "source_set_hash",
        "selection_binding_hash",
        "proof_input_hash",
        "proof_packet_hash",
        "pit_dataset_manifest_hash",
        "after_cost_label_set_hash",
        "dataset_hash",
        "row_ids_hash",
        "train_row_ids_hash",
        "validation_row_ids_hash",
        "test_row_ids_hash",
        "feature_schema_hash",
        "feature_definition_hash",
        "label_schema_hash",
        "label_config_hash",
        "split_hash",
        "leakage_report_hash",
        "fold_preprocessing_stats_hash",
        "evidence_set_hash",
    }
    for field in scalar_hash_fields:
        if not _is_hash(value.get(field)):
            raise AlrChallengerTrainingContractError(
                "input_lineage_" + field + "_invalid"
            )
    for field in (
        "reward_record_hashes",
        "repository_source_artifact_hashes",
        "repository_projection_edge_hashes",
        "repository_outcome_bridge_artifact_hashes",
    ):
        items = value.get(field)
        if not isinstance(items, list) or not items or not all(
            _is_hash(item) for item in items
        ):
            raise AlrChallengerTrainingContractError(
                "input_lineage_" + field + "_invalid"
            )
    reward_hashes = value["reward_record_hashes"]
    if reward_hashes != sorted(reward_hashes) or len(reward_hashes) != len(
        set(reward_hashes)
    ):
        raise AlrChallengerTrainingContractError(
            "input_lineage_reward_record_hashes_not_canonical"
        )
    if not _is_positive_int(value.get("row_count")):
        raise AlrChallengerTrainingContractError("input_lineage_row_count_invalid")
    evidence_identity = {
        "projection_artifact_hash": value["projection_artifact_hash"],
        "projection_hash": value["projection_hash"],
        "decision_hash": value["decision_hash"],
        "handoff_hash": value["handoff_hash"],
        "source_set_hash": value["source_set_hash"],
        "selection_binding_hash": value["selection_binding_hash"],
        "proof_input_hash": value["proof_input_hash"],
        "proof_packet_hash": value["proof_packet_hash"],
        "reward_record_hashes": copy.deepcopy(reward_hashes),
        "pit_dataset_manifest_hash": value["pit_dataset_manifest_hash"],
        "after_cost_label_set_hash": value["after_cost_label_set_hash"],
    }
    if _canonical_sha256(evidence_identity) != value["evidence_set_hash"]:
        raise AlrChallengerTrainingContractError(
            "input_lineage_evidence_set_hash_mismatch"
        )


def _input_lineage(
    receipt: Mapping[str, Any],
    proof: Mapping[str, Any],
    rewards: Sequence[Mapping[str, Any]],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    adapter = _mapping(receipt.get("adapter_result"))
    projection = _mapping(receipt.get("projection_refs"))
    binding = _mapping(receipt.get("selection_binding"))
    repository = _mapping(receipt.get("repository_sources"))
    row_set = _mapping(manifest.get("row_set"))
    split = _mapping(manifest.get("split_lineage"))
    feature = _mapping(manifest.get("feature_lineage"))
    label = _mapping(manifest.get("label_lineage"))
    leakage = _mapping(manifest.get("leakage_evidence"))
    reward_hashes = [compute_reward_record_hash(record) for record in rewards]
    label_rows = [
        {
            "record_hash": record_hash,
            "candidate_identity": copy.deepcopy(
                dict(_mapping(record.get("candidate_identity")))
            ),
            "reward": {
                "reward_kind": _mapping(record.get("reward")).get("reward_kind"),
                "net_pnl_bps": _mapping(record.get("reward")).get("net_pnl_bps"),
                "net_pnl_usdt": _mapping(record.get("reward")).get("net_pnl_usdt"),
                "sample_weight": _mapping(record.get("reward")).get("sample_weight"),
            },
            "effect_window": copy.deepcopy(
                dict(_mapping(record.get("effect_window")))
            ),
        }
        for record_hash, record in zip(reward_hashes, rewards)
    ]
    after_cost_label_set_hash = _canonical_sha256(label_rows)
    evidence_identity = {
        "projection_artifact_hash": projection.get("artifact_hash"),
        "projection_hash": projection.get("projection_hash"),
        "decision_hash": projection.get("decision_hash"),
        "handoff_hash": projection.get("handoff_hash"),
        "source_set_hash": projection.get("source_set_hash"),
        "selection_binding_hash": binding.get("binding_hash"),
        "proof_input_hash": adapter.get("proof_input_hash"),
        "proof_packet_hash": compute_proof_packet_hash(proof),
        "reward_record_hashes": reward_hashes,
        "pit_dataset_manifest_hash": compute_pit_dataset_manifest_hash(manifest),
        "after_cost_label_set_hash": after_cost_label_set_hash,
    }
    evidence_set_hash = _canonical_sha256(evidence_identity)
    lineage = {
        **evidence_identity,
        "repository_source_artifact_hashes": copy.deepcopy(
            list(repository.get("source_artifact_hashes", []))
        ),
        "repository_projection_edge_hashes": copy.deepcopy(
            list(repository.get("projection_edge_hashes", []))
        ),
        "repository_outcome_bridge_artifact_hashes": copy.deepcopy(
            list(repository.get("outcome_bridge_artifact_hashes", []))
        ),
        "dataset_hash": row_set.get("dataset_hash"),
        "row_ids_hash": row_set.get("row_ids_hash"),
        "row_count": row_set.get("row_count"),
        "train_row_ids_hash": split.get("train_row_ids_hash"),
        "validation_row_ids_hash": split.get("validation_row_ids_hash"),
        "test_row_ids_hash": split.get("test_row_ids_hash"),
        "feature_schema_hash": feature.get("feature_schema_hash"),
        "feature_definition_hash": feature.get("feature_definition_hash"),
        "label_schema_hash": label.get("label_schema_hash"),
        "label_config_hash": label.get("label_config_hash"),
        "split_hash": split.get("split_hash"),
        "leakage_report_hash": leakage.get("leakage_report_hash"),
        "fold_preprocessing_stats_hash": leakage.get(
            "fold_preprocessing_stats_hash"
        ),
        "evidence_set_hash": evidence_set_hash,
    }
    _validate_input_lineage_contract(lineage)
    return lineage


def _reward_records(receipt: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = _mapping(receipt.get("canonical_adapter_inputs")).get("reward_records")
    if not isinstance(records, list) or not records:
        raise AlrChallengerTrainingContractError("reward_records_missing")
    if not all(isinstance(item, Mapping) for item in records):
        raise AlrChallengerTrainingContractError("reward_records_invalid")
    return [copy.deepcopy(dict(item)) for item in records]


def _authority_violations(value: Any) -> tuple[str, ...]:
    violations: list[str] = []
    for path, key, item in _walk(value):
        normalized = key.lower().replace("-", "_")
        if _SENSITIVE_KEY_RE.search(normalized):
            violations.append(path + ":sensitive_key")
            continue
        if not _truthy(item):
            continue
        if normalized in _AUTHORITY_TRUE_KEYS or (
            any(term in normalized for term in _AUTHORITY_TERMS)
            and any(action in normalized for action in _AUTHORITY_ACTION_TERMS)
        ):
            violations.append(path)
    return tuple(sorted(set(violations)))


def _walk(value: Any, prefix: str = "") -> list[tuple[str, str, Any]]:
    items: list[tuple[str, str, Any]] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            path = f"{prefix}.{key_text}" if prefix else key_text
            items.append((path, key_text, child))
            items.extend(_walk(child, path))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            items.extend(_walk(child, f"{prefix}[{index}]"))
    return items


def _truthy(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return math.isfinite(float(value)) and float(value) != 0.0
    if isinstance(value, str):
        return value.strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
            "enabled",
            "grant",
            "granted",
        }
    return False


def _canonical_sha256(value: Any) -> str:
    try:
        canonical = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise AlrChallengerTrainingContractError(
            "canonical_payload_invalid"
        ) from exc
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _required_hash(value: Any, field: str) -> str:
    if not _is_hash(value):
        raise AlrChallengerTrainingContractError(field + "_invalid")
    return str(value)


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and bool(_HASH_RE.fullmatch(value))


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_positive_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) > 0.0
    )


def _is_nonnegative_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0.0
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _all_false(value: Any) -> bool:
    return isinstance(value, Mapping) and bool(value) and all(
        item is False for item in value.values()
    )


def _all_zero(value: Any) -> bool:
    return isinstance(value, Mapping) and bool(value) and all(
        isinstance(item, int) and not isinstance(item, bool) and item == 0
        for item in value.values()
    )


def _typed_mapping_equal(value: Any, expected: Mapping[str, Any]) -> bool:
    if not isinstance(value, Mapping) or set(value) != set(expected):
        return False
    return all(
        type(value[key]) is type(expected_value) and value[key] == expected_value
        for key, expected_value in expected.items()
    )


def _invalid(
    reason: str,
    reasons: Sequence[str] | None = None,
    *,
    authority_boundary_violation: bool = False,
) -> AlrChallengerTrainingContractValidation:
    return AlrChallengerTrainingContractValidation(
        valid=False,
        verdict=INVALID,
        reason=reason,
        reasons=tuple(reasons or (reason,)),
        authority_boundary_violation=authority_boundary_violation,
    )


__all__ = [
    "ALR_CHALLENGER_TRAINING_CONTRACT_SCHEMA_VERSION",
    "CODE_MANIFEST_SCHEMA_VERSION",
    "TRAINING_CONFIG_SCHEMA_VERSION",
    "SCHEMA_REQUIRED",
    "INVALID",
    "AlrChallengerTrainingContractError",
    "AlrChallengerTrainingContractValidation",
    "build_alr_challenger_training_contract",
    "compute_alr_challenger_training_contract_hash",
    "validate_alr_challenger_training_contract",
]
