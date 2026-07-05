#!/usr/bin/env python3
"""Build a source-only standing Demo loss-control envelope review.

The packet previews a future runtime-readable
``standing_demo_operator_authorization_v1`` envelope and the exact runtime
materialization/rollback plan. This helper does not write the envelope to the
runtime path, mutate env/crontab, submit orders, grant probe/order authority,
lower Cost Gate, or create promotion/profit proof.
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
from cost_gate_learning_lane.false_negative_candidate_packet import (
    SCHEMA_VERSION as FALSE_NEGATIVE_CANDIDATE_PACKET_SCHEMA_VERSION,
)
from cost_gate_learning_lane.standing_demo_authorization import (
    summarize_standing_demo_authorization,
)

# 共用純函數葉節點：以 alias-import 保持函數體內 _dict/_list/_str/_sha256/_utc_now 引用逐字節不變。
from cost_gate_learning_lane._lane_common import (
    as_dict as _dict,
    as_list as _list,
    as_str as _str,
    file_sha256 as _sha256,
    utc_now as _utc_now,
)


SCHEMA_VERSION = "cost_gate_standing_demo_loss_control_envelope_review_v1"
READY_STATUS = "STANDING_DEMO_LOSS_CONTROL_ENVELOPE_REVIEW_READY_NO_RUNTIME_MUTATION"
PACKET_NOT_READY_STATUS = "FALSE_NEGATIVE_CANDIDATE_PACKET_NOT_READY"
SELECTION_REQUIRED_STATUS = "FALSE_NEGATIVE_CANDIDATE_SELECTION_REQUIRED"
CANDIDATE_NOT_REVIEWABLE_STATUS = "FALSE_NEGATIVE_CANDIDATE_NOT_REVIEWABLE"
MATERIALIZATION_PATH_INVALID_STATUS = "MATERIALIZATION_PATH_INVALID"
MATERIALIZATION_ENV_VAR_INVALID_STATUS = "MATERIALIZATION_ENV_VAR_INVALID"
LOSS_CONTROL_LIMIT_INVALID_STATUS = "LOSS_CONTROL_LIMIT_INVALID"
GUI_RISK_CAP_INPUT_REQUIRED_STATUS = "GUI_RISK_CAP_INPUT_REQUIRED"
OPERATOR_ID_REQUIRED_STATUS = "OPERATOR_ID_REQUIRED"
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"
GENERATED_ENVELOPE_VALIDATION_FAILED_STATUS = (
    "GENERATED_ENVELOPE_VALIDATION_FAILED"
)

FALSE_NEGATIVE_CANDIDATE_PACKET_READY_STATUS = (
    "COST_GATE_FALSE_NEGATIVE_CANDIDATES_READY_FOR_OPERATOR_REVIEW"
)
DEFAULT_MAX_ARTIFACT_AGE_HOURS = 24
DEFAULT_AUTHORIZATION_TTL_HOURS = 12
DEFAULT_MAX_AUTHORIZATION_TTL_HOURS = 24
DEFAULT_MAX_AUTHORIZED_PROBE_ORDERS = 2
HARD_MAX_AUTHORIZED_PROBE_ORDERS = 3
DEFAULT_OPERATOR_ID = "standing-demo-loss-control-review"
DEFAULT_STANDING_ENV_VAR = "OPENCLAW_COST_GATE_STANDING_DEMO_AUTHORIZATION_JSON"
ALLOWED_STANDING_ENV_VARS = {DEFAULT_STANDING_ENV_VAR}
DEFAULT_MATERIALIZATION_PATH = Path(
    "/tmp/openclaw/cost_gate_learning_lane/standing_demo_operator_authorization.json"
)
ALLOWED_MATERIALIZATION_ROOTS = (
    Path("/tmp/openclaw/cost_gate_learning_lane"),
)

BOUNDARY = (
    "source-only standing Demo loss-control envelope materialization review; "
    "no runtime file write, env or crontab mutation, PG query/write, Bybit "
    "call, order, cancel, service restart, risk mutation, Cost Gate lowering, "
    "probe authority, order authority, live authority, promotion proof, or "
    "profit proof"
)

FALSE_SAFE_STRINGS = {
    "0",
    "false",
    "n",
    "no",
    "off",
    "disabled",
    "none",
    "null",
    "absent",
    "missing",
    "deny",
    "denied",
    "not_enabled",
    "not enabled",
    "not_granted",
    "not granted",
    "not_authorized",
    "not authorized",
    "not_present",
    "not present",
    "not_ready",
    "not ready",
}

FORBIDDEN_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "bounded_demo_probe_authorized",
    "bybit_call_performed",
    "bybit_private_call_performed",
    "cap_mutation_performed",
    "config_mutation_performed",
    "cost_gate_lowering_performed",
    "cost_gate_lowering_recommended",
    "credential_load_performed",
    "crontab_mutation_performed",
    "env_mutation_performed",
    "exchange_call_performed",
    "global_cost_gate_lowering_recommended",
    "ledger_append_performed",
    "live_authority_granted",
    "live_promotion_performed",
    "mainnet_authority_granted",
    "network_call_performed",
    "operator_authorization_object_emitted",
    "order_admission_ready",
    "order_authority_granted",
    "order_cancel_performed",
    "order_modify_performed",
    "order_submission_performed",
    "pg_query_performed",
    "pg_write_performed",
    "plan_mutation_performed",
    "probe_authority_granted",
    "promotion_evidence",
    "promotion_proof",
    "risk_mutation_performed",
    "runtime_mutation_performed",
    "service_restart_performed",
    "standing_envelope_materialized",
    "writer_enabled",
}

FORBIDDEN_ALIAS_RULES = {
    "cost_gate_lowering_alias": ("cost", "gate", "lowering"),
    "cost_gate_proof_alias": ("cost", "gate", "proof"),
    "env_mutation_alias": ("env", "mutation"),
    "crontab_mutation_alias": ("crontab", "mutation"),
    "live_authority_alias": ("live", "authority"),
    "mainnet_authority_alias": ("mainnet", "authority"),
    "operator_auth_object_alias": ("operator", "auth", "object"),
    "order_authority_alias": ("order", "authority"),
    "order_submission_alias": ("order", "submission"),
    "probe_authority_alias": ("probe", "authority"),
    "promotion_proof_alias": ("promotion", "proof"),
    "runtime_mutation_alias": ("runtime", "mutation"),
}


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
        text = value.strip().lower()
        return bool(text) and text not in FALSE_SAFE_STRINGS
    return value is not None


def _normalize_key(key: Any) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in str(key))


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


def _generated_at(payload: dict[str, Any]) -> Any:
    return payload.get("generated_at_utc") or payload.get("generated") or payload.get(
        "ts_utc"
    )


def _artifact_summary(
    *,
    name: str,
    path: Path | None,
    payload: dict[str, Any] | None,
    source_error: str | None,
    now_utc: dt.datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    present = isinstance(payload, dict) and bool(payload) and source_error is None
    generated_at = _generated_at(payload or {}) if present else None
    age = _age_seconds(generated_at, now_utc=now_utc) if generated_at else None
    if source_error:
        status = "UNAVAILABLE"
    elif not present:
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
        "path_basename": path.name if path else None,
        "sha256": _sha256(path),
        "status": status,
        "present": present,
        "generated_at_utc": generated_at,
        "age_seconds": age,
        "max_age_seconds": max_age_seconds,
        "schema_version": (payload or {}).get("schema_version") if present else None,
        "source_error": source_error,
    }


def _authority_preserved(*payloads: dict[str, Any] | None) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    stack: list[Any] = list(payloads)
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            stack.extend(item)
            continue
        data = _dict(item)
        if not data:
            continue
        adjustment = data.get("main_cost_gate_adjustment")
        if adjustment not in (None, "", "NONE"):
            reasons.append("main_cost_gate_adjustment_not_none")
        for key, value in data.items():
            if not _truthy(value):
                continue
            normalized_key = _normalize_key(key)
            if key in FORBIDDEN_TRUE_KEYS:
                reasons.append(f"{key}_true")
            for label, tokens in FORBIDDEN_ALIAS_RULES.items():
                if all(token in normalized_key for token in tokens):
                    reasons.append(f"{key}_true_alias_{label}")
        stack.extend(value for value in data.values() if isinstance(value, (dict, list)))
    return not reasons, sorted(set(reasons))


def _candidate_rows(packet: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _list(_dict(packet).get("ranked_false_negative_candidates")):
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _candidate_summary(candidate: dict[str, Any] | None) -> dict[str, Any]:
    row = _dict(candidate)
    return {
        "side_cell_key": row.get("side_cell_key"),
        "false_negative_rank": row.get("false_negative_rank"),
        "strategy_names": row.get("strategy_names") or [],
        "symbols": row.get("symbols") or [],
        "sides": row.get("sides") or [],
        "horizon_minutes": row.get("horizon_minutes") or [],
        "dominant_horizon_minutes": row.get("dominant_horizon_minutes"),
        "outcome_count": _int(row.get("outcome_count")),
        "avg_gross_bps": _float(row.get("avg_gross_bps")),
        "avg_net_bps": _float(row.get("avg_net_bps")),
        "avg_cost_bps": _float(row.get("avg_cost_bps")),
        "net_positive_pct": _float(row.get("net_positive_pct")),
        "net_cost_cushion_bps": _float(row.get("net_cost_cushion_bps")),
        "wrongful_block_score": _float(row.get("wrongful_block_score")),
        "candidate_class": row.get("candidate_class"),
        "learning_diagnosis": row.get("learning_diagnosis"),
        "status": row.get("status"),
        "reason": row.get("reason"),
        "next_action": row.get("next_action"),
        "operator_review_required": row.get("operator_review_required") is True,
        "global_cost_gate_lowering_recommended": (
            row.get("global_cost_gate_lowering_recommended") is True
        ),
        "probe_authority_granted": row.get("probe_authority_granted") is True,
        "order_authority_granted": row.get("order_authority_granted") is True,
        "promotion_evidence": row.get("promotion_evidence") is True,
        "risk_cap_lineage": _dict(
            row.get("risk_cap_lineage")
            or row.get("risk_semantics")
            or row.get("cap_resolution")
        ),
    }


def _select_candidate(
    packet: dict[str, Any] | None,
    selected_side_cell_key: str | None,
) -> tuple[dict[str, Any] | None, str]:
    rows = _candidate_rows(packet)
    selected = _str(selected_side_cell_key)
    if selected:
        for row in rows:
            if _str(row.get("side_cell_key")) == selected:
                return row, "explicit_side_cell_key"
        return None, "explicit_side_cell_key_not_found"
    if rows:
        return rows[0], "top_ranked_false_negative"
    return None, "no_ranked_false_negative_candidate"


def _first(value: Any) -> Any:
    values = _list(value)
    return values[0] if values else None


def _candidate_scope(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "side_cell_key": candidate.get("side_cell_key"),
        "strategy_name": _first(candidate.get("strategy_names")),
        "symbol": _first(candidate.get("symbols")),
        "side": _first(candidate.get("sides")),
        "outcome_horizon_minutes": candidate.get("dominant_horizon_minutes")
        or _first(candidate.get("horizon_minutes")),
    }


def _candidate_scope_complete(candidate_scope: dict[str, Any]) -> bool:
    return all(_str(candidate_scope.get(key)) for key in candidate_scope)


def _candidate_reviewable(candidate: dict[str, Any]) -> bool:
    return (
        bool(_str(candidate.get("side_cell_key")))
        and candidate.get("candidate_class") == "false_negative_after_cost"
        and candidate.get("operator_review_required") is True
        and candidate.get("global_cost_gate_lowering_recommended") is not True
        and candidate.get("probe_authority_granted") is not True
        and candidate.get("order_authority_granted") is not True
        and candidate.get("promotion_evidence") is not True
    )


def _risk_cap_lineage_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    lineage = _dict(candidate.get("risk_cap_lineage"))
    source_of_truth = _str(
        lineage.get("risk_source_of_truth")
        or lineage.get("source")
        or lineage.get("cap_source")
    )
    source_text = source_of_truth.lower()
    resolved_cap = _float(lineage.get("resolved_cap_usdt"))
    per_trade_fraction = _float(
        lineage.get("per_trade_risk_pct_fraction")
        or lineage.get("per_trade_risk_pct")
    )
    per_trade_display = _float(
        lineage.get("per_trade_risk_pct_display")
        or lineage.get("gui_p1_risk_trade_pct")
    )
    local_10_is_authority = _truthy(
        lineage.get("local_10_usdt_cap_is_global_risk_authority")
    )
    bounded_probe_local_cap_is_authority = _truthy(
        lineage.get("bounded_probe_local_cap_usdt_is_authority")
    )
    gui_backed = (
        ("gui" in source_text and "riskconfig" in source_text)
        or lineage.get("gui_risk_config_is_source_of_truth") is True
        or lineage.get("gui_risk_config_is_authority") is True
    )
    valid = (
        bool(lineage)
        and gui_backed
        and resolved_cap is not None
        and resolved_cap > 0.0
        and per_trade_fraction is not None
        and 0.0 < per_trade_fraction <= 1.0
        and per_trade_display is not None
        and per_trade_display > 0.0
        and local_10_is_authority is False
        and bounded_probe_local_cap_is_authority is False
    )
    return {
        "valid": valid,
        "risk_source_of_truth": source_of_truth or None,
        "cap_source": lineage.get("cap_source"),
        "account_equity_usdt": _float(lineage.get("account_equity_usdt")),
        "per_trade_risk_pct_fraction": per_trade_fraction,
        "per_trade_risk_pct_display": per_trade_display,
        "position_size_max_pct": _float(lineage.get("position_size_max_pct")),
        "single_position_budget_usdt": _float(
            lineage.get("single_position_budget_usdt")
        ),
        "resolved_cap_usdt": resolved_cap,
        "rounded_notional_usdt": _float(
            lineage.get("rounded_notional_usdt")
            or lineage.get("constructed_notional_usdt")
        ),
        "local_10_usdt_cap_is_global_risk_authority": local_10_is_authority,
        "bounded_probe_local_cap_usdt_is_authority": (
            bounded_probe_local_cap_is_authority
        ),
    }


def _packet_ready(
    packet: dict[str, Any],
    artifact: dict[str, Any],
    *,
    authority_ok: bool,
) -> bool:
    answers = _dict(packet.get("answers"))
    summary = _dict(packet.get("summary"))
    return (
        authority_ok
        and artifact.get("status") == "FRESH"
        and artifact.get("schema_version") == FALSE_NEGATIVE_CANDIDATE_PACKET_SCHEMA_VERSION
        and packet.get("status") == FALSE_NEGATIVE_CANDIDATE_PACKET_READY_STATUS
        and answers.get("operator_review_ready") is True
        and answers.get("global_cost_gate_lowering_recommended") is not True
        and answers.get("probe_authority_granted") is not True
        and answers.get("order_authority_granted") is not True
        and answers.get("promotion_evidence") is not True
        and _int(summary.get("false_negative_candidate_count")) > 0
    )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _validate_materialization_path(path: Path | None) -> tuple[bool, str, dict[str, Any]]:
    if path is None:
        return False, "materialization_path_missing", {}
    raw = str(path)
    if "\x00" in raw or "\n" in raw or "\r" in raw:
        return False, "materialization_path_contains_control_character", {"path": raw}
    if not path.is_absolute():
        return False, "materialization_path_must_be_absolute", {"path": raw}
    if path.suffix.lower() != ".json":
        return False, "materialization_path_must_end_json", {"path": raw}
    if path.exists() and path.is_dir():
        return False, "materialization_path_is_directory", {"path": raw}
    resolved = path.expanduser().resolve(strict=False)
    allowed_roots = tuple(root.resolve(strict=False) for root in ALLOWED_MATERIALIZATION_ROOTS)
    if not any(_is_relative_to(resolved, root) for root in allowed_roots):
        return (
            False,
            "materialization_path_must_stay_under_allowed_runtime_artifact_root",
            {
                "path": str(resolved),
                "allowed_roots": [str(root) for root in allowed_roots],
            },
        )
    return (
        True,
        "materialization_path_valid",
        {
            "path": str(resolved),
            "allowed_roots": [str(root) for root in allowed_roots],
        },
    )


def _validate_env_var(env_var: str | None) -> tuple[bool, str, dict[str, Any]]:
    text = _str(env_var)
    if not text:
        return False, "standing_authorization_env_var_missing", {}
    if text not in ALLOWED_STANDING_ENV_VARS:
        return (
            False,
            "standing_authorization_env_var_not_allowed",
            {"env_var": text, "allowed_env_vars": sorted(ALLOWED_STANDING_ENV_VARS)},
        )
    return True, "standing_authorization_env_var_valid", {"env_var": text}


def _validate_loss_control_limits(
    *,
    max_authorized_probe_orders: int,
    authorization_ttl_hours: int,
    max_authorization_ttl_hours: int,
) -> tuple[bool, list[str], dict[str, Any]]:
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
    return (
        not reasons,
        reasons,
        {
            "max_authorized_probe_orders_per_candidate": max_authorized_probe_orders,
            "hard_max_authorized_probe_orders_per_candidate": HARD_MAX_AUTHORIZED_PROBE_ORDERS,
            "authorization_ttl_hours": authorization_ttl_hours,
            "max_authorization_ttl_hours": max_authorization_ttl_hours,
        },
    )


def _standing_authorization_id(
    *,
    candidate_scope: dict[str, Any],
    now_utc: dt.datetime,
) -> str:
    digest = hashlib.sha256(
        json.dumps(candidate_scope, sort_keys=True, default=str).encode("utf-8")
        + now_utc.isoformat().encode("utf-8")
    ).hexdigest()[:12]
    return f"standing-demo-loss-control-{now_utc:%Y%m%dT%H%M%SZ}-{digest}"


def _build_envelope_preview(
    *,
    candidate_scope: dict[str, Any],
    operator_id: str,
    max_authorized_probe_orders: int,
    expires_at_utc: dt.datetime,
    now_utc: dt.datetime,
    risk_cap_lineage: dict[str, Any],
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
        "max_authorized_probe_orders_per_candidate": max_authorized_probe_orders,
        "expires_at_utc": expires_at_utc.isoformat(),
        "risk_cap_lineage": risk_cap_lineage,
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
    *,
    status: str,
    reason: str,
    next_actions: list[str] | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "passed": passed,
        "status": status,
        "reason": reason,
        "next_actions": next_actions or [],
        "evidence": evidence or {},
    }


def _status_from_failed_gates(failed_gates: list[dict[str, Any]]) -> str:
    failed = {gate["name"] for gate in failed_gates}
    if "authority_boundary_preserved" in failed:
        return AUTHORITY_BOUNDARY_VIOLATION_STATUS
    if "materialization_path_valid" in failed:
        return MATERIALIZATION_PATH_INVALID_STATUS
    if "materialization_env_var_valid" in failed:
        return MATERIALIZATION_ENV_VAR_INVALID_STATUS
    if "loss_control_limits_valid" in failed:
        return LOSS_CONTROL_LIMIT_INVALID_STATUS
    if "operator_id_present" in failed:
        return OPERATOR_ID_REQUIRED_STATUS
    if "false_negative_candidate_packet_ready" in failed:
        return PACKET_NOT_READY_STATUS
    if "candidate_selected" in failed:
        return SELECTION_REQUIRED_STATUS
    if "candidate_reviewable" in failed or "candidate_scope_complete" in failed:
        return CANDIDATE_NOT_REVIEWABLE_STATUS
    if "gui_risk_cap_lineage_valid" in failed:
        return GUI_RISK_CAP_INPUT_REQUIRED_STATUS
    if "standing_demo_authorization_preview_valid" in failed:
        return GENERATED_ENVELOPE_VALIDATION_FAILED_STATUS
    return READY_STATUS


def _dedupe(items: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = _str(item)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _materialization_plan(
    *,
    path: Path,
    env_var: str,
    candidate_scope: dict[str, Any],
    max_authorized_probe_orders: int,
    authorization_ttl_hours: int,
    max_authorization_ttl_hours: int,
) -> dict[str, Any]:
    side_cell = _str(candidate_scope.get("side_cell_key"))
    return {
        "source_only_review": True,
        "runtime_mutation_performed_by_this_helper": False,
        "standing_envelope_materialized_by_this_helper": False,
        "proposed_runtime_envelope_path": str(path),
        "proposed_env_var": env_var,
        "proposed_env_assignment": f"{env_var}={path}",
        "proposed_env_scope": (
            "cost_gate_learning_lane_cron_only; alpha_discovery_throughput_cron "
            "will observe this same path only through its documented fallback "
            "when OPENCLAW_ALPHA_STANDING_DEMO_AUTHORIZATION_JSON is unset"
        ),
        "candidate_scope_policy": {
            "candidate_scoping_required": True,
            "candidate_scope": candidate_scope,
            "cross_candidate_reuse_allowed": False,
            "candidate_scope_mismatch_policy": "fail_closed_no_review_approval",
        },
        "loss_control_envelope": {
            "demo_only": True,
            "max_authorized_probe_orders_per_candidate": max_authorized_probe_orders,
            "hard_max_authorized_probe_orders_per_candidate": HARD_MAX_AUTHORIZED_PROBE_ORDERS,
            "authorization_ttl_hours": authorization_ttl_hours,
            "max_authorization_ttl_hours": max_authorization_ttl_hours,
            "scheduled_bounded_probe_operator_authorization_decision_must_remain": "defer",
        },
        "future_apply_steps_require_e3_review": [
            "write the reviewed standing_demo_operator_authorization_v1 JSON atomically with mode 0600 at proposed_runtime_envelope_path",
            "add only the proposed_env_assignment to the cost_gate_learning_lane_cron crontab line or reviewed runtime env wrapper",
            "do not set OPENCLAW_COST_GATE_BOUNDED_PROBE_OPERATOR_AUTHORIZATION_DECISION=authorize",
            "refresh false_negative_operator_review and false_negative_bounded_probe_preflight artifacts and verify no probe/order authority is emitted",
        ],
        "validation_commands": [
            (
                "PYTHONPATH=helper_scripts/research python3 -m "
                "cost_gate_learning_lane.false_negative_operator_review "
                "--false-negative-candidate-packet-json "
                "/tmp/openclaw/cost_gate_learning_lane/false_negative_candidate_packet_latest.json "
                f"--standing-demo-authorization-json {path} "
                f"--selected-side-cell-key '{side_cell}' --decision defer "
                f"--max-authorization-ttl-hours {max_authorization_ttl_hours} --print-json"
            ),
            (
                "PYTHONPATH=helper_scripts/research python3 -m "
                "cost_gate_learning_lane.false_negative_bounded_probe_preflight "
                "--autonomous-parameter-proposal-json "
                "/tmp/openclaw/cost_gate_learning_lane/autonomous_parameter_proposal_latest.json "
                "--false-negative-operator-review-json "
                "/tmp/openclaw/cost_gate_learning_lane/false_negative_operator_review_latest.json "
                f"--standing-demo-authorization-json {path} --print-json"
            ),
        ],
        "rollback_plan": [
            f"remove {env_var} from the cost_gate_learning_lane_cron crontab/env wiring",
            f"move or delete {path} after recording sha256 and review id",
            f"verify crontab/env no longer contains {env_var}",
            "refresh natural scheduled artifacts with default defer and confirm they fail closed or remain no-authority",
        ],
        "rollback_verification_expected": {
            "standing_env_configured": False,
            "operator_authorization_object_emitted": False,
            "bounded_demo_probe_authorized": False,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "order_submission_performed": False,
        },
    }


def build_standing_demo_loss_control_envelope_review(
    *,
    false_negative_candidate_packet: dict[str, Any] | None,
    false_negative_candidate_packet_path: Path | None = None,
    false_negative_candidate_packet_error: str | None = None,
    selected_side_cell_key: str | None = None,
    operator_id: str | None = DEFAULT_OPERATOR_ID,
    standing_demo_authorization_output_path: Path = DEFAULT_MATERIALIZATION_PATH,
    standing_demo_authorization_env_var: str = DEFAULT_STANDING_ENV_VAR,
    max_authorized_probe_orders: int = DEFAULT_MAX_AUTHORIZED_PROBE_ORDERS,
    authorization_ttl_hours: int = DEFAULT_AUTHORIZATION_TTL_HOURS,
    max_authorization_ttl_hours: int = DEFAULT_MAX_AUTHORIZATION_TTL_HOURS,
    now_utc: dt.datetime | None = None,
    max_artifact_age_hours: int = DEFAULT_MAX_ARTIFACT_AGE_HOURS,
) -> dict[str, Any]:
    """Build a fail-closed review packet for future runtime materialization."""
    if max_artifact_age_hours < 1 or max_artifact_age_hours > 24 * 14:
        raise ValueError("max_artifact_age_hours must be in [1, 336]")

    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    max_age_seconds = max_artifact_age_hours * 3600
    packet = _dict(false_negative_candidate_packet)
    artifact = _artifact_summary(
        name="false_negative_candidate_packet",
        path=false_negative_candidate_packet_path,
        payload=packet,
        source_error=false_negative_candidate_packet_error,
        now_utc=now,
        max_age_seconds=max_age_seconds,
    )
    authority_ok, authority_reasons = _authority_preserved(packet)
    selected, selection_method = _select_candidate(packet, selected_side_cell_key)
    candidate = _candidate_summary(selected)
    candidate_scope = _candidate_scope(candidate)
    path_valid, path_reason, path_evidence = _validate_materialization_path(
        standing_demo_authorization_output_path
    )
    env_valid, env_reason, env_evidence = _validate_env_var(
        standing_demo_authorization_env_var
    )
    limits_valid, limit_reasons, limit_evidence = _validate_loss_control_limits(
        max_authorized_probe_orders=max_authorized_probe_orders,
        authorization_ttl_hours=authorization_ttl_hours,
        max_authorization_ttl_hours=max_authorization_ttl_hours,
    )
    operator = _str(operator_id)
    packet_ready = _packet_ready(packet, artifact, authority_ok=authority_ok)
    candidate_selected = bool(_str(candidate.get("side_cell_key")))
    candidate_reviewable = _candidate_reviewable(candidate)
    candidate_scope_complete = _candidate_scope_complete(candidate_scope)
    risk_cap_lineage = _risk_cap_lineage_summary(candidate)
    risk_cap_valid = risk_cap_lineage.get("valid") is True

    envelope_preview: dict[str, Any] = {}
    standing_summary: dict[str, Any] = {}
    can_preview = (
        authority_ok
        and path_valid
        and env_valid
        and limits_valid
        and bool(operator)
        and packet_ready
        and candidate_selected
        and candidate_reviewable
        and candidate_scope_complete
        and risk_cap_valid
    )
    if can_preview:
        envelope_preview = _build_envelope_preview(
            candidate_scope=candidate_scope,
            operator_id=operator,
            max_authorized_probe_orders=max_authorized_probe_orders,
            expires_at_utc=now + dt.timedelta(hours=authorization_ttl_hours),
            now_utc=now,
            risk_cap_lineage=risk_cap_lineage,
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

    gates = [
        _gate(
            "authority_boundary_preserved",
            authority_ok,
            status="PRESERVED" if authority_ok else "VIOLATED",
            reason=(
                "source packet and candidate rows must not contain runtime/order/live "
                "authority, Cost Gate lowering, env/crontab/runtime mutation, or proof"
            ),
            next_actions=["remove_authority_contaminated_input_before_review"],
            evidence={"authority_contamination_reasons": authority_reasons},
        ),
        _gate(
            "materialization_path_valid",
            path_valid,
            status="VALID" if path_valid else "INVALID",
            reason=path_reason,
            next_actions=["choose_allowed_tmp_openclaw_cost_gate_json_path"],
            evidence=path_evidence,
        ),
        _gate(
            "materialization_env_var_valid",
            env_valid,
            status="VALID" if env_valid else "INVALID",
            reason=env_reason,
            next_actions=["use_only_openclaw_cost_gate_standing_demo_authorization_json"],
            evidence=env_evidence,
        ),
        _gate(
            "loss_control_limits_valid",
            limits_valid,
            status="VALID" if limits_valid else "INVALID",
            reason=";".join(limit_reasons) or "loss_control_limits_valid",
            next_actions=["reduce_probe_order_cap_or_ttl_before_materialization_review"],
            evidence=limit_evidence,
        ),
        _gate(
            "operator_id_present",
            bool(operator),
            status="PRESENT" if operator else "MISSING",
            reason="standing Demo envelope preview requires auditable operator id",
            next_actions=["record_operator_id_before_materialization_review"],
        ),
        _gate(
            "false_negative_candidate_packet_ready",
            packet_ready,
            status=str(packet.get("status") or artifact.get("status")),
            reason=(
                "candidate packet must be fresh, schema-valid, ready for operator "
                "review, and no-authority"
            ),
            next_actions=["refresh_cost_gate_false_negative_candidate_packet"],
            evidence={
                "artifact": artifact,
                "summary": _dict(packet.get("summary")),
                "answers": _dict(packet.get("answers")),
            },
        ),
        _gate(
            "candidate_selected",
            candidate_selected,
            status="SELECTED" if candidate_selected else selection_method,
            reason="review must bind to exactly one ranked false-negative side-cell",
            next_actions=["select_ranked_false_negative_side_cell_for_review"],
            evidence={
                "selection_method": selection_method,
                "selected_side_cell_key": selected_side_cell_key,
            },
        ),
        _gate(
            "candidate_reviewable",
            candidate_reviewable,
            status=str(candidate.get("status") or "MISSING"),
            reason="selected candidate must remain false_negative_after_cost and no-authority",
            next_actions=["rebuild_packet_or_select_reviewable_false_negative_candidate"],
            evidence=candidate,
        ),
        _gate(
            "candidate_scope_complete",
            candidate_scope_complete,
            status="COMPLETE" if candidate_scope_complete else "INCOMPLETE",
            reason="standing envelope must be candidate-scoped by side-cell, strategy, symbol, side, and horizon",
            next_actions=["refresh_candidate_packet_with_complete_candidate_identity"],
            evidence=candidate_scope,
        ),
        _gate(
            "gui_risk_cap_lineage_valid",
            risk_cap_valid,
            status="VALID" if risk_cap_valid else "MISSING_OR_INVALID",
            reason=(
                "standing envelope preview must carry GUI-backed Rust RiskConfig "
                "cap lineage; local 10 USDT diagnostics cannot define per-order risk"
            ),
            next_actions=[
                "refresh_candidate_packet_with_gui_risk_cap_lineage"
            ],
            evidence=risk_cap_lineage,
        ),
        _gate(
            "standing_demo_authorization_preview_valid",
            preview_valid,
            status="VALID" if preview_valid else "NOT_EVALUATED_OR_INVALID",
            reason=(
                "generated preview must pass standing_demo_operator_authorization_v1 "
                "validator for the selected candidate"
            ),
            next_actions=["repair_envelope_preview_before_runtime_materialization"],
            evidence=standing_summary,
        ),
    ]
    failed_gates = [gate for gate in gates if gate["passed"] is not True]
    status = _status_from_failed_gates(failed_gates)
    ready = status == READY_STATUS
    next_actions = (
        ["submit_runtime_materialization_plan_for_e3_review"]
        if ready
        else _dedupe(
            [
                action
                for gate in failed_gates
                for action in _list(gate.get("next_actions"))
            ]
        )
    )
    materialization_plan = (
        _materialization_plan(
            path=standing_demo_authorization_output_path,
            env_var=standing_demo_authorization_env_var,
            candidate_scope=candidate_scope,
            max_authorized_probe_orders=max_authorized_probe_orders,
            authorization_ttl_hours=authorization_ttl_hours,
            max_authorization_ttl_hours=max_authorization_ttl_hours,
        )
        if ready
        else {}
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": ";".join(gate["name"] for gate in failed_gates)
        or "standing_demo_loss_control_envelope_review_ready",
        "source_inputs": {
            "false_negative_candidate_packet": artifact,
            "authority_preserved": authority_ok,
            "authority_contamination_reasons": authority_reasons,
            "selection_method": selection_method,
        },
        "candidate": candidate if candidate_selected else {},
        "candidate_scope": candidate_scope if candidate_scope_complete else {},
        "envelope_preview": envelope_preview if ready else {},
        "standing_demo_authorization_validation": standing_summary,
        "materialization_plan": materialization_plan,
        "gates": gates,
        "blocking_gate_count": len(failed_gates),
        "blocking_gates": [gate["name"] for gate in failed_gates],
        "next_actions": next_actions,
        "summary": {
            "review_ready_no_runtime_mutation": ready,
            "proposed_runtime_envelope_path": (
                str(standing_demo_authorization_output_path) if path_valid else None
            ),
            "proposed_env_var": (
                standing_demo_authorization_env_var if env_valid else None
            ),
            "selected_side_cell_key": candidate.get("side_cell_key"),
            "standing_demo_authorization_preview_valid": preview_valid,
            "runtime_mutation_performed": False,
            "standing_envelope_materialized": False,
            "bounded_demo_probe_authorized": False,
            "operator_authorization_object_emitted": False,
            "max_safe_next_action": (
                "submit_runtime_materialization_plan_for_e3_review"
                if ready
                else "repair_blocking_gates_before_runtime_materialization_review"
            ),
        },
        "answers": {
            "source_only_research_artifact": True,
            "review_ready_no_runtime_mutation": ready,
            "runtime_mutation_performed": False,
            "env_mutation_performed": False,
            "crontab_mutation_performed": False,
            "standing_envelope_materialized": False,
            "standing_demo_authorization_valid": preview_valid,
            "standing_demo_authorization_consumed": False,
            "operator_authorization_object_emitted": False,
            "bounded_demo_probe_authorized": False,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "review_grants_runtime_authority": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "live_authority_granted": False,
            "mainnet_authority_granted": False,
            "order_submission_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "bybit_call_performed": False,
            "promotion_evidence": False,
            "promotion_proof": False,
            "profit_proof": False,
        },
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    summary = _dict(packet.get("summary"))
    lines = [
        "# Standing Demo Loss-Control Envelope Review",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Side-cell: `{summary.get('selected_side_cell_key')}`",
        f"- Runtime envelope path: `{summary.get('proposed_runtime_envelope_path')}`",
        f"- Env var: `{summary.get('proposed_env_var')}`",
        f"- Boundary: {BOUNDARY}.",
        "",
        "## Gates",
        "",
        "| gate | passed | status | reason |",
        "|---|---:|---|---|",
    ]
    for gate in packet.get("gates") or []:
        lines.append(
            f"| {gate.get('name')} | `{gate.get('passed')}` | "
            f"`{gate.get('status')}` | {gate.get('reason')} |"
        )
    lines.extend(["", "## Materialization Plan", ""])
    plan = _dict(packet.get("materialization_plan"))
    if not plan:
        lines.append("_No materialization plan emitted while gates are blocked._")
    else:
        lines.append("```json")
        lines.append(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
        lines.append("```")
    lines.extend(["", "## Envelope Preview", ""])
    envelope = _dict(packet.get("envelope_preview"))
    if not envelope:
        lines.append("_No envelope preview emitted while gates are blocked._")
    else:
        lines.append("```json")
        lines.append(json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True))
        lines.append("```")
    lines.extend(["", "## No-Authority Answers", ""])
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


def _same_path(left: Path | None, right: Path | None) -> bool:
    if left is None or right is None:
        return False
    return left.expanduser().resolve(strict=False) == right.expanduser().resolve(
        strict=False
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--false-negative-candidate-packet-json", type=Path, required=True)
    parser.add_argument("--selected-side-cell-key")
    parser.add_argument("--operator-id", default=DEFAULT_OPERATOR_ID)
    parser.add_argument(
        "--standing-demo-authorization-output-path",
        type=Path,
        default=DEFAULT_MATERIALIZATION_PATH,
        help="Proposed future runtime envelope path. This helper never writes it.",
    )
    parser.add_argument(
        "--standing-demo-authorization-env-var",
        default=DEFAULT_STANDING_ENV_VAR,
    )
    parser.add_argument(
        "--max-authorized-probe-orders",
        type=int,
        default=DEFAULT_MAX_AUTHORIZED_PROBE_ORDERS,
    )
    parser.add_argument(
        "--authorization-ttl-hours",
        type=int,
        default=DEFAULT_AUTHORIZATION_TTL_HOURS,
    )
    parser.add_argument(
        "--max-authorization-ttl-hours",
        type=int,
        default=DEFAULT_MAX_AUTHORIZATION_TTL_HOURS,
    )
    parser.add_argument("--max-artifact-age-hours", type=int, default=24)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet, err = _read_json(args.false_negative_candidate_packet_json)
    review = build_standing_demo_loss_control_envelope_review(
        false_negative_candidate_packet=packet,
        false_negative_candidate_packet_path=args.false_negative_candidate_packet_json,
        false_negative_candidate_packet_error=err,
        selected_side_cell_key=args.selected_side_cell_key,
        operator_id=args.operator_id,
        standing_demo_authorization_output_path=(
            args.standing_demo_authorization_output_path
        ),
        standing_demo_authorization_env_var=args.standing_demo_authorization_env_var,
        max_authorized_probe_orders=args.max_authorized_probe_orders,
        authorization_ttl_hours=args.authorization_ttl_hours,
        max_authorization_ttl_hours=args.max_authorization_ttl_hours,
        max_artifact_age_hours=args.max_artifact_age_hours,
    )
    materialization_path = args.standing_demo_authorization_output_path
    if _same_path(args.json_output, materialization_path) or _same_path(
        args.output, materialization_path
    ):
        raise SystemExit(
            "refusing to write review output to proposed runtime authorization path"
        )
    markdown = render_markdown(review)
    if args.json_output:
        _write_json(args.json_output, review)
    if args.output:
        _write_text(args.output, markdown)
    if args.print_json:
        print(json.dumps(review, ensure_ascii=False, sort_keys=True, default=str))
    elif not args.output and not args.json_output:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
