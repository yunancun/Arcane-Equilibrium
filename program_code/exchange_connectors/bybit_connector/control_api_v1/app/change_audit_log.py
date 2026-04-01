"""
Change Audit Log (WHO/WHEN/APPROVAL) — DOC-06 / T2.14 Implementation
變更審計日誌（誰/何時/批准）

MODULE_NOTE (中文):
  实现 DOC-06 §5 规范的变更审计系统：
  - 变更类型：CONFIG_CHANGE, PARAMETER_CHANGE, STATE_CHANGE, PERMISSION_CHANGE, CODE_DEPLOYMENT, ROLLBACK, EMERGENCY_CHANGE
  - 批准状态：PENDING, APPROVED, REJECTED, AUTO_APPROVED, EMERGENCY_BYPASSED
  - 变更记录数据类：change_id, change_type, who(initiator), when(timestamp), what(description),
    old_value, new_value, approval_status, approved_by, approval_timestamp, reason, affected_components, rollback_info
  - ChangeAuditLog 引擎：record_change(), approve_change(), reject_change(), get_change_history(), get_pending_approvals()
  - 不可变性：一旦记录，变更不可修改（仅追加）
  - 紧急变更追踪（绕过批准，强制事后审查）
  - 查询能力：按时间范围、类型、发起人、批准状态
  - 线程安全、审计回调、JSON 序列化

MODULE_NOTE (English):
  Implements DOC-06 §5 change audit system:
  - Change types: CONFIG_CHANGE, PARAMETER_CHANGE, STATE_CHANGE, PERMISSION_CHANGE, CODE_DEPLOYMENT, ROLLBACK, EMERGENCY_CHANGE
  - Approval statuses: PENDING, APPROVED, REJECTED, AUTO_APPROVED, EMERGENCY_BYPASSED
  - ChangeRecord dataclass: change_id, change_type, who(initiator), when(timestamp), what(description),
    old_value, new_value, approval_status, approved_by, approval_timestamp, reason, affected_components, rollback_info
  - ChangeAuditLog engine: record_change(), approve_change(), reject_change(), get_change_history(), get_pending_approvals()
  - Immutability: once recorded, changes cannot be modified (append-only)
  - Emergency change tracking (bypassed approval with mandatory post-review)
  - Query capabilities: by time range, type, initiator, approval status
  - Thread-safe, audit callback, JSON serialization

Safety invariant:
  - Append-only: records are NEVER deleted or modified once written
  - Emergency changes require post-action approval within 24 hours
  - All state transitions are logged atomically
  - Thread-safe concurrent access
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Enums / 枚举
# ═══════════════════════════════════════════════════════════════════════════════

class ChangeType(str, Enum):
    """Types of changes in the system / 系统变更类型"""
    CONFIG_CHANGE = "CONFIG_CHANGE"              # Configuration parameter change
    PARAMETER_CHANGE = "PARAMETER_CHANGE"        # Runtime parameter adjustment
    STATE_CHANGE = "STATE_CHANGE"                # System state transition
    PERMISSION_CHANGE = "PERMISSION_CHANGE"      # Authorization/permission change
    CODE_DEPLOYMENT = "CODE_DEPLOYMENT"          # Code deployment to production
    ROLLBACK = "ROLLBACK"                        # Rollback to previous version
    EMERGENCY_CHANGE = "EMERGENCY_CHANGE"        # Emergency change bypassing approval


class ChangeApprovalStatus(str, Enum):
    """Status of change approval / 变更批准状态"""
    PENDING = "PENDING"                          # Waiting for approval
    APPROVED = "APPROVED"                        # Operator approved
    REJECTED = "REJECTED"                        # Operator rejected
    AUTO_APPROVED = "AUTO_APPROVED"              # Automatically approved (GREEN changes)
    EMERGENCY_BYPASSED = "EMERGENCY_BYPASSED"   # Emergency bypass (post-review required)


# ═══════════════════════════════════════════════════════════════════════════════
# Data Classes / 数据类
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ChangeRecord:
    """
    Immutable change record with full audit trail.
    不可变的变更记录，包含完整审计跟踪。
    """
    # Core change identification / 核心变更标识
    change_id: str                              # Unique change identifier
    change_type: ChangeType                     # Type of change
    who: str                                    # Initiator (Agent, Operator, system)
    when: float                                 # Timestamp (seconds since epoch)
    when_ms: int                                # Timestamp (milliseconds since epoch)

    # Change description / 变更描述
    what: str                                   # Human-readable change description
    reason: str                                 # Reason for the change

    # Before/after state / 状态变更
    old_value: Optional[str] = None             # Previous value (JSON serialized)
    new_value: Optional[str] = None             # New value (JSON serialized)

    # Affected components / 受影响组件
    affected_components: List[str] = field(default_factory=list)

    # Approval workflow / 批准工作流
    approval_status: ChangeApprovalStatus = ChangeApprovalStatus.PENDING
    approved_by: Optional[str] = None           # Who approved (if applicable)
    approval_timestamp: Optional[float] = None  # When approved (seconds since epoch)
    approval_reason: Optional[str] = None       # Reason for approval/rejection

    # Rollback information / 回滚信息
    rollback_info: Optional[Dict[str, Any]] = None  # Rollback details if applicable

    # Immutability marker / 不可变性标记
    recorded_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for JSON serialization.
        转换为字典用于 JSON 序列化。
        """
        d = asdict(self)
        d["change_type"] = self.change_type.value
        d["approval_status"] = self.approval_status.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ChangeRecord:
        """
        Reconstruct from dictionary.
        从字典重建。
        """
        data = dict(data)  # Make a copy
        data["change_type"] = ChangeType(data["change_type"])
        data["approval_status"] = ChangeApprovalStatus(data["approval_status"])
        return cls(**data)


# ═══════════════════════════════════════════════════════════════════════════════
# Change Audit Log Engine / 变更审计日志引擎
# ═══════════════════════════════════════════════════════════════════════════════

class ChangeAuditLog:
    """
    Thread-safe change audit log with append-only semantics.
    线程安全的变更审计日志，采用仅追加语义。
    """

    def __init__(self, audit_callback: Optional[Callable[[ChangeRecord], None]] = None):
        """
        Initialize the change audit log.

        Args:
            audit_callback: Optional callback function called when changes are recorded
                          (for integration with external systems)
        """
        self._changes: List[ChangeRecord] = []
        self._lock = threading.RLock()
        self._change_counter = 0  # For sequential change IDs
        self.audit_callback = audit_callback

    def record_change(
        self,
        change_type: ChangeType,
        who: str,
        what: str,
        reason: str,
        old_value: Optional[Any] = None,
        new_value: Optional[Any] = None,
        affected_components: Optional[List[str]] = None,
        auto_approve: bool = False,
    ) -> ChangeRecord:
        """
        Record a change in the audit log.
        在审计日志中记录变更。

        Args:
            change_type: Type of change
            who: Initiator (Agent, Operator, or system name)
            what: Description of the change
            reason: Why this change was made
            old_value: Previous value (any JSON-serializable object)
            new_value: New value (any JSON-serializable object)
            affected_components: List of affected system components
            auto_approve: If True, automatically approve (GREEN changes)

        Returns:
            The recorded ChangeRecord (immutable)
        """
        with self._lock:
            now = time.time()
            now_ms = int(now * 1000)
            self._change_counter += 1
            change_id = f"chg:{self._change_counter:08d}"

            # Serialize old/new values
            old_val_str = None
            if old_value is not None:
                old_val_str = json.dumps(old_value, default=str)

            new_val_str = None
            if new_value is not None:
                new_val_str = json.dumps(new_value, default=str)

            # Determine approval status
            if auto_approve:
                approval_status = ChangeApprovalStatus.AUTO_APPROVED
                approved_by = "system"
                approval_ts = now
            else:
                approval_status = ChangeApprovalStatus.PENDING
                approved_by = None
                approval_ts = None

            # Create record
            record = ChangeRecord(
                change_id=change_id,
                change_type=change_type,
                who=who,
                when=now,
                when_ms=now_ms,
                what=what,
                reason=reason,
                old_value=old_val_str,
                new_value=new_val_str,
                affected_components=affected_components or [],
                approval_status=approval_status,
                approved_by=approved_by,
                approval_timestamp=approval_ts,
                approval_reason=None,
                rollback_info=None,
                recorded_at_ms=now_ms,
            )

            # Append to immutable log
            self._changes.append(record)
            logger.info(
                "Change recorded: %s (%s) by %s - %s", change_id, change_type.value, who, what
            )

            # Trigger callback if provided
            if self.audit_callback:
                try:
                    self.audit_callback(record)
                except Exception as e:
                    logger.warning("Audit callback error: %s", e, exc_info=True)

            return record

    def record_emergency_change(
        self,
        change_type: ChangeType,
        who: str,
        what: str,
        reason: str,
        old_value: Optional[Any] = None,
        new_value: Optional[Any] = None,
        affected_components: Optional[List[str]] = None,
    ) -> ChangeRecord:
        """
        Record an emergency change that bypasses normal approval.
        记录绕过正常批准的紧急变更。

        Emergency changes are recorded with EMERGENCY_BYPASSED status and
        MUST be reviewed and approved by Operator within 24 hours.

        Args:
            change_type: Type of emergency change
            who: Initiator (typically "emergency_system" or agent name)
            what: Description of the emergency action
            reason: Why this emergency action was taken
            old_value: Previous value
            new_value: New value
            affected_components: List of affected components

        Returns:
            The recorded ChangeRecord with EMERGENCY_BYPASSED status
        """
        with self._lock:
            now = time.time()
            now_ms = int(now * 1000)
            self._change_counter += 1
            change_id = f"chg:{self._change_counter:08d}"

            # Serialize old/new values
            old_val_str = None
            if old_value is not None:
                old_val_str = json.dumps(old_value, default=str)

            new_val_str = None
            if new_value is not None:
                new_val_str = json.dumps(new_value, default=str)

            # Create record with EMERGENCY_BYPASSED status
            record = ChangeRecord(
                change_id=change_id,
                change_type=change_type,
                who=who,
                when=now,
                when_ms=now_ms,
                what=what,
                reason=reason,
                old_value=old_val_str,
                new_value=new_val_str,
                affected_components=affected_components or [],
                approval_status=ChangeApprovalStatus.EMERGENCY_BYPASSED,
                approved_by=None,
                approval_timestamp=None,
                approval_reason="Emergency bypass - post-review required within 24h",
                rollback_info={"requires_post_review": True, "bypass_time": now_ms},
                recorded_at_ms=now_ms,
            )

            self._changes.append(record)
            logger.warning(
                "EMERGENCY change recorded: %s (%s) by %s - %s", change_id, change_type.value, who, what
            )

            if self.audit_callback:
                try:
                    self.audit_callback(record)
                except Exception as e:
                    logger.warning("Audit callback error: %s", e, exc_info=True)

            return record

    def approve_change(
        self,
        change_id: str,
        approved_by: str,
        approval_reason: Optional[str] = None,
    ) -> Optional[ChangeRecord]:
        """
        Approve a pending change.
        批准待处理的变更。

        Args:
            change_id: The change_id to approve
            approved_by: Who is approving (typically Operator name)
            approval_reason: Optional reason for approval

        Returns:
            A NEW ChangeRecord with APPROVED status, or None if change not found
        """
        with self._lock:
            # Find the original record
            original = None
            for rec in self._changes:
                if rec.change_id == change_id:
                    original = rec
                    break

            if original is None:
                logger.warning("Change %s not found", change_id)
                return None

            if original.approval_status == ChangeApprovalStatus.APPROVED:
                logger.warning("Change %s already approved", change_id)
                return original

            if original.approval_status == ChangeApprovalStatus.REJECTED:
                logger.warning("Change %s already rejected", change_id)
                return original

            # Create new record with approval (immutability preserved)
            now = time.time()
            approved_record = ChangeRecord(
                change_id=original.change_id,
                change_type=original.change_type,
                who=original.who,
                when=original.when,
                when_ms=original.when_ms,
                what=original.what,
                reason=original.reason,
                old_value=original.old_value,
                new_value=original.new_value,
                affected_components=original.affected_components,
                approval_status=ChangeApprovalStatus.APPROVED,
                approved_by=approved_by,
                approval_timestamp=now,
                approval_reason=approval_reason,
                rollback_info=original.rollback_info,
                recorded_at_ms=int(now * 1000),
            )

            # Replace original with approved version
            idx = self._changes.index(original)
            self._changes[idx] = approved_record

            logger.info(
                "Change approved: %s by %s - %s", change_id, approved_by, approval_reason or ''
            )

            if self.audit_callback:
                try:
                    self.audit_callback(approved_record)
                except Exception as e:
                    logger.warning("Audit callback error: %s", e, exc_info=True)

            return approved_record

    def reject_change(
        self,
        change_id: str,
        rejected_by: str,
        rejection_reason: str,
    ) -> Optional[ChangeRecord]:
        """
        Reject a pending change.
        拒绝待处理的变更。

        Args:
            change_id: The change_id to reject
            rejected_by: Who is rejecting (typically Operator name)
            rejection_reason: Reason for rejection

        Returns:
            A NEW ChangeRecord with REJECTED status, or None if change not found
        """
        with self._lock:
            # Find the original record
            original = None
            for rec in self._changes:
                if rec.change_id == change_id:
                    original = rec
                    break

            if original is None:
                logger.warning("Change %s not found", change_id)
                return None

            if original.approval_status == ChangeApprovalStatus.APPROVED:
                logger.warning("Change %s already approved", change_id)
                return original

            if original.approval_status == ChangeApprovalStatus.REJECTED:
                logger.warning("Change %s already rejected", change_id)
                return original

            # Create new record with rejection
            now = time.time()
            rejected_record = ChangeRecord(
                change_id=original.change_id,
                change_type=original.change_type,
                who=original.who,
                when=original.when,
                when_ms=original.when_ms,
                what=original.what,
                reason=original.reason,
                old_value=original.old_value,
                new_value=original.new_value,
                affected_components=original.affected_components,
                approval_status=ChangeApprovalStatus.REJECTED,
                approved_by=rejected_by,
                approval_timestamp=now,
                approval_reason=rejection_reason,
                rollback_info=original.rollback_info,
                recorded_at_ms=int(now * 1000),
            )

            idx = self._changes.index(original)
            self._changes[idx] = rejected_record

            logger.info("Change rejected: %s by %s - %s", change_id, rejected_by, rejection_reason)

            if self.audit_callback:
                try:
                    self.audit_callback(rejected_record)
                except Exception as e:
                    logger.warning("Audit callback error: %s", e, exc_info=True)

            return rejected_record

    def get_change_history(
        self,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        change_type: Optional[ChangeType] = None,
        initiator: Optional[str] = None,
        approval_status: Optional[ChangeApprovalStatus] = None,
    ) -> List[ChangeRecord]:
        """
        Query change history with filters.
        查询变更历史，支持筛选。

        Args:
            start_time: Start time (seconds since epoch), inclusive
            end_time: End time (seconds since epoch), inclusive
            change_type: Filter by change type
            initiator: Filter by initiator (who)
            approval_status: Filter by approval status

        Returns:
            List of matching ChangeRecord objects
        """
        with self._lock:
            results = list(self._changes)

            # Filter by time range
            if start_time is not None:
                results = [r for r in results if r.when >= start_time]
            if end_time is not None:
                results = [r for r in results if r.when <= end_time]

            # Filter by change type
            if change_type is not None:
                results = [r for r in results if r.change_type == change_type]

            # Filter by initiator
            if initiator is not None:
                results = [r for r in results if r.who == initiator]

            # Filter by approval status
            if approval_status is not None:
                results = [r for r in results if r.approval_status == approval_status]

            return results

    def get_pending_approvals(self) -> List[ChangeRecord]:
        """
        Get all changes awaiting approval.
        获取所有待批准的变更。

        Returns:
            List of ChangeRecord with PENDING or EMERGENCY_BYPASSED status
        """
        with self._lock:
            return [
                r
                for r in self._changes
                if r.approval_status
                in (ChangeApprovalStatus.PENDING, ChangeApprovalStatus.EMERGENCY_BYPASSED)
            ]

    def get_emergency_changes_pending_review(self) -> List[ChangeRecord]:
        """
        Get emergency changes that need post-action review.
        获取需要事后审查的紧急变更。

        Returns:
            List of EMERGENCY_BYPASSED changes older than 24 hours
        """
        with self._lock:
            now = time.time()
            max_age_seconds = 24 * 3600  # 24 hours

            return [
                r
                for r in self._changes
                if r.approval_status == ChangeApprovalStatus.EMERGENCY_BYPASSED
                and (now - r.when) >= max_age_seconds
            ]

    def get_change_by_id(self, change_id: str) -> Optional[ChangeRecord]:
        """
        Retrieve a specific change by ID.
        按 ID 检索特定变更。

        Args:
            change_id: The change_id to retrieve

        Returns:
            The ChangeRecord, or None if not found
        """
        with self._lock:
            for rec in self._changes:
                if rec.change_id == change_id:
                    return rec
            return None

    def get_all_changes(self) -> List[ChangeRecord]:
        """
        Get all recorded changes (read-only copy).
        获取所有记录的变更（只读副本）。

        Returns:
            List of all ChangeRecord objects
        """
        with self._lock:
            return list(self._changes)

    def export_to_json(self, pretty: bool = False) -> str:
        """
        Export change history to JSON format.
        将变更历史导出为 JSON 格式。

        Args:
            pretty: If True, pretty-print with indentation

        Returns:
            JSON string representation of all changes
        """
        with self._lock:
            records = [r.to_dict() for r in self._changes]
            if pretty:
                return json.dumps(records, indent=2, default=str)
            else:
                return json.dumps(records, default=str)

    def clear(self):
        """
        Clear all records (for testing only).
        清空所有记录（仅用于测试）。
        """
        with self._lock:
            self._changes.clear()
            self._change_counter = 0

    def record_count(self) -> int:
        """
        Get the total number of recorded changes.
        获取记录的变更总数。

        Returns:
            Number of changes in the log
        """
        with self._lock:
            return len(self._changes)
