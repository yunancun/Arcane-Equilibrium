#!/usr/bin/env python3
"""Scan artifact files for candidate-matched actual order/fill evidence.

The scan is deliberately read-only. It consumes JSONL ledger files, pipeline
snapshot JSON files, and optional engine log tails. It does not query PG, call
Bybit, acquire a Decision Lease, submit/cancel/modify orders, or mutate runtime.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "current_candidate_order_fill_evidence_scan_strict_v1"
NO_EVIDENCE_STATUS = "NO_CANDIDATE_MATCHED_ACTUAL_ORDER_FILL_EVIDENCE"
EVIDENCE_PRESENT_STATUS = "CANDIDATE_MATCHED_ACTUAL_ORDER_FILL_EVIDENCE_PRESENT"

STRICT_DEFINITION = (
    "candidate-bound rows/objects with concrete non-empty order/fill/execution/"
    "fee/slippage/reconstruction identifiers or metrics; context flags such as "
    "allowed_to_submit_order are excluded"
)

BOUNDARY = (
    "artifact-only strict order/fill evidence scan; no PG query/write, no Bybit "
    "public/private/order endpoint, no Decision Lease, no order/cancel/modify, "
    "no runtime/env/service mutation, no Cost Gate lowering, no live/mainnet, "
    "and no proof/promotion claim"
)

STRICT_EVENT_HINTS = {
    "actual_order",
    "bounded_probe_order",
    "dispatch_response",
    "exchange_order",
    "execution",
    "fill",
    "filled",
    "order_dispatch",
    "order_result",
    "order_update",
    "trade_execution",
}

STRICT_KEY_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"(^|_)avg_fill_price($|_)",
        r"(^|_)client_order_id($|_)",
        r"(^|_)commission($|_)",
        r"(^|_)cum_exec_qty($|_)",
        r"(^|_)exec(ution)?_id($|_)",
        r"(^|_)exchange_order_id($|_)",
        r"(^|_)fee(_bps|_usdt|_amount)?($|_)",
        r"(^|_)fill(_id|_price|_qty|ed_qty)?($|_)",
        r"(^|_)order_id($|_)",
        r"(^|_)order_status($|_)",
        r"(^|_)reconstruct(ion|ability)?(_id|_status)?($|_)",
        r"(^|_)slippage(_bps|_usdt)?($|_)",
        r"(^|_)trade_id($|_)",
    )
)

EXCLUDED_STRICT_KEYS = {
    "allowed_to_submit_order",
    "bybit_order_endpoint_allowed_by_this_packet",
    "order_authority",
    "order_authority_granted",
    "order_authority_granted_in_authorization_object",
    "order_capable_action_allowed_by_this_packet",
    "order_submission_allowed",
    "order_submission_allowed_by_this_packet",
    "order_submission_performed",
    "probe_authority_granted",
    "probe_authority_granted_in_authorization_object",
}

LOG_STRICT_RE = re.compile(
    r"(order_id|exchange_order_id|client_order_id|fill_id|execution|exec_id|"
    r"filled|fee|slippage|OrderUpdate|Dispatch)",
    re.IGNORECASE,
)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _str(value: Any) -> str:
    return str(value or "").strip()


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _candidate_from_side_cell(side_cell_key: str) -> dict[str, Any]:
    parts = side_cell_key.split("|")
    return {
        "side_cell_key": side_cell_key,
        "strategy_name": parts[0] if len(parts) == 3 else None,
        "symbol": parts[1] if len(parts) == 3 else None,
        "side": parts[2] if len(parts) == 3 else None,
    }


def _sample(value: Any, *, limit: int = 800) -> Any:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(text) <= limit:
        return value
    return text[:limit] + "...<truncated>"


def _path_summary(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
    except OSError:
        return {"path": str(path), "present": False}
    return {
        "path": str(path),
        "present": True,
        "size_bytes": stat.st_size,
        "sha256": _sha256(path),
        "mtime_utc": dt.datetime.fromtimestamp(
            stat.st_mtime, tz=dt.timezone.utc
        ).isoformat(),
    }


def _iter_json_values(node: Any, path: str = "$"):
    yield path, node
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _iter_json_values(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _iter_json_values(value, f"{path}[{index}]")


def _candidate_matches(node: Any, candidate: str) -> bool:
    if isinstance(node, str):
        return node == candidate
    if isinstance(node, dict):
        for key in (
            "candidate",
            "candidate_id",
            "selected_side_cell_key",
            "side_cell_key",
        ):
            if node.get(key) == candidate:
                return True
        summary = node.get("candidate_summary")
        if isinstance(summary, dict) and summary.get("side_cell_key") == candidate:
            return True
        return any(_candidate_matches(value, candidate) for value in node.values())
    if isinstance(node, list):
        return any(_candidate_matches(value, candidate) for value in node)
    return False


def _strict_key_match(key: str) -> bool:
    normalized = key.strip().lower()
    if normalized in EXCLUDED_STRICT_KEYS:
        return False
    return any(pattern.search(normalized) for pattern in STRICT_KEY_PATTERNS)


def _strict_values(node: Any) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for path, value in _iter_json_values(node):
        key = path.rsplit(".", 1)[-1].split("[", 1)[0]
        if not _strict_key_match(key):
            continue
        if value in (None, "", [], {}):
            continue
        if isinstance(value, bool):
            continue
        matches.append({"path": path, "value": _sample(value, limit=200)})
    return matches


def _record_type(node: Any) -> str | None:
    if isinstance(node, dict):
        for key in ("record_type", "event_type", "type", "kind"):
            text = _str(node.get(key))
            if text:
                return text
    return None


def _strict_record_type_hint(record_type: str | None) -> bool:
    text = _str(record_type).lower()
    return any(hint in text for hint in STRICT_EVENT_HINTS)


def _scan_ledger(path: Path, *, candidate: str, sample_limit: int) -> dict[str, Any]:
    summary = _path_summary(path)
    candidate_rows = 0
    parse_errors = 0
    total_rows = 0
    top = Counter()
    latest_candidate_events: list[list[Any]] = []
    strict_samples: list[dict[str, Any]] = []
    allowed_true_samples: list[dict[str, Any]] = []

    if not summary.get("present"):
        summary.update(
            {
                "total_rows": total_rows,
                "candidate_rows": candidate_rows,
                "parse_errors": parse_errors,
                "record_type_top": [],
                "strict_evidence_samples": strict_samples,
                "allowed_true_samples": allowed_true_samples,
            }
        )
        return summary

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            total_rows += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                parse_errors += 1
                continue
            if not isinstance(row, dict) or not _candidate_matches(row, candidate):
                continue
            candidate_rows += 1
            rec_type = _record_type(row) or "unknown"
            top[rec_type] += 1
            event_ts = row.get("ts_utc") or row.get("timestamp") or row.get("created_at")
            latest_candidate_events.append([event_ts, line_no, rec_type])
            latest_candidate_events = latest_candidate_events[-12:]
            if row.get("allowed_to_submit_order") is True and len(allowed_true_samples) < sample_limit:
                allowed_true_samples.append({"line": line_no, "record_type": rec_type})
            strict = _strict_values(row)
            if strict and (_strict_record_type_hint(rec_type) or len(strict) >= 2):
                if len(strict_samples) < sample_limit:
                    strict_samples.append(
                        {
                            "line": line_no,
                            "record_type": rec_type,
                            "strict_values": strict[:8],
                            "sample": _sample(row),
                        }
                    )

    summary.update(
        {
            "total_rows": total_rows,
            "candidate_rows": candidate_rows,
            "parse_errors": parse_errors,
            "record_type_top": top.most_common(12),
            "latest_candidate_events": latest_candidate_events,
            "strict_evidence_samples": strict_samples,
            "allowed_true_samples": allowed_true_samples,
        }
    )
    return summary


def _scan_snapshot(path: Path, *, candidate: str, sample_limit: int) -> dict[str, Any]:
    summary = _path_summary(path)
    strict_candidate_objects = 0
    samples: list[dict[str, Any]] = []
    if not summary.get("present"):
        summary.update({"strict_candidate_objects": 0, "samples": []})
        return summary
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        summary.update({"error": type(exc).__name__, "strict_candidate_objects": 0, "samples": []})
        return summary
    for json_path, node in _iter_json_values(payload):
        if not isinstance(node, dict) or not _candidate_matches(node, candidate):
            continue
        strict = _strict_values(node)
        if strict:
            strict_candidate_objects += 1
            if len(samples) < sample_limit:
                samples.append(
                    {
                        "json_path": json_path,
                        "strict_values": strict[:8],
                        "sample": _sample(node),
                    }
                )
    summary.update({"strict_candidate_objects": strict_candidate_objects, "samples": samples})
    return summary


def _scan_log_tail(
    path: Path,
    *,
    candidate: str,
    sample_limit: int,
    tail_bytes: int,
) -> dict[str, Any]:
    summary = _path_summary(path)
    matches: list[str] = []
    if not summary.get("present"):
        summary.update({"strict_tail_match_count": 0, "strict_tail_samples": []})
        return summary
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - tail_bytes))
            text = handle.read().decode("utf-8", errors="replace")
    except OSError as exc:
        summary.update(
            {
                "error": type(exc).__name__,
                "strict_tail_match_count": 0,
                "strict_tail_samples": [],
            }
        )
        return summary
    count = 0
    for line in text.splitlines():
        if candidate in line and LOG_STRICT_RE.search(line):
            count += 1
            if len(matches) < sample_limit:
                matches.append(line[:800])
    summary.update({"strict_tail_match_count": count, "strict_tail_samples": matches})
    return summary


def build_scan(
    *,
    candidate: str,
    ledger_paths: list[Path],
    snapshot_paths: list[Path],
    log_paths: list[Path],
    sample_limit: int = 12,
    log_tail_bytes: int = 2_000_000,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    if not candidate:
        raise ValueError("candidate is required")
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    ledgers = [
        _scan_ledger(path, candidate=candidate, sample_limit=sample_limit)
        for path in ledger_paths
    ]
    snapshots = {
        str(path): _scan_snapshot(path, candidate=candidate, sample_limit=sample_limit)
        for path in snapshot_paths
    }
    logs = {
        str(path): _scan_log_tail(
            path,
            candidate=candidate,
            sample_limit=sample_limit,
            tail_bytes=log_tail_bytes,
        )
        for path in log_paths
    }
    strict_samples = [
        sample
        for ledger in ledgers
        for sample in ledger.get("strict_evidence_samples", [])
    ]
    snapshot_hits = sum(
        int(snapshot.get("strict_candidate_objects") or 0)
        for snapshot in snapshots.values()
    )
    log_hits = sum(int(log.get("strict_tail_match_count") or 0) for log in logs.values())
    evidence_present = bool(strict_samples or snapshot_hits or log_hits)
    ledger_candidate_rows = sum(int(ledger.get("candidate_rows") or 0) for ledger in ledgers)
    ledger_record_top = Counter()
    latest_events: list[list[Any]] = []
    for ledger in ledgers:
        ledger_record_top.update(dict(ledger.get("record_type_top") or []))
        latest_events.extend(ledger.get("latest_candidate_events") or [])
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": EVIDENCE_PRESENT_STATUS if evidence_present else NO_EVIDENCE_STATUS,
        "candidate": candidate,
        "candidate_identity": _candidate_from_side_cell(candidate),
        "candidate_matched_actual_order_fill_evidence_present": evidence_present,
        "strict_definition": STRICT_DEFINITION,
        "ledger_counts": {
            "candidate_rows": ledger_candidate_rows,
            "source_file_count": len(ledgers),
            "total_rows": sum(int(ledger.get("total_rows") or 0) for ledger in ledgers),
            "parse_errors": sum(int(ledger.get("parse_errors") or 0) for ledger in ledgers),
        },
        "ledger_record_type_top": ledger_record_top.most_common(12),
        "ledger_latest_candidate_events": latest_events[-12:],
        "ledger_strict_evidence_samples": strict_samples[:sample_limit],
        "ledger_allowed_true_samples": [
            sample
            for ledger in ledgers
            for sample in ledger.get("allowed_true_samples", [])
        ][:sample_limit],
        "pipeline_snapshot_strict_hits": snapshots,
        "engine_log_strict_tail_match_count": log_hits,
        "engine_log_strict_tail_samples": [
            sample for log in logs.values() for sample in log.get("strict_tail_samples", [])
        ][:sample_limit],
        "source_artifacts": {
            "ledgers": ledgers,
            "snapshots": list(snapshots.values()),
            "logs": list(logs.values()),
        },
        "answers": {
            "artifact_read_only": True,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "bybit_call_performed": False,
            "decision_lease_performed": False,
            "order_submission_performed": False,
            "runtime_mutation_performed": False,
            "cost_gate_lowering_performed": False,
            "live_authority_granted": False,
            "promotion_proof": False,
            "profit_proof": False,
        },
        "boundary": BOUNDARY,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Current Candidate Strict Order/Fill Evidence Scan",
        "",
        f"- Generated: `{payload.get('generated_at_utc')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Candidate: `{payload.get('candidate')}`",
        "- Candidate-matched actual order/fill evidence present: "
        f"`{payload.get('candidate_matched_actual_order_fill_evidence_present')}`",
        f"- Ledger candidate rows: `{payload.get('ledger_counts', {}).get('candidate_rows')}`",
        f"- Engine log strict tail matches: `{payload.get('engine_log_strict_tail_match_count')}`",
        "",
        "## Boundary",
        "",
        str(payload.get("boundary")),
    ]
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--ledger-jsonl", type=Path, action="append", default=[])
    parser.add_argument("--pipeline-snapshot-json", type=Path, action="append", default=[])
    parser.add_argument("--engine-log", type=Path, action="append", default=[])
    parser.add_argument("--sample-limit", type=int, default=12)
    parser.add_argument("--log-tail-bytes", type=int, default=2_000_000)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    payload = build_scan(
        candidate=args.candidate,
        ledger_paths=args.ledger_jsonl,
        snapshot_paths=args.pipeline_snapshot_json,
        log_paths=args.engine_log,
        sample_limit=args.sample_limit,
        log_tail_bytes=args.log_tail_bytes,
    )
    if args.json_output:
        _write_json(args.json_output, payload)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render_markdown(payload), encoding="utf-8")
    if args.print_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
