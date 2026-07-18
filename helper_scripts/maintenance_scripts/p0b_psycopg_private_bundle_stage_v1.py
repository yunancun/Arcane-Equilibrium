#!/usr/bin/python3
"""Stage one exact psycopg runtime bundle into a private immutable-by-contract tree.

The default mode is a zero-effect preflight.  ``--apply`` performs one atomic
directory publication after every source byte is hash-checked.  The adapter has
no service, database, broker, credential, or subprocess surface.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, Mapping


SCHEMA = "p0b_psycopg_private_bundle_stage_v1"
SOURCE_ROOT = Path("/home/ncyu/.local/lib/python3.12/site-packages")
DESTINATION_PARENT = Path("/home/ncyu/BybitOpenClaw/var/openclaw")
DESTINATION_NAME = "p0b-observer-deps"
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
HEX64 = frozenset("0123456789abcdef")
RENAME_NOREPLACE = 1

PRODUCTION_DIRECTORY_CHAINS: dict[str, tuple[tuple[str, int, int, int], ...]] = {
    str(SOURCE_ROOT): (
        ("home", 0, 0, 0o755),
        ("ncyu", 1000, 1000, 0o750),
        (".local", 1000, 1000, 0o700),
        ("lib", 1000, 1000, 0o775),
        ("python3.12", 1000, 1000, 0o775),
        ("site-packages", 1000, 1000, 0o775),
    ),
    str(DESTINATION_PARENT): (
        ("home", 0, 0, 0o755),
        ("ncyu", 1000, 1000, 0o750),
        ("BybitOpenClaw", 1000, 1000, 0o755),
        ("var", 1000, 1000, 0o755),
        ("openclaw", 1000, 1000, 0o700),
    ),
}

SEALED_MANIFEST: dict[str, dict[str, str]] = {
    "psycopg2": {
        "__init__.py": "f66a3941dd2e587884071d82768806a2cda436ab6534d1b36ed625182d21592f",
        "_ipaddress.py": "8e4bb284b82a50644170b3560ccf10272b15eaad4da5cfd1607e3f904ec964f5",
        "_json.py": "5cf9f83e7cdb4e0d4372acfb9f524cbf974a841e55155ebcdf8184b7149ac2dd",
        "_psycopg.cpython-312-x86_64-linux-gnu.so": "df93d0caf76c1c457f400b1e3c73e46c3e444432c89a68f223b19bbd90562187",
        "_range.py": "b1779e9c6ada244130d88de673c46598d8afcb68cc83bcd6a1a9c37acd98c29f",
        "errorcodes.py": "f0113f6403fb6e1b0848ac8b3f4824ad683f34d8f5ba3dfb751df9e840deeb2a",
        "errors.py": "6804b8749c938356ec0f3243091400301fecef3bfe438c81e98be2876e88fb43",
        "extensions.py": "086d241b9bcbf0eb79d375069435d724915d1562e0e07136fdcd7e94b38b73c3",
        "extras.py": "a017eb76fb569fc213c5cdf1fa1da1e88c0752c59d56a09d7f81a985bd09a98f",
        "pool.py": "50612df0874fdf135cd8f1983651b8b10be0f2785fe1a7829f3dfd8534741fc2",
        "sql.py": "39c144026a5ed9a31faf1d0c124e0bc74d17bd75c90a6be595a3956c963eca81",
        "tz.py": "afde642bb7864a9398aff96e0b262cce71ccce3979dac2e3b2748f5e45cbcd12",
    },
    "psycopg2_binary.libs": {
        "libcom_err-2abe824b.so.2.1": "5426dcb54dd01c9eedda05e2179f0e47114e8b48a534ffe9e94916e79471b257",
        "libcrypt-13f4f5d0.so.1": "a74d1e8438d224e0fff14da0001f5e50129b0d666a103bf981b976770158d106",
        "libcrypto-88208852.so.3": "2fd37154b19333c0bee46ff24aaafab5c38f0b9aff4bedc107753b67f3161c80",
        "libgssapi_krb5-497db0c6.so.2.2": "2a74b0330ee973281b26f8ebe4acef0ebf9ee99c6b68497cf9151fff6c4c34e1",
        "libk5crypto-b1f99d5c.so.3.1": "9844e5009e70a6ad2fb22b587306810fe2a7b1b9f6b9922daa1c78ba3466de27",
        "libkeyutils-dfe70bd6.so.1.5": "c29e41b03cf4b2dffbfb4960946e2b42f82c0ca5d53d231d3f0fc597ba274488",
        "libkrb5-fcafa220.so.3.3": "b2aab528ff4cab2144e5ce01b246ac09f574a072a53ff63ea81d6bb29b26b8f1",
        "libkrb5support-d0bcff84.so.0.1": "6a71f57d748fef79b4e736d5348875545d0a224fa8928b5d62a3cf2647fc109f",
        "liblber-314cbfbf.so.2.0.200": "fdba45538f1d793a9902797c5f888b39e7a5e8b7bf5fe0447e01ab7f487c1bc7",
        "libldap-331dad9d.so.2.0.200": "c56191deb6b726bf408634f46522ea4e829087b85bba619ae250718d6ed9ffc6",
        "libpcre-9513aab5.so.1.2.0": "02eda850e04931656d8af81f5171bff74d8bec1553d3d85c3d32d7fc5efe8864",
        "libpq-f521cc7d.so.5.17": "c2870f74ba59a43550b515eb7044ec35e66d77674f65c7d784c2247966e1893f",
        "libsasl2-84219a89.so.3.0.0": "ae3f8967d5fa191dac7c6ae5f9130f659cf2f5cb66b2f7e5c5a1a5a47369fe5a",
        "libselinux-0922c95c.so.1": "d4fa8e7fb3add960a68325a59c9694244aea3213fd739a50815cb067c4965654",
        "libssl-fe1b61af.so.3": "2db83e4f393066674c90ebfdec7367ce707020931754a4bab2995d2ada377c43",
    },
}


class StageError(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _valid_hash(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and set(value).issubset(HEX64)
    )


def _validate_manifest(manifest: Mapping[str, Mapping[str, str]]) -> None:
    if set(manifest) != {"psycopg2", "psycopg2_binary.libs"}:
        raise StageError("manifest_directory_set_invalid")
    for directory, entries in manifest.items():
        if not isinstance(entries, Mapping) or not entries:
            raise StageError("manifest_entries_invalid")
        for name, digest in entries.items():
            if (
                not isinstance(name, str)
                or not name
                or name in {".", ".."}
                or "/" in name
                or "\x00" in name
                or not _valid_hash(digest)
            ):
                raise StageError("manifest_entry_invalid")
        if directory == "psycopg2" and not any(
            name.startswith("_psycopg.") and name.endswith(".so")
            for name in entries
        ):
            raise StageError("manifest_extension_missing")


def canonical_manifest_sha256(manifest: Mapping[str, Mapping[str, str]]) -> str:
    _validate_manifest(manifest)
    raw = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _open_production_directory(path: Path) -> tuple[int, os.stat_result]:
    expected = PRODUCTION_DIRECTORY_CHAINS.get(str(path))
    if expected is None or not path.is_absolute():
        raise StageError("production_directory_not_sealed")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open("/", flags)
    try:
        root = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(root.st_mode)
            or root.st_uid != 0
            or root.st_gid != 0
            or stat.S_IMODE(root.st_mode) != 0o755
        ):
            raise StageError("production_root_identity_invalid")
        for name, uid, gid, mode in expected:
            child = os.open(name, flags, dir_fd=descriptor)
            opened = os.fstat(child)
            if (
                not stat.S_ISDIR(opened.st_mode)
                or opened.st_uid != uid
                or opened.st_gid != gid
                or stat.S_IMODE(opened.st_mode) != mode
            ):
                os.close(child)
                raise StageError("production_directory_chain_invalid")
            os.close(descriptor)
            descriptor = child
        return descriptor, os.fstat(descriptor)
    except Exception:
        os.close(descriptor)
        raise


def _open_directory(
    path: Path,
    *,
    private: bool,
    strict_chain: bool = False,
) -> tuple[int, os.stat_result]:
    if strict_chain:
        descriptor, opened = _open_production_directory(path)
        if private and stat.S_IMODE(opened.st_mode) != 0o700:
            os.close(descriptor)
            raise StageError("directory_identity_invalid")
        return descriptor, opened
    try:
        before = path.lstat()
    except OSError as exc:
        raise StageError("directory_unavailable") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
        raise StageError("directory_identity_invalid")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise StageError("directory_open_failed") from exc
    opened = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        or opened.st_uid != os.getuid()
        or opened.st_gid != os.getgid()
        or (private and stat.S_IMODE(opened.st_mode) != 0o700)
    ):
        os.close(descriptor)
        raise StageError("directory_identity_invalid")
    return descriptor, opened


def _open_child_directory(parent_fd: int, name: str, *, private: bool) -> int:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise StageError("source_directory_invalid") from exc
    opened = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or opened.st_uid != os.getuid()
        or opened.st_gid != os.getgid()
        or (private and stat.S_IMODE(opened.st_mode) != 0o700)
    ):
        os.close(descriptor)
        raise StageError("source_directory_invalid")
    return descriptor


def _read_regular_at(directory_fd: int, name: str) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except OSError as exc:
        raise StageError("source_file_open_failed") from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_uid != os.getuid()
            or opened.st_gid != os.getgid()
            or opened.st_size > MAX_FILE_BYTES
        ):
            raise StageError("source_file_identity_invalid")
        chunks: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        final = os.fstat(descriptor)
        if (
            final.st_size != opened.st_size
            or final.st_mtime_ns != opened.st_mtime_ns
            or final.st_ctime_ns != opened.st_ctime_ns
        ):
            raise StageError("source_file_changed_during_read")
    finally:
        os.close(descriptor)
    raw = b"".join(chunks)
    if len(raw) != opened.st_size:
        raise StageError("source_file_short_read")
    return raw, opened


def _read_tree(
    root: Path,
    manifest: Mapping[str, Mapping[str, str]],
    *,
    private: bool,
    strict_chain: bool = False,
) -> tuple[dict[str, dict[str, bytes]], int]:
    _validate_manifest(manifest)
    root_fd, _identity = _open_directory(
        root,
        private=private,
        strict_chain=strict_chain,
    )
    try:
        return _read_tree_at(root_fd, manifest, private=private)
    finally:
        os.close(root_fd)


def _read_tree_at(
    root_fd: int,
    manifest: Mapping[str, Mapping[str, str]],
    *,
    private: bool,
) -> tuple[dict[str, dict[str, bytes]], int]:
    _validate_manifest(manifest)
    result: dict[str, dict[str, bytes]] = {}
    total = 0
    root_entries = set(os.listdir(root_fd))
    if (private and root_entries != set(manifest)) or (
        not private and not set(manifest).issubset(root_entries)
    ):
        raise StageError("source_directory_set_mismatch")
    for directory in sorted(manifest):
        child_fd = _open_child_directory(root_fd, directory, private=private)
        try:
            actual_entries = set(os.listdir(child_fd))
            expected_entries = set(manifest[directory])
            if not private and directory == "psycopg2" and "__pycache__" in actual_entries:
                cached = os.stat("__pycache__", dir_fd=child_fd, follow_symlinks=False)
                if not stat.S_ISDIR(cached.st_mode):
                    raise StageError("source_entry_set_mismatch")
                actual_entries.remove("__pycache__")
            if actual_entries != expected_entries:
                raise StageError("source_entry_set_mismatch")
            rows: dict[str, bytes] = {}
            for name, expected_hash in sorted(manifest[directory].items()):
                raw, identity = _read_regular_at(child_fd, name)
                if private:
                    expected_mode = 0o700 if name.endswith(".so") or ".so." in name else 0o600
                    if stat.S_IMODE(identity.st_mode) != expected_mode:
                        raise StageError("private_file_mode_invalid")
                if hashlib.sha256(raw).hexdigest() != expected_hash:
                    raise StageError("source_hash_mismatch")
                total += len(raw)
                if total > MAX_TOTAL_BYTES:
                    raise StageError("source_total_bytes_exceeded")
                rows[name] = raw
            result[directory] = rows
        finally:
            os.close(child_fd)
    return result, total


def _destination_exists(parent_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise StageError("destination_identity_unavailable") from exc
    return True


def _write_file(directory_fd: int, name: str, raw: bytes, mode: int) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(name, flags, mode, dir_fd=directory_fd)
    try:
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset : offset + 1024 * 1024])
            if written <= 0:
                raise StageError("destination_file_short_write")
            offset += written
        os.fchmod(descriptor, mode)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _rename_noreplace(parent_fd: int, source_name: str, destination_name: str) -> None:
    if sys.platform != "linux":
        if _destination_exists(parent_fd, destination_name):
            raise StageError("destination_raced")
        os.rename(
            source_name,
            destination_name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        return
    library = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(library, "renameat2", None)
    if renameat2 is None:
        raise StageError("renameat2_unavailable")
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        parent_fd,
        os.fsencode(source_name),
        parent_fd,
        os.fsencode(destination_name),
        RENAME_NOREPLACE,
    )
    if result == 0:
        return
    error = ctypes.get_errno()
    if error == errno.EEXIST:
        raise StageError("destination_raced")
    raise StageError("renameat2_failed")


def _remove_expected_temp(
    parent_fd: int,
    temp_name: str,
    manifest: Mapping[str, Mapping[str, str]],
) -> bool:
    try:
        temp_fd = _open_child_directory(parent_fd, temp_name, private=True)
    except StageError:
        return False
    try:
        if set(os.listdir(temp_fd)) != {"site-packages"}:
            return False
        site_fd = _open_child_directory(temp_fd, "site-packages", private=True)
        try:
            if set(os.listdir(site_fd)) != set(manifest):
                return False
            for directory, entries in manifest.items():
                child_fd = _open_child_directory(site_fd, directory, private=True)
                try:
                    actual = set(os.listdir(child_fd))
                    if not actual.issubset(set(entries)):
                        return False
                    for name in actual:
                        os.unlink(name, dir_fd=child_fd)
                finally:
                    os.close(child_fd)
                os.rmdir(directory, dir_fd=site_fd)
        finally:
            os.close(site_fd)
        os.rmdir("site-packages", dir_fd=temp_fd)
    finally:
        os.close(temp_fd)
    os.rmdir(temp_name, dir_fd=parent_fd)
    os.fsync(parent_fd)
    return True


def _publish_tree(
    destination_parent: Path,
    destination_name: str,
    manifest: Mapping[str, Mapping[str, str]],
    payloads: Mapping[str, Mapping[str, bytes]],
    *,
    strict_chain: bool,
) -> int:
    parent_fd, _identity = _open_directory(
        destination_parent,
        private=True,
        strict_chain=strict_chain,
    )
    temp_name = f".{destination_name}.stage-v1.tmp"
    created = False
    try:
        if _destination_exists(parent_fd, destination_name):
            raise StageError("destination_already_exists")
        if _destination_exists(parent_fd, temp_name):
            raise StageError("temporary_path_exists")
        os.mkdir(temp_name, mode=0o700, dir_fd=parent_fd)
        created = True
        temp_fd = _open_child_directory(parent_fd, temp_name, private=True)
        try:
            os.mkdir("site-packages", mode=0o700, dir_fd=temp_fd)
            site_fd = _open_child_directory(temp_fd, "site-packages", private=True)
            try:
                for directory in sorted(manifest):
                    os.mkdir(directory, mode=0o700, dir_fd=site_fd)
                    child_fd = _open_child_directory(site_fd, directory, private=True)
                    try:
                        for name in sorted(manifest[directory]):
                            mode = 0o700 if name.endswith(".so") or ".so." in name else 0o600
                            _write_file(child_fd, name, payloads[directory][name], mode)
                        os.fsync(child_fd)
                    finally:
                        os.close(child_fd)
                os.fsync(site_fd)
                _verified, verified_bytes = _read_tree_at(
                    site_fd,
                    manifest,
                    private=True,
                )
            finally:
                os.close(site_fd)
            os.fsync(temp_fd)
        finally:
            os.close(temp_fd)
        _rename_noreplace(parent_fd, temp_name, destination_name)
        created = False
        os.fsync(parent_fd)
        published_fd = _open_child_directory(
            parent_fd,
            destination_name,
            private=True,
        )
        try:
            if set(os.listdir(published_fd)) != {"site-packages"}:
                raise StageError("published_directory_set_mismatch")
            site_fd = _open_child_directory(
                published_fd,
                "site-packages",
                private=True,
            )
            try:
                _published, published_bytes = _read_tree_at(
                    site_fd,
                    manifest,
                    private=True,
                )
            finally:
                os.close(site_fd)
        finally:
            os.close(published_fd)
        if published_bytes != verified_bytes:
            raise StageError("published_size_mismatch")
        return published_bytes
    except Exception:
        if created and not _remove_expected_temp(parent_fd, temp_name, manifest):
            raise StageError("temporary_cleanup_unverified")
        raise
    finally:
        os.close(parent_fd)


def _base_result(manifest: Mapping[str, Mapping[str, str]]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA,
        "status": "BLOCKED_NO_EFFECT",
        "reason_codes": [],
        "source_root": str(SOURCE_ROOT),
        "destination": str(DESTINATION_PARENT / DESTINATION_NAME),
        "source_manifest_sha256": canonical_manifest_sha256(manifest),
        "destination_manifest_sha256": None,
        "mutation_performed": False,
        "boundaries": {
            "service_mutation": False,
            "database_access": False,
            "broker_contact": False,
            "credential_access": False,
            "subprocess_spawned": False,
            "source_repository_mutation": False,
        },
    }


def stage_bundle(
    *,
    source_root: Path,
    destination_parent: Path,
    destination_name: str,
    manifest: Mapping[str, Mapping[str, str]],
    apply: bool,
    strict_anchors: bool = False,
) -> dict[str, Any]:
    result = _base_result(manifest)
    result["source_root"] = str(source_root)
    result["destination"] = str(destination_parent / destination_name)
    mutation_started = False
    try:
        if strict_anchors and sys.platform != "linux":
            raise StageError("production_linux_required")
        if (
            not isinstance(destination_name, str)
            or not destination_name
            or destination_name in {".", ".."}
            or "/" in destination_name
            or "\x00" in destination_name
        ):
            raise StageError("destination_name_invalid")
        payloads, total_bytes = _read_tree(
            source_root,
            manifest,
            private=False,
            strict_chain=strict_anchors,
        )
        result["source_total_bytes"] = total_bytes
        parent_fd, _identity = _open_directory(
            destination_parent,
            private=True,
            strict_chain=strict_anchors,
        )
        try:
            if _destination_exists(parent_fd, destination_name):
                raise StageError("destination_already_exists")
            if _destination_exists(parent_fd, f".{destination_name}.stage-v1.tmp"):
                raise StageError("temporary_path_exists")
        finally:
            os.close(parent_fd)
        if not apply:
            result["status"] = "PREFLIGHT_PASS"
            return result
        mutation_started = True
        verified_bytes = _publish_tree(
            destination_parent,
            destination_name,
            manifest,
            payloads,
            strict_chain=strict_anchors,
        )
        if verified_bytes != total_bytes:
            raise StageError("destination_size_mismatch")
        result["status"] = "APPLIED_POSTCHECK_PASS"
        result["destination_manifest_sha256"] = canonical_manifest_sha256(manifest)
        result["mutation_performed"] = True
        return result
    except StageError as exc:
        result["status"] = "FAIL_CLOSED_UNVERIFIED" if mutation_started else "BLOCKED_NO_EFFECT"
        result["reason_codes"] = [exc.reason]
        result["mutation_performed"] = mutation_started
        return result
    except Exception as exc:
        result["status"] = "FAIL_CLOSED_UNVERIFIED" if mutation_started else "BLOCKED_NO_EFFECT"
        result["reason_codes"] = ["unexpected_" + type(exc).__name__]
        result["mutation_performed"] = mutation_started
        return result


def main(argv: list[str] | None = None) -> int:
    if sys.flags.isolated != 1 or sys.dont_write_bytecode is not True:
        result = _base_result(SEALED_MANIFEST)
        result["reason_codes"] = ["isolated_no_bytecode_runtime_required"]
        print(json.dumps(result, sort_keys=True, separators=(",", ":")), flush=True)
        return 4
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    result = stage_bundle(
        source_root=SOURCE_ROOT,
        destination_parent=DESTINATION_PARENT,
        destination_name=DESTINATION_NAME,
        manifest=SEALED_MANIFEST,
        apply=args.apply,
        strict_anchors=True,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")), flush=True)
    return 0 if result["status"] in {"PREFLIGHT_PASS", "APPLIED_POSTCHECK_PASS"} else 4


if __name__ == "__main__":
    raise SystemExit(main())
