#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fill_sim — queue-position fill-simulation（CP-3 做市 go/no-go 工具，$0 唯讀研究）。

MODULE_NOTE
模塊用途：
  量化做市的單一決定性未知 = fill-conditional adverse selection（你被成交時往往是你錯了）。
  campaign-8 dose-response 已證 NET 符號取決於 queue position（front +5.5bp / 5bp-queue ~0 /
  back -6.9bp），但這在節流取樣的 ob_top 上量不到——recorder-v2 full-L1（market.l1_events）
  才有 queue/queue-advance 粒度。本模組用 l1_events（BBO 事件流）+ trades（aggressor flow）
  做事件驅動的 hypothetical 掛單成交模擬，per-symbol 輸出：
    - fill rate（NO-FILL=機會成本，計入分母）
    - fill-conditional adverse selection（beta-residual post-fill mid 移動，5/15/30s）
    - NET edge（bps/fill）= half_spread_captured − adverse_selection − 2×maker_fee
    - cost wall：打平所需 fee/rebate/spread 條件（break-even fee、fee shortfall、required spread）
    - naive（兩側都掛）vs informed-skip（信號強烈不利該側就不掛）對照，比較 NET / quoting-hour
  確認的 beta-clean 信號（OFI@10s +0.031、BTC→alt 5s lead +0.077）僅作 skip filter（避開被
  逆選),非 profit source。

  ⚠️ 誠實框架（NON-NEGOTIABLE，沿用 harness caveat 慣例）：~100min 單窗 ≈ 1 個 regime 樣本，
     是最早期結構性偵察讀數,**不是 go/no-go**。禁 DSR/PSR/PBO/Sharpe；n_fills 報實數,
     <30/cell 抑制顯著性宣稱。真 CP-3 裁決見 report cp3_requirements。

主要函數：
  - simulate_symbol：單 symbol 事件驅動 queue 狀態機（§1）+ 3-case fill resolver（§2）。
  - measure_adverse_selection：beta-residual post-fill mid 移動（§3，重用 core beta 機制）。
  - run：組裝 naive/informed 兩策略對照 + 報告（§4/§5）。

硬邊界（沿用 microstructure data_loader/core 契約，不弱化任何 anti-fool 檢查）：
  - read-only：只 SELECT market.l1_events / market.trades / market.ob_top（loader
    set_session readonly）。0 order path、0 auth、0 lease、0 risk、0 寫 market 表。
  - 只寫 --out 指定的 JSON/CSV artifact。
  - l1_events §1.2 兩段過濾（crossed-row 結構性 + post-fix ts floor），fail-loud 計數;
    crossed_after_filter==0 是硬 AC（對齊 Rust E4 test_crossed_never_emitted_invariant）。
  - back-of-queue conservatism 非可選（size_ahead := Q0）;maker fee 2bp/side 無 rebate。
  - leak-free：beta 用 core 的 rolling-30min cov/var 各 shift(1) 機制 verbatim;
    post-fill horizon mid 是合法的「已實現逆向移動量測窗」,非 feature。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import core, data_loader

MAKER_FEE_BPS = 2.0     # per side（對齊 mm_sizing_run.MAKER_FEE_BPS，無 rebate）
TAKER_FEE_BPS = 5.5     # per side（taker-exit 變體用）
MAKER_FEE_ROUND_TRIP_BPS = 2 * MAKER_FEE_BPS
# post-fix 重啟 floor（recorder-v2 crossed-fix）。預設 +02 本地時。可由 --clean-since 覆蓋。
DEFAULT_CLEAN_SINCE = "2026-06-17T14:25:00+02:00"
# adverse-selection 量測 horizon（秒）。
DEFAULT_HORIZONS = (5, 15, 30)
# 掛單取樣節奏（秒）：每 N 秒在 bid/ask 各放一張獨立 hypothetical 掛單。
DEFAULT_CADENCE_S = core.GRID_STEP_S
# 顯著性抑制門檻：per-cell n_fills < 此值,不出顯著性宣稱（誠實）。
MIN_FILLS_FOR_SIGNIF = 30
# informed-skip 信號的 worst-tail quantile（預設 skip 最差 10% 信號的掛單）。
DEFAULT_SKIP_QUANTILE = 0.10
# NOTE-A 隊列劑量反應（queue dose-response）：你在 touch 隊列中身前的量 = frac × Q0。
#   front = 0.0×Q0（隊首,最樂觀,假設你最先 join）
#   mid   = 0.5×Q0（隊中。L1-only 無多檔深度,無法算真「5bp-of-depth」累積量;
#           以 touch 隊列的一半為 mid-queue 近似,並在報告誠實標注此近似。）
#   back  = 1.0×Q0（隊尾,保守,NON-OPTIONAL 預設）
QUEUE_POSITIONS = {"front": 0.0, "mid": 0.5, "back": 1.0}
DEFAULT_QUEUE_POSITION = "back"


# ============================================================
# §1.2 post-fix 兩段過濾（fail-loud 計數）
# ============================================================
def filter_l1_clean(l1: pd.DataFrame, clean_since):
    """l1_events §1.2 兩段獨立 guard。回 (l1_clean, counts dict)。

    guard-1（結構性,primary）：drop best_bid >= best_ask（crossed/locked stale 簿,非真 BBO;
      與 Rust crossed-fix 同不變量,leak-free 只用該 row 自身欄位,即使 restart ts 不精確也成立）。
    guard-2（ts floor,parameterized,default-on）：drop ts < clean_since（pre-fix stale 簿汙染）。
    兩者分開計數,fail-loud（不靜默丟）。AC：過濾後 crossed_after_filter == 0。
    """
    n_raw = len(l1)
    if n_raw == 0:
        return l1, {"l1_rows_raw": 0, "n_pre_fix_dropped": 0, "n_crossed_dropped": 0,
                    "l1_rows_post_filter": 0, "crossed_after_filter": 0}
    pre_fix_mask = l1["ts"] < clean_since if clean_since is not None else pd.Series(False, index=l1.index)
    n_pre_fix = int(pre_fix_mask.sum())
    l1b = l1.loc[~pre_fix_mask]
    crossed_mask = l1b["best_bid"] >= l1b["best_ask"]
    n_crossed = int(crossed_mask.sum())
    l1c = l1b.loc[~crossed_mask].copy()
    # AC 驗證：過濾後絕不該還有 crossed。
    crossed_after = int((l1c["best_bid"] >= l1c["best_ask"]).sum())
    l1c["mid"] = 0.5 * (l1c["best_bid"] + l1c["best_ask"])
    return l1c, {
        "l1_rows_raw": n_raw,
        "n_pre_fix_dropped": n_pre_fix,
        "n_crossed_dropped": n_crossed,
        "l1_rows_post_filter": int(len(l1c)),
        "crossed_after_filter": crossed_after,
    }


# ============================================================
# §1.3 + §2 單 symbol 事件驅動 queue 狀態機 + 3-case fill resolver
# ============================================================
def _ts_ns(ts_like) -> np.ndarray:
    """tz-aware datetime Series/Index → int64 **奈秒** since epoch（UTC）。

    pandas3 移除了 Series.view。本表 TIMESTAMPTZ 載入後 dtype 是 datetime64[us, UTC]
    （微秒解析度）——直接 astype('int64') 會得「微秒」非奈秒,與本模組 step_ns/horizon
    的奈秒假設差 1000x（會把 115min 窗壓成 ~7s）。故先 tz 去除 + 強制轉 datetime64[ns]
    再取 int64,保證恆為真奈秒,與 step_ns=秒×1e9 / (t/1e9) 一致。
    """
    idx = pd.DatetimeIndex(ts_like)
    # tz-aware → 去 tz（值已是 UTC 基準的絕對時刻）→ 強制奈秒解析度。
    if idx.tz is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    return np.asarray(idx).astype("datetime64[ns]").astype("int64")


def _build_mid_series(l1_sym: pd.DataFrame):
    """單 symbol l1 → 排序的 (ts ns int64, mid, best_bid, best_ask, bid_size, ask_size) numpy。

    供 asof-backward 查「<= t 最後一筆已知簿」（PIT,不看未來）。
    """
    g = l1_sym.sort_values(["ts", "update_id"]).reset_index(drop=True)
    return {
        "ts": _ts_ns(g["ts"]),  # ns since epoch（UTC）
        "mid": g["mid"].to_numpy(),
        "bb": g["best_bid"].to_numpy(),
        "ba": g["best_ask"].to_numpy(),
        "bsz": g["bid_size"].to_numpy(),
        "asz": g["ask_size"].to_numpy(),
    }


def _asof_idx(ts_arr: np.ndarray, t: int) -> int:
    """回 ts_arr 中 <= t 的最後一筆 index（asof-backward,leak-free）;無則 -1。"""
    i = np.searchsorted(ts_arr, t, side="right") - 1
    return int(i)


def simulate_symbol(l1_sym: pd.DataFrame, tr_sym: pd.DataFrame, cadence_s: float,
                    size_ahead_frac: float = 1.0):
    """單 symbol：固定節奏掛 hypothetical 掛單,事件驅動走 queue 狀態機,回 quote-trial DataFrame。

    每張掛單獨立模擬（無 inventory carry;§6 inventory risk 屬 portfolio 範疇,不在此）。
    狀態機（§1.3）：
      - Q0 = 掛單時點該側 size-at-touch（asof-backward）。size_ahead := size_ahead_frac×Q0
        （NOTE-A 隊列劑量反應 sweep：front=0.0 / mid=0.5 / back=1.0;back 為保守預設）。
      - aggressor 消耗：同側 aggressor（bid←Sell / ask←Buy）at-or-through P_quote 累加 qty。
      - cancel 推進：兩 l1 事件間該側 size 下降中,扣掉同期 trade 消耗的殘餘 = cancel-ahead,
        floored 0;size 上升（新單加入）不把你往後推（FIFO 保守,你保絕對 rank）。
        BUG-3 修：prev_size 改為「每處理一個 best==p_quote 的事件後一律更新」,且只在
        本事件 best 仍 == p_quote 時做 cancel-attribution（避 best 短暫離開又回來時 size
        基準 stale 把 level-change 的整段差額誤記成 cancel-ahead 而虛報推進）。
      - PIT：單次前向 chronological 迭代,t 時只看 ts<=t 事件,結構性保證無 look-ahead。
    3-case 終止（§2）：
      - FILL：size_ahead <= 0 且 best_S 仍 == P_quote。
      - NO_FILL：best_S 改善離開你（bid 被抬高 / ask 被壓低）前隊列未耗盡 → 機會成本,計入分母。
      - ADVERSE_THROUGH：價格逆向穿過你的 level（被 sweep）同刻你被填到隊尾 → 結構性壞 fill。
      - 同 ts 同時 fill+sweep → 解為 FILL（你在 rest,sweep 命中你,保守）。

    回 DataFrame，一列一次 quote-trial：
      symbol, side, t_place(ns), p_quote, q0, outcome, t_fill(ns or NaN), fill_lag_s, mid_place。
    """
    if l1_sym.empty or tr_sym.empty:
        return pd.DataFrame()

    book = _build_mid_series(l1_sym)
    bts = book["ts"]
    if len(bts) < 5:
        return pd.DataFrame()

    # trades → numpy（同側分流；Sell aggressor 消耗 bid,Buy aggressor 消耗 ask）。
    tr = tr_sym.sort_values("ts").reset_index(drop=True)
    tr_ts = _ts_ns(tr["ts"])
    tr_px = tr["price"].to_numpy()
    tr_qty = tr["qty"].to_numpy()
    tr_is_sell = (tr["side"] == "Sell").to_numpy()  # Sell aggressor

    t0 = int(bts[0])
    t1 = int(bts[-1])
    step_ns = int(cadence_s * 1e9)
    place_ts = np.arange(t0, t1, step_ns, dtype="int64")

    rows = []
    n_book = len(bts)
    n_tr = len(tr_ts)

    for side in ("bid", "ask"):
        for tp in place_ts:
            bi = _asof_idx(bts, int(tp))
            if bi < 0:
                continue
            if side == "bid":
                p_quote = book["bb"][bi]
                q0 = book["bsz"][bi]
            else:
                p_quote = book["ba"][bi]
                q0 = book["asz"][bi]
            mid_place = book["mid"][bi]
            if not (np.isfinite(p_quote) and np.isfinite(q0) and q0 > 0 and np.isfinite(mid_place)):
                continue

            # 起步事件 index：第一筆 ts > tp 的 book 事件（往後走）。
            ev = bi + 1
            # 起步 trade index：第一筆 ts > tp 的 trade。
            ti = int(np.searchsorted(tr_ts, int(tp), side="right"))

            q_eff = float(size_ahead_frac) * float(q0)   # NOTE-A：身前有效隊列量
            size_ahead = q_eff
            outcome = None
            t_fill = np.nan
            # 前一個已知該側 size（追 cancel 推進用）。BUG-3：恆等於「上一個 best==p_quote
            # 事件後的 size」,best 短暫離開又回來時不拿陳舊基準算 cancel-ahead。
            prev_size = float(q0)

            # 前向 chronological 迭代 book 事件;每段消化期間的 trade。
            while ev < n_book:
                ev_t = int(bts[ev])
                # 本段 = (上一個處理點, ev_t]，先吃這段的同側 aggressor 消耗。
                consumed = 0.0
                while ti < n_tr and tr_ts[ti] <= ev_t:
                    same_side = tr_is_sell[ti] if side == "bid" else (not tr_is_sell[ti])
                    if same_side:
                        # at-or-through：Sell print px<=p_quote 消耗 bid;Buy print px>=p_quote 消耗 ask。
                        hit = (tr_px[ti] <= p_quote) if side == "bid" else (tr_px[ti] >= p_quote)
                        if hit:
                            consumed += float(tr_qty[ti])
                    ti += 1
                size_ahead -= consumed

                # FILL：身前隊列被同側 aggressor 成交耗盡。
                # 必須由「本段有真實同側成交（consumed>0）」觸發——否則 front-of-queue
                # (q_eff=0) 會在毫無成交時假成交（你身前 0 但仍需對手單來吃你）。
                if size_ahead <= 0 and consumed > 0:
                    # best_S 此刻是否仍在 p_quote？檢查本事件後的簿狀態。
                    bb_now = book["bb"][ev]
                    ba_now = book["ba"][ev]
                    if side == "bid":
                        through = bb_now < p_quote or ba_now <= p_quote  # 價被壓到你之下=被穿
                    else:
                        through = ba_now > p_quote or bb_now >= p_quote
                    outcome = "adverse_through" if through else "fill"
                    t_fill = ev_t
                    break

                # 本事件後該側 best/size。
                if side == "bid":
                    best_now = book["bb"][ev]
                    size_now = book["bsz"][ev]
                    improved_away = best_now > p_quote      # 有人比你出更好價 → 市場離開你
                    moved_through = best_now < p_quote       # 價跌穿你的 level
                else:
                    best_now = book["ba"][ev]
                    size_now = book["asz"][ev]
                    improved_away = best_now < p_quote
                    moved_through = best_now > p_quote

                if improved_away:
                    outcome = "no_fill"
                    break
                if moved_through:
                    # 價穿過你的 level 但隊列在 BBO 還沒清完 → 被 sweep 到隊尾,結構壞 fill。
                    outcome = "adverse_through"
                    t_fill = ev_t
                    break

                # best 仍在 p_quote：cancel 推進（size 下降扣掉本段 trade 消耗的殘餘）。
                # BUG-3：只在 best 全程 == p_quote（level 未變）時做 cancel-attribution;
                #   prev_size 一律更新（不再藏在 cancel_ahead>0 分支內,避陳舊基準）。
                #   cancel 推進只縮 size_ahead,不自行觸發成交——真成交永遠要等下一筆同側
                #   trade（保守,direction-safe）。
                if best_now == p_quote and np.isfinite(size_now):
                    drop = prev_size - size_now
                    cancel_ahead = drop - consumed  # 已被 trade 消耗的部分不重複算
                    if cancel_ahead > 0:
                        size_ahead -= cancel_ahead   # 只往前推,size 上升不往後推
                        if size_ahead < 0:
                            size_ahead = 0.0          # floor;成交仍待下一筆同側 trade
                    prev_size = size_now
                ev += 1

            if outcome is None:
                # 走到資料尾仍未終止 → 視為 no_fill（窗截斷,保守不假裝成交）。
                outcome = "no_fill"

            fill_lag = (t_fill - tp) / 1e9 if (outcome in ("fill", "adverse_through")
                                              and np.isfinite(t_fill)) else np.nan
            rows.append({
                "symbol": l1_sym["symbol"].iloc[0],
                "side": side,
                "t_place": int(tp),
                "p_quote": float(p_quote),
                "q0": float(q0),
                "q_eff": float(q_eff),
                "outcome": outcome,
                "t_fill": float(t_fill) if np.isfinite(t_fill) else np.nan,
                "fill_lag_s": float(fill_lag) if np.isfinite(fill_lag) else np.nan,
                "mid_place": float(mid_place),
            })

    return pd.DataFrame(rows)


# ============================================================
# §3 beta-residual adverse-selection（重用 core beta 機制）
# ============================================================
def _leakfree_beta_at(g_sym, g_btc, t_fill_ns: int) -> float:
    """t_fill 時點的 leak-free rolling 30min beta（cov/var 各 shift(1)，clip(-5,5)）。

    與 core.assemble_frames 同機制：用 5s 同期報酬,rolling BETA_ROLL_S 窗,shift(1) 確保
    beta 只用 < t_fill 資訊。回標量 beta（退化 → 0.0）。
    g_sym / g_btc 為 _build_mid_series 結果。
    """
    roll = max(core.BETA_ROLL_S // core.GRID_STEP_S, 30)
    # 用 5s 網格的同期 log-return。先把兩者對齊到 t_fill 之前的 5s 網格。
    # 取 t_fill 之前 (roll+2) 根 5s bar 的 mid（asof-backward）。
    step_ns = int(core.GRID_STEP_S * 1e9)
    grid_t = np.array([t_fill_ns - step_ns * k for k in range(roll + 2, -1, -1)], dtype="int64")
    m_sym = np.array([g_sym["mid"][_asof_idx(g_sym["ts"], int(gt))]
                      if _asof_idx(g_sym["ts"], int(gt)) >= 0 else np.nan for gt in grid_t])
    m_btc = np.array([g_btc["mid"][_asof_idx(g_btc["ts"], int(gt))]
                      if _asof_idx(g_btc["ts"], int(gt)) >= 0 else np.nan for gt in grid_t])
    s = pd.Series(np.log(m_sym[1:] / m_sym[:-1]))
    b = pd.Series(np.log(m_btc[1:] / m_btc[:-1]))
    if s.notna().sum() < 30 or b.notna().sum() < 30:
        return 0.0
    # rolling cov/var 各 shift(1)：最後一個窗的 beta = 嚴格用到倒數第二根為止（< t_fill）。
    cov = s.rolling(roll).cov(b).shift(1)
    var = b.rolling(roll).var().shift(1)
    beta = (cov / var).clip(-5, 5).fillna(0.0)
    val = float(beta.iloc[-1]) if len(beta) else 0.0
    return val if np.isfinite(val) else 0.0


def measure_adverse_selection(trials: pd.DataFrame, book_by_sym: dict, btc_book: dict,
                              horizons) -> pd.DataFrame:
    """對 FILL（含 adverse_through）量 beta-residual post-fill mid 移動 → adverse_sel bps。

    bid fill（你做多）：adverse_sel(h) = −resid_move(h) ×1e4（mid 落 = 你買在跌前 = 被逆選）。
    ask fill（你做空）：adverse_sel(h) = +resid_move(h) ×1e4（mid 升 = 你賣在漲前 = 被逆選）。

    BUG-2 captured half-spread（核心修）：
      - normal fill：half_spread = |mid_place − p_quote| / mid_place ×1e4
        （你掛進去時的 quoted half-spread——你成交時 mid 仍在 mid_place,真實捕捉到）。
      - adverse_through：half_spread 改以「成交時 mid」為基準
        = |mid(t_fill) − p_quote| / mid(t_fill) ×1e4。
        因為簿被穿過去時 mid 已偏離 mid_place,拿 mid_place 算會「虛報」你捕捉到的 spread
        （甚至可能 p_quote 已落在新 mid 的另一側 → 真實捕捉為負）。改以 mid(t_fill) 為基準
        才反映你「被填當下相對 fair 的真實 edge」,避免 adverse_through 高估 captured spread
        而稀釋「逆選是二階」的結論。
      - 兩者皆額外保留 half_spread_at_place_bps / half_spread_at_fill_bps 供透明對照。
    resid_move = raw_move − beta·btc_move;beta = leak-free（< t_fill）。
    horizon mid 是 asof-backward l1 mid at t_fill+h（合法已實現量測,非 feature）。
    """
    filled = trials[trials["outcome"].isin(["fill", "adverse_through"])].copy()
    if filled.empty:
        return filled
    out_rows = []
    for _, r in filled.iterrows():
        sym = r["symbol"]
        g = book_by_sym.get(sym)
        if g is None:
            continue
        tf = int(r["t_fill"])
        i0 = _asof_idx(g["ts"], tf)
        ib0 = _asof_idx(btc_book["ts"], tf)
        if i0 < 0 or ib0 < 0:
            continue
        mid0 = g["mid"][i0]
        midb0 = btc_book["mid"][ib0]
        if not (np.isfinite(mid0) and mid0 > 0 and np.isfinite(midb0) and midb0 > 0):
            continue
        beta = _leakfree_beta_at(g, btc_book, tf)
        sign_s = 1.0 if r["side"] == "bid" else -1.0  # bid:long, ask:short
        # BUG-2：captured half-spread。normal fill 用 mid_place;adverse_through 用 mid(t_fill)。
        #   adverse_through 以「被填當下 mid」為基準,反映簿穿過後真實捕捉到的 spread(可為負)。
        hs_place = (r["mid_place"] - r["p_quote"]) / r["mid_place"] * 1e4
        hs_fill = (mid0 - r["p_quote"]) / mid0 * 1e4
        #   bid: 捕捉 = mid − p_quote（>0 才是真捕捉）;ask: 捕捉 = p_quote − mid。乘 sign_s 統一。
        hs_place_signed = sign_s * hs_place
        hs_fill_signed = sign_s * hs_fill
        if r["outcome"] == "adverse_through":
            half_spread_bps = hs_fill_signed
        else:
            half_spread_bps = hs_place_signed
        rec = {"symbol": sym, "side": r["side"], "outcome": r["outcome"],
               "half_spread_bps": float(half_spread_bps),
               "half_spread_at_place_bps": float(hs_place_signed),
               "half_spread_at_fill_bps": float(hs_fill_signed),
               "mid_fill": float(mid0),
               "t_fill": tf, "t_place": int(r["t_place"])}
        for h in horizons:
            th = tf + int(h * 1e9)
            ih = _asof_idx(g["ts"], th)
            ibh = _asof_idx(btc_book["ts"], th)
            if ih < 0 or ibh < 0:
                rec[f"adverse_sel_bps@{h}"] = np.nan
                continue
            midh = g["mid"][ih]
            midbh = btc_book["mid"][ibh]
            if not (np.isfinite(midh) and midh > 0 and np.isfinite(midbh) and midbh > 0):
                rec[f"adverse_sel_bps@{h}"] = np.nan
                continue
            raw_move = np.log(midh / mid0)
            btc_move = np.log(midbh / midb0)
            resid_move = raw_move - beta * btc_move
            # adverse_sel：bid → −resid;ask → +resid。統一 = −sign_s · resid。
            adverse = -sign_s * resid_move * 1e4
            rec[f"adverse_sel_bps@{h}"] = float(adverse)
        out_rows.append(rec)
    return pd.DataFrame(out_rows)


# ============================================================
# §4 informed-skip 信號（重用 core.ofi + BTC-lead，僅作 skip filter）
# ============================================================
def _build_signal_grid(tr_sym, l1_sym, btc_l1, t0, t1):
    """單 symbol 在 core 5s 網格上算 OFI@10s + BTC→alt 5s-lead 殘差信號（leak-free,shift(1)）。

    回 DataFrame index=grid ts(UTC), 欄 o(OFI@10s), btc_lead(BTC 上一根 5s resid 報酬)。
    純作 informed-skip 的 PIT 信號源（t_place 用 < t_place 的 bar）。
    """
    # 用 l1 mid 當 ob 來餵 build_grid（build_grid 需 mid/book_imb;這裡只要 mid 對齊 + OFI）。
    ob_sym = l1_sym[["ts", "symbol", "best_bid", "best_ask", "bid_size", "ask_size", "mid"]].copy()
    ob_sym["book_imb"] = (ob_sym["bid_size"] - ob_sym["ask_size"]) / \
                         (ob_sym["bid_size"] + ob_sym["ask_size"])
    g = core.build_grid(tr_sym, ob_sym, t0, t1)
    o = core.ofi(g, 10)  # OFI@10s（leak-free,[t-10,t)）
    # BTC 5s-lead：BTC 上一根 5s log-return（shift(1) → 嚴格 < t）。
    ob_btc = btc_l1[["ts", "symbol", "best_bid", "best_ask", "bid_size", "ask_size", "mid"]].copy()
    ob_btc["book_imb"] = (ob_btc["bid_size"] - ob_btc["ask_size"]) / \
                         (ob_btc["bid_size"] + ob_btc["ask_size"])
    # BTC trades 餵 px;但這裡只要 BTC mid grid 報酬。借 build_grid 的 mid 對齊。
    gb = core.build_grid(btc_l1.assign(price=btc_l1["mid"], qty=1.0, sgn=0.0)[
                             ["ts", "price", "qty", "sgn"]].assign(symbol="BTCUSDT"),
                         ob_btc, t0, t1)
    btc_ret = np.log(gb["mid"] / gb["mid"].shift(1)).shift(1)  # 上一根 5s 報酬 → 嚴格 < t
    df = pd.DataFrame({"o": o, "btc_lead": btc_ret.reindex(g.index)})
    return df


def _signal_at(sig_df, t_ns: int, col: str):
    """asof-backward 取 < t 的最後一根信號 bar（PIT；嚴格用 t 之前已知）。"""
    if sig_df is None or sig_df.empty or col not in sig_df:
        return np.nan
    idx = _ts_ns(sig_df.index)
    i = np.searchsorted(idx, t_ns, side="left") - 1  # 嚴格 < t（left → 不含等號 bar）
    if i < 0:
        return np.nan
    v = sig_df[col].to_numpy()[i]
    return float(v) if np.isfinite(v) else np.nan


def apply_informed_skip(trials, sig_by_sym, skip_quantile):
    """加 informed-skip 標記：信號強烈不利該側 → skip（不掛）。

    bid 掛單：信號強負（預測 mid 下殺）→ skip（會被逆選）。
    ask 掛單：信號強正（預測 mid 上漲）→ skip。
    用 OFI@10s 與 BTC-lead 任一落在「對你不利的 worst-tail quantile」即 skip。
    回加 informed_skip(bool) 欄的 trials copy。
    """
    trials = trials.copy()
    # 先收每 symbol 信號分布的 quantile 門檻。
    skip_flags = np.zeros(len(trials), dtype=bool)
    for sym, sig in sig_by_sym.items():
        if sig is None or sig.empty:
            continue
        o_vals = sig["o"].dropna()
        b_vals = sig["btc_lead"].dropna()
        if len(o_vals) < 10 or len(b_vals) < 10:
            o_lo = o_hi = b_lo = b_hi = np.nan
        else:
            o_lo = o_vals.quantile(skip_quantile)
            o_hi = o_vals.quantile(1 - skip_quantile)
            b_lo = b_vals.quantile(skip_quantile)
            b_hi = b_vals.quantile(1 - skip_quantile)
        sub_idx = trials.index[trials["symbol"] == sym]
        for ix in sub_idx:
            tp = int(trials.at[ix, "t_place"])
            side = trials.at[ix, "side"]
            o = _signal_at(sig, tp, "o")
            bl = _signal_at(sig, tp, "btc_lead")
            skip = False
            if side == "bid":
                # 強負信號 → 預測下殺 → skip bid。
                if np.isfinite(o) and np.isfinite(o_lo) and o <= o_lo:
                    skip = True
                if np.isfinite(bl) and np.isfinite(b_lo) and bl <= b_lo:
                    skip = True
            else:
                if np.isfinite(o) and np.isfinite(o_hi) and o >= o_hi:
                    skip = True
                if np.isfinite(bl) and np.isfinite(b_hi) and bl >= b_hi:
                    skip = True
            if skip:
                skip_flags[trials.index.get_loc(ix)] = True
    trials["informed_skip"] = skip_flags
    return trials


# ============================================================
# §3/§4/§5 per-symbol 聚合 + 報告組裝
# ============================================================
def _r(x, nd=4):
    if x is None:
        return None
    try:
        xf = float(x)
        if xf != xf:  # NaN
            return None
        return round(xf, nd)
    except (TypeError, ValueError):
        return None


def _net_block(sub, horizons, n_for_signif):
    """對一個 fill-subset（已 merge adverse）算 half_spread + per-horizon adverse + NET。

    回 dict：half_spread_bps + 每 horizon 的 adverse_sel / net_maker / net_taker / cost wall。
    half_spread 為 BUG-2 修正後的 signed captured half-spread（adverse_through 用 mid_fill）。
    n_for_signif 用「本 subset 的 n」判顯著性抑制（誠實:小樣本不出顯著宣稱）。
    """
    n = int(len(sub))
    out = {"n": n}
    if n == 0:
        out["half_spread_bps"] = None
        for h in horizons:
            out[f"adverse_sel_bps@{h}"] = None
            out[f"adverse_sel_median_bps@{h}"] = None
            out[f"edge_before_fees_bps@{h}"] = None
            out[f"net_bps@{h}_maker_exit"] = None
            out[f"net_bps@{h}_taker_exit"] = None
            out[f"break_even_fee_round_trip_bps@{h}_maker_exit"] = None
            out[f"break_even_maker_fee_bps_per_side@{h}_maker_exit"] = None
            out[f"fee_round_trip_shortfall_bps@{h}_maker_exit"] = None
            out[f"required_half_spread_bps@{h}_maker_exit"] = None
            out[f"required_maker_rebate_bps_per_side@{h}_maker_exit"] = None
            out[f"signif_suppressed@{h}"] = True
        return out
    half_spread = float(sub["half_spread_bps"].mean())
    out["half_spread_bps"] = _r(half_spread, 3)
    for h in horizons:
        col = f"adverse_sel_bps@{h}"
        if col in sub and sub[col].notna().any():
            adv_mean = float(sub[col].mean())
            adv_med = float(sub[col].median())
            edge_before_fees = half_spread - adv_mean
            net_maker = edge_before_fees - MAKER_FEE_ROUND_TRIP_BPS
            net_taker = half_spread - adv_mean - MAKER_FEE_BPS - TAKER_FEE_BPS
            break_even_fee_rt = edge_before_fees
            break_even_maker_fee = break_even_fee_rt / 2.0
            fee_rt_shortfall = MAKER_FEE_ROUND_TRIP_BPS - break_even_fee_rt
            required_half_spread = adv_mean + MAKER_FEE_ROUND_TRIP_BPS
            required_maker_rebate = max(0.0, -break_even_maker_fee)
        else:
            adv_mean = adv_med = edge_before_fees = net_maker = net_taker = np.nan
            break_even_fee_rt = break_even_maker_fee = fee_rt_shortfall = np.nan
            required_half_spread = required_maker_rebate = np.nan
        out[f"adverse_sel_bps@{h}"] = _r(adv_mean, 3)
        out[f"adverse_sel_median_bps@{h}"] = _r(adv_med, 3)
        out[f"edge_before_fees_bps@{h}"] = _r(edge_before_fees, 3)
        out[f"net_bps@{h}_maker_exit"] = _r(net_maker, 3)
        out[f"net_bps@{h}_taker_exit"] = _r(net_taker, 3)
        out[f"break_even_fee_round_trip_bps@{h}_maker_exit"] = _r(break_even_fee_rt, 3)
        out[f"break_even_maker_fee_bps_per_side@{h}_maker_exit"] = _r(break_even_maker_fee, 3)
        out[f"fee_round_trip_shortfall_bps@{h}_maker_exit"] = _r(fee_rt_shortfall, 3)
        out[f"required_half_spread_bps@{h}_maker_exit"] = _r(required_half_spread, 3)
        out[f"required_maker_rebate_bps_per_side@{h}_maker_exit"] = _r(required_maker_rebate, 3)
        out[f"signif_suppressed@{h}"] = bool(n < MIN_FILLS_FOR_SIGNIF)
    return out


def _policy_stats(trials_policy, adverse_by_fill, horizons, span_hours):
    """單一策略（naive=全部 / informed=非 skip）的 fill_rate + adverse + NET。

    BUG-1 修：n_fills_outcome（sim 判定的 fill+adverse_through 總數,fill_rate 分子）與
      n_fills_measured（成功 merge 上 adverse-selection 量測,即有 post-fill horizon mid 的子集）
      分開報。NET 統計只用 measured 子集,且 n 用 len(measured) 不用 len(filled)。
      measured_coverage = n_measured / n_outcome（量測覆蓋率,透明）。
    NOTE-B 修：pooled NET 混了 normal fill 與 adverse_through（經濟學不同）→ 強制拆三軌:
      pooled（全 measured） / fill_only / adverse_through_only,各帶獨立 n 與 NET。
    NET(h) = half_spread_captured − adverse_sel(h) − 2·maker_fee（maker-exit,4bp RT）。
    taker-exit 變體 = half_spread − adverse_sel − maker_fee − taker_fee（2+5.5bp）。
    """
    n_quotes = len(trials_policy)
    if n_quotes == 0:
        return None
    filled = trials_policy[trials_policy["outcome"].isin(["fill", "adverse_through"])]
    n_fills_outcome = len(filled)
    n_adverse_through_outcome = int((filled["outcome"] == "adverse_through").sum())
    fill_rate = n_fills_outcome / n_quotes
    # 對齊到 adverse_by_fill（用 (t_place, side, symbol) 對應）= 量測子集。
    if adverse_by_fill is not None and not adverse_by_fill.empty and n_fills_outcome > 0:
        key = ["symbol", "side", "t_place"]
        merged = filled.merge(adverse_by_fill, on=key, how="inner", suffixes=("", "_adv"))
        # outcome 欄在 filled 與 adverse 都有 → merge 後取 adverse 端（同值,保險用 filled 端）。
        if "outcome_adv" in merged:
            merged = merged.drop(columns=["outcome_adv"])
    else:
        merged = pd.DataFrame()
    n_fills_measured = int(len(merged))

    res = {
        "n_quotes": int(n_quotes),
        "n_fills_outcome": int(n_fills_outcome),
        "n_fills_measured": n_fills_measured,
        "measured_coverage": _r(n_fills_measured / n_fills_outcome, 3) if n_fills_outcome else None,
        "fill_rate": _r(fill_rate, 4),
        "n_adverse_through_outcome": n_adverse_through_outcome,
        "n_adverse_through_measured": int((merged["outcome"] == "adverse_through").sum())
                                      if not merged.empty else 0,
    }
    # NOTE-B 三軌拆分。
    fill_only = merged[merged["outcome"] == "fill"] if not merged.empty else merged
    adv_only = merged[merged["outcome"] == "adverse_through"] if not merged.empty else merged
    res["pooled_measured"] = _net_block(merged, horizons, n_fills_measured)
    res["fill_only"] = _net_block(fill_only, horizons, len(fill_only) if not merged.empty else 0)
    res["adverse_through_only"] = _net_block(adv_only, horizons,
                                             len(adv_only) if not merged.empty else 0)
    # NET / quoting-hour（用 fill_only mean net per fill × n_fill_only / span_hours;
    #   只計 normal fill 的可持續做市流,adverse_through 是被穿的壞 fill 不算正常 quoting yield）。
    for h in horizons:
        nm = res["fill_only"].get(f"net_bps@{h}_maker_exit")
        n_fo = res["fill_only"]["n"]
        per_hr = (nm * n_fo / span_hours) if (nm is not None and span_hours > 0) else None
        res[f"net_per_quoting_hour_usd_units@{h}_maker_fill_only"] = _r(per_hr, 3)
    return res


def _scorecard_cell(scope: str, queue_position: str, policy: str, track: str,
                    block: dict, horizon_s: int, *, symbol: str | None = None) -> dict | None:
    n = int(block.get("n") or 0)
    net = block.get(f"net_bps@{horizon_s}_maker_exit")
    half_spread = block.get("half_spread_bps")
    adverse = block.get(f"adverse_sel_bps@{horizon_s}")
    edge_before_fees = block.get(f"edge_before_fees_bps@{horizon_s}")
    if edge_before_fees is None and half_spread is not None and adverse is not None:
        edge_before_fees = float(half_spread) - float(adverse)
    fee_shortfall = block.get(f"fee_round_trip_shortfall_bps@{horizon_s}_maker_exit")
    if fee_shortfall is None and edge_before_fees is not None:
        fee_shortfall = MAKER_FEE_ROUND_TRIP_BPS - float(edge_before_fees)
    if net is None:
        return None
    return {
        "scope": scope,
        "symbol": symbol,
        "queue_position": queue_position,
        "policy": policy,
        "track": track,
        "n": n,
        "net_bps": _r(net, 3),
        "half_spread_bps": _r(half_spread, 3),
        "adverse_sel_bps": _r(adverse, 3),
        "edge_before_fees_bps": _r(edge_before_fees, 3),
        "fee_round_trip_shortfall_bps": _r(fee_shortfall, 3),
        "required_half_spread_bps": _r(
            block.get(f"required_half_spread_bps@{horizon_s}_maker_exit"),
            3,
        ),
        "required_maker_rebate_bps_per_side": _r(
            block.get(f"required_maker_rebate_bps_per_side@{horizon_s}_maker_exit"),
            3,
        ),
        "signif_suppressed": bool(block.get(f"signif_suppressed@{horizon_s}", n < MIN_FILLS_FOR_SIGNIF)),
    }


def fill_sim_edge_scorecard(report: dict, *, primary_horizon_s: int = 15) -> dict:
    """Compact reducer for the fill-sim report.

    This ranks already-computed fill_only maker-edge cells. It intentionally
    does not promote an alpha; it makes the closest-to-breakeven conditional
    slice visible so PM/QC can decide whether deeper research is warranted.
    """
    primary_queue = report.get("primary_queue_position") or DEFAULT_QUEUE_POSITION
    cells: list[dict] = []

    def add_policy(scope: str, queue_position: str, policy_name: str, policy: dict,
                   *, symbol: str | None = None):
        if not policy:
            return
        block = policy.get("fill_only") or {}
        cell = _scorecard_cell(
            scope,
            queue_position,
            policy_name,
            "fill_only",
            block,
            primary_horizon_s,
            symbol=symbol,
        )
        if cell is not None:
            cells.append(cell)

    for policy_name, policy in (report.get("pooled") or {}).items():
        add_policy("pooled_primary_queue", primary_queue, policy_name, policy)

    qdr = ((report.get("queue_dose_response") or {}).get("queue_positions") or {})
    for queue_position, qrow in qdr.items():
        for policy_name in ("naive", "informed_skip"):
            add_policy("pooled_queue_dose", queue_position, policy_name, qrow.get(policy_name) or {})

    for row in report.get("per_symbol") or []:
        symbol = row.get("symbol")
        for policy_name in ("naive", "informed_skip"):
            add_policy("per_symbol_primary_queue", primary_queue, policy_name, row.get(policy_name) or {},
                       symbol=symbol)

    ranked = sorted(cells, key=lambda c: (c["net_bps"] is not None, c["net_bps"]), reverse=True)
    positive = [c for c in ranked if c["net_bps"] is not None and c["net_bps"] > 0.0]
    positive_sample_gate = [
        c for c in positive
        if c["n"] >= MIN_FILLS_FOR_SIGNIF and not c["signif_suppressed"]
    ]
    back_ranked = [c for c in ranked if c["queue_position"] == DEFAULT_QUEUE_POSITION]
    if positive_sample_gate:
        status = "CONDITIONAL_POSITIVE_FILL_ONLY_CELL"
    elif positive:
        status = "POSITIVE_FILL_ONLY_CELL_BELOW_SAMPLE_GATE"
    else:
        status = "NO_POSITIVE_FILL_ONLY_CELL"
    return {
        "status": status,
        "primary_horizon_s": primary_horizon_s,
        "fee_round_trip_bps": MAKER_FEE_ROUND_TRIP_BPS,
        "min_fills_for_signif": MIN_FILLS_FOR_SIGNIF,
        "cells_evaluated": len(cells),
        "best_fill_only": ranked[0] if ranked else None,
        "best_back_of_queue_fill_only": back_ranked[0] if back_ranked else None,
        "positive_fill_only_cells": positive[:10],
        "positive_fill_only_cells_with_sample_gate": positive_sample_gate[:10],
        "nearest_to_breakeven_fill_only_cells": ranked[:10],
        "note": (
            "Research scorecard only. Positive cells need cross-regime CP-3 evidence, "
            "portfolio inventory-risk review, and formal QC/MIT/AI-E review before any strategy work."
        ),
    }


def run(l1, tr, ob, syms, clean_since, horizons, cadence_s, skip_quantile, since_ts, until_ts):
    """純計算入口：回 report dict。l1 為 raw（未過濾）;本函數做 §1.2 過濾並計數。"""
    l1_clean, fcounts = filter_l1_clean(l1, clean_since)

    # ob_top cross-check 用（§5.3）。
    ob_clean = core.clean_obtop(ob) if ob is not None and not ob.empty else pd.DataFrame()

    span_min = 0.0
    l1_min_ts = None
    l1_max_ts = None
    l1_max_age_hours = None
    if not l1_clean.empty:
        l1_min_ts = l1_clean["ts"].min()
        l1_max_ts = l1_clean["ts"].max()
        span_min = (l1_clean["ts"].max() - l1_clean["ts"].min()).total_seconds() / 60.0
        l1_max_age_hours = (
            pd.Timestamp.now(tz="UTC") - pd.Timestamp(l1_max_ts).tz_convert("UTC")
        ).total_seconds() / 3600.0
    span_hours = span_min / 60.0

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window": {"since": str(since_ts), "until": str(until_ts),
                   "clean_since": str(clean_since)},
        "params": {"cadence_s": cadence_s, "horizons_s": list(horizons),
                   "skip_quantile": skip_quantile, "maker_fee_bps_per_side": MAKER_FEE_BPS,
                   "taker_fee_bps_per_side": TAKER_FEE_BPS,
                   "fee_round_trip_bps": MAKER_FEE_ROUND_TRIP_BPS,
                   "cost_wall_definition": (
                       "edge_before_fees=half_spread-adverse; break_even_fee_round_trip=edge_before_fees; "
                       "fee_round_trip_shortfall=current_fee_round_trip-break_even_fee_round_trip; "
                       "negative break_even_maker_fee implies required maker rebate per side"
                   ),
                   "queue_positions_frac": QUEUE_POSITIONS,
                   "primary_queue_model": ("back-of-queue (size_ahead=Q0, conservative, "
                                           "NON-OPTIONAL default); front/mid also reported "
                                           "as dose-response sweep")},
        "data": {
            "trades_rows": int(len(tr)),
            **fcounts,
            "span_minutes": _r(span_min, 2),
            "l1_min_ts": l1_min_ts.isoformat() if l1_min_ts is not None else None,
            "l1_max_ts": l1_max_ts.isoformat() if l1_max_ts is not None else None,
            "l1_max_age_hours": _r(l1_max_age_hours, 3),
            "n_symbols": int(len(syms)),
        },
        "caveat": (
            "earliest structural read on full-L1 — NOT go/no-go. Single ~{:.0f}min window "
            "≈ 1 regime. n_fills small; no DSR/PSR/PBO/Sharpe. CP-3 verdict needs >=10-12 "
            "distinct vol/trend regime-days (~2-3wk+) of clean post-fix l1_events."
        ).format(span_min),
        "cp3_requirements": [
            ">=10-12 distinct regime-days clean post-fix l1_events (vol-quantile × trend-sign coverage)",
            "per-symbol n_fills >= 200 (or >=30/regime-cell) before any significance/DSR",
            "NET(h) > 0 ACROSS regimes (esp. trend-stress days) for informed-skew on wide-spread alts (DOT/UNI/LINK/ARB tier; majors too narrow)",
            "block-bootstrap CI (Politis-Romano, preserves autocorr) on NET + fill-cond adverse selection; DSR-deflate any param sweep (theta/timeout/horizon, K)",
            "robustness to back-of-queue conservatism + maker-vs-taker exit (report both)",
            "INVENTORY-RISK GAP: per-quote trials do NOT capture getting-run-over batch risk (correlated same-side fills in a trend; PC1~BTC, effective N~2) — separate CP-3 portfolio-risk lens required",
            "WIDE-SPREAD TENSION: widest-spread alts expected to show low fill_rate + high fill-conditional adverse selection — honest structural tension, not a bug",
        ],
    }

    if l1_clean.empty or tr.empty:
        report["abort"] = "empty l1_events (post-filter) or trades"
        return report
    if fcounts["crossed_after_filter"] != 0:
        report["abort"] = "ANTI-FOOL FAIL: crossed rows survived filter (crossed_after_filter != 0)"
        return report
    if core.BETA_SYM not in syms or l1_clean[l1_clean["symbol"] == core.BETA_SYM].empty:
        report["abort"] = f"no {core.BETA_SYM} l1_events — cannot beta-residualise (fail-loud)"
        return report

    # 建 per-symbol book + BTC book。
    book_by_sym = {}
    for s in syms:
        sub = l1_clean[l1_clean["symbol"] == s]
        if len(sub) >= 5:
            book_by_sym[s] = _build_mid_series(sub)
    btc_book = book_by_sym[core.BETA_SYM]

    t0 = l1_clean["ts"].min().ceil("s")
    t1 = l1_clean["ts"].max().floor("s")
    btc_l1 = l1_clean[l1_clean["symbol"] == core.BETA_SYM]

    # informed-skip 信號（queue-position 無關,只算一次)。
    sig_by_sym = {}
    sim_inputs = {}  # s -> (l1_s, tr_s)
    for s in syms:
        if s not in book_by_sym:
            continue
        l1_s = l1_clean[l1_clean["symbol"] == s]
        tr_s = tr[tr["symbol"] == s]
        if tr_s.empty:
            continue
        sim_inputs[s] = (l1_s, tr_s)
        try:
            sig_by_sym[s] = _build_signal_grid(tr_s, l1_s, btc_l1, t0, t1)
        except Exception as e:  # 信號失敗不該炸整個 sim（informed 退化為 naive）
            sig_by_sym[s] = None
            print(f"[warn] signal grid failed for {s}: {e}", file=sys.stderr)

    if not sim_inputs:
        report["abort"] = "no quote-trials generated (all symbols too thin)"
        return report

    # NOTE-A：queue dose-response — 同一掛單在 front / mid / back 三個身前隊列量各跑一次。
    def _run_one_position(frac):
        all_trials = []
        for s, (l1_s, tr_s) in sim_inputs.items():
            trials_s = simulate_symbol(l1_s, tr_s, cadence_s, size_ahead_frac=frac)
            if not trials_s.empty:
                all_trials.append(trials_s)
        if not all_trials:
            return None, None
        trials = pd.concat(all_trials, ignore_index=True)
        trials = apply_informed_skip(trials, sig_by_sym, skip_quantile)
        adverse = measure_adverse_selection(trials, book_by_sym, btc_book, horizons)
        return trials, adverse

    queue_results = {}   # pos -> (trials, adverse)
    for pos, frac in QUEUE_POSITIONS.items():
        tr_pos, adv_pos = _run_one_position(frac)
        if tr_pos is not None:
            queue_results[pos] = (tr_pos, adv_pos)
        print(f"[sim] queue_position={pos} (frac={frac}) "
              f"trials={0 if tr_pos is None else len(tr_pos)}", file=sys.stderr)

    if DEFAULT_QUEUE_POSITION not in queue_results:
        report["abort"] = "no quote-trials at back-of-queue (conservative default)"
        return report

    # 主 per_symbol / pooled = back-of-queue（保守預設,NON-OPTIONAL）。
    trials, adverse = queue_results[DEFAULT_QUEUE_POSITION]
    per_symbol = []
    for s in sorted(trials["symbol"].unique()):
        tsub = trials[trials["symbol"] == s]
        asub = adverse[adverse["symbol"] == s] if not adverse.empty else adverse
        naive = _policy_stats(tsub, asub, horizons, span_hours)
        informed = _policy_stats(tsub[~tsub["informed_skip"]], asub, horizons, span_hours)
        if naive is None:
            continue
        per_symbol.append({
            "symbol": s,
            "n_l1_events": int(len(l1_clean[l1_clean["symbol"] == s])),
            "naive": naive,
            "informed_skip": informed,
            "n_skipped": int(tsub["informed_skip"].sum()),
        })
    per_symbol.sort(key=lambda d: -d["naive"]["n_fills_outcome"])
    report["per_symbol"] = per_symbol
    report["primary_queue_position"] = DEFAULT_QUEUE_POSITION

    report["pooled"] = {
        "naive": _policy_stats(trials, adverse, horizons, span_hours),
        "informed_skip": _policy_stats(trials[~trials["informed_skip"]], adverse, horizons, span_hours),
    }

    # NOTE-A：queue dose-response 曲線（pooled naive + informed_skip，per queue position）。
    qdr = {"note": ("queue dose-response sweep: size_ahead = frac×Q0. "
                    "front=0.0 (most optimistic), mid=0.5 (L1-only approx of mid-queue; "
                    "no multi-level depth → not true 5bp-of-depth), back=1.0 (conservative default). "
                    "KEY question: does NET clear 0 (i.e., captured half-spread > fee+adverse) at ANY "
                    "queue position in this CALM regime?"),
           "queue_positions": {}}
    for pos, frac in QUEUE_POSITIONS.items():
        if pos not in queue_results:
            qdr["queue_positions"][pos] = {"size_ahead_frac": frac, "abort": "no trials"}
            continue
        tr_pos, adv_pos = queue_results[pos]
        qdr["queue_positions"][pos] = {
            "size_ahead_frac": frac,
            "naive": _policy_stats(tr_pos, adv_pos, horizons, span_hours),
            "informed_skip": _policy_stats(tr_pos[~tr_pos["informed_skip"]], adv_pos,
                                           horizons, span_hours),
        }
    report["queue_dose_response"] = qdr

    # ob_top cross-check（§5.3）：l1 mid vs ob_top mid 中位絕對差 bps。
    report["obtop_crosscheck"] = _obtop_crosscheck(l1_clean, ob_clean)
    primary_horizon = 15 if 15 in horizons else (horizons[0] if horizons else 15)
    report["edge_scorecard"] = fill_sim_edge_scorecard(
        report,
        primary_horizon_s=primary_horizon,
    )

    return report


def _obtop_crosscheck(l1_clean, ob_clean):
    """l1-derived mid vs ob_top mid 在抽樣時點的中位絕對差 bps（recorder-v2 BBO sanity）。"""
    if ob_clean is None or ob_clean.empty:
        return {"note": "no ob_top in window — cross-check skipped", "median_abs_discrepancy_bps": None}
    diffs = []
    syms = set(l1_clean["symbol"].unique()) & set(ob_clean["symbol"].unique())
    for s in list(syms)[:10]:  # 抽前 10 symbol 足夠 sanity
        l1s = l1_clean[l1_clean["symbol"] == s][["ts", "mid"]].sort_values("ts")
        obs = ob_clean[ob_clean["symbol"] == s][["ts", "mid"]].sort_values("ts").rename(
            columns={"mid": "ob_mid"})
        if l1s.empty or obs.empty:
            continue
        m = pd.merge_asof(obs, l1s, on="ts", direction="backward").dropna()
        if m.empty:
            continue
        d = (np.abs(m["ob_mid"] - m["mid"]) / m["mid"] * 1e4)
        diffs.append(d)
    if not diffs:
        return {"note": "no overlapping symbols", "median_abs_discrepancy_bps": None}
    alld = pd.concat(diffs)
    return {
        "n_compared_points": int(len(alld)),
        "median_abs_discrepancy_bps": _r(float(alld.median()), 3),
        "p90_abs_discrepancy_bps": _r(float(alld.quantile(0.90)), 3),
        "note": "l1-derived mid vs sampled ob_top mid; small = recorder-v2 BBO sane post-fix",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Queue-position fill-simulation (CP-3 MM go/no-go tool, read-only $0)")
    ap.add_argument("--hours", type=float, default=0, help="只取最近 N 小時；0=全部")
    ap.add_argument("--since", default=None, help="窗起點 ISO8601（優先於 --hours）")
    ap.add_argument("--until", default=None, help="窗終點 ISO8601（exclusive）")
    ap.add_argument("--clean-since", default=DEFAULT_CLEAN_SINCE,
                    help="post-fix ts floor（recorder-v2 crossed-fix restart）;'none'=關閉 ts floor")
    ap.add_argument("--cadence-s", type=float, default=DEFAULT_CADENCE_S,
                    help="掛單取樣節奏（秒）")
    ap.add_argument("--skip-quantile", type=float, default=DEFAULT_SKIP_QUANTILE,
                    help="informed-skip 的 worst-tail quantile（skip 最差此比例的信號）")
    ap.add_argument("--horizons", default="5,15,30", help="adverse-selection horizon 秒,逗號分隔")
    ap.add_argument("--min-l1-events", type=int, default=core.MIN_TRADES,
                    help="symbol 入選最低窗內 l1 事件數")
    ap.add_argument("--out", default="/tmp/openclaw/research/fillsim/fillsim_report.json")
    args = ap.parse_args(argv)

    horizons = tuple(int(x) for x in args.horizons.split(",") if x.strip())
    if args.clean_since.lower() == "none":
        clean_since = None
    else:
        cs = datetime.fromisoformat(args.clean_since)
        clean_since = cs if cs.tzinfo else cs.replace(tzinfo=timezone.utc)
        clean_since = pd.Timestamp(clean_since).tz_convert("UTC")

    conn = data_loader.connect()
    try:
        since_ts, until_ts = data_loader.resolve_window(conn, args.hours, args.since, args.until)
        print(f"[load] window since={since_ts} until={until_ts}", file=sys.stderr)
        syms = data_loader.liquid_l1_symbols(conn, since_ts, until_ts, args.min_l1_events)
        l1 = data_loader.load_l1_events(conn, since_ts, until_ts)
        tr = data_loader.load_trades(conn, since_ts, until_ts)
        ob = data_loader.load_obtop(conn, since_ts, until_ts)
    finally:
        conn.close()
    # BTC 必納入（殘差化基準）。
    if core.BETA_SYM not in syms and not l1.empty and (l1["symbol"] == core.BETA_SYM).any():
        syms = sorted(set(syms) | {core.BETA_SYM})
    print(f"[load] l1={len(l1)} trades={len(tr)} ob={len(ob)} symbols={len(syms)}", file=sys.stderr)
    if not l1.empty:
        l1 = l1[l1["symbol"].isin(syms)]
    if not tr.empty:
        tr = tr[tr["symbol"].isin(syms)]

    report = run(l1, tr, ob, syms, clean_since, horizons, args.cadence_s,
                 args.skip_quantile, since_ts, until_ts)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    # per-symbol CSV（back-of-queue 主結果攤平；nested 三軌 net-block 一併展開）。
    def _flatten_policy(prefix, pol):
        out = {}
        for k, v in pol.items():
            if isinstance(v, dict):
                for kk, vv in v.items():
                    out[f"{prefix}.{k}.{kk}"] = vv
            else:
                out[f"{prefix}.{k}"] = v
        return out

    if "per_symbol" in report and report["per_symbol"]:
        flat = []
        for ps in report["per_symbol"]:
            row = {"symbol": ps["symbol"], "n_l1_events": ps["n_l1_events"],
                   "n_skipped": ps["n_skipped"]}
            for pol in ("naive", "informed_skip"):
                row.update(_flatten_policy(pol, ps[pol]))
            flat.append(row)
        csv_path = os.path.splitext(args.out)[0] + "_per_symbol.csv"
        pd.DataFrame(flat).to_csv(csv_path, index=False)
        print(f"[artifact] {csv_path}", file=sys.stderr)

    # 人類可讀摘要（含 queue dose-response）。
    summary_keys = ("window", "params", "data", "caveat", "obtop_crosscheck",
                    "primary_queue_position", "edge_scorecard", "pooled",
                    "queue_dose_response")
    print(json.dumps({k: report[k] for k in summary_keys if k in report},
                     indent=2, ensure_ascii=False))
    if "abort" in report:
        print(f"\n[ABORT] {report['abort']}")
    print(f"\n[artifact] {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
