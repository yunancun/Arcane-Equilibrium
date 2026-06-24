#!/usr/bin/env python3
"""Build a no-order construction preview for one rerouted bounded Demo candidate.

This artifact consumes a lower-price reroute review packet plus a read-only
market snapshot. It proves whether the selected candidate can be constructed
under current instrument filters, BBO freshness, passive placement, and the
candidate-scoped Demo cap before any order path is admitted.

It does not query or write PG, call Bybit, submit orders, lower the Cost Gate,
grant probe/order/live authority, append ledgers, or mutate runtime state.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, InvalidOperation
from pathlib import Path
from typing import Any


CONSTRUCTION_PREVIEW_SCHEMA_VERSION = (
    "bounded_demo_probe_candidate_construction_preview_v1"
)
LOWER_PRICE_REROUTE_REVIEW_SCHEMA_VERSION = (
    "bounded_demo_probe_lower_price_reroute_review_v1"
)
MARKET_SNAPSHOT_SCHEMA_VERSION = "bounded_probe_candidate_market_snapshot_v1"
EXPECTED_MARKET_SNAPSHOT_SOURCE = (
    "read_only_pg:market.market_tickers+market.symbol_universe_snapshots"
)

REROUTE_READY_STATUS = "LOWER_PRICE_REROUTE_READY_FOR_DEMO_CONSTRUCTION_REVIEW"
READY_STATUS = "CANDIDATE_CONSTRUCTION_PREVIEW_READY_NO_ORDER"
INPUT_REQUIRED_STATUS = "CANDIDATE_CONSTRUCTION_INPUT_REQUIRED"
CANDIDATE_MISMATCH_STATUS = "CANDIDATE_CONSTRUCTION_CANDIDATE_MISMATCH"
BBO_STALE_STATUS = "CANDIDATE_CONSTRUCTION_BBO_STALE"
NOT_FEASIBLE_STATUS = "CANDIDATE_CONSTRUCTION_NOT_FEASIBLE_UNDER_CAP"
AUTHORITY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

DEFAULT_MAX_ARTIFACT_AGE_HOURS = 24
BOUNDARY = (
    "artifact-only bounded Demo candidate construction preview; no PG query/write, "
    "Bybit call, order, config, risk, auth, runtime mutation, global Cost Gate "
    "lowering, probe authority, order authority, live/mainnet authority, ledger "
    "append, or promotion proof"
)

FORBIDDEN_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "bounded_demo_probe_authorized",
    "bybit_call_performed",
    "canonical_plan_mutation_performed",
    "cost_gate_lowering_recommended",
    "global_cost_gate_lowering_recommended",
    "ledger_append_performed",
    "live_authority_granted",
    "live_promotion_performed",
    "mainnet_authority_granted",
    "operator_authorization_object_emitted",
    "order_authority_granted",
    "order_authority_granted_in_object",
    "order_authority_granted_in_authorization_object",
    "order_submission_performed",
    "pg_query_performed",
    "pg_write_performed",
    "plan_mutation_performed",
    "probe_authority_granted",
    "probe_authority_granted_in_object",
    "probe_authority_granted_in_authorization_object",
    "promotion_evidence",
    "promotion_proof",
    "cost_gate_mutation_found",
    "runtime_mutation_performed",
    "runtime_order_authority_granted",
    "runtime_order_authority_found",
    "runtime_probe_authority_granted",
    "runtime_probe_authority_found",
    "review_grants_runtime_authority",
    "service_restart_performed",
    "writer_enabled",
}


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return str(value or "").strip()


def _present(value: Any) -> bool:
    return value is not None and _str(value) != ""


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


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _decimal_float(value: Decimal | None, ndigits: int = 8) -> float | None:
    if value is None:
        return None
    return round(float(value), ndigits)


def _floor_to_step(value: Decimal, step: Decimal) -> Decimal | None:
    if value <= 0 or step <= 0:
        return None
    units = (value / step).to_integral_value(rounding=ROUND_FLOOR)
    return units * step


def _ceil_to_step(value: Decimal, step: Decimal) -> Decimal | None:
    if value <= 0 or step <= 0:
        return None
    units = (value / step).to_integral_value(rounding=ROUND_CEILING)
    return units * step


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
        stat = path.stat()
        sha256 = hashlib.sha256(data).hexdigest()
        size_bytes = stat.st_size
        mtime_epoch_seconds = int(stat.st_mtime)
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


def _authority_preserved(
    *,
    reroute_review: dict[str, Any] | None,
    market_snapshot: dict[str, Any] | None,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    payload_rules = [
        (reroute_review, set()),
        (market_snapshot, {"pg_query_performed"}),
    ]
    for payload, allowed_true_keys in payload_rules:
        for node in _iter_nodes(_dict(payload)):
            if not isinstance(node, dict):
                continue
            for key, value in node.items():
                if (
                    key in FORBIDDEN_TRUE_KEYS
                    and key not in allowed_true_keys
                    and _contaminating_value(value)
                ):
                    reasons.append(f"{key}_contaminating")
            if _str(node.get("main_cost_gate_adjustment")).upper() not in ("", "NONE"):
                reasons.append("main_cost_gate_adjustment_not_none")
    return not reasons, sorted(set(reasons))


def _normalized_horizon(value: Any) -> int | None:
    parsed = _float(value)
    if parsed is None or not parsed.is_integer():
        return None
    return int(parsed)


def _candidate_identity(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "side_cell_key": _str(candidate.get("side_cell_key")) or None,
        "strategy_name": _str(candidate.get("strategy_name")) or None,
        "symbol": _str(candidate.get("symbol")) or None,
        "side": _str(candidate.get("side")) or None,
        "outcome_horizon_minutes": _normalized_horizon(
            candidate.get("outcome_horizon_minutes")
        ),
    }


def _identity_complete(candidate: dict[str, Any]) -> bool:
    ident = _candidate_identity(candidate)
    return all(
        [
            ident.get("side_cell_key"),
            ident.get("strategy_name"),
            ident.get("symbol"),
            ident.get("side"),
            ident.get("outcome_horizon_minutes") is not None,
        ]
    )


def _identity_key(candidate: dict[str, Any]) -> tuple[Any, Any, Any, Any, Any]:
    ident = _candidate_identity(candidate)
    return (
        ident.get("side_cell_key"),
        ident.get("strategy_name"),
        ident.get("symbol"),
        ident.get("side"),
        ident.get("outcome_horizon_minutes"),
    )


def _selected_candidate(reroute_review: dict[str, Any] | None) -> dict[str, Any]:
    return _candidate_identity(_dict(_dict(reroute_review).get("selected_candidate")))


def _snapshot_candidate(market_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    return _candidate_identity(_dict(_dict(market_snapshot).get("candidate")))


def _market_value(
    snapshot: dict[str, Any],
    key: str,
    *,
    section: str = "derived",
) -> Any:
    return _dict(snapshot.get(section)).get(key)


def _market_inputs(market_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    snapshot = _dict(market_snapshot)
    ticker = _dict(snapshot.get("ticker"))
    instrument = _dict(snapshot.get("instrument"))
    risk_limits = _dict(snapshot.get("risk_limits"))
    return {
        "instrument_status": instrument.get("status"),
        "derived_instrument_status": _market_value(snapshot, "instrument_status"),
        "best_bid": _float(ticker.get("best_bid")),
        "best_ask": _float(ticker.get("best_ask")),
        "derived_best_bid_raw": _market_value(snapshot, "best_bid"),
        "derived_best_bid": _float(_market_value(snapshot, "best_bid")),
        "derived_best_ask_raw": _market_value(snapshot, "best_ask"),
        "derived_best_ask": _float(_market_value(snapshot, "best_ask")),
        "last_price": _float(ticker.get("last_price")),
        "mark_price": _float(ticker.get("mark_price")),
        "spread_bps": _float(ticker.get("spread_bps")),
        "derived_spread_bps_raw": _market_value(snapshot, "spread_bps"),
        "derived_spread_bps": _float(_market_value(snapshot, "spread_bps")),
        "tick_size": _float(instrument.get("tick_size")),
        "qty_step": _float(instrument.get("qty_step")),
        "min_notional": _float(instrument.get("min_notional")),
        "derived_tick_size_raw": _market_value(snapshot, "tick_size"),
        "derived_tick_size": _float(_market_value(snapshot, "tick_size")),
        "derived_qty_step_raw": _market_value(snapshot, "qty_step"),
        "derived_qty_step": _float(_market_value(snapshot, "qty_step")),
        "derived_min_notional_raw": _market_value(snapshot, "min_notional"),
        "derived_min_notional": _float(_market_value(snapshot, "min_notional")),
        "cap_usdt": _float(risk_limits.get("cap_usdt")),
        "max_fresh_bbo_age_ms": _float(risk_limits.get("max_fresh_bbo_age_ms")),
        "reported_bbo_age_ms": _float(_market_value(snapshot, "bbo_age_ms")),
        "ticker_ts": ticker.get("ts"),
        "instrument_ts": instrument.get("ts"),
        "pg_snapshot_timestamp": snapshot.get("pg_snapshot_timestamp"),
        "source": snapshot.get("source"),
        "ticker_symbol": ticker.get("symbol"),
        "instrument_symbol": instrument.get("symbol"),
        "instrument_category": instrument.get("category"),
    }


def _numbers_match(left: Any, right: Any, *, tolerance: float = 1e-9) -> bool:
    if not _present(right):
        return True
    parsed_left = _float(left)
    parsed_right = _float(right)
    if parsed_left is None or parsed_right is None:
        return False
    return abs(parsed_left - parsed_right) <= tolerance


def _snapshot_internal_consistency(inputs: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    derived_status = _str(inputs.get("derived_instrument_status"))
    raw_status = _str(inputs.get("instrument_status"))
    if derived_status and (not raw_status or derived_status != raw_status):
        reasons.append("derived_instrument_status_disagrees_with_raw_instrument")
    for raw_key, derived_raw_key, derived_key in (
        ("best_bid", "derived_best_bid_raw", "derived_best_bid"),
        ("best_ask", "derived_best_ask_raw", "derived_best_ask"),
        ("spread_bps", "derived_spread_bps_raw", "derived_spread_bps"),
        ("tick_size", "derived_tick_size_raw", "derived_tick_size"),
        ("qty_step", "derived_qty_step_raw", "derived_qty_step"),
        ("min_notional", "derived_min_notional_raw", "derived_min_notional"),
    ):
        if not _numbers_match(inputs.get(raw_key), inputs.get(derived_raw_key)):
            reasons.append(f"{derived_key}_disagrees_with_raw_{raw_key}")
    return not reasons, reasons


def _effective_bbo_age_ms(
    *,
    ticker_ts: Any,
    now_utc: dt.datetime,
) -> float | None:
    parsed = _parse_dt(ticker_ts)
    if parsed is None:
        return None
    age_ms = (now_utc - parsed).total_seconds() * 1000.0
    return age_ms if age_ms >= 0.0 else None


def _placement_and_sizing(
    *,
    candidate: dict[str, Any],
    inputs: dict[str, Any],
) -> dict[str, Any]:
    side = _str(candidate.get("side")).lower()
    best_bid = _decimal(inputs.get("best_bid"))
    best_ask = _decimal(inputs.get("best_ask"))
    tick_size = _decimal(inputs.get("tick_size"))
    qty_step = _decimal(inputs.get("qty_step"))
    min_notional = _decimal(inputs.get("min_notional"))
    cap_usdt = _decimal(inputs.get("cap_usdt"))
    if not all([best_bid, best_ask, tick_size, qty_step, min_notional, cap_usdt]):
        return {
            "constructible": False,
            "reason": "missing_or_non_positive_price_filter_or_cap_input",
        }
    if best_bid <= 0 or best_ask <= 0 or best_bid >= best_ask:
        return {"constructible": False, "reason": "invalid_bbo"}
    if tick_size <= 0 or qty_step <= 0 or min_notional <= 0 or cap_usdt <= 0:
        return {"constructible": False, "reason": "invalid_filter_or_cap"}

    if side == "sell":
        limit_price = _ceil_to_step(best_ask, tick_size)
        reference_price = best_bid
        passive_against_touch = bool(limit_price and limit_price > best_bid)
        placement_mode = "sell_near_touch_post_only_at_or_above_best_ask"
    elif side == "buy":
        limit_price = _floor_to_step(best_bid, tick_size)
        reference_price = best_ask
        passive_against_touch = bool(limit_price and limit_price < best_ask)
        placement_mode = "buy_near_touch_post_only_at_or_below_best_bid"
    else:
        return {"constructible": False, "reason": "unsupported_side"}

    if limit_price is None or limit_price <= 0:
        return {"constructible": False, "reason": "limit_price_not_constructible"}

    raw_qty = cap_usdt / limit_price
    rounded_qty = _floor_to_step(raw_qty, qty_step)
    rounded_notional = (
        rounded_qty * limit_price if rounded_qty is not None else None
    )
    min_positive_qty_notional = qty_step * limit_price
    feasible = (
        passive_against_touch
        and rounded_qty is not None
        and rounded_qty > 0
        and rounded_notional is not None
        and rounded_notional >= min_notional
        and min_positive_qty_notional <= cap_usdt
    )
    blocking = []
    if not passive_against_touch:
        blocking.append("near_touch_limit_would_cross_or_not_be_passive")
    if rounded_qty is None or rounded_qty <= 0:
        blocking.append("rounded_qty_not_positive_under_cap")
    if rounded_notional is None or rounded_notional < min_notional:
        blocking.append("rounded_notional_below_min_notional")
    if min_positive_qty_notional > cap_usdt:
        blocking.append("min_positive_qty_notional_exceeds_cap")
    return {
        "constructible": feasible,
        "reason": "constructible_under_cap" if feasible else "not_constructible_under_cap",
        "placement_mode": placement_mode,
        "reference_price": _decimal_float(reference_price),
        "limit_price": _decimal_float(limit_price),
        "best_bid": _decimal_float(best_bid),
        "best_ask": _decimal_float(best_ask),
        "tick_size": _decimal_float(tick_size),
        "qty_step": _decimal_float(qty_step),
        "raw_qty": _decimal_float(raw_qty),
        "rounded_qty": _decimal_float(rounded_qty),
        "rounded_notional_usdt": _decimal_float(rounded_notional),
        "min_notional": _decimal_float(min_notional),
        "cap_usdt": _decimal_float(cap_usdt),
        "min_positive_qty_notional_usdt": _decimal_float(
            min_positive_qty_notional, ndigits=6
        ),
        "passive_against_touch": passive_against_touch,
        "blocking_reasons": blocking,
    }


def build_candidate_construction_preview(
    *,
    reroute_review: dict[str, Any] | None,
    market_snapshot: dict[str, Any] | None,
    demo_operational_authorization_available: bool = False,
    now_utc: dt.datetime | None = None,
    max_artifact_age_hours: int = DEFAULT_MAX_ARTIFACT_AGE_HOURS,
    artifact_paths: dict[str, Path | None] | None = None,
) -> dict[str, Any]:
    if max_artifact_age_hours < 1 or max_artifact_age_hours > 24 * 14:
        raise ValueError("max_artifact_age_hours must be in [1, 336]")
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    paths = artifact_paths or {}
    max_age_seconds = max_artifact_age_hours * 3600
    artifacts = {
        "reroute_review": _artifact_summary(
            name="reroute_review",
            path=paths.get("reroute_review"),
            payload=reroute_review,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        ),
        "market_snapshot": _artifact_summary(
            name="market_snapshot",
            path=paths.get("market_snapshot"),
            payload=market_snapshot,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        ),
    }
    authority_preserved, contamination_reasons = _authority_preserved(
        reroute_review=reroute_review,
        market_snapshot=market_snapshot,
    )
    selected = _selected_candidate(reroute_review)
    snapshot_candidate = _snapshot_candidate(market_snapshot)
    candidate_match = (
        _identity_complete(selected)
        and _identity_complete(snapshot_candidate)
        and _identity_key(selected) == _identity_key(snapshot_candidate)
    )
    inputs = _market_inputs(market_snapshot)
    placement = _placement_and_sizing(candidate=selected, inputs=inputs)
    selected_symbol = _str(selected.get("symbol"))
    market_snapshot_source_valid = (
        _str(inputs.get("source")) == EXPECTED_MARKET_SNAPSHOT_SOURCE
    )
    market_snapshot_consistent, consistency_reasons = _snapshot_internal_consistency(
        inputs
    )
    market_data_symbols_match = (
        bool(selected_symbol)
        and _str(inputs.get("ticker_symbol")) == selected_symbol
        and _str(inputs.get("instrument_symbol")) == selected_symbol
    )
    reroute_ready = (
        artifacts["reroute_review"].get("status") == "FRESH"
        and artifacts["reroute_review"].get("schema_version")
        == LOWER_PRICE_REROUTE_REVIEW_SCHEMA_VERSION
        and _dict(reroute_review).get("status") == REROUTE_READY_STATUS
    )
    market_ready = (
        artifacts["market_snapshot"].get("status") == "FRESH"
        and artifacts["market_snapshot"].get("schema_version")
        == MARKET_SNAPSHOT_SCHEMA_VERSION
        and market_snapshot_source_valid
        and market_snapshot_consistent
    )
    instrument_trading = _str(inputs.get("instrument_status")) == "Trading"
    reported_bbo_age_ms = _float(inputs.get("reported_bbo_age_ms"))
    effective_bbo_age_ms = _effective_bbo_age_ms(
        ticker_ts=inputs.get("ticker_ts"),
        now_utc=now,
    )
    max_fresh_ms = _float(inputs.get("max_fresh_bbo_age_ms"))
    bbo_fresh = (
        effective_bbo_age_ms is not None
        and max_fresh_ms is not None
        and effective_bbo_age_ms <= max_fresh_ms
    )
    blocking_gates: list[str] = []
    if not reroute_ready:
        blocking_gates.append("reroute_review_ready")
    if not market_ready:
        blocking_gates.append("market_snapshot_ready")
    if not market_snapshot_source_valid:
        blocking_gates.append("market_snapshot_read_only_source")
    if not market_snapshot_consistent:
        blocking_gates.append("market_snapshot_internal_consistency")
        blocking_gates.extend(consistency_reasons)
    if not candidate_match:
        blocking_gates.append("candidate_exact_match")
    if not market_data_symbols_match:
        blocking_gates.append("market_data_symbol_match")
    if not instrument_trading:
        blocking_gates.append("instrument_status_trading")
    if not bbo_fresh:
        blocking_gates.append("bbo_freshness")
    if bbo_fresh and placement.get("constructible") is not True:
        blocking_gates.extend(_list(placement.get("blocking_reasons")) or ["constructible_under_cap"])
    elif not bbo_fresh and placement.get("constructible") is not True:
        blocking_gates.append("construction_deferred_until_fresh_bbo")

    if not authority_preserved:
        status = AUTHORITY_VIOLATION_STATUS
        reason = "input_artifacts_contain_authority_or_mutation_contamination"
        next_actions = ["remove_authority_or_mutation_contamination_before_preview"]
    elif not reroute_ready or not market_ready:
        status = INPUT_REQUIRED_STATUS
        reason = "fresh_schema_valid_reroute_review_and_market_snapshot_required"
        next_actions = ["refresh_missing_or_stale_input_artifacts"]
    elif not candidate_match or not market_data_symbols_match:
        status = CANDIDATE_MISMATCH_STATUS
        reason = "reroute_review_candidate_and_market_snapshot_market_data_mismatch"
        next_actions = ["refresh_candidate_specific_market_snapshot_for_selected_reroute"]
    elif not bbo_fresh:
        status = BBO_STALE_STATUS
        reason = "market_snapshot_bbo_age_exceeds_freshness_gate"
        next_actions = ["refresh_read_only_market_snapshot_before_demo_order_admission"]
    elif not instrument_trading or placement.get("constructible") is not True:
        status = NOT_FEASIBLE_STATUS
        reason = "candidate_not_constructible_under_current_filters_cap_or_passive_placement"
        next_actions = ["reroute_to_another_cap_feasible_candidate_or_repair_filters"]
    else:
        status = READY_STATUS
        reason = "candidate_constructible_under_current_filters_cap_and_fresh_bbo"
        next_actions = [
            "continue_to_demo_order_admission_review_without_lowering_global_cost_gate",
            "require_candidate_matched_fill_attribution_fee_slippage_controls",
            "do_not_count_unattributed_or_flash_dip_buy_fills_as_probe_proof",
        ]

    return {
        "schema_version": CONSTRUCTION_PREVIEW_SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "candidate": selected,
        "snapshot_candidate": snapshot_candidate,
        "candidate_match": candidate_match,
        "market_inputs": {
            "instrument_status": inputs.get("instrument_status"),
            "derived_instrument_status": inputs.get("derived_instrument_status"),
            "best_bid": _round(inputs.get("best_bid")),
            "best_ask": _round(inputs.get("best_ask")),
            "derived_best_bid": _round(inputs.get("derived_best_bid")),
            "derived_best_ask": _round(inputs.get("derived_best_ask")),
            "last_price": _round(inputs.get("last_price")),
            "mark_price": _round(inputs.get("mark_price")),
            "spread_bps": _round(inputs.get("spread_bps"), 4),
            "derived_spread_bps": _round(inputs.get("derived_spread_bps"), 4),
            "tick_size": _round(inputs.get("tick_size"), 8),
            "qty_step": _round(inputs.get("qty_step"), 8),
            "min_notional": _round(inputs.get("min_notional"), 4),
            "derived_tick_size": _round(inputs.get("derived_tick_size"), 8),
            "derived_qty_step": _round(inputs.get("derived_qty_step"), 8),
            "derived_min_notional": _round(inputs.get("derived_min_notional"), 4),
            "cap_usdt": _round(inputs.get("cap_usdt"), 4),
            "max_fresh_bbo_age_ms": _round(max_fresh_ms, 3),
            "reported_bbo_age_ms": _round(reported_bbo_age_ms, 3),
            "effective_bbo_age_ms": _round(effective_bbo_age_ms, 3),
            "bbo_age_ms": _round(effective_bbo_age_ms, 3),
            "ticker_ts": inputs.get("ticker_ts"),
            "instrument_ts": inputs.get("instrument_ts"),
            "pg_snapshot_timestamp": inputs.get("pg_snapshot_timestamp"),
            "source": inputs.get("source"),
            "ticker_symbol": inputs.get("ticker_symbol"),
            "instrument_symbol": inputs.get("instrument_symbol"),
            "instrument_category": inputs.get("instrument_category"),
        },
        "construction": placement,
        "readiness": {
            "reroute_review_ready": reroute_ready,
            "market_snapshot_ready": market_ready,
            "market_snapshot_read_only_source": market_snapshot_source_valid,
            "market_snapshot_internal_consistency": market_snapshot_consistent,
            "market_snapshot_internal_consistency_reasons": consistency_reasons,
            "candidate_exact_match": candidate_match,
            "market_data_symbols_match": market_data_symbols_match,
            "instrument_status_trading": instrument_trading,
            "bbo_fresh": bbo_fresh,
            "constructible_under_cap": placement.get("constructible") is True,
            "blocking_gates": sorted(set(blocking_gates)),
            "blocking_gate_count": len(set(blocking_gates)),
        },
        "artifacts": artifacts,
        "blocking_gates": sorted(set(blocking_gates)),
        "blocking_gate_count": len(set(blocking_gates)),
        "next_actions": next_actions,
        "answers": {
            "candidate_construction_preview_ready_no_order": status == READY_STATUS,
            "demo_operational_authorization_available_from_thread": (
                demo_operational_authorization_available is True
            ),
            "runtime_mutation_performed": False,
            "canonical_plan_mutation_performed": False,
            "ledger_append_performed": False,
            "pg_query_performed": False,
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
    construction = _dict(packet.get("construction"))
    inputs = _dict(packet.get("market_inputs"))
    readiness = _dict(packet.get("readiness"))
    lines = [
        "# Bounded Demo Candidate Construction Preview",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: {packet.get('reason')}",
        f"- Candidate: `{_dict(packet.get('candidate')).get('side_cell_key')}`",
        f"- Instrument status: `{inputs.get('instrument_status')}`",
        f"- BBO age ms: `{inputs.get('bbo_age_ms')}` / max `{inputs.get('max_fresh_bbo_age_ms')}`",
        f"- Best bid/ask: `{inputs.get('best_bid')}` / `{inputs.get('best_ask')}`",
        f"- Limit price: `{construction.get('limit_price')}`",
        f"- Rounded qty: `{construction.get('rounded_qty')}`",
        f"- Rounded notional USDT: `{construction.get('rounded_notional_usdt')}`",
        f"- Min positive qty notional USDT: `{construction.get('min_positive_qty_notional_usdt')}`",
        f"- Blocking gates: `{readiness.get('blocking_gates')}`",
        f"- Boundary: {packet.get('boundary')}",
        "",
        "## Input Artifacts",
        "",
    ]
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
    parser.add_argument("--reroute-review-json", type=Path, required=True)
    parser.add_argument("--market-snapshot-json", type=Path, required=True)
    parser.add_argument("--demo-operational-authorization-available", action="store_true")
    parser.add_argument("--max-artifact-age-hours", type=int, default=24)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    paths = {
        "reroute_review": args.reroute_review_json,
        "market_snapshot": args.market_snapshot_json,
    }
    packet = build_candidate_construction_preview(
        reroute_review=_read_json(args.reroute_review_json),
        market_snapshot=_read_json(args.market_snapshot_json),
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
