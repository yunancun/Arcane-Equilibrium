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
from . import provider_client
from . import provider_keys_store
from . import provider_model_catalog
from . import provider_pricing_catalog
from .layer2_cost_tracker import Layer2CostTracker
from .layer2_engine import Layer2Engine
# ARCH-RC1 1C-3-F: Layer 2's paper-side path now goes through the Rust engine
# via IPC. PAPER_ENGINE / SHADOW_CONSUMER from paper_trading_routes were both
# `None` in production after RC-10; the consumer is now built on-demand below
# from the EngineIPCClient singleton.
# ARCH-RC1 1C-3-F：Layer 2 紙盤路徑改走 IPC，consumer 在此模組內按需建構。
from .shadow_decision_builder import ShadowDecisionConsumer

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


def _build_shadow_consumer() -> ShadowDecisionConsumer | None:
    """Build a ShadowDecisionConsumer backed by the EngineIPCClient singleton.
    Returns None when the IPC client cannot be resolved (test env / boot race);
    Layer 2 falls back to "no paper submission" in that case.
    建構由 EngineIPCClient singleton 支撐的 ShadowDecisionConsumer。
    IPC 不可用時返回 None；Layer 2 會跳過紙盤提交。
    """
    try:
        from .ipc_client import EngineIPCClient  # noqa: PLC0415
        factory = getattr(EngineIPCClient, "get_singleton", None)
        if factory is None:
            return None
        client = factory()
        return ShadowDecisionConsumer(client=client)
    except Exception as exc:
        logger.warning("ShadowDecisionConsumer wiring skipped: %s", exc)
        return None


def _get_engine() -> Layer2Engine:
    global _engine
    if _engine is None:
        _engine = Layer2Engine(
            cost_tracker=_get_cost_tracker(),
            paper_engine=None,  # ARCH-RC1 1C-3-F: Python paper engine retired
            shadow_consumer=_build_shadow_consumer(),
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
    default_model: str | None = Field(default=None, max_length=128)
    default_provider: str | None = Field(default=None, max_length=20)
    allow_opus_upgrade: bool | None = None
    max_iterations: int | None = Field(default=None, gt=0, le=50)
    search_providers_enabled: list[str] | None = None
    search_max_results: int | None = Field(default=None, gt=0, le=20)
    auto_submit_to_paper: bool | None = None
    confidence_threshold: float | None = Field(default=None, ge=0, le=1)
    edge_threshold_bps: float | None = Field(default=None, ge=0)
    # Tier 2/3 預算降級（layer2_engine._resolve_effective_provider 用）
    fallback_tier2_provider: str | None = Field(default=None, max_length=20)
    fallback_tier2_model: str | None = Field(default=None, max_length=128)
    fallback_tier2_threshold_pct: float | None = Field(default=None, ge=0, le=1)
    fallback_tier3_provider: str | None = Field(default=None, max_length=20)
    fallback_tier3_model: str | None = Field(default=None, max_length=128)
    fallback_tier3_threshold_pct: float | None = Field(default=None, ge=0, le=1)
    # GUI Tab-AI 「AI 供应商管理」面板新增。
    # provider_keys: { provider_name: api_key }，由 provider_keys_store 持久化到
    # secrets/providers/<provider>.env，並注入當前進程 env（Anthropic 還會 reset client）。
    # 不會進 Layer2Config（不是引擎參數，是憑證 secrets）。
    provider_keys: dict[str, str] | None = Field(default=None)


_PROVIDER_MODEL_CONFIG_KEYS = frozenset({
    "default_provider",
    "default_model",
    "fallback_tier2_provider",
    "fallback_tier2_model",
    "fallback_tier3_provider",
    "fallback_tier3_model",
})


def _validate_provider_model_pair(provider: str, model: str, *, field_prefix: str) -> None:
    if provider not in provider_client.L2_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail={
                "reason_codes": ["provider_not_l2_capable"],
                "field": f"{field_prefix}_provider",
                "provider": provider,
            },
        )
    allowed = provider_model_catalog.allowed_model_values(provider)
    if model not in allowed:
        raise HTTPException(
            status_code=400,
            detail={
                "reason_codes": ["model_not_supported_by_provider"],
                "field": f"{field_prefix}_model",
                "provider": provider,
                "model": model,
                "allowed_models": allowed,
            },
        )


def _validate_layer2_model_config(updates: dict[str, Any], current: Any) -> None:
    """拒絕會讓 provider/model 配對失真的 GUI/API 寫入。"""
    if not (_PROVIDER_MODEL_CONFIG_KEYS & updates.keys()):
        return
    candidate = current.to_dict()
    candidate.update(updates)
    _validate_provider_model_pair(
        str(candidate.get("default_provider") or ""),
        str(candidate.get("default_model") or ""),
        field_prefix="default",
    )
    _validate_provider_model_pair(
        str(candidate.get("fallback_tier2_provider") or ""),
        str(candidate.get("fallback_tier2_model") or ""),
        field_prefix="fallback_tier2",
    )
    _validate_provider_model_pair(
        str(candidate.get("fallback_tier3_provider") or ""),
        str(candidate.get("fallback_tier3_model") or ""),
        field_prefix="fallback_tier3",
    )


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
    base.require_scope_and_operator(actor, "ai_budget:write")
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


@layer2_router.post("/cost/reset")
async def reset_today_costs(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """
    Zero-out today's AI cost counters (claude_usd, search_usd, total_usd, session_count).
    Operator action — useful for calibration after a test run.
    将今日 AI 成本计数器归零（校准用途）。
    """
    tracker = _get_cost_tracker()
    zeroed = tracker.reset_today_costs()
    return _layer2_response({
        "message": "Today's AI cost counters reset to zero / 今日 AI 成本已归零",
        "cleared": zeroed,
    })


@layer2_router.get("/cost/pricing")
async def get_pricing(
    force_refresh: bool = Query(default=False),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """
    Get pricing table and verification status.
    获取定价表和核实状态。
    """
    tracker = _get_cost_tracker()
    return _layer2_response(
        provider_pricing_catalog.refresh_pricing_if_needed(
            tracker,
            force_refresh=force_refresh,
        )
    )


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
    Check local LLM connectivity and list available models.
    检查本地 LLM 连通状态并列出可用模型。

    LLM-ABC-MIGRATION-1: routed via local_llm_factory (LOCAL_LLM_PROVIDER env
    switches between Ollama /api/tags and LM Studio /v1/models).
    Endpoint name retained for GUI compatibility.
    LLM-ABC-MIGRATION-1：經 local_llm_factory 路由；依 provider 切換模型列表端點。
    端點名保留不動以維持 GUI 相容。

    Returns:
        available (bool)   — whether local LLM is reachable / 本地 LLM 是否可达
        provider  (str)    — "ollama" | "lm_studio"
        base_url  (str)    — configured endpoint / 已配置的端点地址
        default_model (str)— default model name / 默认模型名称
        models    (list)   — installed model names / 已安装的模型列表
        model_count (int)  — number of installed models / 已安装模型数量
    """
    from .local_llm_factory import (  # local import to avoid circular deps / 避免循环导入
        get_local_llm_client, PROVIDER_LM_STUDIO, _resolve_provider,
    )

    client = get_local_llm_client()
    provider = _resolve_provider()
    # is_available() has a 60s TTL cache — cheap to call on every GUI refresh
    # is_available() 内置 60s TTL 缓存，每次 GUI 刷新调用无额外开销
    available = client.is_available()
    result: dict[str, Any] = {
        "available": available,
        "provider": provider,
        "base_url": client.config.base_url,
        "default_model": client.config.model,
    }
    if available:
        # Fetch installed model list per provider — Ollama: /api/tags; LM Studio: /v1/models
        # 依 provider 取模型列表 — Ollama 走 /api/tags，LM Studio 走 /v1/models
        import urllib.request, json as _json
        try:
            if provider == PROVIDER_LM_STUDIO:
                url = client.config.base_url.rstrip("/") + "/models"
                with urllib.request.urlopen(url, timeout=5) as resp:
                    data = _json.loads(resp.read())
                models = [m.get("id", "") for m in data.get("data", [])]
            else:
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
    更新 Layer 2 配置（包含 provider API keys）。

    provider_keys 路由到 provider_keys_store（寫 secrets/providers/<p>.env + 注入 env）；
    不進 Layer2Config（憑證不是引擎參數）。其餘欄位走 cost_tracker.update_config。
    """
    tracker = _get_cost_tracker()
    raw = req.model_dump()
    provider_keys: dict[str, str] | None = raw.pop("provider_keys", None)
    updates = {k: v for k, v in raw.items() if v is not None}
    _validate_layer2_model_config(updates, tracker.get_config())

    # ── provider keys 寫入 + 即時 env 注入 ───────────────────────────
    # 寫入屬狀態變更，要求 Operator 角色（API key 是憑證，比一般 config 敏感）。
    provider_results: list[dict[str, Any]] = []
    provider_errors: list[dict[str, Any]] = []
    if provider_keys:
        base.require_operator_role(actor)
        for provider, key in provider_keys.items():
            if provider not in provider_keys_store.ALLOWED_PROVIDERS:
                provider_errors.append({
                    "provider": provider,
                    "reason_code": "provider_not_whitelisted",
                })
                continue
            try:
                result = provider_keys_store.save_key(provider, str(key))
                provider_results.append(result)
            except ValueError as exc:
                provider_errors.append({
                    "provider": provider,
                    "reason_code": "validation_failed",
                    "detail": str(exc),
                })
            except Exception as exc:
                logger.exception("provider_keys save failed: provider=%s", provider)
                provider_errors.append({
                    "provider": provider,
                    "reason_code": "io_error",
                    "detail": str(exc),
                })

    # ── 沒有任何寫入動作 ─────────────────────────────────────────────
    if not updates and not provider_keys:
        return _layer2_response(
            {"message": "No updates provided"},
            action_result="blocked",
            reason_codes=["empty_update"],
        )

    # ── tracker 配置 ────────────────────────────────────────────────
    config_dict: dict[str, Any] | None = None
    if updates:
        config = tracker.update_config(updates)
        config_dict = config.to_dict()

    # ── 回傳 envelope（含 provider 結果）──────────────────────────
    payload: dict[str, Any] = {
        "message": "Configuration updated",
        "config": config_dict,
    }
    if provider_keys is not None:
        payload["provider_results"] = provider_results
        payload["provider_errors"] = provider_errors
        payload["provider_status"] = provider_keys_store.status()

    if provider_errors:
        # 部分成功也標 partial：前端據此提示
        return _layer2_response(
            payload,
            action_result="partial" if provider_results or updates else "blocked",
            reason_codes=[err["reason_code"] for err in provider_errors],
        )
    return _layer2_response(payload)


# ═══════════════════════════════════════════════════════════════════════════════
# Provider Key Management / 供應商密鑰管理
# ═══════════════════════════════════════════════════════════════════════════════

@layer2_router.get("/providers/status")
async def get_providers_status(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """
    回 GUI Tab-AI 用的供應商狀態快照。
    永不回明文 key（只回 masked + configured + client_implemented）。
    """
    return _layer2_response(provider_keys_store.status())


@layer2_router.get("/providers/models")
async def get_providers_models(
    force_refresh: bool = Query(default=False),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """
    回 GUI Engine Settings 用的 provider model catalog。
    只打 models/list 類只讀 endpoint；結果做 TTL cache，force_refresh=true 可手動刷新。
    """
    return _layer2_response(provider_model_catalog.get_model_catalog(force_refresh=force_refresh))


@layer2_router.delete("/providers/{provider}")
async def delete_provider_key(
    provider: str,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """
    刪除某 provider 的 API key（檔案 + env），需 Operator 角色。
    """
    base.require_operator_role(actor)
    if provider not in provider_keys_store.ALLOWED_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail={"reason_codes": ["provider_not_whitelisted"], "provider": provider},
        )
    try:
        result = provider_keys_store.delete_key(provider)
    except Exception as exc:
        logger.exception("provider_keys delete failed: provider=%s", provider)
        raise HTTPException(
            status_code=500,
            detail={"reason_codes": ["io_error"], "detail": str(exc)},
        )
    return _layer2_response({
        **result,
        "provider_status": provider_keys_store.status(),
    })
