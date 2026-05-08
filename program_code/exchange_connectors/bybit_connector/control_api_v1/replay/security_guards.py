"""REF-20 Sprint 1 Track C — security guard module for /replay/* endpoints.
REF-20 Sprint 1 Track C — /replay/* 端點安全守門模組。

MODULE_NOTE (EN):
    Sprint 1 Track C E2 retrofit (CLAUDE.md §九 1500 LOC hard cap enforcement).
    Replay routes' P0-2 (TEST_KEY env var bypass), P0-4 (SIGTERM cmdline cert),
    and P0-5 (IDOR cross-actor + path traversal) security fixes were inline in
    ``replay_routes.py`` after Sprint 1 Track C IMPL pushed final LOC to 1603
    (103 over the 1500 hard cap). PM rejected the §九 baseline exception
    request; this module extracts the security guard helpers + endpoint-body
    sub-routines so ``replay_routes.py`` drops back under the cap while the
    endpoint @router decorators remain in their original module.

    Each helper is *pure* (no FastAPI / pydantic imports) so unit tests can
    exercise the security logic in isolation. Helpers raise ``HTTPException``
    when the route handler must return non-200; otherwise they return
    structured tuples that the route handler converts to ``_replay_response``
    envelopes.

    Public API:

      ``perform_p0_2_boot_guard()``
          Module-init invariant for ``replay_routes.py`` — raise
          ``RuntimeError`` if ``OPENCLAW_RELEASE_PROFILE='live'`` and
          ``OPENCLAW_REPLAY_VERIFY_TEST_KEY`` is set. Caller is the importer
          of ``replay_routes`` (uvicorn boots fail-closed; attacker cannot
          simply set env to bypass).

      ``resolve_manifest_verify_test_key(actor_id, declared_hash, audit_emit_fn)``
          Per-route gate for POST ``/manifest/verify``. Returns the test key
          (empty string if live profile or env unset). Live profile + env
          set → emit ``replay_signature_test_key_blocked`` audit + return
          empty string; per-request fail-closed mirrors module-init.

      ``verify_replay_cancel_pid(pid, run_id, verify_pid_fn)``
          Sub-routine for POST ``/cancel``. Wraps ``verify_replay_runner_pid``
          (Track A helper) so the route handler returns 409 with
          ``replay_pid_identity_mismatch`` reason when cmdline cert fails.

      ``build_report_idor_sql(manifest_uuid, actor_id, can_read_any)``
          Sub-routine for GET ``/report/{experiment_id}``. Returns ``(sql,
          params)`` tuple. ``can_read_any=True`` (admin) → SQL omits
          ``actor_id`` filter; otherwise SQL includes ``AND s.actor_id = %s``.

      ``check_artifact_path_within_allowlist(artifact_path, allowlist_check_fn)``
          Sub-routine for GET ``/report/{experiment_id}``. Wraps
          ``artifact_path_within_allowlist`` (Track C helper). Returns
          ``(within: bool, error_reason: Optional[str])``.

    All audit emits use the ``audit_emit_fn`` callback so the route module
    can pass its own ``_emit_audit_stub`` (single source of truth for
    audit logging across security guards + route bodies).

MODULE_NOTE (中):
    Sprint 1 Track C E2 退回後的 retrofit（CLAUDE.md §九 1500 LOC 硬上限執
    行）。Replay routes 的 P0-2（TEST_KEY env 注入）/ P0-4（SIGTERM cmdline
    認證）/ P0-5（IDOR 跨 actor + 路徑遍歷）安全修補原 inline 於
    ``replay_routes.py``，Sprint 1 Track C IMPL 完成後檔案 1603 LOC（超
    1500 硬上限 103 LOC）；PM 拒絕 §九 baseline exception 申請。本 module
    抽出安全守門 helper + endpoint body 子常式，讓 ``replay_routes.py`` 重
    回 cap 內，而端點 @router 裝飾器仍在原 module。

    每個 helper 為 *純函式*（無 FastAPI / pydantic import），單測可隔離測
    安全邏輯。需返回非 200 時 raise ``HTTPException``；否則回結構化 tuple，
    由 route handler 轉為 ``_replay_response`` 信封。

    公開 API（用法見 EN 部分）：
      - ``perform_p0_2_boot_guard()``
      - ``resolve_manifest_verify_test_key(...)``
      - ``verify_replay_cancel_pid(...)``
      - ``build_report_idor_sql(...)``
      - ``check_artifact_path_within_allowlist(...)``

    所有 audit emit 透過 ``audit_emit_fn`` callback；route module 傳入自己
    的 ``_emit_audit_stub`` 為單一日誌源（routes + guards 共用）。

SPEC: REF-20 V3 §3 G3 + §6 + §11 + §12 #3 binding
PA Sprint 1 Track C dispatch:
    docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--ref20_sprint1_partition_design.md
E2 retrofit dispatch (Track C return):
    Sprint 1 Track C E2 review verdict — 4 finding (LOC over cap / scope
    not registered / boot guard log-only / V053 race window).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable, Optional, Tuple

# ─── Logging setup / 日誌設定 ────────────────────────────────────────
log = logging.getLogger("replay.security_guards")


# ═══════════════════════════════════════════════════════════════════════════════
# P0-2 — TEST_KEY env var bypass guard / TEST_KEY env 注入守門
# ═══════════════════════════════════════════════════════════════════════════════


def perform_p0_2_boot_guard(
    is_live_release_profile_fn: Callable[[], bool],
    test_key_env_var: str = "OPENCLAW_REPLAY_VERIFY_TEST_KEY",
) -> None:
    """Module-init fail-closed guard for live profile + TEST_KEY env coexistence.
    Module-init fail-closed 守門：live profile + TEST_KEY env 共存即 raise。

    REF-20 Sprint 1 Track C P0-2 + E2 retrofit F6 — the original IMPL
    only logged ERROR if both env vars were set; attacker controlling env
    could still continue uvicorn startup. E2 retrofit forces fail-closed:
    raise ``RuntimeError`` so uvicorn boot fails before any request can
    enter the verify endpoint.

    Dev-mode safety: this only raises when BOTH conditions hold
    (``OPENCLAW_RELEASE_PROFILE='live'`` AND ``OPENCLAW_REPLAY_VERIFY_TEST_KEY``
    is non-empty). In dev / test, ``OPENCLAW_RELEASE_PROFILE`` is unset
    (default = empty), so this branch is unreachable in normal dev work.

    REF-20 Sprint 1 Track C P0-2 + E2 retrofit F6 — 前版只在雙設時 log
    ERROR；attacker 控 env 仍可繼續啟動 uvicorn。E2 retrofit 強制 fail-closed：
    raise ``RuntimeError`` 使 uvicorn 啟動失敗，請求未到 verify 端點即斷。

    Dev-mode 安全性：僅雙條件（``OPENCLAW_RELEASE_PROFILE='live'`` 且
    ``OPENCLAW_REPLAY_VERIFY_TEST_KEY`` 非空）才 raise。dev / test 不設
    ``OPENCLAW_RELEASE_PROFILE``（預設空），此分支於正常 dev 工作不可達。

    Args / 參數:
        is_live_release_profile_fn: Callable returning True iff the
            release profile is live (passed in for testability; production
            uses ``route_helpers.is_live_release_profile``).
        test_key_env_var: Env var name to check; default
            ``"OPENCLAW_REPLAY_VERIFY_TEST_KEY"``.

    Raises / 例外:
        RuntimeError: live profile + TEST_KEY env both set (attack
            surface; fail-closed at boot).
    """
    if is_live_release_profile_fn() and os.environ.get(test_key_env_var, "").strip():
        # Fail-closed boot: do NOT continue. Operator must un-set the test
        # key env (attacker-supplied or stale dev override) before starting
        # uvicorn in live profile.
        # Fail-closed boot：不可繼續。Operator 必清掉 test key env（attacker
        # 設或 dev 殘留）後才能在 live profile 啟動 uvicorn。
        raise RuntimeError(
            "REF-20 Track C P0-2 boot guard FAIL-CLOSED: "
            f"{test_key_env_var} is set with OPENCLAW_RELEASE_PROFILE=live; "
            "test_key_hex must NEVER be honored in live profile (forge risk). "
            "Unset the env var or change OPENCLAW_RELEASE_PROFILE before booting."
        )


def resolve_manifest_verify_test_key(
    *,
    actor_id: str,
    declared_hash_hex: str,
    is_live_release_profile_fn: Callable[[], bool],
    audit_emit_fn: Callable[..., None],
    test_key_env_var: str = "OPENCLAW_REPLAY_VERIFY_TEST_KEY",
) -> str:
    """Per-route gate: live profile forces test key empty + audits the block.
    Per-route 守門：live profile 強制清空 test key 並 audit。

    REF-20 Sprint 1 Track C P0-2 — defense-in-depth on the boot guard.
    The boot guard fails uvicorn startup; this function still fires on
    every request because:
      1. attacker may not control boot (e.g. systemd-managed unit with
         locked env); test key may be set later via shell exec into
         container / pid-fs;
      2. boot guard catch in non-live profile (dev) where TEST_KEY is
         legitimate — this gate only redacts when explicitly live.

    REF-20 Sprint 1 Track C P0-2 — boot guard 的縱深防禦。boot guard 已使
    uvicorn 啟動失敗；本函式仍逐請求觸發，因：
      1. attacker 可能不控 boot（systemd-managed unit、env 鎖定）；test key
         可能後續經 shell exec / pid-fs 注入；
      2. boot guard 不對 dev 啟動有效（dev TEST_KEY 為合法工具）；本守門僅
         在 explicit live 時清空。

    Args:
        actor_id: 認證後 actor id（audit row）。
        declared_hash_hex: body 內聲明 manifest hash（audit row）。
        is_live_release_profile_fn: Callable returning True iff live profile.
        audit_emit_fn: ``_emit_audit_stub`` callback（caller 提供以共用
            audit logger）。
        test_key_env_var: Env var name; default
            ``"OPENCLAW_REPLAY_VERIFY_TEST_KEY"``.

    Returns / 回傳:
        Empty string if live profile is active (test key force-cleared);
        otherwise the env var value (may itself be empty if not set).
    """
    if is_live_release_profile_fn():
        if os.environ.get(test_key_env_var, "").strip():
            audit_emit_fn(
                event_type="replay_signature_test_key_blocked",
                actor_id=actor_id,
                experiment_id=None,
                manifest_hash=declared_hash_hex,
                decision="blocked_by_release_profile",
                extra_payload={"release_profile": "live"},
            )
        return ""
    return os.environ.get(test_key_env_var, "")


# ═══════════════════════════════════════════════════════════════════════════════
# P0-4 — SIGTERM cmdline cert / SIGTERM cmdline 認證
# ═══════════════════════════════════════════════════════════════════════════════


def execute_replay_cancel_pg_path(
    *,
    actor_id: str,
    cancel_reason: Optional[str],
    statement_timeout_ms: int,
    get_pg_conn_fn: Callable[..., Any],
    v045_table_present_fn: Callable[[Any], bool],
    verify_pid_fn: Callable[[int], Tuple[bool, Optional[str]]],
    log_fn: Optional[Callable[..., None]] = None,
) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
    """Cancel-route PG path: SELECT active run + cmdline cert + UPDATE row.
    Cancel route PG 路徑：SELECT active run + cmdline 認證 + UPDATE row。

    REF-20 Sprint 1 Track C P0-4 + E2 retrofit — extracted from
    ``replay_routes.py`` ``post_replay_cancel`` to satisfy CLAUDE.md §九
    1500 LOC hard cap. Logic is unchanged from the inline form: hold a
    single PG cursor for the whole xact (V045 SELECT → cmdline cert →
    UPDATE row to cancelled). The only IO outside the xact is
    ``os.kill(pid, SIGTERM)`` which is caller-handled (route handler
    issues the signal *after* this helper returns ``cancelled_dict``;
    that keeps the helper test-hermetic without `os.kill` mocking).

    REF-20 Sprint 1 Track C P0-4 + E2 retrofit — 從 ``replay_routes.py``
    ``post_replay_cancel`` 抽出，以符合 CLAUDE.md §九 1500 LOC 硬上限。
    邏輯與 inline 一致：單一 PG cursor 包整 xact（V045 SELECT → cmdline
    認證 → UPDATE row → cancelled）。xact 外的 IO 只剩 ``os.kill(pid,
    SIGTERM)``，由 caller route handler 在 helper 回 ``cancelled_dict``
    後送（保持 helper test 封閉，無需 mock os.kill）。

    Args:
        actor_id: 認證後 actor id（V045 SELECT WHERE actor_id）。
        cancel_reason: V045 ``cancel_reason`` column；可為 None。
        statement_timeout_ms: SET LOCAL statement_timeout 毫秒。
        get_pg_conn_fn: ``get_pg_conn`` callable（context manager）。
        v045_table_present_fn: ``v045_table_present`` callable（cur → bool）。
        verify_pid_fn: ``verify_replay_runner_pid`` callable（pid → tuple）。
        log_fn: optional ``logger.warning`` callable for PG path 異常記錄。

    Returns / 回傳:
        (cancelled_dict, err_or_none) where cancelled_dict (when err_or_none
        is None) contains:
          - ``run_id``: V045 PK ::text
          - ``manifest_id``: V045 manifest_id ::text
          - ``subprocess_pid``: V045 ``subprocess_pid`` (caller os.kill target)
          - ``former_status``: pre-cancel status enum
        Error reasons:
          - ``"pg_unavailable"`` — get_pg_conn returned None.
          - ``"v045_absent"`` — V045 schema not deployed (caller falls back).
          - ``"no_active_run"`` — no starting/running row for actor.
          - ``"pid_identity_mismatch:<reason>"`` — Track C P0-4 fail-closed.
          - ``"race_already_final"`` — UPDATE RETURNING empty (xact race).
          - ``"pg_error:<ExcName>"`` — generic PG exception (rolled back).
    """
    with get_pg_conn_fn() as conn:
        if conn is None:
            return None, "pg_unavailable"
        try:
            cur = conn.cursor()
            cur.execute("SET LOCAL statement_timeout = %s", (statement_timeout_ms,))
            if not v045_table_present_fn(cur):
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

            # Track C P0-4 fail-closed: psutil cmdline cert before SIGTERM.
            # Track C P0-4 fail-closed：psutil cmdline 認證後再 SIGTERM。
            pid_safe, pid_err = verify_replay_cancel_pid(pid, run_id, verify_pid_fn)
            if not pid_safe:
                return None, f"pid_identity_mismatch:{pid_err}"

            # Flip DB row to cancelled.
            # 翻 DB row 為 cancelled。
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
                (cancel_reason, run_id),
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
        except Exception as exc:  # noqa: BLE001 — fail-closed PG envelope
            if log_fn is not None:
                log_fn("replay_routes /cancel PG path exception: %s", exc)
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001 — best-effort rollback
                pass
            return None, f"pg_error:{type(exc).__name__}"


def verify_replay_cancel_pid(
    pid: Optional[int],
    run_id: str,
    verify_pid_fn: Callable[[int], Tuple[bool, Optional[str]]],
) -> Tuple[bool, Optional[str]]:
    """Cmdline-cert wrapper for cancel-route SIGTERM target.
    Cancel route 對 SIGTERM 目標的 cmdline 認證封裝。

    REF-20 Sprint 1 Track C P0-4 — wrap ``verify_replay_runner_pid``
    (Track A helper) so the cancel route handler can fail-closed before
    issuing ``os.kill``. PID-reuse safe via psutil cmdline check (the
    Track A helper queries the *current* process's argv; reused PIDs
    return unrelated cmdline → False).

    REF-20 Sprint 1 Track C P0-4 — 封裝 ``verify_replay_runner_pid``
    （Track A helper），cancel route 在 ``os.kill`` 前 fail-closed。
    PID reuse 安全：Track A helper 查當前 process argv，被復用的 PID 回
    無關 cmdline → False。

    Args:
        pid: V045 ``subprocess_pid`` column value (raw, untrusted).
            ``None`` or ``≤ 0`` → return ``(True, None)`` (no SIGTERM
            target; caller skips ``os.kill`` regardless).
        run_id: V045 PK; logging only.
        verify_pid_fn: ``verify_replay_runner_pid`` callable; injected
            for testability.

    Returns / 回傳:
        (True, None) — pid is missing/zero or cmdline contains
            ``replay_runner`` (caller may call ``os.kill``).
        (False, "<error_reason>") — cmdline check failed; caller
            MUST NOT call ``os.kill`` and should return 409 with
            ``replay_pid_identity_mismatch`` reason.
    """
    if pid is None or pid <= 0:
        return True, None
    pid_ok, pid_err = verify_pid_fn(int(pid))
    if not pid_ok:
        log.warning(
            "cancel_run: PID identity FAILED pid=%d run=%s err=%s; "
            "SKIPPING SIGTERM (Track C P0-4)",
            pid, run_id, pid_err,
        )
        return False, pid_err
    return True, None


# ═══════════════════════════════════════════════════════════════════════════════
# P0-5a — IDOR cross-actor SQL + admin bypass / IDOR 跨 actor SQL + admin 旁通
# ═══════════════════════════════════════════════════════════════════════════════


# Base SELECT (shared between admin-bypass + actor-filtered branches).
# 共用基底 SELECT（admin bypass + actor-filtered 兩分支共享）。
_REPORT_BASE_SELECT = (
    "SELECT a.artifact_id::text, a.artifact_type, a.artifact_path, a.byte_size, "
    "a.is_mock, EXTRACT(EPOCH FROM a.created_at)*1000 AS created_at_ms, "
    "s.run_id::text, s.status, s.exit_code, "
    "EXTRACT(EPOCH FROM s.started_at)*1000 AS started_at_ms, "
    "EXTRACT(EPOCH FROM s.completed_at)*1000 AS completed_at_ms "
    "FROM replay.report_artifacts a JOIN replay.run_state s ON a.run_id = s.run_id "
)

_REPORT_ARTIFACT_ORDER_BY = (
    "ORDER BY CASE a.artifact_type "
    "WHEN 'replay_report' THEN 0 "
    "WHEN 'pnl_summary' THEN 1 "
    "ELSE 2 END, a.created_at;"
)


def build_report_idor_sql(
    manifest_uuid: str,
    actor_id: str,
    can_read_any: bool,
) -> Tuple[str, Tuple[Any, ...]]:
    """Build (sql, params) for GET /replay/report/{experiment_id} with IDOR fix.
    為 GET /replay/report/{experiment_id} 構造帶 IDOR 守門的 (sql, params)。

    REF-20 Sprint 1 Track C P0-5a + E2 retrofit F8 — default branch adds
    ``AND s.actor_id = %s`` filter so plain-operator viewers cannot read
    cross-actor reports. Admin path (``can_read_any=True``) omits the
    filter for cross-actor incident investigation; admin must hold the
    explicitly-registered ``replay:read:any`` scope (defaults registered
    by E2 F8 retrofit).

    REF-20 Sprint 1 Track C P0-5a + E2 retrofit F8 — 預設分支加
    ``AND s.actor_id = %s`` filter，plain operator viewer 不可讀跨 actor
    report。Admin 路徑（``can_read_any=True``）不加 filter，供跨 actor
    incident investigation 使用；admin 須持 explicit-registered
    ``replay:read:any`` scope（E2 F8 retrofit 後 default 集合內登記）。

    Args:
        manifest_uuid: UUID5-derived manifest uuid（route handler 由
            ``experiment_id`` 衍生）。
        actor_id: 認證後 actor id（plain branch 必傳；admin branch 不用）。
        can_read_any: True iff actor holds ``replay:read:any`` scope.

    Returns / 回傳:
        (sql_str, params_tuple) — caller passes to ``_async_safe_pg_select``.
        Plain branch: ``len(params) == 2``（manifest_uuid, actor_id）。
        Admin branch: ``len(params) == 1``（manifest_uuid）。
    """
    if can_read_any:
        sql = _REPORT_BASE_SELECT + (
            "WHERE s.manifest_id = %s::uuid " + _REPORT_ARTIFACT_ORDER_BY
        )
        return sql, (manifest_uuid,)
    sql = _REPORT_BASE_SELECT + (
        "WHERE s.manifest_id = %s::uuid AND s.actor_id = %s "
        + _REPORT_ARTIFACT_ORDER_BY
    )
    return sql, (manifest_uuid, actor_id)


# ═══════════════════════════════════════════════════════════════════════════════
# P0-5b — Path traversal allowlist guard / 路徑遍歷白名單守門
# ═══════════════════════════════════════════════════════════════════════════════


def check_artifact_path_within_allowlist(
    artifact_path: Path,
    allowlist_check_fn: Callable[[Path], Tuple[bool, Optional[str]]],
) -> Tuple[bool, Optional[str]]:
    """Wrap ``artifact_path_within_allowlist`` for sub-routine reuse.
    封裝 ``artifact_path_within_allowlist`` 以便子常式重用。

    REF-20 Sprint 1 Track C P0-5b — thin wrapper exists so route handler
    can call a single name from this security_guards module without
    needing a direct import of route_helpers (decoupling); also leaves a
    single grep-anchor for future allowlist policy hardening (e.g. tier
    fences, symlink resolution depth limits).

    REF-20 Sprint 1 Track C P0-5b — 薄封裝；route handler 從本 module 呼叫
    單一名稱即可，不需 direct import route_helpers（解耦）；同時為未來
    allowlist 政策硬化（tier fences、symlink resolve 深度限制）留單一
    grep anchor。

    Args:
        artifact_path: V046 ``artifact_path`` column value (untrusted).
        allowlist_check_fn: ``artifact_path_within_allowlist`` callable.

    Returns / 回傳:
        (True, None) — within allowlist (caller may open file).
        (False, "<error_reason>") — caller MUST NOT open file; sets
            ``payload_read_error="path_traversal_blocked:<reason>"`` on
            the artifact response and emits
            ``replay_artifact_path_traversal_blocked`` audit.
    """
    return allowlist_check_fn(artifact_path)


# ═══════════════════════════════════════════════════════════════════════════════
# Module export / 模組匯出
# ═══════════════════════════════════════════════════════════════════════════════


__all__ = [
    "build_report_idor_sql",
    "check_artifact_path_within_allowlist",
    "execute_replay_cancel_pg_path",
    "perform_p0_2_boot_guard",
    "resolve_manifest_verify_test_key",
    "verify_replay_cancel_pid",
]
