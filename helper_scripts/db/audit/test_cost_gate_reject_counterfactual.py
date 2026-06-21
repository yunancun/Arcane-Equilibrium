from __future__ import annotations

import pytest

from helper_scripts.db.audit.cost_gate_reject_counterfactual import (
    AuditConfig,
    build_json_payload,
    build_learning_lane_scorecard,
    build_counterfactual_sql,
    classify_learning_lane_row,
    render_markdown,
    side_to_int,
    validate_config,
)


def test_side_to_int_accepts_operator_terms() -> None:
    assert side_to_int("Buy") == 1
    assert side_to_int("long") == 1
    assert side_to_int("Sell") == -1
    assert side_to_int("short") == -1
    assert side_to_int(None) is None


def test_side_to_int_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        side_to_int("flat")


def test_counterfactual_sql_uses_feature_rows_and_klines_not_outcomes() -> None:
    cfg = AuditConfig(
        engine_modes=("demo", "live_demo"),
        lookback_hours=168,
        horizon_minutes=60,
        limit=50_000,
        friction_bps=4.0,
        strategy="ma_crossover",
        symbol="BTCUSDT",
        side=1,
    )
    sql, params = build_counterfactual_sql(cfg)

    assert "learning.decision_features f" in sql
    assert "market.klines k" in sql
    assert "trading.decision_outcomes" not in sql
    assert "LIKE 'cost_gate%%'" in sql
    assert "LIKE 'cost_gate%'" not in sql
    assert "f.strategy_name = %s" in sql
    assert "f.symbol = %s" in sql
    assert "f.side = %s" in sql
    assert params == [
        ["demo", "live_demo"],
        168,
        60,
        "ma_crossover",
        "BTCUSDT",
        1,
        50_000,
        60,
        4.0,
        4.0,
    ]


def test_validate_config_bounds() -> None:
    cfg = AuditConfig(
        engine_modes=("demo",),
        lookback_hours=168,
        horizon_minutes=60,
        limit=50_000,
        friction_bps=4.0,
    )
    validate_config(cfg)

    with pytest.raises(ValueError):
        validate_config(
            AuditConfig(
                engine_modes=("demo",),
                lookback_hours=0,
                horizon_minutes=60,
                limit=50_000,
                friction_bps=4.0,
            )
        )

    with pytest.raises(ValueError):
        validate_config(
            AuditConfig(
                engine_modes=("unknown",),
                lookback_hours=168,
                horizon_minutes=60,
                limit=50_000,
                friction_bps=4.0,
            )
        )

    with pytest.raises(ValueError):
        validate_config(
            AuditConfig(
                engine_modes=("demo",),
                lookback_hours=168,
                horizon_minutes=60,
                limit=50,
                friction_bps=4.0,
                min_probe_sample=51,
            )
        )

    with pytest.raises(ValueError):
        validate_config(
            AuditConfig(
                engine_modes=("demo",),
                lookback_hours=168,
                horizon_minutes=60,
                limit=50_000,
                friction_bps=4.0,
                min_probe_net_positive_pct=101.0,
            )
        )


def test_learning_lane_scorecard_classifies_probe_block_and_sample_gap() -> None:
    cfg = AuditConfig(
        engine_modes=("demo", "live_demo"),
        lookback_hours=168,
        horizon_minutes=60,
        limit=50_000,
        friction_bps=4.0,
        min_probe_sample=100,
    )
    rows = [
        {
            "strategy_name": "ma_crossover",
            "symbol": "ETHUSDT",
            "side": "Sell",
            "reject_reason_code": "cost_gate_js_demo_negative_edge",
            "n": 13_487,
            "joined_contexts": 13,
            "avg_gross_bps": 101.9788,
            "p50_gross_bps": 17.9914,
            "p90_gross_bps": 239.4133,
            "avg_net_bps": 97.9788,
            "gross_positive_pct": 86.01,
            "net_positive_pct": 86.01,
            "max_ts": "2026-06-19 06:29:59.987+02",
        },
        {
            "strategy_name": "ma_crossover",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "reject_reason_code": "cost_gate_js_demo_negative_edge",
            "n": 24_437,
            "joined_contexts": 32,
            "avg_gross_bps": -31.7434,
            "p50_gross_bps": -29.6769,
            "p90_gross_bps": -10.7815,
            "avg_net_bps": -35.7434,
            "gross_positive_pct": 0.0,
            "net_positive_pct": 0.0,
            "max_ts": "2026-06-21 08:47:59.990+02",
        },
        {
            "strategy_name": "grid",
            "symbol": "DOGEUSDT",
            "side": "Buy",
            "reject_reason_code": "cost_gate_js_demo_negative_edge",
            "n": 3,
            "joined_contexts": 0,
            "avg_gross_bps": 20.0,
            "p50_gross_bps": 20.0,
            "p90_gross_bps": 20.0,
            "avg_net_bps": 16.0,
            "gross_positive_pct": 100.0,
            "net_positive_pct": 100.0,
            "max_ts": "2026-06-21 08:47:59.990+02",
        },
        {
            "strategy_name": "funding_arb",
            "symbol": "REUSDT",
            "side": "Buy",
            "reject_reason_code": "cost_gate_atr_unavailable",
            "n": 1_265,
            "joined_contexts": 0,
            "avg_gross_bps": 206.1157,
            "p50_gross_bps": 212.2594,
            "p90_gross_bps": 383.0337,
            "avg_net_bps": 202.1157,
            "gross_positive_pct": 69.8,
            "net_positive_pct": 69.8,
            "max_ts": "2026-06-19 10:06:56.617+02",
        },
    ]
    coverage = {
        "decision_features": 182_058,
        "features_joined_contexts": 353,
        "features_joined_outcomes": 0,
    }

    assert classify_learning_lane_row(cfg, rows[0])[0] == "LEARNING_PROBE_CANDIDATE"
    assert classify_learning_lane_row(cfg, rows[1])[0] == "BLOCK_CONFIRMED"
    assert classify_learning_lane_row(cfg, rows[2])[0] == "INSUFFICIENT_SAMPLE"
    assert classify_learning_lane_row(cfg, rows[3])[0] == "DATA_COVERAGE_BLOCKER"

    scorecard = build_learning_lane_scorecard(cfg, coverage, rows)
    assert scorecard["status"] == "LEARNING_LANE_PROBE_CANDIDATES_PRESENT"
    assert scorecard["outcome_path_status"] == "OUTCOME_PATH_STALLED_FOR_FEATURE_REJECTS"
    assert scorecard["action_counts"] == {
        "LEARNING_PROBE_CANDIDATE": 1,
        "BLOCK_CONFIRMED": 1,
        "INSUFFICIENT_SAMPLE": 1,
        "DATA_COVERAGE_BLOCKER": 1,
    }
    assert scorecard["probe_candidates"][0]["symbol"] == "ETHUSDT"
    assert scorecard["block_confirmed"][0]["symbol"] == "BTCUSDT"
    ranking = scorecard["profit_opportunity_ranking"]
    assert ranking["schema_version"] == "cost_gate_profit_opportunity_ranking_v1"
    assert ranking["status"] == "PROFIT_LEARNING_CANDIDATES_PRESENT"
    assert ranking["next_trigger"] == (
        "operator_review_top_ranked_side_cells_for_bounded_demo_learning_lane"
    )
    assert ranking["candidate_count"] == 1
    assert ranking["boundary"] == {
        "order_authority": "NOT_GRANTED",
        "main_cost_gate_adjustment": "NONE",
        "promotion_evidence": False,
        "runtime_mutation": "NONE",
    }
    top = ranking["top_side_cells"][0]
    assert top["side_cell_key"] == "ma_crossover|ETHUSDT|Sell"
    assert top["priority_tier"] == "HIGH_PRIORITY_BOUNDED_DEMO_LEARNING"
    assert top["order_authority"] == "NOT_GRANTED"
    assert top["main_cost_gate_adjustment"] == "NONE"
    assert top["promotion_evidence"] is False
    assert top["next_action"] == "operator_review_ranked_side_cell_for_bounded_demo_learning_lane"
    assert top["priority_score"] > 70.0
    assert top["median_margin_bps"] == pytest.approx(13.9914)
    assert top["hit_rate_margin_pct"] == pytest.approx(31.01)


def test_markdown_and_json_payload_surface_learning_lane_actions() -> None:
    cfg = AuditConfig(
        engine_modes=("demo",),
        lookback_hours=24,
        horizon_minutes=30,
        limit=1_000,
        friction_bps=4.0,
        min_probe_sample=10,
    )
    coverage = {
        "risk_verdicts": 10,
        "latest_risk_verdict_ts": "2026-06-21T00:00:00Z",
        "risk_verdicts_joined_intents": 0,
        "decision_features": 10,
        "features_joined_contexts": 0,
        "features_joined_outcomes": 0,
        "decision_context_old_pending": 100,
    }
    rows = [
        {
            "strategy_name": "ma_crossover",
            "symbol": "NEARUSDT",
            "side": "Sell",
            "reject_reason_code": "cost_gate_js_demo_negative_edge",
            "n": 25,
            "joined_contexts": 0,
            "avg_gross_bps": 20.0,
            "p50_gross_bps": 8.0,
            "p90_gross_bps": 30.0,
            "avg_net_bps": 16.0,
            "gross_positive_pct": 90.0,
            "net_positive_pct": 80.0,
            "max_ts": "2026-06-21T00:00:00Z",
        }
    ]

    markdown = render_markdown(
        cfg,
        coverage,
        rows,
        generated="2026-06-21T00:00:00+00:00",
    )
    assert "## Learning Lane Scorecard" in markdown
    assert "### Profit Opportunity Ranking" in markdown
    assert "PROFIT_LEARNING_CANDIDATES_PRESENT" in markdown
    assert "LEARNING_PROBE_CANDIDATE" in markdown
    assert "NEARUSDT" in markdown

    payload = build_json_payload(
        cfg,
        coverage,
        rows,
        generated="2026-06-21T00:00:00+00:00",
    )
    scorecard = payload["learning_lane_scorecard"]
    assert scorecard["schema_version"] == "cost_gate_reject_counterfactual_v2"
    assert scorecard["status"] == "LEARNING_LANE_PROBE_CANDIDATES_PRESENT"
    assert scorecard["rows"][0]["learning_lane_action"] == "LEARNING_PROBE_CANDIDATE"
    ranking = scorecard["profit_opportunity_ranking"]
    assert ranking["status"] == "PROFIT_LEARNING_CANDIDATES_PRESENT"
    assert ranking["top_side_cells"][0]["side_cell_key"] == "ma_crossover|NEARUSDT|Sell"
    assert ranking["top_side_cells"][0]["order_authority"] == "NOT_GRANTED"
