from __future__ import annotations

import hashlib
import json
import os
import stat
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
    monkeypatch.setenv("OPENCLAW_CUTOVER_PREFLIGHT_ROOT", str(tmp_path))
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
    readiness_blockers: list[str] | None = None,
    answers: dict | None = None,
    public_ipv4: str | None = None,
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
        "readiness": {
            "blocking_reasons": readiness_blockers
            if readiness_blockers is not None
            else [
                "connector_mode:bybit_mode_not_demo",
                "connector_mode:bybit_connector_write_not_enabled",
            ],
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
    if public_ipv4 is not None:
        payload["public_ipv4_for_bybit_api_allowlist"] = public_ipv4
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


def test_bybit_demo_connector_mode_accepts_relative_preflight_below_trusted_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, env_file = _client(tmp_path, monkeypatch)
    env_file.parent.mkdir(parents=True)
    env_file.write_text("BYBIT_MODE=read_only\n", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    preflight_path, preflight_sha = _write_preflight(
        nested / "cutover_preflight.json",
        env_file=env_file,
    )

    resp = client.post(
        "/api/v1/settings/bybit-demo-connector-mode",
        json=_post_body(
            Path("nested") / preflight_path.name,
            preflight_sha,
        ),
    )

    assert resp.status_code == 200
    assert resp.json()["cutover_preflight"]["sha256"] == preflight_sha


def test_bybit_demo_connector_mode_rejects_group_writable_preflight_root(
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
    tmp_path.chmod(0o770)

    resp = client.post(
        "/api/v1/settings/bybit-demo-connector-mode",
        json=_post_body(preflight_path, preflight_sha),
    )

    assert resp.status_code == 400
    assert "BYBIT_MODE=read_only" in env_file.read_text(encoding="utf-8")


def test_bybit_demo_connector_mode_rejects_group_writable_preflight_file(
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
    preflight_path.chmod(0o660)

    resp = client.post(
        "/api/v1/settings/bybit-demo-connector-mode",
        json=_post_body(preflight_path, preflight_sha),
    )

    assert resp.status_code == 400
    assert "BYBIT_MODE=read_only" in env_file.read_text(encoding="utf-8")


def test_bybit_demo_connector_mode_rejects_foreign_owned_preflight_file(
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
    real_fstat = settings_routes.os.fstat

    def foreign_file_owner(fd):
        metadata = real_fstat(fd)
        if stat.S_ISREG(metadata.st_mode):
            values = list(metadata)
            values[4] = os.geteuid() + 1
            return os.stat_result(values)
        return metadata

    monkeypatch.setattr(settings_routes.os, "fstat", foreign_file_owner)

    resp = client.post(
        "/api/v1/settings/bybit-demo-connector-mode",
        json=_post_body(preflight_path, preflight_sha),
    )

    assert resp.status_code == 400
    assert "BYBIT_MODE=read_only" in env_file.read_text(encoding="utf-8")


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


def test_bybit_demo_connector_mode_rejects_uncleared_demo_credential_blocker(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, env_file = _client(tmp_path, monkeypatch)
    env_file.parent.mkdir(parents=True)
    env_file.write_text("BYBIT_MODE=read_only\n", encoding="utf-8")
    preflight_path, preflight_sha = _write_preflight(
        tmp_path / "cutover_preflight.json",
        env_file=env_file,
        readiness_blockers=[
            "demo_api_slot:demo_api_key_expected_value_mismatch",
            "connector_mode:bybit_mode_not_demo",
        ],
    )

    resp = client.post(
        "/api/v1/settings/bybit-demo-connector-mode",
        json=_post_body(preflight_path, preflight_sha),
    )

    assert resp.status_code == 400
    assert "Demo credential readiness must be green" in resp.json()["detail"]
    assert "BYBIT_MODE=read_only" in env_file.read_text(encoding="utf-8")
    assert "BYBIT_CONNECTOR_WRITE_ENABLED=true" not in env_file.read_text(encoding="utf-8")


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


def test_bybit_demo_connector_mode_rejects_preflight_outside_trusted_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, env_file = _client(tmp_path, monkeypatch)
    env_file.parent.mkdir(parents=True)
    env_file.write_text("BYBIT_MODE=read_only\n", encoding="utf-8")
    outside_path = tmp_path.parent / f".{tmp_path.name}-outside-preflight.json"
    try:
        preflight_path, preflight_sha = _write_preflight(
            outside_path,
            env_file=env_file,
        )

        resp = client.post(
            "/api/v1/settings/bybit-demo-connector-mode",
            json=_post_body(preflight_path, preflight_sha),
        )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid cutover preflight path"
        assert str(preflight_path) not in resp.text
        assert "BYBIT_MODE=read_only" in env_file.read_text(encoding="utf-8")
        assert "BYBIT_CONNECTOR_WRITE_ENABLED=true" not in env_file.read_text(
            encoding="utf-8"
        )
    finally:
        outside_path.unlink(missing_ok=True)


def test_bybit_demo_connector_mode_rejects_parent_segments_inside_trusted_root(
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
    ambiguous_path = tmp_path / "nested" / ".." / preflight_path.name

    resp = client.post(
        "/api/v1/settings/bybit-demo-connector-mode",
        json=_post_body(ambiguous_path, preflight_sha),
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid cutover preflight path"
    assert "BYBIT_MODE=read_only" in env_file.read_text(encoding="utf-8")
    assert "BYBIT_CONNECTOR_WRITE_ENABLED=true" not in env_file.read_text(
        encoding="utf-8"
    )


def test_bybit_demo_connector_mode_rejects_non_json_preflight(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, env_file = _client(tmp_path, monkeypatch)
    env_file.parent.mkdir(parents=True)
    env_file.write_text("BYBIT_MODE=read_only\n", encoding="utf-8")
    preflight_path, preflight_sha = _write_preflight(
        tmp_path / "cutover_preflight.txt",
        env_file=env_file,
    )

    resp = client.post(
        "/api/v1/settings/bybit-demo-connector-mode",
        json=_post_body(preflight_path, preflight_sha),
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid cutover preflight path"
    assert "BYBIT_MODE=read_only" in env_file.read_text(encoding="utf-8")
    assert "BYBIT_CONNECTOR_WRITE_ENABLED=true" not in env_file.read_text(
        encoding="utf-8"
    )


def test_bybit_demo_connector_mode_rejects_preflight_symlink(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, env_file = _client(tmp_path, monkeypatch)
    env_file.parent.mkdir(parents=True)
    env_file.write_text("BYBIT_MODE=read_only\n", encoding="utf-8")
    target_path, preflight_sha = _write_preflight(
        tmp_path / "cutover_preflight_target.json",
        env_file=env_file,
    )
    symlink_path = tmp_path / "cutover_preflight.json"
    symlink_path.symlink_to(target_path)

    resp = client.post(
        "/api/v1/settings/bybit-demo-connector-mode",
        json=_post_body(symlink_path, preflight_sha),
    )

    assert resp.status_code == 400
    assert "BYBIT_MODE=read_only" in env_file.read_text(encoding="utf-8")
    assert "BYBIT_CONNECTOR_WRITE_ENABLED=true" not in env_file.read_text(
        encoding="utf-8"
    )


def test_bybit_demo_connector_mode_rejects_nested_directory_symlink_escape(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, env_file = _client(tmp_path, monkeypatch)
    env_file.parent.mkdir(parents=True)
    env_file.write_text("BYBIT_MODE=read_only\n", encoding="utf-8")
    outside_dir = tmp_path.parent / f".{tmp_path.name}-outside-cutover"
    outside_dir.mkdir()
    outside_path = outside_dir / "cutover_preflight.json"
    try:
        _target_path, preflight_sha = _write_preflight(
            outside_path,
            env_file=env_file,
        )
        escaped_dir = tmp_path / "escaped"
        escaped_dir.symlink_to(outside_dir, target_is_directory=True)

        resp = client.post(
            "/api/v1/settings/bybit-demo-connector-mode",
            json=_post_body(escaped_dir / outside_path.name, preflight_sha),
        )

        assert resp.status_code == 400
        assert "BYBIT_MODE=read_only" in env_file.read_text(encoding="utf-8")
        assert "BYBIT_CONNECTOR_WRITE_ENABLED=true" not in env_file.read_text(
            encoding="utf-8"
        )
    finally:
        outside_path.unlink(missing_ok=True)
        outside_dir.rmdir()


def test_bybit_demo_connector_mode_rejects_preexisting_trusted_root_symlink(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, env_file = _client(tmp_path, monkeypatch)
    env_file.parent.mkdir(parents=True)
    env_file.write_text("BYBIT_MODE=read_only\n", encoding="utf-8")
    configured_root = tmp_path / "configured-root"
    outside_root = tmp_path.parent / f".{tmp_path.name}-outside-root"
    outside_root.mkdir()
    outside_path = outside_root / "cutover_preflight.json"
    try:
        _target_path, preflight_sha = _write_preflight(
            outside_path,
            env_file=env_file,
        )
        configured_root.symlink_to(outside_root, target_is_directory=True)
        monkeypatch.setenv(
            "OPENCLAW_CUTOVER_PREFLIGHT_ROOT",
            str(configured_root),
        )

        resp = client.post(
            "/api/v1/settings/bybit-demo-connector-mode",
            json=_post_body(Path(outside_path.name), preflight_sha),
        )

        assert resp.status_code == 400
        assert "BYBIT_MODE=read_only" in env_file.read_text(encoding="utf-8")
        assert "BYBIT_CONNECTOR_WRITE_ENABLED=true" not in env_file.read_text(
            encoding="utf-8"
        )
    finally:
        outside_path.unlink(missing_ok=True)
        outside_root.rmdir()


def test_bybit_demo_connector_mode_rejects_trusted_root_ancestor_replacement(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, env_file = _client(tmp_path, monkeypatch)
    env_file.parent.mkdir(parents=True)
    env_file.write_text("BYBIT_MODE=read_only\n", encoding="utf-8")
    configured_parent = tmp_path / "configured-parent"
    original_parent = tmp_path / "original-parent"
    outside_parent = tmp_path / "outside-parent"
    configured_root = configured_parent / "root"
    outside_root = outside_parent / "root"
    configured_root.mkdir(parents=True)
    outside_root.mkdir(parents=True)
    _write_preflight(
        configured_root / "cutover_preflight.json",
        env_file=env_file,
        public_ipv4="original-root",
    )
    _outside_path, outside_sha = _write_preflight(
        outside_root / "cutover_preflight.json",
        env_file=env_file,
        public_ipv4="external-root",
    )
    monkeypatch.setenv(
        "OPENCLAW_CUTOVER_PREFLIGHT_ROOT",
        str(configured_root),
    )
    real_open = settings_routes.os.open
    swapped = False

    def open_after_ancestor_swap(path, flags, *args, **kwargs):
        nonlocal swapped
        dir_fd = kwargs.get("dir_fd")
        if not swapped and (
            (dir_fd is None and Path(path) == configured_root)
            or (dir_fd is not None and os.fspath(path) == configured_parent.name)
        ):
            configured_parent.rename(original_parent)
            configured_parent.symlink_to(outside_parent, target_is_directory=True)
            swapped = True
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(settings_routes.os, "open", open_after_ancestor_swap)

    resp = client.post(
        "/api/v1/settings/bybit-demo-connector-mode",
        json=_post_body(Path("cutover_preflight.json"), outside_sha),
    )

    assert swapped is True
    assert resp.status_code == 400
    assert "BYBIT_MODE=read_only" in env_file.read_text(encoding="utf-8")
    assert "BYBIT_CONNECTOR_WRITE_ENABLED=true" not in env_file.read_text(
        encoding="utf-8"
    )


def test_bybit_demo_connector_mode_hashes_and_parses_same_open_file_bytes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, env_file = _client(tmp_path, monkeypatch)
    env_file.parent.mkdir(parents=True)
    env_file.write_text("BYBIT_MODE=read_only\n", encoding="utf-8")
    preflight_path, preflight_sha = _write_preflight(
        tmp_path / "cutover_preflight.json",
        env_file=env_file,
        public_ipv4="original-fixture",
    )
    replacement_path, _ = _write_preflight(
        tmp_path / "replacement.json",
        env_file=env_file,
        public_ipv4="replacement-fixture",
    )
    real_open = settings_routes.os.open
    open_count = 0

    def open_then_swap(path, flags, *args, **kwargs):
        nonlocal open_count
        fd = real_open(path, flags, *args, **kwargs)
        if (
            Path(path).name == preflight_path.name
            and kwargs.get("dir_fd") is not None
        ):
            open_count += 1
            replacement_path.replace(preflight_path)
        return fd

    monkeypatch.setattr(settings_routes.os, "open", open_then_swap)

    resp = client.post(
        "/api/v1/settings/bybit-demo-connector-mode",
        json=_post_body(preflight_path, preflight_sha),
    )

    assert resp.status_code == 200
    assert open_count == 1
    assert (
        resp.json()["cutover_preflight"]["public_ipv4_for_bybit_api_allowlist"]
        == "original-fixture"
    )


def test_bybit_demo_connector_mode_rejects_oversized_preflight(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, env_file = _client(tmp_path, monkeypatch)
    env_file.parent.mkdir(parents=True)
    env_file.write_text("BYBIT_MODE=read_only\n", encoding="utf-8")
    preflight_path = tmp_path / "cutover_preflight.json"
    preflight_path.write_text(
        json.dumps({"padding": "x" * settings_routes._CUTOVER_PREFLIGHT_MAX_BYTES}),
        encoding="utf-8",
    )
    preflight_sha = hashlib.sha256(preflight_path.read_bytes()).hexdigest()

    resp = client.post(
        "/api/v1/settings/bybit-demo-connector-mode",
        json=_post_body(preflight_path, preflight_sha),
    )

    assert resp.status_code == 400
    assert "BYBIT_MODE=read_only" in env_file.read_text(encoding="utf-8")
    assert "BYBIT_CONNECTOR_WRITE_ENABLED=true" not in env_file.read_text(
        encoding="utf-8"
    )
