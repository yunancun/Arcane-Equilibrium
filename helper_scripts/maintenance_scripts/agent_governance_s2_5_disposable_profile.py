#!/usr/bin/env python3
"""S2.5 recovery rehearsal 的固定 user-systemd profile SSOT。

本模組只描述 source contract，不建立 unit、不取得 lock，也不宣稱 target host
已存在。所有路徑、身分與 unit 名稱皆由程式碼固定；呼叫端沒有覆寫面。
"""

from __future__ import annotations


PROFILE_ID = "s2_5_recovery_user_systemd_disposable_v1"
PROFILE_UID = 1000
PROFILE_GID = 1000
PROFILE_TARGET_CLASS = "disposable_systemd"
PROFILE_EVIDENCE_CLASS = "LOCAL_REPRODUCIBLE"

XDG_RUNTIME_ROOT = "/run/user/1000"
USER_MANAGER_ROOT = XDG_RUNTIME_ROOT + "/systemd"
USER_MANAGER_UNIT_ROOT = USER_MANAGER_ROOT + "/user"
USER_MANAGER_CGROUP_ROOT = (
    "/user.slice/user-1000.slice/user@1000.service/app.slice"
)

PROFILE_RUNTIME_ROOT = XDG_RUNTIME_ROOT + "/arcane-equilibrium-aiml-s2e"
DISPOSABLE_STATE_ROOT = PROFILE_RUNTIME_ROOT + "/s2_5-recovery"
DISPOSABLE_LOCK_ROOT = PROFILE_RUNTIME_ROOT + "/locks"
S2_4_RECOVERY_INSTALL_FENCE_LOCK_PATH = (
    DISPOSABLE_LOCK_ROOT + "/s2-4-recovery-install-fence.lock"
)
S2_5_RECOVERY_LIFECYCLE_LOCK_PATH = (
    DISPOSABLE_LOCK_ROOT + "/s2-5-recovery-lifecycle.lock"
)

DISPOSABLE_TARGET_UNIT = "arcane-equilibrium-aiml-s2-5-disposable.target"
RECOVERY_RUNNER_UNIT = "arcane-equilibrium-aiml-s2-5-recovery.service"
ANCHOR_WRITER_UNIT = "arcane-equilibrium-aiml-s2-5-anchor-writer.service"
ANCHOR_READER_UNIT = "arcane-equilibrium-aiml-s2-5-anchor-reader.service"
ANCHOR_VERIFIER_UNIT = "arcane-equilibrium-aiml-s2-5-anchor-verifier.service"

RECOVERY_RUNNER_ROLE = "recovery_runner"
ANCHOR_WRITER_ROLE = "external_anchor_writer"
ANCHOR_READER_ROLE = "external_anchor_reader"
ANCHOR_VERIFIER_ROLE = "external_anchor_verifier"

RECOVERY_RUNNER_CGROUP = USER_MANAGER_CGROUP_ROOT + "/" + RECOVERY_RUNNER_UNIT
ANCHOR_WRITER_CGROUP = USER_MANAGER_CGROUP_ROOT + "/" + ANCHOR_WRITER_UNIT
ANCHOR_READER_CGROUP = USER_MANAGER_CGROUP_ROOT + "/" + ANCHOR_READER_UNIT
ANCHOR_VERIFIER_CGROUP = USER_MANAGER_CGROUP_ROOT + "/" + ANCHOR_VERIFIER_UNIT

ANCHOR_STORE_ID = "s2-5-recovery-external-anchor-v1"
ANCHOR_COLLECTION_ID = "s2-5-recovery-anchor-chain-v1"
ANCHOR_RESOURCE_CLASS = "EXTERNAL_APPEND_ONLY_WORM"
ANCHOR_RESOURCE_SCOPE = "OUTSIDE_REPLACEABLE_STATE_ROOT"

SIDE_EFFECT_CLASS = "DISPOSABLE_TEST"
STATUS_UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED = (
    "UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED"
)


def profile_record() -> dict[str, object]:
    """回傳固定 profile 的新 dict，避免共享可變 singleton。"""

    return {
        "profile_id": PROFILE_ID,
        "uid": PROFILE_UID,
        "gid": PROFILE_GID,
        "target_class": PROFILE_TARGET_CLASS,
        "evidence_class": PROFILE_EVIDENCE_CLASS,
        "xdg_runtime_root": XDG_RUNTIME_ROOT,
        "user_manager_root": USER_MANAGER_ROOT,
        "user_manager_unit_root": USER_MANAGER_UNIT_ROOT,
        "user_manager_cgroup_root": USER_MANAGER_CGROUP_ROOT,
        "state_root": DISPOSABLE_STATE_ROOT,
        "lock_root": DISPOSABLE_LOCK_ROOT,
        "s2_4_recovery_install_fence_lock_path": (
            S2_4_RECOVERY_INSTALL_FENCE_LOCK_PATH
        ),
        "s2_5_recovery_lifecycle_lock_path": S2_5_RECOVERY_LIFECYCLE_LOCK_PATH,
        "disposable_target_unit": DISPOSABLE_TARGET_UNIT,
        "recovery_runner_unit": RECOVERY_RUNNER_UNIT,
        "anchor_store_id": ANCHOR_STORE_ID,
        "anchor_collection_id": ANCHOR_COLLECTION_ID,
        "anchor_resource_class": ANCHOR_RESOURCE_CLASS,
        "anchor_resource_scope": ANCHOR_RESOURCE_SCOPE,
        "anchor_identities": {
            "writer": {
                "role": ANCHOR_WRITER_ROLE,
                "unit": ANCHOR_WRITER_UNIT,
                "cgroup": ANCHOR_WRITER_CGROUP,
            },
            "reader": {
                "role": ANCHOR_READER_ROLE,
                "unit": ANCHOR_READER_UNIT,
                "cgroup": ANCHOR_READER_CGROUP,
            },
            "verifier": {
                "role": ANCHOR_VERIFIER_ROLE,
                "unit": ANCHOR_VERIFIER_UNIT,
                "cgroup": ANCHOR_VERIFIER_CGROUP,
            },
        },
    }
