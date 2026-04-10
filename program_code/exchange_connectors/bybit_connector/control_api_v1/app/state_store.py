"""
MODULE_NOTE (中文):
  狀態存儲模塊。包含 JsonStateStore（線程安全 JSON 文件讀寫 + 原子寫入）
  和 build_default_state()（初始狀態構建器）。
  從 main_legacy.py 拆分而來。

  ★ Monkey-patch 安全說明：main.py 在啟動時完全替換 JsonStateStore.read/write/mutate
  方法，因此本模塊內部對 compile_state/_compile_for_response 的引用在生產環境中
  為死代碼。保留這些引用是為了支持直接導入 main_legacy 的測試路徑。

MODULE_NOTE (English):
  State store module. Contains JsonStateStore (thread-safe JSON file read/write
  with atomic writes) and build_default_state() (initial state builder).
  Extracted from main_legacy.py.

  ★ Monkey-patch safety note: main.py completely replaces JsonStateStore.read/write/mutate
  methods at startup, so internal references to compile_state/_compile_for_response in this
  module are dead code in production. These references are retained to support test paths
  that import main_legacy directly.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from .state_compiler import (
    PRODUCT_FAMILIES,
    _compile_for_response,
    _permission_block,
    compile_state,
    mark_compile_dirty,
    now_ms,
)

logger = logging.getLogger(__name__)


def build_default_state() -> dict[str, Any]:
    ts = now_ms()
    product_families: dict[str, Any] = {}
    capability_product_families: dict[str, Any] = {}
    permission_by_pf: dict[str, Any] = {}

    for pf in PRODUCT_FAMILIES:
        visible = pf == "spot"
        product_families[pf] = {
            "facts": {
                "exchange_permission_fact": "readonly_visible",
                "account_permission_fact": "readonly_visible",
            },
            "controls": {
                "enabled_switch": False,
                "visibility_switch": visible,
                "mode_switch": "disabled",
            },
            "derived": {
                "capability_state": "visible_only" if visible else "unavailable",
                "execution_authority_state": "disabled",
                "product_family_summary": "visible_but_disabled" if visible else "hidden",
            },
            "audit": {"last_change_ts_ms": None, "last_change_by": None},
        }
        capability_product_families[pf] = {
            "visibility_capability_state": "implemented",
            "control_plane_capability_state": "implemented" if pf == "spot" else "reserved",
            "execution_capability_state": "reserved",
        }
        permission_by_pf[pf] = _permission_block(False)

    state = {
        "meta": {
            "schema_name": "openclaw_bybit_state_dictionary",
            "document_version": "v1",
            "schema_version": "v1",
            "api_version": "v1",
            "snapshot_ts_ms": ts,
            "state_revision": 1,
            "environment": "local_dev",
            "repo_branch": "feature/openclaw-bybit-control-api-gui-v1-rc2",
            "repo_commit_short": "",
            "state_compiler_version": "control_api_v1_mvp",
            "snapshot_source_summary": {
                "runtime_latest_used": False,
                "canonical_recheck_used": True,
                "functional_closeout_used": True,
                "telemetry_used": True,
                "manual_inputs_used": True,
            },
        },
        "global_runtime": {
            "facts": {
                "system_mode_fact": "design_only",
                "execution_state_fact": "execution_disabled",
                "runtime_last_refresh_ts_ms": ts,
                "runtime_data_freshness_state": "fresh",
            },
            "controls": {
                "global_execution_mode_switch": "disabled",
                "global_operator_mode_switch": "manual_only",
            },
            "derived": {
                "global_stage_label": "design_only_gate_closed",
                "global_mode_state": "design_only",
                "global_capability_state": "shadow_control_ready",
                "global_execution_authority_state": "disabled",
                "runtime_still_protected": True,
                "overview_blocker_summary": ["global_execution_blocked"],
            },
            "audit": {
                "last_runtime_state_change_ts_ms": None,
                "last_runtime_state_change_by": None,
            },
        },
        "chapter_status": {
            "I": {
                "chapter_display_name": "I (Decision Lease Control Plane)",
                "chapter_state": "canonical_closed",
                "chapter_interpretation": "shadow_only_decision_lease_control_plane_closed",
                "current_phase_ready": True,
                "readiness_scope": "shadow_closeout",
                "execution_meaning": "does_not_grant_live_execution",
                "last_verified_ts_ms": ts,
                "source_of_truth": "canonical_recheck",
            },
            "J": {
                "chapter_display_name": "J (Functional Closeout / Shadow)",
                "chapter_state": "canonical_closed",
                "chapter_interpretation": "functional_closeout_ready_shadow_only",
                "current_phase_ready": True,
                "readiness_scope": "shadow_closeout",
                "execution_meaning": "does_not_grant_live_execution",
                "last_verified_ts_ms": ts,
                "source_of_truth": "closeout",
            },
            "K": {
                "chapter_display_name": "K (Functional Closeout / Design Gate)",
                "chapter_state": "canonical_closed",
                "chapter_interpretation": "functional_closeout_ready_design_only_gate_closed",
                "current_phase_ready": True,
                "readiness_scope": "design_only_gate_closed",
                "execution_meaning": "design_only_gate_closed_not_enabled",
                "last_verified_ts_ms": ts,
                "source_of_truth": "closeout",
            },
            # ── L 章：学习 / 自我感知 / Net PnL ──
            # L Chapter: Learning / Self-Observability / Net PnL
            "L": {
                "chapter_display_name": "L (Learning / Self-Observability / Net PnL)",
                "chapter_state": "implemented",
                "chapter_interpretation": "learning_observe_and_record_active",
                "current_phase_ready": True,
                "readiness_scope": "observe_and_record_only",
                "execution_meaning": "does_not_grant_live_execution",
                "last_verified_ts_ms": ts,
                "source_of_truth": "learning_state",
            },
        },
        "product_family_status": product_families,
        "control_plane": {
            "execution_control_summary": {
                "global_execution_mode_switch_summary": "disabled",
                "global_operator_mode_switch_summary": "manual_only",
            },
            "demo_control": {
                "demo_state_switch": "closed",
                "demo_validate_requested": False,
                "demo_operator_ack_required": True,
                "demo_operator_ack_completed": False,
                "demo_prerequisites_gate_state": "not_evaluated",
                "demo_prerequisites_reason_codes": [],
                "demo_prerequisites_last_evaluated_ts_ms": None,
                "demo_arm_gate_state": "blocked",
                "demo_arm_reason_codes": ["prerequisites_not_passed"],
                "demo_arm_last_evaluated_ts_ms": None,
                "demo_enable_gate_state": "blocked",
                "demo_enable_reason_codes": ["not_armed"],
                "demo_enable_last_evaluated_ts_ms": None,
                "demo_relock_gate_state": "passed",
                "demo_relock_reason_codes": [],
                "demo_relock_last_evaluated_ts_ms": None,
                "demo_last_action_type": None,
                "demo_last_action_result": None,
                "demo_last_action_reason_codes": [],
                "demo_last_action_ts_ms": None,
                "demo_cooldown_state": "inactive",
                "demo_cooldown_until_ts_ms": None,
            },
            "action_permissions": {
                "global": _permission_block(False),
                "by_product_family": permission_by_pf,
            },
            "health_gate_summary": {
                "health_gates_overall_state_summary": "not_evaluated",
                "exchange_timeout_gate_state_summary": "not_evaluated",
                "ws_disconnect_gate_state_summary": "not_evaluated",
                "latency_gate_state_summary": "not_evaluated",
                "freshness_gate_state_summary": "not_evaluated",
            },
            "risk_envelope": {
                "risk_policy_switch": "default_guarded",
                "risk_policy_profile": "default",
                "effective_risk_envelope_state": "configured",
            },
        },
        "capability_matrix": {
            "J": {
                "canonical_recheck_state": "passed",
                "closeout_state": "passed",
                "canonical_recheck_last_verified_ts_ms": ts,
                "closeout_last_verified_ts_ms": ts,
            },
            "K": {
                "canonical_recheck_state": "passed",
                "closeout_state": "passed",
                "canonical_recheck_last_verified_ts_ms": ts,
                "closeout_last_verified_ts_ms": ts,
            },
            "product_families": capability_product_families,
        },
        "business_metrics": {
            "daily": {
                "window_start_ts_ms": ts,
                "window_end_ts_ms": ts,
                "window_timezone": "Europe/Madrid",
                "reporting_currency": "USDT",
                "fx_rate_source": "bybit_mark_or_manual_config",
                "valuation_basis": "mark",
                "realized_pnl": 0,
                "unrealized_pnl": 0,
                "gross_pnl": 0,
                "total_cost": 0,
                "net_operating_pnl": 0,
                "manual_cost_included": True,
                "manual_cost_source_count": 0,
                "business_event_count": 0,
            },
            # ── L 章周期快照 / L-chapter period snapshots ──
            # 用于 Net PnL 趋势追踪：Operator 手动保存当前经营指标快照。
            # For Net PnL trend tracking: Operator manually saves current business metrics snapshot.
            "period_snapshots": [],
        },
        "health_telemetry": {
            "scores": {
                "overall_health_score": 100,
                "ai_health_score": 100,
                "exchange_health_score": 100,
                "infra_health_score": 100,
                "data_freshness_score": 100,
            },
            "metrics": {
                "avg_ai_latency_ms": 0,
                "exchange_timeout_count": 0,
                "ws_disconnect_count": 0,
                "runtime_stale_count": 0,
            },
            "evaluation_context": {
                "evaluation_window_sec": 300,
                "sample_count": 0,
                "last_evaluated_ts_ms": ts,
                "threshold_basis": "rolling_window",
            },
            "gates": {
                "health_gates_overall_state": "passed",
                "exchange_timeout_gate_state": "passed",
                "ws_disconnect_gate_state": "passed",
                "latency_gate_state": "passed",
                "freshness_gate_state": "passed",
            },
        },
        "learning_state": {
            "observation_summary": {
                "last_observation_ts_ms": None,
                "recent_lessons_count": 0,
                "recent_hypothesis_count": 0,
                "recent_experiment_proposal_count": 0,
            },
            "memory": {"lessons_memory_state": "active", "last_memory_update_ts_ms": None},
            "hypotheses": {"active_hypothesis_count": 0, "last_hypothesis_ts_ms": None},
            "experiments": {
                "approval_required": True,
                "active_experiment_count": 0,
                "last_experiment_proposal_ts_ms": None,
            },
            "derived": {"learning_progression_state": "observe_and_record_only"},
            # ── L 章学习记录存储 / L-chapter learning record storage ──
            # observations: 观察流记录 / Observation feed records
            # lessons: 经验教训记录 / Lessons memory records
            # hypotheses: 假设队列 / Hypothesis queue
            # experiments: 实验队列 / Experiment queue
            # manual_notes: 手动备注（已有）/ Manual notes (existing)
            "records": {
                "observations": [],
                "lessons": [],
                "hypotheses": [],
                "experiments": [],
                "manual_notes": [],
                "review_queue": [],
            },
            # ── 自动学习管线摘要 / Auto learning pipeline summary ──
            "auto_pipeline": {
                "last_observation_scan_ts_ms": None,
                "last_lesson_scan_ts_ms": None,
                "last_hypothesis_scan_ts_ms": None,
                "total_packets_generated": 0,
                "total_packets_approved": 0,
                "total_packets_rejected": 0,
            },
        },
        "audit_context": {
            "last_operator_action_type": None,
            "last_operator_action_ts_ms": None,
            "last_operator_action_result": None,
            "last_operator_action_operator": None,
            "last_operator_action_target": None,
            "last_operator_action_request_id": None,
            "last_operator_action_reason_codes": [],
            "last_operator_action_audit_ref": None,
            "last_state_revision_before": None,
            "last_state_revision_after": None,
            "last_control_action_type": None,
            "last_control_action_request_id": None,
            "last_control_action_ts_ms": None,
            "last_control_action_by": None,
            "last_control_action_result": None,
            "last_control_action_reason_codes": [],
            "last_control_action_audit_ref": None,
            "last_write_action_type": None,
            "last_write_action_request_id": None,
            "last_write_action_ts_ms": None,
            "last_write_action_by": None,
            "last_write_action_result": None,
            "last_write_action_reason_codes": [],
            "last_write_action_audit_ref": None,
        },
        "records": {
            "idempotency": {},
            "cost_entries": [],
            "event_entries": [],
        },
    }
    return compile_state(state)


class JsonStateStore:
    def __init__(self, file_path: str) -> None:
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._lock = threading.RLock()
        if not self.file_path.exists():
            self.write(build_default_state())

    def read(self) -> dict[str, Any]:
        with self._lock:
            try:
                with self.file_path.open("r", encoding="utf-8") as handle:
                    payload = json.load(handle)
            except (json.JSONDecodeError, FileNotFoundError, OSError) as e:
                logger.error("State file read error, returning default state / 状态文件读取异常: %s", e)
                payload = build_default_state()
            compiled = compile_state(payload)
            if compiled != payload:
                self.write(compiled)
            return compiled

    def write(self, state: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            # Invalidate compile cache on write (B6 dirty-flag).
            # 写入时使编译缓存失效（B6 脏标志）。
            mark_compile_dirty()
            compiled = _compile_for_response(state)
            # Atomic write: write to temp file, then rename (prevents corruption on crash)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self.file_path.parent),
                prefix=".state_tmp_",
                suffix=".json",
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(compiled, handle, ensure_ascii=False, indent=2)
                os.replace(tmp_path, str(self.file_path))
            except BaseException:
                # Clean up temp file on failure
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            # 限制状态文件权限：仅 owner 可读写 / Restrict state file: owner read/write only
            os.chmod(str(self.file_path), 0o600)
            return compiled

    def mutate(self, mutator) -> dict[str, Any]:
        with self._lock:
            current = self.read()
            mutated = mutator(copy.deepcopy(current))
            return self.write(mutated)
