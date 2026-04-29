"""Read-only OpportunityTracker producer for MLDE.

The Rust core has an OpportunityTracker implementation, but production Python
Strategist previously passed empty ``regret_data``. This module supplies a
small DB-backed read-only bridge: rejected opportunities are compared against
later decision outcomes and summarized as undertrading/overtrading/balanced.
"""

from __future__ import annotations

import logging
import math
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
_CACHE: dict[tuple[str, int, float], tuple[float, dict[str, Any]]] = {}


@dataclass(frozen=True)
class OpportunityConfig:
    engine_mode: str = "demo"
    lookback_hours: int = 24
    friction_bps: float = 11.0
    min_samples: int = 5
    ttl_s: float = 300.0


def config_from_env(engine_mode: str = "demo") -> OpportunityConfig:
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

    return OpportunityConfig(
        engine_mode=engine_mode,
        lookback_hours=max(1, _int("OPENCLAW_MLDE_OPPORTUNITY_LOOKBACK_HOURS", 24)),
        friction_bps=max(0.0, _float("OPENCLAW_MLDE_OPPORTUNITY_FRICTION_BPS", 11.0)),
        min_samples=max(1, _int("OPENCLAW_MLDE_OPPORTUNITY_MIN_SAMPLES", 5)),
        ttl_s=max(5.0, _float("OPENCLAW_MLDE_OPPORTUNITY_TTL_S", 300.0)),
    )


def _resolve_dsn(dsn: Optional[str]) -> Optional[str]:
    return dsn or os.environ.get("OPENCLAW_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _engine_mode_scope(engine_mode: str) -> tuple[str, ...]:
    if engine_mode not in VALID_ENGINE_MODES:
        raise ValueError(f"invalid engine_mode: {engine_mode!r}")
    if engine_mode == "live":
        return ("live", "live_demo")
    return (engine_mode,)


def _safe_direction(side: str | None) -> int:
    return -1 if str(side or "").lower() in ("sell", "short") else 1


def summarize_rejected_outcomes(rows: list[dict[str, Any]], cfg: OpportunityConfig) -> dict[str, Any]:
    """Pure regret/dodge classifier from rejected opportunity outcome rows."""
    regrets: list[float] = []
    dodged: list[float] = []
    by_strategy: dict[str, dict[str, Any]] = {}

    for row in rows:
        raw = row.get("outcome_1h")
        if raw is None:
            raw = row.get("outcome_5m")
        if raw is None:
            raw = row.get("outcome_1m")
        if raw is None:
            continue
        strategy = str(row.get("strategy_name") or "unknown")
        directional_bps = float(raw) * 10_000.0 * _safe_direction(row.get("side"))
        net_bps = directional_bps - cfg.friction_bps
        bucket = by_strategy.setdefault(strategy, {"n": 0, "regret_bps": 0.0, "dodged_bps": 0.0})
        bucket["n"] += 1
        if net_bps > 0.0:
            regrets.append(net_bps)
            bucket["regret_bps"] += net_bps
        else:
            dodged.append(net_bps)
            bucket["dodged_bps"] += net_bps

    n = len(regrets) + len(dodged)
    avg_regret = sum(regrets) / len(regrets) if regrets else 0.0
    avg_dodged = sum(dodged) / len(dodged) if dodged else 0.0
    if n < cfg.min_samples:
        direction = "balanced"
    elif len(regrets) >= max(2, math.ceil(len(dodged) * 1.25)) and avg_regret > abs(avg_dodged):
        direction = "undertrading"
    elif len(dodged) >= max(2, math.ceil(len(regrets) * 1.25)):
        direction = "overtrading"
    else:
        direction = "balanced"

    top_strategy = None
    if by_strategy:
        top_strategy = max(by_strategy.items(), key=lambda item: item[1]["n"])[0]

    return {
        "net_regret_direction": direction,
        "rejected_sample_count": n,
        "regret_count": len(regrets),
        "dodged_count": len(dodged),
        "avg_regret_bps": round(avg_regret, 4),
        "avg_dodged_bps": round(avg_dodged, 4),
        "top_strategy": top_strategy,
        "by_strategy": by_strategy,
        "_meta": {
            "source": "opportunity_tracker",
            "engine_mode": cfg.engine_mode,
            "lookback_hours": cfg.lookback_hours,
            "friction_bps": cfg.friction_bps,
            "min_samples": cfg.min_samples,
            "policy": "read_only_advisory",
        },
    }


def _fetch_rejected_rows(dsn: str, cfg: OpportunityConfig) -> list[dict[str, Any]]:
    if psycopg2 is None:
        raise RuntimeError("psycopg2 not installed")
    sql = """
        SELECT
            rv.engine_mode,
            rv.context_id,
            rv.symbol,
            rv.verdict,
            rv.reason,
            i.strategy_name,
            i.side,
            o.outcome_1m,
            o.outcome_5m,
            o.outcome_1h
        FROM trading.risk_verdicts rv
        JOIN trading.intents i
          ON i.intent_id = rv.intent_id
         AND i.engine_mode = rv.engine_mode
        LEFT JOIN trading.decision_outcomes o
          ON o.context_id = rv.context_id
        WHERE rv.engine_mode = ANY(%s)
          AND rv.ts >= now() - (%s::int || ' hours')::interval
          AND lower(rv.verdict) LIKE 'reject%%'
          AND COALESCE(i.details->>'source', '') <> 'command'
        ORDER BY rv.ts DESC
        LIMIT 500
    """
    with psycopg2.connect(dsn, connect_timeout=2) as conn:  # pragma: no cover - DB path
        with conn.cursor() as cur:
            cur.execute(sql, (list(_engine_mode_scope(cfg.engine_mode)), cfg.lookback_hours))
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_recent_regret_summary(
    dsn: Optional[str] = None,
    *,
    engine_mode: str = "demo",
    cfg: Optional[OpportunityConfig] = None,
) -> dict[str, Any]:
    cfg = cfg or config_from_env(engine_mode)
    resolved_dsn = _resolve_dsn(dsn)
    if not resolved_dsn:
        return {}
    cache_key = (cfg.engine_mode, cfg.lookback_hours, cfg.friction_bps)
    now = time.time()
    cached = _CACHE.get(cache_key)
    if cached and now - cached[0] < cfg.ttl_s:
        return cached[1]
    try:
        rows = _fetch_rejected_rows(resolved_dsn, cfg)
        summary = summarize_rejected_outcomes(rows, cfg)
    except Exception as exc:  # noqa: BLE001
        logger.debug("opportunity tracker unavailable: %s", exc)
        summary = {}
    _CACHE[cache_key] = (now, summary)
    return summary


def persist_regret_summary(
    dsn: Optional[str] = None,
    *,
    engine_mode: str = "demo",
    cfg: Optional[OpportunityConfig] = None,
) -> dict[str, Any]:
    cfg = cfg or config_from_env(engine_mode)
    resolved_dsn = _resolve_dsn(dsn)
    if not resolved_dsn:
        return {"skipped": "no_database_url", "inserted": 0}
    summary = get_recent_regret_summary(resolved_dsn, engine_mode=engine_mode, cfg=cfg)
    if not summary:
        return {"inserted": 0, "summary": {}}
    if psycopg2 is None or Json is None:
        raise RuntimeError("psycopg2 not installed")
    with psycopg2.connect(resolved_dsn, connect_timeout=2) as conn:  # pragma: no cover - DB path
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO learning.mlde_shadow_recommendations
                    (engine_mode, source, recommendation_type, primary_metric,
                     expected_net_bps, confidence, sample_count, payload,
                     applied, requires_governance, created_by)
                VALUES
                    (%s, 'opportunity_tracker', 'regret_summary', 'net_bps_after_fee',
                     %s, %s, %s, %s, false, true, 'mlde_opportunity_tracker')
                """,
                (
                    cfg.engine_mode,
                    summary.get("avg_regret_bps", 0.0),
                    min(0.85, (summary.get("rejected_sample_count", 0) or 0) / 50.0),
                    summary.get("rejected_sample_count", 0),
                    Json(summary),
                ),
            )
        conn.commit()
    return {"inserted": 1, "summary": summary}
