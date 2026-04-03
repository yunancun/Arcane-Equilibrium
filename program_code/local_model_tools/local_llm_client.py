"""
1-9: LocalLLMClient — Abstract Base for Local LLM Inference / 本地 LLM 推理抽象基類
===================================================================================

MODULE_NOTE (中文):
  LocalLLMClient 定義本地 LLM 推理的統一接口（報告 §4.5）：
  - generate()：同步文本生成
  - is_available()：連通性檢測
  - get_model_info()：模型信息

  實現目標：Ollama + LM Studio 兼容。
  業務邏輯禁止直接調用 Ollama HTTP endpoint，必須通過此接口。
  跨平台：不依賴特定 LLM 服務的內部細節。

MODULE_NOTE (English):
  LocalLLMClient defines the unified interface for local LLM inference (Report §4.5):
  - generate(): synchronous text generation
  - is_available(): connectivity check
  - get_model_info(): model information

  Implementation target: Ollama + LM Studio compatibility.
  Business logic must NOT call Ollama HTTP endpoints directly — use this interface.
  Cross-platform: no dependency on LLM service-specific internals.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMResponse:
    """
    Unified LLM response container.
    統一的 LLM 響應容器。
    """
    text: str = ""
    model: str = ""
    latency_ms: float = 0.0
    tokens_used: int = 0
    cost_usd: float = 0.0  # Always 0 for local models / 本地模型始終為 0
    success: bool = True
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "model": self.model,
            "latency_ms": round(self.latency_ms, 1),
            "tokens_used": self.tokens_used,
            "cost_usd": self.cost_usd,
            "success": self.success,
            "error": self.error,
        }


class LocalLLMClient(ABC):
    """
    Abstract base class for local LLM inference providers.
    本地 LLM 推理供應商的抽象基類。

    Implementations: OllamaProvider, LMStudioProvider.
    All business logic should depend on this interface, not on specific providers.
    所有業務邏輯應依賴此接口，不依賴特定供應商。
    """

    @abstractmethod
    def is_available(self, *, force_check: bool = False) -> bool:
        """
        Check if the LLM service is reachable and model is loaded.
        檢查 LLM 服務是否可達且模型已載入。
        """
        ...

    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float = 0.3,
        max_tokens: int = 500,
        timeout_s: float = 30.0,
    ) -> LLMResponse:
        """
        Generate text from a prompt (synchronous).
        從提示詞生成文本（同步）。

        Args:
            prompt: User prompt text.
            system: Optional system prompt.
            temperature: Sampling temperature (0.0 = deterministic).
            max_tokens: Maximum tokens to generate.
            timeout_s: Timeout in seconds.

        Returns:
            LLMResponse with generated text or error.
        """
        ...

    @abstractmethod
    def get_model_info(self) -> dict[str, Any]:
        """
        Return model name, provider, and capabilities.
        返回模型名稱、供應商和能力信息。
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier: "ollama" | "lm_studio" / 供應商標識"""
        ...


class OllamaProvider(LocalLLMClient):
    """
    Ollama-backed LocalLLMClient implementation.
    基於 Ollama 的 LocalLLMClient 實現。

    Wraps the existing OllamaClient to conform to the ABC interface.
    包裝現有的 OllamaClient 以符合 ABC 接口。
    """

    def __init__(self, ollama_client: Any) -> None:
        self._client = ollama_client

    @property
    def provider_name(self) -> str:
        return "ollama"

    def is_available(self, *, force_check: bool = False) -> bool:
        return self._client.is_available(force_check=force_check)

    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float = 0.3,
        max_tokens: int = 500,
        timeout_s: float = 30.0,
    ) -> LLMResponse:
        try:
            resp = self._client.generate(
                prompt, system=system, temperature=temperature,
                max_tokens=max_tokens, timeout=timeout_s,
            )
            return LLMResponse(
                text=resp.text if hasattr(resp, "text") else str(resp),
                model=getattr(resp, "model", self._client.model),
                latency_ms=getattr(resp, "latency_ms", 0.0),
                tokens_used=getattr(resp, "tokens_used", 0),
                cost_usd=0.0,
                success=True,
            )
        except Exception as e:
            return LLMResponse(success=False, error=str(e))

    def get_model_info(self) -> dict[str, Any]:
        return {
            "provider": "ollama",
            "model": self._client.model,
            "available": self.is_available(),
        }


class LMStudioProvider(LocalLLMClient):
    """
    LM Studio-backed LocalLLMClient implementation.
    基於 LM Studio 的 LocalLLMClient 實現。

    Uses OpenAI-compatible API endpoint (LM Studio serves on localhost:1234).
    使用 OpenAI 兼容 API（LM Studio 在 localhost:1234 上服務）。
    """

    def __init__(
        self,
        base_url: str = "http://localhost:1234/v1",
        model: str = "default",
    ) -> None:
        self._base_url = base_url
        self._model = model

    @property
    def provider_name(self) -> str:
        return "lm_studio"

    def is_available(self, *, force_check: bool = False) -> bool:
        import urllib.request
        try:
            req = urllib.request.Request(f"{self._base_url}/models", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float = 0.3,
        max_tokens: int = 500,
        timeout_s: float = 30.0,
    ) -> LLMResponse:
        import json
        import time as _time
        import urllib.request

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = json.dumps({
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }).encode()

        t0 = _time.perf_counter()
        try:
            req = urllib.request.Request(
                f"{self._base_url}/chat/completions",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                data = json.loads(resp.read().decode())
                text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                latency = (_time.perf_counter() - t0) * 1000
                tokens = data.get("usage", {}).get("total_tokens", 0)
                return LLMResponse(
                    text=text, model=self._model,
                    latency_ms=latency, tokens_used=tokens,
                )
        except Exception as e:
            return LLMResponse(success=False, error=str(e))

    def get_model_info(self) -> dict[str, Any]:
        return {
            "provider": "lm_studio",
            "model": self._model,
            "base_url": self._base_url,
            "available": self.is_available(),
        }
