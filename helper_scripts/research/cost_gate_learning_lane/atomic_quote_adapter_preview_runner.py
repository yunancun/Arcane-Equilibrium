#!/usr/bin/env python3
"""Run one reviewed public quote -> adapter -> no-order preview flow.

This helper keeps the freshness-sensitive public quote handoff inside one
process. It still uses the existing public quote capture, adapter, and
construction preview contracts, and it does not submit orders, query or write
PG, lower gates, grant authority, mutate runtime state, or write ``_latest``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from cost_gate_learning_lane import bbo_freshness_public_quote_capture as quote_capture
from cost_gate_learning_lane import public_quote_market_snapshot_adapter as quote_adapter
from cost_gate_learning_lane.bounded_probe_candidate_construction_preview import (
    READY_STATUS as PREVIEW_READY_STATUS,
    build_candidate_construction_preview,
    render_markdown as render_preview_markdown,
)


SCHEMA_VERSION = "cost_gate_atomic_quote_adapter_preview_runner_v1"
READY_STATUS = "ATOMIC_QUOTE_ADAPTER_PREVIEW_READY_NO_ORDER"
QUOTE_NOT_READY_STATUS = "ATOMIC_QUOTE_CAPTURE_FAILED_CLOSED_NO_ORDER"
ADAPTER_NOT_READY_STATUS = "ATOMIC_QUOTE_ADAPTER_FAILED_CLOSED_NO_ORDER"
PREVIEW_NOT_READY_STATUS = "ATOMIC_CONSTRUCTION_PREVIEW_NOT_READY_NO_ORDER"

BOUNDARY = (
    "atomic public quote to adapter to no-order construction preview runner; "
    "no private/auth endpoint, PG query/write, _latest overwrite, order, cancel, "
    "modify, config, risk, auth, runtime/service/env/crontab mutation, Cost Gate "
    "lowering, freshness gate lowering, probe authority, order authority, "
    "live/mainnet authority, ledger append, or promotion proof"
)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _candidate(packet: dict[str, Any] | None) -> dict[str, Any]:
    return _dict(_dict(packet).get("selected_candidate") or _dict(packet).get("candidate"))


def _artifact(path: Path) -> dict[str, Any]:
    return {"path": str(path), "exists": path.exists()}


def _output_dir_allowed(output_dir: Path) -> bool:
    return all("latest" not in part.lower() for part in output_dir.parts)


def _output_path_allowed(output_dir: Path, output_path: Path | None) -> bool:
    if output_path is None:
        return True
    try:
        resolved_output = output_path.resolve()
        resolved_dir = output_dir.resolve()
    except OSError:
        return False
    return (
        _output_dir_allowed(output_path)
        and resolved_output != resolved_dir
        and resolved_dir in resolved_output.parents
    )


def _requests_summary(quote: dict[str, Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for request in _list(_dict(quote).get("requests")):
        request = _dict(request)
        envelope = _dict(request.get("request_envelope"))
        out.append(
            {
                "label": request.get("label"),
                "path": envelope.get("path"),
                "query": envelope.get("query"),
                "method": envelope.get("method"),
                "ok": request.get("ok"),
                "http_status": request.get("http_status"),
                "retCode": request.get("retCode"),
                "redirect_refused": request.get("redirect_refused"),
            }
        )
    return out


def _authority_answers(
    *,
    quote: dict[str, Any] | None,
    snapshot: dict[str, Any] | None,
    preview: dict[str, Any] | None,
) -> dict[str, Any]:
    quote_answers = _dict(_dict(quote).get("answers"))
    snapshot_answers = _dict(_dict(snapshot).get("answers"))
    preview_answers = _dict(_dict(preview).get("answers"))
    return {
        "bybit_public_market_data_call_performed": (
            quote_answers.get("bybit_public_market_data_call_performed") is True
        ),
        "bybit_private_call_performed": False,
        "auth_headers_present": quote_answers.get("auth_headers_present") is True,
        "cookie_headers_present": quote_answers.get("cookie_headers_present") is True,
        "pg_query_performed": False,
        "pg_write_performed": False,
        "runtime_mutation_performed": False,
        "runtime_env_mutation_performed": False,
        "service_restart_performed": False,
        "crontab_mutation_performed": False,
        "config_mutation_performed": False,
        "risk_mutation_performed": False,
        "order_submission_performed": False,
        "order_cancel_modify_performed": False,
        "writer_enabled": False,
        "global_cost_gate_lowering_recommended": False,
        "main_cost_gate_adjustment": "NONE",
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "live_authority_granted": False,
        "promotion_evidence": False,
        "adapter_reused_public_quote_artifact": (
            snapshot_answers.get("bybit_public_market_data_call_reused_from_artifact")
            is True
        ),
        "construction_preview_ready_no_order": (
            preview_answers.get("candidate_construction_preview_ready_no_order")
            is True
        ),
    }


def _summary_status(
    *,
    quote: dict[str, Any] | None,
    adapter_error: str | None,
    preview: dict[str, Any] | None,
) -> tuple[str, str]:
    if _dict(quote).get("status") != quote_capture.READY_STATUS:
        return QUOTE_NOT_READY_STATUS, "public_quote_capture_failed_closed"
    if adapter_error:
        return ADAPTER_NOT_READY_STATUS, adapter_error
    if _dict(preview).get("status") != PREVIEW_READY_STATUS:
        return PREVIEW_NOT_READY_STATUS, "construction_preview_not_ready_no_order"
    return READY_STATUS, "atomic_quote_adapter_preview_ready_no_order"


def run_atomic_quote_adapter_preview(
    *,
    reroute_review: dict[str, Any],
    reroute_review_path: Path,
    output_dir: Path,
    base_url: str = quote_capture.DEFAULT_BASE_URL,
    timeout_seconds: float = 2.0,
    cap_usdt: float | None = None,
    demo_operational_authorization_available: bool = False,
    source_head: str | None = None,
    runtime_head: str | None = None,
    opener: quote_capture.Opener | None = None,
    now_fn: quote_capture.NowFn | None = None,
    monotonic_fn: quote_capture.MonotonicFn | None = None,
) -> dict[str, Any]:
    if not _output_dir_allowed(output_dir):
        raise ValueError("output_dir must be timestamped and must not contain latest")
    output_dir.mkdir(parents=True, exist_ok=True)
    quote_path = output_dir / "public_quote.json"
    quote_md_path = output_dir / "public_quote.md"
    snapshot_path = output_dir / "market_snapshot.json"
    snapshot_md_path = output_dir / "market_snapshot.md"
    preview_path = output_dir / "construction_preview.json"
    preview_md_path = output_dir / "construction_preview.md"

    quote = quote_capture.capture_public_quote(
        reroute_review=reroute_review,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        cap_usdt=cap_usdt,
        max_fresh_bbo_age_ms=1000,
        opener=opener,
        now_fn=now_fn,
        monotonic_fn=monotonic_fn,
        source_head=source_head,
        runtime_head=runtime_head,
    )
    _write_json(quote_path, quote)
    _write_text(quote_md_path, quote_capture.render_markdown(quote))

    snapshot: dict[str, Any] | None = None
    preview: dict[str, Any] | None = None
    adapter_error = None
    if quote.get("status") == quote_capture.READY_STATUS:
        try:
            snapshot = quote_adapter.build_market_snapshot_from_public_quote(
                public_quote=quote,
                reroute_review=reroute_review,
                public_quote_path=quote_path,
                reroute_review_path=reroute_review_path,
                generated_at_utc=(now_fn or _utc_now)(),
                cap_usdt=cap_usdt,
                max_fresh_bbo_age_ms=1000,
            )
        except ValueError as exc:
            adapter_error = str(exc)
        else:
            _write_json(snapshot_path, snapshot)
            _write_text(snapshot_md_path, quote_adapter.render_markdown(snapshot))
            preview = build_candidate_construction_preview(
                reroute_review=reroute_review,
                market_snapshot=snapshot,
                demo_operational_authorization_available=(
                    demo_operational_authorization_available
                ),
                now_utc=(now_fn or _utc_now)(),
                artifact_paths={
                    "reroute_review": reroute_review_path,
                    "market_snapshot": snapshot_path,
                },
            )
            _write_json(preview_path, preview)
            _write_text(preview_md_path, render_preview_markdown(preview))

    status, reason = _summary_status(
        quote=quote,
        adapter_error=adapter_error,
        preview=preview,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": (now_fn or _utc_now)().astimezone(dt.timezone.utc).isoformat(),
        "status": status,
        "reason": reason,
        "candidate": _candidate(reroute_review),
        "output_dir": str(output_dir),
        "artifacts": {
            "public_quote": _artifact(quote_path),
            "market_snapshot": _artifact(snapshot_path),
            "construction_preview": _artifact(preview_path),
        },
        "statuses": {
            "public_quote": _dict(quote).get("status"),
            "market_snapshot": _dict(_dict(snapshot).get("adapter")).get("status"),
            "construction_preview": _dict(preview).get("status"),
        },
        "request_count": len(_list(quote.get("requests"))),
        "requests": _requests_summary(quote),
        "adapter_error": adapter_error,
        "preview_blocking_gates": _list(_dict(preview).get("blocking_gates")),
        "answers": _authority_answers(quote=quote, snapshot=snapshot, preview=preview),
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# Atomic Quote Adapter Preview Runner",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: {packet.get('reason')}",
        f"- Candidate: `{_dict(packet.get('candidate')).get('side_cell_key')}`",
        f"- Output dir: `{packet.get('output_dir')}`",
        f"- Request count: `{packet.get('request_count')}`",
        f"- Boundary: {packet.get('boundary')}",
        "",
        "## Statuses",
        "",
    ]
    for key, value in _dict(packet.get("statuses")).items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Requests", ""])
    for request in _list(packet.get("requests")):
        request = _dict(request)
        lines.append(
            f"- `{request.get('label')}` path=`{request.get('path')}` "
            f"ok=`{request.get('ok')}` retCode=`{request.get('retCode')}`"
        )
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reroute-review-json", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-url", default=quote_capture.DEFAULT_BASE_URL)
    parser.add_argument("--timeout-seconds", type=float, default=2.0)
    parser.add_argument("--cap-usdt", type=float)
    parser.add_argument("--demo-operational-authorization-available", action="store_true")
    parser.add_argument("--source-head")
    parser.add_argument("--runtime-head")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if not _output_path_allowed(args.output_dir, args.json_output):
        raise ValueError("json-output must stay under output-dir and must not contain latest")
    if not _output_path_allowed(args.output_dir, args.output):
        raise ValueError("output must stay under output-dir and must not contain latest")
    reroute = _read_json(args.reroute_review_json)
    if reroute is None:
        raise ValueError("reroute review JSON is required")
    packet = run_atomic_quote_adapter_preview(
        reroute_review=reroute,
        reroute_review_path=args.reroute_review_json,
        output_dir=args.output_dir,
        base_url=args.base_url,
        timeout_seconds=args.timeout_seconds,
        cap_usdt=args.cap_usdt,
        demo_operational_authorization_available=(
            args.demo_operational_authorization_available
        ),
        source_head=args.source_head,
        runtime_head=args.runtime_head,
    )
    markdown = render_markdown(packet)
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.output:
        _write_text(args.output, markdown)
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True, default=str))
    if not args.json_output and not args.output and not args.print_json:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
