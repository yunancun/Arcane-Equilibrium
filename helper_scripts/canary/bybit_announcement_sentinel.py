#!/usr/bin/env python3
"""
MODULE_NOTE
模塊用途：Bybit 公告增量哨兵（cron 30min，alert-only，絕不自動觸發任何交易動作）。
  輪詢官方公開公告 API → 本地 seen-set 去重 → 新發現分級告警。設計 SSOT：
  docs/CCAgentWorkSpace/BB/workspace/reports/2026-06-11--bybit_announcement_sentinel_advisory.md。

數據源（BB 裁決 §1）：GET https://api.bybit.com/v5/announcements/index
  ?locale=en-US&page=1&limit=50 —— public 無 auth、plain GET，**不經任何簽名
  client、零 credential 面**（與交易憑證完全隔離）。每 cron 輪恰 1 call。

去重（BB 裁決 §4，load-bearing）：主鍵 = 正規化 url（strip query/fragment +
  trailing-slash 一致化）；輔助 id = url 尾 `blt<hex>` CMS entry UID；url 缺失/
  畸形時 fallback sha256(locale|title|publishTime)。增量 = seen-set 差集。
  **禁任何 timestamp watermark**：列表排序鍵是 dateTimestamp（編輯日）非
  publishTime，雙樣本排序 inversion 實證（BB §1.3），watermark 必漏件。

severity 映射（BB §2）：delistings / maintenance_updates = P0 無條件；
  product_updates 默認 P1，tag/keyword escalator 命中 → P0；new_crypto 衍生品
  tag → P1 否則 P2；latest_bybit_news 默認 P2，tag → P1、keyword → P0；
  other = P1（未知桶寬網）；latest_activities / new_fiat_listings = P2 ignore。
  P2 不告警（仍記 seen + 原文落 state 供審計）。

主要類/函數：FetchError、normalize_url、extract_blt_id、derive_article_key、
  classify_announcement、fetch_announcements、load_state/save_state/prune_seen、
  run_once、_resolve_alert_fn（sibling-import watchdog emitter，同 incident_sentinel）。
依賴：純 stdlib（urllib/json/re/hashlib）+ sibling alert_sink（禁 redirect opener，
  E3：外連 GET 不跟跳 30x）。告警 sibling-import
  engine_watchdog._send_alert_best_effort（其本地耐久 sink 保證無 creds 也必達）。

硬邊界（alert-only，E2 可結構性 grep 驗證）：
  - 0 簽名 / 0 API key / 0 credential：不 import 任何 bybit client，無 HMAC 簽名面。
  - 0 PG 寫入、0 runtime 行為：唯一本地寫入 = <data_dir>/bybit_announcements_state.json。
  - 網路/解析失敗 = fail-quiet（log 一行 + skip cycle + exit 0），**禁 tight retry**
    （403 = IP ban 10min，tight retry 只會延長 ban；下輪 cron 30min 自然重試）；
    連續 8 輪失敗（≈4h）發一條 sentinel-health meta-alert。
  - untrusted 紀律（BB §6）：title/description 是外部文本；告警 body 只放
    title+url+類別（plain-text 直發不經 LLM），description 絕不展開；
    原始公告 JSON 整條存 state 檔 raw 欄供審計回溯。
  - 25-symbol 名單 runtime 注入（OPENCLAW_BB_SENTINEL_WATCHLIST csv env），禁硬編碼。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

# sibling alert_sink（與 watchdog 同 dir 出貨）：禁 redirect opener 正本。
# 為什麼 module-top import 而非 lazy fail-soft：fetch 的 redirect 禁令不可靜默降級
# （退回會跟跳的 urlopen = 防護消失），缺檔=部署破損，寧 loud-fail 留 cron log。
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import alert_sink

logger = logging.getLogger("bybit_announcement_sentinel")

# ── 常數區 ──

API_HOST = "https://api.bybit.com"
API_PATH = "/v5/announcements/index"
API_LOCALE = "en-US"   # BB 裁決：唯一鎖定（tag 匹配僅對英文 tag 穩定）
API_LIMIT = 50         # 覆蓋 ≥2-3 日流量，與 30min 週期形成巨幅重疊窗（BB §3）

STATE_FILE = "bybit_announcements_state.json"
RETENTION_DAYS = 90.0           # seen 條目修剪窗（>90d 修剪；寧重報不漏報）
META_ALERT_AFTER_FAILURES = 8   # 連續失敗 ≈4h → sentinel-health meta-alert（BB §3）
MAX_ALERTS_PER_RUN = 10         # 單輪告警上限（哨兵長停擺後復跑的洪水保險；超出彙總 1 條）

SEV_P0 = "P0"
SEV_P1 = "P1"
SEV_P2 = "P2"

# severity → watchdog emitter 通道層級（subject 已帶 P0/P1，通道層級只分 CRITICAL/WARN）。
_CHANNEL_SEVERITY = {SEV_P0: "CRITICAL", SEV_P1: "WARN"}

# tag escalation 集（BB §2 表；比對一律 lower-case 正規化，防 API 大小寫 drift）。
_PRODUCT_UPDATES_P0_TAGS = frozenset({
    "derivatives", "futures", "unified trading account", "upgrades", "institutions",
})
_NEWS_P1_TAGS = frozenset({
    "derivatives", "futures", "institutions", "unified trading account",
})
_NEW_CRYPTO_DERIV_TAGS = frozenset({"derivatives", "futures"})

# keyword escalator（BB §2：word-boundary regex 防 `capital`→`api` 誤命中；
# title+description、case-insensitive；寬鬆寧誤升不漏降）。
_KEYWORD_ESCALATORS: tuple[tuple[str, re.Pattern], ...] = tuple(
    (name, re.compile(pattern, re.IGNORECASE))
    for name, pattern in (
        ("api", r"\bapi\b"),
        ("maintenance", r"\bmaintenance\b"),
        ("delist", r"\bdelist"),
        ("settlement", r"\bsettlement\b"),
        ("funding_rate_fee", r"\bfunding\s+(?:rate|fee)s?\b"),
        ("risk_limit", r"\brisk\s+limits?\b"),
        ("margin_tier", r"\bmargin\s+tiers?\b"),
        ("leverage", r"\bleverage\b"),
        ("ticker_change", r"\bticker\s+changes?\b"),
        ("rebrand", r"\brebrand"),
        ("contract_specification", r"\bcontract\s+specifications?\b"),
        ("perpetual_contract_adjustment", r"\bperpetual\s+contracts?\b.{0,80}\badjust|\badjust\w*\b.{0,80}\bperpetual\s+contracts?\b"),
    )
)

# url 尾 CMS entry UID（BB §4：實證 5/5 樣本符 `-blt<hex>/` 形；語意未官方文件化
# 故僅作輔助 id，不作唯一主鍵）。
_BLT_RE = re.compile(r"-(blt[0-9a-f]+)$", re.IGNORECASE)

_VALID_SEVERITIES = (SEV_P0, SEV_P1, SEV_P2)


def _env_float(name: str, default: float) -> float:
    """讀 env 浮點配置；壞值回 default（哨兵自身配置錯不得毀整輪）。"""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("env %s 非數值（%r），改用默認 %s", name, raw, default)
        return default


def _load_watchlist() -> tuple:
    """25-symbol 名單 runtime 注入（BB 驗收 #3：禁硬編碼）。

    來源 = OPENCLAW_BB_SENTINEL_WATCHLIST（csv，如 "BTCUSDT,ETHUSDT"）；
    未設 = 空（不做 symbol 標記，severity 映射其餘規則照常）。
    """
    raw = os.environ.get("OPENCLAW_BB_SENTINEL_WATCHLIST", "").strip()
    if not raw:
        return ()
    return tuple(s.strip().upper() for s in raw.split(",") if s.strip())


# ── 去重鍵（BB §4） ──


def normalize_url(url) -> str | None:
    """正規化公告 url 為主鍵：strip query/fragment + trailing-slash 一致化 +
    scheme/host lower-case。畸形/缺失回 None（caller 走 sha256 fallback）。"""
    if not isinstance(url, str) or not url.strip():
        return None
    try:
        parts = urllib.parse.urlsplit(url.strip())
    except ValueError:
        return None
    if not parts.netloc:
        return None
    path = parts.path.rstrip("/") or "/"
    scheme = (parts.scheme or "https").lower()
    return f"{scheme}://{parts.netloc.lower()}{path}"


def extract_blt_id(normalized_url: str) -> str | None:
    """從正規化 url 尾提取 `blt<hex>` CMS entry UID（輔助 id；不中回 None）。"""
    m = _BLT_RE.search(normalized_url)
    return m.group(1).lower() if m else None


def derive_article_key(item: dict) -> tuple[str | None, str | None]:
    """單條公告 → (去重主鍵, 輔助 blt id)。

    主鍵優先級（BB §4 裁決）：正規化 url > sha256(locale|title|publishTime) fallback。
    url 與 title 皆缺 = 無法識別 → (None, None)，caller 記 malformed 跳過
    （不可用佔位 key：會把所有畸形條目互相去重吞掉）。
    """
    norm = normalize_url(item.get("url"))
    if norm:
        return norm, extract_blt_id(norm)
    title = item.get("title")
    if not isinstance(title, str) or not title.strip():
        return None, None
    basis = f"{API_LOCALE}|{title.strip()}|{item.get('publishTime', '')}"
    return "sha256:" + hashlib.sha256(basis.encode("utf-8")).hexdigest(), None


# ── severity 分級（BB §2） ──


def classify_announcement(item: dict, watchlist: tuple = ()) -> tuple[str, list]:
    """單條公告 → (severity, matched_escalators)。

    type.key 默認檔位 + tag/keyword escalator + watchlist 命中（見 MODULE_NOTE 映射表）。
    未知 type.key 走 P1（與 'other' 同：未知桶寬網，寧誤升不漏降）。
    """
    type_key = str(((item.get("type") or {}).get("key")) or "").strip().lower()
    title = item.get("title") if isinstance(item.get("title"), str) else ""
    description = item.get("description") if isinstance(item.get("description"), str) else ""
    raw_tags = item.get("tags") if isinstance(item.get("tags"), list) else []
    tags = {str(t).strip().lower() for t in raw_tags if isinstance(t, str)}
    text = f"{title}\n{description}"

    matched: list[str] = []
    for name, rx in _KEYWORD_ESCALATORS:
        if rx.search(text):
            matched.append(f"kw:{name}")
    upper_text = text.upper()
    for sym in watchlist:
        if sym and sym in upper_text:
            matched.append(f"watchlist:{sym}")
    kw_hit = bool(matched)

    if type_key == "delistings":
        severity = SEV_P0  # 無條件（含 rebrand/ticker change，實證 TON→GRAM 歸此類）
    elif type_key == "maintenance_updates":
        severity = SEV_P0  # 無條件（維護窗 = API/WS 不可用風險）
    elif type_key == "product_updates":
        if (tags & _PRODUCT_UPDATES_P0_TAGS) or kw_hit:
            severity = SEV_P0
            matched.extend(f"tag:{t}" for t in sorted(tags & _PRODUCT_UPDATES_P0_TAGS))
        else:
            severity = SEV_P1
    elif type_key == "new_crypto":
        # 衍生品 tag（新永續）→ P1（listing-fade 研究線輸入）；純 Spot → P2。
        severity = SEV_P1 if tags & _NEW_CRYPTO_DERIV_TAGS else SEV_P2
    elif type_key == "latest_bybit_news":
        if kw_hit:
            severity = SEV_P0  # 政策/監管/地區限制變動可能落此桶
        elif tags & _NEWS_P1_TAGS:
            severity = SEV_P1
            matched.extend(f"tag:{t}" for t in sorted(tags & _NEWS_P1_TAGS))
        else:
            severity = SEV_P2
    elif type_key in ("latest_activities", "new_fiat_listings"):
        severity = SEV_P2  # ignore：行銷活動 / 法幣通道與 perp 無關
    else:
        severity = SEV_P1  # 'other' 與未知桶：低流量默認人工掃一眼，不 ignore

    return severity, matched


# ── 拉取（plain GET，零 credential 面） ──


class FetchError(Exception):
    """單輪拉取失敗（HTTP/解析/retCode 非 0）→ caller fail-quiet skip。"""


def fetch_announcements(opener=None, timeout: float = 10.0) -> list[dict]:
    """單次 plain GET 公告列表（V5 envelope 衛生：retCode==0 才消費）。

    opener 為 urlopen-compatible callable（測試注入；收 urllib.request.Request）。
    為什麼不經簽名 client：公告為全域公開資料，哨兵必須零 key 接觸、零簽名面，
    與交易憑證完全隔離（BB §1.1 裁決）。
    默認 opener 禁 redirect（E3）：公告 API 正常路徑不應 30x，跟跳 = 出口可被引去
    任意 host；30x 升 HTTPError → 本函數統一收成 FetchError（fail-quiet skip）。
    list 空非錯誤（照常結束）；任何失敗以 FetchError 拋給 caller 統一 fail-quiet。
    """
    opener = opener or alert_sink.urlopen_no_redirect
    params = urllib.parse.urlencode({"locale": API_LOCALE, "page": 1, "limit": API_LIMIT})
    req = urllib.request.Request(
        f"{API_HOST}{API_PATH}?{params}",
        headers={"User-Agent": "openclaw-bb-sentinel/1.0"},
    )
    try:
        with opener(req, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            raw = resp.read()
    except Exception as exc:  # noqa: BLE001 - 網路層任何錯誤都是同一事實：本輪不可用
        raise FetchError(f"http_error {type(exc).__name__}: {exc}") from exc
    if status != 200:
        raise FetchError(f"http_status_{status}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise FetchError(f"parse_error: {exc}") from exc
    if not isinstance(payload, dict):
        raise FetchError("payload_not_dict")
    if payload.get("retCode") != 0:
        ret_msg = str(payload.get("retMsg", ""))[:120]
        raise FetchError(f"retCode={payload.get('retCode')!r} retMsg={ret_msg!r}")
    items = (payload.get("result") or {}).get("list")
    if not isinstance(items, list):
        raise FetchError("result.list_missing")
    return [it for it in items if isinstance(it, dict)]


# ── state（唯一本地寫入面） ──


def load_state(data_dir: str) -> dict:
    """讀 state；缺檔/壞檔回空 dict（→ 首輪 baseline 模式，天然自癒）。"""
    try:
        with open(Path(data_dir) / STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return {}


def save_state(data_dir: str, state: dict) -> None:
    """原子寫 state（tmp + os.replace，mirror incident_sentinel）；失敗只 log 不拋。"""
    path = Path(data_dir) / STATE_FILE
    tmp = path.with_suffix(".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, default=str)
        os.replace(tmp, path)
    except OSError as exc:
        logger.warning("state 保存失敗：%s", exc)


def prune_seen(state: dict, now: float, retention_days: float = RETENTION_DAYS) -> int:
    """修剪 first_seen_at 超過保留窗的 seen 條目，回傳修剪數。

    為什麼可安全修剪：page-1 窗只覆蓋最近數日，>90d 條目幾乎不可能重現；
    若舊公告被編輯跳回 page-1（dateTimestamp 排序）造成重報 —— 寧重報不漏報（BB §4）。
    """
    cutoff = now - retention_days * 86400.0
    seen = state.get("seen")
    if not isinstance(seen, dict):
        state["seen"] = {}
        return 0
    keep = {}
    for key, entry in seen.items():
        try:
            first_seen = float(entry.get("first_seen_at", 0.0))
        except (TypeError, ValueError, AttributeError):
            first_seen = 0.0
        if first_seen >= cutoff:
            keep[key] = entry
    pruned = len(seen) - len(keep)
    state["seen"] = keep
    return pruned


# ── 告警（sibling-import watchdog emitter，同 incident_sentinel 模式） ──


def _resolve_alert_fn():
    """sibling-import engine_watchdog._send_alert_best_effort（mirror
    incident_sentinel._resolve_alert_fn）。

    import 失敗回 no-op：告警鏈故障不得毀偵測輪（state 檔 raw 原文仍完整可事後查）。
    emitter 自帶本地耐久 sink（alerts/alerts.jsonl）→ 無 creds 也必達。
    """
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    try:
        import engine_watchdog  # noqa: PLC0415 - 刻意延遲 import（大檔，僅發送時需要）

        return engine_watchdog._send_alert_best_effort
    except Exception as exc:  # noqa: BLE001 - fail-soft：偵測輪不得因告警鏈失敗而毀
        logger.warning("engine_watchdog emitter import 失敗，告警降級為 no-op：%s", exc)
        return lambda subject, body, severity, data_dir: None


# W-3（E2 2026-06-11）：C0/C1 控制字符（含 \r\n\t）。外部公告 title/url 是 untrusted
# 文本，帶換行可注入偽 log 行（watchdog INFO 行 log subject）與偽 Telegram 段。
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]+")


def _strip_control(text: str) -> str:
    """剝控制字符 → 單一空格（保留全部可見 unicode 文字）；進 subject/body/log 前必過。"""
    return _CONTROL_CHARS_RE.sub(" ", text or "")


def format_alert(severity: str, type_key: str, title: str, url: str, escalators: list) -> tuple[str, str]:
    """組告警 (subject, body)。

    untrusted 紀律（BB §6.3）：body 只放 title+url+類別（+escalator 指紋），
    plain-text 直發不經 LLM；description 絕不展開（原文在 state 檔 raw 欄）。
    W-3：title/url/type_key/escalators 先剝控制字符再截斷（防 log/訊息注入——type_key
    與 tag 衍生的 escalator 同為外部文本，同類威脅一併剝；state raw 欄保原文供審計）。
    """
    title = _strip_control(title)
    url = _strip_control(url)
    type_key = _strip_control(type_key)
    title_trunc = (title or "(no title)")[:200]
    subject = f"[BB-SENTINEL][{severity}] {type_key}: {title_trunc}"
    body_lines = [
        f"title: {title_trunc}",
        f"url: {(url or '(no url)')[:300]}",
        f"type: {type_key}",
    ]
    if escalators:
        body_lines.append(f"escalators: {_strip_control(', '.join(escalators[:8]))}")
    body_lines.append("(description 不展開；原文存 bybit_announcements_state.json raw 欄供審計)")
    return subject, "\n".join(body_lines)


# ── 編排 ──


def run_once(
    data_dir: str, *,
    opener=None, alert_fn=None, now: float | None = None,
    dry_run: bool = False, sleep_fn=time.sleep,
) -> int:
    """單輪：1 call 拉取 → seen-set 差集 → 分級 → 告警 → state 落盤。恆 exit 0。

    首輪 baseline（state 無 baseline_done）：全部標 seen 不告警（防首跑洪水）。
    fail-quiet：拉取失敗 log 一行 + 連續失敗計數 + exit 0（禁 tight retry）；
    連續 META_ALERT_AFTER_FAILURES 輪（≈4h）恰發一條 sentinel-health meta-alert。
    """
    now = time.time() if now is None else now
    drain_seconds = _env_float("OPENCLAW_BB_SENTINEL_ALERT_DRAIN_SECONDS", 6.0)
    timeout = _env_float("OPENCLAW_BB_SENTINEL_HTTP_TIMEOUT_SECONDS", 10.0)

    state = load_state(data_dir)
    seen = state.get("seen")
    if not isinstance(seen, dict):
        seen = {}
        state["seen"] = seen
    baseline_mode = not bool(state.get("baseline_done"))
    watchlist = _load_watchlist()

    try:
        items = fetch_announcements(opener=opener, timeout=timeout)
    except FetchError as exc:
        # fail-quiet skip：log 一行 + exit 0；下輪 cron 30min 自然重試（禁 tight retry）。
        fails = 0
        try:
            fails = int(state.get("consecutive_failures", 0) or 0)
        except (TypeError, ValueError):
            fails = 0
        fails += 1
        state["consecutive_failures"] = fails
        state["last_failure_at"] = now
        logger.warning("fetch 失敗（quiet-skip，連續第 %d 輪）：%s", fails, exc)
        if fails == META_ALERT_AFTER_FAILURES:
            # 恰在閾值輪發一次 meta-alert（每個故障 episode ≤1 條；成功即歸零）。
            fn = alert_fn or _resolve_alert_fn()
            subject = "[BB-SENTINEL][META] sentinel-health — consecutive fetch failures"
            body = (
                f"公告哨兵連續 {fails} 輪拉取失敗（≈{fails * 0.5:.1f}h），最後錯誤：{exc}\n"
                "action: ssh trade-core; 查 bybit_announcement_sentinel_cron.log 與網路面。"
            )
            if not dry_run:
                try:
                    fn(subject, body, "WARN", data_dir)
                except Exception as alert_exc:  # noqa: BLE001 - fire-and-forget
                    logger.warning("meta-alert 發送失敗（不重試）：%s", alert_exc)
                sleep_fn(drain_seconds)
        save_state(data_dir, state)
        return 0

    state["consecutive_failures"] = 0
    state["last_success_at"] = now

    new_entries: list[tuple[str, dict]] = []
    malformed = 0
    for item in items:
        key, blt_id = derive_article_key(item)
        if key is None:
            malformed += 1
            continue
        if key in seen:
            continue
        severity, escalators = classify_announcement(item, watchlist)
        entry = {
            "first_seen_at": now,
            "blt_id": blt_id,
            "type_key": str(((item.get("type") or {}).get("key")) or ""),
            "title": (item.get("title") or "")[:300] if isinstance(item.get("title"), str) else "",
            "url": (item.get("url") or "")[:500] if isinstance(item.get("url"), str) else "",
            "severity": severity,
            "matched_escalators": escalators,
            "alerted": False,
            # untrusted 紀律：原始公告 JSON 整條落 state 供審計回溯（告警不展開）。
            "raw": item,
        }
        seen[key] = entry
        new_entries.append((key, entry))

    alerts_sent = 0
    if baseline_mode:
        # 首輪 baseline：全部標 seen 不告警（防首跑把整頁 50 條灌成告警洪水）。
        state["baseline_done"] = True
        state["baseline_at"] = now
        logger.info(
            "baseline 輪：%d 條標 seen、0 告警（flood guard）；malformed=%d", len(new_entries), malformed,
        )
    else:
        alertable = [
            (key, entry) for key, entry in new_entries
            if entry["severity"] in (SEV_P0, SEV_P1)
        ]
        fn = alert_fn or _resolve_alert_fn()
        for key, entry in alertable[:MAX_ALERTS_PER_RUN]:
            subject, body = format_alert(
                entry["severity"], entry["type_key"], entry["title"],
                entry["url"] or key, entry["matched_escalators"],
            )
            if dry_run:
                print(f"DRY-RUN would alert: {subject}")
            else:
                try:
                    fn(subject, body, _CHANNEL_SEVERITY.get(entry["severity"], "WARN"), data_dir)
                    entry["alerted"] = True
                    entry["alerted_at"] = now
                except Exception as exc:  # noqa: BLE001 - fire-and-forget：發送失敗不重試
                    logger.warning("alert 發送失敗（不重試）：%s", exc)
            alerts_sent += 1
        overflow = len(alertable) - MAX_ALERTS_PER_RUN
        if overflow > 0:
            # 超出單輪上限：彙總 1 條（明細已全數落 state，operator 可查）。
            subject = f"[BB-SENTINEL][P1] aggregate: {overflow} more new announcement(s) suppressed"
            body = (
                f"本輪新公告超出單輪告警上限 {MAX_ALERTS_PER_RUN}，其餘 {overflow} 條僅落 state。\n"
                "action: 查 bybit_announcements_state.json 的 seen 條目（alerted=false）。"
            )
            if dry_run:
                print(f"DRY-RUN would alert: {subject}")
            else:
                try:
                    fn(subject, body, "WARN", data_dir)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("aggregate alert 發送失敗（不重試）：%s", exc)
            alerts_sent += 1

    pruned = prune_seen(state, now)
    save_state(data_dir, state)
    logger.info(
        "round done：items=%d new=%d alerts=%d malformed=%d pruned=%d baseline=%s seen_total=%d",
        len(items), len(new_entries), alerts_sent, malformed, pruned,
        baseline_mode, len(state.get("seen", {})),
    )

    # 短命進程 drain：daemon-thread alert 在 main 退出前排空（mirror incident_sentinel）。
    if alerts_sent and not dry_run:
        sleep_fn(drain_seconds)
    return 0


def main(argv=None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [BB-SENTINEL] %(levelname)s %(message)s",
    )
    parser = argparse.ArgumentParser(
        prog="bybit_announcement_sentinel",
        description="Bybit 公告增量哨兵：公開 API 輪詢 + seen-set 去重 + 分級告警（alert-only）。",
    )
    parser.add_argument(
        "--data-dir", default=os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"),
        help="runtime data dir（默認 $OPENCLAW_DATA_DIR else /tmp/openclaw，對齊 watchdog）")
    parser.add_argument("--once", action="store_true",
                        help="單輪模式（默認且唯一模式；旗標僅供 cron 行自說明）")
    parser.add_argument("--dry-run", action="store_true",
                        help="跑全輪但不發送（state 照寫；印 would-alert 清單）")
    args = parser.parse_args(argv)
    return run_once(args.data_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
