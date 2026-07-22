"""Structural tests for the S1.2 (LR0B) 7-class component-effect classifier.

Hermetic / stdlib-only.  Covers: matrix-driven derivation for all seven classes,
the fail-closed NONE-block bypass-negatives (an effectful surface cannot be
self-declared source-only), adapter-substitution / missing-intent-field
rejection, forged-artifact rejection by the central validator, and the §9.6
regression guard that the frozen S0.3 classifier/contract digests are byte
unchanged (PROGRAM_ADOPTED must not break).
"""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import aiml_gate_receipt_validator as validator  # noqa: E402
import agent_governance_terminal_receipt_sink as worm_sink  # noqa: E402


# 凍結的 S0.3 身分 digest(建置當日 pin);任一改變即代表 S0.3 被動到,PROGRAM_ADOPTED
# 的 in-process 重算會失敗。此為 design §9.6 的 regression guard。
FROZEN_S0_3_CLASSIFIER_DIGEST = (
    "sha256:1cf8c021b066ceeb364e968add074d263cb28d63db421fdc40620e9904d0ddbc"
)
FROZEN_S0_3_TERMINAL_SINK_CONTRACT_DIGEST = (
    "sha256:9c02cf4bfcf5f97dc455bded87350c9546456d21ef20d0888bd2ef2cde401eb2"
)
CLASSIFIED_AT = "2026-07-22T10:00:00Z"


def _component_work_package(effect_class: str, **overrides: object) -> dict:
    row = validator.AIML_COMPONENT_EFFECT_CLASS_MATRIX[effect_class]
    work_package = {
        "component_work_package_id": f"AIML-{effect_class}-WP",
        "component_effect_class": effect_class,
        "declared_adapter_id": row["adapter_id"],
        "declared_intent_fields": list(row["required_intent_fields"]),
        "owned_path_manifest": [
            "program_code/ml_training/schemas/aiml_gate_receipts/example.schema.json"
        ],
        "direct_interfaces": [row["adapter_id"]],
    }
    work_package.update(overrides)
    return work_package


# --------------------------------------------------------------------------- #
# matrix-driven derivation
# --------------------------------------------------------------------------- #
def test_seven_classes_each_derive_exact_matrix_fields() -> None:
    for effect_class, row in validator.AIML_COMPONENT_EFFECT_CLASS_MATRIX.items():
        classification = validator.classify_component_required_effects(
            _component_work_package(effect_class), classified_at=CLASSIFIED_AT
        )
        assert validator.validate_aiml_artifact(classification, now=CLASSIFIED_AT) == []
        assert classification["classifier_digest"] == (
            validator.aiml_component_effect_class_matrix_digest()
        )
        (effect,) = classification["required_effects"]
        assert effect == {
            "effect_class": effect_class,
            "status": "REQUIRED_PENDING",
            "adapter_id": row["adapter_id"],
            "actor_node_id": row["actor_node_id"],
            "rollback_contract": row["recovery_contract"],
            "independent_postcheck_node_id": row["independent_postcheck_node_id"],
            "required_intent_fields": list(row["required_intent_fields"]),
            "adapter_binding_status": row["adapter_binding_status"],
        }


def test_only_worm_sink_is_implemented_the_other_six_are_pending_s1_5() -> None:
    statuses = {
        name: row["adapter_binding_status"]
        for name, row in validator.AIML_COMPONENT_EFFECT_CLASS_MATRIX.items()
    }
    assert statuses["TERMINAL_RECEIPT_APPEND"] == "IMPLEMENTED_DISPOSABLE"
    assert all(
        status == "PENDING_S1_5"
        for name, status in statuses.items()
        if name != "TERMINAL_RECEIPT_APPEND"
    )


def test_caller_intent_field_ordering_does_not_leak_into_derivation() -> None:
    # 呼叫端以打亂順序宣告 intent fields,派生輸出仍是 matrix 的正規欄位。
    work_package = _component_work_package("ENGINE_SCANNER")
    work_package["declared_intent_fields"] = list(
        reversed(work_package["declared_intent_fields"])
    )
    classification = validator.classify_component_required_effects(
        work_package, classified_at=CLASSIFIED_AT
    )
    (effect,) = classification["required_effects"]
    assert effect["required_intent_fields"] == list(
        validator.AIML_COMPONENT_EFFECT_CLASS_MATRIX["ENGINE_SCANNER"][
            "required_intent_fields"
        ]
    )


def test_every_class_carries_ops_pm_independence_invariants() -> None:
    assert validator.AIML_COMPONENT_EFFECT_CLASS_INVARIANTS == {
        "requires_ops_preflight": True,
        "requires_pm_operator_approved_intent": True,
        "requires_independent_ops_postcheck": True,
        "applier_is_not_sole_verifier": True,
    }
    # invariants 綁進矩陣 digest,篡改任一旗標即改變 classifier 身分。
    assert validator.aiml_component_effect_class_matrix_digest().startswith("sha256:")


# --------------------------------------------------------------------------- #
# bypass-negatives (fail-closed): an effectful surface cannot be source-only
# --------------------------------------------------------------------------- #
def test_declared_none_touching_component_surface_raises() -> None:
    work_package = {
        "component_work_package_id": "AIML-sneaky-WP",
        "component_effect_class": "NONE",
        "declared_adapter_id": "none",
        "declared_intent_fields": ["irrelevant"],
        "owned_path_manifest": [],
        "direct_interfaces": ["terminal_receipt_sink_adapter_v1"],
    }
    with pytest.raises(ValueError, match="cannot be source-only"):
        validator.classify_component_required_effects(
            work_package, classified_at=CLASSIFIED_AT
        )


def test_omitted_class_touching_component_surface_raises() -> None:
    work_package = {
        "component_work_package_id": "AIML-omit-WP",
        "declared_adapter_id": "none",
        "declared_intent_fields": ["irrelevant"],
        "owned_path_manifest": ["pg_role_acl_migration_actor"],
        "direct_interfaces": [],
    }
    with pytest.raises(ValueError, match="cannot be source-only"):
        validator.classify_component_required_effects(
            work_package, classified_at=CLASSIFIED_AT
        )


def test_unknown_class_without_surface_still_raises_never_none() -> None:
    work_package = {
        "component_work_package_id": "AIML-unknown-WP",
        "component_effect_class": "TOTALLY_UNKNOWN",
        "declared_adapter_id": "x",
        "declared_intent_fields": ["y"],
        "owned_path_manifest": [],
        "direct_interfaces": [],
    }
    with pytest.raises(ValueError, match="unsupported component_effect_class"):
        validator.classify_component_required_effects(
            work_package, classified_at=CLASSIFIED_AT
        )


def test_adapter_substitution_is_rejected() -> None:
    work_package = _component_work_package(
        "TERMINAL_RECEIPT_APPEND", declared_adapter_id="deploy_adapter_v1"
    )
    with pytest.raises(ValueError, match="not the admitted adapter"):
        validator.classify_component_required_effects(
            work_package, classified_at=CLASSIFIED_AT
        )


def test_missing_required_intent_fields_is_rejected() -> None:
    work_package = _component_work_package("CREDENTIAL_ROTATION")
    work_package["declared_intent_fields"] = work_package["declared_intent_fields"][:-1]
    with pytest.raises(ValueError, match="do not match the exact"):
        validator.classify_component_required_effects(
            work_package, classified_at=CLASSIFIED_AT
        )


# --------------------------------------------------------------------------- #
# forged-artifact rejection by the central validator
# --------------------------------------------------------------------------- #
def test_validator_rejects_forged_required_effects_downgrade_to_none() -> None:
    classification = validator.classify_component_required_effects(
        _component_work_package("TERMINAL_RECEIPT_APPEND"), classified_at=CLASSIFIED_AT
    )
    forged = deepcopy(classification)
    forged["required_effects"] = [{
        "effect_class": "NONE",
        "status": "NOT_REQUIRED",
        "adapter_id": "none",
        "actor_node_id": "none",
        "rollback_contract": "none",
        "independent_postcheck_node_id": "none",
        "required_intent_fields": ["none"],
        "adapter_binding_status": "NOT_APPLICABLE",
    }]
    errors = validator.validate_aiml_artifact(forged, now=CLASSIFIED_AT)
    assert "AIML component required effects differ from classifier output" in errors


def test_validator_rejects_forged_adapter_in_classified_inputs() -> None:
    classification = validator.classify_component_required_effects(
        _component_work_package("RETENTION_APPLY"), classified_at=CLASSIFIED_AT
    )
    forged = deepcopy(classification)
    forged["classified_inputs"]["declared_adapter_id"] = "deploy_adapter_v1"
    forged["classification_id"] = validator._component_effect_class_identity_digest(forged)
    forged["self_digest"] = validator.artifact_self_digest(forged)
    errors = validator.validate_aiml_artifact(forged, now=CLASSIFIED_AT)
    assert any("is not admitted" in error for error in errors)


def test_validator_rejects_classifier_digest_tamper() -> None:
    classification = validator.classify_component_required_effects(
        _component_work_package("LEARNING_RUNTIME"), classified_at=CLASSIFIED_AT
    )
    tampered = deepcopy(classification)
    tampered["classifier_digest"] = "sha256:" + "0" * 64
    tampered["classification_id"] = validator._component_effect_class_identity_digest(
        tampered
    )
    tampered["self_digest"] = validator.artifact_self_digest(tampered)
    errors = validator.validate_aiml_artifact(tampered, now=CLASSIFIED_AT)
    assert "AIML component effect classifier digest is not admitted" in errors


# --------------------------------------------------------------------------- #
# sibling isolation + drift guards
# --------------------------------------------------------------------------- #
def test_component_matrix_digest_is_separate_from_s0_3_classifier() -> None:
    assert validator.aiml_component_effect_class_matrix_digest() != (
        validator.aiml_effect_classifier_digest()
    )


def test_terminal_append_row_covers_frozen_contract_binding_fields() -> None:
    contract = validator.terminal_receipt_sink_contract()
    # 適配器欄位常數與凍結契約逐字一致(no-drift guard)。
    assert list(worm_sink.PAYLOAD_BINDING_FIELDS) == contract["payload_binding_fields"]
    assert list(worm_sink.IDEMPOTENCY_KEY_FIELDS) == contract["idempotency_key_fields"]
    # matrix 的 TERMINAL_RECEIPT_APPEND intent 欄位為契約綁定欄位的超集。
    intent_fields = set(
        validator.AIML_COMPONENT_EFFECT_CLASS_MATRIX["TERMINAL_RECEIPT_APPEND"][
            "required_intent_fields"
        ]
    )
    assert set(contract["payload_binding_fields"]).issubset(intent_fields)
    assert "idempotency_key" in intent_fields
    assert "independent_readback_ack" in intent_fields


def test_s0_3_classifier_and_contract_digests_are_byte_frozen() -> None:
    # design §9.6 regression guard:S1.2 為嚴格 additive/sibling,S0.3 身分不得漂移。
    assert validator.aiml_effect_classifier_digest() == FROZEN_S0_3_CLASSIFIER_DIGEST
    contract = validator.terminal_receipt_sink_contract()
    assert contract["self_digest"] == FROZEN_S0_3_TERMINAL_SINK_CONTRACT_DIGEST
    assert contract["status"] == "CONTRACT_ONLY"
    assert contract["implementation_paths"] == []


def test_s0_3_required_effect_classification_still_validates() -> None:
    # S0.3 分類分支未被 sibling 動到:一個 canonical S0.3 分類仍應原樣通過。
    attempt = {
        "session_id": "S0.3",
        "attempt_id": "sha256:" + "a" * 64,
        "attempt_phase": "SOURCE_BUILD",
        "path_manifest": ["program_code/ml_training/aiml_gate_receipt_validator.py"],
        "work_package": {
            "work_package_id": "AIML-S0.3-GOVERNANCE-ADOPTION",
            "phase": "SOURCE_BUILD",
            "side_effect_class": "repo_write",
            "runtime_claim": False,
            "owned_path_manifest": [
                "program_code/ml_training/aiml_gate_receipt_validator.py"
            ],
            "direct_interfaces": [
                "agent_governance_registry_v1",
                "agent_governance_route_task",
                "agent_governance_validate_closure",
                "aiml_receipt_dependency_graph_v1",
                "aiml_required_effect_classification_v1",
                "github_repository_policy_attestation_v1",
                "landing_scope_v1",
                "program_adoption_receipt_v1",
                "session_attempt_v1",
                "terminal_receipt_sink_v1",
            ],
        },
    }
    classification = validator.classify_required_effects(
        attempt, classified_at=CLASSIFIED_AT
    )
    assert classification["schema_version"] == "aiml_required_effect_classification_v1"
    assert classification["required_effects"][0]["effect_class"] == (
        "EXTERNAL_READONLY_ATTESTATION"
    )
    assert validator.validate_aiml_artifact(classification) == []
