from __future__ import annotations

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
    actor_id = "api-key-status-test"
    roles = {"operator", "viewer"}


def _client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("OPENCLAW_SECRETS_DIR", str(tmp_path / "secrets"))
    app = FastAPI()
    app.include_router(settings_routes.settings_router)
    app.dependency_overrides[settings_routes._get_auth_actor] = lambda: _Actor()
    app.dependency_overrides[settings_routes._require_operator_auth] = lambda: _Actor()
    return TestClient(app)


def _write_credentials(tmp_path: Path, slot: str = "demo") -> None:
    slot_dir = tmp_path / "secrets" / slot
    slot_dir.mkdir(parents=True)
    (slot_dir / "api_key").write_text("DEMOAPIKEY1234", encoding="utf-8")
    (slot_dir / "api_secret").write_text("DEMOSECRET5678", encoding="utf-8")


def test_api_key_status_unconfigured_skips_validation(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    def _fail_if_called(api_key: str, api_secret: str, slot: str) -> tuple[bool, str]:
        raise AssertionError("validation should not run without stored credentials")

    monkeypatch.setattr(settings_routes, "_validate_bybit_credentials", _fail_if_called)

    resp = client.get("/api/v1/settings/api-key/demo?validate=1")

    assert resp.status_code == 200
    data = resp.json()
    assert data["has_key"] is False
    assert data["validated"] is False
    assert data["validation_status"] == "not_configured"
    assert data["validation_error"] == ""


def test_api_key_status_validate_success(tmp_path: Path, monkeypatch) -> None:
    _write_credentials(tmp_path)
    client = _client(tmp_path, monkeypatch)

    def _valid(api_key: str, api_secret: str, slot: str) -> tuple[bool, str]:
        assert api_key == "DEMOAPIKEY1234"
        assert api_secret == "DEMOSECRET5678"
        assert slot == "demo"
        return True, ""

    monkeypatch.setattr(settings_routes, "_validate_bybit_credentials", _valid)

    resp = client.get("/api/v1/settings/api-key/demo?validate=1")

    assert resp.status_code == 200
    data = resp.json()
    assert data["has_key"] is True
    assert data["key_hint"] == "****1234"
    assert data["validated"] is True
    assert data["validation_status"] == "valid"
    assert data["validation_error"] == ""


def test_api_key_status_validate_invalid(tmp_path: Path, monkeypatch) -> None:
    _write_credentials(tmp_path)
    client = _client(tmp_path, monkeypatch)

    monkeypatch.setattr(
        settings_routes,
        "_validate_bybit_credentials",
        lambda api_key, api_secret, slot: (False, "Bybit retCode=10003: API key is invalid"),
    )

    resp = client.get("/api/v1/settings/api-key/demo?validate=1")

    assert resp.status_code == 200
    data = resp.json()
    assert data["has_key"] is True
    assert data["validated"] is False
    assert data["validation_status"] == "invalid"
    assert data["validation_error"] == "Bybit retCode=10003: API key is invalid"


def test_api_key_status_validate_network_failure_is_not_invalid(
    tmp_path: Path, monkeypatch,
) -> None:
    _write_credentials(tmp_path)
    client = _client(tmp_path, monkeypatch)

    monkeypatch.setattr(
        settings_routes,
        "_validate_bybit_credentials",
        lambda api_key, api_secret, slot: (False, "Network error: timed out"),
    )

    resp = client.get("/api/v1/settings/api-key/demo?validate=1")

    assert resp.status_code == 200
    data = resp.json()
    assert data["has_key"] is True
    assert data["validated"] is False
    assert data["validation_status"] == "validation_unavailable"
    assert data["validation_error"] == "Network error: timed out"
