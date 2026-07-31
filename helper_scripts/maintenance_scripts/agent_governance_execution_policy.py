"""Aggregate execution admission for the Development-Agent Governance Module."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
from typing import Any


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HISTORY_FIELDS = {
    "schema_version",
    "mode",
    "source_thread_id",
    "boundary_turn_id",
    "ephemeral",
    "exception_digest",
}
SURFACE_FIELDS = {
    "schema_version",
    "profile_id",
    "platform",
    "native_selector_binding",
    "usage_telemetry",
    "call_deadline",
    "wave_deadline",
    "history_selection",
    "ephemeral_fork",
    "concurrency_limit",
    "model_visible_interruptions",
    "event_coverage",
    "mandatory_role_eligible",
}
EVENT_INPUT_FIELDS = {
    "event_id",
    "kind",
    "parent_event_id",
    "node_id",
    "spawn_depth",
    "watcher_id",
    "outcome",
    "call_record_digest",
}
EVENT_FIELDS = {*EVENT_INPUT_FIELDS, "sequence"}
LEDGER_FIELDS = {
    "schema_version",
    "root_execution_id",
    "policy_digest",
    "surface_profile_digest",
    "watcher_id",
    "events",
    "terminal_reason",
    "ledger_digest",
}
EVENT_KINDS = {
    "root_turn",
    "spawn",
    "model_call",
    "retry",
    "follow_up",
    "wait",
    "no_delta_wakeup",
    "terminate",
}
EVENT_OUTCOMES = {
    "root_turn": {"completed"},
    "spawn": {"completed"},
    "model_call": {"completed", "null", "timeout"},
    "retry": {"completed", "null", "timeout"},
    "follow_up": {"completed", "null", "timeout"},
    "wait": {"completed", "timeout"},
    "no_delta_wakeup": {"no_delta"},
    "terminate": {"terminated"},
}
SAMPLING_KINDS = {"model_call", "retry", "follow_up"}
CALL_ATTEMPT_KINDS = {"model_call", "retry"}
MANDATORY_ROLE_CONTROL_FIELDS = {
    "native_selector_binding",
    "history_selection",
    "ephemeral_fork",
    "concurrency_limit",
}
TERMINAL_REASONS = {
    "BUDGET_EXHAUSTED",
    "SPAWN_DEPTH_EXCEEDED",
    "WAIT_BUDGET_EXHAUSTED",
    "NO_DELTA_BUDGET_EXHAUSTED",
    "DEADLINE_EXCEEDED",
}
ENVELOPE_ORDER = ("narrow", "standard", "complex", "full_audit")


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _ledger_digest(ledger: dict[str, Any]) -> str:
    return _digest({key: value for key, value in ledger.items() if key != "ledger_digest"})


def compile_execution_budget_policy(
    envelope: str, registry: dict[str, Any],
) -> dict[str, Any]:
    """Compile the Registry envelope and provider-telemetry boundary once."""

    source = registry.get("budget_envelopes", {}).get(envelope)
    if not isinstance(source, dict):
        raise ValueError(f"unknown execution budget envelope {envelope!r}")
    provider_cap = registry.get("execution_policy", {}).get("platform_token_cap")
    if not isinstance(provider_cap, dict):
        raise ValueError("Registry execution policy lacks platform_token_cap")
    return {
        "schema_version": "execution_budget_policy_v1",
        "envelope": envelope,
        **deepcopy(source),
        "platform_token_cap": deepcopy(provider_cap),
    }


def execution_policy_digest(policy: dict[str, Any]) -> str:
    """Return the content address shared by route, Context, and wave receipts."""

    return _digest(policy)


def promote_execution_envelope(
    base_envelope: str,
    *,
    required_nodes: int,
    registry: dict[str, Any],
) -> str:
    """Choose the smallest envelope at or above risk that admits the final DAG."""

    if base_envelope == "profit_diagnosis":
        if registry["budget_envelopes"][base_envelope]["max_unique_nodes"] < required_nodes:
            raise ValueError("profit diagnosis DAG exceeds its dedicated envelope")
        return base_envelope
    try:
        start = ENVELOPE_ORDER.index(base_envelope)
    except ValueError as exc:
        raise ValueError(f"unknown base envelope {base_envelope!r}") from exc
    for name in ENVELOPE_ORDER[start:]:
        if registry["budget_envelopes"][name]["max_unique_nodes"] >= required_nodes:
            return name
    raise ValueError("required delegated DAG exceeds the largest execution envelope")


def default_history_binding(registry: dict[str, Any]) -> dict[str, Any]:
    value = registry.get("execution_policy", {}).get("default_history")
    if not isinstance(value, dict):
        raise ValueError("Registry execution policy lacks default_history")
    return deepcopy(value)


def requested_history_errors(
    value: Any, *, admitted_exception_digests: set[str],
) -> list[str]:
    if not isinstance(value, dict) or set(value) != HISTORY_FIELDS:
        return ["requested history fields do not match requested_history_v1"]
    errors: list[str] = []
    if value.get("schema_version") != "requested_history_v1":
        errors.append("requested history schema_version is invalid")
    if value.get("ephemeral") is not True:
        errors.append("requested history must use an ephemeral child context")
    mode = value.get("mode")
    source = value.get("source_thread_id")
    boundary = value.get("boundary_turn_id")
    exception = value.get("exception_digest")
    if mode == "none":
        if any(item is not None for item in (source, boundary, exception)):
            errors.append("history mode none cannot bind source, boundary, or exception")
    elif mode == "bounded":
        if not all(isinstance(item, str) and item.strip() for item in (source, boundary)):
            errors.append("bounded history requires exact source thread and boundary turn")
        if not isinstance(exception, str) or not DIGEST_RE.fullmatch(exception):
            errors.append("bounded history requires a reviewed exception digest")
        elif exception not in admitted_exception_digests:
            errors.append("bounded history exception was not admitted by the task contract")
    else:
        errors.append("requested history mode must be none or bounded")
    return errors


def surface_profile_binding(
    profile_id: str, registry: dict[str, Any],
) -> dict[str, Any]:
    profile = registry.get("execution_policy", {}).get("surface_profiles", {}).get(
        profile_id
    )
    if not isinstance(profile, dict):
        raise ValueError(f"unknown execution surface profile {profile_id!r}")
    return {"profile": deepcopy(profile), "digest": _digest(profile)}


def requested_execution_binding(
    registry: dict[str, Any],
    *,
    profile_id: str = "claude_saved_workflow_v1",
) -> dict[str, Any]:
    """Project the exact surface/history fields every requested call must bind."""

    binding = surface_profile_binding(profile_id, registry)
    return {
        "surface_profile_id": binding["profile"]["profile_id"],
        "surface_profile_digest": binding["digest"],
        "history": default_history_binding(registry),
    }


def surface_allows_mandatory_role(profile: dict[str, Any], role: str) -> bool:
    if profile.get("mandatory_role_eligible") is not True:
        return False
    if any(
        profile.get(field) != "enforced"
        for field in MANDATORY_ROLE_CONTROL_FIELDS
    ):
        return False
    if role in {"PA", "E4"} and profile.get("native_selector_binding") != "enforced":
        return False
    return True


def registry_execution_policy_errors(registry: dict[str, Any]) -> list[str]:
    policy = registry.get("execution_policy")
    if not isinstance(policy, dict) or set(policy) != {
        "schema_version",
        "default_history",
        "platform_token_cap",
        "surface_profiles",
    }:
        return ["execution_policy fields do not match Registry contract"]
    errors: list[str] = []
    if policy.get("schema_version") != "development_agent_execution_policy_v1":
        errors.append("execution_policy schema_version is invalid")
    errors.extend(
        requested_history_errors(
            policy.get("default_history"), admitted_exception_digests=set()
        )
    )
    cap = policy.get("platform_token_cap")
    if cap != {
        "status": "EXTERNAL_LIMIT",
        "max_total_tokens": None,
        "required_metric": "platform_attested_total_tokens",
    }:
        errors.append("platform token cap must expose the machine-detectable external limit")
    profiles = policy.get("surface_profiles")
    required_profiles = {
        "claude_saved_workflow_v1",
        "codex_native_collaboration_v1",
        "generic_host_v1",
    }
    if not isinstance(profiles, dict) or set(profiles) != required_profiles:
        errors.append("execution surface profile roster is invalid")
        return errors
    for profile_id, profile in profiles.items():
        if not isinstance(profile, dict) or set(profile) != SURFACE_FIELDS:
            errors.append(f"{profile_id}: execution surface profile fields are invalid")
            continue
        if (
            profile.get("schema_version") != "execution_surface_profile_v1"
            or profile.get("profile_id") != profile_id
        ):
            errors.append(f"{profile_id}: execution surface identity is invalid")
        if profile.get("native_selector_binding") not in {
            "enforced",
            "reported_only",
            "unavailable",
        }:
            errors.append(f"{profile_id}: native selector capability is invalid")
        for field in (
            "usage_telemetry",
            "call_deadline",
            "wave_deadline",
            "history_selection",
            "ephemeral_fork",
            "concurrency_limit",
        ):
            if profile.get(field) not in {
                "enforced",
                "reported_only",
                "unavailable",
            }:
                errors.append(f"{profile_id}: {field} capability is invalid")
        if profile.get("model_visible_interruptions") not in {
            "disabled",
            "unavailable",
        }:
            errors.append(
                f"{profile_id}: model-visible interruption policy is invalid"
            )
        coverage = profile.get("event_coverage")
        if not isinstance(coverage, list) or len(set(coverage)) != len(coverage) or any(
            event not in EVENT_KINDS for event in coverage
        ):
            errors.append(f"{profile_id}: event coverage is invalid")
        if not isinstance(profile.get("mandatory_role_eligible"), bool):
            errors.append(f"{profile_id}: mandatory-role eligibility must be boolean")
        elif profile.get("mandatory_role_eligible") is True:
            degraded = sorted(
                field
                for field in MANDATORY_ROLE_CONTROL_FIELDS
                if profile.get(field) != "enforced"
            )
            if degraded:
                errors.append(
                    f"{profile_id}: mandatory-role eligible surface requires "
                    f"enforced {', '.join(degraded)}"
                )
    if profiles.get("generic_host_v1", {}).get("mandatory_role_eligible") is not False:
        errors.append("generic host must remain advisory-only")
    return errors


def new_execution_event_ledger(
    *,
    root_execution_id: str,
    policy_digest: str,
    surface_profile_digest: str,
    watcher_id: str,
) -> dict[str, Any]:
    ledger: dict[str, Any] = {
        "schema_version": "execution_event_ledger_v1",
        "root_execution_id": root_execution_id,
        "policy_digest": policy_digest,
        "surface_profile_digest": surface_profile_digest,
        "watcher_id": watcher_id,
        "events": [],
        "terminal_reason": None,
    }
    ledger["ledger_digest"] = _ledger_digest(ledger)
    return ledger


def _reject_event(
    ledger: dict[str, Any], event: dict[str, Any], reason: str,
) -> tuple[bool, dict[str, Any]]:
    rejected = {
        **event,
        "sequence": len(ledger["events"]),
        "outcome": "rejected",
        "call_record_digest": None,
    }
    ledger["events"].append(rejected)
    ledger["terminal_reason"] = reason
    ledger["ledger_digest"] = _ledger_digest(ledger)
    return False, ledger


def _event_lineage_error(
    event: dict[str, Any],
    prior_admitted: dict[str, dict[str, Any]],
    *,
    enforce_depth: bool = True,
) -> str | None:
    kind = event.get("kind")
    if kind == "root_turn":
        if event.get("parent_event_id") is not None:
            return "root_turn must use depth 0 and no parent"
        if enforce_depth and event.get("spawn_depth") != 0:
            return "root_turn must use depth 0 and no parent"
        return None
    parent = prior_admitted.get(event.get("parent_event_id"))
    if parent is None:
        return "parent does not reference a prior admitted event"
    if kind == "spawn":
        if parent.get("kind") not in {"root_turn", "spawn"}:
            return "spawn parent type must be root_turn or spawn"
        if (
            enforce_depth
            and event.get("spawn_depth") != parent.get("spawn_depth", 0) + 1
        ):
            return "spawn must descend exactly one level from its parent"
    if kind == "model_call":
        parent_kind = parent.get("kind")
        if parent_kind not in {"root_turn", "spawn"}:
            return "model_call parent type must be root_turn or spawn"
        expected_depth = (
            parent.get("spawn_depth", 0) + 1
            if parent_kind == "root_turn"
            else parent.get("spawn_depth")
        )
        if enforce_depth and event.get("spawn_depth") != expected_depth:
            return "model_call depth does not match its admitted parent"
        if (
            parent_kind == "spawn"
            and event.get("node_id") != parent.get("node_id")
        ):
            return "model_call must use the spawned node identity"
    if kind == "retry":
        if parent.get("kind") not in {"model_call", "retry"}:
            return "retry parent must be a prior sampling call"
        if event.get("node_id") != parent.get("node_id"):
            return "retry must preserve the same node as its parent"
        if (
            enforce_depth
            and event.get("spawn_depth") != parent.get("spawn_depth")
        ):
            return "retry must preserve the same depth as its parent"
    if kind == "follow_up":
        if parent.get("kind") not in SAMPLING_KINDS:
            return "follow_up parent must be a prior sampling call"
        if event.get("node_id") != parent.get("node_id"):
            return "follow_up must preserve the same node as its parent"
        if (
            enforce_depth
            and event.get("spawn_depth") != parent.get("spawn_depth")
        ):
            return "follow_up must preserve the same depth as its parent"
    if kind == "wait":
        if parent.get("kind") not in {
            "spawn",
            "model_call",
            "retry",
            "follow_up",
            "wait",
            "no_delta_wakeup",
        }:
            return "wait parent must be prior activity on the delegated node"
        if event.get("node_id") != parent.get("node_id"):
            return "wait must preserve the same node and depth as its parent"
        if (
            enforce_depth
            and event.get("spawn_depth") != parent.get("spawn_depth")
        ):
            return "wait must preserve the same node and depth as its parent"
    if kind == "no_delta_wakeup":
        if parent.get("kind") != "wait":
            return "no_delta_wakeup parent must be wait"
        if event.get("node_id") != parent.get("node_id"):
            return (
                "no_delta_wakeup must preserve the same node and depth as its parent"
            )
        if (
            enforce_depth
            and event.get("spawn_depth") != parent.get("spawn_depth")
        ):
            return (
                "no_delta_wakeup must preserve the same node and depth as its parent"
            )
    if kind == "terminate":
        if parent.get("kind") not in {
            "spawn",
            "model_call",
            "retry",
            "follow_up",
            "wait",
            "no_delta_wakeup",
        }:
            return "terminate parent must be prior activity on the delegated node"
        if event.get("node_id") != parent.get("node_id"):
            return "terminate must preserve the same node and depth as its parent"
        if (
            enforce_depth
            and event.get("spawn_depth") != parent.get("spawn_depth")
        ):
            return "terminate must preserve the same node and depth as its parent"
    return None


def _event_call_digest_error(event: dict[str, Any]) -> str | None:
    is_admitted_sampling = (
        event.get("kind") in SAMPLING_KINDS
        and event.get("outcome") != "rejected"
    )
    call_digest = event.get("call_record_digest")
    if is_admitted_sampling and (
        not isinstance(call_digest, str) or not DIGEST_RE.fullmatch(call_digest)
    ):
        return "sampling event requires a valid call_record_digest"
    if not is_admitted_sampling and call_digest is not None:
        return "non-sampling or rejected event cannot bind call_record_digest"
    return None


def _event_outcome_error(
    event: dict[str, Any], *, allow_rejected: bool,
) -> str | None:
    outcome = event.get("outcome")
    if allow_rejected and outcome == "rejected":
        return None
    if outcome not in EVENT_OUTCOMES.get(event.get("kind"), set()):
        return f"outcome is invalid for {event.get('kind')}"
    return None


def _surface_event_coverage_error(
    ledger: dict[str, Any],
    event: dict[str, Any],
    surface_profile: Any,
) -> str | None:
    if (
        not isinstance(surface_profile, dict)
        or set(surface_profile) != SURFACE_FIELDS
        or surface_profile.get("schema_version") != "execution_surface_profile_v1"
    ):
        return "surface profile contract is invalid"
    if _digest(surface_profile) != ledger.get("surface_profile_digest"):
        return "surface profile digest differs from the execution ledger"
    coverage = surface_profile.get("event_coverage")
    if not isinstance(coverage, list) or any(
        kind not in EVENT_KINDS for kind in coverage
    ):
        return "surface profile event coverage is invalid"
    # root_turn is controller-owned lineage, not a claim that the host surfaced it.
    if event.get("kind") != "root_turn" and event.get("kind") not in coverage:
        return f"surface profile does not attest {event.get('kind')}"
    return None


def _budget_rejection_reason(
    policy: dict[str, Any],
    admitted_events: list[dict[str, Any]],
    event: dict[str, Any],
) -> str | None:
    if event["spawn_depth"] > policy["max_spawn_depth_from_root"]:
        return "SPAWN_DEPTH_EXCEEDED"
    delegated_nodes = {
        item.get("node_id")
        for item in admitted_events
        if item.get("kind") != "root_turn"
    }
    if (
        event["kind"] != "root_turn"
        and event["node_id"] not in delegated_nodes
        and len(delegated_nodes) + 1 > policy["max_unique_nodes"]
    ):
        return "BUDGET_EXHAUSTED"
    if event["kind"] in SAMPLING_KINDS:
        sampling_count = sum(
            item["kind"] in SAMPLING_KINDS for item in admitted_events
        )
        call_attempt_count = sum(
            item["kind"] in CALL_ATTEMPT_KINDS for item in admitted_events
        )
        retry_count = sum(
            item["kind"] == "retry" for item in admitted_events
        )
        followup_count = sum(
            item["kind"] == "follow_up" for item in admitted_events
        )
        root_count = sum(
            item["kind"] == "root_turn" for item in admitted_events
        )
        if (
            (
                event["kind"] in CALL_ATTEMPT_KINDS
                and call_attempt_count + 1 > policy["max_call_attempts"]
            )
            or (
                event["kind"] == "retry"
                and retry_count + 1 > policy["retry_budget"]
            )
            or (
                event["kind"] == "follow_up"
                and followup_count + 1 > policy["max_followup_attempts"]
            )
            or root_count + sampling_count + 1 > policy["max_total_model_turns"]
        ):
            return "BUDGET_EXHAUSTED"
    if event["kind"] == "wait" and (
        sum(item["kind"] == "wait" for item in admitted_events) + 1
        > policy["max_wait_cycles"]
    ):
        return "WAIT_BUDGET_EXHAUSTED"
    if event["kind"] == "no_delta_wakeup" and (
        sum(
            item["kind"] == "no_delta_wakeup" for item in admitted_events
        )
        + 1
        > policy["max_no_delta_wakeups"]
    ):
        return "NO_DELTA_BUDGET_EXHAUSTED"
    return None


def admit_execution_event(
    policy: dict[str, Any],
    ledger: dict[str, Any],
    event: dict[str, Any],
    *,
    surface_profile: dict[str, Any] | None = None,
) -> tuple[bool, dict[str, Any]]:
    """Admit one controller event before any model/tool-side action occurs."""

    ledger = deepcopy(ledger)
    if ledger.get("terminal_reason") is not None:
        return False, ledger
    if not isinstance(event, dict) or set(event) != EVENT_INPUT_FIELDS:
        raise ValueError("execution event fields do not match contract")
    if (
        event.get("kind") not in EVENT_KINDS
        or event.get("watcher_id") != ledger.get("watcher_id")
        or not isinstance(event.get("event_id"), str)
        or not event["event_id"].strip()
        or not isinstance(event.get("node_id"), str)
        or not event["node_id"].strip()
        or not isinstance(event.get("spawn_depth"), int)
        or isinstance(event.get("spawn_depth"), bool)
        or event["spawn_depth"] < 0
    ):
        raise ValueError("execution event identity, watcher, or depth is invalid")
    outcome_error = _event_outcome_error(event, allow_rejected=False)
    if outcome_error is not None:
        raise ValueError(f"execution event {outcome_error}")
    call_digest_error = _event_call_digest_error(event)
    if call_digest_error is not None:
        raise ValueError(f"execution event {call_digest_error}")
    if surface_profile is not None:
        coverage_error = _surface_event_coverage_error(
            ledger, event, surface_profile
        )
        if coverage_error is not None:
            raise ValueError(f"execution event {coverage_error}")
    events = ledger["events"]
    completed = [item for item in events if item.get("outcome") != "rejected"]
    if event["event_id"] in {
        item.get("event_id") for item in events if isinstance(item, dict)
    }:
        raise ValueError("execution event event_id must be unique")
    terminated_lineages = {
        (item.get("node_id"), item.get("spawn_depth"))
        for item in completed
        if item.get("kind") == "terminate"
    }
    if (
        event["kind"] != "root_turn"
        and (event["node_id"], event["spawn_depth"]) in terminated_lineages
    ):
        raise ValueError("execution event node lineage is already terminated")
    if not completed and event["kind"] != "root_turn":
        raise ValueError("execution ledger first event must be root_turn")
    if completed and event["kind"] == "root_turn":
        raise ValueError("execution ledger admits exactly one root_turn")
    prior_admitted = {
        str(item.get("event_id")): item for item in completed
    }
    structural_lineage_error = _event_lineage_error(
        event,
        prior_admitted,
        enforce_depth=event["kind"] == "root_turn",
    )
    if structural_lineage_error is not None:
        raise ValueError(f"execution event {structural_lineage_error}")
    rejection_reason = _budget_rejection_reason(policy, completed, event)
    if rejection_reason == "SPAWN_DEPTH_EXCEEDED":
        return _reject_event(ledger, event, rejection_reason)
    lineage_error = _event_lineage_error(
        event, prior_admitted
    )
    if lineage_error is not None:
        raise ValueError(f"execution event {lineage_error}")
    if rejection_reason is not None:
        return _reject_event(ledger, event, rejection_reason)
    accepted = {**event, "sequence": len(events)}
    events.append(accepted)
    ledger["ledger_digest"] = _ledger_digest(ledger)
    return True, ledger


def validate_execution_event_ledger(
    policy: dict[str, Any],
    ledger: Any,
    *,
    call_record_digests: list[str],
    surface_profile: dict[str, Any] | None = None,
) -> list[str]:
    if not isinstance(ledger, dict) or set(ledger) != LEDGER_FIELDS:
        return ["execution event ledger fields do not match contract"]
    errors: list[str] = []
    if ledger.get("schema_version") != "execution_event_ledger_v1":
        errors.append("execution event ledger schema_version is invalid")
    if ledger.get("policy_digest") != execution_policy_digest(policy):
        errors.append("execution event ledger policy digest differs from authority")
    if not DIGEST_RE.fullmatch(str(ledger.get("surface_profile_digest", ""))):
        errors.append("execution event ledger surface profile digest is invalid")
    if ledger.get("ledger_digest") != _ledger_digest(ledger):
        errors.append("execution event ledger digest is invalid")
    events = ledger.get("events")
    if not isinstance(events, list):
        return [*errors, "execution event ledger events must be a list"]
    admitted_roots = [
        index
        for index, event in enumerate(events)
        if isinstance(event, dict)
        and event.get("kind") == "root_turn"
        and event.get("outcome") != "rejected"
    ]
    if admitted_roots != [0]:
        errors.append(
            "execution event ledger requires exactly one first root_turn"
        )
    prior_admitted_events: dict[str, dict[str, Any]] = {}
    terminated_lineages: set[tuple[Any, Any]] = set()
    seen_event_ids: set[str] = set()
    for index, event in enumerate(events):
        if not isinstance(event, dict) or set(event) != EVENT_FIELDS:
            errors.append(f"execution event {index} fields are invalid")
            continue
        if event.get("sequence") != index:
            errors.append("execution event sequence is not contiguous")
        if event.get("kind") not in EVENT_KINDS:
            errors.append("execution event kind is invalid")
        if event.get("watcher_id") != ledger.get("watcher_id"):
            errors.append("execution event watcher differs from the wave watcher")
        outcome_error = _event_outcome_error(event, allow_rejected=True)
        if outcome_error is not None:
            errors.append(f"execution event {index} {outcome_error}")
        if not isinstance(event.get("node_id"), str) or not event["node_id"].strip():
            errors.append(f"execution event {index} node_id is invalid")
        call_digest_error = _event_call_digest_error(event)
        if call_digest_error is not None:
            errors.append(f"execution event {index} {call_digest_error}")
        if surface_profile is not None:
            coverage_error = _surface_event_coverage_error(
                ledger, event, surface_profile
            )
            if coverage_error is not None:
                errors.append(f"execution event {index} {coverage_error}")
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip():
            errors.append(f"execution event {index} event_id is invalid")
        elif event_id in seen_event_ids:
            errors.append(f"execution event {index} event_id is duplicated")
        else:
            seen_event_ids.add(event_id)
        allow_rejected_depth_overflow = (
            event.get("outcome") == "rejected"
            and ledger.get("terminal_reason") == "SPAWN_DEPTH_EXCEEDED"
            and isinstance(event.get("spawn_depth"), int)
            and event["spawn_depth"] > policy["max_spawn_depth_from_root"]
        )
        lineage_error = _event_lineage_error(
            event,
            prior_admitted_events,
            enforce_depth=not allow_rejected_depth_overflow,
        )
        if lineage_error is not None:
            errors.append(f"execution event {index} {lineage_error}")
        lineage = (event.get("node_id"), event.get("spawn_depth"))
        if event.get("kind") != "root_turn" and lineage in terminated_lineages:
            errors.append(
                f"execution event {index} occurs after its node lineage terminated"
            )
        if event.get("outcome") != "rejected":
            if isinstance(event_id, str):
                prior_admitted_events[event_id] = event
            if event.get("kind") == "terminate":
                terminated_lineages.add(lineage)
    admitted_events = [
        event
        for event in events
        if isinstance(event, dict) and event.get("outcome") != "rejected"
    ]
    completed_calls = [
        event["call_record_digest"]
        for event in admitted_events
        if event.get("kind") in SAMPLING_KINDS
    ]
    completed_call_attempts = [
        event
        for event in admitted_events
        if event.get("kind") in CALL_ATTEMPT_KINDS
    ]
    if completed_calls != call_record_digests:
        errors.append("execution event ledger does not exact-cover call records")
    if len(completed_call_attempts) > policy["max_call_attempts"]:
        errors.append("execution event ledger exceeds the call-attempt cap")
    if len(completed_calls) + 1 > policy["max_total_model_turns"]:
        errors.append("execution event ledger exceeds the total model-turn cap")
    admitted_retry_count = sum(
        event.get("kind") == "retry" for event in admitted_events
    )
    if admitted_retry_count > policy["retry_budget"]:
        errors.append("execution event ledger exceeds the retry budget")
    delegated_nodes = {
        event.get("node_id")
        for event in events
        if isinstance(event, dict)
        and event.get("outcome") != "rejected"
        and event.get("kind") != "root_turn"
    }
    if len(delegated_nodes) > policy["max_unique_nodes"]:
        errors.append(
            "execution event ledger exceeds the distinct delegated-node cap"
        )
    if sum(
        event.get("kind") == "follow_up" for event in admitted_events
    ) > policy["max_followup_attempts"]:
        errors.append("execution event ledger exceeds the follow-up cap")
    if sum(
        event.get("kind") == "wait" for event in admitted_events
    ) > policy["max_wait_cycles"]:
        errors.append("execution event ledger exceeds the wait cap")
    if sum(
        event.get("kind") == "no_delta_wakeup" for event in admitted_events
    ) > policy["max_no_delta_wakeups"]:
        errors.append("execution event ledger exceeds the no-delta cap")
    if any(
        isinstance(event.get("spawn_depth"), int)
        and event["spawn_depth"] > policy["max_spawn_depth_from_root"]
        and event.get("outcome") != "rejected"
        for event in events
    ):
        errors.append("execution event ledger contains an admitted recursive spawn")
    terminal = ledger.get("terminal_reason")
    if terminal is not None and terminal not in TERMINAL_REASONS:
        errors.append("execution event ledger terminal reason is invalid")
    rejected_indexes = [
        index for index, event in enumerate(events) if event.get("outcome") == "rejected"
    ]
    if terminal is not None and not rejected_indexes:
        errors.append(
            "execution event ledger terminal reason requires one final rejected event"
        )
    if rejected_indexes and terminal is None:
        errors.append(
            "execution event ledger final rejected event requires a terminal reason"
        )
    if len(rejected_indexes) > 1:
        errors.append("execution event ledger admits only one terminal rejected event")
    if rejected_indexes and rejected_indexes[-1] != len(events) - 1:
        errors.append("execution event ledger contains work after terminal rejection")
    if (
        len(rejected_indexes) == 1
        and rejected_indexes[0] == len(events) - 1
        and terminal is not None
    ):
        rejected_index = rejected_indexes[0]
        expected_terminal = _budget_rejection_reason(
            policy,
            [
                event
                for event in events[:rejected_index]
                if isinstance(event, dict)
                and event.get("outcome") != "rejected"
            ],
            events[rejected_index],
        )
        if terminal != expected_terminal:
            errors.append(
                "execution event ledger terminal reason does not match policy denial"
            )
    return errors
