"""S2.4(WP4·W4a)§5.2 durable WAL journal 的 focused 測試(§10.5 #7)。

證明:

- 三本 journal 的 exact 路徑導出(``s2-4-probe-`` / ``s2-4-prepare-`` / ``s2-4-`` 加 64 個小寫
  hex),畸形 id 一律 typed 拒且**永不**把 caller 字串 join 進 root;
- 八個 step state 的封閉詞彙(PREPARE 多 ``PREPARING``),越界 state / 亂序 seq / 未 fsync 皆拒;
- write-ahead 次序:``APPLYING`` **先** fsync 才有外部 effect,接著獨立再觀測,再 fsync
  ``APPLIED``(帶**觀測到的** digest),最後 ``VERIFYING``;
- **§10.5 #7 crash matrix**:effect 之前、effect 之後但觀測之前、觀測之後但 ``APPLIED``
  fsync 之前三個窗各自崩潰,持久化的 journal 停在哪一筆是確定的,且 :func:`reconcile_journal`
  由觀測態確定性收斂(續驗 / 該步未施作 / 逆序補償 / ``RECOVERY_REQUIRED`` 零變更);
- 截斷/畸形/checksum 不符的 bytes 一律 ``JOURNAL_CORRUPT_RECOVERY_REQUIRED``,且**絕不**被
  自動改名或覆寫(driver 上出現 unlink/truncate/rotate 面即 typed 拒);
- parent 置換、symlink parent、hardlink 暫存檔、跨裝置暫存一律 ``PRECHECK_FAILED``;
- ``driver=None`` 一律 typed ``EXTERNAL_VERIFICATION_PENDING`` 且零變更。

時間全部錨在凍結常量上(無 wall clock,故無日期腐化)。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
PROGRAM_CODE = ROOT / "program_code"
for candidate in (HELPERS, ML_ROOT, PROGRAM_CODE):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2_4_journal as journal  # noqa: E402
import agent_governance_s2_4_prepare as prepare  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402

_ANCHOR = datetime(2030, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
_HEX = "a" * 64
_PROBE_ID = journal.PROBE_ID_PREFIX + _HEX
_PREPARE_ID = journal.PREPARE_ID_PREFIX + _HEX
_PLAN_ID = journal.PLAN_ID_PREFIX + _HEX
_PLAN_CORE = "sha256:" + _HEX
_PRE = "sha256:" + "2" * 64
_POST = "sha256:" + "4" * 64
_ROLLBACK = "sha256:" + "3" * 64


def _clock(offset_seconds: float = 0.0):
    return lambda: _ANCHOR + timedelta(seconds=offset_seconds)


# ── in-memory 檔案系統 fake(真 openat/fsync/rename 屬 W6)──────────────────────
class FakeDurableFs:
    """注入的 :class:`agent_governance_s2_4_journal.DurableFileDriver` 實作。

    刻意**沒有** unlink/truncate/chmod 面(§5.2:journal 永不被自動改名或覆寫)。
    """

    def __init__(
        self,
        *,
        parent_mode: str = journal.JOURNAL_PARENT_MODE,
        parent_uid: int = 0,
        parent_is_dir: bool = True,
        parent_is_symlink: bool = False,
        parent_device: int = 66306,
        parent_inode: int = 4242,
        temp_device: int | None = None,
        temp_nlink: int = 1,
        temp_mode: str = journal.JOURNAL_FILE_MODE,
        temp_uid: int = 0,
        replace_parent_on_fstat: bool = False,
        short_write: bool = False,
    ) -> None:
        self.parent_mode = parent_mode
        self.parent_uid = parent_uid
        self.parent_is_dir = parent_is_dir
        self.parent_is_symlink = parent_is_symlink
        self.parent_device = parent_device
        self.parent_inode = parent_inode
        self.temp_device = temp_device if temp_device is not None else parent_device
        self.temp_nlink = temp_nlink
        self.temp_mode = temp_mode
        self.temp_uid = temp_uid
        self.replace_parent_on_fstat = replace_parent_on_fstat
        self.short_write = short_write
        self.files: dict[str, bytes] = {}
        self.temp_buffers: dict[int, bytes] = {}
        self.calls: list[str] = []
        self.fsynced_files: list[str] = []
        self.parent_fsyncs = 0
        self._fd = 100
        self._parent_opens = 0

    # -- parent --------------------------------------------------------------
    def _parent_stat(self, fd):
        return {
            "fd": fd,
            "device": self.parent_device,
            "inode": self.parent_inode,
            "nlink": 2,
            "mode": self.parent_mode,
            "uid": self.parent_uid,
            "is_dir": self.parent_is_dir,
            "is_symlink": self.parent_is_symlink,
        }

    def open_parent_directory(self, *, path, flags):
        assert flags == journal.JOURNAL_PARENT_OPEN_FLAGS, flags
        self.calls.append("open_parent_directory")
        self._parent_opens += 1
        self._fd += 1
        return self._parent_stat(self._fd)

    def fstat_parent(self, *, fd):
        self.calls.append("fstat_parent")
        if self.replace_parent_on_fstat:
            # rename 之前 parent 被換掉(device/inode 漂移)。
            self.parent_inode += 1
        return self._parent_stat(fd)

    # -- temp file -----------------------------------------------------------
    def create_temp_file(self, *, parent_fd, basename, flags, mode):
        assert flags == journal.JOURNAL_TEMP_OPEN_FLAGS, flags
        assert mode == journal.JOURNAL_FILE_MODE_BITS, oct(mode)
        assert "/" not in basename
        self.calls.append("create_temp_file")
        self._fd += 1
        self.temp_buffers[self._fd] = b""
        self._temp_names = getattr(self, "_temp_names", {})
        self._temp_names[self._fd] = basename
        return {
            "fd": self._fd,
            "device": self.temp_device,
            "inode": 9000 + self._fd,
            "nlink": self.temp_nlink,
            "mode": self.temp_mode,
            "uid": self.temp_uid,
            "is_regular_file": True,
        }

    def write_bytes(self, *, fd, payload):
        self.calls.append("write_bytes")
        self.temp_buffers[fd] = bytes(payload)
        return len(payload) - 1 if self.short_write else len(payload)

    def fsync_file(self, *, fd):
        self.calls.append("fsync_file")
        self.fsynced_files.append(self._temp_names[fd])

    def atomic_rename(self, *, parent_fd, from_basename, to_basename):
        self.calls.append("atomic_rename")
        for fd, name in self._temp_names.items():
            if name == from_basename:
                self.files[to_basename] = self.temp_buffers[fd]
                return
        raise AssertionError(f"no temp buffer for {from_basename}")

    def fsync_parent_dir(self, *, fd):
        self.calls.append("fsync_parent_dir")
        self.parent_fsyncs += 1

    def read_journal_bytes(self, *, parent_fd, basename):
        self.calls.append("read_journal_bytes")
        return self.files.get(basename)

    def close(self, *, fd):
        self.calls.append("close")


def _install_journal(entries, *, terminal=False):
    return journal.build_install_journal(
        plan_id=_PLAN_ID, plan_core_digest=_PLAN_CORE, idempotency_key=_PLAN_ID,
        expected_pre_state_digest=_PRE, aggregate_rollback_digest=_ROLLBACK,
        entries=entries, terminal=terminal,
    )


def _store(fs=None, *, path=None):
    return journal.JournalStore(
        fs if fs is not None else FakeDurableFs(),
        journal_path=path or journal.install_journal_path(_PLAN_ID),
    )


# ── §5.2 路徑導出 ───────────────────────────────────────────────────────────────
def test_three_journal_paths_derive_from_their_core_digest_ids() -> None:
    assert journal.probe_journal_path(_PROBE_ID) == (
        f"/var/lib/arcane-equilibrium/aiml/install/s2_4/probes/{_PROBE_ID}.probe.journal.json"
    )
    assert journal.prepare_journal_path(_PREPARE_ID) == (
        f"/var/lib/arcane-equilibrium/aiml/install/s2_4/prepared/"
        f"{_PREPARE_ID}.prepare.journal.json"
    )
    assert journal.install_journal_path(_PLAN_ID) == (
        f"/var/lib/arcane-equilibrium/aiml/install/s2_4/{_PLAN_ID}.journal.json"
    )
    # W3 的 prepare 葉自帶同一導出;兩者漂移即 W4 wave-exit 破。
    assert journal.prepare_journal_path(_PREPARE_ID) == prepare.prepare_journal_path(_PREPARE_ID)


@pytest.mark.parametrize(
    "bad",
    ["", "s2-4-probe-", "s2-4-probe-" + "A" * 64, "s2-4-probe-" + "a" * 63,
     "s2-4-probe-" + "a" * 64 + "/../../etc/passwd", None, 7],
)
def test_malformed_ids_never_reach_a_root_path(bad) -> None:
    for derive in (journal.probe_journal_path, journal.prepare_journal_path,
                   journal.install_journal_path):
        with pytest.raises(journal.JournalContractError):
            derive(bad)


def test_journal_temp_basename_refuses_a_caller_path_segment() -> None:
    assert journal.journal_temp_basename("x.json", attempt=2) == ".x.json.tmp.2"
    for bad in ("a/b", "", ".", ".."):
        with pytest.raises(journal.JournalContractError):
            journal.journal_temp_basename(bad)


# ── state 詞彙 + 兩道 digest ────────────────────────────────────────────────────
def test_step_state_vocabulary_is_the_exact_eight_plus_prepare_preparing() -> None:
    assert journal.JOURNAL_STATES == (
        "NOT_STARTED", "APPLYING", "APPLIED", "VERIFYING", "VERIFIED",
        "COMPENSATING", "COMPENSATED", "FAILED",
    )
    assert journal.journal_state_vocabulary("s2_4_install_journal_v1") == journal.JOURNAL_STATES
    assert journal.journal_state_vocabulary("s2_4_capability_probe_journal_v1") == (
        journal.JOURNAL_STATES
    )
    prepare_states = journal.journal_state_vocabulary("s2_4_prepare_journal_v1")
    assert "PREPARING" in prepare_states and set(journal.JOURNAL_STATES) <= set(prepare_states)
    with pytest.raises(journal.JournalContractError):
        journal.journal_state_vocabulary("something_else")


def test_canonical_self_digest_and_separate_outer_checksum_are_both_load_bearing() -> None:
    entry = {
        "seq": 0, "step_index": 0, "state": "APPLYING", "pre_state_digest": _PRE,
        "post_state_digest": _POST, "fsynced": True, "recorded_at": _ANCHOR.isoformat(),
    }
    sealed = _install_journal([entry])
    assert journal.journal_integrity_errors(sealed) == []
    assert sealed["self_digest"] != sealed["outer_checksum"]
    assert validator.validate_aiml_artifact(sealed) == []
    # 內容竄改 → 兩道都破;只改 self_digest → outer 仍抓到。
    body_tampered = dict(sealed, terminal=True)
    assert journal.journal_integrity_errors(body_tampered)
    digest_tampered = dict(sealed, self_digest="sha256:" + "0" * 64)
    assert any(
        "self_digest" in reason for reason in journal.journal_integrity_errors(digest_tampered)
    )


@pytest.mark.parametrize(
    "mutation",
    [
        {"state": "RUNNING"},          # 越界 state
        {"seq": 5},                    # 亂序 seq
        {"fsynced": False},            # 未 fsync 的 WAL entry
    ],
)
def test_entry_sequence_contract_rejects_out_of_vocabulary_or_unfsynced_entries(mutation) -> None:
    entry = {
        "seq": 0, "step_index": 0, "state": "APPLYING", "pre_state_digest": _PRE,
        "post_state_digest": _POST, "fsynced": True, "recorded_at": _ANCHOR.isoformat(),
    }
    entry.update(mutation)
    body = {
        "schema_version": "s2_4_install_journal_v1", "plan_id": _PLAN_ID,
        "plan_core_digest": _PLAN_CORE, "idempotency_key": _PLAN_ID,
        "expected_pre_state_digest": _PRE, "aggregate_rollback_digest": _ROLLBACK,
        "entries": [entry], "terminal": False,
        "journal_integrity": {
            "applying_fsynced_before_effect": True,
            "same_filesystem_atomic_rename": True,
            "file_fsynced": True, "parent_dir_fsynced": True,
        },
    }
    assert journal.journal_entry_sequence_errors(journal.seal_journal(body))


def test_install_journal_idempotency_key_must_be_the_plan_id() -> None:
    with pytest.raises(journal.JournalContractError):
        journal.build_install_journal(
            plan_id=_PLAN_ID, plan_core_digest=_PLAN_CORE,
            idempotency_key=journal.PLAN_ID_PREFIX + "b" * 64,
            expected_pre_state_digest=_PRE, aggregate_rollback_digest=_ROLLBACK,
            entries=[{
                "seq": 0, "step_index": 0, "state": "APPLYING", "pre_state_digest": _PRE,
                "post_state_digest": _POST, "fsynced": True,
                "recorded_at": _ANCHOR.isoformat(),
            }],
            terminal=False,
        )


# ── source lane / durability 紀律 ───────────────────────────────────────────────
def test_source_lane_driver_none_is_pending_with_zero_mutation() -> None:
    store = journal.JournalStore(None, journal_path=journal.install_journal_path(_PLAN_ID))
    for verdict in (store.commit(_install_journal([_applying_entry()])), store.load()):
        assert verdict["status"] == "EXTERNAL_VERIFICATION_PENDING"
        assert verdict["mutation_performed"] is False
        assert verdict["driver_engaged"] is False
        assert verdict["production_authority_flags"] == {
            "nine_authorities_false": True,
            "production_apply_performed": False,
            "running_attested": False,
        }


def _applying_entry(seq=0, step_index=0, pre=_PRE, post=_POST):
    return {
        "seq": seq, "step_index": step_index, "state": "APPLYING",
        "pre_state_digest": pre, "post_state_digest": post, "fsynced": True,
        "recorded_at": _ANCHOR.isoformat(),
    }


def test_commit_uses_same_filesystem_temp_fsync_atomic_rename_and_parent_fsync() -> None:
    fs = FakeDurableFs()
    store = _store(fs)
    verdict = store.commit(_install_journal([_applying_entry()]))
    assert verdict["status"] == "JOURNAL_COMMITTED"
    assert verdict["durability"] == {
        "same_filesystem_atomic_rename": True,
        "file_fsynced": True,
        "parent_dir_fsynced": True,
        "temp_basename": f".{_PLAN_ID}.journal.json.tmp.0",
    }
    # exact 次序:temp 建立 → 寫 → file fsync → parent 重驗 → rename → parent fsync。
    ordered = [call for call in fs.calls if call != "close"]
    assert ordered == [
        "open_parent_directory", "create_temp_file", "write_bytes", "fsync_file",
        "fstat_parent", "atomic_rename", "fsync_parent_dir",
    ]
    assert fs.parent_fsyncs == 1
    assert json.loads(fs.files[f"{_PLAN_ID}.journal.json"].decode("utf-8"))["plan_id"] == _PLAN_ID


@pytest.mark.parametrize(
    "kwargs,marker",
    [
        ({"parent_uid": 1000}, "not root-owned"),
        ({"parent_mode": "0777"}, "not the required"),
        ({"parent_is_symlink": True}, "is a symlink"),
        ({"parent_is_dir": False}, "is not a directory"),
        ({"temp_device": 999}, "different device"),
        ({"temp_nlink": 2}, "link count is not one"),
        ({"temp_mode": "0644"}, "mode is"),
        ({"temp_uid": 1000}, "not root-owned"),
        ({"replace_parent_on_fstat": True}, "was replaced"),
    ],
)
def test_hostile_parent_or_temp_file_is_precheck_failed_with_zero_persisted_bytes(
    kwargs, marker
) -> None:
    fs = FakeDurableFs(**kwargs)
    verdict = _store(fs).commit(_install_journal([_applying_entry()]))
    assert verdict["status"] == "PRECHECK_FAILED", verdict["reasons"]
    assert any(marker in reason for reason in verdict["reasons"]), verdict["reasons"]
    assert fs.files == {}
    assert verdict["mutation_performed"] is False


def test_short_write_is_never_renamed_into_place() -> None:
    fs = FakeDurableFs(short_write=True)
    verdict = _store(fs).commit(_install_journal([_applying_entry()]))
    assert verdict["status"] == "PRECHECK_FAILED"
    assert any("short" in reason for reason in verdict["reasons"])
    assert fs.files == {}


def test_a_journal_driver_exposing_unlink_or_truncate_is_rejected() -> None:
    class _Destructive(FakeDurableFs):
        def unlink(self, **_kwargs):  # pragma: no cover - 只需存在即被拒
            return None

    fs = _Destructive()
    assert journal.assert_no_journal_destructive_surface(fs)
    verdict = _store(fs).commit(_install_journal([_applying_entry()]))
    assert verdict["status"] == "PRECHECK_FAILED"
    assert any("never renamed away" in reason for reason in verdict["reasons"])
    assert fs.files == {}


def test_a_journal_that_does_not_rederive_its_digests_is_never_persisted() -> None:
    fs = FakeDurableFs()
    forged = dict(_install_journal([_applying_entry()]), terminal=True)
    verdict = _store(fs).commit(forged)
    assert verdict["status"] == "PRECHECK_FAILED"
    assert fs.files == {}


# ── 讀回 + JOURNAL_CORRUPT_RECOVERY_REQUIRED ───────────────────────────────────
def test_load_round_trips_a_committed_journal() -> None:
    fs = FakeDurableFs()
    store = _store(fs)
    sealed = _install_journal([_applying_entry()])
    assert store.commit(sealed)["status"] == "JOURNAL_COMMITTED"
    loaded = _store(fs).load()
    assert loaded["status"] == "JOURNAL_LOADED"
    assert loaded["journal"] == sealed


def test_absent_journal_is_typed_absent_not_corrupt() -> None:
    assert _store(FakeDurableFs()).load()["status"] == "JOURNAL_ABSENT"


@pytest.mark.parametrize(
    "payload",
    [
        b'{"schema_version": "s2_4_install_journal_v1", "entri',   # 截斷
        b"not json at all",                                        # 畸形
        b"\xff\xfe\x00",                                           # 非 UTF-8
    ],
)
def test_truncated_or_malformed_bytes_are_journal_corrupt_recovery_required(payload) -> None:
    fs = FakeDurableFs()
    fs.files[f"{_PLAN_ID}.journal.json"] = payload
    verdict = _store(fs).load()
    assert verdict["status"] == "JOURNAL_CORRUPT_RECOVERY_REQUIRED"
    assert verdict["journal"] is None
    # §5.2:絕不自動改名或覆寫——bytes 原樣留在原處。
    assert fs.files[f"{_PLAN_ID}.journal.json"] == payload
    assert "atomic_rename" not in fs.calls


def test_checksum_invalid_bytes_are_corrupt_and_left_untouched() -> None:
    fs = FakeDurableFs()
    store = _store(fs)
    sealed = _install_journal([_applying_entry()])
    store.commit(sealed)
    name = f"{_PLAN_ID}.journal.json"
    tampered = dict(json.loads(fs.files[name].decode("utf-8")))
    tampered["outer_checksum"] = "sha256:" + "0" * 64
    fs.files[name] = json.dumps(tampered).encode("utf-8")
    verdict = _store(fs).load()
    assert verdict["status"] == "JOURNAL_CORRUPT_RECOVERY_REQUIRED"
    assert any("outer_checksum" in reason for reason in verdict["reasons"])
    assert fs.files[name] == json.dumps(tampered).encode("utf-8")


# ── write-ahead 次序 ───────────────────────────────────────────────────────────
def _transaction(fs):
    store = _store(fs)
    return store, journal.WriteAheadTransaction(
        store,
        build_journal=lambda entries, terminal: _install_journal(entries, terminal=terminal),
        clock=_clock(),
    )


def test_write_ahead_step_fsyncs_applying_before_the_effect_then_records_the_observed_digest() -> None:
    fs = FakeDurableFs()
    _store_obj, txn = _transaction(fs)
    order: list[str] = []

    def effect():
        # APPLYING 必須已經落盤:磁碟上讀得到,且最後一筆 state == APPLYING。
        persisted = json.loads(fs.files[f"{_PLAN_ID}.journal.json"].decode("utf-8"))
        order.append("effect:" + persisted["entries"][-1]["state"])

    def observe():
        order.append("observe")
        return _POST

    outcome = txn.step(
        operation_id="publish-base-runtime", step_index=3, pre_state_digest=_PRE,
        expected_post_state_digest=_POST, effect=effect, observe=observe,
    )
    assert outcome["status"] == "JOURNAL_COMMITTED", outcome["reasons"]
    assert order == ["effect:APPLYING", "observe"]
    assert outcome["effect_executed"] and outcome["observed"] and outcome["applied_fsynced"]
    assert outcome["observed_post_state_digest"] == _POST
    assert [entry["state"] for entry in txn.entries] == ["APPLYING", "APPLIED", "VERIFYING"]
    assert [entry["step_index"] for entry in txn.entries] == [3, 3, 3]
    # 每一次轉移都是一次獨立的 durable commit(三次 rename + 三次 parent fsync)。
    assert fs.calls.count("atomic_rename") == 3 and fs.parent_fsyncs == 3


def test_an_observation_that_differs_from_the_plan_records_the_observed_digest_and_does_not_verify() -> None:
    fs = FakeDurableFs()
    _store_obj, txn = _transaction(fs)
    outcome = txn.step(
        operation_id="publish", step_index=0, pre_state_digest=_PRE,
        expected_post_state_digest=_POST, effect=lambda: None,
        observe=lambda: "sha256:" + "9" * 64,
    )
    assert outcome["status"] == "RECOVERY_REQUIRED"
    assert outcome["observed_post_state_digest"] == "sha256:" + "9" * 64
    assert [entry["state"] for entry in txn.entries] == ["APPLYING", "APPLIED"]
    assert txn.entries[-1]["post_state_digest"] == "sha256:" + "9" * 64


def test_an_unfsyncable_applying_record_never_lets_the_effect_run() -> None:
    fs = FakeDurableFs(parent_uid=1000)
    _store_obj, txn = _transaction(fs)
    ran: list[str] = []
    outcome = txn.step(
        operation_id="publish", step_index=0, pre_state_digest=_PRE,
        expected_post_state_digest=_POST, effect=lambda: ran.append("effect"),
        observe=lambda: _POST,
    )
    assert outcome["status"] == "PRECHECK_FAILED"
    assert ran == [] and fs.files == {}
    assert any("never attempted" in reason for reason in outcome["reasons"])


# ── §10.5 #7 crash matrix ──────────────────────────────────────────────────────
def _crash_at(window):
    def fault(current):
        if current == window:
            raise journal.JournalCrash(window)
    return fault


def test_crash_matrix_before_the_effect_leaves_applying_and_zero_effect() -> None:
    """窗 1:``APPLYING`` 已 fsync、外部 effect **尚未**發生。

    重啟後 journal 停在 APPLYING;觀測仍等於 pre-state → 該步標記未施作並安全續行。
    """

    fs = FakeDurableFs()
    _store_obj, txn = _transaction(fs)
    ran: list[str] = []
    with pytest.raises(journal.JournalCrash):
        txn.step(
            operation_id="publish", step_index=0, pre_state_digest=_PRE,
            expected_post_state_digest=_POST, effect=lambda: ran.append("effect"),
            observe=lambda: _POST, fault=_crash_at("pre_effect"),
        )
    assert ran == []
    persisted = _store(fs).load()
    assert persisted["status"] == "JOURNAL_LOADED"
    assert [entry["state"] for entry in persisted["journal"]["entries"]] == ["APPLYING"]
    verdict = journal.reconcile_journal(persisted["journal"], observed_state_digest=_PRE)
    assert verdict["status"] == "STEP_NOT_APPLIED_RESUME"
    assert verdict["mutation_performed"] is False


def test_crash_matrix_after_the_effect_but_before_observation_reconciles_from_observed_state() -> None:
    """窗 2:effect 已發生但尚未再觀測。

    journal 仍停在 APPLYING(§5.2:APPLYING 的崩潰**由觀測態**收斂,絕不盲目重放);
    觀測等於計畫 post-state → 續驗。
    """

    fs = FakeDurableFs()
    _store_obj, txn = _transaction(fs)
    ran: list[str] = []
    with pytest.raises(journal.JournalCrash):
        txn.step(
            operation_id="publish", step_index=0, pre_state_digest=_PRE,
            expected_post_state_digest=_POST, effect=lambda: ran.append("effect"),
            observe=lambda: _POST,
            fault=_crash_at("post_effect_pre_observation"),
        )
    assert ran == ["effect"]
    persisted = _store(fs).load()["journal"]
    assert [entry["state"] for entry in persisted["entries"]] == ["APPLYING"]
    assert journal.reconcile_journal(persisted, observed_state_digest=_POST)["status"] == (
        "RESUME_VERIFICATION"
    )


def test_crash_matrix_after_observation_but_before_the_applied_fsync_is_still_applying() -> None:
    """窗 3:已再觀測、``APPLIED`` **尚未** fsync。

    未 fsync 的 APPLIED 不存在於磁碟(WAL 不是事後日誌);收斂仍由觀測態決定。
    """

    fs = FakeDurableFs()
    _store_obj, txn = _transaction(fs)
    observed: list[str] = []
    with pytest.raises(journal.JournalCrash):
        txn.step(
            operation_id="publish", step_index=0, pre_state_digest=_PRE,
            expected_post_state_digest=_POST, effect=lambda: None,
            observe=lambda: (observed.append("observe"), _POST)[1],
            fault=_crash_at("post_observation_pre_applied_fsync"),
        )
    assert observed == ["observe"]
    persisted = _store(fs).load()["journal"]
    assert [entry["state"] for entry in persisted["entries"]] == ["APPLYING"]
    assert fs.calls.count("atomic_rename") == 1
    assert journal.reconcile_journal(persisted, observed_state_digest=_POST)["status"] == (
        "RESUME_VERIFICATION"
    )


def test_the_three_crash_windows_are_the_declared_fault_vocabulary() -> None:
    assert journal.WAL_FAULT_WINDOWS == (
        "pre_effect", "post_effect_pre_observation", "post_observation_pre_applied_fsync",
    )


# ── 確定性 reconcile ───────────────────────────────────────────────────────────
def test_reconcile_compensates_a_task_owned_partial_state_only_with_a_valid_journal_binding() -> None:
    persisted = _install_journal([_applying_entry()])
    ambiguous = journal.reconcile_journal(
        persisted, observed_state_digest="sha256:" + "7" * 64, task_owned_partial=True
    )
    assert ambiguous["status"] == "RECOVERY_REQUIRED"
    assert ambiguous["mutation_performed"] is False
    owned = journal.reconcile_journal(
        persisted, observed_state_digest="sha256:" + "7" * 64, task_owned_partial=True,
        ownership_evidence={
            "journal_subject": {
                "journal_digest": "sha256:" + "b" * 64,
                "s2_4_receipt_digest": "sha256:" + "c" * 64,
            }
        },
    )
    assert owned["status"] == "COMPENSATE_REVERSE_ORDER"


def test_reconcile_requires_an_independently_observed_digest() -> None:
    persisted = _install_journal([_applying_entry()])
    verdict = journal.reconcile_journal(persisted, observed_state_digest=None)
    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert any("independently observed" in reason for reason in verdict["reasons"])


def test_reconcile_of_a_malformed_journal_is_corrupt_and_starts_nothing() -> None:
    verdict = journal.reconcile_journal(
        dict(_install_journal([_applying_entry()]), terminal=True), observed_state_digest=_PRE
    )
    assert verdict["status"] == "JOURNAL_CORRUPT_RECOVERY_REQUIRED"
    assert verdict["mutation_performed"] is False


def test_a_terminal_journal_needs_no_reconcile() -> None:
    terminal = _install_journal(
        [
            _applying_entry(),
            {
                "seq": 1, "step_index": 0, "state": "VERIFIED", "pre_state_digest": _POST,
                "post_state_digest": _POST, "fsynced": True,
                "recorded_at": _ANCHOR.isoformat(),
            },
        ],
        terminal=True,
    )
    assert journal.reconcile_journal(terminal, observed_state_digest=_POST)["status"] == (
        "TERMINAL_NOTHING_TO_RECONCILE"
    )


# ── probe / prepare 兩本 journal 的 builder ────────────────────────────────────
def test_probe_and_prepare_journals_seal_and_validate_centrally() -> None:
    probe_journal = journal.build_probe_journal(
        probe_id=_PROBE_ID,
        derived_unit_name=f"arcane-aiml-s2-4-probe-{_HEX}.service",
        scope="PREPARE_SANDBOX",
        transient_unit_property_digest="sha256:" + "5" * 64,
        expected_invocation_id_pattern="^[0-9a-f]{32}$",
        cleanup_rollback_digest=_ROLLBACK,
        entries=[{
            "seq": 0, "state": "APPLYING", "pre_state_digest": _PRE,
            "post_state_digest": _POST, "fsynced": True, "recorded_at": _ANCHOR.isoformat(),
        }],
        terminal=False,
    )
    prepare_journal = journal.build_prepare_journal(
        prepare_id=_PREPARE_ID,
        staging_root=f"/var/lib/arcane-equilibrium/aiml/install/s2_4/prepared/{_PREPARE_ID}",
        entries=[{
            "seq": 0, "state": "PREPARING", "pre_state_digest": _PRE,
            "post_state_digest": _PRE, "fsynced": True, "recorded_at": _ANCHOR.isoformat(),
        }],
        terminal=False,
    )
    for artifact in (probe_journal, prepare_journal):
        assert journal.journal_integrity_errors(artifact) == []
        assert journal.journal_entry_sequence_errors(artifact) == []
        assert validator.validate_aiml_artifact(artifact) == []
    # PREPARE 的 durability 契約多一欄:PREPARING 於建立 staging 之前即 fsync。
    assert prepare_journal["journal_integrity"]["preparing_fsynced_before_staging_create"] is True
    assert probe_journal["journal_integrity"] == {
        "same_filesystem_atomic_rename": True, "file_fsynced": True, "parent_dir_fsynced": True,
    }


def test_journal_never_claims_production_or_running() -> None:
    verdict = _store(FakeDurableFs()).commit(_install_journal([_applying_entry()]))
    assert verdict["production_authority_flags"] == {
        "nine_authorities_false": True,
        "production_apply_performed": False,
        "running_attested": False,
    }
    projection = journal.journal_abi_projection()
    assert projection["journal_parent_mode"] == "0700"
    assert projection["journal_file_mode"] == "0600"
    assert "JOURNAL_CORRUPT_RECOVERY_REQUIRED" in projection["typed_statuses"]
