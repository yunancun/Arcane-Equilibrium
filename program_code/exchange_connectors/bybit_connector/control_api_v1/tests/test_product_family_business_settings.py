"""
OpenClaw / Bybit Control API v1 — 产品族配置写接口 + 经营摘要 + PnL 录入 + 系统设置 集成测试
OpenClaw / Bybit Control API v1 — Integration tests for:
  - Product family config write endpoint
  - Business summary endpoint
  - PnL entry input endpoint
  - System settings (config-change) workflow

测试原则 / Testing principles:
  - 每个测试用例使用独立的临时状态文件，互不干扰。
    Each test uses an independent temporary state file; no cross-contamination.
  - 所有断言覆盖：成功路径、拒绝路径、安全边界。
    All assertions cover: success path, rejection path, safety boundaries.
  - 不涉及 live 执行权限变更，仅测试 shadow/demo 层面的控制配置。
    No live execution authority changes; only shadow/demo-level control config.
"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def build_client():
    """
    构建测试客户端（每次使用独立的状态文件和模块实例）。
    Build a test client with an isolated state file and fresh module instance per invocation.

    注意：必须同时 reload main_legacy 以刷新 settings 和 STORE。
    Note: must reload main_legacy too, to refresh settings and STORE.
    """
    runtime_dir = Path(tempfile.mkdtemp(prefix="openclaw_test_pfbiz_"))
    os.environ["OPENCLAW_STATE_FILE"] = str(runtime_dir / "state.json")
    os.environ["OPENCLAW_API_TOKEN"] = "test-token"

    from app import main_legacy as legacy_module
    from app import main as main_module
    importlib.reload(legacy_module)
    importlib.reload(main_module)
    return TestClient(main_module.app)


def auth_headers():
    return {"Authorization": "Bearer test-token"}


def make_envelope(state_revision, payload=None, **extra):
    """
    构建标准请求 envelope。
    Build a standard request envelope.
    """
    env = {
        "request_id": str(uuid.uuid4()),
        "idempotency_key": str(uuid.uuid4()),
        "operator_id": "demo-operator",
        "reason": "test",
        "client_ts_ms": 1711425600000,
        "expected_state_revision": state_revision,
        "expected_previous_state": None,
        "payload": payload or {},
    }
    env.update(extra)
    return env


def get_state_revision(client):
    """
    获取当前 state_revision。
    Fetch the current state_revision.
    """
    r = client.get("/api/v1/system/overview", headers=auth_headers())
    return r.json()["state_revision"]


# ════════════════════════════════════════════════════════════════════════════
# 产品族配置写接口测试 / Product Family Config Write Tests
# ════════════════════════════════════════════════════════════════════════════


class TestProductFamilyConfig:
    """产品族配置端点 / Product family config endpoint tests."""

    def test_enable_spot_returns_success(self):
        """启用 spot 产品族应返回成功 / Enabling spot should return success."""
        client = build_client()
        rev = get_state_revision(client)
        r = client.post(
            "/api/v1/control/product-family/spot/config",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "enabled_switch": True,
                "visibility_switch": True,
                "mode_switch": "shadow_only",
            }),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["action_result"] == "success"
        result = data["data"]
        assert result["family"] == "spot"
        assert result["applied_changes"]["enabled_switch"] is True
        assert result["applied_changes"]["visibility_switch"] is True
        assert result["applied_changes"]["mode_switch"] == "shadow_only"
        assert result["current_controls"]["enabled_switch"] is True
        assert result["current_controls"]["mode_switch"] == "shadow_only"

    def test_observe_only_mode_allowed(self):
        """observe_only 模式应被允许 / observe_only mode should be allowed."""
        client = build_client()
        rev = get_state_revision(client)
        r = client.post(
            "/api/v1/control/product-family/margin/config",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "enabled_switch": True,
                "visibility_switch": True,
                "mode_switch": "observe_only",
            }),
        )
        assert r.status_code == 200
        assert r.json()["data"]["applied_changes"]["mode_switch"] == "observe_only"

    def test_live_mode_rejected(self):
        """live_ready 模式应被拒绝 / live_ready mode should be rejected."""
        client = build_client()
        rev = get_state_revision(client)
        r = client.post(
            "/api/v1/control/product-family/spot/config",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "mode_switch": "live_ready",
            }),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert "mode_switch:live_ready:not_allowed_at_this_stage" in data["rejected_fields"]
        assert "mode_switch" not in data["applied_changes"]

    def test_invalid_family_returns_400(self):
        """无效的产品族名应返回 400 / Invalid family name should return 400."""
        client = build_client()
        rev = get_state_revision(client)
        r = client.post(
            "/api/v1/control/product-family/invalid_family/config",
            headers=auth_headers(),
            json=make_envelope(rev, payload={"enabled_switch": True}),
        )
        assert r.status_code == 400

    def test_action_permissions_update(self):
        """动作权限更新应成功 / Action permissions update should succeed."""
        client = build_client()
        rev = get_state_revision(client)
        r = client.post(
            "/api/v1/control/product-family/spot/config",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "action_permissions": {
                    "new_order": True,
                    "cancel": True,
                    "amend": False,
                },
            }),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["applied_changes"]["action_permissions.new_order"] is True
        assert data["applied_changes"]["action_permissions.cancel"] is True
        assert data["applied_changes"]["action_permissions.amend"] is False
        # 确认 effective state 仍然是 blocked（全局执行未开启）
        # Confirm effective state is still blocked (global execution not open)
        perms = data["current_action_permissions"]
        assert perms["effective_new_order_allowed_state"] != "allowed"

    def test_all_six_families_configurable(self):
        """所有六个产品族都能配置 / All six product families are configurable."""
        families = [
            "spot", "margin", "perp_linear",
            "perp_inverse", "options", "other_derivatives_reserved",
        ]
        client = build_client()
        for family in families:
            rev = get_state_revision(client)
            r = client.post(
                f"/api/v1/control/product-family/{family}/config",
                headers=auth_headers(),
                json=make_envelope(rev, payload={
                    "enabled_switch": True,
                    "visibility_switch": True,
                }),
            )
            assert r.status_code == 200, f"Failed for {family}"
            assert r.json()["data"]["family"] == family

    def test_audit_trail_recorded(self):
        """配置变更应记录审计 / Config change should record audit trail."""
        client = build_client()
        rev = get_state_revision(client)
        r = client.post(
            "/api/v1/control/product-family/spot/config",
            headers=auth_headers(),
            json=make_envelope(rev, payload={"enabled_switch": True}),
        )
        assert r.status_code == 200
        assert r.json()["audit_ref"] is not None

        # 验证审计端点中有记录 / Verify audit endpoint has the record
        audit = client.get("/api/v1/system/audit-summary", headers=auth_headers()).json()
        assert audit["data"]["latest_write_action_summary"]["type"] == "product_family_config_spot"

    def test_derived_state_recomputed_after_config(self):
        """配置后 derived 状态应重新计算 / Derived state should recompute after config."""
        client = build_client()
        rev = get_state_revision(client)
        r = client.post(
            "/api/v1/control/product-family/spot/config",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "enabled_switch": True,
                "visibility_switch": True,
                "mode_switch": "shadow_only",
            }),
        )
        assert r.status_code == 200
        derived = r.json()["data"]["current_derived"]
        # spot 启用 + shadow_only → 应有 shadow 相关 capability
        # spot enabled + shadow_only → should have shadow-related capability
        assert derived["capability_state"] in ("shadow_control_ready", "shadow_visible")


# ════════════════════════════════════════════════════════════════════════════
# 经营摘要测试 / Business Summary Tests
# ════════════════════════════════════════════════════════════════════════════


class TestBusinessSummary:
    """经营摘要端点 / Business summary endpoint tests."""

    def test_summary_returns_complete_structure(self):
        """摘要应返回完整结构 / Summary should return complete structure."""
        client = build_client()
        r = client.get("/api/v1/system/business/summary", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert "daily" in data
        assert "cost_entries_recent" in data
        assert "event_entries_recent" in data
        assert "pnl_entries_recent" in data
        assert "cost_breakdown" in data
        assert "entry_totals" in data

    def test_daily_has_required_fields(self):
        """daily 应包含所有必需字段 / Daily should have all required fields."""
        client = build_client()
        r = client.get("/api/v1/system/business/summary", headers=auth_headers())
        daily = r.json()["data"]["daily"]
        required_fields = [
            "realized_pnl", "unrealized_pnl", "gross_pnl",
            "total_cost", "net_operating_pnl", "business_event_count",
            "reporting_currency", "window_timezone",
        ]
        for field in required_fields:
            assert field in daily, f"Missing field: {field}"

    def test_cost_entry_appears_in_summary(self):
        """录入费用后应出现在摘要中 / Cost entry should appear in summary after recording."""
        client = build_client()
        rev = get_state_revision(client)

        # 录入一条费用 / Record a cost entry
        client.post(
            "/api/v1/input/cost",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "amount": 1.5,
                "category": "ai_api",
                "note": "test cost entry",
            }),
        )

        # 检查摘要 / Check summary
        r = client.get("/api/v1/system/business/summary", headers=auth_headers())
        data = r.json()["data"]
        assert data["entry_totals"]["total_cost_entries"] == 1
        assert len(data["cost_entries_recent"]) == 1
        assert data["cost_entries_recent"][0]["amount"] == 1.5
        assert data["cost_breakdown"]["ai_api"] == 1.5
        assert data["daily"]["total_cost"] == 1.5

    def test_multiple_costs_accumulate(self):
        """多次录入应累积 / Multiple entries should accumulate."""
        client = build_client()
        for i in range(3):
            rev = get_state_revision(client)
            client.post(
                "/api/v1/input/cost",
                headers=auth_headers(),
                json=make_envelope(rev, payload={
                    "amount": 2.0,
                    "category": "exchange_fee" if i % 2 == 0 else "ai_api",
                }),
            )

        r = client.get("/api/v1/system/business/summary", headers=auth_headers())
        data = r.json()["data"]
        assert data["entry_totals"]["total_cost_entries"] == 3
        assert data["daily"]["total_cost"] == 6.0
        assert data["cost_breakdown"]["exchange_fee"] == 4.0
        assert data["cost_breakdown"]["ai_api"] == 2.0


# ════════════════════════════════════════════════════════════════════════════
# PnL 录入测试 / PnL Entry Tests
# ════════════════════════════════════════════════════════════════════════════


class TestPnLEntry:
    """PnL 条目录入端点 / PnL entry input endpoint tests."""

    def test_realized_pnl_accumulates(self):
        """已实现盈亏应累积 / Realized PnL should accumulate."""
        client = build_client()
        rev = get_state_revision(client)

        r = client.post(
            "/api/v1/input/pnl-entry",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "entry_type": "realized",
                "realized_pnl": 10.5,
            }),
        )
        assert r.status_code == 200
        assert r.json()["data"]["accepted"] is True
        assert r.json()["data"]["delta_realized_pnl"] == 10.5

        # 再录入一次 / Record another entry
        rev = get_state_revision(client)
        client.post(
            "/api/v1/input/pnl-entry",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "entry_type": "realized",
                "realized_pnl": 5.0,
            }),
        )

        # 检查每日摘要 / Check daily summary
        summary = client.get("/api/v1/system/business/summary", headers=auth_headers()).json()
        assert summary["data"]["daily"]["realized_pnl"] == 15.5
        assert summary["data"]["entry_totals"]["total_pnl_entries"] == 2

    def test_unrealized_pnl_is_snapshot(self):
        """未实现盈亏取最新快照值 / Unrealized PnL takes the latest snapshot value."""
        client = build_client()
        rev = get_state_revision(client)

        # 第一次录入 unrealized = 100
        client.post(
            "/api/v1/input/pnl-entry",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "entry_type": "unrealized",
                "unrealized_pnl": 100.0,
            }),
        )

        # 第二次录入 unrealized = 50（应覆盖，不累加）
        rev = get_state_revision(client)
        client.post(
            "/api/v1/input/pnl-entry",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "entry_type": "unrealized",
                "unrealized_pnl": 50.0,
            }),
        )

        summary = client.get("/api/v1/system/business/summary", headers=auth_headers()).json()
        # unrealized 应是 50（最新值），不是 150（累加值）
        # unrealized should be 50 (latest), not 150 (accumulated)
        assert summary["data"]["daily"]["unrealized_pnl"] == 50.0

    def test_net_operating_pnl_computed(self):
        """net_operating_pnl 应为 gross_pnl - total_cost / net = gross - cost."""
        client = build_client()

        # 录入费用 / Record cost
        rev = get_state_revision(client)
        client.post(
            "/api/v1/input/cost",
            headers=auth_headers(),
            json=make_envelope(rev, payload={"amount": 3.0, "category": "ai_api"}),
        )

        # 录入 PnL / Record PnL
        rev = get_state_revision(client)
        client.post(
            "/api/v1/input/pnl-entry",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "entry_type": "realized",
                "realized_pnl": 10.0,
            }),
        )

        summary = client.get("/api/v1/system/business/summary", headers=auth_headers()).json()
        daily = summary["data"]["daily"]
        # gross = realized + unrealized = 10 + 0 = 10
        assert daily["gross_pnl"] == 10.0
        # net = gross - cost = 10 - 3 = 7
        assert daily["net_operating_pnl"] == 7.0

    def test_pnl_entries_in_summary_history(self):
        """PnL 条目出现在摘要历史中 / PnL entries appear in summary history."""
        client = build_client()
        rev = get_state_revision(client)
        client.post(
            "/api/v1/input/pnl-entry",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "entry_type": "realized",
                "realized_pnl": 5.0,
                "symbol": "BTCUSDT",
            }),
        )

        summary = client.get("/api/v1/system/business/summary", headers=auth_headers()).json()
        assert len(summary["data"]["pnl_entries_recent"]) == 1
        assert summary["data"]["pnl_entries_recent"][0]["symbol"] == "BTCUSDT"


# ════════════════════════════════════════════════════════════════════════════
# 系统设置变更测试 / System Settings Change Tests
# ════════════════════════════════════════════════════════════════════════════


class TestSystemSettings:
    """通过 config-change 端点修改系统设置 / System settings via config-change endpoint."""

    def test_risk_policy_change(self):
        """风险策略修改应成功 / Risk policy change should succeed."""
        client = build_client()
        rev = get_state_revision(client)
        r = client.post(
            "/api/v1/input/config-change",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "changes": [{
                    "path": "control_plane.risk_envelope.risk_policy_switch",
                    "value": "manual_blocked",
                }]
            }),
        )
        assert r.status_code == 200
        assert "control_plane.risk_envelope.risk_policy_switch" in r.json()["data"]["accepted_paths"]

        # 验证 effective 状态变成 blocking / Verify effective state becomes blocking
        cp = client.get("/api/v1/system/control-plane", headers=auth_headers()).json()
        assert cp["data"]["risk_envelope"]["effective_risk_envelope_state"] == "blocking"

    def test_demo_ack_toggle(self):
        """Demo 确认要求开关应可切换 / Demo ack required should be toggleable."""
        client = build_client()
        rev = get_state_revision(client)
        r = client.post(
            "/api/v1/input/config-change",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "changes": [{
                    "path": "control_plane.demo_control.demo_operator_ack_required",
                    "value": False,
                }]
            }),
        )
        assert r.status_code == 200
        assert r.json()["data"]["accepted_paths"][0] == "control_plane.demo_control.demo_operator_ack_required"

    def test_learning_approval_toggle(self):
        """学习实验审批开关应可切换 / Learning approval should be toggleable."""
        client = build_client()
        rev = get_state_revision(client)
        r = client.post(
            "/api/v1/input/config-change",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "changes": [{
                    "path": "learning_state.experiments.approval_required",
                    "value": False,
                }]
            }),
        )
        assert r.status_code == 200
        assert "learning_state.experiments.approval_required" in r.json()["data"]["accepted_paths"]

    def test_disallowed_path_rejected(self):
        """非白名单路径应被拒绝 / Non-whitelisted path should be rejected."""
        client = build_client()
        rev = get_state_revision(client)
        r = client.post(
            "/api/v1/input/config-change",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "changes": [{
                    "path": "global_runtime.facts.system_mode_fact",
                    "value": "live_reserved",
                }]
            }),
        )
        # 应返回 400（所有路径被拒绝时）/ Should return 400 (all paths rejected)
        assert r.status_code == 400


# ════════════════════════════════════════════════════════════════════════════
# 安全边界测试 / Safety Boundary Tests
# ════════════════════════════════════════════════════════════════════════════


class TestSafetyBoundaries:
    """安全边界检验 / Safety boundary verification."""

    def test_execution_authority_remains_protected(self):
        """任何操作后执行权限仍受保护 / Execution authority remains protected after any operation."""
        client = build_client()

        # 做一系列配置变更 / Perform a series of config changes
        rev = get_state_revision(client)
        client.post(
            "/api/v1/control/product-family/spot/config",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "enabled_switch": True,
                "visibility_switch": True,
                "mode_switch": "shadow_only",
            }),
        )

        # 验证执行权限仍受保护 / Verify execution authority is still protected
        overview = client.get("/api/v1/system/overview", headers=auth_headers()).json()
        assert overview["data"]["global_runtime"]["runtime_still_protected"] is True
        assert overview["data"]["global_runtime"]["global_execution_authority_state"] == "disabled"

    def test_cannot_bypass_execution_via_product_family(self):
        """无法通过产品族配置绕过执行保护 / Cannot bypass execution protection via PF config."""
        client = build_client()
        rev = get_state_revision(client)

        # 尝试把所有产品族都启用为 shadow / Try enabling all PFs as shadow
        for family in ["spot", "margin", "perp_linear", "perp_inverse", "options"]:
            client.post(
                f"/api/v1/control/product-family/{family}/config",
                headers=auth_headers(),
                json=make_envelope(rev, payload={
                    "enabled_switch": True,
                    "visibility_switch": True,
                    "mode_switch": "shadow_only",
                    "action_permissions": {"new_order": True, "cancel": True},
                }),
            )
            rev = get_state_revision(client)

        # 即使全部配置开启，global execution 仍然是 disabled
        # Even with all config enabled, global execution remains disabled
        overview = client.get("/api/v1/system/overview", headers=auth_headers()).json()
        assert overview["data"]["global_runtime"]["global_execution_authority_state"] == "disabled"

    def test_unauthenticated_request_rejected(self):
        """未认证请求应被拒绝 / Unauthenticated request should be rejected."""
        client = build_client()
        r = client.get("/api/v1/system/business/summary")
        assert r.status_code == 401

        r2 = client.post(
            "/api/v1/control/product-family/spot/config",
            json=make_envelope(1, payload={"enabled_switch": True}),
        )
        assert r2.status_code == 401
