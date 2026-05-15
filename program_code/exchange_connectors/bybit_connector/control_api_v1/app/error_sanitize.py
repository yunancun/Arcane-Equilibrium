"""統一錯誤訊息消毒 helper — production 不洩漏 internal exception 細節。

WP-05 Real Fix（取代 WP-05 偽修復）。Global `@app.exception_handler(Exception)` 不
catch `HTTPException` / `RequestValidationError`（FastAPI 順位），所以舊 patch 對
25+ route 仍 raise `HTTPException(detail=f"...{exc}")` 的場景完全無效。本模組提供：

  - `sanitize_exc_for_detail(exc, reason_code)`：回傳穩定的 dict response detail
    （包 `reason_codes` + safe message）。
  - `sanitize_exc_str(exc, fallback)`：回傳純字串（給 `JSONResponse content`
    legacy 路徑用，如 `{"detail": str(e)}` 的 503 fallback）。

`OPENCLAW_DEBUG=1` 時保留 truncated 原始訊息（≤200 chars，type-name + 截斷 str）
供 dev 排查；production（default）只回穩定的 user-facing 訊息。
"""

from __future__ import annotations

import os

_DEBUG = os.getenv("OPENCLAW_DEBUG", "").strip() == "1"

# Reason code → user-facing message 字典（穩定不洩漏內部細節）
# 新增 reason code 必同步更新此表 + WP-05 sign-off report。
_REASON_CODE_MESSAGES: dict[str, str] = {
    "ipc_unreachable": "Engine unreachable",
    "ipc_timeout": "Engine timeout",
    "ipc_error": "Engine error",
    "rust_engine_unavailable": "Rust engine unavailable",
    "auth_failure": "Authentication failed",
    "auth_write_failure": "Authorization write failed",
    "bybit_api_failure": "Exchange API call failed",
    "db_error": "Database error",
    "internal_error": "Internal server error",
    "config_invalid": "Configuration invalid",
    "validation_failed": "Validation failed",
}


def sanitize_exc_for_detail(
    exc: BaseException,
    reason_code: str = "internal_error",
) -> dict:
    """轉換 exception 成穩定不洩漏的 response detail dict。

    Returns:
        {"reason_codes": [reason_code], "detail": "<safe message>"}
        - production: detail = 對應 reason_code 的 user-facing message
        - OPENCLAW_DEBUG=1: detail 額外加 truncated exc class name + str(exc)[:200]

    若 `reason_code` 不在字典：fallback 用 "internal_error" 對應訊息。
    """
    safe_msg = _REASON_CODE_MESSAGES.get(
        reason_code,
        _REASON_CODE_MESSAGES["internal_error"],
    )
    if _DEBUG:
        exc_repr = f"{type(exc).__name__}: {str(exc)[:200]}"
        return {
            "reason_codes": [reason_code],
            "detail": f"{safe_msg} ({exc_repr})",
        }
    return {"reason_codes": [reason_code], "detail": safe_msg}


def sanitize_exc_str(
    exc: BaseException,
    fallback: str = "Internal server error",
) -> str:
    """純字串版本，給 `JSONResponse(content={"detail": str(...)})` legacy 路徑用。

    production: 回傳 `fallback`（caller 自定義 user-facing 短訊息）。
    OPENCLAW_DEBUG=1: 額外附 truncated exc class name + str(exc)[:200]。
    """
    if _DEBUG:
        return f"{fallback} ({type(exc).__name__}: {str(exc)[:200]})"
    return fallback


__all__ = [
    "sanitize_exc_for_detail",
    "sanitize_exc_str",
]
