#!/usr/bin/env python3
"""Build a source-only learning proof/promotion gate verdict packet.

This helper consumes a serving snapshot, learning adjudication packet, and a
candidate proof-evidence artifact. It checks whether evidence is review-ready
for a separate human promotion decision, but it never grants promotion, Cost
Gate, runtime, serving, order, or live authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from cost_gate_learning_lane.learning_adjudicator import (
    READY_STATUS as ADJUDICATOR_READY_STATUS,
    READY_WITH_QUARANTINE_STATUS as ADJUDICATOR_READY_WITH_QUARANTINE_STATUS,
    SCHEMA_VERSION as ADJUDICATOR_SCHEMA_VERSION,
)
from cost_gate_learning_lane.learning_event_contract import (
    AUTHORITY_BOUNDARY_VIOLATION_STATUS,
)
from cost_gate_learning_lane.learning_serving_snapshot import (
    READY_STATUS as SERVING_READY_STATUS,
    SCHEMA_VERSION as SERVING_SCHEMA_VERSION,
)
from cost_gate_learning_lane.proof_exclusion import proof_exclusion_reasons


SCHEMA_VERSION = "cost_gate_learning_proof_promotion_gate_v1"
PROOF_EVIDENCE_SCHEMA_VERSION = "cost_gate_learning_candidate_proof_evidence_v1"

READY_STATUS = "LEARNING_PROOF_PROMOTION_READY_FOR_OPERATOR_REVIEW_NO_AUTHORITY"
BLOCKED_BY_SERVING_STATUS = (
    "LEARNING_PROOF_PROMOTION_BLOCKED_BY_SERVING_SNAPSHOT_NO_AUTHORITY"
)
BLOCKED_BY_ADJUDICATION_STATUS = (
    "LEARNING_PROOF_PROMOTION_BLOCKED_BY_ADJUDICATION_NO_AUTHORITY"
)
BLOCKED_BY_PROOF_STATUS = (
    "LEARNING_PROOF_PROMOTION_BLOCKED_BY_FILL_BACKED_PROOF_NO_AUTHORITY"
)
BLOCKED_BY_PROOF_EXCLUSION_STATUS = (
    "LEARNING_PROOF_PROMOTION_BLOCKED_BY_PROOF_EXCLUSION_NO_AUTHORITY"
)
INPUT_NOT_READY_STATUS = "LEARNING_PROOF_PROMOTION_INPUT_NOT_READY"

BOUNDARY = (
    "artifact-only proof/promotion review packet; no runtime service/env/cron "
    "mutation, no model load or serving slot write, no registry/PG query/write, "
    "no Bybit call, no order, no Cost Gate lowering, no probe/order/live "
    "authority, and no promotion authority or promotion proof"
)

AUTHORITY_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "artifact_delete_performed",
    "bybit_call_performed",
    "canary_slot_promoted",
    "cost_gate_change_allowed",
    "cost_gate_lowering_allowed",
    "demo_mutation_authority_granted",
    "env_mutation_performed",
    "global_cost_gate_lowering_recommended",
    "live_authority_granted",
    "mainnet_authority_granted",
    "model_load_allowed",
    "model_load_allowed_by_this_packet",
    "model_load_performed",
    "order_authority_granted",
    "order_submission_performed",
    "pg_query_performed",
    "pg_write_performed",
    "probe_authority_granted",
    "production_slot_write_performed",
    "promotion_allowed",
    "promotion_allowed_by_this_packet",
    "promotion_authority_granted",
    "promotion_evidence",
    "promotion_proof",
    "registry_write_performed",
    "runtime_mutation_performed",
    "service_restart_performed",
    "serving_authority_granted",
    "serving_snapshot_authority_granted",
    "training_run_performed",
}
AUTHORITY_TRUE_KEY_SUFFIXES = (
    "_allowed_by_this_packet",
)
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

FEE_KEYS = (
    "fee_bps",
    "fee_rate",
    "maker_fee_bps",
    "taker_fee_bps",
    "exec_fee",
    "cost_bps",
)
SLIPPAGE_KEYS = (
    "slippage_bps",
    "price_slippage_bps",
    "execution_slippage_bps",
)
SPREAD_KEYS = (
    "spread_bps",
    "arrival_spread_bps",
    "quoted_spread_bps",
    "bid_ask_spread_bps",
)
CAPACITY_KEYS = (
    "capacity_usdt",
    "notional_usdt",
    "order_notional_usdt",
    "participation_rate",
    "capacity_check",
)
FILL_IDENTITY_KEYS = (
    "fill_id",
    "exec_id",
    "execution_id",
    "order_id",
    "exchange_order_id",
    "bybit_order_id",
    "order_link_id",
    "orderLinkId",
    "openclaw_order_link_id",
)
CANDIDATE_IDENTITY_FIELDS = (
    "side_cell_key",
    "strategy_name",
    "symbol",
    "side",
    "outcome_horizon_minutes",
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
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in TRUTHY_AUTHORITY_STRINGS
    return False


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_payload(payload: Any) -> str:
    return _sha256_text(_canonical_json(payload))


def _has_any(row: dict[str, Any], keys: tuple[str, ...]) -> bool:
    for key in keys:
        value = row.get(key)
        if value is None or value is False:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return True
    return False


def _row_has_demo_fill_identity(row: dict[str, Any]) -> bool:
    return _has_any(row, FILL_IDENTITY_KEYS)


def _row_is_cleanup_or_replay_only(row: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    outcome_source = _str(row.get("outcome_source")).lower()
    fill_class = _str(
        row.get("fill_class")
        or row.get("fill_source")
        or row.get("order_purpose")
        or row.get("lineage_class")
    ).lower()
    source_kind = _str(
        row.get("source_kind")
        or row.get("source_evidence_type")
        or row.get("evidence_type")
    ).lower()
    if (
        _truthy(row.get("cleanup_fill"))
        or _truthy(row.get("cleanup_order"))
        or "cleanup" in outcome_source
        or fill_class == "cleanup"
    ):
        reasons.append("cleanup_fill_not_promotion_evidence")
    if (
        _truthy(row.get("replay_only"))
        or _truthy(row.get("simulation_only"))
        or source_kind in {"replay", "simulation", "backtest"}
        or ("replay" in outcome_source and "demo" not in outcome_source)
    ):
        reasons.append("replay_only_not_promotion_evidence")
    return reasons


def _first(container_list: list[dict[str, Any]], *keys: str) -> Any:
    for container in container_list:
        for key in keys:
            if key in container:
                return container.get(key)
    return None


def _bool_from(
    container_list: list[dict[str, Any]],
    *keys: str,
    default: bool = False,
) -> bool:
    value = _first(container_list, *keys)
    if value is None:
        return default
    return _truthy(value)


def _int_from(
    container_list: list[dict[str, Any]],
    *keys: str,
    default: int = 0,
) -> int:
    value = _first(container_list, *keys)
    return _int(value, default=default)


def _float_from(container_list: list[dict[str, Any]], *keys: str) -> float | None:
    return _float(_first(container_list, *keys))


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
            elif _is_authority_true_key(key) and _truthy(value):
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


def _is_authority_true_key(key: str) -> bool:
    normalized = str(key or "").strip()
    return normalized in AUTHORITY_TRUE_KEYS or any(
        normalized.endswith(suffix) for suffix in AUTHORITY_TRUE_KEY_SUFFIXES
    )


def _source_ref(
    *,
    payload: dict[str, Any],
    path: Path | None,
    source_error: str | None,
) -> dict[str, Any]:
    return {
        "path": str(path) if path else None,
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "source_error": source_error,
        "sha256": _sha256_payload(payload) if payload else None,
    }


def _candidate_id(payload: dict[str, Any]) -> str:
    identity = _dict(payload.get("candidate_identity"))
    candidate = _dict(payload.get("candidate"))
    details = _dict(payload.get("details"))
    return _str(
        payload.get("candidate_id")
        or payload.get("side_cell_key")
        or identity.get("candidate_id")
        or identity.get("side_cell_key")
        or candidate.get("candidate_id")
        or candidate.get("side_cell_key")
        or details.get("candidate_id")
        or details.get("side_cell_key")
    )


def _candidate_identity(proof_evidence: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    identity = _dict(proof_evidence.get("candidate_identity"))
    parsed = _parse_candidate_id(candidate_id)
    return {
        "side_cell_key": _str(
            identity.get("side_cell_key")
            or proof_evidence.get("side_cell_key")
            or candidate_id
        ),
        "strategy_name": _str(
            identity.get("strategy_name")
            or proof_evidence.get("strategy_name")
            or parsed.get("strategy_name")
        ),
        "symbol": _str(
            identity.get("symbol") or proof_evidence.get("symbol") or parsed.get("symbol")
        ).upper(),
        "side": _normalize_side(
            identity.get("side") or proof_evidence.get("side") or parsed.get("side")
        ),
        "outcome_horizon_minutes": _str(
            identity.get("outcome_horizon_minutes")
            or identity.get("horizon_minutes")
            or proof_evidence.get("outcome_horizon_minutes")
            or proof_evidence.get("horizon_minutes")
            or parsed.get("outcome_horizon_minutes")
        ),
    }


def _parse_candidate_id(candidate_id: str) -> dict[str, str]:
    parts = [part.strip() for part in _str(candidate_id).split("|")]
    parsed: dict[str, str] = {}
    if len(parts) >= 3:
        parsed["strategy_name"] = parts[0]
        parsed["symbol"] = parts[1]
        parsed["side"] = parts[2]
    if len(parts) >= 4:
        parsed["outcome_horizon_minutes"] = parts[3]
    return parsed


def _normalize_side(value: Any) -> str:
    text = _str(value)
    if text.lower() == "buy":
        return "Buy"
    if text.lower() == "sell":
        return "Sell"
    return text


def _row_identity_reasons(
    row: dict[str, Any],
    identity: dict[str, Any],
    *,
    row_kind: str,
) -> list[str]:
    reasons: list[str] = []
    row_candidate_id = _candidate_id(row)
    expected_side_cell = _str(identity.get("side_cell_key"))
    if not row_candidate_id:
        reasons.append(f"{row_kind}_side_cell_key_missing")
    elif expected_side_cell and row_candidate_id != expected_side_cell:
        reasons.append(f"{row_kind}_side_cell_key_mismatch")

    expected_strategy = _str(identity.get("strategy_name"))
    row_strategy = _str(row.get("strategy_name"))
    if expected_strategy and not row_strategy:
        reasons.append(f"{row_kind}_strategy_name_missing")
    elif expected_strategy and row_strategy != expected_strategy:
        reasons.append(f"{row_kind}_strategy_name_mismatch")

    expected_symbol = _str(identity.get("symbol")).upper()
    row_symbol = _str(row.get("symbol")).upper()
    if expected_symbol and not row_symbol:
        reasons.append(f"{row_kind}_symbol_missing")
    elif expected_symbol and row_symbol != expected_symbol:
        reasons.append(f"{row_kind}_symbol_mismatch")

    expected_side = _normalize_side(identity.get("side"))
    row_side = _normalize_side(row.get("side"))
    if expected_side and not row_side:
        reasons.append(f"{row_kind}_side_missing")
    elif expected_side and row_side != expected_side:
        reasons.append(f"{row_kind}_side_mismatch")

    expected_horizon = _str(identity.get("outcome_horizon_minutes"))
    row_horizon = _str(
        row.get("outcome_horizon_minutes")
        or row.get("horizon_minutes")
        or row.get("outcome_horizon_min")
    )
    if expected_horizon and not row_horizon:
        reasons.append(f"{row_kind}_outcome_horizon_minutes_missing")
    elif expected_horizon and row_horizon != expected_horizon:
        reasons.append(f"{row_kind}_outcome_horizon_minutes_mismatch")
    return reasons


def _candidate_identity_gate(identity: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in CANDIDATE_IDENTITY_FIELDS if not _str(identity.get(field))]
    return {
        "ready": not missing,
        "identity": identity,
        "missing_fields": missing,
    }


def _serving_gate(
    *,
    serving_snapshot_packet: dict[str, Any],
    serving_snapshot_error: str | None,
) -> dict[str, Any]:
    candidate = _dict(serving_snapshot_packet.get("serving_snapshot_candidate"))
    blockers: list[str] = []
    if serving_snapshot_error:
        blockers.append(f"serving_snapshot_packet:{serving_snapshot_error}")
    if serving_snapshot_packet.get("schema_version") != SERVING_SCHEMA_VERSION:
        blockers.append("serving_snapshot_schema_invalid")
    if serving_snapshot_packet.get("status") != SERVING_READY_STATUS:
        blockers.append("serving_snapshot_not_ready")
    if not candidate:
        blockers.append("serving_snapshot_candidate_missing")
    if _dict(candidate.get("allowed_actions")).get("promotion_allowed_by_this_packet") is True:
        blockers.append("serving_snapshot_claims_promotion_authority")
    return {
        "ready": not blockers,
        "blockers": blockers,
        "serving_status": serving_snapshot_packet.get("status"),
        "snapshot_id": candidate.get("snapshot_id"),
        "model_version": candidate.get("model_version"),
        "runtime_agreement": candidate.get("runtime_agreement"),
        "feature_schema_hash": candidate.get("feature_schema_hash"),
    }


def _adjudication_gate(
    *,
    adjudicator_packet: dict[str, Any],
    adjudicator_error: str | None,
    candidate_id: str,
) -> dict[str, Any]:
    decisions = [_dict(item) for item in _list(adjudicator_packet.get("decisions"))]
    review_decisions = [
        decision
        for decision in decisions
        if _str(decision.get("decision_label")) == "REVIEW"
    ]
    matching_reviews = [
        decision
        for decision in review_decisions
        if not candidate_id or _candidate_id(decision) == candidate_id
    ]
    selected = matching_reviews[0] if matching_reviews else {}
    blockers: list[str] = []
    if adjudicator_error:
        blockers.append(f"learning_adjudicator_packet:{adjudicator_error}")
    if adjudicator_packet.get("schema_version") != ADJUDICATOR_SCHEMA_VERSION:
        blockers.append("learning_adjudicator_schema_invalid")
    if adjudicator_packet.get("status") not in {
        ADJUDICATOR_READY_STATUS,
        ADJUDICATOR_READY_WITH_QUARANTINE_STATUS,
    }:
        blockers.append("learning_adjudicator_not_ready")
    if not candidate_id:
        blockers.append("proof_evidence_candidate_id_missing")
    if not review_decisions:
        blockers.append("learning_adjudicator_has_no_review_decision")
    elif not selected:
        blockers.append("learning_adjudicator_has_no_matching_review_decision")
    if _int(_dict(adjudicator_packet.get("summary")).get("upstream_quarantine_count")) > 0:
        blockers.append("learning_adjudicator_upstream_quarantine_present")
    return {
        "ready": not blockers,
        "blockers": blockers,
        "adjudicator_status": adjudicator_packet.get("status"),
        "candidate_id": candidate_id or None,
        "review_decision_count": len(review_decisions),
        "selected_decision_id": selected.get("decision_id"),
        "selected_decision_label": selected.get("decision_label"),
    }


def _candidate_rows(proof_evidence: dict[str, Any], candidate_id: str) -> list[dict[str, Any]]:
    fill_evidence = _dict(proof_evidence.get("fill_evidence"))
    rows = (
        _list(proof_evidence.get("candidate_matched_demo_fills"))
        or _list(proof_evidence.get("candidate_matched_fill_rows"))
        or _list(fill_evidence.get("candidate_matched_demo_fills"))
        or _list(fill_evidence.get("rows"))
    )
    output: list[dict[str, Any]] = []
    for row in rows:
        data = _dict(row)
        if not data:
            continue
        row_candidate_id = _candidate_id(data)
        if candidate_id and row_candidate_id and row_candidate_id != candidate_id:
            continue
        output.append(data)
    return output


def _matched_control_rows(proof_evidence: dict[str, Any]) -> list[dict[str, Any]]:
    controls = _dict(proof_evidence.get("matched_control_baseline"))
    return (
        _list(proof_evidence.get("matched_control_rows"))
        or _list(controls.get("rows"))
        or _list(controls.get("matched_control_rows"))
    )


def _derived_row_metrics(
    *,
    rows: list[dict[str, Any]],
    controls: list[dict[str, Any]],
    identity: dict[str, Any],
) -> dict[str, Any]:
    excluded_rows = []
    countable_rows = []
    for row in rows:
        reasons = proof_exclusion_reasons(row)
        reasons.extend(_row_identity_reasons(row, identity, row_kind="candidate_fill"))
        if not _row_has_demo_fill_identity(row):
            reasons.append("candidate_matched_demo_fill_identity_missing")
        reasons.extend(_row_is_cleanup_or_replay_only(row))
        if reasons:
            excluded_rows.append({"row": row, "reasons": reasons})
        else:
            countable_rows.append(row)
    excluded_controls = []
    countable_controls = []
    for row in controls:
        reasons = _row_identity_reasons(row, identity, row_kind="matched_control")
        if reasons:
            excluded_controls.append({"row": row, "reasons": reasons})
        else:
            countable_controls.append(row)
    net_values = [
        value
        for value in (_float(row.get("realized_net_bps")) for row in countable_rows)
        if value is not None
    ]
    avg_net = sum(net_values) / len(net_values) if net_values else None
    exclusion_counts = _reason_counts([*excluded_rows, *excluded_controls])
    return {
        "row_backed": bool(rows),
        "candidate_matched_demo_fill_count": len(countable_rows),
        "raw_candidate_matched_demo_fill_count": len(rows),
        "proof_excluded_row_count": len(excluded_rows),
        "proof_excluded_control_count": len(excluded_controls),
        "proof_exclusion_reason_counts": exclusion_counts,
        "fee_evidence_present": bool(countable_rows)
        and all(_has_any(row, FEE_KEYS) for row in countable_rows),
        "slippage_evidence_present": bool(countable_rows)
        and all(_has_any(row, SLIPPAGE_KEYS) for row in countable_rows),
        "spread_evidence_present": bool(countable_rows)
        and all(_has_any(row, SPREAD_KEYS) for row in countable_rows),
        "capacity_evidence_present": bool(countable_rows)
        and all(_has_any(row, CAPACITY_KEYS) for row in countable_rows),
        "avg_realized_net_bps": avg_net,
        "net_of_fees_positive": avg_net is not None and avg_net > 0.0,
        "matched_control_baseline_present": bool(countable_controls),
        "matched_control_count": len(countable_controls),
        "raw_matched_control_count": len(controls),
    }


def _reason_counts(excluded_rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in excluded_rows:
        for reason in _list(item.get("reasons")):
            key = _str(reason)
            if key:
                counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _proof_exclusion_gate(
    *,
    proof_evidence: dict[str, Any],
    proof_exclusion_packet: dict[str, Any],
    derived: dict[str, Any],
) -> dict[str, Any]:
    proof_exclusion = _dict(proof_evidence.get("proof_exclusion"))
    packets = [proof_exclusion, proof_exclusion_packet]
    excluded_count = _int(derived.get("proof_excluded_row_count")) + _int(
        derived.get("proof_excluded_control_count")
    )
    for packet in packets:
        excluded_count += _int(
            packet.get("proof_excluded_probe_outcome_count")
            or packet.get("proof_excluded_row_count")
            or packet.get("excluded_row_count")
        )
    reason_counts: dict[str, int] = dict(_dict(derived.get("proof_exclusion_reason_counts")))
    for packet in packets:
        for reason, count in _dict(packet.get("reason_counts")).items():
            key = _str(reason)
            if key:
                reason_counts[key] = reason_counts.get(key, 0) + _int(count)
    explicit_present = any(
        packet.get("proof_exclusion_present") is True for packet in packets
    )
    explicit_pass = any(
        packet.get("proof_exclusion_passed") is True
        or packet.get("proof_exclusion_present") is False
        for packet in packets
    )
    blockers: list[str] = []
    if excluded_count > 0 or explicit_present:
        blockers.append("proof_exclusion_present")
    if not explicit_pass and excluded_count == 0 and not explicit_present:
        blockers.append("proof_exclusion_pass_not_recorded")
    return {
        "ready": not blockers,
        "blockers": blockers,
        "proof_exclusion_present": bool(excluded_count > 0 or explicit_present),
        "proof_excluded_row_count": excluded_count,
        "reason_counts": dict(sorted(reason_counts.items())),
        "proof_exclusion_pass_recorded": explicit_pass,
    }


def _proof_gate(
    *,
    proof_evidence: dict[str, Any],
    proof_evidence_error: str | None,
    proof_exclusion_packet: dict[str, Any],
    serving_gate: dict[str, Any],
    candidate_id: str,
) -> dict[str, Any]:
    summary = _dict(proof_evidence.get("summary"))
    fill = _dict(proof_evidence.get("fill_evidence"))
    execution = _dict(proof_evidence.get("execution_realism"))
    validation = _dict(proof_evidence.get("validation"))
    controls = _dict(proof_evidence.get("matched_control_baseline"))
    risk = _dict(proof_evidence.get("tail_risk"))
    thresholds = _dict(proof_evidence.get("proof_thresholds"))
    containers = [
        proof_evidence,
        summary,
        fill,
        execution,
        validation,
        controls,
        risk,
        thresholds,
    ]
    rows = _candidate_rows(proof_evidence, candidate_id)
    control_rows = _matched_control_rows(proof_evidence)
    identity = _candidate_identity(proof_evidence, candidate_id)
    identity_gate = _candidate_identity_gate(identity)
    derived = _derived_row_metrics(rows=rows, controls=control_rows, identity=identity)
    fill_count_sources = [derived, fill, summary, proof_evidence]
    control_count_sources = [derived, controls, summary, proof_evidence]
    net_sources = [derived, fill, summary, proof_evidence]

    min_fill_count = _int_from(
        [thresholds, proof_evidence, summary],
        "min_candidate_matched_demo_fills",
        "min_candidate_matched_fill_count",
        default=10,
    )
    fill_count = _int_from(
        fill_count_sources,
        "candidate_matched_demo_fill_count",
        "candidate_matched_fill_count",
        "proof_eligible_probe_outcome_count",
        "completed_probe_outcome_count",
        default=0,
    )
    matched_control_count = _int_from(
        control_count_sources,
        "matched_control_count",
        "matched_control_outcome_count",
        default=0,
    )
    avg_net = _float_from(
        net_sources,
        "avg_realized_net_bps",
        "avg_net_bps",
        "candidate_avg_net_bps",
    )
    serving_snapshot_id = _str(
        _first(
            [proof_evidence, summary],
            "serving_snapshot_id",
            "learning_serving_snapshot_id",
        )
    )
    model_version = _str(
        _first([proof_evidence, summary], "model_version", "serving_model_version")
    )

    proof_exclusion_gate = _proof_exclusion_gate(
        proof_evidence=proof_evidence,
        proof_exclusion_packet=proof_exclusion_packet,
        derived=derived,
    )
    blockers: list[str] = []
    if proof_evidence_error:
        blockers.append(f"proof_evidence_packet:{proof_evidence_error}")
    if proof_evidence.get("schema_version") != PROOF_EVIDENCE_SCHEMA_VERSION:
        blockers.append("proof_evidence_schema_invalid")
    if proof_evidence.get("status") not in {
        "CANDIDATE_PROOF_EVIDENCE_READY",
        "CANDIDATE_PROOF_EVIDENCE_REVIEW_READY",
        "READY",
        "ok",
        "OK",
    }:
        blockers.append("proof_evidence_status_not_ready")
    if identity_gate.get("ready") is not True:
        blockers.append("proof_evidence_candidate_identity_incomplete")
    if derived.get("row_backed") is not True:
        blockers.append("candidate_matched_demo_fill_rows_missing")
    if _int(derived.get("proof_excluded_row_count")) > 0:
        blockers.append("candidate_matched_demo_fill_identity_mismatch_or_excluded")
    if fill_count < max(1, min_fill_count):
        blockers.append("candidate_matched_demo_fills_below_floor")
    if derived.get("fee_evidence_present") is not True:
        blockers.append("real_fee_evidence_missing")
    if derived.get("slippage_evidence_present") is not True:
        blockers.append("real_slippage_evidence_missing")
    if derived.get("spread_evidence_present") is not True:
        blockers.append("spread_evidence_missing")
    if derived.get("capacity_evidence_present") is not True:
        blockers.append("capacity_evidence_missing")
    if not _bool_from(containers, "execution_realism_passed"):
        blockers.append("execution_realism_review_missing_or_failed")
    if not _bool_from(containers, "tail_risk_review_passed"):
        blockers.append("tail_risk_review_missing_or_failed")
    if not _bool_from(containers, "oos_validation_passed"):
        blockers.append("oos_validation_missing_or_failed")
    if not _bool_from(containers, "repeat_set_passed", "repeat_validation_passed"):
        blockers.append("repeat_set_validation_missing_or_failed")
    if matched_control_count <= 0 or derived.get("matched_control_baseline_present") is not True:
        blockers.append("matched_control_baseline_missing")
    if _int(derived.get("proof_excluded_control_count")) > 0:
        blockers.append("matched_control_identity_mismatch_or_excluded")
    if not _bool_from(
        containers,
        "matched_control_outperformance",
        "candidate_outperforms_matched_control",
    ):
        blockers.append("matched_control_outperformance_missing_or_failed")
    if avg_net is None or avg_net <= 0.0:
        blockers.append("net_of_fees_profitability_missing_or_nonpositive")
    if not serving_snapshot_id:
        blockers.append("proof_evidence_serving_snapshot_id_missing")
    elif serving_snapshot_id != _str(serving_gate.get("snapshot_id")):
        blockers.append("proof_evidence_serving_snapshot_id_mismatch")
    if not model_version:
        blockers.append("proof_evidence_model_version_missing")
    elif model_version != _str(serving_gate.get("model_version")):
        blockers.append("proof_evidence_model_version_mismatch")

    return {
        "ready": not blockers and proof_exclusion_gate.get("ready") is True,
        "blockers": blockers,
        "candidate_id": candidate_id or None,
        "serving_snapshot_id": serving_snapshot_id or None,
        "model_version": model_version or None,
        "candidate_identity_gate": identity_gate,
        "min_candidate_matched_demo_fills": max(1, min_fill_count),
        "candidate_matched_demo_fill_count": fill_count,
        "matched_control_count": matched_control_count,
        "raw_candidate_matched_demo_fill_count": derived.get(
            "raw_candidate_matched_demo_fill_count"
        ),
        "raw_matched_control_count": derived.get("raw_matched_control_count"),
        "avg_realized_net_bps": avg_net,
        "row_backed": derived.get("row_backed"),
        "proof_exclusion_gate": proof_exclusion_gate,
        "requirement_checks": {
            "candidate_matched_demo_fills_present": fill_count >= max(1, min_fill_count),
            "fee_evidence_present": "real_fee_evidence_missing" not in blockers,
            "slippage_evidence_present": "real_slippage_evidence_missing" not in blockers,
            "spread_evidence_present": "spread_evidence_missing" not in blockers,
            "capacity_evidence_present": "capacity_evidence_missing" not in blockers,
            "execution_realism_passed": "execution_realism_review_missing_or_failed"
            not in blockers,
            "tail_risk_review_passed": "tail_risk_review_missing_or_failed"
            not in blockers,
            "oos_validation_passed": "oos_validation_missing_or_failed" not in blockers,
            "repeat_set_passed": "repeat_set_validation_missing_or_failed"
            not in blockers,
            "matched_control_baseline_present": "matched_control_baseline_missing"
            not in blockers,
            "matched_control_outperformance": "matched_control_outperformance_missing_or_failed"
            not in blockers,
            "net_of_fees_positive": "net_of_fees_profitability_missing_or_nonpositive"
            not in blockers,
            "serving_snapshot_linked": not any(
                blocker.startswith("proof_evidence_serving_snapshot_id")
                for blocker in blockers
            ),
            "model_version_linked": not any(
                blocker.startswith("proof_evidence_model_version")
                for blocker in blockers
            ),
        },
    }


def _answer_flags(status: str) -> dict[str, Any]:
    ready = status == READY_STATUS
    return {
        "source_only_review_packet": True,
        "promotion_verdict_ready_for_operator_review": ready,
        "proof_requirements_satisfied": ready,
        "requires_separate_operator_promotion_review": True,
        "requires_separate_cost_gate_review": True,
        "requires_separate_runtime_review": True,
        "promotion_allowed_by_this_packet": False,
        "promotion_authority_granted": False,
        "promotion_evidence": False,
        "promotion_proof": False,
        "cost_gate_change_allowed": False,
        "cost_gate_lowering_allowed": False,
        "global_cost_gate_lowering_recommended": False,
        "main_cost_gate_adjustment": "NONE",
        "runtime_mutation_allowed": False,
        "runtime_mutation_performed": False,
        "service_restart_performed": False,
        "env_mutation_performed": False,
        "cron_mutation_performed": False,
        "model_load_allowed_by_this_packet": False,
        "model_load_performed": False,
        "serving_authority_granted": False,
        "serving_slot_write_allowed": False,
        "registry_write_performed": False,
        "pg_query_performed": False,
        "pg_write_performed": False,
        "bybit_call_performed": False,
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "order_submission_performed": False,
        "live_authority_granted": False,
    }


def _verdict_id(
    *,
    candidate_id: str,
    serving_gate: dict[str, Any],
    adjudication_gate: dict[str, Any],
    proof_gate: dict[str, Any],
) -> str:
    seed = {
        "schema_version": SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "snapshot_id": serving_gate.get("snapshot_id"),
        "decision_id": adjudication_gate.get("selected_decision_id"),
        "proof_gate": proof_gate,
    }
    return "learning_promotion_verdict:" + _sha256_payload(seed)[:24]


def build_learning_proof_promotion_gate(
    *,
    serving_snapshot_packet: dict[str, Any] | None,
    learning_adjudicator_packet: dict[str, Any] | None,
    proof_evidence_packet: dict[str, Any] | None,
    proof_exclusion_packet: dict[str, Any] | None = None,
    serving_snapshot_packet_path: Path | None = None,
    learning_adjudicator_packet_path: Path | None = None,
    proof_evidence_packet_path: Path | None = None,
    proof_exclusion_packet_path: Path | None = None,
    serving_snapshot_packet_error: str | None = None,
    learning_adjudicator_packet_error: str | None = None,
    proof_evidence_packet_error: str | None = None,
    proof_exclusion_packet_error: str | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    """Build a deterministic no-authority proof/promotion verdict packet."""
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    serving = _dict(serving_snapshot_packet)
    adjudicator = _dict(learning_adjudicator_packet)
    proof = _dict(proof_evidence_packet)
    proof_exclusion = _dict(proof_exclusion_packet)
    candidate_id = _candidate_id(proof)
    authority_violations = []
    for payload in (serving, adjudicator, proof, proof_exclusion):
        authority_violations.extend(_authority_violations(payload))

    input_blockers: list[str] = []
    if proof_exclusion_packet_error:
        input_blockers.append(f"proof_exclusion_packet:{proof_exclusion_packet_error}")

    serving = _dict(serving_snapshot_packet)
    serving_gate = _serving_gate(
        serving_snapshot_packet=serving,
        serving_snapshot_error=serving_snapshot_packet_error,
    )
    adjudication_gate = _adjudication_gate(
        adjudicator_packet=adjudicator,
        adjudicator_error=learning_adjudicator_packet_error,
        candidate_id=candidate_id,
    )
    proof_gate = _proof_gate(
        proof_evidence=proof,
        proof_evidence_error=proof_evidence_packet_error,
        proof_exclusion_packet=proof_exclusion,
        serving_gate=serving_gate,
        candidate_id=candidate_id,
    )
    proof_exclusion_gate = _dict(proof_gate.get("proof_exclusion_gate"))

    if (
        serving.get("status") == AUTHORITY_BOUNDARY_VIOLATION_STATUS
        or adjudicator.get("status") == AUTHORITY_BOUNDARY_VIOLATION_STATUS
        or proof.get("status") == AUTHORITY_BOUNDARY_VIOLATION_STATUS
        or authority_violations
    ):
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "proof_promotion_input_authority_boundary_violation"
    elif input_blockers:
        status = INPUT_NOT_READY_STATUS
        reason = "proof_promotion_required_inputs_missing_or_unreadable"
    elif not serving_gate["ready"]:
        status = BLOCKED_BY_SERVING_STATUS
        reason = "serving_snapshot_must_be_ready_before_promotion_review"
    elif not adjudication_gate["ready"]:
        status = BLOCKED_BY_ADJUDICATION_STATUS
        reason = "learning_adjudication_review_decision_required_before_promotion_review"
    elif proof_exclusion_gate.get("ready") is not True:
        status = BLOCKED_BY_PROOF_EXCLUSION_STATUS
        reason = "proof_exclusion_must_be_absent_and_recorded_pass_before_promotion_review"
    elif not proof_gate["ready"]:
        status = BLOCKED_BY_PROOF_STATUS
        reason = "fill_backed_candidate_proof_requirements_not_satisfied"
    else:
        status = READY_STATUS
        reason = "proof_requirements_ready_for_separate_operator_promotion_review"

    promotion_verdict: dict[str, Any] | None = None
    if status == READY_STATUS:
        promotion_verdict = {
            "verdict_id": _verdict_id(
                candidate_id=candidate_id,
                serving_gate=serving_gate,
                adjudication_gate=adjudication_gate,
                proof_gate=proof_gate,
            ),
            "verdict_label": "REVIEW_READY_NO_AUTHORITY",
            "candidate_id": candidate_id,
            "serving_snapshot_id": serving_gate.get("snapshot_id"),
            "model_version": serving_gate.get("model_version"),
            "learning_adjudication_decision_id": adjudication_gate.get(
                "selected_decision_id"
            ),
            "proof_requirements_satisfied": True,
            "operator_review_required_before_any_promotion": True,
            "allowed_actions": {
                "operator_review_allowed": True,
                "promotion_allowed_by_this_packet": False,
                "cost_gate_change_allowed_by_this_packet": False,
                "runtime_mutation_allowed_by_this_packet": False,
                "model_load_allowed_by_this_packet": False,
                "registry_write_allowed_by_this_packet": False,
                "pg_write_allowed_by_this_packet": False,
                "order_allowed_by_this_packet": False,
                "live_authority_allowed_by_this_packet": False,
            },
        }

    blocked_verdict = {
        "verdict_emitted": promotion_verdict is not None,
        "input_blockers": input_blockers,
        "serving_blockers": serving_gate.get("blockers"),
        "adjudication_blockers": adjudication_gate.get("blockers"),
        "proof_exclusion_blockers": proof_exclusion_gate.get("blockers"),
        "proof_blockers": proof_gate.get("blockers"),
    }
    packet_sha = _sha256_payload(
        {
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "promotion_verdict": promotion_verdict,
            "blocked_verdict": blocked_verdict,
        }
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "proof_promotion_gate_sha256": packet_sha,
        "source_refs": {
            "serving_snapshot_packet": _source_ref(
                payload=serving,
                path=serving_snapshot_packet_path,
                source_error=serving_snapshot_packet_error,
            ),
            "learning_adjudicator_packet": _source_ref(
                payload=adjudicator,
                path=learning_adjudicator_packet_path,
                source_error=learning_adjudicator_packet_error,
            ),
            "proof_evidence_packet": _source_ref(
                payload=proof,
                path=proof_evidence_packet_path,
                source_error=proof_evidence_packet_error,
            ),
            "proof_exclusion_packet": _source_ref(
                payload=proof_exclusion,
                path=proof_exclusion_packet_path,
                source_error=proof_exclusion_packet_error,
            ),
        },
        "summary": {
            "candidate_id": candidate_id or None,
            "promotion_verdict_emitted": promotion_verdict is not None,
            "serving_ready": serving_gate.get("ready"),
            "adjudication_ready": adjudication_gate.get("ready"),
            "proof_ready": proof_gate.get("ready"),
            "proof_exclusion_ready": proof_exclusion_gate.get("ready"),
            "proof_blocker_count": len(_list(proof_gate.get("blockers"))),
            "authority_violation_count": len(authority_violations),
        },
        "serving_gate": serving_gate,
        "adjudication_gate": adjudication_gate,
        "proof_gate": proof_gate,
        "promotion_verdict": promotion_verdict,
        "blocked_verdict": blocked_verdict,
        "authority_violations": authority_violations,
        "answers": _answer_flags(status),
        "next_actions": _next_actions(status),
        "boundary": BOUNDARY,
    }


def _next_actions(status: str) -> list[str]:
    if status == AUTHORITY_BOUNDARY_VIOLATION_STATUS:
        return [
            "remove_authority_bearing_proof_promotion_input",
            "rerun_source_only_proof_promotion_gate_after_clean_inputs",
        ]
    if status == BLOCKED_BY_SERVING_STATUS:
        return [
            "produce_ready_learning_serving_snapshot_before_promotion_review",
            "do_not_load_model_or_write_serving_slot_from_this_gate",
        ]
    if status == BLOCKED_BY_ADJUDICATION_STATUS:
        return [
            "produce_matching_review_learning_adjudication_decision_for_candidate",
            "keep_blocked_markout_proxy_out_of_promotion_proof_counts",
        ]
    if status == BLOCKED_BY_PROOF_EXCLUSION_STATUS:
        return [
            "repair_or_quarantine_proof_excluded_fill_lineage_before_promotion_review",
            "rerun_candidate_proof_evidence_with_proof_exclusion_pass_recorded",
        ]
    if status == BLOCKED_BY_PROOF_STATUS:
        return [
            "collect_candidate_matched_demo_fill_fee_slippage_spread_capacity_and_control_evidence",
            "complete_oos_repeat_execution_realism_and_tail_risk_reviews",
        ]
    if status == READY_STATUS:
        return [
            "operator_review_promotion_verdict_before_any_cost_gate_or_runtime_change",
            "open_separate_promotion_or_cost_gate_change_review_if_operator_approves",
        ]
    return ["provide_valid_serving_adjudicator_and_proof_evidence_artifacts"]


def render_markdown(packet: dict[str, Any]) -> str:
    summary = _dict(packet.get("summary"))
    answers = _dict(packet.get("answers"))
    proof_gate = _dict(packet.get("proof_gate"))
    verdict = _dict(packet.get("promotion_verdict"))
    blocked = _dict(packet.get("blocked_verdict"))
    lines = [
        "# Cost Gate Learning Proof Promotion Gate",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Candidate: `{summary.get('candidate_id')}`",
        f"- Verdict emitted: `{summary.get('promotion_verdict_emitted')}`",
        f"- Verdict id: `{verdict.get('verdict_id')}`",
        f"- Fill count: `{proof_gate.get('candidate_matched_demo_fill_count')}`",
        f"- Boundary: {packet.get('boundary')}",
        "",
        "## Blockers",
        "",
    ]
    for key in (
        "input_blockers",
        "serving_blockers",
        "adjudication_blockers",
        "proof_exclusion_blockers",
        "proof_blockers",
    ):
        lines.append(f"- `{key}`: `{_list(blocked.get(key))}`")
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
    parser.add_argument("--serving-snapshot-json", type=Path, required=True)
    parser.add_argument("--learning-adjudicator-json", type=Path, required=True)
    parser.add_argument("--proof-evidence-json", type=Path, required=True)
    parser.add_argument("--proof-exclusion-json", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    serving, serving_error = _read_json(args.serving_snapshot_json)
    adjudicator, adjudicator_error = _read_json(args.learning_adjudicator_json)
    proof, proof_error = _read_json(args.proof_evidence_json)
    if args.proof_exclusion_json:
        proof_exclusion, proof_exclusion_error = _read_json(args.proof_exclusion_json)
    else:
        proof_exclusion, proof_exclusion_error = None, None
    packet = build_learning_proof_promotion_gate(
        serving_snapshot_packet=serving,
        learning_adjudicator_packet=adjudicator,
        proof_evidence_packet=proof,
        proof_exclusion_packet=proof_exclusion,
        serving_snapshot_packet_path=args.serving_snapshot_json,
        learning_adjudicator_packet_path=args.learning_adjudicator_json,
        proof_evidence_packet_path=args.proof_evidence_json,
        proof_exclusion_packet_path=args.proof_exclusion_json,
        serving_snapshot_packet_error=serving_error,
        learning_adjudicator_packet_error=adjudicator_error,
        proof_evidence_packet_error=proof_error,
        proof_exclusion_packet_error=proof_exclusion_error,
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
