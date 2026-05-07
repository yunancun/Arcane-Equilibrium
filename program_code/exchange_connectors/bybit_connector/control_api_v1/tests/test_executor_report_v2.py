from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent_contracts import ExecutionReport, GuardianVerdict, StrategistDecision
from app.executor_plan_v2 import build_execution_plan
from app.executor_report_v2 import build_execution_report


def _decision() -> StrategistDecision:
    return StrategistDecision(
        decision_id="decision-paper-BTCUSDT-report-1",
        signal_id="sig-paper-BTCUSDT-report-1",
        ts_ms=1_700_000_000_010,
        engine_mode="paper",
        symbol="BTCUSDT",
        strategy="grid_trading",
        direction="long",
        confidence=0.82,
        decision_action="open",
        selected_strategy="grid_trading",
        proposed_qty=1.0,
        proposed_price=101.5,
    )


def _verdict() -> GuardianVerdict:
    return GuardianVerdict(
        verdict_id="verdict-paper-BTCUSDT-report-1-v1",
        decision_id="decision-paper-BTCUSDT-report-1",
        verdict_version=1,
        ts_ms=1_700_000_000_020,
        engine_mode="paper",
        symbol="BTCUSDT",
        strategy="grid_trading",
        allow=True,
        risk_level="low",
        reasons=["shadow_lineage_ok"],
    )


def test_build_execution_report_computes_quality_metrics_for_analyst() -> None:
    plan = build_execution_plan(_decision(), _verdict())

    report = build_execution_report(
        plan,
        ts_ms=1_700_000_001_500,
        status="filled",
        exchange_order_id="bybit-order-1",
        fill_id="fill-paper-BTCUSDT-1",
        filled_qty=1.0,
        avg_fill_price=101.65,
        fees_paid=0.031,
        fee_bps=3.1,
        submit_ts_ms=1_700_000_001_000,
        exchange_ack_ts_ms=1_700_000_001_120,
        final_fill_ts_ms=1_700_000_001_480,
        liquidity_role="maker",
    )

    assert report.order_plan_id == plan.order_plan_id
    assert report.decision_id == plan.decision_id
    assert report.requested_qty == 1.0
    assert report.filled_qty == 1.0
    assert report.expected_price == 101.5
    assert report.avg_fill_price == 101.65
    assert report.slippage_bps == pytest.approx(14.778325)
    assert report.fees_paid == 0.031
    assert report.fee_bps == 3.1
    assert report.submit_latency_ms == 120.0
    assert report.fill_latency_ms == 480.0
    assert report.liquidity_role == "maker"
    assert report.quality_metrics["metric_source"] == "executor_report_v2"
    assert report.quality_metrics["order_style"] == "post_only"
    assert report.quality_metrics["lease_bound"] is False


def test_execution_report_contract_rejects_negative_fee_and_latency_metrics() -> None:
    payload = {
        "execution_report_id": "report-negative-fee",
        "order_plan_id": "plan-1",
        "decision_id": "decision-1",
        "ts_ms": 1,
        "engine_mode": "paper",
        "symbol": "BTCUSDT",
        "status": "filled",
        "fees_paid": -0.01,
    }
    with pytest.raises(ValidationError):
        ExecutionReport(**payload)

    payload["fees_paid"] = 0.01
    payload["fill_latency_ms"] = -1.0
    with pytest.raises(ValidationError):
        ExecutionReport(**payload)


def test_execution_report_unknown_liquidity_role_is_normalized() -> None:
    plan = build_execution_plan(_decision(), _verdict())

    report = build_execution_report(
        plan,
        ts_ms=1_700_000_001_500,
        status="shadow_planned",
        liquidity_role="not_sure",
    )

    assert report.liquidity_role == "unknown"
    assert report.slippage_bps is None
    assert report.fill_latency_ms is None
