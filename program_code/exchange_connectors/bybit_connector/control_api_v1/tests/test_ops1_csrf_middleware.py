"""OPS-1 Track B 整合測試：CSRF double-submit middleware。

覆蓋 spec §6.1 / §7.3：
  - AC-5 POST without X-CSRF-Token → 403 + reason_codes=["csrf_token_mismatch"]
  - AC-5 POST with mismatched header → 403
  - AC-6 POST with matching cookie+header → middleware pass-through
  - GET / HEAD / OPTIONS regression：完全不驗 CSRF
  - /api/v1/auth/login 豁免（login 時 csrf cookie 還沒存在）
  - /api/v1/csp/report 豁免（瀏覽器後台 POST 不可能附 token）
  - Shadow mode：OPENCLAW_CSRF_SHADOW=1 時 mismatch 也放行
"""

from __future__ import annotations

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app.csrf_middleware import (  # noqa: E402
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    CSRFMiddleware,
)


def _build_app() -> FastAPI:
    """構造一個帶 CSRFMiddleware 的最小 FastAPI app。"""
    app = FastAPI()
    app.add_middleware(CSRFMiddleware)

    @app.get("/api/v1/some_read")
    async def some_read():
        return {"ok": True}

    @app.post("/api/v1/some_write")
    async def some_write():
        return {"written": True}

    @app.post("/api/v1/auth/login")
    async def login():
        # 豁免路徑 — middleware 應該直接 pass-through
        return {"status": "ok"}

    @app.post("/api/v1/csp/report")
    async def csp_report():
        # 豁免路徑
        return {"received": True}

    return app


def test_get_request_bypasses_csrf() -> None:
    """GET 請求不驗 CSRF，無 cookie / header 也應 200。

    為什麼：GET 沒有 side effect，不存在 CSRF 風險。
    """
    client = TestClient(_build_app())
    r = client.get("/api/v1/some_read")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_post_without_csrf_cookie_or_header_returns_403() -> None:
    """寫操作完全沒帶 token → 403 + reason_codes=['csrf_token_mismatch']。"""
    client = TestClient(_build_app())
    r = client.post("/api/v1/some_write")
    assert r.status_code == 403
    body = r.json()
    assert body["detail"]["reason_codes"] == ["csrf_token_mismatch"]


def test_post_with_only_cookie_no_header_returns_403() -> None:
    """有 cookie 但沒 header → 403（double-submit 第二層失敗）。"""
    client = TestClient(_build_app())
    client.cookies.set(CSRF_COOKIE_NAME, "tok_AAAA")
    r = client.post("/api/v1/some_write")
    assert r.status_code == 403
    body = r.json()
    assert body["detail"]["reason_codes"] == ["csrf_token_mismatch"]
    assert "missing header" in body["detail"]["reason_detail"]


def test_post_with_mismatched_cookie_header_returns_403() -> None:
    """cookie 與 header 值不同 → 403。"""
    client = TestClient(_build_app())
    client.cookies.set(CSRF_COOKIE_NAME, "tok_AAAA")
    r = client.post(
        "/api/v1/some_write",
        headers={CSRF_HEADER_NAME: "tok_BBBB"},
    )
    assert r.status_code == 403
    body = r.json()
    assert body["detail"]["reason_codes"] == ["csrf_token_mismatch"]
    assert "mismatch" in body["detail"]["reason_detail"]


def test_post_with_matching_token_passes() -> None:
    """cookie 與 header 都為 'tok_XYZ' → middleware 放行，handler 回 200。"""
    client = TestClient(_build_app())
    token = "tok_match_12345"
    client.cookies.set(CSRF_COOKIE_NAME, token)
    r = client.post(
        "/api/v1/some_write",
        headers={CSRF_HEADER_NAME: token},
    )
    assert r.status_code == 200
    assert r.json() == {"written": True}


def test_login_endpoint_exempt() -> None:
    """POST /api/v1/auth/login 必豁免（登入時還沒有 oc_csrf cookie）。"""
    client = TestClient(_build_app())
    r = client.post("/api/v1/auth/login", json={"u": "x", "p": "y"})
    assert r.status_code == 200


def test_csp_report_endpoint_exempt() -> None:
    """POST /api/v1/csp/report 必豁免（瀏覽器自動 POST，無 cookie）。"""
    client = TestClient(_build_app())
    r = client.post("/api/v1/csp/report", json={"csp-report": {}})
    assert r.status_code == 200


def test_shadow_mode_lets_mismatch_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OPENCLAW_CSRF_SHADOW=1 時，mismatch 也放行（只記 warning）。

    為什麼：spec §7.2 風險 #2 緩衝期需要 shadow mode 蒐集 violation 樣本。
    """
    monkeypatch.setenv("OPENCLAW_CSRF_SHADOW", "1")
    client = TestClient(_build_app())
    r = client.post("/api/v1/some_write")
    # 完全沒 cookie / header 也應放行（200，不是 403）
    assert r.status_code == 200
    assert r.json() == {"written": True}


def test_static_prefix_exempt() -> None:
    """`/static/*` 前綴豁免（防靜態資源被誤算寫操作）。"""
    app = FastAPI()
    app.add_middleware(CSRFMiddleware)

    @app.post("/static/foo")
    async def static_post():
        return {"ok": True}

    client = TestClient(app)
    r = client.post("/static/foo")
    assert r.status_code == 200
