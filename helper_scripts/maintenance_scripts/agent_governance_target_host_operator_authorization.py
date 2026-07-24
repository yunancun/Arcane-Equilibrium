"""Operator-authenticated authorization for one exact S1 target-host intent.

The isolated probe child must not treat a caller-created checksum capsule as
authority.  This module binds the exact typed intent and committed source head
to the existing S1 operator SSH trust root under a dedicated signature
namespace.  The private key never enters this repository or the target host.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import agent_governance_aiml_trusted_host as trusted


AUTHORIZATION_SCHEMA_VERSION = "target_host_probe_operator_authorization_v1"
OPERATOR_IDENTITY = trusted.EXPECTED_S1_TARGET_HOST_SIGNER_IDENTITY
OPERATOR_FINGERPRINT = trusted.EXPECTED_S1_TARGET_HOST_SIGNER_FINGERPRINT
OPERATOR_PUBLIC_KEY = trusted.S1_TRUSTED_TARGET_HOST_PUBLIC_KEY
OPERATOR_ALGORITHM = trusted.EXECUTION_BUNDLE_ALGORITHM
OPERATOR_SIGNATURE_NAMESPACE = (
    "arcane-equilibrium-aiml-s1-target-host-apply"
)
MAX_AUTHORIZATION_TTL = timedelta(minutes=15)

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEAD_RE = re.compile(r"^[0-9a-f]{40}$")
AUTHORIZATION_FIELDS = frozenset({
    "schema_version",
    "signer_identity",
    "signer_fingerprint",
    "algorithm",
    "signature_namespace",
    "intent_id",
    "intent_digest",
    "source_head",
    "expected_host",
    "applier_node_id",
    "postcheck_node_id",
    "issued_at",
    "expires_at",
    "authorization_digest",
})


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def authorization_digest(value: dict[str, Any]) -> str:
    return _digest({
        key: item
        for key, item in value.items()
        if key != "authorization_digest"
    })


def intent_digest(value: dict[str, Any]) -> str:
    """Canonical self-digest for the exact typed intent."""

    return _digest({
        key: item for key, item in value.items() if key != "self_digest"
    })


def _instant(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed.astimezone(timezone.utc)


def build_operator_authorization(
    *,
    intent: dict[str, Any],
    source_head: str,
) -> dict[str, Any]:
    """Project one exact typed intent into the bytes the operator signs."""

    if not isinstance(intent, dict):
        raise ValueError("operator authorization intent must be an object")
    if not HEAD_RE.fullmatch(str(source_head)):
        raise ValueError("operator authorization source_head must be exact 40-hex")
    for field in (
        "intent_id",
        "self_digest",
        "expected_host",
        "applier_node_id",
        "postcheck_node_id",
        "created_at",
        "expires_at",
    ):
        if not intent.get(field):
            raise ValueError(
                f"operator authorization intent lacks required field {field}"
            )
    if not DIGEST_RE.fullmatch(str(intent["intent_id"])):
        raise ValueError("operator authorization intent_id must be a sha256 digest")
    if not DIGEST_RE.fullmatch(str(intent["self_digest"])):
        raise ValueError(
            "operator authorization intent self_digest must be a sha256 digest"
        )
    if intent["self_digest"] != intent_digest(intent):
        raise ValueError(
            "operator authorization intent self_digest does not match its bytes"
        )
    issued = _instant(intent["created_at"])
    intent_expiry = _instant(intent["expires_at"])
    expires = min(intent_expiry, issued + MAX_AUTHORIZATION_TTL)
    if expires <= issued:
        raise ValueError("operator authorization intent interval is invalid")
    authorization: dict[str, Any] = {
        "schema_version": AUTHORIZATION_SCHEMA_VERSION,
        "signer_identity": OPERATOR_IDENTITY,
        "signer_fingerprint": OPERATOR_FINGERPRINT,
        "algorithm": OPERATOR_ALGORITHM,
        "signature_namespace": OPERATOR_SIGNATURE_NAMESPACE,
        "intent_id": intent["intent_id"],
        "intent_digest": intent["self_digest"],
        "source_head": source_head,
        "expected_host": intent["expected_host"],
        "applier_node_id": intent["applier_node_id"],
        "postcheck_node_id": intent["postcheck_node_id"],
        "issued_at": issued.isoformat().replace("+00:00", "Z"),
        "expires_at": expires.isoformat().replace("+00:00", "Z"),
    }
    authorization["authorization_digest"] = authorization_digest(
        authorization
    )
    return authorization


def validate_operator_authorization(
    authorization: Any,
    signature: bytes,
    *,
    intent: dict[str, Any],
    source_head: str,
    now: str,
    actual_host: str | None = None,
) -> list[str]:
    """Validate structure, exact-intent bindings, time, trust root, and SSHSIG."""

    errors: list[str] = []
    if not isinstance(authorization, dict):
        return ["operator authorization must be an object"]
    if set(authorization) != AUTHORIZATION_FIELDS:
        return ["operator authorization fields do not match the exact contract"]
    if authorization.get("schema_version") != AUTHORIZATION_SCHEMA_VERSION:
        errors.append("operator authorization schema_version is invalid")
    for field, expected in (
        ("signer_identity", OPERATOR_IDENTITY),
        ("signer_fingerprint", OPERATOR_FINGERPRINT),
        ("algorithm", OPERATOR_ALGORITHM),
        ("signature_namespace", OPERATOR_SIGNATURE_NAMESPACE),
    ):
        if authorization.get(field) != expected:
            errors.append(f"operator authorization {field} is invalid")
    if authorization.get("authorization_digest") != authorization_digest(
        authorization
    ):
        errors.append("operator authorization digest mismatch")
    if not HEAD_RE.fullmatch(str(source_head)):
        errors.append("operator authorization expected source head is invalid")
    if authorization.get("source_head") != source_head:
        errors.append("operator authorization source head differs from the effect")
    if not isinstance(intent, dict):
        errors.append("operator authorization exact intent is missing")
        intent = {}
    elif intent.get("self_digest") != intent_digest(intent):
        errors.append(
            "operator authorization exact intent self_digest is invalid"
        )
    for auth_field, intent_field in (
        ("intent_id", "intent_id"),
        ("intent_digest", "self_digest"),
        ("expected_host", "expected_host"),
        ("applier_node_id", "applier_node_id"),
        ("postcheck_node_id", "postcheck_node_id"),
    ):
        if authorization.get(auth_field) != intent.get(intent_field):
            errors.append(
                f"operator authorization {auth_field} differs from the exact intent"
            )
    if actual_host is not None and authorization.get("expected_host") != actual_host:
        errors.append(
            "operator authorization expected_host differs from the actual host"
        )
    try:
        issued = _instant(authorization["issued_at"])
        expires = _instant(authorization["expires_at"])
        current = _instant(now)
        intent_created = _instant(intent["created_at"])
        intent_expires = _instant(intent["expires_at"])
        if issued != intent_created:
            errors.append(
                "operator authorization issued_at differs from intent created_at"
            )
        if not issued <= current < expires:
            errors.append("operator authorization is not currently valid")
        if expires > intent_expires:
            errors.append("operator authorization outlives its exact intent")
        if expires - issued > MAX_AUTHORIZATION_TTL:
            errors.append("operator authorization TTL exceeds fifteen minutes")
    except (KeyError, TypeError, ValueError):
        errors.append("operator authorization timestamps are invalid")
    try:
        actual_fingerprint = trusted.ssh_public_key_fingerprint(
            OPERATOR_PUBLIC_KEY
        )
    except ValueError:
        actual_fingerprint = ""
    if not hmac.compare_digest(actual_fingerprint, OPERATOR_FINGERPRINT):
        errors.append("operator authorization trust-root fingerprint mismatch")
    if not trusted._verify_ssh_signature(
        canonical_bytes(authorization),
        signature,
        public_key=OPERATOR_PUBLIC_KEY,
        identity=OPERATOR_IDENTITY,
        namespace=OPERATOR_SIGNATURE_NAMESPACE,
    ):
        errors.append("operator authorization SSH signature is invalid")
    return errors
