"""alr_candidate_board_events(S2.4 W2a 自 alr_event_consumer 拆出)inotify 行為測試。

原 test_alr_event_consumer 中「純 board-watch 面」的五支測試等值搬移至此
(行為/斷言不變;僅把 consumer.* 讀名改為 board.*——consumer 對這些名字仍
re-export 同一物件,身分由 test_alr_event_consumer 的 re-export 斷言鎖住)。
"""

from __future__ import annotations

import os
import select
import struct
import sys
from pathlib import Path

import pytest

from ml_training import alr_candidate_board_events as board
from ml_training.alr_candidate_board_events import AlrEventConsumerError


def test_candidate_board_inotify_source_wakes_on_immutable_create_and_recovers_overflow(
    tmp_path: Path,
) -> None:
    read_fd, write_fd = os.pipe()
    os.set_blocking(read_fd, False)
    rearms: list[Path] = []

    def open_watch(directory: Path) -> tuple[int, int, int]:
        assert directory == tmp_path
        return read_fd, 17, -1

    def reopen_watch(directory: Path) -> tuple[int, int, int]:
        rearms.append(directory)
        return read_fd, 23, -1

    source = board.open_candidate_board_event_source(
        tmp_path,
        open_watch=open_watch,
        reopen_watch=reopen_watch,
    )
    try:
        assert source.consume_reconciliation_request() is True
        assert source.consume_reconciliation_request() is False

        for mask in (
            board._IN_CREATE,
            board._IN_MOVED_TO,
            board._IN_CLOSE_WRITE,
            board._IN_DELETE,
        ):
            name = b"blocked_outcome_review_20260711T120000Z.json\x00"
            padded = name + b"\x00" * ((4 - len(name) % 4) % 4)
            os.write(
                write_fd,
                struct.pack("iIII", 17, mask, 0, len(padded)) + padded,
            )
            source.drain_ready()
            assert source.consume_reconciliation_request() is True

        os.write(
            write_fd,
            struct.pack("iIII", -1, board._IN_Q_OVERFLOW, 0, 0),
        )
        source.drain_ready()
        assert source.consume_reconciliation_request() is True
        assert rearms == [tmp_path]

        os.write(
            write_fd,
            struct.pack("iIII", 17, board._IN_IGNORED, 0, 0),
        )
        source.drain_ready()
        assert source.consume_reconciliation_request() is False
        assert rearms == [tmp_path]

        os.write(
            write_fd,
            struct.pack("iIII", 23, board._IN_IGNORED, 0, 0),
        )
        source.drain_ready()
        assert source.consume_reconciliation_request() is True
        assert rearms == [tmp_path, tmp_path]
    finally:
        source.close()
        with pytest.raises(OSError):
            os.fstat(read_fd)
        os.close(write_fd)


def test_candidate_board_rearm_closes_old_descriptors_and_owns_new_pair(
    tmp_path: Path,
) -> None:
    old_read_fd, old_write_fd = os.pipe()
    new_read_fd, new_write_fd = os.pipe()
    os.set_blocking(old_read_fd, False)
    old_directory_fd = os.open(tmp_path, os.O_RDONLY)
    new_directory_fd = os.open(tmp_path, os.O_RDONLY)

    source = board.open_candidate_board_event_source(
        tmp_path,
        open_watch=lambda directory: (old_read_fd, 17, old_directory_fd),
        reopen_watch=lambda directory: (new_read_fd, 23, new_directory_fd),
    )
    try:
        source.consume_reconciliation_request()
        os.write(
            old_write_fd,
            struct.pack("iIII", 17, board._IN_IGNORED, 0, 0),
        )
        source.drain_ready()

        with pytest.raises(OSError):
            os.fstat(old_read_fd)
        with pytest.raises(OSError):
            os.fstat(old_directory_fd)
        os.fstat(new_read_fd)
        os.fstat(new_directory_fd)
        assert source.consume_reconciliation_request() is True
    finally:
        source.close()
        os.close(old_write_fd)
        os.close(new_write_fd)

    with pytest.raises(OSError):
        os.fstat(new_read_fd)
    with pytest.raises(OSError):
        os.fstat(new_directory_fd)


def test_candidate_board_event_source_rejects_truncated_kernel_record(
    tmp_path: Path,
) -> None:
    read_fd, write_fd = os.pipe()
    os.set_blocking(read_fd, False)
    source = board.open_candidate_board_event_source(
        tmp_path,
        open_watch=lambda directory: (read_fd, 7, -1),
        reopen_watch=lambda directory: (read_fd, 7, -1),
    )
    source.consume_reconciliation_request()
    try:
        os.write(write_fd, b"truncated")
        with pytest.raises(AlrEventConsumerError, match="candidate_board_event_truncated"):
            source.drain_ready()
    finally:
        source.close()
        os.close(write_fd)


def test_inotify_watch_binds_held_directory_fd_across_configured_path_aba(
    tmp_path: Path,
) -> None:
    configured = tmp_path / "configured"
    replacement = tmp_path / "replacement"
    held_name = tmp_path / "held-original"
    configured.mkdir()
    replacement.mkdir()
    original_identity = configured.stat().st_dev, configured.stat().st_ino
    replacement_identity = replacement.stat().st_dev, replacement.stat().st_ino
    observed_paths: list[bytes] = []

    class AddWatch:
        argtypes: object = None
        restype: object = None

        def __call__(self, event_fd: int, path: bytes, mask: int) -> int:
            assert event_fd == 41
            assert mask & board._IN_ONLYDIR
            assert mask & board._IN_DONT_FOLLOW
            observed_paths.append(path)
            decoded = os.fsdecode(path)
            prefix = "/proc/self/fd/"
            assert decoded.startswith(prefix)
            assert decoded.endswith("/.")
            directory_fd = int(decoded[len(prefix) : -2])
            assert (os.fstat(directory_fd).st_dev, os.fstat(directory_fd).st_ino) == (
                original_identity
            )

            configured.rename(held_name)
            replacement.rename(configured)
            try:
                assert (configured.stat().st_dev, configured.stat().st_ino) == (
                    replacement_identity
                )
                assert (os.fstat(directory_fd).st_dev, os.fstat(directory_fd).st_ino) == (
                    original_identity
                )
            finally:
                configured.rename(replacement)
                held_name.rename(configured)
            return 19

    class Libc:
        inotify_add_watch = AddWatch()

    descriptor, directory_fd = board._add_linux_candidate_board_watch(
        Libc(),
        41,
        configured,
    )
    try:
        assert descriptor == 19
        assert observed_paths == [os.fsencode(f"/proc/self/fd/{directory_fd}/.")]
        assert (configured.stat().st_dev, configured.stat().st_ino) == (
            original_identity
        )
    finally:
        os.close(directory_fd)


def test_rename_out_of_the_watched_directory_wakes_reconciliation(tmp_path: Path) -> None:
    """P2-2:把看板改名搬出本目錄,核心發 IN_MOVED_FROM(**不是** IN_DELETE)。

    舊 wake/watch mask 不訂閱該事件 → 被移除的看板永遠留在投影裡。此處以 kernel 記錄的
    位元組形直接餵入事件源:mask 必須被認成 wake,且 watch mask 也必須訂閱它,否則核心
    根本不會投遞這條記錄。
    """
    read_fd, write_fd = os.pipe()
    os.set_blocking(read_fd, False)

    def open_watch(directory: Path) -> tuple[int, int, int]:
        return read_fd, 31, -1

    source = board.open_candidate_board_event_source(
        tmp_path, open_watch=open_watch, reopen_watch=open_watch
    )
    try:
        assert source.consume_reconciliation_request() is True  # 啟動對帳
        assert source.consume_reconciliation_request() is False
        # 訂閱面:核心只投遞 watch mask 內的事件,故兩個 mask 都必須含 IN_MOVED_FROM。
        assert board._INOTIFY_WAKE_MASK & board._IN_MOVED_FROM
        assert board._INOTIFY_WATCH_MASK & board._IN_MOVED_FROM
        name = b"blocked_outcome_review_20260711T120000Z.json\x00"
        padded = name + b"\x00" * ((4 - len(name) % 4) % 4)
        os.write(
            write_fd,
            struct.pack("iIII", 31, board._IN_MOVED_FROM, 7, len(padded)) + padded,
        )
        source.drain_ready()
        assert source.consume_reconciliation_request() is True
    finally:
        source.close()
        os.close(write_fd)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux inotify integration")
def test_linux_inotify_real_rename_out_wakes_bounded_source(tmp_path: Path) -> None:
    """真 inotify:把看板改名搬出受監看目錄,事件源必須醒來並要求對帳。"""
    evidence_directory = tmp_path / "evidence"
    evidence_directory.mkdir()
    board_path = evidence_directory / "blocked_outcome_review_20260711T120000Z.json"
    board_path.write_text("{}\n", encoding="utf-8")
    source = board.open_candidate_board_event_source(evidence_directory)
    try:
        assert source.consume_reconciliation_request() is True
        os.rename(board_path, tmp_path / "blocked_outcome_review_20260711T120000Z.json")
        ready, _, _ = select.select([source], [], [], 1.0)
        assert ready == [source]
        source.drain_ready()
        assert source.consume_reconciliation_request() is True
    finally:
        source.close()


@pytest.mark.skipif(sys.platform != "linux", reason="Linux inotify integration")
def test_linux_inotify_real_link_publish_wakes_bounded_source(tmp_path: Path) -> None:
    evidence_directory = tmp_path / "evidence"
    evidence_directory.mkdir()
    producer_path = tmp_path / "producer.json"
    producer_path.write_text("{}\n", encoding="utf-8")
    source = board.open_candidate_board_event_source(evidence_directory)
    try:
        assert source.consume_reconciliation_request() is True
        os.link(
            producer_path,
            evidence_directory / "blocked_outcome_review_20260711T120000Z.json",
        )
        ready, _, _ = select.select([source], [], [], 1.0)
        assert ready == [source]
        source.drain_ready()
        assert source.consume_reconciliation_request() is True
    finally:
        source.close()
