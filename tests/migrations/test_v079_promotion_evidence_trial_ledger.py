from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "sql/migrations/V079__promotion_evidence_trial_ledger.sql"


def test_v079_adds_promotion_evidence_report_columns():
    sql = MIGRATION.read_text()
    assert "ADD COLUMN IF NOT EXISTS demo_selection_bias_report JSONB" in sql
    assert "ADD COLUMN IF NOT EXISTS demo_tail_risk_report JSONB" in sql
    assert "current_stage" not in sql.split("CREATE TABLE", 1)[0].lower()


def test_v079_creates_strategy_trial_ledger_for_persisted_trial_sharpes():
    sql = MIGRATION.read_text()
    assert "CREATE TABLE IF NOT EXISTS learning.strategy_trial_ledger" in sql
    assert "observed_sharpe DOUBLE PRECISION NOT NULL" in sql
    assert "n_observations  INTEGER     NOT NULL" in sql
    assert "idx_strategy_trial_ledger_strategy_mode_ts" in sql
    assert "does not authorize promotion by itself" in sql
