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


def build_client() -> TestClient:
    runtime_dir = Path(tempfile.mkdtemp(prefix="openclaw_test_runtime_stable_"))
    os.environ["OPENCLAW_STATE_FILE"] = str(runtime_dir / "state.json")
    os.environ["OPENCLAW_API_TOKEN"] = "test-token"

    for module_name in ["app.main_snapshot_stable", "app.main"]:
        if module_name in sys.modules:
            del sys.modules[module_name]

    stable_module = importlib.import_module("app.main_snapshot_stable")
    importlib.reload(stable_module)
    return TestClient(stable_module.app)


def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


def get_overview(client: TestClient) -> dict:
    response = client.get("/api/v1/system/overview", headers=auth_headers())
    assert response.status_code == 200
    return response.json()


def build_envelope(request_id: str, state_revision: int, payload: dict, expected_previous_state=None) -> dict:
    return {
        "request_id": request_id,
        "idempotency_key": request_id,
        "operator_id": "demo-operator",
        "reason": "stable-entrypoint-test",
        "client_ts_ms": 1,
        "expected_state_revision": state_revision,
        "expected_previous_state": expected_previous_state,
        "payload": payload,
    }


def test_snapshot_id_is_stable_across_repeated_reads() -> None:
    client = build_client()
    first = get_overview(client)
    second = get_overview(client)

    assert first["state_revision"] == second["state_revision"]
    assert first["snapshot_id"] == second["snapshot_id"]
    assert first["snapshot_ts_ms"] == second["snapshot_ts_ms"]


def test_snapshot_id_changes_after_write() -> None:
    client = build_client()
    before = get_overview(client)

    response = client.post(
        "/api/v1/input/config-change",
        headers=auth_headers(),
        json=build_envelope(
            request_id="cfg-demo-reserved",
            state_revision=before["state_revision"],
            payload={
                "changes": [
                    {
                        "path": "global_runtime.controls.global_execution_mode_switch",
                        "value": "demo_reserved",
                    }
                ]
            },
        ),
    )
    assert response.status_code == 200

    after = get_overview(client)
    assert after["state_revision"] == before["state_revision"] + 1
    assert after["snapshot_id"] != before["snapshot_id"]


def test_demo_arm_reaches_armed_but_closed_after_demo_reserved() -> None:
    client = build_client()
    before = get_overview(client)

    response_cfg = client.post(
        "/api/v1/input/config-change",
        headers=auth_headers(),
        json=build_envelope(
            request_id="cfg-demo-reserved-2",
            state_revision=before["state_revision"],
            payload={
                "changes": [
                    {
                        "path": "global_runtime.controls.global_execution_mode_switch",
                        "value": "demo_reserved",
                    }
                ]
            },
        ),
    )
    assert response_cfg.status_code == 200

    current = get_overview(client)
    response_validate = client.post(
        "/api/v1/control/demo/validate",
        headers=auth_headers(),
        json=build_envelope(
            request_id="demo-validate-stable",
            state_revision=current["state_revision"],
            payload={},
        ),
    )
    assert response_validate.status_code == 200

    current = get_overview(client)
    response_arm = client.post(
        "/api/v1/control/demo/arm",
        headers=auth_headers(),
        json=build_envelope(
            request_id="demo-arm-stable",
            state_revision=current["state_revision"],
            expected_previous_state="closed",
            payload={"acknowledged": True},
        ),
    )
    assert response_arm.status_code == 200
    assert response_arm.json()["data"]["demo_state_switch"] == "armed_but_closed"
