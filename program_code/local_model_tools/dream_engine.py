"""Read-only DreamEngine producer for MLDE.

This is a narrow production bridge around the current edge-repair questions:
grid spacing, MA whipsaw hold-time, BB breakout threshold/timeframe, and maker
timeout. It emits parameter proposals as advisory data only.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

try:
    import psycopg2  # type: ignore
    from psycopg2.extras import Json  # type: ignore
except ImportError:  # pragma: no cover - runtime DB path only
    psycopg2 = None  # type: ignore[assignment]
    Json = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

VALID_ENGINE_MODES = ("paper", "demo", "live", "live_demo")
_CACHE: dict[tuple[str, int, int, float], tuple[float, dict[str, Any]]] = {}
SCANNER_TEXT_FIELDS = (
    "scanner_market_regime",
    "scanner_trend_phase",
)
SCANNER_NUMERIC_FIELDS = (
    "scanner_trend_score",
    "scanner_range_score",
    "scanner_shock_score",
    "scanner_close_alignment",
    "scanner_range_position",
    "scanner_crowding_score",
    "scanner_reversal_risk_score",
    "scanner_directional_efficiency",
    "scanner_dir_pct",
    "scanner_signed_dir_pct",
    "scanner_range_pct",
    "scanner_fr_bps",
    "scanner_f_ma",
    "scanner_f_grid",
    "scanner_f_bbrv",
    "scanner_f_bkout",
    "scanner_f_funding_arb",
)
SCANNER_CONTEXT_FIELDS = SCANNER_TEXT_FIELDS + SCANNER_NUMERIC_FIELDS


@dataclass(frozen=True)
class DreamConfig:
    engine_mode: str = "demo"
    lookback_hours: int = 168
    min_samples: int = 5
    negative_edge_bps: float = -2.0
    max_insights: int = 12
    ttl_s: float = 300.0


def config_from_env(engine_mode: str = "demo") -> DreamConfig:
    def _int(name: str, default: int) -> int:
        try:
            return int(os.environ.get(name, str(default)))
        except ValueError:
            return default

    def _float(name: str, default: float) -> float:
        try:
            return float(os.environ.get(name, str(default)))
        except ValueError:
            return default

    def _mode_key(name: str) -> str:
        return f"{name}_{engine_mode.upper().replace('-', '_')}"

    def _mode_int(name: str, default: int) -> int:
        mode_name = _mode_key(name)
        if mode_name in os.environ:
            return _int(mode_name, default)
        return _int(name, default)

    min_samples_default = 3 if engine_mode == "demo" else 5
    return DreamConfig(
        engine_mode=engine_mode,
        lookback_hours=max(1, _int("OPENCLAW_MLDE_DREAM_LOOKBACK_HOURS", 168)),
        min_samples=max(
            1,
            _mode_int("OPENCLAW_MLDE_DREAM_MIN_SAMPLES", min_samples_default),
        ),
        negative_edge_bps=_float("OPENCLAW_MLDE_DREAM_NEGATIVE_EDGE_BPS", -2.0),
        max_insights=max(1, _int("OPENCLAW_MLDE_DREAM_MAX_INSIGHTS", 12)),
        ttl_s=max(5.0, _float("OPENCLAW_MLDE_DREAM_TTL_S", 300.0)),
    )


def _resolve_dsn(dsn: Optional[str]) -> Optional[str]:
    return dsn or os.environ.get("OPENCLAW_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _engine_mode_scope(engine_mode: str) -> tuple[str, ...]:
    if engine_mode not in VALID_ENGINE_MODES:
        raise ValueError(f"invalid engine_mode: {engine_mode!r}")
    if engine_mode == "live":
        return ("live", "live_demo")
    return (engine_mode,)


def _confidence(n: int, cfg: DreamConfig) -> float:
    return round(min(0.85, max(0.05, n / max(cfg.min_samples * 8.0, 1.0))), 4)


def _proposal_for_strategy(strategy: str, avg_bps: float) -> dict[str, Any]:
    if strategy == "grid_trading":
        return {
            "param_name": "grid_spacing_bps",
            "suggested_change_pct": 0.25,
            "direction": "widen",
            "question": "grid spacing vs fee drag and chop",
        }
    if strategy == "ma_crossover":
        return {
            "param_name": "min_hold_seconds",
            "suggested_change_pct": 0.50,
            "direction": "lengthen",
            "question": "MA whipsaw hold-time filter",
        }
    if strategy == "bb_breakout":
        return {
            "param_name": "volume_threshold",
            "suggested_change_pct": 0.20 if avg_bps < 0.0 else 0.0,
            "direction": "raise_or_shift_to_5m",
            "question": "BB breakout threshold/timeframe repair",
        }
    if strategy == "bb_reversion":
        return {
            "param_name": "exit_conf_base",
            "suggested_change_pct": 0.10,
            "direction": "tighten_exit_quality",
            "question": "BB reversion adverse excursion control",
        }
    if strategy == "funding_arb":
        return {
            "param_name": "min_funding_edge_bps",
            "suggested_change_pct": 0.20,
            "direction": "raise",
            "question": "funding edge after taker/maker costs",
        }
    return {
        "param_name": "confidence_threshold",
        "suggested_change_pct": 0.05,
        "direction": "raise",
        "question": "generic negative-edge threshold repair",
    }


def build_dream_summary(rows: list[dict[str, Any]], cfg: DreamConfig) -> dict[str, Any]:
    insights: list[dict[str, Any]] = []
    total_n = 0
    weighted_bps = 0.0
    for row in rows:
        n = int(row.get("sample_count") or 0)
        avg_bps = float(row.get("avg_net_bps") or 0.0)
        total_n += n
        weighted_bps += avg_bps * n
        if n < cfg.min_samples or avg_bps > cfg.negative_edge_bps:
            continue
        strategy = str(row.get("strategy_name") or "unknown")
        proposal = _proposal_for_strategy(strategy, avg_bps)
        conf = _confidence(n, cfg)
        insight = {
            "strategy_name": strategy,
            "symbol_bucket": row.get("symbol_bucket"),
            "regime": row.get("regime"),
            "scanner_route_mode": row.get("scanner_route_mode"),
            "scanner_edge_status": row.get("scanner_edge_status"),
            "sample_count": n,
            "current_avg_net_bps": round(avg_bps, 4),
            "expected_improvement_bps": round(abs(avg_bps) * min(0.5, conf), 4),
            "confidence": conf,
            **proposal,
            "policy": "read_only_parameter_proposal",
        }
        scanner_context = _scanner_context_from_row(row)
        if scanner_context:
            insight["scanner_context"] = scanner_context
        insights.append(insight)

    insights = sorted(
        insights,
        key=lambda item: (abs(float(item["current_avg_net_bps"])), int(item["sample_count"])),
        reverse=True,
    )[: cfg.max_insights]
    overall_avg = weighted_bps / total_n if total_n else 0.0
    global_conf = _confidence(total_n, cfg) if total_n else 0.0
    return {
        "_meta": {
            "source": "dream_engine",
            "engine_mode": cfg.engine_mode,
            "lookback_hours": cfg.lookback_hours,
            "min_samples": cfg.min_samples,
            "negative_edge_bps": cfg.negative_edge_bps,
            "policy": "read_only_advisory",
        },
        "global": {
            "sample_count": total_n,
            "avg_net_bps": round(overall_avg, 4),
            "confidence": global_conf,
            "stoploss_multiplier": 0.9 if overall_avg < cfg.negative_edge_bps and global_conf > 0.6 else None,
        },
        "insights": insights,
    }


def _fetch_aggregate_rows(dsn: str, cfg: DreamConfig) -> list[dict[str, Any]]:
    if psycopg2 is None:
        raise RuntimeError("psycopg2 not installed")
    with psycopg2.connect(dsn, connect_timeout=2) as conn:  # pragma: no cover - DB path
        with conn.cursor() as cur:
            available_columns = _fetch_training_view_columns(cur)
            scanner_selects = _scanner_context_select_sql(available_columns)
            sql = f"""
        SELECT
            strategy_name,
            symbol_bucket,
            regime,
            scanner_route_mode,
            scanner_edge_status,
            {scanner_selects},
            count(*)::int AS sample_count,
            avg(net_bps_after_fee)::float8 AS avg_net_bps
        FROM learning.mlde_edge_training_rows
        WHERE engine_mode = ANY(%s)
          AND attribution_chain_ok
          AND net_bps_after_fee IS NOT NULL
          AND ts >= now() - (%s::int || ' hours')::interval
        GROUP BY strategy_name, symbol_bucket, regime, scanner_route_mode, scanner_edge_status
        HAVING count(*) >= %s
        ORDER BY avg(net_bps_after_fee) ASC, count(*) DESC
        LIMIT %s
    """
            cur.execute(
                sql,
                (
                    list(_engine_mode_scope(cfg.engine_mode)),
                    cfg.lookback_hours,
                    cfg.min_samples,
                    cfg.max_insights * 4,
                ),
            )
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def _fetch_training_view_columns(cur: Any) -> set[str]:
    """Return available columns on the MLDE training view.

    回傳 MLDE training view 目前可用欄位，用於跨 migration 相容。
    """
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'learning'
          AND table_name = 'mlde_edge_training_rows'
        """
    )
    return {str(row[0]) for row in (cur.fetchall() or [])}


def _scanner_context_select_sql(available_columns: set[str]) -> str:
    """Build scanner-context aggregate SQL with missing-column fallbacks.

    建立 scanner context 彙總 SQL；欄位尚未 migration 時使用 NULL fallback。
    """
    selects: list[str] = []
    for field in SCANNER_TEXT_FIELDS:
        if field in available_columns:
            selects.append(f"max({field}) AS {field}")
        else:
            selects.append(f"NULL::text AS {field}")
    for field in SCANNER_NUMERIC_FIELDS:
        if field in available_columns:
            selects.append(f"avg({field})::float8 AS {field}")
        else:
            selects.append(f"NULL::float8 AS {field}")
    return ",\n            ".join(selects)


def _scanner_context_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """Extract non-null scanner context fields from an aggregate row.

    從彙總 row 提取非空 scanner context 欄位。
    """
    return {
        field: row[field]
        for field in SCANNER_CONTEXT_FIELDS
        if row.get(field) is not None
    }


def get_latest_dream_summary(
    dsn: Optional[str] = None,
    *,
    engine_mode: str = "demo",
    cfg: Optional[DreamConfig] = None,
) -> dict[str, Any]:
    cfg = cfg or config_from_env(engine_mode)
    resolved_dsn = _resolve_dsn(dsn)
    if not resolved_dsn:
        return {}
    cache_key = (cfg.engine_mode, cfg.lookback_hours, cfg.min_samples, cfg.negative_edge_bps)
    now = time.time()
    cached = _CACHE.get(cache_key)
    if cached and now - cached[0] < cfg.ttl_s:
        return cached[1]
    try:
        rows = _fetch_aggregate_rows(resolved_dsn, cfg)
        summary = build_dream_summary(rows, cfg)
    except Exception as exc:  # noqa: BLE001
        logger.debug("dream engine unavailable: %s", exc)
        summary = {}
    _CACHE[cache_key] = (now, summary)
    return summary


def persist_dream_insights(
    dsn: Optional[str] = None,
    *,
    engine_mode: str = "demo",
    cfg: Optional[DreamConfig] = None,
) -> dict[str, Any]:
    cfg = cfg or config_from_env(engine_mode)
    resolved_dsn = _resolve_dsn(dsn)
    if not resolved_dsn:
        return {"skipped": "no_database_url", "inserted": 0}
    summary = get_latest_dream_summary(resolved_dsn, engine_mode=engine_mode, cfg=cfg)
    insights = list(summary.get("insights") or [])
    if not insights:
        return {"inserted": 0, "insights": 0}
    if psycopg2 is None or Json is None:
        raise RuntimeError("psycopg2 not installed")
    with psycopg2.connect(resolved_dsn, connect_timeout=2) as conn:  # pragma: no cover - DB path
        with conn.cursor() as cur:
            for insight in insights:
                cur.execute(
                    """
                    INSERT INTO learning.mlde_shadow_recommendations
                        (engine_mode, strategy_name, source, recommendation_type,
                         primary_metric, expected_net_bps, confidence, sample_count,
                         payload, applied, requires_governance, created_by)
                    VALUES
                        (%s, %s, 'dream_engine', 'parameter_proposal',
                         'net_bps_after_fee', %s, %s, %s, %s,
                         false, true, 'mlde_dream_engine')
                    """,
                    (
                        cfg.engine_mode,
                        insight.get("strategy_name"),
                        insight.get("expected_improvement_bps"),
                        insight.get("confidence"),
                        insight.get("sample_count"),
                        Json(insight),
                    ),
                )
        conn.commit()
    return {"inserted": len(insights), "insights": len(insights)}
