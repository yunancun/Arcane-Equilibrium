#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────
# MODULE_NOTE
# 模組目的：2026-05-02 P0 sqlx hash drift 修復後 3C TOML 真實生效
#          （`dynamic_stop.base_ratio = 0.25` + funding_arb 3% SL override）。
#          本 audit 在 deploy 後 7 日（target run date 2026-05-09）跑，
#          對比 5 個 metric 的 prior 7d baseline (2026-04-25 → 2026-05-02 17:42 UTC)
#          與 post-deploy 7d window (2026-05-02 17:42 UTC → 2026-05-09)。
#          僅產生 Markdown 報告，**不執行任何 DB write、不觸發任何 action**。
# Module purpose: After 2026-05-02 P0 sqlx hash drift fix, 3C TOML
#                 (`dynamic_stop.base_ratio = 0.25` + funding_arb 3% SL
#                 override) became truly active. Run this audit 7 days
#                 post-deploy (target 2026-05-09) to compare 5 metrics
#                 across prior 7d baseline (2026-04-25 → 2026-05-02 17:42 UTC)
#                 vs post-deploy 7d window. Read-only Markdown report;
#                 no DB write, no auto-action.
#
# 關聯記憶 / Refs:
#   - memory/project_2026_05_02_p0_sqlx_hash_drift.md
#   - memory/project_funding_arb_v2_deprecation_path.md
#   - TODO.md「📅 排程提醒（2026-05-02 P0 + 3C 後續）」section
#
# 執行 / Usage:
#   bash helper_scripts/db/audit/2026-05-09_3c_7d_audit.sh           # full output
#   bash helper_scripts/db/audit/2026-05-09_3c_7d_audit.sh --quiet   # 只印非 PASS metric
#
# Exit codes:
#   0 = all 5 metrics moved in expected direction (PA review optional)
#   1 = ≥1 metric moved against expectation (operator decision required)
#   2 = DB connection / fatal SQL error (env/credentials issue)
# ─────────────────────────────────────────────────────────
"""3C deploy 7d follow-up audit — 5 metric prior-vs-post comparison.

讀取 trading.fills + learning.mlde_edge_training_rows，輸出 5 個 metric
的 baseline / current / delta / verdict 表格 + 1 行整體判斷。

Reuses helper_scripts/db/passive_wait_healthcheck/db.py for connection
parameter resolution; reuses [40] / [38] SQL pattern for the two
healthcheck-aligned metrics. Three new SQL added for dyn_stop fire
count, funding_arb hard_stop validation, and demo gross PnL delta.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

# 將 sibling passive_wait_healthcheck package 加入 sys.path，重用 _get_conn。
# Add sibling passive_wait_healthcheck package to sys.path for _get_conn reuse.
_HERE = Path(__file__).resolve().parent
_PARENT = _HERE.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

# fmt: off
from passive_wait_healthcheck.db import _get_conn  # noqa: E402
# fmt: on


# ── Constants — deploy timestamp + windowing ────────────────────────────────────

# 3C TOML 真實生效時刻：2026-05-02 17:42 UTC（19:42 CEST）
# 對應 commit 6cb1c3b 後 restart_all.sh --rebuild --keep-auth 完成。
# True 3C TOML deploy timestamp: 2026-05-02 17:42 UTC (19:42 CEST).
DEPLOY_UTC = "2026-05-02 17:42:00+00"

# Post-deploy window：deploy → deploy + 7 days
# Prior baseline window：deploy - 7 days → deploy
POST_WINDOW_DAYS = 7
PRIOR_WINDOW_DAYS = 7

# 5 個 metric 預期方向（base_ratio 0.30→0.25 收緊 + funding_arb 3% SL hard cap）
# Expected direction post-3C-deploy:
#   - [40] avg_net_bps:        unchanged-or-up   (SL 收緊不應傷 net edge，預期 ≥ baseline)
#   - dyn_stop fire by strategy: down            (base_ratio 0.30→0.25 應減少 stop fire；逆向需警報)
#   - funding_arb hard_stop firings: any > 3% notional → FAIL
#   - [38] grid_lifecycle_ratio drift: stable    (grid 對 dyn floor 收緊敏感，需驗未漂)
#   - demo gross PnL delta:    unchanged-or-up   (SL 收緊不應淨虧損)


# ── Result struct ───────────────────────────────────────────────────────────────


@dataclass
class MetricResult:
    """Per-metric baseline/current/delta/verdict snapshot.

    每個 metric 的 baseline / current / delta / verdict 結果。
    """

    name: str               # e.g. "[40] realized_edge_acceptance.avg_net_bps"
    baseline: str           # baseline 值（人類可讀）/ baseline value (human-readable)
    current: str            # current 值 / current value
    delta: str              # delta 字串（含單位）/ delta string with units
    delta_pct: str          # delta percent string
    verdict: str            # PASS / WARN / FAIL
    note: str = ""          # 評語 / commentary


def _fmt_pct(num: float | None, den: float | None) -> str:
    """Format ``num/den`` as percent or ``n/a`` if denominator is 0/None."""
    if num is None or den is None or abs(den) < 1e-9:
        return "n/a"
    return f"{(num / den * 100.0):+.1f}%"


def _fmt_delta(curr: float | None, base: float | None, unit: str = "") -> str:
    """Format ``curr - base`` as signed string + optional unit."""
    if curr is None or base is None:
        return "n/a"
    return f"{(curr - base):+.2f}{unit}"


# ── Metric 1 — [40] realized_edge_acceptance window comparison ──────────────────


def metric_realized_edge_acceptance(cur) -> MetricResult:
    """Metric 1: [40] DB-truth realized edge acceptance.

    對比 prior/post 兩個 7d window 的 (avg_net_bps, win_rate, maker_like%,
    fee_drop%) 四個子指標。SL 收緊不應傷 net edge，預期 avg_net 不下降。

    Compare prior/post 7d windows on (avg_net_bps, win_rate, maker_like%,
    fee_drop%). SL tightening should not harm net edge — expect avg_net
    flat or improved.
    """
    try:
        cur.connection.rollback()
    except Exception:
        pass

    # Aggregate post-deploy window vs prior baseline window in one shot.
    # 用 conditional aggregation 一次 query 兩個 window。
    try:
        cur.execute(
            """
            SELECT
              -- Post-deploy window (deploy → deploy+7d)
              COUNT(*) FILTER (
                WHERE ts >= %(deploy)s::timestamptz
                  AND ts <  %(deploy)s::timestamptz + interval '7 days'
              )::int AS post_n,
              AVG(net_bps_after_fee) FILTER (
                WHERE ts >= %(deploy)s::timestamptz
                  AND ts <  %(deploy)s::timestamptz + interval '7 days'
              )::float8 AS post_avg_net,
              (COUNT(*) FILTER (
                WHERE ts >= %(deploy)s::timestamptz
                  AND ts <  %(deploy)s::timestamptz + interval '7 days'
                  AND net_bps_after_fee > 0
              )::float8
              / NULLIF(COUNT(*) FILTER (
                WHERE ts >= %(deploy)s::timestamptz
                  AND ts <  %(deploy)s::timestamptz + interval '7 days'
              ), 0)::float8) AS post_win_rate,

              -- Prior baseline window (deploy-7d → deploy)
              COUNT(*) FILTER (
                WHERE ts >= %(deploy)s::timestamptz - interval '7 days'
                  AND ts <  %(deploy)s::timestamptz
              )::int AS prior_n,
              AVG(net_bps_after_fee) FILTER (
                WHERE ts >= %(deploy)s::timestamptz - interval '7 days'
                  AND ts <  %(deploy)s::timestamptz
              )::float8 AS prior_avg_net,
              (COUNT(*) FILTER (
                WHERE ts >= %(deploy)s::timestamptz - interval '7 days'
                  AND ts <  %(deploy)s::timestamptz
                  AND net_bps_after_fee > 0
              )::float8
              / NULLIF(COUNT(*) FILTER (
                WHERE ts >= %(deploy)s::timestamptz - interval '7 days'
                  AND ts <  %(deploy)s::timestamptz
              ), 0)::float8) AS prior_win_rate
            FROM learning.mlde_edge_training_rows
            WHERE engine_mode IN ('demo', 'live_demo')
              AND attribution_chain_ok
              AND net_bps_after_fee IS NOT NULL
            """,
            {"deploy": DEPLOY_UTC},
        )
        row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return MetricResult(
            name="[40] realized_edge_acceptance",
            baseline="n/a", current="n/a", delta="n/a", delta_pct="n/a",
            verdict="WARN",
            note=f"query failed: {type(exc).__name__}: {exc}",
        )

    if not row:
        return MetricResult(
            name="[40] realized_edge_acceptance",
            baseline="n/a", current="n/a", delta="n/a", delta_pct="n/a",
            verdict="WARN", note="no rows returned",
        )

    post_n, post_avg, post_win, prior_n, prior_avg, prior_win = row
    post_n = int(post_n or 0)
    prior_n = int(prior_n or 0)

    # 樣本不足：回 WARN，不做方向判斷。
    # Insufficient sample: return WARN, skip direction verdict.
    if post_n < 5 or prior_n < 5:
        return MetricResult(
            name="[40] realized_edge_acceptance",
            baseline=f"n={prior_n}",
            current=f"n={post_n}",
            delta="n/a",
            delta_pct="n/a",
            verdict="WARN",
            note=f"sample too small (post={post_n}, prior={prior_n}; need ≥5 each)",
        )

    post_avg = float(post_avg or 0.0)
    prior_avg = float(prior_avg or 0.0)
    post_win = float(post_win or 0.0) * 100.0
    prior_win = float(prior_win or 0.0) * 100.0

    # 方向判斷：avg_net 不應顯著下降（容差 -2 bps）
    # Direction verdict: avg_net should not drop materially (tolerance -2 bps)
    delta_avg = post_avg - prior_avg
    if delta_avg < -2.0:
        verdict = "FAIL"
        note = (
            f"avg_net dropped {delta_avg:+.2f}bps post-deploy "
            f"(SL tightening should not harm edge; investigate)"
        )
    elif delta_avg < 0.0:
        verdict = "WARN"
        note = f"avg_net slightly down {delta_avg:+.2f}bps; within tolerance"
    else:
        verdict = "PASS"
        note = f"avg_net stable or up ({delta_avg:+.2f}bps)"

    return MetricResult(
        name="[40] realized_edge_acceptance",
        baseline=f"n={prior_n}, avg_net={prior_avg:.2f}bps, win={prior_win:.1f}%",
        current=f"n={post_n}, avg_net={post_avg:.2f}bps, win={post_win:.1f}%",
        delta=_fmt_delta(post_avg, prior_avg, "bps"),
        delta_pct=_fmt_pct(delta_avg, prior_avg),
        verdict=verdict,
        note=note,
    )


# ── Metric 2 — dyn_stop fire count by strategy (post vs prior) ──────────────────


def metric_dyn_stop_fire_count_by_strategy(cur) -> MetricResult:
    """Metric 2: dyn_stop fire count grouped by underlying strategy.

    base_ratio 0.30→0.25 收緊預期會「減少 stop fire」（floor 收緊 → fewer
    breaches before exit）；逆向（fire 增加）需 PA review。透過
    `entry_context_id` JOIN 取 entry 的 strategy_name。

    base_ratio tightening (0.30→0.25) expected to reduce stop fires
    (tighter floor → fewer breaches before exit). Inverse direction
    (fire count up) requires PA review. Uses `entry_context_id` JOIN
    to get the entry strategy_name.
    """
    try:
        cur.connection.rollback()
    except Exception:
        pass

    sql = """
WITH dyn_stops AS (
  SELECT close.ts AS close_ts,
         entry.strategy_name AS owner_strategy
  FROM trading.fills close
  LEFT JOIN trading.fills entry
    ON entry.context_id = close.entry_context_id
   AND entry.strategy_name NOT LIKE 'risk_close:%%'
   AND entry.strategy_name NOT LIKE 'strategy_close:%%'
  WHERE close.engine_mode = 'demo'
    AND close.strategy_name LIKE 'risk_close:DYNAMIC%%'
    AND close.ts >= %(deploy)s::timestamptz - interval '7 days'
    AND close.ts <  %(deploy)s::timestamptz + interval '7 days'
)
SELECT
  COALESCE(owner_strategy, '<unattributed>') AS owner,
  COUNT(*) FILTER (
    WHERE close_ts >= %(deploy)s::timestamptz - interval '7 days'
      AND close_ts <  %(deploy)s::timestamptz
  )::int AS prior_n,
  COUNT(*) FILTER (
    WHERE close_ts >= %(deploy)s::timestamptz
      AND close_ts <  %(deploy)s::timestamptz + interval '7 days'
  )::int AS post_n
FROM dyn_stops
GROUP BY 1
ORDER BY post_n DESC, prior_n DESC
"""
    try:
        cur.execute(sql, {"deploy": DEPLOY_UTC})
        rows = cur.fetchall() or []
    except Exception as exc:  # noqa: BLE001
        return MetricResult(
            name="dyn_stop_fire_count_by_strategy",
            baseline="n/a", current="n/a", delta="n/a", delta_pct="n/a",
            verdict="WARN",
            note=f"query failed: {type(exc).__name__}: {exc}",
        )

    if not rows:
        return MetricResult(
            name="dyn_stop_fire_count_by_strategy",
            baseline="0", current="0", delta="0", delta_pct="n/a",
            verdict="WARN",
            note="no risk_close:DYNAMIC% fills in 14d window",
        )

    prior_total = sum(int(r[1] or 0) for r in rows)
    post_total = sum(int(r[2] or 0) for r in rows)
    delta = post_total - prior_total

    # 顯示 top 5 strategy 的明細給 operator 看。
    # Show top 5 strategies for operator visibility.
    breakdown_lines = []
    for row in rows[:5]:
        owner, prior_n, post_n = row[0], int(row[1] or 0), int(row[2] or 0)
        breakdown_lines.append(f"{owner}: {prior_n}→{post_n}")
    breakdown = "; ".join(breakdown_lines)

    # 方向判斷：post < prior * 1.20（容許 +20% 噪音）= PASS；
    # 若 post > prior * 1.50 = FAIL（base_ratio 收緊但 fire 反增 50%+ 不合預期）。
    if prior_total == 0:
        verdict = "WARN"
        note = "prior baseline is 0 — cannot compute direction"
    elif post_total <= prior_total * 1.20:
        verdict = "PASS"
        note = f"fire count flat-or-down post-deploy. Top: {breakdown}"
    elif post_total <= prior_total * 1.50:
        verdict = "WARN"
        note = (
            f"fire count up {((post_total / prior_total) - 1) * 100:+.1f}% "
            f"(<50% tolerance). Top: {breakdown}"
        )
    else:
        verdict = "FAIL"
        note = (
            f"fire count up {((post_total / prior_total) - 1) * 100:+.1f}% "
            f"(>50% — unexpected after base_ratio tightening). Top: {breakdown}"
        )

    return MetricResult(
        name="dyn_stop_fire_count_by_strategy",
        baseline=f"total={prior_total}",
        current=f"total={post_total}",
        delta=f"{delta:+d}",
        delta_pct=_fmt_pct(float(delta), float(prior_total) if prior_total else None),
        verdict=verdict,
        note=note,
    )


# ── Metric 3 — funding_arb hard_stop / dynamic_stop firings (3% notional cap check) ────


def metric_funding_arb_hard_stop_validation(cur) -> MetricResult:
    """Metric 3: funding_arb hard_stop firings within 3% notional cap.

    funding_arb 在 3C TOML 後 stop_loss_max_pct_override = 3.0%。
    任何單筆 abs(realized_pnl) / entry_notional > 3% + slippage buffer (≤5%)
    都是異常（binary 邏輯 / SL gate / notional 計算 bug）。

    Post-3C, funding_arb stop_loss_max_pct_override = 3.0%. Any single-fill
    abs(realized_pnl) / entry_notional > 3% + slippage buffer (≤5%) is
    anomalous (binary logic / SL gate / notional calc bug).
    """
    try:
        cur.connection.rollback()
    except Exception:
        pass

    # Pair close fill (risk_close:HARD/DYNAMIC) with entry (funding_arb)
    # 用 entry_context_id 配對 close 與 entry，篩 owner=funding_arb 的 stop fills。
    sql = """
WITH funding_arb_stops AS (
  SELECT close.ts AS close_ts,
         close.realized_pnl AS pnl,
         close.symbol AS symbol,
         close.strategy_name AS close_tag,
         entry.price AS entry_price,
         close.qty AS close_qty,
         (entry.price * close.qty) AS entry_notional
  FROM trading.fills close
  JOIN trading.fills entry
    ON entry.context_id = close.entry_context_id
   AND entry.strategy_name = 'funding_arb'
  WHERE close.engine_mode = 'demo'
    AND (close.strategy_name LIKE 'risk_close:HARD%%'
         OR close.strategy_name LIKE 'risk_close:DYNAMIC%%')
    AND close.ts >= %(deploy)s::timestamptz
    AND close.ts <  %(deploy)s::timestamptz + interval '7 days'
)
SELECT
  COUNT(*)::int AS n_fires,
  COUNT(*) FILTER (
    WHERE entry_notional > 0
      AND abs(pnl) / entry_notional > 0.03
  )::int AS n_over_3pct,
  COUNT(*) FILTER (
    WHERE entry_notional > 0
      AND abs(pnl) / entry_notional > 0.05
  )::int AS n_over_5pct,
  MAX(
    CASE WHEN entry_notional > 0
         THEN abs(pnl) / entry_notional
         ELSE NULL END
  )::float8 AS max_loss_pct
FROM funding_arb_stops
"""
    try:
        cur.execute(sql, {"deploy": DEPLOY_UTC})
        row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return MetricResult(
            name="funding_arb_hard_stop_validation",
            baseline="n/a", current="n/a", delta="n/a", delta_pct="n/a",
            verdict="WARN",
            note=f"query failed: {type(exc).__name__}: {exc}",
        )

    if not row:
        return MetricResult(
            name="funding_arb_hard_stop_validation",
            baseline="0 fires (pre-deploy not measured)",
            current="0 fires",
            delta="0", delta_pct="n/a",
            verdict="PASS",
            note="no funding_arb stop fills in post-deploy 7d window",
        )

    n_fires, n_over_3pct, n_over_5pct, max_loss = row
    n_fires = int(n_fires or 0)
    n_over_3pct = int(n_over_3pct or 0)
    n_over_5pct = int(n_over_5pct or 0)
    max_loss_pct = float(max_loss or 0.0) * 100.0

    if n_over_5pct > 0:
        verdict = "FAIL"
        note = (
            f"{n_over_5pct} fills exceeded 5% notional loss "
            f"(max={max_loss_pct:.2f}%); SL gate / binary logic / notional calc bug"
        )
    elif n_over_3pct > 0:
        verdict = "WARN"
        note = (
            f"{n_over_3pct} fills exceeded 3% (slippage zone, max={max_loss_pct:.2f}%); "
            f"acceptable if within 5% slippage buffer"
        )
    else:
        verdict = "PASS"
        note = f"all {n_fires} fires within 3% cap (max={max_loss_pct:.2f}%)"

    return MetricResult(
        name="funding_arb_hard_stop_validation",
        baseline="n/a (pre-3C had no 3% cap)",
        current=f"{n_fires} fires, {n_over_3pct} > 3%, {n_over_5pct} > 5%",
        delta="n/a",
        delta_pct="n/a",
        verdict=verdict,
        note=note,
    )


# ── Metric 4 — [38] grid_trading_lifecycle_drift (lifetime ratio stability) ─────


def metric_grid_lifecycle_drift(cur) -> MetricResult:
    """Metric 4: [38] grid_trading lifetime drift demo vs live_demo.

    grid 對 dyn floor 收緊敏感（單倉壽命太短會錯失 mean-reversion 邊際）。
    對比 prior/post 7d 的 demo p50 lifetime — 顯著縮短 (>30%) 需 PA review。

    grid_trading is sensitive to dyn floor tightening (too-short lifetime
    misses mean-reversion edge). Compare prior/post 7d demo p50 lifetime —
    materially shorter (>30%) needs PA review.
    """
    try:
        cur.connection.rollback()
    except Exception:
        pass

    sql = """
WITH grid_lifecycles AS (
  SELECT entry.ts AS entry_ts,
         close.ts AS close_ts,
         EXTRACT(EPOCH FROM (close.ts - entry.ts)) / 60.0 AS lifetime_min
  FROM trading.fills entry
  JOIN trading.fills close
    ON close.entry_context_id = entry.context_id
   AND close.engine_mode = 'demo'
   AND (close.strategy_name LIKE 'strategy_close:grid_close%%'
        OR close.strategy_name LIKE 'risk_close:%%'
        OR close.exit_reason IS NOT NULL)
  WHERE entry.engine_mode = 'demo'
    AND entry.strategy_name = 'grid_trading'
    AND entry.ts >= %(deploy)s::timestamptz - interval '7 days'
    AND entry.ts <  %(deploy)s::timestamptz + interval '7 days'
)
SELECT
  -- prior 7d
  COUNT(*) FILTER (WHERE entry_ts < %(deploy)s::timestamptz)::int AS prior_n,
  percentile_cont(0.5) WITHIN GROUP (
    ORDER BY CASE WHEN entry_ts < %(deploy)s::timestamptz
                  THEN lifetime_min END
  )::float8 AS prior_p50,
  -- post 7d
  COUNT(*) FILTER (WHERE entry_ts >= %(deploy)s::timestamptz)::int AS post_n,
  percentile_cont(0.5) WITHIN GROUP (
    ORDER BY CASE WHEN entry_ts >= %(deploy)s::timestamptz
                  THEN lifetime_min END
  )::float8 AS post_p50
FROM grid_lifecycles
"""
    try:
        cur.execute(sql, {"deploy": DEPLOY_UTC})
        row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return MetricResult(
            name="[38] grid_lifecycle_drift",
            baseline="n/a", current="n/a", delta="n/a", delta_pct="n/a",
            verdict="WARN",
            note=f"query failed: {type(exc).__name__}: {exc}",
        )

    if not row:
        return MetricResult(
            name="[38] grid_lifecycle_drift",
            baseline="n/a", current="n/a", delta="n/a", delta_pct="n/a",
            verdict="WARN", note="no rows",
        )

    prior_n, prior_p50, post_n, post_p50 = row
    prior_n = int(prior_n or 0)
    post_n = int(post_n or 0)

    if prior_n < 5 or post_n < 5:
        return MetricResult(
            name="[38] grid_lifecycle_drift",
            baseline=f"n={prior_n}",
            current=f"n={post_n}",
            delta="n/a", delta_pct="n/a",
            verdict="WARN",
            note=f"sample too small (prior={prior_n}, post={post_n}; need ≥5 each)",
        )

    prior_p50 = float(prior_p50 or 0.0)
    post_p50 = float(post_p50 or 0.0)

    # 方向判斷：lifetime 顯著縮短 (>30%) = WARN；>50% = FAIL
    # Direction: lifetime materially shorter (>30%) = WARN; >50% = FAIL
    if prior_p50 <= 0:
        verdict = "WARN"
        note = "prior_p50 is 0 — cannot compute direction"
    else:
        ratio = post_p50 / prior_p50
        if ratio < 0.50:
            verdict = "FAIL"
            note = (
                f"lifetime shortened {(1 - ratio) * 100:.1f}% "
                f"(>50% — grid edge likely killed by dyn floor)"
            )
        elif ratio < 0.70:
            verdict = "WARN"
            note = (
                f"lifetime shortened {(1 - ratio) * 100:.1f}% "
                f"(30-50% — review grid params)"
            )
        else:
            verdict = "PASS"
            note = f"lifetime stable (ratio={ratio:.2f})"

    return MetricResult(
        name="[38] grid_lifecycle_drift",
        baseline=f"n={prior_n}, p50={prior_p50:.2f}min",
        current=f"n={post_n}, p50={post_p50:.2f}min",
        delta=_fmt_delta(post_p50, prior_p50, "min"),
        delta_pct=_fmt_pct(post_p50 - prior_p50, prior_p50),
        verdict=verdict,
        note=note,
    )


# ── Metric 5 — demo gross PnL delta (post 7d vs prior 7d) ───────────────────────


def metric_demo_gross_pnl_delta(cur) -> MetricResult:
    """Metric 5: demo gross realized_pnl SUM, post 7d vs prior 7d.

    SL 收緊不應淨虧損；post < prior 顯著（< -20%）= 需 PA review。
    SL tightening should not net-lose; post < prior materially (< -20%)
    = PA review needed.
    """
    try:
        cur.connection.rollback()
    except Exception:
        pass

    sql = """
SELECT
  COALESCE(SUM(realized_pnl) FILTER (
    WHERE ts >= %(deploy)s::timestamptz - interval '7 days'
      AND ts <  %(deploy)s::timestamptz
  ), 0)::float8 AS prior_pnl,
  COUNT(*) FILTER (
    WHERE ts >= %(deploy)s::timestamptz - interval '7 days'
      AND ts <  %(deploy)s::timestamptz
  )::int AS prior_n,
  COALESCE(SUM(realized_pnl) FILTER (
    WHERE ts >= %(deploy)s::timestamptz
      AND ts <  %(deploy)s::timestamptz + interval '7 days'
  ), 0)::float8 AS post_pnl,
  COUNT(*) FILTER (
    WHERE ts >= %(deploy)s::timestamptz
      AND ts <  %(deploy)s::timestamptz + interval '7 days'
  )::int AS post_n
FROM trading.fills
WHERE engine_mode = 'demo'
  AND realized_pnl IS NOT NULL
"""
    try:
        cur.execute(sql, {"deploy": DEPLOY_UTC})
        row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return MetricResult(
            name="demo_gross_pnl_delta",
            baseline="n/a", current="n/a", delta="n/a", delta_pct="n/a",
            verdict="WARN",
            note=f"query failed: {type(exc).__name__}: {exc}",
        )

    if not row:
        return MetricResult(
            name="demo_gross_pnl_delta",
            baseline="n/a", current="n/a", delta="n/a", delta_pct="n/a",
            verdict="WARN", note="no rows",
        )

    prior_pnl, prior_n, post_pnl, post_n = row
    prior_pnl = float(prior_pnl or 0.0)
    post_pnl = float(post_pnl or 0.0)
    prior_n = int(prior_n or 0)
    post_n = int(post_n or 0)

    if prior_n < 5 or post_n < 5:
        return MetricResult(
            name="demo_gross_pnl_delta",
            baseline=f"n={prior_n}",
            current=f"n={post_n}",
            delta="n/a", delta_pct="n/a",
            verdict="WARN",
            note=f"sample too small (prior={prior_n}, post={post_n})",
        )

    delta = post_pnl - prior_pnl
    # 方向判斷：post 不應顯著低於 prior (容差 -20%)
    # Direction: post should not be materially worse than prior (-20% tolerance)
    if abs(prior_pnl) < 1e-6:
        verdict = "WARN"
        note = "prior_pnl is ~0 — cannot compute % direction"
    else:
        # 用相對於 prior abs 的 ratio 判斷（避開 prior 為負時除號反轉）
        # Use ratio against abs(prior) to avoid sign-flip when prior is negative
        ratio = delta / abs(prior_pnl)
        if ratio < -0.20:
            verdict = "FAIL"
            note = f"post worse by {ratio * 100:+.1f}% (>20% deterioration)"
        elif ratio < 0.0:
            verdict = "WARN"
            note = f"post slightly worse {ratio * 100:+.1f}% (within tolerance)"
        else:
            verdict = "PASS"
            note = f"post stable or better ({ratio * 100:+.1f}%)"

    return MetricResult(
        name="demo_gross_pnl_delta",
        baseline=f"n={prior_n}, sum={prior_pnl:+.2f} USD",
        current=f"n={post_n}, sum={post_pnl:+.2f} USD",
        delta=_fmt_delta(post_pnl, prior_pnl, " USD"),
        delta_pct=_fmt_pct(delta, abs(prior_pnl) if prior_pnl else None),
        verdict=verdict,
        note=note,
    )


# ── Render + main ───────────────────────────────────────────────────────────────


def render_markdown(results: list[MetricResult]) -> str:
    """Render results as 5-row Markdown table + overall verdict line.

    輸出 5 行 Markdown table + 整體 verdict 行。
    """
    lines: list[str] = []
    lines.append("# 2026-05-09 · 3C deploy 7d follow-up audit")
    lines.append("")
    lines.append(f"- **Deploy timestamp (UTC)**: `{DEPLOY_UTC}`")
    lines.append(
        f"- **Baseline window**: `[deploy - {PRIOR_WINDOW_DAYS}d, deploy)`  "
        f"· **Post window**: `[deploy, deploy + {POST_WINDOW_DAYS}d)`"
    )
    lines.append("- **Engine mode**: `demo` (and `live_demo` for [40]/[38])")
    lines.append("")
    lines.append("| # | Metric | Baseline | Current | Δ | Δ% | Verdict | Note |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for idx, r in enumerate(results, 1):
        lines.append(
            f"| {idx} | {r.name} | {r.baseline} | {r.current} | "
            f"{r.delta} | {r.delta_pct} | **{r.verdict}** | {r.note} |"
        )

    # Overall verdict
    has_fail = any(r.verdict == "FAIL" for r in results)
    has_warn = any(r.verdict == "WARN" for r in results)
    if has_fail:
        verdict = "**FAIL** — at least one metric moved against expectation; PA review required."
    elif has_warn:
        verdict = "**WARN** — review WARN rows; not blocking continued passive observation."
    else:
        verdict = "**PASS** — all 5 metrics moved in expected direction; PA review optional."
    lines.append("")
    lines.append(f"**Overall verdict**: {verdict}")
    return "\n".join(lines)


def render_quiet(results: list[MetricResult]) -> str:
    """Quiet mode: only print non-PASS metrics + overall verdict."""
    non_pass = [r for r in results if r.verdict != "PASS"]
    if not non_pass:
        return "PASS — all 5 metrics moved in expected direction."
    lines = ["# Non-PASS metrics:"]
    for r in non_pass:
        lines.append(f"- **{r.verdict}** {r.name}: {r.note}")
    return "\n".join(lines)


def main() -> int:
    """Entry point — run 5 metrics, print Markdown, return exit code.

    Exit code contract:
      0 = all PASS (or only WARN)
      1 = ≥1 FAIL
      2 = DB connection error
    """
    parser = argparse.ArgumentParser(
        description="2026-05-09 3C deploy 7d follow-up audit "
        "(prior vs post comparison; read-only; no DB write)"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="只印非 PASS metric / Only print non-PASS metrics",
    )
    args = parser.parse_args()

    try:
        conn = _get_conn()
    except Exception as exc:  # noqa: BLE001
        print(f"[FATAL] DB connect failed: {exc}", file=sys.stderr)
        return 2

    try:
        with conn.cursor() as cur:
            results: list[MetricResult] = [
                metric_realized_edge_acceptance(cur),
                metric_dyn_stop_fire_count_by_strategy(cur),
                metric_funding_arb_hard_stop_validation(cur),
                metric_grid_lifecycle_drift(cur),
                metric_demo_gross_pnl_delta(cur),
            ]
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if args.quiet:
        print(render_quiet(results))
    else:
        print(render_markdown(results))

    has_fail = any(r.verdict == "FAIL" for r in results)
    return 1 if has_fail else 0


if __name__ == "__main__":
    sys.exit(main())
