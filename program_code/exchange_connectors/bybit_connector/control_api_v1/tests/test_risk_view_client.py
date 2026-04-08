"""
Tests for RiskViewClient (ARCH-RC1 1C-3-B).
ARCH-RC1 1C-3-B：RiskViewClient 單元測試。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.risk_view_client import RiskViewClient


class FakeIPCClient:
    """Minimal in-memory IPC stub recording calls + serving canned responses."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any] | None]] = []
        self.responses: dict[str, Any] = {}
        self.raise_on: set[str] = set()

    async def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self.calls.append((method, params))
        if method in self.raise_on:
            raise RuntimeError(f"simulated failure for {method}")
        return self.responses.get(method, {})


@pytest.fixture
def fake_ipc() -> FakeIPCClient:
    return FakeIPCClient()


@pytest.fixture
def client(fake_ipc: FakeIPCClient) -> RiskViewClient:
    return RiskViewClient(fake_ipc)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── reads ────────────────────────────────────────────────────────────────────


def test_initial_cache_empty():
    c = RiskViewClient(None)
    assert c.config == {}
    assert c.config_version == 0
    assert c.get_status() == {}
    assert c.get_full_config() == {}


def test_refresh_config_populates_cache(client, fake_ipc):
    fake_ipc.responses["get_risk_config"] = {
        "config": {"limits": {"max_leverage": 5.0}},
        "version": 7,
    }
    snapshot = _run(client.refresh_config())
    assert snapshot == {"limits": {"max_leverage": 5.0}}
    assert client.config_version == 7
    assert client.config["limits"]["max_leverage"] == 5.0


def test_refresh_runtime_status_populates_cache(client, fake_ipc):
    fake_ipc.responses["get_risk_runtime_status"] = {
        "governor_tier": "Cautious",
        "consecutive_losses_by_symbol": {"BTCUSDT": 2},
        "boot_cooldown_remaining_ms": 1500,
        "paper_paused": False,
        "session_halted": False,
    }
    snap = _run(client.refresh_runtime_status())
    assert snap["governor_tier"] == "Cautious"
    status = client.get_status()
    assert status["consecutive_losses_by_symbol"]["BTCUSDT"] == 2


def test_refresh_failure_keeps_old_cache(client, fake_ipc):
    fake_ipc.responses["get_risk_config"] = {"config": {"a": 1}, "version": 1}
    _run(client.refresh_config())
    fake_ipc.raise_on.add("get_risk_config")
    _run(client.refresh_config())  # should not raise
    assert client.config == {"a": 1}  # untouched
    assert client.config_version == 1


def test_get_agent_params_from_snapshot(client, fake_ipc):
    fake_ipc.responses["get_risk_config"] = {
        "config": {"agent_p2": {"position_size_multiplier": 0.5, "cool_off_minutes": 15}},
        "version": 1,
    }
    _run(client.refresh_config())
    p = client.get_agent_params()
    assert p["position_size_multiplier"] == 0.5
    assert p["cool_off_minutes"] == 15
    # Empty cache returns empty dict, never KeyError
    # 空 cache 回空 dict，不丟 KeyError
    c2 = RiskViewClient(None)
    assert c2.get_agent_params() == {}


def test_get_category_config_derives_from_overrides(client, fake_ipc):
    fake_ipc.responses["get_risk_config"] = {
        "config": {"overrides": {"linear": {"max_leverage": 3.0}, "spot": {}}},
        "version": 1,
    }
    _run(client.refresh_config())
    assert client.get_category_config("linear") == {"max_leverage": 3.0}
    assert client.get_category_config("nonexistent") == {}


# ── writes ───────────────────────────────────────────────────────────────────


def test_update_global_config_calls_patch_with_operator(client, fake_ipc):
    fake_ipc.responses["patch_risk_config"] = {"version": 2}
    _run(client.update_global_config({"limits": {"max_leverage": 4.0}}))
    methods = [c[0] for c in fake_ipc.calls]
    assert "patch_risk_config" in methods
    patch_call = next(c for c in fake_ipc.calls if c[0] == "patch_risk_config")
    assert patch_call[1] == {
        "patch": {"limits": {"max_leverage": 4.0}},
        "source": "operator",
    }
    # post-write refresh
    assert "get_risk_config" in methods


def test_update_category_config_wraps_patch(client, fake_ipc):
    _run(client.update_category_config("linear", {"max_leverage": 2.5}))
    patch_call = next(c for c in fake_ipc.calls if c[0] == "patch_risk_config")
    assert patch_call[1]["patch"] == {"overrides": {"linear": {"max_leverage": 2.5}}}
    assert patch_call[1]["source"] == "operator"


def test_agent_adjust_uses_agent_source(client, fake_ipc):
    _run(client.agent_adjust({"agent_p2": {"position_size_multiplier": 0.5}}))
    patch_call = next(c for c in fake_ipc.calls if c[0] == "patch_risk_config")
    assert patch_call[1]["source"] == "agent"


def test_unhalt_session_calls_resume_paper(client, fake_ipc):
    fake_ipc.responses["resume_paper"] = {"message": "resumed"}
    out = _run(client.unhalt_session())
    assert out == {"message": "resumed"}
    methods = [c[0] for c in fake_ipc.calls]
    assert "resume_paper" in methods
    # post-unhalt refresh runtime status
    # 解除 halt 後刷新 runtime status
    assert "get_risk_runtime_status" in methods


def test_unhalt_session_no_ipc():
    c = RiskViewClient(None)
    assert _run(c.unhalt_session()) == {}


def test_clear_consecutive_losses_calls_ipc(client, fake_ipc):
    fake_ipc.responses["clear_consecutive_losses"] = {"result": "cleared 2 symbol(s)"}
    out = _run(client.clear_consecutive_losses())
    assert out == {"result": "cleared 2 symbol(s)"}
    assert any(c[0] == "clear_consecutive_losses" for c in fake_ipc.calls)
    # post-clear refresh
    assert any(c[0] == "get_risk_runtime_status" for c in fake_ipc.calls)


def test_force_governor_tier_tighter_calls_ipc(client, fake_ipc):
    fake_ipc.responses["force_governor_tier_tighter"] = {
        "from": "NORMAL", "to": "CAUTIOUS", "reason": "manual probe"
    }
    out = _run(client.force_governor_tier_tighter("CAUTIOUS", "manual probe"))
    assert out["to"] == "CAUTIOUS"
    methods = [c[0] for c in fake_ipc.calls]
    assert "force_governor_tier_tighter" in methods
    # post-call refresh
    assert "get_risk_runtime_status" in methods
    # Check params payload
    call = next(c for c in fake_ipc.calls if c[0] == "force_governor_tier_tighter")
    assert call[1] == {"target_tier": "CAUTIOUS", "reason": "manual probe"}


def test_force_governor_tier_looser_calls_ipc(client, fake_ipc):
    fake_ipc.responses["force_governor_tier_looser"] = {
        "from": "CAUTIOUS", "to": "NORMAL", "reason_code": "false_positive"
    }
    out = _run(client.force_governor_tier_looser("NORMAL", "false_positive", "tested locally"))
    assert out["reason_code"] == "false_positive"
    call = next(c for c in fake_ipc.calls if c[0] == "force_governor_tier_looser")
    assert call[1] == {
        "target_tier": "NORMAL",
        "reason_code": "false_positive",
        "notes": "tested locally",
    }


def test_force_governor_overrides_no_ipc():
    c = RiskViewClient(None)
    assert _run(c.force_governor_tier_tighter("CAUTIOUS", "x")) == {}
    assert _run(c.force_governor_tier_looser("NORMAL", "false_positive")) == {}


def test_no_ipc_client_safe():
    """RiskViewClient(None) should not crash on any read or write call."""
    c = RiskViewClient(None)
    _run(c.refresh_config())
    _run(c.refresh_runtime_status())
    out = _run(c.update_global_config({"limits": {"max_leverage": 4.0}}))
    assert out == {}
    out2 = _run(c.clear_consecutive_losses())
    assert out2 == {}
