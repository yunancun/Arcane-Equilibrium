"""Deep, content-addressed evidence capture for Development-Agent governance.

This module separates locally reproducible capture, controller-known metadata,
and platform/external claims.  A self-digest proves canonical integrity only;
it never upgrades a record into platform or external authenticity.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from agent_governance_command_replay import (
    command_argv,
    recorded_output,
    replay_contract_for,
    validate_trusted_command_replay,
)
from agent_governance_permissions import authorize_command
from agent_governance_workflow_receipts import (
    build_controller_workflow_call_record,
    validate_workflow_call_record,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_REPRODUCIBLE = "LOCAL_REPRODUCIBLE"
ORCHESTRATOR_BOUND = "ORCHESTRATOR_BOUND"
PLATFORM_OR_EXTERNAL_ATTESTED = "PLATFORM_OR_EXTERNAL_ATTESTED"
TRUST_TIERS = {
    LOCAL_REPRODUCIBLE,
    ORCHESTRATOR_BOUND,
    PLATFORM_OR_EXTERNAL_ATTESTED,
}
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEAD_RE = re.compile(r"^[0-9a-f]{40}$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}$")
TASK_DIGEST_RE = DIGEST_RE
REPOSITORY_FIELDS = {
    "schema_version",
    "trust_tier",
    "scope",
    "source_head",
    "tracked_diff",
    "tracked_paths",
    "untracked",
    "changed_paths",
    "change_manifest_digest",
    "untracked_manifest_digest",
    "observed_at",
    "record_digest",
}
BYTE_CAPTURE_FIELDS = {"encoding", "content", "bytes", "digest"}
UNTRACKED_FIELDS = {"path", "encoding", "content", "bytes", "digest"}
COMMAND_FIELDS = {
    "schema_version",
    "trust_tier",
    "task_contract_digest",
    "node_id",
    "role_id",
    "node_class",
    "argv",
    "command",
    "authorization",
    "replay_contract",
    "started_at",
    "completed_at",
    "exit_code",
    "timed_out",
    "result",
    "stdout",
    "stderr",
    "repository_before",
    "repository_after",
    "record_digest",
}
TELEMETRY_FIELDS = {
    "schema_version", "trust_tier", "assurance", "body", "body_digest",
    "external_record", "record_digest",
}
TELEMETRY_BODY_FIELDS = {"schema_version", "subject_call_ids", "observed_at", "metrics"}
TELEMETRY_METRICS = {
    "input_tokens", "output_tokens", "cache_read_tokens", "tool_calls",
    "retry_count", "wall_time_ms", "rework_count",
}
SENSITIVE_PARTS = {
    ".git", ".ssh", ".aws", ".gnupg", ".netrc", ".env", "credentials",
    "credentials.json", "id_rsa", "id_ed25519",
}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _record_digest(record: dict[str, Any]) -> str:
    return _digest_bytes(
        _canonical_bytes({key: value for key, value in record.items() if key != "record_digest"})
    )


def repository_generation_digest(record: dict[str, Any]) -> str:
    """Hash only Git/content generation fields, excluding observation time."""

    return _digest_bytes(
        _canonical_bytes(
            {
                field: record.get(field)
                for field in (
                    "scope", "source_head", "tracked_diff", "tracked_paths",
                    "untracked", "changed_paths", "change_manifest_digest",
                    "untracked_manifest_digest",
                )
            }
        )
    )


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _timestamp_error(value: Any, label: str) -> str | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone required")
    except (TypeError, ValueError):
        return f"{label} must be a timezone-aware timestamp"
    return None


def _interval_errors(record: dict[str, Any], prefix: str) -> list[str]:
    errors = [
        error for error in (
            _timestamp_error(record.get("started_at"), f"{prefix} started_at"),
            _timestamp_error(record.get("completed_at"), f"{prefix} completed_at"),
        ) if error
    ]
    if not errors and datetime.fromisoformat(str(record["completed_at"]).replace("Z", "+00:00")) < datetime.fromisoformat(str(record["started_at"]).replace("Z", "+00:00")):
        errors.append(f"{prefix} completion precedes start")
    return errors


def _git(root: Path, *arguments: str) -> bytes:
    return subprocess.run(
        ["git", *arguments], cwd=root, check=True, capture_output=True,
    ).stdout


def _repository_root(root: Path) -> Path:
    resolved = root.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError("repository root must be a directory")
    try:
        top = Path(
            _git(resolved, "rev-parse", "--show-toplevel")
            .decode("utf-8", errors="strict")
            .strip()
        ).resolve(strict=True)
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        raise ValueError(f"cannot resolve Git repository root: {error}") from error
    if top != resolved:
        raise ValueError("capture root must be the exact Git repository root")
    return resolved


def _safe_relative_path(value: Any, root: Path) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("repository scope paths must be non-empty canonical strings")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("repository scope paths cannot contain control characters")
    if value.startswith(("~", ":")) or "\\" in value or any(mark in value for mark in "*?["):
        raise ValueError("repository scope path is unsafe")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("repository scope path escapes the repository")
    normalized = path.as_posix()
    if normalized not in {"."} and normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized in {"", ".."}:
        raise ValueError("repository scope path is invalid")
    if SENSITIVE_PARTS.intersection(part.casefold() for part in Path(normalized).parts):
        raise ValueError("repository scope path targets sensitive state")
    cursor = root
    for part in Path(normalized).parts:
        if part == ".":
            continue
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("repository scope path may not traverse a symlink")
    try:
        (root / normalized).resolve(strict=False).relative_to(root)
    except (RuntimeError, ValueError) as error:
        raise ValueError("repository scope path escapes the repository") from error
    return normalized


def _normalize_scope(scope: Any, root: Path) -> list[str]:
    if not isinstance(scope, (list, tuple)) or not scope:
        raise ValueError("repository scope must be a non-empty path list")
    normalized = [_safe_relative_path(value, root) for value in scope]
    if len(normalized) != len(set(normalized)):
        raise ValueError("repository scope paths must be unique")
    return sorted(normalized)


def _path_is_scoped(path: str, scope: list[str]) -> bool:
    return any(item == "." or path == item or path.startswith(item.rstrip("/") + "/") for item in scope)


def _byte_capture(data: bytes) -> dict[str, Any]:
    return {
        "encoding": "base64",
        "content": base64.b64encode(data).decode("ascii"),
        "bytes": len(data),
        "digest": _digest_bytes(data),
    }


def _git_generation(
    repository: Path, paths: list[str]
) -> tuple[str, bytes, list[str], list[str]]:
    try:
        head = _git(repository, "rev-parse", "HEAD").decode("ascii").strip().lower()
        tracked = _git(repository, "diff", "--no-ext-diff", "--binary", "HEAD", "--", *paths)
        tracked_names = sorted(
            item.decode("utf-8", errors="strict")
            for item in _git(
                repository, "diff", "--no-ext-diff", "--name-only", "-z",
                "HEAD", "--", *paths,
            ).split(b"\0")
            if item
        )
        untracked = sorted(
            item.decode("utf-8", errors="strict")
            for item in _git(repository, "ls-files", "--others", "--exclude-standard", "-z", "--", *paths).split(b"\0")
            if item
        )
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        raise ValueError(f"cannot capture repository generation: {error}") from error
    if not HEAD_RE.fullmatch(head):
        raise ValueError("captured Git source_head is not exact 40-hex")
    return head, tracked, tracked_names, untracked


def capture_repository(
    scope: list[str] | tuple[str, ...], *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Capture exact scoped tracked and untracked bytes from the current Git generation."""

    repository = _repository_root(Path(root))
    paths = _normalize_scope(scope, repository)
    source_head, tracked, tracked_names, untracked_names = _git_generation(
        repository, paths
    )
    for raw_path in tracked_names:
        relative = _safe_relative_path(raw_path, repository)
        if not _path_is_scoped(relative, paths):
            raise ValueError("Git returned a tracked path outside the declared scope")
    untracked: list[dict[str, Any]] = []
    for raw_path in untracked_names:
        relative = _safe_relative_path(raw_path, repository)
        if not _path_is_scoped(relative, paths):
            raise ValueError("Git returned an untracked path outside the declared scope")
        candidate = repository / relative
        if candidate.is_symlink() or not candidate.is_file():
            raise ValueError("untracked capture targets a symlink or non-regular file")
        data = candidate.read_bytes()
        untracked.append({"path": relative, **_byte_capture(data)})
    repeated = _git_generation(repository, paths)
    if repeated != (source_head, tracked, tracked_names, untracked_names) or any(
        (repository / item["path"]).read_bytes() != base64.b64decode(item["content"])
        for item in untracked
    ):
        raise ValueError("repository changed during capture; retry on a stable generation")
    changed_paths = sorted(set(tracked_names) | set(untracked_names))
    record: dict[str, Any] = {
        "schema_version": "repository_capture_v1",
        "trust_tier": LOCAL_REPRODUCIBLE,
        "scope": paths,
        "source_head": source_head,
        "tracked_diff": _byte_capture(tracked),
        "tracked_paths": tracked_names,
        "untracked": untracked,
        "changed_paths": changed_paths,
        "change_manifest_digest": _digest_bytes(_canonical_bytes(changed_paths)),
        "untracked_manifest_digest": _digest_bytes(_canonical_bytes(untracked)),
        "observed_at": _now(),
    }
    record["record_digest"] = _record_digest(record)
    return record


def _validate_byte_capture(value: Any, label: str) -> tuple[list[str], bytes | None]:
    if not isinstance(value, dict) or set(value) != BYTE_CAPTURE_FIELDS:
        return [f"{label} fields do not match contract"], None
    errors: list[str] = []
    if value.get("encoding") != "base64" or not isinstance(value.get("content"), str):
        errors.append(f"{label} encoding/content is invalid")
        return errors, None
    try:
        decoded = base64.b64decode(value["content"], validate=True)
    except (ValueError, TypeError):
        errors.append(f"{label} content is not canonical base64")
        return errors, None
    if base64.b64encode(decoded).decode("ascii") != value["content"]:
        errors.append(f"{label} content is not canonical base64")
    if value.get("bytes") != len(decoded):
        errors.append(f"{label} byte count is invalid")
    if value.get("digest") != _digest_bytes(decoded):
        errors.append(f"{label} digest is invalid")
    return errors, decoded


def validate_repository_capture(
    record: Any,
    *,
    expected_scope: list[str] | tuple[str, ...] | None = None,
    root: Path = REPO_ROOT,
    require_current: bool = False,
) -> list[str]:
    """Validate integrity/scope and optionally recheck the current Git generation."""

    if not isinstance(record, dict):
        return ["repository capture must be an object"]
    errors: list[str] = []
    if set(record) != REPOSITORY_FIELDS:
        errors.append("repository capture fields do not match contract")
    if record.get("schema_version") != "repository_capture_v1":
        errors.append("repository capture schema_version is invalid")
    if record.get("trust_tier") != LOCAL_REPRODUCIBLE:
        errors.append("repository capture trust tier is invalid")
    validation_root = Path(root).resolve(strict=False)
    scope = record.get("scope")
    if not isinstance(scope, list) or not scope:
        errors.append("repository capture scope is invalid")
        normalized_scope: list[str] = []
    else:
        try:
            normalized_scope = _normalize_scope(scope, validation_root)
            if scope != normalized_scope:
                errors.append("repository capture scope is not canonical")
        except ValueError as error:
            normalized_scope = []
            errors.append(f"repository capture scope is invalid: {error}")
    if expected_scope is not None:
        try:
            expected = _normalize_scope(expected_scope, validation_root)
            if normalized_scope != expected:
                errors.append("repository capture does not match expected scope")
        except ValueError as error:
            errors.append(f"expected repository scope is invalid: {error}")
    if not HEAD_RE.fullmatch(str(record.get("source_head", ""))):
        errors.append("repository capture source_head is invalid")
    byte_errors, _ = _validate_byte_capture(record.get("tracked_diff"), "tracked diff")
    errors.extend(byte_errors)
    tracked_paths = record.get("tracked_paths")
    if not isinstance(tracked_paths, list):
        errors.append("repository capture tracked path manifest is invalid")
        tracked_paths = []
    else:
        safe_tracked: list[str] = []
        for index, path in enumerate(tracked_paths):
            try:
                safe_path = _safe_relative_path(path, validation_root)
                if path != safe_path or not _path_is_scoped(safe_path, normalized_scope):
                    errors.append(f"tracked_paths[{index}] path is outside canonical scope")
                safe_tracked.append(str(path))
            except ValueError:
                errors.append(f"tracked_paths[{index}] path is unsafe")
        if safe_tracked != sorted(set(safe_tracked)):
            errors.append("repository capture tracked paths are not sorted and unique")
    untracked = record.get("untracked")
    if not isinstance(untracked, list):
        errors.append("repository capture untracked manifest is invalid")
        untracked = []
    else:
        names: list[str] = []
        for index, item in enumerate(untracked):
            if not isinstance(item, dict) or set(item) != UNTRACKED_FIELDS:
                errors.append(f"untracked[{index}] fields do not match contract")
                continue
            path = item.get("path")
            try:
                safe_path = _safe_relative_path(path, validation_root)
                if path != safe_path or not _path_is_scoped(safe_path, normalized_scope):
                    errors.append(f"untracked[{index}] path is outside canonical scope")
                names.append(str(path))
            except ValueError:
                errors.append(f"untracked[{index}] path is unsafe")
            item_bytes = {key: item.get(key) for key in BYTE_CAPTURE_FIELDS}
            item_errors, _ = _validate_byte_capture(item_bytes, f"untracked[{index}]")
            errors.extend(item_errors)
        if names != sorted(set(names)):
            errors.append("repository capture untracked paths are not sorted and unique")
    try:
        manifest_digest = _digest_bytes(_canonical_bytes(untracked))
    except (TypeError, ValueError):
        manifest_digest = None
        errors.append("repository capture untracked manifest is not canonical JSON")
    if record.get("untracked_manifest_digest") != manifest_digest:
        errors.append("repository capture untracked manifest digest is invalid")
    changed_paths = record.get("changed_paths")
    untracked_names = [
        item.get("path") for item in untracked if isinstance(item, dict)
    ]
    expected_changed = sorted(set(tracked_paths) | set(untracked_names))
    if changed_paths != expected_changed:
        errors.append("repository capture changed path manifest is inconsistent")
    try:
        change_digest = _digest_bytes(_canonical_bytes(changed_paths))
    except (TypeError, ValueError):
        change_digest = None
        errors.append("repository capture changed path manifest is not canonical JSON")
    if record.get("change_manifest_digest") != change_digest:
        errors.append("repository capture change manifest digest is invalid")
    timestamp_error = _timestamp_error(record.get("observed_at"), "repository observed_at")
    if timestamp_error:
        errors.append(timestamp_error)
    try:
        digest = _record_digest(record)
    except (TypeError, ValueError):
        digest = None
        errors.append("repository capture is not canonical JSON")
    if record.get("record_digest") != digest:
        errors.append("repository capture self-digest is invalid")
    if require_current and normalized_scope:
        try:
            current = capture_repository(normalized_scope, root=validation_root)
            same_generation = all(
                record.get(field) == current.get(field)
                for field in (
                    "source_head",
                    "tracked_diff",
                    "tracked_paths",
                    "untracked",
                    "changed_paths",
                    "change_manifest_digest",
                    "untracked_manifest_digest",
                )
            )
            if not same_generation:
                errors.append(
                    "repository capture is stale relative to the current Git generation"
                )
        except ValueError as error:
            errors.append(f"current repository generation cannot be checked: {error}")
    return errors


def _identifier_error(value: Any, label: str) -> str | None:
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
        return f"{label} is invalid"
    return None


def capture_command(
    *,
    role_id: str,
    node_id: str,
    task_contract_digest: str,
    command: str | list[str] | tuple[str, ...],
    scope: list[str] | tuple[str, ...],
    node_class: str = "verification",
    root: Path = REPO_ROOT,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """Preflight and execute one local read/test command without a shell.

    Exit status and output bytes are accepted only from the internal process;
    callers have no parameters with which to inject a claimed result.
    """

    repository = _repository_root(Path(root))
    for value, label in ((role_id, "role_id"), (node_id, "node_id")):
        error = _identifier_error(value, label)
        if error:
            raise ValueError(error)
    if not TASK_DIGEST_RE.fullmatch(str(task_contract_digest)):
        raise ValueError("task_contract_digest is invalid")
    if (
        not isinstance(timeout_seconds, int)
        or isinstance(timeout_seconds, bool)
        or timeout_seconds < 1
        or timeout_seconds > 900
    ):
        raise ValueError("timeout_seconds must be an integer from 1 through 900")
    argv, canonical_command = command_argv(command)
    authorization = authorize_command(role_id, canonical_command, node_class=node_class)
    if not authorization.get("allowed"):
        raise PermissionError(f"command is not authorized: {authorization.get('reason')}")
    if authorization.get("policy_class") not in {
        "repo_or_local_test_read",
        "governance_readonly",
        "local_test_adapter",
        "node_scoped_read_only",
    }:
        raise PermissionError("command capture is local-only; remote/external probes are forbidden")
    replay_contract = replay_contract_for(argv, authorization.get("policy_class"))
    repository_before = capture_repository(scope, root=repository)
    started_at = _now()
    timed_out = False
    try:
        completed = subprocess.run(
            argv,
            cwd=repository,
            shell=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as error:
        timed_out = True
        exit_code = -1
        stdout = error.stdout if isinstance(error.stdout, bytes) else b""
        stderr = error.stderr if isinstance(error.stderr, bytes) else b""
    except OSError as error:
        exit_code = 127
        stdout = b""
        stderr = str(error).encode("utf-8", errors="replace")
    completed_at = _now()
    repository_after = capture_repository(scope, root=repository)
    result = "TIMED_OUT" if timed_out else ("PASS" if exit_code == 0 else "FAIL")
    record: dict[str, Any] = {
        "schema_version": "command_capture_v1",
        "trust_tier": LOCAL_REPRODUCIBLE,
        "task_contract_digest": task_contract_digest,
        "node_id": node_id,
        "role_id": role_id,
        "node_class": node_class,
        "argv": argv,
        "command": canonical_command,
        "authorization": authorization,
        "replay_contract": replay_contract,
        "started_at": started_at,
        "completed_at": completed_at,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "result": result,
        "stdout": _byte_capture(recorded_output(replay_contract, stdout)),
        "stderr": _byte_capture(recorded_output(replay_contract, stderr)),
        "repository_before": repository_before,
        "repository_after": repository_after,
    }
    record["record_digest"] = _record_digest(record)
    return record


def validate_command_capture(
    record: Any,
    *,
    expected_role_id: str | None = None,
    expected_node_id: str | None = None,
    expected_task_contract_digest: str | None = None,
    expected_result: str | None = None,
    root: Path = REPO_ROOT,
    reexecute: bool = False,
    replay_timeout_seconds: int = 900,
) -> list[str]:
    """Validate a local command capture and optional exact task/node bindings."""

    if not isinstance(record, dict):
        return ["command capture must be an object"]
    errors: list[str] = []
    if set(record) != COMMAND_FIELDS:
        errors.append("command capture fields do not match contract")
    if record.get("schema_version") != "command_capture_v1":
        errors.append("command capture schema_version is invalid")
    if record.get("trust_tier") != LOCAL_REPRODUCIBLE:
        errors.append("command capture trust tier is invalid")
    for field in ("role_id", "node_id"):
        error = _identifier_error(record.get(field), f"command capture {field}")
        if error:
            errors.append(error)
    if not TASK_DIGEST_RE.fullmatch(str(record.get("task_contract_digest", ""))):
        errors.append("command capture task_contract_digest is invalid")
    try:
        argv, canonical_command = command_argv(record.get("argv"))
        if record.get("command") != canonical_command:
            errors.append("command capture command does not match argv")
    except ValueError as error:
        argv, canonical_command = [], ""
        errors.append(f"command capture argv is invalid: {error}")
    authorization = record.get("authorization")
    if not isinstance(authorization, dict) or set(authorization) != {
        "allowed",
        "policy_class",
        "reason",
    }:
        errors.append("command capture authorization fields are invalid")
    elif argv:
        expected_authorization = authorize_command(
            str(record.get("role_id", "")), canonical_command,
            node_class=record.get("node_class"),
        )
        if authorization != expected_authorization:
            errors.append("command capture authorization does not match current preflight")
        if not authorization.get("allowed") or authorization.get("policy_class") not in {
            "repo_or_local_test_read", "governance_readonly", "local_test_adapter",
            "node_scoped_read_only",
        }:
            errors.append("command capture is not an authorized local read/test command")
        expected_replay_contract = replay_contract_for(argv, authorization.get("policy_class"))
        if record.get("replay_contract") != expected_replay_contract:
            errors.append("command capture replay contract does not match current preflight")
    errors.extend(_interval_errors(record, "command capture"))
    exit_code = record.get("exit_code")
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        errors.append("command capture exit_code is invalid")
    timed_out = record.get("timed_out")
    if not isinstance(timed_out, bool):
        errors.append("command capture timed_out is invalid")
    expected_status = (
        "TIMED_OUT"
        if timed_out is True
        else ("PASS" if exit_code == 0 else "FAIL")
    )
    if timed_out is True and exit_code != -1:
        errors.append("timed-out command capture requires exit_code=-1")
    if record.get("result") != expected_status:
        errors.append("command capture result disagrees with exit status")
    decoded_outputs: dict[str, bytes] = {}
    for field in ("stdout", "stderr"):
        output_errors, decoded = _validate_byte_capture(record.get(field), f"command {field}")
        errors.extend(output_errors)
        if decoded is not None:
            decoded_outputs[field] = decoded
    before = record.get("repository_before")
    after = record.get("repository_after")
    errors.extend(
        f"repository_before: {error}"
        for error in validate_repository_capture(before, root=root)
    )
    errors.extend(
        f"repository_after: {error}"
        for error in validate_repository_capture(after, root=root)
    )
    if isinstance(before, dict) and isinstance(after, dict) and before.get("scope") != after.get("scope"):
        errors.append("command capture repository scopes differ across execution")
    if (
        isinstance(before, dict) and isinstance(after, dict)
        and repository_generation_digest(before) != repository_generation_digest(after)
    ):
        errors.append("command capture mutated the task-scoped repository generation")
    bindings = {
        "role_id": expected_role_id,
        "node_id": expected_node_id,
        "task_contract_digest": expected_task_contract_digest,
        "result": expected_result,
    }
    for field, expected in bindings.items():
        if expected is not None and record.get(field) != expected:
            errors.append(f"command capture does not match expected {field}")
    try:
        digest = _record_digest(record)
    except (TypeError, ValueError):
        digest = None
        errors.append("command capture is not canonical JSON")
    if record.get("record_digest") != digest:
        errors.append("command capture self-digest is invalid")
    if reexecute and not errors:
        errors.extend(
            validate_trusted_command_replay(
                argv=argv,
                recorded_result=record.get("result"),
                recorded_exit_code=record.get("exit_code"),
                recorded_timed_out=record.get("timed_out"),
                recorded_stdout=decoded_outputs["stdout"],
                recorded_stderr=decoded_outputs["stderr"],
                replay_contract=record.get("replay_contract"),
                recorded_repository_after=after,
                root=Path(root),
                timeout_seconds=replay_timeout_seconds,
                resolve_repository=_repository_root,
                capture_repository=capture_repository,
                generation_digest=repository_generation_digest,
            )
        )
    return errors


def _telemetry_body_errors(body: Any) -> list[str]:
    if not isinstance(body, dict):
        return ["telemetry body is missing"]
    errors: list[str] = []
    if set(body) != TELEMETRY_BODY_FIELDS:
        errors.append("telemetry body fields do not match contract")
    if body.get("schema_version") != "telemetry_body_v1":
        errors.append("telemetry body schema_version is invalid")
    calls = body.get("subject_call_ids")
    if (
        not isinstance(calls, list) or not calls or calls != sorted(set(calls))
        or any(_identifier_error(item, "call_id") for item in calls)
    ):
        errors.append("telemetry subject_call_ids must be sorted unique identifiers")
    metrics = body.get("metrics")
    if not isinstance(metrics, dict) or set(metrics) != TELEMETRY_METRICS:
        errors.append("telemetry metrics do not match exact metric contract")
    elif any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in metrics.values()):
        errors.append("telemetry metrics must be exact non-negative integers")
    error = _timestamp_error(body.get("observed_at"), "telemetry observed_at")
    if error:
        errors.append(error)
    return errors


def build_unsigned_telemetry_record(
    *, subject_call_ids: list[str], observed_at: str, metrics: dict[str, int]
) -> dict[str, Any]:
    """Build canonical local platform metadata without claiming external authenticity."""

    body = {
        "schema_version": "telemetry_body_v1",
        "subject_call_ids": sorted(subject_call_ids),
        "observed_at": observed_at,
        "metrics": metrics,
    }
    errors = _telemetry_body_errors(body)
    if errors:
        raise ValueError("invalid telemetry body: " + "; ".join(errors))
    record: dict[str, Any] = {
        "schema_version": "telemetry_record_v1",
        "trust_tier": ORCHESTRATOR_BOUND,
        "assurance": "unsigned_local_platform_record",
        "body": body,
        "body_digest": _digest_bytes(_canonical_bytes(body)),
        "external_record": None,
    }
    record["record_digest"] = _record_digest(record)
    return record


def validate_telemetry_record(
    record: Any,
    *,
    expected_subject_call_ids: list[str] | None = None,
    expected_metrics: dict[str, int] | None = None,
    expected_assurance: str | None = None,
) -> list[str]:
    """Validate exact telemetry body bindings; external assurance is fail-closed."""

    if not isinstance(record, dict):
        return ["telemetry record must be an object"]
    errors: list[str] = []
    if set(record) != TELEMETRY_FIELDS:
        errors.append("telemetry record fields do not match contract")
    if record.get("schema_version") != "telemetry_record_v1":
        errors.append("telemetry record schema_version is invalid")
    body = record.get("body")
    errors.extend(_telemetry_body_errors(body))
    try:
        body_digest = _digest_bytes(_canonical_bytes(body))
    except (TypeError, ValueError):
        body_digest = None
    if record.get("body_digest") != body_digest:
        errors.append("telemetry body digest is invalid")
    assurance = record.get("assurance")
    expected_tier = {
        "unsigned_local_platform_record": ORCHESTRATOR_BOUND,
        "external_attested": PLATFORM_OR_EXTERNAL_ATTESTED,
    }.get(assurance)
    if expected_tier is None or record.get("trust_tier") != expected_tier:
        errors.append("telemetry assurance/trust tier is invalid")
    if assurance == "unsigned_local_platform_record" and record.get("external_record") is not None:
        errors.append("unsigned telemetry cannot carry an external record")
    if assurance == "external_attested":
        errors.append("external telemetry requires a trusted platform record; unavailable")
    if isinstance(body, dict):
        if expected_subject_call_ids is not None and body.get("subject_call_ids") != expected_subject_call_ids:
            errors.append("telemetry record does not match expected subject_call_ids")
        if expected_metrics is not None and body.get("metrics") != expected_metrics:
            errors.append("telemetry record does not match expected metrics")
    if expected_assurance is not None and assurance != expected_assurance:
        errors.append("telemetry record does not match expected assurance")
    try:
        digest = _record_digest(record)
    except (TypeError, ValueError):
        digest = None
        errors.append("telemetry record is not canonical JSON")
    if record.get("record_digest") != digest:
        errors.append("telemetry record self-digest is invalid")
    return errors
