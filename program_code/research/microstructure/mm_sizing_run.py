#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mm_sizing_run — GROSS 做市 spread-capture pool sizing（$0 唯讀，one-off 研究腳本）。

MODULE_NOTE
模塊用途：
  量化「spread x FLOW = 每日有多少 spread-capture $ 可拿」（campaign-8 量了 spread 寬度
  卻從未量 pool 大小）。對每 symbol，用 clean_obtop + trades 算：
    - 時間加權 half-spread（bps，per-side）
    - half_spread > 2bp/4bp/side 的時間佔比
    - 每日 aggressor notional flow（buy+sell）
    - 每日 GROSS spread-capture pool = sum_trade(aggressor_notional x half_spread_at_t)
      net of 2bp/side maker fee（只算 half_spread>2bp 的 flow）
  以及全盤 ranking + realistic-slice 敏感度（1%/5%/20%）。

硬邊界（沿用 microstructure data_loader/core 契約）：
  - read-only：只 SELECT market.trades / market.ob_top（loader set_session readonly）。
  - clean_obtop NON-NEGOTIABLE：best_ask>best_bid AND bid_size>0 AND ask_size>0。
  - half_spread 在「成交時點」取「<= t 最後一筆乾淨快照」（merge_asof backward，leak-free，
    不看未來；做市掛單在成交前已知的盤口）。
  - GROSS：不扣 adverse selection（recorder-v2 才有 full-L1 fill 數據）。誠實標註。
  - 只寫 --out 指定的 JSON/CSV artifact，0 寫 market 表。

維度約定：
  - half_spread_bps = (best_ask - best_bid)/2 / mid * 1e4（per-side，做市單側可拿上限）。
  - maker fee = 2bp/side（無 rebate）。net half-spread = half_spread_bps - 2.0。
  - pool（net-of-fee, gross）= sum over trades where half_spread_bps>2:
        aggressor_notional(=price*qty in USD) * (half_spread_bps - 2.0) / 1e4
    解讀：每筆市價單付 ~half-spread 給對手被動側；做市方淨拿 (half_spread - maker_fee)。
  - 每日化：pool_per_day = pool_window * (24 / span_hours)。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

from . import core, data_loader

MAKER_FEE_BPS = 2.0   # per side
TAKER_FEE_BPS = 5.5   # per side（僅文檔/對照用）
NET_THRESH_BPS = 2.0  # half_spread 須 > maker fee 才 net-positive
WIDE_THRESH_BPS = 4.0  # campaign-8 「>4bp」對照閾


def _twa_and_pct(ob_clean_sym: pd.DataFrame):
    """單 symbol clean ob_top → 時間加權 half-spread + >2bp/>4bp 時間佔比。

    權重 = 每筆乾淨快照到下一筆的 dwell time（秒）；最後一筆無 dwell（補中位數，避免吃掉尾端）。
    half_spread_bps = (best_ask-best_bid)/2/mid*1e4。
    """
    ob = ob_clean_sym.sort_values("ts").reset_index(drop=True)
    if len(ob) < 2:
        return None
    hs = (ob["best_ask"] - ob["best_bid"]) / 2.0 / ob["mid"] * 1e4  # per-side bps
    dt = ob["ts"].shift(-1) - ob["ts"]
    dwell = np.array(dt.dt.total_seconds().values, dtype=float)  # 可寫副本（避免 read-only view）
    med = np.nanmedian(dwell[:-1]) if len(dwell) > 1 else 1.0
    dwell[-1] = med if np.isfinite(med) and med > 0 else 1.0
    dwell = np.clip(dwell, 0, None)
    w = dwell
    wsum = w.sum()
    if wsum <= 0:
        return None
    twa = float(np.average(hs.values, weights=w))
    pct_gt2 = float(w[(hs.values > NET_THRESH_BPS)].sum() / wsum * 100.0)
    pct_gt4 = float(w[(hs.values > WIDE_THRESH_BPS)].sum() / wsum * 100.0)
    return {
        "twa_half_spread_bps": twa,
        "median_half_spread_bps": float(np.median(hs.values)),
        "pct_time_gt2bp": pct_gt2,
        "pct_time_gt4bp": pct_gt4,
        "n_clean_snapshots": int(len(ob)),
    }


def _pool_for_symbol(tr_sym: pd.DataFrame, ob_clean_sym: pd.DataFrame):
    """單 symbol：把每筆 trade asof-merge 到「成交前最後一筆乾淨盤口」→ half_spread_at_t。

    回傳 dict（窗內累計量，未每日化）。
    """
    tr = tr_sym.sort_values("ts").reset_index(drop=True)
    ob = ob_clean_sym.sort_values("ts").reset_index(drop=True)
    if tr.empty or len(ob) < 2:
        return None
    obx = ob[["ts", "best_bid", "best_ask", "mid"]].copy()
    merged = pd.merge_asof(tr[["ts", "side", "price", "qty"]], obx, on="ts",
                           direction="backward")
    merged = merged.dropna(subset=["best_bid", "best_ask", "mid"])
    if merged.empty:
        return None
    hs = (merged["best_ask"] - merged["best_bid"]) / 2.0 / merged["mid"] * 1e4  # per-side bps
    notional = merged["price"] * merged["qty"]  # USD（quote = USDT≈USD）
    buy_notional = float(notional[merged["side"] == "Buy"].sum())
    sell_notional = float(notional[merged["side"] == "Sell"].sum())
    total_notional = float(notional.sum())

    # GROSS pool net of maker fee：只算 half_spread>2bp 的 flow，淨拿 (hs-2bp)。
    net_hs = (hs - MAKER_FEE_BPS).clip(lower=0.0)  # 只正貢獻
    contrib_mask = hs > NET_THRESH_BPS
    pool_net = float((notional[contrib_mask] * net_hs[contrib_mask]).sum() / 1e4)
    # 對照：gross-of-fee（每筆付 full half-spread 給被動側，未扣 maker fee）。
    pool_gross_of_fee = float((notional * hs).sum() / 1e4)
    # flow 佔比：有多少 notional 落在 half_spread>2bp 的時點。
    notional_gt2 = float(notional[contrib_mask].sum())

    # 成交量加權 half-spread（trade-time，對照 time-weighted）。
    vw_hs = float(np.average(hs.values, weights=notional.values)) if total_notional > 0 else float("nan")
    return {
        "n_trades_matched": int(len(merged)),
        "window_notional_usd": total_notional,
        "buy_notional_usd": buy_notional,
        "sell_notional_usd": sell_notional,
        "notional_gt2bp_usd": notional_gt2,
        "vol_weighted_half_spread_bps": vw_hs,
        "pool_net_window_usd": pool_net,
        "pool_gross_of_fee_window_usd": pool_gross_of_fee,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="GROSS MM spread-capture pool sizing (read-only)")
    ap.add_argument("--hours", type=float, default=0, help="只取最近 N 小時；0=全部")
    ap.add_argument("--since", default=None)
    ap.add_argument("--until", default=None)
    ap.add_argument("--min-trades", type=int, default=core.MIN_TRADES)
    ap.add_argument("--out", default="/tmp/openclaw/research/mm_sizing/mm_sizing_report.json")
    args = ap.parse_args(argv)

    conn = data_loader.connect()
    try:
        since_ts, until_ts = data_loader.resolve_window(conn, args.hours, args.since, args.until)
        print(f"[load] window since={since_ts} until={until_ts}", file=sys.stderr)
        syms_all = data_loader.liquid_symbols(conn, since_ts, until_ts, args.min_trades)
        tr = data_loader.load_trades(conn, since_ts, until_ts)
        ob = data_loader.load_obtop(conn, since_ts, until_ts)
    finally:
        conn.close()
    print(f"[load] trades={len(tr)} ob_raw={len(ob)} liquid_symbols={len(syms_all)}", file=sys.stderr)

    ob_raw_n = len(ob)
    ob = core.clean_obtop(ob)
    ob_clean_n = len(ob)

    if tr.empty or ob.empty:
        report = {"abort": "empty trades or ob_top after load/clean"}
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as f:
            json.dump(report, f, indent=2)
        print(json.dumps(report, indent=2))
        return 1

    span_h = (tr["ts"].max() - tr["ts"].min()).total_seconds() / 3600.0
    day_scale = 24.0 / span_h if span_h > 0 else float("nan")

    rows = []
    for s in syms_all:
        tr_s = tr[tr["symbol"] == s]
        ob_s = ob[ob["symbol"] == s]
        if len(tr_s) < args.min_trades or len(ob_s) < 2:
            continue
        twa = _twa_and_pct(ob_s)
        pool = _pool_for_symbol(tr_s, ob_s)
        if twa is None or pool is None:
            continue
        daily_flow = (pool["buy_notional_usd"] + pool["sell_notional_usd"]) * day_scale
        rows.append({
            "symbol": s,
            "n_trades": int(len(tr_s)),
            "n_clean_obtop": twa["n_clean_snapshots"],
            "twa_half_spread_bps": round(twa["twa_half_spread_bps"], 4),
            "median_half_spread_bps": round(twa["median_half_spread_bps"], 4),
            "vol_weighted_half_spread_bps": round(pool["vol_weighted_half_spread_bps"], 4),
            "pct_time_gt2bp": round(twa["pct_time_gt2bp"], 2),
            "pct_time_gt4bp": round(twa["pct_time_gt4bp"], 2),
            "daily_aggressor_notional_usd": round(daily_flow, 2),
            "daily_pool_net_usd": round(pool["pool_net_window_usd"] * day_scale, 2),
            "daily_pool_gross_of_fee_usd": round(pool["pool_gross_of_fee_window_usd"] * day_scale, 2),
        })

    df = pd.DataFrame(rows).sort_values("daily_pool_net_usd", ascending=False).reset_index(drop=True)

    total_daily_pool_net = float(df["daily_pool_net_usd"].sum())
    total_daily_pool_gross_of_fee = float(df["daily_pool_gross_of_fee_usd"].sum())
    total_daily_flow = float(df["daily_aggressor_notional_usd"].sum())
    n_gt2 = int((df["twa_half_spread_bps"] > NET_THRESH_BPS).sum())
    n_gt4 = int((df["twa_half_spread_bps"] > WIDE_THRESH_BPS).sum())

    report = {
        "window": {"since": str(since_ts), "until": str(until_ts), "span_hours": round(span_h, 3),
                   "day_scale": round(day_scale, 4)},
        "data": {
            "trades_rows": int(len(tr)),
            "ob_raw_rows": int(ob_raw_n),
            "ob_clean_rows": int(ob_clean_n),
            "ob_bad_tick_pct": round(100 * (ob_raw_n - ob_clean_n) / max(1, ob_raw_n), 2),
            "n_symbols_total": int(len(syms_all)),
            "n_symbols_sized": int(len(df)),
        },
        "fees": {"maker_bps_per_side": MAKER_FEE_BPS, "taker_bps_per_side": TAKER_FEE_BPS,
                 "net_thresh_bps": NET_THRESH_BPS},
        "totals": {
            "total_daily_pool_net_usd": round(total_daily_pool_net, 2),
            "total_daily_pool_gross_of_fee_usd": round(total_daily_pool_gross_of_fee, 2),
            "total_daily_aggressor_notional_usd": round(total_daily_flow, 2),
            "n_symbols_twa_halfspread_gt2bp": n_gt2,
            "n_symbols_twa_halfspread_gt4bp": n_gt4,
        },
        "realistic_slice_daily_net_usd": {
            "capture_1pct": round(total_daily_pool_net * 0.01, 2),
            "capture_5pct": round(total_daily_pool_net * 0.05, 2),
            "capture_20pct": round(total_daily_pool_net * 0.20, 2),
        },
        "per_symbol": df.to_dict(orient="records"),
        "boundary": ("GROSS — does NOT subtract adverse selection. Upper bound = you are the "
                     "ONLY maker capturing the full half-spread on every aggressor fill. "
                     "Adverse selection (filled when wrong) is recorder-v2-gated (needs full L1 "
                     "queue/fill data). This sizes spread x flow + which symbols; NOT MM profitability."),
    }

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    csv_path = os.path.splitext(args.out)[0] + "_per_symbol.csv"
    df.to_csv(csv_path, index=False)

    # 人類可讀摘要到 stdout。
    print(json.dumps({k: report[k] for k in ("window", "data", "fees", "totals",
                                              "realistic_slice_daily_net_usd")},
                     indent=2, ensure_ascii=False))
    print("\n=== TOP 15 by daily_pool_net_usd ===")
    cols = ["symbol", "twa_half_spread_bps", "pct_time_gt2bp", "pct_time_gt4bp",
            "daily_aggressor_notional_usd", "daily_pool_net_usd"]
    with pd.option_context("display.max_rows", None, "display.width", 200):
        print(df[cols].head(15).to_string(index=False))
    print(f"\n[artifact] {args.out}")
    print(f"[artifact] {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
