"""
provider_client
═══════════════════════════════════════════════════════════════════════════════
L2 推理 provider 抽象層。

職責：
  1. 統一 Anthropic / DeepSeek / OpenAI 的呼叫 shape（agent loop 與 triage）
  2. tier_key → 各 provider 實際 model_id 映射（haiku / sonnet / opus）
  3. 將 Anthropic-style tools schema 翻譯成 OpenAI-compat function calling
  4. 把回應正規化成 L2Response（text + tool_uses + stop_reason + tokens）
  5. 把 tool 結果正確 append 回 messages（provider-specific shape）

非職責：
  - 不負責 budget / pricing / cost 記錄（呼叫端 layer2_engine 用 tier_key 寫入 cost_tracker）
  - 不負責 provider key 持久化（provider_keys_store 管）
  - 不負責 default_provider 選擇邏輯（layer2_engine 根據 daily_pct 與 fallback_tier 決定）

SDK availability：
  - anthropic / openai 套件 import 失敗時 is_available()=False，呼叫方 fallback 到本地 LLM
  - DeepSeek 走 openai SDK + base_url=https://api.deepseek.com（OpenAI-compat）
  - OpenAI 走 openai SDK 預設 base_url
  - 都遵守原 _get_anthropic_client 的 lazy + threading.Lock pattern
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ─── 規格與映射 ────────────────────────────────────────────────────

PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_DEEPSEEK = "deepseek"
PROVIDER_OPENAI = "openai"

# Provider 白名單（L2 推理可用，與 provider_keys_store 同步但更窄
# — perplexity 是搜索專用，google 客戶端尚未實裝在這層）。
L2_PROVIDERS: frozenset[str] = frozenset({
    PROVIDER_ANTHROPIC,
    PROVIDER_DEEPSEEK,
    PROVIDER_OPENAI,
})

# tier_key → 各 provider 的實際 model_id。
# tier_key 是 cost_tracker 記帳用的鍵（PricingTable.models 字典 key）。
# 改 tier_key 必同步改 layer2_types.PricingTable 與 GUI 下拉框。
TIER_HAIKU = "haiku"
TIER_SONNET = "sonnet"
TIER_OPUS = "opus"
TIER_DEEPSEEK_CHAT = "deepseek-chat"
TIER_DEEPSEEK_REASONER = "deepseek-reasoner"
TIER_GPT_4O_MINI = "gpt-4o-mini"
TIER_GPT_4O = "gpt-4o"
TIER_O1 = "o1"

# 每個 provider 提供的 tier key 列表（GUI 下拉 + tier fallback 用）。
PROVIDER_TIERS: dict[str, list[str]] = {
    PROVIDER_ANTHROPIC: [TIER_HAIKU, TIER_SONNET, TIER_OPUS],
    PROVIDER_DEEPSEEK: [TIER_DEEPSEEK_CHAT, TIER_DEEPSEEK_REASONER],
    PROVIDER_OPENAI: [TIER_GPT_4O_MINI, TIER_GPT_4O, TIER_O1],
}

# tier 在「成本/能力」軸上的對位（用於跨 provider 自動 mapping）。
# 例如 default_model=sonnet + fallback to deepseek → 用 deepseek-chat（同檔次）。
TIER_RANK: dict[str, int] = {
    TIER_HAIKU: 1, TIER_GPT_4O_MINI: 1, TIER_DEEPSEEK_CHAT: 2,
    TIER_SONNET: 3, TIER_GPT_4O: 3,
    TIER_DEEPSEEK_REASONER: 4, TIER_OPUS: 5, TIER_O1: 5,
}

# Tier 哪些不支援 function-calling / tool use。
# DeepSeek-reasoner (R1) 當前 API 不支援 tools；agent loop 命中時呼叫端必降級。
TIERS_WITHOUT_TOOLS: frozenset[str] = frozenset({TIER_DEEPSEEK_REASONER})


def map_tier_to_provider(tier: str, provider: str) -> str:
    """
    把 cost_tracker 用的 tier_key 映射到指定 provider 的最接近 tier。
    例：tier="sonnet" + provider="deepseek" → "deepseek-chat"
    例：tier="opus"   + provider="openai"   → "o1"
    當 provider 內的 tier 列表為空 → 回原 tier（不改變）。
    """
    if provider not in PROVIDER_TIERS:
        return tier
    available = PROVIDER_TIERS[provider]
    if tier in available:
        return tier
    target_rank = TIER_RANK.get(tier, 3)
    # 找排名最接近的
    return min(available, key=lambda t: abs(TIER_RANK.get(t, 3) - target_rank))


# ─── 正規化資料結構 ────────────────────────────────────────────────

@dataclass
class ToolUse:
    """正規化的 tool_use 區塊（Anthropic-shape；OpenAI 端會在 adapter 內 reformat）。"""
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class L2Response:
    """provider 無關的回應（layer2_engine.run_session 直接消費）。"""
    text: str = ""                  # 最終文字（end_turn 時取出）
    tool_uses: list[ToolUse] = field(default_factory=list)
    stop_reason: str = "end_turn"   # "end_turn" | "tool_use" | "max_tokens" | "error"
    input_tokens: int = 0
    output_tokens: int = 0
    raw_response: Any = None        # provider 原始物件（除錯用）


# ─── Provider 介面（Protocol-style） ──────────────────────────────

class L2ProviderBase:
    """所有 L2 provider adapter 的公共行為。"""
    name: str = "base"

    def is_available(self) -> bool:
        raise NotImplementedError

    def supports_tools(self, tier: str) -> bool:
        return tier not in TIERS_WITHOUT_TOOLS

    def complete(
        self,
        *,
        tier: str,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        max_tokens: int = 4096,
        timeout: float = 120.0,
    ) -> L2Response:
        raise NotImplementedError

    def append_assistant_message(self, messages: list[dict[str, Any]], response: L2Response) -> None:
        """把 assistant 回應插回 messages（agent loop 下一輪會帶上）。"""
        raise NotImplementedError

    def append_tool_results(
        self,
        messages: list[dict[str, Any]],
        tool_results: list[dict[str, Any]],
    ) -> None:
        """把 tool 執行結果插回 messages。tool_results = [{tool_use_id, output_str, is_error}]。"""
        raise NotImplementedError


# ─── Anthropic adapter ────────────────────────────────────────────

class AnthropicProvider(L2ProviderBase):
    name = PROVIDER_ANTHROPIC

    # tier → claude model id（沿用既有 layer2_types.MODEL_IDS，避免 drift）
    _MODEL_ID_MAP_CACHE: dict[str, str] | None = None

    def __init__(self) -> None:
        self._client: Any = None
        self._lock = threading.Lock()

    def _model_id(self, tier: str) -> str:
        from .layer2_types import MODEL_IDS  # 延遲 import 防 circular
        if tier in MODEL_IDS:
            return MODEL_IDS[tier]
        # tier 不認識 → 回 sonnet
        return MODEL_IDS["sonnet"]

    def is_available(self) -> bool:
        return self._get_client() is not None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        with self._lock:
            if self._client is not None:
                return self._client
            try:
                import anthropic
            except ImportError:
                logger.warning("anthropic SDK 未安裝；AnthropicProvider 不可用")
                return None
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            if not api_key:
                logger.warning("ANTHROPIC_API_KEY 未設置；AnthropicProvider 不可用")
                return None
            self._client = anthropic.Anthropic(api_key=api_key)
            return self._client

    def reset(self) -> None:
        """供 provider_keys_store.save_key 在替換 key 後 hot-reload 用。"""
        with self._lock:
            self._client = None

    def complete(
        self,
        *,
        tier: str,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        max_tokens: int = 4096,
        timeout: float = 120.0,
    ) -> L2Response:
        client = self._get_client()
        if client is None:
            raise RuntimeError("AnthropicProvider unavailable (SDK or key missing)")

        kwargs: dict[str, Any] = dict(
            model=self._model_id(tier),
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
        )
        if tools:
            kwargs["tools"] = tools
        # timeout 由呼叫端用 asyncio.wait_for 包；這裡 SDK 預設 timeout 走它自己的
        resp = client.messages.create(**kwargs)

        text_parts: list[str] = []
        tool_uses: list[ToolUse] = []
        for block in (resp.content or []):
            btype = getattr(block, "type", "")
            if btype == "text" or hasattr(block, "text"):
                t = getattr(block, "text", "") or ""
                if t:
                    text_parts.append(t)
            if btype == "tool_use":
                tool_uses.append(ToolUse(
                    id=getattr(block, "id", ""),
                    name=getattr(block, "name", ""),
                    input=getattr(block, "input", {}) or {},
                ))
        return L2Response(
            text="\n".join(text_parts),
            tool_uses=tool_uses,
            stop_reason=getattr(resp, "stop_reason", "end_turn") or "end_turn",
            input_tokens=int(getattr(resp.usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(resp.usage, "output_tokens", 0) or 0),
            raw_response=resp,
        )

    def append_assistant_message(self, messages: list[dict[str, Any]], response: L2Response) -> None:
        # Anthropic 把原 content blocks 直接塞回；保留 raw 以維 tool_use 結構完整
        raw = response.raw_response
        if raw is not None and getattr(raw, "content", None) is not None:
            messages.append({"role": "assistant", "content": raw.content})
        else:
            # fallback：純文字 assistant
            messages.append({"role": "assistant", "content": response.text})

    def append_tool_results(
        self,
        messages: list[dict[str, Any]],
        tool_results: list[dict[str, Any]],
    ) -> None:
        content = []
        for tr in tool_results:
            content.append({
                "type": "tool_result",
                "tool_use_id": tr["tool_use_id"],
                "content": tr.get("output_str", ""),
                "is_error": bool(tr.get("is_error", False)),
            })
        messages.append({"role": "user", "content": content})


# ─── OpenAI-compat adapter（同時服務 OpenAI + DeepSeek）────────────

class OpenAICompatProvider(L2ProviderBase):
    """
    OpenAI / DeepSeek 共用同一 SDK 與訊息格式（OpenAI ChatCompletion）。
    僅 base_url + 模型名 + key env_var 不同，由 ctor 注入。
    """

    def __init__(
        self,
        *,
        name: str,
        env_var: str,
        base_url: Optional[str],
        tier_to_model: dict[str, str],
        default_tier: str,
    ) -> None:
        self.name = name
        self._env_var = env_var
        self._base_url = base_url
        self._tier_to_model = tier_to_model
        self._default_tier = default_tier
        self._client: Any = None
        self._lock = threading.Lock()

    def _model_id(self, tier: str) -> str:
        if tier in self._tier_to_model:
            return self._tier_to_model[tier]
        # tier 跨 provider mapping
        mapped = map_tier_to_provider(tier, self.name)
        if mapped in self._tier_to_model:
            return self._tier_to_model[mapped]
        return self._tier_to_model[self._default_tier]

    def is_available(self) -> bool:
        return self._get_client() is not None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        with self._lock:
            if self._client is not None:
                return self._client
            try:
                from openai import OpenAI
            except ImportError:
                logger.warning("openai SDK 未安裝；%sProvider 不可用", self.name)
                return None
            api_key = os.getenv(self._env_var, "")
            if not api_key:
                logger.warning("%s 未設置；%sProvider 不可用", self._env_var, self.name)
                return None
            kwargs: dict[str, Any] = {"api_key": api_key}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = OpenAI(**kwargs)
            return self._client

    def reset(self) -> None:
        with self._lock:
            self._client = None

    def _translate_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Anthropic tools schema → OpenAI function calling tools。
        Anthropic: [{name, description, input_schema}]
        OpenAI:    [{type:'function', function:{name, description, parameters}}]
        """
        out = []
        for t in tools:
            out.append({
                "type": "function",
                "function": {
                    "name": t.get("name", ""),
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema") or {"type": "object", "properties": {}},
                },
            })
        return out

    def _translate_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        把 Anthropic-shape messages 翻譯成 OpenAI-shape。
        - Anthropic 'user' 含 tool_result blocks → OpenAI role='tool' 訊息（每 block 一條）
        - Anthropic 'assistant' 含 tool_use blocks → OpenAI role='assistant' + tool_calls
        - 純字串 content 兩邊一致（直接 pass-through）
        """
        out: list[dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")
            if isinstance(content, str):
                out.append({"role": role, "content": content})
                continue
            if not isinstance(content, list):
                out.append({"role": role, "content": str(content) if content is not None else ""})
                continue
            # content 是 list of blocks
            if role == "user":
                # 拆出 tool_result blocks → role=tool；其他 text/image → 合併成單條 user
                user_text_parts: list[str] = []
                for block in content:
                    btype = _block_type(block)
                    if btype == "tool_result":
                        out.append({
                            "role": "tool",
                            "tool_call_id": _block_field(block, "tool_use_id", ""),
                            "content": _block_field(block, "content", "") or "",
                        })
                    elif btype == "text":
                        user_text_parts.append(_block_field(block, "text", "") or "")
                if user_text_parts:
                    out.append({"role": "user", "content": "\n".join(user_text_parts)})
            elif role == "assistant":
                # text + tool_use blocks
                text_parts: list[str] = []
                tool_calls: list[dict[str, Any]] = []
                for block in content:
                    btype = _block_type(block)
                    if btype == "text":
                        text_parts.append(_block_field(block, "text", "") or "")
                    elif btype == "tool_use":
                        import json as _json
                        tool_calls.append({
                            "id": _block_field(block, "id", ""),
                            "type": "function",
                            "function": {
                                "name": _block_field(block, "name", ""),
                                "arguments": _json.dumps(_block_field(block, "input", {}) or {}),
                            },
                        })
                msg_out: dict[str, Any] = {"role": "assistant"}
                if text_parts:
                    msg_out["content"] = "\n".join(text_parts)
                else:
                    msg_out["content"] = None
                if tool_calls:
                    msg_out["tool_calls"] = tool_calls
                out.append(msg_out)
            else:
                # system / 其他 — 直接放（罕見，layer2_engine 把 system 走獨立參數不放 messages）
                out.append({"role": role, "content": content if isinstance(content, str) else str(content)})
        return out

    def complete(
        self,
        *,
        tier: str,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        max_tokens: int = 4096,
        timeout: float = 120.0,
    ) -> L2Response:
        client = self._get_client()
        if client is None:
            raise RuntimeError(f"{self.name}Provider unavailable (SDK or key missing)")

        # tools 不支援的 tier → 強制移除 tools，避免 API 422
        tier_resolved = tier
        use_tools = tools
        if tier_resolved in TIERS_WITHOUT_TOOLS:
            use_tools = None

        oa_messages = [{"role": "system", "content": system_prompt}] + self._translate_messages(messages)
        kwargs: dict[str, Any] = dict(
            model=self._model_id(tier_resolved),
            max_tokens=max_tokens,
            messages=oa_messages,
        )
        if use_tools:
            kwargs["tools"] = self._translate_tools(use_tools)

        resp = client.chat.completions.create(**kwargs)
        choice = resp.choices[0] if resp.choices else None
        message = choice.message if choice else None

        text = getattr(message, "content", "") or "" if message else ""
        tool_uses: list[ToolUse] = []
        if message and getattr(message, "tool_calls", None):
            import json as _json
            for tc in message.tool_calls:
                fn = getattr(tc, "function", None)
                if not fn:
                    continue
                try:
                    args = _json.loads(getattr(fn, "arguments", "{}") or "{}")
                except (ValueError, TypeError):
                    args = {}
                tool_uses.append(ToolUse(
                    id=getattr(tc, "id", ""),
                    name=getattr(fn, "name", ""),
                    input=args,
                ))

        # OpenAI finish_reason → Anthropic stop_reason mapping
        finish = getattr(choice, "finish_reason", "stop") if choice else "stop"
        stop_reason_map = {
            "stop": "end_turn",
            "length": "max_tokens",
            "tool_calls": "tool_use",
            "function_call": "tool_use",
            "content_filter": "error",
        }
        stop_reason = stop_reason_map.get(finish, "end_turn")
        if tool_uses and stop_reason == "end_turn":
            stop_reason = "tool_use"

        usage = getattr(resp, "usage", None)
        return L2Response(
            text=text,
            tool_uses=tool_uses,
            stop_reason=stop_reason,
            input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0,
            output_tokens=int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0,
            raw_response=resp,
        )

    def append_assistant_message(self, messages: list[dict[str, Any]], response: L2Response) -> None:
        # 用 Anthropic-shape append（後續 _translate_messages 再翻）— 確保混用 provider 時格式一致
        blocks: list[dict[str, Any]] = []
        if response.text:
            blocks.append({"type": "text", "text": response.text})
        for tu in response.tool_uses:
            blocks.append({
                "type": "tool_use",
                "id": tu.id,
                "name": tu.name,
                "input": tu.input,
            })
        if not blocks:
            blocks.append({"type": "text", "text": ""})
        messages.append({"role": "assistant", "content": blocks})

    def append_tool_results(
        self,
        messages: list[dict[str, Any]],
        tool_results: list[dict[str, Any]],
    ) -> None:
        content = []
        for tr in tool_results:
            content.append({
                "type": "tool_result",
                "tool_use_id": tr["tool_use_id"],
                "content": tr.get("output_str", ""),
                "is_error": bool(tr.get("is_error", False)),
            })
        messages.append({"role": "user", "content": content})


def _block_type(block: Any) -> str:
    """支援 dict block 與 SDK obj（getattr）。"""
    if isinstance(block, dict):
        return block.get("type", "")
    return getattr(block, "type", "") or ""


def _block_field(block: Any, key: str, default: Any) -> Any:
    if isinstance(block, dict):
        return block.get(key, default)
    return getattr(block, key, default)


# ─── Provider singleton 工廠 ──────────────────────────────────────

_PROVIDER_INSTANCES: dict[str, L2ProviderBase] = {}
_PROVIDER_LOCK = threading.Lock()


def _build_provider(name: str) -> L2ProviderBase:
    if name == PROVIDER_ANTHROPIC:
        return AnthropicProvider()
    if name == PROVIDER_DEEPSEEK:
        return OpenAICompatProvider(
            name=PROVIDER_DEEPSEEK,
            env_var="DEEPSEEK_API_KEY",
            base_url="https://api.deepseek.com",
            tier_to_model={
                TIER_DEEPSEEK_CHAT: "deepseek-chat",
                TIER_DEEPSEEK_REASONER: "deepseek-reasoner",
            },
            default_tier=TIER_DEEPSEEK_CHAT,
        )
    if name == PROVIDER_OPENAI:
        return OpenAICompatProvider(
            name=PROVIDER_OPENAI,
            env_var="OPENAI_API_KEY",
            base_url=None,  # SDK 預設
            tier_to_model={
                TIER_GPT_4O_MINI: "gpt-4o-mini",
                TIER_GPT_4O: "gpt-4o",
                TIER_O1: "o1",
            },
            default_tier=TIER_GPT_4O_MINI,
        )
    raise ValueError(f"unknown L2 provider: {name}")


def get_provider(name: str) -> L2ProviderBase:
    """回 singleton。未知 provider raise ValueError。"""
    if name not in L2_PROVIDERS:
        raise ValueError(f"L2 provider not whitelisted: {name}")
    if name in _PROVIDER_INSTANCES:
        return _PROVIDER_INSTANCES[name]
    with _PROVIDER_LOCK:
        if name in _PROVIDER_INSTANCES:
            return _PROVIDER_INSTANCES[name]
        _PROVIDER_INSTANCES[name] = _build_provider(name)
        return _PROVIDER_INSTANCES[name]


def reset_provider(name: str) -> None:
    """供 provider_keys_store 在 save/delete key 後呼叫，強迫下次重新建 client。"""
    with _PROVIDER_LOCK:
        inst = _PROVIDER_INSTANCES.get(name)
        if inst is not None:
            try:
                inst.reset()
            except AttributeError:
                # base 沒 reset 方法時 fallback：直接踢出 instance
                _PROVIDER_INSTANCES.pop(name, None)


def reset_all_providers() -> None:
    with _PROVIDER_LOCK:
        for inst in _PROVIDER_INSTANCES.values():
            try:
                inst.reset()
            except AttributeError:
                pass
        _PROVIDER_INSTANCES.clear()


def list_implemented_providers() -> list[str]:
    """回有 client adapter 接線的 provider 名單（GUI/status 用）。"""
    return sorted(L2_PROVIDERS)


__all__ = [
    "PROVIDER_ANTHROPIC", "PROVIDER_DEEPSEEK", "PROVIDER_OPENAI", "L2_PROVIDERS",
    "PROVIDER_TIERS", "TIER_RANK", "TIERS_WITHOUT_TOOLS", "map_tier_to_provider",
    "TIER_HAIKU", "TIER_SONNET", "TIER_OPUS",
    "TIER_DEEPSEEK_CHAT", "TIER_DEEPSEEK_REASONER",
    "TIER_GPT_4O_MINI", "TIER_GPT_4O", "TIER_O1",
    "L2Response", "ToolUse",
    "L2ProviderBase", "AnthropicProvider", "OpenAICompatProvider",
    "get_provider", "reset_provider", "reset_all_providers", "list_implemented_providers",
]
