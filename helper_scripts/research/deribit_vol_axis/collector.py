"""Deribit 公開 API 採集核心（throttled HTTP + 解析 + term-structure/skew 構造）。

MODULE_NOTE:
  模塊用途：
    - ThrottledJsonClient：urllib 標準庫 GET-JSON client（host allowlist +
      client-side throttle ≤2 req/s + 指數 backoff retry + 禁 redirect）。Deribit
      JSON-RPC over HTTP：result 在 payload["result"]，錯誤在 payload["error"]
      （HTTP 200 也可能帶 error body，本層偵測 error 物件並升 CollectorHTTPError）。
    - fetch_dvol：GET /public/get_volatility_index_data（DVOL OHLC 序列，唯讀）。
    - fetch_book_summary：GET /public/get_book_summary_by_currency（kind=option，
      單請求回全部 option instrument 含 mark_iv + underlying_price）。
    - parse_instrument_name：CCY-DDMMMYY-STRIKE-{C|P} 解析成 (ccy, expiry_date,
      strike, option_type)。
    - build_term_structure / build_skew：採集端從 surface 構造 ATM IV term-structure
      與 put/call skew（純函數，零過濾、零丟 instrument）。
  依賴：僅標準庫（urllib / json / time / datetime）。零生產模組 import。
  硬邊界：
    - 採集端零 relevance 截斷、零 ranking、零丟 instrument：mark_iv 缺席 / 零
      流動性 / 任何到期的 instrument 一律入 raw surface（filter 是代碼可改版，
      raw 過去不可再生）。term-structure / skew 是 raw 之上的衍生視圖，缺料的
      cell 標 None 不靜默丟。
    - host allowlist 只含 www.deribit.com（唯讀公開 API base）：結構性排除任何
      /api/v2/private/* auth / 下單 endpoint。
    - 默認 urlopen 禁 redirect（mirror polymarket_axis / canary alert_sink）：30x
      跟跳會把出口引去 allowlist 外 host，故 30x 一律升 HTTPError 且不重試。
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Optional

from . import COLLECTION_SET_VERSION

logger = logging.getLogger(__name__)

DERIBIT_BASE = "https://www.deribit.com"

# host allowlist（唯讀公開 API base；見 MODULE_NOTE 硬邊界）。
_ALLOWED_BASES = (DERIBIT_BASE,)

# throttle：≤2 req/s（保守禮貌採集，mirror polymarket_axis 假設）。
DEFAULT_MIN_INTERVAL_S = 0.5
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF_BASE_S = 1.0

# DVOL 序列預設粒度（秒）：3600 = 1h bar；單次回補窗口預設 24h（daily snapshot
# 取最近一日 DVOL OHLC，append-only 不回填更早歷史）。
DVOL_RESOLUTION_S_DEFAULT = 3600
DVOL_WINDOW_S_DEFAULT = 24 * 3600

# instrument_name 月份縮寫 → 月（Deribit 採大寫三字母英文月）。
_MONTH_ABBR = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

# CCY-DDMMMYY-STRIKE-{C|P}，例：BTC-26MAR27-105000-C。
# strike 允許小數（罕見但 schema 容錯）；型別 C=call / P=put。
_INSTRUMENT_RE = re.compile(
    r"^(?P<ccy>[A-Z0-9]+)-(?P<day>\d{1,2})(?P<mon>[A-Z]{3})(?P<yy>\d{2})-"
    r"(?P<strike>\d+(?:\.\d+)?)-(?P<otype>[CP])$"
)


class CollectorHTTPError(Exception):
    """請求在 retry 耗盡後仍失敗，或 JSON-RPC error body（caller 決定 fail-soft）。"""


class _RedirectRefusedHandler(urllib.request.HTTPRedirectHandler):
    """任何 30x redirect 升為 HTTPError（allowlist 防不了跟跳，mirror polymarket_axis）。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        # newurl 截斷 200：Location 是外部可控文本，原樣嵌 error 會灌爆 cron log。
        raise urllib.error.HTTPError(
            req.full_url, code, f"redirect refused (-> {str(newurl)[:200]!r})", headers, fp,
        )


_NO_REDIRECT_OPENER = urllib.request.build_opener(_RedirectRefusedHandler())


def _urlopen_no_redirect(req, timeout: float):
    """urlopen 等價物但禁 redirect；介面對齊注入式測試替身 callable(req, timeout=…)。"""
    return _NO_REDIRECT_OPENER.open(req, timeout=timeout)


class ThrottledJsonClient:
    """urllib GET-JSON client：throttle + 指數 backoff + host allowlist + 禁 redirect。

    為什麼可注入 urlopen/sleep/monotonic：單測以假 transport 驗分頁 / retry /
    throttle 行為，不打真網路（mirror polymarket_axis ThrottledJsonClient）。

    Deribit JSON-RPC 語意：成功回 {"result": ...}；錯誤回 {"error": {...}}（即使
    HTTP 200）。本 client 在拿到 dict 後檢查 error 物件並升 CollectorHTTPError，
    使 caller 不會把錯誤 body 誤當資料。
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

    def get_result(self, base: str, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        """GET JSON-RPC 並回 payload["result"]（error body 升 CollectorHTTPError）。"""
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
                req = urllib.request.Request(url, headers={"User-Agent": "openclaw-deribit-vol-axis/0.1"})
                with self._urlopen(req, timeout=self.timeout_s) as resp:
                    body = resp.read()
                self.request_count += 1
                payload = json.loads(body.decode("utf-8"))
                if isinstance(payload, dict) and payload.get("error"):
                    # JSON-RPC error body（HTTP 200 仍可能帶）：請求語意錯，不重試。
                    err = payload.get("error")
                    raise CollectorHTTPError(f"jsonrpc_error {str(err)[:200]}: {url}")
                if not isinstance(payload, dict) or "result" not in payload:
                    raise CollectorHTTPError(f"missing result: {url}")
                return payload["result"]
            except urllib.error.HTTPError as exc:
                self.request_count += 1
                last_error = f"http_{exc.code}"
                # 30x = 禁 redirect 升上來的：唯讀公開 API 正常路徑不應 redirect，
                # 立即終止不浪費 retry。
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
# 解析 helper
# ---------------------------------------------------------------------------

def _float_or_none(val: Any) -> Optional[float]:
    """研究欄位用 None-保留變體：缺席 ≠ 0.0（mark_iv / underlying 可整欄缺席；
    硬填 0 會把「沒數據」偽裝成「零波動」汙染研究，mirror polymarket_axis 教訓）。"""
    if val is None or isinstance(val, bool):
        return None
    try:
        out = float(val)
    except (ValueError, TypeError):
        return None
    return out


def parse_instrument_name(name: str) -> Optional[dict[str, Any]]:
    """CCY-DDMMMYY-STRIKE-{C|P} → {ccy, expiry_date, strike, option_type}。

    解析失敗回 None（caller 仍保 raw row，不丟 instrument）；expiry_date 取
    UTC 當日（Deribit 期權 08:00 UTC 結算，但研究只需到期「日」做 term bucket，
    日粒度足夠且避免硬編結算時刻假設）。
    """
    m = _INSTRUMENT_RE.match(str(name).strip())
    if m is None:
        return None
    mon = _MONTH_ABBR.get(m.group("mon"))
    if mon is None:
        return None
    try:
        day = int(m.group("day"))
        year = 2000 + int(m.group("yy"))
        expiry = dt.date(year, mon, day)
        strike = float(m.group("strike"))
    except (ValueError, TypeError):
        return None
    return {
        "ccy": m.group("ccy"),
        "expiry_date": expiry.isoformat(),
        "strike": strike,
        "option_type": "call" if m.group("otype") == "C" else "put",
    }


# ---------------------------------------------------------------------------
# Deribit 抓取
# ---------------------------------------------------------------------------

def fetch_dvol(
    client: ThrottledJsonClient,
    *,
    currency: str,
    start_ts_ms: int,
    end_ts_ms: int,
    resolution_s: int = DVOL_RESOLUTION_S_DEFAULT,
) -> dict[str, Any]:
    """GET /public/get_volatility_index_data → DVOL OHLC 序列（唯讀）。

    回 result：{"data": [[ts_ms, open, high, low, close], ...], "continuation": ...}。
    OHLC 單位 = 年化波動率百分比（probe 實證 BTC ≈ 40）。空 data 是合法結果照存。
    """
    params = {
        "currency": str(currency),
        "start_timestamp": str(int(start_ts_ms)),
        "end_timestamp": str(int(end_ts_ms)),
        "resolution": str(int(resolution_s)),
    }
    result = client.get_result(DERIBIT_BASE, "/api/v2/public/get_volatility_index_data", params)
    if not isinstance(result, dict):
        raise CollectorHTTPError("get_volatility_index_data returned non-dict result")
    return result


def fetch_book_summary(
    client: ThrottledJsonClient,
    *,
    currency: str,
) -> list[dict[str, Any]]:
    """GET /public/get_book_summary_by_currency（kind=option）→ 全 option instrument。

    單請求覆蓋全鏈（probe 實證 BTC 944 筆），每筆含 mark_iv + underlying_price +
    open_interest + volume。為什麼不用逐 instrument ticker：book_summary 單請求即
    PIT 一致快照（同一時刻全 surface），逐 ticker loop 既慢又會跨時刻拼接破 PIT。
    """
    params = {"currency": str(currency), "kind": "option"}
    result = client.get_result(DERIBIT_BASE, "/api/v2/public/get_book_summary_by_currency", params)
    if not isinstance(result, list):
        raise CollectorHTTPError("get_book_summary_by_currency returned non-list result")
    return [r for r in result if isinstance(r, dict)]


# ---------------------------------------------------------------------------
# 攤平 + 衍生視圖構造（純函數核心；artifact 寫出由 cli 層負責）
# ---------------------------------------------------------------------------

def flatten_dvol_rows(
    result: dict[str, Any],
    *,
    currency: str,
    snapshot_ts_utc: str,
    collector_git_sha: str,
) -> list[dict[str, Any]]:
    """DVOL result.data → 每 bar 一行（零丟：壞 bar 標 parse_error 仍入列）。"""
    rows: list[dict[str, Any]] = []
    data = result.get("data") or []
    if not isinstance(data, list):
        return rows
    for bar in data:
        row: dict[str, Any] = {
            "snapshot_ts_utc": snapshot_ts_utc,
            "currency": currency,
            "collection_set_version": COLLECTION_SET_VERSION,
            "collector_git_sha": collector_git_sha,
            "parse_error": None,
        }
        try:
            # bar = [ts_ms, open, high, low, close]（probe 實證 5 元）。
            row.update({
                "bar_ts_ms": int(bar[0]),
                "dvol_open": _float_or_none(bar[1]),
                "dvol_high": _float_or_none(bar[2]),
                "dvol_low": _float_or_none(bar[3]),
                "dvol_close": _float_or_none(bar[4]),
            })
        except (IndexError, TypeError, ValueError) as exc:
            row["parse_error"] = f"{type(exc).__name__}: {exc}"
        row["raw_bar"] = bar
        rows.append(row)
    return rows


def flatten_surface_rows(
    summary: list[dict[str, Any]],
    *,
    currency: str,
    snapshot_ts_utc: str,
    collector_git_sha: str,
) -> list[dict[str, Any]]:
    """book_summary 各 option → 一行 IV surface row（零過濾、raw 全量保底）。

    零過濾不變量（mirror polymarket_axis flatten_market_row）：任何 instrument 都
    產出一行——零 OI / 零 volume / mark_iv 缺漏 / 名稱解析失敗統統入列（parse 失敗
    時欄位置 None + parse_error 標記，raw 永遠全量保留）。
    """
    rows: list[dict[str, Any]] = []
    for item in summary:
        row: dict[str, Any] = {
            "snapshot_ts_utc": snapshot_ts_utc,
            "currency": currency,
            "collection_set_version": COLLECTION_SET_VERSION,
            "collector_git_sha": collector_git_sha,
            "parse_error": None,
        }
        try:
            name = str(item.get("instrument_name") or "")
            parsed = parse_instrument_name(name)
            row.update({
                "instrument_name": name,
                "expiry_date": parsed["expiry_date"] if parsed else None,
                "strike": parsed["strike"] if parsed else None,
                "option_type": parsed["option_type"] if parsed else None,
                "name_parse_ok": parsed is not None,
                "mark_iv": _float_or_none(item.get("mark_iv")),
                "underlying_price": _float_or_none(item.get("underlying_price")),
                "mark_price": _float_or_none(item.get("mark_price")),
                "mid_price": _float_or_none(item.get("mid_price")),
                "open_interest": _float_or_none(item.get("open_interest")),
                "volume": _float_or_none(item.get("volume")),
                "volume_usd": _float_or_none(item.get("volume_usd")),
                "underlying_index": item.get("underlying_index"),
                "creation_timestamp": item.get("creation_timestamp"),
            })
        except Exception as exc:  # noqa: BLE001 —— 攤平失敗仍保 row（零丟不變量）。
            row["parse_error"] = f"{type(exc).__name__}: {exc}"
            row.setdefault("instrument_name", str(item.get("instrument_name") or ""))
        row["raw_instrument"] = item
        rows.append(row)
    return rows


def _nearest_atm(rows_for_expiry: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """單一到期內挑「最接近 ATM」的 instrument（|strike - underlying| 最小）。

    為什麼用 nearest-strike 而非插值：研究端 term-structure 只需穩定 ATM proxy；
    真插值需 bid/ask IV（book_summary 不帶）+ 假設，採集端不引入估計假設，把
    nearest-strike ATM IV 當 proxy 並標 atm_strike / underlying 供研究端自行精算。
    """
    best: Optional[dict[str, Any]] = None
    best_dist: Optional[float] = None
    for r in rows_for_expiry:
        strike = r.get("strike")
        und = r.get("underlying_price")
        iv = r.get("mark_iv")
        if strike is None or und is None or iv is None:
            continue
        dist = abs(float(strike) - float(und))
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best = r
    return best


def build_term_structure(
    surface_rows: list[dict[str, Any]],
    *,
    currency: str,
    snapshot_ts_utc: str,
) -> list[dict[str, Any]]:
    """各到期 ATM IV term-structure（每到期一行；零料到期照標 None 不丟）。

    衍生視圖契約：term-structure 是 surface 之上的 ATM proxy 摘要，缺 mark_iv /
    underlying 的到期仍產一行（atm_mark_iv=None），研究端可見「該到期無有效 ATM
    報價」而非靜默消失。
    """
    by_expiry: dict[str, list[dict[str, Any]]] = {}
    for r in surface_rows:
        exp = r.get("expiry_date")
        if exp is None:
            continue
        by_expiry.setdefault(str(exp), []).append(r)

    out: list[dict[str, Any]] = []
    for exp in sorted(by_expiry):
        bucket = by_expiry[exp]
        atm = _nearest_atm(bucket)
        out.append({
            "snapshot_ts_utc": snapshot_ts_utc,
            "currency": currency,
            "expiry_date": exp,
            "n_instruments": len(bucket),
            "atm_strike": atm.get("strike") if atm else None,
            "atm_option_type": atm.get("option_type") if atm else None,
            "atm_mark_iv": atm.get("mark_iv") if atm else None,
            "underlying_price": atm.get("underlying_price") if atm else None,
        })
    return out


def build_skew(
    surface_rows: list[dict[str, Any]],
    *,
    currency: str,
    snapshot_ts_utc: str,
) -> list[dict[str, Any]]:
    """各到期 put/call skew（每到期一行；以 ATM-side IV 為基準算 OTM put/call 偏度）。

    定義（採集端最小、無假設）：
      - put_25d_proxy / call_25d_proxy：缺 delta（book_summary 不帶逐筆 greeks），
        故以「最接近 underlying×(1±skew_band) 的 OTM strike」的 mark_iv 作 wing proxy；
        skew_band 預設 0.10（±10% moneyness）。
      - skew_proxy_bps = (otm_put_iv - otm_call_iv) × 100（vol point → bps；正值 =
        put wing 較貴 = 偏空保護需求）。
    缺任一 wing 的到期標 None（不丟行）；研究端可用 surface_rows 自行精算 25Δ skew。
    """
    band = 0.10
    by_expiry: dict[str, list[dict[str, Any]]] = {}
    for r in surface_rows:
        exp = r.get("expiry_date")
        if exp is None:
            continue
        by_expiry.setdefault(str(exp), []).append(r)

    out: list[dict[str, Any]] = []
    for exp in sorted(by_expiry):
        bucket = by_expiry[exp]
        und = _representative_underlying(bucket)
        otm_put = _wing_iv(bucket, und, "put", band) if und is not None else None
        otm_call = _wing_iv(bucket, und, "call", band) if und is not None else None
        skew_bps = None
        if otm_put is not None and otm_call is not None:
            skew_bps = (otm_put["mark_iv"] - otm_call["mark_iv"]) * 100.0
        out.append({
            "snapshot_ts_utc": snapshot_ts_utc,
            "currency": currency,
            "expiry_date": exp,
            "underlying_price": und,
            "skew_band": band,
            "otm_put_strike": otm_put["strike"] if otm_put else None,
            "otm_put_iv": otm_put["mark_iv"] if otm_put else None,
            "otm_call_strike": otm_call["strike"] if otm_call else None,
            "otm_call_iv": otm_call["mark_iv"] if otm_call else None,
            "skew_proxy_bps": skew_bps,
        })
    return out


def _representative_underlying(bucket: list[dict[str, Any]]) -> Optional[float]:
    """同到期 bucket 的代表 underlying（取第一個非空；同一快照同幣 underlying 一致）。"""
    for r in bucket:
        und = r.get("underlying_price")
        if und is not None:
            return float(und)
    return None


def _wing_iv(
    bucket: list[dict[str, Any]],
    underlying: float,
    option_type: str,
    band: float,
) -> Optional[dict[str, Any]]:
    """挑 OTM wing 上最接近目標 moneyness 的 instrument（put 取 strike<und 側、
    call 取 strike>und 側；目標 strike = und×(1∓band)）。缺有效報價回 None。"""
    if option_type == "put":
        target = underlying * (1.0 - band)
        candidates = [
            r for r in bucket
            if r.get("option_type") == "put" and r.get("strike") is not None
            and r.get("mark_iv") is not None and float(r["strike"]) < underlying
        ]
    else:
        target = underlying * (1.0 + band)
        candidates = [
            r for r in bucket
            if r.get("option_type") == "call" and r.get("strike") is not None
            and r.get("mark_iv") is not None and float(r["strike"]) > underlying
        ]
    if not candidates:
        return None
    best = min(candidates, key=lambda r: abs(float(r["strike"]) - target))
    return {"strike": float(best["strike"]), "mark_iv": float(best["mark_iv"])}


# ---------------------------------------------------------------------------
# 單輪採集編排（純函數核心）
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def collect_vol_snapshot(
    client: ThrottledJsonClient,
    *,
    currencies: tuple[str, ...],
    collector_git_sha: str,
    dvol_window_s: int = DVOL_WINDOW_S_DEFAULT,
    dvol_resolution_s: int = DVOL_RESOLUTION_S_DEFAULT,
    now_iso: Optional[str] = None,
    now_ts_ms: Optional[int] = None,
) -> dict[str, Any]:
    """單輪 vol-surface PIT snapshot：逐幣抓 DVOL + book_summary，構造衍生視圖。

    回 {"dvol_rows", "surface_rows", "term_structure_rows", "skew_rows",
        "raw_instruments", "stats", "errors"}；單幣 / 單面失敗不連累其他
    （fail-soft，error 入 stats，mirror polymarket_axis collect_snapshot_sweep）。
    """
    now = now_iso or _utc_now_iso()
    end_ms = now_ts_ms if now_ts_ms is not None else int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)
    start_ms = end_ms - int(dvol_window_s) * 1000

    dvol_rows: list[dict[str, Any]] = []
    surface_rows: list[dict[str, Any]] = []
    term_rows: list[dict[str, Any]] = []
    skew_rows: list[dict[str, Any]] = []
    raw_instruments: list[dict[str, Any]] = []
    errors: list[str] = []
    per_currency: dict[str, Any] = {}

    for ccy in currencies:
        ccy_stats: dict[str, Any] = {}
        # ---- DVOL OHLC ----
        try:
            dvol_result = fetch_dvol(
                client, currency=ccy,
                start_ts_ms=start_ms, end_ts_ms=end_ms, resolution_s=dvol_resolution_s,
            )
            d_rows = flatten_dvol_rows(
                dvol_result, currency=ccy,
                snapshot_ts_utc=now, collector_git_sha=collector_git_sha,
            )
            dvol_rows.extend(d_rows)
            ccy_stats["dvol_bars"] = len(d_rows)
        except (CollectorHTTPError, ValueError) as exc:
            errors.append(f"dvol:{ccy}:{exc}")
            ccy_stats["dvol_bars"] = None

        # ---- IV surface（book_summary）+ 衍生視圖 ----
        try:
            summary = fetch_book_summary(client, currency=ccy)
            s_rows = flatten_surface_rows(
                summary, currency=ccy,
                snapshot_ts_utc=now, collector_git_sha=collector_git_sha,
            )
            surface_rows.extend(s_rows)
            raw_instruments.append({"fetched_at_utc": now, "currency": ccy, "n": len(summary), "raw": summary})
            t_rows = build_term_structure(s_rows, currency=ccy, snapshot_ts_utc=now)
            sk_rows = build_skew(s_rows, currency=ccy, snapshot_ts_utc=now)
            term_rows.extend(t_rows)
            skew_rows.extend(sk_rows)
            ccy_stats["surface_instruments"] = len(s_rows)
            ccy_stats["term_expiries"] = len(t_rows)
            ccy_stats["skew_expiries"] = len(sk_rows)
        except (CollectorHTTPError, ValueError) as exc:
            errors.append(f"surface:{ccy}:{exc}")
            ccy_stats["surface_instruments"] = None
        per_currency[ccy] = ccy_stats

    stats = {
        "currencies": list(currencies),
        "per_currency": per_currency,
        "dvol_rows": len(dvol_rows),
        "surface_rows": len(surface_rows),
        "term_structure_rows": len(term_rows),
        "skew_rows": len(skew_rows),
        "dvol_window_s": dvol_window_s,
        "dvol_resolution_s": dvol_resolution_s,
        "http_requests": client.request_count,
    }
    return {
        "dvol_rows": dvol_rows,
        "surface_rows": surface_rows,
        "term_structure_rows": term_rows,
        "skew_rows": skew_rows,
        "raw_instruments": raw_instruments,
        "stats": stats,
        "errors": errors,
    }
