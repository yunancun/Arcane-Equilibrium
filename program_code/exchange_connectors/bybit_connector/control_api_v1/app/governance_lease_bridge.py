"""
Governance Lease Bridge — IPC bridge for Decision Lease retrofit (Sprint 3 H E-3).
治理租约桥接 — Decision Lease retrofit 的 IPC 桥接（Sprint 3 H E-3）。

MODULE_NOTE (EN):
    Thin bridge between Python ``GovernanceHub.acquire_lease()`` /
    ``release_lease()`` / ``get_lease()`` (legacy local SM call sites) and
    the Rust ``GovernanceCore`` facade landed by Sprint 3 Track H E-1.

    Roles / 職能:
      1. Encapsulate the IPC call site (one_shot_ipc_call against
         METHOD_ACQUIRE_LEASE / RELEASE / GET) so governance_hub.py stays
         small; one_shot helper handles connect → call → disconnect lifecycle
         with fail-closed semantics already in place.
      2. Provide caller-side SHADOW_BYPASS short-circuit (PA push back #2 HIGH)
         — when shadow_mode_provider() == True, return SHADOW_BYPASS sentinel
         WITHOUT engaging IPC; never write a lease_transitions audit row for
         a shadow path.
      3. Dual-write mirror (PA partition §1 + amendment §5.1 4-week period):
         maintain a thread-local dict[lease_id → metadata] so Python platform
         retains a read-through view while Rust SM is the source of truth.
         This is intentionally simple — no TTL eviction, no LRU, no DB
         persistence. After 4 weeks of zero divergence, the mirror is
         scheduled for removal.
      4. Backward-compat: callers see the existing simple types
         (acquire → Optional[str], release → bool, get → Optional[Lease]).
         Internal IPC payload schema is fully owned by lease_ipc_schema.py.

    Feature flag / 功能旗標:
      ``OPENCLAW_LEASE_PYTHON_IPC_ENABLED`` env var:
        - ``"1"`` → IPC bridge active (Phase 2+ rollout)
        - any other value (default unset) → fall back to legacy local SM via
          provided fallback callable (governance_hub.py legacy code path
          remains 100% intact for the Phase 1 baseline window).

      Strict equality with "1" (mirrors h_state_invalidator + executor cache
      env-gate pattern; "true" / "yes" do NOT enable). This pattern is the
      unwritten convention across the OpenClaw env-gates so operators have a
      single mental model.

    Singletons / 單例:
      None at module level. The bridge owns a thread-safe in-memory mirror
      dict (``_DUAL_WRITE_MIRROR``), but it is package-private and only
      mutated through ``record_dual_write_acquire`` /
      ``record_dual_write_release`` helpers.

MODULE_NOTE (中):
    在 Python ``GovernanceHub.acquire_lease()`` / ``release_lease()`` /
    ``get_lease()``（既有 local SM 呼叫點）與 Sprint 3 Track H E-1 落地的
    Rust ``GovernanceCore`` facade 之間提供薄橋接。

    四項職能:
      1. 封裝 IPC 呼叫點（針對 METHOD_ACQUIRE_LEASE/RELEASE/GET 的
         ``one_shot_ipc_call``），讓 governance_hub.py 保持精瘦；
         one_shot helper 已內建 connect→call→disconnect 生命周期 + fail-closed。
      2. caller 端 SHADOW_BYPASS 短路（PA push back #2 HIGH）：
         shadow_mode_provider() == True 時，回 SHADOW_BYPASS sentinel 但
         完全不啟動 IPC；也不會為 shadow 路徑寫入 lease_transitions audit。
      3. dual-write mirror（PA partition §1 + amendment §5.1 4 週期）：
         維護 thread-safe dict[lease_id → metadata]，讓 Python 平面持有
         read-through 視圖，Rust SM 為 source of truth。刻意精簡 — 無 TTL
         eviction、無 LRU、無 DB 持久化。4 週 0 divergence 後排程移除 mirror。
      4. backward-compat：caller 看到既有簡單型別（acquire → Optional[str]、
         release → bool、get → Optional[Lease]）。IPC payload schema 完全
         由 lease_ipc_schema.py 擁有。

    feature flag:
      ``OPENCLAW_LEASE_PYTHON_IPC_ENABLED`` env var 嚴格等於 "1" 時啟用 IPC，
      其他值 / 未設 → fallback 走既有 legacy local SM（governance_hub.py
      Phase 1 baseline 100% 不變）。

    模組層級無 singleton；mirror dict 為 package-private，只透過
    record_dual_write_* helper 變更。

Safety guarantees / 安全保證:
  - Fail-closed: IPC outage / timeout / malformed payload → fallback or None.
  - SHADOW_BYPASS path NEVER engages IPC.
  - feature flag default OFF → zero behavioral change at deploy time.
  - All mirror access guarded by threading.Lock.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from typing import Any, Awaitable, Callable, Mapping, Optional

from .lease_ipc_schema import (
    DEFAULT_SOURCE_STAGE_PY_EXECUTOR,
    METHOD_ACQUIRE_LEASE,
    METHOD_GET_LEASE,
    METHOD_RELEASE_LEASE,
    OUTCOME_ACTIVE,
    OUTCOME_BYPASS,
    OUTCOME_CONSUMED,
    OUTCOME_FAILED,
    PROFILE_PRODUCTION,
    build_acquire_request_params,
    build_get_request_params,
    build_release_request_params,
    is_shadow_bypass_lease_id,
    make_shadow_bypass_lease_id,
    parse_acquire_response,
    parse_get_response,
    parse_release_response,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Feature flag / 功能旗標
# ═══════════════════════════════════════════════════════════════════════════════

# Strict-equality env var read; mirrors h_state_invalidator + executor_config_cache
# pattern across the codebase. "1" enables; "true", "yes", "ENABLED" do NOT.
# 嚴格等值讀取；對齊 h_state_invalidator + executor_config_cache 慣例。
# 僅 "1" 啟用；"true"、"yes"、"ENABLED" 等不啟用。
LEASE_IPC_ENABLED_ENV: str = "OPENCLAW_LEASE_PYTHON_IPC_ENABLED"


def is_lease_ipc_enabled() -> bool:
    """Return True iff the IPC bridge is enabled by env var.
    當 env var 嚴格等於 "1" 時回 True。

    Returns / 回傳:
        True if the IPC bridge is active (Phase 2+ rollout); False for the
        Phase 1 baseline (legacy local SM fallback).
        IPC bridge 啟用時（Phase 2+）True；Phase 1 baseline（legacy local SM
        fallback）False。
    """
    return os.environ.get(LEASE_IPC_ENABLED_ENV, "") == "1"


# ═══════════════════════════════════════════════════════════════════════════════
# Dual-write mirror (4-week reconcile period) / 雙寫鏡像（4 週對賬期）
# ═══════════════════════════════════════════════════════════════════════════════

# Module-level mirror; package-private; mutated through helpers below.
# Schema: { lease_id: {"intent_id": str, "scope": str, "ttl_seconds": float,
#                      "source": "rs", "acquired_at": float, "released_at": Optional[float],
#                      "release_outcome": Optional[str]} }
# After 4 weeks of zero divergence between Rust SM and this dict, the mirror
# is scheduled for removal (PA partition §1 transitional period).
# 模組級 mirror；package-private；僅透過下方 helper 變更。
# schema：{ lease_id: { intent/scope/ttl/source/timestamps... } }
# Rust SM 與此 dict 4 週 0 divergence 後排程移除（PA partition §1 過渡期）。
_DUAL_WRITE_MIRROR: dict[str, dict[str, Any]] = {}
_DUAL_WRITE_LOCK = threading.Lock()


def record_dual_write_acquire(
    *,
    lease_id: str,
    intent_id: str,
    scope: str,
    ttl_seconds: float,
    source: str = "rs",
) -> None:
    """Record an IPC-acquired lease in the Python-side mirror.
    將 IPC 取得的 lease 記入 Python 端 mirror。

    Skipped silently for SHADOW_BYPASS sentinels (those never reach IPC).
    對 SHADOW_BYPASS sentinel 靜默跳過（這些不會進入 IPC）。
    """
    if is_shadow_bypass_lease_id(lease_id):
        return
    with _DUAL_WRITE_LOCK:
        _DUAL_WRITE_MIRROR[lease_id] = {
            "intent_id": intent_id,
            "scope": scope,
            "ttl_seconds": ttl_seconds,
            "source": source,
            "acquired_at": time.time(),
            "released_at": None,
            "release_outcome": None,
        }


def record_dual_write_release(
    *,
    lease_id: str,
    outcome: str,
) -> None:
    """Mark an existing mirror entry as released.
    將既有 mirror 條目標記為已釋放。
    """
    if is_shadow_bypass_lease_id(lease_id):
        return
    with _DUAL_WRITE_LOCK:
        entry = _DUAL_WRITE_MIRROR.get(lease_id)
        if entry is None:
            # Caller released a lease that was never acquire-mirrored; possibly
            # cross-process or test artifact. Log at debug, do not error.
            # caller 釋放一個從未 acquire 進 mirror 的 lease；可能跨進程或測試
            # 殘留。debug 級記錄，不報錯。
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "release recorded for unknown mirror entry: %s / "
                    "release 對應的 mirror 條目未知：%s",
                    lease_id, lease_id,
                )
            return
        entry["released_at"] = time.time()
        entry["release_outcome"] = outcome


def get_dual_write_mirror_snapshot() -> dict[str, dict[str, Any]]:
    """Return a defensive copy of the mirror (testing + observability).
    回傳 mirror 的防禦性副本（測試 + 可觀測性）。
    """
    with _DUAL_WRITE_LOCK:
        # Shallow copy is enough since inner dicts are not mutated after release;
        # nested dict.copy() defends against caller mutating the snapshot.
        # 內部 dict 在 release 後不再變更，淺拷貝足夠；對內部再 .copy() 防止
        # caller 變更 snapshot。
        return {k: dict(v) for k, v in _DUAL_WRITE_MIRROR.items()}


def reset_dual_write_mirror() -> None:
    """Clear the mirror (test isolation only; never call in production).
    清空 mirror（僅供測試隔離；勿於 production 呼叫）。
    """
    with _DUAL_WRITE_LOCK:
        _DUAL_WRITE_MIRROR.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# IPC dispatch helpers / IPC 派發輔助
# ═══════════════════════════════════════════════════════════════════════════════

# Type alias for the dispatcher injected into bridge methods.
# Real type: callable returning awaitable[dict[str, Any]] when given (method, params, timeout).
# Tests inject a fake dispatcher; production path uses ipc_dispatch.one_shot_ipc_call.
# 派發器型別別名。real type = (method, params, timeout) -> awaitable[dict]。
# 測試注入假派發器；production 走 ipc_dispatch.one_shot_ipc_call。
IPCDispatcher = Callable[..., Awaitable[Mapping[str, Any]]]


def _default_dispatcher() -> IPCDispatcher:
    """Lazy import the real one_shot_ipc_call dispatcher (avoids circular imports).
    延遲匯入 one_shot_ipc_call（避免循環匯入）。
    """
    from .ipc_dispatch import one_shot_ipc_call  # noqa: PLC0415

    async def _dispatch(method: str, params: Mapping[str, Any], timeout: float) -> Mapping[str, Any]:
        return await one_shot_ipc_call(
            method,
            params=dict(params),
            timeout=timeout,
            wrap_errors_as_http=False,           # caller decides policy (return None on err)
            error_context="lease_ipc",
        )

    return _dispatch


def _run_async_blocking(coro: Awaitable[Any], *, timeout: float) -> Any:
    """Run an awaitable to completion, blocking the calling thread.
    將 awaitable 阻塞執行至完成。

    governance_hub.acquire_lease() / release_lease() are sync callers (the
    legacy executor_agent.py:454 path is sync). Internally we run a fresh
    event loop for the IPC call so that we don't depend on an existing
    asyncio loop in the caller thread (governance_hub is invoked from sync
    threads in pytest fixtures + sync MessageBus dispatch).

    governance_hub.acquire_lease() / release_lease() 是 sync caller（legacy
    executor_agent.py:454 是 sync 路徑）。內部跑一個獨立的 event loop 執行
    IPC，避免依賴 caller 線程既有的 asyncio loop（governance_hub 在 pytest
    fixture + sync MessageBus dispatch 中由 sync 線程呼叫）。

    Args / 參數:
        coro: awaitable to drive / 要驅動的 awaitable
        timeout: hard timeout seconds; if elapsed, returns None / 強制超時秒數
            （超過則回 None）

    Returns / 回傳:
        The awaited result, or None on timeout / await 結果或超時時回 None
    """
    # asyncio.run rejects when called from inside a running loop. We probe
    # for that case and fall back to a thread-local executor.
    # asyncio.run 在已 running loop 內呼叫會拒絕；探測後退回 thread-local
    # executor。
    try:
        loop = asyncio.get_running_loop()
        running = loop is not None
    except RuntimeError:
        running = False

    if not running:
        try:
            return asyncio.run(asyncio.wait_for(coro, timeout=timeout))
        except asyncio.TimeoutError:
            logger.warning(
                "lease IPC dispatch timed out after %.1fs / lease IPC 超時 %.1f 秒",
                timeout, timeout,
            )
            return None
        except Exception as exc:  # noqa: BLE001 — fail-closed for any IPC error
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "lease IPC dispatch failed: %s / lease IPC 派發失敗：%s",
                    exc, exc,
                )
            return None

    # Caller thread already has a running loop; spawn a sidecar thread with
    # its own loop. Rare case (governance_hub is normally called from sync
    # MessageBus / pytest threads). Sidecar isolates the new loop from the
    # caller's loop and joins on completion.
    # caller 線程已有 running loop；spawn 獨立 thread 跑新 loop。罕見情境
    # （governance_hub 通常由 sync MessageBus / pytest 呼叫）。sidecar 隔離
    # 新 loop 並 join 至完成。
    result_holder: dict[str, Any] = {"value": None, "exc": None}

    def _runner() -> None:
        try:
            result_holder["value"] = asyncio.run(asyncio.wait_for(coro, timeout=timeout))
        except asyncio.TimeoutError:
            logger.warning(
                "lease IPC dispatch (sidecar) timed out after %.1fs / "
                "lease IPC（sidecar）超時 %.1f 秒",
                timeout, timeout,
            )
        except Exception as exc:  # noqa: BLE001
            result_holder["exc"] = exc

    thread = threading.Thread(target=_runner, name="lease_ipc_sidecar", daemon=True)
    thread.start()
    thread.join(timeout=timeout + 1.0)  # +1s margin for thread cleanup
    if thread.is_alive():
        logger.warning(
            "lease IPC sidecar thread did not finish in %.1fs / "
            "lease IPC sidecar 線程未在 %.1f 秒內完成",
            timeout + 1.0, timeout + 1.0,
        )
        return None
    if result_holder["exc"] is not None and logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "lease IPC sidecar exception: %s / lease IPC sidecar 例外：%s",
            result_holder["exc"], result_holder["exc"],
        )
    return result_holder["value"]


# ═══════════════════════════════════════════════════════════════════════════════
# Public bridge functions / 公開橋接函數
# ═══════════════════════════════════════════════════════════════════════════════

def acquire_lease_via_ipc(
    *,
    intent_id: str,
    scope: str,
    ttl_seconds: float,
    profile: str = PROFILE_PRODUCTION,
    source_stage: str = DEFAULT_SOURCE_STAGE_PY_EXECUTOR,
    timeout_seconds: float = 5.0,
    dispatcher: Optional[IPCDispatcher] = None,
) -> Optional[str]:
    """Acquire a lease through the Rust facade via IPC.
    透過 IPC 經 Rust facade 取得 lease。

    Caller MUST have already verified shadow_mode_provider() returns False;
    this function does NOT short-circuit. Use governance_hub.acquire_lease()
    for the full short-circuit + fallback orchestration.
    caller 必先驗證 shadow_mode_provider() 為 False；本函式不執行短路。
    full 短路 + fallback 編排請呼叫 governance_hub.acquire_lease()。

    Args / 參數:
        intent_id: trade intent id / 交易 intent id
        scope: e.g. "TRADE_ENTRY" / 例如 TRADE_ENTRY
        ttl_seconds: lease TTL / lease TTL 秒數
        profile: governance profile string / 治理 profile
        source_stage: telemetry tag / 遙測標籤
        timeout_seconds: per-call IPC timeout / IPC 單次超時
        dispatcher: injectable dispatcher (test only) / 可注入派發器（僅測試）

    Returns / 回傳:
        lease_id string on success; None on IPC failure / fail-closed.
        成功回 lease_id；IPC 失敗 / fail-closed 回 None。
    """
    try:
        params = build_acquire_request_params(
            intent_id=intent_id,
            scope=scope,
            ttl_seconds=ttl_seconds,
            profile=profile,
            source_stage=source_stage,
        )
    except (TypeError, ValueError) as exc:
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "build_acquire_request_params rejected args: %s / "
                "build_acquire_request_params 拒絕參數：%s",
                exc, exc,
            )
        return None

    dispatch = dispatcher or _default_dispatcher()
    coro = dispatch(METHOD_ACQUIRE_LEASE, params, timeout_seconds)
    raw_result = _run_async_blocking(coro, timeout=timeout_seconds + 1.0)

    if raw_result is None:
        # IPC outage / timeout / non-dict payload — fail-closed.
        # IPC 中斷 / 超時 / 非 dict payload — fail-closed。
        return None
    if not isinstance(raw_result, Mapping):
        return None

    lease_id, outcome = parse_acquire_response(raw_result)
    if lease_id is None:
        return None
    if outcome not in (OUTCOME_ACTIVE, OUTCOME_BYPASS):
        # Unknown outcome — defensive fail-closed.
        # 未知 outcome — 防禦性 fail-closed。
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "lease acquire returned unknown outcome %r / "
                "lease acquire 回未知 outcome %r",
                outcome, outcome,
            )
        return None

    # Bypass outcome → no SM transition; we still return the lease_id (caller
    # can detect Bypass via outcome but the simple Optional[str] contract
    # remains backward-compat). Mirror records this acquire if it isn't a
    # SHADOW_BYPASS sentinel string.
    # Bypass outcome → 無 SM transition；仍回 lease_id（caller 可從 outcome 偵測
    # Bypass，但 Optional[str] 簡單契約仍 backward-compat）。lease_id 不是
    # SHADOW_BYPASS sentinel 字串時，記入 mirror。
    record_dual_write_acquire(
        lease_id=lease_id,
        intent_id=intent_id,
        scope=scope,
        ttl_seconds=ttl_seconds,
    )
    return lease_id


def release_lease_via_ipc(
    *,
    lease_id: str,
    consumed: bool,
    timeout_seconds: float = 5.0,
    dispatcher: Optional[IPCDispatcher] = None,
) -> bool:
    """Release a lease via Rust facade IPC.
    透過 Rust facade IPC 釋放 lease。

    consumed=True → outcome=Consumed; consumed=False → outcome=Failed.
    SHADOW_BYPASS sentinel: short-circuits to True without IPC.
    consumed=True → outcome=Consumed；consumed=False → outcome=Failed。
    SHADOW_BYPASS sentinel：短路回 True 不進 IPC。

    Returns / 回傳:
        True if Rust returned ``ok=true``; False on IPC failure / unknown.
        Rust 回 ok=true 時 True；IPC 失敗 / 未知時 False。
    """
    if is_shadow_bypass_lease_id(lease_id):
        # Symmetric short-circuit: release of a SHADOW_BYPASS sentinel is a
        # no-op success; SM was never engaged on acquire so nothing to release.
        # 對稱短路：SHADOW_BYPASS sentinel 的 release 是 no-op success；
        # acquire 時 SM 未啟動，這裡無事可做。
        return True

    outcome = OUTCOME_CONSUMED if consumed else OUTCOME_FAILED
    try:
        params = build_release_request_params(lease_id=lease_id, outcome=outcome)
    except (TypeError, ValueError) as exc:
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "build_release_request_params rejected args: %s / "
                "build_release_request_params 拒絕參數：%s",
                exc, exc,
            )
        return False

    dispatch = dispatcher or _default_dispatcher()
    coro = dispatch(METHOD_RELEASE_LEASE, params, timeout_seconds)
    raw_result = _run_async_blocking(coro, timeout=timeout_seconds + 1.0)
    ok = isinstance(raw_result, Mapping) and parse_release_response(raw_result)

    if ok:
        record_dual_write_release(lease_id=lease_id, outcome=outcome)
    return ok


def get_lease_via_ipc(
    *,
    lease_id: str,
    timeout_seconds: float = 5.0,
    dispatcher: Optional[IPCDispatcher] = None,
) -> Optional[Mapping[str, Any]]:
    """Fetch a lease object dict from Rust facade via IPC.
    透過 IPC 從 Rust facade 取 lease 物件 dict。

    Returns the raw Rust serde dict (caller adapts as needed) or None when
    not found / IPC fail. SHADOW_BYPASS sentinel short-circuits to None
    (the SM never held this lease).
    回傳 Rust serde dict（caller 視需要轉換）或 not found / IPC 失敗時 None。
    SHADOW_BYPASS sentinel 短路回 None（SM 從未持有此 lease）。
    """
    if is_shadow_bypass_lease_id(lease_id):
        return None

    try:
        params = build_get_request_params(lease_id=lease_id)
    except (TypeError, ValueError):
        return None

    dispatch = dispatcher or _default_dispatcher()
    coro = dispatch(METHOD_GET_LEASE, params, timeout_seconds)
    raw_result = _run_async_blocking(coro, timeout=timeout_seconds + 1.0)
    if not isinstance(raw_result, Mapping):
        return None
    return parse_get_response(raw_result)


# ═══════════════════════════════════════════════════════════════════════════════
# Caller-side shadow short-circuit / caller 端 shadow 短路
# ═══════════════════════════════════════════════════════════════════════════════

def shadow_short_circuit_acquire(
    *,
    intent_id: str,
    shadow_mode_provider: Optional[Callable[[], bool]],
) -> Optional[str]:
    """Return a SHADOW_BYPASS sentinel if the provider reports shadow mode.
    若 provider 回報 shadow mode，回 SHADOW_BYPASS sentinel。

    PA push back #2 HIGH: ExecutorAgent shadow_mode fail-close paths must NOT
    engage IPC (which would falsely populate Rust SM + lease_transitions audit
    row, inflating V054 noise and creating AC-1 假綠).

    PA push back #2 HIGH：ExecutorAgent shadow_mode fail-close 路徑不可進 IPC
    （否則會偽造 Rust SM transition + lease_transitions audit row，推高 V054
    噪聲並讓 AC-1 假綠）。

    Args / 參數:
        intent_id: trade intent id / 交易 intent id
        shadow_mode_provider: optional zero-arg callable returning shadow flag.
            None or any exception → returns None (no short-circuit; caller
            proceeds to full IPC path).
            可選的零參 callable，回傳 shadow 旗標。None 或任意例外 → 回 None
            （不短路；caller 走完整 IPC 路徑）。

    Returns / 回傳:
        SHADOW_BYPASS sentinel string if shadow path detected; None otherwise.
        偵測到 shadow 路徑時回 SHADOW_BYPASS sentinel；否則 None。
    """
    if shadow_mode_provider is None:
        return None
    try:
        is_shadow = bool(shadow_mode_provider())
    except Exception:  # noqa: BLE001 — provider may raise; treat as non-shadow
        # A misbehaving provider must NOT silently route the caller into shadow
        # short-circuit (would hide real lease failures). Treat as not-shadow
        # and let the caller take the full path.
        # 行為異常的 provider 不可靜默把 caller 路由進 shadow 短路（會掩蓋
        # 真實 lease 失敗）。視為 non-shadow，caller 走完整路徑。
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "shadow_mode_provider raised; treating as non-shadow / "
                "shadow_mode_provider 拋例外；視為 non-shadow",
            )
        return None
    if not is_shadow:
        return None
    return make_shadow_bypass_lease_id(intent_id)


__all__ = [
    "LEASE_IPC_ENABLED_ENV",
    "is_lease_ipc_enabled",
    "record_dual_write_acquire",
    "record_dual_write_release",
    "get_dual_write_mirror_snapshot",
    "reset_dual_write_mirror",
    "acquire_lease_via_ipc",
    "release_lease_via_ipc",
    "get_lease_via_ipc",
    "shadow_short_circuit_acquire",
]
