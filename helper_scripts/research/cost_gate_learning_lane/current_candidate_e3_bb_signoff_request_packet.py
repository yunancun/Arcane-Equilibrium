#!/usr/bin/env python3
"""Build E3/BB signoff request packets without granting approval.

This helper consumes a
``current_candidate_e3_bb_enablement_review_contract_v1`` packet and emits a
role-specific request packet plus inert signoff templates. The templates are
intentionally not valid approvals: reviewers must replace the template decision
with the exact reviewed decision after doing their own E3/BB work.

It never enables the adapter/writer, never acquires a Decision Lease, never
calls Bybit, never submits/cancels/modifies orders, never writes PG, and never
grants probe/order/live authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from cost_gate_learning_lane import (
    current_candidate_e3_bb_enablement_review_contract as contract,
)


SCHEMA_VERSION = "current_candidate_e3_bb_signoff_request_packet_v1"
READY_STATUS = "CURRENT_CANDIDATE_E3_BB_SIGNOFF_REQUEST_READY_NO_ORDER"
BLOCKED_BY_LOSS_CONTROL_STATUS = (
    "CURRENT_CANDIDATE_E3_BB_SIGNOFF_REQUEST_BLOCKED_BY_LOSS_CONTROL"
)
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

TEMPLATE_DECISION = "REVIEW_REQUIRED_NO_APPROVAL_TEMPLATE"
DEFAULT_MAX_ARTIFACT_AGE_SECONDS = 6 * 60 * 60

BOUNDARY = (
    "E3/BB signoff request packet only; no E3/BB approval, no order-capable "
    "action, no adapter/writer enablement, no Decision Lease acquire/release, "
    "no Bybit/exchange call, no order/cancel/modify, no PG query/write, no "
    "runtime/service/env/crontab mutation, no Cost Gate lowering, no risk "
    "expansion, no live/mainnet authority, no execution/fill/PnL, and no "
    "profit proof"
)

FORBIDDEN_TEMPLATE_CLAIMS = sorted(
    {
        "approval_granted_by_this_packet",
        "order_capable_action_allowed",
        "allowed_to_submit_order",
        "order_submission_performed",
        "adapter_enablement_performed",
        "writer_enablement_performed",
        "decision_lease_acquire_performed",
        "decision_lease_release_performed",
        "bybit_call_performed",
        "pg_query_performed",
        "pg_write_performed",
        "cost_gate_lowering_performed",
        "live_authority_granted",
        "mainnet_authority_granted",
        "promotion_proof",
        "profit_proof",
    }
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
        return math.isfinite(float(value)) and value != 0
    if isinstance(value, str):
        return value.strip().lower() in {
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
            "approve",
            "approved",
        }
    return False


def _parse_dt(value: Any) -> dt.datetime | None:
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


def _sha256(path: Path | None) -> str | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"json object required: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _artifact_age_seconds(payload: dict[str, Any], now_utc: dt.datetime) -> float | None:
    parsed = _parse_dt(payload.get("generated_at_utc"))
    if parsed is None:
        return None
    return max(0.0, (now_utc - parsed).total_seconds())


def _recursive_authority_violation(payload: Any) -> str | None:
    stack: list[tuple[str, Any]] = [("$", payload)]
    danger_true_keys = contract.DANGER_TRUE_KEYS | {
        "approval_granted_by_this_packet",
        "e3_bb_review_granted_by_this_packet",
    }
    while stack:
        path, node = stack.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                child_path = f"{path}.{key}"
                if key in danger_true_keys and _truthy(value):
                    return child_path
                if key == "main_cost_gate_adjustment" and value not in (
                    None,
                    "",
                    "NONE",
                ):
                    return child_path
                stack.append((child_path, value))
        elif isinstance(node, list):
            for index, item in enumerate(node):
                stack.append((f"{path}[{index}]", item))
    return None


def _false_answers() -> dict[str, Any]:
    return {
        "order_capable_action_allowed": False,
        "allowed_to_submit_order": False,
        "order_submission_performed": False,
        "adapter_enablement_performed": False,
        "writer_enablement_performed": False,
        "decision_lease_acquire_performed": False,
        "decision_lease_release_performed": False,
        "bybit_call_performed": False,
        "pg_query_performed": False,
        "pg_write_performed": False,
        "cost_gate_lowering_performed": False,
        "live_authority_granted": False,
        "mainnet_authority_granted": False,
        "main_cost_gate_adjustment": "NONE",
        "promotion_proof": False,
        "profit_proof": False,
    }


def _review_focus(role: str) -> list[str]:
    if role == contract.E3_ROLE:
        return [
            "verify_no_authority_boundary_contamination",
            "verify_adapter_writer_decision_lease_flags_remain_false",
            "verify_demo_only_no_live_or_mainnet_authority",
            "verify_runtime_mutation_pg_and_secret_exposure_absent",
            "verify_same_window_gates_are_still_required_before_order_action",
        ]
    return [
        "verify_bybit_exchange_call_absent_in_this_packet",
        "verify_order_shape_and_gui_cap_lineage_are_review_only",
        "verify_no_order_cancel_modify_or_private_bybit_action_occurred",
        "verify_cost_gate_and_risk_envelope_are_not_expanded",
        "verify_same_window_bbo_instrument_and_book_clean_gates_remain_required",
    ]


def _template_for_role(
    *,
    role: str,
    generated_at_utc: str,
    candidate_side_cell_key: str | None,
    order_enablement_review_sha256: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": contract.SIGNOFF_SCHEMA_VERSION,
        "generated_at_utc": generated_at_utc,
        "role": role,
        "decision": TEMPLATE_DECISION,
        "candidate_side_cell_key": candidate_side_cell_key,
        "order_enablement_review_sha256": order_enablement_review_sha256,
        "answers": _false_answers(),
        "review_notes": [
            "Replace decision with APPROVE_ENABLEMENT_REVIEW_NO_ORDER only after role review.",
            "This template is not a valid approval and must fail the E3/BB contract until edited by the reviewer.",
        ],
    }


def _validate_contract_packet(
    packet: dict[str, Any] | None,
    *,
    now_utc: dt.datetime,
    max_artifact_age_seconds: int,
) -> dict[str, Any]:
    review = _dict(packet)
    answers = _dict(review.get("answers"))
    required = _dict(review.get("required_signoff_contract"))
    blockers: list[str] = []

    if not review:
        blockers.append("e3_bb_contract_missing")
    if review.get("schema_version") != contract.SCHEMA_VERSION:
        blockers.append("e3_bb_contract_schema_mismatch")
    if review.get("status") != contract.SIGNOFF_REQUIRED_STATUS:
        blockers.append("e3_bb_contract_status_not_signoff_required")
    if review.get("loss_control_blockers") not in ([], None):
        blockers.append("e3_bb_contract_loss_control_blockers_present")
    if review.get("authority_boundary_violation") not in (None, ""):
        blockers.append("e3_bb_contract_authority_violation_present")
    if answers.get("order_capable_action_allowed") is not False:
        blockers.append("e3_bb_contract_order_capable_not_false")
    if answers.get("e3_bb_signoff_contract_ready") is not True:
        blockers.append("e3_bb_contract_not_ready")
    if answers.get("e3_bb_review_approved_no_order") is not False:
        blockers.append("e3_bb_contract_already_or_wrongly_approved")

    allowed_signoff_blockers = {"e3_signoff_missing", "bb_signoff_missing"}
    signoff_blockers = set(_list(review.get("signoff_blockers")))
    unexpected_signoff_blockers = sorted(signoff_blockers - allowed_signoff_blockers)
    if unexpected_signoff_blockers:
        blockers.extend(f"unexpected_signoff_blocker:{item}" for item in unexpected_signoff_blockers)
    if signoff_blockers != allowed_signoff_blockers:
        blockers.append("e3_bb_contract_missing_signoff_blocker_set_mismatch")

    if required.get("schema_version") != contract.SIGNOFF_SCHEMA_VERSION:
        blockers.append("required_signoff_schema_mismatch")
    if required.get("decision") != contract.APPROVE_DECISION:
        blockers.append("required_signoff_decision_mismatch")
    if sorted(_list(required.get("roles"))) != [contract.BB_ROLE, contract.E3_ROLE]:
        blockers.append("required_signoff_roles_mismatch")
    if not _str(required.get("candidate_side_cell_key")):
        blockers.append("required_signoff_candidate_missing")
    if not _str(required.get("order_enablement_review_sha256")):
        blockers.append("required_signoff_order_enablement_sha_missing")

    age = _artifact_age_seconds(review, now_utc)
    fresh = age is None or age <= max_artifact_age_seconds
    if not fresh:
        blockers.append("e3_bb_contract_stale")

    return {
        "status": review.get("status"),
        "generated_at_utc": review.get("generated_at_utc"),
        "age_seconds": age,
        "fresh": fresh,
        "candidate_side_cell_key": required.get("candidate_side_cell_key"),
        "order_enablement_review_sha256": required.get(
            "order_enablement_review_sha256"
        ),
        "signoff_blockers": sorted(signoff_blockers),
        "blockers": blockers,
    }


def build_current_candidate_e3_bb_signoff_request_packet(
    *,
    e3_bb_contract: dict[str, Any] | None,
    now_utc: dt.datetime | None = None,
    max_artifact_age_seconds: int = DEFAULT_MAX_ARTIFACT_AGE_SECONDS,
    e3_bb_contract_path: Path | None = None,
) -> dict[str, Any]:
    if max_artifact_age_seconds <= 0 or max_artifact_age_seconds > 14 * 24 * 3600:
        raise ValueError("max_artifact_age_seconds must be in (0, 1209600]")

    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    generated = now.isoformat()
    contract_summary = _validate_contract_packet(
        e3_bb_contract,
        now_utc=now,
        max_artifact_age_seconds=max_artifact_age_seconds,
    )
    authority_violation = _recursive_authority_violation(e3_bb_contract or {})
    blockers = sorted(set(_list(contract_summary.get("blockers"))))

    if authority_violation:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = f"contract_contains_authority_or_mutation_field:{authority_violation}"
    elif blockers:
        status = BLOCKED_BY_LOSS_CONTROL_STATUS
        reason = "e3_bb_contract_not_safe_for_signoff_request"
    else:
        status = READY_STATUS
        reason = "role_specific_e3_bb_signoff_request_templates_ready_no_order"

    candidate = _str(contract_summary.get("candidate_side_cell_key")) or None
    order_review_sha = _str(contract_summary.get("order_enablement_review_sha256")) or None
    requested_roles = []
    for role in (contract.E3_ROLE, contract.BB_ROLE):
        requested_roles.append(
            {
                "role": role,
                "required_schema_version": contract.SIGNOFF_SCHEMA_VERSION,
                "required_decision_after_review": contract.APPROVE_DECISION,
                "template_decision": TEMPLATE_DECISION,
                "template_is_approval": False,
                "review_focus": _review_focus(role),
                "forbidden_template_claims": FORBIDDEN_TEMPLATE_CLAIMS,
                "signoff_template": _template_for_role(
                    role=role,
                    generated_at_utc=generated,
                    candidate_side_cell_key=candidate,
                    order_enablement_review_sha256=order_review_sha,
                ),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated,
        "status": status,
        "reason": reason,
        "candidate_side_cell_key": candidate,
        "source_contract": {
            "path": str(e3_bb_contract_path) if e3_bb_contract_path else None,
            "sha256": _sha256(e3_bb_contract_path),
            **contract_summary,
        },
        "requested_roles": requested_roles,
        "loss_control_blockers": blockers,
        "authority_boundary_violation": authority_violation,
        "max_safe_next_action": (
            "HAND_REQUEST_PACKET_TO_E3_AND_BB_FOR_EXPLICIT_NO_ORDER_REVIEW"
            if status == READY_STATUS
            else "REPAIR_E3_BB_CONTRACT_INPUTS_NO_ORDER"
        ),
        "answers": {
            "signoff_request_ready": status == READY_STATUS,
            "approval_granted_by_this_packet": False,
            "e3_bb_review_approved_no_order": False,
            "templates_are_approval": False,
            "order_capable_action_allowed": False,
            "allowed_to_submit_order": False,
            "order_submission_performed": False,
            "adapter_enablement_performed": False,
            "writer_enablement_performed": False,
            "decision_lease_acquire_performed": False,
            "decision_lease_release_performed": False,
            "bybit_call_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "cost_gate_lowering_performed": False,
            "risk_expansion": False,
            "live_authority_granted": False,
            "mainnet_authority_granted": False,
            "promotion_proof": False,
            "profit_proof": False,
        },
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# Current Candidate E3/BB Signoff Request Packet",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Candidate: `{packet.get('candidate_side_cell_key')}`",
        f"- Approval granted by this packet: `{_dict(packet.get('answers')).get('approval_granted_by_this_packet')}`",
        f"- Order-capable action allowed: `{_dict(packet.get('answers')).get('order_capable_action_allowed')}`",
        f"- Max safe next action: `{packet.get('max_safe_next_action')}`",
        "",
        "## Loss-Control Blockers",
    ]
    blockers = _list(packet.get("loss_control_blockers"))
    lines.extend(f"- `{blocker}`" for blocker in blockers) if blockers else lines.append("- none")
    lines.extend(["", "## Requested Roles"])
    for role in _list(packet.get("requested_roles")):
        role_packet = _dict(role)
        lines.append(f"- `{role_packet.get('role')}`: template decision `{role_packet.get('template_decision')}`; required decision after review `{role_packet.get('required_decision_after_review')}`")
    lines.extend(["", "## Boundary", "", str(packet.get("boundary", ""))])
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--e3-bb-contract-json", type=Path, required=True)
    parser.add_argument(
        "--max-artifact-age-seconds",
        type=int,
        default=DEFAULT_MAX_ARTIFACT_AGE_SECONDS,
    )
    parser.add_argument("--now-utc")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    now = _parse_dt(args.now_utc) if args.now_utc else None
    packet = build_current_candidate_e3_bb_signoff_request_packet(
        e3_bb_contract=_read_json(args.e3_bb_contract_json),
        now_utc=now,
        max_artifact_age_seconds=args.max_artifact_age_seconds,
        e3_bb_contract_path=args.e3_bb_contract_json,
    )
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.output:
        _write_text(args.output, render_markdown(packet))
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if packet["status"] == READY_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
