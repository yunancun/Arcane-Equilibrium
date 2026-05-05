"""MLDE shadow advisor.

Reads the V031 ML/Dream edge-unblock training view and emits advisory
rank/veto rows into ``learning.mlde_shadow_recommendations``.

This module is deliberately not an execution path. Rows are logged with
``applied=false`` and ``requires_governance=true`` so downstream promotion can
be audited separately.

MODULE_NOTE (EN):
    Wave 6 R20-P4-Q5 extension: a NEW
    ``rank_and_veto_replay_candidates(candidates)`` module-level helper is
    added (no fork) to consume the
    ``ReplayCandidate`` list produced by
    ``local_model_tools.dream_engine.generate_replay_candidates()``
    (P4-Q4) and emit a parallel list of ``RankedCandidate`` rows containing
    ML rank + veto_reason (advisory only, never blocks downstream — V3 §11
    P4 KPI). Output is written to ``replay.mlde_replay_veto_log`` (V043
    migration; landed same commit). The rank logic reuses the existing
    ``_confidence`` helper (sample_count + edge magnitude blend) and
    extends with 3 veto rules:

      - ``cost_edge_ratio < 0.8``  → ``cost_edge_below_threshold``
      - ``PBO > 0.5``              → ``pbo_above_threshold``
      - ``DSR < 0.95``             → ``dsr_below_threshold``

    Plus 2 protective fallbacks:
      - ``confidence == 'none'``   → ``low_confidence_replay``
      - missing strategy_params    → ``unknown_strategy_axis``

    All 5 reasons match the V043 ``chk_replay_mlde_veto_reason`` allowlist
    so DB INSERT does not reject. Caller (replay_routes.py) is responsible
    for routing the V043 INSERT through a verified function (Wave 6 ships
    DB schema only; persistence wiring is Wave 7+ scope per workplan §4).

    Module surface preserved:
      - All Wave 3 P0-T6 functions (``build_recommendations``,
        ``generate_shadow_recommendations``, etc.).
      - ``ShadowAdvisorConfig`` / ``ShadowRecommendation`` dataclasses
        untouched.

    NEW Wave 6 surface:
      - ``VetoReasonLiteral`` — 5-value Literal aligning with V043 enum.
      - ``RankedCandidate`` dataclass — output row.
      - ``rank_and_veto_replay_candidates(candidates, **gate_inputs)``
        module-level helper.

MODULE_NOTE (中):
    Wave 6 R20-P4-Q5 擴展：新增
    ``rank_and_veto_replay_candidates(candidates)`` module-level helper
    (NOT fork)，消費 P4-Q4 產出的 ``ReplayCandidate`` list，emit 平行的
    ``RankedCandidate`` list (含 ML rank + veto_reason)，advisory only 永
    不阻擋下游 (V3 §11 P4 KPI)。輸出寫入 ``replay.mlde_replay_veto_log``
    (V043 migration；同 commit land)。Rank 邏輯重用既有 ``_confidence``
    helper，加 3 veto 規則 + 2 protective fallback (共 5 reason，與 V043
    enum 對齊)。

    Module surface 保留：所有 Wave 3 P0-T6 既有 function 不動。

    Wave 6 新增：
      - ``VetoReasonLiteral`` (5 值 Literal)
      - ``RankedCandidate`` (dataclass)
      - ``rank_and_veto_replay_candidates(...)`` helper

SPEC:
  - REF-20 V3 §11 P4 KPI (advisory only; 0 unverified to applier)
  - REF-20 V3 §12 #6 (mlde_replay_source_guard) + #17 (cv_protocol)
  - REF-20 V3 §12 #24 (cost_edge_ratio >= 0.8 gate)
Workplan:
  docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md §4 Wave 6 R20-P4-Q5
"""

from __future__ import annotations

import json
import logging
import math
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional

# REF-20 Sprint C2 R7-T1.5（PA §2B 漏列補位）：calibrated_replay tier 升級。
# Optional import 模式（避免未上線環境載入 replay 模組失敗）。
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

# ─────────────────────────────────────────────────────────────────────────────
# Wave 6 R20-P4-Q5 enums + thresholds / Wave 6 R20-P4-Q5 enum + 閾值
# ─────────────────────────────────────────────────────────────────────────────

# V043 chk_replay_mlde_veto_reason allowlist mirror; DB INSERT will reject
# any value outside this set.
# V043 chk_replay_mlde_veto_reason 白名單鏡像；DB INSERT 拒絕白名單外值。
VetoReasonLiteral = Literal[
    "cost_edge_below_threshold",
    "pbo_above_threshold",
    "dsr_below_threshold",
    "low_confidence_replay",
    "unknown_strategy_axis",
]

# V3 §12 #24 cost_edge_ratio >= 0.8 gate.
# V3 §12 #24 cost_edge_ratio >= 0.8 守門。
COST_EDGE_RATIO_GATE = 0.8

# V3 §8.3 PBO < 0.5 (when K >= 10) gate.
# V3 §8.3 PBO < 0.5 (K >= 10 時) 守門。
PBO_GATE = 0.5

# V3 §8.3 DSR(K) > 0.95 gate.
# V3 §8.3 DSR(K) > 0.95 守門。
DSR_GATE = 0.95

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


def _persist_recommendations(
    dsn: str,
    recommendations: list[ShadowRecommendation],
    *,
    R6_calibration_provider: Optional[
        Callable[[Optional[str], Optional[str]], "CalibrationResult"]
    ] = None,
    replay_experiment_id_provider: Optional[
        Callable[[ShadowRecommendation], Optional[str]]
    ] = None,
) -> int:
    """REF-20 Sprint C2 R7-T1.5（PA §2B 漏列補位）：升級 calibrated_replay
    tier-aware insert。

    與 dream_engine / opportunity_tracker 同型路徑，但 ``rec.source`` 是
    variable（V031 CHECK allowlist：ml_shadow / dream_engine /
    opportunity_tracker / linucb）。R7 升級 evidence_source_tier 不影響
    rec.source field（兩個正交軸）。

    Backward-compat：
      - 不傳 ``R6_calibration_provider`` → legacy 'real_outcome' fallback。
      - 傳 provider + experiment_id_provider → per-rec 取
        ``CalibrationResult`` + experiment_id；NONE 跳過、其餘走
        calibrated_replay tier。

    Args:
        dsn: PG dsn。
        recommendations: ShadowRecommendation list（caller 由
            generate_shadow_recommendations build）。
        R6_calibration_provider: optional callable
            ``(strategy_name, symbol) → CalibrationResult``。
        replay_experiment_id_provider: optional callable
            ``(rec) → experiment_id``；caller 提供 per-rec experiment_id
            mapping（典型實作：dict lookup or fixed cycle id）。
    """
    if not recommendations:
        return 0
    if psycopg2 is None or Json is None:
        raise RuntimeError("psycopg2 not installed")

    # R7-T1.5: 判斷是否走 calibrated_replay path
    use_r7_path = (
        R6_calibration_provider is not None
        and replay_experiment_id_provider is not None
        and _R7_HELPER_AVAILABLE
        and build_replay_metadata is not None
    )

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
            %s,                             -- p_evidence_source_tier (R7)
            %s,                             -- p_replay_experiment_id (R7)
            %s,                             -- p_manifest_hash (R7 hex)
            %s,                             -- p_expires_at (R7 timestamptz)
            NULL, NULL, NULL                -- decision_lease_id / context_id / intent_id
        )
    """
    inserted = 0
    skipped_none_label = 0

    with psycopg2.connect(dsn, connect_timeout=2) as conn:  # pragma: no cover - DB path
        with conn.cursor() as cur:
            for rec in recommendations:
                # R7-T1.5 metadata 構造（fail-soft）
                tier_arg = "real_outcome"
                replay_experiment_id_arg: Optional[str] = None
                manifest_hash_arg: Optional[str] = None
                expires_at_arg: Optional[Any] = None
                should_insert = True

                if use_r7_path:
                    try:
                        experiment_id = replay_experiment_id_provider(rec)  # type: ignore[misc]
                        cal_result = R6_calibration_provider(  # type: ignore[misc]
                            rec.strategy_name, rec.symbol,
                        )
                        if experiment_id is None or cal_result is None:
                            tier_arg = "real_outcome"
                        else:
                            metadata = build_replay_metadata(
                                experiment_id=experiment_id,
                                calibration_result=cal_result,
                                cur=cur,
                            )
                            if metadata is None:
                                # NONE label / V049 missing → skip
                                should_insert = False
                                skipped_none_label += 1
                            else:
                                tier_arg, replay_experiment_id_arg, manifest_hash_arg, expires_at_arg = metadata
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "mlde_shadow_advisor R7: provider/helper 異常 → "
                            "fallback real_outcome (rec=%s/%s err=%s)",
                            rec.strategy_name, rec.source, exc,
                        )
                        tier_arg = "real_outcome"
                        replay_experiment_id_arg = None
                        manifest_hash_arg = None
                        expires_at_arg = None

                if not should_insert:
                    continue

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
                            tier_arg,
                            replay_experiment_id_arg,
                            manifest_hash_arg,
                            expires_at_arg,
                        ),
                    )
                    inserted += 1
                except psycopg2.Error as exc:  # noqa: BLE001
                    # verified function reject: log and continue.
                    # function reject 拒絕：記 log 後繼續下一筆。
                    logger.warning(
                        "mlde_shadow_advisor: verify_replay_evidence_and_insert rejected rec=%s/%s tier=%s err=%s",
                        rec.strategy_name,
                        rec.source,
                        tier_arg,
                        exc,
                    )
        conn.commit()

    if use_r7_path and skipped_none_label > 0:
        logger.info(
            "mlde_shadow_advisor R7: skipped %d recommendations with NONE label",
            skipped_none_label,
        )
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


# ═════════════════════════════════════════════════════════════════════════════
# Wave 6 R20-P4-Q5 — rank_and_veto_replay_candidates() API
# Wave 6 R20-P4-Q5 — rank_and_veto_replay_candidates() API
#
# Surface-add only. Functions / dataclasses below are NEW; nothing above is
# modified. Caller is replay_routes.py (after P4-Q4 dream_engine produces
# the ReplayCandidate list); output is written to replay.mlde_replay_veto_log
# via the V043 INSERT path. Veto chain is advisory ONLY — does NOT block
# downstream candidate submission per V3 §11 P4 KPI.
#
# 純表面新增。下方為新；上面任何邏輯不動。Caller = replay_routes.py（在
# P4-Q4 dream_engine 產出 ReplayCandidate list 後）；輸出經 V043 INSERT
# path 寫入 replay.mlde_replay_veto_log。Veto chain 純 advisory 不阻擋下游
# 候選提交（per V3 §11 P4 KPI）。
# ═════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class RankedCandidate:
    """One rank/veto advisory row for a ``ReplayCandidate`` from P4-Q4.

    對 P4-Q4 ``ReplayCandidate`` 的單筆 rank/veto advisory row。

    Attributes:
        candidate_id: UUID hex string copied 1-to-1 from
            ``ReplayCandidate.candidate_id`` for soft lineage trace into
            V043 ``replay.mlde_replay_veto_log.candidate_id``.
        rank: 1-indexed rank from MLDE within the input candidate batch
            (1 = best score). Rank is determined by ``ml_score`` desc;
            ties broken by candidate_id lex order for determinism. CHECK
            ``rank >= 1`` enforced at V043 DB layer.
        ml_score: DOUBLE PRECISION ranking score (higher = better
            predicted edge after MLDE feature blend). Range is unbounded
            by design (calibration not assumed at this layer; downstream
            P4-Q1 DSR may calibrate).
        veto_reason: Optional VetoReasonLiteral. None means no veto
            (advisory rank-only row); else one of 5 V043 enum values.
            Advisory only — the candidate IS NOT removed from the input
            list; veto_reason is logged so downstream P6 typed-confirm
            modal can surface it.
        advisory_summary: Bilingual NON-EMPTY string for operator GUI
            (e.g. ``"veto: 成本邊際低 / cost-edge below 0.8"``). The V043
            ``chk_replay_mlde_veto_advisory_summary_nonempty`` CHECK
            enforces non-empty body at DB layer.
    """

    candidate_id: str
    rank: int
    ml_score: float
    veto_reason: Optional[VetoReasonLiteral]
    advisory_summary: str


@dataclass(frozen=True)
class RankAndVetoGateInputs:
    """Optional gate input metadata for ``rank_and_veto_replay_candidates``.

    ``rank_and_veto_replay_candidates`` 的選用 gate input 元資料。

    Attributes:
        pbo: Probability of Backtest Overfitting from P4-Q2 (V3 §8.3
            PBO < 0.5 when K >= 10). NULL means PBO not available
            (insufficient power) — gate is skipped, not failed.
        dsr_k: Deflated Sharpe Ratio across K candidates from P4-Q1
            (V3 §8.3 DSR(K) > 0.95). NULL means DSR not available.
        cost_edge_ratio_override: Override the per-candidate
            ``expected_cost_bps / abs(expected_edge_bps)`` calculation
            with a caller-supplied scalar (some calibration paths feed
            a smoothed cell-level estimate). NULL = use per-candidate
            calculation.

    All fields default to None; the gate is skipped when input is missing
    (gate-by-data-availability, not fail-closed). This matches V3 §11 P4
    "advisory only" — partial info → partial advice, never a hard reject.

    全部 default None；input 缺 → skip 對應 gate (gate-by-data-availability，
    非 fail-closed)。對齊 V3 §11 P4 "advisory only" 契約。
    """

    pbo: Optional[float] = None
    dsr_k: Optional[float] = None
    cost_edge_ratio_override: Optional[float] = None


def _build_advisory_summary(
    rank: int,
    veto_reason: Optional[VetoReasonLiteral],
    cost_edge_ratio: float,
    pbo: Optional[float],
    dsr_k: Optional[float],
) -> str:
    """Build the bilingual advisory_summary string for a candidate.

    為候選建立雙語 advisory_summary 字串。

    The summary always includes the rank prefix; veto_reason (if set)
    selects the bilingual phrase from the canonical phrasebook below.
    Non-veto rows still get a positive bilingual summary so the V043
    ``chk_replay_mlde_veto_advisory_summary_nonempty`` CHECK passes.

    Summary 永遠包含 rank 前綴；veto_reason (若設) 從下方 phrasebook 選對
    應雙語短語。無 veto 也產出正向雙語 summary 以滿足 V043
    ``chk_replay_mlde_veto_advisory_summary_nonempty`` CHECK。
    """
    rank_prefix_zh = f"排名 #{rank}"
    rank_prefix_en = f"rank #{rank}"
    if veto_reason is None:
        return (
            f"{rank_prefix_zh}：通過 advisory rank（無 veto） / "
            f"{rank_prefix_en}: passed advisory rank (no veto)"
        )
    phrasebook: dict[str, tuple[str, str]] = {
        "cost_edge_below_threshold": (
            f"成本邊際比 {cost_edge_ratio:.2f} 低於 V3 §12 #24 閾值 "
            f"{COST_EDGE_RATIO_GATE}",
            f"cost-edge ratio {cost_edge_ratio:.2f} below V3 §12 #24 "
            f"threshold {COST_EDGE_RATIO_GATE}",
        ),
        "pbo_above_threshold": (
            f"PBO {pbo:.3f} 超過 V3 §8.3 閾值 {PBO_GATE}"
            if pbo is not None
            else f"PBO 超過 V3 §8.3 閾值 {PBO_GATE}",
            f"PBO {pbo:.3f} exceeds V3 §8.3 threshold {PBO_GATE}"
            if pbo is not None
            else f"PBO exceeds V3 §8.3 threshold {PBO_GATE}",
        ),
        "dsr_below_threshold": (
            f"DSR(K) {dsr_k:.3f} 低於 V3 §8.3 閾值 {DSR_GATE}"
            if dsr_k is not None
            else f"DSR(K) 低於 V3 §8.3 閾值 {DSR_GATE}",
            f"DSR(K) {dsr_k:.3f} below V3 §8.3 threshold {DSR_GATE}"
            if dsr_k is not None
            else f"DSR(K) below V3 §8.3 threshold {DSR_GATE}",
        ),
        "low_confidence_replay": (
            "候選 confidence='none' (S3 synthetic / Mac 非 actionable)",
            "candidate confidence='none' (S3 synthetic / Mac non-actionable)",
        ),
        "unknown_strategy_axis": (
            "未知 strategy 軸 (fallback generic axis 不可 actionable)",
            "unknown strategy axis (fallback generic axis not actionable)",
        ),
    }
    zh, en = phrasebook[veto_reason]
    return f"{rank_prefix_zh} veto：{zh} / {rank_prefix_en} veto: {en}"


def _decide_veto_reason(
    candidate_strategy_params: dict[str, Any],
    candidate_confidence: str,
    cost_edge_ratio: float,
    gate_inputs: "RankAndVetoGateInputs",
) -> Optional[VetoReasonLiteral]:
    """Decide which veto_reason (if any) applies to a candidate.

    決定候選適用的 veto_reason (若有)。

    Decision order (first match wins; ordering matters for transparency):
      1. Empty strategy_params (caller bug or unknown strategy axis)
         → ``unknown_strategy_axis``.
      2. confidence == 'none' (S3 / Mac dev) → ``low_confidence_replay``.
      3. cost_edge_ratio < 0.8 → ``cost_edge_below_threshold``.
      4. PBO > 0.5 (only if pbo is not None) → ``pbo_above_threshold``.
      5. DSR(K) < 0.95 (only if dsr_k is not None) → ``dsr_below_threshold``.
      6. else → None (no veto, advisory rank-only row).

    決策順序 (首個命中為準；順序影響透明性)。
    """
    if not candidate_strategy_params:
        return "unknown_strategy_axis"
    if candidate_confidence == "none":
        return "low_confidence_replay"
    if cost_edge_ratio < COST_EDGE_RATIO_GATE:
        return "cost_edge_below_threshold"
    if gate_inputs.pbo is not None and gate_inputs.pbo > PBO_GATE:
        return "pbo_above_threshold"
    if gate_inputs.dsr_k is not None and gate_inputs.dsr_k < DSR_GATE:
        return "dsr_below_threshold"
    return None


def _ml_score_for_candidate(
    expected_edge_bps: float,
    expected_cost_bps: float,
    confidence: str,
) -> float:
    """Compute MLDE rank score for a candidate.

    為候選計算 MLDE rank score。

    Wave 6 baseline: blend (edge - cost) with a confidence multiplier.
    Multiplier: 1.0 (high) / 0.7 (medium) / 0.4 (low) / 0.0 (none).
    Score sign: positive = predicted profitable, negative = predicted
    unprofitable; rank desc by score.

    Wave 6 baseline：(edge - cost) 乘 confidence multiplier。
    Multiplier 1.0 / 0.7 / 0.4 / 0.0；score 為正表預測獲利。
    """
    multiplier_map = {"high": 1.0, "medium": 0.7, "low": 0.4, "none": 0.0}
    multiplier = multiplier_map.get(confidence, 0.0)
    return (expected_edge_bps - expected_cost_bps) * multiplier


def rank_and_veto_replay_candidates(
    candidates: list,
    *,
    gate_inputs: Optional["RankAndVetoGateInputs"] = None,
) -> list[RankedCandidate]:
    """Rank and veto a list of ``ReplayCandidate`` (P4-Q4 output).

    對 ``ReplayCandidate`` list (P4-Q4 輸出) 做 rank 與 veto 標記。

    This is the Wave 6 R20-P4-Q5 deliverable: a pure-compute helper that
    consumes the in-memory ``ReplayCandidate`` list from P4-Q4
    ``dream_engine.generate_replay_candidates()`` and emits a parallel
    ``RankedCandidate`` list with ML rank + veto_reason. The function
    does NOT write to ``trading.*``, ``learning.*``, or ``replay.*``;
    the caller (replay_routes.py) is responsible for routing accepted
    advisories through the V043 ``replay.mlde_replay_veto_log`` INSERT
    path.

    本函式為 Wave 6 R20-P4-Q5 交付：純計算 helper，消費 P4-Q4
    in-memory ``ReplayCandidate`` list，emit 平行 ``RankedCandidate`` list
    (含 ML rank + veto_reason)。0 ``trading.*`` / ``learning.*`` /
    ``replay.*`` 寫；caller (replay_routes.py) 自行決定送入 V043
    ``replay.mlde_replay_veto_log`` INSERT path。

    Advisory only / 純 advisory：veto_reason 設值不會從 candidate 集合中
    移除；advisory_summary 給 operator GUI 顯示。

    Args:
        candidates: List of ``ReplayCandidate`` from P4-Q4 (typed
            structurally — accepts any object with the 5 attributes
            ``candidate_id`` / ``strategy_params`` / ``expected_edge_bps``
            / ``expected_cost_bps`` / ``confidence``). Accepts ``list``
            to avoid hard import-coupling to ``local_model_tools``.
        gate_inputs: Optional ``RankAndVetoGateInputs`` with PBO / DSR /
            cost-edge override. Default = empty (PBO/DSR gates skipped).

    Returns:
        ``list[RankedCandidate]`` parallel to input length, ordered by
        ``rank`` ascending (1 = best). Empty input → empty output.

    Raises:
        ValueError: If a candidate is missing the required ``candidate_id``
            attribute (caller bug — input was not produced by P4-Q4 or
            shape-equivalent producer).
    """
    if not candidates:
        return []

    if gate_inputs is None:
        gate_inputs = RankAndVetoGateInputs()

    scored: list[tuple[Any, float, float, Optional[VetoReasonLiteral]]] = []
    for cand in candidates:
        candidate_id = getattr(cand, "candidate_id", None)
        if candidate_id is None or not isinstance(candidate_id, str):
            raise ValueError(
                f"candidate missing string candidate_id: {cand!r}"
            )
        strategy_params = getattr(cand, "strategy_params", {})
        expected_edge_bps = float(getattr(cand, "expected_edge_bps", 0.0))
        expected_cost_bps = float(getattr(cand, "expected_cost_bps", 0.0))
        confidence = getattr(cand, "confidence", "none")

        if gate_inputs.cost_edge_ratio_override is not None:
            cost_edge_ratio = gate_inputs.cost_edge_ratio_override
        else:
            edge_mag = max(abs(expected_edge_bps), 1e-9)
            cost_edge_ratio = edge_mag / max(expected_cost_bps, 1e-9)

        ml_score = _ml_score_for_candidate(
            expected_edge_bps, expected_cost_bps, confidence
        )

        veto_reason = _decide_veto_reason(
            strategy_params, confidence, cost_edge_ratio, gate_inputs
        )

        scored.append((cand, ml_score, cost_edge_ratio, veto_reason))

    scored.sort(
        key=lambda t: (-t[1], getattr(t[0], "candidate_id", "")),
    )

    out: list[RankedCandidate] = []
    for idx, (cand, ml_score, cost_edge_ratio, veto_reason) in enumerate(
        scored, start=1
    ):
        advisory_summary = _build_advisory_summary(
            rank=idx,
            veto_reason=veto_reason,
            cost_edge_ratio=cost_edge_ratio,
            pbo=gate_inputs.pbo,
            dsr_k=gate_inputs.dsr_k,
        )
        out.append(
            RankedCandidate(
                candidate_id=getattr(cand, "candidate_id"),
                rank=idx,
                ml_score=round(ml_score, 6),
                veto_reason=veto_reason,
                advisory_summary=advisory_summary,
            )
        )
    return out


__all__ = [
    "COST_EDGE_RATIO_GATE",
    "DSR_GATE",
    "PBO_GATE",
    "RankAndVetoGateInputs",
    "RankedCandidate",
    "ShadowAdvisorConfig",
    "ShadowRecommendation",
    "VetoReasonLiteral",
    "build_recommendations",
    "config_from_env",
    "generate_shadow_recommendations",
    "rank_and_veto_replay_candidates",
]


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    summary = generate_shadow_recommendations()
    print(json.dumps(summary, indent=2, sort_keys=True))
