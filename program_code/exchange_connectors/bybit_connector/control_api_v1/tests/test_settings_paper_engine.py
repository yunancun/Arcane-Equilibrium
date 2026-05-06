from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


_TEST_DIR = Path(__file__).resolve().parent
_CONTROL_API_DIR = _TEST_DIR.parent
if str(_CONTROL_API_DIR) not in sys.path:
    sys.path.insert(0, str(_CONTROL_API_DIR))

from app.settings_routes import (  # noqa: E402
    _get_auth_actor,
    _require_operator_auth,
    settings_router,
)


class _Actor:
    actor_id = "settings-test"
    roles = {"operator", "viewer"}


def _client(tmp_path: Path, monkeypatch) -> tuple[TestClient, Path]:
    env_file = tmp_path / "environment_files" / "basic_system_services.env"
    monkeypatch.setenv("OPENCLAW_BASIC_SYSTEM_ENV_FILE", str(env_file))
    monkeypatch.delenv("OPENCLAW_ENABLE_PAPER", raising=False)
    monkeypatch.delenv("OPENCLAW_DEVELOPMENT_SUPPORT_MODE", raising=False)
    monkeypatch.delenv("OPENCLAW_GUI_DEVELOPMENT_MODE", raising=False)

    app = FastAPI()
    app.include_router(settings_router)
    app.dependency_overrides[_get_auth_actor] = lambda: _Actor()
    app.dependency_overrides[_require_operator_auth] = lambda: _Actor()
    return TestClient(app), env_file


def test_paper_engine_defaults_disabled(tmp_path: Path, monkeypatch) -> None:
    client, _ = _client(tmp_path, monkeypatch)

    resp = client.get("/api/v1/settings/paper-engine")

    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is False
    assert data["runtime_enabled"] is False
    assert data["restart_required"] is False
    assert data["source"] == "default_disabled"


def test_paper_engine_post_persists_env_file(tmp_path: Path, monkeypatch) -> None:
    client, env_file = _client(tmp_path, monkeypatch)

    resp = client.post("/api/v1/settings/paper-engine", json={"enabled": True})

    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert data["source"] == "env_file"
    assert "OPENCLAW_ENABLE_PAPER=1" in env_file.read_text(encoding="utf-8")
    assert oct(os.stat(env_file).st_mode & 0o777) == "0o600"


def test_paper_engine_reports_restart_required_when_runtime_differs(
    tmp_path: Path, monkeypatch,
) -> None:
    client, _ = _client(tmp_path, monkeypatch)
    monkeypatch.setenv("OPENCLAW_ENABLE_PAPER", "0")

    resp = client.post("/api/v1/settings/paper-engine", json={"enabled": True})

    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert data["runtime_enabled"] is False
    assert data["restart_required"] is True


def test_development_mode_defaults_disabled(tmp_path: Path, monkeypatch) -> None:
    client, _ = _client(tmp_path, monkeypatch)

    resp = client.get("/api/v1/settings/development-mode")

    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is False
    assert data["restart_required"] is False
    assert data["source"] == "default_disabled"
    assert data["scope"] == "development_support_visibility_only"
    assert data["surface"] == "global_development_status_support"


def test_development_mode_post_persists_support_env_file(
    tmp_path: Path, monkeypatch,
) -> None:
    client, env_file = _client(tmp_path, monkeypatch)

    resp = client.post("/api/v1/settings/development-mode", json={"enabled": True})

    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert data["restart_required"] is False
    assert "OPENCLAW_DEVELOPMENT_SUPPORT_MODE=1" in env_file.read_text(encoding="utf-8")
    assert oct(os.stat(env_file).st_mode & 0o777) == "0o600"


def test_development_status_scans_repo_migrations_dynamically(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    migrations = repo / "sql" / "migrations"
    migrations.mkdir(parents=True)
    (migrations / "V001__create_alpha.sql").write_text(
        "-- V001__create_alpha.sql\n"
        "-- ================================================================\n"
        "-- Purpose: create alpha schema for development status tests.\n"
        "-- ---------------------------------------------------------------\n"
        "CREATE SCHEMA IF NOT EXISTS alpha;\n",
        encoding="utf-8",
    )
    (migrations / "V003__create_beta.sql").write_text(
        "-- V003__create_beta.sql\n"
        "-- Purpose: create beta table.\n"
        "CREATE TABLE IF NOT EXISTS beta.items (id INT PRIMARY KEY);\n",
        encoding="utf-8",
    )
    (migrations / "V003_healthcheck.sql").write_text(
        "-- companion\n",
        encoding="utf-8",
    )
    (repo / "TODO.md").write_text("# TODO\n\n- next thing\n", encoding="utf-8")
    agenttodo = repo / "docs" / "architecture" / "multi_agent_rework_2026-05-05"
    agenttodo.mkdir(parents=True)
    (agenttodo / "AgentTodo.md").write_text("# AgentTodo\n\nMAG-001\n", encoding="utf-8")
    reports = repo / "docs" / "CCAgentWorkSpace" / "PM" / "workspace" / "reports"
    reports.mkdir(parents=True)
    (reports / "2026-05-06--sample_report.md").write_text("# sample\n", encoding="utf-8")

    monkeypatch.setenv("OPENCLAW_BASE_DIR", str(repo))
    client, _ = _client(tmp_path, monkeypatch)

    resp = client.get("/api/v1/settings/development-status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["repo_root"] == str(repo.resolve())
    assert data["migrations"]["landed_count"] == 2
    assert data["migrations"]["companion_count"] == 1
    assert "V002" in data["migrations"]["gap_versions"]
    assert data["migrations"]["next_version"] == "V004"
    items = {row["id"]: row for row in data["migrations"]["items"]}
    assert items["V001"]["purpose"] == "create alpha schema for development status tests."
    assert items["V001"]["action_counts"]["create_schema"] == 1
    assert items["V001"]["header_excerpt"][0] == "V001__create_alpha.sql"
    assert not any(set(line) <= {"=", "-", "_", " "} for line in items["V001"]["header_excerpt"])
    assert items["V001"]["size_bytes"] > 0
    assert "beta.items" in items["V003"]["objects"]
    assert items["V003"]["action_counts"]["create_table"] == 1
    assert items["V003"]["companions"] == ["V003_healthcheck.sql"]
    assert items["V003"]["companion_count"] == 1
    assert data["development_context"]["todo_excerpt"][0] == "# TODO"
    assert data["documentation"]["index_files"]["document_inventory_present"] is False
    assert data["documentation"]["live_counts"]["docs_markdown"] >= 2
    assert data["documentation"]["inventory"]["gui_hot_candidates"]["high"][0]["path"] == "TODO.md"
