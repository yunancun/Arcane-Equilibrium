#!/usr/bin/env python3
"""No-mutation cutover preflight for bounded Demo credentials and mode.

The bounded Demo runner is currently blocked before final-window admission when
the Demo API slot does not match the operator-created key or the connector is
still read-only. This helper verifies that the approved source path for fixing
that state exists, and emits a machine-checkable runbook artifact. It never
accepts, prints, validates, or writes API secrets.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import stat
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "bounded_demo_credential_mode_cutover_preflight_v1"
READY_STATUS = "BOUNDED_DEMO_CREDENTIAL_MODE_CUTOVER_PREFLIGHT_READY_NO_MUTATION"
NOT_REQUIRED_STATUS = "BOUNDED_DEMO_CREDENTIAL_MODE_CUTOVER_NOT_REQUIRED_RUNTIME_READY"
SOURCE_BLOCKED_STATUS = "BOUNDED_DEMO_CREDENTIAL_MODE_CUTOVER_BLOCKED_BY_SOURCE_WIRING"
RUNTIME_BLOCKED_STATUS = "BOUNDED_DEMO_CREDENTIAL_MODE_CUTOVER_BLOCKED_BY_UNEXPECTED_RUNTIME_STATE"
INPUT_BLOCKED_STATUS = "BOUNDED_DEMO_CREDENTIAL_MODE_CUTOVER_BLOCKED_BY_INPUT"
READINESS_SCHEMA_VERSION = "bounded_demo_runtime_readiness_v1"
READINESS_READY_STATUS = "BOUNDED_DEMO_RUNTIME_READY_FOR_FINAL_WINDOW_GATES"

DEFAULT_SETTINGS_ROUTES = Path(
    "program_code/exchange_connectors/bybit_connector/control_api_v1/app/settings_routes.py"
)
DEFAULT_CONNECTOR_ENV_FILE = Path(
    "/home/ncyu/BybitOpenClaw/secrets/environment_files/trading_services.env"
)
EXPECTED_RUNTIME_BLOCKERS = {
    "demo_api_slot:demo_api_key_expected_value_mismatch",
    "demo_api_slot:demo_api_key_missing_or_empty",
    "demo_api_slot:demo_api_secret_missing_or_empty",
    "connector_mode:bybit_mode_not_demo",
    "connector_mode:bybit_connector_write_not_enabled",
}
UNEXPECTED_BLOCKER_PREFIXES = (
    "engine_env:",
    "plan:",
    "standing_authorization:",
)
BOUNDARY = (
    "source/runtime read-only cutover preflight only; no API key/secret input, "
    "no secret write, no env/service/runtime mutation, no Bybit private call or "
    "credential validation request, no Decision Lease acquire/release, no order/"
    "cancel/modify, no PG query/write, no writer/adapter enablement, no Cost Gate "
    "lowering, no live/mainnet authority, and no promotion/profit proof"
)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return str(value or "").strip()


def _read_json(path: Path | None) -> tuple[dict[str, Any] | None, str | None]:
    if path is None:
        return None, "not_provided"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "missing"
    except json.JSONDecodeError:
        return None, "invalid_json"
    except OSError as exc:
        return None, f"read_error:{type(exc).__name__}"
    if not isinstance(payload, dict):
        return None, "not_json_object"
    return payload, None


def _sha256_file(path: Path | None) -> str | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mode_octal(path: Path) -> str | None:
    try:
        return oct(stat.S_IMODE(path.stat().st_mode))
    except OSError:
        return None


def _strip_env_value(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1]
    return text


def _read_env_file(path: Path) -> tuple[dict[str, str] | None, str | None]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None, "missing"
    except OSError as exc:
        return None, f"read_error:{type(exc).__name__}"

    values: dict[str, str] = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            values[key] = _strip_env_value(value)
    return values, None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _settings_source_check(path: Path) -> dict[str, Any]:
    try:
        source = path.read_text(encoding="utf-8")
        error = None
    except FileNotFoundError:
        source = ""
        error = "missing"
    except OSError as exc:
        source = ""
        error = f"read_error:{type(exc).__name__}"

    required_tokens = {
        "settings_api_demo_slot_post_route": '@settings_router.post("/api-key/{slot}")',
        "api_key_save_request_model": "class ApiKeySaveRequest",
        "operator_auth_required": "_require_operator_auth",
        "bybit_validation_before_write": "_validate_bybit_credentials",
        "api_key_file_write": '_write_key_file(slot, "api_key"',
        "api_secret_file_write": '_write_key_file(slot, "api_secret"',
        "endpoint_file_write": '_write_key_file(slot, "bybit_endpoint"',
        "slot_whitelist_present": "ALLOWED_SLOTS",
        "demo_slot_allowed": '"demo"',
        "live_demo_slot_allowed": '"live_demo"',
        "live_slot_allowed": '"live"',
    }
    checks = {name: token in source for name, token in required_tokens.items()}
    missing = [name for name, passed in checks.items() if not passed]
    ready = error is None and not missing
    return {
        "status": "READY" if ready else "BLOCKED",
        "path": str(path),
        "present": bool(source),
        "read_error": error,
        "sha256": _sha256_file(path),
        "checks": checks,
        "missing_checks": missing,
        "approved_demo_slot_write_endpoint": "/api/v1/settings/api-key/demo",
        "requires_operator_role": checks.get("operator_auth_required") is True,
        "validates_with_bybit_before_secret_write": (
            checks.get("bybit_validation_before_write") is True
        ),
        "writes_api_secret_values_only_inside_settings_route": (
            checks.get("api_key_file_write") is True
            and checks.get("api_secret_file_write") is True
            and checks.get("endpoint_file_write") is True
        ),
        "ready": ready,
    }


def _connector_env_cutover_preview(path: Path) -> dict[str, Any]:
    values, error = _read_env_file(path)
    current = values or {}
    proposed = {
        "BYBIT_MODE": "demo",
        "BYBIT_CONNECTOR_WRITE_ENABLED": "true",
        "BYBIT_CONNECTOR_HEALTH_STATE": current.get(
            "BYBIT_CONNECTOR_HEALTH_STATE",
            "healthy",
        ),
        "BYBIT_CONNECTOR_CONTRACT_VERSION": current.get(
            "BYBIT_CONNECTOR_CONTRACT_VERSION",
            "v1",
        ),
    }
    blockers: list[str] = []
    if error:
        blockers.append(f"connector_env_{error}")
    if proposed["BYBIT_MODE"] != "demo":
        blockers.append("proposed_mode_not_demo")
    if proposed["BYBIT_CONNECTOR_WRITE_ENABLED"].lower() != "true":
        blockers.append("proposed_write_not_true")
    ready = not blockers
    diff_preview = {
        key: {"current": current.get(key), "proposed": value}
        for key, value in proposed.items()
        if current.get(key) != value
    }
    return {
        "status": "READY" if ready else "BLOCKED",
        "path": str(path),
        "present": values is not None,
        "read_error": error,
        "mode_octal": _mode_octal(path) if values is not None else None,
        "current": {
            "BYBIT_MODE": current.get("BYBIT_MODE"),
            "BYBIT_CONNECTOR_WRITE_ENABLED": current.get(
                "BYBIT_CONNECTOR_WRITE_ENABLED"
            ),
            "BYBIT_CONNECTOR_HEALTH_STATE": current.get(
                "BYBIT_CONNECTOR_HEALTH_STATE"
            ),
            "BYBIT_CONNECTOR_CONTRACT_VERSION": current.get(
                "BYBIT_CONNECTOR_CONTRACT_VERSION"
            ),
        },
        "proposed_demo_only": proposed,
        "diff_preview": diff_preview,
        "blocking_reasons": blockers,
        "ready": ready,
    }


def _readiness_summary(readiness: dict[str, Any] | None, error: str | None, path: Path | None) -> dict[str, Any]:
    payload = readiness or {}
    blockers = [str(item) for item in _list(payload.get("blocking_reasons"))]
    unexpected = [
        reason
        for reason in blockers
        if reason not in EXPECTED_RUNTIME_BLOCKERS
        or reason.startswith(UNEXPECTED_BLOCKER_PREFIXES)
    ]
    answers = _dict(payload.get("answers"))
    authority_clean = all(
        answers.get(key) in (None, False, "NONE")
        for key in (
            "order_capable_action_allowed_by_this_packet",
            "decision_lease_acquire_performed",
            "runtime_mutation_performed",
            "service_restart_performed",
            "env_mutation_performed",
            "writer_enabled_by_this_packet",
            "adapter_enabled_by_this_packet",
            "bybit_private_call_performed",
            "bybit_credential_validation_call_performed",
            "pg_write_performed",
            "order_submission_performed",
            "global_cost_gate_lowering_recommended",
            "live_or_mainnet",
            "live_authority_granted",
            "promotion_evidence",
            "promotion_proof",
        )
    )
    schema_valid = payload.get("schema_version") == READINESS_SCHEMA_VERSION
    status = payload.get("status")
    ready_runtime = status == READINESS_READY_STATUS
    expected_blocked_runtime = (
        schema_valid
        and not ready_runtime
        and not unexpected
        and authority_clean
        and bool(blockers)
    )
    return {
        "path": str(path) if path else None,
        "present": readiness is not None,
        "read_error": error,
        "sha256": _sha256_file(path),
        "schema_version": payload.get("schema_version"),
        "status": status,
        "candidate": payload.get("candidate"),
        "blocking_reasons": blockers,
        "unexpected_blocking_reasons": unexpected,
        "schema_valid": schema_valid,
        "authority_clean": authority_clean,
        "runtime_already_ready": ready_runtime,
        "expected_credential_or_mode_blocker_only": expected_blocked_runtime,
    }


def _top_status(
    readiness: dict[str, Any],
    settings_source: dict[str, Any],
    connector_env: dict[str, Any],
) -> str:
    if readiness["runtime_already_ready"]:
        return NOT_REQUIRED_STATUS
    if not readiness["expected_credential_or_mode_blocker_only"]:
        return RUNTIME_BLOCKED_STATUS
    if not settings_source["ready"]:
        return SOURCE_BLOCKED_STATUS
    if not connector_env["ready"]:
        return SOURCE_BLOCKED_STATUS
    return READY_STATUS


def _state_transition(status: str) -> str:
    if status in {READY_STATUS, NOT_REQUIRED_STATUS}:
        return "DONE_WITH_CONCERNS"
    return "BLOCKED_BY_RUNTIME"


def _next_actions(status: str) -> list[str]:
    if status == READY_STATUS:
        return [
            "enter the Demo API key and secret only through the approved settings API or GUI route",
            "change connector mode to Demo write-enabled only through reviewed runtime config mutation",
            "restart only the required Demo services after config mutation is reviewed",
            "rerun bounded_demo_runtime_readiness before any final-window gate",
        ]
    if status == NOT_REQUIRED_STATUS:
        return [
            "rerun final-window BBO/Decision Lease/Guardian/Rust authority/GUI cap gates",
        ]
    if status == SOURCE_BLOCKED_STATUS:
        return [
            "repair approved settings API or connector env source wiring before any cutover",
        ]
    return [
        "resolve unexpected runtime blockers before credential/mode cutover",
    ]


def _answers(status: str) -> dict[str, Any]:
    return {
        "cutover_preflight_inspected": True,
        "operator_secret_entry_required": status == READY_STATUS,
        "api_key_plaintext_accepted_by_this_packet": False,
        "api_secret_plaintext_accepted_by_this_packet": False,
        "api_secret_value_or_hash_output": False,
        "official_settings_api_path_required": True,
        "connector_env_cutover_preview_only": True,
        "runtime_mutation_performed": False,
        "secret_write_performed": False,
        "env_mutation_performed": False,
        "service_restart_performed": False,
        "bybit_private_call_performed": False,
        "bybit_credential_validation_call_performed": False,
        "decision_lease_acquire_performed": False,
        "order_submission_performed": False,
        "order_capable_action_allowed_by_this_packet": False,
        "writer_enabled_by_this_packet": False,
        "adapter_enabled_by_this_packet": False,
        "global_cost_gate_lowering_recommended": False,
        "main_cost_gate_adjustment": "NONE",
        "live_or_mainnet": False,
        "live_authority_granted": False,
        "promotion_evidence": False,
        "promotion_proof": False,
    }


def build_bounded_demo_credential_mode_cutover_preflight(
    *,
    readiness_json: Path,
    settings_routes_py: Path,
    connector_env_file: Path,
    public_ipv4: str | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = now_utc or _utc_now()
    readiness_payload, readiness_error = _read_json(readiness_json)
    readiness = _readiness_summary(readiness_payload, readiness_error, readiness_json)
    settings_source = _settings_source_check(settings_routes_py)
    connector_env = _connector_env_cutover_preview(connector_env_file)
    status = (
        INPUT_BLOCKED_STATUS
        if readiness_error
        else _top_status(readiness, settings_source, connector_env)
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "profit_first_state_transition": _state_transition(status),
        "public_ipv4_for_bybit_api_allowlist": public_ipv4,
        "readiness": readiness,
        "settings_api_source": settings_source,
        "connector_env_cutover": connector_env,
        "secure_cutover_contract": {
            "api_key_slot": "demo",
            "api_key_write_endpoint": "/api/v1/settings/api-key/demo",
            "credential_validation_required_before_write": True,
            "do_not_put_api_key_or_secret_in_repo_docs_or_process_argv": True,
            "operator_enters_secret_via_gui_or_authenticated_request_body_only": True,
            "post_cutover_required_check": "rerun bounded_demo_runtime_readiness",
            "post_ready_gate_chain": [
                "standing auth freshness",
                "bounded authorization",
                "plan inclusion",
                "final-window BBO/instrument",
                "runner-owned short Decision Lease",
                "Guardian/Rust authority",
                "GUI/Rust RiskConfig cap",
            ],
        },
        "next_actions": _next_actions(status),
        "answers": _answers(status),
        "boundary": BOUNDARY,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readiness-json", type=Path, required=True)
    parser.add_argument("--settings-routes-py", type=Path, default=DEFAULT_SETTINGS_ROUTES)
    parser.add_argument("--connector-env-file", type=Path, default=DEFAULT_CONNECTOR_ENV_FILE)
    parser.add_argument("--public-ipv4")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    packet = build_bounded_demo_credential_mode_cutover_preflight(
        readiness_json=args.readiness_json,
        settings_routes_py=args.settings_routes_py,
        connector_env_file=args.connector_env_file,
        public_ipv4=args.public_ipv4,
    )
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.print_json or not args.json_output:
        print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
