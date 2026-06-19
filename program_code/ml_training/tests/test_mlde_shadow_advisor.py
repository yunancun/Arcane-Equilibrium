from __future__ import annotations

import pytest

import ml_training.mlde_shadow_advisor as mlde_shadow_advisor
from ml_training.mlde_shadow_advisor import (
    DEFAULT_PG_STATEMENT_TIMEOUT_MS,
    ShadowAdvisorConfig,
    ShadowRecommendation,
    build_recommendations,
    config_from_env as shadow_config_from_env,
)
from program_code.local_model_tools.dream_engine import (
    DreamConfig,
    build_dream_summary,
    config_from_env as dream_config_from_env,
)
from program_code.local_model_tools.opportunity_tracker import (
    OpportunityConfig,
    summarize_rejected_outcomes,
)


def test_mlde_shadow_and_dream_use_demo_only_lower_default(monkeypatch):
    for key in (
        "OPENCLAW_MLDE_SHADOW_MIN_SAMPLES",
        "OPENCLAW_MLDE_SHADOW_MIN_SAMPLES_DEMO",
        "OPENCLAW_MLDE_SHADOW_MIN_SAMPLES_LIVE_DEMO",
        "OPENCLAW_MLDE_DREAM_MIN_SAMPLES",
        "OPENCLAW_MLDE_DREAM_MIN_SAMPLES_DEMO",
        "OPENCLAW_MLDE_DREAM_MIN_SAMPLES_LIVE_DEMO",
    ):
        monkeypatch.delenv(key, raising=False)

    assert shadow_config_from_env("demo").min_samples == 3
    assert shadow_config_from_env("live_demo").min_samples == 5
    assert dream_config_from_env("demo").min_samples == 3
    assert dream_config_from_env("live_demo").min_samples == 5


def test_mode_specific_min_samples_env_overrides_generic(monkeypatch):
    monkeypatch.setenv("OPENCLAW_MLDE_SHADOW_MIN_SAMPLES", "5")
    monkeypatch.setenv("OPENCLAW_MLDE_SHADOW_MIN_SAMPLES_DEMO", "2")
    monkeypatch.setenv("OPENCLAW_MLDE_DREAM_MIN_SAMPLES", "5")
    monkeypatch.setenv("OPENCLAW_MLDE_DREAM_MIN_SAMPLES_DEMO", "2")

    assert shadow_config_from_env("demo").min_samples == 2
    assert shadow_config_from_env("live_demo").min_samples == 5
    assert dream_config_from_env("demo").min_samples == 2
    assert dream_config_from_env("live_demo").min_samples == 5


def test_shadow_advisor_config_defaults_to_bounded_pg_statement_timeout(monkeypatch):
    monkeypatch.delenv("OPENCLAW_MLDE_SHADOW_STATEMENT_TIMEOUT_MS", raising=False)

    assert (
        shadow_config_from_env("demo").statement_timeout_ms
        == DEFAULT_PG_STATEMENT_TIMEOUT_MS
    )

    monkeypatch.setenv("OPENCLAW_MLDE_SHADOW_STATEMENT_TIMEOUT_MS", "1234")
    assert shadow_config_from_env("demo").statement_timeout_ms == 1234


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
                "scanner_market_regime": "trending",
                "scanner_trend_phase": "clean_trend",
                "scanner_trend_score": 0.82,
                "scanner_range_score": 0.18,
                "scanner_f_ma": 0.81,
                "scanner_f_bkout": 0.74,
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
    rank = next(r for r in recs if r.recommendation_type == "rank")
    assert rank.payload["scanner_context"]["scanner_trend_phase"] == "clean_trend"
    assert rank.payload["scanner_context"]["scanner_f_bkout"] == 0.74


def test_shadow_advisor_fetch_sets_statement_timeout_before_base_query(monkeypatch):
    calls = []

    class FakeCursor:
        description = None

        def __init__(self):
            self._rows = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params=None):
            calls.append((sql, params))
            self._rows = []
            self.description = [("engine_mode",)]

        def fetchall(self):
            return self._rows

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

    class FakePsycopg2:
        @staticmethod
        def connect(dsn, connect_timeout=2):
            assert dsn == "postgresql://unit-test"
            assert connect_timeout == 2
            return FakeConn()

    monkeypatch.setattr(mlde_shadow_advisor, "psycopg2", FakePsycopg2)

    cfg = ShadowAdvisorConfig(statement_timeout_ms=2345)
    assert mlde_shadow_advisor._fetch_aggregate_rows("postgresql://unit-test", cfg) == []

    assert len(calls) == 2
    timeout_sql, timeout_params = calls[0]
    assert "SET LOCAL statement_timeout" in timeout_sql
    assert timeout_params == (2345,)
    select_sql, select_params = calls[1]
    assert "FROM trading.intents" in select_sql
    assert "JOIN learning.decision_features" in select_sql
    assert "decision_context_snapshots" in select_sql
    assert "mlde_edge_training_rows" not in select_sql
    assert "trading.signals" not in select_sql
    assert select_params[0] == ["demo"]


def test_shadow_advisor_persist_sets_statement_timeout_before_insert(monkeypatch):
    calls = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params=None):
            calls.append((sql, params))

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

        def commit(self):
            pass

    class FakePsycopg2:
        class Error(Exception):
            pass

        @staticmethod
        def connect(dsn, connect_timeout=2):
            assert dsn == "postgresql://unit-test"
            assert connect_timeout == 2
            return FakeConn()

    monkeypatch.setattr(mlde_shadow_advisor, "psycopg2", FakePsycopg2)
    monkeypatch.setattr(mlde_shadow_advisor, "Json", lambda value: value)

    rec = ShadowRecommendation(
        engine_mode="demo",
        source="ml_shadow",
        recommendation_type="rank",
        strategy_name="grid_trading",
        symbol=None,
        expected_net_bps=4.5,
        confidence=0.75,
        sample_count=8,
        payload={"policy": "shadow_advisory_only"},
    )
    inserted = mlde_shadow_advisor._persist_recommendations(
        "postgresql://unit-test",
        [rec],
        statement_timeout_ms=3456,
    )

    assert inserted == 1
    assert len(calls) == 2
    timeout_sql, timeout_params = calls[0]
    assert "SET LOCAL statement_timeout" in timeout_sql
    assert timeout_params == (3456,)
    assert "verify_replay_evidence_and_insert" in calls[1][0]


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
                "scanner_market_regime": "range_bound",
                "scanner_trend_phase": "range_bound",
                "scanner_range_score": 0.78,
                "scanner_f_grid": 0.83,
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
    assert insight["scanner_context"]["scanner_trend_phase"] == "range_bound"
    assert insight["scanner_context"]["scanner_f_grid"] == 0.83


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
