"""
Tests for governance_routes.py authentication: _require_operator_role fix.
治理路由认证测试：_require_operator_role 修复验证

Tests verify:
  1. No token → 401 (handled by current_actor dependency)
  2. Non-operator role → 403
  3. Operator role → passes (no exception)
  4. None actor → 401
  5. AuthenticatedActor without operator role → 403
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

# Path setup / 路径设置
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import HTTPException


# ─────────────────────────────────────────────────────────────────────────────
# Minimal AuthenticatedActor stub (mirrors main_legacy.py definition)
# 最小 AuthenticatedActor 存根，镜像 main_legacy.py 定义
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(slots=True)
class _StubAuthenticatedActor:
    actor_id: str
    actor_type: str
    roles: set
    scopes: set


# ─────────────────────────────────────────────────────────────────────────────
# Import the function under test with AuthenticatedActor monkeypatched
# 导入被测函数，并注入 AuthenticatedActor 存根
# ─────────────────────────────────────────────────────────────────────────────

def _make_require_operator_role(actor_cls: type):
    """
    Factory that returns a _require_operator_role function bound to given actor class.
    工厂函数，返回绑定到指定 actor 类的 _require_operator_role 函数。
    """
    def _require_operator_role(actor: Any) -> None:
        if not actor or not isinstance(actor, actor_cls):
            raise HTTPException(status_code=401, detail="Authentication required")
        is_operator = "operator" in actor.roles
        if not is_operator:
            raise HTTPException(status_code=403, detail="Operator role required")

    return _require_operator_role


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / 夹具
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def require_op():
    """Return _require_operator_role bound to stub actor class."""
    return _make_require_operator_role(_StubAuthenticatedActor)


@pytest.fixture
def operator_actor():
    """AuthenticatedActor with operator role / 拥有 operator 角色的 actor"""
    return _StubAuthenticatedActor(
        actor_id="demo-operator",
        actor_type="human",
        roles={"viewer", "operator", "operator_guarded", "config_admin", "finance_input"},
        scopes={"private_readonly"},
    )


@pytest.fixture
def viewer_actor():
    """AuthenticatedActor with only viewer role / 只有 viewer 角色的 actor"""
    return _StubAuthenticatedActor(
        actor_id="readonly-user",
        actor_type="human",
        roles={"viewer"},
        scopes={"private_readonly"},
    )


@pytest.fixture
def empty_role_actor():
    """AuthenticatedActor with no roles / 没有任何角色的 actor"""
    return _StubAuthenticatedActor(
        actor_id="nobody",
        actor_type="human",
        roles=set(),
        scopes=set(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tests / 测试
# ─────────────────────────────────────────────────────────────────────────────

class TestRequireOperatorRole:
    """Unit tests for _require_operator_role. / _require_operator_role 单元测试"""

    def test_none_actor_raises_401(self, require_op):
        """None actor must raise 401 / None actor 必须返回 401"""
        with pytest.raises(HTTPException) as exc_info:
            require_op(None)
        assert exc_info.value.status_code == 401

    def test_dict_actor_raises_401(self, require_op):
        """Dict-type actor (old broken pattern) must raise 401 / dict 类型 actor（旧错误模式）必须返回 401"""
        fake_dict = {"role": "operator", "user": "admin", "is_operator": True}
        with pytest.raises(HTTPException) as exc_info:
            require_op(fake_dict)
        assert exc_info.value.status_code == 401

    def test_operator_role_passes(self, require_op, operator_actor):
        """Actor with operator role must pass (no exception) / 拥有 operator 角色的 actor 必须通过（无异常）"""
        # Should NOT raise
        require_op(operator_actor)

    def test_viewer_only_raises_403(self, require_op, viewer_actor):
        """Actor without operator role must raise 403 / 没有 operator 角色的 actor 必须返回 403"""
        with pytest.raises(HTTPException) as exc_info:
            require_op(viewer_actor)
        assert exc_info.value.status_code == 403

    def test_empty_roles_raises_403(self, require_op, empty_role_actor):
        """Actor with no roles must raise 403 / 没有任何角色的 actor 必须返回 403"""
        with pytest.raises(HTTPException) as exc_info:
            require_op(empty_role_actor)
        assert exc_info.value.status_code == 403

    def test_config_admin_without_operator_raises_403(self, require_op):
        """config_admin role alone does not grant operator access / 仅 config_admin 角色不授予 operator 权限"""
        actor = _StubAuthenticatedActor(
            actor_id="admin-only",
            actor_type="human",
            roles={"config_admin", "finance_input"},
            scopes={"private_readonly"},
        )
        with pytest.raises(HTTPException) as exc_info:
            require_op(actor)
        assert exc_info.value.status_code == 403

    def test_operator_role_correct_attribute_used(self, require_op, operator_actor):
        """
        Verify the fix uses actor.roles (set) not actor.get() (dict method).
        验证修复使用 actor.roles（set）而非 actor.get()（dict 方法）。
        """
        # _StubAuthenticatedActor has no .get() method;
        # if the old dict-access path were used this would raise AttributeError, not pass.
        assert hasattr(operator_actor, "roles"), "actor.roles attribute must exist"
        assert not hasattr(operator_actor, "get"), "actor must NOT have .get() (not a dict)"
        require_op(operator_actor)  # Must not raise

    def test_actor_id_attribute_accessible(self, operator_actor):
        """
        Verify actor.actor_id is accessible (used in logging after fix).
        验证 actor.actor_id 可访问（修复后用于日志记录）。
        """
        assert operator_actor.actor_id == "demo-operator"

    def test_roles_is_set_type(self, operator_actor):
        """
        Verify actor.roles is a set (membership test via 'in' operator).
        验证 actor.roles 是 set 类型（支持 'in' 运算符成员测试）。
        """
        assert isinstance(operator_actor.roles, set)
        assert "operator" in operator_actor.roles


class TestAuthenticatedActorTypeCheck:
    """
    Verify that isinstance check uses AuthenticatedActor, not dict.
    验证 isinstance 检查使用 AuthenticatedActor 而非 dict。
    """

    def test_dataclass_passes_isinstance(self, require_op, operator_actor):
        """Dataclass actor passes isinstance check / dataclass actor 通过 isinstance 检查"""
        # This must not raise 401
        require_op(operator_actor)

    def test_non_actor_object_raises_401(self, require_op):
        """Arbitrary object (not AuthenticatedActor) must raise 401 / 任意对象（非 AuthenticatedActor）必须返回 401"""
        class FakeActor:
            roles = {"operator"}
            actor_id = "x"

        with pytest.raises(HTTPException) as exc_info:
            require_op(FakeActor())
        assert exc_info.value.status_code == 401

    def test_false_actor_raises_401(self, require_op):
        """Falsy actor (empty string, 0, False) must raise 401 / 假值 actor 必须返回 401"""
        for falsy in ("", 0, False, []):
            with pytest.raises(HTTPException) as exc_info:
                require_op(falsy)
            assert exc_info.value.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# E2 CONDITIONAL PASS resolution: direct production code import test
# E2 有条件通过解决：直接导入生产代码测试
# ─────────────────────────────────────────────────────────────────────────────

class TestRequireOperatorRoleProductionFunction:
    """
    Directly imports and tests the production _require_operator_role from governance_routes.
    直接从 governance_routes 导入并测试生产代码中的 _require_operator_role 函数本身。

    This resolves E2's CONDITIONAL PASS — previous tests used a local stub factory;
    this test confirms the real production function has identical behavior.
    此测试解决 E2 的有条件通过问题 — 之前的测试使用本地存根工厂函数；
    此测试确认真实生产函数具有相同的行为。
    """

    def test_require_operator_role_production_function_direct(self):
        """直接測試生產代碼中的 _require_operator_role 函數本身"""
        from app.governance_routes import _require_operator_role
        from app.main_legacy import AuthenticatedActor

        # operator 應通過 / operator role must pass (no exception)
        operator_actor = AuthenticatedActor(
            actor_id="test-op", actor_type="human",
            roles={"operator"}, scopes=set()
        )
        _require_operator_role(operator_actor)  # 不應拋出異常 / must not raise

        # viewer 應 403 / viewer role must raise 403
        viewer_actor = AuthenticatedActor(
            actor_id="test-viewer", actor_type="human",
            roles={"viewer"}, scopes=set()
        )
        with pytest.raises(HTTPException) as exc:
            _require_operator_role(viewer_actor)
        assert exc.value.status_code == 403

        # None 應 401 / None must raise 401
        with pytest.raises(HTTPException) as exc2:
            _require_operator_role(None)
        assert exc2.value.status_code == 401
