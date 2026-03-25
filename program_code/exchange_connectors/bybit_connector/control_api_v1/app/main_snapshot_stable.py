from __future__ import annotations

"""
Snapshot-stable entrypoint for OpenClaw / Bybit Control API.
OpenClaw / Bybit 控制 API 的快照稳定版入口。

Why this file exists / 为什么需要这个入口：
- 当前 MVP 已可启动，但审计上发现纯 GET 会导致 `snapshot_id` 漂移。
- The current MVP is runnable, but audit validation found that pure GET requests could drift `snapshot_id`.
- 这里采用最小侵入方式，对现有 `app.main` 进行补丁化修复。
- This file applies a minimal-intrusion patch on top of the existing `app.main`.

Current usage / 当前用法：
- `uvicorn app.main_snapshot_stable:app --host 0.0.0.0 --port 8710`
"""

import copy
import json
from types import MethodType
from typing import Any

from . import main as base


def stable_compile_state(state: dict[str, Any], *, refresh_identity: bool) -> dict[str, Any]:
    """
    Recompile derived fields while keeping snapshot identity stable on read.
    只读路径不刷新 snapshot 身份；写入路径才刷新。
    """
    compiled = copy.deepcopy(state)

    if refresh_identity:
        compiled["meta"]["snapshot_ts_ms"] = base.now_ms()

    compiled["global_runtime"]["derived"]["global_mode_state"] = base._compile_global_mode_state(compiled)
    compiled["global_runtime"]["derived"]["global_stage_label"] = base._compile_global_stage_label(compiled)
    compiled["control_plane"]["risk_envelope"]["effective_risk_envelope_state"] = base._compile_effective_risk_envelope_state(compiled)
    base._compile_demo_gate_states(compiled)
    compiled["global_runtime"]["derived"]["global_execution_authority_state"] = base._compile_global_execution_authority_state(compiled)
    compiled["global_runtime"]["derived"]["global_capability_state"] = base._compile_global_capability_state(compiled)
    base._compile_effective_action_permissions(compiled)

    for pf in base.PRODUCT_FAMILIES:
        base._compile_product_family_derived(compiled, pf)

    compiled["global_runtime"]["derived"]["runtime_still_protected"] = (
        compiled["global_runtime"]["derived"]["global_execution_authority_state"] != "demo_enabled"
        and compiled["global_runtime"]["controls"]["global_execution_mode_switch"] != "live_reserved"
    )

    blockers: list[str] = []
    if compiled["global_runtime"]["controls"]["global_execution_mode_switch"] == "disabled":
        blockers.append("global_execution_blocked")
    if compiled["control_plane"]["demo_control"]["demo_state_switch"] != "demo_enabled":
        blockers.append("demo_not_enabled")
    if compiled["control_plane"]["risk_envelope"]["effective_risk_envelope_state"] == "blocking":
        blockers.append("risk_scope_blocked")
    compiled["global_runtime"]["derived"]["overview_blocker_summary"] = blockers

    compiled["control_plane"]["execution_control_summary"] = {
        "global_execution_mode_switch_summary": compiled["global_runtime"]["controls"]["global_execution_mode_switch"],
        "global_operator_mode_switch_summary": compiled["global_runtime"]["controls"]["global_operator_mode_switch"],
    }
    compiled["control_plane"]["health_gate_summary"] = {
        "health_gates_overall_state_summary": compiled["health_telemetry"]["gates"]["health_gates_overall_state"],
        "exchange_timeout_gate_state_summary": compiled["health_telemetry"]["gates"]["exchange_timeout_gate_state"],
        "ws_disconnect_gate_state_summary": compiled["health_telemetry"]["gates"]["ws_disconnect_gate_state"],
        "latency_gate_state_summary": compiled["health_telemetry"]["gates"]["latency_gate_state"],
        "freshness_gate_state_summary": compiled["health_telemetry"]["gates"]["freshness_gate_state"],
    }
    compiled["meta"]["snapshot_id"] = base.build_snapshot_id(compiled)
    return compiled


def _patched_read(self) -> dict[str, Any]:
    """
    Read without writing back refreshed snapshot identity.
    纯读取不回写新的 snapshot 身份。
    """
    with self._lock:
        with self.file_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return stable_compile_state(payload, refresh_identity=False)


def _patched_write(self, state: dict[str, Any]) -> dict[str, Any]:
    """
    Refresh snapshot identity only when the incoming state identity is stale.
    只有在输入状态身份过期时才刷新 snapshot。
    """
    with self._lock:
        compiled_without_refresh = stable_compile_state(state, refresh_identity=False)
        incoming_snapshot_id = state.get("meta", {}).get("snapshot_id")

        if incoming_snapshot_id != compiled_without_refresh["meta"]["snapshot_id"]:
            compiled = stable_compile_state(state, refresh_identity=True)
        else:
            compiled = compiled_without_refresh

        with self.file_path.open("w", encoding="utf-8") as handle:
            json.dump(compiled, handle, ensure_ascii=False, indent=2)
        return compiled


def _patched_mutate(self, mutator):
    with self._lock:
        current = _patched_read(self)
        mutated = mutator(copy.deepcopy(current))
        return _patched_write(self, mutated)


# Patch the existing module in place.
# 直接对现有模块打补丁。
base.compile_state = stable_compile_state
base.JsonStateStore.read = _patched_read
base.JsonStateStore.write = _patched_write
base.JsonStateStore.mutate = _patched_mutate
base.STORE = base.JsonStateStore(base.settings.state_file_path)

app = base.app
