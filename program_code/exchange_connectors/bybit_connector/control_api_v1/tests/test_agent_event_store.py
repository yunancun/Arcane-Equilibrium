from __future__ import annotations

from dataclasses import dataclass

import pytest

from app import agent_event_store as aes
from app.agent_event_store import AgentEventStore
from app.multi_agent_framework import AgentMessage, AgentRole, MessageType


@dataclass
class _FakeCursor:
    executes: list[tuple[str, tuple]]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.executes.append((sql, params or ()))


class _FakeConn:
    def __init__(self):
        self.executes: list[tuple[str, tuple]] = []
        self.commits = 0
        self.cursor_obj = _FakeCursor(self.executes)

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1


class _ConnContext:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.fixture
def fake_conn(monkeypatch):
    conn = _FakeConn()
    monkeypatch.setattr(aes, "Json", None)
    monkeypatch.setattr(aes, "get_pg_conn", lambda: _ConnContext(conn))
    return conn


def test_disabled_store_never_writes(fake_conn) -> None:
    store = AgentEventStore(enabled=False)
    msg = AgentMessage(
        sender=AgentRole.SCOUT,
        receiver=AgentRole.GUARDIAN,
        message_type=MessageType.EVENT_ALERT,
        payload={"context_id": "ctx-1"},
    )

    assert store.record_message(msg) is False
    assert fake_conn.executes == []
    assert store.stats.disabled == 1


def test_record_message_redacts_payload(fake_conn) -> None:
    store = AgentEventStore(enabled=True)
    msg = AgentMessage(
        message_id="msg-1",
        sender=AgentRole.SCOUT,
        receiver=AgentRole.GUARDIAN,
        message_type=MessageType.EVENT_ALERT,
        priority=2,
        payload={
            "context_id": "ctx-1",
            "token": "secret-token",
            "nested": {"raw_prompt": "do not store me"},
            "event_type": "cpi",
        },
    )

    assert store.record_message(msg, engine_mode="demo") is True

    assert len(fake_conn.executes) == 1
    _, params = fake_conn.executes[0]
    payload = params[6]
    assert params[1] == "msg-1"
    assert params[7] == "ctx-1"
    assert payload["token"] == "[REDACTED]"
    assert payload["nested"]["raw_prompt"] == "[REDACTED]"
    assert "secret-token" not in str(payload)
    assert "do not store me" not in str(payload)
    assert payload["engine_mode"] == "demo"
    assert fake_conn.commits == 1
    assert store.stats.message_rows == 1


def test_record_state_change_inserts_redacted_details(fake_conn) -> None:
    store = AgentEventStore(enabled=True)

    assert store.record_state_change(
        agent_name="scout",
        from_state="initializing",
        to_state="running",
        trigger_event="start",
        details={"api_secret": "hidden", "source": "test"},
    )

    _, params = fake_conn.executes[0]
    assert params[:4] == ("scout", "initializing", "running", "start")
    assert params[4]["api_secret"] == "[REDACTED]"
    assert store.stats.state_rows == 1


def test_record_ai_invocation_hashes_prompt_and_redacts_details(fake_conn) -> None:
    store = AgentEventStore(enabled=True)

    assert store.record_ai_invocation(
        provider="ollama",
        model="l1_9b",
        tier="L1",
        purpose="strategist_edge_eval",
        prompt_material="raw prompt must be hashed",
        response_material="raw response must be hashed",
        success=True,
        response_summary="ok",
        context_id="ctx-2",
        details={"raw_response": "raw response must not persist", "symbols": ["BTCUSDT"]},
        engine_mode="demo",
    )

    _, params = fake_conn.executes[0]
    assert params[1:5] == ("ollama", "l1_9b", "L1", "strategist_edge_eval")
    assert len(params[5]) == 64
    assert params[11] == "ok"
    assert params[12] == "ctx-2"
    assert params[13]["raw_response"] == "[REDACTED]"
    assert len(params[13]["response_hash"]) == 64
    assert params[14] == "demo"
    assert "raw prompt must be hashed" not in str(params)
    assert "raw response must not persist" not in str(params)
    assert "raw response must be hashed" not in str(params)
    assert store.stats.ai_rows == 1


def test_db_unavailable_is_fail_soft(monkeypatch) -> None:
    store = AgentEventStore(enabled=True)
    monkeypatch.setattr(aes, "get_pg_conn", lambda: _ConnContext(None))

    ok = store.record_state_change(
        agent_name="guardian",
        from_state="initializing",
        to_state="running",
        trigger_event="start",
    )

    assert ok is False
    assert store.stats.write_failures == 1
    assert "record_state_change" in (store.stats.last_error or "")
