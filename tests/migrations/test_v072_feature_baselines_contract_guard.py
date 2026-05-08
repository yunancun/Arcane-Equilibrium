from __future__ import annotations

from pathlib import Path


SQL = (
    Path(__file__).resolve().parents[2]
    / "sql"
    / "migrations"
    / "V072__feature_baselines_contract_guard.sql"
).read_text(encoding="utf-8")


FEATURE_COLLECTOR_NAMES = (
    "sma_20",
    "sma_50",
    "ema_12",
    "ema_26",
    "rsi_14",
    "macd",
    "macd_signal",
    "macd_histogram",
    "bb_upper",
    "bb_middle",
    "bb_lower",
    "bb_bandwidth",
    "bb_percent_b",
    "atr_14",
    "atr_14_percent",
    "atr_5",
    "atr_5_percent",
    "stoch_k",
    "stoch_d",
    "kama",
    "kama_efficiency",
    "adx",
    "plus_di",
    "minus_di",
    "hurst",
    "regime_id",
    "ewma_vol",
    "vol_regime_id",
    "volume_ratio",
    "donchian_upper",
    "donchian_lower",
    "donchian_middle",
    "donchian_width",
    "price",
)


EDGE_PREDICTOR_ONLY_NAMES = (
    "adx_1h",
    "bb_width_pct",
    "atr_pct",
    "funding_rate",
    "realized_vol_1h",
    "basis_bps",
    "orderbook_imbalance_top5",
    "spread_bps",
    "confluence_score",
    "persistence_elapsed_ms",
    "side",
    "notional_pct_of_bal",
    "concurrent_positions",
    "same_direction_cnt",
    "tod_sin",
    "tod_cos",
    "is_funding_settlement_window",
)


def test_v072_guards_online_latest_as_34_dim_feature_collector_contract() -> None:
    assert "features.online_latest" in SQL
    assert "array_length(feature_vector, 1) <> 34" in SQL
    assert "feature_collector::FEATURE_NAMES" in SQL
    for name in FEATURE_COLLECTOR_NAMES:
        assert f"'{name}'" in SQL


def test_v072_rejects_active_baselines_outside_allowed_feature_names() -> None:
    assert "observability.feature_baselines" in SQL
    assert "valid_until IS NULL" in SQL
    assert "outside the 34-dim feature_collector contract" in SQL
    assert "LEFT JOIN allowed_feature_names" in SQL


def test_v072_does_not_seed_from_edge_predictor_decision_features() -> None:
    lowered = SQL.lower()

    assert "insert into observability.feature_baselines" not in lowered
    assert "\n    FROM learning.decision_features" not in SQL
    for name in EDGE_PREDICTOR_ONLY_NAMES:
        assert f"'{name}'" not in SQL
    assert "Do not seed from the 17-dim edge_predictor learning.decision_features" in SQL


def test_v072_adds_active_baseline_lookup_index() -> None:
    lowered = SQL.lower()

    assert "create index if not exists idx_feature_baselines_active_symbol_feature" in lowered
    assert "on observability.feature_baselines (symbol, feature_name)" in lowered
    assert "where valid_until is null" in lowered
