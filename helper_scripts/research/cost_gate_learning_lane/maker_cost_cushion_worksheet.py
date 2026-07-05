#!/usr/bin/env python3
"""Build a source-only maker/taker cost-cushion worksheet.

This worksheet consumes an existing no-order construction preview and an
existing candidate edge packet. It computes conservative spread/fee/slippage
stress margins for the reviewed AVAX path, but it does not call Bybit, query or
write PG, submit orders, lower gates, grant authority, mutate runtime state, or
write ``_latest``.
"""

from __future__ import annotations

import argparse
import datetime as dt
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


SCHEMA_VERSION = "cost_gate_maker_cost_cushion_worksheet_v1"
READY_STATUS = "MAKER_COST_CUSHION_WORKSHEET_READY_NO_ORDER"
NONPOSITIVE_STATUS = "MAKER_COST_CUSHION_NONPOSITIVE_NO_ORDER"
PREVIEW_NOT_READY_STATUS = "CONSTRUCTION_PREVIEW_INPUT_NOT_READY"
EDGE_NOT_READY_STATUS = "CANDIDATE_EDGE_INPUT_NOT_READY"
CANDIDATE_MISMATCH_STATUS = "CANDIDATE_MISSING_OR_MISMATCH"
COST_INPUT_MISSING_STATUS = "MARKET_COST_INPUT_MISSING"
ASSUMPTION_INVALID_STATUS = "COST_CUSHION_ASSUMPTION_INVALID"
EDGE_CONFLICT_STATUS = "CANDIDATE_EDGE_INPUT_CONFLICT"
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

PREVIEW_SCHEMA_VERSION = "bounded_demo_probe_candidate_construction_preview_v1"
PREVIEW_READY_STATUS = "CANDIDATE_CONSTRUCTION_PREVIEW_READY_NO_ORDER"
ATOMIC_SUMMARY_SCHEMA_VERSION = "cost_gate_atomic_quote_adapter_preview_runner_v1"
ATOMIC_SUMMARY_READY_STATUS = "ATOMIC_QUOTE_ADAPTER_PREVIEW_READY_NO_ORDER"
REROUTE_SCHEMA_VERSION = "bounded_demo_probe_lower_price_reroute_review_v1"
REROUTE_READY_STATUS = "LOWER_PRICE_REROUTE_READY_FOR_DEMO_CONSTRUCTION_REVIEW"

IDENTITY_FIELDS = [
    "side_cell_key",
    "strategy_name",
    "symbol",
    "side",
    "outcome_horizon_minutes",
]

BOUNDARY = (
    "source-only maker/taker cost-cushion worksheet from existing no-order "
    "artifacts; no Bybit call, private/auth/order endpoint, PG query/write, "
    "_latest overwrite, order, cancel, modify, config, risk, auth, runtime, "
    "service, env, or crontab mutation, Cost Gate lowering, freshness gate "
    "lowering, probe authority, order authority, live/mainnet authority, "
    "ledger append, promotion proof, or profit proof"
)

FORBIDDEN_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "adapter_enabled",
    "auth_headers_present",
    "bounded_demo_probe_authorized",
    "bybit_call_performed",
    "bybit_private_call_performed",
    "canonical_plan_mutation_performed",
    "cap_envelope_mutation_allowed",
    "cap_mutation_performed",
    "config_mutation_performed",
    "cookie_headers_present",
    "cost_gate_lowering_recommended",
    "cost_gate_proof",
    "crontab_mutation_performed",
    "env_mutation_performed",
    "environment_mutation_performed",
    "execution_authority",
    "freshness_gate_lowering_recommended",
    "global_cost_gate_lowering_recommended",
    "ledger_append_performed",
    "live_authority_granted",
    "live_promotion_performed",
    "mainnet_authority_granted",
    "operator_authorization_object_emitted",
    "order_admission_ready",
    "order_authority",
    "order_authority_granted",
    "order_cancel_modify_performed",
    "order_cancel_performed",
    "order_modify_performed",
    "order_submission_performed",
    "pg_query_performed",
    "pg_write_performed",
    "plan_mutation_performed",
    "private_endpoint_called",
    "probe_authority",
    "probe_authority_granted",
    "profit_proof",
    "promotion_evidence",
    "promotion_proof",
    "risk_mutation_performed",
    "runtime_env_mutation_performed",
    "runtime_mutation_performed",
    "service_restart_performed",
    "writer_enabled",
}

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
            "y",
            "on",
            "active",
            "admit",
            "admitted",
            "allow",
            "allowed",
            "enabled",
            "grant",
            "granted",
            "permit",
            "permitted",
            "present",
            "authorize",
            "authorized",
            "ready",
        }
    return False


def _forbidden_signal(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        text = value.strip().lower()
        return bool(text) and text not in FALSE_SAFE_STRINGS
    return True


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _positive(value: Any) -> float | None:
    parsed = _number(value)
    return parsed if parsed is not None and parsed > 0 else None


def _nonnegative(value: Any) -> float | None:
    parsed = _number(value)
    return parsed if parsed is not None and parsed >= 0 else None


def _round(value: Any, ndigits: int = 6) -> float | None:
    parsed = _number(value)
    return round(parsed, ndigits) if parsed is not None else None


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
        for key in FORBIDDEN_TRUE_KEYS:
            if _forbidden_signal(data.get(key)):
                reasons.append(f"{key}_true")
        stack.extend(value for value in data.values() if isinstance(value, (dict, list)))
    return not reasons, sorted(set(reasons))


def _horizon(value: Any) -> int | None:
    parsed = _number(value)
    if parsed is None:
        return None
    as_int = int(parsed)
    return as_int if parsed == as_int else None


def _candidate_from_preview(payload: dict[str, Any]) -> dict[str, Any]:
    return _candidate(_dict(payload.get("candidate")))


def _candidate_from_atomic_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return _candidate(_dict(payload.get("candidate")))


def _candidate_from_reroute(payload: dict[str, Any]) -> dict[str, Any]:
    return _candidate(_dict(payload.get("selected_candidate") or payload.get("candidate")))


def _candidate(raw: dict[str, Any]) -> dict[str, Any]:
    candidate: dict[str, Any] = {}
    for key in IDENTITY_FIELDS:
        if key == "outcome_horizon_minutes":
            candidate[key] = _horizon(raw.get(key))
        else:
            value = _str(raw.get(key))
            candidate[key] = value or None
    return candidate


def _candidate_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(candidate.get(key) for key in IDENTITY_FIELDS)


def _candidate_match(candidates: list[dict[str, Any]]) -> bool:
    non_empty = [candidate for candidate in candidates if candidate]
    if len(non_empty) != len(candidates):
        return False
    if not all(_candidate_complete(candidate) for candidate in non_empty):
        return False
    if not all(_candidate_self_consistent(candidate) for candidate in non_empty):
        return False
    first = _candidate_key(non_empty[0])
    return all(_candidate_key(candidate) == first for candidate in non_empty[1:])


def _candidate_complete(candidate: dict[str, Any]) -> bool:
    return all(candidate.get(key) not in (None, "") for key in IDENTITY_FIELDS)


def _candidate_self_consistent(candidate: dict[str, Any]) -> bool:
    side_cell_key = _str(candidate.get("side_cell_key"))
    parts = side_cell_key.split("|")
    if len(parts) != 3:
        return False
    strategy, symbol, side = parts
    return (
        strategy == _str(candidate.get("strategy_name"))
        and symbol == _str(candidate.get("symbol"))
        and side == _str(candidate.get("side"))
    )


def _candidate_identity_reasons(candidates: list[dict[str, Any]]) -> list[str]:
    reasons: list[str] = []
    for index, candidate in enumerate(candidates):
        if not candidate:
            reasons.append(f"candidate_{index}_missing")
            continue
        missing = [key for key in IDENTITY_FIELDS if candidate.get(key) in (None, "")]
        for key in missing:
            reasons.append(f"candidate_{index}_{key}_missing")
        if not missing and not _candidate_self_consistent(candidate):
            reasons.append(f"candidate_{index}_side_cell_key_inconsistent")
    if not reasons and candidates and not _candidate_match(candidates):
        reasons.append("candidate_identity_mismatch_across_inputs")
    return sorted(set(reasons))


def _candidate_payload_for_output(
    preview: dict[str, Any],
    atomic_summary: dict[str, Any],
    reroute_review: dict[str, Any],
) -> dict[str, Any]:
    candidates = [
        _candidate_from_preview(preview),
        *([_candidate_from_atomic_summary(atomic_summary)] if atomic_summary else []),
        *([_candidate_from_reroute(reroute_review)] if reroute_review else []),
    ]
    if _candidate_match(candidates):
        return candidates[0]
    return {}


def _edge_sources(
    *,
    atomic_summary: dict[str, Any],
    atomic_summary_path: Path | None,
    reroute_review: dict[str, Any],
    reroute_review_path: Path | None,
) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    summary_edge = _positive(_dict(atomic_summary.get("candidate")).get("avg_net_bps"))
    if summary_edge is not None:
        sources.append(
            {
                "source": "atomic_summary.candidate.avg_net_bps",
                "path": str(atomic_summary_path) if atomic_summary_path else None,
                "avg_net_bps": _round(summary_edge),
                "input_kind": "modeled_candidate_avg_net_bps_upstream",
            }
        )
    reroute_edge = _positive(
        _dict(reroute_review.get("selected_candidate") or reroute_review.get("candidate")).get(
            "avg_net_bps"
        )
    )
    if reroute_edge is not None:
        sources.append(
            {
                "source": "reroute_review.selected_candidate.avg_net_bps",
                "path": str(reroute_review_path) if reroute_review_path else None,
                "avg_net_bps": _round(reroute_edge),
                "input_kind": "modeled_candidate_avg_net_bps_upstream",
            }
        )
    return sources


def _edge_conflict(edge_sources: list[dict[str, Any]]) -> bool:
    values = [
        source["avg_net_bps"]
        for source in edge_sources
        if _number(source.get("avg_net_bps")) is not None
    ]
    if len(values) < 2:
        return False
    first = values[0]
    return any(abs(value - first) > 0.0001 for value in values[1:])


def _preview_ready(preview: dict[str, Any]) -> bool:
    return (
        preview.get("schema_version") == PREVIEW_SCHEMA_VERSION
        and preview.get("status") == PREVIEW_READY_STATUS
        and _dict(preview.get("answers")).get("candidate_construction_preview_ready_no_order")
        is True
        and _dict(preview.get("construction")).get("constructible") is True
    )


def _optional_ready(
    payload: dict[str, Any],
    *,
    schema_version: str,
    ready_status: str,
) -> bool:
    return not payload or (
        payload.get("schema_version") == schema_version and payload.get("status") == ready_status
    )


def _calc(
    *,
    modeled_avg_net_bps: float,
    spread_bps: float,
    maker_fee_bps_per_side: float,
    taker_fee_bps_per_side: float,
    slippage_buffer_bps: float,
    notional_usdt: float | None,
) -> dict[str, Any]:
    residual = modeled_avg_net_bps - spread_bps - slippage_buffer_bps
    maker_round_trip = maker_fee_bps_per_side * 2.0
    taker_round_trip = taker_fee_bps_per_side * 2.0
    maker_margin = residual - maker_round_trip
    taker_margin = residual - taker_round_trip

    def margin_usdt(margin_bps: float) -> float | None:
        if notional_usdt is None:
            return None
        return notional_usdt * margin_bps / 10000.0

    return {
        "input_edge_interpretation": (
            "modeled_avg_net_bps is upstream candidate evidence, not current "
            "account fee proof. Conservative stress margins subtract explicit "
            "spread, fee, and slippage assumptions and may double-count costs "
            "if the upstream avg_net_bps already included similar cost terms."
        ),
        "modeled_avg_net_bps": _round(modeled_avg_net_bps),
        "observed_preview_spread_bps": _round(spread_bps),
        "slippage_buffer_bps": _round(slippage_buffer_bps),
        "residual_after_spread_slippage_bps": _round(residual),
        "additional_fee_stress_capacity_per_side_bps_before_zero": _round(residual / 2.0),
        "maker_scenario": {
            "fee_assumption_bps_per_side": _round(maker_fee_bps_per_side),
            "round_trip_fee_stress_bps": _round(maker_round_trip),
            "conservative_stress_margin_bps": _round(maker_margin),
            "conservative_stress_margin_usdt_at_preview_notional": _round(
                margin_usdt(maker_margin),
                ndigits=8,
            ),
            "positive_after_stress": maker_margin > 0,
            "intended_liquidity_role": "maker_post_only",
            "order_admission_ready": False,
        },
        "taker_failure_analysis_scenario": {
            "fee_assumption_bps_per_side": _round(taker_fee_bps_per_side),
            "round_trip_fee_stress_bps": _round(taker_round_trip),
            "conservative_stress_margin_bps": _round(taker_margin),
            "conservative_stress_margin_usdt_at_preview_notional": _round(
                margin_usdt(taker_margin),
                ndigits=8,
            ),
            "positive_after_stress": taker_margin > 0,
            "taker_conversion_counts_as_maker_path_success": False,
            "order_admission_ready": False,
        },
    }


def build_maker_cost_cushion_worksheet(
    *,
    construction_preview: dict[str, Any] | None,
    atomic_summary: dict[str, Any] | None = None,
    reroute_review: dict[str, Any] | None = None,
    construction_preview_path: Path | None = None,
    atomic_summary_path: Path | None = None,
    reroute_review_path: Path | None = None,
    maker_fee_bps_per_side: float = 2.0,
    taker_fee_bps_per_side: float = 5.5,
    slippage_buffer_bps: float = 1.0,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    preview = _dict(construction_preview)
    summary = _dict(atomic_summary)
    reroute = _dict(reroute_review)
    authority_ok, authority_reasons = _authority_preserved(preview, summary, reroute)
    preview_ready = _preview_ready(preview)
    summary_ready = _optional_ready(
        summary,
        schema_version=ATOMIC_SUMMARY_SCHEMA_VERSION,
        ready_status=ATOMIC_SUMMARY_READY_STATUS,
    )
    reroute_ready = _optional_ready(
        reroute,
        schema_version=REROUTE_SCHEMA_VERSION,
        ready_status=REROUTE_READY_STATUS,
    )
    candidates = [
        _candidate_from_preview(preview),
        *([_candidate_from_atomic_summary(summary)] if summary else []),
        *([_candidate_from_reroute(reroute)] if reroute else []),
    ]
    candidates_match = _candidate_match(candidates)
    candidate_identity_reasons = _candidate_identity_reasons(candidates)
    candidate = _candidate_payload_for_output(preview, summary, reroute)
    edge_sources = _edge_sources(
        atomic_summary=summary,
        atomic_summary_path=atomic_summary_path,
        reroute_review=reroute,
        reroute_review_path=reroute_review_path,
    )
    edge_conflict = _edge_conflict(edge_sources)
    modeled_avg_net_bps = (
        _positive(edge_sources[0].get("avg_net_bps")) if edge_sources else None
    )
    market_inputs = _dict(preview.get("market_inputs"))
    construction = _dict(preview.get("construction"))
    spread_bps = _positive(
        market_inputs.get("spread_bps") or market_inputs.get("derived_spread_bps")
    )
    maker_fee = _nonnegative(maker_fee_bps_per_side)
    taker_fee = _nonnegative(taker_fee_bps_per_side)
    slippage = _nonnegative(slippage_buffer_bps)
    preview_notional = _positive(construction.get("rounded_notional_usdt"))

    if not authority_ok:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "authority_boundary_violation_in_inputs"
    elif not preview_ready or not summary_ready or not reroute_ready:
        status = PREVIEW_NOT_READY_STATUS
        reason = "required_no_order_input_not_ready"
    elif not candidates_match:
        status = CANDIDATE_MISMATCH_STATUS
        reason = "candidate_missing_or_mismatch_across_inputs"
    elif not edge_sources or modeled_avg_net_bps is None:
        status = EDGE_NOT_READY_STATUS
        reason = "positive_modeled_candidate_avg_net_bps_missing"
    elif edge_conflict:
        status = EDGE_CONFLICT_STATUS
        reason = "modeled_candidate_avg_net_bps_conflict_across_inputs"
    elif spread_bps is None or preview_notional is None:
        status = COST_INPUT_MISSING_STATUS
        reason = "preview_spread_or_notional_missing"
    elif maker_fee is None or taker_fee is None or slippage is None:
        status = ASSUMPTION_INVALID_STATUS
        reason = "fee_or_slippage_assumption_negative_or_nonfinite"
    else:
        calc = _calc(
            modeled_avg_net_bps=modeled_avg_net_bps,
            spread_bps=spread_bps,
            maker_fee_bps_per_side=maker_fee,
            taker_fee_bps_per_side=taker_fee,
            slippage_buffer_bps=slippage,
            notional_usdt=preview_notional,
        )
        maker_margin = _dict(calc.get("maker_scenario")).get(
            "conservative_stress_margin_bps"
        )
        if _number(maker_margin) is not None and maker_margin > 0:
            status = READY_STATUS
            reason = "maker_cost_cushion_positive_under_explicit_stress_assumptions"
        else:
            status = NONPOSITIVE_STATUS
            reason = "maker_cost_cushion_nonpositive_under_explicit_stress_assumptions"

    calc = (
        _calc(
            modeled_avg_net_bps=modeled_avg_net_bps,
            spread_bps=spread_bps,
            maker_fee_bps_per_side=maker_fee,
            taker_fee_bps_per_side=taker_fee,
            slippage_buffer_bps=slippage,
            notional_usdt=preview_notional,
        )
        if status in (READY_STATUS, NONPOSITIVE_STATUS)
        else {}
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "source_inputs": {
            "construction_preview_path": (
                str(construction_preview_path) if construction_preview_path else None
            ),
            "construction_preview_schema_version": preview.get("schema_version"),
            "construction_preview_status": preview.get("status"),
            "atomic_summary_path": str(atomic_summary_path) if atomic_summary_path else None,
            "atomic_summary_schema_version": summary.get("schema_version"),
            "atomic_summary_status": summary.get("status"),
            "reroute_review_path": str(reroute_review_path) if reroute_review_path else None,
            "reroute_review_schema_version": reroute.get("schema_version"),
            "reroute_review_status": reroute.get("status"),
            "authority_preserved": authority_ok,
            "authority_contamination_reasons": authority_reasons,
            "candidate_match": candidates_match,
            "candidate_identity_reasons": candidate_identity_reasons,
            "edge_sources": edge_sources,
            "edge_conflict": edge_conflict,
        },
        "candidate": candidate if status in (READY_STATUS, NONPOSITIVE_STATUS) else {},
        "preview_market_context": {
            "best_bid": _round(market_inputs.get("best_bid")),
            "best_ask": _round(market_inputs.get("best_ask")),
            "bbo_age_ms": _round(
                market_inputs.get("effective_bbo_age_ms")
                or market_inputs.get("bbo_age_ms")
            ),
            "max_fresh_bbo_age_ms": _round(market_inputs.get("max_fresh_bbo_age_ms")),
            "spread_bps": _round(spread_bps),
            "limit_price": _round(construction.get("limit_price")),
            "rounded_qty": _round(construction.get("rounded_qty")),
            "rounded_notional_usdt": _round(preview_notional),
            "cap_usdt": _round(construction.get("cap_usdt")),
            "placement_mode": construction.get("placement_mode"),
            "passive_against_touch": construction.get("passive_against_touch") is True,
        },
        "assumptions": {
            "maker_fee_bps_per_side": _round(maker_fee),
            "taker_fee_bps_per_side": _round(taker_fee),
            "slippage_buffer_bps": _round(slippage),
            "fee_source": "operator/research stress assumption, not current account fee proof",
            "slippage_source": "operator/research stress assumption, not measured fill slippage",
            "assumptions_are_order_authority": False,
        },
        "cost_cushion": calc,
        "readiness": {
            "worksheet_ready_no_order": status == READY_STATUS,
            "maker_margin_positive": _dict(calc.get("maker_scenario")).get(
                "positive_after_stress"
            )
            is True,
            "taker_margin_positive_for_failure_analysis": _dict(
                calc.get("taker_failure_analysis_scenario")
            ).get("positive_after_stress")
            is True,
            "preview_ready": preview_ready,
            "candidate_match": candidates_match,
            "authority_preserved": authority_ok,
            "edge_conflict": edge_conflict,
            "order_admission_ready": False,
            "promotion_evidence": False,
        },
        "failure_conditions": [
            "candidate_identity_mismatch",
            "construction_preview_not_ready_or_not_constructible",
            "modeled_edge_missing_or_conflicting",
            "spread_or_notional_missing",
            "fee_or_slippage_assumption_negative_or_nonfinite",
            "maker_conservative_stress_margin_bps_less_than_or_equal_zero",
            "future_actual_fee_or_slippage_missing_from_outcome_review",
            "future_fill_not_candidate_matched",
            "unattributed_or_cleanup_or_flash_dip_buy_fill_counted_as_proof",
            "Cost Gate or freshness gate lowered",
            "order/probe/live authority inferred from this worksheet",
        ],
        "max_safe_next_action": (
            "package worksheet into operator review packet only; require separate "
            "candidate-scoped bounded Demo authorization and E3/BB order-envelope "
            "review before any runtime/order path"
        ),
        "answers": {
            "source_only_research_artifact": True,
            "maker_cost_cushion_worksheet_ready_no_order": status == READY_STATUS,
            "consumed_existing_public_quote_artifact": bool(summary),
            "bybit_call_performed": False,
            "bybit_private_call_performed": False,
            "new_bybit_public_market_data_call_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "runtime_mutation_performed": False,
            "config_mutation_performed": False,
            "risk_mutation_performed": False,
            "crontab_mutation_performed": False,
            "service_restart_performed": False,
            "bounded_demo_probe_authorized": False,
            "operator_authorization_object_emitted": False,
            "global_cost_gate_lowering_recommended": False,
            "freshness_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "live_authority_granted": False,
            "order_admission_ready": False,
            "order_submission_performed": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# Maker Cost Cushion Worksheet",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Candidate: `{_dict(packet.get('candidate')).get('side_cell_key')}`",
        f"- Boundary: {packet.get('boundary')}",
        "",
        "## Preview Context",
        "",
    ]
    for key, value in _dict(packet.get("preview_market_context")).items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Assumptions", ""])
    for key, value in _dict(packet.get("assumptions")).items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Cost Cushion", "", "```json"])
    lines.append(
        json.dumps(
            _dict(packet.get("cost_cushion")),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    lines.extend(["```", "", "## No-Authority Answers", ""])
    for key, value in _dict(packet.get("answers")).items():
        lines.append(f"- `{key}`: `{value}`")
    return "\n".join(lines) + "\n"


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--construction-preview-json", type=Path, required=True)
    parser.add_argument("--atomic-summary-json", type=Path)
    parser.add_argument("--reroute-review-json", type=Path)
    parser.add_argument("--maker-fee-bps-per-side", type=float, default=2.0)
    parser.add_argument("--taker-fee-bps-per-side", type=float, default=5.5)
    parser.add_argument("--slippage-buffer-bps", type=float, default=1.0)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_maker_cost_cushion_worksheet(
        construction_preview=_read_json(args.construction_preview_json),
        atomic_summary=_read_json(args.atomic_summary_json),
        reroute_review=_read_json(args.reroute_review_json),
        construction_preview_path=args.construction_preview_json,
        atomic_summary_path=args.atomic_summary_json,
        reroute_review_path=args.reroute_review_json,
        maker_fee_bps_per_side=args.maker_fee_bps_per_side,
        taker_fee_bps_per_side=args.taker_fee_bps_per_side,
        slippage_buffer_bps=args.slippage_buffer_bps,
    )
    markdown = render_markdown(packet)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True))
    elif not args.output and not args.json_output:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
    "execution_authority",
    "order_authority",
    "probe_authority",
