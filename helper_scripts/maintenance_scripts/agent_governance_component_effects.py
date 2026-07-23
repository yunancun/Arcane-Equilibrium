"""Data-driven per-component deploy Adapter for AIML LR0B (S1.5).

This module is the single, data-driven per-component deploy Adapter the six
non-WORM rows of ``AIML_COMPONENT_EFFECT_CLASS_MATRIX`` (Engine/Scanner,
Learning-runtime, Controller/workers, Retention-apply, PG-role/ACL/migration,
Credential-rotation) each define.  It implements ONE apply/rollback/postcheck
skeleton (not six hand-coded adapters); the classes differ only by (a) the
matrix-derived exact-intent contract and (b) a disposable-target kind:

* ``temp_dir_artifact`` — a real ``0o700`` deploy root holding a content-addressed
  bundle store plus an atomic active-generation pointer (``os.replace`` swap +
  ``chmod 0o444`` immutable bundle), used by ENGINE_SCANNER / LEARNING_RUNTIME /
  CONTROLLER_WORKERS;
* ``temp_dir_objects`` — a real object set with a throwaway restore copy, real
  ``os.unlink`` delete + real copy-back restore, used by RETENTION_APPLY;
* ``disposable_pg`` — a real throwaway PostgreSQL cluster (the S1.1/S1.3 pattern),
  used by PG_ROLE_ACL_MIGRATION (real ``CREATE ROLE``/``GRANT`` apply,
  ``REVOKE``/``DROP`` rollback, reader still ``42501``-denied) and
  CREDENTIAL_ROTATION (real ``ALTER ROLE ... PASSWORD`` A->B->A, old-credential
  ``28P01`` rejection).

Two load-bearing invariants are MACHINE-enforced, never promised:

1. **Exact restoration** — ``pre_state_digest == post_rollback_digest`` (byte
   identity of the ACTIVE state projection).  A result claiming a clean
   apply/rollback with unequal digests RAISES (``rollback_not_exact``).
2. **Applier is not sole verifier** — the postcheck ``verifier_node`` must differ
   from the result ``apply_actor_node``; equal RAISES
   (``applier_is_sole_verifier``).

**Honest split (never faked).**  What is REAL and ``LOCAL_REPRODUCIBLE`` on this
Mac: the three disposable targets' apply/rollback/postcheck above (a real
``postgres`` emits genuine ``42501``/``28P01``; real ``os.replace``/``os.unlink``/
``chmod`` emit genuine state transitions).  What is honestly DEFERRED (recorded as
such, never simulated): a real ``systemctl``/service restart, running attestation,
cgroup/slice/UID, a production migration/role/credential slot, a real remote-host
mutation, and the REAL remote/platform-attested observation -> S1.6/S2.4/S2.5.
S1.5 makes NO network/remote contact and applies to NO production target
(``production`` target and ``production_apply_performed=true`` fail closed).

**Evidence-authenticity honesty (CLAUDE Typed Authority Matrix).**  A
``LOCAL_REPRODUCIBLE`` label on the receipt bytes is a self-attested summary: a
canonical self-digest authenticates integrity only, never who executed what.  The
distinct in-process verifier proves the *structural* independence rule, not
cryptographic actor authenticity or a real remote observation.  Any S2.4/S2.5
consumer relying on a ``LOCAL_REPRODUCIBLE`` component-effect receipt MUST re-run
the disposable proof or obtain platform attestation; it may not trust the
``evidence_class`` label alone.

Like S1.1/S1.3/S1.4 this module is stdlib-first (``hashlib``/``json``/``os``/
``shutil``/``tempfile``/``stat``); ``psycopg2`` is a lazy import used only in the
``disposable_pg`` path.  It consumes S1.3 (``agent_governance_identity_acl_contract``)
as a READ-ONLY import that is actually EXERCISED — a ``PG_ROLE_ACL_MIGRATION`` /
``CREDENTIAL_ROTATION`` intent is validated against S1.3's least-privilege
``assert_least_privilege_topology`` + rotation-order check + ``credential_slot_fingerprint``
so a non-least-privilege role delta / unsafe rotation order / mis-derived slot
fingerprint is rejected — and S1.4 (``hash_bundle_tree`` in
``agent_governance_runtime_candidate_spike``), and reuses the S1.2 WORM
``os.replace``/``chmod 0o444`` atomic primitive for the artifact swap.  The central validator recognizes the four typed
schemas additively (S1.5 injects NO live ``route_task`` node and NO
``closure_packet_v1`` effect binding; those route+apply a real effect and are S2.4).
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = Path(__file__).resolve()
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
for _candidate in (HELPER_DIR, ML_TRAINING_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

# 唯讀消費:S1.2 矩陣/classifier(中央 validator)+ S1.4 bundle 雜湊 + S1.3 憑證輪換觀察。
import aiml_gate_receipt_validator as central_validator  # noqa: E402
from agent_governance_runtime_candidate_spike import hash_bundle_tree  # noqa: E402
from agent_governance_identity_acl_contract import (  # noqa: E402
    assert_least_privilege_topology,
    credential_slot_fingerprint,
)
from agent_governance_schema import schema_subset_errors  # noqa: E402


SCHEMA_DIR = ML_TRAINING_DIR / "schemas" / "aiml_gate_receipts"
INTENT_SCHEMA_PATH = SCHEMA_DIR / "component_effect_intent_v1.schema.json"
RESULT_SCHEMA_PATH = SCHEMA_DIR / "component_effect_result_v1.schema.json"
ATTESTATION_SCHEMA_PATH = (
    SCHEMA_DIR / "component_effect_postcheck_attestation_v1.schema.json"
)
RECEIPT_SCHEMA_PATH = SCHEMA_DIR / "effect_seams_ready_receipt_v1.schema.json"

INTENT_SCHEMA_VERSION = "component_effect_intent_v1"
RESULT_SCHEMA_VERSION = "component_effect_result_v1"
ATTESTATION_SCHEMA_VERSION = "component_effect_postcheck_attestation_v1"
RECEIPT_SCHEMA_VERSION = "effect_seams_ready_receipt_v1"
HARNESS_ID = "component_effect_seams_harness_v1"
SPRINT_GATE_SCOPE = "S1.5_CONTRIBUTION"

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
# active-generation 指標 / prior_hash 只能是裸 sha256 hex(內容定址 bundle 名);任何 ../ 或
# 非 hex 值會讓 artifact_state_digest 去雜湊任意目錄 → 指標寫入/交換一律先過此白名單。
RAW_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SQLSTATE_RE = re.compile(r"^[0-9A-Z]{5}$")
# PG 識別碼白名單(角色/schema/表名皆由本模組控制,非使用者輸入;仍防禦性引號 + 限字元)。
_PG_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]*$")

# 六個非 WORM 的 deploy 元件類(S1.5 擁有;WORM 由 S1.2 落地,不在此)。
DEPLOY_COMPONENT_CLASSES = (
    "ENGINE_SCANNER",
    "LEARNING_RUNTIME",
    "CONTROLLER_WORKERS",
    "RETENTION_APPLY",
    "PG_ROLE_ACL_MIGRATION",
    "CREDENTIAL_ROTATION",
)
# 每類 -> 單一 disposable target kind(§4;CONTROLLER_WORKERS 以 artifact swap 為正規面)。
DISPOSABLE_TARGET_KIND_BY_CLASS = {
    "ENGINE_SCANNER": "temp_dir_artifact",
    "LEARNING_RUNTIME": "temp_dir_artifact",
    "CONTROLLER_WORKERS": "temp_dir_artifact",
    "RETENTION_APPLY": "temp_dir_objects",
    "PG_ROLE_ACL_MIGRATION": "disposable_pg",
    "CREDENTIAL_ROTATION": "disposable_pg",
}
DISPOSABLE_TARGET_KINDS = frozenset(DISPOSABLE_TARGET_KIND_BY_CLASS.values())

TARGET_CLASSES = frozenset({"disposable_local", "production"})
S1_TARGET_CLASS = "disposable_local"
EVIDENCE_CLASSES = frozenset({"LOCAL_REPRODUCIBLE", "STRUCTURAL_ONLY"})
APPLY_STATUSES = frozenset({
    "APPLIED_ROLLED_BACK_EXACT",
    "ROLLED_BACK_INTERRUPTED",
    "NOT_RESTORED_FAILED",
    "FAILED",
})
RUNTIME_WITNESS_KINDS = frozenset({
    "live_disposable_pg",
    "real_filesystem_atomic_swap",
    "real_object_delete_restore",
    "structural_contract",
})
TTL_CEILING_SECONDS = 3600

# §11 的 12 個 bypass-negative 種類;PASS rollup 必須十二者全部存在且皆 REJECTED。
BYPASS_KINDS = (
    "source_only_route_of_effectful_class",
    "generic_deploy_apply_enabled_without_per_class_contract",
    "apply_without_preflight",
    "apply_without_approved_intent",
    "apply_without_rollback_binding",
    "production_target",
    "applier_is_sole_verifier",
    "rollback_not_exact",
    "cross_class_adapter_substitution",
    "classifier_or_matrix_digest_tamper",
    "plaintext_secret_ingress",
    "apply_was_a_noop",
)
BYPASS_KIND_SET = frozenset(BYPASS_KINDS)

# S1.2 註冊表狀態(dependency 綁定用;deploy_adapter_v1 必仍 apply-disabled)。
WORM_SINK_STATUS = "declared_disposable_worm_emulation_implemented"
GENERIC_DEPLOY_ADAPTER_ID = "deploy_adapter_v1"
GENERIC_DEPLOY_DISABLED_STATUS = (
    "declared_apply_disabled_until_recovery_controls_bound"
)
REGISTRY_PATH = REPO_ROOT / ".codex" / "agent_registry_v1.json"

# temp_dir_artifact 佈署根的固定佈局。
_ACTIVE_POINTER = "active_generation"
_BUNDLES_DIR = "bundles"
_UNIT_FILE = "unit.service"
# temp_dir_objects 佈局。
_OBJECTS_DIR = "objects"
_RESTORE_DIR = "restore_capacity"

# 對序列化 payload 的機密掃描,沿用 S1.1/S1.3 風格(github token / auth header /
# credential 賦值 / postgres DSN 憑證形)。component-effect payload 皆為 digest/label。
SECRET_LIKE_RE = re.compile(
    r"(?:github_pat_|gh[pousr]_[A-Za-z0-9]{12,})"
    r"|(?:access[_-]?token|auth(?:orization)?|client[_-]?secret|password|"
    r"pgpassword|private[_-]?key)\s*[:=]"
    r"|(?:basic|bearer)\s+[A-Za-z0-9._~+/=-]{12,}"
    r"|postgres(?:ql)?://[^\s:/@]+:[^\s:/@]+@",
    re.IGNORECASE,
)
SECRET_PATTERNS_CHECKED = (
    "auth_scheme_token",
    "credential_assignment",
    "github_token",
    "postgres_dsn_credentials",
)

RECEIPT_FIELDS = frozenset({
    "schema_version",
    "harness_id",
    "status",
    "caller",
    "target_class",
    "governance_wiring",
    "admitted_classes",
    "observation_seam",
    "bypass_negatives",
    "dependency_receipts",
    "boundary",
    "sprint_gate_scope",
    "source_sha256",
    "schema_sha256",
    "secret_scan",
    "observation_time",
    "expires_at",
    "ttl_seconds",
    "failure_reason",
    "self_digest",
})


class ComponentEffectError(RuntimeError):
    """Base for a would-be artifact that cannot be safely emitted.

    Fail-closed: the Adapter raises (rather than emit an artifact) whenever
    emitting would fake evidence — a production target, a non-exact rollback
    claimed as exact, an applier that is its own sole verifier, or a secret-like
    value in a serialized payload.
    """


class SecretLeakageError(ComponentEffectError):
    """Raised when a would-be artifact field carries secret-like content."""


class ProductionTargetRejected(ComponentEffectError):
    """Raised when a ``production`` target reaches the S1.5 disposable gate."""


class NonExactRollbackError(ComponentEffectError):
    """Raised when a rollback claimed exact has ``pre != post`` digests.

    The exact-restoration crux is not fakeable: a result may honestly report
    ``NOT_RESTORED_FAILED``, but it may never claim a clean apply/rollback while
    the post-rollback digest differs from the pre-state digest.
    """


class ApplierIsSoleVerifierError(ComponentEffectError):
    """Raised when the postcheck verifier equals the apply actor node."""


# --------------------------------------------------------------------------- #
# canonical digest helpers (mirror agent_governance_pg_readonly_identity.py)
# --------------------------------------------------------------------------- #
def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_digest(value: Any) -> str:
    """Return the canonical sha256 identity used for pre-state / result digests."""

    return _sha256_bytes(_canonical_bytes(value))


def _file_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone is required")
    return parsed


@lru_cache(maxsize=1)
def source_sha256() -> str:
    """Return the sha256 identity of this Adapter module source."""

    return _file_sha256(SOURCE_PATH)


@lru_cache(maxsize=None)
def _schema(path_str: str) -> dict[str, Any]:
    return json.loads(Path(path_str).read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def schema_sha256(path_str: str) -> str:
    """Return the sha256 identity of a schema file."""

    return _file_sha256(Path(path_str))


def intent_digest(intent: dict[str, Any]) -> str:
    return canonical_digest(
        {key: value for key, value in intent.items() if key != "intent_digest"}
    )


def result_digest(result: dict[str, Any]) -> str:
    return canonical_digest(
        {key: value for key, value in result.items() if key != "result_digest"}
    )


def attestation_digest(attestation: dict[str, Any]) -> str:
    return canonical_digest(
        {key: value for key, value in attestation.items() if key != "attestation_digest"}
    )


def receipt_digest(receipt: dict[str, Any]) -> str:
    return canonical_digest(
        {key: value for key, value in receipt.items() if key != "self_digest"}
    )


# --------------------------------------------------------------------------- #
# secret scan (fail-closed, mirror S1.1/S1.3)
# --------------------------------------------------------------------------- #
def _contains_secret_like(value: Any) -> bool:
    if isinstance(value, str):
        return SECRET_LIKE_RE.search(value) is not None
    if isinstance(value, list):
        return any(_contains_secret_like(item) for item in value)
    if isinstance(value, dict):
        return any(
            _contains_secret_like(key) or _contains_secret_like(item)
            for key, item in value.items()
        )
    return False


def _guard_no_secret(payload: Any) -> None:
    # fail-closed:任何機密樣態即拒絕序列化,絕不發出帶密 artifact。
    if _contains_secret_like(payload):
        raise SecretLeakageError("component-effect payload carries secret-like content")


# --------------------------------------------------------------------------- #
# matrix-derived contract accessors (derive, never hand-declare — reuse S1.2)
# --------------------------------------------------------------------------- #
def _matrix_row(effect_class: str) -> dict[str, Any]:
    if effect_class not in DEPLOY_COMPONENT_CLASSES:
        raise ComponentEffectError(f"not an S1.5 deploy component class: {effect_class!r}")
    return central_validator.AIML_COMPONENT_EFFECT_CLASS_MATRIX[effect_class]


def required_intent_fields(effect_class: str) -> list[str]:
    """Return the exact matrix intent-field contract for a class (order preserved)."""

    return list(_matrix_row(effect_class)["required_intent_fields"])


def adapter_id_for(effect_class: str) -> str:
    return _matrix_row(effect_class)["adapter_id"]


def recovery_contract_for(effect_class: str) -> str:
    return _matrix_row(effect_class)["recovery_contract"]


def disposable_target_kind_for(effect_class: str) -> str:
    return DISPOSABLE_TARGET_KIND_BY_CLASS[effect_class]


def class_invariants() -> dict[str, Any]:
    return dict(central_validator.AIML_COMPONENT_EFFECT_CLASS_INVARIANTS)


def component_effect_matrix_digest() -> str:
    return central_validator.aiml_component_effect_class_matrix_digest()


def _typed_confirm(effect_class: str, disposable_target_kind: str, intent_id: str) -> str:
    return f"component-effect:{effect_class}:{disposable_target_kind}:{intent_id}"


# 消費 S1.3:對 PG-role/credential 兩類 intent 做真實最小權限 / 輪換順序 conformance。
# assert_least_privilege_topology 的每條錯誤都以 over_grant_kind 前綴,擷取本檢查關切的種類。
_S13_ROLE_OVER_GRANT_KINDS = frozenset({"writer_role_for_reader", "superuser_role", "shared_role"})
_S13_ROTATION_OVER_GRANT_KINDS = frozenset({"unsafe_rotation_order"})


def _s13_kinds(errors: list[str], keep: frozenset[str]) -> list[str]:
    return [error for error in errors if error.split(":", 1)[0] in keep]


def _assert_s13_intent_conformance(effect_class: str, intent_fields: dict[str, Any]) -> list[str]:
    """Reject a non-least-privilege PG / credential intent using the S1.3 contract.

    Reuses S1.3 ``assert_least_privilege_topology`` (the PG role/ACL delta) + its
    rotation-order check + ``credential_slot_fingerprint`` (credential rotation) so the
    "consumes S1.3" binding is EXERCISED, not merely imported: a superuser /
    reader-with-write role delta, an unsafe rotation order, or a mis-derived slot
    fingerprint is rejected here (other topology facets, e.g. host UID / socket, are out
    of an intent's scope and their over-grant kinds are deliberately not consulted).
    """

    if effect_class == "PG_ROLE_ACL_MIGRATION":
        delta = intent_fields.get("role_acl_delta")
        roles = delta.get("pg_role_topology") if isinstance(delta, dict) else None
        if not isinstance(roles, list) or not roles:
            return ["component effect PG role_acl_delta must carry a non-empty pg_role_topology"]
        return _s13_kinds(
            assert_least_privilege_topology({"pg_role_topology": roles}),
            _S13_ROLE_OVER_GRANT_KINDS,
        )
    if effect_class == "CREDENTIAL_ROTATION":
        errors = _s13_kinds(
            assert_least_privilege_topology(
                {"secret_lifecycle": {"rotation": {"rotation_order": intent_fields.get("rotation_order")}}}
            ),
            _S13_ROTATION_OVER_GRANT_KINDS,
        )
        slot = intent_fields.get("secret_slot_target")
        if not isinstance(slot, str) or not slot:
            errors.append("component effect credential intent lacks a secret_slot_target for the S1.3 fingerprint")
        else:
            if intent_fields.get("old_fingerprint") != credential_slot_fingerprint(slot, "old"):
                errors.append("component effect credential old_fingerprint is not the S1.3 slot fingerprint")
            if intent_fields.get("new_fingerprint") != credential_slot_fingerprint(slot, "new"):
                errors.append("component effect credential new_fingerprint is not the S1.3 slot fingerprint")
        return errors
    return []


def _disposable_intent_fields(effect_class: str) -> dict[str, Any]:
    """Return non-secret placeholder values for the matrix intent-field key-set.

    A disposable proof binds the exact matrix key-set (Python-enforced); the values
    are non-secret disposable-proof labels (the load-bearing binding is the rollback
    ``pre_state_digest``, not these illustrative values).  The two S1.3-bound classes
    additionally carry a least-privilege-CONFORMANT role delta / rotation order so the
    honest disposable path passes ``_assert_s13_intent_conformance`` (the negatives
    mutate these into non-least-privilege shapes).
    """

    if effect_class == "PG_ROLE_ACL_MIGRATION":
        return {
            "migration_id": "aiml_disposable_migration",
            "migration_checksum": canonical_digest({"disposable_migration_checksum": effect_class}),
            "role_acl_delta": {
                "pg_role_topology": [
                    {
                        "component": "fit_evaluation",
                        "role_name": "aiml_disposable_migration_role",
                        "privilege_class": "migration_apply",
                        "is_superuser": False,
                        "forbidden_attrs_all_false": True,
                        "is_reader": False,
                        "writer_for_reader": False,
                    }
                ]
            },
            "pre_state_digest": canonical_digest({"disposable_pre_state": effect_class}),
            "transactional_or_double_apply": "transactional",
            "recovery": "rollback_or_approved_forward",
        }
    if effect_class == "CREDENTIAL_ROTATION":
        slot = "aiml_disposable_credential_slot"
        return {
            "secret_slot_target": slot,
            "role_target": "aiml_disposable_rotation_role",
            "old_fingerprint": credential_slot_fingerprint(slot, "old"),
            "new_fingerprint": credential_slot_fingerprint(slot, "new"),
            "rotation_order": ["stage_new_secret", "alter_role_credential", "revoke_old_secret"],
            "old_credential_rejection_proof": {
                "attempted": "connect_with_superseded_credential",
                "verdict": "DENIED",
            },
        }
    return {field: f"disposable-proof:{effect_class}:{field}" for field in required_intent_fields(effect_class)}


# --------------------------------------------------------------------------- #
# intent builder + validator
# --------------------------------------------------------------------------- #
def build_component_effect_intent(
    *,
    effect_class: str,
    target_class: str,
    pre_state_digest: str,
    apply_actor_node: str,
    independent_postcheck_node: str,
    approved_by: str,
    approved_at: str,
    ttl_seconds: int,
    intent_id: str,
    intent_fields: dict[str, Any] | None = None,
    ops_preflight_ready: bool = True,
    include_ops_preflight: bool = True,
    include_rollback_binding: bool = True,
    include_approval: bool = True,
) -> dict[str, Any]:
    """Build one canonical, self-hashed ``component_effect_intent_v1``.

    ``adapter_id`` / ``disposable_target_kind`` / ``recovery_contract`` /
    ``class_invariants`` are DERIVED from the matrix (a caller cannot supply or
    downgrade them).  ``production`` fails closed (raise).  The optional
    ``include_*`` toggles exist ONLY to drive the fail-closed bypass-negatives
    (an intent missing preflight / approval / rollback binding must be rejected).
    """

    if effect_class not in DEPLOY_COMPONENT_CLASSES:
        raise ComponentEffectError(f"not an S1.5 deploy component class: {effect_class!r}")
    if target_class not in TARGET_CLASSES:
        raise ComponentEffectError(f"unrecognized target_class: {target_class!r}")
    if target_class != S1_TARGET_CLASS:
        # production 一律 fail-closed:S1.5 只對 disposable 施加 effect(S2.0/S2.4 才是真 apply)。
        raise ProductionTargetRejected(
            "S1.5 applies to disposable_local only; production is rejected fail-closed"
        )
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
        raise ComponentEffectError("ttl_seconds must be an integer")
    if not (1 <= ttl_seconds <= TTL_CEILING_SECONDS):
        raise ComponentEffectError(f"ttl_seconds must be within [1, {TTL_CEILING_SECONDS}]")
    if not DIGEST_RE.fullmatch(str(pre_state_digest)):
        raise ComponentEffectError("pre_state_digest must be a sha256 digest")

    disposable_target_kind = disposable_target_kind_for(effect_class)
    approved = _parse_time(approved_at)
    expires = approved + timedelta(seconds=ttl_seconds)
    fields = dict(intent_fields) if intent_fields is not None else _disposable_intent_fields(effect_class)

    intent: dict[str, Any] = {
        "schema_version": INTENT_SCHEMA_VERSION,
        "intent_id": intent_id,
        "effect_class": effect_class,
        "adapter_id": adapter_id_for(effect_class),
        "disposable_target_kind": disposable_target_kind,
        "target_class": target_class,
        "intent_fields": fields,
        "class_invariants": class_invariants(),
        "apply_actor_node": apply_actor_node,
        "independent_postcheck_node": independent_postcheck_node,
        "approved_at": approved.isoformat(),
        "expires_at": expires.isoformat(),
        "hard_stops": [
            "disposable_local target only; production is rejected fail-closed",
            "no real service restart / remote-host mutation / production migration",
            "the applier node cannot be its own sole verifier",
            "no plaintext secret ingress",
        ],
        "typed_confirm": _typed_confirm(effect_class, disposable_target_kind, intent_id),
        "ttl_seconds": ttl_seconds,
    }
    if include_ops_preflight:
        intent["ops_preflight"] = {
            "preflight_id": f"ops-preflight:{intent_id}",
            "ready": bool(ops_preflight_ready),
            "observed_at": approved.isoformat(),
            "expires_at": expires.isoformat(),
        }
    if include_rollback_binding:
        intent["rollback_binding"] = {
            "recovery_contract": recovery_contract_for(effect_class),
            "pre_state_digest": pre_state_digest,
        }
    if include_approval:
        intent["approved_by"] = approved_by
    _guard_no_secret(intent)
    intent["intent_digest"] = intent_digest(intent)
    return intent


def validate_component_effect_intent(intent: Any, *, now: str) -> list[str]:
    """Validate intent structure/integrity + the disposable-apply admission gate."""

    if not isinstance(intent, dict):
        return ["component effect intent must be an object"]
    schema = _schema(str(INTENT_SCHEMA_PATH))
    errors = [
        f"component effect intent schema violation: {error}"
        for error in schema_subset_errors(intent, schema, schema)
    ]
    if errors:
        return errors

    effect_class = intent.get("effect_class")
    if effect_class not in DEPLOY_COMPONENT_CLASSES:
        errors.append("component effect intent effect_class is not an S1.5 deploy class")
        return errors
    if intent.get("adapter_id") != adapter_id_for(effect_class):
        errors.append("component effect intent adapter_id is not the matrix adapter for the class")
    if intent.get("disposable_target_kind") != disposable_target_kind_for(effect_class):
        errors.append("component effect intent disposable_target_kind is not the class target kind")
    if intent.get("target_class") != S1_TARGET_CLASS:
        errors.append("component effect intent target_class must be disposable_local (production rejected)")
    if intent.get("class_invariants") != class_invariants():
        errors.append("component effect intent class_invariants are not the exact matrix invariants")
    fields = intent.get("intent_fields")
    if not isinstance(fields, dict) or sorted(fields) != sorted(required_intent_fields(effect_class)):
        errors.append("component effect intent_fields are not exactly the matrix required_intent_fields")
    else:
        # 消費 S1.3:PG-role/credential intent 的 delta/rotation 必須符合 S1.3 最小權限契約。
        errors.extend(_assert_s13_intent_conformance(effect_class, fields))
    rollback = intent.get("rollback_binding") or {}
    if rollback.get("recovery_contract") != recovery_contract_for(effect_class):
        errors.append("component effect intent rollback recovery_contract is not the matrix contract")
    if intent.get("typed_confirm") != _typed_confirm(
        effect_class, intent.get("disposable_target_kind"), str(intent.get("intent_id"))
    ):
        errors.append("component effect intent typed_confirm is not bound to class/kind/intent_id")
    if intent.get("intent_digest") != intent_digest(intent):
        errors.append("component effect intent_digest does not match canonical intent")
    if _contains_secret_like({k: v for k, v in intent.items()}):
        errors.append("component effect intent carries secret-like content")
    try:
        approved = _parse_time(str(intent.get("approved_at", "")))
        expires = _parse_time(str(intent.get("expires_at", "")))
        current = _parse_time(now)
        preflight = intent.get("ops_preflight") or {}
        observed = _parse_time(str(preflight.get("observed_at", "")))
        preflight_expiry = _parse_time(str(preflight.get("expires_at", "")))
        if not approved <= current < expires:
            errors.append("component effect intent is outside its approval window")
        if expires - approved > timedelta(seconds=TTL_CEILING_SECONDS):
            errors.append("component effect intent TTL exceeds its ceiling")
        if not observed <= current < preflight_expiry:
            errors.append("component effect OPS preflight is stale")
    except (TypeError, ValueError):
        errors.append("component effect intent timestamps are invalid")
    return errors


def refuse_apply_without_contract(intent: dict[str, Any], *, now: str) -> None:
    """Fail-closed apply gate: raise unless the intent fully admits a disposable apply.

    An intent missing an OPS preflight, a PM/operator approval, or a rollback
    binding — or targeting production — is refused here (the generic deploy apply
    stays disabled for a class without its per-class contract).
    """

    errors = validate_component_effect_intent(intent, now=now)
    if errors:
        raise ComponentEffectError(
            "intent does not admit a disposable apply: " + "; ".join(errors)
        )
    if intent.get("target_class") != S1_TARGET_CLASS:
        raise ProductionTargetRejected("apply refuses a non-disposable target_class")


# --------------------------------------------------------------------------- #
# disposable target: temp_dir_artifact (content-addressed bundle + atomic pointer)
# --------------------------------------------------------------------------- #
def _pg_ident(name: Any) -> str:
    if not isinstance(name, str) or not _PG_IDENT_RE.fullmatch(name):
        raise ComponentEffectError(f"unsafe SQL identifier: {name!r}")
    return '"' + name + '"'


def _chmod_bundle_immutable(bundle_dir: Path) -> None:
    # committed bundle 檔案 chmod 0o444(immutable-after-write,S1.2 WORM 前例);目錄保持
    # 0o700 供 traverse 與日後清理。
    for path in bundle_dir.rglob("*"):
        if path.is_file():
            os.chmod(path, 0o444)


def _confined_child(base: Path, rel: str) -> Path:
    """Return ``base / rel`` or fail closed unless it stays strictly within ``base``.

    Bundle/object keys are DATA the Adapter writes/restores; an absolute key, a ``..``
    escape, a symlink-escape, or a NUL/empty key would be an out-of-confinement write —
    rejected before any filesystem touch (mirrors the ``objects_apply`` deleter guard).
    """

    if not isinstance(rel, str) or not rel or "\x00" in rel:
        raise ComponentEffectError(f"unsafe filesystem key (empty/NUL): {rel!r}")
    if os.path.isabs(rel):
        raise ComponentEffectError(f"unsafe filesystem key (absolute): {rel!r}")
    candidate = base / rel
    if not _within(base, candidate):
        raise ComponentEffectError(f"filesystem key escapes its confinement: {rel!r}")
    return candidate


def _guard_pointer_hash(value: Any) -> str:
    # active-generation 指標 / prior_hash 必為裸 sha256 hex,否則拒絕(擋 ../ 指標雜湊任意目錄)。
    if not isinstance(value, str) or not RAW_SHA256_RE.fullmatch(value):
        raise ComponentEffectError(f"deploy pointer must be a bare sha256 hex: {value!r}")
    return value


def _stage_bundle(root: Path, files: dict[str, bytes]) -> str:
    """Content-address a bundle into ``bundles/<sha256>`` and return the raw hash."""

    bundles = root / _BUNDLES_DIR
    bundles.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="stage_", dir=bundles))
    try:
        for rel, data in sorted(files.items()):
            target = _confined_child(staging, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    except ComponentEffectError:
        # 被拒鍵不得留下半成品 staging(錯誤路徑亦保持 disposable 根乾淨)。
        shutil.rmtree(staging, ignore_errors=True)
        raise
    closure_hash, _count = hash_bundle_tree(staging)  # S1.4 read-only
    raw = closure_hash.split(":", 1)[1]
    final = bundles / raw
    if final.exists():
        # 內容定址:同內容已存在 → 丟棄 staging(冪等)。
        shutil.rmtree(staging, ignore_errors=True)
    else:
        os.replace(staging, final)
        _chmod_bundle_immutable(final)
    return raw


def _write_pointer_initial(root: Path, bundle_hash: str) -> None:
    (root / _ACTIVE_POINTER).write_text(_guard_pointer_hash(bundle_hash), encoding="utf-8")


def _swap_pointer(root: Path, bundle_hash: str) -> None:
    # 原子邊界(S1.2 WORM 前例):先驗證裸 hex 指標再寫 tmp,最後 os.replace 覆蓋 active-generation。
    safe = _guard_pointer_hash(bundle_hash)
    tmp = root / (_ACTIVE_POINTER + ".tmp." + uuid.uuid4().hex)
    tmp.write_text(safe, encoding="utf-8")
    os.replace(tmp, root / _ACTIVE_POINTER)


def artifact_deploy_root_init(
    root: str | os.PathLike[str],
    *,
    prior_bundle_files: dict[str, bytes],
    unit_text: bytes | None = None,
) -> str:
    """Materialize a private ``0o700`` deploy root; return the prior bundle hash."""

    root_path = Path(root)
    os.makedirs(root_path, exist_ok=True)
    os.chmod(root_path, 0o700)
    prior_hash = _stage_bundle(root_path, prior_bundle_files)
    _write_pointer_initial(root_path, prior_hash)
    if unit_text is not None:
        (root_path / _UNIT_FILE).write_bytes(unit_text)
    return prior_hash


def artifact_state_digest(root: str | os.PathLike[str]) -> str:
    """Digest the ACTIVE deployment projection (pointer + active bundle + unit)."""

    root_path = Path(root)
    active = (root_path / _ACTIVE_POINTER).read_text(encoding="utf-8")
    active_bundle = root_path / _BUNDLES_DIR / active
    if active_bundle.is_dir():
        bundle_closure, count = hash_bundle_tree(active_bundle)
    else:
        bundle_closure, count = "sha256:" + "0" * 64, 0
    unit = root_path / _UNIT_FILE
    unit_sha = _file_sha256(unit) if unit.is_file() else None
    return canonical_digest({
        "active_generation": active,
        "active_bundle_closure": bundle_closure,
        "active_bundle_file_count": count,
        "unit_service_sha256": unit_sha,
    })


def artifact_apply(root: str | os.PathLike[str], *, new_bundle_files: dict[str, bytes]) -> tuple[str, str]:
    """Stage a new bundle, atomically swap the pointer; return (new_hash, applied_digest)."""

    new_hash = _stage_bundle(Path(root), new_bundle_files)
    _swap_pointer(Path(root), new_hash)
    return new_hash, artifact_state_digest(root)


def artifact_apply_interrupted(root: str | os.PathLike[str], *, new_bundle_files: dict[str, bytes]) -> str:
    """Stage a new bundle but NEVER swap the pointer (prior generation stays active)."""

    _stage_bundle(Path(root), new_bundle_files)
    return artifact_state_digest(root)  # == pre-state(指標未動)


def artifact_rollback(root: str | os.PathLike[str], *, prior_hash: str) -> str:
    """Atomically swap the pointer back to the prior bundle; return post-rollback digest."""

    _swap_pointer(Path(root), prior_hash)
    return artifact_state_digest(root)


# --------------------------------------------------------------------------- #
# disposable target: temp_dir_objects (real delete + restore, retention)
# --------------------------------------------------------------------------- #
def _within(base: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def objects_root_init(root: str | os.PathLike[str], *, objects: dict[str, bytes]) -> str:
    """Materialize a private object set + a throwaway restore copy; return pre digest."""

    root_path = Path(root)
    os.makedirs(root_path, exist_ok=True)
    os.chmod(root_path, 0o700)
    obj_dir = root_path / _OBJECTS_DIR
    restore = root_path / _RESTORE_DIR
    for rel, data in sorted(objects.items()):
        for base in (obj_dir, restore):
            target = base / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    return objects_state_digest(root_path)


def objects_state_digest(root: str | os.PathLike[str]) -> str:
    closure, count = hash_bundle_tree(Path(root) / _OBJECTS_DIR)
    return canonical_digest({"objects_closure": closure, "object_count": count})


def objects_apply(root: str | os.PathLike[str], *, tombstone_set: list[str]) -> str:
    """Real tombstone-delete of EXACTLY the declared object set (never beyond it)."""

    obj_dir = Path(root) / _OBJECTS_DIR
    for rel in tombstone_set:
        target = obj_dir / rel
        # deleter 身分不得超出宣告的 tombstone 集(拒絕 base 之外/不存在的路徑)。
        if not _within(obj_dir, target) or not target.is_file():
            raise ComponentEffectError(
                f"tombstone target outside the declared object set / missing: {rel!r}"
            )
        os.unlink(target)
    return objects_state_digest(root)


def objects_rollback(root: str | os.PathLike[str], *, tombstone_set: list[str]) -> str:
    """Restore the exact tombstoned set from the throwaway restore copy (real copy-back)."""

    obj_dir = Path(root) / _OBJECTS_DIR
    restore = Path(root) / _RESTORE_DIR
    for rel in tombstone_set:
        # 還原身分同樣不得逾越:restore 來源與 obj_dir 目的地都必須嚴格受限(deleter 拒的 rel,
        # 還原亦拒),否則 ../ / 絕對路徑 / symlink 逃逸會造成任意目錄建立 + 檔案寫入。
        src = _confined_child(restore, rel)
        dst = _confined_child(obj_dir, rel)
        if not src.is_file():
            raise ComponentEffectError(f"restore source missing / not a file: {rel!r}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return objects_state_digest(root)


# --------------------------------------------------------------------------- #
# disposable target: disposable_pg (role/ACL apply+rollback, credential rotation)
# --------------------------------------------------------------------------- #
def pg_role_acl_state_digest(cursor: Any, *, role: str, schema: str, table: str) -> str:
    """Digest the role + its table-grant catalog projection (a real catalog read)."""

    cursor.execute(
        "SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, rolreplication "
        "FROM pg_catalog.pg_roles WHERE rolname = %s",
        (role,),
    )
    role_rows = [list(row) for row in cursor.fetchall()]
    cursor.execute(
        "SELECT grantee, privilege_type FROM information_schema.role_table_grants "
        "WHERE table_schema = %s AND table_name = %s AND grantee = %s "
        "ORDER BY privilege_type",
        (schema, table, role),
    )
    grant_rows = [list(row) for row in cursor.fetchall()]
    return canonical_digest({"role": role_rows, "grants": grant_rows})


def pg_role_acl_apply(cursor: Any, *, role: str, schema: str, table: str) -> None:
    """Real CREATE ROLE + least-privilege GRANT (the disposable migration apply)."""

    cursor.execute(f"CREATE ROLE {_pg_ident(role)} NOLOGIN")
    cursor.execute(f"GRANT USAGE ON SCHEMA {_pg_ident(schema)} TO {_pg_ident(role)}")
    cursor.execute(
        f"GRANT SELECT ON {_pg_ident(schema)}.{_pg_ident(table)} TO {_pg_ident(role)}"
    )


def pg_role_acl_rollback(cursor: Any, *, role: str, schema: str, table: str) -> None:
    """Real REVOKE + DROP ROLE (the disposable migration rollback)."""

    cursor.execute(
        f"REVOKE ALL ON {_pg_ident(schema)}.{_pg_ident(table)} FROM {_pg_ident(role)}"
    )
    cursor.execute(f"REVOKE ALL ON SCHEMA {_pg_ident(schema)} FROM {_pg_ident(role)}")
    cursor.execute(f"DROP ROLE IF EXISTS {_pg_ident(role)}")


def _probe_connects(connect: Callable[[], Any]) -> bool:
    try:
        connection = connect()
    except Exception:  # noqa: BLE001 - 任何驅動錯誤即視為連不上
        return False
    try:
        connection.close()
    except Exception:  # pragma: no cover - best effort  # noqa: BLE001
        pass
    return True


def pg_credential_generation_probe(
    connect_a: Callable[[], Any], connect_b: Callable[[], Any]
) -> dict[str, Any]:
    """Probe which credential generation currently connects (a real runtime read)."""

    a_connects = _probe_connects(connect_a)
    b_connects = _probe_connects(connect_b)
    if a_connects and not b_connects:
        generation = "A"
    elif b_connects and not a_connects:
        generation = "B"
    elif a_connects and b_connects:
        generation = "BOTH"
    else:
        generation = "NONE"
    return {
        "a_connects": a_connects,
        "b_connects": b_connects,
        "active_generation": generation,
    }


def pg_credential_state_digest(probe: dict[str, Any]) -> str:
    """Digest the OBSERVED credential-generation projection (non-vacuous)."""

    return canonical_digest({
        "active_generation": probe["active_generation"],
        "a_connects": probe["a_connects"],
        "b_connects": probe["b_connects"],
    })


# --------------------------------------------------------------------------- #
# result builder + validator (exact-restoration crux, machine-enforced)
# --------------------------------------------------------------------------- #
def build_component_effect_result(
    *,
    intent: dict[str, Any],
    apply_status: str,
    pre_state_digest: str,
    applied_digest: str | None,
    post_rollback_digest: str,
    apply_actor_node: str,
    applied_observed: bool,
    observation_window_stable: bool,
    runtime_witness_kind: str,
    observed_sqlstate: str | None,
    evidence_class: str,
    started_at: str,
    completed_at: str,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    """Build one canonical, self-hashed ``component_effect_result_v1``.

    Machine-enforced crux: ``APPLIED_ROLLED_BACK_EXACT`` / ``ROLLED_BACK_INTERRUPTED``
    REQUIRE ``pre_state_digest == post_rollback_digest`` (else raise
    ``NonExactRollbackError``); ``NOT_RESTORED_FAILED`` requires they DIFFER.
    ``production`` target and any ``production_apply_performed`` claim fail closed.
    """

    if not isinstance(intent, dict):
        raise ComponentEffectError("result requires the admitted intent")
    if intent.get("target_class") != S1_TARGET_CLASS:
        raise ProductionTargetRejected("result refuses a non-disposable target_class")
    if apply_status not in APPLY_STATUSES:
        raise ComponentEffectError(f"unrecognized apply_status: {apply_status!r}")
    if evidence_class not in EVIDENCE_CLASSES:
        raise ComponentEffectError(f"unrecognized evidence_class: {evidence_class!r}")
    if runtime_witness_kind not in RUNTIME_WITNESS_KINDS:
        raise ComponentEffectError(f"unrecognized runtime_witness_kind: {runtime_witness_kind!r}")
    for digest in (pre_state_digest, post_rollback_digest):
        if not DIGEST_RE.fullmatch(str(digest)):
            raise ComponentEffectError("pre/post digests must be sha256 digests")
    if observed_sqlstate is not None and not SQLSTATE_RE.fullmatch(str(observed_sqlstate)):
        raise ComponentEffectError("observed_sqlstate must be a 5-char SQLSTATE or null")
    if evidence_class == "LOCAL_REPRODUCIBLE" and runtime_witness_kind == "structural_contract":
        raise ComponentEffectError("LOCAL_REPRODUCIBLE requires a real runtime witness")

    exact = pre_state_digest == post_rollback_digest
    if apply_status in {"APPLIED_ROLLED_BACK_EXACT", "ROLLED_BACK_INTERRUPTED"}:
        if not exact:
            # 宣稱乾淨 apply/rollback 卻 pre != post → 造假 exact restoration,fail-closed。
            raise NonExactRollbackError(
                "a clean apply/rollback claim requires pre_state_digest == post_rollback_digest"
            )
        rollback_restored_exact = True
        if apply_status == "APPLIED_ROLLED_BACK_EXACT":
            if not applied_observed:
                raise ComponentEffectError("APPLIED_ROLLED_BACK_EXACT requires applied_observed")
            # apply 必須真的改變過 active 狀態:applied 缺失或等於 pre 代表 no-op apply,會讓
            # 「exact restoration」空洞可造假(applied==pre==post 也能「證明」乾淨回滾)→ fail-closed。
            # 此檢查僅限 APPLIED_ROLLED_BACK_EXACT;ROLLED_BACK_INTERRUPTED 的 applied==pre 為合法
            # (指標從未 swap,先前世代仍 active)。
            if applied_digest is None or applied_digest == pre_state_digest:
                raise NonExactRollbackError(
                    "APPLIED_ROLLED_BACK_EXACT requires the apply to change state "
                    "(applied_digest must be present and differ from pre_state_digest)"
                )
            resolved_failure = None
        else:
            resolved_failure = failure_reason or (
                "apply interrupted before commit; prior generation left active"
            )
    elif apply_status == "NOT_RESTORED_FAILED":
        if exact:
            raise ComponentEffectError("NOT_RESTORED_FAILED contradicts an exact restoration")
        rollback_restored_exact = False
        resolved_failure = failure_reason or (
            "post-rollback digest does not equal pre-state; the target was not restored"
        )
    else:  # FAILED
        rollback_restored_exact = False
        resolved_failure = failure_reason or "apply failed before a committed effect"

    started = _parse_time(started_at)
    completed = _parse_time(completed_at)
    result: dict[str, Any] = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "intent_id": intent.get("intent_id"),
        "intent_digest": intent.get("intent_digest"),
        "effect_class": intent.get("effect_class"),
        "adapter_id": intent.get("adapter_id"),
        "disposable_target_kind": intent.get("disposable_target_kind"),
        "target_class": S1_TARGET_CLASS,
        "apply_status": apply_status,
        "pre_state_digest": pre_state_digest,
        "applied_digest": applied_digest,
        "post_rollback_digest": post_rollback_digest,
        "rollback_restored_exact": rollback_restored_exact,
        "apply_actor_node": apply_actor_node,
        "observation": {
            "applied_observed": bool(applied_observed),
            "observation_window_stable": bool(observation_window_stable),
            "detail_digest": canonical_digest({
                "apply_status": apply_status,
                "pre": pre_state_digest,
                "applied": applied_digest,
                "post": post_rollback_digest,
            }),
            "runtime_witness": {
                "kind": runtime_witness_kind,
                "observed_sqlstate": observed_sqlstate,
            },
        },
        "evidence_class": evidence_class,
        "production_apply_performed": False,
        "real_service_restart": False,
        "real_remote_host_mutation": False,
        "started_at": started.isoformat(),
        "completed_at": completed.isoformat(),
        "evidence_expires_at": (completed + timedelta(minutes=15)).isoformat(),
        "failure_reason": resolved_failure,
    }
    _guard_no_secret(result)
    result["result_digest"] = result_digest(result)
    return result


def validate_component_effect_result(result: Any, *, now: str | None = None) -> list[str]:
    """Validate result structure/integrity + the exact-restoration crux."""

    if not isinstance(result, dict):
        return ["component effect result must be an object"]
    schema = _schema(str(RESULT_SCHEMA_PATH))
    errors = [
        f"component effect result schema violation: {error}"
        for error in schema_subset_errors(result, schema, schema)
    ]
    if errors:
        return errors

    effect_class = result.get("effect_class")
    if effect_class not in DEPLOY_COMPONENT_CLASSES:
        errors.append("component effect result effect_class is not an S1.5 deploy class")
        return errors
    if result.get("adapter_id") != adapter_id_for(effect_class):
        errors.append("component effect result adapter_id is not the matrix adapter for the class")
    if result.get("disposable_target_kind") != disposable_target_kind_for(effect_class):
        errors.append("component effect result disposable_target_kind is not the class target kind")
    if result.get("target_class") != S1_TARGET_CLASS:
        errors.append("component effect result target_class must be disposable_local")
    for flag in ("production_apply_performed", "real_service_restart", "real_remote_host_mutation"):
        if result.get(flag) is not False:
            errors.append(f"component effect result {flag} must be false")

    status = result.get("apply_status")
    exact = result.get("pre_state_digest") == result.get("post_rollback_digest")
    restored = result.get("rollback_restored_exact")
    if status in {"APPLIED_ROLLED_BACK_EXACT", "ROLLED_BACK_INTERRUPTED"}:
        if not exact:
            errors.append("a clean apply/rollback result requires pre == post rollback digest")
        if restored is not True:
            errors.append("a clean apply/rollback result must set rollback_restored_exact true")
        if status == "APPLIED_ROLLED_BACK_EXACT":
            if result.get("failure_reason") is not None:
                errors.append("APPLIED_ROLLED_BACK_EXACT result cannot carry a failure_reason")
            # no-op apply 攔截:applied 缺失或等於 pre → 未真正改變狀態,exact restoration 空洞(此檢查
            # 不適用 ROLLED_BACK_INTERRUPTED,其 applied==pre 合法)。
            applied = result.get("applied_digest")
            if applied is None or applied == result.get("pre_state_digest"):
                errors.append(
                    "APPLIED_ROLLED_BACK_EXACT result requires applied_digest present and "
                    "!= pre_state_digest (a no-op apply cannot prove exact restoration)"
                )
    else:
        if restored is not False:
            errors.append("a failed/not-restored result must set rollback_restored_exact false")
        if status == "NOT_RESTORED_FAILED" and exact:
            errors.append("NOT_RESTORED_FAILED result contradicts an exact restoration")
        if not isinstance(result.get("failure_reason"), str) or not result.get("failure_reason").strip():
            errors.append("a failed/not-restored result requires a non-empty failure_reason")
    if restored is True and not exact:
        errors.append("rollback_restored_exact true requires pre == post rollback digest")

    observation = result.get("observation") or {}
    witness = observation.get("runtime_witness") or {}
    if result.get("evidence_class") == "LOCAL_REPRODUCIBLE" and witness.get("kind") == "structural_contract":
        errors.append("LOCAL_REPRODUCIBLE result requires a real runtime witness (not structural_contract)")
    if _contains_secret_like(result):
        errors.append("component effect result carries secret-like content")

    try:
        started = _parse_time(str(result.get("started_at", "")))
        completed = _parse_time(str(result.get("completed_at", "")))
        evidence_expiry = _parse_time(str(result.get("evidence_expires_at", "")))
        if not started <= completed < evidence_expiry:
            errors.append("component effect result start/completion/expiry order is invalid")
        if evidence_expiry - completed > timedelta(minutes=15):
            errors.append("component effect result evidence TTL exceeds fifteen minutes")
        if now is not None and _parse_time(now) >= evidence_expiry:
            errors.append("component effect result evidence is stale at the central gate")
    except (TypeError, ValueError):
        errors.append("component effect result timestamps are invalid")
    if result.get("result_digest") != result_digest(result):
        errors.append("component effect result_digest does not match canonical result")
    return errors


# --------------------------------------------------------------------------- #
# independent distinct-actor postcheck attestation (applier != verifier crux)
# --------------------------------------------------------------------------- #
def build_postcheck_attestation(
    *,
    result: dict[str, Any],
    verifier_node: str,
    reobserved_post_rollback_digest: str,
    restoration_confirmed: bool,
    evidence_class: str,
    observed_at: str,
    ttl_seconds: int = 900,
) -> dict[str, Any]:
    """Build one canonical, self-hashed ``component_effect_postcheck_attestation_v1``.

    Machine-enforced crux: ``verifier_node`` MUST differ from the result's
    ``apply_actor_node`` (raise ``ApplierIsSoleVerifierError`` if equal).  The
    verifier INDEPENDENTLY re-derives ``reobserved_post_rollback_digest`` (it does
    not copy the applier's claim); ``restoration_confirmed`` is only true when that
    re-derived digest equals the result's post-rollback digest.
    ``remote_platform_attested`` is const false (the real remote attestation is
    S2.5/S1.6).
    """

    if not isinstance(result, dict):
        raise ComponentEffectError("attestation requires the applied result")
    apply_actor = result.get("apply_actor_node")
    if verifier_node == apply_actor:
        # 施加者不能是其唯一驗證者(§4 crux);相等即 fail-closed 拒絕。
        raise ApplierIsSoleVerifierError(
            "verifier_node must differ from apply_actor_node (applier is not sole verifier)"
        )
    if evidence_class not in EVIDENCE_CLASSES:
        raise ComponentEffectError(f"unrecognized evidence_class: {evidence_class!r}")
    if not DIGEST_RE.fullmatch(str(reobserved_post_rollback_digest)):
        raise ComponentEffectError("reobserved_post_rollback_digest must be a sha256 digest")
    # restoration_confirmed 必須恰等於「獨立重算的 post-rollback digest == result 的 post digest」:
    # 無法重算出完全一致 digest 的驗證者不得宣稱 confirmed;反之能重算一致卻不 confirm 亦不自洽。
    # 兩者不符即 fail-closed(擋掉 confirmed=True 卻餵入捏造 reobserved digest 的偽證)。
    rederived_matches = reobserved_post_rollback_digest == result.get("post_rollback_digest")
    if bool(restoration_confirmed) != rederived_matches:
        raise ComponentEffectError(
            "restoration_confirmed must equal (reobserved_post_rollback_digest == "
            "result.post_rollback_digest); a verifier that cannot re-derive the exact "
            "post-rollback digest cannot claim restoration_confirmed"
        )
    observed = _parse_time(observed_at)
    attestation: dict[str, Any] = {
        "schema_version": ATTESTATION_SCHEMA_VERSION,
        "result_digest": result.get("result_digest"),
        "intent_id": result.get("intent_id"),
        "intent_digest": result.get("intent_digest"),
        "effect_class": result.get("effect_class"),
        "adapter_id": result.get("adapter_id"),
        "apply_actor_node": apply_actor,
        "verifier_node": verifier_node,
        "reobserved_post_rollback_digest": reobserved_post_rollback_digest,
        "restoration_confirmed": bool(restoration_confirmed),
        "applier_is_not_sole_verifier": True,
        "remote_platform_attested": False,
        "evidence_class": evidence_class,
        "observed_at": observed.isoformat(),
        "expires_at": (observed + timedelta(seconds=ttl_seconds)).isoformat(),
    }
    _guard_no_secret(attestation)
    attestation["attestation_digest"] = attestation_digest(attestation)
    return attestation


def validate_postcheck_attestation(
    attestation: Any, *, result: dict[str, Any] | None = None, now: str | None = None
) -> list[str]:
    """Validate attestation structure/integrity + the applier!=verifier independence."""

    if not isinstance(attestation, dict):
        return ["component effect postcheck attestation must be an object"]
    schema = _schema(str(ATTESTATION_SCHEMA_PATH))
    errors = [
        f"component effect postcheck attestation schema violation: {error}"
        for error in schema_subset_errors(attestation, schema, schema)
    ]
    if errors:
        return errors

    if attestation.get("verifier_node") == attestation.get("apply_actor_node"):
        errors.append("component effect postcheck verifier_node must differ from apply_actor_node")
    if attestation.get("applier_is_not_sole_verifier") is not True:
        errors.append("component effect postcheck must assert applier_is_not_sole_verifier")
    if attestation.get("remote_platform_attested") is not False:
        errors.append("component effect postcheck remote_platform_attested must be false (S2.5/S1.6)")
    if attestation.get("effect_class") not in DEPLOY_COMPONENT_CLASSES:
        errors.append("component effect postcheck effect_class is not an S1.5 deploy class")
    if result is not None:
        if attestation.get("result_digest") != result.get("result_digest"):
            errors.append("component effect postcheck result_digest is not bound to the result")
        if attestation.get("apply_actor_node") != result.get("apply_actor_node"):
            errors.append("component effect postcheck apply_actor_node differs from the result")
        confirmed = attestation.get("restoration_confirmed") is True
        matches = attestation.get("reobserved_post_rollback_digest") == result.get("post_rollback_digest")
        if confirmed and not matches:
            errors.append("component effect postcheck confirms restoration but re-derived digest differs")
        if matches and not confirmed:
            errors.append("component effect postcheck re-derived the restoration digest yet did not confirm")
    try:
        observed = _parse_time(str(attestation.get("observed_at", "")))
        expires = _parse_time(str(attestation.get("expires_at", "")))
        if not observed < expires:
            errors.append("component effect postcheck observed_at must precede expires_at")
        if now is not None and _parse_time(now) >= expires:
            errors.append("component effect postcheck attestation is stale")
    except (TypeError, ValueError):
        errors.append("component effect postcheck timestamps are invalid")
    if attestation.get("attestation_digest") != attestation_digest(attestation):
        errors.append("component effect postcheck attestation_digest does not match canonical attestation")
    return errors


# --------------------------------------------------------------------------- #
# bypass-negatives (fail-closed; each REALLY triggers the rejection, no rubber stamp)
# --------------------------------------------------------------------------- #
def _honest_seed_intent(now: str) -> dict[str, Any]:
    # 供反例衍生的誠實 intent(ENGINE_SCANNER,disposable);pre_state_digest 為佔位 digest。
    return build_component_effect_intent(
        effect_class="ENGINE_SCANNER",
        target_class="disposable_local",
        pre_state_digest=canonical_digest({"seed": "pre_state"}),
        apply_actor_node="engine_scanner_deploy_actor",
        independent_postcheck_node="engine_scanner_ops_postcheck",
        approved_by="operator:s1.5",
        approved_at=now,
        ttl_seconds=600,
        intent_id="component-effect-seed-001",
    )


def _bypass_source_only_route_of_effectful_class() -> None:
    # NONE 類卻碰到 component 面 → S1.2 classifier 必 raise。
    central_validator.classify_component_required_effects(
        {
            "component_work_package_id": "AIML-bypass-source-only",
            "component_effect_class": "NONE",
            "declared_adapter_id": "none",
            "declared_intent_fields": ["irrelevant"],
            "owned_path_manifest": [],
            "direct_interfaces": ["engine_scanner_deploy_adapter_v1"],
        },
        classified_at="2026-07-22T10:00:00Z",
    )


def _bypass_generic_deploy_apply_enabled_without_per_class_contract() -> None:
    # 通用 deploy_adapter_v1 必仍 apply-disabled(不得替某 component class 施加 effect)。
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    status = registry.get("effect_adapters", {}).get(GENERIC_DEPLOY_ADAPTER_ID, {}).get("status")
    if status != GENERIC_DEPLOY_DISABLED_STATUS:
        raise ComponentEffectError(
            f"generic {GENERIC_DEPLOY_ADAPTER_ID} is not apply-disabled: {status!r}"
        )
    raise ComponentEffectError(
        "generic deploy apply stays disabled for a class without its per-class contract"
    )


def _bypass_apply_without_preflight(now: str) -> None:
    intent = build_component_effect_intent(
        effect_class="ENGINE_SCANNER", target_class="disposable_local",
        pre_state_digest=canonical_digest({"seed": "pre_state"}),
        apply_actor_node="engine_scanner_deploy_actor",
        independent_postcheck_node="engine_scanner_ops_postcheck",
        approved_by="operator:s1.5", approved_at=now, ttl_seconds=600,
        intent_id="component-effect-nopreflight-001", include_ops_preflight=False,
    )
    refuse_apply_without_contract(intent, now=now)


def _bypass_apply_without_approved_intent(now: str) -> None:
    intent = build_component_effect_intent(
        effect_class="ENGINE_SCANNER", target_class="disposable_local",
        pre_state_digest=canonical_digest({"seed": "pre_state"}),
        apply_actor_node="engine_scanner_deploy_actor",
        independent_postcheck_node="engine_scanner_ops_postcheck",
        approved_by="operator:s1.5", approved_at=now, ttl_seconds=600,
        intent_id="component-effect-noapproval-001", include_approval=False,
    )
    refuse_apply_without_contract(intent, now=now)


def _bypass_apply_without_rollback_binding(now: str) -> None:
    intent = build_component_effect_intent(
        effect_class="ENGINE_SCANNER", target_class="disposable_local",
        pre_state_digest=canonical_digest({"seed": "pre_state"}),
        apply_actor_node="engine_scanner_deploy_actor",
        independent_postcheck_node="engine_scanner_ops_postcheck",
        approved_by="operator:s1.5", approved_at=now, ttl_seconds=600,
        intent_id="component-effect-norollback-001", include_rollback_binding=False,
    )
    refuse_apply_without_contract(intent, now=now)


def _bypass_production_target(now: str) -> None:
    build_component_effect_intent(
        effect_class="ENGINE_SCANNER", target_class="production",
        pre_state_digest=canonical_digest({"seed": "pre_state"}),
        apply_actor_node="engine_scanner_deploy_actor",
        independent_postcheck_node="engine_scanner_ops_postcheck",
        approved_by="operator:s1.5", approved_at=now, ttl_seconds=600,
        intent_id="component-effect-prod-001",
    )


def _bypass_applier_is_sole_verifier(now: str) -> None:
    result = _synthetic_exact_result(now, apply_actor_node="engine_scanner_deploy_actor")
    build_postcheck_attestation(
        result=result, verifier_node="engine_scanner_deploy_actor",  # 同一 node → 拒
        reobserved_post_rollback_digest=result["post_rollback_digest"],
        restoration_confirmed=True, evidence_class="STRUCTURAL_ONLY", observed_at=now,
    )


def _bypass_rollback_not_exact(now: str) -> None:
    intent = _honest_seed_intent(now)
    build_component_effect_result(
        intent=intent, apply_status="APPLIED_ROLLED_BACK_EXACT",
        pre_state_digest=canonical_digest({"pre": "A"}),
        applied_digest=canonical_digest({"applied": "B"}),
        post_rollback_digest=canonical_digest({"post": "C"}),  # != pre → 拒
        apply_actor_node="engine_scanner_deploy_actor", applied_observed=True,
        observation_window_stable=True, runtime_witness_kind="structural_contract",
        observed_sqlstate=None, evidence_class="STRUCTURAL_ONLY",
        started_at=now, completed_at=now,
    )


def _bypass_cross_class_adapter_substitution() -> None:
    # 錯的 adapter_id 對某 class → S1.2 classifier 必 raise。
    central_validator.classify_component_required_effects(
        {
            "component_work_package_id": "AIML-bypass-adapter-sub",
            "component_effect_class": "RETENTION_APPLY",
            "declared_adapter_id": "engine_scanner_deploy_adapter_v1",  # 錯類 adapter
            "declared_intent_fields": required_intent_fields("RETENTION_APPLY"),
            "owned_path_manifest": [],
            "direct_interfaces": [],
        },
        classified_at="2026-07-22T10:00:00Z",
    )


def _bypass_classifier_or_matrix_digest_tamper(now: str) -> None:
    # matrix digest 被竄改的 rollup → validator 必拒。以合成 bypass 案例建參考 receipt,
    # 避免 tamper 反例與 _reference_receipt 互相遞迴。
    receipt = _reference_receipt(now, bypass_negatives=_synthetic_bypass_cases())
    tampered = copy.deepcopy(receipt)
    tampered["governance_wiring"]["component_effect_matrix_digest"] = "sha256:" + "0" * 64
    tampered["self_digest"] = receipt_digest(tampered)
    errors = validate_effect_seams_ready_receipt(tampered, now=now)
    matrix_errors = [error for error in errors if "matrix digest" in error]
    if not matrix_errors:
        # tamper 未被攔 → 非 fail-closed;正常返回,由 run_bypass_negative 標記 vacuous。
        return
    # tamper 被 validator 攔下 = REJECTED 訊號(raise 供 run_bypass_negative 記錄)。
    raise ComponentEffectError("tampered matrix digest rejected: " + "; ".join(matrix_errors))


def _bypass_plaintext_secret_ingress(now: str) -> None:
    intent = _honest_seed_intent(now)
    poisoned = copy.deepcopy(intent)
    poisoned["intent_fields"]["binary_digest"] = "password=plaintexthunter2example"
    _guard_no_secret(poisoned)  # 必 raise SecretLeakageError


def _bypass_apply_was_a_noop(now: str) -> None:
    # no-op apply:applied == pre == post,雖然 pre==post「看似」exact restoration,但 apply 從未
    # 改變狀態 → build_component_effect_result 必拒(否則 exact restoration 空洞可造假)。
    intent = _honest_seed_intent(now)
    pre = canonical_digest({"pre": "noop"})
    build_component_effect_result(
        intent=intent, apply_status="APPLIED_ROLLED_BACK_EXACT",
        pre_state_digest=pre, applied_digest=pre,  # applied == pre → no-op → 拒
        post_rollback_digest=pre,
        apply_actor_node="engine_scanner_deploy_actor", applied_observed=True,
        observation_window_stable=True, runtime_witness_kind="structural_contract",
        observed_sqlstate=None, evidence_class="STRUCTURAL_ONLY",
        started_at=now, completed_at=now,
    )


_BYPASS_RUNNERS: dict[str, Callable[[str], None]] = {
    "source_only_route_of_effectful_class": lambda now: _bypass_source_only_route_of_effectful_class(),
    "generic_deploy_apply_enabled_without_per_class_contract": lambda now: _bypass_generic_deploy_apply_enabled_without_per_class_contract(),
    "apply_without_preflight": _bypass_apply_without_preflight,
    "apply_without_approved_intent": _bypass_apply_without_approved_intent,
    "apply_without_rollback_binding": _bypass_apply_without_rollback_binding,
    "production_target": _bypass_production_target,
    "applier_is_sole_verifier": _bypass_applier_is_sole_verifier,
    "rollback_not_exact": _bypass_rollback_not_exact,
    "cross_class_adapter_substitution": lambda now: _bypass_cross_class_adapter_substitution(),
    "classifier_or_matrix_digest_tamper": _bypass_classifier_or_matrix_digest_tamper,
    "plaintext_secret_ingress": _bypass_plaintext_secret_ingress,
    "apply_was_a_noop": _bypass_apply_was_a_noop,
}


def run_bypass_negative(kind: str, *, now: str) -> dict[str, Any]:
    """Run one §11 bypass-negative; confirm it REALLY fails closed (no rubber stamp).

    Each runner exercises the exact rejection path.  If a runner does NOT raise the
    case is vacuous and this re-raises ``ComponentEffectError`` — the receipt must
    never record a bypass as ``REJECTED`` when the path did not actually reject.
    """

    runner = _BYPASS_RUNNERS.get(kind)
    if runner is None:
        raise ComponentEffectError(f"unknown bypass-negative kind: {kind!r}")
    try:
        runner(now)
    except (ComponentEffectError, ValueError) as error:
        return {
            "case_id": f"neg-{BYPASS_KINDS.index(kind) + 1:02d}-{kind}",
            "bypass_kind": kind,
            "expected": "FAIL_CLOSED",
            "observed_verdict": "REJECTED",
            "evidence_class": "STRUCTURAL_ONLY",
            "reason": str(error)[:200],
        }
    raise ComponentEffectError(
        f"bypass-negative {kind!r} did not fail closed (vacuous rejection)"
    )


def build_bypass_negative_cases(*, now: str) -> list[dict[str, Any]]:
    """Run all twelve §11 bypass-negatives and return their REJECTED case records."""

    return [run_bypass_negative(kind, now=now) for kind in BYPASS_KINDS]


def _synthetic_bypass_cases() -> list[dict[str, Any]]:
    """Pre-formed REJECTED case records (no runner) used only to break the reference
    receipt <-> tamper-bypass cycle; the REAL runs are ``build_bypass_negative_cases``."""

    return [
        {
            "case_id": f"neg-{index + 1:02d}-{kind}",
            "bypass_kind": kind,
            "expected": "FAIL_CLOSED",
            "observed_verdict": "REJECTED",
            "evidence_class": "STRUCTURAL_ONLY",
        }
        for index, kind in enumerate(BYPASS_KINDS)
    ]


# --------------------------------------------------------------------------- #
# rollup receipt builder + validator
# --------------------------------------------------------------------------- #
def build_admitted_class_entry(
    *, result: dict[str, Any], attestation: dict[str, Any]
) -> dict[str, Any]:
    """Project one class's REAL result + independent postcheck into a rollup entry.

    綁定真實 evidence(非僅呼叫者投影的 digest):除複核 crux 不變量(pre==post 恰好還原、
    applied != pre、applier != verifier、restoration_confirmed 綁定 reobserved==post)外,另
    重算兩者的 canonical digest 必須等於物件自綁值,並跑完整 ``validate_component_effect_result``
    / ``validate_postcheck_attestation`` 必須零錯。合成投影 / digest-alone(無真實
    apply/rollback/postcheck 的 result/attestation 物件)於此 build 時即 fail-closed 被拒 ——
    rollup entry 無法憑 digest 或手工投影湊出。
    """

    if not isinstance(result, dict) or not isinstance(attestation, dict):
        raise ComponentEffectError(
            "rollup entry requires the real component_effect_result_v1 and postcheck "
            "attestation objects (a synthetic / digests-alone projection is rejected)"
        )
    if result.get("apply_status") != "APPLIED_ROLLED_BACK_EXACT":
        raise ComponentEffectError("rollup admits only APPLIED_ROLLED_BACK_EXACT results")
    if result.get("rollback_restored_exact") is not True:
        raise NonExactRollbackError("rollup admits only exactly-restored results")
    if result.get("pre_state_digest") != result.get("post_rollback_digest"):
        raise NonExactRollbackError("rollup entry requires pre == post rollback digest")
    # no-op apply 攔截(防禦縱深):applied 缺失或等於 pre 代表 apply 從未真正改變 active 狀態,
    # 「exact restoration」形同空洞(applied==pre==post 也能偽證乾淨回滾)。誠實管線已於 result
    # builder 擋掉,此處在 rollup entry builder 再核一次,擋住手工偽造的 no-op EXACT result
    # (S2.4 消費的 rollup 路徑平價再核,對齊上方 pre==post、下方 reobserved 的 re-check)。
    applied = result.get("applied_digest")
    if applied is None or applied == result.get("pre_state_digest"):
        raise NonExactRollbackError(
            "rollup entry requires the apply to change state "
            "(applied_digest must be present and differ from pre_state_digest)"
        )
    if attestation.get("apply_actor_node") == attestation.get("verifier_node"):
        raise ApplierIsSoleVerifierError("rollup entry requires a distinct verifier")
    if attestation.get("result_digest") != result.get("result_digest"):
        raise ComponentEffectError("rollup attestation is not bound to the result")
    # 獨立 postcheck 必須 load-bearing:唯有 verifier 真的 confirm 且重算 digest 與 result 的
    # post digest 完全一致,rollup 才收該類(否則「獨立驗證」淪為裝飾)。reobserved digest 隨 entry
    # 帶入,供 rollup validator 於消費端(非僅 builder)再核。
    if attestation.get("restoration_confirmed") is not True:
        raise ComponentEffectError("rollup admits only confirmed-restoration attestations")
    reobserved = attestation.get("reobserved_post_rollback_digest")
    if reobserved != result.get("post_rollback_digest"):
        raise NonExactRollbackError(
            "rollup entry requires the independent verifier's reobserved digest to equal post_rollback_digest"
        )
    # 綁定真實 evidence(收尾防線):entry 綁入的 result_digest / attestation_digest 必須等於由物件
    # 重算的 canonical digest(擋捏造 digest 的合成投影),且兩物件必須各自通過完整 validator
    # (schema / integrity / crux 全數重跑)。任一不符即 fail-closed —— rollup entry 只能由真正建構
    # 並驗證過的 result+attestation 產生,無法從 digest-alone / 手工投影湊出。
    if result.get("result_digest") != result_digest(result):
        raise ComponentEffectError(
            "rollup entry result_digest is not the canonical digest of the result object "
            "(a synthetic / digests-alone projection cannot be admitted)"
        )
    if attestation.get("attestation_digest") != attestation_digest(attestation):
        raise ComponentEffectError(
            "rollup entry attestation_digest is not the canonical digest of the attestation "
            "object (a synthetic / digests-alone projection cannot be admitted)"
        )
    result_errors = validate_component_effect_result(result)
    if result_errors:
        raise ComponentEffectError(
            "rollup entry requires a valid component_effect_result_v1: " + "; ".join(result_errors)
        )
    attestation_errors = validate_postcheck_attestation(attestation, result=result)
    if attestation_errors:
        raise ComponentEffectError(
            "rollup entry requires a valid postcheck attestation: " + "; ".join(attestation_errors)
        )
    return {
        "effect_class": result["effect_class"],
        "adapter_id": result["adapter_id"],
        "disposable_target_kind": result["disposable_target_kind"],
        "intent_digest": result["intent_digest"],
        "pre_state_digest": result["pre_state_digest"],
        "result_digest": result["result_digest"],
        "post_rollback_digest": result["post_rollback_digest"],
        "reobserved_post_rollback_digest": reobserved,
        "rollback_restored_exact": True,
        "apply_actor_node": result["apply_actor_node"],
        "postcheck_attestation_digest": attestation["attestation_digest"],
        "postcheck_verifier_node": attestation["verifier_node"],
        "applier_is_not_sole_verifier": True,
        "evidence_class": result["evidence_class"],
        "production_apply_performed": False,
    }


def build_effect_seams_ready_receipt(
    *,
    caller: str,
    class_evidence: list[dict[str, Any]],
    bypass_negatives: list[dict[str, Any]],
    dependency_receipts: dict[str, Any],
    observation_time: str,
    ttl_seconds: int,
) -> dict[str, Any]:
    """Build the canonical, self-hashed ``effect_seams_ready_receipt_v1`` rollup.

    ``class_evidence`` is a list of ``{"result": <component_effect_result_v1>,
    "attestation": <component_effect_postcheck_attestation_v1>}`` REAL object pairs;
    every admitted-class entry is produced (and validated) by
    ``build_admitted_class_entry`` here — a caller cannot hand in a pre-built entry
    or a digests-alone projection, so the "six valid-looking entries -> PASS"
    forgery path is closed at build.  Unsafe states raise (never emit): a production
    target, a non-exact rollback, an applier==verifier, a ``production_apply_performed``
    claim, a missing bypass kind, ttl out of range, or a secret in any serialized
    payload.  ``status=PASS`` only when all six classes are present + exactly restored
    + distinct-verified, every §11 bypass kind is REJECTED, and every boundary flag holds.
    """

    if not isinstance(caller, str) or not caller:
        raise ComponentEffectError("caller is required")
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or not (1 <= ttl_seconds <= TTL_CEILING_SECONDS):
        raise ComponentEffectError(f"ttl_seconds must be within [1, {TTL_CEILING_SECONDS}]")

    # 每個 admitted class 一律由真實 result+attestation 物件經 build_admitted_class_entry 產生並
    # 驗證(重算 digest + 完整 validator + crux 複核);呼叫者不得直接遞入手工 entry / digest-alone
    # 投影。這關閉「六個看似合法的 entry → PASS receipt」的偽造路徑。
    if not isinstance(class_evidence, list):
        raise ComponentEffectError("class_evidence must be a list of {result, attestation} pairs")
    admitted_classes: list[dict[str, Any]] = []
    for evidence in class_evidence:
        if (
            not isinstance(evidence, dict)
            or "result" not in evidence
            or "attestation" not in evidence
        ):
            raise ComponentEffectError(
                "each class_evidence item must be a {result, attestation} object pair"
            )
        admitted_classes.append(
            build_admitted_class_entry(
                result=evidence["result"], attestation=evidence["attestation"]
            )
        )

    seen_classes: list[str] = []
    for entry in admitted_classes:
        if entry.get("production_apply_performed") is not False:
            raise ComponentEffectError("an admitted class claims production_apply_performed")
        if entry.get("rollback_restored_exact") is not True or (
            entry.get("pre_state_digest") != entry.get("post_rollback_digest")
        ):
            raise NonExactRollbackError("an admitted class is not exactly restored")
        if entry.get("reobserved_post_rollback_digest") != entry.get("post_rollback_digest"):
            raise NonExactRollbackError(
                "an admitted class independent postcheck did not re-derive the exact post digest"
            )
        if entry.get("apply_actor_node") == entry.get("postcheck_verifier_node"):
            raise ApplierIsSoleVerifierError("an admitted class has applier == verifier")
        seen_classes.append(entry.get("effect_class"))
    missing_classes = set(DEPLOY_COMPONENT_CLASSES) - set(seen_classes)
    present_bypass = {case.get("bypass_kind") for case in bypass_negatives}
    missing_bypass = BYPASS_KIND_SET - present_bypass
    non_rejected = [case for case in bypass_negatives if case.get("observed_verdict") != "REJECTED"]
    if non_rejected:
        raise ComponentEffectError("a bypass-negative did not fail closed")

    reasons: list[str] = []
    if missing_classes:
        reasons.append(f"missing admitted deploy classes: {sorted(missing_classes)}")
    if len(seen_classes) != len(set(seen_classes)):
        reasons.append("duplicate admitted deploy classes")
    if missing_bypass:
        reasons.append(f"missing bypass-negative kinds: {sorted(missing_bypass)}")

    status = "PASS" if not reasons else "FAIL"
    failure_reason = None if status == "PASS" else "; ".join(reasons)
    observed = _parse_time(observation_time)

    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "harness_id": HARNESS_ID,
        "status": status,
        "caller": caller,
        "target_class": S1_TARGET_CLASS,
        "governance_wiring": {
            "component_effect_matrix_digest": component_effect_matrix_digest(),
            "registered_adapter_ids": sorted(adapter_id_for(cls) for cls in DEPLOY_COMPONENT_CLASSES),
            "schema_files_registered": [
                INTENT_SCHEMA_VERSION, RESULT_SCHEMA_VERSION,
                ATTESTATION_SCHEMA_VERSION, RECEIPT_SCHEMA_VERSION,
            ],
            "central_validator_recognizes": True,
            "generated_views_unchanged": True,
        },
        "admitted_classes": admitted_classes,
        "observation_seam": {
            "seam_kind": "independent_distinct_actor_postcheck",
            "remote_platform_attested": False,
            "attestation_schema": ATTESTATION_SCHEMA_VERSION,
            "deferred_to": "S2.5_running_attestation_and_S1.6_target_host_probe",
        },
        "bypass_negatives": [
            {
                "case_id": case["case_id"],
                "bypass_kind": case["bypass_kind"],
                "expected": "FAIL_CLOSED",
                "observed_verdict": "REJECTED",
                "evidence_class": case.get("evidence_class", "STRUCTURAL_ONLY"),
            }
            for case in bypass_negatives
        ],
        "dependency_receipts": dependency_receipts,
        "boundary": {
            "production_apply_performed": False,
            "real_service_restart": False,
            "real_remote_host_mutation": False,
            "real_migration_applied": False,
            "nine_authorities_false": True,
        },
        "sprint_gate_scope": SPRINT_GATE_SCOPE,
        "source_sha256": source_sha256(),
        "schema_sha256": schema_sha256(str(RECEIPT_SCHEMA_PATH)),
        "secret_scan": {
            "patterns_checked": list(SECRET_PATTERNS_CHECKED),
            "leaked": False,
        },
        "observation_time": observed.isoformat(),
        "expires_at": (observed + timedelta(seconds=ttl_seconds)).isoformat(),
        "ttl_seconds": ttl_seconds,
        "failure_reason": failure_reason,
    }
    # 計算 self_digest 前掃描整份 receipt(排除 secret_scan 自身)。
    _guard_no_secret({k: v for k, v in receipt.items() if k != "secret_scan"})
    receipt["self_digest"] = receipt_digest(receipt)
    return receipt


def validate_effect_seams_ready_receipt(receipt: Any, *, now: str | None = None) -> list[str]:
    """Validate the rollup receipt structure/integrity + every PASS-critical crux.

    STRUCTURE-ONLY(刻意):本 validator 只核對 receipt 位元的結構 / 完整性 / 自綁 digest 與各
    PASS-critical 交叉欄位(pre==post、reobserved==post、applier!=verifier、bypass 齊全)。它
    不持有(也無法重驗)每類底層的 ``component_effect_result_v1`` /
    ``component_effect_postcheck_attestation_v1`` 物件 —— 那些真實物件只在 build 時存在。因此一份
    合法的 rollup 只能經 ``build_effect_seams_ready_receipt`` 以「已綁定且驗證過的真實 result+
    attestation evidence」產生;一份手工撰寫的 rollup 即使結構 / digest 自洽,也不代表底層
    apply/rollback/postcheck 真的發生過。消費者(S2.4/S2.5)不得僅憑本結構檢查即信任一份 rollup
    的 digest,必須重跑 builder 或取得可信主機 attestation(見模組 docstring 的
    evidence-authenticity 誠實聲明)。
    """

    if not isinstance(receipt, dict):
        return ["effect seams ready receipt must be an object"]
    schema = _schema(str(RECEIPT_SCHEMA_PATH))
    errors = [
        f"effect seams ready receipt schema violation: {error}"
        for error in schema_subset_errors(receipt, schema, schema)
    ]
    if set(receipt) != RECEIPT_FIELDS:
        errors.append(
            "effect seams ready receipt fields mismatch: "
            f"missing={sorted(RECEIPT_FIELDS - set(receipt))} "
            f"extra={sorted(set(receipt) - RECEIPT_FIELDS)}"
        )
    if errors:
        return errors

    if receipt.get("harness_id") != HARNESS_ID:
        errors.append("effect seams ready receipt harness_id is invalid")
    if receipt.get("sprint_gate_scope") != SPRINT_GATE_SCOPE:
        errors.append("effect seams ready receipt sprint_gate_scope must be S1.5_CONTRIBUTION")
    if receipt.get("target_class") != S1_TARGET_CLASS:
        errors.append("effect seams ready receipt target_class must be disposable_local")
    for field_name in ("source_sha256", "schema_sha256", "self_digest"):
        if not DIGEST_RE.fullmatch(str(receipt.get(field_name, ""))):
            errors.append(f"effect seams ready receipt {field_name} is invalid")
    if receipt.get("source_sha256") != source_sha256():
        errors.append("effect seams ready receipt source_sha256 does not bind this module")
    if receipt.get("schema_sha256") != schema_sha256(str(RECEIPT_SCHEMA_PATH)):
        errors.append("effect seams ready receipt schema_sha256 does not bind the schema")

    wiring = receipt.get("governance_wiring") or {}
    if wiring.get("component_effect_matrix_digest") != component_effect_matrix_digest():
        errors.append("effect seams ready receipt component effect matrix digest is not admitted")
    if set(wiring.get("registered_adapter_ids", [])) != {
        adapter_id_for(cls) for cls in DEPLOY_COMPONENT_CLASSES
    }:
        errors.append("effect seams ready receipt registered_adapter_ids are not the six matrix adapters")
    if set(wiring.get("schema_files_registered", [])) != {
        INTENT_SCHEMA_VERSION, RESULT_SCHEMA_VERSION,
        ATTESTATION_SCHEMA_VERSION, RECEIPT_SCHEMA_VERSION,
    }:
        errors.append("effect seams ready receipt schema_files_registered are not the four schemas")

    admitted = receipt.get("admitted_classes") or []
    seen: list[str] = []
    for entry in admitted:
        effect_class = entry.get("effect_class")
        seen.append(effect_class)
        if effect_class in DEPLOY_COMPONENT_CLASSES:
            if entry.get("adapter_id") != adapter_id_for(effect_class):
                errors.append(f"admitted class {effect_class} adapter_id is not the matrix adapter")
            if entry.get("disposable_target_kind") != disposable_target_kind_for(effect_class):
                errors.append(f"admitted class {effect_class} disposable_target_kind is wrong")
        if entry.get("pre_state_digest") != entry.get("post_rollback_digest"):
            errors.append(f"admitted class {effect_class} is not exactly restored (pre != post)")
        if entry.get("reobserved_post_rollback_digest") != entry.get("post_rollback_digest"):
            # 消費端(非僅 builder)再核獨立驗證者確實重算出一致 post digest。
            errors.append(
                f"admitted class {effect_class} independent postcheck did not re-derive the exact post digest"
            )
        if entry.get("apply_actor_node") == entry.get("postcheck_verifier_node"):
            errors.append(f"admitted class {effect_class} applier equals its verifier")
    missing = set(DEPLOY_COMPONENT_CLASSES) - set(seen)
    if missing:
        errors.append(f"effect seams ready receipt is missing deploy classes: {sorted(missing)}")
    if len(seen) != len(set(seen)):
        errors.append("effect seams ready receipt has duplicate admitted classes")

    present_bypass = {case.get("bypass_kind") for case in receipt.get("bypass_negatives", [])}
    missing_bypass = BYPASS_KIND_SET - present_bypass
    if missing_bypass:
        errors.append(f"effect seams ready receipt is missing bypass kinds: {sorted(missing_bypass)}")
    if any(case.get("observed_verdict") != "REJECTED" for case in receipt.get("bypass_negatives", [])):
        errors.append("effect seams ready receipt has a bypass-negative that did not fail closed")

    dependency = receipt.get("dependency_receipts") or {}
    if dependency.get("component_effect_matrix_digest") != component_effect_matrix_digest():
        errors.append("effect seams ready receipt dependency matrix digest is not admitted")
    if receipt.get("secret_scan", {}).get("leaked") is not False:
        errors.append("effect seams ready receipt secret_scan.leaked must be false")
    if _contains_secret_like({k: v for k, v in receipt.items() if k != "secret_scan"}):
        errors.append("effect seams ready receipt carries secret-like content")

    status = receipt.get("status")
    failure_reason = receipt.get("failure_reason")
    if status == "PASS":
        if failure_reason is not None:
            errors.append("PASS effect seams ready receipt cannot carry a failure_reason")
        if missing or missing_bypass:
            errors.append("PASS effect seams ready receipt requires all six classes and all bypass kinds")
    elif status == "FAIL":
        if not isinstance(failure_reason, str) or not failure_reason.strip():
            errors.append("FAIL effect seams ready receipt requires a non-empty failure_reason")
    else:
        errors.append("effect seams ready receipt status is invalid")

    try:
        observed = _parse_time(str(receipt.get("observation_time", "")))
        expires = _parse_time(str(receipt.get("expires_at", "")))
        if not observed < expires:
            errors.append("effect seams ready receipt observation_time must precede expires_at")
        if now is not None and _parse_time(now) >= expires:
            errors.append("effect seams ready receipt is stale")
    except (TypeError, ValueError):
        errors.append("effect seams ready receipt timestamps are invalid")
    if receipt.get("self_digest") != receipt_digest(receipt):
        errors.append("effect seams ready receipt self_digest does not match canonical receipt")
    return errors


# --------------------------------------------------------------------------- #
# reference / synthetic helpers (hermetic; drive bypass-negatives + structural tests)
# --------------------------------------------------------------------------- #
def _synthetic_exact_result(now: str, *, apply_actor_node: str) -> dict[str, Any]:
    intent = _honest_seed_intent(now)
    pre = canonical_digest({"synthetic": "pre_state"})
    return build_component_effect_result(
        intent=intent, apply_status="APPLIED_ROLLED_BACK_EXACT",
        pre_state_digest=pre, applied_digest=canonical_digest({"synthetic": "applied"}),
        post_rollback_digest=pre, apply_actor_node=apply_actor_node,
        applied_observed=True, observation_window_stable=True,
        runtime_witness_kind="structural_contract", observed_sqlstate=None,
        evidence_class="STRUCTURAL_ONLY", started_at=now, completed_at=now,
    )


def _reference_dependency_receipts() -> dict[str, Any]:
    return {
        "pg_readonly_identity_receipt_digest": canonical_digest({"s1_1": "pg_readonly_identity"}),
        "component_effect_matrix_digest": component_effect_matrix_digest(),
        "worm_sink_status": WORM_SINK_STATUS,
        "identity_acl_contract_receipt_digest": canonical_digest({"s1_3": "identity_acl_contract"}),
        "runtime_candidate_receipt_a_digest": canonical_digest({"s1_4": "runtime_candidate_a"}),
        "runtime_candidate_receipt_b_digest": canonical_digest({"s1_4": "runtime_candidate_b"}),
    }


def _reference_receipt(
    now: str, *, bypass_negatives: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Build a hermetic, structurally-complete PASS rollup for the six classes.

    Uses synthetic structural results (a distinct verifier per class); the
    disposable ``LOCAL_REPRODUCIBLE`` proofs live in the companion tests.  When
    ``bypass_negatives`` is None the real §11 runs are executed; the tamper
    bypass passes synthetic cases to avoid a build<->tamper recursion.
    """

    class_evidence: list[dict[str, Any]] = []
    for effect_class in DEPLOY_COMPONENT_CLASSES:
        pre = canonical_digest({"reference_pre": effect_class})
        intent = build_component_effect_intent(
            effect_class=effect_class, target_class="disposable_local",
            pre_state_digest=pre, apply_actor_node=f"{effect_class.lower()}_apply_actor",
            independent_postcheck_node=f"{effect_class.lower()}_ops_postcheck",
            approved_by="operator:s1.5", approved_at=now, ttl_seconds=600,
            intent_id=f"component-effect-ref-{effect_class.lower()}",
        )
        result = build_component_effect_result(
            intent=intent, apply_status="APPLIED_ROLLED_BACK_EXACT",
            pre_state_digest=pre, applied_digest=canonical_digest({"applied": effect_class}),
            post_rollback_digest=pre, apply_actor_node=f"{effect_class.lower()}_apply_actor",
            applied_observed=True, observation_window_stable=True,
            runtime_witness_kind="structural_contract", observed_sqlstate=None,
            evidence_class="STRUCTURAL_ONLY", started_at=now, completed_at=now,
        )
        attestation = build_postcheck_attestation(
            result=result, verifier_node=f"{effect_class.lower()}_independent_verifier",
            reobserved_post_rollback_digest=pre, restoration_confirmed=True,
            evidence_class="STRUCTURAL_ONLY", observed_at=now,
        )
        class_evidence.append({"result": result, "attestation": attestation})
    bypass = bypass_negatives if bypass_negatives is not None else build_bypass_negative_cases(now=now)
    return build_effect_seams_ready_receipt(
        caller="component_effect_seams_harness_v1:reference",
        class_evidence=class_evidence, bypass_negatives=bypass,
        dependency_receipts=_reference_dependency_receipts(),
        observation_time=now, ttl_seconds=900,
    )
