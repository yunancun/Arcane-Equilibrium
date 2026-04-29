"""MLDE shadow advisor.

Reads the V031 ML/Dream edge-unblock training view and emits advisory
rank/veto rows into ``learning.mlde_shadow_recommendations``.

This module is deliberately not an execution path. Rows are logged with
``applied=false`` and ``requires_governance=true`` so downstream promotion can
be audited separately.
"""

from __future__ import annotations

import json
import logging
import math
import os
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


@dataclass(frozen=True)
class ShadowAdvisorConfig:
    engine_mode: str = "demo"
    lookback_hours: int = 168
    min_samples: int = 5
    positive_rank_bps: float = 2.0
    negative_veto_bps: float = -2.0
    reward_scale_bps: float = 100.0
    confidence_cap: float = 0.85
    max_recommendations: int = 64


@dataclass(frozen=True)
class ShadowRecommendation:
    engine_mode: str
    source: str
    recommendation_type: str
    strategy_name: str
    symbol: Optional[str]
    expected_net_bps: float
    confidence: float
    sample_count: int
    payload: dict[str, Any]


def config_from_env(engine_mode: str = "demo") -> ShadowAdvisorConfig:
    """Build tunable defaults from env vars.

    Agents can tune these without code edits:
      OPENCLAW_MLDE_SHADOW_LOOKBACK_HOURS
      OPENCLAW_MLDE_SHADOW_MIN_SAMPLES_<ENGINE_MODE>
      OPENCLAW_MLDE_SHADOW_MIN_SAMPLES
      OPENCLAW_MLDE_SHADOW_POSITIVE_RANK_BPS
      OPENCLAW_MLDE_SHADOW_NEGATIVE_VETO_BPS
      OPENCLAW_MLDE_SHADOW_CONFIDENCE_CAP
      OPENCLAW_MLDE_SHADOW_MAX_RECOMMENDATIONS
    """

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
    return ShadowAdvisorConfig(
        engine_mode=engine_mode,
        lookback_hours=max(1, _int("OPENCLAW_MLDE_SHADOW_LOOKBACK_HOURS", 168)),
        min_samples=max(
            1,
            _mode_int("OPENCLAW_MLDE_SHADOW_MIN_SAMPLES", min_samples_default),
        ),
        positive_rank_bps=_float("OPENCLAW_MLDE_SHADOW_POSITIVE_RANK_BPS", 2.0),
        negative_veto_bps=_float("OPENCLAW_MLDE_SHADOW_NEGATIVE_VETO_BPS", -2.0),
        confidence_cap=max(0.05, min(1.0, _float("OPENCLAW_MLDE_SHADOW_CONFIDENCE_CAP", 0.85))),
        max_recommendations=max(1, _int("OPENCLAW_MLDE_SHADOW_MAX_RECOMMENDATIONS", 64)),
    )


def _resolve_dsn(dsn: Optional[str]) -> Optional[str]:
    return dsn or os.environ.get("OPENCLAW_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _engine_mode_scope(engine_mode: str) -> tuple[str, ...]:
    if engine_mode not in VALID_ENGINE_MODES:
        raise ValueError(f"invalid engine_mode: {engine_mode!r}")
    if engine_mode == "live":
        return ("live", "live_demo")
    return (engine_mode,)


def _confidence(sample_count: int, avg_bps: float, cfg: ShadowAdvisorConfig) -> float:
    sample_term = math.sqrt(sample_count / (sample_count + cfg.min_samples * 4.0))
    edge_term = min(1.0, abs(avg_bps) / max(abs(cfg.positive_rank_bps), abs(cfg.negative_veto_bps), 1.0))
    return round(min(cfg.confidence_cap, max(0.05, sample_term * edge_term)), 4)


def build_recommendations(
    aggregate_rows: list[dict[str, Any]],
    cfg: ShadowAdvisorConfig,
) -> list[ShadowRecommendation]:
    """Pure recommendation builder from aggregate SQL rows."""
    recommendations: list[ShadowRecommendation] = []
    for row in aggregate_rows:
        n = int(row.get("sample_count") or 0)
        if n < cfg.min_samples:
            continue
        avg_bps = float(row.get("avg_net_bps") or 0.0)
        if avg_bps >= cfg.positive_rank_bps:
            rec_type = "rank"
        elif avg_bps <= cfg.negative_veto_bps:
            rec_type = "veto"
        else:
            continue

        payload = {
            "arm_id": row.get("mlde_arm_id"),
            "linucb_arm_id": row.get("linucb_arm_id"),
            "strategy_name": row.get("strategy_name"),
            "symbol_bucket": row.get("symbol_bucket"),
            "regime": row.get("regime"),
            "scanner_route_mode": row.get("scanner_route_mode"),
            "scanner_edge_status": row.get("scanner_edge_status"),
            "avg_net_bps": avg_bps,
            "win_rate": row.get("win_rate"),
            "sample_count": n,
            "reward_scale_bps": cfg.reward_scale_bps,
            "policy": "shadow_advisory_only",
        }
        recommendations.append(
            ShadowRecommendation(
                engine_mode=str(row.get("engine_mode") or cfg.engine_mode),
                source="ml_shadow",
                recommendation_type=rec_type,
                strategy_name=str(row.get("strategy_name") or "unknown"),
                symbol=None,
                expected_net_bps=avg_bps,
                confidence=_confidence(n, avg_bps, cfg),
                sample_count=n,
                payload=payload,
            )
        )
    return sorted(
        recommendations,
        key=lambda r: (abs(r.expected_net_bps), r.sample_count, r.confidence),
        reverse=True,
    )[: cfg.max_recommendations]


def _fetch_aggregate_rows(dsn: str, cfg: ShadowAdvisorConfig) -> list[dict[str, Any]]:
    if psycopg2 is None:
        raise RuntimeError("psycopg2 not installed")
    sql = """
        SELECT
            engine_mode,
            strategy_name,
            symbol_bucket,
            regime,
            scanner_route_mode,
            scanner_edge_status,
            mlde_arm_id,
            linucb_arm_id,
            count(*)::int AS sample_count,
            avg(net_bps_after_fee)::float8 AS avg_net_bps,
            avg(CASE WHEN net_bps_after_fee > 0 THEN 1.0 ELSE 0.0 END)::float8 AS win_rate
        FROM learning.mlde_edge_training_rows
        WHERE engine_mode = ANY(%s)
          AND attribution_chain_ok
          AND net_bps_after_fee IS NOT NULL
          AND ts >= now() - (%s::int || ' hours')::interval
        GROUP BY
            engine_mode, strategy_name, symbol_bucket, regime,
            scanner_route_mode, scanner_edge_status, mlde_arm_id, linucb_arm_id
        HAVING count(*) >= %s
        ORDER BY abs(avg(net_bps_after_fee)) DESC, count(*) DESC
        LIMIT %s
    """
    with psycopg2.connect(dsn, connect_timeout=2) as conn:  # pragma: no cover - DB path
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    list(_engine_mode_scope(cfg.engine_mode)),
                    cfg.lookback_hours,
                    cfg.min_samples,
                    cfg.max_recommendations,
                ),
            )
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def _persist_recommendations(dsn: str, recommendations: list[ShadowRecommendation]) -> int:
    if not recommendations:
        return 0
    if psycopg2 is None or Json is None:
        raise RuntimeError("psycopg2 not installed")
    sql = """
        INSERT INTO learning.mlde_shadow_recommendations
            (engine_mode, symbol, strategy_name, source, recommendation_type,
             primary_metric, expected_net_bps, confidence, sample_count, payload,
             applied, requires_governance, created_by)
        VALUES
            (%s, %s, %s, %s, %s, 'net_bps_after_fee', %s, %s, %s, %s,
             false, true, 'mlde_shadow_advisor')
    """
    with psycopg2.connect(dsn, connect_timeout=2) as conn:  # pragma: no cover - DB path
        with conn.cursor() as cur:
            for rec in recommendations:
                cur.execute(
                    sql,
                    (
                        rec.engine_mode,
                        rec.symbol,
                        rec.strategy_name,
                        rec.source,
                        rec.recommendation_type,
                        rec.expected_net_bps,
                        rec.confidence,
                        rec.sample_count,
                        Json(rec.payload),
                    ),
                )
        conn.commit()
    return len(recommendations)


def generate_shadow_recommendations(
    dsn: Optional[str] = None,
    cfg: Optional[ShadowAdvisorConfig] = None,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Generate and optionally persist shadow recommendations.

    Returns a compact summary suitable for scheduler status payloads.
    """
    cfg = cfg or config_from_env()
    resolved_dsn = _resolve_dsn(dsn)
    if not resolved_dsn:
        return {"skipped": "no_database_url", "inserted": 0, "recommendations": 0}
    rows = _fetch_aggregate_rows(resolved_dsn, cfg)
    recs = build_recommendations(rows, cfg)
    inserted = 0 if dry_run else _persist_recommendations(resolved_dsn, recs)
    return {
        "engine_mode": cfg.engine_mode,
        "aggregate_rows": len(rows),
        "recommendations": len(recs),
        "inserted": inserted,
        "dry_run": dry_run,
    }


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    summary = generate_shadow_recommendations()
    print(json.dumps(summary, indent=2, sort_keys=True))
