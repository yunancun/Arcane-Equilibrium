"""Race-resistant bounded reads for local ALR control/evidence files."""

from __future__ import annotations

import errno
import os
import stat
from pathlib import Path
from typing import Final


UNAVAILABLE: Final = "UNAVAILABLE"
NOT_REGULAR: Final = "NOT_REGULAR"
MODE_INVALID: Final = "MODE_INVALID"
SIZE_INVALID: Final = "SIZE_INVALID"
CHANGED: Final = "CHANGED"
UNREADABLE: Final = "UNREADABLE"
SECURE_OPEN_UNAVAILABLE: Final = "SECURE_OPEN_UNAVAILABLE"


class AlrSafeFileError(OSError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def read_bounded_regular_file(
    path: Path,
    *,
    max_bytes: int,
    require_nonempty: bool,
    require_private_mode: bool,
    expected_stat: os.stat_result | None = None,
) -> bytes:
    """Open once with O_NOFOLLOW, validate/read/revalidate the same fd."""
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ValueError("max_bytes_invalid")
    nofollow = getattr(os, "O_NOFOLLOW", None)
    cloexec = getattr(os, "O_CLOEXEC", None)
    if nofollow is None or cloexec is None:
        raise AlrSafeFileError(SECURE_OPEN_UNAVAILABLE)
    flags = os.O_RDONLY | nofollow | cloexec
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        if expected_stat is not None and exc.errno in {errno.ENOENT, errno.ELOOP}:
            raise AlrSafeFileError(CHANGED) from exc
        if exc.errno in {errno.ELOOP, errno.EISDIR}:
            raise AlrSafeFileError(NOT_REGULAR) from exc
        raise AlrSafeFileError(UNAVAILABLE) from exc
    try:
        try:
            before = os.fstat(descriptor)
        except OSError as exc:
            raise AlrSafeFileError(UNREADABLE) from exc
        if not stat.S_ISREG(before.st_mode):
            raise AlrSafeFileError(NOT_REGULAR)
        if expected_stat is not None and _identity(before) != _identity(expected_stat):
            raise AlrSafeFileError(CHANGED)
        if require_private_mode and stat.S_IMODE(before.st_mode) & 0o077:
            raise AlrSafeFileError(MODE_INVALID)
        if before.st_size > max_bytes or (require_nonempty and before.st_size <= 0):
            raise AlrSafeFileError(SIZE_INVALID)
        chunks: list[bytes] = []
        total = 0
        while True:
            try:
                chunk = os.read(descriptor, min(65_536, max_bytes + 1 - total))
            except OSError as exc:
                raise AlrSafeFileError(UNREADABLE) from exc
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise AlrSafeFileError(SIZE_INVALID)
        try:
            after = os.fstat(descriptor)
        except OSError as exc:
            raise AlrSafeFileError(UNREADABLE) from exc
        if _identity(before) != _identity(after) or total != before.st_size:
            raise AlrSafeFileError(CHANGED)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _identity(metadata: os.stat_result) -> tuple[int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
    )
