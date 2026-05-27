from __future__ import annotations

"""
MODULE_NOTE (中文):
  控制 API 核心單例與設定模組（Wave A-D 重構後，從 ~5265 行瘦身至 ~420 行）。
  保留項目：settings 單例 + 依賴 settings 的函數（build_authenticated_actor /
  build_source_context / get_latest_snapshot / current_actor / envelope_response）+
  FastAPI app 創建 + 中間件 + re-export 向後兼容符號。
  業務邏輯已拆至：control_ops / pnl_ops / learning_ops / legacy_routes。

  ★ 多個測試依賴 importlib.reload(main_legacy) 重建 Settings，因此 settings 單例
  和所有直接引用 settings 的函數必須留在本文件。

MODULE_NOTE (English):
  Control API core singletons and settings module (slimmed from ~5265 to ~420 lines
  after Wave A-D refactoring). Retains: settings singleton + settings-dependent
  functions (build_authenticated_actor / build_source_context / get_latest_snapshot /
  current_actor / envelope_response) + FastAPI app creation + middleware + re-export
  backward-compatible symbols. Business logic extracted to: control_ops / pnl_ops /
  learning_ops / legacy_routes.

  ★ Multiple tests rely on importlib.reload(main_legacy) to recreate Settings,
  so the settings singleton and all functions directly referencing it must remain here.

Safety invariant:
  execution_state remains "disabled" and live_execution_allowed remains False
  by default. All execution guards from the active main.py apply here as well.
"""

import hmac
import logging
import os
import re
import time

logger = logging.getLogger(__name__)
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.exceptions import HTTPException as StarletteHTTPException


# ── Wave B re-exports: auth (Settings class + credentials + AuthenticatedActor) ──
# 從 auth.py 重新導出認證相關類和函數，保持向後兼容。
# ★ settings 單例和依賴它的函數留在本文件（reload 安全）。
from .auth import (  # noqa: F401
    AuthenticatedActor,
    Settings,
    _AUTH_CREDENTIALS,
    _LOGIN_FAIL_MAX_IPS,
    _LOGIN_LOCKOUT_WINDOW,
    _LOGIN_MAX_FAILURES,
    _load_auth_credentials,
    _login_fail_counts,
    _login_fail_lock,
    _resolve_api_token,
    _split_csv,
    audit_actor_id,
    require_operator_role,
    require_scope,
    require_scope_and_operator,
    require_scope_and_identity,
    verify_operator_identity,
)

settings = Settings()

# ── Wave A re-exports: state_models (type aliases + Pydantic models) ─────────
# 從 state_models.py 重新導出所有類型別名和模型，保持向後兼容。
# Re-export all type aliases and models from state_models.py for backward compat.
from .state_models import (  # noqa: F401
    ActionResult,
    AIConsultationResultData,
    AutoGenerationResultData,
    BusinessSummaryData,
    CompletenessState,
    ConfigChangeAcceptedData,
    ConnectionState,
    DemoState,
    DemoTransitionData,
    DemoValidateData,
    EffectiveRiskEnvelopeState,
    ExperimentAcceptedData,
    ExperimentApprovalData,
    ExperimentCompletionData,
    GateState,
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
    RuntimeConnectionState,
    SafeBundleData,
    SafeBundleStepResult,
    SourceContext,
    T,
)



# NOTE: All Pydantic model classes (RequestEnvelope through AIConsultationResultData)
# have been moved to state_models.py and re-exported above.
# 注意：所有 Pydantic 模型類已移至 state_models.py，上方已重新導出。


# ── Wave A re-exports: state_compiler (constants + compile functions) ─────────
# 從 state_compiler.py 重新導出所有常量和編譯函數，保持向後兼容。
# Re-export all constants and compile functions from state_compiler.py for backward compat.
from .state_compiler import (  # noqa: F401
    ACTION_NAMES,
    AUTO_SCAN_TYPES,
    CONFIDENCE_LEVELS,
    CONFIG_CHANGE_WHITELIST,
    EXPERIMENT_APPROVAL_ACTIONS,
    HYPOTHESIS_VERDICT_ACTIONS,
    LESSON_CATEGORIES,
    OBSERVATION_CATEGORIES,
    PRODUCT_FAMILIES,
    REVIEW_DECISION_ACTIONS,
    _COMPILE_STATE_SIG_CACHE,
    _MAX_TEXT_LONG,
    _MAX_TEXT_SHORT,
    _compile_demo_gate_states,
    _compile_effective_action_permissions,
    _compile_effective_risk_envelope_state,
    _compile_for_response,
    _compile_global_capability_state,
    _compile_global_execution_authority_state,
    _compile_global_mode_state,
    _compile_global_stage_label,
    _compile_learning_derived,
    _compile_product_family_derived,
    _do_compile_core,
    _permission_block,
    mark_compile_dirty,
    _validate_text_length,
    build_snapshot_id,
    compile_state,
    deep_set,
    now_ms,
)

# ── Wave A re-exports: state_store (JsonStateStore + build_default_state) ─────
# 從 state_store.py 重新導出存儲類和默認狀態構建器。
# Re-export store class and default state builder from state_store.py.
from .state_store import JsonStateStore, build_default_state  # noqa: F401

STORE = JsonStateStore(settings.state_file_path)

# ── Wave B re-exports: state_helpers (state operation helpers) ────────────────
# 從 state_helpers.py 重新導出狀態操作輔助函數，保持向後兼容。
# ★ build_source_context / envelope_response / get_latest_snapshot 留在本文件。
from .state_helpers import (  # noqa: F401
    _IDEMPOTENCY_MAX_ENTRIES,
    _IDEMPOTENCY_TTL_MS,
    _assert_previous_state,
    _assert_revision,
    _blocked,
    _bump_revision,
    _check_idempotency,
    _cleanup_idempotency_cache,
    _store_idempotent_response,
    _write_audit_fields,
    ensure_source_is_usable,
    request_fingerprint,
)

# ── Wave C re-exports: control_ops (control plane business logic) ──
# 從 control_ops.py 重新導出控制面板業務邏輯函數，保持向後兼容。
# Re-export control plane business logic from control_ops.py for backward compat.
from .control_ops import (  # noqa: F401
    ALLOWED_MODE_SWITCHES,
    apply_config_change,
    apply_input_action,
    apply_product_family_config,
    build_overview,
    perform_demo_transition,
    perform_recheck,
    perform_safe_bundle,
    perform_validate,
)

# ── Wave C re-exports: pnl_ops (PnL and business metrics) ──
# 從 pnl_ops.py 重新導出 PnL 和經營指標函數，保持向後兼容。
# Re-export PnL and business metrics functions from pnl_ops.py for backward compat.
from .pnl_ops import (  # noqa: F401
    _MAX_RECENT_ENTRIES,
    apply_pnl_entry,
    apply_pnl_period_snapshot,
    build_business_summary,
    build_net_pnl_dashboard,
)

# ── Wave C re-exports: learning_ops (learning system operations) ──
# 從 learning_ops.py 重新導出學習系統操作函數，保持向後兼容。
# Re-export learning system operations from learning_ops.py for backward compat.
# ★ 學習系統函數不再從此處 re-export（消除循環 import）。
# ★ Learning system functions no longer re-exported here (eliminates circular import).
# 消費者應直接 import learning_ops / learning_records / learning_auto_pipeline / learning_queries。
# Consumers should import from learning_ops / learning_records / learning_auto_pipeline / learning_queries directly.




def build_authenticated_actor() -> AuthenticatedActor:
    return AuthenticatedActor(
        actor_id=settings.auth_actor_id,
        actor_type=settings.auth_actor_type,
        roles=set(settings.auth_roles),
        scopes=set(settings.auth_scopes),
    )


def build_source_context(snapshot: dict[str, Any]) -> SourceContext:
    execution_name = settings.execution_connector_name
    return SourceContext(
        readonly_connector_name=settings.readonly_connector_name,
        readonly_connector_role="fact_source",
        readonly_connector_scope="private_readonly",
        execution_connector_name=execution_name,
        execution_connector_role="execution_source_reserved",
        execution_connector_scope="private_execution" if execution_name else "not_attached",
        connector_role_separation_ok=(execution_name is None or execution_name != settings.readonly_connector_name),
        rest_private_connection_state=settings.rest_private_connection_state,
        ws_private_connection_state=settings.ws_private_connection_state,
        runtime_connection_state=settings.runtime_connection_state,
        account_fact_completeness_state=settings.account_fact_completeness_state,
        source_snapshot_completeness_state=settings.source_snapshot_completeness_state,
        pinned_runtime_snapshot_id=f"runtime:{snapshot['meta']['snapshot_id']}",
        pinned_runtime_snapshot_ts_ms=snapshot["meta"]["snapshot_ts_ms"],
    )

def get_latest_snapshot() -> tuple[dict[str, Any], SourceContext]:
    snapshot = STORE.read()
    return snapshot, build_source_context(snapshot)





app = FastAPI(
    title=settings.service_name,
    version=settings.api_version,
    description="OpenClaw / Bybit Control API + GUI MVP",
)

# ── CORS 中间件 / CORS middleware ─────────────────────────────────────────────
# 默认仅允许同源访问；部署时通过 OPENCLAW_CORS_ORIGINS 设置允许的前端源
# Default: same-origin only. Set OPENCLAW_CORS_ORIGINS for deployment.
_cors_origins = os.getenv("OPENCLAW_CORS_ORIGINS", "").strip()
_cors_origin_list: list[str] = _cors_origins.split(",") if _cors_origins else []

# 安全校验：allow_credentials=True 时不允许通配符 "*"，否则浏览器会拒绝且存在安全风险
# Security validation: wildcard "*" with allow_credentials=True is forbidden by CORS spec
# and poses a credential-leaking risk. Remove "*" and log a warning at startup. (APR01-HIGH-1)
if "*" in _cors_origin_list:
    _cors_origin_list = [o for o in _cors_origin_list if o != "*"]
    logger.warning(
        "CORS: removed wildcard '*' from allow_origins because allow_credentials=True. "
        "Wildcard + credentials is forbidden by the CORS specification. "
        "Remaining origins: %s",
        _cors_origin_list or "(none — same-origin only)",
    )

# Security rationale for allow_credentials=True with dynamic origins:
# HttpOnly cookies carry the session token (Batch 5+6). The browser enforces
# that credentials are only sent to origins listed in Access-Control-Allow-Origin,
# so we MUST enumerate explicit origins — never "*". The wildcard strip above
# guarantees this invariant at startup.
# 安全说明：allow_credentials=True 配合动态来源列表确保 HttpOnly cookie
# 仅发送到白名单来源，浏览器层面强制执行 CORS 限制。
logger.info(
    "CORS: configured allow_origins=%s (credentials=True, methods=GET/POST)",
    _cors_origin_list or "(none — same-origin only)",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

# ── 速率限制 / Rate limiting ──────────────────────────────────────────────────
# 默认限制：每 IP 120 次/分钟（可通过 OPENCLAW_RATE_LIMIT 覆盖）
# Default: 120 requests/minute per IP (overridable via OPENCLAW_RATE_LIMIT)
# 登录端点单独限制为 5 次/分钟 + IP 锁定，防止暴力破解（P1-8 修复）
# Login endpoint separately capped at 5/minute + IP lockout to prevent brute-force (P1-8 fix)
_rate_limit_default = os.getenv("OPENCLAW_RATE_LIMIT", "120/minute")
limiter = Limiter(key_func=get_remote_address, default_limits=[_rate_limit_default])
app.state.limiter = limiter
from slowapi.middleware import SlowAPIMiddleware
app.add_middleware(SlowAPIMiddleware)

# ── OPS-1 Track B: CSRF double-submit middleware ─────────────────────────────
# Starlette `add_middleware` 採 LIFO/onion 順序：較晚 add 的 middleware 在 inbound
# 階段較早執行。本檔註冊次序為 CORS → SlowAPI → CSRF，故 inbound 處理順序為
# `CSRF → SlowAPI → CORS → route`。
# 為什麼這個順序安全：
#   - OPTIONS 不在 CSRF 寫操作集合，preflight 不會被攔截，CORS 正常運作
#   - CSRF 比對是 constant-time + 常數成本，先擋 mismatch 反而避免下游 SlowAPI 與
#     route handler 多餘 CPU；惡意洪流仍會被 SlowAPI 在 5/分鐘 login 等 endpoint
#     獨立攔截
# 為什麼用 add_middleware 而非 @middleware：CSRFMiddleware 繼承 BaseHTTPMiddleware
# 走 ASGI 標準路徑，比 decorator 更明確且可單獨單元測試。
# 預設 enforcing；操作者可暫時設 OPENCLAW_CSRF_SHADOW=1 進入 shadow mode（只記
# log 不阻擋）作為 14d 過渡期使用。
from .csrf_middleware import CSRFMiddleware  # noqa: E402
app.add_middleware(CSRFMiddleware)


# ── 安全响应头中间件 / Security response headers middleware ────────────────────
# APR01-MEDIUM-3: 为所有响应添加安全 HTTP 头，防止常见 Web 攻击向量。
# APR01-MEDIUM-3: Add security HTTP headers to ALL responses to mitigate
# common web attack vectors (clickjacking, MIME-sniffing, XSS, info leakage).
#
# CSP 注意事项 / CSP notes:
#   - 'unsafe-inline' 用于 script-src 和 style-src，因为 GUI HTML 使用内联 <script>/<style>
#     'unsafe-inline' needed for script/style because GUI HTML uses inline <script>/<style>
#   - https://unpkg.com 用于 trading.html 的 TradingView 图表库
#     https://unpkg.com needed for TradingView charting library in trading.html
#   - http://trade-core:3000 用于 tab-monitoring.html 的 Grafana iframe
#     http://trade-core:3000 needed for Grafana iframe in tab-monitoring.html
#   - data: 用于 img-src（内联图片，如 base64 编码的图标）
#     data: for img-src (inline images such as base64-encoded icons)
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """為每個 HTTP 響應注入安全頭，降低 XSS / 點擊劫持 / MIME 嗅探等風險。

    OPS-1 Wave A (Track C)：除既有 enforcing CSP 之外，並 emit
    `Content-Security-Policy-Report-Only` 影子規則蒐集 14 天 violation。
    為什麼 report-only：Wave A 不砍 `unsafe-inline`（25 個 HTML 仍 inline
    script），先以 Report-Only 觀測 nonce-based 升級在實際 GUI 上會生出多少
    violation；Wave B（P1，first Live D-14 前 1 sprint）才正式收緊。
    """
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://unpkg.com; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-src 'self' http://trade-core:3000; "
        "frame-ancestors 'self'"
    )
    # OPS-1 Wave A: Report-Only shadow CSP（不阻擋，只記錄）— 為 Wave B 收
    # 緊 `unsafe-inline` 提前蒐集 violation 樣本。CSP report-uri 指向自家
    # POST /api/v1/csp/report endpoint。Wave B 完成後此 shadow 規則直接升
    # 為 enforcing CSP，並刪掉 `unsafe-inline`。
    response.headers["Content-Security-Policy-Report-Only"] = (
        "default-src 'self'; "
        "script-src 'self' https://unpkg.com; "
        "style-src 'self'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-src 'self' http://trade-core:3000; "
        "frame-ancestors 'self'; "
        "report-uri /api/v1/csp/report"
    )
    return response


# ── OPS-1 Wave A: CSP violation report endpoint ──────────────────────────────
# 為什麼 stdout JSON log 而非 V### migration：spec §5.3 明說 OPS-1 不開新
# migration；Wave B 完成升級後再考慮入 `learning.csp_violation_log`。
# OPS-1 round 2 (F-4)：加 60/分鐘限頻 + 8KB body 上限。tailnet 內任何設備都能 POST
# 此 endpoint，沒有限制會被灌爆 journal log；瀏覽器正常 violation 頻率 ≤幾次/分鐘。
_CSP_REPORT_MAX_BYTES = 8 * 1024  # 8KB body 上限


@app.post("/api/v1/csp/report", include_in_schema=False)
@limiter.limit("60/minute")
async def csp_report(request: Request):
    """接收瀏覽器送來的 CSP violation report（JSON）。

    spec §5.3：Wave A 用 stdout JSON log 蒐集 14 天樣本；Wave B 才考慮 PG
    持久化。不需 auth（瀏覽器後台自動 POST，不可能附 cookie 給 cross-origin
    target；同源 report 即使無 cookie 也應接收）。

    OPS-1 round 2 (F-4)：限頻 60/分鐘 per-IP + body 上限 8KB；超出 413。
    """
    # 為什麼先讀 raw body 再 parse：FastAPI request.json() 直接讀完全部 bytes，
    # 沒辦法後置限制大小；改先 await body() 量 length 才安全。
    raw = await request.body()
    if len(raw) > _CSP_REPORT_MAX_BYTES:
        logger.warning(
            "CSP report body too large (%d bytes > %d) from %s",
            len(raw), _CSP_REPORT_MAX_BYTES,
            request.client.host if request.client else "unknown",
        )
        return JSONResponse(status_code=413, content=None)
    try:
        import json as _json  # 局部 import 避免污染 module top-level
        payload = _json.loads(raw.decode("utf-8")) if raw else {}
    except Exception:
        # 為什麼 silent 204：瀏覽器送爛 JSON 時不該 noise toast 給使用者；只記 warning。
        logger.warning(
            "CSP report received with invalid JSON body from %s",
            request.client.host if request.client else "unknown",
        )
        return JSONResponse(status_code=204, content=None)
    logger.info("csp_violation_report payload=%s", payload)
    return JSONResponse(status_code=204, content=None)


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    from starlette.responses import JSONResponse
    return JSONResponse(
        status_code=429,
        content={"detail": {"reason_codes": ["rate_limit_exceeded"], "retry_after": str(exc.detail)}},
    )


# ── E3-MED-4: 未捕獲例外的全域錯誤消毒中間件 ──────────────────────────────────
# 防止未處理的 500 錯誤把 str(exc)（含內部路徑/堆疊）洩漏給客戶端。
# OPENCLAW_DEBUG=1 時保留詳細錯誤訊息供開發使用；生產模式只回傳通用訊息。
_OPENCLAW_DEBUG = os.getenv("OPENCLAW_DEBUG", "").strip() == "1"


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled exception on %s %s: %s",
        request.method,
        request.url.path,
        exc,
        exc_info=True,
    )
    if _OPENCLAW_DEBUG:
        detail = {"reason_codes": ["internal_error"], "detail": str(exc)}
    else:
        detail = {"reason_codes": ["internal_error"], "detail": "Internal server error"}
    return JSONResponse(status_code=500, content={"detail": detail})


# ── WP-05 Real Fix: HTTPException + RequestValidationError handler 順位補完 ─────
# FastAPI 順位：`@app.exception_handler(Exception)` 不會捕 `HTTPException`/
# `RequestValidationError`（已由 FastAPI 內建 handler 處理）。下面兩個 handler
# 攔截這兩類，再做最後一道 leak 偵測 + 消毒。
# 偵測 pattern：`": <ErrorClass>"` / `: <Number>` / `Traceback` / `<class '...'>`
# 命中 → 換成 "Internal error"；不命中（如 reason_codes dict / 手寫短訊息）→ 放行。

# Leak 偵測 regex：抓「`: SomeError`」「`: 123`」「Traceback」「<class 'foo'>」等
# 表示原始 exception/str 注入未經消毒的 pattern。reason_codes-only dict 不會命中。
_LEAK_PATTERN = re.compile(
    r":\s+\w*Error|:\s+\d+|Traceback|<class '"
)


@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
    """HTTPException 二次消毒 — 攔截 detail=f"...{exc}" 漏網的 leak pattern。

    - detail 是 dict（structured response）→ 原樣放行（已是受控結構）
    - detail 是 str 且命中 leak pattern + 非 DEBUG → 改成通用 "Internal error"
    - 其他 str（短訊息 / 純業務文案）→ 原樣放行（避免破壞既有 GUI 文案）
    """
    detail = exc.detail
    if isinstance(detail, str) and not _OPENCLAW_DEBUG:
        if _LEAK_PATTERN.search(detail):
            logger.warning(
                "Sanitized leaky HTTPException detail on %s %s (status=%s)",
                request.method,
                request.url.path,
                exc.status_code,
            )
            detail = "Internal error"
    return JSONResponse(status_code=exc.status_code, content={"detail": detail})


@app.exception_handler(RequestValidationError)
async def _validation_error_handler(request: Request, exc: RequestValidationError):
    """422 validation 錯誤 — production 隱藏 pydantic errors 細節（含欄位 + 內部 type）。

    OPENCLAW_DEBUG=1 才回原 errors() 結構供開發排查。
    """
    if _OPENCLAW_DEBUG:
        return JSONResponse(status_code=422, content={"detail": exc.errors()})
    return JSONResponse(
        status_code=422,
        content={"detail": {"reason_codes": ["validation_failed"], "detail": "Validation failed"}},
    )


# ── WP-05 startup warn: OPENCLAW_DEBUG=1 production-leak 提醒 ─────────────────
# 不 fail-closed（避免破 dev workflow），只 log warning。
if _OPENCLAW_DEBUG and os.getenv("OPENCLAW_ALLOW_DEV", "").strip() != "1":
    logger.warning(
        "OPENCLAW_DEBUG=1 detected: exception messages will leak internal "
        "details to clients. Set OPENCLAW_ALLOW_DEV=1 to acknowledge or unset "
        "OPENCLAW_DEBUG for production."
    )


static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# SEC-D03: Auth guard for static files — prevent unauthenticated access to GUI HTML/JS.
# SEC-D03：靜態文件認證守衛 — 防止未認證用戶訪問 GUI HTML/JS。
# Exempt: styles.css (needed by login page before auth), favicon, and robots.txt.
# 豁免：styles.css（登錄頁面認證前需要）、favicon、robots.txt。
_STATIC_AUTH_EXEMPT = frozenset({"/static/styles.css", "/static/favicon.ico", "/static/robots.txt"})


@app.middleware("http")
async def static_auth_guard(request: Request, call_next):
    """Block unauthenticated access to static files (except login-page assets).
    阻止未認證用戶訪問靜態文件（登錄頁面資源除外）。
    """
    path = request.url.path
    if path.startswith("/static/") and path not in _STATIC_AUTH_EXEMPT:
        cookie_token = request.cookies.get("oc_auth_token")
        if not cookie_token or not hmac.compare_digest(
            cookie_token.encode("utf-8"), settings.api_token.encode("utf-8")
        ):
            from starlette.responses import JSONResponse
            return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
    response = await call_next(request)
    # No-cache for static files during development / 開發階段禁止靜態文件緩存
    if path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


def current_actor(
    request: Request,
    authorization: str | None = Header(default=None),
) -> Any:
    """
    Authenticate the caller via HttpOnly cookie (GUI) or Authorization header (API clients).
    Cookie takes priority; header is fallback for programmatic access.
    通过 HttpOnly cookie（GUI）或 Authorization header（API 客户端）验证调用者。
    Cookie 优先；header 为编程接口的后备方案。
    """
    token: str | None = None

    # Priority 1: HttpOnly cookie (XSS-safe, set by /api/v1/auth/login)
    # 优先级 1：HttpOnly cookie（防 XSS，由登录端点设置）
    cookie_token = request.cookies.get("oc_auth_token")
    if cookie_token:
        token = cookie_token

    # Priority 2: Authorization header (for programmatic API clients)
    # 优先级 2：Authorization header（供编程 API 客户端使用）
    if token is None and authorization is not None and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "", 1).strip()

    if token is None:
        raise HTTPException(status_code=401, detail={"reason_codes": ["unauthenticated"]})

    # 常数时间比较，防止时序攻击 / Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(token.encode("utf-8"), settings.api_token.encode("utf-8")):
        raise HTTPException(status_code=401, detail={"reason_codes": ["unauthenticated"]})
    return build_authenticated_actor()


def envelope_response(
    *,
    snapshot: dict[str, Any],
    request_id: str | None,
    action_result: str,
    data: Any,
    audit_ref: str | None = None,
    reason_codes: list[str] | None = None,
) -> ResponseEnvelope[Any]:
    return ResponseEnvelope[Any](
        api_version=settings.api_version,
        schema_version=settings.schema_version,
        request_id=request_id,
        snapshot_ts_ms=snapshot["meta"]["snapshot_ts_ms"],
        snapshot_id=snapshot["meta"]["snapshot_id"],
        state_revision=snapshot["meta"]["state_revision"],
        action_result=action_result,
        reason_codes=reason_codes or [],
        warnings=[],
        audit_ref=audit_ref,
        source_context=build_source_context(snapshot),
        data=data,
    )



# ── E5-P0-5: Register legacy route handlers (5 domain files) ────────────────
# 路由處理器已從 legacy_routes.py 拆分為 5 個領域檔案，在此依序註冊。
# Route handlers split from legacy_routes.py into 5 domain files, registered in order.
#
# Files + responsibility / 檔案與職責：
#   auth_legacy_routes.py    — 3 auth routes (login/logout/check)
#   gui_legacy_routes.py     — 6 GUI / HTML routes (/login, /, /gui, /console, /trading, /favicon.ico)
#   system_legacy_routes.py  — 14 system / health read routes (incl. /api/v1/healthz)
#   learning_legacy_routes.py — 19 learning / PnL routes
#   control_legacy_routes.py — 15 control / operator-write routes
# Total: 57 routes (54 from legacy_routes.py pre-refactor + /healthz + /system/fx-rates + /favicon.ico).
from .auth_legacy_routes import register_auth_legacy_routes  # noqa: E402
from .gui_legacy_routes import register_gui_legacy_routes  # noqa: E402
from .system_legacy_routes import register_system_legacy_routes  # noqa: E402
from .learning_legacy_routes import register_learning_legacy_routes  # noqa: E402
from .control_legacy_routes import register_control_legacy_routes  # noqa: E402

register_auth_legacy_routes(app)
register_gui_legacy_routes(app)
register_system_legacy_routes(app)
register_learning_legacy_routes(app)
register_control_legacy_routes(app)
