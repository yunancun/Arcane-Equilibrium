from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from app import governance_routes
from app import live_halt_recovery
from app.live_halt_recovery import LIVE_HALT_REQUEST_ID


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _write_live_halt_snapshot(tmp_path, *, halted: bool = True) -> None:
    snapshot = {
        "session_halted": halted,
        "paper_paused": halted,
        "session_drawdown_pct": 6.4241,
        "system_mode": "live_reserved",
        "risk_manager_config": {
            "limits": {
                "session_drawdown_max_pct": 12.0,
            },
        },
    }
    (tmp_path / "pipeline_snapshot_live.json").write_text(
        json.dumps(snapshot),
        encoding="utf-8",
    )


def _operator_actor():
    return SimpleNamespace(actor_id="operator-1", roles={"operator"})


def test_live_halt_snapshot_builds_virtual_pending_request(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCLAW_DATA_DIR", str(tmp_path))
    _write_live_halt_snapshot(tmp_path)

    req = live_halt_recovery.build_live_halt_recovery_request()

    assert req is not None
    assert req["request_id"] == LIVE_HALT_REQUEST_ID
    assert req["status"] == "pending"
    assert req["recovery_type"] == "trading_resume"
    assert req["evidence"]["engine"] == "live"
    assert req["evidence"]["session_drawdown_pct"] == 6.4241


def test_live_halt_sentinel_suppresses_already_approved_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCLAW_DATA_DIR", str(tmp_path))
    _write_live_halt_snapshot(tmp_path)
    snapshot_mtime_ms = int((tmp_path / "pipeline_snapshot_live.json").stat().st_mtime * 1000)
    (tmp_path / "live_halt_recovery_approved.json").write_text(
        json.dumps({
            "approved_at_ms": snapshot_mtime_ms + 1000,
            "snapshot_mtime_ms": snapshot_mtime_ms,
            "request_id": LIVE_HALT_REQUEST_ID,
        }),
        encoding="utf-8",
    )

    assert live_halt_recovery.build_live_halt_recovery_request() is None


def test_governance_pending_includes_live_halt_virtual_request(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCLAW_DATA_DIR", str(tmp_path))
    _write_live_halt_snapshot(tmp_path)

    class FakeGate:
        def get_pending_requests(self):
            return []

    fake_hub = SimpleNamespace(_recovery_gate=FakeGate())
    monkeypatch.setattr(governance_routes, "_get_governance_hub", lambda: fake_hub)

    resp = governance_routes.get_pending_recovery_requests(actor=_operator_actor())

    assert resp["ok"] is True
    assert resp["data"][0]["request_id"] == LIVE_HALT_REQUEST_ID


def test_governance_approve_routes_live_halt_to_recovery_helper(monkeypatch):
    fake_hub = SimpleNamespace(
        _recovery_gate=None,
        _change_audit_log=None,
        is_globally_enabled=lambda: True,
    )
    called: dict[str, str] = {}

    async def fake_approve(actor_id: str):
        called["actor_id"] = actor_id
        return {"request_id": LIVE_HALT_REQUEST_ID, "status": "approved"}

    monkeypatch.setattr(governance_routes, "_get_governance_hub", lambda: fake_hub)
    monkeypatch.setattr(governance_routes, "approve_live_halt_recovery", fake_approve)
    monkeypatch.setattr(governance_routes, "_record_live_halt_recovery_audit", lambda *_: None)

    resp = _run(
        governance_routes.approve_recovery_request(
            request_id=LIVE_HALT_REQUEST_ID,
            actor=_operator_actor(),
        )
    )

    assert called["actor_id"] == "operator-1"
    assert resp["ok"] is True
    assert resp["message"] == "live_halt_recovery_approved"


def test_approve_live_halt_recovery_offline_resets_state_and_writes_sentinel(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("OPENCLAW_DATA_DIR", str(tmp_path))
    _write_live_halt_snapshot(tmp_path)
    (tmp_path / "live_state.json").write_text(
        json.dumps({
            "balance": 9357.59,
            "initial_balance": 10000.0,
            "peak_balance": 10000.0,
            "total_realized_pnl": -642.41,
            "positions": [],
        }),
        encoding="utf-8",
    )

    async def fake_ipc_reset():
        return {}

    async def fake_ipc_unhalt():
        return {}

    monkeypatch.setattr(live_halt_recovery, "_try_ipc_reset_live", fake_ipc_reset)
    monkeypatch.setattr(live_halt_recovery, "_try_ipc_unhalt_live", fake_ipc_unhalt)
    monkeypatch.setattr(
        live_halt_recovery,
        "_delete_live_checkpoints",
        lambda: {"ok": True, "deleted_rows": 1, "engine_modes": ["live", "live_demo"]},
    )

    result = _run(live_halt_recovery.approve_live_halt_recovery("operator-1"))

    live_state = json.loads((tmp_path / "live_state.json").read_text(encoding="utf-8"))
    assert result["status"] == "approved"
    assert result["offline_reset"]["ok"] is True
    assert live_state["peak_balance"] == live_state["balance"]
    assert (tmp_path / "live_halt_recovery_approved.json").exists()
    assert live_halt_recovery.build_live_halt_recovery_request() is None
