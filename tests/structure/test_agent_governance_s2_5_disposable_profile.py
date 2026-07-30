"""S2.5 disposable user-systemd profile single-source-of-truth checks."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

import agent_governance_s2_5_disposable_profile as profile  # noqa: E402
import agent_governance_s2_5_recovery_store as store  # noqa: E402


def test_recovery_store_consumes_the_fixed_disposable_profile_ssot():
    assert store.DISPOSABLE_STATE_ROOT == profile.DISPOSABLE_STATE_ROOT
    assert store.PROFILE_ID == profile.PROFILE_ID
    assert store.PROFILE_UID == profile.PROFILE_UID == 1000
    assert store.PROFILE_GID == profile.PROFILE_GID == 1000

    source = (HELPERS / "agent_governance_s2_5_recovery_store.py").read_text(
        encoding="utf-8"
    )
    assert "from agent_governance_s2_5_disposable_profile import" in source
    assert source.count("/run/user/1000/arcane-equilibrium-aiml-s2e") == 0


def test_profile_fixes_user_manager_paths_locks_units_and_cgroups():
    assert profile.XDG_RUNTIME_ROOT == "/run/user/1000"
    assert profile.DISPOSABLE_STATE_ROOT.startswith(profile.PROFILE_RUNTIME_ROOT + "/")
    assert profile.DISPOSABLE_LOCK_ROOT.startswith(profile.PROFILE_RUNTIME_ROOT + "/")
    locks = {
        profile.S2_4_RECOVERY_INSTALL_FENCE_LOCK_PATH,
        profile.S2_5_RECOVERY_LIFECYCLE_LOCK_PATH,
    }
    assert len(locks) == 2
    assert all(path.startswith(profile.DISPOSABLE_LOCK_ROOT + "/") for path in locks)
    assert all(not path.startswith("/run/lock/") for path in locks)

    units = {
        profile.DISPOSABLE_TARGET_UNIT,
        profile.RECOVERY_RUNNER_UNIT,
        profile.ANCHOR_WRITER_UNIT,
        profile.ANCHOR_READER_UNIT,
        profile.ANCHOR_VERIFIER_UNIT,
    }
    assert len(units) == 5
    assert all(unit.startswith("arcane-equilibrium-aiml-s2-5-") for unit in units)
    for unit, cgroup in (
        (profile.RECOVERY_RUNNER_UNIT, profile.RECOVERY_RUNNER_CGROUP),
        (profile.ANCHOR_WRITER_UNIT, profile.ANCHOR_WRITER_CGROUP),
        (profile.ANCHOR_READER_UNIT, profile.ANCHOR_READER_CGROUP),
        (profile.ANCHOR_VERIFIER_UNIT, profile.ANCHOR_VERIFIER_CGROUP),
    ):
        assert cgroup == profile.USER_MANAGER_CGROUP_ROOT + "/" + unit


def test_external_anchor_is_explicitly_outside_the_replaceable_state_root():
    assert profile.ANCHOR_RESOURCE_CLASS == "EXTERNAL_APPEND_ONLY_WORM"
    assert profile.ANCHOR_RESOURCE_SCOPE == "OUTSIDE_REPLACEABLE_STATE_ROOT"
    assert profile.ANCHOR_STORE_ID != profile.DISPOSABLE_STATE_ROOT
    assert profile.ANCHOR_COLLECTION_ID != profile.DISPOSABLE_STATE_ROOT


def test_profile_record_is_fresh_and_does_not_expose_a_mutable_singleton():
    first = profile.profile_record()
    second = profile.profile_record()
    assert first == second
    assert first is not second
    assert first["anchor_identities"] is not second["anchor_identities"]
    first["anchor_identities"]["writer"]["unit"] = "tampered.service"
    assert (
        profile.profile_record()["anchor_identities"]["writer"]["unit"]
        == profile.ANCHOR_WRITER_UNIT
    )


def test_disposable_profile_does_not_modify_production_lock_constants():
    s2_4_source = (
        HELPERS / "agent_governance_s2_4_lock.py"
    ).read_text(encoding="utf-8")
    s2_5_source = (
        HELPERS / "agent_governance_s2_5_wal.py"
    ).read_text(encoding="utf-8")
    assert (
        'INSTALL_LOCK_PATH = "/run/lock/arcane-equilibrium-aiml-s2-4-install.lock"'
        in s2_4_source
    )
    assert (
        'S2_5_LOCK_PATH = "/run/lock/arcane-equilibrium-aiml-s2-5-lifecycle.lock"'
        in s2_5_source
    )
