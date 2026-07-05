#!/usr/bin/env python3
"""Build a no-authority lower-price reroute review for bounded Demo probes.

This packet consumes the BTC order-construction repair packet and candidate-
specific false-negative bounded-probe artifacts. It selects exactly one
cap-feasible lower-price candidate for the next no-order construction review.
It can also consume a timestamped cap-feasible selection wrapper so a selected
candidate is not forced back through a stale repair packet.

It never queries or writes PG, calls Bybit, submits orders, mutates plans,
lowers the Cost Gate, grants probe/order/live authority, appends ledgers, or
creates promotion proof.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from typing import Any

# 共用純函數葉節點：以 alias-import 保持函數體內 _dict/_list/_str/_utc_now 引用逐字節不變。
from cost_gate_learning_lane._lane_common import (
    as_dict as _dict,
    as_list as _list,
    as_str as _str,
    utc_now as _utc_now,
)


LOWER_PRICE_REROUTE_REVIEW_SCHEMA_VERSION = (
    "bounded_demo_probe_lower_price_reroute_review_v1"
)
ORDER_CONSTRUCTION_REPAIR_SCHEMA_VERSION = (
    "bounded_demo_probe_order_construction_repair_v1"
)
CAP_FEASIBLE_SELECTION_SCHEMA_VERSION = (
    "bounded_demo_probe_cap_feasible_candidate_selection_review_v1"
)
FALSE_NEGATIVE_PREFLIGHT_SCHEMA_VERSION = (
    "cost_gate_false_negative_bounded_demo_probe_preflight_v1"
)
FALSE_NEGATIVE_OPERATOR_REVIEW_SCHEMA_VERSION = (
    "cost_gate_false_negative_operator_review_v1"
)
PLACEMENT_REPAIR_PLAN_SCHEMA_VERSION = (
    "bounded_demo_probe_placement_repair_plan_v1"
)
OPERATOR_AUTHORIZATION_PACKET_SCHEMA_VERSION = (
    "bounded_demo_probe_operator_authorization_packet_v1"
)
AUTHORITY_PATCH_READINESS_SCHEMA_VERSION = (
    "bounded_demo_probe_authority_patch_readiness_v1"
)
TOUCHABILITY_PREFLIGHT_SCHEMA_VERSION = "bounded_demo_probe_touchability_preflight_v1"

ORDER_CONSTRUCTION_REPAIR_READY_STATUS = "ORDER_CONSTRUCTION_REPAIR_REQUIRED"
CAP_FEASIBLE_SELECTION_READY_STATUS = (
    "CAP_FEASIBLE_CANDIDATE_SELECTED_FOR_PREFLIGHT_REVIEW"
)
READY_STATUS = "LOWER_PRICE_REROUTE_READY_FOR_DEMO_CONSTRUCTION_REVIEW"
INPUT_REQUIRED_STATUS = "LOWER_PRICE_REROUTE_INPUT_REQUIRED"
NOT_FEASIBLE_STATUS = "LOWER_PRICE_REROUTE_CANDIDATE_NOT_FEASIBLE"
ALIGNMENT_BLOCKED_STATUS = "LOWER_PRICE_REROUTE_ALIGNMENT_BLOCKED"
AUTHORITY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"
FALSE_NEGATIVE_PREFLIGHT_READY_STATUS = (
    "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION"
)
FALSE_NEGATIVE_REVIEW_APPROVED_STATUS = (
    "APPROVED_COST_GATE_FALSE_NEGATIVE_FOR_BOUNDED_DEMO_PROBE_PREFLIGHT"
)
PLACEMENT_REPAIR_READY_STATUS = "PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW"
OPERATOR_AUTHORIZATION_REVIEW_READY_STATUS = "READY_FOR_OPERATOR_AUTHORIZATION_REVIEW"
AUTHORITY_PATH_READY_STATUS = "AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW"

DEFAULT_MAX_ARTIFACT_AGE_HOURS = 24
BOUNDARY = (
    "artifact-only lower-price bounded Demo reroute review; no PG query/write, "
    "Bybit call, order, config, risk, auth, runtime mutation, global Cost Gate "
    "lowering, probe authority, order authority, live/mainnet authority, ledger "
    "append, or promotion proof"
)

DANGER_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "bounded_demo_probe_authorized",
    "bybit_call_performed",
    "canonical_plan_mutation_performed",
    "cost_gate_lowering_recommended",
    "global_cost_gate_lowering_recommended",
    "ledger_append_performed",
    "live_authority_granted",
    "mainnet_authority_granted",
    "operator_authorization_object_emitted",
    "order_authority_granted",
    "order_authority_granted_in_authorization_object",
    "order_submission_performed",
    "pg_write_performed",
    "pg_query_performed",
    "plan_mutation_performed",
    "probe_authority_granted",
    "probe_authority_granted_in_authorization_object",
    "promotion_evidence",
    "promotion_proof",
    "cost_gate_mutation_found",
    "live_promotion_performed",
    "runtime_mutation_performed",
    "runtime_order_authority_granted",
    "runtime_order_authority_found",
    "runtime_probe_authority_granted",
    "runtime_probe_authority_found",
    "review_grants_runtime_authority",
    "service_restart_performed",
    "writer_enabled",
}


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _round(value: Any, ndigits: int = 6) -> float | None:
    parsed = _float(value)
    return round(parsed, ndigits) if parsed is not None else None


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
    return (
        payload.get("generated_at_utc")
        or payload.get("generated")
        or payload.get("ts_utc")
    )


def _artifact_summary(
    *,
    name: str,
    path: Path | None,
    payload: dict[str, Any] | None,
    now_utc: dt.datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    present = isinstance(payload, dict) and bool(payload)
    generated_at = _generated_at(payload or {}) if present else None
    age = _age_seconds(generated_at, now_utc=now_utc) if generated_at else None
    if not present:
        status = "MISSING"
    elif age is None:
        status = "PRESENT_UNKNOWN_AGE"
    elif age > max_age_seconds:
        status = "STALE"
    else:
        status = "FRESH"
    sha256 = None
    size_bytes = None
    mtime_epoch_seconds = None
    if path and path.exists() and path.is_file():
        data = path.read_bytes()
        sha256 = hashlib.sha256(data).hexdigest()
        size_bytes = len(data)
        mtime_epoch_seconds = int(path.stat().st_mtime)
    return {
        "name": name,
        "path": str(path) if path else None,
        "sha256": sha256,
        "size_bytes": size_bytes,
        "mtime_epoch_seconds": mtime_epoch_seconds,
        "status": status,
        "present": present,
        "generated_at_utc": generated_at,
        "age_seconds": age,
        "max_age_seconds": max_age_seconds,
        "schema_version": (payload or {}).get("schema_version") if present else None,
    }


def _contaminating_value(value: Any) -> bool:
    if value is None or value is False:
        return False
    if value is True:
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "none", "null"}
    if isinstance(value, (dict, list, tuple, set)):
        return len(value) > 0
    return True


def _iter_nodes(value: Any) -> list[Any]:
    out = [value]
    if isinstance(value, dict):
        for child in value.values():
            out.extend(_iter_nodes(child))
    elif isinstance(value, list):
        for child in value:
            out.extend(_iter_nodes(child))
    return out


def _authority_preserved_named(
    payloads: dict[str, dict[str, Any] | None],
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    for source_name, payload in payloads.items():
        source_payload = _dict(payload)
        answers_node = _dict(source_payload.get("answers"))
        for node in _iter_nodes(_dict(payload)):
            if not isinstance(node, dict):
                continue
            for key, value in node.items():
                allowed_readonly_pg_evidence = (
                    source_name == "cap_feasible_selection"
                    and key == "pg_query_performed"
                    and node is answers_node
                )
                if (
                    key in DANGER_KEYS
                    and not allowed_readonly_pg_evidence
                    and _contaminating_value(value)
                ):
                    reasons.append(f"{key}_contaminating")
            if _str(node.get("main_cost_gate_adjustment")).upper() not in ("", "NONE"):
                reasons.append("main_cost_gate_adjustment_not_none")
    return not reasons, sorted(set(reasons))


def _authority_preserved(*payloads: dict[str, Any] | None) -> tuple[bool, list[str]]:
    return _authority_preserved_named(
        {f"payload_{idx}": payload for idx, payload in enumerate(payloads)}
    )


def _candidate_from_packet(packet: dict[str, Any] | None) -> dict[str, Any]:
    payload = _dict(packet)
    candidate = _dict(payload.get("candidate"))
    if not candidate and payload.get("selected_side_cell_key"):
        candidate = {"side_cell_key": payload.get("selected_side_cell_key")}
    symbols = _list(candidate.get("symbols"))
    sides = _list(candidate.get("sides"))
    strategies = _list(candidate.get("strategy_names"))
    horizons = _list(candidate.get("horizon_minutes"))
    return {
        "side_cell_key": candidate.get("side_cell_key")
        or payload.get("side_cell_key")
        or payload.get("selected_side_cell_key"),
        "strategy_name": candidate.get("strategy_name")
        or (strategies[0] if strategies else None),
        "symbol": candidate.get("symbol") or (symbols[0] if symbols else None),
        "side": candidate.get("side") or (sides[0] if sides else None),
        "outcome_horizon_minutes": (
            candidate.get("outcome_horizon_minutes")
            or candidate.get("dominant_horizon_minutes")
            or (horizons[0] if horizons else None)
        ),
    }


def _candidate_key(candidate: dict[str, Any]) -> tuple[Any, Any, Any, Any, Any]:
    return (
        candidate.get("side_cell_key"),
        candidate.get("strategy_name"),
        candidate.get("symbol"),
        candidate.get("side"),
        _normalized_horizon(candidate.get("outcome_horizon_minutes")),
    )


def _normalized_horizon(value: Any) -> int | None:
    parsed = _float(value)
    if parsed is None or not parsed.is_integer():
        return None
    return int(parsed)


def _candidate_identity_complete(candidate: dict[str, Any]) -> bool:
    return (
        bool(_str(candidate.get("side_cell_key")))
        and bool(_str(candidate.get("strategy_name")))
        and bool(_str(candidate.get("symbol")))
        and bool(_str(candidate.get("side")))
        and _normalized_horizon(candidate.get("outcome_horizon_minutes")) is not None
    )


def _candidate_instrument_trading(candidate: dict[str, Any]) -> bool:
    return _str(candidate.get("instrument_status")) == "Trading"


def _candidate_feasible(candidate: dict[str, Any]) -> bool:
    return (
        _dict(candidate).get("fits_current_cap") is True
        and _candidate_identity_complete(candidate)
        and _candidate_instrument_trading(candidate)
    )


def _candidate_aligned(selected: dict[str, Any], packet: dict[str, Any] | None) -> bool:
    candidate = _candidate_from_packet(packet)
    selected_key = _candidate_key(selected)
    candidate_key = _candidate_key(candidate)
    return (
        _candidate_identity_complete(selected)
        and _candidate_identity_complete(candidate)
        and selected_key == candidate_key
    )


def _feasible_candidates(repair_packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _list(_dict(repair_packet.get("candidate_universe_screen")).get("rows"))
    return [row for row in rows if _candidate_feasible(_dict(row))]


def _cap_feasible_selection_candidate(packet: dict[str, Any] | None) -> dict[str, Any]:
    return _dict(_dict(packet).get("selected_candidate"))


def _current_cap_usdt(candidate: dict[str, Any]) -> Any:
    current_cap = candidate.get("current_cap_usdt")
    return candidate.get("cap_usdt") if current_cap is None else current_cap


def _cap_feasible_selection_ready(
    packet: dict[str, Any],
    artifacts: dict[str, dict[str, Any]],
) -> bool:
    candidate = _cap_feasible_selection_candidate(packet)
    return (
        _artifact_gate(
            artifacts,
            "cap_feasible_selection",
            schema=CAP_FEASIBLE_SELECTION_SCHEMA_VERSION,
        )
        and _dict(packet).get("status") == CAP_FEASIBLE_SELECTION_READY_STATUS
        and _candidate_feasible(candidate)
    )


def _candidate_source_candidates(
    repair_packet: dict[str, Any],
    cap_feasible_selection: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], str]:
    cap_candidate = _cap_feasible_selection_candidate(cap_feasible_selection)
    if cap_candidate:
        return (
            [_dict(cap_candidate)] if _candidate_feasible(cap_candidate) else [],
            "cap_feasible_selection",
        )
    return _feasible_candidates(repair_packet), "order_construction_repair"


def _select_candidate(
    repair_packet: dict[str, Any],
    *,
    cap_feasible_selection: dict[str, Any] | None,
    selected_side_cell_key: str | None,
) -> tuple[dict[str, Any] | None, list[str], str, int]:
    feasible, source = _candidate_source_candidates(
        repair_packet, cap_feasible_selection
    )
    feasible = [_dict(row) for row in feasible]
    if selected_side_cell_key:
        matches = [
            row for row in feasible if _str(row.get("side_cell_key")) == selected_side_cell_key
        ]
        if len(matches) != 1:
            return (
                None,
                ["selected_side_cell_key_not_exactly_one_feasible_candidate"],
                source,
                len(feasible),
            )
        return matches[0], [], source, len(feasible)
    if len(feasible) < 1:
        return None, ["no_cap_feasible_lower_price_candidate"], source, len(feasible)
    if len(feasible) > 1:
        return (
            None,
            ["explicit_side_cell_key_required_when_multiple_feasible_candidates"],
            source,
            len(feasible),
        )
    top = feasible[0]
    duplicate_top = [
        row
        for row in feasible
        if _str(row.get("side_cell_key")) == _str(top.get("side_cell_key"))
    ]
    if len(duplicate_top) != 1:
        return None, ["top_side_cell_key_not_unique"], source, len(feasible)
    return top, [], source, len(feasible)


def _artifact_gate(
    artifacts: dict[str, dict[str, Any]],
    name: str,
    *,
    schema: str,
) -> bool:
    artifact = artifacts[name]
    return artifact.get("status") == "FRESH" and artifact.get("schema_version") == schema


def _repair_ready(packet: dict[str, Any], artifacts: dict[str, dict[str, Any]]) -> bool:
    lower_option = None
    for option in _list(packet.get("repair_options")):
        option = _dict(option)
        if option.get("option_id") == "lower_price_candidate_reroute_screen":
            lower_option = option
            break
    return (
        _artifact_gate(
            artifacts,
            "order_construction_repair",
            schema=ORDER_CONSTRUCTION_REPAIR_SCHEMA_VERSION,
        )
        and packet.get("status") == ORDER_CONSTRUCTION_REPAIR_READY_STATUS
        and _dict(packet.get("source_candidate_universe")).get(
            "valid_for_reroute_screen"
        )
        is True
        and _dict(lower_option).get("status") == "AVAILABLE"
    )


def _candidate_source_ready(
    *,
    repair_packet: dict[str, Any],
    cap_feasible_selection: dict[str, Any] | None,
    candidate_source: str,
    artifacts: dict[str, dict[str, Any]],
) -> tuple[bool, list[str]]:
    repair_ready = _repair_ready(repair_packet, artifacts)
    selection_ready = _cap_feasible_selection_ready(
        _dict(cap_feasible_selection), artifacts
    )
    if candidate_source == "cap_feasible_selection":
        if selection_ready:
            return True, []
        return False, ["cap_feasible_candidate_selection_ready"]
    if repair_ready:
        return True, []
    return False, ["order_construction_repair_ready"]


def _readiness_gates(
    *,
    selected: dict[str, Any],
    artifacts: dict[str, dict[str, Any]],
    false_negative_preflight: dict[str, Any] | None,
    false_negative_operator_review: dict[str, Any] | None,
    placement_repair_plan: dict[str, Any] | None,
    operator_authorization: dict[str, Any] | None,
    authority_patch_readiness: dict[str, Any] | None,
    touchability_preflight: dict[str, Any] | None,
) -> dict[str, Any]:
    gates = {
        "false_negative_preflight_ready": (
            _artifact_gate(
                artifacts,
                "false_negative_preflight",
                schema=FALSE_NEGATIVE_PREFLIGHT_SCHEMA_VERSION,
            )
            and _dict(false_negative_preflight).get("status")
            == FALSE_NEGATIVE_PREFLIGHT_READY_STATUS
            and _candidate_aligned(selected, false_negative_preflight)
        ),
        "false_negative_operator_review_approved": (
            _artifact_gate(
                artifacts,
                "false_negative_operator_review",
                schema=FALSE_NEGATIVE_OPERATOR_REVIEW_SCHEMA_VERSION,
            )
            and _dict(false_negative_operator_review).get("status")
            == FALSE_NEGATIVE_REVIEW_APPROVED_STATUS
            and _candidate_aligned(selected, false_negative_operator_review)
        ),
        "placement_repair_plan_ready": (
            _artifact_gate(
                artifacts,
                "placement_repair_plan",
                schema=PLACEMENT_REPAIR_PLAN_SCHEMA_VERSION,
            )
            and _dict(placement_repair_plan).get("status") == PLACEMENT_REPAIR_READY_STATUS
            and _candidate_aligned(selected, placement_repair_plan)
        ),
        "operator_authorization_review_ready_no_authority": (
            _artifact_gate(
                artifacts,
                "operator_authorization",
                schema=OPERATOR_AUTHORIZATION_PACKET_SCHEMA_VERSION,
            )
            and _dict(operator_authorization).get("status")
            == OPERATOR_AUTHORIZATION_REVIEW_READY_STATUS
            and _candidate_aligned(selected, operator_authorization)
            and _dict(_dict(operator_authorization).get("answers")).get(
                "operator_authorization_object_emitted"
            )
            is not True
        ),
        "authority_path_patch_ready": (
            _artifact_gate(
                artifacts,
                "authority_patch_readiness",
                schema=AUTHORITY_PATCH_READINESS_SCHEMA_VERSION,
            )
            and _dict(authority_patch_readiness).get("status")
            == AUTHORITY_PATH_READY_STATUS
            and _dict(_dict(authority_patch_readiness).get("answers")).get(
                "rust_patch_required"
            )
            is False
        ),
        "touchability_preflight_fresh_candidate_matched": (
            _artifact_gate(
                artifacts,
                "touchability_preflight",
                schema=TOUCHABILITY_PREFLIGHT_SCHEMA_VERSION,
            )
            and _candidate_aligned(selected, touchability_preflight)
        ),
    }
    return {
        "gates": gates,
        "blocking_gates": [name for name, passed in gates.items() if passed is not True],
        "blocking_gate_count": sum(1 for passed in gates.values() if passed is not True),
    }


def build_lower_price_reroute_review(
    *,
    order_construction_repair: dict[str, Any] | None,
    cap_feasible_selection: dict[str, Any] | None = None,
    false_negative_preflight: dict[str, Any] | None = None,
    false_negative_operator_review: dict[str, Any] | None = None,
    placement_repair_plan: dict[str, Any] | None = None,
    operator_authorization: dict[str, Any] | None = None,
    authority_patch_readiness: dict[str, Any] | None = None,
    touchability_preflight: dict[str, Any] | None = None,
    selected_side_cell_key: str | None = None,
    demo_operational_authorization_available: bool = False,
    now_utc: dt.datetime | None = None,
    max_artifact_age_hours: int = DEFAULT_MAX_ARTIFACT_AGE_HOURS,
    artifact_paths: dict[str, Path | None] | None = None,
) -> dict[str, Any]:
    if max_artifact_age_hours < 1 or max_artifact_age_hours > 24 * 14:
        raise ValueError("max_artifact_age_hours must be in [1, 336]")
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    max_age_seconds = max_artifact_age_hours * 3600
    paths = artifact_paths or {}
    inputs = {
        "order_construction_repair": order_construction_repair,
        "cap_feasible_selection": cap_feasible_selection,
        "false_negative_preflight": false_negative_preflight,
        "false_negative_operator_review": false_negative_operator_review,
        "placement_repair_plan": placement_repair_plan,
        "operator_authorization": operator_authorization,
        "authority_patch_readiness": authority_patch_readiness,
        "touchability_preflight": touchability_preflight,
    }
    artifacts = {
        name: _artifact_summary(
            name=name,
            path=paths.get(name),
            payload=payload,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        )
        for name, payload in inputs.items()
    }
    authority_preserved, contamination_reasons = _authority_preserved_named(inputs)
    repair_packet = _dict(order_construction_repair)
    selected, selection_reasons, candidate_source, feasible_candidate_count = _select_candidate(
        repair_packet,
        cap_feasible_selection=cap_feasible_selection,
        selected_side_cell_key=_str(selected_side_cell_key) or None,
    )
    feasible = bool(selected) and selected.get("fits_current_cap") is True
    repair_ready = _repair_ready(repair_packet, artifacts)
    cap_feasible_selection_ready = _cap_feasible_selection_ready(
        _dict(cap_feasible_selection), artifacts
    )
    candidate_source_ready, candidate_source_blockers = _candidate_source_ready(
        repair_packet=repair_packet,
        cap_feasible_selection=cap_feasible_selection,
        candidate_source=candidate_source,
        artifacts=artifacts,
    )
    gates = _readiness_gates(
        selected=selected or {},
        artifacts=artifacts,
        false_negative_preflight=false_negative_preflight,
        false_negative_operator_review=false_negative_operator_review,
        placement_repair_plan=placement_repair_plan,
        operator_authorization=operator_authorization,
        authority_patch_readiness=authority_patch_readiness,
        touchability_preflight=touchability_preflight,
    )
    blocking_gates = list(selection_reasons) + gates["blocking_gates"]
    if not authority_preserved:
        status = AUTHORITY_VIOLATION_STATUS
        reason = "input_artifacts_contain_authority_or_mutation_contamination"
        next_actions = ["remove_authority_or_mutation_contamination_before_reroute_review"]
    elif not candidate_source_ready:
        status = INPUT_REQUIRED_STATUS
        reason = "fresh_candidate_source_with_available_lower_price_reroute_required"
        blocking_gates.extend(candidate_source_blockers)
        next_actions = [
            "refresh_bounded_probe_order_construction_repair_or_cap_feasible_selection_packet"
        ]
    elif not feasible:
        status = NOT_FEASIBLE_STATUS
        reason = "no_exactly_one_cap_feasible_lower_price_candidate_selected"
        next_actions = ["refresh_candidate_universe_or_select_one_cap_feasible_candidate"]
    elif blocking_gates:
        status = ALIGNMENT_BLOCKED_STATUS
        reason = "selected_candidate_not_aligned_with_required_bounded_probe_artifacts"
        next_actions = ["refresh_candidate_specific_bounded_probe_review_chain"]
    else:
        status = READY_STATUS
        reason = "selected_lower_price_candidate_is_cap_feasible_and_review_chain_aligned"
        next_actions = [
            "build_candidate_specific_no_order_construction_preview_for_selected_reroute",
            "do_not_submit_order_until_construction_preview_and_runtime_gates_pass",
            "preserve_global_cost_gate_and_require_candidate_matched_fill_fee_slippage_controls",
        ]
    selected_candidate = selected or {}
    return {
        "schema_version": LOWER_PRICE_REROUTE_REVIEW_SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "selected_candidate": {
            "side_cell_key": selected_candidate.get("side_cell_key"),
            "strategy_name": selected_candidate.get("strategy_name"),
            "symbol": selected_candidate.get("symbol"),
            "side": selected_candidate.get("side"),
            "outcome_horizon_minutes": selected_candidate.get(
                "outcome_horizon_minutes"
            ),
            "false_negative_rank": selected_candidate.get("false_negative_rank"),
            "friction_rank": selected_candidate.get("friction_rank"),
            "avg_net_bps": selected_candidate.get("avg_net_bps"),
            "net_positive_pct": selected_candidate.get("net_positive_pct"),
            "outcome_count": selected_candidate.get("outcome_count"),
            "current_cap_usdt": _current_cap_usdt(selected_candidate),
            "minimum_required_demo_notional_usdt_per_order": selected_candidate.get(
                "minimum_required_demo_notional_usdt_per_order"
            ),
            "spread_bps": selected_candidate.get("spread_bps"),
            "instrument_status": selected_candidate.get("instrument_status"),
        },
        "candidate_selection": {
            "selection_method": "explicit_side_cell_key"
            if selected_side_cell_key
            else f"top_cap_feasible_false_negative_from_{candidate_source}",
            "candidate_source": candidate_source,
            "requested_side_cell_key": selected_side_cell_key,
            "exactly_one_candidate_selected": bool(selected),
            "selection_reasons": selection_reasons,
            "feasible_candidate_count": feasible_candidate_count,
        },
        "readiness": {
            "repair_ready": repair_ready,
            "cap_feasible_selection_ready": cap_feasible_selection_ready,
            "candidate_source_ready": candidate_source_ready,
            **gates,
        },
        "artifacts": artifacts,
        "blocking_gates": sorted(set(blocking_gates)),
        "blocking_gate_count": len(set(blocking_gates)),
        "next_actions": next_actions,
        "answers": {
            "exactly_one_lower_price_candidate_selected": bool(selected),
            "selected_candidate_fits_current_cap": feasible,
            "ready_for_candidate_specific_no_order_construction_review": (
                status == READY_STATUS
            ),
            "demo_operational_authorization_available_from_thread": (
                demo_operational_authorization_available is True
            ),
            "runtime_mutation_performed": False,
            "canonical_plan_mutation_performed": False,
            "ledger_append_performed": False,
            "pg_write_performed": False,
            "bybit_call_performed": False,
            "order_submission_performed": False,
            "writer_enabled": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "live_authority_granted": False,
            "promotion_evidence": False,
        },
        "authority_preserved": authority_preserved,
        "authority_contamination_reasons": contamination_reasons,
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    candidate = _dict(packet.get("selected_candidate"))
    readiness = _dict(packet.get("readiness"))
    lines = [
        "# Bounded Demo Lower-Price Reroute Review",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: {packet.get('reason')}",
        f"- Selected candidate: `{candidate.get('side_cell_key')}`",
        f"- Avg net bps: `{candidate.get('avg_net_bps')}`",
        f"- Net-positive pct: `{candidate.get('net_positive_pct')}`",
        f"- Outcome count: `{candidate.get('outcome_count')}`",
        f"- Current cap USDT: `{candidate.get('current_cap_usdt')}`",
        f"- Minimum executable USDT/order: `{candidate.get('minimum_required_demo_notional_usdt_per_order')}`",
        f"- Blocking gates: `{packet.get('blocking_gates')}`",
        f"- Boundary: {packet.get('boundary')}",
        "",
        "## Readiness Gates",
        "",
    ]
    for name, passed in _dict(readiness.get("gates")).items():
        lines.append(f"- `{name}`: `{passed}`")
    lines.extend(["", "## Input Artifacts", ""])
    for name, artifact in _dict(packet.get("artifacts")).items():
        artifact = _dict(artifact)
        lines.append(
            f"- `{name}`: `{artifact.get('status')}` schema=`{artifact.get('schema_version')}` "
            f"sha256=`{artifact.get('sha256')}` path=`{artifact.get('path')}`"
        )
    lines.extend(["", "## Next Actions", ""])
    for action in _list(packet.get("next_actions")):
        lines.append(f"- `{action}`")
    return "\n".join(lines) + "\n"


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


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
    parser.add_argument("--order-construction-repair-json", type=Path)
    parser.add_argument("--cap-feasible-selection-json", type=Path)
    parser.add_argument("--false-negative-preflight-json", type=Path)
    parser.add_argument("--false-negative-operator-review-json", type=Path)
    parser.add_argument("--placement-repair-plan-json", type=Path)
    parser.add_argument("--operator-authorization-json", type=Path)
    parser.add_argument("--authority-patch-readiness-json", type=Path)
    parser.add_argument("--touchability-preflight-json", type=Path)
    parser.add_argument("--selected-side-cell-key")
    parser.add_argument("--demo-operational-authorization-available", action="store_true")
    parser.add_argument("--max-artifact-age-hours", type=int, default=24)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    paths = {
        "order_construction_repair": args.order_construction_repair_json,
        "cap_feasible_selection": args.cap_feasible_selection_json,
        "false_negative_preflight": args.false_negative_preflight_json,
        "false_negative_operator_review": args.false_negative_operator_review_json,
        "placement_repair_plan": args.placement_repair_plan_json,
        "operator_authorization": args.operator_authorization_json,
        "authority_patch_readiness": args.authority_patch_readiness_json,
        "touchability_preflight": args.touchability_preflight_json,
    }
    packet = build_lower_price_reroute_review(
        order_construction_repair=_read_json(args.order_construction_repair_json),
        cap_feasible_selection=_read_json(args.cap_feasible_selection_json),
        false_negative_preflight=_read_json(args.false_negative_preflight_json),
        false_negative_operator_review=_read_json(
            args.false_negative_operator_review_json
        ),
        placement_repair_plan=_read_json(args.placement_repair_plan_json),
        operator_authorization=_read_json(args.operator_authorization_json),
        authority_patch_readiness=_read_json(args.authority_patch_readiness_json),
        touchability_preflight=_read_json(args.touchability_preflight_json),
        selected_side_cell_key=args.selected_side_cell_key,
        demo_operational_authorization_available=(
            args.demo_operational_authorization_available
        ),
        max_artifact_age_hours=args.max_artifact_age_hours,
        artifact_paths=paths,
    )
    markdown = render_markdown(packet)
    if args.output:
        _write_text(args.output, markdown)
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True, default=str))
    if not args.output and not args.json_output and not args.print_json:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
