"""REF-20 P4-S11 — mlde_demo_applier source filter tests.

模組目的 / Module purpose:
    驗證 ``mlde_demo_applier._fetch_pending`` (via
    ``mlde_demo_applier_evidence_filter`` helper) 加上的 evidence-source
    filter 在 4 個 forward-compat schema 階段下行為正確：

      Case 1: evidence_source_tier filter ALLOWS the 5 valid tiers
              (whitelist single source of truth = V036 + V040 CHECK enum).
      Case 2: replay manifest expired (expires_at <= now()) → row excluded.
      Case 3: replay manifest status='cancelled' → row excluded.
      Case 4: replay_experiment_id IS NULL (legacy non-replay row) → ALLOW.

    Validate that the evidence-source filter added to
    ``_fetch_pending`` (delegated to ``mlde_demo_applier_evidence_filter``)
    behaves correctly across 4 forward-compat schema phases.

關聯文件 / Related docs:
    - docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
      §4 Wave 6 R20-P4-S11
    - docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md
      §4.2 + §12 #6
    - sql/migrations/V036__replay_evidence_source_guard.sql
    - sql/migrations/V038-V040__add/backfill/finalize_evidence_source_tier.sql

Hard contracts (E2 / E3 / FA review focus):
    - 純 unit test：對 cursor mock，0 PG hit
    - 4 case 覆蓋 P4-S11 dispatch 條目 case 1-4
    - 不驗證 SQL 字串完整內容；驗 sql fragment 含正確 token + params
"""

from __future__ import annotations

import pytest

from ml_training.mlde_demo_applier import DemoApplierConfig, _fetch_pending
from ml_training.mlde_demo_applier_evidence_filter import (
    DEFAULT_EVIDENCE_SOURCE_TIER_ALLOWLIST,
    EVIDENCE_SOURCE_TIER_ALLOWLIST,
    SYNTHETIC_EVIDENCE_SOURCE_TIERS,
    build_evidence_source_filter,
    evidence_filter_capabilities,
    fetch_pending_sql_and_params,
    resolve_accepted_tiers,
)


# ─── Cursor mock ──────────────────────────────────────────────────────────


class _DictRow(dict):
    """Mimic psycopg2 DictRow / 模擬 psycopg2 DictRow。"""


class _ProbeCursor:
    """Programmable cursor for forward-compat schema probe + fetch tests.

    Usage / 用法:
      `_ProbeCursor(probe_responses, fetch_rows)` — `probe_responses` 餵
      capabilities probe 的 4 次 cur.execute (column probe / experiments
      regclass / experiments column probe / final SELECT)；fetch_rows 為
      最後 SELECT cur.fetchall() 回傳。

    For partial schema cases callers may pass less probe responses; the
    cursor returns `None` for fetchone() and `[]` for fetchall() if the
    probe queue is exhausted (mimics post-V040 fail-soft behavior).
    """

    def __init__(
        self,
        probe_responses: list,
        fetch_rows: list | None = None,
    ) -> None:
        self._queue = list(probe_responses)
        self._current = None
        self._fetch_rows = fetch_rows or []
        self.executed: list[tuple[str, tuple]] = []

    def execute(self, sql, params=()):
        # Final SELECT (the actual mlde_shadow_recommendations query) is
        # detected by the FROM clause; everything before that is probe.
        # Final SELECT (真正 mlde_shadow_recommendations 查詢) 由 FROM
        # clause 區分；之前都是 probe。
        self.executed.append((sql, tuple(params) if params else ()))
        if "FROM learning.mlde_shadow_recommendations" in sql and "WHERE ts >=" in sql:
            self._current = None  # last execute drives fetchall()
            return
        self._current = self._queue.pop(0) if self._queue else None

    def fetchone(self):
        cur = self._current
        # Reset to None for next single-row probe.
        # 取完置 None，避免下一輪 probe 拿到舊 row。
        self._current = None
        return cur

    def fetchall(self):
        # If the previous execute hit the SELECT branch, return fetch_rows.
        # 若上一次 execute 是真正 SELECT，回 fetch_rows。
        if self.executed and "FROM learning.mlde_shadow_recommendations" in self.executed[-1][0]:
            rows = self._fetch_rows
            self._fetch_rows = []
            return rows
        if isinstance(self._current, list):
            return self._current
        return [self._current] if self._current is not None else []


# Forward-compat schema phase probe responses.
# Forward-compat schema 階段 probe response。

# Phase 1 — full schema landed (V040 + replay.experiments fixture).
# 階段 1 — 完整 schema land（V040 + replay.experiments fixture）。
PROBE_FULL_SCHEMA = [
    [("evidence_source_tier",), ("replay_experiment_id",), ("manifest_hash",)],
    (True,),
    [
        ("expires_at",),
        ("status",),
        ("manifest_hash",),
        ("manifest_jsonb",),
        ("oos_label_window_start",),
        ("oos_label_window_end",),
        ("oos_embargo_seconds",),
        ("total_candidates_k",),
    ],
    (True,),
    [("report_hash",), ("report_jsonb",), ("strategy_name",), ("engine_mode",)],
]

# Phase 2 — V040 landed but replay metadata columns NOT YET added.
# 階段 2 — V040 land 但 replay metadata column 尚未 add。
PROBE_LEGACY_TIER_ONLY = [
    [("evidence_source_tier",)],  # only tier landed
    (True,),  # replay.experiments stub exists (V041)
    [],  # but no expires_at / status
    (False,),
]


# ─── Case 1: evidence_source_tier allowlist allows the 5 valid tiers ─────


def test_case1_evidence_source_tier_allowlist_allows_5_valid_tiers():
    """Case 1: filter ACCEPTS rows whose evidence_source_tier is in 白名單。
    Case 1：filter 接受 evidence_source_tier 屬白名單之 row。
    """
    # Allowlist must match V036 + V040 CHECK enum + 'mlde_advisor' alias.
    # 白名單必須對齊 V036 + V040 CHECK enum + 'mlde_advisor' alias。
    assert EVIDENCE_SOURCE_TIER_ALLOWLIST == (
        "real_outcome",
        "calibrated_replay",
        "synthetic_replay",
        "counterfactual_replay",
        "mlde_advisor",
    )

    caps = {
        "has_evidence_source_tier": True,
        "has_replay_experiment_id": True,
        "has_manifest_hash": True,
        "has_replay_experiments": True,
        "replay_experiments_has_expires_at": True,
        "replay_experiments_has_status": True,
        "replay_experiments_has_manifest_hash": True,
    }
    fragment, extra = build_evidence_source_filter(caps)

    # Block A：tier filter 必出現
    # Block A: tier filter MUST appear
    assert "AND COALESCE(evidence_source_tier, 'real_outcome') = ANY(%s)" in fragment
    # P3-03：預設不接受 synthetic_replay；Block A param 為 default allowlist。
    # Default accepted tiers exclude synthetic_replay (P3-03).
    assert extra[0] == list(DEFAULT_EVIDENCE_SOURCE_TIER_ALLOWLIST)
    assert "synthetic_replay" not in extra[0]

    # Block B：active manifest gate 必含 expires_at + status NOT IN 三 tier
    # Block B: active manifest gate must reference expires_at + status NOT IN
    assert "expires_at > now()" in fragment
    assert "status NOT IN ('cancelled','expired','compromised')" in fragment


# ─── Case 2: expired manifest filter excludes expired rows ───────────────


def test_case2_expired_manifest_filter_excludes_expired_row():
    """Case 2: when manifest expires_at <= now(), filter EXCLUDES the row.
    Case 2：manifest expires_at 已過時，filter 排除該 row。
    """
    caps = {
        "has_evidence_source_tier": True,
        "has_replay_experiment_id": True,
        "has_manifest_hash": True,
        "has_replay_experiments": True,
        "replay_experiments_has_expires_at": True,
        "replay_experiments_has_status": True,
        "replay_experiments_has_manifest_hash": True,
    }
    fragment, _ = build_evidence_source_filter(caps)

    # 子查詢必含 ``expires_at > now()`` — PG semantics: expired (<=) excluded.
    # subquery must contain ``expires_at > now()`` — expired rows excluded
    # by PG semantics.
    assert "expires_at > now()" in fragment
    # 子查詢必含 manifest_hash IS NOT NULL（unverified manifest 也排除）
    # subquery must require manifest_hash IS NOT NULL (unverified excluded).
    assert "manifest_hash IS NOT NULL" in fragment


# ─── Case 3: cancelled status filter excludes cancelled rows ─────────────


def test_case3_cancelled_status_filter_excludes_cancelled_row():
    """Case 3: status IN ('cancelled','expired','compromised') excluded.
    Case 3：status IN 三 tier 之 row 被排除。
    """
    caps = {
        "has_evidence_source_tier": True,
        "has_replay_experiment_id": True,
        "has_manifest_hash": True,
        "has_replay_experiments": True,
        "replay_experiments_has_expires_at": True,
        "replay_experiments_has_status": True,
        "replay_experiments_has_manifest_hash": True,
    }
    fragment, _ = build_evidence_source_filter(caps)
    # status NOT IN ('cancelled','expired','compromised') 必出現
    # status NOT IN clause must appear
    assert "status NOT IN ('cancelled','expired','compromised')" in fragment


# ─── Case 4: NULL replay_experiment_id (legacy non-replay rows) → ALLOW ──


def test_case4_null_replay_experiment_id_legacy_row_allowed():
    """Case 4: replay_experiment_id IS NULL (legacy real_outcome) → ALLOW.
    Case 4：legacy real_outcome row（replay_experiment_id IS NULL）被允許。
    """
    caps = {
        "has_evidence_source_tier": True,
        "has_replay_experiment_id": True,
        "has_manifest_hash": True,
        "has_replay_experiments": True,
        "replay_experiments_has_expires_at": True,
        "replay_experiments_has_status": True,
        "replay_experiments_has_manifest_hash": True,
    }
    fragment, _ = build_evidence_source_filter(caps)

    # OR-clause 必包 ``replay_experiment_id IS NULL`` — legacy row 通過
    # OR-clause must include ``replay_experiment_id IS NULL`` so legacy
    # real_outcome rows pass the filter.
    assert "replay_experiment_id IS NULL" in fragment
    # 與 OR 之後子查詢配合（IN 子查詢搜 active manifest）
    # paired with OR + subquery against active manifests
    assert " OR " in fragment


# ─── Forward-compat: legacy schema graceful fallback ─────────────────────


def test_forward_compat_legacy_schema_skips_filter():
    """Forward-compat: pre-V038 schema (no evidence_source_tier column) →
    filter 完全 fallback (empty fragment / empty extra params)。
    Pre-V038 schema → filter degrades gracefully to empty fragment.
    """
    caps = {
        "has_evidence_source_tier": False,
        "has_replay_experiment_id": False,
        "has_manifest_hash": False,
        "has_replay_experiments": False,
        "replay_experiments_has_expires_at": False,
        "replay_experiments_has_status": False,
    }
    fragment, extra = build_evidence_source_filter(caps)
    assert fragment == ""
    assert extra == []


def test_forward_compat_partial_schema_only_tier_filter():
    """Forward-compat：V040 land 但 replay_experiment_id column 尚未 add，
    Block B 完全跳過；Block A tier filter 保留。
    Partial schema (V040 only, replay metadata pending) → only Block A
    tier filter is emitted.
    """
    caps = {
        "has_evidence_source_tier": True,
        "has_replay_experiment_id": False,  # column not yet landed
        "has_manifest_hash": False,
        "has_replay_experiments": True,
        "replay_experiments_has_expires_at": True,
        "replay_experiments_has_status": True,
    }
    fragment, extra = build_evidence_source_filter(caps)
    assert "AND COALESCE(evidence_source_tier, 'real_outcome') = ANY(%s)" in fragment
    # Block B 不應出現
    # Block B must not appear
    assert "replay_experiment_id IS NULL" not in fragment
    # P3-03：預設 allowlist 排除 synthetic_replay。
    assert extra == [list(DEFAULT_EVIDENCE_SOURCE_TIER_ALLOWLIST)]


# ─── End-to-end: _fetch_pending applies SQL via helper ───────────────────


def test_fetch_pending_full_schema_executes_filtered_sql():
    """End-to-end: _fetch_pending 在 full schema 下發出含 P4-S11 filter SQL。
    With full schema, _fetch_pending issues SQL containing P4-S11 filter.
    """
    cur = _ProbeCursor(
        probe_responses=PROBE_FULL_SCHEMA,
        fetch_rows=[
            _DictRow({
                "id": 1, "ts": None, "engine_mode": "demo", "source": "ml_shadow",
                "recommendation_type": "parameter_proposal",
                "strategy_name": "grid_trading", "symbol": "BTCUSDT",
                "expected_net_bps": 12.0, "confidence": 0.8, "sample_count": 50,
                "payload": {},
            }),
        ],
    )
    cfg = DemoApplierConfig()
    rows = _fetch_pending(cur, cfg)
    assert len(rows) == 1
    # Final SELECT 必含 evidence_source_tier filter
    # Final SELECT must include evidence_source_tier filter
    final_sql, final_params = cur.executed[-1]
    assert "FROM learning.mlde_shadow_recommendations" in final_sql
    assert "evidence_source_tier" in final_sql
    assert "evidence_source_tier::text AS evidence_source_tier" in final_sql
    assert "replay_experiment_id::text AS replay_experiment_id" in final_sql
    assert "encode(manifest_hash, 'hex') AS manifest_hash" in final_sql
    assert "LEFT JOIN replay.experiments e" in final_sql
    assert "expires_at > now()" in final_sql
    assert "e.status::text AS replay_registry_status" in final_sql
    assert "encode(e.manifest_hash, 'hex') AS replay_registry_manifest_hash" in final_sql
    assert "e.manifest_jsonb AS replay_registry_manifest_jsonb" in final_sql
    assert "e.oos_label_window_start AS replay_registry_oos_label_window_start" in final_sql
    assert "e.total_candidates_K AS replay_registry_total_candidates_k" in final_sql
    assert "LEFT JOIN learning.demo_residual_alpha_reports drar" in final_sql
    assert "drar.report_hash AS durable_residual_alpha_report_hash" in final_sql
    assert "drar.report_jsonb AS durable_residual_alpha_report_jsonb" in final_sql
    # tier allowlist 必為 SQL params 之一（預設排除 synthetic_replay，P3-03）
    # default accepted tiers (synthetic excluded) must be one of the SQL params
    assert list(DEFAULT_EVIDENCE_SOURCE_TIER_ALLOWLIST) in [list(p) if isinstance(p, list) else p for p in final_params]


def test_fetch_pending_legacy_schema_falls_back_to_unfiltered_sql():
    """End-to-end: pre-V038 schema 下 _fetch_pending 不附加 P4-S11 filter
    （helper graceful fallback），caller 行為與舊版一致。
    Pre-V038 schema → _fetch_pending issues SQL without P4-S11 filter
    (helper graceful fallback); caller behavior unchanged from legacy.
    """
    # Probe queue: column probe → empty list (no tier column).
    # Probe queue：column probe → 空 list（無 tier column）。
    cur = _ProbeCursor(
        probe_responses=[
            [],  # mlde_shadow_recommendations columns (none of the 3 land)
        ],
        fetch_rows=[],
    )
    cfg = DemoApplierConfig()
    rows = _fetch_pending(cur, cfg)
    assert rows == []
    final_sql, final_params = cur.executed[-1]
    assert "FROM learning.mlde_shadow_recommendations" in final_sql
    assert "NULL::text AS evidence_source_tier" in final_sql
    assert "NULL::text AS replay_experiment_id" in final_sql
    assert "NULL::text AS manifest_hash" in final_sql
    assert "NULL::text AS replay_registry_status" in final_sql
    assert "NULL::jsonb AS replay_registry_manifest_jsonb" in final_sql
    assert "COALESCE(evidence_source_tier" not in final_sql


def test_fetch_pending_without_row_fk_does_not_reference_registry_alias():
    """row FK 欄位不存在時，不能 SELECT e.* registry alias。"""
    cur = _ProbeCursor(
        probe_responses=[
            [("evidence_source_tier",)],  # no replay_experiment_id column
            (True,),
            [
                ("expires_at",),
                ("status",),
                ("manifest_hash",),
                ("manifest_jsonb",),
            ],
        ],
        fetch_rows=[],
    )
    _fetch_pending(cur, DemoApplierConfig())

    final_sql, _ = cur.executed[-1]
    assert "LEFT JOIN replay.experiments e" not in final_sql
    assert " e." not in final_sql
    assert "NULL::text AS replay_registry_status" in final_sql
    assert "NULL::jsonb AS replay_registry_manifest_jsonb" in final_sql


def test_fetch_pending_helper_accepts_required_kwargs():
    """``fetch_pending_sql_and_params`` accepts the 5 required kwargs
    and returns (sql, tuple-of-params); enforces caller surface stable.
    驗 helper 介面穩定（5 個 kwarg + 回傳 tuple shape）。
    """
    cur = _ProbeCursor(
        probe_responses=[
            [],  # legacy schema → empty filter
        ],
    )
    sql, params = fetch_pending_sql_and_params(
        cur,
        lookback_hours=72,
        engine_mode="demo",
        min_confidence=0.4,
        min_samples=5,
        max_recommendations=12,
    )
    assert isinstance(sql, str)
    assert isinstance(params, tuple)
    # 4 base params (lookback / engine / conf / samples) + 1 limit (legacy fallback adds nothing extra)
    # 4 base + 1 limit = 5 params 在 legacy fallback 路徑
    assert len(params) == 5
    assert params[0] == 72
    assert params[1] == "demo"
    assert params[-1] == 12


# ─── evidence_filter_capabilities probe shape ────────────────────────────


def test_evidence_filter_capabilities_returns_all_keys():
    """``evidence_filter_capabilities`` 回 dict 必含 schema-presence key。
    The cap dict must always include stable schema-presence keys for caller
    branching.
    """
    cur = _ProbeCursor(probe_responses=[
        [],  # column probe empty
    ])
    caps = evidence_filter_capabilities(cur)
    expected_keys = {
        "has_evidence_source_tier",
        "has_replay_experiment_id",
        "has_manifest_hash",
        "has_replay_experiments",
        "replay_experiments_has_expires_at",
        "replay_experiments_has_status",
        "replay_experiments_has_manifest_hash",
        "replay_experiments_has_manifest_jsonb",
        "replay_experiments_has_oos_label_window_start",
        "replay_experiments_has_oos_label_window_end",
        "replay_experiments_has_oos_embargo_seconds",
        "replay_experiments_has_total_candidates_k",
        "has_residual_alpha_reports",
        "residual_alpha_reports_has_report_hash",
        "residual_alpha_reports_has_report_jsonb",
        "residual_alpha_reports_has_strategy_name",
        "residual_alpha_reports_has_engine_mode",
    }
    assert set(caps.keys()) == expected_keys
    # legacy schema → all False
    # legacy schema → 全 False
    assert all(v is False for v in caps.values())


def test_evidence_filter_capabilities_full_schema():
    """Full schema → all caps True / 完整 schema → caps 全 True。"""
    cur = _ProbeCursor(probe_responses=PROBE_FULL_SCHEMA)
    caps = evidence_filter_capabilities(cur)
    assert caps["has_evidence_source_tier"] is True
    assert caps["has_replay_experiment_id"] is True
    assert caps["has_manifest_hash"] is True
    assert caps["has_replay_experiments"] is True
    assert caps["replay_experiments_has_expires_at"] is True
    assert caps["replay_experiments_has_status"] is True
    assert caps["replay_experiments_has_manifest_hash"] is True
    assert caps["replay_experiments_has_manifest_jsonb"] is True
    assert caps["replay_experiments_has_oos_label_window_start"] is True
    assert caps["replay_experiments_has_oos_label_window_end"] is True
    assert caps["replay_experiments_has_oos_embargo_seconds"] is True
    assert caps["replay_experiments_has_total_candidates_k"] is True
    assert caps["has_residual_alpha_reports"] is True
    assert caps["residual_alpha_reports_has_report_hash"] is True
    assert caps["residual_alpha_reports_has_report_jsonb"] is True
    assert caps["residual_alpha_reports_has_strategy_name"] is True
    assert caps["residual_alpha_reports_has_engine_mode"] is True


# ─── P3-03: synthetic_replay opt-in bucket ───────────────────────────────


def test_synthetic_excluded_from_default_allowlist():
    """P3-03：synthetic_replay 不在 demo-applier 預設接受清單內。
    synthetic_replay must not be in the default accepted-tier set.
    """
    # 完整 enum 仍含 synthetic（對齊 V036/V040 CHECK，作為儲存值 SoT）。
    assert "synthetic_replay" in EVIDENCE_SOURCE_TIER_ALLOWLIST
    # 但 demo-applier 預設不接受 synthetic（不計為真實升級證據）。
    assert "synthetic_replay" not in DEFAULT_EVIDENCE_SOURCE_TIER_ALLOWLIST
    assert SYNTHETIC_EVIDENCE_SOURCE_TIERS == ("synthetic_replay",)


def test_resolve_accepted_tiers_default_excludes_synthetic():
    """預設 resolve_accepted_tiers 不含 synthetic_replay。
    Default resolve_accepted_tiers excludes synthetic_replay.
    """
    accepted = resolve_accepted_tiers()
    assert "synthetic_replay" not in accepted
    assert "real_outcome" in accepted
    assert accepted == list(DEFAULT_EVIDENCE_SOURCE_TIER_ALLOWLIST)


def test_resolve_accepted_tiers_opt_in_includes_synthetic():
    """顯式 allow_synthetic=True 才把 synthetic_replay 併回。
    Only explicit allow_synthetic=True re-includes synthetic_replay.
    """
    accepted = resolve_accepted_tiers(allow_synthetic=True)
    assert "synthetic_replay" in accepted
    # 仍含全部其他 default tier。
    for tier in DEFAULT_EVIDENCE_SOURCE_TIER_ALLOWLIST:
        assert tier in accepted


def test_build_filter_default_excludes_synthetic_param():
    """build_evidence_source_filter 預設 Block A param 不含 synthetic_replay。
    Default Block A param excludes synthetic_replay.
    """
    caps = {
        "has_evidence_source_tier": True,
        "has_replay_experiment_id": False,
        "has_manifest_hash": False,
        "has_replay_experiments": False,
        "replay_experiments_has_expires_at": False,
        "replay_experiments_has_status": False,
    }
    _, extra = build_evidence_source_filter(caps)
    assert "synthetic_replay" not in extra[0]


def test_build_filter_opt_in_includes_synthetic_param():
    """allow_synthetic=True → Block A param 含 synthetic_replay。
    allow_synthetic=True → Block A param includes synthetic_replay.
    """
    caps = {
        "has_evidence_source_tier": True,
        "has_replay_experiment_id": False,
        "has_manifest_hash": False,
        "has_replay_experiments": False,
        "replay_experiments_has_expires_at": False,
        "replay_experiments_has_status": False,
    }
    _, extra = build_evidence_source_filter(caps, allow_synthetic=True)
    assert "synthetic_replay" in extra[0]


def test_fetch_pending_helper_defaults_to_excluding_synthetic():
    """fetch_pending_sql_and_params 預設不接受 synthetic（caller 不傳 flag）。
    The helper defaults to excluding synthetic when caller omits the flag.
    """
    cur = _ProbeCursor(
        probe_responses=[
            [("evidence_source_tier",)],  # tier column landed, no replay meta
        ],
    )
    _, params = fetch_pending_sql_and_params(
        cur,
        lookback_hours=72,
        engine_mode="demo",
        min_confidence=0.4,
        min_samples=5,
        max_recommendations=12,
    )
    # tier allowlist param 不含 synthetic_replay。
    tier_params = [p for p in params if isinstance(p, list)]
    assert tier_params, "expected a tier allowlist list param"
    assert "synthetic_replay" not in tier_params[0]
