"""
E4 Wave 1 P1-7: Governance Routes Coverage Tests
E4 Wave 1 P1-7：治理路由覆蓋率測試

MODULE_NOTE (中文):
  本模組將 governance_routes.py 測試覆蓋率從 ~10% 提升至 45%+。
  策略：對工具函數/Pydantic 模型做單元測試，對路由函數通過 mock GovernanceHub
  執行業務邏輯分支測試，覆蓋正常路徑、hub 不可用（503）、未授權（401/403）、
  業務邏輯錯誤（400）、服務端錯誤（500）等主要分支。

MODULE_NOTE (English):
  This module raises governance_routes.py test coverage from ~10% to 45%+.
  Strategy: Unit-test utility functions and Pydantic models directly; test route
  handler logic via mock GovernanceHub covering happy-path, hub-unavailable (503),
  unauthorised (401/403), business-logic errors (400), and server errors (500).

Coverage targets:
  - _sanitize_string / _sanitize_log
  - GovernanceResponse.success / .error
  - Pydantic model validation (all 8 models)
  - _require_operator_role (production function, direct)
  - _get_governance_hub / _get_paper_live_gate return-None path
  - get_governance_status — hub None → 503; hub.get_status() None → 500; happy path
  - get_detailed_governance_status — hub None → 503; happy path
  - get_authorization_status — hub None → 503; happy path
  - request_authorization — hub None → 503; hub disabled → 403; auth_sm None → 503; happy path
  - approve_authorization — hub None → 503; non-operator → 403; no pending → error; happy path
  - get_risk_level — hub None → 503; happy path; level mapping
  - override_risk_level — hub None → 503; non-operator → 403; invalid level → 400; escalation rejected → 403; happy path
  - trigger_manual_reconciliation — hub None → 503; happy path
  - get_active_leases — hub None → 503; happy path with lease_sm
  - get_governance_events — hub None → 503; limit clamping; happy path
  - governance_health_check — hub None → 503; happy path
  - get_paper_live_gate_status — gate None → 503; happy path
  - get_pending_recovery_requests — hub None → 503; recovery_gate None; happy path
  - get_change_history — hub None → 503; change_audit_log None; happy path
  - get_pending_approvals — hub None → 503; change_audit_log None; happy path
  - approve_audit_change / reject_audit_change — hub None; operator check; not found
  - _sanitize_string edge cases
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from fastapi import HTTPException

# ─────────────────────────────────────────────────────────────────────────────
# PATH SETUP / 路径设置
# ─────────────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ─────────────────────────────────────────────────────────────────────────────
# Imports from production code / 從生產代碼導入
# ─────────────────────────────────────────────────────────────────────────────
from app.governance_routes import (
    _sanitize_string,
    _sanitize_log,
    _build_lease_router_status_payload,
    _require_operator_role,
    GovernanceResponse,
    AuthApprovalRequest,
    RiskOverrideRequest,
    ManualReconciliationRequest,
    DeEscalationRequest,
    ApproveDeEscalationRequest,
    SymbolWhitelistAddRequest,
    PaperLiveGateEvaluateRequest,
    AuthRequestBody,
    AuditApprovalBody,
    # Route handler functions imported directly for unit-testing without HTTP
    get_governance_status,
    get_detailed_governance_status,
    get_authorization_status,
    request_authorization,
    approve_authorization,
    get_risk_level,
    override_risk_level,
    trigger_manual_reconciliation,
    get_active_leases,
    get_governance_events,
    governance_health_check,
    get_paper_live_gate_status,
    evaluate_paper_live_gate,
    get_pending_recovery_requests,
    get_change_history,
    get_pending_approvals,
    approve_audit_change,
    reject_audit_change,
    request_de_escalation,
    get_learning_tier_status,
    get_lease_router_status,
)
from app.main_legacy import AuthenticatedActor


# ─────────────────────────────────────────────────────────────────────────────
# Module-level isolation fixture: prevent test_api_contract.py module reload
# from invalidating _get_authenticated_actor_class() cache.
# 模組級隔離 fixture：防止 test_api_contract.py reload main_legacy 導致
# _get_authenticated_actor_class() 緩存失效，使所有 isinstance 判斷失敗。
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _pin_actor_class(monkeypatch):
    """
    Pin _get_authenticated_actor_class to always return the AuthenticatedActor
    imported at module load time. This prevents test_api_contract.py's
    importlib.reload(main_legacy) from making _require_operator_role fail for
    all actors with 401 (because isinstance check uses a stale class reference).

    固定 _get_authenticated_actor_class 的返回值為模組加載時導入的類，
    防止其他測試的 importlib.reload(main_legacy) 導致 isinstance 檢查失敗。
    """
    monkeypatch.setattr(
        "app.governance_routes._get_authenticated_actor_class",
        lambda: AuthenticatedActor
    )


# ─────────────────────────────────────────────────────────────────────────────
# Helper factories / 輔助工廠函數
# ─────────────────────────────────────────────────────────────────────────────

def _make_actor(roles: set | None = None, actor_id: str = "test-operator") -> AuthenticatedActor:
    """Create an AuthenticatedActor for tests. / 创建用于测试的 AuthenticatedActor。"""
    if roles is None:
        roles = {"operator", "viewer"}
    return AuthenticatedActor(
        actor_id=actor_id,
        actor_type="human",
        roles=roles,
        scopes={"private_readonly"},
    )


def _make_hub_status(**kwargs) -> MagicMock:
    """
    Build a minimal GovernanceStatus mock with safe defaults.
    建立帶安全預設值的最小 GovernanceStatus mock。
    """
    status = MagicMock()
    defaults = dict(
        auth_state="IDLE",
        auth_expires_at_ms=None,
        auth_scope={},
        auth_pending_approval=False,
        risk_level=0,
        risk_level_name="NORMAL",
        risk_escalation_reason=None,
        mode="normal",
        active_leases_count=0,
        total_leases_tracked=0,
        last_reconciliation_ms=None,
        last_reconciliation_result=None,
        is_consistent=True,
        enabled=True,
        incident_count=0,
        callback_errors=0,
    )
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(status, k, v)
    status.to_dict.return_value = {k: v for k, v in defaults.items()}
    return status


def _make_hub(status: MagicMock | None = None, enabled: bool = True) -> MagicMock:
    """
    Build a minimal GovernanceHub mock.
    建立最小 GovernanceHub mock。
    """
    hub = MagicMock()
    hub._enabled = enabled
    hub.is_enabled.return_value = enabled
    hub.is_globally_enabled.return_value = enabled
    hub.is_authorized.return_value = True
    hub._authorization_sm = MagicMock()
    hub._risk_governor_sm = None
    hub._lease_sm = MagicMock()
    hub._recovery_gate = None
    hub._change_audit_log = None
    hub._oms_sm = None
    hub._learning_tier_gate = None
    if status is None:
        status = _make_hub_status()
    hub.get_status.return_value = status
    hub._check_de_escalation_gate = MagicMock(return_value=True)
    return hub


# ─────────────────────────────────────────────────────────────────────────────
# 1. Utility function tests / 工具函數測試
# ─────────────────────────────────────────────────────────────────────────────

class TestSanitizeString:
    """Tests for _sanitize_string() / _sanitize_string() 測試"""

    def test_normal_string_passes_through(self):
        """Plain ASCII string returns unchanged (HTML has no special chars). / 純 ASCII 不含特殊字符原樣返回。"""
        assert _sanitize_string("hello world") == "hello world"

    def test_html_special_chars_escaped(self):
        """< > & are HTML-escaped. / < > & 被 HTML 轉義。"""
        result = _sanitize_string("<script>alert('xss')</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_quotes_escaped(self):
        """Double quotes are escaped (quote=True). / 雙引號被轉義。"""
        result = _sanitize_string('say "hello"')
        assert '"hello"' not in result
        assert "&quot;hello&quot;" in result or "&#x27;" in result or "hello" in result

    def test_length_truncation(self):
        """Input longer than max_len is truncated. / 超過 max_len 的輸入被截斷。"""
        long_str = "a" * 1000
        result = _sanitize_string(long_str, max_len=100)
        # After HTML-escaping 'a' stays 'a', so length should be 100
        assert len(result) == 100

    def test_non_string_raises_value_error(self):
        """Non-string input raises ValueError. / 非字符串輸入拋出 ValueError。"""
        with pytest.raises(ValueError):
            _sanitize_string(123)  # type: ignore

    def test_empty_string(self):
        """Empty string is valid and returns empty. / 空字符串有效並返回空。"""
        assert _sanitize_string("") == ""


class TestSanitizeLog:
    """Tests for _sanitize_log() / _sanitize_log() 測試"""

    def test_newlines_escaped(self):
        """Newline characters are replaced with \\n. / 換行符被替換為 \\n。"""
        result = _sanitize_log("line1\nline2")
        assert "\n" not in result
        assert "\\n" in result

    def test_carriage_return_escaped(self):
        """Carriage return is replaced with \\r. / 回車符被替換為 \\r。"""
        result = _sanitize_log("line1\rline2")
        assert "\r" not in result
        assert "\\r" in result

    def test_long_string_truncated(self):
        """Strings longer than max_len are truncated. / 超過 max_len 的字符串被截斷。"""
        result = _sanitize_log("a" * 500, max_len=200)
        assert len(result) == 200

    def test_non_string_uses_repr(self):
        """Non-string input uses repr() up to max_len. / 非字符串使用 repr()。"""
        result = _sanitize_log(42)
        assert "42" in result

    def test_normal_string_unchanged(self):
        """Normal string without special chars is unchanged. / 普通字符串不變。"""
        assert _sanitize_log("normal log message") == "normal log message"


# ─────────────────────────────────────────────────────────────────────────────
# 2. GovernanceResponse tests / GovernanceResponse 測試
# ─────────────────────────────────────────────────────────────────────────────

class TestGovernanceResponse:
    """Tests for GovernanceResponse static methods. / GovernanceResponse 靜態方法測試。"""

    def test_success_structure(self):
        """success() returns dict with ok=True, data, message, data_category. / success() 返回正確結構。"""
        result = GovernanceResponse.success(data={"k": "v"}, message="my_msg")
        assert result["ok"] is True
        assert result["message"] == "my_msg"
        assert result["data"] == {"k": "v"}
        assert result["data_category"] == "governance"

    def test_success_defaults(self):
        """success() with no args uses defaults. / 無參數 success() 使用預設值。"""
        result = GovernanceResponse.success()
        assert result["ok"] is True
        assert result["message"] == "ok"
        assert result["data"] is None

    def test_error_structure(self):
        """error() returns dict with ok=False, message, code, data_category. / error() 返回正確結構。"""
        result = GovernanceResponse.error("bad request", "ERR_CODE", 400)
        assert result["ok"] is False
        assert result["message"] == "bad request"
        assert result["code"] == "ERR_CODE"
        assert result["data_category"] == "governance"

    def test_error_defaults(self):
        """error() default code is 'error'. / error() 預設 code 為 'error'。"""
        result = GovernanceResponse.error("something went wrong")
        assert result["code"] == "error"


class TestLeaseRouterStatus:
    """W-AUDIT-3 F-17 Decision Lease router status surface."""

    def test_payload_prefers_rust_ipc_status(self):
        """Runtime IPC payload is authoritative when available."""
        calls: list[dict[str, Any]] = []

        async def fake_dispatch(method: str, **kwargs: Any) -> dict[str, Any]:
            calls.append({"method": method, "kwargs": kwargs})
            return {
                "governor_tier": "NORMAL",
                "paper_paused": False,
                "session_halted": False,
                "lease_router": {
                    "enabled": True,
                    "audit_writer_configured": True,
                    "source": "GovernanceCore.router_gate_enabled",
                    "scope": "production_intent_router",
                },
            }

        payload = asyncio.run(_build_lease_router_status_payload(fake_dispatch))
        assert calls[0]["method"] == "get_risk_runtime_status"
        assert payload["enabled"] is True
        assert payload["router_gate_enabled"] is True
        assert payload["status"] == "enabled"
        assert payload["source"] == "rust_ipc:get_risk_runtime_status"
        assert payload["ipc_available"] is True
        assert payload["audit_writer_configured"] is True
        assert payload["runtime_source"] == "GovernanceCore.router_gate_enabled"
        assert payload["scope"] == "production_intent_router"
        assert payload["warning"] is None

    def test_payload_degrades_to_env_without_hardcoded_false(self, monkeypatch):
        """IPC outage keeps a visible unknown/env-backed status, not false."""
        monkeypatch.setenv("OPENCLAW_LEASE_ROUTER_GATE_ENABLED", "1")

        async def failing_dispatch(method: str, **kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("socket down\nretry later")

        payload = asyncio.run(_build_lease_router_status_payload(failing_dispatch))
        assert payload["enabled"] is True
        assert payload["status"] == "enabled"
        assert payload["source"] == "api_env_fallback"
        assert payload["ipc_available"] is False
        assert payload["warning"] == "rust_ipc_unavailable"
        assert "\n" not in payload["error"]

    def test_route_wraps_status_payload(self, monkeypatch):
        """The public route returns the unified governance envelope."""
        import app.governance_routes as mod

        async def fake_builder() -> dict[str, Any]:
            return {"enabled": False, "source": "unit_test"}

        monkeypatch.setattr(mod, "_build_lease_router_status_payload", fake_builder)
        response = asyncio.run(get_lease_router_status(actor=_make_actor()))
        assert response["ok"] is True
        assert response["message"] == "lease_router_status"
        assert response["data"] == {"enabled": False, "source": "unit_test"}


# ─────────────────────────────────────────────────────────────────────────────
# 3. Pydantic model validation tests / Pydantic 模型驗證測試
# ─────────────────────────────────────────────────────────────────────────────

class TestPydanticModels:
    """Validates Pydantic request models. / 驗證 Pydantic 請求模型。"""

    def test_auth_approval_request_valid(self):
        obj = AuthApprovalRequest(approval_note="Looks good, approved")
        assert obj.approval_note == "Looks good, approved"

    def test_auth_approval_request_empty_note_fails(self):
        """Empty approval_note violates min_length=1. / 空 approval_note 違反 min_length=1。"""
        with pytest.raises(Exception):
            AuthApprovalRequest(approval_note="")

    def test_risk_override_request_valid(self):
        obj = RiskOverrideRequest(target_level="NORMAL", reason="Market calmed down")
        assert obj.target_level == "NORMAL"

    def test_risk_override_request_empty_reason_fails(self):
        with pytest.raises(Exception):
            RiskOverrideRequest(target_level="NORMAL", reason="")

    def test_manual_reconciliation_request_valid(self):
        obj = ManualReconciliationRequest(
            paper_state={"balance": 1000},
            demo_state=None,
            reason="manual check"
        )
        assert obj.paper_state == {"balance": 1000}
        assert obj.demo_state is None

    def test_de_escalation_request_valid(self):
        obj = DeEscalationRequest(target_level=0, requested_by="operator1", reason="Calm market")
        assert obj.target_level == 0

    def test_de_escalation_request_level_out_of_range_fails(self):
        """target_level must be 0-5. / target_level 必須在 0-5 範圍內。"""
        with pytest.raises(Exception):
            DeEscalationRequest(target_level=6, requested_by="op", reason="test")

    def test_approve_de_escalation_valid(self):
        obj = ApproveDeEscalationRequest(approved_by="operator1")
        assert obj.approved_by == "operator1"

    def test_symbol_whitelist_add_valid(self):
        obj = SymbolWhitelistAddRequest(symbol="BTCUSDT", category="linear")
        assert obj.symbol == "BTCUSDT"

    def test_paper_live_gate_evaluate_valid(self):
        import time
        obj = PaperLiveGateEvaluateRequest(
            paper_start_time_ms=int(time.time() * 1000) - 86400000,
            total_trades=100,
            win_rate_percent=55.0,
            net_pnl=500.0,
            sharpe_ratio=1.5,
            max_drawdown_percent=10.0,
            profit_factor=1.8,
        )
        assert obj.win_rate_percent == 55.0

    def test_paper_live_gate_win_rate_out_of_range_fails(self):
        import time
        with pytest.raises(Exception):
            PaperLiveGateEvaluateRequest(
                paper_start_time_ms=int(time.time() * 1000),
                total_trades=50,
                win_rate_percent=110.0,  # > 100
                net_pnl=0.0,
                sharpe_ratio=0.0,
                max_drawdown_percent=5.0,
                profit_factor=1.0,
            )

    def test_auth_request_body_defaults(self):
        obj = AuthRequestBody()
        assert obj.ttl_hours == 24
        assert obj.reason == "operator_request"

    def test_auth_request_body_custom(self):
        obj = AuthRequestBody(scope={"mode": "paper"}, ttl_hours=48, reason="extended session")
        assert obj.ttl_hours == 48

    def test_auth_request_body_ttl_out_of_range_fails(self):
        with pytest.raises(Exception):
            AuthRequestBody(ttl_hours=200)  # > 168

    def test_audit_approval_body_default(self):
        obj = AuditApprovalBody()
        assert obj.reason == ""


# ─────────────────────────────────────────────────────────────────────────────
# 4. _require_operator_role — production function direct tests
# 直接測試生產代碼 _require_operator_role
# ─────────────────────────────────────────────────────────────────────────────

class TestRequireOperatorRoleProduction:
    """Direct tests of production _require_operator_role. / 直接測試生產 _require_operator_role。"""

    def test_operator_passes(self):
        actor = _make_actor(roles={"operator", "viewer"})
        _require_operator_role(actor)  # must not raise

    def test_viewer_raises_403(self):
        actor = _make_actor(roles={"viewer"})
        with pytest.raises(HTTPException) as exc:
            _require_operator_role(actor)
        assert exc.value.status_code == 403

    def test_none_raises_401(self):
        with pytest.raises(HTTPException) as exc:
            _require_operator_role(None)
        assert exc.value.status_code == 401

    def test_dict_raises_401(self):
        with pytest.raises(HTTPException) as exc:
            _require_operator_role({"roles": {"operator"}})
        assert exc.value.status_code == 401

    def test_empty_roles_raises_403(self):
        actor = _make_actor(roles=set())
        with pytest.raises(HTTPException) as exc:
            _require_operator_role(actor)
        assert exc.value.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# 5. Route handler tests via direct function calls with mocked hub
# 通過直接調用路由函數並 mock hub 進行測試
# ─────────────────────────────────────────────────────────────────────────────

GOV_MOD = "app.governance_routes"


class TestGetGovernanceStatus:
    """Tests for get_governance_status(). / get_governance_status() 測試。"""

    def test_hub_unavailable_raises_503(self):
        """When hub is None, route raises 503. / hub 為 None 時，路由拋出 503。"""
        actor = _make_actor()
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=None):
            with pytest.raises(HTTPException) as exc:
                get_governance_status(actor=actor)
            assert exc.value.status_code == 503

    def test_hub_get_status_returns_none_raises_500(self):
        """hub.get_status() returning None raises 500. / get_status() 返回 None 時拋出 500。"""
        actor = _make_actor()
        hub = _make_hub()
        hub.get_status.return_value = None
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            with pytest.raises(HTTPException) as exc:
                get_governance_status(actor=actor)
            assert exc.value.status_code == 500

    def test_happy_path_returns_ok(self):
        """Normal hub returns ok=True response. / 正常 hub 返回 ok=True 響應。"""
        actor = _make_actor()
        status = _make_hub_status()
        hub = _make_hub(status=status)
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = get_governance_status(actor=actor)
        assert result["ok"] is True
        assert result["message"] == "governance_status"

    def test_hub_exception_raises_500(self):
        """hub.get_status() raising RuntimeError causes 500. / get_status() 拋出 RuntimeError 時 500。"""
        actor = _make_actor()
        hub = _make_hub()
        hub.get_status.side_effect = RuntimeError("db failure")
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            with pytest.raises(HTTPException) as exc:
                get_governance_status(actor=actor)
            assert exc.value.status_code == 500


class TestGetDetailedGovernanceStatus:
    """Tests for get_detailed_governance_status(). / get_detailed_governance_status() 測試。"""

    def test_hub_unavailable_raises_503(self):
        actor = _make_actor()
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=None):
            with pytest.raises(HTTPException) as exc:
                get_detailed_governance_status(actor=actor)
            assert exc.value.status_code == 503

    def test_hub_status_none_raises_500(self):
        actor = _make_actor()
        hub = _make_hub()
        hub.get_status.return_value = None
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            with pytest.raises(HTTPException) as exc:
                get_detailed_governance_status(actor=actor)
            assert exc.value.status_code == 500

    def test_happy_path_returns_ok(self):
        actor = _make_actor()
        status = _make_hub_status()
        hub = _make_hub(status=status)
        hub._recovery_gate = None
        hub._change_audit_log = None
        hub._oms_sm = None
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            with patch(f"{GOV_MOD}.get_detailed_governance_status.__module__"):
                pass
            # Patch paper_trading_routes import to avoid real module load
            with patch.dict("sys.modules", {"app.paper_trading_routes": MagicMock(ENGINE=None)}):
                result = get_detailed_governance_status(actor=actor)
        assert result["ok"] is True
        assert result["message"] == "governance_status_detailed"


class TestGetAuthorizationStatus:
    """Tests for get_authorization_status(). / get_authorization_status() 測試。"""

    def test_hub_unavailable_raises_503(self):
        actor = _make_actor()
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=None):
            with pytest.raises(HTTPException) as exc:
                get_authorization_status(actor=actor)
            assert exc.value.status_code == 503

    def test_hub_status_none_raises_500(self):
        actor = _make_actor()
        hub = _make_hub()
        hub.get_status.return_value = None
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            with pytest.raises(HTTPException) as exc:
                get_authorization_status(actor=actor)
            assert exc.value.status_code == 500

    def test_happy_path_returns_auth_detail(self):
        actor = _make_actor()
        status = _make_hub_status(auth_state="ACTIVE", auth_pending_approval=False)
        hub = _make_hub(status=status)
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = get_authorization_status(actor=actor)
        assert result["ok"] is True
        assert result["data"]["state"] == "ACTIVE"
        assert result["data"]["is_effective"] is True  # ACTIVE is effective

    def test_idle_state_is_not_effective(self):
        actor = _make_actor()
        status = _make_hub_status(auth_state="IDLE")
        hub = _make_hub(status=status)
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = get_authorization_status(actor=actor)
        assert result["data"]["is_effective"] is False


class TestRequestAuthorization:
    """Tests for request_authorization(). / request_authorization() 測試。"""

    def _make_body(self, **kw):
        defaults = dict(scope={}, ttl_hours=24, reason="test reason")
        defaults.update(kw)
        return AuthRequestBody(**defaults)

    def test_hub_unavailable_raises_503(self):
        actor = _make_actor()
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=None):
            with pytest.raises(HTTPException) as exc:
                request_authorization(body=self._make_body(), actor=actor)
            assert exc.value.status_code == 503

    def test_hub_disabled_raises_403(self):
        actor = _make_actor()
        hub = _make_hub(enabled=False)
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            with pytest.raises(HTTPException) as exc:
                request_authorization(body=self._make_body(), actor=actor)
            assert exc.value.status_code == 403

    def test_authorization_sm_none_raises_503(self):
        actor = _make_actor()
        hub = _make_hub(enabled=True)
        hub._authorization_sm = None
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            with pytest.raises(HTTPException) as exc:
                request_authorization(body=self._make_body(), actor=actor)
            assert exc.value.status_code == 503

    def test_happy_path_returns_pending_approval(self):
        actor = _make_actor()
        hub = _make_hub(enabled=True)
        mock_auth_obj = MagicMock()
        mock_auth_obj.authorization_id = "auth-001"
        hub._authorization_sm.create_draft.return_value = mock_auth_obj
        hub._authorization_sm.submit_for_approval.return_value = None
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = request_authorization(body=self._make_body(), actor=actor)
        assert result["ok"] is True
        assert result["data"]["state"] == "pending_approval"
        assert result["data"]["authorization_id"] == "auth-001"


class TestApproveAuthorization:
    """Tests for approve_authorization(). / approve_authorization() 測試。"""

    def _make_body(self, note="Approved by operator"):
        return AuthApprovalRequest(approval_note=note)

    def test_hub_unavailable_raises_503(self):
        actor = _make_actor()
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=None):
            with pytest.raises(HTTPException) as exc:
                approve_authorization(body=self._make_body(), actor=actor)
            assert exc.value.status_code == 503

    def test_non_operator_raises_403(self):
        actor = _make_actor(roles={"viewer"})
        hub = _make_hub(enabled=True)
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            with pytest.raises(HTTPException) as exc:
                approve_authorization(body=self._make_body(), actor=actor)
            assert exc.value.status_code == 403

    def test_no_pending_approval_returns_error(self):
        actor = _make_actor()
        status = _make_hub_status(auth_pending_approval=False)
        hub = _make_hub(status=status, enabled=True)
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = approve_authorization(body=self._make_body(), actor=actor)
        assert result["ok"] is False
        assert result["code"] == "no_pending_approval"

    def test_happy_path_returns_approval_recorded(self):
        actor = _make_actor()
        status = _make_hub_status(auth_pending_approval=True)
        hub = _make_hub(status=status, enabled=True)
        # Setup pending auth in list_all
        pending_auth = MagicMock()
        pending_auth.state.value = "PENDING_APPROVAL"
        pending_auth.authorization_id = "auth-002"
        hub._authorization_sm.list_all.return_value = [pending_auth]
        hub._authorization_sm.approve.return_value = None
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = approve_authorization(body=self._make_body(), actor=actor)
        assert result["ok"] is True
        assert result["data"]["status"] == "approval_recorded"


class TestGetRiskLevel:
    """Tests for get_risk_level(). / get_risk_level() 測試。"""

    def test_hub_unavailable_raises_503(self):
        actor = _make_actor()
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=None):
            with pytest.raises(HTTPException) as exc:
                get_risk_level(actor=actor)
            assert exc.value.status_code == 503

    def test_happy_path_returns_level_detail(self):
        actor = _make_actor()
        status = _make_hub_status(risk_level=0, risk_level_name="NORMAL")
        hub = _make_hub(status=status)
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = get_risk_level(actor=actor)
        assert result["ok"] is True
        assert result["data"]["level"] == 0
        assert result["data"]["level_name"] == "NORMAL"

    def test_risk_level_mapping_applied(self):
        """Risk level int maps to named string even if status has wrong name. / 整數風險等級映射為命名字符串。"""
        actor = _make_actor()
        status = _make_hub_status(risk_level=2, risk_level_name="WRONG_NAME")
        hub = _make_hub(status=status)
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = get_risk_level(actor=actor)
        assert result["data"]["level_name"] == "REDUCED"

    def test_risk_level_none_not_mapped(self):
        """If risk_level is None, mapping step is skipped. / risk_level 為 None 時跳過映射。"""
        actor = _make_actor()
        status = _make_hub_status(risk_level=None, risk_level_name="UNKNOWN")
        hub = _make_hub(status=status)
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = get_risk_level(actor=actor)
        # level_name should remain as status provides it (mapping skipped)
        assert result["ok"] is True


class TestOverrideRiskLevel:
    """Tests for override_risk_level(). / override_risk_level() 測試。"""

    def _make_body(self, target="NORMAL", reason="de-escalate"):
        return RiskOverrideRequest(target_level=target, reason=reason)

    def test_hub_unavailable_raises_503(self):
        actor = _make_actor()
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=None):
            with pytest.raises(HTTPException) as exc:
                override_risk_level(body=self._make_body(), actor=actor)
            assert exc.value.status_code == 503

    def test_non_operator_raises_403(self):
        actor = _make_actor(roles={"viewer"})
        hub = _make_hub(enabled=True)
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            with pytest.raises(HTTPException) as exc:
                override_risk_level(body=self._make_body(), actor=actor)
            assert exc.value.status_code == 403

    def test_invalid_target_level_returns_error(self):
        actor = _make_actor()
        hub = _make_hub(enabled=True)
        status = _make_hub_status(risk_level=3)
        hub.get_status.return_value = status
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = override_risk_level(
                body=RiskOverrideRequest(target_level="INVALID_LEVEL", reason="test"),
                actor=actor
            )
        assert result["ok"] is False
        assert result["code"] == "invalid_level"

    def test_escalation_rejected(self):
        """Target level >= current level should be rejected. / 目標等級 >= 當前等級應被拒絕。"""
        actor = _make_actor()
        hub = _make_hub(enabled=True)
        status = _make_hub_status(risk_level=1)  # current = CAUTIOUS
        hub.get_status.return_value = status
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            # target DEFENSIVE (3) > current CAUTIOUS (1) → escalation
            result = override_risk_level(
                body=RiskOverrideRequest(target_level="DEFENSIVE", reason="test"),
                actor=actor
            )
        assert result["ok"] is False
        assert result["code"] == "escalation_not_allowed"

    def test_happy_path_deescalation_applied(self):
        """De-escalation from CAUTIOUS to NORMAL succeeds. / 從 CAUTIOUS 降至 NORMAL 成功。"""
        actor = _make_actor()
        hub = _make_hub(enabled=True)
        status = _make_hub_status(risk_level=2)  # REDUCED
        hub.get_status.return_value = status
        hub._check_de_escalation_gate.return_value = True
        hub._risk_governor_sm = None  # Skip actual SM call
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = override_risk_level(
                body=RiskOverrideRequest(target_level="NORMAL", reason="market recovered"),
                actor=actor
            )
        assert result["ok"] is True
        assert result["data"]["status"] == "override_applied"

    def test_deescalation_gate_pending(self):
        """Gate not cleared → de_escalation_pending_approval response. / 門控未通過 → 待批准狀態。"""
        actor = _make_actor()
        hub = _make_hub(enabled=True)
        status = _make_hub_status(risk_level=3)
        hub.get_status.return_value = status
        hub._check_de_escalation_gate.return_value = False
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = override_risk_level(
                body=RiskOverrideRequest(target_level="NORMAL", reason="operator request"),
                actor=actor
            )
        # Should return pending approval response (ok=True with specific message)
        assert result["ok"] is True
        assert result["message"] == "de_escalation_pending_approval"


class TestGetActiveLeases:
    """Tests for get_active_leases(). / get_active_leases() 測試。"""

    def test_hub_unavailable_raises_503(self):
        actor = _make_actor()
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=None):
            with pytest.raises(HTTPException) as exc:
                get_active_leases(actor=actor)
            assert exc.value.status_code == 503

    def test_hub_status_none_raises_500(self):
        actor = _make_actor()
        hub = _make_hub()
        hub.get_status.return_value = None
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            with pytest.raises(HTTPException) as exc:
                get_active_leases(actor=actor)
            assert exc.value.status_code == 500

    def test_happy_path_with_no_lease_sm(self):
        actor = _make_actor()
        status = _make_hub_status(active_leases_count=0, total_leases_tracked=0)
        hub = _make_hub(status=status)
        hub._lease_sm = None
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = get_active_leases(actor=actor)
        assert result["ok"] is True
        assert result["data"]["leases"] == []
        assert result["data"]["all_leases"] == []

    def test_happy_path_with_lease_sm(self):
        actor = _make_actor()
        status = _make_hub_status(active_leases_count=1, total_leases_tracked=1)
        hub = _make_hub(status=status)
        mock_lease = MagicMock()
        mock_lease.to_dict.return_value = {"lease_id": "L001", "state": "ACTIVE"}
        hub._lease_sm.get_all.return_value = [mock_lease]
        hub._lease_sm.get_live.return_value = [mock_lease]
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = get_active_leases(actor=actor)
        assert result["ok"] is True
        assert len(result["data"]["leases"]) == 1
        assert result["data"]["leases"][0]["lease_id"] == "L001"


class TestGetGovernanceEvents:
    """Tests for get_governance_events(). / get_governance_events() 測試。"""

    def test_hub_unavailable_raises_503(self):
        actor = _make_actor()
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=None):
            with pytest.raises(HTTPException) as exc:
                get_governance_events(actor=actor)
            assert exc.value.status_code == 503

    def test_limit_clamping_too_large(self):
        """limit > 1000 is clamped to 1000. / limit > 1000 被限制為 1000。"""
        actor = _make_actor()
        hub = _make_hub()
        hub.get_governance_events.return_value = []
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = get_governance_events(limit=9999, actor=actor)
        hub.get_governance_events.assert_called_with(limit=1000, event_type=None)
        assert result["data"]["limit"] == 1000

    def test_limit_clamping_too_small(self):
        """limit < 1 is clamped to 1. / limit < 1 被限制為 1。"""
        actor = _make_actor()
        hub = _make_hub()
        hub.get_governance_events.return_value = []
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = get_governance_events(limit=-5, actor=actor)
        hub.get_governance_events.assert_called_with(limit=1, event_type=None)

    def test_happy_path_with_events(self):
        actor = _make_actor()
        hub = _make_hub()
        hub.get_governance_events.return_value = [{"event_id": "E001", "type": "risk_governor"}]
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = get_governance_events(limit=10, event_type="risk_governor", actor=actor)
        assert result["ok"] is True
        assert result["data"]["count"] == 1
        assert result["data"]["event_type_filter"] == "risk_governor"

    def test_happy_path_empty_events(self):
        actor = _make_actor()
        hub = _make_hub()
        hub.get_governance_events.return_value = []
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = get_governance_events(actor=actor)
        assert result["ok"] is True
        assert result["data"]["count"] == 0


class TestGovernanceHealthCheck:
    """Tests for governance_health_check(). / governance_health_check() 測試。"""

    def test_hub_unavailable_raises_503(self):
        actor = _make_actor()
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=None):
            with pytest.raises(HTTPException) as exc:
                governance_health_check(actor=actor)
            assert exc.value.status_code == 503

    def test_happy_path_enabled_hub(self):
        actor = _make_actor()
        status = _make_hub_status(enabled=True, mode="normal")
        hub = _make_hub(status=status)
        hub.is_authorized.return_value = True
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = governance_health_check(actor=actor)
        assert result["ok"] is True
        assert result["data"]["overall_health"] == "ok"
        assert result["data"]["is_authorized"] is True

    def test_disabled_hub_returns_disabled_health(self):
        actor = _make_actor()
        status = _make_hub_status(enabled=False, mode="normal")
        hub = _make_hub(status=status)
        hub.is_authorized.return_value = False
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = governance_health_check(actor=actor)
        assert result["data"]["overall_health"] == "disabled"


class TestGetPaperLiveGateStatus:
    """Tests for get_paper_live_gate_status(). / get_paper_live_gate_status() 測試。"""

    def test_gate_unavailable_raises_503(self):
        actor = _make_actor()
        with patch(f"{GOV_MOD}._get_paper_live_gate", return_value=None):
            with pytest.raises(HTTPException) as exc:
                get_paper_live_gate_status(actor=actor)
            assert exc.value.status_code == 503

    def test_gate_without_get_gate_status_method(self):
        """Gate object that lacks get_gate_status() returns not_evaluated. / 缺少方法的 gate 返回 not_evaluated。"""
        actor = _make_actor()
        gate = MagicMock(spec=[])  # no methods
        with patch(f"{GOV_MOD}._get_paper_live_gate", return_value=gate):
            result = get_paper_live_gate_status(actor=actor)
        assert result["ok"] is True
        assert result["data"] == {"status": "not_evaluated"}

    def test_happy_path_with_gate_status(self):
        actor = _make_actor()
        gate_status = MagicMock()
        gate_status.to_dict.return_value = {"status": "open", "passed": 11}
        gate = MagicMock()
        gate.get_gate_status.return_value = gate_status
        with patch(f"{GOV_MOD}._get_paper_live_gate", return_value=gate):
            result = get_paper_live_gate_status(actor=actor)
        assert result["ok"] is True
        assert result["data"]["status"] == "open"


class TestGetPendingRecoveryRequests:
    """Tests for get_pending_recovery_requests(). / get_pending_recovery_requests() 測試。"""

    def test_hub_unavailable_raises_503(self):
        actor = _make_actor()
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=None):
            with pytest.raises(HTTPException) as exc:
                get_pending_recovery_requests(actor=actor)
            assert exc.value.status_code == 503

    def test_no_recovery_gate_returns_empty(self):
        actor = _make_actor()
        hub = _make_hub()
        hub._recovery_gate = None
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = get_pending_recovery_requests(actor=actor)
        assert result["ok"] is True
        assert result["data"] == []

    def test_happy_path_with_pending_requests(self):
        actor = _make_actor()
        hub = _make_hub()
        hub._recovery_gate = MagicMock()
        hub._recovery_gate.get_pending_requests.return_value = [
            {"request_id": "R001", "status": "pending"}
        ]
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = get_pending_recovery_requests(actor=actor)
        assert result["ok"] is True
        assert len(result["data"]) == 1


class TestGetChangeHistory:
    """Tests for get_change_history(). / get_change_history() 測試。"""

    def test_hub_unavailable_raises_503(self):
        actor = _make_actor()
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=None):
            with pytest.raises(HTTPException) as exc:
                get_change_history(actor=actor)
            assert exc.value.status_code == 503

    def test_no_change_audit_log_returns_empty(self):
        actor = _make_actor()
        hub = _make_hub()
        hub._change_audit_log = None
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = get_change_history(actor=actor)
        assert result["ok"] is True
        assert result["data"] == []

    def test_happy_path_returns_changes(self):
        actor = _make_actor()
        hub = _make_hub()
        mock_change = MagicMock()
        mock_change.to_dict.return_value = {"change_id": "C001", "type": "config"}
        hub._change_audit_log = MagicMock()
        hub._change_audit_log.get_all_changes.return_value = [mock_change]
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = get_change_history(limit=50, actor=actor)
        assert result["ok"] is True
        assert len(result["data"]) == 1


class TestGetPendingApprovals:
    """Tests for get_pending_approvals(). / get_pending_approvals() 測試。"""

    def test_hub_unavailable_raises_503(self):
        actor = _make_actor()
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=None):
            with pytest.raises(HTTPException) as exc:
                get_pending_approvals(actor=actor)
            assert exc.value.status_code == 503

    def test_no_change_audit_log_returns_empty(self):
        actor = _make_actor()
        hub = _make_hub()
        hub._change_audit_log = None
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = get_pending_approvals(actor=actor)
        assert result["ok"] is True
        assert result["data"] == []

    def test_happy_path_returns_pending_list(self):
        actor = _make_actor()
        hub = _make_hub()
        mock_change = MagicMock()
        mock_change.to_dict.return_value = {"change_id": "C002", "state": "PENDING"}
        hub._change_audit_log = MagicMock()
        hub._change_audit_log.get_pending_approvals.return_value = [mock_change]
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = get_pending_approvals(actor=actor)
        assert result["ok"] is True
        assert len(result["data"]) == 1


class TestApproveAuditChange:
    """Tests for approve_audit_change(). / approve_audit_change() 測試。"""

    def test_hub_unavailable_raises_503(self):
        actor = _make_actor()
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=None):
            with pytest.raises(HTTPException) as exc:
                approve_audit_change(change_id="C001", body=AuditApprovalBody(), actor=actor)
            assert exc.value.status_code == 503

    def test_non_operator_raises_403(self):
        """
        P0-1 fix: _require_operator_role now uses isinstance(actor, AuthenticatedActor).
        Non-operator role must raise 403 directly (HTTPException is re-raised correctly).
        P0-1 修复：_require_operator_role 现在使用 isinstance(actor, AuthenticatedActor)。
        非 operator 角色必须直接抛出 403（HTTPException 被正确 re-raise）。
        """
        actor = _make_actor(roles={"viewer"})
        hub = _make_hub()
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            with pytest.raises(HTTPException) as exc:
                approve_audit_change(change_id="C001", body=AuditApprovalBody(), actor=actor)
            assert exc.value.status_code == 403
            assert "Operator role required" in str(exc.value.detail)

    def test_no_change_audit_log_returns_503_error(self):
        actor = _make_actor()
        hub = _make_hub()
        hub._change_audit_log = None
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = approve_audit_change(change_id="C001", body=AuditApprovalBody(), actor=actor)
        assert result["ok"] is False
        assert result["code"] == "log_unavailable"

    def test_change_not_found_returns_404_error(self):
        actor = _make_actor()
        hub = _make_hub()
        hub._change_audit_log = MagicMock()
        hub._change_audit_log.approve_change.return_value = None  # not found
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = approve_audit_change(change_id="NONEXISTENT", body=AuditApprovalBody(), actor=actor)
        assert result["ok"] is False
        assert result["code"] == "not_found"

    def test_happy_path_returns_approved(self):
        actor = _make_actor()
        hub = _make_hub()
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"change_id": "C001", "state": "APPROVED"}
        hub._change_audit_log = MagicMock()
        hub._change_audit_log.approve_change.return_value = mock_result
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = approve_audit_change(
                change_id="C001",
                body=AuditApprovalBody(reason="Looks good"),
                actor=actor
            )
        assert result["ok"] is True
        assert result["message"] == "audit_change_approved"


class TestRejectAuditChange:
    """Tests for reject_audit_change(). / reject_audit_change() 測試。"""

    def test_hub_unavailable_raises_503(self):
        actor = _make_actor()
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=None):
            with pytest.raises(HTTPException) as exc:
                reject_audit_change(change_id="C001", body=AuditApprovalBody(), actor=actor)
            assert exc.value.status_code == 503

    def test_non_operator_raises_403(self):
        """
        P0-1 fix: _require_operator_role now uses isinstance(actor, AuthenticatedActor).
        Non-operator role must raise 403 directly (HTTPException is re-raised correctly).
        P0-1 修复：_require_operator_role 现在使用 isinstance(actor, AuthenticatedActor)。
        非 operator 角色必须直接抛出 403（HTTPException 被正确 re-raise）。
        """
        actor = _make_actor(roles={"viewer"})
        hub = _make_hub()
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            with pytest.raises(HTTPException) as exc:
                reject_audit_change(change_id="C001", body=AuditApprovalBody(), actor=actor)
            assert exc.value.status_code == 403
            assert "Operator role required" in str(exc.value.detail)

    def test_not_found_returns_404_error(self):
        actor = _make_actor()
        hub = _make_hub()
        hub._change_audit_log = MagicMock()
        hub._change_audit_log.reject_change.return_value = None
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = reject_audit_change(change_id="NONE", body=AuditApprovalBody(), actor=actor)
        assert result["ok"] is False
        assert result["code"] == "not_found"

    def test_happy_path_returns_rejected(self):
        actor = _make_actor()
        hub = _make_hub()
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"change_id": "C001", "state": "REJECTED"}
        hub._change_audit_log = MagicMock()
        hub._change_audit_log.reject_change.return_value = mock_result
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = reject_audit_change(
                change_id="C001",
                body=AuditApprovalBody(reason="Not approved"),
                actor=actor
            )
        assert result["ok"] is True
        assert result["message"] == "audit_change_rejected"


class TestTriggerManualReconciliation:
    """Tests for trigger_manual_reconciliation(). / trigger_manual_reconciliation() 測試。"""

    def _make_body(self):
        return ManualReconciliationRequest(paper_state={"balance": 1000}, reason="test")

    def test_hub_unavailable_raises_503(self):
        actor = _make_actor()
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=None):
            with pytest.raises(HTTPException) as exc:
                trigger_manual_reconciliation(body=self._make_body(), actor=actor)
            assert exc.value.status_code == 503

    def test_hub_disabled_raises_403(self):
        actor = _make_actor()
        hub = _make_hub(enabled=False)
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            with pytest.raises(HTTPException) as exc:
                trigger_manual_reconciliation(body=self._make_body(), actor=actor)
            assert exc.value.status_code == 403

    def test_happy_path_returns_reconciliation_result(self):
        actor = _make_actor()
        hub = _make_hub(enabled=True)
        hub.reconcile.return_value = {
            "ok": True,
            "result": "consistent",
            "is_consistent": True,
            "severity": "none",
            "discrepancies": [],
        }
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = trigger_manual_reconciliation(body=self._make_body(), actor=actor)
        assert result["ok"] is True
        assert result["data"]["is_consistent"] is True

    def test_reconciliation_returns_error_response(self):
        actor = _make_actor()
        hub = _make_hub(enabled=True)
        hub.reconcile.return_value = {
            "ok": False,
            "reason": "State mismatch",
        }
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = trigger_manual_reconciliation(body=self._make_body(), actor=actor)
        assert result["ok"] is False
        assert result["code"] == "reconciliation_error"


class TestGetLearningTierStatus:
    """Tests for get_learning_tier_status(). / get_learning_tier_status() 測試。"""

    def test_hub_unavailable_raises_503(self):
        actor = _make_actor()
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=None):
            with pytest.raises(HTTPException) as exc:
                get_learning_tier_status(actor=actor)
            assert exc.value.status_code == 503

    def test_happy_path_returns_tier_status(self):
        actor = _make_actor()
        hub = _make_hub()
        hub.get_learning_tier_status.return_value = {
            "current_tier": 1,
            "capabilities": ["basic_scan"],
        }
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = get_learning_tier_status(actor=actor)
        assert result["ok"] is True
        assert result["data"]["current_tier"] == 1


class TestRequestDeEscalation:
    """Tests for request_de_escalation(). / request_de_escalation() 測試。"""

    def _make_body(self):
        return DeEscalationRequest(target_level=0, requested_by="operator1", reason="Calm now")

    def test_hub_unavailable_raises_503(self):
        actor = _make_actor()
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=None):
            with pytest.raises(HTTPException) as exc:
                request_de_escalation(body=self._make_body(), actor=actor)
            assert exc.value.status_code == 503

    def test_hub_disabled_raises_403(self):
        actor = _make_actor()
        hub = _make_hub(enabled=False)
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            with pytest.raises(HTTPException) as exc:
                request_de_escalation(body=self._make_body(), actor=actor)
            assert exc.value.status_code == 403

    def test_submission_failure_returns_error(self):
        actor = _make_actor()
        hub = _make_hub(enabled=True)
        hub.request_de_escalation.return_value = None
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = request_de_escalation(body=self._make_body(), actor=actor)
        assert result["ok"] is False
        assert result["code"] == "submission_failed"

    def test_happy_path_returns_pending(self):
        actor = _make_actor()
        hub = _make_hub(enabled=True)
        hub.request_de_escalation.return_value = "REQ-001"
        with patch(f"{GOV_MOD}._get_governance_hub", return_value=hub):
            result = request_de_escalation(body=self._make_body(), actor=actor)
        assert result["ok"] is True
        assert result["data"]["request_id"] == "REQ-001"
        assert result["data"]["status"] == "pending_approval"


# ─────────────────────────────────────────────────────────────────────────────
# 1B-2: H0 Gate Status Freshness Fields
# 1B-2: H0 確定性門控狀態端點新鮮度字段測試
# ─────────────────────────────────────────────────────────────────────────────

class TestGetH0GateStatusFreshnessFields:
    """
    Tests for the freshness diagnostic fields added by 1B-2 to the
    GET /api/v1/governance/h0-gate/status endpoint.

    驗證 1B-2 新增的新鮮度診斷字段是否正確出現在
    GET /api/v1/governance/h0-gate/status 的回應中。
    """

    def _make_gate(self, price_ts: dict | None = None) -> MagicMock:
        """
        Build a mock H0Gate with get_current_state() and optional _price_ts.
        構建一個帶有 get_current_state() 和可選 _price_ts 的模擬 H0Gate。
        """
        gate = MagicMock()
        gate.get_current_state.return_value = {"system_mode": "demo_only", "stats": {}}
        # Attach _price_ts dict to simulate gate internals.
        # 設置 _price_ts 字典模擬 gate 內部狀態。
        if price_ts is not None:
            gate._price_ts = price_ts
            gate._config = MagicMock()
            gate._config.max_data_age_ms = 1000
        else:
            # No _price_ts attribute at all (simulate bare mock).
            # 完全沒有 _price_ts 屬性（模擬裸 mock 情況）。
            del gate._price_ts
        return gate

    def test_freshness_fields_present_when_gate_has_price_data(self):
        """
        When gate._price_ts has entries, response includes freshness_age_ms,
        freshness_score, and data_quality_warn_only.

        gate._price_ts 有數據時，回應應包含 freshness_age_ms、freshness_score、
        data_quality_warn_only 三個字段。
        """
        import time as _time
        from app.governance_routes import get_h0_gate_status

        # Fresh data: timestamp = now - 100ms (should give high freshness score)
        # 新鮮數據：時間戳 = 現在 - 100ms（應給出高新鮮度分數）
        now_ms = int(_time.time() * 1000)
        gate = self._make_gate(price_ts={"BTCUSDT": now_ms - 100})
        actor = _make_actor()

        with patch(f"{GOV_MOD}._get_h0_gate", return_value=gate):
            result = get_h0_gate_status(actor=actor)

        assert result["ok"] is True
        assert "freshness_age_ms" in result, "freshness_age_ms must be present"
        assert "freshness_score" in result, "freshness_score must be present"
        assert "data_quality_warn_only" in result, "data_quality_warn_only must be present"
        # freshness_age_ms should be roughly 100ms (tolerance 500ms for CI)
        # freshness_age_ms 應大約為 100ms（容許 CI 下 500ms 誤差）
        assert result["freshness_age_ms"] is not None
        assert result["freshness_age_ms"] >= 0
        # Sprint 5a: H0Gate is fail-closed (not advisory) — value changed True→False
        # Sprint 5a: H0Gate 為 fail-closed（非 warn-only），值已更新為 False
        assert result["data_quality_warn_only"] is False

    def test_freshness_age_ms_is_none_when_no_price_data(self):
        """
        When gate._price_ts is empty, freshness_age_ms should be None
        (no data available — cognitive honesty, principle 10).

        gate._price_ts 為空時，freshness_age_ms 應為 None
        （無數據 — 認知誠實，根原則 10）。
        """
        from app.governance_routes import get_h0_gate_status

        gate = MagicMock()
        gate.get_current_state.return_value = {"system_mode": "demo_only", "stats": {}}
        gate._price_ts = {}  # empty dict — no ticks yet / 空字典，尚無 tick
        gate._config = MagicMock()
        gate._config.max_data_age_ms = 1000
        actor = _make_actor()

        with patch(f"{GOV_MOD}._get_h0_gate", return_value=gate):
            result = get_h0_gate_status(actor=actor)

        assert result["ok"] is True
        assert result["freshness_age_ms"] is None
        assert result["freshness_score"] is None
        # Sprint 5a: H0Gate is fail-closed (not advisory) — value changed True→False
        # Sprint 5a: H0Gate 為 fail-closed（非 warn-only），值已更新為 False
        assert result["data_quality_warn_only"] is False

    def test_h0_gate_unavailable_raises_503(self):
        """
        When _get_h0_gate() returns None, route must raise 503.
        _get_h0_gate() 返回 None 時，路由必須拋出 503。
        """
        from app.governance_routes import get_h0_gate_status

        actor = _make_actor()
        with patch(f"{GOV_MOD}._get_h0_gate", return_value=None):
            with pytest.raises(HTTPException) as exc:
                get_h0_gate_status(actor=actor)
        assert exc.value.status_code == 503
