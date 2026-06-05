from __future__ import annotations

"""
Layer 2 Toolbox Extension — G3-08 (2026-06-05)
Layer 2 工具箱擴充 —— G3-08（2026-06-05）

MODULE_NOTE (中文):
  本模組提供 Layer 2 推理迴圈三個微結構（microstructure）工具的純實作：
    - get_orderbook      — Bybit V5 公開 orderbook（外部 HTTP，預設關閉）
    - get_cvd            — 本地 PG market.trade_agg_1m 滾動買賣量差（CVD，預設開啟）
    - get_liquidations   — 本地 PG market.liquidations 視窗統計（預設開啟）

  為什麼分檔（不寫進 layer2_tools.py）：沿用 G3-07 的 sibling 範式——
    schema entries / handler dict 註冊留在 layer2_tools.py（caller surface），
    本 sibling 只負責「fetch 與解析」純函式 + dict 序列化，讓 layer2_tools.py
    遠低於 2000 行硬上限。

  資料來源邊界（PA 已驗，硬約束）：
    - CVD 不在 Rust 記憶體；只能讀 PG 表 market.trade_agg_1m（buy_volume /
      sell_volume / symbol / ts），Python 端做滾動加總，不動 Rust。
    - 強平資料：Bybit 沒有公開 liquidation 端點；只能讀我們自己的 PG
      hypertable market.liquidations（ts / symbol / side / qty / price），
      絕不為 liq 呼叫 Bybit。
    - orderbook 是唯一外部來源（Bybit V5 公開端點，無需簽名），預設關閉。

  硬邊界：
    - 三工具一律 READ-ONLY：只 SELECT / 外部 GET，絕無 INSERT/UPDATE/DELETE、
      不下單、不碰 lease / authorization。
    - 任何 transport / non-200 / parse / PG 失敗 → 回帶 "error" key 的 dict，
      *絕不 raise* —— 防止 L2 推理鏈被工具層異常中斷（fail-closed）。
    - 零筆資料是合法狀態（error=None + 數值為 0），不視為錯誤。
    - 共用 env-gate / HTTP 設定沿用 G3-07 sibling 的 helper（is_tool_enabled /
      http_timeout / bybit_public_base_url），避免重複定義漂移。
"""

import logging
import time
from typing import Any

from .layer2_types import (
    ENV_L2_TOOL_CVD_ENABLED,
    ENV_L2_TOOL_LIQUIDATIONS_ENABLED,
    ENV_L2_TOOL_ORDERBOOK_ENABLED,
)
# 沿用 G3-07 sibling 的共用 helper：env-gate 判斷 / HTTP 超時 / Bybit 公開 base URL。
# 為什麼複用而非重寫：truthy 語意與 base-URL 解析（含 file-based fallback）必須與
# G3-07 完全一致，避免兩套工具行為分歧。
from .layer2_tools_g3_07 import (
    DEFAULT_TOOL_DISABLED_ERROR,
    bybit_public_base_url,
    http_timeout,
    is_tool_enabled,
)
from . import db_pool

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
# 預設值 / 範圍限制（fail-closed clamp）
# ─────────────────────────────────────────────────────────

DEFAULT_ORDERBOOK_DEPTH = 5
MIN_ORDERBOOK_DEPTH = 1
MAX_ORDERBOOK_DEPTH = 25

DEFAULT_CVD_WINDOW_BARS = 20
MIN_CVD_WINDOW_BARS = 1
MAX_CVD_WINDOW_BARS = 60

DEFAULT_LIQ_WINDOW_MINUTES = 15
MIN_LIQ_WINDOW_MINUTES = 1
MAX_LIQ_WINDOW_MINUTES = 60

DEFAULT_DATA_UNAVAILABLE_ERROR = "data unavailable"


def _clamp_int(raw: Any, lo: int, hi: int, default: int) -> int:
    """
    把使用者參數收斂到 [lo, hi]；非整數或缺值回 default。
    為什麼：LLM 產生的 arg 可能是字串 / 浮點 / 超界值，工具層必須先收斂，
    避免把垃圾值帶進 SQL LIMIT 或 HTTP 參數。
    """
    if raw is None:
        return default
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return default
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


# ─────────────────────────────────────────────────────────
# get_orderbook — 外部 Bybit V5 公開 orderbook，預設關閉，fail-closed
# ─────────────────────────────────────────────────────────

async def get_orderbook(args: dict[str, Any]) -> dict[str, Any]:
    """
    取得 symbol 的 Bybit V5 公開 orderbook 快照（top-N 檔）。
    Fetch a Bybit V5 public orderbook snapshot (top-N levels) for a symbol.

    為什麼預設關閉：唯一走外部網路（Bybit）的微結構工具；依 fail-closed 預設，
    需設 OPENCLAW_L2_TOOL_ORDERBOOK_ENABLED=1 才啟用。Bybit V5 orderbook 為
    公開端點（無需簽名），demo / testnet / mainnet 皆安全。

    回傳欄位：
      {symbol, bids, asks, ts_ms, bid_ask_spread_bps, bid_imbalance_ratio, error}
      - bids / asks: [[price, qty], ...]（價格由內向外排序，Bybit 原樣）
      - bid_ask_spread_bps: (best_ask - best_bid) / mid * 10000
      - bid_imbalance_ratio: sum(bid_qty) / (sum(bid_qty)+sum(ask_qty))，top-N

    Fail-closed 契約：
      - env-disabled  → {error:"tool disabled by env", ...zeros}
      - missing symbol→ {error:"symbol is required", ...}
      - HTTP/parse err→ {error:"data unavailable: ...", ...}
    """
    symbol = (args.get("symbol") or "").strip()

    # 先檢查 env-gate（即使 args 缺失也統一回 disabled，避免關閉時洩漏輸入回顯）。
    if not is_tool_enabled(ENV_L2_TOOL_ORDERBOOK_ENABLED):
        return _orderbook_result(symbol, error=DEFAULT_TOOL_DISABLED_ERROR)

    if not symbol:
        return _orderbook_result(symbol, error="symbol is required")

    depth = _clamp_int(
        args.get("limit"),
        MIN_ORDERBOOK_DEPTH,
        MAX_ORDERBOOK_DEPTH,
        DEFAULT_ORDERBOOK_DEPTH,
    )
    return await _fetch_orderbook(symbol, depth)


def _orderbook_result(
    symbol: str,
    *,
    bids: list[list[float]] | None = None,
    asks: list[list[float]] | None = None,
    ts_ms: int | None = None,
    bid_ask_spread_bps: float | None = None,
    bid_imbalance_ratio: float | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """orderbook 工具統一回傳 shape（JSON 安全）。"""
    return {
        "symbol": symbol,
        "bids": bids if bids is not None else [],
        "asks": asks if asks is not None else [],
        "ts_ms": ts_ms,
        "bid_ask_spread_bps": bid_ask_spread_bps,
        "bid_imbalance_ratio": bid_imbalance_ratio,
        "error": error,
    }


async def _fetch_orderbook(symbol: str, depth: int) -> dict[str, Any]:
    """
    HTTP 取 Bybit V5 orderbook 並解析。純 helper（patch httpx 即可單測）。
    Bybit V5: GET /v5/market/orderbook?category=linear&symbol=&limit=
    回傳信封 result.b（bids）/ result.a（asks）/ result.ts（ms）。
    """
    try:
        import httpx
    except ImportError:
        return _orderbook_result(symbol, error="httpx not installed")

    base = bybit_public_base_url()
    timeout = http_timeout()
    url = f"{base}/v5/market/orderbook"
    params = {"category": "linear", "symbol": symbol, "limit": depth}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return _orderbook_result(
                    symbol,
                    error=f"{DEFAULT_DATA_UNAVAILABLE_ERROR}: HTTP {resp.status_code}",
                )
            data = resp.json()
    except Exception as e:
        return _orderbook_result(
            symbol,
            error=f"{DEFAULT_DATA_UNAVAILABLE_ERROR}: {str(e)[:200]}",
        )

    if not isinstance(data, dict) or data.get("retCode") != 0:
        ret_msg = data.get("retMsg", "unknown") if isinstance(data, dict) else "non-dict"
        return _orderbook_result(
            symbol,
            error=f"{DEFAULT_DATA_UNAVAILABLE_ERROR}: retCode!=0 ({ret_msg})",
        )

    result = data.get("result") if isinstance(data.get("result"), dict) else {}
    raw_bids = result.get("b") or []
    raw_asks = result.get("a") or []

    bids = _parse_levels(raw_bids)
    asks = _parse_levels(raw_asks)

    if not bids or not asks:
        return _orderbook_result(
            symbol,
            bids=bids,
            asks=asks,
            error=f"{DEFAULT_DATA_UNAVAILABLE_ERROR}: empty orderbook side",
        )

    # ts（毫秒）：優先 result.ts，再 data.time。
    ts_ms: int | None = None
    for ts_raw in (result.get("ts"), data.get("time")):
        if ts_raw:
            try:
                ts_ms = int(ts_raw)
                break
            except (TypeError, ValueError):
                continue

    best_bid = bids[0][0]
    best_ask = asks[0][0]
    spread_bps: float | None = None
    mid = (best_bid + best_ask) / 2.0
    if mid > 0:
        spread_bps = round((best_ask - best_bid) / mid * 10000.0, 4)

    sum_bid_qty = sum(level[1] for level in bids)
    sum_ask_qty = sum(level[1] for level in asks)
    denom = sum_bid_qty + sum_ask_qty
    imbalance: float | None = round(sum_bid_qty / denom, 6) if denom > 0 else None

    return _orderbook_result(
        symbol,
        bids=bids,
        asks=asks,
        ts_ms=ts_ms,
        bid_ask_spread_bps=spread_bps,
        bid_imbalance_ratio=imbalance,
    )


def _parse_levels(raw: Any) -> list[list[float]]:
    """
    把 Bybit orderbook 的 [["price","qty"], ...] 解析為 [[float, float], ...]。
    非數值 / 結構異常的 level 直接略過（fail-soft），不 raise。
    """
    out: list[list[float]] = []
    if not isinstance(raw, list):
        return out
    for level in raw:
        if not isinstance(level, (list, tuple)) or len(level) < 2:
            continue
        try:
            price = float(level[0])
            qty = float(level[1])
        except (TypeError, ValueError):
            continue
        out.append([price, qty])
    return out


# ─────────────────────────────────────────────────────────
# get_cvd — 本地 PG market.trade_agg_1m 滾動買賣量差，預設開啟，fail-closed
# ─────────────────────────────────────────────────────────

async def get_cvd(args: dict[str, Any]) -> dict[str, Any]:
    """
    取 symbol 最近 N 根 1 分鐘 bar 的累積成交量差（CVD = buy_volume - sell_volume）。
    Cumulative volume delta over the last N 1-minute bars from our own PG.

    為什麼讀 PG 而非 Bybit：CVD 不在 Rust 記憶體；Bybit 公開端點也無此聚合。
    我們自己的 market.trade_agg_1m 已按分鐘聚合 buy_volume / sell_volume，
    直接 SQL 加總即得 CVD，免費且唯讀。預設開啟（OPENCLAW_L2_TOOL_CVD_ENABLED
    未設時亦視為開啟，因免費本地讀取）。

    Args：symbol（必填）、window_bars（1-60，預設 20）。
    回傳：{symbol, cvd, buy_volume, sell_volume, bars, oldest_bar_ts,
           freshness_secs, error}
      - cvd = buy_volume - sell_volume（視窗加總）
      - bars = 實際命中的 bar 數（可能少於 window_bars）
      - 零筆 = 合法（error=None，數值皆 0，bars=0）
    """
    symbol = (args.get("symbol") or "").strip()

    # CVD 預設開啟：只有顯式關閉（旗標設成 falsy 以外的值才開）—— 與 orderbook
    # 不同，這裡免費且唯讀，故未設旗標時也放行；只有把旗標明確設為 falsy 才關。
    if _tool_disabled_when_default_on(ENV_L2_TOOL_CVD_ENABLED):
        return _cvd_result(symbol, error=DEFAULT_TOOL_DISABLED_ERROR)

    if not symbol:
        return _cvd_result(symbol, error="symbol is required")

    window_bars = _clamp_int(
        args.get("window_bars"),
        MIN_CVD_WINDOW_BARS,
        MAX_CVD_WINDOW_BARS,
        DEFAULT_CVD_WINDOW_BARS,
    )
    # 同步 PG 讀取包進 thread，避免阻塞事件迴圈。
    return await _to_thread(_fetch_cvd_sync, symbol, window_bars)


def _cvd_result(
    symbol: str,
    *,
    cvd: float = 0.0,
    buy_volume: float = 0.0,
    sell_volume: float = 0.0,
    bars: int = 0,
    oldest_bar_ts: str | None = None,
    freshness_secs: int | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """CVD 工具統一回傳 shape。"""
    return {
        "symbol": symbol,
        "cvd": cvd,
        "buy_volume": buy_volume,
        "sell_volume": sell_volume,
        "bars": bars,
        "oldest_bar_ts": oldest_bar_ts,
        "freshness_secs": freshness_secs,
        "error": error,
    }


def _fetch_cvd_sync(symbol: str, window_bars: int) -> dict[str, Any]:
    """
    同步 PG 讀取 + 聚合 CVD。純 helper（DB 不可用回 error dict，不 raise）。

    SQL：取最近 window_bars 根 bar（ts DESC LIMIT N），對其 buy_volume /
    sell_volume 加總。參數化查詢（symbol / limit 皆綁定參數）。
    """
    with db_pool.get_pg_conn() as conn:
        if conn is None:
            return _cvd_result(
                symbol,
                error=f"{DEFAULT_DATA_UNAVAILABLE_ERROR}: PG unavailable",
            )
        try:
            cur = conn.cursor()
            # 先取視窗內逐 bar，再於 Python 端加總；同時拿 oldest bar ts 與
            # newest bar ts（算 freshness）。LIMIT 綁定參數防注入。
            cur.execute(
                """
                SELECT ts,
                       COALESCE(buy_volume, 0)  AS buy_volume,
                       COALESCE(sell_volume, 0) AS sell_volume
                FROM market.trade_agg_1m
                WHERE symbol = %s
                ORDER BY ts DESC
                LIMIT %s
                """,
                (symbol, window_bars),
            )
            rows = cur.fetchall()
        except Exception as e:
            return _cvd_result(
                symbol,
                error=f"{DEFAULT_DATA_UNAVAILABLE_ERROR}: {str(e)[:200]}",
            )

    # 零筆是合法狀態（該 symbol 近期無聚合成交）：回 0 值、error=None。
    if not rows:
        return _cvd_result(symbol, bars=0)

    total_buy = 0.0
    total_sell = 0.0
    # rows 按 ts DESC：第 0 筆最新，最後一筆最舊。
    for _ts, buy_v, sell_v in rows:
        total_buy += float(buy_v or 0.0)
        total_sell += float(sell_v or 0.0)

    newest_ts = rows[0][0]
    oldest_ts = rows[-1][0]
    freshness_secs = _freshness_secs_from_ts(newest_ts)

    return _cvd_result(
        symbol,
        cvd=round(total_buy - total_sell, 6),
        buy_volume=round(total_buy, 6),
        sell_volume=round(total_sell, 6),
        bars=len(rows),
        oldest_bar_ts=_iso_or_none(oldest_ts),
        freshness_secs=freshness_secs,
    )


# ─────────────────────────────────────────────────────────
# get_liquidations — 本地 PG market.liquidations 視窗統計，預設開啟，fail-closed
# ─────────────────────────────────────────────────────────

async def get_liquidations(args: dict[str, Any]) -> dict[str, Any]:
    """
    取 symbol 最近 window_minutes 分鐘的強平統計（依 side 分組）。
    Liquidation stats over the last window_minutes, grouped by side, from our PG.

    為什麼讀 PG 而非 Bybit：Bybit 無公開 liquidation 端點；我們自己的
    market.liquidations hypertable（ts / symbol / side / qty / price）是唯一來源。
    免費唯讀，預設開啟（OPENCLAW_L2_TOOL_LIQUIDATIONS_ENABLED 未設亦開）。

    Args：symbol（必填）、window_minutes（1-60，預設 15）。
    回傳：{symbol, window_minutes, buy_liq_qty, sell_liq_qty, buy_liq_count,
           sell_liq_count, net_liq_qty, largest_single_qty, oldest_event_ts,
           freshness_secs, error}
      - side 依 Bybit 慣例為 'Buy'/'Sell'（被清算方向）
      - net_liq_qty = buy_liq_qty - sell_liq_qty
      - 零筆 = 合法（error=None，數值皆 0 / count=0）
    """
    symbol = (args.get("symbol") or "").strip()

    if _tool_disabled_when_default_on(ENV_L2_TOOL_LIQUIDATIONS_ENABLED):
        return _liq_result(symbol, 0, error=DEFAULT_TOOL_DISABLED_ERROR)

    window_minutes = _clamp_int(
        args.get("window_minutes"),
        MIN_LIQ_WINDOW_MINUTES,
        MAX_LIQ_WINDOW_MINUTES,
        DEFAULT_LIQ_WINDOW_MINUTES,
    )

    if not symbol:
        return _liq_result(symbol, window_minutes, error="symbol is required")

    return await _to_thread(_fetch_liquidations_sync, symbol, window_minutes)


def _liq_result(
    symbol: str,
    window_minutes: int,
    *,
    buy_liq_qty: float = 0.0,
    sell_liq_qty: float = 0.0,
    buy_liq_count: int = 0,
    sell_liq_count: int = 0,
    net_liq_qty: float = 0.0,
    largest_single_qty: float = 0.0,
    oldest_event_ts: str | None = None,
    freshness_secs: int | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """liquidations 工具統一回傳 shape。"""
    return {
        "symbol": symbol,
        "window_minutes": window_minutes,
        "buy_liq_qty": buy_liq_qty,
        "sell_liq_qty": sell_liq_qty,
        "buy_liq_count": buy_liq_count,
        "sell_liq_count": sell_liq_count,
        "net_liq_qty": net_liq_qty,
        "largest_single_qty": largest_single_qty,
        "oldest_event_ts": oldest_event_ts,
        "freshness_secs": freshness_secs,
        "error": error,
    }


def _fetch_liquidations_sync(symbol: str, window_minutes: int) -> dict[str, Any]:
    """
    同步 PG 讀取 + 依 side 聚合強平。純 helper（DB 不可用回 error dict，不 raise）。

    SQL：以 ts >= now() - interval 視窗過濾，依 side 分組取 sum(qty) / count /
    max(qty)，並取整體 oldest ts 與 newest ts。window_minutes 以整數秒綁定參數
    （make_interval），避免字串拼接注入。
    """
    with db_pool.get_pg_conn() as conn:
        if conn is None:
            return _liq_result(
                symbol,
                window_minutes,
                error=f"{DEFAULT_DATA_UNAVAILABLE_ERROR}: PG unavailable",
            )
        try:
            cur = conn.cursor()
            # 用 make_interval(secs => %s) 綁定視窗秒數（純參數，無字串拼接）。
            cur.execute(
                """
                SELECT side,
                       COALESCE(SUM(qty), 0) AS sum_qty,
                       COUNT(*)              AS cnt,
                       COALESCE(MAX(qty), 0) AS max_qty,
                       MIN(ts)               AS oldest_ts,
                       MAX(ts)               AS newest_ts
                FROM market.liquidations
                WHERE symbol = %s
                  AND ts >= NOW() - make_interval(secs => %s)
                GROUP BY side
                """,
                (symbol, window_minutes * 60),
            )
            rows = cur.fetchall()
        except Exception as e:
            return _liq_result(
                symbol,
                window_minutes,
                error=f"{DEFAULT_DATA_UNAVAILABLE_ERROR}: {str(e)[:200]}",
            )

    # 零筆是合法狀態（視窗內無強平）：回 0 值、error=None。
    if not rows:
        return _liq_result(symbol, window_minutes)

    buy_qty = 0.0
    sell_qty = 0.0
    buy_cnt = 0
    sell_cnt = 0
    largest = 0.0
    oldest_ts = None
    newest_ts = None

    for side, sum_qty, cnt, max_qty, row_oldest, row_newest in rows:
        # .lower() 是 load-bearing，勿在「清理」時拿掉：production market.liquidations.side
        # 是 Bybit V5 首字母大寫的 "Buy"/"Sell"，下面 == "buy"/"sell" 比對依賴此正規化；
        # 移除 .lower() 會讓全部歷史/現役列落到 else 分支，買賣量恆為 0。
        side_norm = (side or "").strip().lower()
        q = float(sum_qty or 0.0)
        c = int(cnt or 0)
        if side_norm == "buy":
            buy_qty += q
            buy_cnt += c
        elif side_norm == "sell":
            sell_qty += q
            sell_cnt += c
        else:
            # 未知 side —— 不歸入買賣，但仍計入 largest / freshness，避免靜默吞掉資料。
            # 為什麼仍要防禦：V002 建表時 side 僅 TEXT NOT NULL（無 CHECK）；V095 才
            # 補上 CHECK (side IN ('Buy','Sell'))，但該約束是 NOT VALID，不回溯校驗
            # 既有列，故 V095 之前寫入的歷史列仍可能出現非 Buy/Sell（含大小寫變體）。
            logger.debug("get_liquidations: unexpected side %r for %s", side, symbol)
        largest = max(largest, float(max_qty or 0.0))
        oldest_ts = _min_ts(oldest_ts, row_oldest)
        newest_ts = _max_ts(newest_ts, row_newest)

    return _liq_result(
        symbol,
        window_minutes,
        buy_liq_qty=round(buy_qty, 6),
        sell_liq_qty=round(sell_qty, 6),
        buy_liq_count=buy_cnt,
        sell_liq_count=sell_cnt,
        net_liq_qty=round(buy_qty - sell_qty, 6),
        largest_single_qty=round(largest, 6),
        oldest_event_ts=_iso_or_none(oldest_ts),
        freshness_secs=_freshness_secs_from_ts(newest_ts),
    )


# ─────────────────────────────────────────────────────────
# 共用小工具 / shared helpers
# ─────────────────────────────────────────────────────────

def _tool_disabled_when_default_on(env_name: str) -> bool:
    """
    預設開啟的工具：判斷是否被「顯式關閉」。
    為什麼與 is_tool_enabled 相反：CVD / liquidations 讀本地 PG，免費唯讀，
    故未設旗標時放行；只有當 operator 明確把旗標設為 falsy（"0"/"false"/
    "no"/"off"）才關閉。未設 / 空字串 → 視為開啟。
    """
    import os
    raw = os.getenv(env_name)
    if raw is None:
        return False  # 未設 → 開啟（不關閉）
    norm = raw.strip().lower()
    if norm == "":
        return False  # 空字串 → 開啟
    return norm in ("0", "false", "no", "off")


async def _to_thread(fn, *fn_args):
    """把同步函式丟到 thread 執行（沿用標準 asyncio.to_thread）。"""
    import asyncio
    return await asyncio.to_thread(fn, *fn_args)


def _iso_or_none(ts: Any) -> str | None:
    """把 timestamptz（datetime）轉 ISO 字串；None / 異常回 None。"""
    if ts is None:
        return None
    try:
        return ts.isoformat()
    except (AttributeError, ValueError):
        try:
            return str(ts)
        except Exception:
            return None


def _freshness_secs_from_ts(ts: Any) -> int | None:
    """
    依最新事件時戳算 freshness 秒數（now - ts）。
    ts 為 None 或無法取 epoch → 回 None；負值（時鐘偏移）夾為 0。
    """
    if ts is None:
        return None
    try:
        epoch = ts.timestamp()
    except (AttributeError, ValueError, OverflowError):
        return None
    delta = time.time() - epoch
    if delta < 0:
        return 0
    return int(delta)


def _min_ts(current: Any, candidate: Any) -> Any:
    """取兩個時戳的較早者（None-safe）。"""
    if candidate is None:
        return current
    if current is None:
        return candidate
    return current if current <= candidate else candidate


def _max_ts(current: Any, candidate: Any) -> Any:
    """取兩個時戳的較晚者（None-safe）。"""
    if candidate is None:
        return current
    if current is None:
        return candidate
    return current if current >= candidate else candidate


__all__ = [
    "DEFAULT_ORDERBOOK_DEPTH",
    "MIN_ORDERBOOK_DEPTH",
    "MAX_ORDERBOOK_DEPTH",
    "DEFAULT_CVD_WINDOW_BARS",
    "MIN_CVD_WINDOW_BARS",
    "MAX_CVD_WINDOW_BARS",
    "DEFAULT_LIQ_WINDOW_MINUTES",
    "MIN_LIQ_WINDOW_MINUTES",
    "MAX_LIQ_WINDOW_MINUTES",
    "DEFAULT_DATA_UNAVAILABLE_ERROR",
    "get_orderbook",
    "get_cvd",
    "get_liquidations",
]
