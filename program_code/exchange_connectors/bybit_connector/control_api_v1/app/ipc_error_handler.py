"""IPC error classification — unified Python → Rust call-site error policy.
IPC 錯誤分類 — 統一 Python→Rust 調用點錯誤策略。

MODULE_NOTE (EN):
    This helper centralises how route handlers map IPC exceptions (from
    ``EngineIPCClient``) onto ``fastapi.HTTPException`` status codes.  The
    mapping mirrors the policy previously duplicated inside
    ``ai_budget_routes.update_ai_budget_config_route``:

        EngineTimeoutError      → 504 engine timeout
        EngineDisconnectedError → 503 engine unreachable
        any other Exception     → 503 engine error (wrapped type name)

    Keep behaviour byte-for-byte identical to the current ai_budget_routes
    site: status codes, detail strings, and ``from exc`` chaining are all
    preserved.  New adopters should simply wrap their IPC call in
    ``raise_http_for_ipc_error`` or use the ``ipc_error_boundary`` context.

    Lazy-imports the exception types so this module can be imported in test
    environments where ``ipc_client`` is absent; falls back to built-in
    ``ConnectionError``/``TimeoutError`` — same fallback as ai_budget_routes.

MODULE_NOTE (中):
    本模組集中管理路由處理器將 IPC 例外（來自 ``EngineIPCClient``）映射到
    ``fastapi.HTTPException`` 狀態碼的策略。映射方式鏡像原本散在
    ``ai_budget_routes.update_ai_budget_config_route`` 的重複實作：

        EngineTimeoutError      → 504 engine timeout
        EngineDisconnectedError → 503 engine unreachable
        其他 Exception          → 503 engine error（包含類型名稱）

    保持與 ai_budget_routes 現場行為 byte-for-byte 一致：狀態碼、detail
    字串、``from exc`` 鏈都保留。新採用點只需 ``raise_http_for_ipc_error``
    或使用 ``ipc_error_boundary`` 上下文管理器。

    例外類型採延遲匯入，測試環境無 ``ipc_client`` 時退回到 built-in
    ``ConnectionError`` / ``TimeoutError`` — 與 ai_budget_routes 的 fallback
    相同。

Safety guarantees / 安全保證:
  - Fail-closed: never swallows IPC errors — always re-raises as HTTPException.
  - Byte-for-byte compatibility: messages identical to legacy hand-written sites.
  - Cross-platform: no filesystem or socket access, pure error classification.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, NoReturn

from fastapi import HTTPException

logger = logging.getLogger(__name__)


# ─── Lazy exception import / 延遲匯入例外類型 ───────────────────────────────

def _load_engine_exception_types() -> tuple[type[BaseException], type[BaseException]]:
    """Return ``(EngineDisconnectedError, EngineTimeoutError)`` with fallbacks.
    回傳 IPC 斷線/超時例外類型；若 ``ipc_client`` 不存在則 fallback。

    This mirrors the lazy-import block in ``ai_budget_routes.py`` so we keep
    identical fallback semantics for test environments that monkey-patch IPC.
    鏡像 ai_budget_routes.py 的懶匯入區塊，與測試 monkey-patch 保持一致。
    """
    try:
        from .ipc_client import (  # noqa: PLC0415
            EngineDisconnectedError,
            EngineTimeoutError,
        )
        return EngineDisconnectedError, EngineTimeoutError
    except Exception:  # pragma: no cover — only exercised without ipc_client
        return ConnectionError, TimeoutError  # type: ignore[return-value]


# ─── Public API / 公開 API ──────────────────────────────────────────────────

def raise_http_for_ipc_error(
    exc: BaseException,
    *,
    context: str = "ipc",
    log: logging.Logger | None = None,
) -> NoReturn:
    """Translate an IPC exception into the canonical ``HTTPException``.
    將 IPC 例外轉換為標準的 ``HTTPException``。

    :param exc:     caught exception from an ``await client.call(...)``.
                    從 ``await client.call(...)`` 捕獲的例外。
    :param context: short tag used in log messages (e.g. ``"ai_budget"``).
                    記錄日誌時使用的短標籤。
    :param log:     optional caller logger; falls back to module logger.
                    可選呼叫方 logger；預設使用模組 logger。

    Mapping (identical to ai_budget_routes legacy):
      - ``EngineTimeoutError``      → ``HTTPException(504, "engine timeout")``
      - ``EngineDisconnectedError`` → ``HTTPException(503, f"engine unreachable: {exc}")``
      - any other ``Exception``     → ``HTTPException(503, f"engine error: {type(exc).__name__}: {exc}")``
    映射規則（與 ai_budget_routes 舊路徑完全一致）。

    Always raises; declared ``NoReturn`` so type-checkers track control flow.
    一律拋出；宣告為 ``NoReturn`` 讓型別檢查器追蹤控制流。
    """
    _log = log or logger
    disconnected_cls, timeout_cls = _load_engine_exception_types()

    # Order matters: TimeoutError is more specific than Exception but the two
    # engine types are siblings — use isinstance so custom subclasses flow too.
    # 順序重要：Timeout 比 Exception 具體；用 isinstance 讓子類也能命中。
    if isinstance(exc, timeout_cls):
        _log.warning("%s: ipc timeout: %s", context, exc)
        raise HTTPException(status_code=504, detail="engine timeout") from exc
    if isinstance(exc, disconnected_cls):
        _log.warning("%s: ipc disconnected: %s", context, exc)
        raise HTTPException(
            status_code=503,
            detail=f"engine unreachable: {exc}",
        ) from exc

    _log.error("%s: ipc call failed: %s", context, exc)
    raise HTTPException(
        status_code=503,
        detail=f"engine error: {type(exc).__name__}: {exc}",
    ) from exc


@asynccontextmanager
async def ipc_error_boundary(
    *,
    context: str = "ipc",
    log: logging.Logger | None = None,
) -> AsyncIterator[None]:
    """Async context manager that funnels IPC errors through the mapping above.
    異步上下文管理器，將 IPC 錯誤導向上述映射策略。

    Usage / 用法::

        async with ipc_error_boundary(context="ai_budget"):
            result = await client.update_ai_budget_config(...)

    ``HTTPException`` raised by the caller (e.g. 400 for a Rust-reported
    structured error) passes through unchanged. All other exceptions are
    mapped via :func:`raise_http_for_ipc_error`.
    呼叫方主動拋出的 ``HTTPException``（例如 400，對應 Rust 結構化錯誤）
    原樣通過；其他例外一律透過 :func:`raise_http_for_ipc_error` 映射。
    """
    try:
        yield
    except HTTPException:
        # Caller-produced HTTP errors pass through unchanged / 原樣放行
        raise
    except Exception as exc:  # noqa: BLE001 — we reclassify below
        raise_http_for_ipc_error(exc, context=context, log=log)


def classify_ipc_exception(exc: BaseException) -> dict[str, Any]:
    """Return a structured classification dict without raising.
    不拋出例外，回傳結構化分類字典。

    Useful for fail-soft paths (e.g. GUI polling endpoints) that prefer to
    surface ``ok=False`` with an ``error`` string instead of a 5xx response.
    適用於 fail-soft 路徑（例如 GUI 輪詢端點），以 ``ok=False`` 搭配
    ``error`` 字串的方式回傳，避免觸發 5xx 重試。

    Returns::

        {"kind": "timeout" | "disconnected" | "other",
         "http_status": 504 | 503,
         "detail":   <human-readable string>,
         "error_tag": "ipc_error:<ExceptionClassName>"}
    """
    disconnected_cls, timeout_cls = _load_engine_exception_types()
    tag = f"ipc_error:{type(exc).__name__}"
    if isinstance(exc, timeout_cls):
        return {
            "kind": "timeout",
            "http_status": 504,
            "detail": "engine timeout",
            "error_tag": tag,
        }
    if isinstance(exc, disconnected_cls):
        return {
            "kind": "disconnected",
            "http_status": 503,
            "detail": f"engine unreachable: {exc}",
            "error_tag": tag,
        }
    return {
        "kind": "other",
        "http_status": 503,
        "detail": f"engine error: {type(exc).__name__}: {exc}",
        "error_tag": tag,
    }


__all__ = [
    "raise_http_for_ipc_error",
    "ipc_error_boundary",
    "classify_ipc_exception",
]
