from __future__ import annotations

"""
MODULE_NOTE (中文):
  Auth legacy 路由（E5-P0-5 拆分自 legacy_routes.py）。
  包含 3 條路由：
    POST /api/v1/auth/login    — 使用者密碼驗證，簽發 HttpOnly cookie（5/min rate limit）
    POST /api/v1/auth/logout   — 清除 HttpOnly cookie
    GET  /api/v1/auth/check    — 檢查 cookie 是否仍然有效

  ★ Monkey-patch 安全：所有受 main.py patch 的符號（STORE / envelope_response /
    get_latest_snapshot 等）必須在 request 時間透過 `_base.xxx(...)` 間接查找，
    不可在模組 top-level 捕獲。

MODULE_NOTE (English):
  Auth legacy routes (split out of legacy_routes.py in E5-P0-5).
  Contains 3 routes:
    POST /api/v1/auth/login    — username/password auth, issues HttpOnly cookie (5/min)
    POST /api/v1/auth/logout   — clears the HttpOnly cookie
    GET  /api/v1/auth/check    — validates that the auth cookie is still live

  ★ Monkey-patch safety: every main.py-patched symbol (STORE / envelope_response /
    get_latest_snapshot / etc.) is resolved via `_base.xxx(...)` at request time.
    No module-level capture of patched references.
"""

import time

from fastapi import HTTPException, Request
from starlette.responses import JSONResponse

from . import main_legacy as _base
from .auth_routes_common import (
    AuthLoginRequest,
    check_ip_lockout,
    clear_ip_failure,
    delete_auth_cookie,
    increment_ip_failure,
    load_expected_credentials,
    set_auth_cookie,
    verify_login_credentials,
    verify_token_constant_time,
)


def register_auth_legacy_routes(app) -> None:
    """
    Register all auth-related legacy routes on the FastAPI app.
    在 FastAPI app 上註冊所有 auth 相關 legacy 路由。
    """
    # ★ settings / limiter 不會被 monkey-patch，可直接捕獲。
    # ★ settings / limiter not monkey-patched, safe to capture here.
    settings = _base.settings
    limiter = _base.limiter

    @app.post("/api/v1/auth/login", include_in_schema=False)
    @limiter.limit("5/minute")
    async def auth_login(request: Request):
        """
        Authenticate with username/password, return HttpOnly bearer cookie.
        使用者名稱+密碼驗證，簽發 HttpOnly bearer cookie。

        Rate-limited to 5/minute per IP. IPs that fail ≥5 times within 15 minutes
        are locked out with HTTP 429 until the window expires.
        每 IP 限速 5/分鐘；15 分鐘內失敗 ≥5 次返回 429 鎖定。

        Note: Body parsed manually because @limiter.limit breaks FastAPI's Body() injection.
        注意：手動解析 body，因為 @limiter.limit 裝飾器破壞 FastAPI 的 Body() 注入。
        """
        try:
            body = await request.json()
            req = AuthLoginRequest(**body)
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid request body")

        client_ip: str = request.client.host if request.client else "unknown"
        now = time.time()

        # IP-level lockout check — before any credential work.
        # IP 級別鎖定檢查（在比對憑證之前）。
        await check_ip_lockout(client_ip, now)

        expected_user, expected_pass = load_expected_credentials()

        if not verify_login_credentials(
            req.username, req.password, expected_user, expected_pass
        ):
            # Record failure for this IP (with capacity eviction).
            # 記錄該 IP 的失敗（帶容量淘汰）。
            await increment_ip_failure(client_ip, now)
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Login succeeded — clear any failure record for this IP.
        # 登入成功，清除該 IP 的失敗記錄。
        await clear_ip_failure(client_ip)

        # SEC-06: do NOT echo the token in the JSON body — HttpOnly invariant.
        # SEC-06：不在 JSON body 中回傳 token，保持 HttpOnly 不變式。
        resp = JSONResponse({"status": "ok", "username": req.username})
        set_auth_cookie(resp, settings.api_token, request)
        return resp

    @app.post("/api/v1/auth/logout", include_in_schema=False)
    async def auth_logout(request: Request):
        """
        Clear the HttpOnly auth cookie. GUI calls this on logout.
        清除 HttpOnly 認證 cookie；GUI 登出時呼叫。
        """
        resp = JSONResponse({"status": "logged_out"})
        delete_auth_cookie(resp, request)
        return resp

    @app.get("/api/v1/auth/check", include_in_schema=False)
    async def auth_check(request: Request):
        """
        Lightweight endpoint for GUI to verify cookie validity.
        No Authorization header needed — reads cookie directly.
        GUI 用於驗證 cookie 是否仍有效的輕量端點；無需 Authorization header。
        """
        cookie_token = request.cookies.get("oc_auth_token")
        if not cookie_token:
            raise HTTPException(status_code=401, detail="Not authenticated")
        if not verify_token_constant_time(cookie_token):
            raise HTTPException(status_code=401, detail="Not authenticated")
        return {"authenticated": True}


__all__ = ["register_auth_legacy_routes"]
