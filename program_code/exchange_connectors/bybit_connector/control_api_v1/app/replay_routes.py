from __future__ import annotations

"""REF-20 Paper Replay Lab — 8 routes wired to T1 binary + PG advisory lock.
REF-20 Paper Replay Lab — 8 路由接 T1 binary + PG advisory lock。

MODULE_NOTE (EN):
    Wave 4 R20-P2b-T2 + T3 merged deliverable. 8 routes (POST /run + /cancel
    + /manifest/verify mutating; GET /status + /report/{id} + /manifests +
    /health/signature + /list read-only). PG advisory locks (V045) primary;
    in-memory ``_ACTIVE_RUNS`` LEGACY FALLBACK when V045 absent / PG unreachable.
    Hard contracts: session-token auth on all routes; mutating routes need
    Operator + ``replay:write``; cap exceeded → 409; PG outage → degraded=true
    (V3 §12 #22); ``replay_runner`` Popen wraps whitelisted env (V3 §6.2);
    cross-platform clean (CLAUDE.md §七 ★★, no /Users / /home literals).

    Sprint 1 Track C E2 retrofit moved P0-2 / P0-4 / P0-5 security helpers to
    sibling ``replay/security_guards.py`` for §九 1500 LOC cap compliance.

MODULE_NOTE (中):
    Wave 4 R20-P2b-T2 + T3 合併交付。8 路由（POST /run + /cancel + /manifest/
    verify 變更；GET /status + /report/{id} + /manifests + /health/signature
    + /list 只讀）。PG advisory lock（V045）主路徑；in-memory ``_ACTIVE_RUNS``
    LEGACY FALLBACK，V045 缺/PG 不可達時走。硬約束：session-token 驗於所有
    route；變更類需 Operator + ``replay:write``；cap 超 → 409；PG outage →
    degraded=true（V3 §12 #22）；``replay_runner`` Popen 白名單 env（V3 §6.2）；
    跨平台合規（CLAUDE.md §七 ★★，無 /Users / /home literal）。

    Sprint 1 Track C E2 retrofit 把 P0-2 / P0-4 / P0-5 安全 helper 移至
    sibling ``replay/security_guards.py``，符合 §九 1500 LOC cap。

SPEC: REF-20 V3 §3 G3/G7 + §6 + §12 #3/#14/#22 binding
Workplan: docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md §4 Wave 4
Dispatch: docs/execution_plan/2026-05-03--ref20_wave2_dispatch_v1.md §6 v1.1 Option C
"""

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from . import main_legacy as base
from .auth import require_scope_and_operator
from .db_pool import get_pg_conn

# Replay helpers + security guards — relative-package first (production),
# absolute fallback (test layout via conftest.py PROJECT_ROOT injection).
# Replay helper + 安全守門：先 relative-package（生產），fail 時 absolute（測試佈局）。
try:
    from ..replay import route_helpers as _rh  # type: ignore[no-redef]
    from ..replay import security_guards as _sg  # type: ignore[no-redef]
    from ..replay import manifest_signer as _ms  # type: ignore[no-redef]
    from ..replay import experiment_registry as _er  # type: ignore[no-redef]
    from ..replay import report_route as _rr  # type: ignore[no-redef]
except ImportError:
    from replay import route_helpers as _rh  # type: ignore[no-redef]
    from replay import security_guards as _sg  # type: ignore[no-redef]
    try:
        from replay import manifest_signer as _ms  # type: ignore[no-redef]
    except ImportError:
        _ms = None  # type: ignore[assignment]
    from replay import experiment_registry as _er  # type: ignore[no-redef]
    from replay import report_route as _rr  # type: ignore[no-redef]
ADVISORY_LOCK_GLOBAL_KEY = _rh.ADVISORY_LOCK_GLOBAL_KEY
ADVISORY_LOCK_PER_ACTOR_PREFIX = _rh.ADVISORY_LOCK_PER_ACTOR_PREFIX
_count_active_runs_for_actor = _rh.count_active_runs_for_actor
_count_active_runs_global = _rh.count_active_runs_global
_resolve_artifact_output_dir = _rh.resolve_artifact_output_dir
_spawn_replay_runner = _rh.spawn_replay_runner
_try_acquire_pg_advisory_locks = _rh.try_acquire_pg_advisory_locks
_v045_table_present = _rh.v045_table_present
_write_manifest_fixture = _rh.write_manifest_fixture
_verify_replay_runner_pid = _rh.verify_replay_runner_pid
_is_live_release_profile = _rh.is_live_release_profile
_artifact_path_within_allowlist = _rh.artifact_path_within_allowlist
_build_default_manifest_payload = _rh.build_default_manifest_payload
_compute_replay_health_state = _rh.compute_replay_health_state

logger = logging.getLogger(__name__)


# Track C P0-2 boot guard: live profile + TEST_KEY env both set ⇒ FAIL-CLOSED.
# E2 retrofit F6: log-only is a fake-fix; raise so uvicorn boot fails before
# any /replay/manifest/verify request can enter the test_key path.
# Track C P0-2 boot guard：live profile + TEST_KEY env 雙設 ⇒ FAIL-CLOSED。
# E2 retrofit F6：log-only 是 fake-fix；raise 讓 uvicorn 啟動失敗，
# /replay/manifest/verify 請求未到 test_key 路徑即斷。
_sg.perform_p0_2_boot_guard(_is_live_release_profile)


# ═══════════════════════════════════════════════════════════════════════════════
# Router / 路由器
# ═══════════════════════════════════════════════════════════════════════════════

replay_router = APIRouter(
    prefix="/api/v1/replay",
    tags=["Replay Lab / 重放實驗室"],
)


# ═══════════════════════════════════════════════════════════════════════════════
# Constants & In-Memory State / 常數與記憶體狀態
# ═══════════════════════════════════════════════════════════════════════════════

# V3 §5 manifest TTL (30d) / per-actor active manifest cap (20).
# V3 §5 manifest TTL (30d) / 每個 actor 活躍 manifest 上限（20）。
MANIFEST_TTL_DAYS = 30
PER_ACTOR_MANIFEST_CAP = 20

# V3 §5: P2/P3 global active run cap = 1; per-actor cap = 1.
# V3 §5：P2/P3 全局活躍 run 上限 = 1；每個 actor 上限 = 1。
GLOBAL_ACTIVE_RUN_CAP = 1
PER_ACTOR_ACTIVE_RUN_CAP = 1

# Mirror of `agents_routes_helpers._STATEMENT_TIMEOUT_MS`. Read-only fail-closed
# guard for any PG SELECT inside this module. V3 §12 #22.
# 鏡像 ``agents_routes_helpers._STATEMENT_TIMEOUT_MS``。本模組任何 PG SELECT
# 的只讀 fail-closed 守門。V3 §12 #22。
_STATEMENT_TIMEOUT_MS = 2_000

# Advisory lock keys are imported from replay.route_helpers (single source of
# truth across replay_routes + tests + ad-hoc PG sql probes).
# advisory lock key 從 replay.route_helpers 匯入（routes + tests + ad-hoc
# PG sql probe 共用單一 source of truth）。
# (re-exported as module-level names ADVISORY_LOCK_GLOBAL_KEY +
#  ADVISORY_LOCK_PER_ACTOR_PREFIX above for back-compat with __all__).

# In-memory active run state — LEGACY FALLBACK for hermetic single-worker
# test coverage + pre-V045 graceful degradation. PG advisory lock + V045 is
# canonical; this dict is touched ONLY when V045 absent or PG unreachable.
# Both paths share cap semantics (global=1, per-actor=1).
# 記憶體中 active run 狀態 — LEGACY FALLBACK（single-worker test + pre-V045
# graceful 降級）。PG advisory lock + V045 為 canonical；只在 V045 缺或 PG
# 不可達時觸碰本 dict。兩路徑同 cap 語意（global=1, per-actor=1）。
_ACTIVE_RUNS: dict[str, dict[str, Any]] = {}

# Async lock guarding atomic check-and-set on ``_ACTIVE_RUNS`` to prevent
# TOCTOU between cap check and run insertion under uvicorn concurrent
# requests. Single asyncio.Lock suffices because GLOBAL_ACTIVE_RUN_CAP=1
# (only one writer ever holds the lock for state mutation).
# 對 ``_ACTIVE_RUNS`` 原子 check-and-set 的 async lock，防 uvicorn 並發
# 請求下 TOCTOU。單 asyncio.Lock 足夠（GLOBAL_ACTIVE_RUN_CAP=1）。
_ACTIVE_RUNS_LOCK: asyncio.Lock = asyncio.Lock()


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic Models / 請求響應模型
#
# Sprint A R1-T3 (2026-05-04) extraction: the 3 request models below were moved
# to ``replay/replay_models.py`` so this file stays under the §九 1500 LOC cap
# after the ``/api/v1/replay/health`` route lands. Behaviour is byte-identical
# to the prior inline form; module-level aliases preserve back-compat for
# ``__all__`` consumers and existing tests.
#
# Sprint A R1-T3（2026-05-04）抽出：下方 3 個請求模型已移到
# ``replay/replay_models.py``，目的是讓本檔在 ``/api/v1/replay/health`` 路由
# 上線後仍守住 §九 1500 LOC 硬上限。行為與內嵌完全等同；模組級別名保留
# ``__all__`` 消費者與既有測試的向後相容性。
# ═══════════════════════════════════════════════════════════════════════════════

try:
    from ..replay.replay_models import (  # type: ignore[no-redef]
        ReplayCancelRequest,
        ReplayManifestVerifyRequest,
        ReplayRunRequest,
    )
except ImportError:
    from replay.replay_models import (  # type: ignore[no-redef]
        ReplayCancelRequest,
        ReplayManifestVerifyRequest,
        ReplayRunRequest,
    )

# REF-20 Sprint A R2-T1: re-export request model owned by experiment_registry.
# REF-20 Sprint A R2-T1：re-export ``experiment_registry`` 擁有的請求模型。
ReplayExperimentRegisterRequest = _er.ReplayExperimentRegisterRequest


# ═══════════════════════════════════════════════════════════════════════════════
# Auth + Concurrency Helpers / 認證與並發守門
# ═══════════════════════════════════════════════════════════════════════════════


def _require_replay_write(actor: base.AuthenticatedActor) -> None:
    """Mutating-route gate: Operator role + ``replay:write`` scope.
    變更類 route 守門：Operator 角色 + ``replay:write`` scope。

    Mirrors ``risk_routes._require_risk_write``. Fail-closed via
    ``HTTPException`` (401/403) re-raised by FastAPI.
    """
    require_scope_and_operator(actor, "replay:write")


def _actor_can_read_any_replay_report(actor: base.AuthenticatedActor) -> bool:
    """Track C P0-5a IDOR admin bypass: True iff actor holds ``replay:read:any``.
    Track C P0-5a IDOR admin 旁通：actor 持 ``replay:read:any`` 即 True。

    Plain operator role alone is NOT enough — explicit-grant scope only.
    Defense-in-depth on missing actor (already 401'd by FastAPI Depends).
    """
    if actor is None:
        return False
    return "replay:read:any" in (getattr(actor, "scopes", None) or set())


# REF-20 Sprint A R2 round 2 fix M-2: per-actor rate limit key function.
# REF-20 Sprint A R2 round 2 fix M-2：per-actor rate limit key 函式。
def _replay_rate_limit_key(request: Request) -> str:
    """Rate-limit key for /replay write endpoints (R2 round 2 fix M-2).
    /replay 寫入端點的 rate-limit key（R2 round 2 fix M-2）。

    Tries ``request.state.actor.actor_id`` first; falls back to
    ``request.client.host`` if FastAPI ``Depends(current_actor)`` has not
    yet populated state (slowapi runs the wrapper BEFORE the Depends
    resolution, so under current wiring this almost always falls back to
    IP). The fallback IP-based limit is still meaningfully stricter than
    the global 120/min default.
    先試 ``request.state.actor.actor_id``；FastAPI ``Depends(current_actor)``
    尚未填 state 時 fallback 到 ``request.client.host``（slowapi wrapper
    跑在 Depends 之前所以基本都 fallback；fallback 仍比 global 120/min
    嚴格）。
    """
    state_actor = getattr(getattr(request, "state", None), "actor", None)
    if state_actor is not None:
        actor_id = getattr(state_actor, "actor_id", None)
        if actor_id:
            return f"actor:{actor_id}"
    client = getattr(request, "client", None)
    return f"ip:{client.host}" if client is not None else "ip:unknown"


# Resolve the limiter once at module init (avoids attribute lookup per request).
# 模組初始化時解析 limiter（避免每請求 attribute lookup）。
_replay_limiter = base.limiter


# Note / 註：binary path / output dir / advisory lock / V045 helpers
# are imported from replay.route_helpers (Wave 4 R20-P2b-T2 split per
# CLAUDE.md §九 1500 LOC cap). They are aliased above to keep the
# private-name convention used in this module.


async def _check_run_caps_inmemory(actor_id: str) -> None:
    """Enforce V3 §5 concurrency caps via in-memory dict (fallback path).
    透過 in-memory dict 強制 V3 §5 並發上限（fallback 路徑）。

    Used when V045 absent OR PG unreachable (graceful degradation).
    Caller must already hold ``_ACTIVE_RUNS_LOCK``.
    V045 缺或 PG 不可達時使用；caller 必先持 ``_ACTIVE_RUNS_LOCK``。
    """
    global_count = len(_ACTIVE_RUNS)
    if global_count >= GLOBAL_ACTIVE_RUN_CAP:
        existing_actors = list(_ACTIVE_RUNS.keys())
        if actor_id in _ACTIVE_RUNS:
            raise HTTPException(
                status_code=409,
                detail={
                    "reason_codes": ["replay_per_actor_cap_exceeded"],
                    "message": (
                        f"actor '{actor_id}' already has an active replay "
                        f"run (per-actor cap = {PER_ACTOR_ACTIVE_RUN_CAP})"
                    ),
                    "active_actors": existing_actors,
                },
            )
        raise HTTPException(
            status_code=409,
            detail={
                "reason_codes": ["replay_global_cap_exceeded"],
                "message": (
                    f"global active replay run cap reached "
                    f"(cap = {GLOBAL_ACTIVE_RUN_CAP})"
                ),
                "active_actors": existing_actors,
            },
        )
    if actor_id in _ACTIVE_RUNS:
        raise HTTPException(
            status_code=409,
            detail={
                "reason_codes": ["replay_per_actor_cap_exceeded"],
                "message": (
                    f"actor '{actor_id}' already has an active replay run"
                ),
            },
        )


# ─── Thin wrappers delegating to route_helpers / 委派 route_helpers 的薄封裝 ─
# Canonical impls in replay/route_helpers.py; wrappers preserve module-private
# names used by tests + endpoints. / 規範實作在 replay/route_helpers.py。
_emit_audit_stub = _rh.emit_replay_audit_stub
_replay_response = _rh.replay_response_envelope


def _safe_pg_select(
    sql: str, params: tuple[Any, ...] | list[Any],
) -> Tuple[list[tuple[Any, ...]], Optional[str]]:
    """SELECT + statement_timeout + PG-degraded fail-closed envelope.
    SELECT + statement_timeout + PG 中斷 fail-closed 信封。
    """
    return _rh.safe_pg_select(get_pg_conn, sql, params, _STATEMENT_TIMEOUT_MS)


async def _async_safe_pg_select(
    sql: str, params: tuple[Any, ...] | list[Any],
) -> Tuple[list[tuple[Any, ...]], Optional[str]]:
    """Async wrapper around ``_safe_pg_select`` (H-4 pattern).
    ``_safe_pg_select`` async 包裝（H-4 pattern）。"""
    return await asyncio.to_thread(_safe_pg_select, sql, params)


# ═══════════════════════════════════════════════════════════════════════════════
# Routes / 路由
#
# Note / 註：subprocess Popen wrapper (_spawn_replay_runner) is imported from
# replay.route_helpers (Wave 4 R20-P2b-T2 split per CLAUDE.md §九 1500 LOC cap).
# ═══════════════════════════════════════════════════════════════════════════════


@replay_router.post("/experiments/register")
@_replay_limiter.limit("10/minute", key_func=_replay_rate_limit_key)
async def post_experiment_register(
    request: Request,
    body: ReplayExperimentRegisterRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """Register a manifest in V049 ``replay.experiments`` (R2-T1 thin handler).
    在 V049 註冊 manifest（R2-T1 薄 handler）。Auth: Operator + ``replay:write``.
    Rate limit: 10/min per-actor (R2 round 2 fix M-2; slowapi 0.1.9 falls
    back to per-IP under current wiring — see ``_replay_rate_limit_key``).
    Logic: ``replay/experiment_registry.py`` (CLAUDE.md §九 1500 LOC cap).
    """
    _require_replay_write(actor)
    actor_id = str(actor.actor_id)
    result, err = await asyncio.to_thread(
        _er.run_register_in_pg_xact, get_pg_conn, actor, body,
        statement_timeout_ms=_STATEMENT_TIMEOUT_MS, manifest_signer_module=_ms,
    )
    http_err = _er.map_register_error_to_http(err)
    if http_err is not None:
        status, detail = http_err
        raise HTTPException(status_code=status, detail=detail)
    _emit_audit_stub(
        event_type="replay_experiment_registered", actor_id=actor_id,
        experiment_id=result["experiment_id"] if result else None,
        manifest_hash=result.get("manifest_hash") if result else None,
        decision="registered",
        extra_payload={
            "idempotency_hit": result.get("idempotency_hit", False) if result else False,
            "data_tier": body.data_tier, "timeframe": body.timeframe,
            "symbol": body.symbol, "strategy": body.strategy,
        },
    )
    return _replay_response(result)


@replay_router.post("/run")
@_replay_limiter.limit("10/minute", key_func=_replay_rate_limit_key)
async def post_replay_run(
    request: Request,
    body: ReplayRunRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """Start a replay run for a pre-registered manifest.
    啟動 pre-registered manifest 的 replay run。

    Auth: Operator + ``replay:write``. Concurrency cap V3 §5: global=1, per-actor=1.
    Rate limit: 10/min per-actor (R2 round 2 fix M-2).

    Wiring (R2-T2 amended): PG advisory lock → SELECT V049.experiments
    FOR SHARE → INSERT V045.run_state status='starting' → spawn
    ``replay_runner`` → UPDATE pid + status='running'. V045 absent or PG
    unreachable → in-memory ``_ACTIVE_RUNS`` fallback (legacy hermetic test).
    R2-T2 修訂後流程：取 PG advisory lock → SELECT V049 FOR SHARE → INSERT
    V045 → spawn → UPDATE。V045 缺 / PG 斷 → in-memory fallback。
    """
    _require_replay_write(actor)
    actor_id = str(actor.actor_id)
    started_at_ms = int(time.time() * 1000)

    # ── Try PG advisory-lock path (primary) ──
    # 嘗試 PG advisory-lock 路徑（主路徑）。
    pg_path_attempted = False
    pg_path_succeeded = False
    pg_err: Optional[str] = None

    def _do_pg_path() -> Tuple[Optional[str], Optional[int], Optional[str], Optional[Path]]:
        """Sync helper to keep the entire xact under one cursor.
        同步 helper，把整個 xact 包在一個 cursor 內。

        Returns / 回傳:
            (run_id, pid, err_reason, output_dir)
            run_id is None if path did not run; pid is None if spawn
            failed but DB row was created.
        """
        with get_pg_conn() as conn:
            if conn is None:
                return None, None, "pg_unavailable", None
            try:
                cur = conn.cursor()
                cur.execute("SET LOCAL statement_timeout = %s", (_STATEMENT_TIMEOUT_MS,))

                # Schema-absent graceful: if V045 missing, fall back to in-memory.
                # Schema-absent graceful：V045 缺則 fallback in-memory。
                if not _v045_table_present(cur):
                    return None, None, "v045_absent", None

                # 1) Try advisory locks within this xact.
                # 1) 在此 xact 內嘗試 advisory lock。
                lock_ok, lock_err = _try_acquire_pg_advisory_locks(cur, actor_id)
                if not lock_ok:
                    return None, None, lock_err, None

                # 2) Belt-and-suspenders: query active runs in V045 to verify
                # cap (locks should already prevent races, but this is a
                # defense-in-depth check that's cheap given we hold the lock).
                # 2) 雙保險：在 V045 查 active run 確認 cap（lock 應已防 race，
                # 但持鎖時的 defense-in-depth 廉價檢查）。
                per_actor_count = _count_active_runs_for_actor(cur, actor_id)
                if per_actor_count >= PER_ACTOR_ACTIVE_RUN_CAP:
                    return None, None, "replay_per_actor_cap_exceeded", None
                global_count = _count_active_runs_global(cur)
                if global_count >= GLOBAL_ACTIVE_RUN_CAP:
                    return None, None, "replay_global_cap_exceeded", None

                # 3) INSERT row with status='starting'; pid filled later.
                # 3) INSERT 列 status='starting'；pid 稍後填。
                run_id_local = uuid.uuid4().hex
                # REF-20 Sprint A R2-T2: real SELECT (FOR SHARE) replaces UUID5.
                manifest_uuid = _rh.lookup_registered_experiment_id(cur, body.experiment_id)
                if manifest_uuid is None:
                    return None, None, "replay_experiment_not_registered", None

                cur.execute(
                    """
                    INSERT INTO replay.run_state (
                        run_id, actor_id, manifest_id, status,
                        started_at, runtime_environment, idempotency_key
                    ) VALUES (
                        %s::uuid, %s, %s::uuid, 'starting',
                        NOW(),
                        COALESCE(NULLIF(%s, ''), 'linux_trade_core'),
                        %s
                    );
                    """,
                    (
                        run_id_local, actor_id, str(manifest_uuid),
                        os.environ.get("OPENCLAW_REPLAY_RUNTIME_ENV", ""),
                        body.idempotency_key,
                    ),
                )

                # 4) Resolve output_dir + write manifest fixture (with
                # embedded ``run_id`` so Rust runner self-verifies basename
                # match — REF-20 Sprint 1 Track A PA push back #2 invariant).
                # Manifest fixture has minimum 6 fields the Rust
                # ``ReplayManifest`` struct reads (Wave 4 T1 contract):
                # experiment_id / data_tier / fixture_uri / signature /
                # manifest_hash / signature_key_ref. Track A uses *placeholder*
                # values for signature/hash (Wave 4 sibling key.hex archive
                # path will warn-skip verification per current
                # ``load_and_verify_manifest`` fall-through; Wave 6 V042 SQL
                # archive integration replaces with full HMAC verify).
                #
                # 4) 解析 output_dir + 寫 manifest fixture（embed ``run_id``
                # 使 Rust runner 自驗 basename 一致 — REF-20 Sprint 1 Track A
                # PA push back #2 不變量）。manifest fixture 含 6 個 Rust
                # ``ReplayManifest`` struct 讀的最小欄位（Wave 4 T1 契約）：
                # experiment_id / data_tier / fixture_uri / signature /
                # manifest_hash / signature_key_ref。Track A 用 *placeholder*
                # 值給 signature/hash（Wave 4 sibling key.hex archive 路徑
                # warn-skip verification per 當前 ``load_and_verify_manifest``
                # fall-through；Wave 6 V042 SQL archive integration 換實 HMAC verify）。
                output_dir = _resolve_artifact_output_dir(run_id_local)
                try:
                    manifest_fixture_path = _write_manifest_fixture(
                        run_id=run_id_local,
                        manifest_data=_build_default_manifest_payload(
                            experiment_id=body.experiment_id,
                            output_dir=output_dir,
                        ),
                        output_dir=output_dir,
                    )
                except (OSError, ValueError) as exc:
                    cur.execute(
                        """
                        UPDATE replay.run_state
                           SET status = 'failed',
                               exit_code = -1,
                               completed_at = NOW(),
                               cancel_reason = %s
                         WHERE run_id = %s::uuid;
                        """,
                        (
                            f"manifest_fixture_write_failed:{type(exc).__name__}",
                            run_id_local,
                        ),
                    )
                    conn.commit()
                    return (
                        run_id_local,
                        None,
                        f"manifest_fixture_write_failed:{type(exc).__name__}",
                        output_dir,
                    )

                # 5) Spawn subprocess (still holding xact lock) + poll-then-INSERT.
                # spawn_replay_runner waits ``poll_grace_seconds`` (default 1.5s)
                # and polls ``proc.poll()`` to detect early death (CLI schema
                # mismatch / manifest fail-closed cause non-zero exit; previous
                # Python flow trusted Popen alone and never noticed — root
                # cause #1+#2 of REF-20 Sprint 1 Track A).
                #
                # 5) Spawn 子程序（仍持 xact lock）+ poll-then-INSERT。
                # spawn_replay_runner 等 ``poll_grace_seconds``（預設 1.5s）
                # 後 ``proc.poll()`` 偵測早死亡（CLI schema mismatch /
                # manifest fail-closed 致非 0 結束；前版 Python 只信 Popen，
                # 完全沒發現 — REF-20 Sprint 1 Track A 第一+二根因）。
                pid, spawn_err = _spawn_replay_runner(
                    run_id=run_id_local,
                    manifest_id=str(manifest_uuid),
                    output_dir=output_dir,
                    manifest_fixture_path=manifest_fixture_path,
                )

                if pid is None:
                    # Mark row as failed; commit so audit row persists.
                    # 標 row failed；commit 讓 audit row 持久化。
                    cur.execute(
                        """
                        UPDATE replay.run_state
                           SET status = 'failed',
                               exit_code = -1,
                               completed_at = NOW(),
                               cancel_reason = %s
                         WHERE run_id = %s::uuid;
                        """,
                        (f"spawn_failed:{spawn_err}", run_id_local),
                    )
                    conn.commit()
                    return run_id_local, None, spawn_err, output_dir

                # 6) UPDATE pid + status='running' (only after poll-alive
                # confirmed by spawn_replay_runner; pid is None already
                # caught the dead-runner case above).
                # 6) UPDATE pid + status='running'（僅 spawn_replay_runner
                # poll-alive 確認後；pid is None 已於上面捕獲 dead-runner case）。
                cur.execute(
                    """
                    UPDATE replay.run_state
                       SET subprocess_pid = %s,
                           status = 'running'
                     WHERE run_id = %s::uuid;
                    """,
                    (pid, run_id_local),
                )
                conn.commit()
                return run_id_local, pid, None, output_dir
            except Exception as exc:
                logger.warning("replay_routes /run PG path exception: %s", exc)
                try:
                    conn.rollback()
                except Exception:
                    pass
                return None, None, f"pg_error:{type(exc).__name__}", None

    # Try PG path off the event loop.
    # 在 event loop 外試 PG path。
    pg_path_attempted = True
    run_id, subprocess_pid, pg_err, output_dir = await asyncio.to_thread(_do_pg_path)

    if run_id is not None and pg_err is None:
        # PG path succeeded.
        # PG 路徑成功。
        pg_path_succeeded = True
        _emit_audit_stub(
            event_type="replay_run_started",
            actor_id=actor_id,
            experiment_id=body.experiment_id,
            manifest_hash=None,
            decision="accepted",
            extra_payload={
                "run_id": run_id,
                "subprocess_pid": subprocess_pid,
                "idempotency_key": body.idempotency_key,
                "path": "pg_advisory_lock",
            },
        )
        return _replay_response({
            "run_id": run_id,
            "experiment_id": body.experiment_id,
            "started_at_ms": started_at_ms,
            "status": "running",
            "subprocess_pid": subprocess_pid,
            "wiring_status": "pg_advisory_lock_path_active",
            "output_dir": str(output_dir) if output_dir else None,
        })

    if pg_err in ("replay_global_cap_exceeded", "replay_per_actor_cap_exceeded"):
        # Cap exceeded → 409 (do NOT fallback to in-memory; PG state is canonical).
        # cap 超出 → 409（不 fallback；PG 狀態 canonical）。
        raise HTTPException(
            status_code=409,
            detail={
                "reason_codes": [pg_err],
                "message": (
                    f"V3 §5 concurrency cap exceeded ({pg_err}); "
                    "wait for current run to complete or cancel"
                ),
            },
        )

    if pg_err == "replay_experiment_not_registered":
        # REF-20 Sprint A R2-T2: not in V049 → 400 (no fallback). 未註冊 → 400。
        raise HTTPException(status_code=400, detail={
            "reason_codes": ["replay_experiment_not_registered"],
            "message": (
                f"experiment_id '{body.experiment_id}' has no row in "
                "replay.experiments; call POST /api/v1/replay/experiments/register first."
            ),
        })

    if pg_err == "binary_not_found":
        # Binary missing → 503 (operator must deploy or set env).
        # binary 缺 → 503（operator 必部署或設 env）。
        raise HTTPException(
            status_code=503,
            detail={
                "reason_codes": ["replay_runner_binary_missing"],
                "message": (
                    "replay_runner binary not found; set "
                    "OPENCLAW_REPLAY_RUNNER_BIN env or build "
                    "rust/openclaw_engine --features replay_isolated"
                ),
            },
        )

    if pg_err and pg_err.startswith((
        "spawn_error:",
        "spawn_died_early:",
        "mkdir_error:",
        "pg_error:",
        "manifest_fixture_write_failed:",
    )):
        # Hard failure on PG path; surface 503 so operator can inspect logs.
        # ``spawn_died_early`` means binary spawned but exited non-zero within
        # the 1.5s poll grace (REF-20 Sprint 1 Track A — typically CLI schema
        # mismatch / manifest fail-closed).
        #
        # PG 路徑硬失敗；503 讓 operator 查 log。``spawn_died_early`` =
        # binary 已 spawn 但 1.5s poll grace 內非 0 結束（REF-20 Sprint 1
        # Track A — CLI schema mismatch / manifest fail-closed 典型表現）。
        raise HTTPException(
            status_code=503,
            detail={
                "reason_codes": ["replay_runner_spawn_failed"],
                "message": f"replay_runner failed to spawn: {pg_err}",
            },
        )

    if pg_err == "manifest_fixture_not_found":
        # Caller-supplied manifest fixture path missing on disk before spawn.
        # This is fail-closed defense-in-depth on top of route_helpers writing
        # the fixture (race / FS-level deletion theoretical edge).
        # caller 端 manifest fixture 路徑 spawn 前不在 disk。對 route_helpers
        # 寫 fixture 路徑的 fail-closed 縱深防禦（race / FS 層刪除理論邊界）。
        raise HTTPException(
            status_code=503,
            detail={
                "reason_codes": ["replay_manifest_fixture_missing"],
                "message": (
                    "manifest fixture not found at expected path; "
                    "filesystem race or pre-spawn deletion suspected"
                ),
            },
        )

    # ── Fallback path: in-memory dict ──
    # fallback 路徑：in-memory dict。
    # Reached when pg_err in ("pg_unavailable", "v045_absent", None-with-no-row).
    # pg_err 為 ("pg_unavailable", "v045_absent", None-with-no-row) 時走 fallback。
    async with _ACTIVE_RUNS_LOCK:
        await _check_run_caps_inmemory(actor_id)

        run_id_fallback = uuid.uuid4().hex
        _ACTIVE_RUNS[actor_id] = {
            "run_id": run_id_fallback,
            "experiment_id": body.experiment_id,
            "started_at_ms": started_at_ms,
            "manifest_hash": None,
            "idempotency_key": body.idempotency_key,
            "actor_id": actor_id,
        }

    _emit_audit_stub(
        event_type="replay_run_started",
        actor_id=actor_id,
        experiment_id=body.experiment_id,
        manifest_hash=None,
        decision="accepted",
        extra_payload={
            "run_id": run_id_fallback,
            "idempotency_key": body.idempotency_key,
            "path": "in_memory_fallback",
            "fallback_reason": pg_err or "no_pg_conn",
        },
    )

    return _replay_response({
        "run_id": run_id_fallback,
        "experiment_id": body.experiment_id,
        "started_at_ms": started_at_ms,
        "status": "running",
        "wiring_status": "scaffold_only_no_runner_spawned",
    })


@replay_router.get("/status")
async def get_replay_status(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """Get current replay run status for the calling actor.
    取得當前呼叫方 actor 的 replay run 狀態。

    Read-only; no scope requirement beyond authentication.

    Wave 4 R20-P2b-T2 wiring: queries V045 replay.run_state for actor's
    active run (status IN starting/running). Falls back to in-memory dict
    when V045 absent.

    Wave 4 R20-P2b-T2 接線：查 V045 replay.run_state 取 actor 的 active run；
    V045 缺則 fallback in-memory dict。
    """
    actor_id = str(actor.actor_id)

    # Try PG path first.
    # 先試 PG 路徑。
    rows, err = await _async_safe_pg_select(
        """
        SELECT run_id::text, manifest_id::text, status,
               subprocess_pid,
               EXTRACT(EPOCH FROM started_at)*1000 AS started_at_ms,
               output_path, runtime_environment,
               idempotency_key
          FROM replay.run_state
         WHERE actor_id = %s
           AND status IN ('starting','running')
         ORDER BY started_at DESC
         LIMIT 1;
        """,
        (actor_id,),
    )

    if err is None and rows:
        row = rows[0]
        snapshot = {
            "run_id": row[0],
            "experiment_id": None,  # V045 stores manifest_id; experiment_id is upstream
            "manifest_id": row[1],
            "status": row[2],
            "subprocess_pid": row[3],
            "started_at_ms": int(row[4]) if row[4] is not None else None,
            "output_path": row[5],
            "runtime_environment": row[6],
            "idempotency_key": row[7],
            "actor_id": actor_id,
        }
        return _replay_response({
            "actor_id": actor_id,
            "active_run": snapshot,
            "is_idle": False,
            "wiring_status": "pg_path_active",
        })

    if err is None and not rows:
        # PG OK but no active run; still authoritative.
        # PG 通但無 active run；仍為 canonical。
        return _replay_response({
            "actor_id": actor_id,
            "active_run": None,
            "is_idle": True,
            "wiring_status": "pg_path_active",
        })

    # Fallback to in-memory dict (PG unavailable / V045 absent).
    # fallback in-memory dict（PG 不可達 / V045 缺）。
    async with _ACTIVE_RUNS_LOCK:
        snapshot_legacy = _ACTIVE_RUNS.get(actor_id)
        snapshot_copy = dict(snapshot_legacy) if snapshot_legacy else None

    return _replay_response(
        data={
            "actor_id": actor_id,
            "active_run": snapshot_copy,
            "is_idle": snapshot_copy is None,
            "wiring_status": "in_memory_fallback",
        },
        degraded=(err is not None),
        reason=err,
    )


@replay_router.post("/cancel")
async def post_replay_cancel(
    body: ReplayCancelRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """Cancel the calling actor's active replay run.
    取消呼叫方 actor 的活躍 replay run。

    Auth: Operator + ``replay:write`` scope.

    Wave 4 R20-P2b-T2 wiring:
      1. SELECT active run from V045; if none → 409.
      2. (V045 path) Send SIGTERM to subprocess_pid via os.kill.
      3. UPDATE V045 row: status='cancelled', exit_code=-1.
      4. Fallback to in-memory dict pop on V045 absent.

    Wave 4 R20-P2b-T2 接線：
      1. 從 V045 查 active run；無則 409。
      2. （V045 路徑）對 subprocess_pid 透過 os.kill 送 SIGTERM。
      3. UPDATE V045 row：status='cancelled'、exit_code=-1。
      4. V045 缺時 fallback in-memory pop。
    """
    _require_replay_write(actor)
    actor_id = str(actor.actor_id)

    # Track C E2 retrofit: PG path body in security_guards (§九 1500 LOC cap);
    # caller sends SIGTERM after success (xact-external for hermetic test).
    # Track C E2 retrofit：PG path body 於 security_guards（§九 1500 LOC cap）；
    # caller 成功後送 SIGTERM（xact 外，hermetic test 友好）。
    cancelled_dict, pg_err = await asyncio.to_thread(
        _sg.execute_replay_cancel_pg_path,
        actor_id=actor_id, cancel_reason=body.reason,
        statement_timeout_ms=_STATEMENT_TIMEOUT_MS,
        get_pg_conn_fn=get_pg_conn, v045_table_present_fn=_v045_table_present,
        verify_pid_fn=_verify_replay_runner_pid, log_fn=logger.warning,
    )

    if cancelled_dict is not None and pg_err is None:
        _pid = cancelled_dict.get("subprocess_pid")
        if _pid is not None and _pid > 0:
            try:
                import signal
                os.kill(_pid, signal.SIGTERM)
                logger.info("cancel_run: SIGTERM pid=%d run=%s (verified)",
                            _pid, cancelled_dict["run_id"])
            except ProcessLookupError:
                logger.info("cancel_run: pid=%d already exited; DB only", _pid)
            except (PermissionError, OSError) as exc:
                logger.warning("cancel_run: os.kill(pid=%d) failed: %s; DB only", _pid, exc)

        _emit_audit_stub(
            event_type="replay_run_cancelled",
            actor_id=actor_id,
            experiment_id=body.experiment_id,
            manifest_hash=None,
            decision="cancelled",
            extra_payload={
                "reason": body.reason,
                "run_id": cancelled_dict["run_id"],
                "subprocess_pid": cancelled_dict.get("subprocess_pid"),
                "path": "pg_advisory_lock",
            },
        )
        return _replay_response({
            "actor_id": actor_id,
            "cancelled_run_id": cancelled_dict["run_id"],
            "cancelled_manifest_id": cancelled_dict["manifest_id"],
            "wiring_status": "pg_path_active",
        })

    if pg_err == "no_active_run":
        raise HTTPException(
            status_code=409,
            detail={
                "reason_codes": ["replay_no_active_run"],
                "message": f"actor '{actor_id}' has no active replay run",
            },
        )

    if pg_err and pg_err.startswith("pid_identity_mismatch:"):
        # Track C P0-4: pid identity check rejected SIGTERM. Audit + 409.
        _emit_audit_stub(
            event_type="replay_pid_identity_mismatch",
            actor_id=actor_id, experiment_id=body.experiment_id, manifest_hash=None,
            decision="blocked_by_pid_identity_check", extra_payload={"pg_err": pg_err},
        )
        raise HTTPException(
            status_code=409,
            detail={"reason_codes": ["replay_pid_identity_mismatch"],
                    "message": f"PID identity check failed ({pg_err}); SIGTERM refused"},
        )

    # Fallback in-memory.
    # in-memory fallback。
    async with _ACTIVE_RUNS_LOCK:
        snapshot = _ACTIVE_RUNS.get(actor_id)
        if not snapshot:
            raise HTTPException(
                status_code=409,
                detail={
                    "reason_codes": ["replay_no_active_run"],
                    "message": f"actor '{actor_id}' has no active replay run",
                },
            )
        if body.experiment_id and body.experiment_id != snapshot.get("experiment_id"):
            raise HTTPException(
                status_code=409,
                detail={
                    "reason_codes": ["replay_experiment_id_mismatch"],
                    "message": (
                        f"requested experiment_id does not match active run; "
                        f"active={snapshot.get('experiment_id')}"
                    ),
                },
            )
        cancelled = _ACTIVE_RUNS.pop(actor_id)

    _emit_audit_stub(
        event_type="replay_run_cancelled",
        actor_id=actor_id,
        experiment_id=cancelled.get("experiment_id"),
        manifest_hash=cancelled.get("manifest_hash"),
        decision="cancelled",
        extra_payload={
            "reason": body.reason,
            "run_id": cancelled.get("run_id"),
            "path": "in_memory_fallback",
        },
    )

    return _replay_response({
        "actor_id": actor_id,
        "cancelled_run_id": cancelled.get("run_id"),
        "cancelled_experiment_id": cancelled.get("experiment_id"),
        "wiring_status": "in_memory_fallback",
    })


@replay_router.get("/report/{experiment_id}")
async def get_replay_report(
    experiment_id: str,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """Fetch the report for a completed (or running) replay experiment.
    取得已完成（或運行中）replay experiment 的報告。

    Read-only; authentication required. Logic in
    ``replay/report_route.py`` (R2 round 2 fix H-3 cross-route consistency
    extraction; CLAUDE.md §九 1500 LOC cap on this file).

    Read-only；需認證。Logic 在 ``replay/report_route.py``（R2 round 2
    fix H-3 跨 route 一致性抽出）。
    """
    response, http_err = await _rr.fetch_report_for_experiment(
        experiment_id=experiment_id,
        actor=actor,
        get_pg_conn_fn=get_pg_conn,
        lookup_registered_experiment_id_fn=_rh.lookup_registered_experiment_id,
        actor_can_read_any_fn=_actor_can_read_any_replay_report,
        build_report_idor_sql_fn=_sg.build_report_idor_sql,
        async_safe_pg_select_fn=_async_safe_pg_select,
        artifact_path_within_allowlist_fn=_artifact_path_within_allowlist,
        check_artifact_path_within_allowlist_fn=(
            _sg.check_artifact_path_within_allowlist
        ),
        audit_emit_fn=_emit_audit_stub,
        replay_response_envelope_fn=_replay_response,
        statement_timeout_ms=_STATEMENT_TIMEOUT_MS,
    )
    if http_err is not None:
        status, detail = http_err
        raise HTTPException(status_code=status, detail=detail)
    return response


@replay_router.get("/manifests")
async def get_replay_manifests(
    limit: int = Query(default=20, ge=1, le=PER_ACTOR_MANIFEST_CAP),
    offset: int = Query(default=0, ge=0),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """List manifests created by the calling actor (paginated).
    列出呼叫方 actor 建立的 manifest（分頁）。

    Read-only.

    Wave 4 R20-P2b-T2 wiring: queries replay.experiments (P2b runner SQL
    fixture, NOT a migration). When fixture absent, falls back to V045
    run_state (a less rich projection).

    Wave 4 R20-P2b-T2 接線：查 replay.experiments（P2b runner SQL fixture，
    非 migration）。fixture 缺則 fallback V045 run_state 投影。
    """
    actor_id = str(actor.actor_id)

    # Try replay.experiments (the fixture-deployed manifest registry).
    # 試 replay.experiments（fixture 部署的 manifest registry）。
    rows, err = await _async_safe_pg_select(
        """
        SELECT experiment_id, created_at, runtime_environment, data_tier,
               status, expires_at
          FROM replay.experiments
         WHERE created_by = %s
         ORDER BY created_at DESC
         LIMIT %s OFFSET %s;
        """,
        (actor_id, limit, offset),
    )

    if err is None:
        manifests = [
            {
                "experiment_id": r[0],
                "created_at": r[1].isoformat() if hasattr(r[1], "isoformat") else str(r[1]),
                "runtime_environment": r[2],
                "data_tier": r[3],
                "status": r[4],
                "expires_at": (
                    r[5].isoformat() if r[5] and hasattr(r[5], "isoformat")
                    else (str(r[5]) if r[5] else None)
                ),
            }
            for r in rows
        ]
        return _replay_response({
            "actor_id": actor_id,
            "manifests": manifests,
            "limit": limit,
            "offset": offset,
            "wiring_status": "pg_path_active",
        })

    # Fallback to V045 projection (no manifest_jsonb metadata, but at least
    # caller sees their runs).
    # fallback V045 投影（無 manifest_jsonb metadata，但 caller 至少看見 runs）。
    rows_v045, err_v045 = await _async_safe_pg_select(
        """
        SELECT manifest_id::text, started_at, runtime_environment, status, run_id::text
          FROM replay.run_state
         WHERE actor_id = %s
         ORDER BY started_at DESC
         LIMIT %s OFFSET %s;
        """,
        (actor_id, limit, offset),
    )

    if err_v045 is None:
        manifests_v045 = [
            {
                "manifest_id": r[0],
                "started_at": r[1].isoformat() if hasattr(r[1], "isoformat") else str(r[1]),
                "runtime_environment": r[2],
                "status": r[3],
                "run_id": r[4],
                "experiment_id": None,  # not available in V045-only projection
            }
            for r in rows_v045
        ]
        return _replay_response(
            data={
                "actor_id": actor_id,
                "manifests": manifests_v045,
                "limit": limit,
                "offset": offset,
                "wiring_status": "v045_fallback_projection",
            },
            degraded=True,
            reason=f"fixture_absent:{err}",
        )

    return _replay_response(
        data={
            "actor_id": actor_id,
            "manifests": [],
            "limit": limit,
            "offset": offset,
            "wiring_status": "degraded",
        },
        degraded=True,
        reason=f"fixture_absent:{err}; v045_absent:{err_v045}",
    )


@replay_router.post("/manifest/verify")
async def post_manifest_verify(
    body: ReplayManifestVerifyRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """Verify a manifest's HMAC signature against an archived signing key.
    驗證 manifest HMAC 簽名（對照已存檔簽名 key）。

    Auth: Operator + ``replay:write`` scope (signature verification can
    leak fingerprint timing; restrict to write-capable actors).

    REF-20 Sprint A R2-T3 (2026-05-04): production path uses
    secrets-file fallback via ``manifest_signer.resolve_verify_key_source``
    (TEST_KEY env > $OPENCLAW_SECRETS_DIR/<env>/replay_signing_key >
    410 unprovisioned). Replaces prior 501 fallthrough.
    REF-20 Sprint A R2-T3：production 路徑用 secrets file fallback 取代
    501 fallthrough。
    """
    _require_replay_write(actor)
    actor_id = str(actor.actor_id)

    import base64

    try:
        canonical_bytes = base64.b64decode(body.canonical_bytes_b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "reason_codes": ["replay_invalid_b64"],
                "message": f"canonical_bytes_b64 not valid base64: {type(exc).__name__}",
            },
        )

    # Lookup ManifestSigner module loaded at module-init; 503 if absent.
    # 在 module-init 載入的 ManifestSigner module；缺則 503。
    if _ms is None:
        raise HTTPException(
            status_code=503,
            detail={
                "reason_codes": ["manifest_signer_unavailable"],
                "message": "manifest_signer module not importable",
            },
        )
    InMemoryKeyArchive = _ms.InMemoryKeyArchive
    KeyStatus = _ms.KeyStatus
    ManifestSigner = _ms.ManifestSigner

    # Track C P0-2 (E2 retrofit): per-route gate via security_guards. Boot
    # guard already failed uvicorn startup if both envs are set in live;
    # this gate is defense-in-depth for late-injected env (post-boot).
    # Track C P0-2（E2 retrofit）：透過 security_guards 的 per-route 守門。
    # boot guard 已使 uvicorn 在雙設時啟動失敗；本守門為 post-boot 注入
    # 的縱深防禦。
    test_key_hex = _sg.resolve_manifest_verify_test_key(
        actor_id=actor_id,
        declared_hash_hex=body.declared_hash_hex,
        is_live_release_profile_fn=_is_live_release_profile,
        audit_emit_fn=_emit_audit_stub,
    )
    # REF-20 Sprint A R2-T3: secrets-file fallback replaces 501 fallthrough.
    active_key_bytes, secrets_fingerprint, wiring_status, key_err = (
        _ms.resolve_verify_key_source(
            test_key_hex=test_key_hex,
            is_live_release_profile_fn=_is_live_release_profile,
        )
    )
    if active_key_bytes is None:
        _emit_audit_stub(
            event_type="replay_manifest_verify_attempted",
            actor_id=actor_id, experiment_id=None,
            manifest_hash=body.declared_hash_hex,
            decision="key_archive_not_provisioned",
            extra_payload={"fingerprint": body.fingerprint,
                           "signature_hex_prefix": body.signature_hex[:16],
                           "key_err": key_err},
        )
        raise HTTPException(status_code=410, detail={
            "reason_codes": ["replay_verify_key_archive_not_provisioned"],
            "message": (
                "manifest signature verification key archive not provisioned; "
                "place key at $OPENCLAW_SECRETS_DIR/<env>/replay_signing_key "
                "(helper_scripts/operator/generate_replay_signing_key.sh) or "
                "set OPENCLAW_REPLAY_VERIFY_TEST_KEY for hermetic test"
            ),
        })
    active_fingerprint = secrets_fingerprint or body.fingerprint

    # Verify path / 驗 path.
    try:
        signer = ManifestSigner.from_bytes_for_test(active_key_bytes, active_fingerprint)
        archive = InMemoryKeyArchive()
        # body.fingerprint mismatch active_fingerprint (secrets path) →
        # KEY_MISSING fail-closed. fingerprint 不符 fail-closed。
        archive.insert(body.fingerprint, KeyStatus.ACTIVE)
        signer.verify(
            canonical_bytes, body.declared_hash_hex,
            body.signature_hex, body.fingerprint, archive,
        )
        _emit_audit_stub(
            event_type="replay_manifest_verify_attempted",
            actor_id=actor_id, experiment_id=None,
            manifest_hash=body.declared_hash_hex,
            decision=f"verified:{wiring_status}",
            extra_payload={"fingerprint": body.fingerprint},
        )
        return _replay_response({"verified": True, "fingerprint": body.fingerprint,
                                 "wiring_status": wiring_status})
    except ValueError as exc:
        # ManifestSigner.verify raises ValueError(SignatureFailMode.X.value).
        fail_mode = str(exc)
        _emit_audit_stub(
            event_type="replay_manifest_verify_attempted",
            actor_id=actor_id, experiment_id=None,
            manifest_hash=body.declared_hash_hex,
            decision=f"failed:{fail_mode}",
            extra_payload={"fingerprint": body.fingerprint, "fail_mode": fail_mode},
        )
        return _replay_response(
            data={"verified": False, "fingerprint": body.fingerprint,
                  "fail_mode": fail_mode, "wiring_status": wiring_status},
            degraded=True, reason=f"verify_failed:{fail_mode}",
        )


@replay_router.get("/health")
async def get_replay_health(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """Backend-readiness probe for the Replay Lab as a whole.
    Replay Lab 整體後端就緒探針。

    REF-20 Sprint A R1-T3 (2026-05-04): contract health route added per
    plan §6.R1 acceptance "binary resolution + /api/v1/replay/health
    behind the intended auth policy". Auth = ``Depends(base.current_actor)``
    (logged-in only) — same pattern as ``/health/signature``; monitoring
    infra without write scope can probe.

    Aggregates four pre-conditions for ``/run`` usability:
      1. ``resolve_replay_runner_bin()`` points at an on-disk binary;
      2. ``OPENCLAW_DATA_DIR`` exists + is writable;
      3. PG up + V045 + V049 schemas reachable;
      4. binary release profile env reported (``live`` / ``paper`` / blank).

    Wiring-status priority (highest → lowest):
      ``binary_missing`` > ``degraded`` > ``ready``
    A non-``ready`` status sets ``degraded=True`` in the envelope so
    upstream monitoring (and the GUI Replay subtab gating logic) can fail
    fast without parsing the inner dict.

    REF-20 Sprint A R1-T3（2026-05-04）：依 plan §6.R1 acceptance「binary
    resolution + /api/v1/replay/health 走預期 auth policy」加上 contract
    health route。Auth = ``Depends(base.current_actor)``（已登入即可），
    與 ``/health/signature`` 對齊；不要求 write scope，monitoring infra
    無 write scope 亦可 probe。

    聚合 ``/run`` 可用性的四個前置條件：
      1. ``resolve_replay_runner_bin()`` 指向實際落盤的 binary；
      2. ``OPENCLAW_DATA_DIR`` 存在且可寫；
      3. PG 可達且 V045 + V049 schema 已部署；
      4. 上報 binary release profile env（``live`` / ``paper`` / 空）。

    wiring_status 優先級（高 → 低）：
      ``binary_missing`` > ``degraded`` > ``ready``
    任何非 ``ready`` 狀態會在 envelope 設 ``degraded=True``，讓上游
    monitoring（以及 GUI Replay subtab 的 gating 邏輯）能快速失敗，
    不必解析內部 dict。
    """
    rows, err = await _async_safe_pg_select(
        """
        SELECT
            EXISTS(
                SELECT 1 FROM information_schema.tables
                 WHERE table_schema='replay'
                   AND table_name='run_state' LIMIT 1),
            EXISTS(
                SELECT 1 FROM information_schema.tables
                 WHERE table_schema='replay'
                   AND table_name='experiments' LIMIT 1);
        """,
        (),
    )
    health = _compute_replay_health_state(rows=rows or [], pg_err=err)
    degraded = health["wiring_status"] != "ready"
    return _replay_response(
        data=health,
        degraded=degraded,
        reason=None if not degraded else f"wiring_status:{health['wiring_status']}",
    )


@replay_router.get("/health/signature")
async def get_signature_health(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """Health probe for the manifest signing module.
    Manifest 簽名模組健康探針。

    Wave 4 R20-P2b-T2 wiring: now also reports the V042 SQL archive
    presence + key fingerprint count from secrets dir.

    Wave 4 R20-P2b-T2 接線：另回報 V042 SQL archive 存在性 + secrets dir
    的 key fingerprint 數。
    """
    health: dict[str, Any] = {
        "module_importable": False,
        "secrets_dir_env_set": False,
        "fail_modes_count": 0,
        "v042_archive_present": False,
    }
    if _ms is None:
        return _replay_response(
            data=health, degraded=True,
            reason="manifest_signer_import_failed",
        )
    health["module_importable"] = True
    health["fail_modes_count"] = len(list(_ms.SignatureFailMode))

    health["secrets_dir_env_set"] = bool(os.environ.get("OPENCLAW_SECRETS_DIR"))

    # Probe V042 SQL archive presence.
    # 探測 V042 SQL archive 存在性。
    rows, err = await _async_safe_pg_select(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='replay' AND table_name='signing_keys' LIMIT 1;",
        (),
    )
    if err is None and rows:
        health["v042_archive_present"] = True

    return _replay_response(data=health)


@replay_router.get("/list")
async def get_replay_list(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status_filter: Optional[str] = Query(
        default=None,
        pattern="^(created|running|completed|failed|cancelled|starting)$",
        description="V3 §4.1 + V045 status enum filter",
    ),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """List replay experiments visible to the calling actor (paginated).
    列出呼叫方 actor 可見的 replay experiments（分頁）。

    Read-only.

    Wave 4 R20-P2b-T2 wiring: queries V045 replay.run_state for actor's
    full run history (incl. completed / failed / cancelled).

    Wave 4 R20-P2b-T2 接線：查 V045 replay.run_state 取 actor 全 run 歷史。
    """
    actor_id = str(actor.actor_id)

    # Build SQL with optional status filter.
    # 建 SQL 帶 optional status filter。
    if status_filter:
        sql = """
            SELECT run_id::text, manifest_id::text, status,
                   started_at, completed_at, exit_code,
                   runtime_environment
              FROM replay.run_state
             WHERE actor_id = %s AND status = %s
             ORDER BY started_at DESC
             LIMIT %s OFFSET %s;
        """
        params: tuple[Any, ...] = (actor_id, status_filter, limit, offset)
    else:
        sql = """
            SELECT run_id::text, manifest_id::text, status,
                   started_at, completed_at, exit_code,
                   runtime_environment
              FROM replay.run_state
             WHERE actor_id = %s
             ORDER BY started_at DESC
             LIMIT %s OFFSET %s;
        """
        params = (actor_id, limit, offset)

    rows, err = await _async_safe_pg_select(sql, params)

    if err is not None:
        return _replay_response(
            data={
                "actor_id": actor_id,
                "experiments": [],
                "limit": limit,
                "offset": offset,
                "status_filter": status_filter,
                "wiring_status": "degraded",
            },
            degraded=True,
            reason=err,
        )

    experiments = [
        {
            "run_id": r[0],
            "manifest_id": r[1],
            "status": r[2],
            "started_at": r[3].isoformat() if hasattr(r[3], "isoformat") else str(r[3]),
            "completed_at": (
                r[4].isoformat() if r[4] and hasattr(r[4], "isoformat")
                else (str(r[4]) if r[4] else None)
            ),
            "exit_code": r[5],
            "runtime_environment": r[6],
        }
        for r in rows
    ]
    return _replay_response({
        "actor_id": actor_id,
        "experiments": experiments,
        "limit": limit,
        "offset": offset,
        "status_filter": status_filter,
        "wiring_status": "pg_path_active",
    })


# ═══════════════════════════════════════════════════════════════════════════════
# Test-only helpers / 測試專用輔助
# ═══════════════════════════════════════════════════════════════════════════════


def _reset_active_runs_for_test() -> None:
    """Clear the in-memory active-run dict between tests.
    測試之間清空 in-memory active-run dict。

    LEGACY test helper. Production code MUST NOT call this. Pytest
    fixtures call this in setup/teardown to keep tests hermetic.
    LEGACY 測試輔助。生產禁呼叫；pytest fixture 在 setup/teardown 呼叫。
    """
    _ACTIVE_RUNS.clear()


__all__ = [
    "replay_router",
    "ReplayRunRequest",
    "ReplayCancelRequest",
    "ReplayManifestVerifyRequest",
    "ReplayExperimentRegisterRequest",
    "GLOBAL_ACTIVE_RUN_CAP",
    "PER_ACTOR_ACTIVE_RUN_CAP",
    "MANIFEST_TTL_DAYS",
    "PER_ACTOR_MANIFEST_CAP",
    "ADVISORY_LOCK_GLOBAL_KEY",
    "ADVISORY_LOCK_PER_ACTOR_PREFIX",
]
