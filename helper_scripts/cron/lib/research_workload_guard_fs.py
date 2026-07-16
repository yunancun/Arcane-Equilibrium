"""Descriptor-bound filesystem operations for the research workload guard."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import secrets
import stat
import sys
from collections.abc import Callable, Sequence
from typing import Any


FAIL_CLOSED = 75
BeforeMissingCreate = Callable[[int, str], None]


def _top_level_resolved_components(path: str) -> list[str]:
    raw = os.path.normpath(path)
    if not os.path.isabs(raw) or raw == os.sep:
        raise OSError("private path must be an absolute non-root path")
    parts = raw.strip(os.sep).split(os.sep)
    first_path = os.path.join(os.sep, parts[0])
    try:
        before = os.lstat(first_path)
    except FileNotFoundError:
        return parts
    if not stat.S_ISLNK(before.st_mode):
        return parts
    if before.st_uid != 0:
        raise OSError("only a root-owned top-level compatibility symlink is allowed")
    target = os.readlink(first_path)
    after = os.lstat(first_path)
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_uid,
        before.st_mtime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_uid,
        after.st_mtime_ns,
    )
    if identity_before != identity_after or not stat.S_ISLNK(after.st_mode):
        raise OSError("top-level compatibility symlink changed during inspection")
    if not os.path.isabs(target):
        target = os.path.join(os.sep, target)
    resolved_prefix = os.path.normpath(target)
    if not os.path.isabs(resolved_prefix):
        raise OSError("compatibility symlink target is not absolute")
    prefix_parts = [part for part in resolved_prefix.strip(os.sep).split(os.sep) if part]
    return [*prefix_parts, *parts[1:]]


def _validate_directory(metadata: os.stat_result, *, final: bool) -> None:
    if not stat.S_ISDIR(metadata.st_mode):
        raise OSError("path component is not a directory")
    mode = stat.S_IMODE(metadata.st_mode)
    effective_uid = os.geteuid()
    if final:
        if metadata.st_uid != effective_uid or mode & 0o022:
            raise OSError("private leaf must be service-owned and not group/world writable")
        return
    shared_sticky_root = (
        metadata.st_uid == 0
        and bool(mode & stat.S_ISVTX)
        and bool(mode & 0o002)
        and not bool(mode & 0o020)
    )
    if metadata.st_uid not in {0, effective_uid}:
        raise OSError("ancestor has an untrusted owner")
    if mode & 0o022 and not shared_sticky_root:
        raise OSError("ancestor is writable by a lower-privilege identity")


def open_private_dir(
    path: str,
    *,
    create: bool,
    before_missing_create: BeforeMissingCreate | None = None,
) -> int:
    """Return a validated directory fd without following lexical symlinks."""

    components = _top_level_resolved_components(path)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    parent_fd = os.open(os.sep, flags)
    try:
        for index, component in enumerate(components):
            final = index == len(components) - 1
            try:
                os.stat(component, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                if not create:
                    raise
                if before_missing_create is not None:
                    before_missing_create(parent_fd, component)
                try:
                    os.mkdir(component, 0o700, dir_fd=parent_fd)
                except FileExistsError:
                    pass
            child_fd = os.open(component, flags | nofollow, dir_fd=parent_fd)
            try:
                _validate_directory(os.fstat(child_fd), final=final)
            except BaseException:
                os.close(child_fd)
                raise
            os.close(parent_fd)
            parent_fd = child_fd
        result = parent_fd
        parent_fd = -1
        return result
    finally:
        if parent_fd >= 0:
            os.close(parent_fd)


def prepare_private_dir(
    path: str, *, before_missing_create: BeforeMissingCreate | None = None
) -> None:
    fd = open_private_dir(
        path,
        create=True,
        before_missing_create=before_missing_create,
    )
    os.close(fd)


def _private_parent(path: str, *, create: bool) -> tuple[int, str]:
    raw = os.path.normpath(path)
    if not os.path.isabs(raw):
        raise OSError("file path must be absolute")
    name = os.path.basename(raw)
    if not name or name in {".", ".."}:
        raise OSError("file basename is invalid")
    return open_private_dir(os.path.dirname(raw), create=create), name


def _validate_private_file(metadata: os.stat_result) -> None:
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise OSError("private file ownership mode or link count is unsafe")


def prepare_private_file(path: str) -> None:
    parent_fd, name = _private_parent(path, create=True)
    try:
        flags = (
            os.O_RDWR
            | os.O_CREAT
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        fd = os.open(name, flags, 0o600, dir_fd=parent_fd)
        try:
            _validate_private_file(os.fstat(fd))
            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def load_private_json(path: str) -> dict[str, Any]:
    parent_fd, name = _private_parent(path, create=False)
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(name, flags, dir_fd=parent_fd)
        try:
            _validate_private_file(os.fstat(fd))
            with os.fdopen(fd, encoding="utf-8") as handle:
                fd = -1
                payload = json.load(handle)
        finally:
            if fd >= 0:
                os.close(fd)
    finally:
        os.close(parent_fd)
    if not isinstance(payload, dict):
        raise OSError("private JSON payload is not an object")
    return payload


def atomic_write_private_json(path: str, payload: dict[str, Any]) -> None:
    parent_fd, name = _private_parent(path, create=False)
    temporary = ""
    fd = -1
    try:
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        for _ in range(64):
            temporary = f".{name}.tmp.{secrets.token_hex(16)}"
            try:
                fd = os.open(temporary, flags, 0o600, dir_fd=parent_fd)
                break
            except FileExistsError:
                continue
        if fd < 0:
            raise OSError("cannot allocate exclusive private temporary file")
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
        os.replace(
            temporary,
            name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        temporary = ""
    finally:
        if fd >= 0:
            os.close(fd)
        if temporary:
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        os.close(parent_fd)


def _state_write(args: Sequence[str]) -> None:
    path, status, reason, rc, lane, token, source_head, scope_unit = args
    payload = {
        "schema_version": "research_workload_guard_state_v1",
        "ts_utc": datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "lane": lane,
        "token": token,
        "source_head": source_head,
        "scope_unit": scope_unit or None,
        "status": status,
        "reason": reason or None,
        "rc": int(rc),
    }
    atomic_write_private_json(path, payload)


def _owner_create(args: Sequence[str]) -> None:
    path, lane, source_head, pid, start, token, heartbeat_file, now = args
    parent_fd, name = _private_parent(path, create=False)
    try:
        try:
            os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise OSError("owner already exists")
    finally:
        os.close(parent_fd)
    atomic_write_private_json(
        path,
        {
            "schema_version": "research_job_owner_v1",
            "lane": lane,
            "source_head": source_head,
            "pid": int(pid),
            "proc_start_ticks": int(start),
            "token": token,
            "scope_unit": "none",
            "control_group": "none",
            "acquired_epoch": int(now),
            "heartbeat_epoch": int(now),
            "heartbeat_file": heartbeat_file,
            "progress_seq": 0,
            "stage": "ACQUIRED",
        },
    )


def _owner_heartbeat(args: Sequence[str]) -> None:
    path, token, now, seq, stage, scope, control_group = args
    payload = load_private_json(path)
    if payload.get("token") != token:
        raise OSError("owner token mismatch")
    existing_scope = payload.get("scope_unit", "none")
    existing_control_group = payload.get("control_group", "none")
    if not isinstance(existing_scope, str) or not isinstance(existing_control_group, str):
        raise OSError("owner scope pair has invalid types")
    if (existing_scope == "none") != (existing_control_group == "none"):
        raise OSError("owner scope pair is split")
    if (scope == "none") != (control_group == "none") and existing_scope == "none":
        raise OSError("new owner scope pair is split")
    if existing_scope != "none":
        if scope == "none":
            scope = existing_scope
        elif existing_scope != scope:
            raise OSError("owner scope changed")
        if control_group == "none":
            control_group = existing_control_group
        elif control_group != existing_control_group:
            raise OSError("owner control group changed")
    payload.update(
        heartbeat_epoch=int(now),
        progress_seq=max(int(seq), int(payload.get("progress_seq", 0)) + 1),
        stage=stage,
        scope_unit=scope,
        control_group=control_group,
    )
    atomic_write_private_json(path, payload)


def _owner_bind(args: Sequence[str]) -> None:
    path, token, unit, control_group, now = args
    payload = load_private_json(path)
    if payload.get("token") != token:
        raise OSError("owner token mismatch")
    existing_scope = payload.get("scope_unit", "none")
    existing_control_group = payload.get("control_group", "none")
    if not isinstance(existing_scope, str) or not isinstance(existing_control_group, str):
        raise OSError("owner scope pair has invalid types")
    if (existing_scope == "none") != (existing_control_group == "none"):
        raise OSError("owner scope pair is split")
    if existing_scope not in {"none", unit}:
        raise OSError("owner scope changed")
    if existing_control_group not in {"none", control_group}:
        raise OSError("owner control group changed")
    payload.update(
        scope_unit=unit,
        control_group=control_group,
        heartbeat_epoch=int(now),
        progress_seq=int(payload.get("progress_seq", 0)) + 1,
        stage="SCOPE_BOUND",
    )
    atomic_write_private_json(path, payload)


def _completion_write(args: Sequence[str]) -> None:
    out, lane, token, source_head, *paths = args
    if not paths:
        raise OSError("completion paths are empty")
    digests: dict[str, str] = {}
    for path in paths:
        with open(path, "rb") as handle:
            digests[path] = hashlib.sha256(handle.read()).hexdigest()
    atomic_write_private_json(
        out,
        {
            "schema_version": "research_workload_completion_v1",
            "ts_utc": datetime.datetime.now(datetime.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "lane": lane,
            "token": token,
            "source_head": source_head,
            "status": "COMPLETE",
            "completion_paths": list(paths),
            "sha256_by_path": digests,
        },
    )


def main(argv: Sequence[str]) -> int:
    if len(argv) < 2:
        return 64
    operation, args = argv[0], argv[1:]
    try:
        if operation == "prepare-dir" and len(args) == 1:
            prepare_private_dir(args[0])
        elif operation == "prepare-file" and len(args) == 1:
            prepare_private_file(args[0])
        elif operation == "state-write" and len(args) == 8:
            _state_write(args)
        elif operation == "owner-create" and len(args) == 8:
            _owner_create(args)
        elif operation == "owner-heartbeat" and len(args) == 7:
            _owner_heartbeat(args)
        elif operation == "owner-bind" and len(args) == 5:
            _owner_bind(args)
        elif operation == "completion-write" and len(args) >= 5:
            _completion_write(args)
        elif operation == "state-status" and len(args) == 1:
            print(load_private_json(args[0]).get("status") or "")
        else:
            return 64
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return FAIL_CLOSED
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
