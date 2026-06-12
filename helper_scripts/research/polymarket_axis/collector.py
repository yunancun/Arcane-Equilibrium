"""Polymarket Gamma / CLOB 採集核心（throttled HTTP + 解析 + 攤平）。

MODULE_NOTE:
  模塊用途：
    - ThrottledJsonClient：urllib 標準庫 GET-JSON client（host allowlist +
      client-side throttle ≤2 req/s + 指數 backoff retry——上游稱 15K req/10s
      非約束，仍保守禮貌採集，QC memo §2）。
    - fetch_events_by_tag：Gamma ``GET /events`` tag 枚舉分頁（主路，deterministic；
      官方參數 limit/offset/tag_slug/closed，2026-06-11 真實 API probe 驗證：
      回應 = bare JSON array）。
    - fetch_search_events：``GET /public-search`` keyword 補充發現面（每頁 5
      events、回應 = {"events": [...], "pagination": {"hasMore": ...}}）。
    - fetch_market_by_id：``GET /markets/{id}`` path-form 單抓（track-to-resolution
      follow-up 用；probe 實證 query-form ``/markets?id=`` 默認濾掉 closed market，
      是陷阱，故必須用 path-form）。
    - fetch_prices_history：CLOB ``GET /prices-history``（retrospective lane 專用，
      唯讀 timeseries；CLOB 下單 / auth 類 endpoint 全程不碰）。
    - flatten_event_rows / flatten_market_row：market-level 一行/每 snapshot 攤平。
  依賴：僅標準庫（urllib / json / time / datetime）。零生產模組 import。
  硬邊界：
    - 採集端零 relevance 截斷、零 ranking、零丟 row：closed / 零流動性 / 任何
      內容的 market 一律入列（filter 是代碼可改版，raw 過去不可再生）。
      攤平失敗的 market 也保 row（parse_error 標記 + raw 全量），不靜默丟。
    - host allowlist 只含 gamma-api.polymarket.com / clob.polymarket.com 兩個
      唯讀公開 API base：結構性排除任何下單 / auth endpoint。
    - 默認 urlopen 禁 redirect（E3 2026-06-11）：30x 跟跳會把出口引去 allowlist 外
      host（allowlist 只驗請求 base，防不了 redirect），故 30x 一律升 HTTPError
      且不重試。本 helper 與 canary/alert_sink.py 同款（package 隔離紅線：本軸
      零跨 package import，故就地放一份最小副本，正本語義以 alert_sink 為準）。

上游出處（MIT attribution）：_parse_outcome_prices / _safe_float 與 closed/active
  欄位判讀移植自 last30days-skill（MIT, Copyright (c) 2026 Matt Van Horn）
  commit 122158415ae421da83e739f2668032f6bc78d39c 的
  skills/last30days/scripts/lib/polymarket.py；其 relevance / 截斷 / 搜索-UX
  邏輯已按 QC memo §1 丟棄。
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Optional

from . import (
    LANE_RETROSPECTIVE,
    LANE_SNAPSHOT,
    QUERY_SET_VERSION,
)

logger = logging.getLogger(__name__)

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"

# host allowlist（唯讀公開 API；見 MODULE_NOTE 硬邊界）。
_ALLOWED_BASES = (GAMMA_BASE, CLOB_BASE)

# throttle：≤2 req/s（QC memo §2 保守假設、禮貌採集）。
DEFAULT_MIN_INTERVAL_S = 0.5
DEFAULT_TIMEOUT_S = 20.0
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF_BASE_S = 1.0

# /events 枚舉每頁上限與 runaway 保險（50 頁 × 100 = 5000 events 遠超 crypto tag
# 現實規模；保險絲防 API 異常迴圈，不是 relevance 截斷——觸頂會記 warning + 入
# stats，研究端可見）。
EVENTS_PAGE_LIMIT = 100
MAX_EVENT_PAGES_DEFAULT = 50


class CollectorHTTPError(Exception):
    """請求在 retry 耗盡後仍失敗（caller 決定 fail-soft 路徑）。"""


class _RedirectRefusedHandler(urllib.request.HTTPRedirectHandler):
    """任何 30x redirect 升為 HTTPError（見 MODULE_NOTE 硬邊界：allowlist 防不了跟跳）。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        # newurl 截斷 200：Location 是外部可控文本，原樣嵌 error message 會經
        # exc log 灌爆 cron log（截斷自查 2026-06-12，與 canary/alert_sink.py 同步）。
        raise urllib.error.HTTPError(
            req.full_url, code, f"redirect refused (-> {str(newurl)[:200]!r})", headers, fp,
        )


_NO_REDIRECT_OPENER = urllib.request.build_opener(_RedirectRefusedHandler())


def _urlopen_no_redirect(req, timeout: float):
    """urlopen 等價物但禁 redirect；介面對齊注入式測試替身 callable(req, timeout=…)。"""
    return _NO_REDIRECT_OPENER.open(req, timeout=timeout)


class ThrottledJsonClient:
    """urllib GET-JSON client：throttle + 指數 backoff + host allowlist。

    為什麼可注入 urlopen/sleep/monotonic：單測以假 transport 驗分頁 / retry /
    throttle 行為，不打真網路（gate_b_rest InstrumentsInfoPoller 同模式）。
    """

    def __init__(
        self,
        *,
        min_interval_s: float = DEFAULT_MIN_INTERVAL_S,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        retries: int = DEFAULT_RETRIES,
        backoff_base_s: float = DEFAULT_BACKOFF_BASE_S,
        urlopen: Callable[..., Any] = _urlopen_no_redirect,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.min_interval_s = float(min_interval_s)
        self.timeout_s = float(timeout_s)
        self.retries = int(retries)
        self.backoff_base_s = float(backoff_base_s)
        self._urlopen = urlopen
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_request_at: Optional[float] = None
        self.request_count = 0

    def get_json(self, base: str, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        if base not in _ALLOWED_BASES:
            # fail-closed：allowlist 外的 base 是程式錯誤，不是可重試的網路況。
            raise ValueError(f"base not in allowlist: {base}")
        url = f"{base}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        last_error: Optional[str] = None
        for attempt in range(self.retries + 1):
            self._throttle()
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "openclaw-polymarket-axis/0.1"})
                with self._urlopen(req, timeout=self.timeout_s) as resp:
                    body = resp.read()
                self.request_count += 1
                return json.loads(body.decode("utf-8"))
            except urllib.error.HTTPError as exc:
                self.request_count += 1
                last_error = f"http_{exc.code}"
                # 30x = 默認 opener 拒 redirect 升上來的（E3）：redirect 不是可重試
                # 網路況（唯讀公開 API 正常路徑不應 redirect），立即終止不浪費 retry。
                if 300 <= exc.code < 400:
                    raise CollectorHTTPError(f"redirect_refused {last_error}: {url}") from exc
                # 4xx（除 429）= 請求本身錯，重試無意義；429/5xx 退避後重試。
                if exc.code != 429 and 400 <= exc.code < 500:
                    raise CollectorHTTPError(f"{last_error}: {url}") from exc
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                self.request_count += 1
                last_error = f"{type(exc).__name__}: {exc}"
            if attempt < self.retries:
                self._sleep(self.backoff_base_s * (2 ** attempt))
        raise CollectorHTTPError(f"retries exhausted ({last_error}): {url}")

    def _throttle(self) -> None:
        now = self._monotonic()
        if self._last_request_at is not None:
            wait = self.min_interval_s - (now - self._last_request_at)
            if wait > 0:
                self._sleep(wait)
                now = self._monotonic()
        self._last_request_at = now


# ---------------------------------------------------------------------------
# 上游移植解析 helper（MIT；見模塊頭 attribution）
# ---------------------------------------------------------------------------

def _parse_outcome_prices(market: dict[str, Any]) -> list[tuple[str, float]]:
    """解析 outcomePrices 為 (outcome_name, price) 列表。

    上游邏輯逐式保留：outcomes 與 outcomePrices 都可能是 JSON-encoded 字串
    （probe 實證：'["Yes", "No"]' / '["0", "1"]'），雙層 fail-soft 解析；
    單價非數值跳過該價、名缺位補 "Outcome {i+1}"。
    """
    outcomes_raw = market.get("outcomes") or []
    prices_raw = market.get("outcomePrices")

    if not prices_raw:
        return []

    try:
        if isinstance(outcomes_raw, str):
            outcomes = json.loads(outcomes_raw)
        else:
            outcomes = outcomes_raw
    except (json.JSONDecodeError, TypeError):
        outcomes = []

    try:
        if isinstance(prices_raw, str):
            prices = json.loads(prices_raw)
        else:
            prices = prices_raw
    except (json.JSONDecodeError, TypeError):
        return []

    result: list[tuple[str, float]] = []
    for i, price in enumerate(prices):
        try:
            p = float(price)
        except (ValueError, TypeError):
            continue
        name = outcomes[i] if i < len(outcomes) else f"Outcome {i+1}"
        result.append((str(name), p))

    return result


def _safe_float(val: Any, default: float = 0.0) -> float:
    """上游移植：失敗回 default 的浮點轉換（排序鍵等「必須有數」場景用）。"""
    try:
        return float(val or default)
    except (ValueError, TypeError):
        return default


def _float_or_none(val: Any) -> Optional[float]:
    """研究欄位用 None-保留變體：缺席 ≠ 0.0（probe 實證 market-level liquidity /
    volume24hr 可整欄缺席；硬填 0 會把「沒數據」偽裝成「零流動性」汙染研究）。"""
    if val is None or isinstance(val, bool):
        return None
    try:
        out = float(val)
    except (ValueError, TypeError):
        return None
    return out


# ---------------------------------------------------------------------------
# Gamma / CLOB 抓取
# ---------------------------------------------------------------------------

def fetch_events_by_tag(
    client: ThrottledJsonClient,
    *,
    tag_slug: str,
    closed: bool = False,
    max_pages: int = MAX_EVENT_PAGES_DEFAULT,
    page_limit: int = EVENTS_PAGE_LIMIT,
    order: Optional[str] = None,
    ascending: Optional[bool] = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Gamma /events tag 枚舉主路：limit/offset 分頁直到短頁。

    回 (events, stats)。stats.page_cap_hit=True 代表觸到 runaway 保險絲，
    研究端必須知道枚舉不完整（誠實披露，非靜默截斷）。
    """
    events: list[dict[str, Any]] = []
    pages = 0
    page_cap_hit = False
    offset = 0
    while pages < max_pages:
        params: dict[str, Any] = {
            "tag_slug": tag_slug,
            "closed": "true" if closed else "false",
            "limit": str(page_limit),
            "offset": str(offset),
        }
        if order:
            params["order"] = order
        if ascending is not None:
            params["ascending"] = "true" if ascending else "false"
        page = client.get_json(GAMMA_BASE, "/events", params)
        pages += 1
        if not isinstance(page, list):
            # schema 漂移 fail-soft：非預期形狀停止分頁，已收 events 照常回。
            logger.warning("gamma /events non-list page (type=%s); stop pagination", type(page).__name__)
            break
        events.extend(e for e in page if isinstance(e, dict))
        if len(page) < page_limit:
            break
        offset += page_limit
    else:
        page_cap_hit = True
        logger.warning("gamma /events page cap hit (max_pages=%s); enumeration incomplete", max_pages)
    stats = {"pages": pages, "page_cap_hit": page_cap_hit, "events": len(events)}
    return events, stats


def fetch_search_events(
    client: ThrottledJsonClient,
    *,
    keyword: str,
    max_pages: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """/public-search keyword 補充發現面（每頁 5 events；hasMore=false 早停）。

    為什麼仍要它：tag 枚舉漏掉「沒掛 crypto tag 但與 crypto 高相關」的事件
    （宏觀 Fed/CPI、監管 SEC/ETF 類），keyword 集是查詢集 v1 的第二圈。
    """
    events: list[dict[str, Any]] = []
    pages = 0
    for page_no in range(1, max_pages + 1):
        params = {"q": keyword, "page": str(page_no), "events_status": "active"}
        try:
            payload = client.get_json(GAMMA_BASE, "/public-search", params)
        except CollectorHTTPError as exc:
            # 單 keyword 失敗不連累其他 keyword（fail-soft；error 入 stats）。
            return events, {"pages": pages, "error": str(exc), "events": len(events)}
        pages += 1
        if not isinstance(payload, dict):
            break
        page_events = payload.get("events") or []
        events.extend(e for e in page_events if isinstance(e, dict))
        pagination = payload.get("pagination") or {}
        if not pagination.get("hasMore", False):
            break
    return events, {"pages": pages, "events": len(events)}


def fetch_market_by_id(client: ThrottledJsonClient, market_id: str) -> dict[str, Any]:
    """GET /markets/{id} path-form 單抓（follow-up 專用）。

    為什麼不用 /markets?id=：probe 實證 query-form 默認套 closed 過濾，closed
    market 回空列表——而 follow-up 的對象恰恰大多 closed。path-form 無此過濾。
    """
    mid = str(market_id).strip()
    if not mid or not mid.isdigit():
        raise ValueError(f"invalid market id: {market_id!r}")
    payload = client.get_json(GAMMA_BASE, f"/markets/{mid}")
    if not isinstance(payload, dict):
        raise CollectorHTTPError(f"/markets/{mid} returned non-dict")
    return payload


def fetch_prices_history(
    client: ThrottledJsonClient,
    *,
    clob_token_id: str,
    interval: Optional[str] = None,
    fidelity: Optional[int] = None,
    start_ts: Optional[int] = None,
    end_ts: Optional[int] = None,
) -> dict[str, Any]:
    """CLOB /prices-history（retrospective lane 唯一抓取面）。

    已知限制（QC memo §6 + probe 實證）：resolved/closed 市場僅 ≥12h 粒度、
    部分 token 直接空 history——空回應是預期結果，照存（研究端勿假設細粒度
    可事後補）。
    """
    params: dict[str, Any] = {"market": str(clob_token_id)}
    if interval:
        params["interval"] = interval
    if fidelity is not None:
        params["fidelity"] = str(int(fidelity))
    if start_ts is not None:
        params["startTs"] = str(int(start_ts))
    if end_ts is not None:
        params["endTs"] = str(int(end_ts))
    payload = client.get_json(CLOB_BASE, "/prices-history", params)
    if not isinstance(payload, dict):
        raise CollectorHTTPError("/prices-history returned non-dict")
    return payload


# ---------------------------------------------------------------------------
# 攤平（market-level 一行/每 snapshot）
# ---------------------------------------------------------------------------

def _event_header(event: dict[str, Any]) -> dict[str, Any]:
    """event 原始 JSON 去掉 markets 鍵的 header（raw 保底用）。

    為什麼去 markets：raw event 整包嵌進每個 market row 會把全部 sibling market
    重複 N 次；header + 各 market 自己的 raw 已是無損覆蓋。
    """
    return {k: v for k, v in event.items() if k != "markets"}


def flatten_market_row(
    market: dict[str, Any],
    event: dict[str, Any],
    *,
    snapshot_ts_utc: str,
    collector_git_sha: str,
    row_source: str,
    discovery_queries: Optional[list[str]] = None,
) -> dict[str, Any]:
    """單 market → 一行 snapshot row（QC memo §2 欄位最小集 + raw 保底）。

    零過濾不變量：本函數對任何輸入 market 都產出一行——closed / 零流動性 /
    欄位缺漏 / 解析失敗統統入列（parse 失敗時欄位置 None + parse_error 標記，
    raw 永遠全量保留，schema 漂移 fail-soft）。
    """
    row: dict[str, Any] = {
        "snapshot_ts_utc": snapshot_ts_utc,
        "lane": LANE_SNAPSHOT,
        "query_set_version": QUERY_SET_VERSION,
        "collector_git_sha": collector_git_sha,
        "row_source": row_source,
        "discovery_queries": list(discovery_queries or []),
        "parse_error": None,
    }
    try:
        outcome_pairs = _parse_outcome_prices(market)
        row.update({
            # event 欄位攤平（event-level volume/liquidity/competitive 為主源：
            # probe 實證 market-level volume24hr/liquidity 可缺席）。
            "event_id": str(event.get("id") or ""),
            "event_slug": event.get("slug"),
            "event_title": event.get("title"),
            "event_tags": _tag_slugs(event),
            "event_closed": event.get("closed"),
            "event_active": event.get("active"),
            "event_end_date": event.get("endDate"),
            "event_updated_at": event.get("updatedAt"),
            "event_liquidity": _float_or_none(event.get("liquidity")),
            "event_competitive": _float_or_none(event.get("competitive")),
            "event_volume24hr": _float_or_none(event.get("volume24hr")),
            "event_volume1wk": _float_or_none(event.get("volume1wk")),
            "event_volume1mo": _float_or_none(event.get("volume1mo")),
            # market 欄位。
            "market_id": str(market.get("id") or ""),
            "question": market.get("question"),
            "market_slug": market.get("slug"),
            "outcomes": [name for name, _ in outcome_pairs],
            "outcome_prices": [price for _, price in outcome_pairs],
            "clob_token_ids": _clob_token_ids(market),
            "volume_num": _float_or_none(market.get("volumeNum") if "volumeNum" in market else market.get("volume")),
            "volume24hr": _float_or_none(market.get("volume24hr")),
            "volume1wk": _float_or_none(market.get("volume1wk")),
            "volume1mo": _float_or_none(market.get("volume1mo")),
            "liquidity_num": _float_or_none(market.get("liquidityNum") if "liquidityNum" in market else market.get("liquidity")),
            "one_day_price_change": _float_or_none(market.get("oneDayPriceChange")),
            "one_week_price_change": _float_or_none(market.get("oneWeekPriceChange")),
            "one_month_price_change": _float_or_none(market.get("oneMonthPriceChange")),
            "end_date": market.get("endDate"),
            "closed": market.get("closed"),
            "active": market.get("active"),
            "uma_resolution_status": market.get("umaResolutionStatus"),
            "closed_time": market.get("closedTime"),
            "updated_at": market.get("updatedAt"),
        })
    except Exception as exc:  # noqa: BLE001 —— 攤平失敗仍要保 row（零丟 row 不變量）。
        row["parse_error"] = f"{type(exc).__name__}: {exc}"
        row.setdefault("event_id", str(event.get("id") or ""))
        row.setdefault("market_id", str(market.get("id") or ""))
    # raw 保底永遠附上（schema 漂移時的唯一完整事實源）。
    row["raw_market"] = market
    row["raw_event_header"] = _event_header(event)
    return row


def _tag_slugs(event: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for tag in event.get("tags") or []:
        if isinstance(tag, dict):
            slug = tag.get("slug") or tag.get("label")
            if slug:
                out.append(str(slug))
        elif tag:
            out.append(str(tag))
    return out


def _clob_token_ids(market: dict[str, Any]) -> list[str]:
    raw = market.get("clobTokenIds")
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(t) for t in raw]
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return [str(t) for t in parsed] if isinstance(parsed, list) else []


def flatten_event_rows(
    event: dict[str, Any],
    *,
    snapshot_ts_utc: str,
    collector_git_sha: str,
    row_source: str,
    discovery_queries: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """event → 各 market row。markets 缺席 / 空 = 0 行（無 market 可攤），
    但 raw event 仍由 caller 寫入 raw lane（不丟 event 本體）。"""
    markets = event.get("markets")
    if not isinstance(markets, list):
        return []
    return [
        flatten_market_row(
            m, event,
            snapshot_ts_utc=snapshot_ts_utc,
            collector_git_sha=collector_git_sha,
            row_source=row_source,
            discovery_queries=discovery_queries,
        )
        for m in markets if isinstance(m, dict)
    ]


# ---------------------------------------------------------------------------
# 三模式採集編排（純函數核心；artifact 寫出由 cli 層負責）
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def collect_snapshot_sweep(
    client: ThrottledJsonClient,
    tracker,
    *,
    collector_git_sha: str,
    tag_slug: str,
    keywords: tuple[str, ...],
    keyword_pages: int,
    max_event_pages: int = MAX_EVENT_PAGES_DEFAULT,
    top_n: Optional[int] = None,
    now_iso: Optional[str] = None,
) -> dict[str, Any]:
    """snapshot lane 單輪 sweep（daily 全量 / hourly-topn 由參數差異化）。

    daily：tag 枚舉全分頁 + keyword 補充 + tracked follow-up。
    hourly-topn：top_n 給定時改走 order=volume24hr 降冪單頁 top-N（server-side
      排序非採集端 relevance 截斷——「只抓 top-N」本身是 QC memo §2 規定的
      hourly 查詢範圍圈定），不跑 keyword 補充與 follow-up（daily 專責）。

    回 {"rows", "raw_events", "raw_markets", "stats", "errors"}；
    tracker（state.TrackerState）就地更新，由 caller 決定何時持久化。
    """
    now = now_iso or _utc_now_iso()
    rows: list[dict[str, Any]] = []
    raw_events: list[dict[str, Any]] = []
    raw_markets: list[dict[str, Any]] = []
    errors: list[str] = []
    stats: dict[str, Any] = {"mode_top_n": top_n}

    seen_market_ids: set[str] = set()
    # 兩階段：先聚合全部發現源（tag / keyword 重疊時記全部 query 標籤），再一次
    # 發行 row——row 的 discovery_queries 才能完整反映多源；重疊去重是冪等合併
    # 非 relevance 過濾（同一 event 不重複攤平，首見 payload 為準）。
    ordered_event_ids: list[str] = []
    events_meta: dict[str, dict[str, Any]] = {}

    def _gather_events(events: list[dict[str, Any]], query_label: str, row_source: str) -> None:
        for event in events:
            event_id = str(event.get("id") or "")
            if not event_id:
                continue
            meta = events_meta.get(event_id)
            if meta is None:
                meta = {"event": event, "row_source": row_source, "queries": []}
                events_meta[event_id] = meta
                ordered_event_ids.append(event_id)
            if query_label not in meta["queries"]:
                meta["queries"].append(query_label)

    def _emit_all() -> None:
        for event_id in ordered_event_ids:
            meta = events_meta[event_id]
            event = meta["event"]
            raw_events.append({
                "fetched_at_utc": now,
                "row_source": meta["row_source"],
                "queries": list(meta["queries"]),
                "event": event,
            })
            rows.extend(flatten_event_rows(
                event,
                snapshot_ts_utc=now,
                collector_git_sha=collector_git_sha,
                row_source=meta["row_source"],
                discovery_queries=meta["queries"],
            ))
            for m in (event.get("markets") or []):
                if not isinstance(m, dict):
                    continue
                mid = str(m.get("id") or "")
                if mid:
                    seen_market_ids.add(mid)
                tracker.record_seen(m, event_id, seen_at_utc=now)

    # ---- 主路：tag 枚舉 ----
    if top_n is not None:
        # hourly-topn：server-side volume24hr 降冪，單頁 top-N
        # （camelCase 參數形 2026-06-11 真 API 實證有效；文檔頁的 snake_case
        #   volume_24hr 實測不排序）。
        try:
            events, tag_stats = fetch_events_by_tag(
                client, tag_slug=tag_slug, closed=False,
                max_pages=1, page_limit=int(top_n),
                order="volume24hr", ascending=False,
            )
            _gather_events(events, f"tag:{tag_slug}|order=volume24hr|top{top_n}", "events_tag_topn")
            stats["tag_enumeration"] = tag_stats
        except CollectorHTTPError as exc:
            errors.append(f"tag_topn:{exc}")
        _emit_all()
    else:
        try:
            events, tag_stats = fetch_events_by_tag(
                client, tag_slug=tag_slug, closed=False, max_pages=max_event_pages,
            )
            _gather_events(events, f"tag:{tag_slug}", "events_tag")
            stats["tag_enumeration"] = tag_stats
        except CollectorHTTPError as exc:
            errors.append(f"tag_enumeration:{exc}")

        # ---- 補充：keyword 搜索 ----
        keyword_stats: dict[str, Any] = {}
        for kw in keywords if keyword_pages > 0 else ():
            events, kw_stats = fetch_search_events(client, keyword=kw, max_pages=keyword_pages)
            keyword_stats[kw] = kw_stats
            if kw_stats.get("error"):
                errors.append(f"keyword:{kw}:{kw_stats['error']}")
            _gather_events(events, f"kw:{kw}", "public_search")
        stats["keyword_supplement"] = keyword_stats
        _emit_all()

        # ---- track-to-resolution follow-up（本輪沒見到的 tracking 中 market）----
        follow_ids = tracker.follow_up_ids(seen_market_ids)
        follow_ok = 0
        follow_fail = 0
        for mid in follow_ids:
            try:
                market = fetch_market_by_id(client, mid)
            except (CollectorHTTPError, ValueError) as exc:
                follow_fail += 1
                tracker.record_fetch_error(mid)
                errors.append(f"follow_up:{mid}:{exc}")
                continue
            follow_ok += 1
            raw_markets.append({"fetched_at_utc": now, "row_source": "resolution_follow_up", "market": market})
            # follow-up 的 event 上下文只剩 id（path-form 不帶 event 包裝），
            # 以 tracker 登記的 event_id 構造最小 event header。
            entry = tracker.entries.get(mid) or {}
            pseudo_event = {"id": entry.get("event_id", "")}
            rows.append(flatten_market_row(
                market, pseudo_event,
                snapshot_ts_utc=now,
                collector_git_sha=collector_git_sha,
                row_source="resolution_follow_up",
            ))
            tracker.record_seen(market, entry.get("event_id", ""), seen_at_utc=now)
        stats["follow_up"] = {"attempted": len(follow_ids), "ok": follow_ok, "failed": follow_fail}

    stats.update({
        "unique_events": len(ordered_event_ids),
        "snapshot_rows": len(rows),
        "tracker_counts": tracker.counts(),
        "http_requests": client.request_count,
    })
    return {"rows": rows, "raw_events": raw_events, "raw_markets": raw_markets, "stats": stats, "errors": errors}


def collect_prices_history(
    client: ThrottledJsonClient,
    *,
    token_jobs: list[dict[str, Any]],
    interval: Optional[str],
    fidelity: Optional[int],
    start_ts: Optional[int],
    end_ts: Optional[int],
    collector_git_sha: str,
    now_iso: Optional[str] = None,
) -> dict[str, Any]:
    """retrospective lane：逐 clob token 拉 /prices-history。

    每 token 一行（含空 history——已知限制照存）；單 token 失敗不連累其他。
    行內 lane=retrospective + retrieved_at_utc 拉取日標記（QC memo §2：獨立
    artifact lane，永不混入 snapshot lane 充當「當時採集」）。
    """
    now = now_iso or _utc_now_iso()
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for job in token_jobs:
        token = str(job.get("clob_token_id") or "")
        if not token:
            continue
        base_row = {
            "lane": LANE_RETROSPECTIVE,
            "retrospective": True,
            "retrieved_at_utc": now,
            "collector_git_sha": collector_git_sha,
            "market_id": job.get("market_id"),
            "clob_token_id": token,
            "interval": interval,
            "fidelity": fidelity,
            "start_ts": start_ts,
            "end_ts": end_ts,
        }
        try:
            payload = fetch_prices_history(
                client, clob_token_id=token,
                interval=interval, fidelity=fidelity, start_ts=start_ts, end_ts=end_ts,
            )
        except CollectorHTTPError as exc:
            errors.append(f"prices_history:{token}:{exc}")
            rows.append({**base_row, "fetch_error": str(exc), "history": None, "n_points": None})
            continue
        history = payload.get("history") or []
        rows.append({**base_row, "fetch_error": None, "history": history, "n_points": len(history)})
    stats = {"tokens": len(token_jobs), "rows": len(rows), "http_requests": client.request_count}
    return {"rows": rows, "stats": stats, "errors": errors}
