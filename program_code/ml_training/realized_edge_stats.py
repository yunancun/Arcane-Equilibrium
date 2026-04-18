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
# Winsorization constants / Winsorization 常量
# ---------------------------------------------------------------------------

# P1-17 (2026-04-18 Edge Crisis RCA). Per-round-trip PnL outliers (e.g. -152,015 bps
# on grid_trading::DOTUSDT) were poisoning James-Stein shrinkage via a toxic
# grand_mean (~-4530 bps raw → -2214 bps committed), then B=0.888 shrinkage pulled
# every cell toward that value. Root cause is likely halt_session mis-crediting
# (separate P1-16 pairing ticket) and/or micro-notional round-trips amplifying
# fee drag. Winsorize any single round-trip's gross/net bps to ±5000 bps (±50%)
# at the record level. Justification: across risk_config_{demo,live,paper}.toml
# the max stop_loss_max_pct is demo=25%; 2× that = 50% = 5000 bps comfortably
# covers legitimate stop-outs + slippage while clipping obvious pairing-bug
# or data-quality outliers (which observed at 6000-150000 bps magnitudes).
# P1-17（2026-04-18 Edge 危機 RCA）。單筆往返 PnL 的離群值（例如
# grid_trading::DOTUSDT 上 -152,015 bps）正在透過毒性 grand_mean（原始 ~-4530 bps →
# 寫入 -2214 bps）污染 James-Stein 收縮，然後 B=0.888 將每個格子拉向該值。
# 根因可能為 halt_session 誤配對（另立 P1-16 配對票）和/或微名義往返放大手續費拖累。
# 在記錄級別將任一往返的 gross/net bps 限幅至 ±5000 bps（±50%）。
# 理由：risk_config_{demo,live,paper}.toml 中最大 stop_loss_max_pct 為 demo=25%；
# 其 2 倍 = 50% = 5000 bps 足以容納合法止損 + 滑價，同時裁掉明顯的配對 bug
# 或資料品質離群值（觀測到的量級為 6000-150000 bps）。
_WINSORIZE_BPS = 5000.0

# Module-level counter; incremented each time clamp fires, for E4-grade auditing.
# 模組級計數器；每次限幅觸發時遞增，用於 E4 級別審計。
_winsorize_clamp_count: int = 0


def _reset_winsorize_counter() -> None:
    """Reset the clamp counter (test helper). / 重置限幅計數器（測試輔助）。"""
    global _winsorize_clamp_count
    _winsorize_clamp_count = 0


def get_winsorize_clamp_count() -> int:
    """Return the current clamp-fire count. / 返回當前限幅觸發次數。"""
    return _winsorize_clamp_count


# ---------------------------------------------------------------------------
# P1-16 defensive gates / P1-16 防禦閘門
# ---------------------------------------------------------------------------

# Threshold on |ln(exit_price / entry_price)|. Exceeding this means the pair
# crosses a >65% round-trip price move — physically implausible for a single
# position close inside 24h crypto (stop_loss caps at 25% even on the loosest
# demo profile). The P1-16 incident saw ETHUSDT $2357.94 smeared onto
# DOT/HIGH/IP/AAVEUSDT at their entry scales of $0.0013–$7.8, giving
# |ln(ratio)| ≈ 5.7–12.8 → we skip these pairs outright so they never reach
# James-Stein shrinkage even if the Winsorizer misses them.
# 價格跳變閘門門檻：|ln(exit/entry)| 超過 0.5 代表往返價差 >65%，
# 單次平倉物理上不可能（最寬 demo profile 的 stop_loss 也只 25%）。
# P1-16 事件中 ETHUSDT $2357.94 被蓋到 DOT/HIGH/IP/AAVEUSDT 的 $0.0013–$7.8
# entry，|ln(ratio)| ≈ 5.7–12.8 → 此閘門會直接丟棄這些 pair，即使 Winsorize 漏網。
_PRICE_JUMP_LN_LIMIT = 0.5

_price_jump_skip_count: int = 0


def _reset_price_jump_counter() -> None:
    """Reset the price-jump skip counter (test helper). / 重置跳價略過計數器（測試輔助）。"""
    global _price_jump_skip_count
    _price_jump_skip_count = 0


def get_price_jump_skip_count() -> int:
    """Return the current price-jump skip count. / 返回當前跳價略過次數。"""
    return _price_jump_skip_count


def _is_price_jump_pair(entry_price: float, exit_price: float) -> bool:
    """
    Return True if the entry→exit price ratio is so extreme that the pair is
    almost certainly the product of a shared-price corruption bug upstream
    (P1-16) rather than a real market move.
    若 entry→exit 比率極端到幾乎確定是上游共享價 bug（P1-16）而非真實行情，
    返回 True。
    """
    if entry_price <= 0.0 or exit_price <= 0.0:
        return False
    if not (math.isfinite(entry_price) and math.isfinite(exit_price)):
        return False
    return abs(math.log(exit_price / entry_price)) > _PRICE_JUMP_LN_LIMIT


def _winsorize_bps(value: float, field_name: str, strategy: str, symbol: str) -> float:
    """
    Clamp a bps value to [-_WINSORIZE_BPS, +_WINSORIZE_BPS]; log + count on fire.
    將 bps 值限幅至 [-_WINSORIZE_BPS, +_WINSORIZE_BPS]；觸發時記錄 + 計數。
    """
    global _winsorize_clamp_count
    if value > _WINSORIZE_BPS:
        logger.info(
            "WINSORIZE clamp (%s, %s) %s: %.2f bps → %.2f bps",
            strategy, symbol, field_name, value, _WINSORIZE_BPS,
        )
        _winsorize_clamp_count += 1
        return _WINSORIZE_BPS
    if value < -_WINSORIZE_BPS:
        logger.info(
            "WINSORIZE clamp (%s, %s) %s: %.2f bps → %.2f bps",
            strategy, symbol, field_name, value, -_WINSORIZE_BPS,
        )
        _winsorize_clamp_count += 1
        return -_WINSORIZE_BPS
    return value

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
    global _price_jump_skip_count
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
                # Entry fill — push to queue. `qty_total` preserves the original
                # fill size so partial matches can defend against micro-denominator
                # amplification (P1-16). `qty_remaining` is decremented by matches.
                # 入場成交入列。qty_total 保留原始大小供部分配對防止微分母放大（P1-16）。
                open_entries.append({
                    "strategy_name": strategy_name,
                    "qty_total": qty,
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
                    # P1-16 defensive gate (b): use max(full entry notional, match
                    # notional) as the bps denominator. For partial matches this
                    # floors the denominator at the full entry, preventing tiny
                    # matched_qty × entry_price from turning an apportioned PnL
                    # into absurd bps (the $0.13 denominator vs $235 loss that
                    # produced -17,617,373 bps in the original incident).
                    # P1-16 防禦 (b)：bps 分母取 max(整筆 entry notional, 本次配對 notional)。
                    # 部分配對時把分母托底至整筆 entry，避免微小 matched_qty × entry_price
                    # 把分攤 PnL 放大成荒謬 bps（$0.13 分母 vs $235 虧損 = -17M bps）。
                    entry_notional_full = entry["entry_price"] * entry["qty_total"]
                    denom_bps = max(entry_notional_full, entry_notional)
                    # Gross PnL for this matched portion (price difference)
                    # Note: realized_pnl from DB is for the whole exit fill, so we apportion
                    gross_pnl_usd = realized_pnl * (matched_qty / qty) if qty > 0 else 0.0
                    entry_fee_usd = entry["entry_fee"] * fraction
                    exit_fee_usd = fee * (matched_qty / qty) if qty > 0 else 0.0

                    if entry_notional > 0:
                        # P1-16 defensive gate (a): skip pairs whose entry→exit
                        # price ratio is physically implausible (|ln| > 0.5, i.e.
                        # >65% round-trip). These are almost certainly the product
                        # of shared-price corruption (halt_session etc.) and must
                        # not poison James-Stein shrinkage — Winsorize caps
                        # magnitude but still lets the sign and sample count
                        # through. Skipping eliminates both.
                        # P1-16 防禦 (a)：略過物理上不可能的 entry→exit 比率（|ln|>0.5
                        # 即 >65% 往返）。這幾乎鐵定是共享價污染（halt_session 等），
                        # 不能污染 JS 收縮——Winsorize 只裁量級卻仍讓符號與樣本計數
                        # 流入，直接 skip 可同時斷絕兩者。
                        if _is_price_jump_pair(entry["entry_price"], price):
                            _price_jump_skip_count += 1
                            logger.info(
                                "PRICE-JUMP skip (%s, %s): entry=%.6f exit=%.6f "
                                "|ln(ratio)|=%.3f > %.2f (likely shared-price corruption)",
                                entry["strategy_name"], symbol,
                                entry["entry_price"], price,
                                abs(math.log(price / entry["entry_price"])),
                                _PRICE_JUMP_LN_LIMIT,
                            )
                        else:
                            gross_bps_raw = _bps(gross_pnl_usd, denom_bps)
                            net_bps_raw = _bps(
                                gross_pnl_usd - entry_fee_usd - exit_fee_usd,
                                denom_bps,
                            )
                            # P1-17: Winsorize signed PnL at record level to contain
                            # outlier round-trips (e.g. halt_session pairing bug).
                            # Fees are intentionally NOT winsorized — they're bounded
                            # by fee_rate × notional and carry no outlier risk.
                            # P1-17：在記錄級別對有符號 PnL 限幅以控制離群往返
                            #（例如 halt_session 配對 bug）。手續費刻意不限幅——
                            # 其由 fee_rate × notional 有界，無離群風險。
                            gross_bps = _winsorize_bps(
                                gross_bps_raw, "gross_pnl_bps",
                                entry["strategy_name"], symbol,
                            )
                            net_bps = _winsorize_bps(
                                net_bps_raw, "net_pnl_bps",
                                entry["strategy_name"], symbol,
                            )
                            rec = RoundTripRecord(
                                strategy_name=entry["strategy_name"],
                                symbol=symbol,
                                gross_pnl_bps=gross_bps,
                                entry_fee_bps=_bps(entry_fee_usd, denom_bps),
                                exit_fee_bps=_bps(exit_fee_usd, denom_bps),
                                net_pnl_bps=net_bps,
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
