from __future__ import annotations

"""
OpenClaw proposal and approval ledger store.

MODULE_NOTE (中文):
  OC-GW-5/6/7 的唯一 proposal / approval / channel-event 持久化入口。
  本模組只寫 openclaw.* ledger 表；不呼叫 order、config、live-auth、
  deploy、shell、migration 或 Bybit 相關路徑。Approval 在 P1 階段只記錄
  operator decision；side effect delegation 保持 fail-closed。
"""

import hashlib
import json
import logging
import time
from typing import Any

from .db_pool import get_pg_conn

try:  # pragma: no cover - exercised when psycopg2 is installed
    from psycopg2.extras import Json
except Exception:  # pragma: no cover - static tests may omit psycopg2
    Json = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_STATEMENT_TIMEOUT_MS = 2_000
_MAX_PAYLOAD_BYTES = 32_768
_SENSITIVE_KEYS = {
    "api_key",
    "api_secret",
    "authorization",
    "cookie",
    "password",
    "prompt",
    "raw_prompt",
    "raw_response",
    "refresh_token",
    "secret",
    "stack_trace",
    "token",
    "traceback",
}
_SAFE_APPROVAL_TYPES = {"read_only_report", "diagnosis_followup", "offline_replay"}
_SAFE_APPROVAL_RISK_CLASSES = {"read_only", "offline"}
_FORBIDDEN_SIDE_EFFECT_FRAGMENTS = (
    "order",
    "cancel",
    "close",
    "secret",
    "key",
    "live-auth",
    "session/start",
    "risk-config",
    "strategy-config",
    "toml",
    "deploy",
    "restart",
    "shell",
    "migration",
)


class OpenClawProposalStoreUnavailable(RuntimeError):
    pass


class OpenClawProposalValidationError(ValueError):
    pass


def _now_ms() -> int:
    return int(time.time() * 1000)


def _json_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _json_param(value: Any) -> Any:
    if Json is not None:
        return Json(value)
    return json.dumps(value, sort_keys=True, default=str)


def _details_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return dict(parsed) if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            key_lower = key_text.lower()
            if (
                key_lower in _SENSITIVE_KEYS
                or key_lower.endswith("_secret")
                or key_lower.endswith("_token")
                or key_lower.endswith("_password")
            ):
                out[key_text] = "[REDACTED]"
            else:
                out[key_text] = _redact(item)
        return out
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return [_redact(item) for item in value]
    return value


def _bounded_payload(value: Any) -> Any:
    redacted = _redact(value)
    encoded = json.dumps(redacted, sort_keys=True, default=str).encode("utf-8")
    if len(encoded) <= _MAX_PAYLOAD_BYTES:
        return redacted
    return {
        "payload_truncated": True,
        "original_bytes": len(encoded),
        "max_payload_bytes": _MAX_PAYLOAD_BYTES,
        "summary_hash": hashlib.sha256(encoded).hexdigest(),
    }


def _clean_summary(value: str | None) -> str:
    summary = (value or "").strip()
    if not summary:
        raise OpenClawProposalValidationError("summary_required")
    return summary[:1000]


def _validate_side_effect_route(route: str | None) -> str | None:
    if route is None:
        return None
    route_text = route.strip()
    if not route_text:
        return None
    lowered = route_text.lower()
    if any(fragment in lowered for fragment in _FORBIDDEN_SIDE_EFFECT_FRAGMENTS):
        raise OpenClawProposalValidationError("forbidden_side_effect_route")
    if not lowered.startswith("/api/v1/governance/"):
        raise OpenClawProposalValidationError("unsupported_side_effect_route")
    return route_text


def _proposal_id(*, source: str, channel: str, request_id: str) -> str:
    return "prop_" + _json_hash(
        {
            "source": source,
            "channel": channel,
            "request_id": request_id,
        }
    )


def _approval_id(*, proposal_id: str, request_id: str, decision: str) -> str:
    return "appr_" + _json_hash(
        {
            "proposal_id": proposal_id,
            "request_id": request_id,
            "decision": decision,
        }
    )


def _channel_event_id(
    *,
    request_id: str,
    channel: str,
    event_type: str,
    linked_proposal_id: str | None,
) -> str:
    return "chan_" + _json_hash(
        {
            "request_id": request_id,
            "channel": channel,
            "event_type": event_type,
            "linked_proposal_id": linked_proposal_id,
        }
    )


def _fetch_one_dict(cur: Any) -> dict[str, Any] | None:
    row = cur.fetchone()
    if row is None:
        return None
    names = [item[0] for item in cur.description]
    out = dict(zip(names, row, strict=False))
    for key in ("created_by", "evidence_refs", "payload", "actor", "governance_result_ref"):
        if key in out:
            out[key] = _details_dict(out[key]) if key != "evidence_refs" else out[key]
    return out


def _fetch_all_dicts(cur: Any) -> list[dict[str, Any]]:
    rows = list(cur.fetchall() or [])
    names = [item[0] for item in cur.description]
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(zip(names, row, strict=False))
        for key in (
            "created_by",
            "payload",
            "actor",
            "governance_result_ref",
        ):
            if key in item:
                item[key] = _details_dict(item[key])
        out.append(item)
    return out


def _proposal_columns() -> str:
    return """
        proposal_id,
        request_id,
        created_at_ms,
        created_by,
        proposal_type,
        risk_class,
        status,
        summary,
        evidence_refs,
        required_approval_class,
        operator_action_required,
        expires_at_ms,
        linked_diagnosis_id,
        linked_escalation_id,
        side_effect_route,
        payload
    """


def _approval_columns() -> str:
    return """
        approval_id,
        proposal_id,
        request_id,
        decision,
        decided_at_ms,
        actor,
        auth_result,
        reason,
        delegated_route,
        governance_result_ref
    """


class OpenClawProposalStore:
    def _execute(self, fn: Any) -> Any:
        with get_pg_conn() as conn:
            if conn is None:
                raise OpenClawProposalStoreUnavailable("pg_unavailable")
            try:
                cur = conn.cursor()
                cur.execute("SET LOCAL statement_timeout = %s", (_STATEMENT_TIMEOUT_MS,))
                result = fn(cur)
                conn.commit()
                return result
            except OpenClawProposalValidationError:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise
            except Exception as exc:  # noqa: BLE001 - route converts to 503
                try:
                    conn.rollback()
                except Exception:
                    pass
                logger.warning("openclaw proposal store operation failed: %s", exc)
                raise OpenClawProposalStoreUnavailable(type(exc).__name__) from exc

    def list_proposals(self, *, limit: int = 50) -> tuple[dict[str, Any], str | None]:
        ledger: dict[str, Any] = {
            "source_table": "openclaw.proposals",
            "available": False,
            "items": [],
            "recent_count": 0,
        }

        def _op(cur: Any) -> dict[str, Any]:
            cur.execute("SELECT to_regclass(%s) IS NOT NULL", ("openclaw.proposals",))
            row = cur.fetchone()
            if not row or not row[0]:
                ledger["missing_table"] = "openclaw.proposals"
                return ledger
            cur.execute(
                f"""
                SELECT {_proposal_columns()}
                  FROM openclaw.proposals
                 ORDER BY created_at_ms DESC
                 LIMIT %s
                """,
                (int(limit),),
            )
            items = _fetch_all_dicts(cur)
            ledger.update(
                {
                    "available": True,
                    "items": items,
                    "recent_count": len(items),
                }
            )
            return ledger

        try:
            result = self._execute(_op)
            if result.get("missing_table"):
                return result, "openclaw_proposal_ledger_unavailable:missing_table"
            return result, None
        except OpenClawProposalStoreUnavailable as exc:
            return ledger, f"openclaw_proposal_ledger_unavailable:{exc}"

    def create_proposal(
        self,
        *,
        request_context: dict[str, Any],
        actor: dict[str, Any],
        proposal_type: str,
        risk_class: str,
        summary: str,
        evidence_refs: list[dict[str, Any]],
        required_approval_class: str,
        expires_at_ms: int | None,
        linked_diagnosis_id: str | None,
        linked_escalation_id: str | None,
        side_effect_route: str | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        request_id = str(request_context.get("request_id") or "").strip()
        source = str(request_context.get("source") or "").strip()
        channel = str(request_context.get("channel") or "").strip()
        if not request_id or not source or not channel:
            raise OpenClawProposalValidationError("request_context_required")
        if not evidence_refs:
            raise OpenClawProposalValidationError("evidence_refs_required")
        now = _now_ms()
        if required_approval_class != "none" and (expires_at_ms is None or expires_at_ms <= now):
            raise OpenClawProposalValidationError("future_expiry_required")
        clean_route = _validate_side_effect_route(side_effect_route)
        clean_summary = _clean_summary(summary)
        proposal_id = _proposal_id(source=source, channel=channel, request_id=request_id)
        status = "visible" if required_approval_class == "none" else "pending_approval"
        operator_action_required = required_approval_class != "none"
        created_by = {
            "source": source,
            "channel": channel,
            "sender": request_context.get("sender"),
            "auth_profile": request_context.get("auth_profile"),
            "actor": actor,
        }
        safe_payload = _bounded_payload(payload or {})
        safe_refs = _bounded_payload(evidence_refs)

        def _op(cur: Any) -> dict[str, Any]:
            cur.execute(
                f"""
                INSERT INTO openclaw.proposals (
                    proposal_id,
                    source,
                    channel,
                    request_id,
                    created_at_ms,
                    created_by,
                    proposal_type,
                    risk_class,
                    status,
                    summary,
                    evidence_refs,
                    required_approval_class,
                    operator_action_required,
                    expires_at_ms,
                    linked_diagnosis_id,
                    linked_escalation_id,
                    side_effect_route,
                    payload
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (source, channel, request_id) DO NOTHING
                RETURNING {_proposal_columns()}
                """,
                (
                    proposal_id,
                    source,
                    channel,
                    request_id,
                    now,
                    _json_param(created_by),
                    proposal_type,
                    risk_class,
                    status,
                    clean_summary,
                    _json_param(safe_refs),
                    required_approval_class,
                    operator_action_required,
                    expires_at_ms,
                    linked_diagnosis_id,
                    linked_escalation_id,
                    clean_route,
                    _json_param(safe_payload),
                ),
            )
            inserted = _fetch_one_dict(cur)
            if inserted is not None:
                self._record_channel_event(
                    cur,
                    request_context=request_context,
                    event_type="proposal_created",
                    linked_proposal_id=proposal_id,
                    linked_escalation_id=linked_escalation_id,
                    payload_summary=clean_summary,
                )
                return inserted
            cur.execute(
                f"""
                SELECT {_proposal_columns()}
                  FROM openclaw.proposals
                 WHERE source = %s AND channel = %s AND request_id = %s
                """,
                (source, channel, request_id),
            )
            existing = _fetch_one_dict(cur)
            if existing is None:
                raise OpenClawProposalStoreUnavailable("idempotent_readback_failed")
            return existing

        return self._execute(_op)

    def decide_proposal(
        self,
        *,
        proposal_id: str,
        request_context: dict[str, Any],
        actor: dict[str, Any],
        action: str,
        reason: str | None,
    ) -> dict[str, Any] | None:
        if action not in {"approve", "reject"}:
            raise OpenClawProposalValidationError("unsupported_decision")
        request_id = str(request_context.get("request_id") or "").strip()
        if not request_id:
            raise OpenClawProposalValidationError("request_context_required")
        clean_reason = (reason or "").strip()[:1000] or None
        decided_at_ms = _now_ms()

        def _op(cur: Any) -> dict[str, Any] | None:
            cur.execute(
                f"""
                SELECT {_approval_columns()}
                  FROM openclaw.approval_decisions
                 WHERE proposal_id = %s AND request_id = %s
                """,
                (proposal_id, request_id),
            )
            existing_decision = _fetch_one_dict(cur)
            if existing_decision is not None:
                return existing_decision

            cur.execute(
                f"""
                SELECT {_proposal_columns()},
                       proposal_type,
                       risk_class,
                       required_approval_class
                  FROM openclaw.proposals
                 WHERE proposal_id = %s
                 FOR UPDATE
                """,
                (proposal_id,),
            )
            proposal = _fetch_one_dict(cur)
            if proposal is None:
                return None

            decision = "rejected" if action == "reject" else "approved"
            auth_result = "authenticated"
            delegated_route = None
            governance_result_ref: dict[str, Any] | None = {
                "status": "not_delegated",
                "reason": "openclaw_p1_approval_relay_records_decision_only",
            }
            next_status = "rejected" if action == "reject" else "approved"
            if action == "approve":
                expires_at_ms = proposal.get("expires_at_ms")
                if expires_at_ms is not None and int(expires_at_ms) <= decided_at_ms:
                    decision = "expired"
                    next_status = "expired"
                    governance_result_ref = None
                elif not self._approval_can_complete_without_delegation(proposal):
                    decision = "denied"
                    next_status = str(proposal.get("status") or "pending_approval")
                    governance_result_ref = {
                        "status": "blocked",
                        "reason": "side_effect_delegation_not_enabled",
                    }
            approval_id = _approval_id(
                proposal_id=proposal_id,
                request_id=request_id,
                decision=decision,
            )
            cur.execute(
                f"""
                INSERT INTO openclaw.approval_decisions (
                    approval_id,
                    proposal_id,
                    request_id,
                    decision,
                    decided_at_ms,
                    actor,
                    auth_result,
                    reason,
                    delegated_route,
                    governance_result_ref
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (proposal_id, request_id) DO NOTHING
                RETURNING {_approval_columns()}
                """,
                (
                    approval_id,
                    proposal_id,
                    request_id,
                    decision,
                    decided_at_ms,
                    _json_param(actor),
                    auth_result,
                    clean_reason,
                    delegated_route,
                    _json_param(governance_result_ref) if governance_result_ref is not None else None,
                ),
            )
            approval = _fetch_one_dict(cur)
            if approval is None:
                cur.execute(
                    f"""
                    SELECT {_approval_columns()}
                      FROM openclaw.approval_decisions
                     WHERE proposal_id = %s AND request_id = %s
                    """,
                    (proposal_id, request_id),
                )
                approval = _fetch_one_dict(cur)
            if approval is None:
                raise OpenClawProposalStoreUnavailable("approval_readback_failed")

            if next_status != proposal.get("status"):
                cur.execute(
                    """
                    UPDATE openclaw.proposals
                       SET status = %s
                     WHERE proposal_id = %s
                    """,
                    (next_status, proposal_id),
                )
            self._record_channel_event(
                cur,
                request_context=request_context,
                event_type="approval_intent",
                linked_proposal_id=proposal_id,
                linked_escalation_id=proposal.get("linked_escalation_id"),
                payload_summary=f"{action}:{decision}",
            )
            return approval

        return self._execute(_op)

    def _approval_can_complete_without_delegation(self, proposal: dict[str, Any]) -> bool:
        return (
            proposal.get("proposal_type") in _SAFE_APPROVAL_TYPES
            and proposal.get("risk_class") in _SAFE_APPROVAL_RISK_CLASSES
            and not proposal.get("side_effect_route")
            and proposal.get("required_approval_class") in {"operator", "none"}
        )

    def _record_channel_event(
        self,
        cur: Any,
        *,
        request_context: dict[str, Any],
        event_type: str,
        linked_proposal_id: str | None,
        linked_escalation_id: str | None,
        payload_summary: str,
    ) -> None:
        request_id = str(request_context.get("request_id") or "")
        channel = str(request_context.get("channel") or "gateway_internal")
        event_id = _channel_event_id(
            request_id=request_id,
            channel=channel,
            event_type=event_type,
            linked_proposal_id=linked_proposal_id,
        )
        cur.execute(
            """
            INSERT INTO openclaw.channel_events (
                channel_event_id,
                request_id,
                ts_ms,
                direction,
                channel,
                sender,
                auth_profile,
                event_type,
                status,
                linked_proposal_id,
                linked_escalation_id,
                payload_summary
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (channel_event_id) DO NOTHING
            """,
            (
                event_id,
                request_id,
                _now_ms(),
                "inbound",
                channel,
                str(request_context.get("sender") or ""),
                str(request_context.get("auth_profile") or "read_only"),
                event_type,
                "persisted",
                linked_proposal_id,
                linked_escalation_id,
                payload_summary[:1000],
            ),
        )
