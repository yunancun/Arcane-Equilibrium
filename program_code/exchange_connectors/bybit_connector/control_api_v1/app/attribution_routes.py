from __future__ import annotations

"""
PnL Attribution API Routes / PnL 歸因分析 API 路由

MODULE_NOTE (中文):
  PnL Attribution API 路由 — 暴露 TradeAttributionEngine 的歸因分析功能。
  所有端點只讀（原則 #2 讀寫分離）。
  4 個端點：全策略聚合 / 單策略詳情 / Skill vs Luck 比例 / 單筆交易歸因。
  Engine singleton 從 phase2_strategy_routes.TRADE_ATTRIBUTION 懶載入。

MODULE_NOTE (English):
  PnL Attribution API routes — expose TradeAttributionEngine analysis capabilities.
  All endpoints read-only (Principle #2: read-write separation).
  4 endpoints: all-strategy summary / single-strategy detail / skill-vs-luck ratios / single-trade attribution.
  Engine singleton lazy-loaded from phase2_strategy_routes.TRADE_ATTRIBUTION.
"""

import datetime
import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# Router / 路由定義
# ═══════════════════════════════════════════════════════════════════════════════

attribution_router = APIRouter(
    prefix="/api/v1/attribution",
    tags=["PnL Attribution / PnL 歸因分析"],
)


def _get_engine():
    """
    Lazy-load the TradeAttributionEngine singleton from phase2_strategy_routes.
    延遲載入 phase2_strategy_routes 中的 TradeAttributionEngine 單例，
    避免循環導入和模塊初始化順序問題。

    Returns the TRADE_ATTRIBUTION singleton, or None if unavailable.
    返回 TRADE_ATTRIBUTION 單例，若不可用則返回 None。
    """
    try:
        from .phase2_strategy_routes import TRADE_ATTRIBUTION
        return TRADE_ATTRIBUTION
    except (ImportError, AttributeError) as exc:
        logger.warning(
            "TradeAttributionEngine not available: %s / 歸因引擎不可用: %s",
            exc, exc,
        )
        return None


def _ok(data: Any) -> Dict[str, Any]:
    """Standard success envelope / 標準成功回應封裝"""
    return {"status": "ok", "data": data}


def _error(message: str, status_code: int = 500) -> None:
    """Raise HTTPException with standard error envelope / 標準錯誤回應"""
    raise HTTPException(
        status_code=status_code,
        detail={"status": "error", "message": message},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Endpoints / 端點
# ═══════════════════════════════════════════════════════════════════════════════


@attribution_router.get("/summary")
async def get_attribution_summary():
    """
    GET /api/v1/attribution/summary
    全策略聚合視圖 — 返回所有策略的歸因摘要。
    All-strategy aggregated view — returns attribution summaries for every strategy.

    Read-only. Returns empty dict when no data available.
    只讀。無數據時返回空字典。
    """
    engine = _get_engine()
    if engine is None:
        return _ok({"by_strategy": {}})

    summaries = engine.list_strategy_summaries()
    return _ok({
        "by_strategy": {
            name: summary.to_dict()
            for name, summary in summaries.items()
        },
    })


@attribution_router.get("/strategy/{name}")
async def get_strategy_attribution(name: str):
    """
    GET /api/v1/attribution/strategy/{name}
    單策略歸因詳情 — 返回指定策略的 6 因子分解（全時間範圍）。
    Single-strategy attribution detail — returns 6-factor decomposition (full time range).

    Read-only. Returns 404 if strategy has no attribution data.
    只讀。策略無數據時返回 404。
    """
    engine = _get_engine()
    if engine is None:
        _error("Attribution engine not available / 歸因引擎不可用", 503)

    # Use full time range for aggregation / 使用完整時間範圍進行聚合
    period_start = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
    period_end = datetime.datetime.now(datetime.timezone.utc)

    result = engine.aggregate_attribution(
        strategy=name,
        period_start=period_start,
        period_end=period_end,
    )

    if result is None:
        _error(
            f"No attribution data for strategy '{name}' / 策略 '{name}' 無歸因數據",
            404,
        )

    return _ok(result.to_dict())


@attribution_router.get("/skill-ratio")
async def get_skill_ratios():
    """
    GET /api/v1/attribution/skill-ratio
    各策略 Skill vs Luck 比例 — 長期追蹤每個策略的技能佔比。
    Per-strategy skill vs luck ratios — long-term tracking of skill contribution.

    Read-only. Returns empty dict when no data available.
    只讀。無數據時返回空字典。
    """
    engine = _get_engine()
    if engine is None:
        return _ok({"by_strategy": {}})

    ratios = engine.list_strategy_skill_ratios()
    return _ok({
        "by_strategy": {
            name: ratio.to_dict()
            for name, ratio in ratios.items()
        },
    })


@attribution_router.get("/trade/{trade_id}")
async def get_trade_attribution(trade_id: str):
    """
    GET /api/v1/attribution/trade/{trade_id}
    單筆交易歸因 — 返回指定交易的完整 6 因子分解結果。
    Single-trade attribution — returns full 6-factor decomposition for a specific trade.

    Read-only. Returns 404 if trade_id not found.
    只讀。找不到 trade_id 時返回 404。
    """
    engine = _get_engine()
    if engine is None:
        _error("Attribution engine not available / 歸因引擎不可用", 503)

    result = engine.get_trade_attribution(trade_id)
    if result is None:
        _error(
            f"No attribution found for trade '{trade_id}' / 找不到交易 '{trade_id}' 的歸因數據",
            404,
        )

    return _ok(result.to_dict())
