from __future__ import annotations

"""
MODULE_NOTE (中文):
  FastAPI 应用主入口模块，在 main_legacy 基础上叠加快照稳定性编译与 runtime bridge 覆盖。
  负责状态读写的确定性重编译（snapshot identity 不变性）、runtime 事实层叠加、以及
  所有子路由（Paper Trading / L2 AI / Risk / Strategy / Governance / Scout）的统一注册。
  属于 Control API v1 层，是系统唯一的 HTTP 服务暴露点。

MODULE_NOTE (English):
  Main FastAPI application entry point, layering snapshot-stable compilation and a
  runtime bridge on top of main_legacy. Responsible for deterministic state recompilation
  (preserving snapshot identity on reads), runtime fact overlay, and unified registration
  of all sub-routers (Paper Trading / L2 AI / Risk / Strategy / Governance / Scout).
  Part of the Control API v1 layer; serves as the single HTTP service exposure point.

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
    Delegates to _do_compile_core (shared helper in state_compiler) to eliminate
    duplication with compile_state(). include_learning=False preserves the original
    stable_compile_state behavior (no L-chapter learning derived fields).
    委托给 state_compiler._do_compile_core（共享编译核心），消除与 compile_state
    的代码重复。include_learning=False 保留原始 stable_compile_state 行为。
    """
    compiled = copy.deepcopy(state)
    return base._do_compile_core(
        compiled,
        refresh_identity=refresh_identity,
        include_learning=False,
    )


def _patched_read(self) -> dict[str, Any]:
    with self._lock:
        with self.file_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return stable_compile_state(payload, refresh_identity=False)


def _patched_write(self, state: dict[str, Any]) -> dict[str, Any]:
    with self._lock:
        # Invalidate compile cache on write (B6 dirty-flag).
        # 写入时使编译缓存失效（B6 脏标志）。
        base.mark_compile_dirty()
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

# ── Backtest Engine Router / 回測引擎路由注册 ──
from .backtest_routes import router as backtest_router  # noqa: E402
app.include_router(backtest_router)

# ── Experiment Ledger Router / 實驗假設管理路由注册 ──
from .experiment_routes import router as experiment_router  # noqa: E402
app.include_router(experiment_router)

# ── Evolution Engine Router / 進化引擎路由注册 ──
from .evolution_routes import router as evolution_router  # noqa: E402
app.include_router(evolution_router)

# ── PnL Attribution Router / PnL 歸因分析路由注册 ──
from .attribution_routes import attribution_router  # noqa: E402
app.include_router(attribution_router)

# ── AI Budget Router / AI 預算路由注册 ──
from .ai_budget_routes import router as ai_budget_router  # noqa: E402
app.include_router(ai_budget_router)

# ── Settings Router / 設置路由注册（API key 管理）──
from .settings_routes import settings_router  # noqa: E402
app.include_router(settings_router)

# ── Live Session Router / 實盤 Session 路由注册 ──
from .live_session_routes import live_router  # noqa: E402
app.include_router(live_router)

# ── Startup Integrity Check / 啟動完整性驗證 ────────────────────────────────
# Verify that non-optional critical dependencies were successfully injected at
# module initialisation time.  H0_GATE is allowed to be None in degraded /
# test environments; the hub/risk dependencies must always be present —
# if they are None the server must not start.
# DEAD-PY-2: PIPELINE_BRIDGE removed (always None, intentional).
# 驗證非可選關鍵依賴在模塊初始化時已成功注入。
# H0_GATE 允許為 None（降級/測試環境）；
# 其餘依賴必須存在 — 若為 None 則服務拒絕啟動。

# DEAD-PY-2: SymbolCategoryRegistry soft import removed (no longer seeded from startup).
# SymbolCategoryRegistry is still used at runtime via symbol_category_registry.py directly.

# ── Startup Readiness State（模塊頂層，GIL 保護，dict key-level 替換是原子操作）──
# Tracks background init progress. GUI polls /api/v1/system/startup-status to detect readiness.
# 追蹤背景初始化進度。GUI 輪詢端點確認就緒狀態，取代盲等 2s。
_STARTUP_STATE: dict[str, dict] = {
    "symbol_registry": {"status": "pending"},  # pending | initializing | ready | failed | error
}

@app.on_event("startup")
async def _startup_integrity_check() -> None:
    """Startup integrity check — fail-closed if non-optional deps are missing.
    啟動完整性驗證 — 非可選依賴缺失時 fail-closed 拒絕啟動。

    ARCHITECTURE RULE（嚴禁違反 / DO NOT VIOLATE）:
      This handler MUST complete in < 100ms.
      ALL slow I/O operations (HTTP, file, time.sleep) MUST be offloaded to daemon threads.
      此 handler 必須在 < 100ms 內完成。
      所有慢速 I/O（HTTP、文件、sleep）必須放入 daemon thread 執行。

      ✅ DO:   threading.Thread(target=slow_fn, daemon=True).start()
      ❌ NEVER: await asyncio.to_thread(anything_with_network_io)
      ❌ NEVER: await httpx/aiohttp/requests calls
      ❌ NEVER: time.sleep(), urllib.request.urlopen() without thread offload

      Reference pattern: ccbed0d (pipeline_bridge K-line bootstrap fix)
                         This file Phase 4 (SymbolCategoryRegistry daemon thread)
    """
    import time as _time
    _t0 = _time.monotonic()
    from .paper_trading_routes import GOV_HUB, ENGINE, RISK_MANAGER, H0_GATE  # noqa: PLC0415
    # Hard-required: these must never be None in any environment
    # 硬性要求：任何環境下均不得為 None
    _hard_required: dict[str, object] = {
        "governance_hub (GOV_HUB)": GOV_HUB,
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
    # DEAD-PY-2: PIPELINE_BRIDGE removed from soft deps (always None, intentional).
    _soft_required: dict[str, object] = {
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

    # ── Auto-reauth on startup: if active paper session exists but no auth, re-grant ──
    # 啟動時自動重授權：如果存在活躍 paper session 但 GovernanceHub 無有效授權，自動補授權。
    # Root cause: grant_paper_authorization() is only called on POST /paper/session/start.
    # On server restart, the existing session is loaded from state file without triggering start.
    # Fix: check session state on startup and re-grant authorization if needed (fail-open).
    # 根因：grant_paper_authorization() 只在 POST /paper/session/start 時調用。
    # 服務器重啟後，現有 session 從文件載入，不會重新觸發 start，導致授權缺失。
    # 修復：啟動時檢查 session 狀態，若需要則補授權（fail-open，不阻斷啟動）。
    try:
        from .ipc_state_reader import get_rust_reader as _get_rust_reader
        _rust_reader = _get_rust_reader()
        _session_state = _rust_reader.get_paper_state() if _rust_reader.is_available() else None
        # Rust snapshot is flat: {balance, positions, ...} — if it exists, engine is active
        # Rust 快照是扁平結構 — 存在即表示引擎在運行
        _is_active = _session_state is not None

        if _is_active and GOV_HUB is not None:
            if not GOV_HUB.is_authorized():
                _granted = GOV_HUB.grant_paper_authorization()
                if _granted:
                    base.logger.info(
                        "Startup auto-reauth: active paper session detected, paper authorization re-granted "
                        "/ 啟動自動重授權：檢測到活躍 paper session，已補授 paper 授權"
                    )
                else:
                    base.logger.warning(
                        "Startup auto-reauth: active paper session but grant_paper_authorization() returned False "
                        "/ 啟動自動重授權：活躍 session 但 grant_paper_authorization() 返回 False"
                    )
            else:
                base.logger.info(
                    "Startup auto-reauth: paper authorization already active — no-op "
                    "/ 啟動自動重授權：授權已有效，跳過"
                )
    except Exception as _reauth_exc:
        # fail-open: must not block startup
        # fail-open：不阻斷啟動
        base.logger.warning(
            "Startup auto-reauth failed (fail-open): %s / 啟動自動重授權失敗（不阻斷）：%s",
            _reauth_exc, _reauth_exc,
        )

    # DEAD-PY-2: SymbolCategoryRegistry→PipelineBridge seeding block removed.
    # PipelineBridge is gone; SymbolCategoryRegistry seeding into the Rust engine
    # is handled by the Rust side directly.
    # DEAD-PY-2：SymbolCategoryRegistry→PipelineBridge 注入塊已刪除。
    # PipelineBridge 已移除；Rust 引擎端直接管理 registry。

    # ── Phase 3: ExperimentLedger startup auto-seed from TruthSourceRegistry snapshot ──
    # 啟動時從 TruthSourceRegistry 快照自動填充初始假設（fail-open，不阻斷啟動）
    # On startup, auto-seed ExperimentLedger from persisted TruthSourceRegistry snapshot.
    # fail-open: any failure must not block startup.
    # APR01-P0-1: Use the singleton (which already loaded from disk) instead of a
    # throwaway instance. This ensures Agents and auto-seed share the same registry.
    # APR01-P0-1：使用单例（已从磁盘加载）而非创建临时实例，确保 Agents 和
    # auto-seed 共享同一个 registry。
    try:
        from .experiment_routes import get_experiment_ledger  # noqa: PLC0415
        from .truth_source_registry import get_truth_registry  # noqa: PLC0415
        _seed_registry = get_truth_registry()
        _all_claims = _seed_registry.get_all_claims()
        if _all_claims:
            _ledger = get_experiment_ledger()
            seeded = _ledger.auto_seed_from_claims(
                list(_all_claims.values()),
                min_confidence=0.5,
            )
            base.logger.info(
                "Startup auto-seed: %d claims in registry, seeded %d hypotheses / "
                "啟動自動填充：registry 中 %d 條 claim，生成 %d 個假設",
                len(_all_claims), seeded, len(_all_claims), seeded,
            )
    except Exception as _e:
        # fail-open：自動填充失敗不阻斷啟動 / fail-open: auto-seed failure must not block startup
        base.logger.warning("ExperimentLedger startup auto-seed failed (fail-open): %s", _e)

    # ── Phase 3C: Evolution auto-scheduler startup (fail-open) ──────────────
    # 啟動進化自動排程器（fail-open，不阻斷啟動）
    # Start evolution auto-scheduler (fail-open; must not block startup).
    try:
        from .evolution_auto_scheduler import start_scheduler  # noqa: PLC0415
        start_scheduler()
        base.logger.info(
            "EvolutionScheduler started / 進化排程器已啟動"
        )
    except Exception as _sched_exc:
        base.logger.warning(
            "EvolutionScheduler startup failed (fail-open): %s / 進化排程器啟動失敗（不阻斷）：%s",
            _sched_exc, _sched_exc,
        )

    # ── OC-3 / 6-RC-6: Reconciler governor-tier alert monitor ────────────────
    # 啟動對帳器 governor tier 告警監控（fail-open，不阻斷啟動）
    # asyncio.create_task is non-blocking: schedules coroutine for the event loop.
    # asyncio.create_task 非阻塞：將協程排入事件循環，不影響 < 100ms 要求。
    try:
        import asyncio as _asyncio_startup  # noqa: PLC0415
        from .paper_trading_wiring import reconciler_alert_monitor as _recon_monitor  # noqa: PLC0415
        _asyncio_startup.create_task(
            _recon_monitor(),
            name="reconciler-alert-monitor",
        )
        base.logger.info(
            "OC-3 reconciler_alert_monitor scheduled / OC-3 對帳器告警監控已排程"
        )
    except Exception as _oc3_exc:
        base.logger.warning(
            "OC-3 monitor startup failed (fail-open): %s / OC-3 監控啟動失敗（不阻斷）：%s",
            _oc3_exc, _oc3_exc,
        )

    _elapsed_ms = (_time.monotonic() - _t0) * 1000
    base.logger.info(
        "Startup handler completed in %.1f ms (target < 100 ms) "
        "/ 啟動 handler 耗時 %.1f ms（目標 < 100 ms）",
        _elapsed_ms, _elapsed_ms,
    )
    if _elapsed_ms > 500:
        base.logger.warning(
            "Startup handler took %.1f ms — exceeds 500 ms budget. "
            "Check for blocking await calls above. / 啟動 handler 耗時超過 500 ms，請檢查是否有阻塞 await",
            _elapsed_ms,
        )


@app.get("/api/v1/system/startup-status", include_in_schema=False)
async def _system_startup_status():
    """
    Returns background initialization progress. No auth required — read-only public metadata.
    返回背景初始化進度。不需認證，僅返回只讀公開元數據（無業務數據、無授權信息）。

    GUI polls this after server restart to know when HTTP service is accepting requests.
    GUI 在服務器重啟後輪詢此端點，確認 HTTP 服務已就緒。

    Response:
      server: "up" — always present when this endpoint responds
      background_init: dict per component {"status": pending|initializing|ready|failed|error}
      all_ready: true when all background tasks have completed (success or failure)
    """
    all_ready = all(
        v.get("status") in ("ready", "failed", "error")
        for v in _STARTUP_STATE.values()
    )
    return {"server": "up", "background_init": _STARTUP_STATE, "all_ready": all_ready}


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
