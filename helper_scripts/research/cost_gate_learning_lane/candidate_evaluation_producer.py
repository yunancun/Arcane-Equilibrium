"""Attach explicit cold evaluation evidence before an outcome becomes appendable.

The attached projection is ex-post selection/evidence lineage only.  It must
never be unpacked into PIT training, online, or inference features.  Any
predictive D-1 feature needs its own event-time-cutoff manifest and derivation.
"""

from __future__ import annotations

import copy
import datetime as dt
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from cost_gate_learning_lane.contract import (
    ADMIT_DECISION,
    BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE,
    PROBE_OUTCOME_RECORD_TYPE,
)
from cost_gate_learning_lane.candidate_evaluation_context import (
    attach_candidate_evaluation_context,
    build_candidate_evaluation_context,
    validate_candidate_event_context,
    validate_candidate_evaluation_context,
)
from cost_gate_learning_lane.candidate_evaluation_cold_source import (
    DEFAULT_GIT_ANCESTRY_RESOLVER,
    DEFER,
    PERMANENTLY_UNAVAILABLE,
    PRE_CAPABILITY_BUILD,
    READY,
    CandidateEvaluationSourceResolution,
    GitAncestryResolver,
    build_candidate_evaluation_source_unavailability,
    validate_candidate_evaluation_source_unavailability,
)


ATTACHED = "ATTACHED"
DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE = (
    "DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE"
)
NOT_APPLICABLE = "NOT_APPLICABLE"
_DEFAULT_ANCESTRY_RESOLVER = DEFAULT_GIT_ANCESTRY_RESOLVER

_SOURCE_BUNDLE_FIELDS = {
    "evidence_regime_label",
    "regime_entry_counts",
    "target_regime_context",
    "context_hashes",
    "resource",
    "portfolio",
    "proof",
    "hidden_oos_state",
}
_HIDDEN_OOS_FIELDS = {
    "schema_version",
    "state",
    "open_count",
    "opened_for_iteration",
    "consumed",
    "invalidated",
    "family_id",
    "split_hash",
    "state_hash",
}
_EVALUATION_FIELDS = {
    "candidate_evaluation_context",
    "candidate_evaluation_context_status",
    "candidate_learning_context_projection",
    "candidate_learning_context",
}
_EVALUATION_CLAIM_FIELDS = {
    "candidate_evaluation_context",
    "candidate_evaluation_context_status",
    "candidate_learning_context_projection",
}
_SOURCE_UNAVAILABILITY_FIELDS = {
    "candidate_evaluation_source_status",
    "candidate_evaluation_source_unavailability",
}
_SAFE_FAMILY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_SAFE_GAP_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,127}\Z")
_SENSITIVE_TOKEN_MARKERS = (
    "SECRET",
    "PASSWORD",
    "CREDENTIAL",
    "API_KEY",
    "PRIVATE_KEY",
    "ACCESS_TOKEN",
    "AUTH_TOKEN",
    "BEARER_TOKEN",
    "REFRESH_TOKEN",
    "API_TOKEN",
    "DSN",
    "PASSWD",
    "PWD",
)
_SQL_TOKEN_PREFIXES = (
    "SELECT",
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "CREATE",
)

CandidateEvaluationSourceProvider = Callable[
    [dict[str, Any], str],
    Mapping[str, Any] | CandidateEvaluationSourceResolution | None,
]


def attach_candidate_evaluation_to_outcome(
    outcome: Mapping[str, Any],
    *,
    source_provider: CandidateEvaluationSourceProvider | None = None,
    ancestry_resolver: GitAncestryResolver | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    """Return one detached ATTACHED, DEFER, PERMANENT, or N/A result.

    ``source_provider`` is an explicit validation seam, not proof that its
    caller is authoritative.  Production callers intentionally pass ``None``
    until a separately governed cold-source provider exists; current/board
    state must never be wired here as an implicit source.
    """
    resolver = ancestry_resolver or _DEFAULT_ANCESTRY_RESOLVER
    try:
        row = copy.deepcopy(dict(outcome))
    except Exception:
        return _result(DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE, {})

    record_type = row.get("record_type")
    if not isinstance(record_type, str):
        return _result(DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE, row)
    if (
        record_type == PROBE_OUTCOME_RECORD_TYPE
        or record_type == BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE
    ) and not outcome_subtype_semantics_valid(row):
        return _result(DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE, row)
    if record_type != BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE:
        return _result(NOT_APPLICABLE, row)

    try:
        summary_value = row.get("candidate_summary")
        if isinstance(summary_value, Mapping):
            summary = copy.deepcopy(
                {key: summary_value[key] for key in summary_value}
            )
            row["candidate_summary"] = summary
        else:
            summary = {}
        claim_fields = _EVALUATION_CLAIM_FIELDS & set(summary)
        unavailability_fields = _SOURCE_UNAVAILABILITY_FIELDS & set(summary)
    except Exception:
        return _result(DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE, {})

    try:
        event = _validated_bound_candidate_event(
            row,
            summary,
            evaluation_claimed=bool(claim_fields or unavailability_fields),
        )
    except Exception:
        return _result(DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE, row)

    if event is None:
        return _result(NOT_APPLICABLE, row)

    try:
        captured_at = dt.datetime.fromtimestamp(
            event["captured_at_ms"] / 1_000,
            tz=dt.timezone.utc,
        )
        as_of_date = captured_at.date() + dt.timedelta(days=1)
        as_of_utc_date = as_of_date.isoformat()
        day_closed_at = dt.datetime.combine(
            as_of_date,
            dt.time.min,
            tzinfo=dt.timezone.utc,
        )
        normalized_now = _normalized_utc(now_utc)
        if normalized_now is None or normalized_now < day_closed_at:
            return _result(DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE, row)

        present_evaluation_fields = _EVALUATION_FIELDS & set(summary)
        present_unavailability_fields = (
            _SOURCE_UNAVAILABILITY_FIELDS & set(summary)
        )
        if present_evaluation_fields and present_unavailability_fields:
            return _result(DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE, row)
        if present_unavailability_fields:
            if present_unavailability_fields != _SOURCE_UNAVAILABILITY_FIELDS:
                return _result(DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE, row)
            if (
                summary["candidate_evaluation_source_status"]
                != PERMANENTLY_UNAVAILABLE
            ):
                return _result(DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE, row)
            validate_candidate_evaluation_source_unavailability(
                summary["candidate_evaluation_source_unavailability"],
                candidate_event_context=event,
            )
            if not resolver.is_strict_pre_capability(event["build_git_sha"]):
                return _result(DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE, row)
            return _result(PERMANENTLY_UNAVAILABLE, row)

        if present_evaluation_fields:
            if present_evaluation_fields != _EVALUATION_FIELDS:
                return _result(DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE, row)
            evaluation = validate_candidate_evaluation_context(
                summary["candidate_evaluation_context"]
            )
            if evaluation["as_of_utc_date"] != as_of_utc_date:
                return _result(DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE, row)
            if not _source_tokens_safe(evaluation):
                return _result(DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE, row)
            attached_summary = attach_candidate_evaluation_context(
                summary,
                candidate_evaluation_context=evaluation,
            )
            if not _exact_value_equal(attached_summary, summary):
                return _result(DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE, row)
            row["candidate_summary"] = attached_summary
            return _result(ATTACHED, row)

        if source_provider is None:
            return _result(DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE, row)

        source = source_provider(copy.deepcopy(event), as_of_utc_date)
        if isinstance(source, CandidateEvaluationSourceResolution):
            if source.status == DEFER:
                return _result(DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE, row)
            if source.status == PERMANENTLY_UNAVAILABLE:
                if not resolver.is_strict_pre_capability(
                    event["build_git_sha"]
                ):
                    return _result(
                        DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE,
                        row,
                    )
                terminal_summary = copy.deepcopy(summary)
                terminal_summary["candidate_evaluation_source_status"] = (
                    PERMANENTLY_UNAVAILABLE
                )
                terminal_summary[
                    "candidate_evaluation_source_unavailability"
                ] = build_candidate_evaluation_source_unavailability(event)
                row["candidate_summary"] = terminal_summary
                return _result(PERMANENTLY_UNAVAILABLE, row)
            if source.status != READY:
                return _result(DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE, row)
            source = source.bundle
        if not isinstance(source, Mapping) or set(source) != _SOURCE_BUNDLE_FIELDS:
            return _result(DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE, row)
        hidden_oos_state = source.get("hidden_oos_state")
        if (
            not isinstance(hidden_oos_state, Mapping)
            or set(hidden_oos_state) != _HIDDEN_OOS_FIELDS
            or not _source_tokens_safe(source)
        ):
            return _result(DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE, row)
        source_bundle = copy.deepcopy(dict(source))
        evaluation = build_candidate_evaluation_context(
            candidate_event_context=event,
            as_of_utc_date=as_of_utc_date,
            **source_bundle,
        )
        attached_summary = attach_candidate_evaluation_context(
            summary,
            candidate_evaluation_context=evaluation,
        )
    except Exception:
        return _result(DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE, row)

    row["candidate_summary"] = attached_summary
    return _result(ATTACHED, row)


def partition_candidate_evaluation_outcomes(
    outcomes: Sequence[Mapping[str, Any]],
    *,
    source_provider: CandidateEvaluationSourceProvider | None = None,
    ancestry_resolver: GitAncestryResolver | None = None,
    now_utc: dt.datetime,
) -> dict[str, Any]:
    """Preflight the whole batch and expose appendable rows only if none defer."""
    results = []
    for row in outcomes:
        try:
            record_type = row.get("record_type")
        except Exception:
            record_type = None
        if (
            record_type != PROBE_OUTCOME_RECORD_TYPE
            and record_type != BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE
        ):
            try:
                detached = copy.deepcopy(dict(row))
            except Exception:
                detached = {}
            results.append(
                _result(DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE, detached)
            )
            continue
        results.append(
            attach_candidate_evaluation_to_outcome(
                row,
                source_provider=source_provider,
                ancestry_resolver=ancestry_resolver,
                now_utc=now_utc,
            )
        )
    _defer_mixed_generation_conflicts(results, outcomes)
    attached_count = sum(result["status"] == ATTACHED for result in results)
    deferred_count = sum(
        result["status"] == DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE
        for result in results
    )
    # Backward-compatible aggregate: both contextless history and a truthful
    # permanent source terminal are appendable without evaluation enrichment.
    not_applicable_count = sum(
        result["status"] in {NOT_APPLICABLE, PERMANENTLY_UNAVAILABLE}
        for result in results
    )
    eligible_count = attached_count + deferred_count
    batch_deferred = deferred_count > 0
    appendable = [] if batch_deferred else [result["outcome"] for result in results]
    probe_outcomes = [
        row for row in appendable if row.get("record_type") == "probe_outcome"
    ]
    blocked_outcomes = [
        row
        for row in appendable
        if row.get("record_type") == "blocked_signal_outcome"
    ]
    defer_reason_counts = (
        {DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE: deferred_count}
        if deferred_count
        else {}
    )
    return {
        "generated_outcome_count": eligible_count + not_applicable_count,
        "candidate_evaluation_eligible_count": eligible_count,
        "candidate_evaluation_preflight_attached_count": attached_count,
        "candidate_evaluation_deferred_count": deferred_count,
        "candidate_evaluation_not_applicable_count": not_applicable_count,
        "candidate_evaluation_defer_reason_counts": defer_reason_counts,
        "candidate_evaluation_batch_deferred": batch_deferred,
        "deferred_outcome_count": deferred_count,
        "outcomes": appendable,
        "probe_outcomes": probe_outcomes,
        "blocked_signal_outcomes": blocked_outcomes,
    }


def outcome_subtype_semantics_valid(row: Mapping[str, Any]) -> bool:
    """Reject record-type relabeling before an outcome row is appended."""
    record_type = row.get("record_type")
    decision = row.get("source_admission_decision")
    allowed = row.get("allowed_to_submit_order")
    source = row.get("outcome_source")
    if record_type == PROBE_OUTCOME_RECORD_TYPE:
        return bool(
            decision == ADMIT_DECISION
            and allowed is True
            and source == "market_markout_proxy"
        )
    if record_type == BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE:
        return bool(
            isinstance(decision, str)
            and decision
            and decision != ADMIT_DECISION
            and allowed is False
            and source == "market_markout_proxy_for_blocked_signal"
        )
    return False


def _result(status: str, outcome: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": status,
        "defer_reason": (
            DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE
            if status == DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE
            else None
        ),
        "unavailability_reason": (
            PRE_CAPABILITY_BUILD
            if status == PERMANENTLY_UNAVAILABLE
            else None
        ),
        "outcome": outcome,
    }


def _normalized_utc(value: Any) -> dt.datetime | None:
    if not isinstance(value, dt.datetime) or value.tzinfo is None:
        return None
    return value.astimezone(dt.timezone.utc)


def _exact_value_equal(left: Any, right: Any) -> bool:
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return set(left) == set(right) and all(
            _exact_value_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _exact_value_equal(left_item, right_item)
            for left_item, right_item in zip(left, right)
        )
    return type(left) is type(right) and left == right


def _validated_bound_candidate_event(
    row: Mapping[str, Any],
    summary: Mapping[str, Any],
    *,
    evaluation_claimed: bool,
) -> dict[str, Any] | None:
    """Validate raw context and bind it to both outer event and outcome row."""
    raw_status = summary.get("candidate_event_context_status")
    raw_value = summary.get("candidate_event_context")
    outer_value = row.get("event")
    outer_has_context = bool(
        isinstance(outer_value, Mapping)
        and "candidate_event_context" in outer_value
    )

    if not outer_has_context:
        if (
            evaluation_claimed
            or raw_value is not None
            or raw_status not in {None, "UNQUALIFIED_CONTEXT_MISSING"}
        ):
            raise ValueError("CANDIDATE_EVENT_CONTEXT_OUTER_MISSING")
        return None

    outer_event = copy.deepcopy(
        {key: outer_value[key] for key in outer_value}
    )
    outer_context = validate_candidate_event_context(
        outer_event["candidate_event_context"]
    )
    _validate_outer_event_bindings(outer_event, outer_context)
    if raw_status != "VALID" or not isinstance(raw_value, Mapping):
        raise ValueError("CANDIDATE_EVENT_CONTEXT_SUMMARY_MISSING")
    raw_event = validate_candidate_event_context(raw_value)
    if not _exact_value_equal(raw_event, outer_context):
        raise ValueError("CANDIDATE_EVENT_CONTEXT_SUMMARY_CONFLICT")
    _validate_outcome_row_bindings(row, raw_event)
    return raw_event


def _validate_outer_event_bindings(
    outer_event: Mapping[str, Any],
    context: Mapping[str, Any],
) -> None:
    for outer_field, context_field in (
        ("strategy_name", "strategy_name"),
        ("symbol", "symbol"),
        ("side", "side"),
        ("context_id", "context_id"),
        ("signal_id", "signal_id"),
        ("engine_mode", "evidence_engine_mode"),
        ("ts_ms", "captured_at_ms"),
    ):
        if (
            outer_field not in outer_event
            or not _exact_value_equal(
                outer_event[outer_field],
                context[context_field],
            )
        ):
            raise ValueError("CANDIDATE_EVENT_CONTEXT_OUTER_BINDING_MISMATCH")


def _validate_outcome_row_bindings(
    row: Mapping[str, Any],
    event: Mapping[str, Any],
) -> None:
    identity = {
        "strategy_name": event["strategy_name"],
        "symbol": event["symbol"],
        "side": event["side"],
        "horizon_minutes": event["horizon_policy"]["outcome_horizon_minutes"],
        "event_ts_ms": event["captured_at_ms"],
        "attempt_id": event["context_id"],
        "side_cell_key": (
            f"{event['strategy_name']}|{event['symbol']}|{event['side']}"
        ),
    }
    if not all(
        field in row and _exact_value_equal(row[field], expected)
        for field, expected in identity.items()
    ):
        raise ValueError("CANDIDATE_OUTCOME_OUTER_BINDING_MISMATCH")


def _source_tokens_safe(source: Mapping[str, Any]) -> bool:
    hidden = source.get("hidden_oos_state")
    proof = source.get("proof")
    next_gap = proof.get("next_gap") if isinstance(proof, Mapping) else None
    family_id = hidden.get("family_id") if isinstance(hidden, Mapping) else None
    gap_code = next_gap.get("code") if isinstance(next_gap, Mapping) else None
    return bool(
        _token_safe(family_id, pattern=_SAFE_FAMILY_ID)
        and _token_safe(gap_code, pattern=_SAFE_GAP_CODE)
    )


def _token_safe(value: Any, *, pattern: re.Pattern[str]) -> bool:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        return False
    normalized = value.upper()
    pieces = set(re.split(r"[_.-]", normalized))
    return (
        not any(marker in normalized for marker in _SENSITIVE_TOKEN_MARKERS)
        and "AUTH" not in pieces
        and not any(
            normalized == prefix or normalized.startswith(prefix + "_")
            for prefix in _SQL_TOKEN_PREFIXES
        )
    )


def _defer_mixed_generation_conflicts(
    results: list[dict[str, Any]],
    original_outcomes: Sequence[Mapping[str, Any]],
) -> None:
    identity_event_hashes: dict[tuple[str, str], set[str]] = {}
    event_terminal_hashes: dict[str, set[tuple[str, str]]] = {}
    resolved_lineage: dict[
        int,
        tuple[tuple[str, str], str, tuple[str, str]],
    ] = {}
    for index, result in enumerate(results):
        if result["status"] not in {ATTACHED, PERMANENTLY_UNAVAILABLE}:
            continue
        try:
            row = result["outcome"]
            summary = row["candidate_summary"]
            event = summary["candidate_event_context"]
            identity_key = (row["attempt_id"], event["context_id"])
            event_hash = event["event_hash"]
            if result["status"] == ATTACHED:
                terminal_hash = summary["candidate_evaluation_context"][
                    "candidate_evaluation_context_hash"
                ]
            else:
                terminal_hash = summary[
                    "candidate_evaluation_source_unavailability"
                ]["candidate_evaluation_source_unavailability_hash"]
            terminal_identity = (result["status"], terminal_hash)
            if not all(
                isinstance(value, str) and value
                for value in (*identity_key, event_hash, terminal_hash)
            ):
                raise ValueError("RESOLVED_LINEAGE_IDENTITY_INVALID")
        except Exception:
            try:
                original = copy.deepcopy(dict(original_outcomes[index]))
            except Exception:
                original = {}
            results[index] = _result(
                DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE,
                original,
            )
            continue
        identity_event_hashes.setdefault(identity_key, set()).add(event_hash)
        event_terminal_hashes.setdefault(event_hash, set()).add(
            terminal_identity
        )
        resolved_lineage[index] = (
            identity_key,
            event_hash,
            terminal_identity,
        )

    conflicted = {
        index
        for index, (
            identity_key,
            event_hash,
            _terminal_identity,
        ) in resolved_lineage.items()
        if len(identity_event_hashes[identity_key]) > 1
        or len(event_terminal_hashes[event_hash]) > 1
    }
    for index in conflicted:
        try:
            original = copy.deepcopy(dict(original_outcomes[index]))
        except Exception:
            original = {}
        results[index] = _result(
            DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE,
            original,
        )


__all__ = [
    "ATTACHED",
    "CandidateEvaluationSourceProvider",
    "DEFER_COLD_EVALUATION_SOURCE_INCOMPLETE",
    "NOT_APPLICABLE",
    "PERMANENTLY_UNAVAILABLE",
    "attach_candidate_evaluation_to_outcome",
    "outcome_subtype_semantics_valid",
    "partition_candidate_evaluation_outcomes",
]
