"""Exclusive linked-worktree writer leases; no scheduling authority."""

from __future__ import annotations

import fcntl
import json
import os
import re
import secrets
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

WRITER_LEASE_SCHEMA_VERSION = "writer_leases_v1"
WRITER_LEASE_BINDING_SCHEMA_VERSION = "writer_lease_admission_bindings_v1"
DEFAULT_LEASE_TTL_SECONDS = 7200
MIN_LEASE_TTL_SECONDS = 60
MAX_LEASE_TTL_SECONDS = 86400
LEGACY_WRITER_LEASE_FIELDS = {
    "lease_id", "task_id", "owner", "worktree", "branch",
    "acquired_at", "expires_at",
}
LW2_WRITER_LEASE_FIELDS = LEGACY_WRITER_LEASE_FIELDS | {
    "admission_id", "accepted_generation_digest",
}
WRITER_LEASE_BINDING_FIELDS = {
    "lease_id", "task_id", "owner", "worktree", "admission_id",
    "task_contract_digest",
}


class _WriterLeasePreconditionFailed(Exception):
    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


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
        self.binding_path = (
            self.common_dir / "codex-writer-lease-admission-bindings-v1.json"
        )
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

    def read_admission_bindings(self) -> dict[str, Any]:
        """Read ordinary admission bindings serialized by the writer lock."""

        if self.binding_path.is_symlink():
            raise ValueError("writer lease admission bindings must not be a symlink")
        try:
            raw = json.loads(self.binding_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {
                "schema_version": WRITER_LEASE_BINDING_SCHEMA_VERSION,
                "bindings": {},
            }
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(
                f"writer lease admission bindings are unreadable: {error}"
            ) from error
        _validate_binding_state(raw)
        return raw

    def transact(
        self,
        action: Callable[
            [dict[str, Any], dict[str, Any]],
            tuple[dict[str, Any], dict[str, Any], dict[str, Any], bool],
        ],
    ) -> dict[str, Any]:
        """Serialize lease and sidecar decisions under the one writer lock."""

        self.common_dir.mkdir(parents=True, exist_ok=True)
        if any(
            path.is_symlink()
            for path in (self.lock_path, self.state_path, self.binding_path)
        ):
            raise ValueError("writer lease files must not be symlinks")
        with self.lock_path.open("a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            lease_state = self.read()
            binding_state = self.read_admission_bindings()
            lease_state, binding_state, result, persist = action(
                lease_state, binding_state
            )
            _validate_lease_state(lease_state)
            _validate_binding_state(binding_state)
            if persist:
                # A crash between replaces leaves an unbound lease, which is
                # fail-closed and exact-cleanup-only. Never publish PASS before
                # the binding is durable.
                self._replace_json(
                    self.state_path, "codex-writer-leases-v1.", lease_state
                )
                self._replace_json(
                    self.binding_path,
                    "codex-writer-lease-admission-bindings-v1.",
                    binding_state,
                )
            return result

    def _replace_json(
        self, path: Path, prefix: str, value: dict[str, Any]
    ) -> None:
        fd, temporary_name = tempfile.mkstemp(
            prefix=prefix, suffix=".tmp", dir=self.common_dir
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)


def _validate_lease_state(state: Any) -> None:
    if not isinstance(state, dict) or set(state) != {"schema_version", "leases"}:
        raise ValueError("writer lease state must contain only schema_version and leases")
    if state["schema_version"] != WRITER_LEASE_SCHEMA_VERSION:
        raise ValueError("writer lease state schema_version is invalid")
    if not isinstance(state["leases"], dict):
        raise ValueError("writer lease state leases must be an object")
    for worktree, lease in state["leases"].items():
        if (
            not isinstance(worktree, str)
            or not isinstance(lease, dict)
            or frozenset(lease) not in {
                frozenset(LEGACY_WRITER_LEASE_FIELDS),
                frozenset(LW2_WRITER_LEASE_FIELDS),
            }
        ):
            raise ValueError("writer lease record shape is invalid")
        if lease["worktree"] != worktree:
            raise ValueError("writer lease key must match worktree")
        if any(
            not isinstance(lease[field], str) or not lease[field]
            for field in lease
        ):
            raise ValueError("writer lease fields must be non-empty strings")
        if set(lease) == LW2_WRITER_LEASE_FIELDS and (
            not re.fullmatch(r"[0-9a-f]{32}", lease["admission_id"])
            or not re.fullmatch(
                r"sha256:[0-9a-f]{64}",
                lease["accepted_generation_digest"],
            )
        ):
            raise ValueError("LW2 writer lease admission binding is invalid")
        _parse_timestamp(lease["acquired_at"])
        _parse_timestamp(lease["expires_at"])


def _validate_binding_state(state: Any) -> None:
    if not isinstance(state, dict) or set(state) != {"schema_version", "bindings"}:
        raise ValueError(
            "writer lease admission binding state must contain only schema_version "
            "and bindings"
        )
    if state["schema_version"] != WRITER_LEASE_BINDING_SCHEMA_VERSION:
        raise ValueError("writer lease admission binding schema_version is invalid")
    if not isinstance(state["bindings"], dict):
        raise ValueError("writer lease admission bindings must be an object")
    for worktree, binding in state["bindings"].items():
        if (
            not isinstance(worktree, str)
            or not isinstance(binding, dict)
            or set(binding) != WRITER_LEASE_BINDING_FIELDS
            or binding["worktree"] != worktree
        ):
            raise ValueError("writer lease admission binding shape is invalid")
        if any(
            not isinstance(binding[field], str) or not binding[field]
            for field in WRITER_LEASE_BINDING_FIELDS
        ):
            raise ValueError(
                "writer lease admission binding fields must be non-empty strings"
            )
        if (
            not re.fullmatch(r"[0-9a-f]{32}", binding["lease_id"])
            or not re.fullmatch(r"[0-9a-f]{32}", binding["admission_id"])
            or not re.fullmatch(
                r"sha256:[0-9a-f]{64}", binding["task_contract_digest"]
            )
        ):
            raise ValueError("writer lease admission binding identity is invalid")


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


def _native_git_environment() -> dict[str, str]:
    from agent_governance_capture import native_git_environment

    return native_git_environment()


def _native_git_command(repo: Path, *args: str) -> list[str]:
    from agent_governance_capture import native_git_command

    return native_git_command(repo, *args)


def _git_text(
    repo: Path,
    *args: str,
    native_graph: bool = False,
) -> str | None:
    try:
        result = subprocess.run(
            _native_git_command(repo, *args),
            check=False,
            capture_output=True,
            env=_native_git_environment(),
            stdin=subprocess.DEVNULL,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def inspect_worktree(
    repo: Path,
    *,
    native_graph: bool = False,
) -> WorktreeIdentity:
    """Resolve the exact checkout identity without mutating Git."""

    root_text = _git_text(
        repo, "rev-parse", "--show-toplevel", native_graph=native_graph
    )
    common_text = _git_text(
        repo,
        "rev-parse",
        "--path-format=absolute",
        "--git-common-dir",
        native_graph=native_graph,
    )
    git_dir_text = _git_text(
        repo,
        "rev-parse",
        "--path-format=absolute",
        "--absolute-git-dir",
        native_graph=native_graph,
    )
    if not root_text or not common_text or not git_dir_text:
        raise ValueError("repository worktree identity is unavailable")
    root = Path(root_text).resolve()
    status = _git_text(
        root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        native_graph=native_graph,
    )
    if status is None:
        raise ValueError("repository dirty state is unavailable")
    return WorktreeIdentity(
        worktree=str(root),
        branch=_git_text(
            root,
            "symbolic-ref",
            "--quiet",
            "--short",
            "HEAD",
            native_graph=native_graph,
        ),
        head=_git_text(root, "rev-parse", "HEAD", native_graph=native_graph),
        common_dir=Path(common_text).resolve(),
        git_dir=Path(git_dir_text).resolve(),
        dirty=bool(status),
    )


def _capture_dirty_paths(
    repo: Path,
    *,
    native_graph: bool = False,
) -> tuple[list[str], list[str]]:
    """Recapture exact dirty and staged paths without trusting porcelain text."""

    def nul_paths(*args: str) -> list[str]:
        try:
            completed = subprocess.run(
                _native_git_command(repo, *args),
                check=True,
                capture_output=True,
                env=_native_git_environment(),
                stdin=subprocess.DEVNULL,
                timeout=20,
            )
            return [
                raw.decode("utf-8")
                for raw in completed.stdout.split(b"\0")
                if raw
            ]
        except (
            OSError,
            UnicodeDecodeError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ) as error:
            raise ValueError("writer dirty path state is unavailable") from error

    tracked = nul_paths(
        "diff", "--no-ext-diff", "--no-textconv", "--no-renames",
        "--name-only", "-z", "HEAD", "--"
    )
    untracked = nul_paths(
        "ls-files", "--others", "--exclude-standard", "-z", "--"
    )
    staged = nul_paths(
        "diff", "--no-ext-diff", "--no-textconv", "--cached",
        "--name-only", "-z", "--"
    )
    return sorted(set(tracked + untracked)), sorted(set(staged))


def _git_bytes(repo: Path, *args: str) -> bytes:
    """Return exact Git bytes for publication evidence or fail closed."""

    try:
        completed = subprocess.run(
            _native_git_command(repo, *args),
            check=True,
            capture_output=True,
            env=_native_git_environment(),
            stdin=subprocess.DEVNULL,
            timeout=20,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise ValueError("LW2 publication Git evidence is unavailable") from error
    return completed.stdout


def _origin_urls(repo: Path) -> tuple[list[str], list[str]]:
    from agent_governance_capture import native_origin_urls
    return native_origin_urls(repo)


def _canonical_remote_head(repo: Path, repository_url: str, ref: str) -> str | None:
    from agent_governance_capture import native_remote_head
    return native_remote_head(repo, repository_url, ref)


def _publication_boundary(
    *,
    repo: Path,
    identity: WorktreeIdentity,
    lease: dict[str, str],
    record: dict[str, Any],
    selected: bool,
    publication_status: dict[str, Any] | None,
    publication_native_snapshot: dict[str, Any] | None,
    phase: str | None,
    expected_branch: str | None,
    expected_head: str | None,
) -> tuple[dict[str, Any], list[str], datetime]:
    """Finish publication while admission then writer locks remain held.

    The trusted clock is deliberately the final I/O boundary.  Its return is
    followed only by pure validation and result construction.
    """

    from agent_governance_lw2_readmission import LW2_DESTINATION_REF, LW2_REPOSITORY_URL
    from agent_governance_capture import (
        NativeEvidenceMismatch,
        NativeEvidenceUnavailable,
        capture_native_protected_snapshot,
        validate_public_github_repository_ref,
    )

    final_phase = phase
    source_sha = expected_head
    branch = expected_branch
    reasons: list[str] = []

    try:
        final_identity = inspect_worktree(repo, native_graph=True)
        dirty_paths, staged_paths = _capture_dirty_paths(repo, native_graph=True)
    except ValueError:
        final_identity = None
        dirty_paths, staged_paths = [], []
        reasons.append("PUBLICATION_FINAL_FEATURE_UNAVAILABLE")
    final_native_snapshot = None
    if selected:
        try:
            final_native_snapshot = capture_native_protected_snapshot(
                repo, allowed_worktree_differences=record["task_contract"]["dirty_scope"]
            )
        except NativeEvidenceUnavailable:
            reasons.append("LW2_PUBLICATION_FINAL_GENERATION_UNAVAILABLE")
        except (NativeEvidenceMismatch, ValueError):
            reasons.append("LW2_PUBLICATION_FINAL_GENERATION_MISMATCH")

    try:
        post_generation_identity = inspect_worktree(repo, native_graph=True)
        post_generation_dirty, post_generation_staged = _capture_dirty_paths(
            repo, native_graph=True
        )
    except ValueError:
        post_generation_identity = None
        post_generation_dirty, post_generation_staged = [], []
        reasons.append("PUBLICATION_FINAL_FEATURE_UNAVAILABLE")
    try:
        fetch_urls, push_urls = _origin_urls(repo)
    except ValueError:
        fetch_urls, push_urls = [], []
        reasons.append("FINAL_ORIGIN_URL_UNAVAILABLE")
    main_ref = LW2_DESTINATION_REF
    branch_ref = f"refs/heads/{branch}" if isinstance(branch, str) else ""
    urls_match = len(fetch_urls) == 1 and fetch_urls == push_urls
    repository_url = fetch_urls[0] if urls_match else ""
    public_origin_valid = bool(
        repository_url
        and validate_public_github_repository_ref(repository_url, main_ref)
        and (
            final_phase != "post-push"
            or validate_public_github_repository_ref(repository_url, branch_ref)
        )
    )
    local_main = _git_text(
        repo, "rev-parse", "refs/remotes/origin/main", native_graph=True
    )
    canonical_main = (
        _canonical_remote_head(repo, repository_url, main_ref)
        if public_origin_valid else None
    )
    canonical_branch = (
        _canonical_remote_head(repo, repository_url, branch_ref)
        if public_origin_valid and final_phase == "post-push" else None
    )
    final_time = _utc_now()
    # Pure in-memory checks only below this line.
    if not urls_match:
        reasons.append("FINAL_ORIGIN_URL_MISMATCH")
    elif not public_origin_valid:
        reasons.append("FINAL_ORIGIN_URL_INVALID")
    if selected and (fetch_urls != [LW2_REPOSITORY_URL] or push_urls != [LW2_REPOSITORY_URL]):
        reasons.append("LW2_PUBLICATION_FINAL_ORIGIN_URL_DRIFT")
    if final_identity is not None and (
        final_identity.worktree != identity.worktree
        or final_identity.common_dir != identity.common_dir
        or final_identity.branch != branch
        or final_identity.head != source_sha
        or final_identity.dirty or dirty_paths or staged_paths
    ):
        reasons.append("PUBLICATION_FINAL_FEATURE_DRIFT")
    feature = publication_status.get("feature") if isinstance(publication_status, dict) else None
    if selected and (
        not isinstance(feature, dict)
        or feature.get("head") != source_sha
        or publication_native_snapshot is None
        or final_native_snapshot != publication_native_snapshot
    ):
        reasons.append("LW2_PUBLICATION_FINAL_GENERATION_MISMATCH")
    if post_generation_identity is not None and (
        post_generation_identity.worktree != identity.worktree
        or post_generation_identity.common_dir != identity.common_dir
        or post_generation_identity.branch != branch
        or post_generation_identity.head != source_sha
        or post_generation_identity.dirty or post_generation_dirty
        or post_generation_staged
    ):
        reasons.append("PUBLICATION_FINAL_FEATURE_DRIFT")
    accepted_base = (
        publication_status.get("accepted_base")
        if isinstance(publication_status, dict)
        else None
    )
    accepted_head = (
        accepted_base.get("head") if isinstance(accepted_base, dict) else None
    )
    if local_main is None:
        reasons.append("FINAL_LOCAL_ORIGIN_MAIN_UNAVAILABLE")
    if canonical_main is None:
        reasons.append("FINAL_TRUE_ORIGIN_MAIN_UNAVAILABLE")
    expected_main_heads = [local_main]
    if selected:
        expected_main_heads.append(accepted_head)
    if canonical_main is not None and any(
        item is None or canonical_main != item for item in expected_main_heads
    ):
        reasons.append("FINAL_TRUE_ORIGIN_MAIN_DRIFT")
    if final_phase == "post-push" and canonical_branch != source_sha:
        reasons.append("REMOTE_BRANCH_HEAD_MISMATCH")
    if record.get("state") != "ACTIVE":
        reasons.append("TASK_ADMISSION_TERMINAL")
    if not _active_lease(lease, final_time):
        reasons.append("WRITER_LEASE_EXPIRED")
    boundary = {
        "schema_version": "writer_publication_boundary_v1",
        "phase": final_phase,
        "publication_source_sha": source_sha,
        "push_refspec": (
            f"{source_sha}:refs/heads/{branch}"
            if isinstance(source_sha, str) and isinstance(branch, str)
            else None
        ),
        "local_origin_main": local_main,
        "true_origin_main": canonical_main,
        "true_remote_branch_head": canonical_branch,
        "observed_at": _timestamp(final_time),
    }
    return boundary, list(dict.fromkeys(reasons)), final_time


def _unsafe_replace_namespace(namespace: Path) -> bool:
    """Reject loose replace material without following filesystem indirection."""

    try:
        metadata = namespace.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        return True
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_mode & 0o444 == 0
        or metadata.st_mode & 0o111 == 0
    ):
        return True
    try:
        with os.scandir(namespace) as entries:
            return next(entries, None) is not None
    except OSError:
        return True


def _capture_native_graph_safety(
    *,
    repo: Path,
    common_dir: Path,
    canonical_claim_digest: Callable[[Any], str],
) -> tuple[dict[str, Any] | None, bool]:
    """Capture absence of every local Git graph projection mechanism."""

    ambient_replace_base = "GIT_REPLACE_REF_BASE" in os.environ
    try:
        raw_refs = _git_bytes(
            repo, "for-each-ref", "--format=%(refname)", "refs/replace/"
        )
        replace_refs = sorted(
            line.decode("utf-8") for line in raw_refs.splitlines() if line
        )
    except (UnicodeDecodeError, ValueError):
        return None, True
    replace_namespace_unsafe = _unsafe_replace_namespace(
        common_dir / "refs" / "replace"
    )
    grafts = common_dir / "info" / "grafts"
    try:
        grafts.lstat()
    except FileNotFoundError:
        grafts_present = False
    except OSError:
        grafts_present = True
    else:
        grafts_present = True
    if (
        ambient_replace_base
        or replace_refs
        or replace_namespace_unsafe
        or grafts_present
    ):
        return None, True
    empty_digest = canonical_claim_digest([])
    native_graph = {
        "schema_version": "lw2_native_git_graph_v1",
        "read_mode": "git_--no-replace-objects",
        "git_replace_ref_base": "ABSENT",
        "replace_namespace": "refs/replace/",
        "replace_ref_count": 0,
        "replace_refs_digest": empty_digest,
        "grafts": "ABSENT",
        "grafts_digest": empty_digest,
    }
    return native_graph, False


def _capture_lw2_publication_generation(
    repo: Path,
    task_contract: dict[str, Any],
    *,
    canonical_claim_digest: Callable[[Any], str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reuse the admission producer for the exact current feature generation."""
    del canonical_claim_digest
    from agent_governance_task_admission import capture_task_admission_generation_evidence
    return capture_task_admission_generation_evidence(repo, task_contract)


def _ordinary_publication_status(
    *,
    repo: Path,
    record: dict[str, Any],
    expected_head: str,
    canonical_claim_digest: Callable[[Any], str],
) -> tuple[dict[str, Any] | None, list[str]]:
    """Bind one ordinary publication to its admitted native commit range."""

    from agent_governance_capture import (
        NativeEvidenceMismatch,
        NativeEvidenceUnavailable,
        capture_native_linear_commit_range,
        native_commit_identity,
    )

    accepted = record.get("accepted_base")
    if not isinstance(accepted, dict):
        return None, ["ORDINARY_PUBLICATION_ACCEPTED_BASE_MISSING"]
    accepted_head = accepted["head"]
    accepted_tree = accepted["tree"]
    reasons: list[str] = []
    try:
        base_object_tree, _ = native_commit_identity(repo, accepted_head)
        feature_tree, _ = native_commit_identity(repo, expected_head)
    except (NativeEvidenceMismatch, NativeEvidenceUnavailable):
        return None, ["ORDINARY_PUBLICATION_COMMIT_EVIDENCE_UNAVAILABLE"]
    if base_object_tree != accepted_tree:
        reasons.append("ORDINARY_PUBLICATION_ACCEPTED_BASE_OBJECT_MISMATCH")
    commit_records, patch_records, range_reasons = (
        capture_native_linear_commit_range(repo, accepted_head, expected_head)
    )
    reasons.extend({
        "NATIVE_COMMIT_RANGE_UNAVAILABLE": "ORDINARY_PUBLICATION_COMMIT_EVIDENCE_UNAVAILABLE",
        "NATIVE_COMMIT_RANGE_BASE_NOT_ANCESTOR": "ORDINARY_PUBLICATION_BASE_NOT_ANCESTOR",
        "NATIVE_COMMIT_RANGE_NONLINEAR_HISTORY": "ORDINARY_PUBLICATION_NONLINEAR_HISTORY",
        "NATIVE_COMMIT_RANGE_EMPTY": "ORDINARY_PUBLICATION_EMPTY_COMMIT_RANGE",
    }[reason] for reason in range_reasons)
    touched_paths = sorted({
        path for commit in commit_records for path in commit["paths"]
    })
    if not set(touched_paths).issubset(record["task_contract"]["dirty_scope"]):
        reasons.append(
            "ORDINARY_PUBLICATION_COMMITTED_PATH_OUTSIDE_ADMITTED_SCOPE"
        )
    if reasons:
        return None, list(dict.fromkeys(reasons))
    native_range = {
        "schema_version": "native_linear_commit_range_v1",
        "read_mode": "git_--no-replace-objects",
        "rename_detection": "disabled",
        "textconv": "disabled",
    }
    return {
        "schema_version": "ordinary_writer_publication_status_v1",
        "accepted_base": dict(accepted),
        "feature": {"head": expected_head, "tree": feature_tree},
        "ordered_commits": [item["commit"] for item in commit_records],
        "touched_paths": touched_paths,
        "native_range": native_range,
        "native_range_digest": canonical_claim_digest(native_range),
        "ordered_commit_path_digest": canonical_claim_digest(commit_records),
        "binary_patch_digest": canonical_claim_digest(patch_records),
    }, []


def _lw2_publication_status(
    *,
    repo: Path,
    identity: WorktreeIdentity,
    record: dict[str, Any],
    canonical_claim_digest: Callable[[Any], str],
) -> tuple[dict[str, Any] | None, list[str], dict[str, Any] | None]:
    """Recapture a read-only, admission-bound LW2 publication transition."""

    from agent_governance_capture import (
        NativeEvidenceMismatch,
        NativeEvidenceUnavailable,
        PLATFORM_OR_EXTERNAL_ATTESTED,
        capture_native_linear_commit_range,
        native_commit_identity,
    )
    from agent_governance_lw2_readmission import (
        LW2_DESTINATION_REF,
        LW2_REPOSITORY_URL,
    )

    accepted = record["accepted_generation"]
    task_contract = record["task_contract"]
    accepted_head = accepted["source_head"]
    accepted_tree = accepted["source_tree"]
    reasons: list[str] = []
    native_graph, graph_projection_present = _capture_native_graph_safety(
        repo=repo,
        common_dir=identity.common_dir,
        canonical_claim_digest=canonical_claim_digest,
    )
    if graph_projection_present:
        return None, ["LW2_PUBLICATION_GRAPH_PROJECTION_PRESENT"], None
    assert native_graph is not None

    claim_inputs = task_contract.get("claim_inputs")
    claim_payloads = task_contract.get("claim_payloads")
    base_identity = (
        claim_payloads.get("lw2_combined_main_identity")
        if isinstance(claim_payloads, dict)
        else None
    )
    identity_fields = {
        "schema_version", "repository_url", "destination_ref", "head", "tree",
        "publication_provenance",
    }
    publication_fields = {
        "schema_version", "trust_tier", "provider", "provider_record_id",
        "repository_url", "destination_ref", "head", "tree", "status",
        "record_digest",
    }
    publication = (
        base_identity.get("publication_provenance")
        if isinstance(base_identity, dict)
        else None
    )
    if (
        not isinstance(base_identity, dict)
        or set(base_identity) != identity_fields
        or base_identity.get("schema_version") != "lw2_combined_main_identity_v2"
        or base_identity.get("repository_url") != LW2_REPOSITORY_URL
        or base_identity.get("destination_ref") != LW2_DESTINATION_REF
        or (base_identity.get("head"), base_identity.get("tree"))
        != (accepted_head, accepted_tree)
        or not isinstance(claim_inputs, dict)
        or claim_inputs.get("lw2_combined_main_identity")
        != canonical_claim_digest(base_identity)
    ):
        reasons.append("LW2_PUBLICATION_ACCEPTED_BASE_CLAIM_MISMATCH")
    if (
        not isinstance(publication, dict)
        or set(publication) != publication_fields
        or publication.get("schema_version")
        != "lw2_destination_publication_provenance_v1"
        or publication.get("trust_tier") != PLATFORM_OR_EXTERNAL_ATTESTED
        or publication.get("provider") != "github"
        or not isinstance(publication.get("provider_record_id"), str)
        or not publication.get("provider_record_id", "").strip()
        or publication.get("repository_url") != LW2_REPOSITORY_URL
        or publication.get("destination_ref") != LW2_DESTINATION_REF
        or (publication.get("head"), publication.get("tree"))
        != (accepted_head, accepted_tree)
        or publication.get("status") != "PUBLISHED"
        or publication.get("record_digest")
        != canonical_claim_digest({
            key: value
            for key, value in publication.items()
            if key != "record_digest"
        })
    ):
        reasons.append("LW2_PUBLICATION_BASE_PROVENANCE_INVALID")
    if (
        not identity.linked
        or identity.branch in {None, "main"}
    ):
        reasons.append("LW2_PUBLICATION_FEATURE_WORKTREE_REQUIRED")

    try:
        dirty_paths, staged_paths = _capture_dirty_paths(repo, native_graph=True)
    except ValueError:
        dirty_paths, staged_paths = [], []
        reasons.append("LW2_PUBLICATION_DIRTY_STATE_UNAVAILABLE")
    origin_main = _git_text(
        repo,
        "rev-parse",
        "refs/remotes/origin/main",
        native_graph=True,
    )
    try:
        origin_fetch_urls, origin_push_urls = _origin_urls(repo)
    except ValueError:
        origin_fetch_urls, origin_push_urls = [], []
    try:
        accepted_object_tree, _ = native_commit_identity(repo, accepted_head)
    except (NativeEvidenceMismatch, NativeEvidenceUnavailable):
        accepted_object_tree = None
    if accepted_object_tree != accepted_tree:
        reasons.append("LW2_PUBLICATION_ACCEPTED_BASE_OBJECT_MISMATCH")
    if origin_fetch_urls != [LW2_REPOSITORY_URL]:
        reasons.append("LW2_PUBLICATION_ORIGIN_FETCH_URL_MISMATCH")
    if origin_push_urls != [LW2_REPOSITORY_URL]:
        reasons.append("LW2_PUBLICATION_ORIGIN_PUSH_URL_MISMATCH")
    if origin_main != accepted_head:
        reasons.append("LW2_PUBLICATION_ORIGIN_MAIN_DRIFT")
    if staged_paths:
        reasons.append("LW2_PUBLICATION_STAGED_CHANGES")
    if identity.dirty or dirty_paths:
        reasons.append("LW2_PUBLICATION_DIRTY_WORKTREE")
    feature_head = identity.head or ""
    try:
        feature_tree, _ = native_commit_identity(repo, feature_head)
    except (NativeEvidenceMismatch, NativeEvidenceUnavailable):
        feature_tree = ""
        reasons.append("LW2_PUBLICATION_COMMIT_EVIDENCE_UNAVAILABLE")
    commit_path_records, patch_records, range_reasons = (
        capture_native_linear_commit_range(repo, accepted_head, feature_head)
    )
    reasons.extend({
        "NATIVE_COMMIT_RANGE_UNAVAILABLE": "LW2_PUBLICATION_COMMIT_EVIDENCE_UNAVAILABLE",
        "NATIVE_COMMIT_RANGE_BASE_NOT_ANCESTOR": "LW2_PUBLICATION_BASE_NOT_ANCESTOR",
        "NATIVE_COMMIT_RANGE_NONLINEAR_HISTORY": "LW2_PUBLICATION_NONLINEAR_HISTORY",
        "NATIVE_COMMIT_RANGE_EMPTY": "LW2_PUBLICATION_EMPTY_COMMIT_RANGE",
    }[reason] for reason in range_reasons)
    touched_paths = sorted({
        path
        for commit_record in commit_path_records
        for path in commit_record["paths"]
    })
    if not set(touched_paths).issubset(task_contract["dirty_scope"]):
        reasons.append("LW2_PUBLICATION_COMMITTED_PATH_OUTSIDE_ADMITTED_SCOPE")

    final_native_graph, final_graph_projection_present = (
        _capture_native_graph_safety(
            repo=repo,
            common_dir=identity.common_dir,
            canonical_claim_digest=canonical_claim_digest,
        )
    )
    if final_graph_projection_present or final_native_graph != native_graph:
        return None, ["LW2_PUBLICATION_GRAPH_PROJECTION_PRESENT"], None
    try:
        final_identity = inspect_worktree(repo, native_graph=True)
        final_tree, _ = native_commit_identity(repo, final_identity.head or "")
    except (ValueError, NativeEvidenceMismatch, NativeEvidenceUnavailable):
        final_identity = None
        final_tree = None
        reasons.append("LW2_PUBLICATION_FINAL_RECAPTURE_UNAVAILABLE")
    final_origin_main = _git_text(
        repo,
        "rev-parse",
        "refs/remotes/origin/main",
        native_graph=True,
    )
    try:
        final_origin_fetch_urls, final_origin_push_urls = _origin_urls(repo)
    except ValueError:
        final_origin_fetch_urls, final_origin_push_urls = [], []
        reasons.append("LW2_PUBLICATION_FINAL_RECAPTURE_UNAVAILABLE")
    try:
        final_dirty_paths, final_staged_paths = _capture_dirty_paths(
            repo, native_graph=True
        )
    except ValueError:
        final_dirty_paths, final_staged_paths = [], []
        reasons.append("LW2_PUBLICATION_FINAL_RECAPTURE_UNAVAILABLE")
    try:
        final_generation, final_native_snapshot = _capture_lw2_publication_generation(
            repo,
            task_contract,
            canonical_claim_digest=canonical_claim_digest,
        )
    except NativeEvidenceUnavailable:
        final_generation = None
        final_native_snapshot = None
        reasons.append("LW2_PUBLICATION_FINAL_RECAPTURE_UNAVAILABLE")
    except (NativeEvidenceMismatch, ValueError):
        final_generation = None
        final_native_snapshot = None
        reasons.append("LW2_PUBLICATION_FEATURE_GENERATION_MISMATCH")
    if final_identity is not None and (
        final_identity.worktree != identity.worktree
        or final_identity.common_dir != identity.common_dir
        or final_identity.branch != identity.branch
        or final_identity.head != feature_head
        or final_tree != feature_tree
        or final_origin_main != origin_main
        or final_identity.dirty != identity.dirty
        or final_dirty_paths != dirty_paths
        or final_staged_paths != staged_paths
    ):
        reasons.append("LW2_PUBLICATION_FINAL_RECAPTURE_DRIFT")
    if (
        final_origin_fetch_urls != origin_fetch_urls
        or final_origin_push_urls != origin_push_urls
    ):
        reasons.append("LW2_PUBLICATION_FINAL_ORIGIN_URL_DRIFT")
    if final_generation is not None:
        if final_generation["scope"] != accepted["scope"]:
            reasons.append("LW2_PUBLICATION_PROTECTED_INVENTORY_DRIFT")
        if (
            final_generation["source_head"],
            final_generation["source_tree"],
        ) != (feature_head, feature_tree):
            reasons.append("LW2_PUBLICATION_FEATURE_IDENTITY_DRIFT")
    if reasons:
        return None, list(dict.fromkeys(reasons)), final_native_snapshot

    assert isinstance(publication, dict)
    assert final_generation is not None
    return {
        "schema_version": "lw2_writer_publication_status_v1",
        "accepted_base": {
            "head": accepted_head,
            "tree": accepted_tree,
            "generation_digest": canonical_claim_digest(accepted),
            "publication_provenance_digest": publication["record_digest"],
        },
        "feature": {
            "head": feature_head,
            "tree": feature_tree,
            "generation_digest": canonical_claim_digest(final_generation),
        },
        "ordered_commits": [
            item["commit"] for item in commit_path_records
        ],
        "touched_paths": touched_paths,
        "native_graph": native_graph,
        "native_graph_digest": canonical_claim_digest(native_graph),
        "ordered_commit_path_digest": canonical_claim_digest(commit_path_records),
        "binary_patch_digest": canonical_claim_digest({
            "native_graph_digest": canonical_claim_digest(native_graph),
            "patch_records": patch_records,
        }),
    }, [], final_native_snapshot


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
        "admission_scope": None,
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


def _acquire_writer_lease(
    store: WriterLeaseStore,
    identity: WorktreeIdentity,
    *,
    task_id: str,
    owner: str,
    ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
    now: datetime | None = None,
    admission_binding: dict[str, str] | None = None,
    pre_persist_validate: Callable[[], list[str]] | None = None,
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
        if pre_persist_validate is not None:
            validation_reasons = pre_persist_validate()
            if validation_reasons:
                raise _WriterLeasePreconditionFailed(validation_reasons)
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
        if admission_binding is not None:
            lease.update(admission_binding)
        leases[identity.worktree] = lease
        result["lease"] = lease
        return state

    try:
        store.update(mutation)
    except _WriterLeasePreconditionFailed as error:
        result["reasons"] = error.reasons
    if result.get("reasons"):
        return _lease_result(
            "acquire",
            status="FAIL",
            reasons=result["reasons"],
            identity=identity,
            lease=None,
        )
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


def acquire_writer_lease(
    store: WriterLeaseStore,
    identity: WorktreeIdentity,
    *,
    task_id: str,
    owner: str,
    admission_id: str | None = None,
    ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Acquire in memory, or require production task-admission authority."""

    if isinstance(store, FileWriterLeaseStore):
        if store.common_dir != identity.common_dir.resolve():
            return _lease_result(
                "acquire", status="FAIL",
                reasons=["WRITER_LEASE_STORE_MISMATCH"],
                identity=identity, lease=None,
            )
        return filesystem_writer_lease_action(
            action="acquire",
            repo=Path(identity.worktree),
            task_id=task_id,
            owner=owner,
            admission_id=admission_id,
            ttl_seconds=ttl_seconds,
            now=now,
        )

    from agent_governance_lw2_readmission import lw2_contract_selected

    if lw2_contract_selected({}, task_id=task_id):
        return _lease_result(
            "acquire", status="FAIL",
            reasons=["LW2_ADMISSION_ACTION_REQUIRED"],
            identity=identity, lease=None,
        )
    return _acquire_writer_lease(
        store, identity, task_id=task_id, owner=owner,
        ttl_seconds=ttl_seconds, now=now,
    )


def _validate_writer_lease(
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


def validate_writer_lease(
    store: WriterLeaseStore,
    identity: WorktreeIdentity,
    *,
    task_id: str,
    lease_id: str,
    owner: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate an ordinary lease; bound LW2 leases require the action API."""

    if isinstance(store, FileWriterLeaseStore):
        return _lease_result(
            "validate", status="FAIL",
            reasons=["TASK_ADMISSION_ACTION_REQUIRED"],
            identity=identity, lease=None,
        )
    try:
        lease = store.read()["leases"].get(identity.worktree)
    except ValueError:
        lease = None
    if isinstance(lease, dict) and set(lease) == LW2_WRITER_LEASE_FIELDS:
        return _lease_result(
            "validate", status="FAIL",
            reasons=["LW2_ADMISSION_ACTION_REQUIRED"],
            identity=identity, lease=None,
        )
    return _validate_writer_lease(
        store, identity, task_id=task_id, lease_id=lease_id,
        owner=owner, now=now,
    )


def _renew_writer_lease(
    store: WriterLeaseStore,
    identity: WorktreeIdentity,
    *,
    task_id: str,
    owner: str,
    lease_id: str,
    ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
    now: datetime | None = None,
    pre_renew_validate: Callable[[], list[str]] | None = None,
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
        if pre_renew_validate is not None:
            validation_reasons = pre_renew_validate()
            if validation_reasons:
                result["reasons"] = validation_reasons
                return state
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
    """Renew an ordinary lease; bound LW2 leases require the action API."""

    if isinstance(store, FileWriterLeaseStore):
        return _lease_result(
            "renew", status="FAIL",
            reasons=["TASK_ADMISSION_ACTION_REQUIRED"],
            identity=identity, lease=None,
        )
    try:
        lease = store.read()["leases"].get(identity.worktree)
    except ValueError:
        lease = None
    if isinstance(lease, dict) and set(lease) == LW2_WRITER_LEASE_FIELDS:
        return _lease_result(
            "renew", status="FAIL",
            reasons=["LW2_ADMISSION_ACTION_REQUIRED"],
            identity=identity, lease=None,
        )
    return _renew_writer_lease(
        store, identity, task_id=task_id, owner=owner,
        lease_id=lease_id, ttl_seconds=ttl_seconds, now=now,
    )


def _release_writer_lease(
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


def release_writer_lease(
    store: WriterLeaseStore,
    identity: WorktreeIdentity,
    *,
    task_id: str,
    owner: str,
    lease_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Release an ordinary lease; bound LW2 leases require the action API."""

    if isinstance(store, FileWriterLeaseStore):
        return _lease_result(
            "release", status="FAIL",
            reasons=["TASK_ADMISSION_ACTION_REQUIRED"],
            identity=identity, lease=None,
        )
    try:
        lease = store.read()["leases"].get(identity.worktree)
    except ValueError:
        lease = None
    if isinstance(lease, dict) and set(lease) == LW2_WRITER_LEASE_FIELDS:
        return _lease_result(
            "release", status="FAIL",
            reasons=["LW2_ADMISSION_ACTION_REQUIRED"],
            identity=identity, lease=None,
        )
    return _release_writer_lease(
        store, identity, task_id=task_id, owner=owner,
        lease_id=lease_id, now=now,
    )


def filesystem_writer_lease_action(
    *,
    action: str,
    repo: Path,
    task_id: str,
    owner: str,
    lease_id: str | None = None,
    admission_id: str | None = None,
    ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
    now: datetime | None = None,
    publication_phase: str | None = None,
    publication_expected_branch: str | None = None,
    publication_expected_head: str | None = None,
) -> dict[str, Any]:
    """Run one explicit production writer-lease action."""

    identity = inspect_worktree(repo, native_graph=action == "publication-status")
    if action == "publication-status":
        from agent_governance_capture import publication_input_reasons
        input_reasons = publication_input_reasons(
            publication_phase, publication_expected_branch,
            publication_expected_head,
        )
        if input_reasons:
            return _lease_result(
                action, status="FAIL", reasons=input_reasons,
                identity=identity, lease=None,
            )
    store = FileWriterLeaseStore(identity.common_dir)
    from agent_governance_lw2_readmission import (  # local: avoid cycle
        canonical_claim_digest,
        lw2_contract_selected,
        validate_lw2_contract_binding,
    )
    from agent_governance_task_admission import (  # local: avoid cycle
        FileTaskAdmissionStore,
        capture_task_admission_generation,
    )
    from agent_governance_capture import (
        NativeEvidenceMismatch,
        NativeEvidenceUnavailable,
    )

    admission_store = FileTaskAdmissionStore(identity.common_dir)
    current_time = (
        None if action == "publication-status" else (now or _utc_now())
    )

    def admission_reasons(
        record: dict[str, Any] | None,
        *,
        require_active: bool,
    ) -> list[str]:
        reasons: list[str] = []
        if record is None:
            return ["TASK_ADMISSION_MISSING"]
        if record["task_id"] != task_id:
            reasons.append("TASK_ADMISSION_TASK_MISMATCH")
        if record["owner"] != owner:
            reasons.append("TASK_ADMISSION_OWNER_MISMATCH")
        if record["admission_id"] != admission_id:
            reasons.append("TASK_ADMISSION_ID_MISMATCH")
        if require_active and record["state"] != "ACTIVE":
            reasons.append("TASK_ADMISSION_TERMINAL")
        return reasons

    def exact_lease_result(
        lease: dict[str, str] | None,
        locked_identity: WorktreeIdentity,
        *,
        validation_time: datetime | None = None,
    ) -> dict[str, Any]:
        effective_time = validation_time or current_time
        assert effective_time is not None
        reasons = _lease_validation_reasons(
            lease,
            locked_identity,
            task_id=task_id,
            lease_id=lease_id or "",
            owner=owner,
            now=effective_time,
        )
        return _lease_result(
            action,
            status="FAIL" if reasons else "PASS",
            reasons=reasons,
            identity=locked_identity,
            lease=lease,
        )

    def action_under_admission_lock(state: dict[str, Any]) -> dict[str, Any]:
        record = state["admissions"].get(identity.worktree)
        if not admission_id:
            return _lease_result(
                action, status="FAIL",
                reasons=["TASK_ADMISSION_ID_REQUIRED"],
                identity=identity, lease=None,
            )
        if action != "acquire" and not lease_id:
            return _lease_result(
                action, status="FAIL",
                reasons=["WRITER_LEASE_ID_REQUIRED"],
                identity=identity, lease=None,
            )

        def writer_transaction(
            lease_state: dict[str, Any],
            binding_state: dict[str, Any],
        ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], bool]:
            locked_identity = inspect_worktree(
                repo, native_graph=action == "publication-status"
            )
            if (
                locked_identity.worktree != identity.worktree
                or locked_identity.common_dir != identity.common_dir
                or locked_identity.branch != identity.branch
                or locked_identity.head != identity.head
            ):
                result = _lease_result(
                    action, status="FAIL",
                    reasons=["WRITER_LEASE_IDENTITY_DRIFT"],
                    identity=locked_identity, lease=None,
                )
                return lease_state, binding_state, result, False
            lease_validation_time = (
                _utc_now() if action == "publication-status" else current_time
            )
            assert lease_validation_time is not None
            lease = lease_state["leases"].get(identity.worktree)
            binding = binding_state["bindings"].get(identity.worktree)
            selected = (
                lw2_contract_selected({}, task_id=task_id)
                or (
                    record is not None
                    and lw2_contract_selected(
                        record["task_contract"], task_id=record["task_id"]
                    )
                )
                or (
                    isinstance(lease, dict)
                    and set(lease) == LW2_WRITER_LEASE_FIELDS
                )
            )

            if action == "release":
                if selected:
                    if (
                        not isinstance(lease, dict)
                        or set(lease) != LW2_WRITER_LEASE_FIELDS
                    ):
                        result = _lease_result(
                            action, status="FAIL",
                            reasons=["LW2_LEASE_BINDING_MISSING"],
                            identity=locked_identity, lease=None,
                        )
                        return lease_state, binding_state, result, False
                    if lease["admission_id"] != admission_id:
                        result = _lease_result(
                            action, status="FAIL",
                            reasons=["TASK_ADMISSION_ID_MISMATCH"],
                            identity=locked_identity, lease=None,
                        )
                        return lease_state, binding_state, result, False
                elif (
                    binding is not None
                    and isinstance(lease, dict)
                    and binding["lease_id"] == lease.get("lease_id")
                ):
                    expected_binding = {
                        "lease_id": lease_id,
                        "task_id": task_id,
                        "owner": owner,
                        "worktree": identity.worktree,
                        "admission_id": admission_id,
                        "task_contract_digest": binding["task_contract_digest"],
                    }
                    if binding != expected_binding:
                        result = _lease_result(
                            action, status="FAIL",
                            reasons=["WRITER_LEASE_ADMISSION_BINDING_MISMATCH"],
                            identity=locked_identity, lease=None,
                        )
                        return lease_state, binding_state, result, False
                result = exact_lease_result(lease, locked_identity)
                if result["status"] != "PASS":
                    return lease_state, binding_state, result, False
                del lease_state["leases"][identity.worktree]
                binding_state["bindings"].pop(identity.worktree, None)
                result["lease"] = None
                return lease_state, binding_state, result, True

            reasons = admission_reasons(record, require_active=True)
            if reasons:
                result = _lease_result(
                    action, status="FAIL", reasons=reasons,
                    identity=locked_identity, lease=None,
                )
                return lease_state, binding_state, result, False
            assert record is not None

            if action == "acquire":
                acquire_reasons: list[str] = []
                if ttl_seconds < MIN_LEASE_TTL_SECONDS or ttl_seconds > MAX_LEASE_TTL_SECONDS:
                    acquire_reasons.append("LEASE_TTL_OUT_OF_RANGE")
                if not locked_identity.linked:
                    acquire_reasons.append("LINKED_WORKTREE_REQUIRED")
                if locked_identity.branch in {None, "main"}:
                    acquire_reasons.append("ATTACHED_FEATURE_BRANCH_REQUIRED")
                if locked_identity.dirty and not selected:
                    acquire_reasons.append("CLEAN_WORKTREE_REQUIRED")
                if lease and _active_lease(lease, current_time):
                    acquire_reasons.append("WORKTREE_WRITER_LEASE_HELD")
                if acquire_reasons:
                    result = _lease_result(
                        action, status="FAIL", reasons=acquire_reasons,
                        identity=locked_identity, lease=None,
                    )
                    return lease_state, binding_state, result, False
                if selected:
                    validate_lw2_contract_binding(
                        record["task_contract"],
                        task_id=record["task_id"],
                        repo=Path(identity.worktree),
                    )
                    accepted_generation = record["accepted_generation"]
                    if locked_identity.head != accepted_generation["source_head"]:
                        result = _lease_result(
                            action, status="FAIL",
                            reasons=["TASK_ADMISSION_GENERATION_MISMATCH"],
                            identity=locked_identity, lease=None,
                        )
                        return lease_state, binding_state, result, False
                    try:
                        dirty_paths, staged_paths = _capture_dirty_paths(
                            Path(identity.worktree)
                        )
                    except ValueError:
                        result = _lease_result(
                            action, status="FAIL",
                            reasons=["TASK_ADMISSION_GENERATION_UNAVAILABLE"],
                            identity=locked_identity, lease=None,
                        )
                        return lease_state, binding_state, result, False
                    if staged_paths:
                        result = _lease_result(
                            action, status="FAIL",
                            reasons=["PREEXISTING_STAGED_CHANGES"],
                            identity=locked_identity, lease=None,
                        )
                        return lease_state, binding_state, result, False
                    if not set(dirty_paths).issubset(
                        record["task_contract"]["dirty_scope"]
                    ):
                        result = _lease_result(
                            action, status="FAIL",
                            reasons=["DIRTY_PATH_OUTSIDE_ADMITTED_SCOPE"],
                            identity=locked_identity, lease=None,
                        )
                        return lease_state, binding_state, result, False
                    try:
                        current_generation = capture_task_admission_generation(
                            Path(identity.worktree), record["task_contract"]
                        )
                    except NativeEvidenceUnavailable:
                        result = _lease_result(
                            action, status="FAIL",
                            reasons=["TASK_ADMISSION_GENERATION_UNAVAILABLE"],
                            identity=locked_identity, lease=None,
                        )
                        return lease_state, binding_state, result, False
                    except (NativeEvidenceMismatch, ValueError):
                        result = _lease_result(
                            action, status="FAIL",
                            reasons=["TASK_ADMISSION_GENERATION_MISMATCH"],
                            identity=locked_identity, lease=None,
                        )
                        return lease_state, binding_state, result, False
                    if current_generation != record.get("accepted_generation"):
                        result = _lease_result(
                            action, status="FAIL",
                            reasons=["TASK_ADMISSION_GENERATION_MISMATCH"],
                            identity=locked_identity, lease=None,
                        )
                        return lease_state, binding_state, result, False
                else:
                    accepted_base = record.get("accepted_base")
                    if not isinstance(accepted_base, dict):
                        result = _lease_result(
                            action, status="FAIL",
                            reasons=["TASK_ADMISSION_ACCEPTED_BASE_MISSING"],
                            identity=locked_identity, lease=None,
                        )
                        return lease_state, binding_state, result, False
                    try:
                        from agent_governance_capture import capture_native_head_tree
                        current_base = capture_native_head_tree(
                            Path(identity.worktree)
                        )
                    except (NativeEvidenceMismatch, NativeEvidenceUnavailable):
                        result = _lease_result(
                            action, status="FAIL",
                            reasons=["TASK_ADMISSION_ACCEPTED_BASE_UNAVAILABLE"],
                            identity=locked_identity, lease=None,
                        )
                        return lease_state, binding_state, result, False
                    if current_base != accepted_base:
                        result = _lease_result(
                            action, status="FAIL",
                            reasons=["TASK_ADMISSION_ACCEPTED_BASE_MISMATCH"],
                            identity=locked_identity, lease=None,
                        )
                        return lease_state, binding_state, result, False
                new_lease = {
                    "lease_id": secrets.token_hex(16),
                    "task_id": task_id,
                    "owner": owner,
                    "worktree": identity.worktree,
                    "branch": locked_identity.branch or "",
                    "acquired_at": _timestamp(current_time),
                    "expires_at": _timestamp(
                        current_time + timedelta(seconds=ttl_seconds)
                    ),
                }
                if selected:
                    new_lease.update({
                        "admission_id": admission_id,
                        "accepted_generation_digest": canonical_claim_digest(
                            record["accepted_generation"]
                        ),
                    })
                    binding_state["bindings"].pop(identity.worktree, None)
                else:
                    binding_state["bindings"][identity.worktree] = {
                        "lease_id": new_lease["lease_id"],
                        "task_id": task_id,
                        "owner": owner,
                        "worktree": identity.worktree,
                        "admission_id": admission_id,
                        "task_contract_digest": record["task_contract_digest"],
                    }
                lease_state["leases"][identity.worktree] = new_lease
                result = _lease_result(
                    action, status="PASS", reasons=[],
                    identity=locked_identity, lease=new_lease,
                )
                return lease_state, binding_state, result, True

            if selected:
                validate_lw2_contract_binding(
                    record["task_contract"],
                    task_id=record["task_id"],
                    repo=(
                        None
                        if action == "publication-status"
                        else Path(identity.worktree)
                    ),
                )
                if (
                    not isinstance(lease, dict)
                    or set(lease) != LW2_WRITER_LEASE_FIELDS
                ):
                    result = _lease_result(
                        action, status="FAIL",
                        reasons=["LW2_LEASE_BINDING_MISSING"],
                        identity=locked_identity, lease=None,
                    )
                    return lease_state, binding_state, result, False
                accepted_digest = canonical_claim_digest(
                    record["accepted_generation"]
                )
                if lease["admission_id"] != admission_id:
                    result = _lease_result(
                        action, status="FAIL",
                        reasons=["TASK_ADMISSION_ID_MISMATCH"],
                        identity=locked_identity, lease=None,
                    )
                    return lease_state, binding_state, result, False
                if lease["accepted_generation_digest"] != accepted_digest:
                    result = _lease_result(
                        action, status="FAIL",
                        reasons=["TASK_ADMISSION_GENERATION_MISMATCH"],
                        identity=locked_identity, lease=None,
                    )
                    return lease_state, binding_state, result, False
                if action != "publication-status":
                    try:
                        current_generation = capture_task_admission_generation(
                            Path(identity.worktree), record["task_contract"]
                        )
                    except NativeEvidenceUnavailable:
                        result = _lease_result(
                            action, status="FAIL",
                            reasons=["TASK_ADMISSION_GENERATION_UNAVAILABLE"],
                            identity=locked_identity, lease=None,
                        )
                        return lease_state, binding_state, result, False
                    except (NativeEvidenceMismatch, ValueError):
                        result = _lease_result(
                            action, status="FAIL",
                            reasons=["TASK_ADMISSION_GENERATION_MISMATCH"],
                            identity=locked_identity, lease=None,
                        )
                        return lease_state, binding_state, result, False
                    if current_generation != record.get("accepted_generation"):
                        result = _lease_result(
                            action, status="FAIL",
                            reasons=["TASK_ADMISSION_GENERATION_MISMATCH"],
                            identity=locked_identity, lease=None,
                        )
                        return lease_state, binding_state, result, False
            else:
                ordinary_lease_result = exact_lease_result(
                    lease,
                    locked_identity,
                    validation_time=lease_validation_time,
                )
                if ordinary_lease_result["status"] != "PASS":
                    return (
                        lease_state,
                        binding_state,
                        ordinary_lease_result,
                        False,
                    )
                if binding is None:
                    result = _lease_result(
                        action, status="FAIL",
                        reasons=["WRITER_LEASE_ADMISSION_BINDING_MISSING"],
                        identity=locked_identity, lease=None,
                    )
                    return lease_state, binding_state, result, False
                expected_binding = {
                    "lease_id": lease_id,
                    "task_id": task_id,
                    "owner": owner,
                    "worktree": identity.worktree,
                    "admission_id": admission_id,
                    "task_contract_digest": record["task_contract_digest"],
                }
                if binding != expected_binding:
                    result = _lease_result(
                        action, status="FAIL",
                        reasons=["WRITER_LEASE_ADMISSION_BINDING_MISMATCH"],
                        identity=locked_identity, lease=None,
                    )
                    return lease_state, binding_state, result, False

            result = exact_lease_result(
                lease,
                locked_identity,
                validation_time=lease_validation_time,
            )
            if result["status"] == "PASS" and action in {
                "status", "publication-status",
            }:
                admission_scope = {
                    "task_contract_digest": record["task_contract_digest"],
                    "dirty_scope": list(record["task_contract"]["dirty_scope"]),
                    "lw2_selected": selected,
                }
                publication_status = None
                publication_native_snapshot = None
                publication_boundary = None
                publication_reasons: list[str] = []
                if action == "publication-status":
                    assert lease is not None
                    if selected:
                        publication_status, publication_reasons, publication_native_snapshot = (
                            _lw2_publication_status(
                                repo=Path(identity.worktree), identity=locked_identity,
                                record=record,
                                canonical_claim_digest=canonical_claim_digest,
                            )
                        )
                    else:
                        assert publication_expected_head is not None
                        publication_status, publication_reasons = (
                            _ordinary_publication_status(
                                repo=Path(identity.worktree),
                                record=record,
                                expected_head=publication_expected_head,
                                canonical_claim_digest=canonical_claim_digest,
                            )
                        )
                if action == "publication-status":
                    assert lease is not None
                    if publication_reasons:
                        result["status"] = "FAIL"
                        result["reasons"] = publication_reasons
                        return lease_state, binding_state, result, False
                    publication_boundary, publication_reasons, _ = (
                        _publication_boundary(
                            repo=Path(identity.worktree),
                            identity=locked_identity,
                            lease=lease,
                            record=record,
                            selected=selected,
                            publication_status=publication_status,
                            publication_native_snapshot=publication_native_snapshot,
                            phase=publication_phase,
                            expected_branch=publication_expected_branch,
                            expected_head=publication_expected_head,
                        )
                    )
                    if publication_reasons:
                        result["status"] = "FAIL"
                        result["reasons"] = publication_reasons
                        result["publication_boundary"] = publication_boundary
                        return lease_state, binding_state, result, False
                result["admission_scope"] = admission_scope
                if publication_status is not None:
                    result["publication_status"] = publication_status
                if publication_boundary is not None:
                    result["publication_boundary"] = publication_boundary
                return lease_state, binding_state, result, False
            if result["status"] != "PASS":
                return lease_state, binding_state, result, False
            if action == "renew":
                if ttl_seconds < MIN_LEASE_TTL_SECONDS or ttl_seconds > MAX_LEASE_TTL_SECONDS:
                    result = _lease_result(
                        action, status="FAIL",
                        reasons=["LEASE_TTL_OUT_OF_RANGE"],
                        identity=locked_identity, lease=None,
                    )
                    return lease_state, binding_state, result, False
                assert lease is not None
                lease["expires_at"] = _timestamp(
                    current_time + timedelta(seconds=ttl_seconds)
                )
                result["lease"] = lease
                return lease_state, binding_state, result, True
            raise ValueError(f"unsupported writer lease action: {action}")

        return store.transact(writer_transaction)

    return admission_store.serialized_read(action_under_admission_lock)
