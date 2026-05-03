"""REF-20 Wave 2 P2a-S3 — replay_routes auth + concurrency cap tests.
REF-20 Wave 2 P2a-S3 — replay_routes 認證 + 並發上限測試。

MODULE_NOTE (EN):
    Hermetic 4-case suite covering V3 §12 #3 ``replay_route_auth_contract``
    acceptance binding for the 8-route Paper Replay Lab scaffold:

      Case 1: Unauthenticated POST /run → 401.
      Case 2: Authenticated + 0 active runs → POST /run accepts (200).
      Case 3: Authenticated + 1 active run for SAME actor → POST /run
              rejects with 409 + reason ``replay_per_actor_cap_exceeded``.
      Case 4: Authenticated + 1 active run for DIFFERENT actor (global
              cap=1 reached) → POST /run rejects with 409 + reason
              ``replay_global_cap_exceeded``.

    Mock fixtures only — no PG hit, no Rust IPC, no engine spawn (per
    Wave 3 dispatch §"Mock fixtures (no real DB hit per Wave 3 dispatch)").

MODULE_NOTE (中):
    封閉式 4-case 測試套件，覆蓋 V3 §12 #3 ``replay_route_auth_contract``
    acceptance binding，針對 Paper Replay Lab 的 8-route scaffold：

      Case 1：未認證 POST /run → 401。
      Case 2：已認證 + 0 active run → POST /run 接受（200）。
      Case 3：已認證 + 同 actor 已有 1 active run → POST /run 拒絕 409
              + reason ``replay_per_actor_cap_exceeded``。
      Case 4：已認證 + 其他 actor 已有 1 active run（global cap=1 已達）
              → POST /run 拒絕 409 + reason ``replay_global_cap_exceeded``。

    僅 mock fixture — 不接 PG / Rust IPC / engine（per Wave 3 dispatch
    §"Mock fixtures（no real DB hit）"）。

SPEC: REF-20 V3 §3 G3 + §6 + §12 #3
Workplan: docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
          §4 Wave 2 R20-P2a-S3
"""

from __future__ import annotations

import os
import sys

import pytest


_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import AuthenticatedActor  # noqa: E402
from app.main_legacy import current_actor  # noqa: E402
from app.replay_routes import (  # noqa: E402
    GLOBAL_ACTIVE_RUN_CAP,
    PER_ACTOR_ACTIVE_RUN_CAP,
    _ACTIVE_RUNS,
    _reset_active_runs_for_test,
    replay_router,
)


# ─── Auth-override stubs ──────────────────────────────────────────────────────


def _operator_actor_alice() -> AuthenticatedActor:
    """Build an Operator actor with replay:write scope (actor_id='alice').
    建立具 replay:write scope 的 Operator actor（actor_id='alice'）。
    """
    return AuthenticatedActor(
        actor_id="alice",
        actor_type="human",
        roles={"operator", "viewer"},
        scopes={"replay:write", "private_readonly"},
    )


def _operator_actor_bob() -> AuthenticatedActor:
    """Build a different Operator actor (actor_id='bob') for cross-actor cap test.
    建立另一個 Operator actor（actor_id='bob'）給跨 actor cap 測試。
    """
    return AuthenticatedActor(
        actor_id="bob",
        actor_type="human",
        roles={"operator", "viewer"},
        scopes={"replay:write", "private_readonly"},
    )


# ─── Pytest fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_state_around_each_test():
    """Clear in-memory active-run dict before AND after every test.
    每個 test 前後清空 in-memory active-run dict。

    Autouse to keep the four cases hermetic regardless of run order.
    autouse 確保 4 個 case 順序無關。
    """
    _reset_active_runs_for_test()
    yield
    _reset_active_runs_for_test()


def _build_client_with_actor(actor_factory) -> TestClient:
    """Build a FastAPI TestClient mounting replay_router with auth override.
    建立 FastAPI TestClient，掛 replay_router + auth override。
    """
    app = FastAPI()
    app.include_router(replay_router)
    if actor_factory is not None:
        app.dependency_overrides[current_actor] = actor_factory
    return TestClient(app)


def _build_unauth_client() -> TestClient:
    """TestClient WITHOUT auth override → ``current_actor`` runs and fails 401.
    不掛 auth override 的 TestClient → ``current_actor`` 跑完真路徑，無
    cookie / Authorization header → 401。
    """
    app = FastAPI()
    app.include_router(replay_router)
    return TestClient(app)


# ─── Test cases ───────────────────────────────────────────────────────────────


def test_unauthenticated_post_run_returns_401() -> None:
    """Case 1: Unauthenticated POST /run → 401.
    Case 1：未認證 POST /run → 401。

    The real ``current_actor`` dependency runs (no override), finds no
    cookie + no ``Authorization: Bearer`` header → raises ``HTTPException
    401`` with ``reason_codes=['unauthenticated']``.
    真實 ``current_actor`` dependency 跑（無 override），找不到 cookie +
    無 ``Authorization: Bearer`` header → raises 401 +
    ``reason_codes=['unauthenticated']``。
    """
    client = _build_unauth_client()
    resp = client.post(
        "/api/v1/replay/run",
        json={"experiment_id": "exp-2026-05-03-test"},
    )
    assert resp.status_code == 401, (
        f"expected 401 unauthenticated, got {resp.status_code}: {resp.text}"
    )
    detail = resp.json().get("detail", {})
    assert "reason_codes" in detail
    assert "unauthenticated" in detail["reason_codes"]


def test_authenticated_zero_active_run_post_run_accepts() -> None:
    """Case 2: Authenticated + 0 active run → POST /run accepts.
    Case 2：已認證 + 0 active run → POST /run 接受。

    Asserts:
      - 200 OK.
      - Response body has ``ok=true``, ``data.run_id``, ``data.experiment_id``,
        ``data.status='running'``, ``data.wiring_status`` marker present.
      - In-memory ``_ACTIVE_RUNS`` registers the actor's run after call.
    斷言：200 + run_id + status='running' + 記憶體 dict 已登記。
    """
    client = _build_client_with_actor(_operator_actor_alice)
    assert len(_ACTIVE_RUNS) == 0  # baseline
    resp = client.post(
        "/api/v1/replay/run",
        json={"experiment_id": "exp-2026-05-03-test"},
    )
    assert resp.status_code == 200, (
        f"expected 200 happy path, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["experiment_id"] == "exp-2026-05-03-test"
    assert data["status"] == "running"
    assert "run_id" in data and data["run_id"]
    # Wave 4 wiring marker must be visible to downstream consumers.
    # Wave 4 wiring marker 對下游消費者必須可見。
    assert data["wiring_status"] == "scaffold_only_no_runner_spawned"

    # In-memory state reflects the run.
    # 記憶體狀態反映該 run。
    assert "alice" in _ACTIVE_RUNS
    assert _ACTIVE_RUNS["alice"]["experiment_id"] == "exp-2026-05-03-test"
    assert _ACTIVE_RUNS["alice"]["run_id"] == data["run_id"]


def test_authenticated_per_actor_cap_returns_409() -> None:
    """Case 3: Same actor + 1 active run → POST /run rejects 409.
    Case 3：同 actor 已有 1 active run → POST /run 拒絕 409。

    Pre-seeds ``_ACTIVE_RUNS['alice']`` (simulating an in-flight run from
    a prior request), then issues a second POST /run as the same actor.
    Expect 409 + ``reason_codes=['replay_per_actor_cap_exceeded']``.
    Per-actor cap (= ``PER_ACTOR_ACTIVE_RUN_CAP``=1) takes precedence
    over global cap because the more specific reason gives downstream UI
    a clearer disambiguation.
    預先 seed ``_ACTIVE_RUNS['alice']``（模擬 in-flight run），再以同
    actor 發第二次 POST /run。預期 409 +
    ``reason_codes=['replay_per_actor_cap_exceeded']``。per-actor cap
    優先於 global cap，因為更具體的 reason 對下游 UI 更清晰。
    """
    # Pre-seed: alice already has an active run.
    # 預先 seed：alice 已有 active run。
    _ACTIVE_RUNS["alice"] = {
        "run_id": "preseed-alice-run",
        "experiment_id": "exp-preseed",
        "started_at_ms": 1_700_000_000_000,
        "manifest_hash": None,
        "idempotency_key": None,
        "actor_id": "alice",
    }
    assert len(_ACTIVE_RUNS) == PER_ACTOR_ACTIVE_RUN_CAP

    client = _build_client_with_actor(_operator_actor_alice)
    resp = client.post(
        "/api/v1/replay/run",
        json={"experiment_id": "exp-2026-05-03-second-attempt"},
    )
    assert resp.status_code == 409, (
        f"expected 409 per-actor cap, got {resp.status_code}: {resp.text}"
    )
    detail = resp.json().get("detail", {})
    assert "reason_codes" in detail
    assert "replay_per_actor_cap_exceeded" in detail["reason_codes"]
    # The pre-seeded run must still be present (caller's attempt rejected
    # without mutating state).
    # 預先 seed 的 run 仍在（被拒絕的請求不應 mutate state）。
    assert _ACTIVE_RUNS["alice"]["run_id"] == "preseed-alice-run"


def test_authenticated_global_cap_returns_409() -> None:
    """Case 4: Different actor + 1 active run globally → POST /run rejects 409.
    Case 4：另一 actor 已有 active run（global cap=1 已達）→ POST /run
    拒絕 409。

    Pre-seeds ``_ACTIVE_RUNS['alice']`` (simulating an in-flight run by
    Alice), then issues POST /run as Bob (different actor). Expect 409 +
    ``reason_codes=['replay_global_cap_exceeded']`` because Bob's
    per-actor count is 0 but the global count has already reached
    ``GLOBAL_ACTIVE_RUN_CAP=1``.
    預先 seed Alice 的 active run，再以 Bob 發 POST /run。預期 409 +
    ``reason_codes=['replay_global_cap_exceeded']``，因 Bob 個人計數=0
    但全局計數已達 ``GLOBAL_ACTIVE_RUN_CAP=1``。
    """
    # Pre-seed Alice's run.
    # 預先 seed Alice 的 run。
    _ACTIVE_RUNS["alice"] = {
        "run_id": "preseed-alice-run",
        "experiment_id": "exp-alice-preseed",
        "started_at_ms": 1_700_000_000_000,
        "manifest_hash": None,
        "idempotency_key": None,
        "actor_id": "alice",
    }
    assert len(_ACTIVE_RUNS) == GLOBAL_ACTIVE_RUN_CAP

    # Bob (different actor) tries to start a run.
    # Bob（另一 actor）試圖啟動 run。
    client = _build_client_with_actor(_operator_actor_bob)
    resp = client.post(
        "/api/v1/replay/run",
        json={"experiment_id": "exp-bob-2026-05-03"},
    )
    assert resp.status_code == 409, (
        f"expected 409 global cap, got {resp.status_code}: {resp.text}"
    )
    detail = resp.json().get("detail", {})
    assert "reason_codes" in detail
    assert "replay_global_cap_exceeded" in detail["reason_codes"]
    # Bob has NOT been registered (rejected without mutation).
    # Bob 未被登記（被拒絕的請求不 mutate state）。
    assert "bob" not in _ACTIVE_RUNS
    # Alice's run is unchanged.
    # Alice 的 run 不變。
    assert _ACTIVE_RUNS["alice"]["run_id"] == "preseed-alice-run"
