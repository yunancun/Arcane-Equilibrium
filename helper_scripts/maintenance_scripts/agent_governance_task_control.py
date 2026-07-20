#!/usr/bin/env python3
"""Finite-task continuation control and exclusive worktree-writer leases.

This Module is an internal Implementation behind the existing Dispatch and
Closure Interfaces.  It does not schedule work.  It makes the scheduling
decision deterministic and keeps one writable task bound to one linked
feature worktree at a time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
from pathlib import Path, PurePosixPath
from typing import Any

from agent_governance_writer_lease import (
    DEFAULT_LEASE_TTL_SECONDS,
    MAX_LEASE_TTL_SECONDS,
    MIN_LEASE_TTL_SECONDS,
    FileWriterLeaseStore,
    InMemoryWriterLeaseStore,
    WorktreeIdentity,
    WriterLeaseStore,
    _git_text,
    acquire_writer_lease,
    filesystem_writer_lease_action,
    inspect_worktree,
    release_writer_lease,
    renew_writer_lease,
    validate_writer_lease,
)


TASK_EXECUTION_SCHEMA_VERSION = "task_execution_control_v1"
CONTINUATION_MODES = ("finite", "operator_loop")
DEFAULT_CONTINUATION_MODE = "finite"
AUTOMATIC_WAKEUP_MODES = ("operator_loop",)
SAME_PROGRESS_TERMINAL = "BLOCKED_NO_DELTA"
MAX_TASK_SOURCE_FILES = 4096
MAX_TASK_SOURCE_BYTES = 64 * 1024 * 1024

EXPECTED_TASK_EXECUTION_CONTROL = {
    "schema_version": TASK_EXECUTION_SCHEMA_VERSION,
    "default_continuation_mode": DEFAULT_CONTINUATION_MODE,
    "continuation_modes": list(CONTINUATION_MODES),
    "automatic_wakeup_modes": list(AUTOMATIC_WAKEUP_MODES),
    "same_progress_terminal": SAME_PROGRESS_TERMINAL,
    "operator_loop_requires_explicit_request": True,
    "operator_loop_request_marker": "/loop",
    "control_binding": "admitted_task_contract_digest",
    "continuation_requires_previous": True,
    "snapshot_producer": "recaptured_task_owned_bytes",
    "dispatchable_work_statuses": ["ACTIVE"],
    "semantic_progress_fields": ["task_source_digest"],
    "non_progress_fields": ["round", "work_status", "source_head", "blocker_code"],
    "writer_lease": {
        "scope": "worktree",
        "requires_linked_feature_worktree": True,
        "default_ttl_seconds": DEFAULT_LEASE_TTL_SECONDS,
        "min_ttl_seconds": MIN_LEASE_TTL_SECONDS,
        "max_ttl_seconds": MAX_LEASE_TTL_SECONDS,
    },
}

TERMINAL_WORK_STATUSES = frozenset(
    {"DONE", "DONE_WITH_CONCERNS", "BLOCKED", "NEEDS_CONTEXT", SAME_PROGRESS_TERMINAL}
)
ACTIVE_PROGRESS_STATUSES = frozenset({"ACTIVE", "IN_PROGRESS"})
QUEUE_LANES = {
    "ACTIVE": "active",
    "IN_PROGRESS": "active",
    "BLOCKED": "waiting",
    "NEEDS_CONTEXT": "waiting",
    "WAITING": "waiting",
    "DEFERRED": "waiting",
    "DONE": "closed",
    "DONE_WITH_CONCERNS": "closed",
    SAME_PROGRESS_TERMINAL: "closed",
}
NULLABLE_NEXT_ACTION_STATUSES = frozenset(
    {"DONE", "DONE_WITH_CONCERNS", SAME_PROGRESS_TERMINAL}
)
PROGRESS_SNAPSHOT_FIELDS = frozenset({
    "schema_version", "round", "work_status", "source_head",
    "task_contract_digest", "task_source_manifest", "task_source_digest",
    "blocker_code", "progress_digest",
})
COMPILED_TASK_EXECUTION_CONTROL_FIELDS = frozenset({
    "schema_version", "continuation_mode", "automatic_wakeup_admitted",
    "same_progress_terminal", "writer_lease", "task_prompt_digest",
    "operator_loop_request_digest", "task_contract_digest",
})
OPERATOR_LOOP_MARKER = re.compile(
    r"\A[ \t]*/loop[ \t]*(?:\r?\n|\Z)"
)


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def task_contract_digest(task_contract: Any) -> str:
    """Return the canonical digest of one already-normalized task contract."""

    if not isinstance(task_contract, dict):
        raise ValueError("task_contract must be an object")
    return _canonical_digest(task_contract)


def validate_task_execution_control(contract: Any) -> list[str]:
    """Validate the exact registry-owned task execution contract."""

    if contract != EXPECTED_TASK_EXECUTION_CONTROL:
        return [
            "task_execution_control must match the finite-default, explicit-loop, "
            "worktree-writer-lease contract"
        ]
    return []


def operator_loop_request_digest(task_prompt: str) -> str | None:
    """Bind loop authority only to a leading Operator ``/loop`` control line."""

    if not OPERATOR_LOOP_MARKER.search(task_prompt):
        return None
    return _canonical_digest({
        "request_marker": "/loop",
        "task_prompt": task_prompt,
    })


def compile_task_execution_policy(task_contract: dict[str, Any]) -> dict[str, Any]:
    """Compile continuation authority from one immutable normalized task contract."""

    if not isinstance(task_contract, dict):
        raise ValueError("task_contract must be an object")
    continuation_mode = task_contract.get("continuation_mode")
    task_prompt = task_contract.get("task_prompt")
    if continuation_mode not in CONTINUATION_MODES:
        raise ValueError(f"invalid continuation_mode: {continuation_mode}")
    if not isinstance(task_prompt, str) or not task_prompt.strip():
        raise ValueError("task_prompt must be a non-empty string")
    prompt_digest = "sha256:" + hashlib.sha256(
        task_prompt.encode("utf-8")
    ).hexdigest()
    if task_contract.get("task_prompt_digest") != prompt_digest:
        raise ValueError("task_contract task_prompt_digest does not match exact bytes")
    request_digest = operator_loop_request_digest(task_prompt)
    if continuation_mode == "operator_loop" and request_digest is None:
        raise ValueError(
            "operator_loop requires a leading /loop control line in the Operator task_prompt"
        )
    expected_request_digest = (
        request_digest if continuation_mode == "operator_loop" else None
    )
    if task_contract.get("operator_loop_request_digest") != expected_request_digest:
        raise ValueError("task_contract operator loop request binding is invalid")
    return {
        "schema_version": TASK_EXECUTION_SCHEMA_VERSION,
        "continuation_mode": continuation_mode,
        "automatic_wakeup_admitted": continuation_mode in AUTOMATIC_WAKEUP_MODES,
        "same_progress_terminal": SAME_PROGRESS_TERMINAL,
        "writer_lease": dict(EXPECTED_TASK_EXECUTION_CONTROL["writer_lease"]),
        "task_prompt_digest": prompt_digest,
        "operator_loop_request_digest": expected_request_digest,
        "task_contract_digest": task_contract_digest(task_contract),
    }


def validate_compiled_task_execution_control(
    control: Any,
    *,
    task_contract: dict[str, Any],
    admitted_task_contract_digest: str,
) -> dict[str, Any]:
    """Recompile from the admitted contract so callers cannot replace authority."""

    if (
        not isinstance(control, dict)
        or set(control) != COMPILED_TASK_EXECUTION_CONTROL_FIELDS
    ):
        raise ValueError("task_execution_control fields are not exact")
    expected = compile_task_execution_policy(task_contract)
    if expected["task_contract_digest"] != admitted_task_contract_digest:
        raise ValueError("task_contract does not match the admitted task contract digest")
    if control != expected:
        raise ValueError("task_execution_control does not match its exact task_prompt")
    return expected


def queue_lane(work_status: str) -> str:
    """Return the one physical queue lane for a work status."""

    try:
        return QUEUE_LANES[work_status]
    except KeyError as error:
        raise ValueError(f"unknown queue work_status: {work_status}") from error


def is_dispatchable(work_status: str) -> bool:
    """Only a fresh ACTIVE admission can be selected; IN_PROGRESS is claimed."""

    queue_lane(work_status)
    return work_status == "ACTIVE"


def next_action_may_be_null(work_status: str) -> bool:
    """Terminal Closure states must not synthesize executable work."""

    return work_status in NULLABLE_NEXT_ACTION_STATUSES


def terminal_next_action_errors(
    work_status: str, next_action: Any, *, label: str
) -> list[str]:
    """Enforce terminal-null versus waiting-owner Closure semantics."""

    if work_status == SAME_PROGRESS_TERMINAL and next_action is not None:
        return [f"{label} BLOCKED_NO_DELTA must have next_action=null"]
    if work_status in {"BLOCKED", "NEEDS_CONTEXT"} and not isinstance(
        next_action, dict
    ):
        return [f"{label} BLOCKED/NEEDS_CONTEXT require an owned next_action"]
    return []


def progress_snapshot(
    *,
    round_number: int,
    work_status: str,
    repo: Path,
    task_contract: dict[str, Any],
    admitted_task_contract_digest: str,
    blocker_code: str | None = None,
) -> dict[str, Any]:
    """Build a snapshot from recaptured task-owned repository bytes only."""

    if (
        not isinstance(round_number, int)
        or isinstance(round_number, bool)
        or round_number < 0
    ):
        raise ValueError("round_number must be a non-negative integer")
    allowed_statuses = ACTIVE_PROGRESS_STATUSES | TERMINAL_WORK_STATUSES
    if work_status not in allowed_statuses:
        raise ValueError(f"invalid progress work_status: {work_status}")
    contract_digest = task_contract_digest(task_contract)
    if contract_digest != admitted_task_contract_digest:
        raise ValueError("task_contract does not match the admitted task contract digest")
    repo = repo.resolve()
    source_head = _git_text(repo, "rev-parse", "HEAD")
    if source_head is None or not re.fullmatch(r"[0-9a-f]{40}", source_head):
        raise ValueError("cannot capture an exact repository source_head")
    task_source_manifest = capture_task_source_manifest(repo, task_contract)
    if blocker_code is not None and not (
        isinstance(blocker_code, str)
        and re.fullmatch(r"[A-Z0-9][A-Z0-9_.:-]{0,127}", blocker_code)
    ):
        raise ValueError("blocker_code must be null or a canonical uppercase code")
    task_source_digest = _canonical_digest(task_source_manifest)
    comparison = {"task_source_digest": task_source_digest}
    return {
        "schema_version": "task_progress_snapshot_v1",
        "round": round_number,
        "work_status": work_status,
        "source_head": source_head,
        "task_contract_digest": contract_digest,
        "task_source_manifest": task_source_manifest,
        "task_source_digest": task_source_digest,
        "blocker_code": blocker_code,
        "progress_digest": _canonical_digest(comparison),
    }


def capture_task_source_manifest(
    repo: Path, task_contract: dict[str, Any]
) -> list[dict[str, Any]]:
    """Capture exact bytes only from the task contract's owned source scope."""

    scope = task_contract.get("dirty_scope", [])
    if not isinstance(scope, list) or any(not isinstance(item, str) for item in scope):
        raise ValueError("task_contract dirty_scope must be a string list")
    repo = repo.resolve()
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    total_bytes = 0
    for raw in scope:
        normalized = raw.strip().removeprefix("./").rstrip("/")
        path = PurePosixPath(normalized)
        if (
            not normalized
            or normalized == "."
            or normalized.startswith(("/", "~"))
            or ".." in path.parts
            or path.parts[0].casefold() == ".git"
            or path.as_posix() != normalized
        ):
            raise ValueError("task_contract dirty_scope contains an unsafe path")
        candidate = repo / normalized
        cursor = repo
        for part in path.parts:
            cursor /= part
            if cursor.is_symlink():
                raise ValueError("task-owned source scope cannot contain a symlink")
        try:
            candidate.resolve(strict=False).relative_to(repo)
        except ValueError as error:
            raise ValueError("task-owned source scope escapes the repository") from error
        if candidate.is_symlink():
            raise ValueError("task-owned source scope cannot contain a symlink")
        if not candidate.exists():
            records.append({"path": normalized, "kind": "absent"})
            continue
        candidates = [candidate]
        if candidate.is_dir():
            records.append({"path": normalized, "kind": "directory"})
            candidates = sorted(
                item for item in candidate.rglob("*") if item.is_file() or item.is_symlink()
            )
        for item in candidates:
            relative = item.relative_to(repo).as_posix()
            if relative in seen:
                continue
            seen.add(relative)
            if item.is_symlink():
                raise ValueError("task-owned source scope cannot contain a symlink")
            try:
                item.resolve(strict=True).relative_to(repo)
            except (OSError, ValueError) as error:
                raise ValueError("task-owned source scope escapes the repository") from error
            try:
                item_stat = item.stat(follow_symlinks=False)
            except OSError as error:
                raise ValueError("task-owned source file metadata is unavailable") from error
            if not stat.S_ISREG(item_stat.st_mode):
                raise ValueError("task-owned source scope must contain regular files only")
            if len(seen) > MAX_TASK_SOURCE_FILES:
                raise ValueError("task-owned source scope exceeds the file-count limit")
            total_bytes += item_stat.st_size
            if total_bytes > MAX_TASK_SOURCE_BYTES:
                raise ValueError("task-owned source scope exceeds the byte limit")
            data = item.read_bytes()
            if len(data) != item_stat.st_size:
                raise ValueError("task-owned source file changed while being captured")
            records.append({
                "path": relative,
                "kind": "file",
                "size": len(data),
                "content_sha256": hashlib.sha256(data).hexdigest(),
            })
    return sorted(records, key=lambda record: (record["path"], record["kind"]))


def _validate_task_source_manifest(manifest: Any) -> None:
    if not isinstance(manifest, list):
        raise ValueError("task_source_manifest must be a list")
    paths: list[tuple[str, str]] = []
    for record in manifest:
        if not isinstance(record, dict) or set(record) not in (
            {"path", "kind"},
            {"path", "kind", "size", "content_sha256"},
        ):
            raise ValueError("task_source_manifest record fields are not exact")
        path, kind = record.get("path"), record.get("kind")
        if not isinstance(path, str) or kind not in {"absent", "directory", "file"}:
            raise ValueError("task_source_manifest record is invalid")
        if kind == "file":
            if (
                not isinstance(record.get("size"), int)
                or isinstance(record.get("size"), bool)
                or record["size"] < 0
                or not re.fullmatch(r"[0-9a-f]{64}", str(record.get("content_sha256")))
            ):
                raise ValueError("task_source_manifest file record is invalid")
        elif set(record) != {"path", "kind"}:
            raise ValueError("task_source_manifest non-file record is invalid")
        paths.append((path, kind))
    if paths != sorted(set(paths)):
        raise ValueError("task_source_manifest must be sorted and unique")


def validate_progress_snapshot(snapshot: Any) -> dict[str, Any]:
    """Recompute the task-owned source digest from the embedded manifest."""

    if not isinstance(snapshot, dict) or set(snapshot) != PROGRESS_SNAPSHOT_FIELDS:
        raise ValueError("progress snapshot fields are not exact")
    if (
        not isinstance(snapshot["round"], int)
        or isinstance(snapshot["round"], bool)
        or snapshot["round"] < 0
        or snapshot["work_status"] not in ACTIVE_PROGRESS_STATUSES | TERMINAL_WORK_STATUSES
        or not re.fullmatch(r"[0-9a-f]{40}", str(snapshot["source_head"]))
        or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", str(snapshot["task_contract_digest"])
        )
    ):
        raise ValueError("progress snapshot provenance is invalid")
    manifest = snapshot["task_source_manifest"]
    _validate_task_source_manifest(manifest)
    blocker_code = snapshot["blocker_code"]
    if blocker_code is not None and not (
        isinstance(blocker_code, str)
        and re.fullmatch(r"[A-Z0-9][A-Z0-9_.:-]{0,127}", blocker_code)
    ):
        raise ValueError("progress snapshot blocker_code is invalid")
    task_source_digest = _canonical_digest(manifest)
    comparison = {"task_source_digest": task_source_digest}
    expected = {
        **snapshot,
        "task_source_digest": task_source_digest,
        "progress_digest": _canonical_digest(comparison),
    }
    if snapshot != expected:
        raise ValueError("progress snapshot digest does not match canonical content")
    return expected


def _adjudicate_continuation(
    *,
    repo: Path,
    task_contract: dict[str, Any],
    admitted_task_contract_digest: str,
    task_execution_control: dict[str, Any],
    current: dict[str, Any],
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Decide whether a controller may schedule another turn."""

    policy = validate_compiled_task_execution_control(
        task_execution_control,
        task_contract=task_contract,
        admitted_task_contract_digest=admitted_task_contract_digest,
    )
    continuation_mode = policy["continuation_mode"]
    current = validate_progress_snapshot(current)
    previous = validate_progress_snapshot(previous) if previous is not None else None
    if current["task_contract_digest"] != admitted_task_contract_digest or (
        previous is not None
        and previous["task_contract_digest"] != admitted_task_contract_digest
    ):
        raise ValueError("progress snapshot task contract binding is invalid")
    recaptured_manifest = capture_task_source_manifest(repo.resolve(), task_contract)
    if current["task_source_manifest"] != recaptured_manifest:
        raise ValueError("current progress snapshot does not match task-owned repository bytes")
    current_digest = current["progress_digest"]
    if previous is not None and current["round"] <= previous["round"]:
        raise ValueError("current progress round must be newer than previous round")
    if continuation_mode == DEFAULT_CONTINUATION_MODE:
        decision = "STOP_FINITE_TASK"
        terminal_status = current.get("work_status")
    elif current.get("work_status") in TERMINAL_WORK_STATUSES or (
        previous is not None and previous.get("work_status") in TERMINAL_WORK_STATUSES
    ):
        decision = "STOP_TERMINAL"
        terminal_status = current.get("work_status")
    elif previous is None:
        decision = "STOP_MISSING_PREVIOUS"
        terminal_status = "NEEDS_CONTEXT"
    elif previous is not None and previous.get("progress_digest") == current_digest:
        decision = SAME_PROGRESS_TERMINAL
        terminal_status = SAME_PROGRESS_TERMINAL
    else:
        decision = "CONTINUE_OPERATOR_LOOP"
        terminal_status = None
    wakeup = decision == "CONTINUE_OPERATOR_LOOP"
    return {
        "schema_version": "continuation_decision_v1",
        "continuation_mode": continuation_mode,
        "decision": decision,
        "terminal_work_status": terminal_status,
        "schedule_wakeup": wakeup,
        "progress_digest": current_digest,
        "previous_progress_digest": (
            previous.get("progress_digest") if previous is not None else None
        ),
        "policy": policy,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    lease = subparsers.add_parser("writer-lease")
    lease.add_argument("--action", choices=("acquire", "status", "renew", "release"), required=True)
    lease.add_argument("--repo", type=Path, default=Path("."))
    lease.add_argument("--task-id", required=True)
    lease.add_argument("--owner", required=True)
    lease.add_argument("--lease-id")
    lease.add_argument("--ttl-seconds", type=int, default=DEFAULT_LEASE_TTL_SECONDS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    packet = filesystem_writer_lease_action(
        action=args.action, repo=args.repo, task_id=args.task_id,
        owner=args.owner, lease_id=args.lease_id, ttl_seconds=args.ttl_seconds,
    )
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if packet.get("status", "PASS") == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
