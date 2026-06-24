#!/usr/bin/env python3
"""Decide the current durable SSOT for Cost Gate demo-learning evidence.

The decision is artifact-only: it reads existing activation/result-review
artifacts and emits a machine-readable packet. It does not query PG, call
Bybit, write runtime state, grant authority, lower the Cost Gate, or create
promotion proof.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
from typing import Any


LEARNING_SSOT_DECISION_SCHEMA_VERSION = "cost_gate_learning_ssot_decision_v1"
BOUNDARY = (
    "artifact-only learning SSOT decision; no PG query/write, Bybit call, "
    "order, config, risk, auth, runtime mutation, Cost Gate lowering, "
    "probe authority, order authority, or promotion proof"
)
AUTHORITY_BEARING_TRUE_KEYS = {
    "global_cost_gate_lowering_recommended",
    "probe_authority_granted",
    "order_authority_granted",
    "active_runtime_probe_authority",
    "active_runtime_order_authority",
    "operator_authorization_object_emitted",
    "promotion_evidence",
    "promotion_proof",
    "runtime_mutation_performed",
    "pg_write_performed",
    "bybit_call_performed",
    "order_submission_performed",
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
        parsed = int(float(value))
    except (TypeError, ValueError):
        return default
    return parsed


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _round(value: Any, ndigits: int = 4) -> float | None:
    parsed = _float(value)
    return round(parsed, ndigits) if parsed is not None else None


def _parse_utc(value: Any) -> dt.datetime | None:
    raw = _str(value)
    if not raw:
        return None
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _source_summary(
    payload: dict[str, Any] | None,
    path: Path | None,
    *,
    now_utc: dt.datetime,
) -> dict[str, Any]:
    data = _dict(payload)
    generated_at = data.get("generated_at_utc")
    parsed_generated_at = _parse_utc(generated_at)
    age_seconds = (
        max(0.0, (now_utc - parsed_generated_at).total_seconds())
        if parsed_generated_at is not None
        else None
    )
    return {
        "present": bool(data),
        "path": str(path) if path else None,
        "freshness_status": (
            "MISSING"
            if not data
            else "UNKNOWN_NO_MAX_AGE"
            if parsed_generated_at is not None
            else "UNPARSEABLE_GENERATED_AT"
        ),
        "schema_version": data.get("schema_version"),
        "status": data.get("status"),
        "generated_at_utc": generated_at,
        "age_seconds": _round(age_seconds, 3),
        "max_age_seconds": None,
        "source_error": data.get("source_error") or data.get("ledger_source_error"),
    }


def _result_review_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    data = _dict(payload)
    summary = _dict(data.get("probe_result_summary"))
    quality = _dict(data.get("evidence_quality"))
    answers = _dict(data.get("answers"))
    return {
        "status": data.get("status"),
        "reason": data.get("reason"),
        "completed_probe_outcome_count": _int(summary.get("completed_probe_outcome_count")),
        "proof_eligible_probe_outcome_count": _int(
            summary.get("proof_eligible_probe_outcome_count")
            or summary.get("completed_probe_outcome_count")
        ),
        "proof_excluded_probe_outcome_count": _int(
            summary.get("proof_excluded_probe_outcome_count")
            or answers.get("proof_excluded_probe_outcome_count")
            or quality.get("proof_excluded_probe_outcome_count")
        ),
        "proof_exclusion_present": (
            answers.get("proof_exclusion_present") is True
            or quality.get("proof_exclusion_present") is True
        ),
        "matched_control_present": quality.get("matched_control_present") is True,
        "promotion_evidence": answers.get("promotion_evidence") is True,
    }


def _authority_preserved(*payloads: dict[str, Any] | None) -> bool:
    stack: list[Any] = [payload for payload in payloads if payload is not None]
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
            if data.get(key) is True:
                return False
        stack.extend(value for value in data.values() if isinstance(value, (dict, list)))
    return True


def build_learning_ssot_decision(
    *,
    activation_preflight: dict[str, Any] | None,
    bounded_result_review: dict[str, Any] | None = None,
    activation_preflight_path: Path | None = None,
    bounded_result_review_path: Path | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    """Build the no-authority learning SSOT decision packet."""
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    activation = _dict(activation_preflight)
    answers = _dict(activation.get("answers"))
    ledger = _dict(activation.get("ledger"))
    writer_config = _dict(activation.get("writer_config"))
    writer_process = _dict(activation.get("writer_process"))
    result_review = _result_review_summary(bounded_result_review)

    activation_present = bool(activation)
    artifact_rows = _int(ledger.get("ledger_total_rows"))
    blocked_outcomes = _int(ledger.get("blocked_signal_outcome_count"))
    proof_excluded_probe = _int(ledger.get("proof_excluded_probe_outcome_count"))
    artifact_ledger_present = artifact_rows > 0
    artifact_ledger_has_learning_rows = (
        blocked_outcomes > 0
        or _int(ledger.get("admission_decision_count")) > 0
        or _int(ledger.get("captured_reject_count")) > 0
    )
    writer_config_enabled = writer_config.get("writer_enabled") is True
    writer_process_enabled = writer_process.get("writer_process_enabled") is True
    running_process_checked = writer_process.get("writer_process_checked") is True
    pg_backed_evidence_present = False
    authority_boundary_preserved = _authority_preserved(
        activation_preflight,
        bounded_result_review,
    )
    bounded_result_closed = result_review.get("status") in {
        "FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED",
        "LEARNING_REVIEW_CANDIDATE_OPERATOR_REVIEW_REQUIRED",
        "STOP_BOUNDED_DEMO_PROBE_REALIZED_EDGE_FAILED",
    }

    if not authority_boundary_preserved:
        status = "AUTHORITY_BOUNDARY_VIOLATION"
        current_ssot = "NONE"
        reason = "input_artifact_claimed_authority_or_cost_gate_mutation"
        next_actions = [
            "discard_authority_bearing_input_and_rerun_source_only_ssot_decision",
            "operator_review_authority_boundary_violation_before_learning_ssot_cutover",
        ]
    elif not activation_present:
        status = "SSOT_INPUT_MISSING"
        current_ssot = "NONE"
        reason = "activation_preflight_missing"
        next_actions = ["refresh_cost_gate_learning_lane_activation_preflight"]
    elif not artifact_ledger_present:
        status = "ARTIFACT_LEDGER_NOT_ACCUMULATING"
        current_ssot = "NONE"
        reason = "cost_gate_learning_artifact_ledger_missing_or_empty"
        next_actions = [
            "repair_or_activate_artifact_learning_ledger_before_ssot_selection"
        ]
    elif not artifact_ledger_has_learning_rows:
        status = "ARTIFACT_LEDGER_PRESENT_BUT_NOT_LEARNING_READY"
        current_ssot = "artifact_probe_ledger_jsonl"
        reason = "artifact_ledger_has_rows_but_no_learning_decision_or_outcome_rows"
        next_actions = ["continue_materializing_cost_gate_rejects_and_outcomes"]
    elif writer_config_enabled or writer_process_enabled:
        status = "PG_BACKED_LEDGER_MIGRATION_REVIEW_REQUIRED"
        current_ssot = "artifact_probe_ledger_jsonl"
        reason = "writer_flag_seen_but_pg_backed_learning_ledger_not_proven"
        next_actions = [
            "operator_review_pg_backed_cost_gate_learning_ledger_contract_before_ssot_cutover",
            "prove_pg_backed_ledger_schema_writer_idempotency_and_reconstruction_before_cutover",
        ]
    else:
        status = "ARTIFACT_LEDGER_CURRENT_SSOT"
        current_ssot = "artifact_probe_ledger_jsonl"
        reason = "artifact_learning_ledger_accumulates_evidence_and_pg_backed_writer_is_not_enabled_or_proven"
        next_actions = [
            "treat_artifact_probe_ledger_as_current_learning_ssot_with_strict_provenance",
            "design_pg_backed_cost_gate_learning_ledger_cutover_without_enabling_writer",
        ]

    if result_review.get("proof_exclusion_present") or proof_excluded_probe > 0:
        next_actions = list(
            dict.fromkeys(
                [
                    "repair_or_quarantine_proof_excluded_fill_lineage_before_any_ssot_cutover",
                    *next_actions,
                ]
            )
        )

    gates = {
        "activation_preflight_present": activation_present,
        "authority_boundary_preserved": authority_boundary_preserved,
        "artifact_ledger_present": artifact_ledger_present,
        "artifact_ledger_status": ledger.get("ledger_status"),
        "artifact_ledger_path": ledger.get("ledger_path"),
        "artifact_ledger_has_learning_rows": artifact_ledger_has_learning_rows,
        "artifact_ledger_currently_accumulating": (
            answers.get("currently_accumulating_evidence") is True
        ),
        "artifact_ledger_rows": artifact_rows,
        "blocked_signal_outcome_count": blocked_outcomes,
        "proof_excluded_probe_outcome_count": proof_excluded_probe,
        "runtime_writer_config_enabled": writer_config_enabled,
        "runtime_writer_process_checked": running_process_checked,
        "runtime_writer_process_enabled": writer_process_enabled,
        "pg_backed_learning_ledger_observed": pg_backed_evidence_present,
        "pg_backed_schema_verified": False,
        "pg_backed_writer_idempotency_verified": False,
        "pg_backed_reconstruction_verified": False,
        "pg_probe_performed": False,
        "bounded_result_review_present": bool(_dict(bounded_result_review)),
        "bounded_result_review_closed": bounded_result_closed,
        "bounded_result_review_status": result_review.get("status"),
        "bounded_result_review_proof_exclusion_present": (
            result_review.get("proof_exclusion_present") is True
        ),
        "pg_backed_cutover_ready": False,
    }

    return {
        "schema_version": LEARNING_SSOT_DECISION_SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "current_learning_ssot": current_ssot,
        "target_learning_ssot": "pg_backed_cost_gate_learning_ledger",
        "ssot_decision": {
            "artifact_probe_ledger_is_current_ssot": (
                current_ssot == "artifact_probe_ledger_jsonl"
            ),
            "pg_backed_ledger_is_current_ssot": False,
            "pg_backed_cutover_ready": False,
            "requires_operator_review_for_cutover": True,
            "requires_schema_and_writer_proof_for_cutover": True,
            "requires_reconstruction_proof_for_cutover": True,
            "requires_proof_exclusion_guard_for_cutover": True,
        },
        "migration_gates": gates,
        "result_review": result_review,
        "answers": {
            "learning_loop_closure_decision_recorded": True,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "operator_authorization_object_emitted": False,
            "promotion_evidence": False,
            "runtime_mutation_required": False,
            "runtime_mutation_performed": False,
            "pg_query_performed": False,
            "pg_write_required": False,
            "pg_write_performed": False,
            "bybit_call_required": False,
            "bybit_call_performed": False,
            "order_submission_performed": False,
        },
        "next_actions": next_actions,
        "sources": {
            "activation_preflight": _source_summary(
                activation_preflight,
                activation_preflight_path,
                now_utc=now,
            ),
            "bounded_result_review": _source_summary(
                bounded_result_review,
                bounded_result_review_path,
                now_utc=now,
            ),
        },
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    gates = _dict(packet.get("migration_gates"))
    answers = _dict(packet.get("answers"))
    lines = [
        "# Cost Gate Learning SSOT Decision",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Current SSOT: `{packet.get('current_learning_ssot')}`",
        f"- Target SSOT: `{packet.get('target_learning_ssot')}`",
        f"- Artifact ledger rows: `{gates.get('artifact_ledger_rows')}`",
        f"- Blocked-signal outcomes: `{gates.get('blocked_signal_outcome_count')}`",
        f"- Runtime writer config enabled: `{gates.get('runtime_writer_config_enabled')}`",
        f"- Runtime writer process enabled: `{gates.get('runtime_writer_process_enabled')}`",
        f"- PG-backed cutover ready: `{gates.get('pg_backed_cutover_ready')}`",
        f"- Promotion evidence: `{answers.get('promotion_evidence')}`",
        f"- Boundary: {BOUNDARY}.",
        "",
        "## Next Actions",
        "",
    ]
    for action in _list(packet.get("next_actions")):
        lines.append(f"- `{action}`")
    return "\n".join(lines) + "\n"


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--activation-preflight-json", type=Path)
    parser.add_argument("--bounded-result-review-json", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_learning_ssot_decision(
        activation_preflight=_read_json(args.activation_preflight_json),
        bounded_result_review=_read_json(args.bounded_result_review_json),
        activation_preflight_path=args.activation_preflight_json,
        bounded_result_review_path=args.bounded_result_review_json,
    )
    markdown = render_markdown(packet)
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.output:
        _write_text(args.output, markdown)
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True, default=str))
    elif not args.output:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
