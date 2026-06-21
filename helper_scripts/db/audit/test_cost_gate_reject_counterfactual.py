from __future__ import annotations

import pytest

from helper_scripts.db.audit.cost_gate_reject_counterfactual import (
    AuditConfig,
    build_counterfactual_sql,
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
