"""
MODULE_NOTE
模塊用途：M4 Stage 1 market.liquidations source loader（per W1-B spec §1.3）。

讀取契約：
   - 必剔除 self-fill 引發的 cascade noise
     （LEFT JOIN trading.fills LATERAL 5s 視窗 → fill_id IS NULL）
   - 1h stale alert

Schema 對齊（per W1-C Round 2 empirical PG verify 2026-05-25）：
   - 真實 market.liquidations 只有 5 column: (ts, symbol, side, qty, price)
     → 沒有 size（用 qty）；沒有 aggregator_type（0 V### migration ADD）
   - V095 land 並無 aggregator_type；spec §1.3 列出的 aggregator_type 是 PA 草稿
     階段的 illustrative pseudo-schema，empirical PG 是 SSOT
   - cascade / top_liq window aggregation 在 caller 端（algorithms/event_window.py
     的 detect_liquidation_cascade_events 用 5min rolling sum 判 cascade）做，
     不依賴 source column

不變量：
   - self-fill filter 5s 視窗 — Sprint 2 baseline；Sprint 3 可放寬到 30s
   - 不允許自家 fill 引起的 cascade 被當外部 alpha source
   - source SQL 只負責 raw event ingest；cascade detection 是 algorithm 層職責
"""
from __future__ import annotations

LIQUIDATIONS_FRESHNESS_GATE_HOURS: int = 1
SELF_FILL_FILTER_SECONDS: int = 5  # Sprint 2 baseline；Sprint 3 可放寬 30s

# 為什麼 LEFT JOIN ... IS NULL 不用 NOT EXISTS：兩者語意等價，但 LEFT JOIN
# 在 PG 12+ planner 通常產出更穩定的 query plan（per CR review）。
# 真實 production tune 由 W2-D MIT IMPL 接 cron 後做 EXPLAIN ANALYZE 對比。
#
# 為什麼沒 aggregator_type filter：market.liquidations 是 raw event 表，empirical
# verify 0 aggregator_type column。任何 cascade / top_liq 視窗聚合走 caller-side
# algorithms/event_window.detect_liquidation_cascade_events （5min rolling）。
LIQUIDATIONS_QUERY_SQL: str = """
SELECT
    liq.symbol,
    liq.ts,
    liq.side,
    liq.qty,
    liq.price
FROM market.liquidations liq
LEFT JOIN trading.fills f
       ON f.symbol = liq.symbol
      AND f.ts BETWEEN (liq.ts - %(self_fill_window)s::INTERVAL) AND liq.ts
WHERE liq.ts >= now() - %(lookback)s::INTERVAL
  AND f.fill_id IS NULL
ORDER BY liq.symbol, liq.ts
"""


def build_liquidations_query(
    lookback_days: int = 90,
    self_fill_window_seconds: int = SELF_FILL_FILTER_SECONDS,
) -> tuple[str, dict]:
    """組裝 liquidations ingest query + bind params。

    為什麼 parameterized：self_fill_window_seconds 是 Sprint 2 baseline 5s；
    Sprint 3 可放寬到 30s。
    """
    return LIQUIDATIONS_QUERY_SQL, {
        "lookback": f"{lookback_days} days",
        "self_fill_window": f"{self_fill_window_seconds} seconds",
    }
