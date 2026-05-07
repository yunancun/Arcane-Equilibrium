"""Strategist V2 deterministic decision builder.

MAG-041 keeps this as a typed helper. It does not wire StrategistAgent into the
runtime hot path and does not grant execution authority.
"""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .agent_contracts import (
    AnalystInsight,
    DecisionAction,
    StrategistDecision,
    StrategySignalDirection,
)


CANONICAL_STRATEGY_KEYS = (
    "ma_crossover",
    "grid_trading",
    "bb_reversion",
    "bb_breakout",
    "funding_arb",
)

_STRATEGY_ALIASES = {
    "grid": "grid_trading",
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
    scanner_rank: int | None = Field(default=None, ge=1)
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


class GuardianFeedbackStats(_StrategistV2Model):
    strategy: str | None = None
    symbol: str | None = None
    engine_mode: str | None = None
    window: str = "recent"
    approved: int = Field(default=0, ge=0)
    modified: int = Field(default=0, ge=0)
    rejected: int = Field(default=0, ge=0)
    total: int | None = Field(default=None, ge=0)
    reject_rate: float | None = None
    modify_rate: float | None = None
    top_reasons: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class TruthRegistryClaim(_StrategistV2Model):
    claim_id: str
    strategy: str | None = None
    symbol: str | None = None
    regime: str | None = None
    pattern_text: str
    polarity: str | None = None
    confidence: float = 0.5
    observation_count: int = Field(default=0, ge=0)
    reason: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)


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
    guardian_feedback: list[GuardianFeedbackStats] = Field(default_factory=list)
    guardian_feedback_min_total: int = 3
    analyst_insights: list[AnalystInsight] = Field(default_factory=list)
    truth_registry_claims: list[TruthRegistryClaim] = Field(default_factory=list)
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

    best: tuple[StrategyCandidate, str, float, list[str], dict[str, Any], dict[str, Any]] | None = None
    for candidate in match.candidate_routes:
        normalized_strategy: str | None = None
        reject_reasons = list(candidate.reject_reasons)
        try:
            normalized_strategy = normalize_strategy_key(candidate.strategy)
        except ValueError as exc:
            reject_reasons.append(str(exc))

        net_edge_lcb_bps = _net_edge(candidate)
        guardian_feedback = _guardian_feedback(
            match=match,
            candidate=candidate,
            normalized_strategy=normalized_strategy,
        )
        learning_feedback = _learning_feedback(
            match=match,
            candidate=candidate,
            normalized_strategy=normalized_strategy,
        )
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

        match_score = _match_score(
            candidate,
            net_edge_lcb_bps,
            guardian_feedback["risk_acceptance_prior"],
            learning_feedback["learning_weight"],
        )
        effective_confidence = max(_clamp01(candidate.confidence), match_score)
        confidence_floor = guardian_feedback["confidence_floor"]
        if effective_confidence < confidence_floor:
            reject_reasons.append("confidence_below_cognitive_floor")
        if guardian_feedback["high_reject_rate"] and effective_confidence < confidence_floor:
            reject_reasons.append("guardian_reject_rate_confidence_floor")

        score_row = {
            "candidate_id": candidate.candidate_id,
            "strategy": candidate.strategy,
            "normalized_strategy": normalized_strategy,
            "action": candidate.action,
            "direction": candidate.direction,
            "scanner_rank": candidate.scanner_rank,
            "match_score": round(match_score, 6),
            "confidence": round(effective_confidence, 6),
            "edge_lcb_bps": candidate.edge_lcb_bps,
            "cost_bps": candidate.cost_bps,
            "net_edge_lcb_bps": net_edge_lcb_bps,
            "guardian_feedback": {
                "reject_rate": guardian_feedback["reject_rate"],
                "modify_rate": guardian_feedback["modify_rate"],
                "total": guardian_feedback["total"],
                "confidence_floor": guardian_feedback["confidence_floor"],
                "aggressiveness_multiplier": guardian_feedback["aggressiveness_multiplier"],
                "risk_acceptance_prior": guardian_feedback["risk_acceptance_prior"],
                "top_reasons": guardian_feedback["top_reasons"],
            },
            "learning_feedback": {
                "learning_weight": learning_feedback["learning_weight"],
                "learning_delta": learning_feedback["learning_delta"],
                "reason_codes": learning_feedback["reason_codes"],
                "evidence_refs": learning_feedback["evidence_refs"],
                "typed_rules": learning_feedback["typed_rules"],
            },
            "reject_reasons": reject_reasons,
        }
        candidate_scores.append(score_row)

        if normalized_strategy is None or reject_reasons:
            continue
        if best is None or match_score > best[2]:
            best = (
                candidate,
                normalized_strategy,
                match_score,
                reject_reasons,
                guardian_feedback,
                learning_feedback,
            )

    if best is None:
        return _no_action(match, "all_candidates_rejected", candidate_scores)

    candidate, strategy, match_score, _, guardian_feedback, learning_feedback = best
    net_edge_lcb_bps = _net_edge(candidate)
    confidence = max(_clamp01(candidate.confidence), match_score)
    thesis = _thesis(strategy, candidate, net_edge_lcb_bps)
    invalidation = _invalidation(candidate)
    evidence_refs = list(
        dict.fromkeys(
            [
                *lineage_refs,
                *match.evidence_refs,
                *guardian_feedback["evidence_refs"],
                *learning_feedback["evidence_refs"],
            ]
        )
    )
    fact_refs = list(dict.fromkeys([*match.fact_refs, *learning_feedback["fact_refs"]]))
    inference_refs = list(
        dict.fromkeys([*match.inference_refs, *learning_feedback["inference_refs"]])
    )
    hypothesis_refs = list(
        dict.fromkeys([*match.hypothesis_refs, *learning_feedback["hypothesis_refs"]])
    )
    proposed_qty = None
    if candidate.action == "open" and match.default_size is not None:
        proposed_qty = match.default_size * guardian_feedback["aggressiveness_multiplier"]
    portfolio_impact = {
        **candidate.portfolio_impact,
        "guardian_feedback": {
            "reject_rate": guardian_feedback["reject_rate"],
            "modify_rate": guardian_feedback["modify_rate"],
            "aggressiveness_multiplier": guardian_feedback["aggressiveness_multiplier"],
            "confidence_floor": guardian_feedback["confidence_floor"],
        },
        "learning_feedback": {
            "learning_weight": learning_feedback["learning_weight"],
            "learning_delta": learning_feedback["learning_delta"],
            "reason_codes": learning_feedback["reason_codes"],
            "typed_rules": learning_feedback["typed_rules"],
        },
    }

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
        portfolio_impact=portfolio_impact,
        thesis=thesis,
        invalidation=invalidation,
        proposed_qty=proposed_qty,
        rationale=thesis,
        evidence_refs=evidence_refs,
        fact_refs=fact_refs,
        inference_refs=inference_refs,
        hypothesis_refs=hypothesis_refs,
        metadata={
            **match.metadata,
            "mag": "044",
            "strategy_matching_model": "v3",
            "guardian_feedback_model": "v1",
            "learning_feedback_model": "v1",
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
            "mag": "044",
            "strategy_matching_model": "v3",
            "guardian_feedback_model": "v1",
            "learning_feedback_model": "v1",
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


def _match_score(
    candidate: StrategyCandidate,
    net_edge_lcb_bps: float | None,
    risk_acceptance_prior: float | None = None,
    learning_weight: float | None = None,
) -> float:
    market_fit = _clamp01(candidate.market_fit_score)
    edge_quality = _edge_quality(candidate.edge_lcb_bps)
    net_margin = _net_margin(net_edge_lcb_bps)
    portfolio_fit = _clamp01(candidate.portfolio_fit_score)
    data_quality = _clamp01(candidate.data_quality_score)
    learning = _clamp01(candidate.learning_weight if learning_weight is None else learning_weight)
    risk_prior = _clamp01(
        candidate.risk_acceptance_prior
        if risk_acceptance_prior is None
        else risk_acceptance_prior
    )
    return _clamp01(
        0.25 * market_fit
        + 0.25 * edge_quality
        + 0.15 * net_margin
        + 0.15 * portfolio_fit
        + 0.10 * data_quality
        + 0.05 * learning
        + 0.05 * risk_prior
    )


def _guardian_feedback(
    *,
    match: StrategyMatchInput,
    candidate: StrategyCandidate,
    normalized_strategy: str | None,
) -> dict[str, Any]:
    base_floor = _clamp01(match.cognitive_confidence_floor)
    default = {
        "reject_rate": 0.0,
        "modify_rate": 0.0,
        "total": 0,
        "confidence_floor": base_floor,
        "aggressiveness_multiplier": 1.0,
        "risk_acceptance_prior": _clamp01(candidate.risk_acceptance_prior),
        "top_reasons": [],
        "evidence_refs": [],
        "high_reject_rate": False,
    }
    if candidate.action != "open" or normalized_strategy is None:
        return default

    selected: tuple[GuardianFeedbackStats, float, float, int] | None = None
    for stats in match.guardian_feedback:
        if stats.engine_mode and stats.engine_mode != match.engine_mode:
            continue
        if stats.symbol and stats.symbol != match.symbol:
            continue
        stats_strategy = _normalize_guardian_feedback_strategy(stats.strategy)
        if stats_strategy is not None and stats_strategy != normalized_strategy:
            continue
        total = _guardian_total(stats)
        if total < max(0, match.guardian_feedback_min_total):
            continue
        reject_rate = _guardian_reject_rate(stats, total)
        modify_rate = _guardian_modify_rate(stats, total)
        if selected is None or reject_rate > selected[1]:
            selected = (stats, reject_rate, modify_rate, total)

    if selected is None:
        return default

    stats, reject_rate, modify_rate, total = selected
    confidence_floor = max(base_floor, _guardian_confidence_floor(reject_rate))
    aggressiveness_multiplier = _guardian_aggressiveness_multiplier(
        reject_rate,
        modify_rate,
    )
    risk_acceptance_prior = min(
        _clamp01(candidate.risk_acceptance_prior),
        _clamp01(1.0 - reject_rate - (0.5 * modify_rate)),
    )
    return {
        "reject_rate": round(reject_rate, 6),
        "modify_rate": round(modify_rate, 6),
        "total": total,
        "confidence_floor": round(confidence_floor, 6),
        "aggressiveness_multiplier": round(aggressiveness_multiplier, 6),
        "risk_acceptance_prior": round(risk_acceptance_prior, 6),
        "top_reasons": stats.top_reasons,
        "evidence_refs": stats.evidence_refs,
        "high_reject_rate": reject_rate >= 0.50,
    }


def _normalize_guardian_feedback_strategy(strategy: str | None) -> str | None:
    if strategy is None:
        return None
    try:
        return normalize_strategy_key(strategy)
    except ValueError:
        return strategy.strip().lower()


def _guardian_total(stats: GuardianFeedbackStats) -> int:
    if stats.total is not None:
        return stats.total
    return stats.approved + stats.modified + stats.rejected


def _guardian_reject_rate(stats: GuardianFeedbackStats, total: int) -> float:
    if stats.reject_rate is not None:
        return _clamp01(stats.reject_rate)
    if total <= 0:
        return 0.0
    return _clamp01(stats.rejected / total)


def _guardian_modify_rate(stats: GuardianFeedbackStats, total: int) -> float:
    if stats.modify_rate is not None:
        return _clamp01(stats.modify_rate)
    if total <= 0:
        return 0.0
    return _clamp01(stats.modified / total)


def _guardian_confidence_floor(reject_rate: float) -> float:
    if reject_rate >= 0.70:
        return 0.85
    if reject_rate >= 0.50:
        return 0.75
    if reject_rate >= 0.30:
        return 0.65
    return 0.0


def _guardian_aggressiveness_multiplier(reject_rate: float, modify_rate: float) -> float:
    return max(0.25, _clamp01(1.0 - (0.50 * reject_rate) - (0.25 * modify_rate)))


def _learning_feedback(
    *,
    match: StrategyMatchInput,
    candidate: StrategyCandidate,
    normalized_strategy: str | None,
) -> dict[str, Any]:
    default = {
        "learning_weight": _clamp01(candidate.learning_weight),
        "learning_delta": 0.0,
        "reason_codes": [],
        "evidence_refs": [],
        "fact_refs": [],
        "inference_refs": [],
        "hypothesis_refs": [],
        "typed_rules": [],
    }
    if normalized_strategy is None:
        return default

    delta = 0.0
    reason_codes: list[str] = []
    evidence_refs: list[str] = []
    fact_refs: list[str] = []
    inference_refs: list[str] = []
    hypothesis_refs: list[str] = []
    typed_rules: list[dict[str, Any]] = []

    for insight in match.analyst_insights:
        if insight.engine_mode != match.engine_mode:
            continue
        if insight.symbol != match.symbol:
            continue
        claim_rows = insight.claims or [
            {
                "claim_id": insight.insight_id,
                "strategy": insight.strategy,
                "polarity": insight.metadata.get("polarity")
                if isinstance(insight.metadata, dict)
                else None,
                "confidence": (
                    insight.confidence
                    if insight.confidence is not None
                    else insight.metadata.get("confidence", 0.5)
                    if isinstance(insight.metadata, dict)
                    else 0.5
                ),
                "reason": insight.summary,
            }
        ]
        for claim in claim_rows:
            if not _claim_matches(claim, normalized_strategy, match.symbol):
                continue
            claim_delta, reason = _claim_learning_delta(
                claim,
                source="analyst",
                level=insight.insight_level,
            )
            if reason is None:
                continue
            delta += claim_delta
            reason_codes.append(reason)
            insight_evidence_refs = list(dict.fromkeys([insight.insight_id, *insight.evidence_refs]))
            evidence_refs.extend(insight_evidence_refs)
            typed_rules.append(
                {
                    "source": "analyst",
                    "insight_id": insight.insight_id,
                    "analyst_tier": insight.analyst_tier,
                    "insight_type": insight.insight_type,
                    "insight_level": insight.insight_level,
                    "claim_id": _claim_id(claim),
                    "polarity": _claim_polarity(claim),
                    "reason_code": reason,
                    "evidence_refs": insight_evidence_refs,
                }
            )
            if insight.insight_level == "fact":
                fact_refs.append(insight.insight_id)
            elif insight.insight_level == "hypothesis":
                hypothesis_refs.append(insight.insight_id)
            else:
                inference_refs.append(insight.insight_id)

    for claim in match.truth_registry_claims:
        if claim.symbol and claim.symbol != match.symbol:
            continue
        claim_row = {
            "claim_id": claim.claim_id,
            "strategy": claim.strategy,
            "pattern_text": claim.pattern_text,
            "polarity": claim.polarity,
            "confidence": claim.confidence,
            "observation_count": claim.observation_count,
            "reason": claim.reason,
        }
        if not _claim_matches(claim_row, normalized_strategy, match.symbol):
            continue
        claim_delta, reason = _claim_learning_delta(
            claim_row,
            source="truth_registry",
            level="inference",
        )
        if reason is None:
            continue
        delta += claim_delta
        reason_codes.append(reason)
        evidence_refs.extend([claim.claim_id, *claim.evidence_refs])
        typed_rules.append(
            {
                "source": "truth_registry",
                "insight_level": "inference",
                "claim_id": claim.claim_id,
                "polarity": _claim_polarity(claim_row),
                "reason_code": reason,
                "evidence_refs": list(dict.fromkeys([claim.claim_id, *claim.evidence_refs])),
            }
        )
        inference_refs.append(claim.claim_id)

    learning_weight = _clamp01(candidate.learning_weight + delta)
    return {
        "learning_weight": round(learning_weight, 6),
        "learning_delta": round(learning_weight - _clamp01(candidate.learning_weight), 6),
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "evidence_refs": list(dict.fromkeys(evidence_refs)),
        "fact_refs": list(dict.fromkeys(fact_refs)),
        "inference_refs": list(dict.fromkeys(inference_refs)),
        "hypothesis_refs": list(dict.fromkeys(hypothesis_refs)),
        "typed_rules": typed_rules,
    }


def _claim_matches(claim: dict[str, Any], normalized_strategy: str, symbol: str) -> bool:
    claim_symbol = claim.get("symbol")
    if claim_symbol and str(claim_symbol) != symbol:
        return False
    strategy = claim.get("strategy") or claim.get("applies_to_strategy")
    if strategy is None:
        return False
    try:
        return normalize_strategy_key(str(strategy)) == normalized_strategy
    except ValueError:
        return str(strategy).strip().lower() == normalized_strategy


def _claim_learning_delta(
    claim: dict[str, Any],
    *,
    source: str,
    level: str,
) -> tuple[float, str | None]:
    polarity = _claim_polarity(claim)
    if polarity is None:
        return 0.0, None
    confidence = _clamp01(float(claim.get("confidence", 0.5) or 0.5))
    obs_factor = _observation_factor(claim.get("observation_count"))
    level_factor = {"fact": 1.0, "inference": 0.75, "hypothesis": 0.50}.get(level, 0.75)
    claim_id = _claim_id(claim)
    if polarity == "negative":
        delta = -0.50 * confidence * obs_factor * level_factor
        return delta, f"{source}_negative_pattern:{claim_id}"
    delta = 0.25 * confidence * obs_factor * level_factor
    return delta, f"{source}_positive_pattern:{claim_id}"


def _claim_id(claim: dict[str, Any]) -> str:
    return str(claim.get("claim_id") or claim.get("id") or "unidentified")


def _claim_polarity(claim: dict[str, Any]) -> str | None:
    raw = str(claim.get("polarity") or claim.get("direction") or "").strip().lower()
    pattern_text = str(claim.get("pattern_text") or claim.get("pattern") or "").strip().lower()
    reason = str(claim.get("reason") or "").strip().lower()
    haystack = f"{raw} {pattern_text} {reason}"
    if any(token in haystack for token in ("losing", "loss", "negative", "refuting", "bad")):
        return "negative"
    if any(token in haystack for token in ("winning", "win", "positive", "supporting", "good")):
        return "positive"
    return None


def _observation_factor(value: Any) -> float:
    try:
        obs = float(value)
    except (TypeError, ValueError):
        obs = 0.0
    if obs <= 0.0:
        return 0.50
    return _clamp01(max(0.25, min(obs / 20.0, 1.0)))


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
