"""S2E.2b-1 C2:S2.4 §5.2 POSIX 檔案 / install-lock driver 的 focused 測試。

兩層,理由是 §5.2 的前置**要求 root**(journal parent 必須 uid 0 + mode 0700),而測試不是 root:

* **第一層(真 POSIX I/O)** —— 對真 tmp 目錄直接驅動 driver 自己的每一個方法:``openat`` 相對
  dirfd、``O_EXCL`` 的 EEXIST、短寫回報、``renameat``、``fsync``、唯讀列舉、讀回、fd 記帳。這一層
  不碰 uid 判準,故完全真實(沒有任何 stat 被偽造)。
* **第二層(``JournalStore`` 全鏈)** —— 以 test-only 子類別**只**把回報的 ``uid`` 改成 0
  (``mode`` 用真的 ``chmod 0700``/``0600``,不偽造),讓 §5.2 的 root-owned 前置成立,於是
  temp→fsync→rename→parent-fsync 全鏈與 ``load()`` 讀回可以跑在**真的檔案系統**上。子類別覆寫的是
  **公開 protocol 方法**,production 類別因此沒有為了測試而存在的任何縫。

另證:兩張 ``assert_no_*_surface`` 硬檢對本實作回空(結構上沒有 unlink/truncate/chmod/rename 面)。
"""
from __future__ import annotations

import errno
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
PROGRAM_CODE = ROOT / "program_code"
for candidate in (HELPERS, ML_ROOT, PROGRAM_CODE):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2_4_host_storage as storage  # noqa: E402
import agent_governance_s2_4_journal as journal  # noqa: E402
import agent_governance_s2_4_lock as lock  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402


_ANCHOR = datetime(2030, 1, 1, tzinfo=timezone.utc)
_HEX = "a" * 64
_PLAN_ID = journal.PLAN_ID_PREFIX + _HEX
_PLAN_CORE = "sha256:" + _HEX
_PRE = "sha256:" + "2" * 64
_POST = "sha256:" + "4" * 64
_ROLLBACK = "sha256:" + "3" * 64


def _entry(seq=0, state="APPLYING", pre=_PRE, post=_POST):
    return {
        "seq": seq, "step_index": 0, "state": state,
        "pre_state_digest": pre, "post_state_digest": post, "fsynced": True,
        "recorded_at": _ANCHOR.isoformat(),
        "entry_source": journal.ENTRY_SOURCE_AGGREGATE,
        "component_effect_class": "HOST_IDENTITY_INSTALL",
    }


def _install_journal(entries, *, terminal=False):
    return journal.build_install_journal(
        plan_id=_PLAN_ID, plan_core_digest=_PLAN_CORE, idempotency_key=_PLAN_ID,
        expected_pre_state_digest=_PRE, aggregate_rollback_digest=_ROLLBACK,
        entries=entries, terminal=terminal,
    )


@pytest.fixture()
def parent(tmp_path):
    """一個真的、mode 恰為 0700 的 parent 目錄(uid 是跑測試的人,見第二層說明)。"""

    directory = tmp_path / "s2_4"
    directory.mkdir()
    os.chmod(directory, 0o700)
    return directory


# --------------------------------------------------------------------------- #
# 第一層:真 POSIX I/O
# --------------------------------------------------------------------------- #
def test_open_parent_directory_binds_real_device_inode_mode_and_uid(parent):
    driver = storage.S2_4PosixFileDriver()
    observed = driver.open_parent_directory(
        path=str(parent), flags=journal.JOURNAL_PARENT_OPEN_FLAGS
    )
    real = os.stat(parent)
    assert observed["device"] == real.st_dev
    assert observed["inode"] == real.st_ino
    assert observed["mode"] == journal.JOURNAL_PARENT_MODE
    assert observed["uid"] == os.getuid()
    assert observed["is_dir"] is True
    assert observed["is_symlink"] is False
    # 同一個 fd 再 fstat 一次必得同一 inode(這正是 journal 葉 docstring 說的「套套邏輯」)。
    assert driver.fstat_parent(fd=observed["fd"])["inode"] == real.st_ino
    driver.close(fd=observed["fd"])
    assert driver.open_descriptors == ()


def test_a_symlinked_parent_is_reported_as_not_a_directory_not_as_an_exception(tmp_path):
    """``O_DIRECTORY|O_NOFOLLOW`` 的拒絕是 §5.2 明列的 PRECHECK_FAILED 形狀,不是「讀不到」。

    ``is_symlink`` 必須是 ``lstat`` 的真話而不是 errno 的推論:同一個 symlink 在 Linux 上是
    ``ELOOP``、在 darwin 上是 ``ENOTDIR``,推論會在其中一個平台上說謊(本測試在 darwin 上
    對前一版實作即為紅)。
    """

    real = tmp_path / "real"
    real.mkdir()
    os.chmod(real, 0o700)
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    driver = storage.S2_4PosixFileDriver()
    observed = driver.open_parent_directory(
        path=str(link), flags=journal.JOURNAL_PARENT_OPEN_FLAGS
    )
    assert observed["fd"] is None
    assert observed["is_dir"] is False
    assert observed["is_symlink"] is True
    # 上層據此收成 PRECHECK_FAILED(零變更),而不是 RECOVERY_REQUIRED。
    reasons = journal._parent_precheck_reasons(
        observed, path=str(link), expected_mode=journal.JOURNAL_PARENT_MODE
    )
    assert any("is a symlink" in reason for reason in reasons), reasons
    assert driver.open_descriptors == ()


def test_a_regular_file_as_parent_is_reported_as_not_a_directory(tmp_path):
    victim = tmp_path / "not-a-dir"
    victim.write_text("x", encoding="utf-8")
    driver = storage.S2_4PosixFileDriver()
    observed = driver.open_parent_directory(
        path=str(victim), flags=journal.JOURNAL_PARENT_OPEN_FLAGS
    )
    assert observed["fd"] is None and observed["is_dir"] is False
    assert observed["is_symlink"] is False


def test_an_unreadable_parent_is_an_exception_not_a_shape_claim(tmp_path):
    """``ENOENT`` 是「讀不到」;把它講成「形狀不對」會讓一個未知狀態變成一句確定的話。"""

    driver = storage.S2_4PosixFileDriver()
    with pytest.raises(OSError) as caught:
        driver.open_parent_directory(
            path=str(tmp_path / "nope"), flags=journal.JOURNAL_PARENT_OPEN_FLAGS
        )
    assert caught.value.errno == errno.ENOENT


def test_open_flags_must_be_the_exact_tuple_the_owner_module_declares(parent):
    driver = storage.S2_4PosixFileDriver()
    for bad in [(), ("O_DIRECTORY",), ("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC", "O_CREAT"),
                ("O_RDWR", "O_NOFOLLOW", "O_CLOEXEC")]:
        with pytest.raises(storage.S2_4HostStorageError) as caught:
            driver.open_parent_directory(path=str(parent), flags=bad)
        assert caught.value.code == "open_flags_are_not_the_declared_contract"
    # flag 名 → os.O_* 是一張封閉表:caller 的字串永遠不決定「去 os 上取哪個屬性」。
    assert set(storage._OPEN_FLAG_BITS) == {
        "O_CLOEXEC", "O_CREAT", "O_DIRECTORY", "O_EXCL", "O_NOFOLLOW"
    }
    assert set(journal.JOURNAL_PARENT_OPEN_FLAGS) <= set(storage._OPEN_FLAG_BITS)
    assert set(journal.JOURNAL_TEMP_OPEN_FLAGS) <= set(storage._OPEN_FLAG_BITS)
    assert set(lock.LOCK_PARENT_OPEN_FLAGS) <= set(storage._OPEN_FLAG_BITS)
    assert set(lock.LOCK_FILE_OPEN_FLAGS) <= set(storage._OPEN_FLAG_BITS)


def test_the_full_durable_write_sequence_lands_real_bytes(parent):
    driver = storage.S2_4PosixFileDriver()
    observed = driver.open_parent_directory(
        path=str(parent), flags=journal.JOURNAL_PARENT_OPEN_FLAGS
    )
    parent_fd = observed["fd"]
    temp = driver.create_temp_file(
        parent_fd=parent_fd, basename=".x.tmp", flags=journal.JOURNAL_TEMP_OPEN_FLAGS,
        mode=journal.JOURNAL_FILE_MODE_BITS,
    )
    assert temp["is_regular_file"] is True
    assert temp["nlink"] == 1
    assert temp["mode"] == journal.JOURNAL_FILE_MODE
    # 暫存檔與 parent 同裝置 ⇒ rename 恆為 same-filesystem atomic。
    assert temp["device"] == observed["device"]
    payload = b'{"hello":"world"}'
    assert driver.write_bytes(fd=temp["fd"], payload=payload) == len(payload)
    driver.fsync_file(fd=temp["fd"])
    driver.atomic_rename(parent_fd=parent_fd, from_basename=".x.tmp", to_basename="x.json")
    driver.fsync_parent_dir(fd=parent_fd)
    assert (parent / "x.json").read_bytes() == payload
    assert stat.S_IMODE((parent / "x.json").stat().st_mode) == journal.JOURNAL_FILE_MODE_BITS
    assert driver.read_journal_bytes(parent_fd=parent_fd, basename="x.json") == payload
    assert driver.read_journal_bytes(parent_fd=parent_fd, basename="absent.json") is None
    assert driver.list_journal_basenames(parent_fd=parent_fd) == ["x.json"]
    driver.close(fd=temp["fd"])
    driver.close(fd=parent_fd)
    assert driver.open_descriptors == ()


def test_o_excl_surfaces_the_stranded_temp_file_instead_of_overwriting_it(parent):
    """§5.2 的 EEXIST 必須原樣逸出:吞掉它等於把一次崩潰殘留變成一次無聲覆寫。"""

    (parent / ".x.tmp").write_bytes(b"residue of an interrupted write")
    driver = storage.S2_4PosixFileDriver()
    parent_fd = driver.open_parent_directory(
        path=str(parent), flags=journal.JOURNAL_PARENT_OPEN_FLAGS
    )["fd"]
    with pytest.raises(FileExistsError):
        driver.create_temp_file(
            parent_fd=parent_fd, basename=".x.tmp",
            flags=journal.JOURNAL_TEMP_OPEN_FLAGS, mode=journal.JOURNAL_FILE_MODE_BITS,
        )
    assert (parent / ".x.tmp").read_bytes() == b"residue of an interrupted write"
    # 唯讀列舉是唯一還看得見擱淺暫存檔的面(E16)。
    assert driver.list_journal_basenames(parent_fd=parent_fd) == [".x.tmp"]
    driver.close(fd=parent_fd)


@pytest.mark.parametrize("bad", ["a/b", "", ".", ".."])
def test_a_caller_path_segment_never_reaches_a_syscall(parent, bad):
    driver = storage.S2_4PosixFileDriver()
    parent_fd = driver.open_parent_directory(
        path=str(parent), flags=journal.JOURNAL_PARENT_OPEN_FLAGS
    )["fd"]
    with pytest.raises(storage.S2_4HostStorageError):
        driver.create_temp_file(
            parent_fd=parent_fd, basename=bad, flags=journal.JOURNAL_TEMP_OPEN_FLAGS,
            mode=journal.JOURNAL_FILE_MODE_BITS,
        )
    with pytest.raises(storage.S2_4HostStorageError):
        driver.read_journal_bytes(parent_fd=parent_fd, basename=bad)
    with pytest.raises(storage.S2_4HostStorageError):
        driver.atomic_rename(parent_fd=parent_fd, from_basename=bad, to_basename="x.json")
    driver.close(fd=parent_fd)


def test_write_bytes_loops_until_done_and_reports_the_truly_written_count(parent, monkeypatch):
    """短寫是 ``JournalStore`` 拒絕 rename 一份被截斷 WAL 的唯一訊號,故它必須是**真實**計數。

    ``os.write`` 對一般檔通常一次寫完,POSIX 不保證;因此需要迴圈,而迴圈**不得**因為「我打算
    寫這麼多」就回報完整長度。兩個斷言各殺一種寫法:單次 ``os.write``(不續寫)、以及
    ``return len(payload)``(謊報)。
    """

    driver = storage.S2_4PosixFileDriver()
    parent_fd = driver.open_parent_directory(
        path=str(parent), flags=journal.JOURNAL_PARENT_OPEN_FLAGS
    )["fd"]
    temp = driver.create_temp_file(
        parent_fd=parent_fd, basename=".w.tmp", flags=journal.JOURNAL_TEMP_OPEN_FLAGS,
        mode=journal.JOURNAL_FILE_MODE_BITS,
    )
    payload = b"0123456789"
    real_write = os.write
    requested: list[int] = []

    def _three_bytes_at_a_time(fd, data):
        requested.append(len(data))
        return real_write(fd, bytes(data)[:3])

    monkeypatch.setattr(os, "write", _three_bytes_at_a_time)
    chunked_total = driver.write_bytes(fd=temp["fd"], payload=payload)
    monkeypatch.setattr(os, "write", lambda fd, data: 0)
    stalled_total = driver.write_bytes(fd=temp["fd"], payload=payload)
    monkeypatch.undo()

    assert chunked_total == len(payload)
    assert requested == [10, 7, 4, 1], "單次 os.write 寫不完時必須續寫"
    assert stalled_total == 0, "寫不動時回報的是實際寫入量,不是打算寫入量"
    driver.close(fd=temp["fd"])
    driver.close(fd=parent_fd)
    assert (parent / ".w.tmp").read_bytes() == payload


def test_the_driver_only_closes_descriptors_it_opened(parent):
    """陌生 fd 一律 typed 拒:上層的 ``finally`` 對 close 失敗非常寬容,一次錯誤的 fd 記帳
    會關掉行程裡別人的檔案描述子(含 0/1/2)。"""

    driver = storage.S2_4PosixFileDriver()
    for foreign in (0, 1, 2, 999, None, "3"):
        with pytest.raises(storage.S2_4HostStorageError) as caught:
            driver.close(fd=foreign)
        assert caught.value.code == "close_of_a_descriptor_this_driver_never_opened"
    parent_fd = driver.open_parent_directory(
        path=str(parent), flags=journal.JOURNAL_PARENT_OPEN_FLAGS
    )["fd"]
    driver.close(fd=parent_fd)
    # 關過的 fd 立刻失效(double close 會關到之後被重用的號碼)。
    with pytest.raises(storage.S2_4HostStorageError):
        driver.close(fd=parent_fd)
    with pytest.raises(storage.S2_4HostStorageError):
        driver.fstat_parent(fd=parent_fd)


def test_neither_driver_exposes_a_destructive_surface():
    file_driver = storage.S2_4PosixFileDriver()
    lock_driver = storage.S2_4PosixInstallLockDriver()
    assert journal.assert_no_journal_destructive_surface(file_driver) == []
    assert lock.assert_no_lock_unlink_surface(lock_driver) == []
    # 兩張禁面表逐名比對(反例:任何一個名字出現在實作上,上面兩道就會回非空)。
    for name in journal.FORBIDDEN_JOURNAL_METHODS:
        assert not callable(getattr(file_driver, name, None)), name
    for name in lock.FORBIDDEN_LOCK_METHODS:
        assert not callable(getattr(lock_driver, name, None)), name


# --------------------------------------------------------------------------- #
# 第一層:install lock
# --------------------------------------------------------------------------- #
def test_the_lock_is_created_once_and_flock_is_exclusive_and_non_blocking(parent):
    first = storage.S2_4PosixInstallLockDriver()
    parent_fd = first.open_parent_directory(
        path=str(parent), flags=lock.LOCK_PARENT_OPEN_FLAGS
    )["fd"]
    opened = first.openat_lock_file(
        parent_fd=parent_fd, basename=lock.INSTALL_LOCK_BASENAME,
        flags=lock.LOCK_FILE_OPEN_FLAGS, mode=lock.LOCK_FILE_MODE_BITS,
    )
    assert opened["created"] is True
    observed = first.fstat_lock_file(fd=opened["fd"])
    assert observed["is_regular_file"] is True
    assert observed["mode"] == lock.LOCK_FILE_MODE
    assert observed["nlink"] == 1
    assert first.flock_exclusive_nonblocking(fd=opened["fd"]) is True

    # 第二個 open file description 上的 LOCK_EX|LOCK_NB 必須**立刻**回 False,絕不阻塞。
    second = storage.S2_4PosixInstallLockDriver()
    second_parent = second.open_parent_directory(
        path=str(parent), flags=lock.LOCK_PARENT_OPEN_FLAGS
    )["fd"]
    contended = second.openat_lock_file(
        parent_fd=second_parent, basename=lock.INSTALL_LOCK_BASENAME,
        flags=lock.LOCK_FILE_OPEN_FLAGS, mode=lock.LOCK_FILE_MODE_BITS,
    )
    assert contended["created"] is False
    assert second.flock_exclusive_nonblocking(fd=contended["fd"]) is False

    # 釋放 = 關 fd(§5.2 永不 unlink);釋放後同一把鎖可以再被取得,且 lock 檔仍在。
    first.close(fd=opened["fd"])
    assert second.flock_exclusive_nonblocking(fd=contended["fd"]) is True
    assert (parent / lock.INSTALL_LOCK_BASENAME).exists()
    second.close(fd=contended["fd"])
    second.close(fd=second_parent)
    first.close(fd=parent_fd)


def test_the_lock_basename_is_the_declared_contract_not_a_caller_string(parent):
    driver = storage.S2_4PosixInstallLockDriver()
    parent_fd = driver.open_parent_directory(
        path=str(parent), flags=lock.LOCK_PARENT_OPEN_FLAGS
    )["fd"]
    with pytest.raises(storage.S2_4HostStorageError) as caught:
        driver.openat_lock_file(
            parent_fd=parent_fd, basename="something-else.lock",
            flags=lock.LOCK_FILE_OPEN_FLAGS, mode=lock.LOCK_FILE_MODE_BITS,
        )
    assert caught.value.code == "install_lock_basename_is_not_the_declared_contract"
    assert not (parent / "something-else.lock").exists()
    driver.close(fd=parent_fd)


# --------------------------------------------------------------------------- #
# 第二層:JournalStore / replay-ledger 全鏈跑在真檔案系統上
# --------------------------------------------------------------------------- #
class _RootOwnedFileDriver(storage.S2_4PosixFileDriver):
    """**test-only** 子類別:只把回報的 ``uid`` 改成 0。

    §5.2 要求 journal parent 是 root-owned 的;測試不是 root,而 ``chown`` 到 uid 0 需要
    root。mode 用真的 ``chmod``(0700/0600)不偽造,device/inode/nlink 全部是真的 ``fstat``,
    所以除了 uid 這一欄以外,整條鏈跑的都是真的檔案系統語義。覆寫的是**公開 protocol 方法**,
    production 類別因此沒有任何為了測試而開的縫。
    """

    def open_parent_directory(self, *, path, flags):
        observed = super().open_parent_directory(path=path, flags=flags)
        if observed["fd"] is not None:
            observed["uid"] = 0
        return observed

    def fstat_parent(self, *, fd):
        return dict(super().fstat_parent(fd=fd), uid=0)

    def create_temp_file(self, *, parent_fd, basename, flags, mode):
        return dict(
            super().create_temp_file(
                parent_fd=parent_fd, basename=basename, flags=flags, mode=mode
            ),
            uid=0,
        )


def _store(parent, basename):
    return journal.JournalStore(
        _RootOwnedFileDriver(), journal_path=f"{parent}/{basename}"
    )


def test_journal_store_commit_and_load_round_trip_on_a_real_filesystem(parent):
    store = _store(parent, f"{_PLAN_ID}.journal.json")
    sealed = _install_journal([_entry()])
    verdict = store.commit(sealed)
    assert verdict["status"] == journal.JOURNAL_STATUS_COMMITTED, verdict["reasons"]
    assert verdict["mutation_performed"] is True
    assert verdict["durability"] == {
        "same_filesystem_atomic_rename": True, "file_fsynced": True,
        "parent_dir_fsynced": True, "temp_basename": verdict["durability"]["temp_basename"],
    }
    landed = parent / f"{_PLAN_ID}.journal.json"
    assert landed.read_bytes() == validator._canonical_bytes(sealed)
    assert stat.S_IMODE(landed.stat().st_mode) == journal.JOURNAL_FILE_MODE_BITS
    # 暫存檔不留在磁碟上(rename 把它消耗掉了)。
    assert sorted(p.name for p in parent.iterdir()) == [f"{_PLAN_ID}.journal.json"]

    read = _store(parent, f"{_PLAN_ID}.journal.json").load()
    assert read["status"] == journal.JOURNAL_STATUS_LOADED, read["reasons"]
    assert read["journal"] == sealed
    assert store.driver.open_descriptors == ()


def test_an_absent_journal_is_absent_and_a_truncated_one_is_corrupt(parent):
    assert _store(parent, "absent.journal.json").load()["status"] == (
        journal.JOURNAL_STATUS_ABSENT
    )
    sealed = _install_journal([_entry()])
    (parent / "torn.journal.json").write_bytes(
        validator._canonical_bytes(sealed)[: -10]
    )
    verdict = _store(parent, "torn.journal.json").load()
    assert verdict["status"] == journal.JOURNAL_STATUS_CORRUPT
    # §5.2:壞掉的 journal 絕不被自動改名或覆寫 —— 位元組原封不動留在磁碟上。
    assert (parent / "torn.journal.json").stat().st_size == (
        len(validator._canonical_bytes(sealed)) - 10
    )


def test_a_short_write_never_renames_a_truncated_wal(parent):
    class _ShortWriter(_RootOwnedFileDriver):
        def write_bytes(self, *, fd, payload):
            return super().write_bytes(fd=fd, payload=payload[:-1])

    store = journal.JournalStore(
        _ShortWriter(), journal_path=f"{parent}/{_PLAN_ID}.journal.json"
    )
    verdict = store.commit(_install_journal([_entry()]))
    assert verdict["status"] == journal.JOURNAL_STATUS_PRECHECK_FAILED
    assert verdict["mutation_performed"] is False
    assert not (parent / f"{_PLAN_ID}.journal.json").exists()
    # 未被 rename 的暫存檔留在磁碟上,而 §5.2 不給任何 unlink 面:它由列舉面被看見。
    residue = [p.name for p in parent.iterdir()]
    assert len(residue) == 1
    assert journal.JOURNAL_TEMP_RESIDUE_RE.fullmatch(residue[0]), residue


def test_a_replaced_parent_between_binding_and_rename_is_precheck_failed(parent, tmp_path):
    store = _store(parent, f"{_PLAN_ID}.journal.json")
    first = store.commit(_install_journal([_entry()]))
    assert first["status"] == journal.JOURNAL_STATUS_COMMITTED
    # 把 parent **路徑**換成另一個目錄(fd 仍釘住舊 inode;唯有重新解析看得見)。
    swapped = tmp_path / "swapped"
    swapped.mkdir()
    os.chmod(swapped, 0o700)
    os.rename(parent, tmp_path / "moved-away")
    os.rename(swapped, parent)
    verdict = store.commit(_install_journal([_entry(), _entry(seq=1, state="APPLIED")]))
    assert verdict["status"] == journal.JOURNAL_STATUS_PRECHECK_FAILED
    assert verdict["mutation_performed"] is False
    # 有牙齒的偵測是「重新解析路徑並與綁定的 device/inode 比對」;先命中的是 ``_open_parent``
    # 的那一道(rename 前的 ``_reresolve_parent_reasons`` 是同一個判準的第二道)。
    assert any("replace" in reason for reason in verdict["reasons"]), verdict["reasons"]


def test_the_same_file_driver_carries_the_replay_ledger(parent):
    """§9.1 ledger 與三本 journal 共用同一支 ``DurableFileDriver``(``install_driver`` 只取一次)。"""

    ledger_path = f"{parent}/{lock.REPLAY_LEDGER_PATH.rsplit('/', 1)[-1]}"
    ledger = lock.append_replay_entries(
        lock.empty_replay_ledger(ledger_path=ledger_path),
        [{
            "authorization_id": "sha256:" + "1" * 64,
            "self_digest": "sha256:" + "1" * 63 + "a",
            "profile_identity": "aiml-s2-capability-probe-operator-v1",
        }],
        consumed_at=_ANCHOR.isoformat(), ledger_path=ledger_path,
    )
    assert validator.validate_aiml_artifact(ledger) == []
    store = journal.JournalStore(_RootOwnedFileDriver(), journal_path=ledger_path)
    assert lock._commit_durable_ledger(store, ledger)["status"] == (
        journal.JOURNAL_STATUS_COMMITTED
    )
    read = lock._read_durable_ledger(
        journal.JournalStore(_RootOwnedFileDriver(), journal_path=ledger_path),
        ledger_path=ledger_path,
    )
    assert read["status"] == "LEDGER_LOADED", read["reasons"]
    assert read["ledger"] == ledger
    assert json.loads(Path(ledger_path).read_text(encoding="utf-8"))["append_only"] is True


def test_the_acquire_contract_runs_end_to_end_against_a_real_flock(parent, monkeypatch):
    """``acquire_s2_4_install_lock`` 的固定順序跑在真 ``flock`` 上:取得 → 競爭 → 釋放 → 再取得。"""

    class _RootOwnedLockDriver(storage.S2_4PosixInstallLockDriver):
        # 同 _RootOwnedFileDriver:只把 uid 改成 0(mode 是真的 chmod 出來的)。
        def open_parent_directory(self, *, path, flags):
            observed = super().open_parent_directory(path=path, flags=flags)
            if observed["fd"] is not None:
                observed["uid"] = 0
            return observed

        def fstat_lock_file(self, *, fd):
            return dict(super().fstat_lock_file(fd=fd), uid=0)

    monkeypatch.setattr(lock, "INSTALL_LOCK_PARENT", str(parent))
    holder = _RootOwnedLockDriver()
    acquired = lock.acquire_s2_4_install_lock(holder)
    assert acquired["status"] == lock.LOCK_STATUS_ACQUIRED, acquired["reasons"]
    assert lock.install_lock_is_held(acquired) is True

    contender = _RootOwnedLockDriver()
    contended = lock.acquire_s2_4_install_lock(contender)
    assert contended["status"] == lock.LOCK_STATUS_HELD
    assert contended["mutation_performed"] is False
    assert contender.open_descriptors == (), "競爭路徑必須把 lock fd 關掉(否則重試會耗盡 NOFILE)"

    released = lock.release_s2_4_install_lock(holder, acquired)
    assert released["status"] == lock.LOCK_STATUS_RELEASED
    assert released["lock_unlinked"] is False
    assert lock.install_lock_is_held(acquired) is False
    assert (parent / lock.INSTALL_LOCK_BASENAME).exists()

    again = lock.acquire_s2_4_install_lock(_RootOwnedLockDriver())
    assert again["status"] == lock.LOCK_STATUS_ACQUIRED
    assert again["lock_file_created"] is False
