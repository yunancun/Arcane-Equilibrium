#!/usr/bin/env python3
"""Finite-task continuation control and exclusive worktree-writer leases.

This Module is an internal Implementation behind the existing Dispatch and
Closure Interfaces.  It does not schedule work.  It makes the scheduling
decision deterministic and keeps one writable task bound to one linked
feature worktree at a time.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import secrets
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Protocol


TASK_EXECUTION_SCHEMA_VERSION = "task_execution_control_v1"
WRITER_LEASE_SCHEMA_VERSION = "writer_leases_v1"
CONTINUATION_MODES = ("finite", "operator_loop")
DEFAULT_CONTINUATION_MODE = "finite"
AUTOMATIC_WAKEUP_MODES = ("operator_loop",)
SAME_PROGRESS_TERMINAL = "BLOCKED_NO_DELTA"
DEFAULT_LEASE_TTL_SECONDS = 7200
MIN_LEASE_TTL_SECONDS = 60
MAX_LEASE_TTL_SECONDS = 86400

EXPECTED_TASK_EXECUTION_CONTROL = {
    "schema_version": TASK_EXECUTION_SCHEMA_VERSION,
    "default_continuation_mode": DEFAULT_CONTINUATION_MODE,
    "continuation_modes": list(CONTINUATION_MODES),
    "automatic_wakeup_modes": list(AUTOMATIC_WAKEUP_MODES),
    "same_progress_terminal": SAME_PROGRESS_TERMINAL,
    "operator_loop_requires_explicit_request": True,
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


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("timestamp must be an RFC3339 UTC string ending in Z")
    parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include UTC timezone")
    return parsed.astimezone(timezone.utc)


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def validate_task_execution_control(contract: Any) -> list[str]:
    """Validate the exact registry-owned task execution contract."""

    if contract != EXPECTED_TASK_EXECUTION_CONTROL:
        return [
            "task_execution_control must match the finite-default, explicit-loop, "
            "worktree-writer-lease contract"
        ]
    return []


def compile_task_execution_policy(continuation_mode: str) -> dict[str, Any]:
    """Project the continuation and writer policy into a routed task."""

    if continuation_mode not in CONTINUATION_MODES:
        raise ValueError(f"invalid continuation_mode: {continuation_mode}")
    return {
        "schema_version": TASK_EXECUTION_SCHEMA_VERSION,
        "continuation_mode": continuation_mode,
        "automatic_wakeup_admitted": continuation_mode in AUTOMATIC_WAKEUP_MODES,
        "same_progress_terminal": SAME_PROGRESS_TERMINAL,
        "writer_lease": dict(EXPECTED_TASK_EXECUTION_CONTROL["writer_lease"]),
    }


def queue_lane(work_status: str) -> str:
    """Return the one physical queue lane for a work status."""

    try:
        return QUEUE_LANES[work_status]
    except KeyError as error:
        raise ValueError(f"unknown queue work_status: {work_status}") from error


def is_dispatchable(work_status: str) -> bool:
    """Only active-lane work can be selected for dispatch."""

    return queue_lane(work_status) == "active"


def next_action_may_be_null(work_status: str) -> bool:
    """Terminal Closure states must not synthesize executable work."""

    return work_status in NULLABLE_NEXT_ACTION_STATUSES


def progress_snapshot(
    *,
    round_number: int,
    work_status: str,
    source_head: str,
    context_digest: str,
    external_state_digest: str,
    work_digest: str,
    blocker_code: str | None = None,
) -> dict[str, Any]:
    """Build one exact no-progress comparison snapshot."""

    if not isinstance(round_number, int) or isinstance(round_number, bool) or round_number < 0:
        raise ValueError("round_number must be a non-negative integer")
    allowed_statuses = ACTIVE_PROGRESS_STATUSES | TERMINAL_WORK_STATUSES
    if work_status not in allowed_statuses:
        raise ValueError(f"invalid progress work_status: {work_status}")
    if not isinstance(source_head, str) or len(source_head) != 40 or any(
        char not in "0123456789abcdef" for char in source_head
    ):
        raise ValueError("source_head must be a lowercase 40-hex commit")
    digest_fields = {
        "context_digest": context_digest,
        "external_state_digest": external_state_digest,
        "work_digest": work_digest,
    }
    for field, value in digest_fields.items():
        if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
            raise ValueError(f"{field} must be sha256:<64 lowercase hex>")
        if any(char not in "0123456789abcdef" for char in value.removeprefix("sha256:")):
            raise ValueError(f"{field} must be sha256:<64 lowercase hex>")
    if blocker_code is not None and (
        not isinstance(blocker_code, str) or not blocker_code.strip()
    ):
        raise ValueError("blocker_code must be null or a non-empty string")
    comparison = {
        "work_status": work_status,
        "source_head": source_head,
        "context_digest": context_digest,
        "external_state_digest": external_state_digest,
        "work_digest": work_digest,
        "blocker_code": blocker_code,
    }
    return {
        "schema_version": "task_progress_snapshot_v1",
        "round": round_number,
        **comparison,
        "progress_digest": _canonical_digest(comparison),
    }


def adjudicate_continuation(
    *,
    continuation_mode: str,
    current: dict[str, Any],
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Decide whether a controller may schedule another turn."""

    policy = compile_task_execution_policy(continuation_mode)
    current_digest = current.get("progress_digest")
    if not isinstance(current_digest, str):
        raise ValueError("current snapshot lacks progress_digest")
    if continuation_mode == DEFAULT_CONTINUATION_MODE:
        decision = "STOP_FINITE_TASK"
        terminal_status = current.get("work_status")
    elif current.get("work_status") in TERMINAL_WORK_STATUSES:
        decision = "STOP_TERMINAL"
        terminal_status = current.get("work_status")
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


class WriterLeaseStore(Protocol):
    """Storage Seam for exclusive worktree writer leases."""

    def read(self) -> dict[str, Any]: ...

    def update(self, mutation: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]: ...


class InMemoryWriterLeaseStore:
    """Deterministic test Adapter for the writer-lease Seam."""

    def __init__(self) -> None:
        self._state = {"schema_version": WRITER_LEASE_SCHEMA_VERSION, "leases": {}}

    def read(self) -> dict[str, Any]:
        return json.loads(json.dumps(self._state))

    def update(self, mutation: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        candidate = mutation(self.read())
        self._state = json.loads(json.dumps(candidate))
        return self.read()


class FileWriterLeaseStore:
    """Atomic filesystem Adapter located in Git's common directory."""

    def __init__(self, common_dir: Path) -> None:
        self.common_dir = common_dir.resolve()
        self.state_path = self.common_dir / "codex-writer-leases-v1.json"
        self.lock_path = self.common_dir / "codex-writer-leases-v1.lock"

    def read(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"schema_version": WRITER_LEASE_SCHEMA_VERSION, "leases": {}}
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"writer lease state is unreadable: {error}") from error
        _validate_lease_state(raw)
        return raw

    def update(self, mutation: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        self.common_dir.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            current = self.read()
            candidate = mutation(current)
            _validate_lease_state(candidate)
            fd, temporary_name = tempfile.mkstemp(
                prefix="codex-writer-leases-v1.", suffix=".tmp", dir=self.common_dir
            )
            temporary_path = Path(temporary_name)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(candidate, handle, ensure_ascii=False, sort_keys=True)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary_path, self.state_path)
            finally:
                temporary_path.unlink(missing_ok=True)
            return json.loads(json.dumps(candidate))


def _validate_lease_state(state: Any) -> None:
    if not isinstance(state, dict) or set(state) != {"schema_version", "leases"}:
        raise ValueError("writer lease state must contain only schema_version and leases")
    if state["schema_version"] != WRITER_LEASE_SCHEMA_VERSION:
        raise ValueError("writer lease state schema_version is invalid")
    if not isinstance(state["leases"], dict):
        raise ValueError("writer lease state leases must be an object")
    required = {
        "lease_id", "task_id", "owner", "worktree", "branch", "acquired_at", "expires_at"
    }
    for worktree, lease in state["leases"].items():
        if not isinstance(worktree, str) or not isinstance(lease, dict) or set(lease) != required:
            raise ValueError("writer lease record shape is invalid")
        if lease["worktree"] != worktree:
            raise ValueError("writer lease key must match worktree")
        if any(not isinstance(lease[field], str) or not lease[field] for field in required):
            raise ValueError("writer lease fields must be non-empty strings")
        _parse_timestamp(lease["acquired_at"])
        _parse_timestamp(lease["expires_at"])


@dataclass(frozen=True)
class WorktreeIdentity:
    worktree: str
    branch: str | None
    head: str | None
    common_dir: Path
    git_dir: Path
    dirty: bool

    @property
    def linked(self) -> bool:
        return self.git_dir != self.common_dir


def _git_text(repo: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def inspect_worktree(repo: Path) -> WorktreeIdentity:
    """Resolve the exact checkout identity without mutating Git."""

    root_text = _git_text(repo, "rev-parse", "--show-toplevel")
    common_text = _git_text(repo, "rev-parse", "--path-format=absolute", "--git-common-dir")
    git_dir_text = _git_text(repo, "rev-parse", "--path-format=absolute", "--absolute-git-dir")
    if not root_text or not common_text or not git_dir_text:
        raise ValueError("repository worktree identity is unavailable")
    root = Path(root_text).resolve()
    status = _git_text(root, "status", "--porcelain=v1", "--untracked-files=all")
    if status is None:
        raise ValueError("repository dirty state is unavailable")
    return WorktreeIdentity(
        worktree=str(root),
        branch=_git_text(root, "symbolic-ref", "--quiet", "--short", "HEAD"),
        head=_git_text(root, "rev-parse", "HEAD"),
        common_dir=Path(common_text).resolve(),
        git_dir=Path(git_dir_text).resolve(),
        dirty=bool(status),
    )


def _lease_result(
    action: str,
    *,
    status: str,
    reasons: list[str],
    identity: WorktreeIdentity,
    lease: dict[str, str] | None,
) -> dict[str, Any]:
    return {
        "schema_version": "writer_lease_result_v1",
        "action": action,
        "status": status,
        "reasons": reasons,
        "worktree": identity.worktree,
        "branch": identity.branch,
        "head": identity.head,
        "linked_worktree": identity.linked,
        "lease": lease,
    }


def _active_lease(lease: dict[str, str], now: datetime) -> bool:
    return _parse_timestamp(lease["expires_at"]) > now


def acquire_writer_lease(
    store: WriterLeaseStore,
    identity: WorktreeIdentity,
    *,
    task_id: str,
    owner: str,
    ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Acquire or idempotently renew one exclusive worktree writer lease."""

    current_time = now or _utc_now()
    reasons: list[str] = []
    if not task_id.strip() or not owner.strip():
        reasons.append("TASK_AND_OWNER_REQUIRED")
    if ttl_seconds < MIN_LEASE_TTL_SECONDS or ttl_seconds > MAX_LEASE_TTL_SECONDS:
        reasons.append("LEASE_TTL_OUT_OF_RANGE")
    if not identity.linked:
        reasons.append("LINKED_WORKTREE_REQUIRED")
    if identity.branch in {None, "main"}:
        reasons.append("ATTACHED_FEATURE_BRANCH_REQUIRED")
    if identity.dirty:
        reasons.append("CLEAN_WORKTREE_REQUIRED")
    if reasons:
        return _lease_result("acquire", status="FAIL", reasons=reasons, identity=identity, lease=None)

    result: dict[str, Any] = {}

    def mutation(state: dict[str, Any]) -> dict[str, Any]:
        leases = state["leases"]
        existing = leases.get(identity.worktree)
        if existing and _active_lease(existing, current_time):
            if existing["task_id"] != task_id or existing["owner"] != owner:
                result["collision"] = existing
                return state
            lease_id = existing["lease_id"]
            acquired_at = existing["acquired_at"]
        else:
            lease_id = secrets.token_hex(16)
            acquired_at = _timestamp(current_time)
        lease = {
            "lease_id": lease_id,
            "task_id": task_id,
            "owner": owner,
            "worktree": identity.worktree,
            "branch": identity.branch or "",
            "acquired_at": acquired_at,
            "expires_at": _timestamp(current_time + timedelta(seconds=ttl_seconds)),
        }
        leases[identity.worktree] = lease
        result["lease"] = lease
        return state

    store.update(mutation)
    if "collision" in result:
        return _lease_result(
            "acquire", status="FAIL", reasons=["WORKTREE_WRITER_LEASE_HELD"],
            identity=identity, lease=None,
        )
    return _lease_result(
        "acquire", status="PASS", reasons=[], identity=identity, lease=result["lease"]
    )


def validate_writer_lease(
    store: WriterLeaseStore,
    identity: WorktreeIdentity,
    *,
    task_id: str,
    lease_id: str,
    owner: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Read-only validation Adapter used by Git loop guards."""

    current_time = now or _utc_now()
    try:
        state = store.read()
    except ValueError:
        return _lease_result(
            "validate", status="FAIL", reasons=["WRITER_LEASE_STATE_INVALID"],
            identity=identity, lease=None,
        )
    lease = state["leases"].get(identity.worktree)
    reasons: list[str] = []
    if lease is None:
        reasons.append("WRITER_LEASE_MISSING")
    else:
        if not _active_lease(lease, current_time):
            reasons.append("WRITER_LEASE_EXPIRED")
        if lease["task_id"] != task_id:
            reasons.append("WRITER_LEASE_TASK_MISMATCH")
        if lease["lease_id"] != lease_id:
            reasons.append("WRITER_LEASE_ID_MISMATCH")
        if owner is not None and lease["owner"] != owner:
            reasons.append("WRITER_LEASE_OWNER_MISMATCH")
        if lease["branch"] != identity.branch:
            reasons.append("WRITER_LEASE_BRANCH_MISMATCH")
    return _lease_result(
        "validate", status="FAIL" if reasons else "PASS", reasons=reasons,
        identity=identity, lease=lease,
    )


def renew_writer_lease(
    store: WriterLeaseStore,
    identity: WorktreeIdentity,
    *,
    task_id: str,
    owner: str,
    lease_id: str,
    ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Renew an exact active writer lease without changing its identity."""

    current_time = now or _utc_now()
    validation = validate_writer_lease(
        store, identity, task_id=task_id, owner=owner, lease_id=lease_id, now=current_time
    )
    if validation["status"] != "PASS":
        return {**validation, "action": "renew"}
    if ttl_seconds < MIN_LEASE_TTL_SECONDS or ttl_seconds > MAX_LEASE_TTL_SECONDS:
        return _lease_result(
            "renew", status="FAIL", reasons=["LEASE_TTL_OUT_OF_RANGE"],
            identity=identity, lease=validation["lease"],
        )
    result: dict[str, Any] = {}

    def mutation(state: dict[str, Any]) -> dict[str, Any]:
        lease = state["leases"][identity.worktree]
        lease["expires_at"] = _timestamp(current_time + timedelta(seconds=ttl_seconds))
        result["lease"] = lease
        return state

    store.update(mutation)
    return _lease_result(
        "renew", status="PASS", reasons=[], identity=identity, lease=result["lease"]
    )


def release_writer_lease(
    store: WriterLeaseStore,
    identity: WorktreeIdentity,
    *,
    task_id: str,
    owner: str,
    lease_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Release only the exact task/owner/lease tuple."""

    validation = validate_writer_lease(
        store, identity, task_id=task_id, owner=owner, lease_id=lease_id, now=now
    )
    if validation["status"] != "PASS":
        return {**validation, "action": "release"}

    def mutation(state: dict[str, Any]) -> dict[str, Any]:
        del state["leases"][identity.worktree]
        return state

    store.update(mutation)
    return _lease_result(
        "release", status="PASS", reasons=[], identity=identity, lease=None
    )


def filesystem_writer_lease_action(
    *,
    action: str,
    repo: Path,
    task_id: str,
    owner: str,
    lease_id: str | None = None,
    ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
) -> dict[str, Any]:
    """Run one explicit production writer-lease action."""

    identity = inspect_worktree(repo)
    store = FileWriterLeaseStore(identity.common_dir)
    if action == "acquire":
        return acquire_writer_lease(
            store, identity, task_id=task_id, owner=owner, ttl_seconds=ttl_seconds
        )
    if not lease_id:
        return _lease_result(
            action, status="FAIL", reasons=["WRITER_LEASE_ID_REQUIRED"],
            identity=identity, lease=None,
        )
    if action == "status":
        return validate_writer_lease(
            store, identity, task_id=task_id, owner=owner, lease_id=lease_id
        )
    if action == "renew":
        return renew_writer_lease(
            store, identity, task_id=task_id, owner=owner, lease_id=lease_id,
            ttl_seconds=ttl_seconds,
        )
    if action == "release":
        return release_writer_lease(
            store, identity, task_id=task_id, owner=owner, lease_id=lease_id
        )
    raise ValueError(f"unsupported writer lease action: {action}")


def _json_arg(value: str) -> Any:
    if value.startswith("@"):
        return json.loads(Path(value[1:]).read_text(encoding="utf-8"))
    return json.loads(value)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    continuation = subparsers.add_parser("continuation")
    continuation.add_argument("--mode", choices=CONTINUATION_MODES, required=True)
    continuation.add_argument("--current", required=True)
    continuation.add_argument("--previous")
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
    if args.action == "continuation":
        packet = adjudicate_continuation(
            continuation_mode=args.mode,
            current=_json_arg(args.current),
            previous=_json_arg(args.previous) if args.previous else None,
        )
    else:
        packet = filesystem_writer_lease_action(
            action=args.action, repo=args.repo, task_id=args.task_id,
            owner=args.owner, lease_id=args.lease_id, ttl_seconds=args.ttl_seconds,
        )
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if packet.get("status", "PASS") == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
