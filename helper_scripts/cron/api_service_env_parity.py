#!/usr/bin/env python3
"""Build a source-only Trading API service env-parity packet.

The packet compares supplied snapshots of the currently reachable manual
uvicorn process with the installed systemd user unit. It never inspects live
processes, calls systemctl/curl/PG/Bybit, restarts services, or grants trading
authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import json
import re
import shlex
from pathlib import Path
from typing import Any

from helper_scripts.cron.runtime_health_hygiene import (
    _contains_authority_signal,
    _read_json,
    _str,
    _utc_now,
)


SCHEMA_VERSION = "api_service_env_parity_packet_v1"
BOUNDARY = (
    "source-only API service env-parity packet from supplied snapshots; no "
    "systemctl/ps/curl/PG/Bybit call, no service restart, no env mutation, no "
    "deploy, no runtime mutation, no Cost Gate lowering, no probe/order/live "
    "authority, and no promotion proof"
)
UNSAFE_BIND_HOSTS = {"0.0.0.0", "::"}
DEFAULT_REQUIRED_ENV_KEYS = (
    "OPENCLAW_BASE_DIR",
    "OPENCLAW_DATA_DIR",
    "OPENCLAW_DATABASE_URL_FILE",
    "OPENCLAW_IPC_SECRET_FILE",
    "OPENCLAW_IPC_SOCKET",
    "OPENCLAW_LEASE_PYTHON_IPC_ENABLED",
    "OPENCLAW_LIVE_AUTH_SIGNING_KEY_FILE",
    "OPENCLAW_STRATEGY_TOGGLE_LIVE_MODE",
)
CUTOVER_PLAN_SCHEMA_VERSION = "api_service_runtime_cutover_plan_v1"
SERVICE_NAME = "openclaw-trading-api.service"
LOCAL_BOUNDARY_TRUE_KEYS = {
    "env_mutation_performed",
    "environment_mutation_performed",
    "process_mutation_performed",
    "process_signal_sent",
    "service_apply_performed",
    "service_mutation_performed",
    "service_unit_written",
    "systemctl_call_performed",
    "unit_file_written",
}
LOCAL_BOUNDARY_TRUE_SUFFIXES = (
    "_env_mutation_performed",
    "_environment_mutation_performed",
    "_process_mutation_performed",
    "_service_apply_performed",
    "_service_mutation_performed",
    "_service_unit_written",
    "_systemctl_call_performed",
    "_unit_file_written",
)
SECRET_NAME_FRAGMENTS = (
    "DATABASE_URL",
    "DSN",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "PRIVATE_KEY",
    "SIGNING_KEY",
    "AUTH_KEY",
    "API_KEY",
)
SECRET_OPTION_NAMES = {
    "--api-key",
    "--apikey",
    "--auth-key",
    "--database-url",
    "--key",
    "--password",
    "--private-key",
    "--secret",
    "--signing-key",
    "--token",
}


def _split_cmdline(value: str | None) -> list[str]:
    text = _str(value)
    if not text:
        return []
    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


def _value_present(value: Any) -> bool:
    if value is None or value is False:
        return False
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "none", "null", "no"}
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, (dict, list, tuple, set)):
        return bool(value)
    return bool(value)


def _contains_boundary_signal(value: Any, path: str = "") -> str | None:
    shared = _contains_authority_signal(value, path)
    if shared:
        return shared
    if isinstance(value, dict):
        for key, item in value.items():
            key_str = str(key)
            key_path = f"{path}.{key_str}" if path else key_str
            key_lower = key_str.lower()
            if (
                key_lower in LOCAL_BOUNDARY_TRUE_KEYS
                or key_lower.endswith(LOCAL_BOUNDARY_TRUE_SUFFIXES)
            ) and _value_present(item):
                return key_path
            found = _contains_boundary_signal(item, key_path)
            if found:
                return found
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            found = _contains_boundary_signal(item, f"{path}[{idx}]")
            if found:
                return found
    return None


def _is_secret_name(name: str) -> bool:
    upper = name.upper().replace("-", "_")
    parts = {part for part in upper.split("_") if part}
    return (
        any(fragment in upper for fragment in SECRET_NAME_FRAGMENTS)
        or "KEY" in parts
    )


def _redact_argv(argv: list[str]) -> list[str]:
    redacted: list[str] = []
    redact_next = False
    for token in argv:
        if redact_next:
            redacted.append("REDACTED")
            redact_next = False
            continue
        option_name = token.split("=", 1)[0]
        if option_name.lower() in SECRET_OPTION_NAMES or (
            option_name.startswith("-") and _is_secret_name(option_name)
        ):
            if "=" in token:
                redacted.append(f"{option_name}=REDACTED")
            else:
                redacted.append(token)
                redact_next = True
            continue
        if "=" in token:
            key, _value = token.split("=", 1)
            if _is_secret_name(key):
                redacted.append(f"{key}=REDACTED")
                continue
        redacted.append(token)
    return redacted


def _option_value(argv: list[str], name: str) -> str | None:
    for index, token in enumerate(argv):
        if token == name and index + 1 < len(argv):
            return argv[index + 1]
        if token.startswith(f"{name}="):
            return token.split("=", 1)[1]
    return None


def _int_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _command_summary(cmdline: str | None) -> dict[str, Any]:
    argv = _split_cmdline(cmdline)
    redacted_argv = _redact_argv(argv)
    return {
        "cmdline": shlex.join(redacted_argv) if redacted_argv else "",
        "argv": redacted_argv,
        "redaction_applied": redacted_argv != argv,
        "app": next((token for token in argv if token.endswith(":app")), None),
        "host": _option_value(argv, "--host"),
        "port": _int_or_none(_option_value(argv, "--port")),
        "workers": _int_or_none(_option_value(argv, "--workers")),
    }


def _best_api_process(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    rows = snapshot.get("api_processes")
    if not isinstance(rows, list):
        return None
    candidates = [row for row in rows if isinstance(row, dict)]
    if not candidates:
        return None

    def score(row: dict[str, Any]) -> tuple[int, int, int]:
        cmd = _str(row.get("cmdline"))
        parsed = _command_summary(cmd)
        return (
            1 if parsed.get("app") == "app.main:app" else 0,
            1 if parsed.get("workers") is not None else 0,
            1 if _str(row.get("ppid")) == "1" else 0,
        )

    return sorted(candidates, key=score, reverse=True)[0]


def _parse_show_output(text: str | None) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw_line in _str(text).splitlines():
        if "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def _parse_environment_assignments(value: str | None) -> dict[str, str]:
    try:
        tokens = shlex.split(_str(value), comments=False, posix=True)
    except ValueError:
        tokens = _str(value).split()
    env: dict[str, str] = {}
    for token in tokens:
        if "=" not in token:
            continue
        key, env_value = token.split("=", 1)
        if key:
            env[key] = env_value
    return env


def _parse_systemd_cat(text: str | None) -> dict[str, Any]:
    unit: dict[str, Any] = {"environment": {}}
    for raw_line in _str(text).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("["):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key == "Environment":
            unit["environment"].update(_parse_environment_assignments(value))
        elif key in {"ExecStart", "WorkingDirectory", "Restart", "RestartSec"}:
            unit[key] = value
    return unit


def _systemd_cat_file_content(text: str | None) -> dict[str, Any]:
    """Return redacted file-like unit content from `systemctl cat` output."""
    lines: list[str] = []
    source_fragments: list[str] = []
    redaction_applied = False
    raw_text = text if isinstance(text, str) else str(text or "")
    for raw_line in raw_text.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        newline = raw_line[len(line):]
        if line.startswith("# /") and ".service" in line:
            source_fragments.append(line[2:].strip())
            continue
        redacted_line, redacted = _redacted_unit_line(line)
        if redacted_line is not None:
            lines.append(redacted_line + newline)
            redaction_applied = redaction_applied or redacted
            continue
        lines.append(raw_line)
    dropins_detected = any(".service.d/" in fragment for fragment in source_fragments)
    single_fragment_only = len(source_fragments) == 1 and not dropins_detected
    return {
        "content": "".join(lines),
        "redaction_applied": redaction_applied,
        "source_fragments": source_fragments,
        "single_fragment_only": single_fragment_only,
        "dropins_detected": dropins_detected,
    }


def _redacted_unit_line(line: str) -> tuple[str, bool] | tuple[None, bool]:
    stripped = line.strip()
    if "=" not in stripped:
        return None, False
    key, value = stripped.split("=", 1)
    if key == "Environment":
        return _redacted_environment_line(line)
    if key == "ExecStart":
        argv = _split_cmdline(value)
        redacted_argv = _redact_argv(argv)
        if redacted_argv != argv:
            return f"{key}={shlex.join(redacted_argv)}", True
    return None, False


def _redacted_environment_line(line: str) -> tuple[str, bool]:
    prefix, value = line.split("=", 1)
    env = _parse_environment_assignments(value)
    if not env:
        return line, False
    redacted = False
    safe_env: dict[str, str] = {}
    for key, env_value in env.items():
        safe = _safe_unit_env_value(key, env_value)
        if safe is None:
            safe_env[key] = "REDACTED"
            redacted = True
        else:
            safe_env[key] = safe
    if not redacted:
        return line, False
    return _environment_line(prefix.strip(), safe_env), redacted


def _extract_show_exec_start(value: str | None) -> str | None:
    match = re.search(r"argv\[\]=(.*?) ; ignore_errors=", _str(value))
    if match:
        return match.group(1).strip()
    return None


def _systemd_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    raw_cat_stdout = _dict(snapshot.get("systemd_cat")).get("stdout")
    cat_stdout = _str(raw_cat_stdout)
    show_stdout = _str(_dict(snapshot.get("systemd_show")).get("stdout"))
    unit = _parse_systemd_cat(cat_stdout)
    show = _parse_show_output(show_stdout)
    if "ExecStart" not in unit:
        extracted = _extract_show_exec_start(show.get("ExecStart"))
        if extracted:
            unit["ExecStart"] = extracted
    if "WorkingDirectory" not in unit and show.get("WorkingDirectory"):
        unit["WorkingDirectory"] = show["WorkingDirectory"]
    if show.get("Environment"):
        show_env = _parse_environment_assignments(show.get("Environment"))
        show_env.update(_dict(unit.get("environment")))
        unit["environment"] = show_env
    return {
        "unit": unit,
        "show": show,
        "command": _command_summary(unit.get("ExecStart")),
        "active_state": show.get("ActiveState"),
        "sub_state": show.get("SubState"),
        "unit_file_state": show.get("UnitFileState"),
        "fragment_path": show.get("FragmentPath"),
        "main_pid": _int_or_none(show.get("MainPID")),
        "working_directory": unit.get("WorkingDirectory"),
        "environment": _dict(unit.get("environment")),
        "cat_file_content": _systemd_cat_file_content(raw_cat_stdout),
    }


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _snapshot_from_inputs(
    *,
    combined_snapshot: dict[str, Any] | None,
    process_snapshot: dict[str, Any] | None,
    systemd_snapshot: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    combined = _dict(combined_snapshot)
    process = _dict(process_snapshot) or combined
    systemd = _dict(systemd_snapshot) or combined
    return process, systemd


def _env_missing(
    *,
    process_env: dict[str, Any],
    unit_env: dict[str, Any],
    required_env_keys: tuple[str, ...],
) -> list[str]:
    missing: list[str] = []
    for key in required_env_keys:
        if key in process_env and key not in unit_env:
            missing.append(key)
    return missing


def _safe_unit_env_value(key: str, value: Any) -> str | None:
    text = _str(value)
    if not text:
        return None
    if _is_secret_name(key) and not key.endswith("_FILE"):
        return None
    return text


def _environment_line(prefix: str, env: dict[str, str]) -> str:
    assignments = [
        f"{key}={shlex.quote(value)}"
        for key, value in sorted(env.items())
    ]
    return f"{prefix}={' '.join(assignments)}"


def _unit_environment_proposal(
    *,
    process_env: dict[str, Any],
    required_env_keys: tuple[str, ...],
) -> dict[str, Any]:
    materialized: dict[str, str] = {}
    redacted_required: list[str] = []
    missing_from_process: list[str] = []
    for key in required_env_keys:
        if key not in process_env:
            missing_from_process.append(key)
            continue
        safe = _safe_unit_env_value(key, process_env.get(key))
        if safe is None:
            redacted_required.append(key)
            continue
        materialized[key] = safe
    return {
        "materialized_env": materialized,
        "materialized_environment_lines": [
            _environment_line("Environment", {key: value})
            for key, value in sorted(materialized.items())
        ],
        "redacted_required_env_keys": redacted_required,
        "missing_required_env_keys_from_process_snapshot": missing_from_process,
    }


def _safe_merged_unit_env(
    *,
    current_unit_env: dict[str, Any],
    proposed_env: dict[str, str],
) -> tuple[dict[str, str], list[str]]:
    merged: dict[str, str] = {}
    redacted_existing: list[str] = []
    for key, value in sorted(current_unit_env.items()):
        safe = _safe_unit_env_value(key, value)
        if safe is None:
            redacted_existing.append(key)
            continue
        merged[key] = safe
    merged.update(proposed_env)
    return merged, redacted_existing


def _proposed_exec_start(
    *,
    process_command: dict[str, Any],
    unit_command: dict[str, Any],
) -> str | None:
    app = _str(process_command.get("app")) or _str(unit_command.get("app"))
    host = _str(process_command.get("host"))
    port = process_command.get("port")
    workers = process_command.get("workers")
    if not app or not host or port is None or workers is None:
        return None
    unit_prefix = (
        None
        if unit_command.get("redaction_applied")
        else _uvicorn_prefix(unit_command.get("argv"), app)
    )
    process_prefix = (
        None
        if process_command.get("redaction_applied")
        else _uvicorn_prefix(process_command.get("argv"), app)
    )
    prefix = unit_prefix or process_prefix
    if not prefix:
        return None
    return shlex.join(prefix + [
        "--host",
        host,
        "--port",
        str(port),
        "--workers",
        str(workers),
    ])


def _uvicorn_prefix(argv: Any, app: str) -> list[str] | None:
    if not isinstance(argv, list) or not app:
        return None
    try:
        app_index = argv.index(app)
    except ValueError:
        return None
    prefix = [_str(token) for token in argv[:app_index] if _str(token)]
    if not prefix:
        return None
    if not any(Path(token).name == "uvicorn" or token == "uvicorn" for token in prefix):
        return None
    return prefix + [app]


def _proposed_unit_file(
    *,
    current_unit_content: str,
    current_unit_redaction_applied: bool,
    source_fragments: list[str],
    single_fragment_only: bool,
    dropins_detected: bool,
    proposed_working_directory: str | None,
    proposed_exec_start: str | None,
    current_unit_env: dict[str, Any],
    proposed_env: dict[str, str],
) -> dict[str, Any]:
    current_sha = (
        hashlib.sha256(current_unit_content.encode("utf-8")).hexdigest()
        if current_unit_content
        else None
    )
    if not current_unit_content or not proposed_working_directory or not proposed_exec_start:
        return {
            "available": False,
            "reason": "current_unit_or_proposed_fields_missing",
            "source_fragments": source_fragments,
            "single_fragment_only": single_fragment_only,
            "dropins_detected": dropins_detected,
            "current_unit_file_sha256": current_sha,
        }
    if not single_fragment_only or dropins_detected:
        return {
            "available": False,
            "reason": "multiple_systemd_fragments_present",
            "current_unit_file_content": current_unit_content,
            "current_unit_file_sha256": current_sha,
            "source_fragments": source_fragments,
            "single_fragment_only": single_fragment_only,
            "dropins_detected": dropins_detected,
            "current_content_redaction_applied": current_unit_redaction_applied,
        }

    merged_env, redacted_existing_env_keys = _safe_merged_unit_env(
        current_unit_env=current_unit_env,
        proposed_env=proposed_env,
    )
    replacement_lines = [
        f"WorkingDirectory={proposed_working_directory}",
        f"ExecStart={proposed_exec_start}",
    ]
    replacement_lines.extend(
        _environment_line("Environment", {key: value})
        for key, value in sorted(merged_env.items())
    )

    current_lines = current_unit_content.rstrip("\n").splitlines()
    proposed_lines: list[str] = []
    in_service = False
    service_section_count = 0
    replacements_inserted = False
    for raw_line in current_lines:
        stripped = raw_line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_service = stripped == "[Service]"
            proposed_lines.append(raw_line)
            if in_service:
                service_section_count += 1
                if service_section_count == 1:
                    proposed_lines.extend(replacement_lines)
                    replacements_inserted = True
            continue
        if in_service:
            key = stripped.split("=", 1)[0] if "=" in stripped else ""
            if key in {"WorkingDirectory", "ExecStart", "Environment"}:
                continue
        proposed_lines.append(raw_line)

    if service_section_count != 1 or not replacements_inserted:
        return {
            "available": False,
            "reason": "service_section_missing_or_duplicated",
            "current_unit_file_content": current_unit_content,
            "current_unit_file_sha256": current_sha,
            "source_fragments": source_fragments,
            "single_fragment_only": single_fragment_only,
            "dropins_detected": dropins_detected,
            "service_section_count": service_section_count,
            "current_content_redaction_applied": current_unit_redaction_applied,
        }

    proposed_content = "\n".join(proposed_lines).rstrip() + "\n"
    proposed_contains_redactions = "REDACTED" in proposed_content
    diff_lines = list(difflib.unified_diff(
        current_unit_content.rstrip("\n").splitlines(),
        proposed_content.rstrip("\n").splitlines(),
        fromfile="current/openclaw-trading-api.service",
        tofile="proposed/openclaw-trading-api.service",
        lineterm="",
    ))
    return {
        "available": True,
        "current_unit_file_content": current_unit_content,
        "current_unit_file_sha256": current_sha,
        "proposed_unit_file_content": proposed_content,
        "proposed_unit_file_sha256": hashlib.sha256(
            proposed_content.encode("utf-8")
        ).hexdigest(),
        "unified_diff": "\n".join(diff_lines) + ("\n" if diff_lines else ""),
        "source_fragments": source_fragments,
        "single_fragment_only": single_fragment_only,
        "dropins_detected": dropins_detected,
        "current_content_redaction_applied": current_unit_redaction_applied,
        "proposed_unit_file_contains_redactions": proposed_contains_redactions,
        "redacted_existing_env_keys": redacted_existing_env_keys,
    }


def _pre_apply_revalidation_contract(
    *,
    process_row: dict[str, Any] | None,
    process_command: dict[str, Any],
    systemd: dict[str, Any],
    proposed_unit_file: dict[str, Any],
) -> dict[str, Any]:
    process_env = _dict(_dict(process_row).get("selected_env"))
    contract = {
        "requires_fresh_snapshot_before_apply": True,
        "expected_manual_process": {
            "pid": _dict(process_row).get("pid"),
            "ppid": _dict(process_row).get("ppid"),
            "cwd": _dict(process_row).get("cwd"),
            "cmdline": process_command.get("cmdline"),
            "cmdline_sha256": hashlib.sha256(
                _str(process_command.get("cmdline")).encode("utf-8")
            ).hexdigest(),
            "command_redaction_applied": bool(process_command.get("redaction_applied")),
            "selected_env_keys": sorted(process_env.keys()),
        },
        "expected_listener": {
            "host": process_command.get("host"),
            "port": process_command.get("port"),
            "workers": process_command.get("workers"),
        },
        "expected_current_unit": {
            "fragment_path": systemd.get("fragment_path"),
            "unit_file_state": systemd.get("unit_file_state"),
            "current_unit_file_sha256": proposed_unit_file.get(
                "current_unit_file_sha256"
            ),
            "current_content_redaction_applied": proposed_unit_file.get(
                "current_content_redaction_applied"
            ),
            "source_fragments": proposed_unit_file.get("source_fragments"),
            "single_fragment_only": proposed_unit_file.get("single_fragment_only"),
            "dropins_detected": proposed_unit_file.get("dropins_detected"),
        },
        "expected_proposed_unit": {
            "proposed_unit_file_sha256": proposed_unit_file.get(
                "proposed_unit_file_sha256"
            ),
            "proposed_unit_file_contains_redactions": proposed_unit_file.get(
                "proposed_unit_file_contains_redactions"
            ),
        },
    }
    contract["contract_sha256"] = hashlib.sha256(
        json.dumps(contract, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return contract


def _runtime_cutover_plan(
    *,
    process_row: dict[str, Any] | None,
    process_command: dict[str, Any],
    systemd: dict[str, Any],
    required_env_keys: tuple[str, ...],
    findings: list[dict[str, Any]],
    evidence_gaps: list[str],
    authority_signal: str | None,
) -> dict[str, Any]:
    process_env = _dict(_dict(process_row).get("selected_env"))
    unit_command = _dict(systemd.get("command"))
    current_unit = _dict(systemd.get("cat_file_content"))
    env_proposal = _unit_environment_proposal(
        process_env=process_env,
        required_env_keys=required_env_keys,
    )
    proposed_exec_start = _proposed_exec_start(
        process_command=process_command,
        unit_command=unit_command,
    )
    blockers = []
    if authority_signal:
        blockers.append("authority_or_runtime_mutation_signal_present")
    if evidence_gaps:
        blockers.append("evidence_incomplete")
    if not proposed_exec_start:
        blockers.append("proposed_exec_start_incomplete")
    if env_proposal["missing_required_env_keys_from_process_snapshot"]:
        blockers.append("process_runtime_env_snapshot_incomplete")
    proposed_working_directory = _dict(process_row).get("cwd") or systemd.get(
        "working_directory"
    )
    unit_app = _str(unit_command.get("app"))
    process_app = _str(process_command.get("app"))
    app_mismatch = bool(unit_app and process_app and unit_app != process_app)
    current_unit_content = current_unit.get("content")
    proposed_unit_file = _proposed_unit_file(
        current_unit_content=(
            current_unit_content if isinstance(current_unit_content, str) else ""
        ),
        current_unit_redaction_applied=bool(current_unit.get("redaction_applied")),
        source_fragments=list(current_unit.get("source_fragments") or []),
        single_fragment_only=bool(current_unit.get("single_fragment_only", False)),
        dropins_detected=bool(current_unit.get("dropins_detected", False)),
        proposed_working_directory=_str(proposed_working_directory),
        proposed_exec_start=proposed_exec_start,
        current_unit_env=_dict(systemd.get("environment")),
        proposed_env=_dict(env_proposal.get("materialized_env")),
    )
    if not proposed_unit_file.get("available"):
        blockers.append("proposed_unit_file_content_incomplete")
    if app_mismatch:
        blockers.append("unit_process_app_mismatch")
    if unit_command.get("redaction_applied") or process_command.get("redaction_applied"):
        blockers.append("command_source_redaction_present")
    if proposed_unit_file.get("current_content_redaction_applied"):
        blockers.append("current_unit_file_redaction_present")
    if proposed_unit_file.get("proposed_unit_file_contains_redactions"):
        blockers.append("proposed_unit_file_redaction_present")
    if proposed_unit_file.get("redacted_existing_env_keys"):
        blockers.append("existing_unit_direct_secret_env_redacted")
    unit_file_path = _str(systemd.get("fragment_path")) or (
        "~/.config/systemd/user/openclaw-trading-api.service"
    )
    current_pid = _dict(process_row).get("pid")
    guarded_stop = (
        "verify pid/cmdline/cwd still match the reviewed snapshot, then send "
        f"SIGTERM to manual uvicorn master pid {current_pid}"
        if current_pid
        else "manual uvicorn pid unavailable; do not cut over"
    )
    return {
        "schema_version": CUTOVER_PLAN_SCHEMA_VERSION,
        "apply_allowed_by_this_packet": False,
        "restart_allowed_by_this_packet": False,
        "requires_e3_review_before_apply": True,
        "requires_runtime_mutation_checkpoint_before_apply": True,
        "unit_file_path": unit_file_path,
        "service_name": SERVICE_NAME,
        "proposed_exec_start": proposed_exec_start,
        "proposed_working_directory": proposed_working_directory,
        "proposed_environment": env_proposal,
        "proposed_unit_file": proposed_unit_file,
        "pre_apply_revalidation_contract": _pre_apply_revalidation_contract(
            process_row=process_row,
            process_command=process_command,
            systemd=systemd,
            proposed_unit_file=proposed_unit_file,
        ),
        "unit_enablement_review": {
            "current_unit_file_state": systemd.get("unit_file_state"),
            "enable_allowed_by_this_packet": False,
            "requires_e3_review_before_enable": True,
            "enable_step_template": (
                f"systemctl --user enable {SERVICE_NAME}"
                if systemd.get("unit_file_state") == "disabled"
                else None
            ),
            "rollback_step_template": f"systemctl --user disable {SERVICE_NAME}",
        },
        "exec_start_prefix_review": {
            "unit_app": unit_app or None,
            "process_app": process_app or None,
            "unit_process_app_mismatch": app_mismatch,
            "unit_command_redaction_applied": bool(unit_command.get("redaction_applied")),
            "process_command_redaction_applied": bool(
                process_command.get("redaction_applied")
            ),
            "requires_pm_acceptance_before_apply": True,
            "note": (
                "proposed ExecStart may reuse a reviewed systemd uvicorn prefix even "
                "when the manual process was launched through an equivalent wrapper"
            ),
        },
        "plan_blockers": blockers,
        "preflight_checks": [
            "confirm current manual uvicorn pid/cmdline/cwd/env keys still match reviewed snapshot",
            "confirm port 8000 listener is the reviewed manual uvicorn master/workers",
            "confirm updated unit binds only to the reviewed Tailscale host, not 0.0.0.0 or ::",
            "confirm required runtime env keys are materialized without copying secret values into reports",
            "confirm no Cost Gate/probe/order/live/Bybit/PG mutation flags are present",
        ],
        "apply_sequence_template": [
            f"write reviewed unit content to {unit_file_path}",
            "systemctl --user daemon-reload",
            guarded_stop,
            f"systemctl --user start {SERVICE_NAME}",
            "verify listener, console redirect, authenticated health surface, and service MainPID",
        ],
        "rollback_sequence_template": [
            f"systemctl --user stop {SERVICE_NAME}",
            "restore the previous unit file from timestamped backup",
            "systemctl --user daemon-reload",
            "restart the reviewed manual uvicorn command with the reviewed env file/source",
            "verify listener and console reachability return to the pre-cutover state",
        ],
        "verification_checks": [
            f"systemctl --user show {SERVICE_NAME} ActiveState MainPID ExecStart Environment",
            "ss -ltnp sport = :8000",
            "curl authenticated /api/v1/system/health or existing console smoke with proper auth",
            "rerun api_service_env_parity packet against fresh post-cutover snapshots",
        ],
        "risk_notes": [
            "manual process and systemd service cannot bind the same host:port simultaneously; a guarded handoff is required",
            "this packet intentionally does not perform daemon-reload, start, stop, kill, or file writes",
            "the broad Demo API authorization is not live/mainnet/probe/order authority",
        ],
    }


def _build_findings(
    *,
    process_row: dict[str, Any] | None,
    process_command: dict[str, Any],
    systemd: dict[str, Any],
    required_env_keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    unit_command = _dict(systemd.get("command"))
    process_env = _dict(_dict(process_row).get("selected_env"))
    unit_env = _dict(systemd.get("environment"))
    active_state = _str(systemd.get("active_state"))
    main_pid = systemd.get("main_pid")

    if process_row and active_state != "active":
        findings.append({
            "id": "service_inactive_while_manual_process_present",
            "severity": "high",
            "process_pid": process_row.get("pid"),
            "active_state": active_state or None,
            "main_pid": main_pid,
        })
    if unit_command.get("host") in UNSAFE_BIND_HOSTS:
        findings.append({
            "id": "unsafe_unit_bind_host",
            "severity": "high",
            "unit_host": unit_command.get("host"),
            "reason": "unit binds Trading API on all interfaces",
        })
    if process_command.get("host") and unit_command.get("host") and (
        process_command.get("host") != unit_command.get("host")
    ):
        findings.append({
            "id": "bind_host_mismatch",
            "severity": "medium",
            "process_host": process_command.get("host"),
            "unit_host": unit_command.get("host"),
        })
    if process_command.get("port") and unit_command.get("port") and (
        process_command.get("port") != unit_command.get("port")
    ):
        findings.append({
            "id": "port_mismatch",
            "severity": "high",
            "process_port": process_command.get("port"),
            "unit_port": unit_command.get("port"),
        })
    if process_command.get("workers") != unit_command.get("workers"):
        findings.append({
            "id": "worker_count_mismatch",
            "severity": "medium",
            "process_workers": process_command.get("workers"),
            "unit_workers": unit_command.get("workers"),
        })
    process_cwd = _str(_dict(process_row).get("cwd"))
    unit_cwd = _str(systemd.get("working_directory"))
    if process_cwd and unit_cwd and process_cwd != unit_cwd:
        findings.append({
            "id": "working_directory_mismatch",
            "severity": "medium",
            "process_cwd": process_cwd,
            "unit_working_directory": unit_cwd,
        })
    missing_env = _env_missing(
        process_env=process_env,
        unit_env=unit_env,
        required_env_keys=required_env_keys,
    )
    if missing_env:
        findings.append({
            "id": "unit_missing_runtime_env_keys",
            "severity": "high",
            "missing_env_keys": missing_env,
        })
    if process_env:
        process_missing_env = [
            key for key in required_env_keys if key not in process_env
        ]
        if process_missing_env:
            findings.append({
                "id": "process_missing_required_runtime_env_keys",
                "severity": "medium",
                "missing_env_keys": process_missing_env,
            })
    return findings


def build_api_service_env_parity_packet(
    *,
    combined_snapshot: dict[str, Any] | None = None,
    process_snapshot: dict[str, Any] | None = None,
    systemd_snapshot: dict[str, Any] | None = None,
    required_env_keys: tuple[str, ...] = DEFAULT_REQUIRED_ENV_KEYS,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = now_utc or _utc_now()
    process_payload, systemd_payload = _snapshot_from_inputs(
        combined_snapshot=combined_snapshot,
        process_snapshot=process_snapshot,
        systemd_snapshot=systemd_snapshot,
    )
    authority_signal = _contains_boundary_signal({
        "process_snapshot": process_payload,
        "systemd_snapshot": systemd_payload,
    })
    process_row = _best_api_process(process_payload)
    process_command = _command_summary(_dict(process_row).get("cmdline"))
    systemd = _systemd_summary(systemd_payload)
    evidence_gaps: list[str] = []
    if not process_payload:
        evidence_gaps.append("process_snapshot_missing")
    if not systemd_payload:
        evidence_gaps.append("systemd_snapshot_missing")
    if process_payload and not process_row:
        evidence_gaps.append("manual_uvicorn_process_not_found")
    if process_row:
        raw_selected_env = process_row.get("selected_env")
        if not isinstance(raw_selected_env, dict):
            evidence_gaps.append("process_selected_env_snapshot_missing")
        elif required_env_keys and not any(
            key in raw_selected_env for key in required_env_keys
        ):
            evidence_gaps.append("process_selected_runtime_env_keys_missing")
    if systemd_payload and not _dict(systemd.get("unit")).get("ExecStart"):
        evidence_gaps.append("systemd_exec_start_missing")

    findings = _build_findings(
        process_row=process_row,
        process_command=process_command,
        systemd=systemd,
        required_env_keys=required_env_keys,
    )

    cutover_plan = _runtime_cutover_plan(
        process_row=process_row,
        process_command=process_command,
        systemd=systemd,
        required_env_keys=required_env_keys,
        findings=findings,
        evidence_gaps=evidence_gaps,
        authority_signal=authority_signal,
    )

    if authority_signal:
        status = "API_SERVICE_ENV_PARITY_BOUNDARY_VIOLATION"
        reason = "supplied_snapshot_contains_authority_or_mutation_signal"
    elif evidence_gaps:
        status = "API_SERVICE_ENV_PARITY_EVIDENCE_INCOMPLETE"
        reason = "required_snapshot_evidence_missing"
    elif cutover_plan.get("plan_blockers"):
        status = "API_SERVICE_ENV_PARITY_CUTOVER_PLAN_BLOCKED"
        reason = "runtime_cutover_plan_blockers_present"
    elif findings:
        status = "API_SERVICE_ENV_PARITY_DRIFT"
        reason = "manual_process_and_systemd_unit_not_env_equivalent"
    else:
        status = "API_SERVICE_ENV_PARITY_CLEAN_SOURCE_ONLY"
        reason = "manual_process_and_systemd_unit_env_equivalent_in_supplied_snapshots"

    drift_present = status == "API_SERVICE_ENV_PARITY_DRIFT"
    boundary_violation = status == "API_SERVICE_ENV_PARITY_BOUNDARY_VIOLATION"
    evidence_incomplete = status == "API_SERVICE_ENV_PARITY_EVIDENCE_INCOMPLETE"
    plan_blocked = status == "API_SERVICE_ENV_PARITY_CUTOVER_PLAN_BLOCKED"
    next_actions: list[str]
    if boundary_violation:
        next_actions = ["remove_authority_or_mutation_signals_from_supplied_snapshot"]
    elif evidence_incomplete:
        next_actions = ["supply_process_and_systemd_snapshots_no_restart"]
    elif plan_blocked:
        next_actions = ["repair_cutover_plan_blockers_before_runtime_apply_review"]
    elif drift_present:
        next_actions = [
            "draft_no_restart_systemd_unit_env_parity_patch",
            "e3_review_api_service_owner_parity_plan_before_restart",
            "keep_current_manual_uvicorn_owner_until_parity_acceptance",
        ]
    else:
        next_actions = ["no_service_restart_needed_from_this_packet"]

    missing_env_keys = []
    for finding in findings:
        if finding.get("id") == "unit_missing_runtime_env_keys":
            missing_env_keys = list(finding.get("missing_env_keys") or [])
            break

    return {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "boundary": BOUNDARY,
        "answers": {
            "operator_action_required": bool(
                boundary_violation or evidence_incomplete or plan_blocked or drift_present
            ),
            "api_service_env_parity_drift_present": drift_present,
            "api_service_cutover_plan_blocked": plan_blocked,
            "authority_boundary_violation_present": boundary_violation,
            "service_restart_performed": False,
            "runtime_mutation_performed": False,
            "env_mutation_performed": False,
            "crontab_mutation_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "bybit_call_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "live_authority_granted": False,
            "promotion_evidence": False,
        },
        "evidence_gaps": evidence_gaps,
        "authority_signal_path": authority_signal,
        "manual_process": {
            "present": process_row is not None,
            "pid": _dict(process_row).get("pid"),
            "ppid": _dict(process_row).get("ppid"),
            "cwd": _dict(process_row).get("cwd"),
            "exe": _dict(process_row).get("exe"),
            "command": process_command,
            "selected_env_keys": sorted(_dict(_dict(process_row).get("selected_env")).keys()),
        },
        "systemd_unit": {
            "active_state": systemd.get("active_state"),
            "sub_state": systemd.get("sub_state"),
            "unit_file_state": systemd.get("unit_file_state"),
            "fragment_path": systemd.get("fragment_path"),
            "main_pid": systemd.get("main_pid"),
            "working_directory": systemd.get("working_directory"),
            "command": systemd.get("command"),
            "environment_keys": sorted(_dict(systemd.get("environment")).keys()),
        },
        "findings": findings,
        "no_restart_patch_proposal": {
            "restart_allowed_by_this_packet": False,
            "target_bind_host": process_command.get("host"),
            "target_port": process_command.get("port"),
            "target_workers": process_command.get("workers"),
            "target_working_directory": _dict(process_row).get("cwd"),
            "environment_keys_to_materialize": missing_env_keys,
            "do_not_copy_secret_values_into_reports": True,
            "requires_e3_review_before_apply": True,
        },
        "runtime_cutover_plan": cutover_plan,
        "next_actions": next_actions,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# API Service Env-Parity Packet",
        "",
        f"- schema_version: `{packet.get('schema_version')}`",
        f"- status: `{packet.get('status')}`",
        f"- reason: `{packet.get('reason')}`",
        f"- boundary: {packet.get('boundary')}",
        "",
        "## Manual Process",
        "",
        f"- present: `{packet['manual_process'].get('present')}`",
        f"- pid: `{packet['manual_process'].get('pid')}`",
        f"- cwd: `{packet['manual_process'].get('cwd')}`",
        f"- command: `{packet['manual_process'].get('command', {}).get('cmdline')}`",
        "",
        "## Systemd Unit",
        "",
        f"- active_state: `{packet['systemd_unit'].get('active_state')}`",
        f"- unit_file_state: `{packet['systemd_unit'].get('unit_file_state')}`",
        f"- working_directory: `{packet['systemd_unit'].get('working_directory')}`",
        f"- command: `{packet['systemd_unit'].get('command', {}).get('cmdline')}`",
        "",
        "## Runtime Cutover Plan",
        "",
        f"- apply_allowed_by_this_packet: `{packet['runtime_cutover_plan'].get('apply_allowed_by_this_packet')}`",
        f"- proposed_exec_start: `{packet['runtime_cutover_plan'].get('proposed_exec_start')}`",
        f"- plan_blockers: `{packet['runtime_cutover_plan'].get('plan_blockers')}`",
        "",
        "## Findings",
        "",
    ]
    findings = packet.get("findings") or []
    if findings:
        for finding in findings:
            lines.append(f"- `{finding.get('id')}` severity=`{finding.get('severity')}`")
    else:
        lines.append("- none")
    lines.extend(["", "## No-Authority Answers", ""])
    for key, value in packet.get("answers", {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Next Actions", ""])
    for action in packet.get("next_actions", []):
        lines.append(f"- `{action}`")
    lines.append("")
    return "\n".join(lines)


def _load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    payload, error = _read_json(path)
    if error:
        return {"_snapshot_read_error": error, "_snapshot_path": str(path)}
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--combined-snapshot-json", type=Path)
    parser.add_argument("--process-snapshot-json", type=Path)
    parser.add_argument("--systemd-snapshot-json", type=Path)
    parser.add_argument("--required-env-key", action="append", default=[])
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    args = parser.parse_args()

    required_env_keys = tuple(args.required_env_key) or DEFAULT_REQUIRED_ENV_KEYS
    packet = build_api_service_env_parity_packet(
        combined_snapshot=_load_json(args.combined_snapshot_json),
        process_snapshot=_load_json(args.process_snapshot_json),
        systemd_snapshot=_load_json(args.systemd_snapshot_json),
        required_env_keys=required_env_keys,
    )
    if args.json_output:
        args.json_output.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n")
    if args.output:
        args.output.write_text(render_markdown(packet), encoding="utf-8")
    if args.print_json:
        print(json.dumps(packet, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
