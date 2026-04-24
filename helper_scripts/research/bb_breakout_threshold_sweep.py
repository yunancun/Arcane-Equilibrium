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

# t-critical values for two-sided alpha=0.05 (df = n-1). Hand-curated from
# scipy.stats.t.ppf(0.975, df=k-1). Used by aggregate_combo to stamp each
# combo with the correct df-aware threshold instead of relying on the |t|>1.96
# Normal approximation (which only holds for n>=~30 and silently inflates
# apparent significance for small samples).
# t 雙尾 0.05 臨界值表（df=n-1）；用 df-aware 不用大樣本 1.96 近似避免膨脹小樣本顯著性。
_T_CRIT_95_TABLE = {
    2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571, 7: 2.447, 8: 2.365,
    9: 2.306, 10: 2.262, 11: 2.228, 12: 2.201, 13: 2.179, 14: 2.160, 15: 2.145,
    16: 2.131, 17: 2.120, 18: 2.110, 19: 2.101, 20: 2.093, 25: 2.064, 29: 2.045,
}


def _t_crit_95_for_n(n: int) -> float:
    """Return df=n-1 two-sided alpha=0.05 t-critical value. n<2 → NaN; n>=30
    → 1.96 (Normal approximation valid). Linearly interpolate within table.
    回傳 df=n-1 雙尾 0.05 t 臨界；n<2 → NaN；n>=30 大樣本回 1.96。"""
    if n < 2:
        return float("nan")
    if n >= 30:
        return 1.96
    if n in _T_CRIT_95_TABLE:
        return _T_CRIT_95_TABLE[n]
    # interpolate between nearest table entries
    keys = sorted(_T_CRIT_95_TABLE.keys())
    for i, k in enumerate(keys):
        if k > n:
            lo = keys[i - 1]
            hi = k
            return _T_CRIT_95_TABLE[lo] + (_T_CRIT_95_TABLE[hi] - _T_CRIT_95_TABLE[lo]) * (n - lo) / (hi - lo)
    return 1.96


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
    # IMPORTANT — measurement bias context (FA audit 2026-04-24):
    # Both Rust (`indicators/trend.rs:190`) and pandas `rolling(N).max()`
    # INCLUDE the current bar in the window. So `dc.upper[i] = max(high[i-19..=i])`
    # — by construction `high[i] <= dc.upper[i]` always holds. The breach
    # check `close[i] >= dc.upper[i]` therefore fires only when this bar is
    # the new local max (close == high == max). Such bars are by their nature
    # at the top of a recent push and tend to mean-revert → forward returns
    # from breach bars are biased low NOT because Donchian is a bad signal,
    # but because the breach-detection methodology itself selects mean-reverting
    # tops. Production engine inherits this bias.
    #
    # We compute BOTH the engine-faithful (current-bar-inclusive) and a
    # leak-free (`shift(1)`, prior-bar-only) variant so the report can show
    # F3-style results under both definitions. Leak-free Donchian is the
    # textbook breakout signal; current-bar-inclusive is what the engine
    # actually does. Operator should compare to decide whether to also fix
    # the engine's Donchian usage.
    #
    # Donchian（滾動 N 根最高/最低）：Rust 與 pandas rolling 都**包含 current bar**。
    # close[i]>=dc.upper[i] 只在「本根=近 N 根新高」時 true → 必然 mean-revert，
    # 是測量偏 not signal property。同時計算 leak-free shift(1) 版本供對比。
    out["donchian_upper"] = out["high"].rolling(
        DONCHIAN_PERIOD, min_periods=DONCHIAN_PERIOD
    ).max()
    out["donchian_lower"] = out["low"].rolling(
        DONCHIAN_PERIOD, min_periods=DONCHIAN_PERIOD
    ).min()
    # Leak-free variant: shift(1) excludes the current bar.
    # Leak-free 變體：shift(1) 排除 current bar。
    out["donchian_upper_leakfree"] = out["donchian_upper"].shift(1)
    out["donchian_lower_leakfree"] = out["donchian_lower"].shift(1)

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
    # FA audit (2026-04-24) leak-free Donchian: shift(1) values excluding
    # current bar. NaN on first DONCHIAN_PERIOD+1 bars, harmless because we
    # already enforce `start = max(BB_PERIOD, DONCHIAN_PERIOD, VOLUME_MA_PERIOD)`
    # and breach check tolerates NaN (any comparison with NaN returns False).
    # FA audit leak-free 欄位；前 N+1 根 NaN 安全（比較 NaN 必為 False，不誤判 breach）。
    dc_up_lf = ind["donchian_upper_leakfree"].to_numpy()
    dc_lo_lf = ind["donchian_lower_leakfree"].to_numpy()
    ts = ind["ts"].to_numpy()

    # Need enough warm-up for BB/Donchian to be valid.
    # 需至少 BB_PERIOD 根 warm-up。
    n = len(ind)
    start = max(BB_PERIOD, DONCHIAN_PERIOD, VOLUME_MA_PERIOD)

    entries = []
    last_squeeze_idx = -1
    for i in range(start, n):
        # FIX-26-DEADLOCK-1 parity (Rust commit bcc5401, 2026-04-24): stale
        # squeeze records are auto-cleared BEFORE the is_none() guard when
        # they have expired. The pre-fix semantic permanently locked out
        # symbols after one failed-entry expiry window; the post-fix semantic
        # (now shipped in Rust) allows fresh squeeze re-registration. Python
        # now mirrors post-fix. For pre-fix behaviour studies, comment this
        # block out.
        #
        # E2 audit follow-up (2026-04-24): Rust uses `>=` for the inclusive
        # boundary (mod.rs:412 `ctx.timestamp_ms >= stored_ts.saturating_add(...)`).
        # Original Python used `>` which leaves a 1-bar gap at the exact
        # boundary (`i - stored == SQUEEZE_EXPIRY_BARS` clears in Rust but not
        # Python). Switch to `>=` for strict parity.
        # FIX-26-DEADLOCK-1 對齊（Rust 2026-04-24 修）：過期 squeeze 記錄在 is_none()
        # guard 前自動清除。E2 audit：用 `>=` inclusive 對齊 Rust，原 `>` 在邊界差 1 bar。
        if last_squeeze_idx >= 0 and i - last_squeeze_idx >= SQUEEZE_EXPIRY_BARS:
            last_squeeze_idx = -1

        # FIX-26 original: record ONLY on first detection within a window.
        # Continued-squeeze bars do NOT refresh the timer (preserved by Rust
        # commit bcc5401 — auto-clear only triggers on expiry, not on continued
        # detection within an active window).
        # FIX-26 原語義：每個 squeeze 窗口內僅首次記錄；持續壓縮不刷新。
        if bw[i] < squeeze_bw:
            if last_squeeze_idx < 0:
                last_squeeze_idx = i
            continue  # cannot simultaneously expand on the same bar
        if last_squeeze_idx < 0:
            continue
        if i - last_squeeze_idx > SQUEEZE_EXPIRY_BARS:
            # Redundant with the auto-clear at top of loop, kept as safety net.
            # 與迴圈頂的 auto-clear 冗餘，保留為安全網。
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
        # Engine-faithful (current-bar-inclusive) breach AND leak-free
        # (prior-bar-only) breach. Capture both per entry so aggregate_combo
        # can compute breach_diff_tstat under both definitions and the report
        # can show whether the F3 finding survives the look-ahead correction.
        # 引擎一致 breach（含當前 bar）與 leak-free breach（僅排除當前 bar），
        # 兩者並存供 aggregate 對比、揭露 F3 是否仍成立於 leak-free 定義下。
        if direction == 1:
            donchian_breach = price[i] >= dc_up[i]
            donchian_breach_lf = price[i] >= dc_up_lf[i] if not np.isnan(dc_up_lf[i]) else False
        else:
            donchian_breach = price[i] <= dc_lo[i]
            donchian_breach_lf = price[i] <= dc_lo_lf[i] if not np.isnan(dc_lo_lf[i]) else False
        entries.append((ts[i], direction, price[i], donchian_breach, donchian_breach_lf, i))
        # Consume this squeeze (engine sets squeeze_detected_ms=None on entry).
        # 入場後消耗此 squeeze（對齊 engine 在入場時清除 squeeze_detected_ms）。
        last_squeeze_idx = -1

    return pd.DataFrame(
        entries,
        columns=[
            "ts", "direction", "price",
            "donchian_breach", "donchian_breach_leakfree",
            "bar_idx",
        ],
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
        # Empty-combo path — populate the SAME keys as the populated path so
        # pd.DataFrame construction from list-of-dicts yields a consistent
        # schema across all combos. Missing a key in the empty branch causes
        # `print_top`'s column subscript to explode with an Index([-1]*len)
        # error (pandas silently treats the missing column as a positional
        # -1 index). Keep in lockstep with the populated `for h in ...` loop
        # and the Donchian breach block below.
        # 空組合也要填齊 key：list-of-dicts → DataFrame 才會 schema 一致。
        for h in horizons_bars:
            stats[f"fwd{h}_mean"] = float("nan")
            stats[f"fwd{h}_med"] = float("nan")
            stats[f"fwd{h}_winr"] = float("nan")
            stats[f"fwd{h}_sharpe"] = float("nan")
            stats[f"fwd{h}_se"] = float("nan")
            stats[f"fwd{h}_tstat"] = float("nan")
            stats[f"fwd{h}_t_crit_95"] = float("nan")
        stats["donchian_breach_frac"] = float("nan")
        stats["donchian_breach_leakfree_frac"] = float("nan")
        stats["breach_n"] = 0.0
        stats["miss_n"] = 0.0
        stats["breach_fwd_mean_diff"] = float("nan")
        stats["breach_diff_tstat"] = float("nan")
        stats["breach_n_leakfree"] = 0.0
        stats["miss_n_leakfree"] = 0.0
        stats["breach_fwd_mean_diff_leakfree"] = float("nan")
        stats["breach_diff_tstat_leakfree"] = float("nan")
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
            # FA audit (2026-04-24): use SAMPLE std (ddof=1, Bessel correction)
            # not POPULATION std (ddof=0). For small n (<30) the bias is
            # ~7-15% and biases tstat upward, inflating apparent significance.
            # FA audit：sample std 用 ddof=1，否則小 n 下 sd 被低估、tstat 膨脹。
            sd = float(vals.std(ddof=1)) if len(vals) > 1 else float("nan")
            k = len(vals)
            # SE of mean + t-statistic. NOTE the t-test is one-sample with
            # null mu0=0 and df=k-1; for n<30 the |t|>1.96 Normal approximation
            # is inadequate — use df-aware critical values from
            # `scipy.stats.t.ppf(0.975, df=k-1)` if possible, or refer to the
            # `fwd{h}_t_crit_95` column we add below for a self-contained
            # rule-of-thumb threshold.
            # SE 與 t 統計；df=k-1。n<30 不適用 1.96 大樣本近似 — 看 t_crit_95 欄。
            se = sd / (k ** 0.5) if k > 1 and sd > 1e-12 else float("nan")
            stats[f"fwd{h}_mean"] = mu
            stats[f"fwd{h}_med"] = float(vals.median())
            stats[f"fwd{h}_winr"] = float((vals > 0).mean())
            stats[f"fwd{h}_sharpe"] = mu / sd if sd and sd > 1e-12 else float("nan")
            stats[f"fwd{h}_se"] = se
            stats[f"fwd{h}_tstat"] = mu / se if se and se > 1e-12 else float("nan")
            # df-aware 95% two-sided t critical value (Welch-Satterthwaite-free,
            # uses simple df=k-1). Table values for n=2..30; n>=30 use 1.96.
            # df 對應 95% 雙尾 t 臨界值；小 n 用查表，n>=30 用 1.96。
            stats[f"fwd{h}_t_crit_95"] = _t_crit_95_for_n(k)

    # Also coerce here; mean of object-dtype bools returns NaN on pandas 3.
    # 同樣需強制 bool：object dtype 下 mean() 於 pandas 3 會返 NaN。
    stats["donchian_breach_frac"] = float(entries["donchian_breach"].astype(bool).mean())
    stats["donchian_breach_leakfree_frac"] = float(
        entries["donchian_breach_leakfree"].astype(bool).mean()
    )
    # Score-mode indicator: does Donchian breach actually correlate with better
    # outcomes? If the diff is ~0, the +bonus vs -bonus under Score mode is
    # just noise; if strongly positive, Score mode's bias is real.
    # Add breach subset SIZE + Welch-like t-stat for the diff so readers can
    # see whether the signed diff is distinguishable from zero, not just read
    # the sign. Small breach_n (< ~15) means the diff is noise-dominated.
    # Score mode 指標 + subset size + Welch-like t 以判讀 diff 是否顯著。
    primary = horizons_bars[len(horizons_bars) // 2]  # middle horizon as primary
    col = f"fwd_{primary}"

    def _breach_diff_stats(mask_col: str, n_key: str, miss_key: str,
                           diff_key: str, tstat_key: str) -> None:
        """Helper to compute one set of breach-vs-miss diff stats. Coerces
        bool dtype (avoids ~series → int trap) and applies Welch SE.
        Note: `breach_diff_tstat` should be compared against
        `_t_crit_95_for_n(min(breach_n, miss_n))` not 1.96 — small subsamples
        invalidate the Normal approximation.
        Bonferroni note: when ranking 64 combos × N horizons, the proper
        family-wise α=0.05 critical |t| is `_t_crit_95_for_n(min_n) +
        log(n_tests)` adjustment per dim. This is recorded for the report
        layer to apply, NOT applied here (script is per-combo agnostic).
        Helper：計算一組 breach-vs-miss 差異統計；強制 bool dtype + Welch SE。"""
        mask = entries[mask_col].astype(bool)
        br_v = entries[mask][col].dropna()
        mi_v = entries[~mask][col].dropna()
        stats[n_key] = float(len(br_v))
        stats[miss_key] = float(len(mi_v))
        if len(br_v) > 1 and len(mi_v) > 1:
            diff = float(br_v.mean() - mi_v.mean())
            var_b = float(br_v.var(ddof=1)) / len(br_v)
            var_m = float(mi_v.var(ddof=1)) / len(mi_v)
            se_diff = (var_b + var_m) ** 0.5 if (var_b + var_m) > 1e-18 else float("nan")
            stats[diff_key] = diff
            stats[tstat_key] = diff / se_diff if se_diff and se_diff > 1e-12 else float("nan")
        else:
            stats[diff_key] = float("nan")
            stats[tstat_key] = float("nan")

    if col in entries:
        # FA audit (2026-04-24): compute breach-diff stats under BOTH the
        # engine-faithful Donchian (current-bar-inclusive, mean-revert biased)
        # AND the leak-free Donchian (prior-bar-only, textbook breakout).
        # The leak-free numbers are the "real" measurement of Donchian's
        # value as a confirmation signal; the engine-faithful numbers reflect
        # what the production strategy will actually see.
        # FA audit：對引擎一致 + leak-free 兩種 Donchian 各算一組 breach diff，
        # 報告需同時呈現以揭露 F3 是否為測量偏。
        _breach_diff_stats(
            "donchian_breach",
            "breach_n", "miss_n",
            "breach_fwd_mean_diff", "breach_diff_tstat",
        )
        _breach_diff_stats(
            "donchian_breach_leakfree",
            "breach_n_leakfree", "miss_n_leakfree",
            "breach_fwd_mean_diff_leakfree", "breach_diff_tstat_leakfree",
        )
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

    # Rankings + STATISTICAL HEALTH WARNINGS.
    # Use df-aware t_crit_95 column for per-row significance gate, NOT the
    # 1.96 Normal approximation (only valid n>=30). Also remind operator
    # of Bonferroni correction for multiple-testing — running 64 combos ×
    # k horizons, naive top-N picking IS look-elsewhere fishing.
    # 排序 + 統計健康警告。用 df-aware t_crit_95，不用 1.96 大樣本近似；
    # 提醒 operator 多重檢驗 Bonferroni 校正（top-N 是 look-elsewhere fishing）。
    n_combos = len(qualified)
    n_horizons = len(horizons_bars)
    n_tests = n_combos * n_horizons
    # Bonferroni-corrected α for family-wise 0.05; use α/n then convert to
    # ~|z| for n>=30 or ~t with worst-case df. Conservative threshold for
    # operator visual scan: |t| > 3.5 ~= Bonferroni 95% with df>=20.
    # Bonferroni 95% 校正：family-wise α=0.05 → |t|>~3.5（保守，Normal 端）。
    bonferroni_t = 3.5 if n_tests > 16 else 2.5
    print(f"\n═════ STATISTICAL HEALTH ═════")
    print(f"  combos: {n_combos} × horizons: {n_horizons} = {n_tests} tests")
    print(f"  Bonferroni-corrected |t| threshold for FW α=0.05: ~{bonferroni_t}")
    print(f"  Pooled signals across 5 strongly-correlated symbols (BTC/ETH/SOL/")
    print(f"  XRP/DOGE corr ~0.6-0.8) — effective independent n ≈ raw_n / 3-4.")
    print(f"  Engine-faithful Donchian (`donchian_breach_*`) includes current bar")
    print(f"  → mean-revert biased. Compare against `*_leakfree` columns (shift(1))")
    print(f"  to see if F3-style breach effects survive the look-ahead correction.")
    print(f"  Per-row: |fwd{primary}_tstat| vs `fwd{primary}_t_crit_95` is df-aware.")

    cols_full = [
        "squeeze_bw", "expansion_bw", "volume_threshold", "n_signals",
        f"fwd{primary}_mean", f"fwd{primary}_winr", f"fwd{primary}_sharpe",
        f"fwd{primary}_tstat", f"fwd{primary}_t_crit_95",
        "donchian_breach_frac", "breach_n",
        "breach_fwd_mean_diff", "breach_diff_tstat",
        "breach_n_leakfree", "breach_diff_tstat_leakfree",
    ]
    cols_short = [
        "squeeze_bw", "expansion_bw", "volume_threshold", "n_signals",
        f"fwd{primary}_mean", f"fwd{primary}_winr",
        f"fwd{primary}_sharpe", f"fwd{primary}_tstat",
    ]
    print(f"\n═════ Top {top_n} by fwd{primary}_mean ═════")
    print(qualified.nlargest(top_n, f"fwd{primary}_mean")[cols_full].to_string(index=False))

    print(f"\n═════ Top {top_n} by fwd{primary}_tstat (compare to t_crit_95 for df-aware 95%; Bonferroni ~{bonferroni_t}) ═════")
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
