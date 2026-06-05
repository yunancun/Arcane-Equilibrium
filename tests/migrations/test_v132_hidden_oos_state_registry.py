from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "sql/migrations/V132__hidden_oos_state_registry.sql"


def test_v132_creates_hidden_oos_state_registry():
    sql = MIGRATION.read_text()
    assert "CREATE TABLE IF NOT EXISTS learning.hidden_oos_state_registry" in sql
    assert "replay_experiment_id             UUID        NOT NULL" in sql
    assert "state_jsonb                      JSONB       NOT NULL" in sql
    assert "UNIQUE (replay_experiment_id)" in sql
    assert "UNIQUE (family_id, split_hash)" in sql


def test_v132_enforces_state_machine_flags():
    sql = MIGRATION.read_text()
    assert "hidden_oos_state_registry_state_flags_chk" in sql
    assert "state = 'sealed'" in sql
    assert "state = 'consumed'" in sql
    assert "open_count > 0" in sql
    assert "consumed IS TRUE" in sql
    assert "invalidated IS TRUE" in sql


def test_v132_has_guards_and_audit_comment():
    sql = MIGRATION.read_text()
    assert "V132 Guard A FAIL" in sql
    assert "V132 Guard B FAIL" in sql
    assert "V132 Guard C FAIL" in sql
    assert "Audit evidence only, not promotion authority" in sql
    assert "add_retention_policy" not in sql
    assert "drop_chunks" not in sql
