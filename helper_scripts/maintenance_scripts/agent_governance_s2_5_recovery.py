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
from datetime import datetime, timezone
from typing import Any

from aiml_gate_receipt_schema_core import (
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
_BINDING_KEYS = frozenset({
    "task_digest", "unresolved_state_digest", "state_root_identity", "journal_set",
    "replay_ledger_head", "pre_state", "source_head", "host_identity", "authorization",
    "trusted_anchor", "actor_identity", "actor_process", "kernel_binding_digest",
    "admission_digest",
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
    "authorization_id", "authorization_digest", "issued_at", "expires_at", "consume_once",
})
_ANCHOR_KEYS = frozenset({
    "schema_version", "anchor_id", "anchor_digest", "storage_class", "anchor_scope_id",
    "bound_state_root_id", "source_head", "host_identity", "reference_digest",
})
_NODE_KEYS = frozenset({"node_id", "role", "permission"})
_PROCESS_KEYS = frozenset({"uid", "cgroup"})
_CAPTURE_KEYS = frozenset({
    "schema_version", "source_head", "host_identity", "node_identity",
    "process_identity", "observed_at", "capture_digest",
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


def _binding_errors(binding: Any) -> list[str]:
    errors = _exact(binding, _BINDING_KEYS, "recovery_binding")
    if errors:
        return errors
    errors.extend(_exact(binding["state_root_identity"], _ROOT_KEYS, "state_root_identity"))
    errors.extend(_exact(binding["journal_set"], _JOURNAL_KEYS, "journal_set"))
    errors.extend(_exact(binding["replay_ledger_head"], _LEDGER_KEYS, "replay_ledger_head"))
    errors.extend(_exact(binding["pre_state"], _STATE_KEYS, "pre_state"))
    errors.extend(_exact(binding["authorization"], _AUTH_KEYS, "authorization"))
    errors.extend(_exact(binding["trusted_anchor"], _ANCHOR_KEYS, "trusted_anchor"))
    errors.extend(_exact(binding["actor_identity"], _NODE_KEYS, "bound actor_identity"))
    errors.extend(_exact(binding["actor_process"], _PROCESS_KEYS, "bound actor_process"))
    errors.extend(_sealed(
        binding["authorization"], "authorization_digest", "authorization"
    ))
    errors.extend(_sealed(
        binding["trusted_anchor"], "reference_digest", "trusted_anchor"
    ))
    anchor = binding["trusted_anchor"]
    root = binding["state_root_identity"]
    if anchor.get("storage_class") != "INDEPENDENT_OFF_STATE_ROOT":
        errors.append("trusted anchor is not independently stored off the state root")
    if anchor.get("anchor_scope_id") == anchor.get("bound_state_root_id"):
        errors.append("trusted anchor scope must differ from the replaceable state root")
    if anchor.get("bound_state_root_id") != root.get("root_id"):
        errors.append("trusted anchor does not bind the exact state-root identity")
    if anchor.get("source_head") != binding.get("source_head"):
        errors.append("trusted anchor source_head differs from the recovery binding")
    if anchor.get("host_identity") != binding.get("host_identity"):
        errors.append("trusted anchor host_identity differs from the recovery binding")
    journals = binding["journal_set"]
    if journals.get("head_digest") not in journals.get("journal_digests", []):
        errors.append("journal head is not a member of the exact journal set")
    if binding["authorization"].get("consume_once") is not True:
        errors.append("recovery authorization must be consume-once")
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
    return hits


def _capture_errors(capture: Any, *, permission: str) -> list[str]:
    errors = _exact(capture, _CAPTURE_KEYS, "capture")
    if errors:
        return errors
    errors.extend(_exact(capture["node_identity"], _NODE_KEYS, "capture node_identity"))
    errors.extend(_exact(capture["process_identity"], _PROCESS_KEYS, "capture process_identity"))
    errors.extend(_sealed(capture, "capture_digest", "capture"))
    if capture["node_identity"].get("permission") != permission:
        errors.append(f"capture permission must be {permission}")
    return errors


def _fresh_authorization_errors(binding: dict[str, Any], now: Any) -> list[str]:
    authorization = binding["authorization"]
    try:
        issued = _parse_timestamp(str(authorization["issued_at"]))
        expires = _parse_timestamp(str(authorization["expires_at"]))
        current = (
            datetime.now(timezone.utc)
            if now is None
            else _parse_timestamp(now) if isinstance(now, str) else now
        )
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
    now: Any = None,
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
    }
    errors.extend(_binding_errors(binding))
    if now is not None:
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
    errors.extend(_capture_errors(actor_capture, permission="effect"))
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
) -> dict[str, Any]:
    errors = validate_recovery_artifact(intent)
    errors.extend(validate_recovery_artifact(rollback))
    errors.extend(_capture_errors(actor_capture, permission="effect"))
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
        "authorization_consumed": True,
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
    errors.extend(_capture_errors(verifier_capture, permission="read_only"))
    if result.get("recovery_intent_digest") != intent.get("intent_digest"):
        errors.append("postcheck result is bound to a different intent")
    if verifier_capture.get("source_head") != intent.get("recovery_binding", {}).get("source_head"):
        errors.append("postcheck source_head differs from intent")
    if verifier_capture.get("host_identity") != intent.get("recovery_binding", {}).get("host_identity"):
        errors.append("postcheck host differs from intent")
    if status not in {"RECOVERY_CLEARED", "RECOVERY_UNRESOLVED"}:
        errors.append("unsupported recovery postcheck status")
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
    errors.extend(_binding_errors(artifact.get("recovery_binding")))
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
        errors.extend(_capture_errors(artifact.get("actor_capture"), permission="effect"))
        if artifact.get("actor_capture_digest") != artifact.get("actor_capture", {}).get(
            "capture_digest"
        ):
            errors.append("rollback actor capture digest differs from the bound capture")
        if artifact.get("actor_identity") != artifact.get("actor_capture", {}).get(
            "node_identity"
        ):
            errors.append("rollback actor identity is not derived from its capture")
        if artifact.get("actor_process") != artifact.get("actor_capture", {}).get(
            "process_identity"
        ):
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
        errors.extend(_capture_errors(artifact.get("actor_capture"), permission="effect"))
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
        if artifact.get("authorization_consumed") is not True:
            errors.append("recovery result does not prove consume-once authorization consumption")
    elif schema == "s2_5_recovery_postcheck_v1":
        errors.extend(_capture_errors(
            artifact.get("verifier_capture"), permission="read_only"
        ))
        if artifact.get("verifier_capture_digest") != artifact.get(
            "verifier_capture", {}
        ).get("capture_digest"):
            errors.append("postcheck verifier capture digest differs from the capture")
        if artifact.get("verifier_identity") != artifact.get(
            "verifier_capture", {}
        ).get("node_identity"):
            errors.append("postcheck verifier identity is not derived from its capture")
        if artifact.get("verifier_process") != artifact.get(
            "verifier_capture", {}
        ).get("process_identity"):
            errors.append("postcheck verifier process is not derived from its capture")
        expected = canonical_digest(_without(artifact, "postcheck_id", "self_digest"))
        if artifact.get("postcheck_id") != expected:
            errors.append("recovery postcheck identity does not re-derive")
        if artifact.get("observed_state_digest") != canonical_digest(
            artifact.get("observed_state")
        ):
            errors.append("postcheck observed-state digest does not re-derive")
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
    if recovery_result["actor_process"] == independent_postcheck["verifier_process"]:
        errors.append("recovery verifier must be a different process")
    if actor != binding["actor_identity"]:
        errors.append("recovery actor was renamed or differs from the kernel-bound actor")
    if recovery_result["actor_process"] != binding["actor_process"]:
        errors.append("recovery actor process differs from the kernel-bound process")
    authorization_id = binding["authorization"]["authorization_id"]
    if authorization_id in consumed_authorization_ids:
        errors.append("recovery authorization was already consumed")
    return errors
