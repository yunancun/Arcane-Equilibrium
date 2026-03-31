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

# ── Governance Hub Router / 治理集線器路由注册 ──
from .governance_routes import governance_router  # noqa: E402
app.include_router(governance_router)

# ── Scout Agent Router / Scout 代理路由注册 ──
from .scout_routes import scout_router  # noqa: E402
app.include_router(scout_router)

# ── Startup Integrity Check / 啟動完整性驗證 ────────────────────────────────
# Verify that non-optional critical dependencies were successfully injected at
# module initialisation time.  PIPELINE_BRIDGE and H0_GATE are allowed to be
# None in degraded / test environments; the three hub/engine/risk dependencies
# must always be present — if they are None the server must not start.
# 驗證非可選關鍵依賴在模塊初始化時已成功注入。
# PIPELINE_BRIDGE 和 H0_GATE 允許為 None（降級/測試環境）；
# 其餘三個依賴必須存在 — 若為 None 則服務拒絕啟動。
@app.on_event("startup")
async def _startup_integrity_check() -> None:
    """Startup integrity check — fail-closed if non-optional deps are missing.
    啟動完整性驗證 — 非可選依賴缺失時 fail-closed 拒絕啟動。
    """
    from .paper_trading_routes import GOV_HUB, ENGINE, RISK_MANAGER, H0_GATE  # noqa: PLC0415
    from .phase2_strategy_routes import PIPELINE_BRIDGE  # noqa: PLC0415

    # Hard-required: these must never be None in any environment
    # 硬性要求：任何環境下均不得為 None
    _hard_required: dict[str, object] = {
        "governance_hub (GOV_HUB)": GOV_HUB,
        "paper_engine (ENGINE)": ENGINE,
        "risk_manager (RISK_MANAGER)": RISK_MANAGER,
    }
    missing = [name for name, dep in _hard_required.items() if dep is None]
    if missing:
        base.logger.critical(
            "Startup integrity check FAILED — missing critical deps: %s", missing
        )
        raise RuntimeError(f"Startup integrity check failed: {missing}")

    # Soft-required: None is allowed (degraded mode), but log a warning
    # 軟性依賴：允許為 None（降級模式），但記錄警告
    _soft_required: dict[str, object] = {
        "pipeline_bridge (PIPELINE_BRIDGE)": PIPELINE_BRIDGE,
        "h0_gate (H0_GATE)": H0_GATE,
    }
    degraded = [name for name, dep in _soft_required.items() if dep is None]
    if degraded:
        base.logger.warning(
            "Startup integrity check: soft deps missing (degraded mode) — %s", degraded
        )

    base.logger.info(
        "Startup integrity check passed — hard deps all present%s",
        f"; degraded: {degraded}" if degraded else "",
    )


# ── OpenClaw Gateway Proxy / OpenClaw Gateway 反向代理 ──
# Proxies /openclaw/* to localhost:18789 so remote clients don't need direct access to port 18789
# 将 /openclaw/* 代理到 localhost:18789，远程客户端无需直接访问 18789 端口
import asyncio as _asyncio  # noqa: E402
import os as _oc_os  # noqa: E402
import urllib.request as _oc_urllib  # noqa: E402
from fastapi import Depends, Request  # noqa: E402
from fastapi.responses import Response  # noqa: E402

# P1-NEW-6: 模組頂層緩存 OPENCLAW_GATEWAY_HOST，避免每次請求重新讀取 env
# P1-NEW-6: Cache OPENCLAW_GATEWAY_HOST at module level to avoid per-request env lookup
_OC_HOST = _oc_os.getenv("OPENCLAW_GATEWAY_HOST", "127.0.0.1")

@app.api_route("/openclaw/{path:path}", methods=["GET", "POST", "PUT", "DELETE"], include_in_schema=False)
async def openclaw_proxy(path: str, request: Request, actor=Depends(base.current_actor)):
    """Reverse proxy to OpenClaw Gateway — requires authenticated actor / 需要已認證 Actor"""
    # Gateway binds to loopback when using --tailscale serve
    target = f"http://{_OC_HOST}:18789/{path}"
    try:
        body = await request.body()
        req = _oc_urllib.Request(
            target,
            data=body if body else None,
            # P1-NEW-1: 過濾 authorization header — Gateway 綁 loopback 信任域，不應接收用戶 Token
            # P1-NEW-1: Strip authorization header — Gateway is loopback-only trusted domain
            headers={k: v for k, v in request.headers.items() if k.lower() not in ("host", "transfer-encoding", "authorization")},
            method=request.method,
        )

        def _do_request():
            with _oc_urllib.urlopen(req, timeout=10) as resp:
                _content = resp.read()
                _headers = dict(resp.headers)
                _headers.pop("Transfer-Encoding", None)
                return _content, resp.status, _headers

        content, status_code, headers = await _asyncio.to_thread(_do_request)
        return Response(content=content, status_code=status_code, headers=headers)
    except _oc_urllib.HTTPError as e:
        return Response(content=e.read(), status_code=e.code)
    except Exception as e:
        # P1-NEW-5: 記錄代理異常，便於排障 / Log proxy errors for diagnostics
        base.logger.warning("openclaw_proxy error [%s]: %s", path, type(e).__name__)
        return Response(content=b'{"error":"OpenClaw Gateway unreachable"}', status_code=502)
