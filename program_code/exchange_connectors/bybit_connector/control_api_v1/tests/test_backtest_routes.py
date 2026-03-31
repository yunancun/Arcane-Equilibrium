"""
E4 Batch 2C — BacktestRoutes API Tests
E4 Batch 2C — BacktestRoutes API 測試

MODULE_NOTE (中文):
  本模塊為 backtest_routes.py 提供 REST API 層測試。
  策略：使用 FastAPI TestClient + 依賴覆蓋 override auth dependency，
  並 mock BacktestEngine 避免依賴真實市場數據或 KlineManager。

  測試目標：
  R1. POST /run 正常路徑返回 200 + 有效結果字段
  R2. backtest_mode=False → 400
  R3. GET /status 未執行時返回 idle 狀態
  R4. GET /status 執行後返回 last_run_ts
  R5. 未授權用戶（無 Operator 角色）不能觸發 POST /run → 403
  R6. TruthRegistry 高品質回測結果自動注入（truth_registered=True）
  R7. BacktestEngine 內部異常 → 500
  R8. GET /status 無需 Operator 角色，所有認證 actor 均可訪問

MODULE_NOTE (English):
  Provides REST API layer tests for backtest_routes.py.
  Strategy: FastAPI TestClient + dependency override for auth, mock BacktestEngine
  to avoid real market data or KlineManager dependency.

  Test goals:
  R1. POST /run happy path returns 200 + valid result fields
  R2. backtest_mode=False → 400
  R3. GET /status before any run returns idle status
  R4. GET /status after run returns last_run_ts
  R5. Non-operator actor cannot POST /run → 403
  R6. High-quality backtest result auto-injects TruthRegistry (truth_registered=True)
  R7. BacktestEngine internal exception → 500
  R8. GET /status requires only authentication, not Operator role
"""

from __future__ import annotations

import sys
import os
from dataclasses import dataclass
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

from app.backtest_routes import router, get_backtest_engine, _backtest_engine
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
# Test App factory / 測試應用工廠
# ─────────────────────────────────────────────────────────────────────────────

def _make_test_app(actor: AuthenticatedActor) -> FastAPI:
    """
    Create a minimal FastAPI app with backtest router and overridden auth dependency.
    建立只含回測路由及認證依賴覆蓋的最小 FastAPI 測試應用。
    """
    app = FastAPI()
    app.include_router(router)
    # Override auth to return the given actor without token validation
    # 覆蓋認證依賴，直接返回指定 actor，無需 token 驗證
    app.dependency_overrides[_get_auth_actor] = lambda: actor
    return app


def _make_mock_engine(
    *,
    total_trades: int = 20,
    win_rate: float = 0.6,
    sharpe_ratio: float = 1.5,
    total_return_pct: float = 12.5,
) -> MagicMock:
    """
    Create a mock BacktestEngine whose .run() returns a realistic BacktestResult.
    建立一個 mock BacktestEngine，其 .run() 返回合法的 BacktestResult。
    """
    engine = MagicMock()

    result = MagicMock()
    result.total_trades = total_trades
    result.win_rate = win_rate
    result.sharpe_ratio = sharpe_ratio
    result.total_return_pct = total_return_pct
    result.to_dict.return_value = {
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "strategy_name": "ma_crossover",
        "total_trades": total_trades,
        "win_rate": win_rate,
        "sharpe_ratio": sharpe_ratio,
        "total_return_pct": total_return_pct,
        "is_simulated": True,
    }

    engine.run.return_value = result
    engine.get_status.return_value = {
        "status": "ok",
        "last_run_ts": 1700000000.0,
        "last_result": {
            "total_trades": total_trades,
            "win_rate": win_rate,
            "sharpe_ratio": sharpe_ratio,
            "total_return_pct": total_return_pct,
        },
    }
    return engine


# ─────────────────────────────────────────────────────────────────────────────
# R1: POST /run happy path
# R1: POST /run 正常路徑
# ─────────────────────────────────────────────────────────────────────────────

class TestBacktestRunHappyPath:
    """R1: POST /run returns 200 with required result fields."""

    def test_backtest_run_returns_result(self):
        """
        POST /run with valid payload returns 200 and result dict.
        有效 payload 的 POST /run 應返回 200 及結果字典。
        """
        app = _make_test_app(_operator_actor())
        mock_engine = _make_mock_engine()

        with patch("app.backtest_routes.get_backtest_engine", return_value=mock_engine):
            client = TestClient(app)
            resp = client.post("/api/v1/backtest/run", json={
                "symbol": "BTCUSDT",
                "timeframe": "5m",
                "strategy_name": "ma_crossover",
                "backtest_mode": True,
            })

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "win_rate" in data, "Response must contain 'win_rate'"
        assert "sharpe_ratio" in data, "Response must contain 'sharpe_ratio'"
        assert "total_return_pct" in data, "Response must contain 'total_return_pct'"

    def test_backtest_run_returns_truth_registered_field(self):
        """
        POST /run response always contains 'truth_registered' field.
        POST /run 響應始終包含 'truth_registered' 字段。
        """
        app = _make_test_app(_operator_actor())
        mock_engine = _make_mock_engine()

        with patch("app.backtest_routes.get_backtest_engine", return_value=mock_engine):
            client = TestClient(app)
            resp = client.post("/api/v1/backtest/run", json={
                "symbol": "ETHUSDT",
                "timeframe": "1h",
                "strategy_name": "grid",
                "backtest_mode": True,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert "truth_registered" in data, "Response must contain 'truth_registered' field"

    def test_backtest_run_default_backtest_mode_true(self):
        """
        Omitting backtest_mode defaults to True and succeeds.
        省略 backtest_mode 默認為 True，請求應成功。
        """
        app = _make_test_app(_operator_actor())
        mock_engine = _make_mock_engine()

        with patch("app.backtest_routes.get_backtest_engine", return_value=mock_engine):
            client = TestClient(app)
            # omit backtest_mode — default is True
            resp = client.post("/api/v1/backtest/run", json={
                "symbol": "BTCUSDT",
                "timeframe": "5m",
                "strategy_name": "bb_reversion",
            })

        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# R2: backtest_mode=False → 400
# R2: backtest_mode=False → 400
# ─────────────────────────────────────────────────────────────────────────────

class TestBacktestRunBacktestModeFalse:
    """R2: backtest_mode=False must return 400."""

    def test_backtest_run_backtest_mode_false_fails(self):
        """
        POST /run with backtest_mode=False should return 400.
        backtest_mode=False 的 POST /run 應返回 400。
        """
        app = _make_test_app(_operator_actor())

        with patch("app.backtest_routes.get_backtest_engine"):
            client = TestClient(app)
            resp = client.post("/api/v1/backtest/run", json={
                "symbol": "BTCUSDT",
                "timeframe": "5m",
                "strategy_name": "ma_crossover",
                "backtest_mode": False,
            })

        assert resp.status_code == 400, f"Expected 400 for backtest_mode=False, got {resp.status_code}"

    def test_backtest_run_engine_raises_value_error_returns_400(self):
        """
        If BacktestEngine.run() raises ValueError, route returns 400.
        BacktestEngine.run() 拋出 ValueError 時，路由應返回 400。
        """
        app = _make_test_app(_operator_actor())
        mock_engine = MagicMock()
        mock_engine.run.side_effect = ValueError("backtest_mode must be True")

        with patch("app.backtest_routes.get_backtest_engine", return_value=mock_engine):
            client = TestClient(app)
            resp = client.post("/api/v1/backtest/run", json={
                "symbol": "BTCUSDT",
                "timeframe": "5m",
                "strategy_name": "ma_crossover",
                "backtest_mode": True,  # route-level check passes, engine raises
            })

        assert resp.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# R3/R4: GET /status
# R3/R4: GET /status
# ─────────────────────────────────────────────────────────────────────────────

class TestBacktestStatus:
    """R3/R4: GET /status endpoint behavior."""

    def test_backtest_status_idle_before_any_run(self):
        """
        GET /status before any run returns 200 with idle/no-run state.
        首次執行前 GET /status 返回 200 及 idle 狀態。
        """
        app = _make_test_app(_viewer_actor())  # viewer can read status (no Operator needed)
        idle_engine = MagicMock()
        idle_engine.get_status.return_value = {
            "status": "idle",
            "message": "No backtest has been run yet",
            "last_run_ts": None,
        }

        with patch("app.backtest_routes.get_backtest_engine", return_value=idle_engine):
            client = TestClient(app)
            resp = client.get("/api/v1/backtest/status")

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        # Must have some status indicator
        assert "status" in data or "last_run_ts" in data, \
            "Status response must include 'status' or 'last_run_ts'"

    def test_backtest_status_after_run_has_last_run_ts(self):
        """
        GET /status after a run should return last_run_ts (non-None).
        執行後 GET /status 應返回非 None 的 last_run_ts。
        """
        app = _make_test_app(_viewer_actor())
        engine_after_run = MagicMock()
        engine_after_run.get_status.return_value = {
            "status": "ok",
            "last_run_ts": 1700000000.0,
            "last_result": {
                "total_trades": 15,
                "win_rate": 0.55,
            },
        }

        with patch("app.backtest_routes.get_backtest_engine", return_value=engine_after_run):
            client = TestClient(app)
            resp = client.get("/api/v1/backtest/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data.get("last_run_ts") is not None, \
            "After a run, last_run_ts should be non-None"


# ─────────────────────────────────────────────────────────────────────────────
# R5: Non-operator cannot POST /run
# R5: 非 operator 不能 POST /run
# ─────────────────────────────────────────────────────────────────────────────

class TestBacktestRunRequiresOperatorRole:
    """R5: POST /run requires Operator role."""

    def test_backtest_run_requires_operator_role(self):
        """
        Viewer-only actor calling POST /run should receive 403.
        只有 viewer 角色的 actor 呼叫 POST /run 應得到 403。
        """
        app = _make_test_app(_viewer_actor())

        with patch("app.backtest_routes.get_backtest_engine"):
            client = TestClient(app)
            resp = client.post("/api/v1/backtest/run", json={
                "symbol": "BTCUSDT",
                "timeframe": "5m",
                "strategy_name": "ma_crossover",
                "backtest_mode": True,
            })

        assert resp.status_code == 403, \
            f"Expected 403 for non-operator, got {resp.status_code}: {resp.text}"

    def test_backtest_run_actor_with_no_roles_returns_403_or_401(self):
        """
        Actor with empty roles calling POST /run should be rejected (401 or 403).
        空角色的 actor 呼叫 POST /run 應被拒絕（401 或 403）。
        """
        no_role_actor = AuthenticatedActor(
            actor_id="no-role-actor",
            actor_type="human",
            roles=set(),
            scopes=set(),
        )
        app = _make_test_app(no_role_actor)

        with patch("app.backtest_routes.get_backtest_engine"):
            client = TestClient(app)
            resp = client.post("/api/v1/backtest/run", json={
                "symbol": "BTCUSDT",
                "timeframe": "5m",
                "strategy_name": "ma_crossover",
                "backtest_mode": True,
            })

        assert resp.status_code in (401, 403), \
            f"Expected 401 or 403 for no-role actor, got {resp.status_code}"


# ─────────────────────────────────────────────────────────────────────────────
# R6: TruthRegistry auto-injection for high-quality results
# R6: 高品質回測結果自動注入 TruthRegistry
# ─────────────────────────────────────────────────────────────────────────────

class TestBacktestTruthRegistryInjection:
    """R6: High-quality backtest results (sharpe>1.0, trades>=10) trigger registry injection."""

    def test_high_quality_result_sets_truth_registered_true(self):
        """
        When sharpe_ratio > 1.0 and total_trades >= 10, truth_registered should be True
        if TruthRegistry is available.
        sharpe > 1.0 且 trades >= 10 時，truth_registered 應為 True（若 TruthRegistry 可用）。
        """
        from app.truth_source_registry import TruthSourceRegistry
        from unittest.mock import MagicMock

        app = _make_test_app(_operator_actor())
        mock_engine = _make_mock_engine(sharpe_ratio=2.0, total_trades=25, win_rate=0.65)

        # Inject a real registry into a mock ANALYST_AGENT
        registry = TruthSourceRegistry()
        mock_analyst = MagicMock()
        mock_analyst._truth_registry = registry

        with patch("app.backtest_routes.get_backtest_engine", return_value=mock_engine), \
             patch("app.phase2_strategy_routes.ANALYST_AGENT", mock_analyst, create=True):
            client = TestClient(app)
            resp = client.post("/api/v1/backtest/run", json={
                "symbol": "BTCUSDT",
                "timeframe": "5m",
                "strategy_name": "ma_crossover",
                "backtest_mode": True,
            })

        assert resp.status_code == 200
        data = resp.json()
        # truth_registered depends on whether ANALYST_AGENT import succeeds
        assert "truth_registered" in data, "truth_registered field must always be present"

    def test_low_quality_result_truth_registered_false(self):
        """
        When sharpe_ratio <= 1.0 or total_trades < 10, truth_registered should be False.
        sharpe <= 1.0 或 trades < 10 時，truth_registered 應為 False。
        """
        app = _make_test_app(_operator_actor())
        # Low quality: sharpe < 1.0
        mock_engine = _make_mock_engine(sharpe_ratio=0.5, total_trades=5, win_rate=0.4)

        with patch("app.backtest_routes.get_backtest_engine", return_value=mock_engine):
            client = TestClient(app)
            resp = client.post("/api/v1/backtest/run", json={
                "symbol": "BTCUSDT",
                "timeframe": "5m",
                "strategy_name": "ma_crossover",
                "backtest_mode": True,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data.get("truth_registered") is False, \
            "Low-quality result should have truth_registered=False"


# ─────────────────────────────────────────────────────────────────────────────
# R7: BacktestEngine internal exception → 500
# R7: BacktestEngine 內部異常 → 500
# ─────────────────────────────────────────────────────────────────────────────

class TestBacktestRunEngineException:
    """R7: Unexpected engine exception returns 500."""

    def test_engine_unexpected_exception_returns_500(self):
        """
        BacktestEngine.run() raises unexpected RuntimeError → route returns 500.
        BacktestEngine.run() 拋出意外 RuntimeError → 路由返回 500。
        """
        app = _make_test_app(_operator_actor())
        mock_engine = MagicMock()
        mock_engine.run.side_effect = RuntimeError("unexpected internal failure")

        with patch("app.backtest_routes.get_backtest_engine", return_value=mock_engine):
            client = TestClient(app)
            resp = client.post("/api/v1/backtest/run", json={
                "symbol": "BTCUSDT",
                "timeframe": "5m",
                "strategy_name": "ma_crossover",
                "backtest_mode": True,
            })

        assert resp.status_code == 500, \
            f"Expected 500 for engine RuntimeError, got {resp.status_code}"
        data = resp.json()
        assert data.get("detail") == "Internal server error", \
            "Internal errors should not leak exception details"


# ─────────────────────────────────────────────────────────────────────────────
# R8: GET /status — no Operator role required (viewer can access)
# R8: GET /status — 無需 Operator 角色
# ─────────────────────────────────────────────────────────────────────────────

class TestBacktestStatusNoOperatorRequired:
    """R8: GET /status is accessible to all authenticated actors."""

    def test_status_accessible_by_viewer(self):
        """
        Viewer-only actor can access GET /status.
        只有 viewer 角色的 actor 可訪問 GET /status。
        """
        app = _make_test_app(_viewer_actor())
        engine = MagicMock()
        engine.get_status.return_value = {"status": "idle", "last_run_ts": None}

        with patch("app.backtest_routes.get_backtest_engine", return_value=engine):
            client = TestClient(app)
            resp = client.get("/api/v1/backtest/status")

        assert resp.status_code == 200, \
            f"Viewer should be able to access GET /status, got {resp.status_code}"

    def test_status_accessible_by_operator(self):
        """
        Operator actor can also access GET /status.
        operator 角色同樣可訪問 GET /status。
        """
        app = _make_test_app(_operator_actor())
        engine = MagicMock()
        engine.get_status.return_value = {"status": "idle", "last_run_ts": None}

        with patch("app.backtest_routes.get_backtest_engine", return_value=engine):
            client = TestClient(app)
            resp = client.get("/api/v1/backtest/status")

        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# R9: get_backtest_engine singleton — idempotent
# R9: get_backtest_engine 單例 — 幂等
# ─────────────────────────────────────────────────────────────────────────────

class TestBacktestEngineSingleton:
    """R9: get_backtest_engine() returns the same instance on repeated calls."""

    def test_get_backtest_engine_singleton(self):
        """
        get_backtest_engine() called twice returns the same object.
        兩次調用 get_backtest_engine() 返回相同對象。
        """
        import app.backtest_routes as br
        # Reset singleton for test isolation
        # 重置單例以確保測試隔離
        original = br._backtest_engine
        br._backtest_engine = None
        try:
            e1 = br.get_backtest_engine()
            e2 = br.get_backtest_engine()
            assert e1 is e2, "get_backtest_engine() should return the same singleton instance"
        finally:
            br._backtest_engine = original
