"""Hermetic structural tests for the LR0B identity/ACL contract Adapter (S1.3).

No PostgreSQL server and no real host mutation here; these exercise the crux
negative-ACL checker (the nine §8 over-grant rows = ten over_grant_kinds), the
declarative least-privilege topology, the builder/validator roundtrip, digest
binding, TTL/time ordering, the fail-closed rejections (production target,
production_*_provisioned, secret ingress, non-denial rotation code, over-grant
not rejected) and the machine-false production flags.  The real disposable
SQLSTATEs (42501 / 28P01) and socket-dir mode are proven in the ``_disposable``
module.
"""

from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

import agent_governance_identity_acl_contract as adapter  # noqa: E402
from agent_governance_schema import schema_subset_errors  # noqa: E402


SCHEMA_PATH = (
    ROOT
    / "program_code/ml_training/schemas/aiml_gate_receipts"
    / "identity_acl_contract_receipt_v1.schema.json"
)
OBS = datetime(2026, 7, 22, 12, 0, 0, tzinfo=timezone.utc).isoformat()
NOW = (datetime(2026, 7, 22, 12, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=5)).isoformat()


def _build(**overrides):
    params = dict(
        caller="E1:S1.3",
        platform={"os": "darwin", "arch": "arm64", "postgres_version": "16.14"},
        target_class="disposable_local",
        contract=adapter.canonical_identity_acl_contract(),
        observation_time=OBS,
        ttl_seconds=3600,
        evidence_class="STRUCTURAL_ONLY",
    )
    params.update(overrides)
    return adapter.build_identity_acl_contract_receipt(**params)


def _live_rotation_proof():
    # 用來驅動 _evidence_ceiling 見證機制的一份 live 樣態 proof(單元測試機制,非宣稱真實觀察)。
    return {
        "attempted": "reconnect_with_superseded_credential",
        "observed_sqlstate": "28P01",
        "verdict": "DENIED",
        "observation_source": "live_disposable_pg",
        "new_credential_connected": True,
    }


class _FakeConn:
    def close(self):
        return None


# --------------------------------------------------------------------------- #
# the honest topology is least-privilege
# --------------------------------------------------------------------------- #
def test_canonical_topology_has_no_over_grant():
    contract = adapter.canonical_identity_acl_contract()
    assert adapter.assert_least_privilege_topology(contract) == []


def test_canonical_topology_component_and_role_shape():
    contract = adapter.canonical_identity_acl_contract()
    components = [row["component"] for row in contract["host_uid_topology"]]
    # PM 決策 #3:fit/evaluation 合為單一 fit_evaluation 身分(plan §LR3)。
    assert components == list(adapter.COMPONENTS)
    assert "fit_evaluation" in components
    assert "fit_worker" not in components and "evaluation_worker" not in components
    # S1.1 唯讀觀察身分作為一列被重用。
    role_names = {row["role_name"] for row in contract["pg_role_topology"]}
    assert "aiml_observer_ro" in role_names
    # controller/workers 無 OCI socket、無 DBus。
    for row in contract["host_uid_topology"]:
        if row["component"] in adapter.WORKER_COMPONENTS:
            assert row["oci_socket_access"] is False
            assert row["dbus_authority"] is False


# --------------------------------------------------------------------------- #
# the crux: every over-grant kind is rejected (nine §8 rows = ten kinds)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("kind", adapter.OVER_GRANT_KINDS)
def test_each_over_grant_is_rejected_by_the_checker(kind):
    mutated = adapter.OVER_GRANT_MUTATORS[kind](
        copy.deepcopy(adapter.canonical_identity_acl_contract())
    )
    errors = adapter.assert_least_privilege_topology(mutated)
    assert errors, f"{kind} mutation was not rejected"
    assert adapter._over_grant_detected(errors, kind), f"{kind} not the flagged over-grant"


def test_pass_receipt_records_all_ten_crux_over_grants_rejected():
    receipt = _build()
    assert receipt["status"] == "PASS"
    kinds = {case["over_grant_kind"] for case in receipt["negative_acl_cases"]}
    assert kinds == adapter.CRUX_OVER_GRANT_KINDS
    assert len(receipt["negative_acl_cases"]) == 10
    for case in receipt["negative_acl_cases"]:
        assert case["expected"] == "FAIL_CLOSED"
        assert case["observed_verdict"] == "REJECTED"


def test_vacuous_checker_refuses_to_certify(monkeypatch):
    # 若 checker 對某個過度授權沒回報錯誤(vacuous),builder 必須 raise 而非發 PASS。
    monkeypatch.setattr(adapter, "assert_least_privilege_topology", lambda contract: [])
    with pytest.raises(adapter.LeastPrivilegeError):
        adapter.build_negative_acl_cases(adapter.canonical_identity_acl_contract())


def test_over_granting_honest_topology_refuses_to_build():
    # 誠實拓撲本身若帶過度授權(如 root uid),builder fail-closed raise。
    contract = adapter.canonical_identity_acl_contract()
    contract["host_uid_topology"][0]["non_root"] = False
    with pytest.raises(adapter.LeastPrivilegeError):
        _build(contract=contract)


# --------------------------------------------------------------------------- #
# builder -> validator PASS roundtrip + digest binding
# --------------------------------------------------------------------------- #
def test_pass_receipt_roundtrips_through_validator_and_schema():
    receipt = _build()
    assert receipt["status"] == "PASS"
    assert receipt["target_class"] == "disposable_local"
    assert receipt["evidence_class"] == "STRUCTURAL_ONLY"
    assert receipt["failure_reason"] is None
    assert set(receipt) == adapter.RECEIPT_FIELDS
    assert adapter.validate_identity_acl_contract_receipt(
        receipt, require_success=True, now=NOW
    ) == []
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema_subset_errors(receipt, schema, schema) == []


def test_pass_receipt_binds_source_and_schema_and_self_digest():
    receipt = _build()
    assert receipt["source_sha256"] == adapter.source_sha256()
    assert receipt["schema_sha256"] == adapter.schema_sha256()
    assert receipt["self_digest"] == adapter.receipt_digest(receipt)


def test_tampered_field_breaks_self_digest():
    receipt = _build()
    tampered = copy.deepcopy(receipt)
    tampered["caller"] = "someone-else"
    errors = adapter.validate_identity_acl_contract_receipt(tampered)
    assert any("self_digest" in error for error in errors)


def test_validator_rejects_mismatched_source_sha256():
    receipt = _build()
    tampered = copy.deepcopy(receipt)
    tampered["source_sha256"] = "sha256:" + "0" * 64
    tampered["self_digest"] = adapter.receipt_digest(tampered)
    errors = adapter.validate_identity_acl_contract_receipt(tampered)
    assert any("source_sha256 does not bind" in error for error in errors)


def test_validator_rejects_mismatched_schema_sha256():
    receipt = _build()
    tampered = copy.deepcopy(receipt)
    tampered["schema_sha256"] = "sha256:" + "0" * 64
    tampered["self_digest"] = adapter.receipt_digest(tampered)
    errors = adapter.validate_identity_acl_contract_receipt(tampered)
    assert any("schema_sha256 does not bind" in error for error in errors)


# --------------------------------------------------------------------------- #
# TTL / time ordering
# --------------------------------------------------------------------------- #
def test_ttl_and_time_ordering_are_bound():
    receipt = _build(ttl_seconds=1800)
    observed = datetime.fromisoformat(receipt["observation_time"])
    expires = datetime.fromisoformat(receipt["expires_at"])
    assert (expires - observed) == timedelta(seconds=1800)
    stale_now = (expires + timedelta(seconds=1)).isoformat()
    errors = adapter.validate_identity_acl_contract_receipt(receipt, now=stale_now)
    assert any("fresh" in error for error in errors)


def test_internal_temporal_consistency_enforced_without_now():
    receipt = _build(ttl_seconds=1800)
    tampered = copy.deepcopy(receipt)
    observed = datetime.fromisoformat(tampered["observation_time"])
    tampered["expires_at"] = (observed + timedelta(seconds=1801)).isoformat()
    tampered["self_digest"] = adapter.receipt_digest(tampered)
    errors = adapter.validate_identity_acl_contract_receipt(tampered, now=None)
    assert any("expires_at does not equal" in error for error in errors)


@pytest.mark.parametrize("ttl", [0, -1, 3601, 7200, True, 1.5])
def test_ttl_outside_bound_refuses_to_build(ttl):
    with pytest.raises(ValueError):
        _build(ttl_seconds=ttl)


# --------------------------------------------------------------------------- #
# evidence-ceiling consistency
# --------------------------------------------------------------------------- #
def test_structural_only_ceiling_still_passes():
    # S1.3 與 S1.1 不同:STRUCTURAL_ONLY 的誠實契約也可 PASS(crux 是結構可證的)。
    receipt = _build(evidence_class="STRUCTURAL_ONLY")
    assert receipt["status"] == "PASS"
    assert receipt["evidence_class"] == "STRUCTURAL_ONLY"


def test_bare_evidence_class_label_alone_does_not_lift_ceiling():
    # (item #4 誠實化)天花板只認較具體的 observation_source/mode_source 顧問標籤,不認裸 evidence_class
    # 欄位:純結構契約=STRUCTURAL_ONLY;帶上 observation_source=live_disposable_pg 標籤才升為
    # LOCAL_REPRODUCIBLE。這只擋「最懶的單欄升級」——該來源標籤本身仍是呼叫端可自設、非自我認證的,
    # 真確性需消費端 _disposable 重跑或平台背書(見模組 docstring 的 Consumer contract),自雜湊 receipt
    # 無法證明自身執行。
    structural = adapter.canonical_identity_acl_contract()
    assert adapter._evidence_ceiling(structural) == "STRUCTURAL_ONLY"
    assert adapter._has_live_disposable_witness(structural) is False
    live = adapter.canonical_identity_acl_contract(old_credential_rejection_proof=_live_rotation_proof())
    assert adapter._evidence_ceiling(live) == "LOCAL_REPRODUCIBLE"
    assert adapter._has_live_disposable_witness(live) is True


def test_hermetic_receipt_cannot_claim_local_reproducible():
    # (item #4)純結構契約(default 28P01/0700,無 live 見證)宣稱 LOCAL_REPRODUCIBLE → FAIL,
    # 絕不能被當作 LOCAL_REPRODUCIBLE PASS(structural-only content → STRUCTURAL_ONLY ceiling)。
    contract = adapter.canonical_identity_acl_contract()
    assert adapter._evidence_ceiling(contract) == "STRUCTURAL_ONLY"
    receipt = _build(contract=contract, evidence_class="LOCAL_REPRODUCIBLE")
    assert receipt["status"] == "FAIL"
    assert "strongest non-deferred facet" in receipt["failure_reason"]


def test_evidence_class_below_ceiling_is_failed():
    contract = adapter.canonical_identity_acl_contract(old_credential_rejection_proof=_live_rotation_proof())
    assert adapter._evidence_ceiling(contract) == "LOCAL_REPRODUCIBLE"
    receipt = _build(contract=contract, evidence_class="STRUCTURAL_ONLY")
    assert receipt["status"] == "FAIL"
    assert "strongest non-deferred facet" in receipt["failure_reason"]


# --------------------------------------------------------------------------- #
# fail-closed policy verdicts (emit an honest FAIL receipt)
# --------------------------------------------------------------------------- #
def test_production_target_is_rejected_fail_closed():
    receipt = _build(target_class="production")
    assert receipt["status"] == "FAIL"
    assert receipt["failure_reason"]
    errors = adapter.validate_identity_acl_contract_receipt(receipt)
    assert any("disposable_local" in error for error in errors)
    # 即便硬塞 status=PASS 也無法通過 schema(production 永不 PASS)。
    forged = copy.deepcopy(receipt)
    forged["status"] = "PASS"
    forged["failure_reason"] = None
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema_subset_errors(forged, schema, schema) != []


# --------------------------------------------------------------------------- #
# fail-closed integrity violations (refuse to emit)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "facet,flag",
    [
        ("host_uid_topology", "production_uid_provisioned"),
        ("pg_role_topology", "production_role_provisioned"),
        ("socket_dir_acl", "production_socket_provisioned"),
    ],
)
def test_production_provisioned_flag_true_refuses_to_build(facet, flag):
    contract = adapter.canonical_identity_acl_contract()
    contract[facet][0][flag] = True
    with pytest.raises(adapter.IdentityAclContractError):
        _build(contract=contract)


def test_production_hba_installed_true_refuses_to_build():
    contract = adapter.canonical_identity_acl_contract()
    contract["auth_mapping"]["production_hba_installed"] = True
    with pytest.raises(adapter.IdentityAclContractError):
        _build(contract=contract)


def test_production_credential_rotated_true_refuses_to_build():
    contract = adapter.canonical_identity_acl_contract()
    contract["secret_lifecycle"]["production_credential_rotated"] = True
    with pytest.raises(adapter.IdentityAclContractError):
        _build(contract=contract)


def test_non_denial_rotation_code_refuses_to_build():
    # rotation 拒絕碼若非憑證拒絕類(28P01/28000),不可作為 old-credential 拒絕證明 → raise。
    contract = adapter.canonical_identity_acl_contract()
    contract["secret_lifecycle"]["rotation"]["old_credential_rejection_proof"]["observed_sqlstate"] = "00000"
    with pytest.raises(adapter.IdentityAclContractError):
        _build(contract=contract)


def test_equal_rotation_fingerprints_refuse_to_build():
    contract = adapter.canonical_identity_acl_contract()
    same = adapter.canonical_digest({"same": "fingerprint"})
    contract["secret_lifecycle"]["rotation"]["old_fingerprint"] = same
    contract["secret_lifecycle"]["rotation"]["new_fingerprint"] = same
    with pytest.raises(ValueError):
        _build(contract=contract)


# --------------------------------------------------------------------------- #
# secret scan / redaction
# --------------------------------------------------------------------------- #
def test_builder_refuses_to_serialize_an_injected_secret():
    with pytest.raises(adapter.SecretLeakageError):
        _build(caller="PGPASSWORD=hunter2supersecretvalue")


def test_secret_guard_detects_github_and_auth_families():
    assert adapter._contains_secret_like("github_pat_" + "A" * 22)
    assert adapter._contains_secret_like("Bearer abcdef0123456789xyz")
    with pytest.raises(adapter.SecretLeakageError):
        _build(caller="ghp_" + "C" * 20)


def test_plaintext_secret_in_contract_refuses_to_build():
    contract = adapter.canonical_identity_acl_contract()
    # DSN 於 runtime 在 "@" 處拼接,避免公開倉庫 secret scanner 對測試夾具誤報。
    contract["secret_lifecycle"]["rotation"]["secret_slot_target"] = (
        "postgresql://u:realsecretpw" + "@h:5432/db"
    )
    with pytest.raises(adapter.SecretLeakageError):
        _build(contract=contract)


def test_validator_rescans_for_embedded_secret():
    receipt = _build()
    poisoned = copy.deepcopy(receipt)
    poisoned["caller"] = "password=leakedsecretvalue"
    poisoned["self_digest"] = adapter.receipt_digest(poisoned)
    errors = adapter.validate_identity_acl_contract_receipt(poisoned)
    assert any("secret-like" in error for error in errors)


# --------------------------------------------------------------------------- #
# structural negatives caught by the validator (forged PASS receipts)
# --------------------------------------------------------------------------- #
def test_validator_catches_shared_uid_in_forged_receipt():
    receipt = _build()
    forged = copy.deepcopy(receipt)
    forged["host_uid_topology"][1]["uid_label"] = forged["host_uid_topology"][0]["uid_label"]
    forged["self_digest"] = adapter.receipt_digest(forged)
    errors = adapter.validate_identity_acl_contract_receipt(forged)
    assert any("not distinct" in error for error in errors)


def test_validator_catches_missing_crux_case_in_forged_receipt():
    receipt = _build()
    forged = copy.deepcopy(receipt)
    forged["negative_acl_cases"] = [
        case for case in forged["negative_acl_cases"]
        if case["over_grant_kind"] != "superuser_role"
    ]
    forged["self_digest"] = adapter.receipt_digest(forged)
    errors = adapter.validate_identity_acl_contract_receipt(forged)
    assert any("miss crux over-grants" in error for error in errors)


def test_validator_catches_missing_rollback_kind_in_forged_receipt():
    receipt = _build()
    forged = copy.deepcopy(receipt)
    forged["rollback"] = [rb for rb in forged["rollback"] if rb["change_kind"] != "secret_slot"]
    forged["self_digest"] = adapter.receipt_digest(forged)
    errors = adapter.validate_identity_acl_contract_receipt(forged)
    assert any("missing change_kind secret_slot" in error for error in errors)


def test_all_production_flags_are_machine_false():
    receipt = _build()
    for row in receipt["host_uid_topology"]:
        assert row["production_uid_provisioned"] is False
    for row in receipt["pg_role_topology"]:
        assert row["production_role_provisioned"] is False
    for row in receipt["socket_dir_acl"]:
        assert row["production_socket_provisioned"] is False
    assert receipt["auth_mapping"]["production_hba_installed"] is False
    assert receipt["secret_lifecycle"]["production_credential_rotated"] is False


# --------------------------------------------------------------------------- #
# credential-denial SQLSTATE resolution (pure)
# --------------------------------------------------------------------------- #
def test_resolve_credential_denial_sqlstate_from_message():
    assert adapter.resolve_credential_denial_sqlstate(
        None, 'FATAL:  password authentication failed for user "x"'
    ) == "28P01"
    assert adapter.resolve_credential_denial_sqlstate("28P01", "") == "28P01"
    assert adapter.resolve_credential_denial_sqlstate(None, "unrelated failure") is None


def test_resolve_credential_denial_narrows_generic_and_peer_auth():
    # (item #2)泛化 / peer / ident "authentication failed" 不再被誤映射為 28000。
    assert adapter.resolve_credential_denial_sqlstate(
        None, 'FATAL:  Peer authentication failed for user "x"'
    ) is None
    assert adapter.resolve_credential_denial_sqlstate(None, "authentication failed") is None
    # 明確的 28000 代碼字串(非泛語句)仍可解析。
    assert adapter.resolve_credential_denial_sqlstate("28000", "") == "28000"


def test_mode_privacy_arithmetic():
    assert adapter._mode_is_private("0700") is True
    assert adapter._mode_is_private("0750") is False
    assert adapter._mode_is_private("0777") is False
    assert adapter._mode_is_private("700") is False


def test_adapter_id_and_schema_version_are_constants():
    assert adapter.ADAPTER_ID == "identity_acl_contract_adapter_v1"
    assert adapter.RECEIPT_SCHEMA_VERSION == "identity_acl_contract_receipt_v1"
    assert adapter.TTL_CEILING_SECONDS == 3600


# --------------------------------------------------------------------------- #
# (item #1) exhaustive least-privilege — free-form over-grants are REJECTED
# --------------------------------------------------------------------------- #
def test_over_broad_least_privilege_caps_are_rejected():
    # 危險/未知能力(oci-socket/sudo/read-all-secrets/spawn-container)不在 ALLOWLIST → 拒絕。
    contract = adapter.canonical_identity_acl_contract()
    contract["host_uid_topology"][0]["least_privilege_caps"] = [
        "oci_socket_full", "sudo_all", "read_all_secrets", "spawn_container",
    ]
    errors = adapter.assert_least_privilege_topology(contract)
    assert adapter._over_grant_detected(errors, "over_broad_capability")
    with pytest.raises(adapter.LeastPrivilegeError):
        _build(contract=contract)


def test_unknown_capability_fails_closed():
    contract = adapter.canonical_identity_acl_contract()
    contract["host_uid_topology"][0]["least_privilege_caps"] = ["read_config", "totally_unknown_cap"]
    errors = adapter.assert_least_privilege_topology(contract)
    assert adapter._over_grant_detected(errors, "over_broad_capability")


def test_wildcard_ident_map_to_superuser_is_rejected():
    # auth_mapping.ident_map="all-os-users-to-superuser" 這類 all/wildcard→privileged 映射被拒
    # (S1.3 已收斂為 null-only,任何 non-null 值皆拒)。
    contract = adapter.canonical_identity_acl_contract()
    contract["auth_mapping"]["ident_map"] = "all-os-users-to-superuser"
    errors = adapter.assert_least_privilege_topology(contract)
    assert adapter._over_grant_detected(errors, "unsafe_ident_map")
    with pytest.raises(adapter.LeastPrivilegeError):
        _build(contract=contract)


def test_non_null_ident_map_is_rejected():
    # (item #3a)S1.3 徹底移除 ident_map free-form 攻擊面:任何 non-null ident_map 一律拒絕——
    # 即使搭配 ident 方法、即使形狀有界(有界 ident map 是 S2.4 範疇,非 S1.3)。
    contract = adapter.canonical_identity_acl_contract()
    contract["auth_mapping"]["method"] = "pg_hba_ident_local"  # 即便是 ident 方法
    contract["auth_mapping"]["ident_map"] = "aiml_local_map"    # 有界形狀也拒
    errors = adapter.assert_least_privilege_topology(contract)
    assert adapter._over_grant_detected(errors, "unsafe_ident_map")
    assert any("must be null at S1.3" in e for e in errors)
    with pytest.raises(adapter.LeastPrivilegeError):
        _build(contract=contract)
    # schema 亦僅接受 null:forge 任何字串 ident_map 進 receipt 即 schema 違規。
    receipt = _build()
    forged = copy.deepcopy(receipt)
    forged["auth_mapping"]["ident_map"] = "aiml_local_map"
    forged["self_digest"] = adapter.receipt_digest(forged)
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema_subset_errors(forged, schema, schema) != []


def test_revoke_before_stage_rotation_order_is_rejected():
    # rotation_order=["revoke_old_secret","alter_role_credential"](revoke-before-stage)被拒。
    contract = adapter.canonical_identity_acl_contract()
    contract["secret_lifecycle"]["rotation"]["rotation_order"] = [
        "revoke_old_secret", "alter_role_credential",
    ]
    errors = adapter.assert_least_privilege_topology(contract)
    assert adapter._over_grant_detected(errors, "unsafe_rotation_order")
    with pytest.raises(adapter.LeastPrivilegeError):
        _build(contract=contract)


def test_alter_before_stage_rotation_order_is_rejected():
    contract = adapter.canonical_identity_acl_contract()
    contract["secret_lifecycle"]["rotation"]["rotation_order"] = [
        "alter_role_credential", "stage_new_secret", "revoke_old_secret",
    ]
    errors = adapter.assert_least_privilege_topology(contract)
    assert adapter._over_grant_detected(errors, "unsafe_rotation_order")


def test_rotation_order_without_activate_is_rejected():
    # (item #3b)僅 stage→revoke、缺 alter/activate 步驟的輪換順序被拒:新憑證從未被啟用。
    contract = adapter.canonical_identity_acl_contract()
    contract["secret_lifecycle"]["rotation"]["rotation_order"] = [
        "stage_new_secret", "revoke_old_secret",
    ]
    errors = adapter.assert_least_privilege_topology(contract)
    assert adapter._over_grant_detected(errors, "unsafe_rotation_order")
    assert any("never activated" in e for e in errors)
    with pytest.raises(adapter.LeastPrivilegeError):
        _build(contract=contract)


def test_revoke_before_stage_with_both_tokens_is_rejected():
    # (item #3c/E4)stage 與 revoke 皆存在但 revoke 在 stage 之前(舊憑證在新憑證生效前即被移除)→ 拒。
    contract = adapter.canonical_identity_acl_contract()
    contract["secret_lifecycle"]["rotation"]["rotation_order"] = [
        "revoke_old_secret", "stage_new_secret", "alter_role_credential",
    ]
    errors = adapter.assert_least_privilege_topology(contract)
    assert adapter._over_grant_detected(errors, "unsafe_rotation_order")
    assert any("precedes stage-new" in e for e in errors)


# --------------------------------------------------------------------------- #
# (item #1/E3) socket owner + uid_label are bound to the owning component
# --------------------------------------------------------------------------- #
def test_shared_socket_owner_across_components_is_rejected():
    # 所有 socket dir owner/group 綁成同一元件 UID(單一 owner 橫跨全部元件=跨元件最小權限破壞)→ 拒:
    # owner 非各自元件的正規 UID + owner 跨元件不互異。
    contract = adapter.canonical_identity_acl_contract()
    shared = contract["socket_dir_acl"][0]["owner_uid_label"]
    for sock in contract["socket_dir_acl"]:
        sock["owner_uid_label"] = shared
        sock["group_label"] = shared
    errors = adapter.assert_least_privilege_topology(contract)
    assert adapter._over_grant_detected(errors, "unsafe_socket_owner")
    assert any("not distinct across components" in e for e in errors)
    with pytest.raises(adapter.LeastPrivilegeError):
        _build(contract=contract)


def test_socket_owner_bound_to_owning_component():
    # owner 綁到「別元件」的正規 UID(非自身)→ 拒。
    contract = adapter.canonical_identity_acl_contract()
    for sock in contract["socket_dir_acl"]:
        if sock["component"] == "serving":
            sock["owner_uid_label"] = adapter.CANONICAL_UID_LABEL["controller"]
    errors = adapter.assert_least_privilege_topology(contract)
    assert adapter._over_grant_detected(errors, "unsafe_socket_owner")
    assert any("is not the owning component's host UID" in e for e in errors)


def test_uid_label_naming_root_is_rejected():
    # uid_label="root" 卻宣稱 non_root=true(label 騎在布林值上偷帶 root/特權身分)→ 拒。
    contract = adapter.canonical_identity_acl_contract()
    contract["host_uid_topology"][0]["uid_label"] = "root"
    assert contract["host_uid_topology"][0]["non_root"] is True
    errors = adapter.assert_least_privilege_topology(contract)
    assert adapter._over_grant_detected(errors, "unsafe_uid_label")
    assert any("names a root/privileged identity" in e for e in errors)
    with pytest.raises(adapter.LeastPrivilegeError):
        _build(contract=contract)


# --------------------------------------------------------------------------- #
# (item #2) rotation-proof soundness — the REUSABLE function is sound
# --------------------------------------------------------------------------- #
def test_missing_role_denial_is_not_accepted_as_rotation_proof():
    # 缺 role:新憑證也連不上(scram 下缺 role 回相同 28P01),故拒絕認證為 old-credential 拒絕。
    def new_missing():
        raise Exception('FATAL:  password authentication failed for user "aiml_fit_evaluation"')

    def old_missing():
        raise Exception('FATAL:  password authentication failed for user "aiml_fit_evaluation"')

    with pytest.raises(adapter.LeastPrivilegeError) as excinfo:
        adapter.observe_old_credential_rejection(old_missing, connect_with_new_credential=new_missing)
    assert "new credential did not connect" in str(excinfo.value)


def test_peer_auth_failure_is_not_accepted_as_rotation_proof():
    # peer 認證失敗(新憑證可連,舊憑證回 peer-auth 而非 invalid-password)不得充當輪換證明。
    def new_ok():
        return _FakeConn()

    def old_peer():
        raise Exception('FATAL:  Peer authentication failed for user "aiml_fit_evaluation"')

    with pytest.raises(adapter.LeastPrivilegeError) as excinfo:
        adapter.observe_old_credential_rejection(old_peer, connect_with_new_credential=new_ok)
    assert "invalid-password" in str(excinfo.value)


def test_genuine_old_vs_new_rotation_is_accepted():
    # 唯有真實 old-vs-new(新可連、舊被 28P01 invalid-password 拒)才認證,並帶 live 見證。
    def new_ok():
        return _FakeConn()

    def old_rejected():
        raise Exception('FATAL:  password authentication failed for user "aiml_fit_evaluation"')

    proof = adapter.observe_old_credential_rejection(old_rejected, connect_with_new_credential=new_ok)
    assert proof["observed_sqlstate"] == "28P01"
    assert proof["verdict"] == "DENIED"
    assert proof["observation_source"] == "live_disposable_pg"
    assert proof["new_credential_connected"] is True


def test_accepted_old_credential_is_not_fail_closed():
    def new_ok():
        return _FakeConn()

    def old_accepted():
        return _FakeConn()

    with pytest.raises(adapter.LeastPrivilegeError) as excinfo:
        adapter.observe_old_credential_rejection(old_accepted, connect_with_new_credential=new_ok)
    assert "accepted" in str(excinfo.value)


def test_live_rotation_proof_without_new_connect_refuses_to_build():
    # 建構期不變量:live 標記但 new_credential_connected=False → 不可序列化 → raise。
    unsound = _live_rotation_proof()
    unsound["new_credential_connected"] = False
    contract = adapter.canonical_identity_acl_contract(old_credential_rejection_proof=unsound)
    with pytest.raises(adapter.IdentityAclContractError):
        _build(contract=contract, evidence_class="LOCAL_REPRODUCIBLE")


# --------------------------------------------------------------------------- #
# (item #3) validator independently re-verifies negatives + component completeness
# --------------------------------------------------------------------------- #
def test_validator_independently_catches_over_grant_missed_by_facet_checks():
    # 偽造:注入危險 cap(逐 facet 檢查看不到),validator 獨立重跑 least-privilege 檢查抓到。
    receipt = _build()
    forged = copy.deepcopy(receipt)
    forged["host_uid_topology"][0]["least_privilege_caps"] = ["sudo_all"]
    forged["self_digest"] = adapter.receipt_digest(forged)
    errors = adapter.validate_identity_acl_contract_receipt(forged)
    assert any("reconstructed topology is not least-privilege" in e for e in errors)


def test_validator_rejects_forged_fabricated_rejected_negatives():
    # 偽造:塞入一個重複/捏造的 REJECTED negative case,獨立重推導 kinds 不吻合 → 拒絕。
    receipt = _build()
    forged = copy.deepcopy(receipt)
    forged["negative_acl_cases"] = forged["negative_acl_cases"] + [dict(forged["negative_acl_cases"][0])]
    forged["self_digest"] = adapter.receipt_digest(forged)
    errors = adapter.validate_identity_acl_contract_receipt(forged)
    assert any("independent re-derivation" in e for e in errors)


def test_validator_rejects_dropped_controller_row():
    # 偽造:靜默 drop controller 列(規避 controller 的 non-root/no-OCI/no-DBus 約束)→ 拒絕。
    receipt = _build()
    forged = copy.deepcopy(receipt)
    forged["host_uid_topology"] = [
        row for row in forged["host_uid_topology"] if row["component"] != "controller"
    ]
    forged["self_digest"] = adapter.receipt_digest(forged)
    errors = adapter.validate_identity_acl_contract_receipt(forged)
    assert any("components must be exactly" in e for e in errors)


def test_validator_rejects_single_component_receipt():
    receipt = _build()
    forged = copy.deepcopy(receipt)
    forged["host_uid_topology"] = forged["host_uid_topology"][:1]
    forged["self_digest"] = adapter.receipt_digest(forged)
    errors = adapter.validate_identity_acl_contract_receipt(forged)
    assert any("components must be exactly" in e for e in errors)


def test_validator_rejects_extra_or_duplicate_component():
    receipt = _build()
    forged = copy.deepcopy(receipt)
    forged["host_uid_topology"] = forged["host_uid_topology"] + [dict(forged["host_uid_topology"][0])]
    forged["self_digest"] = adapter.receipt_digest(forged)
    errors = adapter.validate_identity_acl_contract_receipt(forged)
    assert any("duplicate component" in e for e in errors)


def test_validator_rejects_dropped_socket_component():
    # (item E4)component-completeness 偽造:靜默 drop socket_dir_acl 的 controller 列 → 拒。
    receipt = _build()
    forged = copy.deepcopy(receipt)
    forged["socket_dir_acl"] = [
        row for row in forged["socket_dir_acl"] if row["component"] != "controller"
    ]
    forged["self_digest"] = adapter.receipt_digest(forged)
    errors = adapter.validate_identity_acl_contract_receipt(forged)
    assert any("socket_dir_acl components must be exactly" in e for e in errors)


def test_validator_rejects_dropped_pg_role_component():
    # (item E4)component-completeness 偽造:靜默 drop pg_role_topology 的 deleter 列 → 拒。
    receipt = _build()
    forged = copy.deepcopy(receipt)
    forged["pg_role_topology"] = [
        row for row in forged["pg_role_topology"] if row["component"] != "deleter"
    ]
    forged["self_digest"] = adapter.receipt_digest(forged)
    errors = adapter.validate_identity_acl_contract_receipt(forged)
    assert any("pg_role_topology components must be exactly" in e for e in errors)


def test_validator_catches_shared_socket_owner_in_forged_receipt():
    # (item #1/E3)偽造 PASS receipt:所有 socket owner 綁成同一 UID(逐 facet 檢查看不到 cross-component
    # owner 破壞),validator 的重建路徑重跑 least-privilege 檢查抓到。
    receipt = _build()
    forged = copy.deepcopy(receipt)
    shared = forged["socket_dir_acl"][0]["owner_uid_label"]
    for sock in forged["socket_dir_acl"]:
        sock["owner_uid_label"] = shared
        sock["group_label"] = shared
    forged["self_digest"] = adapter.receipt_digest(forged)
    errors = adapter.validate_identity_acl_contract_receipt(forged)
    assert any("reconstructed topology is not least-privilege" in e for e in errors)
    assert any("unsafe_socket_owner" in e for e in errors)


def test_validator_catches_root_uid_label_in_forged_receipt():
    # (item #1/E3)偽造 PASS receipt:uid_label="root" 但 non_root=true;validator 重建路徑抓到特權 label。
    receipt = _build()
    forged = copy.deepcopy(receipt)
    forged["host_uid_topology"][0]["uid_label"] = "root"
    forged["self_digest"] = adapter.receipt_digest(forged)
    errors = adapter.validate_identity_acl_contract_receipt(forged)
    assert any("reconstructed topology is not least-privilege" in e for e in errors)
    assert any("unsafe_uid_label" in e for e in errors)


# --------------------------------------------------------------------------- #
# (item #5) dbus_authority checker branch + (item #7) privilege_class cross-bind
# --------------------------------------------------------------------------- #
def test_dbus_authority_is_rejected_by_the_checker():
    # controller-oci mutator 只翻 oci_socket;此處補 dbus_authority=True 的 checker 分支。
    contract = adapter.canonical_identity_acl_contract()
    for host in contract["host_uid_topology"]:
        if host["component"] == "controller":
            host["dbus_authority"] = True
    errors = adapter.assert_least_privilege_topology(contract)
    assert adapter._over_grant_detected(errors, "controller_oci_socket_or_dbus")
    assert any("DBus authority" in e for e in errors)
    with pytest.raises(adapter.LeastPrivilegeError):
        _build(contract=contract)


def test_validator_rejects_mislabeled_privilege_class():
    # 偽造:把 serving 元件 mislabel 成 queue_writer,validator 依正規綁定擋下。
    receipt = _build()
    forged = copy.deepcopy(receipt)
    for row in forged["pg_role_topology"]:
        if row["component"] == "serving":
            row["privilege_class"] = "queue_writer"
    forged["self_digest"] = adapter.receipt_digest(forged)
    errors = adapter.validate_identity_acl_contract_receipt(forged)
    assert any("privilege_class must be" in e for e in errors)


# --------------------------------------------------------------------------- #
# (item #6) rotation fingerprint is a non-secret slot id, never the raw secret
# --------------------------------------------------------------------------- #
def test_credential_slot_fingerprint_is_non_secret_and_generation_distinct():
    old_fp = adapter.credential_slot_fingerprint("aiml_pg_credential_slot", "old")
    new_fp = adapter.credential_slot_fingerprint("aiml_pg_credential_slot", "new")
    assert adapter.DIGEST_RE.fullmatch(old_fp) and adapter.DIGEST_RE.fullmatch(new_fp)
    assert old_fp != new_fp
    # 指紋只綁非機密槽位身分:相同 slot+generation 可重現(非對原始密碼取雜湊)。
    assert old_fp == adapter.credential_slot_fingerprint("aiml_pg_credential_slot", "old")
