from __future__ import annotations

from app.position_review_v2 import (
    PositionReviewInput,
    build_position_review,
    position_review_to_strategy_candidate,
)
from app.scanner_advisory_contracts import OpportunityDecay
from app.strategist_decision_v2 import StrategyMatchInput, build_strategist_decision


def _decay(**overrides) -> OpportunityDecay:
    payload = {
        "decay_id": "oppdecay:scan-2:BTCUSDT",
        "candidate_id": "oppcand:scan-1:BTCUSDT:grid_trading",
        "scan_id": "scan-2",
        "decay_ts_ms": 1_700_000_000_000,
        "symbol": "BTCUSDT",
        "strategy": "grid_trading",
        "authority_mode": "advisory_enforced",
        "reason": "exited_top_set",
        "previous_score": 72.5,
        "current_score": 31.0,
        "previous_rank": 3,
        "current_rank": None,
        "has_open_position": True,
        "position_review_required": True,
        "auto_close_allowed": False,
        "evidence": {"position_review_input": True},
    }
    payload.update(overrides)
    return OpportunityDecay(**payload)


def _review_input(**overrides) -> PositionReviewInput:
    payload = {
        "review_id": "position-review-paper-BTCUSDT-1",
        "ts_ms": 1_700_000_000_100,
        "engine_mode": "paper",
        "symbol": "BTCUSDT",
        "strategy": "grid_trading",
        "position_id": "position-paper-BTCUSDT-1",
        "position_side": "long",
        "direction": "long",
        "scanner_decay": _decay(),
        "has_open_position": True,
        "remaining_edge_lcb_bps": 8.0,
        "exit_cost_bps": 4.0,
        "current_pnl_bps": 16.0,
        "market_regime_before": "range_bound",
        "market_regime_after": "range_bound",
        "evidence_refs": ["scanner-row-2"],
        "fact_refs": ["fact-open-position-1"],
        "inference_refs": ["inference-edge-lcb-1"],
        "hypothesis_refs": ["hypothesis-regime-1"],
    }
    payload.update(overrides)
    return PositionReviewInput(**payload)


def test_scanner_decay_with_positive_remaining_edge_holds_and_never_auto_closes() -> None:
    review = build_position_review(_review_input())

    assert review.recommendation == "hold"
    assert review.decision_action == "hold"
    assert review.position_directives["stop_adding"] is True
    assert review.position_directives["allow_auto_close"] is False
    assert "scanner_decay_requires_review" in review.reason_codes
    assert "scanner_rank_exited" in review.reason_codes
    assert review.fact_refs == ["fact-open-position-1"]
    assert review.inference_refs == ["inference-edge-lcb-1"]
    assert review.hypothesis_refs == ["hypothesis-regime-1"]


def test_regime_shift_with_weak_edge_tightens_exit_without_close_dispatch() -> None:
    review = build_position_review(
        _review_input(
            scanner_decay=None,
            trigger="regime_shift",
            remaining_edge_lcb_bps=1.5,
            current_pnl_bps=3.0,
            market_regime_before="range_bound",
            market_regime_after="trending",
        )
    )

    assert review.trigger == "regime_shift"
    assert review.recommendation == "tighten_exit"
    assert review.decision_action == "hold"
    assert review.position_directives["tighten_exit"] is True
    assert review.position_directives["requires_guardian"] is False


def test_positive_net_exit_converts_to_close_candidate_for_strategist_decision() -> None:
    review = build_position_review(
        _review_input(
            remaining_edge_lcb_bps=-12.0,
            exit_cost_bps=4.0,
            current_pnl_bps=19.0,
        )
    )

    assert review.recommendation == "close_when_net_positive"
    assert review.decision_action == "close"
    assert review.net_exit_bps == 15.0
    assert review.position_directives["requires_guardian"] is True

    candidate = position_review_to_strategy_candidate(review)
    decision = build_strategist_decision(
        StrategyMatchInput(
            match_id="match-paper-BTCUSDT-review-close",
            signal_id="sig-paper-BTCUSDT-review-close",
            ts_ms=review.ts_ms + 1,
            engine_mode=review.engine_mode,
            symbol=review.symbol,
            direction="close_long",
            candidate_routes=[candidate],
            position_review_id=review.position_review_id,
            evidence_refs=review.evidence_refs,
            fact_refs=review.fact_refs,
            inference_refs=review.inference_refs,
            hypothesis_refs=review.hypothesis_refs,
        )
    )

    assert decision.decision_action == "close"
    assert decision.selected_candidate_id == review.position_review_id
    assert decision.expected_net_edge_bps == -12.0
    assert decision.portfolio_impact["recommendation"] == "close_when_net_positive"


def test_negative_edge_without_positive_exit_reduces_and_ignores_decay_auto_close_flag() -> None:
    review = build_position_review(
        _review_input(
            scanner_decay=_decay(auto_close_allowed=True),
            remaining_edge_lcb_bps=-9.0,
            exit_cost_bps=5.0,
            current_pnl_bps=-12.0,
            adverse_pnl_drift_bps=-8.0,
        )
    )

    assert review.recommendation == "reduce"
    assert review.decision_action == "reduce"
    assert review.urgency == "high"
    assert "scanner_decay_auto_close_ignored" in review.reason_codes
    assert review.position_directives["allow_auto_close"] is False


def test_hard_risk_fact_can_recommend_close_now_with_guardian_lineage_required() -> None:
    review = build_position_review(
        _review_input(
            scanner_decay=None,
            trigger="guardian_risk_pattern",
            risk_requires_exit=True,
            remaining_edge_lcb_bps=5.0,
            current_pnl_bps=-2.0,
            fact_refs=["fact-guardian-risk-1"],
        )
    )

    assert review.recommendation == "close_now_if_risk_requires"
    assert review.decision_action == "close"
    assert review.urgency == "critical"
    assert review.position_directives["requires_guardian"] is True
    assert "risk_requires_exit" in review.reason_codes


def test_no_open_position_is_explicit_no_action() -> None:
    review = build_position_review(
        _review_input(
            scanner_decay=_decay(has_open_position=False, position_review_required=False),
            has_open_position=False,
        )
    )

    assert review.recommendation == "no_action"
    assert review.decision_action == "no_action"
    assert "no_open_position" in review.reason_codes
