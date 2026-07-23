"""Structural + bypass-negative tests for the LR0C real target-host probe (S1.6B).

Hermetic and runs everywhere: these tests exercise the choice/verdict LOGIC of the
target-host variant WITHOUT any systemd/bwrap/cgroup — the real non-root Linux
primitives run only on ``trade-core`` (a separate gated OPS step) and SKIP cleanly
here.  The suite asserts: the target-host receipt structure + committed schema; the
machine-encoded selection rule (OCI ``NON_SATISFIABLE_NON_ROOT`` boundary-driven
non-selection ⇒ ``final_choice==content_addressed_fixed_path``); the BINDING gate
(BINDING iff EVERY fixed-path seam ``PASSED_TARGET_HOST``, else
``PROVISIONAL_PENDING_LINUX`` naming the unmet seam — a BINDING claim over a
DEFERRED seam is REJECTED); the honest PLUGGABLE PG-identity deferral (recorded, not
faked); the attestation honesty gate (a Mac ``STRUCTURAL_ONLY`` synthesis cannot
certify the target-host exit); the boundary/no-production consts, applier!=verifier,
secret-scan; and that every bypass-negative REALLY fails closed.  The REAL on-host
executor functions are proven to SKIP (raise ``TargetHostUnavailableError``) on this
non-target node — never faked.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_target_host_probe as th  # noqa: E402
import agent_governance_component_effects as ce  # noqa: E402
from agent_governance_schema import schema_subset_errors  # noqa: E402


OBS = "2026-07-23T12:00:00+00:00"
FRESH = "2026-07-23T12:05:00+00:00"
STALE = "2026-07-23T13:30:00+00:00"

# 一個代表 governed on-host command_capture_v2 record_digest 的參照(真跑由 OPS capture 提供)。
CAP = "sha256:" + "c" * 64
# distinct 驗證者交來的真殘留觀察:units/cgroup/netns/temp 皆已清。
CLEAN_RESIDUE = {"units_gone": True, "cgroup_gone": True, "netns_gone": True, "temp_gone": True}


def _resign(obj):
    obj = copy.deepcopy(obj)
    obj.pop("self_digest", None)
    obj["self_digest"] = th.receipt_digest(obj)
    return obj


# --------------------------------------------------------------------------- #
# fixtures: an ATTESTED PASS reference (as the real trade-core run + distinct-OPS attach would emit)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def attested_binding():
    # pg real + independent_postcheck attached (distinct verifier) + bound capture digest -> BINDING
    return th.build_attested_reference_receipt(now=OBS, pg_mode=th.PG_MODE_REAL, capture_digest=CAP)


@pytest.fixture(scope="module")
def attested_provisional():
    # pg deferred (server absent), independent_postcheck attached -> PROVISIONAL_PENDING_LINUX naming pg_identity
    return th.build_attested_reference_receipt(now=OBS, pg_mode=th.PG_MODE_DEFERRED, capture_digest=CAP)


@pytest.fixture(scope="module")
def applier_only():
    # applier self-run: independent_postcheck DEFERRED, no distinct verifier yet -> PROVISIONAL naming it
    return th.build_attested_reference_receipt(
        now=OBS, pg_mode=th.PG_MODE_REAL, independent_postcheck_attached=False, capture_digest=CAP
    )


@pytest.fixture(scope="module")
def structural_ref():
    return th.build_structural_reference_receipt(now=OBS, pg_mode=th.PG_MODE_DEFERRED)


# --------------------------------------------------------------------------- #
# structure, schema, field-set, freshness, binding to source/schema
# --------------------------------------------------------------------------- #
def test_attested_binding_receipt_is_passing_and_self_consistent(attested_binding):
    assert attested_binding["status"] == "PASS"
    assert attested_binding["harness_id"] == "target_host_probe_v1"
    assert attested_binding["schema_version"] == "learning_runtime_choice_receipt_target_host_v1"
    assert attested_binding["target_class"] == "target_host"
    assert attested_binding["evidence_class"] == "PLATFORM_OR_EXTERNAL_ATTESTED"
    assert set(attested_binding) == th.RECEIPT_FIELDS
    assert th.validate_target_host_choice_receipt(
        attested_binding, require_success=True, require_target_host_attested=True, now=FRESH
    ) == []


def test_reference_receipt_matches_committed_schema(attested_binding, attested_provisional, structural_ref):
    schema = json.loads(th.RECEIPT_SCHEMA_PATH.read_text(encoding="utf-8"))
    for receipt in (attested_binding, attested_provisional, structural_ref):
        assert schema_subset_errors(receipt, schema, schema) == []


def test_receipt_binds_its_own_source_and_schema(attested_binding):
    assert attested_binding["source_sha256"] == th.source_sha256()
    assert attested_binding["schema_sha256"] == th.receipt_schema_sha256()
    assert attested_binding["self_digest"] == th.receipt_digest(attested_binding)


def test_stale_receipt_is_rejected(attested_binding):
    errors = th.validate_target_host_choice_receipt(attested_binding, now=STALE)
    assert any("not fresh" in error for error in errors)


def test_tampered_field_without_resign_is_rejected(attested_binding):
    tampered = copy.deepcopy(attested_binding)
    tampered["caller"] = "attacker-without-resign"
    errors = th.validate_target_host_choice_receipt(tampered, now=FRESH)
    assert any("self_digest does not match" in error for error in errors)


# --------------------------------------------------------------------------- #
# the final choice + OCI NON_SATISFIABLE_NON_ROOT boundary-driven non-selection
# --------------------------------------------------------------------------- #
def test_final_choice_is_fixed_path_and_oci_not_selectable(attested_binding):
    selection = attested_binding["selection"]
    assert selection["final_choice"] == "content_addressed_fixed_path"
    assert selection["oci_selectable"] is False
    assert selection["selection_rule"] == "oci_only_if_all_seams_pass_else_fixed_path"


def test_every_oci_seam_is_non_satisfiable_non_root(attested_binding):
    oci_block = next(b for b in attested_binding["candidate_probes"] if b["candidate_id"] == "exact_image_id_oci")
    assert {seam["seam_id"] for seam in oci_block["seams"]} == th.TARGET_HOST_SEAM_SET
    assert all(seam["verdict"] == "NON_SATISFIABLE_NON_ROOT" for seam in oci_block["seams"])
    # 理由必明示 LR2 no-OCI-socket 邊界(PM Q1)。
    assert all("LR2" in seam["note"] for seam in oci_block["seams"])
    assert "lr2_no_oci_socket_dbus" in oci_block["caveats"]


def test_oci_seam_claimed_satisfiable_is_rejected(attested_binding):
    # OCI-non-satisfiable 被拒進非選擇:謊稱某 OCI seam 可滿足 → validator 拒。
    forged = copy.deepcopy(attested_binding)
    oci_block = next(b for b in forged["candidate_probes"] if b["candidate_id"] == "exact_image_id_oci")
    oci_block["seams"][0]["verdict"] = "PASSED_TARGET_HOST"
    forged = _resign(forged)
    errors = th.validate_target_host_choice_receipt(forged, now=FRESH)
    assert any("NON_SATISFIABLE_NON_ROOT" in error for error in errors)


def test_forced_oci_selection_is_machine_rejected(attested_binding):
    forged = copy.deepcopy(attested_binding)
    forged["selection"]["final_choice"] = "exact_image_id_oci"
    forged = _resign(forged)
    errors = th.validate_target_host_choice_receipt(forged, now=FRESH)
    assert any("select OCI" in error for error in errors)


# --------------------------------------------------------------------------- #
# the BINDING gate: BINDING iff every fixed-path seam PASSED; else PROVISIONAL
# --------------------------------------------------------------------------- #
def test_all_fixed_path_seams_passed_is_binding(attested_binding):
    fixed = next(b for b in attested_binding["candidate_probes"] if b["candidate_id"] == "content_addressed_fixed_path")
    assert {seam["seam_id"] for seam in fixed["seams"]} == th.TARGET_HOST_SEAM_SET
    assert all(seam["verdict"] == "PASSED_TARGET_HOST" for seam in fixed["seams"])
    assert attested_binding["selection"]["binding"] == "BINDING"
    assert attested_binding["selection"]["pending_seams"] == []


def test_deferred_seam_makes_choice_provisional_naming_the_seam(attested_provisional):
    # PROVISIONAL when a seam is DEFERRED — the honest PG-deferred path (server absent).
    assert attested_provisional["status"] == "PASS"  # 探針有效跑過
    assert attested_provisional["selection"]["binding"] == "PROVISIONAL_PENDING_LINUX"
    assert attested_provisional["selection"]["pending_seams"] == ["pg_identity"]
    assert attested_provisional["probe_scope"]["pg_identity_mode"] == "deferred_server_absent"
    fixed = next(b for b in attested_provisional["candidate_probes"] if b["candidate_id"] == "content_addressed_fixed_path")
    pg_seam = next(seam for seam in fixed["seams"] if seam["seam_id"] == "pg_identity")
    assert pg_seam["verdict"] == "DEFERRED_TARGET_HOST"
    # 誠實:note 明說 server 未安裝、綁 S1.1、裝上即翻真(未造假)。
    assert "postgresql-server not installed" in pg_seam["note"]
    assert th.validate_target_host_choice_receipt(
        attested_provisional, require_success=True, require_target_host_attested=True, now=FRESH
    ) == []


def test_binding_receipt_with_a_deferred_fixed_path_seam_is_rejected(attested_provisional):
    # 一張硬標 BINDING 卻仍夾 DEFERRED fixed-path seam(pg_identity)的 receipt 必被拒(必為 PROVISIONAL)。
    forged = copy.deepcopy(attested_provisional)
    forged["selection"]["binding"] = "BINDING"
    forged["selection"]["pending_seams"] = []
    forged = _resign(forged)
    errors = th.validate_target_host_choice_receipt(forged, now=FRESH)
    assert any("claims BINDING but these fixed-path seams" in error for error in errors)


def test_provisional_without_unmet_seam_is_rejected(attested_binding):
    # 全 seam PASSED 卻標 PROVISIONAL → 拒(必為 BINDING)。
    forged = copy.deepcopy(attested_binding)
    forged["selection"]["binding"] = "PROVISIONAL_PENDING_LINUX"
    forged["selection"]["pending_seams"] = ["pg_identity"]
    forged = _resign(forged)
    errors = th.validate_target_host_choice_receipt(forged, now=FRESH)
    assert any("PROVISIONAL_PENDING_LINUX but every fixed-path seam PASSED" in error for error in errors)


def test_pending_seams_must_exactly_name_unmet(attested_provisional):
    forged = copy.deepcopy(attested_provisional)
    forged["selection"]["pending_seams"] = ["start_stop"]  # 未如實指名 pg_identity
    forged = _resign(forged)
    errors = th.validate_target_host_choice_receipt(forged, now=FRESH)
    assert any("pending_seams must exactly name" in error for error in errors)


# --------------------------------------------------------------------------- #
# #1 independent_postcheck: applier alone is PROVISIONAL; a DISTINCT verifier attach -> BINDING
# --------------------------------------------------------------------------- #
def test_applier_only_receipt_is_provisional_naming_independent_postcheck(applier_only):
    # applier 自跑:independent_postcheck DEFERRED -> PROVISIONAL 指名它,絕非 BINDING。
    assert applier_only["status"] == "PASS"
    assert applier_only["selection"]["binding"] == "PROVISIONAL_PENDING_LINUX"
    assert applier_only["selection"]["pending_seams"] == ["independent_postcheck"]
    fixed = next(b for b in applier_only["candidate_probes"] if b["candidate_id"] == "content_addressed_fixed_path")
    ip_seam = next(s for s in fixed["seams"] if s["seam_id"] == "independent_postcheck")
    assert ip_seam["verdict"] == "DEFERRED_TARGET_HOST"
    # 自跑 receipt 就算有 capture digest 也仍是 PROVISIONAL(獨立確認未到位)。
    assert th.validate_target_host_choice_receipt(applier_only, now=FRESH) == []


def test_attach_by_distinct_verifier_upgrades_to_binding(applier_only):
    bound = th.attach_independent_postcheck(
        applier_only, verifier_node="s16b_independent_verifier",
        residue_observation=CLEAN_RESIDUE, now=OBS,
    )
    assert bound["selection"]["binding"] == "BINDING"
    assert bound["selection"]["pending_seams"] == []
    fixed = next(b for b in bound["candidate_probes"] if b["candidate_id"] == "content_addressed_fixed_path")
    ip_seam = next(s for s in fixed["seams"] if s["seam_id"] == "independent_postcheck")
    assert ip_seam["verdict"] == "PASSED_TARGET_HOST"
    # 附掛後(capture digest + ATTESTED + 全 seam PASSED)方可被採信為真出口。
    assert th.validate_target_host_choice_receipt(
        bound, require_success=True, require_target_host_attested=True, now=FRESH
    ) == []


def test_same_actor_attach_is_rejected(applier_only):
    with pytest.raises(ce.ApplierIsSoleVerifierError):
        th.attach_independent_postcheck(
            applier_only, verifier_node="s16b_apply_actor",  # == apply_actor_node -> 拒
            residue_observation=CLEAN_RESIDUE, now=OBS,
        )


def test_attach_requires_a_clean_residue_observation(applier_only):
    # 殘留未清(temp 未消)-> 不得附掛 PASS。
    with pytest.raises(th.TargetHostProbeError):
        th.attach_independent_postcheck(
            applier_only, verifier_node="s16b_independent_verifier",
            residue_observation={"units_gone": True, "cgroup_gone": True, "netns_gone": True, "temp_gone": False},
            now=OBS,
        )


def test_attach_on_already_attached_is_rejected(attested_binding):
    # independent_postcheck 已 PASSED,再附掛 -> 拒(非 DEFERRED)。
    with pytest.raises(th.TargetHostProbeError):
        th.attach_independent_postcheck(
            attested_binding, verifier_node="s16b_independent_verifier",
            residue_observation=CLEAN_RESIDUE, now=OBS,
        )


def test_deferred_independent_postcheck_cannot_be_binding(applier_only):
    # 硬標 BINDING 卻仍夾 DEFERRED independent_postcheck -> BINDING 閘拒。
    forged = copy.deepcopy(applier_only)
    forged["selection"]["binding"] = "BINDING"
    forged["selection"]["pending_seams"] = []
    forged = _resign(forged)
    errors = th.validate_target_host_choice_receipt(forged, now=FRESH)
    assert any("claims BINDING but these fixed-path seams" in error for error in errors)


# --------------------------------------------------------------------------- #
# #3 attestation binds to a governed on-host capture digest, not a self-set label
# --------------------------------------------------------------------------- #
def test_reference_without_capture_digest_fails_require_attested():
    ref = th.build_attested_reference_receipt(now=OBS, pg_mode=th.PG_MODE_REAL)  # capture_digest=None
    assert ref["target_host_capture_digest"] is None
    errors = th.validate_target_host_choice_receipt(ref, require_target_host_attested=True, now=FRESH)
    assert any("target_host_capture_digest" in error for error in errors)


def test_bound_capture_digest_passes_require_attested():
    bound = th.build_attested_reference_receipt(now=OBS, pg_mode=th.PG_MODE_REAL, capture_digest=CAP)
    assert bound["target_host_capture_digest"] == CAP
    assert th.validate_target_host_choice_receipt(
        bound, require_success=True, require_target_host_attested=True, now=FRESH
    ) == []


def test_malformed_capture_digest_is_rejected(attested_binding):
    forged = copy.deepcopy(attested_binding)
    forged["target_host_capture_digest"] = "not-a-sha256"
    forged = _resign(forged)
    errors = th.validate_target_host_choice_receipt(forged, now=FRESH)
    assert any("target_host_capture_digest must be a sha256" in error for error in errors)


# --------------------------------------------------------------------------- #
# #4 per-primitive non-root / no-production boundary (defense-in-depth, direct-call safe)
# --------------------------------------------------------------------------- #
def test_non_root_boundary_rejects_production_paths(monkeypatch):
    monkeypatch.setattr(th, "_passwordless_sudo_present", lambda: False)
    for prod in ("/opt/aiml/models", "/opt/openclaw/x", "/usr/lib/x", "/srv/y"):
        with pytest.raises(th.FailClosedStop):
            th._assert_non_root_boundary(prod)
    # 安全路徑(非生產前綴)通過,不 raise。
    th._assert_non_root_boundary("/tmp/aiml-safe-scratch")


def test_non_root_boundary_rejects_root(monkeypatch):
    monkeypatch.setattr(th.os, "geteuid", lambda: 0)
    with pytest.raises(th.FailClosedStop):
        th._assert_non_root_boundary("/tmp/whatever")


def test_non_root_boundary_rejects_passwordless_sudo(monkeypatch):
    monkeypatch.setattr(th, "_passwordless_sudo_present", lambda: True)
    with pytest.raises(th.FailClosedStop):
        th._assert_non_root_boundary()


@pytest.mark.parametrize("call", [
    lambda: th.probe_native_lib_loading_on_host(bundle_dir="/opt/aiml/models"),
    lambda: th.probe_immutable_closure_on_host(deploy_root="/opt/openclaw/bundle"),
    lambda: th.probe_failure_rollback_cleanup_on_host(nonce="x", launcher_argv=["/bin/true"], teardown_root="/srv/x"),
])
def test_primitive_direct_call_on_production_path_rejected(monkeypatch, call):
    # 直呼 primitive(即使假裝在 target host)碰生產路徑 -> boundary 於 spawn 前 fail-closed。
    monkeypatch.setattr(th, "target_host_available", lambda: True)
    monkeypatch.setattr(th, "_passwordless_sudo_present", lambda: False)
    with pytest.raises(th.FailClosedStop):
        call()


# --------------------------------------------------------------------------- #
# PLUGGABLE PG-identity: real vs deferred, recorded not faked; mode/seam consistency
# --------------------------------------------------------------------------- #
def test_pg_mode_real_requires_pg_seam_passed():
    seams = th.synthesize_fixed_path_seams(th.PG_MODE_DEFERRED)  # pg DEFERRED
    with pytest.raises(th.TargetHostProbeError):
        # pg_identity_mode=real 卻餵 DEFERRED pg seam → 不一致,builder raise。
        th.build_target_host_choice_receipt(
            caller="t", platform=th.detect_platform(), target_class="target_host",
            host_identity=th._structural_host_identity(),
            apply_actor_node="a", postcheck_verifier_node="v",
            fixed_path_seams=seams, pg_identity_mode=th.PG_MODE_REAL,
            evidence_class="PLATFORM_OR_EXTERNAL_ATTESTED",
            real_target_host_primitives_invoked=True, complete_teardown_verified=True,
            runtime_candidate_receipt_a_digest="sha256:" + "0" * 64,
            runtime_candidate_receipt_b_digest="sha256:" + "1" * 64,
            runtime_candidate_comparison_digest="sha256:" + "2" * 64,
            effect_seams_ready_receipt_digest="sha256:" + "3" * 64,
            pg_readonly_identity_receipt_digest="sha256:" + "4" * 64,
            observation_time=OBS, ttl_seconds=900,
        )


def test_pg_deferred_path_is_recorded_not_faked(attested_provisional):
    # deferred 模式:pg_identity_mode + seam verdict + note 一致誠實;S1.1 receipt 以 digest 綁定。
    assert attested_provisional["probe_scope"]["pg_identity_mode"] == "deferred_server_absent"
    dep = attested_provisional["dependency_receipts"]
    assert th.DIGEST_RE.fullmatch(dep["pg_readonly_identity_receipt_digest"])


def test_native_representativeness_flag_only_on_native_seam(attested_binding):
    fixed = next(b for b in attested_binding["candidate_probes"] if b["candidate_id"] == "content_addressed_fixed_path")
    by_id = {seam["seam_id"]: seam for seam in fixed["seams"]}
    assert by_id["native_lib_loading"]["representativeness"] == "representative_native_lib"
    for seam_id, seam in by_id.items():
        if seam_id != "native_lib_loading":
            assert "representativeness" not in seam


# --------------------------------------------------------------------------- #
# the attestation honesty gate: Mac structural cannot certify the target-host exit
# --------------------------------------------------------------------------- #
def test_structural_only_receipt_is_fail_and_cannot_be_attested(structural_ref):
    assert structural_ref["status"] == "FAIL"
    assert structural_ref["evidence_class"] == "STRUCTURAL_ONLY"
    assert structural_ref["boundary"]["real_target_host_primitives_invoked"] is False
    # DERIVED 選擇欄位仍如實(邏輯可測),但需真出口時被拒。
    assert structural_ref["selection"]["final_choice"] == "content_addressed_fixed_path"
    errors = th.validate_target_host_choice_receipt(structural_ref, require_target_host_attested=True, now=FRESH)
    assert any("not PLATFORM_OR_EXTERNAL_ATTESTED" in error for error in errors)


def test_structural_only_receipt_fails_require_success(structural_ref):
    errors = th.validate_target_host_choice_receipt(structural_ref, require_success=True, now=FRESH)
    assert any("does not prove a passing target-host probe" in error for error in errors)


def test_faked_attestation_without_invoked_is_rejected(structural_ref):
    # 謊稱 ATTESTED+PASS 卻 real_target_host_primitives_invoked=false → PASS 分支拒(假背書)。
    forged = copy.deepcopy(structural_ref)
    forged["evidence_class"] = "PLATFORM_OR_EXTERNAL_ATTESTED"
    forged["status"] = "PASS"
    forged["failure_reason"] = None
    forged["probe_scope"]["target_host_probe_performed"] = True
    forged = _resign(forged)
    errors = th.validate_target_host_choice_receipt(forged, now=FRESH)
    assert any("real_target_host_primitives_invoked true" in error for error in errors)


def test_pass_acceptance_without_now_is_rejected(attested_binding):
    errors = th.validate_target_host_choice_receipt(attested_binding, require_success=True, now=None)
    assert any("requires a non-null now" in error for error in errors)


# --------------------------------------------------------------------------- #
# boundary consts + no-production assertions
# --------------------------------------------------------------------------- #
def test_boundary_consts_and_no_production(attested_binding):
    boundary = attested_binding["boundary"]
    for flag in ("non_root", "user_scope_only", "no_docker_invoked", "no_system_scope",
                 "no_production_path", "prod_pg_untouched", "applier_ne_verifier"):
        assert boundary[flag] is True, flag
    assert boundary["production_running_attested"] is False
    assert attested_binding["production_running_attested"] is False
    assert attested_binding["platform"]["non_root_oci_runtime_available"] is False
    host = attested_binding["host_identity"]
    assert host["passwordless_sudo_present"] is False
    assert host["non_root_uid"] is True
    assert th.REQUIRED_DELEGATED_CONTROLLERS <= set(host["delegated_controllers"])
    # PM Q4:cpuset/io 記為 root-only 延後。
    assert set(host["deferred_root_only_controllers"]) == set(th.DEFERRED_ROOT_ONLY_CONTROLLERS)


@pytest.mark.parametrize("flag,needle", [
    ("no_production_path", "no_production_path must be true"),
    ("no_docker_invoked", "no_docker_invoked must be true"),
    ("no_system_scope", "no_system_scope must be true"),
    ("prod_pg_untouched", "prod_pg_untouched must be true"),
])
def test_boundary_flag_flipped_is_rejected(attested_binding, flag, needle):
    forged = copy.deepcopy(attested_binding)
    forged["boundary"][flag] = False
    forged = _resign(forged)
    errors = th.validate_target_host_choice_receipt(forged, now=FRESH)
    assert any(needle in error for error in errors)


def test_forged_production_running_attested_is_rejected(attested_binding):
    forged = copy.deepcopy(attested_binding)
    forged["production_running_attested"] = True
    forged["boundary"]["production_running_attested"] = True
    forged = _resign(forged)
    errors = th.validate_target_host_choice_receipt(forged, now=FRESH)
    assert any("production_running_attested" in error for error in errors)


def test_passwordless_sudo_and_missing_controller_rejected(attested_binding):
    sudo = _resign({**copy.deepcopy(attested_binding), "host_identity": {**attested_binding["host_identity"], "passwordless_sudo_present": True}})
    assert any("passwordless_sudo_present must be false" in e for e in th.validate_target_host_choice_receipt(sudo, now=FRESH))
    missing = copy.deepcopy(attested_binding)
    missing["host_identity"]["delegated_controllers"] = ["cpu", "pids"]
    missing = _resign(missing)
    assert any("delegated_controllers must include" in e for e in th.validate_target_host_choice_receipt(missing, now=FRESH))


# --------------------------------------------------------------------------- #
# builder-level fail-closed raises
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad_class", ["production", "disposable_local", "disposable_offline"])
def test_non_target_host_class_raises(bad_class):
    with pytest.raises(th.TargetClassRejectedError):
        th.build_target_host_choice_receipt(
            caller="t", platform=th.detect_platform(), target_class=bad_class,
            host_identity=th._structural_host_identity(),
            apply_actor_node="a", postcheck_verifier_node="v",
            fixed_path_seams=th.synthesize_fixed_path_seams(th.PG_MODE_REAL),
            pg_identity_mode=th.PG_MODE_REAL, evidence_class="PLATFORM_OR_EXTERNAL_ATTESTED",
            real_target_host_primitives_invoked=True, complete_teardown_verified=True,
            runtime_candidate_receipt_a_digest="sha256:" + "0" * 64,
            runtime_candidate_receipt_b_digest="sha256:" + "1" * 64,
            runtime_candidate_comparison_digest="sha256:" + "2" * 64,
            effect_seams_ready_receipt_digest="sha256:" + "3" * 64,
            pg_readonly_identity_receipt_digest="sha256:" + "4" * 64,
            observation_time=OBS, ttl_seconds=900,
        )


def test_applier_equals_verifier_raises():
    with pytest.raises(ce.ApplierIsSoleVerifierError):
        th.build_target_host_choice_receipt(
            caller="t", platform=th.detect_platform(), target_class="target_host",
            host_identity=th._structural_host_identity(),
            apply_actor_node="same", postcheck_verifier_node="same",
            fixed_path_seams=th.synthesize_fixed_path_seams(th.PG_MODE_REAL),
            pg_identity_mode=th.PG_MODE_REAL, evidence_class="PLATFORM_OR_EXTERNAL_ATTESTED",
            real_target_host_primitives_invoked=True, complete_teardown_verified=True,
            runtime_candidate_receipt_a_digest="sha256:" + "0" * 64,
            runtime_candidate_receipt_b_digest="sha256:" + "1" * 64,
            runtime_candidate_comparison_digest="sha256:" + "2" * 64,
            effect_seams_ready_receipt_digest="sha256:" + "3" * 64,
            pg_readonly_identity_receipt_digest="sha256:" + "4" * 64,
            observation_time=OBS, ttl_seconds=900,
        )


def test_incomplete_fixed_path_seam_set_raises():
    partial = th.synthesize_fixed_path_seams(th.PG_MODE_REAL)[:-1]  # 只 7 個 seam
    with pytest.raises(th.TargetHostProbeError):
        th.build_target_host_choice_receipt(
            caller="t", platform=th.detect_platform(), target_class="target_host",
            host_identity=th._structural_host_identity(),
            apply_actor_node="a", postcheck_verifier_node="v",
            fixed_path_seams=partial, pg_identity_mode=th.PG_MODE_REAL,
            evidence_class="PLATFORM_OR_EXTERNAL_ATTESTED",
            real_target_host_primitives_invoked=True, complete_teardown_verified=True,
            runtime_candidate_receipt_a_digest="sha256:" + "0" * 64,
            runtime_candidate_receipt_b_digest="sha256:" + "1" * 64,
            runtime_candidate_comparison_digest="sha256:" + "2" * 64,
            effect_seams_ready_receipt_digest="sha256:" + "3" * 64,
            pg_readonly_identity_receipt_digest="sha256:" + "4" * 64,
            observation_time=OBS, ttl_seconds=900,
        )


def test_secret_ingress_raises(attested_binding):
    poisoned = copy.deepcopy(attested_binding)
    poisoned["selection"]["reason"] = "authorization=Bearer plaintexthunter2exampletoken"
    with pytest.raises(th.SecretLeakageError):
        th._guard_no_secret({k: v for k, v in poisoned.items() if k != "secret_scan"})


# --------------------------------------------------------------------------- #
# bypass-negatives: all sixteen REALLY fail closed (non-vacuous)
# --------------------------------------------------------------------------- #
def test_all_bypass_negatives_fail_closed():
    cases = th.build_bypass_negative_cases(now=OBS)
    assert len(cases) == 16
    assert {case["bypass_kind"] for case in cases} == th.BYPASS_KIND_SET
    assert all(case["observed_verdict"] == "REJECTED" for case in cases)
    assert all(case["expected"] == "FAIL_CLOSED" for case in cases)


def test_bypass_runner_is_non_vacuous():
    with pytest.raises(th.TargetHostProbeError):
        th.run_bypass_negative("no_such_kind", now=OBS)


def test_vacuous_rejection_reraises(monkeypatch):
    monkeypatch.setitem(th._BYPASS_RUNNERS, "matrix_digest_tamper", lambda now: None)
    with pytest.raises(th.TargetHostProbeError):
        th.run_bypass_negative("matrix_digest_tamper", now=OBS)


# --------------------------------------------------------------------------- #
# the REAL on-host executor SKIPS cleanly on this non-target node (never fakes)
# --------------------------------------------------------------------------- #
def test_target_host_unavailable_on_this_node():
    # 非 target host(Mac / 無 systemd-run / 未設 AIML_TARGET_HOST_PROBE=1)→ False。
    assert th.target_host_available() is False


@pytest.mark.parametrize("call", [
    lambda: th.run_target_host_probe(throwaway_root="/tmp/aiml", pg_readonly_identity_receipt_digest="sha256:" + "0" * 64),
    lambda: th.preflight_target_host(throwaway_root="/tmp/aiml"),
    lambda: th.probe_start_stop_on_host(launcher_argv=["/bin/true"], nonce="x"),
    lambda: th.probe_cgroup_isolation_on_host(nonce="x"),
    lambda: th.probe_network_denial_on_host(),
    lambda: th.probe_native_lib_loading_on_host(bundle_dir="/tmp/aiml"),
    lambda: th.probe_immutable_closure_on_host(deploy_root="/tmp/aiml"),
    lambda: th.probe_failure_rollback_cleanup_on_host(nonce="x", launcher_argv=["/bin/true"], teardown_root="/tmp/aiml"),
    lambda: th.probe_pg_identity_on_host(pg_readonly_identity_receipt_digest="sha256:" + "0" * 64),
    lambda: th.pg_identity_mode_on_host(),
])
def test_on_host_functions_skip_not_fake(call):
    # 每個真效果 on-host 函式在非 target host 被呼叫 → TargetHostUnavailableError(乾淨跳過,絕不造假)。
    with pytest.raises(th.TargetHostUnavailableError):
        call()


# --------------------------------------------------------------------------- #
# self-validating: NOT registered in the central AIML closure validator
# --------------------------------------------------------------------------- #
def test_target_host_receipt_is_not_registered_in_central_validator():
    import aiml_gate_receipt_validator as validator
    assert "learning_runtime_choice_receipt_target_host_v1" not in validator.SCHEMA_FILES
    assert "learning_runtime_choice_receipt_v1" not in validator.SCHEMA_FILES
