"""Shared fixtures and payload builders for Stock/ETF route tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import stock_etf_routes as route_module  # noqa: E402
from app.main_legacy import AuthenticatedActor, current_actor  # noqa: E402
from app.stock_etf_routes import stock_etf_router  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parents[2] / "app" / "static"


def _viewer_actor() -> AuthenticatedActor:
    return AuthenticatedActor(
        actor_id="test-viewer",
        actor_type="human",
        roles={"viewer"},
        scopes={"private_readonly"},
    )


@pytest.fixture
def client_fail_closed() -> TestClient:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    app.dependency_overrides[current_actor] = _viewer_actor
    with patch.object(route_module, "_get_ipc", AsyncMock(return_value=None)):
        yield TestClient(app)


def _make_client_with_ipc(fake_ipc: Any) -> TestClient:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    app.dependency_overrides[current_actor] = _viewer_actor
    patcher = patch.object(route_module, "_get_ipc", AsyncMock(return_value=fake_ipc))
    patcher.start()
    client = TestClient(app)
    client._stock_etf_patcher = patcher  # type: ignore[attr-defined]
    return client


def _make_authless_client() -> TestClient:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    return TestClient(app)
