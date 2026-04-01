from __future__ import annotations

"""
MODULE_NOTE (中文):
  學習記錄 CRUD 模塊。包含觀察/經驗/假設/實驗的錄入，
  以及假設審批、實驗審批、實驗完成等寫操作。
  從 learning_ops.py 拆分而來（learning_ops Wave E 重構）。

  ★ 寫操作通過 _base.STORE / _base.get_latest_snapshot() 間接訪問單例。

MODULE_NOTE (English):
  Learning records CRUD module. Contains observation/lesson/hypothesis/experiment
  recording, plus hypothesis verdict, experiment approval, and experiment completion
  write operations. Extracted from learning_ops.py (learning_ops Wave E refactoring).

  ★ Write operations access singletons indirectly via _base.STORE / _base.get_latest_snapshot().
"""

import logging
from typing import Any

from fastapi import HTTPException

from . import main_legacy as _base
from .auth import AuthenticatedActor, require_scope_and_identity
from .state_compiler import (
    CONFIDENCE_LEVELS,
    EXPERIMENT_APPROVAL_ACTIONS,
    HYPOTHESIS_VERDICT_ACTIONS,
    LESSON_CATEGORIES,
    OBSERVATION_CATEGORIES,
    _MAX_TEXT_LONG,
    _MAX_TEXT_SHORT,
    _compile_for_response,
    _validate_text_length,
    now_ms,
)
from .state_helpers import (
    _assert_revision,
    _bump_revision,
    _check_idempotency,
    _store_idempotent_response,
    _write_audit_fields,
)
from .state_models import RequestEnvelope

logger = logging.getLogger(__name__)


def apply_learning_observation(
    envelope: RequestEnvelope, actor: AuthenticatedActor
) -> tuple[dict[str, Any], str]:
    """
    录入一条观察记录到观察流 / Record an observation to the observation feed.

    payload 必填字段 / Required payload fields:
    - title: str        观察标题 / Observation title
    - detail: str       观察详情 / Observation detail
    - category: str     类别（market/execution/cost/system/strategy/other）
    - confidence_level: str  置信度（fact/inference/hypothesis）

    payload 可选字段 / Optional payload fields:
    - related_hypothesis_id: str  关联假设 ID / Related hypothesis ID
    - tags: list[str]            标签 / Tags
    """
    snapshot, _ = _base.get_latest_snapshot()
    require_scope_and_identity(actor, "learning:write", envelope)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)

    # 验证必填字段 / Validate required fields
    p = envelope.payload
    title = _validate_text_length(str(p.get("title", "")).strip(), "title", _MAX_TEXT_SHORT)
    detail = _validate_text_length(str(p.get("detail", "")).strip(), "detail", _MAX_TEXT_LONG)
    category = str(p.get("category", "")).strip()
    confidence = str(p.get("confidence_level", "")).strip()
    if not title or not detail:
        raise HTTPException(status_code=400, detail={"reason_codes": ["missing_title_or_detail"]})
    if category not in OBSERVATION_CATEGORIES:
        raise HTTPException(status_code=400, detail={"reason_codes": ["invalid_observation_category"]})
    if confidence not in CONFIDENCE_LEVELS:
        raise HTTPException(status_code=400, detail={"reason_codes": ["invalid_confidence_level"]})

    ts = now_ms()
    observation_id = f"obs:{ts}"

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        # 构建观察记录 / Build observation record
        record = {
            "observation_id": observation_id,
            "recorded_ts_ms": ts,
            "recorded_by": actor.actor_id,
            "source": "operator_input",
            "category": category,
            "confidence_level": confidence,
            "title": title,
            "detail": detail,
            "related_hypothesis_id": p.get("related_hypothesis_id"),
            "tags": list(p.get("tags", [])),
        }
        # 确保 observations 列表存在（兼容旧快照）
        # Ensure observations list exists (backward-compatible with old state files)
        ls_records = state["learning_state"].setdefault("records", {})
        ls_records.setdefault("observations", []).append(record)

        # 更新最后观察时间 / Update last observation timestamp
        state["learning_state"]["observation_summary"]["last_observation_ts_ms"] = ts

        audit_ref = _write_audit_fields(
            state, action_type="learning_observation", operator_id=actor.actor_id,
            request_id=envelope.request_id, result="success", reason_codes=[],
            is_control_action=False,
        )
        _bump_revision(state)
        compiled = _compile_for_response(state)
        response = {
            "audit_ref": audit_ref,
            "data": {"accepted": True, "observation_id": observation_id, "record_count_delta": 1},
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        return compiled

    final_state = _base.STORE.mutate(mutator)
    return {
        "audit_ref": final_state["audit_context"]["last_write_action_audit_ref"],
        "data": {"accepted": True, "observation_id": observation_id, "record_count_delta": 1},
        "snapshot": final_state,
    }, "success"


def apply_learning_lesson(
    envelope: RequestEnvelope, actor: AuthenticatedActor
) -> tuple[dict[str, Any], str]:
    """
    录入一条经验教训到经验记忆库 / Record a lesson to the lessons memory.

    payload 必填字段 / Required payload fields:
    - title: str        经验标题 / Lesson title
    - detail: str       经验详情 / Lesson detail
    - category: str     类别（market_pattern/cost_insight/execution_quality/strategy/system/other）
    - confidence_level: str  置信度（fact/inference/hypothesis）

    payload 可选字段 / Optional payload fields:
    - source_observation_ids: list[str]  来源观察 ID 列表 / Source observation IDs
    - actionable: bool                   是否可操作 / Whether actionable
    - related_hypothesis_ids: list[str]  关联假设 ID 列表 / Related hypothesis IDs
    - tags: list[str]                    标签 / Tags
    """
    snapshot, _ = _base.get_latest_snapshot()
    require_scope_and_identity(actor, "learning:write", envelope)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)

    p = envelope.payload
    title = _validate_text_length(str(p.get("title", "")).strip(), "title", _MAX_TEXT_SHORT)
    detail = _validate_text_length(str(p.get("detail", "")).strip(), "detail", _MAX_TEXT_LONG)
    category = str(p.get("category", "")).strip()
    confidence = str(p.get("confidence_level", "")).strip()
    if not title or not detail:
        raise HTTPException(status_code=400, detail={"reason_codes": ["missing_title_or_detail"]})
    if category not in LESSON_CATEGORIES:
        raise HTTPException(status_code=400, detail={"reason_codes": ["invalid_lesson_category"]})
    if confidence not in CONFIDENCE_LEVELS:
        raise HTTPException(status_code=400, detail={"reason_codes": ["invalid_confidence_level"]})

    ts = now_ms()
    lesson_id = f"lesson:{ts}"

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        record = {
            "lesson_id": lesson_id,
            "recorded_ts_ms": ts,
            "recorded_by": actor.actor_id,
            "source_observation_ids": list(p.get("source_observation_ids", [])),
            "confidence_level": confidence,
            "category": category,
            "title": title,
            "detail": detail,
            "actionable": bool(p.get("actionable", False)),
            "related_hypothesis_ids": list(p.get("related_hypothesis_ids", [])),
            "tags": list(p.get("tags", [])),
        }
        ls_records = state["learning_state"].setdefault("records", {})
        ls_records.setdefault("lessons", []).append(record)

        # 更新记忆最后更新时间 / Update memory last update timestamp
        state["learning_state"]["memory"]["last_memory_update_ts_ms"] = ts

        audit_ref = _write_audit_fields(
            state, action_type="learning_lesson", operator_id=actor.actor_id,
            request_id=envelope.request_id, result="success", reason_codes=[],
            is_control_action=False,
        )
        _bump_revision(state)
        compiled = _compile_for_response(state)
        response = {
            "audit_ref": audit_ref,
            "data": {"accepted": True, "lesson_id": lesson_id, "record_count_delta": 1},
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        return compiled

    final_state = _base.STORE.mutate(mutator)
    return {
        "audit_ref": final_state["audit_context"]["last_write_action_audit_ref"],
        "data": {"accepted": True, "lesson_id": lesson_id, "record_count_delta": 1},
        "snapshot": final_state,
    }, "success"


def apply_learning_hypothesis(
    envelope: RequestEnvelope, actor: AuthenticatedActor
) -> tuple[dict[str, Any], str]:
    """
    提出一条假设到假设队列 / Propose a hypothesis to the hypothesis queue.

    原则 8：假设的 confidence_level 始终强制为 "hypothesis"，不由调用方指定。
    Principle 8: hypothesis confidence_level is always forced to "hypothesis", not caller-specified.

    payload 必填字段 / Required payload fields:
    - title: str                假设标题 / Hypothesis title
    - description: str          假设描述 / Hypothesis description
    - testable_prediction: str  可检验的预测 / Testable prediction

    payload 可选字段 / Optional payload fields:
    - supporting_observation_ids: list[str]  支持该假设的观察 ID / Supporting observation IDs
    - supporting_lesson_ids: list[str]       支持该假设的经验 ID / Supporting lesson IDs
    - tags: list[str]                        标签 / Tags
    """
    snapshot, _ = _base.get_latest_snapshot()
    require_scope_and_identity(actor, "learning:write", envelope)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)

    p = envelope.payload
    title = _validate_text_length(str(p.get("title", "")).strip(), "title", _MAX_TEXT_SHORT)
    description = _validate_text_length(str(p.get("description", "")).strip(), "description", _MAX_TEXT_LONG)
    testable_prediction = _validate_text_length(str(p.get("testable_prediction", "")).strip(), "testable_prediction", _MAX_TEXT_LONG)
    if not title or not description or not testable_prediction:
        raise HTTPException(status_code=400, detail={"reason_codes": ["missing_required_hypothesis_fields"]})

    ts = now_ms()
    hypothesis_id = f"hyp:{ts}"

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        record = {
            "hypothesis_id": hypothesis_id,
            "recorded_ts_ms": ts,
            "recorded_by": actor.actor_id,
            # 原则 8：强制为 hypothesis / Principle 8: forced to hypothesis
            "status": "proposed",
            "confidence_level": "hypothesis",
            "title": title,
            "description": description,
            "testable_prediction": testable_prediction,
            "supporting_observation_ids": list(p.get("supporting_observation_ids", [])),
            "supporting_lesson_ids": list(p.get("supporting_lesson_ids", [])),
            "related_experiment_id": None,
            "operator_verdict": None,
            "operator_verdict_ts_ms": None,
            "operator_verdict_reason": None,
            "tags": list(p.get("tags", [])),
        }
        state["learning_state"]["records"]["hypotheses"].append(record)
        state["learning_state"]["hypotheses"]["last_hypothesis_ts_ms"] = ts

        audit_ref = _write_audit_fields(
            state, action_type="learning_hypothesis", operator_id=actor.actor_id,
            request_id=envelope.request_id, result="success", reason_codes=[],
            is_control_action=False,
        )
        _bump_revision(state)
        compiled = _compile_for_response(state)
        response = {
            "audit_ref": audit_ref,
            "data": {"accepted": True, "hypothesis_id": hypothesis_id, "status": "proposed", "record_count_delta": 1},
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        return compiled

    final_state = _base.STORE.mutate(mutator)
    return {
        "audit_ref": final_state["audit_context"]["last_write_action_audit_ref"],
        "data": {"accepted": True, "hypothesis_id": hypothesis_id, "status": "proposed", "record_count_delta": 1},
        "snapshot": final_state,
    }, "success"


def apply_learning_experiment(
    envelope: RequestEnvelope, actor: AuthenticatedActor
) -> tuple[dict[str, Any], str]:
    """
    提出一项实验到实验队列 / Propose an experiment to the experiment queue.

    如果当前 learning_state.experiments.approval_required=True，
    实验状态初始化为 pending_approval；否则直接 approved。
    If approval_required=True, experiment status starts as pending_approval; otherwise approved.

    payload 必填字段 / Required payload fields:
    - hypothesis_id: str    关联假设 ID / Linked hypothesis ID (must exist)
    - title: str            实验标题 / Experiment title
    - description: str      实验描述 / Experiment description
    - method: str           实验方法 / Experiment method
    - success_criteria: str 成功标准 / Success criteria

    payload 可选字段 / Optional payload fields:
    - risk_assessment: str  风险评估 / Risk assessment
    - tags: list[str]       标签 / Tags
    """
    snapshot, _ = _base.get_latest_snapshot()
    require_scope_and_identity(actor, "learning:write", envelope)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)

    p = envelope.payload
    hypothesis_id = str(p.get("hypothesis_id", "")).strip()
    title = _validate_text_length(str(p.get("title", "")).strip(), "title", _MAX_TEXT_SHORT)
    description = _validate_text_length(str(p.get("description", "")).strip(), "description", _MAX_TEXT_LONG)
    method = _validate_text_length(str(p.get("method", "")).strip(), "method", _MAX_TEXT_LONG)
    success_criteria = _validate_text_length(str(p.get("success_criteria", "")).strip(), "success_criteria", _MAX_TEXT_LONG)
    if not hypothesis_id or not title or not description or not method or not success_criteria:
        raise HTTPException(status_code=400, detail={"reason_codes": ["missing_required_experiment_fields"]})

    # 验证关联假设存在 / Verify linked hypothesis exists
    hyp_list = snapshot["learning_state"]["records"]["hypotheses"]
    if not any(h.get("hypothesis_id") == hypothesis_id for h in hyp_list):
        raise HTTPException(status_code=400, detail={"reason_codes": ["hypothesis_not_found"]})

    # 快照当前审批要求 / Snapshot current approval requirement
    approval_required = snapshot["learning_state"]["experiments"]["approval_required"]
    initial_status = "pending_approval" if approval_required else "approved"

    ts = now_ms()
    experiment_id = f"exp:{ts}"

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        record = {
            "experiment_id": experiment_id,
            "recorded_ts_ms": ts,
            "recorded_by": actor.actor_id,
            "status": initial_status,
            "hypothesis_id": hypothesis_id,
            "title": title,
            "description": description,
            "method": method,
            "success_criteria": success_criteria,
            "risk_assessment": str(p.get("risk_assessment", "")),
            "approval_required": approval_required,
            "operator_approval": None,
            "operator_approval_ts_ms": None,
            "operator_approval_reason": None,
            "result_summary": None,
            "result_confidence_level": None,
            "completed_ts_ms": None,
            "tags": list(p.get("tags", [])),
        }
        state["learning_state"]["records"]["experiments"].append(record)
        state["learning_state"]["experiments"]["last_experiment_proposal_ts_ms"] = ts

        audit_ref = _write_audit_fields(
            state, action_type="learning_experiment", operator_id=actor.actor_id,
            request_id=envelope.request_id, result="success", reason_codes=[],
            is_control_action=False,
        )
        _bump_revision(state)
        compiled = _compile_for_response(state)
        response = {
            "audit_ref": audit_ref,
            "data": {
                "accepted": True, "experiment_id": experiment_id,
                "status": initial_status, "approval_required": approval_required,
                "record_count_delta": 1,
            },
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        return compiled

    final_state = _base.STORE.mutate(mutator)
    return {
        "audit_ref": final_state["audit_context"]["last_write_action_audit_ref"],
        "data": {
            "accepted": True, "experiment_id": experiment_id,
            "status": initial_status, "approval_required": approval_required,
            "record_count_delta": 1,
        },
        "snapshot": final_state,
    }, "success"


def apply_hypothesis_verdict(
    envelope: RequestEnvelope, actor: AuthenticatedActor, hypothesis_id: str
) -> tuple[dict[str, Any], str]:
    """
    Operator 对假设做出审批判定 / Operator renders verdict on a hypothesis.

    payload 必填字段 / Required payload fields:
    - verdict: str  判定结果（approved / rejected / archived）
    - reason: str   判定理由 / Verdict reason (optional but recommended)

    状态转换 / Status transitions:
    - proposed → approved / rejected / archived
    - under_review → approved / rejected / archived
    """
    snapshot, _ = _base.get_latest_snapshot()
    require_scope_and_identity(actor, "learning:manage", envelope)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)

    p = envelope.payload
    verdict = str(p.get("verdict", "")).strip()
    if verdict not in HYPOTHESIS_VERDICT_ACTIONS:
        raise HTTPException(status_code=400, detail={"reason_codes": ["invalid_hypothesis_verdict"]})

    # 查找假设 / Find the hypothesis
    hyp_list = snapshot["learning_state"]["records"]["hypotheses"]
    target = None
    target_idx = -1
    for idx, h in enumerate(hyp_list):
        if h.get("hypothesis_id") == hypothesis_id:
            target = h
            target_idx = idx
            break
    if target is None:
        raise HTTPException(status_code=404, detail={"reason_codes": ["hypothesis_not_found"]})

    ts = now_ms()
    # 映射 verdict → 新状态 / Map verdict → new status
    status_map = {"approved": "validated", "rejected": "invalidated", "archived": "archived"}
    new_status = status_map[verdict]

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        hyp = state["learning_state"]["records"]["hypotheses"][target_idx]
        hyp["status"] = new_status
        hyp["operator_verdict"] = verdict
        hyp["operator_verdict_ts_ms"] = ts
        hyp["operator_verdict_reason"] = str(p.get("reason", ""))

        audit_ref = _write_audit_fields(
            state, action_type="hypothesis_verdict", operator_id=actor.actor_id,
            request_id=envelope.request_id, result="success", reason_codes=[],
            is_control_action=False,
        )
        _bump_revision(state)
        compiled = _compile_for_response(state)
        response = {
            "audit_ref": audit_ref,
            "data": {"hypothesis_id": hypothesis_id, "new_status": new_status, "operator_verdict": verdict},
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        return compiled

    final_state = _base.STORE.mutate(mutator)
    return {
        "audit_ref": final_state["audit_context"]["last_write_action_audit_ref"],
        "data": {"hypothesis_id": hypothesis_id, "new_status": new_status, "operator_verdict": verdict},
        "snapshot": final_state,
    }, "success"


def apply_experiment_approval(
    envelope: RequestEnvelope, actor: AuthenticatedActor, experiment_id: str
) -> tuple[dict[str, Any], str]:
    """
    Operator 审批或拒绝实验 / Operator approves or rejects an experiment.

    仅对 pending_approval 状态的实验有效。
    Only valid for experiments in pending_approval status.

    payload 必填字段 / Required payload fields:
    - action: str   审批动作（approved / rejected）
    - reason: str   理由 / Reason (optional but recommended)
    """
    snapshot, _ = _base.get_latest_snapshot()
    require_scope_and_identity(actor, "learning:manage", envelope)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)

    p = envelope.payload
    action = str(p.get("action", "")).strip()
    if action not in EXPERIMENT_APPROVAL_ACTIONS:
        raise HTTPException(status_code=400, detail={"reason_codes": ["invalid_experiment_approval_action"]})

    # 查找实验 / Find the experiment
    exp_list = snapshot["learning_state"]["records"]["experiments"]
    target_idx = -1
    for idx, e in enumerate(exp_list):
        if e.get("experiment_id") == experiment_id:
            if e.get("status") != "pending_approval":
                raise HTTPException(status_code=400, detail={"reason_codes": ["experiment_not_pending_approval"]})
            target_idx = idx
            break
    if target_idx == -1:
        raise HTTPException(status_code=404, detail={"reason_codes": ["experiment_not_found"]})

    ts = now_ms()

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        exp = state["learning_state"]["records"]["experiments"][target_idx]
        exp["status"] = action  # "approved" or "rejected"
        exp["operator_approval"] = action
        exp["operator_approval_ts_ms"] = ts
        exp["operator_approval_reason"] = str(p.get("reason", ""))

        audit_ref = _write_audit_fields(
            state, action_type="experiment_approval", operator_id=actor.actor_id,
            request_id=envelope.request_id, result="success", reason_codes=[],
            is_control_action=False,
        )
        _bump_revision(state)
        compiled = _compile_for_response(state)
        response = {
            "audit_ref": audit_ref,
            "data": {"experiment_id": experiment_id, "new_status": action, "operator_approval": action},
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        return compiled

    final_state = _base.STORE.mutate(mutator)
    return {
        "audit_ref": final_state["audit_context"]["last_write_action_audit_ref"],
        "data": {"experiment_id": experiment_id, "new_status": action, "operator_approval": action},
        "snapshot": final_state,
    }, "success"


def apply_experiment_completion(
    envelope: RequestEnvelope, actor: AuthenticatedActor, experiment_id: str
) -> tuple[dict[str, Any], str]:
    """
    标记实验完成并录入结论 / Mark an experiment as completed and record conclusion.

    仅对 approved 或 in_progress 状态的实验有效。
    Only valid for experiments in approved or in_progress status.

    payload 必填字段 / Required payload fields:
    - result_summary: str           实验结论摘要 / Experiment conclusion summary
    - result_confidence_level: str  结论置信度（fact/inference/hypothesis）
    """
    snapshot, _ = _base.get_latest_snapshot()
    require_scope_and_identity(actor, "learning:manage", envelope)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)

    p = envelope.payload
    result_summary = str(p.get("result_summary", "")).strip()
    result_confidence = str(p.get("result_confidence_level", "")).strip()
    if not result_summary:
        raise HTTPException(status_code=400, detail={"reason_codes": ["missing_result_summary"]})
    if result_confidence not in CONFIDENCE_LEVELS:
        raise HTTPException(status_code=400, detail={"reason_codes": ["invalid_confidence_level"]})

    # 查找实验 / Find the experiment
    exp_list = snapshot["learning_state"]["records"]["experiments"]
    target_idx = -1
    for idx, e in enumerate(exp_list):
        if e.get("experiment_id") == experiment_id:
            if e.get("status") not in {"approved", "in_progress"}:
                raise HTTPException(status_code=400, detail={"reason_codes": ["experiment_not_completable"]})
            target_idx = idx
            break
    if target_idx == -1:
        raise HTTPException(status_code=404, detail={"reason_codes": ["experiment_not_found"]})

    ts = now_ms()

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        exp = state["learning_state"]["records"]["experiments"][target_idx]
        exp["status"] = "completed"
        exp["result_summary"] = result_summary
        exp["result_confidence_level"] = result_confidence
        exp["completed_ts_ms"] = ts

        audit_ref = _write_audit_fields(
            state, action_type="experiment_completion", operator_id=actor.actor_id,
            request_id=envelope.request_id, result="success", reason_codes=[],
            is_control_action=False,
        )
        _bump_revision(state)
        compiled = _compile_for_response(state)
        response = {
            "audit_ref": audit_ref,
            "data": {
                "experiment_id": experiment_id, "new_status": "completed",
                "result_summary": result_summary, "result_confidence_level": result_confidence,
            },
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        return compiled

    final_state = _base.STORE.mutate(mutator)
    return {
        "audit_ref": final_state["audit_context"]["last_write_action_audit_ref"],
        "data": {
            "experiment_id": experiment_id, "new_status": "completed",
            "result_summary": result_summary, "result_confidence_level": result_confidence,
        },
        "snapshot": final_state,
    }, "success"
