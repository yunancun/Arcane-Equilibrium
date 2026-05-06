"""
MODULE_NOTE
模組目的：LG-5 Live Candidate Evaluation Contract consumer side。實裝
        ``GovernanceHub.review_live_candidate(candidate_id)`` —— 對
        ``learning.mlde_param_applications`` 中的 live promotion candidate
        執行 R1–R6 + R-meta 7 條 evaluation rule，產出 ``ReviewVerdict``，
        emit audit row 至 ``learning.governance_audit_log``，approve 時
        透過 ``GovernanceHub.acquire_lease()`` 取得 Decision Lease 並寫回
        candidate row 的 ``decision_lease_id`` 欄位。

Module purpose: LG-5 Live Candidate Evaluation Contract consumer side.
                Implements ``GovernanceHub.review_live_candidate(candidate_id)``
                — runs R1-R6 + R-meta evaluation rules against a live
                promotion candidate row in ``learning.mlde_param_applications``,
                produces a ``ReviewVerdict``, emits an audit row to
                ``learning.governance_audit_log``, and on approve acquires a
                Decision Lease via ``GovernanceHub.acquire_lease()`` and
                writes ``decision_lease_id`` back to the candidate row.

Spec source / 規格來源：
    docs/CCAgentWorkSpace/PA/workspace/reports/
        2026-05-02--lg5_live_candidate_eval_contract_rfc_v2.md
    §2.2 Consumer side / §2.3 Audit / §3 R1-R6 + R-meta / §4 Lease

PA dispatch warnings / PA 派發預警 (RFC §9):
    1. governance_hub.py LOC budget — 本檔為 PM 預授權 split sibling，
       核心 ``acquire_lease`` / ``get_effective`` / ``_lock`` 留在 governance_hub.py。
       Sibling: governance_hub.py LOC budget — this file is the PM-pre-authorized
       split sibling; core acquire_lease/get_effective/_lock stay in
       governance_hub.py.
    2. Lock contention — ``review_live_candidate`` 嚴禁在 ``GovernanceHub._lock``
       持鎖期間做 DB read。Pattern：
         a. 取一個 short read transaction 讀 candidate row + pending count
         b. **Release** transaction
         c. 純 in-memory + 額外 DB read (無 lock) 計算 verdict
         d. 若 approve → 短暫呼叫 ``hub.acquire_lease()`` (內部會持鎖)
       Lock contention — ``review_live_candidate`` MUST NOT hold
       ``GovernanceHub._lock`` while doing DB reads. Pattern:
         a. short read txn for candidate row + pending count
         b. release txn
         c. compute verdict in memory + further DB reads (no hub lock)
         d. on approve → brief ``hub.acquire_lease()`` call (it manages its own lock)
    3. Audit fail-closed — audit write 失敗 → 回 ``defer
       defer_audit_write_failed``，不發 lease (CLAUDE.md §二 原則 #6 + #8)。
       Audit fail-closed — audit write failure → return ``defer
       defer_audit_write_failed``, do NOT issue lease.

關聯 / Cross-ref:
    - Producer payload: program_code/ml_training/mlde_demo_applier.py
      (``_build_live_candidate_payload`` 寫 ``schema_version =
      live_candidate_eval_v1`` 與 5 個 sub-key)
    - SQL schema: sql/migrations/V032 (mlde_param_applications) +
      V035 (governance_audit_log)
    - Consumer integration: GovernanceHub instance (this module imports the
      class from .governance_hub but does not modify it)
"""

from __future__ import annotations

import json
import logging
import math
import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Optional

from .db_pool import get_conn, put_conn

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Constants / 常數 (per RFC v2 §3 + §4)
# ═══════════════════════════════════════════════════════════════════════════════

# Schema version expected from producer / Producer 必填 payload schema_version
EXPECTED_SCHEMA_VERSION = "live_candidate_eval_v1"

# R1 — 0.85 ratio + 0.15 absolute floor (MF-Q1)
R1_MAKER_FILL_RATIO = 0.85
R1_MAKER_FILL_FLOOR = 0.15

# R2 — clamp(0.3, 1.0); pass >= 1.5 bps (MF-Q2)
R2_CLAMP_LOW = 0.3
R2_CLAMP_HIGH = 1.0
R2_PASS_THRESHOLD_BPS = 1.5

# R3 — PSR(0) >= 0.95; n_strategy_fills >= 100 (MF-Q3)
R3_PSR_THRESHOLD = 0.95
R3_PSR_BORDERLINE_HIGH = 0.97  # borderline band → shorter lease
R3_MIN_SAMPLE_COUNT = 100

# R4 — Bailey-LdP simplified SR_0; trigger >= 5 pending (MF-Q4)
R4_TRIGGER_PENDING_COUNT = 5
R4_PENDING_CAP = 16  # mlde_demo_applier.max_recommendations
R4_EULER_GAMMA = 0.5772156649015329  # Euler-Mascheroni constant
R4_FALLBACK_DEMO_FACTOR = 0.25  # K<5 worst-case override (informational; not default)

# R5 — cost_edge_ratio bands (CLAUDE.md §二 #13, MF-Q5)
R5_PASS_CEIL = 0.5
R5_WARN_CEIL = 0.8

# R6 — hard veto (MF-Q6)
R6_DAILY_NEG_SNAPSHOTS_REQUIRED = 7
R6_MAKER_FILL_CATASTROPHIC_FLOOR = 0.10

# R-meta constants + evaluators relocated to ``governance_hub_lg5_r_meta`` sibling
# (Fix 2 IMPL-2-consumer split, keeps parent < 1500 LOC); 4 symbols re-exported.
# R-meta 常數與 evaluator 已 split 至 sibling，re-export 維持 backward-compat。
from .governance_hub_lg5_r_meta import (  # noqa: F401  (re-export)
    R_META_RATIO_FLOOR, _R_META_MIN_SAMPLE_PER_STRATEGY,
    evaluate_r_meta, evaluate_r_meta_sample_threshold,
    build_r_meta_gate_verdict_kwargs,
)

# Lease TTL bands (RFC §4)
LEASE_TTL_DEFAULT_MS = 6 * 3600 * 1000  # 6 h
LEASE_TTL_R5_WARN_MS = 1 * 3600 * 1000  # 1 h
LEASE_TTL_R3_BORDERLINE_MS = 2 * 3600 * 1000  # 2 h
LEASE_TTL_LEARNING_PERIOD_MS = 2 * 3600 * 1000  # 2 h (first 30d post-deploy)

# Standard lease revoke triggers (RFC §4)
DEFAULT_LEASE_REVOKE_TRIGGERS = (
    "[22]_trading_pipeline_silent_gap",
    "[33]_maker_fill_rate_drop",
    "[40]_realized_edge_acceptance",
    "[42]_live_candidate_eval_contract",
    "[42b]_attribution_chain_drift",
)

_TAKER_FEE_RATE: float = 0.00055
_MAKER_FEE_CUTOFF: float = 0.00040
_STRATEGY_ENTRY_FILL_PREDICATE: str = """
                      AND (f.entry_context_id IS NULL OR f.entry_context_id = '')
                      AND f.exit_reason IS NULL
                      AND f.order_id NOT LIKE 'oc_risk_%%'
"""


def _strategy_entry_fill_predicate() -> str:
    """SQL predicate for strategy-owned entry fills only. 僅篩 strategy entry fill。"""
    return _STRATEGY_ENTRY_FILL_PREDICATE


# ═══════════════════════════════════════════════════════════════════════════════
# ReviewVerdict dataclass / 評估結果資料類 (per RFC §2.2)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ReviewVerdict:
    """LG-5 ``review_live_candidate`` 評估結果。
    LG-5 ``review_live_candidate`` evaluation outcome.

    所有 R2/R3/R4 raw inputs 全部 echo 入 audit row（per RFC §2.3 +
    §13 V035 schema），供 IMPL-5 7d retro 校準。
    All R2/R3/R4 raw inputs echoed into the audit row (per RFC §2.3 +
    §13 V035 schema) for IMPL-5 7d retro calibration.
    """

    decision: Literal["approve", "reject", "defer"]
    reason: str
    rule_failures: list[str]
    expected_net_bps_demo: float
    expected_net_bps_live_adjusted: Optional[float]
    expected_net_bps_deflated: Optional[float]
    cost_regime_ratio: Optional[float]
    cost_regime_ratio_clamped: Optional[float]
    psr_value: Optional[float]
    psr_n_samples: Optional[int]
    psr_skew: Optional[float]
    psr_kurt: Optional[float]
    sr_0_deflation: Optional[float]
    v_pending_net_bps: Optional[float]
    lease_ttl_ms: Optional[int]
    lease_revoke_triggers: list[str] = field(default_factory=list)
    decided_at_ts: int = 0  # unix ms
    decided_by: str = "GovernanceHub.review_live_candidate"
    payload_snapshot: dict = field(default_factory=dict)
    # Fix 2 NEW：候選 strategy 3d attribution sample 數，IMPL-5 retro 校準用。
    attribution_sample_count: Optional[int] = None


# ═══════════════════════════════════════════════════════════════════════════════
# Internal helpers / 內部輔助 — pure functions, no DB access
# ═══════════════════════════════════════════════════════════════════════════════

def _safe_float(value: Any, default: float = 0.0) -> float:
    """Coerce to float fail-soft / 容錯轉 float。"""
    try:
        if value is None:
            return default
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    """Coerce to int fail-soft / 容錯轉 int。"""
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _now_ms() -> int:
    """Unix epoch ms / Unix epoch 毫秒。"""
    return int(time.time() * 1000)


def _inv_norm_cdf(p: float) -> float:
    """Inverse standard normal CDF using stdlib NormalDist (no scipy dep).
    使用 stdlib NormalDist 計算反標準常態 CDF（避免 scipy 依賴）。

    Mac dev environment 沒有 scipy；統一走 ``statistics.NormalDist``
    （Python 3.8+ stdlib，與 scipy.stats.norm.ppf 同精度）。
    """
    if p <= 0.0 or p >= 1.0:
        # Defensive — Bailey-LdP K=1 corner (p=1-1/K=0); skip via fallback.
        # 防禦性處理 — Bailey-LdP K=1 邊界 (p=1-1/K=0)；由 fallback 略過。
        raise ValueError(f"_inv_norm_cdf requires 0 < p < 1, got {p}")
    return statistics.NormalDist().inv_cdf(p)


def _normal_cdf(x: float) -> float:
    """Standard normal CDF / 標準常態 CDF。"""
    return statistics.NormalDist().cdf(x)


def _compute_bailey_ldp_sr_0(K: int, v_pending_net_bps: float) -> float:
    """Bailey-López-de-Prado simplified SR_0 deflation magnitude.
    Bailey-López-de-Prado 簡化 SR_0 deflation 量。

    Formula (RFC §3 R4):
      γ = 0.5772 (Euler-Mascheroni)
      SR_0 = sqrt(V) × ((1-γ)·Φ⁻¹(1-1/K) + γ·Φ⁻¹(1-1/(K·e)))

    Args:
        K: pending candidate count (clamped to >=2 for stable Φ⁻¹).
        v_pending_net_bps: sample variance of expected_net_bps_live_adjusted
                           across K pending candidates (bps²).

    Returns:
        Deflation magnitude in bps (subtract from R2-adjusted expectation).
    """
    if K < 2:
        return 0.0
    if v_pending_net_bps <= 0.0:
        return 0.0
    sqrt_v = math.sqrt(v_pending_net_bps)
    p1 = 1.0 - 1.0 / float(K)
    p2 = 1.0 - 1.0 / (float(K) * math.e)
    if p1 <= 0.0 or p1 >= 1.0 or p2 <= 0.0 or p2 >= 1.0:
        return 0.0
    z1 = _inv_norm_cdf(p1)
    z2 = _inv_norm_cdf(p2)
    return sqrt_v * ((1.0 - R4_EULER_GAMMA) * z1 + R4_EULER_GAMMA * z2)


def _compute_psr(
    sr_observed: float,
    n: int,
    skew: float,
    kurt: float,
    sr_benchmark: float = 0.0,
) -> float:
    """PSR(SR_benchmark) per Bailey-López-de-Prado 2012.
    PSR(SR_benchmark) per Bailey-López-de-Prado 2012。

    Formula:
      PSR = Φ((SR - SR_b) × sqrt(n - 1) / sqrt(1 - skew·SR + ((kurt-1)/4)·SR²))

    Inputs use *per-sample* Sharpe (i.e. mean / std without annualization);
    benchmark default = 0 (positive expected return).
    """
    if n < 2:
        return 0.0
    denom_inner = 1.0 - skew * sr_observed + ((kurt - 1.0) / 4.0) * sr_observed * sr_observed
    if denom_inner <= 0.0:
        # Pathological skew/kurt combination → fail-closed conservative
        # 病態 skew/kurt 組合 → fail-closed 取保守值
        return 0.0
    z = (sr_observed - sr_benchmark) * math.sqrt(n - 1) / math.sqrt(denom_inner)
    return _normal_cdf(z)


# ═══════════════════════════════════════════════════════════════════════════════
# DB helpers / DB 存取 — short transactions, NO hub lock held
# ═══════════════════════════════════════════════════════════════════════════════

def _fetch_candidate_row(candidate_id: int) -> Optional[dict[str, Any]]:
    """Read one candidate row from learning.mlde_param_applications.
    從 learning.mlde_param_applications 讀取單筆 candidate row。

    Filter: id = candidate_id AND engine_mode='live' AND status='candidate'
            AND application_type='live_promotion_candidate' (per RFC v2 §2.2
            line 140 + MF-M3).
    """
    conn = get_conn()
    if conn is None:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, ts, engine_mode, recommendation_id, application_type,
                       target_name, patch, status, reason, requires_governance,
                       decision_lease_id, payload
                FROM learning.mlde_param_applications
                WHERE id = %s
                  AND engine_mode = 'live'
                  AND status = 'candidate'
                  AND application_type = 'live_promotion_candidate'
                LIMIT 1
                """,
                (candidate_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        cols = (
            "id", "ts", "engine_mode", "recommendation_id", "application_type",
            "target_name", "patch", "status", "reason", "requires_governance",
            "decision_lease_id", "payload",
        )
        return dict(zip(cols, row))
    except Exception as exc:  # noqa: BLE001 — fail-soft; consumer downstream defers
        logger.warning("lg5 fetch_candidate_row failed id=%s err=%s", candidate_id, exc)
        return None
    finally:
        put_conn(conn)


def _fetch_source_recommendation(recommendation_id: int) -> Optional[dict[str, Any]]:
    """Read source demo recommendation row (R3 / R4 demo expected_net_bps).
    讀取 demo 來源 recommendation row（R3 / R4 demo expected_net_bps 來源）。
    """
    if recommendation_id is None or recommendation_id <= 0:
        return None
    conn = get_conn()
    if conn is None:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, strategy_name, symbol, expected_net_bps, confidence,
                       sample_count
                FROM learning.mlde_shadow_recommendations
                WHERE id = %s
                LIMIT 1
                """,
                (recommendation_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "strategy_name": row[1],
            "symbol": row[2],
            "expected_net_bps": _safe_float(row[3], 0.0),
            "confidence": _safe_float(row[4], 0.0),
            "sample_count": _safe_int(row[5], 0),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("lg5 fetch_source_recommendation failed id=%s err=%s",
                       recommendation_id, exc)
        return None
    finally:
        put_conn(conn)


def _fetch_live_cost_regime() -> dict[str, float]:
    """Fetch current live cost regime from trading.fills (last 24h, live_demo).
    從 trading.fills 取最近 24h live_demo 成本制度（R1 / R2 / R5 / R6 input）。

    Mirrors healthcheck [33] posterior + [40] live realized — independent SQL
    so consumer is not coupled to healthcheck cron freshness.

    Returns:
        dict with keys: maker_fill_rate, avg_fee_bps, avg_slippage_bps,
                        avg_net_bps, sample_count.
        Empty defaults on DB failure → R-driven defer downstream.
    """
    result: dict[str, float] = {
        "maker_fill_rate": 0.0,
        "avg_fee_bps": 0.0,
        "avg_slippage_bps": 0.0,
        "avg_net_bps": 0.0,
        "sample_count": 0,
    }
    conn = get_conn()
    if conn is None:
        return result
    try:
        with conn.cursor() as cur:
            # Mirror [33] maker_fill on live_demo entry fills 24h.
            # 鏡 [33] live_demo 入場 fill 的 maker_fill 24h。
            cur.execute(
                """
                WITH entry_fills AS (
                    SELECT
                        CASE
                            WHEN lower(coalesce(f.liquidity_role, '')) = 'maker'
                              OR coalesce(nullif(f.fee_rate, 0), %s) <= %s
                            THEN 1 ELSE 0
                        END AS maker_like,
                        coalesce(nullif(f.fee_rate, 0), %s)::float8 * 10000.0 AS fee_bps
                    FROM trading.fills f
                    WHERE f.ts > now() - INTERVAL '24 hours'
                      AND f.engine_mode IN ('live', 'live_demo')
                      AND coalesce(f.strategy_name, '') <> ''
                      AND f.strategy_name NOT LIKE 'risk_close:%%'
                      AND f.strategy_name NOT LIKE 'strategy_close:%%'
                      AND f.strategy_name NOT LIKE 'ipc_close%%'
                      AND f.strategy_name NOT LIKE 'unattributed:%%'
                      AND coalesce(f.exit_source, '') = ''
                """ + _strategy_entry_fill_predicate() + """
                )
                SELECT
                    count(*)::int,
                    coalesce(sum(maker_like), 0)::int,
                    coalesce(avg(fee_bps), 0.0)::float8
                FROM entry_fills
                """,
                (_TAKER_FEE_RATE, _MAKER_FEE_CUTOFF, _TAKER_FEE_RATE),
            )
            row = cur.fetchone()
        if row is not None:
            total = _safe_int(row[0])
            maker_like = _safe_int(row[1])
            avg_fee_bps = _safe_float(row[2])
            result["sample_count"] = float(total)
            if total > 0:
                result["maker_fill_rate"] = maker_like / total
            result["avg_fee_bps"] = avg_fee_bps

        # Mirror [40] live realized net + slippage from MLDE training rows.
        # 鏡 [40] live realized net + slippage from MLDE training rows view。
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('learning.mlde_edge_training_rows') IS NOT NULL")
            exists_row = cur.fetchone()
            if exists_row and exists_row[0]:
                cur.execute(
                    """
                    SELECT
                        coalesce(avg(net_bps_after_fee), 0.0)::float8,
                        coalesce(avg(slippage_bps), 0.0)::float8
                    FROM learning.mlde_edge_training_rows
                    WHERE ts > now() - INTERVAL '24 hours'
                      AND engine_mode IN ('live', 'live_demo')
                      AND attribution_chain_ok
                      AND net_bps_after_fee IS NOT NULL
                    """
                )
                net_row = cur.fetchone()
                if net_row is not None:
                    result["avg_net_bps"] = _safe_float(net_row[0])
                    result["avg_slippage_bps"] = _safe_float(net_row[1])
    except Exception as exc:  # noqa: BLE001
        logger.warning("lg5 fetch_live_cost_regime failed err=%s", exc)
    finally:
        put_conn(conn)
    return result


def _fetch_r6_daily_snapshots() -> dict[str, int]:
    """R6: count negative daily-snapshot avg_net over past 7 complete days.
    R6：過去 7 個完整日的 daily snapshot avg_net 中為負的數量。

    Per RFC §3 R6 SQL pseudocode (line ~330-348): each daily snapshot is
    one independent aggregate (NOT rolling 24h × 7).
    """
    result = {"n_snapshots": 0, "n_negative": 0}
    conn = get_conn()
    if conn is None:
        return result
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH daily_snapshots AS (
                    SELECT
                        date_trunc('day', ts) AS day,
                        AVG(net_bps_after_fee) AS daily_avg_net
                    FROM trading.fills
                    WHERE engine_mode IN ('live', 'live_demo')
                      AND ts >= now() - INTERVAL '7 days'
                      AND ts <  date_trunc('day', now())
                      AND net_bps_after_fee IS NOT NULL
                    GROUP BY date_trunc('day', ts)
                    ORDER BY day DESC
                    LIMIT 7
                )
                SELECT
                    count(*)::int,
                    count(*) FILTER (WHERE daily_avg_net < 0)::int
                FROM daily_snapshots
                """
            )
            row = cur.fetchone()
        if row is not None:
            result["n_snapshots"] = _safe_int(row[0])
            result["n_negative"] = _safe_int(row[1])
    except Exception as exc:  # noqa: BLE001
        logger.warning("lg5 fetch_r6_daily_snapshots failed err=%s", exc)
    finally:
        put_conn(conn)
    return result


def _fetch_pending_candidate_pool() -> list[dict[str, Any]]:
    """Fetch all currently-pending live candidates (for R4 K + V_pending).
    取所有 pending live candidates（供 R4 K + V_pending 計算）。
    """
    conn = get_conn()
    if conn is None:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, payload
                FROM learning.mlde_param_applications
                WHERE engine_mode = 'live'
                  AND status = 'candidate'
                  AND application_type = 'live_promotion_candidate'
                  AND decision_lease_id IS NULL
                ORDER BY ts DESC
                LIMIT %s
                """,
                (R4_PENDING_CAP,),
            )
            rows = cur.fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            payload = row[1] if isinstance(row[1], dict) else (
                json.loads(row[1]) if isinstance(row[1], (str, bytes)) else {}
            )
            result.append({"id": row[0], "payload": payload})
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("lg5 fetch_pending_candidate_pool failed err=%s", exc)
        return []
    finally:
        put_conn(conn)


def _fetch_strategy_return_distribution(
    strategy_name: str,
    window_days: int = 7,
) -> Optional[tuple[float, float, float, float, int]]:
    """R3 input: per-fill net_bps distribution stats for the candidate strategy.
    R3 輸入：candidate strategy 的 per-fill net_bps 分佈統計量。

    Returns (mean, std, skew, kurt, n) or None on failure / insufficient data.
    Window: ``window_days`` (default 7d, fall back to 14d if 7d <100 samples).
    Returns sample skew/kurt (not population); n>=2 required.
    """
    if not strategy_name:
        return None
    conn = get_conn()
    if conn is None:
        return None
    try:
        for window in (window_days, 14):
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT net_bps_after_fee
                    FROM learning.mlde_edge_training_rows
                    WHERE ts > now() - (%s::int || ' days')::interval
                      AND engine_mode IN ('demo', 'live_demo')
                      AND attribution_chain_ok
                      AND net_bps_after_fee IS NOT NULL
                      AND strategy_name = %s
                    """,
                    (window, strategy_name),
                )
                rows = cur.fetchall()
            samples = [_safe_float(r[0], 0.0) for r in rows]
            n = len(samples)
            if n >= R3_MIN_SAMPLE_COUNT or window == 14:
                if n < 2:
                    return None
                mean = sum(samples) / n
                std = statistics.pstdev(samples)
                if std <= 0.0:
                    return (mean, 0.0, 0.0, 3.0, n)
                centered = [s - mean for s in samples]
                m2 = sum(c * c for c in centered) / n
                m3 = sum(c * c * c for c in centered) / n
                m4 = sum(c * c * c * c for c in centered) / n
                # Sample skewness / kurtosis (Pearson moment-based).
                # 樣本偏度 / 峰度（Pearson moment 基底）。
                skew = m3 / (m2 ** 1.5) if m2 > 0 else 0.0
                kurt = m4 / (m2 * m2) if m2 > 0 else 3.0
                return (mean, std, skew, kurt, n)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("lg5 fetch_strategy_return_distribution failed s=%s err=%s",
                       strategy_name, exc)
        return None
    finally:
        put_conn(conn)


# ═══════════════════════════════════════════════════════════════════════════════
# Audit emission / Audit row 寫入 (per RFC §2.3 + §13 V035)
# ═══════════════════════════════════════════════════════════════════════════════

def _emit_audit_row(
    event_type: str,
    candidate_id: Optional[int],
    verdict: ReviewVerdict,
) -> bool:
    """Write a single row to learning.governance_audit_log.
    寫一筆 row 至 learning.governance_audit_log。

    Returns True on success, False on failure (caller must downgrade verdict
    to ``defer defer_audit_write_failed`` per RFC §2.3 fail-closed).
    """
    conn = get_conn()
    if conn is None:
        logger.warning("lg5 audit emit: no DB conn (fail-closed)")
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO learning.governance_audit_log (
                    event_type, candidate_id, decision_lease_id,
                    verdict_decision, verdict_reason, rule_failures,
                    expected_net_bps_demo, expected_net_bps_live_adjusted,
                    expected_net_bps_deflated,
                    cost_regime_ratio, cost_regime_ratio_clamped,
                    psr_value, psr_n_samples, psr_skew, psr_kurt,
                    sr_0_deflation, v_pending_net_bps,
                    lease_ttl_ms, lease_revoke_triggers,
                    decided_by, payload
                ) VALUES (
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s,
                    %s, %s,
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s::jsonb
                )
                """,
                (
                    event_type,
                    candidate_id,
                    None,  # decision_lease_id NULL for non-approve paths (defer/reject); approve path uses _emit_approve_audit_and_persist_lease_atomic instead.
                    verdict.decision,
                    verdict.reason,
                    list(verdict.rule_failures),
                    verdict.expected_net_bps_demo,
                    verdict.expected_net_bps_live_adjusted,
                    verdict.expected_net_bps_deflated,
                    verdict.cost_regime_ratio,
                    verdict.cost_regime_ratio_clamped,
                    verdict.psr_value,
                    verdict.psr_n_samples,
                    verdict.psr_skew,
                    verdict.psr_kurt,
                    verdict.sr_0_deflation,
                    verdict.v_pending_net_bps,
                    verdict.lease_ttl_ms,
                    list(verdict.lease_revoke_triggers),
                    verdict.decided_by,
                    json.dumps({
                        "payload_snapshot": verdict.payload_snapshot,
                        "decided_at_ts": verdict.decided_at_ts,
                        # Fix 2 IMPL-2 (V035 has no column → JSONB sub-key, schema unchanged).
                        # Fix 2 IMPL-2：V035 無對應 column，寫入 payload JSONB sub-key 維持 schema 不變。
                        "attribution_sample_count": verdict.attribution_sample_count,
                    }, default=str),
                ),
            )
        conn.commit()
        return True
    except Exception as exc:  # noqa: BLE001 — fail-closed per RFC §2.3
        logger.warning("lg5 audit emit failed cand=%s err=%s", candidate_id, exc)
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False
    finally:
        put_conn(conn)


def _emit_approve_audit_and_persist_lease_atomic(
    candidate_id: int,
    verdict: ReviewVerdict,
    lease_id: str,
) -> bool:
    """Atomic single-transaction approve commit (HIGH-2 fix, RFC §2.3 line 215).
    單 transaction approve commit（HIGH-2 修，對齊 RFC §2.3 line 215）。

    Three writes share one cursor + commit:
      a. INSERT review_live_candidate audit row WITH decision_lease_id
      b. UPDATE mlde_param_applications.decision_lease_id
      c. INSERT lease_grant audit row (back-compat)
    Failure in any step → full rollback + return False; caller must
    downgrade verdict to ``defer_audit_write_failed`` (RFC §2.3 fail-closed).
    任一步失敗整批 rollback；caller 必須 downgrade 為 defer_audit_write_failed。
    """
    conn = get_conn()
    if conn is None:
        logger.warning("lg5 atomic approve commit: no DB conn (fail-closed)")
        return False
    try:
        with conn.cursor() as cur:
            # Step a: INSERT main audit row WITH lease_id populated
            cur.execute(
                """
                INSERT INTO learning.governance_audit_log (
                    event_type, candidate_id, decision_lease_id,
                    verdict_decision, verdict_reason, rule_failures,
                    expected_net_bps_demo, expected_net_bps_live_adjusted,
                    expected_net_bps_deflated,
                    cost_regime_ratio, cost_regime_ratio_clamped,
                    psr_value, psr_n_samples, psr_skew, psr_kurt,
                    sr_0_deflation, v_pending_net_bps,
                    lease_ttl_ms, lease_revoke_triggers,
                    decided_by, payload
                ) VALUES (
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s,
                    %s, %s,
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s::jsonb
                )
                """,
                (
                    "review_live_candidate",
                    candidate_id,
                    lease_id,  # populated atomically (HIGH-2 fix)
                    verdict.decision,
                    verdict.reason,
                    list(verdict.rule_failures),
                    verdict.expected_net_bps_demo,
                    verdict.expected_net_bps_live_adjusted,
                    verdict.expected_net_bps_deflated,
                    verdict.cost_regime_ratio,
                    verdict.cost_regime_ratio_clamped,
                    verdict.psr_value,
                    verdict.psr_n_samples,
                    verdict.psr_skew,
                    verdict.psr_kurt,
                    verdict.sr_0_deflation,
                    verdict.v_pending_net_bps,
                    verdict.lease_ttl_ms,
                    list(verdict.lease_revoke_triggers),
                    verdict.decided_by,
                    json.dumps({
                        "payload_snapshot": verdict.payload_snapshot,
                        "decided_at_ts": verdict.decided_at_ts,
                        # Fix 2 IMPL-2 (V035 has no column → JSONB sub-key, schema unchanged).
                        # Fix 2 IMPL-2：V035 無對應 column，寫入 payload JSONB sub-key 維持 schema 不變。
                        "attribution_sample_count": verdict.attribution_sample_count,
                    }, default=str),
                ),
            )
            # Step b: UPDATE candidate row decision_lease_id
            cur.execute(
                """
                UPDATE learning.mlde_param_applications
                SET decision_lease_id = %s
                WHERE id = %s
                """,
                (lease_id, candidate_id),
            )
            # Step c: INSERT lease_grant secondary audit row (back-compat)
            cur.execute(
                """
                INSERT INTO learning.governance_audit_log (
                    event_type, candidate_id, decision_lease_id,
                    verdict_decision, verdict_reason,
                    rule_failures, lease_revoke_triggers,
                    decided_by
                ) VALUES (
                    'lease_grant', %s, %s,
                    'approve', 'lease_persisted',
                    '{}', '{}',
                    'GovernanceHub.review_live_candidate'
                )
                """,
                (candidate_id, lease_id),
            )
        conn.commit()
        return True
    except Exception as exc:  # noqa: BLE001 — fail-closed per RFC §2.3
        logger.warning(
            "lg5 atomic approve commit failed cand=%s lease=%s err=%s",
            candidate_id, lease_id, exc,
        )
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False
    finally:
        put_conn(conn)


# ═══════════════════════════════════════════════════════════════════════════════
# Verdict factory / Verdict 建構輔助
# ═══════════════════════════════════════════════════════════════════════════════

def _make_verdict(
    decision: Literal["approve", "reject", "defer"],
    reason: str,
    *,
    rule_failures: Optional[Iterable[str]] = None,
    expected_net_bps_demo: float = 0.0,
    expected_net_bps_live_adjusted: Optional[float] = None,
    expected_net_bps_deflated: Optional[float] = None,
    cost_regime_ratio: Optional[float] = None,
    cost_regime_ratio_clamped: Optional[float] = None,
    psr_value: Optional[float] = None,
    psr_n_samples: Optional[int] = None,
    psr_skew: Optional[float] = None,
    psr_kurt: Optional[float] = None,
    sr_0_deflation: Optional[float] = None,
    v_pending_net_bps: Optional[float] = None,
    lease_ttl_ms: Optional[int] = None,
    lease_revoke_triggers: Optional[Iterable[str]] = None,
    decided_by: str = "GovernanceHub.review_live_candidate",
    payload_snapshot: Optional[dict] = None,
    attribution_sample_count: Optional[int] = None,
) -> ReviewVerdict:
    """Build a ReviewVerdict with sane defaults / 建構 ReviewVerdict 帶安全預設。"""
    return ReviewVerdict(
        decision=decision,
        reason=reason,
        rule_failures=list(rule_failures or []),
        expected_net_bps_demo=expected_net_bps_demo,
        expected_net_bps_live_adjusted=expected_net_bps_live_adjusted,
        expected_net_bps_deflated=expected_net_bps_deflated,
        cost_regime_ratio=cost_regime_ratio,
        cost_regime_ratio_clamped=cost_regime_ratio_clamped,
        psr_value=psr_value,
        psr_n_samples=psr_n_samples,
        psr_skew=psr_skew,
        psr_kurt=psr_kurt,
        sr_0_deflation=sr_0_deflation,
        v_pending_net_bps=v_pending_net_bps,
        lease_ttl_ms=lease_ttl_ms,
        lease_revoke_triggers=list(lease_revoke_triggers or []),
        decided_at_ts=_now_ms(),
        decided_by=decided_by,
        payload_snapshot=payload_snapshot or {},
        attribution_sample_count=attribution_sample_count,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Pure rule evaluators / 純函數規則評估器 — no DB access, easy to unit test
# ═══════════════════════════════════════════════════════════════════════════════

def evaluate_r1(
    live_maker_fill_rate: float,
    demo_maker_fill_rate: float,
) -> tuple[bool, str]:
    """R1 Live cost regime check (RFC §3 R1, MF-Q1).
    R1 Live 成本制度檢查（RFC §3 R1, MF-Q1）。

    Pass:
        live_maker >= demo_maker × 0.85  AND  live_maker >= 0.15
    """
    if live_maker_fill_rate < R1_MAKER_FILL_FLOOR:
        return False, f"R1: live maker {live_maker_fill_rate:.3f} below floor {R1_MAKER_FILL_FLOOR}"
    if demo_maker_fill_rate > 0.0 and live_maker_fill_rate < demo_maker_fill_rate * R1_MAKER_FILL_RATIO:
        return False, (
            f"R1: live maker {live_maker_fill_rate:.3f} < demo {demo_maker_fill_rate:.3f} × "
            f"{R1_MAKER_FILL_RATIO}"
        )
    return True, "R1 pass"


def evaluate_r2(
    expected_net_bps_demo: float,
    live_maker_fill_rate: float,
    demo_maker_fill_rate: float,
    live_avg_fee_bps: float,
    demo_avg_fee_bps: float,
    live_avg_slippage_bps: float,
    demo_avg_slippage_bps: float,
) -> tuple[bool, str, float, float, float]:
    """R2 distribution-shift haircut (RFC §3 R2, MF-Q2).
    R2 分佈漂移 haircut（RFC §3 R2, MF-Q2）。

    Returns:
        (pass, message, cost_regime_ratio, cost_regime_ratio_clamped,
         expected_net_bps_live_adjusted)

    Formula:
        ratio = (live_maker × (1 - live_taker_fee + live_maker_rebate)) /
                (demo_maker × (1 - demo_taker_fee + demo_maker_rebate))

    Simplification: avg_fee_bps already encodes the maker_rebate / taker_fee
    blended cost; we use ``(1 - avg_fee_bps/10000)`` as the multiplier.
    """
    # Guard: demo baseline missing → cannot compute ratio
    # 防護：demo baseline 缺失 → 無法計算 ratio
    if demo_maker_fill_rate <= 0.0:
        return False, "R2: demo maker_fill_rate is zero (baseline missing)", 0.0, R2_CLAMP_LOW, 0.0

    live_mult = max(0.0, 1.0 - live_avg_fee_bps / 10000.0)
    demo_mult = max(1e-9, 1.0 - demo_avg_fee_bps / 10000.0)
    ratio = (live_maker_fill_rate * live_mult) / (demo_maker_fill_rate * demo_mult)
    ratio_clamped = max(R2_CLAMP_LOW, min(R2_CLAMP_HIGH, ratio))
    slippage_diff = live_avg_slippage_bps - demo_avg_slippage_bps
    adjusted = expected_net_bps_demo * ratio_clamped - slippage_diff
    if adjusted < R2_PASS_THRESHOLD_BPS:
        return False, (
            f"R2: adjusted {adjusted:.2f}bps < {R2_PASS_THRESHOLD_BPS}bps "
            f"(ratio={ratio:.3f} clamped={ratio_clamped:.3f} slip_diff={slippage_diff:.2f})"
        ), ratio, ratio_clamped, adjusted
    return True, "R2 pass", ratio, ratio_clamped, adjusted


def evaluate_r3(
    n_strategy_fills: int,
    distribution_stats: Optional[tuple[float, float, float, float, int]],
) -> tuple[Literal["pass", "fail", "defer"], str, Optional[float], Optional[int],
           Optional[float], Optional[float]]:
    """R3 PSR(0) check (RFC §3 R3, MF-Q3).
    R3 PSR(0) 檢查（RFC §3 R3, MF-Q3）。

    Returns:
        (status, message, psr_value, psr_n, psr_skew, psr_kurt)
        status: "pass" / "fail" / "defer" (data insufficient)
    """
    if n_strategy_fills < R3_MIN_SAMPLE_COUNT and (
        distribution_stats is None or distribution_stats[4] < R3_MIN_SAMPLE_COUNT
    ):
        return "defer", f"R3: n={n_strategy_fills} < {R3_MIN_SAMPLE_COUNT} (defer)", None, n_strategy_fills, None, None
    if distribution_stats is None:
        return "defer", "R3: distribution stats unavailable (defer)", None, n_strategy_fills, None, None
    mean, std, skew, kurt, n = distribution_stats
    if std <= 0.0:
        return "fail", "R3: std=0 (no variance, cannot compute PSR)", 0.0, n, skew, kurt
    sr = mean / std
    psr = _compute_psr(sr_observed=sr, n=n, skew=skew, kurt=kurt, sr_benchmark=0.0)
    if psr < R3_PSR_THRESHOLD:
        return "fail", f"R3: PSR(0)={psr:.3f} < {R3_PSR_THRESHOLD}", psr, n, skew, kurt
    return "pass", f"R3: PSR(0)={psr:.3f}", psr, n, skew, kurt


def evaluate_r4(
    expected_net_bps_live_adjusted: float,
    pending_pool: list[dict[str, Any]],
    expected_net_bps_demo: float,
    worst_case_override: bool = False,
) -> tuple[Literal["pass", "fail", "skip"], str, float, Optional[float], Optional[float]]:
    """R4 DSR / multiple-testing deflation (RFC §3 R4, MF-Q4).
    R4 DSR / 多重測試 deflation（RFC §3 R4, MF-Q4）。

    Returns:
        (status, message, expected_net_bps_deflated, sr_0_deflation, v_pending)
        status: "pass" / "fail" / "skip" (K<5)
    """
    K = len(pending_pool)
    if K < R4_TRIGGER_PENDING_COUNT:
        if worst_case_override and K <= 1:
            deflated = R4_FALLBACK_DEMO_FACTOR * expected_net_bps_demo
            if deflated < R2_PASS_THRESHOLD_BPS:
                return "fail", f"R4 worst-case override: {deflated:.2f}bps < {R2_PASS_THRESHOLD_BPS}", deflated, None, None
            return "pass", f"R4 worst-case override pass: {deflated:.2f}bps", deflated, None, None
        return "skip", f"R4: K={K} < {R4_TRIGGER_PENDING_COUNT} (skip, informational)", expected_net_bps_live_adjusted, None, None

    # Compute V_pending across pool (use each pool member's own
    # expected_net_bps_live_adjusted if available in payload, else fall back
    # to demo expected as proxy — conservative).
    # 計算 K 個 pool 成員 R2 後 expected 的方差。
    pool_adjusted: list[float] = []
    for member in pending_pool:
        payload = member.get("payload") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:  # noqa: BLE001
                payload = {}
        review = payload.get("review_verdict") if isinstance(payload, dict) else None
        if isinstance(review, dict) and review.get("expected_net_bps_live_adjusted") is not None:
            pool_adjusted.append(_safe_float(review["expected_net_bps_live_adjusted"]))
        else:
            # Fallback: payload.demo_cost_baseline.avg_realized_net_bps_7d as proxy
            baseline = payload.get("demo_cost_baseline") if isinstance(payload, dict) else None
            if isinstance(baseline, dict):
                pool_adjusted.append(_safe_float(baseline.get("avg_realized_net_bps_7d", 0.0)))
            else:
                pool_adjusted.append(0.0)

    if len(pool_adjusted) < 2:
        return "skip", f"R4: pool variance unavailable (n={len(pool_adjusted)})", expected_net_bps_live_adjusted, None, None
    v_pending = statistics.pvariance(pool_adjusted)
    sr_0 = _compute_bailey_ldp_sr_0(K, v_pending)
    deflated = expected_net_bps_live_adjusted - sr_0
    if deflated < R2_PASS_THRESHOLD_BPS:
        return "fail", (
            f"R4: deflated {deflated:.2f}bps < {R2_PASS_THRESHOLD_BPS} "
            f"(SR_0={sr_0:.2f}, V_pending={v_pending:.2f}, K={K})"
        ), deflated, sr_0, v_pending
    return "pass", f"R4: deflated {deflated:.2f}bps (SR_0={sr_0:.2f}, K={K})", deflated, sr_0, v_pending


def evaluate_r5(
    expected_net_bps_demo: float,
    demo_avg_fee_bps: float,
    demo_avg_slippage_bps: float,
    live_avg_fee_bps: float,
    live_avg_slippage_bps: float,
) -> tuple[Literal["pass", "warn", "fail"], str, float]:
    """R5 cost_edge_ratio gate (RFC §3 R5, MF-Q5).
    R5 cost_edge_ratio 門控（RFC §3 R5, MF-Q5）。

    Uses demo gross baseline (avoid R2 double-count):
        realized_gross_edge_bps_demo = expected_net_bps_demo
                                     + (demo_avg_fee_bps + demo_avg_slippage_bps)
        cost_edge_ratio = (live_avg_fee_bps + live_avg_slippage_bps) /
                          max(realized_gross_edge_bps_demo, 0.01)
    """
    realized_gross_demo = expected_net_bps_demo + demo_avg_fee_bps + demo_avg_slippage_bps
    realized_cost_live = live_avg_fee_bps + live_avg_slippage_bps
    ratio = realized_cost_live / max(realized_gross_demo, 0.01)
    if ratio < R5_PASS_CEIL:
        return "pass", f"R5: cost_edge_ratio={ratio:.3f} < {R5_PASS_CEIL} pass", ratio
    if ratio < R5_WARN_CEIL:
        return "warn", f"R5: cost_edge_ratio={ratio:.3f} in [{R5_PASS_CEIL},{R5_WARN_CEIL}) warn", ratio
    return "fail", f"R5: cost_edge_ratio={ratio:.3f} >= {R5_WARN_CEIL} fail", ratio


def evaluate_r6(
    daily_snapshots: dict[str, int],
    live_maker_fill_rate: float,
    pipeline_silent_gap_fail: bool,
    auth_effective: bool,
) -> tuple[bool, str]:
    """R6 hard veto (RFC §3 R6, MF-Q6).
    R6 硬否決（RFC §3 R6, MF-Q6）。

    Returns (vetoed, reason). vetoed=True → caller must reject_hard_veto.

    Per RFC §3 R6 + line 320/347: data gap (n_snap < 7) does NOT veto here.
    Caller (review_live_candidate) is responsible for the data-gap pre-check
    and must defer with reason ``defer_data_insufficient`` BEFORE invoking
    evaluate_r6 — fail-closed default. Strict equality below ensures we never
    silently fall through when n_snap is short.
    依 RFC §3 R6 + line 320/347：data gap (n_snap < 7) 不在這裡 veto。
    由 caller (review_live_candidate) 在進入 evaluate_r6 前先做 data-gap
    pre-check 並 defer (defer_data_insufficient) — fail-closed default。
    下面採嚴格相等避免 n_snap 不足時 silent fall-through。
    """
    n_snap = daily_snapshots.get("n_snapshots", 0)
    n_neg = daily_snapshots.get("n_negative", 0)
    if n_snap == R6_DAILY_NEG_SNAPSHOTS_REQUIRED and n_neg == R6_DAILY_NEG_SNAPSHOTS_REQUIRED:
        return True, f"R6 hard veto: {n_neg}/{n_snap} daily snapshots negative"
    if live_maker_fill_rate < R6_MAKER_FILL_CATASTROPHIC_FLOOR:
        return True, f"R6 hard veto: live maker {live_maker_fill_rate:.3f} < catastrophic floor {R6_MAKER_FILL_CATASTROPHIC_FLOOR}"
    if pipeline_silent_gap_fail:
        return True, "R6 hard veto: [22] trading_pipeline_silent_gap FAIL"
    if not auth_effective:
        return True, "R6 hard veto: authorization not effective"
    return False, "R6 pass"


# ═══════════════════════════════════════════════════════════════════════════════
# Lease TTL selection / Lease TTL 選擇 (RFC §4)
# ═══════════════════════════════════════════════════════════════════════════════

def _select_lease_ttl_ms(
    r5_status: str,
    r3_status: str,
    psr_value: Optional[float],
    learning_period: bool = False,
) -> int:
    """Pick lease TTL ms per RFC §4 band logic.
    依 RFC §4 帶狀邏輯選 lease TTL (ms)。
    """
    ttl = LEASE_TTL_DEFAULT_MS
    if r5_status == "warn":
        ttl = min(ttl, LEASE_TTL_R5_WARN_MS)
    if r3_status == "pass" and psr_value is not None and R3_PSR_THRESHOLD <= psr_value < R3_PSR_BORDERLINE_HIGH:
        ttl = min(ttl, LEASE_TTL_R3_BORDERLINE_MS)
    if learning_period:
        ttl = min(ttl, LEASE_TTL_LEARNING_PERIOD_MS)
    return ttl


# ═══════════════════════════════════════════════════════════════════════════════
# Main entry point / 主入口
# ═══════════════════════════════════════════════════════════════════════════════

def review_live_candidate(
    hub: Any,
    candidate_id: int,
    *,
    decided_by: str = "GovernanceHub.review_live_candidate",
    learning_period: bool = False,
    pipeline_silent_gap_fail: bool = False,
    worst_case_r4_override: bool = False,
) -> ReviewVerdict:
    """LG-5 consumer entry point. Evaluates one live candidate per RFC v2.
    LG-5 consumer 入口。對單一 live candidate 執行 RFC v2 §3 全套規則。

    Lock contention safety pattern (PA §9 #2):
      1. Read candidate row + payload   (DB only, NO hub lock)
      2. Read live cost regime + R6 daily snapshots + pending pool
                                       (DB only, NO hub lock)
      3. Compute verdict in memory     (no DB, no lock)
      Non-approve verdicts (reject/defer): emit standalone audit row + return.
      Approve verdict path (HIGH-2 round 2 atomicity fix, RFC §2.3 line 215):
        4. ``hub.acquire_lease()`` (hub manages its own lock)
           fail → defer_lease_acquisition_failed + standalone audit
        5. Atomic single-tx commit:
             a. INSERT audit row (event=review_live_candidate) WITH lease_id
             b. UPDATE mlde_param_applications.decision_lease_id
             c. INSERT lease_grant audit row (back-compat)
           fail (any step) → rollback + downgrade to defer_audit_write_failed

    Args:
        hub: GovernanceHub instance (for ``acquire_lease`` + ``is_authorized``).
        candidate_id: PK of learning.mlde_param_applications row.
        decided_by: trigger source string for audit (e.g. ".scheduler",
                    ".operator_manual:<actor>", ".bulk_re_evaluation").
        learning_period: if True, cap lease TTL to 2h (first 30d post-deploy).
        pipeline_silent_gap_fail: caller-supplied [22] healthcheck status.
        worst_case_r4_override: if True and K<5, apply 0.25 × demo fallback.

    Returns:
        ReviewVerdict (always — function never raises; fail-soft + audit).
    """
    decided_by_full = decided_by

    # ── Step 1: read candidate row (NO hub lock held) ─────────────────────────
    candidate = _fetch_candidate_row(candidate_id)
    if candidate is None:
        verdict = _make_verdict(
            "defer", "defer_data_insufficient",
            decided_by=decided_by_full,
        )
        _emit_audit_row("review_live_candidate", candidate_id, verdict)
        return verdict

    payload = candidate.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:  # noqa: BLE001
            payload = {}
    if not isinstance(payload, dict):
        payload = {}

    schema_version = str(payload.get("schema_version") or "")
    if schema_version != EXPECTED_SCHEMA_VERSION:
        verdict = _make_verdict(
            "reject", "reject_schema_unknown",
            rule_failures=["schema_version"],
            payload_snapshot={"schema_version_seen": schema_version},
            decided_by=decided_by_full,
        )
        _emit_audit_row("review_live_candidate", candidate_id, verdict)
        return verdict

    # Extract baseline values from payload (producer is fail-soft → may be 0).
    # 從 payload 取出 baseline（producer fail-soft，可能為 0）。
    demo_cost_baseline = payload.get("demo_cost_baseline") or {}
    demo_realized_window = payload.get("demo_realized_window") or {}
    attribution_dict = payload.get("demo_attribution_chain_ratio_by_strategy") or {}
    if not isinstance(attribution_dict, dict):
        attribution_dict = {}
    # Fix 2 IMPL-2 PA Q3: per-strategy sample count dict for R-meta low-sample
    # defer; missing (pre-Fix 2 payload) → None → skip sample check (preserves
    # 27 pending candidates per RFC §6.1).
    # Fix 2 IMPL-2 PA Q3：sample dict；缺 → None → 略過 sample check（preserves 27 pending）。
    _raw_smp = payload.get("demo_attribution_sample_count_by_strategy")
    sample_count_dict: Optional[dict[str, int]] = _raw_smp if isinstance(_raw_smp, dict) else None

    # Source recommendation row for expected_net_bps_demo (column on
    # mlde_shadow_recommendations, not on mlde_param_applications).
    # 取 source recommendation 的 expected_net_bps_demo（mlde_param_applications
    # 沒有此欄位，需從 mlde_shadow_recommendations 撈）。
    rec_id = candidate.get("recommendation_id")
    source_rec = _fetch_source_recommendation(rec_id) if rec_id is not None else None
    expected_net_bps_demo = _safe_float(
        (source_rec or {}).get("expected_net_bps", 0.0), 0.0
    )

    # Candidate strategy = target_name (mlde_demo_applier writes this);
    # fallback to source_rec.strategy_name.
    # candidate strategy = target_name；fallback to source_rec.strategy_name。
    candidate_strategy = str(
        candidate.get("target_name")
        or (source_rec or {}).get("strategy_name", "")
        or ""
    )

    # ── Step 2: read live regime / R6 snapshots / pending pool (NO hub lock) ──
    live_regime = _fetch_live_cost_regime()
    daily_snapshots = _fetch_r6_daily_snapshots()
    pending_pool = _fetch_pending_candidate_pool()

    # Auth effective check — query hub but do NOT hold lock during DB reads.
    # auth 有效性 — 查 hub 但不持鎖跑 DB read。
    try:
        auth_effective = bool(hub.is_authorized()) if hasattr(hub, "is_authorized") else True
    except Exception as exc:  # noqa: BLE001
        logger.warning("lg5 review: hub.is_authorized() failed: %s", exc)
        auth_effective = False

    # ── Step 3: compute verdict in memory (no DB, no lock) ────────────────────
    rule_failures: list[str] = []
    demo_maker = _safe_float(demo_cost_baseline.get("maker_fill_rate_7d"))
    demo_fee_bps = _safe_float(demo_cost_baseline.get("avg_realized_fee_bps_7d"))
    demo_slip_bps = _safe_float(demo_cost_baseline.get("avg_realized_slippage_bps_7d"))
    live_maker = live_regime["maker_fill_rate"]
    live_fee_bps = live_regime["avg_fee_bps"]
    live_slip_bps = live_regime["avg_slippage_bps"]

    # ── R6 data-gap pre-check (RFC §3 R6 line 320/347 fail-closed) ────────────
    # n_snap < 7 → defer; evaluate_r6 itself now requires strict n_snap == 7
    # to veto, so this pre-check is the only place data-gap is caught.
    # n_snap < 7 → defer；evaluate_r6 改為嚴格 n_snap == 7 才 veto，data gap 由本處捕捉。
    n_snap_pre = daily_snapshots.get("n_snapshots", 0)
    if n_snap_pre < R6_DAILY_NEG_SNAPSHOTS_REQUIRED:
        verdict = _make_verdict(
            "defer", "defer_data_insufficient",
            rule_failures=["R6_data_gap"],
            expected_net_bps_demo=expected_net_bps_demo,
            payload_snapshot={
                "r6_data_gap": True,
                "n_snapshots": n_snap_pre,
                "n_negative": daily_snapshots.get("n_negative", 0),
                "required": R6_DAILY_NEG_SNAPSHOTS_REQUIRED,
            },
            decided_by=decided_by_full,
        )
        _emit_audit_row("review_live_candidate", candidate_id, verdict)
        return verdict

    # R6 first (per RFC §3: hard veto覆蓋個別 rule).
    # R6 先檢查（per RFC §3：hard veto 覆蓋個別 rule）。
    r6_vetoed, r6_msg = evaluate_r6(
        daily_snapshots=daily_snapshots,
        live_maker_fill_rate=live_maker,
        pipeline_silent_gap_fail=pipeline_silent_gap_fail,
        auth_effective=auth_effective,
    )
    if r6_vetoed:
        verdict = _make_verdict(
            "reject", "reject_hard_veto",
            rule_failures=["R6"],
            expected_net_bps_demo=expected_net_bps_demo,
            payload_snapshot={"r6_msg": r6_msg, "live_regime": live_regime,
                              "daily_snapshots": daily_snapshots},
            decided_by=decided_by_full,
        )
        _emit_audit_row("review_live_candidate", candidate_id, verdict)
        return verdict

    # R-meta per-strategy gate (Fix 2 IMPL-2-consumer split): helper resolves
    # unknown / low_sample (Fix 2 PA Q3) / ratio fail in one call.
    # R-meta gate：helper 一次解 unknown / low_sample / ratio fail。
    r_meta_kwargs, r_meta_sample_n, r_meta_msg = build_r_meta_gate_verdict_kwargs(
        candidate_strategy, attribution_dict, sample_count_dict,
        expected_net_bps_demo, decided_by_full,
    )
    if r_meta_kwargs is not None:
        verdict = _make_verdict(**r_meta_kwargs)
        _emit_audit_row("review_live_candidate", candidate_id, verdict)
        return verdict

    # R1
    r1_pass, r1_msg = evaluate_r1(live_maker, demo_maker)
    if not r1_pass:
        rule_failures.append("R1")

    # R2
    r2_pass, r2_msg, cost_ratio, cost_ratio_clamped, adjusted = evaluate_r2(
        expected_net_bps_demo=expected_net_bps_demo,
        live_maker_fill_rate=live_maker,
        demo_maker_fill_rate=demo_maker,
        live_avg_fee_bps=live_fee_bps,
        demo_avg_fee_bps=demo_fee_bps,
        live_avg_slippage_bps=live_slip_bps,
        demo_avg_slippage_bps=demo_slip_bps,
    )
    if not r2_pass:
        rule_failures.append("R2")

    # R3
    n_strategy_fills = _safe_int(demo_realized_window.get("n_strategy_fills"))
    distribution = _fetch_strategy_return_distribution(candidate_strategy, window_days=7)
    r3_status, r3_msg, psr_value, psr_n, psr_skew, psr_kurt = evaluate_r3(
        n_strategy_fills, distribution
    )
    if r3_status == "defer":
        verdict = _make_verdict(
            "defer", "defer_data_insufficient",
            rule_failures=["R3"],
            expected_net_bps_demo=expected_net_bps_demo,
            expected_net_bps_live_adjusted=adjusted if r2_pass else None,
            cost_regime_ratio=cost_ratio,
            cost_regime_ratio_clamped=cost_ratio_clamped,
            psr_n_samples=psr_n,
            payload_snapshot={"r3_msg": r3_msg},
            decided_by=decided_by_full,
        )
        _emit_audit_row("review_live_candidate", candidate_id, verdict)
        return verdict
    if r3_status == "fail":
        rule_failures.append("R3")

    # R4
    r4_status, r4_msg, deflated, sr_0, v_pending = evaluate_r4(
        expected_net_bps_live_adjusted=adjusted,
        pending_pool=pending_pool,
        expected_net_bps_demo=expected_net_bps_demo,
        worst_case_override=worst_case_r4_override,
    )
    if r4_status == "fail":
        rule_failures.append("R4")
    elif r4_status == "skip":
        # informational — not a failure
        # 資訊性 — 非 failure
        rule_failures.append("r4_skipped_insufficient_pool")

    # R5
    r5_status, r5_msg, r5_ratio = evaluate_r5(
        expected_net_bps_demo=expected_net_bps_demo,
        demo_avg_fee_bps=demo_fee_bps,
        demo_avg_slippage_bps=demo_slip_bps,
        live_avg_fee_bps=live_fee_bps,
        live_avg_slippage_bps=live_slip_bps,
    )
    if r5_status == "fail":
        rule_failures.append("R5")

    # ── Decide overall verdict ────────────────────────────────────────────────
    # Any of R1-R5 fail (excluding informational r4_skipped) → reject.
    # R1-R5 任一 fail（不含 informational r4_skipped）→ reject。
    blocking_failures = [rf for rf in rule_failures if rf != "r4_skipped_insufficient_pool"]

    if blocking_failures:
        # Pick reason by priority order R1 → R2 → R3 → R5 → R4
        # 依優先序選 reason
        reason_map = {
            "R1": "reject_cost_regime_drift",
            "R2": "reject_haircut_negative",
            "R3": "reject_psr_below_floor",
            "R5": "reject_cost_edge_ratio",
            "R4": "reject_dsr_deflated",
        }
        reason = next(
            (reason_map[r] for r in ("R1", "R2", "R3", "R5", "R4") if r in blocking_failures),
            "reject_haircut_negative",
        )
        verdict = _make_verdict(
            "reject", reason,
            rule_failures=rule_failures,
            expected_net_bps_demo=expected_net_bps_demo,
            expected_net_bps_live_adjusted=adjusted,
            expected_net_bps_deflated=deflated if r4_status != "skip" else None,
            cost_regime_ratio=cost_ratio,
            cost_regime_ratio_clamped=cost_ratio_clamped,
            psr_value=psr_value,
            psr_n_samples=psr_n,
            psr_skew=psr_skew,
            psr_kurt=psr_kurt,
            sr_0_deflation=sr_0,
            v_pending_net_bps=v_pending,
            payload_snapshot={
                "r1_msg": r1_msg, "r2_msg": r2_msg, "r3_msg": r3_msg,
                "r4_msg": r4_msg, "r5_msg": r5_msg,
            },
            decided_by=decided_by_full,
        )
        if not _emit_audit_row("review_live_candidate", candidate_id, verdict):
            verdict = _make_verdict(
                "defer", "defer_audit_write_failed",
                rule_failures=rule_failures,
                expected_net_bps_demo=expected_net_bps_demo,
                decided_by=decided_by_full,
            )
        return verdict

    # ── All R1-R5 pass + R6 not vetoed + R-meta pass → approve path ───────────
    lease_ttl_ms = _select_lease_ttl_ms(
        r5_status=r5_status,
        r3_status=r3_status,
        psr_value=psr_value,
        learning_period=learning_period,
    )

    verdict = _make_verdict(
        "approve", "approve_within_envelope",
        rule_failures=rule_failures,  # may contain only "r4_skipped_insufficient_pool"
        expected_net_bps_demo=expected_net_bps_demo,
        expected_net_bps_live_adjusted=adjusted,
        expected_net_bps_deflated=deflated if r4_status != "skip" else None,
        cost_regime_ratio=cost_ratio,
        cost_regime_ratio_clamped=cost_ratio_clamped,
        psr_value=psr_value,
        psr_n_samples=psr_n,
        psr_skew=psr_skew,
        psr_kurt=psr_kurt,
        sr_0_deflation=sr_0,
        v_pending_net_bps=v_pending,
        lease_ttl_ms=lease_ttl_ms,
        lease_revoke_triggers=list(DEFAULT_LEASE_REVOKE_TRIGGERS),
        decided_by=decided_by_full,
        payload_snapshot={
            "r1_msg": r1_msg, "r2_msg": r2_msg, "r3_msg": r3_msg,
            "r4_msg": r4_msg, "r5_msg": r5_msg, "r_meta_msg": r_meta_msg,
        },
    )

    # ── Step 4: hub.acquire_lease() FIRST (HIGH-2, RFC §2.3 line 215) ────────
    # Step 4 acquire (fail → defer); Step 5 atomic single-tx audit+UPDATE.
    # KNOWN GAP MEDIUM-2 round 1: authorization.json has no ``scope.lease_scopes``
    # — ``_auth_permits_scope`` returns True when empty, so dynamic
    # ``LIVE_CANDIDATE_APPLY:*`` is permitted today. If operator later
    # schema-binds without ``LIVE_CANDIDATE_APPLY`` (or wildcard), this path
    # runtime-fails to ``defer_lease_acquisition_failed`` (flagged to PA).
    # MEDIUM-2：authorization.json 目前無 scope.lease_scopes，已 flag 給 PA 補 §4。
    lease_id: Optional[str] = None
    try:
        lease_id = hub.acquire_lease(
            intent_id=f"live_candidate_{candidate_id}",
            scope=f"LIVE_CANDIDATE_APPLY:{candidate_strategy}:{candidate.get('target_name', '')}",
            ttl_seconds=lease_ttl_ms / 1000.0,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("lg5 review: acquire_lease raised cand=%s err=%s", candidate_id, exc)
        lease_id = None

    if not lease_id:
        # Lease acquisition failed → defer + standalone audit (no lease persisted)
        # Lease 取得失敗 → defer + 獨立 audit（不持久化 lease）
        downgrade = _make_verdict(
            "defer", "defer_lease_acquisition_failed",
            rule_failures=rule_failures,
            expected_net_bps_demo=expected_net_bps_demo,
            expected_net_bps_live_adjusted=adjusted,
            expected_net_bps_deflated=deflated if r4_status != "skip" else None,
            cost_regime_ratio=cost_ratio,
            cost_regime_ratio_clamped=cost_ratio_clamped,
            psr_value=psr_value,
            psr_n_samples=psr_n,
            psr_skew=psr_skew,
            psr_kurt=psr_kurt,
            sr_0_deflation=sr_0,
            v_pending_net_bps=v_pending,
            decided_by=decided_by_full,
            payload_snapshot=verdict.payload_snapshot,
        )
        _emit_audit_row("review_live_candidate", candidate_id, downgrade)
        return downgrade

    # ── Step 5: atomic single-tx commit (audit WITH lease_id + UPDATE candidate) ─
    # HIGH-2 修：失敗 → rollback + downgrade。
    if not _emit_approve_audit_and_persist_lease_atomic(
        candidate_id, verdict, lease_id
    ):
        # Atomic commit failed. candidate.decision_lease_id remains NULL.
        # Hub already activated lease in memory; rely on ExpiryGuardian TTL.
        # 原子寫入失敗；hub 端 lease 在 memory active，倚靠 TTL 回收。
        logger.warning(
            "lg5 review: atomic approve commit failed cand=%s lease=%s — "
            "downgrading to defer_audit_write_failed; lease orphaned until TTL",
            candidate_id, lease_id,
        )
        downgrade = _make_verdict(
            "defer", "defer_audit_write_failed",
            rule_failures=rule_failures,
            expected_net_bps_demo=expected_net_bps_demo,
            expected_net_bps_live_adjusted=adjusted,
            decided_by=decided_by_full,
            payload_snapshot={
                "atomic_commit_failed": True,
                "orphaned_lease_id": lease_id,
            },
        )
        # Best-effort secondary audit (independent conn; primary tx rolled back).
        _emit_audit_row("review_live_candidate", candidate_id, downgrade)
        return downgrade

    return verdict
