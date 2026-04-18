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

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app.strategy_read_routes import get_scanner_opportunities  # noqa: E402


class _FakeActor:
    role = "viewer"
    username = "test"


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


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
                    "sector": "majors",
                    "edge_bonus": 3.21,
                    "edge_n": 87,
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
    assert opps[0] == {
        "symbol": "BTCUSDT",
        "strategy_type": "MaCrossover",
        "score": 87.5,
        "reason": "majors · edge=+3.21 (n=87)",
    }
    assert opps[1]["reason"] == "majors · edge=-1.50 (n=42)"
    assert body["stats"]["active_count"] == 2
    assert body["stats"]["rejected_count"] == 3


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
