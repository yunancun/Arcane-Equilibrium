"""
Edge Label Backfill — populate learning.decision_features.label_net_edge_bps.
邊緣標籤回填 — 填充 learning.decision_features 的 label_net_edge_bps。

MODULE_NOTE (EN): EDGE-P3-1 Stage 1 (PA) label backfill job. Reads unlabeled
    rows from learning.decision_features, joins with trading.fills (entry +
    close fills via context_id / entry_context_id), computes realized_net_edge
    bps per §4.1, handles split qty-weighted blend (§4.2) and grid VWAP merge
    (§4.3), excludes orphan_close/adopted_close/shadow_fill tags, and UPDATEs
    the feature rows. Also exposes check_stale_labels() alerter (§8.2 acceptance
    criteria: demo 48h label fill rate > 95%).

MODULE_NOTE (中): EDGE-P3-1 Stage 1（PA）標籤回填任務。從 learning.decision_features
    讀取未標籤行，JOIN trading.fills（entry + close 透過 context_id / entry_context_id），
    按 §4.1 計算 realized_net_edge bps，處理 split qty-weighted blend（§4.2）與 grid VWAP
    合併（§4.3），排除 orphan_close/adopted_close/shadow_fill 標籤，UPDATE 回特徵行。
    另外 check_stale_labels() 告警（§8.2 驗收：demo 48h 填充率 > 95%）。

Spec: docs/references/2026-04-15--edge_predictor_spec.md v1.4
SQL migration: sql/migrations/V017__edge_predictor_tables.sql

Usage / 用法:
    source settings/environment_files/basic_system_services.env
    python3 -m program_code.ml_training.edge_label_backfill \
        --engine-mode demo --batch-limit 5000
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
    filled_count:          int = 0  # rows with non-NULL label written
    excluded_count:        int = 0  # rows marked tried-but-excluded
    split_blend_count:     int = 0  # non-grid, close_count > 1
    grid_merged_count:     int = 0  # grid_trading strategy
    skipped_no_entry_fill: int = 0  # entry row missing
    batch_limit_hit:       bool = False

    def to_dict(self) -> dict:
        return {
            "filled":          self.filled_count,
            "excluded":        self.excluded_count,
            "split_blend":     self.split_blend_count,
            "grid_merged":     self.grid_merged_count,
            "skipped_no_entry": self.skipped_no_entry_fill,
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
        dsn = f"postgresql://redacted@{host}:{port}/{db}"
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


def backfill_labels(
    pg_url: Optional[str] = None,
    engine_mode: str = "demo",
    batch_limit: int = 5000,
    dry_run: bool = False,
) -> BackfillResult:
    """Run one backfill pass for `engine_mode`.
    為指定 engine_mode 執行一次回填。

    Args:
        pg_url:      DSN override (else env vars / 優先環境變量)
        engine_mode: 'paper' | 'demo' | 'live' | 'live_demo'. `live` widens to
            `('live','live_demo')`; explicit `live_demo` remains exact.
        batch_limit: max rows per pass (two passes: included + excluded)
        dry_run:     if True, ROLLBACK instead of COMMIT

    Returns BackfillResult summary.
    """
    engine_modes = list(engine_mode_scope(engine_mode))

    result = BackfillResult()

    conn = _get_conn(pg_url)
    try:
        with conn.cursor() as cur:
            # Pass 1: included (with labels)
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
            cur.execute(
                _BACKFILL_EXCLUDED_SQL,
                {"engine_modes": engine_modes, "batch_limit": batch_limit},
            )
            excluded_rows = cur.fetchall()
            result.excluded_count = len(excluded_rows)

            if result.filled_count >= batch_limit or result.excluded_count >= batch_limit:
                result.batch_limit_hit = True

        if dry_run:
            conn.rollback()
            logger.info("DRY-RUN rollback: %s", result.to_dict())
        else:
            conn.commit()
            logger.info(
                "backfill_labels(%s) committed: filled=%d excluded=%d split=%d grid=%d",
                engine_mode,
                result.filled_count,
                result.excluded_count,
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

    result = backfill_labels(
        engine_mode=args.engine_mode,
        batch_limit=args.batch_limit,
        dry_run=args.dry_run,
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
