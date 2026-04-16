"""
Shadow-fill consumer route tests (EDGE-P3-1 Step 7c).
Shadow-fill 消費者路由測試（EDGE-P3-1 Step 7c）。

MODULE_NOTE (EN): Covers the three read endpoints:
  * list         — filters + pagination echoes + fail-closed empty rows
  * summary      — per-strategy aggregate + zero-row fallback
  * promotion_gate — sample-count-tier verdict mapping
Uses a fake DB connection so tests are hermetic — no real PG required.

MODULE_NOTE (中): 三條路由（list / summary / promotion_gate）的煙霧 +
  邊界測試。以 fake DB 取代真實 PG，保持測試封閉。
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import pytest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import shadow_fills_routes as sf_module  # noqa: E402
from app.main_legacy import AuthenticatedActor, current_actor  # noqa: E402
from app.shadow_fills_routes import (  # noqa: E402
    _ALLOWED_STRATEGIES,
    _PROMOTION_SHIP_PROD_MIN,
    _PROMOTION_SHIP_SHADOW_MIN,
    _promotion_verdict,
    shadow_fills_router,
)


def _viewer_actor() -> AuthenticatedActor:
    return AuthenticatedActor(
        actor_id="test-viewer",
        actor_type="human",
        roles={"viewer"},
        scopes={"private_readonly"},
    )


class _FakeCursor:
    """Minimal cursor stand-in supporting execute/fetchall/fetchone/description."""

    def __init__(self, rows: list[tuple[Any, ...]], columns: list[str]) -> None:
        self._rows = rows
        self._columns = columns
        self.description = [type("Col", (), {"name": c})() for c in columns]

    def execute(self, sql: str, args: tuple[Any, ...] | None = None) -> None:
        self.last_sql = sql
        self.last_args = args

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._rows[0] if self._rows else None


class _FakeConn:
    def __init__(self, rows: list[tuple[Any, ...]], columns: list[str]) -> None:
        self._cur = _FakeCursor(rows, columns)

    def cursor(self) -> _FakeCursor:
        return self._cur


@contextmanager
def _pg_returns(rows: list[tuple[Any, ...]], columns: list[str]):
    """Patch `get_pg_conn` to yield a fake connection with the given rowset."""

    @contextmanager
    def _fake() -> Any:
        yield _FakeConn(rows, columns)

    with patch.object(sf_module, "get_pg_conn", _fake):
        yield


@contextmanager
def _pg_unavailable():
    """Patch `get_pg_conn` to yield None (DB offline scenario)."""

    @contextmanager
    def _fake() -> Any:
        yield None

    with patch.object(sf_module, "get_pg_conn", _fake):
        yield


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(shadow_fills_router)
    app.dependency_overrides[current_actor] = _viewer_actor
    return TestClient(app)


# ─── _promotion_verdict unit tests ───────────────────────────────────────


def test_verdict_insufficient_samples_below_shadow_min() -> None:
    v, _ = _promotion_verdict(0, 0)
    assert v == "insufficient_samples"
    v, _ = _promotion_verdict(_PROMOTION_SHIP_SHADOW_MIN - 1, 0)
    assert v == "insufficient_samples"


def test_verdict_awaiting_synthetic_when_total_meets_threshold_but_synthetic_missing() -> None:
    v, _ = _promotion_verdict(_PROMOTION_SHIP_SHADOW_MIN, 0)
    assert v == "awaiting_synthetic_labels"


def test_verdict_ship_shadow_in_mid_tier() -> None:
    v, _ = _promotion_verdict(
        _PROMOTION_SHIP_SHADOW_MIN, _PROMOTION_SHIP_SHADOW_MIN
    )
    assert v == "ship_shadow_candidate"
    v, _ = _promotion_verdict(_PROMOTION_SHIP_PROD_MIN - 1, _PROMOTION_SHIP_SHADOW_MIN)
    assert v == "ship_shadow_candidate"


def test_verdict_ship_prod_when_both_thresholds_met() -> None:
    v, _ = _promotion_verdict(_PROMOTION_SHIP_PROD_MIN, _PROMOTION_SHIP_SHADOW_MIN)
    assert v == "ship_prod_candidate"
    v, _ = _promotion_verdict(10_000, 10_000)
    assert v == "ship_prod_candidate"


# ─── /api/v1/edge/shadow_fills (list) ────────────────────────────────────


def test_list_returns_200_when_pg_down(client: TestClient) -> None:
    with _pg_unavailable():
        resp = client.get("/api/v1/edge/shadow_fills")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["rows"] == []
    assert body["data"]["degraded"] is True
    assert body["data"]["reason"] == "pg_unavailable"


def test_list_rejects_non_whitelisted_engine(client: TestClient) -> None:
    resp = client.get("/api/v1/edge/shadow_fills", params={"engine": "demo"})
    assert resp.status_code == 400


def test_list_rejects_non_whitelisted_strategy(client: TestClient) -> None:
    resp = client.get(
        "/api/v1/edge/shadow_fills", params={"strategy": "not_a_strategy"}
    )
    assert resp.status_code == 400


def test_list_surfaces_rows_and_filters_echo(client: TestClient) -> None:
    import datetime as dt

    ts = dt.datetime(2026, 4, 16, 12, 0, 0, tzinfo=dt.timezone.utc)
    row = (
        1,  # shadow_id
        "ctx-abc",  # context_id
        ts,  # ts
        "paper",  # engine_mode
        "ma_crossover",  # strategy_name
        "BTCUSDT",  # symbol
        1,  # side
        -5.0,  # predicted_q10
        10.0,  # predicted_q50
        25.0,  # predicted_q90
        8.5,  # cost_bps_at_open
        None,  # synthetic_exit_price
        None,  # synthetic_hold_ms
        None,  # synthetic_net_edge_bps
        "shadow_fill:epsilon_greedy",
    )
    cols = [
        "shadow_id",
        "context_id",
        "ts",
        "engine_mode",
        "strategy_name",
        "symbol",
        "side",
        "predicted_q10",
        "predicted_q50",
        "predicted_q90",
        "cost_bps_at_open",
        "synthetic_exit_price",
        "synthetic_hold_ms",
        "synthetic_net_edge_bps",
        "close_tag",
    ]
    with _pg_returns([row], cols):
        resp = client.get(
            "/api/v1/edge/shadow_fills",
            params={"strategy": "ma_crossover", "limit": 10, "offset": 0},
        )
    assert resp.status_code == 200
    body = resp.json()
    data = body["data"]
    assert data["degraded"] is False
    assert data["filters"]["strategy"] == "ma_crossover"
    assert len(data["rows"]) == 1
    assert data["rows"][0]["context_id"] == "ctx-abc"
    assert data["rows"][0]["ts"].startswith("2026-04-16T12:00:00")


# ─── /api/v1/edge/shadow_fills/summary ───────────────────────────────────


def test_summary_zero_fallback_lists_every_allowed_strategy(
    client: TestClient,
) -> None:
    with _pg_returns([], []):
        resp = client.get("/api/v1/edge/shadow_fills/summary")
    assert resp.status_code == 200
    body = resp.json()
    by_strategy = body["data"]["by_strategy"]
    assert {r["strategy_name"] for r in by_strategy} == set(_ALLOWED_STRATEGIES)
    for r in by_strategy:
        assert r["n"] == 0
        assert r["n_with_synthetic"] == 0


def test_summary_surfaces_aggregate_rows(client: TestClient) -> None:
    import datetime as dt

    first = dt.datetime(2026, 4, 10, 0, 0, 0, tzinfo=dt.timezone.utc)
    last = dt.datetime(2026, 4, 16, 0, 0, 0, tzinfo=dt.timezone.utc)
    # (strategy, n, n_synth, q50_mean, cost_mean, synth_edge_mean, first_ts, last_ts)
    rows = [("ma_crossover", 120, 80, 7.2, 8.5, 3.1, first, last)]
    with _pg_returns(rows, ["stub"]):
        resp = client.get("/api/v1/edge/shadow_fills/summary")
    assert resp.status_code == 200
    by_strategy = {
        row["strategy_name"]: row for row in resp.json()["data"]["by_strategy"]
    }
    assert by_strategy["ma_crossover"]["n"] == 120
    assert by_strategy["ma_crossover"]["n_with_synthetic"] == 80
    # Strategies with no rows still appear with zeroed values.
    assert by_strategy["bb_reversion"]["n"] == 0


def test_summary_degrades_when_pg_down(client: TestClient) -> None:
    with _pg_unavailable():
        resp = client.get("/api/v1/edge/shadow_fills/summary")
    body = resp.json()
    assert body["data"]["degraded"] is True
    # Even on PG failure, zero-sample rows for each strategy are returned.
    assert len(body["data"]["by_strategy"]) == len(_ALLOWED_STRATEGIES)


# ─── /api/v1/edge/shadow_fills/promotion_gate/{strategy} ─────────────────


def test_gate_rejects_unknown_strategy(client: TestClient) -> None:
    resp = client.get("/api/v1/edge/shadow_fills/promotion_gate/unknown")
    assert resp.status_code == 400


def test_gate_insufficient_samples_on_empty_table(client: TestClient) -> None:
    # COUNT on empty table returns (0, 0, None, None)
    with _pg_returns([(0, 0, None, None)], ["n", "n_synth", "first_ts", "last_ts"]):
        resp = client.get("/api/v1/edge/shadow_fills/promotion_gate/ma_crossover")
    body = resp.json()["data"]
    assert body["sample_count"] == 0
    assert body["samples_with_synthetic"] == 0
    assert body["verdict"] == "insufficient_samples"
    assert body["thresholds"]["ship_prod_min"] == _PROMOTION_SHIP_PROD_MIN


def test_gate_ship_prod_candidate_when_thresholds_met(client: TestClient) -> None:
    import datetime as dt

    first = dt.datetime(2026, 4, 1, 0, 0, 0, tzinfo=dt.timezone.utc)
    last = dt.datetime(2026, 4, 16, 0, 0, 0, tzinfo=dt.timezone.utc)
    rows = [(600, 550, first, last)]
    with _pg_returns(rows, ["n", "n_synth", "first_ts", "last_ts"]):
        resp = client.get("/api/v1/edge/shadow_fills/promotion_gate/grid_trading")
    body = resp.json()["data"]
    assert body["verdict"] == "ship_prod_candidate"
    assert body["sample_count"] == 600
    assert body["samples_with_synthetic"] == 550


def test_gate_degrades_when_pg_down(client: TestClient) -> None:
    with _pg_unavailable():
        resp = client.get("/api/v1/edge/shadow_fills/promotion_gate/ma_crossover")
    # Gate still returns 200 with zero-count verdict when PG is down.
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["verdict"] == "insufficient_samples"
