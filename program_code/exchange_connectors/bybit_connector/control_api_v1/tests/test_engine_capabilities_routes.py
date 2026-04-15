"""
Engine capabilities route smoke tests (EDGE-P3-1 Step 7f).
引擎能力路由煙霧測試（EDGE-P3-1 Step 7f）。

MODULE_NOTE (EN): Covers the fail-closed contract of
  GET /api/v1/engine/capabilities — i.e. without a live IPC engine the
  endpoint must still return 200 + degraded=true + the static payload
  sections (api_version / feature_schema / ipc_methods). Also verifies
  a happy path where the IPC client is stubbed to return per-engine
  RiskConfig snapshots — the route must surface them into data.engines.

MODULE_NOTE (中): 驗證 `/api/v1/engine/capabilities` 的 fail-closed 契約與
  happy path 的 per-engine 快照展開。
"""

from __future__ import annotations

import os
import sys
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import engine_capabilities_routes as cap_module  # noqa: E402
from app.engine_capabilities_routes import (  # noqa: E402
    _EDGE_P3_IPC_SUPPORT,
    _EDGE_PREDICTOR_FIELDS,
    _ENGINES,
    engine_capabilities_router,
)
from app.main_legacy import AuthenticatedActor, current_actor  # noqa: E402


def _viewer_actor() -> AuthenticatedActor:
    """Minimal viewer actor (capabilities probe is read-only). / 最小 viewer actor。"""
    return AuthenticatedActor(
        actor_id="test-viewer",
        actor_type="human",
        roles={"viewer"},
        scopes={"private_readonly"},
    )


@pytest.fixture
def client_fail_closed() -> TestClient:
    """
    Build an isolated app with no IPC backend so the route must exercise its
    fail-closed path. Reset the module-level IPC singleton between tests so
    earlier successful tests cannot leak state into this one.
    無 IPC 後端的隔離 app；重置模組級 IPC 單例避免跨測試狀態污染。
    """
    cap_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(engine_capabilities_router)
    app.dependency_overrides[current_actor] = _viewer_actor
    with patch.object(cap_module, "_get_ipc", AsyncMock(return_value=None)):
        yield TestClient(app)


@pytest.fixture
def client_happy() -> TestClient:
    """
    Build an app whose stubbed IPC returns deterministic per-engine RiskConfig
    snapshots so data.engines contains real values.
    存根 IPC 回傳確定性 per-engine RiskConfig 快照，填入 data.engines。
    """
    cap_module._IPC_CLIENT = None

    async def _fake_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "get_risk_config"
        assert params is not None
        engine = params.get("engine")
        # Distinct values per engine so tests can assert correct routing.
        # 每引擎值不同，便於斷言路由正確。
        use_map = {"paper": True, "demo": False, "live": False}
        shadow_map = {"paper": True, "demo": True, "live": False}
        return {
            "config": {
                "edge_predictor": {
                    "use_edge_predictor": use_map[engine],
                    "shadow_mode": shadow_map[engine],
                    "quantile_safety_k": 0.5,
                    "require_q10_positive_for_adds": True,
                    "exploration_rate": 0.05 if engine == "paper" else 0.0,
                    "fallback_on_error": "shrinkage",
                }
            },
            "version": 1,
        }

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)

    app = FastAPI()
    app.include_router(engine_capabilities_router)
    app.dependency_overrides[current_actor] = _viewer_actor
    with patch.object(cap_module, "_get_ipc", AsyncMock(return_value=fake_ipc)):
        yield TestClient(app)


# ─── Fail-closed contract / Fail-closed 契約 ──────────────────────────────


def test_capabilities_returns_200_without_ipc(client_fail_closed: TestClient) -> None:
    """No IPC backend still serves 200. / 無 IPC 仍回 200。"""
    resp = client_fail_closed.get("/api/v1/engine/capabilities")
    assert resp.status_code == 200


def test_capabilities_degraded_when_ipc_down(client_fail_closed: TestClient) -> None:
    """IPC unreachable → degraded=true + reason set. / IPC 斷線 → degraded=true + reason。"""
    body = client_fail_closed.get("/api/v1/engine/capabilities").json()
    data = body["data"]
    assert data["degraded"] is True
    assert data["reason"] == "ipc_unavailable"
    for engine in _ENGINES:
        engine_view = data["engines"][engine]
        for field in _EDGE_PREDICTOR_FIELDS:
            assert engine_view[field] is None, (
                f"{engine}.{field} must be None in fail-closed path, got {engine_view[field]}"
            )


def test_capabilities_static_payload_present_when_degraded(client_fail_closed: TestClient) -> None:
    """Static sections (schema / ipc_methods) must survive IPC failure.
    靜態部分（schema / ipc_methods）即使 IPC 失敗也要存在。"""
    data = client_fail_closed.get("/api/v1/engine/capabilities").json()["data"]
    schema = data["feature_schema"]
    assert schema["schema_version"] == "v1"
    assert schema["dim"] == 17
    assert isinstance(schema["names"], list)
    assert len(schema["names"]) == 17
    assert schema["names"][0] == "adx_1h"
    assert schema["names"][-1] == "is_funding_settlement_window"
    assert data["ipc_methods"] == _EDGE_P3_IPC_SUPPORT


# ─── Happy path / Happy path ──────────────────────────────────────────────


def test_capabilities_happy_path_surfaces_engines(client_happy: TestClient) -> None:
    """Stubbed IPC → data.engines contains per-engine predictor flags; not degraded.
    存根 IPC → data.engines 填入 per-engine 旗標；非 degraded。"""
    body = client_happy.get("/api/v1/engine/capabilities").json()
    data = body["data"]
    assert data["degraded"] is False
    assert data["reason"] is None
    assert data["engines"]["paper"]["use_edge_predictor"] is True
    assert data["engines"]["demo"]["use_edge_predictor"] is False
    assert data["engines"]["live"]["use_edge_predictor"] is False
    assert data["engines"]["paper"]["exploration_rate"] == 0.05
    assert data["engines"]["demo"]["exploration_rate"] == 0.0


def test_capabilities_envelope_shape(client_happy: TestClient) -> None:
    """Envelope keys + category match existing conventions.
    包裝鍵與類別符合既有慣例。"""
    body = client_happy.get("/api/v1/engine/capabilities").json()
    assert body["ok"] is True
    assert body["is_simulated"] is False
    assert body["data_category"] == "engine_capabilities"
    for engine in _ENGINES:
        assert engine in body["data"]["engines"]


def test_capabilities_requires_auth() -> None:
    """Without dependency override → 401 (current_actor rejects empty token).
    無依賴覆蓋 → 401（current_actor 拒絕空 token）。"""
    cap_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(engine_capabilities_router)
    client = TestClient(app)
    resp = client.get("/api/v1/engine/capabilities")
    assert resp.status_code == 401
