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
import re
import stat
import subprocess
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

# Legacy Paper engine process toggle. The Rust engine reads this at process
# startup; the GUI reads the persisted setting immediately to decide whether
# to expose the legacy Paper tab.
# Legacy Paper engine 進程開關。Rust engine 啟動時讀取；GUI 立即讀取持久化
# 設定，以決定是否顯示 legacy Paper tab。
_PAPER_ENGINE_ENV_KEY = "OPENCLAW_ENABLE_PAPER"
_DEVELOPMENT_SUPPORT_MODE_ENV_KEY = "OPENCLAW_DEVELOPMENT_SUPPORT_MODE"
_LEGACY_GUI_DEVELOPMENT_MODE_ENV_KEY = "OPENCLAW_GUI_DEVELOPMENT_MODE"
_BASIC_SYSTEM_ENV_FILE = "basic_system_services.env"
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


class PaperEngineSettingRequest(BaseModel):
    """Request body for POST /api/v1/settings/paper-engine."""
    enabled: bool = Field(
        ...,
        description="Whether the legacy Paper engine GUI/backend path is enabled",
    )


class DevelopmentSupportSettingRequest(BaseModel):
    """Request body for POST /api/v1/settings/development-mode."""
    enabled: bool = Field(
        ...,
        description="Whether global development support surfaces are visible",
    )


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
        logger.error("Failed to persist paper engine setting: %s", exc)
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
        logger.error("Failed to persist development support setting: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to persist development support setting")

    payload = _development_support_mode_payload()
    logger.info(
        "Development support mode updated enabled=%s actor=%s",
        payload["enabled"],
        getattr(actor, "actor_id", "?"),
    )
    return payload
