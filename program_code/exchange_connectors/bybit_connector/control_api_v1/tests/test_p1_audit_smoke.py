"""WP-E4/T-P1-2/3/4 smoke tests for layer2_engine, ai_service, ipc_client.
WP-E4/T-P1-2/3/4 對 layer2_engine、ai_service、ipc_client 的煙霧測試。

These exercise the constructor surface, pure helper functions, and graceful
fallback paths that don't require a running Anthropic API or Rust engine.
本檔案測試構造函式表面、純輔助函式以及不需要 Anthropic API 或 Rust 引擎的優雅降級路徑。
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────
# T-P1-2: layer2_engine.Layer2Engine
# ─────────────────────────────────────────────────────────────────────────

def test_layer2_engine_initial_state():
    from app.layer2_engine import Layer2Engine

    cost_tracker = MagicMock()
    cost_tracker.get_config.return_value = MagicMock()
    engine = Layer2Engine(cost_tracker=cost_tracker)
    assert engine.is_running is False
    assert engine.get_current_session() is None


def test_layer2_engine_reset_anthropic_client_idempotent():
    from app.layer2_engine import _get_anthropic_client, reset_anthropic_client

    # Calling reset twice should not raise even if no client was created.
    # 連續重置兩次不應拋異常。
    reset_anthropic_client()
    reset_anthropic_client()
    # _get_anthropic_client either returns a client or None — both are valid.
    result = _get_anthropic_client()
    assert result is None or hasattr(result, "messages")


@pytest.mark.asyncio
async def test_layer2_engine_l1_triage_handles_no_client(monkeypatch):
    """When the Anthropic client is unavailable, l1_triage should fall back."""
    from app.layer2_engine import Layer2Engine

    cost_tracker = MagicMock()
    cost_tracker.get_config.return_value = MagicMock()
    engine = Layer2Engine(cost_tracker=cost_tracker)

    # Force both upstream paths unavailable.
    # 強制 Anthropic 與本地 Ollama 都不可用。
    monkeypatch.setattr("app.layer2_engine._get_anthropic_client", lambda: None)
    fake_local = AsyncMock(return_value={"worth_investigating": False, "reason": "stub"})
    monkeypatch.setattr(engine, "_l1_triage_local", fake_local)

    result = await engine.l1_triage(context={"symbol": "BTCUSDT"})
    assert isinstance(result, dict)
    assert "worth_investigating" in result


# ─────────────────────────────────────────────────────────────────────────
# T-P1-3: ai_service.AIService
# ─────────────────────────────────────────────────────────────────────────

def test_ai_service_resolve_socket_path_explicit_wins(monkeypatch):
    from app.ai_service import _resolve_socket_path

    monkeypatch.setenv("OPENCLAW_AI_SERVICE_SOCKET", "/from/env.sock")
    assert _resolve_socket_path("/explicit.sock") == "/explicit.sock"


def test_ai_service_resolve_socket_path_env_fallback(monkeypatch):
    from app.ai_service import _resolve_socket_path

    monkeypatch.setenv("OPENCLAW_AI_SERVICE_SOCKET", "/from/env.sock")
    assert _resolve_socket_path(None) == "/from/env.sock"


def test_ai_service_resolve_socket_path_default(monkeypatch):
    from app.ai_service import _resolve_socket_path

    monkeypatch.delenv("OPENCLAW_AI_SERVICE_SOCKET", raising=False)
    path = _resolve_socket_path(None)
    assert path.endswith(".sock")


def test_ai_service_initial_state():
    from app.ai_service import AIService

    svc = AIService()
    assert svc._stats["total_dispatches"] == 0
    assert svc._stats["errors"] == 0
    # All five agent handlers must be registered.
    # 五個 Agent 處理器必須全部註冊。
    for method in (
        "strategist_evaluate",
        "analyst_evaluate",
        "conductor_evaluate",
        "scout_scan",
        "guardian_check",
    ):
        assert method in svc._handlers


def test_ai_service_strategist_prompt_exposes_wide_adjustment_skill():
    from app.ai_service import AIService

    prompt = AIService._build_strategist_prompt(
        strategy="ma_crossover",
        symbol="BTCUSDT",
        win_rate=0.31,
        avg_pnl=-1.25,
        fill_count=42,
        current_params={"cooldown_ms": 100_000},
        param_ranges=[
            {
                "name": "cooldown_ms",
                "min": 1_000,
                "max": 1_000_000,
                "agent_adjustable": True,
            }
        ],
        normal_delta_pct=0.30,
        max_delta_pct=0.50,
    )

    assert "Strategist Skill: Wide Parameter Adjustment" in prompt
    assert "normal_range=[70000, 130000]" in prompt
    assert "wide_skill_range=[50000, 150000]" in prompt
    assert "This is not an approval gate" in prompt
    assert "±30% cap" not in prompt


def test_ai_service_strategist_prompt_uses_runtime_max_delta():
    from app.ai_service import AIService

    prompt = AIService._build_strategist_prompt(
        strategy="grid_trading",
        symbol="ETHUSDT",
        win_rate=0.2,
        avg_pnl=-2.0,
        fill_count=80,
        current_params={"grid_spacing_pct": 0.02},
        param_ranges=[
            {
                "name": "grid_spacing_pct",
                "min": 0.001,
                "max": 0.05,
                "agent_adjustable": True,
            }
        ],
        normal_delta_pct=0.30,
        max_delta_pct=0.40,
    )

    assert "normal_range=[0.014, 0.026]" in prompt
    assert "wide_skill_range=[0.012, 0.028]" in prompt
    assert "30%-40%" in prompt


@pytest.mark.asyncio
async def test_ai_service_dispatch_unknown_method_returns_error():
    from app.ai_service import AIService

    svc = AIService()
    result = await svc.dispatch("nonexistent_method", {})
    assert isinstance(result, dict)
    # Should report an error rather than raise.
    # 應返回錯誤而非拋出異常。
    assert "error" in result or result.get("status") == "error"
    assert svc._stats["total_dispatches"] == 1


# ─────────────────────────────────────────────────────────────────────────
# T-P1-4: ipc_client.EngineIPCClient
# ─────────────────────────────────────────────────────────────────────────

def test_engine_ipc_client_initial_state(tmp_path):
    from app.ipc_client import EngineIPCClient

    socket_path = str(tmp_path / "smoke.sock")
    client = EngineIPCClient(socket_path=socket_path)
    assert client.is_connected is False
    # Engine considered available until fallback explicitly trips.
    # 在降級模式被觸發前 engine 視為可用。
    assert client.is_engine_available is True
    assert client._socket_path == socket_path


def test_engine_ipc_client_socket_env_fallback(monkeypatch):
    from app.ipc_client import EngineIPCClient

    monkeypatch.setenv("OPENCLAW_IPC_SOCKET", "/env/path.sock")
    client = EngineIPCClient()
    assert client._socket_path == "/env/path.sock"


@pytest.mark.asyncio
async def test_engine_ipc_client_call_disconnected_raises():
    from app.ipc_client import EngineDisconnectedError, EngineIPCClient

    client = EngineIPCClient(socket_path="/nonexistent/test.sock")
    with pytest.raises(EngineDisconnectedError):
        await client.call("get_state")
