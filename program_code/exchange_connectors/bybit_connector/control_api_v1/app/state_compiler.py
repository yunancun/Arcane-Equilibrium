"""
MODULE_NOTE (中文):
  狀態編譯器模塊。包含 compile_state() 及所有 _compile_* 派生字段計算函數，
  加上系統常量（ACTION_NAMES、PRODUCT_FAMILIES、學習系統白名單等）。
  從 main_legacy.py 拆分而來。所有函數為純函數（輸入→輸出），
  不持有狀態，不引用 STORE singleton。

MODULE_NOTE (English):
  State compiler module. Contains compile_state() and all _compile_* derived-field
  computation functions, plus system constants (ACTION_NAMES, PRODUCT_FAMILIES,
  learning system whitelists, etc.). Extracted from main_legacy.py.
  All functions are pure (input→output), hold no state, do not reference the STORE singleton.
"""
from __future__ import annotations

import copy
import hashlib
import inspect as _inspect
import json
import threading
import time
import weakref
from typing import Any

from .utils.time_utils import now_ms

from fastapi import HTTPException

from .state_models import EffectiveRiskEnvelopeState


# ── L 章学习系统常量 / L-chapter Learning System Constants ────────────────────

# 观察类别白名单 / Allowed observation categories
# 用于验证观察记录的 category 字段
# Used to validate the category field of observation records
OBSERVATION_CATEGORIES = frozenset({"market", "execution", "cost", "system", "strategy", "other"})

# 经验教训类别白名单 / Allowed lesson categories
# 用于验证经验教训的 category 字段
# Used to validate the category field of lesson records
LESSON_CATEGORIES = frozenset({"market_pattern", "cost_insight", "execution_quality", "strategy", "system", "other"})

# 置信度级别白名单 / Allowed confidence levels
# 原则 8：所有结论区分事实 / 推断 / 假设
# Principle 8: all conclusions must distinguish fact / inference / hypothesis
CONFIDENCE_LEVELS = frozenset({"fact", "inference", "hypothesis"})

# 假设审批动作白名单 / Allowed hypothesis verdict actions
HYPOTHESIS_VERDICT_ACTIONS = frozenset({"approved", "rejected", "archived"})

# 实验审批动作白名单 / Allowed experiment approval actions
EXPERIMENT_APPROVAL_ACTIONS = frozenset({"approved", "rejected"})

# ── L 章自动学习管线常量 / L-chapter Auto Learning Pipeline Constants ────────
# 审核包状态白名单 / Review packet status whitelist
REVIEW_PACKET_STATUSES = frozenset({
    "pending_review",    # 待审核
    "approved",          # 已批准
    "rejected",          # 已拒绝
    "deferred",          # 已搁置
    "ai_consulted",      # AI 已咨询（等待最终决定）
})

# 审核包类型白名单 / Review packet type whitelist
REVIEW_PACKET_TYPES = frozenset({
    "auto_observation",   # 自动观察
    "auto_lesson",        # 自动经验
    "auto_hypothesis",    # 自动假设
})

# 审核包决策动作白名单 / Review packet decision action whitelist
REVIEW_DECISION_ACTIONS = frozenset({
    "approve",   # 批准
    "reject",    # 拒绝
    "defer",     # 搁置
    "ask_ai",    # 询问 AI
})

# 自动观察扫描类型白名单 / Auto scan type whitelist
AUTO_SCAN_TYPES = frozenset({"observations", "lessons", "hypotheses"})


# ── 输入长度限制 / Input length limits ─────────────────────────────────────────
_MAX_TEXT_SHORT = 200   # 标题 / title 类
_MAX_TEXT_LONG = 2000   # 详情 / detail / description 类
_MAX_TEXT_REASON = 500  # 理由 / reason 类
_MAX_PAYLOAD_SIZE = 50000  # payload JSON 总字节 / total payload bytes

# Module-level cache for compile_state signature inspection.
# Uses WeakKeyDictionary so the function object itself is the key; when compile_state is
# monkey-patched (e.g. in tests) the old entry is automatically GC'd and the new function
# gets a fresh lookup.  id()-keyed plain dicts risk false hits after GC id reuse.
# 模块级签名缓存：以函数对象为键（WeakKeyDictionary），避免高频 _compile_for_response
# 路径重复调用 inspect.signature()；GC 回收旧函数后条目自动消失，不存在 id 重用误判。
_COMPILE_STATE_SIG_CACHE: weakref.WeakKeyDictionary[Any, bool] = weakref.WeakKeyDictionary()

# ── B6 dirty-flag memoization for compile_state ─────────────────────────────
# Cache the last compiled result and skip recomputation when state has not
# changed.  Any write/mutate operation must call mark_compile_dirty() to
# invalidate the cache.  This avoids O(n) list scans on every read.
# B6 脏标志缓存：缓存上次编译结果，在状态未变时跳过重复计算。
# 任何写入/变更操作必须调用 mark_compile_dirty() 使缓存失效。
_compile_cache: dict[str, Any] = {}
_compile_dirty: bool = True
# Lock protecting _compile_cache and _compile_dirty against concurrent access.
# 保護 _compile_cache 和 _compile_dirty 的線程鎖，防止並發讀寫競態。
_compile_cache_lock = threading.Lock()


def mark_compile_dirty() -> None:
    """
    Mark the compile cache as dirty so the next compile_state() recomputes.
    Called by any code path that mutates state (write / mutate operations).
    标记编译缓存为脏，使下次 compile_state() 重新计算。
    由任何修改状态的代码路径（写入/变更操作）调用。
    """
    global _compile_dirty
    with _compile_cache_lock:
        _compile_dirty = True


def _validate_text_length(value: str, field_name: str, max_len: int) -> str:
    """验证文本长度，超限抛 400 / Validate text length, raise 400 if exceeded."""
    if len(value) > max_len:
        raise HTTPException(
            status_code=400,
            detail={"reason_codes": [f"{field_name}_too_long"], "max_length": max_len, "actual_length": len(value)},
        )
    return value


ACTION_NAMES = [
    "new_order",
    "cancel",
    "amend",
    "reduce_only",
    "increase_position",
    "close_position",
]

PRODUCT_FAMILIES = [
    "spot",
    "margin",
    "perp_linear",
    "perp_inverse",
    "options",
    "other_derivatives_reserved",
]

CONFIG_CHANGE_WHITELIST = {
    "meta.environment",
    "global_runtime.controls.global_execution_mode_switch",
    "global_runtime.controls.global_operator_mode_switch",
    "control_plane.demo_control.demo_operator_ack_required",
    "control_plane.risk_envelope.risk_policy_switch",
    "control_plane.risk_envelope.risk_policy_profile",
    "learning_state.experiments.approval_required",
}
for pf in PRODUCT_FAMILIES:
    CONFIG_CHANGE_WHITELIST.add(f"product_family_status.{pf}.controls.enabled_switch")
    CONFIG_CHANGE_WHITELIST.add(f"product_family_status.{pf}.controls.visibility_switch")
    CONFIG_CHANGE_WHITELIST.add(f"product_family_status.{pf}.controls.mode_switch")
    for action_name in ACTION_NAMES:
        CONFIG_CHANGE_WHITELIST.add(
            f"control_plane.action_permissions.global.configured_{action_name}_allowed_switch"
        )
        CONFIG_CHANGE_WHITELIST.add(
            f"control_plane.action_permissions.by_product_family.{pf}.configured_{action_name}_allowed_switch"
        )


def _permission_block(configured: bool = False) -> dict[str, Any]:
    block: dict[str, Any] = {}
    for action_name in ACTION_NAMES:
        block[f"configured_{action_name}_allowed_switch"] = configured
        block[f"effective_{action_name}_allowed_state"] = "disabled"
        block[f"effective_{action_name}_reason_codes"] = []
    return block


def deep_set(container: dict[str, Any], path: str, value: Any) -> None:
    pieces = path.split(".")
    current = container
    for piece in pieces[:-1]:
        if piece not in current:
            raise KeyError(f"Path component '{piece}' not found in state (full path: {path})")
        current = current[piece]
    current[pieces[-1]] = value


def build_snapshot_id(state: dict[str, Any]) -> str:
    revision = state["meta"]["state_revision"]
    meta = {
        "revision": revision,
        "global_execution_mode_switch": state["global_runtime"]["controls"]["global_execution_mode_switch"],
        "demo_state_switch": state["control_plane"]["demo_control"]["demo_state_switch"],
        "risk_state": state["control_plane"]["risk_envelope"]["effective_risk_envelope_state"],
        "updated_ts": state["meta"]["snapshot_ts_ms"],
    }
    payload = json.dumps(meta, ensure_ascii=False, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:12]
    return f"snapshot:{revision}:{digest}"


def _compile_global_stage_label(state: dict[str, Any]) -> str:
    controls = state["global_runtime"]["controls"]
    chapter_status = state["chapter_status"]

    if controls["global_execution_mode_switch"] == "live_reserved":
        return "future_live_reserved"
    if (
        chapter_status["K"]["current_phase_ready"] is True
        and chapter_status["K"]["readiness_scope"] == "design_only_gate_closed"
    ):
        return "design_only_gate_closed"
    if (
        chapter_status["J"]["current_phase_ready"] is True
        and chapter_status["J"]["readiness_scope"] == "shadow_closeout"
    ):
        return "shadow_closeout_ready"
    if chapter_status["J"]["chapter_state"] in {"partial", "implemented", "canonical_open"}:
        return "shadow_closeout_partial"
    return "observer_baseline"


def _compile_global_mode_state(state: dict[str, Any]) -> str:
    # Derive from control switch (user intent) rather than fact (static init value).
    # The fact is initialized as "design_only" and never updated by config-change,
    # while the control switch reflects the operator's actual mode selection.
    # 从控制开关（用户意图）派生，而非从 fact（静态初始值）读取。
    control_mode = state["global_runtime"]["controls"]["global_execution_mode_switch"]
    mapping = {
        "disabled": "design_only",
        "observe_only": "observe_only",
        "shadow_only": "shadow_only",
        "demo_reserved": "demo_reserved",
        "live_reserved": "live_reserved",
    }
    return mapping.get(control_mode, "design_only")


def _compile_effective_risk_envelope_state(state: dict[str, Any]) -> EffectiveRiskEnvelopeState:
    policy_switch = state["control_plane"]["risk_envelope"]["risk_policy_switch"]
    health_overall = state["health_telemetry"]["gates"]["health_gates_overall_state"]
    cooldown_state = state["control_plane"]["demo_control"]["demo_cooldown_state"]

    if policy_switch == "manual_blocked":
        return "blocking"
    if health_overall == "failed":
        return "blocking"
    if cooldown_state == "active" and state["control_plane"]["demo_control"]["demo_state_switch"] == "demo_enabled":
        return "blocking"
    if policy_switch == "default_guarded":
        return "configured"
    return "reserved"


def _compile_demo_gate_states(state: dict[str, Any]) -> None:
    demo = state["control_plane"]["demo_control"]
    execution_mode = state["global_runtime"]["controls"]["global_execution_mode_switch"]
    health_overall = state["health_telemetry"]["gates"]["health_gates_overall_state"]
    risk_state = state["control_plane"]["risk_envelope"]["effective_risk_envelope_state"]

    prerequisite_reasons: list[str] = []
    if execution_mode == "live_reserved":
        prereq_state = "blocked"
        prerequisite_reasons.append("live_mode_reserved_only")
    else:
        prereq_state = "passed"

    demo["demo_prerequisites_gate_state"] = prereq_state
    demo["demo_prerequisites_reason_codes"] = prerequisite_reasons

    arm_reasons: list[str] = []
    if prereq_state != "passed":
        arm_state = "blocked"
        arm_reasons.append("prerequisites_not_passed")
    elif execution_mode != "demo_reserved":
        arm_state = "blocked"
        arm_reasons.append("execution_mode_disabled")
    else:
        arm_state = "passed"

    demo["demo_arm_gate_state"] = arm_state
    demo["demo_arm_reason_codes"] = arm_reasons

    enable_reasons: list[str] = []
    if demo["demo_state_switch"] != "armed_but_closed":
        enable_state = "blocked"
        enable_reasons.append("not_armed")
    elif health_overall == "failed":
        enable_state = "blocked"
        enable_reasons.append("health_gate_blocked")
    elif risk_state == "blocking":
        enable_state = "blocked"
        enable_reasons.append("risk_envelope_blocked")
    elif demo["demo_cooldown_state"] == "active" and (demo["demo_cooldown_until_ts_ms"] or 0) > now_ms():
        enable_state = "blocked"
        enable_reasons.append("cooldown_active")
    else:
        enable_state = "passed"

    demo["demo_enable_gate_state"] = enable_state
    demo["demo_enable_reason_codes"] = enable_reasons
    demo["demo_relock_gate_state"] = "passed"
    demo["demo_relock_reason_codes"] = []


def _compile_global_execution_authority_state(state: dict[str, Any]) -> str:
    execution_mode = state["global_runtime"]["controls"]["global_execution_mode_switch"]
    demo_state = state["control_plane"]["demo_control"]["demo_state_switch"]
    health_overall = state["health_telemetry"]["gates"]["health_gates_overall_state"]
    risk_state = state["control_plane"]["risk_envelope"]["effective_risk_envelope_state"]

    if execution_mode == "disabled":
        return "disabled"
    if execution_mode == "live_reserved":
        return "live_blocked"
    if execution_mode == "demo_reserved" and demo_state != "demo_enabled":
        return "demo_blocked"
    if (
        execution_mode == "demo_reserved"
        and demo_state == "demo_enabled"
        and health_overall != "failed"
        and risk_state != "blocking"
    ):
        return "demo_enabled"
    return "demo_blocked"


def _compile_global_capability_state(state: dict[str, Any]) -> str:
    stage = state["global_runtime"]["derived"]["global_stage_label"]
    if stage == "design_only_gate_closed":
        return "shadow_control_ready"
    if stage == "shadow_closeout_ready":
        return "shadow_operational_visibility"
    if stage == "future_live_reserved":
        return "live_candidate_reserved"
    return "minimal_visibility"


def _compile_effective_action_permissions(state: dict[str, Any]) -> None:
    execution_mode = state["global_runtime"]["controls"]["global_execution_mode_switch"]
    demo_state = state["control_plane"]["demo_control"]["demo_state_switch"]
    risk_state = state["control_plane"]["risk_envelope"]["effective_risk_envelope_state"]

    global_block = state["control_plane"]["action_permissions"]["global"]
    for action_name in ACTION_NAMES:
        configured_key = f"configured_{action_name}_allowed_switch"
        effective_key = f"effective_{action_name}_allowed_state"
        reason_key = f"effective_{action_name}_reason_codes"
        reasons: list[str] = []

        if not global_block[configured_key]:
            state_value = "disabled"
            reasons.append("configured_switch_disabled")
        elif execution_mode == "disabled":
            state_value = "blocked"
            reasons.append("global_execution_blocked")
        elif demo_state != "demo_enabled":
            state_value = "blocked"
            reasons.append("demo_not_enabled")
        elif risk_state == "blocking":
            state_value = "blocked"
            reasons.append("risk_scope_blocked")
        else:
            state_value = "allowed"

        global_block[effective_key] = state_value
        global_block[reason_key] = reasons

    for pf in PRODUCT_FAMILIES:
        pf_control = state["product_family_status"][pf]["controls"]
        pf_permission = state["control_plane"]["action_permissions"]["by_product_family"][pf]
        for action_name in ACTION_NAMES:
            configured_key = f"configured_{action_name}_allowed_switch"
            effective_key = f"effective_{action_name}_allowed_state"
            reason_key = f"effective_{action_name}_reason_codes"
            reasons = []

            if not pf_permission[configured_key]:
                state_value = "disabled"
                reasons.append("configured_switch_disabled")
            elif not pf_control["enabled_switch"]:
                state_value = "blocked"
                reasons.append("product_family_disabled")
            elif not pf_control["visibility_switch"]:
                state_value = "blocked"
                reasons.append("product_family_not_visible")
            elif pf_control["mode_switch"] != "shadow_only":
                state_value = "blocked"
                reasons.append("product_family_mode_blocked")
            elif execution_mode == "disabled":
                state_value = "blocked"
                reasons.append("global_execution_blocked")
            elif demo_state != "demo_enabled":
                state_value = "blocked"
                reasons.append("demo_not_enabled")
            elif risk_state == "blocking":
                state_value = "blocked"
                reasons.append("risk_scope_blocked")
            else:
                state_value = "allowed"

            pf_permission[effective_key] = state_value
            pf_permission[reason_key] = reasons


def _compile_product_family_derived(state: dict[str, Any], pf: str) -> None:
    pf_state = state["product_family_status"][pf]
    controls = pf_state["controls"]
    facts = pf_state["facts"]
    global_exec_authority = state["global_runtime"]["derived"]["global_execution_authority_state"]
    effective_any_allowed = False

    if not controls["visibility_switch"]:
        capability_state = "unavailable"
    elif facts["exchange_permission_fact"] == "unavailable" or facts["account_permission_fact"] == "unavailable":
        capability_state = "unavailable"
    elif not controls["enabled_switch"]:
        capability_state = "visible_only"
    elif controls["mode_switch"] == "observe_only":
        capability_state = "visible_only"
    elif (
        controls["mode_switch"] == "shadow_only"
        and state["capability_matrix"]["product_families"][pf]["control_plane_capability_state"] == "implemented"
    ):
        capability_state = "shadow_control_ready"
    elif controls["mode_switch"] == "shadow_only":
        capability_state = "shadow_visible"
    else:
        capability_state = "reserved"

    for action_name in ACTION_NAMES:
        if (
            state["control_plane"]["action_permissions"]["by_product_family"][pf][
                f"effective_{action_name}_allowed_state"
            ]
            == "allowed"
        ):
            effective_any_allowed = True
            break

    if not controls["enabled_switch"]:
        execution_authority_state = "disabled"
    elif global_exec_authority == "disabled":
        execution_authority_state = "disabled"
    elif global_exec_authority != "demo_enabled":
        execution_authority_state = "blocked"
    elif controls["mode_switch"] != "shadow_only":
        execution_authority_state = "blocked"
    elif effective_any_allowed:
        execution_authority_state = "guarded"
    else:
        execution_authority_state = "blocked"

    if not controls["visibility_switch"]:
        summary = "hidden"
    elif not controls["enabled_switch"]:
        summary = "visible_but_disabled"
    elif controls["mode_switch"] == "disabled":
        summary = "visible_but_not_enabled"
    elif capability_state == "shadow_control_ready":
        summary = "shadow_control_ready"
    elif controls["mode_switch"] in {"observe_only", "shadow_only"}:
        summary = "shadow_visible_only"
    else:
        summary = "reserved"

    pf_state["derived"]["capability_state"] = capability_state
    pf_state["derived"]["execution_authority_state"] = execution_authority_state
    pf_state["derived"]["product_family_summary"] = summary


def _compile_for_response(state: dict[str, Any]) -> dict[str, Any]:
    """
    Compile state for building mutator response data (no file write).
    为构建 mutator 响应数据编译状态（不写文件）。

    This handles both the original compile_state and the patched stable_compile_state.
    兼容原始 compile_state 和 patched stable_compile_state。

    Uses _COMPILE_STATE_SIG_CACHE (WeakKeyDictionary keyed by function object) to avoid
    repeated inspect.signature() calls on this high-frequency path (every mutator operation).
    Cache auto-invalidates when compile_state is monkey-patched (e.g. in tests) because the
    old function object becomes unreachable and its entry is automatically removed by GC.
    使用 WeakKeyDictionary 缓存（以函数对象本身为键）避免高频路径重复调用 inspect.signature()；
    compile_state 被替换（如测试 monkeypatch）时旧函数对象被 GC 回收，缓存条目自动消失，
    新函数对象触发重新检测，不存在 id 重用后的错误命中问题。
    """
    fn = compile_state
    has_refresh = _COMPILE_STATE_SIG_CACHE.get(fn)
    if has_refresh is None:
        has_refresh = "refresh_identity" in _inspect.signature(fn).parameters
        _COMPILE_STATE_SIG_CACHE[fn] = has_refresh
    if has_refresh:
        return fn(state, refresh_identity=False)
    return fn(state)


def _do_compile_core(
    state: dict[str, Any],
    *,
    refresh_identity: bool = True,
    include_learning: bool = True,
) -> dict[str, Any]:
    """
    Shared compilation core used by both compile_state() and stable_compile_state().
    将 compile_state 和 stable_compile_state 的共同编译逻辑提取为统一入口，
    通过参数区分差异：refresh_identity 控制是否刷新时间戳，include_learning 控制
    是否计算学习状态派生字段。

    Args:
        state: Deep-copied state dict (caller must deepcopy before calling).
        refresh_identity: If True, update snapshot_ts_ms to now.
        include_learning: If True, compute L-chapter learning derived fields.

    Returns:
        Compiled state dict with all derived fields populated.
    """
    if refresh_identity:
        state["meta"]["snapshot_ts_ms"] = now_ms()

    state["global_runtime"]["derived"]["global_mode_state"] = _compile_global_mode_state(state)
    state["global_runtime"]["derived"]["global_stage_label"] = _compile_global_stage_label(state)
    state["control_plane"]["risk_envelope"]["effective_risk_envelope_state"] = _compile_effective_risk_envelope_state(state)
    _compile_demo_gate_states(state)
    state["global_runtime"]["derived"]["global_execution_authority_state"] = _compile_global_execution_authority_state(state)
    state["global_runtime"]["derived"]["global_capability_state"] = _compile_global_capability_state(state)
    _compile_effective_action_permissions(state)

    for pf in PRODUCT_FAMILIES:
        _compile_product_family_derived(state, pf)

    state["global_runtime"]["derived"]["runtime_still_protected"] = (
        state["global_runtime"]["derived"]["global_execution_authority_state"] != "demo_enabled"
        and state["global_runtime"]["controls"]["global_execution_mode_switch"] != "live_reserved"
    )

    blockers: list[str] = []
    if state["global_runtime"]["controls"]["global_execution_mode_switch"] == "disabled":
        blockers.append("global_execution_blocked")
    if state["control_plane"]["demo_control"]["demo_state_switch"] != "demo_enabled":
        blockers.append("demo_not_enabled")
    if state["control_plane"]["risk_envelope"]["effective_risk_envelope_state"] == "blocking":
        blockers.append("risk_scope_blocked")
    state["global_runtime"]["derived"]["overview_blocker_summary"] = blockers

    state["control_plane"]["execution_control_summary"] = {
        "global_execution_mode_switch_summary": state["global_runtime"]["controls"]["global_execution_mode_switch"],
        "global_operator_mode_switch_summary": state["global_runtime"]["controls"]["global_operator_mode_switch"],
    }
    state["control_plane"]["health_gate_summary"] = {
        "health_gates_overall_state_summary": state["health_telemetry"]["gates"]["health_gates_overall_state"],
        "exchange_timeout_gate_state_summary": state["health_telemetry"]["gates"]["exchange_timeout_gate_state"],
        "ws_disconnect_gate_state_summary": state["health_telemetry"]["gates"]["ws_disconnect_gate_state"],
        "latency_gate_state_summary": state["health_telemetry"]["gates"]["latency_gate_state"],
        "freshness_gate_state_summary": state["health_telemetry"]["gates"]["freshness_gate_state"],
    }

    if include_learning:
        _compile_learning_derived(state)

    state["meta"]["snapshot_id"] = build_snapshot_id(state)
    return state


def _compile_learning_derived(state: dict[str, Any]) -> None:
    """
    Compute L-chapter learning state derived fields from records lists.
    从 records 列表动态计算学习状态摘要统计，确保派生字段始终与底层数据一致。
    """
    ls = state.get("learning_state", {})
    ls_records = ls.get("records", {})

    # 统计活跃假设数（状态为 proposed / under_review / testing）
    # Count active hypotheses (status in proposed / under_review / testing)
    active_hyp = [h for h in ls_records.get("hypotheses", [])
                  if h.get("status") in {"proposed", "under_review", "testing"}]
    ls.setdefault("hypotheses", {})["active_hypothesis_count"] = len(active_hyp)

    # 统计活跃实验数（状态为 proposed / pending_approval / approved / in_progress）
    # Count active experiments (status in proposed / pending_approval / approved / in_progress)
    active_exp = [e for e in ls_records.get("experiments", [])
                  if e.get("status") in {"proposed", "pending_approval", "approved", "in_progress"}]
    ls.setdefault("experiments", {})["active_experiment_count"] = len(active_exp)

    # 更新观察摘要计数 / Update observation summary counts
    obs_summary = ls.setdefault("observation_summary", {})
    obs_summary["recent_lessons_count"] = len(ls_records.get("lessons", []))
    obs_summary["recent_hypothesis_count"] = len(ls_records.get("hypotheses", []))
    obs_summary["recent_experiment_proposal_count"] = len(ls_records.get("experiments", []))

    # 学习进展状态始终为 observe_and_record_only（当前系统 read_only / disabled）
    # Learning progression state always observe_and_record_only while system is read_only
    ls.setdefault("derived", {})["learning_progression_state"] = "observe_and_record_only"

    # 自动学习管线审核包计数 / Auto learning pipeline review queue count
    review_queue = ls_records.get("review_queue", [])
    auto_pipeline = ls.setdefault("auto_pipeline", {})
    auto_pipeline["pending_review_count"] = len(
        [p for p in review_queue if p.get("status") == "pending_review"]
    )


def compile_state(state: dict[str, Any]) -> dict[str, Any]:
    """
    Full state compilation with identity refresh and learning derived fields.
    完整状态编译，刷新 snapshot 身份并计算学习派生字段。

    Uses dirty-flag memoization (B6): if the state has not been mutated since
    the last call AND the input state_revision matches, returns the cached
    result immediately without O(n) list scans.
    使用脏标志缓存（B6）：若自上次调用以来状态未被修改且 state_revision 匹配，
    直接返回缓存结果，避免每次 O(n) 列表扫描。
    """
    global _compile_dirty, _compile_cache
    # Double-check: dirty flag AND state_revision must match to use cache.
    # This prevents cross-contamination when different state dicts are compiled.
    # 双重检查：脏标志 AND state_revision 必须匹配才能使用缓存，
    # 防止不同 state dict 之间的交叉污染。
    incoming_rev = state.get("meta", {}).get("state_revision")
    with _compile_cache_lock:
        cached_rev = _compile_cache.get("meta", {}).get("state_revision") if _compile_cache else None
        if not _compile_dirty and _compile_cache and incoming_rev == cached_rev:
            return copy.deepcopy(_compile_cache)
    # Compile outside the lock to avoid holding it during O(n) computation.
    # 在鎖外編譯，避免在 O(n) 計算期間持有鎖。
    compiled = copy.deepcopy(state)
    result = _do_compile_core(compiled, refresh_identity=True, include_learning=True)
    with _compile_cache_lock:
        _compile_cache = result
        _compile_dirty = False
    return copy.deepcopy(result)
