from __future__ import annotations

"""
Settings Routes — API key management endpoints
設置路由 — API key 槽位管理端點

MODULE_NOTE (中文):
  本模塊提供 API key 槽位的安全讀取與寫入端點：
  - GET  /api/v1/settings/api-key/{slot} — 返回遮罩後的 key hint（永不返回明文）
  - POST /api/v1/settings/api-key/{slot} — 驗證 key 後寫入 secrets 目錄，設置 chmod 600

  安全設計原則：
  1. Write-only from GUI — GET 只返回遮罩 hint，API 永不暴露明文 key
  2. Operator 角色守衛 — 所有端點要求認證；POST 額外要求 Operator 角色
  3. Slot 白名單 — 只允許 "demo" 和 "live"，防止路徑穿越
  4. 路徑安全 — secrets 目錄通過環境變量配置，fallback 到 ~/BybitOpenClaw/secrets/
  5. 驗證後寫入 — POST 先調 Bybit REST 驗證 key 有效性，驗證通過才寫磁盤
  6. chmod 600 — 寫入後立即收緊文件權限

MODULE_NOTE (English):
  Provides secure read/write endpoints for API key slot management:
  - GET  /api/v1/settings/api-key/{slot} — Returns masked key hint (never plaintext)
  - POST /api/v1/settings/api-key/{slot} — Validates key via Bybit REST, writes to secrets dir, chmod 600

  Security design:
  1. Write-only from GUI — GET only returns masked hint; API never exposes plaintext keys
  2. Operator auth guard — all endpoints require auth; POST additionally requires Operator role
  3. Slot whitelist — only "demo" and "live" are accepted, prevents path traversal
  4. Path safety — secrets dir configured via env var, falls back to ~/BybitOpenClaw/secrets/
  5. Validate-then-write — POST validates via Bybit REST before touching disk
  6. chmod 600 — file permissions tightened immediately after write
"""

import asyncio
import hashlib
import hmac as hmac_lib
import json
import logging
import os
import stat
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# BLOCKER-7 fix: Module-level asyncio.Lock serialising save_api_key so that
# two concurrent POSTs (e.g. demo + live with the same key) cannot race past
# the cross-slot conflict check. Bybit validation network I/O is held inside
# the lock, so worst case the second writer waits ~2-3 s — acceptable for an
# operator-only endpoint.
# BLOCKER-7 修復：模組層級 asyncio.Lock，串行化 save_api_key — 避免兩個並行
# POST（如 demo 與 live 同一把 key）同時通過跨槽位衝突檢查後各自落盤。
# Bybit 驗證網路 I/O 在鎖內進行，最壞情況第二個寫入等約 2-3 秒 —
# 這是 operator-only 端點，代價可接受。
_save_api_key_lock: asyncio.Lock = asyncio.Lock()

# ═══════════════════════════════════════════════════════════════════════════════
# Router / 路由器
# ═══════════════════════════════════════════════════════════════════════════════

settings_router = APIRouter(
    prefix="/api/v1/settings",
    tags=["Settings / 設置"],
)

# ═══════════════════════════════════════════════════════════════════════════════
# Constants / 常量
# ═══════════════════════════════════════════════════════════════════════════════

# Allowed slot names — whitelist prevents path traversal
# 允許的槽位名稱白名單，防止路徑穿越攻擊
# "live_demo" is a virtual slot: validates via demo server, persists to live path.
# 「live_demo」為虛擬槽位：通過 demo 伺服器驗證，寫入 live 路徑。
ALLOWED_SLOTS: frozenset[str] = frozenset({"demo", "live_demo", "live"})

# Base URL per slot — demo uses Bybit demo trading environment
# 每個槽位對應的 Bybit REST 基礎 URL
_BYBIT_BASE_URL: dict[str, str] = {
    "demo": "https://api-demo.bybit.com",
    "live_demo": "https://api-demo.bybit.com",
    "live": "https://api.bybit.com",
}

# Storage path mapping — live_demo writes to the live directory
# 存儲路徑映射 — live_demo 寫入 live 目錄
_SLOT_STORAGE_PATH: dict[str, str] = {
    "demo": "demo",
    "live_demo": "live",
    "live": "live",
}

# Validation endpoint — low-permission read-only query, sufficient to verify auth
# 驗證端點 — 低權限只讀查詢，足以驗證 key 有效性
_VALIDATE_PATH = "/v5/user/query-api"

# HTTP timeout for validation call (seconds) / 驗證請求超時（秒）
_VALIDATE_TIMEOUT = 10

# ═══════════════════════════════════════════════════════════════════════════════
# Helpers / 輔助函數
# ═══════════════════════════════════════════════════════════════════════════════


def _secrets_slot_dir(slot: str) -> Path:
    """
    Return the directory path for a given key slot.
    返回指定槽位的 secrets 目錄路徑。

    Uses OPENCLAW_SECRETS_DIR env var when set (cross-platform support).
    Otherwise falls back to ~/BybitOpenClaw/secrets/secret_files/bybit/{slot}.
    優先使用環境變量（跨平台），否則 fallback 到 ~/BybitOpenClaw/secrets/。
    """
    # Resolve virtual slots (e.g. live_demo → live) to physical storage path
    # 虛擬槽位（如 live_demo）映射到物理存儲路徑（live）
    storage_slot = _SLOT_STORAGE_PATH.get(slot, slot)
    base_env = os.environ.get("OPENCLAW_SECRETS_DIR")
    if base_env:
        return Path(base_env) / storage_slot
    return Path.home() / "BybitOpenClaw" / "secrets" / "secret_files" / "bybit" / storage_slot


def _mask_key(key: str) -> str:
    """
    Return a masked version of the key showing only the last 4 characters.
    返回遮罩後的 key，只顯示最後 4 個字符。
    """
    key = key.strip()
    if not key:
        return ""
    if len(key) <= 4:
        return "****"
    return "****" + key[-4:]


def _read_key_file(slot: str, filename: str) -> str:
    """
    Safely read a secret file for the given slot.
    安全讀取指定槽位的 secret 文件。

    Returns empty string if the file does not exist or is empty.
    文件不存在或為空時返回空字符串。
    """
    path = _secrets_slot_dir(slot) / filename
    try:
        content = path.read_text(encoding="utf-8").strip()
        return content
    except (FileNotFoundError, PermissionError, OSError):
        return ""


def _write_key_file(slot: str, filename: str, content: str) -> None:
    """
    Write content to a secret file and enforce chmod 600 permissions.
    寫入 secret 文件並強制設置 chmod 600 權限。

    Creates the directory tree with restrictive permissions if missing.
    目錄不存在時以嚴格權限創建。
    """
    slot_dir = _secrets_slot_dir(slot)
    slot_dir.mkdir(parents=True, exist_ok=True)
    # Ensure directory itself is only owner-accessible (700)
    # 確保目錄僅 owner 可訪問（700）
    try:
        os.chmod(slot_dir, stat.S_IRWXU)
    except OSError:
        pass  # Best-effort; might fail on some FS / 盡力而為，部分文件系統可能失敗

    path = slot_dir / filename
    path.write_text(content.strip(), encoding="utf-8")
    # Enforce 600 — owner read/write only, no group/other access
    # 強制 600 — 僅 owner 可讀寫，group/other 無權限
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def _build_bybit_signature(
    api_key: str,
    api_secret: str,
    timestamp: int,
    recv_window: int,
    query_string: str,
) -> str:
    """
    Build HMAC-SHA256 signature for Bybit v5 API.
    構建 Bybit v5 API 的 HMAC-SHA256 簽名。

    Signature format: timestamp + api_key + recv_window + query_string_or_body
    簽名格式：timestamp + api_key + recv_window + 查詢字符串或請求體
    """
    param_str = f"{timestamp}{api_key}{recv_window}{query_string}"
    return hmac_lib.new(
        api_secret.encode("utf-8"),
        param_str.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()


def _validate_bybit_credentials(api_key: str, api_secret: str, slot: str) -> tuple[bool, str]:
    """
    Validate Bybit API credentials by making a signed REST call.
    通過簽名 REST 調用驗證 Bybit API 憑證。

    Returns (is_valid, error_message).
    返回 (是否有效, 錯誤信息)。

    Calls /v5/user/query-api — read-only, low-permission endpoint sufficient for auth check.
    調用 /v5/user/query-api — 只讀低權限端點，足以驗證認證。
    """
    api_key = api_key.strip()
    api_secret = api_secret.strip()

    # Basic format sanity checks / 基礎格式校驗
    if not api_key or len(api_key) < 8:
        return False, "API key too short or empty"
    if not api_secret or len(api_secret) < 8:
        return False, "API secret too short or empty"

    base_url = _BYBIT_BASE_URL.get(slot, _BYBIT_BASE_URL["live"])
    timestamp = int(time.time() * 1000)
    recv_window = 5000
    query_string = ""

    signature = _build_bybit_signature(api_key, api_secret, timestamp, recv_window, query_string)

    url = f"{base_url}{_VALIDATE_PATH}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("X-BAPI-API-KEY", api_key)
    req.add_header("X-BAPI-SIGN", signature)
    req.add_header("X-BAPI-TIMESTAMP", str(timestamp))
    req.add_header("X-BAPI-RECV-WINDOW", str(recv_window))
    req.add_header("X-BAPI-SIGN-TYPE", "2")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=_VALIDATE_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:
            return False, f"HTTP {exc.code}: {exc.reason}"
    except urllib.error.URLError as exc:
        return False, f"Network error: {exc.reason}"
    except Exception as exc:
        return False, f"Unexpected error: {type(exc).__name__}: {exc}"

    ret_code = body.get("retCode", -1)
    ret_msg = body.get("retMsg", "unknown")

    if ret_code == 0:
        return True, ""
    # retCode 10003 = invalid API key, 10004 = invalid signature, etc.
    # retCode 10003 = 無效 API key，10004 = 無效簽名，等
    return False, f"Bybit retCode={ret_code}: {ret_msg}"


# ═══════════════════════════════════════════════════════════════════════════════
# Auth Dependencies / 認證依賴
# ═══════════════════════════════════════════════════════════════════════════════


def _get_auth_actor(
    request: Request,
    authorization: str | None = Header(default=None),
) -> Any:
    """
    Validate authentication via cookie or Bearer token.
    通過 cookie 或 Bearer token 驗證認證。

    Reuses the same logic as governance_routes._get_auth_actor.
    複用 governance_routes._get_auth_actor 的邏輯。
    """
    try:
        from . import main_legacy as base
    except ImportError:
        raise HTTPException(status_code=503, detail="Auth system unavailable")

    import hmac as _hmac

    token: str | None = None
    cookie_token = request.cookies.get("oc_auth_token")
    if cookie_token:
        token = cookie_token
    if token is None and authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "", 1).strip()
    if token is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not _hmac.compare_digest(token.encode("utf-8"), base.settings.api_token.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Authentication required")
    return base.build_authenticated_actor()


def _require_operator_auth(
    request: Request,
    authorization: str | None = Header(default=None),
) -> Any:
    """
    Validate authentication AND require Operator role.
    驗證認證並要求 Operator 角色。
    """
    actor = _get_auth_actor(request, authorization)
    if not actor or not hasattr(actor, "roles") or "operator" not in actor.roles:
        raise HTTPException(status_code=403, detail="Operator role required")
    return actor


# ═══════════════════════════════════════════════════════════════════════════════
# Request / Response Models / 請求/響應模型
# ═══════════════════════════════════════════════════════════════════════════════


class ApiKeySaveRequest(BaseModel):
    """Request body for POST /api/v1/settings/api-key/{slot}"""
    api_key: str = Field(..., min_length=1, max_length=128, description="Bybit API key")
    api_secret: str = Field(..., min_length=1, max_length=128, description="Bybit API secret")


# ═══════════════════════════════════════════════════════════════════════════════
# Endpoints / 端點
# ═══════════════════════════════════════════════════════════════════════════════


@settings_router.get("/api-key/{slot}")
async def get_api_key_status(
    slot: str,
    actor: Any = Depends(_get_auth_actor),
) -> dict:
    """
    GET /api/v1/settings/api-key/{slot}
    返回 API key 槽位狀態（遮罩 hint，永不返回明文）

    Returns masked hint of the stored API key — never returns plaintext.
    Returns has_key=False if no key is stored for this slot.

    返回已存儲 API key 的遮罩 hint，永不返回明文。
    槽位無 key 時 has_key=False。
    """
    if slot not in ALLOWED_SLOTS:
        raise HTTPException(status_code=400, detail=f"Invalid slot '{slot}'. Allowed: {sorted(ALLOWED_SLOTS)}")

    api_key = _read_key_file(slot, "api_key")
    api_secret = _read_key_file(slot, "api_secret")
    has_key = bool(api_key and api_secret)

    # Compute last_modified from the key file mtime / 從文件 mtime 獲取最後修改時間
    last_modified: str | None = None
    try:
        path = _secrets_slot_dir(slot) / "api_key"
        if path.exists():
            mtime = path.stat().st_mtime
            last_modified = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(mtime))
    except OSError:
        pass

    return {
        "slot": slot,
        "has_key": has_key,
        "key_hint": _mask_key(api_key) if api_key else "",
        "last_modified": last_modified,
    }


@settings_router.post("/api-key/{slot}")
async def save_api_key(
    slot: str,
    body: ApiKeySaveRequest,
    actor: Any = Depends(_require_operator_auth),
) -> dict:
    """
    POST /api/v1/settings/api-key/{slot}
    驗證並保存 API key（寫入 secrets 目錄，chmod 600）

    Validates the key via a signed Bybit REST call before writing.
    Returns {saved, validated, key_hint} — never echoes the plaintext key.

    寫入前通過簽名 Bybit REST 調用驗證 key 有效性。
    返回 {saved, validated, key_hint}，永不 echo 明文 key。
    """
    if slot not in ALLOWED_SLOTS:
        raise HTTPException(status_code=400, detail=f"Invalid slot '{slot}'. Allowed: {sorted(ALLOWED_SLOTS)}")

    api_key = body.api_key.strip()
    api_secret = body.api_secret.strip()

    # Security: strip any whitespace, reject obvious injections / 清除空白，拒絕明顯注入
    if any(c in api_key + api_secret for c in ("\n", "\r", "\x00", "/")):
        raise HTTPException(status_code=400, detail="API key contains invalid characters")

    # BLOCKER-7 fix: serialize the whole conflict-check → validate → write
    # sequence under a module-level lock, otherwise two concurrent POSTs with
    # the same key into different slots both pass the check before either writes.
    # BLOCKER-7 修復：整段衝突檢查 → 驗證 → 寫入必須串行 —
    # 否則兩個並行 POST 以同一 key 寫入不同槽位時會雙雙通過檢查。
    async with _save_api_key_lock:
        # 3E-7: Cross-slot conflict detection — same API key must not be used by two pipelines.
        # 3E-7：跨槽位衝突檢測 — 同一 API key 不能同時被兩個管線使用。
        _CONFLICT_PAIRS: dict[str, list[str]] = {
            "demo": ["live", "live_demo"],
            "live_demo": ["demo"],
            "live": ["demo"],
        }
        # BLOCKER-5 fix: Use hmac.compare_digest for constant-time comparison to
        # prevent timing-attack leakage of existing keys. Encode to bytes first
        # because compare_digest is strictest on same-type inputs.
        # BLOCKER-5 修復：使用 hmac.compare_digest 做常數時間比較，避免透過
        # 回應耗時洩漏既存 key。先 encode 為 bytes — compare_digest 對同型別輸入最安全。
        api_key_b = api_key.encode("utf-8")
        for other_slot in _CONFLICT_PAIRS.get(slot, []):
            existing_key = _read_key_file(other_slot, "api_key")
            if existing_key and hmac_lib.compare_digest(
                existing_key.strip().encode("utf-8"), api_key_b
            ):
                logger.warning(
                    "API key conflict: slot '%s' key matches '%s' slot (actor: %s)",
                    slot, other_slot, getattr(actor, "actor_id", "?"),
                )
                raise HTTPException(
                    status_code=409,
                    detail=f"API key conflicts with '{other_slot}' slot. "
                           "Each pipeline must use a distinct API key.",
                )

        # Validate via Bybit REST / 調用 Bybit REST 驗證
        logger.info("Validating Bybit API key for slot '%s' (actor: %s)", slot, getattr(actor, "actor_id", "?"))
        is_valid, err_msg = _validate_bybit_credentials(api_key, api_secret, slot)

        if not is_valid:
            # SEC-F04: Truncate err_msg to prevent potential info leakage from Bybit API responses.
            # SEC-F04：截斷 err_msg 防止 Bybit API 回應洩漏敏感信息。
            safe_err = (err_msg or "")[:200]
            logger.warning(
                "Bybit key validation failed for slot '%s': %s (actor: %s)",
                slot, safe_err, getattr(actor, "actor_id", "?"),
            )
            return {
                "saved": False,
                "validated": False,
                "key_hint": "",
                "error": safe_err,
            }

        # Write to secrets directory / 寫入 secrets 目錄
        # Also write bybit_endpoint metadata so Rust knows which server to connect to.
        # live_demo slot → demo server; live slot → mainnet; demo slot → demo (informational).
        # 同時寫入 bybit_endpoint 元數據，讓 Rust 知道連哪個伺服器。
        # live_demo 槽 → demo 伺服器；live 槽 → 主網；demo 槽 → demo（參考用）。
        _SLOT_ENDPOINT: dict[str, str] = {"demo": "demo", "live_demo": "demo", "live": "mainnet"}
        try:
            _write_key_file(slot, "api_key", api_key)
            _write_key_file(slot, "api_secret", api_secret)
            _write_key_file(slot, "bybit_endpoint", _SLOT_ENDPOINT.get(slot, "mainnet"))
        except (OSError, PermissionError) as exc:
            # Log full detail server-side; return generic message to client (no path leakage)
            # 服務器端記錄完整細節；返回通用錯誤消息，不向客戶端洩漏文件路徑
            logger.error("Failed to write API key for slot '%s': %s", slot, exc)
            raise HTTPException(status_code=500, detail="Failed to persist API key. Check server logs.")

        key_hint = _mask_key(api_key)
        logger.info(
            "API key saved for slot '%s', hint=%s (actor: %s)",
            slot, key_hint, getattr(actor, "actor_id", "?"),
        )

        return {
            "saved": True,
            "validated": True,
            "key_hint": key_hint,
            "slot": slot,
        }
