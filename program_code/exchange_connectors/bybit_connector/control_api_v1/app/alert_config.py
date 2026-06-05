"""
Alert Config — GUI-configurable alert credentials store (pure stdlib)
告警配置 — GUI 可配置的告警憑證儲存（純標準庫）

MODULE_NOTE (中文):
  模塊用途：統一的告警憑證讀寫層。operator 在 GUI 設定 Telegram / Webhook 憑證，
    寫進 <data_dir>/alert_config.json；FastAPI app 的 alerter 與獨立 watchdog
    都從這個檔讀（file-primary），檔缺/壞時回退既有 env 變量（env-fallback，
    保留 OPENCLAW_TELEGRAM_* / OPENCLAW_WEBHOOK_* 既有行為）。
  主要函數：load_alert_config / save_alert_config / mask_secret / validate_webhook_url。
  依賴：純標準庫（json / os / stat / socket / ipaddress / urllib.parse）。
    **嚴禁** import FastAPI 或 app 內任何模塊 —— watchdog 需以零 app 依賴方式共用本檔
    的 schema 與 key 名（watchdog 端內聯一份 ~15 行的讀取拷貝，不直接 import）。
  硬邊界：
    - 本模塊只負責「通知憑證」儲存；不碰交易 / 風控 / 授權任何硬邊界。
    - load 為 best-effort，永不拋例外（壞檔回安全的 disabled 空 dict）；告警鏈的
      失敗永遠不得影響交易或 watchdog 主循環。
    - GET/回傳面永不外洩明文 token / secret（呼叫端用 mask_secret）。
    - validate_webhook_url 提供 SSRF 守衛：只允許 https，且阻擋指向內網 / loopback /
      link-local（含雲端 metadata 169.254.169.254）的 URL。
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import stat
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ALERT_CONFIG_FILENAME = "alert_config.json"

# 清空 sentinel：POST 以空字串表示「保留原值」，以此 sentinel 表示「清除」。
CLEAR_SENTINEL = "__CLEAR__"

# 控制字元黑名單（用於 token / secret / url 注入防護）。
_CONTROL_CHARS = ("\n", "\r", "\x00")


def _default_config() -> dict[str, Any]:
    """回傳全 disabled 的安全預設 config（schema version=1）。

    為什麼需要：壞檔 / 缺檔 / env 也空時，所有讀取路徑都落到這個安全空殼，
    確保 is_enabled 永遠 False（fail-closed：未配置即靜默 no-op）。
    """
    return {
        "version": 1,
        "telegram": {"enabled": False, "bot_token": "", "chat_id": ""},
        "webhook": {"enabled": False, "urls": [], "secret": ""},
        "updated_at": 0,
    }


def _config_path(data_dir: str) -> Path:
    return Path(data_dir) / ALERT_CONFIG_FILENAME


def _coerce_str(value: Any) -> str:
    """把任意值收斂成 str（非 str → ""）；防止壞檔把 dict/list 灌進憑證欄位。"""
    return value if isinstance(value, str) else ""


def _normalize(raw: Any) -> dict[str, Any]:
    """把磁碟上的原始 JSON 收斂成嚴格 schema（缺欄位補預設，型別不符丟棄）。

    為什麼嚴格收斂：alert_config.json 由 GUI 寫，但也可能被人手改壞；下游 alerter
    直接用這些欄位拼 HTTP 請求，必須保證型別乾淨，否則壞檔可能讓 alerter 拋例外
    （違反「告警失敗不影響交易」不變量）。
    """
    cfg = _default_config()
    if not isinstance(raw, dict):
        return cfg

    tg_raw = raw.get("telegram")
    if isinstance(tg_raw, dict):
        cfg["telegram"]["bot_token"] = _coerce_str(tg_raw.get("bot_token"))
        cfg["telegram"]["chat_id"] = _coerce_str(tg_raw.get("chat_id"))
        cfg["telegram"]["enabled"] = bool(tg_raw.get("enabled", False))

    wh_raw = raw.get("webhook")
    if isinstance(wh_raw, dict):
        urls_raw = wh_raw.get("urls")
        urls: list[str] = []
        if isinstance(urls_raw, list):
            urls = [u.strip() for u in urls_raw if isinstance(u, str) and u.strip()]
        cfg["webhook"]["urls"] = urls
        cfg["webhook"]["secret"] = _coerce_str(wh_raw.get("secret"))
        cfg["webhook"]["enabled"] = bool(wh_raw.get("enabled", False))

    updated = raw.get("updated_at")
    if isinstance(updated, (int, float)):
        cfg["updated_at"] = int(updated)

    return cfg


def _apply_env_fallback(cfg: dict[str, Any]) -> dict[str, Any]:
    """檔內憑證為空時，從既有 env 變量補（back-compat）。

    為什麼：在 operator 尚未用 GUI 寫檔前，既有部署可能已透過
    OPENCLAW_TELEGRAM_* / OPENCLAW_WEBHOOK_* env 配了憑證；file-primary 但
    env-fallback 保證舊行為不被本次改動打斷。enabled 由「憑證齊全」推導，
    與既有 alerter 的 is_enabled 語義一致（雙非空才算啟用）。
    """
    if not cfg["telegram"]["bot_token"] and not cfg["telegram"]["chat_id"]:
        env_token = os.getenv("OPENCLAW_TELEGRAM_BOT_TOKEN", "").strip()
        env_chat = os.getenv("OPENCLAW_TELEGRAM_CHAT_ID", "").strip()
        if env_token or env_chat:
            cfg["telegram"]["bot_token"] = env_token
            cfg["telegram"]["chat_id"] = env_chat
            cfg["telegram"]["enabled"] = bool(env_token and env_chat)

    if not cfg["webhook"]["urls"]:
        env_urls_raw = os.getenv("OPENCLAW_WEBHOOK_URLS", "")
        env_urls = [u.strip() for u in env_urls_raw.split(",") if u.strip()]
        if env_urls:
            cfg["webhook"]["urls"] = env_urls
            cfg["webhook"]["enabled"] = True
            if not cfg["webhook"]["secret"]:
                cfg["webhook"]["secret"] = os.getenv("OPENCLAW_WEBHOOK_SECRET", "").strip()

    return cfg


def load_alert_config(data_dir: str) -> dict[str, Any]:
    """讀取告警 config：file-primary，env-fallback；best-effort，永不拋。

    壞檔 / 缺檔一律回安全的 disabled 空殼（再套 env-fallback）。本函數是 alerter
    與 watchdog 的單一憑證來源；任何例外都被吞掉換成安全預設，確保告警鏈絕不
    把錯誤往上拋進交易 / 監控主路徑。
    """
    raw: Any = None
    try:
        with open(_config_path(data_dir), "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        raw = None
    except Exception:  # noqa: BLE001 - 憑證讀取必須 fail-safe，任何意外都回安全預設
        raw = None

    cfg = _normalize(raw)
    return _apply_env_fallback(cfg)


def save_alert_config(data_dir: str, cfg: dict[str, Any]) -> None:
    """原子寫入告警 config：mkdir(0700) → tmp → os.replace → chmod 0600。

    鏡像 settings_routes._write_key_file 的安全落盤紀律：先收緊目錄權限（best-effort），
    經 tmp+replace 原子替換，最後把檔權限收到 0600（僅 owner 讀寫）。憑證檔含明文
    token / secret，權限必須最嚴。
    """
    normalized = _normalize(cfg)
    normalized["updated_at"] = int(time.time())

    path = _config_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, stat.S_IRWXU)  # 0700 best-effort
    except OSError:
        pass  # 部分 FS 可能不支援，盡力而為

    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2)
    # E3 LOW-1 (2026-06-05)：先把 tmp 收到 0600 再 replace。os.replace 是 rename，
    # 會沿用「來源 inode」的權限，故換上去的最終檔一落地就是 0600，徹底消除
    # 「replace 後、chmod 前」那段最終憑證檔為 0644（umask 預設、group/other 可讀）
    # 的時間窗。replace 後再 chmod 一次作雙保險（極少數 FS 行為差異時兜底）。
    os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)  # 0600（replace 前，關掉 0644 窗）
    os.replace(tmp, path)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0600（belt-and-suspenders）


def mask_secret(s: str) -> str:
    """遮罩憑證：回傳 "••••"+last4；空字串回 ""（鏡像 _mask_key 語義）。

    為什麼用點點而非星號：與前端既有 hint 樣式一致；GET 面永不回明文，只回此遮罩。
    """
    s = (s or "").strip()
    if not s:
        return ""
    if len(s) <= 4:
        return "••••"
    return "••••" + s[-4:]


def has_control_chars(s: str) -> bool:
    """是否含控制字元（\\n / \\r / \\x00）—— 注入防護。"""
    return any(c in s for c in _CONTROL_CHARS)


def validate_webhook_url(url: str) -> tuple[bool, str]:
    """SSRF 守衛：驗證 webhook URL 是否安全可外送。

    為什麼需要（倉內原本無 SSRF 守衛）：webhook URL 由 operator 在 GUI 自由填，
    若指向內網 / loopback / 雲端 metadata，本服務會變成 SSRF 跳板。規則：
      1. scheme 必須是 https（明文 http 不允許 —— 憑證走 HMAC，且避免降級攻擊）。
      2. 解析 host 的所有 IP，任一落在以下私有 / 特殊網段即拒：
         - loopback 127.0.0.0/8 / ::1
         - RFC1918 10/8、172.16-31、192.168/16
         - link-local 169.254/16（含雲端 metadata 169.254.169.254）
         - unspecified 0.0.0.0 / ::
    殘留風險（已知並接受）：DNS-rebind —— 驗證時解析安全、送出時 DNS 已換成內網。
    本配置為 operator-only 低頻設定，於驗證時阻擋即可（不在每次送出時重解析）。

    回傳 (ok, reason)；ok=False 時 reason 為安全的、不含使用者輸入回顯的原因碼。
    """
    if not isinstance(url, str) or not url.strip():
        return False, "empty_url"
    url = url.strip()
    if has_control_chars(url):
        return False, "control_chars"

    try:
        parts = urlsplit(url)
    except ValueError:
        return False, "malformed_url"

    if parts.scheme != "https":
        return False, "scheme_not_https"

    host = parts.hostname
    if not host:
        return False, "missing_host"

    # 解析 host 的全部 IP（A/AAAA）；任一不安全即拒。
    # 解析失敗（NXDOMAIN 等）視為不可驗證 → 拒（fail-closed）。
    try:
        infos = socket.getaddrinfo(host, parts.port or 443, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, OSError):
        return False, "dns_resolve_failed"

    addrs: set[str] = set()
    for info in infos:
        sockaddr = info[4]
        if sockaddr and isinstance(sockaddr[0], str):
            addrs.add(sockaddr[0])

    if not addrs:
        return False, "no_addresses"

    for addr in addrs:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False, "bad_ip"
        # is_private 已涵蓋 RFC1918 + loopback + link-local + unique-local；
        # 額外顯式擋 unspecified / reserved / multicast 以求嚴格。
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_unspecified
            or ip.is_reserved
            or ip.is_multicast
        ):
            return False, "blocked_internal_address"

    return True, ""
