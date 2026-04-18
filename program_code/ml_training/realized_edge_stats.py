"""
Realized Edge Statistics — per (strategy, symbol) round-trip PnL distribution.
實現邊際統計 — 每 (策略, 幣種) 的往返 PnL 分布。

MODULE_NOTE (EN): Phase 5 P0 (2026-04-08 Edge Crisis). Queries trading.fills to
  compute per-(strategy, symbol) realized edge in basis points. Round-trip = entry
  fill + matching exit fill (paired by symbol + side reversal). Feeds james_stein_estimator.py.
MODULE_NOTE (中): Phase 5 P0（Edge 危機）。查詢 trading.fills，計算每 (策略, 幣種)
  的實現邊際（bps）。往返 = 入場成交 + 配對出場成交。輸出給 james_stein_estimator.py。

Usage / 使用：
    python -m program_code.ml_training.realized_edge_stats [--days N] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database connection / 數據庫連接
# ---------------------------------------------------------------------------

def _get_db_conn():
    """
    Return a psycopg2 connection using environment variables.
    使用環境變量建立 psycopg2 連接。
    """
    import psycopg2  # type: ignore[import]

    host = os.environ.get("PG_HOST", "localhost")
    port = int(os.environ.get("PG_PORT", "5432"))
    dbname = os.environ.get("PG_DB", "trading_ai")
    user = os.environ.get("PG_USER", "trading_admin")
    password = os.environ.get("PG_PASSWORD", "")

    return psycopg2.connect(
        host=host, port=port, dbname=dbname, user=user, password=password
    )


# ---------------------------------------------------------------------------
# Data structures / 數據結構
# ---------------------------------------------------------------------------

@dataclass
class RoundTripRecord:
    """
    A single completed round-trip (entry + exit).
    一筆完整往返（入場 + 出場）。
    """
    strategy_name: str
    symbol: str
    # In basis points (1 bps = 0.01%) relative to notional at entry
    gross_pnl_bps: float      # gross PnL / bps / 毛利 bps
    entry_fee_bps: float      # entry fill fee / bps / 入場手續費 bps
    exit_fee_bps: float       # exit fill fee / bps / 出場手續費 bps
    net_pnl_bps: float        # net PnL after both fees / 扣費後淨利 bps
    entry_ts: datetime
    exit_ts: Optional[datetime]
    notional_usd: float       # entry notional / 入場名義金額


@dataclass
class EdgeStats:
    """
    Aggregated edge statistics for one (strategy, symbol) cell.
    單個 (策略, 幣種) 格子的聚合邊際統計。
    """
    strategy_name: str
    symbol: str
    n: int                         # sample count / 樣本數
    mean_net_bps: float            # mean realized net edge / 均值淨邊際 bps
    std_net_bps: float             # sample std dev / 樣本標準差 bps
    mean_gross_bps: float          # mean gross edge (before fees) / 均值毛邊際 bps
    mean_fee_bps: float            # mean total fee (entry + exit) / 均值手續費 bps
    # Raw per-observation values (for JS shrinkage input)
    # 原始觀測值（供 JS 收縮輸入）
    raw_bps_list: list[float] = field(default_factory=list)
    # 5-01: Per-parameter metrics for multi-dimensional JS shrinkage + k-means.
    # 5-01：多維 JS 收縮 + k-means 的逐參數指標。
    win_rate: float = 0.0          # fraction of round-trips with positive net PnL / 盈利往返佔比
    avg_win_bps: float = 0.0       # mean net_pnl_bps for winning trades / 盈利交易均值 bps
    avg_loss_bps: float = 0.0      # mean net_pnl_bps for losing trades / 虧損交易均值 bps


# ---------------------------------------------------------------------------
# Core query: fetch fills and reconstruct round-trips
# ---------------------------------------------------------------------------

_FILLS_QUERY = """
SELECT
    f.ts,
    f.symbol,
    COALESCE(f.strategy_name, 'unknown') AS strategy_name,
    f.side,
    f.qty,
    f.price,
    f.fee,
    f.realized_pnl,
    f.is_paper,
    f.engine_mode
FROM trading.fills f
WHERE f.ts >= %(since)s
  AND f.engine_mode = %(engine_mode)s
ORDER BY f.symbol, f.ts ASC
"""


def _bps(value_usd: float, notional_usd: float) -> float:
    """Convert USD value to basis points relative to notional. / USD 值轉換為相對名義金額的 bps。"""
    if notional_usd <= 0:
        return 0.0
    return (value_usd / notional_usd) * 10_000.0


def _pair_round_trips(fills: list[dict]) -> list[RoundTripRecord]:
    """
    Pair entry and exit fills for a single symbol using a FIFO queue.
    Use realized_pnl on exit fills (non-zero) to determine the gross PnL.
    使用 FIFO 隊列為單個幣種配對入場和出場成交。

    Strategy: group fills by (symbol, strategy_name). Within each group,
    exit fills (realized_pnl != 0 OR strategy_name starts with risk_close/
    stop_trigger/strategy_close) are matched against open positions.
    策略：按 (symbol, strategy_name) 分組。出場成交（realized_pnl != 0 或 strategy_name
    以 risk_close/stop_trigger/strategy_close 開頭）與入場成交的倉位配對。
    """
    records: list[RoundTripRecord] = []

    # Group by symbol
    by_symbol: dict[str, list[dict]] = {}
    for f in fills:
        by_symbol.setdefault(f["symbol"], []).append(f)

    for symbol, sym_fills in by_symbol.items():
        # FIFO queue of open entry fills: (strategy_name, qty_remaining, entry_price, entry_fee, ts)
        open_entries: list[dict] = []

        for fill in sorted(sym_fills, key=lambda x: x["ts"]):
            qty = float(fill["qty"])
            price = float(fill["price"])
            fee = float(fill["fee"])
            realized_pnl = float(fill["realized_pnl"])
            strategy_name = fill["strategy_name"]
            ts = fill["ts"]

            # EDGE-P2-1: close tags now use prefixed format:
            #   risk_close:*  — risk evaluator / fast-track / halt
            #   stop_trigger:* — StopManager hard/trailing/time stop
            #   strategy_close:* — strategy-driven exit
            # Legacy fills may still use old unprefixed names (stop_/time_stop).
            is_exit = (
                realized_pnl != 0.0
                or strategy_name.startswith("risk_close")
                or strategy_name.startswith("stop_trigger")
                or strategy_name.startswith("strategy_close")
                or strategy_name.startswith("stop_")
                or strategy_name.startswith("time_stop")
            )

            if not is_exit:
                # Entry fill — push to queue
                open_entries.append({
                    "strategy_name": strategy_name,
                    "qty_remaining": qty,
                    "entry_price": price,
                    "entry_fee": fee,
                    "ts": ts,
                })
            else:
                # Exit fill — match against oldest entry (FIFO)
                exit_qty_remaining = qty
                while exit_qty_remaining > 1e-9 and open_entries:
                    entry = open_entries[0]
                    matched_qty = min(exit_qty_remaining, entry["qty_remaining"])
                    fraction = matched_qty / entry["qty_remaining"] if entry["qty_remaining"] > 0 else 0

                    entry_notional = entry["entry_price"] * matched_qty
                    # Gross PnL for this matched portion (price difference)
                    # Note: realized_pnl from DB is for the whole exit fill, so we apportion
                    gross_pnl_usd = realized_pnl * (matched_qty / qty) if qty > 0 else 0.0
                    entry_fee_usd = entry["entry_fee"] * fraction
                    exit_fee_usd = fee * (matched_qty / qty) if qty > 0 else 0.0

                    if entry_notional > 0:
                        rec = RoundTripRecord(
                            strategy_name=entry["strategy_name"],
                            symbol=symbol,
                            gross_pnl_bps=_bps(gross_pnl_usd, entry_notional),
                            entry_fee_bps=_bps(entry_fee_usd, entry_notional),
                            exit_fee_bps=_bps(exit_fee_usd, entry_notional),
                            net_pnl_bps=_bps(
                                gross_pnl_usd - entry_fee_usd - exit_fee_usd,
                                entry_notional,
                            ),
                            entry_ts=entry["ts"],
                            exit_ts=ts,
                            notional_usd=entry_notional,
                        )
                        records.append(rec)

                    entry["qty_remaining"] -= matched_qty
                    exit_qty_remaining -= matched_qty

                    if entry["qty_remaining"] < 1e-9:
                        open_entries.pop(0)

    return records


def compute_edge_stats(
    days_back: int = 30,
    min_samples: int = 3,
    engine_mode: str = "demo",
) -> dict[tuple[str, str], EdgeStats]:
    """
    Query fills for a specific engine_mode and compute per-(strategy, symbol) realized edge stats.
    查詢指定 engine_mode 的成交並計算每 (策略, 幣種) 的實現邊際統計。

    Args:
        days_back: How many calendar days to look back. / 向前查詢的天數。
        min_samples: Minimum round-trips per cell for a valid estimate. / 有效估計的最小往返數。
        engine_mode: 'demo', 'paper', or 'live'. Defaults to 'demo' to avoid paper data pollution.
                     'demo'、'paper' 或 'live'。默認 'demo' 以避免 paper 數據污染。

    Returns:
        Dict mapping (strategy_name, symbol) → EdgeStats.
    """
    if engine_mode not in ("paper", "demo", "live", "live_demo"):
        raise ValueError(f"Invalid engine_mode: {engine_mode!r} (must be paper/demo/live/live_demo)")

    conn = _get_db_conn()
    try:
        since = datetime.now(tz=timezone.utc) - timedelta(days=days_back)
        with conn.cursor() as cur:
            cur.execute(_FILLS_QUERY, {"since": since, "engine_mode": engine_mode})
            cols = [d[0] for d in cur.description]
            fills = [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()

    logger.info("Fetched %d %s fills since %s", len(fills), engine_mode, since.date())

    # Pair into round-trips
    records = _pair_round_trips(fills)
    logger.info("Paired %d round-trip records", len(records))

    # Aggregate by (strategy, symbol)
    cells: dict[tuple[str, str], list[RoundTripRecord]] = {}
    for rec in records:
        key = (rec.strategy_name, rec.symbol)
        cells.setdefault(key, []).append(rec)

    stats: dict[tuple[str, str], EdgeStats] = {}
    for (strategy, symbol), recs in cells.items():
        if len(recs) < min_samples:
            logger.debug(
                "Skipping (%s, %s): only %d round-trips (min %d)",
                strategy, symbol, len(recs), min_samples,
            )
            continue

        net_bps = [r.net_pnl_bps for r in recs]
        gross_bps = [r.gross_pnl_bps for r in recs]
        fee_bps = [r.entry_fee_bps + r.exit_fee_bps for r in recs]

        n = len(net_bps)
        mean_net = sum(net_bps) / n
        mean_gross = sum(gross_bps) / n
        mean_fee = sum(fee_bps) / n

        # Sample standard deviation / 樣本標準差
        if n >= 2:
            variance = sum((x - mean_net) ** 2 for x in net_bps) / (n - 1)
            std_net = math.sqrt(variance)
        else:
            std_net = 0.0

        # 5-01: Win rate + avg win/loss for multi-dimensional shrinkage.
        # 5-01：勝率 + 平均盈虧，用於多維收縮。
        wins = [x for x in net_bps if x > 0]
        losses = [x for x in net_bps if x <= 0]
        win_rate = len(wins) / n if n > 0 else 0.0
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0

        stats[(strategy, symbol)] = EdgeStats(
            strategy_name=strategy,
            symbol=symbol,
            n=n,
            mean_net_bps=mean_net,
            std_net_bps=std_net,
            mean_gross_bps=mean_gross,
            mean_fee_bps=mean_fee,
            raw_bps_list=net_bps,
            win_rate=win_rate,
            avg_win_bps=avg_win,
            avg_loss_bps=avg_loss,
        )
        logger.info(
            "  (%s, %s): n=%d mean_net=%.2f bps std=%.2f bps fee=%.2f bps win_rate=%.2f",
            strategy, symbol, n, mean_net, std_net, mean_fee, win_rate,
        )

    return stats


# ---------------------------------------------------------------------------
# CLI entry point / CLI 入口
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compute realized edge stats from paper fills.")
    p.add_argument("--days", type=int, default=30, help="Days of history to query (default 30)")
    p.add_argument("--min-samples", type=int, default=3, help="Min round-trips per cell (default 3)")
    p.add_argument("--mode", type=str, default="demo", choices=["paper", "demo", "live"],
                   help="Engine mode to query fills from (default: demo)")
    p.add_argument("--out", type=str, default=None, help="Write JSON summary to this path")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def main() -> None:
    """CLI entry point. / CLI 入口。"""
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    stats = compute_edge_stats(days_back=args.days, min_samples=args.min_samples,
                               engine_mode=args.mode)

    summary = {
        f"{s}::{sym}": {
            "n": es.n,
            "mean_net_bps": round(es.mean_net_bps, 4),
            "std_net_bps": round(es.std_net_bps, 4),
            "mean_gross_bps": round(es.mean_gross_bps, 4),
            "mean_fee_bps": round(es.mean_fee_bps, 4),
        }
        for (s, sym), es in stats.items()
    }

    print(json.dumps(summary, indent=2))

    if args.out:
        with open(args.out, "w") as f:
            json.dump(summary, f, indent=2)
        logger.info("Written to %s", args.out)


if __name__ == "__main__":
    main()
