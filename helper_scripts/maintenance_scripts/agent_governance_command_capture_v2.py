"""One-call, context-bound local command capture Adapter."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO

from agent_governance_capture import (
    LOCAL_REPRODUCIBLE,
    REPO_ROOT,
)
from agent_governance_command_replay import (
    CANONICAL_TEST_OUTPUT_V1,
    EXACT_OUTPUT,
    RESULT_ONLY,
    command_argv,
    replay_contract_for,
)
from agent_governance_context_validation import validate_context_artifact
from agent_governance_generation_summary import capture_generation_summary
from agent_governance_permissions import authorize_native_command
from agent_governance_registry import native_agent_contract
from agent_governance_routing import route_task
from agent_governance_workflow_receipts import canonical_digest


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
DURATION_RE = re.compile(rb"(?<![A-Za-z0-9_.])\d+(?:\.\d+)?(?:ms|s)(?![A-Za-z0-9_.])")
PREVIEW_LIMIT = 4096
LOCAL_POLICY_CLASSES = {
    "repo_or_local_test_read", "governance_readonly", "local_test_adapter",
    "node_scoped_read_only",
}
EXECUTION_TASK_FIELDS = {
    "node_id", "role", "native_agent", "node_class", "permission",
    "requires", "path_scope",
}
GENERATION_FIELDS = {
    "schema_version", "scope", "source_head", "generation_digest",
    "observed_at", "record_digest",
}
OUTPUT_FIELDS = {
    "encoding", "preview_text", "preview_base64", "preview_source_bytes",
    "bytes", "digest", "replay_digest", "truncated", "preview_redacted",
}
RECORD_FIELDS = {
    "schema_version", "trust_tier", "context_artifact_digest",
    "task_contract_digest", "execution_task", "execution_task_digest",
    "node_id", "role_id", "native_agent", "node_class", "permission",
    "path_scope", "argv", "command", "authorization", "replay_contract",
    "timeout_seconds", "started_at", "completed_at", "exit_code",
    "timed_out", "result", "stdout", "stderr", "repository_before",
    "repository_after", "whole_repository_before", "whole_repository_after",
    "effect_enforcement", "host_sandbox_attestation_ref", "record_digest",
}
SAFE_INHERITED_ENVIRONMENT = {
    "PATH", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "SYSTEMROOT",
}
SECRET_VALUE_PATTERNS = (
    re.compile(
        rb"(?i)([\"']?[A-Z0-9_.-]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API[_-]?KEY|ACCESS[_-]?KEY|PRIVATE[_-]?KEY|CREDENTIAL)[A-Z0-9_.-]*[\"']?\s*[:=]\s*[\"']?)([^\s,;}\"']+)"
    ),
    re.compile(rb"(?i)(authorization\s*:\s*bearer\s+)([A-Za-z0-9._~+/=-]+)"),
    re.compile(rb"(?i)(https?://)([^/\s:@]+):([^/@\s]+)@"),
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _self_digest(value: dict[str, Any]) -> str:
    return _digest_bytes(_canonical_bytes({
        key: item for key, item in value.items() if key != "record_digest"
    }))


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def _generation_summary(scope: list[str], root: Path) -> dict[str, Any]:
    return capture_generation_summary(scope, root=root)


def _normalized_digest(handle: BinaryIO, replay_contract: str) -> str | None:
    if replay_contract == RESULT_ONLY:
        return None
    handle.seek(0)
    digest = hashlib.sha256()
    tail = b""
    while True:
        chunk = handle.read(64 * 1024)
        if not chunk:
            break
        data = tail + chunk
        if len(data) <= 256:
            tail = data
            continue
        body, tail = data[:-256], data[-256:]
        digest.update(
            DURATION_RE.sub(b"<duration>", body)
            if replay_contract == CANONICAL_TEST_OUTPUT_V1 else body
        )
    digest.update(
        DURATION_RE.sub(b"<duration>", tail)
        if replay_contract == CANONICAL_TEST_OUTPUT_V1 else tail
    )
    return "sha256:" + digest.hexdigest()


def _redact_preview(data: bytes) -> tuple[bytes, bool]:
    redacted = data
    for index, pattern in enumerate(SECRET_VALUE_PATTERNS):
        replacement = rb"\1<redacted>@" if index == 2 else rb"\1<redacted>"
        redacted = pattern.sub(replacement, redacted)
    return redacted, redacted != data


def _is_text(data: bytes) -> bool:
    try:
        data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return False
    return not any(
        byte == 0 or (byte < 32 and byte not in b"\t\n\r") for byte in data
    )


def _bounded_text(data: bytes) -> str:
    candidate = data[:PREVIEW_LIMIT]
    while candidate:
        try:
            return candidate.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            if error.end != len(candidate):
                return candidate.decode("utf-8", errors="replace")
            candidate = candidate[:-1]
    return ""


def _output_summary(handle: BinaryIO, replay_contract: str) -> dict[str, Any]:
    handle.seek(0)
    raw_digest = hashlib.sha256()
    total = 0
    preview = bytearray()
    while True:
        chunk = handle.read(64 * 1024)
        if not chunk:
            break
        raw_digest.update(chunk)
        total += len(chunk)
        if len(preview) < PREVIEW_LIMIT:
            preview.extend(chunk[: PREVIEW_LIMIT - len(preview)])
    result_only = replay_contract == RESULT_ONLY
    source_preview = b"" if result_only else bytes(preview)
    shown, secret_redacted = _redact_preview(source_preview)
    shown = shown[:PREVIEW_LIMIT]
    textual = _is_text(shown)
    return {
        "encoding": "utf-8" if textual else "base64",
        "preview_text": _bounded_text(shown) if textual else None,
        "preview_base64": (
            None if textual else base64.b64encode(shown).decode("ascii")
        ),
        "preview_source_bytes": len(source_preview),
        "bytes": total,
        "digest": "sha256:" + raw_digest.hexdigest(),
        "replay_digest": _normalized_digest(handle, replay_contract),
        "truncated": total > len(source_preview),
        "preview_redacted": result_only or secret_redacted,
    }


def _controlled_environment(isolated_root: Path) -> dict[str, str]:
    environment = {
        key: value for key, value in os.environ.items()
        if key in SAFE_INHERITED_ENVIRONMENT
    }
    environment.update({
        "HOME": str(isolated_root / "home"),
        "TMPDIR": str(isolated_root / "tmp"),
        "XDG_CONFIG_HOME": str(isolated_root / "config"),
        "XDG_CACHE_HOME": str(isolated_root / "cache"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_ADDOPTS": "-p no:cacheprovider",
    })
    for directory in ("home", "tmp", "config", "cache"):
        (isolated_root / directory).mkdir(mode=0o700)
    return environment


def _execute(
    argv: list[str], *, root: Path, timeout_seconds: int, replay_contract: str,
) -> dict[str, Any]:
    with (
        tempfile.TemporaryDirectory(prefix="governed-command-") as isolated,
        tempfile.TemporaryFile() as stdout_file,
        tempfile.TemporaryFile() as stderr_file,
    ):
        isolated_root = Path(isolated)
        started_at = _now()
        timed_out = False
        try:
            completed = subprocess.run(
                argv, cwd=root, shell=False, stdin=subprocess.DEVNULL,
                stdout=stdout_file, stderr=stderr_file, timeout=timeout_seconds,
                check=False, env=_controlled_environment(isolated_root),
            )
            exit_code = completed.returncode
        except subprocess.TimeoutExpired:
            timed_out, exit_code = True, -1
        except OSError as error:
            exit_code = 127
            stderr_file.write(str(error).encode("utf-8", errors="replace"))
        completed_at = _now()
        return {
            "started_at": started_at, "completed_at": completed_at,
            "exit_code": exit_code, "timed_out": timed_out,
            "result": "TIMED_OUT" if timed_out else "PASS" if exit_code == 0 else "FAIL",
            "stdout": _output_summary(stdout_file, replay_contract),
            "stderr": _output_summary(stderr_file, replay_contract),
        }


def _bound_execution_task(
    context_artifact: dict[str, Any], native_agent: str, node_id: str, root: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    validated = validate_context_artifact(context_artifact, root=root)
    if validated["errors"]:
        raise ValueError("context artifact is invalid: " + "; ".join(validated["errors"]))
    plan = validated["plan"]
    task_contract = plan["task_contract"]
    route = route_task(task_contract)
    matches = [
        task for task in route["required_role_nodes"]
        if task.get("node_id") == node_id
    ]
    if len(matches) != 1:
        raise ValueError("node_id is not one canonical routed execution task")
    task = {field: matches[0].get(field) for field in EXECUTION_TASK_FIELDS}
    identity = native_agent_contract(native_agent)
    if (
        task["native_agent"] != native_agent
        or task["role"] != identity["role_id"]
        or task["node_class"] != identity["node_class"]
        or task["permission"] != identity["permission"]
    ):
        raise PermissionError("native agent does not own the routed execution task")
    if task["node_class"] != "verification" or task["permission"] != "read_only":
        raise PermissionError("capture-command is restricted to read-only verification tasks")
    path_scope = (
        task["path_scope"]
        or task_contract.get("verification_scope", [])
        or task_contract.get("dirty_scope", [])
    )
    if not isinstance(path_scope, list) or not path_scope:
        raise ValueError("routed command capture has no non-empty derived path_scope")
    return task, task_contract, sorted(path_scope)


def capture_governed_command(
    *,
    native_agent: str,
    node_id: str,
    context_artifact: dict[str, Any],
    argv: list[str] | tuple[str, ...],
    root: Path = REPO_ROOT,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """Derive identity/scope from Context and execute exactly one local argv."""

    repository = Path(root).resolve(strict=True)
    if not 1 <= timeout_seconds <= 900:
        raise ValueError("timeout_seconds must be from 1 through 900")
    execution_task, task_contract, path_scope = _bound_execution_task(
        context_artifact, native_agent, node_id, repository,
    )
    command_argv_value, command = command_argv(argv)
    authorization = authorize_native_command(native_agent, command)
    if not authorization.get("allowed"):
        raise PermissionError(f"command is not authorized: {authorization.get('reason')}")
    if authorization.get("policy_class") not in LOCAL_POLICY_CLASSES:
        raise PermissionError(
            "capture-command policy rejects direct network/private/effect argv; "
            "repository policy is not OS effect isolation"
        )
    replay_contract = replay_contract_for(
        command_argv_value, authorization.get("policy_class")
    )
    whole_before = _generation_summary(["."], repository)
    repository_before = _generation_summary(path_scope, repository)
    executed = _execute(
        command_argv_value, root=repository, timeout_seconds=timeout_seconds,
        replay_contract=replay_contract,
    )
    repository_after = _generation_summary(path_scope, repository)
    whole_after = _generation_summary(["."], repository)
    record: dict[str, Any] = {
        "schema_version": "command_capture_v2",
        "trust_tier": LOCAL_REPRODUCIBLE,
        "context_artifact_digest": context_artifact["artifact_digest"],
        "task_contract_digest": context_artifact["task_contract_digest"],
        "execution_task": execution_task,
        "execution_task_digest": canonical_digest(execution_task),
        "node_id": execution_task["node_id"], "role_id": execution_task["role"],
        "native_agent": native_agent, "node_class": execution_task["node_class"],
        "permission": execution_task["permission"], "path_scope": path_scope,
        "argv": command_argv_value, "command": command,
        "authorization": authorization, "replay_contract": replay_contract,
        "timeout_seconds": timeout_seconds, **executed,
        "repository_before": repository_before,
        "repository_after": repository_after,
        "whole_repository_before": whole_before,
        "whole_repository_after": whole_after,
        "effect_enforcement": "repository_policy_only",
        "host_sandbox_attestation_ref": None,
    }
    record["record_digest"] = _self_digest(record)
    errors = validate_governed_command_capture(
        record, expected_context_artifact_digest=context_artifact["artifact_digest"],
        expected_task_contract_digest=context_artifact["task_contract_digest"],
        expected_execution_task=execution_task, expected_path_scope=path_scope,
    )
    if errors:
        raise RuntimeError("governed command capture failed: " + "; ".join(errors))
    return record


def _generation_errors(
    summary: Any, *, expected_scope: list[str], label: str,
) -> list[str]:
    if not isinstance(summary, dict):
        return [f"{label} must be an object"]
    errors: list[str] = []
    if set(summary) != GENERATION_FIELDS:
        errors.append(f"{label} fields are invalid")
    if summary.get("schema_version") != "repository_generation_summary_v1":
        errors.append(f"{label} schema_version is invalid")
    if summary.get("scope") != sorted(expected_scope):
        errors.append(f"{label} scope is invalid")
    if not re.fullmatch(r"[0-9a-f]{40}", str(summary.get("source_head", ""))):
        errors.append(f"{label} source_head is invalid")
    if not DIGEST_RE.fullmatch(str(summary.get("generation_digest", ""))):
        errors.append(f"{label} generation digest is invalid")
    if _time(summary.get("observed_at")) is None:
        errors.append(f"{label} observed_at is invalid")
    if summary.get("record_digest") != _self_digest(summary):
        errors.append(f"{label} self-digest is invalid")
    return errors


def _output_errors(output: Any, label: str) -> list[str]:
    if not isinstance(output, dict):
        return [f"{label} summary is missing"]
    errors: list[str] = []
    if set(output) != OUTPUT_FIELDS:
        errors.append(f"{label} summary fields are invalid")
        return errors
    encoding = output.get("encoding")
    preview_text = output.get("preview_text")
    preview_base64 = output.get("preview_base64")
    if encoding == "utf-8" and isinstance(preview_text, str) and preview_base64 is None:
        preview = preview_text.encode("utf-8")
    elif encoding == "base64" and preview_text is None and isinstance(preview_base64, str):
        try:
            preview = base64.b64decode(preview_base64, validate=True)
        except (TypeError, ValueError):
            preview = b""
            errors.append(f"{label} preview is invalid base64")
    else:
        preview = b""
        errors.append(f"{label} preview encoding/channel is invalid")
    source_bytes = output.get("preview_source_bytes")
    if (
        not isinstance(source_bytes, int) or isinstance(source_bytes, bool)
        or not 0 <= source_bytes <= PREVIEW_LIMIT
    ):
        errors.append(f"{label} preview source byte count is invalid")
    total = output.get("bytes")
    if not isinstance(total, int) or isinstance(total, bool) or total < 0:
        errors.append(f"{label} full byte count is invalid")
    if len(preview) > PREVIEW_LIMIT:
        errors.append(f"{label} preview exceeds bound")
    if _redact_preview(preview)[0] != preview:
        errors.append(f"{label} preview contains an unredacted secret")
    if not DIGEST_RE.fullmatch(str(output.get("digest", ""))):
        errors.append(f"{label} full digest is invalid")
    replay_digest = output.get("replay_digest")
    if replay_digest is not None and not DIGEST_RE.fullmatch(str(replay_digest)):
        errors.append(f"{label} replay digest is invalid")
    if output.get("truncated") is not (
        isinstance(total, int) and isinstance(source_bytes, int)
        and total > source_bytes
    ):
        errors.append(f"{label} truncation flag is invalid")
    if not isinstance(output.get("preview_redacted"), bool):
        errors.append(f"{label} preview_redacted is invalid")
    return errors


def validate_governed_command_capture(
    record: Any,
    *,
    expected_context_artifact_digest: str | None = None,
    expected_task_contract_digest: str | None = None,
    expected_execution_task: dict[str, Any] | None = None,
    expected_path_scope: list[str] | None = None,
    expected_source_head: str | None = None,
    root: Path = REPO_ROOT,
    reexecute: bool = False,
) -> list[str]:
    """Validate v2 binding, compact outputs, generations, and optional replay."""

    if not isinstance(record, dict):
        return ["governed command capture must be an object"]
    errors: list[str] = []
    if set(record) != RECORD_FIELDS:
        errors.append("governed command capture fields do not match contract")
    if record.get("schema_version") != "command_capture_v2":
        errors.append("governed command capture schema_version is invalid")
    if record.get("trust_tier") != LOCAL_REPRODUCIBLE:
        errors.append("governed command capture trust tier is invalid")
    if record.get("effect_enforcement") != "repository_policy_only":
        errors.append("governed command effect enforcement boundary is invalid")
    if record.get("host_sandbox_attestation_ref") is not None:
        errors.append("governed command cannot self-assert a host sandbox attestation")
    execution_task = record.get("execution_task")
    if not isinstance(execution_task, dict) or set(execution_task) != EXECUTION_TASK_FIELDS:
        errors.append("governed command execution task is invalid")
        execution_task = {}
    if record.get("execution_task_digest") != canonical_digest(execution_task):
        errors.append("governed command execution task digest is invalid")
    if expected_execution_task is not None and execution_task != expected_execution_task:
        errors.append("governed command execution task differs from dispatch")
    for record_field, task_field in (
        ("node_id", "node_id"), ("role_id", "role"),
        ("native_agent", "native_agent"), ("node_class", "node_class"),
        ("permission", "permission"),
    ):
        if record.get(record_field) != execution_task.get(task_field):
            errors.append(f"governed command {record_field} differs from execution task")
    path_scope = record.get("path_scope")
    if not isinstance(path_scope, list) or not path_scope or path_scope != sorted(set(path_scope)):
        errors.append("governed command path_scope is invalid")
        path_scope = []
    if expected_path_scope is not None and path_scope != sorted(expected_path_scope):
        errors.append("governed command path_scope differs from dispatch-derived scope")
    for field, expected in (
        ("context_artifact_digest", expected_context_artifact_digest),
        ("task_contract_digest", expected_task_contract_digest),
    ):
        if not DIGEST_RE.fullmatch(str(record.get(field, ""))):
            errors.append(f"governed command {field} is invalid")
        if expected is not None and record.get(field) != expected:
            errors.append(f"governed command {field} differs from expected Context")
    try:
        argv, command = command_argv(record.get("argv"))
        if record.get("command") != command:
            errors.append("governed command string differs from argv")
    except ValueError as error:
        argv, command = [], ""
        errors.append(f"governed command argv is invalid: {error}")
    authorization = record.get("authorization")
    expected_authorization = authorize_native_command(str(record.get("native_agent", "")), command)
    if authorization != expected_authorization:
        errors.append("governed command authorization differs from exact native policy")
    if not isinstance(authorization, dict) or authorization.get("policy_class") not in LOCAL_POLICY_CLASSES:
        errors.append("governed command is not an authorized local read/test command")
    if record.get("replay_contract") != replay_contract_for(
        argv, authorization.get("policy_class") if isinstance(authorization, dict) else None
    ):
        errors.append("governed command replay contract is invalid")
    timeout = record.get("timeout_seconds")
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 900:
        errors.append("governed command timeout is invalid")
    started, completed = _time(record.get("started_at")), _time(record.get("completed_at"))
    if started is None or completed is None or completed < started:
        errors.append("governed command interval is invalid")
    exit_code, timed_out = record.get("exit_code"), record.get("timed_out")
    expected_result = (
        "TIMED_OUT" if timed_out is True else "PASS" if exit_code == 0 else "FAIL"
    )
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        errors.append("governed command exit_code is invalid")
    if not isinstance(timed_out, bool) or record.get("result") != expected_result:
        errors.append("governed command result/timed_out is invalid")
    errors.extend(_output_errors(record.get("stdout"), "governed command stdout"))
    errors.extend(_output_errors(record.get("stderr"), "governed command stderr"))
    for field, scope in (
        ("repository_before", path_scope), ("repository_after", path_scope),
        ("whole_repository_before", ["."]), ("whole_repository_after", ["."]),
    ):
        errors.extend(_generation_errors(record.get(field), expected_scope=scope, label=field))
        summary = record.get(field)
        if (
            expected_source_head is not None and isinstance(summary, dict)
            and summary.get("source_head") != expected_source_head
        ):
            errors.append(f"{field} source_head differs from admitted baseline")
    if isinstance(record.get("repository_before"), dict) and isinstance(record.get("repository_after"), dict) and record["repository_before"].get("generation_digest") != record["repository_after"].get("generation_digest"):
        errors.append("governed command mutated task-scoped repository generation")
    if isinstance(record.get("whole_repository_before"), dict) and isinstance(record.get("whole_repository_after"), dict) and record["whole_repository_before"].get("generation_digest") != record["whole_repository_after"].get("generation_digest"):
        errors.append("governed command mutated whole-repository generation")
    if record.get("record_digest") != _self_digest(record):
        errors.append("governed command capture self-digest is invalid")
    if reexecute and not errors:
        errors.extend(_replay_errors(record, root=Path(root)))
    return errors


def _replay_errors(record: dict[str, Any], *, root: Path) -> list[str]:
    path_scope = record["path_scope"]
    current_task = _generation_summary(path_scope, root)
    current_whole = _generation_summary(["."], root)
    if current_task["generation_digest"] != record["repository_after"]["generation_digest"]:
        return ["governed command task generation is stale before replay"]
    if current_whole["generation_digest"] != record["whole_repository_after"]["generation_digest"]:
        return ["governed command whole-repository generation is stale before replay"]
    replay = _execute(
        record["argv"], root=root, timeout_seconds=record["timeout_seconds"],
        replay_contract=record["replay_contract"],
    )
    errors: list[str] = []
    if any(replay[field] != record[field] for field in ("exit_code", "timed_out", "result")):
        errors.append("governed command result does not reproduce")
    for stream in ("stdout", "stderr"):
        expected, actual = record[stream], replay[stream]
        if record["replay_contract"] == EXACT_OUTPUT:
            if (actual["bytes"], actual["digest"]) != (expected["bytes"], expected["digest"]):
                errors.append(f"governed command {stream} exact output does not reproduce")
        elif record["replay_contract"] == CANONICAL_TEST_OUTPUT_V1 and actual["replay_digest"] != expected["replay_digest"]:
            errors.append(f"governed command {stream} canonical output does not reproduce")
    after_task = _generation_summary(path_scope, root)
    after_whole = _generation_summary(["."], root)
    if after_task["generation_digest"] != current_task["generation_digest"]:
        errors.append("governed command replay mutated task-scoped generation")
    if after_whole["generation_digest"] != current_whole["generation_digest"]:
        errors.append("governed command replay mutated whole-repository generation")
    return errors
