"""Pre-live edge gate trend reader.
Pre-live 邊際 gate 趨勢讀取器。

This module mirrors the read-only parts of passive healthchecks [33], [38],
and [40] so the Live dashboard can show trend context without touching runtime
state, strategy params, or execution controls.
本模組鏡像 passive healthcheck [33]/[38]/[40] 的只讀查詢，讓 Live dashboard
可顯示趨勢脈絡；不修改 runtime、策略參數或交易控制。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .db_pool import get_pg_conn

logger = logging.getLogger(__name__)


MAKER_FEE_RATE = 0.00020
TAKER_FEE_RATE = 0.00055
MAKER_FEE_CUTOFF = (MAKER_FEE_RATE + TAKER_FEE_RATE) / 2.0
MAKER_FEE_DROP_TARGET_PCT = 60.0
MAKER_FILL_MIN_SAMPLE = 30

GRID_LIFETIME_RATIO_WARN = 0.5
GRID_LIFETIME_RATIO_FAIL = 0.3
GRID_FEE_BURN_ABS_WARN = 0.8
GRID_FEE_BURN_ABS_FAIL = 1.5
GRID_FEE_BURN_RATIO_WARN = 2.0
GRID_REENTRY_RATE_WARN = 0.5
GRID_REENTRY_RATE_FAIL = 0.7
GRID_REENTRY_DELTA_WARN = 0.3
GRID_LIFECYCLE_MIN_SAMPLE = 5
GRID_COHORT_MIN_COMMON_SYMBOLS = 2

EDGE_ACCEPTANCE_MIN_SAMPLE = 30
EDGE_ACCEPTANCE_MIN_AVG_NET_BPS = 5.0
EDGE_ACCEPTANCE_BAD_CELL_MIN_N = 10
EDGE_ACCEPTANCE_BAD_CELL_MAX_AVG_BPS = -10.0
EDGE_ACCEPTANCE_MAKER_MIN_PCT = 50.0

GATE_LABELS: dict[str, tuple[str, str]] = {
    "33": ("maker_fill_rate", "PostOnly maker fill / fee-drop"),
    "38": ("grid_trading_lifecycle_drift", "Grid lifecycle drift"),
    "40": ("realized_edge_acceptance", "Realized edge acceptance"),
}
ACTIVE_STRATEGIES: tuple[str, ...] = (
    "grid_trading",
    "ma_crossover",
    "funding_arb",
    "bb_breakout",
    "bb_reversion",
)

STRATEGY_ENTRY_FILL_PREDICATE = """
      AND (f.entry_context_id IS NULL OR f.entry_context_id = '')
      AND f.exit_reason IS NULL
      AND f.order_id NOT LIKE 'oc_risk_%%'
"""


def _strategy_entry_fill_predicate() -> str:
    """SQL predicate for strategy-owned entry fills only. 僅篩 strategy entry fill。"""
    return STRATEGY_ENTRY_FILL_PREDICATE


def _as_int(value: Any, default: int = 0) -> int:
    """Coerce DB scalar to int. 將 DB scalar 轉為 int。"""
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    """Coerce DB scalar to float. 將 DB scalar 轉為 float。"""
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _round_or_none(value: Any, digits: int = 2) -> float | None:
    """Round finite values and preserve missing values. 四捨五入有限值，缺值保留 None。"""
    try:
        if value is None:
            return None
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _pct(numerator: float, denominator: float) -> float:
    """Return percentage, guarding zero denominators. 回傳百分比並防止除以零。"""
    if denominator <= 0:
        return 0.0
    return numerator / denominator * 100.0


def _fee_drop_pct(avg_fee_rate: float) -> float:
    """Compute taker-to-maker fee-drop percentage. 計算 taker 到 maker 的降費百分比。"""
    denom = TAKER_FEE_RATE - MAKER_FEE_RATE
    if denom <= 0:
        return 0.0
    return max(0.0, min(100.0, (TAKER_FEE_RATE - avg_fee_rate) / denom * 100.0))


def _rollback_cursor(cur: Any) -> None:
    """Reset transaction state after a failed read. 讀取失敗後重置 transaction 狀態。"""
    try:
        cur.connection.rollback()
    except Exception:
        pass


def _gate_template(gate_id: str, *, available: bool = True) -> dict[str, Any]:
    """Create a stable gate payload shell. 建立穩定 gate payload 外殼。"""
    key, label = GATE_LABELS[gate_id]
    return {
        "gate_id": gate_id,
        "key": key,
        "label": label,
        "available": available,
        "status": "unknown",
        "summary": "",
        "target": {},
        "current": {},
        "series": [],
        "diagnostics": [],
    }


def _status_from_level(level: str) -> str:
    """Normalize healthcheck levels for GUI chips. 正規化 healthcheck 狀態供 GUI 標籤使用。"""
    lowered = str(level or "").lower()
    if lowered in {"pass", "warn", "fail"}:
        return lowered
    return "unknown"


def _fetch_maker_fill_gate(cur: Any, window_days: int) -> dict[str, Any]:
    """Fetch [33] maker quality daily trend and rolling current value.
    讀取 [33] maker 品質每日趨勢與 rolling 現值。
    """
    gate = _gate_template("33")
    span_days = max(0, window_days - 1)
    _rollback_cursor(cur)

    day_sql = """
WITH days AS (
  SELECT generate_series(
    date_trunc('day', now()) - (%s::int * interval '1 day'),
    date_trunc('day', now()),
    interval '1 day'
  ) AS bucket_day
),
entry_fills AS (
  SELECT
    date_trunc('day', f.ts) AS bucket_day,
    lower(coalesce(f.liquidity_role, '')) AS liquidity_role,
    lower(coalesce(o.order_type, '')) AS order_type,
    lower(coalesce(o.time_in_force, '')) AS time_in_force,
    coalesce(nullif(f.fee_rate, 0), %s)::float8 AS effective_fee_rate,
    CASE
      WHEN lower(coalesce(f.liquidity_role, '')) = 'maker'
        OR coalesce(nullif(f.fee_rate, 0), %s) <= %s
      THEN 1 ELSE 0
    END AS maker_like
  FROM trading.fills f
  LEFT JOIN trading.orders o
    ON o.order_id = f.order_id
   AND o.ts >= date_trunc('day', now()) - ((%s::int + 1) * interval '1 day')
  WHERE f.ts >= date_trunc('day', now()) - (%s::int * interval '1 day')
    AND f.engine_mode IN ('demo', 'live_demo')
    AND coalesce(f.strategy_name, '') <> ''
    AND f.strategy_name NOT LIKE 'risk_close:%%'
    AND f.strategy_name NOT LIKE 'strategy_close:%%'
    AND f.strategy_name NOT LIKE 'ipc_close%%'
    AND f.strategy_name NOT LIKE 'unattributed:%%'
    AND coalesce(f.exit_source, '') = ''
""" + _strategy_entry_fill_predicate() + """
)
SELECT
  to_char(d.bucket_day, 'YYYY-MM-DD') AS bucket_day,
  count(ef.effective_fee_rate)::int AS total_fills,
  coalesce(sum(ef.maker_like), 0)::int AS maker_like_fills,
  avg(ef.effective_fee_rate)::float8 AS avg_fee_rate,
  count(*) FILTER (WHERE ef.order_type = 'limit')::int AS limit_order_fills,
  count(*) FILTER (WHERE ef.time_in_force = 'postonly')::int AS postonly_order_fills
FROM days d
LEFT JOIN entry_fills ef ON ef.bucket_day = d.bucket_day
GROUP BY d.bucket_day
ORDER BY d.bucket_day
"""
    current_sql = """
WITH entry_fills AS (
  SELECT
    lower(coalesce(f.liquidity_role, '')) AS liquidity_role,
    lower(coalesce(o.order_type, '')) AS order_type,
    lower(coalesce(o.time_in_force, '')) AS time_in_force,
    coalesce(nullif(f.fee_rate, 0), %s)::float8 AS effective_fee_rate,
    CASE
      WHEN lower(coalesce(f.liquidity_role, '')) = 'maker'
        OR coalesce(nullif(f.fee_rate, 0), %s) <= %s
      THEN 1 ELSE 0
    END AS maker_like
  FROM trading.fills f
  LEFT JOIN trading.orders o
    ON o.order_id = f.order_id
   AND o.ts > now() - ((%s::int + 1) * interval '1 day')
  WHERE f.ts > now() - (%s::int * interval '1 day')
    AND f.engine_mode IN ('demo', 'live_demo')
    AND coalesce(f.strategy_name, '') <> ''
    AND f.strategy_name NOT LIKE 'risk_close:%%'
    AND f.strategy_name NOT LIKE 'strategy_close:%%'
    AND f.strategy_name NOT LIKE 'ipc_close%%'
    AND f.strategy_name NOT LIKE 'unattributed:%%'
    AND coalesce(f.exit_source, '') = ''
""" + _strategy_entry_fill_predicate() + """
)
SELECT
  count(*)::int AS total_fills,
  coalesce(sum(maker_like), 0)::int AS maker_like_fills,
  avg(effective_fee_rate)::float8 AS avg_fee_rate,
  count(*) FILTER (WHERE order_type = 'limit')::int AS limit_order_fills,
  count(*) FILTER (WHERE time_in_force = 'postonly')::int AS postonly_order_fills
FROM entry_fills
"""
    try:
        cur.execute(
            day_sql,
            (
                span_days,
                TAKER_FEE_RATE,
                TAKER_FEE_RATE,
                MAKER_FEE_CUTOFF,
                span_days,
                span_days,
            ),
        )
        day_rows = cur.fetchall() or []
        cur.execute(
            current_sql,
            (
                TAKER_FEE_RATE,
                TAKER_FEE_RATE,
                MAKER_FEE_CUTOFF,
                window_days,
                window_days,
            ),
        )
        current_row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        _rollback_cursor(cur)
        gate.update(
            {
                "available": False,
                "status": "unknown",
                "summary": f"maker fill trend query failed: {type(exc).__name__}: {exc}",
                "diagnostics": [str(exc)],
            }
        )
        return gate

    series: list[dict[str, Any]] = []
    for row in day_rows:
        total = _as_int(row[1])
        maker_like = _as_int(row[2])
        avg_fee_rate = _as_float(row[3], TAKER_FEE_RATE)
        limit_rows = _as_int(row[4])
        postonly_rows = _as_int(row[5])
        series.append(
            {
                "bucket_day": row[0],
                "entry_fills": total,
                "maker_like_pct": round(_pct(maker_like, total), 1),
                "fee_drop_pct": round(_fee_drop_pct(avg_fee_rate), 1),
                "avg_fee_bps": round(avg_fee_rate * 10_000, 2),
                "limit_pct": round(_pct(limit_rows, total), 1),
                "postonly_pct": round(_pct(postonly_rows, total), 1),
            }
        )

    total = _as_int(current_row[0] if current_row else 0)
    maker_like = _as_int(current_row[1] if current_row else 0)
    avg_fee_rate = _as_float(current_row[2] if current_row else None, TAKER_FEE_RATE)
    limit_rows = _as_int(current_row[3] if current_row else 0)
    postonly_rows = _as_int(current_row[4] if current_row else 0)
    maker_pct = _pct(maker_like, total)
    fee_drop = _fee_drop_pct(avg_fee_rate)
    if total == 0:
        status = "pass"
        summary = f"{window_days}d demo/live_demo entry_fills=0; no maker-fill sample yet"
    elif total < MAKER_FILL_MIN_SAMPLE:
        status = "warn"
        summary = f"{window_days}d entry_fills={total} below sample target {MAKER_FILL_MIN_SAMPLE}"
    elif fee_drop >= MAKER_FEE_DROP_TARGET_PCT:
        status = "pass"
        summary = f"{window_days}d fee_drop={fee_drop:.1f}% meets PostOnly target"
    else:
        status = "warn"
        summary = f"{window_days}d fee_drop={fee_drop:.1f}% below PostOnly target"

    gate.update(
        {
            "status": status,
            "summary": summary,
            "target": {
                "fee_drop_pct_min": MAKER_FEE_DROP_TARGET_PCT,
                "min_entry_fills": MAKER_FILL_MIN_SAMPLE,
            },
            "current": {
                "window_days": window_days,
                "entry_fills": total,
                "maker_like_fills": maker_like,
                "maker_like_pct": round(maker_pct, 1),
                "avg_fee_bps": round(avg_fee_rate * 10_000, 2),
                "fee_drop_pct": round(fee_drop, 1),
                "limit_order_fills": limit_rows,
                "limit_pct": round(_pct(limit_rows, total), 1),
                "postonly_order_fills": postonly_rows,
                "postonly_pct": round(_pct(postonly_rows, total), 1),
            },
            "series": series,
        }
    )
    return gate


def _fetch_grid_lifecycle_gate(cur: Any, window_days: int) -> dict[str, Any]:
    """Fetch [38] grid lifecycle trend and current drift summary.
    讀取 [38] grid lifecycle 趨勢與當前 drift 摘要。
    """
    gate = _gate_template("38")
    span_days = max(0, window_days - 1)
    _rollback_cursor(cur)
    day_sql = """
WITH days AS (
  SELECT generate_series(
    date_trunc('day', now()) - (%s::int * interval '1 day'),
    date_trunc('day', now()),
    interval '1 day'
  ) AS bucket_day
),
entries AS (
  SELECT f.engine_mode, f.symbol, f.side,
         f.context_id AS entry_cid,
         date_trunc('day', f.ts) AS bucket_day,
         f.ts AS entry_ts,
         f.fee AS entry_fee
  FROM trading.fills f
  WHERE f.ts >= date_trunc('day', now()) - (%s::int * interval '1 day')
    AND f.engine_mode IN ('demo', 'live_demo')
    AND f.strategy_name = 'grid_trading'
""" + _strategy_entry_fill_predicate() + """
),
closes AS (
  SELECT f.entry_context_id AS entry_cid,
         f.ts AS exit_ts,
         f.fee AS exit_fee,
         f.realized_pnl AS realized_pnl,
         row_number() OVER (PARTITION BY f.entry_context_id ORDER BY f.ts) AS rn
  FROM trading.fills f
  WHERE f.ts >= date_trunc('day', now()) - (%s::int * interval '1 day')
    AND f.engine_mode IN ('demo', 'live_demo')
    AND f.entry_context_id IS NOT NULL
    AND f.entry_context_id <> ''
    AND (f.strategy_name LIKE 'strategy_close:grid_close%%'
         OR f.strategy_name LIKE 'risk_close:%%'
         OR f.exit_reason IS NOT NULL)
),
first_close AS (SELECT * FROM closes WHERE rn = 1),
lifecycles AS (
  SELECT e.bucket_day, e.engine_mode, e.symbol, e.side,
         EXTRACT(EPOCH FROM (c.exit_ts - e.entry_ts))/60.0 AS lifetime_min,
         (e.entry_fee + c.exit_fee) AS total_fee_usd,
         c.realized_pnl
  FROM entries e
  JOIN first_close c ON c.entry_cid = e.entry_cid
)
SELECT
  to_char(d.bucket_day, 'YYYY-MM-DD') AS bucket_day,
  count(*) FILTER (WHERE l.engine_mode = 'demo')::int AS demo_n,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY l.lifetime_min)
    FILTER (WHERE l.engine_mode = 'demo')::float8 AS demo_p50_min,
  count(*) FILTER (WHERE l.engine_mode = 'live_demo')::int AS live_demo_n,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY l.lifetime_min)
    FILTER (WHERE l.engine_mode = 'live_demo')::float8 AS live_demo_p50_min
FROM days d
LEFT JOIN lifecycles l ON l.bucket_day = d.bucket_day
GROUP BY d.bucket_day
ORDER BY d.bucket_day
"""
    current_lifecycle_cte = """
WITH entries AS (
  SELECT f.engine_mode, f.symbol, f.side,
         f.context_id AS entry_cid,
         f.ts AS entry_ts,
         f.fee AS entry_fee
  FROM trading.fills f
  WHERE f.ts > now() - interval '24 hours'
    AND f.engine_mode IN ('demo', 'live_demo')
    AND f.strategy_name = 'grid_trading'
""" + _strategy_entry_fill_predicate() + """
),
closes AS (
  SELECT f.entry_context_id AS entry_cid,
         f.ts AS exit_ts,
         f.fee AS exit_fee,
         f.realized_pnl AS realized_pnl,
         row_number() OVER (PARTITION BY f.entry_context_id ORDER BY f.ts) AS rn
  FROM trading.fills f
  WHERE f.ts > now() - interval '24 hours'
    AND f.engine_mode IN ('demo', 'live_demo')
    AND f.entry_context_id IS NOT NULL
    AND f.entry_context_id <> ''
    AND (f.strategy_name LIKE 'strategy_close:grid_close%%'
         OR f.strategy_name LIKE 'risk_close:%%'
         OR f.exit_reason IS NOT NULL)
),
first_close AS (SELECT * FROM closes WHERE rn = 1),
lifecycles AS (
  SELECT e.engine_mode, e.symbol, e.side,
         EXTRACT(EPOCH FROM (c.exit_ts - e.entry_ts))/60.0 AS lifetime_min,
         (e.entry_fee + c.exit_fee) AS total_fee_usd,
         c.realized_pnl
  FROM entries e
  JOIN first_close c ON c.entry_cid = e.entry_cid
)
"""
    current_sql = current_lifecycle_cte + """
SELECT engine_mode,
       count(*)::int AS n,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY lifetime_min)::float8 AS p50_min,
       avg(lifetime_min)::float8 AS avg_min,
       sum(total_fee_usd)::float8 AS sum_fee,
       sum(abs(coalesce(realized_pnl,0)))::float8 AS sum_abs_pnl
FROM lifecycles
GROUP BY engine_mode
ORDER BY engine_mode
"""
    cohort_sql = current_lifecycle_cte + """
, by_cohort AS (
  SELECT engine_mode, symbol, side,
         count(*)::int AS n,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY lifetime_min)::float8 AS p50_min
  FROM lifecycles
  GROUP BY engine_mode, symbol, side
),
common_cohorts AS (
  SELECT d.symbol, d.side,
         d.n AS demo_n,
         l.n AS live_demo_n,
         d.p50_min AS demo_p50_min,
         l.p50_min AS live_demo_p50_min,
         l.p50_min / NULLIF(d.p50_min, 0)::float8 AS lifetime_ratio
  FROM by_cohort d
  JOIN by_cohort l
    ON l.symbol = d.symbol
   AND l.side = d.side
   AND l.engine_mode = 'live_demo'
  WHERE d.engine_mode = 'demo'
    AND d.p50_min > 0
)
SELECT count(*)::int AS common_cohorts,
       coalesce(sum(demo_n), 0)::int AS demo_common_n,
       coalesce(sum(live_demo_n), 0)::int AS live_common_n,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY lifetime_ratio)::float8 AS median_ratio,
       sum(live_demo_n * lifetime_ratio)::float8
         / NULLIF(sum(live_demo_n), 0)::float8 AS live_weighted_ratio
FROM common_cohorts
"""
    reentry_sql = """
WITH entries_with_lag AS (
  SELECT f.engine_mode, f.symbol, f.side, f.ts AS entry_ts,
         LAG(f.ts) OVER (PARTITION BY f.engine_mode, f.symbol, f.side ORDER BY f.ts) AS prev_ts
  FROM trading.fills f
  WHERE f.ts > now() - interval '24 hours'
    AND f.engine_mode IN ('demo', 'live_demo')
    AND f.strategy_name = 'grid_trading'
    AND coalesce(f.exit_source, '') = ''
""" + _strategy_entry_fill_predicate() + """
)
SELECT engine_mode,
       count(*)::int AS total_entries,
       count(*) FILTER (
           WHERE prev_ts IS NOT NULL
             AND entry_ts - prev_ts < interval '1 hour')::int AS re_entries,
       (count(*) FILTER (
           WHERE prev_ts IS NOT NULL
             AND entry_ts - prev_ts < interval '1 hour'))::float8
         / NULLIF(count(*), 0)::float8 AS re_entry_rate
FROM entries_with_lag
GROUP BY engine_mode
ORDER BY engine_mode
"""
    try:
        cur.execute(day_sql, (span_days, span_days, span_days))
        day_rows = cur.fetchall() or []
        cur.execute(current_sql)
        current_rows = cur.fetchall() or []
        cur.execute(cohort_sql)
        cohort_row = cur.fetchone()
        cur.execute(reentry_sql)
        re_rows = cur.fetchall() or []
    except Exception as exc:  # noqa: BLE001
        _rollback_cursor(cur)
        gate.update(
            {
                "available": False,
                "status": "unknown",
                "summary": f"grid lifecycle trend query failed: {type(exc).__name__}: {exc}",
                "diagnostics": [str(exc)],
            }
        )
        return gate

    series: list[dict[str, Any]] = []
    for row in day_rows:
        demo_n = _as_int(row[1])
        demo_p50 = _round_or_none(row[2], 2)
        live_n = _as_int(row[3])
        live_p50 = _round_or_none(row[4], 2)
        lifetime_ratio = None
        if demo_p50 and live_p50 is not None:
            lifetime_ratio = round(live_p50 / demo_p50, 2)
        series.append(
            {
                "bucket_day": row[0],
                "demo_n": demo_n,
                "demo_p50_min": demo_p50,
                "live_demo_n": live_n,
                "live_demo_p50_min": live_p50,
                "lifetime_ratio": lifetime_ratio,
            }
        )

    stats: dict[str, dict[str, float]] = {}
    for row in current_rows:
        mode = str(row[0] or "")
        stats[mode] = {
            "n": float(_as_int(row[1])),
            "p50_min": _as_float(row[2], 0.0),
            "avg_min": _as_float(row[3], 0.0),
            "sum_fee": _as_float(row[4], 0.0),
            "sum_abs_pnl": _as_float(row[5], 0.0),
        }
    re_stats: dict[str, dict[str, float]] = {}
    for row in re_rows:
        mode = str(row[0] or "")
        re_stats[mode] = {
            "total": float(_as_int(row[1])),
            "re": float(_as_int(row[2])),
            "rate": _as_float(row[3], 0.0),
        }

    demo = stats.get("demo")
    live_demo = stats.get("live_demo")
    re_demo = re_stats.get("demo", {"rate": 0.0, "total": 0.0, "re": 0.0})
    re_live = re_stats.get("live_demo", {"rate": 0.0, "total": 0.0, "re": 0.0})
    global_lifetime_ratio = None
    cohort_common = _as_int(cohort_row[0] if cohort_row else 0)
    demo_common_n = _as_int(cohort_row[1] if cohort_row else 0)
    live_common_n = _as_int(cohort_row[2] if cohort_row else 0)
    cohort_lifetime_ratio = (
        _as_float(cohort_row[3], 0.0) if cohort_row and cohort_row[3] is not None else None
    )
    cohort_weighted_ratio = (
        _as_float(cohort_row[4], 0.0) if cohort_row and cohort_row[4] is not None else None
    )
    cohort_comparable = (
        cohort_common >= GRID_COHORT_MIN_COMMON_SYMBOLS
        and demo_common_n >= GRID_LIFECYCLE_MIN_SAMPLE
        and live_common_n >= GRID_LIFECYCLE_MIN_SAMPLE
    )
    lifetime_ratio = cohort_lifetime_ratio if cohort_comparable else None
    fee_burn_demo = None
    fee_burn_live = None
    fee_burn_ratio = None
    if demo and live_demo and demo["p50_min"] > 0:
        global_lifetime_ratio = live_demo["p50_min"] / demo["p50_min"]
    if demo and demo["sum_abs_pnl"] > 0:
        fee_burn_demo = demo["sum_fee"] / demo["sum_abs_pnl"]
    if live_demo and live_demo["sum_abs_pnl"] > 0:
        fee_burn_live = live_demo["sum_fee"] / live_demo["sum_abs_pnl"]
    if fee_burn_demo and fee_burn_demo > 0 and fee_burn_live is not None:
        fee_burn_ratio = fee_burn_live / fee_burn_demo

    severities: list[tuple[str, str]] = []
    if lifetime_ratio is not None:
        if lifetime_ratio < GRID_LIFETIME_RATIO_FAIL:
            severities.append(("fail", f"cohort_lifetime_ratio={lifetime_ratio:.2f}"))
        elif lifetime_ratio < GRID_LIFETIME_RATIO_WARN:
            severities.append(("warn", f"cohort_lifetime_ratio={lifetime_ratio:.2f}"))
    elif global_lifetime_ratio is not None and global_lifetime_ratio < GRID_LIFETIME_RATIO_WARN:
        severities.append(
            (
                "warn",
                "cohort sample insufficient "
                f"(common={cohort_common}, demo_common_n={demo_common_n}, "
                f"live_common_n={live_common_n}, global_ratio={global_lifetime_ratio:.2f})",
            )
        )
    if fee_burn_live is not None:
        if fee_burn_live > GRID_FEE_BURN_ABS_FAIL:
            severities.append(("fail", f"live fee_burn={fee_burn_live:.2f}"))
        elif fee_burn_live > GRID_FEE_BURN_ABS_WARN:
            severities.append(("warn", f"live fee_burn={fee_burn_live:.2f}"))
    if fee_burn_ratio is not None and fee_burn_ratio > GRID_FEE_BURN_RATIO_WARN:
        severities.append(("warn", f"fee_burn_ratio={fee_burn_ratio:.2f}"))
    if re_live["rate"] > GRID_REENTRY_RATE_FAIL:
        severities.append(("fail", f"live re_entry_rate={re_live['rate']:.2f}"))
    elif re_live["rate"] > GRID_REENTRY_RATE_WARN:
        severities.append(("warn", f"live re_entry_rate={re_live['rate']:.2f}"))
    re_delta = re_live["rate"] - re_demo["rate"]
    if re_delta > GRID_REENTRY_DELTA_WARN:
        severities.append(("warn", f"re_entry_delta={re_delta:.2f}"))

    if not demo or demo["n"] < GRID_LIFECYCLE_MIN_SAMPLE:
        status = "warn"
        summary = f"24h demo lifecycles n={int(demo['n']) if demo else 0}; insufficient baseline"
    elif not live_demo or live_demo["n"] < GRID_LIFECYCLE_MIN_SAMPLE:
        status = "warn"
        summary = f"24h live_demo lifecycles n={int(live_demo['n']) if live_demo else 0}; insufficient live sample"
    elif any(level == "fail" for level, _ in severities):
        status = "fail"
        summary = "24h grid lifecycle fail: " + "; ".join(reason for level, reason in severities if level == "fail")
    elif any(level == "warn" for level, _ in severities):
        status = "warn"
        summary = "24h grid lifecycle warn: " + "; ".join(reason for level, reason in severities if level == "warn")
    else:
        status = "pass"
        summary = "24h grid lifecycle within drift thresholds"

    gate.update(
        {
            "status": status,
            "summary": summary,
            "target": {
                "min_lifecycle_sample_per_mode": GRID_LIFECYCLE_MIN_SAMPLE,
                "lifetime_ratio_warn_min": GRID_LIFETIME_RATIO_WARN,
                "lifetime_ratio_fail_min": GRID_LIFETIME_RATIO_FAIL,
                "min_common_cohorts": GRID_COHORT_MIN_COMMON_SYMBOLS,
                "live_reentry_rate_warn_max": GRID_REENTRY_RATE_WARN,
                "live_reentry_rate_fail_max": GRID_REENTRY_RATE_FAIL,
            },
            "current": {
                "window_hours": 24,
                "demo_n": int(demo["n"]) if demo else 0,
                "demo_p50_min": _round_or_none(demo["p50_min"] if demo else None, 2),
                "live_demo_n": int(live_demo["n"]) if live_demo else 0,
                "live_demo_p50_min": _round_or_none(live_demo["p50_min"] if live_demo else None, 2),
                "lifetime_ratio": _round_or_none(lifetime_ratio, 2),
                "global_lifetime_ratio": _round_or_none(global_lifetime_ratio, 2),
                "cohort_common": cohort_common,
                "demo_common_n": demo_common_n,
                "live_common_n": live_common_n,
                "cohort_lifetime_ratio": _round_or_none(cohort_lifetime_ratio, 2),
                "cohort_weighted_lifetime_ratio": _round_or_none(cohort_weighted_ratio, 2),
                "demo_reentry_rate": _round_or_none(re_demo["rate"], 2),
                "live_demo_reentry_rate": _round_or_none(re_live["rate"], 2),
                "reentry_delta": _round_or_none(re_delta, 2),
                "demo_fee_burn": _round_or_none(fee_burn_demo, 2),
                "live_demo_fee_burn": _round_or_none(fee_burn_live, 2),
                "fee_burn_ratio": _round_or_none(fee_burn_ratio, 2),
            },
            "series": series,
        }
    )
    return gate


def _fetch_realized_edge_gate(
    cur: Any,
    window_days: int,
    maker_gate: dict[str, Any],
) -> dict[str, Any]:
    """Fetch [40] realized post-fee edge trend.
    讀取 [40] 扣費後 realized edge 趨勢。
    """
    gate = _gate_template("40")
    span_days = max(0, window_days - 1)
    _rollback_cursor(cur)
    try:
        cur.execute("SELECT to_regclass('learning.mlde_edge_training_rows') IS NOT NULL")
        exists = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        _rollback_cursor(cur)
        gate.update(
            {
                "available": False,
                "status": "unknown",
                "summary": f"edge training view existence check failed: {exc}",
                "diagnostics": [str(exc)],
            }
        )
        return gate
    if not exists or not exists[0]:
        gate.update(
            {
                "available": False,
                "status": "unknown",
                "summary": "learning.mlde_edge_training_rows missing; cannot trend realized edge",
            }
        )
        return gate

    day_sql = """
WITH days AS (
  SELECT generate_series(
    date_trunc('day', now()) - (%s::int * interval '1 day'),
    date_trunc('day', now()),
    interval '1 day'
  ) AS bucket_day
),
edge_rows AS (
  SELECT date_trunc('day', ts) AS bucket_day, net_bps_after_fee
  FROM learning.mlde_edge_training_rows
  WHERE ts >= date_trunc('day', now()) - (%s::int * interval '1 day')
    AND engine_mode IN ('demo', 'live_demo')
    AND attribution_chain_ok
    AND net_bps_after_fee IS NOT NULL
)
SELECT
  to_char(d.bucket_day, 'YYYY-MM-DD') AS bucket_day,
  count(e.net_bps_after_fee)::int AS rows,
  count(e.net_bps_after_fee) FILTER (WHERE e.net_bps_after_fee > 0)::int AS wins,
  avg(e.net_bps_after_fee)::float8 AS avg_net_bps
FROM days d
LEFT JOIN edge_rows e ON e.bucket_day = d.bucket_day
GROUP BY d.bucket_day
ORDER BY d.bucket_day
"""
    current_sql = """
SELECT
  COUNT(*)::int,
  COUNT(*) FILTER (WHERE net_bps_after_fee > 0)::int,
  AVG(net_bps_after_fee)::float8
FROM learning.mlde_edge_training_rows
WHERE ts > now() - interval '24 hours'
  AND engine_mode IN ('demo', 'live_demo')
  AND attribution_chain_ok
  AND net_bps_after_fee IS NOT NULL
"""
    bad_cells_sql = """
SELECT engine_mode, strategy_name, symbol, COUNT(*)::int, AVG(net_bps_after_fee)::float8
FROM learning.mlde_edge_training_rows
WHERE ts > now() - interval '24 hours'
  AND engine_mode IN ('demo', 'live_demo')
  AND attribution_chain_ok
  AND net_bps_after_fee IS NOT NULL
GROUP BY engine_mode, strategy_name, symbol
HAVING COUNT(*) >= %s AND AVG(net_bps_after_fee) < %s
ORDER BY AVG(net_bps_after_fee), COUNT(*) DESC
LIMIT 6
"""
    try:
        cur.execute(day_sql, (span_days, span_days))
        day_rows = cur.fetchall() or []
        cur.execute(current_sql)
        current_row = cur.fetchone()
        cur.execute(
            bad_cells_sql,
            (EDGE_ACCEPTANCE_BAD_CELL_MIN_N, EDGE_ACCEPTANCE_BAD_CELL_MAX_AVG_BPS),
        )
        bad_rows = cur.fetchall() or []
    except Exception as exc:  # noqa: BLE001
        _rollback_cursor(cur)
        gate.update(
            {
                "available": False,
                "status": "unknown",
                "summary": f"realized edge trend query failed: {type(exc).__name__}: {exc}",
                "diagnostics": [str(exc)],
            }
        )
        return gate

    series: list[dict[str, Any]] = []
    for row in day_rows:
        total = _as_int(row[1])
        wins = _as_int(row[2])
        avg_net = _round_or_none(row[3], 2)
        series.append(
            {
                "bucket_day": row[0],
                "rows": total,
                "win_rate_pct": round(_pct(wins, total), 1),
                "avg_net_bps": avg_net,
            }
        )

    total = _as_int(current_row[0] if current_row else 0)
    wins = _as_int(current_row[1] if current_row else 0)
    avg_net = _as_float(current_row[2] if current_row else None, 0.0)
    maker_current = maker_gate.get("current") if isinstance(maker_gate, dict) else {}
    maker_total = _as_int(maker_current.get("entry_fills"))
    maker_pct = _as_float(maker_current.get("maker_like_pct"), 0.0)
    fee_drop = _as_float(maker_current.get("fee_drop_pct"), 0.0)
    bad_cells = [
        {
            "engine_mode": str(row[0] or ""),
            "strategy_name": str(row[1] or ""),
            "symbol": str(row[2] or ""),
            "rows": _as_int(row[3]),
            "avg_net_bps": _round_or_none(row[4], 2),
        }
        for row in bad_rows
    ]

    warnings: list[str] = []
    if total == 0:
        status = "warn"
        summary = "24h MLDE rows=0; no fresh post-fee training rows"
    elif bad_cells:
        status = "fail"
        summary = f"24h realized edge has {len(bad_cells)} active negative cells"
    else:
        if total >= EDGE_ACCEPTANCE_MIN_SAMPLE and avg_net <= EDGE_ACCEPTANCE_MIN_AVG_NET_BPS:
            warnings.append(f"avg_net={avg_net:.2f}bps")
        if maker_total >= MAKER_FILL_MIN_SAMPLE and maker_pct < EDGE_ACCEPTANCE_MAKER_MIN_PCT:
            warnings.append(f"maker_like={maker_pct:.1f}%")
        if maker_total >= MAKER_FILL_MIN_SAMPLE and fee_drop < MAKER_FEE_DROP_TARGET_PCT:
            warnings.append(f"fee_drop={fee_drop:.1f}%")
        if warnings:
            status = "warn"
            summary = "24h realized edge below acceptance: " + "; ".join(warnings)
        else:
            status = "pass"
            summary = "24h realized edge within acceptance guard"

    gate.update(
        {
            "status": status,
            "summary": summary,
            "target": {
                "min_rows": EDGE_ACCEPTANCE_MIN_SAMPLE,
                "min_avg_net_bps": EDGE_ACCEPTANCE_MIN_AVG_NET_BPS,
                "bad_cell_min_rows": EDGE_ACCEPTANCE_BAD_CELL_MIN_N,
                "bad_cell_max_avg_bps": EDGE_ACCEPTANCE_BAD_CELL_MAX_AVG_BPS,
                "maker_like_pct_min": EDGE_ACCEPTANCE_MAKER_MIN_PCT,
                "fee_drop_pct_min": MAKER_FEE_DROP_TARGET_PCT,
            },
            "current": {
                "window_hours": 24,
                "rows": total,
                "wins": wins,
                "win_rate_pct": round(_pct(wins, total), 1),
                "avg_net_bps": round(avg_net, 2),
                "maker_entry_fills": maker_total,
                "maker_like_pct": round(maker_pct, 1),
                "fee_drop_pct": round(fee_drop, 1),
                "bad_cells": bad_cells,
            },
            "series": series,
        }
    )
    return gate


def _fetch_strategy_status(
    cur: Any,
    window_days: int,
    realized_edge_gate: dict[str, Any],
    lifecycle_gate: dict[str, Any],
) -> list[dict[str, Any]]:
    """Fetch per-strategy pre-live edge status from MLDE labels.
    從 MLDE label 讀取每策略 pre-live edge 狀態。
    """
    _rollback_cursor(cur)
    try:
        cur.execute("SELECT to_regclass('learning.mlde_edge_training_rows') IS NOT NULL")
        exists = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        logger.warning("strategy edge status existence check failed: %s", exc)
        return [
            {
                "strategy_name": name,
                "status": "unknown",
                "summary": "learning.mlde_edge_training_rows existence check failed",
                "rows_24h": 0,
                "rows_window": 0,
            }
            for name in ACTIVE_STRATEGIES
        ]
    if not exists or not exists[0]:
        return [
            {
                "strategy_name": name,
                "status": "unknown",
                "summary": "learning.mlde_edge_training_rows missing",
                "rows_24h": 0,
                "rows_window": 0,
            }
            for name in ACTIVE_STRATEGIES
        ]

    sql = """
WITH strategy_rows AS (
  SELECT
    strategy_name,
    ts,
    net_bps_after_fee
  FROM learning.mlde_edge_training_rows
  WHERE ts > now() - (%s::int * interval '1 day')
    AND engine_mode IN ('demo', 'live_demo')
    AND attribution_chain_ok
    AND net_bps_after_fee IS NOT NULL
    AND coalesce(strategy_name, '') <> ''
)
SELECT
  strategy_name,
  COUNT(*) FILTER (WHERE ts > now() - interval '24 hours')::int AS rows_24h,
  AVG(net_bps_after_fee) FILTER (WHERE ts > now() - interval '24 hours')::float8 AS avg_net_24h_bps,
  (COUNT(*) FILTER (
     WHERE ts > now() - interval '24 hours' AND net_bps_after_fee > 0
   )::float8 / NULLIF(COUNT(*) FILTER (WHERE ts > now() - interval '24 hours'), 0)::float8 * 100.0)::float8
    AS win_rate_24h_pct,
  COUNT(*)::int AS rows_window,
  AVG(net_bps_after_fee)::float8 AS avg_net_window_bps
FROM strategy_rows
GROUP BY strategy_name
ORDER BY strategy_name
"""
    try:
        cur.execute(sql, (window_days,))
        rows = cur.fetchall() or []
    except Exception as exc:  # noqa: BLE001
        _rollback_cursor(cur)
        logger.warning("strategy edge status query failed: %s", exc)
        return [
            {
                "strategy_name": name,
                "status": "unknown",
                "summary": f"strategy edge query failed: {type(exc).__name__}",
                "rows_24h": 0,
                "rows_window": 0,
            }
            for name in ACTIVE_STRATEGIES
        ]

    by_name: dict[str, dict[str, Any]] = {}
    bad_cells = (realized_edge_gate.get("current") or {}).get("bad_cells") or []
    bad_by_strategy: dict[str, list[dict[str, Any]]] = {}
    for cell in bad_cells:
        name = str(cell.get("strategy_name") or "")
        if name:
            bad_by_strategy.setdefault(name, []).append(cell)

    lifecycle_status = str(lifecycle_gate.get("status") or "unknown").lower()
    for row in rows:
        name = str(row[0] or "")
        rows_24h = _as_int(row[1])
        avg_24h = _round_or_none(row[2], 2)
        win_24h = _round_or_none(row[3], 1)
        rows_window = _as_int(row[4])
        avg_window = _round_or_none(row[5], 2)
        bad = bad_by_strategy.get(name, [])
        reasons: list[str] = []
        status = "unknown"

        if bad:
            status = "crisis"
            reasons.append(f"{len(bad)} active negative cell(s)")
        elif rows_24h == 0:
            status = "unknown"
            reasons.append("no fresh 24h MLDE labels")
        elif rows_24h < EDGE_ACCEPTANCE_BAD_CELL_MIN_N:
            status = "warn"
            reasons.append(f"24h rows {rows_24h} below sample target {EDGE_ACCEPTANCE_BAD_CELL_MIN_N}")
        elif avg_24h is not None and avg_24h > EDGE_ACCEPTANCE_MIN_AVG_NET_BPS:
            status = "pass"
            reasons.append(f"24h avg_net {avg_24h:.2f} bps above target")
        elif avg_24h is not None and avg_24h > 0:
            status = "warn"
            reasons.append(f"24h avg_net {avg_24h:.2f} bps positive but below target")
        elif avg_24h is not None:
            status = "fail"
            reasons.append(f"24h avg_net {avg_24h:.2f} bps is non-positive")

        if name == "grid_trading" and lifecycle_status in {"warn", "fail"}:
            if status not in {"crisis", "fail"}:
                status = "warn"
            reasons.append(f"grid lifecycle gate {lifecycle_status}")

        by_name[name] = {
            "strategy_name": name,
            "status": status,
            "rows_24h": rows_24h,
            "avg_net_24h_bps": avg_24h,
            "win_rate_24h_pct": win_24h,
            "rows_window": rows_window,
            "avg_net_window_bps": avg_window,
            "bad_cells": bad,
            "summary": "; ".join(reasons) if reasons else "no status reason",
            "target": {
                "min_rows_24h": EDGE_ACCEPTANCE_BAD_CELL_MIN_N,
                "min_avg_net_bps": EDGE_ACCEPTANCE_MIN_AVG_NET_BPS,
                "crisis_avg_net_bps_max": EDGE_ACCEPTANCE_BAD_CELL_MAX_AVG_BPS,
            },
        }

    all_names = list(ACTIVE_STRATEGIES)
    for name in sorted(set(by_name) | set(bad_by_strategy)):
        if name not in all_names:
            all_names.append(name)

    result: list[dict[str, Any]] = []
    for name in all_names:
        if name in by_name:
            result.append(by_name[name])
            continue
        bad = bad_by_strategy.get(name, [])
        result.append(
            {
                "strategy_name": name,
                "status": "crisis" if bad else "unknown",
                "rows_24h": 0,
                "avg_net_24h_bps": None,
                "win_rate_24h_pct": None,
                "rows_window": 0,
                "avg_net_window_bps": None,
                "bad_cells": bad,
                "summary": (
                    f"{len(bad)} active negative cell(s)"
                    if bad else "no fresh MLDE labels in window"
                ),
                "target": {
                    "min_rows_24h": EDGE_ACCEPTANCE_BAD_CELL_MIN_N,
                    "min_avg_net_bps": EDGE_ACCEPTANCE_MIN_AVG_NET_BPS,
                    "crisis_avg_net_bps_max": EDGE_ACCEPTANCE_BAD_CELL_MAX_AVG_BPS,
                },
            }
        )
    return result


def _readiness_item(
    *,
    gate: str,
    key: str,
    label: str,
    value: Any,
    target: str,
    passed: bool,
    known: bool = True,
    detail: str = "",
) -> dict[str, Any]:
    """Create a Live readiness checklist item. 建立 Live readiness 檢查項。"""
    status = "pass" if passed else ("fail" if known else "unknown")
    return {
        "gate": gate,
        "key": key,
        "label": label,
        "value": value,
        "target": target,
        "passed": bool(passed),
        "known": bool(known),
        "status": status,
        "detail": detail,
    }


def build_live_readiness(gates: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Build the dashboard Live-readiness checklist from gate payloads.
    從 gate payload 建立 dashboard Live readiness 檢查清單。
    """
    maker = gates.get("33", {})
    lifecycle = gates.get("38", {})
    edge = gates.get("40", {})
    maker_current = maker.get("current") or {}
    lifecycle_current = lifecycle.get("current") or {}
    edge_current = edge.get("current") or {}

    maker_rows = _as_int(maker_current.get("entry_fills"))
    fee_drop = maker_current.get("fee_drop_pct")
    maker_like = maker_current.get("maker_like_pct")
    lifetime_ratio = lifecycle_current.get("lifetime_ratio")
    live_reentry = lifecycle_current.get("live_demo_reentry_rate")
    demo_n = _as_int(lifecycle_current.get("demo_n"))
    live_n = _as_int(lifecycle_current.get("live_demo_n"))
    edge_rows = _as_int(edge_current.get("rows"))
    avg_net = edge_current.get("avg_net_bps")
    bad_cells = edge_current.get("bad_cells") or []

    fee_known = fee_drop is not None and maker_rows >= MAKER_FILL_MIN_SAMPLE
    lifetime_known = (
        lifetime_ratio is not None
        and demo_n >= GRID_LIFECYCLE_MIN_SAMPLE
        and live_n >= GRID_LIFECYCLE_MIN_SAMPLE
    )
    reentry_known = live_reentry is not None and live_n >= GRID_LIFECYCLE_MIN_SAMPLE
    edge_known = avg_net is not None and edge_rows >= EDGE_ACCEPTANCE_MIN_SAMPLE
    maker_like_known = maker_like is not None and maker_rows >= MAKER_FILL_MIN_SAMPLE

    items = [
        _readiness_item(
            gate="33",
            key="postonly_fee_drop",
            label="PostOnly fee drop",
            value=fee_drop,
            target=f">= {MAKER_FEE_DROP_TARGET_PCT:.0f}% with >= {MAKER_FILL_MIN_SAMPLE} fills",
            known=fee_known,
            passed=bool(fee_known and _as_float(fee_drop) >= MAKER_FEE_DROP_TARGET_PCT),
            detail=f"entry_fills={maker_rows}",
        ),
        _readiness_item(
            gate="33",
            key="maker_like_share",
            label="Maker-like settlement",
            value=maker_like,
            target=f">= {EDGE_ACCEPTANCE_MAKER_MIN_PCT:.0f}% with >= {MAKER_FILL_MIN_SAMPLE} fills",
            known=maker_like_known,
            passed=bool(maker_like_known and _as_float(maker_like) >= EDGE_ACCEPTANCE_MAKER_MIN_PCT),
            detail=f"entry_fills={maker_rows}",
        ),
        _readiness_item(
            gate="38",
            key="grid_lifetime_ratio",
            label="Grid lifetime ratio",
            value=lifetime_ratio,
            target=f">= {GRID_LIFETIME_RATIO_WARN:.2f} with >= {GRID_LIFECYCLE_MIN_SAMPLE}/mode",
            known=lifetime_known,
            passed=bool(lifetime_known and _as_float(lifetime_ratio) >= GRID_LIFETIME_RATIO_WARN),
            detail=f"demo_n={demo_n}, live_demo_n={live_n}",
        ),
        _readiness_item(
            gate="38",
            key="grid_reentry_rate",
            label="Grid live re-entry rate",
            value=live_reentry,
            target=f"<= {GRID_REENTRY_RATE_WARN:.2f}",
            known=reentry_known,
            passed=bool(reentry_known and _as_float(live_reentry) <= GRID_REENTRY_RATE_WARN),
            detail=f"live_demo_n={live_n}",
        ),
        _readiness_item(
            gate="40",
            key="realized_avg_net_bps",
            label="Realized avg net edge",
            value=avg_net,
            target=f"> {EDGE_ACCEPTANCE_MIN_AVG_NET_BPS:.1f} bps with >= {EDGE_ACCEPTANCE_MIN_SAMPLE} rows",
            known=edge_known,
            passed=bool(edge_known and _as_float(avg_net) > EDGE_ACCEPTANCE_MIN_AVG_NET_BPS),
            detail=f"rows={edge_rows}",
        ),
        _readiness_item(
            gate="40",
            key="negative_cells",
            label="Active negative cells",
            value=len(bad_cells),
            target=f"0 cells below {EDGE_ACCEPTANCE_BAD_CELL_MAX_AVG_BPS:.0f} bps",
            known=bool(edge.get("available")),
            passed=bool(edge.get("available") and len(bad_cells) == 0),
            detail=f"bad_cells={len(bad_cells)}",
        ),
    ]
    ready = all(item["passed"] for item in items)
    return {
        "ready": ready,
        "status": "ready" if ready else "not_ready",
        "items": items,
        "passed": sum(1 for item in items if item["passed"]),
        "total": len(items),
        "unknown": sum(1 for item in items if not item["known"]),
    }


def _degraded_payload(window_days: int, reason: str) -> dict[str, Any]:
    """Return a stable fail-soft payload when PG is unavailable.
    PG 不可用時回傳穩定 fail-soft payload。
    """
    gates = {gate_id: _gate_template(gate_id, available=False) for gate_id in GATE_LABELS}
    for gate in gates.values():
        gate["summary"] = reason
        gate["diagnostics"] = [reason]
    return {
        "available": False,
        "source": "pg_prelive_edge_gate_trends",
        "window_days": window_days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gates": gates,
        "readiness": build_live_readiness(gates),
        "strategy_status": [
            {
                "strategy_name": name,
                "status": "unknown",
                "summary": reason,
                "rows_24h": 0,
                "rows_window": 0,
            }
            for name in ACTIVE_STRATEGIES
        ],
        "error": reason,
    }


def fetch_prelive_edge_gate_trends(window_days: int = 7) -> dict[str, Any]:
    """Fetch read-only trend data for pre-live gates [33], [38], and [40].
    讀取 pre-live gate [33]/[38]/[40] 的只讀趨勢資料。
    """
    bounded_days = max(3, min(int(window_days or 7), 30))
    try:
        with get_pg_conn() as conn:
            if conn is None:
                return _degraded_payload(bounded_days, "postgres connection unavailable")
            cur = conn.cursor()
            maker_gate = _fetch_maker_fill_gate(cur, bounded_days)
            lifecycle_gate = _fetch_grid_lifecycle_gate(cur, bounded_days)
            realized_edge_gate = _fetch_realized_edge_gate(cur, bounded_days, maker_gate)
            gates = {
                "33": maker_gate,
                "38": lifecycle_gate,
                "40": realized_edge_gate,
            }
            return {
                "available": any(gate.get("available") for gate in gates.values()),
                "source": "pg_prelive_edge_gate_trends",
                "window_days": bounded_days,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "gates": gates,
                "readiness": build_live_readiness(gates),
                "strategy_status": _fetch_strategy_status(
                    cur,
                    bounded_days,
                    realized_edge_gate,
                    lifecycle_gate,
                ),
            }
    except Exception as exc:  # noqa: BLE001
        logger.warning("pre-live edge gate trend fetch failed: %s", exc, exc_info=True)
        return _degraded_payload(bounded_days, f"trend fetch failed: {type(exc).__name__}: {exc}")
