from __future__ import annotations

import re
from pathlib import Path


_THIS_FILE = Path(__file__).resolve()
_REPO_ROOT = _THIS_FILE.parents[2]
_MIGRATION = _REPO_ROOT / "sql" / "migrations" / "V054__lease_transitions_audit_writer.sql"


def _migration_sql() -> str:
    return _MIGRATION.read_text(encoding="utf-8")


def _strip_sql_comments(sql: str) -> str:
    return re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)


def _normalized_sql() -> str:
    return re.sub(r"\s+", " ", _strip_sql_comments(_migration_sql()).lower())


def test_v054_migration_file_exists() -> None:
    assert _MIGRATION.exists()


def test_v054_is_transactional_and_guarded() -> None:
    sql = _normalized_sql()

    assert "begin; do $$" in sql
    assert "commit;" in sql
    assert "table_schema = 'learning' and table_name = 'governance_audit_log'" in sql
    assert "v054 guard a: learning.governance_audit_log not found" in sql
    assert "table_schema = 'learning' and table_name = 'lease_transitions'" in sql
    for column in ("transition_id", "lease_id", "from_state", "to_state", "event", "ts_ms", "created_at"):
        assert f"'{column}'" in sql


def test_v054_creates_lease_transitions_table_with_constraints() -> None:
    sql = _normalized_sql()

    assert "create table if not exists learning.lease_transitions" in sql
    for column in (
        "transition_id text not null",
        "lease_id text not null",
        "from_state text",
        "to_state text not null",
        "event text not null",
        "initiator text not null",
        "reason_codes text[] not null default array[]::text[]",
        "requires_approval boolean not null default false",
        "approved_by text",
        "profile text not null",
        "engine_mode text not null",
        "context_id text",
        "ts_ms bigint not null",
        "created_at timestamptz not null default now()",
        "primary key (transition_id, created_at)",
    ):
        assert column in sql

    assert "constraint chk_lease_transitions_profile" in sql
    for profile in ("production", "validation", "exploration"):
        assert f"'{profile}'" in sql

    assert "constraint chk_lease_transitions_to_state" in sql
    for state in (
        "draft",
        "registered",
        "active",
        "bridged",
        "frozen",
        "revoked",
        "expired",
        "rejected",
        "consumed",
    ):
        assert f"'{state}'" in sql

    assert "constraint chk_lease_transitions_engine_mode" in sql
    for mode in ("paper", "demo", "live_demo", "live_mainnet", "shadow"):
        assert f"'{mode}'" in sql

    assert "constraint chk_lease_transitions_ts_ms_positive check (ts_ms > 0)" in sql


def test_v054_creates_query_indexes_and_optional_hypertable() -> None:
    sql = _normalized_sql()

    for index_name in (
        "idx_lease_transitions_lease_id_ts",
        "idx_lease_transitions_to_state_profile_ts",
        "idx_lease_transitions_engine_mode_ts",
    ):
        assert f"create index if not exists {index_name}" in sql

    assert "select 1 from pg_extension where extname = 'timescaledb'" in sql
    assert "create_hypertable(" in sql
    assert "'learning.lease_transitions'" in sql
    assert "'created_at'" in sql
    assert "if_not_exists => true" in sql


def test_v054_extends_governance_audit_event_type_check() -> None:
    sql = _normalized_sql()

    assert "lock table learning.governance_audit_log in access exclusive mode" in sql
    assert "drop constraint if exists governance_audit_log_event_type_check" in sql
    assert "add constraint governance_audit_log_event_type_check" in sql

    for event_type in (
        "review_live_candidate",
        "lease_grant",
        "lease_auto_revoke",
        "bulk_re_evaluation",
        "audit_write_failed",
        "replay_handoff_request",
        "replay_run_started",
        "replay_run_cancelled",
        "replay_manifest_verify_attempted",
        "replay_signature_test_key_blocked",
        "replay_pid_identity_mismatch",
        "replay_idor_admin_bypass",
        "replay_artifact_path_traversal_blocked",
        "replay_argv_mismatch_blocked",
        "lease_acquire_fail",
        "lease_acquire_request",
        "lease_acquire_success",
        "lease_release_cancelled",
        "lease_release_consumed",
        "lease_release_failed",
        "lease_sm_transition",
    ):
        assert f"'{event_type}'" in sql
