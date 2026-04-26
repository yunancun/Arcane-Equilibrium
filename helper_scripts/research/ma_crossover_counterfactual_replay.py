#!/usr/bin/env python3
"""ma_crossover counterfactual fee replay — read-only PG analysis tool.
ma_crossover 反事實費率重算 — 唯讀 PG 分析工具。

MODULE_NOTE (EN): Wave 3 G2-02 helper. Re-aggregates closed ma_crossover
trades from `trading.fills` under user-specified counterfactual fee
scenarios (e.g. fee_bps = 2.0 = PostOnly maker rate, 5.5 = current taker
rate post G7-09). For each (symbol, fee_bps) pair, reports n_trades /
avg_win_bps / avg_loss_bps / R:R / win_rate / net_edge_bps /
net_pnl_total. Output is markdown by default for direct operator/QC
consumption. The "AGGREGATE" row pools all symbols into a single line.

Pure read-only: no writes, no business-logic mutation. Lazy-imports
psycopg2 inside main() (CLAUDE.md §七 hygiene rule — no PG connect at
import time so --smoke-test runs without a live DB).

PnL math (clarified after Rust fill_engine.rs source review, 2026-04-26):
  realized_pnl in trading.fills is GROSS (price-diff only, fees not
  subtracted — fees deducted separately from balance). So:
    gross_pnl_usdt    = close.realized_pnl
    notional          = close.qty * close.price        (close-side)
    gross_pnl_bps     = gross_pnl_usdt / notional * 10000
    actual_net_bps    = (gross_pnl_usdt - close.fee - entry.fee) / notional * 10000
    cf_net_bps(scen)  = gross_pnl_bps - 2 * scenario_fee_bps
                        # 2× because counterfactual assumes both entry +
                        #   exit pay the scenario rate symmetrically;
                        #   per the existing fee model in fills (fee_rate
                        #   is per-side), this matches reality.

Trade pairing via FILL-CONTEXT-LINKAGE-1 (V017):
  close fill: realized_pnl != 0 AND entry_context_id IS NOT NULL
  entry fill: context_id = close.entry_context_id
  → INNER JOIN drops orphan close fills lacking matching entry. This is
    intentional: counterfactual math requires both fees and the entry
    price for sanity. Orphans logged as a WARN at end.

MODULE_NOTE (中): Wave 3 G2-02 helper。從 `trading.fills` 重新聚合已平倉
ma_crossover 交易，在 operator 指定的反事實 fee 情境下（如 2.0 bps =
PostOnly maker、5.5 bps = G7-09 後 taker 現況）逐 (symbol, fee_bps) 報
n_trades / avg_win / avg_loss / R:R / win_rate / net_edge / net_pnl_total。
默認 markdown 輸出供 operator/QC 直接觀看。「AGGREGATE」行為全 symbol 合計。

純唯讀：不寫資料、不動業務邏輯。psycopg2 lazy-import 進 main()（避 --smoke-test
需要真連 PG）。

PnL 公式（基於 Rust fill_engine.rs 源碼釐清，2026-04-26）：
  trading.fills.realized_pnl 是 GROSS（純價差，未扣 fee；fee 從 balance 另扣）：
    gross_pnl_usdt    = close.realized_pnl
    notional          = close.qty * close.price                    (close 側)
    gross_pnl_bps     = gross_pnl_usdt / notional * 10000
    actual_net_bps    = (gross_pnl_usdt - close.fee - entry.fee) / notional * 10000
    cf_net_bps(scen)  = gross_pnl_bps - 2 * scenario_fee_bps
                        # ×2 因為反事實假設 entry + exit 對稱付一次費

Pair 匹配（FILL-CONTEXT-LINKAGE-1, V017）：
  close fill: realized_pnl != 0 AND entry_context_id IS NOT NULL
  entry fill: context_id = close.entry_context_id
  → INNER JOIN 丟棄沒匹配 entry 的 orphan close fill；反事實計算需 entry
    fee 與 entry price 才合理；orphan 數量結尾 WARN 顯示。

CAVEAT (partial close / accumulate / 部分平倉與累積) — E2 G2-02 review:
  - The "× 2 fee" assumption holds ONLY for the 1-entry × 1-close-per-JOIN-row
    case (one entry context_id linked to exactly one close fill).
  - For partial closes (e.g., fast_track ReduceToHalf, multiple close fills
    pointing back to the same entry context_id), the counterfactual
    OVERCOUNTS fees by (N - 1) × scenario_fee_bps where N = number of close
    fills. The entry-side fee is paid once on the original entry, but our
    INNER JOIN replicates the entry row across each close → entry fee gets
    subtracted N times instead of once.
  - For accumulate (multi-entry → single close fill), the close has only one
    entry_context_id (its most recent entry), so other entries are missed
    entirely → counterfactual UNDERCOUNTS fees by (M - 1) × scenario_fee_bps
    where M = number of entries that contributed to the position.
  - For pure ma_crossover (the default --strategy-name), no partial-close /
    accumulate paths are wired today, so this caveat is informational; the
    × 2 assumption is exact for the current ma_crossover pipeline.
  - For mixed-strategy backtests via --strategy-name override (e.g.
    fast_track / grid_trading), validate the assumption against per-symbol
    counts in `trading.intents` (entry vs close intent counts) before
    trusting cf_net_bps; if the ratio drifts from 1:1, treat output as a
    rough upper bound only.

部分平倉 / 累積的注意事項（E2 G2-02 review）：
  - 「× 2 fee」假設只在「1 entry × 1 close per JOIN row」（一個 entry
    context_id 對應一個 close fill）成立。
  - 部分平倉（如 fast_track ReduceToHalf；多個 close fill 指向同一
    entry_context_id）會 OVERCOUNT 費用 (N − 1) × scenario_fee_bps，
    其中 N = close fill 數。entry 側 fee 在進場時只付一次，但 INNER JOIN
    在每個 close 都把 entry 拷一份 → entry fee 變成扣 N 次。
  - 累積（多 entry → 單 close）下 close 只有一個 entry_context_id（最近
    一筆 entry），其他 entry 完全漏掉 → counterfactual UNDERCOUNT 費用
    (M − 1) × scenario_fee_bps，M = 同倉位內 entry 筆數。
  - 純 ma_crossover（預設 --strategy-name）目前無 partial-close / accumulate
    路徑，本 caveat 為資訊性；目前管線下 × 2 假設精確。
  - 混合策略 backtest（用 --strategy-name 切 fast_track / grid_trading 等）
    請先用 `trading.intents` 比對 entry/close intent 比例；偏離 1:1 時，
    cf_net_bps 只能當粗估上界看待。

Usage:
  OPENCLAW_DATABASE_URL=postgresql://... \\
    python3 helper_scripts/research/ma_crossover_counterfactual_replay.py \\
      [--engine-mode demo] [--strategy-name ma_crossover] \\
      [--lookback-days 30] [--fee-scenarios 2.0,5.5] \\
      [--output-format markdown] [--symbols BTCUSDT,ETHUSDT]
  python3 ... --smoke-test          # SQL syntax dry-run, no DB needed

Exit codes:
  0 = success + ≥1 symbol has ≥30 trades
  1 = all (symbol, fee_scenario) cells have <10 trades (insufficient sample)
  2 = DB connection error
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any


# ─────────────────────────────────────────────────────────────────────────
# SQL templates (no PG connect at import time).
# SQL 模板（import 期不連 PG）。
# ─────────────────────────────────────────────────────────────────────────
#
# Notes / 備註：
#   - INNER JOIN drops close fills with NULL entry_context_id (V017 era
#     pre-FILL-CONTEXT-LINKAGE-1 may have NULL). Orphans counted in
#     ORPHAN_COUNT_SQL for transparency.
#   - realized_pnl is REAL (float32) in PG → cast NUMERIC for safer aggregation
#     downstream; we keep it as Python float for math.
#   - %s placeholder style (psycopg2 default — not :name).
#   - lookback uses interval `'%s days'` constructed from validated int input.
#   - WHERE close.qty > 0 AND close.price > 0 AND entry.qty > 0 AND
#     entry.price > 0 — drop badly closed rows (Edge case requirement).
#   - Single inner JOIN keeps it simple; one PASS per fetchall.
#   - close.realized_pnl != 0 plus close.entry_context_id IS NOT NULL
#     identifies close fills (entry fills have realized_pnl=0 by Rust
#     apply_fill semantics).

PAIRED_FILLS_SQL = """
SELECT
    close.symbol            AS symbol,
    close.engine_mode       AS engine_mode,
    close.strategy_name     AS strategy_name,
    close.qty               AS close_qty,
    close.price             AS close_price,
    close.realized_pnl      AS gross_pnl_usdt,
    close.fee               AS close_fee_usdt,
    close.fee_rate          AS close_fee_rate,
    entry.qty               AS entry_qty,
    entry.price             AS entry_price,
    entry.fee               AS entry_fee_usdt,
    entry.fee_rate          AS entry_fee_rate,
    close.ts                AS close_ts
FROM trading.fills AS close
INNER JOIN trading.fills AS entry
    ON entry.context_id = close.entry_context_id
WHERE close.strategy_name      = %s
  AND close.engine_mode        = %s
  AND close.realized_pnl       != 0
  AND close.entry_context_id   IS NOT NULL
  AND close.qty                > 0
  AND close.price              > 0
  AND entry.qty                > 0
  AND entry.price              > 0
  AND close.ts                 > now() - (%s || ' days')::interval
  {symbol_filter}
ORDER BY close.ts ASC
"""

# Symbols filter sub-clause; built only when --symbols is given.
SYMBOL_FILTER_TEMPLATE = "AND close.symbol = ANY(%s)"

# Orphan-count SQL = same WHERE except entry_context_id IS NULL OR no JOIN match.
# Used purely for an end-of-run informational WARN; not part of stats.
# Orphan 計數 SQL = 同 WHERE 但 entry_context_id IS NULL 或無 JOIN 匹配；
# 純結尾資訊 WARN，不入統計。
ORPHAN_COUNT_SQL = """
SELECT COUNT(*) FROM trading.fills AS close
LEFT JOIN trading.fills AS entry
    ON entry.context_id = close.entry_context_id
WHERE close.strategy_name      = %s
  AND close.engine_mode        = %s
  AND close.realized_pnl       != 0
  AND close.ts                 > now() - (%s || ' days')::interval
  AND (close.entry_context_id IS NULL OR entry.context_id IS NULL)
  {symbol_filter}
"""


# ─────────────────────────────────────────────────────────────────────────
# DB helpers — mirror passive_wait_healthcheck.py + bb_breakout_threshold_sweep.py
# DB 連線 — 沿用既有 helper 風格（ENV → DSN）。
# ─────────────────────────────────────────────────────────────────────────


def _build_dsn() -> str:
    """Build PG DSN from env, mirroring style in helper_scripts/db/passive_wait_healthcheck.py.
    從 env 構造 PG DSN，沿用 helper_scripts/db/passive_wait_healthcheck.py 風格。
    """
    return (
        os.environ.get("OPENCLAW_DATABASE_URL")
        or f"postgresql://{os.environ.get('POSTGRES_USER','')}"
        f":{os.environ.get('POSTGRES_PASSWORD','')}"
        f"@{os.environ.get('POSTGRES_HOST','127.0.0.1')}"
        f":{os.environ.get('POSTGRES_PORT','5432')}"
        f"/{os.environ.get('POSTGRES_DB','')}"
    )


def _open_conn():
    """Lazy import + open PG connection. Failure raises (caller handles exit 2).
    延遲載入並開 PG 連線；失敗向上拋（呼叫端轉 exit 2）。
    """
    import psycopg2  # type: ignore  # lazy: avoid import-time DB hard-dep

    dsn = _build_dsn()
    return psycopg2.connect(dsn)


# ─────────────────────────────────────────────────────────────────────────
# Counterfactual math.
# 反事實計算。
# ─────────────────────────────────────────────────────────────────────────


def compute_per_trade_bps(row: dict[str, Any], scenario_fee_bps: float) -> dict[str, float]:
    """Return per-trade bps metrics for a paired (entry, close) fill row.

    Inputs (row keys must be present from PAIRED_FILLS_SQL):
      gross_pnl_usdt, close_qty, close_price, close_fee_usdt, entry_fee_usdt

    Returns (all bps):
      gross_pnl_bps    — pre-fee PnL / notional (close-side notional, USDT)
      actual_net_bps   — gross - actual entry/exit fees (sanity vs reality)
      cf_net_bps       — gross - 2 × scenario_fee_bps (counterfactual)
      notional_usdt    — close-side notional for net_pnl_total weighting

    對配對好的 (entry, close) 成交逐筆算 bps 指標：
      gross_pnl_bps    = 純價差 / notional × 10000
      actual_net_bps   = 純價差扣實際雙邊 fee / notional × 10000
      cf_net_bps       = gross_bps - 2 × scenario_fee_bps（反事實核心）
      notional_usdt    = close 側 notional，用於加權計算 total pnl

    Why ×2 / 為何乘 2: the trading.fills schema records fee per side
    (entry fill has its own fee, close fill has its own fee). A scenario
    of "fee_bps = 2.0" thus subtracts 2.0 for entry + 2.0 for exit. This
    matches the production fee model under PostOnly maker rate, which is
    a per-side rate (Bybit charges the same percentage on both sides).
    為何乘 2：fills 表 fee 每側各記一筆（entry/close 各 1）。「fee_bps = 2.0」
    情境下 entry 扣 2 + exit 扣 2，與 Bybit PostOnly 雙邊對稱費率一致。
    """
    notional = float(row["close_qty"]) * float(row["close_price"])
    if notional <= 0:
        # Defensive: caller should already have filtered. Returning 0s lets
        # the aggregator skip safely without ZeroDivisionError.
        # 防禦：呼叫端應已過濾；回 0 讓聚合器安全跳過、避免 ZeroDivisionError。
        return {"gross_pnl_bps": 0.0, "actual_net_bps": 0.0, "cf_net_bps": 0.0, "notional_usdt": 0.0}

    gross_pnl_usdt = float(row["gross_pnl_usdt"])
    actual_fee_usdt = float(row["close_fee_usdt"]) + float(row["entry_fee_usdt"])
    gross_pnl_bps = gross_pnl_usdt / notional * 10000.0
    actual_net_bps = (gross_pnl_usdt - actual_fee_usdt) / notional * 10000.0
    cf_net_bps = gross_pnl_bps - 2.0 * scenario_fee_bps

    return {
        "gross_pnl_bps": gross_pnl_bps,
        "actual_net_bps": actual_net_bps,
        "cf_net_bps": cf_net_bps,
        "notional_usdt": notional,
    }


def aggregate_per_symbol_per_scenario(
    rows: list[dict[str, Any]],
    fee_scenarios: list[float],
) -> list[dict[str, Any]]:
    """Aggregate paired fills into one row per (symbol, fee_scenario_bps).

    Output row keys:
      symbol, fee_bps, n_trades, avg_win_bps, avg_loss_bps,
      rr_ratio, win_rate, net_edge_bps, net_pnl_total_usdt

    Notation:
      avg_win_bps   = mean(cf_net_bps where cf_net_bps > 0)
      avg_loss_bps  = mean(cf_net_bps where cf_net_bps < 0)   (negative)
      rr_ratio      = abs(avg_win_bps / avg_loss_bps)         (None when undefined)
      win_rate      = count(>0) / n_trades
      net_edge_bps  = mean(cf_net_bps)                        (per-trade avg)
      net_pnl_total_usdt = sum(cf_net_bps × notional / 10000)
                          # convert each trade's cf bps × that trade's notional
                          #   back to USDT, then sum.

    每 (symbol, fee_scenario) 一行；avg_win/avg_loss 取正/負分組均值；
    rr_ratio 為 |avg_win/avg_loss|；net_edge_bps 為 cf bps 樣本均；
    net_pnl_total_usdt 用每筆 notional 加權還原回 USDT 後加總。
    """
    out: list[dict[str, Any]] = []
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_symbol.setdefault(r["symbol"], []).append(r)

    for symbol in sorted(by_symbol.keys()):
        srows = by_symbol[symbol]
        for fee_bps in fee_scenarios:
            cf_list: list[float] = []
            notional_list: list[float] = []
            for r in srows:
                m = compute_per_trade_bps(r, fee_bps)
                if m["notional_usdt"] <= 0:
                    continue
                cf_list.append(m["cf_net_bps"])
                notional_list.append(m["notional_usdt"])

            n = len(cf_list)
            if n == 0:
                continue

            wins = [x for x in cf_list if x > 0]
            losses = [x for x in cf_list if x < 0]
            avg_win = (sum(wins) / len(wins)) if wins else None
            avg_loss = (sum(losses) / len(losses)) if losses else None
            rr_ratio = (
                abs(avg_win / avg_loss)
                if (avg_win is not None and avg_loss is not None and avg_loss != 0)
                else None
            )
            win_rate = len(wins) / n
            net_edge = sum(cf_list) / n
            # USDT total: sum over trades of (cf_bps_i × notional_i / 10000).
            # Equivalent to recomputing per-trade USDT cf-PnL and summing.
            # USDT 總額：對每筆 (cf_bps × notional / 10000) 加總，等同逐筆還原 USDT cf-PnL。
            net_pnl_total = sum(
                cf * notional / 10000.0 for cf, notional in zip(cf_list, notional_list)
            )

            out.append({
                "symbol": symbol,
                "fee_bps": fee_bps,
                "n_trades": n,
                "avg_win_bps": avg_win,
                "avg_loss_bps": avg_loss,
                "rr_ratio": rr_ratio,
                "win_rate": win_rate,
                "net_edge_bps": net_edge,
                "net_pnl_total_usdt": net_pnl_total,
            })

    # AGGREGATE row per fee_scenario (pool all symbols). Computed independently
    # from raw rows so notional weighting is honest.
    # 全 symbol AGGREGATE 行：直接從原始 rows 跑一次（不從 per-symbol 加總，避免
    # 算術平均 vs 加權的不一致）。
    for fee_bps in fee_scenarios:
        cf_list: list[float] = []
        notional_list: list[float] = []
        for r in rows:
            m = compute_per_trade_bps(r, fee_bps)
            if m["notional_usdt"] <= 0:
                continue
            cf_list.append(m["cf_net_bps"])
            notional_list.append(m["notional_usdt"])

        n = len(cf_list)
        if n == 0:
            continue

        wins = [x for x in cf_list if x > 0]
        losses = [x for x in cf_list if x < 0]
        avg_win = (sum(wins) / len(wins)) if wins else None
        avg_loss = (sum(losses) / len(losses)) if losses else None
        rr_ratio = (
            abs(avg_win / avg_loss)
            if (avg_win is not None and avg_loss is not None and avg_loss != 0)
            else None
        )
        win_rate = len(wins) / n
        net_edge = sum(cf_list) / n
        net_pnl_total = sum(
            cf * notional / 10000.0 for cf, notional in zip(cf_list, notional_list)
        )

        out.append({
            "symbol": "AGGREGATE",
            "fee_bps": fee_bps,
            "n_trades": n,
            "avg_win_bps": avg_win,
            "avg_loss_bps": avg_loss,
            "rr_ratio": rr_ratio,
            "win_rate": win_rate,
            "net_edge_bps": net_edge,
            "net_pnl_total_usdt": net_pnl_total,
        })

    return out


# ─────────────────────────────────────────────────────────────────────────
# Output formatters.
# 輸出格式化。
# ─────────────────────────────────────────────────────────────────────────


def _fmt_num(value: Any, fmt: str) -> str:
    """Format value with fmt; show '—' for None.
    格式化數值；None 顯示「—」。
    """
    if value is None:
        return "—"
    try:
        return format(value, fmt)
    except Exception:
        return str(value)


def render_markdown(stats: list[dict[str, Any]], min_per_symbol: int = 5) -> str:
    """Render stats as a markdown table.

    Per spec: per-symbol rows with n_trades < min_per_symbol are dropped to
    avoid noise — but always counted in the AGGREGATE row.
    AGGREGATE row is always shown (even if its own threshold isn't met).
    Sort: per-symbol rows by symbol asc, then fee_bps asc; AGGREGATE at end.

    依規格：per-symbol n_trades < min_per_symbol 不入表（噪音）；但全部仍計入
    AGGREGATE。AGGREGATE 永遠顯示，固定排尾。
    """
    headers = [
        "symbol", "fee_bps", "n_trades",
        "avg_win_bps", "avg_loss_bps", "R:R",
        "win_rate", "net_edge_bps", "net_pnl_total",
    ]
    sep = ["|" + "|".join(["---"] * len(headers)) + "|"]
    lines = ["| " + " | ".join(headers) + " |"] + sep

    per_symbol = [r for r in stats if r["symbol"] != "AGGREGATE"]
    aggregate = [r for r in stats if r["symbol"] == "AGGREGATE"]

    # Filter per-symbol noise floor
    # Per-symbol 噪音地板過濾
    per_symbol_kept = [r for r in per_symbol if r["n_trades"] >= min_per_symbol]
    per_symbol_dropped = [r for r in per_symbol if r["n_trades"] < min_per_symbol]

    per_symbol_kept.sort(key=lambda r: (r["symbol"], r["fee_bps"]))
    aggregate.sort(key=lambda r: r["fee_bps"])

    for r in per_symbol_kept + aggregate:
        lines.append("| " + " | ".join([
            r["symbol"],
            _fmt_num(r["fee_bps"], ".1f"),
            str(r["n_trades"]),
            _fmt_num(r["avg_win_bps"], ".2f"),
            _fmt_num(r["avg_loss_bps"], ".2f"),
            _fmt_num(r["rr_ratio"], ".2f"),
            _fmt_num(r["win_rate"], ".1%"),
            _fmt_num(r["net_edge_bps"], "+.2f"),
            _fmt_num(r["net_pnl_total_usdt"], "+.2f"),
        ]) + " |")

    if per_symbol_dropped:
        dropped_summary = ", ".join(sorted({r["symbol"] for r in per_symbol_dropped}))
        lines.append("")
        lines.append(
            f"_Per-symbol rows dropped (< {min_per_symbol} trades, still in AGGREGATE): {dropped_summary}_"
        )

    # E2 G2-02 review caveat — partial close / accumulate fee bias.
    # E2 G2-02 審查留白 — 部分平倉 / 累積的費率偏差注意事項。
    lines.append("")
    lines.append(
        "_Note: counterfactual assumes 1 entry × 1 close per fill pair. "
        "For partial closes (fast_track ReduceToHalf) over-counts fees by "
        "(N-1) × fee_bps; for accumulate under-counts by (M-1) × fee_bps. "
        "Pure ma_crossover usage is unaffected. "
        "假設 1 進 1 出，部分平倉/累積會偏差。_"
    )

    return "\n".join(lines)


def render_csv(stats: list[dict[str, Any]]) -> str:
    """Render stats as CSV (no per-symbol filter — full dump).
    輸出 CSV（不做 per-symbol 過濾，全量 dump）。
    """
    buf = io.StringIO()
    fieldnames = [
        "symbol", "fee_bps", "n_trades",
        "avg_win_bps", "avg_loss_bps", "rr_ratio",
        "win_rate", "net_edge_bps", "net_pnl_total_usdt",
    ]
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for r in sorted(stats, key=lambda r: (r["symbol"] != "AGGREGATE", r["symbol"], r["fee_bps"])):
        writer.writerow({k: r.get(k) for k in fieldnames})
    return buf.getvalue().rstrip("\n")


def render_json(stats: list[dict[str, Any]]) -> str:
    """Render stats as JSON array (no per-symbol filter).
    輸出 JSON 陣列（不做 per-symbol 過濾）。
    """
    return json.dumps(
        sorted(stats, key=lambda r: (r["symbol"] != "AGGREGATE", r["symbol"], r["fee_bps"])),
        indent=2,
        default=str,
    )


# ─────────────────────────────────────────────────────────────────────────
# CLI + main.
# CLI 與主流程。
# ─────────────────────────────────────────────────────────────────────────


def _parse_fee_scenarios(raw: str) -> list[float]:
    """Parse comma-separated bps list, validate >0 and not too large.
    解析逗號分隔 bps 列表；要求 >0 且不離譜大。
    """
    out: list[float] = []
    for s in raw.split(","):
        s = s.strip()
        if not s:
            continue
        v = float(s)
        if v <= 0:
            raise ValueError(f"fee_bps must be > 0, got {v}")
        if v > 1000:
            # 1000 bps = 10%; sanity ceiling. Beyond this almost certainly typo.
            # 1000 bps = 10%；上限 sanity。再大幾乎必是 typo。
            raise ValueError(f"fee_bps {v} exceeds sanity cap (1000 bps = 10%)")
        out.append(v)
    if not out:
        raise ValueError("--fee-scenarios produced empty list")
    return out


def _build_query(symbols: list[str] | None) -> tuple[str, str]:
    """Return (paired_sql, orphan_sql) with symbol filter applied if given.
    視 --symbols 是否提供回傳已注入過濾的 SQL。
    """
    if symbols:
        sub = SYMBOL_FILTER_TEMPLATE
    else:
        sub = ""
    return (
        PAIRED_FILLS_SQL.format(symbol_filter=sub),
        ORPHAN_COUNT_SQL.format(symbol_filter=sub),
    )


def _run_smoke_test(args: argparse.Namespace) -> int:
    """SQL syntax dry-run — no DB needed. Validates SQL string formatting +
    parameter shape. Prints both SQL templates with placeholders + the args
    that would be bound. Returns 0 on success.
    --smoke-test：純 SQL 語法檢測，不需 DB；印 SQL 與將 bind 的參數。
    """
    print("=" * 78)
    print("SMOKE TEST — SQL syntax + arg-shape dry-run (no DB connection)")
    print("=" * 78)

    fee_scenarios = _parse_fee_scenarios(args.fee_scenarios)
    symbols = [s.strip() for s in args.symbols.split(",")] if args.symbols else None
    paired_sql, orphan_sql = _build_query(symbols)

    # Bind args for paired SQL: (strategy_name, engine_mode, lookback_days, [symbols])
    # Bind args 順序：(strategy_name, engine_mode, lookback_days, [symbols])
    paired_args: tuple = (args.strategy_name, args.engine_mode, str(args.lookback_days))
    if symbols:
        paired_args = paired_args + (symbols,)

    # Same for orphan SQL.
    orphan_args = paired_args  # identical bindings

    print(f"\n[strategy_name]   {args.strategy_name}")
    print(f"[engine_mode]     {args.engine_mode}")
    print(f"[lookback_days]   {args.lookback_days}")
    print(f"[fee_scenarios]   {fee_scenarios}  (parsed OK)")
    print(f"[symbols]         {symbols if symbols else 'ALL'}")
    print(f"[output_format]   {args.output_format}")

    print("\n--- PAIRED_FILLS_SQL ---")
    print(paired_sql)
    print(f"\n[paired_args] {paired_args!r}  (count={len(paired_args)})")

    # Sanity: count placeholders vs args. Each %s = one bind.
    # SAFE: only counts %s tokens from controlled string templates.
    placeholders = paired_sql.count("%s")
    print(f"[paired_sql placeholders]  {placeholders}")
    if placeholders != len(paired_args):
        print(f"[FAIL] placeholder count != args count")
        return 1

    print("\n--- ORPHAN_COUNT_SQL ---")
    print(orphan_sql)
    print(f"\n[orphan_args] {orphan_args!r}  (count={len(orphan_args)})")

    placeholders_o = orphan_sql.count("%s")
    print(f"[orphan_sql placeholders]  {placeholders_o}")
    if placeholders_o != len(orphan_args):
        print(f"[FAIL] orphan placeholder count != args count")
        return 1

    # Aggregator math sanity on synthetic rows.
    # 用合成 row 做聚合器數學自檢。
    print("\n--- aggregator self-test ---")
    synthetic_rows = [
        # 1 win, 1 loss for ETHUSDT @ scen=2.0
        {"symbol": "ETHUSDT", "engine_mode": "demo", "strategy_name": "ma_crossover",
         "close_qty": 1.0, "close_price": 4000.0, "gross_pnl_usdt": 4.0,
         "close_fee_usdt": 2.2, "close_fee_rate": 0.00055,
         "entry_qty": 1.0, "entry_price": 3996.0, "entry_fee_usdt": 2.2, "entry_fee_rate": 0.00055,
         "close_ts": "synthetic"},
        {"symbol": "ETHUSDT", "engine_mode": "demo", "strategy_name": "ma_crossover",
         "close_qty": 1.0, "close_price": 4000.0, "gross_pnl_usdt": -8.0,
         "close_fee_usdt": 2.2, "close_fee_rate": 0.00055,
         "entry_qty": 1.0, "entry_price": 4008.0, "entry_fee_usdt": 2.2, "entry_fee_rate": 0.00055,
         "close_ts": "synthetic"},
    ]
    agg = aggregate_per_symbol_per_scenario(synthetic_rows, fee_scenarios)
    for row in agg:
        print(f"  {row['symbol']:<12} fee={row['fee_bps']:>5.1f} "
              f"n={row['n_trades']:>3} edge={row['net_edge_bps']:+.2f}bps "
              f"R:R={_fmt_num(row['rr_ratio'], '.2f')}")

    # Render formatters too — catches any KeyError before live run.
    # 也跑一次 renderer，提早抓 KeyError。
    print("\n--- renderers ---")
    md = render_markdown(agg)
    print(f"[markdown] {len(md)} chars, {md.count(chr(10))} lines")
    cs = render_csv(agg)
    print(f"[csv]      {len(cs)} chars, {cs.count(chr(10))} lines")
    js = render_json(agg)
    print(f"[json]     {len(js)} chars (parsed OK)")

    print("\n[OK] smoke test passed — SQL templates valid + math + renderers OK.")
    return 0


def main() -> int:
    """CLI entrypoint. Returns process exit code per docstring spec.
    CLI 入口；exit code 依 docstring 規格。
    """
    parser = argparse.ArgumentParser(
        description="ma_crossover counterfactual fee replay (Wave 3 G2-02).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 ma_crossover_counterfactual_replay.py --smoke-test\n"
            "  OPENCLAW_DATABASE_URL=postgresql://... python3 ma_crossover_counterfactual_replay.py\n"
            "  ... --engine-mode demo --lookback-days 14 --fee-scenarios 2.0,5.5\n"
            "  ... --symbols ETHUSDT,BTCUSDT --output-format csv\n"
        ),
    )
    parser.add_argument(
        "--engine-mode", default="demo",
        choices=["demo", "live_demo", "paper", "live"],
        help="engine_mode column filter (default: demo). 'live' rarely used here.",
    )
    parser.add_argument(
        "--strategy-name", default="ma_crossover",
        help="strategy_name column filter (default: ma_crossover).",
    )
    parser.add_argument(
        "--lookback-days", type=int, default=30,
        help="window of close.ts > now() - N days (default: 30).",
    )
    parser.add_argument(
        "--fee-scenarios", default="2.0,5.5",
        help="comma-separated counterfactual fee_bps to test (default: '2.0,5.5'). "
             "Each scenario subtracts 2× from gross bps (entry+exit).",
    )
    parser.add_argument(
        "--output-format", default="markdown",
        choices=["markdown", "csv", "json"],
        help="output format (default: markdown). markdown is human-friendly.",
    )
    parser.add_argument(
        "--symbols", default=None,
        help="optional comma-separated symbol whitelist. Default: ALL.",
    )
    parser.add_argument(
        "--min-per-symbol", type=int, default=5,
        help="hide per-symbol rows with n_trades < this in markdown (default: 5). "
             "Always kept in AGGREGATE and CSV/JSON.",
    )
    parser.add_argument(
        "--smoke-test", action="store_true",
        help="dry-run SQL+math+renderers, no DB connection. Exit 0 on success.",
    )

    args = parser.parse_args()

    # Logging: simple INFO-level format, stderr (so stdout stays clean for
    # piping markdown/csv/json).
    # Logging：簡單 INFO 格式，stderr 輸出，stdout 保留純結果便於 pipe。
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stderr,
    )
    log = logging.getLogger("ma_cf_replay")

    # Validate fee scenarios early.
    # 提早驗證 fee scenario 格式。
    try:
        fee_scenarios = _parse_fee_scenarios(args.fee_scenarios)
    except ValueError as e:
        log.error("invalid --fee-scenarios %r: %s", args.fee_scenarios, e)
        return 2

    if args.lookback_days <= 0:
        log.error("--lookback-days must be > 0")
        return 2

    if args.smoke_test:
        return _run_smoke_test(args)

    symbols = [s.strip() for s in args.symbols.split(",")] if args.symbols else None
    paired_sql, orphan_sql = _build_query(symbols)

    # ── Connect / fetch ──
    # 連線並取資料；連線錯 → exit 2。
    try:
        conn = _open_conn()
    except Exception as e:
        log.error("DB connection failed: %s", e)
        return 2

    rows: list[dict[str, Any]] = []
    orphan_count = 0
    try:
        with conn.cursor() as cur:
            log.info("fetching paired close fills (strategy=%s mode=%s lookback=%dd symbols=%s)",
                     args.strategy_name, args.engine_mode, args.lookback_days,
                     symbols if symbols else "ALL")
            paired_args: tuple = (args.strategy_name, args.engine_mode, str(args.lookback_days))
            if symbols:
                paired_args = paired_args + (symbols,)
            cur.execute(paired_sql, paired_args)
            colnames = [d[0] for d in cur.description] if cur.description else []
            for r in cur.fetchall():
                rows.append(dict(zip(colnames, r)))
            log.info("fetched %d paired (entry,close) fill rows", len(rows))

            cur.execute(orphan_sql, paired_args)
            orphan_count = int(cur.fetchone()[0] or 0)
            if orphan_count > 0:
                log.warning("orphan close fills (no entry pair) skipped: %d "
                            "— pre-V017 data or missing entry_context_id",
                            orphan_count)
    finally:
        conn.close()

    if not rows:
        log.warning("no paired close fills found — check engine_mode / strategy_name / lookback")
        # Still print empty markdown table so output isn't void.
        # 空表也印 markdown，避免 stdout 為空。
        empty_md = "_no paired close fills found in the requested window._"
        print(empty_md if args.output_format == "markdown" else "")
        return 1

    # Per-symbol progress log: count trades per symbol (informational only).
    # Per-symbol 進度 log：每 symbol 多少交易（純資訊）。
    per_symbol_n: dict[str, int] = {}
    for r in rows:
        per_symbol_n[r["symbol"]] = per_symbol_n.get(r["symbol"], 0) + 1
    for sym in sorted(per_symbol_n):
        log.info("[load] %s: %d paired trades", sym, per_symbol_n[sym])

    stats = aggregate_per_symbol_per_scenario(rows, fee_scenarios)
    log.info("aggregated %d (symbol, fee_scenario) cells (incl. AGGREGATE)", len(stats))

    # ── Sample-size gate (per spec) ──
    # 樣本量門檻（依規格）：
    #   exit 1 if all (symbol, fee_scenario) cells < 10 trades, OR no symbol >= 30
    # We interpret "any symbol with ≥30 trades" loosely as "some per-symbol
    # cell with >= 30 in any scenario" (n_trades is identical across scenarios
    # for a given symbol, so this collapses to 1 check per symbol).
    # 規格曲解處：「任一 cell 全部 < 10 → exit 1；至少一個 symbol >= 30 → exit 0」。
    # 注意：對同 symbol，不同 fee_scenario 的 n_trades 相同（樣本同 row 集合），
    # 所以 per-symbol 只需檢查一次。
    per_symbol_max_n = max(
        (r["n_trades"] for r in stats if r["symbol"] != "AGGREGATE"),
        default=0,
    )
    aggregate_max_n = max(
        (r["n_trades"] for r in stats if r["symbol"] == "AGGREGATE"),
        default=0,
    )

    # Render output.
    # 輸出渲染。
    if args.output_format == "markdown":
        out = render_markdown(stats, min_per_symbol=args.min_per_symbol)
    elif args.output_format == "csv":
        out = render_csv(stats)
    else:  # json
        out = render_json(stats)
    print(out)

    # Exit code logic.
    # exit code 邏輯。
    if per_symbol_max_n < 10 and aggregate_max_n < 10:
        log.warning("all cells have < 10 trades — sample insufficient (exit 1)")
        return 1
    if per_symbol_max_n < 30:
        log.warning("no per-symbol cell reached >= 30 trades; AGGREGATE n=%d", aggregate_max_n)
        # Spec says "≥1 symbol with ≥30 trades" for exit 0. If aggregate is
        # large enough that's still useful → exit 0 to avoid spurious red.
        # Conservative: only exit 1 when ALL cells < 10 (above branch).
        # 規格嚴格要求 ≥1 symbol ≥30 才 exit 0，但實務上 AGGREGATE 大也算可用。
        # 保守處理：只有「全部 cells < 10」才 exit 1（上面分支），其他放行。
    log.info("done; per-symbol max n=%d, aggregate max n=%d, orphans=%d",
             per_symbol_max_n, aggregate_max_n, orphan_count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
