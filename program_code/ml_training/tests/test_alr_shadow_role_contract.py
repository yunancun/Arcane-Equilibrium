from __future__ import annotations

from pathlib import Path


def test_role_contract_is_least_privilege_and_has_no_credential_creation() -> None:
    root = Path(__file__).resolve().parents[3]
    text = (root / "sql/contracts/alr_shadow_role_contract_v1.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE ROLE" not in text
    assert "PASSWORD" not in text
    assert "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT" in text
    assert "REVOKE ALL PRIVILEGES ON DATABASE trading_ai FROM alr_shadow" in text
    assert "GRANT CONNECT ON DATABASE trading_ai TO alr_shadow" in text
    assert "GRANT SELECT ON TABLE trading.scanner_snapshots TO alr_shadow" in text
    assert "GRANT SELECT, INSERT ON TABLE learning.alr_source_events TO alr_shadow" in text
    assert "GRANT SELECT, INSERT ON TABLE learning.alr_training_runs TO alr_shadow" in text
    assert "GRANT SELECT, INSERT ON TABLE learning.alr_outcome_feedback_events TO alr_shadow" in text
    assert "GRANT SELECT, INSERT ON TABLE learning.alr_health_events TO alr_shadow" in text
    assert "GRANT SELECT, INSERT ON TABLE learning.alr_consumer_events TO alr_shadow" in text
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE learning.alr_derived_cache_entries TO alr_shadow" in text
    assert "GRANT UPDATE ON TABLE learning.alr_" not in text
    assert "GRANT DELETE ON TABLE learning.alr_" not in text
