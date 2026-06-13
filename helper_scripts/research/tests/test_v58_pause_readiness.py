"""Tests for V5.8 pause readiness artifact builder."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from v58_pause_readiness import builder as builder_mod
from v58_pause_readiness import harness as harness_mod


def _write(path: Path, text: str = "placeholder") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _minimal_repo(root: Path) -> Path:
    for spec in (
        builder_mod.REQUIRED_DESIGN_FILES
        + builder_mod.REQUIRED_GOVERNANCE_FILES
        + builder_mod.REQUIRED_SOURCE_SURFACES
    ):
        _write(root / spec.path)
    _write(root / "TODO.md", "P0-EDGE-1 listing fade Gate-B NO-GO active-IMPL 凍結 stage0_ready")
    _write(root / "CHANGELOG.md", "active-IMPL 凍結 stage0_ready")
    _write(
        root / "docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-31--v58_design_progress_preservation_audit.md",
        "active-IMPL frozen 凍結 stage0_ready",
    )
    _write(
        root / "rust/openclaw_engine/src/governance/lal/mod.rs",
        "Tier 2/3/4 transition not implemented defer to Sprint 4+",
    )
    _write(root / "rust/openclaw_engine/tests/m5_model_client_stub_panic.rs", "unimplemented")
    _write(root / "rust/openclaw_engine/tests/m12_order_router_stub.rs", "fail-loud")
    for name in (
        "V099__autonomy_level_config.sql",
        "V100__m4_hypothesis_base_table.sql",
        "V103__extend_m4_hypothesis_columns.sql",
        "V106__health_observations.sql",
        "V107__replay_divergence_log.sql",
        "V109__m8_anomaly_events_hypertable.sql",
        "V112__decision_lease_lal_tiers.sql",
        "V113__governance_audit_log_pg_dump_event_types.sql",
        "V114__notification_failsafe_events_hypertable.sql",
        "V115__panel_basis_panel.sql",
        "V139__agent_memory_store.sql",
    ):
        _write(root / "sql/migrations" / name)
    return root


def _watch(path: Path, status: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "status": status,
        "generated_at_utc": "2026-06-13T00:00:00Z",
        "candidate_counts": {"total": 1, "alertable": 1},
        "candidates": [{
            "symbol": "ABCUSDT",
            "recommended_action": "START_GATE_B_NOW",
            "event_time_utc": "2026-06-13T00:00:00Z",
        }],
    }), encoding="utf-8")
    return path


def test_pause_ready_with_expected_warnings_when_gate_watch_not_attached(tmp_path):
    repo = _minimal_repo(tmp_path / "repo")
    summary = builder_mod.build_summary(repo_root=repo, run_id="r1")

    assert summary["pause_readiness_status"] == "PASS_PAUSE_READY_WITH_WARNINGS"
    assert summary["counts"]["fail"] == 0
    assert summary["unfreeze_gate"]["met"] is False
    assert summary["gate_watch"]["artifact_status"] == "NOT_PROVIDED"
    assert summary["migration_reality"]["original_v58_slots"]


def test_missing_required_design_file_blocks_pause_ready(tmp_path):
    repo = _minimal_repo(tmp_path / "repo")
    (repo / "docs/execution_plan/2026-05-21--m7_decay_enforced_design_spec.md").unlink()

    summary = builder_mod.build_summary(repo_root=repo, run_id="r2")

    assert summary["pause_readiness_status"] == "BLOCKED_MISSING_PAUSE_ASSET"
    assert any(
        row["id"] == "design.m7" and row["status"] == "FAIL"
        for row in summary["checks"]
    )


def test_gate_watch_actionable_is_preserved_in_summary(tmp_path):
    repo = _minimal_repo(tmp_path / "repo")
    watch = _watch(tmp_path / "gate_b_watch_latest.json", "ACTIONABLE_START_NOW")

    summary = builder_mod.build_summary(
        repo_root=repo,
        run_id="r3",
        gate_watch_latest_json=str(watch),
    )

    assert summary["gate_watch"]["artifact_status"] == "ACTIONABLE_START_NOW"
    assert summary["gate_watch"]["operator_action"] == "START_ISOLATED_24H_PROBE"
    assert "aeg_gate_b_probe.py" in summary["gate_watch"]["probe_command_hints"][0]["shell"]


def test_harness_writes_artifact(tmp_path):
    repo = _minimal_repo(tmp_path / "repo")
    result = harness_mod.build_and_write(argparse.Namespace(
        run_id="r4",
        repo_root=str(repo),
        artifact_root=str(tmp_path / "out"),
        gate_watch_latest_json=None,
        session_id=None,
        created_by_role="PM",
    ))

    assert Path(result["written"]["summary"]).exists()
    assert result["summary"]["counts"]["fail"] == 0


def test_static_no_runtime_or_db_route():
    pkg = Path(__file__).resolve().parents[1] / "v58_pause_readiness"
    code = "\n".join(path.read_text(encoding="utf-8") for path in pkg.glob("*.py"))
    forbidden = (
        "psycopg2",
        "asyncpg",
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
        "urlopen",
        "requests.",
        "OPENCLAW_ALLOW_MAINNET",
        "execution_authority",
        "wss://stream.bybit.com",
    )
    for needle in forbidden:
        assert needle not in code
