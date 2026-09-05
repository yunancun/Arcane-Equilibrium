"""
MODULE_NOTE
模塊用途：從固定 repo config 與明確 supplied global config 收集有限 execution-surface 宣告。
主要函數：collect_local_execution_surface。
依賴：tomllib/tomli、既有 execution-surface probe builder 與 validator。
硬邊界：最多讀兩個 64 KiB regular UTF-8 TOML；不追 symlink、不掃 ambient home/env，
不接受 host verifier，也不把本地 bytes 提升為 host-selected truth。
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 production path
    import tomli as tomllib  # type: ignore[no-redef]

from agent_governance_execution_surface_probe import (
    REPO_ROOT,
    build_execution_surface_truth_report,
    execution_surface_probe_policy,
    validate_execution_surface_truth_report,
)


LOCAL_CONFIG_MAX_BYTES = 64 * 1024
LOCAL_CONFIG_MAX_PATH_COMPONENTS = 32
LOCAL_CONFIG_MAX_TOML_DEPTH = 32


class ExecutionSurfaceLocalCollectionError(ValueError):
    """本地 collector 的固定、secret-safe 拒絕；不攜帶 path、key、value 或 parser 原文。"""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


def _collection_error(error_code: str, message: str) -> None:
    raise ExecutionSurfaceLocalCollectionError(error_code, message)


def _canonical_digest(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _snapshot_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _absolute_parts(path: Path) -> tuple[str, ...]:
    if not path.is_absolute():
        _collection_error(
            "LOCAL_CONFIG_PATH_INVALID",
            "local config path is invalid",
        )
    parts = path.parts[1:]
    if (
        not parts
        or any(part in {"", ".", ".."} for part in parts)
        or len(parts) > LOCAL_CONFIG_MAX_PATH_COMPONENTS
    ):
        _collection_error(
            "LOCAL_CONFIG_PATH_INVALID",
            "local config path is invalid",
        )
    return parts


def _open_parent_without_symlinks(path: Path) -> tuple[int, str]:
    """從 filesystem root 逐層綁定 directory fd，拒絕任一 parent symlink。"""

    parts = _absolute_parts(path)
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    directory_fd = os.open("/", directory_flags)
    try:
        for component in parts[:-1]:
            try:
                inspected = os.stat(
                    component,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                _collection_error(
                    "LOCAL_CONFIG_MISSING",
                    "local config is missing",
                )
            except OSError:
                _collection_error("LOCAL_CONFIG_IO", "local config cannot be inspected")
            if stat.S_ISLNK(inspected.st_mode):
                _collection_error(
                    "LOCAL_CONFIG_SYMLINK",
                    "local config path must not contain a symlink",
                )
            if not stat.S_ISDIR(inspected.st_mode):
                _collection_error(
                    "LOCAL_CONFIG_NOT_REGULAR",
                    "local config path is not regular",
                )
            try:
                next_fd = os.open(component, directory_flags, dir_fd=directory_fd)
            except OSError as error:
                if error.errno in {errno.ELOOP, errno.ENOTDIR}:
                    _collection_error(
                        "LOCAL_CONFIG_SYMLINK",
                        "local config path must not contain a symlink",
                    )
                _collection_error("LOCAL_CONFIG_IO", "local config cannot be opened")
            if _snapshot_identity(os.fstat(next_fd))[:3] != _snapshot_identity(inspected)[:3]:
                os.close(next_fd)
                _collection_error(
                    "LOCAL_CONFIG_CHANGED",
                    "local config changed during bounded loading",
                )
            os.close(directory_fd)
            directory_fd = next_fd
        return directory_fd, parts[-1]
    except BaseException:
        os.close(directory_fd)
        raise


def _stat_regular_at(directory_fd: int, basename: str) -> os.stat_result:
    try:
        inspected = os.stat(
            basename,
            dir_fd=directory_fd,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        _collection_error("LOCAL_CONFIG_MISSING", "local config is missing")
    except OSError:
        _collection_error("LOCAL_CONFIG_IO", "local config cannot be inspected")
    if stat.S_ISLNK(inspected.st_mode):
        _collection_error(
            "LOCAL_CONFIG_SYMLINK",
            "local config path must not contain a symlink",
        )
    if not stat.S_ISREG(inspected.st_mode):
        _collection_error(
            "LOCAL_CONFIG_NOT_REGULAR",
            "local config path is not a regular file",
        )
    if inspected.st_size > LOCAL_CONFIG_MAX_BYTES:
        _collection_error(
            "LOCAL_CONFIG_TOO_LARGE",
            "local config exceeds the byte limit",
        )
    return inspected


def _open_regular_without_symlinks(path: Path) -> tuple[int, os.stat_result]:
    """以 root-anchored openat traversal 綁定每層 inode，避免 parent/final symlink race。"""

    directory_fd, basename = _open_parent_without_symlinks(path)
    file_flags = (
        os.O_RDONLY
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        inspected = _stat_regular_at(directory_fd, basename)
        try:
            descriptor = os.open(basename, file_flags, dir_fd=directory_fd)
        except OSError as error:
            if error.errno in {errno.ELOOP, errno.ENOTDIR}:
                _collection_error(
                    "LOCAL_CONFIG_SYMLINK",
                    "local config path must not contain a symlink",
                )
            _collection_error("LOCAL_CONFIG_IO", "local config cannot be opened")
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or _snapshot_identity(opened)[:3] != _snapshot_identity(inspected)[:3]
        ):
            os.close(descriptor)
            _collection_error(
                "LOCAL_CONFIG_CHANGED",
                "local config changed during bounded loading",
            )
        return descriptor, inspected
    finally:
        os.close(directory_fd)


def _restat_regular_without_symlinks(path: Path) -> os.stat_result:
    directory_fd, basename = _open_parent_without_symlinks(path)
    try:
        return _stat_regular_at(directory_fd, basename)
    finally:
        os.close(directory_fd)


def _read_bounded_config(path: Path) -> bytes:
    descriptor, initial = _open_regular_without_symlinks(path)
    try:
        chunks: list[bytes] = []
        remaining = LOCAL_CONFIG_MAX_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        final = os.fstat(descriptor)
    except OSError:
        _collection_error("LOCAL_CONFIG_IO", "local config cannot be read")
    finally:
        os.close(descriptor)
    if len(payload) > LOCAL_CONFIG_MAX_BYTES:
        _collection_error(
            "LOCAL_CONFIG_TOO_LARGE",
            "local config exceeds the byte limit",
        )
    try:
        rebound = _restat_regular_without_symlinks(path)
    except ExecutionSurfaceLocalCollectionError:
        # 為什麼 fail-closed：初讀後 pathname 消失或變成 symlink 都代表同一 snapshot 已失效。
        _collection_error(
            "LOCAL_CONFIG_CHANGED",
            "local config changed during bounded loading",
        )
    if not (
        _snapshot_identity(final)
        == _snapshot_identity(initial)
        == _snapshot_identity(rebound)
    ):
        _collection_error(
            "LOCAL_CONFIG_CHANGED",
            "local config changed during bounded loading",
        )
    return payload


def _check_toml_depth(value: Any, depth: int = 0) -> None:
    if depth > LOCAL_CONFIG_MAX_TOML_DEPTH:
        _collection_error(
            "LOCAL_CONFIG_TOO_DEEP",
            "local config nesting exceeds the depth limit",
        )
    if isinstance(value, dict):
        for nested in value.values():
            _check_toml_depth(nested, depth + 1)
    elif isinstance(value, list):
        for nested in value:
            _check_toml_depth(nested, depth + 1)


def _declaration_source(source_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    source = {
        "source_id": source_id,
        "source_kind": "config_declaration_v1",
        "payload": payload,
        "payload_sha256": _canonical_digest(payload),
    }
    source["source_sha256"] = _canonical_digest(source)
    return source


def _collect_one_source(
    source_id: str,
    path: Path,
    *,
    surface_profile_id: str,
    registry: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    status = {
        "source_id": source_id,
        "status": "rejected",
        "file_bytes_sha256": None,
        "error_code": None,
    }
    try:
        payload = _read_bounded_config(path)
    except ExecutionSurfaceLocalCollectionError as error:
        if error.error_code == "LOCAL_CONFIG_MISSING":
            status["status"] = "missing"
        else:
            status["error_code"] = error.error_code
        return status, None
    status["file_bytes_sha256"] = "sha256:" + hashlib.sha256(payload).hexdigest()
    if not payload.strip():
        status["status"] = "empty"
        return status, None
    try:
        decoded = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        status["error_code"] = "LOCAL_CONFIG_ENCODING"
        return status, None
    try:
        parsed = tomllib.loads(decoded)
        _check_toml_depth(parsed)
    except ExecutionSurfaceLocalCollectionError as error:
        status["error_code"] = error.error_code
        return status, None
    except (RecursionError, TypeError, ValueError, tomllib.TOMLDecodeError):
        status["error_code"] = "LOCAL_CONFIG_TOML"
        return status, None
    agents = parsed.get("agents")
    if agents is None:
        status["status"] = "no_data"
        return status, None
    if not isinstance(agents, dict):
        status["error_code"] = "LOCAL_CONFIG_SOURCE_POLICY"
        return status, None
    allowed = execution_surface_probe_policy()["config_key_allowlist"]
    values = []
    for qualified_key in allowed:
        local_key = qualified_key.removeprefix("agents.")
        if local_key in agents:
            values.append({"key": qualified_key, "value": agents[local_key]})
    # 未知 key 不外洩；沒有 allowlisted declaration 時以 no_data 明示。
    if not values:
        status["status"] = "no_data"
        return status, None
    try:
        # digest 也在 boundary 內：NaN/Inf/date 不能以 raw JSON error 逃出 collector。
        source = _declaration_source(source_id, {"values": values})
        # 既有 builder 是唯一 typed/policy authority；collector 不另建寬鬆 validator。
        build_execution_surface_truth_report(
            {
                "schema_version": "execution_surface_probe_request_v1",
                "surface_profile_id": surface_profile_id,
                "sources": [source],
            },
            registry,
        )
    except (TypeError, ValueError):
        status["error_code"] = "LOCAL_CONFIG_SOURCE_POLICY"
        return status, None
    status["status"] = "collected"
    return status, source


def collect_local_execution_surface(
    surface_profile_id: str,
    registry: dict[str, Any],
    *,
    root: Path = REPO_ROOT,
    global_config: Path | None = None,
) -> dict[str, Any]:
    """收集最多兩個明確 TOML source，並透過既有 probe 產生可 replay 的 UNVERIFIED report。

    `root/.codex/config.toml` 是唯一固定 repository source；global source 僅在 caller
    明確提供 `global_config` 時讀取。函數不接受 host verifier，也不讀環境變數或 home。
    """

    profiles = registry.get("execution_policy", {}).get("surface_profiles", {})
    if surface_profile_id not in profiles:
        _collection_error(
            "LOCAL_PROFILE_INVALID",
            "execution-surface profile is not Registry declared",
        )

    root_path = Path(root)
    if not root_path.is_absolute():
        _collection_error("LOCAL_CONFIG_PATH_INVALID", "local config path is invalid")
    requested_global = None
    if global_config is not None:
        requested_global = Path(global_config)
        if requested_global.name != "config.toml":
            _collection_error(
                "LOCAL_GLOBAL_CONFIG_ARGUMENT",
                "global config argument is invalid",
            )
        if not requested_global.is_absolute():
            requested_global = root_path / requested_global

    statuses: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    if requested_global is None:
        statuses.append(
            {
                "source_id": "global_config",
                "status": "not_requested",
                "file_bytes_sha256": None,
                "error_code": None,
            }
        )
    else:
        status, source = _collect_one_source(
            "global_config",
            requested_global,
            surface_profile_id=surface_profile_id,
            registry=registry,
        )
        statuses.append(status)
        if source is not None:
            sources.append(source)

    status, source = _collect_one_source(
        "repository_config",
        root_path / ".codex" / "config.toml",
        surface_profile_id=surface_profile_id,
        registry=registry,
    )
    statuses.append(status)
    if source is not None:
        sources.append(source)

    request = None
    report = None
    collection_status = "UNAVAILABLE"
    if sources:
        request = {
            "schema_version": "execution_surface_probe_request_v1",
            "surface_profile_id": surface_profile_id,
            "sources": sources,
        }
        report = build_execution_surface_truth_report(request, registry)
        if validate_execution_surface_truth_report(report, registry):
            _collection_error(
                "LOCAL_REPORT_INVALID",
                "local execution-surface report failed validation",
            )
        collection_status = report["report_status"]

    collection: dict[str, Any] = {
        "schema_version": "execution_surface_local_collection_v1",
        "collection_status": collection_status,
        "sources": statuses,
        "request": request,
        "report": report,
    }
    collection["collection_digest"] = _canonical_digest(collection)
    return collection
