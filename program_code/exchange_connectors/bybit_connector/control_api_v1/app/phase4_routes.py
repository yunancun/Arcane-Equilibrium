"""
Phase 4 Dashboard Routes — skeleton (4-00).
Phase 4 儀表板路由 — 骨架（4-00）。

MODULE_NOTE (中文):
  本模組為 Phase 4 儀表板提供骨架路由：
  1. GET /api/v1/phase4/status — 返回四個模組（Teacher/LinUCB/News/DL-3）的紅黃綠燈狀態
  2. GET /api/v1/phase4 — 渲染靜態 tab-phase4.html（重定向至 /static/tab-phase4.html）

  狀態源：先嘗試 IPC `get_phase4_status`，失敗時 fail-closed 回 grey + degraded。
  後續 4-01 ... 4-21 會將 stub grey 替換為各模組真實聚合（Teacher 回放/LinUCB regret/
  News severity/DL-3 health）。

MODULE_NOTE (English):
  Skeleton routes for the Phase 4 dashboard:
  1. GET /api/v1/phase4/status — returns traffic-light state for 4 modules
     (Teacher / LinUCB / News / DL-3).
  2. GET /api/v1/phase4 — redirects to the static tab-phase4.html.

  Status source: tries IPC `get_phase4_status`; on failure fail-closed to grey
  with degraded=true. Sub-tasks 4-01 ... 4-21 will replace the grey stub with
  the real per-module aggregations.

Safety:
  - Read-only — no trading state mutation. / 純讀取，不改交易狀態。
  - Fail-closed — IPC down → grey, never silent green. / IPC 斷線時退回 grey，
    永不靜默回 green。
  - No hard-coded paths — see CLAUDE.md §七 cross-platform rule.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

logger = logging.getLogger(__name__)

# Router prefix follows the project's /api/v1 convention.
# 路由前綴遵循項目 /api/v1 約定。
phase4_router = APIRouter(prefix="/api/v1/phase4", tags=["phase4"])


# Allowed traffic-light vocabulary / 合法紅黃綠燈詞彙
_VALID_LIGHTS = {"grey", "green", "yellow", "red"}

# Phase 4 module keys (must stay in sync with Rust handle_get_phase4_status).
# Phase 4 模組鍵（必須與 Rust handle_get_phase4_status 保持同步）。
_MODULE_KEYS = ("teacher", "linucb", "news", "dl3")


def _grey_payload(degraded: bool, reason: str | None = None) -> dict[str, Any]:
    """
    Build a grey-only payload (used as fail-closed default).
    構造全 grey 的 payload（fail-closed 預設）。
    """
    payload: dict[str, Any] = {key: "grey" for key in _MODULE_KEYS}
    payload["last_update_ms"] = int(time.time() * 1000)
    payload["degraded"] = degraded
    if reason is not None:
        payload["reason"] = reason
    return payload


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Validate and normalize a phase4 status payload.
    Unknown / invalid status values are coerced to "grey" (fail-closed).
    校驗並標準化 phase4 狀態 payload。未知或非法狀態值強制降為 "grey"（fail-closed）。
    """
    out: dict[str, Any] = {}
    for key in _MODULE_KEYS:
        v = payload.get(key)
        out[key] = v if isinstance(v, str) and v in _VALID_LIGHTS else "grey"
    last_ms = payload.get("last_update_ms")
    out["last_update_ms"] = (
        int(last_ms) if isinstance(last_ms, (int, float)) and last_ms > 0
        else int(time.time() * 1000)
    )
    out["degraded"] = False
    return out


async def _query_engine_status() -> dict[str, Any]:
    """
    Query the Rust engine via IPC for the latest phase4 aggregation.
    Falls back to grey on any failure (no exception raised to caller).
    通過 IPC 向 Rust 引擎查詢最新的 phase4 聚合，任何失敗均退回 grey
    （不向呼叫者拋例外）。
    """
    try:
        # Lazy import to avoid hard coupling in test environments.
        # 延遲匯入以避免在測試環境硬耦合。
        from .ipc_client import EngineIPCClient  # type: ignore
    except Exception as exc:  # pragma: no cover - import-time guard
        logger.warning("phase4: IPC client import failed: %s", exc)
        return _grey_payload(degraded=True, reason="ipc_client_import_failed")

    client_factory = getattr(EngineIPCClient, "get_singleton", None)
    if client_factory is None:
        # No singleton helper — best effort: return grey.
        # 沒有 singleton helper — 盡力而為：返回 grey。
        return _grey_payload(degraded=True, reason="no_singleton")

    try:
        client = client_factory()
        raw = await client.get_phase4_status()
        if not isinstance(raw, dict):
            return _grey_payload(degraded=True, reason="bad_payload_shape")
        return _sanitize(raw)
    except Exception as exc:
        logger.warning("phase4: IPC get_phase4_status failed: %s", exc)
        return _grey_payload(degraded=True, reason=f"ipc_error:{type(exc).__name__}")


@phase4_router.get("/status")
async def get_phase4_status() -> dict[str, Any]:
    """
    Phase 4 dashboard status aggregation endpoint.
    Phase 4 儀表板狀態聚合端點。

    Returns a flat dict:
        {
          "teacher":  "grey" | "green" | "yellow" | "red",
          "linucb":   "grey" | ...,
          "news":     "grey" | ...,
          "dl3":      "grey" | ...,
          "last_update_ms": <unix-millis>,
          "degraded": <bool>,
          "reason":   <optional str>
        }

    Until 4-01 ... 4-21 are implemented, every module is reported as "grey"
    (not started). The frontend should render grey lights as neutral.
    在 4-01 ... 4-21 實作之前，所有模組均回報為 "grey"（未啟動）。前端應將
    grey 燈渲染為中性灰色。
    """
    return await _query_engine_status()


@phase4_router.get("", include_in_schema=False)
async def phase4_tab_redirect() -> RedirectResponse:
    """
    Convenience route — redirect /api/v1/phase4 to the static tab.
    便利路由 — 將 /api/v1/phase4 重定向至靜態 tab 頁面。
    """
    return RedirectResponse(url="/static/tab-phase4.html")
