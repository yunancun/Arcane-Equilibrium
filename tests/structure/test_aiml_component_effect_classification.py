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
# S1.5 matrix flip:六個非 WORM 類 PENDING_S1_5 -> IMPLEMENTED_DISPOSABLE 後,矩陣 digest
# 刻意改變(與 S0.3 classifier digest 是分開的兩個 digest,S0.3 仍 byte-frozen)。此 pin 是
# 有意更新的迴歸守衛:除了這次 flip,矩陣不得再漂移。
PINNED_COMPONENT_MATRIX_DIGEST = (
    "sha256:22d78882a2dace9ceb640b74b2a5dca2f2a8cc05861720f5ab25c5c9ac86c445"
)
# S2.4(WP4·W1)v2 install-seam 矩陣 digest 的 build-day pin。此 digest 綁定七類的 exact §4
# ABI(adapter/actor/postcheck/rollback/required_intent_fields tokens);intent-field tokens
# 一經敲定即為 ABI,除有意變更外此 pin 不得漂移。與 v1 矩陣 digest、S0.3 classifier digest
# 是三個分開的 digest(v1 與 S0.3 仍 byte-frozen)。
PINNED_COMPONENT_MATRIX_V2_DIGEST = (
    "sha256:01d3062c79725b32b7c1468d02013a0df28dfeba1cf29d513cbf3bd6b4143c64"
)
# v1 sibling schema 檔的逐位元組凍結雜湊:v1 為 byte-frozen,W1 只做嚴格 additive。
FROZEN_COMPONENT_V1_SCHEMA_FILE_DIGEST = (
    "sha256:deb153a023d3e183a538597c0c8cdac1356e2c70e89d0837b805aa47159e5af9"
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


def test_all_seven_classes_are_implemented_disposable_after_s1_5_flip() -> None:
    # S1.5 matrix flip:六個非 WORM deploy 類的 adapter_binding_status 由 PENDING_S1_5
    # 翻為 IMPLEMENTED_DISPOSABLE(與 S1.2 對 TERMINAL_RECEIPT_APPEND 的先例一致)。
    statuses = {
        name: row["adapter_binding_status"]
        for name, row in validator.AIML_COMPONENT_EFFECT_CLASS_MATRIX.items()
    }
    assert statuses["TERMINAL_RECEIPT_APPEND"] == "IMPLEMENTED_DISPOSABLE"
    assert all(status == "IMPLEMENTED_DISPOSABLE" for status in statuses.values())
    assert "PENDING_S1_5" not in set(statuses.values())


def test_component_matrix_digest_pin_reflects_the_s1_5_flip() -> None:
    # 有意更新的 pin:flip 後矩陣 digest 為此固定值;除本次 flip 外不得再漂移。
    assert validator.aiml_component_effect_class_matrix_digest() == (
        PINNED_COMPONENT_MATRIX_DIGEST
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


# =========================================================================== #
# S2.4(WP4·W1)CP1:v2 install-source-seam 七類 sibling 分類器。嚴格 additive,
# v1 與 S0.3 byte-frozen。§6 items 1-10。
# =========================================================================== #
# §4 逐行 ABI 期望表(contract lines 251-257):class -> (adapter, actor, postcheck,
# rollback, required_intent_fields)。此表釘死 CP3 將斷言的 per-row 綁定。
_V2_EXPECTED_ABI = {
    "HOST_CAPABILITY_PROBE": (
        "s2_4_capability_probe_adapter_v1",
        "s2_4_capability_probe_actor",
        "s2_4_capability_probe_postcheck_v1",
        "s2_4_capability_probe_rollback_v1",
        ["probe_scope", "transient_unit_property_digest", "host_cgroup_identity",
         "cleanup_budget", "expiry"],
    ),
    "HOST_IDENTITY_INSTALL": (
        "s2_4_host_identity_adapter_v1",
        "s2_4_host_identity_actor",
        "s2_4_host_identity_postcheck_v1",
        "s2_4_host_identity_rollback_v1",
        ["plan", "uid_gid_directory_manifest", "pre_state", "expiry"],
    ),
    "PG_ROLE_ACL_MIGRATION": (
        "s2_4_pg_role_acl_adapter_v1",
        "s2_4_pg_admin_actor",
        "s2_4_pg_acl_postcheck_v1",
        "s2_4_pg_acl_rollback_v1",
        ["plan", "topology", "acl_manifest", "pg_migration_permit",
         "admin_handle_descriptor", "pre_state", "expiry"],
    ),
    "CREDENTIAL_INSTALL": (
        "s2_4_credential_install_adapter_v1",
        "s2_4_host_secret_actor",
        "s2_4_credential_postcheck_v1",
        "s2_4_credential_rollback_v1",
        ["plan", "credential_name", "encrypted_blob_digest", "host_identity",
         "pre_state", "expiry"],
    ),
    "LEARNING_RUNTIME_PREPARE": (
        "s2_4_prepare_adapter_v1",
        "s2_4_prepare_actor",
        "s2_4_prepare_postcheck_v1",
        "s2_4_prepare_rollback_v1",
        ["prepare_core", "prepare_authorization", "staging_root_device_inode",
         "resource_budget", "expiry"],
    ),
    "LEARNING_RUNTIME": (
        "s2_4_runtime_install_adapter_v1",
        "s2_4_host_runtime_actor",
        "s2_4_runtime_postcheck_v1",
        "s2_4_runtime_rollback_v1",
        ["plan", "prepare_receipt", "base_app_launch_manifests_and_target_paths",
         "pre_state", "expiry"],
    ),
    "ENGINE_SCANNER": (
        "s2_4_engine_scanner_install_adapter_v1",
        "s2_4_host_service_actor",
        "s2_4_engine_scanner_postcheck_v1",
        "s2_4_engine_scanner_rollback_v1",
        ["plan", "unit_policy_evidence_manifests", "inactive_post_state",
         "pre_state", "expiry"],
    ),
}


def _component_work_package_v2(effect_class: str, **overrides: object) -> dict:
    row = validator.AIML_COMPONENT_EFFECT_CLASS_MATRIX_V2[effect_class]
    work_package = {
        "component_work_package_id": f"AIML-{effect_class}-V2-WP",
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


# CP3 per-row ABI 綁定:一份合法 s2_4_component_effect_intent_v1(五 APPLY class 之一)。三個 common
# token(plan/pre_state/expiry)落頂層,class-specific token 落 required_intent_fields 物件的 digest 鍵。
_INTENT_D = "sha256:" + "a" * 64
_INTENT_D2 = "sha256:" + "b" * 64
_INTENT_TS = "2026-07-24T00:00:00Z"
_V2_APPLY_CLASSES = validator.S2_4_APPLY_ROW_CLASS_ORDER


def _component_effect_intent_v2(effect_class: str, **overrides: object) -> dict:
    keys = validator._S2_4_APPLY_INTENT_CLASS_TOKEN_FIELDS[effect_class].values()
    required_intent_fields = {
        key: ("engine-scanner-db" if key == "credential_name" else _INTENT_D)
        for key in keys
    }
    intent = {
        "schema_version": "s2_4_component_effect_intent_v1",
        "component_effect_class": effect_class,
        "install_plan_digest": _INTENT_D,
        "pre_state_digest": _INTENT_D2,
        "required_intent_fields": required_intent_fields,
        "expires_at": _INTENT_TS,
        "self_digest": _INTENT_D,
    }
    intent.update(overrides)
    intent["self_digest"] = validator.artifact_self_digest(intent)
    return intent


# --------------------------------------------------------------------------- #
# §6 #1 (via #24): seven v2 classes each derive exact §4 matrix fields
# --------------------------------------------------------------------------- #
def test_v2_seven_classes_each_derive_exact_matrix_fields() -> None:
    assert set(validator.AIML_COMPONENT_EFFECT_CLASS_MATRIX_V2) == set(_V2_EXPECTED_ABI)
    for effect_class, row in validator.AIML_COMPONENT_EFFECT_CLASS_MATRIX_V2.items():
        adapter, actor, postcheck, rollback, intent_fields = _V2_EXPECTED_ABI[
            effect_class
        ]
        # 矩陣逐行 = §4 ABI(CP3 將再斷言,這裡先釘死)。
        assert row["adapter_id"] == adapter
        assert row["actor_node_id"] == actor
        assert row["independent_postcheck_node_id"] == postcheck
        assert row["recovery_contract"] == rollback
        assert list(row["required_intent_fields"]) == intent_fields
        assert row["adapter_binding_status"] == "AUTHORITY_LOCKED_PRODUCTION_CAPABLE"

        classification = validator.classify_component_required_effects_v2(
            _component_work_package_v2(effect_class), classified_at=CLASSIFIED_AT
        )
        assert validator.validate_aiml_artifact(classification, now=CLASSIFIED_AT) == []
        assert classification["schema_version"] == (
            "aiml_component_effect_classification_v2"
        )
        assert classification["classifier_digest"] == (
            validator.aiml_component_effect_class_matrix_v2_digest()
        )
        (effect,) = classification["required_effects"]
        assert effect == {
            "effect_class": effect_class,
            "status": "REQUIRED_PENDING",
            "adapter_id": adapter,
            "actor_node_id": actor,
            "rollback_contract": rollback,
            "independent_postcheck_node_id": postcheck,
            "required_intent_fields": intent_fields,
            "adapter_binding_status": "AUTHORITY_LOCKED_PRODUCTION_CAPABLE",
        }

    # CP3:五個 APPLY row 的 typed component-effect intent 逐份 derive 出 exact §4 ABI 綁定,
    # 且中央閘接受該 intent(closed schema + per-row 綁定)。兩個前置類(HOST_CAPABILITY_PROBE /
    # LEARNING_RUNTIME_PREPARE)不走此 intent schema,故只在上方 classify 迴圈涵蓋。
    for effect_class in _V2_APPLY_CLASSES:
        adapter, actor, postcheck, rollback, intent_fields = _V2_EXPECTED_ABI[effect_class]
        intent = _component_effect_intent_v2(effect_class)
        assert validator.validate_aiml_artifact(intent) == [], effect_class
        binding = validator.derive_component_intent_binding(intent)
        assert binding == {
            "component_effect_class": effect_class,
            "adapter_id": adapter,
            "actor_node_id": actor,
            "independent_postcheck_node_id": postcheck,
            "recovery_contract": rollback,
            "adapter_binding_status": "AUTHORITY_LOCKED_PRODUCTION_CAPABLE",
            "required_intent_fields": intent_fields,
        }


def test_v2_matrix_carries_same_four_independence_invariants_as_v1() -> None:
    assert validator.AIML_COMPONENT_EFFECT_CLASS_V2_INVARIANTS == {
        "requires_ops_preflight": True,
        "requires_pm_operator_approved_intent": True,
        "requires_independent_ops_postcheck": True,
        "applier_is_not_sole_verifier": True,
    }


# --------------------------------------------------------------------------- #
# §6 #2: PINNED_COMPONENT_MATRIX_V2_DIGEST pin
# --------------------------------------------------------------------------- #
def test_v2_component_matrix_digest_pin() -> None:
    assert validator.aiml_component_effect_class_matrix_v2_digest() == (
        PINNED_COMPONENT_MATRIX_V2_DIGEST
    )


# --------------------------------------------------------------------------- #
# §6 #3: v2 digest distinct from v1 digest and from S0.3 classifier
# --------------------------------------------------------------------------- #
def test_v2_digest_is_distinct_from_v1_and_s0_3() -> None:
    v2 = validator.aiml_component_effect_class_matrix_v2_digest()
    assert v2 != validator.aiml_component_effect_class_matrix_digest()
    assert v2 != validator.aiml_effect_classifier_digest()
    assert v2 == PINNED_COMPONENT_MATRIX_V2_DIGEST


# --------------------------------------------------------------------------- #
# §6 #4: v1 matrix + v1 schema bytes + PROGRAM_SCHEMA_PATHS byte-frozen
# --------------------------------------------------------------------------- #
def test_v1_matrix_schema_and_program_schema_paths_byte_frozen() -> None:
    import hashlib

    assert validator.aiml_component_effect_class_matrix_digest() == (
        PINNED_COMPONENT_MATRIX_DIGEST
    )
    assert validator.aiml_effect_classifier_digest() == FROZEN_S0_3_CLASSIFIER_DIGEST
    v1_schema = (
        validator.SCHEMA_DIR / "aiml_component_effect_classification_v1.schema.json"
    ).read_bytes()
    assert "sha256:" + hashlib.sha256(v1_schema).hexdigest() == (
        FROZEN_COMPONENT_V1_SCHEMA_FILE_DIGEST
    )
    # v1 sibling schema 仍只在 SCHEMA_FILES 查找、絕不進入 PROGRAM_SCHEMA_PATHS(固定七名 tuple)。
    assert len(validator.PROGRAM_SCHEMA_PATHS) == 7
    assert not any(
        "component_effect_classification" in path
        for path in validator.PROGRAM_SCHEMA_PATHS
    )
    # v2 schema 亦僅 SCHEMA_FILES 查找,不觸 PROGRAM_SCHEMA_PATHS。
    assert "aiml_component_effect_classification_v2" in validator.SCHEMA_FILES
    assert (
        validator.SCHEMA_DIR
        / validator.SCHEMA_FILES["aiml_component_effect_classification_v2"]
    ).is_file()


# --------------------------------------------------------------------------- #
# §6 #5: a valid v2 step is accepted by the central validator
# --------------------------------------------------------------------------- #
def test_v2_valid_classification_step_is_accepted() -> None:
    classification = validator.classify_component_required_effects_v2(
        _component_work_package_v2("PG_ROLE_ACL_MIGRATION"), classified_at=CLASSIFIED_AT
    )
    assert validator.validate_aiml_artifact(classification, now=CLASSIFIED_AT) == []


# --------------------------------------------------------------------------- #
# §6 #6: cross-version digest rejected in BOTH directions
# --------------------------------------------------------------------------- #
def test_v2_artifact_carrying_v1_digest_is_rejected() -> None:
    classification = validator.classify_component_required_effects_v2(
        _component_work_package_v2("LEARNING_RUNTIME"), classified_at=CLASSIFIED_AT
    )
    forged = deepcopy(classification)
    forged["classifier_digest"] = validator.aiml_component_effect_class_matrix_digest()
    forged["classification_id"] = validator._component_effect_class_identity_digest(
        forged
    )
    forged["self_digest"] = validator.artifact_self_digest(forged)
    errors = validator.validate_aiml_artifact(forged, now=CLASSIFIED_AT)
    assert "AIML component effect v2 classifier digest is not admitted" in errors


def test_v1_artifact_carrying_v2_digest_is_rejected() -> None:
    classification = validator.classify_component_required_effects(
        _component_work_package("ENGINE_SCANNER"), classified_at=CLASSIFIED_AT
    )
    forged = deepcopy(classification)
    forged["classifier_digest"] = validator.aiml_component_effect_class_matrix_v2_digest()
    forged["classification_id"] = validator._component_effect_class_identity_digest(
        forged
    )
    forged["self_digest"] = validator.artifact_self_digest(forged)
    errors = validator.validate_aiml_artifact(forged, now=CLASSIFIED_AT)
    assert "AIML component effect classifier digest is not admitted" in errors


def test_v2_schema_version_does_not_match_v1_dispatch() -> None:
    # 同一 artifact 不會同時被兩個分支處理:v2 schema_version 只走 v2 分支。
    classification = validator.classify_component_required_effects_v2(
        _component_work_package_v2("HOST_CAPABILITY_PROBE"), classified_at=CLASSIFIED_AT
    )
    assert classification["schema_version"] == "aiml_component_effect_classification_v2"
    assert validator.validate_aiml_artifact(classification, now=CLASSIFIED_AT) == []


# --------------------------------------------------------------------------- #
# §6 #7: forged downgrade-to-NONE rejected by the central recompute
# --------------------------------------------------------------------------- #
def test_v2_validator_rejects_forged_downgrade_to_none() -> None:
    classification = validator.classify_component_required_effects_v2(
        _component_work_package_v2("CREDENTIAL_INSTALL"), classified_at=CLASSIFIED_AT
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
        "adapter_binding_status": "AUTHORITY_LOCKED_PRODUCTION_CAPABLE",
    }]
    errors = validator.validate_aiml_artifact(forged, now=CLASSIFIED_AT)
    assert "AIML component v2 required effects differ from classifier output" in errors


# --------------------------------------------------------------------------- #
# §6 #8: adapter-substitution rejected (classify + central recompute)
# --------------------------------------------------------------------------- #
def test_v2_adapter_substitution_is_rejected_at_classify() -> None:
    work_package = _component_work_package_v2(
        "ENGINE_SCANNER", declared_adapter_id="s2_4_prepare_adapter_v1"
    )
    with pytest.raises(ValueError, match="not the admitted adapter"):
        validator.classify_component_required_effects_v2(
            work_package, classified_at=CLASSIFIED_AT
        )


def test_v2_validator_rejects_forged_adapter_in_classified_inputs() -> None:
    classification = validator.classify_component_required_effects_v2(
        _component_work_package_v2("HOST_IDENTITY_INSTALL"), classified_at=CLASSIFIED_AT
    )
    forged = deepcopy(classification)
    forged["classified_inputs"]["declared_adapter_id"] = "s2_4_prepare_adapter_v1"
    forged["classification_id"] = validator._component_effect_class_identity_digest(
        forged
    )
    forged["self_digest"] = validator.artifact_self_digest(forged)
    errors = validator.validate_aiml_artifact(forged, now=CLASSIFIED_AT)
    assert any("is not admitted" in error for error in errors)


# --------------------------------------------------------------------------- #
# §6 #9: adapter_binding_status tamper rejected (schema enum is single-valued)
# --------------------------------------------------------------------------- #
def test_v2_binding_status_tamper_is_rejected_by_schema_enum() -> None:
    classification = validator.classify_component_required_effects_v2(
        _component_work_package_v2("LEARNING_RUNTIME_PREPARE"), classified_at=CLASSIFIED_AT
    )
    tampered = deepcopy(classification)
    # v1 的綁定值在 v2 schema enum 之外,故 schema-subset 檢查即拒。
    tampered["required_effects"][0]["adapter_binding_status"] = "IMPLEMENTED_DISPOSABLE"
    tampered["classification_id"] = validator._component_effect_class_identity_digest(
        tampered
    )
    tampered["self_digest"] = validator.artifact_self_digest(tampered)
    errors = validator.validate_aiml_artifact(tampered, now=CLASSIFIED_AT)
    assert any("enum" in error for error in errors)


# --------------------------------------------------------------------------- #
# §6 #10: intent-field-set tamper rejected (classify + central recompute)
# --------------------------------------------------------------------------- #
def test_v2_intent_field_set_tamper_is_rejected_at_classify() -> None:
    work_package = _component_work_package_v2("PG_ROLE_ACL_MIGRATION")
    work_package["declared_intent_fields"] = work_package["declared_intent_fields"][:-1]
    with pytest.raises(ValueError, match="do not match the exact"):
        validator.classify_component_required_effects_v2(
            work_package, classified_at=CLASSIFIED_AT
        )


def test_v2_validator_rejects_forged_intent_fields_in_required_effects() -> None:
    classification = validator.classify_component_required_effects_v2(
        _component_work_package_v2("HOST_CAPABILITY_PROBE"), classified_at=CLASSIFIED_AT
    )
    forged = deepcopy(classification)
    forged["required_effects"][0]["required_intent_fields"] = ["probe_scope"]
    forged["classification_id"] = validator._component_effect_class_identity_digest(
        forged
    )
    forged["self_digest"] = validator.artifact_self_digest(forged)
    errors = validator.validate_aiml_artifact(forged, now=CLASSIFIED_AT)
    assert "AIML component v2 required effects differ from classifier output" in errors


# --------------------------------------------------------------------------- #
# bypass-negative: an effectful v2 surface cannot be self-declared source-only
# --------------------------------------------------------------------------- #
def test_v2_declared_none_touching_component_surface_raises() -> None:
    work_package = {
        "component_work_package_id": "AIML-v2-sneaky-WP",
        "component_effect_class": "NONE",
        "declared_adapter_id": "none",
        "declared_intent_fields": ["irrelevant"],
        "owned_path_manifest": [],
        "direct_interfaces": ["s2_4_runtime_install_adapter_v1"],
    }
    with pytest.raises(ValueError, match="cannot be source-only"):
        validator.classify_component_required_effects_v2(
            work_package, classified_at=CLASSIFIED_AT
        )


# --------------------------------------------------------------------------- #
# §6 #22:host-identity 突變面只屬 HOST_IDENTITY_INSTALL;PG-permit intent 不得夾帶它。
# --------------------------------------------------------------------------- #
def test_host_identity_only_classifies_as_host_identity_install() -> None:
    # §4 token uid_gid_directory_manifest(host UID/GID/目錄突變)只出現在 HOST_IDENTITY_INSTALL 列。
    owners = [
        cls
        for cls, row in validator.AIML_COMPONENT_EFFECT_CLASS_MATRIX_V2.items()
        if "uid_gid_directory_manifest" in row["required_intent_fields"]
    ]
    assert owners == ["HOST_IDENTITY_INSTALL"]
    # 一份合法 HOST_IDENTITY_INSTALL intent 綁到 host-identity ABI,且中央閘接受。
    intent = _component_effect_intent_v2("HOST_IDENTITY_INSTALL")
    binding = validator.derive_component_intent_binding(intent)
    assert binding["adapter_id"] == "s2_4_host_identity_adapter_v1"
    assert binding["actor_node_id"] == "s2_4_host_identity_actor"
    assert binding["recovery_contract"] == "s2_4_host_identity_rollback_v1"
    assert binding["required_intent_fields"] == [
        "plan", "uid_gid_directory_manifest", "pre_state", "expiry",
    ]
    assert validator.validate_aiml_artifact(intent) == []


def test_pg_permit_cannot_authorize_host_identity_mutation() -> None:
    # PG_ROLE_ACL_MIGRATION 列的 required_intent_fields 排除任何 host uid/gid/目錄/身分突變 token。
    pg_row = validator.AIML_COMPONENT_EFFECT_CLASS_MATRIX_V2["PG_ROLE_ACL_MIGRATION"]
    assert not any(
        tok in pg_row["required_intent_fields"]
        for tok in ("uid_gid_directory_manifest", "host_identity", "credential_name")
    )
    # 一份 PG intent 夾帶 host-identity 面(uid_gid_directory_manifest_digest):intent schema 允許
    # (該鍵在共享 $defs 為合法可選,PG 必要鍵仍在),但 CP3 per-row 綁定關閉此縫 → extra 鍵拒。
    forged = _component_effect_intent_v2("PG_ROLE_ACL_MIGRATION")
    forged["required_intent_fields"]["uid_gid_directory_manifest_digest"] = _INTENT_D
    forged["self_digest"] = validator.artifact_self_digest(forged)
    schema = validator._load_schema("s2_4_component_effect_intent_v1")
    assert validator.schema_subset_errors(forged, schema, schema) == []  # schema 本身通過
    errors = validator.validate_aiml_artifact(forged)  # 但中央閘的 per-row 綁定拒
    assert any("do not match the exact §4 row set" in e for e in errors), errors
    with pytest.raises(ValueError, match="do not match the exact §4 row set"):
        validator.derive_component_intent_binding(forged)


# --------------------------------------------------------------------------- #
# per-row 綁定 tamper 反例:swapped adapter_id / short-or-extra intent-field set → 拒。
# --------------------------------------------------------------------------- #
def test_v2_per_row_binding_tamper_rejected() -> None:
    # swapped adapter_id(classify 的 per-row 綁定;caller 不能換 adapter)。
    with pytest.raises(ValueError, match="not the admitted adapter"):
        validator.classify_component_required_effects_v2(
            _component_work_package_v2(
                "ENGINE_SCANNER", declared_adapter_id="s2_4_prepare_adapter_v1"
            ),
            classified_at=CLASSIFIED_AT,
        )
    # short intent-field set(intent 缺 class 必要鍵)→ derive raise。
    short = _component_effect_intent_v2("PG_ROLE_ACL_MIGRATION")
    del short["required_intent_fields"]["acl_manifest_digest"]
    with pytest.raises(ValueError, match="do not match the exact §4 row set"):
        validator.derive_component_intent_binding(short)
    # 前置類/未知類不是五個 APPLY row → derive raise。
    with pytest.raises(ValueError, match="not one of the five"):
        validator.derive_component_intent_binding(
            _component_effect_intent_v2(
                "PG_ROLE_ACL_MIGRATION", component_effect_class="HOST_CAPABILITY_PROBE"
            )
        )
