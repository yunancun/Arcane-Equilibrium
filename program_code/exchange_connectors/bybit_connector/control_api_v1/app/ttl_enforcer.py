"""
TTL Enforcer — Time-to-Live Enforcement for State Machines
TTL 执行者 — 所有状态机的生命周期强制执行

MODULE_NOTE (中文):
  本模块实现 GAP-M8 要求的 TTL（生存时间）强制执行系统：
  - Authorization (授权): PENDING_APPROVAL 最多 24 小时 → 自动 REJECT
  - Decision Lease (决策租约): ACTIVE 最多 30 秒 → 自动 EXPIRE，BRIDGED 最多 60 秒 → 自动 EXPIRE
  - Risk Governor (风控总督): CIRCUIT_BREAKER 最多 1 小时 → 需要人工审查，MANUAL_REVIEW 最多 24 小时 → 升级
  - OMS (订单管理): SUBMITTED 最多 30 秒 → 自动取消，WORKING 最多 可变时间

  核心设计不变量：
  - TTL 是自动的，不可绕过的强制约束
  - 每个状态机对象进入特定状态时自动开始 TTL 计时
  - TTL 到期时自动执行 on_expiry_action（自动过期或需要人工审查）
  - 全部 TTL 记录可审计、可追踪、可导出
  - Daemon sweep 模式：周期性检查过期条目
  - 线程安全，支持高并发

MODULE_NOTE (English):
  Implements the TTL enforcement system per GAP-M8:
  - Authorization: PENDING_APPROVAL max 24h → auto-REJECT
  - Decision Lease: ACTIVE max 30s → auto-EXPIRE, BRIDGED max 60s → auto-EXPIRE
  - Risk Governor: CIRCUIT_BREAKER max 1h → manual review required, MANUAL_REVIEW max 24h → escalate
  - OMS: SUBMITTED max 30s → auto-cancel, WORKING max variable

  Core safety invariants:
  - TTL is automatic, non-bypassable enforcement
  - Each state machine object starts TTL countdown on state entry
  - On expiry, on_expiry_action executes automatically (auto-expire or require manual review)
  - All TTL records are auditable, traceable, exportable
  - Daemon sweep mode: periodic check for expired entries
  - Thread-safe, high concurrency support

Safety invariant:
  - No state can exist past its max_duration_seconds without explicit action
  - Expiry actions are immutable once state entered
  - GUI / Learning / Strategy layers CANNOT bypass TTL enforcement
  - Every expiry generates audit trail
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# TTL Configuration / TTL 配置
# ═══════════════════════════════════════════════════════════════════════════════


class TTLExpiryAction(str, Enum):
    """Actions to take when TTL expires / TTL 到期时的动作"""

    AUTO_REJECT = "auto_reject"  # Authorization: PENDING_APPROVAL → REJECTED
    AUTO_EXPIRE = "auto_expire"  # Decision Lease, Risk Governor CIRCUIT_BREAKER → fallback
    AUTO_CANCEL = "auto_cancel"  # OMS: SUBMITTED → CANCELED
    MANUAL_REVIEW_REQUIRED = "manual_review_required"  # Risk Governor: escalate to MANUAL_REVIEW
    ESCALATE = "escalate"  # Risk Governor MANUAL_REVIEW → requires escalation


@dataclass(frozen=True)
class TTLConfig:
    """
    Configuration for a single TTL enforcement rule.
    单个 TTL 强制执行规则的配置。

    Args:
        state_machine_name: Name of the state machine (e.g., 'Authorization', 'DecisionLease')
        state_name: Name of the state to enforce TTL on (e.g., 'PENDING_APPROVAL')
        max_duration_seconds: Maximum allowed duration in seconds
        on_expiry_action: Action to take upon expiry (TTLExpiryAction)
        on_expiry_target_state: Target state to transition to (if applicable)
    """

    state_machine_name: str
    state_name: str
    max_duration_seconds: int
    on_expiry_action: TTLExpiryAction
    on_expiry_target_state: Optional[str] = None

    def __hash__(self) -> int:
        """Make it hashable for use as dict key / 使其可哈希以用作字典键"""
        return hash((self.state_machine_name, self.state_name))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TTLConfig):
            return NotImplemented
        return (
            self.state_machine_name == other.state_machine_name
            and self.state_name == other.state_name
        )


@dataclass
class TTLEntry:
    """
    A single TTL tracking record for a state machine object.
    单个状态机对象的 TTL 追踪记录。

    Args:
        entry_id: Unique identifier for this TTL entry
        state_machine_name: Name of the state machine
        object_id: ID of the state machine object (e.g., authorization_id, lease_id)
        state_name: Current state name
        entered_at_ms: Timestamp when state was entered (milliseconds)
        expires_at_ms: Timestamp when TTL expires (milliseconds)
        config: TTLConfig that created this entry
        expired: Whether TTL has expired
        action_taken: Action executed upon expiry (if any)
        action_timestamp_ms: When the action was taken
    """

    entry_id: str
    state_machine_name: str
    object_id: str
    state_name: str
    entered_at_ms: int
    expires_at_ms: int
    config: TTLConfig
    expired: bool = False
    action_taken: Optional[str] = None
    action_timestamp_ms: Optional[int] = None

    def is_expired(self, current_time_ms: Optional[int] = None) -> bool:
        """Check if TTL has expired / 检查 TTL 是否已过期"""
        if self.expired:
            return True
        now = current_time_ms or int(time.time() * 1000)
        return now >= self.expires_at_ms

    def remaining_seconds(self, current_time_ms: Optional[int] = None) -> float:
        """Get remaining seconds before expiry / 获取过期前剩余秒数"""
        now = current_time_ms or int(time.time() * 1000)
        return max(0, (self.expires_at_ms - now) / 1000.0)


# ═══════════════════════════════════════════════════════════════════════════════
# Default TTL Configurations / 默认 TTL 配置
# ═══════════════════════════════════════════════════════════════════════════════


def _create_default_ttl_configs() -> Dict[tuple, TTLConfig]:
    """
    Create default TTL configurations for all state machines.
    为所有状态机创建默认 TTL 配置。

    Returns:
        Dictionary keyed by (state_machine_name, state_name)
    """
    configs = {}

    # Authorization (授权) — SM-01
    # PENDING_APPROVAL: max 24 hours → auto-REJECT
    auth_pending = TTLConfig(
        state_machine_name="Authorization",
        state_name="PENDING_APPROVAL",
        max_duration_seconds=86400,  # 24 hours
        on_expiry_action=TTLExpiryAction.AUTO_REJECT,
        on_expiry_target_state="REJECTED",
    )
    configs[(auth_pending.state_machine_name, auth_pending.state_name)] = auth_pending

    # Decision Lease (决策租约) — SM-02
    # ACTIVE: max 30 seconds → auto-EXPIRE
    lease_active = TTLConfig(
        state_machine_name="DecisionLease",
        state_name="ACTIVE",
        max_duration_seconds=30,
        on_expiry_action=TTLExpiryAction.AUTO_EXPIRE,
        on_expiry_target_state="EXPIRED",
    )
    configs[(lease_active.state_machine_name, lease_active.state_name)] = lease_active

    # BRIDGED: max 60 seconds → auto-EXPIRE
    lease_bridged = TTLConfig(
        state_machine_name="DecisionLease",
        state_name="BRIDGED",
        max_duration_seconds=60,
        on_expiry_action=TTLExpiryAction.AUTO_EXPIRE,
        on_expiry_target_state="EXPIRED",
    )
    configs[(lease_bridged.state_machine_name, lease_bridged.state_name)] = lease_bridged

    # Risk Governor (风控总督) — SM-04
    # CIRCUIT_BREAKER: max 1 hour → requires manual review
    risk_circuit = TTLConfig(
        state_machine_name="RiskGovernor",
        state_name="CIRCUIT_BREAKER",
        max_duration_seconds=3600,  # 1 hour
        on_expiry_action=TTLExpiryAction.MANUAL_REVIEW_REQUIRED,
        on_expiry_target_state="MANUAL_REVIEW",
    )
    configs[(risk_circuit.state_machine_name, risk_circuit.state_name)] = risk_circuit

    # MANUAL_REVIEW: max 24 hours → escalate
    risk_manual = TTLConfig(
        state_machine_name="RiskGovernor",
        state_name="MANUAL_REVIEW",
        max_duration_seconds=86400,  # 24 hours
        on_expiry_action=TTLExpiryAction.ESCALATE,
        on_expiry_target_state=None,  # Escalation doesn't auto-transition
    )
    configs[(risk_manual.state_machine_name, risk_manual.state_name)] = risk_manual

    # OMS (订单管理) — Extension
    # SUBMITTED: max 30 seconds → auto-CANCEL
    oms_submitted = TTLConfig(
        state_machine_name="OMS",
        state_name="SUBMITTED",
        max_duration_seconds=30,
        on_expiry_action=TTLExpiryAction.AUTO_CANCEL,
        on_expiry_target_state="CANCELED",
    )
    configs[(oms_submitted.state_machine_name, oms_submitted.state_name)] = oms_submitted

    return configs


# ═══════════════════════════════════════════════════════════════════════════════
# TTL Enforcer Engine / TTL 执行者引擎
# ═══════════════════════════════════════════════════════════════════════════════


class TTLEnforcer:
    """
    Thread-safe TTL enforcement engine for all state machines.
    为所有状态机的线程安全 TTL 强制执行引擎。

    Features / 功能：
      - Automatic TTL tracking on state entry
      - Periodic daemon sweep for expired entries
      - Thread-safe concurrent access
      - Full audit trail
      - Callback support for expiry actions
      - Export/import for persistence
    """

    def __init__(
        self,
        default_configs: Optional[Dict[tuple, TTLConfig]] = None,
        audit_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        expiry_callback: Optional[Callable[[TTLEntry, str], None]] = None,
    ):
        """
        Initialize TTL enforcer.

        Args:
            default_configs: Default TTL configurations (uses built-in if None)
            audit_callback: Callback for audit events
            expiry_callback: Callback when TTL expires (entry, action_type)
        """
        self._configs = default_configs or _create_default_ttl_configs()
        self._audit_callback = audit_callback
        self._expiry_callback = expiry_callback

        # Thread-safe storage
        self._entries: Dict[str, TTLEntry] = {}  # entry_id → TTLEntry
        self._object_entries: Dict[tuple, List[str]] = {}  # (sm_name, object_id) → [entry_ids]
        self._lock = threading.RLock()

        # Daemon sweep control
        self._sweep_thread: Optional[threading.Thread] = None
        self._sweep_interval_seconds = 5  # Check every 5 seconds
        self._sweep_active = False

    def register_entry(
        self,
        state_machine_name: str,
        object_id: str,
        state_name: str,
        current_time_ms: Optional[int] = None,
    ) -> Optional[TTLEntry]:
        """
        Register a new TTL entry when an object enters a state.
        当对象进入状态时注册新 TTL 条目。

        Args:
            state_machine_name: Name of the state machine
            object_id: ID of the object
            state_name: State entered
            current_time_ms: Current time (defaults to now)

        Returns:
            TTLEntry if a TTL config exists for this state, None otherwise
        """
        config = self._configs.get((state_machine_name, state_name))
        if not config:
            return None

        now = current_time_ms or int(time.time() * 1000)
        entry = TTLEntry(
            entry_id=str(uuid.uuid4()),
            state_machine_name=state_machine_name,
            object_id=object_id,
            state_name=state_name,
            entered_at_ms=now,
            expires_at_ms=now + (config.max_duration_seconds * 1000),
            config=config,
        )

        with self._lock:
            self._entries[entry.entry_id] = entry
            key = (state_machine_name, object_id)
            if key not in self._object_entries:
                self._object_entries[key] = []
            self._object_entries[key].append(entry.entry_id)

        self._audit_log(
            event_type="ttl_entry_registered",
            entry_id=entry.entry_id,
            state_machine_name=state_machine_name,
            object_id=object_id,
            state_name=state_name,
            max_duration_seconds=config.max_duration_seconds,
        )

        return entry

    def check_expiry(self, entry_id: str, current_time_ms: Optional[int] = None) -> bool:
        """
        Check if a specific entry has expired.
        检查特定条目是否已过期。

        Returns:
            True if entry exists and has expired, False otherwise
        """
        with self._lock:
            entry = self._entries.get(entry_id)
            if not entry:
                return False
            return entry.is_expired(current_time_ms)

    def sweep_expired(
        self, current_time_ms: Optional[int] = None
    ) -> List[tuple]:
        """
        Sweep all entries and expire those past their TTL.
        扫描所有条目并过期超过 TTL 的条目。

        Returns:
            List of (entry_id, action_taken) tuples for expired entries
        """
        now = current_time_ms or int(time.time() * 1000)
        expired_list = []

        with self._lock:
            entries_to_check = list(self._entries.values())

        for entry in entries_to_check:
            if entry.is_expired(now) and not entry.action_taken:
                action = self._execute_expiry_action(entry, now)
                expired_list.append((entry.entry_id, action))

        return expired_list

    def _execute_expiry_action(self, entry: TTLEntry, current_time_ms: int) -> str:
        """
        Execute the action specified in the TTL config.
        执行 TTL 配置中指定的动作。

        Returns:
            Action name that was executed
        """
        action = entry.config.on_expiry_action.value

        with self._lock:
            entry.expired = True
            entry.action_taken = action
            entry.action_timestamp_ms = current_time_ms

        self._audit_log(
            event_type="ttl_expired",
            entry_id=entry.entry_id,
            state_machine_name=entry.state_machine_name,
            object_id=entry.object_id,
            state_name=entry.state_name,
            action_taken=action,
            target_state=entry.config.on_expiry_target_state,
        )

        if self._expiry_callback:
            try:
                self._expiry_callback(entry, action)
            except Exception as e:
                logger.exception(
                    f"Expiry callback error for entry {entry.entry_id}: {e}"
                )

        return action

    def get_active_entries(
        self, state_machine_name: str, object_id: str
    ) -> List[TTLEntry]:
        """
        Get all active (non-expired) TTL entries for an object.
        获取对象的所有活跃（未过期）TTL 条目。
        """
        with self._lock:
            key = (state_machine_name, object_id)
            entry_ids = self._object_entries.get(key, [])
            return [
                self._entries[eid]
                for eid in entry_ids
                if eid in self._entries and not self._entries[eid].expired
            ]

    def get_expired_entries(
        self,
        state_machine_name: Optional[str] = None,
        object_id: Optional[str] = None,
    ) -> List[TTLEntry]:
        """
        Get all expired TTL entries (optionally filtered).
        获取所有过期 TTL 条目（可选过滤）。
        """
        with self._lock:
            entries = list(self._entries.values())

        result = [e for e in entries if e.expired]

        if state_machine_name:
            result = [e for e in result if e.state_machine_name == state_machine_name]

        if object_id:
            result = [e for e in result if e.object_id == object_id]

        return result

    def mark_action_taken(
        self, entry_id: str, action: str, current_time_ms: Optional[int] = None
    ) -> bool:
        """
        Mark that an action was taken for an expired entry (externally).
        标记已为过期条目执行了操作（外部）。

        Returns:
            True if entry was found and updated, False otherwise
        """
        now = current_time_ms or int(time.time() * 1000)

        with self._lock:
            entry = self._entries.get(entry_id)
            if not entry:
                return False

            entry.action_taken = action
            entry.action_timestamp_ms = now

        self._audit_log(
            event_type="ttl_action_taken",
            entry_id=entry_id,
            action=action,
        )

        return True

    def start_daemon_sweep(self, interval_seconds: float = 5) -> None:
        """
        Start a daemon thread that periodically sweeps for expired entries.
        启动定期扫描过期条目的守护线程。
        """
        with self._lock:
            if self._sweep_active:
                logger.warning("Daemon sweep already running")
                return

            self._sweep_interval_seconds = interval_seconds
            self._sweep_active = True

        self._sweep_thread = threading.Thread(
            target=self._daemon_sweep_loop,
            daemon=True,
            name="TTLEnforcer-DaemonSweep",
        )
        self._sweep_thread.start()
        logger.info(f"TTL enforcer daemon sweep started (interval: {interval_seconds}s)")

    def stop_daemon_sweep(self, timeout_seconds: float = 10) -> bool:
        """
        Stop the daemon sweep thread.
        停止守护扫描线程。

        Returns:
            True if stopped cleanly, False if timeout
        """
        with self._lock:
            self._sweep_active = False

        if self._sweep_thread:
            self._sweep_thread.join(timeout=timeout_seconds)
            if self._sweep_thread.is_alive():
                logger.warning("Daemon sweep thread did not stop in time")
                return False

        logger.info("TTL enforcer daemon sweep stopped")
        return True

    def _daemon_sweep_loop(self) -> None:
        """Continuous sweep loop for daemon thread / 守护线程的连续扫描循环"""
        logger.debug("Daemon sweep loop started")

        while self._sweep_active:
            try:
                expired = self.sweep_expired()
                if expired:
                    logger.debug(f"Daemon sweep: {len(expired)} entries expired")
            except Exception as e:
                logger.exception(f"Error in daemon sweep: {e}")

            time.sleep(self._sweep_interval_seconds)

        logger.debug("Daemon sweep loop stopped")

    def export_entries(self) -> Dict[str, Any]:
        """
        Export all TTL entries as JSON-compatible dict.
        导出所有 TTL 条目为 JSON 兼容字典。
        """
        with self._lock:
            entries = []
            for entry in self._entries.values():
                entries.append(
                    {
                        "entry_id": entry.entry_id,
                        "state_machine_name": entry.state_machine_name,
                        "object_id": entry.object_id,
                        "state_name": entry.state_name,
                        "entered_at_ms": entry.entered_at_ms,
                        "expires_at_ms": entry.expires_at_ms,
                        "max_duration_seconds": entry.config.max_duration_seconds,
                        "on_expiry_action": entry.config.on_expiry_action.value,
                        "on_expiry_target_state": entry.config.on_expiry_target_state,
                        "expired": entry.expired,
                        "action_taken": entry.action_taken,
                        "action_timestamp_ms": entry.action_timestamp_ms,
                    }
                )

            return {
                "exported_at_ms": int(time.time() * 1000),
                "total_entries": len(entries),
                "entries": entries,
            }

    def get_stats(self) -> Dict[str, Any]:
        """
        Get current TTL enforcer statistics.
        获取当前 TTL 执行者统计。
        """
        with self._lock:
            total = len(self._entries)
            expired = sum(1 for e in self._entries.values() if e.expired)
            active = total - expired

            by_state_machine = {}
            for entry in self._entries.values():
                sm_name = entry.state_machine_name
                if sm_name not in by_state_machine:
                    by_state_machine[sm_name] = {"total": 0, "expired": 0, "active": 0}
                by_state_machine[sm_name]["total"] += 1
                if entry.expired:
                    by_state_machine[sm_name]["expired"] += 1
                else:
                    by_state_machine[sm_name]["active"] += 1

            return {
                "timestamp_ms": int(time.time() * 1000),
                "total_entries": total,
                "active_entries": active,
                "expired_entries": expired,
                "by_state_machine": by_state_machine,
                "daemon_sweep_active": self._sweep_active,
            }

    def _audit_log(self, event_type: str, **kwargs) -> None:
        """Log audit event / 记录审计事件"""
        if not self._audit_callback:
            return

        try:
            self._audit_callback(
                {
                    "event_type": event_type,
                    "timestamp_ms": int(time.time() * 1000),
                    **kwargs,
                }
            )
        except Exception as e:
            logger.exception(f"Error in audit callback: {e}")

    def __repr__(self) -> str:
        stats = self.get_stats()
        return (
            f"TTLEnforcer(total={stats['total_entries']}, "
            f"active={stats['active_entries']}, "
            f"expired={stats['expired_entries']}, "
            f"daemon_sweep_active={stats['daemon_sweep_active']})"
        )
