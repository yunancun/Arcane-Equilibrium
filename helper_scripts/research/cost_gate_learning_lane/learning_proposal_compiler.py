#!/usr/bin/env python3
"""Compile LearningEvents into no-authority review proposal candidates.

This helper consumes the source-only LearningEvent contract and groups events
by candidate identity. The output is a review packet only: it does not query or
write PG, call Bybit, submit orders, mutate runtime state, lower Cost Gate, or
grant probe/order/live authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from cost_gate_learning_lane.learning_event_contract import (
    AUTHORITY_BOUNDARY_VIOLATION_STATUS,
    EVENT_SCHEMA_VERSION,
    READY_STATUS as LEARNING_EVENT_READY_STATUS,
    READY_WITH_QUARANTINE_STATUS as LEARNING_EVENT_READY_WITH_QUARANTINE_STATUS,
    SCHEMA_VERSION as LEARNING_EVENT_CONTRACT_SCHEMA_VERSION,
)


SCHEMA_VERSION = "cost_gate_learning_proposal_compiler_v1"
READY_STATUS = "LEARNING_PROPOSAL_COMPILER_READY_NO_AUTHORITY"
READY_WITH_QUARANTINE_STATUS = (
    "LEARNING_PROPOSAL_COMPILER_READY_WITH_QUARANTINE_NO_AUTHORITY"
)
INPUT_NOT_READY_STATUS = "LEARNING_EVENT_CONTRACT_INPUT_NOT_READY"
NO_REVIEWABLE_EVENTS_STATUS = "LEARNING_PROPOSAL_COMPILER_NO_REVIEWABLE_EVENTS"

BOUNDARY = (
    "artifact-only LearningEvent proposal compiler; review packet only; no PG "
    "query/write, Bybit call, order, config, risk, auth, runtime mutation, "
    "Cost Gate lowering, probe authority, order authority, live authority, or "
    "promotion proof"
)

AUTHORITY_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "bounded_demo_probe_authorized",
    "bybit_call_performed",
    "cap_envelope_mutation_allowed",
    "cost_gate_lowering_allowed",
    "demo_mutation_authority_granted",
    "global_cost_gate_lowering_recommended",
    "live_authority_granted",
    "mutation_enabled",
    "order_authority_granted",
    "order_submission_performed",
    "operator_authorization_object_emitted",
    "pg_write_performed",
    "probe_authority_granted",
    "promotion_evidence",
    "promotion_proof",
    "runtime_mutation_performed",
}
TRUTHY_AUTHORITY_STRINGS = {
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


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _round(value: Any, ndigits: int = 4) -> float | None:
    parsed = _float(value)
    return round(parsed, ndigits) if parsed is not None else None


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _truthy_authority(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in TRUTHY_AUTHORITY_STRINGS
    return False


def _parse_utc(value: Any) -> dt.datetime | None:
    text = _str(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _authority_violations(payload: Any) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    stack: list[tuple[str, Any]] = [("$", payload)]
    while stack:
        path, item = stack.pop()
        if isinstance(item, list):
            for index, value in enumerate(item):
                stack.append((f"{path}[{index}]", value))
            continue
        data = _dict(item)
        if not data:
            continue
        for key, value in data.items():
            item_path = f"{path}.{key}"
            if key == "main_cost_gate_adjustment" and value not in (None, "", "NONE"):
                violations.append(
                    {
                        "path": item_path,
                        "key": key,
                        "reason": "main_cost_gate_adjustment_not_none",
                    }
                )
            elif key in AUTHORITY_TRUE_KEYS and _truthy_authority(value):
                violations.append(
                    {
                        "path": item_path,
                        "key": key,
                        "reason": "authority_truthy_value",
                    }
                )
            if isinstance(value, (dict, list)):
                stack.append((item_path, value))
    return violations


def _event_timestamp(event: dict[str, Any]) -> dt.datetime | None:
    return _parse_utc(event.get("source_generated_at_utc")) or _parse_utc(
        event.get("generated_at_utc")
    )


def _event_sort_key(event: dict[str, Any]) -> tuple[str, str]:
    parsed = _event_timestamp(event)
    return (
        parsed.isoformat() if parsed else "",
        _str(event.get("event_id")),
    )


def _candidate_id(event: dict[str, Any]) -> str:
    candidate = _dict(event.get("candidate_identity"))
    return _str(event.get("candidate_id") or candidate.get("candidate_id"))


def _candidate_identity(events: list[dict[str, Any]]) -> dict[str, Any]:
    for event in events:
        candidate = _dict(event.get("candidate_identity"))
        if candidate:
            return {
                "candidate_id": _str(event.get("candidate_id") or candidate.get("candidate_id")),
                "side_cell_key": _str(candidate.get("side_cell_key")),
                "strategy_name": _str(candidate.get("strategy_name")),
                "symbol": _str(candidate.get("symbol")).upper(),
                "side": _str(candidate.get("side")),
                "outcome_horizon_minutes": candidate.get("outcome_horizon_minutes"),
            }
    return {}


def _source_hashes(events: list[dict[str, Any]]) -> list[str]:
    hashes: set[str] = set()
    for event in events:
        for source_ref in _list(event.get("source_refs")):
            row_hash = _str(_dict(source_ref).get("row_sha256"))
            if row_hash:
                hashes.add(row_hash)
    return sorted(hashes)


def _window_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    parsed = [value for value in (_event_timestamp(event) for event in events) if value]
    first = min(parsed).isoformat() if parsed else None
    last = max(parsed).isoformat() if parsed else None
    return {
        "event_count": len(events),
        "first_source_generated_at_utc": first,
        "last_source_generated_at_utc": last,
        "source_payload_sha256s": _source_hashes(events),
    }


def _counts(events: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for event in events:
        value = _str(event.get(key)) or "UNKNOWN"
        out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items()))


def _proposal_status(
    *,
    blocked_markout_proxy_count: int,
    fill_backed_proof_count: int,
    event_count: int,
) -> tuple[str, str, list[str]]:
    if fill_backed_proof_count > 0:
        return (
            "REVIEW_ONLY_FILL_BACKED_EVIDENCE_PRESENT_NOT_AUTHORITY",
            "fill_backed_events_require_separate_proof_and_promotion_review",
            ["run_proof_exclusion_and_execution_realism_before_any_promotion_review"],
        )
    if blocked_markout_proxy_count > 0:
        return (
            "REVIEW_ONLY_BLOCKED_MARKOUT_CONTEXT_NOT_PROOF",
            "blocked_markout_proxy_events_are_context_only_not_fill_backed_proof",
            [
                "compile_operator_review_packet_without_counting_blocked_markout_as_profit_proof",
                "collect_candidate_matched_fill_backed_outcomes_before_promotion",
            ],
        )
    if event_count > 0:
        return (
            "REVIEW_ONLY_INSUFFICIENT_OUTCOME_EVIDENCE",
            "events_present_but_no_outcome_or_fill_backed_proof_tier",
            ["continue_learning_event_accumulation_without_runtime_mutation"],
        )
    return (
        "NO_EVENTS",
        "no_events_for_candidate",
        ["refresh_learning_event_contract"],
    )


def _proposal_candidate(candidate_id: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    sorted_events = sorted(events, key=_event_sort_key)
    proof_tiers = _counts(sorted_events, "proof_tier")
    event_types = _counts(sorted_events, "event_type")
    blocked_markout_proxy_count = proof_tiers.get("blocked_markout_proxy", 0)
    fill_backed_proof_count = proof_tiers.get("fill_backed_probe_proof", 0)
    status, reason, next_actions = _proposal_status(
        blocked_markout_proxy_count=blocked_markout_proxy_count,
        fill_backed_proof_count=fill_backed_proof_count,
        event_count=len(sorted_events),
    )
    identity = _candidate_identity(sorted_events)
    seed = {
        "candidate_id": candidate_id,
        "event_packet_sha256s": [
            event.get("event_packet_sha256") for event in sorted_events
        ],
        "schema_version": SCHEMA_VERSION,
    }
    proposal_id = "learning_proposal:" + _sha256_text(_canonical_json(seed))[:24]
    return {
        "proposal_id": proposal_id,
        "proposal_status": status,
        "reason": reason,
        "proposal_scope": "review_only_not_mutation_authority",
        "candidate_id": candidate_id,
        "candidate_identity": identity,
        "evidence_window": _window_summary(sorted_events),
        "event_type_counts": event_types,
        "proof_tier_counts": proof_tiers,
        "proof_filters": {
            "blocked_markout_proxy_count": blocked_markout_proxy_count,
            "blocked_markout_proxy_counts_as_fill_backed_proof": False,
            "candidate_fill_backed_proof_event_count": fill_backed_proof_count,
            "fill_backed_proof_ready": False,
            "promotion_proof_ready": False,
        },
        "source_event_ids": [event.get("event_id") for event in sorted_events],
        "source_event_packet_sha256s": [
            event.get("event_packet_sha256") for event in sorted_events
        ],
        "review_only_proposed_actions": [
            {
                "action": "operator_review_learning_candidate",
                "allowed_by_this_packet": True,
                "mutation_allowed_by_this_packet": False,
            },
            {
                "action": "runtime_or_cost_gate_mutation",
                "allowed_by_this_packet": False,
                "mutation_allowed_by_this_packet": False,
            },
        ],
        "next_actions": next_actions,
    }


def _answer_flags(status: str) -> dict[str, Any]:
    ready = status in {READY_STATUS, READY_WITH_QUARANTINE_STATUS}
    return {
        "learning_proposal_compiler_ready": ready,
        "review_only_proposals_emitted": ready,
        "blocked_markout_proxy_counts_as_fill_backed_proof": False,
        "fill_backed_proof_ready": False,
        "promotion_proof_ready": False,
        "pg_backed_cutover_ready": False,
        "current_jsonl_ssot_preserved": True,
        "mutation_enabled": False,
        "demo_mutation_authority_granted": False,
        "cost_gate_lowering_allowed": False,
        "global_cost_gate_lowering_recommended": False,
        "main_cost_gate_adjustment": "NONE",
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "active_runtime_probe_authority": False,
        "active_runtime_order_authority": False,
        "live_authority_granted": False,
        "operator_authorization_object_emitted": False,
        "promotion_evidence": False,
        "promotion_proof": False,
        "runtime_mutation_required": False,
        "runtime_mutation_performed": False,
        "pg_query_performed": False,
        "pg_write_required": False,
        "pg_write_performed": False,
        "bybit_call_required": False,
        "bybit_call_performed": False,
        "order_submission_performed": False,
    }


def _valid_events(contract: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for item in _list(contract.get("events")):
        event = _dict(item)
        if (
            event.get("schema_version") == EVENT_SCHEMA_VERSION
            and _candidate_id(event)
            and _str(event.get("event_packet_sha256"))
        ):
            events.append(event)
    return events


def build_learning_proposal_compiler(
    *,
    learning_event_contract: dict[str, Any] | None,
    learning_event_contract_path: Path | None = None,
    learning_event_contract_error: str | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    """Build a review-only proposal compiler packet from LearningEvents."""
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    contract = _dict(learning_event_contract)
    contract_answers = _dict(contract.get("answers"))
    upstream_quarantine = _dict(contract.get("quarantine"))
    upstream_quarantine_count = _int(
        _dict(contract.get("summary")).get("quarantine_count")
        or upstream_quarantine.get("malformed_event_count")
    )
    upstream_authority_violations = _list(contract.get("authority_violations"))
    local_authority_violations = _authority_violations(contract)
    authority_violations = [*upstream_authority_violations, *local_authority_violations]
    contract_ready = (
        learning_event_contract_error is None
        and contract.get("schema_version") == LEARNING_EVENT_CONTRACT_SCHEMA_VERSION
        and contract.get("status")
        in {LEARNING_EVENT_READY_STATUS, LEARNING_EVENT_READY_WITH_QUARANTINE_STATUS}
        and contract_answers.get("pg_write_performed") is not True
        and contract_answers.get("bybit_call_performed") is not True
        and contract_answers.get("order_authority_granted") is not True
        and contract_answers.get("promotion_evidence") is not True
    )
    events = _valid_events(contract)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        grouped.setdefault(_candidate_id(event), []).append(event)
    proposals = [
        _proposal_candidate(candidate_id, grouped[candidate_id])
        for candidate_id in sorted(grouped)
    ]

    if contract.get("status") == AUTHORITY_BOUNDARY_VIOLATION_STATUS or authority_violations:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "learning_event_contract_authority_boundary_violation"
        proposals = []
    elif not contract_ready:
        status = INPUT_NOT_READY_STATUS
        reason = "learning_event_contract_missing_not_ready_or_schema_invalid"
        proposals = []
    elif not proposals:
        status = NO_REVIEWABLE_EVENTS_STATUS
        reason = "learning_event_contract_has_no_reviewable_events"
    elif upstream_quarantine_count > 0:
        status = READY_WITH_QUARANTINE_STATUS
        reason = "proposal_candidates_ready_with_upstream_quarantine"
    else:
        status = READY_STATUS
        reason = "proposal_candidates_ready_review_only"

    candidate_proof_event_count = sum(
        _dict(proposal.get("proof_filters")).get("candidate_fill_backed_proof_event_count", 0)
        for proposal in proposals
    )
    blocked_markout_proxy_count = sum(
        _dict(proposal.get("proof_filters")).get("blocked_markout_proxy_count", 0)
        for proposal in proposals
    )
    compiler_sha256 = _sha256_text(
        _canonical_json(
            {
                "schema_version": SCHEMA_VERSION,
                "proposal_ids": [proposal.get("proposal_id") for proposal in proposals],
                "contract_sha256": contract.get("contract_sha256"),
                "status": status,
            }
        )
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "compiler_sha256": compiler_sha256,
        "source_contract": {
            "path": str(learning_event_contract_path)
            if learning_event_contract_path
            else None,
            "schema_version": contract.get("schema_version"),
            "status": contract.get("status"),
            "contract_sha256": contract.get("contract_sha256"),
            "source_error": learning_event_contract_error,
        },
        "summary": {
            "candidate_group_count": len(proposals),
            "source_event_count": len(events) if status != AUTHORITY_BOUNDARY_VIOLATION_STATUS else 0,
            "proposal_candidate_count": len(proposals),
            "blocked_markout_proxy_event_count": blocked_markout_proxy_count,
            "candidate_fill_backed_proof_event_count": candidate_proof_event_count,
            "upstream_quarantine_count": upstream_quarantine_count,
            "authority_violation_count": len(authority_violations),
            "current_jsonl_ssot_preserved": True,
            "pg_backed_cutover_ready": False,
        },
        "proposal_candidates": proposals,
        "quarantine": {
            "upstream_quarantine_count": upstream_quarantine_count,
            "upstream_quarantine_review_required": upstream_quarantine_count > 0,
            "upstream_quarantine": upstream_quarantine,
        },
        "authority_violations": authority_violations,
        "answers": _answer_flags(status),
        "next_actions": (
            [
                "remove_authority_bearing_learning_event_contract_input",
                "operator_review_authority_boundary_violation_before_learning_proposal_compiler",
            ]
            if status == AUTHORITY_BOUNDARY_VIOLATION_STATUS
            else [
                "review_learning_proposal_candidates_without_runtime_mutation",
                "keep_blocked_markout_proxy_out_of_fill_backed_proof_counts",
                "do_not_start_pg_cutover_or_demo_mutation_from_proposal_compiler",
            ]
        ),
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    summary = _dict(packet.get("summary"))
    answers = _dict(packet.get("answers"))
    lines = [
        "# Cost Gate Learning Proposal Compiler",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Proposal candidates: `{summary.get('proposal_candidate_count')}`",
        f"- Blocked markout proxy events: `{summary.get('blocked_markout_proxy_event_count')}`",
        f"- Fill-backed proof events: `{summary.get('candidate_fill_backed_proof_event_count')}`",
        f"- Order authority granted: `{answers.get('order_authority_granted')}`",
        f"- Boundary: {packet.get('boundary')}",
        "",
        "## Proposal Candidates",
        "",
        "| proposal_id | candidate | status | blocked_markout | fill_backed_proof |",
        "|---|---|---|---:|---:|",
    ]
    for proposal in _list(packet.get("proposal_candidates")):
        filters = _dict(_dict(proposal).get("proof_filters"))
        lines.append(
            f"| `{proposal.get('proposal_id')}` | `{proposal.get('candidate_id')}` | "
            f"`{proposal.get('proposal_status')}` | "
            f"`{filters.get('blocked_markout_proxy_count')}` | "
            f"`{filters.get('candidate_fill_backed_proof_event_count')}` |"
        )
    lines.extend(["", "## No-Authority Answers", ""])
    for key, value in answers.items():
        lines.append(f"- `{key}`: `{value}`")
    return "\n".join(lines) + "\n"


def _read_json(path: Path | None) -> tuple[dict[str, Any] | None, str | None]:
    if path is None:
        return None, "missing_path"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "missing"
    except (OSError, json.JSONDecodeError, ValueError) as exc:
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
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--learning-event-contract-json", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    contract, err = _read_json(args.learning_event_contract_json)
    packet = build_learning_proposal_compiler(
        learning_event_contract=contract,
        learning_event_contract_path=args.learning_event_contract_json,
        learning_event_contract_error=err,
    )
    markdown = render_markdown(packet)
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.output:
        _write_text(args.output, markdown)
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True, default=str))
    elif not args.output and not args.json_output:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
