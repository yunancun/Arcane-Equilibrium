"""S2.4(WP4·W4a)§5.2 install lock 與 §9.1 replay-ledger **append** 的 focused 測試。

證明:

- exact 取得契約:parent 以 ``O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC`` 開啟並綁 device/inode/mode,
  lock 以 ``openat(O_NOFOLLOW|O_CREAT|O_CLOEXEC, 0600)`` 開,``fstat`` 必須證明 root-owned
  一般檔 / mode ``0600`` / link count 一 / 期望 device,**才**做 non-blocking exclusive ``flock``;
- 競爭 → ``INSTALL_LOCK_HELD`` 且零 install 變更;symlink、hardlink、被置換的 parent、寬鬆
  ownership/mode → ``PRECHECK_FAILED``;lock **永不** unlink(driver 上出現該面即 typed 拒);
- ``driver=None`` → typed ``EXTERNAL_VERIFICATION_PENDING`` 且零變更;
- replay append 只在**持有 lock** 且以 lock 下讀到的 durable ledger head 裁決後才發生;
  entry hash-chained + fsynced;同 key 同 plan 的 replay 成功且**不**重複 append;同 key 綁不同
  plan 一律 ``AUTHORIZATION_REJECTED``(§10.5 #8);atomic 消費是全有全無。

時間全部錨在凍結常量上(無 wall clock,故無日期腐化)。
"""
from __future__ import annotations

import json
import sys
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
import agent_governance_s2_4_lock as lock  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402
import s2_4_w3b_testkit as kit  # noqa: E402
from test_agent_governance_s2_4_journal import FakeDurableFs  # noqa: E402


# ── install lock fake ──────────────────────────────────────────────────────────
class FakeLockDriver:
    """注入的 :class:`agent_governance_s2_4_lock.InstallLockDriver`;無 unlink/chmod 面。"""

    def __init__(
        self,
        *,
        parent_uid: int = 0,
        parent_mode: str = "0755",
        parent_is_dir: bool = True,
        parent_is_symlink: bool = False,
        parent_device: int = 66306,
        parent_inode: int = 555,
        lock_uid: int = 0,
        lock_mode: str = lock.LOCK_FILE_MODE,
        lock_nlink: int = 1,
        lock_device: int | None = None,
        lock_is_regular: bool = True,
        flock_succeeds: bool = True,
        replace_parent_on_fstat: bool = False,
    ) -> None:
        self.parent_uid = parent_uid
        self.parent_mode = parent_mode
        self.parent_is_dir = parent_is_dir
        self.parent_is_symlink = parent_is_symlink
        self.parent_device = parent_device
        self.parent_inode = parent_inode
        self.lock_uid = lock_uid
        self.lock_mode = lock_mode
        self.lock_nlink = lock_nlink
        self.lock_device = lock_device if lock_device is not None else parent_device
        self.lock_is_regular = lock_is_regular
        self.flock_succeeds = flock_succeeds
        self.replace_parent_on_fstat = replace_parent_on_fstat
        self.calls: list[str] = []
        self.closed: list[int] = []

    def _parent(self, fd):
        return {
            "fd": fd, "device": self.parent_device, "inode": self.parent_inode, "nlink": 2,
            "mode": self.parent_mode, "uid": self.parent_uid, "is_dir": self.parent_is_dir,
            "is_symlink": self.parent_is_symlink,
        }

    def open_parent_directory(self, *, path, flags):
        assert path == lock.INSTALL_LOCK_PARENT, path
        assert flags == lock.LOCK_PARENT_OPEN_FLAGS, flags
        self.calls.append("open_parent_directory")
        return self._parent(10)

    def fstat_parent(self, *, fd):
        self.calls.append("fstat_parent")
        if self.replace_parent_on_fstat:
            self.parent_inode += 1
        return self._parent(fd)

    def openat_lock_file(self, *, parent_fd, basename, flags, mode):
        assert basename == lock.INSTALL_LOCK_BASENAME, basename
        assert flags == lock.LOCK_FILE_OPEN_FLAGS, flags
        assert mode == lock.LOCK_FILE_MODE_BITS, oct(mode)
        self.calls.append("openat_lock_file")
        return {"fd": 11, "created": True}

    def fstat_lock_file(self, *, fd):
        self.calls.append("fstat_lock_file")
        return {
            "uid": self.lock_uid, "gid": 0, "mode": self.lock_mode, "nlink": self.lock_nlink,
            "device": self.lock_device, "inode": 777,
            "is_regular_file": self.lock_is_regular,
        }

    def flock_exclusive_nonblocking(self, *, fd):
        self.calls.append("flock_exclusive_nonblocking")
        return self.flock_succeeds

    def close(self, *, fd):
        self.calls.append("close")
        self.closed.append(fd)


# ── §5.2 install lock ──────────────────────────────────────────────────────────
def test_lock_path_is_the_exact_run_lock_basename() -> None:
    assert lock.INSTALL_LOCK_PATH == (
        "/run/lock/arcane-equilibrium-aiml-s2-4-install.lock"
    )
    assert lock.INSTALL_LOCK_PARENT == "/run/lock"
    assert lock.INSTALL_LOCK_BASENAME == "arcane-equilibrium-aiml-s2-4-install.lock"


def test_source_lane_driver_none_is_pending_with_zero_mutation() -> None:
    verdict = lock.acquire_s2_4_install_lock(None)
    assert verdict["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert verdict["mutation_performed"] is False
    assert verdict["driver_engaged"] is False
    assert verdict["lock_file_created"] is False
    assert verdict["lock_unlinked"] is False
    assert verdict["production_authority_flags"] == {
        "nine_authorities_false": True,
        "production_apply_performed": False,
        "running_attested": False,
    }


def test_clean_acquisition_follows_the_exact_flag_and_fstat_order() -> None:
    driver = FakeLockDriver()
    verdict = lock.acquire_s2_4_install_lock(driver)
    assert verdict["status"] == "INSTALL_LOCK_ACQUIRED", verdict["reasons"]
    assert verdict["lock_fd"] == 11
    assert verdict["bound_parent"] == {"device": 66306, "inode": 555, "mode": "0755"}
    assert verdict["lock_unlinked"] is False
    # fstat 四項證明必在 flock **之前**;parent 置換重驗亦在 flock 之前。
    assert [call for call in driver.calls if call != "close"] == [
        "open_parent_directory", "openat_lock_file", "fstat_lock_file", "fstat_parent",
        "flock_exclusive_nonblocking",
    ]


def test_contention_returns_install_lock_held_with_zero_mutation() -> None:
    driver = FakeLockDriver(flock_succeeds=False)
    verdict = lock.acquire_s2_4_install_lock(driver)
    assert verdict["status"] == "INSTALL_LOCK_HELD"
    assert verdict["mutation_performed"] is False
    assert verdict["lock_unlinked"] is False
    assert any("already owns" in reason for reason in verdict["reasons"])


@pytest.mark.parametrize(
    "kwargs,marker",
    [
        ({"parent_uid": 1000}, "not root-owned"),
        ({"parent_mode": "1777"}, "permissive"),
        ({"parent_is_symlink": True}, "is a symlink"),
        ({"parent_is_dir": False}, "is not a directory"),
        ({"lock_is_regular": False}, "not a regular file"),
        ({"lock_uid": 1000}, "not root-owned"),
        ({"lock_mode": "0644"}, "mode is"),
        ({"lock_nlink": 2}, "link count is not one"),
        ({"lock_device": 999}, "bound parent device"),
        ({"replace_parent_on_fstat": True}, "was replaced"),
    ],
)
def test_hostile_lock_or_parent_is_precheck_failed_before_any_flock(kwargs, marker) -> None:
    driver = FakeLockDriver(**kwargs)
    verdict = lock.acquire_s2_4_install_lock(driver)
    assert verdict["status"] == "PRECHECK_FAILED", verdict["reasons"]
    assert any(marker in reason for reason in verdict["reasons"]), verdict["reasons"]
    assert verdict["mutation_performed"] is False
    assert "flock_exclusive_nonblocking" not in driver.calls


def test_a_lock_driver_exposing_unlink_is_rejected_and_never_engaged() -> None:
    class _Unlinker(FakeLockDriver):
        def unlink(self, **_kwargs):  # pragma: no cover - 只需存在即被拒
            return None

    driver = _Unlinker()
    assert lock.assert_no_lock_unlink_surface(driver)
    verdict = lock.acquire_s2_4_install_lock(driver)
    assert verdict["status"] == "PRECHECK_FAILED"
    assert any("never unlinked" in reason for reason in verdict["reasons"])
    assert driver.calls == []
    assert lock.assert_no_lock_unlink_surface(FakeLockDriver()) == []


def test_release_closes_the_fd_and_never_unlinks() -> None:
    driver = FakeLockDriver()
    acquired = lock.acquire_s2_4_install_lock(driver)
    released = lock.release_s2_4_install_lock(driver, acquired)
    assert released == {"status": "INSTALL_LOCK_RELEASED", "reasons": [], "lock_unlinked": False}
    assert 11 in driver.closed
    assert lock.release_s2_4_install_lock(driver, {"status": "INSTALL_LOCK_HELD"})["status"] == (
        "NOT_HELD"
    )


def test_a_driver_that_raises_is_typed_recovery_required() -> None:
    class _Broken(FakeLockDriver):
        def openat_lock_file(self, **_kwargs):
            raise OSError("/run/lock/secret-path-in-message")

    verdict = lock.acquire_s2_4_install_lock(_Broken())
    assert verdict["status"] == "RECOVERY_REQUIRED"
    # driver 例外文字被紅字化成類名(絕不夾帶主機路徑)。
    assert any("OSError" in reason for reason in verdict["reasons"])
    assert not any("secret-path-in-message" in reason for reason in verdict["reasons"])


# ── §9.1 replay-ledger append ──────────────────────────────────────────────────
_LEDGER_BASENAME = "authorization-replay-ledger.json"


def _ledger_fs():
    """ledger 的 parent 是 install state root(mode 0700)。"""

    return FakeDurableFs(parent_mode=journal.JOURNAL_PARENT_MODE)


def _permits(tmp_path, monkeypatch):
    return kit.signed_authorizations(tmp_path, monkeypatch)


def _expected_bindings():
    return {
        "apply_aggregate": {
            "domain": "arcane-equilibrium-aiml-s2-install",
            "plan_core_digest": kit.PLAN_DIGEST,
            "plan_id": kit.PLAN_ID,
        },
        "pg_migration": {
            "domain": "arcane-equilibrium-aiml-s2-pg-migration",
            "plan_core_digest": kit.PLAN_DIGEST,
            "plan_id": kit.PLAN_ID,
        },
    }


def _acquired():
    return lock.acquire_s2_4_install_lock(FakeLockDriver())


def test_append_requires_the_install_lock(tmp_path, monkeypatch) -> None:
    signed = _permits(tmp_path, monkeypatch)
    outcome = lock.consume_authorizations_under_lock(
        _ledger_fs(),
        authorizations={"apply_aggregate": signed["apply_aggregate"]},
        expected_payload_bindings={"apply_aggregate": _expected_bindings()["apply_aggregate"]},
        lock_verdict={"status": "INSTALL_LOCK_HELD"},
        now=kit.NOW,
    )
    assert outcome["status"] == "INSTALL_LOCK_REQUIRED"
    assert outcome["mutation_performed"] is False
    assert any("under the exclusive" in reason for reason in outcome["reasons"])


def test_source_lane_append_without_a_file_driver_is_pending(tmp_path, monkeypatch) -> None:
    signed = _permits(tmp_path, monkeypatch)
    outcome = lock.consume_authorizations_under_lock(
        None,
        authorizations={"apply_aggregate": signed["apply_aggregate"]},
        expected_payload_bindings={"apply_aggregate": _expected_bindings()["apply_aggregate"]},
        lock_verdict=_acquired(),
        now=kit.NOW,
    )
    assert outcome["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert outcome["mutation_performed"] is False


def test_append_is_hash_chained_fsynced_and_atomically_renamed(tmp_path, monkeypatch) -> None:
    signed = _permits(tmp_path, monkeypatch)
    fs = _ledger_fs()
    outcome = lock.consume_authorizations_under_lock(
        fs,
        authorizations={
            "apply_aggregate": signed["apply_aggregate"],
            "pg_migration": signed["pg_migration"],
        },
        expected_payload_bindings=_expected_bindings(),
        lock_verdict=_acquired(),
        now=kit.NOW,
    )
    assert outcome["status"] == "AUTHORIZATION_CONSUMPTION_APPENDED", outcome["reasons"]
    assert outcome["mutation_performed"] is True
    ledger = outcome["ledger"]
    assert validator._s2_4_replay_ledger_errors(ledger) == []
    assert validator.validate_aiml_artifact(ledger) == []
    assert [entry["seq"] for entry in ledger["entries"]] == [0, 1]
    assert ledger["entries"][0]["prev_entry_digest"] is None
    assert ledger["entries"][1]["prev_entry_digest"] == ledger["entries"][0]["entry_digest"]
    assert all(entry["fsynced"] is True for entry in ledger["entries"])
    assert sorted(outcome["appended_authorization_ids"]) == sorted(
        [signed["apply_aggregate"]["authorization_id"], signed["pg_migration"]["authorization_id"]]
    )
    # durability:temp → fsync → atomic rename → parent fsync(同 journal 紀律)。
    assert "fsync_file" in fs.calls and "atomic_rename" in fs.calls
    assert fs.parent_fsyncs == 1
    persisted = json.loads(fs.files[_LEDGER_BASENAME].decode("utf-8"))
    assert persisted == ledger


def test_same_key_same_plan_is_an_idempotent_replay_that_appends_nothing(
    tmp_path, monkeypatch
) -> None:
    """§10.5 #8 前半:相同 idempotency key + 相同 plan 綁定 → 成功、零重複 append。"""

    signed = _permits(tmp_path, monkeypatch)
    fs = _ledger_fs()
    first = lock.consume_authorizations_under_lock(
        fs,
        authorizations={"apply_aggregate": signed["apply_aggregate"]},
        expected_payload_bindings={"apply_aggregate": _expected_bindings()["apply_aggregate"]},
        lock_verdict=_acquired(), now=kit.NOW,
    )
    assert first["status"] == "AUTHORIZATION_CONSUMPTION_APPENDED"
    renames = fs.calls.count("atomic_rename")
    second = lock.consume_authorizations_under_lock(
        fs,
        authorizations={"apply_aggregate": signed["apply_aggregate"]},
        expected_payload_bindings={"apply_aggregate": _expected_bindings()["apply_aggregate"]},
        lock_verdict=_acquired(), now=kit.NOW,
    )
    assert second["status"] == "IDEMPOTENT_REPLAY_ADMITTED", second["reasons"]
    assert second["mutation_performed"] is False
    assert second["appended_authorization_ids"] == []
    assert fs.calls.count("atomic_rename") == renames
    assert len(second["ledger"]["entries"]) == 1


def test_same_key_different_plan_is_authorization_rejected(tmp_path, monkeypatch) -> None:
    """§10.5 #8 後半:同一 replay id 已綁到別的 permit/plan → 拒,且零 append。"""

    signed = _permits(tmp_path, monkeypatch)
    fs = _ledger_fs()
    hijacked = lock.append_replay_entries(
        lock.empty_replay_ledger(),
        [
            {
                "authorization_id": signed["apply_aggregate"]["authorization_id"],
                "self_digest": "sha256:" + "d" * 64,   # 不同的 permit/plan
                "profile_identity": signed["apply_aggregate"]["profile_identity"],
            }
        ],
        consumed_at=kit.ISSUED,
    )
    fs.files[_LEDGER_BASENAME] = validator._canonical_bytes(hijacked)
    outcome = lock.consume_authorizations_under_lock(
        fs,
        authorizations={"apply_aggregate": signed["apply_aggregate"]},
        expected_payload_bindings={"apply_aggregate": _expected_bindings()["apply_aggregate"]},
        lock_verdict=_acquired(), now=kit.NOW,
    )
    assert outcome["status"] == "AUTHORIZATION_REJECTED"
    assert outcome["mutation_performed"] is False
    assert any("DIFFERENT authorization/plan" in reason for reason in outcome["reasons"])
    assert json.loads(fs.files[_LEDGER_BASENAME].decode("utf-8")) == hijacked


def test_a_permit_not_bound_to_this_plan_is_rejected_before_any_append(
    tmp_path, monkeypatch
) -> None:
    signed = _permits(tmp_path, monkeypatch)
    fs = _ledger_fs()
    substituted = dict(_expected_bindings()["apply_aggregate"])
    substituted["plan_core_digest"] = "sha256:" + "9" * 64
    outcome = lock.consume_authorizations_under_lock(
        fs,
        authorizations={"apply_aggregate": signed["apply_aggregate"]},
        expected_payload_bindings={"apply_aggregate": substituted},
        lock_verdict=_acquired(), now=kit.NOW,
    )
    assert outcome["status"] == "AUTHORIZATION_REJECTED"
    assert any("intent substitution" in reason for reason in outcome["reasons"])
    assert fs.files == {}


def test_atomic_consumption_is_all_or_nothing(tmp_path, monkeypatch) -> None:
    """§9.1:APPLY 於第一次變更之前 atomically 消費兩張 permit——一張不過即零 append。"""

    signed = _permits(tmp_path, monkeypatch)
    fs = _ledger_fs()
    bindings = _expected_bindings()
    bindings["pg_migration"] = dict(bindings["pg_migration"], plan_id="s2-4-" + "0" * 64)
    outcome = lock.consume_authorizations_under_lock(
        fs,
        authorizations={
            "apply_aggregate": signed["apply_aggregate"],
            "pg_migration": signed["pg_migration"],
        },
        expected_payload_bindings=bindings,
        lock_verdict=_acquired(), now=kit.NOW,
    )
    assert outcome["status"] == "AUTHORIZATION_REJECTED"
    assert outcome["mutation_performed"] is False
    assert any("all-or-nothing" in reason for reason in outcome["reasons"])
    assert fs.files == {}


def test_every_consumed_permit_needs_its_own_expected_binding(tmp_path, monkeypatch) -> None:
    signed = _permits(tmp_path, monkeypatch)
    outcome = lock.consume_authorizations_under_lock(
        _ledger_fs(),
        authorizations={
            "apply_aggregate": signed["apply_aggregate"],
            "pg_migration": signed["pg_migration"],
        },
        expected_payload_bindings={"apply_aggregate": _expected_bindings()["apply_aggregate"]},
        lock_verdict=_acquired(), now=kit.NOW,
    )
    assert outcome["status"] == "AUTHORIZATION_REJECTED"
    assert any("independently re-derived" in reason for reason in outcome["reasons"])


def test_a_corrupt_durable_ledger_is_typed_and_never_overwritten(tmp_path, monkeypatch) -> None:
    signed = _permits(tmp_path, monkeypatch)
    fs = _ledger_fs()
    fs.files[_LEDGER_BASENAME] = b'{"schema_version": "s2_4_authorization_replay_led'
    outcome = lock.consume_authorizations_under_lock(
        fs,
        authorizations={"apply_aggregate": signed["apply_aggregate"]},
        expected_payload_bindings={"apply_aggregate": _expected_bindings()["apply_aggregate"]},
        lock_verdict=_acquired(), now=kit.NOW,
    )
    assert outcome["status"] == "LEDGER_CORRUPT_RECOVERY_REQUIRED"
    assert outcome["mutation_performed"] is False
    assert fs.files[_LEDGER_BASENAME] == b'{"schema_version": "s2_4_authorization_replay_led'
    assert "atomic_rename" not in fs.calls


def test_an_expired_permit_can_never_be_consumed(tmp_path, monkeypatch) -> None:
    private_key, public_key, fingerprint = kit.mint_key(tmp_path, name="expired-op")
    kit.install_pinned_key(monkeypatch, public_key, fingerprint)
    expired = kit.authorization(
        private_key, profile_key="apply_aggregate",
        payload_binding=kit.apply_payload_binding("apply_aggregate", expires_at=kit.ISSUED),
        expires_at=kit.ISSUED,
    )
    outcome = lock.consume_authorizations_under_lock(
        _ledger_fs(),
        authorizations={"apply_aggregate": expired},
        expected_payload_bindings={"apply_aggregate": _expected_bindings()["apply_aggregate"]},
        lock_verdict=_acquired(), now=kit.NOW,
    )
    assert outcome["status"] == "AUTHORIZATION_REJECTED"


def test_replay_append_never_claims_production() -> None:
    projection = lock.lock_abi_projection()
    assert projection["replay_ledger_path"] == (
        "/var/lib/arcane-equilibrium/aiml/install/s2_4/authorization-replay-ledger.json"
    )
    assert projection["lock_file_mode"] == "0600"
    assert "INSTALL_LOCK_HELD" in projection["lock_typed_statuses"]
    outcome = lock.consume_authorizations_under_lock(
        None, authorizations={"apply_aggregate": {}},
        expected_payload_bindings={"apply_aggregate": {"domain": "x"}},
        lock_verdict=_acquired(),
    )
    assert outcome["production_authority_flags"] == {
        "nine_authorities_false": True,
        "production_apply_performed": False,
        "running_attested": False,
    }
