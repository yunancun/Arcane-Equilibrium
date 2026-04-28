"""
G3-02 Phase C — POST /api/v1/executor/shadow-toggle route tests.
G3-02 Phase C — POST /api/v1/executor/shadow-toggle 路由測試。

MODULE_NOTE (EN):
  Verifies the operator-facing shadow_mode flip endpoint:
    1. Auth gate matrix (engine × direction).
    2. IPC dispatch shape on success.
    3. 403 + structured `gate_failed` payload on denial.
    4. Audit log entry written for both success + denial.
    5. Concurrent flip race-free at the IPC layer (mocked).

  Mock boundary:
    - `current_actor` Depends → injected via FastAPI dependency_overrides.
    - `one_shot_ipc_call` (the only real IPC call) → patched module-level.
    - `_change_audit_log` → tracked via a recorder injected through hub.

  We exercise the route via FastAPI TestClient against a freshly-built
  ``FastAPI`` app that includes only ``executor_router`` (no need to spin up
  the full main_legacy stack). Operator role check still runs because we
  inject a real-shaped actor object via dependency_overrides.

MODULE_NOTE (中):
  G3-02 Phase C 路由整合測試；使用最小 FastAPI app + dependency_overrides 注入
  actor，不依賴完整 main_legacy 啟動。

Coverage map (per task spec ~15-20 cases):
  TestEngineWhitelist:
    - test_invalid_engine_returns_400
  TestOperatorRoleGate:
    - test_no_operator_role_returns_403
  TestRetreatToShadow:
    - test_retreat_demo_succeeds_for_operator
    - test_retreat_live_succeeds_for_operator_no_live_gate
  TestDemoShadowToLive:
    - test_demo_shadow_to_live_operator_only_succeeds
  TestPaperShadowToLive:
    - test_paper_shadow_to_live_operator_only_succeeds
  TestLiveShadowToLiveGateChain:
    - test_live_flip_no_global_mode_403_live_reserved
    - test_live_flip_no_authorization_json_403_authorization
    - test_live_flip_expired_authorization_403_authorization_expired
    - test_live_flip_no_mainnet_env_403_mainnet_env
    - test_live_flip_missing_secret_slot_403_secret_slot
    - test_live_flip_all_gates_green_succeeds
  TestIpcDispatchShape:
    - test_success_calls_patch_risk_config_with_executor_subpatch
    - test_ipc_failure_returns_500
  TestAuditLog:
    - test_success_writes_audit_log_entry
    - test_denial_writes_audit_log_entry
  TestConcurrent:
    - test_back_to_back_flips_each_invoke_ipc
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

# ── Path setup / 路径设置 ─────────────────────────────────────────────────────
_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import executor_routes


# ── Fake actor (mirrors AuthenticatedActor duck-type) ────────────────────────


@dataclass
class _FakeActor:
    """Mirror AuthenticatedActor's duck-typed shape (actor_id + roles).
    對齊 AuthenticatedActor duck-type（actor_id + roles）。"""

    actor_id: str = "test-operator"
    roles: set[str] | None = None

    def __post_init__(self) -> None:
        if self.roles is None:
            self.roles = {"operator", "viewer"}


def _operator_actor() -> _FakeActor:
    return _FakeActor(actor_id="demo-operator", roles={"operator", "viewer"})


def _viewer_actor() -> _FakeActor:
    return _FakeActor(actor_id="viewer-only", roles={"viewer"})


def _make_app(actor: _FakeActor) -> FastAPI:
    """Build a minimal FastAPI app with executor_router + actor override.
    建構最小 FastAPI app：只掛 executor_router，並覆寫 current_actor。

    SINGLETON-POLLUTION-EXECUTOR-SHADOW-TOGGLE-API fix (Option A, test fixture):
      Sibling `test_api_contract.py::build_client` runs `importlib.reload(main_legacy)`
      which rebinds `main_legacy.current_actor` to a *new* function object. The
      original `executor_routes.executor_router` was built before the reload,
      so its `Depends(base.current_actor)` holds the *old* callable. Without
      mitigation, `dependency_overrides[base.current_actor]` (which after reload
      resolves to the *new* callable) fails to match → override silently bypassed
      → 401 unauthorized instead of expected 400/200.

      Fix: reload `executor_routes` itself inside `_make_app` so the router is
      rebuilt against whatever `main_legacy.current_actor` is currently bound,
      and the test-side `base.current_actor` lookup matches.
      鏡 W3 SINGLETON Option A pattern（test fixture defense-in-depth），不動
      production code（route 建構期 freeze Depends 是 FastAPI 標準語意）。
    """
    import importlib
    from app import executor_routes as _executor_routes_mod
    importlib.reload(_executor_routes_mod)

    app = FastAPI()
    app.include_router(_executor_routes_mod.executor_router)

    # Override main_legacy.current_actor — the route uses Depends(base.current_actor).
    # 覆寫 main_legacy.current_actor — route 透過 Depends(base.current_actor) 使用。
    from app import main_legacy as base
    app.dependency_overrides[base.current_actor] = lambda: actor
    return app


# ── Audit log recorder ───────────────────────────────────────────────────────


class _AuditRecorder:
    """Capture record_change calls so tests can assert on them.
    記錄 record_change 呼叫供測試斷言。"""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def record_change(self, **kwargs: Any) -> None:
        self.entries.append(kwargs)


def _patch_audit_hub(audit: _AuditRecorder):
    """Patch `_get_governance_hub` to return a hub whose `_change_audit_log` is
    our recorder. Returns the patcher so caller can stop() it.
    Patch _get_governance_hub 回傳帶錄音器的 hub。
    """
    fake_hub = MagicMock()
    fake_hub._change_audit_log = audit
    return patch(
        "app.governance_routes._get_governance_hub",
        return_value=fake_hub,
    )


# ── HMAC + authorization.json helpers ────────────────────────────────────────


def _build_signed_authorization(
    *,
    secret: str,
    expires_at_ms: int,
    operator_id: str = "test-op",
    env_allowed: list[str] | None = None,
    tier: str = "T0_ENTRY",
    version: int = 2,
    approved_system_mode: str = "live_reserved",
    issued_at_ms: int | None = None,
) -> dict[str, Any]:
    """Build a signed authorization.json record (matches Rust canonical_payload).
    建構簽名 authorization.json 記錄（對齊 Rust canonical_payload）。"""
    if env_allowed is None:
        env_allowed = ["live_demo"]
    if issued_at_ms is None:
        issued_at_ms = int(time.time() * 1000)
    envs_sorted = sorted(set(env_allowed))
    if version == 1:
        payload = f"{version}|{tier}|{issued_at_ms}|{expires_at_ms}|{operator_id}|{','.join(envs_sorted)}"
    else:
        payload = (
            f"{version}|{tier}|{issued_at_ms}|{expires_at_ms}|{operator_id}|"
            f"{approved_system_mode}|{','.join(envs_sorted)}"
        )
    sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "version": version,
        "tier": tier,
        "issued_at_ms": issued_at_ms,
        "expires_at_ms": expires_at_ms,
        "operator_id": operator_id,
        **({} if version == 1 else {"approved_system_mode": approved_system_mode}),
        "env_allowed": env_allowed,
        "sig": sig,
    }


def _write_secret_slot(
    tmpdir: Path,
    *,
    api_key: str | None = "k",
    api_secret: str | None = "s",
    bybit_endpoint: str = "demo",
    authorization_record: dict[str, Any] | None = None,
) -> Path:
    """Set up $OPENCLAW_SECRETS_DIR/live/* contents for a test run.
    為測試建立 secret slot 內容；回傳指向 OPENCLAW_SECRETS_DIR 的根目錄。"""
    slot_dir = tmpdir / "secret_files" / "bybit" / "live"
    slot_dir.mkdir(parents=True, exist_ok=True)
    if api_key is not None:
        (slot_dir / "api_key").write_text(api_key, encoding="utf-8")
    if api_secret is not None:
        (slot_dir / "api_secret").write_text(api_secret, encoding="utf-8")
    (slot_dir / "bybit_endpoint").write_text(bybit_endpoint, encoding="utf-8")
    if authorization_record is not None:
        (slot_dir / "authorization.json").write_text(
            json.dumps(authorization_record), encoding="utf-8",
        )
    # OPENCLAW_SECRETS_DIR points at .../secret_files/bybit  per env semantics.
    # OPENCLAW_SECRETS_DIR 指向 .../secret_files/bybit。
    return tmpdir / "secret_files" / "bybit"


# ─────────────────────────────────────────────────────────────────────────────
# Engine whitelist
# ─────────────────────────────────────────────────────────────────────────────


class TestEngineWhitelist(unittest.TestCase):

    def test_invalid_engine_returns_400(self) -> None:
        app = _make_app(_operator_actor())
        client = TestClient(app)
        resp = client.post(
            "/api/v1/executor/shadow-toggle",
            json={"engine": "evil; DROP TABLE", "shadow_mode": True},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid engine", resp.json()["detail"])


# ─────────────────────────────────────────────────────────────────────────────
# Operator role gate (always required)
# ─────────────────────────────────────────────────────────────────────────────


class TestOperatorRoleGate(unittest.TestCase):

    def test_no_operator_role_returns_403(self) -> None:
        app = _make_app(_viewer_actor())
        client = TestClient(app)
        # Even retreat (cheap) requires Operator role.
        # 即使 retreat（便宜）也需 Operator 角色。
        resp = client.post(
            "/api/v1/executor/shadow-toggle",
            json={"engine": "demo", "shadow_mode": True},
        )
        self.assertEqual(resp.status_code, 403)


# ─────────────────────────────────────────────────────────────────────────────
# Retreat to shadow (always cheap — Operator role only)
# ─────────────────────────────────────────────────────────────────────────────


class TestRetreatToShadow(unittest.TestCase):

    def test_retreat_demo_succeeds_for_operator(self) -> None:
        app = _make_app(_operator_actor())
        client = TestClient(app)
        with patch(
            "app.executor_routes.one_shot_ipc_call",
            new=AsyncMock(return_value={"version": 42, "applied": True}),
        ):
            resp = client.post(
                "/api/v1/executor/shadow-toggle",
                json={"engine": "demo", "shadow_mode": True},
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["applied"]["shadow_mode"], True)
        self.assertEqual(body["engine"], "demo")
        self.assertEqual(body["version"], 42)

    def test_retreat_live_succeeds_for_operator_no_live_gate(self) -> None:
        """Even retreating live → shadow needs only Operator role (safe direction)."""
        app = _make_app(_operator_actor())
        client = TestClient(app)
        with patch(
            "app.executor_routes.one_shot_ipc_call",
            new=AsyncMock(return_value={"version": 99}),
        ):
            resp = client.post(
                "/api/v1/executor/shadow-toggle",
                json={"engine": "live", "shadow_mode": True},
            )
        self.assertEqual(resp.status_code, 200, resp.text)


# ─────────────────────────────────────────────────────────────────────────────
# Demo shadow→live: Operator role only
# ─────────────────────────────────────────────────────────────────────────────


class TestDemoShadowToLive(unittest.TestCase):

    def test_demo_shadow_to_live_operator_only_succeeds(self) -> None:
        app = _make_app(_operator_actor())
        client = TestClient(app)
        with patch(
            "app.executor_routes.one_shot_ipc_call",
            new=AsyncMock(return_value={"version": 5}),
        ):
            resp = client.post(
                "/api/v1/executor/shadow-toggle",
                json={"engine": "demo", "shadow_mode": False},
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["applied"]["shadow_mode"], False)


# ─────────────────────────────────────────────────────────────────────────────
# Paper shadow→live: Operator role only
# ─────────────────────────────────────────────────────────────────────────────


class TestPaperShadowToLive(unittest.TestCase):

    def test_paper_shadow_to_live_operator_only_succeeds(self) -> None:
        app = _make_app(_operator_actor())
        client = TestClient(app)
        with patch(
            "app.executor_routes.one_shot_ipc_call",
            new=AsyncMock(return_value={"version": 1}),
        ):
            resp = client.post(
                "/api/v1/executor/shadow-toggle",
                json={"engine": "paper", "shadow_mode": False},
            )
        self.assertEqual(resp.status_code, 200, resp.text)


# ─────────────────────────────────────────────────────────────────────────────
# Live shadow→live: full 5-gate chain
# ─────────────────────────────────────────────────────────────────────────────


class TestLiveShadowToLiveGateChain(unittest.TestCase):

    def setUp(self) -> None:
        # Always start with a valid Operator actor — gate 1 passes.
        # 起點：Operator actor — 第 1 道過。
        self.app = _make_app(_operator_actor())
        self.client = TestClient(self.app)

    def _post(self) -> Any:
        return self.client.post(
            "/api/v1/executor/shadow-toggle",
            json={"engine": "live", "shadow_mode": False},
        )

    def test_live_flip_no_global_mode_403_live_reserved(self) -> None:
        """Gate 2 fail: global_mode_state is not exactly live_reserved."""
        with patch(
            "app.live_session_routes._get_global_mode_state",
            return_value="paper_only",
        ):
            resp = self._post()
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"]["gate_failed"], "live_reserved")

    def test_live_flip_live_substring_mode_403_live_reserved(self) -> None:
        """Gate 2 must reject live-ish modes such as live_demo."""
        with patch(
            "app.live_session_routes._get_global_mode_state",
            return_value="live_demo",
        ):
            resp = self._post()
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"]["gate_failed"], "live_reserved")

    def test_live_flip_no_authorization_json_403_authorization(self) -> None:
        """Gate 5 fail: authorization.json missing."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            secrets_root = _write_secret_slot(
                tmp_path,
                api_key="k",
                api_secret="s",
                bybit_endpoint="demo",  # avoids gate 3
                authorization_record=None,  # missing
            )
            with patch.dict(os.environ, {
                "OPENCLAW_SECRETS_DIR": str(secrets_root),
                "OPENCLAW_IPC_SECRET": "test-secret",
            }), patch(
                "app.live_session_routes._get_global_mode_state",
                return_value="live_reserved",
            ):
                resp = self._post()
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"]["gate_failed"], "authorization")

    def test_live_flip_expired_authorization_403_authorization_expired(self) -> None:
        """Gate 5 fail: authorization.json expired."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            secret = "test-secret"
            expired = int(time.time() * 1000) - 60_000  # 1 min in the past
            record = _build_signed_authorization(
                secret=secret,
                expires_at_ms=expired,
                env_allowed=["live_demo"],
            )
            secrets_root = _write_secret_slot(
                tmp_path,
                bybit_endpoint="demo",
                authorization_record=record,
            )
            with patch.dict(os.environ, {
                "OPENCLAW_SECRETS_DIR": str(secrets_root),
                "OPENCLAW_IPC_SECRET": secret,
            }), patch(
                "app.live_session_routes._get_global_mode_state",
                return_value="live_reserved",
            ):
                resp = self._post()
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"]["gate_failed"], "authorization_expired")

    def test_live_flip_v1_authorization_403_authorization_schema(self) -> None:
        """Gate 5 fail: stale v1 authorization must not satisfy Python gate."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            secret = "test-secret"
            future_ms = int(time.time() * 1000) + 24 * 3600 * 1000
            record = _build_signed_authorization(
                secret=secret,
                expires_at_ms=future_ms,
                env_allowed=["live_demo"],
                version=1,
            )
            secrets_root = _write_secret_slot(
                tmp_path,
                bybit_endpoint="demo",
                authorization_record=record,
            )
            with patch.dict(os.environ, {
                "OPENCLAW_SECRETS_DIR": str(secrets_root),
                "OPENCLAW_IPC_SECRET": secret,
            }), patch(
                "app.live_session_routes._get_global_mode_state",
                return_value="live_reserved",
            ):
                resp = self._post()
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"]["gate_failed"], "authorization_schema")

    def test_live_flip_wrong_authorized_mode_403_authorization_schema(self) -> None:
        """Gate 5 fail: schema v2 auth must bind approved_system_mode=live_reserved."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            secret = "test-secret"
            future_ms = int(time.time() * 1000) + 24 * 3600 * 1000
            record = _build_signed_authorization(
                secret=secret,
                expires_at_ms=future_ms,
                env_allowed=["live_demo"],
                approved_system_mode="demo_reserved",
            )
            secrets_root = _write_secret_slot(
                tmp_path,
                bybit_endpoint="demo",
                authorization_record=record,
            )
            with patch.dict(os.environ, {
                "OPENCLAW_SECRETS_DIR": str(secrets_root),
                "OPENCLAW_IPC_SECRET": secret,
            }), patch(
                "app.live_session_routes._get_global_mode_state",
                return_value="live_reserved",
            ):
                resp = self._post()
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"]["gate_failed"], "authorization_schema")

    def test_live_flip_no_mainnet_env_403_mainnet_env(self) -> None:
        """Gate 3 fail: bybit_endpoint=mainnet but OPENCLAW_ALLOW_MAINNET unset."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            secrets_root = _write_secret_slot(
                tmp_path,
                bybit_endpoint="mainnet",
            )
            env_overrides = {"OPENCLAW_SECRETS_DIR": str(secrets_root)}
            # Make sure OPENCLAW_ALLOW_MAINNET is not set in this test.
            # 測試中刻意不設置 OPENCLAW_ALLOW_MAINNET。
            env_overrides["OPENCLAW_ALLOW_MAINNET"] = ""
            with patch.dict(os.environ, env_overrides), patch(
                "app.live_session_routes._get_global_mode_state",
                return_value="live_reserved",
            ):
                resp = self._post()
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"]["gate_failed"], "mainnet_env")

    def test_live_flip_missing_secret_slot_403_secret_slot(self) -> None:
        """Gate 4 fail: api_key file empty / missing."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            secrets_root = _write_secret_slot(
                tmp_path,
                api_key=None,  # missing
                api_secret="s",
                bybit_endpoint="demo",
            )
            with patch.dict(os.environ, {
                "OPENCLAW_SECRETS_DIR": str(secrets_root),
                "OPENCLAW_IPC_SECRET": "test-secret",
            }), patch(
                "app.live_session_routes._get_global_mode_state",
                return_value="live_reserved",
            ):
                resp = self._post()
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"]["gate_failed"], "secret_slot")

    def test_live_flip_all_gates_green_succeeds(self) -> None:
        """All 5 gates green → 200 + IPC dispatched."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            secret = "test-secret"
            future_ms = int(time.time() * 1000) + 24 * 3600 * 1000
            record = _build_signed_authorization(
                secret=secret,
                expires_at_ms=future_ms,
                env_allowed=["live_demo"],
            )
            secrets_root = _write_secret_slot(
                tmp_path,
                bybit_endpoint="demo",  # → "live_demo" label, no mainnet env
                authorization_record=record,
            )
            with patch.dict(os.environ, {
                "OPENCLAW_SECRETS_DIR": str(secrets_root),
                "OPENCLAW_IPC_SECRET": secret,
            }), patch(
                "app.live_session_routes._get_global_mode_state",
                return_value="live_reserved",
            ), patch(
                "app.executor_routes.one_shot_ipc_call",
                new=AsyncMock(return_value={"version": 7}),
            ):
                resp = self._post()
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["applied"]["shadow_mode"], False)
        self.assertEqual(body["engine"], "live")


# ─────────────────────────────────────────────────────────────────────────────
# IPC dispatch shape
# ─────────────────────────────────────────────────────────────────────────────


class TestIpcDispatchShape(unittest.TestCase):

    def test_success_calls_patch_risk_config_with_executor_subpatch(self) -> None:
        """Verify Phase A IPC contract: method=patch_risk_config + executor sub-patch.
        驗證 Phase A IPC 契約：method=patch_risk_config 且 patch.executor 子欄位。"""
        app = _make_app(_operator_actor())
        client = TestClient(app)
        ipc_mock = AsyncMock(return_value={"version": 11})
        with patch("app.executor_routes.one_shot_ipc_call", new=ipc_mock):
            resp = client.post(
                "/api/v1/executor/shadow-toggle",
                json={"engine": "demo", "shadow_mode": False, "source": "audit_test"},
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        ipc_mock.assert_called_once()
        # one_shot_ipc_call(method, params=, timeout=, ...)
        args, kwargs = ipc_mock.call_args
        self.assertEqual(args[0], "patch_risk_config")
        params = kwargs.get("params") or args[1]
        self.assertEqual(params["engine"], "demo")
        self.assertEqual(params["source"], "audit_test")
        self.assertEqual(params["patch"], {"executor": {"shadow_mode": False}})

    def test_ipc_failure_returns_500(self) -> None:
        app = _make_app(_operator_actor())
        client = TestClient(app)
        with patch(
            "app.executor_routes.one_shot_ipc_call",
            new=AsyncMock(side_effect=RuntimeError("socket-down")),
        ):
            resp = client.post(
                "/api/v1/executor/shadow-toggle",
                json={"engine": "demo", "shadow_mode": True},
            )
        self.assertEqual(resp.status_code, 500)
        self.assertIn("rust_engine_unavailable", resp.json()["detail"])


# ─────────────────────────────────────────────────────────────────────────────
# Audit log writes (success + denial)
# ─────────────────────────────────────────────────────────────────────────────


class TestAuditLog(unittest.TestCase):

    def test_success_writes_audit_log_entry(self) -> None:
        app = _make_app(_operator_actor())
        client = TestClient(app)
        audit = _AuditRecorder()
        with _patch_audit_hub(audit), patch(
            "app.executor_routes.one_shot_ipc_call",
            new=AsyncMock(return_value={"version": 1}),
        ):
            resp = client.post(
                "/api/v1/executor/shadow-toggle",
                json={"engine": "demo", "shadow_mode": False, "source": "operator"},
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(len(audit.entries), 1)
        entry = audit.entries[0]
        self.assertEqual(entry["who"], "demo-operator")
        self.assertIn("applied", entry["what"])
        self.assertEqual(entry["new_value"]["shadow_mode"], False)
        self.assertIsNone(entry["new_value"]["gate_failed"])

    def test_denial_writes_audit_log_entry(self) -> None:
        app = _make_app(_viewer_actor())
        client = TestClient(app)
        audit = _AuditRecorder()
        with _patch_audit_hub(audit):
            resp = client.post(
                "/api/v1/executor/shadow-toggle",
                json={"engine": "demo", "shadow_mode": True},
            )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(len(audit.entries), 1)
        entry = audit.entries[0]
        self.assertIn("denied", entry["what"])
        # gate_failed field present (operator_role for non-Operator viewers)
        self.assertIsNotNone(entry["new_value"]["gate_failed"])


# ─────────────────────────────────────────────────────────────────────────────
# Concurrent flips — two back-to-back POSTs each fire their own IPC call
# ─────────────────────────────────────────────────────────────────────────────


class TestConcurrent(unittest.TestCase):

    def test_back_to_back_flips_each_invoke_ipc(self) -> None:
        """Two requests in sequence → two IPC calls (no caching/dedup at this layer).

        Real concurrent semantics live in Rust ConfigStore (mutex-serialised);
        the Python route is stateless wrt. the patch path.
        本層無快取/去重；真正併發語意在 Rust ConfigStore 端（mutex 序列化）。
        """
        app = _make_app(_operator_actor())
        client = TestClient(app)
        ipc_mock = AsyncMock(return_value={"version": 1})
        with patch("app.executor_routes.one_shot_ipc_call", new=ipc_mock):
            r1 = client.post(
                "/api/v1/executor/shadow-toggle",
                json={"engine": "demo", "shadow_mode": False},
            )
            r2 = client.post(
                "/api/v1/executor/shadow-toggle",
                json={"engine": "demo", "shadow_mode": True},
            )
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(ipc_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()
