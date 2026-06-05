"""REF-20 P4-S11 evidence-source filter helpers for ``mlde_demo_applier``.

模組目的 / Module purpose:
    為 ``mlde_demo_applier._fetch_pending`` 提供 forward-compat schema 探測
    + WHERE-fragment 構造 helper。獨立檔案以避免 ``mlde_demo_applier.py``
    超出 CLAUDE.md §九 1500 LOC 硬上限（pre-existing baseline 1541 LOC 屬
    exception clause 範圍，本 task 不擴大檔身）。

    Provide forward-compat schema probe + WHERE-fragment builder for
    ``mlde_demo_applier._fetch_pending``. Split out to keep
    ``mlde_demo_applier.py`` under the CLAUDE.md §九 1500 LOC hard cap
    (pre-existing baseline 1541 LOC sits inside the exception clause; this
    task must not grow the file).

REF-20 V3 §4.2 P4-S11 contract:
    1. evidence_source_tier IN ('real_outcome', 'calibrated_replay',
       'synthetic_replay', 'counterfactual_replay', 'mlde_advisor').
    2. replay_experiment_id IS NULL (legacy real_outcome) OR points at an
       active manifest in ``replay.experiments`` with
       (manifest_hash NOT NULL AND expires_at > now()
        AND status NOT IN ('cancelled','expired','compromised')).
    3. Schema 任一字段缺（V040 column 未上線 / replay.experiments stub 缺
       expires_at|status）→ graceful fallback：跳過該 column 上的 filter
       並由本 helper 內部註明 forward-compat。

關聯文件 / Related docs:
    - docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
      §4 Wave 6 R20-P4-S11
    - docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md
      §4.2 + §12 #6 + #22
    - sql/migrations/V036__replay_evidence_source_guard.sql (allowlist
      single source of truth)
    - sql/migrations/V038-V040__add/backfill/finalize_evidence_source_tier.sql

Hard contracts (E2 / E3 / FA review focus):
    - 不執行 INSERT / UPDATE — 純 SELECT helper
    - 探測 fail-soft：SQL exception → caller 回 legacy 行為
    - 不依賴 V### 物理 column 必存在；schema drift 不破 caller
    - 與 ``mlde_demo_applier`` 共享 ``_EVIDENCE_SOURCE_TIER_ALLOWLIST`` 為
      single source of truth；任何修改需同步 V036 / V040 CHECK enum
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# REF-20 P4-S11 evidence_source_tier 白名單 — applier 只接受 verified
# replay-derived 或 real_outcome row。對齊 V3 §4.2 + V038-V040 retrofit
# 後 column NOT NULL + CHECK enum 限制；'mlde_advisor' 為向前相容 alias，
# 上游 producer 切換 'ml_shadow' 後可移除。
# REF-20 P4-S11 evidence_source_tier allowlist — applier accepts only
# verified replay-derived or real_outcome rows. Aligned with V3 §4.2 +
# V038-V040 retrofit (column NOT NULL + CHECK enum). 'mlde_advisor' is
# kept as forward-compat alias; remove once upstream producer switches
# to 'ml_shadow'.
#
# tier 語意注意（source='dream_engine' row）：evidence_source_tier='real_outcome'
# 描述的是「證據基底」為真——即 avg_net_bps 來自真實 filled cell；但該 row 的
# expected_net_bps 本身是啟發式回收投影（見 payload.expected_net_bps_kind =
# 'heuristic_recovery_projection'），非實測 edge。filter 接受此 tier 是因「基底為真」，
# 而非「expected_net_bps 已驗證」。consumer 勿從 expected_net_bps 推論已實現 /
# forward edge 量級。
EVIDENCE_SOURCE_TIER_ALLOWLIST: tuple[str, ...] = (
    "real_outcome",
    "calibrated_replay",
    "synthetic_replay",
    "counterfactual_replay",
    "mlde_advisor",
)

# P3-03：synthetic_replay 為「合成回放」證據，並非真實成交 / 真實 outcome。
# 為什麼預設排除（fail-closed / 不計為真）：CLAUDE.md「不得偽造證據」精神 +
# Root Principle 6（不確定預設保守）。合成回放可模糊證據品質，不應與真實證據
# silently 等價計入 demo-applier 的升級證據。故拆出可辨識的 synthetic bucket，
# 預設不接受；唯有顯式 opt-in（allow_synthetic=True，由 caller 明確開啟）才納入。
# 注意：此處只收緊 applier runtime allowlist，不改 V036/V040 DB CHECK enum
# （EVIDENCE_SOURCE_TIER_ALLOWLIST 仍對齊 enum 作為儲存值 single source of truth）。
SYNTHETIC_EVIDENCE_SOURCE_TIERS: tuple[str, ...] = ("synthetic_replay",)

# Demo-applier 預設接受的證據 tier（排除 synthetic bucket）。
# Default tiers the demo applier accepts (synthetic excluded by default).
DEFAULT_EVIDENCE_SOURCE_TIER_ALLOWLIST: tuple[str, ...] = tuple(
    tier
    for tier in EVIDENCE_SOURCE_TIER_ALLOWLIST
    if tier not in SYNTHETIC_EVIDENCE_SOURCE_TIERS
)


def resolve_accepted_tiers(*, allow_synthetic: bool = False) -> list[str]:
    """回傳 demo-applier 實際接受的 evidence tier 清單。

    為什麼：synthetic_replay 預設不計為真實升級證據（P3-03）。只有 caller
    顯式 allow_synthetic=True 時才把 synthetic bucket 併回。保守、絕不放寬。
    """
    accepted = list(DEFAULT_EVIDENCE_SOURCE_TIER_ALLOWLIST)
    if allow_synthetic:
        accepted.extend(SYNTHETIC_EVIDENCE_SOURCE_TIERS)
    return accepted


def evidence_filter_capabilities(cur: Any) -> dict[str, bool]:
    """Probe schema for forward-compat REF-20 P4-S11 column / table presence.
    探測 schema 取得 REF-20 P4-S11 forward-compat 欄位 / 表存在性。

    Returns dict with keys:
      - has_evidence_source_tier  (V038+ landed)
      - has_replay_experiment_id  (post-V040 retrofit; column may not exist)
      - has_manifest_hash         (post-V040 retrofit; column may not exist)
      - has_replay_experiments    (V041 stub or P2b fixture)
      - replay_experiments_has_expires_at (P2b fixture only)
      - replay_experiments_has_status     (P2b fixture only)
      - replay_experiments_has_manifest_hash
      - replay_experiments_has_manifest_jsonb
      - replay_experiments_has_oos_label_window_start
      - replay_experiments_has_oos_label_window_end
      - replay_experiments_has_oos_embargo_seconds
      - replay_experiments_has_total_candidates_k
      - has_residual_alpha_reports
      - residual_alpha_reports_has_report_hash
      - residual_alpha_reports_has_report_jsonb
      - residual_alpha_reports_has_strategy_name
      - residual_alpha_reports_has_engine_mode

    Each capability missing → caller falls back gracefully (skip filter
    on that column with comment marking forward-compat per dispatch §
    "對既有 schema 字段 missing → graceful fallback").

    各能力缺 → caller graceful fallback（在該 column 上跳過 filter 並
    註明 forward-compat per dispatch §「graceful fallback」）。

    Probe is fail-soft: SQL exception → all-False (treat as legacy schema).
    探測為 fail-soft：SQL 異常 → 全 False（視為 legacy schema）。
    """
    caps = {
        "has_evidence_source_tier": False,
        "has_replay_experiment_id": False,
        "has_manifest_hash": False,
        "has_replay_experiments": False,
        "replay_experiments_has_expires_at": False,
        "replay_experiments_has_status": False,
        "replay_experiments_has_manifest_hash": False,
        "replay_experiments_has_manifest_jsonb": False,
        "replay_experiments_has_oos_label_window_start": False,
        "replay_experiments_has_oos_label_window_end": False,
        "replay_experiments_has_oos_embargo_seconds": False,
        "replay_experiments_has_total_candidates_k": False,
        "has_residual_alpha_reports": False,
        "residual_alpha_reports_has_report_hash": False,
        "residual_alpha_reports_has_report_jsonb": False,
        "residual_alpha_reports_has_strategy_name": False,
        "residual_alpha_reports_has_engine_mode": False,
    }
    # 1) probe mlde_shadow_recommendations columns
    # 1) 探 mlde_shadow_recommendations 的欄位
    try:
        cur.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = 'learning'
               AND table_name = 'mlde_shadow_recommendations'
               AND column_name = ANY(%s)
            """,
            (["evidence_source_tier", "replay_experiment_id", "manifest_hash"],),
        )
        rows = cur.fetchall() or []
    except Exception as exc:  # noqa: BLE001 - fail-soft probe
        logger.warning("p4_s11 evidence column probe failed: %s", exc)
        return caps
    cols_present = {str(r[0]) for r in rows if r and r[0] is not None}
    caps["has_evidence_source_tier"] = "evidence_source_tier" in cols_present
    caps["has_replay_experiment_id"] = "replay_experiment_id" in cols_present
    caps["has_manifest_hash"] = "manifest_hash" in cols_present

    # 2) probe replay.experiments table + columns (forward-compat for P2b
    # fixture not yet landed in current Wave 6 prod state).
    # 2) 探 replay.experiments 表 + 欄位（P2b fixture 尚未 land 時 forward-compat）。
    try:
        cur.execute("SELECT to_regclass('replay.experiments') IS NOT NULL")
        row = cur.fetchone()
    except Exception:  # noqa: BLE001
        return caps
    if not row or not row[0]:
        return caps
    caps["has_replay_experiments"] = True

    try:
        cur.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = 'replay'
               AND table_name = 'experiments'
               AND column_name = ANY(%s)
            """,
            ([
                "expires_at",
                "status",
                "manifest_hash",
                "manifest_jsonb",
                "oos_label_window_start",
                "oos_label_window_end",
                "oos_embargo_seconds",
                "total_candidates_k",
            ],),
        )
        rep_rows = cur.fetchall() or []
    except Exception:  # noqa: BLE001
        return caps
    rep_cols = {str(r[0]) for r in rep_rows if r and r[0] is not None}
    caps["replay_experiments_has_expires_at"] = "expires_at" in rep_cols
    caps["replay_experiments_has_status"] = "status" in rep_cols
    caps["replay_experiments_has_manifest_hash"] = "manifest_hash" in rep_cols
    caps["replay_experiments_has_manifest_jsonb"] = "manifest_jsonb" in rep_cols
    caps["replay_experiments_has_oos_label_window_start"] = (
        "oos_label_window_start" in rep_cols
    )
    caps["replay_experiments_has_oos_label_window_end"] = (
        "oos_label_window_end" in rep_cols
    )
    caps["replay_experiments_has_oos_embargo_seconds"] = (
        "oos_embargo_seconds" in rep_cols
    )
    caps["replay_experiments_has_total_candidates_k"] = (
        "total_candidates_k" in rep_cols
    )

    # 3) V131 residual alpha report durable registry。此表缺失不破 SELECT，
    # 但 source contract 會在 durable snapshot 欄位為 NULL 時 fail-closed。
    try:
        cur.execute(
            "SELECT to_regclass('learning.demo_residual_alpha_reports') IS NOT NULL"
        )
        residual_row = cur.fetchone()
    except Exception:  # noqa: BLE001
        return caps
    if not residual_row or not residual_row[0]:
        return caps
    caps["has_residual_alpha_reports"] = True

    try:
        cur.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = 'learning'
               AND table_name = 'demo_residual_alpha_reports'
               AND column_name = ANY(%s)
            """,
            (["report_hash", "report_jsonb", "strategy_name", "engine_mode"],),
        )
        residual_rows = cur.fetchall() or []
    except Exception:  # noqa: BLE001
        return caps
    residual_cols = {str(r[0]) for r in residual_rows if r and r[0] is not None}
    caps["residual_alpha_reports_has_report_hash"] = "report_hash" in residual_cols
    caps["residual_alpha_reports_has_report_jsonb"] = "report_jsonb" in residual_cols
    caps["residual_alpha_reports_has_strategy_name"] = "strategy_name" in residual_cols
    caps["residual_alpha_reports_has_engine_mode"] = "engine_mode" in residual_cols
    return caps


def build_evidence_source_filter(
    caps: dict[str, bool],
    *,
    allow_synthetic: bool = False,
) -> tuple[str, list[Any]]:
    """Build surgical WHERE-fragment + extra params for REF-20 P4-S11.
    建構 REF-20 P4-S11 的外科 WHERE-fragment + 額外參數。

    僅在 column / table 物理存在時 emit filter；缺者 graceful fallback
    (skip filter on that column with comment 標 forward-compat) per
    dispatch §"對既有 schema 字段 missing → graceful fallback"。

    Emit filter only when column / table physically exists; otherwise
    graceful fallback (skip filter on that column, marked forward-compat
    per dispatch §"graceful fallback on missing schema field").

    Returns / 回傳 (sql_fragment_with_AND_prefix, extra_params_list)。
    sql_fragment 為空字串 (legacy 完全 fallback) 時 extra_params 也為 []。
    Returns (sql_fragment_with_AND_prefix, extra_params_list); both
    empty in the legacy-schema fallback path.
    """
    if not caps.get("has_evidence_source_tier"):
        # Legacy schema (pre-V038) → no filter possible; preserve previous
        # behavior. Forward-compat: V038-V040 retrofit makes column physical.
        # legacy schema (V038 前) → 無法 filter；保既有行為。V038-V040 後 column 物理化。
        return "", []

    fragments: list[str] = []
    extra_params: list[Any] = []

    # Block A: evidence_source_tier IN (accepted tiers)
    # Block A：evidence_source_tier 必在接受清單內。
    # 預設排除 synthetic_replay（P3-03）；唯有 allow_synthetic=True 才納入。
    fragments.append(
        "AND COALESCE(evidence_source_tier, 'real_outcome') = ANY(%s)"
    )
    extra_params.append(resolve_accepted_tiers(allow_synthetic=allow_synthetic))

    # Block B: replay_experiment_id NULL allowed (legacy non-replay rows
    # = real_outcome) OR points at active manifest in replay.experiments
    # (forward-compat — when both columns land + replay.experiments has
    # expires_at + status).
    # Block B：replay_experiment_id NULL 允許 (legacy 非 replay row =
    # real_outcome)，或指向 replay.experiments 中活躍 manifest
    # (forward-compat — 當 column 與 replay.experiments 都存在 + 有
    # expires_at + status 時)。
    if (
        caps.get("has_replay_experiment_id")
        and caps.get("has_manifest_hash")
        and caps.get("has_replay_experiments")
        and caps.get("replay_experiments_has_expires_at")
        and caps.get("replay_experiments_has_status")
        and caps.get("replay_experiments_has_manifest_hash")
    ):
        fragments.append(
            "AND ("
            "  replay_experiment_id IS NULL "
            "  OR replay_experiment_id IN ("
            "    SELECT experiment_id FROM replay.experiments "
            "    WHERE manifest_hash IS NOT NULL "
            "      AND expires_at > now() "
            "      AND status NOT IN ('cancelled','expired','compromised')"
            "  )"
            ")"
        )
    elif (
        caps.get("has_replay_experiment_id")
        and caps.get("has_replay_experiments")
    ):
        # Partial forward-compat: column 存在但 replay.experiments stub 缺
        # expires_at / status — degrade to FK-only (existence) gate.
        # Partial forward-compat: column exists but stub missing
        # expires_at / status — degrade to FK-only (existence) gate.
        # 部分 forward-compat：column 存在但 stub 缺欄 — 退到 FK 存在性 gate。
        fragments.append(
            "AND ("
            "  replay_experiment_id IS NULL "
            "  OR EXISTS ("
            "    SELECT 1 FROM replay.experiments e "
            "    WHERE e.experiment_id = "
            "      learning.mlde_shadow_recommendations.replay_experiment_id"
            "  )"
            ")"
        )
    # else: replay_experiment_id column not yet landed → skip Block B
    # entirely (legacy schema treats every row as real_outcome via
    # evidence_source_tier filter above).
    # 否則：column 尚未 land → 完全略過 Block B（legacy schema 透過
    # evidence_source_tier filter 視所有 row 為 real_outcome）。

    return "\n           ".join(fragments), extra_params


def fetch_pending_sql_and_params(
    cur: Any,
    *,
    lookback_hours: int,
    engine_mode: str,
    min_confidence: float,
    min_samples: int,
    max_recommendations: int,
    allow_synthetic: bool = False,
) -> tuple[str, tuple[Any, ...]]:
    """Build SELECT sql + params for ``mlde_demo_applier._fetch_pending``.
    建構 ``mlde_demo_applier._fetch_pending`` 用 SELECT sql + params。

    Single source of truth for the P4-S11 evidence-source filter wiring;
    ``_fetch_pending`` only `cur.execute(sql, params)` + `fetchall()`.

    本函數為 P4-S11 evidence-source filter 接線唯一 SoT；
    ``_fetch_pending`` 僅 `cur.execute(sql, params)` + `fetchall()`。

    allow_synthetic 預設 False：synthetic_replay 不計為真實升級證據（P3-03）。
    """
    caps = evidence_filter_capabilities(cur)
    extra_filter, extra_params = build_evidence_source_filter(
        caps, allow_synthetic=allow_synthetic
    )
    # REF-20 Sprint C2 R7-T7 Part B (per MIT §1.5 + AI-E 推薦)：
    # observability log — 每 cycle dump active capabilities + Block A/B mode。
    # block_a = 'on' / 'skip'（has_evidence_source_tier 是否啟用）。
    # block_b = 'full' / 'partial' / 'skip'：
    #   full = 4 個 FK 能力全 true（NOT NULL + manifest_hash + expires_at + status）
    #   partial = FK column 在但 stub 缺 expires_at/status（degraded existence-only gate）
    #   skip = replay_experiment_id column 未 land（完全 fallback）
    has_evidence_source_tier = bool(caps.get("has_evidence_source_tier"))
    has_fk_only = (
        bool(caps.get("has_replay_experiment_id"))
        and bool(caps.get("has_replay_experiments"))
    )
    all_block_b_caps_true = (
        has_fk_only
        and bool(caps.get("has_manifest_hash"))
        and bool(caps.get("replay_experiments_has_expires_at"))
        and bool(caps.get("replay_experiments_has_status"))
        and bool(caps.get("replay_experiments_has_manifest_hash"))
    )
    block_a_label = "on" if has_evidence_source_tier else "skip"
    if not has_evidence_source_tier:
        block_b_label = "skip"
    elif all_block_b_caps_true:
        block_b_label = "full"
    elif has_fk_only:
        block_b_label = "partial"
    else:
        block_b_label = "skip"
    caps_count = sum(1 for v in caps.values() if v)
    # synthetic bucket 模式 observability（P3-03）：預設 'excluded'，
    # 顯式 opt-in 時 'opt_in'。
    synthetic_label = "opt_in" if allow_synthetic else "excluded"
    has_residual_registry_join = (
        bool(caps.get("has_residual_alpha_reports"))
        and bool(caps.get("residual_alpha_reports_has_report_hash"))
        and bool(caps.get("residual_alpha_reports_has_report_jsonb"))
        and bool(caps.get("residual_alpha_reports_has_strategy_name"))
        and bool(caps.get("residual_alpha_reports_has_engine_mode"))
        and bool(caps.get("replay_experiments_has_manifest_jsonb"))
        and has_fk_only
    )
    residual_registry_label = "on" if has_residual_registry_join else "missing"
    logger.info(
        "evidence_filter capability dump: caps=%d/%d block_a=%s block_b=%s synthetic=%s residual_registry=%s",
        caps_count,
        len(caps),
        block_a_label,
        block_b_label,
        synthetic_label,
        residual_registry_label,
    )
    evidence_source_tier_select = (
        "evidence_source_tier::text AS evidence_source_tier"
        if caps.get("has_evidence_source_tier")
        else "NULL::text AS evidence_source_tier"
    )
    replay_experiment_id_select = (
        "replay_experiment_id::text AS replay_experiment_id"
        if caps.get("has_replay_experiment_id")
        else "NULL::text AS replay_experiment_id"
    )
    manifest_hash_select = (
        "encode(manifest_hash, 'hex') AS manifest_hash"
        if caps.get("has_manifest_hash")
        else "NULL::text AS manifest_hash"
    )
    has_registry_join = (
        bool(caps.get("has_replay_experiment_id"))
        and bool(caps.get("has_replay_experiments"))
    )
    registry_join = (
        "LEFT JOIN replay.experiments e "
        "ON e.experiment_id = learning.mlde_shadow_recommendations.replay_experiment_id"
        if has_registry_join
        else ""
    )
    residual_registry_join = (
        "LEFT JOIN learning.demo_residual_alpha_reports drar "
        "ON drar.report_hash = "
        "  (e.manifest_jsonb ->> 'demo_residual_alpha_report_hash') "
        "AND drar.strategy_name = learning.mlde_shadow_recommendations.strategy_name "
        "AND drar.engine_mode = learning.mlde_shadow_recommendations.engine_mode"
        if has_residual_registry_join
        else ""
    )
    registry_status_select = (
        "e.status::text AS replay_registry_status"
        if caps.get("replay_experiments_has_status")
        and has_registry_join
        else "NULL::text AS replay_registry_status"
    )
    registry_expires_at_select = (
        "e.expires_at AS replay_registry_expires_at"
        if caps.get("replay_experiments_has_expires_at")
        and has_registry_join
        else "NULL::timestamptz AS replay_registry_expires_at"
    )
    registry_manifest_hash_select = (
        "encode(e.manifest_hash, 'hex') AS replay_registry_manifest_hash"
        if caps.get("replay_experiments_has_manifest_hash")
        and has_registry_join
        else "NULL::text AS replay_registry_manifest_hash"
    )
    registry_manifest_jsonb_select = (
        "e.manifest_jsonb AS replay_registry_manifest_jsonb"
        if caps.get("replay_experiments_has_manifest_jsonb")
        and has_registry_join
        else "NULL::jsonb AS replay_registry_manifest_jsonb"
    )
    registry_oos_start_select = (
        "e.oos_label_window_start AS replay_registry_oos_label_window_start"
        if caps.get("replay_experiments_has_oos_label_window_start")
        and has_registry_join
        else "NULL::timestamptz AS replay_registry_oos_label_window_start"
    )
    registry_oos_end_select = (
        "e.oos_label_window_end AS replay_registry_oos_label_window_end"
        if caps.get("replay_experiments_has_oos_label_window_end")
        and has_registry_join
        else "NULL::timestamptz AS replay_registry_oos_label_window_end"
    )
    registry_embargo_select = (
        "e.oos_embargo_seconds AS replay_registry_oos_embargo_seconds"
        if caps.get("replay_experiments_has_oos_embargo_seconds")
        and has_registry_join
        else "NULL::bigint AS replay_registry_oos_embargo_seconds"
    )
    registry_k_select = (
        "e.total_candidates_K AS replay_registry_total_candidates_k"
        if caps.get("replay_experiments_has_total_candidates_k")
        and has_registry_join
        else "NULL::integer AS replay_registry_total_candidates_k"
    )
    durable_residual_hash_select = (
        "drar.report_hash AS durable_residual_alpha_report_hash"
        if has_residual_registry_join
        else "NULL::text AS durable_residual_alpha_report_hash"
    )
    durable_residual_jsonb_select = (
        "drar.report_jsonb AS durable_residual_alpha_report_jsonb"
        if has_residual_registry_join
        else "NULL::jsonb AS durable_residual_alpha_report_jsonb"
    )

    sql = """
        SELECT id, ts, engine_mode, source, recommendation_type, strategy_name,
               symbol, expected_net_bps, confidence, sample_count,
               context_id, intent_id,
               {evidence_source_tier_select},
               {replay_experiment_id_select},
               {manifest_hash_select},
               {registry_status_select},
               {registry_expires_at_select},
               {registry_manifest_hash_select},
               {registry_manifest_jsonb_select},
               {registry_oos_start_select},
               {registry_oos_end_select},
               {registry_embargo_select},
               {registry_k_select},
               {durable_residual_hash_select},
               {durable_residual_jsonb_select},
               payload
          FROM learning.mlde_shadow_recommendations
          {registry_join}
          {residual_registry_join}
         WHERE ts >= now() - (%s::int || ' hours')::interval
           AND engine_mode = %s
           AND NOT applied
           AND COALESCE(confidence, 0.0) >= %s
           AND COALESCE(sample_count, 0) >= %s
           {evidence_filter}
         ORDER BY confidence DESC NULLS LAST, sample_count DESC NULLS LAST, ts DESC
         LIMIT %s
    """.format(
        evidence_filter=extra_filter,
        evidence_source_tier_select=evidence_source_tier_select,
        replay_experiment_id_select=replay_experiment_id_select,
        manifest_hash_select=manifest_hash_select,
        registry_join=registry_join,
        residual_registry_join=residual_registry_join,
        registry_status_select=registry_status_select,
        registry_expires_at_select=registry_expires_at_select,
        registry_manifest_hash_select=registry_manifest_hash_select,
        registry_manifest_jsonb_select=registry_manifest_jsonb_select,
        registry_oos_start_select=registry_oos_start_select,
        registry_oos_end_select=registry_oos_end_select,
        registry_embargo_select=registry_embargo_select,
        registry_k_select=registry_k_select,
        durable_residual_hash_select=durable_residual_hash_select,
        durable_residual_jsonb_select=durable_residual_jsonb_select,
    )
    params: list[Any] = [
        lookback_hours,
        engine_mode,
        min_confidence,
        min_samples,
    ]
    params.extend(extra_params)
    params.append(max_recommendations)
    return sql, tuple(params)


__all__ = [
    "EVIDENCE_SOURCE_TIER_ALLOWLIST",
    "SYNTHETIC_EVIDENCE_SOURCE_TIERS",
    "DEFAULT_EVIDENCE_SOURCE_TIER_ALLOWLIST",
    "resolve_accepted_tiers",
    "evidence_filter_capabilities",
    "build_evidence_source_filter",
    "fetch_pending_sql_and_params",
]
