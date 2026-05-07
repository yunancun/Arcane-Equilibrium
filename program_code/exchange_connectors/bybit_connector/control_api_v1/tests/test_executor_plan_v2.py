from __future__ import annotations

import pytest

from app.agent_contracts import (
    GuardianP2Modification,
    GuardianVerdict,
    StrategistDecision,
)
from app.executor_plan_v2 import build_execution_plan


def _decision(**overrides) -> StrategistDecision:
    payload = {
        "decision_id": "decision-paper-BTCUSDT-1",
        "signal_id": "sig-paper-BTCUSDT-1",
        "ts_ms": 1_700_000_000_010,
        "engine_mode": "paper",
        "symbol": "BTCUSDT",
        "strategy": "grid_trading",
        "direction": "long",
        "confidence": 0.82,
        "decision_action": "open",
        "selected_strategy": "grid_trading",
        "selected_candidate_id": "route-grid-1",
        "expected_net_edge_bps": 18.0,
        "proposed_qty": 1.0,
        "proposed_price": 101.5,
        "rationale": "open with maker entry",
        "evidence_refs": ["scanner-candidate-1"],
        "metadata": {},
    }
    payload.update(overrides)
    return StrategistDecision(**payload)


def _verdict(**overrides) -> GuardianVerdict:
    payload = {
        "verdict_id": "verdict-paper-BTCUSDT-1-v1",
        "decision_id": "decision-paper-BTCUSDT-1",
        "verdict_version": 1,
        "ts_ms": 1_700_000_000_020,
        "engine_mode": "paper",
        "symbol": "BTCUSDT",
        "strategy": "grid_trading",
        "allow": True,
        "risk_level": "low",
        "reasons": ["shadow_lineage_ok"],
    }
    payload.update(overrides)
    return GuardianVerdict(**payload)


def test_approved_open_with_price_becomes_post_only_plan() -> None:
    decision = _decision(metadata={"max_slippage_bps": 8.0, "urgency": "normal"})
    verdict = _verdict(verdict_version=2)

    plan = build_execution_plan(decision, verdict)

    assert plan.decision_id == decision.decision_id
    assert plan.verdict_id == verdict.verdict_id
    assert plan.verdict_version == 2
    assert plan.symbol == decision.symbol
    assert plan.direction == decision.direction
    assert plan.symbol_source == "strategist_decision"
    assert plan.direction_source == "strategist_decision"
    assert plan.qty == 1.0
    assert plan.reduce_only is False
    assert plan.order_style == "post_only"
    assert plan.order_type == "limit"
    assert plan.limit_price == 101.5
    assert plan.time_in_force == "PostOnly"
    assert plan.maker_preference == "maker_only"
    assert plan.urgency == "normal"
    assert plan.max_slippage_bps == 8.0
    assert plan.lease_scope == "TRADE_ENTRY"
    assert plan.lease_ttl_ms == 30_000
    assert plan.idempotency_key == f"execution_plan:paper:{plan.order_plan_id}"
    assert plan.metadata["builder"] == "executor_plan_v2"
    assert plan.metadata["guardian_reasons"] == ["shadow_lineage_ok"]


def test_guardian_p2_modifications_tighten_qty_stop_cooldown_without_scope_change() -> None:
    verdict = _verdict(
        risk_level="medium",
        reasons=["strategy_soft_risk"],
        p2_modifications=[
            GuardianP2Modification(
                field="size",
                action="reduce",
                original_value=1.0,
                modified_value=0.4,
                unit="base_qty",
                reason_code="strategy_soft_risk",
                reason="soft drawdown size cap",
            ),
            GuardianP2Modification(
                field="stop",
                action="tighten",
                original_value=120.0,
                modified_value=75.0,
                unit="bps",
                reason_code="strategy_soft_risk",
                reason="soft drawdown stop tighten",
                evidence_refs=["execution_report-soft-risk"],
            ),
            GuardianP2Modification(
                field="cooldown",
                action="extend",
                original_value=None,
                modified_value=1_800_000,
                unit="ms",
                reason_code="strategy_soft_risk",
                reason="soft drawdown cooldown",
                metadata={"cooldown_until_ms": 1_700_001_800_000},
            ),
        ],
    )

    plan = build_execution_plan(_decision(), verdict)

    assert plan.qty == 0.4
    assert plan.symbol == "BTCUSDT"
    assert plan.direction == "long"
    assert plan.local_stop_policy == {
        "source": "guardian_p2",
        "action": "tighten",
        "value": 75.0,
        "unit": "bps",
        "reason_code": "strategy_soft_risk",
        "reason": "soft drawdown stop tighten",
        "evidence_refs": ["execution_report-soft-risk"],
    }
    assert plan.order_style_params["cooldown_policy"]["value"] == 1_800_000
    assert plan.order_style_params["cooldown_policy"]["cooldown_until_ms"] == 1_700_001_800_000
    assert plan.metadata["guardian_risk_level"] == "medium"
    assert plan.metadata["applied_p2_modifications"][0]["applied_qty"] == 0.4


def test_rejected_guardian_verdict_fails_closed() -> None:
    with pytest.raises(ValueError, match="guardian_verdict_rejects_execution_plan"):
        build_execution_plan(_decision(), _verdict(allow=False, risk_level="high"))


def test_scope_mismatch_between_decision_and_verdict_fails_closed() -> None:
    with pytest.raises(ValueError, match="guardian_verdict_symbol_mismatch"):
        build_execution_plan(_decision(), _verdict(symbol="ETHUSDT"))


def test_hold_and_no_action_decisions_do_not_generate_execution_plans() -> None:
    with pytest.raises(ValueError, match="execution_plan_for_non_trading_decision"):
        build_execution_plan(
            _decision(decision_action="hold", direction="neutral", proposed_price=None),
            _verdict(),
        )

    with pytest.raises(ValueError, match="execution_plan_for_non_trading_decision"):
        build_execution_plan(
            _decision(decision_action="no_action", direction="neutral", proposed_price=None),
            _verdict(),
        )


def test_close_decision_uses_strategist_close_direction_reduce_only_market_exit() -> None:
    decision = _decision(
        decision_action="close",
        direction="close_long",
        proposed_qty=0.5,
        proposed_price=None,
        metadata={"urgency": "normal", "max_slippage_bps": 5.0},
    )

    plan = build_execution_plan(decision, _verdict())

    assert plan.direction == "close_long"
    assert plan.reduce_only is True
    assert plan.order_style == "market"
    assert plan.order_type == "market"
    assert plan.limit_price is None
    assert plan.time_in_force is None
    assert plan.maker_preference == "none"
    assert plan.urgency == "high"
    assert plan.max_slippage_bps == 25.0
    assert plan.lease_scope == "TRADE_EXIT"


def test_executor_refuses_to_infer_close_direction_from_long_or_short() -> None:
    with pytest.raises(ValueError, match="exit_decision_requires_close_direction_from_strategist"):
        build_execution_plan(
            _decision(decision_action="close", direction="long", proposed_price=None),
            _verdict(),
        )


def test_missing_or_nonpositive_qty_is_rejected() -> None:
    with pytest.raises(ValueError, match="strategist_proposed_qty_required"):
        build_execution_plan(_decision(proposed_qty=None), _verdict())

    with pytest.raises(ValueError, match="strategist_proposed_qty_required"):
        build_execution_plan(_decision(proposed_qty=0.0), _verdict())


def test_market_entry_without_price_keeps_slippage_and_taker_preference_bounded() -> None:
    plan = build_execution_plan(_decision(proposed_price=None), _verdict())

    assert plan.order_style == "market"
    assert plan.order_type == "market"
    assert plan.limit_price is None
    assert plan.time_in_force is None
    assert plan.maker_preference == "allow_taker"
    assert plan.max_slippage_bps == 10.0
