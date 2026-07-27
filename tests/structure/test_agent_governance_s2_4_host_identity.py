"""S2.4(WP4·W3b)``HOST_IDENTITY_INSTALL`` row 的 focused 測試(§8 / §10.5 #31/#37)。

依 §10.1.1 的 2000 行治理自 ``test_agent_governance_s2_4_apply`` 拆出(共用腳手架下沉至
``s2_4_w3b_testkit``)。證明:

- source lane(``driver=None``)typed ``EXTERNAL_VERIFICATION_PENDING``、零變更、零 driver 接觸;
- §10.5 #31:只有 PG permit 時 typed 拒並明文點名該縫;
- §10.5 #37:service-account / 目錄屬性漂移在第一次變更之前失敗;
- §5.3:exact desired + 無 ownership → ``PREEXISTING_UNOWNED_STATE``(絕不收養);
- **UID/GID 三重把關**(W3 review E3 P1-3):S2.3 cross-check + system-account 區間 +
  變更前的數值佔用觀測;uid=gid=26(postgres)必被拒;
- **§5.4 補償 exactness**(W3 review E2 P1-4):補償後再觀測仍見殘留即 ``RECOVERY_REQUIRED``。
"""
from __future__ import annotations

import json as json_module
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
PROGRAM_CODE = ROOT / "program_code"
for candidate in (HELPERS, ML_ROOT, PROGRAM_CODE, ROOT / "tests/structure"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2_4_apply as apply_mod  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402
import s2_4_w3b_testkit as kit  # noqa: E402

_PLAN_DIGEST = kit.PLAN_DIGEST
_PRE_STATE = kit.PRE_STATE
_UID = kit.UID
_GID = kit.GID
_PostcheckMixin = kit.PostcheckMixin
_intent = kit.component_intent
_common = kit.common_apply_kwargs
_owned = kit.owned_evidence


@pytest.fixture()
def signed(tmp_path, monkeypatch):
    return kit.signed_authorizations(tmp_path, monkeypatch)


# ══════════════════════════ 1) HOST_IDENTITY_INSTALL ═══════════════════════════
class _FakeHostIdentityDriver(_PostcheckMixin):
    # in-memory fixture 絕不冒充平台背書(W3 review E2 P1-1 / E3 P2-6)。
    evidence_class = "STRUCTURAL_ONLY"

    def __init__(self, *, identity=None, directories=None, postcheck_ok=True,
                 fail_at=None, compensation_ok=True, uid_owner=None, gid_owner=None,
                 residual_after_compensation=()):
        self.calls: list[str] = []
        self.identity = identity
        self.directories = dict(directories or {})
        self.postcheck_ok = postcheck_ok
        self.fail_at = fail_at
        self.compensation_ok = compensation_ok
        self.removed: list[str] = []
        # 數值 UID/GID 的既有佔用者(None = 無人佔用)。
        self.uid_owner = uid_owner
        self.gid_owner = gid_owner
        # 補償「沒拋例外」但實際未清乾淨的 subject(用於證明再觀測是 load-bearing 的)。
        self.residual_after_compensation = set(residual_after_compensation)

    def observe_identity(self, *, name):
        self.calls.append("observe_identity")
        if self.identity is not None:
            return dict(self.identity)
        if "remove_system_account" in self.calls:
            return (
                apply_mod.host_identity_desired_state(uid=_UID, gid=_GID)
                if "identity" in self.residual_after_compensation else None
            )
        if "create_system_account" in self.calls:
            return apply_mod.host_identity_desired_state(uid=_UID, gid=_GID)
        return None

    def observe_account_by_uid(self, *, uid):
        self.calls.append("observe_account_by_uid")
        return dict(self.uid_owner) if self.uid_owner else None

    def observe_group_by_gid(self, *, gid):
        self.calls.append("observe_group_by_gid")
        return dict(self.gid_owner) if self.gid_owner else None

    def create_system_account(self, *, name, uid, gid, home, shell):
        self.calls.append("create_system_account")
        if self.fail_at == "create_system_account":
            raise RuntimeError("injected identity failure")

    def remove_system_account(self, *, name):
        self.calls.append("remove_system_account")
        if not self.compensation_ok:
            raise RuntimeError("compensation failed")

    def observe_directory(self, *, path):
        self.calls.append("observe_directory")
        if path in self.directories:
            return dict(self.directories[path])
        removed = f"remove_directory:{path}" in self.calls
        if removed and path not in self.residual_after_compensation:
            return None
        if f"create_directory:{path}" in self.calls:
            return next(
                dict(entry) for entry in apply_mod.host_identity_directory_tree()
                if entry["path"] == path
            )
        return None

    def create_directory(self, *, path, owner, group, mode):
        self.calls.append(f"create_directory:{path}")
        if self.fail_at == path:
            raise RuntimeError("injected directory failure")

    def remove_directory(self, *, path):
        self.calls.append(f"remove_directory:{path}")
        self.removed.append(path)
        if not self.compensation_ok:
            raise RuntimeError("compensation failed")


def _host_identity_intent(uid: int = _UID, gid: int = _GID) -> tuple[dict, dict]:
    manifest = apply_mod.build_uid_gid_directory_manifest(uid=uid, gid=gid)
    intent = _intent(
        "HOST_IDENTITY_INSTALL",
        {"uid_gid_directory_manifest_digest": validator.canonical_digest(manifest)},
    )
    return intent, manifest


def test_host_identity_source_lane_is_pending_with_zero_mutation(signed) -> None:
    intent, manifest = _host_identity_intent()
    verdict = apply_mod.apply_s2_4_host_identity(
        intent, driver=None, uid_gid_directory_manifest=manifest, **_common(signed)
    )
    assert verdict["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert verdict["mutation_performed"] is False and verdict["driver_engaged"] is False
    assert verdict["result"] is None and verdict["blocks_aggregate"] is True
    assert verdict["row_abi"]["adapter_id"] == "s2_4_host_identity_adapter_v1"
    assert verdict["row_abi"]["actor_node_id"] == "s2_4_host_identity_actor"
    assert verdict["row_abi"]["independent_postcheck_node_id"] == "s2_4_host_identity_postcheck_v1"
    assert verdict["row_abi"]["recovery_contract"] == "s2_4_host_identity_rollback_v1"
    assert verdict["production_authority_flags"] == {
        "nine_authorities_false": True,
        "production_apply_performed": False,
        "running_attested": False,
    }


def test_host_identity_apply_creates_the_exact_account_and_tree(signed) -> None:
    intent, manifest = _host_identity_intent()
    driver = _FakeHostIdentityDriver()
    verdict = apply_mod.apply_s2_4_host_identity(
        intent, driver=driver, uid_gid_directory_manifest=manifest, **_common(signed)
    )
    assert verdict["status"] == "SATISFIED", verdict["reasons"]
    assert validator.validate_aiml_artifact(verdict["result"]) == []
    assert validator.validate_aiml_artifact(verdict["postcheck"]) == []
    assert validator.validate_aiml_artifact(verdict["rollback"]) == []
    assert verdict["result"]["status"] == "SATISFIED"
    assert verdict["result"]["production_authority_flags"]["running_attested"] is False
    identity = verdict["observed_subjects"]["identity"]
    assert identity["shell"] == "/usr/sbin/nologin"
    assert identity["password_locked"] is True
    assert identity["supplementary_groups"] == []
    assert identity["account_expiry"] is None
    assert identity["uid"] == _UID and identity["gid"] == _GID
    assert sorted(entry["path"] for entry in apply_mod.host_identity_directory_tree()) == sorted(
        verdict["observed_subjects"]["directories"]
    )
    assert driver.calls[0] == "observe_identity"


@pytest.mark.parametrize("attribute,value", [
    ("uid", 1000), ("gid", 1000), ("shell", "/bin/bash"), ("home", "/home/aiml"),
    ("password_locked", False), ("supplementary_groups", ["sudo"]),
    ("account_expiry", "2031-01-01"), ("system_account", False),
])
def test_service_account_attribute_drift_fails_before_mutation(signed, attribute, value) -> None:
    intent, manifest = _host_identity_intent()
    drifted = apply_mod.host_identity_desired_state(uid=_UID, gid=_GID)
    drifted[attribute] = value
    driver = _FakeHostIdentityDriver(identity=drifted)
    verdict = apply_mod.apply_s2_4_host_identity(
        intent, driver=driver, uid_gid_directory_manifest=manifest, **_common(signed)
    )
    assert verdict["status"] == "PRESTATE_MISMATCH"
    assert verdict["mutation_performed"] is False
    assert "create_system_account" not in driver.calls
    assert any("before any mutation" in reason for reason in verdict["reasons"])


def test_directory_mode_or_owner_drift_fails_before_mutation(signed) -> None:
    intent, manifest = _host_identity_intent()
    tree = apply_mod.host_identity_directory_tree()
    drifted = {tree[0]["path"]: {**tree[0], "mode": "0777"}}
    driver = _FakeHostIdentityDriver(
        identity=apply_mod.host_identity_desired_state(uid=_UID, gid=_GID), directories=drifted
    )
    verdict = apply_mod.apply_s2_4_host_identity(
        intent, driver=driver, uid_gid_directory_manifest=manifest, **_common(signed)
    )
    assert verdict["status"] == "PRESTATE_MISMATCH"
    assert not any(call.startswith("create_directory") for call in driver.calls)


def test_exact_desired_identity_without_ownership_is_never_adopted(signed) -> None:
    intent, manifest = _host_identity_intent()
    driver = _FakeHostIdentityDriver(
        identity=apply_mod.host_identity_desired_state(uid=_UID, gid=_GID),
        directories={
            entry["path"]: dict(entry) for entry in apply_mod.host_identity_directory_tree()
        },
    )
    verdict = apply_mod.apply_s2_4_host_identity(
        intent, driver=driver, uid_gid_directory_manifest=manifest, **_common(signed)
    )
    assert verdict["status"] == "PREEXISTING_UNOWNED_STATE"
    assert verdict["mutation_performed"] is False


def test_exact_desired_identity_with_ownership_is_noop_verified(signed) -> None:
    intent, manifest = _host_identity_intent()
    owned = {"s2_4_receipt_digest": "sha256:" + "a" * 64, "journal_digest": "sha256:" + "b" * 64}
    tree = apply_mod.host_identity_directory_tree()
    driver = _FakeHostIdentityDriver(
        identity=apply_mod.host_identity_desired_state(uid=_UID, gid=_GID),
        directories={entry["path"]: dict(entry) for entry in tree},
    )
    verdict = apply_mod.apply_s2_4_host_identity(
        intent, driver=driver, uid_gid_directory_manifest=manifest,
        ownership_evidence={"identity": owned, **{entry["path"]: owned for entry in tree}},
        **_common(signed),
    )
    assert verdict["status"] == "NOOP_VERIFIED"
    assert verdict["mutation_performed"] is False
    assert verdict["result"]["status"] == "NOOP_VERIFIED"


def test_a_pg_permit_cannot_authorize_host_identity_mutation(signed) -> None:
    intent, manifest = _host_identity_intent()
    driver = _FakeHostIdentityDriver()
    verdict = apply_mod.apply_s2_4_host_identity(
        intent, {"pg_migration": signed["pg_migration"]}, driver,
        uid_gid_directory_manifest=manifest, replay_ledger=kit.replay_ledger(),
        now=kit.NOW, clock=kit.frozen_clock(),
    )
    assert verdict["status"] == "AUTHORIZATION_REJECTED"
    assert any("PG-migration permit cannot authorize" in reason for reason in verdict["reasons"])
    assert driver.calls == []


def test_host_identity_effects_classify_only_as_host_identity_install() -> None:
    for subject in ("host_user", "host_group", "host_directory"):
        assert apply_mod.derive_host_identity_effect_class_status(
            subject_kind=subject, declared_class="HOST_IDENTITY_INSTALL"
        )["status"] == "HOST_IDENTITY_CLASSIFICATION_ADMITTED"
        for other in ("PG_ROLE_ACL_MIGRATION", "CREDENTIAL_INSTALL", "LEARNING_RUNTIME",
                      "ENGINE_SCANNER", "NONE"):
            verdict = apply_mod.derive_host_identity_effect_class_status(
                subject_kind=subject, declared_class=other
            )
            assert verdict["status"] == "HOST_IDENTITY_CLASSIFICATION_REJECTED"
            assert any("#31" in reason for reason in verdict["reasons"])


def test_host_identity_failure_compensates_only_task_owned_creations(signed) -> None:
    intent, manifest = _host_identity_intent()
    tree = apply_mod.host_identity_directory_tree()
    driver = _FakeHostIdentityDriver(fail_at=tree[-1]["path"])
    verdict = apply_mod.apply_s2_4_host_identity(
        intent, driver=driver, uid_gid_directory_manifest=manifest, **_common(signed)
    )
    assert verdict["status"] == "FAILED"
    assert verdict["rollback"]["status"] == "COMPENSATED_EXACT"
    assert verdict["rollback"]["no_secret_reconstructed"] is True
    assert "remove_system_account" in driver.calls
    assert driver.removed == [entry["path"] for entry in reversed(tree[:-1])]


def test_host_identity_postcheck_failure_rolls_back(signed) -> None:
    intent, manifest = _host_identity_intent()
    driver = _FakeHostIdentityDriver(postcheck_ok=False)
    verdict = apply_mod.apply_s2_4_host_identity(
        intent, driver=driver, uid_gid_directory_manifest=manifest, **_common(signed)
    )
    assert verdict["status"] == "POSTCHECK_FAILED_ROLLED_BACK"
    assert verdict["rollback"]["status"] == "COMPENSATED_EXACT"
    assert "remove_system_account" in driver.calls


# ── W3 review E3 P1-3:UID/GID 不受限 = 提權(區間 / S2.3 cross-check / 碰撞觀測)──────
@pytest.mark.parametrize("uid,gid", [
    (26, 26),        # postgres(建模主機):共用 UID → scanner 在 kernel 眼中就是 postgres
    (0, 0),          # root
    (1, 1),          # daemon
    (1000, 1000),    # 第一個人類帳號
    (65534, 65534),  # nobody
    (-1, 947), (947, 0), (2 ** 31, 947),
])
def test_a_signed_manifest_cannot_place_the_scanner_on_a_foreign_uid(signed, uid, gid) -> None:
    """被簽 manifest 上的 uid/gid 舊碼只驗「正整數」;uid=gid=26 會讓 scanner 與 postgres
    共用 UID —— local socket peer-auth 直達 superuser + data dir 讀取,整條
    PG_ROLE_ACL_MIGRATION 邊界形同虛設。"""

    manifest = apply_mod.build_uid_gid_directory_manifest(uid=uid, gid=gid)
    intent = _intent(
        "HOST_IDENTITY_INSTALL",
        {"uid_gid_directory_manifest_digest": validator.canonical_digest(manifest)},
    )
    driver = _FakeHostIdentityDriver()
    verdict = apply_mod.apply_s2_4_host_identity(
        intent, driver=driver, uid_gid_directory_manifest=manifest, **_common(signed)
    )
    assert verdict["status"] == "PRECHECK_FAILED", (uid, gid, verdict["status"])
    assert verdict["mutation_performed"] is False
    assert driver.calls == []
    assert any("system-account range" in reason for reason in verdict["reasons"])


@pytest.mark.parametrize("uid,gid", [(100, 100), (947, 947), (999, 999)])
def test_the_system_account_range_still_admits_the_signed_plan(signed, uid, gid) -> None:
    manifest = apply_mod.build_uid_gid_directory_manifest(uid=uid, gid=gid)
    intent = _intent(
        "HOST_IDENTITY_INSTALL",
        {"uid_gid_directory_manifest_digest": validator.canonical_digest(manifest)},
    )
    assert apply_mod.apply_s2_4_host_identity(
        intent, driver=None, uid_gid_directory_manifest=manifest, **_common(signed)
    )["status"] == "EXTERNAL_VERIFICATION_PENDING"


def test_a_uid_already_held_by_another_account_is_a_pre_mutation_refusal(signed) -> None:
    intent, manifest = _host_identity_intent()
    driver = _FakeHostIdentityDriver(uid_owner={"name": "postgres", "uid": _UID})
    verdict = apply_mod.apply_s2_4_host_identity(
        intent, driver=driver, uid_gid_directory_manifest=manifest, **_common(signed)
    )
    assert verdict["status"] == "PREEXISTING_UNOWNED_STATE"
    assert verdict["mutation_performed"] is False
    assert "create_system_account" not in driver.calls
    assert any("already held by account" in reason for reason in verdict["reasons"])


def test_a_gid_already_held_by_another_group_is_a_pre_mutation_refusal(signed) -> None:
    intent, manifest = _host_identity_intent()
    driver = _FakeHostIdentityDriver(gid_owner={"name": "postgres", "gid": _GID})
    verdict = apply_mod.apply_s2_4_host_identity(
        intent, driver=driver, uid_gid_directory_manifest=manifest, **_common(signed)
    )
    assert verdict["status"] == "PREEXISTING_UNOWNED_STATE"
    assert "create_system_account" not in driver.calls
    assert any("already held by group" in reason for reason in verdict["reasons"])


def test_the_uid_contract_cross_checks_the_s2_3_expected_identity_artifact(tmp_path) -> None:
    """數值 UID 無法 pin 到 S2.3(該 artifact 沒有數值欄位),但標籤/角色/non-root 面可以;
    artifact 缺席或被竄改一律 fail-closed。"""

    assert apply_mod.s2_3_expected_identity_reasons() == []
    assert apply_mod.apply_abi_projection()["s2_3_pins_numeric_uid_gid"] is False
    assert apply_mod.s2_3_expected_identity_reasons(repo_root=tmp_path)
    tampered = tmp_path / apply_mod.S2_3_EXPECTED_IDENTITY_REL
    tampered.parent.mkdir(parents=True, exist_ok=True)
    source = json_module.loads(
        (ROOT / apply_mod.S2_3_EXPECTED_IDENTITY_REL).read_text(encoding="utf-8")
    )
    for component in source["expected_component_identities"]:
        if component["component"] == "engine_scanner":
            component["uid_label"] = "postgres"
    tampered.write_text(json_module.dumps(source), encoding="utf-8")
    reasons = apply_mod.s2_3_expected_identity_reasons(repo_root=tmp_path)
    assert any("uid_label" in reason for reason in reasons)


def test_host_identity_compensation_that_leaves_residue_is_recovery_required(signed) -> None:
    """補償的 remove_* 全部「沒拋例外」,但再觀測仍看得到殘留 → 絕不宣稱 COMPENSATED_EXACT。"""

    tree = apply_mod.host_identity_directory_tree()
    intent, manifest = _host_identity_intent()
    driver = _FakeHostIdentityDriver(
        fail_at=tree[-1]["path"], residual_after_compensation={tree[0]["path"]}
    )
    verdict = apply_mod.apply_s2_4_host_identity(
        intent, driver=driver, uid_gid_directory_manifest=manifest, **_common(signed)
    )
    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert verdict["rollback"]["status"] == "RECOVERY_REQUIRED"
    assert verdict["rollback"]["exact_pre_state_restored"] is False


def test_host_identity_manifest_must_bind_the_signed_digest(signed) -> None:
    intent, _ = _host_identity_intent()
    driver = _FakeHostIdentityDriver()
    verdict = apply_mod.apply_s2_4_host_identity(
        intent, driver=driver,
        uid_gid_directory_manifest=apply_mod.build_uid_gid_directory_manifest(uid=1, gid=1),
        **_common(signed),
    )
    assert verdict["status"] == "PRECHECK_FAILED"
    assert driver.calls == []


def test_host_identity_manifest_digest_is_the_only_thing_that_tells_a_from_b(signed) -> None:
    """W5 對抗審計第三輪 P1-F:上面那支同名測試**不是**在證 digest 綁定。

    它遞交的 manifest 是 ``uid=1, gid=1``,而 §8 身分契約(保留 uid 範圍)在 digest 比對
    之後就會拒掉它——把 digest 比對整段換成 ``if False:``,全樹 6111/46 一個都不紅。
    這裡遞交一份**同樣通過 §8 契約**、只是 uid/gid 不是被簽的那一組的 manifest:能區分 A 與 B
    的東西只剩「manifest 的正規 digest 必須等於被簽 intent 裡的那一個」。移除該綁定後,
    applier 會帶著 caller 自選、未被簽的 uid/gid 走到 ``create_system_account``。
    """

    signed_manifest = apply_mod.build_uid_gid_directory_manifest(uid=_UID, gid=_GID)
    other_manifest = apply_mod.build_uid_gid_directory_manifest(uid=_UID + 7, gid=_GID + 7)
    assert validator.canonical_digest(signed_manifest) != validator.canonical_digest(
        other_manifest
    )
    # B 自己是一份合法的 §8 manifest(否則本測試證的又是契約而不是綁定)。
    assert apply_mod._host_identity_contract_reasons(
        other_manifest["identity"], other_manifest["static_directories"]
    ) == []
    intent = _intent(
        "HOST_IDENTITY_INSTALL",
        {"uid_gid_directory_manifest_digest": validator.canonical_digest(signed_manifest)},
    )
    driver = _FakeHostIdentityDriver()
    verdict = apply_mod.apply_s2_4_host_identity(
        intent, driver=driver, uid_gid_directory_manifest=other_manifest, **_common(signed)
    )
    assert verdict["status"] == "PRECHECK_FAILED", verdict
    assert driver.calls == []
    assert verdict["mutation_performed"] is False


def test_host_identity_manifest_cannot_smuggle_a_worker_chosen_directory(signed) -> None:
    manifest = apply_mod.build_uid_gid_directory_manifest(uid=_UID, gid=_GID)
    manifest["static_directories"].append(
        {"path": "/srv/evil", "owner": "root", "group": "root", "mode": "0777"}
    )
    intent = _intent(
        "HOST_IDENTITY_INSTALL",
        {"uid_gid_directory_manifest_digest": validator.canonical_digest(manifest)},
    )
    driver = _FakeHostIdentityDriver()
    verdict = apply_mod.apply_s2_4_host_identity(
        intent, driver=driver, uid_gid_directory_manifest=manifest, **_common(signed)
    )
    assert verdict["status"] == "PRECHECK_FAILED"
    assert driver.calls == []


