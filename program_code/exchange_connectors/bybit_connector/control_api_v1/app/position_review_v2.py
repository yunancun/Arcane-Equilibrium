"""Strategist V2 PositionReview builder.

MAG-042 keeps PositionReview as a typed deterministic helper. It turns scanner
decay and regime-shift evidence into a review recommendation; it does not
dispatch orders or wire Strategist into the runtime hot path.
"""

from __future__ import annotations

import hashlib
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .agent_contracts import (
    DecisionAction,
    PositionReview,
    PositionReviewRecommendation,
    PositionReviewTrigger,
    PositionReviewUrgency,
    StrategySignalDirection,
)
from .scanner_advisory_contracts import OpportunityDecay
from .strategist_decision_v2 import StrategyCandidate


class _PositionReviewV2Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


PositionSide = Literal["long", "short", "flat", "unknown"]


class PositionReviewInput(_PositionReviewV2Model):
    review_id: str | None = None
    ts_ms: int
    engine_mode: str
    symbol: str
    strategy: str | None = None
    position_id: str | None = None
    position_side: PositionSide = "unknown"
    direction: StrategySignalDirection = "neutral"
    scanner_decay: OpportunityDecay | None = None
    trigger: PositionReviewTrigger | None = None
    has_open_position: bool = True
    remaining_edge_lcb_bps: float | None = None
    exit_cost_bps: float | None = None
    current_pnl_bps: float | None = None
    adverse_pnl_drift_bps: float | None = None
    cost_edge_ratio: float | None = None
    market_regime_before: str | None = None
    market_regime_after: str | None = None
    regime_shift_detected: bool = False
    time_stop_fraction: float | None = None
    risk_requires_exit: bool = False
    evidence_refs: list[str] = Field(default_factory=list)
    fact_refs: list[str] = Field(default_factory=list)
    inference_refs: list[str] = Field(default_factory=list)
    hypothesis_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def build_position_review(review_input: PositionReviewInput) -> PositionReview:
    """Build a deterministic PositionReview recommendation from typed evidence."""

    trigger = _trigger(review_input)
    scanner_decay = review_input.scanner_decay
    reason_codes = _base_reason_codes(review_input, trigger)
    evidence_refs = _evidence_refs(review_input)
    net_exit_bps = _net_exit_bps(review_input)

    if not _has_open_position(review_input):
        reason_codes.append("no_open_position")
        return _review(
            review_input,
            trigger,
            "no_action",
            "no_action",
            "low",
            0.0,
            net_exit_bps,
            reason_codes,
            evidence_refs,
            "No PositionReview action: no open position is present.",
            "Re-evaluate only if a live position is observed.",
        )

    if scanner_decay is not None and not scanner_decay.position_review_required:
        reason_codes.append("scanner_decay_not_review_required")
        return _review(
            review_input,
            trigger,
            "no_action",
            "no_action",
            "low",
            0.0,
            net_exit_bps,
            reason_codes,
            evidence_refs,
            "No PositionReview action: scanner decay did not require review.",
            "Re-evaluate if a decay event marks position_review_required.",
        )

    if review_input.risk_requires_exit:
        reason_codes.append("risk_requires_exit")
        return _review(
            review_input,
            trigger,
            "close_now_if_risk_requires",
            "close",
            "critical",
            0.95,
            net_exit_bps,
            reason_codes,
            evidence_refs,
            "Close review requires Guardian-confirmed risk handling.",
            "Invalidate if Guardian classifies the risk fact as non-blocking.",
        )

    remaining_edge = review_input.remaining_edge_lcb_bps
    if remaining_edge is not None and remaining_edge < 0.0:
        reason_codes.append("remaining_edge_negative")
        if net_exit_bps is not None and net_exit_bps > 0.0:
            reason_codes.append("net_exit_positive_after_cost")
            return _review(
                review_input,
                trigger,
                "close_when_net_positive",
                "close",
                "high",
                _confidence(0.82, review_input),
                net_exit_bps,
                reason_codes,
                evidence_refs,
                "Close review is favorable because remaining edge is negative and net exit is positive.",
                "Invalidate if net exit turns non-positive or newer edge evidence recovers.",
            )
        return _review(
            review_input,
            trigger,
            "reduce",
            "reduce",
            "high" if _adverse_drift(review_input) else "medium",
            _confidence(0.74, review_input),
            net_exit_bps,
            reason_codes,
            evidence_refs,
            "Reduce review is favored because remaining edge is negative but immediate close lacks positive net exit.",
            "Invalidate if net exit turns positive or risk facts require a protective close.",
        )

    if _regime_shift(review_input):
        reason_codes.append("regime_shift_detected")
        if remaining_edge is None or remaining_edge <= 2.0:
            return _review(
                review_input,
                trigger,
                "tighten_exit",
                "hold",
                "medium",
                _confidence(0.68, review_input),
                net_exit_bps,
                reason_codes,
                evidence_refs,
                "Tighten exit because the regime changed and remaining edge is weak or unproven.",
                "Invalidate if regime stabilizes and edge evidence becomes positive.",
            )

    if _cost_edge_deteriorated(review_input):
        reason_codes.append("cost_edge_ratio_deteriorated")
        return _review(
            review_input,
            trigger,
            "tighten_exit",
            "hold",
            "medium",
            _confidence(0.66, review_input),
            net_exit_bps,
            reason_codes,
            evidence_refs,
            "Tighten exit because cost consumes too much of the remaining edge.",
            "Invalidate if cost-edge ratio recovers below the deterioration threshold.",
        )

    if _time_stop_nearing(review_input):
        reason_codes.append("time_stop_nearing")
        return _review(
            review_input,
            trigger,
            "stop_adding",
            "hold",
            "medium",
            _confidence(0.62, review_input),
            net_exit_bps,
            reason_codes,
            evidence_refs,
            "Stop adding while time-stop pressure is high.",
            "Invalidate if the position refreshes its thesis before the time stop.",
        )

    if scanner_decay is not None:
        reason_codes.append("scanner_decay_edge_still_non_negative")
        return _review(
            review_input,
            trigger,
            "hold",
            "hold",
            "low",
            _confidence(0.58, review_input),
            net_exit_bps,
            reason_codes,
            evidence_refs,
            "Hold review: scanner decay is advisory and remaining edge is not negative.",
            "Invalidate if remaining edge turns negative, regime shifts, or Guardian reports a risk fact.",
        )

    return _review(
        review_input,
        trigger,
        "hold",
        "hold",
        "low",
        _confidence(0.52, review_input),
        net_exit_bps,
        reason_codes,
        evidence_refs,
        "Hold review: no tactical exit condition is active.",
        "Invalidate if scanner decay, regime shift, or cost deterioration appears.",
    )


def position_review_to_strategy_candidate(review: PositionReview) -> StrategyCandidate:
    """Convert a PositionReview into a StrategistDecision candidate route."""

    action = _candidate_action(review.recommendation)
    reject_reasons: list[str] = []
    strategy = review.strategy or "position_review_missing_strategy"
    if review.strategy is None:
        reject_reasons.append("position_review_missing_strategy")
    if review.recommendation == "no_action":
        reject_reasons.append("position_review_no_action")

    return StrategyCandidate(
        candidate_id=review.position_review_id,
        strategy=strategy,
        action=action,
        direction=review.direction,
        market_fit_score=_review_market_fit(review),
        edge_lcb_bps=review.remaining_edge_lcb_bps,
        cost_bps=review.exit_cost_bps,
        net_edge_lcb_bps=review.remaining_edge_lcb_bps,
        data_quality_score=0.80 if review.evidence_refs else 0.45,
        learning_weight=0.50,
        risk_acceptance_prior=0.55 if action in {"reduce", "close"} else 0.50,
        portfolio_fit_score=0.80 if action in {"reduce", "close"} else 0.55,
        confidence=review.confidence,
        reject_reasons=reject_reasons,
        portfolio_impact={
            "position_review_id": review.position_review_id,
            "recommendation": review.recommendation,
            "directives": review.position_directives,
            "net_exit_bps": review.net_exit_bps,
        },
    )


def _trigger(review_input: PositionReviewInput) -> PositionReviewTrigger:
    if review_input.trigger is not None:
        return review_input.trigger
    if review_input.scanner_decay is not None:
        return "scanner_decay"
    if _regime_shift(review_input):
        return "regime_shift"
    if _adverse_drift(review_input):
        return "adverse_pnl_drift"
    if _cost_edge_deteriorated(review_input):
        return "cost_edge_ratio_deterioration"
    if _time_stop_nearing(review_input):
        return "time_stop_nearing"
    return "scanner_decay"


def _base_reason_codes(
    review_input: PositionReviewInput,
    trigger: PositionReviewTrigger,
) -> list[str]:
    reason_codes = [f"trigger:{trigger}"]
    decay = review_input.scanner_decay
    if decay is not None:
        reason_codes.append(f"scanner_decay_reason:{decay.reason}")
        if decay.auto_close_allowed:
            reason_codes.append("scanner_decay_auto_close_ignored")
        if decay.position_review_required:
            reason_codes.append("scanner_decay_requires_review")
        if decay.previous_score is not None and decay.current_score is not None:
            if decay.current_score < decay.previous_score:
                reason_codes.append("scanner_score_deteriorated")
        if decay.current_rank is None and decay.previous_rank is not None:
            reason_codes.append("scanner_rank_exited")
    if _adverse_drift(review_input):
        reason_codes.append("adverse_pnl_drift")
    return list(dict.fromkeys(reason_codes))


def _review(
    review_input: PositionReviewInput,
    trigger: PositionReviewTrigger,
    recommendation: PositionReviewRecommendation,
    decision_action: DecisionAction,
    urgency: PositionReviewUrgency,
    confidence: float,
    net_exit_bps: float | None,
    reason_codes: list[str],
    evidence_refs: list[str],
    thesis: str,
    invalidation: str,
) -> PositionReview:
    directives = _position_directives(recommendation, decision_action)
    return PositionReview(
        position_review_id=_review_id(review_input),
        ts_ms=review_input.ts_ms,
        engine_mode=review_input.engine_mode,
        symbol=review_input.symbol,
        strategy=review_input.strategy or _decay_strategy(review_input),
        position_id=review_input.position_id,
        scanner_decay_id=_scanner_decay_id(review_input),
        trigger=trigger,
        recommendation=recommendation,
        decision_action=decision_action,
        direction=_review_direction(review_input, decision_action),
        urgency=urgency,
        confidence=_clamp01(confidence),
        remaining_edge_lcb_bps=review_input.remaining_edge_lcb_bps,
        exit_cost_bps=review_input.exit_cost_bps,
        current_pnl_bps=review_input.current_pnl_bps,
        net_exit_bps=net_exit_bps,
        market_regime_before=review_input.market_regime_before,
        market_regime_after=review_input.market_regime_after,
        reason_codes=list(dict.fromkeys(reason_codes)),
        position_directives=directives,
        thesis=thesis,
        invalidation=invalidation,
        evidence_refs=evidence_refs,
        fact_refs=review_input.fact_refs,
        inference_refs=review_input.inference_refs,
        hypothesis_refs=review_input.hypothesis_refs,
        metadata={
            **review_input.metadata,
            "mag": "042",
            "position_review_model": "v1",
            "scanner_decay_auto_close_allowed": (
                review_input.scanner_decay.auto_close_allowed
                if review_input.scanner_decay is not None
                else None
            ),
        },
    )


def _position_directives(
    recommendation: PositionReviewRecommendation,
    decision_action: DecisionAction,
) -> dict[str, Any]:
    tighten = recommendation in {
        "tighten_exit",
        "reduce",
        "close_when_net_positive",
        "close_now_if_risk_requires",
    }
    return {
        "stop_adding": recommendation
        in {
            "hold",
            "stop_adding",
            "tighten_exit",
            "reduce",
            "close_when_net_positive",
            "close_now_if_risk_requires",
        },
        "tighten_exit": tighten,
        "allow_auto_close": False,
        "requires_guardian": decision_action in {"reduce", "close"},
    }


def _candidate_action(recommendation: PositionReviewRecommendation) -> DecisionAction:
    if recommendation == "reduce":
        return "reduce"
    if recommendation in {"close_when_net_positive", "close_now_if_risk_requires"}:
        return "close"
    if recommendation == "no_action":
        return "no_action"
    return "hold"


def _review_market_fit(review: PositionReview) -> float:
    if review.recommendation in {"close_when_net_positive", "close_now_if_risk_requires"}:
        return 0.90
    if review.recommendation == "reduce":
        return 0.82
    if review.recommendation == "tighten_exit":
        return 0.70
    if review.recommendation == "stop_adding":
        return 0.62
    return 0.55


def _review_direction(
    review_input: PositionReviewInput,
    decision_action: DecisionAction,
) -> StrategySignalDirection:
    if decision_action in {"reduce", "close"}:
        if review_input.position_side == "long":
            return "close_long"
        if review_input.position_side == "short":
            return "close_short"
    return review_input.direction


def _confidence(base: float, review_input: PositionReviewInput) -> float:
    confidence = base
    if review_input.scanner_decay is not None:
        confidence += 0.04
    if _regime_shift(review_input):
        confidence += 0.04
    if review_input.fact_refs:
        confidence += 0.03
    if review_input.inference_refs:
        confidence += 0.02
    return _clamp01(confidence)


def _evidence_refs(review_input: PositionReviewInput) -> list[str]:
    refs = list(review_input.evidence_refs)
    decay_id = _scanner_decay_id(review_input)
    if decay_id:
        refs.insert(0, decay_id)
    if review_input.position_id:
        refs.insert(0, review_input.position_id)
    return list(dict.fromkeys(refs))


def _net_exit_bps(review_input: PositionReviewInput) -> float | None:
    if review_input.current_pnl_bps is None or review_input.exit_cost_bps is None:
        return None
    return review_input.current_pnl_bps - review_input.exit_cost_bps


def _has_open_position(review_input: PositionReviewInput) -> bool:
    if not review_input.has_open_position:
        return False
    if review_input.scanner_decay is not None:
        return review_input.scanner_decay.has_open_position
    return True


def _regime_shift(review_input: PositionReviewInput) -> bool:
    if review_input.regime_shift_detected:
        return True
    before = review_input.market_regime_before
    after = review_input.market_regime_after
    return bool(before and after and before != after)


def _adverse_drift(review_input: PositionReviewInput) -> bool:
    return (
        review_input.adverse_pnl_drift_bps is not None
        and review_input.adverse_pnl_drift_bps <= -5.0
    )


def _cost_edge_deteriorated(review_input: PositionReviewInput) -> bool:
    if review_input.cost_edge_ratio is not None and review_input.cost_edge_ratio >= 0.80:
        return True
    edge = review_input.remaining_edge_lcb_bps
    cost = review_input.exit_cost_bps
    return edge is not None and cost is not None and edge > 0.0 and cost / max(edge, 1e-9) >= 0.80


def _time_stop_nearing(review_input: PositionReviewInput) -> bool:
    return review_input.time_stop_fraction is not None and review_input.time_stop_fraction >= 0.80


def _decay_strategy(review_input: PositionReviewInput) -> str | None:
    if review_input.scanner_decay is None:
        return None
    return review_input.scanner_decay.strategy


def _scanner_decay_id(review_input: PositionReviewInput) -> str | None:
    if review_input.scanner_decay is None:
        return None
    return review_input.scanner_decay.decay_id


def _review_id(review_input: PositionReviewInput) -> str:
    if review_input.review_id:
        return review_input.review_id
    stable_source = _scanner_decay_id(review_input) or review_input.position_id or str(review_input.ts_ms)
    digest = hashlib.sha256(
        f"{review_input.engine_mode}\0{review_input.symbol}\0{stable_source}".encode()
    ).hexdigest()[:16]
    return f"position-review-{review_input.engine_mode}-{review_input.symbol}-{digest}"


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
