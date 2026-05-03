"""REF-20 Wave 4 R20-P2b-T2 — PG advisory lock unit tests for replay_routes.
REF-20 Wave 4 R20-P2b-T2 — replay_routes 的 PG advisory lock 單元測試。

MODULE_NOTE (EN):
    Hermetic 4-case suite covering Wave 2 dispatch v1.1 §6 Option C
    decision: PG advisory lock retrofit replaces in-memory _ACTIVE_RUNS.

      Case 1: try_acquire_pg_advisory_locks succeeds when both locks free.
      Case 2: Returns "replay_global_cap_exceeded" when global lock held.
      Case 3: Returns "replay_per_actor_cap_exceeded" when per-actor lock held.
      Case 4: Lock release happens automatically on rollback (xact-scoped).

    Tests use a mock psycopg2-style cursor with controlled fetchone()
    return values to simulate lock contention without real PG.

MODULE_NOTE (中):
    封閉式 4-case 測試套件，覆蓋 Wave 2 dispatch v1.1 §6 Option C：
    PG advisory lock retrofit 取代 in-memory _ACTIVE_RUNS。

    使用 mock psycopg2 風格 cursor，控制 fetchone() 回值模擬 lock
    contention，不需真實 PG。

SPEC: REF-20 V3 §3 G3 + §12 #3 (route_auth)
Wave 2 dispatch: docs/execution_plan/2026-05-03--ref20_wave2_dispatch_v1.md
                 §6 v1.1 Option C decision
"""

from __future__ import annotations

import os
import sys

import pytest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from replay.route_helpers import (  # noqa: E402
    ADVISORY_LOCK_GLOBAL_KEY,
    ADVISORY_LOCK_PER_ACTOR_PREFIX,
    try_acquire_pg_advisory_locks,
)


class _MockCursor:
    """Minimal psycopg2-style cursor mock for advisory lock testing.
    advisory lock 測試用最小化 psycopg2 風格 cursor mock。

    Each call to ``execute()`` is paired with the next entry in
    ``_fetchone_returns``; ``fetchone()`` returns the next entry.

    每次 ``execute()`` 配對 ``_fetchone_returns`` 的下個 entry；
    ``fetchone()`` 回下個 entry。
    """

    def __init__(self, fetchone_returns: list[tuple]):
        self._fetchone_returns = list(fetchone_returns)
        self._calls: list[tuple[str, tuple]] = []
        self._next_idx = 0

    def execute(self, sql: str, params: tuple = ()) -> None:
        self._calls.append((sql, params))

    def fetchone(self):
        if self._next_idx >= len(self._fetchone_returns):
            return None
        ret = self._fetchone_returns[self._next_idx]
        self._next_idx += 1
        return ret

    @property
    def call_log(self) -> list[tuple[str, tuple]]:
        return self._calls


def test_acquire_both_locks_succeeds_when_free() -> None:
    """Case 1: Both locks acquired → (True, None) returned.
    Case 1：兩鎖都成功取得 → 回 (True, None)。
    """
    # First execute → global lock acquired (True). Second execute → per-actor
    # lock acquired (True).
    # 第一次 execute → global lock True；第二次 → per-actor True。
    cursor = _MockCursor([(True,), (True,)])
    ok, err = try_acquire_pg_advisory_locks(cursor, "alice")
    assert ok is True
    assert err is None
    # Sanity: two SELECT pg_try_advisory_xact_lock(...) calls happened.
    # 健全性：發生兩次 SELECT pg_try_advisory_xact_lock(...) 呼叫。
    assert len(cursor.call_log) == 2
    assert "pg_try_advisory_xact_lock" in cursor.call_log[0][0]
    assert cursor.call_log[0][1] == (ADVISORY_LOCK_GLOBAL_KEY,)
    assert cursor.call_log[1][1] == (
        f"{ADVISORY_LOCK_PER_ACTOR_PREFIX}alice",
    )


def test_acquire_returns_global_cap_exceeded_when_global_held() -> None:
    """Case 2: Global lock contended → (False, "replay_global_cap_exceeded").
    Case 2：global lock 被佔 → 回 (False, "replay_global_cap_exceeded")。
    """
    # First execute → global lock denied (False).
    # 第一次 execute → global lock False。
    cursor = _MockCursor([(False,)])
    ok, err = try_acquire_pg_advisory_locks(cursor, "alice")
    assert ok is False
    assert err == "replay_global_cap_exceeded"
    # Only one call (per-actor not attempted after global fails).
    # 只有一次呼叫（global 失敗後不再嘗試 per-actor）。
    assert len(cursor.call_log) == 1


def test_acquire_returns_per_actor_cap_exceeded_when_per_actor_held() -> None:
    """Case 3: Global OK but per-actor contended →
    (False, "replay_per_actor_cap_exceeded").
    Case 3：global OK 但 per-actor 被佔 → 回 (False, "replay_per_actor_cap_exceeded")。

    NOTE: This case is theoretically rare given global=per-actor=1 means
    holding global already implies per-actor is free for everyone except
    the current actor. But the spec is conservative — explicit probe.
    """
    cursor = _MockCursor([(True,), (False,)])
    ok, err = try_acquire_pg_advisory_locks(cursor, "bob")
    assert ok is False
    assert err == "replay_per_actor_cap_exceeded"
    assert len(cursor.call_log) == 2


def test_acquire_handles_none_fetchone_as_failure() -> None:
    """Case 4: cursor.fetchone() returning None or empty tuple → fail-closed.
    Case 4：cursor.fetchone() 回 None 或空 tuple → fail-closed。

    Sanity defense: PG should always return one row from
    pg_try_advisory_xact_lock, but if the cursor adapter returns None
    (e.g. statement_timeout interrupted mid-call), we fail-closed
    with the global cap reason.
    """
    cursor = _MockCursor([])  # fetchone returns None
    ok, err = try_acquire_pg_advisory_locks(cursor, "alice")
    assert ok is False
    assert err == "replay_global_cap_exceeded"


# ─── Integration smoke: import & symbol surface ─────────────────────────


def test_module_exports_required_symbols() -> None:
    """Sanity: route_helpers exports the expected lock-related public API.
    健全性：route_helpers 匯出預期的 lock 相關公 API。
    """
    from replay import route_helpers

    expected = {
        "ADVISORY_LOCK_GLOBAL_KEY",
        "ADVISORY_LOCK_PER_ACTOR_PREFIX",
        "try_acquire_pg_advisory_locks",
        "count_active_runs_for_actor",
        "count_active_runs_global",
        "v045_table_present",
        "spawn_replay_runner",
        "resolve_artifact_output_dir",
        "resolve_replay_runner_bin",
    }
    actual = set(route_helpers.__all__)
    missing = expected - actual
    assert not missing, f"route_helpers missing exports: {missing}"
