"""OpenClaw gateway AI-cost route for paper trading.

OpenClaw gateway AI 成本路由；Paper/Demo/Live 指標只讀復用此成本來源。
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from fastapi import APIRouter, Depends

from . import main_legacy as base
from .paper_trading_response import paper_response

ai_cost_router = APIRouter()


def _fetch_openclaw_usage_cost() -> dict[str, Any] | None:
    """Fetch AI usage cost from OpenClaw gateway CLI.

    透過 OpenClaw gateway CLI 讀取 AI 用量成本；失敗時返回 None。
    """
    try:
        result = subprocess.run(
            ["openclaw", "gateway", "usage-cost", "--json", "--days", "30"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        return None


def fetch_total_ai_cost_30d() -> float | None:
    """Return OpenClaw gateway 30-day total AI cost, or None if unavailable.

    返回 OpenClaw gateway 30 日 AI 總成本；不可用時返回 None。
    """
    raw = _fetch_openclaw_usage_cost()
    if raw is None:
        return None
    try:
        return float((raw.get("totals") or {}).get("totalCost", 0.0))
    except (TypeError, ValueError):
        return None


@ai_cost_router.get("/ai-cost")
def get_ai_cost(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get AI usage cost from OpenClaw gateway.

    從 OpenClaw gateway 讀取 AI 用量成本並包成 Paper API response。
    """
    raw = _fetch_openclaw_usage_cost()
    if raw is None:
        return paper_response({
            "available": False,
            "message": "OpenClaw gateway not reachable / OpenClaw 网关不可达",
            "today_cost": 0.0,
            "today_tokens": 0,
            "total_cost_30d": 0.0,
            "total_tokens_30d": 0,
            "daily": [],
        })

    daily = raw.get("daily", [])
    totals = raw.get("totals", {})

    today_entry = daily[-1] if daily else {}
    today_cost = today_entry.get("totalCost", 0.0)
    today_tokens = today_entry.get("totalTokens", 0)

    return paper_response({
        "available": True,
        "source": "openclaw_gateway_usage_cost",
        "today_cost": round(today_cost, 6),
        "today_tokens": today_tokens,
        "total_cost_30d": round(totals.get("totalCost", 0.0), 6),
        "total_tokens_30d": totals.get("totalTokens", 0),
        "cost_breakdown": {
            "input_cost": round(totals.get("inputCost", 0.0), 6),
            "output_cost": round(totals.get("outputCost", 0.0), 6),
            "cache_read_cost": round(totals.get("cacheReadCost", 0.0), 6),
            "cache_write_cost": round(totals.get("cacheWriteCost", 0.0), 6),
        },
        "daily": daily[-7:],
    })
