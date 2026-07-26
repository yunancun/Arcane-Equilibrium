"""Candidate board(immutable 候選榜)inotify wake 事件源——由 alr_event_consumer 拆出。

MODULE_NOTE
模塊用途:Linux inotify 目錄監看(事件名絕不攜帶學習內容),供 consumer 的
    candidate reconciliation 車道以 wake 訊號驅動;並持有 consumer 家族共用的
    typed error 根類別 ``AlrEventConsumerError``。
主要對象:AlrEventConsumerError、CandidateBoardEventSource、
    open_candidate_board_event_source。
硬邊界:本模組零 SQL、零 DB 連線、零 retention 匯入;僅作 fd/inotify 生命週期
    管理。S2.4 §2.1 2000 行治理拆分(W2a):alr_event_consumer 逐位元組搬出本段,
    對外仍經 consumer re-export(公開匯入面不變)。

import-DAG 註記:本模組是 consumer 家族的 DAG 根之一——top-level 絕不匯入
alr_event_consumer 或任何 repository 模組(無循環);``AlrEventConsumerError``
定義於此,consumer 與 alr_retention_runner 皆由此取得同一類別(異常身分不變)。
"""

from __future__ import annotations

import ctypes
import errno
import os
import re
import stat
import struct
import sys
from pathlib import Path
from typing import Any


_IN_ACCESS_EVENT = struct.Struct("iIII")
_IN_CREATE = 0x00000100
_IN_DELETE = 0x00000200
_IN_MOVED_FROM = 0x00000040
_IN_MOVED_TO = 0x00000080
_IN_CLOSE_WRITE = 0x00000008
_IN_DELETE_SELF = 0x00000400
_IN_MOVE_SELF = 0x00000800
_IN_UNMOUNT = 0x00002000
_IN_Q_OVERFLOW = 0x00004000
_IN_IGNORED = 0x00008000
_IN_ONLYDIR = 0x01000000
_IN_DONT_FOLLOW = 0x02000000
# The immutable publisher links the new board before pruning the old board.
# DELETE is the retry wake when a CREATE reconciliation observes that transient.
# P2-2(W2 review):把一份不可變看板「改名搬出」本目錄,核心發的是 IN_MOVED_FROM 而
# **不是** IN_DELETE——舊 wake mask 不訂閱它,該看板於是永遠留在投影裡(移除事件被吞)。
# rename-out 與 unlink 對帳語義完全相同,故一併入 wake mask(watch mask 由其導出)。
_INOTIFY_WAKE_MASK = (
    _IN_CREATE | _IN_DELETE | _IN_MOVED_FROM | _IN_MOVED_TO | _IN_CLOSE_WRITE
)
_INOTIFY_INVALIDATION_MASK = _IN_DELETE_SELF | _IN_MOVE_SELF | _IN_UNMOUNT | _IN_IGNORED
_INOTIFY_WATCH_MASK = _INOTIFY_WAKE_MASK | (
    _IN_DELETE_SELF | _IN_MOVE_SELF | _IN_UNMOUNT
) | _IN_ONLYDIR | _IN_DONT_FOLLOW
_IMMUTABLE_CANDIDATE_BOARD_NAME_RE = re.compile(
    r"^blocked_outcome_review_[0-9]{8}T[0-9]{6}Z\.json$"
)


class AlrEventConsumerError(ValueError):
    """An ALR notification or consumer control cannot be handled safely."""


class CandidateBoardEventSource:
    """Linux inotify wake source; event names never carry learning content."""

    def __init__(
        self,
        directory: Path,
        *,
        event_fd: int,
        watch_descriptor: int,
        directory_fd: int,
        reopen_watch: Any,
    ) -> None:
        self._directory = directory
        self._event_fd = event_fd
        self._watch_descriptor = watch_descriptor
        self._directory_fd = directory_fd
        self._reopen_watch = reopen_watch
        self._reconciliation_required = True
        self._closed = False

    def __enter__(self) -> "CandidateBoardEventSource":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def fileno(self) -> int:
        if self._closed:
            raise AlrEventConsumerError("candidate_board_event_source_closed")
        return self._event_fd

    def consume_reconciliation_request(self) -> bool:
        requested = self._reconciliation_required
        self._reconciliation_required = False
        return requested

    def drain_ready(self) -> None:
        """Drain bounded kernel records and reduce every valid event to one wake."""
        if self._closed:
            raise AlrEventConsumerError("candidate_board_event_source_closed")
        try:
            payload = os.read(self._event_fd, 64 * 1024)
        except BlockingIOError:
            return
        except OSError as exc:
            if exc.errno in {errno.EAGAIN, errno.EWOULDBLOCK}:
                return
            raise AlrEventConsumerError("candidate_board_event_read_failed") from exc
        if not payload:
            return
        offset = 0
        invalidated = False
        while offset < len(payload):
            if len(payload) - offset < _IN_ACCESS_EVENT.size:
                raise AlrEventConsumerError("candidate_board_event_truncated")
            watch_descriptor, mask, _cookie, name_length = _IN_ACCESS_EVENT.unpack_from(
                payload, offset
            )
            offset += _IN_ACCESS_EVENT.size
            if name_length > 4096 or offset + name_length > len(payload):
                raise AlrEventConsumerError("candidate_board_event_name_invalid")
            raw_name = bytes(payload[offset : offset + name_length])
            offset += name_length
            if watch_descriptor == -1 and mask & _IN_Q_OVERFLOW:
                invalidated = True
                self._reconciliation_required = True
                continue
            if watch_descriptor != self._watch_descriptor:
                continue
            if mask & _INOTIFY_INVALIDATION_MASK:
                invalidated = True
                self._reconciliation_required = True
                continue
            if mask & _INOTIFY_WAKE_MASK:
                name = raw_name.split(b"\x00", 1)[0]
                try:
                    decoded_name = name.decode("ascii")
                except UnicodeDecodeError:
                    continue
                if _IMMUTABLE_CANDIDATE_BOARD_NAME_RE.fullmatch(decoded_name):
                    self._reconciliation_required = True
        if invalidated:
            new_event_fd, new_watch, new_directory_fd = self._reopen_watch(
                self._directory
            )
            old_event_fd = self._event_fd
            old_directory_fd = self._directory_fd
            self._event_fd = new_event_fd
            self._watch_descriptor = new_watch
            self._directory_fd = new_directory_fd
            _close_candidate_board_watch_descriptors(
                old_event_fd if old_event_fd != new_event_fd else -1,
                old_directory_fd
                if old_directory_fd >= 0 and old_directory_fd != new_directory_fd
                else -1,
            )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        _close_candidate_board_watch_descriptors(
            self._event_fd,
            self._directory_fd,
        )


def _close_candidate_board_watch_descriptors(
    event_fd: int,
    directory_fd: int,
) -> None:
    try:
        if directory_fd >= 0:
            os.close(directory_fd)
    finally:
        if event_fd >= 0:
            os.close(event_fd)


def open_candidate_board_event_source(
    directory: Path,
    *,
    open_watch: Any = None,
    reopen_watch: Any = None,
) -> CandidateBoardEventSource:
    """Open one nonblocking Linux directory watch with startup reconciliation."""
    opener = open_watch or _open_linux_candidate_board_watch
    reopen = reopen_watch or _open_linux_candidate_board_watch
    event_fd, watch_descriptor, directory_fd = opener(Path(directory))
    return CandidateBoardEventSource(
        Path(directory),
        event_fd=event_fd,
        watch_descriptor=watch_descriptor,
        directory_fd=directory_fd,
        reopen_watch=reopen,
    )


def _open_linux_candidate_board_watch(directory: Path) -> tuple[int, int, int]:
    if sys.platform != "linux":
        raise AlrEventConsumerError("candidate_board_inotify_unsupported")
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        init = libc.inotify_init1
        init.argtypes = [ctypes.c_int]
        init.restype = ctypes.c_int
    except (AttributeError, OSError) as exc:
        raise AlrEventConsumerError("candidate_board_inotify_unavailable") from exc
    event_fd = init(os.O_NONBLOCK | os.O_CLOEXEC)
    if event_fd < 0:
        error_number = ctypes.get_errno()
        raise AlrEventConsumerError(
            f"candidate_board_inotify_open_failed:{error_number}"
        ) from OSError(error_number, os.strerror(error_number))
    try:
        watch_descriptor, directory_fd = _add_linux_candidate_board_watch(
            libc,
            event_fd,
            directory,
        )
    except Exception:
        os.close(event_fd)
        raise
    return event_fd, watch_descriptor, directory_fd


def _add_linux_candidate_board_watch(
    libc: Any,
    event_fd: int,
    directory: Path,
) -> tuple[int, int]:
    try:
        before = directory.lstat()
    except OSError as exc:
        raise AlrEventConsumerError("candidate_board_directory_unavailable") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
        raise AlrEventConsumerError("candidate_board_directory_invalid")
    try:
        directory_fd = os.open(
            directory,
            os.O_RDONLY
            | os.O_CLOEXEC
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as exc:
        raise AlrEventConsumerError("candidate_board_directory_unavailable") from exc
    try:
        opened = os.fstat(directory_fd)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise AlrEventConsumerError("candidate_board_directory_changed")
        add_watch = libc.inotify_add_watch
        add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
        add_watch.restype = ctypes.c_int
        held_directory_path = os.fsencode(f"/proc/self/fd/{directory_fd}/.")
        descriptor = add_watch(
            event_fd,
            held_directory_path,
            _INOTIFY_WATCH_MASK,
        )
        if descriptor < 0:
            error_number = ctypes.get_errno()
            raise AlrEventConsumerError(
                f"candidate_board_inotify_watch_failed:{error_number}"
            ) from OSError(error_number, os.strerror(error_number))
        after = directory.lstat()
        if (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino):
            raise AlrEventConsumerError("candidate_board_directory_changed")
        return descriptor, directory_fd
    except Exception:
        os.close(directory_fd)
        raise
