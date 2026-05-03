"""
MODULE_NOTE (中文):
  認證與配置模塊。包含 Settings 類（應用配置 dataclass）、_resolve_api_token（Token 解析鏈）、
  AuthenticatedActor（已認證操作者 dataclass）、以及登錄失敗追蹤變量。
  從 main_legacy.py 拆分而來（Wave B 重構）。

  ★ 注意：settings 單例和依賴 settings 的函數（build_authenticated_actor / current_actor /
  build_source_context / envelope_response）留在 main_legacy.py，因為多個測試依賴
  importlib.reload(main_legacy) 來重建 Settings 實例。

MODULE_NOTE (English):
  Authentication and configuration module. Contains Settings class (app configuration dataclass),
  _resolve_api_token (token resolution chain), AuthenticatedActor (authenticated operator dataclass),
  and login failure tracking variables. Extracted from main_legacy.py (Wave B refactoring).

  ★ Note: The settings singleton and functions that depend on it (build_authenticated_actor /
  current_actor / build_source_context / envelope_response) remain in main_legacy.py because
  multiple tests rely on importlib.reload(main_legacy) to recreate the Settings instance.
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import HTTPException, status

from .state_models import RequestEnvelope

logger = logging.getLogger(__name__)


def _split_csv(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def _is_truthy_env(value: str | None) -> bool:
    """Return true for explicit opt-in env strings.
    將明確 opt-in 的環境變量字串轉成布林值。
    """
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


# Login failure tracking — IP → (failure_count, first_failure_timestamp)
# 登录失败追踪：IP → (失败次数, 首次失败时间戳)
# Locked out after 5 failures within 15 minutes; auto-resets after window expires.
# 15分钟内失败5次后锁定；超过窗口期自动重置。（P1-8 修复）
_login_fail_counts: dict[str, tuple[int, float]] = {}
_LOGIN_MAX_FAILURES = 5        # 同一IP最多失败次数 / max failures per IP
_LOGIN_LOCKOUT_WINDOW = 900.0  # 锁定窗口（秒）/ lockout window in seconds (15 min)
_login_fail_lock = asyncio.Lock()  # 保护 _login_fail_counts 的并发锁 / asyncio lock for _login_fail_counts (P1-NEW-3)
_LOGIN_FAIL_MAX_IPS = 2000         # 最多追踪 IP 数，防止 OOM / max tracked IPs to prevent OOM (P1-NEW-3)

# ── Auth credentials cache (P1-12) ────────────────────────────────────────────
# Loaded once at startup; avoids per-request file I/O on the login endpoint.
# 启动时一次性加载凭证，避免每次登录请求都读文件。
_AUTH_CREDENTIALS: dict[str, str] | None = None


def _load_auth_credentials() -> dict[str, str]:
    """Load auth credentials once at startup and cache.
    启动时加载一次认证凭证并缓存，后续直接返回缓存值。

    Cross-platform path resolution (CLAUDE.md §七.★★.1):
    1. $OPENCLAW_SECRETS_ROOT/environment_files/gui_auth.env
    2. Linux legacy: ~/BybitOpenClaw/secrets/gui_auth.env

    跨平台路徑解析（CLAUDE.md §七.★★.1）：優先讀 $OPENCLAW_SECRETS_ROOT，
    再 fallback 到 Linux legacy 預設路徑（不破壞既有部署）。
    """
    global _AUTH_CREDENTIALS
    if _AUTH_CREDENTIALS is not None:
        return _AUTH_CREDENTIALS
    creds: dict[str, str] = {}
    env_path: Path | None = None
    secrets_root = os.environ.get("OPENCLAW_SECRETS_ROOT")
    if secrets_root:
        candidate = Path(secrets_root) / "environment_files" / "gui_auth.env"
        if candidate.exists():
            env_path = candidate
    if env_path is None:
        legacy = Path(os.path.expanduser("~/BybitOpenClaw/secrets/gui_auth.env"))
        if legacy.exists():
            env_path = legacy
    if env_path is not None:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    creds[k.strip()] = v.strip()
    _AUTH_CREDENTIALS = creds
    return creds


def _resolve_api_token() -> str:
    """
    API Token 解析顺序 / API Token resolution order:
    1. 环境变量 OPENCLAW_API_TOKEN（推荐）/ Environment variable (recommended)
    2. Token 文件 OPENCLAW_API_TOKEN_FILE 指向的文件 / File pointed to by env var
    3. 默认 token 文件路径 ../.secrets/api_token / Default token file path
    4. 自动生成并保存到默认路径 / Auto-generate and save to default path

    安全规则 / Safety rules:
    - 不接受 "change-me" 或空值 / Rejects "change-me" or empty values
    - 占位符 token 明確 fail-closed / Placeholder token fails closed
    - 自動生成時不打印 token 值 / Auto-generation never prints token value
    """
    import sys

    # 1. 环境变量 / Environment variable
    env_token = os.getenv("OPENCLAW_API_TOKEN", "").strip()
    if env_token and env_token not in {"change-me", "CHANGE_ME", "your-token-here"}:
        return env_token
    if env_token:
        raise RuntimeError(
            "OPENCLAW_API_TOKEN is a placeholder; configure a real token or "
            "OPENCLAW_API_TOKEN_FILE. / OPENCLAW_API_TOKEN 是占位符，請配置真 token 或 token file。"
        )

    # 2. Token 文件（环境变量指定路径）/ Token file (env-specified path)
    token_file_env = os.getenv("OPENCLAW_API_TOKEN_FILE", "").strip()
    if token_file_env:
        token_file = Path(token_file_env)
    else:
        # 3. 默认 token 文件路径 / Default token file path
        token_file = Path(__file__).resolve().parent.parent / ".secrets" / "api_token"

    if token_file.exists():
        saved_token = token_file.read_text(encoding="utf-8").strip()
        if saved_token and saved_token not in {"change-me", "CHANGE_ME", "your-token-here"}:
            return saved_token
        if saved_token:
            raise RuntimeError(
                f"API token file contains a placeholder: {token_file}. "
                "Replace it before starting the API."
            )

    if _is_truthy_env(os.getenv("OPENCLAW_API_TOKEN_STRICT")):
        raise RuntimeError(
            "No API token configured and OPENCLAW_API_TOKEN_STRICT=1. "
            "Set OPENCLAW_API_TOKEN_FILE or OPENCLAW_API_TOKEN."
        )

    # 4. 自动生成 / Auto-generate
    new_token = secrets.token_urlsafe(32)
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(new_token + "\n", encoding="utf-8")
    os.chmod(str(token_file), 0o600)
    os.chmod(str(token_file.parent), 0o700)

    print(
        f"\n{'='*60}\n"
        f"  [OpenClaw] API Token 已自动生成并保存\n"
        f"  [OpenClaw] API Token auto-generated and saved\n"
        f"\n"
        f"  文件 / File: {token_file}\n"
        f"  Token value intentionally not printed. Read the 0600 file locally if needed.\n"
        f"  Token 值不打印；如需查看，請在本機讀取 0600 權限檔案。\n"
        f"\n"
        f"  请妥善保管此 Token。重置方法见：\n"
        f"  Keep this token safe. Reset instructions:\n"
        f"    docs/references/API_TOKEN_RESET_GUIDE.md\n"
        f"{'='*60}\n",
        file=sys.stderr,
    )
    return new_token


@dataclass(slots=True)
class Settings:
    api_prefix: str = "/api/v1"
    api_version: str = "v1"
    schema_version: str = "v1"
    service_name: str = "OpenClaw / Bybit Control API"
    gui_title: str = "OpenClaw / Bybit Control Center"

    api_token: str = field(default_factory=_resolve_api_token)
    auth_actor_id: str = field(default_factory=lambda: os.getenv("OPENCLAW_AUTH_ACTOR_ID", "demo-operator"))
    auth_actor_type: str = field(default_factory=lambda: os.getenv("OPENCLAW_AUTH_ACTOR_TYPE", "human"))
    auth_roles: set[str] = field(
        default_factory=lambda: _split_csv(
            os.getenv(
                "OPENCLAW_AUTH_ROLES",
                "viewer,operator,operator_guarded,config_admin,finance_input",
            )
        )
    )
    auth_scopes: set[str] = field(
        default_factory=lambda: _split_csv(
            os.getenv(
                "OPENCLAW_AUTH_SCOPES",
                ",".join(
                    [
                        "state:read",
                        "learning:read",
                        "control:recheck",
                        "control:validate",
                        "control:arm",
                        "control:enable",
                        "control:relock",
                        "control:bundle",
                        "input:cost",
                        "input:event",
                        "input:note",
                        "input:config",
                        # ── L 章学习系统权限 / L-chapter learning system scopes ──
                        "learning:write",   # 录入观察/经验/假设/实验 / Record observations/lessons/hypotheses/experiments
                        "learning:manage",  # 审批假设/实验、完成实验 / Approve hypotheses/experiments, complete experiments
                        # ── 纸上交易权限 / Paper trading scopes ──
                        "paper:read",       # 查看纸上交易数据 / View paper trading data
                        "paper:trade",      # 提交/取消纸上订单 / Submit/cancel paper orders
                        "live:trade",
                        "live:authority",
                        # ── Route-family write/read scopes (Batch B hardening) ──
                        # 路由族權限（Batch B auth hardening）
                        "ai_budget:write",
                        "risk:write",
                        "strategy:write",
                        "system:write",
                        "system:restart",
                        "paper:config",
                        "executor:write",
                        "ml:read",
                        "ml:write",
                        # ── REF-20 Replay Lab scopes (Sprint 1 Track C E2 retrofit F8) ──
                        # REF-20 Replay 實驗室 scope（Sprint 1 Track C E2 retrofit F8）
                        # ``replay:write`` — POST /run, /cancel, /manifest/verify
                        #   (mutating routes; Operator-only)
                        # ``replay:read:any`` — admin bypass scope used by GET
                        #   /report/{experiment_id}; allows cross-actor read for
                        #   incident investigation. Plain operator should NOT
                        #   hold this scope; explicit grant per-incident only.
                        # ``replay:read:any`` 為 admin 跨 actor 讀 report 的 scope；
                        # 一般 operator 不應持，僅 incident investigation 顯式授予。
                        "replay:write",
                        "replay:read:any",
                    ]
                ),
            )
        )
    )
    state_file_path: str = field(
        default_factory=lambda: os.getenv(
            "OPENCLAW_STATE_FILE",
            os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__),
                    "..",
                    "runtime",
                    "openclaw_bybit_control_state.json",
                )
            ),
        )
    )
    readonly_connector_name: str = field(
        default_factory=lambda: os.getenv("OPENCLAW_READONLY_CONNECTOR_NAME", "bybit_prod_readonly_main")
    )
    execution_connector_name: str | None = field(
        default_factory=lambda: os.getenv("OPENCLAW_EXECUTION_CONNECTOR_NAME") or None
    )
    rest_private_connection_state: str = field(
        default_factory=lambda: os.getenv("OPENCLAW_REST_PRIVATE_CONNECTION_STATE", "ready")
    )
    ws_private_connection_state: str = field(
        default_factory=lambda: os.getenv("OPENCLAW_WS_PRIVATE_CONNECTION_STATE", "ready")
    )
    runtime_connection_state: str = field(
        default_factory=lambda: os.getenv("OPENCLAW_RUNTIME_CONNECTION_STATE", "healthy")
    )
    account_fact_completeness_state: str = field(
        default_factory=lambda: os.getenv("OPENCLAW_ACCOUNT_FACT_COMPLETENESS_STATE", "complete")
    )
    source_snapshot_completeness_state: str = field(
        default_factory=lambda: os.getenv("OPENCLAW_SOURCE_SNAPSHOT_COMPLETENESS_STATE", "complete")
    )


@dataclass(slots=True)
class AuthenticatedActor:
    actor_id: str
    actor_type: str
    roles: set[str]
    scopes: set[str]


def require_scope(actor: AuthenticatedActor, scope: str) -> None:
    scopes = getattr(actor, "scopes", set()) or set()
    if scope not in scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"reason_codes": ["forbidden_scope"]},
        )


def require_operator_role(actor: AuthenticatedActor) -> None:
    """Require an authenticated Operator role.
    要求已認證 actor 具有 Operator 角色。

    Kept in auth.py so non-governance routers can share the same fail-closed
    write gate without importing governance_routes and risking circular imports.
    放在 auth.py，讓非 governance 路由也能共用同一 fail-closed 寫入閘門。
    """
    if not actor or not hasattr(actor, "roles") or not hasattr(actor, "actor_id"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"reason_codes": ["unauthenticated"]},
        )
    if "operator" not in actor.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"reason_codes": ["operator_role_required"]},
        )


def require_scope_and_operator(actor: AuthenticatedActor, scope: str) -> None:
    """Require both route-family scope and Operator role for state changes.
    state-changing route 必須同時具備 route-family scope 與 Operator 角色。
    """
    require_operator_role(actor)
    require_scope(actor, scope)


def audit_actor_id(actor: AuthenticatedActor) -> str:
    """Return the server-authenticated actor id for audit fields.
    回傳伺服器認證出的 actor id，供 audit 欄位使用；不信任 client-supplied by/id。
    """
    return str(getattr(actor, "actor_id", "unknown"))


def require_scope_and_identity(
    actor: AuthenticatedActor, scope: str, envelope: RequestEnvelope
) -> None:
    """Enforce scope permission AND operator identity in one call.
    一次調用同時檢查權限範圍和操作員身份。

    Every write operation requires both checks. Combining them into one function
    ensures neither can be accidentally omitted.
    每個寫操作都需要兩項檢查。合併為一個函數確保不會遺漏任何一項。
    """
    require_scope(actor, scope)
    verify_operator_identity(envelope, actor)


def verify_operator_identity(envelope: RequestEnvelope, actor: AuthenticatedActor) -> None:
    """Verify that the request envelope's operator_id matches the authenticated actor.
    验证请求信封中的 operator_id 与已认证操作者是否一致。

    TOCTOU note (E3-LOW-LEGACY-1) — ACKNOWLEDGED, not exploitable in current architecture:
    TOCTOU 备注（E3-LOW-LEGACY-1）— 已确认，在当前架构下不可利用：
      - actor is a fresh per-request dataclass built from the immutable settings singleton
        actor 是每次请求新建的 dataclass，来源于不可变的 settings 单例
      - envelope.operator_id is parsed from the request body (immutable within request)
        envelope.operator_id 来自请求体（请求内不可变）
      - No await point exists between check and subsequent use in callers
        调用者在检查和后续使用之间没有 await 点
      - settings.auth_actor_id is set once at startup and never mutated
        settings.auth_actor_id 在启动时设置一次，此后不再变更
    """
    if envelope.operator_id != actor.actor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"reason_codes": ["operator_identity_mismatch"]},
        )
