#!/usr/bin/env python3
"""Build an inert Demo mutation envelope from learning adjudication decisions.

This helper is the review layer between learning adjudication and any future
bounded Demo/runtime mutation gate. It can describe candidate-scoped mutation
review intent, but it never applies a mutation, enables writers/adapters,
submits orders, lowers Cost Gate, or grants promotion proof.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from cost_gate_learning_lane.bounded_demo_runtime_readiness import (
    READY_STATUS as RUNTIME_READY_STATUS,
    SCHEMA_VERSION as RUNTIME_READINESS_SCHEMA_VERSION,
)
from cost_gate_learning_lane.learning_adjudicator import (
    READY_STATUS as ADJUDICATOR_READY_STATUS,
    READY_WITH_QUARANTINE_STATUS as ADJUDICATOR_READY_WITH_QUARANTINE_STATUS,
    SCHEMA_VERSION as ADJUDICATOR_SCHEMA_VERSION,
)
from cost_gate_learning_lane.learning_event_contract import (
    AUTHORITY_BOUNDARY_VIOLATION_STATUS,
)


SCHEMA_VERSION = "cost_gate_learning_demo_mutation_envelope_v1"
READY_STATUS = "LEARNING_DEMO_MUTATION_ENVELOPE_READY_FOR_OPERATOR_GATE_NO_AUTHORITY"
READY_WITH_QUARANTINE_STATUS = (
    "LEARNING_DEMO_MUTATION_ENVELOPE_READY_WITH_QUARANTINE_NO_AUTHORITY"
)
BLOCKED_BY_RUNTIME_READINESS_STATUS = (
    "LEARNING_DEMO_MUTATION_ENVELOPE_BLOCKED_BY_RUNTIME_READINESS_NO_AUTHORITY"
)
INPUT_NOT_READY_STATUS = "LEARNING_ADJUDICATOR_INPUT_NOT_READY"
NO_ENVELOPES_STATUS = "LEARNING_DEMO_MUTATION_ENVELOPE_NO_DECISIONS"

BOUNDARY = (
    "artifact-only inert Demo mutation envelope; operator/runtime gates required; "
    "no PG query/write, Bybit call, order, config, risk, auth, runtime/env/service/"
    "cron mutation, writer/adapter enablement, Cost Gate lowering, probe authority, "
    "order authority, live authority, or promotion proof"
)

AUTHORITY_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "adapter_enabled_by_this_packet",
    "bounded_demo_probe_authorized",
    "bybit_call_performed",
    "bybit_private_call_performed",
    "cap_envelope_mutation_allowed",
    "cost_gate_change_allowed",
    "cost_gate_lowering_allowed",
    "demo_mutation_allowed",
    "demo_mutation_authority_granted",
    "env_mutation_performed",
    "global_cost_gate_lowering_recommended",
    "live_authority_granted",
    "mutation_allowed",
    "mutation_enabled",
    "operator_authorization_object_emitted",
    "order_authority_granted",
    "order_capable_action_allowed_by_this_packet",
    "order_submission_allowed",
    "order_submission_performed",
    "pg_write_performed",
    "probe_authority_granted",
    "promotion_allowed",
    "promotion_evidence",
    "promotion_proof",
    "promotion_proof_ready",
    "runtime_mutation_allowed",
    "runtime_mutation_performed",
    "service_restart_performed",
    "writer_enabled_by_this_packet",
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


def _runtime_readiness_gate(
    readiness: dict[str, Any],
    *,
    source_error: str | None,
) -> dict[str, Any]:
    blocking_reasons = [
        _str(reason)
        for reason in _list(readiness.get("blocking_reasons"))
        if _str(reason)
    ]
    check_statuses: dict[str, Any] = {}
    for name, check in _dict(readiness.get("checks")).items():
        check_statuses[name] = {
            "status": _dict(check).get("status"),
            "ready": _dict(check).get("ready"),
            "blocking_reasons": _list(_dict(check).get("blocking_reasons")),
        }
    if source_error:
        blocking_reasons.append(f"bounded_demo_runtime_readiness:{source_error}")
    if readiness.get("schema_version") != RUNTIME_READINESS_SCHEMA_VERSION:
        blocking_reasons.append("bounded_demo_runtime_readiness_schema_invalid")

    ready = (
        source_error is None
        and readiness.get("schema_version") == RUNTIME_READINESS_SCHEMA_VERSION
        and readiness.get("status") == RUNTIME_READY_STATUS
    )
    credential_mode_blockers = [
        reason
        for reason in blocking_reasons
        if reason.startswith("demo_api_slot:") or reason.startswith("connector_mode:")
    ]
    return {
        "schema_version": readiness.get("schema_version"),
        "status": readiness.get("status"),
        "source_error": source_error,
        "ready_for_final_window_gates": ready,
        "candidate": readiness.get("candidate") or {},
        "blocking_reasons": blocking_reasons,
        "credential_mode_blockers": credential_mode_blockers,
        "check_statuses": check_statuses,
        "secret_values_omitted": True,
        "required_before_any_demo_mutation": True,
    }


def _envelope_label(decision: dict[str, Any]) -> tuple[str, str]:
    label = _str(decision.get("decision_label"))
    if label == "REVIEW":
        return (
            "OPERATOR_REVIEW_REQUIRED_NO_AUTHORITY",
            "fill_backed_evidence_present_but_requires_operator_runtime_and_proof_gates",
        )
    if label == "DEFER":
        return (
            "DEFER_CONTEXT_ONLY_NO_DEMO_MUTATION",
            "adjudicator_deferred_candidate_context_is_not_mutation_authority",
        )
    return (
        "REJECT_NO_DEMO_MUTATION",
        "adjudicator_rejected_or_did_not_mark_candidate_reviewable",
    )


def _required_gates(runtime_gate: dict[str, Any]) -> list[str]:
    gates = [
        "explicit_operator_demo_mutation_review",
        "bounded_demo_runtime_readiness_green",
        "credential_and_connector_mode_readiness_green",
        "fresh_standing_demo_authorization_scope",
        "final_window_bbo_decision_lease_guardian_rust_authority",
        "proof_exclusion_and_execution_realism_review",
        "separate_runtime_mutation_apply_checkpoint",
    ]
    if _list(runtime_gate.get("credential_mode_blockers")):
        gates.insert(1, "resolve_preserved_demo_credential_and_connector_mode_blockers")
    return gates


def _mutation_envelope(
    decision: dict[str, Any],
    *,
    runtime_gate: dict[str, Any],
    upstream_quarantine_count: int,
) -> dict[str, Any]:
    label, reason = _envelope_label(decision)
    proof_gates = _dict(decision.get("proof_eligibility_gates"))
    blocked_markout_count = _int(proof_gates.get("blocked_markout_proxy_count"))
    fill_backed_count = _int(
        proof_gates.get("candidate_fill_backed_proof_event_count")
    )
    blockers: list[str] = []
    if decision.get("decision_label") != "REVIEW":
        blockers.append("adjudication_label_not_review")
    if blocked_markout_count > 0 and fill_backed_count == 0:
        blockers.append("blocked_markout_proxy_context_only_not_fill_backed_proof")
    if not runtime_gate.get("ready_for_final_window_gates"):
        blockers.extend(_list(runtime_gate.get("blocking_reasons")))
    if upstream_quarantine_count > 0:
        blockers.append("upstream_quarantine_review_required")

    seed = {
        "schema_version": SCHEMA_VERSION,
        "decision_id": decision.get("decision_id"),
        "candidate_id": decision.get("candidate_id"),
        "envelope_label": label,
    }
    envelope_id = "learning_demo_mutation_envelope:" + _sha256_text(
        _canonical_json(seed)
    )[:24]
    return {
        "envelope_id": envelope_id,
        "envelope_label": label,
        "reason": reason,
        "decision_id": decision.get("decision_id"),
        "decision_label": decision.get("decision_label"),
        "adjudication": decision.get("adjudication"),
        "candidate_id": decision.get("candidate_id"),
        "candidate_identity": decision.get("candidate_identity") or {},
        "source_event_ids": decision.get("source_event_ids") or [],
        "source_event_packet_sha256s": decision.get("source_event_packet_sha256s")
        or [],
        "proof_gates": {
            "blocked_markout_proxy_count": blocked_markout_count,
            "blocked_markout_proxy_counts_as_fill_backed_proof": False,
            "candidate_fill_backed_proof_event_count": fill_backed_count,
            "fill_backed_proof_ready": False,
            "promotion_proof_ready": False,
            "quarantine_clear": upstream_quarantine_count == 0,
        },
        "runtime_readiness_gate": runtime_gate,
        "operator_gate": {
            "required": True,
            "satisfied_by_this_packet": False,
            "mutation_authority_granted": False,
        },
        "required_gates_before_any_demo_mutation": _required_gates(runtime_gate),
        "blocking_reasons": blockers,
        "allowed_actions": {
            "operator_review_packet_allowed": True,
            "demo_mutation_allowed_by_this_packet": False,
            "runtime_mutation_allowed_by_this_packet": False,
            "order_submission_allowed_by_this_packet": False,
            "cost_gate_change_allowed_by_this_packet": False,
            "promotion_allowed_by_this_packet": False,
        },
    }


def _answer_flags(status: str, runtime_gate: dict[str, Any], envelope_count: int) -> dict[str, Any]:
    ready = status in {READY_STATUS, READY_WITH_QUARANTINE_STATUS}
    credential_mode_blockers = _list(runtime_gate.get("credential_mode_blockers"))
    return {
        "learning_demo_mutation_envelope_ready": ready,
        "demo_mutation_envelope_emitted": envelope_count > 0,
        "runtime_readiness_artifact_required": True,
        "runtime_readiness_blockers_preserved": bool(
            _list(runtime_gate.get("blocking_reasons"))
        ),
        "credential_mode_blockers_preserved": bool(credential_mode_blockers),
        "bounded_demo_final_window_prerequisites_ready": bool(
            runtime_gate.get("ready_for_final_window_gates")
        ),
        "operator_gate_required": True,
        "operator_gate_satisfied_by_this_packet": False,
        "mutation_enabled": False,
        "demo_mutation_allowed": False,
        "demo_mutation_authority_granted": False,
        "runtime_mutation_allowed": False,
        "runtime_mutation_performed": False,
        "env_mutation_performed": False,
        "service_restart_performed": False,
        "writer_enabled_by_this_packet": False,
        "adapter_enabled_by_this_packet": False,
        "cost_gate_change_allowed": False,
        "cost_gate_lowering_allowed": False,
        "global_cost_gate_lowering_recommended": False,
        "main_cost_gate_adjustment": "NONE",
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "active_runtime_probe_authority": False,
        "active_runtime_order_authority": False,
        "live_authority_granted": False,
        "promotion_evidence": False,
        "promotion_proof": False,
        "promotion_proof_ready": False,
        "pg_query_performed": False,
        "pg_write_required": False,
        "pg_write_performed": False,
        "bybit_call_required": False,
        "bybit_call_performed": False,
        "order_submission_allowed": False,
        "order_submission_performed": False,
    }


def build_learning_demo_mutation_envelope(
    *,
    learning_adjudicator: dict[str, Any] | None,
    learning_adjudicator_path: Path | None = None,
    learning_adjudicator_error: str | None = None,
    bounded_demo_runtime_readiness: dict[str, Any] | None = None,
    bounded_demo_runtime_readiness_path: Path | None = None,
    bounded_demo_runtime_readiness_error: str | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    """Build inert mutation review envelopes from adjudication decisions."""
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    adjudicator = _dict(learning_adjudicator)
    runtime_readiness = _dict(bounded_demo_runtime_readiness)
    adjudicator_answers = _dict(adjudicator.get("answers"))
    adjudicator_summary = _dict(adjudicator.get("summary"))
    quarantine = _dict(adjudicator.get("quarantine"))
    upstream_quarantine_count = _int(
        adjudicator_summary.get("upstream_quarantine_count")
        or quarantine.get("upstream_quarantine_count")
    )
    runtime_error = (
        bounded_demo_runtime_readiness_error
        or ("missing" if not runtime_readiness else None)
    )
    runtime_gate = _runtime_readiness_gate(
        runtime_readiness,
        source_error=runtime_error,
    )
    upstream_authority_violations = [
        *_list(adjudicator.get("authority_violations")),
        *_list(runtime_readiness.get("authority_violations")),
    ]
    local_authority_violations = [
        *_authority_violations(adjudicator),
        *_authority_violations(runtime_readiness),
    ]
    authority_violations = [
        *upstream_authority_violations,
        *local_authority_violations,
    ]
    adjudicator_ready = (
        learning_adjudicator_error is None
        and adjudicator.get("schema_version") == ADJUDICATOR_SCHEMA_VERSION
        and adjudicator.get("status")
        in {ADJUDICATOR_READY_STATUS, ADJUDICATOR_READY_WITH_QUARANTINE_STATUS}
        and adjudicator_answers.get("pg_write_performed") is not True
        and adjudicator_answers.get("bybit_call_performed") is not True
        and adjudicator_answers.get("order_authority_granted") is not True
        and adjudicator_answers.get("promotion_evidence") is not True
        and adjudicator_answers.get("demo_mutation_authority_granted") is not True
    )
    decisions = [
        _dict(item)
        for item in _list(adjudicator.get("decisions"))
        if _dict(item).get("decision_id") and _dict(item).get("candidate_id")
    ]
    envelopes = [
        _mutation_envelope(
            decision,
            runtime_gate=runtime_gate,
            upstream_quarantine_count=upstream_quarantine_count,
        )
        for decision in decisions
    ]

    if (
        adjudicator.get("status") == AUTHORITY_BOUNDARY_VIOLATION_STATUS
        or authority_violations
    ):
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "learning_adjudicator_or_runtime_readiness_authority_boundary_violation"
        envelopes = []
    elif not adjudicator_ready:
        status = INPUT_NOT_READY_STATUS
        reason = "learning_adjudicator_missing_not_ready_or_schema_invalid"
        envelopes = []
    elif not envelopes:
        status = NO_ENVELOPES_STATUS
        reason = "learning_adjudicator_has_no_decisions"
    elif not runtime_gate.get("ready_for_final_window_gates"):
        status = BLOCKED_BY_RUNTIME_READINESS_STATUS
        reason = "bounded_demo_runtime_readiness_gate_not_green"
    elif upstream_quarantine_count > 0:
        status = READY_WITH_QUARANTINE_STATUS
        reason = "demo_mutation_envelope_ready_with_upstream_quarantine"
    else:
        status = READY_STATUS
        reason = "demo_mutation_envelope_ready_for_operator_gate_review_only"

    label_counts: dict[str, int] = {}
    for envelope in envelopes:
        label = _str(envelope.get("envelope_label")) or "UNKNOWN"
        label_counts[label] = label_counts.get(label, 0) + 1
    envelope_sha256 = _sha256_text(
        _canonical_json(
            {
                "schema_version": SCHEMA_VERSION,
                "status": status,
                "envelope_ids": [envelope.get("envelope_id") for envelope in envelopes],
                "adjudicator_sha256": adjudicator.get("adjudicator_sha256"),
                "runtime_readiness_status": runtime_gate.get("status"),
            }
        )
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "envelope_sha256": envelope_sha256,
        "source_adjudicator": {
            "path": str(learning_adjudicator_path) if learning_adjudicator_path else None,
            "schema_version": adjudicator.get("schema_version"),
            "status": adjudicator.get("status"),
            "adjudicator_sha256": adjudicator.get("adjudicator_sha256"),
            "source_error": learning_adjudicator_error,
        },
        "source_runtime_readiness": {
            "path": str(bounded_demo_runtime_readiness_path)
            if bounded_demo_runtime_readiness_path
            else None,
            "schema_version": runtime_gate.get("schema_version"),
            "status": runtime_gate.get("status"),
            "source_error": runtime_gate.get("source_error"),
        },
        "summary": {
            "envelope_count": len(envelopes),
            "operator_review_required_count": label_counts.get(
                "OPERATOR_REVIEW_REQUIRED_NO_AUTHORITY", 0
            ),
            "defer_context_only_count": label_counts.get(
                "DEFER_CONTEXT_ONLY_NO_DEMO_MUTATION", 0
            ),
            "reject_no_mutation_count": label_counts.get(
                "REJECT_NO_DEMO_MUTATION", 0
            ),
            "runtime_readiness_ready": bool(
                runtime_gate.get("ready_for_final_window_gates")
            ),
            "runtime_readiness_blocker_count": len(
                _list(runtime_gate.get("blocking_reasons"))
            ),
            "credential_mode_blocker_count": len(
                _list(runtime_gate.get("credential_mode_blockers"))
            ),
            "upstream_quarantine_count": upstream_quarantine_count,
            "authority_violation_count": len(authority_violations),
            "current_jsonl_ssot_preserved": True,
            "pg_backed_cutover_ready": False,
        },
        "runtime_readiness_gate": runtime_gate,
        "mutation_envelopes": envelopes,
        "quarantine": {
            "upstream_quarantine_count": upstream_quarantine_count,
            "upstream_quarantine_review_required": upstream_quarantine_count > 0,
            "upstream_quarantine": quarantine,
        },
        "authority_violations": authority_violations,
        "answers": _answer_flags(status, runtime_gate, len(envelopes)),
        "next_actions": (
            [
                "remove_authority_bearing_learning_or_runtime_readiness_input",
                "operator_review_authority_boundary_violation_before_demo_mutation_envelope",
            ]
            if status == AUTHORITY_BOUNDARY_VIOLATION_STATUS
            else [
                "review_inert_demo_mutation_envelopes_without_runtime_mutation",
                "resolve_demo_credential_mode_blockers_before_any_runtime_gate"
                if _list(runtime_gate.get("credential_mode_blockers"))
                else "keep_runtime_readiness_gate_green_before_operator_mutation_review",
                "require_separate_operator_and_runtime_apply_checkpoint_before_any_demo_mutation",
            ]
        ),
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    summary = _dict(packet.get("summary"))
    answers = _dict(packet.get("answers"))
    lines = [
        "# Cost Gate Learning Demo Mutation Envelope",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Envelopes: `{summary.get('envelope_count')}`",
        f"- Runtime readiness ready: `{summary.get('runtime_readiness_ready')}`",
        f"- Credential/mode blockers: `{summary.get('credential_mode_blocker_count')}`",
        f"- Demo mutation allowed: `{answers.get('demo_mutation_allowed')}`",
        f"- Boundary: {packet.get('boundary')}",
        "",
        "## Mutation Envelopes",
        "",
        "| envelope_id | label | candidate | blockers |",
        "|---|---|---|---:|",
    ]
    for envelope in _list(packet.get("mutation_envelopes")):
        lines.append(
            f"| `{envelope.get('envelope_id')}` | `{envelope.get('envelope_label')}` | "
            f"`{envelope.get('candidate_id')}` | "
            f"`{len(_list(envelope.get('blocking_reasons')))}` |"
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
    parser.add_argument("--learning-adjudicator-json", type=Path, required=True)
    parser.add_argument("--bounded-demo-runtime-readiness-json", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    adjudicator, adjudicator_err = _read_json(args.learning_adjudicator_json)
    readiness, readiness_err = _read_json(args.bounded_demo_runtime_readiness_json)
    packet = build_learning_demo_mutation_envelope(
        learning_adjudicator=adjudicator,
        learning_adjudicator_path=args.learning_adjudicator_json,
        learning_adjudicator_error=adjudicator_err,
        bounded_demo_runtime_readiness=readiness,
        bounded_demo_runtime_readiness_path=args.bounded_demo_runtime_readiness_json,
        bounded_demo_runtime_readiness_error=readiness_err,
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
