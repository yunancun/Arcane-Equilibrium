from __future__ import annotations

"""
Paper Trading Risk Control Routes / 紙上交易風控路由
ARCH-RC1 1C-3-C: All routes now use `RiskViewClient` (thin IPC view of Rust
authoritative RiskConfig). Python `RiskManager` is no longer touched here —
its remaining importers are migrated in 1C-3-D.

8 routes under /api/v1/paper/risk:
  GET  /config                    — full RiskConfig snapshot
  POST /config/global             — patch_risk_config (operator source)
  GET  /config/category/{c}       — derived per-category view
  POST /config/category/{c}       — patch_risk_config nested override
  GET  /status                    — Rust-native runtime status (governor_tier etc.)
  GET  /ai-context                — Rust snapshot (no risk_manager touch)
  POST /agent-adjust              — patch_risk_config (agent source)
  POST /reset-cooldown            — clear_consecutive_losses IPC
  POST /unhalt-session            — resume_paper IPC

MODULE_NOTE (中文):
  ARCH-RC1 1C-3-C：所有 route 改用 RiskViewClient（Rust 權威 RiskConfig 的薄 IPC 視圖）。
  Python RiskManager 在本檔內不再被引用，剩餘 importer 由 1C-3-D 處理。
  寫入路徑：route → RiskViewClient → patch_risk_config IPC → Rust ConfigStore.replace()
  → 5 engines hot-reload + V014 audit row。
  Strict failure mode：IPC unreachable → HTTP 500（不再 best-effort）。
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import main_legacy as base
from .ipc_client import EngineIPCClient
from .ipc_state_reader import get_rust_reader
from .risk_view_client import RiskViewClient

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# Router / 路由器
# ═══════════════════════════════════════════════════════════════════════════════

risk_router = APIRouter(
    prefix="/api/v1/paper/risk",
    tags=["Paper Risk Control / 紙上風險控制"],
)


# ─── Module-level RiskViewClient singleton (lazy-initialised) ─────────────────
# 模組級 RiskViewClient 單例（懶初始化）
_RISK_VIEW_CLIENT: RiskViewClient | None = None
_IPC_CLIENT: EngineIPCClient | None = None


async def _get_risk_view_client() -> RiskViewClient:
    """
    Lazy-init RiskViewClient + underlying EngineIPCClient on first call.
    The IPC client is reused across requests (it has its own lock + reconnect).
    第一次呼叫時建立 RiskViewClient + EngineIPCClient；後續 request 重用同一 instance。
    """
    global _RISK_VIEW_CLIENT, _IPC_CLIENT
    if _RISK_VIEW_CLIENT is None:
        _IPC_CLIENT = EngineIPCClient()
        try:
            await _IPC_CLIENT.connect()
        except Exception as e:
            logger.warning("RiskViewClient IPC connect failed: %s", e)
        _RISK_VIEW_CLIENT = RiskViewClient(_IPC_CLIENT)
    return _RISK_VIEW_CLIENT


def _risk_response(data: Any) -> dict[str, Any]:
    return {
        "ok": True,
        "data": data,
        "is_simulated": True,
        "data_category": "paper_risk_control",
    }


def _ipc_failure(detail: str) -> HTTPException:
    """Strict failure: IPC unreachable → HTTP 500. No more best-effort silent skip."""
    return HTTPException(status_code=500, detail=f"rust_engine_unavailable: {detail}")


# ═══════════════════════════════════════════════════════════════════════════════
# Request Models / 請求模型 (unchanged from pre-1C-3-C)
# ═══════════════════════════════════════════════════════════════════════════════

class GlobalConfigUpdate(BaseModel):
    max_stop_loss_pct: float | None = Field(default=None, gt=0, le=100)
    max_take_profit_pct: float | None = Field(default=None, gt=0, le=100)
    tp_enabled: bool | None = None
    max_single_position_pct: float | None = Field(default=None, gt=0, le=100)
    max_total_exposure_pct: float | None = Field(default=None, gt=0, le=500)
    max_correlated_exposure_pct: float | None = Field(default=None, gt=0, le=200)
    max_leverage: float | None = Field(default=None, gt=0, le=200)
    max_session_drawdown_pct: float | None = Field(default=None, gt=0, le=100)
    max_daily_loss_pct: float | None = Field(default=None, gt=0, le=100)
    consecutive_loss_cooldown_count: int | None = Field(default=None, gt=0, le=100)
    consecutive_loss_cooldown_minutes: int | None = Field(default=None, gt=0, le=1440)
    max_holding_hours: float | None = Field(default=None, gt=0, le=8760)
    max_cost_edge_ratio: float | None = Field(default=None, gt=0, le=10)
    allowed_categories: list[str] | None = None
    preferred_margin_mode: str | None = None
    preferred_position_mode: str | None = None
    p1_risk_pct: float | None = Field(default=None, gt=0, le=100)
    trailing_stop_pct: float | None = Field(default=None, ge=0, le=50)
    atr_multiplier: float | None = Field(default=None, ge=0, le=10)
    max_same_direction_positions: int | None = Field(default=None, gt=0, le=25)
    h0_shadow_mode: bool | None = None


class CategoryConfigUpdate(BaseModel):
    enabled: bool | None = None
    max_leverage: float | None = Field(default=None, gt=0, le=200)
    max_single_position_pct: float | None = Field(default=None, gt=0, le=100)
    max_total_exposure_pct: float | None = Field(default=None, gt=0, le=500)
    max_stop_loss_pct: float | None = Field(default=None, gt=0, le=100)
    max_holding_hours: float | None = Field(default=None, gt=0, le=8760)
    allowed_symbols: list[str] | None = None
    spot_allow_margin: bool | None = None
    perp_max_funding_rate_abs: float | None = Field(default=None, gt=0)
    option_max_premium_pct: float | None = Field(default=None, gt=0, le=100)
    option_max_delta_exposure: float | None = Field(default=None, gt=0)
    option_allowed_strategies: list[str] | None = None


class AgentAdjustRequest(BaseModel):
    effective_stop_loss_pct: float | None = None
    effective_take_profit_pct: float | None = None
    trailing_stop_enabled: bool | None = None
    trailing_stop_activation_pct: float | None = Field(default=None, gt=0)
    trailing_stop_distance_pct: float | None = Field(default=None, gt=0)
    position_size_multiplier: float | None = Field(default=None, ge=0.1, le=1.0)
    category_preference_weights: dict[str, float] | None = None
    prefer_limit_over_market: bool | None = None
    use_reduce_only_for_close: bool | None = None
    use_post_only_for_limit: bool | None = None


# ═══════════════════════════════════════════════════════════════════════════════
# Routes / 路由
# ═══════════════════════════════════════════════════════════════════════════════

@risk_router.get("/config")
async def get_risk_config(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get full RiskConfig snapshot from Rust authority. / 從 Rust 權威獲取完整 RiskConfig 快照。"""
    from .risk_view_client import _GLOBAL_TO_RUST
    client = await _get_risk_view_client()
    raw = await client.refresh_config()
    config = dict(raw)  # don't mutate cache

    # Build GUI-compatible flat global_config from Rust nested structure.
    # GUI reads cfg.global_config (or cfg.p1) expecting flat field names.
    # / 從 Rust 嵌套結構建立 GUI 兼容的平坦 global_config。
    limits   = raw.get("limits", {})
    agent    = raw.get("agent", {})
    dstop    = raw.get("dynamic_stop", {})
    aclust   = raw.get("anti_cluster", {})
    runtime  = raw.get("runtime", {})
    global_config: dict[str, Any] = {
        "max_stop_loss_pct":            limits.get("stop_loss_max_pct"),
        "max_take_profit_pct":          limits.get("take_profit_max_pct"),
        "tp_enabled":                   limits.get("take_profit_enforced"),
        "max_single_position_pct":      limits.get("position_size_max_pct"),
        "max_total_exposure_pct":       limits.get("total_exposure_max_pct"),
        "max_correlated_exposure_pct":  limits.get("correlated_exposure_max_pct"),
        "max_leverage":                 limits.get("leverage_max"),
        "max_session_drawdown_pct":     limits.get("session_drawdown_max_pct"),
        "max_daily_loss_pct":           limits.get("daily_loss_max_pct"),
        "consecutive_loss_cooldown_count":   limits.get("consec_loss_cooldown_count"),
        "consecutive_loss_cooldown_minutes": limits.get("consec_loss_cooldown_min"),
        "max_holding_hours":            limits.get("holding_hours_max"),
        # Rust stores per_trade_risk_pct as fraction (0.03); expose as percent (3.0).
        # Rust 用小數存（0.03），GUI 顯示百分比（3.0）。
        "p1_risk_pct": (
            limits.get("per_trade_risk_pct") * 100.0
            if isinstance(limits.get("per_trade_risk_pct"), (int, float))
            else None
        ),
        "allowed_categories":           limits.get("allowed_categories"),
        "preferred_margin_mode":        limits.get("margin_mode"),
        "preferred_position_mode":      limits.get("position_mode"),
        "max_same_direction_positions": aclust.get("max_same_direction"),
        "trailing_stop_pct":            agent.get("trailing_distance_pct"),
        "atr_multiplier":               dstop.get("atr_stop_mult"),
        "h0_shadow_mode":               runtime.get("h0_shadow_mode"),
    }
    config["global_config"] = global_config
    config["p1"] = global_config  # alias used by some GUI paths

    # Optional: append Rust state-reader snapshot for legacy GUI fields
    # 3E-ARCH: read paper engine snapshot — risk dashboard tracks paper-engine
    # drawdown / balance / gate stats. Without engine="paper" the compat file is
    # written by whichever engine has is_primary=true (Live > Demo > Paper).
    # 可選：附加 Rust state-reader 快照供舊 GUI 欄位使用。
    # 3E-ARCH：必須讀 paper 引擎快照（風控儀表板追蹤 paper 引擎指標）。
    reader = get_rust_reader()
    snap = reader.get_snapshot(engine="paper") if reader.is_engine_available("paper") else None
    if snap is not None:
        config["rust_active"] = {
            "stop_config": snap.get("stop_config"),
            "guardian_config": snap.get("guardian_config"),
            "risk_manager_config": snap.get("risk_manager_config"),
            "source": "rust_engine",
        }
    return _risk_response({"config": config, "version": client.config_version})


@risk_router.post("/config/global")
async def update_global_config(
    body: GlobalConfigUpdate,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Patch P1 global RiskConfig via Rust ConfigStore (operator source).
    Hot-reloads to 5 downstream engines + writes V014 audit row.
    透過 Rust ConfigStore 修改 P1 全局風控（operator 來源）。
    成功後熱更新 5 個下游引擎並寫入 V014 audit。
    """
    client = await _get_risk_view_client()
    updates = body.model_dump(exclude_none=True)
    if not updates:
        await client.refresh_config()
        return _risk_response({"message": "no_updates", "config": client.config})
    try:
        await client.update_global_config(updates)
    except Exception as e:
        raise _ipc_failure(f"patch_risk_config: {e}") from e
    return _risk_response({"message": "updated", "config": client.config, "version": client.config_version})


@risk_router.get("/config/category/{category}")
async def get_category_config(
    category: str,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get P0 category-override config from cached Rust snapshot."""
    client = await _get_risk_view_client()
    await client.refresh_config()
    cfg = client.get_category_config(category)
    if not cfg:
        return _risk_response({"category": category, "config": None, "message": "using_global_defaults"})
    return _risk_response({"category": category, "config": cfg})


@risk_router.post("/config/category/{category}")
async def update_category_config(
    category: str,
    body: CategoryConfigUpdate,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Patch P0 category override via Rust ConfigStore (operator source, nested patch)."""
    client = await _get_risk_view_client()
    updates = body.model_dump(exclude_none=True)
    if not updates:
        await client.refresh_config()
        return _risk_response({
            "message": "no_updates",
            "config": client.get_category_config(category),
        })
    try:
        await client.update_category_config(category, updates)
    except Exception as e:
        raise _ipc_failure(f"patch_risk_config category: {e}") from e
    return _risk_response({
        "message": "updated",
        "category": category,
        "config": client.get_category_config(category),
    })


@risk_router.get("/status")
async def get_risk_status(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Rust-native runtime status (governor_tier / consecutive_losses_by_symbol /
    boot_cooldown_remaining_ms / paper_paused / session_halted).

    ★ Schema deliberately differs from the Python-era `rm.get_status()`. GUI
    Risk tab is rebound in tab-risk.html within the same commit.
    ★ Schema 與 Python 時代 rm.get_status() 刻意不同。GUI Risk tab 同 commit 改綁定。
    """
    client = await _get_risk_view_client()
    runtime = await client.refresh_runtime_status()
    # Append optional state-reader fields for richer dashboard
    # 3E-ARCH: explicit engine="paper" for paper-engine drawdown / balance fields.
    # 附加 state-reader 欄位給 dashboard 用。3E-ARCH：明確指定 paper 引擎。
    reader = get_rust_reader()
    snap = reader.get_snapshot(engine="paper") if reader.is_engine_available("paper") else None
    if snap is not None:
        ps = snap.get("paper_state", {}) or {}
        runtime = dict(runtime)
        runtime["session_drawdown_pct"] = round(snap.get("session_drawdown_pct", 0.0), 2)
        runtime["daily_loss_pct"] = round(snap.get("daily_loss_pct", 0.0), 2)
        runtime["peak_balance_usdt"] = ps.get("peak_balance", 0)
        runtime["current_balance_usdt"] = ps.get("balance", 0)
        runtime["h0_gate_stats"] = snap.get("h0_gate_stats")
        runtime["source"] = "rust_engine"
    return _risk_response(runtime)


@risk_router.get("/ai-context")
async def get_ai_risk_context(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Risk context for AI decision-making — Rust snapshot only, no RiskViewClient touch.
    3E-ARCH: read paper engine snapshot. / 3E-ARCH：讀 paper 引擎快照。
    """
    reader = get_rust_reader()
    snap = reader.get_snapshot(engine="paper") if reader.is_engine_available("paper") else None
    if snap is not None:
        dd = snap.get("session_drawdown_pct", 0.0)
        dl = snap.get("daily_loss_pct", 0.0)
        halted = snap.get("session_halted", False)
        pressure = min(1.0, max(dd, dl) / 10.0)
        suggestion = "halt" if halted else ("reduce" if pressure > 0.5 else "normal")
        ctx = {
            "risk_pressure": round(pressure, 3),
            "suggestion": suggestion,
            "session_drawdown_pct": round(dd, 2),
            "daily_loss_pct": round(dl, 2),
            "session_halted": halted,
            "consecutive_losses": snap.get("consecutive_losses", {}),
            "source": "rust_engine",
        }
    else:
        ctx = {"risk_pressure": 0.0, "suggestion": "normal", "error": "rust_engine_unavailable"}
    return _risk_response(ctx)


@risk_router.post("/agent-adjust")
async def agent_adjust(
    body: AgentAdjustRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Agent self-tuning — patch_risk_config with source=agent for V014 audit."""
    client = await _get_risk_view_client()
    updates = {k: v for k, v in body.model_dump().items() if k in body.model_fields_set}
    if not updates:
        await client.refresh_config()
        return _risk_response({"message": "no_updates", "agent_params": client.get_agent_params()})
    try:
        await client.agent_adjust(updates)
    except Exception as e:
        raise _ipc_failure(f"patch_risk_config agent: {e}") from e
    return _risk_response({
        "message": "adjusted",
        "agent_params": client.get_agent_params(),
        "version": client.config_version,
    })


@risk_router.post("/reset-cooldown")
async def reset_cooldown(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Clear per-symbol consecutive-loss counters via Rust IPC.
    Note: post-RRC-1 there is NO Python cooldown counter — this only clears
    the Rust per-symbol map (governor tier untouched, see 1C-3-B-2).
    透過 Rust IPC 清除 per-symbol 連虧計數器（governor tier 不變）。
    """
    client = await _get_risk_view_client()
    try:
        result = await client.clear_consecutive_losses()
    except Exception as e:
        raise _ipc_failure(f"clear_consecutive_losses: {e}") from e
    return _risk_response({"message": "cooldown_reset", "result": result, "status": client.get_status()})


# ═══════════════════════════════════════════════════════════════════════════════
# LIVE-P2-1/P2-2: Per-engine RiskConfig endpoints
# LIVE-P2-1/P2-2：每引擎 RiskConfig 端點
# ═══════════════════════════════════════════════════════════════════════════════

# Allowed engine names (whitelist prevents IPC injection via path param).
# 允許的引擎名稱白名單（防止 path param 注入到 IPC）。
_ALLOWED_ENGINES: frozenset[str] = frozenset({"paper", "demo", "live"})


async def _get_direct_ipc() -> EngineIPCClient:
    """
    Return a direct EngineIPCClient for per-engine IPC calls (bypasses RiskViewClient
    so version tracking doesn't bleed across engines).
    為每引擎 IPC 調用返回直接 EngineIPCClient（繞過 RiskViewClient 避免跨引擎版本追蹤）。
    """
    # Reuse the module-level IPC client if it was already initialized, otherwise
    # create a fresh one.  Lazy init mirrors _get_risk_view_client() pattern.
    # 如果模組級 IPC 客戶端已初始化則複用，否則創建新實例。
    global _IPC_CLIENT
    if _IPC_CLIENT is None:
        _IPC_CLIENT = EngineIPCClient()
        try:
            await _IPC_CLIENT.connect()
        except Exception as e:
            logger.warning("Per-engine IPC connect failed: %s", e)
    return _IPC_CLIENT


def _build_global_patch(updates: dict[str, Any]) -> dict[str, Any]:
    """
    Remap flat GUI field names → Rust RiskConfig nested patch dict.
    Reuses the same _GLOBAL_TO_RUST mapping as RiskViewClient.
    將 GUI 平坦欄位映射到 Rust RiskConfig 嵌套 patch dict（複用 RiskViewClient 映射）。
    """
    from .risk_view_client import _GLOBAL_TO_RUST
    patch: dict[str, Any] = {}
    for gui_key, value in updates.items():
        if gui_key not in _GLOBAL_TO_RUST:
            continue
        section, rust_key = _GLOBAL_TO_RUST[gui_key]
        # Special: p1_risk_pct is sent as percent (3.0) but Rust stores as fraction (0.03).
        # p1_risk_pct 以百分比傳入（3.0），Rust 以小數存（0.03）。
        if gui_key == "p1_risk_pct" and isinstance(value, (int, float)):
            value = value / 100.0
        if section not in patch:
            patch[section] = {}
        patch[section][rust_key] = value
    return patch


@risk_router.get("/config/engine/{engine}")
async def get_per_engine_risk_config(
    engine: str,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    GET /api/v1/paper/risk/config/engine/{engine}
    Returns full RiskConfig snapshot for the specified engine (paper|demo|live).
    Calls IPC get_risk_config with engine routing param (LIVE-P2-1).

    返回指定引擎（paper|demo|live）的完整 RiskConfig 快照。
    透過 IPC get_risk_config 的 engine 路由參數讀取對應 store（LIVE-P2-1）。
    """
    if engine not in _ALLOWED_ENGINES:
        raise HTTPException(status_code=400, detail=f"Invalid engine '{engine}'. Must be one of: {sorted(_ALLOWED_ENGINES)}")
    ipc = await _get_direct_ipc()
    try:
        resp = await ipc.call("get_risk_config", params={"engine": engine})
    except Exception as e:
        raise _ipc_failure(f"get_risk_config engine={engine}: {e}") from e

    raw = resp if isinstance(resp, dict) else {}
    config = raw.get("config", raw)
    version = raw.get("version", 0)

    # Build the same GUI-compatible flat global_config shape as GET /config.
    # 建立與 GET /config 相同的 GUI 兼容 global_config 形狀。
    limits  = config.get("limits", {}) if isinstance(config, dict) else {}
    agent   = config.get("agent", {}) if isinstance(config, dict) else {}
    dstop   = config.get("dynamic_stop", {}) if isinstance(config, dict) else {}
    aclust  = config.get("anti_cluster", {}) if isinstance(config, dict) else {}
    runtime = config.get("runtime", {}) if isinstance(config, dict) else {}
    global_config: dict[str, Any] = {
        "max_stop_loss_pct":            limits.get("stop_loss_max_pct"),
        "max_take_profit_pct":          limits.get("take_profit_max_pct"),
        "tp_enabled":                   limits.get("take_profit_enforced"),
        "max_single_position_pct":      limits.get("position_size_max_pct"),
        "max_total_exposure_pct":       limits.get("total_exposure_max_pct"),
        "max_correlated_exposure_pct":  limits.get("correlated_exposure_max_pct"),
        "max_leverage":                 limits.get("leverage_max"),
        "max_session_drawdown_pct":     limits.get("session_drawdown_max_pct"),
        "max_daily_loss_pct":           limits.get("daily_loss_max_pct"),
        "consecutive_loss_cooldown_count":   limits.get("consec_loss_cooldown_count"),
        "consecutive_loss_cooldown_minutes": limits.get("consec_loss_cooldown_min"),
        "max_holding_hours":            limits.get("holding_hours_max"),
        "p1_risk_pct": (
            limits.get("per_trade_risk_pct") * 100.0
            if isinstance(limits.get("per_trade_risk_pct"), (int, float))
            else None
        ),
        "allowed_categories":           limits.get("allowed_categories"),
        "preferred_margin_mode":        limits.get("margin_mode"),
        "preferred_position_mode":      limits.get("position_mode"),
        "max_same_direction_positions": aclust.get("max_same_direction"),
        "trailing_stop_pct":            agent.get("trailing_distance_pct"),
        "atr_multiplier":               dstop.get("atr_stop_mult"),
        "h0_shadow_mode":               runtime.get("h0_shadow_mode"),
    }
    config_out = dict(config) if isinstance(config, dict) else {}
    config_out["global_config"] = global_config
    config_out["p1"] = global_config
    return _risk_response({"engine": engine, "config": config_out, "version": version})


@risk_router.post("/config/engine/{engine}/global")
async def update_per_engine_global_config(
    engine: str,
    body: GlobalConfigUpdate,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    POST /api/v1/paper/risk/config/engine/{engine}/global
    Patch RiskConfig for the specified engine (paper|demo|live) via IPC.
    Operator role required. Live engine: extra care — changes affect real money.

    透過 IPC patch_risk_config 修改指定引擎（paper|demo|live）的 RiskConfig。
    需要 Operator 角色。Live 引擎：更新影響真實資金，需謹慎。
    """
    if engine not in _ALLOWED_ENGINES:
        raise HTTPException(status_code=400, detail=f"Invalid engine '{engine}'. Must be one of: {sorted(_ALLOWED_ENGINES)}")
    ipc = await _get_direct_ipc()
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return _risk_response({"engine": engine, "message": "no_updates"})
    patch = _build_global_patch(updates)
    if not patch:
        return _risk_response({"engine": engine, "message": "no_mappable_fields"})
    try:
        resp = await ipc.call(
            "patch_risk_config",
            params={"engine": engine, "patch": patch, "source": "operator"},
        )
    except Exception as e:
        raise _ipc_failure(f"patch_risk_config engine={engine}: {e}") from e
    result = resp if isinstance(resp, dict) else {}
    if not result.get("ok"):
        raise _ipc_failure(f"patch_risk_config engine={engine} returned not-ok: {result}")
    return _risk_response({
        "engine": engine,
        "message": "updated",
        "version": result.get("version"),
        "source": result.get("source"),
    })


@risk_router.post("/unhalt-session")
async def unhalt_session(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Manually clear Rust session_halted + paper_paused via resume_paper IPC.

    ARCH-RC1 1C-3-E F-mini: dropped the deprecated PAPER_STORE.mutate parallel
    write. Rust ConfigStore + paper_state are now the sole authority for
    session_halted; downstream readers consume the Rust snapshot.
    1C-3-E F-mini：移除已棄用的 Python 並行寫入路徑，session_halted 由 Rust 權威。
    """
    client = await _get_risk_view_client()
    try:
        await client.unhalt_session()
    except Exception as e:
        raise _ipc_failure(f"resume_paper: {e}") from e

    return _risk_response({"message": "session_unhalted"})
