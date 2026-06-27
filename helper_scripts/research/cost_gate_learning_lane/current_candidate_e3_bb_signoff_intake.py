#!/usr/bin/env python3
"""Locate and validate E3/BB signoff artifacts without order authority.

This helper is the machine-checkable intake step after the E3/BB signoff request
packet. It scans explicit directories for JSON files matching
``current_candidate_e3_bb_enablement_signoff_v1``, selects candidate/order-review
matching E3 and BB signoffs, and feeds them back into the existing E3/BB contract
validator.

It never creates signoffs, never enables the adapter/writer, never acquires a
Decision Lease, never calls Bybit, never submits/cancels/modifies orders, never
writes PG, and never grants probe/order/live authority.
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
from cost_gate_learning_lane import current_candidate_e3_bb_signoff_request_packet as request


SCHEMA_VERSION = "current_candidate_e3_bb_signoff_intake_v1"
APPROVED_NO_ORDER_STATUS = (
    "CURRENT_CANDIDATE_E3_BB_SIGNOFF_INTAKE_APPROVED_NO_ORDER"
)
SIGNOFFS_MISSING_STATUS = (
    "CURRENT_CANDIDATE_E3_BB_SIGNOFF_INTAKE_SIGNOFFS_MISSING_NO_ORDER"
)
BLOCKED_BY_LOSS_CONTROL_STATUS = (
    "CURRENT_CANDIDATE_E3_BB_SIGNOFF_INTAKE_BLOCKED_BY_LOSS_CONTROL"
)
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

DEFAULT_MAX_ARTIFACT_AGE_SECONDS = 6 * 60 * 60

BOUNDARY = (
    "E3/BB signoff intake only; no signoff creation, no order-capable action, "
    "no adapter/writer enablement, no Decision Lease acquire/release, no "
    "Bybit/exchange call, no order/cancel/modify, no PG query/write, no "
    "runtime/service/env/crontab mutation, no Cost Gate lowering, no risk "
    "expansion, no live/mainnet authority, no execution/fill/PnL, and no "
    "profit proof"
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


def _try_read_json(path: Path) -> dict[str, Any] | None:
    try:
        return _read_json(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _recursive_authority_violation(payload: Any) -> str | None:
    stack: list[tuple[str, Any]] = [("$", payload)]
    danger_true_keys = contract.DANGER_TRUE_KEYS | {
        "approval_granted_by_this_packet",
        "signoff_created_by_this_packet",
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


def _request_summary(packet: dict[str, Any] | None) -> dict[str, Any]:
    request_packet = _dict(packet)
    source_contract = _dict(request_packet.get("source_contract"))
    blockers: list[str] = []
    if request_packet.get("schema_version") != request.SCHEMA_VERSION:
        blockers.append("signoff_request_schema_mismatch")
    if request_packet.get("status") != request.READY_STATUS:
        blockers.append("signoff_request_status_not_ready")
    if _dict(request_packet.get("answers")).get("approval_granted_by_this_packet") is not False:
        blockers.append("signoff_request_claims_approval")
    if _dict(request_packet.get("answers")).get("order_capable_action_allowed") is not False:
        blockers.append("signoff_request_order_capable_not_false")
    if source_contract.get("status") != contract.SIGNOFF_REQUIRED_STATUS:
        blockers.append("source_contract_not_signoff_required")
    expected_candidate = _str(
        request_packet.get("candidate_side_cell_key")
        or source_contract.get("candidate_side_cell_key")
    )
    expected_review_sha = _str(source_contract.get("order_enablement_review_sha256"))
    if not expected_candidate:
        blockers.append("signoff_request_candidate_missing")
    if not expected_review_sha:
        blockers.append("signoff_request_order_enablement_sha_missing")
    return {
        "status": request_packet.get("status"),
        "candidate_side_cell_key": expected_candidate or None,
        "order_enablement_review_sha256": expected_review_sha or None,
        "source_contract_sha256": source_contract.get("sha256"),
        "blockers": blockers,
    }


def _candidate_sort_key(path: Path, payload: dict[str, Any]) -> tuple[str, str]:
    generated = _parse_dt(payload.get("generated_at_utc"))
    if generated is None:
        try:
            generated = dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc)
        except OSError:
            generated = dt.datetime.fromtimestamp(0, dt.timezone.utc)
    return (generated.isoformat(), str(path))


def _candidate_summary(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "schema_version": payload.get("schema_version"),
        "generated_at_utc": payload.get("generated_at_utc"),
        "role": payload.get("role"),
        "decision": payload.get("decision"),
        "candidate_side_cell_key": payload.get("candidate_side_cell_key"),
        "order_enablement_review_sha256": payload.get(
            "order_enablement_review_sha256"
        ),
    }


def _iter_json_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for base in paths:
        if base.is_file():
            files.append(base)
        elif base.is_dir():
            files.extend(sorted(base.rglob("*.json")))
    return files


def _locate_signoffs(
    *,
    search_paths: list[Path],
    candidate_side_cell_key: str | None,
    order_enablement_review_sha256: str | None,
) -> dict[str, Any]:
    candidates_by_role: dict[str, list[tuple[Path, dict[str, Any]]]] = {
        contract.E3_ROLE: [],
        contract.BB_ROLE: [],
    }
    ignored_count = 0
    for path in _iter_json_files(search_paths):
        payload = _try_read_json(path)
        if not payload:
            ignored_count += 1
            continue
        role = payload.get("role")
        if payload.get("schema_version") != contract.SIGNOFF_SCHEMA_VERSION:
            ignored_count += 1
            continue
        if role not in candidates_by_role:
            ignored_count += 1
            continue
        if (
            candidate_side_cell_key
            and payload.get("candidate_side_cell_key") != candidate_side_cell_key
        ):
            ignored_count += 1
            continue
        if (
            order_enablement_review_sha256
            and payload.get("order_enablement_review_sha256")
            != order_enablement_review_sha256
        ):
            ignored_count += 1
            continue
        candidates_by_role[role].append((path, payload))

    selected: dict[str, dict[str, Any]] = {}
    selected_payloads: dict[str, dict[str, Any]] = {}
    selected_paths: dict[str, Path] = {}
    for role, candidates in candidates_by_role.items():
        if candidates:
            path, payload = sorted(
                candidates, key=lambda item: _candidate_sort_key(item[0], item[1])
            )[-1]
            selected[role] = _candidate_summary(path, payload)
            selected_payloads[role] = payload
            selected_paths[role] = path
        else:
            selected[role] = {}

    return {
        "searched_paths": [str(path) for path in search_paths],
        "ignored_file_count": ignored_count,
        "candidate_count_by_role": {
            role: len(candidates) for role, candidates in candidates_by_role.items()
        },
        "selected": selected,
        "selected_payloads": selected_payloads,
        "selected_paths": selected_paths,
    }


def build_current_candidate_e3_bb_signoff_intake(
    *,
    order_enablement_review: dict[str, Any] | None,
    signoff_request_packet: dict[str, Any] | None,
    search_paths: list[Path],
    now_utc: dt.datetime | None = None,
    max_artifact_age_seconds: int = DEFAULT_MAX_ARTIFACT_AGE_SECONDS,
    order_enablement_path: Path | None = None,
    request_path: Path | None = None,
) -> dict[str, Any]:
    if max_artifact_age_seconds <= 0 or max_artifact_age_seconds > 14 * 24 * 3600:
        raise ValueError("max_artifact_age_seconds must be in (0, 1209600]")

    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    request_review = _request_summary(signoff_request_packet)
    expected_review_sha = _str(request_review.get("order_enablement_review_sha256"))
    order_review_sha = _sha256(order_enablement_path)
    blockers = list(_list(request_review.get("blockers")))
    if expected_review_sha and order_review_sha and expected_review_sha != order_review_sha:
        blockers.append("order_enablement_review_sha_mismatch")

    located = _locate_signoffs(
        search_paths=search_paths,
        candidate_side_cell_key=_str(request_review.get("candidate_side_cell_key")) or None,
        order_enablement_review_sha256=expected_review_sha or order_review_sha,
    )
    selected_payloads = _dict(located.get("selected_payloads"))
    selected_paths = _dict(located.get("selected_paths"))

    contract_packet = contract.build_current_candidate_e3_bb_enablement_review_contract(
        order_enablement_review=order_enablement_review,
        e3_signoff=selected_payloads.get(contract.E3_ROLE),
        bb_signoff=selected_payloads.get(contract.BB_ROLE),
        candidate_side_cell_key=_str(request_review.get("candidate_side_cell_key")) or None,
        now_utc=now,
        max_artifact_age_seconds=max_artifact_age_seconds,
        order_enablement_path=order_enablement_path,
        e3_signoff_path=selected_paths.get(contract.E3_ROLE),
        bb_signoff_path=selected_paths.get(contract.BB_ROLE),
    )
    authority_violation = _recursive_authority_violation(
        {
            "signoff_request_packet": signoff_request_packet or {},
            "contract_packet": contract_packet,
        }
    )

    if authority_violation:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = f"input_contains_authority_or_mutation_field:{authority_violation}"
    elif blockers or contract_packet.get("status") == contract.BLOCKED_BY_LOSS_CONTROL_STATUS:
        status = BLOCKED_BY_LOSS_CONTROL_STATUS
        reason = "signoff_intake_inputs_blocked_by_loss_control"
    elif contract_packet.get("status") == contract.APPROVED_NO_ORDER_STATUS:
        status = APPROVED_NO_ORDER_STATUS
        reason = "e3_bb_signoffs_found_and_validate_no_order_review_only"
    else:
        status = SIGNOFFS_MISSING_STATUS
        reason = "valid_e3_bb_signoff_artifacts_not_found"

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "request_packet": {
            "path": str(request_path) if request_path else None,
            "sha256": _sha256(request_path),
            **request_review,
        },
        "order_enablement_review": {
            "path": str(order_enablement_path) if order_enablement_path else None,
            "sha256": order_review_sha,
        },
        "signoff_locator": {
            "searched_paths": located.get("searched_paths"),
            "ignored_file_count": located.get("ignored_file_count"),
            "candidate_count_by_role": located.get("candidate_count_by_role"),
            "selected": located.get("selected"),
        },
        "contract_review": contract_packet,
        "loss_control_blockers": sorted(set(blockers + _list(contract_packet.get("loss_control_blockers")))),
        "signoff_blockers": _list(contract_packet.get("signoff_blockers")),
        "authority_boundary_violation": authority_violation
        or contract_packet.get("authority_boundary_violation"),
        "max_safe_next_action": (
            "PM_SUPERVISED_SAME_WINDOW_GATE_REVALIDATION_ONLY_NO_ORDER_FROM_THIS_PACKET"
            if status == APPROVED_NO_ORDER_STATUS
            else "COLLECT_ACTUAL_E3_BB_SIGNOFF_ARTIFACTS_NO_ORDER"
            if status == SIGNOFFS_MISSING_STATUS
            else "REPAIR_SIGNOFF_INTAKE_INPUTS_NO_ORDER"
        ),
        "answers": {
            "signoffs_found_and_validated": status == APPROVED_NO_ORDER_STATUS,
            "e3_bb_review_approved_no_order": status == APPROVED_NO_ORDER_STATUS,
            "signoff_created_by_this_packet": False,
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
    answers = _dict(packet.get("answers"))
    locator = _dict(packet.get("signoff_locator"))
    lines = [
        "# Current Candidate E3/BB Signoff Intake",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Signoffs found and validated: `{answers.get('signoffs_found_and_validated')}`",
        f"- Order-capable action allowed: `{answers.get('order_capable_action_allowed')}`",
        f"- Max safe next action: `{packet.get('max_safe_next_action')}`",
        "",
        "## Selected Signoffs",
    ]
    selected = _dict(locator.get("selected"))
    for role in (contract.E3_ROLE, contract.BB_ROLE):
        item = _dict(selected.get(role))
        if item:
            lines.append(f"- `{role}`: `{item.get('path')}` sha `{item.get('sha256')}` decision `{item.get('decision')}`")
        else:
            lines.append(f"- `{role}`: missing")
    lines.extend(["", "## Signoff Blockers"])
    signoff_blockers = _list(packet.get("signoff_blockers"))
    if signoff_blockers:
        lines.extend(f"- `{blocker}`" for blocker in signoff_blockers)
    else:
        lines.append("- none")
    lines.extend(["", "## Boundary", "", str(packet.get("boundary", ""))])
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order-enable-review-json", type=Path, required=True)
    parser.add_argument("--signoff-request-json", type=Path, required=True)
    parser.add_argument(
        "--signoff-search-path",
        type=Path,
        action="append",
        default=[],
        help="Directory or JSON file to scan. Can be provided multiple times.",
    )
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
    search_paths = args.signoff_search_path or [args.signoff_request_json.parent]
    packet = build_current_candidate_e3_bb_signoff_intake(
        order_enablement_review=_read_json(args.order_enable_review_json),
        signoff_request_packet=_read_json(args.signoff_request_json),
        search_paths=search_paths,
        now_utc=now,
        max_artifact_age_seconds=args.max_artifact_age_seconds,
        order_enablement_path=args.order_enable_review_json,
        request_path=args.signoff_request_json,
    )
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.output:
        _write_text(args.output, render_markdown(packet))
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if packet["status"] == APPROVED_NO_ORDER_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
