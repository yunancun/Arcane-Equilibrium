"""Strategist V2 deterministic decision builder.

MAG-041 keeps this as a typed helper. It does not wire StrategistAgent into the
runtime hot path and does not grant execution authority.
"""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .agent_contracts import DecisionAction, StrategistDecision, StrategySignalDirection


CANONICAL_STRATEGY_KEYS = (
    "ma_crossover",
    "grid_trading",
    "bb_reversion",
    "bb_breakout",
    "funding_arb",
)

_STRATEGY_ALIASES = {
    "funding_rate_arb": "funding_arb",
    "bollinger_reversion": "bb_reversion",
    "bollinger_breakout": "bb_breakout",
}


class _StrategistV2Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StrategyCandidate(_StrategistV2Model):
    candidate_id: str
    strategy: str
    action: DecisionAction = "open"
    direction: StrategySignalDirection = "neutral"
    market_fit_score: float = 0.0
    edge_lcb_bps: float | None = None
    cost_bps: float | None = None
    net_edge_lcb_bps: float | None = None
    data_quality_score: float = 0.5
    learning_weight: float = 0.5
    risk_acceptance_prior: float = 0.5
    portfolio_fit_score: float = 0.5
    confidence: float = 0.0
    reject_reasons: list[str] = Field(default_factory=list)
    portfolio_impact: dict[str, Any] = Field(default_factory=dict)


class StrategyMatchInput(_StrategistV2Model):
    match_id: str
    signal_id: str
    ts_ms: int
    engine_mode: str
    symbol: str
    direction: StrategySignalDirection = "neutral"
    candidate_routes: list[StrategyCandidate] = Field(default_factory=list)
    scanner_candidate_id: str | None = None
    position_review_id: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    fact_refs: list[str] = Field(default_factory=list)
    inference_refs: list[str] = Field(default_factory=list)
    hypothesis_refs: list[str] = Field(default_factory=list)
    cognitive_confidence_floor: float = 0.0
    min_data_quality_score: float = 0.2
    default_size: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def normalize_strategy_key(strategy: str) -> str:
    key = strategy.strip().lower()
    key = _STRATEGY_ALIASES.get(key, key)
    if key not in CANONICAL_STRATEGY_KEYS:
        raise ValueError(f"unknown_strategy:{strategy}")
    return key


def build_strategist_decision(match: StrategyMatchInput) -> StrategistDecision:
    """Build a deterministic MAG-041 StrategistDecision from route candidates."""

    candidate_scores: list[dict[str, Any]] = []
    lineage_refs = _lineage_refs(match)
    if not lineage_refs:
        return _no_action(match, "missing_lineage", candidate_scores)
    if not match.candidate_routes:
        return _no_action(match, "no_strategy_candidates", candidate_scores)

    best: tuple[StrategyCandidate, str, float, list[str]] | None = None
    for candidate in match.candidate_routes:
        normalized_strategy: str | None = None
        reject_reasons = list(candidate.reject_reasons)
        try:
            normalized_strategy = normalize_strategy_key(candidate.strategy)
        except ValueError as exc:
            reject_reasons.append(str(exc))

        net_edge_lcb_bps = _net_edge(candidate)
        if candidate.data_quality_score < match.min_data_quality_score:
            reject_reasons.append("data_quality_below_floor")
        if (
            candidate.action == "open"
            and net_edge_lcb_bps is not None
            and net_edge_lcb_bps < 0.0
        ):
            reject_reasons.append("negative_net_lcb_blocks_open")
        if candidate.action in {"reduce", "close"} and match.position_review_id is None:
            reject_reasons.append("position_review_required_for_tactical_exit")

        match_score = _match_score(candidate, net_edge_lcb_bps)
        effective_confidence = max(_clamp01(candidate.confidence), match_score)
        if effective_confidence < _clamp01(match.cognitive_confidence_floor):
            reject_reasons.append("confidence_below_cognitive_floor")

        score_row = {
            "candidate_id": candidate.candidate_id,
            "strategy": candidate.strategy,
            "normalized_strategy": normalized_strategy,
            "action": candidate.action,
            "direction": candidate.direction,
            "match_score": round(match_score, 6),
            "confidence": round(effective_confidence, 6),
            "edge_lcb_bps": candidate.edge_lcb_bps,
            "cost_bps": candidate.cost_bps,
            "net_edge_lcb_bps": net_edge_lcb_bps,
            "reject_reasons": reject_reasons,
        }
        candidate_scores.append(score_row)

        if normalized_strategy is None or reject_reasons:
            continue
        if best is None or match_score > best[2]:
            best = (candidate, normalized_strategy, match_score, reject_reasons)

    if best is None:
        return _no_action(match, "all_candidates_rejected", candidate_scores)

    candidate, strategy, match_score, _ = best
    net_edge_lcb_bps = _net_edge(candidate)
    confidence = max(_clamp01(candidate.confidence), match_score)
    thesis = _thesis(strategy, candidate, net_edge_lcb_bps)
    invalidation = _invalidation(candidate)
    evidence_refs = list(dict.fromkeys([*lineage_refs, *match.evidence_refs]))

    return StrategistDecision(
        decision_id=_decision_id(match.match_id, match.engine_mode, match.symbol),
        signal_id=match.signal_id,
        ts_ms=match.ts_ms,
        engine_mode=match.engine_mode,
        symbol=match.symbol,
        strategy=strategy,
        direction=candidate.direction,
        confidence=confidence,
        decision_action=candidate.action,
        selected_strategy=strategy,  # type: ignore[arg-type]
        selected_candidate_id=candidate.candidate_id,
        candidate_scores=candidate_scores,
        expected_net_edge_bps=net_edge_lcb_bps,
        portfolio_impact=candidate.portfolio_impact,
        thesis=thesis,
        invalidation=invalidation,
        proposed_qty=match.default_size if candidate.action == "open" else None,
        rationale=thesis,
        evidence_refs=evidence_refs,
        fact_refs=match.fact_refs,
        inference_refs=match.inference_refs,
        hypothesis_refs=match.hypothesis_refs,
        metadata={
            **match.metadata,
            "mag": "041",
            "strategy_matching_model": "v1",
            "scanner_candidate_id": match.scanner_candidate_id,
            "position_review_id": match.position_review_id,
        },
    )


def _no_action(
    match: StrategyMatchInput,
    reason: str,
    candidate_scores: list[dict[str, Any]],
) -> StrategistDecision:
    evidence_refs = list(dict.fromkeys(_lineage_refs(match) + match.evidence_refs))
    return StrategistDecision(
        decision_id=_decision_id(match.match_id, match.engine_mode, match.symbol),
        signal_id=match.signal_id,
        ts_ms=match.ts_ms,
        engine_mode=match.engine_mode,
        symbol=match.symbol,
        strategy="no_action",
        direction="neutral",
        confidence=0.0,
        decision_action="no_action",
        selected_strategy=None,
        selected_candidate_id=None,
        candidate_scores=candidate_scores,
        expected_net_edge_bps=None,
        portfolio_impact={},
        thesis=f"No actionable Strategist V2 candidate: {reason}",
        invalidation="Re-evaluate when required evidence and candidates are available.",
        rationale=reason,
        evidence_refs=evidence_refs,
        fact_refs=match.fact_refs,
        inference_refs=match.inference_refs,
        hypothesis_refs=match.hypothesis_refs,
        metadata={
            **match.metadata,
            "mag": "041",
            "strategy_matching_model": "v1",
            "reject_reasons": [reason],
        },
    )


def _lineage_refs(match: StrategyMatchInput) -> list[str]:
    refs = []
    for value in (match.signal_id, match.scanner_candidate_id, match.position_review_id):
        if value:
            refs.append(value)
    return refs


def _decision_id(match_id: str, engine_mode: str, symbol: str) -> str:
    digest = hashlib.sha256(f"{engine_mode}\0{symbol}\0{match_id}".encode()).hexdigest()[:16]
    return f"decision-{engine_mode}-{symbol}-{digest}"


def _net_edge(candidate: StrategyCandidate) -> float | None:
    if candidate.net_edge_lcb_bps is not None:
        return candidate.net_edge_lcb_bps
    if candidate.edge_lcb_bps is None or candidate.cost_bps is None:
        return None
    return candidate.edge_lcb_bps - candidate.cost_bps


def _match_score(candidate: StrategyCandidate, net_edge_lcb_bps: float | None) -> float:
    market_fit = _clamp01(candidate.market_fit_score)
    edge_quality = _edge_quality(candidate.edge_lcb_bps)
    net_margin = _net_margin(net_edge_lcb_bps)
    portfolio_fit = _clamp01(candidate.portfolio_fit_score)
    data_quality = _clamp01(candidate.data_quality_score)
    learning = _clamp01(candidate.learning_weight)
    risk_prior = _clamp01(candidate.risk_acceptance_prior)
    return _clamp01(
        0.25 * market_fit
        + 0.25 * edge_quality
        + 0.15 * net_margin
        + 0.15 * portfolio_fit
        + 0.10 * data_quality
        + 0.05 * learning
        + 0.05 * risk_prior
    )


def _edge_quality(edge_lcb_bps: float | None) -> float:
    if edge_lcb_bps is None:
        return 0.35
    return _clamp01((edge_lcb_bps + 20.0) / 80.0)


def _net_margin(net_edge_lcb_bps: float | None) -> float:
    if net_edge_lcb_bps is None:
        return 0.30
    return _clamp01((net_edge_lcb_bps + 10.0) / 50.0)


def _thesis(strategy: str, candidate: StrategyCandidate, net_edge_lcb_bps: float | None) -> str:
    edge_text = "unknown" if net_edge_lcb_bps is None else f"{net_edge_lcb_bps:.2f}bps"
    return (
        f"{candidate.action} {strategy} on {candidate.direction}: "
        f"market_fit={candidate.market_fit_score:.2f}, net_lcb={edge_text}"
    )


def _invalidation(candidate: StrategyCandidate) -> str:
    if candidate.action == "open":
        return "Invalidate if net edge LCB turns negative or Guardian modifies/rejects the plan."
    if candidate.action in {"reduce", "close"}:
        return "Invalidate if position review evidence is stale or Guardian rejects the exit."
    return "Invalidate if fresher evidence changes candidate ranking."


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
