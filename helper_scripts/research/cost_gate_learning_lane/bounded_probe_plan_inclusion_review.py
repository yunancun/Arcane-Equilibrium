#!/usr/bin/env python3
"""Build a no-order plan-inclusion review for a bounded Demo authorization.

The review consumes a timestamped bounded authorization packet plus the
candidate preflight/construction evidence and creates an inactive
``cost_gate_demo_learning_lane_plan_v1`` preview. It then dry-runs the existing
runtime adapter with the adapter gate disabled. The result is a review artifact,
not a plan write, not a ledger append, and not order authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from cost_gate_learning_lane.contract import (
    ADMIT_DECISION,
    BOUNDED_PROBE_AUTHORIZED_STATUS,
    BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SCHEMA_VERSION,
    ELIGIBLE_REJECT_REASON_CODE,
    ORDER_AUTHORITY_GRANTED,
)
from cost_gate_learning_lane.policy import DEMO_LEARNING_LANE_SCHEMA_VERSION
from cost_gate_learning_lane.runtime_adapter import (
    evaluate_probe_admission,
    read_jsonl_ledger,
)


PLAN_INCLUSION_REVIEW_SCHEMA_VERSION = (
    "bounded_demo_probe_authorization_plan_inclusion_review_v1"
)
READY_STATUS = "PLAN_INCLUSION_PREVIEW_READY_NO_ADMISSION"
DEFAULT_MAX_ARTIFACT_AGE_HOURS = 24
DEFAULT_COOLDOWN_MINUTES = 30
PREFLIGHT_READY_STATUS = "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION"
CONSTRUCTION_READY_STATUS = "CANDIDATE_CONSTRUCTION_PREVIEW_READY_NO_ORDER"
BOUNDARY = (
    "source-only plan inclusion review; no latest overwrite, plan mutation, "
    "ledger append, PG query/write, Bybit call, order/cancel/modify, service/"
    "env/crontab mutation, Rust writer, Cost Gate lowering, live authority, "
    "active runtime probe/order authority, or promotion proof"
)


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


def _age_seconds(value: Any, *, now_utc: dt.datetime) -> float | None:
    parsed = _parse_dt(value)
    if parsed is None:
        return None
    age = (now_utc - parsed).total_seconds()
    return age if age >= 0.0 else None


def _sha256(path: Path | None) -> str | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact_summary(
    *,
    name: str,
    path: Path | None,
    payload: dict[str, Any] | None,
    now_utc: dt.datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    present = isinstance(payload, dict) and bool(payload)
    generated_at = (payload or {}).get("generated_at_utc") if present else None
    age = _age_seconds(generated_at, now_utc=now_utc) if generated_at else None
    if not present:
        status = "MISSING"
    elif age is None:
        status = "PRESENT_UNKNOWN_AGE"
    elif age > max_age_seconds:
        status = "STALE"
    else:
        status = "FRESH"
    return {
        "name": name,
        "path": str(path) if path else None,
        "sha256": _sha256(path),
        "status": status,
        "present": present,
        "generated_at_utc": generated_at,
        "age_seconds": age,
        "max_age_seconds": max_age_seconds,
        "schema_version": (payload or {}).get("schema_version") if present else None,
    }


def _candidate_from_preflight(preflight: dict[str, Any]) -> dict[str, Any]:
    design = _dict(preflight.get("bounded_demo_probe_design"))
    candidate = _dict(preflight.get("candidate")) or _dict(design.get("candidate"))
    return dict(candidate)


def _candidate_from_preview(preview: dict[str, Any]) -> dict[str, Any]:
    return dict(_dict(preview.get("candidate")))


def _candidate_from_authorization(packet: dict[str, Any]) -> dict[str, Any]:
    return dict(_dict(packet.get("candidate")))


def _candidate_key(candidate: dict[str, Any]) -> tuple[Any, Any, Any, Any, Any]:
    return (
        candidate.get("side_cell_key"),
        candidate.get("strategy_name"),
        candidate.get("symbol"),
        candidate.get("side"),
        candidate.get("outcome_horizon_minutes"),
    )


def _candidate_aligned(*candidates: dict[str, Any]) -> bool:
    keys = [_candidate_key(candidate) for candidate in candidates]
    if any(not key[0] for key in keys):
        return False
    return len(set(keys)) == 1


def _answer_is_false_or_missing(answers: dict[str, Any], key: str) -> bool:
    return answers.get(key) in (None, False)


def _main_cost_gate_none(payload: dict[str, Any]) -> bool:
    answers = _dict(payload.get("answers"))
    return (
        payload.get("main_cost_gate_adjustment") in (None, "", "NONE")
        and answers.get("main_cost_gate_adjustment") in (None, "", "NONE")
    )


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
            "grant",
            "granted",
            "authorize",
            "authorized",
        }
    return False


def _recursive_authority_violation(payload: Any) -> str | None:
    danger_true_keys = {
        "active_runtime_probe_authority",
        "active_runtime_order_authority",
        "adapter_enabled_by_this_packet",
        "allowed_to_submit_order",
        "canonical_plan_mutation_performed",
        "ledger_append_performed",
        "live_authority_granted",
        "order_authority_granted",
        "order_cancel_performed",
        "order_modify_performed",
        "order_submission_performed",
        "pg_write_performed",
        "plan_mutation_performed",
        "probe_authority_granted",
        "promotion_evidence",
        "promotion_proof",
        "runtime_mutation_performed",
        "writer_enabled",
    }
    stack: list[Any] = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(node)
            continue
        if not isinstance(node, dict):
            continue
        for key, value in node.items():
            if key in danger_true_keys and _truthy(value):
                return key
            if key == "main_cost_gate_adjustment" and value not in (None, "", "NONE"):
                return key
            if key == "order_authority" and value not in (None, "", "NOT_GRANTED"):
                return key
            if isinstance(value, (dict, list)):
                stack.append(value)
    return None


def _auth_packet_hidden_authority_violation(packet: dict[str, Any]) -> str | None:
    packet_without_auth = {
        key: value
        for key, value in packet.items()
        if key != "operator_authorization"
    }
    return _recursive_authority_violation(packet_without_auth)


def _no_mutating_answers(payload: dict[str, Any]) -> bool:
    answers = _dict(payload.get("answers"))
    false_keys = {
        "active_runtime_probe_authority",
        "active_runtime_order_authority",
        "canonical_plan_mutation_performed",
        "ledger_append_performed",
        "live_authority_granted",
        "order_authority_granted",
        "order_cancel_performed",
        "order_modify_performed",
        "order_submission_performed",
        "pg_write_performed",
        "plan_mutation_performed",
        "probe_authority_granted",
        "promotion_evidence",
        "promotion_proof",
        "runtime_mutation_performed",
        "writer_enabled",
    }
    return (
        _recursive_authority_violation(payload) is None
        and _main_cost_gate_none(payload)
        and all(
            _answer_is_false_or_missing(answers, key) for key in false_keys
        )
    )


def _auth_packet_safe(packet: dict[str, Any], *, now_utc: dt.datetime) -> tuple[bool, str]:
    answers = _dict(packet.get("answers"))
    auth = _dict(packet.get("operator_authorization"))
    hidden_violation = _auth_packet_hidden_authority_violation(packet)
    if hidden_violation is not None:
        return False, f"authorization_packet_hidden_authority_violation:{hidden_violation}"
    if packet.get("status") != BOUNDED_PROBE_AUTHORIZED_STATUS:
        return False, "authorization_packet_not_authorized"
    if answers.get("operator_authorization_object_emitted") is not True:
        return False, "authorization_object_missing"
    for key in (
        "active_runtime_probe_authority",
        "active_runtime_order_authority",
        "plan_mutation_performed",
        "writer_enabled",
        "order_submission_performed",
        "runtime_mutation_performed",
        "global_cost_gate_lowering_recommended",
        "promotion_evidence",
    ):
        if answers.get(key) is not False:
            return False, f"authorization_packet_active_or_mutating:{key}"
    if answers.get("main_cost_gate_adjustment") != "NONE":
        return False, "authorization_packet_cost_gate_adjustment_not_none"
    if auth.get("schema_version") != BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SCHEMA_VERSION:
        return False, "operator_authorization_schema_mismatch"
    if auth.get("status") != BOUNDED_PROBE_AUTHORIZED_STATUS:
        return False, "operator_authorization_status_not_authorized"
    if auth.get("side_cell_key") != _dict(packet.get("candidate")).get("side_cell_key"):
        return False, "operator_authorization_side_cell_mismatch"
    if auth.get("main_cost_gate_adjustment") != "NONE":
        return False, "operator_authorization_cost_gate_adjustment_not_none"
    if auth.get("order_authority") != ORDER_AUTHORITY_GRANTED:
        return False, "operator_authorization_order_authority_mismatch"
    if auth.get("probe_authority_granted") is not True:
        return False, "operator_authorization_probe_authority_not_granted"
    if auth.get("order_authority_granted") is not True:
        return False, "operator_authorization_order_authority_not_granted"
    if auth.get("promotion_evidence") is not False:
        return False, "operator_authorization_promotion_boundary_invalid"
    expires_at = _parse_dt(auth.get("expires_at_utc"))
    if expires_at is None:
        return False, "operator_authorization_expiry_missing_or_malformed"
    if expires_at <= now_utc:
        return False, "operator_authorization_expired"
    return True, "operator_authorization_valid"


def _sanitized_hypothetical_decision(decision: dict[str, Any] | None) -> dict[str, Any] | None:
    if decision is None:
        return None
    would_admit = decision.get("decision") == ADMIT_DECISION
    return {
        "schema_version": decision.get("schema_version"),
        "generated_at_utc": decision.get("generated_at_utc"),
        "decision": decision.get("decision"),
        "reason": decision.get("reason"),
        "side_cell_key": decision.get("side_cell_key"),
        "would_admit_if_adapter_enabled": would_admit,
        "allowed_to_submit_order_in_current_review": False,
        "raw_allowed_to_submit_order_redacted": True,
        "boundary": "hypothetical summary only; no current order allowance emitted",
    }


def _preflight_ready(preflight: dict[str, Any]) -> bool:
    answers = _dict(preflight.get("answers"))
    return (
        preflight.get("schema_version")
        == "cost_gate_false_negative_bounded_demo_probe_preflight_v1"
        and preflight.get("status") == PREFLIGHT_READY_STATUS
        and answers.get("ready_for_operator_bounded_demo_probe_authorization") is True
        and _no_mutating_answers(preflight)
    )


def _construction_ready(preview: dict[str, Any]) -> bool:
    answers = _dict(preview.get("answers"))
    construction = _dict(preview.get("construction"))
    return (
        preview.get("schema_version") == "bounded_demo_probe_candidate_construction_preview_v1"
        and preview.get("status") == CONSTRUCTION_READY_STATUS
        and construction.get("constructible") is True
        and not _list(preview.get("blocking_gates"))
        and _no_mutating_answers(preview)
        and answers.get("candidate_construction_preview_ready_no_order") is True
    )


def _build_plan_preview(
    *,
    preflight: dict[str, Any],
    preview: dict[str, Any],
    authorization_packet: dict[str, Any],
    now_utc: dt.datetime,
    cooldown_minutes: int,
) -> dict[str, Any]:
    candidate = _candidate_from_preflight(preflight)
    design = _dict(preflight.get("bounded_demo_probe_design"))
    limits = _dict(design.get("suggested_initial_probe_limits"))
    construction = _dict(preview.get("construction"))
    auth = _dict(authorization_packet.get("operator_authorization"))
    max_orders = min(
        max(1, _int(limits.get("max_probe_intents_before_review"), 1)),
        max(1, _int(auth.get("max_authorized_probe_orders"), 1)),
    )
    horizon = _int(candidate.get("outcome_horizon_minutes"), 60)
    return {
        "schema_version": DEMO_LEARNING_LANE_SCHEMA_VERSION,
        "generated_at_utc": now_utc.isoformat(),
        "status": "READY_FOR_DEMO_LEARNING_PROBE",
        "gate_status": "OPERATOR_REVIEW",
        "policy": "artifact_only_demo_learning_probe_plan_no_order_authority",
        "main_cost_gate_adjustment": "NONE",
        "learning_gate_adjustment": "SIDE_CELL_DEMO_PROBE_ONLY_AFTER_ADAPTER_WIRING",
        "order_authority": ORDER_AUTHORITY_GRANTED,
        "operator_authorization": auth,
        "source": {
            "preflight_status": preflight.get("status"),
            "authorization_packet_status": authorization_packet.get("status"),
            "construction_preview_status": preview.get("status"),
            "construction_limit_price": construction.get("limit_price"),
            "construction_rounded_qty": construction.get("rounded_qty"),
            "construction_rounded_notional_usdt": construction.get("rounded_notional_usdt"),
        },
        "selected_probe_candidate_count": 1,
        "probe_candidates": [
            {
                "side_cell_key": candidate.get("side_cell_key"),
                "strategy_name": candidate.get("strategy_name"),
                "symbol": candidate.get("symbol"),
                "side": candidate.get("side"),
                "source_kind": candidate.get("source_kind"),
                "reject_reason_code": ELIGIBLE_REJECT_REASON_CODE,
                "outcome_horizon_minutes": horizon,
                "probe_proposal": {
                    "mode": "demo_only_learning_probe",
                    "max_probe_orders": max_orders,
                    "cooldown_minutes": cooldown_minutes,
                    "outcome_horizon_minutes": horizon,
                    "learning_outcome_horizon_minutes": horizon,
                    "requires_runtime_policy_adapter": True,
                    "requires_probe_attempt_logging": True,
                    "requires_probe_outcome_logging": True,
                    "requires_candidate_horizon_outcome_logging": True,
                },
                "guardrails": {
                    "main_cost_gate_adjustment": "NONE",
                    "may_bypass_main_live_gate": False,
                    "demo_only": True,
                    "paper_not_promotion_evidence": True,
                    "notional_or_qty_not_granted_by_artifact": True,
                    "max_demo_notional_usdt_per_order": construction.get("cap_usdt"),
                    "placement_mode": construction.get("placement_mode"),
                },
            }
        ],
        "required_runtime_wiring": [
            "separate_pm_e3_review_before_plan_or_latest_propagation",
            "do_not_use_drifted_authorization_latest_for_this_candidate",
            "runtime_adapter_must_remain_disabled_until_explicit_admission_gate",
            "record_candidate_matched_attempt_fill_fee_slippage_lineage_after_any_probe",
        ],
        "stop_conditions": _list(design.get("stop_conditions")),
        "boundary": "inactive preview only; not written to runtime plan/latest and not order authority",
    }


def _event_for_candidate(candidate: dict[str, Any], *, now_utc: dt.datetime) -> dict[str, Any]:
    ts_ms = int(now_utc.timestamp() * 1000)
    return {
        "strategy_name": candidate.get("strategy_name"),
        "symbol": candidate.get("symbol"),
        "side": candidate.get("side"),
        "reject_reason_code": ELIGIBLE_REJECT_REASON_CODE,
        "engine_mode": "live_demo",
        "ts_ms": ts_ms,
        "context_id": f"plan-preview-{candidate.get('symbol')}-{ts_ms}",
        "signal_id": f"plan-preview-signal-{candidate.get('symbol')}-{ts_ms}",
    }


def _status_from_failed(failed: list[str]) -> str:
    if not failed:
        return READY_STATUS
    first = failed[0]
    return {
        "preflight_ready": "PREFLIGHT_NOT_READY",
        "construction_preview_ready": "CONSTRUCTION_PREVIEW_NOT_READY",
        "authorization_packet_safe": "AUTHORIZATION_PACKET_NOT_READY",
        "candidate_alignment": "CANDIDATE_ALIGNMENT_MISMATCH",
        "inactive_adapter_gate": "INACTIVE_ADMISSION_DRY_RUN_NOT_BLOCKED_AS_EXPECTED",
        "hypothetical_adapter_gate": "HYPOTHETICAL_ADMISSION_NOT_READY",
    }.get(first, "PLAN_INCLUSION_PREVIEW_NOT_READY")


def build_plan_inclusion_review(
    *,
    preflight: dict[str, Any] | None,
    construction_preview: dict[str, Any] | None,
    authorization_packet: dict[str, Any] | None,
    ledger_rows: list[dict[str, Any]] | None = None,
    paths: dict[str, Path | None] | None = None,
    now_utc: dt.datetime | None = None,
    max_artifact_age_hours: int = DEFAULT_MAX_ARTIFACT_AGE_HOURS,
    cooldown_minutes: int = DEFAULT_COOLDOWN_MINUTES,
    risk_state: str = "NORMAL",
) -> dict[str, Any]:
    if max_artifact_age_hours < 1 or max_artifact_age_hours > 24 * 14:
        raise ValueError("max_artifact_age_hours must be in [1, 336]")
    if cooldown_minutes < 0 or cooldown_minutes > 24 * 60:
        raise ValueError("cooldown_minutes must be in [0, 1440]")
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    max_age_seconds = max_artifact_age_hours * 3600
    paths = paths or {}
    preflight_payload = _dict(preflight)
    preview_payload = _dict(construction_preview)
    auth_payload = _dict(authorization_packet)
    artifacts = {
        "preflight": _artifact_summary(
            name="preflight",
            path=paths.get("preflight"),
            payload=preflight_payload,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        ),
        "construction_preview": _artifact_summary(
            name="construction_preview",
            path=paths.get("construction_preview"),
            payload=preview_payload,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        ),
        "authorization_packet": _artifact_summary(
            name="authorization_packet",
            path=paths.get("authorization_packet"),
            payload=auth_payload,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        ),
    }

    auth_safe, auth_reason = _auth_packet_safe(auth_payload, now_utc=now)
    candidates = {
        "preflight": _candidate_from_preflight(preflight_payload),
        "construction_preview": _candidate_from_preview(preview_payload),
        "authorization_packet": _candidate_from_authorization(auth_payload),
    }
    aligned = _candidate_aligned(*candidates.values())

    gates = {
        "preflight_ready": (
            artifacts["preflight"]["status"] == "FRESH" and _preflight_ready(preflight_payload)
        ),
        "construction_preview_ready": (
            artifacts["construction_preview"]["status"] == "FRESH"
            and _construction_ready(preview_payload)
        ),
        "authorization_packet_safe": (
            artifacts["authorization_packet"]["status"] == "FRESH" and auth_safe
        ),
        "candidate_alignment": aligned,
    }
    plan_preview: dict[str, Any] | None = None
    inactive_decision: dict[str, Any] | None = None
    hypothetical_decision: dict[str, Any] | None = None
    if all(gates.values()):
        plan_preview = _build_plan_preview(
            preflight=preflight_payload,
            preview=preview_payload,
            authorization_packet=auth_payload,
            now_utc=now,
            cooldown_minutes=cooldown_minutes,
        )
        event = _event_for_candidate(candidates["preflight"], now_utc=now)
        rows = ledger_rows or []
        inactive_decision = evaluate_probe_admission(
            plan_preview,
            event,
            ledger_rows=rows,
            now_utc=now,
            adapter_enabled=False,
            risk_state=risk_state,
        )
        hypothetical_decision = evaluate_probe_admission(
            plan_preview,
            event,
            ledger_rows=rows,
            now_utc=now,
            adapter_enabled=True,
            risk_state=risk_state,
        )
        gates["inactive_adapter_gate"] = inactive_decision.get("decision") == "ADAPTER_DISABLED"
        gates["hypothetical_adapter_gate"] = (
            hypothetical_decision.get("decision") == ADMIT_DECISION
        )
    failed = [name for name, passed in gates.items() if passed is not True]
    status = _status_from_failed(failed)
    return {
        "schema_version": PLAN_INCLUSION_REVIEW_SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": ";".join(failed) if failed else "inactive_plan_preview_ready_no_admission",
        "review_scope": "source_only_plan_inclusion_preview_not_runtime_admission",
        "candidate": candidates["preflight"],
        "candidate_alignment": {
            "aligned": aligned,
            "candidates": candidates,
        },
        "gates": gates,
        "authorization_packet_validation_reason": auth_reason,
        "plan_preview": plan_preview,
        "inactive_adapter_decision": inactive_decision,
        "hypothetical_adapter_enabled_decision": _sanitized_hypothetical_decision(
            hypothetical_decision
        ),
        "hypothetical_only": True,
        "next_actions": (
            [
                "pm_e3_review_before_any_runtime_plan_or_latest_propagation",
                "do_not_copy_timestamped_authorization_into_latest_as_shortcut",
                "if_runtime_admission_is_approved_then_use_rust_authority_path_and_candidate_matched_lineage",
            ]
            if status == READY_STATUS
            else ["repair_failed_gate_before_runtime_propagation_review"]
        ),
        "answers": {
            "plan_inclusion_preview_ready": status == READY_STATUS,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "adapter_enabled_by_this_packet": False,
            "latest_overwrite_performed": False,
            "plan_mutation_performed": False,
            "ledger_append_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "bybit_call_performed": False,
            "order_submission_performed": False,
            "order_cancel_performed": False,
            "order_modify_performed": False,
            "service_restart_performed": False,
            "runtime_mutation_performed": False,
            "writer_enabled": False,
            "main_cost_gate_adjustment": "NONE",
            "global_cost_gate_lowering_recommended": False,
            "live_authority_granted": False,
            "promotion_evidence": False,
        },
        "artifacts": artifacts,
        "boundary": BOUNDARY,
    }


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def render_markdown(review: dict[str, Any]) -> str:
    candidate = _dict(review.get("candidate"))
    inactive = _dict(review.get("inactive_adapter_decision"))
    hypothetical = _dict(review.get("hypothetical_adapter_enabled_decision"))
    lines = [
        "# Bounded Probe Plan Inclusion Review",
        "",
        f"- Generated: `{review.get('generated_at_utc')}`",
        f"- Status: `{review.get('status')}`",
        f"- Reason: `{review.get('reason')}`",
        f"- Side-cell: `{candidate.get('side_cell_key')}`",
        f"- Inactive adapter decision: `{inactive.get('decision')}`",
        f"- Hypothetical adapter-enabled decision: `{hypothetical.get('decision')}`",
        f"- Boundary: {review.get('boundary')}",
        "",
        "## Gates",
        "",
    ]
    for name, passed in _dict(review.get("gates")).items():
        lines.append(f"- `{name}`: `{passed}`")
    lines.extend(["", "## Next Actions", ""])
    for action in _list(review.get("next_actions")):
        lines.append(f"- `{action}`")
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-json", type=Path, required=True)
    parser.add_argument("--construction-preview-json", type=Path, required=True)
    parser.add_argument("--authorization-packet-json", type=Path, required=True)
    parser.add_argument("--ledger-jsonl", type=Path)
    parser.add_argument("--risk-state", default="NORMAL")
    parser.add_argument("--cooldown-minutes", type=int, default=DEFAULT_COOLDOWN_MINUTES)
    parser.add_argument("--max-artifact-age-hours", type=int, default=DEFAULT_MAX_ARTIFACT_AGE_HOURS)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    ledger_rows = read_jsonl_ledger(args.ledger_jsonl) if args.ledger_jsonl else []
    review = build_plan_inclusion_review(
        preflight=_read_json(args.preflight_json),
        construction_preview=_read_json(args.construction_preview_json),
        authorization_packet=_read_json(args.authorization_packet_json),
        ledger_rows=ledger_rows,
        paths={
            "preflight": args.preflight_json,
            "construction_preview": args.construction_preview_json,
            "authorization_packet": args.authorization_packet_json,
        },
        max_artifact_age_hours=args.max_artifact_age_hours,
        cooldown_minutes=args.cooldown_minutes,
        risk_state=args.risk_state,
    )
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(review, ensure_ascii=False, indent=2, sort_keys=True, default=str)
            + "\n",
            encoding="utf-8",
        )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render_markdown(review), encoding="utf-8")
    if args.print_json or not args.json_output and not args.output:
        print(json.dumps(review, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
