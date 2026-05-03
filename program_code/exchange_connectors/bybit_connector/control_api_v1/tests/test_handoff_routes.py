"""REF-20 R20-P6-S13 handoff_routes pytest — 6 cases pinned with mock cursor.

REF-20 R20-P6-S13 handoff_routes pytest — 用 mock cursor 釘 6 個 case。

MODULE_NOTE (EN):
    Wave 8 R20-P6-S13 (server-side regex + cooldown) + R20-P6-S14
    (V044 UNIQUE retrofit caller path) + R20-P6-S15 (atomic audit emit).
    Pins six load-bearing behaviours of post_handoff() via in-memory fake
    cursor + monkeypatched _emit_handoff_audit:

      1. Phrase format invalid (regex miss) → 400 phrase_format_invalid
      2. Phrase mismatch (HANDOFF wrong-uuid) → 400 phrase_mismatch
      3. Cooldown in progress (same actor, last ts within 30s) → 429
      4. Cooldown bypass (different actor) → 200
      5. Idempotency cached return → 200 + cached=true
      6. Audit emit row written via _emit_handoff_audit cursor

    Avoids spinning up real PostgreSQL; tests must be runnable on the Mac
    dev path where psycopg2 is installed but no PG instance exists.

MODULE_NOTE (中):
    Wave 8 R20-P6-S13/S14/S15。用 in-memory fake cursor 釘 6 個 case。
    Mac dev 無 PG instance 也能跑（不接真 PG）。

Tests / 測試覆蓋:
    1. test_phrase_format_invalid_400
    2. test_phrase_mismatch_400
    3. test_cooldown_same_actor_429
    4. test_cooldown_different_actor_bypass
    5. test_idempotency_cached_return
    6. test_audit_emit_row_written
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest


# Match conftest pattern (sys.path includes control_api_v1).
# 對齊 conftest pattern（sys.path 含 control_api_v1）。
from app import handoff_routes  # noqa: E402
from app.handoff_routes import (  # noqa: E402
    COOLDOWN_SECONDS,
    HANDOFF_PHRASE_REGEX,
    HandoffRequest,
)


# ─── Constants for test / 測試常數 ──────────────────────────────────


TEST_EXPERIMENT_ID = "abcdef01-2345-6789-abcd-ef0123456789"
TEST_MANIFEST_ID = "00000000-0000-0000-0000-000000000abc"
TEST_VALID_PHRASE = f"HANDOFF {TEST_EXPERIMENT_ID}"
TEST_IDEMPOTENCY_KEY = "11111111-1111-1111-1111-111111111111"
TEST_ACTOR_ID = "test-operator-A"
TEST_OTHER_ACTOR_ID = "test-operator-B"


# ─── Fake cursor for handoff path / handoff 路徑假 cursor ───────────


class _FakeCursor:
    """Minimal psycopg2-compatible cursor for handoff route unit tests.
    Handoff route 單元測試最小 psycopg2-相容 cursor。

    Tracks SQL + params for assertion; returns canned fetchone() / fetchall()
    based on the SQL pattern (information_schema probe vs idempotency lookup
    vs cooldown query vs INSERT).

    記錄 SQL + params 供 assert；按 SQL 模式回 canned fetchone/fetchall。
    """

    def __init__(
        self,
        v044_present: bool = True,
        idempotency_cached: Optional[tuple[str, str, datetime, Optional[str]]] = None,
        last_handoff_seconds_ago: Optional[float] = None,
    ) -> None:
        self.v044_present = v044_present
        self.idempotency_cached = idempotency_cached
        self.last_handoff_seconds_ago = last_handoff_seconds_ago
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self._next_fetchone: Any = None
        self._next_fetchall: list[Any] = []
        self.audit_log_inserts: list[tuple[Any, ...]] = []

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        self.executed.append((sql, tuple(params or ())))
        sql_norm = re.sub(r"\s+", " ", sql).strip().lower()

        if "set local statement_timeout" in sql_norm:
            self._next_fetchone = None
            return

        if "information_schema.tables" in sql_norm and "handoff_requests" in sql_norm:
            self._next_fetchone = (1,) if self.v044_present else None
            return

        if "select trace_id, result, ts, reject_reason" in sql_norm:
            # Idempotency lookup.
            if self.idempotency_cached is not None:
                self._next_fetchone = self.idempotency_cached
            else:
                self._next_fetchone = None
            return

        if "extract(epoch from (now() - ts))" in sql_norm:
            # Cooldown query.
            if self.last_handoff_seconds_ago is not None:
                self._next_fetchone = (self.last_handoff_seconds_ago,)
            else:
                self._next_fetchone = None
            return

        if "insert into replay.handoff_requests" in sql_norm:
            # No fetchone needed.
            self._next_fetchone = None
            return

        if "insert into learning.governance_audit_log" in sql_norm:
            # Audit emit INSERT path (via emit_handoff_audit).
            self.audit_log_inserts.append(tuple(params or ()))
            self._next_fetchone = None
            return

        # Fallback.
        self._next_fetchone = None

    def fetchone(self) -> Any:
        return self._next_fetchone

    def fetchall(self) -> list[Any]:
        return list(self._next_fetchall)

    def close(self) -> None:
        pass


class _FakeConn:
    """Minimal psycopg2-compatible connection wrapping FakeCursor.
    最小 psycopg2-相容 connection 包 FakeCursor。
    """

    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor
        self.commits: int = 0
        self.rollbacks: int = 0

    def cursor(self) -> _FakeCursor:
        return self._cursor

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


@pytest.fixture
def patch_db(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Patch get_pg_conn + emit_handoff_audit + AuthenticatedActor.
    Patch get_pg_conn / emit_handoff_audit / AuthenticatedActor。

    Returns dict with 'cursor' / 'conn' for assertion access.
    回傳 dict 含 cursor / conn 供 assert。
    """
    cursor = _FakeCursor()
    conn = _FakeConn(cursor)

    class _CtxMgr:
        def __enter__(self_inner) -> _FakeConn:
            return conn

        def __exit__(self_inner, *args: Any) -> None:
            return None

    monkeypatch.setattr(handoff_routes, "get_pg_conn", lambda: _CtxMgr())

    # Track audit emit calls.
    audit_calls: list[dict[str, Any]] = []

    def _fake_emit(
        *,
        actor_id: str,
        request: Any,
        result: str,
        trace_id: str,
        reject_reason: Optional[str] = None,
        cached: bool = False,
        cursor: Any = None,
    ) -> bool:
        audit_calls.append({
            "actor_id": actor_id,
            "experiment_id": request.experiment_id,
            "result": result,
            "trace_id": trace_id,
            "reject_reason": reject_reason,
            "cached": cached,
        })
        # Simulate INSERT via cursor for atomic test assertion.
        if cursor is not None:
            cursor.execute(
                "INSERT INTO learning.governance_audit_log (event_type) VALUES (%s)",
                ("replay_handoff_request",),
            )
        return True

    monkeypatch.setattr(handoff_routes, "_emit_handoff_audit", _fake_emit)

    return {
        "cursor": cursor,
        "conn": conn,
        "audit_calls": audit_calls,
    }


def _make_actor(actor_id: str = TEST_ACTOR_ID) -> Any:
    """Return a stub AuthenticatedActor with operator role + replay:write scope.
    回傳 stub AuthenticatedActor（有 operator 角色 + replay:write scope）。
    """
    actor = MagicMock()
    actor.actor_id = actor_id
    actor.actor_type = "operator"
    actor.roles = {"operator"}
    actor.scopes = {"replay:write"}
    return actor


# ─── Test 1: Phrase format invalid → 400 ────────────────────────────


def test_phrase_format_invalid_400(patch_db: dict[str, Any]) -> None:
    """Server-side regex miss → 400 phrase_format_invalid (P6-S13).
    server-side regex 不過 → 400 phrase_format_invalid（P6-S13）。
    """
    body = HandoffRequest(
        experiment_id=TEST_EXPERIMENT_ID,
        manifest_id=TEST_MANIFEST_ID,
        # Capital letters not allowed by regex; pad to 44 chars (8+36).
        # 大寫字母 regex 不允；補到 44 字（8+36）。
        typed_phrase="HANDOFF ABCDEF01-2345-6789-ABCD-EF0123456789",
        operator_notes=None,
    )
    actor = _make_actor()

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(handoff_routes.post_handoff(
            body=body,
            actor=actor,
            idempotency_key=TEST_IDEMPOTENCY_KEY,
        ))
    assert exc_info.value.status_code == 400
    assert "phrase_format_invalid" in str(exc_info.value.detail)


# ─── Test 2: Phrase mismatch → 400 ──────────────────────────────────


def test_phrase_mismatch_400(patch_db: dict[str, Any]) -> None:
    """Format passes but experiment_id substring wrong → 400 phrase_mismatch.
    格式過但 experiment_id 子串不對 → 400 phrase_mismatch。
    """
    # Different experiment_id in phrase vs body field; both valid format.
    # phrase 與 body 的 experiment_id 不同；兩者皆合格式。
    wrong_id = "ffffffff-ffff-ffff-ffff-ffffffffffff"
    body = HandoffRequest(
        experiment_id=TEST_EXPERIMENT_ID,
        manifest_id=TEST_MANIFEST_ID,
        typed_phrase=f"HANDOFF {wrong_id}",
        operator_notes=None,
    )
    actor = _make_actor()

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(handoff_routes.post_handoff(
            body=body,
            actor=actor,
            idempotency_key=TEST_IDEMPOTENCY_KEY,
        ))
    assert exc_info.value.status_code == 400
    assert "phrase_mismatch" in str(exc_info.value.detail)


# ─── Test 3: Cooldown same actor → 429 ──────────────────────────────


def test_cooldown_same_actor_429(patch_db: dict[str, Any]) -> None:
    """Same actor, last handoff 5s ago → 429 cooldown_in_progress.
    同 actor 5s 前剛 handoff → 429 cooldown_in_progress。
    """
    # Patch cursor: V044 present, no cached, last handoff 5s ago.
    # patch cursor：V044 在、無 cached、上次 5s 前。
    patch_db["cursor"].last_handoff_seconds_ago = 5.0

    body = HandoffRequest(
        experiment_id=TEST_EXPERIMENT_ID,
        manifest_id=TEST_MANIFEST_ID,
        typed_phrase=TEST_VALID_PHRASE,
        operator_notes=None,
    )
    actor = _make_actor()

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(handoff_routes.post_handoff(
            body=body,
            actor=actor,
            idempotency_key=TEST_IDEMPOTENCY_KEY,
        ))
    assert exc_info.value.status_code == 429
    detail_str = str(exc_info.value.detail)
    assert "cooldown_in_progress" in detail_str


# ─── Test 4: Cooldown bypass (different actor) → 200 ───────────────


def test_cooldown_different_actor_bypass(patch_db: dict[str, Any]) -> None:
    """Different actor → cooldown does NOT apply; success path.
    不同 actor → cooldown 不適用；走 success path。

    The cooldown query in _do_handoff_pg() filters by actor_id; if the
    actor in the request differs from any prior actor, the query returns
    no rows and cooldown gate passes.
    Cooldown 查詢按 actor_id 過濾；不同 actor 查不到 row、cooldown 過。
    """
    # Patch cursor: V044 present, no idempotency cached, NO recent handoff
    # for this actor (different actor's row would not appear because
    # SQL filters by actor_id).
    # patch cursor：V044 在、無 cached、本 actor 無 recent handoff
    # （SQL 以 actor_id 過濾，他 actor row 查不到）。
    patch_db["cursor"].last_handoff_seconds_ago = None

    body = HandoffRequest(
        experiment_id=TEST_EXPERIMENT_ID,
        manifest_id=TEST_MANIFEST_ID,
        typed_phrase=TEST_VALID_PHRASE,
        operator_notes=None,
    )
    # Different actor (TEST_OTHER_ACTOR_ID).
    actor = _make_actor(actor_id=TEST_OTHER_ACTOR_ID)

    response = asyncio.run(handoff_routes.post_handoff(
        body=body,
        actor=actor,
        idempotency_key=TEST_IDEMPOTENCY_KEY,
    ))
    assert response["ok"] is True
    assert response["data"]["actor_id"] == TEST_OTHER_ACTOR_ID
    assert response["data"]["cached"] is False
    assert response["data"]["result"] == "success"
    assert response["data"]["trace_id"] is not None


# ─── Test 5: Idempotency cached return → 200 + cached=true ─────────


def test_idempotency_cached_return(patch_db: dict[str, Any]) -> None:
    """V044 UNIQUE(actor_id, idempotency_key) hit → 200 cached=true.
    V044 UNIQUE 命中 → 200 cached=true。
    """
    # Patch cursor: V044 present, idempotency cached row exists.
    # patch cursor：V044 在、idempotency cached row 已存在。
    cached_trace_id = "1700000000000-deadbeef-1111-2222-3333-444455556666"
    cached_ts = datetime.now(timezone.utc) - timedelta(minutes=5)
    patch_db["cursor"].idempotency_cached = (
        cached_trace_id, "success", cached_ts, None,
    )

    body = HandoffRequest(
        experiment_id=TEST_EXPERIMENT_ID,
        manifest_id=TEST_MANIFEST_ID,
        typed_phrase=TEST_VALID_PHRASE,
        operator_notes=None,
    )
    actor = _make_actor()

    response = asyncio.run(handoff_routes.post_handoff(
        body=body,
        actor=actor,
        idempotency_key=TEST_IDEMPOTENCY_KEY,
    ))
    assert response["ok"] is True
    assert response["data"]["cached"] is True
    assert response["data"]["trace_id"] == cached_trace_id
    assert response["data"]["result"] == "success"


# ─── Test 6: Audit emit row written via cursor ─────────────────────


def test_audit_emit_row_written(patch_db: dict[str, Any]) -> None:
    """Success path emits one audit row via emit_handoff_audit cursor.
    success 路徑經 emit_handoff_audit cursor 寫一列 audit row。

    Verifies P6-S15 atomic write contract: audit row INSERT happens
    under the same cursor as replay.handoff_requests INSERT.
    驗 P6-S15 原子寫契約：audit row INSERT 與 handoff_requests INSERT
    同 cursor。
    """
    # Patch cursor: V044 present, no cached, no recent handoff.
    # patch cursor：V044 在、無 cached、無 recent。
    body = HandoffRequest(
        experiment_id=TEST_EXPERIMENT_ID,
        manifest_id=TEST_MANIFEST_ID,
        typed_phrase=TEST_VALID_PHRASE,
        operator_notes="test operator notes",
    )
    actor = _make_actor()

    response = asyncio.run(handoff_routes.post_handoff(
        body=body,
        actor=actor,
        idempotency_key=TEST_IDEMPOTENCY_KEY,
    ))
    assert response["ok"] is True
    assert response["data"]["cached"] is False

    # Audit emit was called once with success result.
    audit_calls = patch_db["audit_calls"]
    assert len(audit_calls) == 1
    call = audit_calls[0]
    assert call["actor_id"] == TEST_ACTOR_ID
    assert call["experiment_id"] == TEST_EXPERIMENT_ID
    assert call["result"] == "success"
    assert call["reject_reason"] is None

    # Verify audit row INSERT happened under the same cursor (P6-S15 atomic).
    audit_inserts = patch_db["cursor"].audit_log_inserts
    assert len(audit_inserts) == 1
    # event_type was 'replay_handoff_request'.
    assert audit_inserts[0][0] == "replay_handoff_request"


# ─── Bonus: regex itself / regex 自身 ────────────────────────────


def test_handoff_phrase_regex_canonical_examples() -> None:
    """V3 §12 #20 server-side regex matches valid + rejects invalid examples.
    V3 §12 #20 server-side regex 接合法、拒非法示例。
    """
    # Valid: lowercase + digits + hyphens, exactly 36 chars after 'HANDOFF '.
    assert HANDOFF_PHRASE_REGEX.match(
        "HANDOFF abcdef01-2345-6789-abcd-ef0123456789"
    )

    # Invalid: uppercase letters in UUID.
    assert not HANDOFF_PHRASE_REGEX.match(
        "HANDOFF ABCDEF01-2345-6789-abcd-ef0123456789"
    )

    # Invalid: missing prefix space.
    assert not HANDOFF_PHRASE_REGEX.match(
        "HANDOFFabcdef01-2345-6789-abcd-ef0123456789"
    )

    # Invalid: prefix lowercase.
    assert not HANDOFF_PHRASE_REGEX.match(
        "handoff abcdef01-2345-6789-abcd-ef0123456789"
    )

    # Invalid: trailing junk.
    assert not HANDOFF_PHRASE_REGEX.match(
        "HANDOFF abcdef01-2345-6789-abcd-ef0123456789 "
    )

    # Invalid: too short.
    assert not HANDOFF_PHRASE_REGEX.match("HANDOFF abc")
