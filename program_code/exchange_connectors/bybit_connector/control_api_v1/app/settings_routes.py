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
  3. Slot 白名單 — 只允許 "demo"、"live_demo" 和 "live"，防止路徑穿越
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
  3. Slot whitelist — only "demo", "live_demo", and "live" are accepted, prevents path traversal
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
import re
import stat
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Mapping

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from . import alert_config as _alert_cfg
from .error_sanitize import log_safe_exception

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

# Alert config: per-process throttle for the /alerts/test endpoint so a real
# outbound alert cannot be hammered. monotonic 時間戳，最小間隔見 _ALERT_TEST_MIN_INTERVAL。
# 告警 config：/alerts/test 端點的 per-process 節流，避免真實外送告警被連發。
_ALERT_TEST_MIN_INTERVAL_SECONDS = 10.0
_alert_test_last_ts: float = 0.0
_alert_test_lock: asyncio.Lock = asyncio.Lock()

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
_SECRET_FILENAMES: frozenset[str] = frozenset(
    {"api_key", "api_secret", "bybit_endpoint"}
)
_SECRET_DIR_MODE = stat.S_IRWXU
_SECRET_FILE_MODE = stat.S_IRUSR | stat.S_IWUSR
_SECRET_FILE_MAX_BYTES = 64 * 1024

# Validation endpoint — low-permission read-only query, sufficient to verify auth
# 驗證端點 — 低權限只讀查詢，足以驗證 key 有效性
_VALIDATE_PATH = "/v5/user/query-api"

# HTTP timeout for validation call (seconds) / 驗證請求超時（秒）
_VALIDATE_TIMEOUT = 10

# Legacy Paper engine process toggle. The Rust engine reads this at process
# startup; the GUI reads the persisted setting immediately to decide whether
# to expose the legacy Paper tab.
# Legacy Paper engine 進程開關。Rust engine 啟動時讀取；GUI 立即讀取持久化
# 設定，以決定是否顯示 legacy Paper tab。
_PAPER_ENGINE_ENV_KEY = "OPENCLAW_ENABLE_PAPER"
_DEVELOPMENT_SUPPORT_MODE_ENV_KEY = "OPENCLAW_DEVELOPMENT_SUPPORT_MODE"
_LEGACY_GUI_DEVELOPMENT_MODE_ENV_KEY = "OPENCLAW_GUI_DEVELOPMENT_MODE"
_BASIC_SYSTEM_ENV_FILE = "basic_system_services.env"
_TRADING_SERVICES_ENV_FILE = "trading_services.env"
_BYBIT_MODE_ENV_KEY = "BYBIT_MODE"
_BYBIT_CONNECTOR_WRITE_ENABLED_ENV_KEY = "BYBIT_CONNECTOR_WRITE_ENABLED"
_BYBIT_DEMO_CONNECTOR_MODE_CONFIRM = "enable_demo_connector_mode:bounded_demo_probe:demo_only"
_CUTOVER_PREFLIGHT_SCHEMA_VERSION = "bounded_demo_credential_mode_cutover_preflight_v1"
_CUTOVER_PREFLIGHT_READY_STATUS = "BOUNDED_DEMO_CREDENTIAL_MODE_CUTOVER_PREFLIGHT_READY_NO_MUTATION"
_CUTOVER_PREFLIGHT_MAX_BYTES = 1024 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ENV_TRUTHY = frozenset({"1", "true", "yes", "on", "enabled"})
_ENV_FALSEY = frozenset({"0", "false", "no", "off", "disabled"})
_MIGRATION_FILE_RE = re.compile(r"^V(?P<version>\d{3})__(?P<name>.+)\.sql$")
_MIGRATION_COMPANION_RE = re.compile(r"^V(?P<version>\d{3})_(?!_)(?P<name>.+)\.sql$")
_DOC_CLUSTER_PATHS = (
    "docs/CCAgentWorkSpace",
    "docs/governance_dev",
    "docs/worklogs",
    "docs/references",
    "docs/archive",
    "docs/execution_plan",
    "docs/audits",
    "docs/audit",
    "docs/decisions",
    "docs/adr",
    "docs/architecture",
    "docs/runbooks",
    "docs/healthchecks",
    "docs/handoffs",
    "docs/known_issues",
    "docs/rust_migration",
    "memory",
    ".codex",
    ".claude_reports",
)

# ═══════════════════════════════════════════════════════════════════════════════
# Helpers / 輔助函數
# ═══════════════════════════════════════════════════════════════════════════════


def _secrets_root() -> Path:
    base_env = os.environ.get("OPENCLAW_SECRETS_DIR")
    if base_env:
        configured = Path(base_env).expanduser()
    else:
        configured = (
        Path.home()
        / "BybitOpenClaw"
        / "secrets"
        / "secret_files"
        / "bybit"
        )
    return Path(os.path.abspath(configured))


def _reject_secret_symlink(path: Path) -> None:
    if path.is_symlink():
        raise ValueError("secret path must not be a symlink")


def _secret_directory_open_flags() -> int:
    no_follow = getattr(os, "O_NOFOLLOW", None)
    directory = getattr(os, "O_DIRECTORY", None)
    if no_follow is None or directory is None:
        raise OSError("required safe-open flags are unavailable")
    return os.O_RDONLY | no_follow | directory


def _effective_uid() -> int:
    get_effective_uid = getattr(os, "geteuid", None)
    if get_effective_uid is None:
        raise OSError("effective uid is unavailable")
    return int(get_effective_uid())


def _require_private_secret_directory_fd(fd: int) -> None:
    directory_stat = os.fstat(fd)
    if (
        not stat.S_ISDIR(directory_stat.st_mode)
        or stat.S_IMODE(directory_stat.st_mode) != _SECRET_DIR_MODE
        or directory_stat.st_uid != _effective_uid()
    ):
        raise PermissionError("secret directory must be owned by euid with mode 0700")


def _require_private_secret_file_stat(file_stat: os.stat_result) -> None:
    if (
        not stat.S_ISREG(file_stat.st_mode)
        or stat.S_IMODE(file_stat.st_mode) != _SECRET_FILE_MODE
        or file_stat.st_uid != _effective_uid()
    ):
        raise PermissionError("secret file must be owned by euid with mode 0600")


def _open_absolute_directory(path: Path, *, create_missing: bool) -> int:
    """Open an absolute directory chain without following any component symlink."""
    absolute = Path(os.path.abspath(path))
    if not absolute.is_absolute() or not absolute.anchor:
        raise ValueError("secret root must be absolute")
    flags = _secret_directory_open_flags()
    current_fd = -1
    try:
        current_fd = os.open(absolute.anchor, flags)
        for component in absolute.parts[1:]:
            if component in {"", ".", ".."}:
                raise ValueError("invalid secret directory component")
            try:
                next_fd = os.open(component, flags, dir_fd=current_fd)
            except FileNotFoundError:
                if not create_missing:
                    raise
                try:
                    os.mkdir(component, _SECRET_DIR_MODE, dir_fd=current_fd)
                except FileExistsError:
                    pass
                next_fd = os.open(component, flags, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
        result_fd = current_fd
        current_fd = -1
        return result_fd
    finally:
        if current_fd >= 0:
            os.close(current_fd)


def _open_secret_root_fd(*, create: bool) -> int:
    fd = _open_absolute_directory(_secrets_root(), create_missing=create)
    try:
        _require_private_secret_directory_fd(fd)
        return fd
    except BaseException:
        os.close(fd)
        raise


def _open_secret_slot_fd(slot: str, *, create: bool) -> int:
    if slot not in ALLOWED_SLOTS:
        raise ValueError("unsupported secret slot")
    root_fd = _open_secret_root_fd(create=create)
    slot_fd = -1
    try:
        storage_slot = _SLOT_STORAGE_PATH[slot]
        try:
            slot_fd = os.open(
                storage_slot,
                _secret_directory_open_flags(),
                dir_fd=root_fd,
            )
        except FileNotFoundError:
            if not create:
                raise
            try:
                os.mkdir(storage_slot, _SECRET_DIR_MODE, dir_fd=root_fd)
            except FileExistsError:
                pass
            slot_fd = os.open(
                storage_slot,
                _secret_directory_open_flags(),
                dir_fd=root_fd,
            )
        _require_private_secret_directory_fd(slot_fd)
        result_fd = slot_fd
        slot_fd = -1
        return result_fd
    finally:
        if slot_fd >= 0:
            os.close(slot_fd)
        os.close(root_fd)


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
    if slot not in ALLOWED_SLOTS:
        raise ValueError("unsupported secret slot")
    root = _secrets_root()
    _reject_secret_symlink(root)
    candidate = Path(os.path.abspath(root / _SLOT_STORAGE_PATH[slot]))
    if not candidate.is_relative_to(root):
        raise ValueError("secret slot escapes configured root")
    _reject_secret_symlink(candidate)
    return candidate


def _secret_file_path(slot: str, filename: str) -> Path:
    if filename not in _SECRET_FILENAMES:
        raise ValueError("unsupported secret filename")
    root = _secrets_root()
    candidate = Path(os.path.abspath(_secrets_slot_dir(slot) / filename))
    if not candidate.is_relative_to(root):
        raise ValueError("secret file escapes configured root")
    _reject_secret_symlink(candidate)
    return candidate


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
    try:
        raw = _read_key_file_bytes(slot, filename)
        return raw.decode("utf-8").strip() if raw is not None else ""
    except (FileNotFoundError, PermissionError, OSError, UnicodeError, ValueError):
        return ""


def _read_key_file_bytes(slot: str, filename: str) -> bytes | None:
    """Return one bounded regular secret file exactly, or ``None`` if absent."""
    if filename not in _SECRET_FILENAMES:
        raise ValueError("unsupported secret filename")
    slot_fd = -1
    fd = -1
    try:
        slot_fd = _open_secret_slot_fd(slot, create=False)
        no_follow = getattr(os, "O_NOFOLLOW", None)
        nonblock = getattr(os, "O_NONBLOCK", None)
        if no_follow is None or nonblock is None:
            raise OSError("required safe-open flags are unavailable")
        fd = os.open(
            filename,
            os.O_RDONLY | no_follow | nonblock,
            dir_fd=slot_fd,
        )
        before = os.fstat(fd)
        _require_private_secret_file_stat(before)
        if before.st_size < 0 or before.st_size > _SECRET_FILE_MAX_BYTES:
            raise ValueError("secret target exceeds size bound")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(fd, min(remaining, 64 * 1024))
            if not chunk:
                raise OSError("secret target changed during read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(fd, 1):
            raise OSError("secret target changed during read")
        after = os.fstat(fd)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_mode,
            before.st_uid,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_mode,
            after.st_uid,
        ):
            raise OSError("secret target changed during read")
        return b"".join(chunks)
    except FileNotFoundError:
        return None
    finally:
        if fd >= 0:
            os.close(fd)
        if slot_fd >= 0:
            os.close(slot_fd)


def _secret_file_mtime(slot: str, filename: str) -> float | None:
    """Read trusted secret-file metadata through the same descriptor boundary."""
    if filename not in _SECRET_FILENAMES:
        raise ValueError("unsupported secret filename")
    slot_fd = -1
    fd = -1
    try:
        slot_fd = _open_secret_slot_fd(slot, create=False)
        no_follow = getattr(os, "O_NOFOLLOW", None)
        nonblock = getattr(os, "O_NONBLOCK", None)
        if no_follow is None or nonblock is None:
            raise OSError("required safe-open flags are unavailable")
        fd = os.open(
            filename,
            os.O_RDONLY | no_follow | nonblock,
            dir_fd=slot_fd,
        )
        file_stat = os.fstat(fd)
        _require_private_secret_file_stat(file_stat)
        return float(file_stat.st_mtime)
    except FileNotFoundError:
        return None
    finally:
        if fd >= 0:
            os.close(fd)
        if slot_fd >= 0:
            os.close(slot_fd)


def _write_key_file(slot: str, filename: str, content: str | bytes) -> None:
    """
    Write content to a secret file and enforce chmod 600 permissions.
    寫入 secret 文件並強制設置 chmod 600 權限。

    Creates the directory tree with restrictive permissions if missing.
    目錄不存在時以嚴格權限創建。
    """
    if filename not in _SECRET_FILENAMES:
        raise ValueError("unsupported secret filename")
    raw_content = (
        content.strip().encode("utf-8")
        if isinstance(content, str)
        else bytes(content)
    )
    if len(raw_content) > _SECRET_FILE_MAX_BYTES:
        raise ValueError("secret content exceeds size bound")
    slot_fd = _open_secret_slot_fd(slot, create=True)
    fd = -1
    temp_name: str | None = None
    try:
        try:
            existing_stat = os.stat(filename, dir_fd=slot_fd, follow_symlinks=False)
        except FileNotFoundError:
            existing_stat = None
        if existing_stat is not None:
            _require_private_secret_file_stat(existing_stat)

        no_follow = getattr(os, "O_NOFOLLOW", None)
        if no_follow is None:
            raise OSError("required safe-open flags are unavailable")
        for _attempt in range(32):
            candidate = f".{filename}.{uuid.uuid4().hex}.tmp"
            try:
                fd = os.open(
                    candidate,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | no_follow,
                    _SECRET_FILE_MODE,
                    dir_fd=slot_fd,
                )
            except FileExistsError:
                continue
            temp_name = candidate
            break
        if fd < 0 or temp_name is None:
            raise FileExistsError("could not allocate secret temporary file")

        os.fchmod(fd, _SECRET_FILE_MODE)
        _require_private_secret_file_stat(os.fstat(fd))
        view = memoryview(raw_content)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short secret write")
            view = view[written:]
        os.fsync(fd)
        os.close(fd)
        fd = -1

        os.replace(
            temp_name,
            filename,
            src_dir_fd=slot_fd,
            dst_dir_fd=slot_fd,
        )
        temp_name = None
        final_stat = os.stat(filename, dir_fd=slot_fd, follow_symlinks=False)
        _require_private_secret_file_stat(final_stat)
        os.fsync(slot_fd)
    finally:
        if fd >= 0:
            os.close(fd)
        if temp_name is not None:
            try:
                os.unlink(temp_name, dir_fd=slot_fd)
            except FileNotFoundError:
                pass
        os.close(slot_fd)


def _remove_key_file(slot: str, filename: str) -> None:
    """Remove a regular owned secret file and durably record the directory entry."""
    if filename not in _SECRET_FILENAMES:
        raise ValueError("unsupported secret filename")
    try:
        slot_fd = _open_secret_slot_fd(slot, create=False)
    except FileNotFoundError:
        return
    try:
        try:
            target_stat = os.stat(filename, dir_fd=slot_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        _require_private_secret_file_stat(target_stat)
        os.unlink(filename, dir_fd=slot_fd)
        os.fsync(slot_fd)
    finally:
        os.close(slot_fd)


def _write_credential_bundle(slot: str, values: Mapping[str, str]) -> None:
    """Persist the three-file credential bundle with same-process rollback.

    Every old file is snapshotted before the first replacement.  If a write or
    post-write check raises in this process, all three paths are restored to
    their prior bytes (or removed when previously absent).  This is deliberately
    not described as power-loss atomicity: a filesystem has no multi-file
    transaction here, so sudden process/host loss can still expose a mixed tuple.
    """
    filenames = ("api_key", "api_secret", "bybit_endpoint")
    if set(values) != set(filenames):
        raise ValueError("credential bundle must contain exactly three files")
    old_values = {name: _read_key_file_bytes(slot, name) for name in filenames}
    try:
        for name in filenames:
            _write_key_file(slot, name, values[name])
    except (OSError, PermissionError, ValueError) as write_error:
        rollback_errors: list[BaseException] = []
        for name in reversed(filenames):
            try:
                old_value = old_values[name]
                if old_value is None:
                    _remove_key_file(slot, name)
                else:
                    _write_key_file(slot, name, old_value)
            except (OSError, PermissionError, ValueError) as rollback_error:
                rollback_errors.append(rollback_error)
        if rollback_errors:
            logger.critical(
                "operation=credential_bundle_rollback status=failed error_count=%d",
                len(rollback_errors),
            )
            raise OSError("credential bundle rollback failed") from write_error
        raise


def _coerce_env_bool(raw: str | None, *, default: bool = False) -> bool:
    """Parse shell-style boolean env values. / 解析 shell 風格布林值。"""
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _ENV_TRUTHY:
        return True
    if value in _ENV_FALSEY:
        return False
    return default


def _paper_engine_env_file() -> Path:
    """Resolve the operator environment file used by restart_all.sh.
    解析 restart_all.sh 會讀取的 operator environment file。

    Test override order:
      1. OPENCLAW_BASIC_SYSTEM_ENV_FILE
      2. OPENCLAW_SECRETS_ROOT/environment_files/basic_system_services.env
      3. ~/BybitOpenClaw/secrets/environment_files/basic_system_services.env
    """
    explicit = os.environ.get("OPENCLAW_BASIC_SYSTEM_ENV_FILE")
    if explicit:
        return Path(explicit).expanduser()
    secrets_root = os.environ.get("OPENCLAW_SECRETS_ROOT")
    if secrets_root:
        return Path(secrets_root).expanduser() / "environment_files" / _BASIC_SYSTEM_ENV_FILE
    return Path.home() / "BybitOpenClaw" / "secrets" / "environment_files" / _BASIC_SYSTEM_ENV_FILE


def _trading_services_env_file() -> Path:
    """Resolve the operator env file read by the Bybit connector service."""
    explicit = os.environ.get("OPENCLAW_TRADING_SERVICES_ENV_FILE")
    if explicit:
        return Path(explicit).expanduser()
    secrets_root = os.environ.get("OPENCLAW_SECRETS_ROOT")
    if secrets_root:
        return Path(secrets_root).expanduser() / "environment_files" / _TRADING_SERVICES_ENV_FILE
    return Path.home() / "BybitOpenClaw" / "secrets" / "environment_files" / _TRADING_SERVICES_ENV_FILE


def _read_env_file_value(path: Path, key: str) -> str | None:
    """Read a KEY=value assignment without sourcing the file. / 不 source 文件讀 KEY=value。"""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, PermissionError, OSError):
        return None
    prefix = key + "="
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export " + prefix):
            value = stripped[len("export " + prefix):].strip()
        elif stripped.startswith(prefix):
            value = stripped[len(prefix):].strip()
        else:
            continue
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        return value
    return None


def _write_env_file_value(path: Path, key: str, value: str) -> None:
    """Upsert KEY=value in an env file with restrictive permissions.
    以嚴格權限在 env file 中 upsert KEY=value。
    """
    if "\n" in key + value or "\r" in key + value or "\x00" in key + value:
        raise ValueError("invalid_env_assignment")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, stat.S_IRWXU)
    except OSError:
        pass

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = []

    prefix = key + "="
    updated = False
    next_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(prefix) or stripped.startswith("export " + prefix):
            next_lines.append(f"{key}={value}")
            updated = True
        else:
            next_lines.append(line)
    if not updated:
        if next_lines and next_lines[-1].strip():
            next_lines.append("")
        next_lines.append(f"{key}={value}")

    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text("\n".join(next_lines).rstrip() + "\n", encoding="utf-8")
    os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    tmp.replace(path)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def _cutover_preflight_location(
    raw_path: str | Path,
) -> tuple[Path, tuple[str, ...], Path]:
    """Return the trusted root, relative components, and lexical candidate."""
    trusted_root = Path(
        os.environ.get("OPENCLAW_CUTOVER_PREFLIGHT_ROOT", "/tmp/openclaw")
    ).expanduser().resolve(strict=True)
    supplied = Path(raw_path).expanduser()
    if ".." in supplied.parts:
        raise ValueError("cutover preflight path contains parent traversal")
    candidate = supplied if supplied.is_absolute() else trusted_root / supplied
    lexical = Path(os.path.abspath(candidate))
    if not trusted_root.is_dir() or supplied.suffix.casefold() != ".json":
        raise ValueError("cutover preflight path is outside policy")
    try:
        relative = lexical.relative_to(trusted_root)
    except ValueError as exc:
        raise ValueError("cutover preflight path is outside policy") from exc
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError("cutover preflight path is outside policy")
    return trusted_root, relative.parts, lexical


def _open_cutover_preflight_fd(path: Path) -> int:
    """Open one final file beneath a trusted directory descriptor."""
    no_follow = getattr(os, "O_NOFOLLOW", None)
    nonblock = getattr(os, "O_NONBLOCK", None)
    directory = getattr(os, "O_DIRECTORY", None)
    if no_follow is None or nonblock is None or directory is None:
        raise OSError("required safe-open flags are unavailable")

    trusted_root, parts, _lexical = _cutover_preflight_location(path)
    directory_flags = os.O_RDONLY | directory | no_follow
    opened_directories: list[int] = []
    try:
        parent_fd = os.open(trusted_root, directory_flags)
        opened_directories.append(parent_fd)
        for component in parts[:-1]:
            parent_fd = os.open(
                component,
                directory_flags,
                dir_fd=parent_fd,
            )
            opened_directories.append(parent_fd)
        return os.open(
            parts[-1],
            os.O_RDONLY | no_follow | nonblock,
            dir_fd=parent_fd,
        )
    finally:
        for directory_fd in reversed(opened_directories):
            os.close(directory_fd)


def _read_cutover_preflight_object(path: Path) -> tuple[dict[str, Any], str]:
    """Read, hash, and parse one bounded regular file through one safe fd."""

    fd = -1
    try:
        fd = _open_cutover_preflight_fd(path)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise OSError("cutover preflight is not a regular file")
        if before.st_size < 0 or before.st_size > _CUTOVER_PREFLIGHT_MAX_BYTES:
            raise OSError("cutover preflight exceeds size bound")

        chunks: list[bytes] = []
        total = 0
        while total <= _CUTOVER_PREFLIGHT_MAX_BYTES:
            chunk = os.read(
                fd,
                min(64 * 1024, _CUTOVER_PREFLIGHT_MAX_BYTES + 1 - total),
            )
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        if total > _CUTOVER_PREFLIGHT_MAX_BYTES:
            raise OSError("cutover preflight exceeds size bound")

        after = os.fstat(fd)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise OSError("cutover preflight changed during read")
        raw = b"".join(chunks)
        payload = json.loads(raw)
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail="Cutover preflight JSON not found")
    except (json.JSONDecodeError, UnicodeError) as exc:
        log_safe_exception(logger, "cutover_preflight_json_read", exc, level=logging.WARNING)
        raise HTTPException(status_code=400, detail="Invalid cutover preflight JSON")
    except (OSError, ValueError) as exc:
        log_safe_exception(logger, "cutover_preflight_file_read", exc, level=logging.WARNING)
        raise HTTPException(status_code=400, detail="Unable to read cutover preflight JSON")
    finally:
        if fd >= 0:
            os.close(fd)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Cutover preflight JSON must be an object")
    return payload, hashlib.sha256(raw).hexdigest()


def _require_preflight_false_answers(answers: dict[str, Any]) -> None:
    required_false = (
        "secret_write_performed",
        "env_mutation_performed",
        "runtime_mutation_performed",
        "service_restart_performed",
        "order_capable_action_allowed_by_this_packet",
        "order_submission_performed",
        "decision_lease_acquire_performed",
        "bybit_private_call_performed",
        "bybit_credential_validation_call_performed",
        "live_or_mainnet",
        "live_authority_granted",
        "global_cost_gate_lowering_recommended",
        "writer_enabled_by_this_packet",
        "adapter_enabled_by_this_packet",
        "promotion_evidence",
        "promotion_proof",
    )
    offenders = [key for key in required_false if answers.get(key) is not False]
    if offenders:
        raise HTTPException(
            status_code=400,
            detail=f"Cutover preflight has unsafe or missing answer flags: {offenders}",
        )
    if answers.get("connector_env_cutover_preview_only") is not True:
        raise HTTPException(
            status_code=400,
            detail="Cutover preflight must be preview-only",
        )


def _credential_blockers_from_cutover_preflight(payload: dict[str, Any]) -> list[str]:
    """返回 connector mode cutover 前必須先清掉的 Demo credential blockers。"""
    readiness = payload.get("readiness")
    if not isinstance(readiness, dict):
        raise HTTPException(status_code=400, detail="Cutover preflight missing readiness")
    blockers = readiness.get("blocking_reasons")
    if not isinstance(blockers, list):
        raise HTTPException(status_code=400, detail="Cutover preflight missing readiness blockers")
    return [
        str(reason)
        for reason in blockers
        if str(reason).startswith("demo_api_slot:")
    ]


def _resolve_cutover_preflight_path(raw_path: str) -> Path:
    try:
        _trusted_root, _parts, lexical = _cutover_preflight_location(raw_path)
    except (OSError, RuntimeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid cutover preflight path")
    return lexical


def _validate_demo_connector_cutover_preflight(
    *,
    preflight_path: Path,
    expected_sha256: str,
    target_env_file: Path,
) -> dict[str, Any]:
    expected_sha256 = expected_sha256.strip().lower()
    if not _SHA256_RE.fullmatch(expected_sha256):
        raise HTTPException(status_code=400, detail="Invalid preflight sha256")

    payload, actual_sha256 = _read_cutover_preflight_object(preflight_path)
    if not hmac_lib.compare_digest(actual_sha256, expected_sha256):
        raise HTTPException(status_code=400, detail="Cutover preflight sha256 mismatch")

    schema_version = payload.get("schema_version") or payload.get("schema")
    if schema_version != _CUTOVER_PREFLIGHT_SCHEMA_VERSION:
        raise HTTPException(status_code=400, detail="Unsupported cutover preflight schema")
    if payload.get("status") != _CUTOVER_PREFLIGHT_READY_STATUS:
        raise HTTPException(status_code=400, detail="Cutover preflight is not ready")

    answers = payload.get("answers")
    if not isinstance(answers, dict):
        raise HTTPException(status_code=400, detail="Cutover preflight missing answers")
    _require_preflight_false_answers(answers)
    if answers.get("main_cost_gate_adjustment") not in (None, "NONE"):
        raise HTTPException(status_code=400, detail="Cutover preflight touches Cost Gate")
    credential_blockers = _credential_blockers_from_cutover_preflight(payload)
    if credential_blockers:
        raise HTTPException(
            status_code=400,
            detail=(
                "Demo credential readiness must be green before connector mode "
                f"cutover: {credential_blockers}"
            ),
        )

    source = payload.get("settings_api_source")
    if not isinstance(source, dict) or source.get("ready") is not True:
        raise HTTPException(status_code=400, detail="Cutover preflight settings source is not ready")
    if source.get("requires_operator_role") is not True:
        raise HTTPException(status_code=400, detail="Cutover preflight lacks operator-role proof")

    cutover = payload.get("connector_env_cutover")
    if not isinstance(cutover, dict):
        raise HTTPException(status_code=400, detail="Cutover preflight missing connector cutover")
    if cutover.get("ready") is not True or cutover.get("status") != "READY":
        raise HTTPException(status_code=400, detail="Connector cutover preflight is not ready")

    preflight_env_path = cutover.get("path")
    if preflight_env_path:
        left = str(Path(str(preflight_env_path)).expanduser())
        right = str(target_env_file.expanduser())
        if left != right:
            raise HTTPException(status_code=400, detail="Cutover preflight env file mismatch")

    proposed = cutover.get("proposed_demo_only")
    if not isinstance(proposed, dict):
        raise HTTPException(status_code=400, detail="Cutover preflight missing proposed Demo env")
    if str(proposed.get(_BYBIT_MODE_ENV_KEY, "")).lower() != "demo":
        raise HTTPException(status_code=400, detail="Cutover preflight mode is not Demo")
    if str(proposed.get(_BYBIT_CONNECTOR_WRITE_ENABLED_ENV_KEY, "")).lower() != "true":
        raise HTTPException(status_code=400, detail="Cutover preflight write flag is not true")

    return {
        "path": str(preflight_path),
        "sha256": actual_sha256,
        "schema_version": schema_version,
        "status": payload.get("status"),
        "connector_env_path": preflight_env_path or "",
        "public_ipv4_for_bybit_api_allowlist": payload.get("public_ipv4_for_bybit_api_allowlist", ""),
    }


# ── Alert config helpers / 告警配置輔助函數 ──


def _alert_data_dir() -> str:
    """告警 config 的儲存目錄 —— 與 watchdog / 引擎共用 OPENCLAW_DATA_DIR。

    為什麼共用：watchdog（獨立進程）與 app 都讀同一個
    <OPENCLAW_DATA_DIR>/alert_config.json，operator 在 GUI 寫一次即生效兩端。
    """
    return os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")


def _alert_config_masked_view(cfg: dict[str, Any]) -> dict[str, Any]:
    """把內部 config 轉成對外安全視圖（永不回明文 token / secret）。

    chat_id 與 urls 屬識別碼 / 端點（非機密），明文回；token / secret 只回
    *_configured 布林 + 遮罩 hint。any_channel_active 反映 enabled 且憑證齊全。
    """
    tg = cfg.get("telegram", {})
    wh = cfg.get("webhook", {})
    tg_token = tg.get("bot_token", "")
    tg_chat = tg.get("chat_id", "")
    wh_urls = wh.get("urls", [])
    wh_secret = wh.get("secret", "")

    telegram_active = bool(tg.get("enabled")) and bool(tg_token) and bool(tg_chat)
    webhook_active = bool(wh.get("enabled")) and len(wh_urls) > 0

    updated_at = cfg.get("updated_at", 0)
    last_modified = int(updated_at) if updated_at else None

    return {
        "telegram": {
            "enabled": bool(tg.get("enabled")),
            "bot_token_configured": bool(tg_token),
            "bot_token_hint": _alert_cfg.mask_secret(tg_token),
            "chat_id": tg_chat,
        },
        "webhook": {
            "enabled": bool(wh.get("enabled")),
            "urls": list(wh_urls),
            "secret_configured": bool(wh_secret),
            "secret_hint": _alert_cfg.mask_secret(wh_secret),
        },
        "any_channel_active": telegram_active or webhook_active,
        "config_present": bool(updated_at),
        "last_modified": last_modified,
    }


def _resolve_repo_root() -> Path:
    """Resolve the canonical repo root for read-only development diagnostics."""
    base_dir = os.environ.get("OPENCLAW_BASE_DIR")
    if base_dir:
        root = Path(base_dir).expanduser().resolve()
        if (root / "sql" / "migrations").is_dir():
            return root
    for parent in Path(__file__).resolve().parents:
        if (parent / "sql" / "migrations").is_dir():
            return parent
    return Path.cwd().resolve()


def _dev_git(root: Path, *args: str) -> str:
    """Run a bounded git read command. Returns empty string on failure."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=1.5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def _migration_phase(version: int) -> str:
    if version <= 8:
        return "foundation"
    if version <= 21:
        return "agent/runtime"
    if version <= 35:
        return "learning/edge"
    if version <= 48:
        return "replay governance"
    if version <= 61:
        return "REF-20/21 hardening"
    return "future"


def _title_from_migration_name(name: str) -> str:
    return name.replace("_", " ").strip()


def _read_text_limited(path: Path, *, max_chars: int = 20000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, PermissionError, OSError):
        return ""
    return text[:max_chars]


def _is_sql_comment_separator(comment: str) -> bool:
    compact = comment.strip()
    return bool(compact) and set(compact) <= {"=", "-", "_", " ", "\t"}


def _extract_migration_purpose(path: Path, fallback: str) -> str:
    """Extract a concise purpose from migration header comments."""
    text = _read_text_limited(path, max_chars=12000)
    if not text:
        return fallback
    purpose: list[str] = []
    fallback_comments: list[str] = []
    capturing = False
    for raw in text.splitlines()[:120]:
        stripped = raw.strip()
        if not stripped:
            if capturing and purpose:
                break
            continue
        if not stripped.startswith("--"):
            if capturing and purpose:
                break
            continue
        comment = stripped[2:].strip()
        if not comment:
            continue
        if _is_sql_comment_separator(comment):
            continue
        if "Purpose" in comment or "目的" in comment:
            capturing = True
            after = comment.split(":", 1)[-1].strip() if ":" in comment else comment
            if after and after.lower() not in {"purpose", "purpose / 目的"}:
                purpose.append(after)
            continue
        if capturing:
            purpose.append(comment)
            if len(" ".join(purpose)) > 260:
                break
        elif len(fallback_comments) < 3 and not comment.startswith("V"):
            fallback_comments.append(comment)
    summary = " ".join(purpose or fallback_comments).strip()
    if not summary:
        summary = fallback
    return summary[:320]


def _extract_migration_objects(path: Path) -> list[str]:
    text = _read_text_limited(path, max_chars=30000)
    if not text:
        return []
    patterns = [
        r"\bCREATE\s+(?:TABLE|VIEW|INDEX|SCHEMA|FUNCTION|TYPE)\s+"
        r"(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z_][\w.]+)",
        r"\bALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?([a-zA-Z_][\w.]+)",
    ]
    objects: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            name = match.group(1).strip().strip('"')
            if name and name not in seen:
                seen.add(name)
                objects.append(name)
            if len(objects) >= 8:
                return objects
    return objects


def _extract_migration_header(path: Path) -> list[str]:
    text = _read_text_limited(path, max_chars=16000)
    if not text:
        return []
    rows: list[str] = []
    for raw in text.splitlines()[:140]:
        stripped = raw.strip()
        if not stripped:
            if rows:
                break
            continue
        if not stripped.startswith("--"):
            break
        comment = stripped[2:].strip()
        if not comment:
            continue
        if _is_sql_comment_separator(comment):
            continue
        rows.append(comment[:260])
        if len(rows) >= 10:
            break
    return rows


def _extract_migration_action_counts(text: str) -> dict[str, int]:
    if not text:
        return {}
    patterns = {
        "create_schema": r"\bCREATE\s+SCHEMA\b",
        "create_table": r"\bCREATE\s+TABLE\b",
        "create_view": r"\bCREATE\s+(?:OR\s+REPLACE\s+)?VIEW\b",
        "create_index": r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\b",
        "create_function": r"\bCREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\b",
        "alter_table": r"\bALTER\s+TABLE\b",
        "grant": r"\bGRANT\b",
        "revoke": r"\bREVOKE\b",
    }
    counts = {
        key: len(re.findall(pattern, text, flags=re.IGNORECASE))
        for key, pattern in patterns.items()
    }
    return {key: count for key, count in counts.items() if count}


def _doc_excerpt(path: Path, *, max_lines: int = 12) -> list[str]:
    text = _read_text_limited(path, max_chars=20000)
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        out.append(line[:260])
        if len(out) >= max_lines:
            break
    return out


def _recent_pm_reports(root: Path, *, limit: int = 8) -> list[dict[str, Any]]:
    reports_dir = root / "docs" / "CCAgentWorkSpace" / "PM" / "workspace" / "reports"
    try:
        reports = [p for p in reports_dir.glob("*.md") if p.is_file()]
    except OSError:
        return []
    reports.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [
        {
            "file": str(path.relative_to(root)),
            "title": path.stem.replace("--", " · ").replace("_", " "),
            "mtime_epoch": int(path.stat().st_mtime),
        }
        for path in reports[:limit]
    ]


def _count_markdown_files(path: Path) -> int:
    try:
        return sum(1 for p in path.rglob("*.md") if p.is_file())
    except OSError:
        return 0


def _fallback_document_inventory() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source": "runtime fallback",
        "policy": {
            "strategy": "index-first; no mass rename until redirects and hot references are stable",
        },
        "target_taxonomy": [
            {"path": "docs/00-active", "purpose": "active status and plan pointers"},
            {"path": "docs/01-architecture", "purpose": "architecture overlays and ADRs"},
            {"path": "docs/02-execution-plans", "purpose": "REF, MAG, sprint, wave, and phase plans"},
            {"path": "docs/03-governance", "purpose": "governance specs, amendments, registers"},
            {"path": "docs/04-audits", "purpose": "audit and verdict reports"},
            {"path": "docs/05-agent-workspace", "purpose": "role workspaces and reports"},
            {"path": "docs/_indexes", "purpose": "machine-readable inventories and redirect maps"},
        ],
        "gui_hot_candidates": {
            "high": [
                {"path": "TODO.md", "surface": "Global Development Status", "integration": "parsed structured data"},
                {"path": "CLAUDE.md", "surface": "Live readiness", "integration": "parsed structured data"},
                {
                    "path": "docs/architecture/multi_agent_rework_2026-05-05/AgentTodo.md",
                    "surface": "Agent Control",
                    "integration": "parsed structured data and OpenClaw status APIs",
                },
            ],
            "medium": [],
            "low": [],
        },
        "phased_execution": [
            "Generate docs/_indexes/document_inventory.json and docs/_indexes/path_redirects.md before moving files.",
            "Build GUI from indexes and parsed active docs before moving hot paths.",
            "Move cold docs first, with redirect stubs for at least one release cycle.",
        ],
        "risk_notes": [
            "Agent boot rules and dispatch files reference fixed paths.",
            "SQL migrations and code comments cite execution plans and reports.",
            "CCAgentWorkSpace report paths are active role conventions.",
        ],
    }


def _build_documentation_inventory_payload(root: Path) -> dict[str, Any]:
    index_dir = root / "docs" / "_indexes"
    inventory_path = index_dir / "document_inventory.json"
    redirects_path = index_dir / "path_redirects.md"
    inventory = _fallback_document_inventory()
    try:
        if inventory_path.is_file():
            loaded = json.loads(inventory_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                inventory = loaded
    except (json.JSONDecodeError, OSError):
        inventory = _fallback_document_inventory()

    live_clusters = []
    for rel in _DOC_CLUSTER_PATHS:
        path = root / rel
        if path.exists():
            live_clusters.append(
                {
                    "path": rel,
                    "markdown_count": _count_markdown_files(path),
                }
            )
    return {
        "index_files": {
            "document_inventory_present": inventory_path.is_file(),
            "path_redirects_present": redirects_path.is_file(),
            "document_inventory": str(inventory_path.relative_to(root)) if inventory_path.is_file() else "",
            "path_redirects": str(redirects_path.relative_to(root)) if redirects_path.is_file() else "",
        },
        "live_counts": {
            "docs_markdown": _count_markdown_files(root / "docs"),
            "memory_markdown": _count_markdown_files(root / "memory"),
            "codex_markdown": _count_markdown_files(root / ".codex"),
            "claude_reports_markdown": _count_markdown_files(root / ".claude_reports"),
        },
        "live_clusters": live_clusters,
        "inventory": inventory,
    }


def _build_development_status_payload() -> dict[str, Any]:
    """Build read-only repository development diagnostics for Support tab."""
    root = _resolve_repo_root()
    migrations_dir = root / "sql" / "migrations"
    migration_by_version: dict[int, Path] = {}
    companions_by_version: dict[int, list[Path]] = {}
    if migrations_dir.is_dir():
        for path in migrations_dir.iterdir():
            if not path.is_file():
                continue
            match = _MIGRATION_FILE_RE.match(path.name)
            if match:
                migration_by_version[int(match.group("version"))] = path
                continue
            companion = _MIGRATION_COMPANION_RE.match(path.name)
            if companion:
                companions_by_version.setdefault(
                    int(companion.group("version")),
                    [],
                ).append(path)

    max_landed = max(migration_by_version.keys(), default=0)
    display_max = max(max_landed, 63)
    items: list[dict[str, Any]] = []
    gaps: list[str] = []
    for version in range(1, display_max + 1):
        path = migration_by_version.get(version)
        version_id = f"V{version:03d}"
        companions = sorted(p.name for p in companions_by_version.get(version, []))
        if path is None:
            status = "future" if version > max_landed else "gap"
            if status == "gap":
                gaps.append(version_id)
            title = "future development slot" if status == "future" else "reserved gap / missing file"
            items.append(
                {
                    "id": version_id,
                    "version": version,
                    "status": status,
                    "file": "",
                    "title": title,
                    "purpose": title,
                    "phase": _migration_phase(version),
                    "objects": [],
                    "companions": companions,
                    "companion_count": len(companions),
                    "header_excerpt": [],
                    "action_counts": {},
                    "line_count": 0,
                    "size_bytes": 0,
                }
            )
            continue
        name = _MIGRATION_FILE_RE.match(path.name).group("name")  # type: ignore[union-attr]
        title = _title_from_migration_name(name)
        text = _read_text_limited(path, max_chars=500000)
        items.append(
            {
                "id": version_id,
                "version": version,
                "status": "landed",
                "file": str(path.relative_to(root)),
                "title": title,
                "purpose": _extract_migration_purpose(path, title),
                "phase": _migration_phase(version),
                "objects": _extract_migration_objects(path),
                "companions": companions,
                "companion_count": len(companions),
                "header_excerpt": _extract_migration_header(path),
                "action_counts": _extract_migration_action_counts(text),
                "line_count": len(text.splitlines()) if text else 0,
                "size_bytes": path.stat().st_size,
            }
        )

    branch = _dev_git(root, "rev-parse", "--abbrev-ref", "HEAD")
    sha = _dev_git(root, "rev-parse", "--short", "HEAD")
    subject = _dev_git(root, "log", "-1", "--pretty=%s")
    dirty_raw = _dev_git(root, "status", "--porcelain")
    dirty_paths = [line[3:] for line in dirty_raw.splitlines() if len(line) > 3]
    recent_commits = [
        {"sha": row.split("\t", 1)[0], "subject": row.split("\t", 1)[1]}
        for row in _dev_git(root, "log", "-5", "--pretty=%h%x09%s").splitlines()
        if "\t" in row
    ]
    latest = items[max_landed - 1] if max_landed and max_landed <= len(items) else None
    return {
        "generated_at_epoch": int(time.time()),
        "repo_root": str(root),
        "migrations_dir": str(migrations_dir.relative_to(root)) if migrations_dir.is_dir() else "",
        "migrations": {
            "display_max_version": display_max,
            "landed_count": len(migration_by_version),
            "companion_count": sum(len(v) for v in companions_by_version.values()),
            "gap_count": len(gaps),
            "gap_versions": gaps,
            "latest": latest,
            "next_version": f"V{max_landed + 1:03d}" if max_landed else "V001",
            "items": items,
        },
        "git": {
            "branch": branch or "unknown",
            "sha": sha or "unknown",
            "subject": subject or "unknown",
            "dirty_count": len(dirty_paths),
            "dirty_paths": dirty_paths[:12],
            "recent_commits": recent_commits,
        },
        "development_context": {
            "todo_excerpt": _doc_excerpt(root / "TODO.md", max_lines=10),
            "agenttodo_excerpt": _doc_excerpt(
                root / "docs" / "architecture" / "multi_agent_rework_2026-05-05" / "AgentTodo.md",
                max_lines=10,
            ),
            "recent_pm_reports": _recent_pm_reports(root),
        },
        "documentation": _build_documentation_inventory_payload(root),
        "runbook": [
            {
                "label": "Focused console static tests",
                "command": (
                    "python3 -m pytest "
                    "program_code/exchange_connectors/bybit_connector/control_api_v1/"
                    "tests/static/test_replay_subtab_static_assets.py -q"
                ),
            },
            {
                "label": "API-only restart",
                "command": "bash helper_scripts/restart_all.sh --api-only",
            },
            {
                "label": "Migration dry-run pattern",
                "command": "psql \"$OPENCLAW_DATABASE_URL\" -v ON_ERROR_STOP=1 -f sql/migrations/V0xx__name.sql",
            },
        ],
    }


def _paper_engine_setting_payload() -> dict[str, Any]:
    """Return configured/runtime Paper engine setting payload for GUI.
    回傳 GUI 所需的 configured/runtime Paper engine 設定。
    """
    env_file = _paper_engine_env_file()
    file_raw = _read_env_file_value(env_file, _PAPER_ENGINE_ENV_KEY)
    runtime_raw = os.environ.get(_PAPER_ENGINE_ENV_KEY)

    if file_raw is not None:
        configured_enabled = _coerce_env_bool(file_raw)
        source = "env_file"
    elif runtime_raw is not None:
        configured_enabled = _coerce_env_bool(runtime_raw)
        source = "process_env"
    else:
        configured_enabled = False
        source = "default_disabled"

    runtime_enabled = _coerce_env_bool(runtime_raw, default=configured_enabled)
    return {
        "enabled": configured_enabled,
        "configured_enabled": configured_enabled,
        "runtime_enabled": runtime_enabled,
        "restart_required": runtime_enabled != configured_enabled,
        "source": source,
        "env_key": _PAPER_ENGINE_ENV_KEY,
        "env_file_present": env_file.exists(),
    }


def _bybit_demo_connector_mode_payload() -> dict[str, Any]:
    """Return persisted/runtime Demo connector mode without exposing secrets."""
    env_file = _trading_services_env_file()
    file_mode = _read_env_file_value(env_file, _BYBIT_MODE_ENV_KEY)
    file_write_raw = _read_env_file_value(env_file, _BYBIT_CONNECTOR_WRITE_ENABLED_ENV_KEY)
    runtime_mode = os.environ.get(_BYBIT_MODE_ENV_KEY)
    runtime_write_raw = os.environ.get(_BYBIT_CONNECTOR_WRITE_ENABLED_ENV_KEY)

    configured_ready = (
        str(file_mode or "").strip().lower() == "demo"
        and _coerce_env_bool(file_write_raw, default=False)
    )
    runtime_ready = (
        str(runtime_mode or "").strip().lower() == "demo"
        and _coerce_env_bool(runtime_write_raw, default=False)
    )
    return {
        "enabled": configured_ready,
        "configured_ready": configured_ready,
        "runtime_ready": runtime_ready,
        "restart_required": configured_ready != runtime_ready,
        "env_file": str(env_file),
        "env_file_present": env_file.exists(),
        "configured": {
            _BYBIT_MODE_ENV_KEY: file_mode,
            _BYBIT_CONNECTOR_WRITE_ENABLED_ENV_KEY: file_write_raw,
        },
        "runtime": {
            _BYBIT_MODE_ENV_KEY: runtime_mode,
            _BYBIT_CONNECTOR_WRITE_ENABLED_ENV_KEY: runtime_write_raw,
        },
        "scope": "bybit_demo_connector_mode_only",
        "boundary": {
            "demo_only": True,
            "live_or_mainnet": False,
            "secret_write_performed": False,
            "service_restart_performed": False,
            "bybit_private_call_performed": False,
            "order_capable_action_allowed_by_this_packet": False,
            "global_cost_gate_lowering_recommended": False,
        },
    }


def _development_support_mode_payload() -> dict[str, Any]:
    """Return the development support visibility setting payload.

    This setting controls only the support/status surface visibility. It does
    not affect engine runtime, trading authority, risk config, live auth, or
    restart behavior.
    """
    env_file = _paper_engine_env_file()
    file_raw = _read_env_file_value(env_file, _DEVELOPMENT_SUPPORT_MODE_ENV_KEY)
    legacy_file_raw = _read_env_file_value(env_file, _LEGACY_GUI_DEVELOPMENT_MODE_ENV_KEY)
    runtime_raw = os.environ.get(_DEVELOPMENT_SUPPORT_MODE_ENV_KEY)
    legacy_runtime_raw = os.environ.get(_LEGACY_GUI_DEVELOPMENT_MODE_ENV_KEY)

    if file_raw is not None:
        enabled = _coerce_env_bool(file_raw)
        source = "env_file"
    elif legacy_file_raw is not None:
        enabled = _coerce_env_bool(legacy_file_raw)
        source = "legacy_env_file"
    elif runtime_raw is not None:
        enabled = _coerce_env_bool(runtime_raw)
        source = "process_env"
    elif legacy_runtime_raw is not None:
        enabled = _coerce_env_bool(legacy_runtime_raw)
        source = "legacy_process_env"
    else:
        enabled = False
        source = "default_disabled"

    return {
        "enabled": enabled,
        "configured_enabled": enabled,
        "restart_required": False,
        "source": source,
        "env_key": _DEVELOPMENT_SUPPORT_MODE_ENV_KEY,
        "legacy_env_key": _LEGACY_GUI_DEVELOPMENT_MODE_ENV_KEY,
        "env_file_present": env_file.exists(),
        "scope": "development_support_visibility_only",
        "surface": "global_development_status_support",
    }


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
        return False, "invalid_credentials"
    if not api_secret or len(api_secret) < 8:
        return False, "invalid_credentials"

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
        except Exception as parse_exc:
            log_safe_exception(logger, "bybit_credential_http_response_parse", parse_exc)
            return False, "validation_unavailable"
    except urllib.error.URLError as exc:
        log_safe_exception(logger, "bybit_credential_network_request", exc)
        return False, "validation_unavailable"
    except Exception as exc:
        log_safe_exception(logger, "bybit_credential_validation", exc)
        return False, "validation_unavailable"

    if not isinstance(body, dict):
        logger.error("operation=bybit_credential_response_shape error=invalid_object")
        return False, "validation_unavailable"

    ret_code = body.get("retCode", -1)

    if ret_code == 0:
        return True, ""
    # retCode 10003 = invalid API key, 10004 = invalid signature, etc.
    # retCode 10003 = 無效 API key，10004 = 無效簽名，等
    return False, "invalid_credentials"


def _validation_status_from_error(error: str) -> str:
    """
    Classify validation failures for UI severity.
    將驗證失敗分類為 UI 嚴重程度。
    """
    if error == "validation_unavailable":
        return "validation_unavailable"
    return "invalid"


def _public_validation_error(error: str) -> tuple[str, str]:
    """Map internal validation categories to stable, non-sensitive client text."""
    status = _validation_status_from_error(error)
    if status == "validation_unavailable":
        return status, "Credential validation unavailable"
    return status, "Credential validation failed"


def _api_key_validation_state(
    *,
    has_key: bool,
    api_key: str,
    api_secret: str,
    slot: str,
    validate: bool,
) -> dict[str, Any]:
    """
    Build optional validation metadata for API key status responses.
    建立 API key 狀態回應的可選驗證資訊。
    """
    if not has_key:
        return {
            "validated": False,
            "validation_status": "not_configured",
            "validation_error": "",
        }
    if not validate:
        return {
            "validated": None,
            "validation_status": "not_checked",
            "validation_error": "",
        }

    is_valid, err_msg = _validate_bybit_credentials(api_key, api_secret, slot)
    if is_valid:
        return {
            "validated": True,
            "validation_status": "valid",
            "validation_error": "",
        }

    validation_status, public_error = _public_validation_error(err_msg)
    return {
        "validated": False,
        "validation_status": validation_status,
        "validation_error": public_error,
    }


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


class PaperEngineSettingRequest(BaseModel):
    """Request body for POST /api/v1/settings/paper-engine."""
    enabled: bool = Field(
        ...,
        description="Whether the legacy Paper engine GUI/backend path is enabled",
    )


class BybitDemoConnectorModeRequest(BaseModel):
    """Request body for POST /api/v1/settings/bybit-demo-connector-mode."""
    cutover_preflight_json: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="Machine-checkable bounded Demo cutover preflight artifact path",
    )
    cutover_preflight_sha256: str = Field(
        ...,
        min_length=64,
        max_length=64,
        description="Expected sha256 for the cutover preflight artifact",
    )
    confirm: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Exact Demo-only connector mode confirmation string",
    )


class DevelopmentSupportSettingRequest(BaseModel):
    """Request body for POST /api/v1/settings/development-mode."""
    enabled: bool = Field(
        ...,
        description="Whether global development support surfaces are visible",
    )


# ── Alert config request models / 告警配置請求模型 ──
# PARTIAL-SAFE 語義：bot_token / secret 留空字串 = 保留原值；sentinel "__CLEAR__" = 清除。
# 所有欄位皆 optional —— operator 可只更新單一通道。


class AlertTelegramRequest(BaseModel):
    enabled: bool | None = Field(default=None)
    bot_token: str | None = Field(default=None, max_length=512)
    chat_id: str | None = Field(default=None, max_length=128)


class AlertWebhookRequest(BaseModel):
    enabled: bool | None = Field(default=None)
    urls: list[str] | None = Field(default=None)
    secret: str | None = Field(default=None, max_length=512)


class AlertConfigSaveRequest(BaseModel):
    """Request body for POST /api/v1/settings/alerts."""
    telegram: AlertTelegramRequest | None = Field(default=None)
    webhook: AlertWebhookRequest | None = Field(default=None)


# ═══════════════════════════════════════════════════════════════════════════════
# Endpoints / 端點
# ═══════════════════════════════════════════════════════════════════════════════


@settings_router.get("/api-key/{slot}")
async def get_api_key_status(
    slot: str,
    validate: bool = Query(default=False),
    actor: Any = Depends(_get_auth_actor),
) -> dict:
    """
    GET /api/v1/settings/api-key/{slot}
    返回 API key 槽位狀態（遮罩 hint，永不返回明文）

    Returns masked hint of the stored API key — never returns plaintext.
    Returns has_key=False if no key is stored for this slot.
    If validate=true, performs the same read-only Bybit credential check used by POST.

    返回已存儲 API key 的遮罩 hint，永不返回明文。
    槽位無 key 時 has_key=False。
    validate=true 時執行與 POST 相同的 Bybit 只讀憑證驗證。
    """
    if slot not in ALLOWED_SLOTS:
        raise HTTPException(status_code=400, detail=f"Invalid slot '{slot}'. Allowed: {sorted(ALLOWED_SLOTS)}")

    api_key = _read_key_file(slot, "api_key")
    api_secret = _read_key_file(slot, "api_secret")
    has_key = bool(api_key and api_secret)

    # Compute last_modified from the key file mtime / 從文件 mtime 獲取最後修改時間
    last_modified: str | None = None
    try:
        mtime = _secret_file_mtime(slot, "api_key")
        if mtime is not None:
            last_modified = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(mtime))
    except (OSError, PermissionError, ValueError):
        pass

    validation_state = _api_key_validation_state(
        has_key=has_key,
        api_key=api_key,
        api_secret=api_secret,
        slot=slot,
        validate=validate,
    )

    return {
        "slot": slot,
        "has_key": has_key,
        "key_hint": _mask_key(api_key) if api_key else "",
        "last_modified": last_modified,
        **validation_state,
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
            validation_status, public_error = _public_validation_error(err_msg)
            logger.warning(
                "operation=bybit_key_validation slot=%s validation_status=%s actor=%s",
                slot, validation_status, getattr(actor, "actor_id", "?"),
            )
            return {
                "saved": False,
                "validated": False,
                "key_hint": "",
                "error": public_error,
            }

        # Write to secrets directory / 寫入 secrets 目錄
        # Also write bybit_endpoint metadata so Rust knows which server to connect to.
        # live_demo slot → demo server; live slot → mainnet; demo slot → demo (informational).
        # 同時寫入 bybit_endpoint 元數據，讓 Rust 知道連哪個伺服器。
        # live_demo 槽 → demo 伺服器；live 槽 → 主網；demo 槽 → demo（參考用）。
        _SLOT_ENDPOINT: dict[str, str] = {"demo": "demo", "live_demo": "demo", "live": "mainnet"}
        try:
            _write_credential_bundle(
                slot,
                {
                    "api_key": api_key,
                    "api_secret": api_secret,
                    "bybit_endpoint": _SLOT_ENDPOINT.get(slot, "mainnet"),
                },
            )
        except (OSError, PermissionError, ValueError) as exc:
            log_safe_exception(logger, "api_key_persist", exc)
            raise HTTPException(status_code=500, detail="Failed to persist API key. Check server logs.")

        key_hint = _mask_key(api_key)
        logger.info(
            "API key saved for slot '%s' (actor: %s)",
            slot, getattr(actor, "actor_id", "?"),
        )

        return {
            "saved": True,
            "validated": True,
            "key_hint": key_hint,
            "slot": slot,
        }


@settings_router.get("/paper-engine")
async def get_paper_engine_setting(
    actor: Any = Depends(_get_auth_actor),
) -> dict:
    """
    GET /api/v1/settings/paper-engine
    Return the configured legacy Paper engine visibility/runtime setting.

    The default is disabled when no persisted value exists. ``enabled`` is the
    configured GUI truth; ``runtime_enabled`` is the current process value, so
    a settings write can correctly report that restart is needed.
    """
    return _paper_engine_setting_payload()


@settings_router.post("/paper-engine")
async def save_paper_engine_setting(
    body: PaperEngineSettingRequest,
    actor: Any = Depends(_require_operator_auth),
) -> dict:
    """
    POST /api/v1/settings/paper-engine
    Persist the legacy Paper engine toggle into the restart_all.sh env file.

    This intentionally does not restart services. The response includes
    ``restart_required`` when the running process still differs from the
    persisted setting.
    """
    value = "1" if body.enabled else "0"
    try:
        _write_env_file_value(_paper_engine_env_file(), _PAPER_ENGINE_ENV_KEY, value)
    except (OSError, PermissionError, ValueError) as exc:
        log_safe_exception(logger, "paper_engine_setting_persist", exc)
        raise HTTPException(status_code=500, detail="Failed to persist Paper engine setting")

    payload = _paper_engine_setting_payload()
    logger.info(
        "Paper engine setting updated enabled=%s runtime_enabled=%s restart_required=%s actor=%s",
        payload["enabled"],
        payload["runtime_enabled"],
        payload["restart_required"],
        getattr(actor, "actor_id", "?"),
    )
    return payload


@settings_router.get("/bybit-demo-connector-mode")
async def get_bybit_demo_connector_mode(
    actor: Any = Depends(_get_auth_actor),
) -> dict:
    """
    GET /api/v1/settings/bybit-demo-connector-mode
    Return persisted/runtime Bybit Demo connector mode state.

    This endpoint is read-only. It does not inspect or return API key/secret
    material and does not grant order, lease, risk, live, or Cost Gate authority.
    """
    return _bybit_demo_connector_mode_payload()


@settings_router.post("/bybit-demo-connector-mode")
async def save_bybit_demo_connector_mode(
    body: BybitDemoConnectorModeRequest,
    actor: Any = Depends(_require_operator_auth),
) -> dict:
    """
    POST /api/v1/settings/bybit-demo-connector-mode
    Persist the reviewed Demo-only Bybit connector mode cutover.

    Guardrails:
    - requires Operator auth and an exact confirmation string
    - requires a machine-checkable cutover preflight JSON with matching sha256
    - writes only BYBIT_MODE=demo and BYBIT_CONNECTOR_WRITE_ENABLED=true
    - does not write secrets, restart services, call Bybit, acquire leases, or submit orders
    """
    if body.confirm != _BYBIT_DEMO_CONNECTOR_MODE_CONFIRM:
        raise HTTPException(status_code=400, detail="Invalid Demo connector mode confirmation")

    env_file = _trading_services_env_file()
    preflight = _validate_demo_connector_cutover_preflight(
        preflight_path=_resolve_cutover_preflight_path(body.cutover_preflight_json),
        expected_sha256=body.cutover_preflight_sha256,
        target_env_file=env_file,
    )

    try:
        _write_env_file_value(env_file, _BYBIT_MODE_ENV_KEY, "demo")
        _write_env_file_value(env_file, _BYBIT_CONNECTOR_WRITE_ENABLED_ENV_KEY, "true")
    except (OSError, PermissionError, ValueError) as exc:
        log_safe_exception(logger, "bybit_demo_connector_mode_persist", exc)
        raise HTTPException(status_code=500, detail="Failed to persist Bybit Demo connector mode")

    payload = _bybit_demo_connector_mode_payload()
    payload.update(
        {
            "saved": True,
            "cutover_preflight": preflight,
            "answers": {
                "secret_write_performed": False,
                "env_mutation_performed": True,
                "runtime_mutation_performed": False,
                "service_restart_performed": False,
                "bybit_private_call_performed": False,
                "bybit_credential_validation_call_performed": False,
                "decision_lease_acquire_performed": False,
                "order_capable_action_allowed_by_this_packet": False,
                "order_submission_performed": False,
                "live_or_mainnet": False,
                "global_cost_gate_lowering_recommended": False,
            },
        }
    )
    logger.info(
        "Bybit Demo connector mode persisted restart_required=%s actor=%s preflight_sha=%s",
        payload["restart_required"],
        getattr(actor, "actor_id", "?"),
        preflight["sha256"],
    )
    return payload


@settings_router.get("/development-mode")
async def get_development_mode_setting(
    actor: Any = Depends(_get_auth_actor),
) -> dict:
    """
    GET /api/v1/settings/development-mode
    Return the development support visibility setting.

    Kept as a compatibility endpoint for the prior GUI build. Current static
    pages use browser-local storage so an old running process cannot turn this
    support toggle into a 404.
    """
    return _development_support_mode_payload()


@settings_router.get("/development-status")
async def get_development_status(
    actor: Any = Depends(_get_auth_actor),
) -> dict:
    """
    GET /api/v1/settings/development-status
    Return read-only repository development diagnostics for the Support tab.

    This endpoint scans source-controlled migrations and handoff documents at
    request time, so V064+ files appear without front-end changes.
    """
    return _build_development_status_payload()


@settings_router.post("/development-mode")
async def save_development_mode_setting(
    body: DevelopmentSupportSettingRequest,
    actor: Any = Depends(_require_operator_auth),
) -> dict:
    """
    POST /api/v1/settings/development-mode
    Persist the development support visibility toggle.

    Enabling exposes the Support tab and development-only status/control
    surfaces. Disabling hides them. No service restart is required.
    """
    value = "1" if body.enabled else "0"
    try:
        _write_env_file_value(
            _paper_engine_env_file(),
            _DEVELOPMENT_SUPPORT_MODE_ENV_KEY,
            value,
        )
    except (OSError, PermissionError, ValueError) as exc:
        log_safe_exception(logger, "development_support_setting_persist", exc)
        raise HTTPException(status_code=500, detail="Failed to persist development support setting")

    payload = _development_support_mode_payload()
    logger.info(
        "Development support mode updated enabled=%s actor=%s",
        payload["enabled"],
        getattr(actor, "actor_id", "?"),
    )
    return payload


# ═══════════════════════════════════════════════════════════════════════════════
# Alert config endpoints / 告警配置端點
# ═══════════════════════════════════════════════════════════════════════════════
# operator 在 GUI 設定 Telegram / Webhook 憑證，寫進 <data_dir>/alert_config.json；
# app alerter 與獨立 watchdog 都從這個檔讀。GET 永不回明文；POST partial-safe。


@settings_router.get("/alerts")
async def get_alert_config(
    actor: Any = Depends(_get_auth_actor),
) -> dict:
    """
    GET /api/v1/settings/alerts
    返回告警配置狀態（遮罩 token / secret，永不回明文）。

    bot_token / secret 只回 *_configured + 遮罩 hint；chat_id / urls 屬識別碼明文回。
    """
    cfg = _alert_cfg.load_alert_config(_alert_data_dir())
    return _alert_config_masked_view(cfg)


@settings_router.post("/alerts")
async def save_alert_config_endpoint(
    body: AlertConfigSaveRequest,
    actor: Any = Depends(_require_operator_auth),
) -> dict:
    """
    POST /api/v1/settings/alerts
    保存告警配置（partial-safe，寫入 chmod 600）。

    PARTIAL-SAFE：bot_token / secret 留空字串 = 保留原值（與 stored 合併）；
    sentinel "__CLEAR__" = 清除該值。驗證：
      - telegram.enabled → 合併後 token + chat_id 皆非空
      - webhook.enabled → urls 非空，每個 url 通過 SSRF 守衛 validate_webhook_url
      - 拒絕控制字元 \\n \\r \\x00；urls ≤ 10
    驗證失敗回 400（安全訊息，永不 echo 明文）。
    """
    data_dir = _alert_data_dir()
    # 讀出 stored 作為 partial-merge 基底；env-fallback 已併入（不影響合併語義）。
    stored = _alert_cfg.load_alert_config(data_dir)

    merged_tg = dict(stored["telegram"])
    merged_wh = dict(stored["webhook"])

    # ── Telegram 合併 ──
    if body.telegram is not None:
        tg = body.telegram
        if tg.enabled is not None:
            merged_tg["enabled"] = bool(tg.enabled)
        merged_tg["bot_token"] = _merge_secret_field(
            tg.bot_token, merged_tg.get("bot_token", ""), field="bot_token",
        )
        if tg.chat_id is not None:
            chat = tg.chat_id.strip()
            if _alert_cfg.has_control_chars(chat):
                raise HTTPException(status_code=400, detail="chat_id contains invalid characters")
            merged_tg["chat_id"] = "" if chat == _alert_cfg.CLEAR_SENTINEL else chat

    # ── Webhook 合併 ──
    if body.webhook is not None:
        wh = body.webhook
        if wh.enabled is not None:
            merged_wh["enabled"] = bool(wh.enabled)
        merged_wh["secret"] = _merge_secret_field(
            wh.secret, merged_wh.get("secret", ""), field="secret",
        )
        if wh.urls is not None:
            merged_wh["urls"] = _sanitize_webhook_urls(wh.urls)

    # ── enabled 前置條件驗證（fail-closed：要啟用必須憑證齊全且 URL 安全）──
    if merged_tg.get("enabled"):
        if not merged_tg.get("bot_token") or not merged_tg.get("chat_id"):
            raise HTTPException(
                status_code=400,
                detail="Telegram requires both bot_token and chat_id to be set",
            )
    if merged_wh.get("enabled"):
        urls = merged_wh.get("urls", [])
        if not urls:
            raise HTTPException(status_code=400, detail="Webhook requires at least one URL")
        for url in urls:
            ok, reason = _alert_cfg.validate_webhook_url(url)
            if not ok:
                # reason 為安全原因碼（不含使用者輸入回顯）。
                raise HTTPException(
                    status_code=400, detail=f"Invalid webhook URL ({reason})",
                )

    new_cfg = {
        "version": 1,
        "telegram": merged_tg,
        "webhook": merged_wh,
    }
    try:
        _alert_cfg.save_alert_config(data_dir, new_cfg)
    except (OSError, PermissionError) as exc:
        log_safe_exception(logger, "alert_config_persist", exc)
        raise HTTPException(status_code=500, detail="Failed to persist alert config")

    logger.info(
        "Alert config updated telegram_enabled=%s webhook_enabled=%s actor=%s",
        merged_tg.get("enabled"),
        merged_wh.get("enabled"),
        getattr(actor, "actor_id", "?"),
    )
    # 回讀（含原子寫入後的 updated_at），轉成遮罩視圖。
    saved = _alert_cfg.load_alert_config(data_dir)
    view = _alert_config_masked_view(saved)
    view["saved"] = True
    return view


@settings_router.post("/alerts/test")
async def test_alert_config(
    actor: Any = Depends(_require_operator_auth),
) -> dict:
    """
    POST /api/v1/settings/alerts/test
    透過已啟用通道發送一條真實的良性測試告警（走 app 同一 alerter 路徑）。

    per-process 節流 ≥ 10 秒；error 經過 sanitize + 截斷 ≤ 200 字元。
    """
    global _alert_test_last_ts
    async with _alert_test_lock:
        now = time.monotonic()
        if now - _alert_test_last_ts < _ALERT_TEST_MIN_INTERVAL_SECONDS:
            wait = _ALERT_TEST_MIN_INTERVAL_SECONDS - (now - _alert_test_last_ts)
            raise HTTPException(
                status_code=429,
                detail=f"Test alert rate-limited; retry in {wait:.0f}s",
            )
        _alert_test_last_ts = now

    cfg = _alert_cfg.load_alert_config(_alert_data_dir())
    tg = cfg.get("telegram", {})
    wh = cfg.get("webhook", {})
    tg_active = bool(tg.get("enabled")) and bool(tg.get("bot_token")) and bool(tg.get("chat_id"))
    wh_active = bool(wh.get("enabled")) and len(wh.get("urls", [])) > 0

    result = {
        "telegram": {"attempted": tg_active, "ok": False, "error": None},
        "webhook": {"attempted": wh_active, "ok": False, "error": None},
    }

    # 走 app 同一 alerter 路徑：用 GUI config 直接構造一次性 alerter，send() 同步回布林。
    # 為什麼一次性構造而非用全域 ALERT_ROUTER：ALERT_ROUTER 在進程啟動時建立，可能
    # 早於 operator 在 GUI 寫憑證；測試端點必須反映「當前檔內配置」是否真能送出。
    if tg_active:
        ok, err = await asyncio.to_thread(_send_test_telegram, tg)
        result["telegram"]["ok"] = ok
        result["telegram"]["error"] = err
    if wh_active:
        ok, err = await asyncio.to_thread(_send_test_webhook, wh)
        result["webhook"]["ok"] = ok
        result["webhook"]["error"] = err

    logger.info(
        "Alert test fired telegram=%s/%s webhook=%s/%s actor=%s",
        tg_active, result["telegram"]["ok"],
        wh_active, result["webhook"]["ok"],
        getattr(actor, "actor_id", "?"),
    )
    return result


def _merge_secret_field(incoming: str | None, stored: str, *, field: str) -> str:
    """Partial-safe 合併單一機密欄位（bot_token / secret）。

    None 或空字串 → 保留 stored（「不變更」）；sentinel "__CLEAR__" → 清空；
    其他 → 採新值（先擋控制字元）。
    """
    if incoming is None:
        return stored
    value = incoming.strip()
    if value == "":
        return stored
    if value == _alert_cfg.CLEAR_SENTINEL:
        return ""
    if _alert_cfg.has_control_chars(value):
        raise HTTPException(status_code=400, detail=f"{field} contains invalid characters")
    return value


def _sanitize_webhook_urls(urls: list[str]) -> list[str]:
    """清洗 webhook urls：去空白 / 空項，擋控制字元，限制 ≤ 10。

    sentinel ["__CLEAR__"] 視為清空（回 []）。實際 SSRF 驗證在 enabled 前置條件做
    （只在要啟用時阻擋內網位址，避免 disabled 草稿也被 DNS 解析卡住）。
    """
    if not isinstance(urls, list):
        raise HTTPException(status_code=400, detail="urls must be a list")
    if len(urls) == 1 and isinstance(urls[0], str) and urls[0].strip() == _alert_cfg.CLEAR_SENTINEL:
        return []
    cleaned: list[str] = []
    for u in urls:
        if not isinstance(u, str):
            raise HTTPException(status_code=400, detail="urls must be strings")
        s = u.strip()
        if not s:
            continue
        if _alert_cfg.has_control_chars(s):
            raise HTTPException(status_code=400, detail="webhook URL contains invalid characters")
        cleaned.append(s)
    if len(cleaned) > 10:
        raise HTTPException(status_code=400, detail="At most 10 webhook URLs are allowed")
    return cleaned


def _safe_alert_error(exc: Exception) -> str:
    """把 alerter 例外轉成安全、截斷的錯誤字串（≤ 200，不外洩憑證）。"""
    msg = str(exc) if exc else "send_failed"
    return msg[:200]


def _send_test_telegram(tg: dict[str, Any]) -> tuple[bool, str | None]:
    """用 GUI config 構造一次性 TelegramAlerter，發送測試告警（同步）。

    走 app 同一 alerter 的 send() 路徑（非便捷 send_async，因測試需同步回布林）。
    """
    try:
        from .telegram_alerter import TelegramAlerter

        alerter = TelegramAlerter(
            bot_token=tg.get("bot_token", ""),
            chat_id=tg.get("chat_id", ""),
        )
        ok = alerter.send("🔔 <b>System</b>\nTEST\n<i>OpenClaw alert test</i>")
        return bool(ok), None if ok else "telegram_send_returned_false"
    except Exception as exc:  # noqa: BLE001 - 測試端點不得因 alerter 例外而 500
        return False, _safe_alert_error(exc)


def _send_test_webhook(wh: dict[str, Any]) -> tuple[bool, str | None]:
    """用 GUI config 構造一次性 WebhookAlerter，發送測試告警（同步）。"""
    try:
        from .webhook_alerter import WebhookAlerter

        alerter = WebhookAlerter(
            urls=list(wh.get("urls", [])),
            secret=wh.get("secret", ""),
        )
        ok = alerter.send({
            "type": "system", "event": "TEST", "detail": "OpenClaw alert test",
            "timestamp_ms": int(time.time() * 1000),
        })
        return bool(ok), None if ok else "webhook_send_returned_false"
    except Exception as exc:  # noqa: BLE001 - 測試端點不得因 alerter 例外而 500
        return False, _safe_alert_error(exc)
