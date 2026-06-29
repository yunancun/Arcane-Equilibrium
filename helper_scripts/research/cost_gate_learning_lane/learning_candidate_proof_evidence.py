#!/usr/bin/env python3
"""Build row-backed candidate proof evidence for the learning promotion gate.

This helper normalizes already-produced artifact rows into
``cost_gate_learning_candidate_proof_evidence_v1``. It never queries PG, calls
Bybit, reads secrets, submits orders, mutates runtime, or grants authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from cost_gate_learning_lane.learning_proof_promotion_gate import (
    PROOF_EVIDENCE_SCHEMA_VERSION,
)
from cost_gate_learning_lane.proof_exclusion import proof_exclusion_reasons


READY_STATUS = "CANDIDATE_PROOF_EVIDENCE_READY"
BLOCKED_STATUS = "CANDIDATE_PROOF_EVIDENCE_BLOCKED"
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "CANDIDATE_PROOF_EVIDENCE_AUTHORITY_BOUNDARY_VIOLATION"

BOUNDARY = (
    "artifact-only candidate proof evidence producer; no PG query/write, no "
    "Bybit call, no secret read/write, no order, no runtime/env/service/cron "
    "mutation, no Cost Gate lowering, and no probe/order/live/promotion authority"
)

AUTHORITY_TRUE_KEY_SUFFIXES = ("_allowed_by_this_packet",)
AUTHORITY_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "bybit_call_performed",
    "cost_gate_lowering_allowed",
    "demo_mutation_authority_granted",
    "env_mutation_performed",
    "live_authority_granted",
    "mainnet_authority_granted",
    "model_load_performed",
    "order_authority_granted",
    "order_submission_performed",
    "pg_query_performed",
    "pg_write_performed",
    "probe_authority_granted",
    "promotion_allowed",
    "promotion_authority_granted",
    "promotion_evidence",
    "promotion_proof",
    "registry_write_performed",
    "runtime_mutation_performed",
    "service_restart_performed",
}
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

FEE_KEYS = ("fee_bps", "fee_rate", "maker_fee_bps", "taker_fee_bps", "exec_fee", "cost_bps")
SLIPPAGE_KEYS = ("slippage_bps", "price_slippage_bps", "execution_slippage_bps")
SPREAD_KEYS = ("spread_bps", "arrival_spread_bps", "quoted_spread_bps", "bid_ask_spread_bps")
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
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


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


def _sha256_payload(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _read_json(path: Path | None) -> tuple[Any, str | None]:
    if path is None:
        return {}, None
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}, "missing"
    except OSError as exc:
        return {}, f"{type(exc).__name__}:{exc}"
    try:
        return json.loads(raw), None
    except json.JSONDecodeError as exc:
        return {}, f"json_decode_error:{exc}"


def _source_ref(path: Path | None, payload: Any, error: str | None) -> dict[str, Any]:
    return {
        "path": str(path) if path else None,
        "read_error": error,
        "schema_version": _dict(payload).get("schema_version"),
        "status": _dict(payload).get("status"),
        "sha256": _sha256_payload(payload) if payload else None,
    }


def _is_authority_key(key: str) -> bool:
    normalized = str(key or "").strip()
    return normalized in AUTHORITY_TRUE_KEYS or any(
        normalized.endswith(suffix) for suffix in AUTHORITY_TRUE_KEY_SUFFIXES
    )


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
                violations.append({"path": item_path, "key": key, "reason": "main_cost_gate_adjustment_not_none"})
            elif _is_authority_key(key) and _truthy(value):
                violations.append({"path": item_path, "key": key, "reason": "authority_truthy_value"})
            if isinstance(value, (dict, list)):
                stack.append((item_path, value))
    return violations


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


def _candidate_identity(
    *,
    candidate_id: str,
    strategy_name: str | None,
    symbol: str | None,
    side: str | None,
    outcome_horizon_minutes: str | None,
) -> dict[str, Any]:
    parsed = _parse_candidate_id(candidate_id)
    return {
        "side_cell_key": candidate_id,
        "strategy_name": _str(strategy_name or parsed.get("strategy_name")),
        "symbol": _str(symbol or parsed.get("symbol")).upper(),
        "side": _normalize_side(side or parsed.get("side")),
        "outcome_horizon_minutes": _str(
            outcome_horizon_minutes or parsed.get("outcome_horizon_minutes")
        ),
    }


def _candidate_id(row: dict[str, Any]) -> str:
    identity = _dict(row.get("candidate_identity"))
    return _str(
        row.get("candidate_id")
        or row.get("side_cell_key")
        or identity.get("candidate_id")
        or identity.get("side_cell_key")
    )


def _has_any(row: dict[str, Any], keys: tuple[str, ...]) -> bool:
    for key in keys:
        value = row.get(key)
        if value is None or value is False:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return True
    return False


def _extract_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [_dict(item) for item in payload if _dict(item)]
    data = _dict(payload)
    candidates = [
        data.get("candidate_matched_demo_fills"),
        data.get("candidate_matched_fill_rows"),
        data.get("strict_evidence_samples"),
        data.get("evidence_samples"),
        data.get("actual_order_fill_rows"),
        data.get("order_fill_rows"),
        data.get("fill_rows"),
        data.get("rows"),
        _dict(data.get("fill_evidence")).get("rows"),
        _dict(data.get("matched_control_baseline")).get("rows"),
    ]
    for rows in candidates:
        values = [_dict(item) for item in _list(rows) if _dict(item)]
        if values:
            return values
    return []


def _row_identity_reasons(row: dict[str, Any], identity: dict[str, Any], row_kind: str) -> list[str]:
    reasons: list[str] = []
    expected_side_cell = _str(identity.get("side_cell_key"))
    row_candidate = _candidate_id(row)
    if not row_candidate:
        reasons.append(f"{row_kind}_side_cell_key_missing")
    elif expected_side_cell and row_candidate != expected_side_cell:
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


def _cleanup_or_replay_reasons(row: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    outcome_source = _str(row.get("outcome_source")).lower()
    source_kind = _str(row.get("source_kind") or row.get("source_evidence_type") or row.get("evidence_type")).lower()
    if _truthy(row.get("cleanup_fill")) or _truthy(row.get("cleanup_order")) or "cleanup" in outcome_source:
        reasons.append("cleanup_fill_not_promotion_evidence")
    if _truthy(row.get("replay_only")) or _truthy(row.get("simulation_only")) or source_kind in {"replay", "simulation", "backtest"}:
        reasons.append("replay_only_not_promotion_evidence")
    return reasons


def _reason_counts(excluded: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in excluded:
        for reason in _list(item.get("reasons")):
            key = _str(reason)
            if key:
                counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _review_bool(payload: dict[str, Any], *keys: str) -> bool:
    containers = [payload, _dict(payload.get("summary")), _dict(payload.get("answers"))]
    for container in containers:
        for key in keys:
            if key in container:
                return _truthy(container.get(key))
    return False


def build_candidate_proof_evidence(
    *,
    candidate_id: str,
    strategy_name: str | None,
    symbol: str | None,
    side: str | None,
    outcome_horizon_minutes: str | None,
    serving_snapshot_id: str,
    model_version: str,
    candidate_fill_rows_packet: Any,
    matched_control_rows_packet: Any,
    execution_realism_packet: dict[str, Any],
    tail_risk_packet: dict[str, Any],
    validation_packet: dict[str, Any],
    proof_exclusion_packet: dict[str, Any],
    min_candidate_matched_demo_fills: int = 10,
    now_utc: dt.datetime | None = None,
    source_paths: dict[str, Path | None] | None = None,
    source_errors: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    now = now_utc or _utc_now()
    paths = source_paths or {}
    errors = source_errors or {}
    identity = _candidate_identity(
        candidate_id=candidate_id,
        strategy_name=strategy_name,
        symbol=symbol,
        side=side,
        outcome_horizon_minutes=outcome_horizon_minutes,
    )
    identity_missing = [key for key, value in identity.items() if not _str(value)]
    fill_rows = _extract_rows(candidate_fill_rows_packet)
    control_rows = _extract_rows(matched_control_rows_packet)
    authority_violations: list[dict[str, Any]] = []
    for payload in (
        candidate_fill_rows_packet,
        matched_control_rows_packet,
        execution_realism_packet,
        tail_risk_packet,
        validation_packet,
        proof_exclusion_packet,
    ):
        authority_violations.extend(_authority_violations(payload))

    accepted_fills = []
    excluded = []
    for row in fill_rows:
        reasons = [
            *proof_exclusion_reasons(row),
            *_row_identity_reasons(row, identity, "candidate_fill"),
            *_cleanup_or_replay_reasons(row),
        ]
        if not _has_any(row, FILL_IDENTITY_KEYS):
            reasons.append("candidate_matched_demo_fill_identity_missing")
        if reasons:
            excluded.append({"row": row, "reasons": reasons})
        else:
            accepted_fills.append(row)

    accepted_controls = []
    excluded_controls = []
    for row in control_rows:
        reasons = _row_identity_reasons(row, identity, "matched_control")
        if reasons:
            excluded_controls.append({"row": row, "reasons": reasons})
        else:
            accepted_controls.append(row)

    net_values = [
        value
        for value in (_float(row.get("realized_net_bps")) for row in accepted_fills)
        if value is not None
    ]
    avg_net = sum(net_values) / len(net_values) if net_values else None
    proof_exclusion_present = bool(excluded or excluded_controls) or _truthy(
        proof_exclusion_packet.get("proof_exclusion_present")
    )
    proof_exclusion_passed = not proof_exclusion_present and not identity_missing
    proof_exclusion_passed = proof_exclusion_passed or _truthy(
        proof_exclusion_packet.get("proof_exclusion_passed")
    )
    execution_passed = _review_bool(execution_realism_packet, "execution_realism_passed")
    tail_passed = _review_bool(tail_risk_packet, "tail_risk_review_passed")
    oos_passed = _review_bool(validation_packet, "oos_validation_passed")
    repeat_passed = _review_bool(validation_packet, "repeat_set_passed", "repeat_validation_passed")
    control_outperformance = _review_bool(
        _dict(matched_control_rows_packet),
        "matched_control_outperformance",
        "candidate_outperforms_matched_control",
    )

    blockers: list[str] = []
    if identity_missing:
        blockers.append("candidate_identity_incomplete")
    if not serving_snapshot_id:
        blockers.append("serving_snapshot_id_missing")
    if not model_version:
        blockers.append("model_version_missing")
    if len(accepted_fills) < max(1, min_candidate_matched_demo_fills):
        blockers.append("candidate_matched_demo_fills_below_floor")
    if not accepted_fills:
        blockers.append("candidate_matched_demo_fill_rows_missing")
    if not all(_has_any(row, FEE_KEYS) for row in accepted_fills):
        blockers.append("real_fee_evidence_missing")
    if not all(_has_any(row, SLIPPAGE_KEYS) for row in accepted_fills):
        blockers.append("real_slippage_evidence_missing")
    if not all(_has_any(row, SPREAD_KEYS) for row in accepted_fills):
        blockers.append("spread_evidence_missing")
    if not all(_has_any(row, CAPACITY_KEYS) for row in accepted_fills):
        blockers.append("capacity_evidence_missing")
    if avg_net is None or avg_net <= 0:
        blockers.append("net_of_fees_profitability_missing_or_nonpositive")
    if not accepted_controls:
        blockers.append("matched_control_baseline_missing")
    if not control_outperformance:
        blockers.append("matched_control_outperformance_missing_or_failed")
    if not execution_passed:
        blockers.append("execution_realism_review_missing_or_failed")
    if not tail_passed:
        blockers.append("tail_risk_review_missing_or_failed")
    if not oos_passed:
        blockers.append("oos_validation_missing_or_failed")
    if not repeat_passed:
        blockers.append("repeat_set_validation_missing_or_failed")
    if not proof_exclusion_passed:
        blockers.append("proof_exclusion_pass_missing_or_failed")
    if excluded or excluded_controls:
        blockers.append("identity_or_proof_exclusion_rows_present")

    if authority_violations:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "candidate_proof_evidence_input_authority_boundary_violation"
    elif blockers:
        status = BLOCKED_STATUS
        reason = "candidate_proof_evidence_requirements_not_satisfied"
    else:
        status = READY_STATUS
        reason = "candidate_proof_evidence_ready_for_promotion_gate"

    packet = {
        "schema_version": PROOF_EVIDENCE_SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "boundary": BOUNDARY,
        "candidate_id": candidate_id,
        "candidate_identity": identity,
        "serving_snapshot_id": serving_snapshot_id or None,
        "model_version": model_version or None,
        "proof_thresholds": {
            "min_candidate_matched_demo_fills": max(1, min_candidate_matched_demo_fills),
        },
        "fill_evidence": {
            "candidate_matched_demo_fill_count": len(accepted_fills),
            "raw_candidate_matched_demo_fill_count": len(fill_rows),
            "fee_evidence_present": bool(accepted_fills)
            and all(_has_any(row, FEE_KEYS) for row in accepted_fills),
            "slippage_evidence_present": bool(accepted_fills)
            and all(_has_any(row, SLIPPAGE_KEYS) for row in accepted_fills),
            "spread_evidence_present": bool(accepted_fills)
            and all(_has_any(row, SPREAD_KEYS) for row in accepted_fills),
            "capacity_evidence_present": bool(accepted_fills)
            and all(_has_any(row, CAPACITY_KEYS) for row in accepted_fills),
            "avg_realized_net_bps": avg_net,
            "net_of_fees_positive": avg_net is not None and avg_net > 0,
        },
        "execution_realism": {
            "execution_realism_passed": execution_passed,
            "source_ref": _source_ref(paths.get("execution_realism"), execution_realism_packet, errors.get("execution_realism")),
        },
        "tail_risk": {
            "tail_risk_review_passed": tail_passed,
            "source_ref": _source_ref(paths.get("tail_risk"), tail_risk_packet, errors.get("tail_risk")),
        },
        "validation": {
            "oos_validation_passed": oos_passed,
            "repeat_set_passed": repeat_passed,
            "source_ref": _source_ref(paths.get("validation"), validation_packet, errors.get("validation")),
        },
        "matched_control_baseline": {
            "matched_control_baseline_present": bool(accepted_controls),
            "matched_control_count": len(accepted_controls),
            "raw_matched_control_count": len(control_rows),
            "matched_control_outperformance": control_outperformance,
            "rows": accepted_controls,
        },
        "candidate_matched_demo_fills": accepted_fills,
        "proof_exclusion": {
            "proof_exclusion_passed": proof_exclusion_passed,
            "proof_exclusion_present": proof_exclusion_present,
            "proof_excluded_row_count": len(excluded) + len(excluded_controls),
            "reason_counts": _reason_counts([*excluded, *excluded_controls]),
            "external_source_ref": _source_ref(paths.get("proof_exclusion"), proof_exclusion_packet, errors.get("proof_exclusion")),
        },
        "source_refs": {
            "candidate_fill_rows": _source_ref(paths.get("candidate_fill_rows"), candidate_fill_rows_packet, errors.get("candidate_fill_rows")),
            "matched_control_rows": _source_ref(paths.get("matched_control_rows"), matched_control_rows_packet, errors.get("matched_control_rows")),
        },
        "summary": {
            "blockers": blockers,
            "authority_violation_count": len(authority_violations),
            "candidate_matched_demo_fill_count": len(accepted_fills),
            "matched_control_count": len(accepted_controls),
            "proof_excluded_row_count": len(excluded) + len(excluded_controls),
        },
        "authority_violations": authority_violations,
        "answers": {
            "source_only_review_packet": True,
            "proof_requirements_satisfied": status == READY_STATUS,
            "promotion_allowed_by_this_packet": False,
            "promotion_authority_granted": False,
            "promotion_evidence": False,
            "promotion_proof": False,
            "cost_gate_lowering_allowed": False,
            "main_cost_gate_adjustment": "NONE",
            "runtime_mutation_performed": False,
            "env_mutation_performed": False,
            "service_restart_performed": False,
            "cron_mutation_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "bybit_call_performed": False,
            "order_authority_granted": False,
            "order_submission_performed": False,
            "live_authority_granted": False,
        },
    }
    packet["packet_sha256"] = _sha256_payload(packet)
    return packet


def render_markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# Learning Candidate Proof Evidence",
        "",
        f"- Status: `{packet.get('status')}`",
        f"- Candidate: `{packet.get('candidate_id')}`",
        f"- Candidate fills: `{_dict(packet.get('fill_evidence')).get('candidate_matched_demo_fill_count')}`",
        f"- Matched controls: `{_dict(packet.get('matched_control_baseline')).get('matched_control_count')}`",
        f"- Proof exclusions: `{_dict(packet.get('proof_exclusion')).get('proof_excluded_row_count')}`",
        f"- Authority violations: `{len(_list(packet.get('authority_violations')))}`",
        "",
        "## Boundary",
        "",
        str(packet.get("boundary")),
    ]
    blockers = _list(_dict(packet.get("summary")).get("blockers"))
    if blockers:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- `{blocker}`" for blocker in blockers)
    return "\n".join(lines) + "\n"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--strategy-name", default=None)
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--side", default=None)
    parser.add_argument("--outcome-horizon-minutes", default=None)
    parser.add_argument("--serving-snapshot-id", required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--candidate-fill-rows-json", type=Path, required=True)
    parser.add_argument("--matched-control-rows-json", type=Path, required=True)
    parser.add_argument("--execution-realism-json", type=Path, default=None)
    parser.add_argument("--tail-risk-json", type=Path, default=None)
    parser.add_argument("--validation-json", type=Path, default=None)
    parser.add_argument("--proof-exclusion-json", type=Path, default=None)
    parser.add_argument("--min-candidate-matched-demo-fills", type=int, default=10)
    parser.add_argument("--json-output", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--print-json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    fill_rows, fill_error = _read_json(args.candidate_fill_rows_json)
    controls, control_error = _read_json(args.matched_control_rows_json)
    execution, execution_error = _read_json(args.execution_realism_json)
    tail, tail_error = _read_json(args.tail_risk_json)
    validation, validation_error = _read_json(args.validation_json)
    proof_exclusion, proof_exclusion_error = _read_json(args.proof_exclusion_json)
    packet = build_candidate_proof_evidence(
        candidate_id=args.candidate_id,
        strategy_name=args.strategy_name,
        symbol=args.symbol,
        side=args.side,
        outcome_horizon_minutes=args.outcome_horizon_minutes,
        serving_snapshot_id=args.serving_snapshot_id,
        model_version=args.model_version,
        candidate_fill_rows_packet=fill_rows,
        matched_control_rows_packet=controls,
        execution_realism_packet=_dict(execution),
        tail_risk_packet=_dict(tail),
        validation_packet=_dict(validation),
        proof_exclusion_packet=_dict(proof_exclusion),
        min_candidate_matched_demo_fills=args.min_candidate_matched_demo_fills,
        source_paths={
            "candidate_fill_rows": args.candidate_fill_rows_json,
            "matched_control_rows": args.matched_control_rows_json,
            "execution_realism": args.execution_realism_json,
            "tail_risk": args.tail_risk_json,
            "validation": args.validation_json,
            "proof_exclusion": args.proof_exclusion_json,
        },
        source_errors={
            "candidate_fill_rows": fill_error,
            "matched_control_rows": control_error,
            "execution_realism": execution_error,
            "tail_risk": tail_error,
            "validation": validation_error,
            "proof_exclusion": proof_exclusion_error,
        },
    )
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render_markdown(packet), encoding="utf-8")
    if args.print_json:
        print(json.dumps(packet, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
