from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

_TEST_DIR = Path(__file__).resolve().parent
_CONTROL_API_DIR = _TEST_DIR.parent
if str(_CONTROL_API_DIR) not in sys.path:
    sys.path.insert(0, str(_CONTROL_API_DIR))

from app import governance_routes as gr
from app.governance_routes import governance_router


def _actor() -> SimpleNamespace:
    return SimpleNamespace(actor_id="test-operator", roles={"viewer", "operator"})


@contextmanager
def _pg_unavailable():
    yield None


class _FakeCursor:
    def __init__(self, conn: "_FakeConn") -> None:
        self.conn = conn
        self.description: list[tuple[str]] = []
        self._row: tuple[Any, ...] | None = None

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        q = " ".join(sql.split())
        self.conn.statements.append((q, params))
        self._row = None
        self.description = []
        if q.startswith("SELECT pg_try_advisory_xact_lock"):
            self._row = (True,)
        elif q.startswith("UPDATE system.autonomy_level_config"):
            self.conn.current_level = str((params or ("CONSERVATIVE",))[0])
        elif q.startswith("NOTIFY autonomy_level_changed"):
            pass
        elif q.startswith("SELECT current_level::text AS current_level, last_switched_at"):
            self.description = [
                ("current_level",),
                ("last_switched_at",),
                ("switched_by",),
                ("switch_reason",),
                ("created_at",),
                ("updated_at",),
            ]
            ts = datetime.now(timezone.utc) - timedelta(days=2)
            self._row = (
                self.conn.current_level,
                ts,
                "system_default",
                "cold_start_default_level_conservative",
                ts,
                ts,
            )
        elif q.startswith("SELECT audit_id, switched_at_utc"):
            self.description = [
                ("audit_id",),
                ("switched_at_utc",),
                ("switched_at_local",),
                ("actor",),
                ("actor_role",),
                ("level_before",),
                ("level_after",),
                ("twofa_verify_result",),
                ("twofa_method",),
                ("switch_reason",),
                ("result",),
                ("emergency_override",),
                ("emergency_override_reason",),
                ("notification_slack_status",),
                ("notification_email_status",),
                ("notification_banner_status",),
                ("notification_escalation_result",),
            ]
            ts = datetime.now(timezone.utc) - timedelta(days=2)
            self._row = (
                1,
                ts,
                ts.replace(tzinfo=None),
                "system_default",
                "system_default",
                "CONSERVATIVE",
                "CONSERVATIVE",
                None,
                None,
                "cold_start_default_level_conservative",
                "system_seed",
                False,
                None,
                None,
                None,
                None,
                None,
            )
        elif q.startswith("SELECT current_level::text FROM system.autonomy_level_config"):
            self._row = (self.conn.current_level,)
        elif q.startswith("INSERT INTO system.autonomy_level_switch_audit"):
            self.conn.insert_params.append(params or ())

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._row


class _FakeConn:
    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple[Any, ...] | None]] = []
        self.insert_params: list[tuple[Any, ...]] = []
        self.committed = False
        self.rolled_back = False
        self.current_level = "CONSERVATIVE"

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


@contextmanager
def _fake_pg(conn: _FakeConn):
    yield conn


def _client(monkeypatch, conn_ctx) -> TestClient:
    app = FastAPI()
    app.include_router(governance_router)
    app.dependency_overrides[gr._get_auth_actor] = _actor
    app.dependency_overrides[gr._require_operator_auth] = _actor
    monkeypatch.setattr(gr, "_get_autonomy_pg_conn", lambda: conn_ctx)
    return TestClient(app)


def test_autonomy_state_degrades_when_pg_unavailable(monkeypatch) -> None:
    client = _client(monkeypatch, _pg_unavailable())

    response = client.get("/api/v1/governance/autonomy-level/state")

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["wiring_status"] == "degraded"
    assert body["data"]["current_level"] == "CONSERVATIVE"
    assert "v099_schema_unavailable" in body["data"]["switch_blockers"]


def test_autonomy_state_reads_v099_and_disables_switch_until_gates(monkeypatch) -> None:
    conn = _FakeConn()
    client = _client(monkeypatch, _fake_pg(conn))

    response = client.get("/api/v1/governance/autonomy-level/state")

    assert response.status_code == 200, response.json()
    data = response.json()["data"]
    assert data["wiring_status"] == "pg_path_active"
    assert data["current_level"] == "CONSERVATIVE"
    assert data["target_level"] == "STANDARD"
    assert data["can_switch"] is False
    assert "totp_backend_unavailable" in data["switch_blockers"]
    assert "level2_evidence_gate_not_met" in data["switch_blockers"]
    assert len(data["matrix"]) == 20


def test_autonomy_switch_fails_closed_and_audits_when_totp_backend_missing(monkeypatch) -> None:
    conn = _FakeConn()
    client = _client(monkeypatch, _fake_pg(conn))
    monkeypatch.setattr(gr, "_get_autonomy_pg_conn", lambda: _fake_pg(conn))
    monkeypatch.setattr(
        gr,
        "_autonomy_eligibility_payload",
        lambda: {"eligible": True, "gates": [], "summary": "test eligible"},
    )
    payload = {
        "target_level": "STANDARD",
        "reason": "evidence baseline review text long enough for audit trail",
        "typed_confirm_phrase": "CONFIRM SWITCH",
        "totp_code": "123456",
    }

    response = client.post("/api/v1/governance/autonomy-level/switch", json=payload)

    assert response.status_code == 403
    assert response.json()["detail"]["reason_codes"] == ["twofa_backend_down"]
    assert conn.committed is True
    assert conn.insert_params
    insert = conn.insert_params[0]
    assert insert[3] == "FAIL"
    assert insert[4] == "backend_unreachable"
    assert insert[6] == "twofa_backend_down"


def test_autonomy_switch_blocks_level2_before_totp_when_evidence_missing(monkeypatch) -> None:
    conn = _FakeConn()
    client = _client(monkeypatch, _fake_pg(conn))
    monkeypatch.setattr(gr, "_verify_autonomy_totp", lambda _code: (True, "TOTP", "success"))
    payload = {
        "target_level": "STANDARD",
        "reason": "evidence baseline review text long enough for audit trail",
        "typed_confirm_phrase": "CONFIRM SWITCH",
        "totp_code": "123456",
    }

    response = client.post("/api/v1/governance/autonomy-level/switch", json=payload)

    assert response.status_code == 403
    assert response.json()["detail"]["reason_codes"] == ["level2_evidence_gate_not_met"]
    assert conn.insert_params
    assert conn.insert_params[0][6] == "freeze_active_block"


def test_autonomy_switch_success_audits_and_notifies_when_eligible(monkeypatch) -> None:
    conn = _FakeConn()
    client = _client(monkeypatch, _fake_pg(conn))
    monkeypatch.setattr(gr, "_get_autonomy_pg_conn", lambda: _fake_pg(conn))
    monkeypatch.setattr(
        gr,
        "_autonomy_eligibility_payload",
        lambda: {"eligible": True, "gates": [], "summary": "test eligible"},
    )
    monkeypatch.setattr(gr, "_autonomy_totp_backend_configured", lambda: True)
    monkeypatch.setattr(gr, "_verify_autonomy_totp", lambda _code: (True, "TOTP", "success"))
    payload = {
        "target_level": "STANDARD",
        "reason": "evidence baseline review text long enough for audit trail",
        "typed_confirm_phrase": "CONFIRM SWITCH",
        "totp_code": "123456",
    }

    response = client.post("/api/v1/governance/autonomy-level/switch", json=payload)

    assert response.status_code == 200, response.json()
    assert response.json()["message"] == "autonomy_level_switched"
    assert conn.current_level == "STANDARD"
    assert conn.committed is True
    assert conn.insert_params
    insert = conn.insert_params[0]
    assert insert[3] == "PASS"
    assert insert[4] == "TOTP"
    assert insert[6] == "success"
    assert any(stmt[0].startswith("NOTIFY autonomy_level_changed") for stmt in conn.statements)


def test_autonomy_switch_typed_confirm_mismatch_is_audited(monkeypatch) -> None:
    conn = _FakeConn()
    client = _client(monkeypatch, _fake_pg(conn))
    payload = {
        "target_level": "STANDARD",
        "reason": "evidence baseline review text long enough for audit trail",
        "typed_confirm_phrase": "confirm switch",
        "totp_code": "123456",
    }

    response = client.post("/api/v1/governance/autonomy-level/switch", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"]["reason_codes"] == ["typed_confirm_mismatch"]
    assert conn.insert_params
    assert conn.insert_params[0][6] == "typed_confirm_mismatch"
