"""S2.5(WP5)中央閘委派分支測試(design §5/§6/§11)。

覆蓋:五 schema round-trip + closed 拒外鍵、v3 additive 分類(exact adapter/actor/postcheck/
rollback;cross-version digest 拒、降版拒、adapter 替換拒)、frozen S0.3 classifier 與 v1/v2
matrix digest 逐位不變、SCHEMA_FILES 註冊而 PROGRAM_SCHEMA_PATHS 未動、now 必帶+過期
fail-closed、never-refreshable(任何 refresh 一律拒)、fixture 偽裝 platform-attested 拒
(§8.3 硬邊界)。
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ML_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ML_ROOT.parents[1]
HELPERS = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
for _candidate in (ML_ROOT, HELPERS):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from aiml_gate_receipt_validator import (  # noqa: E402
    PROGRAM_SCHEMA_PATHS,
    SCHEMA_DIR,
    SCHEMA_FILES,
    aiml_effect_classifier_digest,
    aiml_component_effect_class_matrix_digest,
    aiml_component_effect_class_matrix_v2_digest,
    artifact_self_digest,
    canonical_digest,
    validate_aiml_artifact,
)
import aiml_gate_receipt_s2_5 as leaf  # noqa: E402

ANCHOR = datetime(2030, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
NOW = (ANCHOR + timedelta(minutes=2)).isoformat()
LATE = (ANCHOR + timedelta(days=2)).isoformat()

# 拆分前後三個分類身分 digest 的凍結值(§0/§11 #2:byte-frozen 釘死;v3 落地不得動它們)。
FROZEN_S0_3 = "sha256:1cf8c021b066ceeb364e968add074d263cb28d63db421fdc40620e9904d0ddbc"


def _core(phase: str = "S2_5A_START") -> dict:
    is_final = phase == "S2_5B_FINAL"
    return {
        "schema_version": "s2_5_start_core_v1",
        "phase": phase,
        "target_host": "trade-core",
        "unit_name": "arcane-equilibrium-aiml-engine-scanner.service",
        "expected_unit_fragment_digest": "sha256:" + "a" * 64,
        "s2_4_install_effect_receipt_digest": "sha256:" + "b" * 64,
        "expected_launch_bundle_digest": "sha256:" + "c" * 64,
        "expected_application_bundle_digest": "sha256:" + "d" * 64,
        "expected_base_runtime_tree_digest": "sha256:" + "e" * 64,
        "native_loader_closure_digest": "sha256:" + "f" * 64,
        "s2_1_drill_receipt_digest": "sha256:" + "1" * 64 if is_final else None,
        "pre_drill_attestation_digest": "sha256:" + "4" * 64 if is_final else None,
        "attestation_window": {
            "max_evidence_age_seconds": 120, "min_samples": 3, "sample_interval_seconds": 5,
        },
        "start_budget_seconds": 120,
        "rollback_budget_seconds": 120,
        "safety_margin_seconds": 30,
        "authorization_profile": {
            "profile_identity": (
                "aiml-s2-5b-final-operator-v1" if is_final else "aiml-s2-5a-start-operator-v1"
            ),
            "signature_namespace": (
                "arcane-equilibrium-aiml-s2-5b-final"
                if is_final
                else "arcane-equilibrium-aiml-s2-5a-start"
            ),
            "attestor_identity": "aiml-s2-5-runtime-attestor-v1",
            "attestor_namespace": "arcane-equilibrium-aiml-s2-5-running-attestation",
            "max_ttl_seconds": 900,
        },
        "source_head": "0" * 40,
        "issued_at": ANCHOR.isoformat(),
        "expires_at": (ANCHOR + timedelta(minutes=10)).isoformat(),
    }


def _intent(phase: str = "S2_5A_START") -> dict:
    core = _core(phase)
    core_digest = canonical_digest(core)
    intent = {
        "schema_version": "s2_5_start_intent_v1",
        "route_class": "s2_5_start_intent",
        "core": core,
        "core_digest": core_digest,
        "start_id": "s2-5-" + core_digest.split(":", 1)[1],
        "route_surface": {
            "required_effect_class": leaf.S2_5_PHASE_EFFECT_CLASS[phase],
            "effect_lineage": "WATCHDOG_ROLLBACK_TEST",
            "runtime_effect": True,
            "service": "installed_unit_lifecycle_only",
            "risk": "critical",
            "runtime_claim": True,
        },
        "forbidden_surfaces": {
            name: False
            for name in (
                "pg_write", "migration", "secret", "credential_install", "host_identity",
                "prepare_fetch_build", "unit_render_install", "daemon_reload",
                "broker_or_order",
            )
        },
        "expires_at": (ANCHOR + timedelta(minutes=10)).isoformat(),
    }
    intent["self_digest"] = artifact_self_digest(intent)
    return intent


def _observer_gate() -> dict:
    return {
        "verifier_node_id": "s2-5-independent-verifier",
        "db_evidence_via_observer_role": True,
        "max_evidence_age_seconds": 120,
        "oldest_evidence_at": (ANCHOR + timedelta(minutes=1)).isoformat(),
        "evaluated_at": (ANCHOR + timedelta(minutes=2)).isoformat(),
        "stale": False,
    }


def _dimensions() -> dict:
    return {
        "unit": {
            "active_state": "active", "sub_state": "running",
            "unit_file_state": "enabled", "main_pid": 4001,
            "n_restarts_baseline": 0, "fragment_digest_match": True,
        },
        "pid_cgroup": {
            "cmdline_digest": "sha256:" + "2" * 64, "control_group_match": True,
            "boot_id": "boot-1", "process_start_ticks": "1234567",
            "invocation_id": "inv-1",
        },
        "mount": {
            "launch_root_match": True, "loader_closure_match": True,
            "executable_mappings_in_manifest": True,
        },
        "network": {
            "address_families_ok": True, "ip_allow_loopback_only": True,
            "listening_sockets_empty": True,
        },
        "pg_identity": {
            "advisory_lock_holder_count": 1, "backend_role": "aiml_engine_scanner",
            "backend_database": "trading_ai", "session_started_seen": True,
            "unclosed_session_absent": True, "topology_guard_match": True,
        },
    }


def _running_receipt(status: str = "SOURCE_SIMULATION_PASS", **overrides) -> dict:
    intent = _intent()
    receipt = {
        "schema_version": "s2_5_running_attestation_v1",
        "adapter_id": "s2_5_runtime_start_adapter_v1",
        "status": status,
        "intent_id": intent["start_id"],
        "intent_digest": intent["self_digest"],
        "target_class": "simulated_harness",
        "target_host": "trade-core",
        "unit_name": "arcane-equilibrium-aiml-engine-scanner.service",
        "owner_fingerprint": "sha256:" + "3" * 64,
        "running_dimensions": _dimensions(),
        "enabled_persistence": {
            "unit_file_state": "enabled", "wanted_by_link_present": True,
            "reboot_survival_observed": None,
        },
        "observer_gate": _observer_gate(),
        "precheck": {
            "inactive_prestate_verified": True, "loader_closure_reverified": True,
            "s2_4_recovery_clear": True, "install_lock_free": True,
        },
        # S2E.3 F4:鎖窗 typed 關閉的證據(成功臂的硬條件)。
        "lock_window": {
            "hold_acquired": True,
            "hold_released": True,
            "release_status": "S2_5_LIFECYCLE_LOCK_RELEASED",
        },
        "rollback_record": None,
        "apply_actor_node": "s2-5-start-applier",
        "independent_verifier_node": "s2-5-independent-verifier",
        "verifier_capture_digest": None,
        "trusted_host_attestation": None,
        "evidence_class": "LOCAL_REPRODUCIBLE",
        "boundary": {
            "production_started_by_source_lane": False,
            "production_running_attested_without_attestor": False,
            "fixture_impersonates_platform_attested": False,
            "nine_authorities_false": True,
        },
        "started_at": (ANCHOR + timedelta(minutes=1)).isoformat(),
        "completed_at": (ANCHOR + timedelta(minutes=2)).isoformat(),
        "evidence_expires_at": (ANCHOR + timedelta(minutes=10)).isoformat(),
        "failure_reason": None,
        "source_head": "0" * 40,
    }
    receipt.update(overrides)
    receipt["self_digest"] = artifact_self_digest(receipt)
    return receipt


# ── §11 #1:五 schema round-trip + closed 拒外鍵 ─────────────────────────────────
def test_s2_5_schemas_are_registered_and_round_trip_cleanly():
    for name in (
        "s2_5_start_core_v1", "s2_5_start_intent_v1", "s2_5_running_attestation_v1",
        "s2_5_final_attestation_v1", "s2_5_rollback_drill_receipt_v1",
        "aiml_component_effect_classification_v3",
    ):
        assert name in SCHEMA_FILES
        assert (SCHEMA_DIR / SCHEMA_FILES[name]).is_file()
    assert validate_aiml_artifact(_core(), now=NOW) == []
    assert validate_aiml_artifact(_core("S2_5B_FINAL"), now=NOW) == []
    assert validate_aiml_artifact(_intent(), now=NOW) == []
    assert validate_aiml_artifact(_intent("S2_5B_FINAL"), now=NOW) == []
    assert validate_aiml_artifact(_running_receipt(), now=NOW) == []


def test_s2_5_closed_schemas_reject_extra_keys_and_missing_now():
    intent = _intent()
    smuggled = deepcopy(intent)
    smuggled["command"] = "systemctl start foo"
    smuggled["self_digest"] = artifact_self_digest(smuggled)
    assert validate_aiml_artifact(smuggled, now=NOW)
    # now 必帶:缺 now 一律 fail-closed(§11 #17)。
    errors = validate_aiml_artifact(intent, now=None)
    assert any("requires now" in error for error in errors)
    # 過期 fail-closed。
    assert any(
        "expired" in error for error in validate_aiml_artifact(intent, now=LATE)
    )


def test_forbidden_intent_keys_are_rejected_even_when_nested():
    intent = _intent()
    # closed schema 擋不到「值物件內」的鍵——核心 FORBIDDEN_INTENT_KEYS 掃描補上。
    hits = leaf._forbidden_key_hits({"core": {"deep": {"signal": 9}}})
    assert hits == ["$.core.deep.signal"]


def test_phase_cross_consts_are_mutually_exclusive():
    # S2.5A 帶 drill digest ⇒ 拒;S2.5B 缺 drill digest ⇒ 拒(§11 #12)。
    core_a = _core()
    core_a["s2_1_drill_receipt_digest"] = "sha256:" + "1" * 64
    assert validate_aiml_artifact(core_a, now=NOW)
    core_b = _core("S2_5B_FINAL")
    core_b["s2_1_drill_receipt_digest"] = None
    assert validate_aiml_artifact(core_b, now=NOW)


def test_intent_id_and_core_digest_rederive():
    intent = _intent()
    forged = deepcopy(intent)
    forged["start_id"] = "s2-5-" + "9" * 64
    forged["self_digest"] = artifact_self_digest(forged)
    assert any(
        "start_id" in error for error in validate_aiml_artifact(forged, now=NOW)
    )
    drifted = deepcopy(intent)
    drifted["core"]["target_host"] = "other-host"
    drifted["self_digest"] = artifact_self_digest(drifted)
    assert any(
        "core_digest" in error for error in validate_aiml_artifact(drifted, now=NOW)
    )


# ── §11 #2:frozen digests 逐位不變 ─────────────────────────────────────────────
def test_frozen_classifier_and_v1_v2_matrix_digests_are_unchanged():
    assert aiml_effect_classifier_digest() == FROZEN_S0_3
    assert aiml_component_effect_class_matrix_digest() == (
        "sha256:22d78882a2dace9ceb640b74b2a5dca2f2a8cc05861720f5ab25c5c9ac86c445"
    )
    assert aiml_component_effect_class_matrix_v2_digest() == (
        "sha256:01d3062c79725b32b7c1468d02013a0df28dfeba1cf29d513cbf3bd6b4143c64"
    )
    assert "aiml_component_effect_classification_v3" not in PROGRAM_SCHEMA_PATHS
    assert not any(str(key).startswith("s2_5_") for key in PROGRAM_SCHEMA_PATHS)


# ── §11 #3:v3 additive 分類 ────────────────────────────────────────────────────
def _v3_work_package(effect_class: str = "ENGINE_SCANNER_SERVICE_START") -> dict:
    row = leaf.AIML_COMPONENT_EFFECT_CLASS_MATRIX_V3[effect_class]
    return {
        "component_work_package_id": "AIML-S2.5-WP5",
        "component_effect_class": effect_class,
        "declared_adapter_id": row["adapter_id"],
        "declared_intent_fields": list(row["required_intent_fields"]),
        "owned_path_manifest": [],
        "direct_interfaces": [],
    }


def test_v3_classification_round_trips_for_both_classes():
    for effect_class in leaf.AIML_COMPONENT_EFFECT_CLASS_MATRIX_V3:
        classification = leaf.classify_component_required_effects_v3(
            _v3_work_package(effect_class), classified_at=NOW
        )
        assert validate_aiml_artifact(classification, now=NOW) == []
        effect = classification["required_effects"][0]
        assert effect["adapter_binding_status"] == "AUTHORITY_LOCKED_PRODUCTION_CAPABLE"


def test_v3_rejects_adapter_substitution_and_source_only_downgrade():
    package = _v3_work_package()
    package["declared_adapter_id"] = "s2_4_install_adapter_v1"
    with pytest.raises(ValueError, match="not the admitted adapter"):
        leaf.classify_component_required_effects_v3(package, classified_at=NOW)
    downgraded = _v3_work_package()
    downgraded["component_effect_class"] = None
    downgraded["direct_interfaces"] = ["s2_5_host_service_actor"]
    with pytest.raises(ValueError, match="cannot be source-only"):
        leaf.classify_component_required_effects_v3(downgraded, classified_at=NOW)


def test_v3_cross_version_digest_and_downgrade_are_rejected():
    classification = leaf.classify_component_required_effects_v3(
        _v3_work_package(), classified_at=NOW
    )
    # v2 digest 冒充 v3 ⇒ 拒。
    forged = deepcopy(classification)
    forged["classifier_digest"] = aiml_component_effect_class_matrix_v2_digest()
    forged["classification_id"] = leaf._identity_digest(forged)
    forged["self_digest"] = artifact_self_digest(forged)
    assert any(
        "not admitted" in error for error in validate_aiml_artifact(forged, now=NOW)
    )
    # 把 v3 分類降版成 v2 schema_version ⇒ v2 分支以 v2 digest 檢查 ⇒ 拒。
    downgraded = deepcopy(classification)
    downgraded["schema_version"] = "aiml_component_effect_classification_v2"
    downgraded["classification_id"] = leaf._identity_digest(downgraded)
    downgraded["self_digest"] = artifact_self_digest(downgraded)
    assert validate_aiml_artifact(downgraded, now=NOW)


# ── §11 #18:never-refreshable ────────────────────────────────────────────────
def test_any_s2_5_refresh_by_reference_is_forbidden():
    receipt = _running_receipt()
    refresh = {"schema_version": "s2_4_dependency_refresh_attestation_v1"}
    for evidence_class in leaf.S2_5_NEVER_REFRESHABLE_EVIDENCE:
        verdict = leaf.derive_s2_5_source_dependency_admission_status(
            evidence_class=evidence_class, receipt=receipt, refresh=refresh, now=NOW
        )
        assert verdict["status"] == "DEPENDENCY_REFRESH_BY_REFERENCE_FORBIDDEN"
    fresh = leaf.derive_s2_5_source_dependency_admission_status(
        evidence_class="S2_5_RUNNING_ATTESTATION", receipt=receipt, now=NOW
    )
    assert fresh["status"] == "SOURCE_DEPENDENCY_FRESH"
    expired = leaf.derive_s2_5_source_dependency_admission_status(
        evidence_class="S2_5_RUNNING_ATTESTATION", receipt=receipt, now=LATE
    )
    assert expired["status"] == "DEPENDENCY_EVIDENCE_REOBSERVATION_REQUIRED"
    unknown = leaf.derive_s2_5_source_dependency_admission_status(
        evidence_class="NOT_A_CLASS", receipt=receipt, now=NOW
    )
    assert unknown["status"] == "SOURCE_DEPENDENCY_REJECTED"


# ── §8.3 硬邊界:fixture 永不假冒 platform-attested PASS ─────────────────────────
def test_fixture_impersonating_platform_attested_is_structurally_rejected():
    # simulated 目標宣稱 PLATFORM_OR_EXTERNAL_ATTESTED ⇒ closed allOf 拒。
    forged = _running_receipt(evidence_class="PLATFORM_OR_EXTERNAL_ATTESTED")
    assert validate_aiml_artifact(forged, now=NOW)
    # simulated 目標夾帶偽 attestor 物件 ⇒ allOf(trusted_host_attestation 必 null)拒。
    with_attestor = _running_receipt(trusted_host_attestation={
        "attestor_identity": "aiml-s2-5-runtime-attestor-v1",
        "signature_namespace": "arcane-equilibrium-aiml-s2-5-running-attestation",
        "attestation_kind": "A",
        "intent_digest": "sha256:" + "0" * 64,
        "running_dimensions_digest": "sha256:" + "0" * 64,
        "observer_gate_digest": "sha256:" + "0" * 64,
        "trusted_host_time": NOW,
        "expires_at": (ANCHOR + timedelta(minutes=10)).isoformat(),
        "signature_armored": "-----BEGIN SSH SIGNATURE-----\nforged\n-----END SSH SIGNATURE-----",
    })
    assert validate_aiml_artifact(with_attestor, now=NOW)
    # RUNNING_ATTESTED 在 simulated 目標上 ⇒ allOf(必 production)拒。
    impersonated = _running_receipt(status="RUNNING_ATTESTED")
    assert validate_aiml_artifact(impersonated, now=NOW)
    # boundary 旗標翻面 ⇒ const 拒(九 authority/impersonation 面;§8.4)。
    flipped = _running_receipt()
    flipped["boundary"]["fixture_impersonates_platform_attested"] = True
    flipped["self_digest"] = artifact_self_digest(flipped)
    assert validate_aiml_artifact(flipped, now=NOW)
    flipped2 = _running_receipt()
    flipped2["boundary"]["nine_authorities_false"] = False
    flipped2["self_digest"] = artifact_self_digest(flipped2)
    assert validate_aiml_artifact(flipped2, now=NOW)


def test_production_running_attested_with_forged_signature_is_rejected_at_the_gate():
    """§8.4 刀:「RUNNING_ATTESTED 的 attestor 驗簽呼叫刪除」的紅測試(中央閘層)。

    production 目標 + 結構完好的 attestor 物件 + 偽簽章 ⇒ 中央閘必拒——刪掉委派葉的
    `_attestation_errors` 呼叫,這支測試就是那把刀的紅。
    """

    forged = _running_receipt(
        status="RUNNING_ATTESTED",
        target_class="production",
        evidence_class="PLATFORM_OR_EXTERNAL_ATTESTED",
        trusted_host_attestation={
            "attestor_identity": "aiml-s2-5-runtime-attestor-v1",
            "signature_namespace": "arcane-equilibrium-aiml-s2-5-running-attestation",
            "attestation_kind": "A",
            "intent_digest": _intent()["self_digest"],
            "running_dimensions_digest": canonical_digest(_dimensions()),
            "observer_gate_digest": canonical_digest(_observer_gate()),
            "trusted_host_time": NOW,
            "expires_at": (ANCHOR + timedelta(minutes=10)).isoformat(),
            "signature_armored": (
                "-----BEGIN SSH SIGNATURE-----\nZm9yZ2Vk\n-----END SSH SIGNATURE-----"
            ),
        },
    )
    errors = validate_aiml_artifact(forged, now=NOW)
    assert any("SSH signature is invalid" in error for error in errors), errors


# ── §5.4 option (b):各 schema 的 const-false 守衛各自 load-bearing ────────────────
def test_success_statuses_require_fresh_observer_gate_and_passing_dimensions():
    stale_gate = _observer_gate()
    stale_gate["oldest_evidence_at"] = ANCHOR.isoformat()
    stale_gate["evaluated_at"] = (ANCHOR + timedelta(minutes=30)).isoformat()
    # 超齡但仍自稱 stale=False ⇒ 代碼級 dead-man 拒。
    over_age = _running_receipt(observer_gate=stale_gate)
    assert any(
        "dead-man" in error for error in validate_aiml_artifact(over_age, now=NOW)
    )
    # 任一維 fail 而 status 仍 SOURCE_SIMULATION_PASS ⇒ 拒。
    dims = _dimensions()
    dims["network"]["listening_sockets_empty"] = False
    failing = _running_receipt(running_dimensions=dims)
    assert any(
        "failing" in error for error in validate_aiml_artifact(failing, now=NOW)
    )
    # verifier == applier ⇒ 拒(schema 表達不了,代碼級)。
    same_actor = _running_receipt(
        independent_verifier_node="s2-5-start-applier",
        observer_gate=dict(_observer_gate(), verifier_node_id="s2-5-start-applier"),
    )
    assert any(
        "differ" in error for error in validate_aiml_artifact(same_actor, now=NOW)
    )


def test_rollback_drill_receipt_semantics_have_teeth():
    base = {
        "schema_version": "s2_5_rollback_drill_receipt_v1",
        "kind": "ROLLBACK_TO_DISABLED",
        "status": "RESTORED_INACTIVE",
        "intent_id": "s2-5-" + "0" * 64,
        "unit_name": "arcane-equilibrium-aiml-engine-scanner.service",
        "pre_state": {
            "active_state": "inactive", "unit_file_state": "disabled",
            "n_restarts": 0, "invocation_id": "none",
        },
        "post_state": {
            "active_state": "inactive", "unit_file_state": "disabled",
            "n_restarts": 0, "invocation_id": "none",
        },
        "operation": {"kind": "systemd_stop_disable"},
        "s2_4_inactive_prestate_digest": "sha256:" + "5" * 64,
        "watchdog_last": None,
        "observed_at": (ANCHOR + timedelta(minutes=2)).isoformat(),
        "expires_at": (ANCHOR + timedelta(minutes=10)).isoformat(),
        "source_head": "0" * 40,
    }
    base["self_digest"] = artifact_self_digest(base)
    assert validate_aiml_artifact(base, now=NOW) == []
    # RESTORED_INACTIVE 但 post_state 仍 active ⇒ allOf 拒。
    not_restored = deepcopy(base)
    not_restored["post_state"]["active_state"] = "active"
    not_restored["self_digest"] = artifact_self_digest(not_restored)
    assert validate_aiml_artifact(not_restored, now=NOW)
    # WATCHDOG_RESET_LAST 而 watchdog_last=null ⇒ allOf 拒(§5.4 各自 load-bearing)。
    reset_missing = deepcopy(base)
    reset_missing["kind"] = "WATCHDOG_RESET_LAST"
    reset_missing["status"] = "RESET_CLEAN"
    reset_missing["operation"] = {"kind": "systemd_reset_failed"}
    reset_missing["s2_4_inactive_prestate_digest"] = None
    reset_missing["self_digest"] = artifact_self_digest(reset_missing)
    assert validate_aiml_artifact(reset_missing, now=NOW)
    # RESET_CLEAN 但 unexplained_restart_detected=true ⇒ allOf 拒。
    dirty_reset = deepcopy(reset_missing)
    dirty_reset["watchdog_last"] = {
        "watchdog_usec": "none", "n_restarts_before": 0, "n_restarts_after": 1,
        "invocation_id_before": "inv-1", "invocation_id_after": "inv-2",
        "last_lifecycle_operation": {"kind": "systemd_reset_failed"},
        "last_transition_matches_authorized_op": True,
        "unexplained_restart_detected": True,
    }
    dirty_reset["post_state"]["n_restarts"] = 1
    dirty_reset["self_digest"] = artifact_self_digest(dirty_reset)
    assert validate_aiml_artifact(dirty_reset, now=NOW)


# ── tranche 1b(E2 F2):PLATFORM 類 evidence_class ⇒ attested status + attestor 在場 ──
def test_non_attested_status_cannot_claim_platform_evidence_class():
    forged = _running_receipt(
        status="EXTERNAL_VERIFICATION_PENDING",
        target_class="production",
        evidence_class="PLATFORM_OR_EXTERNAL_ATTESTED",
        failure_reason="pending the trusted-host attestor",
    )
    errors = validate_aiml_artifact(forged, now=NOW)
    assert any("PLATFORM_OR_EXTERNAL_ATTESTED requires" in error for error in errors)


# ── tranche 1b(E2 F6/M4a):verifier≠applier 兩臂各自 load-bearing ──────────────────
def test_observer_gate_verifier_equal_to_applier_is_rejected_alone():
    # 只翻 observer_gate 臂(independent_verifier_node 維持相異)。
    receipt = _running_receipt(
        observer_gate=dict(_observer_gate(), verifier_node_id="s2-5-start-applier"),
    )
    errors = validate_aiml_artifact(receipt, now=NOW)
    assert any("dead-man verifier" in error for error in errors)
    assert not any(
        error.startswith("independent_verifier_node") for error in errors
    )


def test_independent_verifier_equal_to_applier_is_rejected_alone():
    # 只翻 independent_verifier_node 臂(observer_gate 維持相異)。
    receipt = _running_receipt(independent_verifier_node="s2-5-start-applier")
    errors = validate_aiml_artifact(receipt, now=NOW)
    assert any(
        "independent_verifier_node must differ" in error for error in errors
    )
    assert not any("dead-man verifier" in error for error in errors)


# ── tranche 1b(E2 F9):attested 與 simulation 常量拆分 ────────────────────────────
def test_success_status_constants_are_split_and_disjoint():
    assert not hasattr(leaf, "_S2_5_SUCCESS_STATUSES")  # 舊合併常量已除役。
    assert leaf._S2_5_ATTESTED_STATUSES == {"RUNNING_ATTESTED", "FINAL_ATTESTED"}
    assert leaf._S2_5_SIMULATION_STATUSES == {"SOURCE_SIMULATION_PASS"}
    assert not (leaf._S2_5_ATTESTED_STATUSES & leaf._S2_5_SIMULATION_STATUSES)


# ── tranche 1b(E3 P1-3):s2_5 replay ledger schema + 鏈重驗 ───────────────────────
def _sealed_ledger() -> dict:
    entries = []
    previous = None
    for index, auth_hex in enumerate(("a", "c")):
        entry = {
            "seq": index,
            "prev_entry_digest": previous,
            "authorization_id": "s2-5-auth-" + auth_hex * 64,
            "start_id": "s2-5-" + "b" * 64,
            "consumed_at": NOW,
            "fsynced": True,
        }
        entry["entry_digest"] = canonical_digest(entry)
        previous = entry["entry_digest"]
        entries.append(entry)
    ledger = {
        "schema_version": "s2_5_authorization_replay_ledger_v1",
        "ledger_path": "/var/lib/arcane-equilibrium/aiml/install/s2_5/"
        "authorization-replay-ledger.json",
        "entries": entries,
        "append_only": True,
    }
    ledger["self_digest"] = artifact_self_digest(ledger)
    return ledger


def test_s2_5_replay_ledger_schema_round_trips_and_rejects_tampering():
    assert "s2_5_authorization_replay_ledger_v1" in SCHEMA_FILES
    assert (SCHEMA_DIR / SCHEMA_FILES["s2_5_authorization_replay_ledger_v1"]).is_file()
    ledger = _sealed_ledger()
    assert validate_aiml_artifact(ledger) == []
    # 尾截斷後未重封 ⇒ self_digest 重算即斷(整本清空另由 schema minItems 拒)。
    truncated = deepcopy(ledger)
    truncated["entries"].pop()
    assert any(
        "self_digest" in error for error in validate_aiml_artifact(truncated)
    )
    wiped = deepcopy(ledger)
    wiped["entries"] = []
    assert validate_aiml_artifact(wiped)
    # seq 竄改 ⇒ 鏈重驗斷(fork/reorder 同一臂)。
    reordered = deepcopy(ledger)
    reordered["entries"][0]["seq"] = 1
    reordered["self_digest"] = artifact_self_digest(reordered)
    assert any(
        "hash chain is broken" in error for error in validate_aiml_artifact(reordered)
    )
    # append_only 翻面 ⇒ closed schema 拒。
    mutable = deepcopy(ledger)
    mutable["append_only"] = False
    mutable["self_digest"] = artifact_self_digest(mutable)
    assert validate_aiml_artifact(mutable)


# ── tranche 1b(E2 條件性 P1,E1#1):§6 closure binding ───────────────────────────
def _ops_preflight(intent: dict) -> dict:
    fragment = {
        "schema_version": "s2_5_ops_preflight_fragment_v1_informal",
        "intent_digest": intent["self_digest"],
        "preflight": {"unit_inactive_confirmed": True},
    }
    fragment["self_digest"] = artifact_self_digest(fragment)
    return fragment


def test_attestation_binding_pending_branch_is_typed_not_skipped():
    intent = _intent()
    receipt = _running_receipt()
    verdict = leaf.validate_s2_5_attestation_binding(
        intent=intent, ops_preflight=_ops_preflight(intent), receipt=receipt,
        verifier_capture=None, now=NOW,
    )
    # source lane:verifier_capture_digest 為 None ⇒ typed PENDING 分支,絕不是 PASS。
    assert verdict["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert any("not yet bound" in reason for reason in verdict["reasons"])


def _verifier_capture(node_id: str = "ops-postcheck-verifier") -> dict:
    """P2-3 之後的合法 capture record:record_digest 由 record bytes canonical 重算而得。"""

    capture = {
        "schema_version": "command_capture_v2",
        "node_id": node_id,
        "argv": ["/usr/bin/systemctl", "show",
                 "arcane-equilibrium-aiml-engine-scanner.service", "--no-pager"],
        "exit_code": 0,
    }
    capture["record_digest"] = canonical_digest(capture)
    return capture


def test_attestation_binding_three_way_cross_check_verifies_and_rejects():
    intent = _intent()
    capture = _verifier_capture()
    receipt = _running_receipt(verifier_capture_digest=capture["record_digest"])
    verdict = leaf.validate_s2_5_attestation_binding(
        intent=intent, ops_preflight=_ops_preflight(intent), receipt=receipt,
        verifier_capture=capture, now=NOW,
    )
    assert verdict["status"] == "S2_5_ATTESTATION_BINDING_VERIFIED", verdict
    # capture node == applier ⇒ 拒(applier 永不自證)。
    self_capture = _verifier_capture(node_id="s2-5-start-applier")
    self_receipt = _running_receipt(
        verifier_capture_digest=self_capture["record_digest"]
    )
    self_run = leaf.validate_s2_5_attestation_binding(
        intent=intent, ops_preflight=_ops_preflight(intent), receipt=self_receipt,
        verifier_capture=self_capture, now=NOW,
    )
    assert self_run["status"] == "S2_5_ATTESTATION_BINDING_REJECTED"
    # record_digest 不等 receipt 綁定值 ⇒ 拒。
    drifted_receipt = _running_receipt(verifier_capture_digest="sha256:" + "8" * 64)
    drifted = leaf.validate_s2_5_attestation_binding(
        intent=intent, ops_preflight=_ops_preflight(intent), receipt=drifted_receipt,
        verifier_capture=capture, now=NOW,
    )
    assert drifted["status"] == "S2_5_ATTESTATION_BINDING_REJECTED"
    # 單側主張(receipt 有 digest、capture 缺席)⇒ 拒,不是 PENDING。
    one_sided = leaf.validate_s2_5_attestation_binding(
        intent=intent, ops_preflight=_ops_preflight(intent), receipt=receipt,
        verifier_capture=None, now=NOW,
    )
    assert one_sided["status"] == "S2_5_ATTESTATION_BINDING_REJECTED"


def test_attestation_binding_rejects_a_self_reported_record_digest():
    """P2-3(tranche 2)紅→綠:偽造 capture=照抄 receipt 綁定值的兩鍵 stub 必拒。

    修前:capture 的 record_digest 只做字串相等比對,{"record_digest": 照抄,
    "node_id": "x"} 可直達 VERIFIED;修後 canonical 重算三值鏈,必斷。
    """

    intent = _intent()
    forged_digest = "sha256:" + "7" * 64
    receipt = _running_receipt(verifier_capture_digest=forged_digest)
    forged = {"record_digest": forged_digest, "node_id": "x"}
    verdict = leaf.validate_s2_5_attestation_binding(
        intent=intent, ops_preflight=_ops_preflight(intent), receipt=receipt,
        verifier_capture=forged, now=NOW,
    )
    assert verdict["status"] == "S2_5_ATTESTATION_BINDING_REJECTED", verdict
    assert any("never trusted" in reason for reason in verdict["reasons"])
    # 非 dict capture(裸 digest 字串)⇒ fail-closed 拒。
    bare = leaf.validate_s2_5_attestation_binding(
        intent=intent, ops_preflight=_ops_preflight(intent), receipt=receipt,
        verifier_capture=forged_digest, now=NOW,
    )
    assert bare["status"] == "S2_5_ATTESTATION_BINDING_REJECTED"
    assert any("well-formed" in reason for reason in bare["reasons"])
    # node_id 缺席(匿名 capture)⇒ 拒——即使 record_digest 真的由重算得出。
    anonymous = {"schema_version": "command_capture_v2", "exit_code": 0}
    anonymous["record_digest"] = canonical_digest(anonymous)
    anon_receipt = _running_receipt(
        verifier_capture_digest=anonymous["record_digest"]
    )
    anon = leaf.validate_s2_5_attestation_binding(
        intent=intent, ops_preflight=_ops_preflight(intent), receipt=anon_receipt,
        verifier_capture=anonymous, now=NOW,
    )
    assert anon["status"] == "S2_5_ATTESTATION_BINDING_REJECTED"
    assert any("node_id" in reason for reason in anon["reasons"])
    # record_digest 非 sha256 形狀(最小 record 形狀)⇒ 拒。
    malformed = {"record_digest": "not-a-digest", "node_id": "y"}
    bad_shape = leaf.validate_s2_5_attestation_binding(
        intent=intent, ops_preflight=_ops_preflight(intent),
        receipt=_running_receipt(verifier_capture_digest="sha256:" + "6" * 64),
        verifier_capture=malformed, now=NOW,
    )
    assert bad_shape["status"] == "S2_5_ATTESTATION_BINDING_REJECTED"
    assert any("sha256" in reason for reason in bad_shape["reasons"])


def test_attestation_binding_requires_unit_inactive_confirmed_true():
    """note-2(tranche 2)紅→綠:OPS preflight 的語義面——unit_inactive_confirmed 必須
    為 true。false(誠實重封 self_digest)修前可過結構驗直達 PENDING/VERIFIED。"""

    intent = _intent()
    receipt = _running_receipt()
    live_preflight = {
        "schema_version": "s2_5_ops_preflight_fragment_v1_informal",
        "intent_digest": intent["self_digest"],
        "preflight": {"unit_inactive_confirmed": False},
    }
    live_preflight["self_digest"] = artifact_self_digest(live_preflight)
    verdict = leaf.validate_s2_5_attestation_binding(
        intent=intent, ops_preflight=live_preflight, receipt=receipt,
        verifier_capture=None, now=NOW,
    )
    assert verdict["status"] == "S2_5_ATTESTATION_BINDING_REJECTED", verdict
    assert any("unit_inactive_confirmed" in reason for reason in verdict["reasons"])
    # preflight 面缺席(無 preflight 子物件)同拒。
    faceless = {
        "schema_version": "s2_5_ops_preflight_fragment_v1_informal",
        "intent_digest": intent["self_digest"],
    }
    faceless["self_digest"] = artifact_self_digest(faceless)
    verdict2 = leaf.validate_s2_5_attestation_binding(
        intent=intent, ops_preflight=faceless, receipt=receipt,
        verifier_capture=None, now=NOW,
    )
    assert verdict2["status"] == "S2_5_ATTESTATION_BINDING_REJECTED"


def test_attestation_binding_rejects_broken_preflight_and_foreign_intent():
    intent = _intent()
    receipt = _running_receipt()
    # OPS preflight 自報 digest(重算不符)⇒ 拒。
    forged_preflight = _ops_preflight(intent)
    forged_preflight["preflight"]["unit_inactive_confirmed"] = False  # 未重封。
    verdict = leaf.validate_s2_5_attestation_binding(
        intent=intent, ops_preflight=forged_preflight, receipt=receipt,
        verifier_capture=None, now=NOW,
    )
    assert verdict["status"] == "S2_5_ATTESTATION_BINDING_REJECTED"
    # receipt 綁的是另一份 intent ⇒ 拒。
    foreign_intent = _intent("S2_5B_FINAL")
    verdict2 = leaf.validate_s2_5_attestation_binding(
        intent=foreign_intent, ops_preflight=_ops_preflight(foreign_intent),
        receipt=receipt, verifier_capture=None, now=NOW,
    )
    assert verdict2["status"] == "S2_5_ATTESTATION_BINDING_REJECTED"
