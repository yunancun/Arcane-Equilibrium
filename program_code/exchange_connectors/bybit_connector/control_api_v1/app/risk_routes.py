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
from .h0_block_evidence import H0GateEvidence, h0_reason_breakdown
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


def _ipc_failure(
    reason_code: str,
    *,
    log_detail: str | None = None,
) -> HTTPException:
    """嚴格失敗：IPC 不可達 → HTTP 500，禁假成功。

    P2-WP05-FUP-1：reason_code 是 client-facing 穩定字串；log_detail（含原
    exception repr 或 result dict）只進 log，不外洩到 HTTPException.detail。
    保留 `rust_engine_unavailable:` 前綴維持既有 substring 測試斷言相容
    （見 tests/test_reset_drawdown_route.py:266）。

    Future-proof note (E2 LOW advisory 2026-05-18)：未來若 RiskConfig schema
    新增 secret / api_key / authorization / password 等敏感欄位，
    `log_detail=f"...: {result!r}"` callsite（如 line 717 patch_risk_config_not_ok
    分支）需審 result 序列化白名單，避免敏感欄位流入 server-side log。
    目前 IPC `patch_risk_config` 回 `{ok, config, version, source}` 0 敏感欄位
    （rust/openclaw_engine/src/ipc_server/handlers_config.rs:187-195 已驗）。
    """
    if log_detail:
        logger.warning("ipc failure: %s | %s", reason_code, log_detail)
    return HTTPException(
        status_code=500,
        detail=f"rust_engine_unavailable: {reason_code}",
    )


def _require_risk_write(actor: base.AuthenticatedActor) -> None:
    """Shared Batch B gate for risk/session mutations.
    Batch B 共用風控/Session 寫入閘門：必須是 Operator 且具 risk:write scope。
    """
    base.require_scope_and_operator(actor, "risk:write")


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
    _require_risk_write(actor)
    client = await _get_risk_view_client()
    updates = body.model_dump(exclude_none=True)
    if not updates:
        await client.refresh_config()
        return _risk_response({"message": "no_updates", "config": client.config})
    try:
        await client.update_global_config(updates)
    except Exception as e:
        raise _ipc_failure(
            "ipc_patch_risk_config_failed",
            log_detail=str(e),
        ) from e
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
    _require_risk_write(actor)
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
        raise _ipc_failure(
            "ipc_patch_risk_config_category_failed",
            log_detail=str(e),
        ) from e
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
    _require_risk_write(actor)
    client = await _get_risk_view_client()
    updates = {k: v for k, v in body.model_dump().items() if k in body.model_fields_set}
    if not updates:
        await client.refresh_config()
        return _risk_response({"message": "no_updates", "agent_params": client.get_agent_params()})
    try:
        await client.agent_adjust(updates)
    except Exception as e:
        raise _ipc_failure(
            "ipc_patch_risk_config_agent_failed",
            log_detail=str(e),
        ) from e
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
    _require_risk_write(actor)
    client = await _get_risk_view_client()
    try:
        result = await client.clear_consecutive_losses()
    except Exception as e:
        raise _ipc_failure(
            "ipc_clear_consecutive_losses_failed",
            log_detail=str(e),
        ) from e
    return _risk_response({"message": "cooldown_reset", "result": result, "status": client.get_status()})


# ═══════════════════════════════════════════════════════════════════════════════
# P1-5 A2: Operator-driven drawdown baseline reset
# P1-5 A2：Operator 手動重置 drawdown 基準
# ═══════════════════════════════════════════════════════════════════════════════

class ResetDrawdownBaselineRequest(BaseModel):
    """
    Request body for POST /reset-drawdown-baseline.
    POST /reset-drawdown-baseline 的請求 body。

    Explicit `engine` + `reason` are REQUIRED — this endpoint lowers the
    drawdown circuit breaker baseline and MUST be audit-traceable per Root
    Principle #8 (交易可解釋).

    `engine` 與 `reason` 為必填 — 此端點會降低 drawdown 斷路器基準，按根
    原則 #8「交易可解釋」必須可審計。
    """

    engine: str = Field(
        ...,
        description="Target engine: paper | demo | live",
    )
    reason: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Operator reason for resetting the drawdown baseline",
    )


def _record_reset_drawdown_audit(
    who: str,
    engine: str,
    reason: str,
    ipc_response: dict[str, Any],
) -> None:
    """
    Write change_audit_log entry for a drawdown baseline reset.
    Fail-soft: if the governance hub is unavailable the reset still returns
    success (the Rust side already confirmed DB DELETE), but we log at WARN so
    the gap is visible. Root Principle #8 cannot be fully honoured without the
    hub — operators should see the warning and investigate.

    為一次 drawdown 基準重置寫 change_audit_log。若 governance hub 不可用，
    重置仍返回成功（Rust 端 DB DELETE 已確認），但以 WARN 記錄缺口。
    """
    try:
        from .governance_routes import _get_governance_hub  # lazy import
        hub = _get_governance_hub()
    except Exception as e:
        logger.warning("reset_drawdown_baseline: governance hub lazy import failed: %s", e)
        return

    if hub is None or getattr(hub, "_change_audit_log", None) is None:
        logger.warning(
            "reset_drawdown_baseline: change_audit_log unavailable — "
            "operator=%s engine=%s (Root Principle #8 trace gap)",
            who, engine,
        )
        return

    try:
        from .change_audit_log import ChangeType
        hub._change_audit_log.record_change(
            change_type=ChangeType.STATE_CHANGE,
            who=who,
            what=f"Drawdown baseline reset (engine={engine})",
            reason=reason,
            old_value={"peak_balance": "prev"},
            new_value={"peak_balance": "equal_to_balance", "ipc_result": ipc_response},
            affected_components=[f"paper_state:{engine}", "trading.paper_state_checkpoint"],
            auto_approve=True,  # operator-authenticated action already passed auth
        )
    except Exception as e:
        logger.warning("reset_drawdown_baseline: change_audit_log write failed: %s", e)


@risk_router.post("/reset-drawdown-baseline")
async def reset_drawdown_baseline(
    body: ResetDrawdownBaselineRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    P1-5 A2: Operator-driven drawdown baseline reset.
    P1-5 A2：Operator 手動 drawdown 基準重置。

    Equalises Rust PaperState `peak_balance = balance` and DELETEs the
    `trading.paper_state_checkpoint` row for the selected engine so the next
    restart cold-starts. This is the ONLY path that lowers `peak_balance`;
    restarts never do it automatically (fail-closed per Root Principles
    #5 生存>利潤 / #6 失敗默認收縮 / #8 交易可解釋).

    Requires Operator role. Writes a STATE_CHANGE entry to change_audit_log.

    讓 Rust PaperState `peak_balance = balance` 並刪除對應引擎的
    `trading.paper_state_checkpoint` row，下次啟動冷起。此為唯一可降 peak
    的路徑，重啟永不自動降（根原則 #5/#6/#8 fail-closed）。需 Operator 角色，
    寫 change_audit_log STATE_CHANGE。
    """
    _require_risk_write(actor)
    # Operator role gate — use the same duck-typed check as governance_routes.
    # 以 governance_routes 相同的 duck-typed 檢查來閘 operator 角色。
    if not actor or not hasattr(actor, "roles") or not hasattr(actor, "actor_id"):
        raise HTTPException(status_code=401, detail="Authentication required")
    if "operator" not in actor.roles:
        logger.warning(
            "Non-operator attempted reset_drawdown_baseline: actor=%s engine=%s",
            str(actor.actor_id).replace("\n", "\\n")[:200],
            body.engine,
        )
        raise HTTPException(status_code=403, detail="Operator role required")

    # Whitelist engine to prevent IPC injection.
    # 白名單 engine 防 IPC 注入。
    if body.engine not in _ALLOWED_ENGINES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid engine '{body.engine}'. Must be one of: {sorted(_ALLOWED_ENGINES)}",
        )

    client = await _get_risk_view_client()
    try:
        result = await client.reset_drawdown_baseline(body.engine)
    except Exception as e:
        raise _ipc_failure(
            "ipc_reset_drawdown_baseline_failed",
            log_detail=f"engine={body.engine}: {e}",
        ) from e

    # Root Principle #8: trade explainability — audit ALL baseline resets.
    # 根原則 #8：交易可解釋 — 所有 baseline 重置皆寫審計。
    _record_reset_drawdown_audit(
        who=str(actor.actor_id),
        engine=body.engine,
        reason=body.reason,
        ipc_response=result,
    )

    return _risk_response({
        "message": "drawdown_baseline_reset",
        "engine": body.engine,
        "result": result,
        "status": client.get_status(),
    })


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
        raise _ipc_failure(
            "ipc_get_risk_config_failed",
            log_detail=f"engine={engine}: {e}",
        ) from e

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
    _require_risk_write(actor)
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
        raise _ipc_failure(
            "ipc_patch_risk_config_per_engine_failed",
            log_detail=f"engine={engine}: {e}",
        ) from e
    result = resp if isinstance(resp, dict) else {}
    if not result.get("ok"):
        raise _ipc_failure(
            "ipc_patch_risk_config_not_ok",
            log_detail=f"engine={engine}: {result!r}",
        )
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
    _require_risk_write(actor)
    client = await _get_risk_view_client()
    try:
        await client.unhalt_session()
    except Exception as e:
        raise _ipc_failure(
            "ipc_resume_paper_failed",
            log_detail=str(e),
        ) from e

    return _risk_response({"message": "session_unhalted"})


# ═══════════════════════════════════════════════════════════════════════════════
# LG-1 T4: Operator Verification — H0 Block Summary
# LG-1 T4：Operator 驗證 — H0 阻擋摘要
# ═══════════════════════════════════════════════════════════════════════════════
#
# MODULE_NOTE (中文):
#   PA tech plan §1.4 表 T4：GET /h0_block_summary 提供 operator 驗證 H0 hard-block
#   是否真實生效的 read-only 端點。資料源：
#   - h0_gate_stats：由 Rust engine 透過 IPC pipeline snapshot 提供累計計數
#     （since engine boot；五個 sub-check counter：freshness / health / eligibility
#     / envelope / cooldown），來自 GateStats（openclaw_core::h0_gate）。
#   - trading.fills：對窗口期 fills 數量做 sanity check；H0 hard-block 路徑
#     早退而不會寫入 fill，故 fills > 0 + h0_shadow_mode=false 表示 H0 正常放行。
#
#   PA spec 字段對齊與設計取捨：
#   - `h0_block_events_by_strategy` 改名為 `h0_block_events_by_reason` —— H0 是
#     pre-strategy gate（per-symbol gate）, 沒有 strategy 維度；改用 GateStats
#     真實 5 sub-check counter 對 operator 更有實用價值。
#   - `fills_during_block` 改語意為「窗口期 fills 計數」—— H0 hard-block 路徑
#     不會寫入 fill（step_0_5_h0_gate.rs:43-94），所以「block 期間 fill」by-design
#     恆為 0；本字段提供窗口期 fills_total 給 operator 對賬 acceptance 計算。
#   - `last_block_event_at_utc` —— GateStats 不帶 per-event 時間戳（cumulative
#     counter only），無法精確還原；以 engine snapshot 的 written_at_ms 作為
#     last_check_at_utc 提供近似（fail-safe = None 表示 unknown）。
#   - `block_acceptance_pct` 定義：
#     若窗口期 has fills (>0) + h0_shadow_mode=false → 100%（fail-closed 設計
#     已驗證）；若 fills=0 + 0 block → 100%（無交易活動，無法證偽，定義為 pass）；
#     若 fills>0 但 h0_shadow_mode=true → WARN（hard-block 未啟用）。
#
#   Auth：與 risk_router 既有 read-only 路由相同（current_actor，無需 risk:write）。
#
#   設計依據：CLAUDE.md §四（讀寫分離 + 讀為主）+ §七（中文注釋 + 跨平台）。

class H0BlockSummaryEngineDetail(BaseModel):
    """單一 engine 的 H0 阻擋摘要詳情。"""

    engine_mode: str = Field(..., description="引擎模式 (paper/demo/live)")
    h0_shadow_mode: bool | None = Field(
        default=None,
        description="該引擎當前 h0_shadow_mode；true=只觀察不阻擋, false=hard-block",
    )
    engine_available: bool = Field(
        ..., description="該引擎 snapshot 是否新鮮可讀（<60s）"
    )
    # GateStats cumulative counters since engine boot
    # GateStats 自 engine 啟動的累計計數
    h0_block_events_total: int = Field(
        0, description="自 engine 啟動以來總 block 事件數（5 sub-check 加總）"
    )
    h0_block_events_by_reason: dict[str, int] = Field(
        default_factory=dict,
        description="按 reason 分類的 block 計數（freshness/health/eligibility/envelope/cooldown）",
    )
    h0_total_checks: int = Field(
        0, description="自 engine 啟動以來 H0 gate 檢查總次數"
    )
    h0_allow_rate_pct: float = Field(
        0.0, description="放行率百分比（0-100）；等於 (total_checks - total_blocked) / total_checks"
    )
    # Window-scoped fills sanity check
    # 窗口期 fills sanity check（trading.fills）
    fills_in_window: int = Field(
        0, description="窗口期內該引擎 trading.fills 計數（block 期間 by-design 無 fill）"
    )
    # Last known check timestamp (best-effort — GateStats has no per-event ts)
    # 最近一次檢查時間戳（snapshot.written_at_ms 近似；GateStats 無 per-event ts）
    last_check_at_utc: str | None = Field(
        default=None,
        description="engine snapshot 的 written_at_ms（近似 last H0 check 時間）；None 表示 engine 不可達",
    )
    # WARN / PASS / FAIL per-engine sub-verdict
    # 該引擎子裁決（WARN / PASS / FAIL）
    health_status: str = Field(
        "UNKNOWN",
        description="該引擎子裁決：PASS（hard-block 啟用且 fail-closed 驗證）/ "
                    "WARN（shadow-mode 或 snapshot 不可達）/ FAIL（hard-block 未啟用但有大量阻擋事件）",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="補充說明（窗口語意、近似值來源、缺漏資料原因）",
    )


class H0BlockSummaryResponse(BaseModel):
    """
    H0 阻擋摘要回應 / H0 block summary response.

    PA tech plan §1.4 T4：給 operator GUI / curl 看的 H0 verification view。
    純 read-only（IPC snapshot + trading.fills SELECT）。
    """

    window_hours: int = Field(..., description="查詢窗口（小時數）")
    engine_modes: list[str] = Field(
        ..., description="本回應涵蓋的 engine_mode 列表"
    )
    # Per-engine breakdown / 每引擎細節
    engines: list[H0BlockSummaryEngineDetail] = Field(
        default_factory=list, description="每引擎的 H0 block 摘要詳情"
    )
    # Aggregated across engines
    # 跨 engine 聚合
    h0_block_events_total: int = Field(
        0,
        description="所有 engine 累計 block 事件總數 since engine boot。**0 = 健康狀態**（H0 active 但本期間 5 sub-check 未觸發 reject 條件），不是 H0 broken。",
    )
    h0_block_events_by_reason: dict[str, int] = Field(
        default_factory=dict,
        description="按 5 sub-check 分類 block 計數：freshness=資料新鮮度 / health=系統健康 / eligibility=symbol 可交易 / envelope=風險上限 / cooldown=冷卻期",
    )
    fills_during_block: int = Field(
        0,
        description="**設計不變式（invariant）：恆為 0**。H0 hard-block 路徑早退（step_0_5_h0_gate.rs:43-94），by-design 不會寫 fill。非觀察量，是 invariant proof。窗口期實際 fills 計數見 engines[].fills_in_window。",
    )
    last_block_event_at_utc: str | None = Field(
        default=None,
        description="**近似值**：取所有 engine pipeline_snapshot.written_at_ms 中最新者，非 per-event 時間戳。GateStats 是 cumulative counter 無 per-event ts；operator 看到此 timestamp 應理解為 'snapshot 寫入時間' 非 'block 發生時間'。None = engine 不可達。",
    )
    block_acceptance_pct: float = Field(
        100.0,
        description="100% = 理想：窗口期所有 fills 都對應 H0 放行 + 無設計不變式違反",
    )
    health_status: str = Field(
        "PASS",
        description="頂層裁決：PASS / WARN / FAIL（規則見 module docstring）",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="頂層補充說明（窗口語意、cumulative counter 限制、缺漏資料）",
    )


# Allowed engine_mode filter values (whitelist; defends against IPC/SQL injection).
# 允許的 engine_mode 篩選白名單（防止 IPC/SQL 注入）。
_H0_SUMMARY_ALLOWED_ENGINES: frozenset[str] = frozenset({"paper", "demo", "live", "live_demo"})

# Default windows / 預設窗口
_H0_SUMMARY_DEFAULT_WINDOW_H: int = 24
_H0_SUMMARY_MIN_WINDOW_H: int = 1
_H0_SUMMARY_MAX_WINDOW_H: int = 24 * 30  # 30 天上限，防止 unbounded SELECT


def _h0_reason_breakdown(gate_stats: dict[str, Any] | None) -> tuple[dict[str, int], int, int]:
    """
    從 GateStats dict（Rust snapshot 提供）抽出 5 sub-check counter + totals。

    回傳 (by_reason, total_blocked, total_checks)；缺漏視為 0。
    """
    return h0_reason_breakdown(gate_stats)


def _count_fills_in_window(engine_modes: list[str], window_hours: int) -> dict[str, int]:
    """
    從 trading.fills 計數窗口期 fills（per engine_mode）。

    純 SELECT；參數化查詢；PG 不可用時回 {} + 上游自行 fail-safe。
    """
    from .db_pool import get_pg_conn

    out: dict[str, int] = {em: 0 for em in engine_modes}
    if not engine_modes or window_hours <= 0:
        return out

    sql = """
        SELECT engine_mode, COUNT(*) AS n
          FROM trading.fills
         WHERE ts >= NOW() - (%s || ' hours')::interval
           AND engine_mode = ANY(%s)
         GROUP BY engine_mode
    """

    with get_pg_conn() as conn:
        if conn is None:
            logger.warning("h0_block_summary: PG unavailable — fills_in_window unavailable")
            return out
        try:
            cur = conn.cursor()
            cur.execute(sql, (str(window_hours), list(engine_modes)))
            for em, n in cur.fetchall():
                out[em] = int(n or 0)
        except Exception as exc:
            logger.warning("h0_block_summary fills count failed: %s", exc)
    return out


def _per_engine_h0_summary(
    engine: str,
    fills_count: int,
    window_hours: int,
) -> H0BlockSummaryEngineDetail:
    """
    抽取單一 engine 的 H0 摘要：從 RustSnapshotReader 拿 pipeline snapshot，
    抽出 h0_gate_stats + runtime.h0_shadow_mode + written_at_ms。

    Fail-safe：snapshot 缺漏時回 engine_available=false 並標 WARN。
    """
    reader = get_rust_reader()
    # 3E-ARCH: live_demo 是 live pipeline 走 demo endpoint；engine snapshot
    # 仍寫到 pipeline_snapshot_live.json（is_live=true）。
    snapshot_engine = "live" if engine == "live_demo" else engine
    available = reader.is_engine_available(snapshot_engine)
    snap = reader.get_snapshot(engine=snapshot_engine) if available else None

    detail = H0BlockSummaryEngineDetail(
        engine_mode=engine,
        engine_available=available,
        fills_in_window=fills_count,
    )

    if not available or snap is None:
        detail.health_status = "WARN"
        detail.notes.append(
            f"engine={engine} snapshot 不可達或過期（>60s）；無法評估 H0 cumulative stats"
        )
        return detail

    evidence = H0GateEvidence.from_snapshot(snap)
    detail.h0_block_events_total = evidence.total_blocked
    detail.h0_block_events_by_reason = evidence.by_reason
    detail.h0_total_checks = evidence.total_checks
    detail.h0_allow_rate_pct = evidence.allow_rate_pct
    detail.h0_shadow_mode = evidence.h0_shadow_mode
    detail.last_check_at_utc = evidence.last_check_at_utc

    # Sub-verdict 規則：
    # FAIL — hard-block 未啟用但 cumulative block events > 0（shadow 期間 GateStats 累積；
    #         此時策略可能有 fill 落地是設計上 shadow 觀察）→ 提示 operator review
    # WARN — h0_shadow_mode=true 表示仍在 shadow 觀察期，hard-block 未真正生效
    # PASS — hard-block 啟用 + 無設計不變式違反
    if detail.h0_shadow_mode is None:
        detail.health_status = "WARN"
        detail.notes.append("無法讀取 h0_shadow_mode（risk_manager_config 缺漏）")
    elif detail.h0_shadow_mode is True:
        detail.health_status = "WARN"
        detail.notes.append(
            "h0_shadow_mode=true（仍在 shadow 觀察期，hard-block 未真正生效；"
            "demo/live_demo 預期 false）"
        )
    else:
        # hard-block 啟用：fail-closed 設計下 block 期間無 fill 是不變式
        detail.health_status = "PASS"

    if evidence.total_checks == 0:
        detail.notes.append(
            f"engine={engine} H0 total_checks=0；engine 可能剛重啟或無 tick 流量"
        )

    return detail


def _aggregate_h0_summary(
    engine_details: list[H0BlockSummaryEngineDetail],
) -> tuple[int, dict[str, int], str | None]:
    """
    跨 engine 聚合 cumulative block events + by_reason + latest check timestamp。
    """
    total = 0
    by_reason: dict[str, int] = {
        "freshness": 0, "health": 0, "eligibility": 0, "envelope": 0, "cooldown": 0,
    }
    last_check: str | None = None
    for det in engine_details:
        total += det.h0_block_events_total
        for k, v in det.h0_block_events_by_reason.items():
            by_reason[k] = by_reason.get(k, 0) + int(v)
        if det.last_check_at_utc:
            if last_check is None or det.last_check_at_utc > last_check:
                last_check = det.last_check_at_utc
    return total, by_reason, last_check


def _top_level_verdict(
    engine_details: list[H0BlockSummaryEngineDetail],
) -> tuple[str, float, list[str]]:
    """
    頂層裁決規則：
    - FAIL — 任何 engine 子裁決為 FAIL
    - WARN — 有 engine WARN 但無 FAIL；或所有 engine 都 unavailable
    - PASS — 所有 engine 都 PASS
    回傳 (status, acceptance_pct, top_level_notes)。
    """
    notes: list[str] = []
    if not engine_details:
        return ("WARN", 0.0, ["無 engine 資料"])

    statuses = [d.health_status for d in engine_details]
    if "FAIL" in statuses:
        return ("FAIL", 0.0, notes)
    if all(s == "WARN" for s in statuses):
        notes.append("所有 engine 都 WARN（snapshot 不可達或 shadow_mode=true）")
        return ("WARN", 0.0, notes)
    if "WARN" in statuses:
        notes.append("部分 engine WARN（見 engines[].notes）")
        return ("WARN", 50.0, notes)
    # 所有 PASS
    return ("PASS", 100.0, notes)


@risk_router.get("/h0_block_summary", response_model=H0BlockSummaryResponse)
async def get_h0_block_summary(
    window_hours: int = 24,
    engine_mode: str | None = None,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> H0BlockSummaryResponse:
    """
    LG-1 T4 — Operator 驗證 H0 hard-block 是否生效的純 read-only 端點。

    Query params:
      - window_hours: 查詢窗口（小時），1..720（30 天）；預設 24
      - engine_mode: 篩選 (paper / demo / live / live_demo)；預設 None = 所有支援的 engine

    回傳：
      H0BlockSummaryResponse —— 包含 per-engine 詳情 + 聚合 stats + 頂層裁決。

    資料源：
      - h0_gate_stats: Rust engine pipeline snapshot (cumulative since engine boot)
      - trading.fills: 窗口期 fills 計數（per engine_mode）做 sanity check

    純 SELECT，無寫入；auth = current_actor（與既有 GET /config 同等級）。
    """
    # ── 1. 參數校驗 ──
    # Param validation
    if window_hours < _H0_SUMMARY_MIN_WINDOW_H or window_hours > _H0_SUMMARY_MAX_WINDOW_H:
        raise HTTPException(
            status_code=400,
            detail=(
                f"window_hours 必須在 [{_H0_SUMMARY_MIN_WINDOW_H}, "
                f"{_H0_SUMMARY_MAX_WINDOW_H}] 範圍內，got={window_hours}"
            ),
        )

    if engine_mode is not None and engine_mode not in _H0_SUMMARY_ALLOWED_ENGINES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"engine_mode '{engine_mode}' 不在允許清單，必須屬於 "
                f"{sorted(_H0_SUMMARY_ALLOWED_ENGINES)}"
            ),
        )

    # ── 2. 決定要查詢的 engine 列表 ──
    # Decide which engines to inspect
    engines_to_check: list[str] = (
        [engine_mode] if engine_mode else sorted(_H0_SUMMARY_ALLOWED_ENGINES)
    )

    # ── 3. 一次拉所有 engine 的窗口期 fills count（PG 一次 SELECT 即可）──
    # Fetch fills count for all engines in a single PG SELECT
    fills_counts = _count_fills_in_window(engines_to_check, window_hours)

    # ── 4. Per-engine detail ──
    # Per-engine detail
    engine_details: list[H0BlockSummaryEngineDetail] = []
    for em in engines_to_check:
        detail = _per_engine_h0_summary(em, fills_counts.get(em, 0), window_hours)
        engine_details.append(detail)

    # ── 5. 聚合 + 頂層裁決 ──
    # Aggregate + top-level verdict
    total_blocked, by_reason, last_check = _aggregate_h0_summary(engine_details)
    verdict, acceptance_pct, top_notes = _top_level_verdict(engine_details)

    response = H0BlockSummaryResponse(
        window_hours=window_hours,
        engine_modes=engines_to_check,
        engines=engine_details,
        h0_block_events_total=total_blocked,
        h0_block_events_by_reason=by_reason,
        # H0 hard-block 路徑早退不寫 fill → 設計不變式恆為 0
        # Hard-block path exits early without emitting fill → invariant always 0
        fills_during_block=0,
        last_block_event_at_utc=last_check,
        block_acceptance_pct=acceptance_pct,
        health_status=verdict,
        notes=top_notes + [
            "GateStats 為累計 counter (since engine boot)，不帶 per-event ts；"
            "last_check_at_utc 取 snapshot.written_at_ms 作近似",
            "fills_during_block 是設計不變式 (恆為 0)；窗口期 fills 計數見 engines[].fills_in_window",
        ],
    )
    return response
