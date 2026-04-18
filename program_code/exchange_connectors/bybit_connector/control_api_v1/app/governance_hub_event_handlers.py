"""
Governance Hub Event Handlers Mixin — callback factories, wiring, and cache invalidation.
治理集線器事件處理器 Mixin — 回調工廠、連接與快取失效。

MODULE_NOTE (EN):
  Extracted from governance_hub.py (E5-P1-9 file size split). Companion to
  governance_hub_cascades.py (FIX-08). Contains the *callback-factory* and
  *wiring* event handlers:
    - _make_audit_callback(sm_name)          : factory for per-SM audit
                                                callbacks that persist to
                                                jsonl files.
    - _make_incident_callback()              : factory for reconciliation
                                                engine incident callbacks.
    - _wire_callbacks()                      : cross-SM callback wiring
                                                (risk → auth).
    - _invalidate_auth_cache()               : authorization cache
                                                invalidation helper.
    - _check_de_escalation_gate(...)         : RecoveryApprovalGate pending
                                                check helper.

  All methods remain *methods* on the ``GovernanceHub`` class via
  multiple-inheritance mixin — their semantics, lock discipline and audit
  semantics are byte-identical to pre-split behaviour. No I/O or state-machine
  semantics are changed.

MODULE_NOTE (中):
  從 governance_hub.py 抽出（E5-P1-9 檔案大小拆分），與
  governance_hub_cascades.py（FIX-08）並列。包含回調工廠 / 連接類事件處理器
  方法：_make_audit_callback / _make_incident_callback / _wire_callbacks /
  _invalidate_auth_cache / _check_de_escalation_gate。

  這些方法透過多重繼承 Mixin 仍掛在 ``GovernanceHub`` 實例上；鎖粒度、審計
  語意、錯誤計數與拆分前完全相同，0 行為變更。

Split rationale / 拆分動機：
  governance_hub.py 於 E5-P1-9 之前為 1052 行，接近 §九 硬上限 1200。
  抽離純回調工廠與 wiring 後回落到 ~810 行，與 cascades mixin 形成兩層
  關注點分離：核心 API + 狀態管理 (governance_hub.py) ←→ Mixin(status,
  cascade) + Mixin(callback wiring)。

Singleton law / 單例契約：
  本 Mixin 不建立任何新 singleton，也不另行建 GovernanceHub。繼承方
  ``GovernanceHub`` 仍是 main_legacy.py 級別唯一單例。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Callable

from .change_audit_log import ChangeType
from .utils.time_utils import now_ms

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Event Handlers Mixin / 事件處理器 Mixin
# ═══════════════════════════════════════════════════════════════════════════════

class GovernanceHubEventHandlersMixin:
    """
    Mixin providing callback factories and wiring helpers for GovernanceHub.
    為 GovernanceHub 提供回調工廠與連接輔助方法的 Mixin。

    All methods depend on GovernanceHub internals (``self._lock``,
    ``self._audit_dir``, ``self._callback_errors``, ``self._cached_auth_state``,
    ``self._change_audit_log``, ``self._risk_governor_sm``,
    ``self._recovery_gate``) and MUST only be used via ``GovernanceHub`` MRO.

    所有方法都依賴 GovernanceHub 內部屬性；只能透過 GovernanceHub 的 MRO 使用。
    """

    # ── Callback factories / 回調工廠 ────────────────────────────────────────

    def _make_audit_callback(self, sm_name: str) -> Callable[[dict[str, Any]], None]:
        """
        Factory for audit callbacks that persist to files / 審計回調工廠

        Optimized: I/O happens outside any lock; only lock is acquired for
        error tracking. / I/O 在鎖外執行，僅錯誤計數進入鎖。
        """
        def callback(event: dict[str, Any]) -> None:
            try:
                audit_file: Path = self._audit_dir / f"{sm_name}_audit.jsonl"
                event_with_meta = {
                    "timestamp_ms": now_ms(),
                    "sm_name": sm_name,
                    **event,
                }
                with open(audit_file, "a") as f:
                    f.write(json.dumps(event_with_meta) + "\n")
                # SECURITY FIX #3: restrictive perms (0o600 = owner rw only)
                # 安全修復 #3：限制權限 0o600（僅擁有者讀寫）
                os.chmod(audit_file, 0o600)
            except Exception as e:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug("Audit callback error for %s: %s", sm_name, e)
                with self._lock:
                    self._callback_errors += 1

        return callback

    def _make_incident_callback(self) -> Callable[[str, dict[str, Any]], None]:
        """
        Factory for reconciliation incident callbacks.
        對賬事件回調工廠。

        Routes reconciliation incidents to appropriate cross-SM handlers.
        將對賬事件路由到對應的跨 SM 處理器。
        """
        def callback(action: str, report: dict[str, Any]) -> None:
            try:
                severity = report.get("overall_result", "").upper()
                # Treat reconciliation failures as incidents
                # 把對賬失敗視為事件
                if action in ["reconciliation_mismatch", "reconciliation_failure"]:
                    # Map overall_result to severity for callback
                    # 將 overall_result 對應到 severity
                    if severity in ["CRITICAL", "FATAL"]:
                        # NOTE: _on_reconciliation_mismatch is provided by
                        # GovernanceHubStatusCascadeMixin (cascades module).
                        # 該方法由 cascades Mixin 提供。
                        self._on_reconciliation_mismatch(severity, report)
                    elif severity == "WARNING":
                        # Minor mismatch - log but don't escalate
                        # 輕微不一致：只記錄不升級
                        if logger.isEnabledFor(logging.DEBUG):
                            logger.debug(
                                "Reconciliation warning: %s",
                                report.get('result'),
                            )
            except Exception as e:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "Incident callback error for action %s: %s", action, e,
                    )
                with self._lock:
                    self._callback_errors += 1

        return callback

    # ── Cross-SM wiring / 跨 SM 連接 ─────────────────────────────────────────

    def _wire_callbacks(self) -> None:
        """Wire cross-SM callbacks / 連接跨 SM 回調

        Replaces risk governor's ``_on_level_change`` hook with the Hub's
        cascade entry point ``_on_risk_escalation``. Reconciliation engine's
        incident callback is set during ``_ensure_initialized`` construction
        (no race).

        將風控狀態機的 ``_on_level_change`` hook 替換為 Hub 的 ``_on_risk_escalation``。
        對賬引擎的 incident callback 在 ``_ensure_initialized`` 建構時即設定，無競態。
        """
        try:
            # Risk escalation → restrict/freeze auth
            # 風控升級 → 限制/凍結授權
            if hasattr(self._risk_governor_sm, "_on_level_change"):
                # Keep reference for debugging / 保留原 callback 指標供除錯
                _original_callback = self._risk_governor_sm._on_level_change  # noqa: F841
                self._risk_governor_sm._on_level_change = (
                    lambda old, new: self._on_risk_escalation(old, new)
                )
            logger.debug("Wired risk escalation callback")
        except Exception as e:
            logger.warning("Failed to wire risk escalation callback: %s", e)

        # Note: Reconciliation engine incident_callback is already set during
        # initialization in _ensure_initialized() to avoid race conditions.
        # 對賬引擎的 incident_callback 在 _ensure_initialized() 已設定以避免競態。

    # ── Cache invalidation / 快取失效 ────────────────────────────────────────

    def _invalidate_auth_cache(self) -> None:
        """Invalidate authorization cache on state changes / 狀態變更時使授權快取失效

        Clears the TTL auth cache (``self._cached_auth_state``) and records a
        STATE_CHANGE entry to the change audit log if configured. Audit log
        failure is non-fatal (debug-logged only).

        清除 TTL 授權快取；若 change_audit_log 已注入則記錄 STATE_CHANGE。
        審計失敗不會中斷流程（僅 debug log）。
        """
        self._cached_auth_state = None
        # Record authorization cache invalidation / 記錄授權快取失效
        if self._change_audit_log:
            try:
                self._change_audit_log.record_change(
                    change_type=ChangeType.STATE_CHANGE,
                    who="GovernanceHub",
                    what="Authorization cache invalidated",
                    reason="State machine transition detected",
                    auto_approve=True,
                )
            except Exception as e:
                logger.debug("ChangeAuditLog record failed (non-fatal): %s", e)

    # ── De-escalation gate helper / 降級門禁輔助 ────────────────────────────

    def _check_de_escalation_gate(
        self, from_state: str, to_state: str, reason: str,
    ) -> bool:
        """
        Check if de-escalation is permitted via RecoveryApprovalGate.
        檢查降級是否通過 RecoveryApprovalGate 批准。

        De-escalation requires approval unless gate is not installed.
        降級需經審批，除非未裝設 gate。

        Args:
            from_state: Current state (more restrictive) / 目前狀態（較嚴格）
            to_state: Target state (less restrictive) / 目標狀態（較寬鬆）
            reason: Reason for de-escalation / 降級理由

        Returns:
            True if de-escalation is permitted; False otherwise.
            允許降級返回 True，否則 False。
        """
        if not self._recovery_gate:
            # No gate installed, allow by default / 未裝 gate 預設放行
            return True

        # Check if pending approvals exist for this transition
        # 檢查是否有針對該轉換的待審批請求
        pending = self._recovery_gate.get_pending_requests()
        for req in pending:
            if (
                req.get("from_state") == from_state
                and req.get("to_state") == to_state
            ):
                return False  # De-escalation pending approval / 正在等待審批

        return True
