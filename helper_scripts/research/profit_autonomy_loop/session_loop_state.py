#!/usr/bin/env python3
"""Build a source-only anti-repeat session loop checkpoint.

The packet consumes an already-supplied loop-state JSON snapshot and applies
the Profit-first Demo-learning Autonomy Improvement Loop anti-repeat rules.
It does not inspect git, runtime, crontab, services, PG, Bybit, or artifacts by
itself, and it never grants probe/order/live authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "profit_first_demo_learning_session_loop_state_v1"
DEFAULT_BLOCKER_ORDER = [
    "P0-PROFIT-EVIDENCE-QUALITY",
    "P0-PROFIT-CANDIDATE-SELECTION",
    "P0-BOUNDED-PROBE-AUTHORIZATION",
    "P0-PROFIT-OUTCOME-REVIEW",
    "P1-LEARNING-LOOP-CLOSURE",
    "P1-AUTONOMOUS-PARAMETER-PROPOSAL",
    "P1-RUNTIME-HEALTH-HYGIENE",
]
ALLOWED_TRANSITIONS = {
    "DONE",
    "DONE_WITH_CONCERNS",
    "BLOCKED_BY_OPERATOR_ACTION",
    "BLOCKED_BY_RUNTIME_AUTHORIZATION",
    "NO-OP_ALREADY_DONE",
    "NO-OP_NO_EVIDENCE_DELTA",
}
AUTHORITY_BEARING_TRUE_KEYS = {
    "crontab_mutation_performed",
    "global_cost_gate_lowering_recommended",
    "live_promotion_performed",
    "order_authority_granted",
    "order_cancel_modify_performed",
    "order_submission_performed",
    "pg_write_performed",
    "probe_authority_granted",
    "promotion_evidence",
    "runtime_mutation_performed",
    "service_restart_performed",
    "writer_enabled",
}
TRUTHY = {
    "1",
    "true",
    "yes",
    "y",
    "on",
    "enabled",
    "grant",
    "granted",
    "authorize",
    "authorized",
}
BOUNDARY = (
    "source-only anti-repeat loop checkpoint from supplied state; no git/runtime/"
    "crontab/service/PG/Bybit inspection, no mutation, no Cost Gate lowering, "
    "no probe/order/live authority, and no promotion proof"
)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return str(value or "").strip()


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in TRUTHY
    return False


def _as_set(value: Any) -> set[str]:
    if isinstance(value, dict):
        return {_str(key) for key, present in value.items() if _truthy(present)}
    return {_str(item) for item in _list(value) if _str(item)}


def _normal(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normal(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_normal(item) for item in value]
    return value


def _snapshot(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_head": state.get("source_head"),
        "runtime_timestamp": state.get("runtime_timestamp"),
        "runtime_snapshot_revision": state.get("runtime_snapshot_revision"),
        "pg_snapshot_timestamp": state.get("pg_snapshot_timestamp"),
        "pg_snapshot_revision": state.get("pg_snapshot_revision"),
        "artifact_mtimes": _dict(state.get("artifact_mtimes")),
        "artifact_revisions": _dict(state.get("artifact_revisions")),
        "exchange_snapshot": _dict(state.get("exchange_snapshot")),
        "open_order_snapshot": _dict(state.get("open_order_snapshot")),
        "fill_lineage_snapshot": _dict(state.get("fill_lineage_snapshot")),
        "operator_authorization_revision": state.get("operator_authorization_revision"),
    }


def _snapshot_defaults(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_head": snapshot.get("source_head"),
        "runtime_timestamp": snapshot.get("runtime_timestamp"),
        "runtime_snapshot_revision": snapshot.get("runtime_snapshot_revision"),
        "pg_snapshot_timestamp": snapshot.get("pg_snapshot_timestamp"),
        "pg_snapshot_revision": snapshot.get("pg_snapshot_revision"),
        "artifact_mtimes": _dict(snapshot.get("artifact_mtimes")),
        "artifact_revisions": _dict(snapshot.get("artifact_revisions")),
        "exchange_snapshot": _dict(snapshot.get("exchange_snapshot")),
        "open_order_snapshot": _dict(snapshot.get("open_order_snapshot")),
        "fill_lineage_snapshot": _dict(snapshot.get("fill_lineage_snapshot")),
        "operator_authorization_revision": snapshot.get("operator_authorization_revision"),
    }


def _same_snapshot(current: dict[str, Any], previous: dict[str, Any]) -> bool:
    return _normal(_snapshot(current)) == _normal(_snapshot_defaults(previous))


def _previous_snapshot_for(state: dict[str, Any], blocker_id: str) -> dict[str, Any]:
    snapshots = _dict(state.get("previous_evidence_snapshots"))
    return _dict(snapshots.get(blocker_id))


def _previous_reports_for(state: dict[str, Any], blocker_id: str) -> list[str]:
    reports = state.get("previous_report_paths")
    if isinstance(reports, dict):
        return [_str(item) for item in _list(reports.get(blocker_id)) if _str(item)]
    return [_str(item) for item in _list(reports) if _str(item)]


def _block_reason(state: dict[str, Any], blocker_id: str) -> str:
    reasons = _dict(state.get("blocked_reasons"))
    reason = _str(reasons.get(blocker_id))
    if reason:
        return reason
    text = _str(state.get("blocked_reason"))
    return text


def _consecutive_block_count(state: dict[str, Any], blocker_id: str) -> int:
    counts = _dict(state.get("consecutive_block_counts"))
    try:
        return int(counts.get(blocker_id, 0))
    except (TypeError, ValueError):
        return 0


def _ordered_blockers(state: dict[str, Any]) -> list[str]:
    blockers = [_str(item) for item in _list(state.get("ordered_blockers")) if _str(item)]
    return blockers or list(DEFAULT_BLOCKER_ORDER)


def _next_blocker_id(state: dict[str, Any], active_blocker_id: str) -> str | None:
    ordered = _ordered_blockers(state)
    completed = _as_set(state.get("completed_blockers"))
    blocked = _as_set(state.get("blocked_blockers"))
    try:
        start = ordered.index(active_blocker_id) + 1
    except ValueError:
        start = 0
    for blocker_id in ordered[start:] + ordered[:start]:
        if blocker_id == active_blocker_id:
            continue
        if blocker_id in completed:
            continue
        if blocker_id in blocked and not _source_only_progress_allowed(state, blocker_id):
            continue
        return blocker_id
    return None


def _source_only_scope_id(state: dict[str, Any]) -> str:
    return _str(state.get("source_only_scope_id"))


def _source_only_progress_allowed(state: dict[str, Any], active: str) -> bool:
    if active.startswith("P0-"):
        return False
    source_only = _as_set(state.get("source_only_progress_blockers"))
    if active not in source_only:
        return False
    scope_id = _source_only_scope_id(state)
    if not scope_id:
        return False
    completed_scopes = _as_set(state.get("completed_source_only_scope_ids"))
    if scope_id in completed_scopes:
        return False
    blocked = _as_set(state.get("blocked_blockers"))
    allowed_blocked = _as_set(state.get("source_only_allowed_blockers"))
    return active not in blocked or active in allowed_blocked


def _authority_boundary_preserved(payload: dict[str, Any]) -> bool:
    stack: list[Any] = [payload]
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            stack.extend(item)
            continue
        data = _dict(item)
        if not data:
            continue
        if data.get("main_cost_gate_adjustment") not in (None, "", "NONE"):
            return False
        for key in AUTHORITY_BEARING_TRUE_KEYS:
            if _truthy(data.get(key)):
                return False
        stack.extend(value for value in data.values() if isinstance(value, (dict, list)))
    return True


def _decision(state: dict[str, Any]) -> tuple[str, str, bool, str | None]:
    active = _str(state.get("active_blocker_id"))
    completed = _as_set(state.get("completed_blockers"))
    blocked = _as_set(state.get("blocked_blockers"))
    previous_reports = _previous_reports_for(state, active)
    previous_snapshot = _previous_snapshot_for(state, active)
    snapshot_delta_found = bool(previous_snapshot) and not _same_snapshot(
        state, previous_snapshot
    )
    source_only_allowed = _source_only_progress_allowed(state, active)
    no_new_delta = (
        bool(previous_reports)
        and bool(previous_snapshot)
        and not snapshot_delta_found
        and not _truthy(state.get("new_evidence_delta_found"))
    )
    block_reason = _block_reason(state, active).lower()
    repeated_block_count = _consecutive_block_count(state, active)

    if not _authority_boundary_preserved(state):
        return (
            "BLOCKED_BY_OPERATOR_ACTION",
            "authority_boundary_violation_in_supplied_loop_state",
            False,
            _next_blocker_id(state, active),
        )
    if active in completed:
        return (
            "NO-OP_ALREADY_DONE",
            "active_blocker_already_in_completed_blockers",
            False,
            _next_blocker_id(state, active),
        )
    if repeated_block_count >= 2 and (
        "runtime" in block_reason or "permission" in block_reason
    ):
        return (
            "BLOCKED_BY_RUNTIME_AUTHORIZATION",
            "active_blocker_repeatedly_blocked_by_runtime_authorization",
            False,
            _next_blocker_id(state, active),
        )
    if repeated_block_count >= 2 and (
        "operator" in block_reason or "authorization" in block_reason
    ):
        return (
            "BLOCKED_BY_OPERATOR_ACTION",
            "active_blocker_repeatedly_blocked_by_operator_action",
            False,
            _next_blocker_id(state, active),
        )
    if active in blocked and not source_only_allowed:
        if "runtime" in block_reason or "permission" in block_reason:
            status = "BLOCKED_BY_RUNTIME_AUTHORIZATION"
            reason = "active_blocker_blocked_by_runtime_authorization"
        else:
            status = "BLOCKED_BY_OPERATOR_ACTION"
            reason = "active_blocker_blocked_by_operator_action"
        return status, reason, False, _next_blocker_id(state, active)
    if no_new_delta and not source_only_allowed:
        return (
            "NO-OP_NO_EVIDENCE_DELTA",
            "previous_report_exists_and_supplied_evidence_snapshot_has_no_delta",
            False,
            _next_blocker_id(state, active),
        )
    if source_only_allowed:
        return (
            "DONE_WITH_CONCERNS",
            "source_only_progress_allowed_for_active_blocker",
            True,
            _next_blocker_id(state, active),
        )
    if snapshot_delta_found:
        return (
            "DONE_WITH_CONCERNS",
            "supplied_evidence_snapshot_delta_allows_active_blocker_progress",
            True,
            _next_blocker_id(state, active),
        )
    if _truthy(state.get("new_evidence_delta_found")):
        return (
            "DONE_WITH_CONCERNS",
            "new_evidence_delta_allows_active_blocker_progress",
            True,
            _next_blocker_id(state, active),
        )
    return (
        "NO-OP_NO_EVIDENCE_DELTA",
        "no_new_evidence_delta_and_no_source_only_progress_declared",
        False,
        _next_blocker_id(state, active),
    )


def build_session_loop_state_packet(
    state: dict[str, Any],
    *,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    active = _str(state.get("active_blocker_id"))
    status, reason, dispatch_allowed, next_blocker_id = _decision(state)
    active = _str(state.get("active_blocker_id"))
    previous_snapshot = _previous_snapshot_for(state, active)
    snapshot_delta_found = bool(previous_snapshot) and not _same_snapshot(
        state, previous_snapshot
    )
    if status not in ALLOWED_TRANSITIONS:
        raise AssertionError(f"unexpected transition status: {status}")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "active_blocker_id": active,
        "blocker_goal": state.get("blocker_goal"),
        "profit_relevance": state.get("profit_relevance"),
        "anti_repeat_decision": reason,
        "dispatch_allowed": dispatch_allowed,
        "action_taken_or_noop_reason": reason,
        "next_blocker_id": next_blocker_id or state.get("next_blocker_id"),
        "why_not_repeating_current_blocker": (
            reason if not dispatch_allowed else "source_only_progress_has_distinct_scope"
        ),
        "session_loop_state": {
            "session_goal": state.get("session_goal"),
            "active_blocker_id": active,
            "blocker_goal": state.get("blocker_goal"),
            "profit_relevance": state.get("profit_relevance"),
            "completed_blockers": sorted(_as_set(state.get("completed_blockers"))),
            "blocked_blockers": sorted(_as_set(state.get("blocked_blockers"))),
            "previous_report_paths": state.get("previous_report_paths") or [],
            "source_head": state.get("source_head"),
            "runtime_timestamp": state.get("runtime_timestamp"),
            "runtime_snapshot_revision": state.get("runtime_snapshot_revision"),
            "pg_snapshot_timestamp": state.get("pg_snapshot_timestamp"),
            "pg_snapshot_revision": state.get("pg_snapshot_revision"),
            "artifact_mtimes": _dict(state.get("artifact_mtimes")),
            "artifact_revisions": _dict(state.get("artifact_revisions")),
            "exchange_snapshot": _dict(state.get("exchange_snapshot")),
            "open_order_snapshot": _dict(state.get("open_order_snapshot")),
            "fill_lineage_snapshot": _dict(state.get("fill_lineage_snapshot")),
            "operator_action_required": state.get("operator_action_required"),
            "new_evidence_delta_required": state.get("new_evidence_delta_required"),
            "new_evidence_delta_found": state.get("new_evidence_delta_found"),
            "source_only_scope_id": _source_only_scope_id(state) or None,
            "acceptance_criteria": state.get("acceptance_criteria"),
            "next_blocker_id": next_blocker_id or state.get("next_blocker_id"),
        },
        "evidence_snapshot": _snapshot(state),
        "previous_evidence_snapshot": previous_snapshot,
        "evidence_snapshot_delta_found": snapshot_delta_found,
        "previous_report_count": len(_previous_reports_for(state, active)),
        "answers": {
            "dispatch_allowed": dispatch_allowed,
            "operator_action_required": state.get("operator_action_required") is True,
            "new_evidence_delta_found": (
                state.get("new_evidence_delta_found") is True or snapshot_delta_found
            ),
            "bybit_call_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "crontab_mutation_performed": False,
            "service_restart_performed": False,
            "runtime_mutation_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# Profit-first Session Loop State Packet",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Active blocker: `{packet.get('active_blocker_id')}`",
        f"- Anti-repeat decision: `{packet.get('anti_repeat_decision')}`",
        f"- Dispatch allowed: `{packet.get('dispatch_allowed')}`",
        f"- Next blocker: `{packet.get('next_blocker_id')}`",
        f"- Boundary: {BOUNDARY}.",
        "",
        "## No-Authority Answers",
        "",
    ]
    for key, value in _dict(packet.get("answers")).items():
        lines.append(f"- `{key}`: `{value}`")
    return "\n".join(lines) + "\n"


def _read_json(path: Path | None) -> tuple[dict[str, Any] | None, str | None]:
    if path is None:
        return None, "missing_path"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "missing"
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return None, f"{type(exc).__name__}:{exc}"
    if not isinstance(payload, dict):
        return None, "not_object"
    return payload, None


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-json", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    state, error = _read_json(args.state_json)
    if error:
        packet = build_session_loop_state_packet(
            {
                "active_blocker_id": "UNKNOWN",
                "blocker_goal": "load supplied session loop state",
                "profit_relevance": "anti-repeat gate cannot run without valid state",
                "blocked_blockers": ["UNKNOWN"],
                "blocked_reason": error,
                "operator_action_required": True,
            }
        )
    else:
        packet = build_session_loop_state_packet(state or {})
    markdown = render_markdown(packet)
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.output:
        _write_text(args.output, markdown)
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True))
    elif not args.output:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
