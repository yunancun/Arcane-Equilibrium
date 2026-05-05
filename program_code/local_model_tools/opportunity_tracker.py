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
from typing import Any, Callable, Optional

# REF-20 Sprint C2 R7-T3：calibrated_replay tier 升級。Optional import 模式
# （避免未上線環境載入 replay 模組失敗）；caller 不傳 R6_calibration_provider
# 時退回 legacy 'real_outcome' fallback path（backward-compat）。
try:  # pragma: no cover - import guard
    from program_code.exchange_connectors.bybit_connector.control_api_v1.replay.calibration_label import (
        CalibrationResult,
    )
    from program_code.local_model_tools.replay_metadata_helper import (
        build_replay_metadata,
    )

    _R7_HELPER_AVAILABLE = True
except ImportError:  # pragma: no cover - fallback when replay subsystem 未上線
    CalibrationResult = None  # type: ignore[assignment, misc]
    build_replay_metadata = None  # type: ignore[assignment]
    _R7_HELPER_AVAILABLE = False

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
    R6_calibration_provider: Optional[
        Callable[[Optional[str], Optional[str]], "CalibrationResult"]
    ] = None,
    replay_experiment_id: Optional[str] = None,
) -> dict[str, Any]:
    """REF-20 Sprint C2 R7-T3：升級為 calibrated_replay tier-aware insert。

    Backward-compat (per AI-E advisory §10 risk #7)：
      - 不傳 ``R6_calibration_provider`` → 走 legacy 'real_outcome' fallback。
      - 傳 provider + replay_experiment_id → 取 ``CalibrationResult``：
        * NONE → skip（回 inserted=0）；
        * LIMITED / CALIBRATED → 寫 'calibrated_replay' tier + 4-tuple
          metadata。

    Args:
        dsn: PG dsn (None → env fallback)。
        engine_mode: paper / demo / live_demo / live。
        cfg: optional override config。
        R6_calibration_provider: optional callable
            ``(strategy=None, symbol=None) → CalibrationResult``。Caller 必
            提供 strategy=None / symbol=None 也能 derive 的 provider（regret
            是 engine_mode-wide aggregates，無 per-strategy/per-symbol scope）。
        replay_experiment_id: optional V049 row UUID 對應 R7 path；caller
            負責綁定 cycle 對應的 experiment_id。
    """
    cfg = cfg or config_from_env(engine_mode)
    resolved_dsn = _resolve_dsn(dsn)
    if not resolved_dsn:
        return {"skipped": "no_database_url", "inserted": 0}
    summary = get_recent_regret_summary(resolved_dsn, engine_mode=engine_mode, cfg=cfg)
    if not summary:
        return {"inserted": 0, "summary": {}}
    # MIT-S2-6: Skip noise rows — regret_summary with sample_count below
    # cfg.min_samples carries no actionable rejection signal and pollutes
    # learning.mlde_shadow_recommendations (~48 NULL/zero-confidence rows/day),
    # diluting downstream applier filters. Persist only when we have a
    # statistically meaningful sample.
    # MIT-S2-6：跳過 noise row — sample_count 低於 cfg.min_samples 的 regret_summary
    # 無實質拒絕信號，會以零信心污染 mlde_shadow_recommendations（~48 row/天），
    # 稀釋下游 applier filter；僅在樣本量有統計意義時才寫入。
    sample_count = int(summary.get("rejected_sample_count", 0) or 0)
    if sample_count < cfg.min_samples:
        return {
            "inserted": 0,
            "skipped": "below_min_samples",
            "sample_count": sample_count,
            "min_samples": cfg.min_samples,
            "summary": summary,
        }
    if psycopg2 is None or Json is None:
        raise RuntimeError("psycopg2 not installed")

    # R7-T3: 判斷 calibrated_replay path 還是 legacy real_outcome path
    use_r7_path = (
        R6_calibration_provider is not None
        and replay_experiment_id is not None
        and _R7_HELPER_AVAILABLE
        and build_replay_metadata is not None
    )

    inserted = 0
    skipped_none_label = 0
    calibrated_inserted = 0

    with psycopg2.connect(resolved_dsn, connect_timeout=2) as conn:  # pragma: no cover - DB path
        with conn.cursor() as cur:
            # R7-T3 metadata 構造（fail-soft）
            tier_arg = "real_outcome"
            replay_experiment_id_arg: Optional[str] = None
            manifest_hash_arg: Optional[str] = None
            expires_at_arg: Optional[Any] = None

            should_insert = True
            if use_r7_path:
                try:
                    # regret 是 engine_mode-wide aggregate；strategy=None
                    # symbol=None 傳給 provider。
                    cal_result = R6_calibration_provider(None, None)  # type: ignore[misc]
                    if cal_result is None:
                        tier_arg = "real_outcome"
                    else:
                        metadata = build_replay_metadata(
                            experiment_id=replay_experiment_id,  # type: ignore[arg-type]
                            calibration_result=cal_result,
                            cur=cur,
                        )
                        if metadata is None:
                            # NONE label / V049 missing → skip insert
                            should_insert = False
                            skipped_none_label += 1
                        else:
                            tier_arg, replay_experiment_id_arg, manifest_hash_arg, expires_at_arg = metadata
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "opportunity_tracker R7: provider/helper 異常 → "
                        "fallback real_outcome (err=%s)",
                        exc,
                    )
                    tier_arg = "real_outcome"
                    replay_experiment_id_arg = None
                    manifest_hash_arg = None
                    expires_at_arg = None

            if should_insert:
                try:
                    cur.execute(
                        """
                        SELECT learning.verify_replay_evidence_and_insert(
                            %s,                             -- p_engine_mode
                            NULL,                           -- p_symbol (regret scope is engine_mode-wide)
                            NULL,                           -- p_strategy_name (regret aggregates across strategies)
                            'opportunity_tracker',          -- p_source
                            'regret_summary',               -- p_recommendation_type
                            %s,                             -- p_expected_net_bps
                            %s,                             -- p_confidence
                            %s,                             -- p_sample_count
                            %s,                             -- p_payload
                            false,                          -- p_applied
                            true,                           -- p_requires_governance
                            'mlde_opportunity_tracker',     -- p_created_by
                            %s,                             -- p_evidence_source_tier (R7)
                            %s,                             -- p_replay_experiment_id (R7)
                            %s,                             -- p_manifest_hash (R7 hex)
                            %s,                             -- p_expires_at (R7 timestamptz)
                            NULL, NULL, NULL                -- decision_lease_id / context_id / intent_id
                        )
                        """,
                        (
                            cfg.engine_mode,
                            summary.get("avg_regret_bps", 0.0),
                            min(0.85, (summary.get("rejected_sample_count", 0) or 0) / 50.0),
                            summary.get("rejected_sample_count", 0),
                            Json(summary),
                            tier_arg,
                            replay_experiment_id_arg,
                            manifest_hash_arg,
                            expires_at_arg,
                        ),
                    )
                    inserted = 1
                    if tier_arg == "calibrated_replay":
                        calibrated_inserted = 1
                except psycopg2.Error as exc:  # noqa: BLE001
                    # verified function reject: log and continue (producer 不 crash).
                    # function reject 拒絕：記 log 後返回 inserted=0。
                    logger.warning(
                        "opportunity_tracker: verify_replay_evidence_and_insert rejected tier=%s err=%s",
                        tier_arg, exc,
                    )
        conn.commit()

    result: dict[str, Any] = {"inserted": inserted, "summary": summary}
    if use_r7_path:
        result["calibrated_inserted"] = calibrated_inserted
        result["skipped_none_label"] = skipped_none_label
    return result
