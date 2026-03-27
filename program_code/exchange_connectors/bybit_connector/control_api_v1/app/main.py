from __future__ import annotations

"""
OpenClaw / Bybit Control API + GUI
OpenClaw / Bybit 控制 API 与 GUI 默认入口（快照稳定版 + runtime bridge）

说明 / Notes:
- 当前默认入口已经通过 snapshot identity 稳定性验证。
- The current default entrypoint has passed snapshot identity stability validation.
- 可选接入 runtime snapshot bridge，从外部 runtime JSON 快照读取真实事实。
- Optionally integrates a runtime snapshot bridge to read real facts from an external runtime JSON snapshot.
- 若需回滚旧实现，请使用 `app.main_legacy:app`。
- To roll back to the old implementation, use `app.main_legacy:app`.
"""

import copy
import json
from typing import Any

from . import main_legacy as base
from .runtime_bridge import (
    build_runtime_aware_source_context,
    derive_response_snapshot_identity,
    overlay_runtime_facts,
)


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
    with self._lock:
        with self.file_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return stable_compile_state(payload, refresh_identity=False)


def _patched_write(self, state: dict[str, Any]) -> dict[str, Any]:
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


def runtime_aware_build_source_context(snapshot: dict[str, Any]) -> Any:
    return build_runtime_aware_source_context(snapshot, base.settings, base.SourceContext)


def runtime_aware_get_latest_snapshot() -> tuple[dict[str, Any], Any]:
    snapshot = base.STORE.read()
    merged_snapshot = overlay_runtime_facts(snapshot)
    return merged_snapshot, runtime_aware_build_source_context(merged_snapshot)


def runtime_aware_envelope_response(
    *,
    snapshot: dict[str, Any],
    request_id: str | None,
    action_result: str,
    data: Any,
    audit_ref: str | None = None,
    reason_codes: list[str] | None = None,
) -> Any:
    source_context = runtime_aware_build_source_context(snapshot)
    response_snapshot_ts_ms, response_snapshot_id = derive_response_snapshot_identity(snapshot, source_context)
    return base.ResponseEnvelope[Any](
        api_version=base.settings.api_version,
        schema_version=base.settings.schema_version,
        request_id=request_id,
        snapshot_ts_ms=response_snapshot_ts_ms,
        snapshot_id=response_snapshot_id,
        state_revision=snapshot["meta"]["state_revision"],
        action_result=action_result,
        reason_codes=reason_codes or [],
        warnings=[],
        audit_ref=audit_ref,
        source_context=source_context,
        data=data,
    )


base.compile_state = stable_compile_state
base.JsonStateStore.read = _patched_read
base.JsonStateStore.write = _patched_write
base.JsonStateStore.mutate = _patched_mutate
base.STORE = base.JsonStateStore(base.settings.state_file_path)
base.build_source_context = runtime_aware_build_source_context
base.get_latest_snapshot = runtime_aware_get_latest_snapshot
base.envelope_response = runtime_aware_envelope_response

app = base.app

# ── Paper Trading Router / 纸上交易路由注册 ──
from .paper_trading_routes import paper_router  # noqa: E402
app.include_router(paper_router)

# ── Layer 2 AI Reasoning Engine Router / L2 AI 推理引擎路由注册 ──
from .layer2_routes import layer2_router  # noqa: E402
app.include_router(layer2_router)

# ── Risk Control Router / 风控路由注册 ──
from .risk_routes import risk_router  # noqa: E402
app.include_router(risk_router)

# ── Phase 2 Strategy Toolkit Router / Phase 2 本地策略工具包路由注册 ──
from .phase2_strategy_routes import phase2_router  # noqa: E402
app.include_router(phase2_router)
