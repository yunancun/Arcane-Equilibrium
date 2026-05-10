"""
Cloud AI pricing refresh helpers.

Most providers expose pricing as documentation pages, not as authenticated
machine-readable APIs or webhooks. This module keeps a reviewed price manifest
for the L2-supported cloud models, polls official pricing pages, and stores
source hashes so the GUI can flag when an official page changed.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import ssl
import urllib.error
import urllib.request
from typing import Any


PRICING_REFRESH_INTERVAL_DAYS = 30
DEEPSEEK_V4_PRO_DISCOUNT_UNTIL = _dt.date(2026, 5, 31)

SOURCE_URLS: dict[str, str] = {
    "anthropic": "https://platform.claude.com/docs/claude/docs/models-overview",
    "deepseek": "https://api-docs.deepseek.com/quick_start/pricing",
    "openai": "https://developers.openai.com/api/docs/models/gpt-5.5",
}


def _today(current_date: str | None = None) -> _dt.date:
    if current_date:
        return _dt.date.fromisoformat(current_date)
    return _dt.date.today()


def _iso(current_date: str | None = None) -> str:
    return _today(current_date).isoformat()


def _deepseek_v4_pro_price(day: _dt.date) -> tuple[float, float]:
    if day <= DEEPSEEK_V4_PRO_DISCOUNT_UNTIL:
        return 0.435, 0.87
    return 1.74, 3.48


def official_pricing_manifest(current_date: str | None = None) -> dict[str, dict[str, Any]]:
    day = _today(current_date)
    checked = day.isoformat()
    deepseek_pro_in, deepseek_pro_out = _deepseek_v4_pro_price(day)
    return {
        "haiku": {
            "model_id": "claude-haiku-4-5-20251001",
            "input_per_mtok": 1.00,
            "output_per_mtok": 5.00,
            "last_verified_date": checked,
        },
        "sonnet": {
            "model_id": "claude-sonnet-4-6",
            "input_per_mtok": 3.00,
            "output_per_mtok": 15.00,
            "last_verified_date": checked,
        },
        "opus": {
            "model_id": "claude-opus-4-7",
            "input_per_mtok": 5.00,
            "output_per_mtok": 25.00,
            "last_verified_date": checked,
        },
        "deepseek-v4-flash": {
            "model_id": "deepseek-v4-flash",
            "input_per_mtok": 0.14,
            "output_per_mtok": 0.28,
            "last_verified_date": checked,
        },
        "deepseek-v4-pro": {
            "model_id": "deepseek-v4-pro",
            "input_per_mtok": deepseek_pro_in,
            "output_per_mtok": deepseek_pro_out,
            "last_verified_date": checked,
        },
        "deepseek-chat": {
            "model_id": "deepseek-chat",
            "input_per_mtok": 0.14,
            "output_per_mtok": 0.28,
            "last_verified_date": checked,
        },
        "deepseek-reasoner": {
            "model_id": "deepseek-reasoner",
            "input_per_mtok": 0.14,
            "output_per_mtok": 0.28,
            "last_verified_date": checked,
        },
        "gpt-5.4-mini": {
            "model_id": "gpt-5.4-mini",
            "input_per_mtok": 0.75,
            "output_per_mtok": 4.50,
            "last_verified_date": checked,
        },
        "gpt-5.4": {
            "model_id": "gpt-5.4",
            "input_per_mtok": 2.50,
            "output_per_mtok": 15.00,
            "last_verified_date": checked,
        },
        "gpt-5.5": {
            "model_id": "gpt-5.5",
            "input_per_mtok": 5.00,
            "output_per_mtok": 30.00,
            "last_verified_date": checked,
        },
        "gpt-4o-mini": {
            "model_id": "gpt-4o-mini",
            "input_per_mtok": 0.15,
            "output_per_mtok": 0.60,
            "last_verified_date": checked,
        },
        "gpt-4o": {
            "model_id": "gpt-4o",
            "input_per_mtok": 2.50,
            "output_per_mtok": 10.00,
            "last_verified_date": checked,
        },
        "o1": {
            "model_id": "o1",
            "input_per_mtok": 15.00,
            "output_per_mtok": 60.00,
            "last_verified_date": checked,
        },
    }


def _fetch_source_hashes(timeout: float = 10.0) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    context = None
    try:
        import certifi  # type: ignore
        context = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        context = None
    for provider, url in SOURCE_URLS.items():
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "text/html,application/json",
                "User-Agent": "OpenClaw-ControlAPI/1.0 pricing-refresh",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
                body = resp.read(2_000_000)
            out[provider] = {
                "url": url,
                "http_status": int(getattr(resp, "status", 200)),
                "sha256": hashlib.sha256(body).hexdigest(),
                "ok": True,
                "error": "",
            }
        except urllib.error.HTTPError as exc:
            out[provider] = {
                "url": url,
                "http_status": int(exc.code),
                "sha256": "",
                "ok": False,
                "error": f"HTTP {exc.code}",
            }
        except Exception as exc:
            out[provider] = {
                "url": url,
                "http_status": None,
                "sha256": "",
                "ok": False,
                "error": type(exc).__name__,
            }
    return out


def _pricing_differs(pricing: Any, manifest: dict[str, dict[str, Any]]) -> bool:
    for tier, expected in manifest.items():
        actual = pricing.models.get(tier)
        if actual is None:
            return True
        if actual.model_id != expected["model_id"]:
            return True
        if abs(float(actual.input_per_mtok) - float(expected["input_per_mtok"])) > 1e-9:
            return True
        if abs(float(actual.output_per_mtok) - float(expected["output_per_mtok"])) > 1e-9:
            return True
    return False


def refresh_pricing_if_needed(
    tracker: Any,
    *,
    force_refresh: bool = False,
    current_date: str | None = None,
) -> dict[str, Any]:
    pricing = tracker.get_pricing()
    day = _iso(current_date)
    manifest = official_pricing_manifest(current_date)
    stale = pricing.is_stale(day)
    differs = _pricing_differs(pricing, manifest)
    reasons: list[str] = []
    if force_refresh:
        reasons.append("force_refresh")
    if stale:
        reasons.append("stale_over_30_days")
    if differs:
        reasons.append("pricing_mismatch")

    if not reasons:
        payload = pricing.to_dict()
        payload["refresh_status"] = "fresh"
        payload["refresh_reasons"] = []
        return payload

    previous_sources = dict(getattr(pricing, "source_meta", {}).get("sources", {}))
    sources = _fetch_source_hashes()
    source_changed = False
    for provider, source in sources.items():
        prev_hash = (previous_sources.get(provider) or {}).get("sha256")
        new_hash = source.get("sha256")
        if prev_hash and new_hash and prev_hash != new_hash:
            source_changed = True

    tracker.update_pricing({
        "models": manifest,
        "source_meta": {
            "last_refresh_date": day,
            "refresh_interval_days": PRICING_REFRESH_INTERVAL_DAYS,
            "refresh_reasons": reasons,
            "source_changed": source_changed,
            "needs_manual_review": source_changed,
            "sources": sources,
            "notes": {
                "official_webhook": "No provider pricing webhook is wired; change detection is polling + source hash.",
                "deepseek_v4_pro_discount_until": DEEPSEEK_V4_PRO_DISCOUNT_UNTIL.isoformat(),
            },
        },
    })
    payload = tracker.get_pricing().to_dict()
    payload["refresh_status"] = "refreshed"
    payload["refresh_reasons"] = reasons
    return payload


__all__ = [
    "PRICING_REFRESH_INTERVAL_DAYS",
    "SOURCE_URLS",
    "official_pricing_manifest",
    "refresh_pricing_if_needed",
]
