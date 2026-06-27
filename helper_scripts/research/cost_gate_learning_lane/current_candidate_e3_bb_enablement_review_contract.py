#!/usr/bin/env python3
"""Build/validate the E3/BB enablement-review contract without order authority.

This helper is the machine-checkable handoff after
``current_candidate_order_enablement_review``. It validates the PM-produced
no-order evidence packet, defines the exact E3 and BB signoff artifact contract,
and can validate those signoffs when supplied.

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

from cost_gate_learning_lane import current_candidate_order_enablement_review as enablement


SCHEMA_VERSION = "current_candidate_e3_bb_enablement_review_contract_v1"
SIGNOFF_SCHEMA_VERSION = "current_candidate_e3_bb_enablement_signoff_v1"

SIGNOFF_REQUIRED_STATUS = (
    "CURRENT_CANDIDATE_E3_BB_ENABLEMENT_REVIEW_SIGNOFF_REQUIRED_NO_ORDER"
)
APPROVED_NO_ORDER_STATUS = (
    "CURRENT_CANDIDATE_E3_BB_ENABLEMENT_REVIEW_APPROVED_NO_ORDER"
)
BLOCKED_BY_LOSS_CONTROL_STATUS = (
    "CURRENT_CANDIDATE_E3_BB_ENABLEMENT_REVIEW_BLOCKED_BY_LOSS_CONTROL"
)
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

DEFAULT_MAX_ARTIFACT_AGE_SECONDS = 6 * 60 * 60
E3_ROLE = "E3"
BB_ROLE = "BB"
APPROVE_DECISION = "APPROVE_ENABLEMENT_REVIEW_NO_ORDER"

BOUNDARY = (
    "E3/BB enablement-review contract only; no order-capable action, no "
    "adapter/writer enablement, no Decision Lease acquire/release, no Bybit/"
    "exchange call, no order/cancel/modify, no PG query/write, no runtime/"
    "service/env/crontab mutation, no Cost Gate lowering, no risk expansion, "
    "no live/mainnet authority, no execution/fill/PnL, and no profit proof"
)

DANGER_TRUE_KEYS = enablement.AUTHORITY_TRUE_KEYS | {
    "e3_bb_review_grants_order_authority",
    "same_window_gates_bypassed",
    "adapter_enablement_approved_now",
    "writer_enablement_approved_now",
}


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


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


def _artifact_summary(
    *,
    name: str,
    path: Path | None,
    payload: dict[str, Any] | None,
    now_utc: dt.datetime,
    max_age_seconds: int,
    required: bool,
) -> dict[str, Any]:
    present = isinstance(payload, dict) and bool(payload)
    age = _artifact_age_seconds(payload or {}, now_utc) if present else None
    fresh = present and (age is None or age <= max_age_seconds)
    blockers: list[str] = []
    if required and not present:
        blockers.append(f"{name}_missing")
    if present and not fresh:
        blockers.append(f"{name}_stale")
    return {
        "name": name,
        "path": str(path) if path else None,
        "sha256": _sha256(path),
        "present": present,
        "schema_version": _dict(payload).get("schema_version") if present else None,
        "status": _dict(payload).get("status") if present else None,
        "generated_at_utc": _dict(payload).get("generated_at_utc") if present else None,
        "age_seconds": age,
        "fresh": fresh,
        "blockers": blockers,
    }


def _recursive_authority_violation(payload: Any) -> str | None:
    stack: list[tuple[str, Any]] = [("$", payload)]
    while stack:
        path, node = stack.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                child_path = f"{path}.{key}"
                if key in DANGER_TRUE_KEYS and _truthy(value):
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


def _candidate_key(packet: dict[str, Any]) -> str | None:
    candidate = _dict(packet.get("candidate"))
    requested = _str(candidate.get("requested_side_cell_key"))
    if requested:
        return requested
    observed = _list(candidate.get("observed_side_cell_keys"))
    if len(observed) == 1:
        return _str(observed[0])
    return None


def _validate_order_enablement_review(packet: dict[str, Any] | None) -> dict[str, Any]:
    review = _dict(packet)
    answers = _dict(review.get("answers"))
    admission = _dict(review.get("admission_review"))
    governance = _dict(review.get("governance_review"))
    deploy = _dict(review.get("deploy_review"))
    blockers: list[str] = []

    if review.get("schema_version") != enablement.SCHEMA_VERSION:
        blockers.append("order_enablement_schema_mismatch")
    if review.get("status") != enablement.READY_FOR_E3_BB_STATUS:
        blockers.append("order_enablement_status_not_ready")
    if review.get("loss_control_blockers") not in ([], None):
        blockers.append("order_enablement_loss_control_blockers_present")
    if review.get("authority_boundary_violation") not in (None, ""):
        blockers.append("order_enablement_authority_violation_present")
    for key in (
        "order_capable_action_allowed",
        "allowed_to_submit_order",
        "order_submission_performed",
        "adapter_enablement_performed",
        "writer_enablement_performed",
        "decision_lease_acquire_performed",
        "decision_lease_release_performed",
        "pg_write_performed",
        "cost_gate_lowering_performed",
        "live_authority_granted",
        "mainnet_authority_granted",
    ):
        if answers.get(key) is not False:
            blockers.append(f"order_enablement_{key}_not_false")

    if admission.get("gui_risk_config_is_source_of_truth") is not True:
        blockers.append("gui_risk_config_not_source_of_truth")
    if _float(admission.get("per_trade_risk_pct_fraction")) != 0.1:
        blockers.append("per_trade_risk_pct_fraction_not_0_1")
    if _float(admission.get("gui_p1_risk_trade_pct")) != 10.0:
        blockers.append("gui_p1_risk_trade_not_10_percent")
    if _float(admission.get("position_size_max_pct")) != 25.0:
        blockers.append("position_size_max_pct_not_25")
    if (_float(admission.get("per_trade_budget_usdt")) or 0.0) <= 10.0:
        blockers.append("per_trade_budget_not_equity_resolved")
    if admission.get("local_10_usdt_cap_is_authority") is not False:
        blockers.append("local_10_usdt_cap_marked_authority")

    if governance.get("risk_level") != "NORMAL":
        blockers.append("guardian_not_normal")
    if _float(governance.get("position_size_multiplier")) != 1.0:
        blockers.append("guardian_multiplier_not_one")
    if _float(governance.get("lease_live_count")) != 0.0:
        blockers.append("lease_live_count_nonzero_before_enablement")
    if _float(governance.get("lease_count")) != 0.0:
        blockers.append("lease_count_nonzero_before_enablement")

    if deploy.get("OPENCLAW_ALLOW_MAINNET") not in ("0", 0, False):
        blockers.append("mainnet_env_not_zero")
    if deploy.get("OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED") not in ("", None, "0", 0, False):
        blockers.append("bounded_probe_adapter_enabled_before_review")
    if deploy.get("OPENCLAW_DEMO_LEARNING_LANE_WRITER") not in ("", None, "0", 0, False):
        blockers.append("demo_learning_lane_writer_enabled_before_review")

    return {
        "status": review.get("status"),
        "candidate": _candidate_key(review),
        "per_trade_risk_pct_fraction": admission.get("per_trade_risk_pct_fraction"),
        "gui_p1_risk_trade_pct": admission.get("gui_p1_risk_trade_pct"),
        "per_trade_budget_usdt": admission.get("per_trade_budget_usdt"),
        "position_size_max_pct": admission.get("position_size_max_pct"),
        "local_10_usdt_cap_is_authority": admission.get(
            "local_10_usdt_cap_is_authority"
        ),
        "guardian_risk_level": governance.get("risk_level"),
        "guardian_position_size_multiplier": governance.get("position_size_multiplier"),
        "lease_live_count": governance.get("lease_live_count"),
        "deploy_runtime_head": deploy.get("runtime_head"),
        "blockers": sorted(set(blockers)),
    }


def _signoff_summary(
    *,
    role: str,
    payload: dict[str, Any] | None,
    candidate_side_cell_key: str | None,
    order_enablement_sha256: str | None,
) -> dict[str, Any]:
    packet = _dict(payload)
    answers = _dict(packet.get("answers"))
    blockers: list[str] = []

    if not packet:
        blockers.append(f"{role.lower()}_signoff_missing")
    else:
        if packet.get("schema_version") != SIGNOFF_SCHEMA_VERSION:
            blockers.append(f"{role.lower()}_signoff_schema_mismatch")
        if packet.get("role") != role:
            blockers.append(f"{role.lower()}_signoff_role_mismatch")
        if packet.get("decision") != APPROVE_DECISION:
            blockers.append(f"{role.lower()}_signoff_decision_not_approve_no_order")
        if candidate_side_cell_key and packet.get("candidate_side_cell_key") != candidate_side_cell_key:
            blockers.append(f"{role.lower()}_signoff_candidate_mismatch")
        if (
            order_enablement_sha256
            and packet.get("order_enablement_review_sha256") != order_enablement_sha256
        ):
            blockers.append(f"{role.lower()}_signoff_review_sha_mismatch")
        for key in (
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
        ):
            if answers.get(key) is not False:
                blockers.append(f"{role.lower()}_signoff_{key}_not_false")
        if answers.get("main_cost_gate_adjustment") not in (None, "NONE"):
            blockers.append(f"{role.lower()}_signoff_cost_gate_adjustment_not_none")

    return {
        "role": role,
        "present": bool(packet),
        "schema_version": packet.get("schema_version"),
        "decision": packet.get("decision"),
        "candidate_side_cell_key": packet.get("candidate_side_cell_key"),
        "order_enablement_review_sha256": packet.get(
            "order_enablement_review_sha256"
        ),
        "blockers": blockers,
    }


def build_current_candidate_e3_bb_enablement_review_contract(
    *,
    order_enablement_review: dict[str, Any] | None,
    e3_signoff: dict[str, Any] | None = None,
    bb_signoff: dict[str, Any] | None = None,
    candidate_side_cell_key: str | None = None,
    now_utc: dt.datetime | None = None,
    max_artifact_age_seconds: int = DEFAULT_MAX_ARTIFACT_AGE_SECONDS,
    order_enablement_path: Path | None = None,
    e3_signoff_path: Path | None = None,
    bb_signoff_path: Path | None = None,
) -> dict[str, Any]:
    if max_artifact_age_seconds <= 0 or max_artifact_age_seconds > 14 * 24 * 3600:
        raise ValueError("max_artifact_age_seconds must be in (0, 1209600]")

    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    artifacts = {
        "order_enablement_review": _artifact_summary(
            name="order_enablement_review",
            path=order_enablement_path,
            payload=order_enablement_review,
            now_utc=now,
            max_age_seconds=max_artifact_age_seconds,
            required=True,
        ),
        "e3_signoff": _artifact_summary(
            name="e3_signoff",
            path=e3_signoff_path,
            payload=e3_signoff,
            now_utc=now,
            max_age_seconds=max_artifact_age_seconds,
            required=False,
        ),
        "bb_signoff": _artifact_summary(
            name="bb_signoff",
            path=bb_signoff_path,
            payload=bb_signoff,
            now_utc=now,
            max_age_seconds=max_artifact_age_seconds,
            required=False,
        ),
    }
    order_enablement_sha = _sha256(order_enablement_path)
    order_review = _validate_order_enablement_review(order_enablement_review)
    observed_candidate = order_review.get("candidate")
    candidate_blockers: list[str] = []
    if candidate_side_cell_key and observed_candidate != candidate_side_cell_key:
        candidate_blockers.append("candidate_identity_mismatch")
    if not (candidate_side_cell_key or observed_candidate):
        candidate_blockers.append("candidate_identity_missing")
    effective_candidate = candidate_side_cell_key or observed_candidate

    e3 = _signoff_summary(
        role=E3_ROLE,
        payload=e3_signoff,
        candidate_side_cell_key=effective_candidate,
        order_enablement_sha256=order_enablement_sha,
    )
    bb = _signoff_summary(
        role=BB_ROLE,
        payload=bb_signoff,
        candidate_side_cell_key=effective_candidate,
        order_enablement_sha256=order_enablement_sha,
    )

    artifact_blockers = [
        blocker
        for name, artifact in artifacts.items()
        if name == "order_enablement_review" or artifact.get("present")
        for blocker in _list(artifact.get("blockers"))
    ]
    loss_control_blockers = sorted(
        set(
            artifact_blockers
            + _list(order_review.get("blockers"))
            + candidate_blockers
        )
    )
    signoff_blockers = sorted(set(_list(e3.get("blockers")) + _list(bb.get("blockers"))))

    authority_violation = _recursive_authority_violation(
        {
            "order_enablement_review": order_enablement_review or {},
            "e3_signoff": e3_signoff or {},
            "bb_signoff": bb_signoff or {},
        }
    )
    if authority_violation:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = f"input_contains_authority_or_mutation_field:{authority_violation}"
    elif loss_control_blockers:
        status = BLOCKED_BY_LOSS_CONTROL_STATUS
        reason = "order_enablement_review_not_safe_for_e3_bb_contract"
    elif signoff_blockers:
        status = SIGNOFF_REQUIRED_STATUS
        reason = "explicit_e3_bb_signoff_artifacts_required_before_same_window_order_gates"
    else:
        status = APPROVED_NO_ORDER_STATUS
        reason = "e3_bb_signoffs_validate_no_order_enablement_review_only"

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "candidate": {
            "requested_side_cell_key": candidate_side_cell_key,
            "observed_side_cell_key": observed_candidate,
            "effective_side_cell_key": effective_candidate,
        },
        "artifacts": artifacts,
        "order_enablement_review": order_review,
        "required_signoff_contract": {
            "schema_version": SIGNOFF_SCHEMA_VERSION,
            "decision": APPROVE_DECISION,
            "roles": [E3_ROLE, BB_ROLE],
            "candidate_side_cell_key": effective_candidate,
            "order_enablement_review_sha256": order_enablement_sha,
            "answers_must_remain_false": sorted(DANGER_TRUE_KEYS),
            "main_cost_gate_adjustment": "NONE",
        },
        "e3_signoff_review": e3,
        "bb_signoff_review": bb,
        "loss_control_blockers": loss_control_blockers,
        "signoff_blockers": signoff_blockers,
        "authority_boundary_violation": authority_violation,
        "max_safe_next_action": (
            "PM_SUPERVISED_SAME_WINDOW_GATE_REVALIDATION_ONLY_NO_ORDER_FROM_THIS_PACKET"
            if status == APPROVED_NO_ORDER_STATUS
            else "COLLECT_E3_BB_SIGNOFF_ARTIFACTS_NO_ORDER"
            if status == SIGNOFF_REQUIRED_STATUS
            else "REPAIR_BLOCKED_INPUTS_NO_ORDER"
        ),
        "required_same_window_gates_before_order_capable_action": [
            "fresh_current_candidate_bounded_demo_authorization",
            "active_bounded_demo_decision_lease",
            "fresh_actual_admission_bbo_and_instrument_snapshot",
            "Guardian_NORMAL_and_Rust_authority_revalidated",
            "GUI_RiskConfig_cap_lineage_from_accepted_Demo_equity",
            "book_clean_pending_order_reconciliation",
            "candidate_matched_order_link_id_and_decision_lease_id",
            "auditability_and_reconstructability_packet",
        ],
        "answers": {
            "e3_bb_signoff_contract_ready": status
            in {SIGNOFF_REQUIRED_STATUS, APPROVED_NO_ORDER_STATUS},
            "e3_bb_review_approved_no_order": status == APPROVED_NO_ORDER_STATUS,
            "order_capable_action_allowed": False,
            "adapter_enablement_performed": False,
            "adapter_enabled_by_this_packet": False,
            "writer_enablement_performed": False,
            "writer_enabled": False,
            "decision_lease_acquire_performed": False,
            "decision_lease_release_performed": False,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "allowed_to_submit_order": False,
            "allowed_to_submit_order_in_current_review": False,
            "order_submission_performed": False,
            "order_cancel_performed": False,
            "order_modify_performed": False,
            "bybit_call_performed": False,
            "exchange_call_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "runtime_mutation_performed": False,
            "service_restart_performed": False,
            "cost_gate_lowering_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "risk_expansion": False,
            "live_authority_granted": False,
            "mainnet_authority_granted": False,
            "promotion_evidence": False,
            "promotion_proof": False,
            "profit_proof": False,
        },
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    candidate = _dict(packet.get("candidate"))
    answers = _dict(packet.get("answers"))
    lines = [
        "# Current Candidate E3/BB Enablement Review Contract",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Candidate: `{candidate.get('effective_side_cell_key')}`",
        f"- E3/BB approved no-order: `{answers.get('e3_bb_review_approved_no_order')}`",
        f"- Order-capable action allowed: `{answers.get('order_capable_action_allowed')}`",
        f"- Max safe next action: `{packet.get('max_safe_next_action')}`",
        "",
        "## Loss-Control Blockers",
    ]
    blockers = _list(packet.get("loss_control_blockers"))
    lines.extend(f"- `{blocker}`" for blocker in blockers) if blockers else lines.append("- none")
    lines.extend(["", "## Signoff Blockers"])
    signoff_blockers = _list(packet.get("signoff_blockers"))
    if signoff_blockers:
        lines.extend(f"- `{blocker}`" for blocker in signoff_blockers)
    else:
        lines.append("- none")
    lines.extend(["", "## Required Same-Window Gates Before Order"])
    for item in _list(packet.get("required_same_window_gates_before_order_capable_action")):
        lines.append(f"- `{item}`")
    lines.extend(["", "## Boundary", "", str(packet.get("boundary", ""))])
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order-enable-review-json", type=Path, required=True)
    parser.add_argument("--e3-signoff-json", type=Path)
    parser.add_argument("--bb-signoff-json", type=Path)
    parser.add_argument("--candidate-side-cell-key")
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
    packet = build_current_candidate_e3_bb_enablement_review_contract(
        order_enablement_review=_read_json(args.order_enable_review_json),
        e3_signoff=_read_json(args.e3_signoff_json),
        bb_signoff=_read_json(args.bb_signoff_json),
        candidate_side_cell_key=args.candidate_side_cell_key,
        now_utc=now,
        max_artifact_age_seconds=args.max_artifact_age_seconds,
        order_enablement_path=args.order_enable_review_json,
        e3_signoff_path=args.e3_signoff_json,
        bb_signoff_path=args.bb_signoff_json,
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
