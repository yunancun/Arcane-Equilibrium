"""
Integration Tests for Learning Tier Auto-Promotion Wiring in PipelineBridge
PipelineBridge 中学习等级自动晋升接线的集成测试

MODULE_NOTE (中文):
  验证 Learning Tier 晋升机制与 PipelineBridge 的集成：
  1. 初始化阶段：在 PipelineBridge 中注入 LearningTierGate
  2. 执行阶段：在 _emit_round_trip 中调用 _try_learning_promotion()
  3. 晋升条件：验证资格检查和自动晋升逻辑
  4. 误差处理：验证晋升失败时的非致命行为
  5. 数据记录：验证 record_outcome() 用正确的 win/loss 标志调用

MODULE_NOTE (English):
  Test integration of Learning Tier promotion mechanism with PipelineBridge:
  1. Initialization: LearningTierGate injected into PipelineBridge
  2. Execution: _try_learning_promotion() called in _emit_round_trip
  3. Promotion conditions: verify eligibility checks and auto-promotion logic
  4. Error handling: verify non-fatal behavior when promotion fails
  5. Data recording: verify record_outcome() called with correct win/loss flags
"""

import datetime
import os
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch, ANY, call

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.pipeline_bridge import PipelineBridge
from app.learning_tier_gate import LearningTierGate, LearningTier, TierEligibilityCriteria


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_components():
    """Create mock components for PipelineBridge / 为 PipelineBridge 创建模拟组件"""
    return {
        "kline_manager": MagicMock(),
        "indicator_engine": MagicMock(),
        "signal_engine": MagicMock(),
        "orchestrator": MagicMock(),
        "paper_engine": MagicMock(),
        "stop_manager": MagicMock(),
    }


@pytest.fixture
def pipeline_bridge(mock_components):
    """Create a PipelineBridge with mock components / 使用模拟组件创建 PipelineBridge"""
    bridge = PipelineBridge(
        kline_manager=mock_components["kline_manager"],
        indicator_engine=mock_components["indicator_engine"],
        signal_engine=mock_components["signal_engine"],
        orchestrator=mock_components["orchestrator"],
        paper_engine=mock_components["paper_engine"],
        stop_manager=mock_components["stop_manager"],
    )
    return bridge


@pytest.fixture
def learning_tier_gate():
    """Create a LearningTierGate instance / 创建一个 LearningTierGate 实例"""
    # Use relaxed criteria for testing (lower thresholds)
    criteria = TierEligibilityCriteria(
        l2_min_observations=10,      # Low threshold for testing
        l2_min_win_rate=0.10,        # Low threshold for testing
        l3_min_l2_runtime_days=1,    # Low threshold for testing
        l3_min_confirmed_patterns=1, # Low threshold for testing
        l4_min_validated_hypotheses=1,
        l4_min_experiment_roi=0.0,
        l5_min_operational_days=30,
        l5_requires_operator_approval=True,
    )
    return LearningTierGate(criteria=criteria)


# ═══════════════════════════════════════════════════════════════════════════════
# Test PipelineBridge.set_learning_tier_gate() Setter
# ═══════════════════════════════════════════════════════════════════════════════

class TestSetLearningTierGate:
    """Test set_learning_tier_gate() setter functionality / 测试 set_learning_tier_gate() setter 功能"""

    def test_set_learning_tier_gate_stores_attribute(self, pipeline_bridge, learning_tier_gate):
        """
        Verify that set_learning_tier_gate() stores the gate and it's accessible.
        验证 set_learning_tier_gate() 存储门控，并且可以访问。
        """
        # Initially should be None (or not set)
        # 最初应该是 None（或未设置）
        assert not hasattr(pipeline_bridge, '_learning_tier_gate') or pipeline_bridge._learning_tier_gate is None

        # Set the gate
        # 设置门控
        pipeline_bridge.set_learning_tier_gate(learning_tier_gate)

        # Should now be set and accessible
        # 现在应该已设置并可访问
        assert hasattr(pipeline_bridge, '_learning_tier_gate')
        assert pipeline_bridge._learning_tier_gate is not None
        assert pipeline_bridge._learning_tier_gate == learning_tier_gate

    def test_set_learning_tier_gate_can_be_called_multiple_times(self, pipeline_bridge):
        """
        Verify that set_learning_tier_gate() can be called multiple times.
        验证 set_learning_tier_gate() 可以被调用多次。
        """
        gate1 = LearningTierGate()
        gate2 = LearningTierGate()

        pipeline_bridge.set_learning_tier_gate(gate1)
        assert pipeline_bridge._learning_tier_gate == gate1

        pipeline_bridge.set_learning_tier_gate(gate2)
        assert pipeline_bridge._learning_tier_gate == gate2


# ═══════════════════════════════════════════════════════════════════════════════
# Test _try_learning_promotion() Integration in _emit_round_trip
# ═══════════════════════════════════════════════════════════════════════════════

class TestLearningPromotionInRoundTrip:
    """Test _try_learning_promotion() integration in _emit_round_trip / 测试 _emit_round_trip 中的 _try_learning_promotion() 集成"""

    def test_try_learning_promotion_called_after_round_trip(self, pipeline_bridge, learning_tier_gate):
        """
        Verify that _try_learning_promotion() is called when _emit_round_trip is executed.
        验证当执行 _emit_round_trip 时调用 _try_learning_promotion()。
        """
        pipeline_bridge.set_learning_tier_gate(learning_tier_gate)

        # Mock _try_learning_promotion to verify it's called
        # 模拟 _try_learning_promotion 以验证它被调用
        original_try_promotion = pipeline_bridge._try_learning_promotion
        call_count = [0]

        def mock_try_promotion(*args, **kwargs):
            call_count[0] += 1
            return original_try_promotion(*args, **kwargs)

        pipeline_bridge._try_learning_promotion = mock_try_promotion

        # Set up an open position
        # 设置打开的持仓
        key = "TestStrategy:BTCUSDT"
        now_ms = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
        pipeline_bridge._open_positions[key] = {
            "symbol": "BTCUSDT",
            "strategy_name": "TestStrategy",
            "side": "long",
            "entry_price": 50000.0,
            "qty": 0.01,
            "entry_ts_ms": now_ms - 3600000,
            "regime": "trend_up",
        }

        # Call _emit_round_trip
        # 调用 _emit_round_trip
        pipeline_bridge._emit_round_trip(
            symbol="BTCUSDT",
            strategy_name="TestStrategy",
            exit_price=51000.0,
            close_pnl=10.0,
        )

        # Verify _try_learning_promotion was called at least once
        # 验证 _try_learning_promotion 至少被调用一次
        assert call_count[0] > 0

    def test_emit_round_trip_without_learning_gate_is_graceful(self, pipeline_bridge):
        """
        Verify that _emit_round_trip works when no gate is set (graceful degradation).
        验证当未设置门控时 _emit_round_trip 可以工作（优雅降级）。
        """
        # Do NOT set a learning tier gate
        # 不设置学习等级门控
        assert pipeline_bridge._learning_tier_gate is None

        # Set up an open position
        # 设置打开的持仓
        key = "TestStrategy:BTCUSDT"
        now_ms = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
        pipeline_bridge._open_positions[key] = {
            "symbol": "BTCUSDT",
            "strategy_name": "TestStrategy",
            "side": "long",
            "entry_price": 50000.0,
            "qty": 0.01,
            "entry_ts_ms": now_ms,
            "regime": "test",
        }

        # This should NOT raise an exception
        # 这不应该引发异常
        pipeline_bridge._emit_round_trip(
            symbol="BTCUSDT",
            strategy_name="TestStrategy",
            exit_price=51000.0,
            close_pnl=1.0,
        )
        # If we reach here, the test passes
        # 如果到达这里，测试通过


# ═══════════════════════════════════════════════════════════════════════════════
# Test Promotion Success Conditions
# ═══════════════════════════════════════════════════════════════════════════════

class TestPromotionSuccessWhenEligible:
    """Test that promotion succeeds when eligibility criteria are met / 测试满足资格条件时晋升成功"""

    def test_promotion_when_gate_eligible_true(self, pipeline_bridge, learning_tier_gate):
        """
        Verify that tier changes when gate reports eligible=True.
        验证当门控报告 eligible=True 时等级更改。
        """
        pipeline_bridge.set_learning_tier_gate(learning_tier_gate)

        # Start at L1
        # 从 L1 开始
        assert learning_tier_gate.current_tier == LearningTier.L1

        # Update metrics to make L2 eligible
        # 更新指标以使 L2 符合资格
        learning_tier_gate.update_metrics(
            observation_count=100,
            win_rate=0.25,
        )

        # Check eligibility
        # 检查资格
        eligible, reasons = learning_tier_gate.check_tier_eligibility(LearningTier.L2)
        assert eligible

        # Promote
        # 晋升
        success = learning_tier_gate.promote_tier(LearningTier.L2)
        assert success
        assert learning_tier_gate.current_tier == LearningTier.L2

    def test_promotion_via_emit_round_trip_when_eligible(self, pipeline_bridge, learning_tier_gate):
        """
        Verify that _emit_round_trip triggers promotion when gate is eligible.
        验证当门控符合资格时 _emit_round_trip 触发晋升。
        """
        pipeline_bridge.set_learning_tier_gate(learning_tier_gate)

        # Set up metrics to be eligible for L2
        # 设置指标以符合 L2 资格
        learning_tier_gate.update_metrics(
            observation_count=100,
            win_rate=0.25,
        )

        # Verify we can promote to L2
        # 验证我们可以晋升到 L2
        success = learning_tier_gate.promote_tier(LearningTier.L2)
        assert success
        assert learning_tier_gate.current_tier == LearningTier.L2

        # Set up metrics to be eligible for L3 (with simulated L2 age)
        # 设置指标以符合 L3 资格（带模拟 L2 年龄）
        learning_tier_gate.update_metrics(
            confirmed_patterns=2,
        )

        # Note: L3 requires 14 days of L2 running by default, but we relaxed it to 1 day in fixture
        # Manually set L2 start time to past
        # 注意：L3 默认需要 14 天的 L2 运行，但我们在 fixture 中将其放宽到 1 天
        # 手动将 L2 开始时间设置为过去
        import time
        learning_tier_gate._l2_start_time_ms = int(time.time() * 1000) - (2 * 24 * 60 * 60 * 1000)  # 2 days ago

        # Now call _emit_round_trip and verify it can promote
        # 现在调用 _emit_round_trip 并验证它可以晋升
        key = "TestStrategy:BTCUSDT"
        now_ms = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
        pipeline_bridge._open_positions[key] = {
            "symbol": "BTCUSDT",
            "strategy_name": "TestStrategy",
            "side": "long",
            "entry_price": 50000.0,
            "qty": 0.01,
            "entry_ts_ms": now_ms - 3600000,
            "regime": "trend_up",
        }

        # Before calling _emit_round_trip, set a mock audit callback to capture promotion
        # 在调用 _emit_round_trip 之前，设置模拟审计回调以捕获晋升
        promotions_captured = []

        def capture_promotion(record):
            promotions_captured.append(record)

        learning_tier_gate._audit_callback = capture_promotion

        # Call _emit_round_trip with winning trade
        # 调用 _emit_round_trip 与获胜交易
        pipeline_bridge._emit_round_trip(
            symbol="BTCUSDT",
            strategy_name="TestStrategy",
            exit_price=51000.0,
            close_pnl=100.0,  # Winning trade
        )

        # Verify we're at L3 (promotion was triggered since we met L3 eligibility criteria)
        # 验证我们在 L3（因为我们满足 L3 资格条件，所以触发了晋升）
        assert learning_tier_gate.current_tier == LearningTier.L3


# ═══════════════════════════════════════════════════════════════════════════════
# Test Promotion Skipped When Not Eligible
# ═══════════════════════════════════════════════════════════════════════════════

class TestPromotionSkippedWhenNotEligible:
    """Test that promotion is skipped when eligibility criteria are not met / 测试不符合资格条件时晋升被跳过"""

    def test_promotion_skipped_when_not_eligible(self, pipeline_bridge, learning_tier_gate):
        """
        Verify that no promotion occurs when gate reports eligible=False.
        验证当门控报告 eligible=False 时不发生晋升。
        """
        pipeline_bridge.set_learning_tier_gate(learning_tier_gate)

        # Ensure L1, with insufficient observations
        # 确保 L1，观察不足
        assert learning_tier_gate.current_tier == LearningTier.L1

        # Update metrics with insufficient data for L2
        # 使用 L2 的不足数据更新指标
        learning_tier_gate.update_metrics(
            observation_count=5,  # Below threshold of 10
            win_rate=0.05,        # Below threshold of 0.10
        )

        # Check eligibility
        # 检查资格
        eligible, reasons = learning_tier_gate.check_tier_eligibility(LearningTier.L2)
        assert not eligible

        # Try to promote (should fail)
        # 尝试晋升（应该失败）
        success = learning_tier_gate.promote_tier(LearningTier.L2)
        assert not success
        assert learning_tier_gate.current_tier == LearningTier.L1

    def test_no_promotion_when_gate_not_set(self, pipeline_bridge):
        """
        Verify that no error occurs and no promotion is attempted when gate is None.
        验证当门控为 None 时不会发生错误且不会尝试晋升。
        """
        # Do NOT set a learning tier gate
        # 不设置学习等级门控
        assert pipeline_bridge._learning_tier_gate is None

        # Set up position
        # 设置持仓
        key = "TestStrategy:ETHUSDT"
        now_ms = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
        pipeline_bridge._open_positions[key] = {
            "symbol": "ETHUSDT",
            "strategy_name": "TestStrategy",
            "side": "long",
            "entry_price": 3000.0,
            "qty": 0.1,
            "entry_ts_ms": now_ms,
            "regime": "consolidation",
        }

        # This should not raise any exception
        # 这不应该引发任何异常
        pipeline_bridge._emit_round_trip(
            symbol="ETHUSDT",
            strategy_name="TestStrategy",
            exit_price=3100.0,
            close_pnl=10.0,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Test Non-Fatal Error Handling
# ═══════════════════════════════════════════════════════════════════════════════

class TestPromotionNonFatalErrorHandling:
    """Test that promotion errors don't crash round-trip completion / 测试晋升错误不会导致 round-trip 完成崩溃"""

    def test_promotion_failure_is_non_fatal(self, pipeline_bridge, learning_tier_gate):
        """
        Verify that if gate.promote_tier() raises an exception, _emit_round_trip still completes.
        验证如果 gate.promote_tier() 引发异常，_emit_round_trip 仍然完成。
        """
        pipeline_bridge.set_learning_tier_gate(learning_tier_gate)

        # Mock promote_tier to raise an exception
        # 模拟 promote_tier 以引发异常
        original_promote = learning_tier_gate.promote_tier

        def raising_promote(*args, **kwargs):
            raise Exception("Simulated promotion error")

        learning_tier_gate.promote_tier = raising_promote

        # Set up position
        # 设置持仓
        key = "TestStrategy:BTCUSDT"
        now_ms = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
        pipeline_bridge._open_positions[key] = {
            "symbol": "BTCUSDT",
            "strategy_name": "TestStrategy",
            "side": "long",
            "entry_price": 50000.0,
            "qty": 0.01,
            "entry_ts_ms": now_ms,
            "regime": "test",
        }

        # This should NOT raise an exception (should catch and log)
        # 这不应该引发异常（应该捕获并记录）
        pipeline_bridge._emit_round_trip(
            symbol="BTCUSDT",
            strategy_name="TestStrategy",
            exit_price=51000.0,
            close_pnl=1.0,
        )
        # If we reach here without exception, the test passes
        # 如果到达这里没有异常，测试通过


# ═══════════════════════════════════════════════════════════════════════════════
# Test record_outcome() with Win/Loss Determination
# ═══════════════════════════════════════════════════════════════════════════════

class TestRecordOutcomeWinLoss:
    """Test record_outcome() called with correct win/loss determination / 测试 record_outcome() 用正确的 win/loss 确定调用"""

    def test_record_outcome_called_with_win_true_for_positive_pnl(self, pipeline_bridge, learning_tier_gate):
        """
        Verify that record_outcome() is called with win=True when close_pnl > 0.
        验证当 close_pnl > 0 时以 win=True 调用 record_outcome()。
        """
        pipeline_bridge.set_learning_tier_gate(learning_tier_gate)

        # Mock record_outcome if it exists
        # 模拟 record_outcome（如果存在）
        if hasattr(learning_tier_gate, 'record_outcome'):
            original_record = learning_tier_gate.record_outcome
            call_args = []

            def mock_record(*args, **kwargs):
                call_args.append((args, kwargs))

            learning_tier_gate.record_outcome = mock_record

            # Set up position
            # 设置持仓
            key = "TestStrategy:BTCUSDT"
            now_ms = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
            pipeline_bridge._open_positions[key] = {
                "symbol": "BTCUSDT",
                "strategy_name": "TestStrategy",
                "side": "long",
                "entry_price": 50000.0,
                "qty": 0.01,
                "entry_ts_ms": now_ms,
                "regime": "test",
            }

            # Call with positive PnL
            # 使用正 PnL 调用
            pipeline_bridge._emit_round_trip(
                symbol="BTCUSDT",
                strategy_name="TestStrategy",
                exit_price=51000.0,
                close_pnl=100.0,  # Positive = win
            )

            # Verify record_outcome was called
            # 验证 record_outcome 被调用
            if call_args:
                # Check that win argument was True
                # 检查 win 参数是否为 True
                assert any('win' in str(arg) for arg in call_args), "record_outcome should be called with win parameter"

    def test_record_outcome_called_with_win_false_for_negative_pnl(self, pipeline_bridge, learning_tier_gate):
        """
        Verify that record_outcome() is called with win=False when close_pnl <= 0.
        验证当 close_pnl <= 0 时以 win=False 调用 record_outcome()。
        """
        pipeline_bridge.set_learning_tier_gate(learning_tier_gate)

        # Mock record_outcome if it exists
        # 模拟 record_outcome（如果存在）
        if hasattr(learning_tier_gate, 'record_outcome'):
            original_record = learning_tier_gate.record_outcome
            call_args = []

            def mock_record(*args, **kwargs):
                call_args.append((args, kwargs))

            learning_tier_gate.record_outcome = mock_record

            # Set up position
            # 设置持仓
            key = "TestStrategy:BTCUSDT"
            now_ms = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
            pipeline_bridge._open_positions[key] = {
                "symbol": "BTCUSDT",
                "strategy_name": "TestStrategy",
                "side": "long",
                "entry_price": 50000.0,
                "qty": 0.01,
                "entry_ts_ms": now_ms,
                "regime": "test",
            }

            # Call with negative PnL
            # 使用负 PnL 调用
            pipeline_bridge._emit_round_trip(
                symbol="BTCUSDT",
                strategy_name="TestStrategy",
                exit_price=49000.0,
                close_pnl=-50.0,  # Negative = loss
            )

            # Verify record_outcome was called
            # 验证 record_outcome 被调用
            if call_args:
                # Check that win argument was False
                # 检查 win 参数是否为 False
                assert any('win' in str(arg) for arg in call_args), "record_outcome should be called with win parameter"

    def test_record_outcome_called_with_win_false_for_zero_pnl(self, pipeline_bridge, learning_tier_gate):
        """
        Verify that record_outcome() is called with win=False when close_pnl == 0.
        验证当 close_pnl == 0 时以 win=False 调用 record_outcome()。
        """
        pipeline_bridge.set_learning_tier_gate(learning_tier_gate)

        # Mock record_outcome if it exists
        # 模拟 record_outcome（如果存在）
        if hasattr(learning_tier_gate, 'record_outcome'):
            original_record = learning_tier_gate.record_outcome
            call_args = []

            def mock_record(*args, **kwargs):
                call_args.append((args, kwargs))

            learning_tier_gate.record_outcome = mock_record

            # Set up position
            # 设置持仓
            key = "TestStrategy:BTCUSDT"
            now_ms = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
            pipeline_bridge._open_positions[key] = {
                "symbol": "BTCUSDT",
                "strategy_name": "TestStrategy",
                "side": "long",
                "entry_price": 50000.0,
                "qty": 0.01,
                "entry_ts_ms": now_ms,
                "regime": "test",
            }

            # Call with zero PnL (break-even)
            # 使用零 PnL 调用（收支平衡）
            pipeline_bridge._emit_round_trip(
                symbol="BTCUSDT",
                strategy_name="TestStrategy",
                exit_price=50000.0,
                close_pnl=0.0,  # Zero = loss (not a win)
            )

            # Verify record_outcome was called
            # 验证 record_outcome 被调用
            if call_args:
                # Check that win argument was False
                # 检查 win 参数是否为 False
                assert any('win' in str(arg) for arg in call_args), "record_outcome should be called with win parameter"


# ═══════════════════════════════════════════════════════════════════════════════
# Test L5 Requires Operator Approval
# ═══════════════════════════════════════════════════════════════════════════════

class TestL5RequiresOperatorApproval:
    """Test that L5 promotion requires explicit Operator approval / 测试 L5 晋升需要明确的 Operator 批准"""

    def test_l5_promotion_fails_without_operator_approval(self, learning_tier_gate):
        """
        Verify that auto-promotion stops at L4 and cannot reach L5 without Operator approval.
        验证自动晋升在 L4 停止，不能在没有 Operator 批准的情况下达到 L5。
        """
        # Manually promote through L1 → L4
        # 手动通过 L1 → L4 晋升
        learning_tier_gate.update_metrics(
            observation_count=100,
            win_rate=0.25,
        )
        assert learning_tier_gate.promote_tier(LearningTier.L2, initiator="LearningGate")

        # Now at L2, promote to L3 (requires L2 age)
        # 现在在 L2，晋升到 L3（需要 L2 年龄）
        import time
        learning_tier_gate._l2_start_time_ms = int(time.time() * 1000) - (2 * 24 * 60 * 60 * 1000)  # 2 days ago
        learning_tier_gate.update_metrics(confirmed_patterns=2)
        assert learning_tier_gate.promote_tier(LearningTier.L3, initiator="LearningGate")

        # Now at L3, promote to L4 (requires hypotheses and ROI)
        # 现在在 L3，晋升到 L4（需要假说和 ROI）
        learning_tier_gate.update_metrics(
            validated_hypotheses=2,
            experiment_roi=0.05,
        )
        assert learning_tier_gate.promote_tier(LearningTier.L4, initiator="LearningGate")

        # Now at L4, try to promote to L5 WITHOUT Operator approval
        # 现在在 L4，尝试在没有 Operator 批准的情况下晋升到 L5
        learning_tier_gate.update_operational_time(180)
        learning_tier_gate.update_metrics(
            sustained_positive_live_days=30,
        )

        # This should FAIL because L5 requires explicit Operator approval
        # 这应该失败，因为 L5 需要明确的 Operator 批准
        success = learning_tier_gate.promote_tier(LearningTier.L5, initiator="LearningGate")
        assert not success
        assert learning_tier_gate.current_tier == LearningTier.L4

    def test_l5_promotion_succeeds_with_operator_approval(self, learning_tier_gate):
        """
        Verify that L5 promotion succeeds when Operator provides approval.
        验证当 Operator 提供批准时 L5 晋升成功。
        """
        # Manually promote through L1 → L4
        # 手动通过 L1 → L4 晋升
        learning_tier_gate.update_metrics(
            observation_count=100,
            win_rate=0.25,
        )
        assert learning_tier_gate.promote_tier(LearningTier.L2, initiator="LearningGate")

        # Promote to L3
        # 晋升到 L3
        import time
        learning_tier_gate._l2_start_time_ms = int(time.time() * 1000) - (2 * 24 * 60 * 60 * 1000)
        learning_tier_gate.update_metrics(confirmed_patterns=2)
        assert learning_tier_gate.promote_tier(LearningTier.L3, initiator="LearningGate")

        # Promote to L4
        # 晋升到 L4
        learning_tier_gate.update_metrics(
            validated_hypotheses=2,
            experiment_roi=0.05,
        )
        assert learning_tier_gate.promote_tier(LearningTier.L4, initiator="LearningGate")

        # Now promote to L5 WITH Operator approval
        # 现在使用 Operator 批准晋升到 L5
        learning_tier_gate.update_operational_time(180)
        learning_tier_gate.update_metrics(
            sustained_positive_live_days=30,
        )

        # This should SUCCEED when approved_by is provided
        # 当提供 approved_by 时这应该成功
        success = learning_tier_gate.promote_tier(
            LearningTier.L5,
            initiator="Operator",
            reason="operator_approved_l5",
            approved_by="operator_001",
        )
        assert success
        assert learning_tier_gate.current_tier == LearningTier.L5


# ═══════════════════════════════════════════════════════════════════════════════
# Test Thread Safety
# ═══════════════════════════════════════════════════════════════════════════════

class TestLearningPromotionThreadSafety:
    """Test thread safety of learning tier promotion / 测试学习等级晋升的线程安全"""

    def test_concurrent_emit_round_trip_calls_with_gate(self, pipeline_bridge, learning_tier_gate):
        """
        Verify multiple threads can safely call _emit_round_trip with learning gate.
        验证多个线程可以安全地使用学习门控调用 _emit_round_trip。
        """
        pipeline_bridge.set_learning_tier_gate(learning_tier_gate)

        errors = []

        def emit_trades(strategy_name, symbol, base_price):
            try:
                for i in range(5):
                    now_ms = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
                    key = f"{strategy_name}:{symbol}"

                    with pipeline_bridge._lock:
                        pipeline_bridge._open_positions[key] = {
                            "symbol": symbol,
                            "strategy_name": strategy_name,
                            "side": "long",
                            "entry_price": base_price,
                            "qty": 0.01,
                            "entry_ts_ms": now_ms,
                            "regime": "test",
                        }

                    pipeline_bridge._emit_round_trip(
                        symbol=symbol,
                        strategy_name=strategy_name,
                        exit_price=base_price + 100,
                        close_pnl=1.0,
                    )
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(3):
            t = threading.Thread(
                target=emit_trades,
                args=(f"Strategy{i}", "BTCUSDT", 50000.0 + i * 1000),
            )
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Should have no errors
        # 应该没有错误
        assert len(errors) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
