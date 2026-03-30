"""
Tests for Ollama/L1 Infrastructure Integration
Ollama/L1 基础设施集成测试

Covers:
  - OllamaClient HTTP communication (with mocked networking)
  - Ollama response parsing and error handling
  - Model availability detection
  - Specialized methods (classify, judge_edge)
  - LocalLLMSearchProvider integration
  - L1TriageLocal fallback logic in Layer2Engine
  - Cost tracking (always zero for local inference)
  - Singleton instance management
  - Configuration from environment variables
  - Retry logic on transient failures
  - Async integration with asyncio.wait_for timeouts
"""

import asyncio
import json
import os
import sys
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ollama_client import (
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    OllamaClient,
    OllamaConfig,
    OllamaResponse,
    get_ollama_client,
    reset_ollama_client,
)
from app.layer2_tools import LocalLLMSearchProvider
from app.layer2_engine import Layer2Engine


# ═══════════════════════════════════════════════════════════════════════════════
# TestOllamaClient Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def ollama_config():
    """Default Ollama config / 默认 Ollama 配置"""
    return OllamaConfig(
        base_url="http://localhost:11434",
        model="qwen3.5:27b-q4_K_M",
        timeout_seconds=30,
        temperature=0.3,
        max_retries=1,
    )


@pytest.fixture
def ollama_client(ollama_config):
    """Fresh Ollama client / 全新 Ollama 客户端"""
    return OllamaClient(config=ollama_config)


@pytest.fixture
def mock_ollama_response_body():
    """Mock Ollama /api/generate response body / 模拟 Ollama /api/generate 响应体"""
    return {
        "model": "qwen3.5:27b-q4_K_M",
        "response": "BTCUSDT shows strong uptrend with volume confirmation. Edge exists.",
        "eval_count": 45,
        "eval_duration": 2500000000,  # nanoseconds
        "total_duration": 3000000000,
    }


@pytest.fixture
def mock_chat_response_body():
    """Mock Ollama /api/chat response body / 模拟 Ollama /api/chat 响应体"""
    return {
        "model": "qwen3.5:27b-q4_K_M",
        "message": {
            "role": "assistant",
            "content": "The market is consolidating. Recommend waiting for breakout confirmation.",
        },
        "eval_count": 32,
        "eval_duration": 1800000000,
        "total_duration": 2000000000,
    }


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset Ollama singleton before each test / 在每个测试前重置 Ollama 单例"""
    reset_ollama_client()
    yield
    reset_ollama_client()


# ═══════════════════════════════════════════════════════════════════════════════
# TestOllamaClient — Unit Tests with Mocked HTTP
# ═══════════════════════════════════════════════════════════════════════════════


class TestOllamaClient:
    """OllamaClient unit tests with mocked HTTP / 使用模拟 HTTP 的单元测试"""

    def test_generate_success(self, ollama_client, mock_ollama_response_body):
        """
        Test: generate() returns valid OllamaResponse on success.
        测试：generate() 成功时返回有效的 OllamaResponse。
        """
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_ollama_response_body).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = ollama_client.generate("Analyze BTCUSDT market trend")

        assert result.success is True
        assert result.text == "BTCUSDT shows strong uptrend with volume confirmation. Edge exists."
        assert result.model == "qwen3.5:27b-q4_K_M"
        assert result.eval_count == 45
        assert result.latency_ms > 0
        assert result.error is None

    def test_generate_timeout(self, ollama_client):
        """
        Test: generate() gracefully handles TimeoutError.
        测试：generate() 优雅地处理超时。
        """
        with patch("urllib.request.urlopen", side_effect=TimeoutError("Connection timed out")):
            result = ollama_client.generate("Test prompt", timeout=5)

        assert result.success is False
        assert result.text == ""
        assert "Timeout" in result.error
        assert result.cost_usd == 0.0

    def test_generate_connection_error(self, ollama_client):
        """
        Test: generate() gracefully handles URLError.
        测试：generate() 优雅地处理连接错误。
        """
        import urllib.error

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("Connection refused"),
        ):
            result = ollama_client.generate("Test prompt")

        assert result.success is False
        assert "Connection error" in result.error
        assert result.cost_usd == 0.0

    def test_is_available_with_model(self, ollama_client):
        """
        Test: is_available() returns True when target model is present.
        测试：当目标模型存在时，is_available() 返回 True。
        """
        tags_response = {
            "models": [
                {"name": "llama2:7b"},
                {"name": "qwen3.5:27b-q4_K_M"},
                {"name": "mistral:7b"},
            ]
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(tags_response).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None

        with patch("urllib.request.urlopen", return_value=mock_response):
            available = ollama_client.is_available(force_check=True)

        assert available is True

    def test_is_available_no_model(self, ollama_client):
        """
        Test: is_available() returns False when target model not found.
        测试：当目标模型未找到时，is_available() 返回 False。
        """
        tags_response = {
            "models": [
                {"name": "llama2:7b"},
                {"name": "mistral:7b"},
            ]
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(tags_response).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None

        with patch("urllib.request.urlopen", return_value=mock_response):
            available = ollama_client.is_available(force_check=True)

        assert available is False

    def test_is_available_server_down(self, ollama_client):
        """
        Test: is_available() returns False when server is unreachable.
        测试：当服务器不可达时，is_available() 返回 False。
        """
        import urllib.error

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("Connection refused"),
        ):
            available = ollama_client.is_available(force_check=True)

        assert available is False

    def test_classify_returns_category(self, ollama_client):
        """
        Test: classify() extracts category from response.
        测试：classify() 从响应中提取类别。
        """
        classify_response = {
            "model": "qwen3.5:27b-q4_K_M",
            "response": "bullish",
            "eval_count": 12,
            "eval_duration": 800000000,
            "total_duration": 900000000,
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(classify_response).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = ollama_client.classify("BTCUSDT up 5%", categories=["bullish", "bearish", "neutral"])

        assert result.success is True
        assert "bullish" in result.text.lower()

    def test_judge_edge_returns_json(self, ollama_client):
        """
        Test: judge_edge() returns valid JSON response.
        测试：judge_edge() 返回有效的 JSON 响应。
        """
        edge_response = {
            "model": "qwen3.5:27b-q4_K_M",
            "response": '{"has_edge": true, "confidence": 0.72, "reason": "Strong trend with volume"}',
            "eval_count": 28,
            "eval_duration": 1600000000,
            "total_duration": 1800000000,
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(edge_response).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = ollama_client.judge_edge("BTC in uptrend, vol up 30%")

        assert result.success is True
        # Response text contains JSON that caller can parse
        json_data = json.loads(result.text)
        assert json_data["has_edge"] is True
        assert json_data["confidence"] == 0.72

    def test_cost_always_zero(self, ollama_client, mock_ollama_response_body):
        """
        Test: OllamaResponse.cost_usd is always 0.0.
        测试：OllamaResponse.cost_usd 始终为 0.0。
        """
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_ollama_response_body).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = ollama_client.generate("Any prompt")

        assert result.cost_usd == 0.0

    def test_singleton_reuse(self):
        """
        Test: get_ollama_client() returns same instance across calls.
        测试：get_ollama_client() 在多次调用中返回相同实例。
        """
        client1 = get_ollama_client()
        client2 = get_ollama_client()
        assert client1 is client2

    def test_config_from_env(self, monkeypatch):
        """
        Test: OllamaConfig reads environment variables.
        测试：OllamaConfig 从环境变量中读取配置。
        """
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://custom:11434")
        monkeypatch.setenv("OLLAMA_MODEL", "custom-model:7b")
        monkeypatch.setenv("OLLAMA_TIMEOUT", "45")

        config = OllamaConfig()
        assert config.base_url == "http://custom:11434"
        assert config.model == "custom-model:7b"
        assert config.timeout_seconds == 45

    def test_retry_on_failure(self, ollama_client, mock_ollama_response_body):
        """
        Test: generate() retries on transient URLError.
        测试：generate() 在临时 URLError 时重试。
        """
        import urllib.error

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_ollama_response_body).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None

        # First call fails, second succeeds
        with patch(
            "urllib.request.urlopen",
            side_effect=[
                urllib.error.URLError("Temporary failure"),
                mock_response,
            ],
        ):
            result = ollama_client.generate("Test prompt")

        assert result.success is True
        assert result.text == "BTCUSDT shows strong uptrend with volume confirmation. Edge exists."

    def test_availability_caching(self, ollama_client):
        """
        Test: is_available() caches result for 60 seconds.
        测试：is_available() 缓存结果 60 秒。
        """
        tags_response = {"models": [{"name": "qwen3.5:27b-q4_K_M"}]}
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(tags_response).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            # First check hits network
            result1 = ollama_client.is_available(force_check=True)
            assert result1 is True
            assert mock_urlopen.call_count == 1

            # Second check uses cache (no network call)
            result2 = ollama_client.is_available(force_check=False)
            assert result2 is True
            assert mock_urlopen.call_count == 1  # Still 1, not 2

            # Force check bypasses cache
            result3 = ollama_client.is_available(force_check=True)
            assert result3 is True
            assert mock_urlopen.call_count == 2

    def test_chat_multi_turn(self, ollama_client, mock_chat_response_body):
        """
        Test: chat() method for multi-turn conversations.
        测试：chat() 方法用于多轮对话。
        """
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_chat_response_body).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None

        messages = [
            {"role": "user", "content": "What is BTC price trend?"},
            {"role": "assistant", "content": "BTC is up 5% in last hour."},
            {"role": "user", "content": "Should we trade?"},
        ]

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            result = ollama_client.chat(messages, system="You are a trading analyst.")

        assert result.success is True
        assert "consolidating" in result.text.lower()
        # Verify the system prompt was included in payload
        call_args = mock_urlopen.call_args
        request_obj = call_args[0][0]
        payload = json.loads(request_obj.data.decode("utf-8"))
        assert "messages" in payload
        assert len(payload["messages"]) == 4  # system + 3 messages

    def test_list_models(self, ollama_client):
        """
        Test: list_models() returns available model names.
        测试：list_models() 返回可用的模型名称。
        """
        tags_response = {
            "models": [
                {"name": "llama2:7b"},
                {"name": "qwen3.5:27b-q4_K_M"},
                {"name": "mistral:7b"},
            ]
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(tags_response).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None

        with patch("urllib.request.urlopen", return_value=mock_response):
            models = ollama_client.list_models()

        assert len(models) == 3
        assert "qwen3.5:27b-q4_K_M" in models


# ═══════════════════════════════════════════════════════════════════════════════
# TestLocalLLMSearchProvider
# ═══════════════════════════════════════════════════════════════════════════════


class TestLocalLLMSearchProvider:
    """LocalLLMSearchProvider integration tests / 本地 LLM 搜索提供者集成测试"""

    @pytest.mark.asyncio
    async def test_search_uses_ollama_client(self):
        """
        Test: search() uses generate() not subprocess.
        测试：search() 使用 generate() 而不是 subprocess。
        """
        provider = LocalLLMSearchProvider()

        mock_response = OllamaResponse(
            text="Bitcoin is a decentralized digital currency...",
            model="qwen3.5:27b-q4_K_M",
            success=True,
            latency_ms=1200.5,
        )

        with patch("app.layer2_tools.get_ollama_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.generate.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await provider.search("What is Bitcoin?")

        assert result.query == "What is Bitcoin?"
        assert len(result.results) == 1
        assert result.results[0].snippet == "Bitcoin is a decentralized digital currency..."
        assert result.provider_used == "LOCAL_LLM"
        assert result.cost_usd == 0.0
        mock_client.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_available_delegates_to_client(self):
        """
        Test: is_available() calls ollama_client.is_available().
        测试：is_available() 调用 ollama_client.is_available()。
        """
        provider = LocalLLMSearchProvider()

        with patch("app.layer2_tools.get_ollama_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.is_available.return_value = True
            mock_get_client.return_value = mock_client

            available = provider.is_available()

        assert available is True
        mock_client.is_available.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_ollama_failure_returns_error(self):
        """
        Test: search() returns error response when Ollama fails.
        测试：当 Ollama 失败时，search() 返回错误响应。
        """
        provider = LocalLLMSearchProvider()

        mock_response = OllamaResponse(
            text="",
            model="qwen3.5:27b-q4_K_M",
            success=False,
            latency_ms=150.0,
            error="Ollama connection timeout",
        )

        with patch("app.layer2_tools.get_ollama_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.generate.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await provider.search("Test query")

        assert result.error is not None
        assert "Ollama connection timeout" in result.error
        assert len(result.results) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# TestL1TriageLocalFallback
# ═══════════════════════════════════════════════════════════════════════════════


class TestL1TriageLocalFallback:
    """L1 triage local fallback tests / L1 本地分诊回退测试"""

    @pytest.mark.asyncio
    async def test_triage_falls_back_to_local(self):
        """
        Test: l1_triage() falls back to _l1_triage_local when Anthropic unavailable.
        测试：当 Anthropic 不可用时，l1_triage() 回退到 _l1_triage_local。
        """
        # Create minimal engine
        cost_tracker = MagicMock()
        cost_tracker.get_config.return_value = MagicMock()

        engine = Layer2Engine(
            cost_tracker=cost_tracker,
            paper_engine=MagicMock(),
            shadow_consumer=MagicMock(),
        )

        mock_ollama_response = OllamaResponse(
            text='{"worth_investigating": true}',
            model="qwen3.5:27b-q4_K_M",
            success=True,
            latency_ms=850.0,
        )

        with patch("app.layer2_engine._get_anthropic_client", return_value=None):
            with patch("app.layer2_engine.get_ollama_client") as mock_get_ollama:
                mock_client = MagicMock()
                mock_client.is_available.return_value = True
                mock_client.generate.return_value = mock_ollama_response
                mock_get_ollama.return_value = mock_client

                result = await engine.l1_triage(context={"price": 50000})

        assert result["worth_investigating"] is True
        assert result["triage_cost_usd"] == 0.0
        assert result["triage_source"] == "local_ollama"

    @pytest.mark.asyncio
    async def test_triage_local_success(self):
        """
        Test: _l1_triage_local parses successful Ollama response with JSON.
        测试：_l1_triage_local 解析成功的 Ollama JSON 响应。
        """
        cost_tracker = MagicMock()
        cost_tracker.get_config.return_value = MagicMock()

        engine = Layer2Engine(
            cost_tracker=cost_tracker,
            paper_engine=MagicMock(),
            shadow_consumer=MagicMock(),
        )

        mock_response = OllamaResponse(
            text='{"worth_investigating": true, "reason": "Strong signal detected"}',
            model="qwen3.5:27b-q4_K_M",
            success=True,
            latency_ms=720.5,
        )

        with patch("app.layer2_engine.get_ollama_client") as mock_get_ollama:
            mock_client = MagicMock()
            mock_client.is_available.return_value = True
            mock_client.generate.return_value = mock_response
            mock_get_ollama.return_value = mock_client

            result = await engine._l1_triage_local("Test market context")

        assert result["worth_investigating"] is True
        assert result["reason"] == "Strong signal detected"
        assert result["triage_cost_usd"] == 0.0
        assert result["triage_latency_ms"] == 720.5

    @pytest.mark.asyncio
    async def test_triage_local_freetext_parsing(self):
        """
        Test: _l1_triage_local handles non-JSON freetext responses.
        测试：_l1_triage_local 处理非 JSON 的自由文本响应。
        """
        cost_tracker = MagicMock()
        cost_tracker.get_config.return_value = MagicMock()

        engine = Layer2Engine(
            cost_tracker=cost_tracker,
            paper_engine=MagicMock(),
            shadow_consumer=MagicMock(),
        )

        # Response is not JSON, contains "yes" keyword
        mock_response = OllamaResponse(
            text="Yes, this is worth investigating. Market shows strong momentum.",
            model="qwen3.5:27b-q4_K_M",
            success=True,
            latency_ms=650.0,
        )

        with patch("app.layer2_engine.get_ollama_client") as mock_get_ollama:
            mock_client = MagicMock()
            mock_client.is_available.return_value = True
            mock_client.generate.return_value = mock_response
            mock_get_ollama.return_value = mock_client

            result = await engine._l1_triage_local("Test context")

        assert result["worth_investigating"] is True
        assert "yes" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_triage_local_freetext_negative(self):
        """
        Test: _l1_triage_local detects negative intent in freetext.
        测试：_l1_triage_local 检测自由文本中的否定意图。
        """
        cost_tracker = MagicMock()
        cost_tracker.get_config.return_value = MagicMock()

        engine = Layer2Engine(
            cost_tracker=cost_tracker,
            paper_engine=MagicMock(),
            shadow_consumer=MagicMock(),
        )

        mock_response = OllamaResponse(
            text="No clear setup. Not worth investigating at this time.",
            model="qwen3.5:27b-q4_K_M",
            success=True,
            latency_ms=580.0,
        )

        with patch("app.layer2_engine.get_ollama_client") as mock_get_ollama:
            mock_client = MagicMock()
            mock_client.is_available.return_value = True
            mock_client.generate.return_value = mock_response
            mock_get_ollama.return_value = mock_client

            result = await engine._l1_triage_local("Test context")

        assert result["worth_investigating"] is False

    @pytest.mark.asyncio
    async def test_triage_local_ollama_unavailable(self):
        """
        Test: _l1_triage_local returns error when Ollama unavailable.
        测试：当 Ollama 不可用时，_l1_triage_local 返回错误。
        """
        cost_tracker = MagicMock()
        cost_tracker.get_config.return_value = MagicMock()

        engine = Layer2Engine(
            cost_tracker=cost_tracker,
            paper_engine=MagicMock(),
            shadow_consumer=MagicMock(),
        )

        with patch("app.layer2_engine.get_ollama_client") as mock_get_ollama:
            mock_client = MagicMock()
            mock_client.is_available.return_value = False
            mock_get_ollama.return_value = mock_client

            result = await engine._l1_triage_local("Test context")

        assert result["worth_investigating"] is False
        assert result["error"] is True
        assert "Ollama not available" in result["reason"]
        assert result["triage_cost_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_triage_local_timeout(self):
        """
        Test: _l1_triage_local handles asyncio.wait_for timeout.
        测试：_l1_triage_local 处理 asyncio.wait_for 超时。
        """
        cost_tracker = MagicMock()
        cost_tracker.get_config.return_value = MagicMock()

        engine = Layer2Engine(
            cost_tracker=cost_tracker,
            paper_engine=MagicMock(),
            shadow_consumer=MagicMock(),
        )

        async def slow_generate(*args, **kwargs):
            await asyncio.sleep(60)  # Sleep longer than timeout
            return OllamaResponse(text="", model="", success=False, latency_ms=0)

        with patch("app.layer2_engine.get_ollama_client") as mock_get_ollama:
            mock_client = MagicMock()
            mock_client.is_available.return_value = True
            mock_client.generate = slow_generate
            mock_get_ollama.return_value = mock_client

            # This should timeout
            result = await asyncio.wait_for(
                engine._l1_triage_local("Test context"),
                timeout=0.1,  # Very short timeout
            )

        # When timeout occurs, function catches asyncio.TimeoutError
        # and returns error dict
        assert result["worth_investigating"] is False
        assert result["error"] is True
        assert result["triage_cost_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_triage_cost_zero_for_local(self):
        """
        Test: Local triage always has triage_cost_usd=0.0.
        测试：本地分诊的 triage_cost_usd 始终为 0.0。
        """
        cost_tracker = MagicMock()
        cost_tracker.get_config.return_value = MagicMock()

        engine = Layer2Engine(
            cost_tracker=cost_tracker,
            paper_engine=MagicMock(),
            shadow_consumer=MagicMock(),
        )

        mock_response = OllamaResponse(
            text='{"worth_investigating": true}',
            model="qwen3.5:27b-q4_K_M",
            success=True,
            latency_ms=900.0,
        )

        with patch("app.layer2_engine.get_ollama_client") as mock_get_ollama:
            mock_client = MagicMock()
            mock_client.is_available.return_value = True
            mock_client.generate.return_value = mock_response
            mock_get_ollama.return_value = mock_client

            result = await engine._l1_triage_local("Context")

        # Verify cost is always zero
        assert result["triage_cost_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_triage_local_response_truncation(self):
        """
        Test: _l1_triage_local truncates long reason text to 200 chars.
        测试：_l1_triage_local 将长的 reason 文本截断为 200 个字符。
        """
        cost_tracker = MagicMock()
        cost_tracker.get_config.return_value = MagicMock()

        engine = Layer2Engine(
            cost_tracker=cost_tracker,
            paper_engine=MagicMock(),
            shadow_consumer=MagicMock(),
        )

        long_text = "x" * 500  # 500 characters

        mock_response = OllamaResponse(
            text=long_text,
            model="qwen3.5:27b-q4_K_M",
            success=True,
            latency_ms=750.0,
        )

        with patch("app.layer2_engine.get_ollama_client") as mock_get_ollama:
            mock_client = MagicMock()
            mock_client.is_available.return_value = True
            mock_client.generate.return_value = mock_response
            mock_get_ollama.return_value = mock_client

            result = await engine._l1_triage_local("Context")

        # Reason should be truncated
        assert len(result["reason"]) <= 200


# ═══════════════════════════════════════════════════════════════════════════════
# TestOllamaResponseProperties
# ═══════════════════════════════════════════════════════════════════════════════


class TestOllamaResponseProperties:
    """OllamaResponse dataclass properties / OllamaResponse 数据类属性"""

    def test_tokens_per_second_calculation(self):
        """
        Test: tokens_per_second correctly calculates throughput.
        测试：tokens_per_second 正确计算吞吐量。
        """
        response = OllamaResponse(
            text="Test response",
            model="qwen",
            success=True,
            latency_ms=1000.0,
            eval_count=100,  # 100 tokens
            eval_duration_ns=1_000_000_000,  # 1 second in nanoseconds
            total_duration_ns=1_100_000_000,
        )

        assert response.tokens_per_second == 100.0  # 100 tokens / 1 second

    def test_tokens_per_second_zero_when_no_eval(self):
        """
        Test: tokens_per_second returns 0 when eval_duration_ns is 0.
        测试：eval_duration_ns 为 0 时 tokens_per_second 返回 0。
        """
        response = OllamaResponse(
            text="Test",
            model="qwen",
            success=True,
            latency_ms=100.0,
            eval_count=0,
            eval_duration_ns=0,
            total_duration_ns=100_000_000,
        )

        assert response.tokens_per_second == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
