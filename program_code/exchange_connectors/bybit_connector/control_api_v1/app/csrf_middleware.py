from __future__ import annotations

"""
MODULE_NOTE (中文):
  CSRF double-submit token middleware（OPS-1 Track B）。
  對所有寫操作（POST / PUT / DELETE / PATCH）強制：請求 header
  `X-CSRF-Token` 必須存在且與 cookie `oc_csrf` constant-time 相等；
  不匹配回 403 + reason_code `csrf_token_mismatch`。

  為什麼 double-submit 而不寫 server-side session：
  - OpenClaw 認證本身就是 stateless cookie，無 session store
  - IMPL 小（單 middleware ~80 行 + 前端 helper），符合 spec §4.2 偏好
  - 已 SameSite=Strict 第一層下，double-submit 第二層足夠 95% 場景

  豁免清單：
  - GET / HEAD / OPTIONS — 純讀，無 side effect，自動跳過
  - `/api/v1/auth/login` — login 時 csrf cookie 還沒存在
  - `/api/v1/auth/logout` — logout 需要對應同源 POST，但 SameSite=Strict
     已防 CSRF；豁免避免 GUI 登出鏈卡住
  - `/api/v1/csp/report` — 瀏覽器自動 POST，不可能附 token
  - `/api/v1/healthz` — 系統健康檢查
  - `/static/*` — 靜態資源（雖然不會 POST）

  Shadow mode：`OPENCLAW_CSRF_SHADOW=1` 時，token 不匹配只記 warning，
  仍放行。為 spec §7.2 風險 #2「上線後既有 GUI 寫操作全 403」緩衝期。

  Token 來源（登入時設定）：
  - JS 前端讀 `document.cookie['oc_csrf']` → 寫入 X-CSRF-Token header
  - cookie 屬性：HttpOnly=False（讓 JS 讀）+ SameSite=Strict + Secure（Live）

  比對採用 `hmac.compare_digest` 防 timing attack。

MODULE_NOTE (English):
  CSRF double-submit token middleware (OPS-1 Track B). Enforces matching
  `X-CSRF-Token` header vs `oc_csrf` cookie on write operations; mismatch
  returns 403 with reason_code `csrf_token_mismatch`.

硬邊界：
  - constant-time compare 必走 `hmac.compare_digest`，禁直接 `==`
  - 豁免清單只能寫進原始碼，不能由 env 動態擴充（防 operator 誤關 CSRF）
"""

import hmac
import logging
import os
import secrets
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# 寫操作 method 白名單（外面是讀操作，自動跳過）。
_WRITE_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})

# 豁免路徑（精確比對，不支援 wildcard 以避免 operator 失誤）。
# 為什麼 hard-coded：CSRF 豁免是安全敏感決策，禁止由 env / config 文件動態擴充。
_EXEMPT_PATHS = frozenset(
    {
        "/api/v1/auth/login",     # login 時還沒有 csrf cookie 可比對
        "/api/v1/auth/logout",    # SameSite=Strict 已防；豁免避免登出鏈斷
        "/api/v1/csp/report",     # 瀏覽器後台 POST，不可能附 token
        "/api/v1/healthz",        # 健康檢查
    }
)

# 豁免前綴（spec §4.2 提到 static — 雖然不會 POST，留作 defence-in-depth）。
_EXEMPT_PREFIXES = ("/static/",)

CSRF_COOKIE_NAME = "oc_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"


def _is_shadow_mode() -> bool:
    """讀 OPENCLAW_CSRF_SHADOW env：1/true 啟用 shadow（只 log warning 不阻擋）。

    為什麼：spec §7.2 風險 #2 緩衝；前 14 天 shadow 蒐集「哪個 tab fetch 沒接
    csrf token」的真實 violation 樣本，E2 review 後才正式 enforce。
    """
    flag = (os.getenv("OPENCLAW_CSRF_SHADOW", "") or "").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def _is_exempt(path: str) -> bool:
    """判定路徑是否在 CSRF 豁免名單內。"""
    if path in _EXEMPT_PATHS:
        return True
    for prefix in _EXEMPT_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


def _csrf_mismatch_response(reason: str) -> JSONResponse:
    """統一 403 結構，對齊 main_legacy.py exception handler 的 `reason_codes` 風格。"""
    return JSONResponse(
        status_code=403,
        content={
            "detail": {
                "reason_codes": ["csrf_token_mismatch"],
                "reason_detail": reason,
            }
        },
    )


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double-submit CSRF middleware。

    流程：
    1. method 不在寫操作集合 → 直接 pass-through
    2. path 在豁免名單 → 直接 pass-through
    3. cookie `oc_csrf` 缺失 → 403 reason_codes=["csrf_token_mismatch"]
    4. header `X-CSRF-Token` 缺失 → 403
    5. constant-time 比對 → mismatch 則 403
    6. 全部通過 → pass-through 給下游 handler

    Shadow mode：3/4/5 mismatch 時改 logger.warning + 放行，方便上線過渡。
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        method = request.method.upper()
        path = request.url.path

        # 讀操作直接過，不論豁免。
        if method not in _WRITE_METHODS:
            return await call_next(request)

        # 豁免路徑直接過。
        if _is_exempt(path):
            return await call_next(request)

        cookie_token = request.cookies.get(CSRF_COOKIE_NAME, "")
        header_token = request.headers.get(CSRF_HEADER_NAME, "")

        shadow = _is_shadow_mode()

        if not cookie_token:
            msg = f"missing cookie {CSRF_COOKIE_NAME!r}"
            if shadow:
                logger.warning(
                    "csrf_shadow: %s on %s %s (would 403 if enforced)",
                    msg, method, path,
                )
                return await call_next(request)
            return _csrf_mismatch_response(msg)

        if not header_token:
            msg = f"missing header {CSRF_HEADER_NAME!r}"
            if shadow:
                logger.warning(
                    "csrf_shadow: %s on %s %s",
                    msg, method, path,
                )
                return await call_next(request)
            return _csrf_mismatch_response(msg)

        # constant-time compare 防 timing attack。
        if not hmac.compare_digest(
            cookie_token.encode("utf-8"),
            header_token.encode("utf-8"),
        ):
            msg = "cookie/header mismatch"
            if shadow:
                logger.warning(
                    "csrf_shadow: %s on %s %s",
                    msg, method, path,
                )
                return await call_next(request)
            return _csrf_mismatch_response(msg)

        return await call_next(request)


def generate_csrf_token() -> str:
    """產生 256-bit 隨機 CSRF token（URL-safe base64）。

    為什麼 32 byte：對齊一般 session token 強度；
    `secrets.token_urlsafe(32)` 產出 ~43 字元 URL-safe 字串。
    """
    return secrets.token_urlsafe(32)


def set_csrf_cookie(response: Response, token: str, *, secure: bool) -> None:
    """登入成功時把 CSRF token 寫入 cookie。

    為什麼 HttpOnly=False：double-submit 要 JS 能讀回 cookie 再寫入
    `X-CSRF-Token` header。SameSite=Strict 已是第一層；
    HttpOnly=False 換來 double-submit 第二層整體更安全。
    """
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        httponly=False,  # 為 double-submit 可被 JS 讀取
        samesite="strict",
        secure=secure,
        max_age=86400,
        path="/",
    )


def delete_csrf_cookie(response: Response, *, secure: bool) -> None:
    """登出時清除 CSRF cookie。"""
    response.delete_cookie(
        key=CSRF_COOKIE_NAME,
        path="/",
        httponly=False,
        samesite="strict",
        secure=secure,
    )


__all__ = [
    "CSRFMiddleware",
    "CSRF_COOKIE_NAME",
    "CSRF_HEADER_NAME",
    "generate_csrf_token",
    "set_csrf_cookie",
    "delete_csrf_cookie",
]
