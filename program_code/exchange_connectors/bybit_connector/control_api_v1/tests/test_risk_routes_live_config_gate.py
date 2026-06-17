"""
POST /api/v1/paper/risk/config/engine/{engine}/global — live config write gate.
update_per_engine_global_config 的 live RiskConfig 寫入面門控測試。

MODULE_NOTE (中):
  驗證 risk_routes.update_per_engine_global_config 對 engine=="live" 在取得 IPC /
  下發 patch 之前，必須先過完整 live 五門（複用 live_preflight.all_five_live_gates_ok
  唯一權威 primitive，與 post_live_session_start / executor_routes 對齊）：
    1. 五門未過 → 409 + {"error":"live_gate_failed","gate_failed":[...]}（fail-closed）。
    2. 五門全過 → 放行，照常下 IPC patch_risk_config。
    3. demo / paper 不受此門（Demo 放寬 / Live 收緊政策）：僅 operator + scope。
    4. 門的位置正確：在 _require_risk_write 之後、IPC 之前 —— 非 operator 拿 403
       而非 409（授權門先於 live 門），且 live 門未過時 IPC 永不被呼叫。
    5. 真實五門鏈（鏡 test_executor_shadow_toggle_api）：global_mode≠live_reserved
       → 409 gate_failed 含 global_mode_not_live_reserved；全綠 → 放行下 IPC。

  Mock 邊界：
    - current_actor Depends → dependency_overrides 注入 _FakeActor。
    - _get_direct_ipc → patch 回傳帶 AsyncMock .call 的假 IPC client（不連真 socket）。
    - live_preflight.all_five_live_gates_ok → 核心行為測試直接 patch 回 (ok, reasons)；
      真實鏈測試走 secret slot + signed authorization.json fixture（不 patch primitive）。
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

# ── Path setup / 路徑設置 ─────────────────────────────────────────────────────
_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from fastapi import FastAPI
from fastapi.testclient import TestClient


# ── Fake actor (mirrors AuthenticatedActor duck-type) ────────────────────────


@dataclass
class _FakeActor:
    """Mirror AuthenticatedActor duck-type（actor_id + roles + scopes）。"""

    actor_id: str = "test-operator"
    roles: set[str] | None = None
    scopes: set[str] | None = None

    def __post_init__(self) -> None:
        if self.roles is None:
            self.roles = {"operator", "viewer"}
        if self.scopes is None:
            self.scopes = {"risk:write"}


def _operator_actor() -> _FakeActor:
    return _FakeActor(actor_id="risk-operator", roles={"operator", "viewer"}, scopes={"risk:write"})


def _viewer_actor() -> _FakeActor:
    return _FakeActor(actor_id="viewer-only", roles={"viewer"}, scopes={"risk:write"})


def _make_app(actor: _FakeActor) -> FastAPI:
    """Build a minimal FastAPI app with risk_router + actor override.
    建構最小 FastAPI app：只掛 risk_router，並覆寫 current_actor。

    鏡 test_executor_shadow_toggle_api._make_app：sibling 測試可能 reload
    main_legacy 重綁 current_actor，故在此 reload risk_routes 讓 router 對齊
    當前綁定的 main_legacy.current_actor（不動 production code）。
    """
    import importlib
    from app import risk_routes as _risk_routes_mod
    importlib.reload(_risk_routes_mod)

    app = FastAPI()
    app.include_router(_risk_routes_mod.risk_router)

    from app import main_legacy as base
    app.dependency_overrides[base.current_actor] = lambda: actor
    return app


def _fake_ipc(call_mock: AsyncMock) -> AsyncMock:
    """Return an async _get_direct_ipc replacement yielding a client whose
    .call is call_mock. 回傳假 _get_direct_ipc：其 client.call 為注入的 AsyncMock。"""
    client = MagicMock()
    client.call = call_mock
    return AsyncMock(return_value=client)


_GLOBAL_PATH = "/api/v1/paper/risk/config/engine/{engine}/global"


# ── HMAC + authorization.json helpers (mirror executor test) ─────────────────


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
    """建構簽名 authorization.json 記錄（對齊 Rust canonical_payload）。"""
    if env_allowed is None:
        env_allowed = ["live_demo"]
    if issued_at_ms is None:
        issued_at_ms = int(time.time() * 1000)
    envs_sorted = sorted(set(env_allowed))
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
        "approved_system_mode": approved_system_mode,
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
    """為測試建立 secret slot 內容；回傳指向 OPENCLAW_SECRETS_DIR 的根目錄。"""
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
    return tmpdir / "secret_files" / "bybit"


# ─────────────────────────────────────────────────────────────────────────────
# Core behavior: live gate (primitive patched)
# ─────────────────────────────────────────────────────────────────────────────


class TestLiveConfigGate(unittest.TestCase):

    def test_live_gate_failed_returns_409_and_no_ipc(self) -> None:
        """engine=live + 五門未過 → 409 live_gate_failed，且 IPC 永不被呼叫。"""
        app = _make_app(_operator_actor())
        client = TestClient(app)
        call_mock = AsyncMock(return_value={"ok": True, "version": 1})
        with patch(
            "app.risk_routes._get_direct_ipc", new=_fake_ipc(call_mock)
        ), patch(
            "app.live_preflight.all_five_live_gates_ok",
            return_value=(False, ["global_mode_not_live_reserved"]),
        ):
            resp = client.post(
                _GLOBAL_PATH.format(engine="live"),
                json={"max_leverage": 3.0},
            )
        self.assertEqual(resp.status_code, 409, resp.text)
        detail = resp.json()["detail"]
        self.assertEqual(detail["error"], "live_gate_failed")
        self.assertEqual(detail["gate_failed"], ["global_mode_not_live_reserved"])
        # fail-closed：門未過時不得下發 IPC patch。
        call_mock.assert_not_called()

    def test_live_gate_passed_proceeds_to_ipc(self) -> None:
        """engine=live + 五門全過 → 放行，下 IPC patch_risk_config（含 Phase-0 token）。"""
        app = _make_app(_operator_actor())
        client = TestClient(app)
        call_mock = AsyncMock(return_value={"ok": True, "version": 42, "source": "operator"})
        # PHASE 0 AUTH-1：live 分支現走 _patch_live_with_token，需 OPENCLAW_LIVE_PATCH_SECRET 鑄 token。
        with patch.dict(os.environ, {"OPENCLAW_LIVE_PATCH_SECRET": "test-live-patch-secret"}), patch(
            "app.risk_routes._get_direct_ipc", new=_fake_ipc(call_mock)
        ), patch(
            "app.live_preflight.all_five_live_gates_ok",
            return_value=(True, []),
        ):
            resp = client.post(
                _GLOBAL_PATH.format(engine="live"),
                json={"max_leverage": 3.0},
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()["data"]
        self.assertEqual(body["engine"], "live")
        self.assertEqual(body["message"], "updated")
        call_mock.assert_called_once()
        args, kwargs = call_mock.call_args
        self.assertEqual(args[0], "patch_risk_config")
        self.assertEqual(kwargs["params"]["engine"], "live")
        # PHASE 0 AUTH-1：live patch 必帶 token 三欄（否則 Rust chokepoint self-deadlock）。
        self.assertIn("live_authz_token", kwargs["params"])
        self.assertIn("live_authz_nonce", kwargs["params"])
        self.assertIn("live_authz_ts", kwargs["params"])

    def test_live_requires_authz_true(self) -> None:
        """live 門必以 require_authz=True 呼叫（與 live-order / session 路徑同級後果）。"""
        app = _make_app(_operator_actor())
        client = TestClient(app)
        call_mock = AsyncMock(return_value={"ok": True, "version": 1})
        gate = MagicMock(return_value=(True, []))
        with patch.dict(os.environ, {"OPENCLAW_LIVE_PATCH_SECRET": "test-live-patch-secret"}), patch(
            "app.risk_routes._get_direct_ipc", new=_fake_ipc(call_mock)
        ), patch("app.live_preflight.all_five_live_gates_ok", gate):
            client.post(
                _GLOBAL_PATH.format(engine="live"),
                json={"max_leverage": 3.0},
            )
        gate.assert_called_once()
        _gargs, gkwargs = gate.call_args
        self.assertTrue(gkwargs.get("require_authz"))


# ─────────────────────────────────────────────────────────────────────────────
# demo / paper unaffected (Demo 放寬 / Live 收緊)
# ─────────────────────────────────────────────────────────────────────────────


class TestDemoPaperUnaffected(unittest.TestCase):

    def test_demo_proceeds_without_live_gate(self) -> None:
        """engine=demo → 不呼 live 門，operator + scope 即放行。"""
        app = _make_app(_operator_actor())
        client = TestClient(app)
        call_mock = AsyncMock(return_value={"ok": True, "version": 7})
        gate = MagicMock(return_value=(False, ["should_not_be_consulted"]))
        with patch(
            "app.risk_routes._get_direct_ipc", new=_fake_ipc(call_mock)
        ), patch("app.live_preflight.all_five_live_gates_ok", gate):
            resp = client.post(
                _GLOBAL_PATH.format(engine="demo"),
                json={"max_leverage": 3.0},
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        gate.assert_not_called()
        call_mock.assert_called_once()

    def test_paper_proceeds_without_live_gate(self) -> None:
        """engine=paper → 不呼 live 門，operator + scope 即放行。"""
        app = _make_app(_operator_actor())
        client = TestClient(app)
        call_mock = AsyncMock(return_value={"ok": True, "version": 3})
        gate = MagicMock(return_value=(False, ["should_not_be_consulted"]))
        with patch(
            "app.risk_routes._get_direct_ipc", new=_fake_ipc(call_mock)
        ), patch("app.live_preflight.all_five_live_gates_ok", gate):
            resp = client.post(
                _GLOBAL_PATH.format(engine="paper"),
                json={"max_leverage": 3.0},
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        gate.assert_not_called()
        call_mock.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# Gate ordering: _require_risk_write BEFORE live gate
# ─────────────────────────────────────────────────────────────────────────────


class TestGateOrdering(unittest.TestCase):

    def test_non_operator_live_returns_403_not_409(self) -> None:
        """非 operator 對 live → 403（risk:write 門先於 live 門），不是 409。"""
        app = _make_app(_viewer_actor())
        client = TestClient(app)
        gate = MagicMock(return_value=(True, []))
        with patch("app.live_preflight.all_five_live_gates_ok", gate):
            resp = client.post(
                _GLOBAL_PATH.format(engine="live"),
                json={"max_leverage": 3.0},
            )
        self.assertEqual(resp.status_code, 403)
        # 授權門先擋下，live 門不該被諮詢。
        gate.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# Real 5-gate chain (no primitive patch) — mirrors executor test
# ─────────────────────────────────────────────────────────────────────────────


class TestRealGateChain(unittest.TestCase):

    def setUp(self) -> None:
        self.app = _make_app(_operator_actor())
        self.client = TestClient(self.app)

    def test_live_no_global_mode_409_global_mode_not_live_reserved(self) -> None:
        """真實鏈 Gate 2：global_mode≠live_reserved → 409。"""
        call_mock = AsyncMock(return_value={"ok": True, "version": 1})
        with patch(
            "app.risk_routes._get_direct_ipc", new=_fake_ipc(call_mock)
        ), patch(
            "app.live_session_routes._get_global_mode_state",
            return_value="paper_only",
        ):
            resp = self.client.post(
                _GLOBAL_PATH.format(engine="live"),
                json={"max_leverage": 3.0},
            )
        self.assertEqual(resp.status_code, 409, resp.text)
        self.assertIn(
            "global_mode_not_live_reserved",
            resp.json()["detail"]["gate_failed"],
        )
        call_mock.assert_not_called()

    def test_live_all_gates_green_proceeds(self) -> None:
        """真實鏈五門全綠 → 放行下 IPC。"""
        import tempfile
        call_mock = AsyncMock(return_value={"ok": True, "version": 9})
        with tempfile.TemporaryDirectory() as tmp:
            secret = "test-secret"
            future_ms = int(time.time() * 1000) + 24 * 3600 * 1000
            record = _build_signed_authorization(
                secret=secret,
                expires_at_ms=future_ms,
                env_allowed=["live_demo"],
            )
            secrets_root = _write_secret_slot(
                Path(tmp),
                bybit_endpoint="demo",  # → live_demo label，免 mainnet env 門
                authorization_record=record,
            )
            with patch.dict(os.environ, {
                "OPENCLAW_SECRETS_DIR": str(secrets_root),
                "OPENCLAW_LIVE_AUTH_SIGNING_KEY": secret,
                # PHASE 0 AUTH-1：live 分支鑄 token 需此 secret。
                "OPENCLAW_LIVE_PATCH_SECRET": "test-live-patch-secret",
            }), patch(
                "app.live_session_routes._get_global_mode_state",
                return_value="live_reserved",
            ), patch(
                "app.risk_routes._get_direct_ipc", new=_fake_ipc(call_mock)
            ):
                resp = self.client.post(
                    _GLOBAL_PATH.format(engine="live"),
                    json={"max_leverage": 3.0},
                )
        self.assertEqual(resp.status_code, 200, resp.text)
        call_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
