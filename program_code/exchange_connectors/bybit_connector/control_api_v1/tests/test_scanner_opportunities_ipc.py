"""Unit tests for /api/v1/strategy/scanner/opportunities — IPC-SCAN-1c rewire.

Calls the async route handler directly (bypassing FastAPI) to stay isolated from
`importlib.reload(main_legacy)` in sibling test modules (which would invalidate a
`dependency_overrides[current_actor]` key and yield spurious 401s).

直接呼叫 async route handler（不走 FastAPI），避免姊妹測試 reload main_legacy
後讓 dependency_overrides 的 current_actor 失效而吐 401。

Covers: IPC ok mapping, uninitialized scanner, null last_scan, IPC exception,
malformed candidates, missing edge fields, bad edge numerics, empty candidate list.
"""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Any
from unittest.mock import patch

import pytest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app.strategy_read_routes import get_scanner_opportunities  # noqa: E402
from app.rust_scanner_reader import enrich_scanner_status_with_db  # noqa: E402


class _FakeActor:
    role = "viewer"
    username = "test"


@pytest.fixture(autouse=True)
def _disable_route_db_enrichment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep route tests hermetic; enrichment itself has a direct unit below."""
    monkeypatch.setattr(
        "app.strategy_read_routes.enrich_scanner_status_with_db",
        lambda status: status,
    )


def _run(coro):
    # Py 3.12：asyncio.get_event_loop() 在無 current loop 時 raise RuntimeError。
    # 前序 test 可能關閉 loop，故每 call 自管 new loop + close，不污染 global state。
    # Py 3.12: asyncio.get_event_loop() raises when no current loop exists.
    # Earlier tests may close the loop, so we manage a fresh loop per call with
    # proper cleanup to avoid polluting global state.
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _fake_ipc_class(call_result: dict | Exception):
    """Build a fake EngineIPCClient class patched into `app.ipc_client`.
    構造假 EngineIPCClient 類別，替換掉 app.ipc_client 的同名類。"""

    class _FakeClient:
        async def connect(self) -> None:
            pass

        async def call(self, method: str, params: dict, timeout: float) -> dict:
            assert method == "get_scanner_status"
            if isinstance(call_result, Exception):
                raise call_result
            return call_result

        async def disconnect(self) -> None:
            pass

    return _FakeClient


# ─── Happy path / 正常路徑 ───────────────────────────────────────────────


def test_opportunities_maps_rust_candidates_to_gui_fields() -> None:
    rust_response = {
        "status": "ok",
        "active_symbols": ["BTCUSDT", "ETHUSDT"],
        "active_count": 2,
        "last_scan": {
            "scan_ts_ms": 1700000000000,
            "duration_ms": 120,
            "added": 1,
            "removed": 0,
            "rejected_count": 3,
            "top_candidates": [
                {
                    "symbol": "BTCUSDT",
                    "final_score": 87.5,
                    "best_strategy": "MaCrossover",
                    "market_regime": "trending",
                    "trend_phase": "clean_trend",
                    "trend_score": 0.82,
                    "range_score": 0.15,
                    "shock_score": 0.04,
                    "crowding_score": 0.12,
                    "reversal_risk_score": 0.08,
                    "f_ma": 0.81,
                    "f_grid": 0.14,
                    "f_bbrv": 0.22,
                    "f_bkout": 0.74,
                    "f_funding_arb": 0.18,
                    "sector": "majors",
                    "edge_bonus": 3.21,
                    "edge_n": 87,
                    "strategy_judgments": {
                        "ma_crossover": {
                            "route_mode": "normal",
                            "final_score": 90.0,
                            "opportunity": {
                                "opportunity_score": 64.0,
                                "opportunity_lcb_bps": 7.0,
                                "admission_hint": "exploration_candidate",
                                "reason": "shadow",
                            },
                        },
                        "grid_trading": {"route_mode": "market_gate", "final_score": 10.0},
                    },
                },
                {
                    "symbol": "ETHUSDT",
                    "final_score": 72.0,
                    "best_strategy": "FundingArb",
                    "sector": "majors",
                    "edge_bonus": -1.5,
                    "edge_n": 42,
                },
            ],
        },
    }
    with patch("app.ipc_client.EngineIPCClient", _fake_ipc_class(rust_response)):
        result = _run(get_scanner_opportunities(actor=_FakeActor()))
    body = result["data"]
    assert body["source"] == "rust_scanner"
    opps = body["opportunities"]
    assert len(opps) == 2
    assert opps[0]["symbol"] == "BTCUSDT"
    assert opps[0]["strategy_type"] == "MaCrossover"
    assert opps[0]["score"] == 87.5
    assert opps[0]["reason"] == "majors · edge=+3.21 (n=87)"
    assert opps[0]["scanner_context"]["trend_phase"] == "clean_trend"
    assert opps[0]["scanner_context"]["market_regime"] == "trending"
    assert opps[0]["fitness"]["f_bkout"] == 0.74
    assert opps[0]["opportunity"]["admission_hint"] == "exploration_candidate"
    assert opps[0]["opportunity"]["opportunity_lcb_bps"] == 7.0
    assert opps[0]["strategy_judgments"]["ma_crossover"]["route_mode"] == "normal"
    assert opps[0]["breakout_proxy"]["inputs"]["trend_score"] == 0.82
    assert opps[1]["reason"] == "majors · edge=-1.50 (n=42)"
    assert body["stats"]["active_count"] == 2
    assert body["stats"]["rejected_count"] == 3
    assert body["stats"]["candidate_detail_source"] == "ipc"


# ─── Fail-soft paths / 降級路徑 ──────────────────────────────────────────


def test_opportunities_scanner_uninitialized_returns_empty() -> None:
    """Scanner not wired → status='uninitialized' → empty opps, preserve envelope."""
    rust_response = {"status": "uninitialized"}
    with patch("app.ipc_client.EngineIPCClient", _fake_ipc_class(rust_response)):
        result = _run(get_scanner_opportunities(actor=_FakeActor()))
    body = result["data"]
    assert body["opportunities"] == []
    assert body["stats"]["status"] == "uninitialized"
    assert body["source"] == "rust_scanner"


def test_opportunities_last_scan_null_returns_empty() -> None:
    """Scanner wired but no scan yet → last_scan=None → empty opps."""
    rust_response = {
        "status": "ok",
        "active_symbols": [],
        "active_count": 0,
        "last_scan": None,
    }
    with patch("app.ipc_client.EngineIPCClient", _fake_ipc_class(rust_response)):
        result = _run(get_scanner_opportunities(actor=_FakeActor()))
    body = result["data"]
    assert body["opportunities"] == []
    assert body["source"] == "rust_scanner"


def test_opportunities_ipc_exception_fails_soft() -> None:
    """IPC raises → endpoint returns empty opps + source='unavailable', not 500."""
    with patch(
        "app.ipc_client.EngineIPCClient",
        _fake_ipc_class(RuntimeError("IPC broken")),
    ):
        result = _run(get_scanner_opportunities(actor=_FakeActor()))
    body = result["data"]
    assert body["opportunities"] == []
    assert body["source"] == "unavailable"


# ─── Candidate-level robustness / 候選級穩健性 ──────────────────────────


def test_opportunities_skips_non_dict_candidates() -> None:
    """Malformed candidate rows must not poison the batch."""
    rust_response = {
        "status": "ok",
        "last_scan": {
            "top_candidates": [
                "not a dict",
                {"symbol": "BTCUSDT", "final_score": 50.0, "best_strategy": "X"},
                42,
                None,
            ]
        },
    }
    with patch("app.ipc_client.EngineIPCClient", _fake_ipc_class(rust_response)):
        result = _run(get_scanner_opportunities(actor=_FakeActor()))
    opps = result["data"]["opportunities"]
    assert len(opps) == 1
    assert opps[0]["symbol"] == "BTCUSDT"


def test_opportunities_missing_edge_fields_uses_dash_reason() -> None:
    """Candidate with no sector + no edge info → reason='--', other fields kept."""
    rust_response = {
        "status": "ok",
        "last_scan": {
            "top_candidates": [
                {"symbol": "BTCUSDT", "final_score": 50.0, "best_strategy": "X"},
            ]
        },
    }
    with patch("app.ipc_client.EngineIPCClient", _fake_ipc_class(rust_response)):
        result = _run(get_scanner_opportunities(actor=_FakeActor()))
    opps = result["data"]["opportunities"]
    assert opps[0]["reason"] == "--"
    assert opps[0]["score"] == 50.0


def test_opportunities_sector_only_no_edge() -> None:
    """Sector present but edge_n=0 → reason shows sector alone (n=0 means no samples)."""
    rust_response = {
        "status": "ok",
        "last_scan": {
            "top_candidates": [
                {
                    "symbol": "BTCUSDT",
                    "final_score": 50.0,
                    "best_strategy": "X",
                    "sector": "alts",
                    "edge_bonus": 1.2,
                    "edge_n": 0,
                },
            ]
        },
    }
    with patch("app.ipc_client.EngineIPCClient", _fake_ipc_class(rust_response)):
        result = _run(get_scanner_opportunities(actor=_FakeActor()))
    opps = result["data"]["opportunities"]
    assert opps[0]["reason"] == "alts"


def test_opportunities_bad_edge_value_keeps_candidate() -> None:
    """A bad edge_bonus (non-numeric) must only lose its reason, not drop the row."""
    rust_response = {
        "status": "ok",
        "last_scan": {
            "top_candidates": [
                {
                    "symbol": "BTCUSDT",
                    "final_score": 50.0,
                    "best_strategy": "X",
                    "sector": "majors",
                    "edge_bonus": "NaN-string",
                    "edge_n": 10,
                },
            ]
        },
    }
    with patch("app.ipc_client.EngineIPCClient", _fake_ipc_class(rust_response)):
        result = _run(get_scanner_opportunities(actor=_FakeActor()))
    opps = result["data"]["opportunities"]
    assert len(opps) == 1
    assert opps[0]["reason"] == "majors"


def test_opportunities_empty_top_candidates() -> None:
    """Empty candidate list → empty opportunities, stats still populated."""
    rust_response = {
        "status": "ok",
        "last_scan": {
            "scan_ts_ms": 1,
            "duration_ms": 0,
            "added": 0,
            "removed": 0,
            "rejected_count": 0,
            "top_candidates": [],
        },
    }
    with patch("app.ipc_client.EngineIPCClient", _fake_ipc_class(rust_response)):
        result = _run(get_scanner_opportunities(actor=_FakeActor()))
    body = result["data"]
    assert body["opportunities"] == []
    assert body["stats"]["scan_ts_ms"] == 1


def test_enrich_scanner_status_merges_latest_snapshot_candidate_details() -> None:
    ipc_status = {
        "status": "ok",
        "last_scan": {
            "top_candidates": [
                {"symbol": "BTCUSDT", "final_score": 91.2, "best_strategy": "MaCrossover"}
            ],
        },
    }
    snapshot_candidate = {
        "symbol": "BTCUSDT",
        "final_score": 88.0,
        "best_strategy": "ma_crossover",
        "close_alignment": 0.92,
        "range_position": 0.85,
        "strategy_judgments": {
            "ma_crossover": {
                "route_mode": "normal",
                "opportunity": {
                    "opportunity_score": 55.0,
                    "opportunity_lcb_bps": 2.5,
                    "admission_hint": "opportunity_positive",
                    "reason": "snapshot",
                },
            },
            "funding_arb": {"route_mode": "momentum_caution"},
        },
    }

    with patch(
        "app.rust_scanner_reader.fetch_latest_scanner_snapshot_candidate_map",
        return_value={"BTCUSDT": snapshot_candidate},
    ):
        enriched = enrich_scanner_status_with_db(ipc_status)

    candidate = enriched["last_scan"]["top_candidates"][0]
    assert candidate["final_score"] == 91.2
    assert candidate["close_alignment"] == 0.92
    assert candidate["strategy_judgments"]["funding_arb"]["route_mode"] == "momentum_caution"
    assert enriched["last_scan"]["candidate_detail_source"] == "ipc_plus_latest_scanner_snapshot"
