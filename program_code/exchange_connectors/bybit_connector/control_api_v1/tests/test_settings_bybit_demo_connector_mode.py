from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


_TEST_DIR = Path(__file__).resolve().parent
_CONTROL_API_DIR = _TEST_DIR.parent
if str(_CONTROL_API_DIR) not in sys.path:
    sys.path.insert(0, str(_CONTROL_API_DIR))

from app import settings_routes  # noqa: E402


class _Actor:
    actor_id = "bybit-demo-connector-mode-test"
    roles = {"operator", "viewer"}


def _client(tmp_path: Path, monkeypatch) -> tuple[TestClient, Path]:
    env_file = tmp_path / "environment_files" / "trading_services.env"
    monkeypatch.setenv("OPENCLAW_TRADING_SERVICES_ENV_FILE", str(env_file))
    monkeypatch.delenv("BYBIT_MODE", raising=False)
    monkeypatch.delenv("BYBIT_CONNECTOR_WRITE_ENABLED", raising=False)

    app = FastAPI()
    app.include_router(settings_routes.settings_router)
    app.dependency_overrides[settings_routes._get_auth_actor] = lambda: _Actor()
    app.dependency_overrides[settings_routes._require_operator_auth] = lambda: _Actor()
    return TestClient(app), env_file


def _write_preflight(
    path: Path,
    *,
    env_file: Path,
    answers: dict | None = None,
) -> tuple[Path, str]:
    safe_answers = {
        "connector_env_cutover_preview_only": True,
        "secret_write_performed": False,
        "env_mutation_performed": False,
        "runtime_mutation_performed": False,
        "service_restart_performed": False,
        "order_capable_action_allowed_by_this_packet": False,
        "order_submission_performed": False,
        "decision_lease_acquire_performed": False,
        "bybit_private_call_performed": False,
        "bybit_credential_validation_call_performed": False,
        "live_or_mainnet": False,
        "live_authority_granted": False,
        "global_cost_gate_lowering_recommended": False,
        "writer_enabled_by_this_packet": False,
        "adapter_enabled_by_this_packet": False,
        "promotion_evidence": False,
        "promotion_proof": False,
        "main_cost_gate_adjustment": "NONE",
    }
    if answers:
        safe_answers.update(answers)
    payload = {
        "schema_version": settings_routes._CUTOVER_PREFLIGHT_SCHEMA_VERSION,
        "status": settings_routes._CUTOVER_PREFLIGHT_READY_STATUS,
        "answers": safe_answers,
        "settings_api_source": {
            "ready": True,
            "requires_operator_role": True,
        },
        "connector_env_cutover": {
            "status": "READY",
            "ready": True,
            "path": str(env_file),
            "proposed_demo_only": {
                "BYBIT_MODE": "demo",
                "BYBIT_CONNECTOR_WRITE_ENABLED": "true",
            },
        },
    }
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    return path, sha


def _post_body(preflight_path: Path, preflight_sha: str) -> dict:
    return {
        "cutover_preflight_json": str(preflight_path),
        "cutover_preflight_sha256": preflight_sha,
        "confirm": settings_routes._BYBIT_DEMO_CONNECTOR_MODE_CONFIRM,
    }


def test_bybit_demo_connector_mode_defaults_disabled(tmp_path: Path, monkeypatch) -> None:
    client, env_file = _client(tmp_path, monkeypatch)

    resp = client.get("/api/v1/settings/bybit-demo-connector-mode")

    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is False
    assert data["configured_ready"] is False
    assert data["runtime_ready"] is False
    assert data["restart_required"] is False
    assert data["env_file"] == str(env_file)
    assert data["boundary"]["demo_only"] is True
    assert data["boundary"]["order_capable_action_allowed_by_this_packet"] is False


def test_bybit_demo_connector_mode_post_persists_demo_only_env(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, env_file = _client(tmp_path, monkeypatch)
    env_file.parent.mkdir(parents=True)
    env_file.write_text(
        "BYBIT_MODE=read_only\n"
        "BYBIT_CONNECTOR_WRITE_ENABLED=false\n"
        "UNRELATED=kept\n",
        encoding="utf-8",
    )
    preflight_path, preflight_sha = _write_preflight(
        tmp_path / "cutover_preflight.json",
        env_file=env_file,
    )

    resp = client.post(
        "/api/v1/settings/bybit-demo-connector-mode",
        json=_post_body(preflight_path, preflight_sha),
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["saved"] is True
    assert data["configured_ready"] is True
    assert data["runtime_ready"] is False
    assert data["restart_required"] is True
    assert data["cutover_preflight"]["sha256"] == preflight_sha
    assert data["answers"]["env_mutation_performed"] is True
    assert data["answers"]["service_restart_performed"] is False
    text = env_file.read_text(encoding="utf-8")
    assert "BYBIT_MODE=demo" in text
    assert "BYBIT_CONNECTOR_WRITE_ENABLED=true" in text
    assert "UNRELATED=kept" in text
    assert oct(os.stat(env_file).st_mode & 0o777) == "0o600"


def test_bybit_demo_connector_mode_rejects_wrong_preflight_sha(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, env_file = _client(tmp_path, monkeypatch)
    env_file.parent.mkdir(parents=True)
    env_file.write_text("BYBIT_MODE=read_only\n", encoding="utf-8")
    preflight_path, _ = _write_preflight(tmp_path / "cutover_preflight.json", env_file=env_file)

    resp = client.post(
        "/api/v1/settings/bybit-demo-connector-mode",
        json=_post_body(preflight_path, "0" * 64),
    )

    assert resp.status_code == 400
    assert "BYBIT_MODE=read_only" in env_file.read_text(encoding="utf-8")
    assert "BYBIT_CONNECTOR_WRITE_ENABLED=true" not in env_file.read_text(encoding="utf-8")


def test_bybit_demo_connector_mode_rejects_authority_contamination(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, env_file = _client(tmp_path, monkeypatch)
    env_file.parent.mkdir(parents=True)
    env_file.write_text("BYBIT_MODE=read_only\n", encoding="utf-8")
    preflight_path, preflight_sha = _write_preflight(
        tmp_path / "cutover_preflight.json",
        env_file=env_file,
        answers={"order_submission_performed": True},
    )

    resp = client.post(
        "/api/v1/settings/bybit-demo-connector-mode",
        json=_post_body(preflight_path, preflight_sha),
    )

    assert resp.status_code == 400
    data = resp.json()
    assert "unsafe or missing answer flags" in data["detail"]
    assert "BYBIT_MODE=read_only" in env_file.read_text(encoding="utf-8")


def test_bybit_demo_connector_mode_rejects_wrong_confirmation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, env_file = _client(tmp_path, monkeypatch)
    env_file.parent.mkdir(parents=True)
    env_file.write_text("BYBIT_MODE=read_only\n", encoding="utf-8")
    preflight_path, preflight_sha = _write_preflight(
        tmp_path / "cutover_preflight.json",
        env_file=env_file,
    )
    body = _post_body(preflight_path, preflight_sha)
    body["confirm"] = "wrong"

    resp = client.post("/api/v1/settings/bybit-demo-connector-mode", json=body)

    assert resp.status_code == 400
    assert "BYBIT_MODE=read_only" in env_file.read_text(encoding="utf-8")
