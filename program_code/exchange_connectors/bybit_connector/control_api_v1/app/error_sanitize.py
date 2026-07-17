"""統一錯誤訊息消毒 helper — production 不洩漏 internal exception 細節。

WP-05 Real Fix（取代 WP-05 偽修復）。Global `@app.exception_handler(Exception)` 不
catch `HTTPException` / `RequestValidationError`（FastAPI 順位），所以舊 patch 對
25+ route 仍 raise `HTTPException(detail=f"...{exc}")` 的場景完全無效。本模組提供：

  - `sanitize_exc_for_detail(exc, reason_code)`：回傳穩定的 dict response detail
    （包 `reason_codes` + safe message）。
  - `sanitize_exc_str(exc, fallback)`：回傳純字串，供 legacy JSONResponse
    error fallback 路徑使用。

所有環境都只回穩定的 user-facing 訊息；診斷資訊透過 opaque error id 與
exception type 寫入 server log，不記錄 exception message 或 traceback。
"""

from __future__ import annotations

import logging
import secrets
from typing import Any

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
        detail = 對應 reason_code 的 user-facing message

    若 `reason_code` 不在字典：fallback 用 "internal_error" 對應訊息。
    """
    safe_msg = _REASON_CODE_MESSAGES.get(
        reason_code,
        _REASON_CODE_MESSAGES["internal_error"],
    )
    return {"reason_codes": [reason_code], "detail": safe_msg}


def sanitize_exc_str(
    exc: BaseException,
    fallback: str = "Internal server error",
) -> str:
    """純字串版本，供 legacy JSONResponse error fallback 路徑使用。

    回傳 `fallback`（caller 自定義 user-facing 短訊息）。
    """
    return fallback


def log_safe_exception(
    logger: Any,
    operation: str,
    exc: BaseException,
    *,
    level: int = logging.ERROR,
) -> str:
    """Log an opaque correlation id and exception type without message or trace."""
    error_id = f"err_{secrets.token_hex(8)}"
    logger.log(
        level,
        "operation=%s error_id=%s exception_type=%s",
        operation,
        error_id,
        type(exc).__name__,
    )
    return error_id


__all__ = [
    "sanitize_exc_for_detail",
    "sanitize_exc_str",
    "log_safe_exception",
]
