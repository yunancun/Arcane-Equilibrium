"""S2.4(WP4·W1)CP2a/CP2b/CP3/CP4 契約測試(自 test_aiml_gate_receipt_validator.py 拆出)。

2000 行治理拆分:test 函式名與本體逐字保留,僅 import 接線調整。CP4 丟棄式鑰 monkeypatch
仍以 facade 模組物件(_w0 alias)為注入點——與拆分前同一縫。
"""

from __future__ import annotations

import json
import subprocess as _subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ML_ROOT = Path(__file__).resolve().parents[1]
if str(ML_ROOT) not in sys.path:
    sys.path.insert(0, str(ML_ROOT))

from aiml_gate_receipt_validator import (  # noqa: E402
    aiml_effect_classifier_digest,
    artifact_self_digest,
    canonical_digest,
    S2_4_AUTHORIZATION_PROFILES,
    s2_4_authorization_profiles_digest,
    SCHEMA_DIR,
    SCHEMA_FILES,
    validate_aiml_artifact,
)

import aiml_gate_receipt_validator as _w0  # noqa: E402


# ── S2.4 · WP4 · W1 · CP2a(capability-probe + prepare 契約 schema)─────────────
# 這 14 份 closed schema 皆屬「契約」:round-trip 乾淨、additionalProperties 拒外鍵、
# unsigned core 排除 id/auth/self_digest、const-false 生產旗標與 allOf 有牙(不得斷言 runtime PASS)。
_CP2A_D = "sha256:" + "a" * 64
_CP2A_D2 = "sha256:" + "b" * 64
_CP2A_GIT = "0" * 40
_CP2A_TS = "2026-07-24T00:00:00+00:00"


def _cp2a_probe_core() -> dict:
    return {
        "schema_version": "s2_4_capability_probe_core_v1",
        "probe_scope": "PREPARE_SANDBOX",
        "transient_unit_property_digest": _CP2A_D,
        "host_cgroup_identity": {
            "host": "trade-core",
            "cgroup_manager_scope": "system_manager",
            "cgroup_root_pattern": "/sys/fs/cgroup/system.slice",
        },
        "cleanup_budget": {"max_cleanup_seconds": 30, "max_cgroup_drain_seconds": 10},
        "source_head": _CP2A_GIT,
        "target_host": "trade-core",
        "created_at": _CP2A_TS,
    }


def _cp2a_prepare_core() -> dict:
    return {
        "schema_version": "s2_4_prepare_core_v1",
        "staging_root_device_inode": {
            "staging_parent_path": "/var/lib/arcane-equilibrium/aiml/install/s2_4/prepared",
            "device": 66306,
            "inode": 12345,
        },
        "resource_budget": {"max_bytes": 1048576, "max_seconds": 600},
        "fetch_budget": {"max_fetch_bytes": 524288, "max_fetch_seconds": 300, "max_artifacts": 32},
        "build_budget": {"max_build_bytes": 524288, "max_build_seconds": 600},
        "source_head": _CP2A_GIT,
        "target_host": "trade-core",
        "created_at": _CP2A_TS,
    }


# CP3 §5.1 re-derivation:route-class 載體的 derived id 必 = prefix + hex(canonical_digest(core)),
# 故 probe_id / prepare_id 由 core 真實導出(先前 placeholder hex 會被 CP3 中央閘拒)。
_CP2A_PROBE_HEX = canonical_digest(_cp2a_probe_core()).split(":", 1)[1]
_CP2A_PREP_HEX = canonical_digest(_cp2a_prepare_core()).split(":", 1)[1]
_CP2A_PROBE_ID = "s2-4-probe-" + _CP2A_PROBE_HEX
_CP2A_PREP_ID = "s2-4-prepare-" + _CP2A_PREP_HEX
_CP2A_UNIT = "arcane-aiml-s2-4-probe-" + _CP2A_PROBE_HEX + ".service"
_CP2A_STAGING = "/var/lib/arcane-equilibrium/aiml/install/s2_4/prepared/" + _CP2A_PREP_ID


def _cp2a_fixtures() -> dict:
    probe_core = _cp2a_probe_core()
    probe_core_digest = canonical_digest(probe_core)
    prepare_core = _cp2a_prepare_core()
    prepare_core_digest = canonical_digest(prepare_core)
    staging_locator = {"staging_root": _CP2A_STAGING, "device": 66306, "inode": 22222}

    artifacts: dict[str, dict] = {}

    artifacts["s2_4_capability_probe_core_v1"] = probe_core

    artifacts["s2_4_capability_probe_intent_v1"] = {
        "schema_version": "s2_4_capability_probe_intent_v1",
        "route_class": "s2_4_capability_probe_intent",
        "core": probe_core,
        "core_digest": probe_core_digest,
        "probe_id": _CP2A_PROBE_ID,
        "route_surface": {
            "required_effect_class": "HOST_CAPABILITY_PROBE",
            "runtime_effect": True,
            "service": "transient_probe_only",
            "risk": "high",
            "runtime_claim": True,
            "probe_budget_bound": True,
            "cleanup_budget_bound": True,
        },
        "forbidden_surfaces": {
            "persistent_unit_write": False,
            "persistent_unit_enable": False,
            "persistent_unit_start": False,
            "daemon_reload": False,
            "pg": False,
            "migration": False,
            "secret": False,
            "credential_install": False,
            "host_identity": False,
            "broker_or_order": False,
        },
        "required_authorization": {
            "profile_identity": "aiml-s2-capability-probe-operator-v1",
            "signature_namespace": "arcane-equilibrium-aiml-s2-capability-probe",
            "max_ttl_seconds": 600,
        },
        "expires_at": _CP2A_TS,
        "self_digest": _CP2A_D,
    }

    artifacts["network_sandbox_capability_attestation_v1"] = {
        "schema_version": "network_sandbox_capability_attestation_v1",
        "scope": "PREPARE_SANDBOX",
        "probe_id": _CP2A_PROBE_ID,
        "probe_core_digest": probe_core_digest,
        "transient_unit_property_digest": _CP2A_D,
        "observed_sandbox_capability_digest": _CP2A_D2,
        "network_isolation_verified": True,
        "evidence_class": "PLATFORM_ATTESTED",
        "production_posture": {
            "is_runtime_production_pass": False,
            "production_apply_performed": False,
            "running_attested": False,
            "nine_authorities_false": True,
        },
        "observed_at": _CP2A_TS,
        "expires_at": _CP2A_TS,
        "self_digest": _CP2A_D,
    }

    artifacts["s2_4_capability_probe_effect_receipt_v1"] = {
        "schema_version": "s2_4_capability_probe_effect_receipt_v1",
        "probe_id": _CP2A_PROBE_ID,
        "probe_core_digest": probe_core_digest,
        "probe_scope": "PREPARE_SANDBOX",
        "authorization_id": _CP2A_D,
        "authorization_digest": _CP2A_D2,
        "derived_unit_name": _CP2A_UNIT,
        "transient_unit_lifecycle": {
            "invocation_id": "abc123",
            "unit_created": True,
            "unit_observed": True,
            "stopped_after_grace": True,
            "reset_failed": True,
            "removed": True,
            "zero_residue_verified": True,
        },
        "journal_digest": _CP2A_D,
        "consumed_replay_entry_digest": _CP2A_D2,
        "postcheck_digest": _CP2A_D,
        "rollback_digest": _CP2A_D2,
        "network_sandbox_capability_attestation_digest": _CP2A_D,
        "terminal_status": "TERMINAL_CLEAN",
        "evidence_class": "PLATFORM_ATTESTED",
        "source_head": _CP2A_GIT,
        "target_host": "trade-core",
        "trusted_host_time": _CP2A_TS,
        "observed_at": _CP2A_TS,
        "expires_at": _CP2A_TS,
        "production_authority_flags": {
            "nine_authorities_false": True,
            "production_apply_performed": False,
            "running_attested": False,
        },
        "self_digest": _CP2A_D,
    }

    artifacts["s2_4_capability_probe_journal_v1"] = {
        "schema_version": "s2_4_capability_probe_journal_v1",
        "probe_id": _CP2A_PROBE_ID,
        "derived_unit_name": _CP2A_UNIT,
        "scope": "PREPARE_SANDBOX",
        "transient_unit_property_digest": _CP2A_D,
        "expected_invocation_id_pattern": "^[0-9a-f]{32}$",
        "cleanup_rollback_digest": _CP2A_D2,
        "entries": [
            {
                "seq": 0,
                "state": "APPLYING",
                "pre_state_digest": _CP2A_D,
                "post_state_digest": _CP2A_D2,
                "fsynced": True,
                "recorded_at": _CP2A_TS,
            }
        ],
        "terminal": True,
        "journal_integrity": {
            "same_filesystem_atomic_rename": True,
            "file_fsynced": True,
            "parent_dir_fsynced": True,
        },
        "outer_checksum": _CP2A_D,
        "self_digest": _CP2A_D2,
    }

    artifacts["s2_4_capability_probe_postcheck_v1"] = {
        "schema_version": "s2_4_capability_probe_postcheck_v1",
        "status": "PASS",
        "probe_id": _CP2A_PROBE_ID,
        "probe_core_digest": probe_core_digest,
        "derived_unit_name": _CP2A_UNIT,
        "verifier_node": "ops-verifier",
        "applier_node": "probe-applier",
        "stopped_confirmed": True,
        "reset_failed_confirmed": True,
        "removed_confirmed": True,
        "no_surviving_unit": True,
        "no_surviving_cgroup": True,
        "no_surviving_process": True,
        "verifier_capture_digest": _CP2A_D,
        "observed_at": _CP2A_TS,
        "expires_at": _CP2A_TS,
        "self_digest": _CP2A_D2,
    }

    artifacts["s2_4_capability_probe_rollback_v1"] = {
        "schema_version": "s2_4_capability_probe_rollback_v1",
        "status": "CLEANED_EXACT",
        "probe_id": _CP2A_PROBE_ID,
        "derived_unit_name": _CP2A_UNIT,
        "pre_state_digest": _CP2A_D,
        "post_state_digest": _CP2A_D2,
        "stop_operation": "transient_unit_stop",
        "cgroup_drain_operation": "bounded_cgroup_drain",
        "reset_failed_operation": "reset_failed",
        "remove_operation": "transient_unit_remove",
        "cgroup_drain_bounded": True,
        "unit_absent": True,
        "cgroup_absent": True,
        "task_files_absent": True,
        "observed_at": _CP2A_TS,
        "expires_at": _CP2A_TS,
        "self_digest": _CP2A_D,
    }

    artifacts["s2_4_prepare_core_v1"] = prepare_core

    artifacts["s2_4_prepare_intent_v1"] = {
        "schema_version": "s2_4_prepare_intent_v1",
        "route_class": "s2_4_prepare_intent",
        "core": prepare_core,
        "core_digest": prepare_core_digest,
        "prepare_id": _CP2A_PREP_ID,
        "route_surface": {
            "required_effect_class": "LEARNING_RUNTIME_PREPARE",
            "runtime_effect": True,
            "service": "transient_builder_only",
            "risk": "high",
            "runtime_claim": True,
            "staging_budget_bound": True,
            "fetch_budget_bound": True,
            "build_budget_bound": True,
            "cleanup_budget_bound": True,
        },
        "forbidden_surfaces": {
            "apply_publish": False,
            "persistent_unit_write": False,
            "persistent_unit_enable": False,
            "persistent_unit_start": False,
            "daemon_reload": False,
            "pg": False,
            "migration": False,
            "secret": False,
            "credential_install": False,
            "host_identity": False,
            "opt_publish": False,
            "etc_write": False,
            "broker_or_order": False,
        },
        "required_authorization": {
            "profile_identity": "aiml-s2-install-prepare-operator-v1",
            "signature_namespace": "arcane-equilibrium-aiml-s2-install-prepare",
            "max_ttl_seconds": 900,
        },
        "source_lock_closure_identity": {
            "source_compatibility_receipt_digest": _CP2A_D,
            "sealed_build_receipt_digest": _CP2A_D2,
            "identity_contract_digest": _CP2A_D,
        },
        "application_manifest_digest": _CP2A_D2,
        "prepare_sandbox_probe_receipt_digest": _CP2A_D,
        "expires_at": _CP2A_TS,
        "self_digest": _CP2A_D,
    }

    prepared_bundle = {
        "schema_version": "s2_4_prepared_install_bundle_v1",
        "prepare_id": _CP2A_PREP_ID,
        "artifact_locators": [{"locator": "blobs/sha256/aaa", "content_digest": _CP2A_D}],
        "base_runtime_tree_manifest_digest": _CP2A_D,
        "base_runtime_tree_digest": _CP2A_D2,
        "application_bundle_manifest_digest": _CP2A_D,
        "application_bundle_digest": _CP2A_D2,
        "launch_bundle_manifest_digest": _CP2A_D,
        "launch_bundle_digest": _CP2A_D2,
        "native_import_proof_digest": _CP2A_D,
        "staging_locator": staging_locator,
        "staging_root_owned_nonwritable": True,
        "source_head": _CP2A_GIT,
        "target_host": "trade-core",
        "created_at": _CP2A_TS,
        "expires_at": _CP2A_TS,
        "self_digest": _CP2A_D,
    }
    artifacts["s2_4_prepared_install_bundle_v1"] = prepared_bundle

    artifacts["s2_4_prepare_effect_receipt_v1"] = {
        "schema_version": "s2_4_prepare_effect_receipt_v1",
        "prepare_id": _CP2A_PREP_ID,
        "prepare_core_digest": prepare_core_digest,
        "authorization_id": _CP2A_D,
        "authorization_digest": _CP2A_D2,
        "prepared_install_bundle_digest": _CP2A_D,
        "staging_locator": staging_locator,
        "journal_digest": _CP2A_D,
        "consumed_replay_entry_digest": _CP2A_D2,
        "postcheck_digest": _CP2A_D,
        "rollback_digest": _CP2A_D2,
        "terminal_status": "PREPARED",
        "evidence_class": "PLATFORM_ATTESTED",
        "source_head": _CP2A_GIT,
        "target_host": "trade-core",
        "trusted_host_time": _CP2A_TS,
        "observed_at": _CP2A_TS,
        "expires_at": _CP2A_TS,
        "production_authority_flags": {
            "nine_authorities_false": True,
            "production_apply_performed": False,
            "running_attested": False,
        },
        "self_digest": _CP2A_D,
    }

    artifacts["s2_4_prepare_journal_v1"] = {
        "schema_version": "s2_4_prepare_journal_v1",
        "prepare_id": _CP2A_PREP_ID,
        "staging_root": _CP2A_STAGING,
        "entries": [
            {
                "seq": 0,
                "state": "PREPARING",
                "pre_state_digest": _CP2A_D,
                "post_state_digest": _CP2A_D2,
                "fsynced": True,
                "recorded_at": _CP2A_TS,
            }
        ],
        "terminal": True,
        "journal_integrity": {
            "preparing_fsynced_before_staging_create": True,
            "same_filesystem_atomic_rename": True,
            "file_fsynced": True,
            "parent_dir_fsynced": True,
        },
        "outer_checksum": _CP2A_D,
        "self_digest": _CP2A_D2,
    }

    artifacts["s2_4_prepare_postcheck_v1"] = {
        "schema_version": "s2_4_prepare_postcheck_v1",
        "status": "PASS",
        "prepare_id": _CP2A_PREP_ID,
        "prepare_core_digest": prepare_core_digest,
        "verifier_node": "ops-verifier",
        "applier_node": "prepare-applier",
        "zero_residue_outside_staging": True,
        "staging_root_owned_nonwritable": True,
        "residue_scan_digest": _CP2A_D,
        "verifier_capture_digest": _CP2A_D2,
        "observed_at": _CP2A_TS,
        "expires_at": _CP2A_TS,
        "self_digest": _CP2A_D,
    }

    artifacts["s2_4_prepare_rollback_v1"] = {
        "schema_version": "s2_4_prepare_rollback_v1",
        "status": "CLEANED_EXACT",
        "prepare_id": _CP2A_PREP_ID,
        "staging_root": _CP2A_STAGING,
        "pre_state_digest": _CP2A_D,
        "post_state_digest": _CP2A_D2,
        "task_owned_only": True,
        "staging_delta_removed": True,
        "staging_absent": True,
        "observed_at": _CP2A_TS,
        "expires_at": _CP2A_TS,
        "self_digest": _CP2A_D,
    }

    # 每份帶 self_digest 者以 canonical self-digest 重封(完整性;非生產者身分)。
    for artifact in artifacts.values():
        if "self_digest" in artifact:
            artifact["self_digest"] = artifact_self_digest(artifact)
    return artifacts


_CP2A_KEYS = (
    "s2_4_capability_probe_core_v1",
    "s2_4_capability_probe_intent_v1",
    "s2_4_capability_probe_effect_receipt_v1",
    "s2_4_capability_probe_journal_v1",
    "s2_4_capability_probe_postcheck_v1",
    "s2_4_capability_probe_rollback_v1",
    "network_sandbox_capability_attestation_v1",
    "s2_4_prepare_core_v1",
    "s2_4_prepare_intent_v1",
    "s2_4_prepare_effect_receipt_v1",
    "s2_4_prepare_journal_v1",
    "s2_4_prepare_postcheck_v1",
    "s2_4_prepare_rollback_v1",
    "s2_4_prepared_install_bundle_v1",
)
_CP2A_CORE_KEYS = ("s2_4_capability_probe_core_v1", "s2_4_prepare_core_v1")


def test_cp2a_schema_files_resolve_to_real_files() -> None:
    for key in _CP2A_KEYS:
        assert key in SCHEMA_FILES, key
        assert (SCHEMA_DIR / SCHEMA_FILES[key]).is_file(), key
    assert len(_CP2A_KEYS) == 14


@pytest.mark.parametrize("key", _CP2A_KEYS)
def test_cp2a_round_trip_validates_clean(key: str) -> None:
    fixture = _cp2a_fixtures()[key]
    assert validate_aiml_artifact(fixture) == [], key
    # closed schema: every top-level schema_version const matches its SCHEMA_FILES key.
    assert fixture["schema_version"] == key


@pytest.mark.parametrize("key", _CP2A_KEYS)
def test_cp2a_additional_properties_extra_key_rejected(key: str) -> None:
    fixture = deepcopy(_cp2a_fixtures()[key])
    fixture["__unexpected_extra__"] = "x"
    if "self_digest" in fixture:
        fixture["self_digest"] = artifact_self_digest(fixture)
    errors = validate_aiml_artifact(fixture)
    assert any("unexpected property" in e or "__unexpected_extra__" in e for e in errors), (key, errors)


@pytest.mark.parametrize("key", _CP2A_KEYS)
def test_cp2a_self_digest_binds_integrity_when_present(key: str) -> None:
    fixture = _cp2a_fixtures()[key]
    if "self_digest" not in fixture:
        pytest.skip(f"{key} is an unsigned core / journal-inner artifact")
    assert fixture["self_digest"] == artifact_self_digest(fixture)


@pytest.mark.parametrize("key", _CP2A_CORE_KEYS)
def test_cp2a_unsigned_core_excludes_id_auth_self_digest(key: str) -> None:
    # §5.1:core 是被簽名對象,其 digest 導 id → core 不得含 id/authorization/self_digest。
    schema = json.loads((SCHEMA_DIR / SCHEMA_FILES[key]).read_text(encoding="utf-8"))
    props = set(schema["properties"])
    required = set(schema["required"])
    forbidden = {
        "self_digest",
        "probe_id",
        "prepare_id",
        "derived_id",
        "authorization",
        "authorization_id",
        "authorization_digest",
        "authorization_set",
        "intent_id",
        "core_digest",
    }
    assert not (props & forbidden), (key, props & forbidden)
    assert not (required & forbidden), (key, required & forbidden)
    fixture = _cp2a_fixtures()[key]
    assert not (set(fixture) & forbidden), (key, set(fixture) & forbidden)


def test_cp2a_receipts_and_attestation_pin_no_runtime_production_pass() -> None:
    # 契約鐵律:任何 receipt/attestation 不得斷言 runtime/production PASS。
    fixtures = _cp2a_fixtures()
    # effect receipts:九 authority const-false + production_apply_performed/running_attested const-false。
    for key in ("s2_4_capability_probe_effect_receipt_v1", "s2_4_prepare_effect_receipt_v1"):
        forged = deepcopy(fixtures[key])
        forged["production_authority_flags"]["production_apply_performed"] = True
        forged["self_digest"] = artifact_self_digest(forged)
        errs = validate_aiml_artifact(forged)
        assert any("production_apply_performed" in e for e in errs), (key, errs)
    # network_sandbox attestation:is_runtime_production_pass const-false。
    forged = deepcopy(fixtures["network_sandbox_capability_attestation_v1"])
    forged["production_posture"]["is_runtime_production_pass"] = True
    forged["self_digest"] = artifact_self_digest(forged)
    errs = validate_aiml_artifact(forged)
    assert any("is_runtime_production_pass" in e for e in errs), errs


def test_cp2a_terminal_and_pass_conditionals_have_teeth() -> None:
    fixtures = _cp2a_fixtures()
    # probe receipt:TERMINAL_CLEAN 要求 removed/reset_failed/zero_residue 皆 true。
    forged = deepcopy(fixtures["s2_4_capability_probe_effect_receipt_v1"])
    forged["transient_unit_lifecycle"]["removed"] = False
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("removed" in e for e in validate_aiml_artifact(forged))
    # probe postcheck:PASS 要求 no_surviving_unit 為 true。
    forged = deepcopy(fixtures["s2_4_capability_probe_postcheck_v1"])
    forged["no_surviving_unit"] = False
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("no_surviving_unit" in e for e in validate_aiml_artifact(forged))
    # prepare postcheck:PASS 要求 zero_residue_outside_staging 為 true。
    forged = deepcopy(fixtures["s2_4_prepare_postcheck_v1"])
    forged["zero_residue_outside_staging"] = False
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("zero_residue_outside_staging" in e for e in validate_aiml_artifact(forged))


def test_cp2a_route_intents_forbid_cross_route_surfaces() -> None:
    fixtures = _cp2a_fixtures()
    # probe intent:任一 §4:285 forbidden surface 翻 true → 拒(結構性,injection 前)。
    forged = deepcopy(fixtures["s2_4_capability_probe_intent_v1"])
    forged["forbidden_surfaces"]["pg"] = True
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("pg" in e for e in validate_aiml_artifact(forged))
    # prepare intent:APPLY/opt/etc 面翻 true → 拒。
    forged = deepcopy(fixtures["s2_4_prepare_intent_v1"])
    forged["forbidden_surfaces"]["opt_publish"] = True
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("opt_publish" in e for e in validate_aiml_artifact(forged))


def test_cp2a_frozen_pins_unchanged_after_schema_files_additions() -> None:
    # 加 14 個 SCHEMA_FILES 查找鍵不動 S0.3 classifier / v1|v2 component matrix / PROGRAM_SCHEMA_PATHS。
    from aiml_gate_receipt_validator import (
        aiml_component_effect_class_matrix_digest,
        aiml_component_effect_class_matrix_v2_digest,
        PROGRAM_SCHEMA_PATHS,
    )

    assert aiml_effect_classifier_digest() == (
        "sha256:1cf8c021b066ceeb364e968add074d263cb28d63db421fdc40620e9904d0ddbc"
    )
    assert aiml_component_effect_class_matrix_digest() == (
        "sha256:22d78882a2dace9ceb640b74b2a5dca2f2a8cc05861720f5ab25c5c9ac86c445"
    )
    assert aiml_component_effect_class_matrix_v2_digest() == (
        "sha256:01d3062c79725b32b7c1468d02013a0df28dfeba1cf29d513cbf3bd6b4143c64"
    )
    assert len(PROGRAM_SCHEMA_PATHS) == 7


# ── S2.4 · WP4 · W1 · CP2b(install/APPLY + component-effect + authorization + PG-topology 契約)──
# 這 16 份 closed schema 皆屬「契約」:round-trip 乾淨、additionalProperties 拒外鍵、unsigned
# aggregate core 排除 plan_id/idempotency_key/auth/self_digest、const-false 生產旗標與 allOf 有牙、
# install-plan 前置拒跨面、operator authorization 四 profile↔namespace 綁定、pg-topology 不自證判定。
_CP2B_D = "sha256:" + "a" * 64
_CP2B_D2 = "sha256:" + "b" * 64
_CP2B_GIT = "0" * 40
_CP2B_TS = "2026-07-24T00:00:00+00:00"
# operator authorization 需 issued < expires 且窗 ≤ profile 上限(600s < 900s):CP4 分支再驗 TTL 相干。
_CP2B_TS_EXP = "2026-07-24T00:10:00+00:00"
_CP2B_CLASSES = (
    "HOST_IDENTITY_INSTALL",
    "PG_ROLE_ACL_MIGRATION",
    "CREDENTIAL_INSTALL",
    "LEARNING_RUNTIME",
    "ENGINE_SCANNER",
)
_CP2B_SSHSIG = "-----BEGIN SSH SIGNATURE-----\n" + "AAAA" * 12 + "\n-----END SSH SIGNATURE-----\n"


def _cp2b_install_plan_core() -> dict:
    return {
        "schema_version": "s2_4_install_plan_core_v1",
        "apply_rows": [
            {"component_effect_class": c, "component_intent_digest": _CP2B_D}
            for c in _CP2B_CLASSES
        ],
        "prepare_receipt_digest": _CP2B_D,
        "topology_pre_digest": _CP2B_D2,
        "hba_delta_digest": _CP2B_D,
        "pre_state_digest": _CP2B_D2,
        "source_head": _CP2B_GIT,
        "target_host": "trade-core",
        "created_at": _CP2B_TS,
    }


# CP3 §5.1 re-derivation:plan_id = 's2-4-' + hex(canonical_digest(plan_core)),idempotency_key=plan_id
# (idempotency_key 在 plan 物件、非簽名 core)。先前 placeholder hex 會被 CP3 中央閘拒。
_CP2B_PLAN_HEX = canonical_digest(_cp2b_install_plan_core()).split(":", 1)[1]
_CP2B_PLAN_ID = "s2-4-" + _CP2B_PLAN_HEX


def _cp2b_fixtures() -> dict:
    core = _cp2b_install_plan_core()
    core_digest = canonical_digest(core)

    artifacts: dict[str, dict] = {}
    artifacts["s2_4_install_plan_core_v1"] = core

    artifacts["s2_4_install_plan_v1"] = {
        "schema_version": "s2_4_install_plan_v1",
        "route_class": "s2_4_install_plan",
        "core": core,
        "core_digest": core_digest,
        "plan_id": _CP2B_PLAN_ID,
        "idempotency_key": _CP2B_PLAN_ID,
        "route_surface": {
            "aggregate_coordinator": True,
            "runtime_effect": True,
            "service": "system_unit_install_inactive",
            "pg": True,
            "migration": True,
            "secret": True,
            "risk": "critical",
            "runtime_claim": True,
            "apply_rows": list(_CP2B_CLASSES),
        },
        "forbidden_surfaces": {
            "prepare_fetch": False,
            "prepare_build": False,
            "arbitrary_shell": False,
            "arbitrary_sql": False,
            "arbitrary_path": False,
            "broker_or_order": False,
        },
        "required_authorization": {
            "aggregate": {
                "profile_identity": "aiml-s2-install-operator-v1",
                "signature_namespace": "arcane-equilibrium-aiml-s2-install",
                "max_ttl_seconds": 900,
            },
            "pg_migration": {
                "profile_identity": "aiml-s2-pg-migration-operator-v1",
                "signature_namespace": "arcane-equilibrium-aiml-s2-pg-migration",
                "max_ttl_seconds": 900,
            },
        },
        "expires_at": _CP2B_TS,
        "self_digest": _CP2B_D,
    }

    artifacts["s2_4_install_effect_receipt_v1"] = {
        "schema_version": "s2_4_install_effect_receipt_v1",
        "plan_id": _CP2B_PLAN_ID,
        "plan_core_digest": core_digest,
        "idempotency_key": _CP2B_PLAN_ID,
        "status": "APPLIED_INACTIVE",
        "aggregate_authorization_id": _CP2B_D,
        "aggregate_authorization_digest": _CP2B_D2,
        "pg_authorization_id": _CP2B_D,
        "pg_authorization_digest": _CP2B_D2,
        "prepare_sandbox_probe_receipt_digest": _CP2B_D,
        "installed_unit_probe_receipt_digest": _CP2B_D2,
        "prepare_result_digest": _CP2B_D,
        "prepare_postcheck_digest": _CP2B_D2,
        "apply_row_results": [
            {"component_effect_class": c, "result_digest": _CP2B_D, "postcheck_digest": _CP2B_D2}
            for c in _CP2B_CLASSES
        ],
        "reverse_compensation_chain_digest": _CP2B_D,
        "journal_digest": _CP2B_D2,
        "unit_state": {"loaded": True, "disabled": True, "inactive": True},
        "service_flags": {
            "service_enabled": False,
            "service_active": False,
            "service_started_by_s2_4": False,
        },
        "evidence_class": "PLATFORM_ATTESTED",
        "production_authority_flags": {
            "nine_authorities_false": True,
            "production_apply_performed": False,
            "running_attested": False,
        },
        "source_head": _CP2B_GIT,
        "target_host": "trade-core",
        "trusted_host_time": _CP2B_TS,
        "observed_at": _CP2B_TS,
        "expires_at": _CP2B_TS,
        "self_digest": _CP2B_D,
    }

    artifacts["s2_4_install_journal_v1"] = {
        "schema_version": "s2_4_install_journal_v1",
        "plan_id": _CP2B_PLAN_ID,
        "plan_core_digest": core_digest,
        "idempotency_key": _CP2B_PLAN_ID,
        "expected_pre_state_digest": _CP2B_D,
        "aggregate_rollback_digest": _CP2B_D2,
        "entries": [
            {
                "seq": 0,
                "step_index": 0,
                "state": "APPLYING",
                "pre_state_digest": _CP2B_D,
                "post_state_digest": _CP2B_D2,
                "fsynced": True,
                "recorded_at": _CP2B_TS,
            }
        ],
        "terminal": True,
        "journal_integrity": {
            "applying_fsynced_before_effect": True,
            "same_filesystem_atomic_rename": True,
            "file_fsynced": True,
            "parent_dir_fsynced": True,
        },
        "outer_checksum": _CP2B_D,
        "self_digest": _CP2B_D2,
    }

    artifacts["s2_4_install_postcheck_v1"] = {
        "schema_version": "s2_4_install_postcheck_v1",
        "status": "PASS",
        "plan_id": _CP2B_PLAN_ID,
        "plan_core_digest": core_digest,
        "verifier_node": "ops-verifier",
        "applier_node": "install-applier",
        "probe_lineage_verified": True,
        "prepare_lineage_verified": True,
        "plan_lineage_verified": True,
        "idempotency_verified": True,
        "pre_state_lineage_verified": True,
        "all_apply_rows_satisfied": True,
        "verifier_capture_digest": _CP2B_D,
        "observed_at": _CP2B_TS,
        "expires_at": _CP2B_TS,
        "self_digest": _CP2B_D,
    }

    artifacts["s2_4_install_rollback_v1"] = {
        "schema_version": "s2_4_install_rollback_v1",
        "status": "COMPENSATED_EXACT",
        "plan_id": _CP2B_PLAN_ID,
        "plan_core_digest": core_digest,
        "pre_state_digest": _CP2B_D,
        "post_state_digest": _CP2B_D2,
        "reverse_ops": [
            {"component_effect_class": c, "per_row_rollback_digest": _CP2B_D, "ownership_verified": True}
            for c in reversed(_CP2B_CLASSES)
        ],
        "ownership_aware": True,
        "exact_pre_state_restored": True,
        "daemon_reload_reasserted": True,
        "hba_reload_reasserted": True,
        "observer_role_preserved": True,
        "no_secret_reconstructed": True,
        "observed_at": _CP2B_TS,
        "expires_at": _CP2B_TS,
        "self_digest": _CP2B_D,
    }

    artifacts["s2_4_install_step_result_v1"] = {
        "schema_version": "s2_4_install_step_result_v1",
        "plan_id": _CP2B_PLAN_ID,
        "step_index": 0,
        "component_effect_class": "HOST_IDENTITY_INSTALL",
        "state": "APPLIED",
        "pre_state_digest": _CP2B_D,
        "post_state_digest": _CP2B_D2,
        "task_owned_delta_digest": _CP2B_D,
        "apply_evidence_digest": _CP2B_D2,
        "postcheck_evidence_digest": _CP2B_D,
        "compensation_intent_digest": None,
        "compensation_result_digest": None,
        "observed_at": _CP2B_TS,
        "self_digest": _CP2B_D,
    }

    artifacts["s2_4_component_effect_intent_v1"] = {
        "schema_version": "s2_4_component_effect_intent_v1",
        "component_effect_class": "PG_ROLE_ACL_MIGRATION",
        "install_plan_digest": _CP2B_D,
        "pre_state_digest": _CP2B_D2,
        "required_intent_fields": {
            "topology_attestation_digest": _CP2B_D,
            "acl_manifest_digest": _CP2B_D2,
            "pg_migration_permit_digest": _CP2B_D,
            "admin_handle_descriptor_digest": _CP2B_D2,
        },
        "expires_at": _CP2B_TS,
        "self_digest": _CP2B_D,
    }

    artifacts["s2_4_component_effect_result_v1"] = {
        "schema_version": "s2_4_component_effect_result_v1",
        "component_effect_class": "CREDENTIAL_INSTALL",
        "install_plan_digest": _CP2B_D,
        "status": "SATISFIED",
        "applied_state_digest": _CP2B_D,
        "postcheck_digest": _CP2B_D2,
        "rollback_digest": _CP2B_D,
        "pre_state_digest": _CP2B_D2,
        "post_state_digest": _CP2B_D,
        "evidence_class": "PLATFORM_ATTESTED",
        "production_authority_flags": {
            "nine_authorities_false": True,
            "production_apply_performed": False,
            "running_attested": False,
        },
        "observed_at": _CP2B_TS,
        "self_digest": _CP2B_D,
    }

    artifacts["s2_4_component_effect_postcheck_v1"] = {
        "schema_version": "s2_4_component_effect_postcheck_v1",
        "status": "PASS",
        "component_effect_class": "ENGINE_SCANNER",
        "install_plan_digest": _CP2B_D,
        "verifier_node": "ops-verifier",
        "applier_node": "install-applier",
        "observed_subject_digest": _CP2B_D,
        "applied_state_verified": True,
        "pre_state_lineage_verified": True,
        "verifier_capture_digest": _CP2B_D2,
        "observed_at": _CP2B_TS,
        "expires_at": _CP2B_TS,
        "self_digest": _CP2B_D,
    }

    artifacts["s2_4_component_effect_rollback_v1"] = {
        "schema_version": "s2_4_component_effect_rollback_v1",
        "status": "COMPENSATED_EXACT",
        "component_effect_class": "LEARNING_RUNTIME",
        "install_plan_digest": _CP2B_D,
        "pre_state_digest": _CP2B_D,
        "post_state_digest": _CP2B_D2,
        "ownership_aware": True,
        "exact_pre_state_restored": True,
        "no_secret_reconstructed": True,
        "observed_at": _CP2B_TS,
        "expires_at": _CP2B_TS,
        "self_digest": _CP2B_D,
    }

    artifacts["s2_4_operator_authorization_v1"] = {
        "schema_version": "s2_4_operator_authorization_v1",
        "profile_identity": "aiml-s2-install-operator-v1",
        "signature_namespace": "arcane-equilibrium-aiml-s2-install",
        "authorization_id": _CP2B_D,
        # CP4:payload_fields 必逐位元組等於 APPLY profile 的 §9.1 ordered list(15 欄)。
        "payload_fields": [
            "domain", "authorization_id", "plan_core_digest", "plan_id",
            "source_head", "target_host", "prepare_receipt_digest",
            "topology_pre_digest", "installed_unit_probe_receipt_digest",
            "hba_delta_digest", "pre_state_digest", "aggregate_rollback_digest",
            "idempotency_key", "issued_at", "expires_at",
        ],
        "issued_at": _CP2B_TS,
        "expires_at": _CP2B_TS_EXP,
        "sshsig_armored": _CP2B_SSHSIG,
        "self_digest": _CP2B_D,
    }

    artifacts["s2_4_authorization_replay_ledger_v1"] = {
        "schema_version": "s2_4_authorization_replay_ledger_v1",
        "ledger_path": "/var/lib/arcane-equilibrium/aiml/install/s2_4/authorization-replay-ledger.json",
        "entries": [
            {
                "seq": 0,
                "prev_entry_digest": None,
                "authorization_id": _CP2B_D,
                "authorization_digest": _CP2B_D2,
                "profile_identity": "aiml-s2-install-operator-v1",
                "consumed_at": _CP2B_TS,
                "entry_digest": _CP2B_D,
                "fsynced": True,
            }
        ],
        "append_only": True,
        "self_digest": _CP2B_D,
    }

    artifacts["s2_4_pg_hba_delta_v1"] = {
        "schema_version": "s2_4_pg_hba_delta_v1",
        "plan_id": _CP2B_PLAN_ID,
        "plan_core_digest": core_digest,
        "cluster_identity_ref": _CP2B_D,
        "pre_hba_digest": _CP2B_D,
        "delta": {
            "operation": "ADD_ROW",
            "normalized_row": "host trading_ai aiml_engine_scanner 127.0.0.1/32 scram-sha-256",
            "insertion_anchor": "after:local all all",
        },
        "post_hba_digest": _CP2B_D2,
        "effective_rule": {
            "source": "127.0.0.1/32",
            "database": "trading_ai",
            "user": "aiml_engine_scanner",
            "method": "scram-sha-256",
        },
        "reload_operation": "pg_hba_reload",
        "rollback_projection_digest": _CP2B_D,
        "observed_at": _CP2B_TS,
        "expires_at": _CP2B_TS,
        "self_digest": _CP2B_D,
    }

    artifacts["pg_topology_attestation_v1"] = {
        "schema_version": "pg_topology_attestation_v1",
        "target_host": "trade-core",
        "source_head": _CP2B_GIT,
        "topology_status": "PG_TOPOLOGY_EVIDENCE_CAPTURED",
        "derived_verdict": None,
        "runtime_listener": {
            "socket_inode": 123,
            "owning_pid": 10,
            "owning_uid": 0,
            "executable_digest": _CP2B_D,
            "cgroup": "/system.slice/postgresql.service",
            "endpoint": "127.0.0.1:5432",
        },
        "proxy_hops": [],
        "admin_endpoint": {"endpoint_class": "attested_local_socket", "handle_class": "local_admin_handle"},
        "cluster_identity": {
            "system_identifier": "7000000000000000000",
            "server_version": "16.2",
            "database_oid": 16400,
            "postmaster_identity": "postmaster-pid-9",
            "reload_operation_id": "reload-op-1",
        },
        "file_identities": {
            "data_dir": {"device": 66306, "inode": 1, "path": "/var/lib/pgsql/16/data", "digest": _CP2B_D},
            "config_file": {"device": 66306, "inode": 2, "path": "/pg/postgresql.conf", "digest": _CP2B_D2},
            "hba_file": {"device": 66306, "inode": 3, "path": "/pg/pg_hba.conf", "digest": _CP2B_D},
        },
        "effective_hba_rule": {
            "source": "127.0.0.1/32",
            "database": "trading_ai",
            "user": "aiml_engine_scanner",
            "method": "scram-sha-256",
        },
        "end_to_end_reaches_cluster": True,
        "listener_config_digest": _CP2B_D,
        "proxy_config_digest": _CP2B_D2,
        "cluster_identity_digest": _CP2B_D,
        "observed_at": _CP2B_TS,
        "expires_at": _CP2B_TS,
        "self_digest": _CP2B_D,
    }

    artifacts["pg_topology_runtime_guard_v1"] = {
        "schema_version": "pg_topology_runtime_guard_v1",
        "guard_path": "/etc/arcane-equilibrium/aiml/engine-scanner/topology-runtime-guard.json",
        "cluster_identity_row_digest": _CP2B_D,
        "plan_topology_digest": _CP2B_D2,
        "runtime_endpoint": {"host": "127.0.0.1", "port": 5432, "dbname": "trading_ai"},
        "system_identifier": "7000000000000000000",
        "database_oid": 16400,
        "server_major_version": 16,
        "binding_nonce": "host-nonce-abc123",
        "expected_topology_values_digest": _CP2B_D,
        "self_digest": _CP2B_D,
    }

    for artifact in artifacts.values():
        if "self_digest" in artifact:
            artifact["self_digest"] = artifact_self_digest(artifact)
    return artifacts


_CP2B_KEYS = (
    "s2_4_install_plan_core_v1",
    "s2_4_install_plan_v1",
    "s2_4_install_effect_receipt_v1",
    "s2_4_install_journal_v1",
    "s2_4_install_postcheck_v1",
    "s2_4_install_rollback_v1",
    "s2_4_install_step_result_v1",
    "s2_4_component_effect_intent_v1",
    "s2_4_component_effect_result_v1",
    "s2_4_component_effect_postcheck_v1",
    "s2_4_component_effect_rollback_v1",
    "s2_4_operator_authorization_v1",
    "s2_4_authorization_replay_ledger_v1",
    "s2_4_pg_hba_delta_v1",
    "pg_topology_attestation_v1",
    "pg_topology_runtime_guard_v1",
)
_CP2B_CORE_KEYS = ("s2_4_install_plan_core_v1",)


def test_cp2b_schema_files_resolve_to_real_files() -> None:
    for key in _CP2B_KEYS:
        assert key in SCHEMA_FILES, key
        assert (SCHEMA_DIR / SCHEMA_FILES[key]).is_file(), key
    assert len(_CP2B_KEYS) == 16
    # CP2a(14)+ CP2b(16)加上既有基線 → 中央 SCHEMA_FILES 委派表 = 65;
    # W2a(§2.1)additive 註冊 pg_acl_manifest_v1 → 66;
    # W2b(§8.1)additive 註冊 application_bundle_runtime_closure_v1 +
    # application_bundle_manifest_v1 → 68;
    # W2c(§8.1 #2/#4)additive 註冊 base_runtime_tree_manifest_v1 +
    # launch_bundle_manifest_v1 → 70。
    assert len(SCHEMA_FILES) == 70
    assert "pg_acl_manifest_v1" in SCHEMA_FILES
    assert (SCHEMA_DIR / SCHEMA_FILES["pg_acl_manifest_v1"]).is_file()
    for w2_key in (
        "application_bundle_runtime_closure_v1",
        "application_bundle_manifest_v1",
        "base_runtime_tree_manifest_v1",
        "launch_bundle_manifest_v1",
    ):
        assert w2_key in SCHEMA_FILES
        assert (SCHEMA_DIR / SCHEMA_FILES[w2_key]).is_file()


@pytest.mark.parametrize("key", _CP2B_KEYS)
def test_cp2b_round_trip_validates_clean(key: str) -> None:
    fixture = _cp2b_fixtures()[key]
    if key == "s2_4_operator_authorization_v1":
        # CP4 為此 artifact 的中央閘分支加上真 §9.1 信任根 SSHSIG 驗簽。CP2b 佔位 fixture 結構全清(profile
        # 解析、full §9.1 ordered payload_fields、相干 TTL、指紋綁定皆過)但攜帶假 armored 簽章,故唯一殘餘
        # 錯誤即該離線公鑰驗簽——已簽的正例(monkeypatch 丟棄式鑰)由 CP4 test 擁有。CP2b 的契約(closed-schema
        # round-trip)在此仍成立:唯一殘餘不是 schema/結構錯,而是信任根驗簽這道 CP4 真閘。
        assert validate_aiml_artifact(fixture) == [
            "s2_4 operator authorization SSH signature is invalid"
        ]
        assert fixture["schema_version"] == key
        return
    assert validate_aiml_artifact(fixture) == [], key
    assert fixture["schema_version"] == key


@pytest.mark.parametrize("key", _CP2B_KEYS)
def test_cp2b_additional_properties_extra_key_rejected(key: str) -> None:
    fixture = deepcopy(_cp2b_fixtures()[key])
    fixture["__unexpected_extra__"] = "x"
    if "self_digest" in fixture:
        fixture["self_digest"] = artifact_self_digest(fixture)
    errors = validate_aiml_artifact(fixture)
    assert any("unexpected property" in e or "__unexpected_extra__" in e for e in errors), (key, errors)


@pytest.mark.parametrize("key", _CP2B_KEYS)
def test_cp2b_self_digest_binds_integrity_when_present(key: str) -> None:
    fixture = _cp2b_fixtures()[key]
    if "self_digest" not in fixture:
        pytest.skip(f"{key} carries no self_digest")
    assert fixture["self_digest"] == artifact_self_digest(fixture)


@pytest.mark.parametrize("key", _CP2B_CORE_KEYS)
def test_cp2b_unsigned_core_excludes_id_auth_self_digest(key: str) -> None:
    # §5.1:aggregate core 是被簽名對象,其 digest 導 plan_id 且 idempotency_key=plan_id → core
    # 不得含 plan_id/idempotency_key/authorization/self_digest(與 probe/prepare core 排除導出 id 同構)。
    schema = json.loads((SCHEMA_DIR / SCHEMA_FILES[key]).read_text(encoding="utf-8"))
    props = set(schema["properties"])
    required = set(schema["required"])
    forbidden = {
        "self_digest",
        "plan_id",
        "idempotency_key",
        "derived_id",
        "authorization",
        "authorization_id",
        "authorization_digest",
        "authorization_set",
        "core_digest",
    }
    assert not (props & forbidden), (key, props & forbidden)
    assert not (required & forbidden), (key, required & forbidden)
    fixture = _cp2b_fixtures()[key]
    assert not (set(fixture) & forbidden), (key, set(fixture) & forbidden)


def test_cp2b_receipt_and_row_result_pin_no_runtime_production_pass() -> None:
    # 契約鐵律:install effect receipt 與每個 component-effect row result 不得斷言 runtime/production PASS。
    fixtures = _cp2b_fixtures()
    for key in ("s2_4_install_effect_receipt_v1", "s2_4_component_effect_result_v1"):
        forged = deepcopy(fixtures[key])
        forged["production_authority_flags"]["production_apply_performed"] = True
        forged["self_digest"] = artifact_self_digest(forged)
        assert any("production_apply_performed" in e for e in validate_aiml_artifact(forged)), key
        forged = deepcopy(fixtures[key])
        forged["production_authority_flags"]["running_attested"] = True
        forged["self_digest"] = artifact_self_digest(forged)
        assert any("running_attested" in e for e in validate_aiml_artifact(forged)), key
    # install effect receipt:service_enabled/active/started_by_s2_4 皆 const-false。
    forged = deepcopy(fixtures["s2_4_install_effect_receipt_v1"])
    forged["service_flags"]["service_enabled"] = True
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("service_enabled" in e for e in validate_aiml_artifact(forged))


def test_cp2b_terminal_and_pass_conditionals_have_teeth() -> None:
    fixtures = _cp2b_fixtures()
    # install effect receipt:APPLIED_INACTIVE 要求 unit loaded/disabled/inactive 皆 true。
    forged = deepcopy(fixtures["s2_4_install_effect_receipt_v1"])
    forged["unit_state"]["inactive"] = False
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("inactive" in e for e in validate_aiml_artifact(forged))
    # install postcheck:PASS 要求 all_apply_rows_satisfied 為 true。
    forged = deepcopy(fixtures["s2_4_install_postcheck_v1"])
    forged["all_apply_rows_satisfied"] = False
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("all_apply_rows_satisfied" in e for e in validate_aiml_artifact(forged))
    # install rollback:COMPENSATED_EXACT 要求 exact_pre_state_restored 為 true。
    forged = deepcopy(fixtures["s2_4_install_rollback_v1"])
    forged["exact_pre_state_restored"] = False
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("exact_pre_state_restored" in e for e in validate_aiml_artifact(forged))
    # component postcheck:PASS 要求 applied_state_verified 為 true。
    forged = deepcopy(fixtures["s2_4_component_effect_postcheck_v1"])
    forged["applied_state_verified"] = False
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("applied_state_verified" in e for e in validate_aiml_artifact(forged))
    # component rollback:COMPENSATED_EXACT 要求 ownership_aware 為 true。
    forged = deepcopy(fixtures["s2_4_component_effect_rollback_v1"])
    forged["ownership_aware"] = False
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("ownership_aware" in e for e in validate_aiml_artifact(forged))


def test_cp2b_install_plan_forbids_cross_route_surfaces() -> None:
    # install plan:§4:287 forbidden surface(PREPARE fetch/build、任意 shell/SQL/path、broker/order)
    # 任一翻 true → 結構性拒(node injection 前)。
    fixtures = _cp2b_fixtures()
    for surface in ("prepare_build", "arbitrary_shell", "arbitrary_sql", "arbitrary_path", "broker_or_order"):
        forged = deepcopy(fixtures["s2_4_install_plan_v1"])
        forged["forbidden_surfaces"][surface] = True
        forged["self_digest"] = artifact_self_digest(forged)
        assert any(surface in e for e in validate_aiml_artifact(forged)), surface


def test_cp2b_component_intent_binds_required_fields_per_class() -> None:
    # §4 row ABI:每 class 的 required_intent_fields 少一個 → 拒(per-class allOf 有牙)。
    fixtures = _cp2b_fixtures()
    forged = deepcopy(fixtures["s2_4_component_effect_intent_v1"])
    del forged["required_intent_fields"]["acl_manifest_digest"]
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("acl_manifest_digest" in e for e in validate_aiml_artifact(forged))
    # 換到 CREDENTIAL_INSTALL class,缺 encrypted_blob_digest → 拒。
    forged = deepcopy(fixtures["s2_4_component_effect_intent_v1"])
    forged["component_effect_class"] = "CREDENTIAL_INSTALL"
    forged["required_intent_fields"] = {"credential_name": "engine-scanner-db", "host_identity_digest": _CP2B_D}
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("encrypted_blob_digest" in e for e in validate_aiml_artifact(forged))


def test_cp2b_operator_authorization_binds_profile_to_namespace() -> None:
    # §9.1:四 profile↔namespace 精確配對,錯配 → 拒;profile_identity 越界 enum → 拒。
    fixtures = _cp2b_fixtures()
    forged = deepcopy(fixtures["s2_4_operator_authorization_v1"])
    forged["signature_namespace"] = "arcane-equilibrium-aiml-s2-pg-migration"
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("signature_namespace" in e for e in validate_aiml_artifact(forged))
    forged = deepcopy(fixtures["s2_4_operator_authorization_v1"])
    forged["profile_identity"] = "aiml-s2-rogue-operator-v1"
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("enum" in e for e in validate_aiml_artifact(forged))


def test_cp2b_pg_topology_cannot_self_declare_verdict() -> None:
    # §8.2:pg_topology_attestation 僅載證據,derived_verdict 恆 const null;caller 帶任何判定 → 拒。
    fixtures = _cp2b_fixtures()
    forged = deepcopy(fixtures["pg_topology_attestation_v1"])
    forged["derived_verdict"] = "PASS"
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("derived_verdict" in e for e in validate_aiml_artifact(forged))
    # topology_status 只是觀測類,無 PASS 值可選(越界即拒)。
    forged = deepcopy(fixtures["pg_topology_attestation_v1"])
    forged["topology_status"] = "PASS"
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("enum" in e for e in validate_aiml_artifact(forged))


def test_cp2b_pg_hba_delta_add_row_requires_normalized_row() -> None:
    # §5.1:HBA delta ADD_ROW 必帶 normalized_row + insertion_anchor;缺 → 拒。
    fixtures = _cp2b_fixtures()
    forged = deepcopy(fixtures["s2_4_pg_hba_delta_v1"])
    del forged["delta"]["normalized_row"]
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("normalized_row" in e for e in validate_aiml_artifact(forged))


def test_cp2b_frozen_pins_unchanged_after_schema_files_additions() -> None:
    # 加 16 個 SCHEMA_FILES 查找鍵不動 S0.3 classifier / v1|v2 component matrix / PROGRAM_SCHEMA_PATHS。
    from aiml_gate_receipt_validator import (
        aiml_component_effect_class_matrix_digest,
        aiml_component_effect_class_matrix_v2_digest,
        PROGRAM_SCHEMA_PATHS,
    )

    assert aiml_effect_classifier_digest() == (
        "sha256:1cf8c021b066ceeb364e968add074d263cb28d63db421fdc40620e9904d0ddbc"
    )
    assert aiml_component_effect_class_matrix_digest() == (
        "sha256:22d78882a2dace9ceb640b74b2a5dca2f2a8cc05861720f5ab25c5c9ac86c445"
    )
    assert aiml_component_effect_class_matrix_v2_digest() == (
        "sha256:01d3062c79725b32b7c1468d02013a0df28dfeba1cf29d513cbf3bd6b4143c64"
    )
    assert len(PROGRAM_SCHEMA_PATHS) == 7


# ── S2.4 · WP4 · W1 · CP3(§5.1 re-derivation + §4:259-264 aggregate-lineage 謂詞)──
def _lineage_receipt(**overrides: object) -> dict:
    receipt = deepcopy(_cp2b_fixtures()["s2_4_install_effect_receipt_v1"])
    receipt.update(overrides)
    return receipt


def test_aggregate_requires_two_probe_receipts_prepare_and_five_apply_rows() -> None:
    from aiml_gate_receipt_validator import derive_install_lineage_status

    receipt = _cp2b_fixtures()["s2_4_install_effect_receipt_v1"]
    # happy lineage → SATISFIED:兩 scoped probe digest 相異(PREPARE_SANDBOX + INSTALLED_UNIT)、
    # 五 APPLY row exact 次序且 unique、PREPARE 結果/postcheck、逆向補償鏈皆在。
    assert derive_install_lineage_status(receipt) == {"status": "SATISFIED", "reasons": []}
    # 交叉綁 install_plan(plan_id/idempotency_key 一致 + plan.core.apply_rows 五類 exact 次序)亦 SATISFIED。
    plan = _cp2b_fixtures()["s2_4_install_plan_v1"]
    assert derive_install_lineage_status(receipt, install_plan=plan)["status"] == "SATISFIED"

    # negative: missing a row(四列)。schema minItems=5 會擋,故直接呼叫謂詞(離線結構驗補 schema 空缺)。
    r = derive_install_lineage_status(
        _lineage_receipt(apply_row_results=receipt["apply_row_results"][:4])
    )
    assert r["status"] == "NOT_SATISFIED"
    assert any("exactly five APPLY rows" in x for x in r["reasons"]), r["reasons"]

    # negative: duplicated class(HOST 出現兩次、ENGINE 缺)。
    dup_rows = deepcopy(receipt["apply_row_results"])
    dup_rows[4]["component_effect_class"] = "HOST_IDENTITY_INSTALL"
    r = derive_install_lineage_status(_lineage_receipt(apply_row_results=dup_rows))
    assert r["status"] == "NOT_SATISFIED"
    assert any("duplicated class" in x for x in r["reasons"]), r["reasons"]

    # negative: misordered classes(五 unique 但亂序)。
    mis_rows = deepcopy(receipt["apply_row_results"])
    mis_rows[0], mis_rows[1] = mis_rows[1], mis_rows[0]
    r = derive_install_lineage_status(_lineage_receipt(apply_row_results=mis_rows))
    assert r["status"] == "NOT_SATISFIED"
    assert any("out of the required §5.1 class order" in x for x in r["reasons"]), r["reasons"]

    # negative: both probes same scope(兩 scoped probe digest 相同 = 同一 probe 充當兩 scope)。
    r = derive_install_lineage_status(_lineage_receipt(
        prepare_sandbox_probe_receipt_digest=receipt["installed_unit_probe_receipt_digest"],
    ))
    assert r["status"] == "NOT_SATISFIED"
    assert any("scopes must be distinct" in x for x in r["reasons"]), r["reasons"]

    # negative: an extra 6th row。schema maxItems=5 會擋,故直接呼叫謂詞。
    six = deepcopy(receipt["apply_row_results"])
    six.append({"component_effect_class": "ENGINE_SCANNER", "result_digest": _CP2B_D, "postcheck_digest": _CP2B_D2})
    r = derive_install_lineage_status(_lineage_receipt(apply_row_results=six))
    assert r["status"] == "NOT_SATISFIED"
    assert any("exactly five APPLY rows" in x for x in r["reasons"]), r["reasons"]


def test_misordered_install_receipt_rejected_by_central_gate() -> None:
    # 五列(schema 通過)但亂序 → 中央閘的 lineage 謂詞在 closed-schema 之上拒。
    receipt = deepcopy(_cp2b_fixtures()["s2_4_install_effect_receipt_v1"])
    receipt["apply_row_results"][0], receipt["apply_row_results"][1] = (
        receipt["apply_row_results"][1],
        receipt["apply_row_results"][0],
    )
    receipt["self_digest"] = artifact_self_digest(receipt)
    errors = validate_aiml_artifact(receipt)
    assert any("out of the required §5.1 class order" in e for e in errors), errors


def test_install_plan_id_and_idempotency_key_rederive_from_core() -> None:
    # item #3:idempotency_key 在 plan 物件、不在簽名 core;plan_id/idempotency_key 由 core 再導出。
    plan = _cp2b_fixtures()["s2_4_install_plan_v1"]
    assert "idempotency_key" in plan
    assert "idempotency_key" not in plan["core"] and "plan_id" not in plan["core"]
    assert plan["idempotency_key"] == plan["plan_id"]
    assert plan["plan_id"] == "s2-4-" + canonical_digest(plan["core"]).split(":", 1)[1]
    assert validate_aiml_artifact(plan) == []

    # plan_id 竄改 → 中央閘拒(不從 core 再導出)。
    tampered = deepcopy(plan)
    tampered["plan_id"] = "s2-4-" + "f" * 64
    tampered["idempotency_key"] = tampered["plan_id"]
    tampered["self_digest"] = artifact_self_digest(tampered)
    assert any("plan_id does not re-derive" in e for e in validate_aiml_artifact(tampered))

    # idempotency_key != plan_id → 拒。
    drift = deepcopy(plan)
    drift["idempotency_key"] = "s2-4-" + "f" * 64
    drift["self_digest"] = artifact_self_digest(drift)
    assert any("idempotency_key must equal plan_id" in e for e in validate_aiml_artifact(drift))


def test_probe_and_prepare_intent_ids_rederive_from_core() -> None:
    probe = deepcopy(_cp2a_fixtures()["s2_4_capability_probe_intent_v1"])
    assert probe["probe_id"] == "s2-4-probe-" + canonical_digest(probe["core"]).split(":", 1)[1]
    probe["probe_id"] = "s2-4-probe-" + "f" * 64
    probe["self_digest"] = artifact_self_digest(probe)
    assert any("probe_id does not re-derive" in e for e in validate_aiml_artifact(probe))

    prep = deepcopy(_cp2a_fixtures()["s2_4_prepare_intent_v1"])
    assert prep["prepare_id"] == "s2-4-prepare-" + canonical_digest(prep["core"]).split(":", 1)[1]
    prep["prepare_id"] = "s2-4-prepare-" + "f" * 64
    prep["self_digest"] = artifact_self_digest(prep)
    assert any("prepare_id does not re-derive" in e for e in validate_aiml_artifact(prep))


# ── S2.4 · WP4 · W1 · CP4(四 §9.1 operator-authorization trust profile + 離線驗證分支)──────
# 這批測試用**丟棄式** ed25519 鑰 + monkeypatch 本 validator 模組副本的 pinned 信任根,證離線驗簽
# CODE(整合 + 信任根綁定)——鏡 W0a 的 _install_operator_profile 姿態。真 §9.1 帶外私鑰不在任何
# fixture,故沒有 fixture 冒充 runtime 真偽:離線驗簽只證「簽章完整 + 綁 §9.1 信任根」,不證真 operator
# 於 runtime 簽了真語義 payload(W6A/W6B EFFECT)。
_CP4_ISSUED = "2026-07-24T00:00:00+00:00"
_CP4_EXPIRES = "2026-07-24T00:10:00+00:00"   # +600s(< 900s profile 上限)
_CP4_NOW = "2026-07-24T00:05:00+00:00"       # 在 [issued, expires) 窗內
_CP4_SIGN_SEQ = [0]


def _cp4_mint_ed25519_key(tmp_path, name):
    """鑄一把丟棄式 ed25519 keypair;回 (private_key_path, public_key, fingerprint)。鏡 W0a helper。"""

    private_key = tmp_path / name
    _subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(private_key)], check=True
    )
    parts = private_key.with_suffix(".pub").read_text(encoding="ascii").split()
    public_key = " ".join(parts[:2])
    fingerprint = _subprocess.run(
        ["ssh-keygen", "-lf", str(private_key.with_suffix(".pub")), "-E", "sha256"],
        check=True, capture_output=True, text=True,
    ).stdout.split()[1]
    return private_key, public_key, fingerprint


def _cp4_install_pinned_key(monkeypatch, public_key, fingerprint) -> None:
    # monkeypatch **本 validator 模組**的信任根副本(非 trusted-host 模組本身)注入丟棄式鑰;驗簽基元
    # (_verify_ssh_signature / ssh_public_key_fingerprint)仍取自 out-of-scope trusted-host,不被 monkeypatch。
    monkeypatch.setattr(_w0, "S2_4_OPERATOR_TRUST_ROOT_PUBLIC_KEY", public_key)
    monkeypatch.setattr(_w0, "S2_4_OPERATOR_TRUST_ROOT_FINGERPRINT", fingerprint)


def _cp4_authorization(profile_key, **overrides):
    profile = S2_4_AUTHORIZATION_PROFILES[profile_key]
    artifact = {
        "schema_version": "s2_4_operator_authorization_v1",
        "profile_identity": profile["profile_identity"],
        "signature_namespace": profile["signature_namespace"],
        "authorization_id": "sha256:" + "1" * 64,
        "payload_fields": list(profile["payload_fields"]),
        "issued_at": _CP4_ISSUED,
        "expires_at": _CP4_EXPIRES,
        "sshsig_armored": _CP2B_SSHSIG,
        "self_digest": "sha256:" + "0" * 64,
    }
    artifact.update(overrides)
    return artifact


def _cp4_sign(private_key, artifact, *, namespace):
    # 對 validator 的離線被簽投影(排除 sshsig_armored + self_digest)簽章,回填真 armored 與 self_digest。
    signed = _w0._s2_4_operator_authorization_signed_bytes(artifact)
    _CP4_SIGN_SEQ[0] += 1
    message = private_key.parent / f"s2_4-auth-{_CP4_SIGN_SEQ[0]}.bin"
    message.write_bytes(signed)
    _subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", str(private_key), "-n", namespace, str(message)],
        check=True, stdout=_subprocess.DEVNULL, stderr=_subprocess.DEVNULL,
    )
    artifact["sshsig_armored"] = message.with_name(message.name + ".sig").read_text(encoding="ascii")
    artifact["self_digest"] = artifact_self_digest(artifact)
    return artifact


def _cp4_profiles_projection(profiles):
    return {
        key: {
            "profile_identity": row["profile_identity"],
            "signature_namespace": row["signature_namespace"],
            "payload_fields": list(row["payload_fields"]),
            "max_ttl_seconds": row["max_ttl_seconds"],
            "skew_seconds": row["skew_seconds"],
        }
        for key, row in profiles.items()
    }


def test_cp4_authorization_profiles_are_pinned() -> None:
    # #17:四 §9.1 profile 的 identity/namespace/ordered payload/max-TTL/skew 釘選——悄改任一即 digest 漂移。
    assert s2_4_authorization_profiles_digest() == (
        "sha256:79b27b7040e8a8d3af84b6a5f0c7c20e45888caaedac146428145ffea54be2dc"
    )
    profiles = S2_4_AUTHORIZATION_PROFILES
    assert set(profiles) == {"capability_probe", "prepare", "apply_aggregate", "pg_migration"}
    # 四 identity ↔ namespace 精確配對(§9.1)。
    assert profiles["capability_probe"]["profile_identity"] == "aiml-s2-capability-probe-operator-v1"
    assert profiles["capability_probe"]["signature_namespace"] == "arcane-equilibrium-aiml-s2-capability-probe"
    assert profiles["prepare"]["profile_identity"] == "aiml-s2-install-prepare-operator-v1"
    assert profiles["prepare"]["signature_namespace"] == "arcane-equilibrium-aiml-s2-install-prepare"
    assert profiles["apply_aggregate"]["profile_identity"] == "aiml-s2-install-operator-v1"
    assert profiles["apply_aggregate"]["signature_namespace"] == "arcane-equilibrium-aiml-s2-install"
    assert profiles["pg_migration"]["profile_identity"] == "aiml-s2-pg-migration-operator-v1"
    assert profiles["pg_migration"]["signature_namespace"] == "arcane-equilibrium-aiml-s2-pg-migration"
    # §9.1 payload token（follow §9.1，非 task 稿）：probe 用 `scope` / `output_derived_unit_digest_or_null`。
    assert profiles["capability_probe"]["payload_fields"][4] == "scope"
    assert profiles["capability_probe"]["payload_fields"][8] == "output_derived_unit_digest_or_null"
    assert "probe_scope" not in profiles["capability_probe"]["payload_fields"]
    # APPLY/PG 上限 900s、skew 60s(§9.1 數值釘定);PROBE/PREPARE 沿用同一保守上限。
    for key in profiles:
        assert profiles[key]["max_ttl_seconds"] == 900
        assert profiles[key]["skew_seconds"] == 60
    # 悄悄重拼一個 payload token → 釘選 digest 漂移(silent re-spelling 被拒)。
    mutated = _cp4_profiles_projection(profiles)
    mutated["apply_aggregate"]["payload_fields"][2] = "plan_core_digest_RENAMED"
    assert canonical_digest(mutated) != s2_4_authorization_profiles_digest()


def test_cp4_monkeypatched_key_validates_clean(tmp_path, monkeypatch) -> None:
    # 正例(counterfactual:valid authorization validates clean):把 pinned 信任根 monkeypatch 成丟棄式鑰
    # 並以之簽 canonical payload → 四 profile 皆離線驗過(乾淨 [])。只證 CODE 驗簽 + 信任根綁定,不冒充 runtime。
    private_key, public_key, fingerprint = _cp4_mint_ed25519_key(tmp_path, "operator")
    _cp4_install_pinned_key(monkeypatch, public_key, fingerprint)
    for profile_key in ("capability_probe", "prepare", "apply_aggregate", "pg_migration"):
        namespace = S2_4_AUTHORIZATION_PROFILES[profile_key]["signature_namespace"]
        auth = _cp4_authorization(profile_key)
        _cp4_sign(private_key, auth, namespace=namespace)
        assert validate_aiml_artifact(auth, now=_CP4_NOW) == [], profile_key


def test_cp4_forged_key_is_rejected_by_trust_root(tmp_path) -> None:
    # #18:丟棄式鑰簽 APPLY 授權,但**不** monkeypatch pinned 信任根(仍是固定 §9.1 根)→ 簽章對 pinned 公鑰
    # 驗證失敗 → 拒。這證信任根綁定是真閘;丟棄式鑰無從冒充真 §9.1 根(離線驗簽 CODE 有效)。指紋檢查仍過
    # (pinned 公鑰指紋 == pinned 指紋),故唯一殘餘即 SSH 簽章無效——正是信任根這道閘。
    private_key, _pub, _fp = _cp4_mint_ed25519_key(tmp_path, "forged")
    auth = _cp4_authorization("apply_aggregate")
    _cp4_sign(private_key, auth, namespace="arcane-equilibrium-aiml-s2-install")
    errors = validate_aiml_artifact(auth, now=_CP4_NOW)
    assert errors == ["s2_4 operator authorization SSH signature is invalid"], errors
    # 進一步:連指紋一起冒充(把 pinned 指紋 monkeypatch 成丟棄式鑰指紋,但**不**改 pinned 公鑰)→ 指紋
    # 與公鑰不再一致 → trust-root fingerprint mismatch(fail-closed;caller-provided 指紋永不被信)。


def test_cp4_fingerprint_mismatch_is_rejected(tmp_path, monkeypatch) -> None:
    # #18(續):把 pinned **指紋**換成丟棄式鑰指紋而 pinned **公鑰**維持 §9.1 根 → 公鑰導出的指紋 ≠ pinned
    # 指紋 → trust-root fingerprint mismatch。證指紋綁定由「公鑰導出」而非採信 caller/常量任意值。
    _priv, _pub, forged_fp = _cp4_mint_ed25519_key(tmp_path, "unpinned")
    monkeypatch.setattr(_w0, "S2_4_OPERATOR_TRUST_ROOT_FINGERPRINT", forged_fp)
    auth = _cp4_authorization("apply_aggregate")  # 假 armored 即可,指紋 mismatch 先觸發
    errors = validate_aiml_artifact(auth, now=_CP4_NOW)
    assert any("trust-root fingerprint mismatch" in e for e in errors), errors


def test_cp4_cross_profile_signature_is_rejected(tmp_path, monkeypatch) -> None:
    # #19:一張 probe 授權不能授權 APPLY/PREPARE 或別 scope。namespace/identity 綁定拒跨 profile 挪用。
    private_key, public_key, fingerprint = _cp4_mint_ed25519_key(tmp_path, "probe")
    _cp4_install_pinned_key(monkeypatch, public_key, fingerprint)
    # 合法 probe 授權(probe payload + probe namespace 簽)→ 乾淨。
    probe = _cp4_authorization("capability_probe")
    _cp4_sign(private_key, probe, namespace="arcane-equilibrium-aiml-s2-capability-probe")
    assert validate_aiml_artifact(probe, now=_CP4_NOW) == []
    # (a) 把這張 probe 授權冒充成 APPLY profile:改 identity+namespace 成 install(schema allOf 自洽),但
    #     payload_fields 仍是 probe 的、簽章仍在 probe namespace 下 → payload 不符 APPLY ordered list + 簽章於
    #     install namespace 驗證失敗。
    forged = deepcopy(probe)
    forged["profile_identity"] = "aiml-s2-install-operator-v1"
    forged["signature_namespace"] = "arcane-equilibrium-aiml-s2-install"
    forged["self_digest"] = artifact_self_digest(forged)
    errors = validate_aiml_artifact(forged, now=_CP4_NOW)
    assert any("payload_fields do not match" in e for e in errors), errors
    assert any("SSH signature is invalid" in e for e in errors), errors
    # (b) 反向:正確 APPLY payload,但**在 probe namespace 下簽** → 於 install namespace 驗證失敗(唯一殘餘)。
    #     這證 namespace domain-separation:一張以別 profile namespace 簽的授權不能在此 profile 下通過。
    mismatch = _cp4_authorization("apply_aggregate")
    _cp4_sign(private_key, mismatch, namespace="arcane-equilibrium-aiml-s2-capability-probe")
    assert validate_aiml_artifact(mismatch, now=_CP4_NOW) == [
        "s2_4 operator authorization SSH signature is invalid"
    ]


def test_cp4_ttl_freshness_and_replay_chain_bounds(tmp_path, monkeypatch) -> None:
    # #20:freshness + TTL 界（>900s APPLY/PG 拒;expired 拒）+ replay-ledger 重複/亂序斷鏈 SHAPE(結構)。
    private_key, public_key, fingerprint = _cp4_mint_ed25519_key(tmp_path, "operator")
    _cp4_install_pinned_key(monkeypatch, public_key, fingerprint)
    # (a) >900s APPLY TTL → 拒(strict >)。issued 00:00 → expires 00:16 = 960s。
    over = _cp4_authorization(
        "apply_aggregate", issued_at="2026-07-24T00:00:00+00:00",
        expires_at="2026-07-24T00:16:00+00:00",
    )
    _cp4_sign(private_key, over, namespace="arcane-equilibrium-aiml-s2-install")
    assert any(
        "TTL exceeds the profile ceiling (900s)" in e
        for e in validate_aiml_artifact(over, now=_CP4_NOW)
    )
    # (b) >900s PG TTL → 拒(1200s)。
    over_pg = _cp4_authorization(
        "pg_migration", issued_at="2026-07-24T00:00:00+00:00",
        expires_at="2026-07-24T00:20:00+00:00",
    )
    _cp4_sign(private_key, over_pg, namespace="arcane-equilibrium-aiml-s2-pg-migration")
    assert any(
        "TTL exceeds the profile ceiling" in e
        for e in validate_aiml_artifact(over_pg, now=_CP4_NOW)
    )
    # (c) expired → 拒(now 超過 expires + skew)。先證窗內乾淨,再證窗外拒。
    fresh = _cp4_authorization("apply_aggregate")
    _cp4_sign(private_key, fresh, namespace="arcane-equilibrium-aiml-s2-install")
    assert validate_aiml_artifact(fresh, now="2026-07-24T00:05:00+00:00") == []
    expired_now = "2026-07-24T00:12:00+00:00"   # > expires(00:10)+skew(60s)=00:11
    assert any(
        "not currently within its freshness window" in e
        for e in validate_aiml_artifact(fresh, now=expired_now)
    )
    # (d) replay-ledger hash-chain SHAPE(結構):genesis prev=null;後續 entry.prev_entry_digest 必鏈住前一
    #     entry_digest;重複/亂序即斷鏈。runtime 消費/fsync/AUTHORIZATION_REJECTED 屬 W6 EFFECT,此處只證形。
    def _entry(seq, prev):
        entry = {
            "seq": seq, "prev_entry_digest": prev, "authorization_id": _CP2B_D,
            "authorization_digest": _CP2B_D2,
            "profile_identity": "aiml-s2-install-operator-v1",
            "consumed_at": _CP2B_TS, "entry_digest": "sha256:" + "0" * 64, "fsynced": True,
        }
        entry["entry_digest"] = canonical_digest(
            {k: v for k, v in entry.items() if k != "entry_digest"}
        )
        return entry

    genesis = _entry(0, None)
    second = _entry(1, genesis["entry_digest"])
    good = {
        "schema_version": "s2_4_authorization_replay_ledger_v1",
        "ledger_path": "/var/lib/arcane-equilibrium/aiml/install/s2_4/authorization-replay-ledger.json",
        "entries": [genesis, second], "append_only": True, "self_digest": "sha256:" + "0" * 64,
    }
    good["self_digest"] = artifact_self_digest(good)
    assert validate_aiml_artifact(good) == []
    assert good["entries"][0]["prev_entry_digest"] is None                       # genesis
    assert good["entries"][1]["prev_entry_digest"] == good["entries"][0]["entry_digest"]  # 鏈成立
    # 亂序:交換兩 entry → entries[1].prev 不再等於 entries[0].entry_digest(斷鏈)且首位不再是 genesis。
    reordered = [good["entries"][1], good["entries"][0]]
    assert reordered[1]["prev_entry_digest"] != reordered[0]["entry_digest"]
    assert reordered[0]["prev_entry_digest"] is not None
    # 重複:把 genesis 複製一份 → seq 重複且第二筆 prev 為 null(應鏈前一 entry_digest)→ 斷鏈。
    duplicated = [good["entries"][0], deepcopy(good["entries"][0])]
    assert duplicated[1]["seq"] == duplicated[0]["seq"]
    assert duplicated[1]["prev_entry_digest"] is None


# ── 2000 行拆分 E2 P1-1 回歸:package-form facade seam ─────────────────────────


def test_package_form_resolver_hits_loaded_facade_without_second_copy() -> None:
    """只載入 package 形 facade 的行程:resolver 必命中同一物件且不惰性創建頂層拷貝。

    E2 P1-1:leaf 的延遲 facade 讀取若硬編頂層名,在 package-form 行程會建立第二份
    完整 facade 拷貝,使 package 形模組物件上的 monkeypatch 被繞過。本測試以獨立
    subprocess 證明修復後:resolver 回傳的就是 package 形 facade 物件、頂層名不被
    惰性載入、對 package 形 facade 的信任根 patch 經 resolver 逐字可見。
    """

    program_code = str(ML_ROOT.parent)
    script = "\n".join((
        "import sys",
        f"sys.path.insert(0, {program_code!r})",
        "import ml_training.aiml_gate_receipt_validator as pkg_facade",
        "import ml_training.aiml_gate_receipt_s2_4_contracts as pkg_contracts",
        "assert 'aiml_gate_receipt_validator' not in sys.modules, 'top-level copy pre-exists'",
        "facade = pkg_contracts._resolve_facade()",
        "assert facade is pkg_facade, ('resolver returned a different module', facade.__name__)",
        "assert 'aiml_gate_receipt_validator' not in sys.modules, 'resolver lazily created a second copy'",
        "pkg_facade.S2_4_OPERATOR_TRUST_ROOT_FINGERPRINT = 'SHA256:forged-for-seam-test'",
        "seen = pkg_contracts._resolve_facade().S2_4_OPERATOR_TRUST_ROOT_FINGERPRINT",
        "assert seen == 'SHA256:forged-for-seam-test', ('patch bypassed', seen)",
        "print('SEAM_OK')",
    ))
    result = _subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr
    assert "SEAM_OK" in result.stdout


# ── S2.4 · WP4 · W2c(base/launch manifest 契約 schema)─────────────────────────
_W2C_D = "sha256:" + "c" * 64


def _w2c_fixtures() -> dict:
    base = {
        "schema_version": "base_runtime_tree_manifest_v1",
        "program_id": "AIML-LONG-LIVED-LANDING-V2",
        "component": "engine_scanner",
        "runtime_content_digest": _W2C_D,
        "target_platform": "x86_64-unknown-linux-gnu",
        "build_tool_versions": [{"tool": "python3", "version": "3.12.3"}],
        "interpreter_target": "bin/python3",
        "native_libraries": [{"path": "lib/libssl.so.3", "sha256": _W2C_D}],
        # P1-2:loader 閉包(樹內 ELF 的 PT_INTERP/DT_NEEDED)是 manifest 的必填面。
        "loader_closure": {
            "derivation": "in_tree_elf_pt_interp_dt_needed_v1",
            "binaries": [
                {
                    "path": "bin/python3",
                    "format": "elf64",
                    "machine": 62,
                    "interpreter": "/opt/arcane-equilibrium/aiml/launches/x/lib/libssl.so.3",
                    "soname": None,
                    "needed": ["libssl.so.3"],
                    "rpath": [],
                    "runpath": ["$ORIGIN/../lib"],
                },
                {
                    "path": "lib/libssl.so.3",
                    "format": "elf64",
                    "machine": 62,
                    "interpreter": None,
                    "soname": "libssl.so.3",
                    "needed": [],
                    "rpath": [],
                    "runpath": [],
                },
            ],
            "external_dependencies": [],
            "undecidable_host_facts": [
                "host_loader_resolved_realpaths",
                "inode_device_identity",
                "distribution_package_identity",
                "ldconfig_cache_and_ld_search_state",
            ],
        },
        "entries": [
            {"path": "bin", "type": "dir", "mode": "0755", "sha256": None},
            {"path": "bin/python3", "type": "file", "mode": "0555", "sha256": _W2C_D},
            {"path": "lib", "type": "dir", "mode": "0755", "sha256": None},
            {"path": "lib/libssl.so.3", "type": "file", "mode": "0555", "sha256": _W2C_D},
        ],
    }
    base["self_digest"] = artifact_self_digest(base)
    launch = {
        "schema_version": "launch_bundle_manifest_v1",
        "program_id": "AIML-LONG-LIVED-LANDING-V2",
        "component": "engine_scanner",
        "runtime_content_digest": _W2C_D,
        "base_runtime_tree_digest": "sha256:" + "d" * 64,
        "application_bundle_digest": "sha256:" + "e" * 64,
        # P1-1:launch 身分綁的是「已驗證的那個包」的 source head(非任意 digest 宣告)。
        "application_source_head": "a" * 40,
        "launcher_config_digest": "sha256:" + "f" * 64,
        "launch_tree_digest": "sha256:" + "1" * 64,
        "target_platform": "x86_64-unknown-linux-gnu",
    }
    launch["self_digest"] = artifact_self_digest(launch)
    return {
        "base_runtime_tree_manifest_v1": base,
        "launch_bundle_manifest_v1": launch,
    }


@pytest.mark.parametrize(
    "key", ("base_runtime_tree_manifest_v1", "launch_bundle_manifest_v1")
)
def test_w2c_manifest_round_trip_validates_clean(key: str) -> None:
    fixture = _w2c_fixtures()[key]
    assert validate_aiml_artifact(fixture) == [], key
    assert fixture["schema_version"] == key


@pytest.mark.parametrize(
    "key", ("base_runtime_tree_manifest_v1", "launch_bundle_manifest_v1")
)
def test_w2c_manifest_extra_key_and_self_digest_tamper_rejected(key: str) -> None:
    fixture = deepcopy(_w2c_fixtures()[key])
    fixture["__unexpected_extra__"] = "x"
    fixture["self_digest"] = artifact_self_digest(fixture)
    errors = validate_aiml_artifact(fixture)
    assert any("unexpected property" in e or "__unexpected_extra__" in e for e in errors)
    tampered = deepcopy(_w2c_fixtures()[key])
    tampered["runtime_content_digest"] = "sha256:" + "0" * 64  # 改 byte 不重封
    assert any("self_digest" in e for e in validate_aiml_artifact(tampered))


def test_w2c_base_manifest_canonical_sortedness_and_type_coherence() -> None:
    # entries 亂序(重封 self_digest)→ canonical 排序驗抓。
    shuffled = deepcopy(_w2c_fixtures()["base_runtime_tree_manifest_v1"])
    shuffled["entries"] = list(reversed(shuffled["entries"]))
    shuffled["self_digest"] = artifact_self_digest(shuffled)
    assert any("sorted" in e for e in validate_aiml_artifact(shuffled))
    # dir 帶 digest(file↔digest 不一致)→ 抓。
    incoherent = deepcopy(_w2c_fixtures()["base_runtime_tree_manifest_v1"])
    incoherent["entries"][0]["sha256"] = _W2C_D
    incoherent["self_digest"] = artifact_self_digest(incoherent)
    assert any("null for dirs" in e for e in validate_aiml_artifact(incoherent))
    # interpreter_target 缺席於 entries → 抓。
    orphan = deepcopy(_w2c_fixtures()["base_runtime_tree_manifest_v1"])
    orphan["entries"] = [e for e in orphan["entries"] if e["path"] != "bin/python3"]
    orphan["self_digest"] = artifact_self_digest(orphan)
    assert any("interpreter_target" in e for e in validate_aiml_artifact(orphan))


# ── S2.4 · WP4 · W2(review P1-5 / P1-6)owned-path commit 綁定 + builder 活探針 ──
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _git(cwd: Path, *args: str) -> str:
    return _subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _owned_scope_repo(tmp_path: Path, paths: tuple[str, ...]) -> Path:
    """把一組 owned path 複製進 throwaway repo 並提交(投影的可控實驗場)。"""
    import shutil

    repo = tmp_path / "owned-scope-repo"
    repo.mkdir()
    for rel in paths:
        source = _REPO_ROOT / rel
        if not source.is_file():
            continue
        destination = repo / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    for args in (
        ("init", "-q"),
        ("config", "user.email", "w2@test"),
        ("config", "user.name", "w2"),
        ("add", "-A"),
        ("commit", "-q", "-m", "owned scope snapshot"),
    ):
        _git(repo, *args)
    return repo


@pytest.mark.parametrize(
    "projection",
    ("w0_owned_path_diff_digest", "w1_owned_path_diff_digest", "w2_owned_path_diff_digest"),
)
def test_owned_path_projection_binds_commit_blobs_not_the_dirty_worktree(
    tmp_path: Path, projection: str
) -> None:
    """P1-5:owned 檔有 staged/unstaged 改動時,投影必須仍是**被綁定 commit** 的函數。

    修前:投影 hash 工作樹位元組,而 receipt 記的是未變的 HEAD;驗證端 hash 同一棵髒樹
    於是照樣 PASS,可是該 commit 的乾淨 checkout 永遠重現不出那份 receipt。
    修後:投影只讀 commit blob,髒工作樹不改變任何 digest,而髒這件事另有可見出口。
    """
    owned = {
        "w0_owned_path_diff_digest": _w0._W0_OWNED_PATHS,
        "w1_owned_path_diff_digest": _w0._W1_OWNED_PATHS,
        "w2_owned_path_diff_digest": _w0._W2_OWNED_PATHS,
    }[projection]
    repo = _owned_scope_repo(tmp_path, tuple(owned))
    derive = getattr(_w0, projection)
    clean = derive(repo)
    victim = next(rel for rel in sorted(owned) if (repo / rel).is_file())
    original = (repo / victim).read_bytes()
    (repo / victim).write_bytes(original + b"\n# smuggled worktree byte\n")
    assert (repo / victim).read_bytes() != original  # 工作樹確實已髒
    assert derive(repo) == clean  # 投影不隨髒工作樹改變(綁 commit blob)
    # 但「髒」本身必須看得見,而不是靜默
    delta = _w0.owned_scope_worktree_delta(repo, tuple(owned))
    assert victim in delta
    # 真的把它提交進去 → 這是**新的** commit,投影必須改變(綁定仍然有牙)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "commit the change")
    assert derive(repo) != clean
    assert _w0.owned_scope_worktree_delta(repo, tuple(owned)) == []
    # 舊 commit 仍可重現原值(投影是 commit 的函數)
    previous = _git(repo, "rev-parse", "HEAD~1")
    assert derive(repo, source_head=previous) == clean


def test_owned_path_projection_is_fail_closed_without_a_resolvable_commit(
    tmp_path: Path,
) -> None:
    """P1-5:不是 git checkout / commit 不可解析 → 全數 None(投影變值 → 導出失敗)。"""
    projection = _w0.owned_path_blob_projection(tmp_path, ("a.py", "b.py"))
    assert projection == {"a.py": None, "b.py": None}
    assert _w0.owned_scope_worktree_delta(tmp_path, ("a.py",)) is None


def _w2_projection_reasons(monkeypatch, **broken) -> list[str]:
    """以注入的壞 builder 再導出 W2 結構層,回傳 typed reasons。"""
    import agent_governance_s2_4_install as _install
    import agent_governance_s2_4_render as _render

    # 注意:install 模組**逐名 re-export** render 的 builder,故注入點必須逐個指名到
    # 探針真正呼叫的那個模組物件(patch 錯模組 = 測試靜默失效)。
    owners = {
        "build_application_bundle_manifest": _install,
        "build_base_runtime_tree_manifest": _render,
        "build_launch_bundle_manifest": _render,
    }
    for name, replacement in broken.items():
        monkeypatch.setattr(owners[name], name, replacement)
    receipt = {
        "wave": "W2",
        "predecessor_wave_receipt_digest": "sha256:" + "0" * 64,
        "owned_path_manifest_digest": canonical_digest(sorted(_w0._W2_OWNED_PATHS)),
        "owned_path_diff_digest": _w0.w2_owned_path_diff_digest(),
        "exported_abi_digest": "sha256:" + "0" * 64,
    }
    return _w0.w2_structural_errors(receipt)


def test_w2_exit_requires_live_probes_of_all_three_bundle_builders(monkeypatch) -> None:
    """P1-6:三個 builder 必須被**執行**;硬編字串 ABI 讓刪掉它們仍能重發 PASS。

    修前:W2 ABI 只以字串代表 base/launch builder、完全漏掉 application-bundle builder,
    而 w2_structural_errors 一個都沒跑過——把它們改壞只會改變 owned-byte digest,重發一份
    新 receipt 之後照樣 PASS。
    """
    helpers = _REPO_ROOT / "helper_scripts/maintenance_scripts"
    if str(helpers) not in sys.path:
        sys.path.insert(0, str(helpers))

    def _deleted(*args, **kwargs):
        raise AttributeError("builder deleted")

    for name, needle in (
        ("build_base_runtime_tree_manifest", "base runtime tree builder"),
        ("build_application_bundle_manifest", "application bundle builder"),
        ("build_launch_bundle_manifest", "launch bundle builder"),
    ):
        with monkeypatch.context() as patched:
            reasons = _w2_projection_reasons(patched, **{name: _deleted})
        assert any(needle in reason for reason in reasons), (name, reasons)


def test_w2_exit_requires_the_launch_builder_to_verify_application_bytes(
    monkeypatch,
) -> None:
    """P1-6/P1-1:launch builder 若「照單全收」任意 application digest,W2 必須拒絕導出。"""
    import agent_governance_s2_4_render as _render

    real_builder = _render.build_launch_bundle_manifest

    def _credulous(launch_tree_root, **kwargs):
        """模擬修前行為:不驗物化的包,語法正確的 digest 一律收下。"""
        supplied = kwargs["application_bundle_digest"]
        if not supplied.endswith("6" * 8):  # 真 digest → 照常建置
            return real_builder(launch_tree_root, **kwargs)
        return {  # 無關 digest → 修前照樣「BUILT」
            "status": "BUILT",
            "launch_bundle_digest": "sha256:" + "7" * 64,
            "launch_leaf_name": "7" * 64,
            "launch_tree_digest": "sha256:" + "8" * 64,
            "verified_application_bundle_digest": supplied,
            "manifest": {
                "application_bundle_digest": supplied,
                "base_runtime_tree_digest": kwargs["base_runtime_tree_digest"],
            },
        }

    with monkeypatch.context() as patched:
        reasons = _w2_projection_reasons(patched, build_launch_bundle_manifest=_credulous)
    assert any(
        "accepts an unrelated application_bundle_digest" in reason for reason in reasons
    ), reasons


def test_w2_exported_abi_carries_the_three_builder_probe_identities() -> None:
    """P1-6:探針結果(狀態 + digest)真的進了 exported-ABI 投影(receipt 可見)。"""
    projection = _w0.w2_exported_abi_projection()
    assert projection["base_runtime_tree_status"] == "BUILT"
    assert projection["application_bundle_status"] == "BUILT"
    assert projection["launch_bundle_status"] == "BUILT"
    assert projection["launch_binds_probed_application"] is True
    assert projection["launch_foreign_application_digest_status"] == "LAUNCH_BUNDLE_INVALID"
    for field in (
        "base_runtime_tree_probe_digest",
        "application_bundle_probe_digest",
        "launch_bundle_probe_digest",
    ):
        assert projection[field].startswith("sha256:"), field
    assert projection["application_bundle_builder"].endswith(
        "build_application_bundle_manifest"
    )
    # P1-4:連線期錯誤分類的 locale 契約亦折入(設定漂移 → receipt 面可見)。
    assert projection["connect_error_locale_contract_digest"].startswith("sha256:")
    # P1-5 可見性:owned scope 的工作樹差異是投影的一部分(髒發射不再是靜默事實)。
    assert isinstance(projection["owned_scope_worktree_delta"], list)
