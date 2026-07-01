from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

from cost_gate_learning_lane import runtime_governance_ipc_readonly_snapshot as mod


NOW = dt.datetime(2026, 6, 27, 8, 0, tzinfo=dt.timezone.utc)


async def _ready_dispatcher(method: str, params: dict, timeout: float) -> dict:
    assert params == {}
    assert timeout == 5.0
    if method == "governance.get_status":
        return {
            "enabled": True,
            "mode": "Normal",
            "risk_level": "Normal",
            "auth_effective_count": 2,
            "auth_pending_approval": 0,
            "lease_live_count": 0,
            "oms_active_count": 0,
        }
    if method == "governance.list_leases":
        return {"result": []}
    if method == "governance.get_risk_state":
        return {
            "level": "NORMAL",
            "constraints": {
                "new_entries_allowed": True,
                "position_size_multiplier": 1.0,
                "reduce_only": False,
                "active_de_risking": False,
                "emergency_stops": False,
                "requires_operator": False,
            },
        }
    raise AssertionError(method)


async def _failing_dispatcher(method: str, params: dict, timeout: float) -> dict:
    if method == "governance.list_leases":
        return {"ok": False, "error": "socket_unavailable"}
    return await _ready_dispatcher(method, params, timeout)


async def _protocol_error_dispatcher(method: str, params: dict, timeout: float) -> dict:
    from app.ipc_client import EngineProtocolError

    raise EngineProtocolError(
        "response_id_mismatch",
        expected_id=1,
        actual_id=None,
    )


def test_build_ready_snapshot_uses_read_only_governance_methods() -> None:
    packet = mod.build_runtime_governance_ipc_readonly_snapshot(
        now_utc=NOW,
        dispatcher=_ready_dispatcher,
        source_head="source",
        runtime_head="runtime",
    )

    assert packet["status"] == mod.READY_STATUS
    assert packet["schema_version"] == mod.SCHEMA_VERSION
    assert set(packet["methods"]) == set(mod.READ_ONLY_METHODS)
    assert packet["summary"]["risk_level"] == "NORMAL"
    assert packet["summary"]["position_size_multiplier"] == 1.0
    assert packet["summary"]["lease_count"] == 0
    assert packet["answers"]["runtime_readonly_ipc_call_performed"] is True
    assert packet["answers"]["read_only_methods_only"] is True
    assert packet["answers"]["decision_lease_acquire_performed"] is False
    assert packet["answers"]["decision_lease_release_performed"] is False
    assert packet["answers"]["order_submission_performed"] is False
    assert packet["answers"]["runtime_mutation_performed"] is False
    assert packet["answers"]["live_authority_granted"] is False
    assert packet["answers"]["main_cost_gate_adjustment"] == "NONE"


def test_build_snapshot_blocks_when_any_runtime_method_fails() -> None:
    packet = mod.build_runtime_governance_ipc_readonly_snapshot(
        now_utc=NOW,
        dispatcher=_failing_dispatcher,
    )

    assert packet["status"] == mod.BLOCKED_BY_RUNTIME_STATUS
    assert packet["summary"] is None
    assert packet["runtime_blockers"] == ["governance.list_leases_not_ok"]
    assert packet["methods"]["governance.list_leases"]["ok"] is False


def test_dispatch_ipc_method_preserves_protocol_error_reason() -> None:
    entry = mod._dispatch_ipc_method(
        method="governance.get_status",
        dispatcher=_protocol_error_dispatcher,
    )

    assert entry["ok"] is False
    assert entry["error"] == "ipc_dispatch_exception:EngineProtocolError"
    assert entry["error_reason"] == "response_id_mismatch"


def test_cli_sets_ipc_secret_file_env_without_serializing_secret(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    secret_file = tmp_path / "ipc_secret"
    secret_file.write_text("test-secret-do-not-print\n", encoding="utf-8")
    seen: dict[str, str | None] = {}

    def fake_build(**kwargs):
        seen["ipc_secret_file"] = os.environ.get("OPENCLAW_IPC_SECRET_FILE")
        return {
            "status": mod.READY_STATUS,
            "schema_version": mod.SCHEMA_VERSION,
            "generated_at_utc": NOW.isoformat(),
            "runtime_blockers": [],
            "summary": {},
            "methods": {},
            "answers": {},
            "boundary": mod.BOUNDARY,
            "source": "runtime_governance_ipc_readonly_snapshot",
        }

    monkeypatch.delenv("OPENCLAW_IPC_SECRET", raising=False)
    monkeypatch.delenv("OPENCLAW_IPC_SECRET_FILE", raising=False)
    monkeypatch.setattr(mod, "build_runtime_governance_ipc_readonly_snapshot", fake_build)

    assert mod.main([
        "--ipc-secret-file",
        str(secret_file),
        "--print-json",
    ]) == 0

    captured = capsys.readouterr()
    assert seen["ipc_secret_file"] == str(secret_file)
    assert os.environ.get("OPENCLAW_IPC_SECRET_FILE") is None
    assert "test-secret-do-not-print" not in captured.out
    assert "test-secret-do-not-print" not in captured.err


def test_cli_restores_existing_ipc_secret_file_env(
    tmp_path: Path,
    monkeypatch,
) -> None:
    secret_file = tmp_path / "new_ipc_secret"
    secret_file.write_text("new-secret-do-not-print\n", encoding="utf-8")
    existing_secret_file = tmp_path / "existing_ipc_secret"
    existing_secret_file.write_text("existing-secret-do-not-print\n", encoding="utf-8")
    seen: dict[str, str | None] = {}

    def fake_build(**kwargs):
        seen["ipc_secret_file"] = os.environ.get("OPENCLAW_IPC_SECRET_FILE")
        return {
            "status": mod.READY_STATUS,
            "schema_version": mod.SCHEMA_VERSION,
            "generated_at_utc": NOW.isoformat(),
            "runtime_blockers": [],
            "summary": {},
            "methods": {},
            "answers": {},
            "boundary": mod.BOUNDARY,
            "source": "runtime_governance_ipc_readonly_snapshot",
        }

    monkeypatch.setenv("OPENCLAW_IPC_SECRET_FILE", str(existing_secret_file))
    monkeypatch.setattr(mod, "build_runtime_governance_ipc_readonly_snapshot", fake_build)

    assert mod.main([
        "--ipc-secret-file",
        str(secret_file),
    ]) == 0

    assert seen["ipc_secret_file"] == str(secret_file)
    assert os.environ.get("OPENCLAW_IPC_SECRET_FILE") == str(existing_secret_file)
