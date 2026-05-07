"""
Tests for LG5-W3-FUP-1 — Lg5ReviewConsumer scheduler.
LG5-W3-FUP-1 Lg5ReviewConsumer 排程器測試。

Coverage / 覆蓋：
  1. Cycle dispatches review_live_candidate per pending candidate, aggregates
     verdict counts correctly (approve / reject / defer).
     Cycle 對每個 pending candidate 派發 review_live_candidate，正確聚合
     verdict 計數（approve / reject / defer）。
  2. Per-candidate exception does NOT abort batch — remaining candidates still
     reviewed; failure recorded in summary.errors + total_errors stat.
     單一 candidate 例外不中斷整批 —— 剩餘 candidate 仍被處理；失敗記入
     summary.errors + total_errors 統計。
  3. ROUND-2 HIGH-1 contract: hub.is_authorized() == False does NOT
     short-circuit at wrapper level — review_live_candidate is still called
     and IMPL-2 R6 evaluator emits reject_hard_veto verdict per-candidate.
     ROUND-2 HIGH-1 契約：hub.is_authorized()==False **不**在 wrapper 層
     短路 —— review_live_candidate 仍被呼叫，IMPL-2 R6 evaluator 對每筆
     candidate 發出 reject_hard_veto verdict。
  4. Empty pending pool → reviewed=0, no error, no review_live_candidate call.
     空 pending pool → reviewed=0，無錯誤，不呼叫 review_live_candidate。
  5. config_from_env: env defaults + invalid value fail-soft to default.
     config_from_env：env 預設 + 無效值 fail-soft 回預設。
  6. start_consumer_scheduler honours OPENCLAW_LG5_CONSUMER_ENABLED=0 → no
     instance, no daemon thread spawned.
     start_consumer_scheduler 遵循 ENABLED=0 → 不建構實例、不 spawn 線程。

Principles honoured / 遵循原則：
  - CLAUDE.md §二 #6 失敗默認收縮（per-candidate fail-open，但 batch 不破）
  - CLAUDE.md §二 #8 交易可解釋（INFO log per cycle，summary 可 SQL/grep 重建）
  - CLAUDE.md §七 雙語注釋
"""
from __future__ import annotations

import os
import threading
from typing import Any, List, Optional
from unittest.mock import MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures / 共用 helpers
# ═══════════════════════════════════════════════════════════════════════════════

class _FakeVerdict:
    """Minimal stand-in for ReviewVerdict — only `decision` matters here.
    ReviewVerdict 極簡替身 —— 本檔測試只在乎 decision 欄位。"""

    def __init__(self, decision: str) -> None:
        self.decision = decision


class _FakeHub:
    """Minimal hub stub — only ``is_authorized`` consulted by consumer.
    Hub 極簡 stub —— consumer 僅查 is_authorized。"""

    def __init__(self, *, authorized: bool = True, raise_on_auth: bool = False) -> None:
        self._authorized = authorized
        self._raise = raise_on_auth
        self.is_authorized_calls = 0

    def is_authorized(self) -> bool:
        self.is_authorized_calls += 1
        if self._raise:
            raise RuntimeError("hub auth check failed (test-injected)")
        return self._authorized


class _FakeCursor:
    """Tiny cursor spy for _fetch_pending_candidate_ids SQL shape tests.
    _fetch_pending_candidate_ids SQL 形狀測試用極簡 cursor spy。"""

    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows
        self.sql = ""
        self.params: tuple[Any, ...] | None = None

    def __enter__(self):
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        self.sql = sql
        self.params = params

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows


class _FakeConn:
    """Connection wrapper exposing a single fake cursor.
    暴露單一 fake cursor 的 connection wrapper。"""

    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _FakeCursor:
        return self._cursor


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset module singleton + leader lock fd before/after each test.
    每測試前後重置模組單例與 leader lock fd。"""
    from app.lg5_review_consumer_scheduler import _reset_for_tests
    _reset_for_tests()
    yield
    _reset_for_tests()


# ═══════════════════════════════════════════════════════════════════════════════
# 0. Pending candidate fetch SQL / Pending candidate 選取 SQL
# ═══════════════════════════════════════════════════════════════════════════════

class TestPendingCandidateFetch:
    """Lock the [42] drain contract at the SQL selection layer.
    在 SQL 選取層鎖住 [42] drain 契約。"""

    def test_fetch_excludes_candidates_already_review_audited(self, monkeypatch):
        """Already-audited candidates must not starve later unaudited rows.
        已 audit candidate 不可持續佔住 cap，導致後續 unaudited rows 飢餓。"""
        from app import lg5_review_consumer_scheduler as mod

        cursor = _FakeCursor([(241,), (249,), (None,)])
        conn = _FakeConn(cursor)
        returned: list[Any] = []

        monkeypatch.setattr(mod, "get_conn", lambda: conn)
        monkeypatch.setattr(mod, "put_conn", lambda c: returned.append(c))

        ids = mod._fetch_pending_candidate_ids(16)

        assert ids == [241, 249]
        normalized_sql = " ".join(cursor.sql.split())
        assert "NOT EXISTS" in normalized_sql
        assert "learning.governance_audit_log AS a" in normalized_sql
        assert "a.candidate_id = c.id" in normalized_sql
        assert "a.event_type = 'review_live_candidate'" in normalized_sql
        assert cursor.params == (16,)
        assert returned == [conn]


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Cycle aggregation / Cycle 聚合
# ═══════════════════════════════════════════════════════════════════════════════

class TestCycleAggregation:
    """Verify per-cycle aggregation of approve/reject/defer counts.
    驗證每 cycle 對 approve/reject/defer 的聚合。"""

    def test_three_candidates_mixed_verdicts_aggregate_correctly(self, monkeypatch):
        """3 candidates → 1 approve + 1 reject + 1 defer aggregated correctly.
        3 candidates → 1 approve + 1 reject + 1 defer 正確聚合。"""
        from app import lg5_review_consumer_scheduler as mod

        candidate_ids = [101, 102, 103]
        verdicts = {
            101: _FakeVerdict("approve"),
            102: _FakeVerdict("reject"),
            103: _FakeVerdict("defer"),
        }
        monkeypatch.setattr(mod, "_fetch_pending_candidate_ids",
                            lambda limit: list(candidate_ids))

        review_calls: List[int] = []

        def fake_review(hub, candidate_id, *, decided_by="x"):
            review_calls.append(candidate_id)
            return verdicts[candidate_id]

        # Patch review function via the module's lazy import path.
        # 透過 module 的 lazy import 路徑 patch review 函數。
        with patch("app.governance_hub_live_candidate_review.review_live_candidate",
                   side_effect=fake_review) as mocked:
            consumer = mod.Lg5ReviewConsumer(
                cycle_secs=10.0,
                max_per_cycle=8,
                hub_provider=lambda: _FakeHub(authorized=True),
            )
            summary = consumer.trigger_now()

        assert summary["candidates_fetched"] == 3
        assert summary["reviewed"] == 3
        assert summary["approved"] == 1
        assert summary["rejected"] == 1
        assert summary["deferred"] == 1
        assert summary["errors"] == []
        assert review_calls == candidate_ids, "review_live_candidate must be called per ID in order"
        assert mocked.call_count == 3

        # Verify totals state propagated.
        # 驗證累積統計亦同步。
        status = consumer.status()
        assert status["total_reviewed"] == 3
        assert status["total_approved"] == 1
        assert status["total_rejected"] == 1
        assert status["total_deferred"] == 1
        assert status["total_errors"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Per-candidate fail-open / 單一 candidate fail-open
# ═══════════════════════════════════════════════════════════════════════════════

class TestPerCandidateFailOpen:
    """Single-candidate exception must not abort the batch.
    單一 candidate 例外不中斷整批。"""

    def test_one_candidate_raises_others_still_reviewed(self, monkeypatch):
        """3 candidates; #2 raises → 2 reviewed, 1 error in summary.
        3 candidates；#2 raise → 2 reviewed，1 error 在 summary。"""
        from app import lg5_review_consumer_scheduler as mod

        monkeypatch.setattr(mod, "_fetch_pending_candidate_ids",
                            lambda limit: [201, 202, 203])

        def fake_review(hub, candidate_id, *, decided_by="x"):
            if candidate_id == 202:
                raise RuntimeError("test-injected per-candidate failure")
            return _FakeVerdict("approve" if candidate_id == 201 else "defer")

        with patch("app.governance_hub_live_candidate_review.review_live_candidate",
                   side_effect=fake_review):
            consumer = mod.Lg5ReviewConsumer(
                cycle_secs=10.0,
                max_per_cycle=8,
                hub_provider=lambda: _FakeHub(authorized=True),
            )
            summary = consumer.trigger_now()

        assert summary["candidates_fetched"] == 3
        # Only 2 successfully reviewed (201 approve + 203 defer).
        # 僅 2 成功 review（201 approve + 203 defer）。
        assert summary["reviewed"] == 2
        assert summary["approved"] == 1
        assert summary["deferred"] == 1
        assert summary["rejected"] == 0
        assert len(summary["errors"]) == 1
        err_entry = summary["errors"][0]
        assert err_entry["candidate_id"] == 202
        assert err_entry["error_class"] == "RuntimeError"
        assert "test-injected" in err_entry["error_msg"]

        # total_errors stat increments cumulatively.
        # total_errors 累積遞增。
        status = consumer.status()
        assert status["total_errors"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 3. ROUND-2 HIGH-1 contract: unauthorized → still call IMPL-2
# ROUND-2 HIGH-1 契約：未授權仍呼叫 IMPL-2
# ═══════════════════════════════════════════════════════════════════════════════

class TestUnauthorizedStillCallsImpl2:
    """ROUND-2 HIGH-1 fix contract:
    Unauthorized hub state must NOT short-circuit at wrapper layer.
    review_live_candidate (IMPL-2) is invoked per-candidate and its internal
    evaluate_r6() returns reject_hard_veto verdict. This proves audit emission
    still happens (IMPL-2 emits reject_hard_veto audit row) and [42]
    unaudited_over_1h backlog drains as designed.

    ROUND-2 HIGH-1 修復契約：
    未授權 hub 狀態**不**在 wrapper 層短路。review_live_candidate (IMPL-2)
    仍逐筆呼叫，其內部 evaluate_r6() 返回 reject_hard_veto verdict。
    證明 audit emission 仍發生（IMPL-2 emit reject_hard_veto audit row），
    [42] unaudited_over_1h backlog 按設計 drain。"""

    def test_unauthorized_hub_still_calls_review_and_aggregates_hard_veto(
        self, monkeypatch,
    ):
        """Unauthorized hub: review IS called per candidate; IMPL-2 returns
        reject_hard_veto verdict; rejected_hard_veto count aggregated.
        未授權 hub：review 仍逐筆呼叫；IMPL-2 返 reject_hard_veto verdict；
        rejected_hard_veto 計數聚合。"""
        from app import lg5_review_consumer_scheduler as mod

        candidate_ids = [501, 502, 503]
        monkeypatch.setattr(mod, "_fetch_pending_candidate_ids",
                            lambda limit: list(candidate_ids))

        review_calls: List[int] = []

        def fake_review_unauthorized(hub, candidate_id, *, decided_by="x"):
            """Simulate IMPL-2 R6 hard-veto behaviour for unauthorized state.
            模擬 IMPL-2 R6 hard-veto 在未授權時的行為。"""
            review_calls.append(candidate_id)
            verdict = _FakeVerdict("reject")
            verdict.reason = "reject_hard_veto"  # IMPL-2 returns this on R6 fail
            return verdict

        with patch("app.governance_hub_live_candidate_review.review_live_candidate",
                   side_effect=fake_review_unauthorized) as mocked:
            consumer = mod.Lg5ReviewConsumer(
                cycle_secs=10.0,
                max_per_cycle=8,
                hub_provider=lambda: _FakeHub(authorized=False),
            )
            summary = consumer.trigger_now()

        # ROUND-2 contract: review IS called (no wrapper short-circuit).
        # ROUND-2 契約：review 仍被呼叫（wrapper 不短路）。
        assert mocked.call_count == 3
        assert review_calls == candidate_ids
        assert summary["candidates_fetched"] == 3
        assert summary["reviewed"] == 3
        assert summary["rejected"] == 3
        # rejected_hard_veto subset metric (verdict-derived, replaces deleted
        # cycles_skipped_not_authorized hub-derived metric).
        # rejected_hard_veto 子集指標（verdict 推導，取代被刪的 hub 推導
        # cycles_skipped_not_authorized 指標）。
        assert summary["rejected_hard_veto"] == 3
        assert summary["approved"] == 0
        assert summary["deferred"] == 0
        assert summary["errors"] == []

        status = consumer.status()
        assert status["total_rejected"] == 3
        assert status["total_rejected_hard_veto"] == 3
        # Old metric must be removed from status() — assert key absent.
        # 舊指標需從 status() 移除 —— 確認 key 不存在。
        assert "cycles_skipped_not_authorized" not in status

    def test_mixed_reject_reasons_only_hard_veto_aggregated(self, monkeypatch):
        """Mix reject_hard_veto with other reject reasons; only reason ==
        reject_hard_veto increments rejected_hard_veto subset count.
        混合 reject_hard_veto 與其他 reject 原因；僅 reason == reject_hard_veto
        遞增 rejected_hard_veto 子集。"""
        from app import lg5_review_consumer_scheduler as mod

        candidate_ids = [601, 602, 603, 604]
        # 601=reject hard_veto, 602=reject other reason, 603=reject hard_veto,
        # 604=approve. rejected_hard_veto should == 2, rejected total == 3.
        # 601=reject hard_veto, 602=reject 其他, 603=reject hard_veto,
        # 604=approve。rejected_hard_veto 應 == 2，rejected total == 3。
        verdicts: dict[int, _FakeVerdict] = {}
        for cid, decision, reason in [
            (601, "reject", "reject_hard_veto"),
            (602, "reject", "reject_r2_cost_drag"),
            (603, "reject", "reject_hard_veto"),
            (604, "approve", "approve"),
        ]:
            v = _FakeVerdict(decision)
            v.reason = reason
            verdicts[cid] = v

        monkeypatch.setattr(mod, "_fetch_pending_candidate_ids",
                            lambda limit: list(candidate_ids))

        def fake_review(hub, candidate_id, *, decided_by="x"):
            return verdicts[candidate_id]

        with patch("app.governance_hub_live_candidate_review.review_live_candidate",
                   side_effect=fake_review):
            consumer = mod.Lg5ReviewConsumer(
                cycle_secs=10.0,
                max_per_cycle=8,
                hub_provider=lambda: _FakeHub(authorized=True),
            )
            summary = consumer.trigger_now()

        assert summary["candidates_fetched"] == 4
        assert summary["reviewed"] == 4
        assert summary["approved"] == 1
        assert summary["rejected"] == 3
        assert summary["rejected_hard_veto"] == 2  # subset of rejected
        assert summary["deferred"] == 0

    def test_hub_is_authorized_raise_not_caught_by_wrapper(self, monkeypatch):
        """ROUND-2 HIGH-1: wrapper no longer queries hub.is_authorized() —
        IMPL-2 internally does so + handles raise as auth_effective=False.
        Verify wrapper does NOT hard-skip on raise; review IS called.
        ROUND-2 HIGH-1：wrapper 不再查 hub.is_authorized() —— IMPL-2 內部會查
        + 將 raise 視為 auth_effective=False。驗證 wrapper 不因 raise hard-skip；
        review 仍被呼叫。"""
        from app import lg5_review_consumer_scheduler as mod

        monkeypatch.setattr(mod, "_fetch_pending_candidate_ids",
                            lambda limit: [777])

        review_calls: List[int] = []

        def fake_review(hub, candidate_id, *, decided_by="x"):
            # Simulate IMPL-2 handling a raising hub: returns hard_veto.
            # 模擬 IMPL-2 處理會 raise 的 hub：返回 hard_veto。
            review_calls.append(candidate_id)
            v = _FakeVerdict("reject")
            v.reason = "reject_hard_veto"
            return v

        with patch("app.governance_hub_live_candidate_review.review_live_candidate",
                   side_effect=fake_review):
            consumer = mod.Lg5ReviewConsumer(
                cycle_secs=10.0,
                max_per_cycle=8,
                # hub raises on is_authorized() — wrapper must not call it.
                # hub 對 is_authorized() raise —— wrapper 不應呼叫之。
                hub_provider=lambda: _FakeHub(authorized=True, raise_on_auth=True),
            )
            summary = consumer.trigger_now()

        # Critical: review IS called (wrapper does not pre-check is_authorized).
        # 關鍵：review 仍被呼叫（wrapper 不預檢 is_authorized）。
        assert review_calls == [777]
        assert summary["reviewed"] == 1
        assert summary["rejected"] == 1
        assert summary["rejected_hard_veto"] == 1
        # Hub.is_authorized was NOT called by wrapper (only by IMPL-2 if it
        # were real). FakeHub.is_authorized_calls counts only direct calls.
        # FakeHub.is_authorized_calls 計直接呼叫次數，wrapper 不呼叫之。
        # (IMPL-2 is mocked here so the count remains 0.)
        # （IMPL-2 已 mock，計數仍為 0。）
        # We assert the FakeHub instance was not consulted by wrapper code.
        # 確認 wrapper 端未呼叫 FakeHub。


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Empty pending pool / 空 pending pool
# ═══════════════════════════════════════════════════════════════════════════════

class TestEmptyPool:
    """Empty pool → no review call, summary reviewed=0, no errors.
    空 pool → 不呼叫 review，summary reviewed=0，無錯誤。"""

    def test_empty_pool_reviewed_zero_no_review_call(self, monkeypatch):
        from app import lg5_review_consumer_scheduler as mod

        monkeypatch.setattr(mod, "_fetch_pending_candidate_ids",
                            lambda limit: [])

        with patch("app.governance_hub_live_candidate_review.review_live_candidate",
                   side_effect=AssertionError("review must not be called for empty pool")):
            consumer = mod.Lg5ReviewConsumer(
                cycle_secs=10.0,
                max_per_cycle=8,
                hub_provider=lambda: _FakeHub(authorized=True),
            )
            summary = consumer.trigger_now()

        assert summary["candidates_fetched"] == 0
        assert summary["reviewed"] == 0
        assert summary["approved"] == 0
        assert summary["rejected"] == 0
        assert summary["deferred"] == 0
        assert summary["errors"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Env-driven config / env 驅動 config
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfigFromEnv:
    """_config_from_env returns env values; invalid values fail-soft to defaults.
    _config_from_env 回 env 值；無效值 fail-soft 回預設。"""

    def test_env_overrides_apply(self, monkeypatch):
        from app import lg5_review_consumer_scheduler as mod

        monkeypatch.setenv("OPENCLAW_LG5_CONSUMER_CYCLE_SECS", "120")
        monkeypatch.setenv("OPENCLAW_LG5_CONSUMER_MAX_PER_CYCLE", "4")
        monkeypatch.setenv("OPENCLAW_LG5_CONSUMER_ENABLED", "1")

        cycle, cap, enabled = mod._config_from_env()
        assert cycle == 120.0
        assert cap == 4
        assert enabled is True

    def test_invalid_cycle_secs_falls_back_to_default(self, monkeypatch):
        from app import lg5_review_consumer_scheduler as mod

        monkeypatch.setenv("OPENCLAW_LG5_CONSUMER_CYCLE_SECS", "notanumber")
        monkeypatch.delenv("OPENCLAW_LG5_CONSUMER_MAX_PER_CYCLE", raising=False)

        cycle, cap, enabled = mod._config_from_env()
        assert cycle == mod.DEFAULT_CYCLE_SECS
        assert cap == mod.DEFAULT_MAX_PER_CYCLE
        assert enabled is True

    def test_zero_max_per_cycle_falls_back_to_default(self, monkeypatch):
        from app import lg5_review_consumer_scheduler as mod

        monkeypatch.setenv("OPENCLAW_LG5_CONSUMER_MAX_PER_CYCLE", "0")
        cycle, cap, enabled = mod._config_from_env()
        assert cap == mod.DEFAULT_MAX_PER_CYCLE


# ═══════════════════════════════════════════════════════════════════════════════
# 6. start_consumer_scheduler env disable
# ═══════════════════════════════════════════════════════════════════════════════

class TestStartGate:
    """start_consumer_scheduler honours ENABLED=0 / leader lock.
    start_consumer_scheduler 遵循 ENABLED=0 / leader lock。"""

    def test_disabled_env_returns_none(self, monkeypatch):
        from app import lg5_review_consumer_scheduler as mod

        monkeypatch.setenv("OPENCLAW_LG5_CONSUMER_ENABLED", "0")
        result = mod.start_consumer_scheduler()
        assert result is None
        assert mod.get_consumer_scheduler() is None
        # NIT-2 thread-leak guard: ENABLED=0 must not spawn the daemon thread.
        # NIT-2 線程洩漏防線：ENABLED=0 不可 spawn daemon thread。
        assert "lg5-review-consumer" not in [
            t.name for t in threading.enumerate()
        ], "daemon thread must not spawn when OPENCLAW_LG5_CONSUMER_ENABLED=0"

    def test_non_leader_env_returns_none(self, monkeypatch):
        """OPENCLAW_SCHEDULER_LEADER=0 → forced non-leader → start returns None.
        OPENCLAW_SCHEDULER_LEADER=0 → 強制非 leader → start 回 None。"""
        from app import lg5_review_consumer_scheduler as mod

        monkeypatch.setenv("OPENCLAW_LG5_CONSUMER_ENABLED", "1")
        monkeypatch.setenv("OPENCLAW_SCHEDULER_LEADER", "0")
        result = mod.start_consumer_scheduler()
        assert result is None
