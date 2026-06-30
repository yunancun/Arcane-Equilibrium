"""Stock/ETF route registration, auth, and static GUI contract tests."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from stock_etf_route_fixtures import (
    STATIC_DIR,
    client_fail_closed,
    route_module,
    stock_etf_router,
)


def test_stock_etf_evidence_status_requires_auth() -> None:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    client = TestClient(app)

    resp = client.get("/api/v1/stock-etf/evidence-status")

    assert resp.status_code == 401


def test_stock_etf_readiness_requires_auth() -> None:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    client = TestClient(app)

    resp = client.get("/api/v1/stock-etf/readiness")

    assert resp.status_code == 401


def test_stock_etf_lane_status_requires_auth() -> None:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    client = TestClient(app)

    resp = client.get("/api/v1/stock-etf/lane-status")

    assert resp.status_code == 401


def test_stock_etf_redirect_requires_auth() -> None:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    client = TestClient(app)

    resp = client.get("/api/v1/stock-etf", follow_redirects=False)

    assert resp.status_code == 401


def test_stock_etf_openapi_exposes_stock_etf_get_only(client_fail_closed: TestClient) -> None:
    schema = client_fail_closed.get("/openapi.json").json()
    stock_paths = {
        path: set(methods)
        for path, methods in schema["paths"].items()
        if path.startswith("/api/v1/stock-etf")
    }

    assert stock_paths == {
        "/api/v1/stock-etf/account-status": {"get"},
        "/api/v1/stock-etf/authorization-status": {"get"},
        "/api/v1/stock-etf/data-foundation-status": {"get"},
        "/api/v1/stock-etf/disable-cleanup-status": {"get"},
        "/api/v1/stock-etf/evidence-status": {"get"},
        "/api/v1/stock-etf/lane-status": {"get"},
        "/api/v1/stock-etf/launch-status": {"get"},
        "/api/v1/stock-etf/paper-status": {"get"},
        "/api/v1/stock-etf/phase0-status": {"get"},
        "/api/v1/stock-etf/policy-status": {"get"},
        "/api/v1/stock-etf/readiness": {"get"},
        "/api/v1/stock-etf/reconciliation-status": {"get"},
        "/api/v1/stock-etf/release-packet-status": {"get"},
        "/api/v1/stock-etf/scorecard-status": {"get"},
        "/api/v1/stock-etf/shadow-status": {"get"},
        "/api/v1/stock-etf/universe-status": {"get"},
    }


def test_stock_etf_runtime_rejects_write_methods(client_fail_closed: TestClient) -> None:
    for path in (
        "/api/v1/stock-etf",
        "/api/v1/stock-etf/account-status",
        "/api/v1/stock-etf/authorization-status",
        "/api/v1/stock-etf/data-foundation-status",
        "/api/v1/stock-etf/disable-cleanup-status",
        "/api/v1/stock-etf/evidence-status",
        "/api/v1/stock-etf/lane-status",
        "/api/v1/stock-etf/launch-status",
        "/api/v1/stock-etf/paper-status",
        "/api/v1/stock-etf/phase0-status",
        "/api/v1/stock-etf/policy-status",
        "/api/v1/stock-etf/readiness",
        "/api/v1/stock-etf/reconciliation-status",
        "/api/v1/stock-etf/release-packet-status",
        "/api/v1/stock-etf/scorecard-status",
        "/api/v1/stock-etf/shadow-status",
        "/api/v1/stock-etf/universe-status",
    ):
        for method in ("post", "put", "patch", "delete"):
            resp = getattr(client_fail_closed, method)(path)
            assert resp.status_code == 405, f"{method.upper()} {path} returned {resp.status_code}"


def test_stock_etf_redirect_to_static_tab(client_fail_closed: TestClient) -> None:
    resp = client_fail_closed.get("/api/v1/stock-etf", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "/static/tab-stock-etf.html" in resp.headers.get("location", "")
    assert "no-store" in resp.headers["cache-control"]
    assert resp.headers["vary"] == "Authorization"


def test_stock_etf_console_tab_registered() -> None:
    console = (STATIC_DIR / "console.html").read_text(encoding="utf-8")
    assert "id: 'stock-etf'" in console
    assert "tab-stock-etf.html" in console
    assert "lane crypto_perp" in console
    assert "login_success" not in console


def test_stock_etf_router_registered_in_main_app() -> None:
    main_source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(
        encoding="utf-8"
    )
    assert "from .stock_etf_routes import stock_etf_router" in main_source
    assert "app.include_router(stock_etf_router)" in main_source


def test_stock_etf_static_tab_is_readonly_display_only() -> None:
    html_source = (STATIC_DIR / "tab-stock-etf.html").read_text(encoding="utf-8")
    phase0_js = (STATIC_DIR / "tab-stock-etf-phase0.js").read_text(
        encoding="utf-8"
    )
    release_packet_js = (STATIC_DIR / "tab-stock-etf-release-packet.js").read_text(
        encoding="utf-8"
    )
    disable_cleanup_js = (STATIC_DIR / "tab-stock-etf-disable-cleanup.js").read_text(
        encoding="utf-8"
    )
    reconciliation_js = (STATIC_DIR / "tab-stock-etf-reconciliation.js").read_text(
        encoding="utf-8"
    )
    js_source = (STATIC_DIR / "tab-stock-etf.js").read_text(encoding="utf-8")
    source = (
        html_source
        + "\n"
        + phase0_js
        + "\n"
        + release_packet_js
        + "\n"
        + disable_cleanup_js
        + "\n"
        + reconciliation_js
        + "\n"
        + js_source
    )
    assert "/api/v1/stock-etf/account-status" in source
    assert "/api/v1/stock-etf/authorization-status" in source
    assert "/api/v1/stock-etf/data-foundation-status" in source
    assert "/api/v1/stock-etf/disable-cleanup-status" in source
    assert "/api/v1/stock-etf/evidence-status" in source
    assert "/api/v1/stock-etf/lane-status" in source
    assert "/api/v1/stock-etf/launch-status" in source
    assert "/api/v1/stock-etf/paper-status" in source
    assert "/api/v1/stock-etf/phase0-status" in source
    assert "/api/v1/stock-etf/policy-status" in source
    assert "/api/v1/stock-etf/readiness" in source
    assert "/api/v1/stock-etf/reconciliation-status" in source
    assert "/api/v1/stock-etf/release-packet-status" in source
    assert "/api/v1/stock-etf/scorecard-status" in source
    assert "/api/v1/stock-etf/shadow-status" in source
    assert "/api/v1/stock-etf/universe-status" in source
    assert "tab-stock-etf-phase0.js" in html_source
    assert "tab-stock-etf-release-packet.js" in html_source
    assert "tab-stock-etf-disable-cleanup.js" in html_source
    assert "tab-stock-etf-reconciliation.js" in html_source
    assert "tab-stock-etf.js" in html_source
    assert "se-evidence-status" in source
    assert "se-evidence-body" in source
    assert "se-account-status" in source
    assert "se-account-body" in source
    assert "se-data-foundation-status" in source
    assert "se-data-foundation-body" in source
    assert "se-policy-status" in source
    assert "se-policy-body" in source
    assert "se-authorization-status" in source
    assert "se-authorization-body" in source
    assert "se-shadow-status" in source
    assert "se-shadow-body" in source
    assert "se-paper-status" in source
    assert "se-paper-body" in source
    assert "se-reconciliation-status" in source
    assert "se-reconciliation-body" in source
    assert "stock_etf_paper_shadow_reconciliation_v1" in source
    assert "expected_reconciliation_contract_id" in source
    assert "paper_shadow_link_hash_present" in source
    assert "reconciliation_writer_started" in source
    assert "fill_import_performed" in source
    assert "shadow_fill_generated" in source
    assert "paper_shadow_reconciliation_hash_present" in source
    assert "stock_etf_scorecard_derivation_v1" in source
    assert "scorecard_derivation" in source
    assert "se-scorecard-status" in source
    assert "se-scorecard-body" in source
    assert "se-launch-status" in source
    assert "se-launch-body" in source
    assert "se-phase0-status" in source
    assert "se-phase0-body" in source
    assert "se-release-packet-status" in source
    assert "se-release-packet-body" in source
    assert "se-disable-cleanup-status" in source
    assert "se-disable-cleanup-body" in source
    assert "se-universe-status" in source
    assert "se-universe-body" in source
    assert "api_allowlist" in source
    assert "se-api-allowlist-status" in source
    assert "se-api-allowlist-body" in source
    assert "ocPost(" not in source
    assert "method: 'POST'" not in source
    assert "method: \"POST\"" not in source
    assert "stock_etf.submit_paper_order" not in source
    assert "stock_etf.cancel_paper_order" not in source
    assert "localStorage" not in source
    assert "sessionStorage" not in source
