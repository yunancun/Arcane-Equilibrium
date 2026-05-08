from __future__ import annotations

from pathlib import Path


SQL = (
    Path(__file__).resolve().parents[2]
    / "sql"
    / "migrations"
    / "V069__drop_dead_observability_scorer_predictions.sql"
).read_text(encoding="utf-8")


def test_v069_drops_only_scorer_predictions_with_restrict() -> None:
    lowered = SQL.lower()

    assert "drop table if exists observability.scorer_predictions restrict" in lowered
    assert "drop table if exists observability.model_performance" not in lowered
    assert "drop table if exists observability.feature_baselines" not in lowered
    assert "drop table if exists observability.drift_events" not in lowered
    assert "cascade" not in lowered


def test_v069_refuses_non_empty_or_dependent_table() -> None:
    assert "SELECT count(*) FROM observability.scorer_predictions" in SQL
    assert "is not empty" in SQL
    assert "pg_depend" in SQL
    assert "dependent relation" in SQL
    assert "refusing drop" in SQL


def test_v069_documents_corrected_scope() -> None:
    assert "model_performance is still read by canary_promoter" in SQL
    assert "feature_baselines and observability.drift_events are kept" in SQL
