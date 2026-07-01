#!/usr/bin/env python3
"""Capture a read-only runtime governance IPC snapshot.

The helper only calls governance read methods used by current-candidate gate
evidence. It does not acquire/release a Decision Lease, mutate runtime state,
call Bybit, query/write PG, or grant order authority.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import inspect
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping


_SRV_ROOT = Path(__file__).resolve().parents[3]
if str(_SRV_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRV_ROOT))


SCHEMA_VERSION = "runtime_governance_ipc_readonly_snapshot_v1"
READY_STATUS = "RUNTIME_GOVERNANCE_IPC_READONLY_SNAPSHOT_READY"
BLOCKED_BY_RUNTIME_STATUS = "RUNTIME_GOVERNANCE_IPC_READONLY_SNAPSHOT_BLOCKED_BY_RUNTIME"

READ_ONLY_METHODS = (
    "governance.get_status",
    "governance.list_leases",
    "governance.get_risk_state",
)

BOUNDARY = (
    "read-only runtime governance IPC snapshot; no Decision Lease acquire or "
    "release, no Guardian/Rust authority grant, no Bybit/private/order call, "
    "no order/cancel/modify, no PG read/write, no runtime/service/env/crontab "
    "mutation, no Cost Gate lowering, no live/mainnet authority, no promotion "
    "proof, and no profit proof"
)

IPCDispatcher = Callable[..., Awaitable[Mapping[str, Any]] | Mapping[str, Any]]


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"json object required: {path}")
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


def _sha256(path: Path | None) -> str | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalize_method_entry(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        payload = dict(raw)
        if payload.get("ok") is False:
            return payload
        if "result" in payload or "payload" in payload:
            return {"ok": payload.get("ok", True), **payload}
        return {"ok": True, "result": payload}
    if isinstance(raw, list):
        return {"ok": True, "result": list(raw)}
    return {"ok": False, "error": "ipc_result_not_object_or_list"}


def _run_dispatcher_awaitable(value: Any, timeout_seconds: float) -> Any:
    if not inspect.isawaitable(value):
        return value
    return asyncio.run(asyncio.wait_for(value, timeout=timeout_seconds + 1.0))


def _dispatch_ipc_method(
    *,
    method: str,
    params: Mapping[str, Any] | None = None,
    dispatcher: IPCDispatcher | None = None,
    timeout_seconds: float = 5.0,
) -> dict[str, Any]:
    try:
        if dispatcher is not None:
            raw = _run_dispatcher_awaitable(
                dispatcher(method, dict(params or {}), timeout_seconds),
                timeout_seconds,
            )
        else:
            from program_code.exchange_connectors.bybit_connector.control_api_v1.app import (  # noqa: PLC0415
                ipc_dispatch,
            )

            raw = _run_dispatcher_awaitable(
                ipc_dispatch.one_shot_ipc_call(
                    method,
                    params=dict(params or {}),
                    timeout=timeout_seconds,
                    wrap_errors_as_http=False,
                    error_context="runtime_governance_ipc_readonly_snapshot",
                ),
                timeout=timeout_seconds + 1.0,
            )
    except Exception as exc:  # noqa: BLE001
        entry = {"ok": False, "error": f"ipc_dispatch_exception:{type(exc).__name__}"}
        reason = getattr(exc, "reason", None)
        if isinstance(reason, str) and reason:
            entry["error_reason"] = reason
        return entry
    return _normalize_method_entry(raw)


def _method_result(entry: Mapping[str, Any]) -> Any:
    if entry.get("ok") is False:
        return None
    if "result" in entry:
        return entry.get("result")
    if "payload" in entry:
        return entry.get("payload")
    return dict(entry)


def _unwrap_result(value: Any) -> Any:
    if isinstance(value, dict) and set(value.keys()) == {"result"}:
        return value.get("result")
    return value


def _lease_count(list_leases_entry: Mapping[str, Any]) -> int:
    raw = _unwrap_result(_method_result(list_leases_entry))
    if isinstance(raw, dict):
        raw = raw.get("leases") or raw.get("items") or raw.get("result")
    leases = _list(raw)
    return len([lease for lease in leases if isinstance(lease, dict)])


def _summary(methods: dict[str, dict[str, Any]]) -> dict[str, Any]:
    status = _dict(_unwrap_result(_method_result(methods["governance.get_status"])))
    risk = _dict(_unwrap_result(_method_result(methods["governance.get_risk_state"])))
    constraints = _dict(risk.get("constraints"))
    multiplier = _float(
        constraints.get("position_size_multiplier")
        if constraints
        else risk.get("position_size_multiplier")
    )
    new_entries_allowed = (
        constraints.get("new_entries_allowed")
        if constraints
        else risk.get("new_entries_allowed")
    )
    return {
        "risk_level": risk.get("level") or status.get("risk_level"),
        "position_size_multiplier": multiplier,
        "new_entries_allowed": new_entries_allowed,
        "lease_live_count": status.get("lease_live_count"),
        "lease_count": _lease_count(methods["governance.list_leases"]),
    }


def build_runtime_governance_ipc_readonly_snapshot(
    *,
    now_utc: dt.datetime | None = None,
    timeout_seconds: float = 5.0,
    source_head: str | None = None,
    runtime_head: str | None = None,
    dispatcher: IPCDispatcher | None = None,
) -> dict[str, Any]:
    if timeout_seconds <= 0 or timeout_seconds > 30:
        raise ValueError("timeout_seconds must be in (0, 30]")

    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    methods = {
        method: _dispatch_ipc_method(
            method=method,
            dispatcher=dispatcher,
            timeout_seconds=timeout_seconds,
        )
        for method in READ_ONLY_METHODS
    }
    runtime_blockers = [
        f"{method}_not_ok"
        for method, entry in methods.items()
        if entry.get("ok") is False
    ]
    read_only_methods_only = set(methods) <= set(READ_ONLY_METHODS)
    if not read_only_methods_only:
        runtime_blockers.append("non_read_only_method_requested")

    status = READY_STATUS if not runtime_blockers else BLOCKED_BY_RUNTIME_STATUS
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": (
            "runtime_governance_readonly_snapshot_ready"
            if status == READY_STATUS
            else "runtime_governance_readonly_snapshot_blocked"
        ),
        "source": "runtime_governance_ipc_readonly_snapshot",
        "source_head": source_head,
        "runtime_head": runtime_head,
        "methods": methods,
        "summary": _summary(methods) if not runtime_blockers else None,
        "runtime_blockers": sorted(set(runtime_blockers)),
        "answers": {
            "runtime_readonly_ipc_call_performed": True,
            "read_only_methods_only": read_only_methods_only,
            "decision_lease_acquire_performed": False,
            "decision_lease_release_performed": False,
            "lease_acquire_performed": False,
            "lease_release_performed": False,
            "order_submission_performed": False,
            "order_cancel_performed": False,
            "order_modify_performed": False,
            "exchange_call_performed": False,
            "bybit_private_call_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "runtime_mutation_performed": False,
            "config_mutation_performed": False,
            "risk_mutation_performed": False,
            "service_restart_performed": False,
            "cost_gate_lowering_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "risk_expansion": False,
            "live_authority_granted": False,
            "mainnet_authority_granted": False,
            "live_or_mainnet": False,
            "main_cost_gate_adjustment": "NONE",
        },
        "boundary": BOUNDARY,
        "artifact_self_hash_sha256": None,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    summary = _dict(packet.get("summary"))
    blockers = _list(packet.get("runtime_blockers"))
    lines = [
        "# Runtime Governance IPC Read-Only Snapshot",
        "",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Risk level: `{summary.get('risk_level')}`",
        f"- Position-size multiplier: `{summary.get('position_size_multiplier')}`",
        f"- Lease live count: `{summary.get('lease_live_count')}`",
        f"- Lease count: `{summary.get('lease_count')}`",
        "",
        "## Blockers",
    ]
    lines.extend(f"- `{blocker}`" for blocker in blockers) if blockers else lines.append("- none")
    lines.extend(["", "## Boundary", packet.get("boundary", "")])
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument("--source-head")
    parser.add_argument("--runtime-head")
    parser.add_argument(
        "--ipc-secret-file",
        type=Path,
        help=(
            "Path to the runtime IPC HMAC secret file. The helper passes only "
            "the path through OPENCLAW_IPC_SECRET_FILE; the secret value is "
            "read by the existing IPC auth layer and is never serialized."
        ),
    )
    parser.add_argument("--print-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    previous_ipc_secret_file = os.environ.get("OPENCLAW_IPC_SECRET_FILE")
    if args.ipc_secret_file is not None:
        os.environ["OPENCLAW_IPC_SECRET_FILE"] = str(args.ipc_secret_file)
    try:
        packet = build_runtime_governance_ipc_readonly_snapshot(
            timeout_seconds=args.timeout_seconds,
            source_head=args.source_head,
            runtime_head=args.runtime_head,
        )
    finally:
        if args.ipc_secret_file is not None:
            if previous_ipc_secret_file is None:
                os.environ.pop("OPENCLAW_IPC_SECRET_FILE", None)
            else:
                os.environ["OPENCLAW_IPC_SECRET_FILE"] = previous_ipc_secret_file
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.output:
        _write_text(args.output, render_markdown(packet))
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if packet["status"] == READY_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
