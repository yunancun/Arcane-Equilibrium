"""Static migration tests for REF-21 V057-V060 governance bootstrap.

REF-21 V057-V060 governance bootstrap migration 的靜態測試。

Mac dev does not run psql here. The test verifies that V057-V060 are real
migration files with the structural contracts that V1.3 only had as sketches.
Linux MIT dry-run remains the runtime gate.
"""

from __future__ import annotations

import re
from pathlib import Path


_THIS_FILE = Path(__file__).resolve()
_SRV_ROOT = _THIS_FILE.parents[2]
_MIGRATIONS_DIR = _SRV_ROOT / "sql" / "migrations"

V057_PATH = _MIGRATIONS_DIR / "V057__replay_tier_promotion_approval.sql"
V058_PATH = _MIGRATIONS_DIR / "V058__symbol_universe_and_strategy_freeze_log.sql"
V059_PATH = _MIGRATIONS_DIR / "V059__edge_estimate_snapshots.sql"
V060_PATH = _MIGRATIONS_DIR / "V060__replay_emergency_audit_log.sql"


def _read_sql(path: Path) -> str:
    assert path.exists(), f"Migration file missing: {path}"
    return path.read_text(encoding="utf-8")


def _strip_sql_comments(sql: str) -> str:
    return "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())


def test_v057_tier_promotion_approval_has_hmac_signature_contract() -> None:
    sql = _strip_sql_comments(_read_sql(V057_PATH))
    assert "CREATE TYPE replay.replay_evidence_tier_v057 AS ENUM" in sql
    for tier in (
        "synthetic_replay",
        "s2_public_replay",
        "s2_oos_replay",
        "s1_calibrated_replay",
        "verified_replay_advisory",
        "legacy_calibrated_replay_pending_review",
        "legacy_counterfactual_replay_pending_review",
    ):
        assert f"'{tier}'" in sql
    assert "CREATE TABLE IF NOT EXISTS replay.tier_promotion_approval" in sql
    assert "signature_scheme TEXT NOT NULL DEFAULT 'hmac_sha256_v1'" in sql
    assert "octet_length(approval_signature) = 32" in sql
    assert "UNIQUE (report_id, from_tier, to_tier, approver_role)" in sql
    assert "replay.calculate_promotion_metrics" not in sql
    assert "V057 Guard A" in sql
    assert "V057 Guard B" in sql
    assert "V057 Guard C" in sql
    assert "REVOKE INSERT, UPDATE, DELETE ON replay.tier_promotion_approval FROM PUBLIC" in sql
    assert "idx_tier_promotion_approval_report" in sql


def test_v058_creates_governance_freeze_log_and_symbol_universe() -> None:
    sql = _strip_sql_comments(_read_sql(V058_PATH))
    assert "CREATE SCHEMA IF NOT EXISTS governance" in sql
    assert "CREATE TABLE IF NOT EXISTS governance.strategy_freeze_log" in sql
    assert "freeze_tag TEXT NOT NULL UNIQUE" in sql
    assert "strategy_git_sha TEXT NOT NULL" in sql
    assert "CREATE TABLE IF NOT EXISTS market.symbol_universe_snapshots" in sql
    assert "PRIMARY KEY (ts, exchange, category, symbol)" in sql
    assert "is_delisted_at_asof BOOLEAN NOT NULL DEFAULT false" in sql
    assert "V058 Guard A" in sql
    assert "V058 Guard B" in sql
    assert "V058 Guard C" in sql
    assert "REVOKE UPDATE, DELETE ON governance.strategy_freeze_log FROM PUBLIC" in sql
    assert "REVOKE UPDATE, DELETE ON market.symbol_universe_snapshots FROM PUBLIC" in sql


def test_v059_edge_snapshot_has_deprecated_flag_and_retention_floor() -> None:
    sql = _strip_sql_comments(_read_sql(V059_PATH))
    assert "CREATE TABLE IF NOT EXISTS learning.edge_estimate_snapshots" in sql
    assert "is_deprecated_at_asof BOOLEAN NOT NULL DEFAULT false" in sql
    assert "deprecated_reason TEXT" in sql
    assert "retention_until TIMESTAMPTZ NOT NULL" in sql
    assert "retention_until >= asof_ts + INTERVAL '75 days'" in sql
    assert "idx_edge_estimate_snapshots_deprecated" in sql
    assert "V059 Guard A" in sql
    assert "V059 Guard B" in sql
    assert "V059 Guard C" in sql
    assert "REVOKE UPDATE, DELETE ON learning.edge_estimate_snapshots FROM PUBLIC" in sql


def test_v060_replay_emergency_log_creates_audit_and_governance_schema() -> None:
    sql = _strip_sql_comments(_read_sql(V060_PATH))
    assert "CREATE SCHEMA IF NOT EXISTS audit" in sql
    assert "CREATE SCHEMA IF NOT EXISTS governance" in sql
    assert "CREATE TABLE IF NOT EXISTS audit.replay_emergency_log" in sql
    assert "route TEXT NOT NULL CHECK (route = '/api/v1/replay/full-chain/prepare')" in sql
    assert "bulk_prod_ip_allowed BOOLEAN NOT NULL DEFAULT false" in sql
    assert "request_count INTEGER NOT NULL CHECK (request_count >= 0)" in sql
    assert "REVOKE UPDATE, DELETE ON audit.replay_emergency_log FROM PUBLIC" in sql
    assert "V060 Guard A" in sql
    assert "V060 Guard B" in sql
    assert "V060 Guard C" in sql
    assert "idx_replay_emergency_log_ts" in sql
    assert "idx_replay_emergency_log_actor_ts" in sql


def test_v057_v060_guard_c_checks_public_write_grants_and_indexes() -> None:
    """Guard C must verify runtime privileges and hot-path indexes.

    Guard C 必須驗 runtime 權限與 hot-path index，不能只靠註釋承諾。
    """
    for path in (V057_PATH, V058_PATH, V059_PATH, V060_PATH):
        sql = _strip_sql_comments(_read_sql(path))
        assert "information_schema.role_table_grants" in sql, path.name
        assert "grantee = 'PUBLIC'" in sql, path.name
        assert "privilege_type IN" in sql, path.name
        assert "FROM pg_indexes" in sql, path.name
