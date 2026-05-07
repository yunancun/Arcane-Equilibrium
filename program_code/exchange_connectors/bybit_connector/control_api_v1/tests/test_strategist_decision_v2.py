from __future__ import annotations

import pytest

from app.strategist_decision_v2 import (
    GuardianFeedbackStats,
    StrategyCandidate,
    StrategyMatchInput,
    build_strategist_decision,
    normalize_strategy_key,
)


def _match(*candidates: StrategyCandidate, **overrides) -> StrategyMatchInput:
    payload = {
        "match_id": "match-paper-BTCUSDT-1",
        "signal_id": "sig-paper-BTCUSDT-1",
        "ts_ms": 1_700_000_000_000,
        "engine_mode": "paper",
        "symbol": "BTCUSDT",
        "direction": "long",
        "candidate_routes": list(candidates),
        "scanner_candidate_id": "scanner-candidate-1",
        "evidence_refs": ["scan-row-1"],
        "fact_refs": ["fact-fill-cost-1"],
        "inference_refs": ["inference-edge-lcb-1"],
        "hypothesis_refs": ["hypothesis-regime-1"],
        "default_size": 0.001,
    }
    payload.update(overrides)
    return StrategyMatchInput(**payload)


def test_selects_canonical_strategy_not_evaluation_source_label() -> None:
    decision = build_strategist_decision(
        _match(
            StrategyCandidate(
                candidate_id="route-ma",
                strategy="ma_crossover",
                action="open",
                direction="long",
                market_fit_score=0.9,
                edge_lcb_bps=24.0,
                cost_bps=6.0,
                data_quality_score=0.9,
            )
        )
    )

    assert decision.decision_action == "open"
    assert decision.strategy == "ma_crossover"
    assert decision.selected_strategy == "ma_crossover"
    assert decision.strategy not in {"strategist_ai", "strategist_heuristic"}
    assert decision.thesis
    assert decision.invalidation
    assert decision.expected_net_edge_bps == 18.0
    assert decision.proposed_qty == 0.001


def test_scanner_top_rank_can_lose_to_better_net_edge_candidate() -> None:
    decision = build_strategist_decision(
        _match(
            StrategyCandidate(
                candidate_id="route-grid-top",
                strategy="grid_trading",
                action="open",
                direction="long",
                market_fit_score=0.99,
                edge_lcb_bps=7.0,
                cost_bps=6.0,
                data_quality_score=0.9,
            ),
            StrategyCandidate(
                candidate_id="route-ma-lower-rank",
                strategy="ma_crossover",
                action="open",
                direction="long",
                market_fit_score=0.70,
                edge_lcb_bps=32.0,
                cost_bps=7.0,
                portfolio_fit_score=0.9,
                learning_weight=0.8,
                risk_acceptance_prior=0.8,
                data_quality_score=0.9,
            ),
        )
    )

    assert decision.selected_strategy == "ma_crossover"
    assert decision.selected_candidate_id == "route-ma-lower-rank"


def test_negative_net_lcb_blocks_new_open_but_allows_position_review_reduce() -> None:
    open_decision = build_strategist_decision(
        _match(
            StrategyCandidate(
                candidate_id="route-grid-negative-open",
                strategy="grid_trading",
                action="open",
                direction="long",
                market_fit_score=0.8,
                edge_lcb_bps=2.0,
                cost_bps=6.0,
                data_quality_score=0.9,
            )
        )
    )
    assert open_decision.decision_action == "no_action"
    assert open_decision.metadata["reject_reasons"] == ["all_candidates_rejected"]
    assert open_decision.candidate_scores[0]["reject_reasons"] == [
        "negative_net_lcb_blocks_open"
    ]

    reduce_decision = build_strategist_decision(
        _match(
            StrategyCandidate(
                candidate_id="route-grid-reduce",
                strategy="grid_trading",
                action="reduce",
                direction="close_long",
                market_fit_score=0.8,
                edge_lcb_bps=2.0,
                cost_bps=6.0,
                data_quality_score=0.9,
            ),
            position_review_id="position-review-1",
        )
    )
    assert reduce_decision.decision_action == "reduce"
    assert reduce_decision.selected_strategy == "grid_trading"
    assert reduce_decision.expected_net_edge_bps == -4.0


def test_strategy_alias_is_normalized_before_persistence() -> None:
    assert normalize_strategy_key("funding_rate_arb") == "funding_arb"

    decision = build_strategist_decision(
        _match(
            StrategyCandidate(
                candidate_id="route-funding",
                strategy="funding_rate_arb",
                action="open",
                direction="short",
                market_fit_score=0.8,
                edge_lcb_bps=18.0,
                cost_bps=3.0,
                data_quality_score=0.9,
            )
        )
    )
    assert decision.strategy == "funding_arb"
    assert decision.selected_strategy == "funding_arb"


def test_missing_evidence_or_candidates_produces_no_action_with_reason() -> None:
    missing_lineage = build_strategist_decision(
        _match(
            StrategyCandidate(candidate_id="route-ma", strategy="ma_crossover"),
            signal_id="",
            scanner_candidate_id=None,
            position_review_id=None,
            evidence_refs=[],
        )
    )
    assert missing_lineage.decision_action == "no_action"
    assert missing_lineage.metadata["reject_reasons"] == ["missing_lineage"]

    no_candidates = build_strategist_decision(_match(candidate_routes=[]))
    assert no_candidates.decision_action == "no_action"
    assert no_candidates.metadata["reject_reasons"] == ["no_strategy_candidates"]


def test_decision_keeps_fact_inference_hypothesis_refs_separate() -> None:
    decision = build_strategist_decision(
        _match(
            StrategyCandidate(
                candidate_id="route-bb",
                strategy="bb_breakout",
                action="open",
                direction="long",
                market_fit_score=0.8,
                edge_lcb_bps=20.0,
                cost_bps=5.0,
                data_quality_score=0.9,
            )
        )
    )

    assert decision.fact_refs == ["fact-fill-cost-1"]
    assert decision.inference_refs == ["inference-edge-lcb-1"]
    assert decision.hypothesis_refs == ["hypothesis-regime-1"]


def test_unknown_strategy_is_rejected_fail_closed() -> None:
    with pytest.raises(ValueError):
        normalize_strategy_key("strategist_ai")

    decision = build_strategist_decision(
        _match(
            StrategyCandidate(
                candidate_id="route-legacy-label",
                strategy="strategist_ai",
                action="open",
                direction="long",
                market_fit_score=0.9,
                edge_lcb_bps=25.0,
                cost_bps=5.0,
                data_quality_score=0.9,
            )
        )
    )
    assert decision.decision_action == "no_action"
    assert decision.candidate_scores[0]["reject_reasons"] == [
        "unknown_strategy:strategist_ai"
    ]


def test_guardian_high_reject_rate_raises_confidence_floor_for_new_opens() -> None:
    decision = build_strategist_decision(
        _match(
            StrategyCandidate(
                candidate_id="route-grid-after-rejects",
                strategy="grid_trading",
                action="open",
                direction="long",
                market_fit_score=0.75,
                edge_lcb_bps=20.0,
                cost_bps=5.0,
                data_quality_score=0.9,
                confidence=0.62,
            ),
            guardian_feedback=[
                GuardianFeedbackStats(
                    strategy="grid_trading",
                    symbol="BTCUSDT",
                    engine_mode="paper",
                    approved=2,
                    rejected=8,
                    top_reasons=["drawdown_limit", "correlation_cap"],
                    evidence_refs=["guardian-window-grid-btc-1"],
                )
            ],
        )
    )

    assert decision.decision_action == "no_action"
    feedback = decision.candidate_scores[0]["guardian_feedback"]
    assert feedback["reject_rate"] == 0.8
    assert feedback["confidence_floor"] == 0.85
    assert feedback["risk_acceptance_prior"] < 0.3
    assert "guardian_reject_rate_confidence_floor" in decision.candidate_scores[0][
        "reject_reasons"
    ]


def test_guardian_reject_stats_reduce_aggressiveness_for_high_confidence_open() -> None:
    decision = build_strategist_decision(
        _match(
            StrategyCandidate(
                candidate_id="route-ma-high-confidence",
                strategy="ma_crossover",
                action="open",
                direction="long",
                market_fit_score=0.95,
                edge_lcb_bps=45.0,
                cost_bps=5.0,
                data_quality_score=0.95,
                confidence=0.92,
            ),
            guardian_feedback=[
                GuardianFeedbackStats(
                    strategy="ma_crossover",
                    symbol="BTCUSDT",
                    approved=4,
                    modified=1,
                    rejected=5,
                    evidence_refs=["guardian-window-ma-btc-1"],
                )
            ],
            default_size=1.0,
        )
    )

    assert decision.decision_action == "open"
    assert decision.proposed_qty == 0.725
    assert decision.evidence_refs[-1] == "guardian-window-ma-btc-1"
    assert decision.portfolio_impact["guardian_feedback"] == {
        "reject_rate": 0.5,
        "modify_rate": 0.1,
        "aggressiveness_multiplier": 0.725,
        "confidence_floor": 0.75,
    }
    assert decision.metadata["guardian_feedback_model"] == "v1"


def test_guardian_feedback_is_strategy_scoped() -> None:
    decision = build_strategist_decision(
        _match(
            StrategyCandidate(
                candidate_id="route-ma-not-grid",
                strategy="ma_crossover",
                action="open",
                direction="long",
                market_fit_score=0.85,
                edge_lcb_bps=28.0,
                cost_bps=6.0,
                data_quality_score=0.9,
                confidence=0.7,
            ),
            guardian_feedback=[
                GuardianFeedbackStats(
                    strategy="grid_trading",
                    symbol="BTCUSDT",
                    approved=1,
                    rejected=9,
                    evidence_refs=["guardian-window-grid-only"],
                )
            ],
        )
    )

    assert decision.decision_action == "open"
    assert decision.candidate_scores[0]["guardian_feedback"]["reject_rate"] == 0.0
    assert decision.proposed_qty == 0.001


def test_guardian_open_rejection_stats_do_not_block_position_review_reduce() -> None:
    decision = build_strategist_decision(
        _match(
            StrategyCandidate(
                candidate_id="route-grid-reduce-after-review",
                strategy="grid_trading",
                action="reduce",
                direction="close_long",
                market_fit_score=0.75,
                edge_lcb_bps=-5.0,
                cost_bps=5.0,
                data_quality_score=0.9,
                confidence=0.45,
            ),
            guardian_feedback=[
                GuardianFeedbackStats(
                    strategy="grid_trading",
                    symbol="BTCUSDT",
                    approved=1,
                    rejected=9,
                )
            ],
            position_review_id="position-review-guardian-feedback-1",
        )
    )

    assert decision.decision_action == "reduce"
    assert decision.candidate_scores[0]["guardian_feedback"]["confidence_floor"] == 0.0
    assert "guardian_reject_rate_confidence_floor" not in decision.candidate_scores[0][
        "reject_reasons"
    ]
