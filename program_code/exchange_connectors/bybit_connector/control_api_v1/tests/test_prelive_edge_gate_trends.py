"""Tests for pre-live edge gate trend payloads.
Pre-live edge gate 趨勢 payload 測試。
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest

from app import prelive_edge_gate_trends as trends


def _ready_gates() -> dict:
    """Return passing gate payloads for readiness tests. 回傳 readiness 測試用通過 payload。"""
    return {
        "33": {
            "available": True,
            "current": {
                "entry_fills": 35,
                "fee_drop_pct": 62.0,
                "maker_like_pct": 55.0,
            },
        },
        "38": {
            "available": True,
            "current": {
                "demo_n": 6,
                "live_demo_n": 6,
                "lifetime_ratio": 0.58,
                "live_demo_reentry_rate": 0.42,
            },
        },
        "40": {
            "available": True,
            "current": {
                "rows": 40,
                "avg_net_bps": 6.2,
                "bad_cells": [],
            },
        },
    }


def test_build_live_readiness_passes_when_all_gate_targets_are_met() -> None:
    readiness = trends.build_live_readiness(_ready_gates())

    assert readiness["ready"] is True
    assert readiness["status"] == "ready"
    assert readiness["passed"] == readiness["total"]
    assert readiness["unknown"] == 0


def test_build_live_readiness_marks_fee_drop_failure_not_ready() -> None:
    gates = _ready_gates()
    gates["33"]["current"]["fee_drop_pct"] = 31.0

    readiness = trends.build_live_readiness(gates)

    assert readiness["ready"] is False
    by_key = {item["key"]: item for item in readiness["items"]}
    assert by_key["postonly_fee_drop"]["status"] == "fail"
    assert by_key["postonly_fee_drop"]["passed"] is False


def test_fetch_prelive_edge_gate_trends_degrades_when_pg_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def no_connection() -> Iterator[None]:
        yield None

    monkeypatch.setattr(trends, "get_pg_conn", no_connection)

    payload = trends.fetch_prelive_edge_gate_trends(window_days=7)

    assert payload["available"] is False
    assert set(payload["gates"]) == {"33", "38", "40"}
    assert payload["readiness"]["ready"] is False
    assert payload["error"] == "postgres connection unavailable"


@pytest.mark.asyncio
async def test_prelive_edge_gate_route_returns_enveloped_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import strategy_read_routes as routes

    def fake_fetch(window_days: int = 7) -> dict:
        return {
            "available": True,
            "source": "unit_test",
            "window_days": window_days,
            "gates": {"33": {}, "38": {}, "40": {}},
            "readiness": {"ready": False, "status": "not_ready", "items": []},
        }

    monkeypatch.setattr(routes, "fetch_prelive_edge_gate_trends", fake_fetch)

    out = await routes.get_prelive_edge_gates(window_days=9, actor=None)

    assert out["data"]["source"] == "unit_test"
    assert out["data"]["window_days"] == 9


def test_live_static_tab_renders_prelive_edge_gate_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    tab = (root / "app" / "static" / "tab-live.html").read_text(encoding="utf-8")
    common = (root / "app" / "static" / "common.js").read_text(encoding="utf-8")

    assert "/api/v1/strategy/prelive/edge-gates" in tab
    assert "loadPreLiveEdgeGates" in tab
    assert "live-readiness-checklist" in tab
    assert "ocMiniTrendSvg" in common
