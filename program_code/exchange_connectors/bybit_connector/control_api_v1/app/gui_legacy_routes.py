from __future__ import annotations

"""
MODULE_NOTE (中文):
  GUI / HTML legacy 路由（E5-P0-5 拆分自 legacy_routes.py）。
  包含 7 條路由：
    GET /login     — 登入頁面
    GET /          — 統一控制台根入口
    GET /gui       — 舊版 GUI index.html
    GET /console   — 統一控制台（cutover flag=1 服玄衡新殼 shell.html，default OFF 服 console.html）
    GET /console/legacy — 永久 legacy 逃生口（無條件服 console.html，供新殼 fallback 安全退回）
    GET /trading   — 交易圖表儀表盤（TradingView Lightweight Charts）
    GET /favicon.ico — empty favicon response to avoid GUI console 404 noise

  除 /login 與根目錄 redirect 外，dashboard HTML 由 server-side auth guard
  保護，避免 client-side redirect JS 被 static auth middleware 擋住時仍洩漏 shell。

MODULE_NOTE (English):
  GUI / HTML legacy routes (split out of legacy_routes.py in E5-P0-5).
  Contains 7 routes:
    GET /login     — login page
    GET /          — unified console root entry
    GET /gui       — legacy GUI index.html
    GET /console   — unified console (cutover flag=1 serves shell.html, default OFF serves console.html)
    GET /console/legacy — permanent legacy escape hatch (always serves console.html for shell fallback)
    GET /trading   — trading chart dashboard (TradingView Lightweight Charts)
    GET /favicon.ico — empty favicon response to avoid GUI console 404 noise

  Except /login and the root redirect, dashboard HTML is protected by a
  server-side auth guard so the shell is not served before auth.
"""

import os
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, Response
from starlette.responses import RedirectResponse

_static_dir = Path(__file__).resolve().parent / "static"


# Cache-Control headers to prevent stale GUI HTML when assets change.
# 禁用快取以避免 GUI HTML 陳舊。
_NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}


def _is_unauthenticated(exc: HTTPException) -> bool:
    """Return True for the canonical current_actor unauthenticated error."""
    detail = exc.detail
    return (
        exc.status_code == 401
        and isinstance(detail, dict)
        and "unauthenticated" in detail.get("reason_codes", [])
    )


def _login_redirect_for(request: Request) -> RedirectResponse:
    """Redirect GUI document requests to login while preserving the target path."""
    target = request.url.path
    if request.url.query:
        target = f"{target}?{request.url.query}"
    return RedirectResponse(
        url=f"/login?redirect={quote(target, safe='/')}",
        status_code=303,
        headers=_NO_CACHE_HEADERS,
    )


def _redirect_if_unauthenticated(request: Request) -> RedirectResponse | None:
    """Authenticate a GUI shell request, or return a login redirect."""
    from . import main_legacy as _base

    try:
        _base.current_actor(
            request=request,
            authorization=request.headers.get("authorization"),
        )
    except HTTPException as exc:
        if _is_unauthenticated(exc):
            return _login_redirect_for(request)
        raise
    return None


def register_gui_legacy_routes(app) -> None:
    """
    Register all GUI / HTML legacy routes on the FastAPI app.
    在 FastAPI app 上註冊所有 GUI / HTML legacy 路由。
    """

    @app.get("/login", include_in_schema=False)
    def login_page() -> FileResponse:
        """Login page for GUI authentication / GUI 登入頁面."""
        return FileResponse(_static_dir / "login.html")

    @app.get("/", include_in_schema=False)
    def root_console(request: Request):
        """Unified console root entry / 統一控制台根入口。"""
        redirect = _redirect_if_unauthenticated(request)
        if redirect is not None:
            return redirect
        return FileResponse(_static_dir / "console.html", headers=_NO_CACHE_HEADERS)

    @app.get("/gui", include_in_schema=False)
    def gui_index(request: Request):
        """Legacy GUI index.html / 舊版 GUI index.html."""
        redirect = _redirect_if_unauthenticated(request)
        if redirect is not None:
            return redirect
        return FileResponse(_static_dir / "index.html", headers=_NO_CACHE_HEADERS)

    @app.get("/console", include_in_schema=False)
    def console_index(request: Request):
        """Unified console: Trading Dashboard + OpenClaw + AI Cost sidebar.
        統一控制台：交易儀表盤 + OpenClaw + AI Cost 側欄。"""
        redirect = _redirect_if_unauthenticated(request)
        if redirect is not None:
            return redirect
        # cutover flag：OPENCLAW_GUI_SHELL_DEFAULT=="1" 時 /console 改服玄衡新殼 shell.html，
        # 否則維持 console.html。default OFF（未設或非 "1"）→ 部署重啟後行為不變，operator
        # 顯式設 =1 才翻轉、unset 即一鍵回滾（fail-safe：翻轉時機由 operator 掌控，非部署即翻臉）。
        # handler 保持 parse→call→format，無商業邏輯（僅選檔）。
        if os.getenv("OPENCLAW_GUI_SHELL_DEFAULT") == "1":
            return FileResponse(_static_dir / "shell.html", headers=_NO_CACHE_HEADERS)
        return FileResponse(_static_dir / "console.html", headers=_NO_CACHE_HEADERS)

    @app.get("/console/legacy", include_in_schema=False)
    def console_legacy(request: Request):
        """永久 legacy 逃生口：無條件服 console.html。

        為什麼：cutover(flag=1)後 /console 改服 shell.html，新殼的 fallback 連結需一條
        穩定的 legacy 路徑安全退回；若指回裸 /console 會在 cutover 態下形成回殼無限迴圈。
        守衛逐字複用 console_index 的 _redirect_if_unauthenticated（auth 零弱化，不引入
        未守衛的檔案暴露路徑）。"""
        redirect = _redirect_if_unauthenticated(request)
        if redirect is not None:
            return redirect
        return FileResponse(_static_dir / "console.html", headers=_NO_CACHE_HEADERS)

    @app.get("/trading", include_in_schema=False)
    def trading_dashboard(request: Request):
        """Trading chart dashboard: TradingView Lightweight Charts + signals + strategies.
        交易圖表儀表盤：TradingView Lightweight Charts + 信號 + 策略。"""
        redirect = _redirect_if_unauthenticated(request)
        if redirect is not None:
            return redirect
        return FileResponse(_static_dir / "trading.html", headers=_NO_CACHE_HEADERS)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        """Avoid browser favicon 404 noise in the operator console."""
        return Response(status_code=204, headers=_NO_CACHE_HEADERS)


__all__ = ["register_gui_legacy_routes"]
