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


# ═══════════════════════════════════════════════════════════════════════════════
# 补充路由覆盖测试 / Supplementary route coverage tests
# ═══════════════════════════════════════════════════════════════════════════════

import uuid


def make_envelope(client, payload=None, **extra):
    rev = client.get("/api/v1/system/overview", headers=auth_headers()).json()["state_revision"]
    env = {
        "request_id": str(uuid.uuid4()),
        "idempotency_key": str(uuid.uuid4()),
        "operator_id": "demo-operator",
        "reason": "test",
        "client_ts_ms": 1,
        "expected_state_revision": rev,
        "expected_previous_state": None,
        "payload": payload or {},
    }
    env.update(extra)
    return env


class TestSupplementaryRoutes:
    """补充未覆盖路由的测试 / Tests for previously uncovered routes."""

    def test_get_capability_matrix(self):
        """GET /system/capability-matrix 返回能力矩阵 / Returns capability matrix."""
        client = build_client()
        r = client.get("/api/v1/system/capability-matrix", headers=auth_headers())
        assert r.status_code == 200
        assert "data" in r.json()

    def test_get_business_daily(self):
        """GET /system/business/daily 返回日度数据 / Returns daily business data."""
        client = build_client()
        r = client.get("/api/v1/system/business/daily", headers=auth_headers())
        assert r.status_code == 200
        assert "data" in r.json()

    def test_get_health(self):
        """GET /system/health 返回健康状态 / Returns health status."""
        client = build_client()
        r = client.get("/api/v1/system/health", headers=auth_headers())
        assert r.status_code == 200
        assert "data" in r.json()

    def test_get_learning_overview(self):
        """GET /learning/overview 返回学习总览 / Returns learning overview."""
        client = build_client()
        r = client.get("/api/v1/learning/overview", headers=auth_headers())
        assert r.status_code == 200
        assert "data" in r.json()

    def test_get_learning_hypotheses(self):
        """GET /learning/hypotheses 返回假设列表 / Returns hypotheses list."""
        client = build_client()
        r = client.get("/api/v1/learning/hypotheses", headers=auth_headers())
        assert r.status_code == 200
        assert "data" in r.json()

    def test_post_demo_enable_requires_state(self):
        """POST /control/demo/enable 需要正确的前置状态 / Requires correct previous state."""
        client = build_client()
        r = client.post(
            "/api/v1/control/demo/enable",
            headers=auth_headers(),
            json=make_envelope(client, expected_previous_state="armed_but_closed"),
        )
        # 应该返回 409（状态不匹配）或 200，不应该 404/500
        assert r.status_code in (200, 409)

    def test_post_demo_relock(self):
        """POST /control/demo/relock 需要正确的前置状态 / Requires correct previous state."""
        client = build_client()
        r = client.post(
            "/api/v1/control/demo/relock",
            headers=auth_headers(),
            json=make_envelope(client, expected_previous_state="demo_enabled"),
        )
        assert r.status_code in (200, 409)

    def test_post_recheck_j_canonical(self):
        """POST /control/recheck/j-canonical 返回检查结果 / Returns recheck result."""
        client = build_client()
        r = client.post(
            "/api/v1/control/recheck/j-canonical",
            headers=auth_headers(),
            json=make_envelope(client),
        )
        assert r.status_code == 200
        assert "data" in r.json()

    def test_post_recheck_k_canonical(self):
        """POST /control/recheck/k-canonical 返回检查结果 / Returns recheck result."""
        client = build_client()
        r = client.post(
            "/api/v1/control/recheck/k-canonical",
            headers=auth_headers(),
            json=make_envelope(client),
        )
        assert r.status_code == 200
        assert "data" in r.json()

    def test_post_recheck_j_closeout(self):
        """POST /control/recheck/j-closeout 返回检查结果 / Returns recheck result."""
        client = build_client()
        r = client.post(
            "/api/v1/control/recheck/j-closeout",
            headers=auth_headers(),
            json=make_envelope(client),
        )
        assert r.status_code == 200

    def test_post_recheck_k_closeout(self):
        """POST /control/recheck/k-closeout 返回检查结果 / Returns recheck result."""
        client = build_client()
        r = client.post(
            "/api/v1/control/recheck/k-closeout",
            headers=auth_headers(),
            json=make_envelope(client),
        )
        assert r.status_code == 200

    def test_post_input_event(self):
        """POST /input/event 接受事件录入 / Accepts event input."""
        client = build_client()
        r = client.post(
            "/api/v1/input/event",
            headers=auth_headers(),
            json=make_envelope(client, payload={"event_type": "test", "detail": "test event"}),
        )
        assert r.status_code == 200

    def test_post_input_manual_note(self):
        """POST /input/manual-note 接受手动备注 / Accepts manual note."""
        client = build_client()
        r = client.post(
            "/api/v1/input/manual-note",
            headers=auth_headers(),
            json=make_envelope(client, payload={"note": "test note"}),
        )
        assert r.status_code == 200

    def test_text_length_limit_enforced(self):
        """超长文本被拒绝 / Overly long text is rejected."""
        client = build_client()
        r = client.post(
            "/api/v1/input/observation",
            headers=auth_headers(),
            json=make_envelope(client, payload={
                "title": "x" * 300,  # 超过 200 限制
                "detail": "test",
                "category": "system",
                "confidence_level": "fact",
            }),
        )
        assert r.status_code == 400
        assert "title_too_long" in str(r.json())

    def test_hmac_token_comparison(self):
        """错误 Token 被拒绝 / Wrong token is rejected."""
        client = build_client()
        r = client.get(
            "/api/v1/system/overview",
            headers={"Authorization": "Bearer wrong-token-value"},
        )
        assert r.status_code == 401
