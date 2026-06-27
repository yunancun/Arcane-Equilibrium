#!/usr/bin/env python3
"""Review current-candidate order enablement readiness without enabling orders.

This helper is the machine-checkable bridge between source/runtime readiness and
an E3/BB exchange-facing enablement review. It consumes already-produced
no-order artifacts and runtime posture evidence, then emits either a
READY-for-review packet or a fail-closed loss-control packet.

It never enables the adapter/writer, never acquires a Decision Lease, never
calls Bybit, never submits/cancels/modifies orders, never writes PG, and never
grants order/live authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "current_candidate_order_enablement_review_v1"
READY_FOR_E3_BB_STATUS = (
    "CURRENT_CANDIDATE_ORDER_ENABLEMENT_READY_FOR_E3_BB_REVIEW_NO_ORDER"
)
BLOCKED_BY_LOSS_CONTROL_STATUS = (
    "CURRENT_CANDIDATE_ORDER_ENABLEMENT_BLOCKED_BY_LOSS_CONTROL"
)
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

DEPLOY_READY_STATUS = "RUNTIME_REBUILD_RESTART_DONE_WITH_CONCERNS_NO_ORDER"
GOVERNANCE_READY_STATUS = "RUNTIME_GOVERNANCE_IPC_READONLY_SNAPSHOT_READY"
ADMISSION_READY_STATUS = "CURRENT_CANDIDATE_BOUNDED_DEMO_ADMISSION_ENVELOPE_READY_NO_ORDER"
READINESS_READY_STATUS = "AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW"
ACTIVE_CALLER_READY_STATUS = "ACTIVE_CALLER_SOURCE_READY_FOR_E3_BB_REVIEW"

DEFAULT_MAX_ARTIFACT_AGE_SECONDS = 6 * 60 * 60
GUI_RISK_SOURCE = "GUI-backed Rust RiskConfig"

BOUNDARY = (
    "no-order current-candidate order enablement review; no adapter/writer "
    "enablement, no Decision Lease acquire/release, no Bybit/private/order "
    "call, no order/cancel/modify, no PG query/write, no runtime/service/env/"
    "crontab mutation, no Cost Gate lowering, no risk expansion, no live/"
    "mainnet authority, no execution, no fill/PnL, and no profit proof"
)

AUTHORITY_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "adapter_enabled",
    "adapter_enabled_by_this_packet",
    "adapter_enablement_performed",
    "allowed_to_submit_order",
    "allowed_to_submit_order_in_current_review",
    "bybit_call_performed",
    "bybit_private_call_performed",
    "config_mutation_performed",
    "cost_gate_lowering_performed",
    "cost_gate_lowering_recommended",
    "crontab_mutation_performed",
    "decision_lease_acquire_performed",
    "decision_lease_release_performed",
    "env_mutation_performed",
    "exchange_call_performed",
    "global_cost_gate_lowering_recommended",
    "lease_acquire_performed",
    "lease_release_performed",
    "live_authority_granted",
    "live_execution_allowed",
    "mainnet_authority_granted",
    "order_admission_ready",
    "order_authority_granted",
    "order_cancel_performed",
    "order_modify_performed",
    "order_submission_performed",
    "pg_query_performed",
    "pg_write_performed",
    "probe_authority_granted",
    "promotion_evidence",
    "promotion_proof",
    "risk_expansion",
    "risk_mutation_performed",
    "runtime_admission_ready",
    "runtime_adapter_enablement_performed",
    "runtime_mutation_performed",
    "service_restart_performed",
    "writer_enabled",
    "writer_enablement_performed",
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


def _first_float(*values: Any) -> float | None:
    for value in values:
        parsed = _float(value)
        if parsed is not None:
            return parsed
    return None


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
    generated_at = payload.get("generated_at_utc") or payload.get("generated") or payload.get(
        "ts_utc"
    )
    parsed = _parse_dt(generated_at)
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
    required: bool = True,
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
        "status": _dict(payload).get("status") if present else None,
        "schema_version": _dict(payload).get("schema_version") if present else None,
        "generated_at_utc": _dict(payload).get("generated_at_utc") if present else None,
        "age_seconds": age,
        "fresh": fresh,
        "blockers": blockers,
    }


def _candidate_key(payload: dict[str, Any]) -> str | None:
    candidate = _dict(payload.get("candidate"))
    key = _str(candidate.get("side_cell_key"))
    if key:
        return key
    strategy = _str(candidate.get("strategy_name"))
    symbol = _str(candidate.get("symbol"))
    side = _str(candidate.get("side"))
    if strategy and symbol and side:
        return f"{strategy}|{symbol}|{side}"
    return None


def _recursive_authority_violation(payload: Any) -> str | None:
    stack: list[tuple[str, Any]] = [("$", payload)]
    while stack:
        path, node = stack.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                child_path = f"{path}.{key}"
                if key in AUTHORITY_TRUE_KEYS and _truthy(value):
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


def _readiness_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    packet = _dict(payload)
    active = _dict(packet.get("active_caller_enablement_review"))
    evidence = _dict(active.get("evidence"))
    answers = _dict(packet.get("answers"))
    blockers: list[str] = []
    if packet.get("status") != READINESS_READY_STATUS:
        blockers.append("readiness_status_not_ready")
    if active.get("status") != ACTIVE_CALLER_READY_STATUS:
        blockers.append("active_caller_not_source_ready")
    if active.get("active_caller_source_ready_for_review") is not True:
        blockers.append("active_caller_source_ready_false")
    if evidence.get("runtime_active_order_request_supplier_present") is not True:
        blockers.append("runtime_active_order_request_supplier_missing")
    if evidence.get("runtime_active_order_request_supplier_contract_missing") not in (
        [],
        None,
    ):
        blockers.append("runtime_active_order_request_supplier_contract_missing")
    if evidence.get("suspicious_hardcoded_local_10_usdt_cap_matches") not in ([], None):
        blockers.append("hardcoded_local_10_usdt_supplier_match")
    if answers.get("allowed_to_submit_order") is not False:
        blockers.append("readiness_allowed_to_submit_order_not_false")
    return {
        "status": packet.get("status"),
        "active_caller_status": active.get("status"),
        "runtime_active_order_request_supplier_present": evidence.get(
            "runtime_active_order_request_supplier_present"
        ),
        "supplier_contract_missing": evidence.get(
            "runtime_active_order_request_supplier_contract_missing"
        ),
        "hardcoded_local_10_matches": evidence.get(
            "suspicious_hardcoded_local_10_usdt_cap_matches"
        ),
        "blockers": blockers,
    }


def _admission_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    packet = _dict(payload)
    answers = _dict(packet.get("answers"))
    risk = _dict(packet.get("risk_semantics"))
    preview = _dict(packet.get("admission_envelope_preview"))
    limits = _dict(preview.get("risk_limits"))
    blockers: list[str] = []
    if packet.get("status") != ADMISSION_READY_STATUS:
        blockers.append("admission_status_not_ready_no_order")
    if packet.get("failed_gates") not in ([], None):
        blockers.append("admission_failed_gates_present")
    if packet.get("runtime_blockers") not in ([], None):
        blockers.append("admission_runtime_blockers_present")
    if packet.get("source_blockers") not in ([], None):
        blockers.append("admission_source_blockers_present")
    if packet.get("authority_contamination_reasons") not in ([], None):
        blockers.append("admission_authority_contamination_present")
    if answers.get("runtime_admission_ready") is not False:
        blockers.append("admission_runtime_admission_ready_not_false")
    if answers.get("order_admission_ready") is not False:
        blockers.append("admission_order_admission_ready_not_false")
    if answers.get("order_submission_performed") is not False:
        blockers.append("admission_order_submission_not_false")

    gui_source = (
        risk.get("gui_risk_config_is_source_of_truth") is True
        or risk.get("risk_source_of_truth") == GUI_RISK_SOURCE
        or limits.get("risk_source_of_truth") == GUI_RISK_SOURCE
    )
    pct_fraction = _float(
        risk.get("per_trade_risk_pct_fraction")
        or limits.get("per_trade_risk_pct_fraction")
        or risk.get("per_trade_risk_pct")
        or limits.get("per_trade_risk_pct")
    )
    pct_display = _float(
        risk.get("gui_p1_risk_trade_pct")
        or risk.get("per_trade_risk_pct_display")
        or limits.get("per_trade_risk_pct_display")
    )
    position_pct = _float(risk.get("position_size_max_pct") or limits.get("position_size_max_pct"))
    per_trade_budget = _float(risk.get("per_trade_budget_usdt") or limits.get("per_trade_budget_usdt"))
    single_position_budget = _first_float(
        risk.get("single_position_budget_usdt"),
        limits.get("single_position_budget_usdt"),
    )
    max_order_notional = _first_float(
        risk.get("max_order_notional_usdt"),
        limits.get("max_order_notional_usdt"),
    )
    effective_cap = _first_float(
        risk.get("effective_single_order_cap_usdt"),
        limits.get("effective_single_order_cap_usdt"),
        risk.get("resolved_cap_usdt"),
        limits.get("resolved_cap_usdt"),
        limits.get("per_order_cap_usdt"),
    )
    local_10_authority = (
        risk.get("local_10_usdt_cap_is_global_risk_authority")
        or risk.get("bounded_probe_local_cap_usdt_is_authority")
        or limits.get("bounded_probe_local_cap_usdt_is_authority")
    )

    if not gui_source:
        blockers.append("gui_risk_config_not_source_of_truth")
    if pct_fraction is None or abs(pct_fraction - 0.1) > 1e-9:
        blockers.append("per_trade_risk_pct_fraction_not_0_1")
    if pct_display is None or abs(pct_display - 10.0) > 1e-9:
        blockers.append("gui_p1_risk_trade_not_10_percent")
    if position_pct is None or abs(position_pct - 25.0) > 1e-9:
        blockers.append("position_size_max_pct_not_25")
    if per_trade_budget is None or per_trade_budget <= 10.0:
        blockers.append("per_trade_budget_not_equity_resolved")
    if single_position_budget is None or single_position_budget <= 10.0:
        blockers.append("single_position_budget_not_equity_resolved")
    if effective_cap is None or effective_cap <= 10.0:
        blockers.append("effective_single_order_cap_not_gui_resolved")
    if (
        effective_cap is not None
        and per_trade_budget is not None
        and effective_cap > per_trade_budget + 1e-8
    ):
        blockers.append("effective_single_order_cap_exceeds_per_trade_budget")
    if (
        effective_cap is not None
        and single_position_budget is not None
        and effective_cap > single_position_budget + 1e-8
    ):
        blockers.append("effective_single_order_cap_exceeds_single_position_budget")
    if (
        effective_cap is not None
        and max_order_notional is not None
        and max_order_notional > 0.0
        and effective_cap > max_order_notional + 1e-8
    ):
        blockers.append("effective_single_order_cap_exceeds_max_order_notional")
    if local_10_authority is not False:
        blockers.append("local_10_usdt_cap_marked_authority")

    return {
        "status": packet.get("status"),
        "candidate": _candidate_key(packet),
        "gui_risk_config_is_source_of_truth": gui_source,
        "per_trade_risk_pct_fraction": pct_fraction,
        "gui_p1_risk_trade_pct": pct_display,
        "position_size_max_pct": position_pct,
        "per_trade_budget_usdt": per_trade_budget,
        "single_position_budget_usdt": single_position_budget,
        "max_order_notional_usdt": max_order_notional,
        "effective_single_order_cap_usdt": effective_cap,
        "local_10_usdt_cap_is_authority": local_10_authority,
        "blockers": blockers,
    }


def _governance_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    packet = _dict(payload)
    summary = _dict(packet.get("summary"))
    blockers: list[str] = []
    if packet.get("status") != GOVERNANCE_READY_STATUS:
        blockers.append("governance_snapshot_not_ready")
    if summary.get("risk_level") != "NORMAL":
        blockers.append("guardian_not_normal")
    if _float(summary.get("position_size_multiplier")) != 1.0:
        blockers.append("guardian_multiplier_not_one")
    if _float(summary.get("lease_live_count")) != 0.0:
        blockers.append("lease_live_count_nonzero_before_enablement")
    if _float(summary.get("lease_count")) != 0.0:
        blockers.append("lease_count_nonzero_before_enablement")
    if packet.get("runtime_blockers") not in ([], None):
        blockers.append("governance_runtime_blockers_present")
    return {
        "status": packet.get("status"),
        "risk_level": summary.get("risk_level"),
        "position_size_multiplier": _float(summary.get("position_size_multiplier")),
        "lease_live_count": summary.get("lease_live_count"),
        "lease_count": summary.get("lease_count"),
        "blockers": blockers,
    }


def _deploy_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    packet = _dict(payload)
    deploy = _dict(packet.get("deploy"))
    posture = _dict(packet.get("runtime_posture"))
    blockers: list[str] = []
    if packet.get("status") != DEPLOY_READY_STATUS:
        blockers.append("deploy_status_not_ready")
    if deploy.get("atomic_sha_verified") is not True:
        blockers.append("deploy_atomic_sha_not_verified")
    if deploy.get("running_proc_sha256") != deploy.get("disk_sha256"):
        blockers.append("deploy_proc_disk_sha_mismatch")
    if posture.get("OPENCLAW_ALLOW_MAINNET") not in ("0", 0, False):
        blockers.append("mainnet_env_not_zero")
    if posture.get("OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED") not in ("", None, "0", 0, False):
        blockers.append("bounded_probe_adapter_enabled_before_review")
    if posture.get("OPENCLAW_DEMO_LEARNING_LANE_WRITER") not in ("", None, "0", 0, False):
        blockers.append("demo_learning_lane_writer_enabled_before_review")
    return {
        "status": packet.get("status"),
        "runtime_head": _dict(packet.get("runtime_source")).get("head"),
        "engine_pid": deploy.get("new_engine_pid"),
        "running_proc_sha256": deploy.get("running_proc_sha256"),
        "disk_sha256": deploy.get("disk_sha256"),
        "atomic_sha_verified": deploy.get("atomic_sha_verified"),
        "OPENCLAW_ALLOW_MAINNET": posture.get("OPENCLAW_ALLOW_MAINNET"),
        "OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED": posture.get(
            "OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED"
        ),
        "OPENCLAW_DEMO_LEARNING_LANE_WRITER": posture.get(
            "OPENCLAW_DEMO_LEARNING_LANE_WRITER"
        ),
        "blockers": blockers,
    }


def _all_blockers(*summaries: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    for summary in summaries:
        blockers.extend(_list(summary.get("blockers")))
    return sorted(set(str(item) for item in blockers if item))


def build_current_candidate_order_enablement_review(
    *,
    readiness_packet: dict[str, Any] | None,
    admission_review: dict[str, Any] | None,
    governance_snapshot: dict[str, Any] | None,
    deploy_manifest: dict[str, Any] | None,
    candidate_side_cell_key: str | None = None,
    now_utc: dt.datetime | None = None,
    max_artifact_age_seconds: int = DEFAULT_MAX_ARTIFACT_AGE_SECONDS,
    readiness_path: Path | None = None,
    admission_path: Path | None = None,
    governance_path: Path | None = None,
    deploy_path: Path | None = None,
) -> dict[str, Any]:
    if max_artifact_age_seconds <= 0 or max_artifact_age_seconds > 14 * 24 * 3600:
        raise ValueError("max_artifact_age_seconds must be in (0, 1209600]")

    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    artifacts = {
        "readiness": _artifact_summary(
            name="readiness",
            path=readiness_path,
            payload=readiness_packet,
            now_utc=now,
            max_age_seconds=max_artifact_age_seconds,
        ),
        "admission": _artifact_summary(
            name="admission",
            path=admission_path,
            payload=admission_review,
            now_utc=now,
            max_age_seconds=max_artifact_age_seconds,
        ),
        "governance": _artifact_summary(
            name="governance",
            path=governance_path,
            payload=governance_snapshot,
            now_utc=now,
            max_age_seconds=max_artifact_age_seconds,
        ),
        "deploy": _artifact_summary(
            name="deploy",
            path=deploy_path,
            payload=deploy_manifest,
            now_utc=now,
            max_age_seconds=max_artifact_age_seconds,
        ),
    }

    readiness = _readiness_summary(readiness_packet)
    admission = _admission_summary(admission_review)
    governance = _governance_summary(governance_snapshot)
    deploy = _deploy_summary(deploy_manifest)

    candidate_keys = {
        key
        for key in (
            candidate_side_cell_key,
            _candidate_key(_dict(readiness_packet)),
            _candidate_key(_dict(admission_review)),
        )
        if key
    }
    candidate_blockers: list[str] = []
    if candidate_side_cell_key and candidate_keys != {candidate_side_cell_key}:
        candidate_blockers.append("candidate_identity_mismatch")
    if not candidate_keys:
        candidate_blockers.append("candidate_identity_missing")

    artifact_blockers = [
        blocker
        for artifact in artifacts.values()
        for blocker in _list(artifact.get("blockers"))
    ]
    authority_violation = _recursive_authority_violation(
        {
            "readiness": readiness_packet or {},
            "admission": admission_review or {},
            "governance": governance_snapshot or {},
            "deploy": deploy_manifest or {},
        }
    )
    review_blockers = _all_blockers(readiness, admission, governance, deploy)
    loss_control_blockers = sorted(
        set(artifact_blockers + candidate_blockers + review_blockers)
    )

    if authority_violation:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = f"input_contains_authority_or_mutation_field:{authority_violation}"
    elif loss_control_blockers:
        status = BLOCKED_BY_LOSS_CONTROL_STATUS
        reason = "enablement_review_inputs_not_ready_or_loss_control_blocked"
    else:
        status = READY_FOR_E3_BB_STATUS
        reason = "source_runtime_no_order_evidence_ready_for_e3_bb_enablement_review"

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "candidate": {
            "requested_side_cell_key": candidate_side_cell_key,
            "observed_side_cell_keys": sorted(candidate_keys),
        },
        "artifacts": artifacts,
        "readiness_review": readiness,
        "admission_review": admission,
        "governance_review": governance,
        "deploy_review": deploy,
        "loss_control_blockers": loss_control_blockers,
        "authority_boundary_violation": authority_violation,
        "max_safe_next_action": (
            "E3_BB_ENABLEMENT_REVIEW_ONLY_NO_ORDER"
            if status == READY_FOR_E3_BB_STATUS
            else "REPAIR_OR_REFRESH_BLOCKED_INPUTS_NO_ORDER"
        ),
        "required_same_window_gates_before_order_capable_action": [
            "explicit_E3_BB_exchange_facing_enablement_review",
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
            "e3_bb_enablement_review_ready": status == READY_FOR_E3_BB_STATUS,
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
            "bybit_private_call_performed": False,
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
        "artifact_self_hash_sha256": None,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    candidate = _dict(packet.get("candidate"))
    answers = _dict(packet.get("answers"))
    lines = [
        "# Current Candidate Order Enablement Review",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Requested candidate: `{candidate.get('requested_side_cell_key')}`",
        f"- Observed candidates: `{candidate.get('observed_side_cell_keys')}`",
        f"- E3/BB review ready: `{answers.get('e3_bb_enablement_review_ready')}`",
        f"- Order-capable action allowed: `{answers.get('order_capable_action_allowed')}`",
        f"- Max safe next action: `{packet.get('max_safe_next_action')}`",
    ]
    admission = _dict(packet.get("admission_review"))
    if admission:
        lines.extend(
            [
                f"- GUI P1 risk/trade: `{admission.get('gui_p1_risk_trade_pct')}%`",
                f"- GUI max single position: `{admission.get('position_size_max_pct')}%`",
                f"- Per-trade budget USDT: `{admission.get('per_trade_budget_usdt')}`",
                f"- Single-position budget USDT: `{admission.get('single_position_budget_usdt')}`",
                f"- Effective single-order cap USDT: `{admission.get('effective_single_order_cap_usdt')}`",
            ]
        )
    lines.extend(["", "## Loss-Control Blockers"])
    blockers = _list(packet.get("loss_control_blockers"))
    lines.extend(f"- `{blocker}`" for blocker in blockers) if blockers else lines.append("- none")
    lines.extend(["", "## Required Same-Window Gates Before Order", ""])
    for item in _list(packet.get("required_same_window_gates_before_order_capable_action")):
        lines.append(f"- `{item}`")
    lines.extend(["", "## Boundary", "", str(packet.get("boundary", ""))])
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readiness-json", type=Path, required=True)
    parser.add_argument("--admission-review-json", type=Path, required=True)
    parser.add_argument("--governance-snapshot-json", type=Path, required=True)
    parser.add_argument("--deploy-manifest-json", type=Path, required=True)
    parser.add_argument("--candidate-side-cell-key")
    parser.add_argument("--max-artifact-age-seconds", type=int, default=DEFAULT_MAX_ARTIFACT_AGE_SECONDS)
    parser.add_argument("--now-utc")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    now = _parse_dt(args.now_utc) if args.now_utc else None
    packet = build_current_candidate_order_enablement_review(
        readiness_packet=_read_json(args.readiness_json),
        admission_review=_read_json(args.admission_review_json),
        governance_snapshot=_read_json(args.governance_snapshot_json),
        deploy_manifest=_read_json(args.deploy_manifest_json),
        candidate_side_cell_key=args.candidate_side_cell_key,
        now_utc=now,
        max_artifact_age_seconds=args.max_artifact_age_seconds,
        readiness_path=args.readiness_json,
        admission_path=args.admission_review_json,
        governance_path=args.governance_snapshot_json,
        deploy_path=args.deploy_manifest_json,
    )
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.output:
        _write_text(args.output, render_markdown(packet))
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if packet["status"] == READY_FOR_E3_BB_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
