#!/usr/bin/env python3
"""S2.5 disposable recovery 的 local-only recovery-anchor protocol。

Reader、writer、verifier 與 clock 是 injected behavior，不是 trusted identity。
公開 API 不接受 path/key/identity/sequence/head/nonce；沒有 durable monotonic floor
與 independently authenticated fixed trust 時，只能產生 ``LOCAL_REPRODUCIBLE`` /
``UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED``，不得升格為外部平台 attestation。
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
for _candidate in (Path(__file__).resolve().parent, ML_TRAINING_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import aiml_gate_receipt_validator as central_validator  # noqa: E402
import agent_governance_s2_5_recovery_store as recovery_store  # noqa: E402
from agent_governance_schema import schema_subset_errors  # noqa: E402
from agent_governance_s2_5_disposable_profile import (  # noqa: E402
    ANCHOR_COLLECTION_ID,
    ANCHOR_READER_CGROUP,
    ANCHOR_READER_ROLE,
    ANCHOR_READER_UNIT,
    ANCHOR_STORE_ID,
    ANCHOR_VERIFIER_CGROUP,
    ANCHOR_VERIFIER_ROLE,
    ANCHOR_VERIFIER_UNIT,
    ANCHOR_WRITER_CGROUP,
    ANCHOR_WRITER_ROLE,
    ANCHOR_WRITER_UNIT,
    PROFILE_EVIDENCE_CLASS,
    PROFILE_ID,
    PROFILE_TARGET_CLASS,
    SIDE_EFFECT_CLASS,
    STATUS_UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED,
)


_SCHEMA_DIR = REPO_ROOT / ".codex" / "schemas"
_LOCAL_SCHEMAS = frozenset({
    "s2_5_recovery_anchor_entry_v2",
    "s2_5_recovery_anchor_latest_v1",
    "s2_5_recovery_anchor_page_v1",
    "s2_5_recovery_anchor_prepared_append_v1",
    "s2_5_recovery_anchor_append_intent_v1",
    "s2_5_recovery_anchor_append_result_v1",
    "s2_5_recovery_anchor_readback_v1",
    "s2_5_recovery_anchor_postcheck_v1",
    "s2_5_recovery_anchor_rollback_v1",
})
_READ_SCHEMAS = frozenset({
    "s2_5_recovery_anchor_entry_v2",
    "s2_5_recovery_anchor_latest_v1",
    "s2_5_recovery_anchor_page_v1",
})
_COMMON = {
    "evidence_class": PROFILE_EVIDENCE_CLASS,
    "side_effect_class": SIDE_EFFECT_CLASS,
    "target_class": PROFILE_TARGET_CLASS,
    "target_profile_id": PROFILE_ID,
    "production_effect": False,
    "production_authority": False,
    "production_effect_count": 0,
}
_IDENTITY_PROFILE = {
    "writer": {
        "role": ANCHOR_WRITER_ROLE,
        "unit": ANCHOR_WRITER_UNIT,
        "cgroup": ANCHOR_WRITER_CGROUP,
        "key_fingerprint": None,
    },
    "reader": {
        "role": ANCHOR_READER_ROLE,
        "unit": ANCHOR_READER_UNIT,
        "cgroup": ANCHOR_READER_CGROUP,
        "key_fingerprint": None,
    },
    "verifier": {
        "role": ANCHOR_VERIFIER_ROLE,
        "unit": ANCHOR_VERIFIER_UNIT,
        "cgroup": ANCHOR_VERIFIER_CGROUP,
        "key_fingerprint": None,
    },
}


class RecoveryAnchorError(RuntimeError):
    """Fail-closed protocol error with a stable non-secret code."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


def _canonical_digest(value: dict[str, Any]) -> str:
    return central_validator.canonical_digest(value)


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _seal(value: dict[str, Any]) -> dict[str, Any]:
    sealed = dict(value)
    sealed["self_digest"] = central_validator.artifact_self_digest(sealed)
    return sealed


def derive_anchor_head(entry: dict[str, Any]) -> str:
    """Derive the immutable chain head from the full sealed entry."""

    return _canonical_digest({
        "schema_version": "s2_5_recovery_anchor_head_v1",
        "sequence": entry.get("sequence"),
        "previous_anchor_digest": entry.get("previous_anchor_digest"),
        "entry_digest": entry.get("self_digest"),
    })


def _local_schema(schema_version: str) -> dict[str, Any]:
    if schema_version not in _LOCAL_SCHEMAS:
        raise RecoveryAnchorError("anchor_schema_version_unknown")
    path = _SCHEMA_DIR / f"{schema_version}.schema.json"
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RecoveryAnchorError(
            "anchor_schema_unreadable", type(error).__name__
        ) from error
    if not isinstance(schema, dict):
        raise RecoveryAnchorError("anchor_schema_not_an_object")
    return schema


def validate_local_artifact(artifact: Any) -> list[str]:
    """Validate an anchor-local artifact without central schema registration."""

    if not isinstance(artifact, dict):
        return ["anchor artifact must be an object"]
    schema_version = artifact.get("schema_version")
    if schema_version not in _LOCAL_SCHEMAS:
        return ["anchor schema_version is unknown"]
    try:
        schema = _local_schema(str(schema_version))
    except RecoveryAnchorError as error:
        return [error.code]
    errors = schema_subset_errors(artifact, schema, schema)
    if artifact.get("self_digest") != central_validator.artifact_self_digest(artifact):
        errors.append("anchor self_digest does not re-derive")
    for key, expected in _COMMON.items():
        if artifact.get(key) != expected:
            errors.append(f"anchor {key} differs from the fixed local profile")
    if schema_version == "s2_5_recovery_anchor_entry_v2":
        errors.extend(_entry_semantic_errors(artifact))
    elif schema_version == "s2_5_recovery_anchor_latest_v1":
        errors.extend(_latest_semantic_errors(artifact))
    elif schema_version == "s2_5_recovery_anchor_page_v1":
        errors.extend(_page_semantic_errors(artifact))
    elif schema_version == "s2_5_recovery_anchor_prepared_append_v1":
        errors.extend(_prepared_semantic_errors(artifact))
    elif schema_version == "s2_5_recovery_anchor_append_intent_v1":
        errors.extend(_append_intent_semantic_errors(artifact))
    elif schema_version == "s2_5_recovery_anchor_append_result_v1":
        errors.extend(_append_result_semantic_errors(artifact))
    elif schema_version == "s2_5_recovery_anchor_readback_v1":
        errors.extend(_readback_semantic_errors(artifact))
    elif schema_version == "s2_5_recovery_anchor_postcheck_v1":
        errors.extend(_postcheck_semantic_errors(artifact))
    elif schema_version == "s2_5_recovery_anchor_rollback_v1":
        errors.extend(_rollback_semantic_errors(artifact))
    return errors


def _integer(value: Any, *, minimum: int = 0) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _entry_semantic_errors(entry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    sequence = entry.get("sequence")
    previous = entry.get("previous_anchor_digest")
    if _integer(sequence, minimum=1):
        if sequence == 1 and previous is not None:
            errors.append("anchor genesis must have a null predecessor")
        if sequence > 1 and previous is None:
            errors.append("anchor non-genesis entry must bind its predecessor")
    status = entry.get("entry_status")
    unresolved = entry.get("unresolved_state_digest")
    authorization = entry.get("authorization_id")
    if status == "RESOLVED":
        if unresolved is not None:
            errors.append("resolved anchor entry must clear unresolved state")
        if authorization is None:
            errors.append("resolved anchor entry must bind consumed authorization")
    elif unresolved is None:
        errors.append("non-resolved anchor entry must retain unresolved state")
    return errors


def _latest_semantic_errors(latest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    sequence = latest.get("sequence")
    count = latest.get("entry_count")
    pages = latest.get("page_count")
    page_size = latest.get("page_size")
    head_fields = (
        latest.get("head_digest"),
        latest.get("head_object_id"),
        latest.get("head_version_id"),
    )
    if _integer(sequence) and _integer(count) and sequence != count:
        errors.append("latest sequence and entry_count differ")
    if _integer(count) and _integer(page_size, minimum=1) and _integer(pages):
        expected_pages = (count + page_size - 1) // page_size
        if pages != expected_pages:
            errors.append("latest page_count does not match entry_count/page_size")
    if sequence == 0:
        if head_fields != (None, None, None) or pages != 0:
            errors.append("empty latest must have null head and zero pages")
    elif _integer(sequence, minimum=1):
        if any(value is None for value in head_fields):
            errors.append("non-empty latest must bind exact head object version")
        if not _integer(pages, minimum=1):
            errors.append("non-empty latest must declare at least one page")
    return errors


def _page_semantic_errors(page: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    index = page.get("page_index")
    count = page.get("page_count")
    cursor_in = page.get("cursor_in")
    cursor_out = page.get("cursor_out")
    if index == 0 and cursor_in is not None:
        errors.append("first anchor page must have null cursor_in")
    if _integer(index) and _integer(count, minimum=1):
        if index >= count:
            errors.append("anchor page index lies outside page_count")
        if index + 1 == count and cursor_out is not None:
            errors.append("last anchor page must terminate")
        if index + 1 < count and cursor_out is None:
            errors.append("non-terminal anchor page cannot terminate early")
    return errors


def _prepared_semantic_errors(prepared: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    raw = prepared.get("prepared_payload_json")
    if not isinstance(raw, str):
        return ["prepared packet payload is not canonical JSON text"]
    try:
        payload = json.loads(raw)
    except ValueError:
        return ["prepared packet payload is not valid JSON"]
    if not isinstance(payload, dict) or _canonical_json(payload) != raw:
        return ["prepared packet payload is not canonical JSON"]
    if prepared.get("prepared_payload_digest") != _canonical_digest(payload):
        errors.append("prepared packet payload digest does not re-derive")
    if set(payload) != {
        "schema_version", "binding", "baseline_latest_digest",
        "entry", "intent", "request",
    }:
        errors.append("prepared payload fields are not closed")
        return errors
    if payload.get("schema_version") != "s2_5_recovery_anchor_prepared_payload_v1":
        errors.append("prepared payload schema_version is invalid")
    binding = payload.get("binding")
    if not isinstance(binding, dict) or set(binding) != {
        "store_id", "state_root_id", "source_head", "manifest_digest",
    }:
        errors.append("prepared payload binding is not closed")
        return errors
    for key in ("store_id", "state_root_id", "source_head", "manifest_digest"):
        if prepared.get(key) != binding.get(key):
            errors.append(f"prepared packet {key} differs from payload binding")
    if prepared.get("baseline_latest_digest") != payload.get(
        "baseline_latest_digest"
    ):
        errors.append("prepared packet baseline latest digest differs")
    entry = payload.get("entry")
    intent = payload.get("intent")
    request = payload.get("request")
    if validate_local_artifact(entry):
        errors.append("prepared packet entry is invalid")
    if validate_local_artifact(intent):
        errors.append("prepared packet intent is invalid")
    if not isinstance(request, dict) or set(request) != {
        "schema_version", "anchor_store_id", "anchor_collection_id",
        "expected_snapshot_id", "expected_latest_version_id",
        "expected_sequence", "expected_head_digest", "idempotency_key", "entry",
    }:
        errors.append("prepared packet request is not closed")
        return errors
    if request.get("schema_version") != (
        "s2_5_recovery_anchor_compare_append_request_v1"
    ):
        errors.append("prepared packet request schema_version is invalid")
    if (
        request.get("anchor_store_id") != ANCHOR_STORE_ID
        or request.get("anchor_collection_id") != ANCHOR_COLLECTION_ID
    ):
        errors.append("prepared packet request anchor identity is invalid")
    if request.get("entry") != entry:
        errors.append("prepared packet request entry differs")
    if isinstance(intent, dict):
        request_binding = {
            "expected_snapshot_id": intent.get("expected_snapshot_id"),
            "expected_latest_version_id": intent.get("expected_latest_version_id"),
            "expected_sequence": intent.get("expected_sequence"),
            "expected_head_digest": intent.get("expected_head_digest"),
            "idempotency_key": intent.get("idempotency_key"),
        }
        if any(request.get(key) != value for key, value in request_binding.items()):
            errors.append("prepared packet request differs from intent")
        if isinstance(entry, dict) and intent.get("entry_digest") != entry.get(
            "self_digest"
        ):
            errors.append("prepared packet intent differs from entry")
    for artifact_name, artifact in (("entry", entry), ("intent", intent)):
        if not isinstance(artifact, dict):
            continue
        expected_binding = {
            "store_id": binding["store_id"],
            "state_root_id": binding["state_root_id"],
            "source_head": binding["source_head"],
            "manifest_digest": binding["manifest_digest"],
        }
        if any(
            artifact.get(key) != value
            for key, value in expected_binding.items()
        ):
            errors.append(
                f"prepared packet {artifact_name} differs from binding"
            )
    return errors


def _derived_intent_head(intent: dict[str, Any]) -> str:
    return _canonical_digest({
        "schema_version": "s2_5_recovery_anchor_head_v1",
        "sequence": intent.get("candidate_sequence"),
        "previous_anchor_digest": intent.get("expected_head_digest"),
        "entry_digest": intent.get("entry_digest"),
    })


def _derived_idempotency(intent: dict[str, Any]) -> str:
    digest = _canonical_digest({
        "schema_version": "s2_5_recovery_anchor_idempotency_v1",
        "anchor_store_id": intent.get("anchor_store_id"),
        "anchor_collection_id": intent.get("anchor_collection_id"),
        "store_id": intent.get("store_id"),
        "state_root_id": intent.get("state_root_id"),
        "source_head": intent.get("source_head"),
        "manifest_digest": intent.get("manifest_digest"),
        "expected_snapshot_id": intent.get("expected_snapshot_id"),
        "expected_latest_version_id": intent.get("expected_latest_version_id"),
        "expected_sequence": intent.get("expected_sequence"),
        "expected_head_digest": intent.get("expected_head_digest"),
        "candidate_sequence": intent.get("candidate_sequence"),
        "candidate_head_digest": intent.get("candidate_head_digest"),
        "entry_digest": intent.get("entry_digest"),
    })
    return "s2-5-anchor-idempotency-" + digest.removeprefix("sha256:")


def _append_intent_semantic_errors(intent: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected = intent.get("expected_sequence")
    candidate = intent.get("candidate_sequence")
    expected_head = intent.get("expected_head_digest")
    if _integer(expected) and candidate != expected + 1:
        errors.append("append intent candidate sequence is not next")
    if expected == 0 and expected_head is not None:
        errors.append("append intent empty latest must have null head")
    if _integer(expected, minimum=1) and expected_head is None:
        errors.append("append intent non-empty latest must bind head")
    if intent.get("candidate_head_digest") != _derived_intent_head(intent):
        errors.append("append intent candidate head does not re-derive")
    if intent.get("idempotency_key") != _derived_idempotency(intent):
        errors.append("append intent idempotency key does not re-derive")
    return errors


def _append_result_semantic_errors(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    status = result.get("status")
    bound = (
        result.get("sequence"),
        result.get("head_digest"),
        result.get("object_id"),
        result.get("version_id"),
        result.get("checksum"),
        result.get("entry_digest"),
    )
    if status in {"APPENDED", "IDEMPOTENT_EXACT"}:
        if any(value is None for value in bound):
            errors.append("successful append result must bind the exact immutable version")
        if result.get("authenticated_response") is not False:
            errors.append("local append result cannot claim external authentication")
        if result.get("failure_code") != STATUS_UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED:
            errors.append("local append result must retain the external-anchor gap")
    elif status == "RECONCILED_EXACT_UNVERIFIED":
        if any(value is None for value in bound):
            errors.append("reconciled result must bind the exact immutable version")
        if result.get("authenticated_response") is not False:
            errors.append("reconciled local result cannot claim external authentication")
        if result.get("failure_code") != STATUS_UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED:
            errors.append("reconciled result must retain the external-anchor gap")
    elif status == "AMBIGUOUS_COMMITTED":
        if any(value is not None for value in bound):
            errors.append("ambiguous append result cannot claim an exact version")
        if result.get("authenticated_response") is not False:
            errors.append("ambiguous append result cannot claim authentication")
        if result.get("failure_code") != "anchor_compare_append_outcome_ambiguous":
            errors.append("ambiguous append result must carry its stable failure code")
    elif status == "RECOVERY_REQUIRED":
        if any(value is not None for value in bound):
            errors.append("recovery append result cannot claim an exact version")
        if not isinstance(result.get("failure_code"), str):
            errors.append("recovery append result must carry a failure code")
    return errors


def _readback_semantic_errors(readback: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    status = readback.get("status")
    checks = (
        readback.get("exact_version_match"),
        readback.get("checksum_match"),
        readback.get("head_match"),
    )
    bound = (
        readback.get("object_id"),
        readback.get("version_id"),
        readback.get("checksum"),
        readback.get("head_digest"),
        readback.get("sequence"),
        readback.get("entry_digest"),
    )
    if readback.get("reader_identity") == readback.get("verifier_identity"):
        errors.append("readback reader and verifier identities must differ")
    if status == "PASS":
        errors.append("local readback cannot claim PASS")
    elif status == "UNVERIFIED":
        if checks != (False, False, False):
            errors.append("UNVERIFIED readback cannot retain PASS checks")
        if readback.get("failure_code") != STATUS_UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED:
            errors.append("UNVERIFIED readback must retain the external-anchor gap")
    elif status == "NOT_PERFORMED":
        if checks != (False, False, False) or any(value is not None for value in bound):
            errors.append("unperformed readback cannot claim version evidence")
        if not isinstance(readback.get("failure_code"), str):
            errors.append("unperformed readback must carry a failure")
    elif status == "RECOVERY_REQUIRED":
        if checks != (False, False, False):
            errors.append("recovery readback cannot retain PASS checks")
        if not isinstance(readback.get("failure_code"), str):
            errors.append("recovery readback must carry a failure")
    return errors


def _postcheck_semantic_errors(postcheck: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    status = postcheck.get("status")
    checks = (
        postcheck.get("appended_entry_present"),
        postcheck.get("latest_advanced"),
        postcheck.get("full_chain_valid"),
        postcheck.get("identity_distinct"),
    )
    digests = (
        postcheck.get("readback_digest"),
        postcheck.get("latest_digest"),
        postcheck.get("enumeration_digest"),
    )
    if status == "PASS":
        errors.append("local postcheck cannot claim PASS")
    elif status == "UNVERIFIED":
        if postcheck.get("full_chain_valid") is not False:
            errors.append("UNVERIFIED postcheck cannot claim a valid trusted chain")
        if postcheck.get("identity_distinct") is not False:
            errors.append("UNVERIFIED postcheck cannot claim authenticated identities")
        if postcheck.get("failure_code") != STATUS_UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED:
            errors.append("UNVERIFIED postcheck must retain the external-anchor gap")
    elif status == "NOT_PERFORMED":
        if checks != (False, False, False, False):
            errors.append("unperformed postcheck cannot claim checks")
        if any(value is not None for value in digests):
            errors.append("unperformed postcheck cannot bind evidence")
        if not isinstance(postcheck.get("failure_code"), str):
            errors.append("unperformed postcheck must carry a failure")
    elif status == "RECOVERY_REQUIRED":
        if checks != (False, False, False, False):
            errors.append("recovery postcheck cannot retain PASS checks")
        if not isinstance(postcheck.get("failure_code"), str):
            errors.append("recovery postcheck must carry a failure")
    return errors


def _rollback_semantic_errors(rollback: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if rollback.get("immutable_anchor_deleted") is not False:
        errors.append("rollback must never delete an immutable anchor")
    if rollback.get("deletion_attempted") is not False:
        errors.append("rollback must never attempt immutable-anchor deletion")
    if rollback.get("status") == "NOT_REQUIRED":
        if rollback.get("operator_action_required") is not False:
            errors.append("NOT_REQUIRED rollback cannot require operator action")
        if rollback.get("reason") is not None:
            errors.append("NOT_REQUIRED rollback cannot carry a failure reason")
    elif rollback.get("status") == "RECOVERY_REQUIRED":
        if rollback.get("operator_action_required") is not True:
            errors.append("RECOVERY_REQUIRED rollback must require operator action")
        if not isinstance(rollback.get("reason"), str):
            errors.append("RECOVERY_REQUIRED rollback must carry a reason")
    return errors


def _parse_time(value: Any, *, code: str) -> datetime:
    if not isinstance(value, str):
        raise RecoveryAnchorError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RecoveryAnchorError(code) from error
    if parsed.tzinfo is None:
        raise RecoveryAnchorError(code)
    return parsed


class AuthenticatedRecoveryAnchor:
    """Validate and append one fixed collection without claiming external trust."""

    def __init__(self, *, writer: Any, reader: Any, verifier: Any, clock: Any) -> None:
        capabilities = (writer, reader, verifier, clock)
        if len({id(item) for item in capabilities}) != len(capabilities):
            raise RecoveryAnchorError("anchor_capabilities_must_be_distinct")
        if not hasattr(writer, "compare_append") or not callable(writer.compare_append):
            raise RecoveryAnchorError("writer_capability_invalid")
        if (
            not hasattr(reader, "read_signed_latest")
            or not callable(reader.read_signed_latest)
            or not hasattr(reader, "read_signed_page")
            or not callable(reader.read_signed_page)
            or not hasattr(reader, "read_signed_exact")
            or not callable(reader.read_signed_exact)
        ):
            raise RecoveryAnchorError("reader_capability_invalid")
        if not hasattr(verifier, "verify_signed") or not callable(verifier.verify_signed):
            raise RecoveryAnchorError("verifier_capability_invalid")
        if not hasattr(clock, "now") or not callable(clock.now):
            raise RecoveryAnchorError("clock_capability_invalid")
        self._writer = writer
        self._reader = reader
        self._verifier = verifier
        self._clock = clock
        self._identities = {
            kind: dict(identity) for kind, identity in _IDENTITY_PROFILE.items()
        }

    def _now(self) -> datetime:
        try:
            moment = self._clock.now()
        except Exception as error:
            raise RecoveryAnchorError(
                "anchor_clock_unavailable", type(error).__name__
            ) from error
        if not isinstance(moment, datetime) or moment.tzinfo is None:
            raise RecoveryAnchorError("anchor_clock_not_aware_datetime")
        return moment

    @staticmethod
    def _freshness_at(
        artifact: dict[str, Any], *, label: str, moment: datetime
    ) -> None:
        issued = _parse_time(artifact.get("issued_at"), code=f"{label}_issued_at_invalid")
        expires = _parse_time(
            artifact.get("expires_at"), code=f"{label}_expires_at_invalid"
        )
        lifetime = expires - issued
        if lifetime <= timedelta(0) or lifetime > timedelta(minutes=5):
            raise RecoveryAnchorError(f"{label}_freshness_window_invalid")
        if issued - moment > timedelta(seconds=60):
            raise RecoveryAnchorError(f"{label}_issued_in_future")
        if moment > expires:
            raise RecoveryAnchorError(f"{label}_stale")

    def _freshness(self, artifact: dict[str, Any], *, label: str) -> None:
        self._freshness_at(artifact, label=label, moment=self._now())

    def _verify_signed(
        self,
        envelope: Any,
        *,
        purpose: str,
        schema_version: str,
        signer_kind: str,
    ) -> dict[str, Any]:
        try:
            payload = self._verifier.verify_signed(
                purpose=purpose, envelope=envelope
            )
        except Exception as error:
            raise RecoveryAnchorError(
                f"{purpose}_signature_invalid", type(error).__name__
            ) from error
        if not isinstance(payload, dict):
            raise RecoveryAnchorError(f"{purpose}_verified_payload_invalid")
        if payload.get("schema_version") != schema_version:
            raise RecoveryAnchorError(f"{purpose}_schema_version_invalid")
        errors = validate_local_artifact(payload)
        if errors:
            raise RecoveryAnchorError(f"{purpose}_artifact_invalid", "; ".join(errors))
        if payload.get("signer_identity") != self._identities[signer_kind]:
            raise RecoveryAnchorError(f"{purpose}_signer_identity_mismatch")
        self._freshness(payload, label=purpose)
        return payload

    def _verify_protocol_signed(
        self,
        envelope: Any,
        *,
        purpose: str,
        schema_version: str,
        signer_kind: str,
        expected_keys: set[str],
        signer_identity_field: str = "signer_identity",
    ) -> dict[str, Any]:
        try:
            payload = self._verifier.verify_signed(
                purpose=purpose, envelope=envelope
            )
        except Exception as error:
            raise RecoveryAnchorError(
                f"{purpose}_signature_invalid", type(error).__name__
            ) from error
        if not isinstance(payload, dict) or set(payload) != expected_keys:
            raise RecoveryAnchorError(f"{purpose}_payload_fields_invalid")
        if payload.get("schema_version") != schema_version:
            raise RecoveryAnchorError(f"{purpose}_schema_version_invalid")
        if payload.get("self_digest") != central_validator.artifact_self_digest(payload):
            raise RecoveryAnchorError(f"{purpose}_self_digest_invalid")
        if payload.get("anchor_store_id") != ANCHOR_STORE_ID or payload.get(
            "anchor_collection_id"
        ) != ANCHOR_COLLECTION_ID:
            raise RecoveryAnchorError(f"{purpose}_anchor_identity_invalid")
        if payload.get(signer_identity_field) != self._identities[signer_kind]:
            raise RecoveryAnchorError(f"{purpose}_signer_identity_mismatch")
        if (
            payload.get("evidence_class") != PROFILE_EVIDENCE_CLASS
            or payload.get("production_effect") is not False
            or payload.get("production_effect_count") != 0
        ):
            raise RecoveryAnchorError(f"{purpose}_evidence_boundary_invalid")
        self._freshness(payload, label=purpose)
        return payload

    @staticmethod
    def _manifest_errors(manifest: Any) -> list[str]:
        if not isinstance(manifest, dict):
            return ["manifest_not_object"]
        errors = recovery_store.validate_local_artifact(manifest)
        if manifest.get("schema_version") != "s2_5_recovery_store_manifest_v1":
            errors.append("manifest_schema_invalid")
        return errors

    @staticmethod
    def _binding_errors(
        artifact: dict[str, Any], manifest: dict[str, Any]
    ) -> list[str]:
        expected = {
            "anchor_store_id": ANCHOR_STORE_ID,
            "anchor_collection_id": ANCHOR_COLLECTION_ID,
            "store_id": manifest["store_id"],
            "state_root_id": manifest["state_root_id"],
            "source_head": manifest["source_head"],
            "target_profile_id": PROFILE_ID,
        }
        return [
            f"{key}_mismatch"
            for key, value in expected.items()
            if artifact.get(key) != value
        ]

    def _read_latest(self, binding: dict[str, Any]) -> dict[str, Any]:
        try:
            envelope = self._reader.read_signed_latest()
        except Exception as error:
            raise RecoveryAnchorError(
                "anchor_latest_read_failed", type(error).__name__
            ) from error
        latest = self._verify_signed(
            envelope,
            purpose="anchor_latest",
            schema_version="s2_5_recovery_anchor_latest_v1",
            signer_kind="reader",
        )
        bindings = self._binding_errors(latest, binding)
        if bindings:
            raise RecoveryAnchorError("anchor_latest_binding_invalid", "; ".join(bindings))
        return latest

    @staticmethod
    def _record_errors(
        record: Any,
        manifest: dict[str, Any],
        *,
        expected_sequence: int,
        expected_previous: str | None,
        expected_idempotency_key: str | None = None,
    ) -> list[str]:
        if not isinstance(record, dict):
            return ["anchor_record_not_object"]
        expected_keys = {
            "object_id", "version_id", "idempotency_key", "checksum",
            "head_digest", "immutable", "retention_mode", "entry",
        }
        errors = []
        if set(record) != expected_keys:
            errors.append("anchor_record_fields_invalid")
        entry = record.get("entry")
        entry_errors = validate_local_artifact(entry)
        if entry_errors:
            errors.append("anchor_record_entry_invalid")
            return errors
        if AuthenticatedRecoveryAnchor._binding_errors(entry, manifest):
            errors.append("anchor_record_entry_binding_invalid")
        if entry.get("sequence") != expected_sequence:
            errors.append("anchor_record_sequence_gap")
        if entry.get("previous_anchor_digest") != expected_previous:
            errors.append("anchor_record_predecessor_gap_or_fork")
        if (
            expected_idempotency_key is not None
            and record.get("idempotency_key") != expected_idempotency_key
        ):
            errors.append("anchor_record_idempotency_mismatch")
        if record.get("checksum") != central_validator.canonical_digest(entry):
            errors.append("anchor_record_checksum_mismatch")
        if record.get("head_digest") != derive_anchor_head(entry):
            errors.append("anchor_record_head_mismatch")
        if record.get("immutable") is not True:
            errors.append("anchor_record_not_immutable")
        if record.get("retention_mode") != "COMPLIANCE_WORM":
            errors.append("anchor_record_retention_invalid")
        return errors

    def enumerate(self, manifest: dict[str, Any]) -> dict[str, Any]:
        """Authenticate every page from genesis to the signed latest head."""

        manifest_errors = self._manifest_errors(manifest)
        if manifest_errors:
            raise RecoveryAnchorError(
                "anchor_manifest_invalid", "; ".join(manifest_errors)
            )
        return self._enumerate_binding({
            "store_id": manifest["store_id"],
            "state_root_id": manifest["state_root_id"],
            "source_head": manifest["source_head"],
        })

    def _enumerate_binding(
        self,
        binding: dict[str, Any],
    ) -> dict[str, Any]:
        """Enumerate one fixed binding without claiming a durable floor."""

        latest = self._read_latest(binding)
        if latest["page_count"] > 10000 or latest["entry_count"] > 100000:
            raise RecoveryAnchorError("anchor_enumeration_bounds_exceeded")
        records: list[dict[str, Any]] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        object_ids: set[str] = set()
        version_ids: set[str] = set()
        sequence_heads: dict[int, str] = {}
        expected_sequence = 1
        expected_previous: str | None = None

        for page_index in range(latest["page_count"]):
            if cursor is not None:
                if cursor in seen_cursors:
                    raise RecoveryAnchorError("anchor_cursor_repeat")
                seen_cursors.add(cursor)
            try:
                envelope = self._reader.read_signed_page(
                    cursor=cursor, snapshot_id=latest["snapshot_id"]
                )
            except Exception as error:
                raise RecoveryAnchorError(
                    "anchor_page_read_failed", type(error).__name__
                ) from error
            page = self._verify_signed(
                envelope,
                purpose="anchor_page",
                schema_version="s2_5_recovery_anchor_page_v1",
                signer_kind="reader",
            )
            bindings = self._binding_errors(page, binding)
            if bindings:
                raise RecoveryAnchorError(
                    "anchor_page_binding_invalid", "; ".join(bindings)
                )
            page_expectations = {
                "snapshot_id": latest["snapshot_id"],
                "latest_version_id": latest["latest_version_id"],
                "latest_sequence": latest["sequence"],
                "latest_head_digest": latest["head_digest"],
                "entry_count": latest["entry_count"],
                "page_count": latest["page_count"],
                "page_index": page_index,
                "cursor_in": cursor,
            }
            if any(page.get(key) != value for key, value in page_expectations.items()):
                raise RecoveryAnchorError("anchor_page_snapshot_or_count_drift")
            terminal = page["cursor_out"] is None
            if terminal and page_index + 1 != latest["page_count"]:
                raise RecoveryAnchorError("anchor_page_early_terminal")
            if not terminal and page_index + 1 == latest["page_count"]:
                raise RecoveryAnchorError("anchor_page_late_terminal")
            if page["cursor_out"] == cursor and cursor is not None:
                raise RecoveryAnchorError("anchor_cursor_repeat")
            for record in page["records"]:
                errors = self._record_errors(
                    record,
                    binding,
                    expected_sequence=expected_sequence,
                    expected_previous=expected_previous,
                )
                if errors:
                    raise RecoveryAnchorError(
                        "anchor_record_invalid", "; ".join(errors)
                    )
                sequence = record["entry"]["sequence"]
                head = record["head_digest"]
                if sequence in sequence_heads and sequence_heads[sequence] != head:
                    raise RecoveryAnchorError("anchor_sequence_fork")
                if sequence in sequence_heads:
                    raise RecoveryAnchorError("anchor_sequence_duplicate")
                if record["object_id"] in object_ids:
                    raise RecoveryAnchorError("anchor_object_duplicate")
                if record["version_id"] in version_ids:
                    raise RecoveryAnchorError("anchor_version_duplicate")
                sequence_heads[sequence] = head
                object_ids.add(record["object_id"])
                version_ids.add(record["version_id"])
                records.append(record)
                expected_previous = head
                expected_sequence += 1
            cursor = page["cursor_out"]

        if cursor is not None:
            raise RecoveryAnchorError("anchor_enumeration_not_terminal")
        if len(records) != latest["entry_count"]:
            raise RecoveryAnchorError("anchor_entry_count_drift")
        if records:
            head_record = records[-1]
            if (
                head_record["head_digest"] != latest["head_digest"]
                or head_record["object_id"] != latest["head_object_id"]
                or head_record["version_id"] != latest["head_version_id"]
                or head_record["entry"]["sequence"] != latest["sequence"]
            ):
                raise RecoveryAnchorError("anchor_latest_head_mismatch")
        elif latest["sequence"] != 0:
            raise RecoveryAnchorError("anchor_nonempty_latest_without_records")
        return {
            "status": STATUS_UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED,
            "evidence_class": PROFILE_EVIDENCE_CLASS,
            "monotonic_floor_status": (
                "UNVERIFIED_DURABLE_MONOTONIC_FLOOR_REQUIRED"
            ),
            "latest": latest,
            "records": records,
            "enumeration_digest": _canonical_digest({
                "schema_version": "s2_5_recovery_anchor_enumeration_v1",
                "latest_digest": latest["self_digest"],
                "record_heads": [item["head_digest"] for item in records],
            }),
        }

    @staticmethod
    def _build_artifact(value: dict[str, Any]) -> dict[str, Any]:
        artifact = _seal(value)
        errors = validate_local_artifact(artifact)
        if errors:
            raise RecoveryAnchorError(
                "anchor_generated_artifact_invalid", "; ".join(errors)
            )
        return artifact

    def _build_entry(
        self,
        manifest: dict[str, Any],
        latest: dict[str, Any],
        moment: datetime,
    ) -> dict[str, Any]:
        nonce_digest = _canonical_digest({
            "schema_version": "s2_5_recovery_anchor_nonce_v1",
            "anchor_store_id": ANCHOR_STORE_ID,
            "anchor_collection_id": ANCHOR_COLLECTION_ID,
            "manifest_digest": manifest["self_digest"],
            "expected_snapshot_id": latest["snapshot_id"],
            "expected_latest_version_id": latest["latest_version_id"],
            "expected_sequence": latest["sequence"],
            "expected_head_digest": latest["head_digest"],
        })
        consumed = manifest["consumed_authorization_ids"]
        return self._build_artifact({
            "schema_version": "s2_5_recovery_anchor_entry_v2",
            "anchor_store_id": ANCHOR_STORE_ID,
            "anchor_collection_id": ANCHOR_COLLECTION_ID,
            "store_id": manifest["store_id"],
            "state_root_id": manifest["state_root_id"],
            "source_head": manifest["source_head"],
            "sequence": latest["sequence"] + 1,
            "previous_anchor_digest": latest["head_digest"],
            "manifest_generation": manifest["generation"],
            "manifest_digest": manifest["self_digest"],
            "unresolved_state_digest": manifest["unresolved_state_digest"],
            "authorization_id": consumed[-1] if consumed else None,
            "entry_status": manifest["phase"],
            "append_actor_identity": self._identities["writer"],
            "appended_at": moment.isoformat(),
            "nonce": (
                "s2-5-anchor-nonce-" + nonce_digest.removeprefix("sha256:")
            ),
            **_COMMON,
        })

    def _build_intent(
        self,
        manifest: dict[str, Any],
        latest: dict[str, Any],
        entry: dict[str, Any],
        moment: datetime,
    ) -> dict[str, Any]:
        candidate_head = derive_anchor_head(entry)
        base = {
            "schema_version": "s2_5_recovery_anchor_append_intent_v1",
            "anchor_store_id": ANCHOR_STORE_ID,
            "anchor_collection_id": ANCHOR_COLLECTION_ID,
            "store_id": manifest["store_id"],
            "state_root_id": manifest["state_root_id"],
            "source_head": manifest["source_head"],
            "manifest_digest": manifest["self_digest"],
            "expected_snapshot_id": latest["snapshot_id"],
            "expected_latest_version_id": latest["latest_version_id"],
            "expected_sequence": latest["sequence"],
            "expected_head_digest": latest["head_digest"],
            "candidate_sequence": entry["sequence"],
            "candidate_head_digest": candidate_head,
            "entry_digest": entry["self_digest"],
            "idempotency_key": "",
            "operation": "COMPARE_APPEND",
            "issued_at": moment.isoformat(),
            "expires_at": (moment + timedelta(minutes=5)).isoformat(),
            "actor_identity": self._identities["writer"],
            **_COMMON,
        }
        base["idempotency_key"] = _derived_idempotency(base)
        return self._build_artifact(base)

    def _recovery_chain(
        self,
        intent: dict[str, Any],
        *,
        prepared_packet_digest: str,
        code: str,
        result_status: str = "RECOVERY_REQUIRED",
        moment: datetime,
    ) -> dict[str, Any]:
        failure_code = (
            "anchor_compare_append_outcome_ambiguous"
            if result_status == "AMBIGUOUS_COMMITTED"
            else code
        )
        result = self._build_artifact({
            "schema_version": "s2_5_recovery_anchor_append_result_v1",
            "anchor_store_id": ANCHOR_STORE_ID,
            "anchor_collection_id": ANCHOR_COLLECTION_ID,
            "prepared_packet_digest": prepared_packet_digest,
            "intent_digest": intent["self_digest"],
            "idempotency_key": intent["idempotency_key"],
            "status": result_status,
            "sequence": None,
            "head_digest": None,
            "object_id": None,
            "version_id": None,
            "checksum": None,
            "entry_digest": None,
            "append_actor_identity": self._identities["writer"],
            "authenticated_response": False,
            "failure_code": failure_code,
            "completed_at": moment.isoformat(),
            **_COMMON,
        })
        readback = self._build_artifact({
            "schema_version": "s2_5_recovery_anchor_readback_v1",
            "anchor_store_id": ANCHOR_STORE_ID,
            "anchor_collection_id": ANCHOR_COLLECTION_ID,
            "result_digest": result["self_digest"],
            "object_id": None,
            "version_id": None,
            "checksum": None,
            "head_digest": None,
            "sequence": None,
            "entry_digest": None,
            "exact_version_match": False,
            "checksum_match": False,
            "head_match": False,
            "reader_identity": self._identities["reader"],
            "verifier_identity": self._identities["verifier"],
            "verified_at": moment.isoformat(),
            "status": "NOT_PERFORMED",
            "failure_code": failure_code,
            **_COMMON,
        })
        postcheck = self._build_artifact({
            "schema_version": "s2_5_recovery_anchor_postcheck_v1",
            "anchor_store_id": ANCHOR_STORE_ID,
            "anchor_collection_id": ANCHOR_COLLECTION_ID,
            "result_digest": result["self_digest"],
            "readback_digest": None,
            "latest_digest": None,
            "enumeration_digest": None,
            "appended_entry_present": False,
            "latest_advanced": False,
            "full_chain_valid": False,
            "identity_distinct": False,
            "checked_at": moment.isoformat(),
            "status": "NOT_PERFORMED",
            "failure_code": failure_code,
            **_COMMON,
        })
        rollback = self._build_artifact({
            "schema_version": "s2_5_recovery_anchor_rollback_v1",
            "anchor_store_id": ANCHOR_STORE_ID,
            "anchor_collection_id": ANCHOR_COLLECTION_ID,
            "intent_digest": intent["self_digest"],
            "result_digest": result["self_digest"],
            "status": "RECOVERY_REQUIRED",
            "immutable_anchor_deleted": False,
            "deletion_attempted": False,
            "operator_action_required": True,
            "reason": failure_code,
            "completed_at": moment.isoformat(),
            **_COMMON,
        })
        return {
            "status": "RECOVERY_REQUIRED",
            "evidence_class": PROFILE_EVIDENCE_CLASS,
            "prepared_packet_digest": prepared_packet_digest,
            "failure_detail_code": code,
            "intent": intent,
            "result": result,
            "readback": readback,
            "postcheck": postcheck,
            "rollback": rollback,
        }

    def _post_append_recovery(
        self,
        intent: dict[str, Any],
        result: dict[str, Any],
        entry: dict[str, Any],
        *,
        prepared_packet_digest: str,
        code: str,
        moment: datetime,
        readback: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if readback is None:
            readback = self._build_artifact({
                "schema_version": "s2_5_recovery_anchor_readback_v1",
                "anchor_store_id": ANCHOR_STORE_ID,
                "anchor_collection_id": ANCHOR_COLLECTION_ID,
                "result_digest": result["self_digest"],
                "object_id": result["object_id"],
                "version_id": result["version_id"],
                "checksum": result["checksum"],
                "head_digest": result["head_digest"],
                "sequence": result["sequence"],
                "entry_digest": result["entry_digest"],
                "exact_version_match": False,
                "checksum_match": False,
                "head_match": False,
                "reader_identity": self._identities["reader"],
                "verifier_identity": self._identities["verifier"],
                "verified_at": moment.isoformat(),
                "status": "RECOVERY_REQUIRED",
                "failure_code": code,
                **_COMMON,
            })
        postcheck = self._build_artifact({
            "schema_version": "s2_5_recovery_anchor_postcheck_v1",
            "anchor_store_id": ANCHOR_STORE_ID,
            "anchor_collection_id": ANCHOR_COLLECTION_ID,
            "result_digest": result["self_digest"],
            "readback_digest": readback["self_digest"],
            "latest_digest": None,
            "enumeration_digest": None,
            "appended_entry_present": False,
            "latest_advanced": False,
            "full_chain_valid": False,
            "identity_distinct": False,
            "checked_at": moment.isoformat(),
            "status": "RECOVERY_REQUIRED",
            "failure_code": code,
            **_COMMON,
        })
        rollback = self._build_artifact({
            "schema_version": "s2_5_recovery_anchor_rollback_v1",
            "anchor_store_id": ANCHOR_STORE_ID,
            "anchor_collection_id": ANCHOR_COLLECTION_ID,
            "intent_digest": intent["self_digest"],
            "result_digest": result["self_digest"],
            "status": "RECOVERY_REQUIRED",
            "immutable_anchor_deleted": False,
            "deletion_attempted": False,
            "operator_action_required": True,
            "reason": code,
            "completed_at": moment.isoformat(),
            **_COMMON,
        })
        return {
            "status": "RECOVERY_REQUIRED",
            "evidence_class": PROFILE_EVIDENCE_CLASS,
            "prepared_packet_digest": prepared_packet_digest,
            "entry": entry,
            "intent": intent,
            "result": result,
            "readback": readback,
            "postcheck": postcheck,
            "rollback": rollback,
        }

    def prepare_append(self, manifest: dict[str, Any]) -> dict[str, Any]:
        """Build a closed exact packet without invoking the writer capability."""

        baseline = self.enumerate(manifest)
        moment = self._now()
        latest = baseline["latest"]
        entry = self._build_entry(manifest, latest, moment)
        intent = self._build_intent(manifest, latest, entry, moment)
        request = {
            "schema_version": "s2_5_recovery_anchor_compare_append_request_v1",
            "anchor_store_id": ANCHOR_STORE_ID,
            "anchor_collection_id": ANCHOR_COLLECTION_ID,
            "expected_snapshot_id": latest["snapshot_id"],
            "expected_latest_version_id": latest["latest_version_id"],
            "expected_sequence": latest["sequence"],
            "expected_head_digest": latest["head_digest"],
            "idempotency_key": intent["idempotency_key"],
            "entry": entry,
        }
        payload = {
            "schema_version": "s2_5_recovery_anchor_prepared_payload_v1",
            "binding": {
                "store_id": manifest["store_id"],
                "state_root_id": manifest["state_root_id"],
                "source_head": manifest["source_head"],
                "manifest_digest": manifest["self_digest"],
            },
            "baseline_latest_digest": latest["self_digest"],
            "entry": entry,
            "intent": intent,
            "request": request,
        }
        return self._build_artifact({
            "schema_version": "s2_5_recovery_anchor_prepared_append_v1",
            "anchor_store_id": ANCHOR_STORE_ID,
            "anchor_collection_id": ANCHOR_COLLECTION_ID,
            **payload["binding"],
            "baseline_latest_digest": latest["self_digest"],
            "prepared_payload_json": _canonical_json(payload),
            "prepared_payload_digest": _canonical_digest(payload),
            "prepared_at": moment.isoformat(),
            "status": "PREPARED_NO_EFFECT",
            "effect_executed": False,
            "monotonic_floor_status": (
                "UNVERIFIED_DURABLE_MONOTONIC_FLOOR_REQUIRED"
            ),
            **_COMMON,
        })

    def append(self, manifest: dict[str, Any]) -> dict[str, Any]:
        """Refuse the unsafe prepare-and-effect convenience API."""

        raise RecoveryAnchorError("anchor_prepared_packet_required")

    @staticmethod
    def _decode_prepared(prepared: Any) -> dict[str, Any]:
        if not isinstance(prepared, dict) or prepared.get("schema_version") != (
            "s2_5_recovery_anchor_prepared_append_v1"
        ):
            raise RecoveryAnchorError("anchor_prepared_packet_invalid")
        errors = validate_local_artifact(prepared)
        if errors:
            raise RecoveryAnchorError(
                "anchor_prepared_packet_invalid", "; ".join(errors)
            )
        try:
            payload = json.loads(prepared["prepared_payload_json"])
        except (TypeError, ValueError) as error:
            raise RecoveryAnchorError(
                "anchor_prepared_packet_payload_invalid"
            ) from error
        if not isinstance(payload, dict):
            raise RecoveryAnchorError("anchor_prepared_packet_payload_invalid")
        return payload

    def execute_prepared(self, prepared: dict[str, Any]) -> dict[str, Any]:
        """Execute only the request sealed into a previously prepared packet."""

        payload = self._decode_prepared(prepared)
        binding = payload["binding"]
        moment = self._now()
        entry = payload["entry"]
        intent = payload["intent"]
        request = payload["request"]
        try:
            self._freshness_at(
                intent,
                label="anchor_append_intent",
                moment=moment,
            )
        except RecoveryAnchorError as error:
            return self._recovery_chain(
                intent,
                prepared_packet_digest=prepared["self_digest"],
                code=error.code,
                result_status="RECOVERY_REQUIRED",
                moment=moment,
            )
        latest = {
            "snapshot_id": request["expected_snapshot_id"],
            "latest_version_id": request["expected_latest_version_id"],
            "sequence": request["expected_sequence"],
            "head_digest": request["expected_head_digest"],
        }
        try:
            envelope = self._writer.compare_append(request=request)
            response = self._verify_protocol_signed(
                envelope,
                purpose="anchor_compare_append",
                schema_version="s2_5_recovery_anchor_compare_append_response_v1",
                signer_kind="writer",
                expected_keys={
                    "schema_version", "anchor_store_id", "anchor_collection_id",
                    "status", "idempotency_key", "expected_latest_version_id",
                    "expected_sequence", "expected_head_digest", "record",
                    "signer_identity", "issued_at", "expires_at", "evidence_class",
                    "production_effect", "production_effect_count", "self_digest",
                },
            )
        except Exception as error:
            code = (
                error.code
                if isinstance(error, RecoveryAnchorError)
                else "anchor_compare_append_failed"
            )
            return self._recovery_chain(
                intent,
                prepared_packet_digest=prepared["self_digest"],
                code=code,
                result_status="AMBIGUOUS_COMMITTED",
                moment=moment,
            )
        response_expected = {
            "idempotency_key": intent["idempotency_key"],
            "expected_latest_version_id": latest["latest_version_id"],
            "expected_sequence": latest["sequence"],
            "expected_head_digest": latest["head_digest"],
        }
        if any(response.get(key) != value for key, value in response_expected.items()):
            return self._recovery_chain(
                intent,
                prepared_packet_digest=prepared["self_digest"],
                code="anchor_compare_append_response_binding_mismatch",
                result_status="AMBIGUOUS_COMMITTED",
                moment=moment,
            )
        if response["status"] not in {"APPENDED", "IDEMPOTENT_EXACT"}:
            ambiguous = response.get("record") is not None
            return self._recovery_chain(
                intent,
                prepared_packet_digest=prepared["self_digest"],
                code="anchor_compare_append_conflict",
                result_status=(
                    "AMBIGUOUS_COMMITTED"
                    if ambiguous
                    else "RECOVERY_REQUIRED"
                ),
                moment=moment,
            )
        record = response["record"]
        record_errors = self._record_errors(
            record,
            binding,
            expected_sequence=entry["sequence"],
            expected_previous=latest["head_digest"],
            expected_idempotency_key=request["idempotency_key"],
        )
        if record_errors or not isinstance(record, dict) or record.get("entry") != entry:
            return self._recovery_chain(
                intent,
                prepared_packet_digest=prepared["self_digest"],
                code="anchor_compare_append_not_exact",
                result_status="AMBIGUOUS_COMMITTED",
                moment=moment,
            )
        result = self._build_artifact({
            "schema_version": "s2_5_recovery_anchor_append_result_v1",
            "anchor_store_id": ANCHOR_STORE_ID,
            "anchor_collection_id": ANCHOR_COLLECTION_ID,
            "prepared_packet_digest": prepared["self_digest"],
            "intent_digest": intent["self_digest"],
            "idempotency_key": intent["idempotency_key"],
            "status": response["status"],
            "sequence": entry["sequence"],
            "head_digest": record["head_digest"],
            "object_id": record["object_id"],
            "version_id": record["version_id"],
            "checksum": record["checksum"],
            "entry_digest": entry["self_digest"],
            "append_actor_identity": self._identities["writer"],
            "authenticated_response": False,
            "failure_code": STATUS_UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED,
            "completed_at": moment.isoformat(),
            **_COMMON,
        })
        try:
            exact_envelope = self._reader.read_signed_exact(
                object_id=record["object_id"], version_id=record["version_id"]
            )
            exact = self._verify_protocol_signed(
                exact_envelope,
                purpose="anchor_exact_read",
                schema_version="s2_5_recovery_anchor_exact_read_v1",
                signer_kind="reader",
                expected_keys={
                    "schema_version", "anchor_store_id", "anchor_collection_id",
                    "record", "reader_identity", "issued_at", "expires_at",
                    "evidence_class", "production_effect",
                    "production_effect_count", "self_digest",
                },
                signer_identity_field="reader_identity",
            )
            if exact["reader_identity"] != self._identities["reader"]:
                raise RecoveryAnchorError("anchor_exact_read_identity_mismatch")
            if exact["record"] != record:
                raise RecoveryAnchorError("anchor_exact_read_version_mismatch")
        except Exception as error:
            code = (
                error.code
                if isinstance(error, RecoveryAnchorError)
                else "anchor_exact_read_failed"
            )
            return self._post_append_recovery(
                intent,
                result,
                entry,
                prepared_packet_digest=prepared["self_digest"],
                code=code,
                moment=moment,
            )
        readback = self._build_artifact({
            "schema_version": "s2_5_recovery_anchor_readback_v1",
            "anchor_store_id": ANCHOR_STORE_ID,
            "anchor_collection_id": ANCHOR_COLLECTION_ID,
            "result_digest": result["self_digest"],
            "object_id": record["object_id"],
            "version_id": record["version_id"],
            "checksum": record["checksum"],
            "head_digest": record["head_digest"],
            "sequence": entry["sequence"],
            "entry_digest": entry["self_digest"],
            "exact_version_match": False,
            "checksum_match": False,
            "head_match": False,
            "reader_identity": self._identities["reader"],
            "verifier_identity": self._identities["verifier"],
            "verified_at": moment.isoformat(),
            "status": "UNVERIFIED",
            "failure_code": STATUS_UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED,
            **_COMMON,
        })
        try:
            enumeration = self._enumerate_binding(binding)
        except RecoveryAnchorError as error:
            return self._post_append_recovery(
                intent,
                result,
                entry,
                prepared_packet_digest=prepared["self_digest"],
                code=error.code,
                moment=moment,
                readback=readback,
            )
        matching = [
            item for item in enumeration["records"]
            if item["object_id"] == record["object_id"]
            and item["version_id"] == record["version_id"]
            and item["idempotency_key"] == request["idempotency_key"]
            and item["entry"] == entry
        ]
        latest_advanced = (
            enumeration["latest"]["sequence"] >= entry["sequence"]
        )
        if len(matching) != 1 or not latest_advanced:
            return self._post_append_recovery(
                intent,
                result,
                entry,
                prepared_packet_digest=prepared["self_digest"],
                code="anchor_post_append_enumeration_mismatch",
                moment=moment,
                readback=readback,
            )
        postcheck = self._build_artifact({
            "schema_version": "s2_5_recovery_anchor_postcheck_v1",
            "anchor_store_id": ANCHOR_STORE_ID,
            "anchor_collection_id": ANCHOR_COLLECTION_ID,
            "result_digest": result["self_digest"],
            "readback_digest": readback["self_digest"],
            "latest_digest": enumeration["latest"]["self_digest"],
            "enumeration_digest": enumeration["enumeration_digest"],
            "appended_entry_present": True,
            "latest_advanced": True,
            "full_chain_valid": False,
            "identity_distinct": False,
            "checked_at": moment.isoformat(),
            "status": "UNVERIFIED",
            "failure_code": STATUS_UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED,
            **_COMMON,
        })
        rollback = self._build_artifact({
            "schema_version": "s2_5_recovery_anchor_rollback_v1",
            "anchor_store_id": ANCHOR_STORE_ID,
            "anchor_collection_id": ANCHOR_COLLECTION_ID,
            "intent_digest": intent["self_digest"],
            "result_digest": result["self_digest"],
            "status": "NOT_REQUIRED",
            "immutable_anchor_deleted": False,
            "deletion_attempted": False,
            "operator_action_required": False,
            "reason": None,
            "completed_at": moment.isoformat(),
            **_COMMON,
        })
        return {
            "status": STATUS_UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED,
            "evidence_class": PROFILE_EVIDENCE_CLASS,
            "prepared_packet_digest": prepared["self_digest"],
            "entry": entry,
            "intent": intent,
            "result": result,
            "readback": readback,
            "postcheck": postcheck,
            "rollback": rollback,
            "enumeration": enumeration,
        }

    def reconcile_prepared(
        self,
        prepared: dict[str, Any],
    ) -> dict[str, Any]:
        """Read-only reconciliation of one exact prepared idempotency request."""

        payload = self._decode_prepared(prepared)
        binding = payload["binding"]
        entry = payload["entry"]
        intent = payload["intent"]
        request = payload["request"]
        moment = self._now()
        try:
            enumeration = self._enumerate_binding(binding)
        except RecoveryAnchorError as error:
            return self._recovery_chain(
                intent,
                prepared_packet_digest=prepared["self_digest"],
                code=error.code,
                moment=moment,
            )
        keyed = [
            item for item in enumeration["records"]
            if item.get("idempotency_key") == request["idempotency_key"]
        ]
        matching = [
            item for item in keyed
            if item.get("entry") == entry
            and item.get("head_digest") == intent["candidate_head_digest"]
        ]
        if len(keyed) != 1 or len(matching) != 1:
            return self._recovery_chain(
                intent,
                prepared_packet_digest=prepared["self_digest"],
                code=(
                    "anchor_prepared_effect_not_observed"
                    if not keyed
                    else "anchor_prepared_reconciliation_mismatch"
                ),
                moment=moment,
            )
        record = matching[0]
        errors = self._record_errors(
            record,
            binding,
            expected_sequence=entry["sequence"],
            expected_previous=request["expected_head_digest"],
            expected_idempotency_key=request["idempotency_key"],
        )
        if errors:
            return self._recovery_chain(
                intent,
                prepared_packet_digest=prepared["self_digest"],
                code="anchor_prepared_reconciliation_mismatch",
                moment=moment,
            )
        try:
            exact_envelope = self._reader.read_signed_exact(
                object_id=record["object_id"],
                version_id=record["version_id"],
            )
            exact = self._verify_protocol_signed(
                exact_envelope,
                purpose="anchor_exact_read",
                schema_version="s2_5_recovery_anchor_exact_read_v1",
                signer_kind="reader",
                expected_keys={
                    "schema_version", "anchor_store_id", "anchor_collection_id",
                    "record", "reader_identity", "issued_at", "expires_at",
                    "evidence_class", "production_effect",
                    "production_effect_count", "self_digest",
                },
                signer_identity_field="reader_identity",
            )
            if exact["record"] != record:
                raise RecoveryAnchorError("anchor_exact_read_version_mismatch")
        except Exception as error:
            code = (
                error.code
                if isinstance(error, RecoveryAnchorError)
                else "anchor_exact_read_failed"
            )
            return self._recovery_chain(
                intent,
                prepared_packet_digest=prepared["self_digest"],
                code=code,
                moment=moment,
            )
        result = self._build_artifact({
            "schema_version": "s2_5_recovery_anchor_append_result_v1",
            "anchor_store_id": ANCHOR_STORE_ID,
            "anchor_collection_id": ANCHOR_COLLECTION_ID,
            "prepared_packet_digest": prepared["self_digest"],
            "intent_digest": intent["self_digest"],
            "idempotency_key": intent["idempotency_key"],
            "status": "RECONCILED_EXACT_UNVERIFIED",
            "sequence": entry["sequence"],
            "head_digest": record["head_digest"],
            "object_id": record["object_id"],
            "version_id": record["version_id"],
            "checksum": record["checksum"],
            "entry_digest": entry["self_digest"],
            "append_actor_identity": self._identities["writer"],
            "authenticated_response": False,
            "failure_code": STATUS_UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED,
            "completed_at": moment.isoformat(),
            **_COMMON,
        })
        readback = self._build_artifact({
            "schema_version": "s2_5_recovery_anchor_readback_v1",
            "anchor_store_id": ANCHOR_STORE_ID,
            "anchor_collection_id": ANCHOR_COLLECTION_ID,
            "result_digest": result["self_digest"],
            "object_id": record["object_id"],
            "version_id": record["version_id"],
            "checksum": record["checksum"],
            "head_digest": record["head_digest"],
            "sequence": entry["sequence"],
            "entry_digest": entry["self_digest"],
            "exact_version_match": False,
            "checksum_match": False,
            "head_match": False,
            "reader_identity": self._identities["reader"],
            "verifier_identity": self._identities["verifier"],
            "verified_at": moment.isoformat(),
            "status": "UNVERIFIED",
            "failure_code": STATUS_UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED,
            **_COMMON,
        })
        postcheck = self._build_artifact({
            "schema_version": "s2_5_recovery_anchor_postcheck_v1",
            "anchor_store_id": ANCHOR_STORE_ID,
            "anchor_collection_id": ANCHOR_COLLECTION_ID,
            "result_digest": result["self_digest"],
            "readback_digest": readback["self_digest"],
            "latest_digest": enumeration["latest"]["self_digest"],
            "enumeration_digest": enumeration["enumeration_digest"],
            "appended_entry_present": True,
            "latest_advanced": (
                enumeration["latest"]["sequence"] >= entry["sequence"]
            ),
            "full_chain_valid": False,
            "identity_distinct": False,
            "checked_at": moment.isoformat(),
            "status": "UNVERIFIED",
            "failure_code": STATUS_UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED,
            **_COMMON,
        })
        rollback = self._build_artifact({
            "schema_version": "s2_5_recovery_anchor_rollback_v1",
            "anchor_store_id": ANCHOR_STORE_ID,
            "anchor_collection_id": ANCHOR_COLLECTION_ID,
            "intent_digest": intent["self_digest"],
            "result_digest": result["self_digest"],
            "status": "NOT_REQUIRED",
            "immutable_anchor_deleted": False,
            "deletion_attempted": False,
            "operator_action_required": False,
            "reason": None,
            "completed_at": moment.isoformat(),
            **_COMMON,
        })
        return {
            "status": STATUS_UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED,
            "evidence_class": PROFILE_EVIDENCE_CLASS,
            "prepared_packet_digest": prepared["self_digest"],
            "entry": entry,
            "intent": intent,
            "result": result,
            "readback": readback,
            "postcheck": postcheck,
            "rollback": rollback,
            "enumeration": enumeration,
        }
