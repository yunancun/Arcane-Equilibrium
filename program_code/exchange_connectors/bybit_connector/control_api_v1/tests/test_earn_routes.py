"""
Earn Routes API Test — Sprint 1B Earn Wave C E1 IMPL（pytest + FastAPI TestClient）

MODULE_NOTE：
  模塊用途：
    對齊 docs/execution_plan/2026-05-25--earn_first_stake_gui_design_spec.md
    §4 + §6 + §9 AC 為 earn_routes.py 6 endpoint 提供 unit test 覆蓋。

  測試策略：
    - FastAPI TestClient + dependency_overrides override _get_auth_actor /
      _require_operator_for_stake；避免依賴真實 cookie / Bearer token；
    - patch.dict os.environ 控制 BYBIT_ENV / OPENCLAW_ALLOW_MAINNET / canary
      data dir；test 不依賴實機 env；
    - monkeypatch earn_routes._ipc_call_strict / _ipc_call_soft 模擬 IPC
      回傳，不啟動真實 Rust engine；
    - monkeypatch earn_routes._global_mode_is_live_reserved bool；
    - monkeypatch earn_routes._query_earn_records_pg 模擬 PG 回傳。

  測試覆蓋（per spec §9 AC + §4.3 fail-closed）：
    R1. typed_confirm_phrase 後端 case-sensitive 比對（spec AC-3）；
    R2. amount [100, 200] 範圍硬鎖 Pydantic 驗（spec §4.3）；
    R3. live_reserved 雙閘 — False → 403（spec §4.3 dual gate）；
    R4. Operator role guard — viewer → 403（spec §4.3 第 1 條）；
    R5. /preflight 5-gate 物件結構 + Stage 0R harness PENDING 空狀態
        （spec §3.3 / §5 / §7.3 AC-2 + AC-4）；
    R6. /records PG degraded fail-soft（spec §3.7 + degraded envelope）；
    R7. /balance + /products + /positions degraded 空狀態（IPC 未接 = Wave D
        carry-over 路徑）；
    R8. /stake happy path IPC mock submitted=true（spec §4.3 處理鏈）；
    R9. /stake IPC rejected_reason 透傳（per earn_router.rs E-3..E-9 fail
        分支）。

依賴：
  - app.earn_routes（被測模組）；
  - app.governance_routes._get_auth_actor（auth dep override 目標）；
  - app.main_legacy.AuthenticatedActor（actor fixture）。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from typing import Any
from unittest.mock import patch

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# PATH SETUP / 路徑設置
# ─────────────────────────────────────────────────────────────────────────────
_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.earn_routes as earn_routes_module
from app.earn_routes import earn_router
from app.governance_routes import _get_auth_actor
from app.main_legacy import AuthenticatedActor


# ─────────────────────────────────────────────────────────────────────────────
# Actor fixtures / Actor 工廠
# ─────────────────────────────────────────────────────────────────────────────


def _operator_actor() -> AuthenticatedActor:
    """Operator role actor — 可走 /stake 寫入路徑。"""
    return AuthenticatedActor(
        actor_id="test-operator",
        actor_type="human",
        roles={"operator", "viewer"},
        scopes={"private_readonly"},
    )


def _viewer_actor() -> AuthenticatedActor:
    """Viewer role actor — read-only 路徑可走，stake 應 403。"""
    return AuthenticatedActor(
        actor_id="test-viewer",
        actor_type="human",
        roles={"viewer"},
        scopes={"private_readonly"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test App factory / 測試應用工廠
# ─────────────────────────────────────────────────────────────────────────────


def _make_test_app(actor: AuthenticatedActor | None) -> FastAPI:
    """
    建立含 earn_router 與 auth dep override 的最小 FastAPI 應用。

    為什麼分 actor=None case：actor=None 模擬未認證請求；FastAPI 走真實
    _get_auth_actor 拋 401。
    """
    test_app = FastAPI()
    test_app.include_router(earn_router)
    if actor is not None:
        test_app.dependency_overrides[_get_auth_actor] = lambda: actor
    return test_app


# ─────────────────────────────────────────────────────────────────────────────
# 共用 valid stake body / Valid stake 請求 payload
# ─────────────────────────────────────────────────────────────────────────────


def _valid_stake_body(amount: int = 100) -> dict[str, Any]:
    """構造合法 stake body；amount 預設 100 對齊 OP-2 範圍下界。

    E2 round 2 (F1)：amount_usd 鎖整數;直接傳 int (非 str)。
    """
    return {
        "coin": "USDT",
        "product_id": "BYBIT_USDT_FLEXIBLE_v1",
        "amount_usd": amount,  # F1: int (不再 str cast)
        "expected_apr_bps": 800,  # 8% APR
        "rationale": "Sprint 1B first stake $100 micro pressure test per OP-2",
        "type_confirm_phrase": f"CONFIRM EARN STAKE ${amount} USDT",
    }


# ─────────────────────────────────────────────────────────────────────────────
# F3 round 2: Stage 0R HMAC sig helper / Stage 0R HMAC 簽名輔助
# ─────────────────────────────────────────────────────────────────────────────

# Test-only HMAC secret;固定避測試間 flake。
_TEST_IPC_SECRET = "test-ipc-secret-for-stage-0r-hmac"


def _sign_stage_0r_payload(payload: dict[str, Any], secret: str = _TEST_IPC_SECRET) -> dict[str, Any]:
    """模擬 harness 寫 JSON 邏輯:剔除 _hmac_sig field、計算 canonical HMAC、回填 sig。

    與 earn_routes._verify_stage_0r_hmac 對齊規則:
      - sort_keys=True + separators=(',', ':') canonical form
      - HMAC-SHA256 hex-lowercase
      - sig field 名 _hmac_sig
    """
    unsigned = {k: v for k, v in payload.items() if k != "_hmac_sig"}
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"))
    sig = hmac.new(
        secret.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    signed = dict(payload)
    signed["_hmac_sig"] = sig
    return signed


# ─────────────────────────────────────────────────────────────────────────────
# R1: typed_confirm_phrase 後端比對 / typed-confirm backend verification
# ─────────────────────────────────────────────────────────────────────────────


class TestTypedConfirmPhraseVerification:
    """R1: typed_confirm_phrase 後端 case-sensitive 比對（spec AC-3 + §6.2）。

    E2 round 2 (F1)：amount 由 Decimal 改 int；helper 簽名 (str, int) -> bool。
    """

    def test_phrase_correct_amount_100_passes(self):
        """`CONFIRM EARN STAKE $100 USDT` + amount=100 → True。"""
        assert earn_routes_module._verify_typed_confirm_phrase(
            "CONFIRM EARN STAKE $100 USDT",
            100,
        ) is True

    def test_phrase_correct_amount_200_passes(self):
        """`CONFIRM EARN STAKE $200 USDT` + amount=200 → True。"""
        assert earn_routes_module._verify_typed_confirm_phrase(
            "CONFIRM EARN STAKE $200 USDT",
            200,
        ) is True

    def test_phrase_case_sensitive_lower_rejected(self):
        """小寫變體 case-sensitive 拒絕（anti-pattern #3 防護）。"""
        assert earn_routes_module._verify_typed_confirm_phrase(
            "confirm earn stake $100 usdt",
            100,
        ) is False

    def test_phrase_amount_mismatch_rejected(self):
        """Phrase amount=100 但 body amount=200 → False（amount 必同步）。"""
        assert earn_routes_module._verify_typed_confirm_phrase(
            "CONFIRM EARN STAKE $100 USDT",
            200,
        ) is False

    def test_phrase_with_trailing_whitespace_rejected(self):
        """尾隨空白 case → 拒絕（防 operator copy-paste 帶入空白）。"""
        assert earn_routes_module._verify_typed_confirm_phrase(
            "CONFIRM EARN STAKE $100 USDT ",
            100,
        ) is False


# ─────────────────────────────────────────────────────────────────────────────
# R2: amount 範圍硬鎖 / amount range hard lock
# ─────────────────────────────────────────────────────────────────────────────


class TestAmountRangeHardLock:
    """R2: amount_usd Pydantic [100, 200] 硬鎖 + coin USDT 硬鎖。

    E2 round 2 (F1)：integer-only 後追加 +3 case 涵蓋:
       - test_amount_float_input_rejected_422 (浮點 100.5 → 422)
       - test_amount_integer_min_200_status_check (整數邊界 100/200 不被 Pydantic 擋)
       - test_amount_negative_rejected_422 (負數 -1 → 422)
    """

    def test_amount_below_min_rejected_422(self):
        """amount=99 → Pydantic 422（< $100 OP-2 範圍下界）。"""
        test_app = _make_test_app(_operator_actor())
        client = TestClient(test_app, raise_server_exceptions=False)
        body = _valid_stake_body(amount=99)
        body["type_confirm_phrase"] = "CONFIRM EARN STAKE $99 USDT"
        resp = client.post("/api/v1/earn/stake", json=body)
        assert resp.status_code == 422, (
            f"Expected 422 for amount=99, got {resp.status_code}: {resp.text}"
        )

    def test_amount_above_max_rejected_422(self):
        """amount=201 → Pydantic 422（> $200 OP-2 範圍上界）。"""
        test_app = _make_test_app(_operator_actor())
        client = TestClient(test_app, raise_server_exceptions=False)
        body = _valid_stake_body(amount=201)
        body["type_confirm_phrase"] = "CONFIRM EARN STAKE $201 USDT"
        resp = client.post("/api/v1/earn/stake", json=body)
        assert resp.status_code == 422, (
            f"Expected 422 for amount=201, got {resp.status_code}: {resp.text}"
        )

    def test_coin_not_usdt_rejected_422(self):
        """coin='BTC' → Pydantic validator 422（OP-3 鎖 USDT）。"""
        test_app = _make_test_app(_operator_actor())
        client = TestClient(test_app, raise_server_exceptions=False)
        body = _valid_stake_body(amount=100)
        body["coin"] = "BTC"
        resp = client.post("/api/v1/earn/stake", json=body)
        assert resp.status_code == 422, (
            f"Expected 422 for coin=BTC, got {resp.status_code}: {resp.text}"
        )

    # ─── F1 round 2: integer-only 新增 case ───────────────────────────────────

    def test_amount_float_input_rejected_422(self):
        """F1: amount=100.5 浮點 → Pydantic strict=True 422 (前後端對齊 integer-only)。"""
        test_app = _make_test_app(_operator_actor())
        client = TestClient(test_app, raise_server_exceptions=False)
        # 構造合法 body 但 amount 強制浮點
        body = _valid_stake_body(amount=100)
        body["amount_usd"] = 100.5  # 直接傳 float
        body["type_confirm_phrase"] = "CONFIRM EARN STAKE $100 USDT"  # phrase 對齊整數 base
        resp = client.post("/api/v1/earn/stake", json=body)
        assert resp.status_code == 422, (
            f"Expected 422 for amount=100.5 (float), got {resp.status_code}: {resp.text}"
        )

    def test_amount_integer_boundaries_pass_pydantic(self):
        """F1: amount=100 / 200 整數邊界 → 不被 Pydantic 422 擋
        (落到 _global_mode_is_live_reserved gate 後續流程,test 端 mock 該 gate 為 False
        → 403,不應是 422)。
        """
        test_app = _make_test_app(_operator_actor())
        client = TestClient(test_app, raise_server_exceptions=False)
        for amount in (100, 200):
            body = _valid_stake_body(amount=amount)
            with patch.object(
                earn_routes_module,
                "_global_mode_is_live_reserved",
                return_value=False,  # 強制走 live_reserved fail 路徑
            ):
                resp = client.post("/api/v1/earn/stake", json=body)
            # Pydantic 422 應該過;後續 live_reserved gate fail 是 403
            assert resp.status_code != 422, (
                f"amount={amount} (boundary int) unexpectedly hit Pydantic 422: {resp.text}"
            )
            assert resp.status_code == 403, (
                f"amount={amount} expected 403 (live_reserved fail), got {resp.status_code}"
            )

    def test_amount_negative_rejected_422(self):
        """F1: amount=-1 → Pydantic 422 (ge=100 觸發, defense-in-depth 避負值繞 Decimal cast)。"""
        test_app = _make_test_app(_operator_actor())
        client = TestClient(test_app, raise_server_exceptions=False)
        body = _valid_stake_body(amount=100)
        body["amount_usd"] = -1
        resp = client.post("/api/v1/earn/stake", json=body)
        assert resp.status_code == 422, (
            f"Expected 422 for amount=-1, got {resp.status_code}: {resp.text}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# R3: live_reserved 雙閘 / live_reserved dual gate
# ─────────────────────────────────────────────────────────────────────────────


class TestLiveReservedDualGate:
    """R3: live_reserved global mode 必為 True 才允許 stake（spec §4.3 dual gate）。"""

    def test_stake_blocked_when_not_live_reserved(self):
        """global mode != live_reserved → 403 + global_mode_not_live_reserved。"""
        test_app = _make_test_app(_operator_actor())
        client = TestClient(test_app, raise_server_exceptions=False)

        with patch.object(
            earn_routes_module,
            "_global_mode_is_live_reserved",
            return_value=False,
        ):
            resp = client.post("/api/v1/earn/stake", json=_valid_stake_body())

        assert resp.status_code == 403
        payload = resp.json()
        detail = payload.get("detail") or {}
        assert "global_mode_not_live_reserved" in (detail.get("reason_codes") or [])


# ─────────────────────────────────────────────────────────────────────────────
# R4: Operator role guard / Operator 角色守衛
# ─────────────────────────────────────────────────────────────────────────────


class TestOperatorRoleGuard:
    """R4: POST /stake 需 Operator 角色；非 Operator → 403。"""

    def test_stake_viewer_returns_403(self):
        """Viewer 走 stake → 403（_require_operator_role 把關）。"""
        test_app = _make_test_app(_viewer_actor())
        client = TestClient(test_app, raise_server_exceptions=False)
        resp = client.post("/api/v1/earn/stake", json=_valid_stake_body())
        assert resp.status_code == 403, (
            f"Expected 403 for viewer, got {resp.status_code}: {resp.text}"
        )

    def test_balance_viewer_allowed(self):
        """Viewer GET /balance 允許（read-only 路徑不需 Operator）。"""
        test_app = _make_test_app(_viewer_actor())
        client = TestClient(test_app, raise_server_exceptions=False)
        # 走 fail-soft 路徑（IPC 不可達）— 預期 200 + degraded=True
        resp = client.get("/api/v1/earn/balance")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload.get("ok") is True
        # degraded 因為 test 環境 IPC 不可達；data 仍有空狀態 default
        data = payload.get("data") or {}
        assert "usdt_balance" in data
        assert "recon_status" in data


# ─────────────────────────────────────────────────────────────────────────────
# R5: /preflight 5-gate 結構 / preflight 5-gate structure
# ─────────────────────────────────────────────────────────────────────────────


class TestPreflightEndpoint:
    """R5: GET /preflight 5-gate 物件 + Stage 0R 子物件 schema（AC-2 + AC-4）。"""

    def test_preflight_returns_5_gates_plus_stage_0r(self, tmp_path):
        """preflight payload 含 5 gate + stage_0r + all_pass + live_reserved。"""
        test_app = _make_test_app(_operator_actor())
        client = TestClient(test_app, raise_server_exceptions=False)

        # 用 tmp_path 作 canary dir → 預期 Stage 0R PENDING（無 JSON）
        canary_dir = tmp_path / "canary"
        canary_dir.mkdir()
        with patch.dict(os.environ, {"OPENCLAW_DATA_DIR": str(tmp_path)}):
            # 清緩存避免上輪 test 影響
            earn_routes_module._PREFLIGHT_CACHE = (0.0, None)
            resp = client.get("/api/v1/earn/preflight")

        assert resp.status_code == 200, resp.text
        payload = resp.json()
        data = payload.get("data") or {}
        for key in ("gate_a", "gate_b", "gate_c", "gate_d", "gate_e"):
            assert key in data, f"missing {key} in preflight payload"
            assert "status" in data[key], f"missing status in {key}"
        assert "stage_0r" in data
        assert data["stage_0r"].get("status") == "PENDING"
        assert data["stage_0r"].get("json_path") is None
        assert "all_pass" in data
        assert "live_reserved" in data

    def test_preflight_stage_0r_pass_when_eligible_json_fresh(self, tmp_path):
        """Stage 0R JSON eligible=True + age<24h + 有效 HMAC sig → status=PASS。

        E2 round 2 (F3)：JSON 必含 _hmac_sig field 才會通過後端 HMAC verify。
        """
        test_app = _make_test_app(_operator_actor())
        client = TestClient(test_app, raise_server_exceptions=False)

        canary_dir = tmp_path / "canary"
        canary_dir.mkdir()
        json_path = canary_dir / "earn_first_stake_stage0r_20260526.json"
        # F3: 構造合法 signed payload
        signed = _sign_stage_0r_payload({
            "eligible_for_first_stake": True,
            "reasons": [],
        })
        json_path.write_text(json.dumps(signed))

        with patch.dict(os.environ, {
            "OPENCLAW_DATA_DIR": str(tmp_path),
            "OPENCLAW_IPC_SECRET": _TEST_IPC_SECRET,
        }):
            earn_routes_module._PREFLIGHT_CACHE = (0.0, None)
            resp = client.get("/api/v1/earn/preflight")

        assert resp.status_code == 200
        stage_0r = (resp.json().get("data") or {}).get("stage_0r") or {}
        assert stage_0r.get("status") == "PASS"
        assert stage_0r.get("eligible_for_first_stake") is True

    def test_preflight_stage_0r_fail_when_not_eligible(self, tmp_path):
        """Stage 0R JSON eligible=False + 有效 HMAC sig → status=FAIL + fail_reasons 透傳。"""
        test_app = _make_test_app(_operator_actor())
        client = TestClient(test_app, raise_server_exceptions=False)

        canary_dir = tmp_path / "canary"
        canary_dir.mkdir()
        json_path = canary_dir / "earn_first_stake_stage0r_20260526.json"
        # F3: 合法 sig 才能進入 eligible=False FAIL 路徑
        signed = _sign_stage_0r_payload({
            "eligible_for_first_stake": False,
            "reasons": ["apy_drift > 5pct"],
        })
        json_path.write_text(json.dumps(signed))

        with patch.dict(os.environ, {
            "OPENCLAW_DATA_DIR": str(tmp_path),
            "OPENCLAW_IPC_SECRET": _TEST_IPC_SECRET,
        }):
            earn_routes_module._PREFLIGHT_CACHE = (0.0, None)
            resp = client.get("/api/v1/earn/preflight")

        stage_0r = (resp.json().get("data") or {}).get("stage_0r") or {}
        assert stage_0r.get("status") == "FAIL"
        assert "apy_drift > 5pct" in stage_0r.get("fail_reasons", [])

    # ─── F3 round 2: HMAC 防偽新增 case ───────────────────────────────────────

    def test_preflight_stage_0r_hmac_tampered_returns_pending(self, tmp_path):
        """F3: 惡意 actor 把 eligible_for_first_stake 從 false 改 true 但 sig 不變
        → 後端 HMAC verify mismatch → status=PENDING + 'stage_0r_hmac_mismatch'。
        為什麼這條 case 救命:防 cron user 以外 actor 直接 vim JSON 繞 first stake 5-gate。
        """
        test_app = _make_test_app(_operator_actor())
        client = TestClient(test_app, raise_server_exceptions=False)

        canary_dir = tmp_path / "canary"
        canary_dir.mkdir()
        json_path = canary_dir / "earn_first_stake_stage0r_20260526.json"

        # Step 1: 用合法 false payload sign
        signed = _sign_stage_0r_payload({
            "eligible_for_first_stake": False,
            "reasons": ["check_failed"],
        })
        # Step 2: 模擬 tamper — 把 eligible 改成 true 但 sig 不重簽
        tampered = dict(signed)
        tampered["eligible_for_first_stake"] = True  # 攻擊向量:cron user 外的 actor 想繞 gate
        json_path.write_text(json.dumps(tampered))

        with patch.dict(os.environ, {
            "OPENCLAW_DATA_DIR": str(tmp_path),
            "OPENCLAW_IPC_SECRET": _TEST_IPC_SECRET,
        }):
            earn_routes_module._PREFLIGHT_CACHE = (0.0, None)
            resp = client.get("/api/v1/earn/preflight")

        stage_0r = (resp.json().get("data") or {}).get("stage_0r") or {}
        assert stage_0r.get("status") == "PENDING", (
            f"HMAC mismatch 應 fail-closed PENDING (不放行 stake), got {stage_0r.get('status')}"
        )
        assert "stage_0r_hmac_mismatch" in (stage_0r.get("fail_reasons") or [])
        assert stage_0r.get("eligible_for_first_stake") is None


# ─────────────────────────────────────────────────────────────────────────────
# R6: /records PG fail-soft / records PG degraded
# ─────────────────────────────────────────────────────────────────────────────


class TestRecordsPgDegraded:
    """R6: PG 不可達時 /records 走 degraded 而非 500。"""

    def test_records_pg_unavailable_returns_degraded(self):
        """PG pool 不可達 → degraded=True + empty records + total=0。"""
        test_app = _make_test_app(_operator_actor())
        client = TestClient(test_app, raise_server_exceptions=False)

        with patch.object(
            earn_routes_module,
            "_query_earn_records_pg",
            return_value=([], None),
        ):
            resp = client.get("/api/v1/earn/records")

        assert resp.status_code == 200
        payload = resp.json()
        assert payload.get("degraded") is True
        assert payload.get("reason") == "earn_records_pg_unavailable"
        data = payload.get("data") or {}
        assert data.get("records") == []
        assert data.get("total") == 0

    def test_records_pg_happy_path_returns_rows(self):
        """PG 回傳 1 row → degraded=False + rows + total。"""
        test_app = _make_test_app(_operator_actor())
        client = TestClient(test_app, raise_server_exceptions=False)

        mock_rows = [
            {
                "movement_id": 1,
                "event_ts_utc": "2026-05-26T10:00:00+00:00",
                "direction": "stake",
                "amount_usdt": "100.00",
                "apr_at_time": 0.08,
                "governance_approval_id": 42,
                "bybit_response_payload": {"ret_code": 0},
                "engine_mode": "live_demo",
                "api_scope_used": "account:earn:write",
                "reconciliation_status": "matched",
            }
        ]
        with patch.object(
            earn_routes_module,
            "_query_earn_records_pg",
            return_value=(mock_rows, 1),
        ):
            resp = client.get("/api/v1/earn/records?direction=stake")

        payload = resp.json()
        assert payload.get("degraded") is False
        data = payload.get("data") or {}
        assert data.get("total") == 1
        assert data["records"][0]["direction"] == "stake"


# ─────────────────────────────────────────────────────────────────────────────
# R7: /balance + /products + /positions degraded / IPC 未接通空狀態
# ─────────────────────────────────────────────────────────────────────────────


class TestReadOnlyEndpointsDegraded:
    """R7: 3 個 IPC-driven GET 端點在 IPC 未接通時走 degraded fail-soft。"""

    def test_balance_ipc_unavailable_returns_degraded_default(self):
        """IPC 不可達 → degraded=True + 0.00 default + recon_status pending_first_stake。"""
        test_app = _make_test_app(_operator_actor())
        client = TestClient(test_app, raise_server_exceptions=False)

        async def _ipc_unavailable(method, params):
            return (None, "ipc_engine_not_connected")

        with patch.object(earn_routes_module, "_ipc_call_soft", _ipc_unavailable):
            resp = client.get("/api/v1/earn/balance")

        payload = resp.json()
        assert payload.get("degraded") is True
        data = payload.get("data") or {}
        assert data.get("recon_status") == "pending_first_stake"

    def test_products_ipc_unavailable_returns_empty(self):
        """IPC 不可達 → products=[] + filtered_for=USDT_FlexibleSaving。"""
        test_app = _make_test_app(_operator_actor())
        client = TestClient(test_app, raise_server_exceptions=False)

        async def _ipc_unavailable(method, params):
            return (None, "ipc_engine_not_connected")

        with patch.object(earn_routes_module, "_ipc_call_soft", _ipc_unavailable):
            resp = client.get("/api/v1/earn/products")

        payload = resp.json()
        assert payload.get("degraded") is True
        data = payload.get("data") or {}
        assert data.get("products") == []
        assert data.get("filtered_for") == "USDT_FlexibleSaving"

    def test_positions_ipc_unavailable_returns_empty(self):
        """IPC 不可達 → positions=[] + degraded（first stake 前空狀態）。"""
        test_app = _make_test_app(_operator_actor())
        client = TestClient(test_app, raise_server_exceptions=False)

        async def _ipc_unavailable(method, params):
            return (None, "ipc_engine_not_connected")

        with patch.object(earn_routes_module, "_ipc_call_soft", _ipc_unavailable):
            resp = client.get("/api/v1/earn/positions")

        payload = resp.json()
        assert payload.get("degraded") is True
        data = payload.get("data") or {}
        assert data.get("positions") == []


# ─────────────────────────────────────────────────────────────────────────────
# R8 + R9: /stake happy path + reject reason 透傳
# ─────────────────────────────────────────────────────────────────────────────


class TestStakeIPCDispatch:
    """R8 + R9: stake 走 IPC strict + IntentResult 透傳結構。"""

    def test_stake_happy_path_submitted_true(self):
        """live_reserved=True + phrase match + IPC submitted=True → 200 + submitted=true。"""
        test_app = _make_test_app(_operator_actor())
        client = TestClient(test_app, raise_server_exceptions=False)

        async def _ipc_strict_ok(method, params, timeout=None):
            return {
                "submitted": True,
                "rejected_reason": None,
                "lease_id": "lease-uuid-abc",
                "movement_id": 7,
                "intent_id": "earn-EARN_STAKE-USDT-approval-actor",
                "bybit_response": {"order_id": "bybit-ord-1"},
            }

        with patch.object(
            earn_routes_module,
            "_global_mode_is_live_reserved",
            return_value=True,
        ), patch.object(
            earn_routes_module,
            "_ipc_call_strict",
            _ipc_strict_ok,
        ):
            resp = client.post("/api/v1/earn/stake", json=_valid_stake_body())

        assert resp.status_code == 200, resp.text
        payload = resp.json()
        data = payload.get("data") or {}
        assert data.get("submitted") is True
        assert data.get("rejected_reason") is None
        assert data.get("lease_id") == "lease-uuid-abc"
        assert data.get("movement_id") == 7
        # audit footer
        audit = payload.get("_audit") or {}
        assert audit.get("actor") == "test-operator"
        assert "trace_id" in audit

    def test_stake_ipc_contract_params_match_rust_method(self):
        """Route sends the exact Rust `process_earn_intent` contract shape."""
        test_app = _make_test_app(_operator_actor())
        client = TestClient(test_app, raise_server_exceptions=False)
        captured: dict[str, Any] = {}

        async def _ipc_strict_contract(method, params, timeout=None):
            captured["method"] = method
            captured["params"] = dict(params)
            captured["timeout"] = timeout
            return {
                "submitted": False,
                "rejected_reason": "earn_dispatch_unwired: bybit_earn_client not injected",
                "lease_id": None,
                "intent_id": None,
                "movement_id": None,
                "bybit_response": None,
            }

        with patch.object(
            earn_routes_module,
            "_global_mode_is_live_reserved",
            return_value=True,
        ), patch.object(
            earn_routes_module,
            "_ipc_call_strict",
            _ipc_strict_contract,
        ):
            resp = client.post("/api/v1/earn/stake", json=_valid_stake_body(amount=100))

        assert resp.status_code == 200, resp.text
        assert captured["method"] == "process_earn_intent"
        assert captured["timeout"] == earn_routes_module._IPC_STAKE_TIMEOUT_SEC
        params = captured["params"]
        assert set(params) == {
            "coin",
            "product_id",
            "amount_usdt",
            "expected_apr_bps",
            "rationale",
            "actor_id",
            "submitted_ts_ms",
            "trace_id",
        }
        assert params["coin"] == "USDT"
        assert params["product_id"] == "BYBIT_USDT_FLEXIBLE_v1"
        assert params["amount_usdt"] == "100"
        assert params["expected_apr_bps"] == 800
        assert params["actor_id"] == "test-operator"
        assert isinstance(params["submitted_ts_ms"], int)
        assert isinstance(params["trace_id"], str)
        assert params["trace_id"].count("-") >= 1
        data = resp.json().get("data") or {}
        assert data.get("submitted") is False
        assert "earn_dispatch_unwired" in (data.get("rejected_reason") or "")

    def test_stake_ipc_returns_rejected_reason_propagates(self):
        """IPC 回 submitted=false + rejected_reason → 200 + 透傳 reason。"""
        test_app = _make_test_app(_operator_actor())
        client = TestClient(test_app, raise_server_exceptions=False)

        async def _ipc_strict_reject(method, params, timeout=None):
            return {
                "submitted": False,
                "rejected_reason": "earn_dispatch_governance_not_authorized",
                "lease_id": None,
                "movement_id": None,
            }

        with patch.object(
            earn_routes_module,
            "_global_mode_is_live_reserved",
            return_value=True,
        ), patch.object(
            earn_routes_module,
            "_ipc_call_strict",
            _ipc_strict_reject,
        ):
            resp = client.post("/api/v1/earn/stake", json=_valid_stake_body())

        # 注意：rejected 仍走 HTTP 200 + submitted=false（per spec §4.3 Rust
        # IntentResult contract）；GUI 顯示 reason 而非 fail-toast。
        assert resp.status_code == 200
        data = resp.json().get("data") or {}
        assert data.get("submitted") is False
        assert data.get("rejected_reason") == "earn_dispatch_governance_not_authorized"

    def test_stake_phrase_mismatch_returns_400(self):
        """Phrase mismatch（amount=100 但 phrase 寫 $200）→ 400。"""
        test_app = _make_test_app(_operator_actor())
        client = TestClient(test_app, raise_server_exceptions=False)

        body = _valid_stake_body(amount=100)
        # 故意打錯 phrase
        body["type_confirm_phrase"] = "CONFIRM EARN STAKE $200 USDT"

        with patch.object(
            earn_routes_module,
            "_global_mode_is_live_reserved",
            return_value=True,
        ):
            resp = client.post("/api/v1/earn/stake", json=body)

        assert resp.status_code == 400
        detail = (resp.json().get("detail") or {})
        assert "phrase_mismatch" in (detail.get("reason_codes") or [])

    # ─── F4 round 2: Wave D carry-over graceful None handling ─────────────────

    def test_stake_wave_d_pending_when_intent_movement_none(self):
        """F4: IPC submitted=True 但 intent_id + movement_id 都 None (Wave D 未接通)
        → 不 crash、不 KeyError;data.wave_d_pending=True 給 GUI 顯示 'pending Wave D'。
        為什麼這條 case 救命:Wave D 接通前 Rust 端 IntentResult wrapper 不補 field,
        Python 端不能假設 dict 必含這 2 key,需 graceful None。
        """
        test_app = _make_test_app(_operator_actor())
        client = TestClient(test_app, raise_server_exceptions=False)

        async def _ipc_strict_partial(method, params, timeout=None):
            # Wave D carry-over: Rust 端 IntentResult patch 未接,intent_id/
            # movement_id 都 None;但 submitted=True (Rust 9-gate 通過)。
            return {
                "submitted": True,
                "rejected_reason": None,
                "lease_id": "lease-uuid-wave-c-only",
                # intent_id 不存在
                # movement_id 不存在
                # bybit_response 不存在
            }

        with patch.object(
            earn_routes_module,
            "_global_mode_is_live_reserved",
            return_value=True,
        ), patch.object(
            earn_routes_module,
            "_ipc_call_strict",
            _ipc_strict_partial,
        ):
            resp = client.post("/api/v1/earn/stake", json=_valid_stake_body())

        assert resp.status_code == 200, f"graceful None 不應 crash 500: {resp.text}"
        data = resp.json().get("data") or {}
        assert data.get("submitted") is True
        assert data.get("intent_id") is None  # graceful default
        assert data.get("movement_id") is None
        assert data.get("bybit_response") is None
        # Wave D pending hint 給 GUI 渲染:
        assert data.get("wave_d_pending") is True
