from __future__ import annotations

import math
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SRV_ROOT = Path(__file__).resolve().parents[3]
if str(SRV_ROOT) not in sys.path:
    sys.path.insert(0, str(SRV_ROOT))

from helper_scripts.m4.stage1_production_runner import (  # noqa: E402
    GovernanceHubDecisionLeaseProvider,
    generate_stage1_candidates,
    map_analysis_lane_to_pg_status,
    run_production_stage1,
)


class FakeCursor:
    def __init__(self, conn: "FakeConnection") -> None:
        self.conn = conn
        self.rows = []
        self.fetchone_row = None
        self.description = None

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params: dict) -> None:
        self.conn.executed.append((sql, params))
        if "INSERT INTO learning.hypotheses" in sql:
            self.conn.inserted_params.append(dict(params))
            self.fetchone_row = {"hypothesis_id": 9000 + len(self.conn.inserted_params)}
            return
        if "FROM market.klines" in sql:
            self.rows = list(self.conn.source_rows["klines"])
            return
        if "FROM trading.fills" in sql:
            self.rows = list(self.conn.source_rows["fills"])
            return
        if "FROM market.liquidations" in sql:
            self.rows = list(self.conn.source_rows["liquidations"])
            return
        if "FROM market.funding_rates" in sql:
            self.rows = list(self.conn.source_rows["funding"])
            return
        raise AssertionError(f"unexpected SQL: {sql[:80]}")

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.fetchone_row


class FakeConnection:
    def __init__(self, source_rows: dict[str, list[dict]]) -> None:
        self.source_rows = source_rows
        self.executed = []
        self.inserted_params = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class FakeGovernanceBridge:
    def __init__(self, lease_ids: list[str]) -> None:
        self.lease_ids = lease_ids
        self.acquire_calls: list[dict] = []
        self.release_calls: list[dict] = []

    def acquire(self, **kwargs):
        self.acquire_calls.append(dict(kwargs))
        if not self.lease_ids:
            return None
        return self.lease_ids.pop(0)

    def release(self, **kwargs):
        self.release_calls.append(dict(kwargs))
        return True


def _kline_rows(n: int = 160) -> list[dict]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for i in range(n):
        price = 100.0 + math.sin(i / 5.0) * 2.0 + i * 0.03
        rows.append(
            {
                "symbol": "BTCUSDT",
                "timeframe": "1m",
                "ts": start + timedelta(minutes=i),
                "open": price,
                "high": price + 0.5,
                "low": price - 0.5,
                "close": price,
                "volume": 10.0,
                "turnover": 1000.0,
            }
        )
    return rows


def _source_rows() -> dict[str, list[dict]]:
    return {
        "klines": _kline_rows(),
        "fills": [],
        "liquidations": [],
        "funding": [],
    }


def test_map_analysis_lane_to_v100_pg_status():
    assert map_analysis_lane_to_pg_status("preregistered") == "preregistered"
    assert map_analysis_lane_to_pg_status("exploratory") == "draft"
    with pytest.raises(ValueError):
        map_analysis_lane_to_pg_status("live")


def test_generate_candidates_never_emits_exploratory_pg_status():
    candidates = generate_stage1_candidates(
        kline_rows=_kline_rows(),
        funding_rows=[],
        liquidation_rows=[],
    )
    assert candidates
    assert all(candidate.pg_status in {"draft", "preregistered"} for candidate in candidates)
    assert "exploratory" not in {candidate.pg_status for candidate in candidates}


def test_non_dry_run_without_writeback_does_not_insert():
    conn = FakeConnection(_source_rows())
    summary = run_production_stage1(
        conn=conn,
        symbols=("BTCUSDT",),
        lookback_days=30,
        max_drafts=1,
        enable_writeback=False,
    )
    assert summary["dry_run"] is False
    assert summary["n_candidates"] > 0
    assert summary["n_drafts"] == 0
    assert conn.inserted_params == []
    assert conn.commits == 0


def test_writeback_requires_real_lease_uuid_before_insert():
    conn = FakeConnection(_source_rows())
    with pytest.raises(RuntimeError, match="one real decision lease UUID"):
        run_production_stage1(
            conn=conn,
            symbols=("BTCUSDT",),
            lookback_days=30,
            max_drafts=1,
            enable_writeback=True,
            decision_lease_draft_ids=(),
        )
    assert conn.inserted_params == []


def test_writeback_inserts_pg_safe_status_with_lease():
    lease_id = uuid.uuid4()
    conn = FakeConnection(_source_rows())
    summary = run_production_stage1(
        conn=conn,
        symbols=("BTCUSDT",),
        lookback_days=30,
        max_drafts=1,
        enable_writeback=True,
        decision_lease_draft_ids=(lease_id,),
    )
    assert summary["n_drafts"] == 1
    assert conn.commits == 1
    assert len(conn.inserted_params) == 1
    params = conn.inserted_params[0]
    assert params["status"] in {"draft", "preregistered"}
    assert params["status"] != "exploratory"
    assert params["decision_lease_draft_id"] == str(lease_id)


def test_writeback_can_acquire_uuid_lease_through_governance_provider():
    lease_id = uuid.uuid4()
    bridge = FakeGovernanceBridge([str(lease_id)])
    provider = GovernanceHubDecisionLeaseProvider(
        acquire_func=bridge.acquire,
        release_func=bridge.release,
    )
    conn = FakeConnection(_source_rows())
    summary = run_production_stage1(
        conn=conn,
        symbols=("BTCUSDT",),
        lookback_days=30,
        max_drafts=1,
        enable_writeback=True,
        lease_provider=provider,
    )

    assert summary["n_drafts"] == 1
    assert conn.commits == 1
    assert conn.inserted_params[0]["decision_lease_draft_id"] == str(lease_id)
    assert bridge.acquire_calls[0]["scope"] == "M4_DRAFT_WRITEBACK"
    assert bridge.acquire_calls[0]["profile"] == "Production"
    assert bridge.release_calls == [
        {"lease_id": str(lease_id), "consumed": True, "timeout_seconds": 5.0}
    ]


def test_governance_provider_releases_non_uuid_lease_and_refuses_insert():
    bridge = FakeGovernanceBridge(["lease:abc123def456"])
    provider = GovernanceHubDecisionLeaseProvider(
        acquire_func=bridge.acquire,
        release_func=bridge.release,
    )
    conn = FakeConnection(_source_rows())

    with pytest.raises(RuntimeError, match="UUID-compatible"):
        run_production_stage1(
            conn=conn,
            symbols=("BTCUSDT",),
            lookback_days=30,
            max_drafts=1,
            enable_writeback=True,
            lease_provider=provider,
        )

    assert conn.inserted_params == []
    assert conn.commits == 0
    assert conn.rollbacks == 1
    assert bridge.release_calls == [
        {
            "lease_id": "lease:abc123def456",
            "consumed": False,
            "timeout_seconds": 5.0,
        }
    ]
