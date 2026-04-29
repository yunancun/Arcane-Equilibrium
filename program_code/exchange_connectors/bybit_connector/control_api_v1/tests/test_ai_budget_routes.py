"""AI Budget routes (Phase 4 · 4-16) — async IPC proxy smoke tests.
AI 預算路由 (Phase 4 · 4-16) — async IPC 代理煙霧測試。

MODULE_NOTE (中):
  本模組驗證 ai_budget_routes.py 的兩個端點以 ARCH-RC1 標準路徑運作：
    - GET  /api/v1/ai_budget/status  → IPC ok 回 200+ok=true，IPC 錯誤回 200+ok=false
    - POST /api/v1/ai_budget/config  → Pydantic 校驗 / await IPC / 503 / 504
  以 monkey-patch 注入 fake IPC client，無需真實 Rust engine。

MODULE_NOTE (EN):
  Smoke tests for ai_budget_routes.py verifying ARCH-RC1 standard behaviour:
    - GET  /api/v1/ai_budget/status  → 200+ok=true on IPC ack, 200+ok=false on IPC error
    - POST /api/v1/ai_budget/config  → Pydantic validation / await IPC / 503 / 504
  Monkey-patches a fake IPC client into the route module — no live engine required.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import pytest

# ─── Path setup / 路徑設置 ────────────────────────────────────────────────
_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import ai_budget_routes  # noqa: E402


# ─── Fake IPC client / 測試用假 IPC 客戶端 ────────────────────────────────

class _FakeOkClient:
    """Returns a healthy budget snapshot. / 回傳正常預算快照。"""

    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []

    async def get_ai_budget_status(self) -> dict[str, Any]:
        return {
            "config": {"local_total": 100.0, "agent_teacher": 60.0},
            "usage_mtd": {"local_total": 25.0, "agent_teacher": 15.0},
            "remaining": {"local_total": 75.0, "agent_teacher": 45.0},
            "degrade_level": "none",
            "last_refresh_ms": 1700000000000,
        }

    async def update_ai_budget_config(
        self, scope: str, monthly_usd: float, updated_by: str = "operator"
    ) -> dict[str, Any]:
        self.updates.append({
            "scope": scope,
            "monthly_usd": monthly_usd,
            "updated_by": updated_by,
        })
        return {"ok": True, "scope": scope, "monthly_usd": monthly_usd}


class _FakeRaisingClient:
    """Raises on every call. / 任何呼叫皆拋例外。"""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def get_ai_budget_status(self) -> dict[str, Any]:
        raise self._exc

    async def update_ai_budget_config(self, **_kwargs: Any) -> dict[str, Any]:
        raise self._exc


@pytest.fixture
def client() -> TestClient:
    """Mount only the AI budget router. / 只掛載 AI 預算路由。"""
    app = FastAPI()
    app.include_router(ai_budget_routes.router)
    return TestClient(app)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Bearer headers for the default test actor. / 預設測試 actor 的 Bearer header。"""
    return {"Authorization": f"Bearer {ai_budget_routes.base.settings.api_token}"}


@pytest.fixture
def patch_ok(monkeypatch: pytest.MonkeyPatch) -> _FakeOkClient:
    """Inject a healthy fake IPC client. / 注入健康的 fake IPC 客戶端。"""
    fake = _FakeOkClient()

    async def _get_fake() -> Any:
        return fake

    monkeypatch.setattr(ai_budget_routes, "_get_ipc_client", _get_fake)
    return fake


@pytest.fixture
def patch_raising(monkeypatch: pytest.MonkeyPatch):
    """Inject a fake IPC client that raises a given exception.
    注入會拋出指定例外的 fake IPC 客戶端。"""

    def _install(exc: Exception) -> None:
        fake = _FakeRaisingClient(exc)

        async def _get_fake() -> Any:
            return fake

        monkeypatch.setattr(ai_budget_routes, "_get_ipc_client", _get_fake)

    return _install


# ─── GET /status tests ────────────────────────────────────────────────────

def test_get_status_returns_200_when_ipc_ok(
    client: TestClient, patch_ok: _FakeOkClient
) -> None:
    """Healthy IPC → 200 + ok=true + populated config/usage.
    IPC 健康時回 200 + ok=true + 完整 config/usage。"""
    resp = client.get("/api/v1/ai_budget/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["config"]["local_total"] == 100.0
    assert body["usage_mtd"]["local_total"] == 25.0
    assert body["degrade_level"] == "none"
    assert body["last_refresh_ms"] == 1700000000000


def test_get_status_returns_ok_false_when_ipc_unreachable(
    client: TestClient, patch_raising
) -> None:
    """IPC raise → 200 + ok=false (degraded mode, GUI tolerates).
    IPC 拋例外時回 200 + ok=false（降級模式，GUI 可容忍）。"""
    patch_raising(ConnectionError("socket missing"))
    resp = client.get("/api/v1/ai_budget/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert "ipc_error" in (body.get("error") or "")


# ─── POST /config tests ───────────────────────────────────────────────────

def test_post_config_validates_payload(
    client: TestClient, patch_ok: _FakeOkClient, auth_headers: dict[str, str]
) -> None:
    """Missing scope → 422 (Pydantic). / 缺 scope 欄位 → 422。"""
    resp = client.post(
        "/api/v1/ai_budget/config",
        headers=auth_headers,
        json={"monthly_usd": 100.0},
    )
    assert resp.status_code == 422


def test_post_config_negative_amount_rejected(
    client: TestClient, patch_ok: _FakeOkClient, auth_headers: dict[str, str]
) -> None:
    """monthly_usd < 0 → 422 (Pydantic ge=0). / 負數 → 422。"""
    resp = client.post(
        "/api/v1/ai_budget/config",
        headers=auth_headers,
        json={"scope": "local_total", "monthly_usd": -50.0},
    )
    assert resp.status_code == 422


def test_post_config_awaits_ipc_returns_200_on_ack(
    client: TestClient, patch_ok: _FakeOkClient, auth_headers: dict[str, str]
) -> None:
    """Healthy IPC ack uses server actor for updated_by.
    IPC ack 使用伺服器認證 actor 作為 updated_by。
    """
    resp = client.post(
        "/api/v1/ai_budget/config",
        headers=auth_headers,
        json={"scope": "agent_teacher", "monthly_usd": 60.0, "updated_by": "tester"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["scope"] == "agent_teacher"
    assert body["monthly_usd"] == 60.0
    assert body["updated_by"] == ai_budget_routes.base.settings.auth_actor_id
    assert patch_ok.updates[-1]["updated_by"] == ai_budget_routes.base.settings.auth_actor_id
    assert isinstance(body["updated_at_ms"], int)
    assert body["updated_at_ms"] > 0


def test_post_config_requires_auth(client: TestClient, patch_ok: _FakeOkClient) -> None:
    """Unauthenticated write is rejected before IPC.
    未認證寫入必須在 IPC 前被拒。
    """
    resp = client.post(
        "/api/v1/ai_budget/config",
        json={"scope": "agent_teacher", "monthly_usd": 60.0},
    )
    assert resp.status_code == 401
    assert patch_ok.updates == []


def test_post_config_requires_operator_scope(
    client: TestClient,
    patch_ok: _FakeOkClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing ai_budget:write scope is rejected before IPC.
    缺少 ai_budget:write scope 時必須在 IPC 前拒絕。
    """
    monkeypatch.setattr(ai_budget_routes.base.settings, "auth_scopes", {"state:read"})
    resp = client.post(
        "/api/v1/ai_budget/config",
        headers=auth_headers,
        json={"scope": "agent_teacher", "monthly_usd": 60.0},
    )
    assert resp.status_code == 403
    assert patch_ok.updates == []


def test_post_config_returns_503_on_ipc_error(
    client: TestClient, patch_raising, auth_headers: dict[str, str]
) -> None:
    """IPC raise generic exception → 503 engine error.
    IPC 拋通用例外 → 503 engine error。"""
    patch_raising(RuntimeError("engine boom"))
    resp = client.post(
        "/api/v1/ai_budget/config",
        headers=auth_headers,
        json={"scope": "local_total", "monthly_usd": 100.0},
    )
    assert resp.status_code == 503
    assert "engine" in resp.json()["detail"].lower()


def test_post_config_returns_504_on_timeout(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, auth_headers: dict[str, str]
) -> None:
    """IPC EngineTimeoutError → 504. / IPC 逾時 → 504。"""
    from app.ipc_client import EngineTimeoutError  # noqa: PLC0415

    fake = _FakeRaisingClient(EngineTimeoutError("timeout"))

    async def _get_fake() -> Any:
        return fake

    monkeypatch.setattr(ai_budget_routes, "_get_ipc_client", _get_fake)
    resp = client.post(
        "/api/v1/ai_budget/config",
        headers=auth_headers,
        json={"scope": "local_total", "monthly_usd": 100.0},
    )
    assert resp.status_code == 504
