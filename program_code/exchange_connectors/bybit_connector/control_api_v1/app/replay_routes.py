from __future__ import annotations

"""REF-20 Paper Replay Lab — 8 routes wired to T1 binary + PG advisory lock.

REF-20 Paper Replay Lab — 8 路由接 T1 binary + PG advisory lock。

MODULE_NOTE (EN):
    Wave 4 R20-P2b-T2 + T3 merged deliverable (per Wave 2 dispatch v1.1
    §6 Option C decision: PG advisory lock retrofit replaces in-memory
    `_ACTIVE_RUNS` dict to make concurrency caps survive the
    `OPENCLAW_API_WORKERS=4` uvicorn default without state drift).

    8 routes (V3 §6 + workplan §4 Wave 4 R20-P2b-T2):
      POST /api/v1/replay/run                    — start replay run
                                                    (spawns replay_runner subprocess)
      GET  /api/v1/replay/status                 — current run status
                                                    (per-actor active snapshot)
      POST /api/v1/replay/cancel                 — cancel running replay
                                                    (SIGTERM via run_state_manager)
      GET  /api/v1/replay/report/{experiment_id} — fetch report
                                                    (reads replay.report_artifacts JSON files)
      GET  /api/v1/replay/manifests              — list manifests for actor
      POST /api/v1/replay/manifest/verify        — verify a manifest signature
                                                    (calls ManifestSigner via P2a-S2)
      GET  /api/v1/replay/health/signature       — health probe (signing module)
      GET  /api/v1/replay/list                   — list replay experiments

    Hard contracts (E2 / E3 / MIT review focus):
      1. ALL routes require session-token auth (401 on missing/wrong token).
      2. Mutating routes (run/cancel/manifest/verify) require Operator +
         ``replay:write`` scope (403 on missing).
      3. Concurrency caps (V3 §5: global=1, per-actor=1) — PRIMARY path:
         PG advisory locks ``pg_try_advisory_xact_lock(hashtext(...))``
         persisted in ``replay.run_state`` (V045); FALLBACK: in-memory
         ``_ACTIVE_RUNS`` dict (V045 absent / PG unreachable).
      4. Cap exceeded → 409 Conflict (NOT 5xx); fail-closed throughout.
      5. ALL PG operations go through ``_safe_pg_select`` wrapper
         (PG outage → degraded=true, NOT 5xx). V3 §12 #22 binding.
      6. Audit emit logged via INFO (V035 enum extension PM-deferred).
      7. ``replay_runner`` binary path: ``OPENCLAW_REPLAY_RUNNER_BIN`` env
         override (default ``$OPENCLAW_BASE_DIR/rust/openclaw_engine/
         target/release/replay_runner``). Subprocess.Popen wrapped — env
         whitelisted (V3 §6.2 no-secrets); args ``--manifest-id <UUID>
         --output-dir <path> --run-id <UUID>``.
      8. Cross-platform clean per CLAUDE.md §七 ★★ (no /Users / /home
         literals; resolves via OPENCLAW_BASE_DIR / OPENCLAW_DATA_DIR).

MODULE_NOTE (中):
    Wave 4 R20-P2b-T2 + T3 合併交付。8 路由 wired 到 replay_runner Rust
    binary + V045 PG advisory lock concurrency-cap path（取代 in-memory
    `_ACTIVE_RUNS` dict）。in-memory dict 保留為 LEGACY FALLBACK，V045 缺
    或 PG 不可達時走（保 既有 4 auth pytest 不破 + pre-V045-deploy 平滑
    過渡）。route 的硬約束、subprocess env 白名單、PG-degraded 信封語意
    與 EN 部分等價，請參考上方逐條。

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

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, validator

from . import main_legacy as base
from .auth import require_scope_and_operator
from .db_pool import get_pg_conn

# Replay helpers — relative-package first (production), absolute fallback
# (test layout via conftest.py PROJECT_ROOT injection).
# Replay helper：先 relative-package（生產），fail 時 absolute（測試佈局）。
try:
    from ..replay import route_helpers as _rh  # type: ignore[no-redef]
    from ..replay import manifest_signer as _ms  # type: ignore[no-redef]
except ImportError:
    from replay import route_helpers as _rh  # type: ignore[no-redef]
    try:
        from replay import manifest_signer as _ms  # type: ignore[no-redef]
    except ImportError:
        _ms = None  # type: ignore[assignment]
ADVISORY_LOCK_GLOBAL_KEY = _rh.ADVISORY_LOCK_GLOBAL_KEY
ADVISORY_LOCK_PER_ACTOR_PREFIX = _rh.ADVISORY_LOCK_PER_ACTOR_PREFIX
_count_active_runs_for_actor = _rh.count_active_runs_for_actor
_count_active_runs_global = _rh.count_active_runs_global
_resolve_artifact_output_dir = _rh.resolve_artifact_output_dir
_spawn_replay_runner = _rh.spawn_replay_runner
_try_acquire_pg_advisory_locks = _rh.try_acquire_pg_advisory_locks
_v045_table_present = _rh.v045_table_present

logger = logging.getLogger(__name__)


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
# ═══════════════════════════════════════════════════════════════════════════════


class ReplayRunRequest(BaseModel):
    """POST /run body — start a replay run.
    POST /run body — 啟動一次 replay run。

    Wave 4 wiring: validates shape + auth, then spawns replay_runner
    subprocess via OPENCLAW_REPLAY_RUNNER_BIN. Concurrency cap enforced
    via PG advisory lock (primary) or in-memory dict (fallback).
    Wave 4 接線：驗 shape + auth，然後透過 OPENCLAW_REPLAY_RUNNER_BIN
    spawn replay_runner 子程序。並發上限由 PG advisory lock（主路徑）
    或 in-memory dict（fallback）強制。
    """

    experiment_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Pre-registered manifest experiment_id (V3 §4.1 schema)",
    )
    idempotency_key: Optional[str] = Field(
        default=None,
        max_length=128,
        description=(
            "Optional idempotency key per V3 §4.1 lineage; if provided "
            "and matches an existing run for this actor, return cached."
        ),
    )

    @validator("experiment_id")
    def _validate_experiment_id(cls, v: str) -> str:
        # Alphanumeric + hyphen/underscore only (path-injection guard).
        # 只允許字母數字+連字號/底線（防 path injection）。
        v = v.strip()
        if not v:
            raise ValueError("experiment_id cannot be empty")
        for ch in v:
            if not (ch.isalnum() or ch in "-_"):
                raise ValueError(
                    "experiment_id may only contain alphanumeric, hyphen, or underscore"
                )
        return v


class ReplayCancelRequest(BaseModel):
    """POST /cancel body — cancel currently running replay.
    POST /cancel body — 取消當前運行中的 replay。
    """

    experiment_id: Optional[str] = Field(
        default=None,
        max_length=128,
        description=(
            "If set, only cancel if the active run matches this id; "
            "guards against stale GUI state cancelling a fresher run."
        ),
    )
    reason: Optional[str] = Field(
        default=None,
        max_length=512,
        description="Operator-supplied cancellation reason (audit row).",
    )


class ReplayManifestVerifyRequest(BaseModel):
    """POST /manifest/verify body — verify HMAC signature of a manifest.
    POST /manifest/verify body — 驗證 manifest 的 HMAC 簽名。
    """

    canonical_bytes_b64: str = Field(
        ...,
        min_length=1,
        description="Base64-encoded canonical manifest bytes.",
    )
    declared_hash_hex: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Declared sha256 hex digest of the body.",
    )
    signature_hex: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Declared HMAC-SHA256 signature (hex).",
    )
    fingerprint: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="16-char key fingerprint (per helper script algorithm).",
    )


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


def _emit_audit_stub(
    *,
    event_type: str,
    actor_id: str,
    experiment_id: Optional[str],
    manifest_hash: Optional[str],
    decision: str,
    extra_payload: Optional[dict[str, Any]] = None,
) -> None:
    """STUB audit emitter — log only, no DB INSERT.
    STUB audit 發射器 — 僅 log，不寫 DB。

    Wave 4 R20-P2b-T2: kept as INFO log until V035 enum extension or
    alert_type discriminator decision (PM-deferred). Subsequent commit
    will replace with INSERT INTO learning.governance_audit_log.
    Wave 4 R20-P2b-T2：保 INFO log，等 V035 enum 擴展或 alert_type
    discriminator 決策（PM 延後）。後續 commit 改為實際 INSERT。
    """
    payload = {
        "event_type": event_type,
        "actor_id": actor_id,
        "experiment_id": experiment_id,
        "manifest_hash": manifest_hash,
        "decision": decision,
        "ts_iso": datetime.now(timezone.utc).isoformat(),
        "extra": extra_payload or {},
    }
    logger.info("replay_audit_stub: %s", json.dumps(payload, sort_keys=True))


# ═══════════════════════════════════════════════════════════════════════════════
# Safe PG Helper / 安全 PG 讀取輔助 (V3 §12 #22 acceptance binding)
# ═══════════════════════════════════════════════════════════════════════════════


def _safe_pg_select(
    sql: str,
    params: tuple[Any, ...] | list[Any],
) -> Tuple[list[tuple[Any, ...]], Optional[str]]:
    """Run SELECT with statement_timeout=2s + PG-degraded fail-closed envelope.
    執行 SELECT，套 statement_timeout=2s + PG 中斷 fail-closed 信封。

    Returns (rows, err_or_none); PG unreachable → ``([], "pg_unavailable")``;
    query exception → ``([], f"pg_error:{type(exc).__name__}")``. Caller
    surfaces err via ``degraded`` flag (V3 §12 #22 binding).
    """
    rows: list[tuple[Any, ...]] = []
    with get_pg_conn() as conn:
        if conn is None:
            return rows, "pg_unavailable"
        try:
            cur = conn.cursor()
            cur.execute(
                "SET LOCAL statement_timeout = %s",
                (_STATEMENT_TIMEOUT_MS,),
            )
            cur.execute(sql, tuple(params))
            rows = list(cur.fetchall())
            return rows, None
        except Exception as exc:
            logger.warning("replay_routes safe_pg_select failed: %s", exc)
            return rows, f"pg_error:{type(exc).__name__}"


async def _async_safe_pg_select(
    sql: str,
    params: tuple[Any, ...] | list[Any],
) -> Tuple[list[tuple[Any, ...]], Optional[str]]:
    """Async wrapper around ``_safe_pg_select`` (H-4 pattern).
    ``_safe_pg_select`` 的 async wrapper（H-4 pattern）。
    """
    return await asyncio.to_thread(_safe_pg_select, sql, params)


def _replay_response(
    data: Any,
    *,
    degraded: bool = False,
    reason: Optional[str] = None,
) -> dict[str, Any]:
    """Standard envelope mirroring ``agents_routes`` shape.
    標準回應信封，鏡像 ``agents_routes`` 形狀。
    """
    return {
        "ok": True,
        "data": data,
        "degraded": degraded,
        "reason": reason,
        "is_simulated": False,
        "data_category": "replay_lab",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Routes / 路由
#
# Note / 註：subprocess Popen wrapper (_spawn_replay_runner) is imported from
# replay.route_helpers (Wave 4 R20-P2b-T2 split per CLAUDE.md §九 1500 LOC cap).
# ═══════════════════════════════════════════════════════════════════════════════


@replay_router.post("/run")
async def post_replay_run(
    body: ReplayRunRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """Start a replay run for the given pre-registered manifest.
    啟動指定 pre-registered manifest 的一次 replay run。

    Auth: Operator + ``replay:write`` scope. Concurrency: global=1,
    per-actor=1 (V3 §5).

    Wave 4 R20-P2b-T2 wiring:
      1. Acquire PG advisory locks within transaction (primary path)
         OR fall back to in-memory dict (V045 absent / PG unavailable).
      2. INSERT replay.run_state row with status='starting'.
      3. Spawn replay_runner subprocess; capture pid.
      4. UPDATE replay.run_state with pid + status='running'.
      5. Return run_id + experiment_id + status to caller.

    Wave 4 R20-P2b-T2 接線：
      1. 在 transaction 內取 PG advisory lock（主路徑）；V045 缺 / PG 不可達
         時 fallback in-memory dict。
      2. INSERT replay.run_state，status='starting'。
      3. Spawn replay_runner 子程序；拿 pid。
      4. UPDATE replay.run_state pid + status='running'。
      5. 回 run_id + experiment_id + status。
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
                # NOTE: experiment_id is the user-facing ID; manifest_id is
                # logical UUID that V045 stores. We use the experiment_id
                # as a synthetic manifest_id source by hashing — Wave 3
                # ledger maps the V### registry FK separately.
                #
                # NOTE：experiment_id 是 user-facing ID；manifest_id 是
                # V045 存的邏輯 UUID。本處用 experiment_id 透過 UUID5
                # 衍生 — Wave 3 ledger 另行 map V### registry FK。
                #
                # We use a UUID5 namespace derivation so the same
                # experiment_id always yields the same manifest_id (allows
                # idempotency on retry).
                # 用 UUID5 namespace 衍生：同 experiment_id 永得同 manifest_id
                # （重試時冪等）。
                manifest_uuid_namespace = uuid.UUID(
                    "00000000-0000-0000-0000-000020260503"
                )
                manifest_uuid = uuid.uuid5(
                    manifest_uuid_namespace, body.experiment_id
                )

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

                # 4) Spawn subprocess (still holding xact lock).
                # 4) Spawn 子程序（仍持 xact lock）。
                output_dir = _resolve_artifact_output_dir(run_id_local)
                pid, spawn_err = _spawn_replay_runner(
                    run_id=run_id_local,
                    manifest_id=str(manifest_uuid),
                    output_dir=output_dir,
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

                # 5) UPDATE pid + status='running'.
                # 5) UPDATE pid + status='running'。
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

    if pg_err and pg_err.startswith(("spawn_error:", "mkdir_error:", "pg_error:")):
        # Hard failure on PG path; surface 503 so operator can inspect logs.
        # PG 路徑硬失敗；503 讓 operator 查 log。
        raise HTTPException(
            status_code=503,
            detail={
                "reason_codes": ["replay_runner_spawn_failed"],
                "message": f"replay_runner failed to spawn: {pg_err}",
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

    # Try PG path.
    # 試 PG 路徑。
    def _do_pg_cancel() -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        """Sync helper for cancel transaction.
        cancel 交易的同步 helper。

        Returns / 回傳:
            (cancelled_dict, err_or_none)
        """
        with get_pg_conn() as conn:
            if conn is None:
                return None, "pg_unavailable"
            try:
                cur = conn.cursor()
                cur.execute("SET LOCAL statement_timeout = %s", (_STATEMENT_TIMEOUT_MS,))
                if not _v045_table_present(cur):
                    return None, "v045_absent"

                cur.execute(
                    """
                    SELECT run_id::text, manifest_id::text,
                           subprocess_pid, status
                      FROM replay.run_state
                     WHERE actor_id = %s
                       AND status IN ('starting','running')
                     ORDER BY started_at DESC
                     LIMIT 1;
                    """,
                    (actor_id,),
                )
                row = cur.fetchone()
                if row is None:
                    return None, "no_active_run"
                run_id, manifest_id_uuid, pid, status = row

                # Send SIGTERM if pid known.
                # 若 pid 已知則送 SIGTERM。
                if pid is not None and pid > 0:
                    try:
                        import signal
                        os.kill(pid, signal.SIGTERM)
                        logger.info(
                            "cancel_run: SIGTERM sent to pid=%d run_id=%s",
                            pid, run_id,
                        )
                    except ProcessLookupError:
                        logger.info(
                            "cancel_run: pid=%d already exited; "
                            "flipping DB only", pid,
                        )
                    except (PermissionError, OSError) as exc:
                        logger.warning(
                            "cancel_run: os.kill(pid=%d) failed: %s; "
                            "flipping DB only", pid, exc,
                        )

                # Flip DB row.
                # 翻 DB row。
                cur.execute(
                    """
                    UPDATE replay.run_state
                       SET status = 'cancelled',
                           exit_code = -1,
                           completed_at = NOW(),
                           cancel_reason = %s
                     WHERE run_id = %s::uuid
                       AND status IN ('starting','running')
                    RETURNING run_id::text;
                    """,
                    (body.reason, run_id),
                )
                flipped = cur.fetchone()
                conn.commit()
                if flipped is None:
                    return None, "race_already_final"
                return {
                    "run_id": run_id,
                    "manifest_id": manifest_id_uuid,
                    "subprocess_pid": pid,
                    "former_status": status,
                }, None
            except Exception as exc:
                logger.warning("replay_routes /cancel PG path exception: %s", exc)
                try:
                    conn.rollback()
                except Exception:
                    pass
                return None, f"pg_error:{type(exc).__name__}"

    cancelled_dict, pg_err = await asyncio.to_thread(_do_pg_cancel)

    if cancelled_dict is not None and pg_err is None:
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

    Read-only; authentication required.

    Wave 4 R20-P2b-T2 wiring: queries replay.report_artifacts (V046) for
    the experiment_id's run; reads each artifact JSON from filesystem.

    Wave 4 R20-P2b-T2 接線：查 replay.report_artifacts（V046）取
    experiment_id 對應 run；從 filesystem 讀每個 artifact JSON。
    """
    # Validate experiment_id shape.
    # 驗 experiment_id 形狀。
    for ch in experiment_id:
        if not (ch.isalnum() or ch in "-_"):
            raise HTTPException(
                status_code=400,
                detail={
                    "reason_codes": ["replay_invalid_experiment_id"],
                    "message": "experiment_id may only contain alphanumeric, hyphen, or underscore",
                },
            )
    if len(experiment_id) > 128:
        raise HTTPException(
            status_code=400,
            detail={
                "reason_codes": ["replay_invalid_experiment_id"],
                "message": "experiment_id exceeds 128 chars",
            },
        )

    # Derive manifest_uuid from experiment_id (same UUID5 derivation as
    # POST /run for cross-route consistency).
    # 從 experiment_id 衍生 manifest_uuid（同 POST /run 的 UUID5 衍生
    # 以保跨 route 一致）。
    manifest_uuid_namespace = uuid.UUID("00000000-0000-0000-0000-000020260503")
    manifest_uuid = str(uuid.uuid5(manifest_uuid_namespace, experiment_id))

    rows, err = await _async_safe_pg_select(
        """
        SELECT a.artifact_id::text, a.artifact_type, a.artifact_path,
               a.byte_size, a.is_mock,
               EXTRACT(EPOCH FROM a.created_at)*1000 AS created_at_ms,
               s.run_id::text, s.status, s.exit_code,
               EXTRACT(EPOCH FROM s.started_at)*1000 AS started_at_ms,
               EXTRACT(EPOCH FROM s.completed_at)*1000 AS completed_at_ms
          FROM replay.report_artifacts a
          JOIN replay.run_state s ON a.run_id = s.run_id
         WHERE s.manifest_id = %s::uuid
         ORDER BY a.created_at;
        """,
        (manifest_uuid,),
    )

    if err is not None:
        # PG outage / V046 absent → 200 + degraded (V3 §12 #22 mirror).
        # PG outage / V046 缺 → 200 + degraded（V3 §12 #22 鏡像）。
        return _replay_response(
            data={
                "experiment_id": experiment_id,
                "manifest_id": manifest_uuid,
                "artifacts": [],
                "wiring_status": "degraded",
            },
            degraded=True,
            reason=err,
        )

    artifacts = []
    for row in rows:
        artifact = {
            "artifact_id": row[0],
            "artifact_type": row[1],
            "artifact_path": row[2],
            "byte_size": row[3],
            "is_mock": row[4],
            "created_at_ms": int(row[5]) if row[5] is not None else None,
        }
        # Optionally read JSON payload from filesystem if file exists.
        # We bound the size to 256 KB to avoid OOM on large artifacts.
        # 可選：file 存在時讀 JSON payload。bound 256 KB 避免 OOM。
        try:
            artifact_path = Path(row[2])
            if artifact_path.is_file() and (row[3] or 0) <= 256 * 1024:
                with open(artifact_path, "rb") as f:
                    payload_bytes = f.read(256 * 1024)
                artifact["payload"] = json.loads(payload_bytes.decode("utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            artifact["payload_read_error"] = (
                f"{type(exc).__name__}: {str(exc)[:80]}"
            )
        artifacts.append(artifact)

    # Run-level summary from JOIN'ed columns (rows[0] has run-level fields).
    # JOIN 後的 run-level summary（rows[0] 含 run-level 欄位）。
    run_summary: Optional[dict[str, Any]] = None
    if rows:
        first = rows[0]
        run_summary = {
            "run_id": first[6],
            "status": first[7],
            "exit_code": first[8],
            "started_at_ms": int(first[9]) if first[9] is not None else None,
            "completed_at_ms": int(first[10]) if first[10] is not None else None,
        }

    return _replay_response({
        "experiment_id": experiment_id,
        "manifest_id": manifest_uuid,
        "run": run_summary,
        "artifacts": artifacts,
        "artifact_count": len(artifacts),
        "wiring_status": "pg_path_active",
    })


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

    Wave 4 R20-P2b-T2 wiring: calls ManifestSigner.verify() backed by
    the InMemoryKeyArchive (P2a-S2 module). Production path uses
    SQL-backed KeyArchive once V042 lands and Wave 6 archive bridge
    deploys.

    Wave 4 R20-P2b-T2 接線：呼叫 ManifestSigner.verify()，由 InMemoryKeyArchive
    （P2a-S2 模組）支撐。生產路徑要等 V042 land + Wave 6 archive 橋接。
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

    # Test-only path: if OPENCLAW_REPLAY_VERIFY_TEST_KEY env set, use it
    # to seed an InMemoryKeyArchive (for hermetic integration tests).
    # 測試路徑：OPENCLAW_REPLAY_VERIFY_TEST_KEY env 設時用以 seed
    # InMemoryKeyArchive（hermetic integration test 用）。
    test_key_hex = os.environ.get("OPENCLAW_REPLAY_VERIFY_TEST_KEY", "")
    if not test_key_hex:
        # Production path: V042 SQL archive lookup not yet wired.
        # 生產路徑：V042 SQL archive 尚未接。
        _emit_audit_stub(
            event_type="replay_manifest_verify_attempted",
            actor_id=actor_id,
            experiment_id=None,
            manifest_hash=body.declared_hash_hex,
            decision="not_implemented_archive_path",
            extra_payload={
                "fingerprint": body.fingerprint,
                "signature_hex_prefix": body.signature_hex[:16],
            },
        )
        raise HTTPException(
            status_code=501,
            detail={
                "reason_codes": ["replay_verify_archive_not_wired"],
                "message": (
                    "manifest signature verification SQL archive (V042) "
                    "not yet wired; set OPENCLAW_REPLAY_VERIFY_TEST_KEY for "
                    "hermetic test or wait for Wave 6 archive bridge deploy"
                ),
            },
        )

    # Hermetic test path.
    # Hermetic test 路徑。
    try:
        key_bytes = bytes.fromhex(test_key_hex)
        signer = ManifestSigner.from_bytes_for_test(key_bytes, body.fingerprint)
        archive = InMemoryKeyArchive()
        archive.upsert_key(body.fingerprint, key_bytes, KeyStatus.ACTIVE)
        signer.verify(
            canonical_bytes,
            body.declared_hash_hex,
            body.signature_hex,
            body.fingerprint,
            archive,
        )
        _emit_audit_stub(
            event_type="replay_manifest_verify_attempted",
            actor_id=actor_id,
            experiment_id=None,
            manifest_hash=body.declared_hash_hex,
            decision="verified_test_path",
            extra_payload={"fingerprint": body.fingerprint},
        )
        return _replay_response({
            "verified": True,
            "fingerprint": body.fingerprint,
            "wiring_status": "test_key_path",
        })
    except ValueError as exc:
        # ManifestSigner.verify raises ValueError(SignatureFailMode.X.value).
        # ManifestSigner.verify 透過 ValueError(SignatureFailMode.X.value) 表失敗。
        fail_mode = str(exc)
        _emit_audit_stub(
            event_type="replay_manifest_verify_attempted",
            actor_id=actor_id,
            experiment_id=None,
            manifest_hash=body.declared_hash_hex,
            decision=f"failed:{fail_mode}",
            extra_payload={
                "fingerprint": body.fingerprint,
                "fail_mode": fail_mode,
            },
        )
        return _replay_response(
            data={
                "verified": False,
                "fingerprint": body.fingerprint,
                "fail_mode": fail_mode,
                "wiring_status": "test_key_path",
            },
            degraded=True,
            reason=f"verify_failed:{fail_mode}",
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
    "GLOBAL_ACTIVE_RUN_CAP",
    "PER_ACTOR_ACTIVE_RUN_CAP",
    "MANIFEST_TTL_DAYS",
    "PER_ACTOR_MANIFEST_CAP",
    "ADVISORY_LOCK_GLOBAL_KEY",
    "ADVISORY_LOCK_PER_ACTOR_PREFIX",
]
