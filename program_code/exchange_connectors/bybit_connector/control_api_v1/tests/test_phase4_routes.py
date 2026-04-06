"""
Phase 4 (4-00) Dashboard skeleton — route smoke tests.
Phase 4 (4-00) 儀表板骨架 — 路由 smoke 測試。

MODULE_NOTE (中文):
  本模組對 phase4_routes.py 的 /api/v1/phase4/status 端點做最小煙霧測試：
  確保在 IPC 不可用的測試環境中，端點仍能 fail-closed 返回全 grey 的合法
  payload，schema 完整、status 詞彙合法。

MODULE_NOTE (English):
  Smoke tests for the /api/v1/phase4/status endpoint defined in
  phase4_routes.py. We do NOT need a live IPC engine — the route is designed
  to fail-closed to all-grey when the engine is unavailable, which matches
  the test environment.
"""

from __future__ import annotations

import os
import sys

import pytest

# ─── Path setup / 路徑設置 ────────────────────────────────────────────────
_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.phase4_routes import phase4_router  # noqa: E402


_VALID_LIGHTS = {"grey", "green", "yellow", "red"}
_MODULES = ("teacher", "linucb", "news", "dl3")


@pytest.fixture
def client() -> TestClient:
    """
    Build a minimal FastAPI app that only mounts the Phase 4 router.
    建立只挂载 Phase 4 路由的最小 FastAPI 應用。
    """
    app = FastAPI()
    app.include_router(phase4_router)
    return TestClient(app)


def test_phase4_status_returns_200(client: TestClient) -> None:
    """Endpoint must respond 200 even without a live engine. / 即使无引擎仍须 200。"""
    resp = client.get("/api/v1/phase4/status")
    assert resp.status_code == 200


def test_phase4_status_schema_complete(client: TestClient) -> None:
    """Response must contain all 4 modules + last_update_ms. / 须包含 4 模组 + 时间戳。"""
    body = client.get("/api/v1/phase4/status").json()
    for key in _MODULES:
        assert key in body, f"missing module key: {key}"
        assert body[key] in _VALID_LIGHTS, f"invalid status for {key}: {body[key]}"
    assert "last_update_ms" in body
    assert isinstance(body["last_update_ms"], int)
    assert body["last_update_ms"] > 0


def test_phase4_status_fail_closed_grey(client: TestClient) -> None:
    """
    Without a live IPC engine, every module must be reported as grey
    and the response should be flagged degraded=true (fail-closed).
    无 IPC 引擎时所有模组应回报 grey，并标记 degraded=true（fail-closed）。
    """
    body = client.get("/api/v1/phase4/status").json()
    for key in _MODULES:
        assert body[key] == "grey", f"expected grey for {key} in test env, got {body[key]}"
    # degraded flag must exist; in test env it should be True
    # （IPC 不可用应明确标记 degraded）
    assert "degraded" in body
    assert body["degraded"] is True


def test_phase4_redirect_to_static_tab(client: TestClient) -> None:
    """GET /api/v1/phase4 should redirect to the static tab. / 须重定向至静态 tab。"""
    resp = client.get("/api/v1/phase4", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "/static/tab-phase4.html" in resp.headers.get("location", "")


# ─── 4-03 Teacher card route tests / Teacher 卡片路由測試 ────────────────


def test_phase4_teacher_route_returns_200_fail_soft(client: TestClient) -> None:
    """GET /api/v1/phase4/teacher must respond 200 even without PG (fail-soft).
    無 PG 時 /api/v1/phase4/teacher 仍須回 200（fail-soft）。
    """
    resp = client.get("/api/v1/phase4/teacher")
    assert resp.status_code == 200


def test_phase4_teacher_route_schema_complete(client: TestClient) -> None:
    """Response must contain all required keys with valid types.
    回應須包含所有必要 key 且型別正確。
    """
    body = client.get("/api/v1/phase4/teacher").json()
    required_keys = {
        "ok",
        "status_light",
        "total_7d",
        "applied_7d",
        "exec_rate",
        "avg_outcome_24h",
        "recent",
        "last_update_ms",
    }
    assert required_keys.issubset(body.keys())
    assert body["status_light"] in _VALID_LIGHTS
    assert isinstance(body["total_7d"], int)
    assert isinstance(body["applied_7d"], int)
    assert isinstance(body["recent"], list)
    assert isinstance(body["last_update_ms"], int)


def test_phase4_teacher_route_grey_when_no_pg(client: TestClient) -> None:
    """Without PG, the route should fail-soft to grey + ok=false.
    無 PG 時應 fail-soft 為 grey + ok=false。
    """
    body = client.get("/api/v1/phase4/teacher").json()
    assert body["ok"] is False
    assert body["status_light"] == "grey"
    assert body["total_7d"] == 0
    assert body["applied_7d"] == 0
    assert body["exec_rate"] == 0.0
    assert body["recent"] == []


def test_phase4_classify_teacher_status_green():
    """High exec rate + non-negative outcome → green."""
    from app.phase4_routes import _classify_teacher_status

    assert _classify_teacher_status(0.85, 5.0) == "green"
    assert _classify_teacher_status(0.85, 0.0) == "green"


def test_phase4_classify_teacher_status_yellow():
    """Mid exec rate or mildly negative outcome → yellow."""
    from app.phase4_routes import _classify_teacher_status

    assert _classify_teacher_status(0.7, 0.0) == "yellow"
    assert _classify_teacher_status(0.85, -5.0) == "yellow"


def test_phase4_classify_teacher_status_red():
    """Low exec rate or very negative outcome → red."""
    from app.phase4_routes import _classify_teacher_status

    assert _classify_teacher_status(0.3, 0.0) == "red"  # exec rate too low
    assert _classify_teacher_status(0.85, -50.0) == "red"  # very negative outcome


def test_phase4_classify_teacher_status_none_outcome_treated_as_zero():
    """avg_outcome_24h = None should be treated as 0 (no info)."""
    from app.phase4_routes import _classify_teacher_status

    assert _classify_teacher_status(0.85, None) == "green"
    assert _classify_teacher_status(0.5, None) == "red"
