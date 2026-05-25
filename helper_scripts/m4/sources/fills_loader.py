"""
MODULE_NOTE
模塊用途：M4 Stage 1 trading.fills source loader（per W1-B spec §1.2）。

讀取契約：
   - engine_mode IN ('live', 'live_demo') — 強制 filter
   - 禁 engine_mode = 'paper'（per CLAUDE.md §四 + memory
     `project_engine_mode_tag_live_demo`）
   - 只取 close_fill = TRUE（對應 forward return）
   - 6h stale alert

不變量：
   - 必含 live_demo（per memory `project_engine_mode_tag_live_demo` 歷史 43k 'live'
     實為 LiveDemo 教訓 — IN ('live','live_demo') 是 SSOT）
"""
from __future__ import annotations

from typing import Iterable

# 為什麼 module-level：5 對抗式 grep（W1-B spec §9.4 Review-4）需 grep
# engine_mode + 必 IN ('live', 'live_demo')。
ALLOWED_ENGINE_MODES: tuple[str, ...] = ("live", "live_demo")
FILLS_FRESHNESS_GATE_HOURS: int = 6


# engine_mode filter 必 `IN ('live', 'live_demo')` — 不能單獨 ='live'
# (per W1-B spec §9.4 + memory project_engine_mode_tag_live_demo).
FILLS_QUERY_SQL: str = """
SELECT
    symbol,
    strategy_name,
    ts,
    side,
    size,
    price,
    fee_rate,
    realized_net_bps,
    entry_context_id,
    close_reason_code
FROM trading.fills
WHERE engine_mode IN ('live', 'live_demo')
  AND ts >= now() - %(lookback)s::INTERVAL
  AND close_fill = TRUE
ORDER BY symbol, strategy_name, ts
"""


def build_fills_query(lookback_days: int = 90) -> tuple[str, dict]:
    """組裝 fills ingest query + bind params。

    為什麼 hard-code engine_mode 在 SQL：filter 是 invariant 不是 caller-tunable
    （per W1-B spec I-4 + CLAUDE.md §四）。caller 不能 override engine_mode filter。
    """
    return FILLS_QUERY_SQL, {"lookback": f"{lookback_days} days"}


def is_engine_mode_valid(mode: str) -> bool:
    """判斷 engine_mode 是否在白名單。

    為什麼提供：caller validation hook；違反必 fail-loud raise（不靜默接受 paper）。
    """
    return mode in ALLOWED_ENGINE_MODES
