#!/usr/bin/env python3
"""Closed, source-only S2.5 durable recovery-controller v2 contracts.

Recovery lifecycle and anchor transport are deliberately orthogonal:

``PREPARED -> CONSUMED -> COMMITTED -> RESOLVED`` records local durable
facts, while ``OUTBOX_PREPARED -> PROOF_ATTACHED_UNVERIFIED`` records only
byte-exact anchor transport.  This module never promotes a local proof to
external trust, admits an effect, clears a latch, or performs persistence.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
for _candidate in (Path(__file__).resolve().parent, ML_TRAINING_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import aiml_gate_receipt_s2_5_host_capture as host_capture  # noqa: E402
import aiml_gate_receipt_validator as central_validator  # noqa: E402
from agent_governance_schema import schema_subset_errors  # noqa: E402
from agent_governance_s2_5_disposable_profile import (  # noqa: E402
    DISPOSABLE_STATE_ROOT,
    PROFILE_EVIDENCE_CLASS,
    PROFILE_ID,
    PROFILE_TARGET_CLASS,
    SIDE_EFFECT_CLASS,
    STATUS_UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED,
)


STATE_SCHEMA = "s2_5_recovery_controller_state_v2"
TRANSITION_SCHEMA = "s2_5_recovery_controller_transition_v2"
OUTBOX_SCHEMA = "s2_5_recovery_anchor_outbox_v1"
PROOF_SCHEMA = "s2_5_recovery_anchor_proof_v1"
MANIFEST_SCHEMA = "s2_5_recovery_store_manifest_v2"
_SCHEMA_DIR = REPO_ROOT / ".codex" / "schemas"
_SCHEMAS = frozenset({
    STATE_SCHEMA,
    TRANSITION_SCHEMA,
    OUTBOX_SCHEMA,
    PROOF_SCHEMA,
    MANIFEST_SCHEMA,
})
_PHASES = ("PREPARED", "CONSUMED", "COMMITTED", "RESOLVED")
_PHASE_EDGES = frozenset({
    ("GENESIS", "PREPARED"),
    ("PREPARED", "CONSUMED"),
    ("CONSUMED", "COMMITTED"),
    ("COMMITTED", "RESOLVED"),
})
_UNRESOLVED_KEYS = frozenset({
    "schema_version",
    "start_id",
    "reasons",
    "task_digest",
    "stable_root_id",
    "state_root_id",
    "journal_set_digest",
    "replay_ledger_head_digest",
    "pre_state",
    "source_head",
    "failure_host_capture_digest",
    "side_effect_class",
    "production_effect",
    "production_authority",
    "target_class",
})
_PRE_STATE_KEYS = frozenset({
    "active_state",
    "unit_file_state",
    "n_restarts",
    "invocation_id",
})
_INTENT_KEYS = frozenset({
    "schema_version",
    "recovery_id",
    "authorization_id",
    "task_digest",
    "start_id",
    "source_head",
    "action",
    "side_effect_class",
    "target_class",
    "production_effect",
    "production_authority",
    "self_digest",
})
_PHASE_ARTIFACT_BASE_KEYS = frozenset({
    "schema_version",
    "authorization_id",
    "recovery_intent_digest",
    "source_head",
    "start_id",
    "side_effect_class",
    "target_class",
    "production_effect",
    "production_authority",
    "self_digest",
})
_PHASE_ARTIFACT_SPECS = {
    "consumption": (
        "s2_5_recovery_consumption_ref_v2",
        _PHASE_ARTIFACT_BASE_KEYS | {"replay_ledger_head_digest"},
    ),
    "effect result": (
        "s2_5_recovery_effect_result_ref_v2",
        _PHASE_ARTIFACT_BASE_KEYS | {"status"},
    ),
    "rollback result": (
        "s2_5_recovery_rollback_ref_v2",
        _PHASE_ARTIFACT_BASE_KEYS | {"status"},
    ),
    "independent postcheck": (
        "s2_5_recovery_postcheck_ref_v2",
        _PHASE_ARTIFACT_BASE_KEYS | {"status"},
    ),
}
_PHASE_ARTIFACT_SUCCESS_STATUS = {
    "effect result": "RECOVERY_APPLIED",
    "rollback result": "ROLLBACK_APPLIED",
    "independent postcheck": "RECOVERY_CLEARED",
}
_FIXED_PRE_STATE = {
    "active_state": "inactive",
    "unit_file_state": "disabled",
    "n_restarts": 0,
    "invocation_id": "none",
}
_OUTBOX_REQUEST_KEYS = frozenset({
    "schema_version",
    "transition_digest",
    "candidate_subject_digest",
    "prior_manifest_digest",
    "expected_external_sequence",
    "expected_external_head_digest",
    "expected_snapshot_id",
    "expected_latest_version_id",
    "candidate_external_sequence",
    "idempotency_key",
    "source_head",
    "start_id",
    "operation",
    "phase",
})
_COMMON = {
    "side_effect_class": SIDE_EFFECT_CLASS,
    "target_class": PROFILE_TARGET_CLASS,
    "target_profile_id": PROFILE_ID,
    "production_effect": False,
    "production_authority": False,
    "production_effect_count": 0,
}
_SUBJECT_COMMON = {
    **_COMMON,
    "trust_status": STATUS_UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED,
}
_CHAIN_IMMUTABLE_SUBJECT_KEYS = (
    "controller_id",
    "stable_host_facts",
    "host_identity",
    "canonical_state_root",
    "stable_root_id",
    "state_root_identity",
    "state_root_id",
    "source_head",
    "start_id",
    "task_digest",
    "operation",
    "authorization_id",
    "unresolved_payload_json",
    "unresolved_state_digest",
    "failure_host_capture_json",
    "failure_host_capture_digest",
    "recovery_admission_capture_json",
    "recovery_admission_capture_digest",
    "journal_inventory",
    "journal_set_digest",
    "recovery_intent_json",
    "recovery_intent_digest",
    "trust_status",
    "side_effect_class",
    "target_class",
    "target_profile_id",
    "production_effect",
    "production_authority",
    "production_effect_count",
)
_PROOF_ATTACH_IMMUTABLE_KEYS = _CHAIN_IMMUTABLE_SUBJECT_KEYS + (
    "phase",
    "replay_ledger",
    "replay_ledger_head_digest",
    "consumed_authorization_ids",
    "consumption_proof_json",
    "consumption_proof_digest",
    "effect_result_json",
    "effect_result_digest",
    "rollback_result_json",
    "rollback_result_digest",
    "independent_postcheck_json",
    "independent_postcheck_digest",
    "prior_phase_anchor_proof_digest",
    "previous_external_sequence",
    "previous_external_head_digest",
    "external_monotonic_floor",
    "external_snapshot_id",
    "external_latest_version_id",
)


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _exact(value: Any, keys: frozenset[str], label: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{label} must be an object"]
    actual = set(value)
    if actual == keys:
        return []
    return [
        f"{label} keys are not closed: missing={sorted(keys - actual)}, "
        f"extra={sorted(actual - keys)}"
    ]


def _parse_canonical_object(
    value: Any, *, label: str
) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(value, str):
        return {}, [f"{label} must be canonical JSON text"]
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}, [f"{label} is not valid JSON"]
    if not isinstance(parsed, dict):
        return {}, [f"{label} must encode an object"]
    if _canonical_json(parsed) != value:
        return parsed, [f"{label} is not canonical JSON"]
    return parsed, []


def _aware_time(value: Any, *, label: str) -> tuple[datetime | None, list[str]]:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None, [f"{label} is not a valid timestamp"]
    if parsed.tzinfo is None:
        return None, [f"{label} must be timezone-aware"]
    return parsed, []


@lru_cache(maxsize=None)
def _schema(schema_version: str) -> dict[str, Any]:
    if schema_version not in _SCHEMAS:
        raise ValueError("controller schema_version is unknown")
    path = _SCHEMA_DIR / f"{schema_version}.schema.json"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError("controller schema is unavailable") from error
    if not isinstance(loaded, dict):
        raise ValueError("controller schema must be an object")
    return loaded


def derive_stable_root_id(capture: dict[str, Any]) -> str:
    """Derive the restart-stable root from signed host identity and fixed path."""

    return central_validator.canonical_digest({
        "schema_version": "s2_5_recovery_stable_root_identity_v2",
        "host_identity": capture.get("host_identity"),
        "canonical_path": DISPOSABLE_STATE_ROOT,
    })


def derive_controller_id(*, stable_root_id: str, source_head: str) -> str:
    digest = central_validator.canonical_digest({
        "schema_version": "s2_5_recovery_controller_identity_v2",
        "stable_root_id": stable_root_id,
        "source_head": source_head,
        "target_profile_id": PROFILE_ID,
    })
    return "s2-5-controller-" + digest.removeprefix("sha256:")


def derive_candidate_subject_digest(subject: dict[str, Any]) -> str:
    return central_validator.canonical_digest({
        "schema_version": "s2_5_recovery_candidate_subject_digest_v2",
        "candidate_subject": subject,
    })


def derive_transition_id(transition: dict[str, Any]) -> str:
    subject = {
        key: value
        for key, value in transition.items()
        if key not in {"transition_id", "self_digest"}
    }
    digest = central_validator.canonical_digest({
        "schema_version": "s2_5_recovery_controller_transition_identity_v2",
        "subject": subject,
    })
    return "s2-5-transition-" + digest.removeprefix("sha256:")


def derive_outbox_idempotency(request: dict[str, Any]) -> str:
    subject = {
        key: value
        for key, value in request.items()
        if key != "idempotency_key"
    }
    digest = central_validator.canonical_digest({
        "schema_version": "s2_5_recovery_anchor_idempotency_v2",
        "subject": subject,
    })
    return "s2-5-anchor-idempotency-" + digest.removeprefix("sha256:")


def derive_store_id(state_root_id: str) -> str:
    digest = central_validator.canonical_digest({
        "profile_id": PROFILE_ID,
        "state_root_id": state_root_id,
    })
    return "s2-5-store-" + digest.removeprefix("sha256:")


def _candidate_schema_errors(subject: Any) -> list[str]:
    root = _schema(STATE_SCHEMA)
    candidate_schema = root.get("$defs", {}).get("candidate")
    if not isinstance(candidate_schema, dict):
        return ["candidate subject schema is unavailable"]
    return schema_subset_errors(subject, candidate_schema, root)


def _capture_errors(
    raw: Any,
    digest: Any,
    *,
    label: str,
    subject: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    capture, errors = _parse_canonical_object(raw, label=label)
    if capture:
        errors.extend(
            f"{label}: {error}"
            for error in (
                host_capture.validate_s2_5_recovery_host_capture_integrity(
                    capture
                )
            )
        )
        if digest != capture.get("self_digest"):
            errors.append(f"{label} digest differs from exact signed capture")
        if capture.get("source_head") != subject.get("source_head"):
            errors.append(f"{label} source_head differs from candidate subject")
        manager = capture.get("boot_manager_facts")
        if (
            not isinstance(manager, dict)
            or manager.get("canonical_state_root") != DISPOSABLE_STATE_ROOT
        ):
            errors.append(f"{label} does not bind the fixed state-root path")
    return capture, errors


def _embedded_artifact_errors(
    raw: Any,
    digest: Any,
    *,
    label: str,
    subject: dict[str, Any],
    required: bool,
) -> list[str]:
    if raw is None or digest is None:
        if raw is None and digest is None and not required:
            return []
        return [f"{label} JSON and digest must be present together"]
    artifact, errors = _parse_canonical_object(raw, label=label)
    if not artifact:
        return errors
    schema_version, keys = _PHASE_ARTIFACT_SPECS[label]
    errors.extend(_exact(artifact, keys, label))
    if artifact.get("schema_version") != schema_version:
        errors.append(f"{label} schema_version is invalid")
    if artifact.get("self_digest") != central_validator.artifact_self_digest(
        artifact
    ):
        errors.append(f"{label} self_digest does not re-derive")
    if digest != artifact.get("self_digest"):
        errors.append(f"{label} digest differs from exact artifact")
    pairs = {
        "authorization_id": "authorization_id",
        "recovery_intent_digest": "recovery_intent_digest",
        "source_head": "source_head",
        "start_id": "start_id",
    }
    for artifact_key, subject_key in pairs.items():
        if artifact.get(artifact_key) != subject.get(subject_key):
            errors.append(f"{label} {artifact_key} differs from candidate")
    for key, expected in (
        ("side_effect_class", SIDE_EFFECT_CLASS),
        ("target_class", PROFILE_TARGET_CLASS),
        ("production_effect", False),
        ("production_authority", False),
    ):
        if artifact.get(key) != expected:
            errors.append(f"{label} {key} violates the fixed boundary")
    expected_status = _PHASE_ARTIFACT_SUCCESS_STATUS.get(label)
    if expected_status is not None and artifact.get("status") != expected_status:
        errors.append(f"{label} status must be {expected_status}")
    if label == "consumption" and artifact.get(
        "replay_ledger_head_digest"
    ) != subject.get("replay_ledger_head_digest"):
        errors.append("consumption replay head differs from candidate")
    return errors


def _subject_errors(subject: Any) -> list[str]:
    errors = _candidate_schema_errors(subject)
    if errors or not isinstance(subject, dict):
        return errors
    for key, expected in _SUBJECT_COMMON.items():
        if subject.get(key) != expected:
            errors.append(f"candidate subject {key} differs from fixed profile")

    stable_root_id = subject.get("stable_root_id")
    if subject.get("controller_id") != derive_controller_id(
        stable_root_id=str(stable_root_id),
        source_head=str(subject.get("source_head")),
    ):
        errors.append("candidate controller id does not re-derive")
    if stable_root_id == subject.get("state_root_id"):
        errors.append("stable and live root identities must differ")
    if subject.get("canonical_state_root") != DISPOSABLE_STATE_ROOT:
        errors.append("candidate state-root path is not code-owned")
    identity = subject.get("state_root_identity")
    if (
        not isinstance(identity, dict)
        or subject.get("state_root_id")
        != central_validator.canonical_digest(identity)
    ):
        errors.append("candidate live state-root id does not re-derive")

    generation = subject.get("generation")
    previous_state = subject.get("previous_controller_state_digest")
    previous_manifest = subject.get("previous_manifest_digest")
    if generation == 1:
        if previous_state is not None or previous_manifest is not None:
            errors.append("generation-one candidate cannot have predecessors")
        if (
            subject.get("phase") != "PREPARED"
            or subject.get("anchor_progress") != "OUTBOX_PREPARED"
        ):
            errors.append(
                "generation one is only PREPARED with OUTBOX_PREPARED"
            )
        if (
            subject.get("previous_external_sequence") != 0
            or subject.get("previous_external_head_digest") is not None
            or subject.get("external_monotonic_floor") != 0
        ):
            errors.append("generation-one external anchor baseline is not empty")
    elif isinstance(generation, int):
        if previous_state is None or previous_manifest is None:
            errors.append("candidate generation after one requires both predecessors")

    failure_capture, capture_errors = _capture_errors(
        subject.get("failure_host_capture_json"),
        subject.get("failure_host_capture_digest"),
        label="failure host capture",
        subject=subject,
    )
    errors.extend(capture_errors)
    admission_capture, capture_errors = _capture_errors(
        subject.get("recovery_admission_capture_json"),
        subject.get("recovery_admission_capture_digest"),
        label="recovery admission capture",
        subject=subject,
    )
    errors.extend(capture_errors)
    if failure_capture and admission_capture:
        if (
            failure_capture.get("stable_host_facts")
            != admission_capture.get("stable_host_facts")
            or failure_capture.get("host_identity")
            != admission_capture.get("host_identity")
        ):
            errors.append("historical and admission captures bind different hosts")
        if subject.get("stable_host_facts") != admission_capture.get(
            "stable_host_facts"
        ):
            errors.append("candidate stable host facts differ from signed capture")
        if subject.get("host_identity") != admission_capture.get(
            "host_identity"
        ):
            errors.append("candidate host identity differs from signed capture")
        if stable_root_id != derive_stable_root_id(admission_capture):
            errors.append("candidate stable-root id does not re-derive")
        failure_time, time_errors = _aware_time(
            failure_capture.get("observed_at"), label="failure observed_at"
        )
        admission_time, admission_time_errors = _aware_time(
            admission_capture.get("observed_at"),
            label="admission observed_at",
        )
        errors.extend(time_errors)
        errors.extend(admission_time_errors)
        if (
            failure_time is not None
            and admission_time is not None
            and admission_time <= failure_time
        ):
            errors.append("recovery admission capture is not later than failure")

    unresolved, unresolved_errors = _parse_canonical_object(
        subject.get("unresolved_payload_json"), label="unresolved payload"
    )
    errors.extend(unresolved_errors)
    errors.extend(_exact(unresolved, _UNRESOLVED_KEYS, "unresolved payload"))
    if unresolved:
        if unresolved.get("schema_version") != (
            "s2_5_recovery_unresolved_payload_v2"
        ):
            errors.append("unresolved payload schema_version is invalid")
        for key in (
            "start_id",
            "task_digest",
            "stable_root_id",
            "state_root_id",
            "journal_set_digest",
            "source_head",
            "failure_host_capture_digest",
        ):
            if unresolved.get(key) != subject.get(key):
                errors.append(f"unresolved payload {key} differs from candidate")
        if (
            subject.get("phase") == "PREPARED"
            and unresolved.get("replay_ledger_head_digest")
            != subject.get("replay_ledger_head_digest")
        ):
            errors.append(
                "prepared unresolved payload replay head differs from candidate"
            )
        pre_state = unresolved.get("pre_state")
        errors.extend(_exact(pre_state, _PRE_STATE_KEYS, "pre_state"))
        if isinstance(pre_state, dict) and pre_state != _FIXED_PRE_STATE:
            errors.append(
                "pre_state differs from the fixed inactive/disabled "
                "disposable baseline"
            )
        reasons = unresolved.get("reasons")
        if (
            not isinstance(reasons, list)
            or not reasons
            or any(not isinstance(item, str) or not item for item in reasons)
        ):
            errors.append("unresolved reasons must be non-empty strings")
        if subject.get("unresolved_state_digest") != (
            central_validator.canonical_digest(unresolved)
        ):
            errors.append("unresolved payload digest does not re-derive")
        for key, expected in (
            ("side_effect_class", SIDE_EFFECT_CLASS),
            ("target_class", PROFILE_TARGET_CLASS),
            ("production_effect", False),
            ("production_authority", False),
        ):
            if unresolved.get(key) != expected:
                errors.append(f"unresolved payload {key} violates fixed boundary")

    inventory = subject.get("journal_inventory")
    if isinstance(inventory, list):
        canonical = sorted(
            inventory,
            key=lambda item: (
                item.get("basename", "") if isinstance(item, dict) else ""
            ),
        )
        if inventory != canonical:
            errors.append("candidate journal inventory is not canonical-sorted")
        basenames = [
            item.get("basename") for item in inventory if isinstance(item, dict)
        ]
        start_ids = [
            item.get("start_id") for item in inventory if isinstance(item, dict)
        ]
        if len(basenames) != len(set(basenames)):
            errors.append("candidate journal basenames are not unique")
        if len(start_ids) != len(set(start_ids)):
            errors.append("candidate journal start ids are not unique")
        if subject.get("start_id") not in start_ids:
            errors.append("candidate active recovery journal is absent")
        expected_journal_set = central_validator.canonical_digest({
            "schema_version": "s2_5_recovery_journal_set_v2",
            "entries": inventory,
        })
        if subject.get("journal_set_digest") != expected_journal_set:
            errors.append("candidate journal-set digest does not re-derive")

    replay = subject.get("replay_ledger")
    consumed = subject.get("consumed_authorization_ids")
    if isinstance(consumed, list) and consumed != sorted(consumed):
        errors.append("consumed authorization ids are not canonical-sorted")
    if isinstance(replay, dict):
        ids = replay.get("authorization_ids")
        if isinstance(ids, list) and ids != sorted(ids):
            errors.append("replay authorization ids are not canonical-sorted")
        if ids != consumed:
            errors.append("replay authorization id set differs from candidate")
        if replay.get("entry_count") != (
            len(ids) if isinstance(ids, list) else -1
        ):
            errors.append("replay entry count differs from exact id set")
        if replay.get("head_digest") != subject.get(
            "replay_ledger_head_digest"
        ):
            errors.append("replay head differs from candidate")
        present = replay.get("present")
        if present is False and (
            replay.get("entry_count") != 0
            or replay.get("file_digest") is not None
            or replay.get("head_digest") is not None
        ):
            errors.append("absent replay ledger must have an empty null head")
        if present is True and (
            replay.get("entry_count", 0) < 1
            or replay.get("file_digest") is None
            or replay.get("head_digest") is None
        ):
            errors.append("present replay ledger must bind non-empty exact bytes")

    intent, intent_errors = _parse_canonical_object(
        subject.get("recovery_intent_json"), label="recovery intent"
    )
    errors.extend(intent_errors)
    errors.extend(_exact(intent, _INTENT_KEYS, "recovery intent"))
    if intent:
        if intent.get("schema_version") != (
            "s2_5_recovery_controller_intent_ref_v2"
        ):
            errors.append("recovery intent schema_version is invalid")
        if intent.get("self_digest") != (
            central_validator.artifact_self_digest(intent)
        ):
            errors.append("recovery intent self_digest does not re-derive")
        if subject.get("recovery_intent_digest") != intent.get("self_digest"):
            errors.append("recovery intent digest differs from exact bytes")
        for key in ("authorization_id", "task_digest", "start_id", "source_head"):
            if intent.get(key) != subject.get(key):
                errors.append(f"recovery intent {key} differs from candidate")
        if intent.get("action") != "ROLLBACK_TO_PRE_STATE":
            errors.append("recovery intent action is not code-owned")
        for key, expected in (
            ("side_effect_class", SIDE_EFFECT_CLASS),
            ("target_class", PROFILE_TARGET_CLASS),
            ("production_effect", False),
            ("production_authority", False),
        ):
            if intent.get(key) != expected:
                errors.append(
                    f"recovery intent {key} violates the fixed boundary"
                )

    phase = subject.get("phase")
    required = {
        "consumption": phase in {"CONSUMED", "COMMITTED", "RESOLVED"},
        "effect result": phase in {"COMMITTED", "RESOLVED"},
        "rollback result": phase in {"COMMITTED", "RESOLVED"},
        "independent postcheck": phase == "RESOLVED",
    }
    artifact_fields = {
        "consumption": ("consumption_proof_json", "consumption_proof_digest"),
        "effect result": ("effect_result_json", "effect_result_digest"),
        "rollback result": ("rollback_result_json", "rollback_result_digest"),
        "independent postcheck": (
            "independent_postcheck_json",
            "independent_postcheck_digest",
        ),
    }
    for label, (json_key, digest_key) in artifact_fields.items():
        errors.extend(_embedded_artifact_errors(
            subject.get(json_key),
            subject.get(digest_key),
            label=label,
            subject=subject,
            required=required[label],
        ))
        if not required[label] and (
            subject.get(json_key) is not None
            or subject.get(digest_key) is not None
        ):
            errors.append(f"{phase} candidate cannot carry {label}")
    expected_consumed = (
        [] if phase == "PREPARED" else [subject.get("authorization_id")]
    )
    if consumed != expected_consumed:
        errors.append(f"{phase} candidate has an invalid consumption set")
    sequence = subject.get("previous_external_sequence")
    floor = subject.get("external_monotonic_floor")
    if (
        isinstance(sequence, int)
        and isinstance(floor, int)
        and sequence < floor
    ):
        errors.append("candidate external sequence is below monotonic floor")
    return errors


def _transition_errors(transition: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    subject = transition.get("candidate_subject")
    subject_schema_errors = _candidate_schema_errors(subject)
    subject_errors = _subject_errors(subject)
    errors.extend(subject_errors)
    if subject_schema_errors:
        return errors
    if isinstance(subject, dict):
        digest = derive_candidate_subject_digest(subject)
        if transition.get("candidate_subject_digest") != digest:
            errors.append("transition candidate subject digest does not re-derive")
        pairs = {
            "to_phase": "phase",
            "generation": "generation",
            "previous_controller_state_digest": (
                "previous_controller_state_digest"
            ),
            "expected_external_sequence": "previous_external_sequence",
            "expected_external_head_digest": "previous_external_head_digest",
            "external_monotonic_floor": "external_monotonic_floor",
            "expected_snapshot_id": "external_snapshot_id",
            "expected_latest_version_id": "external_latest_version_id",
        }
        for transition_key, subject_key in pairs.items():
            if transition.get(transition_key) != subject.get(subject_key):
                errors.append(
                    f"transition {transition_key} differs from candidate subject"
                )
        pair = (transition.get("from_phase"), transition.get("to_phase"))
        if pair not in _PHASE_EDGES:
            errors.append("illegal controller phase transition")
        if subject.get("anchor_progress") != "OUTBOX_PREPARED":
            errors.append("transition candidate must prepare an exact outbox")
        if transition.get("from_phase") == "GENESIS":
            if (
                subject.get("generation") != 1
                or subject.get("previous_controller_state_digest") is not None
                or subject.get("previous_manifest_digest") is not None
            ):
                errors.append("GENESIS transition does not bind generation one")
        elif subject.get("generation") == 1:
            errors.append("non-genesis transition cannot create generation one")
    if transition.get("transition_id") != derive_transition_id(transition):
        errors.append("controller transition id does not re-derive")
    issued, issued_errors = _aware_time(
        transition.get("issued_at"), label="transition issued_at"
    )
    expires, expiry_errors = _aware_time(
        transition.get("expires_at"), label="transition expires_at"
    )
    errors.extend(issued_errors)
    errors.extend(expiry_errors)
    if issued is not None and expires is not None and (
        expires <= issued or expires - issued > timedelta(minutes=5)
    ):
        errors.append("transition freshness window must be in (0, 5 minutes]")
    if transition.get("evidence_class") != PROFILE_EVIDENCE_CLASS:
        errors.append("controller transition cannot promote external trust")
    return errors


def _outbox_errors(outbox: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    transition, transition_errors = _parse_canonical_object(
        outbox.get("transition_json"), label="outbox transition"
    )
    errors.extend(transition_errors)
    if transition:
        errors.extend(validate_controller_artifact(transition))
        if outbox.get("transition_digest") != transition.get("self_digest"):
            errors.append("outbox transition digest differs from exact bytes")
        if outbox.get("candidate_subject_digest") != transition.get(
            "candidate_subject_digest"
        ):
            errors.append("outbox candidate subject differs from transition")
    request, request_errors = _parse_canonical_object(
        outbox.get("prepared_payload_json"), label="prepared payload"
    )
    errors.extend(request_errors)
    errors.extend(_exact(request, _OUTBOX_REQUEST_KEYS, "prepared payload"))
    if request:
        if request.get("schema_version") != (
            "s2_5_recovery_anchor_compare_append_request_v2"
        ):
            errors.append("prepared payload schema_version is invalid")
        if outbox.get("prepared_payload_digest") != (
            central_validator.canonical_digest(request)
        ):
            errors.append("prepared payload digest does not re-derive")
        expected_request_digest = central_validator.canonical_digest({
            "schema_version": "s2_5_recovery_anchor_request_bytes_v1",
            "canonical_json": outbox.get("prepared_payload_json"),
        })
        if outbox.get("request_digest") != expected_request_digest:
            errors.append("prepared request byte digest does not re-derive")
        if request.get("idempotency_key") != derive_outbox_idempotency(request):
            errors.append("prepared request idempotency key does not re-derive")
        direct_pairs = (
            "transition_digest",
            "candidate_subject_digest",
            "prior_manifest_digest",
            "expected_external_sequence",
            "expected_external_head_digest",
            "expected_snapshot_id",
            "expected_latest_version_id",
            "candidate_external_sequence",
            "idempotency_key",
        )
        for key in direct_pairs:
            if request.get(key) != outbox.get(key):
                errors.append(f"prepared payload {key} differs from exact outbox")
        expected_sequence = request.get("expected_external_sequence")
        candidate_sequence = request.get("candidate_external_sequence")
        if (
            not isinstance(expected_sequence, int)
            or isinstance(expected_sequence, bool)
            or not isinstance(candidate_sequence, int)
            or isinstance(candidate_sequence, bool)
        ):
            errors.append("prepared payload sequences must be integers")
        elif candidate_sequence != expected_sequence + 1:
            errors.append("prepared payload candidate sequence is not successor")
        if transition:
            subject = transition.get("candidate_subject")
            if isinstance(subject, dict):
                subject_pairs = {
                    "source_head": "source_head",
                    "start_id": "start_id",
                    "operation": "operation",
                    "phase": "phase",
                    "prior_manifest_digest": "previous_manifest_digest",
                }
                for request_key, subject_key in subject_pairs.items():
                    if request.get(request_key) != subject.get(subject_key):
                        errors.append(
                            f"prepared payload {request_key} differs from candidate"
                        )
    if outbox.get("effect_executed") is not False:
        errors.append("prepared outbox cannot claim an executed effect")
    if outbox.get("evidence_class") != PROFILE_EVIDENCE_CLASS:
        errors.append("prepared outbox cannot promote external trust")
    return errors


def _proof_errors(proof: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    transition, transition_errors = _parse_canonical_object(
        proof.get("transition_json"), label="anchor proof transition"
    )
    errors.extend(transition_errors)
    outbox, outbox_errors = _parse_canonical_object(
        proof.get("outbox_json"), label="anchor proof outbox"
    )
    errors.extend(outbox_errors)
    if transition:
        errors.extend(validate_controller_artifact(transition))
        if proof.get("transition_digest") != transition.get("self_digest"):
            errors.append("anchor proof transition digest differs")
    if outbox:
        errors.extend(validate_controller_artifact(outbox))
        if proof.get("outbox_digest") != outbox.get("self_digest"):
            errors.append("anchor proof outbox digest differs")
        if proof.get("transition_digest") != outbox.get("transition_digest"):
            errors.append("anchor proof transition/outbox binding differs")
        if proof.get("idempotency_key") != outbox.get("idempotency_key"):
            errors.append("anchor proof idempotency differs from outbox")
        if proof.get("sequence") != outbox.get(
            "candidate_external_sequence"
        ):
            errors.append("anchor proof sequence differs from outbox candidate")
        if proof.get("previous_head_digest") != outbox.get(
            "expected_external_head_digest"
        ):
            errors.append("anchor proof predecessor differs from outbox")
        if proof.get("outbox_candidate_subject_digest") != outbox.get(
            "candidate_subject_digest"
        ):
            errors.append("anchor proof candidate subject differs from outbox")
    if transition and isinstance(transition.get("candidate_subject"), dict):
        subject = transition["candidate_subject"]
        for proof_key, subject_key in (
            ("source_head", "source_head"),
            ("start_id", "start_id"),
            ("phase", "phase"),
        ):
            if proof.get(proof_key) != subject.get(subject_key):
                errors.append(f"anchor proof {proof_key} differs from candidate")
    sequence = proof.get("sequence")
    floor = proof.get("external_monotonic_floor")
    if (
        isinstance(sequence, int)
        and isinstance(floor, int)
        and sequence < floor
    ):
        errors.append("anchor proof sequence is below monotonic floor")
    identities = {
        proof.get("writer_identity_digest"),
        proof.get("reader_identity_digest"),
        proof.get("verifier_identity_digest"),
    }
    if len(identities) != 3:
        errors.append("local proof still binds three distinct identity digests")
    if proof.get("evidence_class") != PROFILE_EVIDENCE_CLASS:
        errors.append("C1 proof cannot claim external evidence")
    if not (
        proof.get("immutable_readback") is False
        and proof.get("full_chain_valid") is False
        and proof.get("identity_distinct") is False
        and proof.get("authenticated_response") is False
        and isinstance(proof.get("failure_code"), str)
        and bool(proof.get("failure_code"))
    ):
        errors.append("local proof must retain a closed unverified failure state")
    return errors


def _state_errors(state: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    subject = state.get("candidate_subject")
    subject_errors = _subject_errors(subject)
    errors.extend(subject_errors)
    if not isinstance(subject, dict):
        return errors
    subject_digest = derive_candidate_subject_digest(subject)
    if state.get("candidate_subject_digest") != subject_digest:
        errors.append("state candidate subject digest does not re-derive")
    progress = subject.get("anchor_progress")
    pending = state.get("pending_outbox")
    pending_digest = state.get("pending_outbox_digest")
    proof = state.get("attached_anchor_proof")
    proof_digest = state.get("attached_anchor_proof_digest")
    if progress == "OUTBOX_PREPARED":
        if not isinstance(pending, dict) or pending_digest is None:
            errors.append("OUTBOX_PREPARED state requires an exact outbox")
        if proof is not None or proof_digest is not None:
            errors.append("OUTBOX_PREPARED state cannot attach anchor proof")
    elif progress == "PROOF_ATTACHED_UNVERIFIED":
        if pending is not None or pending_digest is not None:
            errors.append("proof-attached state cannot retain pending outbox")
        if not isinstance(proof, dict) or proof_digest is None:
            errors.append("proof-attached state requires exact local proof")
    if isinstance(pending, dict):
        errors.extend(validate_controller_artifact(pending))
        if pending_digest != pending.get("self_digest"):
            errors.append("state pending outbox digest differs")
        transition, transition_errors = _parse_canonical_object(
            pending.get("transition_json"), label="state pending transition"
        )
        errors.extend(transition_errors)
        if transition:
            if transition.get("candidate_subject") != subject:
                errors.append("pending transition candidate subject differs from state")
            if transition.get("candidate_subject_digest") != subject_digest:
                errors.append("pending transition candidate digest differs from state")
    if isinstance(proof, dict):
        proof_errors = validate_controller_artifact(proof)
        errors.extend(proof_errors)
        if proof_digest != proof.get("self_digest"):
            errors.append("state attached proof digest differs")
        if proof_errors:
            return errors
        if proof.get("confirmed_candidate_subject_digest") != subject_digest:
            errors.append("anchor proof does not bind exact enclosing candidate")
        if proof.get("outbox_prepared_state_digest") != subject.get(
            "previous_controller_state_digest"
        ):
            errors.append("anchor proof does not bind immediate prior state")
        transition, transition_errors = _parse_canonical_object(
            proof.get("transition_json"), label="attached proof transition"
        )
        errors.extend(transition_errors)
        if transition and isinstance(transition.get("candidate_subject"), dict):
            pending_subject = transition["candidate_subject"]
            if pending_subject.get("anchor_progress") != "OUTBOX_PREPARED":
                errors.append("anchor proof did not originate at outbox state")
            if pending_subject.get("generation", -1) + 1 != subject.get(
                "generation"
            ):
                errors.append("proof-attached generation is not prior plus one")
            for key in _PROOF_ATTACH_IMMUTABLE_KEYS:
                if subject.get(key) != pending_subject.get(key):
                    errors.append(
                        f"proof-attached candidate changed immutable {key}"
                    )
    return errors


def _manifest_errors(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    state = manifest.get("controller_state")
    state_errors = validate_controller_artifact(state)
    errors.extend(state_errors)
    if state_errors:
        return errors
    subject = (
        state.get("candidate_subject") if isinstance(state, dict) else None
    )
    identity = manifest.get("state_root_identity")
    if (
        not isinstance(identity, dict)
        or manifest.get("state_root_id")
        != central_validator.canonical_digest(identity)
    ):
        errors.append("manifest live state-root id does not re-derive")
    if manifest.get("store_id") != derive_store_id(
        str(manifest.get("state_root_id"))
    ):
        errors.append("manifest store id does not re-derive")
    generation = manifest.get("generation")
    previous = manifest.get("previous_manifest_digest")
    if generation == 1 and previous is not None:
        errors.append("manifest generation one must have no predecessor")
    if isinstance(generation, int) and generation > 1 and previous is None:
        errors.append("manifest generation after one must bind predecessor")
    if isinstance(state, dict):
        if manifest.get("controller_state_digest") != state.get("self_digest"):
            errors.append("manifest controller-state digest differs")
        for key in (
            "pending_outbox",
            "pending_outbox_digest",
            "attached_anchor_proof",
            "attached_anchor_proof_digest",
        ):
            if manifest.get(key) != state.get(key):
                errors.append(f"manifest {key} differs from controller state")
    if isinstance(subject, dict):
        pairs = (
            "stable_root_id",
            "state_root_id",
            "source_head",
            "generation",
            "phase",
            "anchor_progress",
            "previous_manifest_digest",
            "state_root_identity",
            "journal_inventory",
            "journal_set_digest",
            "replay_ledger",
        )
        for key in pairs:
            if manifest.get(key) != subject.get(key):
                errors.append(f"manifest {key} differs from candidate subject")
        if manifest.get("generation") != subject.get("generation"):
            errors.append("manifest generation differs from controller generation")
    outbox = manifest.get("pending_outbox")
    if isinstance(outbox, dict) and outbox.get(
        "prior_manifest_digest"
    ) != previous:
        errors.append("manifest outbox does not bind exact predecessor")
    inventory = manifest.get("journal_inventory")
    if isinstance(inventory, list):
        if any(
            not isinstance(item, dict)
            or not isinstance(item.get("basename"), str)
            or not isinstance(item.get("start_id"), str)
            for item in inventory
        ):
            errors.append("manifest journal inventory entries are malformed")
            return errors
        basenames = [
            item.get("basename") for item in inventory if isinstance(item, dict)
        ]
        start_ids = [
            item.get("start_id") for item in inventory if isinstance(item, dict)
        ]
        if len(basenames) != len(set(basenames)):
            errors.append("manifest journal basenames are not unique")
        if len(start_ids) != len(set(start_ids)):
            errors.append("manifest journal start ids are not unique")
        if isinstance(subject, dict) and subject.get("start_id") not in start_ids:
            errors.append("manifest active recovery journal is absent")
        expected_set = central_validator.canonical_digest({
            "schema_version": "s2_5_recovery_journal_set_v2",
            "entries": inventory,
        })
        if manifest.get("journal_set_digest") != expected_set:
            errors.append("manifest journal-set digest does not re-derive")
    replay = manifest.get("replay_ledger")
    if isinstance(replay, dict) and isinstance(subject, dict):
        if replay.get("authorization_ids") != subject.get(
            "consumed_authorization_ids"
        ):
            errors.append("manifest replay id set differs from controller")
    return errors


def validate_controller_artifact(artifact: Any) -> list[str]:
    """Validate one closed source-only state, transition, outbox, proof or manifest."""

    if not isinstance(artifact, dict):
        return ["controller artifact must be an object"]
    schema_version = artifact.get("schema_version")
    if not isinstance(schema_version, str) or schema_version not in _SCHEMAS:
        return ["controller schema_version is unknown"]
    try:
        schema = _schema(str(schema_version))
    except ValueError as error:
        return [str(error)]
    errors = schema_subset_errors(artifact, schema, schema)
    if errors:
        if schema_version == TRANSITION_SCHEMA:
            from_phase = artifact.get("from_phase")
            to_phase = artifact.get("to_phase")
            if (
                isinstance(from_phase, str)
                and isinstance(to_phase, str)
                and (from_phase, to_phase) not in _PHASE_EDGES
            ):
                errors.append("illegal controller phase transition")
        return errors
    if artifact.get("self_digest") != central_validator.artifact_self_digest(
        artifact
    ):
        errors.append("controller self_digest does not re-derive")
    for key, expected in _COMMON.items():
        if artifact.get(key) != expected:
            errors.append(f"controller {key} differs from fixed profile")
    if artifact.get("trust_status", STATUS_UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED) != (
        STATUS_UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED
    ):
        errors.append("local controller artifact cannot promote external trust")
    if schema_version == STATE_SCHEMA:
        errors.extend(_state_errors(artifact))
    elif schema_version == TRANSITION_SCHEMA:
        errors.extend(_transition_errors(artifact))
    elif schema_version == OUTBOX_SCHEMA:
        errors.extend(_outbox_errors(artifact))
    elif schema_version == PROOF_SCHEMA:
        errors.extend(_proof_errors(artifact))
    else:
        errors.extend(_manifest_errors(artifact))
    return errors


def validate_fresh_controller_admission(
    state: Any, *, trusted_now: Any
) -> list[str]:
    """Revalidate the full admission capture against a trusted current time."""

    errors = validate_controller_artifact(state)
    if errors:
        return errors
    if not isinstance(state, dict):
        return errors
    subject = state.get("candidate_subject")
    if not isinstance(subject, dict):
        return errors
    admission, parse_errors = _parse_canonical_object(
        subject.get("recovery_admission_capture_json"),
        label="recovery admission capture",
    )
    errors.extend(parse_errors)
    if admission:
        errors.extend(
            f"fresh recovery admission: {error}"
            for error in host_capture.validate_s2_5_recovery_host_capture(
                admission, now=trusted_now
            )
        )
    return errors


def _state_subject(state: Any) -> dict[str, Any]:
    if not isinstance(state, dict):
        return {}
    subject = state.get("candidate_subject")
    return subject if isinstance(subject, dict) else {}


def validate_controller_transition(
    previous: Any,
    transition: Any,
) -> list[str]:
    """Validate a structural phase edge; this never admits the associated effect."""

    errors = validate_controller_artifact(previous)
    errors.extend(validate_controller_artifact(transition))
    if errors:
        return errors
    previous_subject = _state_subject(previous)
    if (
        not isinstance(transition, dict)
        or not previous_subject
        or transition.get("schema_version") != TRANSITION_SCHEMA
    ):
        return errors
    candidate = transition.get("candidate_subject")
    if not isinstance(candidate, dict):
        return errors
    pair = (previous_subject.get("phase"), candidate.get("phase"))
    if pair not in _PHASE_EDGES:
        errors.append("illegal controller phase transition")
    if previous_subject.get("anchor_progress") != (
        "PROOF_ATTACHED_UNVERIFIED"
    ):
        errors.append("phase advance requires prior attached anchor proof")
    if candidate.get("anchor_progress") != "OUTBOX_PREPARED":
        errors.append("phase advance candidate must prepare outbox")
    if transition.get("from_phase") != previous_subject.get("phase"):
        errors.append("transition from_phase differs from prior state")
    if candidate.get("generation") != previous_subject.get("generation", 0) + 1:
        errors.append("candidate generation is not previous plus one")
    if candidate.get("previous_controller_state_digest") != previous.get(
        "self_digest"
    ):
        errors.append("candidate controller predecessor is not exact")
    for key in _CHAIN_IMMUTABLE_SUBJECT_KEYS:
        if candidate.get(key) != previous_subject.get(key):
            errors.append(f"phase transition changed immutable {key}")
    proof = (
        previous.get("attached_anchor_proof")
        if isinstance(previous, dict)
        else None
    )
    if isinstance(proof, dict):
        external_expected = {
            "previous_external_sequence": "sequence",
            "previous_external_head_digest": "head_digest",
            "external_monotonic_floor": "external_monotonic_floor",
            "external_snapshot_id": "snapshot_id",
            "external_latest_version_id": "latest_version_id",
        }
        for candidate_key, proof_key in external_expected.items():
            if candidate.get(candidate_key) != proof.get(proof_key):
                errors.append(
                    f"candidate {candidate_key} differs from prior proof"
                )
        if candidate.get("prior_phase_anchor_proof_digest") != proof.get(
            "self_digest"
        ):
            errors.append("candidate does not bind exact prior anchor proof")
    if pair == ("PREPARED", "CONSUMED"):
        before = previous_subject.get("consumed_authorization_ids")
        after = candidate.get("consumed_authorization_ids")
        expected = sorted(
            list(before) + [candidate.get("authorization_id")]
        ) if isinstance(before, list) else []
        if after != expected or len(after) != len(set(after or [])):
            errors.append("consume edge must add exactly one authorization id")
        if candidate.get("replay_ledger_head_digest") in {
            None,
            previous_subject.get("replay_ledger_head_digest"),
        }:
            errors.append("consume edge must advance replay-ledger head")
    elif pair in {
        ("CONSUMED", "COMMITTED"),
        ("COMMITTED", "RESOLVED"),
    }:
        for key in (
            "consumed_authorization_ids",
            "replay_ledger",
            "replay_ledger_head_digest",
            "consumption_proof_json",
            "consumption_proof_digest",
        ):
            if candidate.get(key) != previous_subject.get(key):
                errors.append(f"post-consume transition changed durable {key}")
    return errors


def validate_controller_state_successor(
    previous: Any,
    candidate: Any,
) -> list[str]:
    """Validate one exact atomic controller generation successor."""

    errors = validate_controller_artifact(previous)
    errors.extend(validate_controller_artifact(candidate))
    if errors:
        return errors
    previous_subject = _state_subject(previous)
    candidate_subject = _state_subject(candidate)
    if not previous_subject or not candidate_subject:
        return errors
    if candidate_subject.get("generation") != (
        previous_subject.get("generation", 0) + 1
    ):
        errors.append("controller successor generation is not previous plus one")
    if candidate_subject.get("previous_controller_state_digest") != (
        previous.get("self_digest")
    ):
        errors.append("controller successor predecessor is not exact")
    previous_progress = previous_subject.get("anchor_progress")
    candidate_progress = candidate_subject.get("anchor_progress")
    if (
        previous_progress == "OUTBOX_PREPARED"
        and candidate_progress == "PROOF_ATTACHED_UNVERIFIED"
    ):
        if candidate_subject.get("phase") != previous_subject.get("phase"):
            errors.append("proof attachment changed recovery phase")
        for key in _PROOF_ATTACH_IMMUTABLE_KEYS:
            if candidate_subject.get(key) != previous_subject.get(key):
                errors.append(f"proof attachment changed immutable {key}")
        proof = candidate.get("attached_anchor_proof")
        if isinstance(proof, dict):
            if proof.get("outbox_prepared_state_digest") != previous.get(
                "self_digest"
            ):
                errors.append("attached proof does not bind exact prior state")
            proof_outbox, proof_outbox_errors = _parse_canonical_object(
                proof.get("outbox_json"), label="successor proof outbox"
            )
            errors.extend(proof_outbox_errors)
            if previous.get("pending_outbox") != proof_outbox:
                errors.append("attached proof outbox differs from prior state")
    elif (
        previous_progress == "PROOF_ATTACHED_UNVERIFIED"
        and candidate_progress == "OUTBOX_PREPARED"
    ):
        outbox = candidate.get("pending_outbox")
        transition: Any = {}
        if isinstance(outbox, dict):
            transition, transition_errors = _parse_canonical_object(
                outbox.get("transition_json"),
                label="successor transition",
            )
            errors.extend(transition_errors)
        errors.extend(validate_controller_transition(previous, transition))
    else:
        errors.append("illegal controller anchor-progress successor")
    return errors


def validate_manifest_successor(previous: Any, candidate: Any) -> list[str]:
    """Validate exact manifest/controller predecessor and generation coupling."""

    errors = validate_controller_artifact(previous)
    errors.extend(validate_controller_artifact(candidate))
    if errors:
        return errors
    if not isinstance(previous, dict) or not isinstance(candidate, dict):
        return errors
    if (
        previous.get("schema_version") != MANIFEST_SCHEMA
        or candidate.get("schema_version") != MANIFEST_SCHEMA
    ):
        return errors + ["manifest successor inputs must both be v2 manifests"]
    if candidate.get("generation") != previous.get("generation", 0) + 1:
        errors.append("manifest successor generation is not previous plus one")
    if candidate.get("previous_manifest_digest") != previous.get("self_digest"):
        errors.append("manifest successor predecessor is not exact")
    for key in ("store_id", "stable_root_id", "state_root_id", "source_head"):
        if candidate.get(key) != previous.get(key):
            errors.append(f"manifest successor changed immutable {key}")
    previous_state = previous.get("controller_state")
    candidate_state = candidate.get("controller_state")
    errors.extend(
        validate_controller_state_successor(previous_state, candidate_state)
    )
    candidate_subject = _state_subject(candidate_state)
    if candidate_subject.get("previous_manifest_digest") != previous.get(
        "self_digest"
    ):
        errors.append("candidate subject manifest predecessor is not exact")
    if isinstance(candidate_state, dict) and candidate_state.get(
        "pending_outbox"
    ) is not None:
        if candidate_state["pending_outbox"].get(
            "prior_manifest_digest"
        ) != previous.get("self_digest"):
            errors.append("candidate outbox predecessor is not exact")
    return errors


def classify_legacy_manifest(manifest: Any) -> dict[str, Any]:
    """Classify legacy/absent state without synthesizing a trusted genesis."""

    if isinstance(manifest, dict) and manifest.get("schema_version") == (
        "s2_5_recovery_store_manifest_v1"
    ):
        status = "RECOVERY_REQUIRED_LEGACY_DIGEST_ONLY"
    else:
        status = "RECOVERY_REQUIRED_EXTERNAL_BOOTSTRAP_REQUIRED"
    return {
        "status": status,
        "auto_upgrade_allowed": False,
        "external_bootstrap_required": True,
        "effect_admitted": False,
        "clear_admitted": False,
        "production_effect": False,
        "production_authority": False,
    }
