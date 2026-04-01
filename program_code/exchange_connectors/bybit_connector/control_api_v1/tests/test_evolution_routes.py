"""
E4 Phase 3 Batch 3B — EvolutionRoutes API Tests
E4 Phase 3 Batch 3B — EvolutionRoutes API 測試

MODULE_NOTE (中文):
  本模塊為 evolution_routes.py 提供 REST API 層測試。
  策略：使用 FastAPI TestClient + 依賴覆蓋 override auth dependency，
  並 mock EvolutionEngine 避免依賴真實的 BacktestEngine 執行。

  測試目標：
  R1. 認證守衛 — POST /run 需要 auth；非 Operator → 403；GET /status 需要 auth
  R2. GET /status — 非 Operator 也可查詢（只讀端點）
  R3. POST /run — 正常路徑 → 200 + best_sharpe；is_simulated 永遠為 True
  R4. POST /run — 格式錯誤 parameter_grids → 422
  R5. POST /run — 引擎異常 → 500 "Internal server error"
  R6. 單例複用 — 兩次請求共享同一引擎實例

MODULE_NOTE (English):
  Provides REST API layer tests for evolution_routes.py.
  Strategy: FastAPI TestClient + dependency override for auth, mock EvolutionEngine
  to avoid depending on real BacktestEngine execution.

  Test goals:
  R1. Auth guards — POST /run requires auth; non-Operator → 403; GET /status requires auth
  R2. GET /status — non-Operator allowed (read-only endpoint)
  R3. POST /run — happy path → 200 + best_sharpe; is_simulated always True
  R4. POST /run — invalid parameter_grids format → 422
  R5. POST /run — engine exception → 500 "Internal server error"
  R6. Singleton reuse — two requests share same engine instance
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

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

import app.evolution_routes as evolution_routes_module
from app.evolution_routes import router, get_evolution_engine
from app.governance_routes import _get_auth_actor
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
# Mock EvolutionResult factory / Mock EvolutionResult 工廠
# ─────────────────────────────────────────────────────────────────────────────

def _make_mock_result(
    strategy_name: str = "ma_crossover",
    symbol: str = "BTCUSDT",
    best_sharpe: float = 1.5,
    best_win_rate: float = 0.6,
) -> MagicMock:
    """
    Create a mock EvolutionResult with to_dict().
    建立帶 to_dict() 的 mock EvolutionResult 對象。

    is_simulated is always True — mirrors the real EvolutionResult.__post_init__ guarantee.
    is_simulated 始終為 True — 鏡像真實 EvolutionResult.__post_init__ 的保證。
    """
    result = MagicMock()
    result.strategy_name = strategy_name
    result.symbol = symbol
    result.best_sharpe = best_sharpe
    result.best_win_rate = best_win_rate
    result.is_simulated = True  # Principle 7 invariant / 原則 7 不變量
    result.to_dict.return_value = {
        "strategy_name": strategy_name,
        "symbol": symbol,
        "timeframe": "1h",
        "best_params": {"stop_loss_pct": 0.02},
        "best_sharpe": best_sharpe,
        "best_win_rate": best_win_rate,
        "total_combinations": 4,
        "evaluated_combinations": 4,
        "all_results": [],
        "completed_at_ms": 1700000000000,
        # Principle 7 isolation marker / 原則 7 隔離標記
        "is_simulated": True,
    }
    return result


def _make_mock_engine(
    result: Optional[MagicMock] = None,
    status: Optional[dict] = None,
) -> MagicMock:
    """
    Create a mock EvolutionEngine with run_evolution() and get_status().
    建立帶 run_evolution() 和 get_status() 的 mock EvolutionEngine。
    """
    engine = MagicMock()
    engine.run_evolution.return_value = result or _make_mock_result()
    engine.get_status.return_value = status or {
        "total_runs": 3,
        "last_run_ts": 1700000000.0,
        "max_combinations": 50,
    }
    return engine


# ─────────────────────────────────────────────────────────────────────────────
# Test App factory / 測試應用工廠
# ─────────────────────────────────────────────────────────────────────────────

def _make_test_app(actor: AuthenticatedActor) -> FastAPI:
    """
    Create a minimal FastAPI app with evolution router and overridden auth dependency.
    建立只含進化路由及認證依賴覆蓋的最小 FastAPI 測試應用。
    """
    test_app = FastAPI()
    test_app.include_router(router)
    # Override auth to return the given actor without token validation
    # 覆蓋認證依賴，直接返回指定 actor，無需 token 驗證
    test_app.dependency_overrides[_get_auth_actor] = lambda: actor
    return test_app


def _make_unauthed_app() -> FastAPI:
    """
    Create a FastAPI app with no auth override — simulates unauthenticated request.
    建立無認證覆蓋的 FastAPI 應用，模擬未認證請求（返回 401）。
    """
    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


# ─────────────────────────────────────────────────────────────────────────────
# Shared valid request payload / 共用的有效請求 payload
# ─────────────────────────────────────────────────────────────────────────────

_VALID_RUN_BODY = {
    "strategy_name": "ma_crossover",
    "symbol": "BTCUSDT",
    "timeframe": "1h",
    "parameter_grids": [
        {"name": "stop_loss_pct", "values": [0.01, 0.02]},
        {"name": "position_size_pct", "values": [0.05, 0.10]},
    ],
    "min_sharpe": 1.0,
    "max_combinations": 50,
}


# ─────────────────────────────────────────────────────────────────────────────
# R1: Auth guard tests — POST /run
# R1: POST /run 認證守衛測試
# ─────────────────────────────────────────────────────────────────────────────

class TestRunAuthGuards:
    """R1: Authentication and authorization guards for POST /run (3 tests)."""

    def test_post_run_no_auth_returns_401(self):
        """
        No auth header on POST /run → 401.
        POST /run 無認證 header → 401。
        """
        test_app = _make_unauthed_app()
        mock_engine = _make_mock_engine()
        with patch.object(evolution_routes_module, "_evolution_engine", mock_engine):
            client = TestClient(test_app, raise_server_exceptions=False)
            resp = client.post("/api/v1/evolution/run", json=_VALID_RUN_BODY)
        assert resp.status_code == 401, (
            f"Expected 401 for unauthenticated request, got {resp.status_code}: {resp.text}"
        )

    def test_post_run_non_operator_returns_403(self):
        """
        Non-operator (viewer) actor on POST /run → 403.
        非 Operator（viewer）actor POST /run → 403（viewer 不可觸發寫入操作）。
        """
        test_app = _make_test_app(_viewer_actor())
        mock_engine = _make_mock_engine()
        with patch.object(evolution_routes_module, "_evolution_engine", mock_engine):
            client = TestClient(test_app, raise_server_exceptions=False)
            resp = client.post("/api/v1/evolution/run", json=_VALID_RUN_BODY)
        assert resp.status_code == 403, (
            f"Expected 403 for non-operator, got {resp.status_code}: {resp.text}"
        )

    def test_get_status_no_auth_returns_401(self):
        """
        No auth header on GET /status → 401.
        GET /status 無認證 header → 401。
        """
        test_app = _make_unauthed_app()
        mock_engine = _make_mock_engine()
        with patch.object(evolution_routes_module, "_evolution_engine", mock_engine):
            client = TestClient(test_app, raise_server_exceptions=False)
            resp = client.get("/api/v1/evolution/status")
        assert resp.status_code == 401, (
            f"Expected 401 for unauthenticated status request, got {resp.status_code}: {resp.text}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# R2: GET /status — non-Operator allowed
# R2: GET /status 非 Operator 可查詢
# ─────────────────────────────────────────────────────────────────────────────

class TestStatusEndpoint:
    """R2: GET /status endpoint tests (2 tests)."""

    def test_get_status_non_operator_allowed(self):
        """
        Non-operator (viewer) can query GET /status (read-only endpoint).
        非 Operator（viewer）可查詢 GET /status（只讀端點）。
        """
        test_app = _make_test_app(_viewer_actor())
        mock_engine = _make_mock_engine(status={
            "total_runs": 7,
            "last_run_ts": 1700000100.0,
            "max_combinations": 50,
        })
        with patch.object(evolution_routes_module, "_evolution_engine", mock_engine):
            client = TestClient(test_app)
            resp = client.get("/api/v1/evolution/status")
        assert resp.status_code == 200, (
            f"Expected 200 for viewer on status, got {resp.status_code}: {resp.text}"
        )

    def test_get_status_returns_total_runs(self):
        """
        GET /status response contains total_runs and max_combinations fields.
        GET /status 響應包含 total_runs 和 max_combinations 字段。
        """
        test_app = _make_test_app(_operator_actor())
        mock_engine = _make_mock_engine(status={
            "total_runs": 5,
            "last_run_ts": 1700000200.0,
            "max_combinations": 50,
        })
        with patch.object(evolution_routes_module, "_evolution_engine", mock_engine):
            client = TestClient(test_app)
            resp = client.get("/api/v1/evolution/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_runs" in data, "Response should contain 'total_runs' / 響應應包含 total_runs"
        assert "max_combinations" in data, "Response should contain 'max_combinations' / 響應應包含 max_combinations"
        assert data["total_runs"] == 5
        assert data["max_combinations"] == 50


# ─────────────────────────────────────────────────────────────────────────────
# R3: POST /run — happy path and is_simulated invariant
# R3: POST /run 正常路徑和 is_simulated 不變量
# ─────────────────────────────────────────────────────────────────────────────

class TestRunHappyPath:
    """R3: POST /run happy path tests (2 tests)."""

    def test_post_run_operator_returns_200(self):
        """
        Valid operator request to POST /run → 200, response dict contains best_sharpe.
        有效 Operator 請求 POST /run → 200，響應字典包含 best_sharpe。
        """
        test_app = _make_test_app(_operator_actor())
        mock_result = _make_mock_result(best_sharpe=1.8)
        mock_engine = _make_mock_engine(result=mock_result)
        with patch.object(evolution_routes_module, "_evolution_engine", mock_engine):
            client = TestClient(test_app)
            resp = client.post("/api/v1/evolution/run", json=_VALID_RUN_BODY)
        assert resp.status_code == 200, (
            f"Expected 200 for operator run, got {resp.status_code}: {resp.text}"
        )
        data = resp.json()
        assert "best_sharpe" in data, "Response should contain 'best_sharpe' / 響應應包含 best_sharpe"
        assert data["best_sharpe"] == 1.8

    def test_post_run_result_has_is_simulated_true(self):
        """
        POST /run response dict always has is_simulated=True (Principle 7 isolation).
        POST /run 響應字典永遠包含 is_simulated=True（原則 7 隔離標記）。
        """
        test_app = _make_test_app(_operator_actor())
        mock_engine = _make_mock_engine()
        with patch.object(evolution_routes_module, "_evolution_engine", mock_engine):
            client = TestClient(test_app)
            resp = client.post("/api/v1/evolution/run", json=_VALID_RUN_BODY)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("is_simulated") is True, (
            "Principle 7: is_simulated must always be True / "
            "原則 7：is_simulated 必須永遠為 True"
        )


# ─────────────────────────────────────────────────────────────────────────────
# R4: POST /run — invalid parameter_grids → 422
# R4: POST /run 格式錯誤 parameter_grids → 422
# ─────────────────────────────────────────────────────────────────────────────

class TestRunValidation:
    """R4: POST /run request validation tests (1 test)."""

    def test_post_run_invalid_parameter_grids_returns_422(self):
        """
        POST /run with parameter_grids missing required 'name' field → 422.
        POST /run 請求體的 parameter_grids 缺少必填 'name' 字段 → 422。
        """
        test_app = _make_test_app(_operator_actor())
        mock_engine = _make_mock_engine()
        invalid_body = {
            **_VALID_RUN_BODY,
            # Missing 'name' key — ParameterGrid construction should fail with KeyError
            # 缺少 'name' 鍵 — ParameterGrid 構造應拋出 KeyError
            "parameter_grids": [{"values": [0.01, 0.02]}],
        }
        with patch.object(evolution_routes_module, "_evolution_engine", mock_engine):
            client = TestClient(test_app, raise_server_exceptions=False)
            resp = client.post("/api/v1/evolution/run", json=invalid_body)
        assert resp.status_code == 422, (
            f"Expected 422 for invalid parameter_grids, got {resp.status_code}: {resp.text}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# R5: POST /run — engine exception → 500
# R5: POST /run 引擎異常 → 500
# ─────────────────────────────────────────────────────────────────────────────

class TestRunEngineError:
    """R5: POST /run engine exception handling (1 test)."""

    def test_post_run_engine_exception_returns_500(self):
        """
        EvolutionEngine.run_evolution() raises unexpected exception → 500 "Internal server error".
        EvolutionEngine.run_evolution() 拋出意外異常 → 500 "Internal server error"。

        Must NOT leak Python exception message to client (security boundary).
        絕不洩露 Python 異常細節給客戶端（安全邊界）。
        """
        test_app = _make_test_app(_operator_actor())
        mock_engine = _make_mock_engine()
        # Simulate an unexpected engine crash / 模擬引擎意外崩潰
        mock_engine.run_evolution.side_effect = RuntimeError("Simulated engine crash")
        with patch.object(evolution_routes_module, "_evolution_engine", mock_engine):
            client = TestClient(test_app, raise_server_exceptions=False)
            resp = client.post("/api/v1/evolution/run", json=_VALID_RUN_BODY)
        assert resp.status_code == 500, (
            f"Expected 500 for engine exception, got {resp.status_code}: {resp.text}"
        )
        data = resp.json()
        # Security: detail must be generic, not Python exception message
        # 安全：detail 必須是通用字符串，不得是 Python 異常消息
        detail = data.get("detail", "")
        assert "Internal server error" in detail, (
            f"Expected generic error message, got: {detail}"
        )
        assert "Simulated engine crash" not in detail, (
            "Python exception message must not be leaked to client / "
            "Python 異常消息不得洩露給客戶端"
        )


# ─────────────────────────────────────────────────────────────────────────────
# R6: Singleton reuse
# R6: 單例複用
# ─────────────────────────────────────────────────────────────────────────────

class TestSingletonReuse:
    """R6: Module-level singleton reuse test (1 test)."""

    def test_singleton_reuse(self):
        """
        Two calls to get_evolution_engine() return the same instance.
        兩次調用 get_evolution_engine() 返回同一個實例。

        Verifies double-check locking singleton pattern.
        驗證雙重檢查鎖單例模式。
        """
        # Reset singleton to ensure clean test / 重置單例確保測試隔離
        original = evolution_routes_module._evolution_engine
        try:
            evolution_routes_module._evolution_engine = None

            test_app = _make_test_app(_operator_actor())
            mock_result = _make_mock_result()
            mock_engine = _make_mock_engine(result=mock_result)

            with patch("app.evolution_routes.EvolutionEngine", return_value=mock_engine):
                # Two requests should share the same engine singleton
                # 兩次請求應共享同一個引擎單例
                engine_first = get_evolution_engine()
                engine_second = get_evolution_engine()
                assert engine_first is engine_second, (
                    "Two calls to get_evolution_engine() should return the same instance / "
                    "兩次調用 get_evolution_engine() 應返回同一個實例"
                )
        finally:
            # Restore original singleton state to avoid test pollution
            # 恢復原始單例狀態，避免污染其他測試
            evolution_routes_module._evolution_engine = original
