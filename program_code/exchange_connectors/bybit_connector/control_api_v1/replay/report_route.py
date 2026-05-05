"""REF-20 Sprint A R2 round 2 fix H-3 — /report endpoint logic extraction.
REF-20 Sprint A R2 round 2 fix H-3 — /report endpoint 邏輯抽出。

MODULE_NOTE (EN):
    Sprint A R2 round 2 (2026-05-04) extraction. Owns the
    ``GET /api/v1/replay/report/{experiment_id}`` business logic so the
    thin handler in ``app/replay_routes.py`` keeps under the CLAUDE.md
    §九 1500 LOC hard cap.

    Why this module exists (E2 review H-3):
      Round 1 ``/report`` handler used ``uuid.uuid5(NAMESPACE, experiment_id)``
      to derive ``manifest_uuid`` then SELECT ``replay.report_artifacts``
      WHERE manifest_id = derived. After R2-T2, ``run_state.manifest_id``
      is the REAL V049 experiment_id (no UUID5 derivation). Result:
      derived UUID != real UUID → ``/report`` always returned 0 row for
      experiments registered post-R2-T2 (cross-route inconsistency).

    R2 round 2 fix H-3:
      ``/report`` now resolves ``experiment_id`` text via
      ``replay.route_helpers.lookup_registered_experiment_id`` — same
      function ``/run`` uses (R2-T2 invariant) — so both routes share
      a single source of truth for the V049 → V045/V046 FK lookup.
      0 row in V049 → 404 ``replay_experiment_not_found``.

    What this module does:
      - ``fetch_report_for_experiment(experiment_id, actor, async_safe_pg_select_fn,
        artifact_path_within_allowlist_fn, audit_emit_fn) -> dict``
        coroutine that:
          1. Validates ``experiment_id`` shape (alphanumeric + '-_').
          2. Looks up V049 ``replay.experiments`` row to get real
             manifest UUID (via separate PG xact, FOR SHARE inside).
          3. Builds IDOR-aware SELECT for ``replay.report_artifacts``
             via ``security_guards.build_report_idor_sql``.
          4. Reads each artifact JSON from disk (path-traversal guarded).
          5. Emits audit stub on traversal block / admin bypass.

    What this module does NOT do (out of scope):
      - PG xact lifecycle (caller-owned, mirrored from /run path).
      - Pydantic request model (path param only).
      - V045 / V046 schema validation (V3 §3 binding outside R2 scope).

MODULE_NOTE (中):
    Sprint A R2 round 2（2026-05-04）抽出。擁有
    ``GET /api/v1/replay/report/{experiment_id}`` 業務邏輯，使
    ``app/replay_routes.py`` 薄 handler 守住 CLAUDE.md §九 1500 LOC 硬上限。

    本 module 為何存在（E2 review H-3）：
      Round 1 ``/report`` handler 用 ``uuid.uuid5(NAMESPACE, experiment_id)``
      衍生 ``manifest_uuid`` 然後 SELECT。R2-T2 後 ``run_state.manifest_id``
      已是 *真* V049 experiment_id，derived ≠ real → ``/report`` 對 R2-T2
      後註冊的 experiment 永遠 0 row（跨 route 不一致）。

    R2 round 2 fix H-3：
      ``/report`` 改用 ``replay.route_helpers.lookup_registered_experiment_id``
      取真 manifest UUID（與 ``/run`` 同函式 R2-T2 invariant），兩 route
      共用 V049 → V045/V046 FK lookup 的 single source of truth。V049 0 row
      → 404 ``replay_experiment_not_found``。

    本 module 做的事：
      - ``fetch_report_for_experiment(...)`` coroutine 實作 5 步驟。

    本 module 不做（範圍外）：
      - PG xact 生命周期（caller 持，鏡像 /run path）。
      - Pydantic 請求模型（僅 path param）。
      - V045 / V046 schema 驗證（V3 §3 binding 範圍外）。

SPEC: docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md §6.R2 round 2 H-3
Reviews: srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-04--ref20_sprint_a_r2_e2_review.md §H-3
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, Tuple

logger = logging.getLogger(__name__)


# ─── Constants / 常數 ─────────────────────────────────────────────────

# Maximum length of experiment_id path parameter.
# experiment_id path 參數最大長度。
MAX_EXPERIMENT_ID_LEN = 128

# Maximum bytes read per artifact JSON (mirror of /report inline value pre-extract).
# 每個 artifact JSON 最大讀取 bytes（與抽前 inline 值一致）。
MAX_ARTIFACT_PAYLOAD_BYTES = 256 * 1024


# ─── Validation helper / 驗證輔助 ──────────────────────────────────────


def validate_experiment_id_shape(experiment_id: str) -> Optional[str]:
    """Validate ``experiment_id`` shape: alphanumeric + '-_', max 128 chars.
    驗 ``experiment_id`` 形狀：字母數字 + '-_'，最長 128。

    Returns / 回傳:
        ``None`` on valid; error reason string on invalid (caller maps
        to 400 ``replay_invalid_experiment_id``).
    """
    if not experiment_id:
        return "empty_experiment_id"
    if len(experiment_id) > MAX_EXPERIMENT_ID_LEN:
        return f"experiment_id_too_long:{len(experiment_id)}"
    for ch in experiment_id:
        if not (ch.isalnum() or ch in "-_"):
            return f"experiment_id_invalid_char:{ch!r}"
    return None


# ─── Manifest lookup (cross-route consistency with /run) ───────────────


def _lookup_manifest_uuid_sync(
    get_pg_conn_fn: Callable[..., Any],
    lookup_registered_experiment_id_fn: Callable[[Any, str], Optional[str]],
    experiment_id: str,
    statement_timeout_ms: int,
    *,
    expected_actor_id: Optional[str] = None,
    admin_bypass: bool = False,
) -> Tuple[Optional[str], Optional[str]]:
    """Open a short PG xact, run lookup_registered_experiment_id, close.
    開短 PG xact 跑 lookup_registered_experiment_id，結束。

    REF-20 Sprint A R2 round 2 fix H-3 (cross-route consistency):
    ``/report`` shares the same V049 lookup helper as ``/run`` (R2-T2
    invariant) so both routes resolve experiment_id text → real V049
    UUID via a single source of truth.
    REF-20 Sprint A R2 round 2 fix H-3（跨 route 一致）：``/report`` 與
    ``/run``（R2-T2 invariant）共用同 V049 lookup helper。

    REF-20 Sprint A R2 round 3 fix M-IDOR-ENUM (cross-actor enumeration):
    Round 2 H-3 introduced an enumeration oracle — ``/report`` returned
    404 for V049 0 row vs 200-with-empty-artifacts for cross-actor row
    that exists, letting authenticated callers probe other actors'
    experiment_id space. Round 3 closes the oracle: when
    ``expected_actor_id`` is provided and the V049 row exists with
    ``created_by != expected_actor_id`` (and the caller has no admin
    bypass), this collapses to the same ``not_registered`` reason as
    a non-existent row → caller surfaces 404 + ``replay_experiment_not_found``.
    The 404 unification mirrors GitHub's repo-private/repo-not-found
    pattern.
    REF-20 Sprint A R2 round 3 fix M-IDOR-ENUM（跨 actor 列舉預言機）：
    Round 2 H-3 引入了枚舉預言機 — ``/report`` 對 V049 0 row 返 404，
    對跨 actor 已存在 row 返 200 空 artifact，讓認證後 caller 可探測
    他人 experiment_id 空間。Round 3 收斂：``expected_actor_id`` 提供
    且 V049 row 的 ``created_by != expected_actor_id``（且 caller 無
    admin bypass）→ 收斂為同 ``not_registered`` reason → caller 返 404
    + ``replay_experiment_not_found``。

    Args:
        expected_actor_id: caller actor_id; non-None enables the IDOR
            enum-oracle close. None retains legacy behaviour (used by
            tests / non-/report callers; current production caller is
            only ``/report`` so it always passes a non-None value).
        admin_bypass: True iff caller holds ``replay:read:any``; allows
            cross-actor row visibility for incident investigation
            (mirrors ``build_report_idor_sql`` admin branch).

    Returns / 回傳:
        (manifest_uuid_text, None) on found and (own row OR admin);
        (None, reason) on not-found / pg outage / cross-actor non-admin.
        reason ∈ {"not_registered", "pg_unavailable", "pg_error:<Exc>"}.
        Cross-actor non-admin maps to ``"not_registered"`` (NOT a
        distinct reason) so HTTP layer cannot distinguish.
    """
    with get_pg_conn_fn() as conn:
        if conn is None:
            return None, "pg_unavailable"
        try:
            cur = conn.cursor()
            cur.execute("SET LOCAL statement_timeout = %s", (statement_timeout_ms,))
            manifest_uuid = lookup_registered_experiment_id_fn(cur, experiment_id)
            if manifest_uuid is None:
                # Read-only — rollback to release any FOR SHARE row lock.
                # 只讀 — rollback 釋放 FOR SHARE row lock。
                conn.rollback()
                return None, "not_registered"

            # Round 3 M-IDOR-ENUM: when caller is non-admin and an
            # ``expected_actor_id`` was supplied, additionally check
            # ``created_by`` to collapse cross-actor existence into the
            # same ``not_registered`` reason. The lookup helper already
            # holds FOR SHARE on the row, so this second SELECT in the
            # same xact reads the same locked tuple.
            # Round 3 M-IDOR-ENUM：caller 非 admin 且 expected_actor_id
            # 提供時，加查 ``created_by`` 把跨 actor 存在收斂為同
            # ``not_registered`` reason。同 xact 第二次 SELECT 讀到的
            # 是同一被 FOR SHARE 鎖住的 tuple。
            if expected_actor_id is not None and not admin_bypass:
                cur.execute(
                    "SELECT created_by FROM replay.experiments "
                    "WHERE experiment_id = %s::uuid;",
                    (manifest_uuid,),
                )
                row = cur.fetchone()
                conn.rollback()
                if row is None or row[0] != expected_actor_id:
                    return None, "not_registered"
                return manifest_uuid, None

            conn.rollback()
            return manifest_uuid, None
        except Exception as exc:  # noqa: BLE001 — fail-closed PG envelope
            logger.warning("_lookup_manifest_uuid_sync: %s", exc)
            try:
                conn.rollback()
            except Exception:
                pass
            return None, f"pg_error:{type(exc).__name__}"


async def _lookup_manifest_uuid(
    get_pg_conn_fn: Callable[..., Any],
    lookup_registered_experiment_id_fn: Callable[[Any, str], Optional[str]],
    experiment_id: str,
    statement_timeout_ms: int,
    *,
    expected_actor_id: Optional[str] = None,
    admin_bypass: bool = False,
) -> Tuple[Optional[str], Optional[str]]:
    """Async wrapper around _lookup_manifest_uuid_sync.
    _lookup_manifest_uuid_sync 的 async 包裝。

    Round 3 M-IDOR-ENUM: forwards ``expected_actor_id`` + ``admin_bypass``
    so the cross-actor enumeration oracle is closed at lookup time.
    Round 3 M-IDOR-ENUM：轉送 ``expected_actor_id`` + ``admin_bypass``，
    使跨 actor enum 預言機在 lookup 階段就被堵。
    """
    return await asyncio.to_thread(
        _lookup_manifest_uuid_sync,
        get_pg_conn_fn,
        lookup_registered_experiment_id_fn,
        experiment_id,
        statement_timeout_ms,
        expected_actor_id=expected_actor_id,
        admin_bypass=admin_bypass,
    )


# ─── Artifact payload reader / artifact payload 讀取 ───────────────────


def _read_artifact_with_traversal_guard(
    artifact_row: tuple,
    artifact_path_within_allowlist_fn: Callable[[Path], Tuple[bool, Optional[str]]],
    check_artifact_path_within_allowlist_fn: Callable[
        [Path, Callable[[Path], Tuple[bool, Optional[str]]]], Tuple[bool, Optional[str]]
    ],
) -> Tuple[dict[str, Any], Optional[str]]:
    """Read one V046 artifact row with path-traversal allowlist guard.
    讀單個 V046 artifact row，含 path-traversal allowlist 守門。

    Returns / 回傳:
        (artifact_dict, traversal_blocked_path_or_None).
    """
    artifact = {
        "artifact_id": artifact_row[0],
        "artifact_type": artifact_row[1],
        "artifact_path": artifact_row[2],
        "byte_size": artifact_row[3],
        "is_mock": artifact_row[4],
        "created_at_ms": int(artifact_row[5]) if artifact_row[5] is not None else None,
    }
    traversal_blocked: Optional[str] = None
    try:
        artifact_path = Path(artifact_row[2])
        within, traversal_err = check_artifact_path_within_allowlist_fn(
            artifact_path, artifact_path_within_allowlist_fn,
        )
        if not within:
            artifact["payload_read_error"] = (
                f"path_traversal_blocked:{traversal_err}"
            )
            traversal_blocked = str(artifact_row[2])[:120]
        elif (
            artifact_path.is_file()
            and (artifact_row[3] or 0) <= MAX_ARTIFACT_PAYLOAD_BYTES
        ):
            with open(artifact_path, "rb") as f:
                payload_bytes = f.read(MAX_ARTIFACT_PAYLOAD_BYTES)
            artifact["payload"] = json.loads(payload_bytes.decode("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        artifact["payload_read_error"] = (
            f"{type(exc).__name__}: {str(exc)[:80]}"
        )
    return artifact, traversal_blocked


def _overlay_artifact_payload_execution_confidence(
    artifact: dict[str, Any],
    execution_confidence: Optional[str],
) -> None:
    """Overlay V049 execution_confidence onto loaded report payloads."""
    if not execution_confidence:
        return
    payload = artifact.get("payload")
    if not isinstance(payload, dict):
        return
    payload["execution_confidence"] = execution_confidence
    result = payload.get("result")
    if isinstance(result, dict):
        result["execution_confidence"] = execution_confidence


# ─── Public coroutine: fetch_report_for_experiment ─────────────────────


async def fetch_report_for_experiment(
    *,
    experiment_id: str,
    actor: Any,
    get_pg_conn_fn: Callable[..., Any],
    lookup_registered_experiment_id_fn: Callable[[Any, str], Optional[str]],
    actor_can_read_any_fn: Callable[[Any], bool],
    build_report_idor_sql_fn: Callable[[str, str, bool], Tuple[str, tuple]],
    async_safe_pg_select_fn: Callable[
        [str, tuple], Awaitable[Tuple[list, Optional[str]]]
    ],
    artifact_path_within_allowlist_fn: Callable[[Path], Tuple[bool, Optional[str]]],
    check_artifact_path_within_allowlist_fn: Callable[
        [Path, Callable[[Path], Tuple[bool, Optional[str]]]],
        Tuple[bool, Optional[str]],
    ],
    audit_emit_fn: Callable[..., None],
    replay_response_envelope_fn: Callable[..., dict[str, Any]],
    statement_timeout_ms: int = 2_000,
) -> Tuple[Optional[dict[str, Any]], Optional[Tuple[int, dict[str, Any]]]]:
    """Run the full GET /report/{experiment_id} flow (R2 round 2 H-3).
    執行完整 GET /report/{experiment_id} 流程（R2 round 2 H-3）。

    Caller is the thin route handler in ``app/replay_routes.py`` which
    only does the auth ``Depends`` + this call + raise ``HTTPException``
    on the (status_code, detail) tuple this returns.

    Args:
        experiment_id: path parameter (V049 experiment_id text).
        actor: ``base.AuthenticatedActor`` from ``Depends(current_actor)``.
        get_pg_conn_fn: ``app.db_pool.get_pg_conn`` context-manager.
        lookup_registered_experiment_id_fn: ``replay.route_helpers``
            same-name (R2-T2 single source of truth for V049 lookup).
        actor_can_read_any_fn: ``app.replay_routes._actor_can_read_any_replay_report``
            (Track C P0-5a admin scope check).
        build_report_idor_sql_fn: ``replay.security_guards.build_report_idor_sql``
            (Track C P0-5a IDOR-aware SQL builder).
        async_safe_pg_select_fn: ``app.replay_routes._async_safe_pg_select``.
        artifact_path_within_allowlist_fn: ``replay.route_helpers
            .artifact_path_within_allowlist`` (Track C P0-5b root check).
        check_artifact_path_within_allowlist_fn:
            ``replay.security_guards.check_artifact_path_within_allowlist``
            (Track C P0-5b wrapper).
        audit_emit_fn: ``replay.route_helpers.emit_replay_audit_stub``.
        replay_response_envelope_fn: ``replay.route_helpers.replay_response_envelope``.
        statement_timeout_ms: per-stmt PG timeout (mirror /run path).

    Returns / 回傳:
        (response_dict, None) on success — caller returns directly;
        (None, (status, detail)) on error — caller raises HTTPException.
    """
    # Step 1: validate experiment_id shape.
    # 步驟 1：驗 experiment_id 形狀。
    shape_err = validate_experiment_id_shape(experiment_id)
    if shape_err is not None:
        return None, (400, {
            "reason_codes": ["replay_invalid_experiment_id"],
            "message": (
                "experiment_id may only contain alphanumeric / '-' / '_' "
                f"and be ≤ {MAX_EXPERIMENT_ID_LEN} chars; reason={shape_err}"
            ),
        })

    actor_id = str(actor.actor_id)

    # Round 3 M-IDOR-ENUM: precompute admin bypass so the V049 lookup can
    # close the cross-actor enumeration oracle at lookup time. The admin
    # bypass is also re-used in step 3 for V046 IDOR SELECT — single
    # authority on which actors can read across boundaries.
    # Round 3 M-IDOR-ENUM：先算 admin bypass，使 V049 lookup 階段就堵跨
    # actor 枚舉預言機。同值在步驟 3 重用為 V046 IDOR SELECT 的 admin
    # bypass — 單一跨界讀取權威。
    idor_admin_bypass = actor_can_read_any_fn(actor)

    # Step 2: cross-route lookup — resolve experiment_id text to real V049 UUID.
    # 步驟 2：跨 route lookup — 把 experiment_id text 解析為真 V049 UUID。
    # R2 round 2 fix H-3: was UUID5 derivation (broken since R2-T2); now
    # uses same helper as /run for invariant alignment.
    # R2 round 2 fix H-3：原 UUID5 derivation（R2-T2 起壞）→ 改用 /run 同
    # helper 對齊不變式。
    # R2 round 3 fix M-IDOR-ENUM: pass actor_id + admin_bypass so cross-actor
    # row existence collapses to the same ``not_registered`` reason as
    # missing row → 404 + ``replay_experiment_not_found`` (no oracle).
    # R2 round 3 fix M-IDOR-ENUM：傳 actor_id + admin_bypass，讓跨 actor
    # 已存在 row 收斂為同 ``not_registered`` reason → 404（去 oracle）。
    manifest_uuid, lookup_err = await _lookup_manifest_uuid(
        get_pg_conn_fn,
        lookup_registered_experiment_id_fn,
        experiment_id,
        statement_timeout_ms,
        expected_actor_id=actor_id,
        admin_bypass=idor_admin_bypass,
    )
    if lookup_err == "not_registered":
        return None, (404, {
            "reason_codes": ["replay_experiment_not_found"],
            "message": (
                f"experiment_id '{experiment_id}' has no row in "
                "replay.experiments (V049); call POST "
                "/api/v1/replay/experiments/register first"
            ),
        })
    if lookup_err is not None:
        # PG outage / pg_error → 200 + degraded (V3 §12 #22 mirror).
        # PG outage / pg_error → 200 + degraded（V3 §12 #22 鏡像）。
        return replay_response_envelope_fn(
            data={
                "experiment_id": experiment_id,
                "manifest_id": None,
                "artifacts": [],
                "wiring_status": "degraded",
            },
            degraded=True,
            reason=lookup_err,
        ), None

    experiment_confidence: Optional[str] = None
    confidence_rows, confidence_err = await async_safe_pg_select_fn(
        """
        SELECT execution_confidence
          FROM replay.experiments
         WHERE experiment_id = %s::uuid
         LIMIT 1;
        """,
        (manifest_uuid,),
    )
    if confidence_err is None and confidence_rows:
        first_confidence_row = confidence_rows[0]
        if len(first_confidence_row) == 1:
            value = first_confidence_row[0]
            if value in ("none", "limited", "calibrated"):
                experiment_confidence = str(value)

    # Step 3: IDOR-aware SELECT against V046.report_artifacts.
    # 步驟 3：對 V046.report_artifacts 做 IDOR-aware SELECT。
    # ``idor_admin_bypass`` already resolved before step 2 for IDOR enum
    # oracle close (round 3 M-IDOR-ENUM); reused here for V046 IDOR.
    # ``idor_admin_bypass`` 已在步驟 2 前解析完畢（round 3 M-IDOR-ENUM）。
    sql, params = build_report_idor_sql_fn(
        manifest_uuid, actor_id, idor_admin_bypass,
    )
    rows, select_err = await async_safe_pg_select_fn(sql, params)

    if select_err is not None:
        # PG outage / V046 absent → 200 + degraded (V3 §12 #22 mirror).
        # PG outage / V046 缺 → 200 + degraded（V3 §12 #22 鏡像）。
        return replay_response_envelope_fn(
            data={
                "experiment_id": experiment_id,
                "manifest_id": manifest_uuid,
                "artifacts": [],
                "wiring_status": "degraded",
            },
            degraded=True,
            reason=select_err,
        ), None

    # Step 4: read each artifact JSON from disk with allowlist guard.
    # 步驟 4：讀每個 artifact JSON，含 allowlist 守門。
    artifacts: list[dict[str, Any]] = []
    traversal_blocked_paths: list[str] = []
    for row in rows:
        artifact, blocked = _read_artifact_with_traversal_guard(
            row,
            artifact_path_within_allowlist_fn,
            check_artifact_path_within_allowlist_fn,
        )
        _overlay_artifact_payload_execution_confidence(
            artifact, experiment_confidence,
        )
        if blocked is not None:
            traversal_blocked_paths.append(blocked)
        artifacts.append(artifact)

    # Step 5: audit stubs — traversal block + admin bypass.
    # 步驟 5：audit stub — traversal block + admin bypass。
    if traversal_blocked_paths:
        audit_emit_fn(
            event_type="replay_artifact_path_traversal_blocked",
            actor_id=actor_id,
            experiment_id=experiment_id,
            manifest_hash=None,
            decision="blocked_path_traversal",
            extra_payload={
                "blocked_count": len(traversal_blocked_paths),
                "samples": traversal_blocked_paths[:3],
            },
        )
    if idor_admin_bypass:
        audit_emit_fn(
            event_type="replay_idor_admin_bypass",
            actor_id=actor_id,
            experiment_id=experiment_id,
            manifest_hash=None,
            decision="admin_bypass_used",
            extra_payload={
                "scope": "replay:read:any",
                "rows_returned": len(rows),
            },
        )

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

    return replay_response_envelope_fn({
        "experiment_id": experiment_id,
        "manifest_id": manifest_uuid,
        "run": run_summary,
        "execution_confidence": experiment_confidence,
        "artifacts": artifacts,
        "artifact_count": len(artifacts),
        "wiring_status": "pg_path_active",
    }), None


__all__ = [
    "fetch_report_for_experiment",
    "validate_experiment_id_shape",
    "MAX_EXPERIMENT_ID_LEN",
    "MAX_ARTIFACT_PAYLOAD_BYTES",
]
