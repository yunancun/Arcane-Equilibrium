"""AI Budget routes — thin async proxy to Rust IPC (ARCH-RC1 standard).
AI Budget 路由 — Rust IPC 的薄 async 代理（ARCH-RC1 標準路徑）。

MODULE_NOTE (EN):
    GET  /api/v1/ai_budget/status  -> awaits engine.get_ai_budget_status()
    POST /api/v1/ai_budget/config  -> awaits engine.update_ai_budget_config(scope, monthly_usd, updated_by)

    Zero local state. The route handler awaits the IPC call and only returns
    200 after Rust confirms. On Rust error/timeout, returns 503/504.

    THIS MODULE IS THE REFERENCE IMPLEMENTATION FOR WP-ARCH-RC1 (RC1-2):
    - async + await IPC + return 200 only on Rust ack
    - No file write, no Python cache, no fallback to disk

MODULE_NOTE (中):
    GET  /api/v1/ai_budget/status  -> 等待 engine.get_ai_budget_status()
    POST /api/v1/ai_budget/config  -> 等待 engine.update_ai_budget_config(...)

    零本地狀態。Route handler await IPC 完成後才回 200。
    Rust 錯誤/超時 → 503/504。

    本模組是 WP-ARCH-RC1（RC1-2）的參考實作：
    - async + await IPC + Rust 確認後才回 200
    - 不寫檔、不快取、不退化到 disk
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Router prefix follows the project's /api/v1 convention.
# 路由前綴遵循項目 /api/v1 約定。
router = APIRouter(prefix="/api/v1/ai_budget", tags=["ai_budget"])


# ─── Pydantic schemas / 響應與請求模型 ──────────────────────────────────────

class BudgetStatusResponse(BaseModel):
    """AI budget status snapshot returned to GUI.
    回傳給 GUI 的 AI 預算狀態快照。
    """
    ok: bool
    config: dict[str, float] | None = None      # scope → monthly_usd
    usage_mtd: dict[str, float] | None = None   # scope → USD spent MTD
    remaining: dict[str, float] | None = None   # scope → USD remaining
    degrade_level: str | None = None            # "none" | "soft_warn" | "hard_limit" | "killswitch"
    last_refresh_ms: int | None = None
    error: str | None = None


class BudgetConfigUpdate(BaseModel):
    """Single-scope budget update payload.
    單一 scope 預算更新請求。
    """
    scope: str = Field(..., min_length=1)
    monthly_usd: float = Field(..., ge=0.0)
    updated_by: str = Field(default="operator")


# ─── IPC client accessor / IPC 客戶端取得 ───────────────────────────────────

async def _get_ipc_client() -> Any:
    """Resolve the singleton EngineIPCClient instance.
    取得 EngineIPCClient 單例。

    Lazy import to avoid hard coupling in test environments where the IPC
    socket may not exist. Tests monkey-patch this function to inject a mock.
    延遲匯入以避免測試環境硬耦合；測試會透過 monkey-patch 注入 mock。
    """
    from .ipc_client import EngineIPCClient  # type: ignore  # noqa: PLC0415

    factory = getattr(EngineIPCClient, "get_singleton", None)
    if factory is None:
        # No singleton helper available — caller will treat this as IPC error.
        # 沒有 singleton helper — 呼叫端視為 IPC 錯誤。
        raise RuntimeError("EngineIPCClient.get_singleton not available")
    return factory()


# ─── Payload normalization / payload 標準化 ─────────────────────────────────

def _normalize_status_payload(raw: dict[str, Any]) -> BudgetStatusResponse:
    """Coerce a raw Rust BudgetTracker status_json into BudgetStatusResponse.
    將 Rust BudgetTracker 的 status_json 原樣轉成 BudgetStatusResponse。

    The Rust side may report ``{"status": "uninitialized", "reason": ...}`` when
    the DB pool is unavailable at boot — surface that as ok=False with the
    reason text in ``error`` so the GUI can show a clear degraded message.
    Rust 側若 DB 池未就緒會回 ``{"status": "uninitialized", "reason": ...}``，
    此時轉為 ok=False 並把 reason 放到 error，GUI 可顯示降級狀態。
    """
    if not isinstance(raw, dict):
        return BudgetStatusResponse(ok=False, error="bad_payload_shape")

    status = raw.get("status")
    if status == "uninitialized":
        return BudgetStatusResponse(
            ok=False,
            error=f"uninitialized: {raw.get('reason', 'unknown')}",
        )

    def _coerce_scope_dict(value: Any) -> dict[str, float] | None:
        if not isinstance(value, dict):
            return None
        out: dict[str, float] = {}
        for k, v in value.items():
            try:
                out[str(k)] = float(v)
            except (TypeError, ValueError):
                continue
        return out

    config = _coerce_scope_dict(raw.get("config") or raw.get("limits"))
    usage_mtd = _coerce_scope_dict(raw.get("usage_mtd") or raw.get("mtd_usage"))
    remaining = _coerce_scope_dict(raw.get("remaining"))

    degrade_level = raw.get("degrade_level")
    if not isinstance(degrade_level, str):
        degrade_level = None

    last_refresh_ms = raw.get("last_refresh_ms")
    if not isinstance(last_refresh_ms, (int, float)):
        last_refresh_ms = None
    else:
        last_refresh_ms = int(last_refresh_ms)

    return BudgetStatusResponse(
        ok=True,
        config=config,
        usage_mtd=usage_mtd,
        remaining=remaining,
        degrade_level=degrade_level,
        last_refresh_ms=last_refresh_ms,
    )


# ─── GET /status ────────────────────────────────────────────────────────────

@router.get("/status", response_model=BudgetStatusResponse)
async def get_ai_budget_status_route() -> BudgetStatusResponse:
    """Read current AI budget status from Rust engine via IPC.
    透過 IPC 從 Rust 引擎讀取當前 AI 預算狀態。

    Always returns 200 — IPC failures are surfaced as ok=False so the GUI's
    30s polling loop can render a degraded banner without retrying via 5xx.
    永遠回 200 — IPC 失敗時以 ok=False 表示，GUI 30 秒輪詢可顯示降級訊息
    而不會被 5xx 觸發重試。
    """
    try:
        client = await _get_ipc_client()
        raw = await client.get_ai_budget_status()
    except Exception as exc:  # noqa: BLE001 — fail-soft for GUI polling
        logger.warning("ai_budget: get_ai_budget_status failed: %s", exc)
        return BudgetStatusResponse(
            ok=False,
            error=f"ipc_error:{type(exc).__name__}",
        )

    return _normalize_status_payload(raw if isinstance(raw, dict) else {})


# ─── POST /config ───────────────────────────────────────────────────────────

@router.post("/config")
async def update_ai_budget_config_route(payload: BudgetConfigUpdate) -> dict[str, Any]:
    """Update a single AI budget scope. await IPC, return 200 only on Rust ack.
    更新單一 AI 預算 scope；await IPC 並僅在 Rust 確認後回 200。

    This is the WP-ARCH-RC1 (RC1-2) reference path:
      - validates payload via Pydantic (Field constraints)
      - awaits IPC call (no fire-and-forget)
      - returns 503 if engine unreachable, 504 on timeout, 400 on Rust reject
      - never writes to disk, never caches state in Python
    本路徑為 WP-ARCH-RC1 (RC1-2) 標準實作：Pydantic 驗證 → await IPC →
    僅在 Rust ack 後回 200，503/504/400 對應不同錯誤；不寫檔、不快取。
    """
    try:
        client = await _get_ipc_client()
    except Exception as exc:  # noqa: BLE001
        logger.error("ai_budget: ipc client unavailable: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"engine unreachable: {type(exc).__name__}",
        ) from exc

    # Lazy import error types so test envs without ipc_client can still import.
    # 延遲匯入錯誤類型，方便不裝 IPC 的測試環境。
    try:
        from .ipc_client import (  # noqa: PLC0415
            EngineDisconnectedError,
            EngineTimeoutError,
        )
    except Exception:  # pragma: no cover
        EngineDisconnectedError = ConnectionError  # type: ignore[assignment]
        EngineTimeoutError = TimeoutError  # type: ignore[assignment]

    try:
        result = await client.update_ai_budget_config(
            scope=payload.scope,
            monthly_usd=payload.monthly_usd,
            updated_by=payload.updated_by,
        )
    except EngineTimeoutError as exc:
        logger.warning("ai_budget: ipc timeout: %s", exc)
        raise HTTPException(status_code=504, detail="engine timeout") from exc
    except EngineDisconnectedError as exc:
        logger.warning("ai_budget: ipc disconnected: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"engine unreachable: {exc}",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("ai_budget: ipc call failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"engine error: {type(exc).__name__}: {exc}",
        ) from exc

    # Rust may return a structured error in result dict — surface as 400.
    # Rust 可能在 result 中回結構化錯誤 — 轉成 400。
    if isinstance(result, dict) and result.get("error"):
        raise HTTPException(status_code=400, detail=str(result["error"]))

    return {
        "ok": True,
        "scope": payload.scope,
        "monthly_usd": payload.monthly_usd,
        "updated_at_ms": int(time.time() * 1000),
        "engine_result": result if isinstance(result, dict) else None,
    }
