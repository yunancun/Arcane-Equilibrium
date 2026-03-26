"""
OpenClaw / Bybit Control API v1 — L 章（学习 / 自我感知 / Net PnL）集成测试
OpenClaw / Bybit Control API v1 — L-Chapter (Learning / Self-Observability / Net PnL) integration tests.

测试覆盖五大模块 / Test coverage for five modules:
  1. 观察流 (Observation Feed) — 录入 + 验证 + 查询
  2. 经验记忆 (Lessons Memory) — 录入 + 关联 + 查询
  3. 假设队列 (Hypothesis Queue) — 提出 + 审批 + 状态转换
  4. 实验队列 (Experiment Queue) — 提案 + 审批 + 完成 + 状态管理
  5. 净 PnL 仪表盘 (Net PnL Dashboard) — 周期快照 + 趋势 + 成本分解

测试原则 / Testing principles:
  - 每个测试用例使用独立的临时状态文件，互不干扰。
    Each test uses an independent temporary state file; no cross-contamination.
  - 所有断言覆盖：成功路径、拒绝路径、安全边界。
    All assertions cover: success path, rejection path, safety boundaries.
  - 学习系统不授予执行权限（原则 7）。
    Learning system does not grant execution authority (Principle 7).
"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

# 确保项目根目录在 sys.path 中 / Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ── 测试工具函数 / Test Utility Functions ──────────────────────────────────────


def build_client():
    """
    构建测试客户端（每次使用独立的状态文件和模块实例）。
    Build a test client with an isolated state file and fresh module instance per invocation.
    """
    runtime_dir = Path(tempfile.mkdtemp(prefix="openclaw_test_learning_"))
    os.environ["OPENCLAW_STATE_FILE"] = str(runtime_dir / "state.json")
    os.environ["OPENCLAW_API_TOKEN"] = "test-token"

    from app import main_legacy as legacy_module
    from app import main as main_module
    importlib.reload(legacy_module)
    importlib.reload(main_module)
    return TestClient(main_module.app)


def auth_headers():
    """认证请求头 / Auth headers."""
    return {"Authorization": "Bearer test-token"}


def make_envelope(state_revision, payload=None, **extra):
    """
    构建标准请求 envelope / Build a standard request envelope.
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
    """获取当前 state_revision / Fetch current state_revision."""
    r = client.get("/api/v1/system/overview", headers=auth_headers())
    return r.json()["state_revision"]


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 观察流测试 / Observation Feed Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestObservationFeed:
    """观察流录入与查询测试 / Observation feed input and query tests."""

    def test_post_observation_accepted(self):
        """录入观察应被接受 / Post observation should be accepted."""
        client = build_client()
        rev = get_state_revision(client)
        r = client.post(
            "/api/v1/input/observation",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "title": "BTC price spike",
                "detail": "BTC surged 5% in 10 minutes on high volume",
                "category": "market",
                "confidence_level": "fact",
            }),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["accepted"] is True
        assert data["observation_id"].startswith("obs:")
        assert data["record_count_delta"] == 1

    def test_observation_requires_title_and_detail(self):
        """缺少标题或详情应返回 400 / Missing title or detail should return 400."""
        client = build_client()
        rev = get_state_revision(client)
        r = client.post(
            "/api/v1/input/observation",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "title": "",
                "detail": "",
                "category": "market",
                "confidence_level": "fact",
            }),
        )
        assert r.status_code == 400

    def test_observation_invalid_category(self):
        """无效类别应返回 400 / Invalid category should return 400."""
        client = build_client()
        rev = get_state_revision(client)
        r = client.post(
            "/api/v1/input/observation",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "title": "test",
                "detail": "test detail",
                "category": "invalid_category",
                "confidence_level": "fact",
            }),
        )
        assert r.status_code == 400

    def test_observation_invalid_confidence_level(self):
        """无效置信度应返回 400 / Invalid confidence level should return 400."""
        client = build_client()
        rev = get_state_revision(client)
        r = client.post(
            "/api/v1/input/observation",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "title": "test",
                "detail": "test detail",
                "category": "market",
                "confidence_level": "certain",
            }),
        )
        assert r.status_code == 400

    def test_learning_feed_returns_observations(self):
        """观察流查询应返回已录入的观察 / Learning feed should return recorded observations."""
        client = build_client()
        rev = get_state_revision(client)
        client.post(
            "/api/v1/input/observation",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "title": "Test observation",
                "detail": "Some detail",
                "category": "system",
                "confidence_level": "inference",
            }),
        )
        r = client.get("/api/v1/learning/feed", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data["observations_recent"]) == 1
        assert data["observations_recent"][0]["title"] == "Test observation"
        assert data["totals"]["total_observations"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 经验记忆测试 / Lessons Memory Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestLessonsMemory:
    """经验教训录入与查询测试 / Lesson input and query tests."""

    def test_post_lesson_accepted(self):
        """录入经验应被接受 / Post lesson should be accepted."""
        client = build_client()
        rev = get_state_revision(client)
        r = client.post(
            "/api/v1/input/lesson",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "title": "High volume precedes volatility",
                "detail": "Observed that volume spikes 30 min before major moves",
                "category": "market_pattern",
                "confidence_level": "inference",
            }),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["accepted"] is True
        assert data["lesson_id"].startswith("lesson:")

    def test_lesson_invalid_category(self):
        """无效经验类别应返回 400 / Invalid lesson category should return 400."""
        client = build_client()
        rev = get_state_revision(client)
        r = client.post(
            "/api/v1/input/lesson",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "title": "test",
                "detail": "test detail",
                "category": "bad_category",
                "confidence_level": "fact",
            }),
        )
        assert r.status_code == 400

    def test_learning_feed_returns_lessons(self):
        """观察流查询应返回已录入的经验 / Learning feed should return recorded lessons."""
        client = build_client()
        rev = get_state_revision(client)
        client.post(
            "/api/v1/input/lesson",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "title": "Cost insight",
                "detail": "AI API costs are 80% of total",
                "category": "cost_insight",
                "confidence_level": "fact",
            }),
        )
        r = client.get("/api/v1/learning/feed", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data["lessons_recent"]) == 1
        assert data["totals"]["total_lessons"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 假设队列测试 / Hypothesis Queue Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestHypothesisQueue:
    """假设提出与审批测试 / Hypothesis proposal and verdict tests."""

    def test_post_hypothesis_accepted(self):
        """提出假设应被接受 / Post hypothesis should be accepted."""
        client = build_client()
        rev = get_state_revision(client)
        r = client.post(
            "/api/v1/input/hypothesis",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "title": "Volume predicts price",
                "description": "High volume precedes 5%+ moves within 1 hour",
                "testable_prediction": "When 5-min volume > 3x average, price moves 5%+ in next hour 60%+ of time",
            }),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["accepted"] is True
        assert data["hypothesis_id"].startswith("hyp:")
        assert data["status"] == "proposed"

    def test_hypothesis_missing_fields(self):
        """缺少必填字段应返回 400 / Missing required fields should return 400."""
        client = build_client()
        rev = get_state_revision(client)
        r = client.post(
            "/api/v1/input/hypothesis",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "title": "test",
                # missing description and testable_prediction
            }),
        )
        assert r.status_code == 400

    def test_hypothesis_verdict_approve(self):
        """假设审批通过应更新状态 / Hypothesis approval should update status."""
        client = build_client()
        rev = get_state_revision(client)

        # 先提出假设 / First propose hypothesis
        r1 = client.post(
            "/api/v1/input/hypothesis",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "title": "Test hypothesis",
                "description": "Test description",
                "testable_prediction": "Test prediction",
            }),
        )
        hyp_id = r1.json()["data"]["hypothesis_id"]
        rev2 = r1.json()["state_revision"]

        # 审批通过 / Approve
        r2 = client.post(
            f"/api/v1/learning/hypothesis/{hyp_id}/verdict",
            headers=auth_headers(),
            json=make_envelope(rev2, payload={"verdict": "approved", "reason": "looks good"}),
        )
        assert r2.status_code == 200
        data = r2.json()["data"]
        assert data["new_status"] == "validated"
        assert data["operator_verdict"] == "approved"

    def test_hypothesis_verdict_reject(self):
        """假设审批拒绝应更新状态 / Hypothesis rejection should update status."""
        client = build_client()
        rev = get_state_revision(client)

        r1 = client.post(
            "/api/v1/input/hypothesis",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "title": "Bad hypothesis",
                "description": "Not well supported",
                "testable_prediction": "Unclear prediction",
            }),
        )
        hyp_id = r1.json()["data"]["hypothesis_id"]
        rev2 = r1.json()["state_revision"]

        r2 = client.post(
            f"/api/v1/learning/hypothesis/{hyp_id}/verdict",
            headers=auth_headers(),
            json=make_envelope(rev2, payload={"verdict": "rejected", "reason": "insufficient evidence"}),
        )
        assert r2.status_code == 200
        assert r2.json()["data"]["new_status"] == "invalidated"

    def test_hypothesis_verdict_invalid_action(self):
        """无效判定动作应返回 400 / Invalid verdict action should return 400."""
        client = build_client()
        rev = get_state_revision(client)

        r1 = client.post(
            "/api/v1/input/hypothesis",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "title": "Test",
                "description": "Test",
                "testable_prediction": "Test",
            }),
        )
        hyp_id = r1.json()["data"]["hypothesis_id"]
        rev2 = r1.json()["state_revision"]

        r2 = client.post(
            f"/api/v1/learning/hypothesis/{hyp_id}/verdict",
            headers=auth_headers(),
            json=make_envelope(rev2, payload={"verdict": "maybe"}),
        )
        assert r2.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 实验队列测试 / Experiment Queue Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestExperimentQueue:
    """实验提案、审批与完成测试 / Experiment proposal, approval, and completion tests."""

    def _create_hypothesis(self, client, rev):
        """辅助：创建一个假设并返回其 ID / Helper: create a hypothesis and return its ID."""
        r = client.post(
            "/api/v1/input/hypothesis",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "title": "Test hypothesis",
                "description": "Test description",
                "testable_prediction": "Test prediction",
            }),
        )
        return r.json()["data"]["hypothesis_id"], r.json()["state_revision"]

    def test_post_experiment_accepted(self):
        """提出实验应被接受 / Post experiment should be accepted."""
        client = build_client()
        rev = get_state_revision(client)
        hyp_id, rev = self._create_hypothesis(client, rev)

        r = client.post(
            "/api/v1/input/experiment",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "hypothesis_id": hyp_id,
                "title": "Volume spike test",
                "description": "Monitor volume spikes for 1 week",
                "method": "Track 5-min volume candles and correlate with price",
                "success_criteria": "60%+ correlation confirmed",
            }),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["accepted"] is True
        assert data["experiment_id"].startswith("exp:")
        assert data["status"] == "pending_approval"
        assert data["approval_required"] is True

    def test_experiment_requires_valid_hypothesis(self):
        """实验必须关联有效假设 / Experiment must link to a valid hypothesis."""
        client = build_client()
        rev = get_state_revision(client)
        r = client.post(
            "/api/v1/input/experiment",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "hypothesis_id": "nonexistent",
                "title": "test",
                "description": "test",
                "method": "test",
                "success_criteria": "test",
            }),
        )
        assert r.status_code == 400

    def test_experiment_approve(self):
        """实验审批通过 / Experiment approval."""
        client = build_client()
        rev = get_state_revision(client)
        hyp_id, rev = self._create_hypothesis(client, rev)

        r1 = client.post(
            "/api/v1/input/experiment",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "hypothesis_id": hyp_id,
                "title": "test exp",
                "description": "test",
                "method": "test",
                "success_criteria": "test",
            }),
        )
        exp_id = r1.json()["data"]["experiment_id"]
        rev2 = r1.json()["state_revision"]

        r2 = client.post(
            f"/api/v1/learning/experiment/{exp_id}/approve",
            headers=auth_headers(),
            json=make_envelope(rev2, payload={"action": "approved", "reason": "proceed"}),
        )
        assert r2.status_code == 200
        assert r2.json()["data"]["new_status"] == "approved"

    def test_experiment_reject(self):
        """实验审批拒绝 / Experiment rejection."""
        client = build_client()
        rev = get_state_revision(client)
        hyp_id, rev = self._create_hypothesis(client, rev)

        r1 = client.post(
            "/api/v1/input/experiment",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "hypothesis_id": hyp_id,
                "title": "risky exp",
                "description": "too risky",
                "method": "unknown",
                "success_criteria": "unclear",
            }),
        )
        exp_id = r1.json()["data"]["experiment_id"]
        rev2 = r1.json()["state_revision"]

        r2 = client.post(
            f"/api/v1/learning/experiment/{exp_id}/approve",
            headers=auth_headers(),
            json=make_envelope(rev2, payload={"action": "rejected", "reason": "too risky"}),
        )
        assert r2.status_code == 200
        assert r2.json()["data"]["new_status"] == "rejected"

    def test_experiment_complete(self):
        """实验完成并录入结论 / Experiment completion with conclusion."""
        client = build_client()
        rev = get_state_revision(client)
        hyp_id, rev = self._create_hypothesis(client, rev)

        # 创建实验 / Create experiment
        r1 = client.post(
            "/api/v1/input/experiment",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "hypothesis_id": hyp_id,
                "title": "completable exp",
                "description": "test",
                "method": "test",
                "success_criteria": "test",
            }),
        )
        exp_id = r1.json()["data"]["experiment_id"]
        rev2 = r1.json()["state_revision"]

        # 审批通过 / Approve
        r2 = client.post(
            f"/api/v1/learning/experiment/{exp_id}/approve",
            headers=auth_headers(),
            json=make_envelope(rev2, payload={"action": "approved"}),
        )
        rev3 = r2.json()["state_revision"]

        # 完成 / Complete
        r3 = client.post(
            f"/api/v1/learning/experiment/{exp_id}/complete",
            headers=auth_headers(),
            json=make_envelope(rev3, payload={
                "result_summary": "Hypothesis confirmed with 65% correlation",
                "result_confidence_level": "inference",
            }),
        )
        assert r3.status_code == 200
        data = r3.json()["data"]
        assert data["new_status"] == "completed"
        assert data["result_confidence_level"] == "inference"

    def test_experiment_complete_requires_summary(self):
        """完成实验时必须提供结论 / Completing experiment requires result summary."""
        client = build_client()
        rev = get_state_revision(client)
        hyp_id, rev = self._create_hypothesis(client, rev)

        r1 = client.post(
            "/api/v1/input/experiment",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "hypothesis_id": hyp_id,
                "title": "test",
                "description": "test",
                "method": "test",
                "success_criteria": "test",
            }),
        )
        exp_id = r1.json()["data"]["experiment_id"]
        rev2 = r1.json()["state_revision"]

        # 审批通过 / Approve
        r2 = client.post(
            f"/api/v1/learning/experiment/{exp_id}/approve",
            headers=auth_headers(),
            json=make_envelope(rev2, payload={"action": "approved"}),
        )
        rev3 = r2.json()["state_revision"]

        # 尝试完成但缺少结论 / Try to complete without summary
        r3 = client.post(
            f"/api/v1/learning/experiment/{exp_id}/complete",
            headers=auth_headers(),
            json=make_envelope(rev3, payload={
                "result_summary": "",
                "result_confidence_level": "fact",
            }),
        )
        assert r3.status_code == 400

    def test_learning_experiments_view(self):
        """实验队列视图应包含已创建的实验 / Experiments view should include created experiments."""
        client = build_client()
        rev = get_state_revision(client)
        hyp_id, rev = self._create_hypothesis(client, rev)

        client.post(
            "/api/v1/input/experiment",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "hypothesis_id": hyp_id,
                "title": "test exp",
                "description": "test",
                "method": "test",
                "success_criteria": "test",
            }),
        )

        r = client.get("/api/v1/learning/experiments", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data["experiments"]) == 1
        assert data["pending_approval_count"] == 1
        assert data["approval_required"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 净 PnL 仪表盘测试 / Net PnL Dashboard Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestNetPnLDashboard:
    """净 PnL 仪表盘测试 / Net PnL dashboard tests."""

    def test_get_net_pnl_dashboard(self):
        """仪表盘应返回完整结构 / Dashboard should return complete structure."""
        client = build_client()
        r = client.get("/api/v1/learning/net-pnl", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert "daily" in data
        assert "cost_breakdown" in data
        assert "period_snapshots" in data
        assert "net_pnl_trend" in data
        assert "entry_totals" in data

    def test_post_period_snapshot(self):
        """保存周期快照应被接受 / Save period snapshot should be accepted."""
        client = build_client()
        rev = get_state_revision(client)
        r = client.post(
            "/api/v1/input/pnl-period-snapshot",
            headers=auth_headers(),
            json=make_envelope(rev, payload={"period_label": "2026-03-26"}),
        )
        assert r.status_code == 200
        assert r.json()["data"]["accepted"] is True

    def test_period_snapshot_appears_in_dashboard(self):
        """周期快照应出现在仪表盘中 / Period snapshot should appear in dashboard."""
        client = build_client()
        rev = get_state_revision(client)

        # 先录入一些成本 / First record some costs
        client.post(
            "/api/v1/input/cost",
            headers=auth_headers(),
            json=make_envelope(rev, payload={"amount": 10.5, "category": "ai_api", "description": "Claude call"}),
        )
        rev2 = get_state_revision(client)

        # 保存快照 / Save snapshot
        client.post(
            "/api/v1/input/pnl-period-snapshot",
            headers=auth_headers(),
            json=make_envelope(rev2, payload={"period_label": "2026-03-26"}),
        )

        r = client.get("/api/v1/learning/net-pnl", headers=auth_headers())
        data = r.json()["data"]
        assert len(data["period_snapshots"]) == 1
        assert data["period_snapshots"][0]["period_label"] == "2026-03-26"
        assert data["period_snapshots"][0]["total_cost"] == 10.5

    def test_net_pnl_trend_from_snapshots(self):
        """趋势数据应从周期快照计算 / Trend data should be computed from period snapshots."""
        client = build_client()
        rev = get_state_revision(client)

        # 保存两个快照 / Save two snapshots
        client.post(
            "/api/v1/input/pnl-period-snapshot",
            headers=auth_headers(),
            json=make_envelope(rev, payload={"period_label": "day-1"}),
        )
        rev2 = get_state_revision(client)
        client.post(
            "/api/v1/input/pnl-period-snapshot",
            headers=auth_headers(),
            json=make_envelope(rev2, payload={"period_label": "day-2"}),
        )

        r = client.get("/api/v1/learning/net-pnl", headers=auth_headers())
        data = r.json()["data"]
        assert len(data["net_pnl_trend"]) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# 6. 状态完整性与向后兼容测试 / State Integrity & Backward Compatibility Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestStateIntegrity:
    """状态完整性与安全边界测试 / State integrity and safety boundary tests."""

    def test_compile_state_updates_learning_derived(self):
        """compile_state 应更新学习派生字段 / compile_state should update learning derived fields."""
        client = build_client()
        rev = get_state_revision(client)

        # 创建一个假设 / Create a hypothesis
        client.post(
            "/api/v1/input/hypothesis",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "title": "test",
                "description": "test",
                "testable_prediction": "test",
            }),
        )

        # 检查假设列表中有记录 / Check hypotheses list has records
        r = client.get("/api/v1/learning/hypotheses", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data["hypotheses"]) == 1

    def test_chapter_status_includes_L(self):
        """章节状态应包含 L 章 / Chapter status should include L chapter."""
        client = build_client()
        r = client.get("/api/v1/system/chapter-status", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert "L" in data
        assert data["L"]["chapter_state"] == "implemented"
        assert data["L"]["readiness_scope"] == "observe_and_record_only"

    def test_existing_learning_overview_backward_compat(self):
        """已有的 learning/overview 端点应继续正常工作 / Existing learning/overview should still work."""
        client = build_client()
        r = client.get("/api/v1/learning/overview", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert "summary" in data
        assert "experiments" in data
        assert "approval_requirements" in data

    def test_existing_learning_hypotheses_backward_compat(self):
        """已有的 learning/hypotheses 端点应继续正常工作 / Existing learning/hypotheses should still work."""
        client = build_client()
        r = client.get("/api/v1/learning/hypotheses", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert "hypotheses" in data
        assert "experiments" in data

    def test_execution_authority_still_protected(self):
        """学习操作不应授予执行权限 / Learning operations should not grant execution authority."""
        client = build_client()
        rev = get_state_revision(client)

        # 做一系列学习操作 / Perform a series of learning operations
        client.post(
            "/api/v1/input/observation",
            headers=auth_headers(),
            json=make_envelope(rev, payload={
                "title": "test", "detail": "test", "category": "market", "confidence_level": "fact",
            }),
        )

        # 验证执行权限未变 / Verify execution authority unchanged
        # 通过 control-plane 端点检查执行模式开关 / Check via control-plane endpoint
        r = client.get("/api/v1/system/control-plane", headers=auth_headers())
        data = r.json()["data"]
        assert data["execution_control_summary"]["global_execution_mode_switch_summary"] == "disabled"

    def test_unauthenticated_learning_rejected(self):
        """未认证请求应被拒绝 / Unauthenticated requests should be rejected."""
        client = build_client()
        r = client.get("/api/v1/learning/feed")
        assert r.status_code == 401

        r2 = client.post(
            "/api/v1/input/observation",
            json=make_envelope(1, payload={
                "title": "test", "detail": "test", "category": "market", "confidence_level": "fact",
            }),
        )
        assert r2.status_code == 401
