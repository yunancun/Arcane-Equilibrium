"""Fail-closed committed-source binding for the governed pytest public entry."""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

from agent_governance_pytest_provider import (
    GOVERNED_PYTEST_PREFIX, GOVERNED_PYTEST_REQUIRED_ARGS,
)


GIT_SEARCH_PATH = ("/usr/bin", "/bin", "/usr/local/bin", "/opt/homebrew/bin")
ALLOWED_MODES = {"100644", "100755", "120000"}


def _is_pytest_argv(argv: list[str]) -> bool:
    return (
        tuple(argv[:4]) == GOVERNED_PYTEST_PREFIX
        or argv[:3] in (["python", "-m", "pytest"], ["python3", "-m", "pytest"])
        or (argv and argv[0].lower() == "pytest")
    )


def _is_governed_pytest_argv(argv: list[str]) -> bool:
    required_end = 4 + len(GOVERNED_PYTEST_REQUIRED_ARGS)
    return (
        tuple(argv[:4]) == GOVERNED_PYTEST_PREFIX
        and tuple(argv[4:required_end]) == GOVERNED_PYTEST_REQUIRED_ARGS
    )


def _pytest_collection_target_errors(argv: list[str]) -> list[str]:
    if not _is_governed_pytest_argv(argv):
        return []
    required_end = 4 + len(GOVERNED_PYTEST_REQUIRED_ARGS)
    for argument in argv[required_end:]:
        if argument.startswith("-"):
            continue
        target = argument.split("::", 1)[0]
        if PurePosixPath(target).is_absolute():
            return [
                "governed pytest absolute pytest collection target is forbidden"
            ]
    return []


def _git_executable() -> str:
    for directory in GIT_SEARCH_PATH:
        candidate = Path(directory) / "git"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return "/usr/bin/git"


def _git_environment() -> dict[str, str]:
    environment = {
        "PATH": os.pathsep.join(GIT_SEARCH_PATH),
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_LITERAL_PATHSPECS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
    }
    if "TZ" in os.environ:
        environment["TZ"] = os.environ["TZ"]
    return environment


def _git(repository: Path, *arguments: str) -> bytes:
    try:
        return subprocess.run(
            [_git_executable(), "-C", str(repository), *arguments],
            cwd=repository,
            check=True,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            env=_git_environment(),
            timeout=60,
        ).stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError(f"cannot verify committed pytest subject: {error}") from error


def _safe_path(value: Any, repository: Path) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("pytest subject paths must be non-empty canonical strings")
    if (
        value.startswith(("~", ":"))
        or "\\" in value
        or any(mark in value for mark in "*?[")
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError("pytest subject path is unsafe")
    relative = PurePosixPath(value)
    if relative.is_absolute() or any(part in {"", ".."} for part in relative.parts):
        raise ValueError("pytest subject path escapes the repository")
    normalized = relative.as_posix()
    if normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized in {"", ".."} or any(
        part.casefold() == ".git" for part in PurePosixPath(normalized).parts
    ):
        raise ValueError("pytest subject path targets Git metadata")
    cursor = repository
    for part in PurePosixPath(normalized).parts:
        cursor = cursor / part
        try:
            metadata = os.lstat(cursor)
        except FileNotFoundError:
            break
        if stat.S_ISLNK(metadata.st_mode):
            # A final committed symlink is checked as a blob below.  No scope
            # path may traverse through one to reach another object.
            if part != PurePosixPath(normalized).parts[-1]:
                raise ValueError("pytest subject path traverses a symlink")
            break
    return normalized


def pytest_subject_scope(
    task_contract: dict[str, Any], path_scope: list[str], *, root: Path,
) -> list[str]:
    """Return the literal dirty/verification union without changing record scope."""

    dirty_scope = task_contract.get("dirty_scope")
    if not isinstance(dirty_scope, list) or not isinstance(path_scope, list):
        raise ValueError("pytest subject scopes are not canonical path lists")
    combined = [
        _safe_path(path, root) for path in [*dirty_scope, *path_scope]
    ]
    if not combined:
        raise ValueError("pytest subject scope is empty")
    return sorted(set(combined))


def _decode_path(raw: bytes) -> str:
    try:
        path = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError("Git returned a non-UTF-8 pytest subject path") from error
    if not path or path != PurePosixPath(path).as_posix() or "\x00" in path:
        raise ValueError("Git returned a non-canonical pytest subject path")
    return path


def _head_manifest(
    repository: Path, source_head: str, scope: list[str],
) -> dict[str, tuple[str, str]]:
    raw = _git(
        repository, "--no-replace-objects", "ls-tree", "-rz", "--full-tree",
        source_head, "--", *scope,
    )
    manifest: dict[str, tuple[str, str]] = {}
    for item in raw.split(b"\0"):
        if not item:
            continue
        try:
            metadata, raw_path = item.split(b"\t", 1)
            mode, object_type, object_id = metadata.decode("ascii").split()
        except (UnicodeDecodeError, ValueError) as error:
            raise ValueError("committed pytest subject tree entry is invalid") from error
        path = _decode_path(raw_path)
        if (
            mode not in ALLOWED_MODES
            or object_type != "blob"
            or len(object_id) != 40
            or any(character not in "0123456789abcdef" for character in object_id)
            or path in manifest
        ):
            raise ValueError("committed pytest subject tree entry is unsupported")
        manifest[path] = (mode, object_id)
    return manifest


def _index_manifest(
    repository: Path, scope: list[str],
) -> dict[str, tuple[str, str]]:
    raw = _git(
        repository, "--no-replace-objects", "ls-files", "--stage", "-z",
        "--", *scope,
    )
    manifest: dict[str, tuple[str, str]] = {}
    for item in raw.split(b"\0"):
        if not item:
            continue
        try:
            metadata, raw_path = item.split(b"\t", 1)
            mode, object_id, stage = metadata.decode("ascii").split()
        except (UnicodeDecodeError, ValueError) as error:
            raise ValueError("pytest subject index entry is invalid") from error
        path = _decode_path(raw_path)
        if (
            mode not in ALLOWED_MODES
            or stage != "0"
            or len(object_id) != 40
            or any(character not in "0123456789abcdef" for character in object_id)
            or path in manifest
        ):
            raise ValueError("pytest subject index mode or stage is unsupported")
        manifest[path] = (mode, object_id)
    return manifest


def _git_blob_id(payload: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(payload)).encode("ascii") + b"\x00" + payload
    ).hexdigest()


def _regular_blob(path: Path) -> tuple[os.stat_result, str]:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError("pytest subject is not one regular file")
        digest = hashlib.sha1()
        digest.update(b"blob " + str(before.st_size).encode("ascii") + b"\x00")
        read_bytes = 0
        while True:
            chunk = os.read(descriptor, 128 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            read_bytes += len(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    stable_fields = ("st_mode", "st_size", "st_mtime_ns", "st_dev", "st_ino")
    if (
        any(getattr(before, field) != getattr(after, field) for field in stable_fields)
        or read_bytes != before.st_size
    ):
        raise ValueError("pytest subject changed while its bytes were verified")
    return before, digest.hexdigest()


def _worktree_entry(repository: Path, path: str) -> tuple[str, str]:
    parts = PurePosixPath(path).parts
    parent = repository
    for part in parts[:-1]:
        parent = parent / part
        try:
            parent_metadata = os.lstat(parent)
        except FileNotFoundError as error:
            raise ValueError(
                f"pytest subject parent is absent from worktree: {path}"
            ) from error
        if stat.S_ISLNK(parent_metadata.st_mode):
            raise ValueError("pytest subject path traverses a symlink")
        if not stat.S_ISDIR(parent_metadata.st_mode):
            raise ValueError("pytest subject parent is not a directory")
    candidate = repository.joinpath(*parts)
    try:
        metadata = os.lstat(candidate)
    except FileNotFoundError as error:
        raise ValueError(f"pytest subject is absent from worktree: {path}") from error
    if stat.S_ISLNK(metadata.st_mode):
        target = os.fsencode(os.readlink(candidate))
        after = os.lstat(candidate)
        if (
            not stat.S_ISLNK(after.st_mode)
            or metadata.st_ino != after.st_ino
            or metadata.st_mtime_ns != after.st_mtime_ns
            or metadata.st_size != after.st_size
        ):
            raise ValueError("pytest subject symlink changed while verified")
        return "120000", _git_blob_id(target)
    metadata, object_id = _regular_blob(candidate)
    mode = "100755" if metadata.st_mode & 0o111 else "100644"
    return mode, object_id


def _untracked_paths(repository: Path, scope: list[str]) -> set[str]:
    paths: set[str] = set()
    commands = (
        ("ls-files", "--others", "--exclude-standard", "-z", "--", *scope),
        (
            "ls-files", "--others", "--ignored", "--exclude-standard", "-z",
            "--", *scope,
        ),
    )
    for arguments in commands:
        for raw_path in _git(repository, "--no-replace-objects", *arguments).split(b"\0"):
            if raw_path:
                paths.add(_decode_path(raw_path))
    return paths


def require_committed_pytest_subject(
    repository: Path, *, source_head: str, scope: list[str],
) -> None:
    """Require exact HEAD/index/worktree equality for every admitted subject path."""

    root = repository.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("pytest subject repository root is not a directory")
    try:
        top = Path(
            _git(root, "rev-parse", "--show-toplevel").decode("utf-8").strip()
        ).resolve(strict=True)
        current_head = _git(
            root, "--no-replace-objects", "rev-parse", "--verify", "HEAD^{commit}",
        ).decode("ascii").strip().lower()
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError("cannot resolve committed pytest subject identity") from error
    if top != root:
        raise ValueError("pytest subject root is not the exact Git repository root")
    if (
        len(source_head) != 40
        or any(character not in "0123456789abcdef" for character in source_head)
        or current_head != source_head
    ):
        raise ValueError("pytest subject HEAD differs from captured source head")
    normalized = sorted({_safe_path(path, root) for path in scope})
    if not normalized:
        raise ValueError("pytest subject scope is empty")

    head = _head_manifest(root, source_head, normalized)
    index = _index_manifest(root, normalized)
    if index != head:
        raise ValueError("pytest subject index differs from committed checkpoint")
    extras = _untracked_paths(root, normalized)
    if extras:
        raise ValueError("pytest subject has uncommitted paths")
    for path, expected in head.items():
        if _worktree_entry(root, path) != expected:
            raise ValueError(
                f"pytest subject worktree differs from committed checkpoint: {path}"
            )


def require_capture_subject(
    repository: Path, source_head: str, task_contract: dict[str, Any],
    path_scope: list[str],
) -> None:
    """Reject a mismatched subject before the capture provider executes."""
    try:
        subject_scope = pytest_subject_scope(
            task_contract, path_scope, root=repository,
        )
        require_committed_pytest_subject(
            repository,
            source_head=source_head,
            scope=subject_scope,
        )
    except (OSError, ValueError) as error:
        raise PermissionError(
            "governed pytest requires admitted subject bytes to match the "
            "committed checkpoint before execution; create the approved "
            "local committed checkpoint, compile a fresh Context artifact, "
            "and retry the canonical agent_governance.py capture-command "
            f"entry: {error}"
        ) from None


def validate_replay_subject(
    root: Path, record: dict[str, Any], expected_subject_scope: list[str] | None,
) -> list[str]:
    """Validate the trusted replay scope independently of caller record scope."""
    path_scope = record["path_scope"]
    if expected_subject_scope is None:
        return [
            "governed pytest trusted replay requires admitted pytest "
            "subject scope"
        ]
    try:
        subject_scope = pytest_subject_scope(
            {"dirty_scope": expected_subject_scope}, [], root=root,
        )
    except (OSError, ValueError) as error:
        return [
            "governed pytest trusted replay admitted pytest subject scope "
            f"is invalid: {error}"
        ]
    if subject_scope != expected_subject_scope or not set(path_scope).issubset(
        subject_scope
    ):
        return [
            "governed pytest trusted replay admitted pytest subject scope "
            "is not the canonical verification-inclusive union"
        ]
    try:
        require_committed_pytest_subject(
            root,
            source_head=record["whole_repository_before"]["source_head"],
            scope=subject_scope,
        )
    except (OSError, ValueError) as error:
        return [
            "governed pytest trusted replay admitted pytest subject differs "
            f"from committed checkpoint: {error}"
        ]
    return []
