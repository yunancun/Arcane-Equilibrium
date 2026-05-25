"""
MODULE_NOTE
模塊用途：M4 Stage 1 market.klines source loader（per W1-B spec §1.1）。

讀取契約：
   - 90d window × 25 symbol × 5 timeframe (1m/5m/15m/1h/4h)
   - 不取 last bar (ts == now() 的 partial bar 必排除)
   - kline freshness < 24h stale → SOURCE_STALE alert

不變量：
   - 跨 timeframe 必統一 UTC timestamp
   - partial bar 必排除（per W1-B spec §1.1 invariant）

依賴：psycopg2-binary（Linux runtime 用）；Mac scaffold 階段不開 PG connection
   (per `feedback_v_migration_pg_dry_run` Mac mock pytest 無法 catch PG runtime
   semantic — 真實 PG verify 由主會話 ssh trade-core 跑 W1-B spec §7 SQL)。
"""
from __future__ import annotations

from typing import Iterable

# 為什麼 module-level constant：5 對抗式 grep（W1-B spec §9.1）需 grep `freshness_gate_hours`。
KLINE_FRESHNESS_GATE_HOURS: int = 24
DEFAULT_LOOKBACK_DAYS: int = 90
SUPPORTED_TIMEFRAMES: tuple[str, ...] = ("1m", "5m", "15m", "1h", "4h")


# 標準 SQL pattern — 對齊 W1-B spec §1.1 invariant：
#   - last partial bar 排除（subquery MAX(ts) - INTERVAL '1 minute'）
#   - 90d window
KLINE_QUERY_SQL: str = """
SELECT
    symbol,
    timeframe,
    ts,
    open,
    high,
    low,
    close,
    volume,
    turnover
FROM market.klines
WHERE symbol = ANY(%(symbols)s::TEXT[])
  AND timeframe = ANY(%(timeframes)s::TEXT[])
  AND ts >= now() - %(lookback)s::INTERVAL
  AND ts < (
      SELECT MAX(ts) - INTERVAL '1 minute'
      FROM market.klines
      WHERE symbol = ANY(%(symbols)s::TEXT[])
        AND timeframe = ANY(%(timeframes)s::TEXT[])
  )
ORDER BY symbol, timeframe, ts
"""


def build_kline_query(
    symbols: Iterable[str],
    timeframes: Iterable[str] = SUPPORTED_TIMEFRAMES,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> tuple[str, dict]:
    """組裝 kline ingest query + bind params。

    為什麼分開 query / params：parametrized query 防 SQL injection（per CLAUDE.md
    §七 安全代碼規範 SQL 參數化）+ caller 可注 mock connection 跑 dry-run。

    Returns: (sql, params dict)
    """
    return (
        KLINE_QUERY_SQL,
        {
            "symbols": list(symbols),
            "timeframes": list(timeframes),
            "lookback": f"{lookback_days} days",
        },
    )


def is_stale(latest_ts_epoch: float, now_epoch: float, gate_hours: int = KLINE_FRESHNESS_GATE_HOURS) -> bool:
    """判斷 kline source 是否 stale（latest ts 距 now > gate_hours）。

    為什麼 fail-loud：stale source 必須 SOURCE_STALE alert + skip 該 batch
    （per W1-B spec §1.1）— 不能靜默用 stale data 算 alpha。
    """
    age_sec = now_epoch - latest_ts_epoch
    return age_sec > gate_hours * 3600
