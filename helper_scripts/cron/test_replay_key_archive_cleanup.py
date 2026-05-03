"""replay_key_archive_cleanup.py — pytest fixtures + scenarios.
replay_key_archive_cleanup.py — pytest 場景測試。

MODULE_NOTE (EN): REF-20 R20-P2a-S1 (Wave 2 Batch 1). Pins three
  load-bearing behaviours of the archive cleanup cron via a hand-rolled
  in-memory fake cursor that simulates the V042 archive table behaviour:
    1. V042 absent → graceful exit 0 (cron entry safe pre-V042).
    2. V042 present + 0 expired rows → 0 update + 0 audit row.
    3. V042 present + 3 expired rows → 3 UPDATE + 3 audit row insert.
  Avoids spinning up real PostgreSQL; tests must be runnable on the Mac
  dev path where psycopg2 is installed but no PG instance exists.

MODULE_NOTE (中): REF-20 R20-P2a-S1（Wave 2 Batch 1）。用手寫
  in-memory fake cursor 釘死 archive cleanup cron 三條 load-bearing
  行為，模擬 V042 archive table 行為：
    1. V042 缺 → graceful exit 0（V042 land 前 cron 條目可安裝）。
    2. V042 在 + 0 過期 row → 0 update + 0 audit row。
    3. V042 在 + 3 過期 row → 3 UPDATE + 3 audit row insert。
  不需要真 PostgreSQL；Mac dev 路徑（psycopg2 裝了但無 PG instance）
  能跑。

Tests / 測試覆蓋:
  1. V042 absent → exit 0 + log message
  2. V042 present + 0 row past retention → exit 0 + 0 update + 0 audit
  3. V042 present + 3 row past retention → exit 0 + 3 update + 3 audit
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# Ensure the cron directory is on sys.path so we can import the script as a
# module (cron entrypoint also self-runs via __name__='__main__').
# 把 cron 目錄加入 sys.path，讓我們可以 import 腳本當 module（cron 入口
# 自身用 __name__='__main__' 走）。
_CRON_DIR = Path(__file__).resolve().parent
if str(_CRON_DIR) not in sys.path:
    sys.path.insert(0, str(_CRON_DIR))

import replay_key_archive_cleanup as cleanup  # noqa: E402


# ─── Fake psycopg2 cursor / 假 cursor ─────────────────────────────────


class _FakeCursor:
    """Minimal psycopg2-compatible cursor for unit tests.
    最小 psycopg2-相容 cursor 供單元測試用。

    Tracks executed SQL + params for assertions; returns canned `fetchone()`
    / `fetchall()` based on a small in-memory script the test seeds upfront.

    記錄已 execute 的 SQL + params 供 assert；依測試預設的 in-memory
    script 回 fetchone/fetchall 結果。
    """

    def __init__(
        self,
        v042_present: bool,
        v035_present: bool,
        flipped_rows: list[tuple[str, str, datetime]],
    ) -> None:
        self.v042_present = v042_present
        self.v035_present = v035_present
        self.flipped_rows = flipped_rows
        self.executed: list[tuple[str, Any]] = []
        self._next_fetchone: Any = None
        self._next_fetchall: list[Any] | None = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql: str, params: Any = None) -> None:
        self.executed.append((sql, params))
        sql_lower = sql.lower()

        # information_schema probe for V042 / V035
        # V042 / V035 表存在偵測
        if "information_schema.tables" in sql_lower:
            if params and "replay" in params and "replay_signing_keys" in params:
                self._next_fetchone = (1,) if self.v042_present else None
            elif params and "learning" in params and "governance_audit_log" in params:
                self._next_fetchone = (1,) if self.v035_present else None
            else:
                self._next_fetchone = None
            self._next_fetchall = None
            return

        # UPDATE ... RETURNING flow
        # UPDATE ... RETURNING 流程
        if "update replay.replay_signing_keys" in sql_lower:
            self._next_fetchall = list(self.flipped_rows)
            self._next_fetchone = None
            return

        # INSERT INTO learning.governance_audit_log — no-op for the cursor;
        # caller asserts via len(executed) growth.
        # INSERT 至 governance_audit_log — cursor 內無動作；caller 用
        # executed list 增量 assert。
        if "insert into learning.governance_audit_log" in sql_lower:
            self._next_fetchone = None
            self._next_fetchall = None
            return

        # Default: nothing to fetch.
        self._next_fetchone = None
        self._next_fetchall = None

    def fetchone(self) -> Any:
        return self._next_fetchone

    def fetchall(self) -> list[Any]:
        if self._next_fetchall is None:
            return []
        return self._next_fetchall


class _FakeConn:
    """Minimal psycopg2-compatible connection wrapping a single cursor.
    最小 psycopg2-相容 connection 包一個 cursor。
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
        # psycopg2 conn-context auto-commits on no exception.
        # psycopg2 conn-context 無 exception 自動 commit。
        if exc_type is None:
            self.committed = True
        return False

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


# ─── Fixtures / 固件 ──────────────────────────────────────────────────


@pytest.fixture
def env_with_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set OPENCLAW_DATABASE_URL so _build_dsn() returns a non-None DSN.
    設 OPENCLAW_DATABASE_URL 讓 _build_dsn() 回非 None DSN。

    DSN value is irrelevant — we mock psycopg2.connect, but the script
    requires the env var to be present to reach the connection step.

    DSN 值不重要 — 我們 mock psycopg2.connect；但腳本要求 env var 存在
    才能到 connect 步驟。
    """
    monkeypatch.setenv("OPENCLAW_DATABASE_URL", "postgresql://fake:fake@127.0.0.1:5432/fake")


# ─── Tests / 測試 ────────────────────────────────────────────────────


def test_v042_absent_exits_0_graceful(env_with_dsn: None) -> None:
    """V042 not yet applied → graceful exit 0 + log message.
    V042 尚未 apply → graceful exit 0 + log 訊息。
    """
    fake_cur = _FakeCursor(v042_present=False, v035_present=True, flipped_rows=[])
    fake_conn = _FakeConn(fake_cur)

    with patch.object(cleanup, "_build_dsn", return_value="postgresql://fake"):
        # Mock psycopg2 module via sys.modules to avoid touching real DB.
        # 用 sys.modules mock psycopg2 module，避免碰真 DB。
        fake_psycopg2 = MagicMock()
        fake_psycopg2.connect.return_value = fake_conn
        with patch.dict("sys.modules", {"psycopg2": fake_psycopg2}):
            rc = cleanup.main()

    assert rc == 0, f"expected exit=0 graceful, got {rc}"
    # First (and only) execute should be the V042 information_schema probe.
    # 第一條（也是唯一）execute 應是 V042 information_schema probe。
    assert len(fake_cur.executed) == 1, (
        f"expected exactly 1 execute (V042 probe), got {len(fake_cur.executed)}: "
        f"{fake_cur.executed!r}"
    )
    sql, params = fake_cur.executed[0]
    assert "information_schema.tables" in sql.lower()
    assert params == ("replay", "replay_signing_keys")


def test_v042_present_zero_rows_past_retention(env_with_dsn: None) -> None:
    """V042 present + 0 row past retention → 0 update + 0 audit insert.
    V042 在 + 0 過期 row → 0 update + 0 audit insert。
    """
    fake_cur = _FakeCursor(v042_present=True, v035_present=True, flipped_rows=[])
    fake_conn = _FakeConn(fake_cur)

    with patch.object(cleanup, "_build_dsn", return_value="postgresql://fake"):
        fake_psycopg2 = MagicMock()
        fake_psycopg2.connect.return_value = fake_conn
        with patch.dict("sys.modules", {"psycopg2": fake_psycopg2}):
            rc = cleanup.main()

    assert rc == 0, f"expected exit=0, got {rc}"
    # Expected execute sequence: V042 probe, UPDATE...RETURNING.
    # No V035 probe and no INSERT (because flipped is empty).
    # 期望 execute 序列：V042 probe、UPDATE...RETURNING。
    # 無 V035 probe 也無 INSERT（flipped 空）。
    assert len(fake_cur.executed) == 2, (
        f"expected 2 executes (V042 probe + UPDATE), got {len(fake_cur.executed)}: "
        f"{fake_cur.executed!r}"
    )
    # No INSERT INTO governance_audit_log.
    # 不能有 governance_audit_log INSERT。
    inserts = [
        sql for sql, _ in fake_cur.executed
        if "insert into learning.governance_audit_log" in sql.lower()
    ]
    assert len(inserts) == 0, f"unexpected INSERT(s): {inserts}"


def test_v042_present_three_rows_past_retention(env_with_dsn: None) -> None:
    """V042 present + 3 row past retention → 3 UPDATE returns + 3 audit insert.
    V042 在 + 3 過期 row → 3 UPDATE 回 row + 3 audit insert。
    """
    now = datetime.now(timezone.utc)
    rows: list[tuple[str, str, datetime]] = [
        ("paper", "abc1234567890def", now - timedelta(days=181)),
        ("demo", "fedcba9876543210", now - timedelta(days=200)),
        ("live", "0011223344556677", now - timedelta(days=250)),
    ]
    fake_cur = _FakeCursor(v042_present=True, v035_present=True, flipped_rows=rows)
    fake_conn = _FakeConn(fake_cur)

    with patch.object(cleanup, "_build_dsn", return_value="postgresql://fake"):
        fake_psycopg2 = MagicMock()
        fake_psycopg2.connect.return_value = fake_conn
        with patch.dict("sys.modules", {"psycopg2": fake_psycopg2}):
            rc = cleanup.main()

    assert rc == 0, f"expected exit=0, got {rc}"
    # Expected executes: V042 probe, UPDATE...RETURNING, V035 probe, 3× INSERT.
    # 期望 execute 序列：V042 probe、UPDATE...RETURNING、V035 probe、3 個 INSERT。
    insert_count = sum(
        1 for sql, _ in fake_cur.executed
        if "insert into learning.governance_audit_log" in sql.lower()
    )
    assert insert_count == 3, (
        f"expected 3 audit row INSERTs, got {insert_count}; "
        f"executed sequence: {[s for s, _ in fake_cur.executed]}"
    )

    # Each INSERT params should carry env + fingerprint payload.
    # 每個 INSERT params 應帶 env + fingerprint payload。
    audit_inserts = [
        params for sql, params in fake_cur.executed
        if "insert into learning.governance_audit_log" in sql.lower()
    ]
    seen_envs: set[str] = set()
    seen_fps: set[str] = set()
    for params in audit_inserts:
        # params is (event_type, decided_by, json_str)
        # params 為 (event_type, decided_by, json_str)
        assert isinstance(params, tuple) and len(params) == 3, params
        event_type, decided_by, payload_json = params
        assert event_type == "audit_write_failed"
        assert decided_by == "replay_key_archive_cleanup_cron"
        # payload is a JSON string; parse and assert.
        # payload 為 JSON 字串；parse + assert。
        import json
        payload = json.loads(payload_json)
        assert payload["alert_type"] == "replay_key_archive_expired"
        assert payload["env"] in {"paper", "demo", "live"}
        seen_envs.add(payload["env"])
        seen_fps.add(payload["fingerprint"])
    assert seen_envs == {"paper", "demo", "live"}
    assert seen_fps == {"abc1234567890def", "fedcba9876543210", "0011223344556677"}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
