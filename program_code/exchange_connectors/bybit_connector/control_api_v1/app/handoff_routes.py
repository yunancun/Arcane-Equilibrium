from __future__ import annotations

"""REF-20 P6 Handoff routes — server-side regex + cooldown + idempotency.

REF-20 P6 Handoff 路由 — server-side regex + cooldown + idempotency。

MODULE_NOTE (EN):
    Wave 8 R20-P6-S13/S14/S15 (Bounded Demo Handoff backend security trio).
    Extracted as a NEW file (NOT added to replay_routes.py) because that
    module is at 1498/1500 LOC (CLAUDE.md §九 hard cap = 1500). Per
    workplan §4 Wave 8 row, the trio lands handoff_routes.py + V044 SQL +
    handoff_audit.py.

    Two routes (V3 §11 P6 + workplan §4 Wave 8):
      POST /api/v1/replay/handoff           — submit handoff request
      GET  /api/v1/replay/handoff/recent    — last 5 handoff records (footer)

    Hard contracts (E2 / E3 / FA review focus):
      1. Server-side regex: ^HANDOFF [a-z0-9-]{36}$ (V3 §12 #20 binding).
         Defends against client-side tamper of the typed phrase JS regex.
      2. Phrase mismatch: typed_phrase MUST equal 'HANDOFF <experiment_id>';
         even after format passes, the experiment_id substring is verified.
      3. Cooldown: ≥30s between handoffs from the SAME actor (4-防誤等級 4).
         Different actor bypasses cooldown (dual-actor handoff supported).
      4. Idempotency: V044 UNIQUE(actor_id, idempotency_key) short-circuits
         duplicate POST /handoff with cached trace_id return.
      5. Atomic commit: replay.handoff_requests INSERT + governance audit
         INSERT happen under the SAME transaction (atomic write or rollback).
      6. Hash-only typed phrase: V044 typed_phrase_hash + V035-extended audit
         payload typed_phrase_hash; raw phrase NEVER persisted.
      7. PG-degraded posture mirrors replay_routes (`_safe_pg_select` /
         degraded=true, NOT 5xx). V3 §12 #22 mirror.
      8. Auth: Operator + replay:write scope (mirrors POST /run).
      9. CLAUDE.md §七 ★★ no /Users / /home literals.

    Wiring with sibling Wave 8 frontend chain (E1a):
      - H1 typed-confirmation modal (UX subdoc §6, 9 fields) submits to
        POST /api/v1/replay/handoff.
      - H3 footer recent 5 list reads from
        GET /api/v1/replay/handoff/recent?n=5.
      - H4 idempotency key handling generates UUID v4 client-side; server
        UNIQUE constraint enforces (V044).

MODULE_NOTE (中):
    Wave 8 R20-P6-S13/S14/S15（Bounded Demo Handoff 後端安全三劍客）。
    抽 NEW 檔（不擠 replay_routes.py）— 後者已 1498/1500（§九 1500 硬上限）。
    Per workplan §4 Wave 8 row，三件落 handoff_routes.py + V044 SQL +
    handoff_audit.py。

    兩條路由：
      POST /api/v1/replay/handoff           — 提交 handoff 請求
      GET  /api/v1/replay/handoff/recent    — 最近 5 筆（footer）

    硬約束（E2 / E3 / FA 審查焦點）：
      1. Server-side regex：^HANDOFF [a-z0-9-]{36}$（V3 §12 #20 綁定）；
         防 client-side JS regex 被竄改。
      2. Phrase 比對：typed_phrase 必等於 'HANDOFF <experiment_id>'；
         過了格式後仍驗 experiment_id 子串。
      3. Cooldown：同 actor ≥30s（4-防誤等級 4）；不同 actor 跳過 cooldown
         （支援 dual-actor handoff）。
      4. Idempotency：V044 UNIQUE(actor_id, idempotency_key) 短路重送，
         回傳 cached trace_id。
      5. Atomic：replay.handoff_requests INSERT + audit INSERT 同 transaction
         （原子寫或原子 rollback）。
      6. Hash-only typed phrase：V044 typed_phrase_hash + V035-擴 audit
         payload typed_phrase_hash；raw phrase 永不持久化。
      7. PG-degraded 信封鏡像 replay_routes；degraded=true，非 5xx。
      8. Auth：Operator + replay:write scope（鏡像 POST /run）。
      9. CLAUDE.md §七 ★★ 無 /Users 或 /home 字面值。

SPEC: REF-20 V3 §11 P6 + §12 #20 + DOC-08 §12 governance audit
Workplan: docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
          §4 Wave 8 R20-P6-S13/S14/S15
UX SoT: docs/execution_plan/2026-05-02--ref20_ux_subdoc_v1.md §6 Handoff
"""

import asyncio
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field, validator

from . import main_legacy as base
from .auth import require_scope_and_operator
from .db_pool import get_pg_conn

# Replay handoff_audit helper — relative-package first (production), absolute
# fallback (test layout via conftest.py PROJECT_ROOT injection).
# handoff_audit helper：先 relative（生產），fail 時 absolute（測試）。
try:
    from ..replay import handoff_audit as _ha  # type: ignore[no-redef]
except ImportError:
    from replay import handoff_audit as _ha  # type: ignore[no-redef]

_emit_handoff_audit = _ha.emit_handoff_audit
_HandoffAuditRequest = _ha.HandoffAuditRequest
_hash_typed_phrase = _ha.hash_typed_phrase

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Router / 路由器
# ═══════════════════════════════════════════════════════════════════════════════


handoff_router = APIRouter(
    prefix="/api/v1/replay",
    tags=["Replay Lab Handoff / 重放實驗室移交"],
)


# ═══════════════════════════════════════════════════════════════════════════════
# Constants / 常數
# ═══════════════════════════════════════════════════════════════════════════════


# V3 §12 #20 server-side regex (defense-in-depth vs client-side JS tamper).
# Format: literal "HANDOFF " (uppercase + space) then 36-char UUID v4 with
# lowercase a-z, digit 0-9, and hyphen only. Length must be exactly 36
# characters AFTER the prefix.
#
# V3 §12 #20 server-side regex（client-side JS 被竄改的防禦）。
# 格式：字面 "HANDOFF " + 36 字 UUID v4（小寫 a-z + 數字 + 連字號）。
HANDOFF_PHRASE_REGEX = re.compile(r"^HANDOFF [a-z0-9\-]{36}$")

# V3 §11 P6 + UX subdoc §6 cooldown ≥30s between same-actor handoffs.
# Different actor bypasses cooldown to support dual-actor pattern.
# 同 actor 兩次 handoff 之間 ≥30s 冷卻；不同 actor 跳過支援 dual-actor。
COOLDOWN_SECONDS = 30

# Recent N footer cap (UX subdoc §6 footer ≥5 records).
# Footer N 上限（UX subdoc §6 ≥5 筆）。
RECENT_N_DEFAULT = 5
RECENT_N_MAX = 50

# Mirror replay_routes._STATEMENT_TIMEOUT_MS for V3 §12 #22 PG-degraded
# fail-closed envelope.
# 鏡像 replay_routes._STATEMENT_TIMEOUT_MS（V3 §12 #22 信封）。
_STATEMENT_TIMEOUT_MS = 2_000

# Idempotency-Key header max length (UI generates 36-char UUID v4 by default;
# we cap at 128 for safety / future extension).
# Idempotency-Key header 最大長度（UI 預設 36 字 UUID v4；cap 128 預留）。
IDEMPOTENCY_KEY_MAX_LEN = 128


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic Models / 請求響應模型
# ═══════════════════════════════════════════════════════════════════════════════


class HandoffRequest(BaseModel):
    """POST /handoff body — submit a demo handoff request.

    POST /handoff body — 提交 demo handoff 請求。

    9 fields per UX subdoc §6 Handoff sub-tab:
      experiment_id / manifest_id / typed_phrase / idempotency_key (header)
      operator_notes / baseline_delta / data_tier / execution_confidence /
      trace_id (server-generated).

    本 model 收 4 個 client-supplied 欄位（experiment_id / manifest_id /
    typed_phrase / operator_notes）；idempotency_key 從 header 拿；
    其餘由 server 補（trace_id / ts / cached / result）。
    """

    experiment_id: str = Field(
        ...,
        min_length=36,
        max_length=36,
        description="Pre-registered experiment_id; UUID v4 36-char string.",
    )
    manifest_id: str = Field(
        ...,
        min_length=36,
        max_length=36,
        description="Manifest UUID; UUID v4 36-char string.",
    )
    typed_phrase: str = Field(
        ...,
        min_length=44,  # 'HANDOFF ' (8) + 36 chars
        max_length=44,
        description=(
            "Operator-typed confirmation phrase: 'HANDOFF <experiment_id>'. "
            "Server-side regex enforces ^HANDOFF [a-z0-9-]{36}$ (V3 §12 #20)."
        ),
    )
    operator_notes: Optional[str] = Field(
        default=None,
        max_length=512,
        description="Operator free-form notes (UI cap 512 chars).",
    )

    @validator("experiment_id", "manifest_id")
    def _validate_uuid_shape(cls, v: str) -> str:
        # Lowercase a-z + digits + hyphens only (UUID v4 normalized form).
        # 只允許小寫 a-z + 數字 + 連字號（UUID v4 規範化）。
        v = v.strip().lower()
        for ch in v:
            if not (ch.isdigit() or ('a' <= ch <= 'f') or ch == '-'):
                raise ValueError(
                    "experiment_id / manifest_id must be lowercase UUID v4 hex/hyphen"
                )
        return v


# ═══════════════════════════════════════════════════════════════════════════════
# Auth + Helpers / 認證與輔助
# ═══════════════════════════════════════════════════════════════════════════════


def _require_replay_write(actor: base.AuthenticatedActor) -> None:
    """Mutating-route gate: Operator role + ``replay:write`` scope.
    變更類 route 守門：Operator 角色 + ``replay:write`` scope。

    Mirrors replay_routes._require_replay_write. Fail-closed via
    HTTPException (401/403) re-raised by FastAPI.
    """
    require_scope_and_operator(actor, "replay:write")


def _generate_trace_id() -> str:
    """Generate sortable trace_id: <ts_ms>-<uuid4>.
    生成可排序的 trace_id：<ts_ms>-<uuid4>。

    Format / 格式: '<13-digit ms>-<36-char uuid4>'.
    44 + 13 + 1 = 50 chars total (well under 128 column).
    50 字元（格式：13 位 ms + 連字 + 36 字 uuid4），充裕未滿 128 上限。
    """
    ts_ms = int(time.time() * 1000)
    return f"{ts_ms}-{uuid.uuid4()}"


def _replay_response(
    data: Any,
    *,
    degraded: bool = False,
    reason: Optional[str] = None,
) -> dict[str, Any]:
    """Standard envelope mirroring agents_routes / replay_routes shape.
    標準回應信封，鏡像 agents_routes / replay_routes。
    """
    return {
        "ok": True,
        "data": data,
        "degraded": degraded,
        "reason": reason,
        "is_simulated": False,
        "data_category": "replay_lab_handoff",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Handoff Routes / Handoff 路由
# ═══════════════════════════════════════════════════════════════════════════════


@handoff_router.post("/handoff")
async def post_handoff(
    body: HandoffRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key",
        min_length=1,
        max_length=IDEMPOTENCY_KEY_MAX_LEN,
        description="Required client-supplied idempotency key (UUID v4 recommended).",
    ),
) -> dict[str, Any]:
    """Submit a demo handoff request with typed-confirmation security trio.

    提交 demo handoff 請求（typed-confirmation 安全三劍客）。

    Auth: Operator + ``replay:write`` scope (mirrors POST /run).

    Security trio enforcement order (P6-S13/S14/S15 binding):
      1. Server-side regex on typed_phrase (^HANDOFF [a-z0-9-]{36}$).
         400 + reject_reason='phrase_format_invalid' on miss.
      2. Phrase content match: typed_phrase MUST equal
         'HANDOFF <experiment_id>'. 400 + reject_reason='phrase_mismatch'.
      3. Cooldown query (same actor, last handoff ts within 30s).
         429 + reject_reason='cooldown_in_progress' on hit.
      4. V044 UNIQUE(actor_id, idempotency_key) idempotency lookup.
         200 + cached=true on hit (returns existing trace_id).
      5. Atomic INSERT replay.handoff_requests + emit governance audit row
         under SAME transaction (P6-S15).
      6. Return 200 + cached=false + new trace_id on success.

    安全三劍客執行序：
      1. Server-side regex 驗 typed_phrase。400 + 'phrase_format_invalid'。
      2. Phrase 內容比對 'HANDOFF <experiment_id>'。400 + 'phrase_mismatch'。
      3. Cooldown 查詢（同 actor 最後 handoff ts 在 30s 內）。429。
      4. V044 UNIQUE(actor_id, idempotency_key) idempotency lookup。200 cached=true。
      5. Atomic INSERT replay.handoff_requests + governance audit emit
         在同 transaction 內（P6-S15）。
      6. 成功回 200 + cached=false + 新 trace_id。
    """
    _require_replay_write(actor)
    actor_id = str(actor.actor_id)

    # ── Step 1: Server-side regex (P6-S13). ──
    # ── 步驟 1：server-side regex（P6-S13）。──
    if not HANDOFF_PHRASE_REGEX.match(body.typed_phrase):
        raise HTTPException(
            status_code=400,
            detail={
                "reason_codes": ["phrase_format_invalid"],
                "message": (
                    "typed_phrase must match '^HANDOFF [a-z0-9-]{36}$' "
                    "(V3 §12 #20 server-side regex)"
                ),
            },
        )

    # ── Step 2: Phrase content match (P6-S13). ──
    # ── 步驟 2：phrase 內容比對（P6-S13）。──
    expected_phrase = f"HANDOFF {body.experiment_id}"
    if body.typed_phrase != expected_phrase:
        raise HTTPException(
            status_code=400,
            detail={
                "reason_codes": ["phrase_mismatch"],
                "message": (
                    "typed_phrase substring does not match experiment_id "
                    "(must be 'HANDOFF <experiment_id>')"
                ),
            },
        )

    # ── Step 3+4+5: Atomic transaction (cooldown query + idempotency
    # lookup + INSERT registry + audit emit). Done in sync helper run
    # off the event loop via asyncio.to_thread (H-4 pattern).
    # ── 步驟 3+4+5：原子 transaction（cooldown + idempotency + 註冊 INSERT
    # + audit emit）。同步 helper 由 asyncio.to_thread off the loop。──
    def _do_handoff_pg() -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        """Sync helper for handoff transaction; returns (result, err_or_none).
        handoff transaction 的同步 helper；回 (result, err_or_none)。
        """
        with get_pg_conn() as conn:
            if conn is None:
                return None, "pg_unavailable"
            try:
                cur = conn.cursor()
                cur.execute(
                    "SET LOCAL statement_timeout = %s",
                    (_STATEMENT_TIMEOUT_MS,),
                )

                # Schema-absent graceful: if V044 missing, surface degraded.
                # Schema-absent graceful：V044 缺 → degraded。
                cur.execute(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'replay' "
                    "AND table_name = 'handoff_requests' LIMIT 1;"
                )
                if cur.fetchone() is None:
                    return None, "v044_absent"

                # ── Step 4 first (faster short-circuit): idempotency lookup. ──
                # ── 先做步驟 4（更快短路）：idempotency lookup。──
                cur.execute(
                    """
                    SELECT trace_id, result, ts, reject_reason
                      FROM replay.handoff_requests
                     WHERE actor_id = %s
                       AND idempotency_key = %s
                     LIMIT 1;
                    """,
                    (actor_id, idempotency_key),
                )
                cached_row = cur.fetchone()
                if cached_row is not None:
                    cached_trace_id, cached_result, cached_ts, cached_reject = (
                        cached_row[0], cached_row[1], cached_row[2], cached_row[3]
                    )
                    return {
                        "trace_id": cached_trace_id,
                        "result": cached_result,
                        "cached": True,
                        "reject_reason": cached_reject,
                        "ts_iso": cached_ts.isoformat() if cached_ts else None,
                    }, None

                # ── Step 3: cooldown query (same actor only). ──
                # ── 步驟 3：cooldown 查詢（僅同 actor）。──
                cur.execute(
                    """
                    SELECT EXTRACT(EPOCH FROM (NOW() - ts)) AS seconds_since
                      FROM replay.handoff_requests
                     WHERE actor_id = %s
                     ORDER BY ts DESC
                     LIMIT 1;
                    """,
                    (actor_id,),
                )
                last_row = cur.fetchone()
                if last_row is not None and last_row[0] is not None:
                    seconds_since = float(last_row[0])
                    if seconds_since < COOLDOWN_SECONDS:
                        # Cooldown hit: 429 + persist a 'rejected' row
                        # (operator forensic trail per UX §6) + audit emit.
                        # Cooldown 命中：429 + 寫 rejected row + audit。
                        trace_id_local = _generate_trace_id()
                        handoff_uuid = uuid.uuid4()
                        phrase_hash_local = _hash_typed_phrase(body.typed_phrase)
                        cur.execute(
                            """
                            INSERT INTO replay.handoff_requests (
                                handoff_id, actor_id, experiment_id,
                                manifest_id, idempotency_key,
                                typed_phrase_hash, operator_notes,
                                result, trace_id, cached, reject_reason
                            ) VALUES (
                                %s, %s, %s::uuid,
                                %s::uuid, %s,
                                %s, %s,
                                'rejected', %s, FALSE, 'cooldown_in_progress'
                            );
                            """,
                            (
                                str(handoff_uuid), actor_id, body.experiment_id,
                                body.manifest_id, idempotency_key,
                                phrase_hash_local, body.operator_notes,
                                trace_id_local,
                            ),
                        )

                        audit_req = _HandoffAuditRequest(
                            experiment_id=body.experiment_id,
                            manifest_id=body.manifest_id,
                            typed_phrase=body.typed_phrase,
                            idempotency_key=idempotency_key,
                            operator_notes=body.operator_notes,
                        )
                        _emit_handoff_audit(
                            actor_id=actor_id,
                            request=audit_req,
                            result="rejected",
                            trace_id=trace_id_local,
                            reject_reason="cooldown_in_progress",
                            cached=False,
                            cursor=cur,
                        )

                        conn.commit()
                        return None, (
                            f"cooldown_in_progress:{int(COOLDOWN_SECONDS - seconds_since)}"
                        )

                # ── Step 5: success path — INSERT registry + audit emit. ──
                # ── 步驟 5：成功路徑 — INSERT 註冊 + audit。──
                trace_id_local = _generate_trace_id()
                handoff_uuid = uuid.uuid4()
                phrase_hash_local = _hash_typed_phrase(body.typed_phrase)
                cur.execute(
                    """
                    INSERT INTO replay.handoff_requests (
                        handoff_id, actor_id, experiment_id,
                        manifest_id, idempotency_key,
                        typed_phrase_hash, operator_notes,
                        result, trace_id, cached, reject_reason
                    ) VALUES (
                        %s, %s, %s::uuid,
                        %s::uuid, %s,
                        %s, %s,
                        'success', %s, FALSE, NULL
                    );
                    """,
                    (
                        str(handoff_uuid), actor_id, body.experiment_id,
                        body.manifest_id, idempotency_key,
                        phrase_hash_local, body.operator_notes,
                        trace_id_local,
                    ),
                )

                # Audit emit under SAME cursor (P6-S15 atomic).
                # Audit emit 在同 cursor（P6-S15 原子）。
                audit_req = _HandoffAuditRequest(
                    experiment_id=body.experiment_id,
                    manifest_id=body.manifest_id,
                    typed_phrase=body.typed_phrase,
                    idempotency_key=idempotency_key,
                    operator_notes=body.operator_notes,
                )
                audit_ok = _emit_handoff_audit(
                    actor_id=actor_id,
                    request=audit_req,
                    result="success",
                    trace_id=trace_id_local,
                    reject_reason=None,
                    cached=False,
                    cursor=cur,
                )

                if not audit_ok:
                    # Per DOC-08 §12 fail-closed: audit failure ⇒ rollback.
                    # DOC-08 §12 fail-closed：audit 失敗 → rollback。
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    return None, "audit_emit_failed"

                conn.commit()
                return {
                    "trace_id": trace_id_local,
                    "result": "success",
                    "cached": False,
                    "reject_reason": None,
                    "ts_iso": datetime.now(timezone.utc).isoformat(),
                }, None
            except Exception as exc:
                logger.warning(
                    "handoff_routes /handoff PG path exception: %s", exc
                )
                try:
                    conn.rollback()
                except Exception:
                    pass
                # V044 UNIQUE(actor_id, idempotency_key) ⇒ unique_violation
                # if race; client should retry idempotency lookup path.
                # V044 UNIQUE 衝突若 race：client 應重試 idempotency lookup。
                err_name = type(exc).__name__
                if "UniqueViolation" in err_name or "IntegrityError" in err_name:
                    return None, "idempotency_race"
                return None, f"pg_error:{err_name}"

    result, pg_err = await asyncio.to_thread(_do_handoff_pg)

    if result is not None and pg_err is None:
        # Success or cached idempotency hit.
        # 成功或 cached idempotency 命中。
        return _replay_response({
            "trace_id": result["trace_id"],
            "result": result["result"],
            "cached": result["cached"],
            "reject_reason": result.get("reject_reason"),
            "experiment_id": body.experiment_id,
            "manifest_id": body.manifest_id,
            "actor_id": actor_id,
            "ts_iso": result.get("ts_iso"),
        })

    if pg_err and pg_err.startswith("cooldown_in_progress:"):
        try:
            remaining = int(pg_err.split(":", 1)[1])
        except (ValueError, IndexError):
            remaining = COOLDOWN_SECONDS
        raise HTTPException(
            status_code=429,
            detail={
                "reason_codes": ["cooldown_in_progress"],
                "message": (
                    f"actor '{actor_id}' must wait {remaining}s before "
                    f"another handoff (V3 §11 P6 cooldown ≥{COOLDOWN_SECONDS}s)"
                ),
                "remaining_seconds": remaining,
            },
        )

    if pg_err == "idempotency_race":
        # UNIQUE race: re-query idempotency to return cached row.
        # UNIQUE race：重查 idempotency 回 cached row。
        def _requery_idempotency() -> Optional[dict[str, Any]]:
            with get_pg_conn() as conn:
                if conn is None:
                    return None
                try:
                    cur = conn.cursor()
                    cur.execute(
                        "SET LOCAL statement_timeout = %s",
                        (_STATEMENT_TIMEOUT_MS,),
                    )
                    cur.execute(
                        """
                        SELECT trace_id, result, ts, reject_reason
                          FROM replay.handoff_requests
                         WHERE actor_id = %s AND idempotency_key = %s
                         LIMIT 1;
                        """,
                        (actor_id, idempotency_key),
                    )
                    row = cur.fetchone()
                    if row is None:
                        return None
                    return {
                        "trace_id": row[0],
                        "result": row[1],
                        "cached": True,
                        "reject_reason": row[3],
                        "ts_iso": row[2].isoformat() if row[2] else None,
                    }
                except Exception:
                    return None

        cached_row = await asyncio.to_thread(_requery_idempotency)
        if cached_row is not None:
            return _replay_response({
                "trace_id": cached_row["trace_id"],
                "result": cached_row["result"],
                "cached": True,
                "reject_reason": cached_row.get("reject_reason"),
                "experiment_id": body.experiment_id,
                "manifest_id": body.manifest_id,
                "actor_id": actor_id,
                "ts_iso": cached_row.get("ts_iso"),
            })
        # Re-query failed too; surface 500.
        # 重查也失敗；500。
        raise HTTPException(
            status_code=500,
            detail={
                "reason_codes": ["idempotency_race_unrecoverable"],
                "message": "UNIQUE race + re-query both failed",
            },
        )

    if pg_err == "audit_emit_failed":
        raise HTTPException(
            status_code=500,
            detail={
                "reason_codes": ["audit_emit_failed"],
                "message": (
                    "DOC-08 §12 fail-closed: handoff registry INSERT rolled "
                    "back because audit emit failed"
                ),
            },
        )

    if pg_err in ("pg_unavailable", "v044_absent"):
        # Degraded posture per V3 §12 #22 mirror.
        # Degraded 信封（V3 §12 #22 鏡像）。
        return _replay_response(
            data={
                "trace_id": None,
                "result": None,
                "cached": False,
                "reject_reason": "degraded",
                "experiment_id": body.experiment_id,
                "manifest_id": body.manifest_id,
                "actor_id": actor_id,
                "wiring_status": "degraded",
            },
            degraded=True,
            reason=pg_err,
        )

    # Hard failure.
    # 硬失敗。
    raise HTTPException(
        status_code=503,
        detail={
            "reason_codes": ["handoff_pg_error"],
            "message": f"handoff transaction failed: {pg_err}",
        },
    )


@handoff_router.get("/handoff/recent")
async def get_handoff_recent(
    n: int = Query(
        default=RECENT_N_DEFAULT,
        ge=1,
        le=RECENT_N_MAX,
        description="Number of recent handoff records (1-50, default 5).",
    ),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """Get the most recent N handoff records (footer for H3 frontend).
    取得最近 N 筆 handoff 紀錄（H3 前端 footer 用）。

    Read-only; authentication required (no scope beyond auth).

    Response includes truncated actor_id for forensic privacy
    (FA security requirement: full actor_id not exposed in footer).
    Operator-mode actors see their own full actor_id but other actors'
    truncated to last 4 chars after a hash prefix.

    回應包含 truncated actor_id（FA 安全要求：footer 不暴露完整 actor_id）。
    Operator 看自己的完整 id；其他 actor 顯示 hash prefix + last 4 chars。
    """
    actor_id = str(actor.actor_id)

    def _do_recent_pg() -> Tuple[list[dict[str, Any]], Optional[str]]:
        with get_pg_conn() as conn:
            if conn is None:
                return [], "pg_unavailable"
            try:
                cur = conn.cursor()
                cur.execute(
                    "SET LOCAL statement_timeout = %s",
                    (_STATEMENT_TIMEOUT_MS,),
                )

                # Schema-absent graceful.
                # Schema-absent graceful。
                cur.execute(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'replay' "
                    "AND table_name = 'handoff_requests' LIMIT 1;"
                )
                if cur.fetchone() is None:
                    return [], "v044_absent"

                cur.execute(
                    """
                    SELECT actor_id, ts, result, trace_id, cached,
                           reject_reason
                      FROM replay.handoff_requests
                     ORDER BY ts DESC
                     LIMIT %s;
                    """,
                    (n,),
                )
                rows = cur.fetchall()
                items: list[dict[str, Any]] = []
                for row in rows:
                    row_actor = str(row[0])
                    # Truncate other actors for forensic privacy; show
                    # caller's own full id for self-identification.
                    # 截短其他 actor；caller 自己看完整 id。
                    if row_actor == actor_id:
                        actor_display = row_actor
                    else:
                        # Last 4 chars + prefix of length 4 from hash.
                        # last 4 chars + 來自 hash 的 4 字 prefix。
                        if len(row_actor) >= 4:
                            actor_display = (
                                f"...{row_actor[-4:]}"
                            )
                        else:
                            actor_display = "***"
                    items.append({
                        "actor_id_display": actor_display,
                        "ts_iso": row[1].isoformat() if row[1] else None,
                        "result": row[2],
                        "trace_id": row[3],
                        "cached": row[4],
                        "reject_reason": row[5],
                    })
                return items, None
            except Exception as exc:
                logger.warning(
                    "handoff_routes /handoff/recent PG path exception: %s", exc
                )
                return [], f"pg_error:{type(exc).__name__}"

    items, pg_err = await asyncio.to_thread(_do_recent_pg)

    if pg_err is None:
        return _replay_response({
            "items": items,
            "count": len(items),
            "n_requested": n,
            "wiring_status": "pg_path_active",
        })

    # Degraded posture per V3 §12 #22 mirror.
    # Degraded 信封（V3 §12 #22 鏡像）。
    return _replay_response(
        data={
            "items": [],
            "count": 0,
            "n_requested": n,
            "wiring_status": "degraded",
        },
        degraded=True,
        reason=pg_err,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Module export / 模組匯出
# ═══════════════════════════════════════════════════════════════════════════════


__all__ = [
    "COOLDOWN_SECONDS",
    "HANDOFF_PHRASE_REGEX",
    "HandoffRequest",
    "handoff_router",
]
