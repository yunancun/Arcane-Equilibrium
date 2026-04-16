from __future__ import annotations

"""
Shadow-fill Consumer Router / Shadow-fill 消費者路由

EDGE-P3-1 Step 7c Python consumer — read-side routes over
`learning.decision_shadow_fills` populated by the Rust shadow_fill_writer.

MODULE_NOTE (EN): Three read endpoints surface shadow-fill data to GUI and
  audit callers:
    * GET /api/v1/edge/shadow_fills             — paginated list (filters)
    * GET /api/v1/edge/shadow_fills/summary     — per-strategy aggregate
    * GET /api/v1/edge/shadow_fills/promotion_gate/{strategy}
                                                — Stage 2 ship-readiness probe

  Shadow fills are ε-greedy paper exploration rows (spec §7.3 / F4+U3): the
  predictor rejected on cost but the exploration coin flip succeeded, so the
  engine synthesises a fill for off-policy observation only — never for live,
  demo, or training labels (parquet_etl §5.1 hard-excludes them). Rows
  therefore only exist when paper is running AND an ONNX predictor is loaded.

  With PAPER-DISABLE-1 (2026-04-16) paper defaults off (`OPENCLAW_ENABLE_PAPER=1`
  to enable) and Stage 2+ synthetic-close writer is not yet wired, so the
  typical response shape today is `n=0, verdict=insufficient_samples`.
  That is the intended empty-path behaviour — the scaffolding is ready for
  when ε-greedy exploration starts producing rows.

  Fail-closed contract: all three endpoints return HTTP 200 with
  `degraded=true` + empty-ish payload when PG is unavailable. Never 5xx.

MODULE_NOTE (中): 三條 EDGE-P3-1 Step 7c 讀取路由，覆蓋
  `learning.decision_shadow_fills`（由 Rust shadow_fill_writer 寫入）。
  Shadow fill = ε-greedy paper 探索合成 fill，僅供離線觀測，不進 live/demo
  也不進訓練 label（parquet_etl §5.1 硬排除）。PAPER-DISABLE-1 後 paper
  預設關閉 → 表預設空；Stage 2+ synthetic-close writer 尚未接線 →
  `synthetic_*` 欄位暫時留 NULL。
  此 module 為骨架，先具備 fail-closed + 空資料優雅返回；實際資料流接通
  後可零改動直接上工作流。HTTP 層永遠 200 + degraded flag，絕不 5xx。
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from . import main_legacy as base
from .db_pool import get_pg_conn

logger = logging.getLogger(__name__)

shadow_fills_router = APIRouter(
    prefix="/api/v1/edge/shadow_fills",
    tags=["Edge Shadow Fills / 邊際預測器 Shadow Fills"],
)


# Allowed engine_mode filter values. DB CHECK pins rows to "paper" so the
# API accepts only that here — guards against client-side typo surfacing an
# empty payload that looks like a DB outage rather than "wrong filter".
# 允許的 engine_mode 篩選值。DB CHECK 鎖定 paper，API 同步限制。
_ALLOWED_ENGINES: tuple[str, ...] = ("paper",)

# Strategy-name whitelist: matches the six active strategies in the engine
# plus `funding_arb_*` family. Kept explicit so the audit endpoint can't
# leak unbounded grouping on a mis-typed strategy_name injected in the URL.
# 策略名白名單（六個活躍策略 + funding_arb 家族），避免 URL 注入誤差造成的
# unbounded GROUP BY。
_ALLOWED_STRATEGIES: frozenset[str] = frozenset(
    {
        "ma_crossover",
        "bb_reversion",
        "bb_breakout",
        "grid_trading",
        "funding_arb",
    }
)

# Stage 2 promotion gate thresholds (spec §8.3 acceptance line 714):
#   n ≥ 500 AND metrics pass → ship prod artifact
#   200 ≤ n < 500            → ship shadow artifact
#   n < 200                  → insufficient samples
# The "metrics pass" conjunct (pinball skill, coverage error, decile lift,
# etc.) is evaluated by the offline training pipeline, not this endpoint —
# here we only surface the sample-count tier + synthetic-label coverage.
# Stage 2 晉升門檻（spec §8.3 line 714）；本端點僅回報樣本數分級 +
# synthetic 標籤覆蓋率，離線訓練指標由 run_training_pipeline 裁決。
_PROMOTION_SHIP_PROD_MIN: int = 500
_PROMOTION_SHIP_SHADOW_MIN: int = 200


def _empty_summary_row(strategy: str) -> dict[str, Any]:
    """Zero-sample shape returned when PG is down or strategy has no rows.
    PG 不可用或策略無資料時回傳的零樣本形狀。"""
    return {
        "strategy_name": strategy,
        "n": 0,
        "n_with_synthetic": 0,
        "predicted_q50_mean": None,
        "cost_bps_mean": None,
        "synthetic_net_edge_bps_mean": None,
        "first_ts_utc": None,
        "last_ts_utc": None,
    }


def _promotion_verdict(n_total: int, n_with_synthetic: int) -> tuple[str, str]:
    """Map (n_total, n_with_synthetic) → (verdict, next_action) per spec §8.3.
    依 spec §8.3 將樣本數分級映射為 verdict + 下一步建議。"""
    if n_total < _PROMOTION_SHIP_SHADOW_MIN:
        return (
            "insufficient_samples",
            f"accumulate ≥{_PROMOTION_SHIP_SHADOW_MIN} shadow fills before ship assessment",
        )
    if n_with_synthetic < _PROMOTION_SHIP_SHADOW_MIN:
        return (
            "awaiting_synthetic_labels",
            "synthetic-close writer must populate synthetic_net_edge_bps "
            "before offline metrics can run",
        )
    if n_total >= _PROMOTION_SHIP_PROD_MIN:
        return (
            "ship_prod_candidate",
            "run offline metrics gate (pinball skill / coverage / decile lift); "
            "pass → ship prod ONNX artifact",
        )
    # 200 <= n_total < 500 with synthetic coverage
    return (
        "ship_shadow_candidate",
        "run offline metrics gate; pass → ship shadow ONNX artifact, "
        f"continue accumulating to n ≥ {_PROMOTION_SHIP_PROD_MIN} for prod",
    )


def _fetch_rows(
    strategy: str | None,
    engine: str,
    symbol: str | None,
    since_iso: str | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], str | None]:
    """Read `learning.decision_shadow_fills` with filters. Returns (rows, err).
    讀取 shadow fills 表（含篩選）；回 (rows, error_reason|None)。"""
    # SQL with bind params — never string-interpolate user input. Filter
    # predicates added conditionally to keep the prepared-statement simple.
    # 動態 WHERE 片段用綁定參數；絕不字串拼接使用者輸入。
    where: list[str] = ["engine_mode = %s"]
    args: list[Any] = [engine]
    if strategy is not None:
        where.append("strategy_name = %s")
        args.append(strategy)
    if symbol is not None:
        where.append("symbol = %s")
        args.append(symbol)
    if since_iso is not None:
        where.append("ts >= %s::timestamptz")
        args.append(since_iso)
    args.extend([limit, offset])

    sql = f"""
        SELECT shadow_id, context_id, ts, engine_mode, strategy_name, symbol,
               side, predicted_q10, predicted_q50, predicted_q90,
               cost_bps_at_open, synthetic_exit_price, synthetic_hold_ms,
               synthetic_net_edge_bps, close_tag
          FROM learning.decision_shadow_fills
         WHERE {' AND '.join(where)}
         ORDER BY ts DESC
         LIMIT %s OFFSET %s
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
                ts = row.get("ts")
                if ts is not None:
                    row["ts"] = ts.isoformat()
                rows.append(row)
            return rows, None
        except Exception as exc:
            logger.warning("shadow_fills list query failed: %s", exc)
            return [], f"pg_error:{type(exc).__name__}"


def _fetch_summary(
    engine: str,
    since_iso: str | None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Per-strategy aggregate. 每策略聚合。"""
    where = ["engine_mode = %s"]
    args: list[Any] = [engine]
    if since_iso is not None:
        where.append("ts >= %s::timestamptz")
        args.append(since_iso)

    sql = f"""
        SELECT strategy_name,
               COUNT(*)                                                   AS n,
               COUNT(synthetic_net_edge_bps)                              AS n_with_synthetic,
               AVG(predicted_q50)                                         AS predicted_q50_mean,
               AVG(cost_bps_at_open)                                      AS cost_bps_mean,
               AVG(synthetic_net_edge_bps) FILTER (WHERE synthetic_net_edge_bps IS NOT NULL)
                                                                          AS synthetic_net_edge_bps_mean,
               MIN(ts)                                                    AS first_ts,
               MAX(ts)                                                    AS last_ts
          FROM learning.decision_shadow_fills
         WHERE {' AND '.join(where)}
         GROUP BY strategy_name
         ORDER BY n DESC
    """

    with get_pg_conn() as conn:
        if conn is None:
            return [], "pg_unavailable"
        try:
            cur = conn.cursor()
            cur.execute(sql, tuple(args))
            result: list[dict[str, Any]] = []
            for (
                strat,
                n,
                n_synth,
                q50_mean,
                cost_mean,
                synth_edge_mean,
                first_ts,
                last_ts,
            ) in cur.fetchall():
                result.append(
                    {
                        "strategy_name": strat,
                        "n": int(n),
                        "n_with_synthetic": int(n_synth or 0),
                        "predicted_q50_mean": float(q50_mean) if q50_mean is not None else None,
                        "cost_bps_mean": float(cost_mean) if cost_mean is not None else None,
                        "synthetic_net_edge_bps_mean": (
                            float(synth_edge_mean) if synth_edge_mean is not None else None
                        ),
                        "first_ts_utc": first_ts.isoformat() if first_ts is not None else None,
                        "last_ts_utc": last_ts.isoformat() if last_ts is not None else None,
                    }
                )
            return result, None
        except Exception as exc:
            logger.warning("shadow_fills summary query failed: %s", exc)
            return [], f"pg_error:{type(exc).__name__}"


def _fetch_gate_counts(
    strategy: str,
    engine: str,
) -> tuple[int, int, str | None, str | None]:
    """Return (n_total, n_with_synthetic, first_ts_iso, last_ts_iso) for the gate.
    回傳 promotion gate 需要的統計。"""
    sql = """
        SELECT COUNT(*)                                 AS n,
               COUNT(synthetic_net_edge_bps)            AS n_synth,
               MIN(ts)                                  AS first_ts,
               MAX(ts)                                  AS last_ts
          FROM learning.decision_shadow_fills
         WHERE engine_mode = %s AND strategy_name = %s
    """

    with get_pg_conn() as conn:
        if conn is None:
            return 0, 0, None, None
        try:
            cur = conn.cursor()
            cur.execute(sql, (engine, strategy))
            row = cur.fetchone() or (0, 0, None, None)
            n, n_synth, first_ts, last_ts = row
            return (
                int(n or 0),
                int(n_synth or 0),
                first_ts.isoformat() if first_ts is not None else None,
                last_ts.isoformat() if last_ts is not None else None,
            )
        except Exception as exc:
            logger.warning("shadow_fills gate query failed: %s", exc)
            return 0, 0, None, None


@shadow_fills_router.get("")
async def list_shadow_fills(
    strategy: str | None = Query(default=None, description="Strategy filter; must be in whitelist / 策略名"),
    engine: str = Query(default="paper", description="engine_mode filter; DB pins to 'paper' / 引擎"),
    symbol: str | None = Query(default=None, max_length=32, description="Symbol filter / 幣種"),
    since: str | None = Query(default=None, description="ISO timestamp lower bound / 時間下界"),
    limit: int = Query(default=50, ge=1, le=500, description="Page size / 分頁大小"),
    offset: int = Query(default=0, ge=0, description="Page offset / 偏移量"),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """
    GET /api/v1/edge/shadow_fills

    Paginated list of ε-greedy shadow fills with optional filters.
    分頁列出 ε-greedy shadow fills，可依 strategy / symbol / since 篩選。

    Returns:
        ok (bool): always True at HTTP layer; see `degraded`.
        data.rows (list[dict]): shadow fill rows, most recent first.
        data.limit / data.offset: pagination echoes.
        data.degraded (bool): True when PG unavailable; data.rows will be [].
        data.reason (str | None): failure reason when degraded.
    """
    if engine not in _ALLOWED_ENGINES:
        raise HTTPException(
            status_code=400,
            detail=f"engine must be one of {_ALLOWED_ENGINES} / engine 須為白名單值",
        )
    if strategy is not None and strategy not in _ALLOWED_STRATEGIES:
        raise HTTPException(
            status_code=400,
            detail=f"strategy not in whitelist {sorted(_ALLOWED_STRATEGIES)} / 策略不在白名單",
        )

    rows, reason = _fetch_rows(strategy, engine, symbol, since, limit, offset)
    data = {
        "rows": rows,
        "limit": limit,
        "offset": offset,
        "filters": {
            "strategy": strategy,
            "engine": engine,
            "symbol": symbol,
            "since": since,
        },
        "degraded": reason is not None,
        "reason": reason,
    }
    return {
        "ok": True,
        "data": data,
        "is_simulated": False,
        "data_category": "edge_shadow_fills",
    }


@shadow_fills_router.get("/summary")
async def summary_shadow_fills(
    engine: str = Query(default="paper", description="engine_mode filter / 引擎"),
    since: str | None = Query(default=None, description="ISO timestamp lower bound / 時間下界"),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """
    GET /api/v1/edge/shadow_fills/summary

    Per-strategy aggregate: sample count, synthetic-label coverage, mean
    predicted q50 / cost / synthetic edge, and time range.
    每策略聚合（樣本數、synthetic 覆蓋、q50 / 成本 / synthetic edge 均值、時間區間）。
    """
    if engine not in _ALLOWED_ENGINES:
        raise HTTPException(
            status_code=400,
            detail=f"engine must be one of {_ALLOWED_ENGINES} / engine 須為白名單值",
        )

    strategies, reason = _fetch_summary(engine, since)
    # Zero-sample strategies are useful to the client (a UI row with n=0 is
    # more informative than a missing row), so we always echo every allowed
    # strategy and overlay real counts on top.
    # 零樣本策略也回傳（n=0），GUI 顯示比缺行更直觀。
    by_name = {row["strategy_name"]: row for row in strategies}
    merged: list[dict[str, Any]] = []
    for name in sorted(_ALLOWED_STRATEGIES):
        merged.append(by_name.get(name) or _empty_summary_row(name))
    # Any unexpected strategy surfaced by the DB (e.g. funding_arb_btc variant)
    # is appended at the end so it does not go silently dropped.
    # DB 若出現白名單外的 strategy_name 仍附加回傳，避免靜默遺失。
    for name, row in by_name.items():
        if name not in _ALLOWED_STRATEGIES:
            merged.append(row)

    data = {
        "by_strategy": merged,
        "filters": {"engine": engine, "since": since},
        "degraded": reason is not None,
        "reason": reason,
    }
    return {
        "ok": True,
        "data": data,
        "is_simulated": False,
        "data_category": "edge_shadow_fills_summary",
    }


@shadow_fills_router.get("/promotion_gate/{strategy}")
async def promotion_gate(
    strategy: str = Path(..., description="Strategy name (whitelisted) / 策略名"),
    engine: str = Query(default="paper", description="engine_mode filter / 引擎"),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """
    GET /api/v1/edge/shadow_fills/promotion_gate/{strategy}

    Shadow-fill Stage 2 ship-readiness probe (spec §8.3 acceptance line 714):
      * n ≥ 500 with synthetic labels → ship_prod_candidate
      * 200 ≤ n < 500 with synthetic labels → ship_shadow_candidate
      * n < 200 → insufficient_samples
      * Has rows but synthetic labels still NULL → awaiting_synthetic_labels
    Offline metric checks (pinball skill / coverage error / decile lift)
    are run by `run_training_pipeline.py`, not here — this endpoint only
    surfaces the sample-count tier.
    樣本數分級 + synthetic 覆蓋判定；離線指標由訓練管線裁決。
    """
    if engine not in _ALLOWED_ENGINES:
        raise HTTPException(
            status_code=400,
            detail=f"engine must be one of {_ALLOWED_ENGINES} / engine 須為白名單值",
        )
    if strategy not in _ALLOWED_STRATEGIES:
        raise HTTPException(
            status_code=400,
            detail=f"strategy not in whitelist {sorted(_ALLOWED_STRATEGIES)} / 策略不在白名單",
        )

    n_total, n_synth, first_ts, last_ts = _fetch_gate_counts(strategy, engine)
    verdict, next_action = _promotion_verdict(n_total, n_synth)
    data = {
        "strategy_name": strategy,
        "engine_mode": engine,
        "sample_count": n_total,
        "samples_with_synthetic": n_synth,
        "first_ts_utc": first_ts,
        "last_ts_utc": last_ts,
        "thresholds": {
            "ship_prod_min": _PROMOTION_SHIP_PROD_MIN,
            "ship_shadow_min": _PROMOTION_SHIP_SHADOW_MIN,
        },
        "verdict": verdict,
        "next_action": next_action,
    }
    return {
        "ok": True,
        "data": data,
        "is_simulated": False,
        "data_category": "edge_shadow_fills_promotion_gate",
    }
