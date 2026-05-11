"""
LG-1 T4 — H0 Block Summary Route 測試 / H0 block summary route tests.

MODULE_NOTE (中文):
  涵蓋 PA tech plan §1.4 表 T4 新增的 GET /api/v1/paper/risk/h0_block_summary。
  五個案例：PASS（hard-block 啟用且 fail-closed 不變式成立）/ WARN（shadow_mode=true）
  / WARN（engine unavailable）/ FAIL（保留：當前實作未定 FAIL 觸發點，僅在
  未來 cumulative monotonic 違反時觸發）/ NO DATA（engine 列表空）。

  使用 fake PG 和 fake RustSnapshotReader 保持測試封閉，無需真實 PG / engine。

  資料源：
    - h0_gate_stats: 模擬 Rust pipeline snapshot 的 GateStats dict
    - trading.fills: 模擬窗口期 fills count（per engine_mode）
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import pytest

# ── path setup ──
# 路徑設置
_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import risk_routes as rr_module  # noqa: E402
from app.main_legacy import AuthenticatedActor, current_actor  # noqa: E402
from app.risk_routes import (  # noqa: E402
    H0BlockSummaryEngineDetail,
    H0BlockSummaryResponse,
    _aggregate_h0_summary,
    _h0_reason_breakdown,
    _per_engine_h0_summary,
    _top_level_verdict,
    risk_router,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Test helpers / 測試輔助
# ═══════════════════════════════════════════════════════════════════════════════


def _viewer_actor() -> AuthenticatedActor:
    """測試用 viewer actor（read-only scope）。"""
    return AuthenticatedActor(
        actor_id="test-viewer",
        actor_type="human",
        roles={"viewer"},
        scopes={"private_readonly"},
    )


def _make_gate_stats(
    blocked_freshness: int = 0,
    blocked_health: int = 0,
    blocked_eligibility: int = 0,
    blocked_envelope: int = 0,
    blocked_cooldown: int = 0,
    total_checks: int = 0,
) -> dict[str, Any]:
    """模擬 Rust GateStats 的 dict 形態（snapshot 內 h0_gate_stats 欄位）。"""
    return {
        "total_checks": total_checks,
        "total_allowed": total_checks - (
            blocked_freshness + blocked_health + blocked_eligibility
            + blocked_envelope + blocked_cooldown
        ),
        "blocked_freshness": blocked_freshness,
        "blocked_health": blocked_health,
        "blocked_eligibility": blocked_eligibility,
        "blocked_envelope": blocked_envelope,
        "blocked_cooldown": blocked_cooldown,
        "shadow_would_block": 0,
        "max_latency_us": 100,
        "total_latency_us": total_checks * 50,
    }


def _make_snapshot(
    h0_shadow_mode: bool,
    gate_stats: dict[str, Any] | None,
    written_at_ms: int = 1726000000000,
) -> dict[str, Any]:
    """模擬 Rust pipeline snapshot（只放本路由用到的欄位）。"""
    snap: dict[str, Any] = {
        "schema_version": "2.0.0",
        "written_at_ms": written_at_ms,
        "risk_manager_config": {
            "runtime": {"h0_shadow_mode": h0_shadow_mode},
        },
    }
    if gate_stats is not None:
        snap["h0_gate_stats"] = gate_stats
    return snap


class _FakeReader:
    """模擬 RustSnapshotReader：用 dict {engine: snapshot or None} 驅動行為。"""

    def __init__(self, engine_to_snap: dict[str, dict[str, Any] | None]) -> None:
        # engine_to_snap[engine] = snapshot dict (available) or None (unavailable)
        self._map = engine_to_snap

    def is_engine_available(self, engine: str) -> bool:
        return self._map.get(engine) is not None

    def get_snapshot(self, engine: str | None = None) -> dict[str, Any] | None:
        if engine is None:
            return None
        return self._map.get(engine)


@contextmanager
def _patch_reader(engine_to_snap: dict[str, dict[str, Any] | None]):
    """Patch get_rust_reader to return a FakeReader."""
    fake = _FakeReader(engine_to_snap)
    with patch.object(rr_module, "get_rust_reader", lambda: fake):
        yield fake


@contextmanager
def _patch_pg(fills_per_engine: dict[str, int] | None):
    """Patch _count_fills_in_window to return given dict (or simulate PG down)."""

    def _fake(_engines: list[str], _window_hours: int) -> dict[str, int]:
        if fills_per_engine is None:
            return {em: 0 for em in _engines}
        return {em: fills_per_engine.get(em, 0) for em in _engines}

    with patch.object(rr_module, "_count_fills_in_window", _fake):
        yield


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient with viewer auth + risk_router only."""
    app = FastAPI()
    app.include_router(risk_router)
    app.dependency_overrides[current_actor] = _viewer_actor
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════════
# Unit tests — helper functions / 輔助函數單元測試
# ═══════════════════════════════════════════════════════════════════════════════


def test_h0_reason_breakdown_with_full_stats() -> None:
    """GateStats dict 完整時，breakdown 5 個 reason + total_blocked + total_checks 都對。"""
    gs = _make_gate_stats(
        blocked_freshness=10,
        blocked_health=5,
        blocked_eligibility=2,
        blocked_envelope=1,
        blocked_cooldown=3,
        total_checks=1000,
    )
    by_reason, total_blocked, total_checks = _h0_reason_breakdown(gs)
    assert by_reason == {
        "freshness": 10, "health": 5, "eligibility": 2, "envelope": 1, "cooldown": 3,
    }
    assert total_blocked == 21
    assert total_checks == 1000


def test_h0_reason_breakdown_handles_missing_keys() -> None:
    """空 dict / None 都安全回 (空, 0, 0)。"""
    by_reason, total_blocked, total_checks = _h0_reason_breakdown(None)
    assert by_reason == {} and total_blocked == 0 and total_checks == 0

    by_reason, total_blocked, total_checks = _h0_reason_breakdown({})
    # 空 dict 走 default-0 路徑
    assert total_blocked == 0 and total_checks == 0
    assert by_reason == {
        "freshness": 0, "health": 0, "eligibility": 0, "envelope": 0, "cooldown": 0,
    }


def test_aggregate_h0_summary_picks_latest_ts() -> None:
    """跨 engine 聚合時，last_check_at_utc 取最新者。"""
    details = [
        H0BlockSummaryEngineDetail(
            engine_mode="demo",
            engine_available=True,
            h0_block_events_total=5,
            h0_block_events_by_reason={"freshness": 5},
            last_check_at_utc="2026-05-11T08:00:00+00:00",
        ),
        H0BlockSummaryEngineDetail(
            engine_mode="live",
            engine_available=True,
            h0_block_events_total=3,
            h0_block_events_by_reason={"health": 3},
            last_check_at_utc="2026-05-11T09:30:00+00:00",  # 較新
        ),
    ]
    total, by_reason, last = _aggregate_h0_summary(details)
    assert total == 8
    assert by_reason["freshness"] == 5
    assert by_reason["health"] == 3
    assert last == "2026-05-11T09:30:00+00:00"


def test_top_level_verdict_all_pass() -> None:
    """所有 engine PASS → 頂層 PASS + 100% acceptance。"""
    details = [
        H0BlockSummaryEngineDetail(engine_mode="demo", engine_available=True, health_status="PASS"),
        H0BlockSummaryEngineDetail(engine_mode="live_demo", engine_available=True, health_status="PASS"),
    ]
    status, pct, _ = _top_level_verdict(details)
    assert status == "PASS"
    assert pct == 100.0


def test_top_level_verdict_any_fail_short_circuits() -> None:
    """任一 engine FAIL → 頂層 FAIL + 0% acceptance。"""
    details = [
        H0BlockSummaryEngineDetail(engine_mode="demo", engine_available=True, health_status="PASS"),
        H0BlockSummaryEngineDetail(engine_mode="live", engine_available=True, health_status="FAIL"),
    ]
    status, pct, _ = _top_level_verdict(details)
    assert status == "FAIL"
    assert pct == 0.0


def test_top_level_verdict_partial_warn() -> None:
    """部分 WARN + 無 FAIL → 頂層 WARN + 50% acceptance。"""
    details = [
        H0BlockSummaryEngineDetail(engine_mode="demo", engine_available=True, health_status="PASS"),
        H0BlockSummaryEngineDetail(engine_mode="paper", engine_available=False, health_status="WARN"),
    ]
    status, pct, _ = _top_level_verdict(details)
    assert status == "WARN"
    assert pct == 50.0


def test_top_level_verdict_empty_input() -> None:
    """無 engine 資料 → WARN + 0%。"""
    status, pct, notes = _top_level_verdict([])
    assert status == "WARN"
    assert pct == 0.0
    assert any("無 engine 資料" in n for n in notes)


def test_per_engine_summary_pass_hard_block() -> None:
    """h0_shadow_mode=false + 有 cumulative checks → 子裁決 PASS。"""
    gs = _make_gate_stats(blocked_freshness=2, total_checks=500)
    snap = _make_snapshot(h0_shadow_mode=False, gate_stats=gs)
    with _patch_reader({"demo": snap}):
        det = _per_engine_h0_summary("demo", fills_count=10, window_hours=24)
    assert det.engine_available is True
    assert det.h0_shadow_mode is False
    assert det.h0_block_events_total == 2
    assert det.h0_block_events_by_reason["freshness"] == 2
    assert det.h0_total_checks == 500
    assert det.health_status == "PASS"
    assert det.fills_in_window == 10


def test_per_engine_summary_warn_shadow_mode() -> None:
    """h0_shadow_mode=true → 子裁決 WARN。"""
    gs = _make_gate_stats(blocked_freshness=0, total_checks=100)
    snap = _make_snapshot(h0_shadow_mode=True, gate_stats=gs)
    with _patch_reader({"paper": snap}):
        det = _per_engine_h0_summary("paper", fills_count=0, window_hours=24)
    assert det.h0_shadow_mode is True
    assert det.health_status == "WARN"
    assert any("shadow_mode" in n.lower() for n in det.notes)


def test_per_engine_summary_warn_unavailable() -> None:
    """engine snapshot 不可達 → 子裁決 WARN + engine_available=false。"""
    with _patch_reader({"demo": None}):
        det = _per_engine_h0_summary("demo", fills_count=0, window_hours=24)
    assert det.engine_available is False
    assert det.health_status == "WARN"
    assert det.h0_block_events_total == 0
    assert any("snapshot 不可達" in n for n in det.notes)


def test_per_engine_summary_live_demo_maps_to_live_snapshot() -> None:
    """live_demo 走 live pipeline_snapshot（is_live=true）。"""
    gs = _make_gate_stats(blocked_envelope=1, total_checks=200)
    snap = _make_snapshot(h0_shadow_mode=False, gate_stats=gs)
    # FakeReader 只認 "live" key（不認 "live_demo"），驗證 mapping 正確
    with _patch_reader({"live": snap}):
        det = _per_engine_h0_summary("live_demo", fills_count=5, window_hours=24)
    assert det.engine_available is True
    assert det.h0_block_events_total == 1
    assert det.health_status == "PASS"


# ═══════════════════════════════════════════════════════════════════════════════
# Route-level tests / Route 級測試
# ═══════════════════════════════════════════════════════════════════════════════


def test_route_default_window_all_engines_pass(client: TestClient) -> None:
    """預設 window=24h，所有 engine snapshot 可達 + hard-block 啟用 → PASS。"""
    gs = _make_gate_stats(blocked_freshness=5, total_checks=10000)
    snap = _make_snapshot(h0_shadow_mode=False, gate_stats=gs)
    engine_map = {
        "paper": _make_snapshot(h0_shadow_mode=False, gate_stats=gs),
        "demo": snap,
        "live": snap,
    }
    fills = {"paper": 0, "demo": 12, "live": 8, "live_demo": 0}
    with _patch_reader(engine_map), _patch_pg(fills):
        resp = client.get("/api/v1/paper/risk/h0_block_summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["window_hours"] == 24
    assert body["health_status"] == "PASS"
    assert body["block_acceptance_pct"] == 100.0
    # 設計不變式
    assert body["fills_during_block"] == 0
    # 5 engine_modes whitelist (paper/demo/live/live_demo) — paper+demo+live snapshot avail；
    # live_demo 用 live snapshot mapping 也 avail
    assert "freshness" in body["h0_block_events_by_reason"]
    assert body["h0_block_events_total"] >= 5  # 三 engine 都拿同 gate_stats，各 +5


def test_route_engine_filter_demo_only(client: TestClient) -> None:
    """engine_mode=demo → 只回 demo engine 結果。"""
    gs = _make_gate_stats(blocked_envelope=3, total_checks=300)
    engine_map = {"demo": _make_snapshot(h0_shadow_mode=False, gate_stats=gs)}
    fills = {"demo": 7}
    with _patch_reader(engine_map), _patch_pg(fills):
        resp = client.get("/api/v1/paper/risk/h0_block_summary?engine_mode=demo")
    assert resp.status_code == 200
    body = resp.json()
    assert body["engine_modes"] == ["demo"]
    assert len(body["engines"]) == 1
    assert body["engines"][0]["engine_mode"] == "demo"
    assert body["engines"][0]["fills_in_window"] == 7
    assert body["engines"][0]["h0_block_events_total"] == 3


def test_route_shadow_mode_warn(client: TestClient) -> None:
    """所有 engine h0_shadow_mode=true → WARN。"""
    gs = _make_gate_stats(total_checks=50)
    snap_shadow = _make_snapshot(h0_shadow_mode=True, gate_stats=gs)
    engine_map = {
        "paper": snap_shadow, "demo": snap_shadow, "live": snap_shadow,
    }
    with _patch_reader(engine_map), _patch_pg({}):
        resp = client.get("/api/v1/paper/risk/h0_block_summary?engine_mode=paper")
    assert resp.status_code == 200
    body = resp.json()
    assert body["health_status"] == "WARN"
    assert body["engines"][0]["health_status"] == "WARN"


def test_route_engine_unavailable_warn(client: TestClient) -> None:
    """engine snapshot 不可達（None）→ engine 子裁決 WARN。"""
    engine_map = {"paper": None, "demo": None, "live": None}
    with _patch_reader(engine_map), _patch_pg({}):
        resp = client.get("/api/v1/paper/risk/h0_block_summary?engine_mode=live")
    assert resp.status_code == 200
    body = resp.json()
    assert body["health_status"] == "WARN"
    assert body["engines"][0]["engine_available"] is False


def test_route_invalid_engine_mode_400(client: TestClient) -> None:
    """非白名單 engine_mode → 400。"""
    resp = client.get("/api/v1/paper/risk/h0_block_summary?engine_mode=mainnet")
    assert resp.status_code == 400
    assert "engine_mode" in resp.json()["detail"]


def test_route_invalid_window_hours_400(client: TestClient) -> None:
    """window_hours 超過 30 天 → 400。"""
    resp = client.get("/api/v1/paper/risk/h0_block_summary?window_hours=10000")
    assert resp.status_code == 400
    assert "window_hours" in resp.json()["detail"]

    resp = client.get("/api/v1/paper/risk/h0_block_summary?window_hours=0")
    assert resp.status_code == 400


def test_route_response_schema_complete(client: TestClient) -> None:
    """response_model 驗證所有必要欄位都存在。"""
    gs = _make_gate_stats(blocked_health=1, total_checks=100)
    snap = _make_snapshot(h0_shadow_mode=False, gate_stats=gs)
    with _patch_reader({"demo": snap}), _patch_pg({"demo": 3}):
        resp = client.get("/api/v1/paper/risk/h0_block_summary?engine_mode=demo")
    assert resp.status_code == 200
    body = resp.json()

    # 頂層必要欄位
    expected_top = {
        "window_hours", "engine_modes", "engines",
        "h0_block_events_total", "h0_block_events_by_reason",
        "fills_during_block", "last_block_event_at_utc",
        "block_acceptance_pct", "health_status", "notes",
    }
    assert expected_top.issubset(set(body.keys()))

    # engine-level 必要欄位
    expected_eng = {
        "engine_mode", "h0_shadow_mode", "engine_available",
        "h0_block_events_total", "h0_block_events_by_reason",
        "h0_total_checks", "h0_allow_rate_pct",
        "fills_in_window", "last_check_at_utc",
        "health_status", "notes",
    }
    assert expected_eng.issubset(set(body["engines"][0].keys()))


def test_route_unauthenticated_401(client: TestClient) -> None:
    """無 auth dependency override 時應 401（驗證 auth gate 真實生效）。"""
    # 創建新 client 沒有 dependency override，模擬 unauthenticated request
    app = FastAPI()
    app.include_router(risk_router)
    unauth_client = TestClient(app)
    resp = unauth_client.get("/api/v1/paper/risk/h0_block_summary")
    # current_actor 走 cookie/header；沒 token → 401
    assert resp.status_code == 401


def test_route_pg_unavailable_graceful_degrade(client: TestClient) -> None:
    """PG 不可用時 fills_in_window=0 + 仍回 200（不 5xx）。"""
    gs = _make_gate_stats(blocked_cooldown=1, total_checks=10)
    snap = _make_snapshot(h0_shadow_mode=False, gate_stats=gs)

    # _count_fills_in_window 內部 PG fail-safe = 全 0
    def _fake_pg(engines: list[str], _w: int) -> dict[str, int]:
        return {em: 0 for em in engines}

    with _patch_reader({"demo": snap}), patch.object(rr_module, "_count_fills_in_window", _fake_pg):
        resp = client.get("/api/v1/paper/risk/h0_block_summary?engine_mode=demo")
    assert resp.status_code == 200
    body = resp.json()
    assert body["engines"][0]["fills_in_window"] == 0
    # 仍 PASS（因 h0_shadow_mode=false）
    assert body["health_status"] == "PASS"


# Sanity: pydantic model directly constructible / Pydantic model 可直接構造
def test_response_model_directly_constructible() -> None:
    """Pydantic model 可獨立構造（schema 不依賴 route 內部 state）。"""
    resp = H0BlockSummaryResponse(
        window_hours=24,
        engine_modes=["demo"],
        engines=[
            H0BlockSummaryEngineDetail(
                engine_mode="demo",
                engine_available=True,
                h0_block_events_total=0,
                h0_block_events_by_reason={"freshness": 0},
            ),
        ],
    )
    assert resp.health_status == "PASS"  # default
    assert resp.fills_during_block == 0
