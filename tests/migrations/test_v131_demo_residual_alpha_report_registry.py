from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "sql/migrations/V131__demo_residual_alpha_report_registry.sql"


def test_v131_creates_durable_residual_alpha_report_registry():
    sql = MIGRATION.read_text()
    assert "CREATE TABLE IF NOT EXISTS learning.demo_residual_alpha_reports" in sql
    assert "report_hash           TEXT        NOT NULL" in sql
    assert "report_jsonb          JSONB       NOT NULL" in sql
    assert "UNIQUE (strategy_name, engine_mode, report_hash)" in sql
    assert "idx_demo_residual_alpha_reports_hash" in sql
    assert "does not authorize promotion by itself" in sql


def test_v131_links_latest_hash_without_storing_report_body_on_pipeline():
    sql = MIGRATION.read_text()
    assert "ADD COLUMN IF NOT EXISTS demo_residual_alpha_report_hash TEXT" in sql
    before_table = sql.split(
        "CREATE TABLE IF NOT EXISTS learning.demo_residual_alpha_reports", 1
    )[0]
    assert "demo_residual_alpha_report JSONB" not in before_table


def test_v131_has_shape_type_and_index_guards():
    sql = MIGRATION.read_text()
    assert "V131 Guard A FAIL" in sql
    assert "V131 Guard B FAIL" in sql
    assert "V131 Guard C FAIL" in sql
    assert "jsonb_typeof(report_jsonb) = 'object'" in sql
    assert "report_hash ~ '^[0-9a-f]{64}$'" in sql
