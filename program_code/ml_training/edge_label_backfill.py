"""
Edge Label Backfill — 填充 learning.decision_features 的 label_*。
Edge Label Backfill — populate learning.decision_features.label_*.

MODULE_NOTE (中): EDGE-P3-1 Stage 1（PA）標籤回填任務。三 pass 設計：
    Pass 1：JOIN trading.fills 算 realized_net_edge_bps（§4.1）+ split qty
            blend（§4.2）+ grid VWAP（§4.3），UPDATE label_net_edge_bps + tag。
    Pass 2：close fill 是 orphan/adopted/shadow 前綴 → 標 close_tag 但 label
            保 NULL（永久排除訓練集）。
    Pass 3（P0-V3-MIT-ROOT-CAUSE 2026-05-09）：超過 abandon_after_days（默認 30d）
            仍未 backfill 的 row 標 abandoned:no_close_fill，防止
            attribution_chain_ok denominator 被歷史死行（如 ma_crossover demo
            5476328 row stuck 自 4/15 起）撐爆。
    另：check_stale_labels()（§8.2 驗收 demo 48h 填充率 > 95%）+
        attribution_chain_ratio()（P0-V3 healthcheck 配套監控）。

Spec: docs/references/2026-04-15--edge_predictor_spec.md v1.4
SQL migration: sql/migrations/V017__edge_predictor_tables.sql
P0-V3-MIT-ROOT-CAUSE 修復：MIT 報告 docs/CCAgentWorkSpace/MIT/workspace/reports/
                          2026-05-09--db_ml_verification_v3.md §2.3 + §7.4

Usage / 用法:
    source settings/environment_files/basic_system_services.env
    python3 -m program_code.ml_training.edge_label_backfill \
        --engine-mode demo --batch-limit 5000
    # P0-V3 第一次 catchup（一次性大批量處理 historical stuck row）：
    python3 -m program_code.ml_training.edge_label_backfill \
        --engine-mode demo --batch-limit 100000 --abandon-after-days 30
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Excluded close_tag prefixes (§4.2 · permanently excluded from training set)
# 永久排除訓練集的 close_tag 前綴
EXCLUDED_TAG_PREFIXES = ("orphan_close:", "adopted_close:", "shadow_fill:")

# Default stale-label age for alerter (§8.2 · 7d)
# 過期標籤告警默認天數（§8.2 · 7 日）
DEFAULT_STALE_DAYS = 7

# P0-V3-MIT-ROOT-CAUSE (2026-05-09): Abandoned-row marker for stuck unfilled rows.
# 久未平倉的死行標記前綴（P0-V3-MIT-ROOT-CAUSE 修復）。
#
# 上下文 / Context:
#   MIT v3 audit (2026-05-09) 發現 attribution_chain_ok 24h 僅 1.13% / 7d 0.05%。
#   PA 初判定 root cause 為「label_close_tag NULL writer 缺失」。
#   E1 PG empirical 查 (Linux trading_ai DB) 揭示真實 root cause 三層：
#     1. Symptom：24h 6834/6912 view row 是 label_filled_at IS NULL
#     2. Mechanism：Pass 1 + Pass 2 的 trigger 條件 = `EXISTS (close fill)`，
#        沒平倉的 entry 永遠不會被 backfill
#     3. Real cause：5476328 demo ma_crossover decision_features row 已 7d+ 仍
#        unfilled (4/15 起累積)，這些「entry 對應的 close fill 永遠不會發生」
#        的 row 無限期堆積，把 attribution_chain_ok denominator 撐爆。
#   Fix 設計：加 Pass 3 把 `abandon_after_days`（默認 30d）以上仍 unfilled 的
#   row 標 `abandoned:no_close_fill` close_tag + label_filled_at = now()。
#   - label_net_edge_bps 仍 NULL（不污染訓練集，per Pass 2 既有設計）
#   - View 計算 `label_filled_at IS NOT NULL` 變 true → 從 Pass 1+2 候選池剔除
#   - Attribution_chain_ok denominator 不再積累歷史死行（觀察成立）
ABANDONED_TAG_PREFIX = "abandoned:no_close_fill"
DEFAULT_ABANDON_AFTER_DAYS = 30

VALID_ENGINE_MODES = ("paper", "demo", "live", "live_demo")


def engine_mode_scope(engine_mode: str) -> tuple[str, ...]:
    """Return DB engine_mode values to backfill for a requested mode.

    LiveDemo rows are emitted by the Live pipeline when it is bound to Bybit's
    demo endpoint. A request for `live` must therefore include `live_demo` or
    the labeler silently starves the Live training path.
    """
    if engine_mode not in VALID_ENGINE_MODES:
        raise ValueError(f"invalid engine_mode: {engine_mode!r}")
    if engine_mode == "live":
        return ("live", "live_demo")
    return (engine_mode,)


@dataclass
class BackfillResult:
    """Result summary from backfill_labels().
    回填結果摘要。"""
    filled_count:          int = 0  # Pass 1 包含的 label 寫入行
    excluded_count:        int = 0  # Pass 2 標 excluded 但無 label 的行
    split_blend_count:     int = 0  # 非 grid 多次 close
    grid_merged_count:     int = 0  # grid_trading
    skipped_no_entry_fill: int = 0  # entry 行缺失
    abandoned_count:       int = 0  # Pass 3 標 abandoned:no_close_fill 的久未平倉行
    batch_limit_hit:       bool = False

    def to_dict(self) -> dict:
        return {
            "filled":          self.filled_count,
            "excluded":        self.excluded_count,
            "split_blend":     self.split_blend_count,
            "grid_merged":     self.grid_merged_count,
            "skipped_no_entry": self.skipped_no_entry_fill,
            "abandoned":       self.abandoned_count,
            "batch_limit_hit": self.batch_limit_hit,
        }


def _get_conn(pg_url: Optional[str]):
    """Open psycopg2 connection (lazy import to keep tests import-light).
    延遲 import 開啟 psycopg2 連線。"""
    try:
        import psycopg2  # type: ignore
    except ImportError as e:
        raise RuntimeError("psycopg2 not installed — activate venv first") from e

    dsn = pg_url or os.environ.get("OPENCLAW_DATABASE_URL") or os.environ.get("DSN")
    if not dsn:
        # Fallback: construct from POSTGRES_* env vars (aligned with helper_scripts/db/)
        # 後備：從 POSTGRES_* 環境變量構造（對齊 helper_scripts/db/）
        host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
        port = os.environ.get("POSTGRES_PORT", "5432")
        user = os.environ.get("POSTGRES_USER", "openclaw")
        password = os.environ.get("POSTGRES_PASSWORD", "")
        db = os.environ.get("POSTGRES_DB", "openclaw")
        dsn = f"postgresql://{user}:{password}@{host}:{port}/{db}"
    return psycopg2.connect(dsn)


# ============================================================
# Core backfill SQL — single atomic statement using CTE.
# 核心回填 SQL — 單一原子 CTE 語句。
#
# Strategy:
#   1. `entries`: unlabeled rows (label_filled_at IS NULL) with at least one close fill.
#   2. `entry_fills`: matched entry fill (context_id = entry's own context_id).
#   3. `close_fills`: close rows pointing back via entry_context_id.
#   4. `classified`: tag each close as excluded or included.
#   5. `per_entry`: aggregate fills; BOOL_OR for any_excluded taint.
#   6. `funding_by_entry`: join attributed funding settlements over entry→close lifecycle.
#   7. `labels`: compute realized_net_edge_bps (gross + funding − entry_fee − close_fee)
#      normalized by entry notional; distinguish grid VWAP vs non-grid blend.
#   8. UPDATE split into two passes:
#      a) included → write label + split_flag + filled_at
#      b) any_excluded → write close_tag + filled_at, keep label=NULL
#         (future runs skip via WHERE label_filled_at IS NULL).
# ============================================================
_BACKFILL_INCLUDED_SQL = """
-- F4-2 (2026-04-26): Every JOIN against trading.fills below filters
-- `strategy_name NOT LIKE 'unattributed:%%'` so Bybit auto-action audit rows
-- (funding payment / dust scrub / auto-补单) cannot leak into label generation.
-- Audit rows have realized_pnl=0 and unique context_ids (`unattrib-{exec_id}-{ts}`)
-- that never match a real decision_features row, so the EXISTS / JOIN already
-- excludes them by definition; the explicit filter is defence-in-depth in case
-- a future writer change reuses context_ids or relaxes invariants.
-- F4-2（2026-04-26）：下方所有 JOIN trading.fills 皆加
-- `strategy_name NOT LIKE 'unattributed:%%'` 過濾，確保 Bybit 自主動作 audit row
-- 不混入 label 產生。Audit row 有獨特 context_id 不可能 JOIN 上真 decision_features，
-- 顯式過濾為深層防護。
WITH entries AS (
    SELECT l.context_id,
           l.strategy_name,
           l.symbol,
           l.engine_mode,
           l.ts AS entry_ts
    FROM learning.decision_features l
    WHERE l.label_filled_at IS NULL
      AND l.engine_mode = ANY(%(engine_modes)s)
      AND EXISTS (
          SELECT 1 FROM trading.fills f
          WHERE f.entry_context_id = l.context_id
            -- F4-2: filter audit rows from existence check
            -- F4-2：EXISTS 中亦排除 audit row
            AND (f.strategy_name IS NULL OR f.strategy_name NOT LIKE 'unattributed:%%')
      )
    ORDER BY l.ts
    LIMIT %(batch_limit)s
),
entry_fills AS (
    SELECT e.context_id,
           f.qty   AS entry_qty,
           f.price AS entry_price,
           f.fee   AS entry_fee
    FROM entries e
    JOIN LATERAL (
        SELECT qty, price, fee
        FROM trading.fills
        WHERE context_id = e.context_id
          AND entry_context_id IS NULL  -- entry row, not a close
          -- F4-2: belt-and-suspenders — audit rows have unique context_ids,
          -- but reject by strategy_name as well in case of future drift.
          -- F4-2：雙保險 — audit context_id 獨特，但同時依 strategy_name 排除。
          AND (strategy_name IS NULL OR strategy_name NOT LIKE 'unattributed:%%')
        ORDER BY ts ASC
        LIMIT 1
    ) f ON TRUE
),
close_fills AS (
    SELECT e.context_id,
           e.strategy_name,
           f.qty          AS close_qty,
           f.price        AS close_price,
           f.fee          AS close_fee,
           f.realized_pnl AS gross_pnl,
           f.strategy_name AS close_tag,
           f.ts            AS close_ts
    FROM entries e
    JOIN trading.fills f ON f.entry_context_id = e.context_id
        -- F4-2: close fills must not be audit rows either.
        -- F4-2：close fill 同樣排除 audit row。
        AND (f.strategy_name IS NULL OR f.strategy_name NOT LIKE 'unattributed:%%')
),
classified AS (
    SELECT *,
           (close_tag LIKE 'orphan_close:%%'
            OR close_tag LIKE 'adopted_close:%%'
            OR close_tag LIKE 'shadow_fill:%%') AS is_excluded
    FROM close_fills
),
per_entry AS (
    SELECT context_id,
           strategy_name,
           -- Use newest close tag as representative (stable ordering by SUM is synthetic)
           (array_agg(close_tag ORDER BY close_qty DESC))[1] AS last_close_tag,
           COUNT(*)                AS close_count,
           SUM(close_qty)          AS total_close_qty,
           SUM(gross_pnl)          AS total_gross_pnl,
           SUM(close_fee)          AS total_close_fee,
           SUM(close_qty * close_price) / NULLIF(SUM(close_qty), 0) AS vwap_exit,
           MAX(close_ts)           AS last_close_ts,
           BOOL_OR(is_excluded)    AS any_excluded
    FROM classified
    GROUP BY context_id, strategy_name
),
funding_by_entry AS (
    SELECT e.context_id,
           COALESCE(SUM(fs.amount), 0.0) AS total_funding_pnl
    FROM entries e
    JOIN per_entry p ON p.context_id = e.context_id
    LEFT JOIN trading.funding_settlements fs
      ON fs.symbol = e.symbol
     AND fs.engine_mode = e.engine_mode
     AND fs.strategy_name = e.strategy_name
     AND fs.ts >= e.entry_ts
     AND fs.ts <= p.last_close_ts
    GROUP BY e.context_id
),
labels AS (
    SELECT e.context_id,
           ef.entry_price,
           ef.entry_qty,
           ef.entry_fee,
           p.strategy_name,
           p.last_close_tag,
           p.close_count,
           p.total_gross_pnl,
           COALESCE(fb.total_funding_pnl, 0.0) AS total_funding_pnl,
           p.total_close_fee,
           p.vwap_exit,
           p.total_close_qty,
           p.any_excluded,
           (p.total_close_qty >= ef.entry_qty * 0.999999) AS close_qty_complete,
           CASE
               WHEN ef.entry_price > 0 AND ef.entry_qty > 0 THEN
                   (p.total_gross_pnl + COALESCE(fb.total_funding_pnl, 0.0)
                    - ef.entry_fee - p.total_close_fee)
                   / (ef.entry_price * ef.entry_qty) * 10000.0
               ELSE NULL
           END AS label_net_edge_bps,
           CASE
               WHEN p.strategy_name = 'grid_trading' THEN FALSE  -- §4.3 VWAP by design
               WHEN p.close_count > 1 THEN TRUE                   -- §4.2 split blend
               ELSE FALSE
           END AS split_flag
    FROM entries e
    JOIN entry_fills ef ON ef.context_id = e.context_id
    JOIN per_entry   p  ON p.context_id  = e.context_id
    LEFT JOIN funding_by_entry fb ON fb.context_id = e.context_id
)
UPDATE learning.decision_features d
SET label_net_edge_bps = l.label_net_edge_bps,
    label_close_tag    = l.last_close_tag,
    label_split_flag   = l.split_flag,
    label_filled_at    = now()
FROM labels l
WHERE d.context_id = l.context_id
  AND NOT l.any_excluded
  AND l.close_qty_complete
  AND l.label_net_edge_bps IS NOT NULL
RETURNING d.context_id, l.strategy_name, l.split_flag
"""

# ----- 第二 pass：把 any_excluded 標籤也 mark 為 filled_at，避免下次重試 -----
# ----- Pass 2: mark any_excluded rows as tried (prevent re-processing) -----
_BACKFILL_EXCLUDED_SQL = """
-- F4-2 (2026-04-26): see _BACKFILL_INCLUDED_SQL for rationale; mirror the
-- `strategy_name NOT LIKE 'unattributed:%%'` filter on the close-side JOIN.
-- F4-2（2026-04-26）：見 _BACKFILL_INCLUDED_SQL 註釋，close 側 JOIN 鏡射過濾。
WITH excluded_entries AS (
    SELECT l.context_id,
           (array_agg(f.strategy_name ORDER BY f.ts DESC))[1] AS last_close_tag
    FROM learning.decision_features l
    JOIN trading.fills f ON f.entry_context_id = l.context_id
    WHERE l.label_filled_at IS NULL
      AND l.engine_mode = ANY(%(engine_modes)s)
      AND f.strategy_name ~ '^(orphan_close:|adopted_close:|shadow_fill:)'
      -- F4-2: audit rows excluded (defence-in-depth; audit context_ids never
      -- match a real decision_features row, but filter explicitly).
      -- F4-2：audit row 排除（深層防護；audit context_id 不會 JOIN 上真 row）。
      AND f.strategy_name NOT LIKE 'unattributed:%%'
    GROUP BY l.context_id
    LIMIT %(batch_limit)s
)
UPDATE learning.decision_features d
SET label_close_tag = e.last_close_tag,
    label_filled_at = now()
    -- label_net_edge_bps intentionally left NULL (excluded from training)
FROM excluded_entries e
WHERE d.context_id = e.context_id
RETURNING d.context_id
"""


# ============================================================
# Pass 3 (P0-V3-MIT-ROOT-CAUSE 2026-05-09)：標記久未平倉的死行為 abandoned。
# Pass 3: mark long-unfilled rows as abandoned (no close fill ever expected).
#
# 為什麼有 Pass 3：
#   Pass 1 + Pass 2 都需要 `EXISTS (SELECT 1 FROM trading.fills WHERE
#   entry_context_id = decision_features.context_id)` 才會 trigger，但實證
#   ma_crossover demo 7d 245k unique context_id 中只 38 有 close fill。剩餘
#   數百萬 row 永遠不會被 backfill，但 view `attribution_chain_ok` 計算的
#   denominator 仍包含它們，導致 ratio 看起來像「learning 死了」。
#
#   Pass 3 把 `abandon_after_days`（默認 30d）以上仍 unfilled 的 row 標
#   `abandoned:no_close_fill` close_tag + `label_filled_at = now()`，使
#   Pass 1 + Pass 2 的 `WHERE label_filled_at IS NULL` 把它們從候選池剔除。
#   `label_net_edge_bps` 仍 NULL（不污染訓練集，與 Pass 2 既有設計對齊）。
#
# 安全保證：
#   - 默認 30d threshold conservative（一般持倉 < 7d）
#   - F4-2 audit row filter 保留（與 Pass 1+2 對齊）
#   - 已 filled 的 row 不會被覆寫（WHERE label_filled_at IS NULL）
#   - 與 Pass 2 標 'orphan_close:%/adopted_close:%/shadow_fill:%' 不衝突
#     （Pass 2 在有 close fill 時 trigger；Pass 3 在無 close fill 時 trigger）
# ============================================================
_BACKFILL_ABANDONED_SQL = """
WITH abandoned_entries AS (
    SELECT l.context_id
    FROM learning.decision_features l
    WHERE l.label_filled_at IS NULL
      AND l.engine_mode = ANY(%(engine_modes)s)
      AND l.ts < (now() - (%(abandon_after_days)s || ' days')::interval)
      AND NOT EXISTS (
          SELECT 1 FROM trading.fills f
          WHERE f.entry_context_id = l.context_id
            -- F4-2 audit row filter（與 Pass 1+2 對齊）
            AND (f.strategy_name IS NULL OR f.strategy_name NOT LIKE 'unattributed:%%')
      )
    ORDER BY l.ts
    LIMIT %(batch_limit)s
)
UPDATE learning.decision_features d
SET label_close_tag = %(abandoned_tag)s,
    label_filled_at = now()
    -- label_net_edge_bps 故意保 NULL（與 Pass 2 一致：不污染訓練集）
    -- label_net_edge_bps intentionally left NULL (excluded from training set, like Pass 2)
FROM abandoned_entries a
WHERE d.context_id = a.context_id
RETURNING d.context_id
"""


def backfill_labels(
    pg_url: Optional[str] = None,
    engine_mode: str = "demo",
    batch_limit: int = 5000,
    dry_run: bool = False,
    abandon_after_days: Optional[int] = DEFAULT_ABANDON_AFTER_DAYS,
) -> BackfillResult:
    """Run one backfill pass for `engine_mode`.
    為指定 engine_mode 執行一次回填。

    Args:
        pg_url:               DSN override（不傳則用環境變數）
        engine_mode:          'paper' | 'demo' | 'live' | 'live_demo'。
                              `live` 自動擴展為 ('live', 'live_demo')；
                              `live_demo` 保持精確。
        batch_limit:          每 pass 最大處理行數（共三 pass）
        dry_run:              True 則 ROLLBACK 不 COMMIT
        abandon_after_days:   Pass 3 abandoned 標記閾值。`None` 跳過 Pass 3
                              （安全 fallback；保留 Pass 1+2 既有行為）。
                              默認 30d（DEFAULT_ABANDON_AFTER_DAYS）。

    Returns BackfillResult summary including abandoned_count.
    """
    engine_modes = list(engine_mode_scope(engine_mode))

    result = BackfillResult()

    conn = _get_conn(pg_url)
    try:
        with conn.cursor() as cur:
            # Pass 1: included (with labels)
            # Pass 1：標準 backfill — entry+close 完整 + 計算 net_edge_bps
            cur.execute(
                _BACKFILL_INCLUDED_SQL,
                {"engine_modes": engine_modes, "batch_limit": batch_limit},
            )
            included_rows = cur.fetchall()
            for _ctx, strat, split_flag in included_rows:
                result.filled_count += 1
                if strat == "grid_trading":
                    result.grid_merged_count += 1
                elif split_flag:
                    result.split_blend_count += 1

            # Pass 2: excluded (mark tried, keep label NULL)
            # Pass 2：close fill 是 orphan/adopted/shadow 前綴，標 close_tag 但
            # label_net_edge_bps 保 NULL（永久排除訓練集）
            cur.execute(
                _BACKFILL_EXCLUDED_SQL,
                {"engine_modes": engine_modes, "batch_limit": batch_limit},
            )
            excluded_rows = cur.fetchall()
            result.excluded_count = len(excluded_rows)

            # Pass 3 (P0-V3-MIT-ROOT-CAUSE 2026-05-09): abandoned marker
            # Pass 3：把超過 abandon_after_days 仍未平倉的 row 標 abandoned，
            # 防止 attribution_chain_ok denominator 被歷史死行撐爆。
            #
            # `abandon_after_days=None` 跳過 Pass 3 = 保留 Pass 1+2 既有 60d 行為
            # （safety fallback：caller 可選擇不 enable Pass 3）
            if abandon_after_days is not None:
                cur.execute(
                    _BACKFILL_ABANDONED_SQL,
                    {
                        "engine_modes":        engine_modes,
                        "batch_limit":         batch_limit,
                        "abandon_after_days":  int(abandon_after_days),
                        "abandoned_tag":       ABANDONED_TAG_PREFIX,
                    },
                )
                abandoned_rows = cur.fetchall()
                result.abandoned_count = len(abandoned_rows)

            if (
                result.filled_count    >= batch_limit
                or result.excluded_count >= batch_limit
                or result.abandoned_count >= batch_limit
            ):
                result.batch_limit_hit = True

        if dry_run:
            conn.rollback()
            logger.info("DRY-RUN rollback: %s", result.to_dict())
        else:
            conn.commit()
            logger.info(
                "backfill_labels(%s) committed: filled=%d excluded=%d abandoned=%d split=%d grid=%d",
                engine_mode,
                result.filled_count,
                result.excluded_count,
                result.abandoned_count,
                result.split_blend_count,
                result.grid_merged_count,
            )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return result


# ============================================================
# Stale-label alerter (§8.2 acceptance check).
# 過期標籤告警（§8.2 驗收條件）。
# ============================================================
_STALE_LABELS_SQL = """
SELECT engine_mode,
       strategy_name,
       count(*) AS stale_rows,
       min(ts)  AS oldest_ts,
       max(ts)  AS newest_ts
FROM learning.decision_features
WHERE label_filled_at IS NULL
  AND ts < now() - (%(max_age_days)s || ' days')::interval
  AND (%(engine_mode_all)s OR engine_mode = ANY(%(engine_modes)s))
GROUP BY engine_mode, strategy_name
ORDER BY stale_rows DESC
"""


def check_stale_labels(
    pg_url: Optional[str] = None,
    max_age_days: int = DEFAULT_STALE_DAYS,
    engine_mode: Optional[str] = None,
) -> list[dict]:
    """Find feature rows older than `max_age_days` without label attempt.
    查找超過 max_age_days 未嘗試標籤的特徵行。

    Returns list of {engine_mode, strategy_name, stale_rows, oldest_ts, newest_ts}.
    """
    engine_modes = list(engine_mode_scope(engine_mode)) if engine_mode is not None else []
    conn = _get_conn(pg_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                _STALE_LABELS_SQL,
                {
                    "max_age_days": max_age_days,
                    "engine_mode_all": engine_mode is None,
                    "engine_modes": engine_modes,
                },
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    return [
        {
            "engine_mode":   r[0],
            "strategy_name": r[1],
            "stale_rows":    int(r[2]),
            "oldest_ts":     r[3].isoformat() if r[3] else None,
            "newest_ts":     r[4].isoformat() if r[4] else None,
        }
        for r in rows
    ]


# ============================================================
# Fill-rate summary (operator dashboard helper)
# 填充率摘要（供 operator 儀表板使用）
# ============================================================
_FILL_RATE_SQL = """
SELECT engine_mode,
       strategy_name,
       count(*) FILTER (WHERE label_net_edge_bps IS NOT NULL) AS labeled,
       count(*) FILTER (WHERE label_filled_at IS NOT NULL
                        AND label_net_edge_bps IS NULL)       AS excluded,
       count(*) FILTER (WHERE label_filled_at IS NULL)        AS pending,
       count(*)                                               AS total
FROM learning.decision_features
WHERE ts >= now() - (%(window_hours)s || ' hours')::interval
GROUP BY engine_mode, strategy_name
ORDER BY engine_mode, strategy_name
"""


def fill_rate_summary(
    pg_url: Optional[str] = None,
    window_hours: int = 48,
) -> list[dict]:
    """Per-strategy label fill-rate within recent window (§8.2 · demo 48h > 95%).
    最近窗口內每策略標籤填充率（§8.2：demo 48h 需 >95%）。"""
    conn = _get_conn(pg_url)
    try:
        with conn.cursor() as cur:
            cur.execute(_FILL_RATE_SQL, {"window_hours": window_hours})
            rows = cur.fetchall()
    finally:
        conn.close()

    out = []
    for em, strat, labeled, excluded, pending, total in rows:
        denom = labeled + excluded + pending
        rate = (labeled + excluded) / denom if denom > 0 else 0.0
        out.append({
            "engine_mode":   em,
            "strategy_name": strat,
            "labeled":       int(labeled),
            "excluded":      int(excluded),
            "pending":       int(pending),
            "total":         int(total),
            "fill_rate":     round(rate, 4),
        })
    return out


# ============================================================
# attribution_chain_ratio 觀察工具（P0-V3-MIT-ROOT-CAUSE healthcheck 配套）
# Attribution chain ratio observer (P0-V3 healthcheck companion).
#
# 用途：
#   提供 healthcheck / sentinel 一個直查 attribution_chain_ok / total ratio
#   的入口，避免 caller 重複寫 SQL。同時提供 by-bucket breakdown，
#   區分 P1/P2/P3/unfilled/abandoned 各佔比，幫助監控 Pass 3 是否生效。
# ============================================================
_ATTRIBUTION_RATIO_SQL = """
SELECT
    COUNT(*)                                          AS total_n,
    COUNT(*) FILTER (WHERE attribution_chain_ok)      AS ok_n,
    COUNT(*) FILTER (WHERE label_filled_at IS NULL)   AS unfilled_n,
    COUNT(*) FILTER (WHERE label_close_tag LIKE 'abandoned:%%') AS abandoned_n,
    COUNT(*) FILTER (
        WHERE label_filled_at IS NOT NULL
          AND label_net_edge_bps IS NULL
          AND (label_close_tag LIKE 'orphan_close:%%'
            OR label_close_tag LIKE 'adopted_close:%%'
            OR label_close_tag LIKE 'shadow_fill:%%')
    )                                                 AS excluded_n
FROM learning.mlde_edge_training_rows
WHERE ts > NOW() - (%(window_hours)s || ' hours')::interval
"""


def attribution_chain_ratio(
    pg_url: Optional[str] = None,
    window_hours: int = 24,
) -> dict:
    """Return attribution_chain_ok ratio + bucket breakdown for monitoring.
    回傳 attribution_chain_ok 比例 + 各 bucket 拆分供監控。

    Bucket 含義：
      ok_n: attribution_chain_ok = true（已 close + 算出 net_edge_bps）
      unfilled_n: 未 backfill（持倉中或 stuck，待 Pass 1+2 或 Pass 3 處理）
      abandoned_n: Pass 3 已標 abandoned:no_close_fill（無 close fill 的死行）
      excluded_n: Pass 2 標 orphan/adopted/shadow（永久排除訓練集）

    Returns:
        {
            'window_hours': int,
            'total_n': int,
            'ok_n': int,
            'ok_ratio': float (0-1),
            'unfilled_n': int,
            'abandoned_n': int,
            'excluded_n': int,
        }
    """
    conn = _get_conn(pg_url)
    try:
        with conn.cursor() as cur:
            cur.execute(_ATTRIBUTION_RATIO_SQL, {"window_hours": window_hours})
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        return {
            "window_hours": int(window_hours),
            "total_n": 0, "ok_n": 0, "ok_ratio": 0.0,
            "unfilled_n": 0, "abandoned_n": 0, "excluded_n": 0,
        }

    total_n, ok_n, unfilled_n, abandoned_n, excluded_n = row
    return {
        "window_hours": int(window_hours),
        "total_n":      int(total_n or 0),
        "ok_n":         int(ok_n or 0),
        "ok_ratio":     round((ok_n or 0) / max(total_n or 1, 1), 6),
        "unfilled_n":   int(unfilled_n or 0),
        "abandoned_n":  int(abandoned_n or 0),
        "excluded_n":   int(excluded_n or 0),
    }


# ============================================================
# CLI
# ============================================================
def _main() -> int:
    parser = argparse.ArgumentParser(description="EDGE-P3-1 label backfill")
    parser.add_argument("--engine-mode", choices=["paper", "demo", "live", "live_demo"], default="demo")
    parser.add_argument("--batch-limit", type=int, default=5000)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check-stale", action="store_true",
                        help="Only run stale-label check, skip backfill")
    parser.add_argument("--stale-days", type=int, default=DEFAULT_STALE_DAYS)
    parser.add_argument("--summary", action="store_true",
                        help="Print fill-rate summary after backfill")
    # P0-V3-MIT-ROOT-CAUSE 2026-05-09: Pass 3 abandoned threshold（默認 30d；
    # 設 0 或負數可關閉 Pass 3 = 退化為 Pass 1+2 既有行為，safety fallback）。
    parser.add_argument("--abandon-after-days", type=int, default=DEFAULT_ABANDON_AFTER_DAYS,
                        help=("Pass 3：超過 N 天仍 unfilled 的 row 標 abandoned:no_close_fill，"
                              "防止歷史死行撐爆 attribution_chain_ok denominator；"
                              f"≤0 關閉 Pass 3。默認 {DEFAULT_ABANDON_AFTER_DAYS}d。"))
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.check_stale:
        stale = check_stale_labels(max_age_days=args.stale_days, engine_mode=args.engine_mode)
        if not stale:
            print(f"OK: no labels older than {args.stale_days}d for {args.engine_mode}")
            return 0
        print(f"STALE labels > {args.stale_days}d:")
        for row in stale:
            print(f"  {row}")
        return 1  # non-zero = operator alert

    # ≤0 關閉 Pass 3（caller-controlled safety fallback）
    abandon_days = args.abandon_after_days if args.abandon_after_days > 0 else None
    result = backfill_labels(
        engine_mode=args.engine_mode,
        batch_limit=args.batch_limit,
        dry_run=args.dry_run,
        abandon_after_days=abandon_days,
    )
    print(f"backfill result: {result.to_dict()}")

    if args.summary:
        summary = fill_rate_summary()
        print("\nfill-rate summary (last 48h):")
        for row in summary:
            print(f"  {row}")

    return 0


if __name__ == "__main__":
    sys.exit(_main())
