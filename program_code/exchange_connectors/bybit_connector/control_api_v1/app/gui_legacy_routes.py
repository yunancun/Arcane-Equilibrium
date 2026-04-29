from __future__ import annotations

"""
MODULE_NOTE (中文):
  GUI / HTML legacy 路由（E5-P0-5 拆分自 legacy_routes.py）。
  包含 5 條路由：
    GET /login     — 登入頁面
    GET /          — 重定向到 /console
    GET /gui       — 舊版 GUI index.html
    GET /console   — 統一控制台（交易儀表盤 + OpenClaw + AI Cost 側欄）
    GET /trading   — 交易圖表儀表盤（TradingView Lightweight Charts）

  除 /login 與根目錄 redirect 外，dashboard HTML 由 server-side auth guard
  保護，避免 client-side redirect JS 被 static auth middleware 擋住時仍洩漏 shell。

MODULE_NOTE (English):
  GUI / HTML legacy routes (split out of legacy_routes.py in E5-P0-5).
  Contains 5 routes:
    GET /login     — login page
    GET /          — redirect to /console
    GET /gui       — legacy GUI index.html
    GET /console   — unified console (trading dashboard + OpenClaw + AI cost sidebar)
    GET /trading   — trading chart dashboard (TradingView Lightweight Charts)

  Except /login and the root redirect, dashboard HTML is protected by a
  server-side auth guard so the shell is not served before auth.
"""

from pathlib import Path

from fastapi import Depends
from fastapi.responses import FileResponse
from starlette.responses import RedirectResponse

_static_dir = Path(__file__).resolve().parent / "static"


# Cache-Control headers to prevent stale GUI HTML when assets change.
# 禁用快取以避免 GUI HTML 陳舊。
_NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}


def register_gui_legacy_routes(app) -> None:
    """
    Register all GUI / HTML legacy routes on the FastAPI app.
    在 FastAPI app 上註冊所有 GUI / HTML legacy 路由。
    """
    from . import main_legacy as _base

    @app.get("/login", include_in_schema=False)
    def login_page() -> FileResponse:
        """Login page for GUI authentication / GUI 登入頁面."""
        return FileResponse(_static_dir / "login.html")

    @app.get("/", include_in_schema=False)
    def root_redirect():
        """Redirect site root to /console / 站點根目錄重定向到 /console."""
        return RedirectResponse(url="/console")

    @app.get("/gui", include_in_schema=False)
    def gui_index(actor=Depends(_base.current_actor)) -> FileResponse:
        """Legacy GUI index.html / 舊版 GUI index.html."""
        return FileResponse(_static_dir / "index.html", headers=_NO_CACHE_HEADERS)

    @app.get("/console", include_in_schema=False)
    def console_index(actor=Depends(_base.current_actor)) -> FileResponse:
        """Unified console: Trading Dashboard + OpenClaw + AI Cost sidebar.
        統一控制台：交易儀表盤 + OpenClaw + AI Cost 側欄。"""
        return FileResponse(_static_dir / "console.html", headers=_NO_CACHE_HEADERS)

    @app.get("/trading", include_in_schema=False)
    def trading_dashboard(actor=Depends(_base.current_actor)) -> FileResponse:
        """Trading chart dashboard: TradingView Lightweight Charts + signals + strategies.
        交易圖表儀表盤：TradingView Lightweight Charts + 信號 + 策略。"""
        return FileResponse(_static_dir / "trading.html", headers=_NO_CACHE_HEADERS)


__all__ = ["register_gui_legacy_routes"]
