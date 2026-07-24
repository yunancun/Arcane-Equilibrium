"""Hermetic structural tests for the LR2 sealed-build + expected-identity binder (S2.3).

No file IO against the real lock and no network: these exercise the
builder/validator/schema roundtrip for BOTH receipts, the flipped S1.4 consts
(real_ml_closure_resolved / reproducible_output_verified true; launch isolated),
the const-false boundary / load / production / running flags, the runtime_content
re-derivation crux, the S1.3 component projection + negative-ACL binding, digest
forgery, and the real committed S1 lineage bindings.  The offline evidence (a
parsed hash-pinned closure, determinism) is proven in the ``_offline`` module.
"""

from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

import agent_governance_sealed_build as sb  # noqa: E402
import agent_governance_identity_acl_contract as s1_3  # noqa: E402
from agent_governance_schema import schema_subset_errors  # noqa: E402


SEALED_SCHEMA_PATH = (
    ROOT / "program_code/ml_training/schemas/aiml_gate_receipts"
    / "sealed_build_receipt_v1.schema.json"
)
EXPECTED_IDENTITY_SCHEMA_PATH = (
    ROOT / "program_code/ml_training/schemas/aiml_gate_receipts"
    / "expected_identity_receipt_v1.schema.json"
)
OBS = datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc).isoformat()
NOW = (datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=5)).isoformat()


def _digest(seed: str) -> str:
    return "sha256:" + hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _closure(**overrides) -> dict:
    closure = {
        "closure_hash": _digest("fixture-closure"),
        "entries_total": 12,
        "hashed_entries_total": 12,
        "unpinned_count": 0,
        "entries": [],
    }
    closure.update(overrides)
    return closure


def _native() -> list:
    return [
        {"package": "lightgbm", "version": "4.6.0", "wheel_sha256": _digest("lgbm"),
         "load_verified_on_target": False},
        {"package": "onnxruntime", "version": "1.20.0", "wheel_sha256": _digest("ort"),
         "load_verified_on_target": False},
    ]


def _build_sealed(**overrides):
    params = dict(
        caller="E1:S2.3",
        platform=sb.target_platform_block(),
        lock_closure=_closure(),
        native_library_inventory=_native(),
        lock_tool="uv 0.11.26",
        lock_input_ref="requirements-ml.lock",
        # F3:S1.6 digest 格式層(schema-level);S1.4-B digest 必為 committed ground-truth 常量。
        learning_runtime_choice_receipt_digest=sb.learning_runtime_choice_schema_sha256(),
        runtime_candidate_receipt_b_digest=sb.S1_4_RUNTIME_CANDIDATE_B_DIGEST,
        observation_time=OBS,
        ttl_seconds=1800,
    )
    params.update(overrides)
    return sb.build_sealed_build_receipt(**params)


def _build_identity(sealed=None, **overrides):
    sealed = sealed or _build_sealed()
    params = dict(
        caller="E1:S2.3",
        platform=sb.target_platform_block(),
        sealed_build_digest=sealed["self_digest"],
        runtime_content_digest=sealed["runtime_content_digest"],
        # F3:S1.3 digest 必為 committed ground-truth 常量。
        identity_acl_contract_digest=sb.S1_3_IDENTITY_ACL_RECEIPT_DIGEST,
        observation_time=OBS,
        ttl_seconds=1800,
    )
    params.update(overrides)
    return sb.build_expected_identity_receipt(**params)


def _sealed_schema() -> dict:
    return json.loads(SEALED_SCHEMA_PATH.read_text(encoding="utf-8"))


def _identity_schema() -> dict:
    return json.loads(EXPECTED_IDENTITY_SCHEMA_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# sealed_build_receipt: builder -> validator -> schema PASS roundtrip
# --------------------------------------------------------------------------- #
def test_sealed_build_pass_roundtrips_validator_and_schema():
    receipt = _build_sealed()
    assert receipt["status"] == "PASS"
    assert receipt["failure_reason"] is None
    assert set(receipt) == sb.SEALED_RECEIPT_FIELDS
    assert sb.validate_sealed_build_receipt(receipt, require_success=True, now=NOW) == []
    schema = _sealed_schema()
    assert schema_subset_errors(receipt, schema, schema) == []


def test_sealed_build_flips_the_three_s1_4_deferred_consts():
    receipt = _build_sealed()
    assert receipt["dependency_closure"]["real_ml_closure_resolved"] is True
    assert receipt["dependency_closure"]["unpinned_count"] == 0
    assert receipt["sealed_input"]["reproducible_output_verified"] is True
    assert receipt["launch"]["python_isolated_mode"] is True
    assert receipt["launch"]["launch_interpreter"] == "absolute_pinned"
    assert receipt["launch"]["system_python_fallback_possible"] is False


def test_sealed_build_boundary_and_load_stay_false():
    receipt = _build_sealed()
    boundary = receipt["boundary"]
    assert boundary["production_installed"] is False
    assert boundary["production_running_attested"] is False
    assert boundary["target_host_loaded"] is False
    assert boundary["nine_authorities_false"] is True
    for record in receipt["native_library_inventory"]:
        assert record["load_verified_on_target"] is False


def test_sealed_build_binds_source_schema_self_digests():
    receipt = _build_sealed()
    assert receipt["source_sha256"] == sb.source_sha256()
    assert receipt["schema_sha256"] == sb.sealed_schema_sha256()
    assert receipt["self_digest"] == sb.receipt_digest(receipt)


def test_runtime_content_digest_is_independently_rederivable():
    receipt = _build_sealed()
    recomputed = sb.runtime_content_digest(
        closure_hash=receipt["closure_hash"],
        isolated_launch_config=receipt["launch"],
        native_lib_inventory_digest=sb.canonical_digest(receipt["native_library_inventory"]),
        python_version=receipt["platform"]["python_version"],
        target_platform=receipt["platform"]["target_platform"],
    )
    assert receipt["runtime_content_digest"] == recomputed


def test_forged_runtime_content_digest_is_rejected():
    forged = deepcopy(_build_sealed())
    forged["runtime_content_digest"] = _digest("not-the-real-content")
    forged["self_digest"] = sb.receipt_digest(forged)
    errors = sb.validate_sealed_build_receipt(forged)
    assert any("independent re-derivation" in e for e in errors)


@pytest.mark.parametrize(
    "path,leaf,bad",
    [
        (("dependency_closure",), "real_ml_closure_resolved", False),
        (("sealed_input",), "reproducible_output_verified", False),
        (("sealed_input",), "mutable_tag_or_alias", True),
        # F7:先前未逐一覆蓋的高價值 const-forgery。
        (("sealed_input",), "relocatable_renamed_venv", True),
        (("launch",), "python_isolated_mode", False),
        (("launch",), "system_python_fallback_possible", True),
        (("launch",), "launch_interpreter", "/usr/bin/python3"),
        (("launch",), "ignores_ambient_env", False),
        (("boundary",), "production_installed", True),
        (("boundary",), "production_running_attested", True),
        (("boundary",), "target_host_loaded", True),
        (("boundary",), "nine_authorities_false", False),
    ],
)
def test_forged_sealed_const_fails_schema_and_validator(path, leaf, bad):
    # 接受的 breadth 註記(F7):此列涵蓋「re-sign 後可偷改的高價值 const」(launch/sealed_input/boundary/
    # dependency_closure 的布林與 launch_interpreter 字串)。其餘 const 欄位(schema_version/adapter_id/
    # selected_runtime_kind/native load_verified_on_target/unpinned_count 等)由 schema `const` 層在
    # schema_subset_errors 一律攔下(本測試同時斷言 schema != [] 佐證),或另有專屬負例覆蓋,不逐一重列。
    forged = deepcopy(_build_sealed())
    node = forged
    for key in path:
        node = node[key]
    node[leaf] = bad
    forged["self_digest"] = sb.receipt_digest(forged)
    schema = _sealed_schema()
    assert schema_subset_errors(forged, schema, schema) != []
    assert sb.validate_sealed_build_receipt(forged) != []


def test_forged_native_load_verified_true_is_rejected():
    forged = deepcopy(_build_sealed())
    assert forged["native_library_inventory"]
    forged["native_library_inventory"][0]["load_verified_on_target"] = True
    forged["self_digest"] = sb.receipt_digest(forged)
    schema = _sealed_schema()
    assert schema_subset_errors(forged, schema, schema) != []
    assert any("load_verified_on_target" in e for e in sb.validate_sealed_build_receipt(forged))


def test_sealed_build_refuses_unpinned_or_unhashed_closure():
    with pytest.raises(sb.LockClosureError):
        _build_sealed(lock_closure=_closure(unpinned_count=1))
    with pytest.raises(sb.LockClosureError):
        _build_sealed(lock_closure=_closure(hashed_entries_total=11))


def test_sealed_build_tamper_breaks_self_digest():
    forged = deepcopy(_build_sealed())
    forged["caller"] = "someone-else"
    assert any("self_digest" in e for e in sb.validate_sealed_build_receipt(forged))


def test_sealed_build_rejects_mismatched_source_and_schema_binding():
    for field in ("source_sha256", "schema_sha256"):
        forged = deepcopy(_build_sealed())
        forged[field] = "sha256:" + "0" * 64
        forged["self_digest"] = sb.receipt_digest(forged)
        assert any("does not bind" in e for e in sb.validate_sealed_build_receipt(forged))


def test_sealed_build_field_set_is_closed():
    forged = deepcopy(_build_sealed())
    forged["extra_field"] = "smuggled"
    forged["self_digest"] = sb.receipt_digest(forged)
    assert any("fields mismatch" in e for e in sb.validate_sealed_build_receipt(forged))


@pytest.mark.parametrize("ttl", [0, -1, 3601, 7200, True, 1.5])
def test_sealed_build_ttl_outside_bound_refuses(ttl):
    with pytest.raises(ValueError):
        _build_sealed(ttl_seconds=ttl)


def test_sealed_build_refuses_injected_secret():
    with pytest.raises(sb.SecretLeakageError):
        _build_sealed(caller="password=hunter2supersecret")


def test_sealed_build_validator_rescans_for_secret():
    poisoned = deepcopy(_build_sealed())
    poisoned["lock_input_ref"] = "authorization: Bearer abcdef0123456789xyz"
    poisoned["self_digest"] = sb.receipt_digest(poisoned)
    assert any("secret-like" in e for e in sb.validate_sealed_build_receipt(poisoned))


def test_sealed_forged_s1_4b_binding_is_rejected():
    # F3:runtime_candidate_receipt_b_digest 離線鎖定 committed ground-truth;非 canonical 值(即使 re-sign)被拒。
    forged = deepcopy(_build_sealed())
    forged["runtime_candidate_receipt_b_digest"] = _digest("not-the-committed-s1.4-b")
    forged["self_digest"] = sb.receipt_digest(forged)
    assert any("S1.4-B ground-truth" in e for e in sb.validate_sealed_build_receipt(forged))


def test_sealed_selected_runtime_kind_const_and_forgery_rejected():
    # F6b:selected_runtime_kind 記錄 S1.6 選定 runtime(非裝飾);偽造 → schema + validator 皆拒。
    receipt = _build_sealed()
    assert receipt["selected_runtime_kind"] == "content_addressed_fixed_path"
    assert receipt["selected_runtime_kind"] == sb.SELECTED_RUNTIME_KIND
    forged = deepcopy(receipt)
    forged["selected_runtime_kind"] = "exact_image_id_oci"
    forged["self_digest"] = sb.receipt_digest(forged)
    schema = _sealed_schema()
    assert schema_subset_errors(forged, schema, schema) != []
    assert any("selected_runtime_kind" in e for e in sb.validate_sealed_build_receipt(forged))


def test_sealed_fail_branch_and_pass_with_failure_reason():
    # F7:行使 vestigial FAIL-status 分支——hand-built FAIL(consts 完整 + 非空 failure_reason)結構有效;
    # PASS 卻帶 failure_reason 被拒。builder 本身恆發 PASS(違反 const 者 fail-closed raise,見上)。
    fail_receipt = deepcopy(_build_sealed())
    fail_receipt["status"] = "FAIL"
    fail_receipt["failure_reason"] = "synthetic fail for branch coverage"
    fail_receipt["self_digest"] = sb.receipt_digest(fail_receipt)
    schema = _sealed_schema()
    assert schema_subset_errors(fail_receipt, schema, schema) == []
    assert sb.validate_sealed_build_receipt(fail_receipt) == []
    bad_pass = deepcopy(_build_sealed())
    bad_pass["failure_reason"] = "should not be here"
    bad_pass["self_digest"] = sb.receipt_digest(bad_pass)
    assert any("cannot carry a failure_reason" in e for e in sb.validate_sealed_build_receipt(bad_pass))


# --------------------------------------------------------------------------- #
# expected_identity_receipt: builder -> validator -> schema PASS roundtrip
# --------------------------------------------------------------------------- #
def test_expected_identity_pass_roundtrips_validator_and_schema():
    receipt = _build_identity()
    assert receipt["status"] == "PASS"
    assert receipt["failure_reason"] is None
    assert receipt["observation_owner"] == "S2.5_LR6"
    assert set(receipt) == sb.EXPECTED_IDENTITY_RECEIPT_FIELDS
    assert sb.validate_expected_identity_receipt(receipt, require_success=True, now=NOW) == []
    schema = _identity_schema()
    assert schema_subset_errors(receipt, schema, schema) == []


def test_expected_identity_projects_the_five_s1_3_components():
    receipt = _build_identity()
    rows = {row["component"]: row for row in receipt["expected_component_identities"]}
    assert set(rows) == set(s1_3.COMPONENTS)
    contract = s1_3.canonical_identity_acl_contract()
    role_by_component = {r["component"]: r for r in contract["pg_role_topology"]}
    for component, row in rows.items():
        assert row["uid_label"] == s1_3.CANONICAL_UID_LABEL[component]
        assert row["pg_role"] == role_by_component[component]["role_name"]
        assert row["privilege_class"] == s1_3.CANONICAL_PRIVILEGE_CLASS[component]
        assert row["oci_socket_access"] is False
        assert row["dbus_authority"] is False
        assert row["non_root"] is True


def test_expected_identity_negative_binding_projects_ten_s1_3_over_grants():
    receipt = _build_identity()
    binding = receipt["negative_acl_binding"]
    assert binding["count"] == len(s1_3.OVER_GRANT_KINDS)
    assert binding["count"] >= 10
    assert binding["all_rejected"] is True
    assert binding["s1_3_negatives_digest"] == sb.canonical_digest(list(s1_3.OVER_GRANT_KINDS))


def test_expected_identity_all_production_and_running_flags_false():
    receipt = _build_identity()
    assert all(v is False for v in receipt["production_provisioned"].values())
    assert all(v is False for v in receipt["running_attested"].values())
    assert all(v is True for v in receipt["least_privilege_assertions"].values())


@pytest.mark.parametrize(
    "component_field",
    ["uid_label", "pg_role", "privilege_class", "auth_method", "socket_dir_mode", "protected_secret_loader"],
)
def test_expected_identity_component_mislabel_is_rejected(component_field):
    forged = deepcopy(_build_identity())
    # 把 controller 列的某欄改成 serving 的值(或無效值),打破 S1.3 投影一致性。
    row = next(r for r in forged["expected_component_identities"] if r["component"] == "controller")
    if component_field == "privilege_class":
        row[component_field] = "serving_read_only"
    elif component_field == "auth_method":
        row[component_field] = "authenticated_loopback"
    elif component_field == "socket_dir_mode":
        row[component_field] = "0755"
    else:
        row[component_field] = "wrong-" + str(row[component_field])
    forged["self_digest"] = sb.receipt_digest(forged)
    assert any("does not match the bound" in e for e in sb.validate_expected_identity_receipt(forged))


@pytest.mark.parametrize("leaf", ["oci_socket_access", "dbus_authority"])
def test_expected_identity_component_oci_or_dbus_true_is_rejected(leaf):
    forged = deepcopy(_build_identity())
    forged["expected_component_identities"][0][leaf] = True
    forged["self_digest"] = sb.receipt_digest(forged)
    schema = _identity_schema()
    assert schema_subset_errors(forged, schema, schema) != []
    assert sb.validate_expected_identity_receipt(forged) != []


def test_expected_identity_dropped_component_is_rejected():
    forged = deepcopy(_build_identity())
    forged["expected_component_identities"] = forged["expected_component_identities"][:4]
    forged["self_digest"] = sb.receipt_digest(forged)
    assert any("exactly the S1.3 sealed set" in e for e in sb.validate_expected_identity_receipt(forged))


def test_expected_identity_forged_negative_count_below_ten_is_rejected():
    forged = deepcopy(_build_identity())
    forged["negative_acl_binding"]["count"] = 9
    forged["self_digest"] = sb.receipt_digest(forged)
    schema = _identity_schema()
    assert schema_subset_errors(forged, schema, schema) != []
    assert any("count must be an integer >= 10" in e for e in sb.validate_expected_identity_receipt(forged))


def test_expected_identity_forged_negatives_digest_is_rejected():
    forged = deepcopy(_build_identity())
    forged["negative_acl_binding"]["s1_3_negatives_digest"] = _digest("wrong-negatives")
    forged["self_digest"] = sb.receipt_digest(forged)
    assert any("s1_3_negatives_digest does not bind" in e for e in sb.validate_expected_identity_receipt(forged))


@pytest.mark.parametrize("block", ["production_provisioned", "running_attested"])
def test_expected_identity_forged_provisioned_or_running_true_is_rejected(block):
    forged = deepcopy(_build_identity())
    leaf = next(iter(forged[block]))
    forged[block][leaf] = True
    forged["self_digest"] = sb.receipt_digest(forged)
    schema = _identity_schema()
    assert schema_subset_errors(forged, schema, schema) != []
    assert sb.validate_expected_identity_receipt(forged) != []


def test_expected_identity_forged_observation_owner_is_rejected():
    forged = deepcopy(_build_identity())
    forged["observation_owner"] = "E1_self_attest"
    forged["self_digest"] = sb.receipt_digest(forged)
    schema = _identity_schema()
    assert schema_subset_errors(forged, schema, schema) != []
    assert any("observation_owner" in e for e in sb.validate_expected_identity_receipt(forged))


def test_expected_identity_rollback_binds_s1_3_change_kinds():
    receipt = _build_identity()
    binding = receipt["rollback_binding"]
    assert binding["rollback_present"] is True
    assert binding["change_kinds"] == sorted(s1_3.CHANGE_KINDS)
    assert binding["rollback_digest"] == sb.canonical_digest(sorted(s1_3.CHANGE_KINDS))


def test_expected_identity_tamper_breaks_self_digest():
    forged = deepcopy(_build_identity())
    forged["caller"] = "someone-else"
    assert any("self_digest" in e for e in sb.validate_expected_identity_receipt(forged))


def test_expected_identity_forged_s1_3_binding_is_rejected():
    # F3:identity_acl_contract_digest 離線鎖定 committed ground-truth;非 canonical 值(即使 re-sign)被拒。
    forged = deepcopy(_build_identity())
    forged["identity_acl_contract_digest"] = _digest("not-the-committed-s1.3")
    forged["self_digest"] = sb.receipt_digest(forged)
    assert any("S1.3 ground-truth" in e for e in sb.validate_expected_identity_receipt(forged))


def test_expected_identity_selected_runtime_kind_const_and_forgery_rejected():
    receipt = _build_identity()
    assert receipt["selected_runtime_kind"] == "content_addressed_fixed_path"
    forged = deepcopy(receipt)
    forged["selected_runtime_kind"] = "exact_image_id_oci"
    forged["self_digest"] = sb.receipt_digest(forged)
    schema = _identity_schema()
    assert schema_subset_errors(forged, schema, schema) != []
    assert any("selected_runtime_kind" in e for e in sb.validate_expected_identity_receipt(forged))


def test_expected_identity_paired_sealed_binding_catches_swap():
    # F2c / FORGERY C:提供配對 sealed_receipt 時,swapped sealed_build_digest / runtime_content_digest 被抓。
    sealed = _build_sealed()
    identity = _build_identity(sealed=sealed)
    assert sb.validate_expected_identity_receipt(identity, sealed_receipt=sealed) == []
    forged = deepcopy(identity)
    forged["sealed_build_digest"] = _digest("swapped-sealed")
    forged["self_digest"] = sb.receipt_digest(forged)
    assert any(
        "sealed_build_digest does not bind" in e
        for e in sb.validate_expected_identity_receipt(forged, sealed_receipt=sealed)
    )
    forged2 = deepcopy(identity)
    forged2["runtime_content_digest"] = _digest("swapped-content")
    forged2["self_digest"] = sb.receipt_digest(forged2)
    assert any(
        "runtime_content_digest does not match the paired" in e
        for e in sb.validate_expected_identity_receipt(forged2, sealed_receipt=sealed)
    )


# --------------------------------------------------------------------------- #
# real committed S1 lineage bindings (also validates BOTH emitted receipts)
# --------------------------------------------------------------------------- #
def test_emitted_real_receipts_bind_committed_s1_lineage():
    sealed, identity = sb.emit_s23_receipts(observation_time=OBS)
    # S1.4-B + S1.3 bind the real committed digests recorded in the S1.5 rollup.
    assert sealed["runtime_candidate_receipt_b_digest"] == sb.S1_4_RUNTIME_CANDIDATE_B_DIGEST
    assert identity["identity_acl_contract_digest"] == sb.S1_3_IDENTITY_ACL_RECEIPT_DIGEST
    # S1.6 runtime-choice receipt is disposable/uncommitted -> schema-level binding.
    assert sealed["learning_runtime_choice_receipt_digest"] == sb.learning_runtime_choice_schema_sha256()
    # expected-identity binds the sealed build it projects onto.
    assert identity["sealed_build_digest"] == sealed["self_digest"]
    assert identity["runtime_content_digest"] == sealed["runtime_content_digest"]
    assert sb.validate_sealed_build_receipt(sealed, require_success=True) == []
    assert sb.validate_expected_identity_receipt(identity, require_success=True) == []
    # real closure stats are truthful.
    assert sealed["dependency_closure"]["unpinned_count"] == 0
    assert sealed["dependency_closure"]["entries_total"] == sealed["dependency_closure"]["hashed_entries_total"]


def test_identity_constants_are_stable():
    assert sb.ADAPTER_ID == "sealed_build_adapter_v1"
    assert sb.SEALED_SCHEMA_VERSION == "sealed_build_receipt_v1"
    assert sb.EXPECTED_IDENTITY_SCHEMA_VERSION == "expected_identity_receipt_v1"
    assert sb.TTL_CEILING_SECONDS == 3600
    assert sb.TARGET_PLATFORM == "x86_64-unknown-linux-gnu"
    assert sb.SELECTED_RUNTIME_KIND == "content_addressed_fixed_path"
