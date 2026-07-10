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

# CSRF double-submit 自鑄對：main_legacy 無條件掛 CSRFMiddleware，所有 POST 需
# cookie `oc_csrf` 與 header `X-CSRF-Token` 同時存在且同值，否則 403。豁免清單
# 是源碼寫死的安全硬邊界（禁 env / 測試擴充），測試側自鑄同值對是合規通過路徑。
_CSRF_TOKEN = "test-csrf-token"


def build_client() -> TestClient:
    runtime_dir = Path(tempfile.mkdtemp(prefix="openclaw_test_runtime_stable_"))
    os.environ["OPENCLAW_STATE_FILE"] = str(runtime_dir / "state.json")
    os.environ["OPENCLAW_API_TOKEN"] = "test-token"
    os.environ.pop("OPENCLAW_RUNTIME_SNAPSHOT_FILE", None)

    for module_name in ["app.main_snapshot_stable", "app.main", "app.runtime_bridge", "app.main_legacy"]:
        if module_name in sys.modules:
            del sys.modules[module_name]

    stable_module = importlib.import_module("app.main_snapshot_stable")
    importlib.reload(stable_module)

    # 為什麼就地刷新而非擴大 sys.modules 清理：上面只刪條目時，fresh main.py 的
    # `from . import main_legacy` 走 CPython 父包屬性捷徑，拿回先行測試檔
    # （collection 期 OPENCLAW_API_TOKEN / OPENCLAW_STATE_FILE 未設 → settings
    # 落入隨機 token 與預設 state 檔）留下的同一個舊 main_legacy 模組；且 ~40 個
    # route/ops 模組在模組層 `from . import main_legacy as _base` 凍結指向它，
    # 構成單一同調實例。擴大刪除輕則 inert、重則把實例劈成新舊兩半（讀路徑
    # 401 或讀寫分家 409），還會波及主圖之外被其他測試檔 collection 期綁定的
    # 模組（app.strategist_agent 字串 patch 失效、conftest 對 app.db_pool 的
    # 進程級 prod-DB 封鎖被拆，P0 2026-06-10）。正解＝保住同調實例，重建其 env 派生
    # 狀態：settings 重讀本測試的 env、STORE 重綁本測試的 state 檔、殘留編譯
    # 快取失效。
    base = sys.modules["app.main"].base
    base.settings = base.Settings()
    base.STORE = base.JsonStateStore(base.settings.state_file_path)
    base.mark_compile_dirty()

    client = TestClient(stable_module.app)
    # CSRF cookie 半邊：與 auth_headers() 的 X-CSRF-Token 同值，middleware
    # constant-time 比對通過。
    client.cookies.set("oc_csrf", _CSRF_TOKEN)
    return client


def auth_headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer test-token",
        # CSRF header 半邊：GET 不檢查、附帶無害；POST 寫操作必需。
        "X-CSRF-Token": _CSRF_TOKEN,
    }


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
