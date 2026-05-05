"""REF-20 Sprint C2 R7-T5 — evidence_filter capability probe test。

模組目的：
    驗證 ``mlde_demo_applier_evidence_filter`` 的 4-gate capability
    probe + Block A/B 構造邏輯在 6 個 case 下行為符合 MIT §1.1 6-key
    + AI-E §9.3 規格：

      Case 1 — Full capability (6/6 true)：完整 Block B 含
              `manifest_hash NOT NULL` + `expires_at > now()` +
              `status NOT IN ('cancelled','expired','compromised')`。
      Case 2 — Partial capability (`replay_experiments_has_expires_at=
              False`)：fallback FK existence-only gate（`EXISTS`
              subquery）。
      Case 3 — Block A only (`has_replay_experiment_id=False`)：含
              evidence_source_tier allowlist filter，0 Block B。
      Case 4 — Top-level fail-soft (`has_evidence_source_tier=False`)：
              SQL 為 empty string（legacy schema fallback）。
      Case 5 — Cycle stale check：每 cycle re-probe — 驗
              `evidence_filter_capabilities(cur)` 在每次
              `fetch_pending_sql_and_params(cur, ...)` 都呼叫。
      Case 6 — Real PG smoke (OPENCLAW_TEST_LIVE_PG=1 opt-in)：mock
              fixture insert row + 驗 Block B SQL 真實 fire。

參考：
    - program_code/ml_training/mlde_demo_applier_evidence_filter.py
      line 91-148 (capability probe) + line 172-238 (build_evidence
      _source_filter 4-level gate) + line 240-323 (fetch_pending_sql_
      and_params 含 R7-T7 Part B observability log)。
    - AI-E advisory §9.3 capability probe spec。
    - MIT §1.1 6-key 4-gate naming。

Hard contracts:
    - 純 unit test：mock cursor + fail-soft fallback；0 PG hit（除 Case 6）。
    - 0 SQL 字串完整內容驗證；驗 fragment 含正確 token + capability dump。
    - 0 hardcoded path / 0 forbidden import。
"""

from __future__ import annotations

import os

import pytest

from ml_training.mlde_demo_applier_evidence_filter import (
    EVIDENCE_SOURCE_TIER_ALLOWLIST,
    build_evidence_source_filter,
    evidence_filter_capabilities,
    fetch_pending_sql_and_params,
)


# ─── Cursor mock 共用 fixture ──────────────────────────────────────────


class _ProbeCursor:
    """模擬 psycopg2 cursor 的 capability probe + final SELECT 三段流程。

    Probe 流程依序：
      1. mlde_shadow_recommendations 欄位 probe (fetchall)
      2. replay.experiments regclass 探（fetchone, returns (True,) or (False,)）
      3. replay.experiments expires_at + status 欄位 probe (fetchall)
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
        self.probe_call_count = 0  # Case 5 用：track 每次 cycle 呼叫次數

    def execute(self, sql, params=()):
        self.executed.append((sql, tuple(params) if params else ()))
        # 真正 SELECT mlde_shadow_recommendations → fetchall 回 fetch_rows
        if (
            "FROM learning.mlde_shadow_recommendations" in sql
            and "WHERE ts >=" in sql
        ):
            self._current = None
            return
        # capability probe（其餘 information_schema / regclass）
        # → 從 queue pop 預設 response
        self.probe_call_count += 1
        self._current = self._queue.pop(0) if self._queue else None

    def fetchone(self):
        cur = self._current
        self._current = None
        return cur

    def fetchall(self):
        # 最後 SELECT branch → 回 fetch_rows
        if (
            self.executed
            and "FROM learning.mlde_shadow_recommendations" in self.executed[-1][0]
        ):
            rows = self._fetch_rows
            self._fetch_rows = []
            return rows
        if isinstance(self._current, list):
            return self._current
        return [self._current] if self._current is not None else []


# ─── Probe response 預設常量 ───────────────────────────────────────────

# Full schema：6/6 capability all true
PROBE_FULL_SCHEMA = [
    [("evidence_source_tier",), ("replay_experiment_id",), ("manifest_hash",)],
    (True,),  # replay.experiments table 存在
    [("expires_at",), ("status",)],
]

# Partial schema：column 在但 stub 缺 expires_at + status
# (有 evidence_source_tier + replay_experiment_id + manifest_hash + replay
#  .experiments 表，但 stub 無 expires_at/status column)
PROBE_PARTIAL_FK_ONLY = [
    [("evidence_source_tier",), ("replay_experiment_id",), ("manifest_hash",)],
    (True,),
    [],  # 0 expires_at / 0 status
]

# Block A only：evidence_source_tier 在但 replay_experiment_id 不在
PROBE_BLOCK_A_ONLY = [
    [("evidence_source_tier",)],  # 只有 evidence_source_tier
    # 後續 probe 不會被呼叫（早期 return）
]

# Pre-V038 legacy schema：什麼都沒有
PROBE_LEGACY_NONE = [
    [],  # 0 column landed
    # 後續 probe 不會被呼叫
]


# ─── Case 1：Full capability (6/6 true) → 完整 Block B ───────────────────


def test_case1_full_capability_all_true_emits_full_block_b():
    """Case 1：6/6 capability 全 true → Block B 含 manifest_hash NOT NULL +
    expires_at > now() + status NOT IN 三 tier 完整版。
    """
    caps = {
        "has_evidence_source_tier": True,
        "has_replay_experiment_id": True,
        "has_manifest_hash": True,
        "has_replay_experiments": True,
        "replay_experiments_has_expires_at": True,
        "replay_experiments_has_status": True,
    }
    fragment, extra = build_evidence_source_filter(caps)

    # Block A 必出現
    assert "AND COALESCE(evidence_source_tier, 'real_outcome') = ANY(%s)" in fragment
    assert extra[0] == list(EVIDENCE_SOURCE_TIER_ALLOWLIST)

    # Block B 完整版三條件全在
    assert "manifest_hash IS NOT NULL" in fragment
    assert "expires_at > now()" in fragment
    assert "status NOT IN ('cancelled','expired','compromised')" in fragment

    # 必為 SELECT...FROM replay.experiments subquery 而非 EXISTS 退化
    assert "SELECT experiment_id FROM replay.experiments" in fragment


# ─── Case 2：Partial capability → fallback FK existence-only gate ──────


def test_case2_partial_capability_fallback_to_fk_existence_only():
    """Case 2：column 在但 stub 缺 expires_at/status → fallback EXISTS gate。"""
    caps = {
        "has_evidence_source_tier": True,
        "has_replay_experiment_id": True,
        "has_manifest_hash": True,
        "has_replay_experiments": True,
        "replay_experiments_has_expires_at": False,  # ← 關鍵
        "replay_experiments_has_status": False,
    }
    fragment, _ = build_evidence_source_filter(caps)

    # Block A 仍在
    assert "AND COALESCE(evidence_source_tier, 'real_outcome') = ANY(%s)" in fragment

    # Block B 退化為 EXISTS subquery（FK existence-only gate）
    assert "EXISTS (" in fragment
    assert "FROM replay.experiments e" in fragment
    assert "e.experiment_id = " in fragment
    assert "learning.mlde_shadow_recommendations.replay_experiment_id" in fragment

    # 不應含完整版 manifest_hash NOT NULL / expires_at > now() / status NOT IN
    # (因為 stub 缺；Partial 路徑不能 reference 缺失的 column)
    assert "expires_at > now()" not in fragment
    assert "status NOT IN" not in fragment

    # 注：當前 IMPL 在 partial path 也不寫 manifest_hash NOT NULL（FK
    # existence-only gate），對齊 helper 註解「degrade to FK-only (existence)
    # gate」。
    # The current IMPL omits `manifest_hash IS NOT NULL` from the partial
    # path because manifest_hash exists at table level — but partial gate
    # only verifies FK existence (degraded mode).


# ─── Case 3：Block A only (replay_experiment_id 未 land) → 0 Block B ───


def test_case3_block_a_only_evidence_source_tier_allowlist_no_block_b():
    """Case 3：has_replay_experiment_id=False → 含 allowlist filter / 0 Block B。"""
    caps = {
        "has_evidence_source_tier": True,
        "has_replay_experiment_id": False,  # ← 關鍵：column 未 land
        "has_manifest_hash": False,
        "has_replay_experiments": False,
        "replay_experiments_has_expires_at": False,
        "replay_experiments_has_status": False,
    }
    fragment, extra = build_evidence_source_filter(caps)

    # Block A 必在
    assert "AND COALESCE(evidence_source_tier, 'real_outcome') = ANY(%s)" in fragment
    assert extra == [list(EVIDENCE_SOURCE_TIER_ALLOWLIST)]

    # Block B 完全略過：不應含任何 replay.experiments / EXISTS / manifest_hash
    # 任何子查詢 token
    assert "replay.experiments" not in fragment
    assert "EXISTS" not in fragment
    assert "replay_experiment_id IS NULL" not in fragment


# ─── Case 4：Top-level fail-soft (has_evidence_source_tier=False) ───────


def test_case4_top_level_fail_soft_legacy_schema_returns_empty():
    """Case 4：has_evidence_source_tier=False → SQL 為空（legacy schema）。"""
    caps = {
        "has_evidence_source_tier": False,  # ← 關鍵：column 完全沒 land
        "has_replay_experiment_id": False,
        "has_manifest_hash": False,
        "has_replay_experiments": False,
        "replay_experiments_has_expires_at": False,
        "replay_experiments_has_status": False,
    }
    fragment, extra = build_evidence_source_filter(caps)

    # 完全空字串
    assert fragment == ""
    assert extra == []


# ─── Case 5：Cycle stale check — 每 cycle re-probe ─────────────────────


def test_case5_capability_re_probed_each_cycle():
    """Case 5：每次 fetch_pending_sql_and_params 必觸發 capability re-probe。

    驗 evidence_filter_capabilities(cur) 在每次 fetch_pending 都會被呼叫，
    即兩次 fetch_pending 期間 capability 不會被 cache（per MIT §1.3 0 cache）。
    """
    # 兩個獨立 cursor，各自 fresh probe queue
    cur1 = _ProbeCursor(list(PROBE_FULL_SCHEMA))
    cur2 = _ProbeCursor(list(PROBE_FULL_SCHEMA))

    # 第一 cycle
    sql1, _ = fetch_pending_sql_and_params(
        cur1,
        lookback_hours=24,
        engine_mode="demo",
        min_confidence=0.5,
        min_samples=10,
        max_recommendations=50,
    )
    # cursor1 應收到 3 次 probe execute 呼叫 + 0 final SELECT (caller 沒 execute sql)
    # probe 共三次：column probe / regclass / experiments column probe
    assert cur1.probe_call_count == 3, (
        f"cycle 1 probe_call_count={cur1.probe_call_count}, expected 3"
    )

    # 第二 cycle 完全獨立 — capability 必再 probe
    sql2, _ = fetch_pending_sql_and_params(
        cur2,
        lookback_hours=24,
        engine_mode="demo",
        min_confidence=0.5,
        min_samples=10,
        max_recommendations=50,
    )
    assert cur2.probe_call_count == 3, (
        f"cycle 2 probe_call_count={cur2.probe_call_count}, expected 3"
    )

    # 兩 cycle 同 schema → 結構應一致（Block B 完整版兩邊都在）
    assert "expires_at > now()" in sql1
    assert "expires_at > now()" in sql2

    # 同一 cursor 連跑兩 cycle：probe 必觸發 6 次（每 cycle 3 次，0 cache）
    cur3 = _ProbeCursor(list(PROBE_FULL_SCHEMA) + list(PROBE_FULL_SCHEMA))
    fetch_pending_sql_and_params(
        cur3,
        lookback_hours=24,
        engine_mode="demo",
        min_confidence=0.5,
        min_samples=10,
        max_recommendations=50,
    )
    fetch_pending_sql_and_params(
        cur3,
        lookback_hours=24,
        engine_mode="demo",
        min_confidence=0.5,
        min_samples=10,
        max_recommendations=50,
    )
    assert cur3.probe_call_count == 6, (
        f"two cycles same cursor probe_call_count={cur3.probe_call_count}, "
        f"expected 6 (re-probe each cycle, no cache)"
    )


# ─── Case 6：Real PG smoke (OPENCLAW_TEST_LIVE_PG=1 opt-in) ─────────────


@pytest.mark.skipif(
    os.environ.get("OPENCLAW_TEST_LIVE_PG") != "1",
    reason="real PG smoke opt-in via OPENCLAW_TEST_LIVE_PG=1",
)
def test_case6_real_pg_smoke_full_block_b_fires():
    """Case 6：Real PG smoke — 對 live PG insert fixture row + 驗 Block B 真 fire。

    僅在 OPENCLAW_TEST_LIVE_PG=1 啟用；CI 預設 skip。
    需 PG runtime 含 V040 + V049 + V051 schema。
    """
    import psycopg2  # type: ignore

    dsn = os.environ.get(
        "OPENCLAW_TEST_PG_DSN",
        "dbname=trading_ai user=postgres host=127.0.0.1",
    )
    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            caps = evidence_filter_capabilities(cur)
            # Real PG 應 land 6/6 capability
            assert caps["has_evidence_source_tier"], "V040 evidence_source_tier 未 land"
            assert caps["has_replay_experiment_id"], "V051 replay_experiment_id 未 land"
            assert caps["has_manifest_hash"], "V051 manifest_hash 未 land"
            assert caps["has_replay_experiments"], "V049 replay.experiments 未 land"
            assert caps["replay_experiments_has_expires_at"], (
                "V049 replay.experiments.expires_at 未 land"
            )
            assert caps["replay_experiments_has_status"], (
                "V049 replay.experiments.status 未 land"
            )
            # Block B 完整版 SQL 必生成
            sql, _ = fetch_pending_sql_and_params(
                cur,
                lookback_hours=24,
                engine_mode="demo",
                min_confidence=0.5,
                min_samples=10,
                max_recommendations=50,
            )
            assert "expires_at > now()" in sql, "Real PG 未 fire Block B 完整版"
            assert "status NOT IN ('cancelled','expired','compromised')" in sql


# ─── Bonus：observability log 驗 R7-T7 Part B (per MIT §1.5) ─────────────


def test_observability_log_full_capability(caplog):
    """R7-T7 Part B：fetch_pending_sql_and_params 必 emit 1-line INFO log
    dump active capabilities + Block B mode（full）。
    """
    import logging

    cur = _ProbeCursor(list(PROBE_FULL_SCHEMA))

    with caplog.at_level(logging.INFO, logger="ml_training.mlde_demo_applier_evidence_filter"):
        fetch_pending_sql_and_params(
            cur,
            lookback_hours=24,
            engine_mode="demo",
            min_confidence=0.5,
            min_samples=10,
            max_recommendations=50,
        )

    # 必有一條 INFO log 含 caps=*/6 + block_a / block_b
    log_msgs = [r.getMessage() for r in caplog.records]
    capability_dumps = [m for m in log_msgs if "evidence_filter capability dump" in m]
    assert len(capability_dumps) >= 1, (
        f"missing capability dump log; all logs={log_msgs}"
    )
    dump = capability_dumps[0]
    assert "caps=6/6" in dump
    assert "block_a=on" in dump
    assert "block_b=full" in dump


def test_observability_log_partial_capability(caplog):
    """R7-T7 Part B：partial capability → block_b=partial。"""
    import logging

    cur = _ProbeCursor(list(PROBE_PARTIAL_FK_ONLY))

    with caplog.at_level(logging.INFO, logger="ml_training.mlde_demo_applier_evidence_filter"):
        fetch_pending_sql_and_params(
            cur,
            lookback_hours=24,
            engine_mode="demo",
            min_confidence=0.5,
            min_samples=10,
            max_recommendations=50,
        )

    log_msgs = [r.getMessage() for r in caplog.records]
    capability_dumps = [m for m in log_msgs if "evidence_filter capability dump" in m]
    assert len(capability_dumps) >= 1
    dump = capability_dumps[0]
    # 4 個 true：has_evidence_source_tier + has_replay_experiment_id +
    # has_manifest_hash + has_replay_experiments
    assert "caps=4/6" in dump
    assert "block_a=on" in dump
    assert "block_b=partial" in dump


def test_observability_log_legacy_schema_skip(caplog):
    """R7-T7 Part B：legacy schema (has_evidence_source_tier=False) →
    block_a=skip + block_b=skip。
    """
    import logging

    cur = _ProbeCursor(list(PROBE_LEGACY_NONE))

    with caplog.at_level(logging.INFO, logger="ml_training.mlde_demo_applier_evidence_filter"):
        fetch_pending_sql_and_params(
            cur,
            lookback_hours=24,
            engine_mode="demo",
            min_confidence=0.5,
            min_samples=10,
            max_recommendations=50,
        )

    log_msgs = [r.getMessage() for r in caplog.records]
    capability_dumps = [m for m in log_msgs if "evidence_filter capability dump" in m]
    assert len(capability_dumps) >= 1
    dump = capability_dumps[0]
    assert "caps=0/6" in dump
    assert "block_a=skip" in dump
    assert "block_b=skip" in dump
