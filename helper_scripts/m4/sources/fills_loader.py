"""
MODULE_NOTE
模塊用途：M4 Stage 1 trading.fills source loader（per W1-B spec §1.2）。

讀取契約：
   - engine_mode IN ('live', 'live_demo') — 強制 filter
   - 禁 engine_mode = 'paper'（per CLAUDE.md §四 + memory
     `project_engine_mode_tag_live_demo`）
   - 只取 close fill（`entry_context_id IS NOT NULL`，canonical pattern per
     program_code/ml_training/edge_label_backfill.py：entry 行 entry_context_id
     IS NULL，close 行 entry_context_id 指向 entry 的 context_id）
   - 6h stale alert

Schema 對齊（per W1-C Round 2 empirical PG verify 2026-05-25）：
   - 真實 trading.fills 沒有 `size` column → 用 `qty`
   - 真實 trading.fills 沒有 `realized_net_bps` column → 用
     `realized_pnl / (price * qty) * 10000` 計算 derived bps（notional bps）
   - 真實 trading.fills 沒有 `close_fill` column → 用 `entry_context_id IS NOT NULL`
   - 真實 trading.fills 沒有 `close_reason_code` column → 用既存 `exit_reason`

不變量：
   - 必含 live_demo（per memory `project_engine_mode_tag_live_demo` 歷史 43k 'live'
     實為 LiveDemo 教訓 — IN ('live','live_demo') 是 SSOT）
   - bps 表達式不可變更為 fee_rate 之類間接 proxy；realized_pnl 是 NULL 時 row 被
     讀回後 caller 端處理（SQL 端不過濾，保留樣本）
"""
from __future__ import annotations

from typing import Iterable

# 為什麼 module-level：5 對抗式 grep（W1-B spec §9.4 Review-4）需 grep
# engine_mode + 必 IN ('live', 'live_demo')。
ALLOWED_ENGINE_MODES: tuple[str, ...] = ("live", "live_demo")
FILLS_FRESHNESS_GATE_HOURS: int = 6


# engine_mode filter 必 `IN ('live', 'live_demo')` — 不能單獨 ='live'
# (per W1-B spec §9.4 + memory project_engine_mode_tag_live_demo).
#
# 為什麼 SQL 中 SELECT realized_pnl / (price * qty) * 10000：
#   trading.fills 無 realized_net_bps column（empirical verify），需從 realized_pnl
#   + notional 推算 bps。NULLIF(price * qty, 0) 防除以零；realized_pnl 本身可能
#   NULL（DEFAULT 0 但歷史可能 NULL），讓 caller 端 dropna 處理。
#
# 為什麼 close-fill 判定用 entry_context_id IS NOT NULL：
#   trading.fills 無 close_fill column（empirical verify）。canonical pattern per
#   program_code/ml_training/edge_label_backfill.py：entry 行 entry_context_id
#   IS NULL，close 行 entry_context_id 指向 entry 的 context_id。
FILLS_QUERY_SQL: str = """
SELECT
    symbol,
    strategy_name,
    ts,
    side,
    qty,
    price,
    fee_rate,
    realized_pnl,
    (realized_pnl / NULLIF(price * qty, 0)) * 10000 AS realized_net_bps,
    entry_context_id,
    exit_reason
FROM trading.fills
WHERE engine_mode IN ('live', 'live_demo')
  AND ts >= now() - %(lookback)s::INTERVAL
  AND entry_context_id IS NOT NULL
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
