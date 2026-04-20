"""
LLM-ABC-MIGRATION-1 · Tests for local_llm_factory
LLM-ABC-MIGRATION-1 · local_llm_factory 測試

Covers:
  - LOCAL_LLM_PROVIDER=ollama  → OllamaClient returned
  - LOCAL_LLM_PROVIDER=lm_studio → LMStudioShimClient returned
  - LOCAL_LLM_PROVIDER=bogus → warning + fallback to Ollama (safe default)
  - LOCAL_LLM_PROVIDER unset → defaults to Ollama
  - heavy=True parity on both providers
  - LMStudioShimClient exposes OllamaClient surface (generate / chat / classify /
    judge_edge / is_available / is_available_async / config.base_url / config.model / model)
  - both-providers-unavailable → fail-soft (is_available() == False, no raise)
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import local_llm_factory as factory
from app.ollama_client import OllamaClient, OllamaResponse, reset_ollama_client


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset both Ollama and LM Studio singletons between tests.
    每個測試前重置兩邊單例。"""
    reset_ollama_client()
    factory.reset_local_llm_singletons()
    yield
    reset_ollama_client()
    factory.reset_local_llm_singletons()


# ─────────────────────────────────────────────────────────────────────────────
# Provider routing / Provider 路由
# ─────────────────────────────────────────────────────────────────────────────


def test_default_provider_is_ollama(monkeypatch):
    """Unset LOCAL_LLM_PROVIDER → Ollama. / 未設 env 走 Ollama。"""
    monkeypatch.delenv("LOCAL_LLM_PROVIDER", raising=False)
    client = factory.get_local_llm_client()
    assert isinstance(client, OllamaClient)


def test_explicit_ollama_provider(monkeypatch):
    monkeypatch.setenv("LOCAL_LLM_PROVIDER", "ollama")
    client = factory.get_local_llm_client()
    assert isinstance(client, OllamaClient)


def test_lm_studio_provider(monkeypatch):
    monkeypatch.setenv("LOCAL_LLM_PROVIDER", "lm_studio")
    client = factory.get_local_llm_client()
    assert isinstance(client, factory.LMStudioShimClient)


def test_unknown_provider_falls_back_to_ollama(monkeypatch, caplog):
    monkeypatch.setenv("LOCAL_LLM_PROVIDER", "bogus_vendor")
    with caplog.at_level("WARNING"):
        client = factory.get_local_llm_client()
    assert isinstance(client, OllamaClient)
    assert any("not recognized" in rec.message for rec in caplog.records)


def test_case_insensitive_provider(monkeypatch):
    monkeypatch.setenv("LOCAL_LLM_PROVIDER", "LM_STUDIO")
    client = factory.get_local_llm_client()
    assert isinstance(client, factory.LMStudioShimClient)


# ─────────────────────────────────────────────────────────────────────────────
# Heavy variant parity / heavy 變體對等
# ─────────────────────────────────────────────────────────────────────────────


def test_heavy_ollama_routes_to_27b(monkeypatch):
    monkeypatch.setenv("LOCAL_LLM_PROVIDER", "ollama")
    heavy = factory.get_local_llm_client(heavy=True)
    assert isinstance(heavy, OllamaClient)
    # 27B singleton has "27b" in its model name
    assert "27b" in heavy.model.lower()


def test_heavy_lm_studio_without_env_reuses_default(monkeypatch):
    """LM_STUDIO_MODEL_HEAVY unset → heavy=True returns default LM Studio client.
    未設 heavy model env → heavy=True 回傳預設 LM Studio client（same singleton）。"""
    monkeypatch.setenv("LOCAL_LLM_PROVIDER", "lm_studio")
    monkeypatch.delenv("LM_STUDIO_MODEL_HEAVY", raising=False)
    default = factory.get_local_llm_client()
    heavy = factory.get_local_llm_client(heavy=True)
    assert default is heavy  # same singleton


def test_heavy_lm_studio_with_env_returns_distinct(monkeypatch):
    monkeypatch.setenv("LOCAL_LLM_PROVIDER", "lm_studio")
    monkeypatch.setenv("LM_STUDIO_MODEL_HEAVY", "qwen3.5-35b-custom")
    default = factory.get_local_llm_client()
    heavy = factory.get_local_llm_client(heavy=True)
    assert default is not heavy
    assert heavy.config.model == "qwen3.5-35b-custom"


# ─────────────────────────────────────────────────────────────────────────────
# LMStudioShimClient surface parity / 接口對齊
# ─────────────────────────────────────────────────────────────────────────────


def test_lm_studio_shim_has_ollama_surface():
    """Shim exposes every attr/method the callers use on OllamaClient.
    Shim 暴露 5 call-site 與 3 agent 使用的全部 OllamaClient 介面。"""
    shim = factory.LMStudioShimClient()
    # attrs
    assert hasattr(shim.config, "base_url")
    assert hasattr(shim.config, "model")
    assert hasattr(shim, "model")
    # methods
    for name in (
        "generate", "chat", "classify", "judge_edge",
        "is_available", "is_available_async",
    ):
        assert callable(getattr(shim, name)), f"missing {name}"


def test_lm_studio_is_available_fail_soft(monkeypatch):
    """Unreachable LM Studio → is_available() returns False, no raise.
    LM Studio 不可達 → is_available() 回 False，不拋異常。"""
    monkeypatch.setenv("LM_STUDIO_BASE_URL", "http://127.0.0.1:9")
    shim = factory.LMStudioShimClient()
    assert shim.is_available(force_check=True) is False


def test_lm_studio_generate_returns_ollama_response_shape():
    """Mocked HTTP → generate() returns OllamaResponse with .text/.success.
    模擬 HTTP 回應 → generate() 回 OllamaResponse 形狀（.text/.success）。"""
    shim = factory.LMStudioShimClient()

    fake_body = json.dumps({
        "id": "x", "choices": [{"message": {"content": "hello"}}],
        "usage": {"total_tokens": 7}, "model": "local-model",
    }).encode()

    class _FakeResp:
        status = 200
        def __init__(self, body): self._body = body
        def read(self): return self._body
        def __enter__(self): return self
        def __exit__(self, *a): return False

    with patch("urllib.request.urlopen", return_value=_FakeResp(fake_body)):
        resp = shim.generate("hi")
    assert isinstance(resp, OllamaResponse)
    assert resp.success is True
    assert resp.text == "hello"
    assert resp.eval_count == 7


def test_lm_studio_generate_fail_soft_on_connection_error():
    """Unreachable LM Studio → generate() returns success=False, no raise.
    LM Studio 不可達 → generate() 回 success=False，不拋異常。"""
    shim = factory.LMStudioShimClient(base_url="http://127.0.0.1:9")
    resp = shim.generate("hi", timeout=1)
    assert isinstance(resp, OllamaResponse)
    assert resp.success is False
    assert resp.error  # non-empty error string


def test_lm_studio_classify_delegates_to_generate():
    shim = factory.LMStudioShimClient()
    with patch.object(shim, "generate", return_value=OllamaResponse(
        text="high", model="local-model", success=True, latency_ms=10.0,
    )) as mock_gen:
        resp = shim.classify("some event", ["low", "medium", "high", "critical"])
    assert resp.success
    assert resp.text == "high"
    assert mock_gen.called
    # temperature forced to 0.1 (OllamaClient.classify parity)
    call = mock_gen.call_args
    assert call.kwargs["temperature"] == 0.1
    assert call.kwargs["max_tokens"] == 32


def test_lm_studio_judge_edge_delegates_to_generate():
    shim = factory.LMStudioShimClient()
    with patch.object(shim, "generate", return_value=OllamaResponse(
        text='{"has_edge": false, "confidence": 0.1, "reason": "noisy"}',
        model="local-model", success=True, latency_ms=12.0,
    )) as mock_gen:
        resp = shim.judge_edge("BTCUSDT context here")
    assert resp.success
    call = mock_gen.call_args
    assert call.kwargs["temperature"] == 0.2
    assert call.kwargs["max_tokens"] == 100
    assert call.kwargs["think"] is False


def test_lm_studio_is_available_async_runs_sync_check():
    shim = factory.LMStudioShimClient(base_url="http://127.0.0.1:9")

    async def _run():
        return await shim.is_available_async(force_check=True)

    result = asyncio.run(_run())
    assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# Singleton semantics / 單例語義
# ─────────────────────────────────────────────────────────────────────────────


def test_lm_studio_singleton_is_reused(monkeypatch):
    monkeypatch.setenv("LOCAL_LLM_PROVIDER", "lm_studio")
    a = factory.get_local_llm_client()
    b = factory.get_local_llm_client()
    assert a is b


def test_reset_singletons_produces_fresh_instance(monkeypatch):
    monkeypatch.setenv("LOCAL_LLM_PROVIDER", "lm_studio")
    a = factory.get_local_llm_client()
    factory.reset_local_llm_singletons()
    b = factory.get_local_llm_client()
    assert a is not b
