from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "sql" / "migrations"


def _read(name: str) -> str:
    return (MIGRATIONS / name).read_text(encoding="utf-8")


V068 = _read("V068__learning_dead_schema_reclassification_guard.sql")
V070 = _read("V070__replay_dead_schema_reclassification_guard.sql")
V071 = _read("V071__learning_dormant_tables_reclassification_guard.sql")


def test_reclassification_guards_are_non_destructive() -> None:
    for sql in (V068, V070, V071):
        lowered = sql.lower()
        assert "drop table" not in lowered
        assert "truncate" not in lowered
        assert "delete from" not in lowered
        assert "cascade" not in lowered
        assert "metadata" in lowered
        assert "no destructive cleanup" in lowered


def test_v068_records_active_learning_and_agent_retention_reasons() -> None:
    expected = (
        "learning.foundation_model_features",
        "learning.weekly_review_log",
        "learning.pattern_insights",
        "learning.experiment_ledger",
        "learning.ml_parameter_suggestions",
        "agent.decision_state_changes",
        "learning.promotion_pipeline",
        "learning.rl_transitions",
        "learning.symbol_clusters",
    )
    for table in expected:
        assert table in V068
    assert "Phase4 weekly review routes read/update" in V068
    assert "V064 Agent Spine decision-store contract" in V068


def test_v070_records_replay_contract_retention_reasons() -> None:
    expected = (
        "replay.handoff_requests",
        "replay.mlde_replay_veto_log",
        "replay.tier_promotion_approval",
        "replay.business_kpi_snapshots",
        "replay.audit_incident_summaries",
    )
    for table in expected:
        assert table in V070
    assert "handoff_routes atomically writes" in V070
    assert "Wave9 business KPI collector" in V070
    assert "Wave9 incident scan" in V070


def test_v071_records_live_or_env_gated_learning_contracts() -> None:
    expected = (
        "learning.cost_edge_advisor_log",
        "learning.ai_usage_log",
        "learning.ai_budget_config",
        "learning.directive_executions",
        "learning.teacher_directives",
    )
    for table in expected:
        assert table in V071
    assert "Rust budget tracker" in V071
    assert "Claude Teacher" in V071
