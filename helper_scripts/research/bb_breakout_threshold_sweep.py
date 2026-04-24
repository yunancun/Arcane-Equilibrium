#!/usr/bin/env python3
"""BB Breakout threshold sensitivity sweep — signal-level offline study.
BB 突破閾值敏感度掃描 — 信號級離線研究。

MODULE_NOTE (EN): P1-11 (1) partial. The full "strategy-level backtest
harness" path (proper Sharpe / drawdown / fees / position sizing via
`openclaw_core::backtest.rs`) is still ~1-2d of Rust wiring. This script
instead gives *signal-level* threshold sensitivity on real `market.klines`
data: for each (squeeze_bw, expansion_bw, volume_threshold, donchian_mode)
combo, count entry candidates that the bb_breakout state machine would
have triggered and report forward-return distribution at N / 2N / 4N min
horizons. Outputs are:
  - `/tmp/openclaw/bb_breakout_sweep_<ts>.csv` — one row per combo
  - stdout ranked top-N summary + CLI copy-paste TOML for hot-reload
Scope caveats (read before interpreting):
  * No position sizing / fees / slippage / persistence / cooldown — pure
    signal-rate + forward-return study. A combo that wins here can still
    lose money under fees + 10 min cooldown + persistence gate. Use for
    directional guidance, not for auto-promoting thresholds to production.
  * Forward returns are raw close-to-close, no exit-side modelling (no
    trailing stop / phys_lock replay). A 30-min forward return > 0 is
    necessary but not sufficient for net-positive edge.
  * Donchian "Score" mode is simulated as "always-emit + tally forward
    return separately for breach-confirmed vs miss". Operator reads
    whether +bonus vs -bonus rows differ materially in outcome.
  * The BB indicator period (20) and stddev (2) are fixed — sweeping those
    is a separate study (not P1-11 (1) scope, different research thread).

MODULE_NOTE (中): P1-11 (1) 部分工作。完整「策略-level backtest harness」
（接 `openclaw_core::backtest.rs` 做 Sharpe/drawdown/fee/倉位）仍需 Rust
接線 ~1-2d。本腳本先做 *信號級* 閾值敏感度：用真實 `market.klines` 對
每組 (squeeze_bw, expansion_bw, volume_threshold, donchian_mode) 組合，
統計 bb_breakout 狀態機會觸發的入場候選數量與 N/2N/4N 分鐘遠期收益分佈。
輸出：
  - `/tmp/openclaw/bb_breakout_sweep_<ts>.csv` — 每組合一行
  - stdout top-N 排序 + 可複製 TOML hot-reload 片段
Scope 限制（讀完再解讀結果）：
  * 無倉位/費率/滑價/persistence/cooldown — 純信號率 + 遠期收益研究。此
    排名領先的組合在手續費 + 10min cooldown + persistence 下仍可能虧損，
    只作方向指引，不代表可直接推上 production。
  * 遠期收益為原始 close-to-close，無出場建模（trailing stop / phys_lock）。
    30min 遠期 > 0 是必要非充分條件。
  * Donchian "Score" 模擬作「總是放行 + 拆分 breach 確認 / 未突破兩組結果」。
    operator 看 +bonus 與 -bonus 行為是否有差。
  * BB 指標 period (20) 與 stddev (2) 固定；sweep 那些是另一研究線。

Usage:
  OPENCLAW_DATABASE_URL=postgresql://... \\
    python3 helper_scripts/research/bb_breakout_threshold_sweep.py \\
    [--symbols BTCUSDT,ETHUSDT,...] [--days 14] [--timeframe 1m] \\
    [--forward-mins 15] [--top 10]

Exit codes: 0 = sweep complete; 2 = DB error / insufficient data.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd


# ═════════════════════════════════════════════════════════════════════════════
# DB connection (mirrors passive_wait_healthcheck.py style)
# DB 連線（沿用 passive_wait_healthcheck.py 風格）。
# ═════════════════════════════════════════════════════════════════════════════

def _get_conn():
    import psycopg2  # type: ignore
    dsn = (
        os.environ.get("OPENCLAW_DATABASE_URL")
        or f"postgresql://{os.environ.get('POSTGRES_USER','')}"
        f":{os.environ.get('POSTGRES_PASSWORD','')}"
        f"@{os.environ.get('POSTGRES_HOST','127.0.0.1')}"
        f":{os.environ.get('POSTGRES_PORT','5432')}"
        f"/{os.environ.get('POSTGRES_DB','')}"
    )
    return psycopg2.connect(dsn)


def fetch_klines(conn, symbol: str, timeframe: str, days: int) -> pd.DataFrame:
    """Pull N days of klines for one symbol. Returned frame is sorted by ts
    ascending with a RangeIndex reset so rolling-window indicators align.
    拉取一 symbol N 日 klines；時間升序 + reset RangeIndex 供滾動指標對齊。
    """
    sql = """
        SELECT ts, open, high, low, close, volume
        FROM market.klines
        WHERE symbol = %s AND timeframe = %s
          AND ts > NOW() - (%s || ' days')::interval
        ORDER BY ts ASC
    """
    df = pd.read_sql(sql, conn, params=(symbol, timeframe, str(days)))
    df.columns = [c.lower() for c in df.columns]
    return df.reset_index(drop=True)


# ═════════════════════════════════════════════════════════════════════════════
# Indicator computation — matches engine semantics closely but simplified.
# 指標計算 — 貼近 engine 語義但簡化。
# ═════════════════════════════════════════════════════════════════════════════

BB_PERIOD = 20
BB_STDDEV = 2.0
DONCHIAN_PERIOD = 20
VOLUME_MA_PERIOD = 20


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add BB bandwidth/%B + Donchian upper/lower + volume_ratio columns.

    - bandwidth = (bb_upper - bb_lower) / bb_middle  (matches
      `openclaw_core::indicators::bollinger` semantics).
    - percent_b = (close - bb_lower) / (bb_upper - bb_lower)
      (clamped 0..1 NOT applied — engine uses raw % B so values can exceed
      [0, 1] on breakouts; entry gate reads `%B > 1.0` / `< 0.0`).
    - volume_ratio = volume / 20-period avg volume (engine `volume_ratio`
      convention).
    bandwidth / %B / Donchian upper-lower / volume_ratio 新欄位；與 engine 一致。
    """
    out = df.copy()
    close = out["close"]

    # Bollinger
    middle = close.rolling(BB_PERIOD, min_periods=BB_PERIOD).mean()
    std = close.rolling(BB_PERIOD, min_periods=BB_PERIOD).std(ddof=0)
    upper = middle + BB_STDDEV * std
    lower = middle - BB_STDDEV * std
    out["bb_upper"] = upper
    out["bb_lower"] = lower
    out["bb_middle"] = middle
    # Protect div-by-zero on degenerate (all-equal) windows.
    # 防 degenerate（全相同）窗口除零。
    band = (upper - lower)
    out["bandwidth"] = (band / middle.replace(0, np.nan)).fillna(0.0)
    out["percent_b"] = ((close - lower) / band.replace(0, np.nan)).fillna(0.5)

    # Donchian (rolling max high / min low).
    # Donchian（滾動 N 根最高/最低）。
    out["donchian_upper"] = out["high"].rolling(
        DONCHIAN_PERIOD, min_periods=DONCHIAN_PERIOD
    ).max()
    out["donchian_lower"] = out["low"].rolling(
        DONCHIAN_PERIOD, min_periods=DONCHIAN_PERIOD
    ).min()

    # Volume ratio (current / 20-period avg).
    # 量比（當前 / 20 根均量）。
    vol_ma = out["volume"].rolling(
        VOLUME_MA_PERIOD, min_periods=VOLUME_MA_PERIOD
    ).mean()
    out["volume_ratio"] = (out["volume"] / vol_ma.replace(0, np.nan)).fillna(1.0)

    return out


# ═════════════════════════════════════════════════════════════════════════════
# Signal detection — squeeze→expansion→volume→direction→donchian (per combo).
# 信號偵測 — 壓縮→擴張→量→方向→Donchian（逐組合）。
# ═════════════════════════════════════════════════════════════════════════════

# FIX-26 mirror: how long a recorded squeeze stays valid before re-requiring
# a fresh squeeze. engine default 2_700_000 ms = 45 min; at 1m bars = 45 rows.
# FIX-26 對齊：記錄的壓縮在 45min 內有效；1m bars 即 45 根。
SQUEEZE_EXPIRY_BARS = 45


def detect_entries(
    ind: pd.DataFrame,
    squeeze_bw: float,
    expansion_bw: float,
    volume_threshold: float,
) -> pd.DataFrame:
    """Return DataFrame of entry candidates with columns:
    ts, direction (+1 long / -1 short), price, donchian_breach (bool).

    Walk bars in order, track last-seen squeeze index; on an expansion bar
    within SQUEEZE_EXPIRY_BARS after squeeze + volume_ratio >= threshold
    + %B extreme (>1.0 long / <0.0 short), emit a candidate.

    指標逐根走訪，追蹤最近壓縮 index；擴張根在 SQUEEZE_EXPIRY_BARS 內 +
    量 >= 閾值 + %B 極端（>1.0 做多 / <0.0 做空），即記為候選。
    """
    # Pre-extract NumPy views (dramatically faster than .iloc loop).
    # 預先抽 NumPy view（比 .iloc 迴圈快很多）。
    bw = ind["bandwidth"].to_numpy()
    pb = ind["percent_b"].to_numpy()
    vol = ind["volume_ratio"].to_numpy()
    price = ind["close"].to_numpy()
    dc_up = ind["donchian_upper"].to_numpy()
    dc_lo = ind["donchian_lower"].to_numpy()
    ts = ind["ts"].to_numpy()

    # Need enough warm-up for BB/Donchian to be valid.
    # 需至少 BB_PERIOD 根 warm-up。
    n = len(ind)
    start = max(BB_PERIOD, DONCHIAN_PERIOD, VOLUME_MA_PERIOD)

    entries = []
    last_squeeze_idx = -1
    for i in range(start, n):
        # FIX-26 parity: Rust `bb_breakout::on_tick` records squeeze_detected_ms
        # ONLY on first detection (see mod.rs:370 `if st.squeeze_detected_ms.is_none()`).
        # Continued squeeze does NOT refresh the timer — expiry clock runs from the
        # first bar after the previous clear. Mirror this exactly or signal counts
        # inflate under long-continuous-squeeze regimes (e.g., 1m BTC where
        # bandwidth stays < typical squeeze_bw for hundreds of bars).
        # FIX-26 對齊：Rust 只在 squeeze_detected_ms 為 None 時才記錄首次偵測；持續
        # 壓縮不會刷新 timer。若覆寫（overwrite-each-bar）會讓連續壓縮下的信號數
        # 大幅膨脹（1m BTC 典型情況），sweep 結果會偏離 runtime 行為。
        if bw[i] < squeeze_bw:
            if last_squeeze_idx < 0:
                last_squeeze_idx = i
            continue  # cannot simultaneously expand on the same bar
        if last_squeeze_idx < 0:
            continue
        if i - last_squeeze_idx > SQUEEZE_EXPIRY_BARS:
            # FIX-26 NOTE: Rust does NOT auto-clear squeeze_detected_ms on expiry;
            # the only clear paths are (a) entry emission + (b) `on_external_close`.
            # This means if squeeze runs uninterrupted past expiry, the strategy
            # deadlocks until an entry fires. In pure-sweep offline replay there
            # is no position/close mechanic, so we continue (don't clear) — the
            # record stays stuck and no further squeezes register for this symbol
            # until we hit expiry, at which point NOTHING fires until we see a
            # bar with bandwidth ≥ squeeze_bw to "break" the continuous squeeze.
            # That post-break bar then still has the stale squeeze_detected_ms,
            # so entry is still blocked (expired). The strategy is effectively
            # locked out — matches real Rust behaviour on prolonged squeeze.
            # FIX-26 注意：Rust 過期不自動清 squeeze_detected_ms（僅入場或外部平倉會清）。
            # 長時間持續壓縮會讓策略死鎖，本 sweep 亦不清 → 與 runtime 一致。
            continue
        if bw[i] <= expansion_bw:
            continue
        if vol[i] < volume_threshold:
            continue
        if pb[i] > 1.0:
            direction = 1
        elif pb[i] < 0.0:
            direction = -1
        else:
            continue
        if direction == 1:
            donchian_breach = price[i] >= dc_up[i]
        else:
            donchian_breach = price[i] <= dc_lo[i]
        entries.append((ts[i], direction, price[i], donchian_breach, i))
        # Consume this squeeze (engine sets squeeze_detected_ms=None on entry).
        # 入場後消耗此 squeeze（對齊 engine 在入場時清除 squeeze_detected_ms）。
        last_squeeze_idx = -1

    return pd.DataFrame(
        entries,
        columns=["ts", "direction", "price", "donchian_breach", "bar_idx"],
    )


def attach_forward_returns(
    entries: pd.DataFrame,
    ind: pd.DataFrame,
    horizons_bars: list[int],
) -> pd.DataFrame:
    """For each entry, compute forward return at each horizon (in bars).
    Direction-adjusted: long = fwd/entry − 1, short = 1 − fwd/entry.
    每個入場算各 horizon 遠期收益；方向已調整（做空取反號）。
    """
    if entries.empty:
        return entries
    close = ind["close"].to_numpy()
    n = len(close)
    out = entries.copy()
    for h in horizons_bars:
        col = f"fwd_{h}"
        rets = np.full(len(out), np.nan)
        for k, (idx, direction) in enumerate(zip(out["bar_idx"].to_numpy(), out["direction"].to_numpy())):
            fwd_idx = idx + h
            if fwd_idx >= n:
                continue
            raw = close[fwd_idx] / close[idx] - 1.0
            rets[k] = raw if direction == 1 else -raw
        out[col] = rets
    return out


# ═════════════════════════════════════════════════════════════════════════════
# Aggregation — per-combo stats.
# 聚合 — 每組合統計。
# ═════════════════════════════════════════════════════════════════════════════

def aggregate_combo(
    entries: pd.DataFrame, horizons_bars: list[int]
) -> dict[str, float]:
    """Per-combo summary: signal count, forward return mean/median, win rate,
    Sharpe-like (mean / std); breakout Donchian-breach split.
    每組合摘要：信號數、遠期收益均值/中位數、勝率、Sharpe-like；Donchian 拆分。
    """
    n = len(entries)
    stats: dict[str, float] = {"n_signals": float(n)}
    if n == 0:
        for h in horizons_bars:
            stats[f"fwd{h}_mean"] = float("nan")
            stats[f"fwd{h}_med"] = float("nan")
            stats[f"fwd{h}_winr"] = float("nan")
            stats[f"fwd{h}_sharpe"] = float("nan")
        stats["donchian_breach_frac"] = float("nan")
        stats["breach_fwd_mean_diff"] = float("nan")
        return stats

    for h in horizons_bars:
        col = f"fwd_{h}"
        vals = entries[col].dropna()
        if len(vals) == 0:
            stats[f"fwd{h}_mean"] = float("nan")
            stats[f"fwd{h}_med"] = float("nan")
            stats[f"fwd{h}_winr"] = float("nan")
            stats[f"fwd{h}_sharpe"] = float("nan")
            stats[f"fwd{h}_se"] = float("nan")
            stats[f"fwd{h}_tstat"] = float("nan")
        else:
            mu = float(vals.mean())
            sd = float(vals.std(ddof=0))
            k = len(vals)
            # SE of mean + two-sided t-like statistic (mu / SE). |t| > 1.96 ≈
            # 95% significance; |t| > 2.58 ≈ 99%. This gates the top-N rankings
            # against the "small-N illusion" where a handful of lucky right-tail
            # winners look like edge but aren't distinguishable from zero.
            # SE = 標準誤；|t| > 1.96 ≈ 95% 顯著；過濾「小樣本右尾幻覺」。
            se = sd / (k ** 0.5) if k > 0 and sd > 1e-12 else float("nan")
            stats[f"fwd{h}_mean"] = mu
            stats[f"fwd{h}_med"] = float(vals.median())
            stats[f"fwd{h}_winr"] = float((vals > 0).mean())
            stats[f"fwd{h}_sharpe"] = mu / sd if sd > 1e-12 else float("nan")
            stats[f"fwd{h}_se"] = se
            stats[f"fwd{h}_tstat"] = mu / se if se and se > 1e-12 else float("nan")

    stats["donchian_breach_frac"] = float(entries["donchian_breach"].mean())
    # Score-mode indicator: does Donchian breach actually correlate with better
    # outcomes? If the diff is ~0, the +bonus vs -bonus under Score mode is
    # just noise; if strongly positive, Score mode's bias is real.
    # Add breach subset SIZE + Welch-like t-stat for the diff so readers can
    # see whether the signed diff is distinguishable from zero, not just read
    # the sign. Small breach_n (< ~15) means the diff is noise-dominated.
    # Score mode 指標 + subset size + Welch-like t 以判讀 diff 是否顯著。
    primary = horizons_bars[len(horizons_bars) // 2]  # middle horizon as primary
    col = f"fwd_{primary}"
    if col in entries:
        br = entries[entries["donchian_breach"]][col].dropna()
        mi = entries[~entries["donchian_breach"]][col].dropna()
        stats["breach_n"] = float(len(br))
        stats["miss_n"] = float(len(mi))
        if len(br) > 1 and len(mi) > 1:
            diff = float(br.mean() - mi.mean())
            var_b = float(br.var(ddof=1)) / len(br)
            var_m = float(mi.var(ddof=1)) / len(mi)
            se_diff = (var_b + var_m) ** 0.5 if (var_b + var_m) > 1e-18 else float("nan")
            stats["breach_fwd_mean_diff"] = diff
            stats["breach_diff_tstat"] = diff / se_diff if se_diff and se_diff > 1e-12 else float("nan")
        else:
            stats["breach_fwd_mean_diff"] = float("nan")
            stats["breach_diff_tstat"] = float("nan")
    return stats


# ═════════════════════════════════════════════════════════════════════════════
# Main sweep driver.
# 主掃描驅動。
# ═════════════════════════════════════════════════════════════════════════════

DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]

# Candidate threshold grids — cover Conservative / Balanced / Aggressive
# profile seed values + a neighborhood. Respects validate invariants
# (squeeze_bw < expansion_bw, volume_threshold >= 1.0).
# 候選閾值網格 — 覆蓋三 profile 種子值 + 鄰域；遵守 validate 不變量。
DEFAULT_SQUEEZE_GRID = [0.015, 0.020, 0.025, 0.030, 0.035, 0.040]
DEFAULT_EXPANSION_GRID = [0.035, 0.040, 0.045, 0.050, 0.055]
DEFAULT_VOLUME_GRID = [1.00, 1.10, 1.20, 1.35, 1.50]


def build_combos(
    squeeze_grid: list[float],
    expansion_grid: list[float],
    volume_grid: list[float],
) -> list[tuple[float, float, float]]:
    """Enumerate valid (squeeze, expansion, volume) combos; drop those violating
    squeeze < expansion invariant."""
    return [
        (s, e, v)
        for s, e, v in product(squeeze_grid, expansion_grid, volume_grid)
        if s < e
    ]


def run_sweep(
    symbols: list[str],
    timeframe: str,
    days: int,
    horizons_bars: list[int],
    combos: list[tuple[float, float, float]],
) -> pd.DataFrame:
    """Pull klines, compute indicators once per symbol, then evaluate all combos
    reusing the indicator frame. Returns flat DataFrame keyed by
    (squeeze_bw, expansion_bw, volume_threshold) pooled across symbols.
    每 symbol 只算一次指標，重複組合評估；回傳按組合 pool 跨 symbol 的 flat 表。
    """
    conn = _get_conn()
    try:
        symbol_indicators: dict[str, pd.DataFrame] = {}
        for sym in symbols:
            df = fetch_klines(conn, sym, timeframe, days)
            if len(df) < BB_PERIOD * 2:
                print(f"[skip] {sym}: only {len(df)} bars, need ≥ {BB_PERIOD * 2}")
                continue
            symbol_indicators[sym] = compute_indicators(df)
            print(f"[load] {sym}: {len(df)} bars, "
                  f"{df['ts'].min()} → {df['ts'].max()}")
    finally:
        conn.close()

    if not symbol_indicators:
        raise RuntimeError("no symbols with sufficient bars")

    rows = []
    for sq, ex, vol in combos:
        pooled_entries: list[pd.DataFrame] = []
        for sym, ind in symbol_indicators.items():
            e = detect_entries(ind, sq, ex, vol)
            e = attach_forward_returns(e, ind, horizons_bars)
            e["symbol"] = sym
            pooled_entries.append(e)
        all_entries = pd.concat(pooled_entries, ignore_index=True) if pooled_entries else pd.DataFrame()
        stats = aggregate_combo(all_entries, horizons_bars)
        stats.update({"squeeze_bw": sq, "expansion_bw": ex, "volume_threshold": vol})
        rows.append(stats)

    return pd.DataFrame(rows)


# ═════════════════════════════════════════════════════════════════════════════
# Reporting.
# ═════════════════════════════════════════════════════════════════════════════

def print_top(result: pd.DataFrame, horizons_bars: list[int], top_n: int) -> None:
    """Print top-N combos ranked by multiple criteria."""
    if result.empty:
        print("[empty] no combos produced stats")
        return
    primary = horizons_bars[len(horizons_bars) // 2]

    # Filter to combos with a statistically useful sample.
    # 過濾到有統計意義的樣本量。
    min_sig = max(20, int(result["n_signals"].max() * 0.05))
    qualified = result[result["n_signals"] >= min_sig].copy()
    print(f"\n[qualified] {len(qualified)} combos with ≥ {min_sig} signals "
          f"(out of {len(result)} total)")
    if qualified.empty:
        qualified = result.copy()

    # Rankings. `tstat` = mean / SE; |tstat| > 1.96 ≈ 95% significance. A top
    # combo with |tstat| < 1.0 is not distinguishable from zero edge even if it
    # sorts high — print it so the reader sees the caveat directly, not only
    # after reading the report.
    # 排序：tstat = mean/SE；|tstat|<1.0 基本等於噪音，即使排前也無意義。
    cols_full = [
        "squeeze_bw", "expansion_bw", "volume_threshold", "n_signals",
        f"fwd{primary}_mean", f"fwd{primary}_winr", f"fwd{primary}_sharpe",
        f"fwd{primary}_tstat",
        "donchian_breach_frac", "breach_n",
        "breach_fwd_mean_diff", "breach_diff_tstat",
    ]
    cols_short = [
        "squeeze_bw", "expansion_bw", "volume_threshold", "n_signals",
        f"fwd{primary}_mean", f"fwd{primary}_winr",
        f"fwd{primary}_sharpe", f"fwd{primary}_tstat",
    ]
    print(f"\n═════ Top {top_n} by fwd{primary}_mean ═════")
    print(qualified.nlargest(top_n, f"fwd{primary}_mean")[cols_full].to_string(index=False))

    print(f"\n═════ Top {top_n} by fwd{primary}_tstat (statistical edge, |t|>1.96 ≈ 95%) ═════")
    print(qualified.nlargest(top_n, f"fwd{primary}_tstat")[cols_full].to_string(index=False))

    print(f"\n═════ Top {top_n} by fwd{primary}_sharpe (risk-adjusted) ═════")
    print(qualified.nlargest(top_n, f"fwd{primary}_sharpe")[cols_full].to_string(index=False))

    print(f"\n═════ Top {top_n} by n_signals (dormancy check) ═════")
    print(qualified.nlargest(top_n, "n_signals")[cols_short].to_string(index=False))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS),
                    help=f"comma-separated symbols (default {','.join(DEFAULT_SYMBOLS)})")
    ap.add_argument("--timeframe", default="1m",
                    help="kline timeframe (default 1m)")
    ap.add_argument("--days", type=int, default=14,
                    help="days of history to pull (default 14)")
    ap.add_argument("--forward-mins", default="5,15,30,60",
                    help="comma-separated forward return horizons in minutes")
    ap.add_argument("--top", type=int, default=10,
                    help="top-N combos to print per ranking")
    ap.add_argument("--squeeze-grid", default=None,
                    help="comma-separated squeeze_bw candidates (default covers 0.015-0.040)")
    ap.add_argument("--expansion-grid", default=None,
                    help="comma-separated expansion_bw candidates (default covers 0.035-0.055)")
    ap.add_argument("--volume-grid", default=None,
                    help="comma-separated volume_threshold candidates (default covers 1.0-1.5)")
    ap.add_argument("--out-dir", default=None,
                    help="output dir for CSV (default $OPENCLAW_DATA_DIR or /tmp/openclaw)")
    args = ap.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    forward_mins = [int(x) for x in args.forward_mins.split(",")]
    # 1-minute bar = 1 bar per minute; for other timeframes user must
    # ensure horizons_bars expresses the same wall-clock duration.
    # 1m bar 下 bar 數==分鐘數；其他 timeframe 使用者自負責換算。
    horizons_bars = forward_mins if args.timeframe == "1m" else forward_mins

    squeeze_grid = [float(x) for x in args.squeeze_grid.split(",")] if args.squeeze_grid else DEFAULT_SQUEEZE_GRID
    expansion_grid = [float(x) for x in args.expansion_grid.split(",")] if args.expansion_grid else DEFAULT_EXPANSION_GRID
    volume_grid = [float(x) for x in args.volume_grid.split(",")] if args.volume_grid else DEFAULT_VOLUME_GRID

    combos = build_combos(squeeze_grid, expansion_grid, volume_grid)
    print(f"[config] symbols={symbols} timeframe={args.timeframe} days={args.days}")
    print(f"[config] forward horizons (bars): {horizons_bars}")
    print(f"[config] combos to evaluate: {len(combos)}")

    try:
        result = run_sweep(symbols, args.timeframe, args.days, horizons_bars, combos)
    except Exception as e:
        print(f"[FATAL] sweep failed: {e}")
        return 2

    # Output CSV (latest + dated per CLAUDE.md §七 convention).
    # 輸出 CSV（latest + dated，對齊 §七 慣例）。
    out_dir = Path(args.out_dir or os.environ.get("OPENCLAW_DATA_DIR") or "/tmp/openclaw")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    latest = out_dir / "bb_breakout_sweep_latest.csv"
    dated = out_dir / f"bb_breakout_sweep_{ts}.csv"
    result.to_csv(latest, index=False)
    result.to_csv(dated, index=False)
    print(f"[output] wrote {latest} + {dated}")

    print_top(result, horizons_bars, args.top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
