"""Executor V2 ExecutionReport quality metrics builder.

MAG-063 keeps execution reporting as a typed helper. It turns a leased or
shadow ExecutionPlan plus fill observations into Analyst-consumable quality
metrics without submitting orders.
"""

from __future__ import annotations

import hashlib
from typing import Any

from .agent_contracts import ExecutionPlan, ExecutionReport


def build_execution_report(
    plan: ExecutionPlan,
    *,
    ts_ms: int,
    status: str,
    exchange_order_id: str | None = None,
    fill_id: str | None = None,
    filled_qty: float | None = None,
    avg_fill_price: float | None = None,
    fees_paid: float | None = None,
    fee_bps: float | None = None,
    submit_ts_ms: int | None = None,
    exchange_ack_ts_ms: int | None = None,
    final_fill_ts_ms: int | None = None,
    liquidity_role: str = "unknown",
    metadata: dict[str, Any] | None = None,
) -> ExecutionReport:
    """Build an ExecutionReport with slippage, fee, and latency metrics."""

    requested_qty = plan.qty
    expected_price = plan.limit_price
    slippage_bps = _slippage_bps(expected_price, avg_fill_price)
    submit_latency_ms = _latency_ms(submit_ts_ms, exchange_ack_ts_ms)
    fill_latency_ms = _latency_ms(submit_ts_ms, final_fill_ts_ms)
    quality_metrics = {
        "metric_source": "executor_report_v2",
        "order_style": plan.order_style,
        "maker_preference": plan.maker_preference,
        "reduce_only": plan.reduce_only,
        "lease_bound": bool(plan.lease_id),
        "slippage_bps": slippage_bps,
        "fees_paid": fees_paid,
        "fee_bps": fee_bps,
        "submit_latency_ms": submit_latency_ms,
        "fill_latency_ms": fill_latency_ms,
        "liquidity_role": _liquidity_role(liquidity_role),
    }

    return ExecutionReport(
        execution_report_id=_execution_report_id(plan, ts_ms, status, exchange_order_id, fill_id),
        order_plan_id=plan.order_plan_id,
        decision_id=plan.decision_id,
        ts_ms=ts_ms,
        engine_mode=plan.engine_mode,
        symbol=plan.symbol,
        status=status,
        exchange_order_id=exchange_order_id,
        fill_id=fill_id,
        requested_qty=requested_qty,
        filled_qty=filled_qty,
        expected_price=expected_price,
        avg_fill_price=avg_fill_price,
        slippage_bps=slippage_bps,
        fees_paid=fees_paid,
        fee_bps=fee_bps,
        submit_latency_ms=submit_latency_ms,
        fill_latency_ms=fill_latency_ms,
        liquidity_role=_liquidity_role(liquidity_role),
        quality_metrics=quality_metrics,
        metadata={
            **(metadata or {}),
            "mag": "063",
            "builder": "executor_report_v2",
            "order_style": plan.order_style,
            "idempotency_key": plan.idempotency_key,
        },
    )


def _execution_report_id(
    plan: ExecutionPlan,
    ts_ms: int,
    status: str,
    exchange_order_id: str | None,
    fill_id: str | None,
) -> str:
    digest = _digest(
        [
            plan.engine_mode,
            plan.order_plan_id,
            plan.decision_id,
            str(ts_ms),
            status,
            exchange_order_id or "",
            fill_id or "",
        ]
    )
    return f"exec-report-{plan.engine_mode}-{plan.symbol}-{digest}"


def _slippage_bps(expected_price: float | None, avg_fill_price: float | None) -> float | None:
    if expected_price is None or avg_fill_price is None or expected_price <= 0.0:
        return None
    return round(abs(avg_fill_price - expected_price) / expected_price * 10_000.0, 6)


def _latency_ms(start_ts_ms: int | None, end_ts_ms: int | None) -> float | None:
    if start_ts_ms is None or end_ts_ms is None:
        return None
    return float(max(0, end_ts_ms - start_ts_ms))


def _liquidity_role(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"maker", "taker", "mixed"}:
        return normalized
    return "unknown"


def _digest(parts: list[str]) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8", errors="replace"))
        h.update(b"\0")
    return h.hexdigest()[:16]
