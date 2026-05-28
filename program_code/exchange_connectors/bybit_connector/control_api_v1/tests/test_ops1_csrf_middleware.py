"""OPS-1 Track B 整合測試：CSRF double-submit middleware。

覆蓋 spec §6.1 / §7.3：
  - AC-5 POST without X-CSRF-Token → 403 + reason_codes=["csrf_token_mismatch"]
  - AC-5 POST with mismatched header → 403
  - AC-6 POST with matching cookie+header → middleware pass-through
  - GET / HEAD / OPTIONS regression：完全不驗 CSRF
  - /api/v1/auth/login 豁免（login 時 csrf cookie 還沒存在）
  - /api/v1/csp/report 豁免（瀏覽器後台 POST 不可能附 token）
  - Shadow mode：OPENCLAW_CSRF_SHADOW=1 時 mismatch 也放行

OPS-1 round 2 (E2 returns)：
  - F-5：/api/v1/auth/logout **不再豁免**；帶 token → 200，無 token → 403
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
_repo_root = Path(_control_api_dir).parents[3]
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

    @app.post("/api/v1/auth/logout")
    async def logout():
        # OPS-1 round 2 (F-5)：logout 不再豁免，需要 token 通過 middleware 才到 handler。
        return {"status": "logged_out"}

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


# ── F-5：logout 不再豁免 ────────────────────────────────────────────────────


def test_logout_without_csrf_token_returns_403() -> None:
    """OPS-1 round 2 / F-5 Option A：/api/v1/auth/logout 從 _EXEMPT_PATHS 移除後，
    無 token 時必 403（阻擋已被 XSS 注入的同源頁面對 logout 發動 DoS 騷擾）。"""
    client = TestClient(_build_app())
    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 403
    body = r.json()
    assert body["detail"]["reason_codes"] == ["csrf_token_mismatch"]


def test_logout_with_matching_token_passes() -> None:
    """F-5：logout 帶有效 token → 走到 handler 回 200。

    為什麼這個 round-trip 重要：前端 ocLogout 鏈走 ocFetchWithCsrf 已自動補 header，
    必須驗證 logout 在 enforcing 模式下對既有 GUI 不卡。
    """
    client = TestClient(_build_app())
    token = "tok_logout_xyz"
    client.cookies.set(CSRF_COOKIE_NAME, token)
    r = client.post(
        "/api/v1/auth/logout",
        headers={CSRF_HEADER_NAME: token},
    )
    assert r.status_code == 200
    assert r.json() == {"status": "logged_out"}


# ── constant-time compare 邊界 ──────────────────────────────────────────────


def test_post_with_empty_token_strings_returns_403() -> None:
    """cookie 和 header 都是空字串 → middleware 視為 missing → 403。

    為什麼：空字串通過 hmac.compare_digest 雙端比對是 True，但邏輯上等同未帶
    token；middleware 先檢查 truthy，空字串走 `missing cookie` 分支。
    """
    client = TestClient(_build_app())
    client.cookies.set(CSRF_COOKIE_NAME, "")
    r = client.post(
        "/api/v1/some_write",
        headers={CSRF_HEADER_NAME: ""},
    )
    assert r.status_code == 403


def test_post_with_unequal_length_tokens_returns_403() -> None:
    """token 長度不同 → constant-time compare False → 403。"""
    client = TestClient(_build_app())
    client.cookies.set(CSRF_COOKIE_NAME, "short")
    r = client.post(
        "/api/v1/some_write",
        headers={CSRF_HEADER_NAME: "much_longer_token_value_aaaa"},
    )
    assert r.status_code == 403


# ── F-2：/api/v1/auth/check 自動 seed oc_csrf cookie ─────────────────────────


def test_auth_check_seeds_csrf_cookie_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OPS-1 round 2 / F-2：既有 oc_auth_token cookie 但無 oc_csrf 時，
    GET /api/v1/auth/check 應 set-cookie 補一個 oc_csrf。

    為什麼：OPS-1 deploy 前已存在 24h auth cookie 的 user，token 還沒過期但
    沒有 csrf cookie；不 seed 的話 enforcing 切換瞬間所有寫操作 403。
    """
    from app import main_legacy as _base  # noqa: E402

    client = TestClient(_base.app)
    # 模擬「已登入 + 缺 csrf cookie」的 production state
    client.cookies.set("oc_auth_token", _base.settings.api_token)
    # 此處不 set oc_csrf
    r = client.get("/api/v1/auth/check")
    assert r.status_code == 200
    assert r.json() == {"authenticated": True}
    # set-cookie header 必含 oc_csrf
    set_cookie_headers = r.headers.get_list("set-cookie") if hasattr(
        r.headers, "get_list"
    ) else r.headers.raw.__str__()
    joined = " ".join(set_cookie_headers) if isinstance(set_cookie_headers, list) else str(set_cookie_headers)
    assert "oc_csrf=" in joined, f"expected oc_csrf in Set-Cookie; got {joined!r}"


def test_auth_check_does_not_reissue_when_csrf_present() -> None:
    """F-2：已有 oc_csrf cookie 時，auth/check 不應該再 set-cookie 改寫（尊重既有 token）。"""
    from app import main_legacy as _base  # noqa: E402

    client = TestClient(_base.app)
    client.cookies.set("oc_auth_token", _base.settings.api_token)
    client.cookies.set("oc_csrf", "existing_csrf_token_xyz")
    r = client.get("/api/v1/auth/check")
    assert r.status_code == 200
    # 應不在 Set-Cookie 中重新發送 oc_csrf
    set_cookie_raw = r.headers.get("set-cookie", "")
    assert "oc_csrf=" not in set_cookie_raw, (
        f"unexpected oc_csrf re-issue: {set_cookie_raw!r}"
    )


def test_auth_check_without_auth_token_returns_401() -> None:
    """F-2 regression：無 oc_auth_token cookie 時 auth/check 必 401（即使請 csrf seed）。"""
    from app import main_legacy as _base  # noqa: E402

    client = TestClient(_base.app)
    r = client.get("/api/v1/auth/check")
    assert r.status_code == 401


# ── F-4：CSP report rate-limit + body size ──────────────────────────────────


def test_csp_report_oversize_body_returns_413(monkeypatch) -> None:
    """OPS-1 round 2 / F-4：>8KB body → 413 (tailnet 內任何設備 spam log 防護)。"""
    # 透過 main_legacy.app 直接驗（CSP report endpoint 真實註冊在那裡）
    from app import main_legacy as _base  # noqa: E402

    client = TestClient(_base.app)
    # 8KB + 1 byte payload
    over_payload = b'{"csp-report":{"x":"' + (b'a' * (8 * 1024)) + b'"}}'
    r = client.post(
        "/api/v1/csp/report",
        content=over_payload,
        headers={"Content-Type": "application/csp-report"},
    )
    assert r.status_code == 413


# ── OPS-1 enforcing cutover：7d shadow zero verify ──────────────────────────


def test_csrf_shadow_zero_verify_script_pass_and_fail(tmp_path) -> None:
    """7d shadow cutover helper：0 csrf_shadow PASS，出現 violation 則 FAIL。"""
    if not shutil.which("bash"):
        pytest.skip("bash not available")

    script = _repo_root / "helper_scripts" / "canary" / "healthchecks" / "csrf_shadow_zero_verify.sh"
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    api_log = logs_dir / "api.log"
    api_log.write_text("api boot ok\n", encoding="utf-8")
    env = os.environ.copy()
    env["OPENCLAW_DATA_DIR"] = str(tmp_path)

    result = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "csrf_shadow=0" in result.stdout

    api_log.write_text("csrf_shadow: missing header on POST /api/v1/x\n", encoding="utf-8")
    result = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert result.returncode == 1
    assert "csrf_shadow=1" in result.stdout
