#!/usr/bin/env python3
"""Build a source-only runtime health hygiene packet.

This packet reconciles two runtime hygiene surfaces without touching runtime:

1. installed demo-learning cron expected-head pins, and
2. Trading API process reachability versus service ownership.

It reads supplied text/JSON snapshots only. It does not call systemctl, inspect
processes, query PG, call Bybit, mutate crontab, restart services, deploy, or
grant trading/probe authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import shlex
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "runtime_health_hygiene_packet_v1"
BOUNDARY = (
    "source-only runtime health hygiene packet from supplied snapshots; no "
    "systemctl/ps/curl/PG/Bybit call, no crontab edit, no service restart, no "
    "deploy, no runtime mutation, no Cost Gate lowering, no probe/order/live "
    "authority, and no promotion proof"
)

STACK_CRON_MARKERS = {
    "demo_learning_evidence": "demo_learning_evidence_audit_cron.sh",
    "sealed_horizon_probe_preflight": "sealed_horizon_probe_preflight_cron.sh",
    "cost_gate_learning_lane": "cost_gate_learning_lane_cron.sh",
    "demo_learning_stack_healthcheck": "demo_learning_stack_healthcheck_cron.sh",
}
EXPECTED_HEAD_VARS_BY_COMPONENT = {
    "demo_learning_evidence": (
        "OPENCLAW_DEMO_LEARNING_EVIDENCE_EXPECTED_HEAD",
        "OPENCLAW_EXPECTED_SOURCE_HEAD",
    ),
    "sealed_horizon_probe_preflight": (
        "OPENCLAW_SEALED_HORIZON_PREFLIGHT_EXPECTED_HEAD",
        "OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD",
        "OPENCLAW_EXPECTED_SOURCE_HEAD",
    ),
    "cost_gate_learning_lane": (
        "OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD",
        "OPENCLAW_EXPECTED_SOURCE_HEAD",
    ),
    "demo_learning_stack_healthcheck": (
        "OPENCLAW_DEMO_LEARNING_STACK_HEALTHCHECK_EXPECTED_HEAD",
        "OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD",
        "OPENCLAW_EXPECTED_SOURCE_HEAD",
    ),
}
TRUTHY = {"1", "true", "yes", "on", "active", "running", "reachable", "ok"}
FALSEY = {"0", "false", "no", "off", "inactive", "dead", "failed", "unreachable"}
GIT_SHA_HEX = set("0123456789abcdefABCDEF")
MIN_GIT_SHA_LEN = 7
MAX_GIT_SHA_LEN = 40


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _str(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(float(value)):
            return None
        return bool(value)
    text = _str(value).lower()
    if text in TRUTHY:
        return True
    if text in FALSEY:
        return False
    return None


def _sha_validation_error(value: str | None) -> str | None:
    clean = _str(value)
    if not clean:
        return "missing"
    if len(clean) < MIN_GIT_SHA_LEN or len(clean) > MAX_GIT_SHA_LEN:
        return "invalid_length"
    if any(char not in GIT_SHA_HEX for char in clean):
        return "non_hex"
    return None


def _sha_prefix_matches(head: str | None, target: str | None) -> bool | None:
    clean_head = _str(head)
    clean_target = _str(target)
    if _sha_validation_error(clean_head) or _sha_validation_error(clean_target):
        return None
    return clean_head.startswith(clean_target) or clean_target.startswith(clean_head)


def _read_text(path: Path | None) -> tuple[str | None, str | None]:
    if path is None:
        return None, "missing_path"
    try:
        return path.read_text(encoding="utf-8"), None
    except FileNotFoundError:
        return None, "missing"
    except OSError as exc:
        return None, f"{type(exc).__name__}:{exc}"


def _read_json(path: Path | None) -> tuple[dict[str, Any] | None, str | None]:
    if path is None:
        return None, "missing_path"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "missing"
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return None, f"{type(exc).__name__}:{exc}"
    if not isinstance(payload, dict):
        return None, "not_object"
    return payload, None


def _env_assignments(line: str) -> dict[str, str]:
    try:
        tokens = shlex.split(line, comments=False, posix=True)
    except ValueError:
        tokens = line.split()
    env: dict[str, str] = {}
    for token in tokens:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        if key and key.replace("_", "").isalnum():
            env[key] = value
    return env


def _matching_cron_entries(crontab_text: str | None) -> list[dict[str, Any]]:
    if crontab_text is None:
        return []
    entries: list[dict[str, Any]] = []
    for raw_line in crontab_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        for component, marker in STACK_CRON_MARKERS.items():
            if marker not in line:
                continue
            env = _env_assignments(line)
            resolved = None
            resolved_var = None
            for name in EXPECTED_HEAD_VARS_BY_COMPONENT[component]:
                value = _str(env.get(name))
                if value:
                    resolved = value
                    resolved_var = name
                    break
            entries.append({
                "component": component,
                "marker": marker,
                "line": line,
                "expected_head": resolved,
                "expected_head_var": resolved_var,
                "expected_head_vars_present": {
                    name: env.get(name)
                    for name in EXPECTED_HEAD_VARS_BY_COMPONENT[component]
                    if name in env
                },
            })
            break
    return entries


def _cron_expected_head_summary(
    *,
    crontab_text: str | None,
    crontab_error: str | None,
    target_source_head: str | None,
) -> dict[str, Any]:
    entries = _matching_cron_entries(crontab_text)
    expected_heads = sorted({
        _str(entry.get("expected_head"))
        for entry in entries
        if _str(entry.get("expected_head"))
    })
    target_source_head_error = _sha_validation_error(target_source_head)
    missing_components = [
        component
        for component in STACK_CRON_MARKERS
        if not any(entry["component"] == component for entry in entries)
    ]
    missing_expected_head = [
        entry["component"] for entry in entries if not _str(entry.get("expected_head"))
    ]
    invalid_expected_head_entries = [
        {
            "component": entry["component"],
            "expected_head": entry.get("expected_head"),
            "validation_error": _sha_validation_error(entry.get("expected_head")),
            "expected_head_var": entry.get("expected_head_var"),
        }
        for entry in entries
        if _str(entry.get("expected_head"))
        and _sha_validation_error(entry.get("expected_head")) is not None
    ]
    mismatched_entries = [
        {
            "component": entry["component"],
            "expected_head": entry.get("expected_head"),
            "target_source_head": target_source_head,
            "expected_head_var": entry.get("expected_head_var"),
        }
        for entry in entries
        if target_source_head_error is None
        and _sha_validation_error(entry.get("expected_head")) is None
        and _sha_prefix_matches(entry.get("expected_head"), target_source_head) is False
    ]
    inconsistent = len(expected_heads) > 1
    drift = (
        bool(mismatched_entries)
        or inconsistent
        or bool(missing_expected_head)
        or bool(invalid_expected_head_entries)
    )
    if crontab_error:
        status = "CRONTAB_SNAPSHOT_UNAVAILABLE"
    elif target_source_head_error == "missing":
        status = "TARGET_SOURCE_HEAD_MISSING"
    elif target_source_head_error is not None:
        status = "TARGET_SOURCE_HEAD_INVALID"
    elif not entries:
        status = "DEMO_LEARNING_STACK_CRON_ENTRIES_MISSING"
    elif drift:
        status = "CRON_EXPECTED_HEAD_DRIFT"
    else:
        status = "CRON_EXPECTED_HEAD_CONSISTENT"
    return {
        "status": status,
        "crontab_error": crontab_error,
        "target_source_head": target_source_head,
        "target_source_head_error": target_source_head_error,
        "matching_entry_count": len(entries),
        "missing_components": missing_components,
        "expected_heads": expected_heads,
        "inconsistent_expected_heads": inconsistent,
        "missing_expected_head_components": missing_expected_head,
        "invalid_expected_head_entries": invalid_expected_head_entries,
        "mismatched_entries": mismatched_entries,
        "expected_head_drift_present": drift,
        "entries": entries,
    }


def _api_service_summary(api_status: dict[str, Any] | None, source_error: str | None) -> dict[str, Any]:
    data = _dict(api_status)
    api_reachable = _bool(
        data.get("api_reachable")
        if "api_reachable" in data
        else data.get("reachable")
    )
    uvicorn_present = _bool(
        data.get("uvicorn_process_present")
        if "uvicorn_process_present" in data
        else data.get("process_present")
    )
    service_active = _bool(
        data.get("openclaw_trading_api_service_active")
        if "openclaw_trading_api_service_active" in data
        else data.get("service_active")
    )
    service_status = (
        data.get("openclaw_trading_api_service_status")
        or data.get("service_status")
    )
    process_owner = data.get("process_owner") or data.get("owner")
    evidence_present = bool(data) and source_error is None
    service_ownership_drift = (
        (api_reachable is True or uvicorn_present is True)
        and service_active is False
    )
    evidence_incomplete = evidence_present and (
        api_reachable is None or uvicorn_present is None or service_active is None
    )
    if source_error:
        status = "API_SERVICE_SNAPSHOT_UNAVAILABLE"
    elif not evidence_present:
        status = "API_SERVICE_EVIDENCE_MISSING"
    elif service_ownership_drift:
        status = "API_SERVICE_OWNERSHIP_DRIFT"
    elif evidence_incomplete:
        status = "API_SERVICE_EVIDENCE_INCOMPLETE"
    elif service_active is True and (api_reachable is True or uvicorn_present is True):
        status = "API_SERVICE_OWNERSHIP_ALIGNED"
    else:
        status = "API_SERVICE_REVIEW_REQUIRED"
    return {
        "status": status,
        "source_error": source_error,
        "api_reachable": api_reachable,
        "uvicorn_process_present": uvicorn_present,
        "openclaw_trading_api_service_active": service_active,
        "openclaw_trading_api_service_status": service_status,
        "process_owner": process_owner,
        "service_ownership_drift_present": service_ownership_drift,
        "evidence_incomplete": evidence_incomplete,
        "raw": data,
    }


def _dedupe(items: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = _str(item)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _status(cron: dict[str, Any], api: dict[str, Any]) -> tuple[str, str, list[str]]:
    next_actions: list[str] = []
    cron_drift = cron.get("expected_head_drift_present") is True
    api_drift = api.get("service_ownership_drift_present") is True
    if cron_drift:
        next_actions.append("operator_reinstall_or_update_demo_learning_cron_expected_head_pins")
    if api_drift:
        next_actions.append("operator_choose_single_trading_api_service_owner_then_restart_under_that_owner")
    if cron["status"] == "CRONTAB_SNAPSHOT_UNAVAILABLE":
        next_actions.append("capture_runtime_crontab_snapshot_before_hygiene_decision")
    if cron["status"] == "TARGET_SOURCE_HEAD_MISSING":
        next_actions.append("supply_target_source_head_before_hygiene_decision")
    if cron["status"] == "TARGET_SOURCE_HEAD_INVALID":
        next_actions.append("supply_valid_target_source_head_before_hygiene_decision")
    if cron["status"] == "DEMO_LEARNING_STACK_CRON_ENTRIES_MISSING":
        next_actions.append("operator_review_demo_learning_stack_cron_install_or_snapshot")
    if api["status"] in {"API_SERVICE_SNAPSHOT_UNAVAILABLE", "API_SERVICE_EVIDENCE_MISSING", "API_SERVICE_EVIDENCE_INCOMPLETE"}:
        next_actions.append("capture_read_only_trading_api_service_and_process_snapshot")
    if api["status"] == "API_SERVICE_REVIEW_REQUIRED":
        next_actions.append("operator_review_trading_api_service_ownership_snapshot")
    if cron_drift and api_drift:
        return (
            "RUNTIME_HEALTH_HYGIENE_DRIFT",
            "cron_expected_head_drift_and_api_service_ownership_drift_present",
            _dedupe(next_actions),
        )
    if cron_drift:
        return (
            "CRON_EXPECTED_HEAD_DRIFT",
            "installed_demo_learning_cron_expected_head_pins_do_not_match_target_source_head",
            _dedupe(next_actions),
        )
    if api_drift:
        return (
            "API_SERVICE_OWNERSHIP_DRIFT",
            "api_reachable_or_uvicorn_present_while_openclaw_trading_api_service_inactive",
            _dedupe(next_actions),
        )
    if api["status"] == "API_SERVICE_REVIEW_REQUIRED":
        return (
            "API_SERVICE_REVIEW_REQUIRED",
            "api_service_snapshot_requires_operator_review_before_hygiene_clean",
            _dedupe(next_actions),
        )
    if next_actions:
        return (
            "RUNTIME_HEALTH_HYGIENE_EVIDENCE_INCOMPLETE",
            "read_only_snapshot_missing_or_incomplete",
            _dedupe(next_actions),
        )
    return (
        "RUNTIME_HEALTH_HYGIENE_CLEAN_SOURCE_ONLY",
        "supplied_cron_and_api_snapshots_do_not_show_expected_head_or_service_ownership_drift",
        ["continue_profit_evidence_quality_operator_resolution_before_bounded_probe_selection"],
    )


def build_runtime_health_hygiene_packet(
    *,
    crontab_text: str | None,
    target_source_head: str | None,
    api_service_status: dict[str, Any] | None = None,
    crontab_error: str | None = None,
    api_service_status_error: str | None = None,
    crontab_text_path: Path | None = None,
    api_service_status_path: Path | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    cron = _cron_expected_head_summary(
        crontab_text=crontab_text,
        crontab_error=crontab_error,
        target_source_head=target_source_head,
    )
    api = _api_service_summary(api_service_status, api_service_status_error)
    status, reason, next_actions = _status(cron, api)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "next_actions": next_actions,
        "target_source_head": target_source_head,
        "cron_expected_head": cron,
        "api_service_ownership": api,
        "sources": {
            "crontab_text_path": str(crontab_text_path) if crontab_text_path else None,
            "api_service_status_path": (
                str(api_service_status_path) if api_service_status_path else None
            ),
        },
        "answers": {
            "cron_expected_head_drift_present": cron.get("expected_head_drift_present") is True,
            "api_service_ownership_drift_present": api.get("service_ownership_drift_present") is True,
            "operator_action_required": status != "RUNTIME_HEALTH_HYGIENE_CLEAN_SOURCE_ONLY",
            "crontab_mutation_performed": False,
            "service_restart_performed": False,
            "runtime_mutation_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "bybit_call_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    cron = _dict(packet.get("cron_expected_head"))
    api = _dict(packet.get("api_service_ownership"))
    answers = _dict(packet.get("answers"))
    lines = [
        "# Runtime Health Hygiene Packet",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Target source head: `{packet.get('target_source_head')}`",
        f"- Cron expected-head status: `{cron.get('status')}`",
        f"- API service status: `{api.get('status')}`",
        f"- Operator action required: `{answers.get('operator_action_required')}`",
        f"- Boundary: {BOUNDARY}.",
        "",
        "## Next Actions",
        "",
    ]
    for action in packet.get("next_actions") or []:
        lines.append(f"- `{action}`")
    lines.extend(["", "## Cron Entries", ""])
    for entry in cron.get("entries") or []:
        lines.append(
            "- `{component}` expected `{head}` via `{var}`".format(
                component=entry.get("component"),
                head=entry.get("expected_head"),
                var=entry.get("expected_head_var"),
            )
        )
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crontab-text-file", type=Path)
    parser.add_argument("--api-service-status-json", type=Path)
    parser.add_argument("--target-source-head")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


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


def main() -> int:
    args = _build_parser().parse_args()
    crontab_text, crontab_error = _read_text(args.crontab_text_file)
    api_status, api_error = _read_json(args.api_service_status_json)
    packet = build_runtime_health_hygiene_packet(
        crontab_text=crontab_text,
        target_source_head=args.target_source_head,
        api_service_status=api_status,
        crontab_error=crontab_error,
        api_service_status_error=api_error,
        crontab_text_path=args.crontab_text_file,
        api_service_status_path=args.api_service_status_json,
    )
    markdown = render_markdown(packet)
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.output:
        _write_text(args.output, markdown)
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True, default=str))
    elif not args.output:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
