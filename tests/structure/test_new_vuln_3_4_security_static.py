from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "program_code/exchange_connectors/bybit_connector/control_api_v1/app"


class _RequestLike:
    def __init__(self, *, scheme: str = "http", headers: dict[str, str] | None = None) -> None:
        self.url = SimpleNamespace(scheme=scheme)
        self.headers = headers or {}


def test_cookie_secure_auto_treats_https_proxy_hints_as_fail_closed(monkeypatch) -> None:
    """OPS-1 P1-OPS-1-PROXY-HEADER-SPOOF-RISK（commit 65e784376）後的契約：

    proxy header 只有 operator 顯式 opt-in `OPENCLAW_TRUST_PROXY_HEADERS=1`
    才可信；未 opt-in 時完全忽略（直連 8000 的攻擊者可任意偽造
    X-Forwarded-*，不得讓不可信輸入影響安全判定），`request.url.scheme`
    為唯一真相。opt-in 後任何 HTTPS hint 一律標 Secure（fail-closed）。
    """
    from program_code.exchange_connectors.bybit_connector.control_api_v1.app.auth_routes_common import (
        should_set_secure_cookie,
    )

    monkeypatch.delenv("OPENCLAW_COOKIE_SECURE", raising=False)

    # 未 opt-in：偽造 proxy hint 對判定零影響（spoof 免疫，fail-closed 到 scheme）。
    monkeypatch.delenv("OPENCLAW_TRUST_PROXY_HEADERS", raising=False)
    assert should_set_secure_cookie(_RequestLike(scheme="https")) is True
    assert should_set_secure_cookie(_RequestLike(headers={"x-forwarded-proto": "https"})) is False
    assert should_set_secure_cookie(_RequestLike()) is False

    # 顯式 opt-in（Caddy 反代部署）：HTTPS hint 一律視為 Secure。
    monkeypatch.setenv("OPENCLAW_TRUST_PROXY_HEADERS", "1")
    assert should_set_secure_cookie(_RequestLike(scheme="https")) is True
    assert should_set_secure_cookie(_RequestLike(headers={"x-forwarded-proto": "https"})) is True
    assert should_set_secure_cookie(_RequestLike(headers={"x-forwarded-ssl": "on"})) is True
    assert should_set_secure_cookie(_RequestLike(headers={"forwarded": "for=127.0.0.1;proto=https"})) is True
    assert should_set_secure_cookie(_RequestLike(headers={"x-forwarded-proto": "http"})) is False
    assert should_set_secure_cookie(_RequestLike()) is False


def test_cookie_secure_explicit_disable_still_overrides_auto(monkeypatch) -> None:
    from program_code.exchange_connectors.bybit_connector.control_api_v1.app.auth_routes_common import (
        should_set_secure_cookie,
    )

    monkeypatch.setenv("OPENCLAW_COOKIE_SECURE", "0")
    # 開啟 proxy 信任，證明顯式 disable 連「可信 hint」也一併覆蓋。
    monkeypatch.setenv("OPENCLAW_TRUST_PROXY_HEADERS", "1")

    assert should_set_secure_cookie(_RequestLike(scheme="https")) is False
    assert should_set_secure_cookie(_RequestLike(headers={"x-forwarded-proto": "https"})) is False


def test_phase4_router_is_mounted_in_control_api_main() -> None:
    source = (APP_ROOT / "main.py").read_text(encoding="utf-8")
    phase4 = (APP_ROOT / "phase4_routes.py").read_text(encoding="utf-8")

    assert "from .phase4_routes import phase4_router" in source
    assert "app.include_router(phase4_router)" in source
    assert '@phase4_router.post("/weekly_review/approve")' in phase4
    assert '@phase4_router.post("/weekly_review/reject")' in phase4
    assert 'base.require_scope_and_operator(actor, "learning:manage")' in phase4
