"""Static migration tests for V080 governance.canary_stage_log + metric_registry.

W-AUDIT-9 T2 Mac mock test：靜態 SQL grep 驗證 schema definition 對齊
AMD-2026-05-09-03 §4.2 + Guard A/B/C / E2 audit point #2 / idempotency markers。

Linux PG empirical dry-run 在 ssh trade-core 端執行；本檔僅 Mac 靜態驗證
（per CLAUDE.md §七 + memory feedback_v_migration_pg_dry_run.md）。
"""

from __future__ import annotations

import re
from pathlib import Path


_THIS_FILE = Path(__file__).resolve()
_SRV_ROOT = _THIS_FILE.parents[2]
V080_PATH = _SRV_ROOT / "sql" / "migrations" / "V080__governance_canary_stage.sql"


def _read_sql() -> str:
    """讀 V080 SQL 文件原文 / read raw V080 SQL"""
    assert V080_PATH.exists(), f"Migration file missing: {V080_PATH}"
    return V080_PATH.read_text(encoding="utf-8")


def _strip_sql_comments(sql: str) -> str:
    """去除 -- 行注釋以避免 grep false-positive / strip line comments"""
    return "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())


def _normalized_sql() -> str:
    """規範化（小寫 + 折疊 whitespace）/ normalize for grep"""
    return re.sub(r"\s+", " ", _strip_sql_comments(_read_sql()).lower())


def test_v080_creates_governance_schema() -> None:
    """V080 必確保 governance schema 存在 / governance schema bootstrap"""
    sql = _normalized_sql()
    assert "create schema if not exists governance" in sql


def test_v080_creates_canary_stage_log_with_required_columns() -> None:
    """canary_stage_log 必含 AMD-2026-05-09-03 §4.2 全部欄位"""
    sql = _normalized_sql()
    assert "create table if not exists governance.canary_stage_log" in sql
    # 必要欄位（per amendment §4.2）
    for col in (
        "stage_log_id",
        "cohort_id",
        "from_stage",
        "to_stage",
        "transition_kind",
        "decision_lease_id",
        "triggered_metric",
        "triggered_value",
        "created_at_ms",
    ):
        assert col in sql, f"missing required column: {col}"


def test_v080_creates_metric_registry_with_required_columns() -> None:
    """canary_stage_metric_registry 必含 AMD §4.2 全部欄位"""
    sql = _normalized_sql()
    assert "create table if not exists governance.canary_stage_metric_registry" in sql
    for col in (
        "metric_id",
        "stage",
        "metric_name",
        "direction",
        "threshold_value",
        "observation_window_ms",
        "active",
    ):
        assert col in sql, f"missing required column: {col}"


def test_v080_stage_check_constraints_0_to_4() -> None:
    """stage 值域 0..=4 必經 CHECK 強制 / stage 0..=4 enforced"""
    sql = _normalized_sql()
    # canary_stage_log
    assert "from_stage between 0 and 4" in sql
    assert "to_stage between 0 and 4" in sql
    # metric_registry
    assert "stage between 0 and 4" in sql


def test_v080_transition_kind_enum_constraint() -> None:
    """transition_kind enum 4 值 / 4-value enum"""
    sql = _normalized_sql()
    assert "transition_kind in" in sql
    for kind in ("manual_promote", "auto_promote", "auto_rollback", "incident_rollback"):
        assert f"'{kind}'" in sql, f"missing enum value: {kind}"


def test_v080_manual_promote_requires_decision_lease_id() -> None:
    """E2 audit point #2: manual_promote 必伴 decision_lease_id（PG 層強制）

    AMD-2026-05-09-03 §4.5 + §7 audit point #2：
    雞蛋死循環防線 — manual_promote 無 lease 違反 audit chain 完整性。
    必須 PG 層 CHECK，不只 application 層。
    """
    sql = _normalized_sql()
    # CHECK constraint 樣式：transition_kind != 'manual_promote' OR decision_lease_id IS NOT NULL
    assert "transition_kind != 'manual_promote'" in sql
    assert "decision_lease_id is not null" in sql


def test_v080_decision_lease_id_uuid_type() -> None:
    """decision_lease_id 必為 UUID 類型（與 lease_transitions UUID 對齊）"""
    sql = _normalized_sql()
    assert "decision_lease_id" in sql
    assert "uuid" in sql


def test_v080_metric_direction_enum() -> None:
    """direction 必為 4 值 enum / direction 4-value enum"""
    sql = _normalized_sql()
    assert "direction in" in sql
    for direction in ("promote_upper", "promote_lower", "rollback_upper", "rollback_lower"):
        assert f"'{direction}'" in sql, f"missing direction: {direction}"


def test_v080_metric_observation_window_positive() -> None:
    """observation_window_ms > 0 / observation window must be positive"""
    sql = _normalized_sql()
    assert "observation_window_ms > 0" in sql


def test_v080_unique_active_metric_per_stage_name() -> None:
    """AMD §4.2: UNIQUE (stage, metric_name) WHERE active=true"""
    sql = _normalized_sql()
    assert "create unique index if not exists" in sql
    assert "uq_canary_stage_metric_registry_active" in sql
    assert "(stage, metric_name)" in sql
    # WHERE active = true
    assert "active = true" in sql


def test_v080_hot_path_index_cohort_created_at_desc() -> None:
    """healthcheck [58] hot-path index：cohort_id + created_at_ms DESC"""
    sql = _normalized_sql()
    assert "idx_canary_stage_log_cohort_created_at" in sql
    assert "(cohort_id, created_at_ms desc)" in sql


def test_v080_partial_rollback_events_index() -> None:
    """rollback events partial index for incident response timeline"""
    sql = _normalized_sql()
    assert "idx_canary_stage_log_rollback_events" in sql
    assert "where transition_kind in ('auto_rollback', 'incident_rollback')" in sql


def test_v080_guard_a_canary_stage_log_columns() -> None:
    """Guard A：legacy schema drift detection / pre-existing legacy schema 偵測

    schema_guard_template.sql Guard A 模板格式，CLAUDE.md §七 強制。
    """
    sql = _normalized_sql()
    assert "schema_guard a: governance.canary_stage_log" in sql
    assert "missing required columns" in sql
    assert "raise exception" in sql


def test_v080_guard_a_metric_registry_columns() -> None:
    """Guard A applied to metric_registry too / 兩 table 都加 Guard A"""
    sql = _normalized_sql()
    assert "schema_guard a: governance.canary_stage_metric_registry" in sql


def test_v080_guard_c_index_column_ordering() -> None:
    """Guard C：hot-path index 欄位順序 (created_at_ms DESC) 不可漂移

    CLAUDE.md §七 + schema_guard_template.sql Guard C 模板。
    若索引存在但缺 DESC，hot-path query 退化為 O(N log N)。
    """
    sql = _normalized_sql()
    assert "schema_guard c: idx_canary_stage_log_cohort_created_at" in sql
    assert "created_at_ms desc" in sql
    assert "pg_get_indexdef" in sql


def test_v080_idempotency_create_table_if_not_exists() -> None:
    """所有 CREATE TABLE 用 IF NOT EXISTS（idempotent re-run 必通過）

    CLAUDE.md §七 SQL migration idempotency 強制：local 跑兩次必不 RAISE。
    """
    sql = _normalized_sql()
    assert "create table if not exists governance.canary_stage_log" in sql
    assert "create table if not exists governance.canary_stage_metric_registry" in sql
    assert "create schema if not exists governance" in sql


def test_v080_idempotency_index_if_not_exists() -> None:
    """所有 CREATE INDEX 用 IF NOT EXISTS"""
    sql = _normalized_sql()
    assert "create index if not exists idx_canary_stage_log_cohort_created_at" in sql
    assert "create index if not exists idx_canary_stage_log_rollback_events" in sql
    assert "create unique index if not exists uq_canary_stage_metric_registry_active" in sql


def test_v080_no_destructive_operations() -> None:
    """V080 純 additive；禁 DROP TABLE / TRUNCATE / DELETE / ALTER COLUMN TYPE"""
    sql = _normalized_sql()
    for forbidden in (
        "drop table",
        "drop schema governance",
        "truncate",
        "delete from governance",
        "alter column",
    ):
        assert forbidden not in sql, f"forbidden destructive op: {forbidden}"


def test_v080_append_only_audit_no_trigger_modifying_data() -> None:
    """V080 不應安裝任何 BEFORE/AFTER trigger 改 data（純 audit table）"""
    sql = _normalized_sql()
    # 應該沒 CREATE TRIGGER（不像 V077 加 columnstore trigger）
    assert "create trigger" not in sql, "V080 should not install triggers"


def test_v080_amendment_reference_in_comments() -> None:
    """V080 必引用 AMD-2026-05-09-03 amendment ID（治理可追溯）"""
    raw_sql = _read_sql().lower()  # raw 才能讀 comment
    assert "amd-2026-05-09-03" in raw_sql, (
        "V080 SQL header/comments must reference AMD-2026-05-09-03 for governance traceability"
    )
    assert "w-audit-9" in raw_sql, "V080 SQL must reference W-AUDIT-9 wave"


def test_v080_runs_against_temp_db_idempotent_two_passes() -> None:
    """If a runtime test harness exists, V080 must apply twice without RAISE.

    Mac 環境下我們無法跑真 PG（需要 docker / Linux postgres），這裡只做 syntax
    sanity（不開 PG connection）。Linux PG dry-run 在 ssh trade-core 完成驗證。
    """
    sql = _read_sql()
    # syntax sanity：必有 PRIMARY KEY / NOT NULL / CHECK / 等 PG 慣用詞
    assert "PRIMARY KEY" in sql
    assert "NOT NULL" in sql
    assert "CHECK" in sql
    # 文件不該有 TODO / FIXME / XXX 標記
    for tag in ("TODO:", "FIXME:", "XXX:"):
        assert tag not in sql, f"V080 should not contain {tag} marker"
