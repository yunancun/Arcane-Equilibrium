from __future__ import annotations

"""
MODULE_NOTE (中文):
  遺留路由處理器模塊。包含所有 FastAPI 路由端點定義：認證（login/logout/check）、
  靜態頁面、系統查詢、控制操作、學習系統、PnL、自動學習管線等。
  從 main_legacy.py 拆分而來（Wave D 重構）。

  ★ 路由通過 register_legacy_routes() 函數註冊到 app，
  在 main_legacy.py 中 app 創建後調用。

MODULE_NOTE (English):
  Legacy route handlers module. Contains all FastAPI route endpoint definitions:
  auth (login/logout/check), static pages, system queries, control operations,
  learning system, PnL, auto learning pipeline, etc.
  Extracted from main_legacy.py (Wave D refactoring).

  ★ Routes are registered to app via register_legacy_routes() function,
  called in main_legacy.py after app creation.
"""

import hmac
import logging
import os
import tempfile
import threading
import time
from typing import Any

from fastapi import Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pathlib import Path
from pydantic import BaseModel, Field

from . import main_legacy as _base
from .auth import (
    AuthenticatedActor,
    _load_auth_credentials,
    _login_fail_counts,
    _LOGIN_FAIL_MAX_IPS,
    _LOGIN_LOCKOUT_WINDOW,
    _LOGIN_MAX_FAILURES,
    _login_fail_lock,
)
from .control_ops import (
    apply_config_change,
    apply_input_action,
    apply_product_family_config,
    build_overview,
    perform_demo_transition,
    perform_recheck,
    perform_safe_bundle,
    perform_validate,
)
from .learning_ops import (
    apply_ai_consultation,
    apply_auto_generate,
    apply_experiment_approval,
    apply_experiment_completion,
    apply_hypothesis_verdict,
    apply_learning_experiment,
    apply_learning_hypothesis,
    apply_learning_lesson,
    apply_learning_observation,
    apply_review_decision,
    build_learning_experiments,
    build_learning_feed,
    build_review_queue,
)
from .pnl_ops import (
    apply_pnl_entry,
    apply_pnl_period_snapshot,
    build_business_summary,
    build_net_pnl_dashboard,
)
from .state_models import (
    AIConsultationResultData,
    AutoGenerationResultData,
    BusinessSummaryData,
    ConfigChangeAcceptedData,
    DemoTransitionData,
    DemoValidateData,
    ExperimentAcceptedData,
    ExperimentApprovalData,
    ExperimentCompletionData,
    HypothesisAcceptedData,
    HypothesisVerdictData,
    InputAcceptedData,
    LearningExperimentsData,
    LearningFeedData,
    LearningHypothesesData,
    LearningOverviewData,
    LessonAcceptedData,
    NetPnLDashboardData,
    ObservationAcceptedData,
    OverviewData,
    PnLEntryData,
    ProductFamilyConfigData,
    RecheckResultData,
    RequestEnvelope,
    ResponseEnvelope,
    ReviewDecisionData,
    ReviewQueueData,
    SafeBundleData,
)

logger = logging.getLogger(__name__)

static_dir = Path(__file__).resolve().parent / "static"


class _LoginRequest(BaseModel):
    username: str
    password: str


class ScheduledRestartRequest(BaseModel):
    """Request body for scheduled restart / 计划重启请求体"""
    delay_minutes: int = Field(..., description="Restart delay in minutes (5/10/15/30/60)")
    force_liquidate: bool = Field(False, description="Close profitable paper positions before restart")

    def validate_delay(self) -> None:
        if self.delay_minutes not in (5, 10, 15, 30, 60):
            raise ValueError("delay_minutes must be one of: 5, 10, 15, 30, 60")


def _close_profitable_paper_positions() -> dict[str, Any]:
    """
    Close paper positions where net PnL (after fees) > 0.
    关闭净盈利（扣除手续费后）的纸盘仓位。

    Returns dict with closed/skipped lists.
    """
    TAKER_FEE_RATE = 0.00055  # Bybit taker fee / Bybit taker 手续费

    try:
        from .phase2_strategy_routes import PAPER_ENGINE, PIPELINE_BRIDGE
    except ImportError:
        return {"closed": [], "skipped": [], "error": "paper engine not available"}

    if PAPER_ENGINE is None:
        return {"closed": [], "skipped": [], "error": "paper engine not initialized"}

    try:
        state = PAPER_ENGINE.get_state()
    except Exception as exc:
        return {"closed": [], "skipped": [], "error": str(exc)}

    positions = state.get("positions", {})
    latest_prices: dict[str, float] = {}
    if PIPELINE_BRIDGE is not None:
        try:
            latest_prices = dict(PIPELINE_BRIDGE._latest_prices)
        except Exception:
            pass

    closed: list[dict] = []
    skipped: list[dict] = []

    for symbol, pos in positions.items():
        qty = pos.get("qty", 0)
        side = pos.get("side", "long")
        entry_price = pos.get("entry_price", 0)
        current_price = latest_prices.get(symbol, 0)

        if qty <= 0 or entry_price <= 0 or current_price <= 0:
            skipped.append({"symbol": symbol, "reason": "missing_price_data"})
            continue

        notional = current_price * qty
        fee_cost = notional * TAKER_FEE_RATE * 2  # open + close taker fees
        raw_pnl = (current_price - entry_price) * qty if side == "long" else (entry_price - current_price) * qty
        net_pnl = raw_pnl - fee_cost

        if net_pnl <= 0:
            skipped.append({"symbol": symbol, "reason": f"would_lose_usd_{-net_pnl:.4f}", "net_pnl": round(net_pnl, 4)})
            continue

        # Close position / 平仓
        close_side = "Sell" if side == "long" else "Buy"
        try:
            PAPER_ENGINE.submit_order(
                symbol=symbol,
                side=close_side,
                order_type="market",
                qty=qty,
                market_prices=latest_prices,
            )
            closed.append({"symbol": symbol, "side": side, "qty": qty,
                           "net_pnl": round(net_pnl, 4), "close_price": current_price})
        except Exception as exc:
            skipped.append({"symbol": symbol, "reason": f"submit_error: {exc}"})

    return {"closed": closed, "skipped": skipped, "error": None}


def _run_restart_in_background(delay_seconds: int) -> None:
    """
    Background thread: sleep then restart the uvicorn process.
    后台线程：等待后重启 uvicorn 进程。

    Writes a temp shell script and executes it in a new session so the
    parent process can die without killing the restart script.
    写入临时 shell 脚本并在新会话中执行，使父进程可以退出而不影响重启脚本。
    """
    import signal
    import subprocess
    import sys

    pid = os.getpid()
    python = sys.executable
    # Reconstruct uvicorn launch command / 重建 uvicorn 启动命令
    work_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # P1-14: Use project logs/ dir instead of /tmp/ to prevent symlink attacks.
    # P1-14 修复：使用项目内 logs/ 目录，防止符号链接攻击。
    script_content = f"""#!/bin/bash
# OpenClaw scheduled restart script / 计划重启脚本
sleep {delay_seconds}
kill {pid} 2>/dev/null
sleep 3
cd {work_dir}
mkdir -p {work_dir}/logs
nohup {python} -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >> {work_dir}/logs/restart.log 2>&1 &
echo "Restarted PID=$!" >> {work_dir}/logs/restart.log
"""
    try:
        fd, script_path = tempfile.mkstemp(suffix=".sh", prefix="openclaw_restart_")
        with os.fdopen(fd, "w") as f:
            f.write(script_content)
        os.chmod(script_path, 0o700)
        subprocess.Popen(
            ["bash", script_path],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info("Scheduled restart script launched: delay=%ds pid=%d", delay_seconds, pid)
    except Exception as exc:
        logger.error("Failed to launch restart script: %s", exc)



def register_legacy_routes(app) -> None:
    """
    Register all legacy route handlers on the FastAPI app.
    在 FastAPI app 上註冊所有遺留路由處理器。

    Called from main_legacy.py after app creation + middleware setup.
    在 main_legacy.py 中 app 創建和中間件設置完成後調用。
    """
    # ★ settings / limiter 不會被 monkey-patch，可以直接捕獲。
    # ★ settings / limiter are not monkey-patched, safe to capture directly.
    settings = _base.settings
    limiter = _base.limiter
    # ★ current_actor / envelope_response / get_latest_snapshot 會被 main.py monkey-patch，
    #   必須在路由函數內通過 _base.xxx 延遲查找，不可在此捕獲。
    # ★ current_actor / envelope_response / get_latest_snapshot are monkey-patched by main.py,
    #   must be looked up via _base.xxx at call time inside route functions, NOT captured here.

    @app.get("/login", include_in_schema=False)
    def login_page() -> FileResponse:
        """Login page for GUI authentication / GUI 登录页面"""
        return FileResponse(static_dir / "login.html")


    class _LoginRequest(BaseModel):
        username: str
        password: str


    @app.post("/api/v1/auth/login", include_in_schema=False)
    @limiter.limit("5/minute")
    async def auth_login(request: Request):
        """
        Authenticate with username/password, return bearer token.
        用户名密码认证，返回 bearer token。

        Rate-limited to 5/minute per IP. IPs that fail ≥5 times within 15 minutes
        are locked out with HTTP 429 until the window expires.
        每IP限速5次/分钟。同一IP在15分钟内失败≥5次，返回429并锁定至窗口期结束。（P1-8 修复）

        Note: Body parsed manually because @limiter.limit breaks FastAPI's Body() injection.
        注意：手动解析 body，因为 @limiter.limit 装饰器破坏 FastAPI 的 Body() 注入。
        """
        try:
            body = await request.json()
            req = _LoginRequest(**body)
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid request body")

        client_ip: str = request.client.host if request.client else "unknown"
        now = time.time()

        # --- IP-level lockout check — runs before any credential work ---
        # --- IP 级别锁定检查（在验证凭证之前执行）---
        # Lock wraps the read-modify-write to avoid race conditions (P1-NEW-3)
        # 用 Lock 包裹读-改-写，防止并发竞态（P1-NEW-3）
        async with _login_fail_lock:
            if client_ip in _login_fail_counts:
                fail_count, first_fail_ts = _login_fail_counts[client_ip]
                elapsed = now - first_fail_ts
                if elapsed > _LOGIN_LOCKOUT_WINDOW:
                    # Window expired — reset counter automatically
                    # 窗口期已过，自动重置计数器
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

        # Load credentials from startup cache (P1-12: avoid per-request file I/O)
        # 从启动缓存读取凭证（P1-12 修复：避免每次请求读文件）
        _creds = _load_auth_credentials()
        _expected_user = _creds.get("GUI_USERNAME", "")
        _expected_pass = _creds.get("GUI_PASSWORD", "")

        if not _expected_user:
            raise HTTPException(status_code=500, detail="Auth config not found")

        if _expected_user == "YOUR_USERNAME":
            raise HTTPException(status_code=500, detail="Auth not configured — edit gui_auth.env")

        if not (hmac.compare_digest(req.username, _expected_user) and
                hmac.compare_digest(req.password, _expected_pass)):
            # Increment failure counter for this IP, with capacity eviction (P1-NEW-3)
            # 遞增此 IP 的失败计数器，加容量上限清理（P1-NEW-3）
            async with _login_fail_lock:
                # Evict expired / oldest entries if dict is at capacity (prevents OOM)
                # 超过容量上限时先清过期，再 FIFO 删最旧条目，防止 OOM
                if len(_login_fail_counts) >= _LOGIN_FAIL_MAX_IPS:
                    _now = time.time()
                    expired = [
                        ip for ip, (cnt, ts) in _login_fail_counts.items()
                        if _now - ts > _LOGIN_LOCKOUT_WINDOW
                    ]
                    for ip in expired:
                        del _login_fail_counts[ip]
                    # If still at capacity after expiry eviction, remove oldest entry (FIFO)
                    # 清完过期后仍超限，FIFO 删最旧条目
                    if len(_login_fail_counts) >= _LOGIN_FAIL_MAX_IPS:
                        oldest_ip = next(iter(_login_fail_counts))
                        del _login_fail_counts[oldest_ip]
                if client_ip in _login_fail_counts:
                    prev_count, first_ts = _login_fail_counts[client_ip]
                    _login_fail_counts[client_ip] = (prev_count + 1, first_ts)
                else:
                    _login_fail_counts[client_ip] = (1, now)
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Login succeeded — clear any failure record for this IP
        # 登录成功，清除该 IP 的失败记录
        async with _login_fail_lock:
            _login_fail_counts.pop(client_ip, None)

        # Set HttpOnly cookie so GUI never needs to touch the token in JS.
        # Also return token in JSON body for backward compatibility with programmatic clients.
        # 设置 HttpOnly cookie，GUI 不再需要在 JS 中操作 token。
        # 同时在 JSON body 中返回 token，保持编程客户端的向后兼容。
        from starlette.responses import JSONResponse
        resp = JSONResponse({"token": settings.api_token, "username": req.username})
        resp.set_cookie(
            key="oc_auth_token",
            value=settings.api_token,
            httponly=True,           # JS 不可读取，防 XSS / Not accessible from JS, prevents XSS
            samesite="strict",       # 防 CSRF / Prevents CSRF
            secure=False,            # TODO: 启用 HTTPS 后改为 True / Set True when HTTPS is enabled
            max_age=86400,           # 24 小时有效 / 24h TTL
            path="/",                # 全站可用 / Available site-wide
        )
        return resp


    @app.post("/api/v1/auth/logout", include_in_schema=False)
    async def auth_logout(request: Request):
        """
        Clear the HttpOnly auth cookie. GUI calls this on logout.
        清除 HttpOnly 认证 cookie。GUI 登出时调用此端点。
        """
        from starlette.responses import JSONResponse
        resp = JSONResponse({"status": "logged_out"})
        resp.delete_cookie(
            key="oc_auth_token",
            path="/",
            httponly=True,
            samesite="strict",
            secure=False,  # TODO: 启用 HTTPS 后改为 True / Set True when HTTPS is enabled
        )
        return resp


    @app.get("/api/v1/auth/check", include_in_schema=False)
    async def auth_check(request: Request):
        """
        Lightweight endpoint for GUI to verify if the auth cookie is valid.
        No Authorization header needed — reads cookie directly.
        GUI 用来验证 cookie 是否有效的轻量端点。无需 Authorization header，直接读 cookie。
        """
        cookie_token = request.cookies.get("oc_auth_token")
        if not cookie_token:
            raise HTTPException(status_code=401, detail="Not authenticated")
        if not hmac.compare_digest(cookie_token.encode("utf-8"), settings.api_token.encode("utf-8")):
            raise HTTPException(status_code=401, detail="Not authenticated")
        return {"authenticated": True}


    @app.get("/", include_in_schema=False)
    def root_redirect():
        from starlette.responses import RedirectResponse
        return RedirectResponse(url="/console")


    @app.get("/gui", include_in_schema=False)
    def gui_index() -> FileResponse:
        return FileResponse(static_dir / "index.html")


    @app.get("/console", include_in_schema=False)
    def console_index() -> FileResponse:
        """Unified console: Trading Dashboard + OpenClaw + AI Cost sidebar"""
        return FileResponse(static_dir / "console.html")


    @app.get("/trading", include_in_schema=False)
    def trading_dashboard() -> FileResponse:
        """Trading chart dashboard: TradingView Lightweight Charts + signals + strategies"""
        return FileResponse(static_dir / "trading.html")


    @app.get(f"{settings.api_prefix}/system/overview", response_model=ResponseEnvelope[OverviewData])
    def get_system_overview(actor=Depends(_base.current_actor)) -> ResponseEnvelope[OverviewData]:
        snapshot, _ = _base.get_latest_snapshot()
        return _base.envelope_response(snapshot=snapshot, request_id=None, action_result="success", data=OverviewData(**build_overview(snapshot)))


    @app.get(f"{settings.api_prefix}/system/chapter-status", response_model=ResponseEnvelope[dict[str, Any]])
    def get_chapter_status(actor=Depends(_base.current_actor)) -> ResponseEnvelope[dict[str, Any]]:
        snapshot, _ = _base.get_latest_snapshot()
        return _base.envelope_response(snapshot=snapshot, request_id=None, action_result="success", data=snapshot["chapter_status"])


    @app.get(f"{settings.api_prefix}/system/control-plane", response_model=ResponseEnvelope[dict[str, Any]])
    def get_control_plane(actor=Depends(_base.current_actor)) -> ResponseEnvelope[dict[str, Any]]:
        snapshot, _ = _base.get_latest_snapshot()
        return _base.envelope_response(snapshot=snapshot, request_id=None, action_result="success", data=snapshot["control_plane"])


    @app.get(f"{settings.api_prefix}/system/capability-matrix", response_model=ResponseEnvelope[dict[str, Any]])
    def get_capability_matrix(actor=Depends(_base.current_actor)) -> ResponseEnvelope[dict[str, Any]]:
        snapshot, _ = _base.get_latest_snapshot()
        return _base.envelope_response(snapshot=snapshot, request_id=None, action_result="success", data=snapshot["capability_matrix"])


    @app.get(f"{settings.api_prefix}/system/product-families", response_model=ResponseEnvelope[dict[str, Any]])
    def get_product_families(actor=Depends(_base.current_actor)) -> ResponseEnvelope[dict[str, Any]]:
        snapshot, _ = _base.get_latest_snapshot()
        return _base.envelope_response(snapshot=snapshot, request_id=None, action_result="success", data=snapshot["product_family_status"])


    @app.get(f"{settings.api_prefix}/system/business/daily", response_model=ResponseEnvelope[dict[str, Any]])
    def get_business_daily(actor=Depends(_base.current_actor)) -> ResponseEnvelope[dict[str, Any]]:
        snapshot, _ = _base.get_latest_snapshot()
        return _base.envelope_response(snapshot=snapshot, request_id=None, action_result="success", data=snapshot["business_metrics"]["daily"])


    @app.get(f"{settings.api_prefix}/system/health", response_model=ResponseEnvelope[dict[str, Any]])
    def get_health(actor=Depends(_base.current_actor)) -> ResponseEnvelope[dict[str, Any]]:
        snapshot, _ = _base.get_latest_snapshot()
        return _base.envelope_response(snapshot=snapshot, request_id=None, action_result="success", data=snapshot["health_telemetry"])


    @app.get(f"{settings.api_prefix}/system/grafana-health", include_in_schema=False)
    async def grafana_health_proxy(actor=Depends(_base.current_actor)):
        """
        Proxy Grafana health check to avoid browser CORS block.
        代理 Grafana 健康检查，避免浏览器 CORS 拦截。
        """
        import asyncio
        try:
            def _check():
                import urllib.request
                with urllib.request.urlopen("http://localhost:3000/api/health", timeout=3) as resp:
                    import json
                    return json.loads(resp.read().decode())
            data = await asyncio.to_thread(_check)
            return {"action_result": "success", "data": {"ok": True, "version": data.get("version", "?")}}
        except Exception:
            return {"action_result": "success", "data": {"ok": False}}


    @app.get(f"{settings.api_prefix}/system/audit-summary", response_model=ResponseEnvelope[dict[str, Any]])
    def get_audit_summary(actor=Depends(_base.current_actor)) -> ResponseEnvelope[dict[str, Any]]:
        snapshot, _ = _base.get_latest_snapshot()
        data = {
            "latest_control_action_summary": {
                "type": snapshot["audit_context"]["last_control_action_type"],
                "request_id": snapshot["audit_context"]["last_control_action_request_id"],
                "ts_ms": snapshot["audit_context"]["last_control_action_ts_ms"],
                "by": snapshot["audit_context"]["last_control_action_by"],
                "result": snapshot["audit_context"]["last_control_action_result"],
                "reason_codes": snapshot["audit_context"]["last_control_action_reason_codes"],
                "audit_ref": snapshot["audit_context"]["last_control_action_audit_ref"],
            },
            "latest_write_action_summary": {
                "type": snapshot["audit_context"]["last_write_action_type"],
                "request_id": snapshot["audit_context"]["last_write_action_request_id"],
                "ts_ms": snapshot["audit_context"]["last_write_action_ts_ms"],
                "by": snapshot["audit_context"]["last_write_action_by"],
                "result": snapshot["audit_context"]["last_write_action_result"],
                "reason_codes": snapshot["audit_context"]["last_write_action_reason_codes"],
                "audit_ref": snapshot["audit_context"]["last_write_action_audit_ref"],
            },
            "last_state_revision_before": snapshot["audit_context"]["last_state_revision_before"],
            "last_state_revision_after": snapshot["audit_context"]["last_state_revision_after"],
        }
        return _base.envelope_response(snapshot=snapshot, request_id=None, action_result="success", data=data)


    @app.get(f"{settings.api_prefix}/system/source-context", response_model=ResponseEnvelope[dict[str, Any]])
    def get_source_context(actor=Depends(_base.current_actor)) -> ResponseEnvelope[dict[str, Any]]:
        snapshot, source = _base.get_latest_snapshot()
        return _base.envelope_response(snapshot=snapshot, request_id=None, action_result="success", data=source.model_dump(mode="json"))


    # ── Scheduled Restart ────────────────────────────────────────────────────────
    # 计划重启：在指定延迟后重启 uvicorn 进程，可选强制清仓（只平盈利仓位）
    # Scheduled restart: restart uvicorn after a specified delay, optionally
    # closing only profitable paper positions before the restart.

    class ScheduledRestartRequest(BaseModel):
        """Request body for scheduled restart / 计划重启请求体"""
        delay_minutes: int = Field(..., description="Restart delay in minutes (5/10/15/30/60)")
        force_liquidate: bool = Field(False, description="Close profitable paper positions before restart")

        def validate_delay(self) -> None:
            if self.delay_minutes not in (5, 10, 15, 30, 60):
                raise ValueError("delay_minutes must be one of: 5, 10, 15, 30, 60")


    def _close_profitable_paper_positions() -> dict[str, Any]:
        """
        Close paper positions where net PnL (after fees) > 0.
        关闭净盈利（扣除手续费后）的纸盘仓位。

        Returns dict with closed/skipped lists.
        """
        TAKER_FEE_RATE = 0.00055  # Bybit taker fee / Bybit taker 手续费

        try:
            from .phase2_strategy_routes import PAPER_ENGINE, PIPELINE_BRIDGE
        except ImportError:
            return {"closed": [], "skipped": [], "error": "paper engine not available"}

        if PAPER_ENGINE is None:
            return {"closed": [], "skipped": [], "error": "paper engine not initialized"}

        try:
            state = PAPER_ENGINE.get_state()
        except Exception as exc:
            return {"closed": [], "skipped": [], "error": str(exc)}

        positions = state.get("positions", {})
        latest_prices: dict[str, float] = {}
        if PIPELINE_BRIDGE is not None:
            try:
                latest_prices = dict(PIPELINE_BRIDGE._latest_prices)
            except Exception:
                pass

        closed: list[dict] = []
        skipped: list[dict] = []

        for symbol, pos in positions.items():
            qty = pos.get("qty", 0)
            side = pos.get("side", "long")
            entry_price = pos.get("entry_price", 0)
            current_price = latest_prices.get(symbol, 0)

            if qty <= 0 or entry_price <= 0 or current_price <= 0:
                skipped.append({"symbol": symbol, "reason": "missing_price_data"})
                continue

            notional = current_price * qty
            fee_cost = notional * TAKER_FEE_RATE * 2  # open + close taker fees
            raw_pnl = (current_price - entry_price) * qty if side == "long" else (entry_price - current_price) * qty
            net_pnl = raw_pnl - fee_cost

            if net_pnl <= 0:
                skipped.append({"symbol": symbol, "reason": f"would_lose_usd_{-net_pnl:.4f}", "net_pnl": round(net_pnl, 4)})
                continue

            # Close position / 平仓
            close_side = "Sell" if side == "long" else "Buy"
            try:
                PAPER_ENGINE.submit_order(
                    symbol=symbol,
                    side=close_side,
                    order_type="market",
                    qty=qty,
                    market_prices=latest_prices,
                )
                closed.append({"symbol": symbol, "side": side, "qty": qty,
                               "net_pnl": round(net_pnl, 4), "close_price": current_price})
            except Exception as exc:
                skipped.append({"symbol": symbol, "reason": f"submit_error: {exc}"})

        return {"closed": closed, "skipped": skipped, "error": None}


    def _run_restart_in_background(delay_seconds: int) -> None:
        """
        Background thread: sleep then restart the uvicorn process.
        后台线程：等待后重启 uvicorn 进程。

        Writes a temp shell script and executes it in a new session so the
        parent process can die without killing the restart script.
        写入临时 shell 脚本并在新会话中执行，使父进程可以退出而不影响重启脚本。
        """
        import signal
        import subprocess
        import sys

        pid = os.getpid()
        python = sys.executable
        # Reconstruct uvicorn launch command / 重建 uvicorn 启动命令
        work_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # P1-14: Use project logs/ dir instead of /tmp/ to prevent symlink attacks.
        # P1-14 修复：使用项目内 logs/ 目录，防止符号链接攻击。
        script_content = f"""#!/bin/bash
    # OpenClaw scheduled restart script / 计划重启脚本
    sleep {delay_seconds}
    kill {pid} 2>/dev/null
    sleep 3
    cd {work_dir}
    mkdir -p {work_dir}/logs
    nohup {python} -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >> {work_dir}/logs/restart.log 2>&1 &
    echo "Restarted PID=$!" >> {work_dir}/logs/restart.log
    """
        try:
            fd, script_path = tempfile.mkstemp(suffix=".sh", prefix="openclaw_restart_")
            with os.fdopen(fd, "w") as f:
                f.write(script_content)
            os.chmod(script_path, 0o700)
            subprocess.Popen(
                ["bash", script_path],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info("Scheduled restart script launched: delay=%ds pid=%d", delay_seconds, pid)
        except Exception as exc:
            logger.error("Failed to launch restart script: %s", exc)


    @app.post(f"{settings.api_prefix}/system/scheduled-restart")
    def post_scheduled_restart(
        request: ScheduledRestartRequest,
        actor=Depends(_base.current_actor),
    ) -> dict[str, Any]:
        """
        Schedule a server restart after the specified delay.
        在指定延迟后计划服务器重启。

        If force_liquidate=True, closes paper positions where net PnL > 0 immediately.
        Positions that would result in a net loss are left open.
        如果 force_liquidate=True，立即关闭净盈利的纸盘仓位。
        会造成净亏损的仓位保持开放。

        Returns scheduled restart time and liquidation results.
        返回计划重启时间和清仓结果。
        """
        try:
            request.validate_delay()
        except ValueError as exc:
            # Log actual error server-side for debugging; do not expose internals to client
            # 記錄實際錯誤供調試；不向客戶端洩露內部資訊
            logger.debug("validate_delay failed: %s", exc)
            raise HTTPException(status_code=400, detail="Invalid delay parameter")

        liquidation_result: dict[str, Any] = {"closed": [], "skipped": [], "error": None}

        if request.force_liquidate:
            liquidation_result = _close_profitable_paper_positions()

        delay_seconds = request.delay_minutes * 60
        restart_at_ts_ms = int(time.time() * 1000) + (delay_seconds * 1000)

        # Launch background restart / 启动后台重启
        t = threading.Thread(
            target=_run_restart_in_background,
            args=(delay_seconds,),
            daemon=True,
            name=f"scheduled-restart-{request.delay_minutes}m",
        )
        t.start()

        logger.info(
            "Scheduled restart in %d min (force_liquidate=%s) by %s",
            request.delay_minutes, request.force_liquidate,
            actor.get("operator_id", "unknown") if isinstance(actor, dict) else "unknown",
        )

        return {
            "action_result": "scheduled",
            "delay_minutes": request.delay_minutes,
            "restart_at_ts_ms": restart_at_ts_ms,
            "force_liquidate": request.force_liquidate,
            "positions_closed": liquidation_result["closed"],
            "positions_skipped": liquidation_result["skipped"],
            "liquidation_error": liquidation_result.get("error"),
            "message": f"Server will restart in {request.delay_minutes} minute(s).",
        }

    @app.get(f"{settings.api_prefix}/learning/overview", response_model=ResponseEnvelope[LearningOverviewData])
    def get_learning_overview(actor=Depends(_base.current_actor)) -> ResponseEnvelope[LearningOverviewData]:
        snapshot, _ = _base.get_latest_snapshot()
        data = LearningOverviewData(
            summary=snapshot["learning_state"]["observation_summary"],
            experiments=snapshot["learning_state"]["experiments"],
            approval_requirements={"approval_required": snapshot["learning_state"]["experiments"]["approval_required"]},
        )
        return _base.envelope_response(snapshot=snapshot, request_id=None, action_result="success", data=data)


    @app.get(f"{settings.api_prefix}/learning/hypotheses", response_model=ResponseEnvelope[LearningHypothesesData])
    def get_learning_hypotheses(actor=Depends(_base.current_actor)) -> ResponseEnvelope[LearningHypothesesData]:
        snapshot, _ = _base.get_latest_snapshot()
        data = LearningHypothesesData(
            hypotheses=snapshot["learning_state"]["records"]["hypotheses"],
            experiments=snapshot["learning_state"]["records"]["experiments"],
            approval_requirements={"approval_required": snapshot["learning_state"]["experiments"]["approval_required"]},
        )
        return _base.envelope_response(snapshot=snapshot, request_id=None, action_result="success", data=data)


    # ═══════════════════════════════════════════════════════════════════════════════
    # L 章路由 / L-Chapter Routes
    #
    # 三类端点：
    # 1. GET 查询端点：观察流 / 实验队列 / 净 PnL 仪表盘
    # 2. POST 录入端点：观察 / 经验 / 假设 / 实验 / 周期快照
    # 3. POST 管理端点：假设审批 / 实验审批 / 实验完成
    #
    # Three categories of endpoints:
    # 1. GET queries: observation feed / experiment queue / net PnL dashboard
    # 2. POST inputs: observation / lesson / hypothesis / experiment / period snapshot
    # 3. POST management: hypothesis verdict / experiment approval / experiment completion
    # ═══════════════════════════════════════════════════════════════════════════════


    @app.get(f"{settings.api_prefix}/learning/feed", response_model=ResponseEnvelope[LearningFeedData])
    def get_learning_feed(actor=Depends(_base.current_actor)) -> ResponseEnvelope[LearningFeedData]:
        """
        学习观察流 / Learning observation feed.

        返回最近的观察和经验教训列表，以及摘要统计。
        Returns recent observations and lessons, plus summary statistics.
        """
        snapshot, _ = _base.get_latest_snapshot()
        feed = build_learning_feed(snapshot)
        return _base.envelope_response(snapshot=snapshot, request_id=None, action_result="success", data=LearningFeedData(**feed))


    @app.get(f"{settings.api_prefix}/learning/experiments", response_model=ResponseEnvelope[LearningExperimentsData])
    def get_learning_experiments_list(actor=Depends(_base.current_actor)) -> ResponseEnvelope[LearningExperimentsData]:
        """
        实验队列完整视图 / Complete experiment queue view.

        包含所有实验和关联假设，以及待审批数量。
        Includes all experiments and linked hypotheses, plus pending approval count.
        """
        snapshot, _ = _base.get_latest_snapshot()
        data = build_learning_experiments(snapshot)
        return _base.envelope_response(snapshot=snapshot, request_id=None, action_result="success", data=LearningExperimentsData(**data))


    @app.get(f"{settings.api_prefix}/learning/net-pnl", response_model=ResponseEnvelope[NetPnLDashboardData])
    def get_net_pnl_dashboard(actor=Depends(_base.current_actor)) -> ResponseEnvelope[NetPnLDashboardData]:
        """
        含所有成本分解的净 PnL 仪表盘 / Net PnL dashboard with full cost breakdown.

        整合每日 PnL、成本分类分解、趋势和最近录入条目。
        Integrates daily PnL, cost category breakdown, trends, and recent entries.
        """
        snapshot, _ = _base.get_latest_snapshot()
        dashboard = build_net_pnl_dashboard(snapshot)
        return _base.envelope_response(snapshot=snapshot, request_id=None, action_result="success", data=NetPnLDashboardData(**dashboard))


    # ── L 章录入路由 / L-Chapter Input Routes ─────────────────────────────────────


    @app.post(f"{settings.api_prefix}/input/observation", response_model=ResponseEnvelope[ObservationAcceptedData])
    def post_input_observation(envelope: RequestEnvelope, actor=Depends(_base.current_actor)) -> ResponseEnvelope[ObservationAcceptedData]:
        """
        录入观察记录 / Record an observation to the observation feed.

        payload 字段 / payload fields:
        - title: str            观察标题（必填）/ Observation title (required)
        - detail: str           观察详情（必填）/ Observation detail (required)
        - category: str         类别（必填）/ Category (required): market/execution/cost/system/strategy/other
        - confidence_level: str 置信度（必填）/ Confidence (required): fact/inference/hypothesis
        - related_hypothesis_id: str  关联假设 ID（可选）/ Related hypothesis ID (optional)
        - tags: list[str]       标签（可选）/ Tags (optional)
        """
        result, action_result = apply_learning_observation(envelope, actor)
        return _base.envelope_response(
            snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result,
            data=ObservationAcceptedData(**result["data"]), audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )


    @app.post(f"{settings.api_prefix}/input/lesson", response_model=ResponseEnvelope[LessonAcceptedData])
    def post_input_lesson(envelope: RequestEnvelope, actor=Depends(_base.current_actor)) -> ResponseEnvelope[LessonAcceptedData]:
        """
        录入经验教训 / Record a lesson to the lessons memory.

        payload 字段 / payload fields:
        - title: str            经验标题（必填）/ Lesson title (required)
        - detail: str           经验详情（必填）/ Lesson detail (required)
        - category: str         类别（必填）/ Category (required): market_pattern/cost_insight/execution_quality/strategy/system/other
        - confidence_level: str 置信度（必填）/ Confidence (required): fact/inference/hypothesis
        """
        result, action_result = apply_learning_lesson(envelope, actor)
        return _base.envelope_response(
            snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result,
            data=LessonAcceptedData(**result["data"]), audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )


    @app.post(f"{settings.api_prefix}/input/hypothesis", response_model=ResponseEnvelope[HypothesisAcceptedData])
    def post_input_hypothesis(envelope: RequestEnvelope, actor=Depends(_base.current_actor)) -> ResponseEnvelope[HypothesisAcceptedData]:
        """
        提出假设 / Propose a hypothesis.

        原则 8：confidence_level 自动设为 "hypothesis"。
        Principle 8: confidence_level is automatically set to "hypothesis".

        payload 字段 / payload fields:
        - title: str                假设标题（必填）/ Title (required)
        - description: str          假设描述（必填）/ Description (required)
        - testable_prediction: str  可检验预测（必填）/ Testable prediction (required)
        """
        result, action_result = apply_learning_hypothesis(envelope, actor)
        return _base.envelope_response(
            snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result,
            data=HypothesisAcceptedData(**result["data"]), audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )


    @app.post(f"{settings.api_prefix}/input/experiment", response_model=ResponseEnvelope[ExperimentAcceptedData])
    def post_input_experiment(envelope: RequestEnvelope, actor=Depends(_base.current_actor)) -> ResponseEnvelope[ExperimentAcceptedData]:
        """
        提出实验 / Propose an experiment to validate a hypothesis.

        payload 字段 / payload fields:
        - hypothesis_id: str    关联假设 ID（必填）/ Linked hypothesis ID (required)
        - title: str            实验标题（必填）/ Title (required)
        - description: str      实验描述（必填）/ Description (required)
        - method: str           实验方法（必填）/ Method (required)
        - success_criteria: str 成功标准（必填）/ Success criteria (required)
        """
        result, action_result = apply_learning_experiment(envelope, actor)
        return _base.envelope_response(
            snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result,
            data=ExperimentAcceptedData(**result["data"]), audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )


    # ── L 章管理路由 / L-Chapter Management Routes ───────────────────────────────


    @app.post(
        f"{settings.api_prefix}/learning/hypothesis/{{hypothesis_id}}/verdict",
        response_model=ResponseEnvelope[HypothesisVerdictData],
    )
    def post_hypothesis_verdict(
        hypothesis_id: str, envelope: RequestEnvelope, actor=Depends(_base.current_actor)
    ) -> ResponseEnvelope[HypothesisVerdictData]:
        """
        Operator 审批假设 / Operator renders verdict on a hypothesis.

        payload 字段 / payload fields:
        - verdict: str  判定（必填）/ Verdict (required): approved / rejected / archived
        - reason: str   理由（可选）/ Reason (optional)
        """
        result, action_result = apply_hypothesis_verdict(envelope, actor, hypothesis_id)
        return _base.envelope_response(
            snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result,
            data=HypothesisVerdictData(**result["data"]), audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )


    @app.post(
        f"{settings.api_prefix}/learning/experiment/{{experiment_id}}/approve",
        response_model=ResponseEnvelope[ExperimentApprovalData],
    )
    def post_experiment_approval(
        experiment_id: str, envelope: RequestEnvelope, actor=Depends(_base.current_actor)
    ) -> ResponseEnvelope[ExperimentApprovalData]:
        """
        Operator 审批实验 / Operator approves or rejects an experiment.

        payload 字段 / payload fields:
        - action: str   审批动作（必填）/ Action (required): approved / rejected
        - reason: str   理由（可选）/ Reason (optional)
        """
        result, action_result = apply_experiment_approval(envelope, actor, experiment_id)
        return _base.envelope_response(
            snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result,
            data=ExperimentApprovalData(**result["data"]), audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )


    @app.post(
        f"{settings.api_prefix}/learning/experiment/{{experiment_id}}/complete",
        response_model=ResponseEnvelope[ExperimentCompletionData],
    )
    def post_experiment_completion(
        experiment_id: str, envelope: RequestEnvelope, actor=Depends(_base.current_actor)
    ) -> ResponseEnvelope[ExperimentCompletionData]:
        """
        标记实验完成 / Mark an experiment as completed.

        payload 字段 / payload fields:
        - result_summary: str           实验结论（必填）/ Conclusion (required)
        - result_confidence_level: str  结论置信度（必填）/ Confidence (required): fact/inference/hypothesis
        """
        result, action_result = apply_experiment_completion(envelope, actor, experiment_id)
        return _base.envelope_response(
            snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result,
            data=ExperimentCompletionData(**result["data"]), audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )


    @app.post(f"{settings.api_prefix}/input/pnl-period-snapshot", response_model=ResponseEnvelope[InputAcceptedData])
    def post_pnl_period_snapshot(envelope: RequestEnvelope, actor=Depends(_base.current_actor)) -> ResponseEnvelope[InputAcceptedData]:
        """
        保存当前经营指标为周期快照 / Save current business metrics as a period snapshot.

        payload 字段 / payload fields:
        - period_label: str  周期标签（必填）/ Period label (required), e.g. "2026-03-26"
        """
        result, action_result = apply_pnl_period_snapshot(envelope, actor)
        return _base.envelope_response(
            snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result,
            data=InputAcceptedData(**result["data"]), audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )


    @app.post(f"{settings.api_prefix}/control/recheck/j-canonical", response_model=ResponseEnvelope[RecheckResultData])
    def post_j_canonical(envelope: RequestEnvelope, actor=Depends(_base.current_actor)) -> ResponseEnvelope[RecheckResultData]:
        result, action_result = perform_recheck(envelope, actor, "J", "canonical")
        return _base.envelope_response(snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result, data=RecheckResultData(**result["data"]), audit_ref=result["audit_ref"], reason_codes=["replayed_request"] if action_result == "replayed" else [])


    @app.post(f"{settings.api_prefix}/control/recheck/k-canonical", response_model=ResponseEnvelope[RecheckResultData])
    def post_k_canonical(envelope: RequestEnvelope, actor=Depends(_base.current_actor)) -> ResponseEnvelope[RecheckResultData]:
        result, action_result = perform_recheck(envelope, actor, "K", "canonical")
        return _base.envelope_response(snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result, data=RecheckResultData(**result["data"]), audit_ref=result["audit_ref"], reason_codes=["replayed_request"] if action_result == "replayed" else [])


    @app.post(f"{settings.api_prefix}/control/recheck/j-closeout", response_model=ResponseEnvelope[RecheckResultData])
    def post_j_closeout(envelope: RequestEnvelope, actor=Depends(_base.current_actor)) -> ResponseEnvelope[RecheckResultData]:
        result, action_result = perform_recheck(envelope, actor, "J", "closeout")
        return _base.envelope_response(snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result, data=RecheckResultData(**result["data"]), audit_ref=result["audit_ref"], reason_codes=["replayed_request"] if action_result == "replayed" else [])


    @app.post(f"{settings.api_prefix}/control/recheck/k-closeout", response_model=ResponseEnvelope[RecheckResultData])
    def post_k_closeout(envelope: RequestEnvelope, actor=Depends(_base.current_actor)) -> ResponseEnvelope[RecheckResultData]:
        result, action_result = perform_recheck(envelope, actor, "K", "closeout")
        return _base.envelope_response(snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result, data=RecheckResultData(**result["data"]), audit_ref=result["audit_ref"], reason_codes=["replayed_request"] if action_result == "replayed" else [])


    @app.post(f"{settings.api_prefix}/control/demo/validate", response_model=ResponseEnvelope[DemoValidateData])
    def post_demo_validate(envelope: RequestEnvelope, actor=Depends(_base.current_actor)) -> ResponseEnvelope[DemoValidateData]:
        result, action_result = perform_validate(envelope, actor)
        return _base.envelope_response(snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result, data=DemoValidateData(**result["data"]), audit_ref=result["audit_ref"], reason_codes=["replayed_request"] if action_result == "replayed" else [])


    @app.post(f"{settings.api_prefix}/control/demo/arm", response_model=ResponseEnvelope[DemoTransitionData])
    def post_demo_arm(envelope: RequestEnvelope, actor=Depends(_base.current_actor)) -> ResponseEnvelope[DemoTransitionData]:
        result, action_result = perform_demo_transition(envelope, actor, "arm")
        return _base.envelope_response(snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result, data=DemoTransitionData(**result["data"]), audit_ref=result["audit_ref"], reason_codes=["replayed_request"] if action_result == "replayed" else [])


    @app.post(f"{settings.api_prefix}/control/demo/enable", response_model=ResponseEnvelope[DemoTransitionData])
    def post_demo_enable(envelope: RequestEnvelope, actor=Depends(_base.current_actor)) -> ResponseEnvelope[DemoTransitionData]:
        result, action_result = perform_demo_transition(envelope, actor, "enable")
        return _base.envelope_response(snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result, data=DemoTransitionData(**result["data"]), audit_ref=result["audit_ref"], reason_codes=["replayed_request"] if action_result == "replayed" else [])


    @app.post(f"{settings.api_prefix}/control/demo/relock", response_model=ResponseEnvelope[DemoTransitionData])
    def post_demo_relock(envelope: RequestEnvelope, actor=Depends(_base.current_actor)) -> ResponseEnvelope[DemoTransitionData]:
        result, action_result = perform_demo_transition(envelope, actor, "relock")
        return _base.envelope_response(snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result, data=DemoTransitionData(**result["data"]), audit_ref=result["audit_ref"], reason_codes=["replayed_request"] if action_result == "replayed" else [])


    @app.post(f"{settings.api_prefix}/control/safe-recheck-bundle", response_model=ResponseEnvelope[SafeBundleData])
    def post_safe_bundle(envelope: RequestEnvelope, actor=Depends(_base.current_actor)) -> ResponseEnvelope[SafeBundleData]:
        result, action_result = perform_safe_bundle(envelope, actor)
        return _base.envelope_response(snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result, data=SafeBundleData(**result["data"]), audit_ref=result["audit_ref"], reason_codes=["replayed_request"] if action_result == "replayed" else [])


    @app.post(f"{settings.api_prefix}/input/cost", response_model=ResponseEnvelope[InputAcceptedData])
    def post_input_cost(envelope: RequestEnvelope, actor=Depends(_base.current_actor)) -> ResponseEnvelope[InputAcceptedData]:
        result, action_result = apply_input_action(envelope, actor, "cost")
        return _base.envelope_response(snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result, data=InputAcceptedData(**result["data"]), audit_ref=result["audit_ref"], reason_codes=["replayed_request"] if action_result == "replayed" else [])


    @app.post(f"{settings.api_prefix}/input/event", response_model=ResponseEnvelope[InputAcceptedData])
    def post_input_event(envelope: RequestEnvelope, actor=Depends(_base.current_actor)) -> ResponseEnvelope[InputAcceptedData]:
        result, action_result = apply_input_action(envelope, actor, "event")
        return _base.envelope_response(snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result, data=InputAcceptedData(**result["data"]), audit_ref=result["audit_ref"], reason_codes=["replayed_request"] if action_result == "replayed" else [])


    @app.post(f"{settings.api_prefix}/input/manual-note", response_model=ResponseEnvelope[InputAcceptedData])
    def post_input_note(envelope: RequestEnvelope, actor=Depends(_base.current_actor)) -> ResponseEnvelope[InputAcceptedData]:
        result, action_result = apply_input_action(envelope, actor, "manual-note")
        return _base.envelope_response(snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result, data=InputAcceptedData(**result["data"]), audit_ref=result["audit_ref"], reason_codes=["replayed_request"] if action_result == "replayed" else [])


    @app.post(f"{settings.api_prefix}/input/config-change", response_model=ResponseEnvelope[ConfigChangeAcceptedData])
    def post_config_change(envelope: RequestEnvelope, actor=Depends(_base.current_actor)) -> ResponseEnvelope[ConfigChangeAcceptedData]:
        result, action_result = apply_config_change(envelope, actor)
        return _base.envelope_response(snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result, data=ConfigChangeAcceptedData(**result["data"]), audit_ref=result["audit_ref"], reason_codes=["replayed_request"] if action_result == "replayed" else [])


    # ── 产品族配置写接口路由 / Product Family Config Write Routes ─────────────────


    @app.post(
        f"{settings.api_prefix}/control/product-family/{{family}}/config",
        response_model=ResponseEnvelope[ProductFamilyConfigData],
    )
    def post_product_family_config(
        family: str,
        envelope: RequestEnvelope,
        actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[ProductFamilyConfigData]:
        """
        修改指定产品族的控制配置 / Modify control configuration for a specific product family.

        payload 支持字段 / Supported payload fields:
        - enabled_switch: bool      是否启用该产品族 / Enable this product family
        - visibility_switch: bool   是否在 GUI 可见 / Make visible in GUI
        - mode_switch: str          模式切换（允许 disabled/observe_only/shadow_only/demo_reserved）
                                    Mode switch (only allows disabled/observe_only/shadow_only)
        - action_permissions: dict  每个动作的开关，例如 {"new_order": false, "cancel": false}
                                    Per-action switches, e.g. {"new_order": false, "cancel": false}

        安全 / Safety: 不能设置为 live 相关模式。需要 input:config scope。
        Cannot set to live-related modes. Requires input:config scope.
        """
        result, action_result = apply_product_family_config(envelope, actor, family)
        return _base.envelope_response(
            snapshot=result["snapshot"],
            request_id=envelope.request_id,
            action_result=action_result,
            data=ProductFamilyConfigData(**result["data"]),
            audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )


    # ── 经营摘要路由 / Business Summary Route ────────────────────────────────────


    @app.get(
        f"{settings.api_prefix}/system/business/summary",
        response_model=ResponseEnvelope[BusinessSummaryData],
    )
    def get_business_summary(actor=Depends(_base.current_actor)) -> ResponseEnvelope[BusinessSummaryData]:
        """
        经营与收益完整摘要 / Complete business and income summary.

        比 /system/business/daily 更完整：包含历史条目列表和按类别成本分解。
        Richer than /system/business/daily: includes entry history and category-level cost breakdown.
        """
        snapshot, _ = _base.get_latest_snapshot()
        summary = build_business_summary(snapshot)
        return _base.envelope_response(
            snapshot=snapshot,
            request_id=None,
            action_result="success",
            data=BusinessSummaryData(**summary),
        )


    # ── PnL 条目录入路由 / PnL Entry Input Route ─────────────────────────────────


    @app.post(f"{settings.api_prefix}/input/pnl-entry", response_model=ResponseEnvelope[PnLEntryData])
    def post_pnl_entry(envelope: RequestEnvelope, actor=Depends(_base.current_actor)) -> ResponseEnvelope[PnLEntryData]:
        """
        录入 PnL 更新条目 / Record a PnL update entry.

        用于手动录入已实现盈亏 / 未实现盈亏更新，自动刷新每日经营摘要中的 PnL 指标。
        Used to manually record realized/unrealized PnL updates.
        Automatically refreshes PnL metrics in the daily business summary.

        payload 字段 / payload fields:
        - entry_type: str          条目类型 / Entry type
        - realized_pnl: float      累计增量（已实现）/ Cumulative delta (realized)
        - unrealized_pnl: float    当前快照值（未实现）/ Current snapshot value (unrealized)
        - symbol: str              涉及标的 / Symbol involved (optional)
        - note: str                备注 / Note (optional)
        - category: str            分类（用于 cost_breakdown）/ Category for cost_breakdown (optional)
        """
        result, action_result = apply_pnl_entry(envelope, actor)
        return _base.envelope_response(
            snapshot=result["snapshot"],
            request_id=envelope.request_id,
            action_result=action_result,
            data=PnLEntryData(**result["data"]),
            audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )


    # ═══════════════════════════════════════════════════════════════════════════════
    # L 章自动学习管线路由 / L-Chapter Auto Learning Pipeline Routes
    #
    # 三类端点：
    # 1. POST 扫描端点：触发自动观察/经验/假设生成
    # 2. GET 审核队列：获取待审核和已审核的审核包
    # 3. POST 审核决策：对审核包做出批准/拒绝/搁置/询问AI 决定
    #
    # Three categories:
    # 1. POST scan: trigger auto observation/lesson/hypothesis generation
    # 2. GET review queue: pending and decided review packets
    # 3. POST review decision: approve/reject/defer/ask-ai on review packets
    # ═══════════════════════════════════════════════════════════════════════════════


    @app.post(
        f"{settings.api_prefix}/learning/auto/scan-observations",
        response_model=ResponseEnvelope[AutoGenerationResultData],
    )
    def post_auto_scan_observations(
        envelope: RequestEnvelope, actor=Depends(_base.current_actor)
    ) -> ResponseEnvelope[AutoGenerationResultData]:
        """
        扫描系统状态并自动生成观察审核包 / Scan system state and auto-generate observation review packets.

        检查健康门控、AI 成本、数据新鲜度、PnL 变化等，
        将发现打包为简单易懂的审核包供 Operator 审批。
        """
        result, action_result = apply_auto_generate(envelope, actor, "observations")
        return _base.envelope_response(
            snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result,
            data=AutoGenerationResultData(**result["data"]), audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )


    @app.post(
        f"{settings.api_prefix}/learning/auto/scan-lessons",
        response_model=ResponseEnvelope[AutoGenerationResultData],
    )
    def post_auto_scan_lessons(
        envelope: RequestEnvelope, actor=Depends(_base.current_actor)
    ) -> ResponseEnvelope[AutoGenerationResultData]:
        """
        从累积观察中自动提取经验审核包 / Auto-extract lesson review packets from accumulated observations.

        检测同一类别是否出现多次观察，如果有规律性，
        建议总结为经验（需要 Operator 审批确认）。
        """
        result, action_result = apply_auto_generate(envelope, actor, "lessons")
        return _base.envelope_response(
            snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result,
            data=AutoGenerationResultData(**result["data"]), audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )


    @app.post(
        f"{settings.api_prefix}/learning/auto/scan-hypotheses",
        response_model=ResponseEnvelope[AutoGenerationResultData],
    )
    def post_auto_scan_hypotheses(
        envelope: RequestEnvelope, actor=Depends(_base.current_actor)
    ) -> ResponseEnvelope[AutoGenerationResultData]:
        """
        从累积经验中自动提议假设审核包 / Auto-propose hypothesis review packets from accumulated lessons.

        对于可操作但尚未关联假设的经验，自动生成假设提议。
        """
        result, action_result = apply_auto_generate(envelope, actor, "hypotheses")
        return _base.envelope_response(
            snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result,
            data=AutoGenerationResultData(**result["data"]), audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )


    @app.get(
        f"{settings.api_prefix}/learning/review-queue",
        response_model=ResponseEnvelope[ReviewQueueData],
    )
    def get_review_queue_view(actor=Depends(_base.current_actor)) -> ResponseEnvelope[ReviewQueueData]:
        """
        获取审核队列 / Get review queue.

        返回待审核的审核包和最近已决定的审核包，以及管线摘要。
        Returns pending and recently decided review packets, plus pipeline summary.
        """
        snapshot, _ = _base.get_latest_snapshot()
        data = build_review_queue(snapshot)
        return _base.envelope_response(
            snapshot=snapshot, request_id=None, action_result="success",
            data=ReviewQueueData(**data),
        )


    @app.post(
        f"{settings.api_prefix}/learning/review/{{packet_id}}/decide",
        response_model=ResponseEnvelope[ReviewDecisionData],
    )
    def post_review_decide(
        packet_id: str, envelope: RequestEnvelope, actor=Depends(_base.current_actor)
    ) -> ResponseEnvelope[ReviewDecisionData]:
        """
        对审核包做出决定 / Decide on a review packet.

        payload 字段 / payload fields:
        - decision: str   "approve" | "reject" | "defer" | "ask_ai"
        - reason: str     决定理由（可选）/ Decision reason (optional)

        批准后系统自动创建对应的正式记录。
        Upon approval, system auto-creates the corresponding record.
        """
        result, action_result = apply_review_decision(envelope, actor, packet_id)
        return _base.envelope_response(
            snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result,
            data=ReviewDecisionData(**result["data"]), audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )


    @app.post(
        f"{settings.api_prefix}/learning/review/{{packet_id}}/ai-consult",
        response_model=ResponseEnvelope[AIConsultationResultData],
    )
    def post_review_ai_consult(
        packet_id: str, envelope: RequestEnvelope, actor=Depends(_base.current_actor)
    ) -> ResponseEnvelope[AIConsultationResultData]:
        """
        [DEPRECATED] 对审核包执行 AI 咨询（Learning Cockpit stub，已廢棄）。
        [DEPRECATED] AI consultation on review packet (Learning Cockpit stub, deprecated).

        此端點是 Learning Cockpit 審核隊列的占位符，非現有 AI 管線。
        This endpoint is a stub for the Learning Cockpit Review Queue, not the active AI pipeline.
        請改用 /phase2/strategist/intel-log 查看策略師 AI 決策記錄。
        Use /phase2/strategist/intel-log for Strategist AI pipeline decisions instead.

        回傳值中包含 deprecation_notice 字段提示遷移。
        Response includes a deprecation_notice field to guide migration.
        """
        result, action_result = apply_ai_consultation(envelope, actor, packet_id)
        return _base.envelope_response(
            snapshot=result["snapshot"], request_id=None, action_result=action_result,
            data=AIConsultationResultData(**result["data"]),
        )

