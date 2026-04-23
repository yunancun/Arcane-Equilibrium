from __future__ import annotations

"""
Strategist Applied-Params History Router /
策略師已應用參數歷史路由

STRATEGIST-HISTORY-OBSERVABILITY-1 backend endpoint (2026-04-23).

MODULE_NOTE (EN): Read-only routes exposing the `learning.strategist_applied_params`
  audit trail (V019 + V020 migrations) plus an optional `trading.fills` join for
  post-apply 7d edge effect. Backs the future GUI "promote history" tab.

  The table records every Strategist parameter change — both 5-min auto-tune
  cycles (`source='strategist_scheduler'`) and manual Operator promotes
  (`source='manual_promote'`, landed via STRATEGIST-PROMOTE-TRIGGER-1 — not
  yet wired, but the schema already supports it). The endpoint therefore
  starts useful today (auto-tune visibility) and will automatically surface
  promote rows the moment TRIGGER-1 starts writing them — no schema change
  needed.

  Endpoints:
    * GET /api/v1/strategist/history
        — list recent N rows with optional engine_mode / strategy / source
          filters. Returns `before` + `after` param JSON so a GUI diff view
          can reconstruct what changed.
    * GET /api/v1/strategist/history/summary
        — aggregate: total rows + success/fail breakdown by `source`. The
          "success" notion here is provisional: V019 only persists rows
          AFTER the in-memory apply succeeded, so every stored row is a
          `source`-tagged success. Once STRATEGIST-PROMOTE-TRIGGER-1 starts
          writing `observability.engine_events { event_type='strategist_promote_fail' }`,
          a follow-up PR can join that in and flip the provisional success
          ratio to a real one.
    * GET /api/v1/strategist/history/{row_id}/effect
        — optional 7d edge effect: net PnL / win rate / fill count from
          `trading.fills` for the (engine_mode, strategy_name) over the
          7-day window starting at `applied_at`. Useful for judging whether
          a specific promote improved or hurt Live edge.

  Fail-closed contract: every endpoint returns HTTP 200 with `degraded=true`
  and an empty-ish payload when PG is unavailable. Never 5xx on DB outage.

MODULE_NOTE (中): 策略師已應用參數歷史查詢路由（STRATEGIST-HISTORY-OBSERVABILITY-1
  backend 端點）。只讀 `learning.strategist_applied_params`（V019 + V020）加
  可選 `trading.fills` join（7d edge effect）。

  表同時記錄 5 min 自動 tune（`source='strategist_scheduler'`）與 Operator 手動
  promote（`source='manual_promote'`，由 STRATEGIST-PROMOTE-TRIGGER-1 寫入—目前
  未接線但 schema 已支援）。故端點現在即有用（自動 tune 歷史），TRIGGER-1 上線
  後 promote row 自動納入，無須 schema 改動。

  三端點：list / summary / {row_id}/effect。全部 fail-closed，PG 不可用回 200 +
  degraded=true，絕不 5xx。
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from . import main_legacy as base
from .db_pool import get_pg_conn

logger = logging.getLogger(__name__)

strategist_history_router = APIRouter(
    prefix="/api/v1/strategist/history",
    tags=["Strategist History / 策略師參數變更歷史"],
)


# ── Allow-list tables / 允許白名單 ────────────────────────────────────────────
# engine_mode filter whitelist. We accept everything a fill might tag with
# (see memory/project_engine_mode_tag_live_demo.md) plus paper/demo, so a
# client UI can scope the view per environment.
# engine_mode 白名單，涵蓋 fill 可能寫入的所有值；供 UI 分引擎檢視。
_ALLOWED_ENGINE_MODES: frozenset[str] = frozenset(
    {"paper", "demo", "live", "live_demo", "live_testnet"}
)

# `source` whitelist mirrors V019 COMMENT on `source` column. We leave it
# loose enough for Phase 5+ promote flow to write 'manual_promote' +
# 'operator_override' without a schema migration.
# `source` 白名單對齊 V019 註解（strategist_scheduler / manual_promote /
# operator_override），不因 Phase 5+ promote flow 新值而要動 migration。
_ALLOWED_SOURCES: frozenset[str] = frozenset(
    {"strategist_scheduler", "manual_promote", "operator_override"}
)

# Strategy name whitelist matches the six active strategies in the engine
# (see `strategy_wiring.py` + `shadow_fills_routes._ALLOWED_STRATEGIES`).
# Keeps unbounded GROUP BY / URL-injected strategy names out.
# 策略名白名單（與 engine 六個策略 + shadow_fills_routes 對齊），防 URL 注入。
_ALLOWED_STRATEGIES: frozenset[str] = frozenset(
    {
        "ma_crossover",
        "bb_reversion",
        "bb_breakout",
        "grid_trading",
        "funding_arb",
    }
)

# Upper bound on `limit` param to keep any future "give me everything" call
# from blowing up memory / response size.
# limit 上界，防任意大 page 擊穿記憶體。
_MAX_LIMIT = 200

# 7-day effect window in milliseconds — matches TODO wording "7d edge effect".
# 7 日 edge effect 窗口（毫秒）。
_SEVEN_DAYS_MS: int = 7 * 24 * 60 * 60 * 1000


# ── Helpers / 輔助函數 ────────────────────────────────────────────────────────


def _fetch_history_rows(
    engine_mode: str | None,
    strategy_name: str | None,
    source: str | None,
    limit: int,
) -> tuple[list[dict[str, Any]], str | None]:
    """
    Read recent strategist applied-params rows with optional filters.
    讀取最近的 strategist_applied_params 列（可選篩選）。

    Returns (rows, err_reason) — err_reason None on success.
    """
    where: list[str] = ["1=1"]
    args: list[Any] = []
    if engine_mode is not None:
        where.append("engine_mode = %s")
        args.append(engine_mode)
    if strategy_name is not None:
        where.append("strategy_name = %s")
        args.append(strategy_name)
    if source is not None:
        where.append("source = %s")
        args.append(source)
    args.append(limit)

    sql = f"""
        SELECT id,
               engine_mode,
               strategy_name,
               applied_at,
               applied_at_ms,
               source,
               reason,
               prev_params_json,
               params_json
          FROM learning.strategist_applied_params
         WHERE {' AND '.join(where)}
         ORDER BY applied_at_ms DESC, id DESC
         LIMIT %s
    """

    with get_pg_conn() as conn:
        if conn is None:
            return [], "pg_unavailable"
        try:
            cur = conn.cursor()
            cur.execute(sql, tuple(args))
            cols = [d.name for d in cur.description] if cur.description else []
            rows: list[dict[str, Any]] = []
            for tup in cur.fetchall():
                row = dict(zip(cols, tup))
                applied_at = row.get("applied_at")
                if applied_at is not None:
                    row["applied_at"] = applied_at.isoformat()
                rows.append(row)
            return rows, None
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("strategist_history list query failed: %s", exc)
            return [], f"pg_error:{type(exc).__name__}"


def _fetch_history_summary(
    engine_mode: str | None,
) -> tuple[dict[str, Any], str | None]:
    """
    Aggregate by (source) + total row count, optional engine filter.
    按 source 聚合加總列數（可選 engine 篩選）。
    """
    where: list[str] = ["1=1"]
    args: list[Any] = []
    if engine_mode is not None:
        where.append("engine_mode = %s")
        args.append(engine_mode)

    sql = f"""
        SELECT source,
               COUNT(*)        AS n,
               MIN(applied_at) AS first_applied_at,
               MAX(applied_at) AS last_applied_at
          FROM learning.strategist_applied_params
         WHERE {' AND '.join(where)}
         GROUP BY source
         ORDER BY n DESC
    """

    with get_pg_conn() as conn:
        if conn is None:
            return {"by_source": [], "total": 0}, "pg_unavailable"
        try:
            cur = conn.cursor()
            cur.execute(sql, tuple(args))
            by_source: list[dict[str, Any]] = []
            total = 0
            for tup in cur.fetchall():
                src, n, first_at, last_at = tup
                n_int = int(n or 0)
                total += n_int
                by_source.append(
                    {
                        "source": src,
                        "n": n_int,
                        "first_applied_at": (
                            first_at.isoformat() if first_at is not None else None
                        ),
                        "last_applied_at": (
                            last_at.isoformat() if last_at is not None else None
                        ),
                    }
                )
            return {"by_source": by_source, "total": total}, None
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("strategist_history summary query failed: %s", exc)
            return {"by_source": [], "total": 0}, f"pg_error:{type(exc).__name__}"


def _fetch_row_by_id(row_id: int) -> tuple[dict[str, Any] | None, str | None]:
    """Fetch a single applied-params row by primary key. 依 id 取單列。"""
    sql = """
        SELECT id, engine_mode, strategy_name, applied_at, applied_at_ms,
               source, reason, prev_params_json, params_json
          FROM learning.strategist_applied_params
         WHERE id = %s
    """
    with get_pg_conn() as conn:
        if conn is None:
            return None, "pg_unavailable"
        try:
            cur = conn.cursor()
            cur.execute(sql, (row_id,))
            tup = cur.fetchone()
            if tup is None:
                return None, None
            cols = [d.name for d in cur.description] if cur.description else []
            row = dict(zip(cols, tup))
            applied_at = row.get("applied_at")
            if applied_at is not None:
                row["applied_at"] = applied_at.isoformat()
            return row, None
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("strategist_history row-by-id query failed: %s", exc)
            return None, f"pg_error:{type(exc).__name__}"


def _fetch_effect_for_row(
    engine_mode: str,
    strategy_name: str,
    applied_at_ms: int,
) -> tuple[dict[str, Any], str | None]:
    """
    Compute 7d edge effect (`trading.fills` net PnL / win rate / count) for a
    (engine_mode, strategy_name) starting at applied_at_ms.

    LiveDemo caveat: fills write `engine_mode = 'live_demo'` even when the
    applied-params row is tagged `'live'` (see
    memory/project_engine_mode_tag_live_demo.md). For 'live' queries we widen
    the filter to `IN ('live', 'live_demo')` so LiveDemo fills aren't silently
    dropped. This mirrors what
    `strategist_scheduler::gather_strategy_metrics` will need when Live tune
    is enabled (FA-1 follow-up in the Rust side).

    LiveDemo 提醒：fills `engine_mode = 'live_demo'` 但 applied 列為
    `'live'`，故 'live' 查詢放寬為 `IN ('live','live_demo')`，避免靜默漏資料。
    """
    mode_filter_args: tuple[str, ...]
    if engine_mode == "live":
        mode_filter_sql = "engine_mode IN (%s, %s)"
        mode_filter_args = ("live", "live_demo")
    else:
        mode_filter_sql = "engine_mode = %s"
        mode_filter_args = (engine_mode,)

    window_end_ms = applied_at_ms + _SEVEN_DAYS_MS
    sql = f"""
        SELECT COUNT(*)::bigint                                          AS fill_count,
               COALESCE(SUM(realized_pnl), 0.0)::float8                  AS net_pnl,
               COALESCE(
                   SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::float8
                   / NULLIF(COUNT(*), 0)::float8,
                   0.0
               )                                                          AS win_rate,
               MIN(ts)                                                    AS first_fill_ts,
               MAX(ts)                                                    AS last_fill_ts
          FROM trading.fills
         WHERE {mode_filter_sql}
           AND strategy_name = %s
           AND ts >= to_timestamp(%s::double precision / 1000.0)
           AND ts <= to_timestamp(%s::double precision / 1000.0)
    """

    args = list(mode_filter_args) + [
        strategy_name,
        applied_at_ms,
        window_end_ms,
    ]

    empty: dict[str, Any] = {
        "fill_count": 0,
        "net_pnl": 0.0,
        "win_rate": 0.0,
        "first_fill_ts": None,
        "last_fill_ts": None,
        "window_start_ms": applied_at_ms,
        "window_end_ms": window_end_ms,
    }

    with get_pg_conn() as conn:
        if conn is None:
            return empty, "pg_unavailable"
        try:
            cur = conn.cursor()
            cur.execute(sql, tuple(args))
            row = cur.fetchone()
            if row is None:
                return empty, None
            fill_count, net_pnl, win_rate, first_ts, last_ts = row
            return {
                "fill_count": int(fill_count or 0),
                "net_pnl": float(net_pnl or 0.0),
                "win_rate": float(win_rate or 0.0),
                "first_fill_ts": first_ts.isoformat() if first_ts is not None else None,
                "last_fill_ts": last_ts.isoformat() if last_ts is not None else None,
                "window_start_ms": applied_at_ms,
                "window_end_ms": window_end_ms,
            }, None
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("strategist_history effect query failed: %s", exc)
            return empty, f"pg_error:{type(exc).__name__}"


# ── Routes / 路由 ─────────────────────────────────────────────────────────────


@strategist_history_router.get("")
async def list_strategist_history(
    engine_mode: str | None = Query(
        default=None,
        description="engine_mode filter (paper/demo/live/live_demo/live_testnet) / 引擎過濾",
    ),
    strategy_name: str | None = Query(
        default=None,
        description="strategy_name filter (whitelisted) / 策略名過濾",
    ),
    source: str | None = Query(
        default=None,
        description=(
            "source filter (strategist_scheduler / manual_promote / operator_override) "
            "/ 來源過濾"
        ),
    ),
    limit: int = Query(default=50, ge=1, le=_MAX_LIMIT, description="Page size / 分頁"),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """
    GET /api/v1/strategist/history — recent N applied-params rows.
    最近 N 個策略師已應用參數列。

    Each row ships:
        id / engine_mode / strategy_name / applied_at (ISO) / applied_at_ms /
        source / reason / prev_params_json / params_json

    The (prev_params_json, params_json) pair lets a GUI render a diff view
    of what changed on this apply.
    """
    if engine_mode is not None and engine_mode not in _ALLOWED_ENGINE_MODES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"engine_mode must be one of {sorted(_ALLOWED_ENGINE_MODES)} "
                f"/ engine_mode 須為白名單值"
            ),
        )
    if strategy_name is not None and strategy_name not in _ALLOWED_STRATEGIES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"strategy_name must be one of {sorted(_ALLOWED_STRATEGIES)} "
                f"/ strategy_name 須為白名單值"
            ),
        )
    if source is not None and source not in _ALLOWED_SOURCES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"source must be one of {sorted(_ALLOWED_SOURCES)} "
                f"/ source 須為白名單值"
            ),
        )

    rows, reason = _fetch_history_rows(engine_mode, strategy_name, source, limit)
    data = {
        "rows": rows,
        "limit": limit,
        "filters": {
            "engine_mode": engine_mode,
            "strategy_name": strategy_name,
            "source": source,
        },
        "degraded": reason is not None,
        "reason": reason,
    }
    return {
        "ok": True,
        "data": data,
        "is_simulated": False,
        "data_category": "strategist_history",
    }


@strategist_history_router.get("/summary")
async def summary_strategist_history(
    engine_mode: str | None = Query(
        default=None,
        description="engine_mode filter / 引擎過濾",
    ),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """
    GET /api/v1/strategist/history/summary — aggregate by source.
    按 source 聚合總覽。

    Returns:
        total: total apply-row count (within filter)
        by_source: list of { source, n, first_applied_at, last_applied_at }

    "Success ratio": all rows are successes (V019 persists only AFTER
    successful in-memory apply). STRATEGIST-PROMOTE-TRIGGER-1 must write
    `observability.engine_events { event_type='strategist_promote_fail' }`
    on failure; a follow-up PR can then surface a real success-vs-fail
    ratio by LEFT JOIN on those events.
    """
    if engine_mode is not None and engine_mode not in _ALLOWED_ENGINE_MODES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"engine_mode must be one of {sorted(_ALLOWED_ENGINE_MODES)} "
                f"/ engine_mode 須為白名單值"
            ),
        )

    agg, reason = _fetch_history_summary(engine_mode)
    data = {
        "total": agg["total"],
        "by_source": agg["by_source"],
        "filters": {"engine_mode": engine_mode},
        "degraded": reason is not None,
        "reason": reason,
        "notes": {
            "success_ratio": (
                "All rows represent successful applies (V019 persists post-apply). "
                "True success/fail ratio awaits STRATEGIST-PROMOTE-TRIGGER-1 "
                "engine_events wiring."
            ),
        },
    }
    return {
        "ok": True,
        "data": data,
        "is_simulated": False,
        "data_category": "strategist_history_summary",
    }


@strategist_history_router.get("/{row_id}/effect")
async def effect_for_history_row(
    row_id: int = Path(..., ge=1, description="strategist_applied_params.id / 列 id"),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """
    GET /api/v1/strategist/history/{row_id}/effect — 7d edge effect.
    單列 7 日 edge 效果。

    Reads `learning.strategist_applied_params` for the row, then aggregates
    `trading.fills` (engine_mode + strategy_name matched) over the 7-day
    window starting at `applied_at_ms`. Returns fill count, net PnL, and
    win rate — enough for a GUI badge "this promote produced +12.3 USDT
    net over 7d on 47 fills (57% win rate)".

    LiveDemo note: for `engine_mode='live'` rows we widen the fills filter
    to `IN ('live','live_demo')` because LiveDemo tags fills as 'live_demo'
    (see memory/project_engine_mode_tag_live_demo.md).
    """
    row, row_reason = _fetch_row_by_id(row_id)
    if row_reason == "pg_unavailable":
        return {
            "ok": True,
            "data": {
                "row": None,
                "effect": None,
                "degraded": True,
                "reason": "pg_unavailable",
            },
            "is_simulated": False,
            "data_category": "strategist_history_effect",
        }
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"strategist_applied_params row {row_id} not found / 列不存在",
        )

    effect, eff_reason = _fetch_effect_for_row(
        engine_mode=row["engine_mode"],
        strategy_name=row["strategy_name"],
        applied_at_ms=int(row["applied_at_ms"]),
    )
    data = {
        "row": row,
        "effect": effect,
        "degraded": eff_reason is not None,
        "reason": eff_reason,
    }
    return {
        "ok": True,
        "data": data,
        "is_simulated": False,
        "data_category": "strategist_history_effect",
    }
