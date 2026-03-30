from __future__ import annotations

"""
Layer 2 AI Reasoning Engine — API Routes / API 路由
10 条 FastAPI 路由：trigger / sessions / cost / pricing / adaptive / config / ollama

MODULE_NOTE (中文):
  本模块定义 Layer 2 AI 推理引擎的所有 API 路由（10 条）：
  POST /paper/layer2/trigger          — 手动触发 L2 推理 session
  GET  /paper/layer2/sessions         — session 列表
  GET  /paper/layer2/sessions/{id}    — session 详情
  GET  /paper/layer2/cost             — 成本汇总
  GET  /paper/layer2/cost/pricing     — 定价表
  POST /paper/layer2/cost/pricing     — 更新定价表
  GET  /paper/layer2/cost/adaptive    — 自适应预算状态
  GET  /paper/layer2/config           — L2 全量配置
  POST /paper/layer2/config           — 更新配置
  GET  /paper/layer2/ollama/status    — Ollama 连通状态 + 已安装模型列表（GUI 用）

MODULE_NOTE (English):
  Defines all Layer 2 AI Reasoning Engine API routes (10 routes):
  POST /paper/layer2/trigger          — manually trigger L2 reasoning session
  GET  /paper/layer2/sessions         — session list
  GET  /paper/layer2/sessions/{id}    — session detail (reasoning chain + model upgrade + PnL attribution)
  GET  /paper/layer2/cost             — cost summary (today/cumulative/budget/adaptive/pricing warning)
  GET  /paper/layer2/cost/pricing     — pricing table + verification status
  POST /paper/layer2/cost/pricing     — update pricing table
  GET  /paper/layer2/cost/adaptive    — adaptive budget state (multiplier + ROI + history)
  GET  /paper/layer2/config           — L2 full configuration
  POST /paper/layer2/config           — update configuration
  GET  /paper/layer2/ollama/status    — Ollama connectivity check + installed model list (GUI use)
"""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from . import main_legacy as base
from .layer2_cost_tracker import Layer2CostTracker
from .layer2_engine import Layer2Engine
from .paper_trading_routes import ENGINE as PAPER_ENGINE, SHADOW_CONSUMER

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# Router & Shared State / 路由与共享状态
# ═══════════════════════════════════════════════════════════════════════════════

layer2_router = APIRouter(
    prefix="/api/v1/paper/layer2",
    tags=["Layer 2 AI Reasoning / L2 AI 推理引擎"],
)

# Lazy-initialized singletons
_cost_tracker: Layer2CostTracker | None = None
_engine: Layer2Engine | None = None


def _get_cost_tracker() -> Layer2CostTracker:
    global _cost_tracker
    if _cost_tracker is None:
        _cost_tracker = Layer2CostTracker()
    return _cost_tracker


def _get_engine() -> Layer2Engine:
    global _engine
    if _engine is None:
        _engine = Layer2Engine(
            cost_tracker=_get_cost_tracker(),
            paper_engine=PAPER_ENGINE,
            shadow_consumer=SHADOW_CONSUMER,
        )
    return _engine


def _layer2_response(
    data: Any,
    action_result: str = "success",
    reason_codes: list[str] | None = None,
) -> dict[str, Any]:
    """Build response envelope for Layer 2 routes / 构建 Layer 2 路由的响应 envelope"""
    return {
        "api_version": "v1",
        "action_result": action_result,
        "reason_codes": reason_codes or [],
        "data_category": "paper_simulated",
        "is_simulated": True,
        "module": "layer2_ai_reasoning_engine",
        "data": data,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Request Models / 请求模型
# ═══════════════════════════════════════════════════════════════════════════════

class TriggerRequest(BaseModel):
    symbol: str = Field(default="BTCUSDT", max_length=30)
    context: str = Field(default="", max_length=2000)
    skip_triage: bool = Field(default=False)
    market_prices: dict[str, float] | None = None


class PricingUpdateRequest(BaseModel):
    models: dict[str, dict[str, Any]] = Field(default_factory=dict)
    perplexity_per_search: float | None = None
    perplexity_last_verified_date: str | None = None


class ConfigUpdateRequest(BaseModel):
    daily_hard_cap_usd: float | None = Field(default=None, gt=0, le=100)
    session_budget_sonnet_usd: float | None = Field(default=None, gt=0, le=50)
    session_budget_opus_usd: float | None = Field(default=None, gt=0, le=50)
    adaptive_enabled: bool | None = None
    adaptive_base_daily_usd: float | None = Field(default=None, gt=0, le=100)
    adaptive_max_multiplier: float | None = Field(default=None, gt=0, le=5)
    adaptive_min_multiplier: float | None = Field(default=None, gt=0, le=2)
    default_model: str | None = Field(default=None, max_length=20)
    allow_opus_upgrade: bool | None = None
    max_iterations: int | None = Field(default=None, gt=0, le=50)
    search_providers_enabled: list[str] | None = None
    search_max_results: int | None = Field(default=None, gt=0, le=20)
    auto_submit_to_paper: bool | None = None
    confidence_threshold: float | None = Field(default=None, ge=0, le=1)
    edge_threshold_bps: float | None = Field(default=None, ge=0)


# ═══════════════════════════════════════════════════════════════════════════════
# Routes / 路由
# ═══════════════════════════════════════════════════════════════════════════════

@layer2_router.post("/trigger")
async def trigger_l2_session(
    req: TriggerRequest,
    background_tasks: BackgroundTasks,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """
    Trigger a Layer 2 reasoning session.
    触发一次 Layer 2 推理 session。

    The session runs in the background. Use GET /sessions/{id} to check progress.
    Session 在后台运行。使用 GET /sessions/{id} 查看进度。
    """
    engine = _get_engine()
    tracker = _get_cost_tracker()

    # Check if already running
    if engine.is_running:
        return _layer2_response(
            {"status": "already_running", "message": "Another L2 session is currently running"},
            action_result="blocked",
            reason_codes=["l2_session_already_running"],
        )

    # Budget check
    allowed, remaining = tracker.check_daily_budget()
    if not allowed:
        return _layer2_response(
            {"status": "budget_exceeded", "remaining_usd": remaining},
            action_result="blocked",
            reason_codes=["daily_budget_exceeded"],
        )

    # L1 triage (unless skipped)
    triage_result = None
    if not req.skip_triage:
        triage_result = await engine.l1_triage()
        if not triage_result.get("worth_investigating", False) and not triage_result.get("error"):
            return _layer2_response(
                {
                    "status": "triage_rejected",
                    "triage": triage_result,
                    "message": "L1 triage determined investigation not warranted",
                },
                action_result="deferred",
                reason_codes=["l1_triage_rejected"],
            )

    # Run session in background
    async def _run():
        await engine.run_session(
            trigger="manual",
            symbol=req.symbol,
            context=req.context,
            market_prices=req.market_prices,
        )

    background_tasks.add_task(asyncio.ensure_future, _run())

    return _layer2_response({
        "status": "triggered",
        "symbol": req.symbol,
        "triage": triage_result,
        "budget_remaining_usd": remaining,
    })


@layer2_router.get("/sessions")
async def get_sessions(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """
    Get L2 session history.
    获取 L2 session 历史。
    """
    tracker = _get_cost_tracker()
    sessions = tracker.get_sessions(limit=limit, offset=offset)
    return _layer2_response({
        "sessions": sessions,
        "count": len(sessions),
        "limit": limit,
        "offset": offset,
    })


@layer2_router.get("/sessions/{session_id}")
async def get_session_detail(
    session_id: str,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """
    Get detailed L2 session info including reasoning chain, model upgrade, PnL attribution.
    获取 L2 session 详情，包括推理链、模型升级和 PnL 归因。
    """
    tracker = _get_cost_tracker()
    session = tracker.get_session_by_id(session_id)
    if session is None:
        engine = _get_engine()
        current = engine.get_current_session()
        if current and current.session_id == session_id:
            return _layer2_response(current.to_dict())
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return _layer2_response(session)


@layer2_router.get("/cost")
async def get_cost_summary(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """
    Get Layer 2 cost summary (today / cumulative / budget / adaptive / pricing warning).
    获取 Layer 2 成本汇总。
    """
    tracker = _get_cost_tracker()
    return _layer2_response(tracker.get_cost_summary())


@layer2_router.get("/cost/pricing")
async def get_pricing(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """
    Get pricing table and verification status.
    获取定价表和核实状态。
    """
    tracker = _get_cost_tracker()
    return _layer2_response(tracker.get_pricing().to_dict())


@layer2_router.post("/cost/pricing")
async def update_pricing(
    req: PricingUpdateRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """
    Update pricing table entries.
    更新定价表条目。
    """
    tracker = _get_cost_tracker()
    updates: dict[str, Any] = {}
    if req.models:
        updates["models"] = req.models
    if req.perplexity_per_search is not None:
        updates["perplexity_per_search"] = req.perplexity_per_search
    if req.perplexity_last_verified_date is not None:
        updates["perplexity_last_verified_date"] = req.perplexity_last_verified_date

    if not updates:
        return _layer2_response(
            {"message": "No updates provided"},
            action_result="blocked",
            reason_codes=["empty_update"],
        )

    pricing = tracker.update_pricing(updates)
    return _layer2_response({
        "pricing": pricing.to_dict(),
        "message": "Pricing updated successfully",
    })


@layer2_router.get("/cost/adaptive")
async def get_adaptive_budget(
    recalculate: bool = Query(default=False),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """
    Get adaptive budget state. Optionally recalculate from recent data.
    获取自适应预算状态。可选择从近期数据重算。
    """
    tracker = _get_cost_tracker()
    if recalculate:
        state = tracker.recalculate_adaptive()
    else:
        state = tracker.get_adaptive_state()
    return _layer2_response(state.to_dict())


@layer2_router.get("/config")
async def get_config(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """
    Get Layer 2 full configuration.
    获取 Layer 2 完整配置。
    """
    tracker = _get_cost_tracker()
    return _layer2_response(tracker.get_config().to_dict())


@layer2_router.get("/ollama/status")
async def get_ollama_status() -> dict[str, Any]:
    """
    Check Ollama connectivity and list available models.
    检查 Ollama 连通状态并列出可用模型。

    Returns:
        available (bool)   — whether Ollama is reachable / Ollama 是否可达
        base_url  (str)    — configured endpoint / 已配置的端点地址
        default_model (str)— default model name / 默认模型名称
        models    (list)   — installed model names from /api/tags / 已安装的模型列表
        model_count (int)  — number of installed models / 已安装模型数量
    """
    from .ollama_client import get_ollama_client  # local import to avoid circular deps / 避免循环导入

    client = get_ollama_client()
    # is_available() has a 60s TTL cache — cheap to call on every GUI refresh
    # is_available() 内置 60s TTL 缓存，每次 GUI 刷新调用无额外开销
    available = client.is_available()
    result: dict[str, Any] = {
        "available": available,
        "base_url": client.config.base_url,
        "default_model": client.config.model,
    }
    if available:
        # Fetch installed model list via /api/tags (Ollama standard endpoint)
        # 通过 /api/tags 获取已安装模型列表（Ollama 标准端点）
        import urllib.request, json as _json
        try:
            url = client.config.base_url.rstrip("/") + "/api/tags"
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = _json.loads(resp.read())
            models = [m["name"] for m in data.get("models", [])]
            result["models"] = models
            result["model_count"] = len(models)
        except Exception as exc:
            # Non-fatal: connectivity confirmed but model list unavailable
            # 非致命错误：连通性已确认，但模型列表无法获取
            result["models"] = []
            result["model_list_error"] = str(exc)
    return _layer2_response(result)


@layer2_router.post("/config")
async def update_config(
    req: ConfigUpdateRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """
    Update Layer 2 configuration.
    更新 Layer 2 配置。
    """
    tracker = _get_cost_tracker()
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        return _layer2_response(
            {"message": "No updates provided"},
            action_result="blocked",
            reason_codes=["empty_update"],
        )

    config = tracker.update_config(updates)
    return _layer2_response({
        "config": config.to_dict(),
        "message": "Configuration updated successfully",
    })
