#!/usr/bin/env python3
"""Generation-stable retained JSONL scanning for learning-lane consumers.

The scanner owns physical file admission and JSONL framing only.  Callers must
provide a consumer-specific reducer; returning a generic full-ledger iterator
or list here would merely move the unbounded-memory failure to another layer.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
from typing import Any

from cost_gate_learning_lane.ledger_rotation import retained_ledger_files


LEDGER_SCAN_ADMISSION_RETRIES = 3
LEDGER_SCAN_CHUNK_BYTES = 1024 * 1024
MAX_LEDGER_JSONL_LINE_BYTES = 16 * 1024 * 1024


class LedgerScanError(ValueError):
    """Fail-closed retained-ledger scan failure."""

    def __init__(
        self,
        code: str,
        *,
        path: Path | None = None,
        line_no: int | None = None,
    ) -> None:
        self.code = code
        self.path = path
        self.line_no = line_no
        location = ""
        if path is not None:
            location = f":{path}"
            if line_no is not None:
                location += f":{line_no}"
        malformed = any(
            marker in code
            for marker in (
                "MALFORMED_JSON",
                "NON_OBJECT_ROW",
                "INVALID_UTF8",
                "PARTIAL_LINE",
                "LINE_OVERSIZED",
            )
        )
        prefix = "malformed JSONL ledger:" if malformed else ""
        super().__init__(f"{prefix}{code}{location}")


class LedgerProjectionLimitError(LedgerScanError):
    """A bounded reducer reached its declared complete-universe limit."""


@dataclass(frozen=True)
class RetainedLedgerSource:
    """One path-position and exact admitted prefix bound to an opened inode."""

    path: Path
    position: int
    dev: int
    ino: int
    admitted_prefix_size: int


@dataclass(frozen=True)
class RetainedLedgerScan:
    """Metadata for one fully consumed retained-ledger generation."""

    ledger_path: Path
    sources: tuple[RetainedLedgerSource, ...]
    source_bytes: int
    row_count: int


@dataclass
class _OpenedSource:
    binding: RetainedLedgerSource
    fd: int

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1


def _inventory(
    ledger_path: Path,
) -> tuple[tuple[Path, int, int, int, int], ...]:
    """Return path-position/dev/inode/size without following symlinks."""
    entries: list[tuple[Path, int, int, int, int]] = []
    for position, path in enumerate(retained_ledger_files(ledger_path)):
        try:
            info = path.stat(follow_symlinks=False)
        except FileNotFoundError:
            raise
        except OSError as exc:
            raise LedgerScanError(
                f"RETAINED_LEDGER_INVENTORY_{type(exc).__name__.upper()}",
                path=path,
            ) from exc
        if not stat.S_ISREG(info.st_mode):
            raise LedgerScanError(
                "RETAINED_LEDGER_SOURCE_NOT_REGULAR",
                path=path,
            )
        entries.append((path, position, info.st_dev, info.st_ino, info.st_size))
    return tuple(entries)


def _open_admitted_generation(
    ledger_path: Path,
    *,
    admission_retries: int,
) -> list[_OpenedSource]:
    """Open one stable retained path generation and bind exact prefix sizes."""
    if admission_retries < 1:
        raise ValueError("admission_retries must be positive")
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise LedgerScanError(
            "RETAINED_LEDGER_SECURE_OPEN_UNAVAILABLE",
            path=ledger_path,
        )
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | nofollow
    )
    last_drift = "RETAINED_LEDGER_GENERATION_UNSTABLE"
    for _attempt in range(admission_retries):
        opened: list[_OpenedSource] = []
        accepted = False
        try:
            try:
                inventory = _inventory(ledger_path)
            except FileNotFoundError:
                last_drift = "RETAINED_LEDGER_GENERATION_CHANGED_DURING_ADMISSION"
                continue
            for path, position, dev, ino, admitted_size in inventory:
                try:
                    fd = os.open(path, flags)
                except FileNotFoundError:
                    last_drift = (
                        "RETAINED_LEDGER_GENERATION_CHANGED_DURING_ADMISSION"
                    )
                    break
                except OSError as exc:
                    raise LedgerScanError(
                        f"RETAINED_LEDGER_OPEN_{type(exc).__name__.upper()}",
                        path=path,
                    ) from exc
                info = os.fstat(fd)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_dev != dev
                    or info.st_ino != ino
                    or info.st_size < admitted_size
                ):
                    os.close(fd)
                    last_drift = (
                        "RETAINED_LEDGER_GENERATION_CHANGED_DURING_ADMISSION"
                    )
                    break
                opened.append(
                    _OpenedSource(
                        binding=RetainedLedgerSource(
                            path=path,
                            position=position,
                            dev=info.st_dev,
                            ino=info.st_ino,
                            admitted_prefix_size=admitted_size,
                        ),
                        fd=fd,
                    )
                )
            if len(opened) != len(inventory):
                continue

            try:
                confirmed = _inventory(ledger_path)
            except FileNotFoundError:
                last_drift = "RETAINED_LEDGER_GENERATION_CHANGED_DURING_ADMISSION"
                continue
            admitted_identity = tuple(
                (
                    source.binding.path,
                    source.binding.position,
                    source.binding.dev,
                    source.binding.ino,
                )
                for source in opened
            )
            confirmed_identity = tuple(
                (path, position, dev, ino)
                for path, position, dev, ino, _size in confirmed
            )
            if confirmed_identity != admitted_identity:
                last_drift = "RETAINED_LEDGER_GENERATION_CHANGED_DURING_ADMISSION"
                continue
            # Appends after admission are intentionally deferred.  A shrink is
            # never admissible because it invalidates the promised prefix.
            if any(
                confirmed_entry[4] < source.binding.admitted_prefix_size
                for confirmed_entry, source in zip(confirmed, opened)
            ):
                last_drift = "RETAINED_LEDGER_PREFIX_SHRANK_DURING_ADMISSION"
                continue
            accepted = True
            return opened
        finally:
            if not accepted:
                for source in opened:
                    source.close()
    raise LedgerScanError(
        f"{last_drift}_AFTER_{admission_retries}_ATTEMPTS",
        path=ledger_path,
    )


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"invalid JSON constant: {value}")


def _parse_row(raw_line: bytes, *, path: Path, line_no: int) -> dict[str, Any]:
    if len(raw_line) > MAX_LEDGER_JSONL_LINE_BYTES:
        raise LedgerScanError(
            "RETAINED_LEDGER_LINE_OVERSIZED",
            path=path,
            line_no=line_no,
        )
    try:
        text = raw_line.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LedgerScanError(
            "RETAINED_LEDGER_INVALID_UTF8",
            path=path,
            line_no=line_no,
        ) from exc
    try:
        row = json.loads(text, parse_constant=_reject_json_constant)
    except (json.JSONDecodeError, ValueError) as exc:
        raise LedgerScanError(
            "RETAINED_LEDGER_MALFORMED_JSON",
            path=path,
            line_no=line_no,
        ) from exc
    if not isinstance(row, dict):
        raise LedgerScanError(
            "RETAINED_LEDGER_NON_OBJECT_ROW",
            path=path,
            line_no=line_no,
        )
    return row


def scan_retained_jsonl(
    ledger_path: Path,
    consume: Callable[[dict[str, Any]], None],
    *,
    on_admitted: Callable[[tuple[RetainedLedgerSource, ...]], None] | None = None,
    admission_retries: int = LEDGER_SCAN_ADMISSION_RETRIES,
    chunk_bytes: int = LEDGER_SCAN_CHUNK_BYTES,
) -> RetainedLedgerScan:
    """Consume one exact retained prefix through a caller-owned bounded reducer.

    A path rotation after admission is safe: held descriptors continue reading
    the admitted inodes.  Appended bytes are not consumed until the next scan.
    Short reads, inode drift on the descriptor, or shrink below the admitted
    prefix fail closed and no successful scan metadata is returned.
    """
    if chunk_bytes < 1:
        raise ValueError("chunk_bytes must be positive")
    opened = _open_admitted_generation(
        ledger_path,
        admission_retries=admission_retries,
    )
    bindings = tuple(source.binding for source in opened)
    row_count = 0
    try:
        if on_admitted is not None:
            on_admitted(bindings)
        for source in opened:
            binding = source.binding
            remaining = binding.admitted_prefix_size
            buffer = b""
            line_no = 0
            while remaining:
                try:
                    chunk = os.read(source.fd, min(chunk_bytes, remaining))
                except OSError as exc:
                    raise LedgerScanError(
                        f"RETAINED_LEDGER_READ_{type(exc).__name__.upper()}",
                        path=binding.path,
                    ) from exc
                if not chunk:
                    raise LedgerScanError(
                        "RETAINED_LEDGER_SHORT_READ",
                        path=binding.path,
                    )
                remaining -= len(chunk)
                buffer += chunk
                while True:
                    newline = buffer.find(b"\n")
                    if newline < 0:
                        break
                    raw_line = buffer[:newline]
                    buffer = buffer[newline + 1 :]
                    line_no += 1
                    if len(raw_line) > MAX_LEDGER_JSONL_LINE_BYTES:
                        raise LedgerScanError(
                            "RETAINED_LEDGER_LINE_OVERSIZED",
                            path=binding.path,
                            line_no=line_no,
                        )
                    if not raw_line.strip():
                        continue
                    consume(
                        _parse_row(
                            raw_line,
                            path=binding.path,
                            line_no=line_no,
                        )
                    )
                    row_count += 1
                if len(buffer) > MAX_LEDGER_JSONL_LINE_BYTES:
                    raise LedgerScanError(
                        "RETAINED_LEDGER_LINE_OVERSIZED",
                        path=binding.path,
                        line_no=line_no + 1,
                    )
            if buffer:
                raise LedgerScanError(
                    "RETAINED_LEDGER_PARTIAL_LINE",
                    path=binding.path,
                    line_no=line_no + 1,
                )
            info = os.fstat(source.fd)
            if info.st_dev != binding.dev or info.st_ino != binding.ino:
                raise LedgerScanError(
                    "RETAINED_LEDGER_OPEN_INODE_REPLACED",
                    path=binding.path,
                )
            if info.st_size < binding.admitted_prefix_size:
                raise LedgerScanError(
                    "RETAINED_LEDGER_PREFIX_SHRANK",
                    path=binding.path,
                )
        try:
            current_inventory = _inventory(ledger_path)
        except FileNotFoundError as exc:
            raise LedgerScanError(
                "RETAINED_LEDGER_PATH_REPLACED_AFTER_ADMISSION",
                path=ledger_path,
            ) from exc
        current_by_inode = {
            (dev, ino): (path, size)
            for path, _position, dev, ino, size in current_inventory
        }
        for binding in bindings:
            current = current_by_inode.get((binding.dev, binding.ino))
            if current is None:
                raise LedgerScanError(
                    "RETAINED_LEDGER_PATH_REPLACED_AFTER_ADMISSION",
                    path=binding.path,
                )
            current_path, current_size = current
            if current_size < binding.admitted_prefix_size:
                raise LedgerScanError(
                    "RETAINED_LEDGER_PREFIX_SHRANK",
                    path=current_path,
                )
    finally:
        for source in opened:
            source.close()
    return RetainedLedgerScan(
        ledger_path=ledger_path,
        sources=bindings,
        source_bytes=sum(source.admitted_prefix_size for source in bindings),
        row_count=row_count,
    )
