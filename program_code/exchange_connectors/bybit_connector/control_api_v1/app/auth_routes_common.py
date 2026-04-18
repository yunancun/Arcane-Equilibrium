from __future__ import annotations

"""
MODULE_NOTE (中文):
  認證路由共用輔助模組（E5-P0-5 拆分產物）。
  集中處理 IP 級別登入失敗鎖定、HttpOnly Cookie 設置與刪除、以及 bearer token
  的 constant-time 驗證。所有 auth 相關路由檔共用此模組，避免邏輯重複與鎖失衡。

  ★ 重要不變式：
  - `check_ip_lockout` / `increment_ip_failure` / `clear_ip_failure` 必須各自
    持有 `_login_fail_lock`，保留原 legacy_routes.py 的 read-check-write 原子性。
  - Cookie 設置/刪除路徑固定 "/", HttpOnly, SameSite=Strict, 且依 request scheme
    自動決定 Secure 屬性（FIX-11）。
  - Token 驗證走 `hmac.compare_digest`，避免 timing side-channel。

MODULE_NOTE (English):
  Shared helpers for auth-related legacy routes (product of E5-P0-5 split).
  Centralizes IP-level login lockout logic, HttpOnly cookie set/delete, and
  constant-time bearer token verification. All auth route files share this
  module to avoid duplicated logic and lock-misuse bugs.

  ★ Invariants:
  - `check_ip_lockout` / `increment_ip_failure` / `clear_ip_failure` each
    acquire `_login_fail_lock` themselves, preserving the read-check-write
    atomicity pattern from the original legacy_routes.py (L247-308).
  - Cookie set/delete always uses path="/", HttpOnly, SameSite=Strict, and
    auto-detects Secure from request scheme (FIX-11).
  - Token comparison uses `hmac.compare_digest` to avoid timing attacks.
"""

import hmac
import time
from typing import Any

from fastapi import HTTPException, Request
from pydantic import BaseModel
from starlette.responses import JSONResponse

from . import main_legacy as _base
from .auth import (
    _LOGIN_FAIL_MAX_IPS,
    _LOGIN_LOCKOUT_WINDOW,
    _LOGIN_MAX_FAILURES,
    _login_fail_counts,
    _login_fail_lock,
    _load_auth_credentials,
)


class AuthLoginRequest(BaseModel):
    """Login request body / 登入請求體."""

    username: str
    password: str


async def check_ip_lockout(client_ip: str, now: float) -> None:
    """
    Raise HTTP 429 if the IP is currently in the lockout window.
    若 IP 目前處於鎖定窗口，直接拋出 HTTP 429。

    Acquires `_login_fail_lock` to guarantee read-check-write atomicity
    (matches legacy_routes.py L247-264 semantics exactly).
    取得 `_login_fail_lock` 確保讀-判-寫原子性（等同 legacy_routes.py L247-264）。
    """
    async with _login_fail_lock:
        if client_ip in _login_fail_counts:
            fail_count, first_fail_ts = _login_fail_counts[client_ip]
            elapsed = now - first_fail_ts
            if elapsed > _LOGIN_LOCKOUT_WINDOW:
                # Window expired — reset counter automatically
                # 窗口期已過，自動重置計數器
                del _login_fail_counts[client_ip]
            elif fail_count >= _LOGIN_MAX_FAILURES:
                retry_after = int(_LOGIN_LOCKOUT_WINDOW - elapsed)
                raise HTTPException(
                    status_code=429,
                    detail={
                        "reason_codes": ["login_locked"],
                        "message": "Too many failed login attempts. Try again later.",
                        "retry_after": retry_after,
                    },
                )


async def increment_ip_failure(client_ip: str, now: float) -> None:
    """
    Record a failed login attempt for the given IP with capacity eviction.
    為指定 IP 記錄一次登入失敗，帶容量淘汰防 OOM。

    Follows the original P1-NEW-3 pattern: expire-first, FIFO-oldest eviction
    when at capacity, then increment.
    遵循原 P1-NEW-3 模式：先清過期、滿則 FIFO 刪最舊、再自增。
    """
    async with _login_fail_lock:
        # Evict expired / oldest entries if dict is at capacity (prevents OOM)
        # 超過容量上限時先清過期，再 FIFO 刪最舊條目，防止 OOM
        if len(_login_fail_counts) >= _LOGIN_FAIL_MAX_IPS:
            _now = time.time()
            expired = [
                ip for ip, (cnt, ts) in _login_fail_counts.items()
                if _now - ts > _LOGIN_LOCKOUT_WINDOW
            ]
            for ip in expired:
                del _login_fail_counts[ip]
            # If still at capacity after expiry eviction, remove oldest entry (FIFO)
            # 清完過期後仍超限，FIFO 刪最舊條目
            if len(_login_fail_counts) >= _LOGIN_FAIL_MAX_IPS:
                oldest_ip = next(iter(_login_fail_counts))
                del _login_fail_counts[oldest_ip]
        if client_ip in _login_fail_counts:
            prev_count, first_ts = _login_fail_counts[client_ip]
            _login_fail_counts[client_ip] = (prev_count + 1, first_ts)
        else:
            _login_fail_counts[client_ip] = (1, now)


async def clear_ip_failure(client_ip: str) -> None:
    """
    Clear all failure records for this IP on successful login.
    登入成功時清除該 IP 的失敗記錄。
    """
    async with _login_fail_lock:
        _login_fail_counts.pop(client_ip, None)


def load_expected_credentials() -> tuple[str, str]:
    """
    Load expected username/password from cached auth credentials.
    從快取載入期望的使用者名稱與密碼。

    Raises HTTPException(500) if credentials are not configured.
    若憑證未配置則拋出 500。
    """
    creds = _load_auth_credentials()
    expected_user = creds.get("GUI_USERNAME", "")
    expected_pass = creds.get("GUI_PASSWORD", "")

    if not expected_user:
        raise HTTPException(status_code=500, detail="Auth config not found")

    if expected_user == "YOUR_USERNAME":
        raise HTTPException(
            status_code=500,
            detail="Auth not configured — edit gui_auth.env",
        )

    return expected_user, expected_pass


def set_auth_cookie(resp: JSONResponse, token: str, request: Request) -> None:
    """
    Attach the HttpOnly auth cookie to the response.
    設置 HttpOnly 認證 cookie 到回應。

    SEC-06: JS cannot read; SameSite=Strict prevents CSRF; Secure auto-detected
    from request scheme (FIX-11).
    SEC-06：JS 不可讀；SameSite=Strict 防 CSRF；Secure 依 request scheme 自動判定。
    """
    resp.set_cookie(
        key="oc_auth_token",
        value=token,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        max_age=86400,
        path="/",
    )


def delete_auth_cookie(resp: JSONResponse, request: Request) -> None:
    """
    Clear the HttpOnly auth cookie on logout.
    登出時清除 HttpOnly 認證 cookie。
    """
    resp.delete_cookie(
        key="oc_auth_token",
        path="/",
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
    )


def verify_token_constant_time(token: str) -> bool:
    """
    Constant-time compare given token against the configured API token.
    以常數時間比對 token 與配置的 API token。

    Returns True iff the tokens match byte-for-byte.
    兩者逐位元相符時回傳 True。
    """
    if not token:
        return False
    expected = _base.settings.api_token
    return hmac.compare_digest(
        token.encode("utf-8"), expected.encode("utf-8")
    )


def verify_login_credentials(
    username: str, password: str, expected_user: str, expected_pass: str
) -> bool:
    """
    Constant-time compare login credentials against expected values.
    以常數時間比對登入憑證與期望值。
    """
    return (
        hmac.compare_digest(username, expected_user)
        and hmac.compare_digest(password, expected_pass)
    )


__all__ = [
    "AuthLoginRequest",
    "check_ip_lockout",
    "increment_ip_failure",
    "clear_ip_failure",
    "load_expected_credentials",
    "set_auth_cookie",
    "delete_auth_cookie",
    "verify_token_constant_time",
    "verify_login_credentials",
]
