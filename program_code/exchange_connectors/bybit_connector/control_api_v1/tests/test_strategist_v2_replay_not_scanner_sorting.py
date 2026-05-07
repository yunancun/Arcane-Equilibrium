from __future__ import annotations

from app.agent_contracts import AnalystInsight
from app.strategist_decision_v2 import (
    GuardianFeedbackStats,
    StrategyCandidate,
    StrategyMatchInput,
    build_strategist_decision,
)


def test_replay_strategist_decision_is_not_raw_scanner_rank_sorting() -> None:
    replay_match = StrategyMatchInput(
        match_id="replay-mag045-BTCUSDT-step-1",
        signal_id="sig-replay-mag045-BTCUSDT-step-1",
        ts_ms=1_700_000_100_000,
        engine_mode="replay",
        symbol="BTCUSDT",
        direction="long",
        scanner_candidate_id="scanner-candidate-replay-rank-1",
        evidence_refs=["scanner-replay-snapshot-1"],
        fact_refs=["fact-cost-cell-1"],
        inference_refs=["inference-edge-lcb-1"],
        hypothesis_refs=["hypothesis-regime-continuation-1"],
        default_size=1.0,
        guardian_feedback=[
            GuardianFeedbackStats(
                strategy="grid_trading",
                symbol="BTCUSDT",
                engine_mode="replay",
                approved=2,
                rejected=8,
                top_reasons=["drawdown_limit"],
                evidence_refs=["guardian-replay-grid-reject-window"],
            )
        ],
        analyst_insights=[
            AnalystInsight(
                insight_id="analyst-replay-grid-loss",
                ts_ms=1_700_000_099_000,
                engine_mode="replay",
                symbol="BTCUSDT",
                strategy="grid_trading",
                insight_level="inference",
                summary="grid_trading losing pattern during one-way shock",
                evidence_refs=["roundtrip-grid-loss-replay"],
                claims=[
                    {
                        "claim_id": "claim-grid-loss-replay",
                        "strategy": "grid_trading",
                        "polarity": "negative",
                        "confidence": 0.9,
                        "observation_count": 20,
                    }
                ],
            )
        ],
        candidate_routes=[
            StrategyCandidate(
                candidate_id="route-grid-scanner-rank-1",
                strategy="grid_trading",
                action="open",
                direction="long",
                scanner_rank=1,
                market_fit_score=0.96,
                edge_lcb_bps=10.0,
                cost_bps=6.0,
                data_quality_score=0.9,
                learning_weight=0.8,
                risk_acceptance_prior=0.8,
                confidence=0.62,
            ),
            StrategyCandidate(
                candidate_id="route-ma-scanner-rank-2",
                strategy="ma_crossover",
                action="open",
                direction="long",
                scanner_rank=2,
                market_fit_score=0.78,
                edge_lcb_bps=34.0,
                cost_bps=7.0,
                data_quality_score=0.9,
                portfolio_fit_score=0.9,
                learning_weight=0.7,
                risk_acceptance_prior=0.75,
                confidence=0.82,
            ),
        ],
    )

    decision = build_strategist_decision(replay_match)
    ranked_rows = {row["candidate_id"]: row for row in decision.candidate_scores}

    assert decision.decision_action == "open"
    assert decision.selected_candidate_id == "route-ma-scanner-rank-2"
    assert decision.selected_strategy == "ma_crossover"
    assert ranked_rows["route-grid-scanner-rank-1"]["scanner_rank"] == 1
    assert ranked_rows["route-ma-scanner-rank-2"]["scanner_rank"] == 2
    assert ranked_rows["route-grid-scanner-rank-1"]["guardian_feedback"]["reject_rate"] == 0.8
    assert ranked_rows["route-grid-scanner-rank-1"]["learning_feedback"]["reason_codes"] == [
        "analyst_negative_pattern:claim-grid-loss-replay"
    ]
    assert "guardian_reject_rate_confidence_floor" in ranked_rows[
        "route-grid-scanner-rank-1"
    ]["reject_reasons"]
    assert decision.expected_net_edge_bps == 27.0
    assert decision.thesis
    assert decision.invalidation
    assert "market_fit=" in decision.thesis
    assert "guardian-replay-grid-reject-window" not in decision.evidence_refs
    assert "scanner-replay-snapshot-1" in decision.evidence_refs
