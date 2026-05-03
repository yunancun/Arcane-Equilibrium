"""REF-20 R20-P6-S15 handoff_audit pytest — 3 cases pinned with mock cursor.

REF-20 R20-P6-S15 handoff_audit pytest — 用 mock cursor 釘 3 個 case。

MODULE_NOTE (EN):
    Wave 8 R20-P6-S15 (audit row to learning.governance_audit_log).
    Pins three load-bearing security behaviours:

      1. Audit emit on success path: INSERT row with event_type=
         'replay_handoff_request' + payload contains trace_id +
         typed_phrase_hash.
      2. Audit emit on rejection path (cooldown / format / mismatch): same
         INSERT with result='rejected' in payload.
      3. typed_phrase NEVER stored raw — only SHA-256 hash; raw phrase
         absent from payload, decided_by, and any column.

    Avoids real PG; tests must be runnable on Mac dev path.

MODULE_NOTE (中):
    Wave 8 R20-P6-S15。釘 3 個關鍵安全行為：success / rejection 都寫 audit
    row、typed_phrase 永不存 raw（只存 SHA-256 hash）。

Tests / 測試覆蓋:
    1. test_audit_emit_success_writes_event_type
    2. test_audit_emit_rejection_writes_event_type_with_reject_reason
    3. test_typed_phrase_hash_never_raw_stored
"""

from __future__ import annotations

import json
from typing import Any

import pytest


# Match conftest pattern (sys.path includes control_api_v1).
# 對齊 conftest pattern。
from replay.handoff_audit import (  # noqa: E402
    HANDOFF_AUDIT_DECIDED_BY_TEMPLATE,
    HANDOFF_AUDIT_EVENT_TYPE,
    HandoffAuditRequest,
    emit_handoff_audit,
    hash_typed_phrase,
)


# ─── Test fixtures / 測試夾具 ────────────────────────────────────────


class _RecordingCursor:
    """Records SQL + params for assertion; no actual DB.
    記錄 SQL + params 供 assert；無真 DB。
    """

    def __init__(self) -> None:
        self.executes: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        self.executes.append((sql, tuple(params or ())))


def _build_request() -> HandoffAuditRequest:
    """Standard test request with realistic UUID-style ids.
    含真實 UUID-style id 的標準測試 request。
    """
    return HandoffAuditRequest(
        experiment_id="abcdef01-2345-6789-abcd-ef0123456789",
        manifest_id="00000000-0000-0000-0000-000000000abc",
        typed_phrase="HANDOFF abcdef01-2345-6789-abcd-ef0123456789",
        idempotency_key="11111111-1111-1111-1111-111111111111",
        operator_notes="test handoff",
    )


# ─── Test 1: Audit emit on success → row written ───────────────────


def test_audit_emit_success_writes_event_type() -> None:
    """Success path emits one row with event_type='replay_handoff_request'.
    success 路徑寫一列 event_type='replay_handoff_request'。
    """
    cur = _RecordingCursor()
    request = _build_request()
    actor_id = "test-operator"
    trace_id = "1700000000000-deadbeef-1234-5678-9abc-defabcdef012"

    ok = emit_handoff_audit(
        actor_id=actor_id,
        request=request,
        result="success",
        trace_id=trace_id,
        reject_reason=None,
        cached=False,
        cursor=cur,
    )
    assert ok is True

    # Exactly one INSERT executed.
    assert len(cur.executes) == 1
    sql, params = cur.executes[0]
    assert "INSERT INTO learning.governance_audit_log" in sql
    # First param is event_type.
    assert params[0] == HANDOFF_AUDIT_EVENT_TYPE
    assert params[0] == "replay_handoff_request"

    # decided_by is templated.
    # decided_by index = -2 in V035 INSERT (decided_by, payload).
    decided_by_param = params[-2]
    assert decided_by_param == HANDOFF_AUDIT_DECIDED_BY_TEMPLATE.format(
        actor_id=actor_id
    )

    # payload JSONB has expected fields.
    payload_str = params[-1]  # last param is payload JSONB
    payload = json.loads(payload_str)
    assert payload["trace_id"] == trace_id
    assert payload["experiment_id"] == request.experiment_id
    assert payload["manifest_id"] == request.manifest_id
    assert payload["idempotency_key"] == request.idempotency_key
    assert payload["result"] == "success"
    assert payload["cached"] is False
    assert payload["reject_reason"] is None
    assert "typed_phrase_hash" in payload


# ─── Test 2: Audit emit on rejection → row written with reject_reason ─


def test_audit_emit_rejection_writes_event_type_with_reject_reason() -> None:
    """Rejection path emits row with result='rejected' + reject_reason in payload.
    rejection 路徑寫 result='rejected' + reject_reason 在 payload。
    """
    cur = _RecordingCursor()
    request = _build_request()
    actor_id = "test-operator"
    trace_id = "1700000000000-feedface-1234-5678-9abc-defabcdef012"

    ok = emit_handoff_audit(
        actor_id=actor_id,
        request=request,
        result="rejected",
        trace_id=trace_id,
        reject_reason="cooldown_in_progress",
        cached=False,
        cursor=cur,
    )
    assert ok is True
    assert len(cur.executes) == 1

    sql, params = cur.executes[0]
    assert "INSERT INTO learning.governance_audit_log" in sql
    # event_type still 'replay_handoff_request' (V035 enum extended by V044).
    assert params[0] == HANDOFF_AUDIT_EVENT_TYPE

    # payload contains reject_reason.
    payload = json.loads(params[-1])
    assert payload["result"] == "rejected"
    assert payload["reject_reason"] == "cooldown_in_progress"


# ─── Test 3: typed_phrase NEVER stored raw ──────────────────────────


def test_typed_phrase_hash_never_raw_stored() -> None:
    """Raw typed_phrase absent from any persisted column / payload.
    raw typed_phrase 在任一持久化 column / payload 都不在。

    Security contract (P6-S15 + V044 typed_phrase_hash column):
      - typed_phrase_hash = sha256_hex(phrase) is computed BEFORE INSERT.
      - The raw phrase string ("HANDOFF abcdef01-...") MUST NOT appear in:
        - any INSERT param value;
        - the payload JSONB;
        - decided_by;
        - column values.
    安全契約：raw phrase 不能出現在任一 INSERT param、payload、decided_by 或欄位。
    """
    cur = _RecordingCursor()
    request = _build_request()
    raw_phrase = request.typed_phrase
    actor_id = "test-operator"
    trace_id = "1700000000000-cafebabe-1234-5678-9abc-defabcdef012"

    ok = emit_handoff_audit(
        actor_id=actor_id,
        request=request,
        result="success",
        trace_id=trace_id,
        reject_reason=None,
        cached=False,
        cursor=cur,
    )
    assert ok is True
    assert len(cur.executes) == 1

    sql, params = cur.executes[0]

    # Verify raw phrase NOT in any param.
    # 驗 raw phrase 不在任一 param。
    for i, p in enumerate(params):
        if isinstance(p, str):
            assert raw_phrase not in p, (
                f"raw typed_phrase found in INSERT param {i}: {p!r}"
            )

    # Verify hash IS in payload.
    # 驗 hash 在 payload。
    payload_str = params[-1]
    payload = json.loads(payload_str)
    assert "typed_phrase_hash" in payload
    expected_hash = hash_typed_phrase(raw_phrase)
    assert payload["typed_phrase_hash"] == expected_hash

    # Verify hash is 64-char SHA-256 hex.
    # 驗 hash 是 64 字 SHA-256 hex。
    assert len(payload["typed_phrase_hash"]) == 64
    assert all(c in "0123456789abcdef" for c in payload["typed_phrase_hash"])


# ─── Bonus: cursor None raises ValueError (programmer error guard) ──


def test_emit_requires_cursor_for_atomicity() -> None:
    """emit_handoff_audit raises ValueError when cursor is None (defensive).
    cursor=None 時 emit_handoff_audit 拋 ValueError（防呆）。
    """
    request = _build_request()
    with pytest.raises(ValueError, match="cursor for transactional atomicity"):
        emit_handoff_audit(
            actor_id="test",
            request=request,
            result="success",
            trace_id="1700000000000-abc",
            cursor=None,
        )


# ─── Bonus: hash function is deterministic + collision-resistant ───


def test_hash_typed_phrase_deterministic_and_collision_resistant() -> None:
    """hash_typed_phrase produces deterministic 64-char SHA-256 hex digest.
    hash_typed_phrase 產生確定性 64 字 SHA-256 hex digest。
    """
    phrase_a = "HANDOFF abcdef01-2345-6789-abcd-ef0123456789"
    phrase_b = "HANDOFF abcdef01-2345-6789-abcd-ef0123456790"  # last digit differs

    hash_a1 = hash_typed_phrase(phrase_a)
    hash_a2 = hash_typed_phrase(phrase_a)
    hash_b = hash_typed_phrase(phrase_b)

    # Deterministic.
    assert hash_a1 == hash_a2
    # Different phrases → different hashes (SHA-256 collision resistance).
    assert hash_a1 != hash_b
    # 64-char SHA-256 hex.
    assert len(hash_a1) == 64
    assert all(c in "0123456789abcdef" for c in hash_a1)
