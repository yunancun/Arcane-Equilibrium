"""Streaming, non-following repository generation summaries.

The command-capture Adapter needs before/after generation bindings, not a copy
of every dirty byte.  This producer therefore hashes staged/unstaged Git diff
streams and untracked filesystem objects without retaining or base64-encoding
their contents.  Untracked symlinks are lstat/readlink records and are never
followed.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO, Iterator


HEAD_RE_LENGTH = 40
STREAM_CHUNK = 128 * 1024
SENSITIVE_PARTS = {
    ".git", ".ssh", ".aws", ".gnupg", ".netrc", ".env", "credentials",
    "credentials.json", "id_rsa", "id_ed25519",
}
SUMMARY_FIELDS = {
    "schema_version", "scope", "source_head", "generation_digest",
    "observed_at", "record_digest",
}


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


def _git_root(root: Path) -> Path:
    repository = root.resolve(strict=True)
    if not repository.is_dir():
        raise ValueError("repository root must be a directory")
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], cwd=repository,
            check=True, capture_output=True,
        )
        top = Path(result.stdout.decode("utf-8", errors="strict").strip()).resolve(
            strict=True
        )
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        raise ValueError(f"cannot resolve Git repository root: {error}") from error
    if top != repository:
        raise ValueError("capture root must be the exact Git repository root")
    return repository


def _safe_scope(value: Any, root: Path) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("repository scope paths must be non-empty canonical strings")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("repository scope paths cannot contain control characters")
    if value.startswith(("~", ":")) or "\\" in value or any(
        mark in value for mark in "*?["
    ):
        raise ValueError("repository scope path is unsafe")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("repository scope path escapes the repository")
    normalized = path.as_posix()
    if normalized != "." and normalized.startswith("./"):
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
        try:
            metadata = os.lstat(cursor)
        except FileNotFoundError:
            break
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError("repository scope path may not traverse a symlink")
    return normalized


def _normalize_scope(scope: Any, root: Path) -> list[str]:
    if not isinstance(scope, (list, tuple)) or not scope:
        raise ValueError("repository scope must be a non-empty path list")
    normalized = [_safe_scope(value, root) for value in scope]
    if len(normalized) != len(set(normalized)):
        raise ValueError("repository scope paths must be unique")
    return sorted(normalized)


def _git_output(repository: Path, *arguments: str) -> bytes:
    try:
        return subprocess.run(
            ["git", *arguments], cwd=repository, check=True, capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError(f"cannot capture repository generation: {error}") from error


def _stream_digest(handle: BinaryIO) -> dict[str, Any]:
    digest = hashlib.sha256()
    total = 0
    while True:
        chunk = handle.read(STREAM_CHUNK)
        if not chunk:
            break
        digest.update(chunk)
        total += len(chunk)
    return {"bytes": total, "digest": "sha256:" + digest.hexdigest()}


def _git_stream_digest(repository: Path, arguments: list[str]) -> dict[str, Any]:
    try:
        process = subprocess.Popen(
            ["git", *arguments], cwd=repository, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    except OSError as error:
        raise ValueError(f"cannot start Git generation capture: {error}") from error
    assert process.stdout is not None
    summary = _stream_digest(process.stdout)
    stderr = process.stderr.read() if process.stderr is not None else b""
    exit_code = process.wait()
    if exit_code != 0:
        detail = stderr.decode("utf-8", errors="replace")[:500]
        raise ValueError(f"Git generation capture failed ({exit_code}): {detail}")
    return summary


def _git_paths(repository: Path, arguments: list[str]) -> Iterator[str]:
    raw = _git_output(repository, *arguments)
    for item in raw.split(b"\0"):
        if not item:
            continue
        try:
            yield item.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise ValueError("Git path is not canonical UTF-8") from error


def _safe_untracked_path(path: str, repository: Path) -> Path:
    if not path or path != Path(path).as_posix() or Path(path).is_absolute():
        raise ValueError("Git returned a non-canonical untracked path")
    if ".." in Path(path).parts or any(
        ord(character) < 32 or ord(character) == 127 for character in path
    ):
        raise ValueError("Git returned an unsafe untracked path")
    if SENSITIVE_PARTS.intersection(part.casefold() for part in Path(path).parts):
        raise ValueError("Git returned a sensitive untracked path")
    cursor = repository
    parts = Path(path).parts
    for part in parts[:-1]:
        cursor = cursor / part
        metadata = os.lstat(cursor)
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError("untracked path traverses a symlink")
        if not stat.S_ISDIR(metadata.st_mode):
            raise ValueError("untracked path parent is not a directory")
    return repository.joinpath(*parts)


def _metadata(metadata: os.stat_result) -> dict[str, int]:
    return {
        "mode": metadata.st_mode,
        "size": metadata.st_size,
        "mtime_ns": metadata.st_mtime_ns,
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
        "uid": metadata.st_uid,
        "gid": metadata.st_gid,
    }


def _regular_file_record(path: str, candidate: Path) -> dict[str, Any]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(candidate, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("untracked capture target is not a regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            content = _stream_digest(handle)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if _metadata(before) != _metadata(after) or content["bytes"] != before.st_size:
        raise ValueError("untracked regular file changed during generation capture")
    return {
        "path": path, "kind": "regular", "lstat": _metadata(before),
        "content": content,
    }


def _symlink_record(path: str, candidate: Path, before: os.stat_result) -> dict[str, Any]:
    target = os.readlink(candidate)
    after = os.lstat(candidate)
    if _metadata(before) != _metadata(after) or not stat.S_ISLNK(after.st_mode):
        raise ValueError("untracked symlink changed during generation capture")
    return {
        "path": path, "kind": "symlink", "lstat": _metadata(before),
        "readlink_target": target,
    }


def _untracked_manifest(repository: Path, paths: list[str]) -> dict[str, Any]:
    digest = hashlib.sha256()
    count = 0
    for path in _git_paths(
        repository,
        ["ls-files", "--others", "--exclude-standard", "-z", "--", *paths],
    ):
        candidate = _safe_untracked_path(path, repository)
        metadata = os.lstat(candidate)
        if stat.S_ISLNK(metadata.st_mode):
            record = _symlink_record(path, candidate, metadata)
        elif stat.S_ISREG(metadata.st_mode):
            record = _regular_file_record(path, candidate)
        else:
            raise ValueError("untracked capture target is neither regular file nor symlink")
        encoded = _canonical_bytes(record)
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        count += 1
    return {"objects": count, "digest": "sha256:" + digest.hexdigest()}


def capture_generation_summary(scope: Any, *, root: Path) -> dict[str, Any]:
    """Return a compact content/metadata binding without following symlinks."""

    repository = _git_root(Path(root))
    paths = _normalize_scope(scope, repository)
    try:
        source_head = _git_output(repository, "rev-parse", "HEAD").decode(
            "ascii", errors="strict"
        ).strip().lower()
    except UnicodeDecodeError as error:
        raise ValueError("Git source_head is not ASCII") from error
    if len(source_head) != HEAD_RE_LENGTH or any(
        character not in "0123456789abcdef" for character in source_head
    ):
        raise ValueError("captured Git source_head is not exact 40-hex")
    components = {
        "schema_version": "repository_generation_stream_v1",
        "scope": paths,
        "source_head": source_head,
        "index_diff": _git_stream_digest(
            repository,
            ["diff", "--no-ext-diff", "--binary", "--cached", "HEAD", "--", *paths],
        ),
        "worktree_diff": _git_stream_digest(
            repository,
            ["diff", "--no-ext-diff", "--binary", "--", *paths],
        ),
        "untracked": _untracked_manifest(repository, paths),
    }
    summary: dict[str, Any] = {
        "schema_version": "repository_generation_summary_v1",
        "scope": paths,
        "source_head": source_head,
        "generation_digest": _digest_bytes(_canonical_bytes(components)),
        "observed_at": _now(),
    }
    summary["record_digest"] = _self_digest(summary)
    return summary


def validate_generation_summary_shape(
    summary: Any, *, expected_scope: list[str], self_digest: Any,
) -> list[str]:
    """Small shape helper; freshness/currentness is checked by the caller."""

    if not isinstance(summary, dict):
        return ["generation summary must be an object"]
    errors: list[str] = []
    if set(summary) != SUMMARY_FIELDS:
        errors.append("generation summary fields are invalid")
    if summary.get("schema_version") != "repository_generation_summary_v1":
        errors.append("generation summary schema_version is invalid")
    if summary.get("scope") != sorted(expected_scope):
        errors.append("generation summary scope is invalid")
    if summary.get("record_digest") != self_digest(summary):
        errors.append("generation summary self-digest is invalid")
    return errors
