"""wave9_business_kpi_collector — pytest fixtures + scenarios.

wave9_business_kpi_collector — pytest 場景測試。

MODULE_NOTE (EN): REF-20 Wave 9 R20-W9-T2. Pins four load-bearing
  behaviours of the business KPI collector cron via a hand-rolled
  in-memory fake cursor that simulates V045/V044/V035 schema:

    1. V047 absent → graceful exit 0 (cron entry safe pre-V047).
    2. mock mode (OPENCLAW_WAVE9_KPI_MOCK=1) → /tmp/wave9_kpi_test_only/
       JSONL write + 0 DB connection.
    3. all schemas present + 0 rows in any table → skeleton snapshots
       (kpi_value=NULL or 0; sample_size=0).
    4. handoff_success_rate sampler with mixed result rows → correct
       success / total rate.

  Avoids spinning up real PostgreSQL; mirrors sibling cron test pattern
  (test_replay_artifact_prune.py).

MODULE_NOTE (中): REF-20 Wave 9 R20-W9-T2。用手寫 in-memory fake cursor
  釘死 KPI collector cron 4 條 load-bearing 行為，模擬 V045/V044/V035
  schema：

    1. V047 缺 → graceful exit 0（V047 land 前 cron 條目可安裝）。
    2. mock 模式 (OPENCLAW_WAVE9_KPI_MOCK=1) → /tmp/wave9_kpi_test_only/
       JSONL 寫 + 0 DB 連線。
    3. 全 schema 在 + 全 0 row → 骨架 snapshot（kpi_value=NULL 或 0；
       sample_size=0）。
    4. handoff_success_rate sampler 混合 result row → 正確 success/total rate。

  不需真 PostgreSQL；對齊 sibling cron 測試模式（test_replay_artifact_prune.py）。

Tests / 測試覆蓋:
  1. test_v047_absent_returns_graceful_exit_0
  2. test_mock_mode_writes_jsonl_to_tmp
  3. test_all_schemas_present_zero_rows_writes_skeleton
  4. test_handoff_success_rate_sampler_correct
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# Ensure cron directory on sys.path.
# 確保 cron 目錄在 sys.path。
_CRON_DIR = Path(__file__).resolve().parent
if str(_CRON_DIR) not in sys.path:
    sys.path.insert(0, str(_CRON_DIR))

import wave9_business_kpi_collector as collector  # noqa: E402


# ─── Fake cursor / 假 cursor ─────────────────────────────────────────


class _FakeCursor:
    """Minimal psycopg2-compatible cursor for KPI collector tests.

    KPI collector 測試最小 psycopg2-相容 cursor。

    Tracks executed SQL + params; returns canned `fetchone()` based on
    presence flags + per-table response data.

    記錄 execute 之 SQL + params；依配置回 fetchone 結果。
    """

    def __init__(
        self,
        v047_present: bool = True,
        run_state_present: bool = True,
        handoff_requests_present: bool = True,
        gov_audit_present: bool = True,
        run_state_count: int = 0,
        handoff_success_count: int = 0,
        handoff_total_count: int = 0,
        fail_mode_counts: dict[str, int] | None = None,
        cap_hits: int = 0,
        total_prunes: int = 0,
        cost_p50: float | None = None,
        cost_n: int = 0,
        gate_fires: int = 0,
        total_reviews: int = 0,
    ) -> None:
        self.v047_present = v047_present
        self.run_state_present = run_state_present
        self.handoff_requests_present = handoff_requests_present
        self.gov_audit_present = gov_audit_present
        self.run_state_count = run_state_count
        self.handoff_success_count = handoff_success_count
        self.handoff_total_count = handoff_total_count
        self.fail_mode_counts = fail_mode_counts or {}
        self.cap_hits = cap_hits
        self.total_prunes = total_prunes
        self.cost_p50 = cost_p50
        self.cost_n = cost_n
        self.gate_fires = gate_fires
        self.total_reviews = total_reviews
        self.executed: list[tuple[str, Any]] = []
        self._next_fetchone: Any = None
        # Track INSERT/UPSERT row count for assertions.
        # 追蹤 INSERT/UPSERT row count 供 assert。
        self.upserted_count = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql: str, params: Any = None) -> None:
        self.executed.append((sql, params))
        sql_lower = sql.lower()

        # information_schema probe.
        # information_schema probe。
        if "information_schema.tables" in sql_lower and params:
            schema, table = params[0], params[1]
            if schema == "replay" and table == "business_kpi_snapshots":
                self._next_fetchone = (1,) if self.v047_present else None
            elif schema == "replay" and table == "run_state":
                self._next_fetchone = (1,) if self.run_state_present else None
            elif schema == "replay" and table == "handoff_requests":
                self._next_fetchone = (
                    (1,) if self.handoff_requests_present else None
                )
            elif schema == "learning" and table == "governance_audit_log":
                self._next_fetchone = (
                    (1,) if self.gov_audit_present else None
                )
            else:
                self._next_fetchone = None
            return

        # SELECT COUNT(*) FROM replay.run_state.
        # SELECT COUNT(*) FROM replay.run_state。
        if (
            "select count(*) from replay.run_state" in sql_lower
        ):
            self._next_fetchone = (self.run_state_count,)
            return

        # handoff_success FILTER query.
        # handoff_success FILTER 查詢。
        if (
            "from replay.handoff_requests" in sql_lower
            and "filter" in sql_lower
        ):
            self._next_fetchone = (
                self.handoff_success_count,
                self.handoff_total_count,
            )
            return

        # Manifest fail mode count (single fm).
        # Manifest fail mode count（單 fm）。
        if (
            "from learning.governance_audit_log" in sql_lower
            and "alert_type" in sql_lower
            and params
            and len(params) == 2
            and params[1] in (
                "signature_invalid",
                "manifest_expired",
                "key_retired",
                "key_expired",
            )
        ):
            self._next_fetchone = (
                self.fail_mode_counts.get(params[1], 0),
            )
            return

        # quota_cap_hit_rate query.
        # quota_cap_hit_rate 查詢。
        if (
            "replay_artifact_prune_storage_cap" in sql_lower
            or "replay_artifact_prune%" in sql_lower
        ):
            self._next_fetchone = (self.cap_hits, self.total_prunes)
            return

        # cost_edge_ratio_p50 query (percentile_cont).
        # cost_edge_ratio_p50 查詢（percentile_cont）。
        if "percentile_cont" in sql_lower:
            self._next_fetchone = (self.cost_p50, self.cost_n)
            return

        # dsr_pbo_gate_fire_rate query.
        # dsr_pbo_gate_fire_rate 查詢。
        if (
            "rule_failures" in sql_lower
            and "review_live_candidate" in sql_lower
        ):
            self._next_fetchone = (self.gate_fires, self.total_reviews)
            return

        # INSERT INTO business_kpi_snapshots.
        if "insert into replay.business_kpi_snapshots" in sql_lower:
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
    """Set OPENCLAW_DATABASE_URL so _build_dsn() returns a non-None DSN.
    設 OPENCLAW_DATABASE_URL 讓 _build_dsn() 回非 None DSN。
    """
    monkeypatch.setenv(
        "OPENCLAW_DATABASE_URL",
        "postgresql://fake:fake@127.0.0.1:5432/fake",
    )
    monkeypatch.delenv("OPENCLAW_WAVE9_KPI_MOCK", raising=False)


@pytest.fixture
def env_mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Activate Mac-dev mock mode.
    啟用 Mac-dev mock 模式。
    """
    monkeypatch.setenv("OPENCLAW_WAVE9_KPI_MOCK", "1")
    monkeypatch.delenv("OPENCLAW_DATABASE_URL", raising=False)


# ─── Tests / 測試 ────────────────────────────────────────────────────


def test_v047_absent_returns_graceful_exit_0(env_with_dsn: None) -> None:
    """V047 absent → graceful exit 0; no INSERT executed.
    V047 缺 → graceful exit 0；無 INSERT 執行。
    """
    fake_cur = _FakeCursor(v047_present=False)
    fake_conn = _FakeConn(fake_cur)
    fake_psycopg2 = MagicMock()
    fake_psycopg2.connect.return_value = fake_conn
    with patch.dict("sys.modules", {"psycopg2": fake_psycopg2}):
        rc = collector.main()

    assert rc == 0, f"expected exit=0 graceful, got {rc}"
    # First execute should be the V047 probe; no INSERTs.
    # 第一條 execute 是 V047 probe；無 INSERT。
    inserts = [
        sql for sql, _ in fake_cur.executed
        if "insert into" in sql.lower()
    ]
    assert len(inserts) == 0, f"unexpected INSERT(s): {inserts}"


def test_mock_mode_writes_jsonl_to_tmp(
    env_mock_mode: None, tmp_path: Path
) -> None:
    """Mock mode → /tmp/wave9_kpi_test_only/snapshot.jsonl created; 0 DB connect.
    Mock 模式 → /tmp/wave9_kpi_test_only/snapshot.jsonl 寫；0 DB 連線。
    """
    # Stub out psycopg2 to ensure mock mode never tries to connect.
    # Stub psycopg2 確保 mock 模式不嘗試連線。
    fake_psycopg2 = MagicMock()
    # If anything calls connect(), test will fail because we assert not called.
    # 若呼叫 connect()，assert 會失敗。
    with patch.dict("sys.modules", {"psycopg2": fake_psycopg2}):
        rc = collector.main()

    assert rc == 0
    # Verify psycopg2.connect not called.
    # 驗證 psycopg2.connect 未呼叫。
    fake_psycopg2.connect.assert_not_called()

    out_path = Path("/tmp/wave9_kpi_test_only/snapshot.jsonl")
    assert out_path.exists(), f"mock JSONL not written at {out_path}"

    # Validate JSONL structure: each line is JSON with required keys.
    # 驗證 JSONL 結構：每行 JSON 含必要 key。
    lines = out_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) > 0, "mock JSONL is empty"

    expected_keys = {
        "snapshot_date",
        "window_type",
        "kpi_name",
        "kpi_value",
        "sample_size",
        "extra",
        "mock",
    }
    for line in lines:
        row = json.loads(line)
        assert expected_keys.issubset(row.keys()), (
            f"missing keys in mock row: {row.keys()}"
        )
        assert row["mock"] is True
        assert row["window_type"] in ("7d", "14d")
        # In mock mode, all samplers see absent tables → kpi_value None.
        # Mock 模式下 sampler 看到表缺 → kpi_value None。

    # Cleanup test artifact.
    # 清除測試產物。
    out_path.unlink(missing_ok=True)


def test_all_schemas_present_zero_rows_writes_skeleton(
    env_with_dsn: None,
) -> None:
    """All tables present + 0 rows → skeleton snapshots upserted (UPSERT).
    全表在 + 0 row → 骨架 snapshot 寫入。
    """
    fake_cur = _FakeCursor(
        v047_present=True,
        run_state_present=True,
        handoff_requests_present=True,
        gov_audit_present=True,
        # All counts 0 / 全 count 0.
        run_state_count=0,
        handoff_success_count=0,
        handoff_total_count=0,
        fail_mode_counts={},
        cap_hits=0,
        total_prunes=0,
        cost_p50=None,
        cost_n=0,
        gate_fires=0,
        total_reviews=0,
    )
    fake_conn = _FakeConn(fake_cur)
    fake_psycopg2 = MagicMock()
    fake_psycopg2.connect.return_value = fake_conn
    with patch.dict("sys.modules", {"psycopg2": fake_psycopg2}):
        rc = collector.main()

    assert rc == 0
    # Expected upsert count = 6 KPIs × 2 windows = 12 rows.
    # 期望 upsert count = 6 KPI × 2 窗口 = 12 row。
    assert fake_cur.upserted_count == 12, (
        f"expected 12 upserts (6 KPIs × 2 windows), got {fake_cur.upserted_count}"
    )


def test_handoff_success_rate_sampler_correct() -> None:
    """handoff_success_rate sampler with seed data → correct ratio.
    handoff_success_rate sampler 配 seed 資料 → 正確 ratio。
    """
    # Seed: 7d window has 3 success / 5 total = 0.6.
    # Seed：7d 窗口 3 success / 5 total = 0.6。
    fake_cur = _FakeCursor(
        v047_present=True,
        handoff_requests_present=True,
        handoff_success_count=3,
        handoff_total_count=5,
    )

    rate, total, extra = collector._sample_handoff_success_rate(
        fake_cur, window_days=7
    )

    assert rate == 0.6
    assert total == 5
    assert extra == {"success_count": 3, "total_count": 5}

    # Edge case: 0 total → rate=None.
    # Edge case：0 total → rate=None。
    fake_cur2 = _FakeCursor(
        v047_present=True,
        handoff_requests_present=True,
        handoff_success_count=0,
        handoff_total_count=0,
    )
    rate2, total2, extra2 = collector._sample_handoff_success_rate(
        fake_cur2, window_days=14
    )
    assert rate2 is None
    assert total2 == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
