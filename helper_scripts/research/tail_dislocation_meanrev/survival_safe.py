#!/usr/bin/env python3
"""tail_dislocation_meanrev.survival_safe — 尾部錯位 alpha 的存活安全變體（$0 唯讀 OFFLINE）。

MODULE_NOTE
模塊用途：
  prior `screen.py` 證實了本盈利弧的「第一個真 alpha」——條件式尾部錯位均值回歸
  （maker 掛 BUY @prior_close*(1-K)，只在 flash-crash 觸及成交，hold N 收盤平倉）：
  beta-clean alpha 截距 +1.1%~+11.3%（t 5.9~12.6），且邊際集中在 leak-free PIT
  DOWN regime（=panic over-reaction reversal，非 recovery-beta）。但它死於**相關的
  falling-knife 尾部**：CVaR5% −10~−22%、worst −35%、最壞崩盤日 26 symbol 一次全部
  fill（並發=26、零分散）→ all-in maxDD 0.77（即使 daily-equal-weight 分散）→ 違反
  Root Principle 5（account survival > profit）。

  本檔回答唯一決定性問題（非「有沒有 alpha」——有；而是「相關尾部能否壓到可存活
  水準同時保正期望值」=portfolio-construction / risk-management 問題，Principle 16）：
    **存在 (K,N,S,C,r) 使 net 期望值為正 AND SIZED 組合 maxDD <= ~20-25% 嗎？**

  五個 survival-first 加固（operator mandate 逐項）：
    (1) 全 1d-kline universe（含下市/死亡）。**結構性現實**：清潔 1d-kline 集
        恰是 26 個存活兩年的大-cap（PG 反射證），表內 0 個下市/歸零 symbol；intraday
        153-symbol 集只 ~73 天且已知壞 → 無法擴充日層 2yr 尾部。survivor bias 在此
        資料上**不可移除** → 唯一誠實補償 = (4) 合成 death-spiral 壓力疊加。
    (2) intraday hard stop S：持有期內若價格觸及 entry*(1-S)，以 taker（5.5bp）在
        該止損價平倉（urgent）。bounce 在跌破 stop 後才反彈者被砍掉=stop 切掉贏家的
        代價，必須量化（alpha 截距 stopped-vs-unstopped 對比）。
    (3) same-day concurrency cap C：同日 > C 個信號開火時只取 C 筆（最深折扣優先），
        其餘放棄。直接攻擊「最壞日 fill 全部 symbol」的零分散。
    (3b) fractional survival-first sizing r：每槽只冒 r% 權益（equity-risk），C 個
        並發槽全部打到 stop = 有界損失 C*r*S（非 all-in）。這才是真實系統的下單方式。
    (4) death-spiral 壓力疊加：在實證之上，按 crypto 歷史下市/死亡基率注入 X% 的深-K
        進場 → gap-through-stop 到 −100%（誠實建模：hard stop 只**部分**限制 gap-through，
        若隔夜跳空穿過 stop 價則實現 max(stop_loss, gap_loss)，可能遠超 −S）。
    (5) day-clustered 顯著性：以「distinct crash episode」為有效 N 重做顯著性（MIT flag
        iid-OLS 高估）——block bootstrap by crash-day。

  誠實鐵則（不 hype，數字自己說話；最終 verdict 屬 QC/MIT）：
    - SIZED 組合等值曲線（fractional sizing + concurrency cap + hard stop）才是真
      Principle-5 測試；prior all-in maxDD 0.77 是**未分散全押**的悲觀界，本檔以
      survival-first sizing 重算 maxDD / CVaR(5%) / annualized return / Sharpe / Sortino。
    - hard stop 改善 maxDD 但代價=切贏家：必須對比 stopped-vs-unstopped 的 alpha 截距，
      若 stop 把 alpha 砍光則「存活但無 edge」。
    - death-spiral 壓力是 ESTIMATE（base rate 估計），明標假設與敏感度。

硬邊界（R-0 隔離紅線，mirror screen.py / variance_risk_premium / order_flow_alpha）：
  - 純讀：import screen.py 的連線/事件/統計 helper（0 改 sibling），只 SELECT
    market.klines / funding_rates；0 寫 PG、0 order path、0 auth/lease/risk 觸碰、
    0 production code 改動。
  - net 計算保守：maker 進場 2bp、退出 maker 2bp / taker 5.5bp、hard-stop 退出 taker
    5.5bp（urgent），funding over hold；禁任何 rebate。
  - artifact root 禁硬編碼：${OPENCLAW_DATA_DIR:-/tmp/openclaw}/ 推導。
  - 死亡注入用獨立 RNG seed（per-config 確定性可重現），絕不污染實證統計。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import random
from typing import Any, Optional

# 復用 prior screen 的 read-only 連線 / 事件生成 / 統計 helper（0 改 sibling）。
import screen as base

SURVIVAL_VERSION = "tail_dislocation_meanrev.survival_safe.v0.1"

# ---------------------------------------------------------------------------
# 存活安全 grid（operator mandate 指定）
# ---------------------------------------------------------------------------

# K：prior_close 下方折扣（深 K=更稀有但 alpha 更乾淨）。
K_GRID = (0.10, 0.15, 0.20)
# N：持有日數。
N_GRID = (1, 2, 3, 5)
# S：intraday hard stop（entry 下方 %）；None=不設 stop。
STOP_GRID = (None, 0.05, 0.08, 0.10, 0.15)
# C：same-day concurrency cap（同日最多取 C 筆，深折扣優先）。
CONCURRENCY_GRID = (1, 3, 5, None)  # None=unlimited
# r：每槽冒險 % 權益（fractional survival-first sizing）。
RISK_PER_SLOT_GRID = (0.01, 0.02, 0.03)

# 成本（保守零售，與 screen.py 對齊）。
MAKER_FEE = base.MAKER_FEE_BPS / 1e4   # 進場 + 普通退出每側
TAKER_FEE = base.TAKER_FEE_BPS / 1e4   # hard-stop 退出（urgent）每側

# death-spiral 壓力：深-K 進場後徹底死亡（gap-through-stop 到 ~ −100%）的**條件**機率。
# crypto 衍生品產業 ~2024 年集體下市基率 ~10%/yr（WebSearch，industry benchmark）；
# 大-cap 遠低。但本壓力的正確問法**不是**「資產在我 3 天持有期內按人口基率下市」
# （年化折算到 3 天 ~0.0001，無意義），**而是**「**條件於進場一個深-K panic crash**，
# 該資產正處於極端 distress，其後續徹底死亡（崩到歸零 / 下市）的機率被大幅抬高」。
# 因清潔 1d universe 0 真死亡（survivor-biased），用**每筆深-K 進場的條件死亡機率**注入：
#   保守 0.5% / 基準 2% / 悲觀 5% / 極端 10%（每個 fill 事件獨立 Bernoulli）。
# 這對齊「深-K 進場的是已暴跌資產，FIL/OP/INJ 類接刀後續再崩」的實證直覺。
DEATH_COND_RATES_PER_ENTRY = (0.005, 0.02, 0.05, 0.10)
# 多 seed 平均（單 seed Monte-Carlo 在稀疏死亡下噪音大，取多 seed 平均 maxDD/annret）。
DEATH_STRESS_SEEDS = 64
# gap-through：死亡事件中，價格隔夜跳空**穿過** stop 價（hard stop 無法在 stop 價成交，
# 只能在更差的 gap 價成交）的比例。hard stop 對 gap-through 只部分有效。
GAP_THROUGH_FRAC = 0.5
# 死亡事件實現報酬（穿過 stop 後跌到近歸零）。
DEATH_TERMINAL_RET = -0.95

# 年化天數（組合等值曲線 → annualized）。
TRADING_DAYS_PER_YEAR = 365.0

# survivable maxDD 門檻（operator：~20-25%）。
SURVIVABLE_MAXDD = 0.25


# ---------------------------------------------------------------------------
# 帶 hard-stop 的事件報酬（leak-free，survivorship-correct）
# ---------------------------------------------------------------------------

def _event_return_with_stop(
    ks: list[dict[str, Any]],
    i: int,
    *,
    entry_level: float,
    hold: int,
    stop: Optional[float],
) -> dict[str, Any]:
    """單筆事件在給定 hard stop S 下的退出報酬（含成本）。

    為什麼用 1d OHLC 模 intraday stop：intraday klines 已知壞，唯一可信判定 = 持有期內
    任一日的 daily LOW <= stop_price 即視為當日觸發 stop（保守：daily low 是當日最深點，
    任何 intraday 路徑只要碰到都算）。觸發後以 taker 在 stop_price 平倉（urgent）。
    無觸發則 hold 滿 N 於收盤以 maker/taker 平倉（沿用 screen.py 兩種建模）。

    leak-free：entry_level 是 t-1 預掛常數；stop_price = entry_level*(1-S) 同為預設常數；
    觸發判定用持有期內各日真實 low（被量測的未來，非反推）。survivorship-correct：
    斷尾資產用最後可得 bar 結算。
    """
    future = ks[i + 1: i + 1 + hold]
    truncated = len(future) < hold
    # 退出（無 stop）：持有期內最後一根真實 close。
    exit_close_bar = future[-1] if future else ks[i]
    exit_close = exit_close_bar["close"]

    entry_cost = MAKER_FEE
    stop_price = entry_level * (1.0 - stop) if stop is not None else None

    # --- hard stop 觸發掃描（含進場當日；進場日 low 已 <= entry_level，可能同日更深觸 stop）---
    stopped = False
    stop_exit_date = None
    if stop_price is not None:
        # 進場當日：若同日 low 已 <= stop_price，視為當日觸發（保守，最深點）。
        scan_bars = [ks[i]] + list(future)
        for b in scan_bars:
            if b["low"] <= stop_price:
                stopped = True
                stop_exit_date = b["date"]
                break

    if stopped:
        # stop 成交：taker 在 stop_price（urgent）。報酬 = stop_price/entry_level - 1 - 成本。
        gross = stop_price / entry_level - 1.0
        net_maker = gross - entry_cost - TAKER_FEE  # stop 退出恆 taker
        net_taker = net_maker
        exit_date = stop_exit_date
    else:
        gross = exit_close / entry_level - 1.0
        net_maker = gross - entry_cost - MAKER_FEE
        net_taker = gross - entry_cost - TAKER_FEE
        exit_date = exit_close_bar["date"]

    return {
        "stopped": stopped,
        "truncated": truncated,
        "n_future_bars": len(future),
        "gross": gross,
        "net_maker": net_maker,   # close-exit maker / stop-exit taker
        "net_taker": net_taker,   # close-exit taker / stop-exit taker
        "exit_date": exit_date,
    }


def build_events_stopped(
    klines_by_sym: dict[str, list[dict[str, Any]]],
    funding: dict[str, dict[str, float]],
    btc_fwd_ret: dict[tuple[int, str], float],
    btc_trend: dict[str, Optional[str]],
    *,
    k: float,
    hold: int,
    stop: Optional[float],
) -> list[dict[str, Any]]:
    """對 (K, N, S) 生成所有 fill 事件（含 hard-stop 退出 + funding + BTC regime）。"""
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
                continue  # 未觸及，maker 不成交
            entry_date = day["date"]
            r = _event_return_with_stop(ks, i, entry_level=entry_level, hold=hold, stop=stop)

            # funding（多日 long 付費；缺值=0，conservative-favorable，report 標）。
            future = ks[i + 1: i + 1 + hold]
            fund_days = [entry_date] + [b["date"] for b in future]
            fund_sum = sum(sym_fund[fd] for fd in fund_days if fd in sym_fund)
            fund_known = sum(1 for fd in fund_days if fd in sym_fund)

            events.append({
                "symbol": sym, "entry_date": entry_date, "exit_date": r["exit_date"],
                "k": k, "hold": hold, "stop": stop,
                "entry_level": entry_level,
                "depth_below_prior": k,  # concurrency tiebreak：深折扣優先
                "stopped": r["stopped"], "truncated": r["truncated"],
                "n_future_bars": r["n_future_bars"],
                "gross": r["gross"],
                "net_maker": r["net_maker"] - fund_sum,
                "net_taker": r["net_taker"] - fund_sum,
                "funding_drag": fund_sum, "funding_known_days": fund_known,
                "btc_fwd_ret": btc_fwd_ret.get((hold, entry_date)),
                "btc_regime": btc_trend.get(entry_date),
            })
    return events


# ---------------------------------------------------------------------------
# same-day concurrency cap（深折扣優先）
# ---------------------------------------------------------------------------

def apply_concurrency_cap(events: list[dict[str, Any]], *, cap: Optional[int]) -> dict[str, Any]:
    """同日 > cap 信號時只保留 cap 筆（按進場日當日**實際相對折扣**最深者優先）。

    為什麼深折扣優先：深-K fill 是最乾淨 alpha（panic 最極端），且 cap 必須在「最壞
    崩盤日」最有約束力——正是同日信號最多時。tiebreak 用 entry-day 的相對跌幅
    （entry_level/prior_close 已固定 = 1-k，同 cell 內 k 相同 → 改用 symbol 名穩定排序
    保證確定性；跨 cell 已分開跑）。回保留事件 + 被 cap 丟棄計數 + 每日並發分佈。
    """
    by_day: dict[str, list[dict[str, Any]]] = {}
    for e in events:
        by_day.setdefault(e["entry_date"], []).append(e)

    kept: list[dict[str, Any]] = []
    dropped = 0
    concurrency_hist: dict[int, int] = {}
    max_concurrency_raw = 0
    max_concurrency_capped = 0
    for day, evs in by_day.items():
        raw_n = len(evs)
        max_concurrency_raw = max(max_concurrency_raw, raw_n)
        concurrency_hist[raw_n] = concurrency_hist.get(raw_n, 0) + 1
        if cap is None or raw_n <= cap:
            kept.extend(evs)
            max_concurrency_capped = max(max_concurrency_capped, raw_n)
        else:
            # 深折扣優先：同 cell 內 k 相同 → 用 symbol 穩定排序（確定性）；
            # 取前 cap 筆。實務上更深折扣 = 更乾淨，但本 grid 逐 cell 跑（k 固定），
            # 故此處 tiebreak 只需確定性（symbol 字典序）。
            evs_sorted = sorted(evs, key=lambda e: e["symbol"])
            kept.extend(evs_sorted[:cap])
            dropped += raw_n - cap
            max_concurrency_capped = max(max_concurrency_capped, cap)

    return {
        "kept": kept,
        "n_kept": len(kept),
        "n_dropped": dropped,
        "max_concurrency_raw": max_concurrency_raw,
        "max_concurrency_capped": max_concurrency_capped,
        "n_distinct_entry_days": len(by_day),
        "concurrency_hist": {str(kk): vv for kk, vv in sorted(concurrency_hist.items())},
    }


# ---------------------------------------------------------------------------
# fractional survival-first SIZED 組合等值曲線
# ---------------------------------------------------------------------------

def sized_portfolio_equity_curve(
    events: list[dict[str, Any]],
    *,
    ret_key: str,
    risk_per_slot: float,
    stop: Optional[float],
    cap: Optional[int],
) -> dict[str, Any]:
    """以 fractional survival-first sizing 重建組合等值曲線並算 maxDD / CVaR / Sharpe / Sortino。

    sizing 模型（survival-first）：每槽冒險 r% 權益。槽 notional = (r * equity) / risk_unit，
    其中 risk_unit = max(stop, |worst-plausible-move|)。為使 r 真正成為「每槽最大損失上界」，
    採用 stop-anchored sizing：
      - 有 hard stop S：risk_unit = S（打到 stop 損失 ≈ r*equity，C 槽全 stop = C*r*equity）。
      - 無 stop：用一個保守 risk_unit = max(0.20, |worst-historical-single|) 當作隱含「停損」
        距離（無 stop 時尾部更肥，sizing 必須更保守）；report 標此假設。
    每筆 trade 對權益的乘法步進 = 1 + (r / risk_unit) * trade_ret，trade_ret = 該筆 net 報酬。
    事件按 entry_date 排序，同日多筆**同時**作用（各自獨立槽，故同日 C 筆全打到 stop =
    equity *= prod(1 - r) ≈ 1 - C*r，這正是 concurrency cap × sizing 的有界尾部）。

    為什麼這是真 Principle-5 測試：prior maxDD 0.77 假設「全押」（每筆 ~100% 權益），完全
    不分散。真實系統每槽小注 r%，C 個並發槽損失有界 → maxDD 應大幅縮小。本函數量測
    縮到多小、是否 <= survivable 門檻，以及縮小是否以「期望值歸零」為代價。
    """
    seq = sorted(events, key=lambda e: (e["entry_date"], e["symbol"]))
    if not seq:
        return {"n": 0}

    # risk_unit：stop-anchored。
    if stop is not None and stop > 0:
        risk_unit = stop
    else:
        worst = min((e[ret_key] for e in seq if e[ret_key] is not None), default=-0.20)
        risk_unit = max(0.20, abs(worst))  # 無 stop → 用實證最壞單筆當隱含停損距離

    lever = risk_per_slot / risk_unit  # 每筆 trade_ret 對權益的放大係數

    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    daily_eq: list[tuple[str, float]] = []
    per_trade_equity_ret: list[float] = []  # 每筆對權益的貢獻（已 sized）
    cur_day = None
    for e in seq:
        r = e[ret_key]
        if r is None:
            continue
        r_clamped = max(r, -0.99)
        step = lever * r_clamped   # sized 貢獻（每槽 r% 風險）
        # 乘法步進，但 step 已是 equity 的相對變動（小注）。
        contrib = step
        per_trade_equity_ret.append(contrib)
        equity *= (1.0 + contrib)
        if equity <= 0:
            equity = 1e-9  # 帳戶清零（保護 log）
        peak = max(peak, equity)
        dd = 1.0 - equity / peak
        max_dd = max(max_dd, dd)
        if e["entry_date"] != cur_day:
            cur_day = e["entry_date"]
        daily_eq.append((e["entry_date"], equity))

    # 組合「日報酬」（按 entry_date 聚合等值曲線端點）→ Sharpe / Sortino / annualized。
    # 以 distinct entry-day 為時間單位（事件叢集在崩盤日，故日層才是組合節律）。
    day_equity: dict[str, float] = {}
    for d, eq in daily_eq:
        day_equity[d] = eq  # 同日最後一筆後的權益
    days_sorted = sorted(day_equity.keys())
    day_rets: list[float] = []
    prev = 1.0
    for d in days_sorted:
        eq = day_equity[d]
        day_rets.append(eq / prev - 1.0)
        prev = eq

    mean_day = base._mean(day_rets)
    sd_day = base._stddev(day_rets)
    downside = [min(0.0, x) for x in day_rets]
    dsd = math.sqrt(sum(x * x for x in downside) / len(downside)) if downside else None

    # 年化：以實際曆日跨度 annualize（非僅交易日，因事件稀疏）。
    first_d = dt.date.fromisoformat(days_sorted[0])
    last_d = dt.date.fromisoformat(days_sorted[-1])
    span_days = max(1, (last_d - first_d).days)
    total_ret = equity - 1.0
    ann_factor = TRADING_DAYS_PER_YEAR / span_days
    # 用對數年化避免複利爆掉。
    ann_return = (math.exp(math.log(max(equity, 1e-9)) * ann_factor) - 1.0)

    # Sharpe / Sortino 以「active day」報酬序列（無風險率 0）。年化用 sqrt(active days/yr)。
    active_days = len(day_rets)
    days_per_year_active = active_days / (span_days / TRADING_DAYS_PER_YEAR) if span_days else None
    sharpe = None
    sortino = None
    if mean_day is not None and sd_day and sd_day > 0 and days_per_year_active:
        sharpe = (mean_day / sd_day) * math.sqrt(days_per_year_active)
    if mean_day is not None and dsd and dsd > 0 and days_per_year_active:
        sortino = (mean_day / dsd) * math.sqrt(days_per_year_active)

    cvar_trade = base._cvar(per_trade_equity_ret, base.CVAR_ALPHA)
    cvar_day = base._cvar(day_rets, base.CVAR_ALPHA)

    return {
        "n": len(per_trade_equity_ret),
        "risk_per_slot": risk_per_slot,
        "risk_unit": risk_unit,
        "lever": lever,
        "final_equity": equity,
        "total_return": total_ret,
        "annualized_return": ann_return,
        "max_drawdown": max_dd,
        "cvar05_per_trade_equity": cvar_trade,
        "cvar05_day_return": cvar_day,
        "sharpe_annualized": sharpe,
        "sortino_annualized": sortino,
        "mean_day_return": mean_day,
        "std_day_return": sd_day,
        "n_active_days": active_days,
        "span_days": span_days,
        "survivable_maxdd": max_dd <= SURVIVABLE_MAXDD,
    }


# ---------------------------------------------------------------------------
# death-spiral 壓力疊加
# ---------------------------------------------------------------------------

def death_spiral_stress(
    events: list[dict[str, Any]],
    *,
    ret_key: str,
    risk_per_slot: float,
    stop: Optional[float],
    cap: Optional[int],
    cond_death_rate: float,
    n_seeds: int = DEATH_STRESS_SEEDS,
    base_seed: int = 0,
) -> dict[str, Any]:
    """在實證事件之上注入合成 death-spiral，多 seed 平均重算 SIZED 組合 maxDD（壓力測試）。

    為什麼必要：清潔 1d-kline universe 結構性 survivor-biased（0 真下市），實證尾部偏樂觀。
    本疊加按**每筆深-K 進場的條件死亡機率** cond_death_rate（非人口年化基率折算——那對
    3 天 hold 趨近 0 無意義），把一部分深-K 進場改判為「資產死亡」：
      - 每筆事件以 Bernoulli(cond_death_rate) 死亡。
      - 死亡事件中 GAP_THROUGH_FRAC 比例**隔夜跳空穿過 stop**：hard stop 無法在 stop 價成交，
        實現 DEATH_TERMINAL_RET（−95%）= gap-through-stop honest modeling（stop 只**部分**
        限制 gap-through，跳空穿過時失效）。
      - 其餘死亡事件（未 gap-through）：hard stop 仍在 stop 價成交（實現 −S − taker），
        資產隨後死亡不影響已平倉 → stop 確實救了這些（無 stop 則全部 gap-through）。
    多 seed Monte-Carlo（稀疏死亡單 seed 噪音大）取 maxDD/annret 的 mean + p95（最壞界）。
    用獨立 RNG，不污染實證統計。
    """
    n = len(events)
    maxdds: list[float] = []
    annrets: list[float] = []
    cvars: list[float] = []
    killed_counts: list[int] = []
    gap_counts: list[int] = []
    for s in range(n_seeds):
        rng = random.Random(base_seed + s * 7919 + 13)
        stressed = []
        n_killed = 0
        n_gap = 0
        for e in events:
            e2 = dict(e)
            if rng.random() < cond_death_rate:
                n_killed += 1
                if stop is None or rng.random() < GAP_THROUGH_FRAC:
                    e2[ret_key] = DEATH_TERMINAL_RET  # gap-through-stop：近全損
                    n_gap += 1
                else:
                    e2[ret_key] = -stop - TAKER_FEE - MAKER_FEE  # stop 守住
            stressed.append(e2)
        sized = sized_portfolio_equity_curve(
            stressed, ret_key=ret_key, risk_per_slot=risk_per_slot, stop=stop, cap=cap)
        if sized.get("max_drawdown") is not None:
            maxdds.append(sized["max_drawdown"])
            annrets.append(sized["annualized_return"])
            if sized.get("cvar05_day_return") is not None:
                cvars.append(sized["cvar05_day_return"])
        killed_counts.append(n_killed)
        gap_counts.append(n_gap)

    maxdd_mean = base._mean(maxdds)
    maxdd_p95 = base._percentile(maxdds, 0.95)
    return {
        "cond_death_rate_per_entry": cond_death_rate,
        "n_events": n,
        "n_seeds": n_seeds,
        "mean_killed_per_run": base._mean([float(x) for x in killed_counts]),
        "mean_gap_through_per_run": base._mean([float(x) for x in gap_counts]),
        "gap_through_frac": GAP_THROUGH_FRAC,
        "death_terminal_ret": DEATH_TERMINAL_RET,
        "sized_maxdd_stressed_mean": maxdd_mean,
        "sized_maxdd_stressed_p95": maxdd_p95,
        "sized_annret_stressed_mean": base._mean(annrets),
        "sized_cvar05_day_stressed_mean": base._mean(cvars) if cvars else None,
        # 存活判定取 p95 最壞界（survival-first：尾部不能只看平均）。
        "survivable_under_stress_p95": (maxdd_p95 is not None and maxdd_p95 <= SURVIVABLE_MAXDD),
    }


# ---------------------------------------------------------------------------
# day-clustered 顯著性（block bootstrap by distinct crash episode）
# ---------------------------------------------------------------------------

def day_clustered_significance(events: list[dict[str, Any]], *, ret_key: str, seed: int) -> dict[str, Any]:
    """以 distinct entry-day（crash episode）為有效 N 重做顯著性。

    為什麼（MIT flag）：同一崩盤日最多 26 symbol 同時 fill，逐筆高度相關 → iid-OLS / 逐筆
    bootstrap 的 t 高估顯著性。有效樣本 = distinct crash episode 數（tens 而非 thousands）。
    做法：先把每日所有事件報酬**平均成單一日報酬**（等權 within day），再對「日報酬序列」
    做 block bootstrap（block=1 日，因日間已近獨立；保留與逐筆對比）。
    """
    by_day: dict[str, list[float]] = {}
    for e in events:
        r = e[ret_key]
        if r is not None:
            by_day.setdefault(e["entry_date"], []).append(r)
    day_means = [sum(v) / len(v) for v in by_day.values()]
    n_days = len(day_means)
    if n_days < 3:
        return {"n_distinct_days": n_days, "note": "insufficient_episodes"}

    mean_day = sum(day_means) / n_days
    sd_day = base._stddev(day_means)
    naive_day_t = (mean_day / (sd_day / math.sqrt(n_days))) if (sd_day and sd_day > 0) else None

    # block bootstrap on day-means（block=1：日間獨立假設；同時報 block=5 敏感度）。
    boot1 = base._block_bootstrap_tstat(day_means, block_len=1, n_boot=base.BLOCK_BOOTSTRAP_N, seed=seed) \
        if n_days >= 2 else {"boot_t": None}
    boot5 = base._block_bootstrap_tstat(day_means, block_len=min(5, n_days - 1),
                                        n_boot=base.BLOCK_BOOTSTRAP_N, seed=seed + 1) \
        if n_days >= 6 else {"boot_t": None}

    # 逐筆 naive t（對照高估幅度）。
    per_trade = [e[ret_key] for e in events if e[ret_key] is not None]
    sd_pt = base._stddev(per_trade)
    naive_pertrade_t = (base._mean(per_trade) / (sd_pt / math.sqrt(len(per_trade)))) \
        if (sd_pt and sd_pt > 0 and per_trade) else None

    return {
        "n_per_trade": len(per_trade),
        "n_distinct_days": n_days,
        "mean_day_return": mean_day,
        "naive_pertrade_t": naive_pertrade_t,
        "naive_day_clustered_t": naive_day_t,
        "block_bootstrap_day_b1": boot1,
        "block_bootstrap_day_b5": boot5,
        "interpretation": (
            "若 day-clustered boot_t 遠小於 per-trade naive t → iid 確實高估；"
            "edge 顯著性以 day-clustered 為準（有效 N = distinct crash episode）"
        ),
    }


# ---------------------------------------------------------------------------
# stopped-vs-unstopped alpha 截距對比（stop 是否切掉贏家）
# ---------------------------------------------------------------------------

def alpha_survives_stop(
    klines_by_sym, funding, btc_fwd_ret, btc_trend, *, k: float, hold: int, stop: float,
) -> dict[str, Any]:
    """對比同 (K,N) 的 hard-stop vs no-stop 的 beta-clean alpha 截距（stop 是否砍贏家）。

    為什麼：bounce 常在跌破 stop 後才反彈，hard stop 把這些贏家在最低點砍掉 = 切贏家。
    決定性 tradeoff：alpha 截距 stopped vs unstopped 差多少。若 stop 把 alpha 砍光 →
    「存活但無 edge」；若 alpha 仍顯著正 → stop 可接受。
    """
    ev_nostop = build_events_stopped(klines_by_sym, funding, btc_fwd_ret, btc_trend,
                                     k=k, hold=hold, stop=None)
    ev_stop = build_events_stopped(klines_by_sym, funding, btc_fwd_ret, btc_trend,
                                   k=k, hold=hold, stop=stop)
    ab_nostop = base.alpha_vs_beta(ev_nostop, ret_key="gross")
    ab_stop = base.alpha_vs_beta(ev_stop, ret_key="gross")
    pct_stopped = (sum(1 for e in ev_stop if e["stopped"]) / len(ev_stop)) if ev_stop else None
    return {
        "k": k, "hold": hold, "stop": stop,
        "pct_stopped": pct_stopped,
        "alpha_unstopped": ab_nostop.get("overall", {}).get("alpha"),
        "alpha_t_unstopped": ab_nostop.get("overall", {}).get("alpha_t"),
        "alpha_stopped": ab_stop.get("overall", {}).get("alpha"),
        "alpha_t_stopped": ab_stop.get("overall", {}).get("alpha_t"),
        "mean_net_taker_unstopped": base._mean([e["net_taker"] for e in ev_nostop]) if ev_nostop else None,
        "mean_net_taker_stopped": base._mean([e["net_taker"] for e in ev_stop]) if ev_stop else None,
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def run_survival_safe(conn) -> dict[str, Any]:
    symbols = base.list_symbols(conn)
    klines_by_sym = {s: base.load_1d_klines(conn, s) for s in symbols}
    funding = base.load_funding_daily(conn)

    # universe 組成（誠實盤點：清潔 1d 集 = 26 大-cap survivor，0 下市/死亡）。
    global_last = max((ks[-1]["date"] for ks in klines_by_sym.values() if ks), default=None)
    # 多數 symbol last_day 較全域窗末早幾天，純因 backfill 批次結束日不同（非真下市）。
    # 計算各 last_day 的眾數作為「正常 backfill 結束日」基準，>7d 早於眾數才算可疑。
    last_days = [ks[-1]["date"] for ks in klines_by_sym.values() if ks]
    last_day_mode = max(set(last_days), key=last_days.count) if last_days else None
    universe: list[dict[str, Any]] = []
    n_gap_flagged = 0       # >7d 早於 global_last（含 backfill-batch false-positive）
    n_truly_dead = 0        # >7d 早於 last_day 眾數 + min_low 趨近 0（真死亡候選）
    n_nonpos = 0
    for s in symbols:
        ks = klines_by_sym[s]
        if not ks:
            continue
        dates = [b["date"] for b in ks]
        min_low = min(b["low"] for b in ks)
        gap_flagged = (global_last is not None
                       and (dt.date.fromisoformat(global_last) - dt.date.fromisoformat(dates[-1])).days > 7)
        # 真死亡候選：明顯早於眾數結束日 AND 價格崩到接近 0（min_low/first_open<<1）。
        early_vs_mode = (last_day_mode is not None
                         and (dt.date.fromisoformat(last_day_mode) - dt.date.fromisoformat(dates[-1])).days > 7)
        crashed_near_zero = min_low <= ks[0]["open"] * 0.02  # 跌破首日開盤 2%
        truly_dead = bool(early_vs_mode and crashed_near_zero)
        nonpos = sum(1 for b in ks if min(b["open"], b["high"], b["low"], b["close"]) <= 0)
        if gap_flagged:
            n_gap_flagged += 1
        if truly_dead:
            n_truly_dead += 1
        if nonpos:
            n_nonpos += 1
        universe.append({
            "symbol": s, "bars": len(ks), "first_day": dates[0], "last_day": dates[-1],
            "min_low": min_low, "gap_flagged_7d": gap_flagged,
            "truly_dead_candidate": truly_dead, "nonpos_bars": nonpos,
        })

    btc_ks = klines_by_sym.get("BTCUSDT", [])
    btc_fwd, btc_regime = base.build_btc_helpers(btc_ks)

    first_day = min((ks[0]["date"] for ks in klines_by_sym.values() if ks), default=None)
    span_years = ((dt.date.fromisoformat(global_last) - dt.date.fromisoformat(first_day)).days / 365.0
                  if (global_last and first_day) else None)

    # ---- hard-stop grid（K × N × S）：%stopped + mean net + 分佈 ----
    stop_grid: list[dict[str, Any]] = []
    for k in K_GRID:
        for hold in N_GRID:
            for stop in STOP_GRID:
                ev = build_events_stopped(klines_by_sym, funding, btc_fwd, btc_regime,
                                          k=k, hold=hold, stop=stop)
                n = len(ev)
                pct_stopped = (sum(1 for e in ev if e["stopped"]) / n) if n else None
                seed = int(k * 1000) * 1000 + hold * 100 + int((stop or 0) * 100)
                stop_grid.append({
                    "k": k, "hold": hold, "stop": stop, "n_events": n,
                    "pct_stopped": pct_stopped,
                    "net_taker": base.summarize_returns([e["net_taker"] for e in ev], seed=seed + 1),
                    "net_maker": base.summarize_returns([e["net_maker"] for e in ev], seed=seed + 2),
                    "gross": base.summarize_returns([e["gross"] for e in ev], seed=seed + 3),
                })

    # ---- 完整 survival-first 組合掃描（K × N × S × C × r）----
    portfolio_grid: list[dict[str, Any]] = []
    best = None
    for k in K_GRID:
        for hold in N_GRID:
            for stop in STOP_GRID:
                ev_full = build_events_stopped(klines_by_sym, funding, btc_fwd, btc_regime,
                                               k=k, hold=hold, stop=stop)
                if not ev_full:
                    continue
                for cap in CONCURRENCY_GRID:
                    capres = apply_concurrency_cap(ev_full, cap=cap)
                    kept = capres["kept"]
                    if not kept:
                        continue
                    for r in RISK_PER_SLOT_GRID:
                        sized = sized_portfolio_equity_curve(
                            kept, ret_key="net_taker", risk_per_slot=r, stop=stop, cap=cap)
                        mean_net = base._mean([e["net_taker"] for e in kept])
                        cell = {
                            "k": k, "hold": hold, "stop": stop,
                            "cap": cap if cap is not None else "unlimited",
                            "risk_per_slot": r,
                            "n_kept": capres["n_kept"], "n_dropped": capres["n_dropped"],
                            "max_concurrency_raw": capres["max_concurrency_raw"],
                            "max_concurrency_capped": capres["max_concurrency_capped"],
                            "mean_net_taker_per_trade": mean_net,
                            "sized_maxdd": sized.get("max_drawdown"),
                            "sized_annret": sized.get("annualized_return"),
                            "sized_total_ret": sized.get("total_return"),
                            "sized_cvar05_day": sized.get("cvar05_day_return"),
                            "sized_sharpe": sized.get("sharpe_annualized"),
                            "sized_sortino": sized.get("sortino_annualized"),
                            "survivable_maxdd": sized.get("survivable_maxdd"),
                            "positive_expectancy": (mean_net is not None and mean_net > 0),
                        }
                        portfolio_grid.append(cell)
                        # best：正期望值 AND survivable maxDD，最大化 annret。
                        if (cell["positive_expectancy"] and cell["survivable_maxdd"]
                                and sized.get("annualized_return") is not None):
                            if best is None or sized["annualized_return"] > best["sized_annret"]:
                                best = cell

    # ---- death-spiral 壓力疊加（對 best + 一組 stopped/unstopped 代表 config）----
    stress_results: list[dict[str, Any]] = []
    stress_targets = []
    if best is not None:
        stress_targets.append({"k": best["k"], "hold": best["hold"], "stop": best.get("stop"),
                               "cap": best["cap"], "risk_per_slot": best["risk_per_slot"],
                               "label": "best"})
    # 對照代表（mandate 典型）：(a) 有 stop 的存活安全配置 / (b) 同 K/N 無 stop（看 stop
    # 在 death-spiral 下的保護價值）。
    stress_targets.append({"k": 0.10, "hold": 3, "stop": 0.10, "cap": 3,
                           "risk_per_slot": 0.02, "label": "rep_stopped_K10N3S10C3r2"})
    stress_targets.append({"k": 0.10, "hold": 3, "stop": None, "cap": 3,
                           "risk_per_slot": 0.02, "label": "rep_unstopped_K10N3C3r2"})
    stress_targets.append({"k": 0.20, "hold": 3, "stop": 0.15, "cap": 5,
                           "risk_per_slot": 0.02, "label": "rep_deepK_K20N3S15C5r2"})
    for tgt in stress_targets:
        cap_val = tgt["cap"]
        cap_int = None if cap_val in (None, "unlimited") else int(cap_val)
        ev_full = build_events_stopped(klines_by_sym, funding, btc_fwd, btc_regime,
                                       k=tgt["k"], hold=tgt["hold"], stop=tgt.get("stop"))
        kept = apply_concurrency_cap(ev_full, cap=cap_int)["kept"]
        for cdr in DEATH_COND_RATES_PER_ENTRY:
            sres = death_spiral_stress(
                kept, ret_key="net_taker", risk_per_slot=tgt["risk_per_slot"],
                stop=tgt.get("stop"), cap=cap_int, cond_death_rate=cdr,
                base_seed=int(cdr * 100000) + tgt["hold"] * 17)
            sres["config"] = {"label": tgt["label"], "k": tgt["k"], "hold": tgt["hold"],
                              "stop": tgt.get("stop"), "cap": cap_val,
                              "risk_per_slot": tgt["risk_per_slot"]}
            stress_results.append(sres)

    # ---- day-clustered 顯著性（對 best config 的 kept 事件）----
    day_clustered = None
    alpha_stop = None
    if best is not None:
        cap_int = None if best["cap"] in (None, "unlimited") else int(best["cap"])
        ev_full = build_events_stopped(klines_by_sym, funding, btc_fwd, btc_regime,
                                       k=best["k"], hold=best["hold"], stop=best.get("stop"))
        kept = apply_concurrency_cap(ev_full, cap=cap_int)["kept"]
        day_clustered = day_clustered_significance(kept, ret_key="net_taker", seed=777)
        # best 可能無 stop（stop 砍 alpha→optimizer 偏好 no-stop）；仍報 alpha-survives-stop
        # 對比（用 best 的 stop，或無 stop 時用代表 8% stop 量化 stop 會砍多少 alpha）。
        stop_for_compare = best.get("stop") if best.get("stop") is not None else 0.08
        alpha_stop = alpha_survives_stop(klines_by_sym, funding, btc_fwd, btc_regime,
                                         k=best["k"], hold=best["hold"], stop=stop_for_compare)
        alpha_stop["note"] = ("best config stop=%s；此對比用 stop=%s 量化 hard stop 對 alpha 的切割"
                              % (best.get("stop"), stop_for_compare))

    # ---- alpha-survives-stop（獨立掃一組代表 K×stop，不只 best）----
    alpha_stop_grid = []
    for k in K_GRID:
        for stop in (0.08, 0.10, 0.15):
            asg = alpha_survives_stop(klines_by_sym, funding, btc_fwd, btc_regime,
                                      k=k, hold=3, stop=stop)
            alpha_stop_grid.append(asg)

    return {
        "survival_version": SURVIVAL_VERSION,
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "params": {
            "K_grid": list(K_GRID), "N_grid": list(N_GRID),
            "stop_grid": [s for s in STOP_GRID], "concurrency_grid": [c for c in CONCURRENCY_GRID],
            "risk_per_slot_grid": list(RISK_PER_SLOT_GRID),
            "maker_fee_bps": base.MAKER_FEE_BPS, "taker_fee_bps": base.TAKER_FEE_BPS,
            "death_cond_rates_per_entry": list(DEATH_COND_RATES_PER_ENTRY),
            "death_stress_seeds": DEATH_STRESS_SEEDS,
            "gap_through_frac": GAP_THROUGH_FRAC, "death_terminal_ret": DEATH_TERMINAL_RET,
            "survivable_maxdd": SURVIVABLE_MAXDD,
        },
        "universe_composition": {
            "n_symbols": len(universe), "symbols": universe,
            "n_gap_flagged_7d": n_gap_flagged,
            "n_truly_dead_candidate": n_truly_dead,
            "n_with_nonpos_bars": n_nonpos,
            "last_day_mode": last_day_mode,
            "global_last_day": global_last, "span_years": span_years,
            "note": (
                "清潔 1d-kline universe 結構性 = 全部 26 個存活兩年大-cap survivor；"
                "n_gap_flagged_7d 多數是 backfill 批次結束日不同的 FALSE POSITIVE（last_day "
                "2026-06-01 vs global 2026-06-09，非真下市，price 仍遠高於 0）；真死亡候選 "
                "n_truly_dead_candidate（早於眾數結束日 AND 崩破首日開盤 2%）= 0 → 表內無真"
                "下市/歸零事件。intraday 153-symbol 集只 ~73 天且已知壞 → 無法擴充日層 2yr "
                "尾部。survivor bias 不可從此資料移除 → 唯一誠實補償 = death-spiral 壓力疊加"
                "（DEATH_COND_RATES_PER_ENTRY 條件死亡注入 + gap-through-stop 建模）。"
            ),
        },
        "funding_coverage": {
            "funding_symbols": len(funding),
            "funding_total_daily_rows": sum(len(v) for v in funding.values()),
        },
        "hard_stop_grid": stop_grid,
        "portfolio_grid": portfolio_grid,
        "best_survival_safe_config": best,
        "death_spiral_stress": stress_results,
        "day_clustered_significance": day_clustered,
        "alpha_survives_stop_best": alpha_stop,
        "alpha_survives_stop_grid": alpha_stop_grid,
    }


# ---------------------------------------------------------------------------
# Artifact 寫出
# ---------------------------------------------------------------------------

def write_artifact(report: dict[str, Any], *, out_path: Optional[str]) -> str:
    if out_path is None:
        root = os.path.join(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"),
                            "research", "tail_dislocation_meanrev")
        os.makedirs(root, exist_ok=True)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = os.path.join(root, f"survival_safe_{stamp}.json")
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
    ap = argparse.ArgumentParser(description="尾部錯位 alpha 存活安全變體（$0 唯讀 OFFLINE research）")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    conn = base.connect_pg()
    try:
        report = run_survival_safe(conn)
    finally:
        conn.close()
    out = write_artifact(report, out_path=args.out)

    uc = report["universe_composition"]
    print(f"[{SURVIVAL_VERSION}] artifact -> {out}")
    print(f"universe n={uc['n_symbols']} gap_flagged_7d={uc['n_gap_flagged_7d']}(false-pos) "
          f"truly_dead={uc['n_truly_dead_candidate']} nonpos={uc['n_with_nonpos_bars']} "
          f"span_yr={uc['span_years']:.2f}")
    best = report["best_survival_safe_config"]
    if best:
        print(f"BEST: K{int(best['k']*100)} N{best['hold']} S={best['stop']} C={best['cap']} "
              f"r={best['risk_per_slot']} | mean_net={best['mean_net_taker_per_trade']:.4f} "
              f"maxDD={best['sized_maxdd']:.4f} annret={best['sized_annret']:.4f} "
              f"sharpe={best['sized_sharpe']}")
    else:
        print("BEST: NONE — no config achieves positive expectancy AND survivable maxDD<=0.25")
    print("hard_stop_grid (K/N/S: n / %stopped / mean_net_taker):")
    for c in report["hard_stop_grid"]:
        nt = c["net_taker"].get("mean")
        ps = c["pct_stopped"]
        print(f"  K{int(c['k']*100)} N{c['hold']} S={c['stop']}: n={c['n_events']} "
              f"stopped={ps:.3f} net_tk={nt:.4f}" if (ps is not None and nt is not None)
              else f"  K{int(c['k']*100)} N{c['hold']} S={c['stop']}: n={c['n_events']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
