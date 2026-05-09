"""
Comprehensive tests for Learning Tier Gate (L1–L5) / 学习等级门控综合测试

Tests cover:
  - Tier state initialization and properties
  - Metrics update and tracking
  - Eligibility checking for all transitions (L1→L2→L3→L4→L5)
  - Promotion logic and audit callbacks
  - Capability restrictions per tier
  - Thread safety
  - Serialization (export/import)
  - Edge cases and error handling

Coverage target: ~100%
"""

import threading
import time
import uuid
from typing import Any

import pytest

from app.learning_tier_gate import (
    LearningTier,
    LearningTierGate,
    TierEligibilityCriteria,
    PromotionEvent,
    PromotionInitiator,
    LearningTierGateError,
    TierCapabilities,
    TIER_CAPABILITIES,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Test Fixtures / 测试夹具
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def gate():
    """Create a fresh LearningTierGate instance for each test / 为每个测试创建新实例"""
    return LearningTierGate()


@pytest.fixture
def audit_log():
    """Fixture to collect audit callbacks / 用于收集审计回调的夹具"""
    logs = []
    def callback(record: dict[str, Any]) -> None:
        logs.append(record)
    return logs


@pytest.fixture
def gate_with_audit(audit_log):
    """Create a gate with audit callback / 创建带审计回调的门控"""
    gate = LearningTierGate(audit_callback=lambda r: audit_log.append(r))
    return gate, audit_log


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Initialization and Basic Properties / 初始化和基本属性
# ═══════════════════════════════════════════════════════════════════════════════

def test_gate_initializes_at_l1(gate):
    """Test that gate initializes at L1 / 测试门控在 L1 初始化"""
    assert gate.current_tier == LearningTier.L1
    assert gate.get_current_tier() == LearningTier.L1


def test_l1_capabilities():
    """Test L1 has only observation recording capability / 测试 L1 仅有观察记录能力"""
    caps = TIER_CAPABILITIES[LearningTier.L1]
    assert caps.can_record_observations is True
    assert caps.can_discover_patterns is False
    assert caps.can_generate_hypotheses is False
    assert caps.can_design_experiments is False
    assert caps.can_evolve_strategies is False
    assert caps.can_auto_deploy_to_paper is True  # L1 now allows auto-deploy to paper
    assert caps.can_optimize_learning_pipeline is False
    # All tiers cannot modify live config per EX-05 §8.2
    assert caps.can_modify_live_config is False


def test_l2_capabilities():
    """Test L2 adds pattern discovery / 测试 L2 添加模式发现能力"""
    caps = TIER_CAPABILITIES[LearningTier.L2]
    assert caps.can_record_observations is True
    assert caps.can_discover_patterns is True
    assert caps.can_generate_hypotheses is False
    assert caps.can_design_experiments is False
    assert caps.can_optimize_learning_pipeline is False


def test_l3_capabilities():
    """Test L3 adds hypothesis and experiment design / 测试 L3 添加假说和实验设计能力"""
    caps = TIER_CAPABILITIES[LearningTier.L3]
    assert caps.can_discover_patterns is True
    assert caps.can_generate_hypotheses is True
    assert caps.can_design_experiments is True
    assert caps.can_auto_deploy_to_paper is True
    assert caps.can_evolve_strategies is False


def test_l4_capabilities():
    """Test L4 adds strategy evolution / 测试 L4 添加策略演进能力"""
    caps = TIER_CAPABILITIES[LearningTier.L4]
    assert caps.can_evolve_strategies is True
    assert caps.can_propose_strategy_variants is True
    assert caps.can_propose_transfers is True
    assert caps.can_predict_regime_transition is True
    assert caps.can_optimize_learning_pipeline is False


def test_l5_capabilities():
    """Test L5 adds meta-learning / 测试 L5 添加元学习能力"""
    caps = TIER_CAPABILITIES[LearningTier.L5]
    assert caps.can_optimize_learning_pipeline is True


def test_no_tier_can_modify_live_config(gate):
    """Test that no tier can modify live config per EX-05 §8.2 / 根据 EX-05 §8.2，测试没有等级可以修改实时配置"""
    for tier in [LearningTier.L1, LearningTier.L2, LearningTier.L3, LearningTier.L4, LearningTier.L5]:
        # Simulate promoting to tier (for capability check)
        gate._state.current_tier = tier
        assert gate.can_modify_live_config() is False


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Metrics Update / 指标更新
# ═══════════════════════════════════════════════════════════════════════════════

def test_update_metrics_observation_count(gate):
    """Test updating observation count / 测试更新观察计数"""
    gate.update_metrics(observation_count=100)
    state = gate.state
    assert state.observation_count == 100


def test_update_metrics_win_rate(gate):
    """Test updating win rate / 测试更新胜率"""
    gate.update_metrics(win_rate=0.25)
    state = gate.state
    assert state.win_rate == 0.25


def test_update_metrics_multiple(gate):
    """Test updating multiple metrics at once / 测试同时更新多个指标"""
    gate.update_metrics(
        observation_count=500,
        win_rate=0.22,
        confirmed_patterns=3,
        validated_hypotheses=2,
        experiment_roi=0.05,
    )
    state = gate.state
    assert state.observation_count == 500
    assert state.win_rate == 0.22
    assert state.confirmed_patterns == 3
    assert state.validated_hypotheses == 2
    assert state.experiment_roi == 0.05


def test_update_operational_time(gate):
    """Test updating operational time / 测试更新运营时间"""
    gate.update_operational_time(180)
    state = gate.state
    assert state.days_operational == 180


# ═══════════════════════════════════════════════════════════════════════════════
# Test: L1 → L2 Transition (Pattern Discovery) / L1 → L2 转换（模式发现）
# ═══════════════════════════════════════════════════════════════════════════════

def test_l1_to_l2_insufficient_observations(gate):
    """Test L1→L2 fails with < 500 observations / 测试 L1→L2 在 < 500 观察时失败"""
    gate.update_metrics(observation_count=499, win_rate=0.25)
    eligible, reasons = gate.check_tier_eligibility(LearningTier.L2)
    assert eligible is False
    assert any("insufficient_observations" in r for r in reasons)


def test_l1_to_l2_low_win_rate(gate):
    """Test L1→L2 fails with win_rate < 20% / 测试 L1→L2 在胜率 < 20% 时失败"""
    gate.update_metrics(observation_count=500, win_rate=0.19)
    eligible, reasons = gate.check_tier_eligibility(LearningTier.L2)
    assert eligible is False
    assert any("low_win_rate" in r for r in reasons)


def test_l1_to_l2_both_gates_fail(gate):
    """Test L1→L2 fails when both gates fail / 测试 L1→L2 在两个门都失败时失败"""
    gate.update_metrics(observation_count=400, win_rate=0.15)
    eligible, reasons = gate.check_tier_eligibility(LearningTier.L2)
    assert eligible is False
    assert len(reasons) >= 2


def test_l1_to_l2_both_gates_pass(gate):
    """Test L1→L2 succeeds when both gates pass / 测试 L1→L2 在两个门都通过时成功"""
    gate.update_metrics(observation_count=500, win_rate=0.20)
    eligible, reasons = gate.check_tier_eligibility(LearningTier.L2)
    assert eligible is True


def test_l1_to_l2_promotion_succeeds(gate):
    """Test L1→L2 promotion actually changes tier / 测试 L1→L2 晋升确实改变等级"""
    gate.update_metrics(observation_count=500, win_rate=0.21)
    result = gate.promote_tier(LearningTier.L2, reason="Pattern discovery capability unlocked")
    assert result is True
    assert gate.current_tier == LearningTier.L2


def test_l1_to_l2_audit_emitted(gate_with_audit):
    """Test L1→L2 promotion emits audit callback / 测试 L1→L2 晋升发出审计回调"""
    gate, audit_log = gate_with_audit
    gate.update_metrics(observation_count=500, win_rate=0.21)
    gate.promote_tier(LearningTier.L2)
    assert len(audit_log) == 1
    record = audit_log[0]
    assert record["previous_tier"] == "L1"
    assert record["next_tier"] == "L2"
    assert record["trigger_event"] == "auto_promote_l1_to_l2"


# ═══════════════════════════════════════════════════════════════════════════════
# Test: L2 → L3 Transition (Hypothesis & Experiment) / L2 → L3 转换（假说与实验）
# ═══════════════════════════════════════════════════════════════════════════════

def test_l2_to_l3_gate_requires_l2_age(gate):
    """Test L3 requires L2 to have run 2+ weeks / 测试 L3 需要 L2 运行 2+ 周"""
    gate._state.current_tier = LearningTier.L2
    gate._l2_start_time_ms = int(time.time() * 1000)  # Just started
    gate.update_metrics(confirmed_patterns=3)
    eligible, reasons = gate.check_tier_eligibility(LearningTier.L3)
    assert eligible is False
    assert any("l2_too_new" in r for r in reasons)


def test_l2_to_l3_gate_requires_confirmed_patterns(gate):
    """Test L3 requires 3+ confirmed patterns / 测试 L3 需要 3+ 已确认模式"""
    gate._state.current_tier = LearningTier.L2
    # Simulate L2 started 2+ weeks ago
    gate._l2_start_time_ms = int(time.time() * 1000) - (15 * 24 * 60 * 60 * 1000)
    gate.update_metrics(confirmed_patterns=2)  # Only 2
    eligible, reasons = gate.check_tier_eligibility(LearningTier.L3)
    assert eligible is False
    assert any("insufficient_patterns" in r for r in reasons)


def test_l2_to_l3_both_gates_pass(gate):
    """Test L3 unlocks when both gates pass / 测试 L3 在两个门都通过时解锁"""
    gate._state.current_tier = LearningTier.L2
    gate._l2_start_time_ms = int(time.time() * 1000) - (15 * 24 * 60 * 60 * 1000)
    gate.update_metrics(confirmed_patterns=3)
    eligible, reasons = gate.check_tier_eligibility(LearningTier.L3)
    assert eligible is True


def test_l2_to_l3_promotion_succeeds(gate):
    """Test L2→L3 promotion succeeds / 测试 L2→L3 晋升成功"""
    gate._state.current_tier = LearningTier.L2
    gate._l2_start_time_ms = int(time.time() * 1000) - (15 * 24 * 60 * 60 * 1000)
    gate.update_metrics(confirmed_patterns=3)
    result = gate.promote_tier(LearningTier.L3)
    assert result is True
    assert gate.current_tier == LearningTier.L3


# ═══════════════════════════════════════════════════════════════════════════════
# Test: L3 → L4 Transition (Strategy Evolution) / L3 → L4 转换（策略演进）
# ═══════════════════════════════════════════════════════════════════════════════

def test_l3_to_l4_insufficient_hypotheses(gate):
    """Test L4 requires 3+ validated hypotheses / 测试 L4 需要 3+ 已验证假说"""
    gate._state.current_tier = LearningTier.L3
    gate.update_metrics(validated_hypotheses=2, experiment_roi=0.1)
    eligible, reasons = gate.check_tier_eligibility(LearningTier.L4)
    assert eligible is False
    assert any("insufficient_hypotheses" in r for r in reasons)


def test_l3_to_l4_negative_roi(gate):
    """Test L4 requires positive ROI / 测试 L4 需要正 ROI"""
    gate._state.current_tier = LearningTier.L3
    gate.update_metrics(validated_hypotheses=3, experiment_roi=-0.05)
    eligible, reasons = gate.check_tier_eligibility(LearningTier.L4)
    assert eligible is False
    assert any("negative_roi" in r for r in reasons)


def test_l3_to_l4_zero_roi_passes(gate):
    """Test L4 accepts zero ROI (break-even) / 测试 L4 接受零 ROI（收支平衡）"""
    gate._state.current_tier = LearningTier.L3
    gate.update_metrics(validated_hypotheses=3, experiment_roi=0.0)
    eligible, reasons = gate.check_tier_eligibility(LearningTier.L4)
    assert eligible is True


def test_l3_to_l4_both_gates_pass(gate):
    """Test L4 unlocks when both gates pass / 测试 L4 在两个门都通过时解锁"""
    gate._state.current_tier = LearningTier.L3
    gate.update_metrics(validated_hypotheses=3, experiment_roi=0.1)
    eligible, reasons = gate.check_tier_eligibility(LearningTier.L4)
    assert eligible is True


def test_l3_to_l4_promotion_succeeds(gate):
    """Test L3→L4 promotion succeeds / 测试 L3→L4 晋升成功"""
    gate._state.current_tier = LearningTier.L3
    gate.update_metrics(validated_hypotheses=3, experiment_roi=0.1)
    result = gate.promote_tier(LearningTier.L4)
    assert result is True
    assert gate.current_tier == LearningTier.L4


# ═══════════════════════════════════════════════════════════════════════════════
# Test: L4 → L5 Transition (Meta-Learning) / L4 → L5 转换（元学习）
# ═══════════════════════════════════════════════════════════════════════════════

def test_l4_to_l5_insufficient_operational_time(gate):
    """Test L5 requires 6+ months operational time / 测试 L5 需要 6+ 月运营时间"""
    gate._state.current_tier = LearningTier.L4
    gate.update_operational_time(179)  # One day short
    gate.update_metrics(sustained_positive_live_days=30)
    eligible, reasons = gate.check_tier_eligibility(LearningTier.L5)
    assert eligible is False
    assert any("insufficient_operational_time" in r for r in reasons)


def test_l4_to_l5_insufficient_positive_live_days(gate):
    """Test L5 requires 30+ sustained positive live days / 测试 L5 需要 30+ 持续正实绩日"""
    gate._state.current_tier = LearningTier.L4
    gate.update_operational_time(180)
    gate.update_metrics(sustained_positive_live_days=29)  # One day short
    eligible, reasons = gate.check_tier_eligibility(LearningTier.L5)
    assert eligible is False
    assert any("insufficient_positive_live_days" in r for r in reasons)


def test_l4_to_l5_requires_operator_approval(gate):
    """Test L5 requires Operator approval (cannot auto-promote) / 测试 L5 需要操作员批准（无法自动晋升）"""
    gate._state.current_tier = LearningTier.L4
    gate.update_operational_time(180)
    gate.update_metrics(sustained_positive_live_days=30)
    # Even though metrics pass, L5 requires explicit Operator approval
    result = gate.promote_tier(LearningTier.L5)
    assert result is False  # Should fail without approved_by


def test_l4_to_l5_operator_approved_succeeds(gate):
    """Test L4→L5 succeeds with Operator approval / 测试 L4→L5 在操作员批准时成功"""
    gate._state.current_tier = LearningTier.L4
    gate.update_operational_time(180)
    gate.update_metrics(sustained_positive_live_days=30)
    result = gate.promote_tier(
        LearningTier.L5,
        initiator="Operator",
        approved_by="nancun@openclaw.dev"
    )
    assert result is True
    assert gate.current_tier == LearningTier.L5


def test_l4_to_l5_audit_includes_approval(gate_with_audit):
    """Test L4→L5 audit record includes approver / 测试 L4→L5 审计记录包括批准者"""
    gate, audit_log = gate_with_audit
    gate._state.current_tier = LearningTier.L4
    gate.update_operational_time(180)
    gate.update_metrics(sustained_positive_live_days=30)
    gate.promote_tier(
        LearningTier.L5,
        initiator="Operator",
        approved_by="nancun@openclaw.dev"
    )
    assert len(audit_log) == 1
    record = audit_log[0]
    assert record["approved_by"] == "nancun@openclaw.dev"


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Sequential Promotion Requirement / 顺序晋升要求
# ═══════════════════════════════════════════════════════════════════════════════

def test_cannot_skip_tiers(gate):
    """Test that tiers cannot be skipped (except via Operator override) / 测试等级不能跳过（除了通过操作员覆盖）"""
    gate._state.current_tier = LearningTier.L1
    # Try to jump directly to L3
    gate.update_metrics(
        observation_count=500,
        win_rate=0.21,
        confirmed_patterns=3,
    )
    result = gate.promote_tier(LearningTier.L3)
    assert result is False
    assert gate.current_tier == LearningTier.L1


def test_operator_can_override_sequential_requirement(gate):
    """Test Operator can override sequential requirement for L5 / 测试操作员可以覆盖 L5 的顺序要求"""
    # Special case: L5 from L4 requires Operator override
    gate._state.current_tier = LearningTier.L4
    gate.update_operational_time(180)
    gate.update_metrics(sustained_positive_live_days=30)
    result = gate.promote_tier(
        LearningTier.L5,
        initiator="Operator",
        approved_by="nancun@openclaw.dev"
    )
    assert result is True


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Audit Trail / 审计追踪
# ═══════════════════════════════════════════════════════════════════════════════

def test_promotion_recorded_in_history(gate_with_audit):
    """Test that promotions are recorded in history / 测试晋升被记录在历史中"""
    gate, audit_log = gate_with_audit
    gate.update_metrics(observation_count=500, win_rate=0.21)
    gate.promote_tier(LearningTier.L2, reason="Test promotion")

    state = gate.state
    assert len(state.promotions) == 1
    assert state.promotions[0]["previous_tier"] == "L1"
    assert state.promotions[0]["next_tier"] == "L2"


def test_state_returns_isolated_promotion_snapshot(gate_with_audit):
    gate, audit_log = gate_with_audit
    gate.update_metrics(observation_count=500, win_rate=0.21)
    gate.promote_tier(LearningTier.L2, reason="Test promotion")

    state = gate.state
    state.promotions[0]["next_tier"] = "MUTATED"

    original = gate.state
    assert original.promotions[0]["next_tier"] == "L2"


def test_multiple_promotions_in_audit_trail(gate_with_audit):
    """Test multiple promotions are tracked in order / 测试多个晋升按顺序被追踪"""
    gate, audit_log = gate_with_audit

    # L1 → L2
    gate.update_metrics(observation_count=500, win_rate=0.21)
    gate.promote_tier(LearningTier.L2)

    # L2 → L3
    gate._l2_start_time_ms = int(time.time() * 1000) - (15 * 24 * 60 * 60 * 1000)
    gate.update_metrics(confirmed_patterns=3)
    gate.promote_tier(LearningTier.L3)

    state = gate.state
    assert len(state.promotions) == 2
    assert state.promotions[0]["next_tier"] == "L2"
    assert state.promotions[1]["next_tier"] == "L3"


def test_audit_record_contains_metrics_snapshot(gate_with_audit):
    """Test audit record includes metrics snapshot / 测试审计记录包括指标快照"""
    gate, audit_log = gate_with_audit
    gate.update_metrics(
        observation_count=500,
        win_rate=0.25,
        confirmed_patterns=2,
        validated_hypotheses=1,
    )
    gate.promote_tier(LearningTier.L2)

    record = audit_log[0]
    snapshot = record["metrics_snapshot"]
    assert snapshot["observation_count"] == 500
    assert snapshot["win_rate"] == 0.25


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Thread Safety / 线程安全
# ═══════════════════════════════════════════════════════════════════════════════

def test_thread_safe_concurrent_metrics_update(gate):
    """Test metrics can be safely updated from multiple threads / 测试指标可以安全地从多个线程更新"""
    results = []

    def update_thread(idx):
        for i in range(100):
            gate.update_metrics(observation_count=idx * 100 + i)
            results.append((idx, gate.state.observation_count))

    threads = [threading.Thread(target=update_thread, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Verify no data corruption
    assert len(results) == 500


def test_thread_safe_concurrent_promotion(gate_with_audit):
    """Test promotion is thread-safe (only one succeeds) / 测试晋升是线程安全的（只有一个成功）"""
    gate, audit_log = gate_with_audit
    gate.update_metrics(observation_count=500, win_rate=0.21)

    results = []
    def promote_thread(idx):
        result = gate.promote_tier(LearningTier.L2, reason=f"Thread {idx}")
        results.append(result)

    threads = [threading.Thread(target=promote_thread, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Verify only one promotion succeeded
    assert sum(results) == 1
    assert gate.current_tier == LearningTier.L2


def test_thread_safe_state_read(gate):
    """Test state can be safely read while metrics are updated / 测试状态可以在更新指标时安全读取"""
    states = []

    def read_thread():
        for _ in range(50):
            states.append(gate.state.observation_count)

    def write_thread():
        for i in range(50):
            gate.update_metrics(observation_count=i)

    t_read = threading.Thread(target=read_thread)
    t_write = threading.Thread(target=write_thread)
    t_read.start()
    t_write.start()
    t_read.join()
    t_write.join()

    # Verify no exception and states collected
    assert len(states) == 50


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Capability Checks / 能力检查
# ═══════════════════════════════════════════════════════════════════════════════

def test_l1_can_record_observations(gate):
    """Test L1 can record observations / 测试 L1 可以记录观察"""
    gate._state.current_tier = LearningTier.L1
    assert gate.can_record_observations() is True


def test_l1_cannot_discover_patterns(gate):
    """Test L1 cannot discover patterns / 测试 L1 无法发现模式"""
    gate._state.current_tier = LearningTier.L1
    assert gate.can_discover_patterns() is False


def test_l2_can_discover_patterns(gate):
    """Test L2 can discover patterns / 测试 L2 可以发现模式"""
    gate._state.current_tier = LearningTier.L2
    assert gate.can_discover_patterns() is True


def test_l2_cannot_generate_hypotheses(gate):
    """Test L2 cannot generate hypotheses / 测试 L2 无法生成假说"""
    gate._state.current_tier = LearningTier.L2
    assert gate.can_generate_hypotheses() is False


def test_l3_can_design_experiments(gate):
    """Test L3 can design experiments / 测试 L3 可以设计实验"""
    gate._state.current_tier = LearningTier.L3
    assert gate.can_design_experiments() is True


def test_l3_cannot_evolve_strategies(gate):
    """Test L3 cannot evolve strategies / 测试 L3 无法演进策略"""
    gate._state.current_tier = LearningTier.L3
    assert gate.can_evolve_strategies() is False


def test_l4_can_evolve_strategies(gate):
    """Test L4 can evolve strategies / 测试 L4 可以演进策略"""
    gate._state.current_tier = LearningTier.L4
    assert gate.can_evolve_strategies() is True


def test_l4_can_predict_regime_transition(gate):
    """Test L4 can predict regime transitions / 测试 L4 可以预测制度转换"""
    gate._state.current_tier = LearningTier.L4
    assert gate.can_predict_regime_transition() is True


def test_l5_can_optimize_learning_pipeline(gate):
    """Test L5 can optimize learning pipeline / 测试 L5 可以优化学习管线"""
    gate._state.current_tier = LearningTier.L5
    assert gate.can_optimize_learning_pipeline() is True


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Serialization (Export/Import) / 序列化（导出/导入）
# ═══════════════════════════════════════════════════════════════════════════════

def test_export_state(gate):
    """Test exporting state / 测试导出状态"""
    gate.update_metrics(observation_count=500, win_rate=0.25)
    exported = gate.export_state()

    assert exported["current_tier"] == "L1"
    assert exported["observation_count"] == 500
    assert exported["win_rate"] == 0.25


def test_import_state(gate):
    """Test importing state / 测试导入状态"""
    exported = {
        "current_tier": "L2",
        "observation_count": 600,
        "win_rate": 0.30,
        "confirmed_patterns": 2,
        "validated_hypotheses": 1,
        "experiment_roi": 0.05,
        "days_at_tier": 10,
        "days_operational": 45,
        "sustained_positive_live_days": 10,
        "tier_promoted_at_ms": int(time.time() * 1000),
        "last_promotion_event": "auto_promote_l1_to_l2",
        "last_promotion_initiator": "LearningGate",
        "last_promotion_reason": "Metrics passed gate",
        "promotions": [],
        "version": 2,
        "criteria": {},
    }

    result = gate.import_state(exported)
    assert result is True

    state = gate.state
    assert state.current_tier == LearningTier.L2
    assert state.observation_count == 600
    assert state.win_rate == 0.30


def test_export_import_roundtrip(gate_with_audit):
    """Test export/import roundtrip preserves state / 测试导出/导入往返保留状态"""
    gate, audit_log = gate_with_audit

    # Promote and update metrics
    gate.update_metrics(observation_count=500, win_rate=0.21)
    gate.promote_tier(LearningTier.L2, reason="Pattern discovery unlocked")

    # Export
    exported = gate.export_state()

    # Create new gate and import
    gate2 = LearningTierGate()
    result = gate2.import_state(exported)
    assert result is True

    # Verify state matches
    state1 = gate.state
    state2 = gate2.state
    assert state1.current_tier == state2.current_tier
    assert state1.observation_count == state2.observation_count
    assert state1.win_rate == state2.win_rate
    assert len(state1.promotions) == len(state2.promotions)


def test_import_invalid_tier_name(gate):
    """Test import handles invalid tier name / 测试导入处理无效等级名称"""
    exported = {
        "current_tier": "INVALID",
        "observation_count": 500,
    }
    result = gate.import_state(exported)
    assert result is False


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Edge Cases and Error Handling / 边界情况和错误处理
# ═══════════════════════════════════════════════════════════════════════════════

def test_promotion_without_meeting_criteria_fails(gate):
    """Test promotion fails if criteria not met / 测试如果标准未满足，晋升失败"""
    gate.update_metrics(observation_count=100, win_rate=0.1)
    result = gate.promote_tier(LearningTier.L2)
    assert result is False
    assert gate.current_tier == LearningTier.L1


def test_promotion_with_operator_override(gate):
    """Test Operator can override eligibility (for testing) / 测试操作员可以覆盖资格（用于测试）"""
    gate.update_metrics(observation_count=100, win_rate=0.1)  # Below threshold
    result = gate.promote_tier(
        LearningTier.L2,
        initiator="Operator",
    )
    assert result is True  # Operator override succeeds


def test_empty_state_on_init(gate):
    """Test initial state has zeros / 测试初始状态有零值"""
    state = gate.state
    assert state.observation_count == 0
    assert state.win_rate == 0.0
    assert state.confirmed_patterns == 0
    assert state.validated_hypotheses == 0
    assert state.experiment_roi == 0.0


def test_eligibility_check_does_not_modify_state(gate):
    """Test checking eligibility doesn't change state / 测试检查资格不会改变状态"""
    gate.update_metrics(observation_count=100)
    state_before = gate.state
    gate.check_tier_eligibility(LearningTier.L2)
    state_after = gate.state

    assert state_before.observation_count == state_after.observation_count
    assert state_before.current_tier == state_after.current_tier


def test_get_current_tier_is_read_only(gate):
    """Test get_current_tier is a read-only property / 测试 get_current_tier 是只读属性"""
    tier = gate.get_current_tier()
    assert tier == LearningTier.L1
    # Verify it's the same every call
    assert gate.get_current_tier() == tier


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Custom Criteria / 自定义条件
# ═══════════════════════════════════════════════════════════════════════════════

def test_custom_eligibility_criteria(audit_log):
    """Test gate accepts custom eligibility criteria / 测试门控接受自定义资格条件"""
    custom_criteria = TierEligibilityCriteria(
        l2_min_observations=100,  # Lower threshold
        l2_min_win_rate=0.15,
    )
    gate = LearningTierGate(criteria=custom_criteria)

    gate.update_metrics(observation_count=100, win_rate=0.15)
    eligible, reasons = gate.check_tier_eligibility(LearningTier.L2)
    assert eligible is True


# ═══════════════════════════════════════════════════════════════════════════════
# Integration Tests / 集成测试
# ═══════════════════════════════════════════════════════════════════════════════

def test_full_evolution_l1_to_l5(gate_with_audit):
    """Test full evolution path from L1 to L5 / 测试从 L1 到 L5 的完整演进路径"""
    gate, audit_log = gate_with_audit

    # L1 → L2
    gate.update_metrics(observation_count=500, win_rate=0.21)
    assert gate.promote_tier(LearningTier.L2) is True
    assert gate.current_tier == LearningTier.L2

    # L2 → L3
    gate._l2_start_time_ms = int(time.time() * 1000) - (15 * 24 * 60 * 60 * 1000)
    gate.update_metrics(confirmed_patterns=3)
    assert gate.promote_tier(LearningTier.L3) is True
    assert gate.current_tier == LearningTier.L3

    # L3 → L4
    gate.update_metrics(validated_hypotheses=3, experiment_roi=0.1)
    assert gate.promote_tier(LearningTier.L4) is True
    assert gate.current_tier == LearningTier.L4

    # L4 → L5 (requires Operator approval)
    gate.update_operational_time(180)
    gate.update_metrics(sustained_positive_live_days=30)
    assert gate.promote_tier(
        LearningTier.L5,
        initiator="Operator",
        approved_by="nancun@openclaw.dev"
    ) is True
    assert gate.current_tier == LearningTier.L5

    # Verify audit trail
    assert len(audit_log) == 4
    assert audit_log[0]["next_tier"] == "L2"
    assert audit_log[1]["next_tier"] == "L3"
    assert audit_log[2]["next_tier"] == "L4"
    assert audit_log[3]["next_tier"] == "L5"
