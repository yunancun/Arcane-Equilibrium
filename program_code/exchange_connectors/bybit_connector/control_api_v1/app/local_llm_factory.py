from __future__ import annotations

"""
LLM-ABC-MIGRATION-1 — Local LLM provider factory
================================================
Governance refs: CLAUDE.md §七 "LocalLLMClient 抽象乾淨", DOC-04 §Cross-platform

MODULE_NOTE (中文):
  本模組提供本地 LLM 客戶端的工廠函式，根據環境變量 LOCAL_LLM_PROVIDER 切換：
  - "ollama"    (預設): 回傳 OllamaClient 單例（Linux 部署 / 向後相容）
  - "lm_studio"        : 回傳 LMStudioShimClient（Mac operator 裝 LM Studio 用）
  - 其他值             : 警告並 fallback 到 ollama（safe default）

  設計原則：LM Studio shim 暴露與 OllamaClient 相同的 surface
  （.generate/.chat/.classify/.judge_edge/.is_available/.is_available_async/
   .config.base_url/.config.model/.model），並回傳 OllamaResponse 形狀的物件，
  以達到「call-site 不關心 provider」+「response 解析 0 變動」的最小侵入遷移。

MODULE_NOTE (English):
  Factory for the local-LLM client used by AIService / Layer2 / 5-Agent system.
  Switches on LOCAL_LLM_PROVIDER env:
  - "ollama"    (default): returns the OllamaClient singleton
  - "lm_studio"          : returns an LMStudioShimClient exposing the same surface
  - unknown              : logs warning, falls back to ollama

  Design: LM Studio shim mirrors OllamaClient's public surface and returns
  OllamaResponse-shaped objects, so call sites don't need to know which provider
  is active and downstream response parsing stays byte-identical.

Environment:
  LOCAL_LLM_PROVIDER     — "ollama" | "lm_studio"   (default "ollama")
  LM_STUDIO_BASE_URL     — default "http://127.0.0.1:1234/v1"
  LM_STUDIO_MODEL        — default "local-model" (LM Studio loads one model at a time)
  LM_STUDIO_MODEL_HEAVY  — default == LM_STUDIO_MODEL (LM Studio typically serves
                           one model; heavy=True returns the same client unless overridden)
"""

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from .ollama_client import (
    OllamaClient,
    OllamaConfig,
    OllamaResponse,
    get_ollama_client,
    get_ollama_client_27b,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Provider identifiers / 供應商標識
# ═══════════════════════════════════════════════════════════════════════════════

PROVIDER_OLLAMA = "ollama"
PROVIDER_LM_STUDIO = "lm_studio"
_VALID_PROVIDERS = (PROVIDER_OLLAMA, PROVIDER_LM_STUDIO)

_DEFAULT_LM_STUDIO_BASE_URL = "http://127.0.0.1:1234/v1"
_DEFAULT_LM_STUDIO_MODEL = "local-model"


def _resolve_provider() -> str:
    """Return the configured provider, falling back to ollama on unknown values.
    回傳已配置供應商；未知值 → 警告並回退到 ollama。"""
    raw = os.environ.get("LOCAL_LLM_PROVIDER", PROVIDER_OLLAMA).strip().lower()
    if raw in _VALID_PROVIDERS:
        return raw
    logger.warning(
        "LOCAL_LLM_PROVIDER=%r not recognized; falling back to %s / "
        "未識別的 LOCAL_LLM_PROVIDER=%r，回退到 %s",
        raw, PROVIDER_OLLAMA, raw, PROVIDER_OLLAMA,
    )
    return PROVIDER_OLLAMA


# ═══════════════════════════════════════════════════════════════════════════════
# LM Studio shim — OpenAI-compat client mimicking OllamaClient surface
# LM Studio shim — 使用 OpenAI 兼容 API，模擬 OllamaClient 接口
# ═══════════════════════════════════════════════════════════════════════════════


class _LMStudioShimConfig:
    """Small config object so callers can read `.config.base_url` / `.config.model`.
    小型 config 物件供 caller 讀 base_url / model（與 OllamaConfig 接口一致）。"""

    def __init__(self, base_url: str, model: str, timeout_seconds: int = 30) -> None:
        self.base_url = base_url
        self.model = model
        self.timeout_seconds = timeout_seconds


class LMStudioShimClient:
    """
    OpenAI-compat client for LM Studio that mimics OllamaClient's public surface.
    模擬 OllamaClient 接口的 LM Studio OpenAI 兼容客戶端。

    Exposes: generate / chat / classify / judge_edge / is_available /
             is_available_async / config / model
    Returns OllamaResponse from LLM calls so downstream parsing is unchanged.
    LLM 回傳一律轉成 OllamaResponse 形狀，下游解析零變動。
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        self._config = _LMStudioShimConfig(
            base_url=base_url or os.environ.get("LM_STUDIO_BASE_URL", _DEFAULT_LM_STUDIO_BASE_URL),
            model=model or os.environ.get("LM_STUDIO_MODEL", _DEFAULT_LM_STUDIO_MODEL),
            timeout_seconds=timeout_seconds,
        )
        self._lock = threading.Lock()
        self._available: bool | None = None
        self._available_ts: float = 0.0
        self._available_ttl: float = 60.0

    # ── Surface parity attrs / 接口對齊屬性 ──

    @property
    def config(self) -> _LMStudioShimConfig:
        return self._config

    @property
    def model(self) -> str:
        return self._config.model

    # ── Connectivity / 連通性 ──

    def is_available(self, *, force_check: bool = False) -> bool:
        now = time.time()
        if not force_check and self._available is not None and (now - self._available_ts) < self._available_ttl:
            return self._available
        with self._lock:
            if not force_check and self._available is not None and (now - self._available_ts) < self._available_ttl:
                return self._available
            try:
                req = urllib.request.Request(f"{self._config.base_url}/models", method="GET")
                with urllib.request.urlopen(req, timeout=1) as resp:
                    ok = resp.status == 200
            except Exception as exc:
                logger.debug("LM Studio availability check failed: %s", exc)
                ok = False
            self._available = ok
            self._available_ts = time.time()
            return ok

    async def is_available_async(self, *, force_check: bool = False) -> bool:
        import asyncio
        return await asyncio.to_thread(self.is_available, force_check=force_check)

    # ── Generate / 生成 ──

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int = 1024,
        timeout: int | None = None,
        think: bool = False,  # ignored on LM Studio (no chain-of-thought flag) / LM Studio 無此旗標
    ) -> OllamaResponse:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self._chat_completion(
            messages, model=model, temperature=temperature,
            max_tokens=max_tokens, timeout=timeout,
        )

    # ── Chat / 多輪對話 ──

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        system: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int = 1024,
        timeout: int | None = None,
        think: bool = False,  # ignored on LM Studio / LM Studio 忽略
    ) -> OllamaResponse:
        full_messages = list(messages)
        if system:
            full_messages.insert(0, {"role": "system", "content": system})
        return self._chat_completion(
            full_messages, model=model, temperature=temperature,
            max_tokens=max_tokens, timeout=timeout,
        )

    # ── Classify (matches OllamaClient.classify) / 分類 ──

    def classify(
        self,
        text: str,
        categories: list[str],
        *,
        system: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ) -> OllamaResponse:
        category_str = ", ".join(categories)
        prompt = (
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
            prompt,
            system=classify_system,
            model=model,
            temperature=0.1,
            max_tokens=32,
            timeout=timeout or 8,
            think=False,
        )

    # ── Judge edge (matches OllamaClient.judge_edge) / 快速 edge 判斷 ──

    def judge_edge(
        self,
        market_context: str,
        *,
        model: str | None = None,
        timeout: int | None = None,
    ) -> OllamaResponse:
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
            max_tokens=100,
            timeout=timeout or 8,
            think=False,
        )

    # ── Internal HTTP / 內部 HTTP ──

    def _chat_completion(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None,
        temperature: float | None,
        max_tokens: int,
        timeout: int | None,
    ) -> OllamaResponse:
        use_model = model or self._config.model
        use_timeout = timeout or self._config.timeout_seconds
        use_temp = 0.3 if temperature is None else temperature
        payload = {
            "model": use_model,
            "messages": messages,
            "temperature": use_temp,
            "max_tokens": max_tokens,
        }
        data = json.dumps(payload).encode("utf-8")
        start = time.time()
        try:
            req = urllib.request.Request(
                f"{self._config.base_url}/chat/completions",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=use_timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            latency_ms = (time.time() - start) * 1000
            text = (
                body.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            tokens = body.get("usage", {}).get("total_tokens", 0)
            return OllamaResponse(
                text=text,
                model=body.get("model", use_model),
                success=True,
                latency_ms=round(latency_ms, 1),
                eval_count=tokens,
                eval_duration_ns=0,
                total_duration_ns=0,
            )
        except urllib.error.URLError as exc:
            return OllamaResponse(
                text="", model=use_model, success=False,
                latency_ms=round((time.time() - start) * 1000, 1),
                error=f"Connection error: {str(exc)[:200]}",
            )
        except TimeoutError:
            return OllamaResponse(
                text="", model=use_model, success=False,
                latency_ms=round((time.time() - start) * 1000, 1),
                error=f"Timeout after {use_timeout}s",
            )
        except json.JSONDecodeError as exc:
            return OllamaResponse(
                text="", model=use_model, success=False,
                latency_ms=round((time.time() - start) * 1000, 1),
                error=f"Invalid JSON response: {str(exc)[:100]}",
            )
        except Exception as exc:  # noqa: BLE001 — fail-soft, caller heuristic fallback
            return OllamaResponse(
                text="", model=use_model, success=False,
                latency_ms=round((time.time() - start) * 1000, 1),
                error=f"Unexpected error: {str(exc)[:200]}",
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Singletons / 單例
# ═══════════════════════════════════════════════════════════════════════════════

_lm_studio_default: LMStudioShimClient | None = None
_lm_studio_heavy: LMStudioShimClient | None = None
_singleton_lock = threading.Lock()


def _get_lm_studio_client() -> LMStudioShimClient:
    global _lm_studio_default
    if _lm_studio_default is not None:
        return _lm_studio_default
    with _singleton_lock:
        if _lm_studio_default is not None:
            return _lm_studio_default
        _lm_studio_default = LMStudioShimClient()
        return _lm_studio_default


def _get_lm_studio_client_heavy() -> LMStudioShimClient:
    """Heavy model singleton for LM Studio. LM Studio typically serves one model
    at a time; if LM_STUDIO_MODEL_HEAVY is unset, returns the default client.
    LM Studio 通常一次只載入一個模型；LM_STUDIO_MODEL_HEAVY 未設時回傳預設 client。"""
    global _lm_studio_heavy
    if _lm_studio_heavy is not None:
        return _lm_studio_heavy
    heavy_model = os.environ.get("LM_STUDIO_MODEL_HEAVY")
    if not heavy_model:
        return _get_lm_studio_client()
    with _singleton_lock:
        if _lm_studio_heavy is not None:
            return _lm_studio_heavy
        _lm_studio_heavy = LMStudioShimClient(model=heavy_model)
        return _lm_studio_heavy


def reset_local_llm_singletons() -> None:
    """Reset shim singletons (for testing). Ollama singletons remain owned by
    ollama_client.reset_ollama_client(). 測試用；Ollama 單例由 ollama_client 負責。"""
    global _lm_studio_default, _lm_studio_heavy
    with _singleton_lock:
        _lm_studio_default = None
        _lm_studio_heavy = None


# ═══════════════════════════════════════════════════════════════════════════════
# Public factory / 公開工廠
# ═══════════════════════════════════════════════════════════════════════════════


def get_local_llm_client(*, heavy: bool = False) -> Any:
    """
    Return the active local LLM client (default or heavy variant) based on
    LOCAL_LLM_PROVIDER env.  Returned object exposes the OllamaClient surface:
    .generate / .chat / .classify / .judge_edge / .is_available /
    .is_available_async / .config.base_url / .config.model / .model.

    依 LOCAL_LLM_PROVIDER 回傳啟用中的本地 LLM 客戶端（預設或重型變體）。
    回傳物件暴露與 OllamaClient 相同 surface，call-site 無感切換。

    Args:
        heavy: If True, return the heavy-model singleton (Ollama: 27B;
               LM Studio: LM_STUDIO_MODEL_HEAVY or default).

    Returns:
        OllamaClient | LMStudioShimClient
    """
    provider = _resolve_provider()
    if provider == PROVIDER_LM_STUDIO:
        return _get_lm_studio_client_heavy() if heavy else _get_lm_studio_client()
    return get_ollama_client_27b() if heavy else get_ollama_client()


__all__ = [
    "PROVIDER_OLLAMA",
    "PROVIDER_LM_STUDIO",
    "LMStudioShimClient",
    "get_local_llm_client",
    "reset_local_llm_singletons",
]
