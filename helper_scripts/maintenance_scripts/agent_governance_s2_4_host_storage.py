#!/usr/bin/env python3
"""S2E.2b-1:S2.4 §5.2 的 **POSIX 檔案 / install-lock driver**(純 ``os`` + ``fcntl``)。

W4a 把 ``DurableFileDriver``(三本 WAL journal + §9.1 replay ledger 共用)與
``InstallLockDriver`` 定義成**注入的 protocol**,並讓 ``driver=None`` 一律 typed
``EXTERNAL_VERIFICATION_PENDING``;真正的 ``openat`` / ``fsync`` / ``renameat`` / ``flock``
一直只存在於測試假件裡。本模組是它們今日在 repo 內的唯一 production 實作。

**本模組不做任何裁決,只回報事實。** §5.2 的每一條前置——parent 必須 root-owned、mode 恰為
``0700``、非 symlink;暫存檔必須同裝置、link count 為一、mode ``0600``;lock 必須是 root-owned
的一般檔——全部由 :mod:`agent_governance_s2_4_journal` 與 :mod:`agent_governance_s2_4_lock`
在**它們拿到本模組回報的觀測之後**執法。driver 若自己也判一次,判準就有兩份,而兩份判準遲早
會分岔;更糟的是「driver 自己判過了」會變成上層放寬的藉口。

**零新主機能力。** 沒有任何行程生成面、沒有 argv、沒有網路、沒有秘密面;能做的事就是那兩個
protocol 逐字宣告的方法,一個不多(family 的 AST 掃描以字串包含判定行程生成面,故本檔連該
模組名都不出現):

- 檔案面**沒有** ``unlink`` / ``truncate`` / ``chmod`` / ``chown`` / ``rotate`` / ``rmdir``
  (:data:`agent_governance_s2_4_journal.FORBIDDEN_JOURNAL_METHODS`)——一本 malformed 的
  journal 永遠不會被自動改名或覆寫,擱淺的暫存檔永遠由 operator 親自處理;
- lock 面**沒有** ``unlink`` / ``rename`` / ``chmod``
  (:data:`agent_governance_s2_4_lock.FORBIDDEN_LOCK_METHODS`)——install lock 永不被 unlink。

兩個 ``assert_no_*_surface`` 硬檢在真正呼叫任何方法之前就會看到這件事;本模組的結構讓它們回空。

**open flags 是導出的,不是手抄的。** 每個進入點只接受**該 owner 模組宣告的 exact flag 元組**
(``JOURNAL_PARENT_OPEN_FLAGS`` 等),flag 名 → ``os.O_*`` 的映射是一張**封閉表**。刻意不用
``getattr(os, name)``:那會讓一個 caller 遞交的字串決定要開什麼旗標,而 ``os`` 這個命名空間裡
不只有旗標。access mode(唯讀 / 唯寫 / 讀寫)是 code-owned 的,caller 永遠遞交不進來。
"""
from __future__ import annotations

import errno
import fcntl
import os
import stat
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
PROGRAM_CODE_DIR = REPO_ROOT / "program_code"
for _candidate in (HELPER_DIR, ML_TRAINING_DIR, PROGRAM_CODE_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import agent_governance_s2_4_journal as _journal  # noqa: E402
import agent_governance_s2_4_lock as _lock  # noqa: E402


class S2_4HostStorageError(RuntimeError):
    """本 driver 的 typed 契約層硬錯誤(帶 ``code``;絕不夾帶主機路徑或秘密片段)。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# flag 名 → ``os.O_*`` 的**封閉**映射(表外一律 typed 拒)。
_OPEN_FLAG_BITS = {
    "O_CLOEXEC": os.O_CLOEXEC,
    "O_CREAT": os.O_CREAT,
    "O_DIRECTORY": os.O_DIRECTORY,
    "O_EXCL": os.O_EXCL,
    "O_NOFOLLOW": os.O_NOFOLLOW,
}
# 「這個路徑不是一個(非 symlink 的)目錄」的兩個 errno。``O_DIRECTORY|O_NOFOLLOW`` 對 symlink
# 在 Linux 回 ``ELOOP``、在 darwin 回 ``ENOTDIR``(``O_DIRECTORY`` 先判),對一般檔兩者都回
# ``ENOTDIR``。這兩種**恰好就是** §5.2 要 typed 拒的形狀,故轉成一份「is_dir=False」的觀測讓
# 上層收成 ``PRECHECK_FAILED``。其餘 ``OSError``(``ENOENT`` / ``EACCES`` / ``EIO`` …)一律原樣
# 逸出:那些是「讀不到」,而「讀不到」不是「形狀不對」,更不是「乾淨」——上層會把它收成
# RECOVERY_REQUIRED 並記下 redact 過的類名。
_NOT_A_DIRECTORY_ERRNOS = (errno.ELOOP, errno.ENOTDIR)
# ``flock(LOCK_EX|LOCK_NB)`` 在「別人正持有」時的 errno(POSIX 允許兩者之一;BSD 另有 EACCES)。
_LOCK_CONTENDED_ERRNOS = (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES)


def _flag_bits(flags: Any, *, expected: tuple[str, ...]) -> int:
    """把 owner 模組宣告的 exact flag 元組折成旗標位元;非 exact 即 typed 拒。"""

    if tuple(flags or ()) != expected:
        raise S2_4HostStorageError("open_flags_are_not_the_declared_contract")
    bits = 0
    for name in expected:
        if name not in _OPEN_FLAG_BITS:
            raise S2_4HostStorageError("open_flag_outside_the_closed_table")
        bits |= _OPEN_FLAG_BITS[name]
    return bits


def _mode_text(st: os.stat_result) -> str:
    """``0700`` / ``0600`` 這種四位八進位字串(§5.2 的 mode 比對就是字串比對)。"""

    return f"{stat.S_IMODE(st.st_mode):04o}"


def _directory_observation(fd: Any, st: os.stat_result) -> dict[str, Any]:
    """``open_parent_directory`` / ``fstat_parent`` 的 exact 回傳形狀。

    誠實界線:``is_symlink`` 由 ``fstat`` 導出,而一個**已經開成功**的 fd 結構上不可能是
    symlink(``O_NOFOLLOW`` 在 open 那一刻就拒掉了)。所以這個欄位在成功路徑上恆為 ``False``,
    真正的 symlink 執法是那個旗標,不是這個欄位;被拒的路徑走
    :func:`_refused_directory_observation`,那裡才會回 ``is_symlink=True``。
    """

    return {
        "fd": fd,
        "device": int(st.st_dev),
        "inode": int(st.st_ino),
        "nlink": int(st.st_nlink),
        "mode": _mode_text(st),
        "uid": int(st.st_uid),
        "is_dir": stat.S_ISDIR(st.st_mode),
        "is_symlink": stat.S_ISLNK(st.st_mode),
    }


def _refused_directory_observation(path: str) -> dict[str, Any]:
    """``ELOOP``/``ENOTDIR`` 之後的觀測:沒有 fd、不是目錄 —— 上層收成 ``PRECHECK_FAILED``。

    ``is_symlink`` **不由 errno 推論**:同一個 symlink 在 Linux 上是 ``ELOOP``、在 darwin 上是
    ``ENOTDIR``,把平台差異推論成一個事實欄位會在其中一個平台上說謊。改為再做一次 ``lstat``
    ——它不跟隨 symlink,所以它說的是真話。``lstat`` 本身也失敗(競態、權限)時記 ``False``:
    「不知道」不冒充「是」,而該路徑無論如何已經因 ``is_dir=False`` 被 typed 拒。
    """

    is_symlink = False
    try:
        is_symlink = stat.S_ISLNK(os.lstat(path).st_mode)
    except OSError:
        is_symlink = False
    return {
        "fd": None,
        "device": None,
        "inode": None,
        "nlink": None,
        "mode": None,
        "uid": None,
        "is_dir": False,
        "is_symlink": bool(is_symlink),
    }


class _OwnedDescriptors:
    """只關自己開過的 fd。

    ``close(fd=…)`` 是 protocol 的一部分,而上層在 ``finally`` 裡對它非常寬容(失敗即吞掉)。
    若 driver 對任何整數都照關不誤,一次錯誤的 fd 記帳就會關掉行程裡別人的檔案描述子——包含
    ``0``/``1``/``2``。故本 driver 記住自己開過哪些,關陌生 fd 一律 typed 拒。
    """

    def __init__(self) -> None:
        self._open: set[int] = set()

    def track(self, fd: int) -> int:
        self._open.add(int(fd))
        return int(fd)

    def close(self, fd: Any) -> None:
        if type(fd) is not int or fd not in self._open:
            raise S2_4HostStorageError("close_of_a_descriptor_this_driver_never_opened")
        self._open.discard(fd)
        os.close(fd)

    def require(self, fd: Any) -> int:
        if type(fd) is not int or fd not in self._open:
            raise S2_4HostStorageError("descriptor_was_not_opened_by_this_driver")
        return fd

    @property
    def open_descriptors(self) -> tuple[int, ...]:
        return tuple(sorted(self._open))


class S2_4PosixFileDriver:
    """§5.2 ``DurableFileDriver`` 的 POSIX 實作(三本 WAL journal + replay ledger 共用一支)。

    落盤紀律由 :class:`agent_governance_s2_4_journal.JournalStore` 驅動,本 driver 只提供它
    要求的每一個系統呼叫:``openat`` 相對於已綁定的 dirfd、``fsync`` 檔案、``renameat`` 同
    parent(故恆為 same-filesystem atomic)、``fsync`` parent 目錄。
    """

    def __init__(self) -> None:
        self._fds = _OwnedDescriptors()

    # -- parent 目錄 --------------------------------------------------------- #
    def open_parent_directory(self, *, path: str, flags: tuple[str, ...]) -> dict[str, Any]:
        bits = _flag_bits(flags, expected=_journal.JOURNAL_PARENT_OPEN_FLAGS)
        try:
            fd = os.open(path, os.O_RDONLY | bits)
        except OSError as error:
            if error.errno in _NOT_A_DIRECTORY_ERRNOS:
                return _refused_directory_observation(path)
            raise
        return _directory_observation(self._fds.track(fd), os.fstat(fd))

    def fstat_parent(self, *, fd: Any) -> dict[str, Any]:
        owned = self._fds.require(fd)
        return _directory_observation(owned, os.fstat(owned))

    def list_journal_basenames(self, *, parent_fd: Any) -> list[str]:
        """**唯讀**列舉(只回 basename;沒有任何刪改面)。"""

        return sorted(os.listdir(self._fds.require(parent_fd)))

    # -- 暫存檔 → fsync → atomic rename → parent fsync ----------------------- #
    def create_temp_file(
        self, *, parent_fd: Any, basename: str, flags: tuple[str, ...], mode: int
    ) -> dict[str, Any]:
        """``openat(O_NOFOLLOW|O_CREAT|O_EXCL|O_CLOEXEC, 0600)``;EEXIST 原樣逸出。

        ``FileExistsError`` 是 :meth:`JournalStore.commit` **顯式**接住並轉成
        ``JOURNAL_TEMP_RESIDUE_RECOVERY_REQUIRED`` 的那一條;在此吞掉它會讓一次崩潰殘留變成
        一次無聲的覆寫。
        """

        owned_parent = self._fds.require(parent_fd)
        bits = _flag_bits(flags, expected=_journal.JOURNAL_TEMP_OPEN_FLAGS)
        if "/" in basename or basename in {"", ".", ".."}:
            raise S2_4HostStorageError("temp_basename_invalid")
        fd = os.open(basename, os.O_WRONLY | bits, mode, dir_fd=owned_parent)
        st = os.fstat(fd)
        return {
            "fd": self._fds.track(fd),
            "device": int(st.st_dev),
            "inode": int(st.st_ino),
            "nlink": int(st.st_nlink),
            "mode": _mode_text(st),
            "uid": int(st.st_uid),
            "is_regular_file": stat.S_ISREG(st.st_mode),
        }

    def write_bytes(self, *, fd: Any, payload: bytes) -> int:
        """寫到寫不動為止,回**實際**寫入的位元組數(短寫是上層要看見的事實)。

        單次 ``os.write`` 對一般檔通常一次寫完,但 POSIX 不保證;迴圈是正確的寫法。迴圈在
        ``os.write`` 回 0(無法再前進)時停下並回報**部分**計數 —— 絕不謊報成完整長度,因為
        ``JournalStore`` 正是靠 ``written != len(payload)`` 拒絕 rename 一份被截斷的 WAL。
        """

        owned = self._fds.require(fd)
        view = memoryview(bytes(payload))
        written = 0
        while written < len(view):
            step = os.write(owned, view[written:])
            if step <= 0:
                break
            written += step
        return written

    def fsync_file(self, *, fd: Any) -> None:
        os.fsync(self._fds.require(fd))

    def atomic_rename(self, *, parent_fd: Any, from_basename: str, to_basename: str) -> None:
        """``renameat(parent_fd, from, parent_fd, to)`` —— 同 parent ⇒ 恆為同檔案系統的原子置換。"""

        owned_parent = self._fds.require(parent_fd)
        for name in (from_basename, to_basename):
            if "/" in name or name in {"", ".", ".."}:
                raise S2_4HostStorageError("rename_basename_invalid")
        os.rename(
            from_basename, to_basename,
            src_dir_fd=owned_parent, dst_dir_fd=owned_parent,
        )

    def fsync_parent_dir(self, *, fd: Any) -> None:
        os.fsync(self._fds.require(fd))

    # -- 讀回 ---------------------------------------------------------------- #
    def read_journal_bytes(self, *, parent_fd: Any, basename: str) -> bytes | None:
        """讀回整份 journal/ledger;不存在回 ``None``(``ABSENT`` ≠ ``CORRUPT``)。"""

        owned_parent = self._fds.require(parent_fd)
        if "/" in basename or basename in {"", ".", ".."}:
            raise S2_4HostStorageError("read_basename_invalid")
        try:
            fd = os.open(
                basename, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=owned_parent
            )
        except FileNotFoundError:
            return None
        try:
            chunks: list[bytes] = []
            while True:
                chunk = os.read(fd, 1 << 16)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            os.close(fd)

    def close(self, *, fd: Any) -> None:
        self._fds.close(fd)

    @property
    def open_descriptors(self) -> tuple[int, ...]:
        """本 driver 目前還開著的 fd(洩漏檢查用;不是 protocol 的一部分)。"""

        return self._fds.open_descriptors


class S2_4PosixInstallLockDriver:
    """§5.2 ``InstallLockDriver`` 的 POSIX 實作。``flock`` 恆為 non-blocking exclusive。

    lock 檔以 ``O_CREAT`` 開(§5.2 明載)但**永不** unlink:一個被 unlink 的 lock 檔會讓下一個
    runner 建出**另一個 inode** 上的同名檔並成功 flock,兩個 writer 於是同時「持有」互斥鎖。
    本類別因此在結構上沒有任何 unlink/rename/chmod 面。
    """

    def __init__(self) -> None:
        self._fds = _OwnedDescriptors()

    def open_parent_directory(self, *, path: str, flags: tuple[str, ...]) -> dict[str, Any]:
        bits = _flag_bits(flags, expected=_lock.LOCK_PARENT_OPEN_FLAGS)
        try:
            fd = os.open(path, os.O_RDONLY | bits)
        except OSError as error:
            if error.errno in _NOT_A_DIRECTORY_ERRNOS:
                return _refused_directory_observation(path)
            raise
        return _directory_observation(self._fds.track(fd), os.fstat(fd))

    def fstat_parent(self, *, fd: Any) -> dict[str, Any]:
        owned = self._fds.require(fd)
        return _directory_observation(owned, os.fstat(owned))

    def openat_lock_file(
        self, *, parent_fd: Any, basename: str, flags: tuple[str, ...], mode: int
    ) -> dict[str, Any]:
        owned_parent = self._fds.require(parent_fd)
        bits = _flag_bits(flags, expected=_lock.LOCK_FILE_OPEN_FLAGS)
        if basename != _lock.INSTALL_LOCK_BASENAME:
            raise S2_4HostStorageError("install_lock_basename_is_not_the_declared_contract")
        # 誠實界線(S2E.2b-1 P2-6):``created`` 是一次 **TOCTOU 觀測**——``stat`` 與底下那次
        # ``open(O_CREAT)`` 之間,另一個 writer 可以建出或移走同名檔,故它只描述「stat 當下看到
        # 什麼」,不是「這次 open 真的建立了它」。它因此**只**落成 verdict 的資訊欄
        # (``lock_file_created``),不是任何閘;互斥完全由 ``flock(LOCK_EX|LOCK_NB)`` 買單,而
        # 本 driver 從不 unlink lock 檔,所以 inode 不會在兩個 writer 腳下被換掉。
        existed = True
        try:
            os.stat(basename, dir_fd=owned_parent, follow_symlinks=False)
        except FileNotFoundError:
            existed = False
        # ``flock`` 需要一個可用的 fd;讀寫模式與 lock 檔零位元組的內容無關(本 driver 從不
        # 寫入 lock 檔),但 ``O_RDWR`` 是 ``flock`` 在各實作上最不意外的開法。
        fd = os.open(basename, os.O_RDWR | bits, mode, dir_fd=owned_parent)
        return {"fd": self._fds.track(fd), "created": not existed}

    def fstat_lock_file(self, *, fd: Any) -> dict[str, Any]:
        owned = self._fds.require(fd)
        st = os.fstat(owned)
        return {
            "uid": int(st.st_uid),
            "gid": int(st.st_gid),
            "mode": _mode_text(st),
            "nlink": int(st.st_nlink),
            "device": int(st.st_dev),
            "inode": int(st.st_ino),
            "is_regular_file": stat.S_ISREG(st.st_mode),
        }

    def flock_exclusive_nonblocking(self, *, fd: Any) -> bool:
        """``LOCK_EX|LOCK_NB``;被別人持有回 ``False``(**絕不**阻塞,絕不重試)。"""

        owned = self._fds.require(fd)
        try:
            fcntl.flock(owned, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in _LOCK_CONTENDED_ERRNOS:
                return False
            raise
        return True

    def close(self, *, fd: Any) -> None:
        """關閉 fd —— 這同時**釋放** ``flock``(§5.2 的釋放路徑,永不 unlink)。"""

        self._fds.close(fd)

    @property
    def open_descriptors(self) -> tuple[int, ...]:
        return self._fds.open_descriptors
