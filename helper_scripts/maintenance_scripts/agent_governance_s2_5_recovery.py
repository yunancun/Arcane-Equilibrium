#!/usr/bin/env python3
"""S2.5 recovery contract leaf.

This module is source/contract only.  It binds a recovery chain to one unresolved
state, exact state-root generation, journal/replay heads, consume-once authority,
trusted off-root anchor reference, host/source/process identity, rollback, and an
independent postcheck.  It performs no command, process, service, or durable-state
operation; materializing the off-root anchor and unresolved manifest is a later slice.
"""

from __future__ import annotations

import copy
import hmac
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import agent_governance_aiml_trusted_host as _trusted_host
from aiml_gate_receipt_schema_core import (
    _canonical_bytes,
    _parse_timestamp,
    artifact_self_digest,
    canonical_digest,
)

RECOVERY_SCHEMA_VERSIONS = frozenset({
    "s2_5_recovery_intent_v1",
    "s2_5_recovery_rollback_v1",
    "s2_5_recovery_result_v1",
    "s2_5_recovery_postcheck_v1",
})
RECOVERY_ACTIONS = frozenset({
    "ROLLBACK_TO_PRE_STATE",
    "REPLAY_JOURNAL",
    "ABORT_AND_PRESERVE_LATCH",
})
RECOVERY_SIGNER_IDENTITY = "aiml-s2-5-recovery-operator-v1"
RECOVERY_SIGNATURE_NAMESPACE = "arcane-equilibrium-aiml-s2-5-recovery"
RECOVERY_ANCHOR_SIGNER_IDENTITY = "aiml-s2-5-recovery-anchor-owner-v1"
RECOVERY_ANCHOR_SIGNATURE_NAMESPACE = (
    "arcane-equilibrium-aiml-s2-5-recovery-anchor"
)
RECOVERY_CONSUMPTION_SIGNER_IDENTITY = (
    "aiml-s2-5-recovery-consumption-ledger-v1"
)
RECOVERY_CONSUMPTION_SIGNATURE_NAMESPACE = (
    "arcane-equilibrium-aiml-s2-5-recovery-consumption"
)
RECOVERY_ACTOR_CAPTURE_SIGNER_IDENTITY = (
    "aiml-s2-5-recovery-actor-attestor-v1"
)
RECOVERY_ACTOR_CAPTURE_SIGNATURE_NAMESPACE = (
    "arcane-equilibrium-aiml-s2-5-recovery-actor-capture"
)
RECOVERY_VERIFIER_CAPTURE_SIGNER_IDENTITY = (
    "aiml-s2-5-recovery-independent-verifier-v1"
)
RECOVERY_VERIFIER_CAPTURE_SIGNATURE_NAMESPACE = (
    "arcane-equilibrium-aiml-s2-5-recovery-verifier-capture"
)
# Each recovery capability has a distinct fixed off-repository trust root.  No
# public builder accepts a key, path, profile, or loader callback.
RECOVERY_AUTHORIZATION_TRUST_ROOT_PUBLIC_KEY_PATH = Path(
    "/etc/arcane-equilibrium/trust/s2-5-recovery-authorization.pub"
)
RECOVERY_AUTHORIZATION_TRUST_ROOT_FINGERPRINT = (
    "SHA256:sJ9ORYOXbpR9NqrNxpPXyQcliBG1j/idb9lLzrTPRdc"
)
RECOVERY_ANCHOR_TRUST_ROOT_PUBLIC_KEY_PATH = Path(
    "/etc/arcane-equilibrium/trust/s2-5-recovery-anchor.pub"
)
RECOVERY_ANCHOR_TRUST_ROOT_FINGERPRINT = (
    "SHA256:RUYp2kjHqzfmMSWnHFOlxBBj7vS9ws+OPAeJNKTUeLA"
)
RECOVERY_CONSUMPTION_TRUST_ROOT_PUBLIC_KEY_PATH = Path(
    "/etc/arcane-equilibrium/trust/s2-5-recovery-consumption.pub"
)
RECOVERY_CONSUMPTION_TRUST_ROOT_FINGERPRINT = (
    "SHA256:zanTk+tXTHROIEqNHC5miSIsd+Z3V3NOdZW/mLz1PcY"
)
RECOVERY_ACTOR_CAPTURE_TRUST_ROOT_PUBLIC_KEY_PATH = Path(
    "/etc/arcane-equilibrium/trust/s2-5-recovery-actor-capture.pub"
)
RECOVERY_ACTOR_CAPTURE_TRUST_ROOT_FINGERPRINT = (
    "SHA256:3u7dOQhWe22HlXBECoqbYC9tje+SZ5AI47Bwy1fZ2aQ"
)
RECOVERY_VERIFIER_CAPTURE_TRUST_ROOT_PUBLIC_KEY_PATH = Path(
    "/etc/arcane-equilibrium/trust/s2-5-recovery-verifier-capture.pub"
)
RECOVERY_VERIFIER_CAPTURE_TRUST_ROOT_FINGERPRINT = (
    "SHA256:cWa7aFhQougPNj98pCDzjvHKKOdaFgKPaEplyZ5zFVA"
)
_BINDING_KEYS = frozenset({
    "task_digest", "unresolved_state_digest", "state_root_identity", "journal_set",
    "replay_ledger_head", "pre_state", "source_head", "host_identity", "authorization",
    "trusted_anchor", "actor_identity", "actor_process", "kernel_binding_digest",
    "admission_digest", "side_effect_class", "production_effect",
    "production_authority", "target_class",
})
_ROOT_KEYS = frozenset({
    "root_id", "root_digest", "generation", "previous_root_digest",
})
_JOURNAL_KEYS = frozenset({"journal_digests", "head_digest"})
_LEDGER_KEYS = frozenset({"entry_count", "tail_digest"})
_STATE_KEYS = frozenset({
    "active_state", "unit_file_state", "n_restarts", "invocation_id",
})
_AUTH_KEYS = frozenset({
    "schema_version", "authorization_id", "authorization_digest", "issued_at",
    "expires_at", "consume_once", "signer_identity", "signer_fingerprint",
    "signature_namespace", "signed_binding", "sshsig_armored",
})
_ANCHOR_KEYS = frozenset({
    "schema_version", "anchor_id", "anchor_digest", "storage_class", "anchor_scope_id",
    "bound_state_root_id", "source_head", "host_identity", "external_sequence",
    "previous_append_head_digest", "append_entry_digest", "append_head_digest",
    "append_only", "immutable_readback", "immutable_readback_digest",
    "append_actor_identity", "readback_verifier_identity", "evidence_class",
    "signer_identity",
    "signer_fingerprint", "signature_namespace", "signed_binding",
    "sshsig_armored", "reference_digest",
})
_ANCHOR_SIGNED_BINDING_KEYS = frozenset({
    "schema_version", "anchor_id", "storage_class", "anchor_scope_id",
    "bound_state_root_id", "source_head", "host_identity", "external_sequence",
    "previous_append_head_digest", "append_entry_digest", "append_head_digest",
    "append_only", "immutable_readback", "immutable_readback_digest",
    "append_actor_identity", "readback_verifier_identity", "evidence_class",
})
_AUTH_BINDING_KEYS = frozenset({
    "action", "task_digest", "unresolved_state_digest", "state_root_identity",
    "journal_set", "replay_ledger_head", "pre_state", "source_head", "host_identity",
    "authorization_id", "issued_at", "expires_at", "trusted_anchor_digest",
    "actor_identity", "actor_process", "kernel_binding_digest", "admission_digest",
    "side_effect_class", "production_effect", "production_authority", "target_class",
})
_CONSUMPTION_KEYS = frozenset({
    "schema_version", "authorization_id", "recovery_id", "recovery_intent_digest",
    "bound_state_root_id", "external_sequence", "previous_append_head_digest",
    "append_entry_digest", "append_head_digest", "append_only", "immutable_readback",
    "immutable_readback_digest", "append_actor_identity",
    "readback_verifier_identity", "evidence_class", "signer_identity",
    "signer_fingerprint", "signature_namespace", "signed_binding",
    "sshsig_armored", "proof_digest",
})
_CONSUMPTION_SIGNED_BINDING_KEYS = frozenset({
    "schema_version", "authorization_id", "recovery_id", "recovery_intent_digest",
    "bound_state_root_id", "external_sequence", "previous_append_head_digest",
    "append_entry_digest", "append_head_digest", "append_only", "immutable_readback",
    "immutable_readback_digest", "append_actor_identity",
    "readback_verifier_identity", "evidence_class",
})
_NODE_KEYS = frozenset({"node_id", "role", "permission", "key_identity"})
_PROCESS_KEYS = frozenset({"uid", "cgroup"})
_CAPTURE_KEYS = frozenset({
    "schema_version", "capture_kind", "source_head", "host_identity",
    "bound_state_root_id", "recovery_id", "recovery_intent_digest",
    "recovery_result_digest", "observed_state", "observed_state_digest",
    "node_identity", "process_identity", "observed_at", "signer_identity",
    "signer_fingerprint", "signature_namespace", "signed_binding",
    "sshsig_armored", "capture_digest",
})
_CAPTURE_SIGNED_BINDING_KEYS = frozenset({
    "schema_version", "capture_kind", "source_head", "host_identity",
    "bound_state_root_id", "recovery_id", "recovery_intent_digest",
    "recovery_result_digest", "observed_state", "observed_state_digest",
    "node_identity", "process_identity", "observed_at",
})
_KERNEL_KEYS = frozenset({
    "schema_version", "source_head", "host_identity", "node_identity",
    "process_identity", "binding_digest",
})
_ADMISSION_KEYS = frozenset({
    "schema_version", "task_digest", "unresolved_state_digest", "state_root_identity",
    "journal_set", "replay_ledger_head", "pre_state", "source_head", "host_identity",
    "admission_digest",
})
_FORBIDDEN_KEYS = frozenset({
    "argv", "command", "raw_command", "shell", "script", "password", "credential",
    "secret", "private_key", "access_token",
})
_SECRET_VALUE_RE = re.compile(
    r"(?:github_pat_|gh[pousr]_[A-Za-z0-9]{12,})"
    r"|(?:access[_-]?token|auth(?:orization)?|client[_-]?secret|password|"
    r"pgpassword|private[_-]?key)\s*[:=]"
    r"|(?:basic|bearer)\s+[A-Za-z0-9._~+/=-]{12,}"
    r"|postgres(?:ql)?://[^\s:/@]+:[^\s:/@]+@",
    re.IGNORECASE,
)


def _without(value: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key not in set(keys)}


def _exact(value: Any, keys: frozenset[str], label: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{label} must be an object"]
    actual = set(value)
    if actual != keys:
        return [
            f"{label} keys are not closed: missing={sorted(keys - actual)}, "
            f"extra={sorted(actual - keys)}"
        ]
    return []


def _sealed(value: Any, digest_key: str, label: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{label} must be an object"]
    expected = canonical_digest(_without(value, digest_key))
    return [] if value.get(digest_key) == expected else [
        f"{label} {digest_key} does not bind the canonical object"
    ]


def _read_fixed_recovery_public_key(path: Path) -> str:
    """Read one code-owned fixed public-key path without following symlinks."""

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("recovery trust root is not a regular file")
        if metadata.st_nlink != 1:
            raise ValueError("recovery trust root must have exactly one hard link")
        if metadata.st_uid not in {0, os.geteuid()}:
            raise ValueError("recovery trust root owner is not trusted")
        if stat.S_IMODE(metadata.st_mode) & 0o022:
            raise ValueError("recovery trust root must not be group/world writable")
        if metadata.st_size < 16 or metadata.st_size > 4096:
            raise ValueError("recovery trust-root public key size is invalid")
        payload = os.read(descriptor, metadata.st_size + 1)
    finally:
        os.close(descriptor)
    try:
        public_key = payload.decode("ascii").strip()
    except UnicodeDecodeError as error:
        raise ValueError("recovery trust root is not ASCII") from error
    parts = public_key.split()
    if len(parts) < 2 or parts[0] != "ssh-ed25519":
        raise ValueError("recovery trust root must be an ssh-ed25519 public key")
    return " ".join(parts[:2])


def _load_recovery_authorization_trust_root_public_key() -> str:
    return _read_fixed_recovery_public_key(
        RECOVERY_AUTHORIZATION_TRUST_ROOT_PUBLIC_KEY_PATH
    )


def _load_recovery_anchor_trust_root_public_key() -> str:
    return _read_fixed_recovery_public_key(
        RECOVERY_ANCHOR_TRUST_ROOT_PUBLIC_KEY_PATH
    )


def _load_recovery_consumption_trust_root_public_key() -> str:
    return _read_fixed_recovery_public_key(
        RECOVERY_CONSUMPTION_TRUST_ROOT_PUBLIC_KEY_PATH
    )


def _load_recovery_actor_capture_trust_root_public_key() -> str:
    return _read_fixed_recovery_public_key(
        RECOVERY_ACTOR_CAPTURE_TRUST_ROOT_PUBLIC_KEY_PATH
    )


def _load_recovery_verifier_capture_trust_root_public_key() -> str:
    return _read_fixed_recovery_public_key(
        RECOVERY_VERIFIER_CAPTURE_TRUST_ROOT_PUBLIC_KEY_PATH
    )


def recovery_anchor_signed_bytes(anchor: dict[str, Any]) -> bytes:
    """Canonical bytes authenticated by the independent anchor-owner key."""

    return _canonical_bytes(anchor["signed_binding"])


def _anchor_errors(anchor: Any, root: Any, binding: dict[str, Any]) -> list[str]:
    errors = _exact(anchor, _ANCHOR_KEYS, "trusted_anchor")
    if not isinstance(anchor, dict):
        return errors
    errors.extend(_exact(
        anchor.get("signed_binding"),
        _ANCHOR_SIGNED_BINDING_KEYS,
        "trusted_anchor signed_binding",
    ))
    errors.extend(_sealed(anchor, "reference_digest", "trusted_anchor"))
    signed = anchor.get("signed_binding")
    if not isinstance(signed, dict):
        return errors
    expected_signed = {
        key: anchor.get(key) for key in _ANCHOR_SIGNED_BINDING_KEYS
    }
    if signed != expected_signed:
        errors.append("trusted anchor signed_binding differs from the exact anchor")
    expected_anchor_digest = canonical_digest(signed)
    if anchor.get("anchor_digest") != expected_anchor_digest:
        errors.append("trusted anchor digest does not bind its signed entry")
    if anchor.get("storage_class") != "INDEPENDENT_OFF_STATE_ROOT":
        errors.append("trusted anchor is not independently stored off the state root")
    if anchor.get("anchor_scope_id") == anchor.get("bound_state_root_id"):
        errors.append("trusted anchor scope must differ from the replaceable state root")
    if not isinstance(root, dict):
        errors.append("trusted anchor cannot bind a malformed state-root identity")
    elif anchor.get("bound_state_root_id") != root.get("root_id"):
        errors.append("trusted anchor does not bind the exact state-root identity")
    if anchor.get("source_head") != binding.get("source_head"):
        errors.append("trusted anchor source_head differs from the recovery binding")
    if anchor.get("host_identity") != binding.get("host_identity"):
        errors.append("trusted anchor host_identity differs from the recovery binding")
    sequence = anchor.get("external_sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        errors.append("trusted anchor external monotonic sequence is invalid")
    expected_head = canonical_digest({
        "external_sequence": sequence,
        "previous_append_head_digest": anchor.get("previous_append_head_digest"),
        "append_entry_digest": anchor.get("append_entry_digest"),
    })
    if anchor.get("append_head_digest") != expected_head:
        errors.append("trusted anchor append-only head does not re-derive")
    if anchor.get("append_only") is not True:
        errors.append("trusted anchor does not prove append-only storage")
    if anchor.get("immutable_readback") is not True:
        errors.append("trusted anchor does not prove immutable readback")
    if anchor.get("immutable_readback_digest") != anchor.get("append_entry_digest"):
        errors.append("trusted anchor immutable readback differs from appended entry")
    if anchor.get("append_actor_identity") == anchor.get("readback_verifier_identity"):
        errors.append("trusted anchor append and readback identities must differ")
    if anchor.get("evidence_class") not in {
        "LOCAL_REPRODUCIBLE", "PLATFORM_OR_EXTERNAL_ATTESTED"
    }:
        errors.append("trusted anchor evidence_class is invalid")
    if anchor.get("signer_identity") != RECOVERY_ANCHOR_SIGNER_IDENTITY:
        errors.append("trusted anchor signer identity is invalid")
    if anchor.get("signature_namespace") != RECOVERY_ANCHOR_SIGNATURE_NAMESPACE:
        errors.append("trusted anchor SSHSIG namespace is invalid")
    errors.extend(_fixed_root_signature_errors(
        signer_fingerprint=anchor.get("signer_fingerprint"),
        signed_bytes=(
            recovery_anchor_signed_bytes(anchor)
            if isinstance(anchor.get("signed_binding"), dict)
            else b""
        ),
        signature=anchor.get("sshsig_armored"),
        identity=RECOVERY_ANCHOR_SIGNER_IDENTITY,
        namespace=RECOVERY_ANCHOR_SIGNATURE_NAMESPACE,
        label="trusted anchor",
    ))
    return errors


def _binding_errors(binding: Any, *, action: str | None = None) -> list[str]:
    errors = _exact(binding, _BINDING_KEYS, "recovery_binding")
    if not isinstance(binding, dict):
        return errors
    root = binding.get("state_root_identity")
    journals = binding.get("journal_set")
    ledger = binding.get("replay_ledger_head")
    pre_state = binding.get("pre_state")
    authorization = binding.get("authorization")
    actor = binding.get("actor_identity")
    process = binding.get("actor_process")
    errors.extend(_exact(root, _ROOT_KEYS, "state_root_identity"))
    errors.extend(_exact(journals, _JOURNAL_KEYS, "journal_set"))
    errors.extend(_exact(ledger, _LEDGER_KEYS, "replay_ledger_head"))
    errors.extend(_exact(pre_state, _STATE_KEYS, "pre_state"))
    errors.extend(_exact(authorization, _AUTH_KEYS, "authorization"))
    errors.extend(_exact(actor, _NODE_KEYS, "bound actor_identity"))
    errors.extend(_exact(process, _PROCESS_KEYS, "bound actor_process"))
    errors.extend(_sealed(authorization, "authorization_digest", "authorization"))
    errors.extend(_anchor_errors(binding.get("trusted_anchor"), root, binding))
    errors.extend(_authorization_errors(binding, action=action))
    if isinstance(journals, dict) and journals.get("head_digest") not in (
        journals.get("journal_digests") if isinstance(journals.get("journal_digests"), list)
        else []
    ):
        errors.append("journal head is not a member of the exact journal set")
    if isinstance(authorization, dict) and authorization.get("consume_once") is not True:
        errors.append("recovery authorization must be consume-once")
    if binding.get("side_effect_class") != "DISPOSABLE_TEST":
        errors.append("recovery is limited to side_effect_class=DISPOSABLE_TEST")
    if binding.get("production_effect") is not False:
        errors.append("recovery production_effect must be false")
    if binding.get("production_authority") is not False:
        errors.append("recovery production_authority must be false")
    if binding.get("target_class") != "disposable_systemd":
        errors.append("recovery target_class must be disposable_systemd")
    return errors


def recovery_authorization_signed_bytes(authorization: dict[str, Any]) -> bytes:
    """Canonical bytes authenticated by the fixed recovery SSHSIG profile."""

    return _canonical_bytes(authorization["signed_binding"])


def _fixed_root_signature_errors(
    *,
    signer_fingerprint: Any,
    signed_bytes: bytes,
    signature: Any,
    identity: str,
    namespace: str,
    label: str,
) -> list[str]:
    """Verify SSHSIG with the fixed trust root selected only by code-owned identity."""

    errors: list[str] = []
    profiles = {
        RECOVERY_SIGNER_IDENTITY: (
            _load_recovery_authorization_trust_root_public_key,
            RECOVERY_AUTHORIZATION_TRUST_ROOT_FINGERPRINT,
        ),
        RECOVERY_ANCHOR_SIGNER_IDENTITY: (
            _load_recovery_anchor_trust_root_public_key,
            RECOVERY_ANCHOR_TRUST_ROOT_FINGERPRINT,
        ),
        RECOVERY_CONSUMPTION_SIGNER_IDENTITY: (
            _load_recovery_consumption_trust_root_public_key,
            RECOVERY_CONSUMPTION_TRUST_ROOT_FINGERPRINT,
        ),
        RECOVERY_ACTOR_CAPTURE_SIGNER_IDENTITY: (
            _load_recovery_actor_capture_trust_root_public_key,
            RECOVERY_ACTOR_CAPTURE_TRUST_ROOT_FINGERPRINT,
        ),
        RECOVERY_VERIFIER_CAPTURE_SIGNER_IDENTITY: (
            _load_recovery_verifier_capture_trust_root_public_key,
            RECOVERY_VERIFIER_CAPTURE_TRUST_ROOT_FINGERPRINT,
        ),
    }
    profile = profiles.get(identity)
    if profile is None:
        return [f"{label} has no code-owned recovery trust profile"]
    loader, expected_fingerprint = profile
    try:
        public_key = loader()
        actual = _trusted_host.ssh_public_key_fingerprint(public_key)
    except (OSError, ValueError) as error:
        return [f"{label} fixed recovery trust root is unavailable or invalid: {error}"]
    if not hmac.compare_digest(actual, str(expected_fingerprint)):
        errors.append(f"{label} fixed recovery trust-root fingerprint mismatch")
    if not hmac.compare_digest(
        str(signer_fingerprint), str(expected_fingerprint)
    ):
        errors.append(f"{label} signer fingerprint is invalid")
    signature_bytes = str(signature or "").encode("ascii", "replace")
    if not _trusted_host._verify_ssh_signature(
        signed_bytes,
        signature_bytes,
        public_key=public_key,
        identity=identity,
        namespace=namespace,
    ):
        errors.append(f"{label} SSHSIG is invalid")
    return errors


def _authorization_errors(
    binding: dict[str, Any], *, action: str | None
) -> list[str]:
    authorization = binding.get("authorization")
    if not isinstance(authorization, dict):
        return ["recovery authorization must be an object"]
    errors = _exact(
        authorization.get("signed_binding"),
        _AUTH_BINDING_KEYS,
        "authorization signed_binding",
    )
    signed = authorization.get("signed_binding")
    if not isinstance(signed, dict):
        return errors
    expected = {
        "action": action,
        "task_digest": binding.get("task_digest"),
        "unresolved_state_digest": binding.get("unresolved_state_digest"),
        "state_root_identity": binding.get("state_root_identity"),
        "journal_set": binding.get("journal_set"),
        "replay_ledger_head": binding.get("replay_ledger_head"),
        "pre_state": binding.get("pre_state"),
        "source_head": binding.get("source_head"),
        "host_identity": binding.get("host_identity"),
        "authorization_id": authorization.get("authorization_id"),
        "issued_at": authorization.get("issued_at"),
        "expires_at": authorization.get("expires_at"),
        "trusted_anchor_digest": binding.get("trusted_anchor", {}).get("anchor_digest"),
        "actor_identity": binding.get("actor_identity"),
        "actor_process": binding.get("actor_process"),
        "kernel_binding_digest": binding.get("kernel_binding_digest"),
        "admission_digest": binding.get("admission_digest"),
        "side_effect_class": binding.get("side_effect_class"),
        "production_effect": binding.get("production_effect"),
        "production_authority": binding.get("production_authority"),
        "target_class": binding.get("target_class"),
    }
    if expected["action"] is None:
        expected["action"] = signed.get("action")
    for key, value in expected.items():
        if signed.get(key) != value:
            errors.append(f"authorization signed_binding.{key} differs from recovery")
    if authorization.get("schema_version") != "s2_5_recovery_authorization_v1":
        errors.append("recovery authorization schema_version is invalid")
    if authorization.get("signer_identity") != RECOVERY_SIGNER_IDENTITY:
        errors.append("recovery authorization signer identity is invalid")
    if authorization.get("signature_namespace") != RECOVERY_SIGNATURE_NAMESPACE:
        errors.append("recovery authorization SSHSIG namespace is invalid")
    try:
        signed_bytes = recovery_authorization_signed_bytes(authorization)
    except (KeyError, TypeError, ValueError):
        signed_bytes = b""
    errors.extend(_fixed_root_signature_errors(
        signer_fingerprint=authorization.get("signer_fingerprint"),
        signed_bytes=signed_bytes,
        signature=authorization.get("sshsig_armored"),
        identity=RECOVERY_SIGNER_IDENTITY,
        namespace=RECOVERY_SIGNATURE_NAMESPACE,
        label="recovery authorization",
    ))
    return errors


def recovery_consumption_signed_bytes(proof: dict[str, Any]) -> bytes:
    """Canonical bytes for the append/readback consume-once ledger proof."""

    return _canonical_bytes(proof["signed_binding"])


def _consumption_errors(
    proof: Any, *, intent: Any, binding: Any
) -> list[str]:
    errors = _exact(
        proof, _CONSUMPTION_KEYS, "authorization_consumption_proof"
    )
    if not isinstance(proof, dict):
        return errors
    errors.extend(_exact(
        proof.get("signed_binding"),
        _CONSUMPTION_SIGNED_BINDING_KEYS,
        "authorization consumption signed_binding",
    ))
    errors.extend(_sealed(
        proof, "proof_digest", "authorization_consumption_proof"
    ))
    signed = proof.get("signed_binding")
    if not isinstance(signed, dict):
        return errors
    if signed != {
        key: proof.get(key) for key in _CONSUMPTION_SIGNED_BINDING_KEYS
    }:
        errors.append("authorization consumption signed_binding differs from proof")
    if not isinstance(binding, dict):
        return errors + ["authorization consumption cannot bind malformed recovery"]
    authorization = binding.get("authorization")
    anchor = binding.get("trusted_anchor")
    root = binding.get("state_root_identity")
    if not isinstance(authorization, dict):
        errors.append("authorization consumption has no bound authorization")
    elif proof.get("authorization_id") != authorization.get("authorization_id"):
        errors.append("authorization consumption binds a different authorization")
    if not isinstance(intent, dict):
        errors.append("authorization consumption has no exact recovery intent")
    else:
        if proof.get("recovery_id") != intent.get("recovery_id"):
            errors.append("authorization consumption binds a different recovery id")
        if proof.get("recovery_intent_digest") != intent.get("intent_digest"):
            errors.append("authorization consumption binds a different intent")
    if not isinstance(root, dict) or proof.get("bound_state_root_id") != root.get("root_id"):
        errors.append("authorization consumption binds a different state root")
    if isinstance(anchor, dict):
        if proof.get("external_sequence") != anchor.get("external_sequence", 0) + 1:
            errors.append("authorization consumption sequence is not the anchor successor")
        if proof.get("previous_append_head_digest") != anchor.get("append_head_digest"):
            errors.append("authorization consumption does not extend the trusted anchor")
    entry = canonical_digest({
        "authorization_id": proof.get("authorization_id"),
        "recovery_id": proof.get("recovery_id"),
        "recovery_intent_digest": proof.get("recovery_intent_digest"),
        "bound_state_root_id": proof.get("bound_state_root_id"),
    })
    if proof.get("append_entry_digest") != entry:
        errors.append("authorization consumption append entry does not re-derive")
    head = canonical_digest({
        "external_sequence": proof.get("external_sequence"),
        "previous_append_head_digest": proof.get("previous_append_head_digest"),
        "append_entry_digest": proof.get("append_entry_digest"),
    })
    if proof.get("append_head_digest") != head:
        errors.append("authorization consumption append head does not re-derive")
    if proof.get("append_only") is not True:
        errors.append("authorization consumption does not prove append-only storage")
    if proof.get("immutable_readback") is not True:
        errors.append("authorization consumption does not prove immutable readback")
    if proof.get("immutable_readback_digest") != proof.get("append_entry_digest"):
        errors.append("authorization consumption readback differs from append entry")
    if proof.get("append_actor_identity") == proof.get("readback_verifier_identity"):
        errors.append("authorization consumption writer and reader must differ")
    if proof.get("evidence_class") not in {
        "LOCAL_REPRODUCIBLE", "PLATFORM_OR_EXTERNAL_ATTESTED"
    }:
        errors.append("authorization consumption evidence_class is invalid")
    if proof.get("signer_identity") != RECOVERY_CONSUMPTION_SIGNER_IDENTITY:
        errors.append("authorization consumption signer identity is invalid")
    if proof.get("signature_namespace") != RECOVERY_CONSUMPTION_SIGNATURE_NAMESPACE:
        errors.append("authorization consumption SSHSIG namespace is invalid")
    try:
        signed_bytes = recovery_consumption_signed_bytes(proof)
    except (KeyError, TypeError, ValueError):
        signed_bytes = b""
    errors.extend(_fixed_root_signature_errors(
        signer_fingerprint=proof.get("signer_fingerprint"),
        signed_bytes=signed_bytes,
        signature=proof.get("sshsig_armored"),
        identity=RECOVERY_CONSUMPTION_SIGNER_IDENTITY,
        namespace=RECOVERY_CONSUMPTION_SIGNATURE_NAMESPACE,
        label="authorization consumption",
    ))
    return errors


def _sensitive_key_hits(value: Any, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in _FORBIDDEN_KEYS:
                hits.append(f"{path}.{key}")
            hits.extend(_sensitive_key_hits(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            hits.extend(_sensitive_key_hits(item, f"{path}[{index}]"))
    elif isinstance(value, str) and _SECRET_VALUE_RE.search(value):
        hits.append(path)
    return hits


def recovery_capture_signed_bytes(capture: dict[str, Any]) -> bytes:
    """Canonical bytes authenticated for actor/verifier observation capture."""

    return _canonical_bytes(capture["signed_binding"])


def _capture_errors(
    capture: Any,
    *,
    permission: str,
    intent: dict[str, Any] | None = None,
    recovery_result_digest: str | None = None,
    observed_state: dict[str, Any] | None = None,
    now: Any = None,
) -> list[str]:
    errors = _exact(capture, _CAPTURE_KEYS, "capture")
    if not isinstance(capture, dict):
        return errors
    errors.extend(_exact(capture.get("node_identity"), _NODE_KEYS, "capture node_identity"))
    errors.extend(_exact(
        capture.get("process_identity"), _PROCESS_KEYS, "capture process_identity"
    ))
    errors.extend(_exact(
        capture.get("observed_state"), _STATE_KEYS, "capture observed_state"
    ))
    errors.extend(_exact(
        capture.get("signed_binding"),
        _CAPTURE_SIGNED_BINDING_KEYS,
        "capture signed_binding",
    ))
    errors.extend(_sealed(capture, "capture_digest", "capture"))
    node = capture.get("node_identity")
    if isinstance(node, dict) and node.get("permission") != permission:
        errors.append(f"capture permission must be {permission}")
    signed = capture.get("signed_binding")
    if isinstance(signed, dict) and signed != {
        key: capture.get(key) for key in _CAPTURE_SIGNED_BINDING_KEYS
    }:
        errors.append("capture signed_binding differs from the exact capture")
    if capture.get("observed_state_digest") != canonical_digest(
        capture.get("observed_state")
    ):
        errors.append("capture observed-state digest does not re-derive")
    if permission == "effect":
        kind = "ACTOR_EFFECT"
        identity = RECOVERY_ACTOR_CAPTURE_SIGNER_IDENTITY
        namespace = RECOVERY_ACTOR_CAPTURE_SIGNATURE_NAMESPACE
        if capture.get("recovery_result_digest") is not None:
            errors.append("actor capture must precede and therefore not bind a result")
    else:
        kind = "INDEPENDENT_POSTCHECK"
        identity = RECOVERY_VERIFIER_CAPTURE_SIGNER_IDENTITY
        namespace = RECOVERY_VERIFIER_CAPTURE_SIGNATURE_NAMESPACE
        if capture.get("recovery_result_digest") is None:
            errors.append("verifier capture must bind the exact recovery result")
    if capture.get("capture_kind") != kind:
        errors.append(f"capture_kind must be {kind}")
    if capture.get("signer_identity") != identity:
        errors.append("capture signer identity is invalid")
    if capture.get("signature_namespace") != namespace:
        errors.append("capture SSHSIG namespace is invalid")
    try:
        signed_bytes = recovery_capture_signed_bytes(capture)
    except (KeyError, TypeError, ValueError):
        signed_bytes = b""
    errors.extend(_fixed_root_signature_errors(
        signer_fingerprint=capture.get("signer_fingerprint"),
        signed_bytes=signed_bytes,
        signature=capture.get("sshsig_armored"),
        identity=identity,
        namespace=namespace,
        label="recovery capture",
    ))
    if intent is not None:
        binding = intent.get("recovery_binding")
        root = binding.get("state_root_identity") if isinstance(binding, dict) else None
        expected = {
            "source_head": binding.get("source_head") if isinstance(binding, dict) else None,
            "host_identity": binding.get("host_identity") if isinstance(binding, dict) else None,
            "bound_state_root_id": root.get("root_id") if isinstance(root, dict) else None,
            "recovery_id": intent.get("recovery_id"),
            "recovery_intent_digest": intent.get("intent_digest"),
        }
        for key, value in expected.items():
            if capture.get(key) != value:
                errors.append(f"capture {key} differs from the recovery intent")
    if recovery_result_digest is not None and capture.get(
        "recovery_result_digest"
    ) != recovery_result_digest:
        errors.append("capture recovery_result_digest differs from result")
    if observed_state is not None and capture.get("observed_state") != observed_state:
        errors.append("capture observed_state differs from the exact state")
    try:
        observed_at = _parse_timestamp(str(capture.get("observed_at")))
    except (TypeError, ValueError) as error:
        errors.append(f"capture observed_at is invalid: {error}")
        observed_at = None
    if observed_at is not None and intent is not None:
        binding = intent.get("recovery_binding")
        authorization = binding.get("authorization") if isinstance(binding, dict) else None
        if isinstance(authorization, dict):
            try:
                issued_at = _parse_timestamp(str(authorization.get("issued_at")))
                expires_at = _parse_timestamp(str(authorization.get("expires_at")))
            except (TypeError, ValueError) as error:
                errors.append(f"capture authorization window is invalid: {error}")
            else:
                if observed_at < issued_at or observed_at >= expires_at:
                    errors.append("capture observed_at is outside the authorization window")
    if observed_at is not None and now is not None:
        try:
            current = _parse_timestamp(now) if isinstance(now, str) else now
            if not isinstance(current, datetime) or current.tzinfo is None:
                raise ValueError("now must be timezone-aware")
        except (TypeError, ValueError) as error:
            errors.append(f"capture current time is invalid: {error}")
        else:
            if observed_at > current:
                errors.append("capture observed_at is in the future")
    return errors


def _fresh_authorization_errors(binding: dict[str, Any], now: Any) -> list[str]:
    authorization = binding.get("authorization")
    if not isinstance(authorization, dict):
        return ["recovery authorization must be an object"]
    if now is None:
        return ["recovery authorization validation requires an explicit current time"]
    try:
        issued = _parse_timestamp(str(authorization["issued_at"]))
        expires = _parse_timestamp(str(authorization["expires_at"]))
        current = _parse_timestamp(now) if isinstance(now, str) else now
        if not isinstance(current, datetime) or current.tzinfo is None:
            raise ValueError("now must be a timezone-aware datetime or timestamp")
    except (TypeError, ValueError) as error:
        return [f"recovery authorization timestamps are invalid: {error}"]
    errors = []
    if issued >= expires:
        errors.append("recovery authorization issued_at must precede expires_at")
    if current < issued or current >= expires:
        errors.append("recovery authorization is stale or not yet valid")
    return errors


def _validated_copy(value: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(value)


def build_recovery_intent(
    *,
    unresolved_state: dict[str, Any],
    kernel_binding: dict[str, Any],
    admission: dict[str, Any],
    authorization: dict[str, Any],
    trusted_anchor: dict[str, Any],
    action: str,
    now: Any,
) -> dict[str, Any]:
    """Build an intent with actor/process identity derived from the sealed kernel binding."""

    errors = []
    errors.extend(_exact(kernel_binding, _KERNEL_KEYS, "kernel_binding"))
    errors.extend(_sealed(kernel_binding, "binding_digest", "kernel_binding"))
    errors.extend(_exact(admission, _ADMISSION_KEYS, "admission"))
    errors.extend(_sealed(admission, "admission_digest", "admission"))
    errors.extend(_exact(authorization, _AUTH_KEYS, "authorization"))
    errors.extend(_sealed(authorization, "authorization_digest", "authorization"))
    errors.extend(_exact(trusted_anchor, _ANCHOR_KEYS, "trusted_anchor"))
    errors.extend(_sealed(trusted_anchor, "reference_digest", "trusted_anchor"))
    if action not in RECOVERY_ACTIONS:
        errors.append("recovery action is not in the code-owned enum")
    unresolved_digest = unresolved_state.get("unresolved_state_digest")
    if unresolved_digest != canonical_digest(_without(unresolved_state, "unresolved_state_digest")):
        errors.append("unresolved state digest does not re-derive")
    if admission.get("unresolved_state_digest") != unresolved_digest:
        errors.append("admission does not bind the current unresolved state")
    for field in ("source_head", "host_identity"):
        if kernel_binding.get(field) != admission.get(field):
            errors.append(f"kernel/admission {field} mismatch")
        if trusted_anchor.get(field) != admission.get(field):
            errors.append(f"anchor/admission {field} mismatch")
    binding = {
        "task_digest": admission.get("task_digest"),
        "unresolved_state_digest": unresolved_digest,
        "state_root_identity": _validated_copy(admission.get("state_root_identity")),
        "journal_set": _validated_copy(admission.get("journal_set")),
        "replay_ledger_head": _validated_copy(admission.get("replay_ledger_head")),
        "pre_state": _validated_copy(admission.get("pre_state")),
        "source_head": admission.get("source_head"),
        "host_identity": admission.get("host_identity"),
        "authorization": _validated_copy(authorization),
        "trusted_anchor": _validated_copy(trusted_anchor),
        "actor_identity": _validated_copy(kernel_binding["node_identity"]),
        "actor_process": _validated_copy(kernel_binding["process_identity"]),
        "kernel_binding_digest": kernel_binding["binding_digest"],
        "admission_digest": admission["admission_digest"],
        "side_effect_class": unresolved_state.get("side_effect_class"),
        "production_effect": unresolved_state.get("production_effect"),
        "production_authority": unresolved_state.get("production_authority"),
        "target_class": unresolved_state.get("target_class"),
    }
    errors.extend(_binding_errors(binding, action=action))
    errors.extend(_fresh_authorization_errors(binding, now))
    if errors:
        raise ValueError("; ".join(errors))
    core = {
        "schema_version": "s2_5_recovery_intent_v1",
        "action": action,
        "recovery_binding": binding,
        "actor_identity": _validated_copy(kernel_binding["node_identity"]),
        "actor_process": _validated_copy(kernel_binding["process_identity"]),
        "kernel_binding_digest": kernel_binding["binding_digest"],
        "admission_digest": admission["admission_digest"],
    }
    intent_digest = canonical_digest(core)
    intent = {
        **core,
        "recovery_id": "s2-5-recovery-" + intent_digest.split(":", 1)[1],
        "intent_digest": intent_digest,
    }
    intent["self_digest"] = artifact_self_digest(intent)
    validation_errors = validate_recovery_artifact(intent, now=now)
    if validation_errors:
        raise ValueError("; ".join(validation_errors))
    return intent


def build_recovery_rollback(
    *,
    intent: dict[str, Any],
    actor_capture: dict[str, Any],
    post_state: dict[str, Any],
    status: str,
) -> dict[str, Any]:
    errors = validate_recovery_artifact(intent)
    errors.extend(_capture_errors(
        actor_capture,
        permission="effect",
        intent=intent,
        observed_state=post_state,
    ))
    errors.extend(_exact(post_state, _STATE_KEYS, "rollback post_state"))
    if actor_capture.get("source_head") != intent.get("recovery_binding", {}).get("source_head"):
        errors.append("rollback capture source_head differs from intent")
    if actor_capture.get("host_identity") != intent.get("recovery_binding", {}).get("host_identity"):
        errors.append("rollback capture host differs from intent")
    if actor_capture.get("node_identity") != intent.get("actor_identity"):
        errors.append("rollback actor identity differs from the kernel-bound actor")
    if actor_capture.get("process_identity") != intent.get("actor_process"):
        errors.append("rollback actor process differs from the kernel-bound process")
    if status not in {"ROLLBACK_APPLIED", "ROLLBACK_FAILED", "LATCH_PRESERVED"}:
        errors.append("unsupported rollback status")
    if intent.get("action") == "ROLLBACK_TO_PRE_STATE" and (
        status == "ROLLBACK_APPLIED"
        and post_state != intent.get("recovery_binding", {}).get("pre_state")
    ):
        errors.append("ROLLBACK_TO_PRE_STATE did not restore the exact pre-state")
    if intent.get("action") == "ABORT_AND_PRESERVE_LATCH" and (
        status != "LATCH_PRESERVED"
        or post_state != intent.get("recovery_binding", {}).get("pre_state")
    ):
        errors.append("ABORT_AND_PRESERVE_LATCH must preserve pre-state and latch")
    if intent.get("action") == "REPLAY_JOURNAL" and status == "ROLLBACK_APPLIED":
        errors.append(
            "REPLAY_JOURNAL cannot apply without a typed target-state predicate"
        )
    if errors:
        raise ValueError("; ".join(errors))
    rollback_intent_digest = canonical_digest({
        "recovery_intent_digest": intent["intent_digest"],
        "action": intent["action"],
        "pre_state": intent["recovery_binding"]["pre_state"],
    })
    rollback_result_digest = canonical_digest({
        "rollback_intent_digest": rollback_intent_digest,
        "post_state": post_state,
        "status": status,
        "actor_capture_digest": actor_capture["capture_digest"],
    })
    rollback = {
        "schema_version": "s2_5_recovery_rollback_v1",
        "recovery_id": intent["recovery_id"],
        "recovery_intent_digest": intent["intent_digest"],
        "action": intent["action"],
        "recovery_binding": _validated_copy(intent["recovery_binding"]),
        "actor_identity": _validated_copy(actor_capture["node_identity"]),
        "actor_process": _validated_copy(actor_capture["process_identity"]),
        "actor_capture_digest": actor_capture["capture_digest"],
        "actor_capture": _validated_copy(actor_capture),
        "pre_state": _validated_copy(intent["recovery_binding"]["pre_state"]),
        "post_state": _validated_copy(post_state),
        "status": status,
        "rollback_intent_digest": rollback_intent_digest,
        "rollback_result_digest": rollback_result_digest,
    }
    rollback["self_digest"] = artifact_self_digest(rollback)
    return rollback


def build_recovery_result(
    *,
    intent: dict[str, Any],
    actor_capture: dict[str, Any],
    rollback: dict[str, Any],
    post_state: dict[str, Any],
    status: str,
    authorization_consumption_proof: dict[str, Any],
) -> dict[str, Any]:
    errors = validate_recovery_artifact(intent)
    errors.extend(validate_recovery_artifact(rollback))
    errors.extend(_capture_errors(
        actor_capture,
        permission="effect",
        intent=intent,
        observed_state=post_state,
    ))
    if rollback.get("recovery_intent_digest") != intent.get("intent_digest"):
        errors.append("rollback is bound to a different recovery intent")
    if rollback.get("recovery_binding") != intent.get("recovery_binding"):
        errors.append("rollback recovery binding differs from intent")
    if rollback.get("actor_capture_digest") != actor_capture.get("capture_digest"):
        errors.append("result actor capture differs from rollback capture")
    if rollback.get("post_state") != post_state:
        errors.append("result post-state differs from rollback post-state")
    if status == "RECOVERY_APPLIED" and rollback.get("status") != "ROLLBACK_APPLIED":
        errors.append("successful recovery requires a successful rollback result")
    if status not in {"RECOVERY_APPLIED", "RECOVERY_FAILED", "RECOVERY_ABORTED"}:
        errors.append("unsupported recovery result status")
    if intent.get("action") in {
        "ABORT_AND_PRESERVE_LATCH", "REPLAY_JOURNAL"
    } and status == "RECOVERY_APPLIED":
        errors.append(f"{intent.get('action')} cannot produce RECOVERY_APPLIED")
    anchor = intent.get("recovery_binding", {}).get("trusted_anchor")
    if (
        status == "RECOVERY_APPLIED"
        and isinstance(anchor, dict)
        and anchor.get("evidence_class") != "PLATFORM_OR_EXTERNAL_ATTESTED"
    ):
        errors.append("source-only evidence cannot claim RECOVERY_APPLIED")
    errors.extend(_consumption_errors(
        authorization_consumption_proof,
        intent=intent,
        binding=intent.get("recovery_binding"),
    ))
    if errors:
        raise ValueError("; ".join(errors))
    result = {
        "schema_version": "s2_5_recovery_result_v1",
        "recovery_id": intent["recovery_id"],
        "recovery_intent_digest": intent["intent_digest"],
        "recovery_intent": _validated_copy(intent),
        "recovery_binding": _validated_copy(intent["recovery_binding"]),
        "actor_identity": _validated_copy(actor_capture["node_identity"]),
        "actor_process": _validated_copy(actor_capture["process_identity"]),
        "actor_capture_digest": actor_capture["capture_digest"],
        "actor_capture": _validated_copy(actor_capture),
        "rollback_intent_digest": rollback["rollback_intent_digest"],
        "rollback_result_digest": rollback["rollback_result_digest"],
        "rollback_status": rollback["status"],
        "rollback": _validated_copy(rollback),
        "post_state": _validated_copy(post_state),
        "status": status,
        "authorization_consumption_proof": _validated_copy(
            authorization_consumption_proof
        ),
    }
    result["result_digest"] = canonical_digest(result)
    result["self_digest"] = artifact_self_digest(result)
    return result


def build_recovery_postcheck(
    *,
    intent: dict[str, Any],
    result: dict[str, Any],
    verifier_capture: dict[str, Any],
    observed_state: dict[str, Any],
    status: str,
) -> dict[str, Any]:
    errors = validate_recovery_artifact(intent)
    errors.extend(validate_recovery_artifact(result))
    errors.extend(_capture_errors(
        verifier_capture,
        permission="read_only",
        intent=intent,
        recovery_result_digest=result.get("result_digest"),
        observed_state=observed_state,
    ))
    if result.get("recovery_intent_digest") != intent.get("intent_digest"):
        errors.append("postcheck result is bound to a different intent")
    if verifier_capture.get("source_head") != intent.get("recovery_binding", {}).get("source_head"):
        errors.append("postcheck source_head differs from intent")
    if verifier_capture.get("host_identity") != intent.get("recovery_binding", {}).get("host_identity"):
        errors.append("postcheck host differs from intent")
    if status not in {"RECOVERY_CLEARED", "RECOVERY_UNRESOLVED"}:
        errors.append("unsupported recovery postcheck status")
    anchor = intent.get("recovery_binding", {}).get("trusted_anchor")
    if (
        status == "RECOVERY_CLEARED"
        and isinstance(anchor, dict)
        and anchor.get("evidence_class") != "PLATFORM_OR_EXTERNAL_ATTESTED"
    ):
        errors.append("source-only evidence cannot claim RECOVERY_CLEARED")
    if errors:
        raise ValueError("; ".join(errors))
    postcheck = {
        "schema_version": "s2_5_recovery_postcheck_v1",
        "recovery_id": intent["recovery_id"],
        "recovery_intent_digest": intent["intent_digest"],
        "recovery_result_digest": result["result_digest"],
        "recovery_binding": _validated_copy(intent["recovery_binding"]),
        "verifier_identity": _validated_copy(verifier_capture["node_identity"]),
        "verifier_process": _validated_copy(verifier_capture["process_identity"]),
        "verifier_capture_digest": verifier_capture["capture_digest"],
        "verifier_capture": _validated_copy(verifier_capture),
        "observed_state": _validated_copy(observed_state),
        "observed_state_digest": canonical_digest(observed_state),
        "status": status,
    }
    postcheck["postcheck_id"] = canonical_digest(postcheck)
    postcheck["self_digest"] = artifact_self_digest(postcheck)
    return postcheck


def validate_recovery_artifact(artifact: Any, *, now: Any = None) -> list[str]:
    """Semantic validator called by the central receipt validator after closed schema."""

    if not isinstance(artifact, dict):
        return ["recovery artifact must be an object"]
    schema = artifact.get("schema_version")
    errors: list[str] = []
    if schema not in RECOVERY_SCHEMA_VERSIONS:
        return [f"unsupported recovery schema_version: {schema!r}"]
    action: str | None = None
    if schema in {"s2_5_recovery_intent_v1", "s2_5_recovery_rollback_v1"}:
        action = artifact.get("action")
    elif schema == "s2_5_recovery_result_v1":
        embedded = artifact.get("recovery_intent")
        action = embedded.get("action") if isinstance(embedded, dict) else None
    elif isinstance(artifact.get("recovery_binding"), dict):
        authorization = artifact["recovery_binding"].get("authorization")
        signed = authorization.get("signed_binding") if isinstance(
            authorization, dict
        ) else None
        action = signed.get("action") if isinstance(signed, dict) else None
    errors.extend(_binding_errors(artifact.get("recovery_binding"), action=action))
    if isinstance(artifact.get("recovery_binding"), dict) and now is not None:
        errors.extend(_fresh_authorization_errors(artifact["recovery_binding"], now))
    hits = _sensitive_key_hits(artifact)
    if hits:
        errors.append(f"recovery artifact contains forbidden command/secret keys: {hits}")
    if artifact.get("self_digest") != artifact_self_digest(artifact):
        errors.append("recovery artifact self_digest does not bind the canonical artifact")
    if schema == "s2_5_recovery_intent_v1":
        expected = canonical_digest(_without(
            artifact, "recovery_id", "intent_digest", "self_digest"
        ))
        if artifact.get("intent_digest") != expected:
            errors.append("recovery intent digest does not re-derive")
        if artifact.get("recovery_id") != "s2-5-recovery-" + expected.split(":", 1)[1]:
            errors.append("recovery_id does not derive from the exact intent")
        if artifact.get("action") not in RECOVERY_ACTIONS:
            errors.append("recovery action is not code-owned")
    elif schema == "s2_5_recovery_rollback_v1":
        actor_capture = artifact.get("actor_capture")
        bound_intent = {
            "recovery_binding": artifact.get("recovery_binding"),
            "recovery_id": artifact.get("recovery_id"),
            "intent_digest": artifact.get("recovery_intent_digest"),
        }
        errors.extend(_capture_errors(
            actor_capture,
            permission="effect",
            intent=bound_intent,
            observed_state=artifact.get("post_state"),
            now=now,
        ))
        capture = actor_capture if isinstance(actor_capture, dict) else {}
        if artifact.get("actor_capture_digest") != capture.get("capture_digest"):
            errors.append("rollback actor capture digest differs from the bound capture")
        if artifact.get("actor_identity") != capture.get("node_identity"):
            errors.append("rollback actor identity is not derived from its capture")
        if artifact.get("actor_process") != capture.get("process_identity"):
            errors.append("rollback actor process is not derived from its capture")
        if artifact.get("actor_identity") != artifact.get("recovery_binding", {}).get(
            "actor_identity"
        ):
            errors.append("rollback actor identity differs from the kernel binding")
        if artifact.get("actor_process") != artifact.get("recovery_binding", {}).get(
            "actor_process"
        ):
            errors.append("rollback actor process differs from the kernel binding")
        expected_intent = canonical_digest({
            "recovery_intent_digest": artifact.get("recovery_intent_digest"),
            "action": artifact.get("action"),
            "pre_state": artifact.get("pre_state"),
        })
        expected_result = canonical_digest({
            "rollback_intent_digest": expected_intent,
            "post_state": artifact.get("post_state"),
            "status": artifact.get("status"),
            "actor_capture_digest": artifact.get("actor_capture_digest"),
        })
        if artifact.get("rollback_intent_digest") != expected_intent:
            errors.append("rollback intent digest does not re-derive")
        if artifact.get("rollback_result_digest") != expected_result:
            errors.append("rollback result digest does not re-derive")
        if artifact.get("pre_state") != artifact.get("recovery_binding", {}).get("pre_state"):
            errors.append("rollback pre-state differs from the bound pre-state")
        if artifact.get("status") not in {
            "ROLLBACK_APPLIED", "ROLLBACK_FAILED", "LATCH_PRESERVED"
        }:
            errors.append("unsupported rollback status")
        if artifact.get("action") == "ROLLBACK_TO_PRE_STATE" and (
            artifact.get("status") == "ROLLBACK_APPLIED"
            and artifact.get("post_state") != artifact.get("pre_state")
        ):
            errors.append("ROLLBACK_TO_PRE_STATE did not restore the exact pre-state")
        if artifact.get("action") == "ABORT_AND_PRESERVE_LATCH" and (
            artifact.get("status") != "LATCH_PRESERVED"
            or artifact.get("post_state") != artifact.get("pre_state")
        ):
            errors.append("ABORT_AND_PRESERVE_LATCH must preserve pre-state and latch")
        if artifact.get("action") == "REPLAY_JOURNAL" and artifact.get(
            "status"
        ) == "ROLLBACK_APPLIED":
            errors.append(
                "REPLAY_JOURNAL cannot apply without a typed target-state predicate"
            )
    elif schema == "s2_5_recovery_result_v1":
        errors.extend(validate_recovery_artifact(artifact.get("recovery_intent"), now=now))
        errors.extend(validate_recovery_artifact(artifact.get("rollback"), now=now))
        embedded_intent = artifact.get("recovery_intent", {})
        embedded_rollback = artifact.get("rollback", {})
        if artifact.get("recovery_intent_digest") != embedded_intent.get("intent_digest"):
            errors.append("result does not bind its exact embedded recovery intent")
        if artifact.get("recovery_binding") != embedded_intent.get("recovery_binding"):
            errors.append("result recovery binding differs from the embedded intent")
        if artifact.get("rollback_intent_digest") != embedded_rollback.get(
            "rollback_intent_digest"
        ):
            errors.append("result rollback-intent digest differs from embedded rollback")
        if artifact.get("rollback_result_digest") != embedded_rollback.get(
            "rollback_result_digest"
        ):
            errors.append("result rollback-result digest differs from embedded rollback")
        if artifact.get("rollback_status") != embedded_rollback.get("status"):
            errors.append("result rollback status differs from embedded rollback")
        if embedded_rollback.get("action") != embedded_intent.get("action"):
            errors.append("result rollback action differs from embedded intent")
        if embedded_rollback.get("recovery_binding") != artifact.get(
            "recovery_binding"
        ):
            errors.append("result rollback recovery binding differs from intent")
        if embedded_rollback.get("post_state") != artifact.get("post_state"):
            errors.append("result post-state differs from embedded rollback")
        errors.extend(_capture_errors(
            artifact.get("actor_capture"),
            permission="effect",
            intent=embedded_intent if isinstance(embedded_intent, dict) else None,
            observed_state=artifact.get("post_state"),
            now=now,
        ))
        if artifact.get("actor_capture_digest") != artifact.get("actor_capture", {}).get(
            "capture_digest"
        ):
            errors.append("result actor capture digest differs from the bound capture")
        if artifact.get("actor_identity") != artifact.get("actor_capture", {}).get(
            "node_identity"
        ):
            errors.append("result actor identity is not derived from its capture")
        if artifact.get("actor_process") != artifact.get("actor_capture", {}).get(
            "process_identity"
        ):
            errors.append("result actor process is not derived from its capture")
        if artifact.get("actor_identity") != artifact.get("recovery_binding", {}).get(
            "actor_identity"
        ):
            errors.append("result actor identity differs from the kernel-bound actor")
        if artifact.get("actor_process") != artifact.get("recovery_binding", {}).get(
            "actor_process"
        ):
            errors.append("result actor process differs from the kernel-bound process")
        expected_rollback_result = canonical_digest({
            "rollback_intent_digest": artifact.get("rollback_intent_digest"),
            "post_state": artifact.get("post_state"),
            "status": artifact.get("rollback_status"),
            "actor_capture_digest": artifact.get("actor_capture_digest"),
        })
        if artifact.get("rollback_result_digest") != expected_rollback_result:
            errors.append("result does not bind the exact rollback result digest")
        expected = canonical_digest(_without(artifact, "result_digest", "self_digest"))
        if artifact.get("result_digest") != expected:
            errors.append("recovery result digest does not re-derive")
        if artifact.get("status") not in {
            "RECOVERY_APPLIED", "RECOVERY_FAILED", "RECOVERY_ABORTED"
        }:
            errors.append("unsupported recovery result status")
        if artifact.get("status") == "RECOVERY_APPLIED" and artifact.get(
            "rollback_status"
        ) != "ROLLBACK_APPLIED":
            errors.append("RECOVERY_APPLIED requires ROLLBACK_APPLIED")
        if embedded_intent.get("action") in {
            "ABORT_AND_PRESERVE_LATCH", "REPLAY_JOURNAL"
        } and artifact.get("status") == "RECOVERY_APPLIED":
            errors.append(
                f"{embedded_intent.get('action')} cannot produce RECOVERY_APPLIED"
            )
        anchor = artifact.get("recovery_binding", {}).get("trusted_anchor")
        if (
            artifact.get("status") == "RECOVERY_APPLIED"
            and isinstance(anchor, dict)
            and anchor.get("evidence_class") != "PLATFORM_OR_EXTERNAL_ATTESTED"
        ):
            errors.append("source-only evidence cannot claim RECOVERY_APPLIED")
        errors.extend(_consumption_errors(
            artifact.get("authorization_consumption_proof"),
            intent=embedded_intent,
            binding=artifact.get("recovery_binding"),
        ))
    elif schema == "s2_5_recovery_postcheck_v1":
        bound_intent = {
            "recovery_binding": artifact.get("recovery_binding"),
            "recovery_id": artifact.get("recovery_id"),
            "intent_digest": artifact.get("recovery_intent_digest"),
        }
        errors.extend(_capture_errors(
            artifact.get("verifier_capture"),
            permission="read_only",
            intent=bound_intent,
            recovery_result_digest=artifact.get("recovery_result_digest"),
            observed_state=artifact.get("observed_state"),
            now=now,
        ))
        verifier_capture = artifact.get("verifier_capture")
        capture = verifier_capture if isinstance(verifier_capture, dict) else {}
        if artifact.get("verifier_capture_digest") != capture.get("capture_digest"):
            errors.append("postcheck verifier capture digest differs from the capture")
        if artifact.get("verifier_identity") != capture.get("node_identity"):
            errors.append("postcheck verifier identity is not derived from its capture")
        if artifact.get("verifier_process") != capture.get("process_identity"):
            errors.append("postcheck verifier process is not derived from its capture")
        expected = canonical_digest(_without(artifact, "postcheck_id", "self_digest"))
        if artifact.get("postcheck_id") != expected:
            errors.append("recovery postcheck identity does not re-derive")
        if artifact.get("observed_state_digest") != canonical_digest(
            artifact.get("observed_state")
        ):
            errors.append("postcheck observed-state digest does not re-derive")
        if artifact.get("status") not in {
            "RECOVERY_CLEARED", "RECOVERY_UNRESOLVED"
        }:
            errors.append("unsupported recovery postcheck status")
        anchor = artifact.get("recovery_binding", {}).get("trusted_anchor")
        if (
            artifact.get("status") == "RECOVERY_CLEARED"
            and isinstance(anchor, dict)
            and anchor.get("evidence_class") != "PLATFORM_OR_EXTERNAL_ATTESTED"
        ):
            errors.append("source-only evidence cannot claim RECOVERY_CLEARED")
    return errors


def validate_recovery_transition(
    *,
    unresolved_state: dict[str, Any] | None,
    recovery_result: Any,
    independent_postcheck: Any,
    consumed_authorization_ids: set[str],
    now: Any = None,
) -> list[str]:
    """Validate the sole legal unresolved→clear transition."""

    if unresolved_state is None:
        return ["no unresolved recovery latch exists"]
    if now is None:
        return ["recovery transition requires an explicit current time"]
    expected_unresolved = canonical_digest(
        _without(unresolved_state, "unresolved_state_digest")
    )
    if unresolved_state.get("unresolved_state_digest") != expected_unresolved:
        return ["live unresolved recovery state digest does not re-derive"]
    errors = validate_recovery_artifact(recovery_result, now=now)
    errors.extend(validate_recovery_artifact(independent_postcheck, now=now))
    if errors:
        return errors
    binding = recovery_result["recovery_binding"]
    if binding["unresolved_state_digest"] != unresolved_state.get("unresolved_state_digest"):
        errors.append("recovery result binds a stale or different unresolved state")
    if independent_postcheck["recovery_binding"] != binding:
        errors.append("independent postcheck recovery binding differs from result")
    if independent_postcheck["recovery_id"] != recovery_result["recovery_id"]:
        errors.append("independent postcheck recovery id differs from result")
    if independent_postcheck["recovery_intent_digest"] != recovery_result[
        "recovery_intent_digest"
    ]:
        errors.append("cross-step recovery intent digest mismatch")
    if independent_postcheck["recovery_result_digest"] != recovery_result["result_digest"]:
        errors.append("postcheck does not bind the exact recovery result")
    if independent_postcheck["observed_state"] != recovery_result["post_state"]:
        errors.append("independent postcheck did not observe the exact result state")
    if recovery_result["status"] != "RECOVERY_APPLIED":
        errors.append("only RECOVERY_APPLIED can clear the latch")
    if independent_postcheck["status"] != "RECOVERY_CLEARED":
        errors.append("independent postcheck did not clear recovery")
    actor = recovery_result["actor_identity"]
    verifier = independent_postcheck["verifier_identity"]
    if actor["node_id"] == verifier["node_id"]:
        errors.append("recovery verifier must be a different node")
    if actor["role"] == verifier["role"]:
        errors.append("recovery verifier must be a different role")
    actor_process = recovery_result["actor_process"]
    verifier_process = independent_postcheck["verifier_process"]
    if actor_process["uid"] == verifier_process["uid"]:
        errors.append("recovery verifier must use a different uid")
    if actor_process["cgroup"] == verifier_process["cgroup"]:
        errors.append("recovery verifier must use a different cgroup")
    if actor["key_identity"] == verifier["key_identity"]:
        errors.append("recovery verifier must use a different key identity")
    if actor != binding["actor_identity"]:
        errors.append("recovery actor was renamed or differs from the kernel-bound actor")
    if recovery_result["actor_process"] != binding["actor_process"]:
        errors.append("recovery actor process differs from the kernel-bound process")
    authorization_id = binding["authorization"]["authorization_id"]
    if authorization_id in consumed_authorization_ids:
        errors.append("recovery authorization was already consumed")
    anchor = binding["trusted_anchor"]
    consumption = recovery_result["authorization_consumption_proof"]
    if anchor["evidence_class"] != "PLATFORM_OR_EXTERNAL_ATTESTED":
        errors.append("source-only trusted anchor cannot clear the recovery latch")
    if consumption["evidence_class"] != "PLATFORM_OR_EXTERNAL_ATTESTED":
        errors.append("source-only consumption proof cannot clear the recovery latch")
    action = recovery_result["recovery_intent"]["action"]
    if action != "ROLLBACK_TO_PRE_STATE":
        errors.append(f"{action} is non-clearing within the current recovery contract")
    actor_capture = recovery_result.get("actor_capture")
    verifier_capture = independent_postcheck.get("verifier_capture")
    if isinstance(actor_capture, dict) and isinstance(verifier_capture, dict):
        try:
            actor_observed_at = _parse_timestamp(str(actor_capture.get("observed_at")))
            verifier_observed_at = _parse_timestamp(
                str(verifier_capture.get("observed_at"))
            )
        except (TypeError, ValueError) as error:
            errors.append(f"recovery capture ordering timestamps are invalid: {error}")
        else:
            if verifier_observed_at < actor_observed_at:
                errors.append("independent postcheck predates the recovery actor capture")
    return errors
