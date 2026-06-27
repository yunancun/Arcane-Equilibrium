#!/usr/bin/env python3
"""Review a current-candidate standing Demo loss-control envelope.

The packet converts the standing Demo operating permission into a
candidate-scoped ``standing_demo_operator_authorization_v1`` preview for the
current candidate. It consumes the current admission review, current GUI cap
envelope, and false-negative candidate packet so the proposed standing envelope
is tied to the GUI/Rust risk source of truth instead of a local 10 USDT
diagnostic cap.

This helper is source-only: it does not write the runtime standing envelope,
mutate env/crontab, emit bounded authorization, create a Decision Lease, pass
Guardian/Rust gates, call Bybit, submit orders, lower Cost Gate, or create
profit proof.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from cost_gate_learning_lane.contract import (
    STANDING_DEMO_AUTHORIZATION_ACTIVE_STATUS,
    STANDING_DEMO_AUTHORIZATION_SCHEMA_VERSION,
)
from cost_gate_learning_lane.standing_demo_authorization import (
    summarize_standing_demo_authorization,
)


SCHEMA_VERSION = "current_candidate_standing_demo_loss_control_envelope_review_v1"
ADMISSION_REVIEW_SCHEMA_VERSION = (
    "current_candidate_bounded_demo_admission_envelope_review_v1"
)
CURRENT_ENVELOPE_SCHEMA_VERSION = "cost_gate_current_candidate_no_order_refresh_envelope_v1"
FALSE_NEGATIVE_CANDIDATE_PACKET_SCHEMA_VERSION = (
    "cost_gate_false_negative_candidate_packet_v1"
)

ADMISSION_BLOCKED_STATUS = (
    "CURRENT_CANDIDATE_BOUNDED_DEMO_ADMISSION_BLOCKED_BY_LOSS_CONTROL"
)
CURRENT_ENVELOPE_READY_STATUS = (
    "CURRENT_CANDIDATE_NO_ORDER_REFRESH_ENVELOPE_READY_NO_CAPTURE_NO_AUTHORITY"
)
FALSE_NEGATIVE_PACKET_READY_STATUS = (
    "COST_GATE_FALSE_NEGATIVE_CANDIDATES_READY_FOR_OPERATOR_REVIEW"
)

READY_STATUS = (
    "CURRENT_CANDIDATE_STANDING_DEMO_LOSS_CONTROL_ENVELOPE_READY_NO_RUNTIME_MUTATION"
)
NOT_READY_STATUS = "CURRENT_CANDIDATE_STANDING_DEMO_LOSS_CONTROL_ENVELOPE_NOT_READY"
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

DEFAULT_OPERATOR_ID = "current-candidate-standing-demo-loss-control-review"
DEFAULT_RUNTIME_ENVELOPE_PATH = Path(
    "/tmp/openclaw/cost_gate_learning_lane/standing_demo_operator_authorization.json"
)
DEFAULT_ENV_VAR = "OPENCLAW_COST_GATE_STANDING_DEMO_AUTHORIZATION_JSON"
ALLOWED_ENV_VARS = {DEFAULT_ENV_VAR}
ALLOWED_RUNTIME_ROOTS = (Path("/tmp/openclaw/cost_gate_learning_lane"),)
DEFAULT_MAX_ARTIFACT_AGE_SECONDS = 6 * 60 * 60
DEFAULT_AUTHORIZATION_TTL_HOURS = 12
DEFAULT_MAX_AUTHORIZATION_TTL_HOURS = 24
DEFAULT_MAX_AUTHORIZED_PROBE_ORDERS = 2
HARD_MAX_AUTHORIZED_PROBE_ORDERS = 3
GUI_CAP_SOURCE = "current_candidate_envelope.cap_resolution.resolved_cap_usdt"
GUI_RISK_SOURCE = "GUI-backed Rust RiskConfig"

AUTHORITY_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "adapter_enabled_by_this_packet",
    "allowed_to_submit_order",
    "bounded_demo_probe_authorized",
    "bybit_call_performed",
    "bybit_private_call_performed",
    "cap_envelope_mutation_allowed",
    "cap_mutation_performed",
    "config_mutation_performed",
    "cost_gate_lowering_performed",
    "cost_gate_lowering_recommended",
    "crontab_mutation_performed",
    "env_mutation_performed",
    "exchange_call_performed",
    "freshness_gate_lowering_recommended",
    "global_cost_gate_lowering_recommended",
    "ledger_append_performed",
    "live_authority_granted",
    "mainnet_authority_granted",
    "operator_authorization_object_emitted",
    "order_admission_ready",
    "order_authority_granted",
    "order_cancel_performed",
    "order_modify_performed",
    "order_submission_performed",
    "pg_query_performed",
    "pg_write_performed",
    "placement_call_performed",
    "plan_mutation_performed",
    "probe_authority_granted",
    "promotion_evidence",
    "promotion_proof",
    "risk_mutation_performed",
    "runtime_admission_ready",
    "runtime_mutation_performed",
    "service_restart_performed",
    "standing_envelope_materialized",
    "writer_enabled",
}

BOUNDARY = (
    "source-only current-candidate standing Demo loss-control envelope review; "
    "no runtime file write, env/crontab mutation, bounded authorization object, "
    "Decision Lease, Guardian/Rust authority grant, Bybit/private/order call, "
    "order/cancel/modify, PG write, Cost Gate lowering, live/mainnet authority, "
    "promotion proof, or profit proof"
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
            "ready",
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


def _generated_at(payload: dict[str, Any]) -> Any:
    return payload.get("generated_at_utc") or payload.get("generated") or payload.get(
        "ts_utc"
    )


def _sha256(path: Path | None) -> str | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
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


def _artifact_summary(
    *,
    name: str,
    path: Path | None,
    payload: dict[str, Any],
    now_utc: dt.datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    present = bool(payload)
    generated_at = _generated_at(payload) if present else None
    parsed = _parse_dt(generated_at) if generated_at else None
    age: float | None = None
    if parsed is not None:
        age = (now_utc - parsed).total_seconds()
    if not present:
        status = "MISSING"
    elif parsed is None:
        status = "PRESENT_UNKNOWN_AGE"
    elif age is not None and age < -60:
        status = "FROM_FUTURE"
    elif age is not None and age > max_age_seconds:
        status = "STALE"
    else:
        status = "FRESH"
    return {
        "name": name,
        "path": str(path) if path else None,
        "sha256": _sha256(path),
        "status": status,
        "present": present,
        "schema_version": payload.get("schema_version") if present else None,
        "artifact_status": payload.get("status") if present else None,
        "generated_at_utc": generated_at,
        "age_seconds": round(age, 3) if age is not None else None,
        "max_age_seconds": max_age_seconds,
    }


def _candidate_identity(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "side_cell_key": candidate.get("side_cell_key"),
        "strategy_name": candidate.get("strategy_name"),
        "symbol": candidate.get("symbol"),
        "side": candidate.get("side"),
        "outcome_horizon_minutes": candidate.get("outcome_horizon_minutes"),
    }


def _candidate_from_false_negative_row(row: dict[str, Any]) -> dict[str, Any]:
    strategies = _list(row.get("strategy_names"))
    symbols = _list(row.get("symbols"))
    sides = _list(row.get("sides"))
    horizons = _list(row.get("horizon_minutes"))
    return {
        "side_cell_key": row.get("side_cell_key"),
        "strategy_name": strategies[0] if strategies else None,
        "symbol": symbols[0] if symbols else None,
        "side": sides[0] if sides else None,
        "outcome_horizon_minutes": (
            row.get("dominant_horizon_minutes") or (horizons[0] if horizons else None)
        ),
    }


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


def _recursive_authority_violations(payload: Any, prefix: str = "") -> list[str]:
    reasons: list[str] = []
    if isinstance(payload, list):
        for idx, item in enumerate(payload):
            reasons.extend(_recursive_authority_violations(item, f"{prefix}[{idx}]"))
        return reasons
    if not isinstance(payload, dict):
        return reasons
    for key, value in payload.items():
        path = f"{prefix}.{key}" if prefix else key
        if key in AUTHORITY_TRUE_KEYS and _truthy(value):
            reasons.append(f"{path}_true")
        if key == "main_cost_gate_adjustment" and value not in (None, "", "NONE"):
            reasons.append(f"{path}_not_none")
        if key == "order_authority" and value not in (None, "", "NOT_GRANTED"):
            reasons.append(f"{path}_not_not_granted")
        if isinstance(value, (dict, list)):
            reasons.extend(_recursive_authority_violations(value, path))
    return reasons


def _same_number(left: Any, right: Any, tolerance: float = 1e-8) -> bool:
    left_num = _float(left)
    right_num = _float(right)
    return (
        left_num is not None
        and right_num is not None
        and abs(left_num - right_num) <= tolerance
    )


def _select_false_negative_candidate(
    packet: dict[str, Any],
    *,
    side_cell_key: str,
) -> tuple[dict[str, Any], str]:
    rows = _list(packet.get("ranked_false_negative_candidates"))
    for row in rows:
        item = _dict(row)
        if item.get("side_cell_key") == side_cell_key:
            return item, "selected_by_current_candidate_side_cell"
    return {}, "current_candidate_not_found_in_ranked_false_negative_candidates"


def _packet_reasons(packet: dict[str, Any], artifact: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if artifact.get("status") != "FRESH":
        reasons.append("false_negative_candidate_packet_not_fresh")
    if packet.get("schema_version") != FALSE_NEGATIVE_CANDIDATE_PACKET_SCHEMA_VERSION:
        reasons.append("false_negative_candidate_packet_schema_invalid")
    if packet.get("status") != FALSE_NEGATIVE_PACKET_READY_STATUS:
        reasons.append("false_negative_candidate_packet_status_not_ready")
    answers = _dict(packet.get("answers"))
    if answers.get("operator_review_ready") is not True:
        reasons.append("false_negative_candidate_packet_operator_review_not_ready")
    if answers.get("global_cost_gate_lowering_recommended") is not False:
        reasons.append("false_negative_candidate_packet_cost_gate_lowering_not_false")
    return sorted(set(reasons))


def _candidate_review_reasons(row: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not row:
        reasons.append("current_candidate_not_found_in_packet")
        return reasons
    if row.get("candidate_class") != "false_negative_after_cost":
        reasons.append("selected_candidate_not_false_negative_after_cost")
    if row.get("status") != "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE":
        reasons.append("selected_candidate_status_not_review_candidate")
    if row.get("operator_review_required") is not True:
        reasons.append("selected_candidate_operator_review_not_required")
    for key in (
        "global_cost_gate_lowering_recommended",
        "probe_authority_granted",
        "order_authority_granted",
        "promotion_evidence",
    ):
        if row.get(key) is not False:
            reasons.append(f"selected_candidate_{key}_not_false")
    return sorted(set(reasons))


def _cap_lineage_reasons(
    *,
    admission_review: dict[str, Any],
    current_envelope: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    risk = _dict(admission_review.get("risk_semantics"))
    cap_resolution = _dict(current_envelope.get("cap_resolution"))
    summary = _dict(current_envelope.get("summary"))
    admission_cap = _float(risk.get("resolved_cap_usdt"))
    envelope_cap = _float(cap_resolution.get("resolved_cap_usdt"))
    rounded_notional = _float(risk.get("rounded_notional_usdt"))
    per_trade_fraction = _float(cap_resolution.get("per_trade_risk_pct_fraction"))
    per_trade_display = _float(cap_resolution.get("per_trade_risk_pct_display"))
    if risk.get("cap_source") != GUI_CAP_SOURCE:
        reasons.append("admission_review_cap_source_not_gui_resolved_cap")
    if risk.get("gui_risk_config_is_source_of_truth") is not True:
        reasons.append("admission_review_gui_risk_not_source_of_truth")
    if risk.get("local_10_usdt_cap_is_global_risk_authority") is not False:
        reasons.append("admission_review_local_10_usdt_marked_authority")
    if risk.get("bounded_probe_local_cap_usdt_is_authority") is not False:
        reasons.append("admission_review_bounded_local_cap_marked_authority")
    if cap_resolution.get("risk_source_of_truth") != GUI_RISK_SOURCE:
        reasons.append("current_envelope_risk_source_not_gui_rust")
    if cap_resolution.get("gui_risk_config_is_authority") is not True:
        reasons.append("current_envelope_gui_risk_not_authority")
    if cap_resolution.get("bounded_probe_local_cap_usdt_is_authority") is not False:
        reasons.append("current_envelope_bounded_local_cap_marked_authority")
    if summary.get("local_10_usdt_cap_is_global_risk_authority") is not False:
        reasons.append("current_envelope_local_10_usdt_marked_authority")
    if cap_resolution.get("account_equity_artifact_accepted") is not True:
        reasons.append("account_equity_artifact_not_accepted")
    if admission_cap is None or admission_cap <= 0:
        reasons.append("admission_resolved_cap_missing_or_non_positive")
    if envelope_cap is None or envelope_cap <= 0:
        reasons.append("current_envelope_resolved_cap_missing_or_non_positive")
    if admission_cap is not None and envelope_cap is not None and not _same_number(
        admission_cap, envelope_cap
    ):
        reasons.append("admission_cap_mismatch_current_envelope_cap")
    if (
        rounded_notional is not None
        and admission_cap is not None
        and rounded_notional > admission_cap + 1e-8
    ):
        reasons.append("rounded_notional_exceeds_gui_resolved_cap")
    if per_trade_fraction is None or per_trade_fraction <= 0:
        reasons.append("per_trade_risk_pct_fraction_missing_or_non_positive")
    elif per_trade_fraction > 1:
        reasons.append("per_trade_risk_pct_fraction_not_fraction")
    if (
        per_trade_fraction is not None
        and per_trade_display is not None
        and abs((per_trade_fraction * 100.0) - per_trade_display) > 1e-6
    ):
        reasons.append("per_trade_risk_pct_display_fraction_mismatch")
    return sorted(set(reasons))


def _source_contract_reasons(
    *,
    admission_review: dict[str, Any],
    current_envelope: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if admission_review.get("schema_version") != ADMISSION_REVIEW_SCHEMA_VERSION:
        reasons.append("admission_review_schema_invalid")
    if admission_review.get("status") != ADMISSION_BLOCKED_STATUS:
        reasons.append("admission_review_status_not_loss_control_blocked")
    if _dict(admission_review.get("answers")).get("review_contract_ready") is not True:
        reasons.append("admission_review_contract_not_ready")
    if _dict(admission_review.get("answers")).get("runtime_admission_ready") is not False:
        reasons.append("admission_review_runtime_admission_not_false")
    if _dict(admission_review.get("answers")).get("order_admission_ready") is not False:
        reasons.append("admission_review_order_admission_not_false")
    if current_envelope.get("schema_version") != CURRENT_ENVELOPE_SCHEMA_VERSION:
        reasons.append("current_envelope_schema_invalid")
    if current_envelope.get("status") != CURRENT_ENVELOPE_READY_STATUS:
        reasons.append("current_envelope_status_not_ready")
    if _dict(current_envelope.get("answers")).get("order_admission_ready") is not False:
        reasons.append("current_envelope_order_admission_not_false")
    return sorted(set(reasons))


def _validate_output_path(path: Path) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        return False, ["runtime_envelope_path_unresolvable"]
    if resolved.name != "standing_demo_operator_authorization.json":
        reasons.append("runtime_envelope_filename_invalid")
    allowed_roots = [root.expanduser().resolve() for root in ALLOWED_RUNTIME_ROOTS]
    if not any(resolved.is_relative_to(root) for root in allowed_roots):
        reasons.append("runtime_envelope_path_outside_allowed_root")
    return not reasons, reasons


def _validate_limits(
    *,
    max_authorized_probe_orders: int,
    authorization_ttl_hours: int,
    max_authorization_ttl_hours: int,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if max_authorized_probe_orders < 1:
        reasons.append("max_authorized_probe_orders_must_be_positive")
    if max_authorized_probe_orders > HARD_MAX_AUTHORIZED_PROBE_ORDERS:
        reasons.append("max_authorized_probe_orders_exceeds_hard_cap")
    if authorization_ttl_hours < 1:
        reasons.append("authorization_ttl_hours_must_be_positive")
    if max_authorization_ttl_hours < 1 or max_authorization_ttl_hours > 24 * 7:
        reasons.append("max_authorization_ttl_hours_out_of_supported_range")
    if authorization_ttl_hours > max_authorization_ttl_hours:
        reasons.append("authorization_ttl_exceeds_validator_max_ttl")
    return not reasons, reasons


def _standing_authorization_id(
    *,
    candidate_scope: dict[str, Any],
    now_utc: dt.datetime,
) -> str:
    seed = json.dumps(candidate_scope, sort_keys=True, default=str) + now_utc.isoformat()
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return f"standing-demo-current-candidate-{now_utc:%Y%m%dT%H%M%SZ}-{digest}"


def _envelope_preview(
    *,
    candidate_scope: dict[str, Any],
    operator_id: str,
    max_authorized_probe_orders: int,
    expires_at_utc: dt.datetime,
    now_utc: dt.datetime,
    risk_cap_lineage: dict[str, Any],
    source_refs: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": STANDING_DEMO_AUTHORIZATION_SCHEMA_VERSION,
        "generated_at_utc": now_utc.isoformat(),
        "status": STANDING_DEMO_AUTHORIZATION_ACTIVE_STATUS,
        "standing_authorization_id": _standing_authorization_id(
            candidate_scope=candidate_scope,
            now_utc=now_utc,
        ),
        "operator_id": operator_id,
        "environment": "demo",
        "scope": "demo_api_only_bounded_probe",
        "demo_only": True,
        "candidate_scoping_required": True,
        "candidate": candidate_scope,
        "risk_cap_lineage": risk_cap_lineage,
        "source_refs": source_refs,
        "max_authorized_probe_orders_per_candidate": max_authorized_probe_orders,
        "expires_at_utc": expires_at_utc.isoformat(),
        "answers": {
            "demo_only": True,
            "candidate_scoping_required": True,
            "live_authority_granted": False,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "bounded_demo_probe_authorized": False,
            "operator_authorization_object_emitted": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
            "promotion_proof": False,
            "runtime_mutation_performed": False,
            "env_mutation_performed": False,
            "crontab_mutation_performed": False,
            "order_submission_performed": False,
        },
    }


def _gate(
    name: str,
    passed: bool,
    reason: str,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "passed": passed,
        "reason": reason,
        "evidence": evidence or {},
    }


def _materialization_plan(
    *,
    path: Path,
    env_var: str,
    candidate_scope: dict[str, Any],
    risk_cap_lineage: dict[str, Any],
    max_authorized_probe_orders: int,
    authorization_ttl_hours: int,
    max_authorization_ttl_hours: int,
) -> dict[str, Any]:
    return {
        "source_only_review": True,
        "runtime_mutation_performed_by_this_helper": False,
        "standing_envelope_materialized_by_this_helper": False,
        "proposed_runtime_envelope_path": str(path),
        "proposed_file_mode": "0600",
        "proposed_env_var": env_var,
        "proposed_env_assignment": f"{env_var}={path}",
        "candidate_scope": candidate_scope,
        "risk_cap_lineage": risk_cap_lineage,
        "loss_control_limits": {
            "demo_only": True,
            "max_authorized_probe_orders_per_candidate": max_authorized_probe_orders,
            "hard_max_authorized_probe_orders_per_candidate": HARD_MAX_AUTHORIZED_PROBE_ORDERS,
            "authorization_ttl_hours": authorization_ttl_hours,
            "max_authorization_ttl_hours": max_authorization_ttl_hours,
            "cost_gate_adjustment": "NONE",
        },
        "future_apply_steps_require_review": [
            "write envelope_preview atomically at proposed_runtime_envelope_path with mode 0600",
            "do not set bounded authorization decision to authorize",
            "refresh false-negative review/preflight with decision defer and verify no order/probe authority",
            "rerun current_candidate_bounded_demo_admission_envelope_review before any order-capable action",
        ],
        "rollback_plan": [
            f"remove {env_var} env/crontab wiring if added",
            f"move or delete {path} after recording sha256 and review id",
            "refresh scheduled artifacts with default defer and confirm no-authority",
        ],
    }


def build_current_candidate_standing_demo_loss_control_envelope_review(
    *,
    admission_review: dict[str, Any] | None,
    current_envelope: dict[str, Any] | None,
    false_negative_candidate_packet: dict[str, Any] | None,
    admission_review_path: Path | None = None,
    current_envelope_path: Path | None = None,
    false_negative_candidate_packet_path: Path | None = None,
    selected_side_cell_key: str | None = None,
    operator_id: str = DEFAULT_OPERATOR_ID,
    runtime_envelope_path: Path = DEFAULT_RUNTIME_ENVELOPE_PATH,
    runtime_env_var: str = DEFAULT_ENV_VAR,
    max_authorized_probe_orders: int = DEFAULT_MAX_AUTHORIZED_PROBE_ORDERS,
    authorization_ttl_hours: int = DEFAULT_AUTHORIZATION_TTL_HOURS,
    max_authorization_ttl_hours: int = DEFAULT_MAX_AUTHORIZATION_TTL_HOURS,
    now_utc: dt.datetime | None = None,
    max_artifact_age_seconds: int = DEFAULT_MAX_ARTIFACT_AGE_SECONDS,
    source_head: str | None = None,
    runtime_head: str | None = None,
) -> dict[str, Any]:
    if max_artifact_age_seconds < 60 or max_artifact_age_seconds > 24 * 3600:
        raise ValueError("max_artifact_age_seconds must be in [60, 86400]")
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    admission = _dict(admission_review)
    envelope = _dict(current_envelope)
    packet = _dict(false_negative_candidate_packet)
    artifacts = {
        "admission_review": _artifact_summary(
            name="admission_review",
            path=admission_review_path,
            payload=admission,
            now_utc=now,
            max_age_seconds=max_artifact_age_seconds,
        ),
        "current_envelope": _artifact_summary(
            name="current_envelope",
            path=current_envelope_path,
            payload=envelope,
            now_utc=now,
            max_age_seconds=max_artifact_age_seconds,
        ),
        "false_negative_candidate_packet": _artifact_summary(
            name="false_negative_candidate_packet",
            path=false_negative_candidate_packet_path,
            payload=packet,
            now_utc=now,
            max_age_seconds=max_artifact_age_seconds,
        ),
    }

    admission_candidate = _candidate_identity(_dict(admission.get("candidate")))
    envelope_candidate = _candidate_identity(_dict(envelope.get("candidate")))
    side_cell_key = selected_side_cell_key or _str(admission_candidate.get("side_cell_key"))
    selected_row, selection_method = _select_false_negative_candidate(
        packet,
        side_cell_key=side_cell_key,
    )
    packet_candidate = _candidate_from_false_negative_row(selected_row)
    candidate_scope = admission_candidate if admission_candidate.get("side_cell_key") else packet_candidate

    source_reasons: list[str] = []
    for name, artifact in artifacts.items():
        if artifact.get("status") != "FRESH":
            source_reasons.append(f"{name}_artifact_not_fresh")
    source_reasons.extend(
        _source_contract_reasons(
            admission_review=admission,
            current_envelope=envelope,
        )
    )
    source_reasons.extend(_packet_reasons(packet, artifacts["false_negative_candidate_packet"]))
    source_reasons.extend(
        _cap_lineage_reasons(
            admission_review=admission,
            current_envelope=envelope,
        )
    )
    source_reasons.extend(_candidate_review_reasons(selected_row))
    candidate_alignment = _candidate_aligned(
        admission_candidate,
        envelope_candidate,
        packet_candidate,
    )
    if not candidate_alignment:
        source_reasons.append("candidate_alignment_failed")

    output_path_valid, output_path_reasons = _validate_output_path(runtime_envelope_path)
    if not output_path_valid:
        source_reasons.extend(output_path_reasons)
    if runtime_env_var not in ALLOWED_ENV_VARS:
        source_reasons.append("runtime_env_var_not_allowed")
    limits_valid, limit_reasons = _validate_limits(
        max_authorized_probe_orders=max_authorized_probe_orders,
        authorization_ttl_hours=authorization_ttl_hours,
        max_authorization_ttl_hours=max_authorization_ttl_hours,
    )
    if not limits_valid:
        source_reasons.extend(limit_reasons)
    if not _str(operator_id):
        source_reasons.append("operator_id_missing")

    authority_reasons: list[str] = []
    for name, payload in (
        ("admission_review", admission),
        ("current_envelope", envelope),
        ("false_negative_candidate_packet", packet),
    ):
        authority_reasons.extend(
            f"{name}.{reason}" for reason in _recursive_authority_violations(payload)
        )

    cap_resolution = _dict(envelope.get("cap_resolution"))
    risk = _dict(admission.get("risk_semantics"))
    risk_cap_lineage = {
        "risk_source_of_truth": GUI_RISK_SOURCE,
        "cap_source": GUI_CAP_SOURCE,
        "account_equity_usdt": cap_resolution.get("account_equity_usdt"),
        "per_trade_risk_pct_fraction": cap_resolution.get("per_trade_risk_pct_fraction"),
        "per_trade_risk_pct_display": cap_resolution.get("per_trade_risk_pct_display"),
        "position_size_max_pct": cap_resolution.get("position_size_max_pct"),
        "single_position_budget_usdt": cap_resolution.get("single_position_budget_usdt"),
        "resolved_cap_usdt": cap_resolution.get("resolved_cap_usdt"),
        "rounded_notional_usdt": risk.get("rounded_notional_usdt"),
        "local_10_usdt_cap_is_global_risk_authority": False,
        "bounded_probe_local_cap_usdt_is_authority": False,
    }
    source_refs = {
        "admission_review_path": str(admission_review_path) if admission_review_path else None,
        "admission_review_sha256": artifacts["admission_review"].get("sha256"),
        "current_envelope_path": str(current_envelope_path) if current_envelope_path else None,
        "current_envelope_sha256": artifacts["current_envelope"].get("sha256"),
        "false_negative_candidate_packet_path": (
            str(false_negative_candidate_packet_path)
            if false_negative_candidate_packet_path
            else None
        ),
        "false_negative_candidate_packet_sha256": artifacts[
            "false_negative_candidate_packet"
        ].get("sha256"),
    }

    can_preview = not source_reasons and not authority_reasons
    envelope_preview: dict[str, Any] = {}
    standing_summary: dict[str, Any] = {}
    if can_preview:
        envelope_preview = _envelope_preview(
            candidate_scope=candidate_scope,
            operator_id=operator_id,
            max_authorized_probe_orders=max_authorized_probe_orders,
            expires_at_utc=now + dt.timedelta(hours=authorization_ttl_hours),
            now_utc=now,
            risk_cap_lineage=risk_cap_lineage,
            source_refs=source_refs,
        )
        standing_summary = summarize_standing_demo_authorization(
            envelope_preview,
            {
                "status": "FRESH",
                "schema_version": STANDING_DEMO_AUTHORIZATION_SCHEMA_VERSION,
            },
            now_utc=now,
            max_authorization_ttl_hours=max_authorization_ttl_hours,
            candidate=candidate_scope,
        )
    preview_valid = bool(
        can_preview
        and standing_summary.get("valid_for_candidate_scoped_authorization") is True
    )
    if can_preview and not preview_valid:
        source_reasons.append("standing_demo_authorization_preview_invalid")

    status = (
        AUTHORITY_BOUNDARY_VIOLATION_STATUS
        if authority_reasons
        else READY_STATUS
        if preview_valid
        else NOT_READY_STATUS
    )
    gates = [
        _gate(
            "source_artifacts_fresh_and_ready",
            not [
                reason for reason in source_reasons
                if reason.endswith("_artifact_not_fresh")
                or reason.endswith("_schema_invalid")
                or reason.endswith("_status_not_ready")
            ],
            "admission review, current envelope, and false-negative packet must be fresh and ready",
            {"source_reasons": sorted(set(source_reasons))},
        ),
        _gate(
            "gui_cap_lineage_valid",
            not _cap_lineage_reasons(admission_review=admission, current_envelope=envelope),
            "risk cap must come from GUI-backed Rust RiskConfig and accepted Demo equity",
            risk_cap_lineage,
        ),
        _gate(
            "selected_candidate_aligned",
            candidate_alignment and not _candidate_review_reasons(selected_row),
            "selected false-negative candidate must match the current admission candidate",
            {
                "selection_method": selection_method,
                "admission_candidate": admission_candidate,
                "current_envelope_candidate": envelope_candidate,
                "packet_candidate": packet_candidate,
                "selected_row": selected_row,
            },
        ),
        _gate(
            "loss_control_limits_valid",
            limits_valid,
            "probe count and TTL must stay inside hard caps",
            {
                "max_authorized_probe_orders": max_authorized_probe_orders,
                "hard_max_authorized_probe_orders": HARD_MAX_AUTHORIZED_PROBE_ORDERS,
                "authorization_ttl_hours": authorization_ttl_hours,
                "max_authorization_ttl_hours": max_authorization_ttl_hours,
                "limit_reasons": limit_reasons,
            },
        ),
        _gate(
            "materialization_plan_scoped",
            output_path_valid and runtime_env_var in ALLOWED_ENV_VARS,
            "future runtime materialization path/env must be constrained",
            {
                "runtime_envelope_path": str(runtime_envelope_path),
                "runtime_env_var": runtime_env_var,
                "output_path_reasons": output_path_reasons,
            },
        ),
        _gate(
            "authority_boundary_preserved",
            not authority_reasons,
            "inputs must not already grant order/probe/live authority or mutation",
            {"authority_reasons": sorted(set(authority_reasons))},
        ),
        _gate(
            "standing_demo_authorization_preview_valid",
            preview_valid,
            "generated standing Demo envelope must pass shared validator",
            standing_summary,
        ),
    ]
    blocking_gates = [gate["name"] for gate in gates if gate["passed"] is not True]
    materialization_plan = (
        _materialization_plan(
            path=runtime_envelope_path,
            env_var=runtime_env_var,
            candidate_scope=candidate_scope,
            risk_cap_lineage=risk_cap_lineage,
            max_authorized_probe_orders=max_authorized_probe_orders,
            authorization_ttl_hours=authorization_ttl_hours,
            max_authorization_ttl_hours=max_authorization_ttl_hours,
        )
        if preview_valid
        else {}
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": ";".join(blocking_gates) or "ready_no_runtime_mutation",
        "candidate": candidate_scope if candidate_scope.get("side_cell_key") else {},
        "source_head": source_head,
        "runtime_head": runtime_head,
        "artifacts": artifacts,
        "source_refs": source_refs,
        "candidate_alignment": {
            "aligned": candidate_alignment,
            "admission_candidate": admission_candidate,
            "current_envelope_candidate": envelope_candidate,
            "false_negative_packet_candidate": packet_candidate,
        },
        "risk_cap_lineage": risk_cap_lineage,
        "selected_false_negative_candidate": selected_row,
        "selection_method": selection_method,
        "envelope_preview": envelope_preview if preview_valid else {},
        "standing_demo_authorization_validation": standing_summary,
        "materialization_plan": materialization_plan,
        "gates": gates,
        "blocking_gates": blocking_gates,
        "blocking_gate_count": len(blocking_gates),
        "source_blockers": sorted(set(source_reasons)),
        "authority_contamination_reasons": sorted(set(authority_reasons)),
        "summary": {
            "review_ready_no_runtime_mutation": preview_valid,
            "selected_side_cell_key": candidate_scope.get("side_cell_key"),
            "resolved_cap_usdt": risk_cap_lineage.get("resolved_cap_usdt"),
            "gui_p1_risk_trade_pct": risk_cap_lineage.get(
                "per_trade_risk_pct_display"
            ),
            "max_authorized_probe_orders_per_candidate": max_authorized_probe_orders,
            "authorization_ttl_hours": authorization_ttl_hours,
            "standing_envelope_materialized": False,
            "bounded_demo_probe_authorized": False,
            "runtime_admission_ready": False,
            "order_admission_ready": False,
            "max_safe_next_action": (
                "review_runtime_materialization_of_current_candidate_standing_envelope"
                if preview_valid
                else "repair_blocking_gates_before_runtime_materialization"
            ),
        },
        "answers": {
            "source_only_research_artifact": True,
            "review_ready_no_runtime_mutation": preview_valid,
            "runtime_mutation_performed": False,
            "env_mutation_performed": False,
            "crontab_mutation_performed": False,
            "standing_envelope_materialized": False,
            "standing_demo_authorization_valid": preview_valid,
            "standing_demo_authorization_consumed": False,
            "operator_authorization_object_emitted": False,
            "bounded_demo_probe_authorized": False,
            "decision_lease_emitted": False,
            "guardian_risk_gate_passed_by_this_packet": False,
            "rust_authority_granted_by_this_packet": False,
            "runtime_admission_ready": False,
            "order_admission_ready": False,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "live_authority_granted": False,
            "mainnet_authority_granted": False,
            "order_submission_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "bybit_call_performed": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
        "boundary": BOUNDARY,
    }


def render_markdown(review: dict[str, Any]) -> str:
    candidate = _dict(review.get("candidate"))
    summary = _dict(review.get("summary"))
    lines = [
        "# Current Candidate Standing Demo Loss-Control Envelope Review",
        "",
        f"- Status: `{review.get('status')}`",
        f"- Reason: `{review.get('reason')}`",
        f"- Candidate: `{candidate.get('side_cell_key')}`",
        f"- GUI P1 risk/trade: `{summary.get('gui_p1_risk_trade_pct')}%`",
        f"- Resolved GUI cap USDT: `{summary.get('resolved_cap_usdt')}`",
        f"- Max probe orders: `{summary.get('max_authorized_probe_orders_per_candidate')}`",
        f"- Runtime mutation performed: `{_dict(review.get('answers')).get('runtime_mutation_performed')}`",
        "",
        "## Gates",
    ]
    for gate in _list(review.get("gates")):
        lines.append(f"- `{gate.get('name')}`: `{gate.get('passed')}`")
    lines.extend(["", "## Blocking Gates"])
    blockers = _list(review.get("blocking_gates"))
    lines.extend(f"- `{blocker}`" for blocker in blockers) if blockers else lines.append("- none")
    lines.extend(["", "## Boundary", BOUNDARY])
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admission-review-json", type=Path, required=True)
    parser.add_argument("--current-envelope-json", type=Path, required=True)
    parser.add_argument("--false-negative-candidate-packet-json", type=Path, required=True)
    parser.add_argument("--selected-side-cell-key")
    parser.add_argument("--operator-id", default=DEFAULT_OPERATOR_ID)
    parser.add_argument("--runtime-envelope-path", type=Path, default=DEFAULT_RUNTIME_ENVELOPE_PATH)
    parser.add_argument("--runtime-env-var", default=DEFAULT_ENV_VAR)
    parser.add_argument("--max-authorized-probe-orders", type=int, default=DEFAULT_MAX_AUTHORIZED_PROBE_ORDERS)
    parser.add_argument("--authorization-ttl-hours", type=int, default=DEFAULT_AUTHORIZATION_TTL_HOURS)
    parser.add_argument("--max-authorization-ttl-hours", type=int, default=DEFAULT_MAX_AUTHORIZATION_TTL_HOURS)
    parser.add_argument("--max-artifact-age-seconds", type=int, default=DEFAULT_MAX_ARTIFACT_AGE_SECONDS)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source-head")
    parser.add_argument("--runtime-head")
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    review = build_current_candidate_standing_demo_loss_control_envelope_review(
        admission_review=_read_json(args.admission_review_json),
        current_envelope=_read_json(args.current_envelope_json),
        false_negative_candidate_packet=_read_json(args.false_negative_candidate_packet_json),
        admission_review_path=args.admission_review_json,
        current_envelope_path=args.current_envelope_json,
        false_negative_candidate_packet_path=args.false_negative_candidate_packet_json,
        selected_side_cell_key=args.selected_side_cell_key,
        operator_id=args.operator_id,
        runtime_envelope_path=args.runtime_envelope_path,
        runtime_env_var=args.runtime_env_var,
        max_authorized_probe_orders=args.max_authorized_probe_orders,
        authorization_ttl_hours=args.authorization_ttl_hours,
        max_authorization_ttl_hours=args.max_authorization_ttl_hours,
        max_artifact_age_seconds=args.max_artifact_age_seconds,
        source_head=args.source_head,
        runtime_head=args.runtime_head,
    )
    if args.json_output:
        _write_json(args.json_output, review)
    if args.output:
        _write_text(args.output, render_markdown(review))
    if args.print_json:
        print(json.dumps(review, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
