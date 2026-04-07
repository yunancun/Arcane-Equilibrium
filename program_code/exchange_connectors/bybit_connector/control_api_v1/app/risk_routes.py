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
    max_total_exposure_pct: float | None = Field(default=None, gt=0, le=100)
    max_correlated_exposure_pct: float | None = Field(default=None, gt=0, le=100)
    max_leverage: float | None = Field(default=None, gt=0, le=200)
    max_session_drawdown_pct: float | None = Field(default=None, gt=0, le=100)
    max_daily_loss_pct: float | None = Field(default=None, gt=0, le=100)
    consecutive_loss_cooldown_count: int | None = Field(default=None, gt=0, le=100)
    consecutive_loss_cooldown_minutes: float | None = Field(default=None, gt=0, le=1440)
    max_holding_hours: float | None = Field(default=None, gt=0, le=8760)
    max_cost_edge_ratio: float | None = Field(default=None, gt=0, le=10)
    allowed_categories: list[str] | None = None
    preferred_margin_mode: str | None = None
    preferred_position_mode: str | None = None
    p1_risk_pct: float | None = Field(default=None, gt=0, le=20)
    trailing_stop_pct: float | None = Field(default=None, ge=0, le=50)
    atr_multiplier: float | None = Field(default=None, ge=0, le=10)
    max_same_direction_positions: int | None = Field(default=None, gt=0, le=25)
    h0_shadow_mode: bool | None = None


class CategoryConfigUpdate(BaseModel):
    enabled: bool | None = None
    max_leverage: float | None = Field(default=None, gt=0, le=200)
    max_single_position_pct: float | None = Field(default=None, gt=0, le=100)
    max_total_exposure_pct: float | None = Field(default=None, gt=0, le=100)
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
    client = await _get_risk_view_client()
    config = await client.refresh_config()
    # Optional: append Rust state-reader snapshot for legacy GUI fields
    # 可選：附加 Rust state-reader 快照供舊 GUI 欄位使用
    reader = get_rust_reader()
    snap = reader.get_snapshot() if reader.is_available() else None
    if snap is not None:
        config = dict(config)  # don't mutate cache
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
    # 附加 state-reader 欄位給 dashboard 用
    reader = get_rust_reader()
    snap = reader.get_snapshot() if reader.is_available() else None
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
    """Risk context for AI decision-making — Rust snapshot only, no RiskViewClient touch."""
    reader = get_rust_reader()
    snap = reader.get_snapshot() if reader.is_available() else None
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


@risk_router.post("/unhalt-session")
async def unhalt_session(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Manually clear Rust session_halted + paper_paused via resume_paper IPC.

    DEPRECATED PAPER_STORE write below: 1C-3-D will remove the Python-side
    PAPER_STORE.session_halted parallel write once all readers have migrated
    to derive from the Rust snapshot.
    DEPRECATED PAPER_STORE 寫入：1C-3-D 移除 Python 側並行寫入。
    """
    client = await _get_risk_view_client()
    try:
        await client.unhalt_session()
    except Exception as e:
        raise _ipc_failure(f"resume_paper: {e}") from e

    # 1C-3-C transitional: keep PAPER_STORE.mutate so other readers (paper_state
    # GUI tile, snapshot writer) don't see stale halted=True until 1C-3-D wires
    # them to the Rust snapshot. Marked DEPRECATED, removal in 1C-3-D.
    # 1C-3-C 過渡：保留 PAPER_STORE.mutate 直到 1C-3-D 把其他 reader 接到 Rust snapshot。
    try:
        from .paper_trading_routes import PAPER_STORE  # type: ignore

        def _mutator(state: dict) -> dict:
            state["session"]["session_halted"] = False
            state["session"]["session_halt_reason"] = None
            return state

        PAPER_STORE.mutate(_mutator)
    except Exception as e:
        logger.warning("PAPER_STORE.mutate (deprecated) failed: %s", e)

    return _risk_response({"message": "session_unhalted"})
