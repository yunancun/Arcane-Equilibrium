#!/usr/bin/env python3
"""Execute an exact recovery-controller outbox with effect-time admission.

This adapter is deliberately local-only.  It consumes the request bytes already
sealed into ``s2_5_recovery_controller_state_v2`` and can never promote its
result above ``LOCAL_REPRODUCIBLE``.  External/WORM trust is a separate adapter.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
for _candidate in (Path(__file__).resolve().parent, ML_TRAINING_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import aiml_gate_receipt_validator as central_validator  # noqa: E402
import agent_governance_s2_5_recovery_controller as controller  # noqa: E402
import agent_governance_s2_5_recovery_lock as recovery_lock  # noqa: E402
import agent_governance_s2_5_recovery_store as recovery_store  # noqa: E402
from agent_governance_schema import schema_subset_errors  # noqa: E402
from agent_governance_s2_5_disposable_profile import (  # noqa: E402
    ANCHOR_READER_CGROUP,
    ANCHOR_READER_ROLE,
    ANCHOR_READER_UNIT,
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
_ARTIFACT_SCHEMAS = frozenset({
    "s2_5_recovery_anchor_effect_intent_v1",
    "s2_5_recovery_anchor_effect_result_v1",
    "s2_5_recovery_anchor_effect_postcheck_v1",
    "s2_5_recovery_anchor_effect_rollback_v1",
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
_IDENTITIES = {
    "writer": {
        "schema_version": "s2_5_recovery_anchor_capability_identity_v1",
        "role": ANCHOR_WRITER_ROLE,
        "unit": ANCHOR_WRITER_UNIT,
        "cgroup": ANCHOR_WRITER_CGROUP,
    },
    "reader": {
        "schema_version": "s2_5_recovery_anchor_capability_identity_v1",
        "role": ANCHOR_READER_ROLE,
        "unit": ANCHOR_READER_UNIT,
        "cgroup": ANCHOR_READER_CGROUP,
    },
    "verifier": {
        "schema_version": "s2_5_recovery_anchor_capability_identity_v1",
        "role": ANCHOR_VERIFIER_ROLE,
        "unit": ANCHOR_VERIFIER_UNIT,
        "cgroup": ANCHOR_VERIFIER_CGROUP,
    },
}
WRITER_IDENTITY_DIGEST = central_validator.canonical_digest(
    _IDENTITIES["writer"]
)
READER_IDENTITY_DIGEST = central_validator.canonical_digest(
    _IDENTITIES["reader"]
)
VERIFIER_IDENTITY_DIGEST = central_validator.canonical_digest(
    _IDENTITIES["verifier"]
)
_PROTOCOL_KEYS = {
    "controller_anchor_compare_append": frozenset({
        "schema_version",
        "request_digest",
        "prepared_payload_digest",
        "idempotency_key",
        "status",
        "object_id",
        "version_id",
        "checksum",
        "sequence",
        "previous_head_digest",
        "head_digest",
        "external_monotonic_floor",
        "snapshot_id",
        "latest_version_id",
        "signer_identity_digest",
        "issued_at",
        "expires_at",
        "self_digest",
        *_COMMON,
    }),
    "controller_anchor_exact_read": frozenset({
        "schema_version",
        "writer_response_digest",
        "request_digest",
        "object_id",
        "version_id",
        "checksum",
        "sequence",
        "head_digest",
        "reader_identity_digest",
        "issued_at",
        "expires_at",
        "self_digest",
        *_COMMON,
    }),
    "controller_anchor_enumeration": frozenset({
        "schema_version",
        "request_digest",
        "sequence",
        "head_digest",
        "external_monotonic_floor",
        "snapshot_id",
        "latest_version_id",
        "writer_response_digests",
        "reader_identity_digest",
        "issued_at",
        "expires_at",
        "self_digest",
        *_COMMON,
    }),
    "controller_anchor_latest": frozenset({
        "schema_version",
        "request_digest",
        "sequence",
        "head_digest",
        "external_monotonic_floor",
        "snapshot_id",
        "latest_version_id",
        "reader_identity_digest",
        "issued_at",
        "expires_at",
        "self_digest",
        *_COMMON,
    }),
}
_CHAIN_KEYS = frozenset({
    "schema_version",
    "status",
    "failure_code",
    "outbox_prepared_state_digest",
    "intent",
    "result",
    "postcheck",
    "rollback",
    "proof",
    "session_lock",
    *_COMMON,
})


class ControllerAnchorEffectError(RuntimeError):
    """Fail-closed adapter construction or input error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _seal(value: dict[str, Any]) -> dict[str, Any]:
    artifact = dict(value)
    artifact["self_digest"] = central_validator.artifact_self_digest(artifact)
    return artifact


def _trusted_now() -> datetime:
    """Read code-owned aware UTC; public APIs cannot supply or replace time."""

    return datetime.now(timezone.utc)


def _observe_manifest_from_root(
    *,
    store: recovery_store.S2_5RecoveryStore,
    root: dict[str, Any],
    source_head: str,
) -> dict[str, Any]:
    snapshot = store._snapshot(root["fd"], root)
    manifest = store._existing_manifest(snapshot, source_head=source_head)
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != controller.MANIFEST_SCHEMA
    ):
        raise ControllerAnchorEffectError(
            "anchor_effect_current_v2_manifest_absent"
        )
    return {
        "manifest": manifest,
        "manifest_discriminator_digest": store._prior_discriminator(snapshot),
        "state_root_id": snapshot["state_root_id"],
    }


def _fixed_manifest_observation(*, source_head: str) -> dict[str, Any]:
    """Read the exact current manifest from the code-owned fixed POSIX store."""

    driver = recovery_store._FIXED_POSIX_RECOVERY_DRIVER()
    store = recovery_store.S2_5RecoveryStore(driver)
    root: dict[str, Any] | None = None
    try:
        root = store._open_root()
        return _observe_manifest_from_root(
            store=store,
            root=root,
            source_head=source_head,
        )
    except recovery_store.RecoveryStoreError as error:
        raise ControllerAnchorEffectError(
            "anchor_effect_fixed_store_observation_failed"
        ) from error
    finally:
        if root is not None:
            store._close(root.get("fd"))


class _FixedEffectSession:
    """Retain the fixed state root and recovery dual lock through dispatch."""

    def __init__(self, *, source_head: str) -> None:
        self.source_head = source_head
        self.driver = recovery_store._FIXED_POSIX_RECOVERY_DRIVER()
        self.store = recovery_store.S2_5RecoveryStore(self.driver)
        self.lock_outcome, self.lease = (
            recovery_lock._acquire_recovery_dual_lock(
                driver=self.driver,
                source_head=source_head,
                session_class="FIXED_POSIX_RECOVERY_SESSION",
            )
        )
        self.root: dict[str, Any] | None = None
        self.active = False
        self.closed = False
        self.failure_code: str | None = None
        if self.lease is None:
            self.failure_code = self.lock_outcome["result"]["failure_code"]
            return
        self.lease["transaction_active"] = True
        try:
            self.root = self.store._open_root()
            recovery_lock._verify_lease(
                self.lease,
                driver=self.driver,
                source_head=self.source_head,
                require_transaction=True,
            )
            self.active = True
        except (
            recovery_store.RecoveryStoreError,
            recovery_lock.RecoveryDualLockError,
        ) as error:
            self.failure_code = error.code
            self.close()
        except Exception as error:
            self.failure_code = (
                "anchor_effect_session_open_" + type(error).__name__
            )
            self.close()

    def _require_active(self) -> dict[str, Any]:
        if (
            self.active is not True
            or self.lease is None
            or self.root is None
        ):
            raise ControllerAnchorEffectError(
                self.failure_code or "anchor_effect_session_inactive"
            )
        try:
            recovery_lock._verify_lease(
                self.lease,
                driver=self.driver,
                source_head=self.source_head,
                require_transaction=True,
            )
        except recovery_lock.RecoveryDualLockError as error:
            raise ControllerAnchorEffectError(error.code) from error
        return self.root

    def _recheck_root(self, retained: dict[str, Any]) -> None:
        current: dict[str, Any] | None = None
        try:
            current = self.store._open_root()
            if not recovery_store._same_root(current, retained):
                raise ControllerAnchorEffectError(
                    "anchor_effect_state_root_replaced"
                )
        except recovery_store.RecoveryStoreError as error:
            raise ControllerAnchorEffectError(
                "anchor_effect_state_root_recheck_failed"
            ) from error
        finally:
            if current is not None:
                self.store._close(current.get("fd"))

    def observe(self) -> dict[str, Any]:
        retained = self._require_active()
        self._recheck_root(retained)
        try:
            return _observe_manifest_from_root(
                store=self.store,
                root=retained,
                source_head=self.source_head,
            )
        except recovery_store.RecoveryStoreError as error:
            raise ControllerAnchorEffectError(
                "anchor_effect_fixed_store_observation_failed"
            ) from error

    def guard_effect(
        self, *, expected_observation: dict[str, Any]
    ) -> None:
        current = self.observe()
        if current != expected_observation:
            raise ControllerAnchorEffectError(
                "anchor_effect_manifest_changed_before_effect"
            )

    def close(self) -> dict[str, Any]:
        if self.closed:
            return self.lock_outcome
        if self.root is not None:
            try:
                self.driver.close(fd=self.root["fd"])
            except Exception:
                self.failure_code = (
                    "anchor_effect_state_root_release_incomplete"
                )
            self.root = None
        self.active = False
        if self.lease is not None:
            self.lease["transaction_active"] = False
            self.lock_outcome["rollback"] = recovery_lock._release_lease(
                self.lease
            )
        self.closed = True
        return self.lock_outcome


def _open_fixed_effect_session(*, source_head: str) -> _FixedEffectSession:
    return _FixedEffectSession(source_head=source_head)


def derive_controller_anchor_head(
    *,
    request_digest: str,
    sequence: int,
    previous_head_digest: str | None,
    checksum: str,
) -> str:
    """Derive the local append head from the exact request and predecessor."""

    return central_validator.canonical_digest({
        "schema_version": "s2_5_recovery_controller_anchor_head_v1",
        "request_digest": request_digest,
        "sequence": sequence,
        "previous_head_digest": previous_head_digest,
        "checksum": checksum,
    })


@lru_cache(maxsize=None)
def _schema(schema_version: str) -> dict[str, Any]:
    if schema_version not in _ARTIFACT_SCHEMAS:
        raise ControllerAnchorEffectError("anchor_effect_schema_unknown")
    try:
        value = json.loads(
            (_SCHEMA_DIR / f"{schema_version}.schema.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, ValueError) as error:
        raise ControllerAnchorEffectError(
            "anchor_effect_schema_unavailable"
        ) from error
    if not isinstance(value, dict):
        raise ControllerAnchorEffectError("anchor_effect_schema_invalid")
    return value


def validate_effect_artifact(artifact: Any) -> list[str]:
    """Validate one typed local adapter artifact."""

    if not isinstance(artifact, dict):
        return ["anchor effect artifact must be an object"]
    schema_version = artifact.get("schema_version")
    if not isinstance(schema_version, str) or schema_version not in (
        _ARTIFACT_SCHEMAS
    ):
        return ["anchor effect artifact schema_version is unknown"]
    try:
        schema = _schema(schema_version)
    except ControllerAnchorEffectError as error:
        return [error.code]
    errors = schema_subset_errors(artifact, schema, schema)
    if artifact.get("self_digest") != central_validator.artifact_self_digest(
        artifact
    ):
        errors.append("anchor effect artifact self_digest does not re-derive")
    for key, expected in _COMMON.items():
        actual = artifact.get(key)
        if type(actual) is not type(expected) or actual != expected:
            errors.append(f"anchor effect artifact {key} differs from profile")
    return errors


def _validate_session_lock(outcome: Any) -> list[str]:
    if outcome is None:
        return []
    if not isinstance(outcome, dict) or set(outcome) != {
        "status",
        "intent",
        "result",
        "postcheck",
        "rollback",
    }:
        return ["session lock outcome fields are not closed"]
    errors: list[str] = []
    for name in ("intent", "result", "postcheck", "rollback"):
        errors.extend(
            f"session_lock.{name}: {error}"
            for error in recovery_lock.validate_local_artifact(
                outcome.get(name)
            )
        )
    intent = outcome.get("intent", {})
    result = outcome.get("result", {})
    postcheck = outcome.get("postcheck", {})
    rollback = outcome.get("rollback", {})
    if outcome.get("status") != result.get("status"):
        errors.append("session lock outcome status differs from result")
    if result.get("intent_digest") != intent.get("self_digest"):
        errors.append("session lock result does not bind intent")
    if postcheck.get("result_digest") != result.get("self_digest"):
        errors.append("session lock postcheck does not bind result")
    if (
        rollback.get("intent_digest") != intent.get("self_digest")
        or rollback.get("result_digest") != result.get("self_digest")
    ):
        errors.append("session lock rollback does not bind acquisition")
    return errors


def validate_effect_chain(chain: Any) -> list[str]:
    """Validate a closed intent/result/postcheck/rollback adapter chain."""

    if not isinstance(chain, dict):
        return ["anchor effect chain must be an object"]
    errors: list[str] = []
    if set(chain) != _CHAIN_KEYS:
        errors.append("anchor effect chain fields are not closed")
        return errors
    if chain.get("schema_version") != (
        "s2_5_recovery_anchor_effect_chain_v1"
    ):
        errors.append("anchor effect chain schema_version is invalid")
    for key, expected in _COMMON.items():
        actual = chain.get(key)
        if type(actual) is not type(expected) or actual != expected:
            errors.append(f"anchor effect chain {key} differs from profile")
    artifacts: dict[str, dict[str, Any]] = {}
    for name in ("intent", "result", "postcheck", "rollback"):
        value = chain.get(name)
        errors.extend(
            f"{name}: {error}" for error in validate_effect_artifact(value)
        )
        if isinstance(value, dict):
            artifacts[name] = value
    intent = artifacts.get("intent", {})
    result = artifacts.get("result", {})
    postcheck = artifacts.get("postcheck", {})
    rollback = artifacts.get("rollback", {})
    session_lock = chain.get("session_lock")
    errors.extend(_validate_session_lock(session_lock))
    state_digest = chain.get("outbox_prepared_state_digest")
    if intent.get("outbox_prepared_state_digest") != state_digest:
        errors.append("intent does not bind exact pending controller state")
    if result.get("intent_digest") != intent.get("self_digest"):
        errors.append("result does not bind exact intent")
    if postcheck.get("result_digest") != result.get("self_digest"):
        errors.append("postcheck does not bind exact result")
    if (
        rollback.get("intent_digest") != intent.get("self_digest")
        or rollback.get("result_digest") != result.get("self_digest")
        or rollback.get("postcheck_digest") != postcheck.get("self_digest")
    ):
        errors.append("rollback does not bind the exact effect chain")
    if chain.get("status") == "PRECHECK_REJECTED":
        if chain.get("proof") is not None:
            errors.append("precheck rejection cannot carry anchor proof")
        if (
            result.get("status") != "PRECHECK_REJECTED"
            or result.get("effect_attempted") is not False
            or result.get("effect_confirmed") is not False
            or postcheck.get("status") != "NOT_PERFORMED"
            or rollback.get("status") != "NOT_REQUIRED"
        ):
            errors.append("precheck rejection chain semantics are invalid")
    elif chain.get("status") == (
        STATUS_UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED
    ):
        proof = chain.get("proof")
        if not isinstance(proof, dict):
            errors.append("executed chain requires exact controller proof")
        else:
            errors.extend(
                f"proof: {error}"
                for error in controller.validate_controller_artifact(proof)
            )
            if proof.get("outbox_prepared_state_digest") != state_digest:
                errors.append("proof does not bind exact pending state")
            if (
                proof.get("object_id") != result.get("object_id")
                or proof.get("version_id") != result.get("version_id")
                or proof.get("checksum") != result.get("checksum")
                or proof.get("sequence") != result.get("sequence")
                or proof.get("head_digest") != result.get("head_digest")
            ):
                errors.append("proof differs from exact effect result")
            if (
                proof.get("exact_readback_digest")
                != postcheck.get("exact_readback_digest")
                or proof.get("enumeration_digest")
                != postcheck.get("enumeration_digest")
                or proof.get("latest_digest")
                != postcheck.get("latest_digest")
            ):
                errors.append("proof differs from exact independent postcheck")
        if (
            result.get("status") not in {"APPENDED", "IDEMPOTENT_EXACT"}
            or result.get("effect_attempted") is not True
            or result.get("effect_confirmed") is not True
            or postcheck.get("status") != "LOCAL_EXACT_UNVERIFIED"
            or rollback.get("status") != "NOT_REQUIRED"
        ):
            errors.append("executed local chain semantics are invalid")
    elif chain.get("status") == "RECOVERY_REQUIRED":
        if chain.get("proof") is not None:
            errors.append("recovery-required chain cannot carry anchor proof")
        if (
            result.get("status") != "RECOVERY_REQUIRED"
            or result.get("effect_attempted") is not True
            or result.get("effect_confirmed") is not False
            or postcheck.get("status") != "RECOVERY_REQUIRED"
            or rollback.get("status") != "RECOVERY_REQUIRED"
            or rollback.get("operator_action_required") is not True
        ):
            errors.append("recovery-required chain semantics are invalid")
    else:
        errors.append("anchor effect chain status is invalid")
    effect_attempted = result.get("effect_attempted")
    if isinstance(session_lock, dict) and (
        session_lock.get("intent", {}).get("source_head")
        != intent.get("source_head")
    ):
        errors.append("session lock does not bind the anchor source head")
    if effect_attempted is True:
        if not isinstance(session_lock, dict):
            errors.append("attempted anchor effect requires a session lock")
        elif (
            session_lock.get("status") != recovery_lock.STATUS_ACQUIRED
            or session_lock.get("postcheck", {}).get("status") != "PASS"
            or session_lock.get("rollback", {}).get("status") != "RELEASED"
        ):
            errors.append(
                "attempted anchor effect requires acquired and released dual lock"
            )
    elif isinstance(session_lock, dict) and (
        session_lock.get("status") == recovery_lock.STATUS_ACQUIRED
        and session_lock.get("rollback", {}).get("status") != "RELEASED"
    ):
        errors.append("acquired precheck session lock was not released")
    return errors


def _failure_code(
    admission_errors: list[str], transition_errors: list[str]
) -> str:
    if any("pending transition is expired" in item for item in transition_errors):
        return "pending_transition_expired"
    if any(
        "pending transition is not yet valid" in item
        for item in transition_errors
    ):
        return "pending_transition_not_yet_valid"
    if admission_errors:
        return "recovery_admission_not_fresh"
    return "pending_transition_invalid"


class ControllerAnchorEffectAdapter:
    """Dispatch only a fresh, exact v2 controller outbox."""

    def __init__(self, *, writer: Any, reader: Any, verifier: Any) -> None:
        capabilities = (writer, reader, verifier)
        if len({id(item) for item in capabilities}) != len(capabilities):
            raise ControllerAnchorEffectError(
                "anchor_effect_capabilities_must_be_distinct"
            )
        required = (
            (writer, "compare_append_controller"),
            (reader, "read_controller_exact"),
            (reader, "enumerate_controller_chain"),
            (reader, "read_controller_latest"),
            (verifier, "verify_signed"),
        )
        if any(
            not hasattr(capability, method)
            or not callable(getattr(capability, method))
            for capability, method in required
        ):
            raise ControllerAnchorEffectError(
                "anchor_effect_capability_invalid"
            )
        self._writer = writer
        self._reader = reader
        self._verifier = verifier

    def _now(self) -> datetime:
        try:
            moment = _trusted_now()
        except Exception as error:
            raise ControllerAnchorEffectError(
                "anchor_effect_clock_unavailable"
            ) from error
        if not isinstance(moment, datetime) or moment.tzinfo is None:
            raise ControllerAnchorEffectError(
                "anchor_effect_clock_not_aware_datetime"
            )
        return moment

    @staticmethod
    def _protocol_time(value: Any, *, code: str) -> datetime:
        if not isinstance(value, str):
            raise ControllerAnchorEffectError(code)
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ControllerAnchorEffectError(code) from error
        if parsed.tzinfo is None:
            raise ControllerAnchorEffectError(code)
        return parsed

    def _verify_protocol(
        self,
        envelope: Any,
        *,
        purpose: str,
        schema_version: str,
        identity_field: str,
        identity_digest: str,
        moment: datetime,
    ) -> dict[str, Any]:
        try:
            payload = self._verifier.verify_signed(
                purpose=purpose, envelope=envelope
            )
        except Exception as error:
            raise ControllerAnchorEffectError(
                f"{purpose}_verification_failed"
            ) from error
        if (
            not isinstance(payload, dict)
            or set(payload) != _PROTOCOL_KEYS[purpose]
            or payload.get("schema_version") != schema_version
            or payload.get(identity_field) != identity_digest
            or payload.get("self_digest")
            != central_validator.artifact_self_digest(payload)
        ):
            raise ControllerAnchorEffectError(
                f"{purpose}_payload_invalid"
            )
        for key, expected in _COMMON.items():
            actual = payload.get(key)
            if type(actual) is not type(expected) or actual != expected:
                raise ControllerAnchorEffectError(
                    f"{purpose}_boundary_invalid"
                )
        issued = self._protocol_time(
            payload.get("issued_at"), code=f"{purpose}_issued_at_invalid"
        )
        expires = self._protocol_time(
            payload.get("expires_at"), code=f"{purpose}_expires_at_invalid"
        )
        if (
            expires <= issued
            or (expires - issued).total_seconds() > 300
            or moment < issued
            or moment > expires
        ):
            raise ControllerAnchorEffectError(f"{purpose}_not_fresh")
        return payload

    @staticmethod
    def _decode_pending(
        state: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        errors = controller.validate_controller_artifact(state)
        if errors or not isinstance(state, dict):
            raise ControllerAnchorEffectError(
                "anchor_effect_pending_state_invalid"
            )
        subject = state.get("candidate_subject")
        outbox = state.get("pending_outbox")
        if (
            not isinstance(subject, dict)
            or subject.get("anchor_progress") != "OUTBOX_PREPARED"
            or not isinstance(outbox, dict)
        ):
            raise ControllerAnchorEffectError(
                "anchor_effect_pending_outbox_absent"
            )
        try:
            request = json.loads(outbox["prepared_payload_json"])
        except (KeyError, TypeError, ValueError) as error:
            raise ControllerAnchorEffectError(
                "anchor_effect_request_invalid"
            ) from error
        if (
            not isinstance(request, dict)
            or _canonical_json(request) != outbox["prepared_payload_json"]
        ):
            raise ControllerAnchorEffectError(
                "anchor_effect_request_not_exact"
            )
        return outbox, request

    @staticmethod
    def _intent(
        state: dict[str, Any],
        outbox: dict[str, Any],
        request: dict[str, Any],
        manifest_discriminator_digest: str,
        moment: datetime,
    ) -> dict[str, Any]:
        return _seal({
            "schema_version": "s2_5_recovery_anchor_effect_intent_v1",
            "outbox_prepared_state_digest": state["self_digest"],
            "manifest_discriminator_digest": manifest_discriminator_digest,
            "outbox_digest": outbox["self_digest"],
            "transition_digest": outbox["transition_digest"],
            "request_digest": outbox["request_digest"],
            "idempotency_key": outbox["idempotency_key"],
            "source_head": request["source_head"],
            "start_id": request["start_id"],
            "phase": request["phase"],
            "candidate_external_sequence": request[
                "candidate_external_sequence"
            ],
            "checked_at": moment.isoformat(),
            **_COMMON,
        })

    @staticmethod
    def _precheck_rejection(
        state: dict[str, Any],
        intent: dict[str, Any],
        *,
        code: str,
        moment: datetime,
        session_lock: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = _seal({
            "schema_version": "s2_5_recovery_anchor_effect_result_v1",
            "intent_digest": intent["self_digest"],
            "request_digest": intent["request_digest"],
            "status": "PRECHECK_REJECTED",
            "effect_attempted": False,
            "effect_confirmed": False,
            "writer_response_digest": None,
            "object_id": None,
            "version_id": None,
            "checksum": None,
            "sequence": None,
            "head_digest": None,
            "failure_code": code,
            "completed_at": moment.isoformat(),
            **_COMMON,
        })
        postcheck = _seal({
            "schema_version": "s2_5_recovery_anchor_effect_postcheck_v1",
            "result_digest": result["self_digest"],
            "status": "NOT_PERFORMED",
            "exact_readback_digest": None,
            "enumeration_digest": None,
            "latest_digest": None,
            "appended_entry_present": False,
            "latest_advanced": False,
            "checked_at": moment.isoformat(),
            "failure_code": code,
            **_COMMON,
        })
        rollback = _seal({
            "schema_version": "s2_5_recovery_anchor_effect_rollback_v1",
            "intent_digest": intent["self_digest"],
            "result_digest": result["self_digest"],
            "postcheck_digest": postcheck["self_digest"],
            "status": "NOT_REQUIRED",
            "deletion_attempted": False,
            "immutable_anchor_deleted": False,
            "operator_action_required": False,
            "reason": None,
            "completed_at": moment.isoformat(),
            **_COMMON,
        })
        chain = {
            "schema_version": "s2_5_recovery_anchor_effect_chain_v1",
            "status": "PRECHECK_REJECTED",
            "failure_code": code,
            "outbox_prepared_state_digest": state["self_digest"],
            "intent": intent,
            "result": result,
            "postcheck": postcheck,
            "rollback": rollback,
            "proof": None,
            "session_lock": session_lock,
            **_COMMON,
        }
        return chain

    @staticmethod
    def _effect_recovery(
        state: dict[str, Any],
        intent: dict[str, Any],
        *,
        code: str,
        moment: datetime,
        session_lock: dict[str, Any],
    ) -> dict[str, Any]:
        result = _seal({
            "schema_version": "s2_5_recovery_anchor_effect_result_v1",
            "intent_digest": intent["self_digest"],
            "request_digest": intent["request_digest"],
            "status": "RECOVERY_REQUIRED",
            "effect_attempted": True,
            "effect_confirmed": False,
            "writer_response_digest": None,
            "object_id": None,
            "version_id": None,
            "checksum": None,
            "sequence": None,
            "head_digest": None,
            "failure_code": code,
            "completed_at": moment.isoformat(),
            **_COMMON,
        })
        postcheck = _seal({
            "schema_version": "s2_5_recovery_anchor_effect_postcheck_v1",
            "result_digest": result["self_digest"],
            "status": "RECOVERY_REQUIRED",
            "exact_readback_digest": None,
            "enumeration_digest": None,
            "latest_digest": None,
            "appended_entry_present": False,
            "latest_advanced": False,
            "checked_at": moment.isoformat(),
            "failure_code": code,
            **_COMMON,
        })
        rollback = _seal({
            "schema_version": "s2_5_recovery_anchor_effect_rollback_v1",
            "intent_digest": intent["self_digest"],
            "result_digest": result["self_digest"],
            "postcheck_digest": postcheck["self_digest"],
            "status": "RECOVERY_REQUIRED",
            "deletion_attempted": False,
            "immutable_anchor_deleted": False,
            "operator_action_required": True,
            "reason": code,
            "completed_at": moment.isoformat(),
            **_COMMON,
        })
        chain = {
            "schema_version": "s2_5_recovery_anchor_effect_chain_v1",
            "status": "RECOVERY_REQUIRED",
            "failure_code": code,
            "outbox_prepared_state_digest": state["self_digest"],
            "intent": intent,
            "result": result,
            "postcheck": postcheck,
            "rollback": rollback,
            "proof": None,
            "session_lock": session_lock,
            **_COMMON,
        }
        return chain

    def _execute_fresh(
        self,
        state: dict[str, Any],
        outbox: dict[str, Any],
        request: dict[str, Any],
        intent: dict[str, Any],
        moment: datetime,
        confirmed_candidate_subject_digest: str,
        session_lock: dict[str, Any],
    ) -> dict[str, Any]:
        envelope = self._writer.compare_append_controller(request=request)
        response = self._verify_protocol(
            envelope,
            purpose="controller_anchor_compare_append",
            schema_version=(
                "s2_5_recovery_anchor_compare_append_response_v2"
            ),
            identity_field="signer_identity_digest",
            identity_digest=WRITER_IDENTITY_DIGEST,
            moment=moment,
        )
        expected_response = {
            "request_digest": outbox["request_digest"],
            "prepared_payload_digest": outbox["prepared_payload_digest"],
            "idempotency_key": outbox["idempotency_key"],
            "sequence": outbox["candidate_external_sequence"],
            "previous_head_digest": outbox[
                "expected_external_head_digest"
            ],
            "checksum": outbox["prepared_payload_digest"],
        }
        if any(
            response.get(key) != expected
            for key, expected in expected_response.items()
        ):
            raise ControllerAnchorEffectError(
                "controller_anchor_compare_append_binding_invalid"
            )
        floor = response.get("external_monotonic_floor")
        if (
            response.get("status") not in {"APPENDED", "IDEMPOTENT_EXACT"}
            or not isinstance(response.get("object_id"), str)
            or not response["object_id"]
            or not isinstance(response.get("version_id"), str)
            or not response["version_id"]
            or response.get("head_digest")
            != derive_controller_anchor_head(
                request_digest=outbox["request_digest"],
                sequence=outbox["candidate_external_sequence"],
                previous_head_digest=outbox[
                    "expected_external_head_digest"
                ],
                checksum=outbox["prepared_payload_digest"],
            )
            or not isinstance(floor, int)
            or isinstance(floor, bool)
            or floor < outbox["candidate_external_sequence"]
            or response.get("latest_version_id") != response["version_id"]
        ):
            raise ControllerAnchorEffectError(
                "controller_anchor_compare_append_result_invalid"
            )
        exact = self._verify_protocol(
            self._reader.read_controller_exact(
                object_id=response["object_id"],
                version_id=response["version_id"],
            ),
            purpose="controller_anchor_exact_read",
            schema_version="s2_5_recovery_anchor_exact_read_v2",
            identity_field="reader_identity_digest",
            identity_digest=READER_IDENTITY_DIGEST,
            moment=moment,
        )
        exact_expected = {
            "writer_response_digest": response["self_digest"],
            "request_digest": outbox["request_digest"],
            "object_id": response["object_id"],
            "version_id": response["version_id"],
            "checksum": response["checksum"],
            "sequence": response["sequence"],
            "head_digest": response["head_digest"],
        }
        if any(
            exact.get(key) != expected
            for key, expected in exact_expected.items()
        ):
            raise ControllerAnchorEffectError(
                "controller_anchor_exact_read_binding_invalid"
            )
        enumeration = self._verify_protocol(
            self._reader.enumerate_controller_chain(
                snapshot_id=response["snapshot_id"]
            ),
            purpose="controller_anchor_enumeration",
            schema_version="s2_5_recovery_anchor_enumeration_v2",
            identity_field="reader_identity_digest",
            identity_digest=READER_IDENTITY_DIGEST,
            moment=moment,
        )
        latest = self._verify_protocol(
            self._reader.read_controller_latest(),
            purpose="controller_anchor_latest",
            schema_version="s2_5_recovery_anchor_latest_v2",
            identity_field="reader_identity_digest",
            identity_digest=READER_IDENTITY_DIGEST,
            moment=moment,
        )
        common_read_expected = {
            "request_digest": outbox["request_digest"],
            "sequence": response["sequence"],
            "head_digest": response["head_digest"],
            "external_monotonic_floor": response[
                "external_monotonic_floor"
            ],
            "snapshot_id": response["snapshot_id"],
            "latest_version_id": response["latest_version_id"],
        }
        if any(
            enumeration.get(key) != expected
            or latest.get(key) != expected
            for key, expected in common_read_expected.items()
        ) or enumeration.get("writer_response_digests") != [
            response["self_digest"]
        ]:
            raise ControllerAnchorEffectError(
                "controller_anchor_chain_readback_invalid"
            )
        result = _seal({
            "schema_version": "s2_5_recovery_anchor_effect_result_v1",
            "intent_digest": intent["self_digest"],
            "request_digest": outbox["request_digest"],
            "status": response["status"],
            "effect_attempted": True,
            "effect_confirmed": True,
            "writer_response_digest": response["self_digest"],
            "object_id": response["object_id"],
            "version_id": response["version_id"],
            "checksum": response["checksum"],
            "sequence": response["sequence"],
            "head_digest": response["head_digest"],
            "failure_code": STATUS_UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED,
            "completed_at": moment.isoformat(),
            **_COMMON,
        })
        postcheck = _seal({
            "schema_version": "s2_5_recovery_anchor_effect_postcheck_v1",
            "result_digest": result["self_digest"],
            "status": "LOCAL_EXACT_UNVERIFIED",
            "exact_readback_digest": exact["self_digest"],
            "enumeration_digest": enumeration["self_digest"],
            "latest_digest": latest["self_digest"],
            "appended_entry_present": True,
            "latest_advanced": True,
            "checked_at": moment.isoformat(),
            "failure_code": STATUS_UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED,
            **_COMMON,
        })
        rollback = _seal({
            "schema_version": "s2_5_recovery_anchor_effect_rollback_v1",
            "intent_digest": intent["self_digest"],
            "result_digest": result["self_digest"],
            "postcheck_digest": postcheck["self_digest"],
            "status": "NOT_REQUIRED",
            "deletion_attempted": False,
            "immutable_anchor_deleted": False,
            "operator_action_required": False,
            "reason": None,
            "completed_at": moment.isoformat(),
            **_COMMON,
        })
        proof = _seal({
            "schema_version": "s2_5_recovery_anchor_proof_v1",
            "outbox_prepared_state_digest": state["self_digest"],
            "outbox_candidate_subject_digest": state[
                "candidate_subject_digest"
            ],
            "confirmed_candidate_subject_digest": (
                confirmed_candidate_subject_digest
            ),
            "transition_json": outbox["transition_json"],
            "transition_digest": outbox["transition_digest"],
            "outbox_json": _canonical_json(outbox),
            "outbox_digest": outbox["self_digest"],
            "idempotency_key": outbox["idempotency_key"],
            "source_head": request["source_head"],
            "start_id": request["start_id"],
            "phase": request["phase"],
            "object_id": response["object_id"],
            "version_id": response["version_id"],
            "checksum": response["checksum"],
            "sequence": response["sequence"],
            "previous_head_digest": response["previous_head_digest"],
            "head_digest": response["head_digest"],
            "external_monotonic_floor": response[
                "external_monotonic_floor"
            ],
            "snapshot_id": response["snapshot_id"],
            "latest_version_id": response["latest_version_id"],
            "exact_readback_digest": exact["self_digest"],
            "enumeration_digest": enumeration["self_digest"],
            "latest_digest": latest["self_digest"],
            "writer_identity_digest": WRITER_IDENTITY_DIGEST,
            "reader_identity_digest": READER_IDENTITY_DIGEST,
            "verifier_identity_digest": VERIFIER_IDENTITY_DIGEST,
            "immutable_readback": False,
            "full_chain_valid": False,
            "identity_distinct": False,
            "authenticated_response": False,
            "failure_code": STATUS_UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED,
            **_COMMON,
        })
        chain = {
            "schema_version": "s2_5_recovery_anchor_effect_chain_v1",
            "status": STATUS_UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED,
            "failure_code": STATUS_UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED,
            "outbox_prepared_state_digest": state["self_digest"],
            "intent": intent,
            "result": result,
            "postcheck": postcheck,
            "rollback": rollback,
            "proof": proof,
            "session_lock": session_lock,
            **_COMMON,
        }
        return chain

    def _execute_pending(
        self,
        state: dict[str, Any],
        *,
        confirmed_candidate_subject_digest: str,
        source_head: str,
        manifest: dict[str, Any],
        manifest_discriminator_digest: str,
    ) -> dict[str, Any]:
        outbox, request = self._decode_pending(state)
        moment = self._now()
        intent = self._intent(
            state,
            outbox,
            request,
            manifest_discriminator_digest,
            moment,
        )
        admission_errors = controller.validate_fresh_controller_admission(
            state, trusted_now=moment
        )
        transition_errors = controller.validate_fresh_pending_transition(
            state, trusted_now=moment
        )
        if admission_errors or transition_errors:
            chain = self._precheck_rejection(
                state,
                intent,
                code=_failure_code(admission_errors, transition_errors),
                moment=moment,
            )
            errors = validate_effect_chain(chain)
            if errors:
                raise ControllerAnchorEffectError(
                    "anchor_effect_generated_chain_invalid"
                )
            return chain

        session = _open_fixed_effect_session(source_head=source_head)
        chain: dict[str, Any] | None = None
        try:
            if session.active is not True:
                chain = self._precheck_rejection(
                    state,
                    intent,
                    code=(
                        getattr(session, "failure_code", None)
                        or "anchor_effect_session_unavailable"
                    ),
                    moment=moment,
                    session_lock=session.lock_outcome,
                )
            else:
                try:
                    current = session.observe()
                    if (
                        current.get("manifest_discriminator_digest")
                        != manifest_discriminator_digest
                        or current.get("state_root_id")
                        != manifest.get("state_root_id")
                        or current.get("manifest") != manifest
                    ):
                        raise ControllerAnchorEffectError(
                            "anchor_effect_manifest_changed_before_effect"
                        )
                    session.guard_effect(expected_observation=current)
                except ControllerAnchorEffectError as error:
                    chain = self._precheck_rejection(
                        state,
                        intent,
                        code=error.code,
                        moment=moment,
                        session_lock=session.lock_outcome,
                    )
                if chain is None:
                    moment = self._now()
                    intent = self._intent(
                        state,
                        outbox,
                        request,
                        manifest_discriminator_digest,
                        moment,
                    )
                    admission_errors = (
                        controller.validate_fresh_controller_admission(
                            state, trusted_now=moment
                        )
                    )
                    transition_errors = (
                        controller.validate_fresh_pending_transition(
                            state, trusted_now=moment
                        )
                    )
                    if admission_errors or transition_errors:
                        chain = self._precheck_rejection(
                            state,
                            intent,
                            code=_failure_code(
                                admission_errors, transition_errors
                            ),
                            moment=moment,
                            session_lock=session.lock_outcome,
                        )
                    else:
                        try:
                            chain = self._execute_fresh(
                                state,
                                outbox,
                                request,
                                intent,
                                moment,
                                confirmed_candidate_subject_digest,
                                session.lock_outcome,
                            )
                        except ControllerAnchorEffectError as error:
                            chain = self._effect_recovery(
                                state,
                                intent,
                                code=error.code,
                                moment=moment,
                                session_lock=session.lock_outcome,
                            )
                        except Exception:
                            chain = self._effect_recovery(
                                state,
                                intent,
                                code="anchor_effect_dispatch_failed",
                                moment=moment,
                                session_lock=session.lock_outcome,
                            )
        finally:
            closed_lock = session.close()
            if chain is not None:
                chain["session_lock"] = closed_lock
        if chain is None:
            raise ControllerAnchorEffectError(
                "anchor_effect_session_closed_without_chain"
            )
        errors = validate_effect_chain(chain)
        if errors:
            raise ControllerAnchorEffectError(
                "anchor_effect_generated_chain_invalid"
            )
        return chain

    def execute_pending_state(self, state: dict[str, Any]) -> dict[str, Any]:
        """Refuse caller-supplied raw state as an effect entry."""

        raise ControllerAnchorEffectError(
            "anchor_effect_fixed_profile_required"
        )

    def execute_pending_manifest(
        self, manifest: dict[str, Any]
    ) -> dict[str, Any]:
        """Refuse caller-supplied raw manifest as an effect entry."""

        raise ControllerAnchorEffectError(
            "anchor_effect_fixed_profile_required"
        )

    def execute_fixed_profile(
        self, *, source_head: str
    ) -> dict[str, Any]:
        """Execute only the twice-observed current fixed-store manifest."""

        observed = _fixed_manifest_observation(source_head=source_head)
        manifest = observed.get("manifest")
        errors = controller.validate_controller_artifact(manifest)
        if (
            errors
            or not isinstance(manifest, dict)
            or manifest.get("schema_version") != controller.MANIFEST_SCHEMA
        ):
            raise ControllerAnchorEffectError(
                "anchor_effect_pending_manifest_invalid"
            )
        state = manifest.get("controller_state")
        if not isinstance(state, dict):
            raise ControllerAnchorEffectError(
                "anchor_effect_pending_state_invalid"
            )
        subject = state.get("candidate_subject")
        if not isinstance(subject, dict):
            raise ControllerAnchorEffectError(
                "anchor_effect_pending_subject_invalid"
            )
        successor_subject = dict(subject)
        successor_subject.update({
            "anchor_progress": "PROOF_ATTACHED_UNVERIFIED",
            "generation": subject.get("generation", 0) + 1,
            "previous_controller_state_digest": state.get("self_digest"),
            "previous_manifest_digest": manifest.get("self_digest"),
        })
        return self._execute_pending(
            state,
            confirmed_candidate_subject_digest=(
                controller.derive_candidate_subject_digest(
                    successor_subject
                )
            ),
            source_head=source_head,
            manifest=manifest,
            manifest_discriminator_digest=observed[
                "manifest_discriminator_digest"
            ],
        )
