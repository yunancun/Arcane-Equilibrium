#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""microstructure.harness — thin runner CLI（CP-1/CP-2/CP-3 一條可重現命令）。

MODULE_NOTE
模塊用途：
  把 core.py（leak-free 純函數）+ data_loader.py（read-only PG）串成一條命令，
  輸出固定 schema 的 report JSON，供 campaign-8 microstructure lead 在
  regime 覆蓋累積過程中（CP-1/CP-2/CP-3）反覆 re-verify 同一信號。

headline 變數（task 指定）：
  - OFI@10s residual-IC（非重疊）+ Fisher-z t（cell w=10,h=10,mid）。
  - per-symbol same-sign fraction（OFI@10s）。
  - book-imb@30s residual-IC（非重疊）+ t（cell w=30,h=30,mid）。

用法（read-only，$0）：
  # 全量已累積資料
  python3 -m program_code.research.microstructure.harness \\
      --out /tmp/openclaw/research/microstructure/cp_report.json
  # 最近 N 小時
  python3 -m program_code.research.microstructure.harness --hours 24 --out <path>
  # 顯式窗（ISO8601 UTC）
  python3 -m program_code.research.microstructure.harness \\
      --since 2026-06-16T00:00:00 --until 2026-06-17T00:00:00 --out <path>

硬邊界：read-only（loader set_session readonly）；只寫 --out 指定的 report artifact；
  2h≈1 regime → 輸出帶 caveat，禁 PBO/DSR/Sharpe / GO-NO-GO 結論。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

import numpy as np

from . import core, data_loader


def _cell(tr, ob, syms, w, h, stride, pxcol="mid"):
    """算單一 (w,h) cell 的 OFI / book_imb 非重疊 pooled IC/t。"""
    frames, _cross = core.assemble_frames(tr, ob, syms, w, h, pxcol)
    ic_o, t_o, n_o = core.pooled_ic_t(frames, "o", stride)
    ic_b, t_b, n_b = core.pooled_ic_t(frames, "b", stride)
    return frames, {
        "params": {"w_s": w, "h_s": h, "px": pxcol, "stride_bars": stride,
                   "stride_seconds": stride * core.GRID_STEP_S},
        "n_cross_symbols": len(frames),
        "ofi": {"resid_ic_nonoverlap": _r(ic_o, 5), "t_nonoverlap": _r(t_o, 3), "n_nonoverlap": n_o},
        "book_imb": {"resid_ic_nonoverlap": _r(ic_b, 5), "t_nonoverlap": _r(t_b, 3), "n_nonoverlap": n_b},
    }


def _r(x, nd):
    """round 但保 None / NaN 為 None（JSON 友善）。"""
    if x is None:
        return None
    try:
        if isinstance(x, float) and (x != x):  # NaN
            return None
    except Exception:
        pass
    return round(float(x), nd)


def run(tr, ob, syms_all, since_ts, until_ts):
    """純計算入口（input 已載入的 DataFrame）：回 report dict。"""
    ob_raw_n = len(ob)
    ob = core.clean_obtop(ob)
    ob_clean_n = len(ob)
    span_h = ((tr["ts"].max() - tr["ts"].min()).total_seconds() / 3600.0) if not tr.empty else 0.0

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window": {"since": str(since_ts), "until": str(until_ts)},
        "data": {
            "trades_rows": int(len(tr)),
            "ob_raw_rows": int(ob_raw_n),
            "ob_clean_rows": int(ob_clean_n),
            "ob_bad_tick_pct": _r(100 * (ob_raw_n - ob_clean_n) / max(1, ob_raw_n), 2),
            "n_symbols_total": int(len(syms_all)),
            "span_hours": _r(span_h, 3),
        },
        "caveat": ("scout only — short span ≈ few regime samples. NO PBO/DSR/Sharpe / GO-NO-GO. "
                   "Real verification needs recorder-v2 full-L1 + >=10-12 regime-day coverage "
                   "(CP-1/CP-2/CP-3)."),
    }

    if tr.empty or ob.empty:
        report["abort"] = "empty trades or ob_top after load/clean"
        return report

    # headline OFI@10s cell（w=10,h=10）。
    stride10 = core.nonoverlap_stride(10, 10)
    frames10, cell10 = _cell(tr, ob, syms_all, 10, 10, stride10)
    report["ofi_at_10s"] = cell10

    # OFI@10s per-symbol same-sign fraction。
    pooled_sign = int(np.sign(cell10["ofi"]["resid_ic_nonoverlap"] or 0.0))
    report["ofi_at_10s_per_symbol"] = core.per_symbol_same_sign(
        frames10, "o", pooled_sign, stride10)

    # book-imb@30s cell（w=30,h=30）。
    stride30 = core.nonoverlap_stride(30, 30)
    _frames30, cell30 = _cell(tr, ob, syms_all, 30, 30, stride30)
    report["book_imb_at_30s"] = cell30

    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description="Campaign-8 microstructure leak-free CP re-verification harness")
    ap.add_argument("--hours", type=float, default=0,
                    help="只取最近 N 小時（相對 max(ts)）；0=全部已累積資料")
    ap.add_argument("--since", default=None, help="窗起點 ISO8601 UTC（與 --until 並用，優先於 --hours）")
    ap.add_argument("--until", default=None, help="窗終點 ISO8601 UTC（exclusive）")
    ap.add_argument("--min-trades", type=int, default=core.MIN_TRADES,
                    help="symbol 入選最低窗內 trade 數")
    ap.add_argument("--out", default="/tmp/openclaw/research/microstructure/cp_report.json",
                    help="report artifact 輸出路徑（唯一寫入面）")
    args = ap.parse_args(argv)

    conn = data_loader.connect()
    try:
        since_ts, until_ts = data_loader.resolve_window(conn, args.hours, args.since, args.until)
        print(f"[load] window since={since_ts} until={until_ts} ...", file=sys.stderr)
        syms_all = data_loader.liquid_symbols(conn, since_ts, until_ts, args.min_trades)
        tr = data_loader.load_trades(conn, since_ts, until_ts)
        ob = data_loader.load_obtop(conn, since_ts, until_ts)
    finally:
        conn.close()
    # 只保留入選 symbol（與 liquid_symbols 一致），減少 pool 噪音。
    if not tr.empty:
        tr = tr[tr["symbol"].isin(syms_all)]
    if not ob.empty:
        ob = ob[ob["symbol"].isin(syms_all)]
    print(f"[load] trades={len(tr)} ob={len(ob)} symbols={len(syms_all)}", file=sys.stderr)

    report = run(tr, ob, syms_all, since_ts, until_ts)

    import os
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\n[artifact] {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
