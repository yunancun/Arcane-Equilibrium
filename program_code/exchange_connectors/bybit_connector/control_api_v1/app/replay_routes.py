from __future__ import annotations

"""REF-20 Paper Replay Lab — 8 routes auth scaffolding.

REF-20 Paper Replay Lab — 8 路由認證 scaffolding。

MODULE_NOTE (EN):
    Wave 2 P2a-S3 deliverable. Provides 8 read+control routes for the
    Paper Replay Lab over `/api/v1/replay`. This commit lands AUTH +
    CONCURRENCY scaffolding only; runtime wiring to the
    `replay_runner` Rust binary is deferred to Wave 4 R20-P2b-T2.

    8 routes (per V3 §6 + workplan §4 Wave 4 R20-P2b-T2):
      POST /api/v1/replay/run                   — start replay run
      GET  /api/v1/replay/status                — current run status
      POST /api/v1/replay/cancel                — cancel running replay
      GET  /api/v1/replay/report/{experiment_id} — fetch report
      GET  /api/v1/replay/manifests             — list manifests for actor
      POST /api/v1/replay/manifest/verify       — verify a manifest signature
      GET  /api/v1/replay/health/signature      — health probe (signing module)
      GET  /api/v1/replay/list                  — list replay experiments

    Hard contracts (E2 / E3 review focus):
      1. ALL routes require session-token auth via
         ``base.AuthenticatedActor = Depends(base.current_actor)``
         (mirrors scout / risk / agents routes); 401 on missing / wrong token.
      2. Mutating routes (run / cancel / manifest/verify) additionally
         require Operator role + ``replay:write`` scope via
         ``require_scope_and_operator(actor, "replay:write")``.
      3. Concurrency caps (V3 §5):
           - Global active run cap = 1 (P2/P3 phase invariant)
           - Per-actor active run cap = 1
         In-memory dict gating; Wave 4 R20-P2b-T2 swaps to PG advisory lock
         once `replay.experiments` has the running-row state machine wired.
      4. Cap exceeded → 409 Conflict (NOT 5xx); unauth → 401; missing
         scope/role → 403. ALL fail-closed.
      5. ALL PG operations go through ``_safe_pg_select`` wrapper
         (mirror of ``agents_routes_helpers._set_statement_timeout`` +
         ``except`` envelope; PG outage → degraded=true, NOT 5xx).
         V3 §12 #22 acceptance binding.
      6. Audit emit (run / cancel / handoff with actor + ts + action +
         manifest_id) is currently a STUB that logs the row payload.
         Wave 4 R20-P2b-T2 wires actual ``INSERT INTO
         learning.governance_audit_log``; this commit MUST NOT INSERT.
      7. NO wiring to ``replay_runner`` binary; NO INSERT into
         ``trading.*`` / live config; NO modification of existing
         ``auth_routes_common.py`` / ``scout_routes.py`` / ``risk_routes.py``.
      8. NO PG schema mutation (V### reservation done in P0-T5; only
         consumed by P2a-S4/S5/S6 sub-agents).
      9. Cross-platform clean per CLAUDE.md §七 ★★ (no ``/Users`` /
         ``/home`` literals).

MODULE_NOTE (中):
    Wave 2 P2a-S3 交付。在 ``/api/v1/replay`` 下提供 8 條 read+control
    路由。本 commit 僅 land AUTH + CONCURRENCY scaffolding；runtime
    wiring 到 Rust ``replay_runner`` 二進位推到 Wave 4 R20-P2b-T2。

    8 路由（V3 §6 + workplan §4 Wave 4 R20-P2b-T2）：
      POST /api/v1/replay/run                   — 啟動 replay run
      GET  /api/v1/replay/status                — 當前 run 狀態
      POST /api/v1/replay/cancel                — 取消正在跑的 replay
      GET  /api/v1/replay/report/{experiment_id} — 拉取報告
      GET  /api/v1/replay/manifests             — 列出 actor 的 manifest
      POST /api/v1/replay/manifest/verify       — 驗證 manifest 簽名
      GET  /api/v1/replay/health/signature      — 簽名模組健康探針
      GET  /api/v1/replay/list                  — 列出 replay experiments

    硬約束（E2 / E3 review 焦點）：
      1. 所有 route 必經 session token 認證
         （``base.AuthenticatedActor = Depends(base.current_actor)``，
         鏡像 scout / risk / agents routes）；missing/wrong token → 401。
      2. 變更類 route（run / cancel / manifest/verify）額外要求
         Operator 角色 + ``replay:write`` scope。
      3. 並發上限（V3 §5）：全局 active run = 1（P2/P3 不變量），
         per-actor active run = 1。in-memory dict 守門；Wave 4 R20-P2b-T2
         切換為 PG advisory lock。
      4. 上限超出 → 409 Conflict（不是 5xx）；未認證 → 401；缺
         scope/role → 403。全 fail-closed。
      5. 所有 PG 操作走 ``_safe_pg_select`` wrapper（鏡像
         ``agents_routes_helpers`` 的 ``_set_statement_timeout`` +
         ``except`` 信封；PG 中斷 → degraded=true 不 5xx）。
         V3 §12 #22 acceptance binding。
      6. Audit emit（run / cancel / handoff with actor + ts + action +
         manifest_id）目前是 STUB（只 log payload）。Wave 4 R20-P2b-T2
         實作 ``INSERT INTO learning.governance_audit_log``；本 commit
         嚴禁 INSERT。
      7. 不接 ``replay_runner`` 二進位；不寫 ``trading.*`` / live
         config；不改既有 ``auth_routes_common.py`` /
         ``scout_routes.py`` / ``risk_routes.py``。
      8. 不動 PG schema（V### reservation 由 P0-T5 完成；只供
         P2a-S4/S5/S6 sub-agent 消費）。
      9. 跨平台守則（CLAUDE.md §七 ★★）：無 ``/Users`` / ``/home``
         字面值。

SPEC: REF-20 V3 §3 G3 (8 routes auth contract) + §6 (Replay Runner
      Contract) + §12 #3 (route_auth) + §12 #22 (safe_query mirror)
Workplan: docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
          §4 Wave 2 R20-P2a-S3
Wave 2 dispatch: docs/execution_plan/2026-05-03--ref20_wave2_dispatch_v1.md
                 §3.1 (P2a security task list)
Ambiguity decisions: §2 #3 (canonical_config_parser reuse `crate::config`
                     read-end + read-only lint) — Python side equivalent =
                     reuse existing app/config_loader pattern (no fork).
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, validator

from . import main_legacy as base
from .auth import require_scope_and_operator
from .db_pool import get_pg_conn

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

# In-memory active run state. Replaced by PG advisory lock in Wave 4 R20-P2b-T2.
# The dict's key is ``actor_id``; the value is a snapshot dataclass-like dict
# with ``experiment_id`` / ``started_at_ms`` / ``manifest_hash``.
# 記憶體中 active run 狀態。Wave 4 R20-P2b-T2 改 PG advisory lock。
# dict key = ``actor_id``；value = 含 experiment_id / started_at_ms /
# manifest_hash 的快照。
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

    Wave 2 scaffold: only enforces shape + auth. Wave 4 R20-P2b-T2
    spawns the actual ``replay_runner`` Rust binary and validates
    manifest registry FK + signature before accepting.
    Wave 2 scaffold：只驗 shape + auth。Wave 4 R20-P2b-T2 真正 spawn
    ``replay_runner`` 並先驗 manifest registry FK + 簽名。
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
        # V3 §4.1: experiment_id is the primary external id; alphanumeric +
        # hyphen only to avoid path injection in /report/{experiment_id}.
        # V3 §4.1：experiment_id 是主要外部 id；只允許字母數字+連字號避免
        # path injection。
        v = v.strip()
        if not v:
            raise ValueError("experiment_id cannot be empty")
        for ch in v:
            if not (ch.isalnum() or ch in "-_"):
                raise ValueError(
                    "experiment_id may only contain alphanumeric, "
                    "hyphen, or underscore"
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
    鏡像 ``risk_routes._require_risk_write``。fail-closed via
    ``HTTPException``（401/403）由 FastAPI re-raise。
    """
    require_scope_and_operator(actor, "replay:write")


async def _check_run_caps(actor_id: str) -> None:
    """Enforce V3 §5 concurrency caps (global=1, per-actor=1).
    強制 V3 §5 並發上限（全局=1，per-actor=1）。

    Reads ``_ACTIVE_RUNS`` under ``_ACTIVE_RUNS_LOCK``. On cap exceeded
    raises ``HTTPException(409)`` with reason_codes for downstream UI
    disambiguation. ``409`` not ``500`` per dispatch §"forbidden state
    回 4xx 不 5xx" red-line.
    在 ``_ACTIVE_RUNS_LOCK`` 內讀 ``_ACTIVE_RUNS``。上限超出 raises
    ``HTTPException(409)`` + reason_codes 供下游 UI 區分。409 而非 500
    per dispatch 紅線「forbidden state 回 4xx 不 5xx」。

    NOTE / 注意:
      Caller is responsible for inserting the active run record AFTER
      this check returns successfully — atomicity guaranteed by holding
      ``_ACTIVE_RUNS_LOCK`` across check + insert (do this in the route
      handler, not split across coroutines).
      呼叫方須在本檢查通過後 insert active run 紀錄；原子性靠在 route
      handler 內持鎖跨越「檢查 + 插入」（不要拆成多個 coroutine）。
    """
    # PRECONDITION: caller must already hold ``_ACTIVE_RUNS_LOCK``.
    # 前置條件：呼叫方必先持有 ``_ACTIVE_RUNS_LOCK``。
    global_count = len(_ACTIVE_RUNS)
    if global_count >= GLOBAL_ACTIVE_RUN_CAP:
        existing_actors = list(_ACTIVE_RUNS.keys())
        # If this actor is the existing holder, surface as per-actor cap
        # (more specific reason); otherwise as global cap.
        # 若本 actor 已為持有者 → 以 per-actor cap reason 回（更具體）；
        # 否則回 global cap reason。
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
    # Per-actor check is identical when global cap = per-actor cap = 1,
    # but kept explicit for clarity + future-proofing if we relax global.
    # global=per-actor=1 時 per-actor 檢查冗餘，但保留以便將來放寬 global。
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

    Wave 4 R20-P2b-T2 replaces this with ``INSERT INTO
    learning.governance_audit_log`` once the schema enum extension /
    PM-classify decides between (a) extending V035 ``event_type`` enum
    with ``replay_run_started`` / ``replay_cancelled`` / ``replay_handoff``,
    or (b) reusing existing ``audit_write_failed`` event_type with
    ``payload->>'alert_type'`` discriminator (matching P2a-S1 cron
    pattern). PM decision deferred to Wave 4 dispatch.
    Wave 4 R20-P2b-T2 改為實際寫入；schema enum 擴展由 Wave 4 dispatch
    時 PM 決定（擴 V035 enum vs reuse audit_write_failed +
    alert_type）。

    Current stub semantics:
      - Always logs the row payload at INFO level.
      - Returns None unconditionally; never raises.
      - 100% safe to call from any path (auth fail / cap fail / happy).
    Stub 行為：永遠 log INFO；無條件 return None；不 raise。任何路徑可呼叫。
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
    # TODO REF-20 R20-P2b-T2: replace with actual INSERT INTO
    # learning.governance_audit_log; use _safe_pg_select-like wrapper
    # (write variant) to keep PG-degraded-safe semantics.
    # TODO REF-20 R20-P2b-T2：改為實際 INSERT；用類似 _safe_pg_select
    # 的 wrapper（write 變種）保留 PG-degraded-safe 語意。
    logger.info("replay_audit_stub: %s", json.dumps(payload, sort_keys=True))


# ═══════════════════════════════════════════════════════════════════════════════
# Safe PG Helper / 安全 PG 讀取輔助 (V3 §12 #22 acceptance binding)
# ═══════════════════════════════════════════════════════════════════════════════


def _safe_pg_select(
    sql: str,
    params: tuple[Any, ...] | list[Any],
) -> Tuple[list[tuple[Any, ...]], Optional[str]]:
    """Run a SELECT with statement_timeout=2s + PG-degraded fail-closed envelope.
    執行 SELECT，套 statement_timeout=2s + PG 中斷 fail-closed 信封。

    Returns (rows, err_or_none). On PG unavailability returns
    ``([], "pg_unavailable")``; on query exception returns
    ``([], f"pg_error:{type(exc).__name__}")``. Caller surfaces ``err``
    via ``degraded`` flag in the response (mirror agents_routes pattern).

    回傳 (rows, err_or_none)。PG 不可達 → ``([], "pg_unavailable")``；
    query 例外 → ``([], f"pg_error:{...}")``。caller 在回應裡用
    ``degraded`` flag 表面化（鏡像 agents_routes pattern）。

    V3 §12 #22 acceptance binding: replay_routes mirror
    ``agents_routes_helpers`` PG-degraded-safe pattern. E2 chaos drill
    PG kill simulation MUST surface ``200 + degraded=true`` (NOT 5xx).

    Sync function intended to be called from async route handlers via
    ``asyncio.to_thread`` to keep the uvicorn event loop unblocked while
    statement_timeout ticks (matches H-4 pattern in agents_routes).
    同步函數，async route handler 應透過 ``asyncio.to_thread`` 呼叫，
    避免 statement_timeout 觸發時阻塞 event loop（鏡像 agents_routes
    H-4 pattern）。
    """
    rows: list[tuple[Any, ...]] = []
    with get_pg_conn() as conn:
        if conn is None:
            return rows, "pg_unavailable"
        try:
            cur = conn.cursor()
            # SET LOCAL reverts at commit/rollback so the timeout never
            # leaks to the next pooled request.
            # SET LOCAL 在 commit/rollback 自動還原，不污染 pool。
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
# ═══════════════════════════════════════════════════════════════════════════════


@replay_router.post("/run")
async def post_replay_run(
    body: ReplayRunRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """Start a replay run for the given pre-registered manifest.
    啟動指定 pre-registered manifest 的一次 replay run。

    Auth: Operator + ``replay:write`` scope. Concurrency: global=1,
    per-actor=1 (V3 §5). Cap exceeded → 409. Wave 2 scaffold: registers
    in-memory active run + emits audit stub; does NOT spawn the
    ``replay_runner`` Rust binary (Wave 4 R20-P2b-T2 wires that).

    認證：Operator + ``replay:write`` scope。並發：global=1、per-actor=1
    （V3 §5）。上限超出 → 409。Wave 2 scaffold：登記 in-memory active
    run + 發 audit stub；不啟動 Rust ``replay_runner`` (Wave 4 接線)。
    """
    _require_replay_write(actor)
    actor_id = str(actor.actor_id)

    # Atomic check-and-set under the lock. Spec §"Per-actor concurrent
    # run cap" requires no TOCTOU between cap check and run record
    # creation; ``_ACTIVE_RUNS_LOCK`` covers both.
    # 鎖內 atomic check-and-set。spec 要求 cap check 與 run record 創建
    # 之間無 TOCTOU；``_ACTIVE_RUNS_LOCK`` 同時覆蓋兩者。
    async with _ACTIVE_RUNS_LOCK:
        await _check_run_caps(actor_id)

        # TODO REF-20 R20-P2b-T2: validate experiment_id exists in
        # replay.experiments + status='created' + signature_verified
        # before accepting; currently the stub registers any well-formed
        # id (no DB read).
        # TODO REF-20 R20-P2b-T2：先驗 replay.experiments 內 experiment_id
        # 存在 + status='created' + 簽名已驗；目前 stub 接受任何合法 id。
        run_id = uuid.uuid4().hex
        started_at_ms = int(time.time() * 1000)
        _ACTIVE_RUNS[actor_id] = {
            "run_id": run_id,
            "experiment_id": body.experiment_id,
            "started_at_ms": started_at_ms,
            "manifest_hash": None,  # populated by Wave 4 wiring after DB lookup
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
            "run_id": run_id,
            "idempotency_key": body.idempotency_key,
        },
    )

    return _replay_response({
        "run_id": run_id,
        "experiment_id": body.experiment_id,
        "started_at_ms": started_at_ms,
        "status": "running",
        # TODO REF-20 R20-P2b-T2 marker for downstream consumers.
        "wiring_status": "scaffold_only_no_runner_spawned",
    })


@replay_router.get("/status")
async def get_replay_status(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """Get current replay run status for the calling actor.
    取得當前呼叫方 actor 的 replay run 狀態。

    Read-only; no scope requirement beyond authentication. Returns
    in-memory active-run snapshot or ``None`` if idle.
    純讀；除認證外無 scope 要求。回 in-memory active-run 快照或 None。
    """
    actor_id = str(actor.actor_id)
    async with _ACTIVE_RUNS_LOCK:
        snapshot = _ACTIVE_RUNS.get(actor_id)
        # Defensive copy under lock to avoid mutation while caller reads.
        # 鎖內 defensive copy 防止外部讀取期間被改。
        snapshot_copy = dict(snapshot) if snapshot else None

    # TODO REF-20 R20-P2b-T2: cross-reference replay.experiments status
    # column (running/completed/failed/cancelled) via _async_safe_pg_select.
    # TODO REF-20 R20-P2b-T2：透過 _async_safe_pg_select 對照
    # replay.experiments status 欄位。
    return _replay_response({
        "actor_id": actor_id,
        "active_run": snapshot_copy,
        "is_idle": snapshot_copy is None,
    })


@replay_router.post("/cancel")
async def post_replay_cancel(
    body: ReplayCancelRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """Cancel the calling actor's active replay run.
    取消呼叫方 actor 的活躍 replay run。

    Auth: Operator + ``replay:write`` scope. If the active run does not
    match ``body.experiment_id`` (when provided), 409 to guard against
    stale GUI state.
    認證：Operator + ``replay:write`` scope。當提供 ``body.experiment_id``
    且不匹配活躍 run → 409 守護 stale GUI。
    """
    _require_replay_write(actor)
    actor_id = str(actor.actor_id)

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
        # If the caller specified an experiment_id, require match (mismatch
        # commonly indicates stale GUI state cancelling a fresher run).
        # 若 caller 指定 experiment_id，要求匹配（不匹配常為 stale GUI 想
        # 取消較新的 run）。
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

    # TODO REF-20 R20-P2b-T2: send cancel signal to ``replay_runner``
    # binary via IPC + update replay.experiments.status='cancelled'.
    # TODO REF-20 R20-P2b-T2：透過 IPC 對 ``replay_runner`` 發送 cancel
    # 信號 + 更新 replay.experiments.status='cancelled'。
    _emit_audit_stub(
        event_type="replay_run_cancelled",
        actor_id=actor_id,
        experiment_id=cancelled.get("experiment_id"),
        manifest_hash=cancelled.get("manifest_hash"),
        decision="cancelled",
        extra_payload={
            "reason": body.reason,
            "run_id": cancelled.get("run_id"),
        },
    )

    return _replay_response({
        "actor_id": actor_id,
        "cancelled_run_id": cancelled.get("run_id"),
        "cancelled_experiment_id": cancelled.get("experiment_id"),
        "wiring_status": "scaffold_only_no_ipc_signal_sent",
    })


@replay_router.get("/report/{experiment_id}")
async def get_replay_report(
    experiment_id: str,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """Fetch the report for a completed (or running) replay experiment.
    取得已完成（或運行中）replay experiment 的報告。

    Read-only; authentication required. Wave 2 scaffold returns a stub
    payload + degraded=true (no DB rows yet — V### migrations are
    P2a-S6 / Wave 3). Wave 4 R20-P2b-T2 wires real
    ``replay.report_artifacts`` lookup via ``_async_safe_pg_select``.
    純讀；要求認證。Wave 2 scaffold 回 stub payload + degraded=true（尚
    無 DB row — V### migrations 屬 P2a-S6 / Wave 3）。Wave 4 R20-P2b-T2
    透過 ``_async_safe_pg_select`` 查 ``replay.report_artifacts``。
    """
    # Validate experiment_id shape to prevent path injection (matches
    # ReplayRunRequest validator).
    # 驗 experiment_id 形狀避免 path injection（同 ReplayRunRequest validator）。
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

    # TODO REF-20 R20-P2b-T2: replace stub with real query:
    #   SELECT artifact_type, uri, source_mix_jsonb, metrics_jsonb, created_at
    #   FROM replay.report_artifacts WHERE experiment_id = %s ORDER BY created_at;
    # currently returns scaffold-only degraded payload.
    # TODO REF-20 R20-P2b-T2：替換為真實 query；目前回 scaffold-only degraded payload。
    return _replay_response(
        data={
            "experiment_id": experiment_id,
            "artifacts": [],
            "wiring_status": "scaffold_only_no_db_lookup",
        },
        degraded=True,
        reason="scaffold_only_v3_migration_pending",
    )


@replay_router.get("/manifests")
async def get_replay_manifests(
    limit: int = Query(default=20, ge=1, le=PER_ACTOR_MANIFEST_CAP),
    offset: int = Query(default=0, ge=0),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """List manifests created by the calling actor (paginated).
    列出呼叫方 actor 建立的 manifest（分頁）。

    Read-only. ``limit`` capped at ``PER_ACTOR_MANIFEST_CAP=20`` per V3 §5.
    純讀；``limit`` 上限 = ``PER_ACTOR_MANIFEST_CAP=20`` (V3 §5)。
    """
    actor_id = str(actor.actor_id)

    # TODO REF-20 R20-P2b-T2: replace stub with real query:
    #   SELECT experiment_id, created_at, runtime_environment, data_tier,
    #          status, expires_at
    #   FROM replay.experiments
    #   WHERE created_by = %s
    #   ORDER BY created_at DESC LIMIT %s OFFSET %s;
    # TODO REF-20 R20-P2b-T2：替換為真實 query。
    return _replay_response(
        data={
            "actor_id": actor_id,
            "manifests": [],
            "limit": limit,
            "offset": offset,
            "wiring_status": "scaffold_only_no_db_lookup",
        },
        degraded=True,
        reason="scaffold_only_v3_migration_pending",
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
    Wave 2 scaffold: signature verification module (P2a-S2 ManifestSigner)
    is already available, but this route does NOT yet wire to it (key
    archive lookup needs P2a-S4 SQL-backed KeyArchive). Returns 501 stub
    (mirrors V3 §5 "Resource limits" intent — not implemented yet).
    認證：Operator + ``replay:write`` scope（簽名驗證可能洩漏 fingerprint
    timing；限制可寫入 actor）。Wave 2 scaffold：P2a-S2 ManifestSigner
    模組已就緒，但本 route 尚未接（需 P2a-S4 SQL-backed KeyArchive）。
    回 501 stub。
    """
    _require_replay_write(actor)
    actor_id = str(actor.actor_id)

    # TODO REF-20 R20-P2b-T2: wire to ManifestSigner.verify(...)
    # backed by P2a-S4 SQL KeyArchive. Until that lands, return 501.
    # TODO REF-20 R20-P2b-T2：接 ManifestSigner.verify(...) + P2a-S4 SQL
    # KeyArchive。在此之前回 501。
    _emit_audit_stub(
        event_type="replay_manifest_verify_attempted",
        actor_id=actor_id,
        experiment_id=None,
        manifest_hash=body.declared_hash_hex,
        decision="not_implemented_scaffold_stage",
        extra_payload={
            "fingerprint": body.fingerprint,
            "signature_hex_prefix": body.signature_hex[:16],
        },
    )
    raise HTTPException(
        status_code=501,
        detail={
            "reason_codes": ["replay_verify_not_wired"],
            "message": (
                "manifest signature verification scaffold-only; "
                "Wave 4 R20-P2b-T2 wires ManifestSigner + SQL KeyArchive"
            ),
        },
    )


@replay_router.get("/health/signature")
async def get_signature_health(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """Health probe for the manifest signing module.
    Manifest 簽名模組健康探針。

    Read-only; authentication required (no scope beyond auth — health
    probes traditionally surface to anyone authenticated). Reports
    whether the Python ``ManifestSigner`` import is healthy and whether
    the secrets dir env var is set; does NOT touch the actual key file
    (key access reserved for `_require_replay_write`-gated paths).
    純讀；認證即可（health probe 慣例）。回報 Python ``ManifestSigner``
    import 是否健康 + secrets dir env var 是否設定；不碰實際 key file。
    """
    import os

    health: dict[str, Any] = {
        "module_importable": False,
        "secrets_dir_env_set": False,
        "fail_modes_count": 0,
    }
    try:
        # Defer import to keep route module load-time clean.
        # 延遲 import 保持路由模組載入時乾淨。
        from ..replay.manifest_signer import SignatureFailMode  # type: ignore

        health["module_importable"] = True
        health["fail_modes_count"] = len(list(SignatureFailMode))
    except ImportError as exc:
        # Health probe surfaces import errors via degraded flag, not 5xx;
        # operator can read the reason and decide.
        # health probe 透過 degraded 表面化 import error，不 5xx；operator
        # 讀 reason 決策。
        return _replay_response(
            data=health,
            degraded=True,
            reason=f"manifest_signer_import_failed: {type(exc).__name__}",
        )

    # OPENCLAW_SECRETS_DIR is the slot base directory per CLAUDE.md §六.
    # Check presence only; do NOT log the actual path (operator privacy).
    # OPENCLAW_SECRETS_DIR per CLAUDE.md §六 是 slot base directory。只查
    # 存在性；不 log 實際路徑（operator 隱私）。
    health["secrets_dir_env_set"] = bool(os.environ.get("OPENCLAW_SECRETS_DIR"))

    return _replay_response(data=health)


@replay_router.get("/list")
async def get_replay_list(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status_filter: Optional[str] = Query(
        default=None,
        pattern="^(created|running|completed|failed|cancelled)$",
        description="V3 §4.1 status enum filter",
    ),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """List replay experiments visible to the calling actor (paginated).
    列出呼叫方 actor 可見的 replay experiments（分頁）。

    Read-only. ``status_filter`` validates against V3 §4.1 enum.
    純讀；``status_filter`` 對照 V3 §4.1 enum 驗證。
    """
    actor_id = str(actor.actor_id)

    # TODO REF-20 R20-P2b-T2: replace stub with real query:
    #   SELECT experiment_id, parent_experiment_id, created_at, status,
    #          runtime_environment, data_tier, expires_at
    #   FROM replay.experiments
    #   WHERE (created_by = %s OR runtime_environment = 'shared')
    #     AND (%s::text IS NULL OR status = %s)
    #   ORDER BY created_at DESC LIMIT %s OFFSET %s;
    # TODO REF-20 R20-P2b-T2：替換為真實 query。
    return _replay_response(
        data={
            "actor_id": actor_id,
            "experiments": [],
            "limit": limit,
            "offset": offset,
            "status_filter": status_filter,
            "wiring_status": "scaffold_only_no_db_lookup",
        },
        degraded=True,
        reason="scaffold_only_v3_migration_pending",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Test-only helpers / 測試專用輔助
# ═══════════════════════════════════════════════════════════════════════════════


def _reset_active_runs_for_test() -> None:
    """Clear the in-memory active-run dict between tests.
    測試之間清空 in-memory active-run dict。

    Production code MUST NOT call this. Pytest fixtures call this in
    setup/teardown to keep tests hermetic.
    生產程式碼禁呼叫；pytest fixture 在 setup/teardown 呼叫保持封閉。
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
]
