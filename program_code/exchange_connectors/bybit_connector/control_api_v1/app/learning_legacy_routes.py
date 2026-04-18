from __future__ import annotations

"""
MODULE_NOTE (中文):
  Learning / PnL legacy 路由（E5-P0-5 拆分自 legacy_routes.py）。
  包含 19 條路由，分五類：

    [GET 只讀]
      /api/v1/learning/overview
      /api/v1/learning/hypotheses
      /api/v1/learning/feed
      /api/v1/learning/experiments
      /api/v1/learning/net-pnl

    [POST 錄入]
      /api/v1/input/observation
      /api/v1/input/lesson
      /api/v1/input/hypothesis
      /api/v1/input/experiment

    [POST 管理]
      /api/v1/learning/hypothesis/{hypothesis_id}/verdict
      /api/v1/learning/experiment/{experiment_id}/approve
      /api/v1/learning/experiment/{experiment_id}/complete

    [POST PnL]
      /api/v1/input/pnl-period-snapshot
      /api/v1/input/pnl-entry

    [自動學習管線]
      /api/v1/learning/auto/scan-observations
      /api/v1/learning/auto/scan-lessons
      /api/v1/learning/auto/scan-hypotheses
      /api/v1/learning/review-queue
      /api/v1/learning/review/{packet_id}/decide

  ★ Monkey-patch 安全：envelope_response / get_latest_snapshot 皆在 request
    時間經 `_base.xxx(...)` 間接呼叫。

MODULE_NOTE (English):
  Learning / PnL legacy routes (split out of legacy_routes.py in E5-P0-5).
  19 routes total, grouped into read views, inputs, management actions, PnL
  inputs, and the auto-learning pipeline scan / review endpoints.

  ★ Monkey-patch safety: envelope_response / get_latest_snapshot resolved via
    `_base.xxx(...)` at request time.
"""

from fastapi import Depends

from . import main_legacy as _base
from .learning_ops import (
    apply_auto_generate,
    apply_experiment_approval,
    apply_experiment_completion,
    apply_hypothesis_verdict,
    apply_learning_experiment,
    apply_learning_hypothesis,
    apply_learning_lesson,
    apply_learning_observation,
    apply_review_decision,
    build_learning_experiments,
    build_learning_feed,
    build_review_queue,
)
from .pnl_ops import (
    apply_pnl_entry,
    apply_pnl_period_snapshot,
    build_net_pnl_dashboard,
)
from .state_models import (
    AutoGenerationResultData,
    ExperimentAcceptedData,
    ExperimentApprovalData,
    ExperimentCompletionData,
    HypothesisAcceptedData,
    HypothesisVerdictData,
    InputAcceptedData,
    LearningExperimentsData,
    LearningFeedData,
    LearningHypothesesData,
    LearningOverviewData,
    LessonAcceptedData,
    NetPnLDashboardData,
    ObservationAcceptedData,
    PnLEntryData,
    RequestEnvelope,
    ResponseEnvelope,
    ReviewDecisionData,
    ReviewQueueData,
)


def register_learning_legacy_routes(app) -> None:
    """
    Register all learning / PnL legacy routes on the FastAPI app.
    在 FastAPI app 上註冊所有 learning / PnL legacy 路由。
    """
    settings = _base.settings

    # ── GET 只讀 / Read-only views ───────────────────────────────────────────

    @app.get(
        f"{settings.api_prefix}/learning/overview",
        response_model=ResponseEnvelope[LearningOverviewData],
    )
    def get_learning_overview(
        actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[LearningOverviewData]:
        """Learning overview / 學習系統總覽."""
        snapshot, _ = _base.get_latest_snapshot()
        data = LearningOverviewData(
            summary=snapshot["learning_state"]["observation_summary"],
            experiments=snapshot["learning_state"]["experiments"],
            approval_requirements={
                "approval_required": snapshot["learning_state"]["experiments"]["approval_required"]
            },
        )
        return _base.envelope_response(
            snapshot=snapshot,
            request_id=None,
            action_result="success",
            data=data,
        )

    @app.get(
        f"{settings.api_prefix}/learning/hypotheses",
        response_model=ResponseEnvelope[LearningHypothesesData],
    )
    def get_learning_hypotheses(
        actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[LearningHypothesesData]:
        """Learning hypotheses list / 學習假設列表."""
        snapshot, _ = _base.get_latest_snapshot()
        data = LearningHypothesesData(
            hypotheses=snapshot["learning_state"]["records"]["hypotheses"],
            experiments=snapshot["learning_state"]["records"]["experiments"],
            approval_requirements={
                "approval_required": snapshot["learning_state"]["experiments"]["approval_required"]
            },
        )
        return _base.envelope_response(
            snapshot=snapshot,
            request_id=None,
            action_result="success",
            data=data,
        )

    @app.get(
        f"{settings.api_prefix}/learning/feed",
        response_model=ResponseEnvelope[LearningFeedData],
    )
    def get_learning_feed(
        actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[LearningFeedData]:
        """
        Learning observation feed / 學習觀察流。

        Returns recent observations and lessons, plus summary statistics.
        返回最近的觀察和經驗教訓列表，以及摘要統計。
        """
        snapshot, _ = _base.get_latest_snapshot()
        feed = build_learning_feed(snapshot)
        return _base.envelope_response(
            snapshot=snapshot,
            request_id=None,
            action_result="success",
            data=LearningFeedData(**feed),
        )

    @app.get(
        f"{settings.api_prefix}/learning/experiments",
        response_model=ResponseEnvelope[LearningExperimentsData],
    )
    def get_learning_experiments_list(
        actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[LearningExperimentsData]:
        """
        Complete experiment queue view / 實驗隊列完整視圖。

        Includes all experiments and linked hypotheses, plus pending approval count.
        包含所有實驗和關聯假設，以及待審批數量。
        """
        snapshot, _ = _base.get_latest_snapshot()
        data = build_learning_experiments(snapshot)
        return _base.envelope_response(
            snapshot=snapshot,
            request_id=None,
            action_result="success",
            data=LearningExperimentsData(**data),
        )

    @app.get(
        f"{settings.api_prefix}/learning/net-pnl",
        response_model=ResponseEnvelope[NetPnLDashboardData],
    )
    def get_net_pnl_dashboard(
        actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[NetPnLDashboardData]:
        """
        Net PnL dashboard with full cost breakdown / 含所有成本分解的淨 PnL 儀表盤。

        Integrates daily PnL, cost category breakdown, trends, and recent entries.
        整合每日 PnL、成本分類分解、趨勢和最近錄入條目。
        """
        snapshot, _ = _base.get_latest_snapshot()
        dashboard = build_net_pnl_dashboard(snapshot)
        return _base.envelope_response(
            snapshot=snapshot,
            request_id=None,
            action_result="success",
            data=NetPnLDashboardData(**dashboard),
        )

    # ── POST 錄入 / Input routes ──────────────────────────────────────────────

    @app.post(
        f"{settings.api_prefix}/input/observation",
        response_model=ResponseEnvelope[ObservationAcceptedData],
    )
    def post_input_observation(
        envelope: RequestEnvelope, actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[ObservationAcceptedData]:
        """
        Record an observation to the observation feed / 錄入觀察記錄。

        payload fields: title, detail, category, confidence_level,
        related_hypothesis_id (optional), tags (optional).
        """
        result, action_result = apply_learning_observation(envelope, actor)
        return _base.envelope_response(
            snapshot=result["snapshot"],
            request_id=envelope.request_id,
            action_result=action_result,
            data=ObservationAcceptedData(**result["data"]),
            audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )

    @app.post(
        f"{settings.api_prefix}/input/lesson",
        response_model=ResponseEnvelope[LessonAcceptedData],
    )
    def post_input_lesson(
        envelope: RequestEnvelope, actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[LessonAcceptedData]:
        """
        Record a lesson to the lessons memory / 錄入經驗教訓。

        payload fields: title, detail, category, confidence_level.
        """
        result, action_result = apply_learning_lesson(envelope, actor)
        return _base.envelope_response(
            snapshot=result["snapshot"],
            request_id=envelope.request_id,
            action_result=action_result,
            data=LessonAcceptedData(**result["data"]),
            audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )

    @app.post(
        f"{settings.api_prefix}/input/hypothesis",
        response_model=ResponseEnvelope[HypothesisAcceptedData],
    )
    def post_input_hypothesis(
        envelope: RequestEnvelope, actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[HypothesisAcceptedData]:
        """
        Propose a hypothesis / 提出假設。

        Principle 8: confidence_level is automatically set to "hypothesis".
        原則 8：confidence_level 自動設為 "hypothesis"。

        payload fields: title, description, testable_prediction.
        """
        result, action_result = apply_learning_hypothesis(envelope, actor)
        return _base.envelope_response(
            snapshot=result["snapshot"],
            request_id=envelope.request_id,
            action_result=action_result,
            data=HypothesisAcceptedData(**result["data"]),
            audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )

    @app.post(
        f"{settings.api_prefix}/input/experiment",
        response_model=ResponseEnvelope[ExperimentAcceptedData],
    )
    def post_input_experiment(
        envelope: RequestEnvelope, actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[ExperimentAcceptedData]:
        """
        Propose an experiment to validate a hypothesis / 提出實驗驗證假設。

        payload fields: hypothesis_id, title, description, method, success_criteria.
        """
        result, action_result = apply_learning_experiment(envelope, actor)
        return _base.envelope_response(
            snapshot=result["snapshot"],
            request_id=envelope.request_id,
            action_result=action_result,
            data=ExperimentAcceptedData(**result["data"]),
            audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )

    # ── POST 管理 / Management routes ─────────────────────────────────────────

    @app.post(
        f"{settings.api_prefix}/learning/hypothesis/{{hypothesis_id}}/verdict",
        response_model=ResponseEnvelope[HypothesisVerdictData],
    )
    def post_hypothesis_verdict(
        hypothesis_id: str,
        envelope: RequestEnvelope,
        actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[HypothesisVerdictData]:
        """
        Operator renders verdict on a hypothesis / Operator 審批假設。

        payload fields: verdict (approved / rejected / archived), reason (optional).
        """
        result, action_result = apply_hypothesis_verdict(envelope, actor, hypothesis_id)
        return _base.envelope_response(
            snapshot=result["snapshot"],
            request_id=envelope.request_id,
            action_result=action_result,
            data=HypothesisVerdictData(**result["data"]),
            audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )

    @app.post(
        f"{settings.api_prefix}/learning/experiment/{{experiment_id}}/approve",
        response_model=ResponseEnvelope[ExperimentApprovalData],
    )
    def post_experiment_approval(
        experiment_id: str,
        envelope: RequestEnvelope,
        actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[ExperimentApprovalData]:
        """
        Operator approves or rejects an experiment / Operator 審批實驗。

        payload fields: action (approved / rejected), reason (optional).
        """
        result, action_result = apply_experiment_approval(envelope, actor, experiment_id)
        return _base.envelope_response(
            snapshot=result["snapshot"],
            request_id=envelope.request_id,
            action_result=action_result,
            data=ExperimentApprovalData(**result["data"]),
            audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )

    @app.post(
        f"{settings.api_prefix}/learning/experiment/{{experiment_id}}/complete",
        response_model=ResponseEnvelope[ExperimentCompletionData],
    )
    def post_experiment_completion(
        experiment_id: str,
        envelope: RequestEnvelope,
        actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[ExperimentCompletionData]:
        """
        Mark an experiment as completed / 標記實驗完成。

        payload fields: result_summary, result_confidence_level
        (fact / inference / hypothesis).
        """
        result, action_result = apply_experiment_completion(envelope, actor, experiment_id)
        return _base.envelope_response(
            snapshot=result["snapshot"],
            request_id=envelope.request_id,
            action_result=action_result,
            data=ExperimentCompletionData(**result["data"]),
            audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )

    # ── PnL Input Routes / PnL 錄入路由 ───────────────────────────────────────

    @app.post(
        f"{settings.api_prefix}/input/pnl-period-snapshot",
        response_model=ResponseEnvelope[InputAcceptedData],
    )
    def post_pnl_period_snapshot(
        envelope: RequestEnvelope, actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[InputAcceptedData]:
        """
        Save current business metrics as a period snapshot.
        保存當前經營指標為週期快照。

        payload fields: period_label (e.g. "2026-03-26").
        """
        result, action_result = apply_pnl_period_snapshot(envelope, actor)
        return _base.envelope_response(
            snapshot=result["snapshot"],
            request_id=envelope.request_id,
            action_result=action_result,
            data=InputAcceptedData(**result["data"]),
            audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )

    @app.post(
        f"{settings.api_prefix}/input/pnl-entry",
        response_model=ResponseEnvelope[PnLEntryData],
    )
    def post_pnl_entry(
        envelope: RequestEnvelope, actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[PnLEntryData]:
        """
        Record a PnL update entry / 錄入 PnL 更新條目。

        Used to manually record realized/unrealized PnL updates.
        Automatically refreshes PnL metrics in the daily business summary.
        用於手動錄入已實現/未實現盈虧更新；自動刷新每日經營摘要中的 PnL 指標。

        payload fields: entry_type, realized_pnl, unrealized_pnl, symbol (opt),
        note (opt), category (opt).
        """
        result, action_result = apply_pnl_entry(envelope, actor)
        return _base.envelope_response(
            snapshot=result["snapshot"],
            request_id=envelope.request_id,
            action_result=action_result,
            data=PnLEntryData(**result["data"]),
            audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )

    # ── Auto Learning Pipeline / 自動學習管線 ─────────────────────────────────

    @app.post(
        f"{settings.api_prefix}/learning/auto/scan-observations",
        response_model=ResponseEnvelope[AutoGenerationResultData],
    )
    def post_auto_scan_observations(
        envelope: RequestEnvelope, actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[AutoGenerationResultData]:
        """
        Scan system state and auto-generate observation review packets.
        掃描系統狀態並自動生成觀察審核包。
        """
        result, action_result = apply_auto_generate(envelope, actor, "observations")
        return _base.envelope_response(
            snapshot=result["snapshot"],
            request_id=envelope.request_id,
            action_result=action_result,
            data=AutoGenerationResultData(**result["data"]),
            audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )

    @app.post(
        f"{settings.api_prefix}/learning/auto/scan-lessons",
        response_model=ResponseEnvelope[AutoGenerationResultData],
    )
    def post_auto_scan_lessons(
        envelope: RequestEnvelope, actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[AutoGenerationResultData]:
        """
        Auto-extract lesson review packets from accumulated observations.
        從累積觀察中自動提取經驗審核包。
        """
        result, action_result = apply_auto_generate(envelope, actor, "lessons")
        return _base.envelope_response(
            snapshot=result["snapshot"],
            request_id=envelope.request_id,
            action_result=action_result,
            data=AutoGenerationResultData(**result["data"]),
            audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )

    @app.post(
        f"{settings.api_prefix}/learning/auto/scan-hypotheses",
        response_model=ResponseEnvelope[AutoGenerationResultData],
    )
    def post_auto_scan_hypotheses(
        envelope: RequestEnvelope, actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[AutoGenerationResultData]:
        """
        Auto-propose hypothesis review packets from accumulated lessons.
        從累積經驗中自動提議假設審核包。
        """
        result, action_result = apply_auto_generate(envelope, actor, "hypotheses")
        return _base.envelope_response(
            snapshot=result["snapshot"],
            request_id=envelope.request_id,
            action_result=action_result,
            data=AutoGenerationResultData(**result["data"]),
            audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )

    @app.get(
        f"{settings.api_prefix}/learning/review-queue",
        response_model=ResponseEnvelope[ReviewQueueData],
    )
    def get_review_queue_view(
        actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[ReviewQueueData]:
        """
        Get review queue / 取得審核隊列。

        Returns pending and recently decided review packets, plus pipeline summary.
        返回待審核的審核包和最近已決定的審核包，以及管線摘要。
        """
        snapshot, _ = _base.get_latest_snapshot()
        data = build_review_queue(snapshot)
        return _base.envelope_response(
            snapshot=snapshot,
            request_id=None,
            action_result="success",
            data=ReviewQueueData(**data),
        )

    @app.post(
        f"{settings.api_prefix}/learning/review/{{packet_id}}/decide",
        response_model=ResponseEnvelope[ReviewDecisionData],
    )
    def post_review_decide(
        packet_id: str,
        envelope: RequestEnvelope,
        actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[ReviewDecisionData]:
        """
        Decide on a review packet / 對審核包做出決定。

        payload fields:
          - decision: "approve" | "reject" | "defer" | "ask_ai"
          - reason:   optional

        Upon approval, system auto-creates the corresponding record.
        批准後系統自動建立對應的正式記錄。
        """
        result, action_result = apply_review_decision(envelope, actor, packet_id)
        return _base.envelope_response(
            snapshot=result["snapshot"],
            request_id=envelope.request_id,
            action_result=action_result,
            data=ReviewDecisionData(**result["data"]),
            audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )


__all__ = ["register_learning_legacy_routes"]
