from __future__ import annotations

import stat
import sys
from pathlib import Path
from types import SimpleNamespace

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
    secrets_root = tmp_path / "secrets"
    slot_dir = tmp_path / "secrets" / slot
    slot_dir.mkdir(parents=True)
    secrets_root.chmod(stat.S_IRWXU)
    slot_dir.chmod(stat.S_IRWXU)
    api_key = slot_dir / "api_key"
    api_secret = slot_dir / "api_secret"
    api_key.write_text("DEMOAPIKEY1234", encoding="utf-8")
    api_secret.write_text("DEMOSECRET5678", encoding="utf-8")
    api_key.chmod(stat.S_IRUSR | stat.S_IWUSR)
    api_secret.chmod(stat.S_IRUSR | stat.S_IWUSR)


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


def test_api_key_status_does_not_follow_slot_symlink_outside_secrets_root(
    tmp_path: Path, monkeypatch
) -> None:
    secrets_root = tmp_path / "secrets"
    outside_slot = tmp_path / "outside-demo"
    secrets_root.mkdir()
    outside_slot.mkdir()
    (outside_slot / "api_key").write_text("OUTSIDEAPIKEY1234", encoding="utf-8")
    (outside_slot / "api_secret").write_text("OUTSIDESECRET5678", encoding="utf-8")
    (secrets_root / "demo").symlink_to(outside_slot, target_is_directory=True)
    client = _client(tmp_path, monkeypatch)

    resp = client.get("/api/v1/settings/api-key/demo")

    assert resp.status_code == 200
    assert resp.json()["has_key"] is False
    assert resp.json()["key_hint"] == ""
    assert resp.json()["last_modified"] is None


def test_api_key_status_rejects_weak_root_directory_permissions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_credentials(tmp_path)
    (tmp_path / "secrets").chmod(
        stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP
    )
    client = _client(tmp_path, monkeypatch)
    validation_slots: list[str] = []

    def _record_validation(api_key: str, api_secret: str, slot: str) -> tuple[bool, str]:
        validation_slots.append(slot)
        return True, ""

    monkeypatch.setattr(settings_routes, "_validate_bybit_credentials", _record_validation)

    resp = client.get("/api/v1/settings/api-key/demo?validate=1")

    assert resp.status_code == 200
    assert resp.json()["has_key"] is False
    assert resp.json()["validated"] is False
    assert resp.json()["last_modified"] is None
    assert validation_slots == []


def test_api_key_status_rejects_weak_slot_directory_permissions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_credentials(tmp_path)
    (tmp_path / "secrets" / "demo").chmod(
        stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP
    )
    client = _client(tmp_path, monkeypatch)

    resp = client.get("/api/v1/settings/api-key/demo?validate=1")

    assert resp.status_code == 200
    assert resp.json()["has_key"] is False
    assert resp.json()["validated"] is False


def test_api_key_status_rejects_weak_secret_file_permissions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_credentials(tmp_path)
    (tmp_path / "secrets" / "demo" / "api_key").chmod(
        stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP
    )
    client = _client(tmp_path, monkeypatch)

    resp = client.get("/api/v1/settings/api-key/demo?validate=1")

    assert resp.status_code == 200
    assert resp.json()["has_key"] is False
    assert resp.json()["validated"] is False


def test_api_key_status_rejects_secret_root_not_owned_by_effective_user(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_credentials(tmp_path)
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        settings_routes.os,
        "geteuid",
        lambda: settings_routes.os.stat(tmp_path / "secrets").st_uid + 1,
    )

    resp = client.get("/api/v1/settings/api-key/demo?validate=1")

    assert resp.status_code == 200
    assert resp.json()["has_key"] is False
    assert resp.json()["validated"] is False


def test_api_key_status_rejects_secret_slot_not_owned_by_effective_user(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_credentials(tmp_path)
    client = _client(tmp_path, monkeypatch)
    real_fstat = settings_routes.os.fstat
    directory_count = 0

    def _wrong_slot_owner(fd: int):
        nonlocal directory_count
        result = real_fstat(fd)
        if not stat.S_ISDIR(result.st_mode):
            return result
        directory_count += 1
        if directory_count % 2:
            return result
        return SimpleNamespace(
            st_mode=result.st_mode,
            st_uid=result.st_uid + 1,
        )

    monkeypatch.setattr(settings_routes.os, "fstat", _wrong_slot_owner)

    resp = client.get("/api/v1/settings/api-key/demo?validate=1")

    assert resp.status_code == 200
    assert resp.json()["has_key"] is False
    assert resp.json()["validated"] is False


def test_api_key_status_rejects_secret_file_not_owned_by_effective_user(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_credentials(tmp_path)
    client = _client(tmp_path, monkeypatch)
    real_fstat = settings_routes.os.fstat

    def _wrong_regular_file_owner(fd: int):
        result = real_fstat(fd)
        if not stat.S_ISREG(result.st_mode):
            return result
        return SimpleNamespace(
            st_mode=result.st_mode,
            st_uid=result.st_uid + 1,
            st_dev=result.st_dev,
            st_ino=result.st_ino,
            st_size=result.st_size,
            st_mtime_ns=result.st_mtime_ns,
        )

    monkeypatch.setattr(settings_routes.os, "fstat", _wrong_regular_file_owner)

    resp = client.get("/api/v1/settings/api-key/demo?validate=1")

    assert resp.status_code == 200
    assert resp.json()["has_key"] is False
    assert resp.json()["validated"] is False
    assert resp.json()["last_modified"] is None


def test_api_key_status_rejects_intermediate_secret_root_symlink(
    tmp_path: Path,
    monkeypatch,
) -> None:
    outside_parent = tmp_path / "outside-parent"
    _write_credentials(outside_parent)
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(outside_parent, target_is_directory=True)
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setenv(
        "OPENCLAW_SECRETS_DIR",
        str(linked_parent / "secrets"),
    )

    resp = client.get("/api/v1/settings/api-key/demo?validate=1")

    assert resp.status_code == 200
    assert resp.json()["has_key"] is False
    assert resp.json()["validated"] is False
    assert resp.json()["last_modified"] is None


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
        lambda api_key, api_secret, slot: (
            False,
            "trace-canary /srv/private.py SELECT secret FROM credentials",
        ),
    )

    resp = client.get("/api/v1/settings/api-key/demo?validate=1")

    assert resp.status_code == 200
    data = resp.json()
    assert data["has_key"] is True
    assert data["validated"] is False
    assert data["validation_status"] == "invalid"
    assert data["validation_error"] == "Credential validation failed"
    assert "trace-canary" not in resp.text


def test_api_key_status_validate_network_failure_is_not_invalid(
    tmp_path: Path, monkeypatch,
) -> None:
    _write_credentials(tmp_path)
    client = _client(tmp_path, monkeypatch)

    monkeypatch.setattr(
        settings_routes,
        "_validate_bybit_credentials",
        lambda api_key, api_secret, slot: (False, "validation_unavailable"),
    )

    resp = client.get("/api/v1/settings/api-key/demo?validate=1")

    assert resp.status_code == 200
    data = resp.json()
    assert data["has_key"] is True
    assert data["validated"] is False
    assert data["validation_status"] == "validation_unavailable"
    assert data["validation_error"] == "Credential validation unavailable"


def test_save_api_key_keeps_hint_in_response_but_omits_it_from_server_logs(
    tmp_path: Path,
    monkeypatch,
    caplog,
) -> None:
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        settings_routes,
        "_validate_bybit_credentials",
        lambda api_key, api_secret, slot: (True, ""),
    )
    caplog.set_level("INFO", logger=settings_routes.__name__)

    resp = client.post(
        "/api/v1/settings/api-key/demo",
        json={
            "api_key": "DEMOAPIKEY1234",
            "api_secret": "DEMOSECRET5678",
        },
    )

    assert resp.status_code == 200
    assert resp.json()["key_hint"] == "****1234"
    assert "****1234" not in caplog.text
    assert "DEMOAPIKEY1234" not in caplog.text
    assert "API key saved for slot 'demo'" in caplog.text
    secrets_root = tmp_path / "secrets"
    slot_dir = secrets_root / "demo"
    assert stat.S_IMODE(secrets_root.stat().st_mode) == 0o700
    assert stat.S_IMODE(slot_dir.stat().st_mode) == 0o700
    for filename in ("api_key", "api_secret", "bybit_endpoint"):
        assert stat.S_IMODE((slot_dir / filename).stat().st_mode) == 0o600
    assert not [path for path in slot_dir.iterdir() if path.name.startswith(".")]


def test_save_api_key_rejects_intermediate_secret_root_symlink(
    tmp_path: Path,
    monkeypatch,
) -> None:
    outside_parent = tmp_path / "outside-parent"
    outside_parent.mkdir()
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(outside_parent, target_is_directory=True)
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setenv(
        "OPENCLAW_SECRETS_DIR",
        str(linked_parent / "secrets"),
    )
    monkeypatch.setattr(
        settings_routes,
        "_validate_bybit_credentials",
        lambda api_key, api_secret, slot: (True, ""),
    )

    resp = client.post(
        "/api/v1/settings/api-key/demo",
        json={
            "api_key": "NEWDEMOAPIKEY9999",
            "api_secret": "NEWDEMOSECRET9999",
        },
    )

    assert resp.status_code == 500
    assert not (outside_parent / "secrets" / "demo" / "api_key").exists()
    assert not (outside_parent / "secrets" / "demo" / "api_secret").exists()


def test_save_api_key_failed_atomic_replace_preserves_existing_secret(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_credentials(tmp_path)
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        settings_routes,
        "_validate_bybit_credentials",
        lambda api_key, api_secret, slot: (True, ""),
    )

    def _replace_denied(source, target, *args, **kwargs) -> None:
        raise PermissionError("replace denied")

    monkeypatch.setattr(settings_routes.os, "replace", _replace_denied)

    resp = client.post(
        "/api/v1/settings/api-key/demo",
        json={
            "api_key": "NEWDEMOAPIKEY9999",
            "api_secret": "NEWDEMOSECRET9999",
        },
    )

    assert resp.status_code == 500
    api_key_path = tmp_path / "secrets" / "demo" / "api_key"
    assert api_key_path.read_text(encoding="utf-8") == "DEMOAPIKEY1234"


def test_save_api_key_second_replace_failure_restores_entire_existing_bundle(
    tmp_path: Path,
    monkeypatch,
    caplog,
) -> None:
    _write_credentials(tmp_path)
    slot_dir = tmp_path / "secrets" / "demo"
    (slot_dir / "bybit_endpoint").write_text("old-demo", encoding="utf-8")
    (slot_dir / "bybit_endpoint").chmod(stat.S_IRUSR | stat.S_IWUSR)
    old_bundle = {
        name: (slot_dir / name).read_bytes()
        for name in ("api_key", "api_secret", "bybit_endpoint")
    }
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        settings_routes,
        "_validate_bybit_credentials",
        lambda api_key, api_secret, slot: (True, ""),
    )
    real_replace = settings_routes.os.replace
    replace_count = 0

    def _fail_second_replace_once(source, target, *args, **kwargs) -> None:
        nonlocal replace_count
        replace_count += 1
        if replace_count == 2:
            raise PermissionError("replacement rejected")
        real_replace(source, target, *args, **kwargs)

    monkeypatch.setattr(settings_routes.os, "replace", _fail_second_replace_once)
    caplog.set_level("ERROR", logger=settings_routes.__name__)

    resp = client.post(
        "/api/v1/settings/api-key/demo",
        json={
            "api_key": "NEWDEMOAPIKEY9999",
            "api_secret": "NEWDEMOSECRET9999",
        },
    )

    assert resp.status_code == 500
    assert {
        name: (slot_dir / name).read_bytes()
        for name in ("api_key", "api_secret", "bybit_endpoint")
    } == old_bundle
    assert "NEWDEMOAPIKEY9999" not in resp.text
    assert "NEWDEMOSECRET9999" not in resp.text
    assert "NEWDEMOAPIKEY9999" not in caplog.text
    assert "NEWDEMOSECRET9999" not in caplog.text


def test_save_api_key_third_replace_failure_restores_entire_existing_bundle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_credentials(tmp_path)
    slot_dir = tmp_path / "secrets" / "demo"
    (slot_dir / "bybit_endpoint").write_text("old-demo", encoding="utf-8")
    (slot_dir / "bybit_endpoint").chmod(stat.S_IRUSR | stat.S_IWUSR)
    old_bundle = {
        name: (slot_dir / name).read_bytes()
        for name in ("api_key", "api_secret", "bybit_endpoint")
    }
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        settings_routes,
        "_validate_bybit_credentials",
        lambda api_key, api_secret, slot: (True, ""),
    )
    real_replace = settings_routes.os.replace
    replace_count = 0

    def _fail_third_replace_once(source, target, *args, **kwargs) -> None:
        nonlocal replace_count
        replace_count += 1
        if replace_count == 3:
            raise PermissionError("replacement rejected")
        real_replace(source, target, *args, **kwargs)

    monkeypatch.setattr(settings_routes.os, "replace", _fail_third_replace_once)

    resp = client.post(
        "/api/v1/settings/api-key/demo",
        json={
            "api_key": "NEWDEMOAPIKEY9999",
            "api_secret": "NEWDEMOSECRET9999",
        },
    )

    assert resp.status_code == 500
    assert {
        name: (slot_dir / name).read_bytes()
        for name in ("api_key", "api_secret", "bybit_endpoint")
    } == old_bundle


def test_save_api_key_rejects_secret_file_symlink_within_configured_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    slot_dir = tmp_path / "secrets" / "demo"
    slot_dir.mkdir(parents=True)
    real_target = slot_dir / "real_api_key"
    real_target.write_text("ORIGINALKEY1234", encoding="utf-8")
    (slot_dir / "api_key").symlink_to(real_target)
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        settings_routes,
        "_validate_bybit_credentials",
        lambda api_key, api_secret, slot: (True, ""),
    )

    resp = client.post(
        "/api/v1/settings/api-key/demo",
        json={
            "api_key": "NEWDEMOAPIKEY9999",
            "api_secret": "NEWDEMOSECRET9999",
        },
    )

    assert resp.status_code == 500
    assert real_target.read_text(encoding="utf-8") == "ORIGINALKEY1234"
    assert (slot_dir / "api_key").is_symlink()


def test_save_api_key_permission_hardening_failure_writes_no_secret(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        settings_routes,
        "_validate_bybit_credentials",
        lambda api_key, api_secret, slot: (True, ""),
    )

    def _fchmod_denied(fd, mode) -> None:
        raise PermissionError("fchmod denied")

    monkeypatch.setattr(settings_routes.os, "fchmod", _fchmod_denied)

    resp = client.post(
        "/api/v1/settings/api-key/demo",
        json={
            "api_key": "NEWDEMOAPIKEY9999",
            "api_secret": "NEWDEMOSECRET9999",
        },
    )

    assert resp.status_code == 500
    slot_dir = tmp_path / "secrets" / "demo"
    assert not (slot_dir / "api_key").exists()
    assert not (slot_dir / "api_secret").exists()
    assert not (slot_dir / "bybit_endpoint").exists()
