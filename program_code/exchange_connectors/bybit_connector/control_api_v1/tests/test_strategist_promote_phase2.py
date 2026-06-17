"""
PHASE 2 — strategist promote/demote ENHANCEMENT tests.
PHASE 2 — 策略師促升/回滾增強測試（flag / criteria / fail-closed audit / demote）。

MODULE_NOTE (中):
  覆蓋 execution_plan 2026-06-17 §2.1/§2.4/§2.5/§2.6 在既有 strategist_promote_routes
  上疊加的三閘 + net-new demote：
    1. flag-OFF + live → 409 promotion_disabled（0 IPC promote）。
    2. criteria Reject/Pending → 409 criteria_not_met（0 IPC promote）。
    3. criteria Eligible → live promote 鑄 token + 同步 INSERT strategist_promotions。
    4. audit INSERT 失敗 → 500 audit_write_failed（loud，非吞錯）。
    5. demote 還原 COMPLETE pre-promotion set（EXACT）。
    6. demote precondition fail（live 中途被改）→ 409 live_changed_since_promotion。
    7. add-key-then-demote 精確性（promote 加 key → demote 還原回完整 pre set）。

  Mock 邊界（不 mock 掉被測閘）：
    - current_actor → dependency_overrides 注入 operator actor。
    - _promotion_enabled → patch 控制 flag（避免依賴真 env）。
    - _fetch_latest_applied_row / _fetch_demo_soak_metrics / _fetch_promotion_row →
      patch（不需真 PG）。
    - _insert_promotion_audit → patch（驗呼叫 + 模擬失敗）；不 mock 掉 INSERT 失敗→500 邏輯。
    - one_shot_ipc_call → AsyncMock，按 method 路由回不同 payload（snapshot/criteria/update）。
    - _apply_target_gate → 在「非閘測」場景 patch 成 no-op 以隔離 criteria/audit 邏輯；
      flag/criteria 閘在 5-gate **之前**，故不需真跑 5-gate（與既有 test 的真 5-gate 互補）。
"""

from __future__ import annotations

import json
import os
import sys
import time
import unittest
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from fastapi import FastAPI
from fastapi.testclient import TestClient


# ── Fake actor ────────────────────────────────────────────────────────────────


@dataclass
class _FakeActor:
    actor_id: str = "demo-operator"
    roles: set[str] | None = None

    def __post_init__(self) -> None:
        if self.roles is None:
            self.roles = {"operator", "viewer"}


def _operator_actor() -> _FakeActor:
    return _FakeActor(actor_id="demo-operator", roles={"operator", "viewer"})


def _make_app(actor: _FakeActor) -> FastAPI:
    """Minimal app with the promote router + actor override (mirror sibling fixture)."""
    import importlib
    from app import strategist_promote_routes as _sp_mod
    importlib.reload(_sp_mod)

    app = FastAPI()
    app.include_router(_sp_mod.strategist_promote_router)

    from app import main_legacy as base
    app.dependency_overrides[base.current_actor] = lambda: actor
    return app


def _fake_source_row(
    *,
    row_id: int = 42,
    strategy_name: str = "grid_trading",
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if params is None:
        params = {"cooldown_ms": 30000, "n_levels": 8}
    return {
        "id": row_id,
        "engine_mode": "demo",
        "strategy_name": strategy_name,
        "applied_at": "2026-04-24T20:00:00+00:00",
        "applied_at_ms": int(time.time() * 1000) - 60_000,
        "source": "strategist_scheduler",
        "reason": "top_deviation_pair",
        "prev_params_json": {"cooldown_ms": 60000, "n_levels": 8},
        "params_json": params,
    }


def _ipc_router(*, snapshot: Any, criteria: dict[str, Any] | None, update: Any) -> AsyncMock:
    """Build an AsyncMock for one_shot_ipc_call that routes by method name.

    snapshot  → get_strategy_params（pre-promotion 完整 set / demote current-live /
                Fix 3 post-promotion re-read — 同一 snapshot 回應於本 fixture）
    criteria  → evaluate_promotion_criteria（verdict payload，REAL handler shape：
                小寫 verdict tag + per_cell/active_count/edge_estimates_fresh，**非**
                舊的大寫 "Eligible" + "criteria_input"——對齊 dispatch.rs handler）
    update    → update_strategy_params（promote/demote 寫入回應）
    """
    async def _side(method: str, *args: Any, **kwargs: Any) -> Any:
        if method == "get_strategy_params":
            return snapshot
        if method == "evaluate_promotion_criteria":
            return criteria if criteria is not None else {"verdict": "pending", "reason": "n/a"}
        if method == "update_strategy_params":
            return update
        raise AssertionError(f"unexpected IPC method {method!r}")

    return AsyncMock(side_effect=_side)


_LIVE_OK_SOAK = {
    "demo_soak_wall_clock_ms": 30 * 24 * 3600 * 1000,
    "ms_since_last_param_change": 5 * 24 * 3600 * 1000,
    "attributable_demo_fills": 120,
}

_FAKE_COST_MODEL = {
    "fee_bps_round_trip": 21.0,
    "cost_gate_safety_multiplier": 1.3,
    "cost_gate_win_rate_floor": 0.3,
    "edge_ttl_secs": 172_800,
}


def _patch_contract_helpers(
    *,
    active_symbols: list[str] | None = None,
    boundary: int = 0,
) -> Any:
    """Patch the Option-A route helpers (active_symbols / cost model / boundary) so
    criteria-gate tests isolate the verdict logic from real TOML/DB.

    為何要 patch：Fix 1 Option A 下 route 真讀 risk_config_live.toml + scanner_config +
    strategy_params_live + 查 demo drawdown DB。單元測試不依賴真檔/真 PG → patch 三 helper。
    """
    from contextlib import ExitStack

    syms = active_symbols if active_symbols is not None else ["BTCUSDT", "ETHUSDT"]
    stack = ExitStack()
    stack.enter_context(
        patch("app.strategist_promote_routes._resolve_active_symbols", return_value=syms)
    )
    stack.enter_context(
        patch(
            "app.strategist_promote_routes._load_live_cost_model",
            return_value=dict(_FAKE_COST_MODEL),
        )
    )
    stack.enter_context(
        patch(
            "app.strategist_promote_routes._compute_demo_boundary_violation_count",
            return_value=boundary,
        )
    )
    return stack


# ─────────────────────────────────────────────────────────────────────────────
# §2.1 flag gate
# ─────────────────────────────────────────────────────────────────────────────


class TestFlagGate(unittest.TestCase):

    def test_flag_off_live_promote_returns_409_promotion_disabled(self) -> None:
        """flag-OFF + live + confirm=true → 409 promotion_disabled, 0 IPC promote."""
        app = _make_app(_operator_actor())
        client = TestClient(app)
        source_row = _fake_source_row()
        ipc_mock = _ipc_router(snapshot={"result": "{}"}, criteria=None, update={"v": 1})
        with patch(
            "app.strategist_promote_routes._promotion_enabled", return_value=False,
        ), patch(
            "app.strategist_promote_routes._fetch_latest_applied_row",
            return_value=(source_row, None),
        ), patch(
            "app.strategist_promote_routes.one_shot_ipc_call", new=ipc_mock,
        ):
            resp = client.post(
                "/api/v1/strategist/promote",
                json={
                    "strategy": "grid_trading", "symbol": "BTCUSDT",
                    "source_engine": "demo", "target_engine": "live", "confirm": True,
                },
            )
        self.assertEqual(resp.status_code, 409, resp.text)
        self.assertEqual(resp.json()["detail"]["error"], "promotion_disabled")
        # No update_strategy_params dispatched (no live mutation).
        called_methods = [c.args[0] for c in ipc_mock.call_args_list]
        self.assertNotIn("update_strategy_params", called_methods)

    def test_flag_off_paper_promote_unaffected(self) -> None:
        """flag-OFF does NOT block paper target (bit-identical to legacy)."""
        app = _make_app(_operator_actor())
        client = TestClient(app)
        source_row = _fake_source_row()
        ipc_mock = _ipc_router(snapshot={"result": "{}"}, criteria=None, update={"version": 1})
        with patch(
            "app.strategist_promote_routes._promotion_enabled", return_value=False,
        ), patch(
            "app.strategist_promote_routes._fetch_latest_applied_row",
            return_value=(source_row, None),
        ), patch(
            "app.strategist_promote_routes.one_shot_ipc_call", new=ipc_mock,
        ):
            resp = client.post(
                "/api/v1/strategist/promote",
                json={
                    "strategy": "grid_trading", "symbol": "BTCUSDT",
                    "source_engine": "demo", "target_engine": "paper", "confirm": True,
                },
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        called_methods = [c.args[0] for c in ipc_mock.call_args_list]
        self.assertIn("update_strategy_params", called_methods)


# ─────────────────────────────────────────────────────────────────────────────
# §2.4 criteria gate
# ─────────────────────────────────────────────────────────────────────────────


class TestCriteriaGate(unittest.TestCase):

    def _post_live(self, client: TestClient) -> Any:
        return client.post(
            "/api/v1/strategist/promote",
            json={
                "strategy": "grid_trading", "symbol": "BTCUSDT",
                "source_engine": "demo", "target_engine": "live", "confirm": True,
            },
        )

    def test_criteria_reject_returns_409_no_ipc_promote(self) -> None:
        """criteria verdict reject → 409 criteria_not_met, 0 update_strategy_params."""
        app = _make_app(_operator_actor())
        client = TestClient(app)
        source_row = _fake_source_row()
        # REAL handler shape: lowercase tag + per_cell (NOT capital "Eligible" / "criteria_input").
        ipc_mock = _ipc_router(
            snapshot={"result": json.dumps({"cooldown_ms": 60000, "n_levels": 8})},
            criteria={"verdict": "reject", "reason": "demo_breached_live_drawdown_envelope",
                      "per_cell": [], "active_count": 1, "edge_estimates_fresh": True},
            update={"version": 99},
        )
        with _patch_contract_helpers(), patch(
            "app.strategist_promote_routes._promotion_enabled", return_value=True,
        ), patch(
            "app.strategist_promote_routes._fetch_latest_applied_row",
            return_value=(source_row, None),
        ), patch(
            "app.strategist_promote_routes._fetch_demo_soak_metrics",
            return_value=dict(_LIVE_OK_SOAK),
        ), patch(
            "app.strategist_promote_routes._insert_promotion_audit", return_value=1,
        ), patch(
            "app.strategist_promote_routes.one_shot_ipc_call", new=ipc_mock,
        ):
            resp = self._post_live(client)
        self.assertEqual(resp.status_code, 409, resp.text)
        self.assertEqual(resp.json()["detail"]["error"], "criteria_not_met")
        self.assertEqual(resp.json()["detail"]["verdict"], "reject")
        called_methods = [c.args[0] for c in ipc_mock.call_args_list]
        self.assertNotIn("update_strategy_params", called_methods)

    def test_criteria_pending_returns_409(self) -> None:
        """criteria pending (0 validated edge cell, DESIRED §2.9) → 409, 0 promote."""
        app = _make_app(_operator_actor())
        client = TestClient(app)
        source_row = _fake_source_row()
        ipc_mock = _ipc_router(
            snapshot={"result": "{}"},
            criteria={"verdict": "pending", "reason": "edge_coverage_below_floor: q=0/25 cov=0",
                      "per_cell": [], "active_count": 25, "edge_estimates_fresh": True},
            update={"version": 99},
        )
        with _patch_contract_helpers(), patch(
            "app.strategist_promote_routes._promotion_enabled", return_value=True,
        ), patch(
            "app.strategist_promote_routes._fetch_latest_applied_row",
            return_value=(source_row, None),
        ), patch(
            "app.strategist_promote_routes._fetch_demo_soak_metrics",
            return_value=dict(_LIVE_OK_SOAK),
        ), patch(
            "app.strategist_promote_routes._insert_promotion_audit", return_value=1,
        ), patch(
            "app.strategist_promote_routes.one_shot_ipc_call", new=ipc_mock,
        ):
            resp = self._post_live(client)
        self.assertEqual(resp.status_code, 409, resp.text)
        self.assertEqual(resp.json()["detail"]["verdict"], "pending")
        called_methods = [c.args[0] for c in ipc_mock.call_args_list]
        self.assertNotIn("update_strategy_params", called_methods)

    def test_criteria_ipc_unavailable_fail_closed_503(self) -> None:
        """criteria IPC down → 503 criteria_evaluation_unavailable (no verdict = no promote)."""
        app = _make_app(_operator_actor())
        client = TestClient(app)
        source_row = _fake_source_row()

        async def _side(method: str, *a: Any, **k: Any) -> Any:
            if method == "get_strategy_params":
                return {"result": "{}"}
            if method == "evaluate_promotion_criteria":
                raise RuntimeError("socket-down")
            raise AssertionError(f"unexpected {method}")

        ipc_mock = AsyncMock(side_effect=_side)
        with _patch_contract_helpers(), patch(
            "app.strategist_promote_routes._promotion_enabled", return_value=True,
        ), patch(
            "app.strategist_promote_routes._fetch_latest_applied_row",
            return_value=(source_row, None),
        ), patch(
            "app.strategist_promote_routes._fetch_demo_soak_metrics",
            return_value=dict(_LIVE_OK_SOAK),
        ), patch(
            "app.strategist_promote_routes.one_shot_ipc_call", new=ipc_mock,
        ):
            resp = self._post_live(client)
        self.assertEqual(resp.status_code, 503, resp.text)
        self.assertEqual(resp.json()["detail"], "criteria_evaluation_unavailable")


# ─────────────────────────────────────────────────────────────────────────────
# §2.4 Eligible → promote (token mint + synchronous audit INSERT)
# ─────────────────────────────────────────────────────────────────────────────


class TestEligiblePromote(unittest.TestCase):

    def test_criteria_eligible_mints_token_and_inserts_audit(self) -> None:
        """eligible → live promote mints token (3 token fields) + INSERT strategist_promotions."""
        app = _make_app(_operator_actor())
        client = TestClient(app)
        source_row = _fake_source_row(params={"cooldown_ms": 45000, "n_levels": 8})
        # snapshot returned for BOTH pre-promotion capture AND Fix-3 post-promotion re-read.
        # Here pre == post (complete typed set) — the route stores the re-read complete set.
        complete_live = {"cooldown_ms": 45000, "n_levels": 8}
        ipc_mock = _ipc_router(
            snapshot={"result": json.dumps(complete_live)},
            criteria={"verdict": "eligible", "reason": None,
                      "per_cell": [{"symbol": "BTCUSDT", "validation_passed": True}],
                      "active_count": 2, "edge_estimates_fresh": True},
            update={"version": 7},
        )
        insert_mock = MagicMock(return_value=555)
        with _patch_contract_helpers(), patch(
            "app.strategist_promote_routes._promotion_enabled", return_value=True,
        ), patch(
            "app.strategist_promote_routes._fetch_latest_applied_row",
            return_value=(source_row, None),
        ), patch(
            "app.strategist_promote_routes._fetch_demo_soak_metrics",
            return_value=dict(_LIVE_OK_SOAK),
        ), patch(
            "app.strategist_promote_routes._apply_target_gate", new=MagicMock(),
        ), patch(
            "app.strategist_promote_routes._insert_promotion_audit", new=insert_mock,
        ), patch.dict(os.environ, {"OPENCLAW_LIVE_PATCH_SECRET": "phase2-test-secret"}), patch(
            "app.strategist_promote_routes.one_shot_ipc_call", new=ipc_mock,
        ):
            resp = client.post(
                "/api/v1/strategist/promote",
                json={
                    "strategy": "grid_trading", "symbol": "BTCUSDT",
                    "source_engine": "demo", "target_engine": "live", "confirm": True,
                },
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["promotion_id"], 555)
        # update_strategy_params dispatched with the 3 token fields (Phase-0 mint).
        update_calls = [c for c in ipc_mock.call_args_list if c.args[0] == "update_strategy_params"]
        self.assertEqual(len(update_calls), 1)
        params = update_calls[0].kwargs.get("params") or update_calls[0].args[1]
        self.assertEqual(params["engine"], "live")
        self.assertTrue(
            {"live_authz_token", "live_authz_nonce", "live_authz_ts"} <= set(params)
        )
        # Synchronous audit INSERT called with action=promote, gate_passed=True, Eligible.
        insert_mock.assert_called_once()
        kw = insert_mock.call_args.kwargs
        self.assertEqual(kw["action"], "promote")
        self.assertTrue(kw["gate_passed"])
        self.assertEqual(kw["criteria_verdict"], "Eligible")
        # Fix 2: criteria_input assembled from REAL handler keys (per_cell/active_count/fresh),
        # NOT the never-emitted "criteria_input" key.
        self.assertEqual(
            kw["criteria_input"]["per_cell"],
            [{"symbol": "BTCUSDT", "validation_passed": True}],
        )
        self.assertEqual(kw["criteria_input"]["active_count"], 2)
        self.assertTrue(kw["criteria_input"]["edge_estimates_fresh"])
        # pre-promotion snapshot captured (full set from get_strategy_params).
        self.assertEqual(kw["pre_promotion_params"], complete_live)
        # Fix 3: promoted_params is the COMPLETE post-promotion re-read set (full-vs-full demote).
        self.assertEqual(kw["promoted_params"], complete_live)

    def test_audit_insert_failure_returns_500_audit_write_failed(self) -> None:
        """live IPC OK but strategist_promotions INSERT fails → 500 audit_write_failed (loud)."""
        app = _make_app(_operator_actor())
        client = TestClient(app)
        source_row = _fake_source_row()
        ipc_mock = _ipc_router(
            snapshot={"result": "{}"},
            criteria={"verdict": "eligible", "reason": None,
                      "per_cell": [], "active_count": 2, "edge_estimates_fresh": True},
            update={"version": 7},
        )
        with _patch_contract_helpers(), patch(
            "app.strategist_promote_routes._promotion_enabled", return_value=True,
        ), patch(
            "app.strategist_promote_routes._fetch_latest_applied_row",
            return_value=(source_row, None),
        ), patch(
            "app.strategist_promote_routes._fetch_demo_soak_metrics",
            return_value=dict(_LIVE_OK_SOAK),
        ), patch(
            "app.strategist_promote_routes._apply_target_gate", new=MagicMock(),
        ), patch(
            "app.strategist_promote_routes._insert_promotion_audit",
            side_effect=RuntimeError("pg-insert-down"),
        ), patch.dict(os.environ, {"OPENCLAW_LIVE_PATCH_SECRET": "phase2-test-secret"}), patch(
            "app.strategist_promote_routes.one_shot_ipc_call", new=ipc_mock,
        ):
            resp = client.post(
                "/api/v1/strategist/promote",
                json={
                    "strategy": "grid_trading", "symbol": "BTCUSDT",
                    "source_engine": "demo", "target_engine": "live", "confirm": True,
                },
            )
        self.assertEqual(resp.status_code, 500, resp.text)
        self.assertEqual(resp.json()["detail"]["error"], "audit_write_failed")
        # The live IPC update DID fire (live already changed → must be loud).
        update_calls = [c for c in ipc_mock.call_args_list if c.args[0] == "update_strategy_params"]
        self.assertEqual(len(update_calls), 1)


# ─────────────────────────────────────────────────────────────────────────────
# §2.5 demote — EXACT restore + precondition guard
# ─────────────────────────────────────────────────────────────────────────────


def _fake_promotion_row(
    *,
    promo_id: int = 555,
    pre: dict[str, Any] | None = None,
    promoted: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if pre is None:
        pre = {"cooldown_ms": 30000, "n_levels": 8}
    if promoted is None:
        promoted = {"cooldown_ms": 45000, "n_levels": 8}
    return {
        "id": promo_id,
        "action": "promote",
        "strategy_name": "grid_trading",
        "symbol": "BTCUSDT",
        "source_engine": "demo",
        "target_engine": "live",
        "pre_promotion_params_json": pre,
        "promoted_params_json": promoted,
        "applied_at_ms": int(time.time() * 1000) - 3600_000,
    }


class TestDemote(unittest.TestCase):

    def _post_demote(self, client: TestClient, *, confirm: bool = True, promo_id: int = 555) -> Any:
        return client.post(
            "/api/v1/strategist/demote",
            json={
                "strategy": "grid_trading", "symbol": "BTCUSDT",
                "promotion_id": promo_id, "confirm": confirm,
            },
        )

    def test_demote_restores_complete_pre_promotion_set(self) -> None:
        """current-live == promoted set → demote restores COMPLETE pre set via IPC + audit."""
        app = _make_app(_operator_actor())
        client = TestClient(app)
        pre = {"cooldown_ms": 30000, "n_levels": 8}
        promoted = {"cooldown_ms": 45000, "n_levels": 8}
        promo_row = _fake_promotion_row(pre=pre, promoted=promoted)
        # current live == promoted (live untouched since promotion) → precondition passes.
        ipc_mock = _ipc_router(
            snapshot={"result": json.dumps(promoted)},
            criteria=None,
            update={"version": 8},
        )
        insert_mock = MagicMock(return_value=901)
        with patch(
            "app.strategist_promote_routes._promotion_enabled", return_value=True,
        ), patch(
            "app.strategist_promote_routes._fetch_promotion_row",
            return_value=(promo_row, None),
        ), patch(
            "app.strategist_promote_routes._apply_target_gate", new=MagicMock(),
        ), patch(
            "app.strategist_promote_routes._insert_promotion_audit", new=insert_mock,
        ), patch.dict(os.environ, {"OPENCLAW_LIVE_PATCH_SECRET": "phase2-test-secret"}), patch(
            "app.strategist_promote_routes.one_shot_ipc_call", new=ipc_mock,
        ):
            resp = self._post_demote(client)
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["action"], "demote")
        self.assertEqual(body["reverts_promotion_id"], 555)
        self.assertEqual(body["restored_params"], pre)
        # update_strategy_params dispatched with the COMPLETE pre-promotion set + token.
        update_calls = [c for c in ipc_mock.call_args_list if c.args[0] == "update_strategy_params"]
        self.assertEqual(len(update_calls), 1)
        params = update_calls[0].kwargs.get("params") or update_calls[0].args[1]
        self.assertEqual(json.loads(params["params_json"]), pre)
        self.assertTrue(
            {"live_authz_token", "live_authz_nonce", "live_authz_ts"} <= set(params)
        )
        # demote audit row: action=demote, reverts_promotion_id set, criteria_verdict=demote_exempt.
        kw = insert_mock.call_args.kwargs
        self.assertEqual(kw["action"], "demote")
        self.assertEqual(kw["reverts_promotion_id"], 555)
        self.assertEqual(kw["criteria_verdict"], "demote_exempt")
        # demote row stores promoted as 'pre' (rolled-back state) and pre as 'promoted' (restored).
        self.assertEqual(kw["pre_promotion_params"], promoted)
        self.assertEqual(kw["promoted_params"], pre)

    def test_demote_precondition_fail_returns_409(self) -> None:
        """live changed since promotion (current != promoted) → 409 live_changed_since_promotion."""
        app = _make_app(_operator_actor())
        client = TestClient(app)
        promo_row = _fake_promotion_row(
            pre={"cooldown_ms": 30000}, promoted={"cooldown_ms": 45000},
        )
        # current live differs from promoted_params_json → precondition fails.
        ipc_mock = _ipc_router(
            snapshot={"result": json.dumps({"cooldown_ms": 99999})},
            criteria=None,
            update={"version": 8},
        )
        with patch(
            "app.strategist_promote_routes._promotion_enabled", return_value=True,
        ), patch(
            "app.strategist_promote_routes._fetch_promotion_row",
            return_value=(promo_row, None),
        ), patch(
            "app.strategist_promote_routes._apply_target_gate", new=MagicMock(),
        ), patch(
            "app.strategist_promote_routes.one_shot_ipc_call", new=ipc_mock,
        ):
            resp = self._post_demote(client)
        self.assertEqual(resp.status_code, 409, resp.text)
        self.assertEqual(resp.json()["detail"]["error"], "live_changed_since_promotion")
        # No restore IPC dispatched.
        update_calls = [c for c in ipc_mock.call_args_list if c.args[0] == "update_strategy_params"]
        self.assertEqual(len(update_calls), 0)

    def test_demote_add_key_then_demote_exactness(self) -> None:
        """add-key-then-demote: promote ADDED a key → demote restores the COMPLETE pre set
        (which does NOT contain the added key), proving EXACT behavioral restore (§2.5)."""
        app = _make_app(_operator_actor())
        client = TestClient(app)
        # pre set has NO 'extra_param'; promote added it + changed cooldown.
        pre = {"cooldown_ms": 30000, "n_levels": 8}
        promoted = {"cooldown_ms": 45000, "n_levels": 8, "extra_param": 1.5}
        promo_row = _fake_promotion_row(pre=pre, promoted=promoted)
        ipc_mock = _ipc_router(
            snapshot={"result": json.dumps(promoted)},  # current live == promoted (with extra key)
            criteria=None,
            update={"version": 9},
        )
        insert_mock = MagicMock(return_value=902)
        with patch(
            "app.strategist_promote_routes._promotion_enabled", return_value=True,
        ), patch(
            "app.strategist_promote_routes._fetch_promotion_row",
            return_value=(promo_row, None),
        ), patch(
            "app.strategist_promote_routes._apply_target_gate", new=MagicMock(),
        ), patch(
            "app.strategist_promote_routes._insert_promotion_audit", new=insert_mock,
        ), patch.dict(os.environ, {"OPENCLAW_LIVE_PATCH_SECRET": "phase2-test-secret"}), patch(
            "app.strategist_promote_routes.one_shot_ipc_call", new=ipc_mock,
        ):
            resp = self._post_demote(client)
        self.assertEqual(resp.status_code, 200, resp.text)
        # Restore payload is exactly the pre set (no 'extra_param'). Rust typed deserialize
        # restores the typed struct; the added key (if non-schema) is inert and not re-sent.
        update_calls = [c for c in ipc_mock.call_args_list if c.args[0] == "update_strategy_params"]
        restored = json.loads(update_calls[0].kwargs.get("params", {}).get("params_json"))
        self.assertEqual(restored, pre)
        self.assertNotIn("extra_param", restored)

    def test_demote_flag_off_returns_409(self) -> None:
        """flag-OFF → demote 409 promotion_disabled (machine not online)."""
        app = _make_app(_operator_actor())
        client = TestClient(app)
        with patch("app.strategist_promote_routes._promotion_enabled", return_value=False):
            resp = self._post_demote(client)
        self.assertEqual(resp.status_code, 409, resp.text)
        self.assertEqual(resp.json()["detail"]["error"], "promotion_disabled")

    def test_demote_unknown_promotion_id_returns_404(self) -> None:
        app = _make_app(_operator_actor())
        client = TestClient(app)
        with patch(
            "app.strategist_promote_routes._promotion_enabled", return_value=True,
        ), patch(
            "app.strategist_promote_routes._fetch_promotion_row",
            return_value=(None, None),
        ):
            resp = self._post_demote(client, promo_id=99999)
        self.assertEqual(resp.status_code, 404, resp.text)

    def test_demote_preview_no_ipc_write(self) -> None:
        """confirm=false → precondition preview only, no update_strategy_params write."""
        app = _make_app(_operator_actor())
        client = TestClient(app)
        promo_row = _fake_promotion_row()
        ipc_mock = _ipc_router(
            snapshot={"result": json.dumps({"cooldown_ms": 45000, "n_levels": 8})},
            criteria=None, update={"version": 8},
        )
        with patch(
            "app.strategist_promote_routes._promotion_enabled", return_value=True,
        ), patch(
            "app.strategist_promote_routes._fetch_promotion_row",
            return_value=(promo_row, None),
        ), patch(
            "app.strategist_promote_routes.one_shot_ipc_call", new=ipc_mock,
        ):
            resp = self._post_demote(client, confirm=False)
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["phase"], "preview")
        update_calls = [c for c in ipc_mock.call_args_list if c.args[0] == "update_strategy_params"]
        self.assertEqual(len(update_calls), 0)


# ─────────────────────────────────────────────────────────────────────────────
# tuned-param diff helper (direction-bound input)
# ─────────────────────────────────────────────────────────────────────────────


class TestTunedParamDiff(unittest.TestCase):

    def test_diff_detects_changed_and_added_keys(self) -> None:
        from app import strategist_promote_routes as sp
        pre = {"cooldown_ms": 30000, "n_levels": 8}
        promoted = {"cooldown_ms": 45000, "n_levels": 8, "new_key": 1}
        self.assertEqual(sp._diff_tuned_param_names(pre, promoted), ["cooldown_ms", "new_key"])

    def test_diff_none_pre_all_keys_changed(self) -> None:
        from app import strategist_promote_routes as sp
        promoted = {"a": 1, "b": 2}
        self.assertEqual(sp._diff_tuned_param_names(None, promoted), ["a", "b"])

    def test_diff_no_changes_empty(self) -> None:
        from app import strategist_promote_routes as sp
        same = {"cooldown_ms": 30000, "n_levels": 8}
        self.assertEqual(sp._diff_tuned_param_names(same, dict(same)), [])


# ─────────────────────────────────────────────────────────────────────────────
# Fix 4 — REAL Python↔Rust IPC contract (param keys + verdict casing), NOT mocked
# ─────────────────────────────────────────────────────────────────────────────


class TestIpcContractKeysAndCasing(unittest.TestCase):
    """Cross the REAL route→Rust contract structurally (Mac can't run engine):
    the route's OUTGOING criteria IPC param keys must EXACTLY equal the keys the
    Rust handler reads, AND the verdict-token casing the handler emits must equal
    what the route consumes. Both sides reference the SINGLE shared contract module
    (strategist_promote_contract) — mutate either side and these BITE.

    這是 Fix 4：跨 REAL 契約而非 mock。route emit key 集合 == handler 讀 key 集合 ==
    共享常數；verdict casing handler emit == route consume。鏡像 live_authz canonical-
    contract test 風格（單一共享來源）。
    """

    def test_route_outgoing_keys_equal_shared_contract(self) -> None:
        """route's _build_criteria_ipc_params emits EXACTLY the shared-contract key set."""
        from app import strategist_promote_routes as sp
        from app import strategist_promote_contract as contract

        emitted = sp._build_criteria_ipc_params(
            strategy_name="grid_trading",
            active_symbols=["BTCUSDT", "ETHUSDT"],
            soak_metrics=dict(_LIVE_OK_SOAK),
            demo_boundary_violation_count=0,
            cost_model=dict(_FAKE_COST_MODEL),
            tuned_param_names=["cooldown_ms"],
        )
        self.assertEqual(
            set(emitted.keys()),
            set(contract.CRITERIA_OUTGOING_KEYS),
            "route OUTGOING criteria IPC keys drifted from shared contract",
        )
        # The two required keys the Rust handler hard-rejects on (ERR_INVALID_REQUEST).
        self.assertIn("strategy", emitted)
        self.assertIn("active_symbols", emitted)
        # Route sends 'strategy' (NOT the old 'strategy_name') — the bug that 503'd everything.
        self.assertNotIn("strategy_name", emitted)
        self.assertIsInstance(emitted["active_symbols"], list)

    def test_outgoing_keys_match_rust_handler_reads(self) -> None:
        """The shared contract key set must equal the params.get(...) keys in the REAL
        Rust handler source (dispatch.rs::handle_evaluate_promotion_criteria). Parse the
        Rust source and extract every params.get("<key>") inside the handler body —
        this is the structural cross-language assertion (Mac can't run the engine).
        """
        import re
        from pathlib import Path
        from app import strategist_promote_contract as contract

        # srv/rust/openclaw_engine/src/ipc_server/dispatch.rs
        srv_root = Path(__file__).resolve().parents[5]
        dispatch = srv_root / "rust" / "openclaw_engine" / "src" / "ipc_server" / "dispatch.rs"
        src = dispatch.read_text(encoding="utf-8")
        # Slice the handler body: from `fn handle_evaluate_promotion_criteria` to the next
        # top-level item (`\nfn ` / `\nmod ` / `\n#[cfg(test)]`) or EOF — the handler is the
        # last fn before the dispatch test module, so several terminators must be tolerated.
        start = src.index("fn handle_evaluate_promotion_criteria")
        rest = src[start + 1 :]
        terminators = [rest.find(t) for t in ("\nfn ", "\nmod ", "\n#[cfg(test)]")]
        terminators = [t for t in terminators if t != -1]
        end_rel = min(terminators) if terminators else len(rest)
        body = src[start : start + 1 + end_rel]
        handler_keys = set(re.findall(r'params\s*\.\s*get\(\s*"([^"]+)"', body))
        # Every key the handler reads must be a key the route sends (the contract set).
        self.assertEqual(
            handler_keys,
            set(contract.CRITERIA_OUTGOING_KEYS),
            f"Rust handler params.get keys {sorted(handler_keys)} != shared contract "
            f"{sorted(contract.CRITERIA_OUTGOING_KEYS)}",
        )

    def test_verdict_casing_handler_emits_what_route_consumes(self) -> None:
        """The Rust handler emits verdict via PromotionVerdict::tag() (lowercase). The
        shared is_eligible() must accept exactly that token. Assert the Rust tag()
        source returns the lowercase tokens the contract canonicalizes on.
        """
        from pathlib import Path
        from app import strategist_promote_contract as contract

        # is_eligible accepts the handler's lowercase tag, case-insensitively.
        self.assertTrue(contract.is_eligible("eligible"))
        self.assertTrue(contract.is_eligible("Eligible"))  # tolerant
        self.assertFalse(contract.is_eligible("pending"))
        self.assertFalse(contract.is_eligible("reject"))
        self.assertFalse(contract.is_eligible(""))
        self.assertFalse(contract.is_eligible(None))
        # The Rust tag() truly returns lowercase tokens (the contract's canonical casing).
        srv_root = Path(__file__).resolve().parents[5]
        pc = (
            srv_root / "rust" / "openclaw_engine" / "src" / "strategist_scheduler"
            / "promotion_criteria.rs"
        )
        src = pc.read_text(encoding="utf-8")
        self.assertIn('PromotionVerdict::Eligible => "eligible"', src)
        self.assertEqual(contract.ELIGIBLE_TOKEN, "eligible")


# ─────────────────────────────────────────────────────────────────────────────
# Fix 3 — promoted_params_json is the COMPLETE post-promotion set (re-read), not
# the PARTIAL source delta → demote precondition compares full-vs-full
# ─────────────────────────────────────────────────────────────────────────────


class TestPromotedFullSetReRead(unittest.TestCase):

    def test_promote_stores_reread_complete_set_not_partial_source(self) -> None:
        """source_params is a PARTIAL delta ({cooldown_ms}); after the live IPC update,
        the route RE-READS get_strategy_params{live} (complete typed set, more keys) and
        stores THAT as promoted_params_json. Proves Fix 3 (full-vs-full demote precondition).
        """
        app = _make_app(_operator_actor())
        client = TestClient(app)
        # PARTIAL source delta (only one key) — the LLM tune recommendation.
        partial_source = {"cooldown_ms": 45000}
        # COMPLETE post-promotion typed set the engine returns after the merge.
        complete_post = {"cooldown_ms": 45000, "n_levels": 8, "max_hold_ms": 600000}
        source_row = _fake_source_row(params=dict(partial_source))

        async def _side(method: str, *a: Any, **k: Any) -> Any:
            if method == "get_strategy_params":
                # Both pre-capture and post-promotion re-read return the COMPLETE set
                # (pre==post here for simplicity; the point is full-set, not partial).
                return {"result": json.dumps(complete_post)}
            if method == "evaluate_promotion_criteria":
                return {"verdict": "eligible", "reason": None,
                        "per_cell": [], "active_count": 2, "edge_estimates_fresh": True}
            if method == "update_strategy_params":
                return {"version": 7}
            raise AssertionError(f"unexpected {method}")

        ipc_mock = AsyncMock(side_effect=_side)
        insert_mock = MagicMock(return_value=777)
        with _patch_contract_helpers(), patch(
            "app.strategist_promote_routes._promotion_enabled", return_value=True,
        ), patch(
            "app.strategist_promote_routes._fetch_latest_applied_row",
            return_value=(source_row, None),
        ), patch(
            "app.strategist_promote_routes._fetch_demo_soak_metrics",
            return_value=dict(_LIVE_OK_SOAK),
        ), patch(
            "app.strategist_promote_routes._apply_target_gate", new=MagicMock(),
        ), patch(
            "app.strategist_promote_routes._insert_promotion_audit", new=insert_mock,
        ), patch.dict(os.environ, {"OPENCLAW_LIVE_PATCH_SECRET": "phase2-test-secret"}), patch(
            "app.strategist_promote_routes.one_shot_ipc_call", new=ipc_mock,
        ):
            resp = client.post(
                "/api/v1/strategist/promote",
                json={
                    "strategy": "grid_trading", "symbol": "BTCUSDT",
                    "source_engine": "demo", "target_engine": "live", "confirm": True,
                },
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        kw = insert_mock.call_args.kwargs
        # promoted_params stored = COMPLETE re-read set (has keys NOT in partial source).
        self.assertEqual(kw["promoted_params"], complete_post)
        self.assertNotEqual(kw["promoted_params"], partial_source)
        self.assertIn("n_levels", kw["promoted_params"])  # key absent from partial source
        self.assertIn("max_hold_ms", kw["promoted_params"])
        # The IPC update was still sent the PARTIAL source (that's the tune delta).
        update_calls = [c for c in ipc_mock.call_args_list if c.args[0] == "update_strategy_params"]
        sent = json.loads(update_calls[0].kwargs.get("params", {}).get("params_json"))
        self.assertEqual(sent, partial_source)


# ─────────────────────────────────────────────────────────────────────────────
# Fix 1 (Option A) — REAL config resolution (NOT mocked) — catches the
# "pinned_symbols lives under [universe], not top-level" + "[limits] envelope"
# class of silent-config bugs the mocked tests bypass.
# ─────────────────────────────────────────────────────────────────────────────


class TestRealConfigResolution(unittest.TestCase):
    """Run the REAL TOML readers (no helper patch) against the checked-in config.
    Synthetic/mocked tests bypass the actual TOML section layout → a wrong section
    path (e.g. top-level pinned_symbols instead of [universe].pinned_symbols) is a
    silent fail-closed bug (everything Reject no_active_symbols, for the WRONG reason).
    """

    def test_active_symbols_intersects_allowed_and_pinned_universe(self) -> None:
        from app import strategist_promote_routes as sp
        # funding_harvest has allowed_symbols=["BTCUSDT"] and BTCUSDT is in [universe].pinned.
        syms = sp._resolve_active_symbols("funding_harvest")
        self.assertEqual(syms, ["BTCUSDT"], "allowed∩pinned must resolve via [universe].pinned")
        # grid_trading has NO allowed_symbols set → empty (→ criteria Reject no_active_symbols).
        self.assertEqual(sp._resolve_active_symbols("grid_trading"), [])

    def test_live_cost_model_reads_slippage_ssot(self) -> None:
        from app import strategist_promote_routes as sp
        cm = sp._load_live_cost_model()
        self.assertIsNotNone(cm)
        # SSOT values from risk_config_live.toml [slippage].
        self.assertEqual(cm["cost_gate_safety_multiplier"], 1.3)
        self.assertEqual(cm["cost_gate_win_rate_floor"], 0.3)
        self.assertEqual(cm["edge_ttl_secs"], 172_800)
        # fee_bps_round_trip = 2*(0.00055 taker + 0.0005 default_rate)*10000 = 21.0.
        self.assertAlmostEqual(cm["fee_bps_round_trip"], 21.0, places=6)

    def test_boundary_reads_live_envelope_and_fail_closes_without_pg(self) -> None:
        from app import strategist_promote_routes as sp
        # On Mac (no PG) the boundary query fails → returns 1 (fail-closed, conservative).
        self.assertEqual(sp._compute_demo_boundary_violation_count("grid_trading"), 1)


if __name__ == "__main__":
    unittest.main()
