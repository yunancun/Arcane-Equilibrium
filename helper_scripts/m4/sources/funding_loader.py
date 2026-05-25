"""
MODULE_NOTE
模塊用途：M4 Stage 1 market.funding_rates source loader（per W1-B spec §1.4）。

讀取契約：
   - Bybit funding settlement 整點 UTC 0/8/16 (3 次/天)
   - Funding flip event 定義: sign change + |rate| > 0.01% (configurable)
   - 12h stale alert

不變量：
   - Funding rate 數據必對齊 settlement 時間（不能用 mid-cycle 估計值）
"""
from __future__ import annotations

FUNDING_FRESHNESS_GATE_HOURS: int = 12

# Bybit funding settlement = 每 8h × 3 次/天 × 365 天 = 1095 次/年
BYBIT_SETTLEMENT_HOURS: tuple[int, ...] = (0, 8, 16)


FUNDING_QUERY_SQL: str = """
SELECT
    symbol,
    ts,
    funding_rate,
    funding_rate * 3 * 365 AS annualized_funding
FROM market.funding_rates
WHERE ts >= now() - %(lookback)s::INTERVAL
ORDER BY symbol, ts
"""


def build_funding_query(lookback_days: int = 90) -> tuple[str, dict]:
    """組裝 funding_rates ingest query + bind params。"""
    return FUNDING_QUERY_SQL, {"lookback": f"{lookback_days} days"}
