"""
Governance Autonomy Service — Autonomy Level 子域業務邏輯 + 路由。

MODULE_NOTE (中):
  模塊用途：承載系統級 Autonomy Level（Conservative / Standard）子域的全部業務
    邏輯與 REST 路由，從 governance_routes.py 提取（P2a 行為保留重構，CLAUDE.md §七
    route handler 僅 parse→call→format）。
  主要類/函數：
    - AutonomyLevelSwitchRequest（請求模型）
    - _build_autonomy_state_payload（讀 V099 PG 狀態 + eligibility + 冷卻計算）
    - _perform_autonomy_switch（advisory-lock + FOR UPDATE 守護的切換交易）
    - _record_autonomy_switch_attempt / _insert_autonomy_switch_audit（審計持久化）
    - _get_autonomy_pg_conn（共享 PG context manager，測試可 patch）
    - 4 個路由：/autonomy-level/state、/eligibility、/status、/switch
  依賴：
    - governance_routes：共享 governance_router、GovernanceResponse、依賴注入
      （_get_auth_actor / _require_operator_auth）、_sanitize_log。
    - autonomy_totp：TOTP 後端探測與驗證。
    - db_pool.get_pg_conn：system.autonomy_level_config / autonomy_level_switch_audit。
  硬邊界：
    - 切換是狀態變更路徑，任一守護（typed_confirm / eligibility / TOTP / cooldown /
      advisory-lock race）失敗必 fail-closed，失敗嘗試在 V099 可用時仍寫審計。
    - 5-gate live 邊界（_AUTONOMY_PATH_MATRIX 前 5 行）為 hard-locked baseline，
      Autonomy Level 切換不改變它們。

注意：本模塊的路由透過 side-effect import 註冊到 governance_router；測試 patch 的
  符號（_get_autonomy_pg_conn / _autonomy_eligibility_payload /
  _autonomy_totp_backend_configured / _verify_autonomy_totp）均為本模塊級全局，
  路由與內部 helper 以裸名引用，monkeypatch.setattr(本模塊, ...) 即可生效。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from .autonomy_totp import (
    autonomy_totp_backend_configured,
    verify_autonomy_totp,
)
from .error_sanitize import log_safe_exception
from .governance_routes import (
    GovernanceResponse,
    _get_auth_actor,
    _require_operator_auth,
    governance_router,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Request Models / 請求模型
# ═══════════════════════════════════════════════════════════════════════════════

class AutonomyLevelSwitchRequest(BaseModel):
    """Request to switch system-wide Autonomy Level / 切換系統級自主程度請求"""

    target_level: str = Field(..., min_length=1, max_length=32)
    reason: str = Field(..., min_length=30, max_length=1000)
    typed_confirm_phrase: str = Field(..., min_length=1, max_length=64)
    totp_code: str = Field(..., min_length=1, max_length=32)
    emergency_override: bool = False
    emergency_override_reason: str | None = Field(default=None, max_length=1000)


# ═══════════════════════════════════════════════════════════════════════════════
# Constants / 常量
# ═══════════════════════════════════════════════════════════════════════════════

_AUTONOMY_LEVELS = {"CONSERVATIVE", "STANDARD"}
_AUTONOMY_TYPED_CONFIRM = "CONFIRM SWITCH"
_AUTONOMY_COOLDOWN_SECONDS = 24 * 60 * 60
_AUTONOMY_ADVISORY_LOCK_KEY = 2026052101

_AUTONOMY_PATH_MATRIX: list[dict[str, str]] = [
    {
        "id": "5-gate-A",
        "path": "Python live_reserved",
        "category": "hard-locked baseline",
        "level1": "manual + Operator role",
        "level2": "manual + Operator role",
    },
    {
        "id": "5-gate-B",
        "path": "Python Operator role",
        "category": "hard-locked baseline",
        "level1": "manual",
        "level2": "manual",
    },
    {
        "id": "5-gate-C",
        "path": "OPENCLAW_ALLOW_MAINNET=1",
        "category": "hard-locked baseline",
        "level1": "manual env-var",
        "level2": "manual env-var",
    },
    {
        "id": "5-gate-D",
        "path": "Valid secret slot",
        "category": "hard-locked baseline",
        "level1": "manual secret slot",
        "level2": "manual secret slot",
    },
    {
        "id": "5-gate-E",
        "path": "Signed authorization.json",
        "category": "hard-locked baseline",
        "level1": "manual renew/approve",
        "level2": "manual renew/approve",
    },
    {"id": "(a)", "path": "Stage LAL 3-4 promotion", "category": "protected", "level1": "operator manual", "level2": "auto with fail-safe"},
    {"id": "(b)", "path": "5-gate live boundary toggle", "category": "protected hard-lock", "level1": "operator manual", "level2": "operator manual"},
    {"id": "(c)", "path": "Copy Trading enable", "category": "protected", "level1": "operator manual", "level2": "auto with ADR-0030 + fail-safe"},
    {"id": "(d)", "path": "Auto-Allocator activation", "category": "protected", "level1": "operator manual", "level2": "auto with LAL gate + fail-safe"},
    {"id": "(e)", "path": "Kill criteria trigger", "category": "protected fail-closed", "level1": "auto-trigger", "level2": "auto-trigger"},
    {"id": "(f)", "path": "ADR-debt land", "category": "protected", "level1": "operator manual", "level2": "auto with R4 verify + fail-safe"},
    {"id": "(g)", "path": "LAL 1 intra-strategy reparam", "category": "opt-in", "level1": "auto with fail-safe", "level2": "auto with fail-safe"},
    {"id": "(h)", "path": "LAL 2 cross-strategy reweight", "category": "opt-in", "level1": "auto with fail-safe", "level2": "auto with fail-safe"},
    {"id": "(i)", "path": "M2 always-on overlay", "category": "opt-in", "level1": "auto with fail-safe", "level2": "auto with fail-safe"},
    {"id": "(j)", "path": "M3 Tier 1+2 health degradation", "category": "opt-in fail-closed", "level1": "auto-trigger", "level2": "auto-trigger"},
    {"id": "(k)", "path": "M6 <=30% reward weight adjustment", "category": "opt-in", "level1": "auto with fail-safe", "level2": "auto with fail-safe"},
    {"id": "(l)", "path": "M7 demote enforced 14d x 50%", "category": "opt-in", "level1": "auto with fail-safe", "level2": "auto with fail-safe"},
    {"id": "(m)", "path": "M8 anomaly active trigger Y2", "category": "opt-in", "level1": "auto with fail-safe", "level2": "auto with fail-safe"},
    {"id": "(n)", "path": "M10 capital tier evaluation", "category": "opt-in", "level1": "auto with fail-safe", "level2": "auto with fail-safe"},
    {"id": "venue", "path": "Venue change", "category": "hard-locked carve-out", "level1": "operator manual", "level2": "operator manual"},
]


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers / 輔助函數
# ═══════════════════════════════════════════════════════════════════════════════

def _get_autonomy_pg_conn() -> Any:
    """Return the shared PG context manager. Wrapped for focused route tests."""
    from .db_pool import get_pg_conn  # noqa: PLC0415

    return get_pg_conn()


def _row_to_dict(cursor: Any, row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    columns = [col[0] for col in cursor.description]
    return dict(zip(columns, row))


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _autonomy_level_label(level: str | None) -> str:
    return {
        "CONSERVATIVE": "Level 1 Conservative",
        "STANDARD": "Level 2 Standard",
    }.get(level or "", "Unknown")


def _autonomy_totp_backend_configured() -> bool:
    return autonomy_totp_backend_configured()


def _verify_autonomy_totp(_code: str) -> tuple[bool, str, str]:
    return verify_autonomy_totp(_code)


def _autonomy_eligibility_payload() -> dict[str, Any]:
    gates = [
        {
            "id": "C-1",
            "label": "21d demo stability",
            "passed": False,
            "status": "blocked",
            "detail": "P0-EDGE-1 evidence baseline is still active; Level 2 remains disabled.",
            "source": "p0_edge_1_pending",
        },
        {
            "id": "C-2",
            "label": "strategy sample floor N>=30",
            "passed": False,
            "status": "blocked",
            "detail": "Alpha-bearing / textbook strategy evidence is not yet sufficient for Level 2.",
            "source": "p0_edge_1_pending",
        },
        {
            "id": "C-3",
            "label": "Wilson 95% lower bound positive",
            "passed": False,
            "status": "blocked",
            "detail": "Wilson-positive evidence gate is pending Sprint 2 Alpha Tournament output.",
            "source": "p0_edge_1_pending",
        },
    ]
    return {
        "eligible": all(g["passed"] for g in gates),
        "gates": gates,
        "summary": "Level 2 enablement remains gated by P0-EDGE-1 evidence.",
    }


def _build_autonomy_state_payload() -> tuple[dict[str, Any], str | None]:
    eligibility = _autonomy_eligibility_payload()
    base: dict[str, Any] = {
        "schema_available": False,
        "wiring_status": "degraded",
        "current_level": "CONSERVATIVE",
        "current_level_label": _autonomy_level_label("CONSERVATIVE"),
        "target_level": "STANDARD",
        "typed_confirm_phrase": _AUTONOMY_TYPED_CONFIRM,
        "totp_backend_configured": _autonomy_totp_backend_configured(),
        "cooldown_remaining_seconds": None,
        "can_switch": False,
        "switch_blockers": ["v099_schema_unavailable", "totp_backend_unavailable"],
        "eligibility": eligibility,
        "matrix": _AUTONOMY_PATH_MATRIX,
        "latest_audit": None,
        "notification": {
            "slack": None,
            "email": None,
            "banner": None,
            "escalation_result": None,
        },
    }

    with _get_autonomy_pg_conn() as conn:
        if conn is None:
            base["reason"] = "pg_unavailable"
            return base, "pg_unavailable"
        try:
            cur = conn.cursor()
            cur.execute("SET LOCAL statement_timeout = %s", (2000,))
            cur.execute(
                """
                SELECT current_level::text AS current_level,
                       last_switched_at,
                       switched_by,
                       switch_reason,
                       created_at,
                       updated_at
                  FROM system.autonomy_level_config
                 WHERE id = 1
                 LIMIT 1;
                """
            )
            row = _row_to_dict(cur, cur.fetchone())
            if not row:
                base["reason"] = "v099_config_row_absent"
                return base, "v099_config_row_absent"

            cur.execute(
                """
                SELECT audit_id,
                       switched_at_utc,
                       switched_at_local,
                       actor,
                       actor_role,
                       level_before::text AS level_before,
                       level_after::text AS level_after,
                       twofa_verify_result,
                       twofa_method,
                       switch_reason,
                       result,
                       emergency_override,
                       emergency_override_reason,
                       notification_slack_status,
                       notification_email_status,
                       notification_banner_status,
                       notification_escalation_result
                  FROM system.autonomy_level_switch_audit
                 ORDER BY switched_at_utc DESC, audit_id DESC
                 LIMIT 1;
                """
            )
            latest = _row_to_dict(cur, cur.fetchone()) or None
        except Exception as exc:  # noqa: BLE001 - status endpoint must degrade
            log_safe_exception(
                logger,
                "autonomy_state_query",
                exc,
                level=logging.WARNING,
            )
            base["reason"] = "pg_error"
            base["error"] = "autonomy_state_unavailable"
            return base, base["reason"]

    level = str(row.get("current_level") or "CONSERVATIVE").upper()
    if level not in _AUTONOMY_LEVELS:
        level = "CONSERVATIVE"
    target = "STANDARD" if level == "CONSERVATIVE" else "CONSERVATIVE"
    last_switched_at = row.get("last_switched_at")
    cooldown_remaining: int | None = None
    if isinstance(last_switched_at, datetime):
        elapsed = (datetime.now(timezone.utc) - last_switched_at).total_seconds()
        cooldown_remaining = max(0, int(_AUTONOMY_COOLDOWN_SECONDS - elapsed))

    blockers: list[str] = []
    if not _autonomy_totp_backend_configured():
        blockers.append("totp_backend_unavailable")
    if target == "STANDARD" and not eligibility["eligible"]:
        blockers.append("level2_evidence_gate_not_met")
    if cooldown_remaining is not None and cooldown_remaining > 0:
        blockers.append("cooldown_active")

    notification = {
        "slack": latest.get("notification_slack_status") if latest else None,
        "email": latest.get("notification_email_status") if latest else None,
        "banner": latest.get("notification_banner_status") if latest else None,
        "escalation_result": latest.get("notification_escalation_result") if latest else None,
    }

    payload = {
        **base,
        "schema_available": True,
        "wiring_status": "pg_path_active",
        "reason": None,
        "current_level": level,
        "current_level_label": _autonomy_level_label(level),
        "target_level": target,
        "target_level_label": _autonomy_level_label(target),
        "last_switched_at_utc": _iso(last_switched_at),
        "last_switched_at_local": _iso(latest.get("switched_at_local")) if latest else None,
        "switched_by": row.get("switched_by"),
        "switch_reason": row.get("switch_reason"),
        "updated_at": _iso(row.get("updated_at")),
        "cooldown_remaining_seconds": cooldown_remaining,
        "switch_blockers": blockers,
        "can_switch": not blockers,
        "notification": notification,
        "latest_audit": {
            **latest,
            "switched_at_utc": _iso(latest.get("switched_at_utc")),
            "switched_at_local": _iso(latest.get("switched_at_local")),
        } if latest else None,
    }
    return payload, None


def _insert_autonomy_switch_audit(
    *,
    actor_id: str,
    level_before: str,
    level_after: str,
    twofa_result: str | None,
    twofa_method: str | None,
    reason: str,
    result: str,
    emergency_override: bool = False,
    emergency_override_reason: str | None = None,
    cursor: Any,
) -> None:
    cursor.execute(
        """
        INSERT INTO system.autonomy_level_switch_audit (
            actor,
            actor_role,
            level_before,
            level_after,
            twofa_verify_result,
            twofa_method,
            switch_reason,
            result,
            emergency_override,
            emergency_override_reason,
            notification_slack_status,
            notification_email_status,
            notification_banner_status
        ) VALUES (
            %s,
            'operator',
            %s::system.autonomy_level_enum,
            %s::system.autonomy_level_enum,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            'SKIPPED',
            'SKIPPED',
            'SHOWN'
        );
        """,
        (
            actor_id,
            level_before,
            level_after,
            twofa_result,
            twofa_method,
            reason,
            result,
            emergency_override,
            emergency_override_reason,
        ),
    )


def _record_autonomy_switch_attempt(
    *,
    actor_id: str,
    target_level: str,
    reason: str,
    result: str,
    twofa_result: str | None = None,
    twofa_method: str | None = None,
    emergency_override: bool = False,
    emergency_override_reason: str | None = None,
) -> tuple[bool, str | None]:
    with _get_autonomy_pg_conn() as conn:
        if conn is None:
            return False, "pg_unavailable"
        try:
            cur = conn.cursor()
            cur.execute("SET LOCAL statement_timeout = %s", (2000,))
            cur.execute(
                "SELECT current_level::text FROM system.autonomy_level_config WHERE id=1 LIMIT 1;"
            )
            row = cur.fetchone()
            if row is None:
                return False, "v099_config_row_absent"
            level_before = str(row[0])
            if level_before == target_level:
                return False, "noop_target"
            _insert_autonomy_switch_audit(
                actor_id=actor_id,
                level_before=level_before,
                level_after=target_level,
                twofa_result=twofa_result,
                twofa_method=twofa_method,
                reason=reason,
                result=result,
                emergency_override=emergency_override,
                emergency_override_reason=emergency_override_reason,
                cursor=cur,
            )
            conn.commit()
            return True, None
        except Exception as exc:  # noqa: BLE001 - audit attempt must fail closed
            try:
                conn.rollback()
            except Exception:
                pass
            log_safe_exception(logger, "autonomy_switch_audit_write", exc)
            return False, "pg_error"


def _perform_autonomy_switch(
    *,
    actor_id: str,
    target_level: str,
    reason: str,
    emergency_override: bool,
    emergency_override_reason: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    with _get_autonomy_pg_conn() as conn:
        if conn is None:
            return None, "pg_unavailable"
        try:
            cur = conn.cursor()
            cur.execute("SET LOCAL statement_timeout = %s", (5000,))
            cur.execute("SELECT pg_try_advisory_xact_lock(%s);", (_AUTONOMY_ADVISORY_LOCK_KEY,))
            lock_row = cur.fetchone()
            if not lock_row or lock_row[0] is not True:
                cur.execute(
                    "SELECT current_level::text FROM system.autonomy_level_config WHERE id=1 LIMIT 1;"
                )
                current_row = cur.fetchone()
                level_before = str(current_row[0]) if current_row else "CONSERVATIVE"
                if level_before != target_level:
                    _insert_autonomy_switch_audit(
                        actor_id=actor_id,
                        level_before=level_before,
                        level_after=target_level,
                        twofa_result="PASS",
                        twofa_method="TOTP",
                        reason=reason,
                        result="race_lost",
                        emergency_override=emergency_override,
                        emergency_override_reason=emergency_override_reason,
                        cursor=cur,
                    )
                    conn.commit()
                return None, "race_lost"

            cur.execute(
                """
                SELECT current_level::text AS current_level, last_switched_at
                  FROM system.autonomy_level_config
                 WHERE id=1
                 FOR UPDATE;
                """
            )
            row = cur.fetchone()
            if row is None:
                return None, "v099_config_row_absent"
            level_before = str(row[0])
            last_switched_at = row[1]
            if level_before == target_level:
                return None, "noop_target"

            if (
                isinstance(last_switched_at, datetime)
                and not emergency_override
                and (datetime.now(timezone.utc) - last_switched_at).total_seconds()
                < _AUTONOMY_COOLDOWN_SECONDS
            ):
                _insert_autonomy_switch_audit(
                    actor_id=actor_id,
                    level_before=level_before,
                    level_after=target_level,
                    twofa_result="PASS",
                    twofa_method="TOTP",
                    reason=reason,
                    result="cooldown_blocked",
                    emergency_override=False,
                    emergency_override_reason=None,
                    cursor=cur,
                )
                conn.commit()
                return None, "cooldown_blocked"

            cur.execute(
                """
                UPDATE system.autonomy_level_config
                   SET current_level = %s::system.autonomy_level_enum,
                       switched_by = %s,
                       switch_reason = %s,
                       last_switched_at = now()
                 WHERE id = 1;
                """,
                (target_level, actor_id, reason),
            )
            _insert_autonomy_switch_audit(
                actor_id=actor_id,
                level_before=level_before,
                level_after=target_level,
                twofa_result="PASS",
                twofa_method="TOTP",
                reason=reason,
                result="success",
                emergency_override=emergency_override,
                emergency_override_reason=emergency_override_reason,
                cursor=cur,
            )
            cur.execute("NOTIFY autonomy_level_changed;")
            conn.commit()
            payload, _ = _build_autonomy_state_payload()
            return payload, None
        except Exception as exc:  # noqa: BLE001 - state-changing path fail-closed
            try:
                conn.rollback()
            except Exception:
                pass
            log_safe_exception(logger, "autonomy_switch_transaction", exc)
            return None, "pg_error"


# ═══════════════════════════════════════════════════════════════════════════════
# Routes / 路由（side-effect 註冊到 governance_router）
# ═══════════════════════════════════════════════════════════════════════════════

@governance_router.get("/autonomy-level/state")
def get_autonomy_level_state(
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Return system-wide Autonomy Level posture.
    返回系統級 Autonomy Level 姿態；PG 不可用時顯式 degraded。
    """
    payload, err = _build_autonomy_state_payload()
    message = "autonomy_level_state_degraded" if err else "autonomy_level_state"
    return GovernanceResponse.success(data=payload, message=message)


@governance_router.get("/autonomy-level/eligibility")
def get_autonomy_level_eligibility(
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Return Level 2 enablement gates.
    返回 Level 2 啟用門檻；目前保守綁定 P0-EDGE-1 未關狀態。
    """
    return GovernanceResponse.success(
        data=_autonomy_eligibility_payload(),
        message="autonomy_level_eligibility",
    )


@governance_router.get("/autonomy-level/status")
def get_autonomy_level_status(
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """Compatibility alias for the GUI preview banner path."""
    payload, err = _build_autonomy_state_payload()
    message = "autonomy_level_status_degraded" if err else "autonomy_level_status"
    return GovernanceResponse.success(data=payload, message=message)


@governance_router.post("/autonomy-level/switch")
def switch_autonomy_level(
    body: AutonomyLevelSwitchRequest,
    actor: Any = Depends(_require_operator_auth),
) -> dict[str, Any]:
    """
    Switch Autonomy Level through the guarded PG transaction path.

    The production path fails closed when the TOTP backend or evidence gate is
    unavailable; failed attempts are still audit-persisted when V099 is available.
    """
    target = body.target_level.strip().upper()
    actor_id = str(getattr(actor, "actor_id", "unknown_operator"))
    if target not in _AUTONOMY_LEVELS:
        raise HTTPException(
            status_code=400,
            detail={"reason_codes": ["invalid_target_level"], "message": "target_level must be CONSERVATIVE or STANDARD"},
        )
    if body.emergency_override and not (body.emergency_override_reason or "").strip():
        raise HTTPException(
            status_code=400,
            detail={"reason_codes": ["emergency_override_reason_required"], "message": "emergency_override_reason is required"},
        )

    if body.typed_confirm_phrase != _AUTONOMY_TYPED_CONFIRM:
        _record_autonomy_switch_attempt(
            actor_id=actor_id,
            target_level=target,
            reason=body.reason,
            result="typed_confirm_mismatch",
            emergency_override=body.emergency_override,
            emergency_override_reason=body.emergency_override_reason,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "reason_codes": ["typed_confirm_mismatch"],
                "message": "typed_confirm_phrase must exactly equal CONFIRM SWITCH",
            },
        )

    eligibility = _autonomy_eligibility_payload()
    if target == "STANDARD" and not eligibility["eligible"]:
        _record_autonomy_switch_attempt(
            actor_id=actor_id,
            target_level=target,
            reason=body.reason,
            result="freeze_active_block",
            emergency_override=body.emergency_override,
            emergency_override_reason=body.emergency_override_reason,
        )
        raise HTTPException(
            status_code=403,
            detail={
                "reason_codes": ["level2_evidence_gate_not_met"],
                "message": "Level 2 switch is disabled until evidence gates pass",
                "eligibility": eligibility,
            },
        )

    twofa_ok, twofa_method, twofa_result_code = _verify_autonomy_totp(body.totp_code)
    if not twofa_ok:
        audit_result = "twofa_backend_down" if twofa_result_code == "twofa_backend_down" else "twofa_fail"
        _record_autonomy_switch_attempt(
            actor_id=actor_id,
            target_level=target,
            reason=body.reason,
            result=audit_result,
            twofa_result="FAIL",
            twofa_method=twofa_method,
            emergency_override=body.emergency_override,
            emergency_override_reason=body.emergency_override_reason,
        )
        raise HTTPException(
            status_code=403,
            detail={
                "reason_codes": [twofa_result_code],
                "message": "Autonomy Level switch failed closed at TOTP verification",
            },
        )

    payload, err = _perform_autonomy_switch(
        actor_id=actor_id,
        target_level=target,
        reason=body.reason,
        emergency_override=body.emergency_override,
        emergency_override_reason=body.emergency_override_reason,
    )
    if err == "cooldown_blocked":
        raise HTTPException(
            status_code=429,
            detail={"reason_codes": ["cooldown_blocked"], "message": "24h Autonomy Level cooldown is active"},
        )
    if err == "race_lost":
        raise HTTPException(
            status_code=409,
            detail={"reason_codes": ["race_lost"], "message": "Another Autonomy Level switch transaction is active"},
        )
    if err == "noop_target":
        raise HTTPException(
            status_code=400,
            detail={"reason_codes": ["noop_target"], "message": "target_level equals current_level"},
        )
    if err:
        raise HTTPException(
            status_code=503,
            detail={"reason_codes": [err], "message": "Autonomy Level switch backend unavailable"},
        )
    return GovernanceResponse.success(data=payload, message="autonomy_level_switched")
