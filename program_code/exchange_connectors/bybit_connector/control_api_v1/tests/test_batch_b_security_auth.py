"""Batch B API/security hardening tests.
Batch B API / security hardening 測試。

These tests pin the shared auth and credential behavior used by the 62-finding
remediation Batch B. They avoid real services and keep secrets in tmp_path.
這些測試鎖定 62-finding Batch B 的共用 auth 與 credential 行為；不觸碰真服務。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request


_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app import auth, auth_routes_common, secret_runtime  # noqa: E402
from app import main_legacy as base  # noqa: E402
from app import gui_legacy_routes, system_legacy_routes  # noqa: E402


def _request(url: str = "http://testserver/login", headers: dict[str, str] | None = None) -> Request:
    """Build a minimal Starlette Request. / 建立最小 Starlette Request。"""
    raw_headers = [
        (k.lower().encode("latin-1"), v.encode("latin-1"))
        for k, v in (headers or {}).items()
    ]
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/login",
        "headers": raw_headers,
        "server": ("testserver", 80),
        "scheme": url.split(":", 1)[0],
        "client": ("127.0.0.1", 12345),
        "query_string": b"",
    })


def test_resolve_api_token_rejects_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    """Placeholder API token fails closed. / API token 占位值必須 fail closed。"""
    monkeypatch.setenv("OPENCLAW_API_TOKEN", "change-me")
    with pytest.raises(RuntimeError, match="placeholder"):
        auth._resolve_api_token()


def test_require_scope_and_operator_blocks_viewer_or_missing_scope() -> None:
    """Shared write gate requires both Operator role and route-family scope.
    共用寫入閘門必須同時檢查 Operator 角色與 route-family scope。
    """
    viewer = SimpleNamespace(actor_id="viewer", roles={"viewer"}, scopes={"risk:write"})
    with pytest.raises(HTTPException) as exc:
        auth.require_scope_and_operator(viewer, "risk:write")
    assert exc.value.status_code == 403

    operator_missing_scope = SimpleNamespace(actor_id="op", roles={"operator"}, scopes={"state:read"})
    with pytest.raises(HTTPException) as exc:
        auth.require_scope_and_operator(operator_missing_scope, "risk:write")
    assert exc.value.status_code == 403

    operator = SimpleNamespace(actor_id="op", roles={"operator"}, scopes={"risk:write"})
    auth.require_scope_and_operator(operator, "risk:write")


def test_auto_generated_token_is_not_printed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Auto-generation prints the file path, not the secret token value.
    自動生成時只打印檔案路徑，不打印 secret token 值。
    """
    token_file = tmp_path / "api_token"
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.delenv("OPENCLAW_API_TOKEN_STRICT", raising=False)
    monkeypatch.setenv("OPENCLAW_API_TOKEN_FILE", str(token_file))
    token = auth._resolve_api_token()
    captured = capsys.readouterr()
    assert token_file.read_text(encoding="utf-8").strip() == token
    assert token not in captured.err
    assert "Token:" not in captured.err


def test_gui_password_blank_or_placeholder_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blank/placeholder GUI password cannot issue an auth cookie.
    空白或占位 GUI password 不得簽發 auth cookie。
    """
    env_dir = tmp_path / "environment_files"
    env_dir.mkdir()
    env_file = env_dir / "gui_auth.env"
    monkeypatch.setenv("OPENCLAW_SECRETS_ROOT", str(tmp_path))

    for password in ("", "YOUR_PASSWORD", "change-me"):
        env_file.write_text(f"GUI_USERNAME=operator\nGUI_PASSWORD={password}\n", encoding="utf-8")
        auth._AUTH_CREDENTIALS = None
        with pytest.raises(HTTPException) as exc:
            auth_routes_common.load_expected_credentials()
        assert exc.value.status_code == 500


def test_cookie_secure_can_be_forced_and_proxy_trusted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cookie Secure honors explicit config and trusted proxy headers.
    Cookie Secure 必須支援顯式配置與可信 proxy header。
    """
    monkeypatch.setenv("OPENCLAW_COOKIE_SECURE", "1")
    assert auth_routes_common.should_set_secure_cookie(_request("http://testserver/login")) is True

    monkeypatch.setenv("OPENCLAW_COOKIE_SECURE", "auto")
    monkeypatch.setenv("OPENCLAW_TRUST_PROXY_HEADERS", "1")
    req = _request("http://testserver/login", {"x-forwarded-proto": "https"})
    assert auth_routes_common.should_set_secure_cookie(req) is True

    monkeypatch.delenv("OPENCLAW_TRUST_PROXY_HEADERS", raising=False)
    assert auth_routes_common.should_set_secure_cookie(_request("http://testserver/login")) is False


def test_dashboard_html_requires_server_side_auth() -> None:
    """Dashboard shells redirect unauthenticated browsers; login remains public.
    Dashboard shell 未認證時跳登入頁；login 保持公開。
    """
    app = FastAPI()
    gui_legacy_routes.register_gui_legacy_routes(app)
    client = TestClient(app)
    assert client.get("/login").status_code == 200
    console = client.get("/console", follow_redirects=False)
    assert console.status_code == 303
    assert console.headers["location"] == "/login?redirect=/console"
    trading = client.get("/trading?embed=1", follow_redirects=False)
    assert trading.status_code == 303
    assert trading.headers["location"] == "/login?redirect=/trading%3Fembed%3D1"
    headers = {"Authorization": f"Bearer {base.settings.api_token}"}
    assert client.get("/console", headers=headers).status_code == 200


def test_detailed_db_health_requires_auth() -> None:
    """Detailed DB pool health is no longer public; /healthz remains public.
    詳細 DB pool health 不再公開；/healthz 保持公開。
    """
    app = FastAPI()
    system_legacy_routes.register_system_legacy_routes(app)
    client = TestClient(app)
    assert client.get("/api/v1/healthz").status_code == 200
    assert client.get("/api/v1/health/db").status_code == 401


def test_secret_runtime_supports_file_backed_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime secrets can be passed by file path instead of process env value."""
    secret_file = tmp_path / "ipc_secret"
    secret_file.write_text("super-secret\n", encoding="utf-8")
    monkeypatch.delenv("OPENCLAW_IPC_SECRET", raising=False)
    monkeypatch.setenv("OPENCLAW_IPC_SECRET_FILE", str(secret_file))
    assert secret_runtime.get_secret_value("OPENCLAW_IPC_SECRET") == "super-secret"


def test_static_high_risk_posts_use_scope_gates() -> None:
    """Live/demo high-risk POST handlers must not regress to operator-only gates."""
    app_dir = Path(_control_api_dir) / "app"
    live_session = (app_dir / "live_session_endpoints.py").read_text(encoding="utf-8")
    live_account = (app_dir / "live_session_account_routes.py").read_text(encoding="utf-8")
    demo = (app_dir / "strategy_ai_routes.py").read_text(encoding="utf-8")
    ml = (app_dir / "ml_routes.py").read_text(encoding="utf-8")

    assert "core._require_operator(actor)" not in live_session
    assert live_session.count("_require_live_trade(actor)") >= 4
    assert live_session.count("_require_live_authority(actor)") >= 2
    assert "core._require_operator(actor)" not in live_account
    assert live_account.count("_require_live_trade(actor)") >= 2
    assert "from .governance_routes import _require_operator_role" not in demo
    assert demo.count("_require_demo_session_write(actor)") >= 6
    assert 'base.require_scope_and_operator(actor, "ml:write")' in ml


def test_static_proxy_and_secret_surfaces_are_locked_down() -> None:
    """Pin Batch B proxy header and script secret-surface regressions."""
    repo_root = Path(_control_api_dir).parents[3]
    app_main = (Path(_control_api_dir) / "app" / "main.py").read_text(encoding="utf-8")
    restart_all = (repo_root / "helper_scripts" / "restart_all.sh").read_text(encoding="utf-8")
    clean_restart = (repo_root / "helper_scripts" / "clean_restart.sh").read_text(encoding="utf-8")
    fresh_start = (repo_root / "helper_scripts" / "fresh_start.sh").read_text(encoding="utf-8")
    deploy_v017 = (repo_root / "helper_scripts" / "db" / "deploy_V017.sh").read_text(encoding="utf-8")
    deploy_v018 = (repo_root / "helper_scripts" / "db" / "deploy_V018.sh").read_text(encoding="utf-8")
    cron = (repo_root / "helper_scripts" / "cron_daily_report.sh").read_text(encoding="utf-8")
    grafana_compose = (repo_root / "docker_projects" / "monitoring_services" / "docker-compose.yml").read_text(encoding="utf-8")

    assert '"authorization"' not in app_main.partition("allowed_headers = {")[2].partition("}")[0]
    assert '"cookie"' not in app_main.partition("allowed_headers = {")[2].partition("}")[0]
    assert "OPENCLAW_DATABASE_URL_FILE" in restart_all
    assert "OPENCLAW_IPC_SECRET_FILE" in restart_all
    assert 'OPENCLAW_IPC_SECRET="${' not in restart_all
    assert 'OPENCLAW_IPC_SECRET="${' not in clean_restart
    assert 'OPENCLAW_IPC_SECRET="${' not in fresh_start
    assert 'psql "$DSN"' not in deploy_v017
    assert 'psql "$DSN"' not in deploy_v018
    assert "bot${BOT_TOKEN}" not in cron
    assert "${GRAFANA_BIND_ADDR:-127.0.0.1}" in grafana_compose
