"""wave9_audit_incident_scan — pytest fixtures + scenarios.

wave9_audit_incident_scan — pytest 場景測試。

MODULE_NOTE (EN): REF-20 Wave 9 R20-W9-T3. Pins four load-bearing
  behaviours of the audit incident scan cron via a hand-rolled
  in-memory fake cursor that simulates V035 governance_audit_log + V048:

    1. V035 absent → graceful exit 0 (cron entry safe pre-V035).
    2. V035 present + V048 absent → scan runs but no UPSERT (graceful).
    3. 0 incidents in 14d window → silent exit 0 + 0 V048 row.
    4. 3 incidents (1 handoff_rejected + 1 key_rotation + 1 generic)
       → exit 1 + 3 V048 UPSERT.

  Avoids spinning up real PostgreSQL; mirrors sibling cron test pattern.

MODULE_NOTE (中): REF-20 Wave 9 R20-W9-T3。用手寫 in-memory fake cursor
  釘死 audit incident scan cron 4 條 load-bearing 行為，模擬 V035 + V048：

    1. V035 缺 → graceful exit 0（cron 條目可在 V035 land 前安裝）。
    2. V035 在 + V048 缺 → scan 跑但無 UPSERT（graceful）。
    3. 14d 窗口 0 incident → silent exit 0 + 0 V048 row。
    4. 3 incidents → exit 1 + 3 V048 UPSERT。

  不需真 PostgreSQL；對齊 sibling cron 測試模式。

Tests / 測試覆蓋:
  1. test_v035_absent_returns_graceful_exit_0
  2. test_v048_absent_scan_runs_but_no_upsert
  3. test_zero_incidents_silent_exit_0
  4. test_three_incidents_exit_1_with_three_upserts
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


_CRON_DIR = Path(__file__).resolve().parent
if str(_CRON_DIR) not in sys.path:
    sys.path.insert(0, str(_CRON_DIR))

import wave9_audit_incident_scan as scan_cron  # noqa: E402


# ─── Fake cursor / 假 cursor ─────────────────────────────────────────


class _FakeCursor:
    """Minimal psycopg2-compatible cursor for incident scan tests.

    Incident scan 測試最小 psycopg2-相容 cursor。

    Tracks executed SQL + params; canned fetchone() based on presence flags.

    記錄 execute SQL + params；依配置回 fetchone。
    """

    def __init__(
        self,
        v035_present: bool = True,
        v048_present: bool = True,
        handoff_rejected_count: int = 0,
        handoff_rejected_first_ts: datetime | None = None,
        handoff_rejected_last_ts: datetime | None = None,
        handoff_rejected_payload: dict[str, Any] | None = None,
        key_rotation_count: int = 0,
        key_rotation_first_ts: datetime | None = None,
        key_rotation_last_ts: datetime | None = None,
        key_rotation_payload: dict[str, Any] | None = None,
        audit_failed_count: int = 0,
        audit_failed_first_ts: datetime | None = None,
        audit_failed_last_ts: datetime | None = None,
        audit_failed_payload: dict[str, Any] | None = None,
    ) -> None:
        self.v035_present = v035_present
        self.v048_present = v048_present
        # Canned response data per scanner.
        # 每 scanner 預設回應資料。
        self._handoff_rejected = (
            handoff_rejected_count,
            handoff_rejected_first_ts,
            handoff_rejected_last_ts,
            handoff_rejected_payload,
        )
        self._key_rotation = (
            key_rotation_count,
            key_rotation_first_ts,
            key_rotation_last_ts,
            key_rotation_payload,
        )
        self._audit_failed = (
            audit_failed_count,
            audit_failed_first_ts,
            audit_failed_last_ts,
            audit_failed_payload,
        )
        self.executed: list[tuple[str, Any]] = []
        self._next_fetchone: Any = None
        self.upserted_count = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql: str, params: Any = None) -> None:
        self.executed.append((sql, params))
        sql_lower = sql.lower()

        # information_schema probe.
        if "information_schema.tables" in sql_lower and params:
            schema, table = params[0], params[1]
            if schema == "learning" and table == "governance_audit_log":
                self._next_fetchone = (1,) if self.v035_present else None
            elif schema == "replay" and table == "audit_incident_summaries":
                self._next_fetchone = (1,) if self.v048_present else None
            else:
                self._next_fetchone = None
            return

        # Scanner queries — match by content.
        # Scanner 查詢 — 用內容判斷。
        if (
            "from learning.governance_audit_log" in sql_lower
            and "replay_handoff_request" in sql_lower
            and "rejected" in sql_lower
        ):
            self._next_fetchone = self._handoff_rejected
            return
        if (
            "from learning.governance_audit_log" in sql_lower
            and "replay_key_rotation_due" in sql_lower
        ):
            self._next_fetchone = self._key_rotation
            return
        if (
            "from learning.governance_audit_log" in sql_lower
            and "audit_write_failed" in sql_lower
            and "replay_key_rotation_due" not in sql_lower.split("(")[1]
            if "(" in sql_lower
            else False
        ):
            # The audit_failed_other scanner runs the most complex query;
            # we match it by exclusion-list shape ("NOT IN (...)").
            # audit_failed_other 用排除清單 NOT IN (...) 模式。
            self._next_fetchone = self._audit_failed
            return
        # Fallback for the audit_failed_other scanner: match the NOT IN pattern.
        # Fallback：用 NOT IN 模式抓 audit_failed_other。
        if "not in (" in sql_lower and "replay_no_live_mutation_violation" in sql_lower:
            self._next_fetchone = self._audit_failed
            return

        # UPSERT to V048.
        if "insert into replay.audit_incident_summaries" in sql_lower:
            self.upserted_count += 1
            self._next_fetchone = None
            return

        # Default: nothing to fetch.
        self._next_fetchone = None

    def fetchone(self) -> Any:
        return self._next_fetchone


class _FakeConn:
    """Minimal psycopg2-compatible connection.
    最小 psycopg2-相容 connection。
    """

    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor
        self.rolled_back = False
        self.closed = False
        self.committed = False

    def cursor(self) -> _FakeCursor:
        return self._cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.committed = True
        return False

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


# ─── Fixtures / 固件 ─────────────────────────────────────────────────


@pytest.fixture
def env_with_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set OPENCLAW_DATABASE_URL.
    設 OPENCLAW_DATABASE_URL。
    """
    monkeypatch.setenv(
        "OPENCLAW_DATABASE_URL",
        "postgresql://redacted@127.0.0.1:5432/fake",
    )


# ─── Tests / 測試 ────────────────────────────────────────────────────


def test_v035_absent_returns_graceful_exit_0(env_with_dsn: None) -> None:
    """V035 governance_audit_log absent → graceful exit 0; no scanners run.
    V035 缺 → graceful exit 0；scanner 不跑。
    """
    fake_cur = _FakeCursor(v035_present=False)
    fake_conn = _FakeConn(fake_cur)
    fake_psycopg2 = MagicMock()
    fake_psycopg2.connect.return_value = fake_conn
    with patch.dict("sys.modules", {"psycopg2": fake_psycopg2}):
        rc = scan_cron.main()

    assert rc == 0, f"expected exit=0 graceful, got {rc}"
    # No INSERTs since scanners didn't run.
    # 因 scanner 未跑，無 INSERT。
    inserts = [
        sql for sql, _ in fake_cur.executed
        if "insert into" in sql.lower()
    ]
    assert len(inserts) == 0
    # No scanner SELECT either (early return).
    # 也無 scanner SELECT（早期 return）。
    scanner_selects = [
        sql for sql, _ in fake_cur.executed
        if "from learning.governance_audit_log" in sql.lower()
        and "where ts" in sql.lower()
    ]
    assert len(scanner_selects) == 0


def test_v048_absent_scan_runs_but_no_upsert(env_with_dsn: None) -> None:
    """V035 present + V048 absent → scanners run but UPSERT skipped.
    V035 在 + V048 缺 → scanner 跑但 UPSERT 跳過。
    """
    fake_cur = _FakeCursor(
        v035_present=True,
        v048_present=False,
        # Seed a violation so we exercise the violation path.
        # Seed 一個違反，跑 violation path。
        handoff_rejected_count=2,
        handoff_rejected_first_ts=datetime(2026, 4, 25, tzinfo=timezone.utc),
        handoff_rejected_last_ts=datetime(2026, 4, 28, tzinfo=timezone.utc),
        handoff_rejected_payload={"reject_reason": "phrase_mismatch"},
    )
    fake_conn = _FakeConn(fake_cur)
    fake_psycopg2 = MagicMock()
    fake_psycopg2.connect.return_value = fake_conn
    with patch.dict("sys.modules", {"psycopg2": fake_psycopg2}):
        rc = scan_cron.main()

    # Violation detected → exit 1.
    # 違反偵測 → exit 1。
    assert rc == 1, f"expected exit=1 (incidents found), got {rc}"
    # 0 V048 UPSERT because V048 absent.
    # V048 缺，0 UPSERT。
    assert fake_cur.upserted_count == 0


def test_zero_incidents_silent_exit_0(env_with_dsn: None) -> None:
    """V035 + V048 present + 0 incidents → silent exit 0 + 0 UPSERT.
    V035 + V048 在 + 0 incident → silent exit 0 + 0 UPSERT。
    """
    fake_cur = _FakeCursor(
        v035_present=True,
        v048_present=True,
        # All scanners return 0 count → no IncidentSummary.
        # 全 scanner 回 0 count → 無 IncidentSummary。
        handoff_rejected_count=0,
        key_rotation_count=0,
        audit_failed_count=0,
    )
    fake_conn = _FakeConn(fake_cur)
    fake_psycopg2 = MagicMock()
    fake_psycopg2.connect.return_value = fake_conn
    with patch.dict("sys.modules", {"psycopg2": fake_psycopg2}):
        rc = scan_cron.main()

    assert rc == 0
    assert fake_cur.upserted_count == 0


def test_three_incidents_exit_1_with_three_upserts(env_with_dsn: None) -> None:
    """3 violations across 3 scanners → exit 1 + 3 V048 UPSERT.
    3 違反跨 3 scanner → exit 1 + 3 V048 UPSERT。
    """
    fake_cur = _FakeCursor(
        v035_present=True,
        v048_present=True,
        # 1 handoff_rejected.
        handoff_rejected_count=2,
        handoff_rejected_first_ts=datetime(2026, 4, 25, tzinfo=timezone.utc),
        handoff_rejected_last_ts=datetime(2026, 4, 28, tzinfo=timezone.utc),
        handoff_rejected_payload={"reject_reason": "phrase_mismatch"},
        # 1 key_rotation.
        key_rotation_count=1,
        key_rotation_first_ts=datetime(2026, 4, 27, tzinfo=timezone.utc),
        key_rotation_last_ts=datetime(2026, 4, 27, tzinfo=timezone.utc),
        key_rotation_payload={"alert_type": "replay_key_rotation_due", "env": "live"},
        # 1 audit_failed_other.
        audit_failed_count=3,
        audit_failed_first_ts=datetime(2026, 4, 22, tzinfo=timezone.utc),
        audit_failed_last_ts=datetime(2026, 4, 30, tzinfo=timezone.utc),
        audit_failed_payload={"alert_type": "schema_drift", "table": "trading.fills"},
    )
    fake_conn = _FakeConn(fake_cur)
    fake_psycopg2 = MagicMock()
    fake_psycopg2.connect.return_value = fake_conn
    with patch.dict("sys.modules", {"psycopg2": fake_psycopg2}):
        rc = scan_cron.main()

    # Violations → exit 1.
    # 違反 → exit 1。
    assert rc == 1, f"expected exit=1, got {rc}"
    # 3 V048 UPSERT row (1 per scanner with count > 0).
    # 3 V048 UPSERT row（每 scanner count > 0 一 row）。
    assert fake_cur.upserted_count == 3, (
        f"expected 3 UPSERTs, got {fake_cur.upserted_count}"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
