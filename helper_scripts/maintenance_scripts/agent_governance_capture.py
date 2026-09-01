"""Deep, content-addressed evidence capture for Development-Agent governance.

This module separates locally reproducible capture, controller-known metadata,
and platform/external claims.  A self-digest proves canonical integrity only;
it never upgrades a record into platform or external authenticity.
"""

from __future__ import annotations

import base64
import errno
import hashlib
import json
import os
import re
import stat
import subprocess
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

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
TRUSTED_GIT_EXECUTABLE = "/usr/bin/git"
TRUSTED_CURL_EXECUTABLE = "/usr/bin/curl"
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
_AMBIENT_GIT_ENVIRONMENT = {
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CEILING_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_CONFIG_COUNT",
    "GIT_CONFIG_PARAMETERS",
    "GIT_DIR",
    "GIT_DISCOVERY_ACROSS_FILESYSTEM",
    "GIT_EXEC_PATH",
    "GIT_EXTERNAL_DIFF",
    "GIT_GRAFT_FILE",
    "GIT_PROXY_COMMAND",
    "GIT_SSH",
    "GIT_SSH_COMMAND",
    "GIT_ASKPASS",
    "SSH_ASKPASS",
    "GIT_PROTOCOL_FROM_USER",
    "GIT_ALLOW_PROTOCOL",
    "GIT_INDEX_FILE",
    "GIT_NAMESPACE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_REPLACE_REF_BASE",
    "GIT_WORK_TREE",
}
_NUMBERED_GIT_CONFIG_ENVIRONMENT = re.compile(r"GIT_CONFIG_(?:KEY|VALUE)_\d+")
_PUBLIC_GITHUB_REPOSITORY_RE = re.compile(
    r"^https://github\.com/"
    r"([A-Za-z0-9][A-Za-z0-9_.-]{0,99})/"
    r"([A-Za-z0-9][A-Za-z0-9_.-]{0,99})\.git$"
)
_PUBLIC_GITHUB_BRANCH_REF_RE = re.compile(
    r"^refs/heads/[A-Za-z0-9][A-Za-z0-9._/-]{0,254}$"
)


class NativeEvidenceUnavailable(ValueError):
    """Authority evidence could not be observed at all."""


class NativeEvidenceMismatch(ValueError):
    """Authority evidence was observed and deterministically disagreed."""


def native_git_environment() -> dict[str, str]:
    """Return the minimal environment for authority-bearing Git reads."""

    return {
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_PAGER": "cat",
        "GIT_TERMINAL_PROMPT": "0",
        "LANG": "C",
        "LC_ALL": "C",
        "PAGER": "cat",
        "PATH": "/usr/bin:/bin",
    }


def publication_input_reasons(
    phase: str | None, branch: str | None, source_sha: str | None
) -> list[str]:
    """Validate caller-bound publication identity without ambient fallback."""

    reasons: list[str] = []
    if phase is None:
        reasons.append("PUBLICATION_PHASE_REQUIRED")
    elif phase not in {"publish", "post-push"}:
        reasons.append("PUBLICATION_PHASE_INVALID")
    if branch is None:
        reasons.append("PUBLICATION_BRANCH_REQUIRED")
    elif not branch or branch == "main":
        reasons.append("PUBLICATION_BRANCH_INVALID")
    if source_sha is None:
        reasons.append("PUBLICATION_SOURCE_SHA_REQUIRED")
    elif not HEAD_RE.fullmatch(source_sha):
        reasons.append("PUBLICATION_SOURCE_SHA_INVALID")
    return reasons


def _native_git_prefix() -> list[str]:
    return [
        TRUSTED_GIT_EXECUTABLE,
        "--no-replace-objects",
        "-c", "core.fsmonitor=false",
        "-c", "core.hooksPath=/dev/null",
        "-c", "credential.helper=",
        "-c", "protocol.allow=never",
        "-c", "protocol.file.allow=always",
        "-c", "protocol.https.allow=always",
    ]


def native_git_command(root: Path, *arguments: str) -> list[str]:
    return [
        *_native_git_prefix(), "-C", str(root), *arguments,
    ]


def native_remote_git_command(*arguments: str) -> list[str]:
    """Build a Git command that cannot discover repository-local config."""

    return [*_native_git_prefix(), *arguments]


def native_remote_git_cwd(root: Path) -> Path:
    """Return a stable directory outside ``root`` and every parent repository."""

    return Path(root.resolve().anchor)


def _public_github_ref_api_url(repository_url: str, ref: str) -> str | None:
    """Map one exact public GitHub origin/ref to its unauthenticated API URL."""

    match = _PUBLIC_GITHUB_REPOSITORY_RE.fullmatch(repository_url)
    if match is None or _PUBLIC_GITHUB_BRANCH_REF_RE.fullmatch(ref) is None:
        return None
    branch = ref.removeprefix("refs/")
    if (
        ".." in branch
        or "@{" in branch
        or "//" in branch
        or "/." in branch
        or branch.endswith(("/", ".", ".lock"))
    ):
        return None
    owner, repository = match.groups()
    return (
        f"https://api.github.com/repos/{owner}/{repository}/git/ref/"
        f"{quote(branch, safe='/')}"
    )


def _public_github_remote_head(
    root: Path, repository_url: str, ref: str
) -> str | None:
    """Read one public GitHub branch ref without credentials or ambient config."""

    api_url = _public_github_ref_api_url(repository_url, ref)
    if api_url is None:
        return None
    command = [
        TRUSTED_CURL_EXECUTABLE,
        "--disable",
        "--fail",
        "--silent",
        "--show-error",
        "--proto",
        "=https",
        "--tlsv1.2",
        "--connect-timeout",
        "10",
        "--max-time",
        "20",
        "--header",
        "Accept: application/vnd.github+json",
        "--header",
        "X-GitHub-Api-Version: 2022-11-28",
        api_url,
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            cwd=native_remote_git_cwd(root),
            env=native_git_environment(),
            stdin=subprocess.DEVNULL,
            timeout=25,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0 or len(completed.stdout) > 4096:
        return None
    try:
        payload = json.loads(completed.stdout.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    remote_object = payload.get("object")
    if (
        payload.get("ref") != ref
        or not isinstance(remote_object, dict)
        or remote_object.get("type") != "commit"
        or not isinstance(remote_object.get("sha"), str)
        or HEAD_RE.fullmatch(remote_object["sha"]) is None
    ):
        return None
    return remote_object["sha"]


def native_remote_head(root: Path, repository_url: str, ref: str) -> str | None:
    """Query an exact URL, with a bounded public-GitHub read-only fallback."""

    command = native_remote_git_command(
        "ls-remote", "--exit-code", repository_url, ref
    )
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            cwd=native_remote_git_cwd(root),
            env=native_git_environment(),
            stdin=subprocess.DEVNULL,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return _public_github_remote_head(root, repository_url, ref)
    if completed.returncode != 0:
        return None
    try:
        decoded = completed.stdout.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None
    lines = decoded.splitlines()
    if len(lines) != 1 or decoded != f"{lines[0]}\n":
        return None
    fields = lines[0].split("\t")
    if (
        len(fields) != 2
        or fields[1] != ref
        or not HEAD_RE.fullmatch(fields[0])
    ):
        return None
    return fields[0]


def native_origin_urls(root: Path) -> tuple[list[str], list[str]]:
    """Read unprojected local origin URLs without includes or ``insteadOf``."""

    def values(key: str) -> list[str]:
        try:
            completed = subprocess.run(
                native_git_command(root, "config", "--local", "--no-includes",
                                   "--null", "--get-all", key),
                check=False,
                capture_output=True,
                env=native_git_environment(),
                stdin=subprocess.DEVNULL,
                timeout=20,
            )
            decoded = completed.stdout.decode("utf-8", errors="strict")
        except (
            OSError,
            UnicodeDecodeError,
            subprocess.TimeoutExpired,
        ) as error:
            raise NativeEvidenceUnavailable(
                "publication origin URL evidence is unavailable"
            ) from error
        if completed.returncode == 1 and not decoded:
            return []
        if completed.returncode != 0:
            raise NativeEvidenceUnavailable(
                "publication origin URL evidence is unavailable"
            )
        items = decoded.split("\0")
        if (
            len(items) < 2
            or items[-1] != ""
            or any(
                not item
                or item != item.strip()
                or any(ord(character) < 32 for character in item)
                for item in items[:-1]
            )
        ):
            raise NativeEvidenceMismatch("publication origin URL is invalid")
        return items[:-1]

    fetch_urls = values("remote.origin.url")
    push_urls = values("remote.origin.pushurl")
    return fetch_urls, push_urls or list(fetch_urls)


def _protected_filesystem_snapshot(
    repo: Path,
    *,
    exact_paths: set[str],
    prefixes: list[str] | tuple[str, ...],
    allowed_missing_exact_paths: set[str] | frozenset[str] = frozenset(),
) -> tuple[list[str], list[dict[str, str]]]:
    """Enumerate protected members through stable, no-follow descriptors."""

    root = repo.resolve(strict=True)
    records: dict[str, dict[str, str]] = {}
    directory_identities: dict[str, tuple[int, int, int, int]] = {}
    root_descriptor: int | None = None

    def mode_text(metadata: os.stat_result) -> str:
        return f"{stat.S_IFMT(metadata.st_mode):06o}:{stat.S_IMODE(metadata.st_mode):04o}"

    def directory_identity(metadata: os.stat_result) -> tuple[int, int, int, int]:
        return (
            metadata.st_dev,
            metadata.st_ino,
            stat.S_IFMT(metadata.st_mode),
            stat.S_IMODE(metadata.st_mode),
        )

    def stable_file_identity(metadata: os.stat_result) -> tuple[int, ...]:
        return (
            metadata.st_dev,
            metadata.st_ino,
            stat.S_IFMT(metadata.st_mode),
            stat.S_IMODE(metadata.st_mode),
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
        )

    def deterministic_os_error(error: OSError, label: str) -> None:
        if error.errno in {
            errno.ENOENT, errno.ENOTDIR, errno.ELOOP, errno.EISDIR,
        }:
            raise NativeEvidenceMismatch(label) from error
        raise NativeEvidenceUnavailable(
            "LW2 protected filesystem evidence is unavailable"
        ) from error

    def safe_component(value: str | bytes) -> str:
        if isinstance(value, bytes):
            try:
                name = value.decode("utf-8", errors="strict")
            except UnicodeDecodeError as error:
                raise NativeEvidenceMismatch(
                    "LW2 protected filesystem member name is not UTF-8"
                ) from error
        else:
            name = value
            try:
                name.encode("utf-8", errors="strict")
            except UnicodeEncodeError as error:
                raise NativeEvidenceMismatch(
                    "LW2 protected filesystem member name is not UTF-8"
                ) from error
        if not name or name in {".", ".."} or "/" in name or "\0" in name:
            raise NativeEvidenceMismatch(
                "LW2 protected filesystem member name is invalid"
            )
        return name

    def relative_parts(relative: str) -> tuple[str, ...]:
        path = PurePosixPath(relative)
        parts = tuple(safe_component(part) for part in path.parts)
        if path.is_absolute() or not parts or relative != "/".join(parts):
            raise NativeEvidenceMismatch(
                "LW2 protected filesystem path is invalid"
            )
        return parts

    def open_directory_at(parent: int, name: str, relative: str) -> int:
        try:
            descriptor = os.open(
                name,
                os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent,
            )
        except OSError as error:
            deterministic_os_error(
                error, "LW2 protected filesystem parent changed type"
            )
            raise AssertionError("unreachable")
        metadata = os.fstat(descriptor)
        if not stat.S_ISDIR(metadata.st_mode):
            os.close(descriptor)
            raise NativeEvidenceMismatch(
                "LW2 protected filesystem parent changed type"
            )
        identity = directory_identity(metadata)
        previous = directory_identities.setdefault(relative, identity)
        if previous != identity:
            os.close(descriptor)
            raise NativeEvidenceMismatch(
                "LW2 protected filesystem parent was replaced"
            )
        return descriptor

    def directory_for_parts(
        parts: tuple[str, ...], *, record: bool = True
    ) -> int:
        assert root_descriptor is not None
        current = os.dup(root_descriptor)
        traversed: list[str] = []
        try:
            for name in parts:
                traversed.append(name)
                relative = "/".join(traversed)
                next_descriptor = open_directory_at(current, name, relative)
                os.close(current)
                current = next_descriptor
            if not record:
                return current
            return current
        except Exception:
            os.close(current)
            raise

    def visit_at(
        parent: int,
        name: str,
        relative: str,
        *,
        directory_allowed: bool,
    ) -> None:
        descriptor: int | None = None
        try:
            metadata = os.stat(
                name, dir_fd=parent, follow_symlinks=False
            )
        except OSError as error:
            if error.errno == errno.ENOENT and relative in allowed_missing_exact_paths:
                return
            deterministic_os_error(
                error, "LW2 protected filesystem member is missing"
            )
            raise AssertionError("unreachable")
        try:
            if stat.S_ISLNK(metadata.st_mode):
                raise NativeEvidenceMismatch(
                    "LW2 protected filesystem contains a symlink"
                )
            if stat.S_ISDIR(metadata.st_mode):
                if not directory_allowed:
                    raise NativeEvidenceMismatch(
                        "LW2 protected exact path is not a regular file"
                    )
                descriptor = open_directory_at(parent, name, relative)
                opened = os.fstat(descriptor)
                if directory_identity(opened) != directory_identity(metadata):
                    raise NativeEvidenceMismatch(
                        "LW2 protected filesystem directory was replaced"
                    )
                records[relative] = {
                    "path": relative,
                    "type": "directory",
                    "mode": mode_text(opened),
                }
                with os.scandir(descriptor) as iterator:
                    children = sorted(
                        safe_component(entry.name) for entry in iterator
                    )
                if directory_identity(os.fstat(descriptor)) != directory_identity(opened):
                    raise NativeEvidenceMismatch(
                        "LW2 protected filesystem directory changed during scan"
                    )
                for child in children:
                    visit_at(
                        descriptor,
                        child,
                        f"{relative}/{child}",
                        directory_allowed=True,
                    )
                if directory_identity(os.fstat(descriptor)) != directory_identity(opened):
                    raise NativeEvidenceMismatch(
                        "LW2 protected filesystem directory changed during capture"
                    )
                return
            if not stat.S_ISREG(metadata.st_mode):
                raise NativeEvidenceMismatch(
                    "LW2 protected filesystem contains a non-regular member"
                )
            descriptor = os.open(
                name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent,
            )
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or stable_file_identity(opened) != stable_file_identity(metadata)
            ):
                raise NativeEvidenceMismatch(
                    "LW2 protected filesystem member was replaced"
                )
            with os.fdopen(descriptor, "rb", closefd=True) as handle:
                descriptor = None
                content = handle.read()
                final_metadata = os.fstat(handle.fileno())
            if stable_file_identity(final_metadata) != stable_file_identity(opened):
                raise NativeEvidenceMismatch(
                    "LW2 protected filesystem member changed during capture"
                )
            records[relative] = {
                "path": relative,
                "type": "regular",
                "mode": mode_text(opened),
                "byte_digest": _digest_bytes(content),
            }
        except NativeEvidenceMismatch:
            raise
        except OSError as error:
            deterministic_os_error(
                error, "LW2 protected filesystem member is missing"
            )
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def visit_path(relative: str, *, directory_allowed: bool) -> None:
        parts = relative_parts(relative)
        parent = directory_for_parts(parts[:-1])
        try:
            visit_at(
                parent, parts[-1], relative, directory_allowed=directory_allowed
            )
        finally:
            os.close(parent)

    try:
        root_descriptor = os.open(
            root,
            os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
        )
        if not stat.S_ISDIR(os.fstat(root_descriptor).st_mode):
            raise NativeEvidenceMismatch(
                "LW2 protected filesystem root is not a directory"
            )
        for relative in sorted(exact_paths):
            visit_path(relative, directory_allowed=False)
        for prefix in sorted(set(prefixes)):
            normalized = prefix.rstrip("/")
            parts = relative_parts(normalized)
            parent_parts, name_prefix = parts[:-1], parts[-1]
            parent_relative = "/".join(parent_parts)
            parent = directory_for_parts(parent_parts)
            try:
                with os.scandir(parent) as iterator:
                    matches = sorted(
                        safe_component(entry.name)
                        for entry in iterator
                        if safe_component(entry.name).startswith(name_prefix)
                    )
                if not matches:
                    raise NativeEvidenceMismatch(
                        "LW2 protected inventory prefix is empty"
                    )
                for name in matches:
                    relative = (
                        name if not parent_relative
                        else f"{parent_relative}/{name}"
                    )
                    visit_at(parent, name, relative, directory_allowed=True)
            finally:
                os.close(parent)
        for relative, expected in list(directory_identities.items()):
            descriptor = directory_for_parts(
                relative_parts(relative), record=False
            )
            try:
                if directory_identity(os.fstat(descriptor)) != expected:
                    raise NativeEvidenceMismatch(
                        "LW2 protected filesystem parent was replaced"
                    )
            finally:
                os.close(descriptor)
    except NativeEvidenceMismatch:
        raise
    except OSError as error:
        deterministic_os_error(
            error, "LW2 protected filesystem root is unavailable"
        )
    finally:
        if root_descriptor is not None:
            os.close(root_descriptor)
    ordered = [records[path] for path in sorted(records)]
    regular_scope = [
        record["path"] for record in ordered if record["type"] == "regular"
    ]
    return regular_scope, ordered


def capture_native_protected_snapshot(
    repo: Path,
    *,
    allowed_worktree_differences: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    """Bind protected native HEAD/index/worktree bytes and index flags.

    Admission recapture may bind an explicitly task-owned dirty path while the
    publication fence calls this with the default empty allowlist.  In both
    modes exceptional index flags remain forbidden and the exact worktree byte
    digest remains part of the snapshot.
    """

    from agent_governance_lw2_readmission import lw2_readmission_policy

    def git_bytes(*arguments: str) -> bytes:
        try:
            return _git(repo, *arguments)
        except (OSError, subprocess.CalledProcessError) as error:
            raise NativeEvidenceUnavailable(
                "LW2 protected Git evidence is unavailable"
            ) from error

    policy = lw2_readmission_policy()
    try:
        tree_entries: dict[str, tuple[str, str, str]] = {}
        for raw in git_bytes(
            "ls-tree", "-rz", "--full-tree", "HEAD"
        ).split(b"\0"):
            if not raw:
                continue
            metadata, raw_path = raw.split(b"\t", 1)
            fields = metadata.split(b" ")
            if len(fields) != 3:
                raise NativeEvidenceMismatch(
                    "LW2 protected HEAD entry is invalid"
                )
            mode, object_type, oid = (
                field.decode("ascii", errors="strict") for field in fields
            )
            path = raw_path.decode("utf-8", errors="strict")
            if path in tree_entries:
                raise NativeEvidenceMismatch(
                    "LW2 protected HEAD entry is duplicated"
                )
            tree_entries[path] = (mode, object_type, oid)
    except NativeEvidenceUnavailable:
        raise
    except (UnicodeDecodeError, ValueError) as error:
        raise NativeEvidenceMismatch(
            "LW2 protected inventory is invalid"
        ) from error
    exact_paths = set(policy["protected_scope_paths"])
    if not exact_paths.issubset(tree_entries):
        raise NativeEvidenceMismatch("LW2 protected inventory is incomplete")
    inventory = set(exact_paths)
    for prefix in policy["protected_scope_prefixes"]:
        matches = {path for path in tree_entries if path.startswith(prefix)}
        if not matches:
            raise NativeEvidenceMismatch(
                "LW2 protected inventory prefix is empty"
            )
        inventory.update(matches)
    scope = sorted(inventory)
    allowed = set(allowed_worktree_differences)
    filesystem_scope, filesystem_entries = _protected_filesystem_snapshot(
        repo,
        exact_paths=exact_paths,
        prefixes=policy["protected_scope_prefixes"],
        allowed_missing_exact_paths=allowed & exact_paths,
    )
    head_scope = set(scope)
    observed_scope = set(filesystem_scope)
    if (head_scope ^ observed_scope) - allowed:
        raise NativeEvidenceMismatch(
            "LW2 protected filesystem scope differs from native HEAD"
        )
    added_scope = observed_scope - head_scope
    if added_scope:
        try:
            native_untracked = {
                raw.decode("utf-8", errors="strict")
                for raw in git_bytes(
                    "ls-files", "--others", "--exclude-standard", "-z", "--"
                ).split(b"\0")
                if raw
            }
        except UnicodeDecodeError as error:
            raise NativeEvidenceMismatch(
                "LW2 native untracked evidence is invalid"
            ) from error
        if not added_scope.issubset(native_untracked):
            raise NativeEvidenceMismatch(
                "LW2 protected allowed addition is not visible as untracked"
            )
    index_scope = sorted(head_scope | observed_scope)

    def index_records(*arguments: str) -> list[bytes]:
        return [
            raw for raw in git_bytes("ls-files", *arguments, "--", *index_scope)
            .split(b"\0") if raw
        ]

    stage_by_path: dict[str, tuple[str, str, str]] = {}
    flags_by_path: dict[str, str] = {}
    try:
        for raw in index_records("--stage", "-z"):
            metadata, raw_path = raw.split(b"\t", 1)
            fields = metadata.split(b" ")
            if len(fields) != 3:
                raise NativeEvidenceMismatch(
                    "LW2 protected index stage entry is invalid"
                )
            mode, oid, stage = (
                field.decode("ascii", errors="strict") for field in fields
            )
            path = raw_path.decode("utf-8", errors="strict")
            if path in stage_by_path:
                raise NativeEvidenceMismatch(
                    "LW2 protected index stage entry is duplicated"
                )
            stage_by_path[path] = (mode, oid, stage)
        for raw in index_records("-v", "-z"):
            if len(raw) < 3 or raw[1:2] != b" ":
                raise NativeEvidenceMismatch(
                    "LW2 protected index flag entry is invalid"
                )
            tag = raw[:1].decode("ascii", errors="strict")
            path = raw[2:].decode("utf-8", errors="strict")
            if path in flags_by_path:
                raise NativeEvidenceMismatch(
                    "LW2 protected index flag entry is duplicated"
                )
            flags_by_path[path] = tag
    except NativeEvidenceUnavailable:
        raise
    except (UnicodeDecodeError, ValueError) as error:
        raise NativeEvidenceMismatch("LW2 protected index is invalid") from error
    if set(stage_by_path) != set(scope) or set(flags_by_path) != set(scope):
        raise NativeEvidenceMismatch(
            "LW2 protected index scope differs from native HEAD"
        )
    if any(path not in scope for path in allowed if path in tree_entries):
        raise NativeEvidenceMismatch(
            "LW2 protected worktree difference allowlist is invalid"
        )
    filesystem_by_path = {
        item["path"]: item
        for item in filesystem_entries
        if item["type"] == "regular"
    }
    entries: list[dict[str, str]] = []
    for relative in scope:
        mode, object_type, oid = tree_entries[relative]
        if (
            object_type != "blob"
            or mode not in {"100644", "100755"}
            or not HEAD_RE.fullmatch(oid)
        ):
            raise NativeEvidenceMismatch(
                "LW2 protected HEAD entry is not a regular blob"
            )
        if stage_by_path[relative] != (mode, oid, "0"):
            raise NativeEvidenceMismatch(
                "LW2 protected index differs from native HEAD"
            )
        if flags_by_path[relative] != "H":
            raise NativeEvidenceMismatch(
                "LW2 protected index contains exceptional flags"
            )
        head_bytes = git_bytes("cat-file", "blob", oid)
        if relative not in filesystem_by_path:
            if relative not in allowed:
                raise NativeEvidenceMismatch(
                    "LW2 protected worktree entry is missing"
                )
            entries.append({
                "path": relative,
                "mode": mode,
                "oid": oid,
                "byte_digest": _digest_bytes(head_bytes),
                "worktree_state": "deleted",
            })
            continue
        worktree = filesystem_by_path[relative]
        worktree_mode = str(worktree["mode"]).split(":", 1)[-1]
        if bool(int(worktree_mode, 8) & stat.S_IXUSR) != (mode == "100755"):
            raise NativeEvidenceMismatch(
                "LW2 protected worktree executable mode differs from HEAD"
            )
        worktree_digest = worktree["byte_digest"]
        if worktree_digest != _digest_bytes(head_bytes) and relative not in allowed:
            raise NativeEvidenceMismatch(
                "LW2 protected worktree bytes differ from native HEAD"
            )
        entries.append({
            "path": relative,
            "mode": mode,
            "oid": oid,
            "byte_digest": worktree_digest,
            "worktree_state": "present",
        })
    for relative in sorted(observed_scope - head_scope):
        worktree = filesystem_by_path[relative]
        entries.append({
            "path": relative,
            "mode": worktree["mode"],
            "oid": "ABSENT",
            "byte_digest": worktree["byte_digest"],
            "worktree_state": "added",
        })
    entries.sort(key=lambda item: item["path"])
    return {
        "scope": scope,
        "entries": entries,
        "filesystem_scope": filesystem_scope,
        "filesystem_entries": filesystem_entries,
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


def repository_generation_digest(
    record: dict[str, Any],
    *,
    native_protected_snapshot: dict[str, Any] | None = None,
) -> str:
    """Hash only Git/content generation fields, excluding observation time."""

    generation = {
        field: record.get(field)
        for field in (
            "scope", "source_head", "tracked_diff", "tracked_paths",
            "untracked", "changed_paths", "change_manifest_digest",
            "untracked_manifest_digest",
        )
    }
    if native_protected_snapshot is not None:
        generation["native_protected_snapshot"] = native_protected_snapshot
    return _digest_bytes(_canonical_bytes(generation))


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
        native_git_command(root, *arguments),
        check=True,
        capture_output=True,
        env=native_git_environment(),
        stdin=subprocess.DEVNULL,
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
        tracked = _git(
            repository,
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--binary",
            "HEAD",
            "--",
            *paths,
        )
        tracked_names = sorted(
            item.decode("utf-8", errors="strict")
            for item in _git(
                repository, "diff", "--no-ext-diff", "--no-textconv",
                "--name-only", "-z", "HEAD", "--", *paths,
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
