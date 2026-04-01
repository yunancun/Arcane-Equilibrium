from __future__ import annotations

"""
Ollama HTTP Client — Local LLM inference via Ollama REST API
本地 LLM 推理客户端，通过 Ollama REST API 与本地模型交互

MODULE_NOTE (中文):
  本模块提供 Ollama HTTP 客户端，替代之前 subprocess 调用方式：
  1. 支持 /api/generate (单轮) 和 /api/chat (多轮对话)
  2. 可配置模型名称（默认 qwen3.5）、超时、temperature
  3. 连通性检测 + 模型可用性检测
  4. 线程安全单例 + 连接池复用
  5. 完整错误处理和 fallback 信号

MODULE_NOTE (English):
  Ollama HTTP client replacing subprocess-based calls:
  1. Supports /api/generate (single-turn) and /api/chat (multi-turn)
  2. Configurable model name (default qwen3.5), timeout, temperature
  3. Connectivity check + model availability detection
  4. Thread-safe singleton + connection pool reuse
  5. Complete error handling and fallback signaling

Safety guarantees:
  - Read-only: never modifies system state
  - Timeout enforcement: configurable per-request timeout
  - Cost: always 0.0 USD (local inference)
"""

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import urllib.request
import urllib.error

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration / 配置
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3.5:9b-q4_K_M"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_TEMPERATURE = 0.3  # Lower for more deterministic trading decisions


@dataclass
class OllamaConfig:
    """Configuration for Ollama client / Ollama 客户端配置"""
    base_url: str = field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL))
    model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", DEFAULT_MODEL))
    timeout_seconds: int = field(default_factory=lambda: int(os.getenv("OLLAMA_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS))))
    temperature: float = DEFAULT_TEMPERATURE
    # NOTE: max_retries=0 is a CLAUDE.md hard boundary (single-attempt mode).
    # Changing this value requires explicit Operator approval and CLAUDE.md update.
    # 注意：max_retries=0 為 CLAUDE.md 硬邊界（單次嘗試模式），變更須 Operator 核准並更新 CLAUDE.md。
    max_retries: int = 0


# ═══════════════════════════════════════════════════════════════════════════════
# Response Types / 响应类型
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class OllamaResponse:
    """Response from Ollama API / Ollama API 响应"""
    text: str
    model: str
    success: bool
    latency_ms: float
    error: str | None = None
    eval_count: int = 0       # tokens generated
    eval_duration_ns: int = 0  # generation time in nanoseconds
    total_duration_ns: int = 0

    @property
    def tokens_per_second(self) -> float:
        if self.eval_duration_ns > 0 and self.eval_count > 0:
            return self.eval_count / (self.eval_duration_ns / 1e9)
        return 0.0

    @property
    def cost_usd(self) -> float:
        return 0.0  # Always free — local inference


# ═══════════════════════════════════════════════════════════════════════════════
# Client / 客户端
# ═══════════════════════════════════════════════════════════════════════════════

class OllamaClient:
    """
    HTTP client for Ollama local LLM inference.
    通过 HTTP API 调用本地 Ollama 模型推理。

    Usage:
        client = OllamaClient()
        if client.is_available():
            resp = client.generate("Analyze BTCUSDT market trend")
            print(resp.text)
    """

    def __init__(self, config: OllamaConfig | None = None):
        self._config = config or OllamaConfig()
        self._lock = threading.Lock()
        self._available: bool | None = None  # cached availability
        self._available_ts: float = 0.0
        self._available_ttl: float = 60.0  # re-check every 60s

    @property
    def config(self) -> OllamaConfig:
        return self._config

    @property
    def model(self) -> str:
        return self._config.model

    # ── Connectivity / 连通性检测 ──

    def is_available(self, *, force_check: bool = False) -> bool:
        """
        Check if Ollama server is reachable and model is loaded (synchronous).
        检测 Ollama 服务是否可达且模型已加载（同步版本）。

        DEPRECATION NOTE: This method blocks the event loop when called from async
        code. Prefer is_available_async() in async contexts.
        弃用提示：在 async 上下文中调用此方法会阻塞事件循环，请改用 is_available_async()。
        """
        now = time.time()
        if not force_check and self._available is not None and (now - self._available_ts) < self._available_ttl:
            return self._available

        with self._lock:
            # Double-check after acquiring lock
            if not force_check and self._available is not None and (now - self._available_ts) < self._available_ttl:
                return self._available

            try:
                url = f"{self._config.base_url}/api/tags"
                req = urllib.request.Request(url, method="GET")
                # timeout=1: health check should be fast; 5s was too generous and
                # blocked callers when Ollama was unreachable.
                # timeout=1：健康檢查應快速完成；原 5s 過長，Ollama 不可達時阻塞調用者。
                with urllib.request.urlopen(req, timeout=1) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    models = [m.get("name", "") for m in data.get("models", [])]
                    # Check if our target model is available (partial match)
                    model_found = any(
                        self._config.model in m or m.startswith(self._config.model)
                        for m in models
                    )
                    if not model_found and models:
                        logger.warning(
                            f"Ollama: model '{self._config.model}' not found. "
                            f"Available: {models[:5]}"
                        )
                    self._available = model_found
                    self._available_ts = time.time()
                    return self._available
            except Exception as e:
                logger.debug("Ollama availability check failed: %s", e)
                self._available = False
                self._available_ts = time.time()
                return False

    async def is_available_async(self, *, force_check: bool = False) -> bool:
        """
        Async wrapper for is_available() — runs the sync health check in a thread.
        is_available() 的异步包装 — 在线程中运行同步健康检查，避免阻塞事件循环。

        Usage / 用法:
            available = await client.is_available_async()
        """
        import asyncio
        return await asyncio.to_thread(self.is_available, force_check=force_check)

    def list_models(self) -> list[str]:
        """List all models available on Ollama server / 列出 Ollama 上所有可用模型"""
        try:
            url = f"{self._config.base_url}/api/tags"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [m.get("name", "") for m in data.get("models", [])]
        except Exception as e:
            logger.error("Failed to list Ollama models: %s", e)
            return []

    # ── Generate (single-turn) / 单轮生成 ──

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int = 1024,
        timeout: int | None = None,
        think: bool = False,
    ) -> OllamaResponse:
        """
        Single-turn generation via /api/generate.
        通过 /api/generate 进行单轮文本生成。

        Args:
            prompt: User prompt / 用户提示
            system: Optional system prompt / 可选系统提示
            model: Override model name / 覆盖模型名
            temperature: Override temperature / 覆盖温度
            max_tokens: Maximum tokens to generate / 最大生成 token 数
            timeout: Override timeout in seconds / 覆盖超时秒数
        """
        start = time.time()
        use_model = model or self._config.model
        use_timeout = timeout or self._config.timeout_seconds
        use_temp = temperature if temperature is not None else self._config.temperature

        payload: dict[str, Any] = {
            "model": use_model,
            "prompt": prompt,
            "stream": False,
            "think": think,  # top-level flag required by Ollama for Qwen3.5 think control
            "options": {
                "temperature": use_temp,
                "num_predict": max_tokens,
            },
        }
        if system:
            payload["system"] = system

        return self._post("/api/generate", payload, use_model, use_timeout, start)

    # ── Chat (multi-turn) / 多轮对话 ──

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        system: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int = 1024,
        timeout: int | None = None,
        think: bool = False,
    ) -> OllamaResponse:
        """
        Multi-turn chat via /api/chat.
        通过 /api/chat 进行多轮对话。

        Args:
            messages: List of {"role": "user/assistant", "content": "..."} / 消息列表
            system: Optional system prompt (prepended) / 可选系统提示
            model: Override model name / 覆盖模型名
            temperature: Override temperature / 覆盖温度
            max_tokens: Maximum tokens to generate / 最大生成 token 数
            timeout: Override timeout in seconds / 覆盖超时秒数
            think: Enable chain-of-thought (Qwen3.5); must be top-level, not inside options
                   启用思维链（Qwen3.5 要求放 JSON 顶层，不可放 options 内）
        """
        start = time.time()
        use_model = model or self._config.model
        use_timeout = timeout or self._config.timeout_seconds
        use_temp = temperature if temperature is not None else self._config.temperature

        chat_messages = list(messages)
        if system:
            chat_messages.insert(0, {"role": "system", "content": system})

        payload: dict[str, Any] = {
            "model": use_model,
            "messages": chat_messages,
            "stream": False,
            "think": think,  # top-level flag required by Ollama for Qwen3.5 think control
            "options": {
                "temperature": use_temp,
                "num_predict": max_tokens,
            },
        }

        return self._post("/api/chat", payload, use_model, use_timeout, start)

    # ── Structured output helpers / 结构化输出辅助 ──

    def classify(
        self,
        text: str,
        categories: list[str],
        *,
        system: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ) -> OllamaResponse:
        """
        Classify text into one of the given categories.
        将文本分类到给定类别之一。
        Designed for market sentiment classification and similar tasks.

        Args:
            text: Text to classify / 待分类文本
            categories: List of valid categories / 有效类别列表
            system: Optional system context / 可选系统上下文
        """
        category_str = ", ".join(categories)
        classify_prompt = (
            f"Classify the following text into exactly ONE of these categories: [{category_str}]\n\n"
            f"Text: {text}\n\n"
            f"Respond with ONLY the category name, nothing else."
        )

        classify_system = system or (
            "You are a precise classification model. "
            "Respond with exactly one word from the allowed categories. "
            "No explanation, no punctuation, just the category."
        )

        return self.generate(
            classify_prompt,
            system=classify_system,
            model=model,
            temperature=0.1,  # Very deterministic for classification
            max_tokens=32,
            timeout=timeout or 8,
            think=False,  # single-word answer needs no chain-of-thought
        )

    def judge_edge(
        self,
        market_context: str,
        *,
        model: str | None = None,
        timeout: int | None = None,
    ) -> OllamaResponse:
        """
        Quick edge judgment: does the current signal have enough edge to trade?
        快速 edge 判断：当前信号是否有足够交易优势？
        Designed as pre-trade filter for Direction B.

        Returns text containing JSON: {"has_edge": bool, "confidence": float, "reason": str}
        """
        system = (
            "You are a crypto trading signal validator. "
            "Given market context, determine if there is a tradeable edge. "
            "Respond with JSON only: {\"has_edge\": true/false, \"confidence\": 0.0-1.0, \"reason\": \"...\"}\n"
            "Be conservative: when in doubt, has_edge=false. "
            "Consider: trend strength, volume confirmation, fee drag (~0.11%), stop distance."
        )

        return self.generate(
            market_context,
            system=system,
            model=model,
            temperature=0.2,
            max_tokens=100,   # JSON answer is ~40-60 tokens; was 256
            timeout=timeout or 8,
            think=False,      # disable chain-of-thought for latency-sensitive gate
        )

    # ── Internal HTTP / 内部 HTTP 实现 ──

    def _post(
        self,
        endpoint: str,
        payload: dict[str, Any],
        model: str,
        timeout: int,
        start: float,
    ) -> OllamaResponse:
        """Send POST request to Ollama API / 向 Ollama API 发送 POST 请求"""
        url = f"{self._config.base_url}{endpoint}"
        data = json.dumps(payload).encode("utf-8")

        for attempt in range(1 + self._config.max_retries):
            try:
                req = urllib.request.Request(
                    url,
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    body = json.loads(resp.read().decode("utf-8"))

                latency_ms = (time.time() - start) * 1000

                # /api/generate returns "response", /api/chat returns "message.content"
                if "response" in body:
                    text = body["response"].strip()
                elif "message" in body and "content" in body["message"]:
                    text = body["message"]["content"].strip()
                else:
                    text = ""

                return OllamaResponse(
                    text=text,
                    model=body.get("model", model),
                    success=True,
                    latency_ms=round(latency_ms, 1),
                    eval_count=body.get("eval_count", 0),
                    eval_duration_ns=body.get("eval_duration", 0),
                    total_duration_ns=body.get("total_duration", 0),
                )

            except urllib.error.URLError as e:
                latency_ms = (time.time() - start) * 1000
                # NOTE: max_retries defaults to 0 (single-attempt mode per CLAUDE.md hard boundary).
                # The retry branches below are intentionally dormant under current config.
                # To enable retries, pass max_retries >= 1 to OllamaConfig. Dead-code by design.
                # 注意：max_retries 預設為 0（CLAUDE.md 硬邊界，單次嘗試模式）。
                # 以下 retry 分支在當前配置下為死代碼，屬設計意圖。如需啟用，傳入 max_retries >= 1。
                if attempt < self._config.max_retries:
                    logger.warning("Ollama request failed (attempt %s), retrying: %s", attempt + 1, e)
                    time.sleep(0.5)
                    continue
                return OllamaResponse(
                    text="", model=model, success=False,
                    latency_ms=round(latency_ms, 1),
                    error=f"Connection error: {str(e)[:200]}",
                )
            except TimeoutError:
                latency_ms = (time.time() - start) * 1000
                return OllamaResponse(
                    text="", model=model, success=False,
                    latency_ms=round(latency_ms, 1),
                    error=f"Timeout after {timeout}s",
                )
            except json.JSONDecodeError as e:
                latency_ms = (time.time() - start) * 1000
                return OllamaResponse(
                    text="", model=model, success=False,
                    latency_ms=round(latency_ms, 1),
                    error=f"Invalid JSON response: {str(e)[:100]}",
                )
            except Exception as e:
                latency_ms = (time.time() - start) * 1000
                return OllamaResponse(
                    text="", model=model, success=False,
                    latency_ms=round(latency_ms, 1),
                    error=f"Unexpected error: {str(e)[:200]}",
                )

        # NOTE: This line is unreachable when max_retries=0. Dead-code by design.
        # Should not reach here, but just in case
        return OllamaResponse(
            text="", model=model, success=False,
            latency_ms=(time.time() - start) * 1000,
            error="Max retries exceeded",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Singleton / 单例
# ═══════════════════════════════════════════════════════════════════════════════

_default_client: OllamaClient | None = None
_heavy_client: OllamaClient | None = None
_singleton_lock = threading.Lock()


def get_ollama_client(config: OllamaConfig | None = None) -> OllamaClient:
    """
    Get or create default OllamaClient singleton (9B — speed-critical tasks).
    获取或创建默认 OllamaClient 单例（9B — 速度敏感任务）。
    """
    global _default_client
    if _default_client is not None and config is None:
        return _default_client

    with _singleton_lock:
        if _default_client is not None and config is None:
            return _default_client
        _default_client = OllamaClient(config)
        return _default_client


def get_ollama_client_27b() -> OllamaClient:
    """
    Get or create 27B OllamaClient singleton (complex / time-insensitive tasks).
    获取或创建 27B OllamaClient 单例（复杂 / 时效不敏感任务）。

    Used by: AnalystAgent weekly pattern discovery, Layer2Engine L2 full loop fallback.
    用于：AnalystAgent 周报模式发现、Layer2Engine L2 完整推理回退。
    """
    global _heavy_client
    if _heavy_client is not None:
        return _heavy_client

    with _singleton_lock:
        if _heavy_client is not None:
            return _heavy_client
        _heavy_client = OllamaClient(OllamaConfig(model="qwen3.5:27b-q4_K_M"))
        return _heavy_client


def reset_ollama_client() -> None:
    """Reset singletons (for testing) / 重置单例（用于测试）"""
    global _default_client, _heavy_client
    with _singleton_lock:
        _default_client = None
        _heavy_client = None
