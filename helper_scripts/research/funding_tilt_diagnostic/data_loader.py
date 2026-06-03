"""唯讀資料載入 — funding-tilt 診斷 harness。

MODULE_NOTE:
  模塊用途：從 PG **唯讀** SELECT funding-tilt 診斷所需資料：
    - canonical run-versioned funding（``research.alpha_funding_rates_history``，
      **固定 canonical run_id 只讀它**，協議 §2.5 禁跨 run 混讀）。
    - 日線 OHLC（``market.klines`` timeframe='1d'，open-to-open 執行價，協議 §2.4）。
    - survivorship（``market.symbol_universe_snapshots.listed_at``，協議 §2.3）。
  本 runtime 實況（MIT cheap pre-check 2026-06-03 親驗）：
    - canonical run = ``18b3c2f8-6125-42a8-a42c-cfcc8aec9406``（唯一 accepted run，
      window 2024-06-03→2026-06-03，46539 列 / 20 symbol）。
    - 18/20 symbol 精確 2190 列 / 730d = 3.0/day（8h 結算，零 gap）；TONUSDT 3701
      （4h+8h mix）、POLUSDT 3418 自 2024-09-05（上市生命全覆蓋，非 gap）。
    - **funding_interval_minutes 全 NULL**（0/46539 populated）→ 必須從 funding_ts
      相鄰間距推 interval（眾數），協議 §2.2 禁假設全 universe 8h。實測只存在 480min
      （8h，87%）+ 240min（4h，13%）兩值。TONUSDT/POLUSDT 是 4h → 7d=42 結算非 21。
  主要函數：``load_panel`` / ``infer_funding_interval_minutes`` /
    ``compute_rule_based_regime``。
  硬邊界：
    - **只 SELECT，絕不寫**。所有 query 參數化（symbol = ANY(%s)）。強制 readonly session。
    - canonical run 固定常數 ``CANONICAL_FUNDING_RUN_ID``，只讀該 run 的 funding rows。
    - cap discipline（協議紅線 2）：本 loader 只讀已實現 funding（信號用排序，不依賴
      cap）；不讀也不反推 funding cap。
    - regime label：**expanding/prior-365 vol tercile**（修 trend full-sample
      cross-section leak，協議 §1 data_loader.py:300 leak fix），leak-free PIT。
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

# 協議 §0 的 20 liquid perp（與 trend 診斷同 universe，backfill_universe.toml）。
DEFAULT_UNIVERSE = (
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT",
    "AVAXUSDT", "DOTUSDT", "LINKUSDT", "LTCUSDT", "TRXUSDT", "BCHUSDT", "NEARUSDT",
    "APTUSDT", "ARBUSDT", "OPUSDT", "SUIUSDT", "TONUSDT", "POLUSDT",
)
BTC_SYMBOL = "BTCUSDT"

# ★ canonical accepted run（協議 §2.5 + MIT cheap pre-check 親驗）。固定只讀此 run。
CANONICAL_FUNDING_RUN_ID = "18b3c2f8-6125-42a8-a42c-cfcc8aec9406"

# rule-based regime 參數（協議 §4b，禁 HMM）。
REGIME_TREND_MA_DAYS = 200  # BTC 200 日 MA（leak-free：用 prior close）
REGIME_VOL_WINDOW = 30  # realized vol 視窗
# vol-tercile leak fix：高 vol 門檻用 expanding/prior-N（不含未來），N=365（協議 §1）。
REGIME_VOL_TERCILE_PRIOR_DAYS = 365

# funding interval 推導：實測只存在 8h（480min）+ 4h（240min）。
_KNOWN_INTERVALS_MIN = (240, 480)


@dataclass
class FundingSeries:
    """單 symbol 的已實現 funding 結算序列（時序，leak-free PIT 對齊用）。

    ts: list[datetime]（UTC，升序），rate: ndarray[分數]（已實現 funding rate）。
    interval_minutes: 從相鄰間距推的眾數 interval（8h=480 / 4h=240）。
    interval_uncertain: 推導失敗或多眾數不明 → True（協議 §2.2 從 rank 排除）。
    """

    ts: list
    rate: np.ndarray
    interval_minutes: Optional[int]
    interval_uncertain: bool


@dataclass
class Panel:
    """對齊後的 funding-tilt 面板。

    dates: 共同日期序列（升序，datetime.date）。
    close/open_/high/low/volume: {symbol: ndarray[T]}（缺日為 NaN）。
    open_ts_utc: ndarray[T] of datetime（每日開盤 wall-clock，00:00 UTC，leak-free
      funding 對齊用——信號只能用 funding_ts < open_ts − ε）。
    survivorship: {symbol: ndarray[T] bool}（True=該日已上市可交易）。
    regime: ndarray[T] of str（'bull'/'bear'/'chop'，由 BTC 計，leak-free PIT）。
    funding: {symbol: FundingSeries}（已實現 funding 結算序列 + 推導 interval）。
    canonical_run_id: 所用 funding run（記錄於報告，協議 §2.5）。
    coverage_notes: 資料覆蓋誠實標記。
    """

    dates: list
    close: dict
    open_: dict
    high: dict
    low: dict
    volume: dict
    open_ts_utc: np.ndarray
    survivorship: dict
    regime: np.ndarray
    funding: dict
    canonical_run_id: str = CANONICAL_FUNDING_RUN_ID
    coverage_notes: dict = field(default_factory=dict)


def _connect(dsn: Optional[str], application_name: str):
    """連 PG（唯讀）。優先 caller dsn，否則用共享 lib.pg_connect 解析。"""
    import psycopg2  # 延遲 import

    if dsn is None:
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
    run_id: str = CANONICAL_FUNDING_RUN_ID,
) -> Panel:
    """載入並對齊 funding-tilt 面板（唯讀）。

    run_id 固定 canonical（協議 §2.5）；caller 不應改，留參數僅供測試/未來 backfill。
    """
    conn = _connect(dsn, "funding_tilt_diagnostic")
    try:
        klines = _load_klines(conn, universe, timeframe)
        listed = _load_listed_at(conn, universe)
        funding_rows = _load_funding_history(conn, universe, run_id)
        run_meta = _load_run_meta(conn, run_id)
        funding_cov = _funding_coverage(funding_rows)
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
    # 每日開盤 wall-clock（00:00 UTC）；leak-free funding 對齊以此為 entry_open_ts。
    open_ts_utc = np.array(
        [dt.datetime.combine(d, dt.time(0, 0), tzinfo=dt.timezone.utc) for d in dates],
        dtype=object,
    )

    for s in universe:
        for d, o, h, lo, c, v in klines.get(s, []):
            i = didx[d]
            open_[s][i] = o
            high[s][i] = h
            low[s][i] = lo
            close[s][i] = c
            volume[s][i] = v if v is not None else np.nan
        la = listed.get(s)
        for i, d in enumerate(dates):
            if la is not None:
                survivorship[s][i] = d >= la
            else:
                survivorship[s][i] = np.isfinite(close[s][i])

    # per-symbol funding 序列 + interval 推導（協議 §2.2）。
    funding: dict = {}
    for s in universe:
        ts_list = [ts for ts, _r in funding_rows.get(s, [])]
        rates = np.array([r for _ts, r in funding_rows.get(s, [])], dtype=float)
        interval_min, uncertain = infer_funding_interval_minutes(ts_list)
        funding[s] = FundingSeries(
            ts=ts_list, rate=rates, interval_minutes=interval_min,
            interval_uncertain=uncertain,
        )

    regime = compute_rule_based_regime(close.get(BTC_SYMBOL), dates)

    coverage_notes = {
        "kline_coverage": kline_cov,
        "funding_coverage": funding_cov,
        "canonical_run": run_meta,
        "regime_source": (
            "rule_based_local_btc_200dma_expanding_prior365_vol_tercile "
            "(regime_snapshots not used; vol-tercile leak fixed to expanding/prior-365)"
        ),
        "survivorship_source": "symbol_universe_snapshots.listed_at",
        "funding_interval_source": (
            "inferred per-symbol from funding_ts adjacent spacing (mode); "
            "funding_interval_minutes column is 100% NULL"
        ),
        "cap_discipline": (
            "signals rank realized funding only; funding cap NOT read and NOT "
            "back-inferred from history max (protocol redline 2)"
        ),
    }
    return Panel(
        dates=dates, close=close, open_=open_, high=high, low=low, volume=volume,
        open_ts_utc=open_ts_utc, survivorship=survivorship, regime=regime,
        funding=funding, canonical_run_id=run_id, coverage_notes=coverage_notes,
    )


def infer_funding_interval_minutes(ts_sorted: list) -> tuple[Optional[int], bool]:
    """從 funding_ts 相鄰間距推 interval（眾數），協議 §2.2。

    為什麼不假設 8h：funding_interval_minutes 欄 100% NULL（funding_oi_backfill.rs:611
    寫 None）。實測只存在 480min（8h）+ 240min（4h）。TONUSDT/POLUSDT 是 4h →「L 個結算」
    對應的 wall-clock 窗較短、7d=42 結算非 21，須正確換算（否則 carry 累積/break-even 錯）。
    回 (interval_minutes, uncertain)。眾數明確且為已知 interval → uncertain=False；
    間距混亂 / 樣本不足 / 眾數非已知 interval → uncertain=True（協議：從 rank 排除）。
    """
    if len(ts_sorted) < 3:
        return None, True
    diffs_min = []
    for a, b in zip(ts_sorted, ts_sorted[1:]):
        delta = (b - a).total_seconds() / 60.0
        if delta > 0:
            diffs_min.append(int(round(delta)))
    if not diffs_min:
        return None, True
    # 眾數（最常見間距）。
    vals, counts = np.unique(np.asarray(diffs_min), return_counts=True)
    mode_idx = int(np.argmax(counts))
    mode_min = int(vals[mode_idx])
    mode_share = float(counts[mode_idx]) / float(len(diffs_min))
    # 把眾數對齊到最近的已知 interval（容忍少量 240/480 mix，如 TONUSDT）。
    nearest = min(_KNOWN_INTERVALS_MIN, key=lambda k: abs(k - mode_min))
    # 眾數須足夠主導（≥50%）且接近已知 interval（±30min 容忍）才算可信。
    if mode_share >= 0.5 and abs(nearest - mode_min) <= 30:
        return nearest, False
    return mode_min, True


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


def _load_funding_history(conn, universe, run_id):
    """唯讀 SELECT canonical run 的已實現 funding 結算序列（協議 §2.5）。

    **只讀 canonical run_id**（PK 含 run_id，多 backfill run append → 禁跨 run 混讀
    重複計數）。回 {symbol: [(funding_ts_utc, rate_float), ...]}（升序）。
    """
    out: dict = {s: [] for s in universe}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT symbol, funding_ts, funding_rate
            FROM research.alpha_funding_rates_history
            WHERE run_id = %s AND symbol = ANY(%s)
            ORDER BY symbol, funding_ts
            """,
            (run_id, list(universe)),
        )
        for symbol, ts, rate in cur.fetchall():
            if rate is None:
                continue
            # 統一成 UTC-aware datetime（PG timestamptz → psycopg2 已帶 tzinfo）。
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=dt.timezone.utc)
            out.setdefault(symbol, []).append((ts, float(rate)))
    return out


def _load_run_meta(conn, run_id):
    """唯讀 SELECT canonical run 的 ingest meta（status / window / manifest_sha256）。

    報告記錄所用 run 證據（協議 §2.5）。表/欄缺失 → 回 minimal dict（不 fail-closed
    硬擋，因 run-id 本身已是 canonical 證據）。
    """
    meta = {"run_id": run_id}
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, window_start, window_end, manifest_sha256, completed_at
                FROM research.alpha_history_ingest_runs
                WHERE run_id = %s
                """,
                (run_id,),
            )
            row = cur.fetchone()
            if row:
                meta.update({
                    "status": row[0],
                    "window_start": str(row[1]),
                    "window_end": str(row[2]),
                    "manifest_sha256": row[3],
                    "completed_at": str(row[4]),
                })
    except Exception as exc:  # noqa: BLE001 — meta 缺失不阻斷診斷（run-id 已是證據）
        meta["meta_lookup_error"] = str(exc)
    return meta


def _funding_coverage(funding_rows):
    """唯讀統計 funding 覆蓋誠實標記（per-symbol count + span）。"""
    cov: dict = {}
    for s, rows in funding_rows.items():
        if rows:
            cov[s] = {"n": len(rows), "min": str(rows[0][0]), "max": str(rows[-1][0])}
        else:
            cov[s] = {"n": 0, "min": None, "max": None}
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

    規則（leak-free：全用 prior close，不含當日）：
      - BTC 收盤 > 200 日 MA 且 realized vol 非高檔 tercile → 'bull'
      - BTC 收盤 < 200 日 MA → 'bear'
      - 其餘（橫盤 / 高 vol 不明確）→ 'chop'
    為什麼 BTC 驅動全市場 regime：crypto 高相關，BTC 是市場 beta 主軸。
    warmup（前 200 日）未滿 → 'chop'（保守，不偽造方向）。

    ★ vol-tercile leak fix（協議 §1，修 trend data_loader.py:300）：
      trend 版用 ``np.quantile(全 finite_vols, 2/3)`` 算高 vol 門檻 = **full-sample
      cross-section leak**（用到未來 vol 分布）。本版改 **expanding/prior-365**：第 t 日
      的高 vol 門檻只用 [t-365, t-1] 的 vol 分布（不含當日與未來），是真正 leak-free PIT。
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
        c = prev[i]
        if not np.isfinite(c) or not np.isfinite(ma):
            continue
        if c > ma:
            out[i] = "bull"
        else:
            out[i] = "bear"
    # vol tercile 細分（leak-free expanding/prior-365）：高 vol 時 bull/bear 降級為 chop。
    vols = _rolling_vol_series(btc_close)
    for i in range(t):
        if not np.isfinite(vols[i]):
            continue
        # 高 vol 門檻只用過去 [i-365, i-1] 的 vol 分布（expanding/prior-N，leak-free）。
        win_lo = max(0, i - REGIME_VOL_TERCILE_PRIOR_DAYS)
        prior_vols = vols[win_lo: i]  # 不含 i（當日），不含未來
        prior_finite = prior_vols[np.isfinite(prior_vols)]
        if len(prior_finite) < 30:
            continue  # 先驗樣本不足 → 不降級（保守，不靠未來補）
        hi_thr = float(np.quantile(prior_finite, 2.0 / 3.0))
        if vols[i] >= hi_thr:
            out[i] = "chop"
    return out


def _rolling_vol_series(btc_close: np.ndarray) -> np.ndarray:
    """過去 30 日 prior 報酬 realized vol（leak-free，out[i] 只用到 i-1）。"""
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
