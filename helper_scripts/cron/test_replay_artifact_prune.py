"""replay_artifact_prune.py — pytest fixtures + scenarios.
replay_artifact_prune.py — pytest 場景測試。

MODULE_NOTE (EN): REF-20 R20-P2a-S5 (Wave 3 Batch 3A). Pins three
  load-bearing behaviours of the prune cron via a hand-rolled in-memory
  fake cursor that simulates the V3 §4.1 replay schema:
    1. replay schema absent → graceful exit 0 (cron entry safe pre-schema).
    2. schema present + 0 expired manifests + under cap → 0 delete + 0 audit.
    3. schema present + 5 expired manifests → 5 DELETE + 1 audit row.
  Avoids spinning up real PostgreSQL; tests must be runnable on the Mac
  dev path where psycopg2 is installed but no PG instance exists.

MODULE_NOTE (中): REF-20 R20-P2a-S5（Wave 3 Batch 3A）。用手寫
  in-memory fake cursor 釘死 prune cron 三條 load-bearing 行為，模擬 V3
  §4.1 replay schema：
    1. replay schema 缺 → graceful exit 0（schema land 前 cron 條目可安裝）。
    2. schema 在 + 0 過期 manifest + 未超 cap → 0 delete + 0 audit。
    3. schema 在 + 5 過期 manifest → 5 DELETE + 1 audit row。
  不需要真 PostgreSQL；Mac dev 路徑（psycopg2 裝了但無 PG instance）
  能跑。

Tests / 測試覆蓋:
  1. test_replay_schema_absent_exits_0_graceful
  2. test_zero_manifests_expired_zero_prune
  3. test_five_manifests_expired_pruned_correctly
"""
from __future__ import annotations

import sys
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

import replay_artifact_prune as prune  # noqa: E402


# ─── Fake cursor / 假 cursor ─────────────────────────────────────────


class _FakeCursor:
    """Minimal psycopg2-compatible cursor for prune cron unit tests.
    Prune cron 單元測試最小 psycopg2-相容 cursor。

    Tracks executed SQL + params for assertions; returns canned `fetchone()`
    / `fetchall()` based on a small in-memory script the test seeds upfront.

    記錄已 execute 的 SQL + params 供 assert；依測試預設的 in-memory
    script 回 fetchone/fetchall 結果。
    """

    def __init__(
        self,
        experiments_present: bool,
        artifacts_present: bool,
        v035_present: bool,
        ttl_pruned_rows: list[tuple[str, str, int]] | None = None,
        storage_used_per_env: dict[str, int] | None = None,
    ) -> None:
        self.experiments_present = experiments_present
        self.artifacts_present = artifacts_present
        self.v035_present = v035_present
        self.ttl_pruned_rows = ttl_pruned_rows or []
        self.storage_used_per_env = storage_used_per_env or {}
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

        # information_schema probe (experiments / report_artifacts / governance_audit_log)
        # information_schema probe（experiments / report_artifacts / governance_audit_log）
        if "information_schema.tables" in sql_lower:
            if params and "experiments" in params:
                self._next_fetchone = (1,) if self.experiments_present else None
            elif params and "report_artifacts" in params:
                self._next_fetchone = (1,) if self.artifacts_present else None
            elif params and "governance_audit_log" in params:
                self._next_fetchone = (1,) if self.v035_present else None
            else:
                self._next_fetchone = None
            self._next_fetchall = None
            return

        # DELETE FROM replay.report_artifacts ... USING replay.experiments
        # (TTL prune flow) → returns ttl_pruned_rows.
        # DELETE FROM replay.report_artifacts ... USING replay.experiments
        # （TTL prune 流程）→ 回 ttl_pruned_rows。
        if (
            "delete from replay.report_artifacts ra" in sql_lower
            and "using replay.experiments" in sql_lower
            and "expires_at < now()" in sql_lower
        ):
            self._next_fetchall = list(self.ttl_pruned_rows)
            self._next_fetchone = None
            return

        # SUM(bytes) for storage cap probe.
        # SUM(bytes) for storage cap probe。
        if (
            "select coalesce(sum(ra.bytes), 0)" in sql_lower
            or "select coalesce(sum(ra.bytes),0)" in sql_lower
        ):
            env_str = params[0] if params else ""
            used = self.storage_used_per_env.get(env_str, 0)
            self._next_fetchone = (used,)
            return

        # SELECT oldest live artifact — under-cap test: returns None to
        # short-circuit the loop. Over-cap test would seed candidates.
        # SELECT 最舊 live artifact — under-cap 測試：回 None 提前退出。
        # Over-cap 測試會 seed candidate。
        if (
            "select ra.artifact_id" in sql_lower
            and "order by ra.created_at asc" in sql_lower
        ):
            self._next_fetchone = None
            self._next_fetchall = None
            return

        # DELETE single artifact by id (storage cap path).
        # DELETE 單個 artifact by id（storage cap 路徑）。
        if "delete from replay.report_artifacts where artifact_id" in sql_lower:
            self._next_fetchone = None
            self._next_fetchall = None
            return

        # INSERT INTO learning.governance_audit_log — no-op for cursor.
        # INSERT 至 governance_audit_log — cursor 無動作。
        if "insert into learning.governance_audit_log" in sql_lower:
            self._next_fetchone = None
            self._next_fetchall = None
            return

        # Default: nothing to fetch. / 預設：無 fetch。
        self._next_fetchone = None
        self._next_fetchall = None

    def fetchone(self) -> Any:
        return self._next_fetchone

    def fetchall(self) -> list[Any]:
        if self._next_fetchall is None:
            return []
        return self._next_fetchall


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
        # psycopg2 conn-context auto-commits on no exception.
        # psycopg2 conn-context 無 exception 自動 commit。
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
    """Set OPENCLAW_DATABASE_URL so _build_dsn() returns a non-None DSN.
    設 OPENCLAW_DATABASE_URL 讓 _build_dsn() 回非 None DSN。

    DSN value is irrelevant — we mock psycopg2.connect, but the script
    requires the env var to be present to reach the connection step.
    """
    monkeypatch.setenv(
        "OPENCLAW_DATABASE_URL",
        "postgresql://fake:fake@127.0.0.1:5432/fake",
    )
    # Clear storage cap override so prune uses default 1024 MB.
    # 清 storage cap override，prune 用預設 1024 MB。
    monkeypatch.delenv(
        "OPENCLAW_REPLAY_ARTIFACT_STORAGE_CAP_MB", raising=False
    )


# ─── Tests / 測試 ────────────────────────────────────────────────────


def test_replay_schema_absent_exits_0_graceful(env_with_dsn: None) -> None:
    """V042 / replay schema absent → graceful exit 0 + log message.
    V042 / replay schema 缺 → graceful exit 0 + log 訊息。
    """
    fake_cur = _FakeCursor(
        experiments_present=False,
        artifacts_present=False,
        v035_present=True,
    )
    fake_conn = _FakeConn(fake_cur)

    fake_psycopg2 = MagicMock()
    fake_psycopg2.connect.return_value = fake_conn
    with patch.dict("sys.modules", {"psycopg2": fake_psycopg2}):
        rc = prune.main()

    assert rc == 0, f"expected exit=0 graceful, got {rc}"
    # First (and only) execute should be the experiments info_schema probe.
    # 第一條（也是唯一一條）execute 應是 experiments info_schema probe。
    assert len(fake_cur.executed) == 1, (
        f"expected exactly 1 execute (schema probe), got "
        f"{len(fake_cur.executed)}: {fake_cur.executed!r}"
    )
    sql, params = fake_cur.executed[0]
    assert "information_schema.tables" in sql.lower()
    assert params == ("replay", "experiments")


def test_zero_manifests_expired_zero_prune(env_with_dsn: None) -> None:
    """Schema present + 0 expired manifest + storage under cap → 0 delete + 0 audit.
    Schema 在 + 0 過期 manifest + storage 未超 cap → 0 delete + 0 audit。
    """
    fake_cur = _FakeCursor(
        experiments_present=True,
        artifacts_present=True,
        v035_present=True,
        ttl_pruned_rows=[],  # 0 rows past TTL
        storage_used_per_env={
            "linux_trade_core": 100 * 1024 * 1024,  # 100 MB << 1024 MB cap
            "mac_dev_smoke_test_only": 10 * 1024 * 1024,  # 10 MB
        },
    )
    fake_conn = _FakeConn(fake_cur)

    fake_psycopg2 = MagicMock()
    fake_psycopg2.connect.return_value = fake_conn
    with patch.dict("sys.modules", {"psycopg2": fake_psycopg2}):
        rc = prune.main()

    assert rc == 0, f"expected exit=0, got {rc}"
    # Expected execute pattern: 2× info_schema probe (experiments + artifacts)
    # + 1× DELETE TTL prune + 1× v035 probe (skipped since 0 pruned) + N×
    # SUM probe per env. NO INSERTs to governance_audit_log because nothing
    # pruned.
    # 期望 execute 序列：2 個 info_schema probe（experiments + artifacts）
    # + 1 個 DELETE TTL prune + 1 個 v035 probe（0 prune 時跳）+ N 個
    # SUM probe per env。**無** governance_audit_log INSERT（無 prune）。
    inserts = [
        sql for sql, _ in fake_cur.executed
        if "insert into learning.governance_audit_log" in sql.lower()
    ]
    assert len(inserts) == 0, f"unexpected INSERT(s): {inserts}"

    # No DELETE single-artifact (storage-cap path) since under cap.
    # 無 DELETE single-artifact（storage-cap path）— 因 under cap。
    single_deletes = [
        sql for sql, _ in fake_cur.executed
        if "delete from replay.report_artifacts where artifact_id" in sql.lower()
    ]
    assert len(single_deletes) == 0, f"unexpected single-DELETE(s): {single_deletes}"


def test_five_manifests_expired_pruned_correctly(
    env_with_dsn: None,
) -> None:
    """Schema present + 5 expired manifest artifacts → 5 DELETE + 1 audit row.
    Schema 在 + 5 過期 manifest artifact → 5 DELETE + 1 audit row。
    """
    # Seed 5 rows that come back from the DELETE...RETURNING.
    # Seed 5 個 row 從 DELETE...RETURNING 回。
    ttl_rows: list[tuple[str, str, int]] = [
        ("exp-001", "art-001", 50 * 1024 * 1024),  # 50 MB
        ("exp-001", "art-002", 30 * 1024 * 1024),  # 30 MB
        ("exp-002", "art-003", 20 * 1024 * 1024),  # 20 MB
        ("exp-003", "art-004", 100 * 1024 * 1024),  # 100 MB
        ("exp-004", "art-005", 5 * 1024 * 1024),  # 5 MB
    ]
    fake_cur = _FakeCursor(
        experiments_present=True,
        artifacts_present=True,
        v035_present=True,
        ttl_pruned_rows=ttl_rows,
        storage_used_per_env={
            "linux_trade_core": 100 * 1024 * 1024,  # 100 MB << cap
            "mac_dev_smoke_test_only": 10 * 1024 * 1024,
        },
    )
    fake_conn = _FakeConn(fake_cur)

    fake_psycopg2 = MagicMock()
    fake_psycopg2.connect.return_value = fake_conn
    with patch.dict("sys.modules", {"psycopg2": fake_psycopg2}):
        rc = prune.main()

    assert rc == 0, f"expected exit=0, got {rc}"

    # Expect exactly one INSERT INTO governance_audit_log for TTL prune
    # (since 5 rows pruned in single batch).
    # 期望 1 個 INSERT 至 governance_audit_log（5 row 一個 batch）。
    audit_inserts = [
        (sql, params) for sql, params in fake_cur.executed
        if "insert into learning.governance_audit_log" in sql.lower()
    ]
    assert len(audit_inserts) == 1, (
        f"expected 1 audit row INSERT (TTL batch), got {len(audit_inserts)}"
    )

    # Inspect payload: alert_type='replay_artifact_prune_ttl' + count=5 +
    # bytes_total = sum.
    # 檢查 payload：alert_type='replay_artifact_prune_ttl' + count=5 +
    # bytes_total = sum。
    insert_sql, insert_params = audit_inserts[0]
    assert isinstance(insert_params, tuple) and len(insert_params) == 3
    event_type, decided_by, payload_json = insert_params
    assert event_type == "audit_write_failed"
    assert decided_by == "replay_artifact_prune_cron"

    import json

    payload = json.loads(payload_json)
    assert payload["alert_type"] == "replay_artifact_prune_ttl"
    assert payload["pruned_count"] == 5
    expected_bytes = sum(b for _, _, b in ttl_rows)
    assert payload["pruned_bytes_total"] == expected_bytes
    # sample_pairs 應含前 10 個 (但只有 5 個 → 全列)。
    # sample_pairs should contain first 10 (only 5 here → all listed).
    assert len(payload["sample_pairs"]) == 5
    sample_eids = {p["experiment_id"] for p in payload["sample_pairs"]}
    sample_aids = {p["artifact_id"] for p in payload["sample_pairs"]}
    assert sample_eids == {"exp-001", "exp-002", "exp-003", "exp-004"}
    assert sample_aids == {f"art-00{i}" for i in range(1, 6)}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
