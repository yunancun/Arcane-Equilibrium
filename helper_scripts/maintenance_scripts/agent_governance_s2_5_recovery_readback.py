#!/usr/bin/env python3
"""Fresh, read-only attestor Adapter for the S2.5 recovery anchor floor.

The public recovery builders never accept a path, transport, clock, nonce, or
current witness.  This leaf creates a fresh challenge and sends it only to one
code-owned AF_UNIX endpoint.  The external verifier's signed response is checked
by the recovery contract leaf; this Adapter records the read-only observation as
typed intent/result/postcheck/rollback receipts and grants no production authority.
"""

from __future__ import annotations

import json
import secrets
import socket
from datetime import datetime, timedelta, timezone
from typing import Any

from aiml_gate_receipt_schema_core import (
    _canonical_bytes,
    artifact_self_digest,
    canonical_digest,
)


ADAPTER_ID = "s2-5-recovery-anchor-current-readback-adapter-v1"
FIXED_ATTESTOR_SOCKET_PATH = (
    "/run/arcane-equilibrium/s2-5-recovery-anchor-readback.sock"
)
FIXED_STORE_ID = "s2-5-recovery-anchor-worm-v1"
QUERY_TTL_SECONDS = 5
SOCKET_TIMEOUT_SECONDS = 2.0
MAX_RESPONSE_BYTES = 65536

_COMMON = {
    "side_effect_class": "DISPOSABLE_TEST",
    "effect_class": "READ_ONLY_EXTERNAL_ATTESTATION",
    "target_class": "disposable_systemd",
    "production_effect": False,
    "production_authority": False,
    "production_runtime_effect_performed": False,
}
_INTENT_KEYS = frozenset({
    "schema_version", "adapter_id", "operation", "store_id", "anchor_scope_id",
    "challenge_nonce", "requested_at", "expires_at", "transport_class",
    "self_digest", *_COMMON,
})
_RESULT_KEYS = frozenset({
    "schema_version", "adapter_id", "intent_digest", "status",
    "effect_attempted", "response", "response_digest", "failure_code",
    "completed_at", "self_digest", *_COMMON,
})
_POSTCHECK_KEYS = frozenset({
    "schema_version", "adapter_id", "intent_digest", "result_digest", "status",
    "challenge_match", "query_digest_match", "store_match", "scope_match",
    "checked_at", "self_digest", *_COMMON,
})
_ROLLBACK_KEYS = frozenset({
    "schema_version", "adapter_id", "intent_digest", "result_digest",
    "postcheck_digest", "status", "mutation_performed", "rollback_attempted",
    "completed_at", "self_digest", *_COMMON,
})
_CHAIN_KEYS = frozenset({
    "schema_version", "adapter_id", "status", "intent", "result", "postcheck",
    "rollback", "self_digest", *_COMMON,
})


class RecoveryAnchorReadbackError(RuntimeError):
    """Stable fail-closed readback Adapter error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _trusted_now() -> datetime:
    return datetime.now(timezone.utc)


def _fresh_challenge_nonce() -> str:
    return "s2-5-readback-challenge-" + secrets.token_hex(32)


def _seal(value: dict[str, Any]) -> dict[str, Any]:
    artifact = dict(value)
    artifact["self_digest"] = artifact_self_digest(artifact)
    return artifact


def _exact(
    value: Any,
    keys: frozenset[str],
    label: str,
) -> list[str]:
    if not isinstance(value, dict):
        return [f"{label} must be an object"]
    actual = set(value)
    if actual != keys:
        return [
            f"{label} keys are not closed: missing={sorted(keys - actual)}, "
            f"extra={sorted(actual - keys)}"
        ]
    return []


def _fixed_transport_exchange(request_bytes: bytes) -> dict[str, Any]:
    """Query the single fixed local attestor endpoint with one JSON frame."""

    if len(request_bytes) > 16384:
        raise RecoveryAnchorReadbackError("readback_query_request_too_large")
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.settimeout(SOCKET_TIMEOUT_SECONDS)
        client.connect(FIXED_ATTESTOR_SOCKET_PATH)
        client.sendall(request_bytes + b"\n")
        payload = b""
        while b"\n" not in payload:
            chunk = client.recv(8192)
            if not chunk:
                raise RecoveryAnchorReadbackError(
                    "readback_query_response_truncated"
                )
            payload += chunk
            if len(payload) > MAX_RESPONSE_BYTES:
                raise RecoveryAnchorReadbackError(
                    "readback_query_response_too_large"
                )
    except RecoveryAnchorReadbackError:
        raise
    except (OSError, TimeoutError) as error:
        raise RecoveryAnchorReadbackError(
            "readback_query_transport_unavailable"
        ) from error
    finally:
        client.close()
    frame, _separator, trailing = payload.partition(b"\n")
    if trailing:
        raise RecoveryAnchorReadbackError(
            "readback_query_multiple_frames_rejected"
        )
    try:
        response = json.loads(frame.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise RecoveryAnchorReadbackError(
            "readback_query_response_invalid_json"
        ) from error
    if not isinstance(response, dict):
        raise RecoveryAnchorReadbackError(
            "readback_query_response_not_an_object"
        )
    return response


def _intent(*, anchor_scope_id: str) -> dict[str, Any]:
    if not isinstance(anchor_scope_id, str) or not anchor_scope_id:
        raise RecoveryAnchorReadbackError("readback_query_scope_invalid")
    moment = _trusted_now()
    return _seal({
        "schema_version": "s2_5_recovery_anchor_readback_query_intent_v1",
        "adapter_id": ADAPTER_ID,
        "operation": "READ_CURRENT_EXTERNAL_ANCHOR",
        "store_id": FIXED_STORE_ID,
        "anchor_scope_id": anchor_scope_id,
        "challenge_nonce": _fresh_challenge_nonce(),
        "requested_at": moment.isoformat(),
        "expires_at": (
            moment + timedelta(seconds=QUERY_TTL_SECONDS)
        ).isoformat(),
        "transport_class": "CODE_OWNED_FIXED_UNIX_SOCKET",
        **_COMMON,
    })


def _failure_chain(
    intent: dict[str, Any],
    *,
    code: str,
) -> dict[str, Any]:
    moment = _trusted_now().isoformat()
    result = _seal({
        "schema_version": "s2_5_recovery_anchor_readback_query_result_v1",
        "adapter_id": ADAPTER_ID,
        "intent_digest": intent["self_digest"],
        "status": "EXTERNAL_VERIFICATION_PENDING",
        "effect_attempted": True,
        "response": None,
        "response_digest": None,
        "failure_code": code,
        "completed_at": moment,
        **_COMMON,
    })
    postcheck = _seal({
        "schema_version": "s2_5_recovery_anchor_readback_query_postcheck_v1",
        "adapter_id": ADAPTER_ID,
        "intent_digest": intent["self_digest"],
        "result_digest": result["self_digest"],
        "status": "UNVERIFIED",
        "challenge_match": False,
        "query_digest_match": False,
        "store_match": False,
        "scope_match": False,
        "checked_at": moment,
        **_COMMON,
    })
    rollback = _seal({
        "schema_version": "s2_5_recovery_anchor_readback_query_rollback_v1",
        "adapter_id": ADAPTER_ID,
        "intent_digest": intent["self_digest"],
        "result_digest": result["self_digest"],
        "postcheck_digest": postcheck["self_digest"],
        "status": "NOT_REQUIRED_READ_ONLY",
        "mutation_performed": False,
        "rollback_attempted": False,
        "completed_at": moment,
        **_COMMON,
    })
    return _seal({
        "schema_version": "s2_5_recovery_anchor_readback_query_chain_v1",
        "adapter_id": ADAPTER_ID,
        "status": "EXTERNAL_VERIFICATION_PENDING",
        "intent": intent,
        "result": result,
        "postcheck": postcheck,
        "rollback": rollback,
        **_COMMON,
    })


def _query_current_anchor_readback(
    *,
    anchor_scope_id: str,
) -> dict[str, Any]:
    """Return one typed fresh-query chain; no caller may supply its transport."""

    intent = _intent(anchor_scope_id=anchor_scope_id)
    try:
        response = _fixed_transport_exchange(_canonical_bytes(intent))
    except RecoveryAnchorReadbackError as error:
        chain = _failure_chain(intent, code=error.code)
        errors = validate_current_readback_chain(chain)
        if errors:
            raise RecoveryAnchorReadbackError(
                "readback_query_generated_failure_chain_invalid"
            )
        return chain
    response_digest = canonical_digest(response)
    checks = {
        "challenge_match": (
            response.get("challenge_nonce") == intent["challenge_nonce"]
        ),
        "query_digest_match": (
            response.get("query_digest") == intent["self_digest"]
        ),
        "store_match": response.get("store_id") == intent["store_id"],
        "scope_match": (
            response.get("anchor_scope_id") == intent["anchor_scope_id"]
        ),
    }
    verified_frame = all(checks.values())
    result = _seal({
        "schema_version": "s2_5_recovery_anchor_readback_query_result_v1",
        "adapter_id": ADAPTER_ID,
        "intent_digest": intent["self_digest"],
        "status": "OBSERVED",
        "effect_attempted": True,
        "response": response,
        "response_digest": response_digest,
        "failure_code": (
            None
            if verified_frame
            else "readback_query_fresh_binding_mismatch"
        ),
        "completed_at": _trusted_now().isoformat(),
        **_COMMON,
    })
    postcheck = _seal({
        "schema_version": "s2_5_recovery_anchor_readback_query_postcheck_v1",
        "adapter_id": ADAPTER_ID,
        "intent_digest": intent["self_digest"],
        "result_digest": result["self_digest"],
        "status": "FRAME_BOUND" if verified_frame else "UNVERIFIED",
        **checks,
        "checked_at": _trusted_now().isoformat(),
        **_COMMON,
    })
    rollback = _seal({
        "schema_version": "s2_5_recovery_anchor_readback_query_rollback_v1",
        "adapter_id": ADAPTER_ID,
        "intent_digest": intent["self_digest"],
        "result_digest": result["self_digest"],
        "postcheck_digest": postcheck["self_digest"],
        "status": "NOT_REQUIRED_READ_ONLY",
        "mutation_performed": False,
        "rollback_attempted": False,
        "completed_at": _trusted_now().isoformat(),
        **_COMMON,
    })
    chain = _seal({
        "schema_version": "s2_5_recovery_anchor_readback_query_chain_v1",
        "adapter_id": ADAPTER_ID,
        "status": (
            "OBSERVED_UNVERIFIED_SIGNATURE"
            if verified_frame
            else "EXTERNAL_VERIFICATION_PENDING"
        ),
        "intent": intent,
        "result": result,
        "postcheck": postcheck,
        "rollback": rollback,
        **_COMMON,
    })
    errors = validate_current_readback_chain(chain)
    if errors:
        raise RecoveryAnchorReadbackError(
            "readback_query_generated_chain_invalid"
        )
    return chain


def validate_current_readback_chain(value: Any) -> list[str]:
    """Revalidate every closed Adapter receipt and its digest links."""

    errors = _exact(value, _CHAIN_KEYS, "readback query chain")
    if not isinstance(value, dict):
        return errors
    artifacts = (
        ("intent", _INTENT_KEYS),
        ("result", _RESULT_KEYS),
        ("postcheck", _POSTCHECK_KEYS),
        ("rollback", _ROLLBACK_KEYS),
    )
    for name, keys in artifacts:
        artifact = value.get(name)
        errors.extend(_exact(artifact, keys, f"readback query {name}"))
        if isinstance(artifact, dict) and artifact.get(
            "self_digest"
        ) != artifact_self_digest(artifact):
            errors.append(f"readback query {name} self_digest does not re-derive")
        if isinstance(artifact, dict):
            for field, expected in _COMMON.items():
                if type(artifact.get(field)) is not type(expected) or (
                    artifact.get(field) != expected
                ):
                    errors.append(
                        f"readback query {name} {field} differs from Adapter"
                    )
    if value.get("self_digest") != artifact_self_digest(value):
        errors.append("readback query chain self_digest does not re-derive")
    for field, expected in _COMMON.items():
        if type(value.get(field)) is not type(expected) or value.get(
            field
        ) != expected:
            errors.append(f"readback query chain {field} differs from Adapter")
    intent = value.get("intent")
    result = value.get("result")
    postcheck = value.get("postcheck")
    rollback = value.get("rollback")
    if not all(
        isinstance(item, dict)
        for item in (intent, result, postcheck, rollback)
    ):
        return errors
    if value.get("adapter_id") != ADAPTER_ID or any(
        item.get("adapter_id") != ADAPTER_ID
        for item in (intent, result, postcheck, rollback)
    ):
        errors.append("readback query Adapter identity differs")
    expected_schemas = {
        "chain": "s2_5_recovery_anchor_readback_query_chain_v1",
        "intent": "s2_5_recovery_anchor_readback_query_intent_v1",
        "result": "s2_5_recovery_anchor_readback_query_result_v1",
        "postcheck": "s2_5_recovery_anchor_readback_query_postcheck_v1",
        "rollback": "s2_5_recovery_anchor_readback_query_rollback_v1",
    }
    for name, artifact in (
        ("chain", value),
        ("intent", intent),
        ("result", result),
        ("postcheck", postcheck),
        ("rollback", rollback),
    ):
        if artifact.get("schema_version") != expected_schemas[name]:
            errors.append(f"readback query {name} schema is invalid")
    if intent.get("operation") != "READ_CURRENT_EXTERNAL_ANCHOR":
        errors.append("readback query intent operation is invalid")
    if intent.get("store_id") != FIXED_STORE_ID:
        errors.append("readback query intent store is not fixed")
    if intent.get("transport_class") != "CODE_OWNED_FIXED_UNIX_SOCKET":
        errors.append("readback query intent transport is not fixed")
    nonce = intent.get("challenge_nonce")
    nonce_prefix = "s2-5-readback-challenge-"
    if not (
        isinstance(nonce, str)
        and nonce.startswith(nonce_prefix)
        and len(nonce) == len(nonce_prefix) + 64
        and all(character in "0123456789abcdef" for character in nonce[len(nonce_prefix):])
    ):
        errors.append("readback query intent challenge nonce is invalid")
    if result.get("intent_digest") != intent.get("self_digest"):
        errors.append("readback query result does not bind intent")
    if postcheck.get("intent_digest") != intent.get("self_digest"):
        errors.append("readback query postcheck does not bind intent")
    if postcheck.get("result_digest") != result.get("self_digest"):
        errors.append("readback query postcheck does not bind result")
    if rollback.get("intent_digest") != intent.get("self_digest"):
        errors.append("readback query rollback does not bind intent")
    if rollback.get("result_digest") != result.get("self_digest"):
        errors.append("readback query rollback does not bind result")
    if rollback.get("postcheck_digest") != postcheck.get("self_digest"):
        errors.append("readback query rollback does not bind postcheck")
    response = result.get("response")
    if response is None:
        if result.get("response_digest") is not None:
            errors.append("readback query absent response has a digest")
    elif not isinstance(response, dict):
        errors.append("readback query response must be an object")
    elif result.get("response_digest") != canonical_digest(response):
        errors.append("readback query response digest does not re-derive")
    stored_checks = {
        "challenge_match": postcheck.get("challenge_match"),
        "query_digest_match": postcheck.get("query_digest_match"),
        "store_match": postcheck.get("store_match"),
        "scope_match": postcheck.get("scope_match"),
    }
    if any(not isinstance(item, bool) for item in stored_checks.values()):
        errors.append("readback query postcheck booleans are invalid")
    binding_fields = {
        "challenge_nonce": ("challenge_match", intent.get("challenge_nonce")),
        "query_digest": ("query_digest_match", intent.get("self_digest")),
        "store_id": ("store_match", intent.get("store_id")),
        "anchor_scope_id": ("scope_match", intent.get("anchor_scope_id")),
    }
    derived_checks = {
        check_field: (
            isinstance(response, dict)
            and response.get(response_field) == expected
        )
        for response_field, (check_field, expected) in binding_fields.items()
    }
    for response_field, (check_field, _expected) in binding_fields.items():
        if stored_checks[check_field] is not derived_checks[check_field]:
            errors.append(
                f"readback query {response_field} binding does not re-derive"
            )
    frame_bound = all(derived_checks.values())
    if (postcheck.get("status") == "FRAME_BOUND") != frame_bound:
        errors.append("readback query postcheck status differs from frame binding")
    expected_result_status = (
        "OBSERVED"
        if isinstance(response, dict)
        else "EXTERNAL_VERIFICATION_PENDING"
    )
    if result.get("status") != expected_result_status:
        errors.append("readback query result status differs from response")
    expected_failure_code = (
        None
        if frame_bound
        else "readback_query_fresh_binding_mismatch"
        if isinstance(response, dict)
        else result.get("failure_code")
    )
    if result.get("failure_code") != expected_failure_code or (
        response is None
        and not isinstance(result.get("failure_code"), str)
    ):
        errors.append("readback query failure code differs from response")
    if result.get("effect_attempted") is not True:
        errors.append("readback query result must record the read-only attempt")
    if rollback.get("status") != "NOT_REQUIRED_READ_ONLY":
        errors.append("readback query rollback status is invalid")
    if rollback.get("mutation_performed") is not False:
        errors.append("readback query cannot report a mutation")
    if rollback.get("rollback_attempted") is not False:
        errors.append("readback query cannot attempt rollback")
    expected_chain_status = (
        "OBSERVED_UNVERIFIED_SIGNATURE"
        if frame_bound and result.get("status") == "OBSERVED"
        else "EXTERNAL_VERIFICATION_PENDING"
    )
    if value.get("status") != expected_chain_status:
        errors.append("readback query chain status differs from receipts")
    return errors
