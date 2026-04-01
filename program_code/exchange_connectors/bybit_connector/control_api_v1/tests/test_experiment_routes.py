"""
E4 Phase 3 Batch 3A — ExperimentRoutes API Tests
E4 Phase 3 Batch 3A — ExperimentRoutes API 測試

MODULE_NOTE (中文):
  本模塊為 experiment_routes.py 提供 REST API 層測試。
  策略：使用 FastAPI TestClient + 依賴覆蓋 override auth dependency，
  並 mock ExperimentLedger 避免依賴其真實實現（experiment_ledger.py 可能尚未存在）。

  測試目標：
  R1. POST /propose — 認證守衛 + 正常路徑 + 必填字段驗證 + proposed_by 設置
  R2. POST /{id}/observe — 認證守衛 + 支持/反駁觀測 + 404 未知 ID
  R3. GET /{id} — 認證守衛 + 正常路徑 + 404 + 非 Operator 也可查詢
  R4. GET /status — 認證守衛 + 非 Operator 可查詢 + get_stats() 結果
  R5. 整合場景 — singleton 複用 + asyncio.to_thread 確認 + propose→observe 狀態流轉

MODULE_NOTE (English):
  Provides REST API layer tests for experiment_routes.py.
  Strategy: FastAPI TestClient + dependency override for auth, mock ExperimentLedger
  to avoid dependency on real implementation (experiment_ledger.py may not yet exist).

  Test goals:
  R1. POST /propose — auth guard + happy path + required field validation + proposed_by
  R2. POST /{id}/observe — auth guard + supporting/refuting outcomes + 404 unknown ID
  R3. GET /{id} — auth guard + happy path + 404 + non-Operator can query
  R4. GET /status — auth guard + non-Operator can query + get_stats() result
  R5. Integration — singleton reuse + asyncio.to_thread confirmed + propose→observe flow
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from unittest.mock import MagicMock, patch, call

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# PATH SETUP / 路徑設置
# ─────────────────────────────────────────────────────────────────────────────
_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

# ─────────────────────────────────────────────────────────────────────────────
# Imports / 導入
# ─────────────────────────────────────────────────────────────────────────────
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.experiment_routes as experiment_routes_module
from app.experiment_routes import router, get_experiment_ledger
from app.governance_routes import _get_auth_actor, _require_operator_role
from app.main_legacy import AuthenticatedActor


# ─────────────────────────────────────────────────────────────────────────────
# Helper actor factories / Actor 工廠函數
# ─────────────────────────────────────────────────────────────────────────────

def _operator_actor() -> AuthenticatedActor:
    """Actor with operator role. / 含 operator 角色的 actor。"""
    return AuthenticatedActor(
        actor_id="test-operator",
        actor_type="human",
        roles={"operator", "viewer"},
        scopes={"private_readonly"},
    )


def _viewer_actor() -> AuthenticatedActor:
    """Actor with only viewer role (no operator). / 僅 viewer 角色的 actor。"""
    return AuthenticatedActor(
        actor_id="test-viewer",
        actor_type="human",
        roles={"viewer"},
        scopes={"private_readonly"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Mock ledger factory / Mock 帳本工廠
# ─────────────────────────────────────────────────────────────────────────────

def _make_mock_hypothesis(
    hypothesis_id: str = "hyp-001",
    status: str = "PENDING",
    confidence: float = 0.5,
) -> MagicMock:
    """
    Create a mock Hypothesis object with to_dict().
    建立帶 to_dict() 的 mock Hypothesis 對象。
    """
    hyp = MagicMock()
    hyp.hypothesis_id = hypothesis_id
    hyp.status = status
    hyp.confidence = confidence
    hyp.to_dict.return_value = {
        "hypothesis_id": hypothesis_id,
        "status": status,
        "confidence": confidence,
        "description": "Test hypothesis",
        "strategy_name": "ma_crossover",
        "regime": "trending",
        "supporting_observations": 3,
        "refuting_observations": 1,
    }
    return hyp


def _make_mock_status_enum(value: str) -> MagicMock:
    """
    Create a mock enum-like status object with .value attribute.
    建立帶 .value 屬性的 mock 枚舉狀態對象（模擬 HypothesisStatus）。
    """
    status = MagicMock()
    status.value = value
    return status


def _make_mock_ledger(
    propose_returns: str = "hyp-001",
    observe_returns_str: str = "CONFIRMED",
    get_hypothesis_returns=None,
    get_stats_returns: dict | None = None,
    use_enum_status: bool = False,
) -> MagicMock:
    """
    Create a fully-configured mock ExperimentLedger.
    建立完整配置的 mock ExperimentLedger。

    Args:
      propose_returns       — hypothesis_id returned by propose_hypothesis()
      observe_returns_str   — status string returned by record_observation()
      get_hypothesis_returns — Hypothesis mock (None → not found)
      get_stats_returns     — dict returned by get_stats()
      use_enum_status       — if True, record_observation returns enum with .value
    """
    ledger = MagicMock()
    ledger.propose_hypothesis.return_value = propose_returns

    if use_enum_status:
        ledger.record_observation.return_value = _make_mock_status_enum(observe_returns_str)
    else:
        ledger.record_observation.return_value = observe_returns_str

    ledger.get_hypothesis.return_value = get_hypothesis_returns
    ledger.get_stats.return_value = get_stats_returns or {
        "total": 5,
        "pending": 2,
        "confirmed": 2,
        "refuted": 1,
    }
    return ledger


# ─────────────────────────────────────────────────────────────────────────────
# Test App factory / 測試應用工廠
# ─────────────────────────────────────────────────────────────────────────────

def _make_test_app(actor: AuthenticatedActor) -> FastAPI:
    """
    Create a minimal FastAPI app with experiment router and overridden auth dependency.
    建立只含實驗路由及認證依賴覆蓋的最小 FastAPI 測試應用。
    """
    app = FastAPI()
    app.include_router(router)
    # Override auth to return the given actor without token validation
    # 覆蓋認證依賴，直接返回指定 actor，無需 token 驗證
    app.dependency_overrides[_get_auth_actor] = lambda: actor
    return app


def _make_unauthed_app() -> FastAPI:
    """
    Create a FastAPI app with no auth override — simulates unauthenticated request.
    建立無認證覆蓋的 FastAPI 應用，模擬未認證請求（返回 401）。
    """
    app = FastAPI()
    app.include_router(router)
    return app


# ─────────────────────────────────────────────────────────────────────────────
# R1: POST /propose
# R1: POST /propose 路由測試
# ─────────────────────────────────────────────────────────────────────────────

class TestProposeHypothesis:
    """R1: POST /api/v1/experiments/propose tests (7 tests)."""

    def test_propose_unauthenticated_returns_401(self):
        """
        Unauthenticated request to POST /propose → 401.
        未認證請求 POST /propose → 401。
        """
        app = _make_unauthed_app()
        mock_ledger = _make_mock_ledger()
        with patch.object(experiment_routes_module, "_ledger", mock_ledger):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/api/v1/experiments/propose", json={
                "description": "RSI strategy works in trending markets",
                "strategy_name": "rsi_strategy",
            })
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"

    def test_propose_non_operator_returns_403(self):
        """
        Non-operator actor POST /propose → 403 (viewer cannot write).
        非 Operator actor POST /propose → 403（viewer 不可寫入）。
        """
        app = _make_test_app(_viewer_actor())
        mock_ledger = _make_mock_ledger()
        with patch.object(experiment_routes_module, "_ledger", mock_ledger):
            client = TestClient(app)
            resp = client.post("/api/v1/experiments/propose", json={
                "description": "RSI strategy works in trending markets",
                "strategy_name": "rsi_strategy",
            })
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"

    def test_propose_happy_path_returns_hypothesis_id(self):
        """
        Valid operator POST /propose → 200 with hypothesis_id in response.
        有效 Operator POST /propose → 200 且響應含 hypothesis_id。
        """
        app = _make_test_app(_operator_actor())
        mock_ledger = _make_mock_ledger(propose_returns="hyp-abc-123")
        with patch.object(experiment_routes_module, "_ledger", mock_ledger):
            client = TestClient(app)
            resp = client.post("/api/v1/experiments/propose", json={
                "description": "MA crossover is profitable in trending regime",
                "strategy_name": "ma_crossover",
                "regime": "trending",
            })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["hypothesis_id"] == "hyp-abc-123"
        assert data["status"] == "PENDING"

    def test_propose_calls_ledger_propose_hypothesis(self):
        """
        POST /propose invokes ledger.propose_hypothesis() with correct arguments.
        POST /propose 使用正確參數調用 ledger.propose_hypothesis()。
        """
        app = _make_test_app(_operator_actor())
        mock_ledger = _make_mock_ledger(propose_returns="hyp-xyz")
        with patch.object(experiment_routes_module, "_ledger", mock_ledger):
            client = TestClient(app)
            resp = client.post("/api/v1/experiments/propose", json={
                "description": "Grid strategy works in ranging markets",
                "strategy_name": "grid",
                "regime": "ranging",
                "min_observations": 30,
            })
        assert resp.status_code == 200
        mock_ledger.propose_hypothesis.assert_called_once()
        kwargs = mock_ledger.propose_hypothesis.call_args.kwargs
        assert kwargs["description"] == "Grid strategy works in ranging markets"
        assert kwargs["strategy_name"] == "grid"
        assert kwargs["regime"] == "ranging"
        assert kwargs["min_observations"] == 30

    def test_propose_sets_proposed_by_operator(self):
        """
        POST /propose always sets proposed_by="operator".
        POST /propose 始終將 proposed_by 設置為 "operator"。
        """
        app = _make_test_app(_operator_actor())
        mock_ledger = _make_mock_ledger()
        with patch.object(experiment_routes_module, "_ledger", mock_ledger):
            client = TestClient(app)
            client.post("/api/v1/experiments/propose", json={
                "description": "Funding arb works in high funding regime",
                "strategy_name": "funding_arb",
            })
        kwargs = mock_ledger.propose_hypothesis.call_args.kwargs
        assert kwargs["proposed_by"] == "operator", \
            f"Expected proposed_by='operator', got {kwargs.get('proposed_by')!r}"

    def test_propose_missing_required_fields_returns_422(self):
        """
        POST /propose without required 'strategy_name' field → 422 Unprocessable Entity.
        POST /propose 缺少必填字段 'strategy_name' → 422。
        """
        app = _make_test_app(_operator_actor())
        mock_ledger = _make_mock_ledger()
        with patch.object(experiment_routes_module, "_ledger", mock_ledger):
            client = TestClient(app)
            resp = client.post("/api/v1/experiments/propose", json={
                "description": "This hypothesis has no strategy_name",
                # Missing: strategy_name
            })
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"

    def test_propose_default_min_observations_is_20(self):
        """
        POST /propose without min_observations → defaults to 20.
        POST /propose 不指定 min_observations → 默認為 20。
        """
        app = _make_test_app(_operator_actor())
        mock_ledger = _make_mock_ledger()
        with patch.object(experiment_routes_module, "_ledger", mock_ledger):
            client = TestClient(app)
            client.post("/api/v1/experiments/propose", json={
                "description": "Default min_observations test",
                "strategy_name": "ma_crossover",
            })
        kwargs = mock_ledger.propose_hypothesis.call_args.kwargs
        assert kwargs["min_observations"] == 20, \
            f"Expected min_observations=20, got {kwargs.get('min_observations')}"


# ─────────────────────────────────────────────────────────────────────────────
# R2: POST /{hypothesis_id}/observe
# R2: POST /{hypothesis_id}/observe 路由測試
# ─────────────────────────────────────────────────────────────────────────────

class TestRecordObservation:
    """R2: POST /api/v1/experiments/{hypothesis_id}/observe tests (6 tests)."""

    def test_observe_unauthenticated_returns_401(self):
        """
        Unauthenticated request to POST /{id}/observe → 401.
        未認證請求 POST /{id}/observe → 401。
        """
        app = _make_unauthed_app()
        mock_ledger = _make_mock_ledger(
            get_hypothesis_returns=_make_mock_hypothesis("hyp-001"),
        )
        with patch.object(experiment_routes_module, "_ledger", mock_ledger):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/api/v1/experiments/hyp-001/observe", json={
                "outcome": "supporting",
            })
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"

    def test_observe_non_operator_returns_403(self):
        """
        Non-operator actor POST /{id}/observe → 403.
        非 Operator actor POST /{id}/observe → 403（viewer 不可寫入）。
        """
        app = _make_test_app(_viewer_actor())
        mock_ledger = _make_mock_ledger(
            get_hypothesis_returns=_make_mock_hypothesis("hyp-001"),
        )
        with patch.object(experiment_routes_module, "_ledger", mock_ledger):
            client = TestClient(app)
            resp = client.post("/api/v1/experiments/hyp-001/observe", json={
                "outcome": "supporting",
            })
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"

    def test_observe_supporting_returns_200(self):
        """
        Valid supporting observation returns 200 with updated status.
        有效支持性觀測返回 200 及更新後狀態。
        """
        app = _make_test_app(_operator_actor())
        mock_ledger = _make_mock_ledger(
            get_hypothesis_returns=_make_mock_hypothesis("hyp-001"),
            observe_returns_str="CONFIRMED",
        )
        with patch.object(experiment_routes_module, "_ledger", mock_ledger):
            client = TestClient(app)
            resp = client.post("/api/v1/experiments/hyp-001/observe", json={
                "outcome": "supporting",
            })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["hypothesis_id"] == "hyp-001"
        assert "status" in data

    def test_observe_refuting_returns_200(self):
        """
        Valid refuting observation returns 200 with REFUTED status.
        有效反駁性觀測返回 200 及 REFUTED 狀態。
        """
        app = _make_test_app(_operator_actor())
        mock_ledger = _make_mock_ledger(
            get_hypothesis_returns=_make_mock_hypothesis("hyp-002"),
            observe_returns_str="REFUTED",
        )
        with patch.object(experiment_routes_module, "_ledger", mock_ledger):
            client = TestClient(app)
            resp = client.post("/api/v1/experiments/hyp-002/observe", json={
                "outcome": "refuting",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "REFUTED" in data["status"] or data["status"] == "REFUTED"

    def test_observe_unknown_hypothesis_returns_404(self):
        """
        POST /{id}/observe with unknown hypothesis_id → 404 fail-closed.
        未知 hypothesis_id POST /{id}/observe → 404（fail-closed）。
        """
        app = _make_test_app(_operator_actor())
        # get_hypothesis returns None → hypothesis not found
        mock_ledger = _make_mock_ledger(get_hypothesis_returns=None)
        with patch.object(experiment_routes_module, "_ledger", mock_ledger):
            client = TestClient(app)
            resp = client.post("/api/v1/experiments/nonexistent-id/observe", json={
                "outcome": "supporting",
            })
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"

    def test_observe_returns_dict_with_status_field(self):
        """
        POST /{id}/observe response always contains 'status' field.
        POST /{id}/observe 響應始終包含 'status' 字段。
        """
        app = _make_test_app(_operator_actor())
        # Test with enum-like status (has .value attribute)
        # 使用枚舉類型狀態（帶 .value 屬性）測試
        mock_ledger = _make_mock_ledger(
            get_hypothesis_returns=_make_mock_hypothesis("hyp-003"),
            observe_returns_str="PENDING",
            use_enum_status=True,
        )
        with patch.object(experiment_routes_module, "_ledger", mock_ledger):
            client = TestClient(app)
            resp = client.post("/api/v1/experiments/hyp-003/observe", json={
                "outcome": "supporting",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data, "Response must contain 'status' field"
        assert isinstance(data["status"], str), "Status must be a string"


# ─────────────────────────────────────────────────────────────────────────────
# R3: GET /{hypothesis_id}
# R3: GET /{hypothesis_id} 路由測試
# ─────────────────────────────────────────────────────────────────────────────

class TestGetHypothesis:
    """R3: GET /api/v1/experiments/{hypothesis_id} tests (5 tests)."""

    def test_get_hypothesis_unauthenticated_returns_401(self):
        """
        Unauthenticated GET /{id} → 401.
        未認證 GET /{id} → 401。
        """
        app = _make_unauthed_app()
        mock_ledger = _make_mock_ledger(
            get_hypothesis_returns=_make_mock_hypothesis("hyp-001"),
        )
        with patch.object(experiment_routes_module, "_ledger", mock_ledger):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/api/v1/experiments/hyp-001")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"

    def test_get_hypothesis_returns_hypothesis_dict(self):
        """
        Authenticated GET /{id} for existing hypothesis → 200 with full dict.
        已認證 GET /{id} 查詢存在的假設 → 200 及完整字典。
        """
        app = _make_test_app(_operator_actor())
        hyp = _make_mock_hypothesis("hyp-777", status="CONFIRMED", confidence=0.8)
        mock_ledger = _make_mock_ledger(get_hypothesis_returns=hyp)
        with patch.object(experiment_routes_module, "_ledger", mock_ledger):
            client = TestClient(app)
            resp = client.get("/api/v1/experiments/hyp-777")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["hypothesis_id"] == "hyp-777"
        assert data["status"] == "CONFIRMED"
        assert data["confidence"] == 0.8

    def test_get_hypothesis_unknown_id_returns_404(self):
        """
        GET /{id} with unknown hypothesis_id → 404 fail-closed.
        未知 hypothesis_id GET /{id} → 404（fail-closed）。
        """
        app = _make_test_app(_operator_actor())
        mock_ledger = _make_mock_ledger(get_hypothesis_returns=None)
        with patch.object(experiment_routes_module, "_ledger", mock_ledger):
            client = TestClient(app)
            resp = client.get("/api/v1/experiments/does-not-exist")
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"

    def test_get_hypothesis_accessible_by_non_operator(self):
        """
        Non-operator viewer can GET /{id} — read-only endpoint requires no Operator role.
        非 Operator viewer 也可 GET /{id} — 只讀端點無需 Operator 角色。
        """
        app = _make_test_app(_viewer_actor())
        hyp = _make_mock_hypothesis("hyp-readonly", status="PENDING")
        mock_ledger = _make_mock_ledger(get_hypothesis_returns=hyp)
        with patch.object(experiment_routes_module, "_ledger", mock_ledger):
            client = TestClient(app)
            resp = client.get("/api/v1/experiments/hyp-readonly")
        assert resp.status_code == 200, \
            f"Non-operator should be able to GET hypothesis; got {resp.status_code}: {resp.text}"

    def test_get_hypothesis_response_contains_required_fields(self):
        """
        GET /{id} response dict contains hypothesis_id, status, confidence.
        GET /{id} 響應字典包含 hypothesis_id / status / confidence 字段。
        """
        app = _make_test_app(_operator_actor())
        hyp = _make_mock_hypothesis("hyp-fields", status="PENDING", confidence=0.55)
        mock_ledger = _make_mock_ledger(get_hypothesis_returns=hyp)
        with patch.object(experiment_routes_module, "_ledger", mock_ledger):
            client = TestClient(app)
            resp = client.get("/api/v1/experiments/hyp-fields")
        assert resp.status_code == 200
        data = resp.json()
        assert "hypothesis_id" in data, "Response must contain 'hypothesis_id'"
        assert "status" in data, "Response must contain 'status'"
        assert "confidence" in data, "Response must contain 'confidence'"


# ─────────────────────────────────────────────────────────────────────────────
# R4: GET /status
# R4: GET /status 路由測試
# ─────────────────────────────────────────────────────────────────────────────

class TestGetLedgerStatus:
    """R4: GET /api/v1/experiments/status tests (4 tests)."""

    def test_status_unauthenticated_returns_401(self):
        """
        Unauthenticated GET /status → 401.
        未認證 GET /status → 401。
        """
        app = _make_unauthed_app()
        mock_ledger = _make_mock_ledger()
        with patch.object(experiment_routes_module, "_ledger", mock_ledger):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/api/v1/experiments/status")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"

    def test_status_accessible_by_non_operator(self):
        """
        Non-operator viewer can GET /status — read-only endpoint.
        非 Operator viewer 也可 GET /status — 只讀端點。
        """
        app = _make_test_app(_viewer_actor())
        mock_ledger = _make_mock_ledger()
        with patch.object(experiment_routes_module, "_ledger", mock_ledger):
            client = TestClient(app)
            resp = client.get("/api/v1/experiments/status")
        assert resp.status_code == 200, \
            f"Non-operator should access /status; got {resp.status_code}: {resp.text}"

    def test_status_returns_get_stats_result(self):
        """
        GET /status returns the dict from ledger.get_stats().
        GET /status 返回 ledger.get_stats() 的字典。
        """
        app = _make_test_app(_operator_actor())
        expected_stats = {
            "total": 10,
            "pending": 4,
            "confirmed": 4,
            "refuted": 2,
            "confirmation_rate": 0.4,
        }
        mock_ledger = _make_mock_ledger(get_stats_returns=expected_stats)
        with patch.object(experiment_routes_module, "_ledger", mock_ledger):
            client = TestClient(app)
            resp = client.get("/api/v1/experiments/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 10
        assert data["pending"] == 4
        assert data["confirmed"] == 4
        assert data["refuted"] == 2

    def test_status_returns_200(self):
        """
        GET /status with authenticated actor always returns 200.
        已認證 GET /status 始終返回 200。
        """
        app = _make_test_app(_operator_actor())
        mock_ledger = _make_mock_ledger()
        with patch.object(experiment_routes_module, "_ledger", mock_ledger):
            client = TestClient(app)
            resp = client.get("/api/v1/experiments/status")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────────────────────────────────────
# R5: Integration scenarios
# R5: 整合場景測試
# ─────────────────────────────────────────────────────────────────────────────

class TestIntegrationScenarios:
    """R5: Integration tests (3 tests)."""

    def test_multiple_requests_use_same_singleton_ledger(self):
        """
        Multiple requests reuse the same ExperimentLedger singleton.
        多次請求複用同一個 ExperimentLedger 單例。

        Verifies that get_experiment_ledger() returns the same object
        across requests when _ledger is already set.
        驗證 _ledger 已設置時，get_experiment_ledger() 跨請求返回同一對象。
        """
        app = _make_test_app(_operator_actor())
        mock_ledger = _make_mock_ledger(
            propose_returns="hyp-singleton-test",
            get_hypothesis_returns=_make_mock_hypothesis("hyp-singleton-test"),
        )

        with patch.object(experiment_routes_module, "_ledger", mock_ledger):
            client = TestClient(app)

            # First request — propose
            resp1 = client.post("/api/v1/experiments/propose", json={
                "description": "Singleton test hypothesis",
                "strategy_name": "ma_crossover",
            })
            assert resp1.status_code == 200

            # Second request — get status
            resp2 = client.get("/api/v1/experiments/status")
            assert resp2.status_code == 200

            # Third request — get hypothesis
            resp3 = client.get("/api/v1/experiments/hyp-singleton-test")
            assert resp3.status_code == 200

        # All calls went through the same mock_ledger instance
        # 所有調用都通過同一個 mock_ledger 實例
        assert mock_ledger.propose_hypothesis.call_count == 1
        assert mock_ledger.get_stats.call_count == 1

    def test_asyncio_to_thread_used_for_propose(self):
        """
        Verify asyncio.to_thread is used when calling ledger.propose_hypothesis().
        驗證調用 ledger.propose_hypothesis() 時使用了 asyncio.to_thread。

        We patch asyncio.to_thread to capture calls and confirm non-blocking execution.
        通過 patch asyncio.to_thread 捕獲調用，確認非阻塞異步執行。
        """
        app = _make_test_app(_operator_actor())

        # We need a ledger in place so the route doesn't try to import ExperimentLedger
        # 需要預設 ledger，避免路由嘗試 import ExperimentLedger
        mock_ledger = _make_mock_ledger(propose_returns="hyp-thread-test")

        original_to_thread = None
        to_thread_calls = []

        async def mock_to_thread(fn, *args, **kwargs):
            to_thread_calls.append((fn, args, kwargs))
            # Actually call the function synchronously in the test
            # 在測試中同步調用函數（避免真正異步執行）
            import inspect
            if inspect.iscoroutinefunction(fn):
                return await fn(*args, **kwargs)
            return fn(*args, **kwargs)

        with patch.object(experiment_routes_module, "_ledger", mock_ledger):
            with patch("app.experiment_routes.asyncio.to_thread", side_effect=mock_to_thread):
                client = TestClient(app)
                resp = client.post("/api/v1/experiments/propose", json={
                    "description": "Thread test hypothesis",
                    "strategy_name": "grid",
                })

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        # asyncio.to_thread should have been called for propose_hypothesis
        # asyncio.to_thread 應該被調用了（用於 propose_hypothesis）
        assert len(to_thread_calls) >= 1, \
            "asyncio.to_thread should have been called at least once"

    def test_propose_then_observe_status_flow(self):
        """
        Integration: propose → observe → get shows correct state transitions.
        整合測試：propose → observe → get 顯示正確的狀態流轉。

        Simulates the full experiment lifecycle: create hypothesis, record
        supporting observation, verify status reflects the update.
        模擬完整實驗生命週期：創建假設、記錄支持性觀測、驗證狀態更新。
        """
        app = _make_test_app(_operator_actor())

        # Phase 1: After propose → hypothesis is PENDING
        # Phase 2: After observe(supporting) → hypothesis is CONFIRMED
        pending_hypothesis = _make_mock_hypothesis("hyp-lifecycle", status="PENDING")
        confirmed_hypothesis = _make_mock_hypothesis("hyp-lifecycle", status="CONFIRMED", confidence=0.75)

        # get_hypothesis returns PENDING on first call, CONFIRMED on second
        # get_hypothesis 第一次返回 PENDING，第二次返回 CONFIRMED
        mock_ledger = MagicMock()
        mock_ledger.propose_hypothesis.return_value = "hyp-lifecycle"
        mock_ledger.get_hypothesis.side_effect = [
            pending_hypothesis,   # Called during /observe pre-flight check
            confirmed_hypothesis, # Called during /get
        ]
        mock_ledger.record_observation.return_value = "CONFIRMED"
        mock_ledger.get_stats.return_value = {"total": 1, "pending": 0, "confirmed": 1, "refuted": 0}

        with patch.object(experiment_routes_module, "_ledger", mock_ledger):
            client = TestClient(app)

            # Step 1: Propose
            propose_resp = client.post("/api/v1/experiments/propose", json={
                "description": "MA crossover confirmed in trending markets",
                "strategy_name": "ma_crossover",
                "regime": "trending",
                "min_observations": 10,
            })
            assert propose_resp.status_code == 200
            assert propose_resp.json()["status"] == "PENDING"

            # Step 2: Observe (supporting)
            observe_resp = client.post("/api/v1/experiments/hyp-lifecycle/observe", json={
                "outcome": "supporting",
            })
            assert observe_resp.status_code == 200
            assert observe_resp.json()["status"] == "CONFIRMED"

            # Step 3: Get — verify updated state
            get_resp = client.get("/api/v1/experiments/hyp-lifecycle")
            assert get_resp.status_code == 200
            get_data = get_resp.json()
            assert get_data["hypothesis_id"] == "hyp-lifecycle"
            assert get_data["status"] == "CONFIRMED"
            assert get_data["confidence"] == 0.75
