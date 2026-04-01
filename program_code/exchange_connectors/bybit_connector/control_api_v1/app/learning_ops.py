from __future__ import annotations

"""
MODULE_NOTE (中文):
  學習系統操作模塊。包含觀察/經驗/假設/實驗的錄入、審批、完成，
  自動學習管線（觀察掃描/經驗提取/假設提議），審核隊列決策，
  以及學習系統只讀查詢構建器。從 main_legacy.py 拆分而來（Wave C 重構）。

  ★ 寫操作通過 _base.STORE / _base.get_latest_snapshot() 間接訪問單例。

MODULE_NOTE (English):
  Learning system operations module. Contains observation/lesson/hypothesis/experiment
  recording, approval, completion; auto learning pipeline (observation scan / lesson
  extraction / hypothesis proposal); review queue decisions; and learning system
  read-only query builders. Extracted from main_legacy.py (Wave C refactoring).

  ★ Write operations access singletons indirectly via _base.STORE / _base.get_latest_snapshot().
"""

import copy
import hashlib
import logging
import warnings
from typing import Any

from fastapi import HTTPException

from . import main_legacy as _base
from .auth import AuthenticatedActor, require_scope, verify_operator_identity
from .state_compiler import (
    AUTO_SCAN_TYPES,
    CONFIDENCE_LEVELS,
    EXPERIMENT_APPROVAL_ACTIONS,
    HYPOTHESIS_VERDICT_ACTIONS,
    LESSON_CATEGORIES,
    OBSERVATION_CATEGORIES,
    REVIEW_DECISION_ACTIONS,
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

# 每次最多返回多少条历史记录 / Max entries returned per call
# (shared with pnl_ops; duplicated here for independence)
_MAX_RECENT_ENTRIES: int = 20


# ═══════════════════════════════════════════════════════════════════════════════
# L 章：学习系统逻辑函数 / L-Chapter: Learning System Logic Functions
#
# 五大模块的写入 / 审批 / 查询逻辑。
# 所有写操作遵循标准流程：scope → snapshot → identity → idempotency → revision → mutate。
#
# Write / approve / query logic for the five learning modules.
# All write operations follow the standard flow:
# scope → snapshot → identity → idempotency → revision → mutate.
# ═══════════════════════════════════════════════════════════════════════════════



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
    require_scope(actor, "learning:write")
    snapshot, _ = _base.get_latest_snapshot()
    verify_operator_identity(envelope, actor)
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
    require_scope(actor, "learning:write")
    snapshot, _ = _base.get_latest_snapshot()
    verify_operator_identity(envelope, actor)
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
    require_scope(actor, "learning:write")
    snapshot, _ = _base.get_latest_snapshot()
    verify_operator_identity(envelope, actor)
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
    require_scope(actor, "learning:write")
    snapshot, _ = _base.get_latest_snapshot()
    verify_operator_identity(envelope, actor)
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
    require_scope(actor, "learning:manage")
    snapshot, _ = _base.get_latest_snapshot()
    verify_operator_identity(envelope, actor)
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
    require_scope(actor, "learning:manage")
    snapshot, _ = _base.get_latest_snapshot()
    verify_operator_identity(envelope, actor)
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
    require_scope(actor, "learning:manage")
    snapshot, _ = _base.get_latest_snapshot()
    verify_operator_identity(envelope, actor)
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


# ═══════════════════════════════════════════════════════════════════════════════
# L 章自动学习管线 / L-Chapter Auto Learning Pipeline
#
# 核心概念：审核包 (Review Packet)
# 系统自动扫描运行状态生成发现 → 打包成简单易懂的审核包 → Operator 审批
# 灵感来源：I8 Manual Approval Packet，但面向非金融专业 Operator 大幅简化。
#
# Core concept: Review Packet
# System auto-scans runtime state → packages findings into simple review packets → Operator decides
# Inspired by I8 Manual Approval Packet, radically simplified for non-financial-expert Operator.
#
# 原则 7 保证：自动生成只创建审核包，不自动创建正式记录。
# Principle 7 guarantee: auto-generation only creates review packets, never creates actual records.
# ═══════════════════════════════════════════════════════════════════════════════



def _content_hash(text: str) -> str:
    """生成内容指纹，用于审核包去重 / Generate content fingerprint for deduplication."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _build_review_packet(
    *,
    packet_type: str,
    what_happened: str,
    why_it_matters: str,
    confidence_level: str,
    target_collection: str,
    record_data: dict[str, Any],
    ai_recommended: bool = True,
    ai_tier: str = "light",
    ai_question: str = "",
    ai_context: dict[str, Any] | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """
    构建标准审核包 / Build a standard review packet.

    每个审核包包含：
    1. 简要说明 (what_happened) — 大白话，无金融术语
    2. 为什么重要 (why_it_matters) — 后果分析，通俗易懂
    3. 你的选择 (options) — 每个选项附带后果说明
    4. 置信度标签 (confidence_level) — 事实/推断/假设
    5. AI 咨询建议 — 推荐层级 + 预估成本 + 预生成问题

    Each packet contains:
    1. what_happened — plain language, no jargon
    2. why_it_matters — consequence analysis in simple terms
    3. options — each option with consequence description
    4. confidence_level — fact / inference / hypothesis
    5. AI consultation — recommended tier + estimated cost + pre-built question
    """
    ts = now_ms()
    packet_id = f"rpkt:{ts}"

    # 按类型设定固定后果说明 / Fixed consequence text per packet type
    # 用大白话让非金融专业的 Operator 一眼就能理解每个选择的结果
    consequence_map = {
        "auto_observation": {
            "approve": "记录为正式观察，系统会记住这个发现并用于后续学习 / Record as observation, system will remember this for future learning",
            "reject": "丢弃这个发现，系统不会记住它 / Discard, system will not remember this",
            "defer": "暂不处理，下次审核时再看 / Skip for now, review later",
        },
        "auto_lesson": {
            "approve": "记录为正式经验，系统会参考这条经验来改进判断 / Record as lesson, system will use this to improve judgment",
            "reject": "丢弃这条经验总结，不纳入系统记忆 / Discard, not added to system memory",
            "defer": "暂不处理，下次审核时再看 / Skip for now, review later",
        },
        "auto_hypothesis": {
            "approve": "正式提出假设，系统会追踪并寻找验证机会 / Formally propose hypothesis, system will track and seek validation",
            "reject": "丢弃这个假设，系统不会追踪它 / Discard, system will not track this",
            "defer": "暂不处理，下次审核时再看 / Skip for now, review later",
        },
    }
    consequences = consequence_map.get(packet_type, consequence_map["auto_observation"])

    # AI 咨询成本估算（参考 H2 query_budget 定义）
    # AI consultation cost estimate (referencing H2 query_budget definitions)
    cost_map = {"light": 0.02, "standard": 0.05, "none": 0.0}
    estimated_cost = cost_map.get(ai_tier, 0.02)

    content_text = f"{packet_type}:{record_data.get('title', '')}:{record_data.get('category', '')}"

    return {
        "packet_id": packet_id,
        "packet_type": packet_type,
        "created_ts_ms": ts,
        "status": "pending_review",
        "source": "system_auto",
        "_content_hash": _content_hash(content_text),
        # ── 简要说明 / What Happened ──
        "what_happened": what_happened,
        # ── 为什么重要 / Why It Matters ──
        "why_it_matters": why_it_matters,
        # ── 你的选择 / Your Options ──
        "options": {
            "approve": {"label": "批准 / Approve", "consequence": consequences["approve"]},
            "reject": {"label": "拒绝 / Reject", "consequence": consequences["reject"]},
            "defer": {"label": "搁置 / Defer", "consequence": consequences["defer"]},
        },
        # ── 置信度标签 / Confidence Tag (原则 8 / Principle 8) ──
        "confidence_level": confidence_level,
        # ── AI 咨询建议 / AI Consultation Suggestion ──
        "ai_consultation": {
            "recommended": ai_recommended,
            "recommended_tier": ai_tier,
            "estimated_cost_usd": estimated_cost,
            "pre_built_question": ai_question,
            "question_context": ai_context or {},
        },
        # ── 候选记录 / Candidate record (批准后创建) ──
        "candidate_record": {
            "target_collection": target_collection,
            "record_data": record_data,
        },
        # ── 审核追踪 / Review audit trail ──
        "decided_by": None,
        "decided_ts_ms": None,
        "decision": None,
        "decision_reason": None,
        "ai_consultation_result": None,
        "ai_consultation_cost_usd": None,
        "tags": tags or [],
    }


def _build_ai_question_for_observation(title: str, detail: str, category: str) -> str:
    """
    为自动观察构建 AI 咨询问题 / Build AI question for auto-observation.

    参考 I 章紧凑 JSON 模式，生成简洁有效的问题。
    Inspired by I-chapter compact JSON pattern, generates concise effective questions.
    """
    return (
        f"系统自动观察到以下情况：{title}。"
        f"详情：{detail}。类别：{category}。"
        f"请用简单的语言评估："
        f"1）这个观察是否值得记录？"
        f"2）置信度应该是「事实」还是「推断」？"
        f"3）是否有需要注意的关联因素？"
    )


def _build_ai_question_for_lesson(title: str, detail: str, obs_count: int) -> str:
    """为自动经验构建 AI 咨询问题 / Build AI question for auto-lesson."""
    return (
        f"系统从 {obs_count} 条相关观察中总结出一条可能的经验：{title}。"
        f"详情：{detail}。"
        f"请用简单的语言评估："
        f"1）这个经验总结是否准确合理？"
        f"2）对未来的系统运行有什么指导意义？"
        f"3）是否需要更多观察来确认？"
    )


def _build_ai_question_for_hypothesis(title: str, prediction: str) -> str:
    """为自动假设构建 AI 咨询问题 / Build AI question for auto-hypothesis."""
    return (
        f"系统基于已有经验提出一个假设：{title}。"
        f"可检验预测：{prediction}。"
        f"请用简单的语言评估："
        f"1）这个假设是否有道理？"
        f"2）如果假设成立，会有什么实际影响？"
        f"3）建议用什么方法来验证这个假设？"
    )


# ── 自动观察扫描 / Auto Observation Scanner ──────────────────────────────────




def generate_auto_observations(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """
    扫描系统运行状态，自动生成观察审核包 / Scan system runtime state, generate observation review packets.

    扫描来源 / Scan sources:
    - health_telemetry: 健康门控、延迟、超时 / Health gates, latency, timeout
    - business_metrics: 成本趋势、PnL 变化 / Cost trends, PnL changes
    - learning_state: 观察模式、空闲检测 / Observation patterns, idle detection

    每条规则输出一个审核包，用大白话描述发现和后果。
    Each rule outputs a review packet in plain language describing finding and consequences.
    """
    packets: list[dict[str, Any]] = []
    health = snapshot.get("health_telemetry", {})
    gates = health.get("gates", {})
    daily = snapshot.get("business_metrics", {}).get("daily", {})
    ls = snapshot.get("learning_state", {})
    ls_records = ls.get("records", {})
    global_rt = snapshot.get("global_runtime", {})

    # ── 规则 1：健康门控失败 / Rule 1: Health gate failure ──
    overall_health = gates.get("health_gates_overall_state", "passed")
    if overall_health != "passed":
        failed_gates = [
            k.replace("_gate_state", "").replace("_", " ")
            for k, v in gates.items()
            if k.endswith("_gate_state") and v != "passed" and k != "health_gates_overall_state"
        ]
        failed_str = "、".join(failed_gates) if failed_gates else "未知项"
        packets.append(_build_review_packet(
            packet_type="auto_observation",
            what_happened=f"系统健康检查未通过：{failed_str} 未达标 / Health check failed: {failed_str}",
            why_it_matters=(
                "系统不健康时，AI 的观察和判断质量可能下降。"
                "按照原则 5，应先保证系统健康再做其他判断。"
                " / When system is unhealthy, AI quality may degrade. Principle 5: system health first."
            ),
            confidence_level="fact",
            target_collection="observations",
            record_data={
                "title": f"系统健康检查未通过：{failed_str}",
                "detail": f"健康门控整体状态 {overall_health}，未通过项：{failed_str}",
                "category": "system",
                "confidence_level": "fact",
                "tags": ["auto_generated", "health"],
            },
            ai_recommended=False,
            ai_tier="none",
            ai_question="",
            tags=["health", "auto_generated"],
        ))

    # ── 规则 2：AI 成本偏高 / Rule 2: AI cost elevated ──
    ai_cost = float(daily.get("ai_api_cost", 0.0))
    if ai_cost > 0.5:
        packets.append(_build_review_packet(
            packet_type="auto_observation",
            what_happened=f"今日 AI 调用成本已达 ${ai_cost:.2f} / Today's AI cost reached ${ai_cost:.2f}",
            why_it_matters=(
                "AI 成本是净利润的直接扣除项。成本过高会侵蚀收益。"
                "应关注是否有不必要的 AI 调用。"
                " / AI cost directly reduces net profit. Monitor for unnecessary calls."
            ),
            confidence_level="fact",
            target_collection="observations",
            record_data={
                "title": f"AI 调用成本偏高：${ai_cost:.2f}",
                "detail": f"今日 AI API 调用累计成本 ${ai_cost:.2f}，超过 $0.50 阈值",
                "category": "cost",
                "confidence_level": "fact",
                "tags": ["auto_generated", "cost", "ai_cost"],
            },
            ai_recommended=True,
            ai_tier="light",
            ai_question=_build_ai_question_for_observation(
                f"AI 调用成本偏高：${ai_cost:.2f}",
                f"今日 AI API 调用累计成本 ${ai_cost:.2f}，超过 $0.50 阈值",
                "cost",
            ),
            ai_context={"metric": "ai_api_cost", "value": ai_cost, "threshold": 0.5},
            tags=["cost", "auto_generated"],
        ))

    # ── 规则 3：数据新鲜度下降 / Rule 3: Data freshness degraded ──
    freshness = global_rt.get("facts", {}).get("runtime_data_freshness_state", "fresh")
    if freshness != "fresh":
        packets.append(_build_review_packet(
            packet_type="auto_observation",
            what_happened=f"数据新鲜度状态异常：{freshness} / Data freshness degraded: {freshness}",
            why_it_matters=(
                "数据不新鲜意味着系统看到的市场信息可能是过时的。"
                "在此状态下做出的任何判断都不够可靠。"
                " / Stale data means market info may be outdated. Judgments become unreliable."
            ),
            confidence_level="fact",
            target_collection="observations",
            record_data={
                "title": f"数据新鲜度异常：{freshness}",
                "detail": f"runtime_data_freshness_state = {freshness}，非 fresh 状态",
                "category": "system",
                "confidence_level": "fact",
                "tags": ["auto_generated", "freshness"],
            },
            ai_recommended=False,
            ai_tier="none",
            ai_question="",
            tags=["freshness", "auto_generated"],
        ))

    # ── 规则 4：PnL 显著变化 / Rule 4: Significant PnL change ──
    net_pnl = float(daily.get("net_operating_pnl", 0.0))
    if abs(net_pnl) > 100.0:
        direction = "盈利" if net_pnl > 0 else "亏损"
        direction_en = "profit" if net_pnl > 0 else "loss"
        packets.append(_build_review_packet(
            packet_type="auto_observation",
            what_happened=f"今日净经营 PnL 显著变化：{direction} ${abs(net_pnl):.2f} / Net PnL significant: {direction_en} ${abs(net_pnl):.2f}",
            why_it_matters=(
                f"净 PnL {direction} ${abs(net_pnl):.2f} 超过 $100 的关注阈值。"
                "建议记录并分析原因，以便优化策略。"
                f" / Net PnL {direction_en} ${abs(net_pnl):.2f} exceeds $100 attention threshold."
            ),
            confidence_level="fact",
            target_collection="observations",
            record_data={
                "title": f"净 PnL 显著{direction}：${abs(net_pnl):.2f}",
                "detail": f"今日净经营 PnL = ${net_pnl:.2f}（{direction} ${abs(net_pnl):.2f}）",
                "category": "cost",
                "confidence_level": "fact",
                "tags": ["auto_generated", "pnl"],
            },
            ai_recommended=True,
            ai_tier="light",
            ai_question=_build_ai_question_for_observation(
                f"净 PnL 显著{direction}：${abs(net_pnl):.2f}",
                f"今日净经营 PnL = ${net_pnl:.2f}",
                "cost",
            ),
            ai_context={"metric": "net_operating_pnl", "value": net_pnl, "threshold": 100.0},
            tags=["pnl", "auto_generated"],
        ))

    # ── 规则 5：长时间无观察 / Rule 5: No observations for extended period ──
    last_obs_ts = ls.get("observation_summary", {}).get("last_observation_ts_ms")
    observations = ls_records.get("observations", [])
    if len(observations) == 0 and last_obs_ts is None:
        packets.append(_build_review_packet(
            packet_type="auto_observation",
            what_happened="系统从未记录过观察 / No observations have been recorded yet",
            why_it_matters=(
                "学习系统需要观察数据作为基础。没有观察就无法总结经验、提出假设。"
                "建议开始记录系统运行中的发现。"
                " / Learning system needs observations as foundation. No observations means no learning."
            ),
            confidence_level="fact",
            target_collection="observations",
            record_data={
                "title": "学习系统初始化：首次观察扫描",
                "detail": "系统自动扫描已启动，但尚未有任何观察记录。这是首次扫描。",
                "category": "system",
                "confidence_level": "fact",
                "tags": ["auto_generated", "initialization"],
            },
            ai_recommended=False,
            ai_tier="none",
            ai_question="",
            tags=["initialization", "auto_generated"],
        ))

    return packets


# ── 自动经验提取 / Auto Lesson Extractor ─────────────────────────────────────




def generate_auto_lessons(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """
    从累积观察中检测模式并提取经验 / Detect patterns in observations and extract lessons.

    策略 / Strategy:
    - 统计每个 category 的观察次数，如果同一类别出现 3+ 次 → 提议生成经验
    - Count observations per category; if same category appears 3+ times → propose a lesson

    经验是推断，不是事实（原则 8）。
    Lessons are inferences, not facts (Principle 8).
    """
    packets: list[dict[str, Any]] = []
    ls_records = snapshot.get("learning_state", {}).get("records", {})
    observations = ls_records.get("observations", [])
    existing_lessons = ls_records.get("lessons", [])

    if len(observations) < 3:
        return packets

    # 按 category 分组计数 / Group by category
    cat_counts: dict[str, int] = {}
    cat_examples: dict[str, list[str]] = {}
    for obs in observations:
        cat = obs.get("category", "other")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        titles = cat_examples.setdefault(cat, [])
        if len(titles) < 3:
            titles.append(obs.get("title", "无标题"))

    # 已有经验的类别（避免重复提议）/ Categories with existing lessons (avoid duplicates)
    existing_lesson_cats = {l.get("category", "") for l in existing_lessons}

    # 类别名称映射（中文显示）/ Category name map for Chinese display
    cat_names = {
        "market": "市场", "execution": "执行", "cost": "成本",
        "system": "系统", "strategy": "策略", "other": "其他",
    }
    lesson_cat_map = {
        "market": "market_pattern", "execution": "execution_quality",
        "cost": "cost_insight", "system": "system", "strategy": "strategy",
        "other": "other",
    }

    for cat, count in cat_counts.items():
        if count < 3:
            continue
        lesson_cat = lesson_cat_map.get(cat, "other")
        if lesson_cat in existing_lesson_cats:
            continue

        cat_cn = cat_names.get(cat, cat)
        examples_str = "；".join(cat_examples.get(cat, []))
        title = f"「{cat_cn}」类别已有 {count} 条观察，建议总结经验"
        detail = f"在「{cat_cn}」类别下已积累 {count} 条观察记录。代表性观察：{examples_str}。建议归纳为一条可复用的经验。"

        packets.append(_build_review_packet(
            packet_type="auto_lesson",
            what_happened=f"「{cat_cn}」类别已有 {count} 条观察，可能存在规律 / {count} observations in '{cat}' category suggest a pattern",
            why_it_matters=(
                f"在同一个类别下反复出现的观察，通常意味着存在规律。"
                f"如果把这些发现总结为经验，系统未来可以更快识别类似情况。"
                f" / Repeated observations in same category often indicate a pattern worth remembering."
            ),
            confidence_level="inference",
            target_collection="lessons",
            record_data={
                "title": title,
                "detail": detail,
                "category": lesson_cat,
                "confidence_level": "inference",
                "actionable": True,
                "tags": ["auto_generated", f"from_{cat}_observations"],
            },
            ai_recommended=True,
            ai_tier="light",
            ai_question=_build_ai_question_for_lesson(title, detail, count),
            ai_context={"category": cat, "observation_count": count},
            tags=["pattern_detection", "auto_generated"],
        ))

    return packets


# ── 自动假设提议 / Auto Hypothesis Proposer ──────────────────────────────────




def generate_auto_hypotheses(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """
    从累积经验中提议假设 / Propose hypotheses from accumulated lessons.

    策略 / Strategy:
    - 有 actionable=True 的 lesson 但无关联的 hypothesis → 建议提出假设
    - If a lesson is actionable but has no linked hypothesis → propose one

    假设的置信度永远是 "hypothesis"（原则 8）。
    Hypothesis confidence is always "hypothesis" (Principle 8).
    """
    packets: list[dict[str, Any]] = []
    ls_records = snapshot.get("learning_state", {}).get("records", {})
    lessons = ls_records.get("lessons", [])
    hypotheses = ls_records.get("hypotheses", [])

    if not lessons:
        return packets

    # 已被假设引用的 lesson ID / Lesson IDs already referenced by hypotheses
    referenced_lesson_ids: set[str] = set()
    for hyp in hypotheses:
        for lid in hyp.get("supporting_lesson_ids", []):
            referenced_lesson_ids.add(lid)

    for lesson in lessons:
        lesson_id = lesson.get("lesson_id", "")
        if not lesson.get("actionable", False):
            continue
        if lesson_id in referenced_lesson_ids:
            continue

        title = lesson.get("title", "无标题")
        detail = lesson.get("detail", "")
        cat = lesson.get("category", "other")

        hyp_title = f"基于经验「{title}」的可检验假设"
        prediction = f"如果经验「{title}」成立，则在类似条件下应该能观察到相同规律"

        packets.append(_build_review_packet(
            packet_type="auto_hypothesis",
            what_happened=f"有一条可操作的经验尚未形成假设：{title} / Actionable lesson without hypothesis: {title}",
            why_it_matters=(
                "可操作的经验如果不转化为假设，就无法被系统性地验证。"
                "提出假设后可以设计实验来确认经验是否可靠。"
                " / Actionable lessons need hypotheses to be systematically validated."
            ),
            confidence_level="hypothesis",
            target_collection="hypotheses",
            record_data={
                "title": hyp_title,
                "description": f"基于经验记录：{detail}",
                "testable_prediction": prediction,
                "confidence_level": "hypothesis",
                "supporting_lesson_ids": [lesson_id],
                "tags": ["auto_generated", f"from_lesson_{lesson_id}"],
            },
            ai_recommended=True,
            ai_tier="standard",
            ai_question=_build_ai_question_for_hypothesis(hyp_title, prediction),
            ai_context={"source_lesson_id": lesson_id, "lesson_category": cat},
            tags=["hypothesis_proposal", "auto_generated"],
        ))

    return packets


# ── 自动学习管线写逻辑 / Auto Learning Pipeline Write Logic ──────────────────




def apply_auto_generate(
    envelope: RequestEnvelope, actor: AuthenticatedActor, scan_type: str
) -> tuple[dict[str, Any], str]:
    """
    触发自动扫描并生成审核包 / Trigger auto-scan and generate review packets.

    scan_type: "observations" | "lessons" | "hypotheses"

    生成的审核包追加到 learning_state.records.review_queue，
    通过 _content_hash 去重（跳过已存在的相同内容）。
    Generated packets are appended to review_queue with deduplication via _content_hash.

    安全保证 / Safety: 只生成审核包，不创建正式记录（原则 7）。
    Only generates review packets, never creates actual records (Principle 7).
    """
    require_scope(actor, "learning:manage")
    snapshot, _ = _base.get_latest_snapshot()
    verify_operator_identity(envelope, actor)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)

    if scan_type not in AUTO_SCAN_TYPES:
        raise HTTPException(status_code=400, detail={"reason_codes": ["invalid_scan_type"]})

    # 根据扫描类型调用对应的生成器 / Call corresponding generator by scan type
    if scan_type == "observations":
        new_packets = generate_auto_observations(snapshot)
    elif scan_type == "lessons":
        new_packets = generate_auto_lessons(snapshot)
    else:
        new_packets = generate_auto_hypotheses(snapshot)

    ts = now_ms()
    generated_ids: list[str] = []
    skipped = 0

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        nonlocal generated_ids, skipped
        ls = state["learning_state"]
        queue = ls.setdefault("records", {}).setdefault("review_queue", [])
        pipeline = ls.setdefault("auto_pipeline", {})

        # 去重：检查已有审核包的 _content_hash / Dedup: check existing _content_hash
        existing_hashes = {
            p.get("_content_hash") for p in queue
            if p.get("status") in {"pending_review", "ai_consulted"}
        }

        for pkt in new_packets:
            if pkt.get("_content_hash") in existing_hashes:
                skipped += 1
                continue
            queue.append(pkt)
            generated_ids.append(pkt["packet_id"])
            existing_hashes.add(pkt.get("_content_hash"))

        # 更新管线摘要 / Update pipeline summary
        ts_key = f"last_{scan_type[:-1] if scan_type.endswith('s') else scan_type}_scan_ts_ms"
        if scan_type == "observations":
            ts_key = "last_observation_scan_ts_ms"
        elif scan_type == "lessons":
            ts_key = "last_lesson_scan_ts_ms"
        else:
            ts_key = "last_hypothesis_scan_ts_ms"
        pipeline[ts_key] = ts
        pipeline["total_packets_generated"] = pipeline.get("total_packets_generated", 0) + len(generated_ids)

        audit_ref = _write_audit_fields(
            state, action_type=f"auto_scan_{scan_type}", operator_id=actor.actor_id,
            request_id=envelope.request_id, result="success", reason_codes=[],
            is_control_action=False,
        )
        _bump_revision(state)
        compiled = _compile_for_response(state)
        response = {
            "audit_ref": audit_ref,
            "data": {
                "packets_generated": len(generated_ids),
                "packet_ids": generated_ids,
                "scan_type": scan_type,
                "skipped_duplicates": skipped,
            },
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        return compiled

    final_state = _base.STORE.mutate(mutator)
    return {
        "audit_ref": final_state["audit_context"]["last_write_action_audit_ref"],
        "data": {
            "packets_generated": len(generated_ids),
            "packet_ids": generated_ids,
            "scan_type": scan_type,
            "skipped_duplicates": skipped,
        },
        "snapshot": final_state,
    }, "success"


def apply_review_decision(
    envelope: RequestEnvelope, actor: AuthenticatedActor, packet_id: str
) -> tuple[dict[str, Any], str]:
    """
    Operator 对审核包做出决定 / Operator decides on a review packet.

    payload:
    - decision: str   "approve" | "reject" | "defer" | "ask_ai"
    - reason: str     决定理由（可选）/ Decision reason (optional)

    批准 (approve): 从 candidate_record 提取数据，在对应 collection 创建真实记录
    拒绝 (reject): 标记为已拒绝，不创建记录
    搁置 (defer): 标记为已搁置，保留在队列中
    询问 AI (ask_ai): 标记为 AI 已咨询，返回预生成问题（实际 AI 调用为 stub）

    Approve: creates real record from candidate_record
    Reject: marks as rejected, no record created
    Defer: marks as deferred, stays in queue
    Ask AI: marks as ai_consulted, returns pre-built question (actual AI call is stub)
    """
    require_scope(actor, "learning:manage")
    snapshot, _ = _base.get_latest_snapshot()
    verify_operator_identity(envelope, actor)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)

    p = envelope.payload
    decision = str(p.get("decision", "")).strip()
    reason = str(p.get("reason", "")).strip()
    if decision not in REVIEW_DECISION_ACTIONS:
        raise HTTPException(status_code=400, detail={"reason_codes": ["invalid_review_decision"]})

    # 查找审核包 / Find the review packet
    queue = snapshot.get("learning_state", {}).get("records", {}).get("review_queue", [])
    target_idx = None
    for i, pkt in enumerate(queue):
        if pkt.get("packet_id") == packet_id:
            target_idx = i
            break
    if target_idx is None:
        raise HTTPException(status_code=404, detail={"reason_codes": ["review_packet_not_found"]})

    pkt = queue[target_idx]
    if pkt["status"] not in {"pending_review", "ai_consulted", "deferred"}:
        raise HTTPException(status_code=400, detail={"reason_codes": ["review_packet_already_decided"]})

    ts = now_ms()
    created_record_id: str | None = None

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        nonlocal created_record_id
        rq = state["learning_state"]["records"]["review_queue"]
        packet = rq[target_idx]

        # 记录决定 / Record decision
        packet["decided_by"] = actor.actor_id
        packet["decided_ts_ms"] = ts
        packet["decision"] = decision
        packet["decision_reason"] = reason or None

        pipeline = state["learning_state"].setdefault("auto_pipeline", {})

        if decision == "approve":
            packet["status"] = "approved"
            pipeline["total_packets_approved"] = pipeline.get("total_packets_approved", 0) + 1

            # 从 candidate_record 创建真实记录 / Create real record from candidate_record
            candidate = packet.get("candidate_record", {})
            target_col = candidate.get("target_collection", "observations")
            rec_data = candidate.get("record_data", {})

            if target_col == "observations":
                record_id = f"obs:{ts}"
                record = {
                    "observation_id": record_id,
                    "recorded_ts_ms": ts,
                    "recorded_by": actor.actor_id,
                    "source": "system_auto_approved",
                    "category": rec_data.get("category", "other"),
                    "confidence_level": rec_data.get("confidence_level", "inference"),
                    "title": rec_data.get("title", ""),
                    "detail": rec_data.get("detail", ""),
                    "related_hypothesis_id": rec_data.get("related_hypothesis_id"),
                    "tags": rec_data.get("tags", []),
                }
                state["learning_state"]["records"].setdefault("observations", []).append(record)
                state["learning_state"]["observation_summary"]["last_observation_ts_ms"] = ts

            elif target_col == "lessons":
                record_id = f"lesson:{ts}"
                record = {
                    "lesson_id": record_id,
                    "recorded_ts_ms": ts,
                    "recorded_by": actor.actor_id,
                    "source_observation_ids": rec_data.get("source_observation_ids", []),
                    "confidence_level": rec_data.get("confidence_level", "inference"),
                    "category": rec_data.get("category", "other"),
                    "title": rec_data.get("title", ""),
                    "detail": rec_data.get("detail", ""),
                    "actionable": rec_data.get("actionable", False),
                    "related_hypothesis_ids": rec_data.get("related_hypothesis_ids", []),
                    "tags": rec_data.get("tags", []),
                }
                state["learning_state"]["records"].setdefault("lessons", []).append(record)
                state["learning_state"]["memory"]["last_memory_update_ts_ms"] = ts

            elif target_col == "hypotheses":
                record_id = f"hyp:{ts}"
                record = {
                    "hypothesis_id": record_id,
                    "recorded_ts_ms": ts,
                    "recorded_by": actor.actor_id,
                    "status": "proposed",
                    "confidence_level": "hypothesis",  # 原则 8 强制 / Principle 8 enforced
                    "title": rec_data.get("title", ""),
                    "description": rec_data.get("description", ""),
                    "testable_prediction": rec_data.get("testable_prediction", ""),
                    "supporting_observation_ids": rec_data.get("supporting_observation_ids", []),
                    "supporting_lesson_ids": rec_data.get("supporting_lesson_ids", []),
                    "related_experiment_id": None,
                    "operator_verdict": None,
                    "operator_verdict_ts_ms": None,
                    "operator_verdict_reason": None,
                    "tags": rec_data.get("tags", []),
                }
                state["learning_state"]["records"].setdefault("hypotheses", []).append(record)
                state["learning_state"]["hypotheses"]["last_hypothesis_ts_ms"] = ts

            else:
                record_id = f"rec:{ts}"

            created_record_id = record_id

        elif decision == "reject":
            packet["status"] = "rejected"
            pipeline["total_packets_rejected"] = pipeline.get("total_packets_rejected", 0) + 1

        elif decision == "defer":
            packet["status"] = "deferred"

        elif decision == "ask_ai":
            packet["status"] = "ai_consulted"
            # AI 调用为 stub / AI call is a stub
            packet["ai_consultation_result"] = (
                "[AI 咨询功能待接入 H 链 / AI consultation pending H-chain integration] "
                "当前为占位回复。实际接入后，系统将通过 H1-H5 治理链调用 AI 并在此显示回复。"
            )
            packet["ai_consultation_cost_usd"] = 0.0

        audit_ref = _write_audit_fields(
            state, action_type=f"review_decision_{decision}", operator_id=actor.actor_id,
            request_id=envelope.request_id, result="success", reason_codes=[],
            is_control_action=False,
        )
        _bump_revision(state)
        compiled = _compile_for_response(state)
        response = {
            "audit_ref": audit_ref,
            "data": {
                "packet_id": packet_id,
                "decision": decision,
                "new_status": packet["status"],
                "record_created": decision == "approve",
                "created_record_id": created_record_id,
            },
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        return compiled

    final_state = _base.STORE.mutate(mutator)
    return {
        "audit_ref": final_state["audit_context"]["last_write_action_audit_ref"],
        "data": {
            "packet_id": packet_id,
            "decision": decision,
            "new_status": "approved" if decision == "approve" else (
                "rejected" if decision == "reject" else (
                    "deferred" if decision == "defer" else "ai_consulted"
                )
            ),
            "record_created": decision == "approve",
            "created_record_id": created_record_id,
        },
        "snapshot": final_state,
    }, "success"


def apply_ai_consultation(
    envelope: RequestEnvelope, actor: AuthenticatedActor, packet_id: str
) -> tuple[dict[str, Any], str]:
    """
    执行 AI 咨询（当前为 stub，已废弃）/ Execute AI consultation (stub, deprecated).

    [DEPRECATED] 此函數是 Learning Cockpit 審核隊列的占位符，非現有 AI 管線。
    [DEPRECATED] This function is a stub for the Learning Cockpit Review Queue,
    not the active AI pipeline. Use /phase2/strategist/intel-log for Strategist decisions.

    若需查看策略師 AI 決策記錄，請使用 /phase2/strategist/intel-log 端點。
    For Strategist AI decisions via the active pipeline, use /phase2/strategist/intel-log.

    兼容性：函數簽名不變，返回值包含 deprecation_notice 字段。
    Compatibility: function signature unchanged; return value includes deprecation_notice.
    """
    # Emit DeprecationWarning so callers (e.g. tests) can detect the deprecation.
    # 發出 DeprecationWarning，讓調用方（如測試）可以感知廢棄狀態。
    # stacklevel=2 points at the caller of apply_ai_consultation, not this function itself.
    warnings.warn(
        "apply_ai_consultation() is deprecated. "
        "Use /phase2/strategist/intel-log for AI pipeline decisions.",
        DeprecationWarning,
        stacklevel=2,
    )
    require_scope(actor, "learning:manage")
    snapshot, _ = _base.get_latest_snapshot()
    verify_operator_identity(envelope, actor)

    queue = snapshot.get("learning_state", {}).get("records", {}).get("review_queue", [])
    target_pkt = None
    for pkt in queue:
        if pkt.get("packet_id") == packet_id:
            target_pkt = pkt
            break
    if target_pkt is None:
        raise HTTPException(status_code=404, detail={"reason_codes": ["review_packet_not_found"]})

    ai_info = target_pkt.get("ai_consultation", {})
    question = ai_info.get("pre_built_question", "无预生成问题")
    tier = ai_info.get("recommended_tier", "light")

    return {
        "audit_ref": None,
        "data": {
            "packet_id": packet_id,
            "ai_tier": tier,
            "question_sent": question,
            "ai_response": (
                "[AI 咨询功能待接入 H 链 / AI consultation pending H-chain integration] "
                "当前为占位回复。系统已准备好通过 H1(thought_gate) → H2(query_budget) → "
                "H3(model_router) → H4(compute_governor) → H5(cost_log) 的完整治理链调用 AI。"
                "接入后将在此显示 AI 的真实回复。"
            ),
            "cost_usd": 0.0,
            "consultation_status": "stub_pending_h_chain_integration",
            # DEPRECATED: indicate callers to migrate to the active Strategist pipeline.
            # 廢棄通知：提示調用方遷移至現有策略師 AI 管線端點。
            "deprecation_notice": (
                "This endpoint is deprecated. "
                "Use /phase2/strategist/intel-log for Strategist AI pipeline decisions. "
                "此端點已廢棄，請改用 /phase2/strategist/intel-log。"
            ),
        },
        "snapshot": snapshot,
    }, "success"


# ── 审核队列只读构建器 / Review Queue Read-Only Builder ──────────────────────




def build_review_queue(snapshot: dict[str, Any]) -> dict[str, Any]:
    """
    构建审核队列视图 / Build review queue view.

    返回待审核的审核包（pending_review + ai_consulted + deferred）
    和最近已决定的审核包（approved + rejected）。
    Returns pending packets and recently decided packets.
    """
    ls = snapshot.get("learning_state", {})
    queue = ls.get("records", {}).get("review_queue", [])
    pipeline = ls.get("auto_pipeline", {})

    pending = [p for p in queue if p.get("status") in {"pending_review", "ai_consulted", "deferred"}]
    decided = [p for p in queue if p.get("status") in {"approved", "rejected"}]

    # 最新在前 / Newest first
    pending.sort(key=lambda x: x.get("created_ts_ms", 0), reverse=True)
    decided.sort(key=lambda x: x.get("decided_ts_ms", 0), reverse=True)

    return {
        "pending_packets": pending,
        "recent_decided": decided[-_MAX_RECENT_ENTRIES:],
        "pending_count": len(pending),
        "total_count": len(queue),
        "auto_pipeline_summary": copy.deepcopy(pipeline),
    }



# ── L 章只读查询构建器 / L-Chapter Read-Only Query Builders ────────────────────




def build_learning_feed(snapshot: dict[str, Any]) -> dict[str, Any]:
    """
    构建完整学习观察流 / Build complete learning observation feed.

    返回最近 N 条观察和经验教训，以及摘要统计。
    Returns the last N observations and lessons, plus summary statistics.
    """
    ls = snapshot.get("learning_state", {})
    ls_records = ls.get("records", {})

    observations = ls_records.get("observations", [])
    lessons = ls_records.get("lessons", [])

    # 取最近 N 条，按最新在前排列 / Take last N, newest first
    obs_recent = list(reversed(observations[-_MAX_RECENT_ENTRIES:]))
    les_recent = list(reversed(lessons[-_MAX_RECENT_ENTRIES:]))

    return {
        "observations_recent": obs_recent,
        "lessons_recent": les_recent,
        "observation_summary": copy.deepcopy(ls.get("observation_summary", {})),
        "memory_state": copy.deepcopy(ls.get("memory", {})),
        "totals": {
            "total_observations": len(observations),
            "total_lessons": len(lessons),
            "total_hypotheses": len(ls_records.get("hypotheses", [])),
            "total_experiments": len(ls_records.get("experiments", [])),
            "total_manual_notes": len(ls_records.get("manual_notes", [])),
        },
    }


def build_learning_experiments(snapshot: dict[str, Any]) -> dict[str, Any]:
    """
    构建实验队列完整视图 / Build complete experiment queue view.

    包含所有实验、关联假设和待审批统计。
    Includes all experiments, linked hypotheses, and pending approval statistics.
    """
    ls = snapshot.get("learning_state", {})
    ls_records = ls.get("records", {})

    experiments = ls_records.get("experiments", [])
    hypotheses = ls_records.get("hypotheses", [])

    # 统计待审批数 / Count pending approvals
    pending = sum(1 for e in experiments if e.get("status") == "pending_approval")

    return {
        "experiments": list(reversed(experiments[-_MAX_RECENT_ENTRIES:])),
        "hypotheses": list(reversed(hypotheses[-_MAX_RECENT_ENTRIES:])),
        "pending_approval_count": pending,
        "approval_required": ls.get("experiments", {}).get("approval_required", True),
    }

