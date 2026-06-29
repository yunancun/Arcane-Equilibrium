#!/usr/bin/env python3
"""Wrap learning lane artifacts into hashed no-authority LearningEvents.

The contract preserves the current artifact ``probe_ledger.jsonl`` SSOT while
adding a deterministic event envelope for downstream review. It does not query
or write PG, call Bybit, submit orders, mutate runtime state, lower Cost Gate,
or grant probe/order/live authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from cost_gate_learning_lane.contract import (
    BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE,
    PROBE_ADMISSION_DECISION_RECORD_TYPE,
    PROBE_OUTCOME_RECORD_TYPE,
)


SCHEMA_VERSION = "cost_gate_learning_event_contract_v1"
EVENT_SCHEMA_VERSION = "cost_gate_learning_event_v1"
READY_STATUS = "LEARNING_EVENT_CONTRACT_READY_NO_AUTHORITY"
READY_WITH_QUARANTINE_STATUS = (
    "LEARNING_EVENT_CONTRACT_READY_WITH_QUARANTINE_NO_AUTHORITY"
)
INPUT_MISSING_STATUS = "LEARNING_EVENT_CONTRACT_INPUT_MISSING"
BLOCKED_STATUS = "LEARNING_EVENT_CONTRACT_BLOCKED"
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

BOUNDARY = (
    "artifact-only LearningEvent contract; preserves artifact probe_ledger.jsonl "
    "as current learning SSOT; no PG query/write, Bybit call, order, config, "
    "risk, auth, runtime mutation, Cost Gate lowering, probe authority, order "
    "authority, live authority, or promotion proof"
)

AUTHORITY_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "adapter_enabled",
    "bounded_demo_probe_authorized",
    "bybit_call_performed",
    "bybit_private_call_performed",
    "bybit_public_market_data_call_performed",
    "cap_envelope_mutation_allowed",
    "crontab_mutation_performed",
    "demo_mutation_authority_granted",
    "env_mutation_performed",
    "exchange_call_performed",
    "global_cost_gate_lowering_recommended",
    "live_authority_granted",
    "mutation_enabled",
    "order_authority_granted",
    "order_cancel_performed",
    "order_modify_performed",
    "order_submission_performed",
    "operator_authorization_object_emitted",
    "pg_query_performed",
    "pg_write_performed",
    "plan_mutation_performed",
    "probe_authority_granted",
    "promotion_evidence",
    "promotion_proof",
    "risk_mutation_performed",
    "runtime_mutation_performed",
    "service_restart_performed",
    "writer_enabled",
}
AUTHORITY_TEXT_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "bounded_demo_probe_authority",
    "live_authority",
    "order_authority",
    "probe_authority",
}
SAFE_AUTHORITY_TEXT_VALUES = {
    "",
    "NONE",
    "NOT_GRANTED",
    "NOT_AUTHORIZED",
    "REVIEW_REQUIRED",
    "REVIEW_REQUIRED_NO_AUTHORITY",
    "INACTIVE_REVIEW_PACKET_ONLY",
}
TRUTHY_AUTHORITY_STRINGS = {
    "1",
    "true",
    "yes",
    "y",
    "on",
    "enabled",
    "grant",
    "granted",
    "authorize",
    "authorized",
}


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return str(value or "").strip()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _truthy_authority(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in TRUTHY_AUTHORITY_STRINGS
    return False


def _parse_utc(value: Any) -> dt.datetime | None:
    text = _str(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _iso_from_ms(value: Any) -> str | None:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return dt.datetime.fromtimestamp(parsed / 1000, tz=dt.timezone.utc).isoformat()


def _source_generated_at(payload: dict[str, Any]) -> str | None:
    event = _dict(payload.get("event"))
    for value in (
        payload.get("generated_at_utc"),
        payload.get("generated_at"),
        payload.get("timestamp_utc"),
        payload.get("ts_utc"),
        event.get("generated_at_utc"),
        event.get("timestamp_utc"),
        event.get("ts_utc"),
    ):
        parsed = _parse_utc(value)
        if parsed is not None:
            return parsed.isoformat()
    for value in (
        payload.get("generated_at_ms"),
        payload.get("event_ts_ms"),
        payload.get("ts_ms"),
        event.get("ts_ms"),
    ):
        rendered = _iso_from_ms(value)
        if rendered:
            return rendered
    return None


def _containers(payload: dict[str, Any]) -> list[dict[str, Any]]:
    containers = [payload]
    for key in (
        "event",
        "candidate",
        "candidate_identity",
        "candidate_summary",
        "proposal",
        "source_candidate",
        "selected_candidate",
    ):
        item = _dict(payload.get(key))
        if item:
            containers.append(item)
    return containers


def _first_value(payload: dict[str, Any], *keys: str) -> Any:
    for container in _containers(payload):
        for key in keys:
            value = container.get(key)
            if value not in (None, ""):
                return value
    return None


def _candidate_identity(payload: dict[str, Any]) -> dict[str, Any]:
    side_cell_key = _str(
        _first_value(payload, "side_cell_key", "selected_side_cell_key", "candidate_id")
    )
    strategy_name = _str(_first_value(payload, "strategy_name", "strategy"))
    symbol = _str(_first_value(payload, "symbol")).upper()
    side = _str(_first_value(payload, "side"))

    if side_cell_key and side_cell_key.count("|") >= 2:
        parts = side_cell_key.split("|")
        strategy_name = strategy_name or parts[0]
        symbol = symbol or parts[1].upper()
        side = side or parts[2]
    if not side_cell_key and strategy_name and symbol and side:
        side_cell_key = "|".join([strategy_name, symbol, side])

    return {
        "candidate_id": side_cell_key,
        "side_cell_key": side_cell_key,
        "strategy_name": strategy_name,
        "symbol": symbol,
        "side": side,
        "outcome_horizon_minutes": _first_value(
            payload,
            "outcome_horizon_minutes",
            "learning_outcome_horizon_minutes",
            "dominant_horizon_minutes",
        ),
    }


def _event_type(payload: dict[str, Any], *, source_kind: str) -> str:
    record_type = _str(payload.get("record_type"))
    if record_type:
        return record_type
    schema_version = _str(payload.get("schema_version"))
    if schema_version:
        return schema_version
    return "artifact_payload" if source_kind == "artifact_json" else "ledger_payload"


def _proof_tier(payload: dict[str, Any], event_type: str) -> str:
    outcome_source = _str(payload.get("outcome_source"))
    if (
        event_type == BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE
        or outcome_source == "market_markout_proxy_for_blocked_signal"
    ):
        return "blocked_markout_proxy"
    if event_type == PROBE_OUTCOME_RECORD_TYPE:
        if outcome_source == "market_markout_proxy":
            return "probe_markout_proxy_not_fill_proof"
        return "probe_outcome_review_only"
    if event_type == PROBE_ADMISSION_DECISION_RECORD_TYPE:
        return "admission_decision_not_outcome"
    return "artifact_review_only"


def _authority_violations(payload: Any) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    stack: list[tuple[str, Any]] = [("$", payload)]
    while stack:
        path, item = stack.pop()
        if isinstance(item, list):
            for index, value in enumerate(item):
                stack.append((f"{path}[{index}]", value))
            continue
        data = _dict(item)
        if not data:
            continue
        for key, value in data.items():
            item_path = f"{path}.{key}"
            if key == "main_cost_gate_adjustment" and value not in (None, "", "NONE"):
                violations.append(
                    {
                        "path": item_path,
                        "key": key,
                        "reason": "main_cost_gate_adjustment_not_none",
                    }
                )
            elif key in AUTHORITY_TRUE_KEYS and _truthy_authority(value):
                violations.append(
                    {
                        "path": item_path,
                        "key": key,
                        "reason": "authority_truthy_value",
                    }
                )
            elif key in AUTHORITY_TEXT_KEYS:
                text = _str(value).upper()
                if text and text not in SAFE_AUTHORITY_TEXT_VALUES:
                    violations.append(
                        {
                            "path": item_path,
                            "key": key,
                            "reason": "authority_text_not_explicitly_not_granted",
                        }
                    )
            if isinstance(value, (dict, list)):
                stack.append((item_path, value))
    return violations


def _quarantine(
    *,
    source_kind: str,
    path: Path | None,
    reason: str,
    line_no: int | None = None,
    row_sha256: str | None = None,
    source_sha256: str | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    return {
        "source_kind": source_kind,
        "path": str(path) if path else None,
        "line_no": line_no,
        "reason": reason,
        "detail": detail,
        "source_sha256": source_sha256,
        "row_sha256": row_sha256,
        "quarantine_sha256": _sha256_text(
            _canonical_json(
                {
                    "source_kind": source_kind,
                    "path": str(path) if path else None,
                    "line_no": line_no,
                    "reason": reason,
                    "detail": detail,
                    "source_sha256": source_sha256,
                    "row_sha256": row_sha256,
                }
            )
        ),
    }


def _source_ref(
    *,
    source_kind: str,
    path: Path | None,
    source_sha256: str | None,
    row_sha256: str,
    line_no: int | None = None,
    artifact_index: int | None = None,
) -> dict[str, Any]:
    return {
        "source_kind": source_kind,
        "path": str(path) if path else None,
        "line_no": line_no,
        "artifact_index": artifact_index,
        "source_sha256": source_sha256,
        "row_sha256": row_sha256,
    }


def _learning_event(
    *,
    payload: dict[str, Any],
    source_ref: dict[str, Any],
    source_generated_at_utc: str,
    emitted_at_utc: str,
) -> dict[str, Any]:
    event_type = _event_type(payload, source_kind=str(source_ref.get("source_kind")))
    candidate = _candidate_identity(payload)
    event_id_seed = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "event_type": event_type,
        "candidate_id": candidate.get("candidate_id"),
        "source_ref": source_ref,
    }
    event_id = "learning_event:" + _sha256_text(_canonical_json(event_id_seed))[:24]
    event = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "event_id": event_id,
        "event_type": event_type,
        "candidate_id": candidate.get("candidate_id"),
        "candidate_identity": candidate,
        "generated_at_utc": emitted_at_utc,
        "source_generated_at_utc": source_generated_at_utc,
        "proof_tier": _proof_tier(payload, event_type),
        "source_refs": [source_ref],
        "source_payload_sha256": source_ref.get("row_sha256"),
        "source_schema_version": payload.get("schema_version"),
        "source_record_type": payload.get("record_type"),
        "source_status": payload.get("status"),
        "no_authority": {
            "runtime_mutation_performed": False,
            "pg_write_performed": False,
            "bybit_call_performed": False,
            "order_submission_performed": False,
            "cost_gate_lowering_allowed": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "live_authority_granted": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
    }
    event["event_packet_sha256"] = _sha256_text(_canonical_json(event))
    return event


def _event_or_quarantine(
    *,
    payload: dict[str, Any],
    source_ref: dict[str, Any],
    emitted_at_utc: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    source_generated_at_utc = _source_generated_at(payload)
    if source_generated_at_utc is None:
        return None, _quarantine(
            source_kind=str(source_ref.get("source_kind")),
            path=Path(str(source_ref.get("path"))) if source_ref.get("path") else None,
            line_no=source_ref.get("line_no"),
            row_sha256=source_ref.get("row_sha256"),
            source_sha256=source_ref.get("source_sha256"),
            reason="missing_or_unparseable_generated_timestamp",
        )
    candidate = _candidate_identity(payload)
    if not candidate.get("candidate_id"):
        return None, _quarantine(
            source_kind=str(source_ref.get("source_kind")),
            path=Path(str(source_ref.get("path"))) if source_ref.get("path") else None,
            line_no=source_ref.get("line_no"),
            row_sha256=source_ref.get("row_sha256"),
            source_sha256=source_ref.get("source_sha256"),
            reason="missing_candidate_identity",
        )
    return _learning_event(
        payload=payload,
        source_ref=source_ref,
        source_generated_at_utc=source_generated_at_utc,
        emitted_at_utc=emitted_at_utc,
    ), None


def _read_probe_ledger_events(
    path: Path | None,
    *,
    emitted_at_utc: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if path is None:
        return [], [], [], {
            "present": False,
            "path": None,
            "source_sha256": None,
            "line_count": 0,
            "parsed_object_count": 0,
            "event_count": 0,
            "quarantine_count": 0,
            "source_error": "missing_path",
        }
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return [], [], [], {
            "present": False,
            "path": str(path),
            "source_sha256": None,
            "line_count": 0,
            "parsed_object_count": 0,
            "event_count": 0,
            "quarantine_count": 0,
            "source_error": "missing",
        }
    source_sha256 = _sha256_bytes(raw)
    rows: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    for line_no, raw_line in enumerate(raw.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue
        row_sha256 = _sha256_bytes(stripped)
        try:
            payload = json.loads(stripped.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            quarantine.append(
                _quarantine(
                    source_kind="probe_ledger_jsonl",
                    path=path,
                    line_no=line_no,
                    row_sha256=row_sha256,
                    source_sha256=source_sha256,
                    reason="malformed_jsonl",
                    detail=f"{type(exc).__name__}:{exc}",
                )
            )
            continue
        if not isinstance(payload, dict):
            quarantine.append(
                _quarantine(
                    source_kind="probe_ledger_jsonl",
                    path=path,
                    line_no=line_no,
                    row_sha256=row_sha256,
                    source_sha256=source_sha256,
                    reason="jsonl_row_not_object",
                )
            )
            continue
        rows.append(payload)
        source_ref = _source_ref(
            source_kind="probe_ledger_jsonl",
            path=path,
            source_sha256=source_sha256,
            row_sha256=row_sha256,
            line_no=line_no,
        )
        event, quarantined = _event_or_quarantine(
            payload=payload,
            source_ref=source_ref,
            emitted_at_utc=emitted_at_utc,
        )
        if event:
            events.append(event)
        if quarantined:
            quarantine.append(quarantined)
    return rows, events, quarantine, {
        "present": True,
        "path": str(path),
        "source_sha256": source_sha256,
        "line_count": len(raw.splitlines()),
        "parsed_object_count": len(rows),
        "event_count": len(events),
        "quarantine_count": len(quarantine),
        "source_error": None,
    }


def _artifact_payloads_from_path(
    path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return [], [
            _quarantine(
                source_kind="artifact_json",
                path=path,
                reason="missing",
            )
        ], {
            "present": False,
            "path": str(path),
            "source_sha256": None,
            "artifact_object_count": 0,
            "source_error": "missing",
        }
    source_sha256 = _sha256_bytes(raw)
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [], [
            _quarantine(
                source_kind="artifact_json",
                path=path,
                reason="malformed_json",
                source_sha256=source_sha256,
                detail=f"{type(exc).__name__}:{exc}",
            )
        ], {
            "present": True,
            "path": str(path),
            "source_sha256": source_sha256,
            "artifact_object_count": 0,
            "source_error": "malformed_json",
        }
    if isinstance(parsed, dict):
        payloads = [parsed]
    elif isinstance(parsed, list):
        payloads = [item for item in parsed if isinstance(item, dict)]
    else:
        payloads = []
    quarantine = []
    if not payloads:
        quarantine.append(
            _quarantine(
                source_kind="artifact_json",
                path=path,
                reason="json_artifact_not_object_or_object_array",
                source_sha256=source_sha256,
            )
        )
    return payloads, quarantine, {
        "present": True,
        "path": str(path),
        "source_sha256": source_sha256,
        "artifact_object_count": len(payloads),
        "source_error": None if payloads else "not_object",
    }


def _read_artifact_events(
    artifact_paths: list[Path],
    *,
    emitted_at_utc: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    payloads: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for path in artifact_paths:
        path_payloads, path_quarantine, summary = _artifact_payloads_from_path(path)
        payloads.extend(path_payloads)
        quarantine.extend(path_quarantine)
        summaries.append(summary)
        source_sha256 = summary.get("source_sha256")
        for index, payload in enumerate(path_payloads):
            row_sha256 = _sha256_text(_canonical_json(payload))
            source_ref = _source_ref(
                source_kind="artifact_json",
                path=path,
                source_sha256=source_sha256,
                row_sha256=row_sha256,
                artifact_index=index,
            )
            event, quarantined = _event_or_quarantine(
                payload=payload,
                source_ref=source_ref,
                emitted_at_utc=emitted_at_utc,
            )
            if event:
                events.append(event)
            if quarantined:
                quarantine.append(quarantined)
    return payloads, events, quarantine, summaries


def _answer_flags(status: str) -> dict[str, Any]:
    ready = status in {READY_STATUS, READY_WITH_QUARANTINE_STATUS}
    return {
        "learning_event_contract_ready": ready,
        "current_jsonl_ssot_preserved": True,
        "pg_backed_cutover_ready": False,
        "mutation_enabled": False,
        "demo_mutation_authority_granted": False,
        "cost_gate_lowering_allowed": False,
        "global_cost_gate_lowering_recommended": False,
        "main_cost_gate_adjustment": "NONE",
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "active_runtime_probe_authority": False,
        "active_runtime_order_authority": False,
        "live_authority_granted": False,
        "operator_authorization_object_emitted": False,
        "promotion_evidence": False,
        "promotion_proof": False,
        "runtime_mutation_required": False,
        "runtime_mutation_performed": False,
        "pg_query_performed": False,
        "pg_write_required": False,
        "pg_write_performed": False,
        "bybit_call_required": False,
        "bybit_call_performed": False,
        "order_submission_performed": False,
    }


def build_learning_event_contract(
    *,
    probe_ledger_jsonl: Path | None = None,
    artifact_json_paths: list[Path] | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    """Build a no-authority LearningEvent envelope contract from artifacts."""
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    emitted_at_utc = now.isoformat()
    artifact_paths = artifact_json_paths or []
    ledger_rows, ledger_events, ledger_quarantine, ledger_summary = (
        _read_probe_ledger_events(probe_ledger_jsonl, emitted_at_utc=emitted_at_utc)
    )
    artifact_payloads, artifact_events, artifact_quarantine, artifact_summaries = (
        _read_artifact_events(artifact_paths, emitted_at_utc=emitted_at_utc)
    )
    payloads = [*ledger_rows, *artifact_payloads]
    events = [*ledger_events, *artifact_events]
    quarantine = [*ledger_quarantine, *artifact_quarantine]
    authority_violations = []
    for payload in payloads:
        authority_violations.extend(_authority_violations(payload))

    source_count = int(ledger_summary.get("present") is True) + sum(
        1 for summary in artifact_summaries if summary.get("present") is True
    )
    if authority_violations:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "source_artifact_claimed_authority_or_cost_gate_mutation"
        events = []
    elif source_count == 0:
        status = INPUT_MISSING_STATUS
        reason = "no_probe_ledger_or_artifact_json_input_present"
    elif not events:
        status = BLOCKED_STATUS
        reason = "no_valid_learning_events_after_quarantine"
    elif quarantine:
        status = READY_WITH_QUARANTINE_STATUS
        reason = "valid_learning_events_present_with_malformed_events_quarantined"
    else:
        status = READY_STATUS
        reason = "learning_events_wrapped_from_artifact_sources"

    event_packet_sha256s = [event["event_packet_sha256"] for event in events]
    contract_sha256 = _sha256_text(
        _canonical_json(
            {
                "schema_version": SCHEMA_VERSION,
                "event_packet_sha256s": event_packet_sha256s,
                "quarantine_sha256s": [
                    item.get("quarantine_sha256") for item in quarantine
                ],
                "authority_violation_count": len(authority_violations),
            }
        )
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": emitted_at_utc,
        "status": status,
        "reason": reason,
        "contract_sha256": contract_sha256,
        "current_learning_ssot": "artifact_probe_ledger_jsonl",
        "target_learning_ssot": "pg_backed_cost_gate_learning_ledger",
        "event_schema_version": EVENT_SCHEMA_VERSION,
        "summary": {
            "source_count": source_count,
            "event_count": len(events),
            "quarantine_count": len(quarantine),
            "authority_violation_count": len(authority_violations),
            "blocked_markout_proxy_event_count": sum(
                1 for event in events if event.get("proof_tier") == "blocked_markout_proxy"
            ),
            "current_jsonl_ssot_preserved": True,
            "pg_backed_cutover_ready": False,
        },
        "sources": {
            "probe_ledger_jsonl": ledger_summary,
            "artifact_json": artifact_summaries,
        },
        "events": events,
        "quarantine": {
            "malformed_event_count": len(quarantine),
            "events": quarantine,
        },
        "authority_violations": authority_violations,
        "answers": _answer_flags(status),
        "next_actions": (
            [
                "remove_authority_bearing_input_and_rerun_learning_event_contract",
                "operator_review_authority_boundary_violation_before_any_learning_cutover",
            ]
            if status == AUTHORITY_BOUNDARY_VIOLATION_STATUS
            else [
                "preserve_artifact_probe_ledger_jsonl_as_learning_ssot",
                "feed_learning_events_to_source_only_proposal_compiler_after_quarantine_review",
                "do_not_start_pg_backed_cutover_until_schema_writer_reconstruction_and_operator_review_pass",
            ]
        ),
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    summary = _dict(packet.get("summary"))
    answers = _dict(packet.get("answers"))
    lines = [
        "# Cost Gate LearningEvent Contract",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Events: `{summary.get('event_count')}`",
        f"- Quarantined: `{summary.get('quarantine_count')}`",
        f"- Blocked markout proxy events: `{summary.get('blocked_markout_proxy_event_count')}`",
        f"- Current learning SSOT: `{packet.get('current_learning_ssot')}`",
        f"- PG cutover ready: `{summary.get('pg_backed_cutover_ready')}`",
        f"- Order authority granted: `{answers.get('order_authority_granted')}`",
        f"- Boundary: {packet.get('boundary')}",
        "",
        "## Events",
        "",
        "| event_id | type | candidate | proof_tier | source |",
        "|---|---|---|---|---|",
    ]
    for event in _list(packet.get("events")):
        source_ref = _dict(_list(event.get("source_refs"))[0] if event.get("source_refs") else {})
        lines.append(
            f"| `{event.get('event_id')}` | `{event.get('event_type')}` | "
            f"`{event.get('candidate_id')}` | `{event.get('proof_tier')}` | "
            f"`{source_ref.get('source_kind')}` |"
        )
    lines.extend(["", "## No-Authority Answers", ""])
    for key, value in answers.items():
        lines.append(f"- `{key}`: `{value}`")
    return "\n".join(lines) + "\n"


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe-ledger-jsonl", type=Path)
    parser.add_argument("--artifact-json", type=Path, action="append", default=[])
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_learning_event_contract(
        probe_ledger_jsonl=args.probe_ledger_jsonl,
        artifact_json_paths=args.artifact_json,
    )
    markdown = render_markdown(packet)
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.output:
        _write_text(args.output, markdown)
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True, default=str))
    elif not args.output and not args.json_output:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
