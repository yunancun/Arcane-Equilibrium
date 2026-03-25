from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def build_client():
    runtime_dir = Path(tempfile.mkdtemp(prefix="openclaw_test_runtime_"))
    os.environ["OPENCLAW_STATE_FILE"] = str(runtime_dir / "state.json")
    os.environ["OPENCLAW_API_TOKEN"] = "test-token"

    from app import main as main_module
    importlib.reload(main_module)
    return TestClient(main_module.app)


def auth_headers():
    return {"Authorization": "Bearer test-token"}


def test_overview_contract_shape():
    client = build_client()
    response = client.get("/api/v1/system/overview", headers=auth_headers())
    assert response.status_code == 200
    payload = response.json()
    assert payload["api_version"] == "v1"
    assert "snapshot_id" in payload
    assert "source_context" in payload
    assert payload["data"]["global_runtime"]["runtime_still_protected"] is True


def test_validate_returns_success_envelope():
    client = build_client()
    overview = client.get("/api/v1/system/overview", headers=auth_headers()).json()
    response = client.post(
        "/api/v1/control/demo/validate",
        headers=auth_headers(),
        json={
            "request_id": "r1",
            "idempotency_key": "i1",
            "operator_id": "demo-operator",
            "reason": "test validate",
            "client_ts_ms": 1,
            "expected_state_revision": overview["state_revision"],
            "expected_previous_state": None,
            "payload": {},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["action_result"] == "success"
    assert "demo_prerequisites_gate_state" in payload["data"]


def test_config_change_whitelist():
    client = build_client()
    overview = client.get("/api/v1/system/overview", headers=auth_headers()).json()
    response = client.post(
        "/api/v1/input/config-change",
        headers=auth_headers(),
        json={
            "request_id": "r2",
            "idempotency_key": "i2",
            "operator_id": "demo-operator",
            "reason": "set demo reserved",
            "client_ts_ms": 2,
            "expected_state_revision": overview["state_revision"],
            "expected_previous_state": None,
            "payload": {
                "changes": [
                    {
                        "path": "global_runtime.controls.global_execution_mode_switch",
                        "value": "demo_reserved",
                    }
                ]
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert "global_runtime.controls.global_execution_mode_switch" in payload["data"]["accepted_paths"]
