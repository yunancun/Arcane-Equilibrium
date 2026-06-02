"""唯讀資料載入 — 多日 trend 診斷 harness。

MODULE_NOTE:
  模塊用途：從 PG **唯讀** SELECT 多日 trend 診斷所需資料：日線 OHLC
    (market.klines timeframe='1d')、funding (market.funding_rates)、survivorship
    (market.symbol_universe_snapshots.listed_at)、regime（market.regime_snapshots
    若空則本地 rule-based 計算）。對齊成共同日期格。
  本 runtime 實況（2026-06-02 親驗，決定 fallback）：
    - 日線：20 symbol × 730 日（POLUSDT 635），2024-06-02→2026-06-01，覆蓋完整。
    - funding：僅 ~58 天（2026-04-05→2026-06-02）→ **用 per-symbol 已實現均值**，
      harness 標 funding INCONCLUSIVE-on-coverage。
    - regime_snapshots：**完全空表** → 本地 rule-based（BTC 200日MA 上下 + realized
      vol tercile，禁 HMM，leak-free PIT），協議 §4b fallback。
    - symbol_universe_snapshots：僅 ~24 天，但 listed_at 可信（POLUSDT 2024-09-05 與
      其 635 日線起點一致）→ 用 listed_at 做 survivorship mask。
  主要函數：``load_panel`` / ``compute_rule_based_regime`` / ``representative_funding``。
  硬邊界：
    - **只 SELECT，絕不寫**。所有 query 參數化（symbol IN %s）。
    - DSN 用 lib.pg_connect.resolve_report_dsn()（OPENCLAW_DATABASE_URL 優先，
      跨平台不硬編碼 host），或 caller 傳入 dsn。
    - regime label scoring 前凍結（leak-free，協議 §4b）。
  依賴：psycopg2（延遲 import）+ numpy。import-time 零 DB 依賴。
"""

from __future__ import annotations

import datetime as dt
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

# 協議 §0 的 20 liquid perp（與 backfill_universe / 日線覆蓋一致）。
DEFAULT_UNIVERSE = (
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT",
    "AVAXUSDT", "DOTUSDT", "LINKUSDT", "LTCUSDT", "TRXUSDT", "BCHUSDT", "NEARUSDT",
    "APTUSDT", "ARBUSDT", "OPUSDT", "SUIUSDT", "TONUSDT", "POLUSDT",
)
BTC_SYMBOL = "BTCUSDT"

# rule-based regime 參數（協議 §4b，禁 HMM）。
REGIME_TREND_MA_DAYS = 200  # BTC 200 日 MA（leak-free：用 shift(1)）
REGIME_VOL_WINDOW = 30  # realized vol 視窗


@dataclass
class Panel:
    """對齊後的多日面板。

    dates: 共同日期序列（升序，datetime.date）。
    close/open_/high/low/volume: {symbol: ndarray[T]}（缺日為 NaN）。
    survivorship: {symbol: ndarray[T] bool}（True=該日已上市可交易）。
    regime: ndarray[T] of str（'bull'/'bear'/'chop'，由 BTC 計，全 symbol 共用市場 regime）。
    funding_mean_per_8h: {symbol: float}（已實現 funding 代表性均值，分數）。
    coverage_notes: 資料覆蓋誠實標記。
    """

    dates: list
    close: dict
    open_: dict
    high: dict
    low: dict
    volume: dict
    survivorship: dict
    regime: np.ndarray
    funding_mean_per_8h: dict
    coverage_notes: dict = field(default_factory=dict)


def _connect(dsn: Optional[str], application_name: str):
    """連 PG（唯讀）。優先 caller dsn，否則用共享 lib.pg_connect 解析。"""
    import psycopg2  # 延遲 import

    if dsn is None:
        # 復用 helper_scripts/lib/pg_connect.resolve_report_dsn（跨平台、不硬編碼 host）。
        srv_root = Path(__file__).resolve().parents[3]  # .../srv
        lib_dir = srv_root / "helper_scripts"
        if str(lib_dir) not in sys.path:
            sys.path.insert(0, str(lib_dir))
        try:
            from lib.pg_connect import resolve_report_dsn  # type: ignore
            dsn = resolve_report_dsn()
        except Exception:
            dsn = os.environ.get("OPENCLAW_DATABASE_URL", "")
    conn = psycopg2.connect(dsn, application_name=application_name)
    conn.set_session(readonly=True)  # 強制唯讀 session（fail-closed 防誤寫）
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = %s", (180000,))
    return conn


def load_panel(
    universe: tuple = DEFAULT_UNIVERSE,
    *,
    dsn: Optional[str] = None,
    timeframe: str = "1d",
) -> Panel:
    """載入並對齊多日面板（唯讀）。"""
    conn = _connect(dsn, "multiday_trend_diagnostic")
    try:
        klines = _load_klines(conn, universe, timeframe)
        listed = _load_listed_at(conn, universe)
        funding = _load_funding_means(conn, universe)
        funding_cov = _load_funding_coverage(conn, universe)
        kline_cov = _kline_coverage(klines)
    finally:
        conn.close()

    # 建共同日期軸（所有 symbol 日期聯集，升序）。
    all_dates = set()
    for sym, rows in klines.items():
        for d, *_ in rows:
            all_dates.add(d)
    dates = sorted(all_dates)
    didx = {d: i for i, d in enumerate(dates)}
    t = len(dates)

    close = {s: np.full(t, np.nan) for s in universe}
    open_ = {s: np.full(t, np.nan) for s in universe}
    high = {s: np.full(t, np.nan) for s in universe}
    low = {s: np.full(t, np.nan) for s in universe}
    volume = {s: np.full(t, np.nan) for s in universe}
    survivorship = {s: np.zeros(t, dtype=bool) for s in universe}

    for s in universe:
        for d, o, h, lo, c, v in klines.get(s, []):
            i = didx[d]
            open_[s][i] = o
            high[s][i] = h
            low[s][i] = lo
            close[s][i] = c
            volume[s][i] = v if v is not None else np.nan
        # survivorship：listed_at 之後（含當日）才可交易。listed_at 缺 → 用首個有 kline 的日。
        la = listed.get(s)
        for i, d in enumerate(dates):
            if la is not None:
                survivorship[s][i] = d >= la
            else:
                survivorship[s][i] = np.isfinite(close[s][i])

    regime = compute_rule_based_regime(close.get(BTC_SYMBOL), dates)

    coverage_notes = {
        "kline_coverage": kline_cov,
        "funding_coverage": funding_cov,
        "regime_source": "rule_based_local_btc_200dma_vol_tercile (regime_snapshots empty)",
        "survivorship_source": "symbol_universe_snapshots.listed_at",
        "funding_window_vs_signal_window": (
            "funding covers only recent window; mean-per-8h applied across full "
            "730d signal window -> funding is INCONCLUSIVE-on-coverage"
        ),
    }
    return Panel(
        dates=dates, close=close, open_=open_, high=high, low=low, volume=volume,
        survivorship=survivorship, regime=regime, funding_mean_per_8h=funding,
        coverage_notes=coverage_notes,
    )


def _load_klines(conn, universe, timeframe):
    """唯讀 SELECT 日線 OHLC。回 {symbol: [(date, open, high, low, close, volume), ...]}。"""
    out: dict = {s: [] for s in universe}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT symbol, ts::date AS d, open, high, low, close, volume
            FROM market.klines
            WHERE timeframe = %s AND symbol = ANY(%s)
            ORDER BY symbol, ts
            """,
            (timeframe, list(universe)),
        )
        for symbol, d, o, h, lo, c, v in cur.fetchall():
            out.setdefault(symbol, []).append((d, float(o), float(h), float(lo), float(c),
                                               float(v) if v is not None else None))
    return out


def _load_listed_at(conn, universe):
    """唯讀 SELECT 各 symbol 最新 snapshot 的 listed_at（survivorship 用）。回 {symbol: date|None}。"""
    out: dict = {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (symbol) symbol, listed_at::date
            FROM market.symbol_universe_snapshots
            WHERE symbol = ANY(%s)
            ORDER BY symbol, ts DESC
            """,
            (list(universe),),
        )
        for symbol, la in cur.fetchall():
            out[symbol] = la
    return out


def _load_funding_means(conn, universe):
    """唯讀 SELECT per-symbol 已實現 funding 均值（per 8h，分數）。回 {symbol: mean_rate}。

    協議 §3：F_settlement 取已實現 history（NOT cap 反推）。因覆蓋僅 ~58 天，用均值近似
    全窗（harness 標 INCONCLUSIVE-on-coverage）。
    """
    out: dict = {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT symbol, avg(funding_rate)::double precision AS mean_rate
            FROM market.funding_rates
            WHERE symbol = ANY(%s)
            GROUP BY symbol
            """,
            (list(universe),),
        )
        for symbol, mr in cur.fetchall():
            out[symbol] = float(mr) if mr is not None else 0.0
    # 缺 funding 的 symbol → 用全 universe 中位數代表性近似（標記）。
    present = [v for v in out.values() if v is not None]
    fallback = float(np.median(present)) if present else 0.0
    for s in universe:
        if s not in out:
            out[s] = fallback
    return out


def _load_funding_coverage(conn, universe):
    """唯讀 SELECT funding 覆蓋誠實標記（per-symbol count + span）。"""
    cov: dict = {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT symbol, count(*) n, min(ts)::date mn, max(ts)::date mx
            FROM market.funding_rates
            WHERE symbol = ANY(%s)
            GROUP BY symbol
            """,
            (list(universe),),
        )
        for symbol, n, mn, mx in cur.fetchall():
            cov[symbol] = {"n": int(n), "min": str(mn), "max": str(mx)}
    return cov


def _kline_coverage(klines):
    out = {}
    for s, rows in klines.items():
        if rows:
            out[s] = {"n": len(rows), "min": str(rows[0][0]), "max": str(rows[-1][0])}
        else:
            out[s] = {"n": 0, "min": None, "max": None}
    return out


def compute_rule_based_regime(btc_close: Optional[np.ndarray], dates: list) -> np.ndarray:
    """本地 rule-based regime（協議 §4b，禁 HMM，leak-free PIT）。

    規則（leak-free：全用 shift(1) 收盤，不含當日）：
      - BTC 收盤 > 200 日 MA 且 realized vol 非高檔 tercile → 'bull'
      - BTC 收盤 < 200 日 MA → 'bear'
      - 其餘（橫盤 / 高 vol 不明確）→ 'chop'
    為什麼 BTC 驅動全市場 regime：crypto 高相關，BTC 是市場 beta 主軸（協議 §4.6 PC1）。
    warmup（前 200 日）未滿 → 'chop'（保守，不偽造方向）。
    """
    t = len(dates)
    out = np.array(["chop"] * t, dtype=object)
    if btc_close is None or t < REGIME_TREND_MA_DAYS + 2:
        return out
    # leak-free：prev_close[i] = btc_close[i-1]。
    prev = np.full(t, np.nan)
    prev[1:] = btc_close[:-1]
    # 200 日 MA（用 prev，含到 i-1）。
    for i in range(t):
        lo = i - REGIME_TREND_MA_DAYS + 1
        if lo < 0:
            continue
        seg = prev[lo: i + 1]
        if np.any(~np.isfinite(seg)):
            continue
        ma = float(seg.mean())
        # realized vol（過去 30 日 prev 報酬 std）。
        vlo = i - REGIME_VOL_WINDOW
        vol = np.nan
        if vlo >= 1:
            r = np.diff(np.log(prev[vlo: i + 1])) if np.all(np.isfinite(prev[vlo: i + 1]) & (prev[vlo: i + 1] > 0)) else None
            if r is not None and len(r) > 1:
                vol = float(np.std(r, ddof=1))
        c = prev[i]
        if not np.isfinite(c) or not np.isfinite(ma):
            continue
        if c > ma:
            out[i] = "bull"
        else:
            out[i] = "bear"
    # vol tercile 細分：高 vol 時 bull/bear 降級為 chop（高不確定 → 保守）。
    vols = _rolling_vol_series(btc_close)
    finite_vols = vols[np.isfinite(vols)]
    if len(finite_vols) > 10:
        hi_thr = np.quantile(finite_vols, 2.0 / 3.0)
        for i in range(t):
            if np.isfinite(vols[i]) and vols[i] >= hi_thr:
                out[i] = "chop"
    return out


def _rolling_vol_series(btc_close: np.ndarray) -> np.ndarray:
    t = len(btc_close)
    out = np.full(t, np.nan)
    prev = np.full(t, np.nan)
    prev[1:] = btc_close[:-1]
    for i in range(t):
        vlo = i - REGIME_VOL_WINDOW
        if vlo < 1:
            continue
        seg = prev[vlo: i + 1]
        if np.any(~np.isfinite(seg)) or np.any(seg <= 0):
            continue
        r = np.diff(np.log(seg))
        if len(r) > 1:
            out[i] = float(np.std(r, ddof=1))
    return out


def cross_sectional_median_daily_vol(panel: Panel) -> float:
    """σ_target = 樣本期 cross-sectional median daily vol（協議 §1 信號 B，不 sweep）。"""
    vols = []
    for s, c in panel.close.items():
        cc = c[np.isfinite(c) & (c > 0)]
        if len(cc) > 30:
            r = np.diff(np.log(cc))
            if len(r) > 2:
                vols.append(float(np.std(r, ddof=1)))
    return float(np.median(vols)) if vols else 0.02
