"""OPS-1 Track C 整合測試：CSP Report-Only header + /api/v1/csp/report endpoint。

覆蓋 spec §6.1：
  - AC-7 CSP report endpoint 接受 JSON → 204
  - Content-Security-Policy-Report-Only header 出現於所有回應
  - report-uri 指向 /api/v1/csp/report
  - PROXY-HEADER-SPOOF-RISK：_has_https_proxy_hint 未 enable env gate 時忽略
"""

from __future__ import annotations

import os
import sys

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app import auth_routes_common  # noqa: E402
from app import main_legacy as _base  # noqa: E402


def _request(scheme: str, headers: dict[str, str] | None = None) -> Request:
    raw = [
        (k.lower().encode("latin-1"), v.encode("latin-1"))
        for k, v in (headers or {}).items()
    ]
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/x",
        "headers": raw,
        "server": ("testserver", 80),
        "scheme": scheme,
        "client": ("127.0.0.1", 1234),
        "query_string": b"",
    })


def test_csp_report_only_header_present_on_responses() -> None:
    """所有 response 帶 Content-Security-Policy-Report-Only header。

    為什麼：spec §5.2 Wave A — 14d 影子規則蒐集 violation 樣本。
    """
    client = TestClient(_base.app)
    # /api/v1/csp/report 是 POST endpoint；用 healthz 之類的讀路徑驗 header
    # 都會經 security_headers_middleware。
    r = client.get("/api/v1/healthz")
    assert "Content-Security-Policy-Report-Only" in r.headers
    report_only = r.headers["Content-Security-Policy-Report-Only"]
    assert "report-uri /api/v1/csp/report" in report_only
    # Wave A 影子規則必砍掉 unsafe-inline（與 enforcing CSP 對比的關鍵差異）
    assert "'unsafe-inline'" not in report_only


def test_csp_report_endpoint_accepts_json_returns_204() -> None:
    """POST /api/v1/csp/report 接受瀏覽器 violation JSON → 204。"""
    client = TestClient(_base.app)
    payload = {
        "csp-report": {
            "document-uri": "https://trade-core/console",
            "violated-directive": "script-src",
            "blocked-uri": "inline",
            "source-file": "https://trade-core/static/console.html",
        }
    }
    r = client.post("/api/v1/csp/report", json=payload)
    assert r.status_code == 204


def test_csp_report_endpoint_tolerates_invalid_json() -> None:
    """瀏覽器送爛 JSON 時 endpoint 不爆 500，仍回 204。"""
    client = TestClient(_base.app)
    r = client.post(
        "/api/v1/csp/report",
        content=b"not-json-at-all",
        headers={"Content-Type": "application/csp-report"},
    )
    assert r.status_code == 204


def test_proxy_header_spoof_risk_fixed_when_env_not_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P1-OPS-1-PROXY-HEADER-SPOOF-RISK fix：未設 OPENCLAW_TRUST_PROXY_HEADERS=1
    時 _has_https_proxy_hint 必須完全忽略 proxy header，不論值多正向。
    """
    monkeypatch.delenv("OPENCLAW_TRUST_PROXY_HEADERS", raising=False)
    monkeypatch.delenv("OPENCLAW_COOKIE_SECURE", raising=False)
    # 攻擊者偽造 X-Forwarded-Proto: https 直連 8000
    req = _request("http", {"x-forwarded-proto": "https"})
    # 未 enable env gate → 必須忽略
    assert auth_routes_common._has_https_proxy_hint(req) is False
    # should_set_secure_cookie 在 auto + scheme=http + 無 trusted proxy hint = False
    monkeypatch.setenv("OPENCLAW_COOKIE_SECURE", "auto")
    assert auth_routes_common.should_set_secure_cookie(req) is False


def test_proxy_header_trusted_when_env_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OPENCLAW_TRUST_PROXY_HEADERS=1 + HTTPS hint → _has_https_proxy_hint True。

    為什麼：Caddy 反代後 operator 顯式 opt-in，是預期的 Live 部署配置。
    """
    monkeypatch.setenv("OPENCLAW_TRUST_PROXY_HEADERS", "1")
    req = _request("http", {"x-forwarded-proto": "https"})
    assert auth_routes_common._has_https_proxy_hint(req) is True
    # X-Forwarded-Ssl on 也應該認
    req2 = _request("http", {"x-forwarded-ssl": "on"})
    assert auth_routes_common._has_https_proxy_hint(req2) is True
    # Forwarded: proto=https 也應該認
    req3 = _request("http", {"forwarded": 'proto=https;by=caddy'})
    assert auth_routes_common._has_https_proxy_hint(req3) is True


def test_proxy_header_negative_or_missing_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """proxy header 缺失或值不為 https → _has_https_proxy_hint False（即使 env 開）。"""
    monkeypatch.setenv("OPENCLAW_TRUST_PROXY_HEADERS", "1")
    # 沒帶任何 proxy header
    assert auth_routes_common._has_https_proxy_hint(_request("http")) is False
    # X-Forwarded-Proto: http 不應被認
    req = _request("http", {"x-forwarded-proto": "http"})
    assert auth_routes_common._has_https_proxy_hint(req) is False


def test_proxy_headers_trusted_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    """_proxy_headers_trusted env gate 邊界值。"""
    for val in ("1", "true", "yes", "on", "TRUE", "On"):
        monkeypatch.setenv("OPENCLAW_TRUST_PROXY_HEADERS", val)
        assert auth_routes_common._proxy_headers_trusted() is True
    for val in ("0", "false", "no", "off", "", "random"):
        monkeypatch.setenv("OPENCLAW_TRUST_PROXY_HEADERS", val)
        assert auth_routes_common._proxy_headers_trusted() is False
    monkeypatch.delenv("OPENCLAW_TRUST_PROXY_HEADERS", raising=False)
    assert auth_routes_common._proxy_headers_trusted() is False
