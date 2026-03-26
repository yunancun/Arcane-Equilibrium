from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def build_client(runtime_payload: dict | None = None) -> TestClient:
    runtime_dir = Path(tempfile.mkdtemp(prefix="openclaw_runtime_bridge_"))
    state_file = runtime_dir / "state.json"
    os.environ["OPENCLAW_STATE_FILE"] = str(state_file)
    os.environ["OPENCLAW_API_TOKEN"] = "test-token"

    runtime_snapshot_file = runtime_dir / "runtime_snapshot.json"
    if runtime_payload is None:
        os.environ.pop("OPENCLAW_RUNTIME_SNAPSHOT_FILE", None)
    else:
        runtime_snapshot_file.write_text(json.dumps(runtime_payload, ensure_ascii=False), encoding="utf-8")
        os.environ["OPENCLAW_RUNTIME_SNAPSHOT_FILE"] = str(runtime_snapshot_file)

    for module_name in ["app.main", "app.main_legacy", "app.runtime_bridge", "app.main_snapshot_stable"]:
        if module_name in sys.modules:
            del sys.modules[module_name]

    main_module = importlib.import_module("app.main")
    importlib.reload(main_module)
    return TestClient(main_module.app)


def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


def test_runtime_snapshot_overlay_updates_source_context_and_facts() -> None:
    client = build_client(
        {
            "runtime_snapshot_id": "runtime:file:001",
            "runtime_snapshot_ts_ms": 1000,
            "readonly_connector_name": "bybit_prod_readonly_main",
            "rest_private_connection_state": "ready",
            "ws_private_connection_state": "degraded",
            "runtime_connection_state": "healthy",
            "account_fact_completeness_state": "partial",
            "source_snapshot_completeness_state": "partial",
            "global_runtime_facts": {
                "system_mode_fact": "shadow_only",
                "execution_state_fact": "execution_disabled",
                "runtime_last_refresh_ts_ms": 999,
                "runtime_data_freshness_state": "fresh",
            },
            "product_family_facts": {
                "spot": {
                    "exchange_permission_fact": "readonly_visible",
                    "account_permission_fact": "readonly_visible",
                },
                "perp_linear": {
                    "exchange_permission_fact": "unavailable",
                    "account_permission_fact": "unavailable",
                },
            },
        }
    )

    overview = client.get("/api/v1/system/overview", headers=auth_headers())
    assert overview.status_code == 200
    overview_payload = overview.json()
    assert overview_payload["source_context"]["pinned_runtime_snapshot_id"] == "runtime:file:001"
    assert overview_payload["source_context"]["ws_private_connection_state"] == "degraded"
    assert overview_payload["source_context"]["account_fact_completeness_state"] == "partial"
    assert overview_payload["data"]["global_runtime"]["global_mode_state"] == "shadow_only"

    product_families = client.get("/api/v1/system/product-families", headers=auth_headers())
    assert product_families.status_code == 200
    product_payload = product_families.json()
    assert product_payload["data"]["perp_linear"]["facts"]["exchange_permission_fact"] == "unavailable"
    assert product_payload["data"]["perp_linear"]["facts"]["account_permission_fact"] == "unavailable"


def test_response_snapshot_id_changes_when_runtime_snapshot_changes() -> None:
    runtime_dir = Path(tempfile.mkdtemp(prefix="openclaw_runtime_bridge_change_"))
    state_file = runtime_dir / "state.json"
    runtime_snapshot_file = runtime_dir / "runtime_snapshot.json"

    os.environ["OPENCLAW_STATE_FILE"] = str(state_file)
    os.environ["OPENCLAW_API_TOKEN"] = "test-token"
    os.environ["OPENCLAW_RUNTIME_SNAPSHOT_FILE"] = str(runtime_snapshot_file)

    runtime_snapshot_file.write_text(
        json.dumps(
            {
                "runtime_snapshot_id": "runtime:file:before",
                "runtime_snapshot_ts_ms": 1000,
                "runtime_connection_state": "healthy",
                "rest_private_connection_state": "ready",
                "ws_private_connection_state": "ready",
                "account_fact_completeness_state": "complete",
                "source_snapshot_completeness_state": "complete",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    for module_name in ["app.main", "app.main_legacy", "app.runtime_bridge", "app.main_snapshot_stable"]:
        if module_name in sys.modules:
            del sys.modules[module_name]
    main_module = importlib.import_module("app.main")
    importlib.reload(main_module)
    client = TestClient(main_module.app)

    first = client.get("/api/v1/system/overview", headers=auth_headers())
    assert first.status_code == 200
    first_payload = first.json()

    runtime_snapshot_file.write_text(
        json.dumps(
            {
                "runtime_snapshot_id": "runtime:file:after",
                "runtime_snapshot_ts_ms": 2000,
                "runtime_connection_state": "healthy",
                "rest_private_connection_state": "ready",
                "ws_private_connection_state": "ready",
                "account_fact_completeness_state": "complete",
                "source_snapshot_completeness_state": "complete",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    second = client.get("/api/v1/system/overview", headers=auth_headers())
    assert second.status_code == 200
    second_payload = second.json()

    assert first_payload["state_revision"] == second_payload["state_revision"]
    assert first_payload["snapshot_id"] != second_payload["snapshot_id"]
    assert first_payload["source_context"]["pinned_runtime_snapshot_id"] == "runtime:file:before"
    assert second_payload["source_context"]["pinned_runtime_snapshot_id"] == "runtime:file:after"


def test_control_route_returns_503_when_runtime_snapshot_marks_source_unavailable() -> None:
    client = build_client(
        {
            "runtime_snapshot_id": "runtime:file:down",
            "runtime_snapshot_ts_ms": 1000,
            "runtime_connection_state": "down",
            "rest_private_connection_state": "down",
            "ws_private_connection_state": "down",
            "account_fact_completeness_state": "missing",
            "source_snapshot_completeness_state": "missing",
        }
    )

    overview = client.get("/api/v1/system/overview", headers=auth_headers()).json()
    response = client.post(
        "/api/v1/control/demo/validate",
        headers=auth_headers(),
        json={
            "request_id": "runtime-down-validate",
            "idempotency_key": "runtime-down-validate",
            "operator_id": "demo-operator",
            "reason": "test runtime unavailable",
            "client_ts_ms": 1,
            "expected_state_revision": overview["state_revision"],
            "expected_previous_state": None,
            "payload": {},
        },
    )
    assert response.status_code == 503
