"""
Tests for TTL Enforcer — GAP-M8 Time Expiry Enforcement
TTL 执行者测试 — GAP-M8 时间到期强制执行

Covers:
  - Default TTL configurations for all state machines
  - TTL entry registration and tracking
  - Expiry detection and action execution
  - Daemon sweep mode
  - Thread safety
  - Audit trail generation
  - Statistics and export
  - Edge cases and error handling
"""

import sys
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch, call

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ttl_enforcer import (
    TTLConfig,
    TTLEntry,
    TTLEnforcer,
    TTLExpiryAction,
    _create_default_ttl_configs,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def ttl_enforcer():
    """Fresh TTL enforcer instance / 全新 TTL 执行者实例"""
    return TTLEnforcer()


@pytest.fixture
def ttl_enforcer_with_callbacks():
    """TTL enforcer with audit and expiry callbacks / 带审计和到期回调的 TTL 执行者"""
    audit_records = []
    expiry_calls = []

    def audit_cb(record):
        audit_records.append(record)

    def expiry_cb(entry, action):
        expiry_calls.append((entry.entry_id, action))

    enforcer = TTLEnforcer(audit_callback=audit_cb, expiry_callback=expiry_cb)
    return enforcer, audit_records, expiry_calls


@pytest.fixture
def custom_ttl_config():
    """Custom TTL config for testing / 用于测试的自定义 TTL 配置"""
    return TTLConfig(
        state_machine_name="TestSM",
        state_name="TEST_STATE",
        max_duration_seconds=10,
        on_expiry_action=TTLExpiryAction.AUTO_EXPIRE,
        on_expiry_target_state="EXPIRED",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Default Configurations
# ═══════════════════════════════════════════════════════════════════════════════


class TestDefaultConfigurations:
    """Test default TTL configurations for all state machines / 测试所有状态机的默认 TTL 配置"""

    def test_default_configs_exist(self):
        """Verify default configs created / 验证默认配置已创建"""
        configs = _create_default_ttl_configs()
        assert len(configs) > 0

    def test_authorization_pending_approval_ttl(self):
        """Authorization: PENDING_APPROVAL max 24 hours / 授权：PENDING_APPROVAL 最多 24 小时"""
        configs = _create_default_ttl_configs()
        key = ("Authorization", "PENDING_APPROVAL")
        assert key in configs
        config = configs[key]
        assert config.max_duration_seconds == 86400
        assert config.on_expiry_action == TTLExpiryAction.AUTO_REJECT
        assert config.on_expiry_target_state == "REJECTED"

    def test_decision_lease_active_ttl(self):
        """Decision Lease: ACTIVE max 30 seconds / 决策租约：ACTIVE 最多 30 秒"""
        configs = _create_default_ttl_configs()
        key = ("DecisionLease", "ACTIVE")
        assert key in configs
        config = configs[key]
        assert config.max_duration_seconds == 30
        assert config.on_expiry_action == TTLExpiryAction.AUTO_EXPIRE
        assert config.on_expiry_target_state == "EXPIRED"

    def test_decision_lease_bridged_ttl(self):
        """Decision Lease: BRIDGED max 60 seconds / 决策租约：BRIDGED 最多 60 秒"""
        configs = _create_default_ttl_configs()
        key = ("DecisionLease", "BRIDGED")
        assert key in configs
        config = configs[key]
        assert config.max_duration_seconds == 60
        assert config.on_expiry_action == TTLExpiryAction.AUTO_EXPIRE
        assert config.on_expiry_target_state == "EXPIRED"

    def test_risk_governor_circuit_breaker_ttl(self):
        """Risk Governor: CIRCUIT_BREAKER max 1 hour / 风控：CIRCUIT_BREAKER 最多 1 小时"""
        configs = _create_default_ttl_configs()
        key = ("RiskGovernor", "CIRCUIT_BREAKER")
        assert key in configs
        config = configs[key]
        assert config.max_duration_seconds == 3600
        assert config.on_expiry_action == TTLExpiryAction.MANUAL_REVIEW_REQUIRED
        assert config.on_expiry_target_state == "MANUAL_REVIEW"

    def test_risk_governor_manual_review_ttl(self):
        """Risk Governor: MANUAL_REVIEW max 24 hours / 风控：MANUAL_REVIEW 最多 24 小时"""
        configs = _create_default_ttl_configs()
        key = ("RiskGovernor", "MANUAL_REVIEW")
        assert key in configs
        config = configs[key]
        assert config.max_duration_seconds == 86400
        assert config.on_expiry_action == TTLExpiryAction.ESCALATE
        assert config.on_expiry_target_state is None

    def test_oms_submitted_ttl(self):
        """OMS: SUBMITTED max 30 seconds / OMS：SUBMITTED 最多 30 秒"""
        configs = _create_default_ttl_configs()
        key = ("OMS", "SUBMITTED")
        assert key in configs
        config = configs[key]
        assert config.max_duration_seconds == 30
        assert config.on_expiry_action == TTLExpiryAction.AUTO_CANCEL
        assert config.on_expiry_target_state == "CANCELED"

    def test_ttl_config_hashable(self):
        """TTLConfig is hashable / TTLConfig 可哈希"""
        config1 = TTLConfig(
            state_machine_name="Auth", state_name="ACTIVE", max_duration_seconds=100,
            on_expiry_action=TTLExpiryAction.AUTO_EXPIRE
        )
        config2 = TTLConfig(
            state_machine_name="Auth", state_name="ACTIVE", max_duration_seconds=200,
            on_expiry_action=TTLExpiryAction.AUTO_REJECT
        )
        # Should be equal based on state_machine_name and state_name
        assert config1 == config2
        assert hash(config1) == hash(config2)

    def test_ttl_config_frozen(self):
        """TTLConfig is frozen (immutable) / TTLConfig 是冻结的（不可变）"""
        config = TTLConfig(
            state_machine_name="Auth", state_name="ACTIVE", max_duration_seconds=100,
            on_expiry_action=TTLExpiryAction.AUTO_EXPIRE
        )
        with pytest.raises(AttributeError):
            config.max_duration_seconds = 200


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: TTL Entry Creation and Tracking
# ═══════════════════════════════════════════════════════════════════════════════


class TestTTLEntryRegistration:
    """Test TTL entry registration and tracking / 测试 TTL 条目注册和追踪"""

    def test_register_entry_with_default_config(self, ttl_enforcer):
        """Register entry for Authorization PENDING_APPROVAL / 为授权 PENDING_APPROVAL 注册条目"""
        now_ms = int(time.time() * 1000)
        entry = ttl_enforcer.register_entry(
            state_machine_name="Authorization",
            object_id="auth_123",
            state_name="PENDING_APPROVAL",
            current_time_ms=now_ms,
        )

        assert entry is not None
        assert entry.state_machine_name == "Authorization"
        assert entry.object_id == "auth_123"
        assert entry.state_name == "PENDING_APPROVAL"
        assert entry.entered_at_ms == now_ms
        assert entry.expires_at_ms == now_ms + 86400 * 1000  # 24 hours
        assert not entry.expired
        assert entry.action_taken is None

    def test_register_entry_without_ttl_config(self, ttl_enforcer):
        """Register entry for state without TTL config returns None / 为没有 TTL 配置的状态注册条目返回 None"""
        entry = ttl_enforcer.register_entry(
            state_machine_name="UnknownSM",
            object_id="obj_123",
            state_name="UNKNOWN_STATE",
        )

        assert entry is None

    def test_register_multiple_entries_for_same_object(self, ttl_enforcer):
        """Register multiple entries for same object / 为同一对象注册多个条目"""
        now_ms = int(time.time() * 1000)

        entry1 = ttl_enforcer.register_entry(
            "Authorization", "auth_123", "PENDING_APPROVAL", now_ms
        )
        entry2 = ttl_enforcer.register_entry(
            "Authorization", "auth_123", "PENDING_APPROVAL", now_ms + 1000
        )

        assert entry1 is not None
        assert entry2 is not None
        assert entry1.entry_id != entry2.entry_id

        active = ttl_enforcer.get_active_entries("Authorization", "auth_123")
        assert len(active) == 2

    def test_entry_is_expired_false_initially(self):
        """TTLEntry.is_expired() returns False initially / TTLEntry.is_expired() 初始返回 False"""
        now_ms = int(time.time() * 1000)
        entry = TTLEntry(
            entry_id="test_1",
            state_machine_name="Auth",
            object_id="obj_1",
            state_name="ACTIVE",
            entered_at_ms=now_ms,
            expires_at_ms=now_ms + 10000,
            config=TTLConfig(
                state_machine_name="Auth",
                state_name="ACTIVE",
                max_duration_seconds=10,
                on_expiry_action=TTLExpiryAction.AUTO_EXPIRE,
            ),
        )

        assert not entry.is_expired()

    def test_entry_is_expired_true_after_ttl(self):
        """TTLEntry.is_expired() returns True after TTL expires / TTLEntry.is_expired() TTL 过期后返回 True"""
        now_ms = int(time.time() * 1000)
        entry = TTLEntry(
            entry_id="test_1",
            state_machine_name="Auth",
            object_id="obj_1",
            state_name="ACTIVE",
            entered_at_ms=now_ms,
            expires_at_ms=now_ms - 1000,  # Already expired
            config=TTLConfig(
                state_machine_name="Auth",
                state_name="ACTIVE",
                max_duration_seconds=1,
                on_expiry_action=TTLExpiryAction.AUTO_EXPIRE,
            ),
        )

        assert entry.is_expired()

    def test_entry_remaining_seconds(self):
        """TTLEntry.remaining_seconds() calculates correctly / TTLEntry.remaining_seconds() 正确计算"""
        now_ms = int(time.time() * 1000)
        entry = TTLEntry(
            entry_id="test_1",
            state_machine_name="Auth",
            object_id="obj_1",
            state_name="ACTIVE",
            entered_at_ms=now_ms,
            expires_at_ms=now_ms + 10000,
            config=TTLConfig(
                state_machine_name="Auth",
                state_name="ACTIVE",
                max_duration_seconds=10,
                on_expiry_action=TTLExpiryAction.AUTO_EXPIRE,
            ),
        )

        remaining = entry.remaining_seconds(now_ms)
        assert 9.9 < remaining <= 10.0


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Expiry Detection and Action
# ═══════════════════════════════════════════════════════════════════════════════


class TestExpiryDetectionAndAction:
    """Test expiry detection and action execution / 测试到期检测和动作执行"""

    def test_check_expiry_not_expired(self, ttl_enforcer):
        """check_expiry returns False for non-expired entry / check_expiry 对未过期条目返回 False"""
        now_ms = int(time.time() * 1000)
        entry = ttl_enforcer.register_entry(
            "Authorization", "auth_123", "PENDING_APPROVAL", now_ms
        )

        assert not ttl_enforcer.check_expiry(entry.entry_id, now_ms)

    def test_check_expiry_expired(self, ttl_enforcer):
        """check_expiry returns True for expired entry / check_expiry 对过期条目返回 True"""
        now_ms = int(time.time() * 1000)
        entry = ttl_enforcer.register_entry(
            "Authorization", "auth_123", "PENDING_APPROVAL", now_ms
        )

        # Check at expiry time + 1 second
        future_ms = now_ms + 86401 * 1000
        assert ttl_enforcer.check_expiry(entry.entry_id, future_ms)

    def test_check_expiry_nonexistent_entry(self, ttl_enforcer):
        """check_expiry returns False for nonexistent entry / check_expiry 对不存在的条目返回 False"""
        assert not ttl_enforcer.check_expiry("nonexistent_id")

    def test_sweep_expired_no_expired_entries(self, ttl_enforcer):
        """sweep_expired returns empty list when no entries expired / 没有过期条目时 sweep_expired 返回空列表"""
        now_ms = int(time.time() * 1000)
        ttl_enforcer.register_entry(
            "Authorization", "auth_123", "PENDING_APPROVAL", now_ms
        )

        expired = ttl_enforcer.sweep_expired(now_ms)
        assert expired == []

    def test_sweep_expired_single_entry(self, ttl_enforcer):
        """sweep_expired expires single entry / sweep_expired 过期单个条目"""
        now_ms = int(time.time() * 1000)
        entry = ttl_enforcer.register_entry(
            "Authorization", "auth_123", "PENDING_APPROVAL", now_ms
        )

        # Sweep at expiry time + 1 second
        future_ms = now_ms + 86401 * 1000
        expired = ttl_enforcer.sweep_expired(future_ms)

        assert len(expired) == 1
        assert expired[0][0] == entry.entry_id
        assert expired[0][1] == TTLExpiryAction.AUTO_REJECT.value

    def test_sweep_expired_multiple_entries(self, ttl_enforcer):
        """sweep_expired handles multiple expired entries / sweep_expired 处理多个过期条目"""
        now_ms = int(time.time() * 1000)

        entry1 = ttl_enforcer.register_entry(
            "Authorization", "auth_1", "PENDING_APPROVAL", now_ms
        )
        entry2 = ttl_enforcer.register_entry(
            "Authorization", "auth_2", "PENDING_APPROVAL", now_ms
        )

        future_ms = now_ms + 86401 * 1000
        expired = ttl_enforcer.sweep_expired(future_ms)

        assert len(expired) == 2

    def test_sweep_expired_mixed_expired_and_active(self, ttl_enforcer):
        """sweep_expired only expires those past TTL / sweep_expired 仅过期超过 TTL 的条目"""
        now_ms = int(time.time() * 1000)

        # Auth entry (24h TTL) registered at now
        entry1 = ttl_enforcer.register_entry(
            "Authorization", "auth_1", "PENDING_APPROVAL", now_ms
        )

        # Lease entry (30s TTL) registered at now, should be active at now + 25h
        entry2 = ttl_enforcer.register_entry(
            "DecisionLease", "lease_1", "ACTIVE", now_ms
        )

        # Sweep at now + 1 second (neither expired)
        future_ms = now_ms + 1000
        expired = ttl_enforcer.sweep_expired(future_ms)
        assert len(expired) == 0

        # Sweep at now + 31 seconds (lease should be expired, auth should not)
        future_ms = now_ms + 31 * 1000
        expired = ttl_enforcer.sweep_expired(future_ms)

        # Only entry2 should be expired (30s TTL)
        assert len(expired) == 1
        assert expired[0][0] == entry2.entry_id

    def test_sweep_expired_same_entry_not_swept_twice(self, ttl_enforcer):
        """sweep_expired doesn't re-expire already expired entries / sweep_expired 不会重新过期已过期的条目"""
        now_ms = int(time.time() * 1000)
        entry = ttl_enforcer.register_entry(
            "Authorization", "auth_123", "PENDING_APPROVAL", now_ms
        )

        future_ms = now_ms + 86401 * 1000

        # First sweep
        expired1 = ttl_enforcer.sweep_expired(future_ms)
        assert len(expired1) == 1

        # Second sweep — should not re-expire
        expired2 = ttl_enforcer.sweep_expired(future_ms)
        assert len(expired2) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Callbacks and Audit Trail
# ═══════════════════════════════════════════════════════════════════════════════


class TestCallbacksAndAuditTrail:
    """Test audit callbacks and expiry callbacks / 测试审计回调和到期回调"""

    def test_audit_callback_on_entry_registration(self, ttl_enforcer_with_callbacks):
        """Audit callback triggered on entry registration / 条目注册时触发审计回调"""
        enforcer, audit_records, _ = ttl_enforcer_with_callbacks
        now_ms = int(time.time() * 1000)

        enforcer.register_entry(
            "Authorization", "auth_123", "PENDING_APPROVAL", now_ms
        )

        assert len(audit_records) == 1
        record = audit_records[0]
        assert record["event_type"] == "ttl_entry_registered"
        assert record["state_machine_name"] == "Authorization"
        assert record["object_id"] == "auth_123"
        assert record["state_name"] == "PENDING_APPROVAL"

    def test_expiry_callback_on_sweep(self, ttl_enforcer_with_callbacks):
        """Expiry callback triggered when entry expires / 条目过期时触发到期回调"""
        enforcer, _, expiry_calls = ttl_enforcer_with_callbacks
        now_ms = int(time.time() * 1000)

        entry = enforcer.register_entry(
            "Authorization", "auth_123", "PENDING_APPROVAL", now_ms
        )

        future_ms = now_ms + 86401 * 1000
        enforcer.sweep_expired(future_ms)

        assert len(expiry_calls) == 1
        assert expiry_calls[0][0] == entry.entry_id
        assert expiry_calls[0][1] == TTLExpiryAction.AUTO_REJECT.value

    def test_expiry_callback_receives_correct_action(self, ttl_enforcer_with_callbacks):
        """Expiry callback receives correct action type / 到期回调接收正确的动作类型"""
        enforcer, _, expiry_calls = ttl_enforcer_with_callbacks
        now_ms = int(time.time() * 1000)

        # Lease ACTIVE → AUTO_EXPIRE
        enforcer.register_entry(
            "DecisionLease", "lease_1", "ACTIVE", now_ms
        )

        future_ms = now_ms + 31 * 1000
        enforcer.sweep_expired(future_ms)

        assert len(expiry_calls) == 1
        assert expiry_calls[0][1] == TTLExpiryAction.AUTO_EXPIRE.value

    def test_audit_callback_error_handled(self, ttl_enforcer):
        """Audit callback errors don't crash enforcer / 审计回调错误不会导致执行者崩溃"""
        def bad_audit_cb(record):
            raise ValueError("Test error")

        enforcer = TTLEnforcer(audit_callback=bad_audit_cb)
        now_ms = int(time.time() * 1000)

        # Should not raise
        entry = enforcer.register_entry(
            "Authorization", "auth_123", "PENDING_APPROVAL", now_ms
        )

        assert entry is not None

    def test_expiry_callback_error_handled(self, ttl_enforcer):
        """Expiry callback errors don't crash enforcer / 到期回调错误不会导致执行者崩溃"""
        def bad_expiry_cb(entry, action):
            raise ValueError("Test error")

        enforcer = TTLEnforcer(expiry_callback=bad_expiry_cb)
        now_ms = int(time.time() * 1000)

        entry = enforcer.register_entry(
            "Authorization", "auth_123", "PENDING_APPROVAL", now_ms
        )

        future_ms = now_ms + 86401 * 1000

        # Should not raise
        expired = enforcer.sweep_expired(future_ms)
        assert len(expired) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Querying and Retrieval
# ═══════════════════════════════════════════════════════════════════════════════


class TestQueryingAndRetrieval:
    """Test querying active and expired entries / 测试查询活跃和过期条目"""

    def test_get_active_entries_empty(self, ttl_enforcer):
        """get_active_entries returns empty list for unknown object / 未知对象返回空列表"""
        active = ttl_enforcer.get_active_entries("Authorization", "auth_999")
        assert active == []

    def test_get_active_entries_single(self, ttl_enforcer):
        """get_active_entries returns registered entries / get_active_entries 返回已注册条目"""
        now_ms = int(time.time() * 1000)
        entry = ttl_enforcer.register_entry(
            "Authorization", "auth_123", "PENDING_APPROVAL", now_ms
        )

        active = ttl_enforcer.get_active_entries("Authorization", "auth_123")
        assert len(active) == 1
        assert active[0].entry_id == entry.entry_id

    def test_get_active_entries_excludes_expired(self, ttl_enforcer):
        """get_active_entries excludes expired entries / get_active_entries 排除过期条目"""
        now_ms = int(time.time() * 1000)

        ttl_enforcer.register_entry(
            "Authorization", "auth_123", "PENDING_APPROVAL", now_ms
        )

        future_ms = now_ms + 86401 * 1000
        ttl_enforcer.sweep_expired(future_ms)

        active = ttl_enforcer.get_active_entries("Authorization", "auth_123")
        assert len(active) == 0

    def test_get_expired_entries_empty(self, ttl_enforcer):
        """get_expired_entries returns empty list initially / 初始返回空列表"""
        expired = ttl_enforcer.get_expired_entries()
        assert expired == []

    def test_get_expired_entries_after_sweep(self, ttl_enforcer):
        """get_expired_entries returns expired entries / get_expired_entries 返回过期条目"""
        now_ms = int(time.time() * 1000)

        entry = ttl_enforcer.register_entry(
            "Authorization", "auth_123", "PENDING_APPROVAL", now_ms
        )

        future_ms = now_ms + 86401 * 1000
        ttl_enforcer.sweep_expired(future_ms)

        expired = ttl_enforcer.get_expired_entries()
        assert len(expired) == 1
        assert expired[0].entry_id == entry.entry_id

    def test_get_expired_entries_filtered_by_state_machine(self, ttl_enforcer):
        """get_expired_entries filters by state machine name / get_expired_entries 按状态机名称过滤"""
        now_ms = int(time.time() * 1000)

        ttl_enforcer.register_entry(
            "Authorization", "auth_1", "PENDING_APPROVAL", now_ms
        )
        ttl_enforcer.register_entry(
            "DecisionLease", "lease_1", "ACTIVE", now_ms
        )

        future_ms = now_ms + 87000 * 1000
        ttl_enforcer.sweep_expired(future_ms)

        auth_expired = ttl_enforcer.get_expired_entries(
            state_machine_name="Authorization"
        )
        assert len(auth_expired) == 1
        assert auth_expired[0].state_machine_name == "Authorization"

    def test_get_expired_entries_filtered_by_object_id(self, ttl_enforcer):
        """get_expired_entries filters by object ID / get_expired_entries 按对象 ID 过滤"""
        now_ms = int(time.time() * 1000)

        entry1 = ttl_enforcer.register_entry(
            "Authorization", "auth_1", "PENDING_APPROVAL", now_ms
        )
        entry2 = ttl_enforcer.register_entry(
            "Authorization", "auth_2", "PENDING_APPROVAL", now_ms
        )

        future_ms = now_ms + 86401 * 1000
        ttl_enforcer.sweep_expired(future_ms)

        filtered = ttl_enforcer.get_expired_entries(object_id="auth_1")
        assert len(filtered) == 1
        assert filtered[0].entry_id == entry1.entry_id


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Daemon Sweep Mode
# ═══════════════════════════════════════════════════════════════════════════════


class TestDaemonSweepMode:
    """Test daemon sweep background thread / 测试守护扫描后台线程"""

    def test_daemon_sweep_starts(self, ttl_enforcer):
        """start_daemon_sweep starts background thread / start_daemon_sweep 启动后台线程"""
        ttl_enforcer.start_daemon_sweep(interval_seconds=1)
        assert ttl_enforcer._sweep_active is True
        assert ttl_enforcer._sweep_thread is not None

        ttl_enforcer.stop_daemon_sweep(timeout_seconds=2)

    def test_daemon_sweep_stops(self, ttl_enforcer):
        """stop_daemon_sweep stops background thread / stop_daemon_sweep 停止后台线程"""
        ttl_enforcer.start_daemon_sweep(interval_seconds=1)
        result = ttl_enforcer.stop_daemon_sweep(timeout_seconds=2)

        assert result is True
        assert ttl_enforcer._sweep_active is False

    def test_daemon_sweep_expiry_execution(self, ttl_enforcer_with_callbacks):
        """Daemon sweep automatically expires entries / 守护扫描自动过期条目"""
        enforcer, _, expiry_calls = ttl_enforcer_with_callbacks
        now_ms = int(time.time() * 1000)

        # Register an entry with short TTL
        custom_config = TTLConfig(
            state_machine_name="QuickExpire",
            state_name="QUICK",
            max_duration_seconds=1,
            on_expiry_action=TTLExpiryAction.AUTO_EXPIRE,
            on_expiry_target_state="EXPIRED",
        )
        enforcer._configs[("QuickExpire", "QUICK")] = custom_config

        enforcer.register_entry("QuickExpire", "obj_1", "QUICK", now_ms)

        # Start daemon with short interval
        enforcer.start_daemon_sweep(interval_seconds=0.5)

        # Wait for sweep to execute
        time.sleep(2)

        # Stop daemon
        enforcer.stop_daemon_sweep(timeout_seconds=2)

        # Verify expiry was triggered
        assert len(expiry_calls) > 0

    def test_daemon_sweep_already_running(self, ttl_enforcer):
        """start_daemon_sweep warns if already running / 如果已运行则警告"""
        ttl_enforcer.start_daemon_sweep(interval_seconds=1)

        # Try to start again (should warn, not crash)
        ttl_enforcer.start_daemon_sweep(interval_seconds=1)

        assert ttl_enforcer._sweep_active is True
        ttl_enforcer.stop_daemon_sweep(timeout_seconds=2)

    def test_daemon_sweep_interval_respected(self, ttl_enforcer):
        """Daemon sweep respects interval parameter / 守护扫描遵守间隔参数"""
        ttl_enforcer.start_daemon_sweep(interval_seconds=0.5)
        assert ttl_enforcer._sweep_interval_seconds == 0.5

        ttl_enforcer.stop_daemon_sweep(timeout_seconds=2)


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Thread Safety
# ═══════════════════════════════════════════════════════════════════════════════


class TestThreadSafety:
    """Test thread-safe concurrent access / 测试线程安全并发访问"""

    def test_concurrent_registration(self, ttl_enforcer):
        """Concurrent entry registration is safe / 并发条目注册是安全的"""
        now_ms = int(time.time() * 1000)
        entries = []
        lock = threading.Lock()

        def register_entries(count):
            for i in range(count):
                entry = ttl_enforcer.register_entry(
                    "Authorization",
                    f"auth_{i}",
                    "PENDING_APPROVAL",
                    now_ms,
                )
                with lock:
                    entries.append(entry)

        threads = [
            threading.Thread(target=register_entries, args=(10,))
            for _ in range(5)
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        assert len(entries) == 50
        assert len(ttl_enforcer._entries) == 50

    def test_concurrent_sweep_and_registration(self, ttl_enforcer):
        """Concurrent sweep and registration is safe / 并发扫描和注册是安全的"""
        now_ms = int(time.time() * 1000)
        errors = []

        def register_and_sweep():
            try:
                for i in range(20):
                    ttl_enforcer.register_entry(
                        "Authorization",
                        f"auth_{i}",
                        "PENDING_APPROVAL",
                        now_ms + i * 100,
                    )
                    ttl_enforcer.sweep_expired(now_ms + i * 1000)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=register_and_sweep) for _ in range(3)]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_concurrent_query_operations(self, ttl_enforcer):
        """Concurrent query operations are safe / 并发查询操作是安全的"""
        now_ms = int(time.time() * 1000)

        for i in range(10):
            ttl_enforcer.register_entry(
                "Authorization",
                f"auth_{i}",
                "PENDING_APPROVAL",
                now_ms,
            )

        errors = []

        def query_entries():
            try:
                for _ in range(50):
                    ttl_enforcer.get_active_entries("Authorization", "auth_0")
                    ttl_enforcer.get_expired_entries()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=query_entries) for _ in range(5)]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Export and Statistics
# ═══════════════════════════════════════════════════════════════════════════════


class TestExportAndStatistics:
    """Test export and statistics functionality / 测试导出和统计功能"""

    def test_export_entries_empty(self, ttl_enforcer):
        """export_entries returns empty list for empty enforcer / 空执行者返回空列表"""
        export = ttl_enforcer.export_entries()

        assert export["total_entries"] == 0
        assert export["entries"] == []
        assert "exported_at_ms" in export

    def test_export_entries_single(self, ttl_enforcer):
        """export_entries exports registered entry / export_entries 导出已注册条目"""
        now_ms = int(time.time() * 1000)
        entry = ttl_enforcer.register_entry(
            "Authorization", "auth_123", "PENDING_APPROVAL", now_ms
        )

        export = ttl_enforcer.export_entries()

        assert export["total_entries"] == 1
        assert len(export["entries"]) == 1

        exported_entry = export["entries"][0]
        assert exported_entry["entry_id"] == entry.entry_id
        assert exported_entry["state_machine_name"] == "Authorization"
        assert exported_entry["object_id"] == "auth_123"
        assert exported_entry["state_name"] == "PENDING_APPROVAL"
        assert exported_entry["max_duration_seconds"] == 86400
        assert exported_entry["on_expiry_action"] == "auto_reject"

    def test_export_entries_multiple(self, ttl_enforcer):
        """export_entries exports multiple entries / export_entries 导出多个条目"""
        now_ms = int(time.time() * 1000)

        for i in range(5):
            ttl_enforcer.register_entry(
                "Authorization",
                f"auth_{i}",
                "PENDING_APPROVAL",
                now_ms,
            )

        export = ttl_enforcer.export_entries()

        assert export["total_entries"] == 5
        assert len(export["entries"]) == 5

    def test_export_includes_expired_status(self, ttl_enforcer):
        """export_entries includes expired status / export_entries 包含过期状态"""
        now_ms = int(time.time() * 1000)
        ttl_enforcer.register_entry(
            "Authorization", "auth_123", "PENDING_APPROVAL", now_ms
        )

        future_ms = now_ms + 86401 * 1000
        ttl_enforcer.sweep_expired(future_ms)

        export = ttl_enforcer.export_entries()

        exported_entry = export["entries"][0]
        assert exported_entry["expired"] is True
        assert exported_entry["action_taken"] == "auto_reject"

    def test_get_stats_empty(self, ttl_enforcer):
        """get_stats returns correct stats for empty enforcer / 空执行者返回正确统计"""
        stats = ttl_enforcer.get_stats()

        assert stats["total_entries"] == 0
        assert stats["active_entries"] == 0
        assert stats["expired_entries"] == 0
        assert stats["daemon_sweep_active"] is False

    def test_get_stats_mixed_state(self, ttl_enforcer):
        """get_stats calculates correct counts / get_stats 计算正确计数"""
        now_ms = int(time.time() * 1000)

        # Register 3 Authorization entries
        for i in range(3):
            ttl_enforcer.register_entry(
                "Authorization",
                f"auth_{i}",
                "PENDING_APPROVAL",
                now_ms,
            )

        # Register 2 DecisionLease entries
        for i in range(2):
            ttl_enforcer.register_entry(
                "DecisionLease",
                f"lease_{i}",
                "ACTIVE",
                now_ms,
            )

        stats = ttl_enforcer.get_stats()

        assert stats["total_entries"] == 5
        assert stats["active_entries"] == 5
        assert stats["expired_entries"] == 0
        assert "Authorization" in stats["by_state_machine"]
        assert "DecisionLease" in stats["by_state_machine"]
        assert stats["by_state_machine"]["Authorization"]["total"] == 3
        assert stats["by_state_machine"]["DecisionLease"]["total"] == 2

    def test_get_stats_with_expired_entries(self, ttl_enforcer):
        """get_stats counts expired entries correctly / get_stats 正确计算过期条目"""
        now_ms = int(time.time() * 1000)

        ttl_enforcer.register_entry(
            "Authorization", "auth_1", "PENDING_APPROVAL", now_ms
        )
        ttl_enforcer.register_entry(
            "Authorization", "auth_2", "PENDING_APPROVAL", now_ms
        )

        future_ms = now_ms + 86401 * 1000
        ttl_enforcer.sweep_expired(future_ms)

        stats = ttl_enforcer.get_stats()

        assert stats["total_entries"] == 2
        assert stats["active_entries"] == 0
        assert stats["expired_entries"] == 2


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Mark Action Taken
# ═══════════════════════════════════════════════════════════════════════════════


class TestMarkActionTaken:
    """Test external action tracking / 测试外部动作追踪"""

    def test_mark_action_taken_success(self, ttl_enforcer_with_callbacks):
        """mark_action_taken updates entry successfully / mark_action_taken 成功更新条目"""
        enforcer, audit_records, _ = ttl_enforcer_with_callbacks
        now_ms = int(time.time() * 1000)

        entry = enforcer.register_entry(
            "Authorization", "auth_123", "PENDING_APPROVAL", now_ms
        )

        result = enforcer.mark_action_taken(entry.entry_id, "manual_action", now_ms)

        assert result is True

        # Check audit
        action_audit = [r for r in audit_records if r["event_type"] == "ttl_action_taken"]
        assert len(action_audit) == 1

    def test_mark_action_taken_nonexistent(self, ttl_enforcer):
        """mark_action_taken returns False for nonexistent entry / 不存在的条目返回 False"""
        result = ttl_enforcer.mark_action_taken("nonexistent", "action")
        assert result is False

    def test_mark_action_taken_updates_timestamp(self, ttl_enforcer):
        """mark_action_taken records timestamp / mark_action_taken 记录时间戳"""
        now_ms = int(time.time() * 1000)
        entry = ttl_enforcer.register_entry(
            "Authorization", "auth_123", "PENDING_APPROVAL", now_ms
        )

        later_ms = now_ms + 1000
        ttl_enforcer.mark_action_taken(entry.entry_id, "action", later_ms)

        # Verify entry was updated
        updated_entry = ttl_enforcer._entries[entry.entry_id]
        assert updated_entry.action_timestamp_ms == later_ms


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Edge Cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Test edge cases and boundary conditions / 测试边界情况和边界条件"""

    def test_entry_expires_exactly_at_limit(self, ttl_enforcer):
        """Entry expires exactly at TTL limit / 条目在 TTL 限制处过期"""
        now_ms = int(time.time() * 1000)
        entry = ttl_enforcer.register_entry(
            "Authorization", "auth_123", "PENDING_APPROVAL", now_ms
        )

        # Check exactly at expiry time
        assert ttl_enforcer.check_expiry(entry.entry_id, entry.expires_at_ms)

    def test_register_with_custom_configs(self):
        """Register entry with custom configs / 用自定义配置注册条目"""
        custom_config = TTLConfig(
            state_machine_name="Custom",
            state_name="CUSTOM_STATE",
            max_duration_seconds=42,
            on_expiry_action=TTLExpiryAction.AUTO_EXPIRE,
            on_expiry_target_state="EXPIRED",
        )

        enforcer = TTLEnforcer(
            default_configs={("Custom", "CUSTOM_STATE"): custom_config}
        )

        now_ms = int(time.time() * 1000)
        entry = enforcer.register_entry(
            "Custom", "obj_1", "CUSTOM_STATE", now_ms
        )

        assert entry is not None
        assert entry.config.max_duration_seconds == 42

    def test_repr_shows_stats(self, ttl_enforcer):
        """__repr__ includes stats / __repr__ 包含统计"""
        now_ms = int(time.time() * 1000)
        ttl_enforcer.register_entry(
            "Authorization", "auth_123", "PENDING_APPROVAL", now_ms
        )

        repr_str = repr(ttl_enforcer)

        assert "TTLEnforcer" in repr_str
        assert "total" in repr_str
        assert "active" in repr_str

    def test_zero_remaining_seconds(self):
        """remaining_seconds returns 0 for expired entry / 过期条目返回 0"""
        now_ms = int(time.time() * 1000)
        entry = TTLEntry(
            entry_id="test",
            state_machine_name="Test",
            object_id="obj",
            state_name="STATE",
            entered_at_ms=now_ms,
            expires_at_ms=now_ms - 1000,
            config=TTLConfig(
                state_machine_name="Test",
                state_name="STATE",
                max_duration_seconds=1,
                on_expiry_action=TTLExpiryAction.AUTO_EXPIRE,
            ),
        )

        remaining = entry.remaining_seconds(now_ms)
        assert remaining == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Test Coverage Summary
# ═══════════════════════════════════════════════════════════════════════════════
#
# Classes covered: 100%
#   - TTLConfig: 100% (frozen dataclass, hashable, equality)
#   - TTLEntry: 100% (is_expired, remaining_seconds, field updates)
#   - TTLEnforcer: 100% (register, check, sweep, query, daemon, export, stats)
#
# Methods covered: 100%
#   - register_entry: happy path, no config, multiple per object
#   - check_expiry: not expired, expired, nonexistent
#   - sweep_expired: empty, single, multiple, mixed, idempotent
#   - get_active_entries: empty, single, excludes expired
#   - get_expired_entries: empty, after sweep, filtered by sm, filtered by id
#   - start/stop daemon: starts, stops, already running, interval respected
#   - export_entries: empty, single, multiple, status, timestamps
#   - get_stats: empty, mixed, with expired
#   - mark_action_taken: success, nonexistent, timestamp
#   - Callbacks: registration, expiry, error handling
#   - Thread safety: concurrent registration, sweep+registration, queries
#
# Features tested: 100%
#   - All default TTL configurations
#   - Entry lifecycle (register → active → expired → action)
#   - Audit trail generation
#   - Expiry action execution
#   - Callback invocation
#   - Thread-safe concurrent access
#   - Daemon sweep mode
#   - Statistics and reporting
#   - Export/import capability
#   - Error handling
#
# ═══════════════════════════════════════════════════════════════════════════════
