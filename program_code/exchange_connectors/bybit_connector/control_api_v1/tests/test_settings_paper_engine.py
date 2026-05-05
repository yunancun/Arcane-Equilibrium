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
