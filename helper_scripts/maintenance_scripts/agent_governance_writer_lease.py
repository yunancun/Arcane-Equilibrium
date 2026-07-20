"""Exclusive linked-worktree writer leases for agent governance.

This internal Adapter owns lease persistence and Git worktree identity.  It has
no continuation or scheduling authority.
"""

from __future__ import annotations

import fcntl
import json
import os
import secrets
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Protocol


WRITER_LEASE_SCHEMA_VERSION = "writer_leases_v1"
DEFAULT_LEASE_TTL_SECONDS = 7200
MIN_LEASE_TTL_SECONDS = 60
MAX_LEASE_TTL_SECONDS = 86400


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


class WriterLeaseStore(Protocol):
    """Storage Seam for exclusive worktree writer leases."""

    def read(self) -> dict[str, Any]: ...

    def update(
        self, mutation: Callable[[dict[str, Any]], dict[str, Any]]
    ) -> dict[str, Any]: ...


class InMemoryWriterLeaseStore:
    """Deterministic test Adapter for the writer-lease Seam."""

    def __init__(self) -> None:
        self._state = {"schema_version": WRITER_LEASE_SCHEMA_VERSION, "leases": {}}

    def read(self) -> dict[str, Any]:
        return json.loads(json.dumps(self._state))

    def update(
        self, mutation: Callable[[dict[str, Any]], dict[str, Any]]
    ) -> dict[str, Any]:
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
        if self.state_path.is_symlink():
            raise ValueError("writer lease state must not be a symlink")
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"schema_version": WRITER_LEASE_SCHEMA_VERSION, "leases": {}}
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"writer lease state is unreadable: {error}") from error
        _validate_lease_state(raw)
        return raw

    def update(
        self, mutation: Callable[[dict[str, Any]], dict[str, Any]]
    ) -> dict[str, Any]:
        self.common_dir.mkdir(parents=True, exist_ok=True)
        if self.lock_path.is_symlink() or self.state_path.is_symlink():
            raise ValueError("writer lease files must not be symlinks")
        with self.lock_path.open("a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            current = self.read()
            candidate = mutation(current)
            _validate_lease_state(candidate)
            fd, temporary_name = tempfile.mkstemp(
                prefix="codex-writer-leases-v1.",
                suffix=".tmp",
                dir=self.common_dir,
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
        "lease_id",
        "task_id",
        "owner",
        "worktree",
        "branch",
        "acquired_at",
        "expires_at",
    }
    for worktree, lease in state["leases"].items():
        if (
            not isinstance(worktree, str)
            or not isinstance(lease, dict)
            or set(lease) != required
        ):
            raise ValueError("writer lease record shape is invalid")
        if lease["worktree"] != worktree:
            raise ValueError("writer lease key must match worktree")
        if any(
            not isinstance(lease[field], str) or not lease[field]
            for field in required
        ):
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
    common_text = _git_text(
        repo, "rev-parse", "--path-format=absolute", "--git-common-dir"
    )
    git_dir_text = _git_text(
        repo, "rev-parse", "--path-format=absolute", "--absolute-git-dir"
    )
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


def _lease_validation_reasons(
    lease: dict[str, str] | None,
    identity: WorktreeIdentity,
    *,
    task_id: str,
    lease_id: str,
    owner: str | None,
    now: datetime,
) -> list[str]:
    if lease is None:
        return ["WRITER_LEASE_MISSING"]
    reasons: list[str] = []
    if not _active_lease(lease, now):
        reasons.append("WRITER_LEASE_EXPIRED")
    if lease["task_id"] != task_id:
        reasons.append("WRITER_LEASE_TASK_MISMATCH")
    if lease["lease_id"] != lease_id:
        reasons.append("WRITER_LEASE_ID_MISMATCH")
    if owner is not None and lease["owner"] != owner:
        reasons.append("WRITER_LEASE_OWNER_MISMATCH")
    if lease["branch"] != identity.branch:
        reasons.append("WRITER_LEASE_BRANCH_MISMATCH")
    return reasons


def acquire_writer_lease(
    store: WriterLeaseStore,
    identity: WorktreeIdentity,
    *,
    task_id: str,
    owner: str,
    ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Acquire one exclusive worktree writer lease; a live lease always collides."""

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
        return _lease_result(
            "acquire",
            status="FAIL",
            reasons=reasons,
            identity=identity,
            lease=None,
        )

    result: dict[str, Any] = {}

    def mutation(state: dict[str, Any]) -> dict[str, Any]:
        leases = state["leases"]
        existing = leases.get(identity.worktree)
        if existing and _active_lease(existing, current_time):
            result["collision"] = existing
            return state
        lease_id = secrets.token_hex(16)
        acquired_at = _timestamp(current_time)
        lease = {
            "lease_id": lease_id,
            "task_id": task_id,
            "owner": owner,
            "worktree": identity.worktree,
            "branch": identity.branch or "",
            "acquired_at": acquired_at,
            "expires_at": _timestamp(
                current_time + timedelta(seconds=ttl_seconds)
            ),
        }
        leases[identity.worktree] = lease
        result["lease"] = lease
        return state

    store.update(mutation)
    if "collision" in result:
        return _lease_result(
            "acquire",
            status="FAIL",
            reasons=["WORKTREE_WRITER_LEASE_HELD"],
            identity=identity,
            lease=None,
        )
    return _lease_result(
        "acquire",
        status="PASS",
        reasons=[],
        identity=identity,
        lease=result["lease"],
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
            "validate",
            status="FAIL",
            reasons=["WRITER_LEASE_STATE_INVALID"],
            identity=identity,
            lease=None,
        )
    lease = state["leases"].get(identity.worktree)
    reasons = _lease_validation_reasons(
        lease,
        identity,
        task_id=task_id,
        lease_id=lease_id,
        owner=owner,
        now=current_time,
    )
    return _lease_result(
        "validate",
        status="FAIL" if reasons else "PASS",
        reasons=reasons,
        identity=identity,
        lease=lease,
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
    if ttl_seconds < MIN_LEASE_TTL_SECONDS or ttl_seconds > MAX_LEASE_TTL_SECONDS:
        return _lease_result(
            "renew",
            status="FAIL",
            reasons=["LEASE_TTL_OUT_OF_RANGE"],
            identity=identity,
            lease=None,
        )
    result: dict[str, Any] = {}

    def mutation(state: dict[str, Any]) -> dict[str, Any]:
        lease = state["leases"].get(identity.worktree)
        reasons = _lease_validation_reasons(
            lease,
            identity,
            task_id=task_id,
            lease_id=lease_id,
            owner=owner,
            now=current_time,
        )
        if reasons:
            result["reasons"] = reasons
            return state
        lease["expires_at"] = _timestamp(
            current_time + timedelta(seconds=ttl_seconds)
        )
        result["lease"] = lease
        return state

    store.update(mutation)
    if result.get("reasons"):
        return _lease_result(
            "renew",
            status="FAIL",
            reasons=result["reasons"],
            identity=identity,
            lease=None,
        )
    return _lease_result(
        "renew",
        status="PASS",
        reasons=[],
        identity=identity,
        lease=result["lease"],
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

    current_time = now or _utc_now()
    result: dict[str, Any] = {}

    def mutation(state: dict[str, Any]) -> dict[str, Any]:
        reasons = _lease_validation_reasons(
            state["leases"].get(identity.worktree),
            identity,
            task_id=task_id,
            lease_id=lease_id,
            owner=owner,
            now=current_time,
        )
        if reasons:
            result["reasons"] = reasons
            return state
        del state["leases"][identity.worktree]
        return state

    store.update(mutation)
    if result.get("reasons"):
        return _lease_result(
            "release",
            status="FAIL",
            reasons=result["reasons"],
            identity=identity,
            lease=None,
        )
    return _lease_result(
        "release",
        status="PASS",
        reasons=[],
        identity=identity,
        lease=None,
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
            store,
            identity,
            task_id=task_id,
            owner=owner,
            ttl_seconds=ttl_seconds,
        )
    if not lease_id:
        return _lease_result(
            action,
            status="FAIL",
            reasons=["WRITER_LEASE_ID_REQUIRED"],
            identity=identity,
            lease=None,
        )
    if action == "status":
        return validate_writer_lease(
            store,
            identity,
            task_id=task_id,
            owner=owner,
            lease_id=lease_id,
        )
    if action == "renew":
        return renew_writer_lease(
            store,
            identity,
            task_id=task_id,
            owner=owner,
            lease_id=lease_id,
            ttl_seconds=ttl_seconds,
        )
    if action == "release":
        return release_writer_lease(
            store,
            identity,
            task_id=task_id,
            owner=owner,
            lease_id=lease_id,
        )
    raise ValueError(f"unsupported writer lease action: {action}")
