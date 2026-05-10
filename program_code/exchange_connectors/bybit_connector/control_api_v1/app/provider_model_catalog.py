"""
Provider model catalog for Tab-AI Engine Settings.

The catalog has two jobs:
  1. Fetch the provider's real model list with the stored API key.
  2. Expose only L2-supported/priced models to Engine Settings selects.

Raw provider model IDs are returned as metadata so the GUI can be honest about
what came from the provider versus what is a documented compatibility alias.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from . import provider_client
from . import provider_keys_store
from .layer2_types import MODEL_HAIKU, MODEL_IDS, MODEL_OPUS, MODEL_SONNET

logger = logging.getLogger(__name__)


DEFAULT_CATALOG_TTL_SECONDS = 6 * 60 * 60
LOCAL_CATALOG_TTL_SECONDS = 60
DEEPSEEK_LEGACY_DEPRECATION_DATE = "2026-07-24"

_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_LOCK = threading.Lock()


def _ttl_seconds() -> int:
    raw = os.environ.get("OPENCLAW_PROVIDER_MODEL_CATALOG_TTL_SECONDS", "")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_CATALOG_TTL_SECONDS
    return max(60, min(value, 24 * 60 * 60))


def invalidate_provider(provider: str | None = None) -> None:
    """Clear cached model catalog entries after key save/delete."""
    with _CACHE_LOCK:
        if provider:
            _CACHE.pop(provider, None)
        else:
            _CACHE.clear()


def _now_ms() -> int:
    return int(time.time() * 1000)


def _read_model_ids(provider: str, key: str, *, timeout: float = 12.0) -> dict[str, Any]:
    urls = provider_keys_store._validation_urls(provider)  # same readonly endpoints as key probe
    headers = provider_keys_store._validation_headers(provider, key)
    last_error: dict[str, Any] = {
        "refresh_status": "not_supported",
        "refresh_error": "",
        "endpoint": None,
        "http_status": None,
    }
    for url in urls:
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = resp.read(2_000_000)
            body = json.loads(payload.decode("utf-8"))
            rows = body.get("data") if isinstance(body, dict) else []
            if rows is None and isinstance(body, dict):
                rows = body.get("models")
            ids: list[str] = []
            for row in rows or []:
                if isinstance(row, str):
                    value = row
                elif isinstance(row, dict):
                    value = str(row.get("id") or row.get("name") or "")
                else:
                    value = ""
                if value and value not in ids:
                    ids.append(value)
            return {
                "refresh_status": "ok",
                "refresh_error": "",
                "endpoint": url,
                "http_status": int(getattr(resp, "status", 200)),
                "provider_model_ids": ids,
            }
        except urllib.error.HTTPError as exc:
            last_error = {
                "refresh_status": "http_error",
                "refresh_error": f"HTTP {exc.code}",
                "endpoint": url,
                "http_status": int(exc.code),
            }
            if exc.code in {404, 405}:
                continue
            break
        except urllib.error.URLError as exc:
            last_error = {
                "refresh_status": "network_error",
                "refresh_error": str(exc.reason)[:160],
                "endpoint": url,
                "http_status": None,
            }
            break
        except Exception as exc:
            last_error = {
                "refresh_status": "parse_error",
                "refresh_error": type(exc).__name__,
                "endpoint": url,
                "http_status": None,
            }
            break
    last_error["provider_model_ids"] = []
    return last_error


def _read_local_model_ids(*, timeout: float = 5.0) -> dict[str, Any]:
    try:
        from .local_llm_factory import PROVIDER_LM_STUDIO, _resolve_provider, get_local_llm_client

        client = get_local_llm_client()
        local_provider = _resolve_provider()
        available = bool(client.is_available())
        endpoint = None
        model_ids: list[str] = []
        if available:
            if hasattr(client, "list_models"):
                model_ids = [str(m) for m in client.list_models() if str(m)]
                endpoint = str(client.config.base_url).rstrip("/") + "/api/tags"
            elif local_provider == PROVIDER_LM_STUDIO:
                endpoint = str(client.config.base_url).rstrip("/") + "/models"
                with urllib.request.urlopen(endpoint, timeout=timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                model_ids = [
                    str(m.get("id") or "")
                    for m in data.get("data", [])
                    if isinstance(m, dict) and (m.get("id") or "")
                ]
        default_model = str(getattr(client.config, "model", "") or "")
        if available and default_model and default_model not in model_ids:
            model_ids.append(default_model)
        return {
            "refresh_status": "ok" if available else "local_unavailable",
            "refresh_error": "",
            "endpoint": endpoint,
            "http_status": 200 if available else None,
            "provider_model_ids": model_ids,
            "default_model": default_model,
            "local_provider": local_provider,
            "available": available,
        }
    except Exception as exc:
        return {
            "refresh_status": "local_error",
            "refresh_error": str(exc)[:160],
            "endpoint": None,
            "http_status": None,
            "provider_model_ids": [],
            "default_model": "",
            "available": False,
        }


def _static_l2_models(provider: str) -> list[dict[str, Any]]:
    if provider == provider_client.PROVIDER_ANTHROPIC:
        return [
            {
                "value": MODEL_HAIKU,
                "model_id": MODEL_IDS[MODEL_HAIKU],
                "label": "haiku - Claude Haiku 4.5",
                "rank": provider_client.TIER_RANK[MODEL_HAIKU],
                "l2_supported": True,
            },
            {
                "value": MODEL_SONNET,
                "model_id": MODEL_IDS[MODEL_SONNET],
                "label": "sonnet - Claude Sonnet 4.6",
                "rank": provider_client.TIER_RANK[MODEL_SONNET],
                "l2_supported": True,
            },
            {
                "value": MODEL_OPUS,
                "model_id": MODEL_IDS[MODEL_OPUS],
                "label": "opus - Claude Opus 4.7",
                "rank": provider_client.TIER_RANK[MODEL_OPUS],
                "l2_supported": True,
            },
        ]
    if provider == provider_client.PROVIDER_DEEPSEEK:
        return [
            {
                "value": provider_client.TIER_DEEPSEEK_V4_FLASH,
                "model_id": "deepseek-v4-flash",
                "label": "deepseek-v4-flash - V4 Flash",
                "rank": provider_client.TIER_RANK[provider_client.TIER_DEEPSEEK_V4_FLASH],
                "l2_supported": True,
            },
            {
                "value": provider_client.TIER_DEEPSEEK_V4_PRO,
                "model_id": "deepseek-v4-pro",
                "label": "deepseek-v4-pro - V4 Pro",
                "rank": provider_client.TIER_RANK[provider_client.TIER_DEEPSEEK_V4_PRO],
                "l2_supported": True,
            },
            {
                "value": provider_client.TIER_DEEPSEEK_CHAT,
                "model_id": "deepseek-chat",
                "label": "deepseek-chat - legacy V4 Flash non-thinking",
                "rank": provider_client.TIER_RANK[provider_client.TIER_DEEPSEEK_CHAT],
                "l2_supported": True,
                "deprecated": True,
                "deprecation_date": DEEPSEEK_LEGACY_DEPRECATION_DATE,
                "alias_of": "deepseek-v4-flash",
            },
            {
                "value": provider_client.TIER_DEEPSEEK_REASONER,
                "model_id": "deepseek-reasoner",
                "label": "deepseek-reasoner - legacy V4 Flash thinking",
                "rank": provider_client.TIER_RANK[provider_client.TIER_DEEPSEEK_REASONER],
                "l2_supported": True,
                "deprecated": True,
                "deprecation_date": DEEPSEEK_LEGACY_DEPRECATION_DATE,
                "alias_of": "deepseek-v4-flash",
            },
        ]
    if provider == provider_client.PROVIDER_OPENAI:
        return [
            {
                "value": provider_client.TIER_GPT_5_4_MINI,
                "model_id": "gpt-5.4-mini",
                "label": "gpt-5.4-mini",
                "rank": provider_client.TIER_RANK[provider_client.TIER_GPT_5_4_MINI],
                "l2_supported": True,
            },
            {
                "value": provider_client.TIER_GPT_5_4,
                "model_id": "gpt-5.4",
                "label": "gpt-5.4",
                "rank": provider_client.TIER_RANK[provider_client.TIER_GPT_5_4],
                "l2_supported": True,
            },
            {
                "value": provider_client.TIER_GPT_5_5,
                "model_id": "gpt-5.5",
                "label": "gpt-5.5",
                "rank": provider_client.TIER_RANK[provider_client.TIER_GPT_5_5],
                "l2_supported": True,
            },
            {
                "value": provider_client.TIER_GPT_4O_MINI,
                "model_id": "gpt-4o-mini",
                "label": "gpt-4o-mini - legacy",
                "rank": provider_client.TIER_RANK[provider_client.TIER_GPT_4O_MINI],
                "l2_supported": True,
            },
            {
                "value": provider_client.TIER_GPT_4O,
                "model_id": "gpt-4o",
                "label": "gpt-4o - legacy",
                "rank": provider_client.TIER_RANK[provider_client.TIER_GPT_4O],
                "l2_supported": True,
            },
            {
                "value": provider_client.TIER_O1,
                "model_id": "o1",
                "label": "o1 - legacy reasoner",
                "rank": provider_client.TIER_RANK[provider_client.TIER_O1],
                "l2_supported": True,
            },
        ]
    if provider == provider_client.PROVIDER_LOCAL_LLM:
        local = _read_local_model_ids()
        rows = []
        for idx, model_id in enumerate(local.get("provider_model_ids") or []):
            tier = provider_client.make_local_tier(str(model_id))
            rows.append({
                "value": tier,
                "model_id": str(model_id),
                "label": f"{model_id} - Local LLM",
                "rank": 10 + idx,
                "l2_supported": True,
                "zero_cost": True,
                "supports_tools": False,
            })
        return rows
    return []


def _decorate_supported_models(
    provider: str,
    supported: list[dict[str, Any]],
    provider_model_ids: list[str],
) -> list[dict[str, Any]]:
    ids = set(provider_model_ids)
    decorated: list[dict[str, Any]] = []
    for model in supported:
        item = dict(model)
        model_id = str(item.get("model_id") or item.get("value") or "")
        alias_of = str(item.get("alias_of") or "")
        listed = model_id in ids
        alias_backed = bool(alias_of and alias_of in ids)
        item["provider"] = provider
        item["provider_listed"] = listed
        item["provider_available"] = listed or alias_backed or not provider_model_ids
        if alias_backed and not listed:
            item["availability_source"] = "documented_alias"
        elif listed:
            item["availability_source"] = "provider_models_endpoint"
        elif provider_model_ids:
            item["availability_source"] = "not_listed_by_provider"
        else:
            item["availability_source"] = "fallback_static"
        decorated.append(item)
    decorated.sort(key=lambda m: (int(m.get("rank") or 99), str(m.get("value") or "")))
    return decorated


def _build_provider_catalog(provider: str, *, force_refresh: bool, ttl_seconds: int) -> dict[str, Any]:
    now_ms = _now_ms()
    provider_ttl_seconds = LOCAL_CATALOG_TTL_SECONDS if provider == provider_client.PROVIDER_LOCAL_LLM else ttl_seconds
    with _CACHE_LOCK:
        cached = _CACHE.get(provider)
        if cached and not force_refresh and int(cached.get("expires_at_ms") or 0) > now_ms:
            out = copy.deepcopy(cached)
            out["cache_hit"] = True
            return out

    supported = _static_l2_models(provider)
    fetched: dict[str, Any]
    if provider == provider_client.PROVIDER_LOCAL_LLM:
        fetched = _read_local_model_ids()
    else:
        key = provider_keys_store._read_key_from_file(provider)
        if key:
            fetched = _read_model_ids(provider, key)
        else:
            fetched = {
                "refresh_status": "no_key",
                "refresh_error": "",
                "endpoint": None,
                "http_status": None,
                "provider_model_ids": [],
            }

    provider_model_ids = list(fetched.get("provider_model_ids") or [])
    fetched_at_ms = now_ms if fetched.get("refresh_status") == "ok" else None
    expires_at_ms = now_ms + provider_ttl_seconds * 1000
    out = {
        "provider": provider,
        "cache_hit": False,
        "ttl_seconds": provider_ttl_seconds,
        "fetched_at_ms": fetched_at_ms,
        "expires_at_ms": expires_at_ms,
        "refresh_status": fetched.get("refresh_status"),
        "refresh_error": fetched.get("refresh_error"),
        "endpoint": fetched.get("endpoint"),
        "http_status": fetched.get("http_status"),
        "local_provider": fetched.get("local_provider"),
        "available": fetched.get("available"),
        "default_model": fetched.get("default_model"),
        "provider_models_count": len(provider_model_ids),
        "provider_model_ids": provider_model_ids,
        "models": _decorate_supported_models(provider, supported, provider_model_ids),
    }

    # Cache no-key/failure states too; the TTL is short enough and save/delete invalidates.
    with _CACHE_LOCK:
        _CACHE[provider] = copy.deepcopy(out)
    return out


def get_model_catalog(*, force_refresh: bool = False) -> dict[str, Any]:
    ttl = _ttl_seconds()
    providers = {
        provider: _build_provider_catalog(provider, force_refresh=force_refresh, ttl_seconds=ttl)
        for provider in sorted(provider_client.L2_PROVIDERS)
    }
    return {
        "generated_at_ms": _now_ms(),
        "ttl_seconds": ttl,
        "local_ttl_seconds": LOCAL_CATALOG_TTL_SECONDS,
        "providers": providers,
    }


def allowed_model_values(provider: str) -> list[str]:
    return [str(m["value"]) for m in _static_l2_models(provider)]


__all__ = [
    "DEEPSEEK_LEGACY_DEPRECATION_DATE",
    "allowed_model_values",
    "get_model_catalog",
    "invalidate_provider",
]
