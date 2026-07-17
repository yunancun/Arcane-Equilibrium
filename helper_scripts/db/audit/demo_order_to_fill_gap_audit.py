#!/usr/bin/env python3
"""Read-only audit for demo orders that did not fill.

The data-flow monitor can say "orders exist but fills do not"; this script
explains the execution side of that gap by comparing recent demo orders with
their intent metadata, order state changes, fills, and observed BBO touchability.

No PG writes, no Bybit calls, no order placement, no risk/config/auth/runtime
mutation, and no Cost Gate mutation.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
import math
import os
from pathlib import Path
import sys
from typing import Any
import uuid

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from helper_scripts.lib.pg_connect import connect_report_pg  # noqa: E402


SCHEMA_VERSION = "demo_order_to_fill_gap_audit_v1"
VALID_ENGINE_MODES = {"paper", "demo", "live_demo", "live", "live_testnet", "replay"}
BOUNDARY = (
    "read-only PG SELECT; no Bybit call, order, config, risk, auth, runtime, "
    "schema, Cost Gate, probe, or promotion mutation"
)
STATEMENT_TIMEOUT_SQLSTATE = "57014"
STATEMENT_TIMEOUT_MESSAGE_PRIMARY = "canceling statement due to statement timeout"


def _is_statement_timeout(exc: BaseException) -> bool:
    if getattr(exc, "pgcode", None) != STATEMENT_TIMEOUT_SQLSTATE:
        return False
    diag = getattr(exc, "diag", None)
    message_primary = getattr(diag, "message_primary", None)
    if not isinstance(message_primary, str):
        return False
    normalized = " ".join(message_primary.split()).casefold()
    return normalized == STATEMENT_TIMEOUT_MESSAGE_PRIMARY


@dataclass(frozen=True)
class AuditConfig:
    engine_modes: tuple[str, ...]
    lookback_hours: int = 48
    touch_window_minutes: int = 24 * 60
    placement_window_seconds: int = 30
    top_limit: int = 50
    deep_gap_bps: float = 500.0


def validate_config(cfg: AuditConfig) -> None:
    if not cfg.engine_modes:
        raise ValueError("at least one engine mode is required")
    bad = [mode for mode in cfg.engine_modes if mode not in VALID_ENGINE_MODES]
    if bad:
        raise ValueError(f"invalid engine mode(s): {bad}")
    if cfg.lookback_hours < 1 or cfg.lookback_hours > 24 * 30:
        raise ValueError("--lookback-hours must be in [1, 720]")
    if cfg.touch_window_minutes < 1 or cfg.touch_window_minutes > 24 * 60 * 7:
        raise ValueError("--touch-window-minutes must be in [1, 10080]")
    if cfg.placement_window_seconds < 1 or cfg.placement_window_seconds > 600:
        raise ValueError("--placement-window-seconds must be in [1, 600]")
    if cfg.top_limit < 1 or cfg.top_limit > 500:
        raise ValueError("--top-limit must be in [1, 500]")
    if cfg.deep_gap_bps < 0.0 or cfg.deep_gap_bps > 10_000.0:
        raise ValueError("--deep-gap-bps must be in [0, 10000]")


def build_order_touchability_sql() -> str:
    return r"""
WITH params AS (
    SELECT
        %s::text[] AS engine_modes,
        %s::int AS lookback_hours,
        %s::int AS touch_window_minutes,
        %s::int AS placement_window_seconds
),
recent_orders AS (
    SELECT o.*
    FROM trading.orders o, params p
    WHERE o.engine_mode = ANY(p.engine_modes)
      AND o.ts >= now() - (p.lookback_hours * interval '1 hour')
),
state_rollup AS (
    SELECT
        o.order_id,
        max(osc.ts) AS latest_state_ts,
        (array_agg(osc.to_status ORDER BY osc.ts DESC))[1] AS latest_to_status,
        (array_agg(osc.reason ORDER BY osc.ts DESC))[1] AS latest_reason,
        max(osc.ts) FILTER (
            WHERE lower(coalesce(osc.to_status, '')) IN (
                'filled',
                'partiallyfilled',
                'partially_filled',
                'cancelled',
                'canceled',
                'rejected',
                'deactivated'
            )
        ) AS latest_terminal_ts,
        bool_or(lower(coalesce(osc.to_status, '')) IN (
            'filled',
            'partiallyfilled',
            'partially_filled'
        )) AS any_fill_state,
        bool_or(lower(coalesce(osc.to_status, '')) IN (
            'cancelled',
            'canceled',
            'deactivated'
        )) AS any_cancelled_state,
        bool_or(lower(coalesce(osc.to_status, '')) = 'rejected') AS any_rejected_state,
        bool_or(coalesce(osc.reason, '') ILIKE '%%post_only_cross%%'
            OR coalesce(osc.reason, '') ILIKE '%%postonlywilltakeliquidity%%'
            OR coalesce(osc.reason, '') ILIKE '%%post only will take liquidity%%'
            OR coalesce(osc.reason, '') ILIKE '%%ec_postonlywilltakeliquidity%%'
        ) AS any_post_only_cross,
        bool_or(coalesce(osc.reason, '') ILIKE '%%self_cancel%%'
            OR coalesce(osc.reason, '') ILIKE '%%percancelrequest%%'
        ) AS any_self_cancel
    FROM recent_orders o
    LEFT JOIN trading.order_state_changes osc
      ON osc.order_id = o.order_id
     AND osc.engine_mode = o.engine_mode
     AND osc.ts >= o.ts
    GROUP BY o.order_id
),
fill_rollup AS (
    SELECT
        o.order_id,
        count(f.fill_id)::bigint AS fill_count,
        min(f.ts) AS first_fill_ts,
        max(f.ts) AS latest_fill_ts,
        sum(coalesce(f.qty, 0)) AS filled_qty,
        avg(f.price) AS avg_fill_price
    FROM recent_orders o
    LEFT JOIN trading.fills f
      ON f.order_id = o.order_id
     AND f.engine_mode = o.engine_mode
     AND f.ts >= o.ts
    GROUP BY o.order_id
)
SELECT
    o.engine_mode,
    o.order_id,
    o.intent_id,
    o.context_id,
    o.ts AS order_ts,
    o.symbol,
    o.side,
    o.strategy_name,
    o.qty AS order_qty,
    o.price AS order_price,
    o.order_type,
    o.time_in_force,
    o.status AS order_status,
    i.price AS intent_price,
    CASE
        WHEN (i.details->>'limit_price') ~
             '^-?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?$'
        THEN (i.details->>'limit_price')::double precision
        ELSE NULL
    END AS intent_limit_price,
    CASE
        WHEN (i.details->>'maker_timeout_ms') ~
             '^-?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?$'
        THEN (i.details->>'maker_timeout_ms')::double precision
        ELSE NULL
    END AS maker_timeout_ms,
    CASE
        WHEN lower(i.details->>'post_only') IN ('true', 'false')
        THEN (i.details->>'post_only')::boolean
        ELSE NULL
    END AS intent_post_only,
    coalesce(
        o.price::double precision,
        CASE
            WHEN (o.details->>'limit_price') ~
                 '^-?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?$'
            THEN (o.details->>'limit_price')::double precision
            ELSE NULL
        END,
        CASE
            WHEN (i.details->>'limit_price') ~
                 '^-?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?$'
            THEN (i.details->>'limit_price')::double precision
            ELSE NULL
        END,
        i.price::double precision
    ) AS effective_limit_price,
    CASE
        WHEN o.price IS NOT NULL THEN 'orders.price'
        WHEN coalesce(o.details ? 'limit_price', false)
             AND (o.details->>'limit_price') ~
                 '^-?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?$'
        THEN 'orders.details.limit_price'
        WHEN coalesce(i.details ? 'limit_price', false)
             AND (i.details->>'limit_price') ~
                 '^-?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?$'
        THEN 'intents.details.limit_price'
        WHEN i.price IS NOT NULL THEN 'intents.price'
        ELSE NULL
    END AS effective_limit_price_source,
    s.latest_state_ts,
    s.latest_to_status,
    s.latest_reason,
    s.latest_terminal_ts,
    coalesce(s.any_fill_state, false) AS any_fill_state,
    coalesce(s.any_cancelled_state, false) AS any_cancelled_state,
    coalesce(s.any_rejected_state, false) AS any_rejected_state,
    coalesce(s.any_post_only_cross, false) AS any_post_only_cross,
    coalesce(s.any_self_cancel, false) AS any_self_cancel,
    coalesce(fr.fill_count, 0)::bigint AS fill_count,
    fr.first_fill_ts,
    fr.latest_fill_ts,
    fr.filled_qty,
    fr.avg_fill_price,
    placement.ts AS placement_bbo_ts,
    placement.best_bid AS placement_best_bid,
    placement.best_ask AS placement_best_ask,
    future.bbo_count AS future_bbo_count,
    future.first_bbo_ts,
    future.latest_bbo_ts,
    future.min_best_ask,
    future.max_best_bid
FROM recent_orders o
LEFT JOIN trading.intents i
  ON i.intent_id = o.intent_id
 AND i.engine_mode = o.engine_mode
LEFT JOIN state_rollup s
  ON s.order_id = o.order_id
LEFT JOIN fill_rollup fr
  ON fr.order_id = o.order_id
LEFT JOIN LATERAL (
    SELECT b.ts, b.best_bid, b.best_ask
    FROM market.ob_top b, params p
    WHERE b.symbol = o.symbol
      AND b.ts BETWEEN
          o.ts - (p.placement_window_seconds * interval '1 second')
          AND o.ts + (p.placement_window_seconds * interval '1 second')
      AND b.best_bid > 0
      AND b.best_ask > 0
    ORDER BY abs(extract(epoch from (b.ts - o.ts))) ASC
    LIMIT 1
) placement ON true
LEFT JOIN LATERAL (
    SELECT
        count(*)::bigint AS bbo_count,
        min(b.ts) AS first_bbo_ts,
        max(b.ts) AS latest_bbo_ts,
        min(b.best_ask) AS min_best_ask,
        max(b.best_bid) AS max_best_bid
    FROM market.ob_top b, params p
    WHERE b.symbol = o.symbol
      AND b.ts >= o.ts
      AND b.ts <= least(
          coalesce(s.latest_terminal_ts, now()),
          o.ts + (p.touch_window_minutes * interval '1 minute')
      )
      AND b.best_bid > 0
      AND b.best_ask > 0
) future ON true
ORDER BY o.ts DESC, o.order_id DESC
LIMIT %s
"""


def _as_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _as_bool(value: Any) -> bool:
    return bool(value)


def _bps(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return round((numerator / denominator) * 10_000.0, 4)


def classify_order(row: dict[str, Any], *, deep_gap_bps: float) -> dict[str, Any]:
    side = str(row.get("side") or "").lower()
    price = _as_float(row.get("effective_limit_price"))
    fill_count = _as_int(row.get("fill_count"))
    any_fill_state = _as_bool(row.get("any_fill_state"))
    future_bbo_count = _as_int(row.get("future_bbo_count"))
    placement_bid = _as_float(row.get("placement_best_bid"))
    placement_ask = _as_float(row.get("placement_best_ask"))
    future_min_ask = _as_float(row.get("min_best_ask"))
    future_max_bid = _as_float(row.get("max_best_bid"))

    if side == "buy":
        touched = (
            price is not None and future_min_ask is not None and future_min_ask <= price
        )
        placement_gap_bps = _bps(
            None if price is None or placement_ask is None else placement_ask - price,
            placement_ask,
        )
        best_touch_gap_bps = _bps(
            None if price is None or future_min_ask is None else future_min_ask - price,
            future_min_ask,
        )
        touch_reference = "future_min_best_ask"
        placement_reference = "placement_best_ask"
    elif side == "sell":
        touched = (
            price is not None and future_max_bid is not None and future_max_bid >= price
        )
        placement_gap_bps = _bps(
            None if price is None or placement_bid is None else price - placement_bid,
            placement_bid,
        )
        best_touch_gap_bps = _bps(
            None if price is None or future_max_bid is None else price - future_max_bid,
            future_max_bid,
        )
        touch_reference = "future_max_best_bid"
        placement_reference = "placement_best_bid"
    else:
        touched = False
        placement_gap_bps = None
        best_touch_gap_bps = None
        touch_reference = None
        placement_reference = None

    if fill_count > 0 or any_fill_state:
        status = "FILLED"
        reason = "fill row or fill state exists for order"
    elif price is None:
        status = "MISSING_EFFECTIVE_LIMIT_PRICE"
        reason = "order has no usable limit price in orders or joined intent metadata"
    elif future_bbo_count == 0:
        status = "NO_BBO_COVERAGE_FOR_TOUCH_WINDOW"
        reason = "no BBO observations were available during the order touch window"
    elif touched:
        status = "BBO_TOUCHED_NO_FILL_RECONCILE_REQUIRED"
        reason = "BBO crossed the passive limit but no fill was recorded"
    elif _as_bool(row.get("any_post_only_cross")):
        status = "POST_ONLY_REJECT_OR_CROSS_NO_FILL"
        reason = "order state changes mention PostOnly crossing/rejection"
    elif (
        best_touch_gap_bps is not None
        and best_touch_gap_bps >= deep_gap_bps
        and _as_bool(row.get("any_self_cancel"))
    ):
        status = "DAY_TIMEOUT_SELF_CANCEL_NO_TOUCH_DEEP_LIMIT"
        reason = "self-cancelled after resting; passive limit stayed far from touch"
    elif best_touch_gap_bps is not None and best_touch_gap_bps >= deep_gap_bps:
        status = "WORKING_DEEP_PASSIVE_LIMIT_NO_TOUCH"
        reason = "working passive limit is far from observed BBO touchability"
    elif _as_bool(row.get("any_self_cancel")):
        status = "SELF_CANCEL_NO_TOUCH"
        reason = "order self-cancelled before observed BBO touch"
    else:
        status = "PASSIVE_LIMIT_NOT_TOUCHED"
        reason = "passive limit was not touched during the observation window"

    order_price_missing = row.get("order_price") is None
    return {
        "status": status,
        "reason": reason,
        "bbo_touched_limit": touched,
        "placement_gap_bps": placement_gap_bps,
        "best_touch_gap_bps": best_touch_gap_bps,
        "touch_reference": touch_reference,
        "placement_reference": placement_reference,
        "effective_limit_price_missing": price is None,
        "orders_price_missing": order_price_missing,
        "effective_limit_price_inferred": (
            order_price_missing and row.get("effective_limit_price_source") is not None
        ),
        "deep_gap_bps": deep_gap_bps,
    }


def enrich_orders(rows: list[dict[str, Any]], *, deep_gap_bps: float) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in rows:
        cls = classify_order(row, deep_gap_bps=deep_gap_bps)
        enriched.append(
            {
                "engine_mode": row.get("engine_mode"),
                "order_id": row.get("order_id"),
                "intent_id": row.get("intent_id"),
                "context_id": row.get("context_id"),
                "order_ts": row.get("order_ts"),
                "symbol": row.get("symbol"),
                "side": row.get("side"),
                "strategy_name": row.get("strategy_name"),
                "order_qty": row.get("order_qty"),
                "order_price": row.get("order_price"),
                "intent_price": row.get("intent_price"),
                "intent_limit_price": row.get("intent_limit_price"),
                "effective_limit_price": row.get("effective_limit_price"),
                "effective_limit_price_source": row.get("effective_limit_price_source"),
                "order_type": row.get("order_type"),
                "time_in_force": row.get("time_in_force"),
                "order_status": row.get("order_status"),
                "latest_to_status": row.get("latest_to_status"),
                "latest_reason": row.get("latest_reason"),
                "any_self_cancel": row.get("any_self_cancel"),
                "any_post_only_cross": row.get("any_post_only_cross"),
                "maker_timeout_ms": row.get("maker_timeout_ms"),
                "fill_count": row.get("fill_count"),
                "placement_bbo_ts": row.get("placement_bbo_ts"),
                "placement_best_bid": row.get("placement_best_bid"),
                "placement_best_ask": row.get("placement_best_ask"),
                "future_bbo_count": row.get("future_bbo_count"),
                "first_bbo_ts": row.get("first_bbo_ts"),
                "latest_bbo_ts": row.get("latest_bbo_ts"),
                "min_best_ask": row.get("min_best_ask"),
                "max_best_bid": row.get("max_best_bid"),
                "classification": cls,
            }
        )
    return enriched


def summarize_orders(orders: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(orders)
    status_counts: dict[str, int] = {}
    for order in orders:
        status = str((order.get("classification") or {}).get("status") or "UNKNOWN")
        status_counts[status] = status_counts.get(status, 0) + 1

    fill_count = sum(_as_int(order.get("fill_count")) for order in orders)
    bbo_touched_no_fill = status_counts.get("BBO_TOUCHED_NO_FILL_RECONCILE_REQUIRED", 0)
    missing_effective = status_counts.get("MISSING_EFFECTIVE_LIMIT_PRICE", 0)
    no_bbo = status_counts.get("NO_BBO_COVERAGE_FOR_TOUCH_WINDOW", 0)
    deep_no_touch = sum(
        status_counts.get(status, 0)
        for status in (
            "WORKING_DEEP_PASSIVE_LIMIT_NO_TOUCH",
            "DAY_TIMEOUT_SELF_CANCEL_NO_TOUCH_DEEP_LIMIT",
        )
    )
    no_touch = sum(
        status_counts.get(status, 0)
        for status in (
            "WORKING_DEEP_PASSIVE_LIMIT_NO_TOUCH",
            "DAY_TIMEOUT_SELF_CANCEL_NO_TOUCH_DEEP_LIMIT",
            "SELF_CANCEL_NO_TOUCH",
            "PASSIVE_LIMIT_NOT_TOUCHED",
        )
    )
    orders_price_missing = sum(
        1
        for order in orders
        if (order.get("classification") or {}).get("orders_price_missing") is True
    )
    inferred_prices = sum(
        1
        for order in orders
        if (order.get("classification") or {}).get("effective_limit_price_inferred")
        is True
    )
    post_only_orders = sum(
        1
        for order in orders
        if str(order.get("time_in_force") or "").lower().replace("_", "") == "postonly"
    )

    if total == 0:
        status = "NO_DEMO_ORDERS_TO_REVIEW"
        reason = "no demo/live_demo orders were found in the lookback window"
        next_action = "continue_data_flow_monitor_until_order_rows_exist"
    elif fill_count > 0:
        status = "FILL_FLOW_PRESENT"
        reason = "one or more fills exist for reviewed orders"
        next_action = "review_realized_execution_quality_and_markouts"
    elif bbo_touched_no_fill > 0:
        status = "BBO_TOUCHED_NO_FILL_RECONCILE_REQUIRED"
        reason = "at least one order should have been touchable by BBO but has no fill"
        next_action = "reconcile_exchange_ws_order_fill_path_before_probe_or_cost_gate_change"
    elif missing_effective > 0:
        status = "ORDER_PRICE_METADATA_MISSING"
        reason = "one or more orders lack effective limit price metadata"
        next_action = "repair_order_audit_price_projection_before_execution_learning"
    elif no_bbo == total:
        status = "NO_BBO_COVERAGE_FOR_ORDER_WINDOWS"
        reason = "orders exist but BBO coverage is unavailable for touchability review"
        next_action = "repair_or_extend_orderbook_capture_before_execution_judgment"
    elif deep_no_touch == total:
        status = "PASSIVE_LIMITS_TOO_DEEP_NO_TOUCH"
        reason = "all reviewed no-fill orders were deep passive limits not touched by BBO"
        next_action = "use_touchability_gate_or_less_passive_bounded_probe_design_before_waiting_for_fills"
    elif no_touch == total:
        status = "PASSIVE_LIMITS_NOT_TOUCHED"
        reason = "reviewed orders were not touched by BBO during their windows"
        next_action = "adjust_probe_touchability_design_before_cost_gate_changes"
    else:
        status = "ORDER_TO_FILL_GAP_MIXED_OR_UNCLASSIFIED"
        reason = "orders have mixed no-fill classifications"
        next_action = "review_order_rows_before_probe_or_cost_gate_change"

    return {
        "status": status,
        "reason": reason,
        "next_action": next_action,
        "counts": {
            "reviewed_orders": total,
            "fill_rows": fill_count,
            "post_only_orders": post_only_orders,
            "orders_price_missing": orders_price_missing,
            "effective_limit_prices_inferred": inferred_prices,
            "bbo_touched_no_fill_orders": bbo_touched_no_fill,
            "deep_passive_no_touch_orders": deep_no_touch,
            "no_touch_orders": no_touch,
            "no_bbo_coverage_orders": no_bbo,
        },
        "status_counts": status_counts,
        "answers": {
            "orders_present": total > 0,
            "fills_present": fill_count > 0,
            "bbo_touched_without_fill": bbo_touched_no_fill > 0,
            "passive_limits_too_deep": total > 0 and deep_no_touch == total,
            "orders_price_missing": orders_price_missing > 0,
            "effective_prices_inferred_from_intents": inferred_prices > 0,
            "global_cost_gate_lowering_recommended": False,
            "order_authority_granted": False,
            "probe_authority_granted": False,
            "promotion_evidence": False,
        },
    }


def fetch_order_rows(conn: Any, cfg: AuditConfig) -> list[dict[str, Any]]:
    validate_config(cfg)
    params: list[Any] = [
        list(cfg.engine_modes),
        cfg.lookback_hours,
        cfg.touch_window_minutes,
        cfg.placement_window_seconds,
        cfg.top_limit,
    ]
    with conn.cursor() as cur:
        cur.execute(build_order_touchability_sql(), params)
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def build_payload(
    *,
    cfg: AuditConfig,
    rows: list[dict[str, Any]],
    generated: str | None = None,
) -> dict[str, Any]:
    generated = generated or datetime.now(timezone.utc).isoformat(timespec="seconds")
    orders = enrich_orders(rows, deep_gap_bps=cfg.deep_gap_bps)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated,
        "engine_modes": list(cfg.engine_modes),
        "lookback_hours": cfg.lookback_hours,
        "touch_window_minutes": cfg.touch_window_minutes,
        "placement_window_seconds": cfg.placement_window_seconds,
        "deep_gap_bps": cfg.deep_gap_bps,
        "summary": summarize_orders(orders),
        "orders": orders,
        "boundary": BOUNDARY,
    }


def build_timeout_audit_payload(
    *,
    cfg: AuditConfig,
    generated: str | None = None,
) -> dict[str, Any]:
    """Build a non-authoritative artifact for one incomplete read-only query."""

    generated = generated or datetime.now(timezone.utc).isoformat(timespec="seconds")
    observation = {
        "status": "PARTIAL_QUERY_INCOMPLETE",
        "query_complete": False,
        "requested_queries": ["order_touchability"],
        "completed_queries": [],
        "failed_queries": ["order_touchability"],
        "stale_snapshot_reused": False,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated,
        "engine_modes": list(cfg.engine_modes),
        "lookback_hours": cfg.lookback_hours,
        "touch_window_minutes": cfg.touch_window_minutes,
        "placement_window_seconds": cfg.placement_window_seconds,
        "deep_gap_bps": cfg.deep_gap_bps,
        "query_complete": False,
        "stale_snapshot_reused": False,
        "observation": observation,
        "summary": {
            "status": "READONLY_QUERY_TIMEOUT",
            "reason": (
                "the read-only order touchability query reached the PostgreSQL "
                "statement timeout"
            ),
            "next_action": (
                "retry_readonly_order_touchability_audit_on_next_natural_cycle_"
                "without_blocking_independent_candidate_board"
            ),
            "observation_status": "PARTIAL_QUERY_INCOMPLETE",
            "query_complete": False,
            "stale_snapshot_reused": False,
            "counts": {
                "reviewed_orders": None,
                "fill_rows": None,
                "post_only_orders": None,
                "orders_price_missing": None,
                "effective_limit_prices_inferred": None,
                "bbo_touched_no_fill_orders": None,
                "deep_passive_no_touch_orders": None,
                "no_touch_orders": None,
                "no_bbo_coverage_orders": None,
            },
            "status_counts": {},
            "answers": {
                "partial_observation": True,
                "query_complete": False,
                "stale_snapshot_reused": False,
                "orders_present": None,
                "fills_present": None,
                "bbo_touched_without_fill": None,
                "passive_limits_too_deep": None,
                "orders_price_missing": None,
                "effective_prices_inferred_from_intents": None,
                "global_cost_gate_lowering_recommended": False,
                "candidate_selection_authority_granted": False,
                "cost_gate_change_authority_granted": False,
                "risk_change_authority_granted": False,
                "order_authority_granted": False,
                "probe_authority_granted": False,
                "proof_authority_granted": False,
                "serving_authority_granted": False,
                "promotion_authority_granted": False,
                "latest_authority_granted": False,
                "promotion_evidence": False,
            },
        },
        "orders": [],
        "boundary": BOUNDARY,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Demo Order-To-Fill Gap Audit",
        "",
        f"- Generated: `{payload.get('generated_at_utc')}`",
        f"- Engine modes: `{','.join(payload.get('engine_modes') or [])}`",
        f"- Lookback hours: `{payload.get('lookback_hours')}`",
        f"- Touch window minutes: `{payload.get('touch_window_minutes')}`",
        f"- Status: `{summary.get('status')}`",
        f"- Reason: {summary.get('reason')}",
        f"- Next action: `{summary.get('next_action')}`",
        f"- Boundary: {payload.get('boundary')}",
    ]
    observation = payload.get("observation")
    if isinstance(observation, dict):
        lines.extend(
            [
                f"- Query complete: `{observation.get('query_complete')}`",
                f"- Stale snapshot reused: `{observation.get('stale_snapshot_reused')}`",
            ]
        )
    lines.extend(
        [
            "",
            "## Counts",
            "",
            "| metric | value |",
            "|---|---:|",
        ]
    )
    for key, value in (summary.get("counts") or {}).items():
        lines.append(f"| {key} | {value} |")
    lines.extend(
        [
            "",
            "## Orders",
            "",
            "| ts | symbol | side | tif | status | effective_px | px_source | "
            "best_touch_gap_bps | class |",
            "|---|---|---|---|---|---:|---|---:|---|",
        ]
    )
    for order in payload.get("orders") or []:
        cls = order.get("classification") or {}
        lines.append(
            "| "
            f"{order.get('order_ts')} | {order.get('symbol')} | {order.get('side')} | "
            f"{order.get('time_in_force')} | {order.get('latest_to_status') or order.get('order_status')} | "
            f"{order.get('effective_limit_price')} | {order.get('effective_limit_price_source')} | "
            f"{cls.get('best_touch_gap_bps')} | {cls.get('status')} |"
        )
    return "\n".join(lines) + "\n"


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-mode", action="append", dest="engine_modes")
    parser.add_argument("--lookback-hours", type=int, default=48)
    parser.add_argument("--touch-window-minutes", type=int, default=24 * 60)
    parser.add_argument("--placement-window-seconds", type=int, default=30)
    parser.add_argument("--top-limit", type=int, default=50)
    parser.add_argument("--deep-gap-bps", type=float, default=500.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args()


def _write_text_atomic(path: Path, text: str) -> None:
    """Atomically replace ``path`` from a unique temporary beside it."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    )
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    args = parse_args()
    cfg = AuditConfig(
        engine_modes=tuple(args.engine_modes or ["demo", "live_demo"]),
        lookback_hours=args.lookback_hours,
        touch_window_minutes=args.touch_window_minutes,
        placement_window_seconds=args.placement_window_seconds,
        top_limit=args.top_limit,
        deep_gap_bps=args.deep_gap_bps,
    )
    validate_config(cfg)
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn = connect_report_pg(
        "demo_order_to_fill_gap_audit",
        statement_timeout_ms_default=180_000,
    )
    query_timed_out = False
    try:
        conn.rollback()
        conn.set_session(readonly=True, autocommit=True)
        try:
            rows = fetch_order_rows(conn, cfg)
        except Exception as exc:
            if not _is_statement_timeout(exc):
                raise
            rows = []
            query_timed_out = True
    finally:
        conn.close()

    if query_timed_out:
        payload = build_timeout_audit_payload(cfg=cfg, generated=generated)
    else:
        payload = build_payload(cfg=cfg, rows=rows, generated=generated)
    markdown = render_markdown(payload)
    if args.output:
        _write_text_atomic(args.output, markdown)
    else:
        print(markdown, end="")
    if args.json_output:
        _write_text_atomic(
            args.json_output,
            json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
