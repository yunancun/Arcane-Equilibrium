from __future__ import annotations

import pytest

from ml_training.mlde_shadow_advisor import ShadowAdvisorConfig, build_recommendations
from program_code.local_model_tools.dream_engine import DreamConfig, build_dream_summary
from program_code.local_model_tools.opportunity_tracker import (
    OpportunityConfig,
    summarize_rejected_outcomes,
)


def test_shadow_advisor_builds_rank_and_veto_recommendations():
    cfg = ShadowAdvisorConfig(min_samples=3, positive_rank_bps=2.0, negative_veto_bps=-2.0)
    recs = build_recommendations(
        [
            {
                "engine_mode": "demo",
                "strategy_name": "ma_crossover",
                "symbol_bucket": "btc",
                "regime": "trending",
                "scanner_route_mode": "normal",
                "scanner_edge_status": "positive",
                "mlde_arm_id": "ma_crossover__btc__trending__normal__positive",
                "linucb_arm_id": "trending__ma_crossover",
                "sample_count": 8,
                "avg_net_bps": 4.5,
                "win_rate": 0.75,
            },
            {
                "engine_mode": "demo",
                "strategy_name": "grid_trading",
                "symbol_bucket": "alt",
                "regime": "mean_reverting",
                "scanner_route_mode": "exploration",
                "scanner_edge_status": "negative",
                "mlde_arm_id": "grid_trading__alt__mean_reverting__exploration__negative",
                "linucb_arm_id": "mean_reverting__grid_trading",
                "sample_count": 9,
                "avg_net_bps": -6.0,
                "win_rate": 0.2,
            },
            {
                "engine_mode": "demo",
                "strategy_name": "bb_reversion",
                "sample_count": 2,
                "avg_net_bps": 20.0,
            },
        ],
        cfg,
    )

    assert {r.recommendation_type for r in recs} == {"rank", "veto"}
    assert all(r.payload["policy"] == "shadow_advisory_only" for r in recs)
    assert all(0.0 < r.confidence <= cfg.confidence_cap for r in recs)


def test_dream_summary_emits_parameter_proposals_for_negative_edge():
    cfg = DreamConfig(min_samples=3, negative_edge_bps=-2.0)
    summary = build_dream_summary(
        [
            {
                "strategy_name": "grid_trading",
                "symbol_bucket": "alt",
                "regime": "mean_reverting",
                "scanner_route_mode": "normal",
                "scanner_edge_status": "negative",
                "sample_count": 12,
                "avg_net_bps": -8.0,
            },
            {
                "strategy_name": "ma_crossover",
                "symbol_bucket": "btc",
                "regime": "trending",
                "scanner_route_mode": "normal",
                "scanner_edge_status": "positive",
                "sample_count": 10,
                "avg_net_bps": 3.0,
            },
        ],
        cfg,
    )

    assert summary["_meta"]["source"] == "dream_engine"
    assert len(summary["insights"]) == 1
    insight = summary["insights"][0]
    assert insight["strategy_name"] == "grid_trading"
    assert insight["param_name"] == "grid_spacing_bps"
    assert insight["expected_improvement_bps"] == pytest.approx(4.0)


def test_opportunity_tracker_classifies_undertrading_and_overtrading():
    cfg = OpportunityConfig(min_samples=2, friction_bps=1.0)
    under = summarize_rejected_outcomes(
        [
            {"strategy_name": "ma_crossover", "side": "Buy", "outcome_1h": 0.003},
            {"strategy_name": "ma_crossover", "side": "Buy", "outcome_1h": 0.004},
            {"strategy_name": "grid_trading", "side": "Buy", "outcome_1h": -0.0001},
        ],
        cfg,
    )
    assert under["net_regret_direction"] == "undertrading"

    over = summarize_rejected_outcomes(
        [
            {"strategy_name": "grid_trading", "side": "Buy", "outcome_1h": -0.003},
            {"strategy_name": "grid_trading", "side": "Buy", "outcome_1h": -0.002},
            {"strategy_name": "ma_crossover", "side": "Buy", "outcome_1h": 0.0},
        ],
        cfg,
    )
    assert over["net_regret_direction"] == "overtrading"
