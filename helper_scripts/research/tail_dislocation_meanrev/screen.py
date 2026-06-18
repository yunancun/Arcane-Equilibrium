#!/usr/bin/env python3
"""tail_dislocation_meanrev.screen — 條件式尾部錯位均值回歸篩查（$0 唯讀 OFFLINE）。

MODULE_NOTE
模塊用途：
  測試本盈利弧從未跑過的「反邏輯、大-move、maker-進場」切法——條件式尾部錯位
  均值回歸（conditional tail-dislocation mean-reversion）。機制：

    在 t-1 收盤後，掛一張 maker 限價 BUY 在 prior_close*(1-K)，K∈{8%,10%,15%,20%}。
    它「只在當日 LOW <= 該價位」才成交（=一次 flash-crash／恐慌拋售）。成交價=該
    maker 價位（無 taker 成本，付 maker fee）。持有 N∈{1,2,3,5} 日，於收盤平倉
    （另有 target-vs-close 變體）。

  假說：每日跌幅分佈的尾部存在恐慌過度反應，其反彈幅度遠大於 4bp maker RT 成本。

  本檔只產出誠實證據（最終 verdict 屬 QC/MIT），絕不 hype。三個它會死的方式
  （mandate 要求 ruthless 對待，全部硬打）：
    (1) alpha-vs-beta：反彈是不是只是 BTC 也一起反彈（=beta-timing 非 alpha）。
        對 BTC 同窗前向報酬回歸，報 beta + 截距(alpha) + t；bull/down 鏡像。
    (2) falling-knife tail：進場後資產繼續崩（甚至歸零/下市）= 近-全損，必計入不可丟。
        報完整 outcome 分佈（含 losers）、CVaR(5%)、worst single trade、大虧比例、
        策略 maxDD。違反 Root Principle 5（尾部炸帳戶）即不可接受。
    (3) capacity/rarity：fill 事件多稀有（稀有尾部=低容量）。

  資料源（皆 ADR 允許 read-only；Bybit 仍唯一執行所）：
    - market.klines timeframe='1d'（唯一 CLEAN 資料集，PG 反射證 0 NULL turnover /
      0 non-positive price / 0 missing-day gap）。LOW/HIGH 乾淨 → 「限價是否成交」
      （當日 low <= 進場價）的判定可信。intraday klines 已知壞，**絕不碰**。
    - market.funding_rates（多日持有期 long 付 funding；僅 ~2026-04 起 ~2 個月覆蓋，
      kline 跨 ~2yr → 多數歷史窗無 funding，conservatively 缺值以 0 或保守上界處理，
      report 內明標）。

  存活/falling-knife 鐵則（#1 讓本策略假性看好的方式）：
    - 若進場資產之後停止交易（kline 斷尾）或崩到 ~0 → 該筆=近-全損，必須計入，
      絕不靜默丟棄。本檔對「持有期內 kline 缺日」與「下市（last bar 早於全域窗末）」
      顯式處理：exit 取持有期內最後一根真實 close；若資產在持有期間徹底停更，
      以最後可得 close 結算（資產真歸零則反映為大幅負報酬）。
    - 誠實揭露：本 26-symbol universe 由「存活兩年的大-cap」構成 → 結構性 survivor-
      biased。report 明標此偏差會讓 bounce 偏樂觀（無真下市/歸零事件落在窗內）。

  leak-free 鐵則：
    - 進場價位 = prior_close*(1-K)，prior_close 是 t-1 已知（PIT，無前視）。
    - fill 條件 = 當日 intraday low <= 進場價位（同日實現，fill 判定不前視——
      進場「價位」是 t-1 預掛的常數，非用當日 low 反推）。
    - 退出 = t+N 收盤（未來，被量測的 target；持有期報酬是被測量）。
    - regime 標籤用 leak-free PIT：BTC 趨勢用 t 之前的 trailing 報酬（shift），
      禁 current-bar rolling（會 mean-revert 偽裝）。
    - naive vs leak-free 並列（本設計進場 level 天生 PIT，naive 對照=用「同日 low
      當進場價」的污染版，證明若用未來 low 反推會多漂亮 → 量化前視污染幅度）。

硬邊界（R-0 隔離紅線，mirror variance_risk_premium / order_flow_alpha）：
  - 純讀：PG 連線 set_session(readonly=True)，只 SELECT market.klines / funding_rates；
    0 寫 PG、0 order path、0 auth/lease/risk 觸碰、0 production code 改動。
  - 零生產模組 import。
  - net 計算保守：maker 進場 2bp/side、退出 model 兩種（maker-rest 2bp / taker 5.5bp），
    funding over hold；禁任何 rebate（無 venue 提供）。
  - artifact root 禁硬編碼：${OPENCLAW_DATA_DIR:-/tmp/openclaw}/ 推導。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
from typing import Any, Optional

SCREEN_VERSION = "tail_dislocation_meanrev.screen.v0.1"

# ---------------------------------------------------------------------------
# 常數（mandate-critical：cost-wall 標尺、K 閾、持有期、leak-free 窗）
# ---------------------------------------------------------------------------

# K：prior_close 下方多少 % 掛 maker BUY（只在 flash-crash 觸及才成交）。
K_THRESHOLDS = (0.08, 0.10, 0.15, 0.20)
# N：持有日數（t+N 收盤平倉）。
HOLD_DAYS = (1, 2, 3, 5)

# 成本（保守零售，bp，禁 rebate）。
MAKER_FEE_BPS = 2.0      # maker 每側
TAKER_FEE_BPS = 5.5      # taker 每側（退出走 market 時）
# 進場永遠 maker（限價靜掛）。退出兩種建模：maker-rest（再 +2bp）或 taker（+5.5bp）。

# 4bp maker RT 成本牆（進場 maker 2bp + 退出 maker 2bp）。net 須顯著高於此。
MAKER_RT_BPS = MAKER_FEE_BPS * 2.0

# crash regime 定義：進場日當日 BTC 報酬 < 此（用於 alpha-vs-beta down 鏡像）。
BTC_CRASH_RET = -0.03
# leak-free PIT BTC 趨勢窗（用 t 之前 trailing 報酬定 regime）。
BTC_TREND_LOOKBACK_D = 5

# 區塊 bootstrap：重疊事件 + 同日多 symbol → 用 block bootstrap 修正 t-stat。
BLOCK_BOOTSTRAP_N = 5000
# 區塊長度（日）：吸收持有期重疊自相關（取最大 hold 的 ~倍數）。
BLOCK_LEN_DAYS = 5

# CVaR 尾部比例。
CVAR_ALPHA = 0.05

# 「大虧」門檻：單筆報酬 < 此視為 large loss（資產續崩）。
LARGE_LOSS_THRESHOLD = -0.10


# ---------------------------------------------------------------------------
# PG 連線（read-only，mirror variance_risk_premium.connect_pg）
# ---------------------------------------------------------------------------

def connect_pg():
    """psycopg2 read-only 連線。

    憑證解析序（皆 libpq / env，禁硬編 user）：
      1. OPENCLAW_DATABASE_URL（若設）。
      2. 否則空 DSN（libpq 讀 PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE / .pgpass）。
    set_session(readonly=True)：結構性禁寫，任何 INSERT/UPDATE 被 PG 拒絕（fail-loud）。
    """
    import psycopg2

    dsn = os.environ.get("OPENCLAW_DATABASE_URL", "")
    conn = psycopg2.connect(dsn) if dsn else psycopg2.connect("")
    conn.set_session(readonly=True)
    return conn


def load_1d_klines(conn, symbol: str) -> list[dict[str, Any]]:
    """讀 market.klines timeframe='1d' 的 (date, OHLC, turnover)，按日升序。

    為什麼只 1d：intraday klines 已知壞，1d 是唯一 CLEAN（PG 反射證 0 NULL turnover /
    0 non-positive / 0 missing-day gap）。SQL 全參數化。open_ts_ms 是 bar-open
    （UTC 當日 00:00），用它定 bar 日期。
    """
    rows: list[dict[str, Any]] = []
    with conn.cursor() as cur:
        cur.execute(
            "SELECT open_ts_ms, open, high, low, close, turnover "
            "FROM market.klines WHERE timeframe='1d' AND symbol=%s "
            "ORDER BY open_ts_ms ASC",
            (symbol,),
        )
        for open_ts_ms, o, h, l, c, turn in cur.fetchall():
            d = dt.datetime.fromtimestamp(int(open_ts_ms) / 1000, dt.timezone.utc).date()
            rows.append({
                "date": d.isoformat(),
                "open": float(o), "high": float(h), "low": float(l), "close": float(c),
                "turnover": float(turn) if turn is not None else None,
            })
    return rows


def list_symbols(conn) -> list[str]:
    """市場 1d kline 全 symbol（升序）。"""
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT symbol FROM market.klines WHERE timeframe='1d' ORDER BY symbol ASC")
        return [r[0] for r in cur.fetchall()]


def load_funding_daily(conn) -> dict[str, dict[str, float]]:
    """讀 market.funding_rates，聚成 per-(symbol, date) 的日 funding（保守取當日均值）。

    Bybit funding 每 8h 結算，long 在 funding_rate>0 時付費。本檔以日為粒度
    （持有期日層結算），用 funding_rate_daily（已是日化）當日均值近似。
    僅 ~2 個月覆蓋 → 多數歷史窗回 0（缺值），report 明標。
    """
    out: dict[str, dict[str, float]] = {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT symbol, (ts AT TIME ZONE 'UTC')::date AS d, avg(funding_rate_daily) "
            "FROM market.funding_rates GROUP BY symbol, (ts AT TIME ZONE 'UTC')::date"
        )
        for sym, d, frd in cur.fetchall():
            if frd is None:
                continue
            out.setdefault(sym, {})[d.isoformat()] = float(frd)
    return out


# ---------------------------------------------------------------------------
# 統計工具
# ---------------------------------------------------------------------------

def _mean(xs: list[float]) -> Optional[float]:
    return (sum(xs) / len(xs)) if xs else None


def _median(xs: list[float]) -> Optional[float]:
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def _stddev(xs: list[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return math.sqrt(var) if var >= 0 else None


def _percentile(xs: list[float], q: float) -> Optional[float]:
    if not xs:
        return None
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    idx = q * (len(s) - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return s[lo]
    frac = idx - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def _cvar(xs: list[float], alpha: float) -> Optional[float]:
    """CVaR(alpha)：最差 alpha 尾部的平均（expected shortfall）。"""
    if not xs:
        return None
    s = sorted(xs)
    k = max(1, int(math.ceil(alpha * len(s))))
    return sum(s[:k]) / k


def _block_bootstrap_tstat(xs: list[float], *, block_len: int, n_boot: int, seed: int) -> dict[str, Any]:
    """重疊事件 → moving-block bootstrap 修正 t-stat（per-caller 獨立 seed）。

    為什麼：fill 事件逐日重疊 + 同日多 symbol 同向 → 樣本高度自相關，naive t-stat
    （sqrt(n)/se）誇大顯著性。block bootstrap 以區塊重採樣保留自相關結構。
    """
    import random

    n = len(xs)
    if n < block_len + 1:
        return {"mean": _mean(xs), "boot_t": None, "ci95": [None, None], "n": n, "method": "insufficient"}
    rng = random.Random(seed)
    obs_mean = sum(xs) / n
    n_blocks = math.ceil(n / block_len)
    means: list[float] = []
    for _ in range(n_boot):
        sample: list[float] = []
        for _ in range(n_blocks):
            start = rng.randint(0, n - block_len)
            sample.extend(xs[start:start + block_len])
        sample = sample[:n]
        means.append(sum(sample) / len(sample))
    boot_sd = _stddev(means)
    boot_t = (obs_mean / boot_sd) if (boot_sd and boot_sd > 0) else None
    return {
        "mean": obs_mean, "boot_se": boot_sd, "boot_t": boot_t,
        "ci95": [_percentile(means, 0.025), _percentile(means, 0.975)],
        "n": n, "n_boot": n_boot, "block_len": block_len, "method": "moving_block_bootstrap",
    }


def _ols(y: list[float], x: list[float]) -> dict[str, Any]:
    """簡單 OLS y = a + b*x，回 alpha(截距)/beta/兩者 t-stat/R²。

    用於 alpha-vs-beta：y=策略前向報酬，x=BTC 同窗前向報酬。
    截距(a)=beta 中性後的 alpha；b=對 BTC 的 beta 載荷。
    """
    n = len(y)
    if n < 3 or len(x) != n:
        return {"alpha": None, "beta": None, "alpha_t": None, "beta_t": None, "r2": None, "n": n}
    mx = sum(x) / n
    my = sum(y) / n
    sxx = sum((xi - mx) ** 2 for xi in x)
    if sxx <= 0:
        return {"alpha": None, "beta": None, "alpha_t": None, "beta_t": None, "r2": None, "n": n}
    sxy = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    beta = sxy / sxx
    alpha = my - beta * mx
    resid = [y[i] - (alpha + beta * x[i]) for i in range(n)]
    sse = sum(r * r for r in resid)
    sst = sum((yi - my) ** 2 for yi in y)
    r2 = (1 - sse / sst) if sst > 0 else None
    if n > 2:
        sigma2 = sse / (n - 2)
        se_beta = math.sqrt(sigma2 / sxx) if sxx > 0 else None
        se_alpha = math.sqrt(sigma2 * (1.0 / n + mx * mx / sxx)) if sxx > 0 else None
        beta_t = (beta / se_beta) if (se_beta and se_beta > 0) else None
        alpha_t = (alpha / se_alpha) if (se_alpha and se_alpha > 0) else None
    else:
        beta_t = alpha_t = None
    return {"alpha": alpha, "beta": beta, "alpha_t": alpha_t, "beta_t": beta_t, "r2": r2, "n": n}


# ---------------------------------------------------------------------------
# 事件生成（leak-free 進場 + survivorship-correct 退出）
# ---------------------------------------------------------------------------

def build_events(
    klines_by_sym: dict[str, list[dict[str, Any]]],
    funding: dict[str, dict[str, float]],
    btc_fwd_ret: dict[tuple[int, str], float],  # (hold_days, date)->BTC 同窗前向報酬
    btc_trend: dict[str, Optional[str]],         # date(entry)->'up'/'down'/'chop'（PIT）
    *,
    k: float,
    hold: int,
) -> list[dict[str, Any]]:
    """對單一 (K, N) 生成所有 fill 事件。

    進場（leak-free）：對每個 entry-day t（有 prior_close），進場價位 =
      prior_close*(1-k)。fill 條件 = klines[t].low <= 進場價位。
    退出（survivorship-correct）：取 t 之後第 N 根真實 kline 的 close。
      若資產在持有期間斷尾（少於 N 根後續 bar）→ 用「最後可得 close」結算
      （falling-knife：資產停更/歸零反映為實際報酬，不丟棄）。
      target-vs-close 變體：target = 進場價*(1+k)（回到 prior_close 附近），
      若持有期內任一日 high >= target 則以 target 退出（先到先平），否則收盤退。

    回每筆事件 dict：含 entry/exit 價、gross/net 報酬（maker/taker exit）、
    funding、是否斷尾、BTC 同窗報酬、entry-day BTC regime。
    """
    events: list[dict[str, Any]] = []
    for sym, ks in klines_by_sym.items():
        sym_fund = funding.get(sym, {})
        n_bars = len(ks)
        for i in range(1, n_bars):
            prior_close = ks[i - 1]["close"]
            if prior_close <= 0:
                continue
            entry_level = prior_close * (1.0 - k)
            day = ks[i]
            if day["low"] > entry_level:
                continue  # 未觸及，不成交
            entry_date = day["date"]
            # --- 退出：survivorship-correct ---
            # 後續可得 bar（從 entry-day 之後）。
            future = ks[i + 1: i + 1 + hold]
            truncated = len(future) < hold
            # exit-at-close：取持有期內最後一根真實 close（斷尾則為最後可得）。
            if future:
                exit_close_bar = future[-1]
            else:
                # 進場後再無 bar（資產立即斷尾）→ 用進場當日 close 結算（保守，
                # 反映「無法再持有」的近-即時平倉；若資產真歸零，close 反映之）。
                exit_close_bar = day
            exit_close = exit_close_bar["close"]
            # target-vs-close 變體：target = entry_level*(1+k)。
            target_price = entry_level * (1.0 + k)
            exit_target_price = exit_close  # 預設未達 target → 收盤退
            target_hit = False
            for b in future:
                if b["high"] >= target_price:
                    exit_target_price = target_price
                    target_hit = True
                    break

            # --- gross 報酬（long：買在 entry_level，賣在 exit）---
            gross_close = exit_close / entry_level - 1.0
            gross_target = exit_target_price / entry_level - 1.0

            # --- funding（多日 long 付費；缺值=0，report 標）---
            # 持有期每日（entry_date..exit_date）long 付 funding_rate_daily（>0 付費，
            # <0 收取）。long 成本 = sum(funding_rate_daily)（正=付）。
            fund_days = [entry_date] + [b["date"] for b in future]
            fund_sum = 0.0
            fund_known = 0
            for fd in fund_days:
                if fd in sym_fund:
                    fund_sum += sym_fund[fd]
                    fund_known += 1
            # long 報酬扣 funding（付正 funding 減損）。
            funding_drag = fund_sum  # 直接是報酬空間的減項（正 funding = long 付）

            # --- net（兩種退出建模）---
            entry_cost = MAKER_FEE_BPS / 1e4
            exit_cost_maker = MAKER_FEE_BPS / 1e4
            exit_cost_taker = TAKER_FEE_BPS / 1e4
            net_close_maker = gross_close - entry_cost - exit_cost_maker - funding_drag
            net_close_taker = gross_close - entry_cost - exit_cost_taker - funding_drag
            net_target_maker = gross_target - entry_cost - exit_cost_maker - funding_drag
            net_target_taker = gross_target - entry_cost - exit_cost_taker - funding_drag

            events.append({
                "symbol": sym, "entry_date": entry_date,
                "exit_date": exit_close_bar["date"],
                "k": k, "hold": hold,
                "prior_close": prior_close, "entry_level": entry_level,
                "exit_close": exit_close, "target_price": target_price,
                "target_hit": target_hit,
                "truncated": truncated, "n_future_bars": len(future),
                "gross_close": gross_close, "gross_target": gross_target,
                "net_close_maker": net_close_maker, "net_close_taker": net_close_taker,
                "net_target_maker": net_target_maker, "net_target_taker": net_target_taker,
                "funding_drag": funding_drag, "funding_known_days": fund_known,
                "funding_total_days": len(fund_days),
                "btc_fwd_ret": btc_fwd_ret.get((hold, entry_date)),
                "btc_regime": btc_trend.get(entry_date),
                # naive 污染對照：若用「同日 low」當進場價（前視），bounce 看多漂亮。
                "entry_low_naive": day["low"],
                "gross_close_naive": (exit_close / day["low"] - 1.0) if day["low"] > 0 else None,
            })
    return events


# ---------------------------------------------------------------------------
# 聚合 / 三 kill 分析
# ---------------------------------------------------------------------------

def summarize_returns(rets: list[float], *, seed: int) -> dict[str, Any]:
    """gross/net 報酬分佈 + block-bootstrap t + 完整尾部（CVaR、worst、大虧比例）。"""
    if not rets:
        return {"n": 0}
    pos = sum(1 for r in rets if r > 0)
    boot = _block_bootstrap_tstat(rets, block_len=BLOCK_LEN_DAYS, n_boot=BLOCK_BOOTSTRAP_N, seed=seed)
    # naive t（不修重疊，用於對照誇大幅度）。
    sd = _stddev(rets)
    naive_t = (_mean(rets) / (sd / math.sqrt(len(rets)))) if (sd and sd > 0) else None
    large_losses = sum(1 for r in rets if r < LARGE_LOSS_THRESHOLD)
    return {
        "n": len(rets),
        "mean": _mean(rets), "median": _median(rets),
        "pct_positive": pos / len(rets),
        "std": sd,
        "naive_t": naive_t,
        "block_bootstrap": boot,
        "min": min(rets), "max": max(rets),
        "p05": _percentile(rets, 0.05), "p25": _percentile(rets, 0.25),
        "p75": _percentile(rets, 0.75), "p95": _percentile(rets, 0.95),
        "cvar05": _cvar(rets, CVAR_ALPHA),
        "worst_single": min(rets),
        "large_loss_count": large_losses,
        "large_loss_pct": large_losses / len(rets),
    }


def equity_max_drawdown(events: list[dict[str, Any]], *, ret_key: str) -> dict[str, Any]:
    """以時間排序的等權「逐筆」報酬序列估 maxDD（近似：事件按 entry_date 排序，
    每筆貢獻 ret 到累積 log-equity）。

    為什麼用 log-equity 累加：策略是逐筆 all-in 等-notional（如 feedback_position_
    sizing 3% risk/trade），近似把每筆報酬視為 equity 的乘法步進。這是「全押單一
    事件」的悲觀界（同日多事件未分散），report 標為近似上界。
    """
    if not events:
        return {"max_drawdown": None, "final_log_equity": None, "n": 0}
    seq = sorted(events, key=lambda e: (e["entry_date"], e["symbol"]))
    log_eq = 0.0
    peak = 0.0
    max_dd = 0.0
    for e in seq:
        r = e[ret_key]
        if r is None:
            continue
        # clamp 報酬下界 -0.99（資產近歸零=近全損，避免 log 爆掉）。
        r_clamped = max(r, -0.99)
        log_eq += math.log1p(r_clamped)
        peak = max(peak, log_eq)
        dd = 1.0 - math.exp(log_eq - peak)
        max_dd = max(max_dd, dd)
    return {"max_drawdown": max_dd, "final_log_equity": log_eq, "n": len(seq)}


def alpha_vs_beta(events: list[dict[str, Any]], *, ret_key: str) -> dict[str, Any]:
    """DECISIVE kill #1：策略前向報酬對 BTC 同窗前向報酬回歸。

    若 alpha(截距)≈0 且 beta>0 顯著 → bounce 主要是 BTC 也反彈（beta-timing 非 alpha）。
    bull/down 鏡像：分別在 entry-day BTC 上漲/下跌 regime 子集回歸；若 edge 只在 BTC
    也反彈（up regime）出現 = beta-timing 確證。
    """
    pairs = [(e[ret_key], e["btc_fwd_ret"]) for e in events
             if e[ret_key] is not None and e["btc_fwd_ret"] is not None]
    if len(pairs) < 3:
        return {"overall": {"n": len(pairs), "note": "insufficient"}}
    y = [p[0] for p in pairs]
    x = [p[1] for p in pairs]
    overall = _ols(y, x)
    # 鏡像：BTC 同窗前向報酬 > 0（BTC 也反彈）vs <= 0（BTC 沒反彈/續跌）。
    up = [(p[0], p[1]) for p in pairs if p[1] > 0]
    dn = [(p[0], p[1]) for p in pairs if p[1] <= 0]
    res_up = summarize_returns([p[0] for p in up], seed=101) if up else {"n": 0}
    res_dn = summarize_returns([p[0] for p in dn], seed=102) if dn else {"n": 0}
    return {
        "overall": overall,
        "strat_ret_when_btc_up": {"n": len(up), "mean": _mean([p[0] for p in up]) if up else None,
                                   "pct_positive": (sum(1 for p in up if p[0] > 0) / len(up)) if up else None},
        "strat_ret_when_btc_down": {"n": len(dn), "mean": _mean([p[0] for p in dn]) if dn else None,
                                     "pct_positive": (sum(1 for p in dn if p[0] > 0) / len(dn)) if dn else None},
        "btc_up_subset_full": res_up,
        "btc_down_subset_full": res_dn,
        "interpretation_hint": (
            "alpha≈0 & beta>0顯著 → beta-timing非alpha；若僅 btc_up 子集為正 → 確證 beta-timing"
        ),
    }


def regime_split(events: list[dict[str, Any]], *, ret_key: str) -> dict[str, Any]:
    """kill #1 補強：leak-free PIT BTC 趨勢 regime 切（up/down/chop）。

    edge 集中在 bull/recovery（beta）還是 down regime 也成立（真 alpha）。
    """
    out: dict[str, Any] = {}
    for reg in ("up", "down", "chop", None):
        rs = [e[ret_key] for e in events if e["btc_regime"] == reg and e[ret_key] is not None]
        label = reg if reg is not None else "unknown_regime"
        out[label] = summarize_returns(rs, seed=hash(("regime", label)) % (2**31)) if rs else {"n": 0}
    return out


# ---------------------------------------------------------------------------
# BTC 前向報酬 + PIT regime 預算
# ---------------------------------------------------------------------------

def build_btc_helpers(btc_ks: list[dict[str, Any]]) -> tuple[dict[tuple[int, str], float], dict[str, Optional[str]]]:
    """預算 (1) BTC 同窗 N-日前向 close-close 報酬 by (hold, date)；
    (2) entry-day 的 PIT BTC 趨勢 regime（用 t 之前 trailing 報酬，leak-free）。

    btc_fwd_ret[(N, date_t)] = BTC close[t+N]/close[t] - 1（與策略同窗）。
    regime[date_t]：trailing BTC_TREND_LOOKBACK_D 日報酬（close[t-1]/close[t-1-L]-1，
      全用 ≤t-1 資訊）；>+2% up / <-2% down / 其餘 chop。
    """
    by_date = {b["date"]: idx for idx, b in enumerate(btc_ks)}
    fwd: dict[tuple[int, str], float] = {}
    regime: dict[str, Optional[str]] = {}
    n = len(btc_ks)
    for idx, b in enumerate(btc_ks):
        d = b["date"]
        c0 = b["close"]
        for hold in HOLD_DAYS:
            j = idx + hold
            if j < n and c0 > 0:
                fwd[(hold, d)] = btc_ks[j]["close"] / c0 - 1.0
        # PIT regime：用 ≤ t-1 的 trailing 報酬（shift，禁 current-bar）。
        ti = idx - 1  # t-1
        bi = ti - BTC_TREND_LOOKBACK_D
        if ti >= 0 and bi >= 0 and btc_ks[bi]["close"] > 0:
            tr = btc_ks[ti]["close"] / btc_ks[bi]["close"] - 1.0
            regime[d] = "up" if tr > 0.02 else ("down" if tr < -0.02 else "chop")
        else:
            regime[d] = None
    return fwd, regime


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def run_screen(conn) -> dict[str, Any]:
    symbols = list_symbols(conn)
    klines_by_sym: dict[str, list[dict[str, Any]]] = {s: load_1d_klines(conn, s) for s in symbols}
    funding = load_funding_daily(conn)

    # 資料品質 / survivorship 盤點。
    global_last = max((ks[-1]["date"] for ks in klines_by_sym.values() if ks), default=None)
    dq: dict[str, Any] = {"symbols": [], "global_last_day": global_last}
    for s in symbols:
        ks = klines_by_sym[s]
        if not ks:
            continue
        dates = [b["date"] for b in ks]
        span_days = (dt.date.fromisoformat(dates[-1]) - dt.date.fromisoformat(dates[0])).days + 1
        nonpos = sum(1 for b in ks if min(b["open"], b["high"], b["low"], b["close"]) <= 0)
        # 下市偵測：last bar 早於全域窗末 > 7 天 = 可能下市（dead symbol）。
        delisted = (global_last is not None
                    and (dt.date.fromisoformat(global_last) - dt.date.fromisoformat(dates[-1])).days > 7)
        dq["symbols"].append({
            "symbol": s, "bars": len(ks), "first_day": dates[0], "last_day": dates[-1],
            "span_days": span_days, "missing_days": span_days - len(ks),
            "min_low": min(b["low"] for b in ks), "nonpos_bars": nonpos,
            "possibly_delisted": delisted,
        })

    btc_ks = klines_by_sym.get("BTCUSDT", [])
    btc_fwd, btc_regime = build_btc_helpers(btc_ks)

    funding_cov = {
        "funding_symbols": len(funding),
        "funding_total_daily_rows": sum(len(v) for v in funding.values()),
    }

    grid: list[dict[str, Any]] = []
    event_frequency: dict[str, Any] = {}
    span_years = None
    if global_last and klines_by_sym:
        first_day = min((ks[0]["date"] for ks in klines_by_sym.values() if ks))
        span_years = (dt.date.fromisoformat(global_last) - dt.date.fromisoformat(first_day)).days / 365.0

    for k in K_THRESHOLDS:
        for hold in HOLD_DAYS:
            events = build_events(klines_by_sym, funding, btc_fwd, btc_regime, k=k, hold=hold)
            n_events = len(events)
            seed_base = int(k * 1000) * 100 + hold
            cell: dict[str, Any] = {
                "k": k, "hold": hold, "n_events": n_events,
                "n_truncated": sum(1 for e in events if e["truncated"]),
            }
            # gross（close 退出 + target 退出）。
            cell["gross_close"] = summarize_returns([e["gross_close"] for e in events], seed=seed_base + 1)
            cell["gross_target"] = summarize_returns([e["gross_target"] for e in events], seed=seed_base + 2)
            cell["target_hit_rate"] = (sum(1 for e in events if e["target_hit"]) / n_events) if n_events else None
            # net（maker/taker exit × close/target）。
            cell["net_close_maker"] = summarize_returns([e["net_close_maker"] for e in events], seed=seed_base + 3)
            cell["net_close_taker"] = summarize_returns([e["net_close_taker"] for e in events], seed=seed_base + 4)
            cell["net_target_maker"] = summarize_returns([e["net_target_maker"] for e in events], seed=seed_base + 5)
            cell["net_target_taker"] = summarize_returns([e["net_target_taker"] for e in events], seed=seed_base + 6)
            # naive 前視污染對照（用同日 low 反推進場價）。
            naive_rets = [e["gross_close_naive"] for e in events if e["gross_close_naive"] is not None]
            cell["gross_close_naive_leak"] = summarize_returns(naive_rets, seed=seed_base + 7)
            # 三 kill。
            cell["alpha_vs_beta_close"] = alpha_vs_beta(events, ret_key="gross_close")
            cell["regime_split_close"] = regime_split(events, ret_key="gross_close")
            cell["maxdd_net_close_maker"] = equity_max_drawdown(events, ret_key="net_close_maker")
            cell["maxdd_gross_close"] = equity_max_drawdown(events, ret_key="gross_close")
            # 容量：per-year 頻率。
            cell["events_per_year"] = (n_events / span_years) if span_years else None
            # funding 覆蓋（本 cell）。
            fk = [e for e in events if e["funding_known_days"] > 0]
            cell["funding_event_coverage_pct"] = (len(fk) / n_events) if n_events else None
            grid.append(cell)
            event_frequency[f"K{int(k*100)}_N{hold}"] = {
                "n_events": n_events, "events_per_year": cell["events_per_year"],
            }

    return {
        "screen_version": SCREEN_VERSION,
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "params": {
            "K_thresholds": list(K_THRESHOLDS), "hold_days": list(HOLD_DAYS),
            "maker_fee_bps": MAKER_FEE_BPS, "taker_fee_bps": TAKER_FEE_BPS,
            "maker_rt_bps": MAKER_RT_BPS, "block_len_days": BLOCK_LEN_DAYS,
            "block_bootstrap_n": BLOCK_BOOTSTRAP_N, "cvar_alpha": CVAR_ALPHA,
            "large_loss_threshold": LARGE_LOSS_THRESHOLD,
            "btc_trend_lookback_d": BTC_TREND_LOOKBACK_D,
        },
        "data_quality": dq,
        "funding_coverage": funding_cov,
        "span_years": span_years,
        "event_frequency": event_frequency,
        "grid": grid,
    }


# ---------------------------------------------------------------------------
# Artifact 寫出
# ---------------------------------------------------------------------------

def _data_root() -> str:
    return os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")


def write_artifact(report: dict[str, Any], *, out_path: Optional[str]) -> str:
    if out_path is None:
        root = os.path.join(_data_root(), "research", "tail_dislocation_meanrev")
        os.makedirs(root, exist_ok=True)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = os.path.join(root, f"tail_dislocation_screen_{stamp}.json")
    else:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    blob = json.dumps(report, indent=2, sort_keys=True, default=str)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(blob)
    sha = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    with open(out_path + ".sha256", "w", encoding="utf-8") as fh:
        fh.write(sha + "  " + os.path.basename(out_path) + "\n")
    return out_path


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="條件式尾部錯位均值回歸篩查（$0 唯讀 OFFLINE research）")
    ap.add_argument("--out", default=None, help="report JSON 路徑（預設 OPENCLAW_DATA_DIR/research/tail_dislocation_meanrev/）")
    args = ap.parse_args(argv)

    conn = connect_pg()
    try:
        report = run_screen(conn)
    finally:
        conn.close()
    out = write_artifact(report, out_path=args.out)

    # 簡明 stdout 摘要（不 hype；數字自己說話）。
    print(f"[{SCREEN_VERSION}] artifact -> {out}")
    print(f"span_years={report['span_years']:.2f} symbols={len(report['data_quality']['symbols'])} "
          f"funding_syms={report['funding_coverage']['funding_symbols']}")
    print("freq (events / events_per_year):")
    for kk, v in report["event_frequency"].items():
        epy = v["events_per_year"]
        print(f"  {kk}: n={v['n_events']} epy={epy:.1f}" if epy is not None else f"  {kk}: n={v['n_events']}")
    print("per-cell read (gross_close mean / net_close_maker mean / net_close_taker mean / boot_t net_maker / alpha / beta):")
    for cell in report["grid"]:
        gc = cell["gross_close"].get("mean")
        ncm = cell["net_close_maker"].get("mean")
        nct = cell["net_close_taker"].get("mean")
        bt = cell["net_close_maker"].get("block_bootstrap", {}).get("boot_t")
        ab = cell["alpha_vs_beta_close"].get("overall", {})
        al = ab.get("alpha")
        be = ab.get("beta")
        alt = ab.get("alpha_t")

        def f(x: Any) -> str:
            return f"{x:.4f}" if isinstance(x, (int, float)) else "None"

        print(f"  K{int(cell['k']*100)}_N{cell['hold']} n={cell['n_events']} "
              f"gross={f(gc)} net_mk={f(ncm)} net_tk={f(nct)} bootT={f(bt)} "
              f"alpha={f(al)}(t={f(alt)}) beta={f(be)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
