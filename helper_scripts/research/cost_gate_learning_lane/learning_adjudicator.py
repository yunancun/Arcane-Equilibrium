#!/usr/bin/env python3
"""Adjudicate learning proposal candidates without granting authority.

The adjudicator turns review-only proposal candidates into deterministic
decisions. It records whether candidates should be reviewed, deferred, or
rejected, but it never grants runtime mutation, order authority, Cost Gate
changes, or promotion proof.
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
)
from cost_gate_learning_lane.learning_proposal_compiler import (
    READY_STATUS as COMPILER_READY_STATUS,
    READY_WITH_QUARANTINE_STATUS as COMPILER_READY_WITH_QUARANTINE_STATUS,
    SCHEMA_VERSION as COMPILER_SCHEMA_VERSION,
)


SCHEMA_VERSION = "cost_gate_learning_adjudicator_v1"
READY_STATUS = "LEARNING_ADJUDICATOR_READY_NO_AUTHORITY"
READY_WITH_QUARANTINE_STATUS = "LEARNING_ADJUDICATOR_READY_WITH_QUARANTINE_NO_AUTHORITY"
INPUT_NOT_READY_STATUS = "LEARNING_PROPOSAL_COMPILER_INPUT_NOT_READY"
NO_DECISIONS_STATUS = "LEARNING_ADJUDICATOR_NO_REVIEWABLE_DECISIONS"

BOUNDARY = (
    "artifact-only learning adjudicator; review/defer/reject decisions only; "
    "no PG query/write, Bybit call, order, config, risk, auth, runtime "
    "mutation, Cost Gate lowering, probe authority, order authority, live "
    "authority, or promotion proof"
)

AUTHORITY_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "bounded_demo_probe_authorized",
    "bybit_call_performed",
    "cap_envelope_mutation_allowed",
    "cost_gate_lowering_allowed",
    "demo_mutation_authority_granted",
    "fill_backed_proof_ready",
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
    "promotion_proof_ready",
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


def _truthy_authority(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in TRUTHY_AUTHORITY_STRINGS
    return False


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


def _proposal_sort_key(proposal: dict[str, Any]) -> tuple[int, int, int, str]:
    filters = _dict(proposal.get("proof_filters"))
    fill_backed = _int(filters.get("candidate_fill_backed_proof_event_count"))
    blocked_markout = _int(filters.get("blocked_markout_proxy_count"))
    events = _int(_dict(proposal.get("evidence_window")).get("event_count"))
    return (-fill_backed, -blocked_markout, -events, _str(proposal.get("candidate_id")))


def _decision_label(filters: dict[str, Any]) -> tuple[str, str, str, list[str]]:
    fill_backed = _int(filters.get("candidate_fill_backed_proof_event_count"))
    blocked_markout = _int(filters.get("blocked_markout_proxy_count"))
    if fill_backed > 0:
        return (
            "REVIEW",
            "REVIEW_REQUIRED_FILL_BACKED_EVIDENCE_GATED_NO_AUTHORITY",
            "fill_backed_events_present_but_require_proof_exclusion_execution_realism_and_operator_review",
            [
                "run_proof_exclusion_and_execution_realism_review",
                "operator_review_fill_backed_candidate_before_any_demo_mutation",
            ],
        )
    if blocked_markout > 0:
        return (
            "DEFER",
            "DEFER_BLOCKED_MARKOUT_CONTEXT_ONLY_NOT_PROOF",
            "blocked_markout_proxy_is_context_only_and_cannot_support_mutation_or_promotion",
            [
                "collect_candidate_matched_fill_backed_outcomes_before_promotion",
                "keep_blocked_markout_proxy_out_of_proof_counts",
            ],
        )
    return (
        "REJECT",
        "REJECT_INSUFFICIENT_LEARNING_EVIDENCE_NO_AUTHORITY",
        "proposal_has_no_reviewable_outcome_or_fill_backed_proof_tier",
        ["continue_learning_event_accumulation_without_runtime_mutation"],
    )


def _adjudication_decision(
    proposal: dict[str, Any],
    *,
    rank: int,
    upstream_quarantine_count: int,
) -> dict[str, Any]:
    filters = _dict(proposal.get("proof_filters"))
    label, adjudication, reason, next_actions = _decision_label(filters)
    candidate_id = _str(proposal.get("candidate_id"))
    decision_seed = {
        "schema_version": SCHEMA_VERSION,
        "proposal_id": proposal.get("proposal_id"),
        "candidate_id": candidate_id,
        "rank": rank,
        "label": label,
        "adjudication": adjudication,
    }
    decision_id = "learning_adjudication:" + _sha256_text(
        _canonical_json(decision_seed)
    )[:24]
    return {
        "decision_id": decision_id,
        "rank": rank,
        "decision_label": label,
        "adjudication": adjudication,
        "reason": reason,
        "proposal_id": proposal.get("proposal_id"),
        "candidate_id": candidate_id,
        "candidate_identity": proposal.get("candidate_identity") or {},
        "evidence_window": proposal.get("evidence_window") or {},
        "proof_eligibility_gates": {
            "blocked_markout_proxy_count": _int(
                filters.get("blocked_markout_proxy_count")
            ),
            "blocked_markout_proxy_counts_as_fill_backed_proof": False,
            "candidate_fill_backed_proof_event_count": _int(
                filters.get("candidate_fill_backed_proof_event_count")
            ),
            "fill_backed_proof_ready": False,
            "promotion_proof_ready": False,
            "upstream_quarantine_count": upstream_quarantine_count,
            "quarantine_clear": upstream_quarantine_count == 0,
            "authority_boundary_preserved": True,
        },
        "source_proposal_status": proposal.get("proposal_status"),
        "source_event_ids": proposal.get("source_event_ids") or [],
        "source_event_packet_sha256s": proposal.get("source_event_packet_sha256s")
        or [],
        "allowed_actions": {
            "review_packet_allowed": True,
            "demo_mutation_allowed": False,
            "runtime_mutation_allowed": False,
            "order_submission_allowed": False,
            "cost_gate_change_allowed": False,
            "promotion_allowed": False,
        },
        "next_actions": next_actions,
    }


def _answer_flags(status: str) -> dict[str, Any]:
    ready = status in {READY_STATUS, READY_WITH_QUARANTINE_STATUS}
    return {
        "learning_adjudicator_ready": ready,
        "review_defer_reject_decisions_emitted": ready,
        "demo_mutation_allowed": False,
        "runtime_mutation_allowed": False,
        "order_submission_allowed": False,
        "cost_gate_change_allowed": False,
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


def build_learning_adjudicator(
    *,
    learning_proposal_compiler: dict[str, Any] | None,
    learning_proposal_compiler_path: Path | None = None,
    learning_proposal_compiler_error: str | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    """Build no-authority adjudication decisions from proposal candidates."""
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    compiler = _dict(learning_proposal_compiler)
    compiler_answers = _dict(compiler.get("answers"))
    compiler_summary = _dict(compiler.get("summary"))
    quarantine = _dict(compiler.get("quarantine"))
    upstream_quarantine_count = _int(
        compiler_summary.get("upstream_quarantine_count")
        or quarantine.get("upstream_quarantine_count")
    )
    upstream_authority_violations = _list(compiler.get("authority_violations"))
    local_authority_violations = _authority_violations(compiler)
    authority_violations = [*upstream_authority_violations, *local_authority_violations]
    compiler_ready = (
        learning_proposal_compiler_error is None
        and compiler.get("schema_version") == COMPILER_SCHEMA_VERSION
        and compiler.get("status")
        in {COMPILER_READY_STATUS, COMPILER_READY_WITH_QUARANTINE_STATUS}
        and compiler_answers.get("pg_write_performed") is not True
        and compiler_answers.get("bybit_call_performed") is not True
        and compiler_answers.get("order_authority_granted") is not True
        and compiler_answers.get("promotion_evidence") is not True
    )
    proposals = [
        _dict(item)
        for item in _list(compiler.get("proposal_candidates"))
        if _dict(item).get("proposal_id") and _dict(item).get("candidate_id")
    ]
    ranked = sorted(proposals, key=_proposal_sort_key)
    decisions = [
        _adjudication_decision(
            proposal,
            rank=index,
            upstream_quarantine_count=upstream_quarantine_count,
        )
        for index, proposal in enumerate(ranked, start=1)
    ]

    if compiler.get("status") == AUTHORITY_BOUNDARY_VIOLATION_STATUS or authority_violations:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "learning_proposal_compiler_authority_boundary_violation"
        decisions = []
    elif not compiler_ready:
        status = INPUT_NOT_READY_STATUS
        reason = "learning_proposal_compiler_missing_not_ready_or_schema_invalid"
        decisions = []
    elif not decisions:
        status = NO_DECISIONS_STATUS
        reason = "learning_proposal_compiler_has_no_reviewable_proposals"
    elif upstream_quarantine_count > 0:
        status = READY_WITH_QUARANTINE_STATUS
        reason = "adjudication_ready_with_upstream_quarantine"
    else:
        status = READY_STATUS
        reason = "adjudication_decisions_ready_review_only"

    label_counts: dict[str, int] = {}
    for decision in decisions:
        label = _str(decision.get("decision_label")) or "UNKNOWN"
        label_counts[label] = label_counts.get(label, 0) + 1
    adjudicator_sha256 = _sha256_text(
        _canonical_json(
            {
                "schema_version": SCHEMA_VERSION,
                "status": status,
                "decision_ids": [decision.get("decision_id") for decision in decisions],
                "compiler_sha256": compiler.get("compiler_sha256"),
            }
        )
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "adjudicator_sha256": adjudicator_sha256,
        "source_compiler": {
            "path": str(learning_proposal_compiler_path)
            if learning_proposal_compiler_path
            else None,
            "schema_version": compiler.get("schema_version"),
            "status": compiler.get("status"),
            "compiler_sha256": compiler.get("compiler_sha256"),
            "source_error": learning_proposal_compiler_error,
        },
        "summary": {
            "decision_count": len(decisions),
            "review_count": label_counts.get("REVIEW", 0),
            "defer_count": label_counts.get("DEFER", 0),
            "reject_count": label_counts.get("REJECT", 0),
            "upstream_quarantine_count": upstream_quarantine_count,
            "authority_violation_count": len(authority_violations),
            "current_jsonl_ssot_preserved": True,
            "pg_backed_cutover_ready": False,
        },
        "decisions": decisions,
        "quarantine": {
            "upstream_quarantine_count": upstream_quarantine_count,
            "upstream_quarantine_review_required": upstream_quarantine_count > 0,
            "upstream_quarantine": quarantine,
        },
        "authority_violations": authority_violations,
        "answers": _answer_flags(status),
        "next_actions": (
            [
                "remove_authority_bearing_learning_proposal_compiler_input",
                "operator_review_authority_boundary_violation_before_learning_adjudication",
            ]
            if status == AUTHORITY_BOUNDARY_VIOLATION_STATUS
            else [
                "review_learning_adjudication_decisions_without_runtime_mutation",
                "keep_blocked_markout_proxy_out_of_fill_backed_proof_counts",
                "do_not_start_demo_mutation_or_cost_gate_change_from_adjudicator",
            ]
        ),
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    summary = _dict(packet.get("summary"))
    answers = _dict(packet.get("answers"))
    lines = [
        "# Cost Gate Learning Adjudicator",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Decisions: `{summary.get('decision_count')}`",
        f"- Review/defer/reject: `{summary.get('review_count')}` / `{summary.get('defer_count')}` / `{summary.get('reject_count')}`",
        f"- Order authority granted: `{answers.get('order_authority_granted')}`",
        f"- Boundary: {packet.get('boundary')}",
        "",
        "## Decisions",
        "",
        "| rank | label | candidate | adjudication |",
        "|---:|---|---|---|",
    ]
    for decision in _list(packet.get("decisions")):
        lines.append(
            f"| `{decision.get('rank')}` | `{decision.get('decision_label')}` | "
            f"`{decision.get('candidate_id')}` | `{decision.get('adjudication')}` |"
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
    parser.add_argument("--learning-proposal-compiler-json", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    compiler, err = _read_json(args.learning_proposal_compiler_json)
    packet = build_learning_adjudicator(
        learning_proposal_compiler=compiler,
        learning_proposal_compiler_path=args.learning_proposal_compiler_json,
        learning_proposal_compiler_error=err,
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
