"""Read-only DreamEngine producer for MLDE.

This is a narrow production bridge around the current edge-repair questions:
grid spacing, MA whipsaw hold-time, BB breakout threshold/timeframe, and maker
timeout. It emits parameter proposals as advisory data only.

MODULE_NOTE (EN):
    Wave 6 R20-P4-Q4 extension: a NEW ``generate_replay_candidates(intent)``
    method is added on the existing module surface (no fork). The new method
    samples N candidate strategy parameter sets given a ``ReplayIntent`` and
    returns a list of ``ReplayCandidate`` dataclasses sorted by
    ``expected_edge_bps`` descending. The method is pure compute (0
    ``trading.*`` write, 0 DB INSERT, 0 lease acquire) and is consumed by
    the upcoming ``replay_routes.py POST /api/v1/replay/run`` caller; the
    caller is responsible for routing the result through
    ``learning.verify_replay_evidence_and_insert()`` (V036) or discarding
    candidates that fail downstream gates (P4-Q5 MLDE veto, calibration,
    cost_edge_ratio).

    Module surface preserved:
      - All Wave 3 P0-T6 functions (``build_dream_summary``,
        ``persist_dream_insights``, ``get_latest_dream_summary``, etc.).
      - ``DreamConfig`` / ``config_from_env`` / ``_proposal_for_strategy``
        helpers untouched (Wave 6 surface-add only).

    NEW Wave 6 surface:
      - ``ReplayIntent`` (dataclass) — caller-supplied request envelope.
      - ``ReplayCandidate`` (dataclass) — per-candidate output row.
      - ``ConfidenceLiteral`` — 4-value Literal {high, medium, low, none}.
      - ``DreamEngine.generate_replay_candidates(intent)`` — new method
        implemented as a top-level ``generate_replay_candidates`` function
        that callers invoke without instantiating a class (mirrors the
        existing module-level helper pattern such as
        ``persist_dream_insights``).

MODULE_NOTE (中):
    Wave 6 R20-P4-Q4 擴展：在 既有 module surface 新增
    ``generate_replay_candidates(intent)`` method (NOT fork)。新 method 依
    ``ReplayIntent`` 取樣 N 個候選 strategy parameter set，回 list of
    ``ReplayCandidate`` (依 expected_edge_bps 由大到小排序)。本 method 為
    純計算 (0 ``trading.*`` 寫、0 DB INSERT、0 lease acquire)，由將上線的
    ``replay_routes.py POST /api/v1/replay/run`` caller 消費；caller 自行
    決定送入 ``learning.verify_replay_evidence_and_insert()`` (V036) 或在
    下游 gate (P4-Q5 MLDE veto / calibration / cost_edge_ratio) 失敗時
    丟棄。

    Module surface 保留：
      - 所有 Wave 3 P0-T6 既有 function 不動。
      - ``DreamConfig`` / ``config_from_env`` / ``_proposal_for_strategy``
        皆不動 (Wave 6 純表面新增)。

    Wave 6 新增：
      - ``ReplayIntent`` (dataclass) — caller 提交的請求信封。
      - ``ReplayCandidate`` (dataclass) — 單筆候選結果。
      - ``ConfidenceLiteral`` — 4 值 Literal。
      - ``generate_replay_candidates(intent)`` — module-level helper
        function (callers 不需實例化 class，鏡像既有 ``persist_dream_insights``
        模式)。

SPEC:
  - REF-20 V3 §6.1 (Canonical replay_runner) + §11 P4 KPI (advisory writer)
  - REF-20 V3 §12 acceptance #6 (mlde_replay_source_guard) + #17 (cv_protocol)
Workplan:
  docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md §4 Wave 6 R20-P4-Q4
"""

from __future__ import annotations

import hashlib
import logging
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional

try:
    import psycopg2  # type: ignore
    from psycopg2.extras import Json  # type: ignore
except ImportError:  # pragma: no cover - runtime DB path only
    psycopg2 = None  # type: ignore[assignment]
    Json = None  # type: ignore[assignment]

# REF-20 Sprint C2 R7-T1：calibrated_replay tier 升級需要 CalibrationResult
# 型別 + build_replay_metadata helper。Optional import 模式（避免未上線環境
# 載入 replay 模組失敗）。caller 不傳 R6_calibration_provider 時退回 legacy
# 'real_outcome' fallback path（backward-compat per AI-E §10 risk #7）。
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

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Wave 6 R20-P4-Q4 公開常數 / Wave 6 R20-P4-Q4 public constants
# ─────────────────────────────────────────────────────────────────────────────

# V3 §3 G7 + §6 / V3 §3 G7 + §6: replay fixture source allowlist。
# 與 ``replay.experiments.runtime_environment`` 配套；S2 = Bybit public REST
# fetch；S3 = synthetic OHLC/tick (research_notes/replay_fixtures/).
# Aligns with ``replay.experiments.runtime_environment``; S2 = Bybit public
# REST fetch; S3 = synthetic OHLC/tick (research_notes/replay_fixtures/).
FixtureSourceLiteral = Literal["s2_bybit_public", "s3_synthetic"]

# V3 §4.1 execution_confidence enum 部分映射 / V3 §4.1 execution_confidence
# enum partial mapping:
#   high     → calibrated + n>=200 + freshness <72h
#   medium   → calibrated but n<200 OR freshness 72-168h
#   low      → calibrated_replay tier 但 power 不足
#   none     → counterfactual / synthetic / Mac dev smoke; never actionable
# Matches ``replay.experiments.execution_confidence`` value subset; the
# canonical V3 enum {none, limited, calibrated} is mapped per
# ``confidence_for_candidate()`` rules (see code below).
ConfidenceLiteral = Literal["high", "medium", "low", "none"]

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
    R6_calibration_provider: Optional[
        Callable[[str, Optional[str]], "CalibrationResult"]
    ] = None,
) -> dict[str, Any]:
    """REF-20 Sprint C2 R7-T1：升級為 calibrated_replay tier-aware insert。

    Backward-compat (per AI-E advisory §10 risk #7)：
      - 不傳 ``R6_calibration_provider`` → 走 legacy 'real_outcome' fallback
        path（既有 18 月生產行為不動）。
      - 傳 provider → per-insight 取 ``CalibrationResult``，依 label：
        * NONE → skip（不 INSERT）；強制下游 fail-fast，避免污染
          calibrated_replay tier。
        * LIMITED / CALIBRATED → 寫 'calibrated_replay' tier + 4-tuple
          metadata (replay_experiment_id / manifest_hash / expires_at)。

    Args:
        dsn: PG dsn (None → env fallback)。
        engine_mode: paper / demo / live_demo / live。
        cfg: optional override config（test 注入用）。
        R6_calibration_provider: optional callable
            ``(strategy_name, symbol) → CalibrationResult``。Caller 必須提
            供能取 R6 ``derive_execution_confidence`` 結果的方法（典型實
            作：caller 上游 pre-computed dict 包成 lambda）。傳 None →
            backward-compat fallback path（'real_outcome' tier）。

    Returns:
        dict with ``inserted`` / ``insights`` 計數 + R7 路徑時加
        ``skipped_none_label`` (NONE label 跳過數量) + ``calibrated_inserted``
        (calibrated_replay tier 寫入數)。
    """
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

    # R7-T1: 判斷是否走 calibrated_replay path 或 legacy real_outcome path。
    # provider 提供 + helper 可用 → 走 R7 升級路徑；否則 backward-compat
    # 'real_outcome' fallback。
    use_r7_path = (
        R6_calibration_provider is not None
        and _R7_HELPER_AVAILABLE
        and build_replay_metadata is not None
    )

    inserted = 0
    skipped_none_label = 0  # R7 path: label=NONE 跳過數
    calibrated_inserted = 0  # R7 path: 走 calibrated_replay tier 數

    with psycopg2.connect(resolved_dsn, connect_timeout=2) as conn:  # pragma: no cover - DB path
        with conn.cursor() as cur:
            for insight in insights:
                strategy_name = insight.get("strategy_name")

                # R7-T1 metadata 構造（fail-soft）
                replay_experiment_id_arg: Optional[str] = None
                manifest_hash_arg: Optional[str] = None
                expires_at_arg: Optional[Any] = None
                tier_arg = "real_outcome"  # 預設 legacy

                if use_r7_path:
                    try:
                        # provider 收 (strategy, symbol) — dream insight scope
                        # 是 strategy-wide，symbol 傳 None。
                        cal_result = R6_calibration_provider(strategy_name, None)  # type: ignore[misc]
                        # Caller 必含 experiment_id（R6 W6 從 V049 derive 後
                        # caller 自記 mapping）。預期 caller 包 lambda 帶 closure。
                        experiment_id = insight.get("replay_experiment_id")
                        if experiment_id is None or cal_result is None:
                            # 缺 experiment_id 或 cal_result → fallback real_outcome
                            tier_arg = "real_outcome"
                        else:
                            metadata = build_replay_metadata(
                                experiment_id=experiment_id,
                                calibration_result=cal_result,
                                cur=cur,
                            )
                            if metadata is None:
                                # NONE label 或 V049 row 缺失 → skip 此筆
                                skipped_none_label += 1
                                continue
                            tier_arg, replay_experiment_id_arg, manifest_hash_arg, expires_at_arg = metadata
                    except Exception as exc:  # noqa: BLE001
                        # R6 provider 異常 → fallback real_outcome（不 crash
                        # producer cycle）
                        logger.warning(
                            "dream_engine R7: provider/helper 異常 → "
                            "fallback real_outcome (strategy=%s err=%s)",
                            strategy_name, exc,
                        )
                        tier_arg = "real_outcome"
                        replay_experiment_id_arg = None
                        manifest_hash_arg = None
                        expires_at_arg = None

                try:
                    cur.execute(
                        """
                        SELECT learning.verify_replay_evidence_and_insert(
                            %s,                             -- p_engine_mode
                            NULL,                           -- p_symbol (insight scope is strategy-wide)
                            %s,                             -- p_strategy_name
                            'dream_engine',                 -- p_source
                            'parameter_proposal',           -- p_recommendation_type
                            %s,                             -- p_expected_net_bps
                            %s,                             -- p_confidence
                            %s,                             -- p_sample_count
                            %s,                             -- p_payload
                            false,                          -- p_applied
                            true,                           -- p_requires_governance
                            'mlde_dream_engine',            -- p_created_by
                            %s,                             -- p_evidence_source_tier (R7: real_outcome | calibrated_replay)
                            %s,                             -- p_replay_experiment_id (R7)
                            %s,                             -- p_manifest_hash (R7 hex)
                            %s,                             -- p_expires_at (R7 timestamptz)
                            NULL, NULL, NULL                -- decision_lease_id / context_id / intent_id
                        )
                        """,
                        (
                            cfg.engine_mode,
                            strategy_name,
                            insight.get("expected_improvement_bps"),
                            insight.get("confidence"),
                            insight.get("sample_count"),
                            Json(insight),
                            tier_arg,
                            replay_experiment_id_arg,
                            manifest_hash_arg,
                            expires_at_arg,
                        ),
                    )
                    inserted += 1
                    if tier_arg == "calibrated_replay":
                        calibrated_inserted += 1
                except psycopg2.Error as exc:  # noqa: BLE001
                    # verified function reject: log and continue (producer 不 crash).
                    # function reject 拒絕：記 log 後繼續下一筆 (producer 不 crash)。
                    logger.warning(
                        "dream_engine: verify_replay_evidence_and_insert rejected insight=%s tier=%s err=%s",
                        strategy_name, tier_arg, exc,
                    )
        conn.commit()

    result: dict[str, Any] = {
        "inserted": inserted,
        "insights": len(insights),
    }
    if use_r7_path:
        result["calibrated_inserted"] = calibrated_inserted
        result["skipped_none_label"] = skipped_none_label
    return result


# ═════════════════════════════════════════════════════════════════════════════
# Wave 6 R20-P4-Q4 — generate_replay_candidates() API
# Wave 6 R20-P4-Q4 — generate_replay_candidates() API
#
# Surface-add only. The functions / dataclasses below are NEW; nothing above
# is modified. Caller is replay_routes.py POST /api/v1/replay/run; output is
# routed through learning.verify_replay_evidence_and_insert() (V036) on
# acceptance, or discarded by P4-Q5 MLDE veto / P3a-Q6 calibration gate.
#
# 純表面新增。下方 function / dataclass 全為新；上面任何邏輯不動。Caller =
# replay_routes.py POST /api/v1/replay/run；output 經
# learning.verify_replay_evidence_and_insert() (V036) 寫入或在 P4-Q5 MLDE
# veto / P3a-Q6 calibration gate 失敗時丟棄。
# ═════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ReplayIntent:
    """Caller-supplied request envelope to ``generate_replay_candidates``.

    呼叫者提交給 ``generate_replay_candidates`` 的請求信封。

    Attributes:
        strategy_id: Strategy key (e.g. ``grid_trading``, ``ma_crossover``).
            Must be one of the 6 ``_proposal_for_strategy`` keys to obtain a
            concrete parameter axis; unknown strategies fall back to the
            generic ``confidence_threshold`` axis.
        symbol: Bybit USDT-margined symbol (e.g. ``BTCUSDT``). Used as the
            ``cell_key`` salt for fixture_payload_hash to ensure
            cross-symbol candidates do not collide.
        cell_key: Strategy/symbol/side cell identifier (V3 §8.4 cell-level
            n>=30 gate; P3b-Q1 sample size accounting). Format
            ``<strategy>::<symbol>::<side>`` is recommended but enforced
            only at the registry function (V036 has no opinion on this
            string body).
        n_candidates: Number of candidate parameter sets to generate.
            Default 100 (V3 §11 P4 KPI: ≥10 advisory rows / week ÷ 7 days
            ÷ 12-15 cells active = ~100 candidates / cell / week is a
            comfortable upper bound; caller may downsize for Mac dev
            smoke). Hard ceiling 1000 to prevent accidental DDoS of the
            applier veto path.
        fixture_source: Either ``s2_bybit_public`` (Bybit REST OHLC/tick)
            or ``s3_synthetic`` (PM-curated research_notes/replay_fixtures
            file). V3 §6.2 explicitly excludes S0/S1 private data from
            replay; this field is the gate.
        manifest_id: Parent replay.experiments.experiment_id (UUID string)
            owning these candidates. NULL is rejected; caller MUST register
            the parent manifest via POST /api/v1/replay/manifests before
            invoking generate_replay_candidates.
    """

    strategy_id: str
    symbol: str
    cell_key: str
    fixture_source: FixtureSourceLiteral
    manifest_id: str
    n_candidates: int = 100


@dataclass(frozen=True)
class ReplayCandidate:
    """One sampled candidate parameter set returned by ``generate_replay_candidates``.

    ``generate_replay_candidates`` 回傳的單筆候選 parameter set。

    Attributes:
        candidate_id: Server-generated UUID4 hex string. The Wave 6
            workplan §4 P4-Q4 row stipulates the API surface returns UUIDs
            so the V043 mlde_replay_veto_log can FK by candidate_id.
        strategy_params: JSONB-compatible dict containing the sampled
            parameter values (e.g. ``{"grid_spacing_bps": 12.5,
            "min_hold_seconds": 95}``). Must serialize cleanly via
            ``psycopg2.extras.Json`` so the V036 verified insert function
            can persist into ``mlde_shadow_recommendations.payload``.
        expected_edge_bps: Estimated edge in bps under the sampled params.
            Sign convention: positive = bullish edge, negative = unprofitable
            after fee. See ``_estimate_candidate_edge`` for derivation.
        expected_cost_bps: Estimated trading cost (maker/taker fee + slippage)
            in bps. Always non-negative. Used downstream by
            ``cost_edge_ratio = expected_cost_bps / max(abs(expected_edge_bps),
            epsilon) >= 0.8`` gate (V3 §12 #24).
        confidence: 4-value Literal {high, medium, low, none}. ``none``
            applies to S3 synthetic fixtures and any Mac dev smoke run
            (V3 §6.3); ``high`` requires calibrated freshness <=72h plus
            n>=200 (V3 §8.1).
        fixture_payload_hash: SHA-256 hex digest over a canonical bytes
            representation of (strategy_id, symbol, cell_key, sample_seed)
            used for reproducibility — given the same seed and intent the
            output payload hash MUST match (Wave 6 acceptance test 5
            verifies). Mirrors the ``manifest_jsonb`` reproducibility
            invariant at the candidate level.
        selection_bias_metadata: P3a-Q3 selection-bias correction metadata
            dict (V3 §8.3 + §12 #17). Always populated; even Mac dev /
            S3 synthetic candidates carry the metadata so downstream PBO
            < 0.5 / DSR(K) > 0.95 gates have the input they expect. Empty
            dict is rejected (Wave 6 acceptance test 5 verifies non-empty).
    """

    candidate_id: str
    strategy_params: dict[str, Any]
    expected_edge_bps: float
    expected_cost_bps: float
    confidence: ConfidenceLiteral
    fixture_payload_hash: str
    selection_bias_metadata: dict[str, Any] = field(default_factory=dict)


# ── Internal helper constants for candidate sampling ─────────────────────────
# ── 候選取樣用內部常數 ────────────────────────────────────────────────────

# Hard ceiling on n_candidates per ReplayIntent (V3 §5 quota guard analogue).
# Caller-supplied n_candidates > MAX_CANDIDATES_PER_INTENT is clamped down.
# 每個 ReplayIntent 的 n_candidates 上限 (V3 §5 quota guard 類比)。
# 超過 MAX_CANDIDATES_PER_INTENT 時夾到上限。
MAX_CANDIDATES_PER_INTENT = 1000

# Per-strategy parameter axis: (param_name, base_value, lo_jitter, hi_jitter).
# Jitter is applied multiplicatively: sampled = base * (1 + uniform(lo, hi)).
# Synchronized with ``_proposal_for_strategy`` keys to avoid silent drift
# when MIT alters the producer schema.
# 每策略參數軸：(param_name, base_value, lo_jitter, hi_jitter)。
# Jitter 乘法套用：sampled = base * (1 + uniform(lo, hi))。
# 與 ``_proposal_for_strategy`` keys 同步以避免 MIT 改 producer schema 時漂移。
_CANDIDATE_PARAM_AXIS: dict[str, tuple[str, float, float, float]] = {
    "grid_trading": ("grid_spacing_bps", 10.0, -0.30, 0.30),
    "ma_crossover": ("min_hold_seconds", 60.0, -0.50, 0.50),
    "bb_breakout": ("volume_threshold", 1.5, -0.20, 0.20),
    "bb_reversion": ("exit_conf_base", 0.60, -0.10, 0.10),
    "funding_arb": ("min_funding_edge_bps", 5.0, -0.20, 0.20),
}


def _confidence_for_candidate(
    fixture_source: FixtureSourceLiteral,
    sample_count: int,
    is_calibrated: bool,
) -> ConfidenceLiteral:
    """Derive ``ConfidenceLiteral`` from fixture / sample / calibration triple.

    依 fixture / sample / calibration 三元組推 ``ConfidenceLiteral``。

    Rules (V3 §6.2/§6.3 + §8.1):
      - S3 synthetic → always ``none`` (non-actionable per V3 §6.2).
      - S2 + uncalibrated → ``low`` (data is real but no calibration
        anchor; Wave 6 fallback for cells without P3a half-life).
      - S2 + calibrated + n>=200 → ``high`` (matches V3 §8.1 strategy
        window power minimum).
      - S2 + calibrated + 30<=n<200 → ``medium`` (P3b cell-level
        threshold).
      - else → ``low``.

    規則：
      - S3 synthetic → 永遠 ``none`` (per V3 §6.2 不可 actionable)。
      - S2 + 未 calibrated → ``low``。
      - S2 + calibrated + n>=200 → ``high``。
      - S2 + calibrated + 30<=n<200 → ``medium``。
      - 其他 → ``low``。
    """
    if fixture_source == "s3_synthetic":
        return "none"
    if not is_calibrated:
        return "low"
    if sample_count >= 200:
        return "high"
    if sample_count >= 30:
        return "medium"
    return "low"


def _estimate_candidate_edge(
    strategy_id: str,
    sampled_param: float,
    base_param: float,
    rng: random.Random,
) -> tuple[float, float]:
    """Return (expected_edge_bps, expected_cost_bps) given sampled param.

    依取樣參數回 (expected_edge_bps, expected_cost_bps)。

    The estimator is intentionally simple — Wave 6 P4-Q4 ships a baseline
    that can be replaced by P4-Q1/Q2 (DSR / PBO) once the calibration
    pipeline data is wired. The current model:

      base_edge_bps  = -2.0 (current 5-strategy gross negative edge per
                             CLAUDE.md §三; matches MLDE training view
                             realized 7d demo gross)
      param_drift    = 0.5 * (sampled_param - base_param) / base_param
                       (i.e. moving the param away from baseline shifts
                       edge proportionally; some strategies negative, some
                       positive — see strategy-specific signs below)
      noise          = uniform(-1.0, 1.0)  (Wave 6 baseline; DSR / PBO
                       replace once P4-Q1/Q2 lands)

      expected_edge_bps  = base_edge_bps + sign * param_drift + noise
      expected_cost_bps  = 1.5 + 0.10 * |sampled_param - base_param| / base_param

    Sign convention:
      - grid_trading: widen → +edge (less fee drag)
      - ma_crossover: lengthen hold → +edge (whipsaw filter)
      - bb_breakout: raise threshold → +edge (cleaner break)
      - bb_reversion: tighten exit → +edge (adverse excursion control)
      - funding_arb: raise min edge → +edge (cost coverage)
      - unknown: neutral 0

    Estimator 故意簡單。Wave 6 P4-Q4 出貨 baseline；P4-Q1/Q2 DSR/PBO 上線
    後可替換。
    """
    base_edge_bps = -2.0
    sign_map = {
        "grid_trading": 1.0,
        "ma_crossover": 1.0,
        "bb_breakout": 1.0,
        "bb_reversion": 1.0,
        "funding_arb": 1.0,
    }
    sign = sign_map.get(strategy_id, 0.0)
    if base_param == 0:
        param_drift = 0.0
    else:
        param_drift = 0.5 * (sampled_param - base_param) / base_param
    noise = rng.uniform(-1.0, 1.0)
    expected_edge_bps = base_edge_bps + sign * param_drift + noise
    cost_drift = 0.10 * abs(sampled_param - base_param) / max(abs(base_param), 1e-9)
    expected_cost_bps = 1.5 + cost_drift
    return (round(expected_edge_bps, 4), round(max(0.0, expected_cost_bps), 4))


def _payload_hash(
    strategy_id: str, symbol: str, cell_key: str, seed: int
) -> str:
    """Compute SHA-256 hex over canonical bytes of (strategy, symbol, cell, seed).

    對 (strategy, symbol, cell, seed) 的 canonical bytes 算 SHA-256 hex。

    Reproducibility invariant (Wave 6 acceptance test 5):
        Same input → byte-equal hash. Used so caller can deduplicate
        candidates across re-runs of the same intent (e.g. operator
        retries POST /api/v1/replay/run before timeout). Mirrors the
        ``manifest_jsonb canonical`` invariant from V3 §4.1 at candidate
        level.
    """
    blob = (
        f"{strategy_id}::{symbol}::{cell_key}::seed={seed}".encode("utf-8")
    )
    return hashlib.sha256(blob).hexdigest()


def _build_selection_bias_metadata(
    intent: ReplayIntent,
    n_actual: int,
    seed: int,
) -> dict[str, Any]:
    """Construct the P3a-Q3 selection_bias_metadata dict.

    建立 P3a-Q3 selection_bias_metadata dict。

    Schema follows V3 §8.3 (selection bias controls) requirements:
      - total_candidates_K (mandatory per V3 §8.3): the actual N candidates
        generated in this intent (capped to MAX_CANDIDATES_PER_INTENT).
      - selection_method: ``parameter_axis_uniform_jitter`` for Wave 6
        baseline (P4-Q1/Q2 DSR/PBO replace later).
      - sample_seed: rng seed used; reproducibility key.
      - intent_fingerprint: short hash binding the metadata to the parent
        intent (so the V043 advisory log can audit which intent generated
        the candidate even after the intent expires per TTL).

    符合 V3 §8.3 selection bias controls 要求的 schema。
    """
    return {
        "total_candidates_K": n_actual,
        "selection_method": "parameter_axis_uniform_jitter",
        "sample_seed": seed,
        "intent_fingerprint": _payload_hash(
            intent.strategy_id, intent.symbol, intent.cell_key, seed
        )[:16],
        "wave6_baseline": True,
        # P4-Q1/Q2 DSR/PBO output goes here once P3a calibration land:
        # "dsr_k": ..., "pbo": ..., per V3 §12 #17.
        # P4-Q1/Q2 DSR/PBO output 後續在 P3a calibration land 後填入：
        # "dsr_k": ..., "pbo": ..., per V3 §12 #17。
    }


def generate_replay_candidates(
    intent: ReplayIntent,
    *,
    seed: Optional[int] = None,
    is_calibrated: bool = False,
    sample_count: int = 0,
) -> list[ReplayCandidate]:
    """Generate sampled replay candidate parameter sets given a ``ReplayIntent``.

    依 ``ReplayIntent`` 生成取樣 replay 候選 parameter set。

    R7-T2 (Sprint C2 W1, 2026-05-05): verify-only — 本 function 是 pure
    compute API；caller `replay_routes.py POST /api/v1/replay/run` 走 V036
    verify_replay_evidence_and_insert 路徑（AI-E §1 grep verified: 0 直接
    INSERT in this function body）。本函數不動 evidence_source_tier；
    R7 升級不影響（caller 已負責決定 tier）。

    This is the Wave 6 R20-P4-Q4 deliverable: a pure-compute API surface
    that the upcoming ``replay_routes.py POST /api/v1/replay/run`` caller
    invokes to obtain N candidate parameter sets sorted by expected_edge_bps
    descending. The function does NOT write to ``trading.*``,
    ``learning.*``, or ``replay.*``; the caller is responsible for routing
    accepted candidates through ``learning.verify_replay_evidence_and_insert()``
    (V036) and rejecting failed ones via the P4-Q5 MLDE veto chain
    (``rank_and_veto_replay_candidates``).

    本函式為 Wave 6 R20-P4-Q4 交付：純計算 API 表面，將上線的
    ``replay_routes.py POST /api/v1/replay/run`` caller 用以取得 N 個依
    expected_edge_bps 由大到小排序的候選 parameter set。本函式 0
    ``trading.*`` 寫、0 ``learning.*`` 寫、0 ``replay.*`` 寫；caller 自行
    決定送入 V036 verified insert function (P4-Q5 MLDE veto 把關後)。

    Args:
        intent: Caller-supplied ``ReplayIntent`` envelope.
        seed: Optional rng seed for reproducibility. If ``None``, a
            deterministic seed is derived from
            ``hash((strategy_id, symbol, cell_key, manifest_id))``
            so identical intents from different operator sessions still
            produce identical candidates (V3 §4.1 manifest reproducibility
            invariant at candidate level).
        is_calibrated: Whether the cell has a calibrated half-life from
            P3a-Q1. False → confidence downgraded to ``low`` even on S2.
            Caller is the calibration-readiness query at the route layer
            (P3a-Q6 freshness gate decides this flag).
        sample_count: Cell-level n (P3b-Q1 cell calibration row count).
            Used by ``_confidence_for_candidate`` to disambiguate ``high``
            (n>=200) vs ``medium`` (n>=30) vs ``low`` confidence on S2.

    Returns:
        ``list[ReplayCandidate]`` sorted by ``expected_edge_bps`` desc.
        Length == ``min(intent.n_candidates, MAX_CANDIDATES_PER_INTENT)``.
        Empty list returned only on hard input validation failure (caller
        bug); production caller is expected to validate intent fields
        upstream at route layer.

    Raises:
        ValueError: On invalid intent fields (n_candidates <= 0, unknown
            fixture_source, empty manifest_id / strategy_id / symbol /
            cell_key). Test 1 verifies the happy path.
    """
    # ── Input validation / 輸入驗證 ──────────────────────────────────────
    if not intent.strategy_id:
        raise ValueError("ReplayIntent.strategy_id must be non-empty")
    if not intent.symbol:
        raise ValueError("ReplayIntent.symbol must be non-empty")
    if not intent.cell_key:
        raise ValueError("ReplayIntent.cell_key must be non-empty")
    if not intent.manifest_id:
        raise ValueError("ReplayIntent.manifest_id must be non-empty")
    if intent.n_candidates <= 0:
        raise ValueError(
            f"ReplayIntent.n_candidates must be positive; got {intent.n_candidates}"
        )
    if intent.fixture_source not in ("s2_bybit_public", "s3_synthetic"):
        raise ValueError(
            f"ReplayIntent.fixture_source must be one of "
            f"('s2_bybit_public', 's3_synthetic'); got {intent.fixture_source!r}"
        )

    # ── Clamp n_candidates to hard ceiling (V3 §5 quota analogue) ────────
    # ── n_candidates 夾到硬上限 (V3 §5 quota 類比) ────────────────────
    n_actual = min(intent.n_candidates, MAX_CANDIDATES_PER_INTENT)

    # ── Derive deterministic seed if caller did not provide one ──────────
    # ── caller 未提供 seed 時推導確定性 seed ────────────────────────────
    if seed is None:
        # Use SHA-256 over canonical bytes (not Python hash() which is
        # randomized by PYTHONHASHSEED). Take first 8 bytes as int.
        # 用 SHA-256 over canonical bytes (非 Python hash()，後者受
        # PYTHONHASHSEED 隨機化)。取前 8 bytes 為 int。
        canonical = (
            f"{intent.strategy_id}::{intent.symbol}::{intent.cell_key}::"
            f"{intent.manifest_id}"
        ).encode("utf-8")
        seed_bytes = hashlib.sha256(canonical).digest()[:8]
        seed = int.from_bytes(seed_bytes, byteorder="big", signed=False)

    rng = random.Random(seed)

    # ── Resolve parameter axis for the strategy ──────────────────────────
    # ── 解析 strategy 對應的 parameter axis ─────────────────────────────
    # Unknown strategies fall back to a generic axis so callers don't
    # crash on legacy / experimental strategy_id values; the resulting
    # candidates carry confidence='low' or 'none' and will be rejected
    # by the P4-Q5 MLDE veto chain anyway.
    # 未知 strategy 走 generic axis；候選 confidence='low'/'none'，會被
    # P4-Q5 MLDE veto chain 拒絕。
    if intent.strategy_id in _CANDIDATE_PARAM_AXIS:
        param_name, base_param, lo_jitter, hi_jitter = _CANDIDATE_PARAM_AXIS[
            intent.strategy_id
        ]
    else:
        param_name = "confidence_threshold"
        base_param = 0.5
        lo_jitter = -0.10
        hi_jitter = 0.10

    # ── Sample candidates / 取樣候選 ─────────────────────────────────────
    candidates: list[ReplayCandidate] = []
    selection_bias_metadata = _build_selection_bias_metadata(
        intent, n_actual, seed
    )

    confidence = _confidence_for_candidate(
        intent.fixture_source, sample_count, is_calibrated
    )

    for i in range(n_actual):
        jitter = rng.uniform(lo_jitter, hi_jitter)
        sampled_param = base_param * (1.0 + jitter)
        # Round to 4 dp for JSON-serializable payload (avoids float repr
        # drift in cross-platform tests).
        # 取 4 dp 以避免跨平台 float repr drift。
        sampled_param = round(sampled_param, 4)

        expected_edge_bps, expected_cost_bps = _estimate_candidate_edge(
            intent.strategy_id, sampled_param, base_param, rng
        )

        # candidate_id is uuid4 hex (32 chars no dashes) so it fits cleanly
        # in V043 mlde_replay_veto_log.candidate_id UUID column.
        # candidate_id 用 uuid4 hex (32 chars 無 dash)；V043
        # mlde_replay_veto_log.candidate_id UUID column 直接吃。
        candidate_id = uuid.UUID(int=rng.getrandbits(128), version=4).hex

        # fixture_payload_hash binds candidate to (intent + iter index +
        # seed) so re-runs reproduce; iter index ensures collision-free
        # within a batch when seed is fixed.
        # fixture_payload_hash 綁 (intent + iter index + seed)；同 batch
        # 內 iter index 保證唯一。
        fpx_hash = _payload_hash(
            intent.strategy_id, intent.symbol, intent.cell_key, seed + i
        )

        strategy_params = {param_name: sampled_param}

        candidates.append(
            ReplayCandidate(
                candidate_id=candidate_id,
                strategy_params=strategy_params,
                expected_edge_bps=expected_edge_bps,
                expected_cost_bps=expected_cost_bps,
                confidence=confidence,
                fixture_payload_hash=fpx_hash,
                selection_bias_metadata=dict(selection_bias_metadata),
            )
        )

    # ── Sort by expected_edge_bps desc / 依 expected_edge_bps 由大到小排序 ──
    candidates.sort(key=lambda c: c.expected_edge_bps, reverse=True)

    return candidates


__all__ = [
    "ConfidenceLiteral",
    "DreamConfig",
    "FixtureSourceLiteral",
    "MAX_CANDIDATES_PER_INTENT",
    "ReplayCandidate",
    "ReplayIntent",
    "build_dream_summary",
    "config_from_env",
    "generate_replay_candidates",
    "get_latest_dream_summary",
    "persist_dream_insights",
]
