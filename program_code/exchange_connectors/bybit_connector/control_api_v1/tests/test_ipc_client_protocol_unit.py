from __future__ import annotations

import json

import pytest

from app.ipc_client import EngineIPCClient, EngineProtocolError


class _FakeReader:
    def __init__(self, response: dict) -> None:
        self._line = json.dumps(response).encode("utf-8") + b"\n"

    async def readline(self) -> bytes:
        return self._line


class _FakeWriter:
    def __init__(self) -> None:
        self.sent: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.sent.append(data)

    async def drain(self) -> None:
        return None


@pytest.mark.asyncio
async def test_engine_ipc_auth_fails_closed_on_response_id_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = EngineIPCClient(socket_path="/tmp/test-fake.sock")
    client._reader = _FakeReader(
        {"jsonrpc": "2.0", "result": {"authenticated": True}, "id": None}
    )
    client._writer = _FakeWriter()
    monkeypatch.setenv("OPENCLAW_IPC_SECRET", "test-secret")

    with pytest.raises(EngineProtocolError) as exc_info:
        await client._authenticate()

    assert exc_info.value.reason == "auth_response_id_mismatch"
    assert exc_info.value.expected_id == 0
    assert exc_info.value.actual_id is None


@pytest.mark.asyncio
async def test_engine_ipc_auth_fails_closed_when_not_authenticated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = EngineIPCClient(socket_path="/tmp/test-fake.sock")
    client._reader = _FakeReader(
        {"jsonrpc": "2.0", "result": {"authenticated": False}, "id": 0}
    )
    client._writer = _FakeWriter()
    monkeypatch.setenv("OPENCLAW_IPC_SECRET", "test-secret")

    with pytest.raises(EngineProtocolError) as exc_info:
        await client._authenticate()

    assert exc_info.value.reason == "auth_response_not_authenticated"
    assert exc_info.value.expected_id == 0
    assert exc_info.value.actual_id == 0


@pytest.mark.asyncio
async def test_engine_ipc_client_fails_closed_on_response_id_mismatch() -> None:
    client = EngineIPCClient(socket_path="/tmp/test-fake.sock")
    client._connected = True
    client._reader = _FakeReader(
        {"jsonrpc": "2.0", "result": {"authenticated": True}, "id": None}
    )
    client._writer = _FakeWriter()

    with pytest.raises(EngineProtocolError) as exc_info:
        await client.call("governance.get_status", timeout=1.0)

    assert exc_info.value.reason == "response_id_mismatch"
    assert exc_info.value.expected_id == 1
    assert exc_info.value.actual_id is None


@pytest.mark.asyncio
async def test_engine_ipc_client_fails_closed_on_missing_result() -> None:
    client = EngineIPCClient(socket_path="/tmp/test-fake.sock")
    client._connected = True
    client._reader = _FakeReader({"jsonrpc": "2.0", "id": 1})
    client._writer = _FakeWriter()

    with pytest.raises(EngineProtocolError) as exc_info:
        await client.call("governance.get_status", timeout=1.0)

    assert exc_info.value.reason == "missing_result"
    assert exc_info.value.expected_id == 1
    assert exc_info.value.actual_id == 1
