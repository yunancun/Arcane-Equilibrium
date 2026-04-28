"""
G3-10 — POST /api/v1/strategist/promote route tests.
G3-10 — POST /api/v1/strategist/promote 路由測試。

MODULE_NOTE (EN):
  Verifies the operator-facing strategist params promotion endpoint:
    1. Input validation (engine pair, strategy whitelist, symbol charset).
    2. Auth gate matrix (preview vs apply × paper vs live).
    3. Two-step confirm flow (confirm=false preview → confirm=true apply).
    4. IPC dispatch shape on apply success (`update_strategy_params`).
    5. 403 + structured `gate_failed` payload on denial.
    6. 404 when no source row exists.
    7. Audit log entry written for both success + denial (preview is NOT audited).
    8. Concurrent apply requests each trigger their own IPC.

  Mock boundary:
    - `current_actor` Depends → injected via FastAPI dependency_overrides.
    - `_fetch_latest_applied_row` (PG read) → patched module-level so we
      don't need a real PG.
    - `one_shot_ipc_call` (the only real IPC call) → patched module-level.
    - `_get_governance_hub` → patched to return a hub whose `_change_audit_log`
      is our `_AuditRecorder` so the test can assert on entries.

MODULE_NOTE (中):
  G3-10 端點整合測試；最小 FastAPI app + dependency_overrides 注入 actor。
  PG 讀取與 IPC 都 mock；不依賴真實 Postgres / Rust engine。
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

from app import strategist_promote_routes


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
    """Build a minimal FastAPI app with strategist_promote_router + actor override.
    建構最小 FastAPI app：只掛 strategist_promote_router，並覆寫 current_actor。

    STRATEGIST-PROMOTE-API singleton-pollution fix (Option A, test fixture):
      Sibling `test_api_contract.py::build_client` runs `importlib.reload(main_legacy)`
      which rebinds `main_legacy.current_actor` to a new function object. The
      original `strategist_promote_routes.strategist_promote_router` was built
      before the reload, so its `Depends(base.current_actor)` holds the old
      callable. Without mitigation, `dependency_overrides[base.current_actor]`
      fails to match → 401 unauthorized instead of expected 200/400/403.

      Fix: reload `strategist_promote_routes` itself inside `_make_app` so the
      router rebuilds its `Depends` against the current `main_legacy.current_actor`.
      鏡 W3 SINGLETON Option A pattern（test fixture defense-in-depth）；不動
      production code（route 建構期 freeze Depends 是 FastAPI 標準語意）。
    """
    import importlib
    from app import strategist_promote_routes as _sp_mod
    importlib.reload(_sp_mod)

    app = FastAPI()
    app.include_router(_sp_mod.strategist_promote_router)

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


# ── Source row fixture ───────────────────────────────────────────────────────


def _fake_source_row(
    *,
    row_id: int = 42,
    engine_mode: str = "demo",
    strategy_name: str = "grid_trading",
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a fake `strategist_applied_params` row dict for mocked PG fetch.
    建構假的 strategist_applied_params row 字典。"""
    if params is None:
        params = {"cooldown_ms": 30000, "n_levels": 8, "spread_bps": 8.0}
    return {
        "id": row_id,
        "engine_mode": engine_mode,
        "strategy_name": strategy_name,
        "applied_at": "2026-04-24T20:00:00+00:00",
        "applied_at_ms": int(time.time() * 1000) - 60_000,
        "source": "strategist_scheduler",
        "reason": "top_deviation_pair",
        "prev_params_json": {"cooldown_ms": 60000, "n_levels": 8, "spread_bps": 10.0},
        "params_json": params,
    }


# ── HMAC + authorization.json helpers (reused from executor tests) ───────────


def _build_signed_authorization(
    *,
    secret: str,
    expires_at_ms: int,
    operator_id: str = "test-op",
    env_allowed: list[str] | None = None,
    tier: str = "T0_ENTRY",
    issued_at_ms: int | None = None,
) -> dict[str, Any]:
    """Build a signed authorization.json record (matches Rust canonical_payload)."""
    if env_allowed is None:
        env_allowed = ["live_demo"]
    if issued_at_ms is None:
        issued_at_ms = int(time.time() * 1000)
    envs_sorted = sorted(set(env_allowed))
    payload = f"1|{tier}|{issued_at_ms}|{expires_at_ms}|{operator_id}|{','.join(envs_sorted)}"
    sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "version": 1,
        "tier": tier,
        "issued_at_ms": issued_at_ms,
        "expires_at_ms": expires_at_ms,
        "operator_id": operator_id,
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
    """Set up $OPENCLAW_SECRETS_DIR/live/* contents for a test run."""
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
# Input validation
# ─────────────────────────────────────────────────────────────────────────────


class TestInputValidation(unittest.TestCase):

    def test_unknown_strategy_returns_400(self) -> None:
        app = _make_app(_operator_actor())
        client = TestClient(app)
        resp = client.post(
            "/api/v1/strategist/promote",
            json={
                "strategy": "evil_strategy",
                "symbol": "BTCUSDT",
                "source_engine": "demo",
                "target_engine": "paper",
            },
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("strategy must be one of", resp.json()["detail"])

    def test_invalid_symbol_charset_returns_400(self) -> None:
        app = _make_app(_operator_actor())
        client = TestClient(app)
        resp = client.post(
            "/api/v1/strategist/promote",
            json={
                "strategy": "grid_trading",
                "symbol": "btcusdt",  # lowercase, not allowed
                "source_engine": "demo",
                "target_engine": "paper",
            },
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("uppercase alphanumeric", resp.json()["detail"])

    def test_same_source_target_returns_400(self) -> None:
        app = _make_app(_operator_actor())
        client = TestClient(app)
        resp = client.post(
            "/api/v1/strategist/promote",
            json={
                "strategy": "grid_trading",
                "symbol": "BTCUSDT",
                "source_engine": "paper",
                "target_engine": "paper",
            },
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("no-op", resp.json()["detail"])

    def test_live_as_source_returns_400(self) -> None:
        """Live can only be a target — never a source (no edge benefit reading
        live params back into demo / paper).
        live 只能當目標，不能當來源。"""
        app = _make_app(_operator_actor())
        client = TestClient(app)
        resp = client.post(
            "/api/v1/strategist/promote",
            json={
                "strategy": "grid_trading",
                "symbol": "BTCUSDT",
                "source_engine": "live",
                "target_engine": "paper",
            },
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("source_engine must be one of", resp.json()["detail"])

    def test_demo_as_target_returns_400(self) -> None:
        """Demo can only be a source — never a target (we never write back to demo)."""
        app = _make_app(_operator_actor())
        client = TestClient(app)
        resp = client.post(
            "/api/v1/strategist/promote",
            json={
                "strategy": "grid_trading",
                "symbol": "BTCUSDT",
                "source_engine": "paper",
                "target_engine": "demo",
            },
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("target_engine must be one of", resp.json()["detail"])

    def test_missing_required_field_returns_422(self) -> None:
        """Missing `strategy` → Pydantic 422 (FastAPI default)."""
        app = _make_app(_operator_actor())
        client = TestClient(app)
        resp = client.post(
            "/api/v1/strategist/promote",
            json={
                "symbol": "BTCUSDT",
                "source_engine": "demo",
                "target_engine": "paper",
            },
        )
        self.assertEqual(resp.status_code, 422)


# ─────────────────────────────────────────────────────────────────────────────
# Operator role gate (always required)
# ─────────────────────────────────────────────────────────────────────────────


class TestOperatorRoleGate(unittest.TestCase):

    def test_no_operator_role_returns_403(self) -> None:
        """Even preview (cheap, no IPC) requires Operator role.
        即使 preview 也需 Operator 角色。"""
        app = _make_app(_viewer_actor())
        client = TestClient(app)
        resp = client.post(
            "/api/v1/strategist/promote",
            json={
                "strategy": "grid_trading",
                "symbol": "BTCUSDT",
                "source_engine": "demo",
                "target_engine": "paper",
                "confirm": False,
            },
        )
        self.assertEqual(resp.status_code, 403)


# ─────────────────────────────────────────────────────────────────────────────
# Source row not found
# ─────────────────────────────────────────────────────────────────────────────


class TestSourceRowNotFound(unittest.TestCase):

    def test_no_source_row_returns_404(self) -> None:
        """No matching (source_engine, strategy) row → 404 with reason."""
        app = _make_app(_operator_actor())
        client = TestClient(app)
        with patch(
            "app.strategist_promote_routes._fetch_latest_applied_row",
            return_value=(None, None),
        ):
            resp = client.post(
                "/api/v1/strategist/promote",
                json={
                    "strategy": "grid_trading",
                    "symbol": "BTCUSDT",
                    "source_engine": "demo",
                    "target_engine": "paper",
                },
            )
        self.assertEqual(resp.status_code, 404)
        self.assertIn("No strategist_applied_params row found", resp.json()["detail"])


# ─────────────────────────────────────────────────────────────────────────────
# Preview path (confirm=false)
# ─────────────────────────────────────────────────────────────────────────────


class TestPreviewPath(unittest.TestCase):

    def test_preview_returns_diff_no_ipc_dispatch(self) -> None:
        """confirm=false → preview JSON, NO IPC, NO audit row."""
        app = _make_app(_operator_actor())
        client = TestClient(app)
        source_row = _fake_source_row(
            params={"cooldown_ms": 30000, "n_levels": 8, "spread_bps": 8.0}
        )
        target_current_str = json.dumps(
            {"cooldown_ms": 60000, "n_levels": 8, "spread_bps": 10.0}
        )
        ipc_mock = AsyncMock(return_value={"result": target_current_str})
        audit = _AuditRecorder()
        with patch(
            "app.strategist_promote_routes._fetch_latest_applied_row",
            return_value=(source_row, None),
        ), patch(
            "app.strategist_promote_routes.one_shot_ipc_call",
            new=ipc_mock,
        ), _patch_audit_hub(audit):
            resp = client.post(
                "/api/v1/strategist/promote",
                json={
                    "strategy": "grid_trading",
                    "symbol": "BTCUSDT",
                    "source_engine": "demo",
                    "target_engine": "paper",
                    "confirm": False,
                },
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["phase"], "preview")
        self.assertTrue(body["confirm_required"])
        self.assertEqual(body["source_row"]["id"], 42)
        self.assertEqual(body["source_params"]["cooldown_ms"], 30000)
        self.assertEqual(body["target_current_params"]["cooldown_ms"], 60000)
        # Diff: cooldown_ms changed, spread_bps changed, n_levels unchanged.
        diff = body["diff"]
        self.assertTrue(diff["cooldown_ms"]["changed"])
        self.assertTrue(diff["spread_bps"]["changed"])
        self.assertFalse(diff["n_levels"]["changed"])
        # Preview only triggered get_strategy_params IPC, not update.
        ipc_mock.assert_called_once()
        self.assertEqual(ipc_mock.call_args[0][0], "get_strategy_params")
        # Preview is NOT audited (intentional).
        self.assertEqual(len(audit.entries), 0)

    def test_preview_with_ipc_unavailable_returns_degraded(self) -> None:
        """Preview tolerates IPC failure on `get_strategy_params` —
        target_current_degraded=True, target_current_params=None.
        IPC 不可用時 preview 仍回 200，target_current 標 degraded。"""
        app = _make_app(_operator_actor())
        client = TestClient(app)
        source_row = _fake_source_row()
        with patch(
            "app.strategist_promote_routes._fetch_latest_applied_row",
            return_value=(source_row, None),
        ), patch(
            "app.strategist_promote_routes.one_shot_ipc_call",
            new=AsyncMock(side_effect=RuntimeError("socket-down")),
        ):
            resp = client.post(
                "/api/v1/strategist/promote",
                json={
                    "strategy": "grid_trading",
                    "symbol": "BTCUSDT",
                    "source_engine": "demo",
                    "target_engine": "paper",
                    "confirm": False,
                },
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["phase"], "preview")
        self.assertTrue(body["target_current_degraded"])
        self.assertIsNone(body["target_current_params"])


# ─────────────────────────────────────────────────────────────────────────────
# Apply path: paper target (confirm=true, Operator only)
# ─────────────────────────────────────────────────────────────────────────────


class TestApplyPaper(unittest.TestCase):

    def test_apply_paper_dispatches_update_strategy_params(self) -> None:
        """target=paper + confirm=true → IPC `update_strategy_params` dispatched."""
        app = _make_app(_operator_actor())
        client = TestClient(app)
        source_row = _fake_source_row()
        ipc_mock = AsyncMock(return_value={"version": 11, "applied": True})
        with patch(
            "app.strategist_promote_routes._fetch_latest_applied_row",
            return_value=(source_row, None),
        ), patch(
            "app.strategist_promote_routes.one_shot_ipc_call",
            new=ipc_mock,
        ):
            resp = client.post(
                "/api/v1/strategist/promote",
                json={
                    "strategy": "grid_trading",
                    "symbol": "BTCUSDT",
                    "source_engine": "demo",
                    "target_engine": "paper",
                    "confirm": True,
                    "source": "g3_10_test",
                },
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["phase"], "apply")
        self.assertEqual(body["target_engine"], "paper")
        self.assertEqual(body["source_row_id"], 42)
        # IPC contract: method=update_strategy_params, with engine + strategy_name + params_json
        ipc_mock.assert_called_once()
        args, kwargs = ipc_mock.call_args
        self.assertEqual(args[0], "update_strategy_params")
        params = kwargs.get("params") or args[1]
        self.assertEqual(params["engine"], "paper")
        self.assertEqual(params["strategy_name"], "grid_trading")
        self.assertEqual(params["source"], "g3_10_test")
        self.assertIn("manual_promote:demo->paper", params["reason"])
        # params_json is a JSON-encoded string (Rust expects string, not nested dict)
        decoded = json.loads(params["params_json"])
        self.assertEqual(decoded["cooldown_ms"], 30000)


# ─────────────────────────────────────────────────────────────────────────────
# Apply path: live target — full 5-gate chain
# ─────────────────────────────────────────────────────────────────────────────


class TestApplyLiveGateChain(unittest.TestCase):

    def setUp(self) -> None:
        self.app = _make_app(_operator_actor())
        self.client = TestClient(self.app)
        self.source_row = _fake_source_row()

    def _post_apply_live(self) -> Any:
        return self.client.post(
            "/api/v1/strategist/promote",
            json={
                "strategy": "grid_trading",
                "symbol": "BTCUSDT",
                "source_engine": "demo",
                "target_engine": "live",
                "confirm": True,
            },
        )

    def test_live_apply_no_global_mode_403_live_reserved(self) -> None:
        """Gate 2 fail: global_mode lacks 'live'."""
        with patch(
            "app.strategist_promote_routes._fetch_latest_applied_row",
            return_value=(self.source_row, None),
        ), patch(
            "app.live_session_routes._get_global_mode_state",
            return_value="paper_only",
        ):
            resp = self._post_apply_live()
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"]["gate_failed"], "live_reserved")

    def test_live_apply_all_gates_green_succeeds(self) -> None:
        """All 5 gates green → 200 + IPC update_strategy_params dispatched."""
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
                bybit_endpoint="demo",  # → live_demo label, no mainnet env
                authorization_record=record,
            )
            ipc_mock = AsyncMock(return_value={"version": 7})
            with patch(
                "app.strategist_promote_routes._fetch_latest_applied_row",
                return_value=(self.source_row, None),
            ), patch.dict(os.environ, {
                "OPENCLAW_SECRETS_DIR": str(secrets_root),
                "OPENCLAW_IPC_SECRET": secret,
            }), patch(
                "app.live_session_routes._get_global_mode_state",
                return_value="live_reserved",
            ), patch(
                "app.strategist_promote_routes.one_shot_ipc_call",
                new=ipc_mock,
            ):
                resp = self._post_apply_live()
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["phase"], "apply")
        self.assertEqual(body["target_engine"], "live")
        ipc_mock.assert_called_once()
        self.assertEqual(ipc_mock.call_args[0][0], "update_strategy_params")
        params = ipc_mock.call_args[1].get("params") or ipc_mock.call_args[0][1]
        self.assertEqual(params["engine"], "live")


# ─────────────────────────────────────────────────────────────────────────────
# IPC failure on apply
# ─────────────────────────────────────────────────────────────────────────────


class TestIpcFailure(unittest.TestCase):

    def test_apply_ipc_failure_returns_500(self) -> None:
        app = _make_app(_operator_actor())
        client = TestClient(app)
        source_row = _fake_source_row()
        with patch(
            "app.strategist_promote_routes._fetch_latest_applied_row",
            return_value=(source_row, None),
        ), patch(
            "app.strategist_promote_routes.one_shot_ipc_call",
            new=AsyncMock(side_effect=RuntimeError("socket-down")),
        ):
            resp = client.post(
                "/api/v1/strategist/promote",
                json={
                    "strategy": "grid_trading",
                    "symbol": "BTCUSDT",
                    "source_engine": "demo",
                    "target_engine": "paper",
                    "confirm": True,
                },
            )
        self.assertEqual(resp.status_code, 500)
        self.assertIn("rust_engine_unavailable", resp.json()["detail"])


# ─────────────────────────────────────────────────────────────────────────────
# Audit log writes (success + denial; preview NOT audited)
# ─────────────────────────────────────────────────────────────────────────────


class TestAuditLog(unittest.TestCase):

    def test_apply_success_writes_audit_log(self) -> None:
        app = _make_app(_operator_actor())
        client = TestClient(app)
        source_row = _fake_source_row()
        audit = _AuditRecorder()
        with _patch_audit_hub(audit), patch(
            "app.strategist_promote_routes._fetch_latest_applied_row",
            return_value=(source_row, None),
        ), patch(
            "app.strategist_promote_routes.one_shot_ipc_call",
            new=AsyncMock(return_value={"version": 1}),
        ):
            resp = client.post(
                "/api/v1/strategist/promote",
                json={
                    "strategy": "grid_trading",
                    "symbol": "BTCUSDT",
                    "source_engine": "demo",
                    "target_engine": "paper",
                    "confirm": True,
                    "source": "operator_manual",
                },
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(len(audit.entries), 1)
        entry = audit.entries[0]
        self.assertEqual(entry["who"], "demo-operator")
        self.assertIn("applied", entry["what"])
        self.assertEqual(entry["new_value"]["target_engine"], "paper")
        self.assertEqual(entry["new_value"]["source_row_id"], 42)
        self.assertIsNone(entry["new_value"]["gate_failed"])

    def test_role_denial_writes_audit_log(self) -> None:
        app = _make_app(_viewer_actor())
        client = TestClient(app)
        audit = _AuditRecorder()
        with _patch_audit_hub(audit):
            resp = client.post(
                "/api/v1/strategist/promote",
                json={
                    "strategy": "grid_trading",
                    "symbol": "BTCUSDT",
                    "source_engine": "demo",
                    "target_engine": "paper",
                    "confirm": True,
                },
            )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(len(audit.entries), 1)
        entry = audit.entries[0]
        self.assertIn("denied", entry["what"])
        self.assertIsNotNone(entry["new_value"]["gate_failed"])

    def test_preview_does_not_audit(self) -> None:
        """Preview is intentionally not audited — design choice to avoid
        flooding change_audit_log with read-only inspections.
        Preview 不寫 audit（避免 audit log 被讀取流量灌爆）。"""
        app = _make_app(_operator_actor())
        client = TestClient(app)
        source_row = _fake_source_row()
        audit = _AuditRecorder()
        with _patch_audit_hub(audit), patch(
            "app.strategist_promote_routes._fetch_latest_applied_row",
            return_value=(source_row, None),
        ), patch(
            "app.strategist_promote_routes.one_shot_ipc_call",
            new=AsyncMock(return_value={"result": "{}"}),
        ):
            resp = client.post(
                "/api/v1/strategist/promote",
                json={
                    "strategy": "grid_trading",
                    "symbol": "BTCUSDT",
                    "source_engine": "demo",
                    "target_engine": "paper",
                    "confirm": False,
                },
            )
        self.assertEqual(resp.status_code, 200)
        # No audit row for pure preview (operator can read-only inspect freely).
        self.assertEqual(len(audit.entries), 0)


# ─────────────────────────────────────────────────────────────────────────────
# Concurrent apply requests — each fires its own IPC
# ─────────────────────────────────────────────────────────────────────────────


class TestConcurrent(unittest.TestCase):

    def test_back_to_back_apply_each_invoke_ipc(self) -> None:
        """Two applies in sequence → two IPC calls (no caching/dedup at this layer).

        Real concurrent serialization lives in Rust ConfigStore (mutex);
        this Python route is stateless wrt. the apply path. Second call
        sees the first's effect because Rust persists between calls.
        本層無快取/去重；真正併發語意在 Rust ConfigStore（mutex 序列化）。
        """
        app = _make_app(_operator_actor())
        client = TestClient(app)
        source_row = _fake_source_row()
        ipc_mock = AsyncMock(return_value={"version": 1})
        with patch(
            "app.strategist_promote_routes._fetch_latest_applied_row",
            return_value=(source_row, None),
        ), patch(
            "app.strategist_promote_routes.one_shot_ipc_call",
            new=ipc_mock,
        ):
            r1 = client.post(
                "/api/v1/strategist/promote",
                json={
                    "strategy": "grid_trading",
                    "symbol": "BTCUSDT",
                    "source_engine": "demo",
                    "target_engine": "paper",
                    "confirm": True,
                },
            )
            r2 = client.post(
                "/api/v1/strategist/promote",
                json={
                    "strategy": "grid_trading",
                    "symbol": "BTCUSDT",
                    "source_engine": "demo",
                    "target_engine": "paper",
                    "confirm": True,
                },
            )
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(ipc_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()
