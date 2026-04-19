"""
Unit tests for P1-5 A2 `/api/v1/paper/risk/reset-drawdown-baseline` route.
P1-5 A2：`/api/v1/paper/risk/reset-drawdown-baseline` 路由單元測試。

Scope / 範圍：
  - Whitelist gate (invalid engine → 400)
  - Operator role gate (missing role → 403)
  - Successful reset writes a ChangeType.STATE_CHANGE audit entry
  - Audit-log write is fail-soft (hub missing / record_change raises → route
    still succeeds because Rust DB DELETE has already confirmed)
  - IPC failure surfaces as HTTP 500 (not fake-success)

We call the async route function directly with a fake actor + fake
RiskViewClient instead of booting FastAPI — the route body's only coupling
to the framework is `HTTPException`, which we inspect directly.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from app import risk_routes
from app.change_audit_log import ChangeAuditLog, ChangeType
from app.risk_routes import (
    ResetDrawdownBaselineRequest,
    _record_reset_drawdown_audit,
    reset_drawdown_baseline,
)


# ─── helpers ────────────────────────────────────────────────────────────────


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class _FakeRiskViewClient:
    """Minimal stand-in for RiskViewClient — only `reset_drawdown_baseline` +
    `get_status` are touched by the route body.
    最小 RiskViewClient 替身 — 路由只用這兩個方法。"""

    def __init__(self, result: dict[str, Any] | Exception) -> None:
        self._result = result
        self.calls: list[str] = []

    async def reset_drawdown_baseline(self, engine: str) -> dict[str, Any]:
        self.calls.append(engine)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result

    def get_status(self) -> dict[str, Any]:
        return {"governor_tier": "Normal"}


def _operator_actor(actor_id: str = "operator-1") -> SimpleNamespace:
    """Duck-typed actor carrying the two attrs `_require_operator_role` checks."""
    return SimpleNamespace(actor_id=actor_id, roles={"operator"})


def _non_operator_actor() -> SimpleNamespace:
    return SimpleNamespace(actor_id="viewer-1", roles={"viewer"})


@pytest.fixture
def patch_risk_view_client(monkeypatch):
    """Install a FakeRiskViewClient in place of the lazy singleton for one test."""

    def _install(client: _FakeRiskViewClient):
        async def _factory():
            return client

        monkeypatch.setattr(risk_routes, "_get_risk_view_client", _factory)
        return client

    return _install


@pytest.fixture
def audit_hub(monkeypatch):
    """Install a real ChangeAuditLog behind `_get_governance_hub` to verify writes."""
    log = ChangeAuditLog()
    hub = SimpleNamespace(_change_audit_log=log)

    # Patch the lazy import helper inside governance_routes that risk_routes
    # calls via `from .governance_routes import _get_governance_hub`.
    from app import governance_routes  # noqa: PLC0415
    monkeypatch.setattr(governance_routes, "_get_governance_hub", lambda: hub)
    return log


# ─── whitelist gate ─────────────────────────────────────────────────────────


def test_invalid_engine_returns_400(patch_risk_view_client):
    """Non-whitelisted engine name MUST 400 before reaching IPC.
    非白名單 engine 名必須在觸達 IPC 前 400。"""
    client = patch_risk_view_client(_FakeRiskViewClient({"ok": True}))
    body = ResetDrawdownBaselineRequest(engine="hacked", reason="probe")
    with pytest.raises(HTTPException) as exc:
        _run(reset_drawdown_baseline(body=body, actor=_operator_actor()))
    assert exc.value.status_code == 400
    # IPC must NOT have been called — whitelist is the hard gate.
    assert client.calls == []


# ─── operator role gate ────────────────────────────────────────────────────


def test_non_operator_returns_403(patch_risk_view_client):
    """Non-operator (viewer role) MUST 403 — baseline reset is operator-only."""
    client = patch_risk_view_client(_FakeRiskViewClient({"ok": True}))
    body = ResetDrawdownBaselineRequest(engine="demo", reason="probe")
    with pytest.raises(HTTPException) as exc:
        _run(reset_drawdown_baseline(body=body, actor=_non_operator_actor()))
    assert exc.value.status_code == 403
    assert client.calls == []


def test_unauthenticated_actor_returns_401(patch_risk_view_client):
    """Actor missing the `roles` / `actor_id` attrs MUST 401.
    缺少 roles / actor_id 屬性的 actor 必須 401。"""
    patch_risk_view_client(_FakeRiskViewClient({"ok": True}))
    body = ResetDrawdownBaselineRequest(engine="demo", reason="probe")
    bad_actor = SimpleNamespace()  # no roles, no actor_id
    with pytest.raises(HTTPException) as exc:
        _run(reset_drawdown_baseline(body=body, actor=bad_actor))
    assert exc.value.status_code == 401


# ─── happy path + audit write ──────────────────────────────────────────────


def test_happy_path_writes_state_change_audit(patch_risk_view_client, audit_hub):
    """Successful reset MUST write a single STATE_CHANGE entry naming the engine
    and operator actor_id. Root Principle #8 (交易可解釋) lock.
    根原則 #8：每次重置必須寫 STATE_CHANGE 審計。"""
    ipc_result = {
        "engine": "demo",
        "result": "drawdown_baseline_reset",
        "checkpoint_deleted": True,
    }
    client = patch_risk_view_client(_FakeRiskViewClient(ipc_result))
    body = ResetDrawdownBaselineRequest(
        engine="demo",
        reason="demo restart playbook: baseline reset after operator review",
    )
    resp = _run(reset_drawdown_baseline(body=body, actor=_operator_actor("op-42")))

    # Route returns ok shape and forwards engine.
    assert resp["ok"] is True
    assert resp["data"]["engine"] == "demo"
    assert resp["data"]["result"] == ipc_result

    # IPC path: client must have been called with the right engine.
    assert client.calls == ["demo"]

    # Audit: exactly one STATE_CHANGE entry, attributed to the operator, naming
    # both engine and the paper_state_checkpoint table as affected components.
    changes = audit_hub.get_all_changes()
    assert len(changes) == 1
    c = changes[0]
    assert c.change_type == ChangeType.STATE_CHANGE
    assert c.who == "op-42"
    assert "demo" in c.what
    assert "paper_state:demo" in c.affected_components
    assert "trading.paper_state_checkpoint" in c.affected_components


# ─── audit helper fail-soft ─────────────────────────────────────────────────


def test_audit_helper_no_hub_is_soft(monkeypatch, caplog):
    """No governance hub available → WARN logged, no exception raised.
    沒有 hub 時只 WARN，不拋錯（route 仍回成功，因 Rust 端已 DELETE）。"""
    from app import governance_routes  # noqa: PLC0415
    monkeypatch.setattr(governance_routes, "_get_governance_hub", lambda: None)

    import logging  # noqa: PLC0415
    with caplog.at_level(logging.WARNING, logger="app.risk_routes"):
        _record_reset_drawdown_audit(
            who="op-1",
            engine="demo",
            reason="hub missing",
            ipc_response={"ok": True},
        )
    assert any(
        "change_audit_log unavailable" in r.getMessage()
        for r in caplog.records
    )


def test_audit_helper_hub_without_log_is_soft(monkeypatch, caplog):
    """Hub present but `_change_audit_log is None` → WARN, no exception.
    有 hub 但審計日誌 None 時只 WARN，不拋錯。"""
    hub = SimpleNamespace(_change_audit_log=None)
    from app import governance_routes  # noqa: PLC0415
    monkeypatch.setattr(governance_routes, "_get_governance_hub", lambda: hub)

    import logging  # noqa: PLC0415
    with caplog.at_level(logging.WARNING, logger="app.risk_routes"):
        _record_reset_drawdown_audit(
            who="op-1",
            engine="demo",
            reason="log missing",
            ipc_response={"ok": True},
        )
    assert any(
        "change_audit_log unavailable" in r.getMessage()
        for r in caplog.records
    )


def test_audit_helper_record_change_raising_is_soft(monkeypatch, caplog):
    """`record_change` raising MUST NOT crash the helper — route still returns
    success because Rust DB DELETE has already confirmed.
    `record_change` 拋錯時 helper 不能 crash — Rust DB DELETE 已完成即成功。"""

    class _BrokenLog:
        def record_change(self, **_kw):
            raise RuntimeError("disk full")

    hub = SimpleNamespace(_change_audit_log=_BrokenLog())
    from app import governance_routes  # noqa: PLC0415
    monkeypatch.setattr(governance_routes, "_get_governance_hub", lambda: hub)

    import logging  # noqa: PLC0415
    with caplog.at_level(logging.WARNING, logger="app.risk_routes"):
        _record_reset_drawdown_audit(
            who="op-1",
            engine="demo",
            reason="disk drill",
            ipc_response={"ok": True},
        )
    assert any(
        "change_audit_log write failed" in r.getMessage()
        for r in caplog.records
    )


# ─── IPC failure surfaces as HTTP 500 ───────────────────────────────────────


def test_ipc_error_surfaces_as_500(patch_risk_view_client, audit_hub):
    """Rust IPC error → HTTP 500 (not fake-success). Audit log MUST NOT record
    a reset that didn't actually happen.
    Rust IPC 錯誤 → HTTP 500（不假成功）；未發生的重置絕不寫審計。"""
    patch_risk_view_client(_FakeRiskViewClient(RuntimeError("ipc timeout")))
    body = ResetDrawdownBaselineRequest(engine="demo", reason="should fail")
    with pytest.raises(HTTPException) as exc:
        _run(reset_drawdown_baseline(body=body, actor=_operator_actor()))
    assert exc.value.status_code == 500
    assert "rust_engine_unavailable" in exc.value.detail
    # Critical invariant: no audit row for a reset that didn't happen.
    # 關鍵不變量：未發生的重置絕不留審計。
    assert audit_hub.get_all_changes() == []
