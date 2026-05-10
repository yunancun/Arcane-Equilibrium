"""
provider_keys_store
═══════════════════════════════════════════════════════════════════════════════
AI 供應商 API Key 持久化模組（Control API GUI Tab-AI 後端支撐）。

職責邊界：
  - 持久化 / 讀取 / 刪除 GUI 提交的 API Key
  - 將寫入動作同步到當前進程 env（Anthropic 走 ANTHROPIC_API_KEY）
  - 對外只回 status（masked / boolean），永不回明文
  - 不負責 L2 推理路由（DeepSeek/OpenAI/Google/Perplexity 客戶端尚未實裝；
    本模組僅落地存儲層，client_implemented=False 由 status() 顯式標記）

跨平台路徑解析（CLAUDE.md §七 .★★.1）：
  優先級：
    1. OPENCLAW_PROVIDER_KEYS_DIR（顯式覆寫）
    2. <OPENCLAW_SECRETS_ROOT>/providers/  （與其他 secrets 一致）
    3. ~/BybitOpenClaw/secrets/providers/  （前端 hint 的預設路徑）
  目錄不存在時自動建立（mode=0700）；檔案以 0600 寫入。

Provider 白名單：
  anthropic / openai / deepseek / perplexity / google / local_llm
  非白名單一律 reject（防 path traversal）。

格式驗證（與前端 KEY_FORMATS 一致）：
  anthropic   sk-ant-...   minLen 20
  openai      sk-...       minLen 20
  deepseek    sk-...       minLen 20
  perplexity  pplx-...     minLen 20
  google      （無前綴）    minLen 20
  local_llm   http(s)://   minLen 8
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ─── Provider 白名單與格式規則 ──────────────────────────────────────

PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OPENAI = "openai"
PROVIDER_DEEPSEEK = "deepseek"
PROVIDER_PERPLEXITY = "perplexity"
PROVIDER_GOOGLE = "google"
PROVIDER_LOCAL_LLM = "local_llm"

ALLOWED_PROVIDERS: frozenset[str] = frozenset({
    PROVIDER_ANTHROPIC,
    PROVIDER_OPENAI,
    PROVIDER_DEEPSEEK,
    PROVIDER_PERPLEXITY,
    PROVIDER_GOOGLE,
    PROVIDER_LOCAL_LLM,
})


@dataclass(frozen=True)
class _ProviderSpec:
    env_var: str            # 對應的環境變數名（runtime 注入用）
    prefix: str | None      # key 必需前綴；None = 無
    min_len: int            # key 最小長度
    description: str        # 顯示用說明
    client_implemented: bool  # 後端推理客戶端是否已實裝
    is_url: bool = False    # local_llm 為 URL 而非 API key


_SPECS: dict[str, _ProviderSpec] = {
    PROVIDER_ANTHROPIC: _ProviderSpec(
        env_var="ANTHROPIC_API_KEY",
        prefix="sk-ant-",
        min_len=20,
        description="Claude Opus 4.7 / Sonnet 4.6 / Haiku 4.5",
        client_implemented=True,  # layer2_engine._get_anthropic_client 已實裝
    ),
    PROVIDER_OPENAI: _ProviderSpec(
        env_var="OPENAI_API_KEY",
        prefix="sk-",
        min_len=20,
        description="GPT-4o / GPT-4o-mini / o1（provider_client OpenAICompat）",
        client_implemented=True,  # provider_client.OpenAICompatProvider 已實裝
    ),
    PROVIDER_DEEPSEEK: _ProviderSpec(
        env_var="DEEPSEEK_API_KEY",
        prefix="sk-",
        min_len=20,
        description="DeepSeek V4 Flash / V4 Pro",
        client_implemented=True,  # provider_client.OpenAICompatProvider + base_url=api.deepseek.com
    ),
    PROVIDER_PERPLEXITY: _ProviderSpec(
        env_var="PERPLEXITY_API_KEY",
        prefix="pplx-",
        min_len=20,
        description="搜索专用 — Scout 工具用，非 L2 推理",
        client_implemented=False,  # 走 layer2_tools 的 search provider 路徑（不是 L2 推理 client）
    ),
    PROVIDER_GOOGLE: _ProviderSpec(
        env_var="GOOGLE_API_KEY",
        prefix=None,
        min_len=20,
        description="Gemini 1.5 Pro / Flash",
        client_implemented=False,
    ),
    PROVIDER_LOCAL_LLM: _ProviderSpec(
        env_var="LOCAL_LLM_BASE_URL",
        prefix="http",
        min_len=8,
        description="Ollama / LM Studio (URL)",
        client_implemented=True,  # local_llm_factory 已實裝（走 OLLAMA/LM_STUDIO BASE_URL）
        is_url=True,
    ),
}

_PROVIDER_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


# ─── 路徑解析 ────────────────────────────────────────────────────────

def _resolve_keys_dir() -> Path:
    """解析 provider keys 目錄。確保目錄存在 + mode=0700。"""
    explicit = os.environ.get("OPENCLAW_PROVIDER_KEYS_DIR")
    if explicit:
        base = Path(explicit).expanduser()
    else:
        secrets_root = os.environ.get("OPENCLAW_SECRETS_ROOT")
        if secrets_root:
            base = Path(secrets_root).expanduser() / "providers"
        else:
            base = Path.home() / "BybitOpenClaw" / "secrets" / "providers"

    try:
        base.mkdir(parents=True, exist_ok=True)
        # 收緊權限；既存目錄也 chmod 0700（best-effort）
        try:
            os.chmod(base, 0o700)
        except OSError:
            pass
    except OSError as exc:
        logger.error("provider_keys_dir mkdir failed: %s (path=%s)", exc, base)
        raise
    return base


def _provider_file(provider: str) -> Path:
    if not _PROVIDER_NAME_RE.match(provider):
        raise ValueError(f"invalid provider name: {provider!r}")
    if provider not in ALLOWED_PROVIDERS:
        raise ValueError(f"provider not in whitelist: {provider!r}")
    return _resolve_keys_dir() / f"{provider}.env"


# ─── 格式驗證 ────────────────────────────────────────────────────────

def validate_key(provider: str, key: str) -> tuple[bool, str | None]:
    """回 (ok, error_message)；不通過時 error_message 為人類可讀說明。"""
    if provider not in _SPECS:
        return False, f"未知供應商: {provider}"
    spec = _SPECS[provider]
    key = (key or "").strip()
    if len(key) < spec.min_len:
        return False, f"密鑰太短（最少 {spec.min_len} 字符）"
    if spec.prefix and not key.startswith(spec.prefix):
        return False, f"格式錯誤（必須以 {spec.prefix} 開頭）"
    return True, None


def _validation_headers(provider: str, key: str) -> dict[str, str]:
    if provider == PROVIDER_ANTHROPIC:
        return {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Accept": "application/json",
        }
    return {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }


def _validation_urls(provider: str) -> list[str]:
    if provider == PROVIDER_ANTHROPIC:
        return ["https://api.anthropic.com/v1/models"]
    if provider == PROVIDER_OPENAI:
        return ["https://api.openai.com/v1/models"]
    if provider == PROVIDER_DEEPSEEK:
        return [
            "https://api.deepseek.com/models",
            "https://api.deepseek.com/v1/models",
        ]
    return []


def probe_key(provider: str, key: str, *, timeout: float = 12.0) -> dict[str, Any]:
    """
    對支援的雲端 L2 provider 做只讀 auth probe。

    這裡只打 models/list 類 endpoint，不發 chat/completion，因此不消耗 token
    成本。返回值永不包含 key 明文。
    """
    key = (key or "").strip()
    urls = _validation_urls(provider)
    if not urls:
        return {
            "validated": False,
            "validation_status": "not_supported",
            "validation_error": "",
        }

    last_result: dict[str, Any] = {
        "validated": False,
        "validation_status": "not_run",
        "validation_error": "",
    }
    for url in urls:
        req = urllib.request.Request(
            url,
            headers=_validation_headers(provider, key),
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp.read(256)
                return {
                    "validated": True,
                    "validation_status": "auth_ok",
                    "validation_http_status": int(resp.status),
                    "validation_endpoint": url,
                    "validation_error": "",
                }
        except urllib.error.HTTPError as exc:
            # 404/405 可能只是 endpoint 版本不匹配；DeepSeek 有兩個候選 endpoint。
            last_result = {
                "validated": False,
                "validation_status": "http_error",
                "validation_http_status": int(exc.code),
                "validation_endpoint": url,
                "validation_error": f"HTTP {exc.code}",
            }
            if exc.code in {404, 405}:
                continue
            return last_result
        except urllib.error.URLError as exc:
            return {
                "validated": False,
                "validation_status": "network_error",
                "validation_endpoint": url,
                "validation_error": str(exc.reason)[:160],
            }
        except Exception as exc:
            return {
                "validated": False,
                "validation_status": "probe_error",
                "validation_endpoint": url,
                "validation_error": type(exc).__name__,
            }
    return last_result


# ─── 寫入 / 讀取 / 刪除 ──────────────────────────────────────────────

_lock = threading.Lock()


def _write_atomic(path: Path, content: str) -> None:
    """原子寫入並設 0600。先寫 .tmp 再 rename，避免半寫狀態。"""
    tmp = path.with_suffix(path.suffix + ".tmp")
    # exclusive create 避免 race；若 tmp 殘留先清掉
    if tmp.exists():
        tmp.unlink()
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    os.replace(str(tmp), str(path))
    # 二次保險：rename 後再 chmod（某些 fs 會丟 mode）
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def save_key(provider: str, key: str) -> dict[str, Any]:
    """
    寫入或替換 provider 的 API key。
    對 anthropic：同步注入 os.environ + reset client，立即生效。

    回傳 dict：{provider, env_var, masked, configured, client_implemented, hot_reloaded}
    """
    if provider not in _SPECS:
        raise ValueError(f"unknown provider: {provider}")
    ok, err = validate_key(provider, key)
    if not ok:
        raise ValueError(err or "key validation failed")

    spec = _SPECS[provider]
    key = key.strip()
    path = _provider_file(provider)

    probe = probe_key(provider, key)
    if provider in {PROVIDER_ANTHROPIC, PROVIDER_OPENAI, PROVIDER_DEEPSEEK} and not probe.get("validated"):
        status = probe.get("validation_status") or "unknown"
        http_status = probe.get("validation_http_status")
        suffix = f" HTTP {http_status}" if http_status else ""
        raise ValueError(f"live validation failed: {status}{suffix}")

    # env 檔案內容：簡單 KEY=value，附 metadata 注釋方便 GUI 誠實顯示驗證狀態。
    updated_at_ms = int(time.time() * 1000)
    content = (
        f"# {provider} API key — managed by Control API GUI\n"
        f"# updated_at_ms={updated_at_ms}\n"
        f"# validation_status={probe.get('validation_status', 'not_supported')}\n"
        f"# validation_checked_at_ms={updated_at_ms if probe.get('validated') else ''}\n"
        f"# validation_http_status={probe.get('validation_http_status', '')}\n"
        f"# validation_endpoint={probe.get('validation_endpoint', '')}\n"
        f"{spec.env_var}={key}\n"
    )

    hot_reloaded = False
    with _lock:
        _write_atomic(path, content)
        # 注入當前進程 env（替換生效路徑）
        os.environ[spec.env_var] = key
        # 觸發 provider_client singleton reset（anthropic / deepseek / openai 都吃這條）
        try:
            from . import provider_client as _pc  # 延遲 import 防 circular
            if provider in _pc.L2_PROVIDERS:
                _pc.reset_provider(provider)
                hot_reloaded = True
        except Exception as exc:
            logger.warning("provider_client reset failed (%s): %s", provider, exc)
        # Anthropic 還有舊的 layer2_engine._anthropic_client singleton（向後相容）
        if provider == PROVIDER_ANTHROPIC:
            try:
                from .layer2_engine import reset_anthropic_client
                reset_anthropic_client()
                hot_reloaded = True
            except Exception as exc:
                logger.warning("anthropic legacy client reset failed: %s", exc)
        try:
            from . import provider_model_catalog as _catalog
            _catalog.invalidate_provider(provider)
        except Exception as exc:
            logger.debug("provider model catalog invalidation skipped (%s): %s", provider, exc)

    logger.info("provider_keys: saved %s (path=%s, hot_reloaded=%s)", provider, path, hot_reloaded)
    return {
        "provider": provider,
        "env_var": spec.env_var,
        "masked": _mask(key),
        "configured": True,
        "client_implemented": spec.client_implemented,
        "hot_reloaded": hot_reloaded,
        **probe,
    }


def delete_key(provider: str) -> dict[str, Any]:
    """刪除 provider 的 key 檔案 + 從當前進程 env 移除。"""
    if provider not in _SPECS:
        raise ValueError(f"unknown provider: {provider}")
    spec = _SPECS[provider]
    path = _provider_file(provider)

    existed = False
    with _lock:
        if path.exists():
            try:
                path.unlink()
                existed = True
            except OSError as exc:
                logger.error("delete_key unlink failed: %s", exc)
                raise
        # 從 env 移除（若 process 之前注入過）
        os.environ.pop(spec.env_var, None)
        # 重置 provider_client singleton（anthropic / deepseek / openai 通吃）
        try:
            from . import provider_client as _pc
            if provider in _pc.L2_PROVIDERS:
                _pc.reset_provider(provider)
        except Exception:
            pass
        try:
            from . import provider_model_catalog as _catalog
            _catalog.invalidate_provider(provider)
        except Exception:
            pass
        if provider == PROVIDER_ANTHROPIC:
            try:
                from .layer2_engine import reset_anthropic_client
                reset_anthropic_client()
            except Exception:
                pass

    logger.info("provider_keys: deleted %s (existed=%s)", provider, existed)
    return {"provider": provider, "deleted": existed, "configured": False}


def _read_key_record(provider: str) -> tuple[str | None, dict[str, str]]:
    """從 .env 檔案讀回 key 與 metadata。檔案缺失或解析失敗回空值。"""
    spec = _SPECS[provider]
    path = _provider_file(provider)
    if not path.exists():
        return None, {}
    metadata: dict[str, str] = {}
    key: str | None = None
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                comment = line[1:].strip()
                if "=" in comment:
                    k, _, v = comment.partition("=")
                    metadata[k.strip()] = v.strip()
                continue
            if "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() == spec.env_var:
                key = v.strip()
    except OSError as exc:
        logger.warning("read provider key failed: %s", exc)
    return key, metadata


def _read_key_from_file(provider: str) -> str | None:
    """從 .env 檔案讀回 key（不含注釋）。檔案缺失或解析失敗回 None。"""
    key, _metadata = _read_key_record(provider)
    return key


def _mask(key: str) -> str:
    """回顯 masked 版本（保前 4 + 後 4 字符），中間 ***。"""
    if not key:
        return ""
    if len(key) <= 10:
        return "*" * len(key)
    return f"{key[:4]}…{key[-4:]}"


def status() -> dict[str, Any]:
    """
    回所有 provider 的狀態快照。永不回明文 key。
    GUI badge 用：configured + client_implemented 兩維度決定顯示。

    回 shape：
      {
        "keys_dir": "...",
        "providers": {
          "anthropic": {configured, client_implemented, env_var, description, masked},
          ...
        }
      }
    """
    out: dict[str, Any] = {}
    for provider, spec in _SPECS.items():
        key, metadata = _read_key_record(provider)
        configured = bool(key)
        validation_status = metadata.get("validation_status")
        out[provider] = {
            "configured": configured,
            "client_implemented": spec.client_implemented,
            "env_var": spec.env_var,
            "description": spec.description,
            "is_url": spec.is_url,
            "masked": _mask(key) if key else None,
            "validated": validation_status == "auth_ok",
            "validation_status": validation_status if configured else None,
            "validation_checked_at_ms": metadata.get("validation_checked_at_ms") or None,
            "validation_http_status": metadata.get("validation_http_status") or None,
        }
    try:
        keys_dir = str(_resolve_keys_dir())
    except OSError:
        keys_dir = "<unresolvable>"
    return {"keys_dir": keys_dir, "providers": out}


def load_into_environ() -> dict[str, bool]:
    """
    啟動時呼叫：把所有已存的 key 注入當前進程 os.environ。
    冪等；返回 {provider: injected_bool}。

    用途：API process 啟動時把 secrets 目錄的 key 加載到 env，
    讓 layer2_engine._get_anthropic_client() 等能直接 os.getenv 拿到。
    """
    injected: dict[str, bool] = {}
    for provider, spec in _SPECS.items():
        try:
            key = _read_key_from_file(provider)
        except Exception:
            key = None
        if key:
            os.environ[spec.env_var] = key
            injected[provider] = True
        else:
            injected[provider] = False
    return injected


__all__ = [
    "ALLOWED_PROVIDERS",
    "PROVIDER_ANTHROPIC",
    "PROVIDER_OPENAI",
    "PROVIDER_DEEPSEEK",
    "PROVIDER_PERPLEXITY",
    "PROVIDER_GOOGLE",
    "PROVIDER_LOCAL_LLM",
    "validate_key",
    "save_key",
    "delete_key",
    "status",
    "load_into_environ",
]
