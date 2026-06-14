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
     `(close.realized_pnl - close.fee - entry.fee) / (price * qty) * 10000`
     計算 derived post-fee bps（notional bps），其中 entry.fee 取單一代表 entry
     行（最早一筆真 entry，見 FILLS_QUERY_SQL 上方說明），非 fan-out 求和
   - 真實 trading.fills 沒有 `close_fill` column → 用 `entry_context_id IS NOT NULL`
   - 真實 trading.fills 沒有 `close_reason_code` column → 用既存 `exit_reason`

不變量：
   - 必含 live_demo（per memory `project_engine_mode_tag_live_demo` 歷史 43k 'live'
     實為 LiveDemo 教訓 — IN ('live','live_demo') 是 SSOT）
   - bps 表達式不可變更為 fee_rate 之類間接 proxy。
   - net label NULL 語意（三條 fail-closed 守衛，皆不 COALESCE 成 0 捏造 gross）：
     realized_net_pnl / realized_net_bps 非 NULL ⟺ 同時滿足 (a) 找到代表 entry 行
     (entry_fill_found=TRUE) (b) 代表 entry fee 非 NULL（LATERAL `e.fee IS NOT NULL`
     已保證 entry_fill_found=TRUE ⟹ entry_fee 非 NULL）(c) close 行 realized_pnl 非
     NULL（CASE `f.realized_pnl IS NOT NULL` 守衛，否則純費用小負值會被當真實 net
     label）。任一不滿足 → net label NULL，row 仍保留（SQL 端不過濾）。
   - caller 契約：**dropna 必對 net label 欄（realized_net_pnl/realized_net_bps）**，
     此為權威信號；entry_fill_found 僅粗診斷旗標 — TRUE 不保證 net label 非 NULL
     （例如代表 entry 存在但 close 行 realized_pnl 為 NULL）。勿僅依 entry_fill_found 旗標。
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
# 為什麼 SQL 中 SELECT realized_pnl - close/entry fee：
#   trading.fills 無 realized_net_bps column（empirical verify），需從 realized_pnl
#   + close fee + entry fee 推算真實 post-fee label。Bybit closedPnl 為扣除
#   openFee/closeFee 後的淨值；本地 close fill 的 realized_pnl 是毛利，直接當
#   net label 會污染 M4 學習樣本。NULLIF(price * qty, 0) 防除以零。
#
# 為什麼 entry fee 走 single-representative LATERAL（非裸 LEFT JOIN）：
#   裸 `LEFT JOIN ... ON context_id = entry_context_id` 有兩個缺陷（Linux PG 實證）：
#   (1) FAN-OUT — context_id 非唯一，一筆 close 行會按共用該 context_id 的行數倍增。
#   (2) WRONG-FEE（嚴重）— 缺 `entry_context_id IS NULL` 謂詞時，自身 context_id
#       等於 entry_context_id 的 CLOSE 行會被當成 entry 命中，把它自己的 close fee
#       當「entry fee」再扣一次 → close fee 被雙重扣除 + 行 fan-out。
#   修法 = LATERAL 只取「最早一筆真 entry 行」的 fee（entry_context_id IS NULL 且
#   排除 close-shaped 的 risk_close:/orphan_close:/adopted_close:/shadow_fill:/
#   unattributed: 前綴 row），對齊 canonical edge_label_backfill.py：
#   `JOIN LATERAL (... ORDER BY ts ASC LIMIT 1)`。
#   為什麼取單一代表而非 SUM(entry.fee)：一筆 entry 可有 N>1 partial close 行，
#   每個 partial close 是一輸出行；SUM 會在每個 partial close 上重扣整筆 entry fee
#   （扣 N 次）→ 過度扣費。單一代表 = 與 canonical 對齊且零新自由參數。
#
# 為什麼 LATERAL 加 `e.fee IS NOT NULL` 謂詞：
#   trading.fills.fee 為 REAL DEFAULT 0 可空（V003）。若代表 entry 行 fee 為 NULL，
#   entry_rep.entry_fee = NULL → net label 算術 `... - entry_fee` = NULL，但
#   entry_fill_found 旗標仍 TRUE → 旗標與 label 矛盾。加 fee 非空謂詞 =
#   entry_fill_found=TRUE ⟹ entry_fee 必非 NULL（精確化 discriminator）。
#
# 為什麼 net label 設 NULL（不 COALESCE(...,0)），三條 fail-closed 守衛：
#   (1) 無代表 entry 行（entry_rep.entry_fill_found IS NULL/FALSE）：若 COALESCE
#   成 0 = 捏造樂觀 gross label 污染 M4 樣本 → emit NULL + entry_fill_found=FALSE。
#   (2) 代表 entry 行 fee 為 NULL：已由上方 LATERAL `e.fee IS NOT NULL` 排除，此類
#   entry 不被選為代表 → entry_fill_found=FALSE → label NULL。
#   (3) close 行自身 realized_pnl 為 NULL：CASE 加 `f.realized_pnl IS NOT NULL`
#   守衛。否則 COALESCE(NULL,0)-fee-entry_fee = 小負值（純費用）被當真實 net label
#   餵入 → 靜默捏造小負 bps。realized_pnl NULL 時 emit NULL label。
#   net label（realized_net_pnl/realized_net_bps）非 NULL ⟺ 三條件全滿足，故
#   **caller 必對 net label 欄 dropna**（net label 是權威信號）；entry_fill_found
#   僅為粗診斷旗標（TRUE 不保證 net label 非 NULL，例如 close 行 realized_pnl NULL）。
#
# 為什麼 close-fill 判定用 entry_context_id IS NOT NULL：
#   trading.fills 無 close_fill column（empirical verify）。canonical pattern per
#   program_code/ml_training/edge_label_backfill.py：entry 行 entry_context_id
#   IS NULL，close 行 entry_context_id 指向 entry 的 context_id。
FILLS_QUERY_SQL: str = """
SELECT
    f.symbol,
    f.strategy_name,
    f.ts,
    f.side,
    f.qty,
    f.price,
    f.fee_rate,
    f.realized_pnl,
    (COALESCE(f.fee, 0) + entry_rep.entry_fee)::float8 AS realized_total_fee,
    CASE WHEN entry_rep.entry_fill_found AND f.realized_pnl IS NOT NULL
         THEN (
             f.realized_pnl
             - COALESCE(f.fee, 0)
             - entry_rep.entry_fee
         )::float8
         ELSE NULL END AS realized_net_pnl,
    CASE WHEN entry_rep.entry_fill_found AND f.realized_pnl IS NOT NULL
         THEN (
             (
                 f.realized_pnl
                 - COALESCE(f.fee, 0)
                 - entry_rep.entry_fee
             ) / NULLIF(f.price * f.qty, 0)
         ) * 10000
         ELSE NULL END AS realized_net_bps,
    entry_rep.entry_fill_found AS entry_fill_found,
    f.entry_context_id,
    f.exit_reason
FROM trading.fills f
LEFT JOIN LATERAL (
    SELECT e.fee::float8 AS entry_fee, TRUE AS entry_fill_found
    FROM trading.fills e
    WHERE e.context_id = f.entry_context_id
      AND e.engine_mode = f.engine_mode
      AND e.entry_context_id IS NULL
      AND e.fee IS NOT NULL
      AND (e.strategy_name IS NULL OR (
            e.strategy_name NOT LIKE 'risk_close:%%'
        AND e.strategy_name NOT LIKE 'orphan_close:%%'
        AND e.strategy_name NOT LIKE 'adopted_close:%%'
        AND e.strategy_name NOT LIKE 'shadow_fill:%%'
        AND e.strategy_name NOT LIKE 'unattributed:%%'))
    ORDER BY e.ts ASC
    LIMIT 1
) entry_rep ON TRUE
WHERE f.engine_mode IN ('live', 'live_demo')
  AND f.ts >= now() - %(lookback)s::INTERVAL
  AND f.entry_context_id IS NOT NULL
ORDER BY f.symbol, f.strategy_name, f.ts
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
