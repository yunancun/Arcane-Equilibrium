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
from unittest.mock import patch

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


@patch("app.db_pool.get_conn", return_value=None)
def test_phase4_teacher_route_grey_when_no_pg(_mock_pool, client: TestClient) -> None:
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


# ─── 4-10 News card route tests / News 卡片路由測試 ──────────────────────


def test_phase4_news_route_returns_200_fail_soft(client: TestClient) -> None:
    """GET /api/v1/phase4/news must respond 200 even without PG (fail-soft).
    無 PG 時 /api/v1/phase4/news 仍須回 200（fail-soft）。
    """
    resp = client.get("/api/v1/phase4/news")
    assert resp.status_code == 200


def test_phase4_news_route_schema_complete(client: TestClient) -> None:
    """Response must contain all required keys with valid types.
    回應須包含所有必要 key 且型別正確。
    """
    body = client.get("/api/v1/phase4/news").json()
    required_keys = {
        "ok",
        "status_light",
        "total_24h",
        "halt_triggers_24h",
        "max_severity_24h",
        "recent",
        "providers",
        "last_update_ms",
    }
    assert required_keys.issubset(body.keys())
    assert body["status_light"] in _VALID_LIGHTS
    assert isinstance(body["total_24h"], int)
    assert isinstance(body["halt_triggers_24h"], int)
    assert isinstance(body["recent"], list)
    assert isinstance(body["providers"], list)
    assert isinstance(body["last_update_ms"], int)
    # 4 known providers should always be present (stub until 4-W4 wiring).
    # 4 個已知 provider 必須存在（4-W4 wiring 之前為 stub）。
    assert len(body["providers"]) == 4
    names = {p["name"] for p in body["providers"]}
    assert names == {"cryptopanic", "cointelegraph_rss", "google_news_rss", "mock"}
    for p in body["providers"]:
        assert "status" in p
        assert "quota_remaining" in p


@patch("app.db_pool.get_conn", return_value=None)
def test_phase4_news_route_grey_when_no_pg(_mock_pool, client: TestClient) -> None:
    """Without PG, the route should fail-soft to grey + ok=false.
    無 PG 時應 fail-soft 為 grey + ok=false。
    """
    body = client.get("/api/v1/phase4/news").json()
    assert body["ok"] is False
    assert body["status_light"] == "grey"
    assert body["total_24h"] == 0
    assert body["halt_triggers_24h"] == 0
    assert body["max_severity_24h"] is None
    assert body["recent"] == []
    # Provider stub still returned even on fail-closed path.
    # Fail-closed 路徑也要回傳 provider stub。
    assert len(body["providers"]) == 4


def test_phase4_classify_news_status_green():
    """Normal news flow + no extreme severity → green."""
    from app.phase4_routes import _classify_news_status

    assert _classify_news_status(12, 2, 0.85) == "green"
    assert _classify_news_status(1, 0, None) == "green"


def test_phase4_classify_news_status_yellow():
    """Zero news in 24h → yellow (provider may be dead)."""
    from app.phase4_routes import _classify_news_status

    assert _classify_news_status(0, 0, None) == "yellow"


def test_phase4_classify_news_status_red():
    """max_severity >= 0.95 → red (extreme risk headline)."""
    from app.phase4_routes import _classify_news_status

    assert _classify_news_status(5, 3, 0.96) == "red"
    assert _classify_news_status(20, 5, 1.0) == "red"


# ─── 4-14 DL-3 card route tests / DL-3 卡片路由測試 ──────────────────────


def test_phase4_dl3_route_returns_200_fail_soft(client: TestClient) -> None:
    """GET /api/v1/phase4/dl3 must respond 200 even without PG (fail-soft).
    無 PG 時 /api/v1/phase4/dl3 仍須回 200（fail-soft）。
    """
    resp = client.get("/api/v1/phase4/dl3")
    assert resp.status_code == 200


def test_phase4_dl3_route_schema_complete(client: TestClient) -> None:
    """Response must contain all required keys with valid types.
    回應須包含所有必要 key 且型別正確。
    """
    body = client.get("/api/v1/phase4/dl3").json()
    required_keys = {
        "ok",
        "status_light",
        "latest_decision",
        "auc_delta",
        "models",
        "recent",
        "last_update_ms",
    }
    assert required_keys.issubset(body.keys())
    assert body["status_light"] in _VALID_LIGHTS
    assert isinstance(body["models"], dict)
    assert "chronos" in body["models"]
    assert "timesfm" in body["models"]
    assert isinstance(body["recent"], list)
    assert isinstance(body["last_update_ms"], int)


@patch("app.db_pool.get_conn", return_value=None)
def test_phase4_dl3_route_grey_when_no_pg(_mock_pool, client: TestClient) -> None:
    """Without PG, the route should fail-soft to grey + ok=false.
    無 PG 時應 fail-soft 為 grey + ok=false。
    """
    body = client.get("/api/v1/phase4/dl3").json()
    assert body["ok"] is False
    assert body["status_light"] == "grey"
    assert body["latest_decision"] is None
    assert body["auc_delta"] is None
    assert body["recent"] == []
    assert body["models"]["chronos"] is None
    assert body["models"]["timesfm"] is None


def test_phase4_classify_dl3_status_green():
    """GO decision + full ok_rate → green."""
    from app.phase4_routes import _classify_dl3_status

    assert _classify_dl3_status("GO", 1.0) == "green"
    assert _classify_dl3_status("GO", None) == "green"


def test_phase4_classify_dl3_status_yellow():
    """GO with degraded ok_rate OR PENDING_DATA → yellow."""
    from app.phase4_routes import _classify_dl3_status

    assert _classify_dl3_status("GO", 0.8) == "yellow"
    assert _classify_dl3_status("PENDING_DATA", None) == "yellow"


def test_phase4_classify_dl3_status_red_and_grey():
    """NO_GO → red; unknown → grey."""
    from app.phase4_routes import _classify_dl3_status

    assert _classify_dl3_status("NO_GO", 1.0) == "red"
    assert _classify_dl3_status(None, None) == "grey"
    assert _classify_dl3_status("WEIRD", None) == "grey"


def test_phase4_classify_dl3_model_availability():
    """Substring match infers availability from observed model names.
    子字串匹配由已觀察到的 model 名稱推斷可用性。
    """
    from app.phase4_routes import _classify_dl3_model_availability

    seen = {"chronos-t5-tiny", "timesfm-1.0-200m"}
    assert _classify_dl3_model_availability("chronos", seen) is True
    assert _classify_dl3_model_availability("timesfm", seen) is True
    assert _classify_dl3_model_availability("chronos", set()) is None


# ─── 4-20 weekly review approval routes ─────────────────────────────────


def test_phase4_weekly_review_approve_validates_payload(client: TestClient) -> None:
    """Missing required fields → 422 Pydantic validation error.
    缺必要欄位 → 422 Pydantic 驗證錯誤。
    """
    resp = client.post("/api/v1/phase4/weekly_review/approve", json={})
    assert resp.status_code == 422


def test_phase4_weekly_review_approve_route_returns_200_fail_soft(client: TestClient) -> None:
    """Valid payload but no PG → 200 with ok=false (fail-soft, no 5xx).
    合法 payload 但無 PG → 200 + ok=false（fail-soft，無 5xx）。
    """
    resp = client.post(
        "/api/v1/phase4/weekly_review/approve",
        json={"week_iso": "2026-W15", "approved_by": "test_op"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert "error" in body


def test_phase4_weekly_review_reject_route_returns_200_fail_soft(client: TestClient) -> None:
    """Reject endpoint also fail-soft on no-PG.
    Reject 端點在無 PG 時也 fail-soft。
    """
    resp = client.post(
        "/api/v1/phase4/weekly_review/reject",
        json={"week_iso": "2026-W15", "approved_by": "test_op", "decision_notes": "x"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False


@patch("app.db_pool.get_conn", return_value=None)
def test_phase4_weekly_review_latest_route_fail_soft(_mock_pool, client: TestClient) -> None:
    """GET latest endpoint should fail-soft to ok=false + review=null.
    GET latest 端點應 fail-soft 為 ok=false + review=null。
    """
    resp = client.get("/api/v1/phase4/weekly_review/latest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["review"] is None


def test_phase4_weekly_review_approve_negative_week_iso_validates(client: TestClient) -> None:
    """Empty week_iso → Pydantic min_length=1 violation → 422.
    空 week_iso → Pydantic min_length=1 違反 → 422。
    """
    resp = client.post(
        "/api/v1/phase4/weekly_review/approve",
        json={"week_iso": "", "approved_by": "test_op"},
    )
    assert resp.status_code == 422
