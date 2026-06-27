from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "current_candidate_runtime_admission_handoff_review_v1"
ADMISSION_ENVELOPE_PREVIEW_SCHEMA_VERSION = (
    "current_candidate_runtime_admission_envelope_preview_v1"
)

REFRESH_SCHEMA_VERSION = "current_candidate_public_quote_construction_refresh_v1"
PUBLIC_QUOTE_SCHEMA_VERSION = "current_candidate_public_quote_capture_v1"
MARKET_SNAPSHOT_SCHEMA_VERSION = "current_candidate_public_quote_market_snapshot_v1"
CONSTRUCTION_PREVIEW_SCHEMA_VERSION = "current_candidate_no_order_construction_preview_v1"
CURRENT_ENVELOPE_SCHEMA_VERSION = "cost_gate_current_candidate_no_order_refresh_envelope_v1"

REFRESH_READY_STATUS = "CURRENT_CANDIDATE_PUBLIC_QUOTE_CONSTRUCTION_REFRESH_READY_NO_ORDER"
PUBLIC_QUOTE_READY_STATUS = "CURRENT_CANDIDATE_PUBLIC_QUOTE_READY_NO_ORDER"
MARKET_SNAPSHOT_READY_STATUS = "CURRENT_CANDIDATE_MARKET_SNAPSHOT_READY_NO_ORDER"
CONSTRUCTION_READY_STATUS = "CURRENT_CANDIDATE_CONSTRUCTION_PREVIEW_READY_NO_ORDER"
CURRENT_ENVELOPE_READY_STATUS = (
    "CURRENT_CANDIDATE_NO_ORDER_REFRESH_ENVELOPE_READY_NO_CAPTURE_NO_AUTHORITY"
)

READY_STATUS = "CURRENT_CANDIDATE_RUNTIME_ADMISSION_HANDOFF_READY_NO_ORDER"
NOT_READY_STATUS = "CURRENT_CANDIDATE_RUNTIME_ADMISSION_HANDOFF_NOT_READY"
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

DEFAULT_MAX_ARTIFACT_AGE_SECONDS = 60 * 60
DEFAULT_MAX_FRESH_BBO_AGE_MS = 1000

AUTHORITY_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "adapter_enabled_by_this_packet",
    "allowed_to_submit_order",
    "bounded_demo_probe_authorized",
    "canonical_plan_mutation_performed",
    "cap_envelope_mutation_allowed",
    "global_cost_gate_lowering_recommended",
    "latest_overwrite_performed",
    "ledger_append_performed",
    "live_authority_granted",
    "order_admission_ready",
    "order_authority_granted",
    "order_cancel_performed",
    "order_modify_performed",
    "order_or_probe_authority_granted",
    "order_submission_performed",
    "pg_write_performed",
    "plan_mutation_performed",
    "probe_authority_granted",
    "promotion_evidence",
    "promotion_proof",
    "risk_mutation_performed",
    "runtime_admission_ready",
    "runtime_mutation_performed",
    "service_restart_performed",
    "writer_enabled",
}

ORDER_OR_PRIVATE_PATH_TOKENS = (
    "/v5/order",
    "/v5/position",
    "/v5/account",
    "/v5/execution",
    "/v5/user",
    "/v5/private",
)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return value if isinstance(value, str) else str(value or "")


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_dt(value: Any) -> dt.datetime | None:
    text = _str(value).strip()
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


def _iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat()


def _sha256_path(path: Path | None) -> str | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _age_seconds(payload: dict[str, Any], *, now_utc: dt.datetime) -> float | None:
    parsed = _parse_dt(payload.get("generated_at_utc"))
    if parsed is None:
        return None
    age = (now_utc - parsed).total_seconds()
    return age if age >= 0.0 else None


def _artifact_summary(
    *,
    name: str,
    path: Path | None,
    payload: dict[str, Any],
    now_utc: dt.datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    age = _age_seconds(payload, now_utc=now_utc) if payload else None
    if not payload:
        status = "MISSING"
    elif age is None:
        status = "PRESENT_UNKNOWN_AGE"
    elif age > max_age_seconds:
        status = "STALE"
    else:
        status = "FRESH"
    return {
        "name": name,
        "path": str(path) if path else None,
        "sha256": _sha256_path(path),
        "status": status,
        "schema_version": payload.get("schema_version") if payload else None,
        "artifact_status": payload.get("status") if payload else None,
        "generated_at_utc": payload.get("generated_at_utc") if payload else None,
        "age_seconds": age,
        "max_age_seconds": max_age_seconds,
    }


def _candidate_key(candidate: dict[str, Any]) -> tuple[Any, Any, Any, Any, Any]:
    return (
        candidate.get("side_cell_key"),
        candidate.get("strategy_name"),
        candidate.get("symbol"),
        candidate.get("side"),
        candidate.get("outcome_horizon_minutes"),
    )


def _candidate_identity(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "side_cell_key": candidate.get("side_cell_key"),
        "strategy_name": candidate.get("strategy_name"),
        "symbol": candidate.get("symbol"),
        "side": candidate.get("side"),
        "outcome_horizon_minutes": candidate.get("outcome_horizon_minutes"),
    }


def _recursive_authority_violations(payload: Any, prefix: str = "") -> list[str]:
    reasons: list[str] = []
    if isinstance(payload, list):
        for idx, item in enumerate(payload):
            reasons.extend(_recursive_authority_violations(item, f"{prefix}[{idx}]"))
        return reasons
    if not isinstance(payload, dict):
        return reasons
    for key, value in payload.items():
        path = f"{prefix}.{key}" if prefix else key
        if key in AUTHORITY_TRUE_KEYS and value is True:
            reasons.append(f"{path}_true")
        if key == "main_cost_gate_adjustment" and value not in (None, "", "NONE"):
            reasons.append(f"{path}_not_none")
        if key == "order_authority" and value not in (None, "", "NOT_GRANTED"):
            reasons.append(f"{path}_not_not_granted")
        if isinstance(value, (dict, list)):
            reasons.extend(_recursive_authority_violations(value, path))
    return reasons


def _schema_status_gate(
    payload: dict[str, Any],
    *,
    schema_version: str,
    status: str,
    gate_name: str,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if payload.get("schema_version") != schema_version:
        reasons.append(f"{gate_name}_schema_version_invalid")
    if payload.get("status") != status:
        reasons.append(f"{gate_name}_status_not_ready")
    return not reasons, reasons


def _request_envelope_reasons(public_quote: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    endpoint = _dict(public_quote.get("endpoint_allowlist"))
    if endpoint.get("private_or_order_paths_allowed") is not False:
        reasons.append("public_quote_endpoint_allowlist_allows_private_or_order_paths")
    if endpoint.get("auth_or_cookie_headers_allowed") is not False:
        reasons.append("public_quote_endpoint_allowlist_allows_auth_or_cookie_headers")
    requests = _list(public_quote.get("requests"))
    if len(requests) != 3:
        reasons.append("public_quote_request_count_not_three")
    labels = {_str(request.get("label")) for request in requests}
    if labels != {"server_time", "ticker", "instrument"}:
        reasons.append("public_quote_request_labels_mismatch")
    for request in requests:
        envelope = _dict(request.get("request_envelope"))
        if envelope.get("method") != "GET":
            reasons.append("public_quote_non_get_request")
        path = _str(envelope.get("path")).lower()
        if any(token in path for token in ORDER_OR_PRIVATE_PATH_TOKENS):
            reasons.append("public_quote_private_or_order_path_present")
        if request.get("request_envelope_ok") is not True:
            reasons.append("public_quote_request_envelope_not_ok")
    return sorted(set(reasons))


def _cap_gate_reasons(
    *,
    refresh: dict[str, Any],
    current_envelope: dict[str, Any],
    construction_preview: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    summary = _dict(refresh.get("summary"))
    cap_resolution = _dict(current_envelope.get("cap_resolution"))
    construction = _dict(construction_preview.get("construction"))
    preview_limits = _dict(construction_preview.get("risk_limits"))
    resolved_cap = _float(summary.get("resolved_cap_usdt"))
    envelope_cap = _float(cap_resolution.get("resolved_cap_usdt"))
    construction_cap = _float(construction.get("cap_usdt"))
    preview_cap = _float(preview_limits.get("cap_usdt"))
    if resolved_cap is None or resolved_cap <= 0:
        reasons.append("resolved_cap_usdt_missing_or_non_positive")
    if envelope_cap is None or resolved_cap != envelope_cap:
        reasons.append("summary_cap_mismatch_current_envelope_cap")
    if construction_cap is None or resolved_cap != construction_cap:
        reasons.append("summary_cap_mismatch_construction_cap")
    if preview_cap is None or resolved_cap != preview_cap:
        reasons.append("summary_cap_mismatch_construction_risk_limits_cap")
    if summary.get("cap_source") != "current_candidate_envelope.cap_resolution.resolved_cap_usdt":
        reasons.append("cap_source_not_current_candidate_envelope_resolved_cap")
    if summary.get("gui_risk_config_is_source_of_truth") is not True:
        reasons.append("gui_risk_config_not_marked_source_of_truth")
    if summary.get("local_10_usdt_cap_is_global_risk_authority") is not False:
        reasons.append("local_10_usdt_cap_marked_global_authority")
    if cap_resolution.get("bounded_probe_local_cap_usdt_is_authority") is not False:
        reasons.append("bounded_probe_local_cap_marked_authority")
    return sorted(set(reasons))


def build_runtime_admission_handoff_review(
    *,
    refresh: dict[str, Any] | None,
    public_quote: dict[str, Any] | None,
    market_snapshot: dict[str, Any] | None,
    construction_preview: dict[str, Any] | None,
    current_envelope: dict[str, Any] | None,
    paths: dict[str, Path | None] | None = None,
    now_utc: dt.datetime | None = None,
    max_artifact_age_seconds: int = DEFAULT_MAX_ARTIFACT_AGE_SECONDS,
    max_fresh_bbo_age_ms: int = DEFAULT_MAX_FRESH_BBO_AGE_MS,
    source_head: str | None = None,
    runtime_head: str | None = None,
) -> dict[str, Any]:
    if max_artifact_age_seconds < 60 or max_artifact_age_seconds > 24 * 3600:
        raise ValueError("max_artifact_age_seconds must be in [60, 86400]")
    if max_fresh_bbo_age_ms <= 0 or max_fresh_bbo_age_ms > 5000:
        raise ValueError("max_fresh_bbo_age_ms must be in [1, 5000]")
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    paths = paths or {}
    refresh_payload = _dict(refresh)
    quote_payload = _dict(public_quote)
    snapshot_payload = _dict(market_snapshot)
    preview_payload = _dict(construction_preview)
    envelope_payload = _dict(current_envelope)

    artifacts = {
        "refresh": _artifact_summary(
            name="refresh",
            path=paths.get("refresh"),
            payload=refresh_payload,
            now_utc=now,
            max_age_seconds=max_artifact_age_seconds,
        ),
        "public_quote": _artifact_summary(
            name="public_quote",
            path=paths.get("public_quote"),
            payload=quote_payload,
            now_utc=now,
            max_age_seconds=max_artifact_age_seconds,
        ),
        "market_snapshot": _artifact_summary(
            name="market_snapshot",
            path=paths.get("market_snapshot"),
            payload=snapshot_payload,
            now_utc=now,
            max_age_seconds=max_artifact_age_seconds,
        ),
        "construction_preview": _artifact_summary(
            name="construction_preview",
            path=paths.get("construction_preview"),
            payload=preview_payload,
            now_utc=now,
            max_age_seconds=max_artifact_age_seconds,
        ),
        "current_envelope": _artifact_summary(
            name="current_envelope",
            path=paths.get("current_envelope"),
            payload=envelope_payload,
            now_utc=now,
            max_age_seconds=max_artifact_age_seconds,
        ),
    }

    reasons: list[str] = []
    for name, artifact in artifacts.items():
        if artifact["status"] != "FRESH":
            reasons.append(f"{name}_artifact_not_fresh")

    schema_gates = {}
    for name, payload, schema, status in (
        ("refresh", refresh_payload, REFRESH_SCHEMA_VERSION, REFRESH_READY_STATUS),
        ("public_quote", quote_payload, PUBLIC_QUOTE_SCHEMA_VERSION, PUBLIC_QUOTE_READY_STATUS),
        ("market_snapshot", snapshot_payload, MARKET_SNAPSHOT_SCHEMA_VERSION, MARKET_SNAPSHOT_READY_STATUS),
        ("construction_preview", preview_payload, CONSTRUCTION_PREVIEW_SCHEMA_VERSION, CONSTRUCTION_READY_STATUS),
        ("current_envelope", envelope_payload, CURRENT_ENVELOPE_SCHEMA_VERSION, CURRENT_ENVELOPE_READY_STATUS),
    ):
        ok, gate_reasons = _schema_status_gate(
            payload,
            schema_version=schema,
            status=status,
            gate_name=name,
        )
        schema_gates[name] = ok
        reasons.extend(gate_reasons)

    candidates = {
        "refresh": _candidate_identity(_dict(refresh_payload.get("candidate"))),
        "public_quote": _candidate_identity(_dict(quote_payload.get("candidate"))),
        "market_snapshot": _candidate_identity(_dict(snapshot_payload.get("candidate"))),
        "construction_preview": _candidate_identity(_dict(preview_payload.get("candidate"))),
        "current_envelope": _candidate_identity(_dict(envelope_payload.get("candidate"))),
    }
    candidate_keys = {_candidate_key(candidate) for candidate in candidates.values()}
    candidate_alignment = len(candidate_keys) == 1 and bool(next(iter(candidate_keys))[0])
    if not candidate_alignment:
        reasons.append("candidate_identity_alignment_failed")

    reasons.extend(_cap_gate_reasons(
        refresh=refresh_payload,
        current_envelope=envelope_payload,
        construction_preview=preview_payload,
    ))
    reasons.extend(_request_envelope_reasons(quote_payload))

    construction = _dict(preview_payload.get("construction"))
    summary = _dict(refresh_payload.get("summary"))
    quote_derived = _dict(quote_payload.get("derived"))
    bbo_age = _float(quote_derived.get("effective_bbo_age_ms"))
    if quote_derived.get("bbo_fresh") is not True:
        reasons.append("public_quote_bbo_not_fresh")
    if bbo_age is None or bbo_age > max_fresh_bbo_age_ms:
        reasons.append("public_quote_bbo_age_exceeds_gate")
    if construction.get("constructible") is not True:
        reasons.append("construction_not_constructible")
    if construction.get("rounded_notional_usdt") is None:
        reasons.append("construction_rounded_notional_missing")
    if summary.get("construction_constructible") is not True:
        reasons.append("refresh_summary_construction_not_constructible")

    authority_reasons: list[str] = []
    for name, payload in (
        ("refresh", refresh_payload),
        ("public_quote", quote_payload),
        ("market_snapshot", snapshot_payload),
        ("construction_preview", preview_payload),
        ("current_envelope", envelope_payload),
    ):
        authority_reasons.extend(
            f"{name}.{reason}" for reason in _recursive_authority_violations(payload)
        )
    if authority_reasons:
        reasons.extend(authority_reasons)

    handoff_ready = not reasons
    runtime_admission_blockers = [
        "bounded_demo_authorization_object_required",
        "decision_lease_required",
        "guardian_risk_gate_required",
        "rust_authority_path_required",
        "fresh_bbo_refresh_required_at_actual_order_admission",
    ]
    status = (
        AUTHORITY_BOUNDARY_VIOLATION_STATUS
        if authority_reasons
        else READY_STATUS if handoff_ready else NOT_READY_STATUS
    )
    candidate = candidates["refresh"] if candidates["refresh"].get("side_cell_key") else {}
    admission_envelope_preview = {
        "schema_version": ADMISSION_ENVELOPE_PREVIEW_SCHEMA_VERSION,
        "status": "READY_FOR_SEPARATE_RUNTIME_ADMISSION_REVIEW" if handoff_ready else "NOT_READY",
        "candidate": candidate,
        "sizing": {
            "cap_usdt": summary.get("resolved_cap_usdt"),
            "cap_source": "current_candidate_envelope.cap_resolution.resolved_cap_usdt",
            "limit_price": construction.get("limit_price"),
            "rounded_qty": construction.get("rounded_qty"),
            "rounded_notional_usdt": construction.get("rounded_notional_usdt"),
            "placement_mode": construction.get("placement_mode"),
        },
        "market": {
            "bbo_age_ms_at_capture": bbo_age,
            "max_fresh_bbo_age_ms": max_fresh_bbo_age_ms,
            "best_bid": construction.get("best_bid"),
            "best_ask": construction.get("best_ask"),
        },
        "required_next_gates": runtime_admission_blockers,
        "order_admission_ready": False,
        "runtime_admission_ready": False,
        "boundary": "preview only; no order/probe/live authority",
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _iso(now),
        "status": status,
        "reason": "handoff_ready_no_order" if handoff_ready else ";".join(sorted(set(reasons))),
        "candidate": candidate,
        "source_head": source_head,
        "runtime_head": runtime_head,
        "artifacts": artifacts,
        "candidate_alignment": {
            "aligned": candidate_alignment,
            "candidates": candidates,
        },
        "gates": {
            "artifacts_fresh": all(item["status"] == "FRESH" for item in artifacts.values()),
            "schema_status_ready": all(schema_gates.values()),
            "candidate_alignment": candidate_alignment,
            "cap_from_gui_resolved_equity": not _cap_gate_reasons(
                refresh=refresh_payload,
                current_envelope=envelope_payload,
                construction_preview=preview_payload,
            ),
            "public_quote_public_only": not _request_envelope_reasons(quote_payload),
            "bbo_fresh_at_capture": (
                quote_derived.get("bbo_fresh") is True
                and bbo_age is not None
                and bbo_age <= max_fresh_bbo_age_ms
            ),
            "construction_constructible_under_cap": construction.get("constructible") is True,
            "no_authority_contamination": not authority_reasons,
            "handoff_ready_no_order": handoff_ready,
            "runtime_admission_ready": False,
            "order_admission_ready": False,
        },
        "runtime_admission_blockers": runtime_admission_blockers,
        "admission_envelope_preview": admission_envelope_preview,
        "blocking_gates": sorted(set(reasons)),
        "blocking_gate_count": len(set(reasons)),
        "authority_contamination_reasons": sorted(set(authority_reasons)),
        "answers": {
            "handoff_ready_no_order": handoff_ready,
            "runtime_admission_ready": False,
            "order_admission_ready": False,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "bounded_demo_probe_authorized": False,
            "decision_lease_emitted": False,
            "guardian_risk_gate_passed_by_this_packet": False,
            "rust_authority_granted_by_this_packet": False,
            "bybit_call_performed": False,
            "bybit_private_call_performed": False,
            "bybit_public_market_data_call_performed": False,
            "order_submission_performed": False,
            "order_cancel_performed": False,
            "order_modify_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "runtime_mutation_performed": False,
            "service_restart_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "live_authority_granted": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
        "boundary": (
            "canonical handoff review only; no latest overwrite, no plan/ledger/PG write, "
            "no Bybit call, no order/cancel/modify, no runtime mutation, no Cost Gate "
            "lowering, no bounded auth, no Decision Lease, no Rust authority grant, "
            "no probe/order/live authority, and no profit proof"
        ),
    }


def render_markdown(review: dict[str, Any]) -> str:
    candidate = _dict(review.get("candidate"))
    gates = _dict(review.get("gates"))
    preview = _dict(review.get("admission_envelope_preview"))
    sizing = _dict(preview.get("sizing"))
    lines = [
        "# Current Candidate Runtime Admission Handoff Review",
        "",
        f"- Status: `{review.get('status')}`",
        f"- Reason: `{review.get('reason')}`",
        f"- Candidate: `{candidate.get('side_cell_key')}`",
        f"- Handoff ready no-order: `{gates.get('handoff_ready_no_order')}`",
        f"- Runtime admission ready: `{gates.get('runtime_admission_ready')}`",
        f"- Order admission ready: `{gates.get('order_admission_ready')}`",
        f"- Cap USDT: `{sizing.get('cap_usdt')}`",
        f"- Limit price: `{sizing.get('limit_price')}`",
        f"- Rounded qty: `{sizing.get('rounded_qty')}`",
        f"- Rounded notional USDT: `{sizing.get('rounded_notional_usdt')}`",
        "",
        "## Gates",
    ]
    for name, passed in gates.items():
        lines.append(f"- `{name}`: `{passed}`")
    lines.extend(["", "## Runtime Admission Blockers"])
    for blocker in _list(review.get("runtime_admission_blockers")):
        lines.append(f"- `{blocker}`")
    lines.extend(["", "## Blocking Gates"])
    blocking = _list(review.get("blocking_gates"))
    lines.extend(f"- `{gate}`" for gate in blocking) if blocking else lines.append("- none")
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-json", type=Path, required=True)
    parser.add_argument("--public-quote-json", type=Path, required=True)
    parser.add_argument("--market-snapshot-json", type=Path, required=True)
    parser.add_argument("--construction-preview-json", type=Path, required=True)
    parser.add_argument("--current-envelope-json", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-artifact-age-seconds", type=int, default=DEFAULT_MAX_ARTIFACT_AGE_SECONDS)
    parser.add_argument("--max-fresh-bbo-age-ms", type=int, default=DEFAULT_MAX_FRESH_BBO_AGE_MS)
    parser.add_argument("--source-head")
    parser.add_argument("--runtime-head")
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    review = build_runtime_admission_handoff_review(
        refresh=_read_json(args.refresh_json),
        public_quote=_read_json(args.public_quote_json),
        market_snapshot=_read_json(args.market_snapshot_json),
        construction_preview=_read_json(args.construction_preview_json),
        current_envelope=_read_json(args.current_envelope_json),
        paths={
            "refresh": args.refresh_json,
            "public_quote": args.public_quote_json,
            "market_snapshot": args.market_snapshot_json,
            "construction_preview": args.construction_preview_json,
            "current_envelope": args.current_envelope_json,
        },
        max_artifact_age_seconds=args.max_artifact_age_seconds,
        max_fresh_bbo_age_ms=args.max_fresh_bbo_age_ms,
        source_head=args.source_head,
        runtime_head=args.runtime_head,
    )
    if args.json_output:
        _write_json(args.json_output, review)
    if args.output:
        _write_text(args.output, render_markdown(review))
    if args.print_json or not args.json_output and not args.output:
        print(json.dumps(review, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
