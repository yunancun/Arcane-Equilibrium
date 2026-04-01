from __future__ import annotations

"""
MODULE_NOTE (中文):
  控制面板操作模塊。包含概覽構建、J/K 章重新檢查、Demo 狀態轉換（validate/arm/enable/relock）、
  安全包操作、輸入動作、配置變更、產品族配置等業務邏輯函數。
  從 main_legacy.py 拆分而來（Wave C 重構）。

  ★ 所有寫操作通過 _base.STORE.mutate() 和 _base.get_latest_snapshot() 間接訪問
  main_legacy 的單例，確保 monkey-patch 和 importlib.reload 安全。

MODULE_NOTE (English):
  Control plane operations module. Contains overview builder, J/K chapter rechecks,
  Demo state transitions (validate/arm/enable/relock), safe bundle, input actions,
  config changes, and product family config business logic functions.
  Extracted from main_legacy.py (Wave C refactoring).

  ★ All write operations access main_legacy singletons indirectly via
  _base.STORE.mutate() and _base.get_latest_snapshot(), ensuring monkey-patch
  and importlib.reload safety.
"""

import copy
import logging
from typing import Any

from fastapi import HTTPException

from . import main_legacy as _base
from .auth import AuthenticatedActor, require_scope_and_identity
from .state_compiler import (
    ACTION_NAMES,
    CONFIG_CHANGE_WHITELIST,
    PRODUCT_FAMILIES,
    _compile_for_response,
    deep_set,
    now_ms,
)
from .state_helpers import (
    _assert_previous_state,
    _assert_revision,
    _blocked,
    _bump_revision,
    _check_idempotency,
    _store_idempotent_response,
    _write_audit_fields,
    ensure_source_is_usable,
)
from .state_models import RequestEnvelope

logger = logging.getLogger(__name__)


def build_overview(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "global_runtime": {
            "global_stage_label": snapshot["global_runtime"]["derived"]["global_stage_label"],
            "global_mode_state": snapshot["global_runtime"]["derived"]["global_mode_state"],
            "global_capability_state": snapshot["global_runtime"]["derived"]["global_capability_state"],
            "global_execution_authority_state": snapshot["global_runtime"]["derived"]["global_execution_authority_state"],
            "runtime_still_protected": snapshot["global_runtime"]["derived"]["runtime_still_protected"],
        },
        "chapter_status_summary": snapshot["chapter_status"],
        "daily_business_summary": snapshot["business_metrics"]["daily"],
        "health_summary": snapshot["health_telemetry"],
        "demo_control_summary": {
            "demo_state_switch": snapshot["control_plane"]["demo_control"]["demo_state_switch"],
            "demo_prerequisites_gate_state": snapshot["control_plane"]["demo_control"]["demo_prerequisites_gate_state"],
            "demo_arm_gate_state": snapshot["control_plane"]["demo_control"]["demo_arm_gate_state"],
            "demo_enable_gate_state": snapshot["control_plane"]["demo_control"]["demo_enable_gate_state"],
            "demo_relock_gate_state": snapshot["control_plane"]["demo_control"]["demo_relock_gate_state"],
        },
        "latest_control_action_summary": {
            "last_control_action_type": snapshot["audit_context"]["last_control_action_type"],
            "last_control_action_ts_ms": snapshot["audit_context"]["last_control_action_ts_ms"],
            "last_control_action_result": snapshot["audit_context"]["last_control_action_result"],
            "last_control_action_reason_codes": snapshot["audit_context"]["last_control_action_reason_codes"],
            "last_control_action_audit_ref": snapshot["audit_context"]["last_control_action_audit_ref"],
        },
        "latest_write_action_summary": {
            "last_write_action_type": snapshot["audit_context"]["last_write_action_type"],
            "last_write_action_ts_ms": snapshot["audit_context"]["last_write_action_ts_ms"],
            "last_write_action_result": snapshot["audit_context"]["last_write_action_result"],
            "last_write_action_reason_codes": snapshot["audit_context"]["last_write_action_reason_codes"],
            "last_write_action_audit_ref": snapshot["audit_context"]["last_write_action_audit_ref"],
        },
    }


def perform_recheck(envelope: RequestEnvelope, actor: AuthenticatedActor, chapter: str, kind: str) -> tuple[dict[str, Any], str]:
    snapshot, source_context = _base.get_latest_snapshot()
    require_scope_and_identity(actor, "control:recheck", envelope)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)
    ensure_source_is_usable(source_context)

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        ts = now_ms()
        target = state["capability_matrix"][chapter]
        if kind == "canonical":
            target["canonical_recheck_state"] = "passed"
            target["canonical_recheck_last_verified_ts_ms"] = ts
        else:
            target["closeout_state"] = "passed"
            target["closeout_last_verified_ts_ms"] = ts

        state["chapter_status"][chapter]["last_verified_ts_ms"] = ts
        audit_ref = _write_audit_fields(
            state,
            action_type=f"{chapter.lower()}_{kind}_recheck",
            operator_id=actor.actor_id,
            request_id=envelope.request_id,
            result="success",
            reason_codes=[],
            is_control_action=True,
        )
        _bump_revision(state)
        compiled = _compile_for_response(state)
        response = {
            "audit_ref": audit_ref,
            "data": {
                "chapter": chapter,
                "recheck_kind": kind,
                "recheck_state": "passed",
                "last_verified_ts_ms": ts,
                "chapter_snapshot": copy.deepcopy(compiled["chapter_status"][chapter]),
                "pinned_runtime_snapshot_id": _base.build_source_context(compiled).pinned_runtime_snapshot_id,
            },
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        return compiled

    final_state = _base.STORE.mutate(mutator)
    source = _base.build_source_context(final_state)
    return {
        "audit_ref": final_state["audit_context"]["last_control_action_audit_ref"],
        "data": {
            "chapter": chapter,
            "recheck_kind": kind,
            "recheck_state": "passed",
            "last_verified_ts_ms": final_state["chapter_status"][chapter]["last_verified_ts_ms"],
            "chapter_snapshot": final_state["chapter_status"][chapter],
            "pinned_runtime_snapshot_id": source.pinned_runtime_snapshot_id,
        },
        "snapshot": final_state,
    }, "success"


def perform_validate(envelope: RequestEnvelope, actor: AuthenticatedActor) -> tuple[dict[str, Any], str]:
    snapshot, source_context = _base.get_latest_snapshot()
    require_scope_and_identity(actor, "control:validate", envelope)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)
    ensure_source_is_usable(source_context)

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        ts = now_ms()
        demo = state["control_plane"]["demo_control"]
        demo["demo_validate_requested"] = True
        demo["demo_prerequisites_last_evaluated_ts_ms"] = ts
        demo["demo_arm_last_evaluated_ts_ms"] = ts
        demo["demo_enable_last_evaluated_ts_ms"] = ts
        demo["demo_relock_last_evaluated_ts_ms"] = ts
        demo["demo_last_action_type"] = "validate"
        demo["demo_last_action_result"] = "success"
        demo["demo_last_action_reason_codes"] = []
        demo["demo_last_action_ts_ms"] = ts

        audit_ref = _write_audit_fields(
            state,
            action_type="demo_validate",
            operator_id=actor.actor_id,
            request_id=envelope.request_id,
            result="success",
            reason_codes=[],
            is_control_action=True,
        )
        _bump_revision(state)
        compiled = _compile_for_response(state)
        response = {
            "audit_ref": audit_ref,
            "data": {
                "demo_state_switch": compiled["control_plane"]["demo_control"]["demo_state_switch"],
                "demo_prerequisites_gate_state": compiled["control_plane"]["demo_control"]["demo_prerequisites_gate_state"],
                "demo_prerequisites_reason_codes": compiled["control_plane"]["demo_control"]["demo_prerequisites_reason_codes"],
                "demo_arm_gate_state": compiled["control_plane"]["demo_control"]["demo_arm_gate_state"],
                "demo_arm_reason_codes": compiled["control_plane"]["demo_control"]["demo_arm_reason_codes"],
                "demo_enable_gate_state": compiled["control_plane"]["demo_control"]["demo_enable_gate_state"],
                "demo_enable_reason_codes": compiled["control_plane"]["demo_control"]["demo_enable_reason_codes"],
                "demo_relock_gate_state": compiled["control_plane"]["demo_control"]["demo_relock_gate_state"],
                "demo_relock_reason_codes": compiled["control_plane"]["demo_control"]["demo_relock_reason_codes"],
                "pinned_runtime_snapshot_id": _base.build_source_context(compiled).pinned_runtime_snapshot_id,
            },
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        return compiled

    final_state = _base.STORE.mutate(mutator)
    source = _base.build_source_context(final_state)
    return {
        "audit_ref": final_state["audit_context"]["last_control_action_audit_ref"],
        "data": {
            "demo_state_switch": final_state["control_plane"]["demo_control"]["demo_state_switch"],
            "demo_prerequisites_gate_state": final_state["control_plane"]["demo_control"]["demo_prerequisites_gate_state"],
            "demo_prerequisites_reason_codes": final_state["control_plane"]["demo_control"]["demo_prerequisites_reason_codes"],
            "demo_arm_gate_state": final_state["control_plane"]["demo_control"]["demo_arm_gate_state"],
            "demo_arm_reason_codes": final_state["control_plane"]["demo_control"]["demo_arm_reason_codes"],
            "demo_enable_gate_state": final_state["control_plane"]["demo_control"]["demo_enable_gate_state"],
            "demo_enable_reason_codes": final_state["control_plane"]["demo_control"]["demo_enable_reason_codes"],
            "demo_relock_gate_state": final_state["control_plane"]["demo_control"]["demo_relock_gate_state"],
            "demo_relock_reason_codes": final_state["control_plane"]["demo_control"]["demo_relock_reason_codes"],
            "pinned_runtime_snapshot_id": source.pinned_runtime_snapshot_id,
        },
        "snapshot": final_state,
    }, "success"


def perform_demo_transition(envelope: RequestEnvelope, actor: AuthenticatedActor, action: str) -> tuple[dict[str, Any], str]:
    scope_map = {"arm": "control:arm", "enable": "control:enable", "relock": "control:relock"}
    snapshot, source_context = _base.get_latest_snapshot()
    require_scope_and_identity(actor, scope_map[action], envelope)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)
    ensure_source_is_usable(source_context)

    if action == "arm":
        _assert_previous_state(snapshot, envelope, {"closed", "relocked"})
        if snapshot["control_plane"]["demo_control"]["demo_prerequisites_gate_state"] != "passed":
            _blocked(["prerequisites_not_passed"])
        if snapshot["global_runtime"]["controls"]["global_execution_mode_switch"] != "demo_reserved":
            _blocked(["execution_mode_disabled"])
        if snapshot["control_plane"]["demo_control"]["demo_operator_ack_required"] and not envelope.payload.get("acknowledged", False):
            _blocked(["operator_ack_required"])

    if action == "enable":
        _assert_previous_state(snapshot, envelope, {"armed_but_closed"})
        if snapshot["control_plane"]["demo_control"]["demo_enable_gate_state"] != "passed":
            _blocked(snapshot["control_plane"]["demo_control"]["demo_enable_reason_codes"])
        if snapshot["control_plane"]["demo_control"]["demo_operator_ack_required"] and not envelope.payload.get("acknowledged", False):
            _blocked(["operator_ack_required"])

    if action == "relock":
        _assert_previous_state(snapshot, envelope, {"armed_but_closed", "demo_enabled", "relocked"})

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        demo = state["control_plane"]["demo_control"]
        previous = demo["demo_state_switch"]
        ts = now_ms()
        reason_codes: list[str] = []

        if action == "arm":
            demo["demo_state_switch"] = "armed_but_closed"
        elif action == "enable":
            demo["demo_state_switch"] = "demo_enabled"
            demo["demo_operator_ack_completed"] = True
        elif action == "relock":
            demo["demo_state_switch"] = "relocked"
            demo["demo_cooldown_state"] = "active"
            demo["demo_cooldown_until_ts_ms"] = envelope.client_ts_ms + 300000

        demo["demo_last_action_type"] = action
        demo["demo_last_action_result"] = "success"
        demo["demo_last_action_reason_codes"] = reason_codes
        demo["demo_last_action_ts_ms"] = ts

        audit_ref = _write_audit_fields(
            state,
            action_type=f"demo_{action}",
            operator_id=actor.actor_id,
            request_id=envelope.request_id,
            result="success",
            reason_codes=reason_codes,
            is_control_action=True,
        )
        _bump_revision(state)
        compiled = _compile_for_response(state)
        response = {
            "audit_ref": audit_ref,
            "data": {
                "demo_state_switch": compiled["control_plane"]["demo_control"]["demo_state_switch"],
                "previous_demo_state_switch": previous,
                "gate_state": "passed",
                "reason_codes": [],
                "pinned_runtime_snapshot_id": _base.build_source_context(compiled).pinned_runtime_snapshot_id,
            },
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        return compiled

    final_state = _base.STORE.mutate(mutator)
    source = _base.build_source_context(final_state)
    previous_state = snapshot["control_plane"]["demo_control"]["demo_state_switch"]
    return {
        "audit_ref": final_state["audit_context"]["last_control_action_audit_ref"],
        "data": {
            "demo_state_switch": final_state["control_plane"]["demo_control"]["demo_state_switch"],
            "previous_demo_state_switch": previous_state,
            "gate_state": "passed",
            "reason_codes": [],
            "pinned_runtime_snapshot_id": source.pinned_runtime_snapshot_id,
        },
        "snapshot": final_state,
    }, "success"


def perform_safe_bundle(envelope: RequestEnvelope, actor: AuthenticatedActor) -> tuple[dict[str, Any], str]:
    snapshot, source_context = _base.get_latest_snapshot()
    require_scope_and_identity(actor, "control:bundle", envelope)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)
    ensure_source_is_usable(source_context)

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        ts = now_ms()
        for chapter in ("J", "K"):
            state["capability_matrix"][chapter]["canonical_recheck_state"] = "passed"
            state["capability_matrix"][chapter]["canonical_recheck_last_verified_ts_ms"] = ts
            state["capability_matrix"][chapter]["closeout_state"] = "passed"
            state["capability_matrix"][chapter]["closeout_last_verified_ts_ms"] = ts
            state["chapter_status"][chapter]["last_verified_ts_ms"] = ts

        demo = state["control_plane"]["demo_control"]
        demo["demo_validate_requested"] = True
        demo["demo_prerequisites_last_evaluated_ts_ms"] = ts
        demo["demo_arm_last_evaluated_ts_ms"] = ts
        demo["demo_enable_last_evaluated_ts_ms"] = ts
        demo["demo_relock_last_evaluated_ts_ms"] = ts
        demo["demo_last_action_type"] = "safe_recheck_bundle"
        demo["demo_last_action_result"] = "success"
        demo["demo_last_action_reason_codes"] = []
        demo["demo_last_action_ts_ms"] = ts

        audit_ref = _write_audit_fields(
            state,
            action_type="safe_recheck_bundle",
            operator_id=actor.actor_id,
            request_id=envelope.request_id,
            result="success",
            reason_codes=[],
            is_control_action=True,
        )
        _bump_revision(state)
        compiled = _compile_for_response(state)
        steps = [
            {"step_name": "j-canonical", "action_result": "success", "reason_codes": [], "audit_ref": audit_ref},
            {"step_name": "k-canonical", "action_result": "success", "reason_codes": [], "audit_ref": audit_ref},
            {"step_name": "j-closeout", "action_result": "success", "reason_codes": [], "audit_ref": audit_ref},
            {"step_name": "k-closeout", "action_result": "success", "reason_codes": [], "audit_ref": audit_ref},
            {"step_name": "demo-validate", "action_result": "success", "reason_codes": [], "audit_ref": audit_ref},
        ]
        response = {
            "audit_ref": audit_ref,
            "data": {
                "bundle_base_snapshot_id": snapshot["meta"]["snapshot_id"],
                "bundle_final_snapshot_id": compiled["meta"]["snapshot_id"],
                "bundle_committed": True,
                "steps": steps,
            },
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        return compiled

    final_state = _base.STORE.mutate(mutator)
    return {
        "audit_ref": final_state["audit_context"]["last_control_action_audit_ref"],
        "data": {
            "bundle_base_snapshot_id": snapshot["meta"]["snapshot_id"],
            "bundle_final_snapshot_id": final_state["meta"]["snapshot_id"],
            "bundle_committed": True,
            "steps": [
                {"step_name": "j-canonical", "action_result": "success", "reason_codes": [], "audit_ref": final_state["audit_context"]["last_control_action_audit_ref"]},
                {"step_name": "k-canonical", "action_result": "success", "reason_codes": [], "audit_ref": final_state["audit_context"]["last_control_action_audit_ref"]},
                {"step_name": "j-closeout", "action_result": "success", "reason_codes": [], "audit_ref": final_state["audit_context"]["last_control_action_audit_ref"]},
                {"step_name": "k-closeout", "action_result": "success", "reason_codes": [], "audit_ref": final_state["audit_context"]["last_control_action_audit_ref"]},
                {"step_name": "demo-validate", "action_result": "success", "reason_codes": [], "audit_ref": final_state["audit_context"]["last_control_action_audit_ref"]},
            ],
        },
        "snapshot": final_state,
    }, "success"


def apply_input_action(envelope: RequestEnvelope, actor: AuthenticatedActor, action: str) -> tuple[dict[str, Any], str]:
    scope_map = {"cost": "input:cost", "event": "input:event", "manual-note": "input:note"}
    snapshot, _ = _base.get_latest_snapshot()
    require_scope_and_identity(actor, scope_map[action], envelope)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        delta = 0
        payload = dict(envelope.payload)
        payload["recorded_ts_ms"] = now_ms()

        if action == "cost":
            amount = float(payload.get("amount", 0))
            state["records"]["cost_entries"].append(payload)
            state["business_metrics"]["daily"]["total_cost"] += amount
            state["business_metrics"]["daily"]["manual_cost_source_count"] += 1
            state["business_metrics"]["daily"]["net_operating_pnl"] -= amount
            delta = 1
        elif action == "event":
            state["records"]["event_entries"].append(payload)
            state["business_metrics"]["daily"]["business_event_count"] += 1
            delta = 1
        else:
            state["learning_state"]["records"]["manual_notes"].append(payload)
            delta = 1

        audit_ref = _write_audit_fields(
            state,
            action_type=action.replace("-", "_"),
            operator_id=actor.actor_id,
            request_id=envelope.request_id,
            result="success",
            reason_codes=[],
            is_control_action=False,
        )
        _bump_revision(state)
        compiled = _compile_for_response(state)
        response = {"audit_ref": audit_ref, "data": {"accepted": True, "record_count_delta": delta}, "snapshot": compiled}
        _store_idempotent_response(compiled, envelope, response)
        return compiled

    final_state = _base.STORE.mutate(mutator)
    return {
        "audit_ref": final_state["audit_context"]["last_write_action_audit_ref"],
        "data": {"accepted": True, "record_count_delta": 1},
        "snapshot": final_state,
    }, "success"


def apply_config_change(envelope: RequestEnvelope, actor: AuthenticatedActor) -> tuple[dict[str, Any], str]:
    snapshot, _ = _base.get_latest_snapshot()
    require_scope_and_identity(actor, "input:config", envelope)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)

    changes = envelope.payload.get("changes")
    if not isinstance(changes, list) or not changes:
        raise HTTPException(status_code=400, detail={"reason_codes": ["cfg_field_required"]})

    accepted_paths: list[str] = []
    rejected_paths: list[str] = []

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        for item in changes:
            if not isinstance(item, dict) or "path" not in item:
                raise HTTPException(status_code=400, detail={"reason_codes": ["cfg_field_required"]})
            path = item["path"]
            value = item.get("value")
            if path not in CONFIG_CHANGE_WHITELIST:
                rejected_paths.append(path)
                continue
            deep_set(state, path, value)
            accepted_paths.append(path)

        if not accepted_paths:
            raise HTTPException(status_code=400, detail={"reason_codes": ["path_not_whitelisted"]})

        audit_ref = _write_audit_fields(
            state,
            action_type="config_change",
            operator_id=actor.actor_id,
            request_id=envelope.request_id,
            result="success",
            reason_codes=[],
            is_control_action=False,
        )
        _bump_revision(state)
        compiled = _compile_for_response(state)
        response = {
            "audit_ref": audit_ref,
            "data": {"accepted_paths": accepted_paths, "rejected_paths": rejected_paths},
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        return compiled

    final_state = _base.STORE.mutate(mutator)
    return {
        "audit_ref": final_state["audit_context"]["last_write_action_audit_ref"],
        "data": {"accepted_paths": accepted_paths, "rejected_paths": rejected_paths},
        "snapshot": final_state,
    }, "success"


# ── 产品族配置写接口 / Product Family Config Write ───────────────────────────

# 当前阶段允许的 mode_switch 值（live 相关值不在此阶段开放）
# Allowed mode_switch values at this stage (live_reserved NOT opened yet)
# demo_reserved 已開放：Paper+Demo 雙引擎模式可用於 linear 和 spot
ALLOWED_MODE_SWITCHES: frozenset[str] = frozenset({"disabled", "observe_only", "shadow_only", "demo_reserved"})



def apply_product_family_config(
    envelope: RequestEnvelope,
    actor: AuthenticatedActor,
    family: str,
) -> tuple[dict[str, Any], str]:
    """
    应用产品族控制配置变更 / Apply product family control configuration changes.

    支持修改：enabled_switch / visibility_switch / mode_switch / action_permissions
    Supports modifying: enabled_switch / visibility_switch / mode_switch / action_permissions

    安全规则 / Safety rules:
    - mode_switch 允许: disabled / observe_only / shadow_only / demo_reserved
      mode_switch allows: disabled / observe_only / shadow_only / demo_reserved
    - 不能直接把产品族升到 live 相关模式（live_reserved 仍锁定）
      Cannot directly set a product family to live-related modes (live_reserved still locked)
    - 需要 input:config scope
      Requires input:config scope
    """
    if family not in PRODUCT_FAMILIES:
        raise HTTPException(
            status_code=400,
            detail={"reason_codes": ["invalid_product_family"]},
        )

    snapshot, _ = _base.get_latest_snapshot()
    require_scope_and_identity(actor, "input:config", envelope)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)

    applied_changes: dict[str, Any] = {}
    rejected_fields: list[str] = []
    payload = dict(envelope.payload)

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        pf_controls = state["product_family_status"][family]["controls"]

        # 处理 enabled_switch（布尔值）/ Handle enabled_switch (boolean)
        if "enabled_switch" in payload:
            val = payload["enabled_switch"]
            if isinstance(val, bool):
                pf_controls["enabled_switch"] = val
                applied_changes["enabled_switch"] = val
            else:
                rejected_fields.append("enabled_switch:invalid_type")

        # 处理 visibility_switch（布尔值）/ Handle visibility_switch (boolean)
        if "visibility_switch" in payload:
            val = payload["visibility_switch"]
            if isinstance(val, bool):
                pf_controls["visibility_switch"] = val
                applied_changes["visibility_switch"] = val
            else:
                rejected_fields.append("visibility_switch:invalid_type")

        # 处理 mode_switch（只允许受限值）/ Handle mode_switch (only allowed values)
        if "mode_switch" in payload:
            val = payload["mode_switch"]
            if val in ALLOWED_MODE_SWITCHES:
                pf_controls["mode_switch"] = val
                applied_changes["mode_switch"] = val
            else:
                rejected_fields.append(f"mode_switch:{val}:not_allowed_at_this_stage")

        # 处理每个动作的开关权限 / Handle per-action permission switches
        action_perms_payload = payload.get("action_permissions", {})
        if isinstance(action_perms_payload, dict):
            pf_perms = state["control_plane"]["action_permissions"]["by_product_family"][family]
            for action_name, val in action_perms_payload.items():
                key = f"configured_{action_name}_allowed_switch"
                if action_name in ACTION_NAMES and isinstance(val, bool):
                    pf_perms[key] = val
                    applied_changes[f"action_permissions.{action_name}"] = val
                else:
                    rejected_fields.append(f"action_permissions.{action_name}:invalid")

        # 更新审计字段 / Update audit fields
        state["product_family_status"][family]["audit"] = {
            "last_change_ts_ms": now_ms(),
            "last_change_by": actor.actor_id,
        }

        result_str = "success" if applied_changes else "blocked"
        audit_ref = _write_audit_fields(
            state,
            action_type=f"product_family_config_{family}",
            operator_id=actor.actor_id,
            request_id=envelope.request_id,
            result=result_str,
            reason_codes=rejected_fields,
            is_control_action=False,
        )
        _bump_revision(state)
        compiled = _compile_for_response(state)
        response = {
            "audit_ref": audit_ref,
            "data": {
                "family": family,
                "applied_changes": dict(applied_changes),
                "rejected_fields": list(rejected_fields),
                "current_controls": copy.deepcopy(compiled["product_family_status"][family]["controls"]),
                "current_derived": copy.deepcopy(compiled["product_family_status"][family]["derived"]),
                "current_action_permissions": copy.deepcopy(
                    compiled["control_plane"]["action_permissions"]["by_product_family"][family]
                ),
            },
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        return compiled

    final_state = _base.STORE.mutate(mutator)
    return {
        "audit_ref": final_state["audit_context"]["last_write_action_audit_ref"],
        "data": {
            "family": family,
            "applied_changes": applied_changes,
            "rejected_fields": rejected_fields,
            "current_controls": final_state["product_family_status"][family]["controls"],
            "current_derived": final_state["product_family_status"][family]["derived"],
            "current_action_permissions": final_state["control_plane"]["action_permissions"]["by_product_family"][family],
        },
        "snapshot": final_state,
    }, "success" if applied_changes else "blocked"

