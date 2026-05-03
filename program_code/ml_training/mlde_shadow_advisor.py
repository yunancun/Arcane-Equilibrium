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
        scanner_context = _scanner_context_from_row(row)
        if scanner_context:
            payload["scanner_context"] = scanner_context
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
    with psycopg2.connect(dsn, connect_timeout=2) as conn:  # pragma: no cover - DB path
        with conn.cursor() as cur:
            available_columns = _fetch_training_view_columns(cur)
            scanner_selects = _scanner_context_select_sql(available_columns)
            sql = f"""
        SELECT
            engine_mode,
            strategy_name,
            symbol_bucket,
            regime,
            scanner_route_mode,
            scanner_edge_status,
            mlde_arm_id,
            linucb_arm_id,
            {scanner_selects},
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


def _persist_recommendations(dsn: str, recommendations: list[ShadowRecommendation]) -> int:
    if not recommendations:
        return 0
    if psycopg2 is None or Json is None:
        raise RuntimeError("psycopg2 not installed")
    # REF-20 W3-P2a-S4: 切換到 verified insert function (V036).
    # PR2 of 3-PR sequence: mlde_shadow_advisor 不再直接 INSERT；改呼叫
    # learning.verify_replay_evidence_and_insert()。注意此處 rec.source /
    # rec.recommendation_type / rec.engine_mode 皆為變量 (從 ShadowRecommendation
    # dataclass 帶入)；verified function arg 接受 source ∈ {ml_shadow,
    # dream_engine, opportunity_tracker, linucb}，與 V031 schema CHECK 對齊。
    # rows 全為 `evidence_source_tier='real_outcome'` (legacy producer path)。
    #
    # REF-20 W3-P2a-S4: switch to verified insert function (V036).
    # PR2 of 3-PR sequence: mlde_shadow_advisor no longer issues raw INSERT.
    # Calls learning.verify_replay_evidence_and_insert() instead. Note:
    # rec.source / rec.recommendation_type / rec.engine_mode are variable
    # (sourced from ShadowRecommendation dataclass). The verified function
    # accepts source from the V031 CHECK allowlist; rows remain
    # `evidence_source_tier='real_outcome'` (legacy producer).
    sql = """
        SELECT learning.verify_replay_evidence_and_insert(
            %s,                             -- p_engine_mode
            %s,                             -- p_symbol
            %s,                             -- p_strategy_name
            %s,                             -- p_source (rec.source)
            %s,                             -- p_recommendation_type (rec.recommendation_type)
            %s,                             -- p_expected_net_bps
            %s,                             -- p_confidence
            %s,                             -- p_sample_count
            %s,                             -- p_payload
            false,                          -- p_applied
            true,                           -- p_requires_governance
            'mlde_shadow_advisor',          -- p_created_by
            'real_outcome',                 -- p_evidence_source_tier
            NULL, NULL, NULL,               -- replay metadata (NULL for real_outcome)
            NULL, NULL, NULL                -- decision_lease_id / context_id / intent_id
        )
    """
    inserted = 0
    with psycopg2.connect(dsn, connect_timeout=2) as conn:  # pragma: no cover - DB path
        with conn.cursor() as cur:
            for rec in recommendations:
                try:
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
                    inserted += 1
                except psycopg2.Error as exc:  # noqa: BLE001
                    # verified function reject: log and continue.
                    # function reject 拒絕：記 log 後繼續下一筆。
                    logger.warning(
                        "mlde_shadow_advisor: verify_replay_evidence_and_insert rejected rec=%s/%s err=%s",
                        rec.strategy_name,
                        rec.source,
                        exc,
                    )
        conn.commit()
    return inserted


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
