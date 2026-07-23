"""Structural + bypass-negative tests for the LR0C runtime choice probe (S1.6).

Hermetic and runs everywhere: the disposable ``temp_dir_artifact`` lifecycle is pure
stdlib (real ``os.replace`` pointer swaps in a ``tmp_path`` dir) and the S1.4
dependency receipts are proven by a real ``python3 -I`` subprocess — NO daemon, NO
initdb, NO docker, NO network.  It asserts the choice-receipt structure, the
machine-encoded selection rule (``final_choice==content_addressed_fixed_path``,
``oci_selectable==false``, nothing-running-attested), the honest disposable-vs-deferred
seam split, the dependency-digest binding, ``supersedes_comparison_null``, and that
every §9 bypass-negative REALLY fails closed.

The ``initdb``-gated real disposable PG-identity seam lives in the companion
``_disposable`` module; this one never needs a server.
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

import agent_governance_runtime_choice_probe as rc  # noqa: E402
import agent_governance_component_effects as ce  # noqa: E402
import agent_governance_runtime_candidate_spike as spike  # noqa: E402
from agent_governance_schema import schema_subset_errors  # noqa: E402


OBS = "2026-07-22T12:00:00+00:00"
FRESH = "2026-07-22T12:05:00+00:00"
STALE = "2026-07-22T13:30:00+00:00"


# --------------------------------------------------------------------------- #
# fixtures: one honest PASS reference receipt (real filesystem lifecycle) reused widely
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def base_dir(tmp_path_factory):
    return str(tmp_path_factory.mktemp("aiml_s16_structural"))


@pytest.fixture(scope="module")
def receipt(base_dir):
    return rc._honest_reference_receipt(OBS, base_dir)


def _resign(obj):
    obj = copy.deepcopy(obj)
    obj.pop("self_digest", None)
    obj["self_digest"] = rc.receipt_digest(obj)
    return obj


# --------------------------------------------------------------------------- #
# honest PASS receipt: structure, schema, field-set, freshness
# --------------------------------------------------------------------------- #
def test_reference_receipt_is_passing_and_self_consistent(receipt):
    assert receipt["status"] == "PASS"
    assert receipt["harness_id"] == "runtime_choice_probe_v1"
    assert receipt["schema_version"] == "learning_runtime_choice_receipt_v1"
    assert receipt["target_class"] == "disposable_local"
    assert set(receipt) == rc.RECEIPT_FIELDS
    assert rc.validate_learning_runtime_choice_receipt(receipt, require_success=True, now=FRESH) == []


def test_reference_receipt_matches_committed_schema(receipt):
    schema = json.loads(rc.RECEIPT_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema_subset_errors(receipt, schema, schema) == []


def test_receipt_binds_its_own_source_and_schema(receipt):
    assert receipt["source_sha256"] == rc.source_sha256()
    assert receipt["schema_sha256"] == rc.receipt_schema_sha256()
    assert receipt["self_digest"] == rc.receipt_digest(receipt)


def test_stale_receipt_is_rejected(receipt):
    errors = rc.validate_learning_runtime_choice_receipt(receipt, now=STALE)
    assert any("not fresh" in error for error in errors)


# --------------------------------------------------------------------------- #
# the final choice + the machine-encoded selection rule (§5.1 / §6)
# --------------------------------------------------------------------------- #
def test_final_choice_is_fixed_path_binding_and_oci_not_selectable(receipt):
    selection = receipt["selection"]
    assert selection["final_choice"] == "content_addressed_fixed_path"
    assert selection["oci_selectable"] is False
    assert selection["binding"] == "BINDING"
    assert selection["selection_rule"] == "oci_only_if_all_seams_pass_else_fixed_path"
    assert list(selection["selection_basis"]) == list(rc.SELECTION_BASIS)
    # target_host_probe_performed honestly false ⇒ the rule forces fixed-path.
    assert receipt["probe_scope"]["target_host_probe_performed"] is False


def test_nothing_running_is_attested(receipt):
    assert receipt["production_running_attested"] is False
    boundary = receipt["boundary"]
    for flag in (
        "production_running_attested", "real_target_host_probe_on_mac", "real_process_started",
        "native_lib_loaded_on_target", "kernel_isolation_exercised", "network_contact",
    ):
        assert boundary[flag] is False, flag
    assert boundary["nine_authorities_false"] is True
    assert receipt["platform"]["target_host_container_runtime_available"] is False


def test_supersedes_comparison_null_and_binds_s14_by_digest(receipt, base_dir):
    assert receipt["supersedes_comparison_null"] is True
    receipt_a, receipt_b, comparison = rc._hermetic_s14_dependencies(OBS, base_dir + "/rebind")
    dep = receipt["dependency_receipts"]
    # the bound comparison digest is a real comparison whose final_choice is null (S1.4 stays const-null).
    assert comparison["final_choice"] is None
    assert rc.DIGEST_RE.fullmatch(dep["runtime_candidate_receipt_a_digest"])
    assert rc.DIGEST_RE.fullmatch(dep["runtime_candidate_comparison_digest"])
    assert dep["component_effect_matrix_digest"] == ce.component_effect_matrix_digest()


def test_oci_selection_rule_is_machine_enforced(receipt):
    # 偽造:硬把 final_choice 改成 OCI(target_host_probe_performed 仍 false)→ 被規則拒。
    forged = _resign({**copy.deepcopy(receipt), "selection": {**receipt["selection"], "final_choice": "exact_image_id_oci"}})
    errors = rc.validate_learning_runtime_choice_receipt(forged, now=FRESH)
    assert any("select OCI" in error for error in errors)


def test_forged_production_running_attested_is_rejected(receipt):
    forged = copy.deepcopy(receipt)
    forged["production_running_attested"] = True
    forged["boundary"]["production_running_attested"] = True
    forged = _resign(forged)
    errors = rc.validate_learning_runtime_choice_receipt(forged, now=FRESH)
    assert any("production_running_attested" in error for error in errors)


def test_forged_deferred_seam_marked_disposably_proven_is_rejected(receipt):
    forged = copy.deepcopy(receipt)
    forged["candidate_probes"][0]["disposable_seams_proven"].append(
        {"seam_id": "network_denial_kernel", "verdict": "DISPOSABLE_PROVEN", "evidence_class": "LOCAL_REPRODUCIBLE"}
    )
    forged = _resign(forged)
    errors = rc.validate_learning_runtime_choice_receipt(forged, now=FRESH)
    assert any("target-host seam" in error for error in errors)


# --------------------------------------------------------------------------- #
# validator re-verifies the disposable-probe evidence (no rubber-stamp of labels)
# --------------------------------------------------------------------------- #
def test_synthetic_no_op_probe_applied_equals_pre_is_rejected(receipt):
    # 空跑 lifecycle 偽造:applied_digest == pre(apply 未改變 active 世代)→ PASS 交付被 validator 拒。
    forged = copy.deepcopy(receipt)
    block = forged["candidate_probes"][0]
    block["applied_digest"] = block["pre_state_digest"]
    forged = _resign(forged)
    errors = rc.validate_learning_runtime_choice_receipt(forged, require_success=True, now=FRESH)
    assert any("applied_digest must differ" in error for error in errors)


def test_structural_only_probe_claiming_pass_is_rejected(receipt):
    # STRUCTURAL_ONLY 探針(無 runtime bytes)謊稱 PASS → validator 拒(builder FAIL 之處 validator 亦 FAIL)。
    forged = copy.deepcopy(receipt)
    forged["candidate_probes"][0]["evidence_class"] = "STRUCTURAL_ONLY"
    forged = _resign(forged)
    errors = rc.validate_learning_runtime_choice_receipt(forged, require_success=True, now=FRESH)
    assert any("must be LOCAL_REPRODUCIBLE for a PASS" in error for error in errors)


def test_pg_identity_seam_without_bound_42501_evidence_is_rejected(receipt):
    # disposable_pg_identity proven seam 無綁定 42501 evidence_digest → 視為無 42501 背書而拒。
    forged = copy.deepcopy(receipt)
    forged["candidate_probes"][0]["disposable_seams_proven"].append(
        {"seam_id": "disposable_pg_identity", "verdict": "DISPOSABLE_PROVEN", "evidence_class": "LOCAL_REPRODUCIBLE"}
    )
    forged = _resign(forged)
    errors = rc.validate_learning_runtime_choice_receipt(forged, now=FRESH)
    assert any("must bind the 42501 denial evidence digest" in error for error in errors)


def test_pg_identity_seam_with_wrong_42501_evidence_digest_is_rejected(receipt):
    # 綁定一個「不是規範 42501 證據」的 evidence_digest → 仍被拒(digest 必等於規範證據的 canonical digest)。
    forged = copy.deepcopy(receipt)
    forged["candidate_probes"][0]["disposable_seams_proven"].append(
        {
            "seam_id": "disposable_pg_identity", "verdict": "DISPOSABLE_PROVEN",
            "evidence_class": "LOCAL_REPRODUCIBLE", "evidence_digest": "sha256:" + "0" * 64,
        }
    )
    forged = _resign(forged)
    errors = rc.validate_learning_runtime_choice_receipt(forged, now=FRESH)
    assert any("must bind the 42501 denial evidence digest" in error for error in errors)


def test_pass_acceptance_without_now_is_rejected(receipt):
    # require_success 缺 now → 新鮮度無從實證,一張過期 receipt 就能矇混;故直接拒。
    errors = rc.validate_learning_runtime_choice_receipt(receipt, require_success=True, now=None)
    assert any("requires a non-null now" in error for error in errors)


def test_fail_receipt_is_rejected_under_require_success(base_dir):
    # 降級探針(STRUCTURAL_ONLY)→ builder 判 status=FAIL;require_success 必拒(且帶 now)。
    started, completed, observed = OBS, rc._plus_seconds(OBS, 30), rc._plus_seconds(OBS, 40)
    probes = [
        rc.probe_candidate(
            candidate_id, base_dir + f"/failpath_{index}_{candidate_id}",
            started_at=started, completed_at=completed, observed_at=observed,
        )
        for index, candidate_id in enumerate((rc.CANDIDATE_OCI, rc.CANDIDATE_FIXED_PATH))
    ]
    probes[0]["evidence_class"] = "STRUCTURAL_ONLY"  # 降級 → 觸發 builder 的 FAIL 理由
    receipt_a, receipt_b, comparison = rc._hermetic_s14_dependencies(OBS, base_dir + "/failpath_s14")
    fail_receipt = rc.build_learning_runtime_choice_receipt(
        caller="test:failpath", platform=rc.detect_platform(), target_class="disposable_local",
        candidate_probes=probes, runtime_candidate_receipt_a=receipt_a,
        runtime_candidate_receipt_b=receipt_b, runtime_candidate_comparison=comparison,
        effect_seams_ready_receipt_digest=rc._canonical_digest({"x": 1}),
        pg_readonly_identity_receipt_digest=rc._canonical_digest({"y": 1}),
        observation_time=OBS, ttl_seconds=900,
    )
    assert fail_receipt["status"] == "FAIL"
    assert isinstance(fail_receipt["failure_reason"], str) and fail_receipt["failure_reason"]
    errors = rc.validate_learning_runtime_choice_receipt(fail_receipt, require_success=True, now=FRESH)
    assert any("does not prove a passing choice" in error for error in errors)


def test_tampered_field_without_resign_is_rejected(receipt):
    # 竄改任一欄位但不重算 self_digest → self_digest 不符 → 拒(完整性守衛)。
    tampered = copy.deepcopy(receipt)
    tampered["caller"] = "attacker-without-resign"
    errors = rc.validate_learning_runtime_choice_receipt(tampered, now=FRESH)
    assert any("self_digest does not match" in error for error in errors)


# --------------------------------------------------------------------------- #
# per-candidate probe: both probed, exact restoration, distinct verifier, seam split
# --------------------------------------------------------------------------- #
def test_both_candidates_probed_with_exact_restoration_and_distinct_verifier(receipt):
    probes = receipt["candidate_probes"]
    assert {block["candidate_id"] for block in probes} == rc.CANDIDATE_IDS
    for block in probes:
        assert block["pre_state_digest"] == block["post_rollback_digest"]  # exact restoration
        assert block["apply_actor_node"] != block["postcheck_verifier_node"]  # distinct verifier
        assert block["evidence_class"] == "LOCAL_REPRODUCIBLE"
        assert rc.DIGEST_RE.fullmatch(block["lifecycle_result_digest"])
        assert rc.DIGEST_RE.fullmatch(block["postcheck_attestation_digest"])


def test_honest_seam_split_per_candidate(receipt):
    for block in receipt["candidate_probes"]:
        proven = {seam["seam_id"] for seam in block["disposable_seams_proven"]}
        deferred = {seam["seam_id"] for seam in block["target_host_deferred_seams"]}
        # 六個 core disposable seam 到齊;disposable_pg_identity 在無 PG 的結構路徑誠實缺席。
        assert rc.CORE_DISPOSABLE_SEAM_SET <= proven
        assert "disposable_pg_identity" not in proven
        # 六個決定性 target-host seam 全 DEFERRED_TARGET_HOST,且不與 proven 交集。
        assert deferred == rc.TARGET_HOST_DEFERRED_SEAM_SET
        assert proven & deferred == set()
        assert all(seam["verdict"] == "DEFERRED_TARGET_HOST" for seam in block["target_host_deferred_seams"])


def test_representativeness_is_honestly_labeled(receipt):
    by_id = {block["candidate_id"]: block for block in receipt["candidate_probes"]}
    assert by_id["content_addressed_fixed_path"]["representativeness"] == "native_shape"
    assert by_id["exact_image_id_oci"]["representativeness"] == "content_addressed_standin"


def test_oci_candidate_records_lr2_no_socket_caveat(receipt):
    by_id = {block["candidate_id"]: block for block in receipt["candidate_probes"]}
    assert "lr2_no_oci_socket_dbus" in by_id["exact_image_id_oci"]["caveats"]


# --------------------------------------------------------------------------- #
# builder-level fail-closed raises
# --------------------------------------------------------------------------- #
def test_production_target_on_mac_raises(base_dir):
    receipt_a, receipt_b, comparison = rc._hermetic_s14_dependencies(OBS, base_dir + "/prodraise")
    probes = rc._reference_probe_blocks(OBS, base_dir + "/prodraise_probes")
    with pytest.raises(rc.TargetHostRejectedError):
        rc.build_learning_runtime_choice_receipt(
            caller="test", platform=rc.detect_platform(), target_class="production",
            candidate_probes=probes, runtime_candidate_receipt_a=receipt_a,
            runtime_candidate_receipt_b=receipt_b, runtime_candidate_comparison=comparison,
            effect_seams_ready_receipt_digest=rc._canonical_digest({"x": 1}),
            pg_readonly_identity_receipt_digest=rc._canonical_digest({"y": 1}),
            observation_time=OBS, ttl_seconds=900,
        )


def test_single_candidate_raises(base_dir):
    receipt_a, receipt_b, comparison = rc._hermetic_s14_dependencies(OBS, base_dir + "/oneraise")
    probes = rc._reference_probe_blocks(OBS, base_dir + "/oneraise_probes")
    with pytest.raises(rc.RuntimeChoiceProbeError):
        rc.build_learning_runtime_choice_receipt(
            caller="test", platform=rc.detect_platform(), target_class="disposable_local",
            candidate_probes=probes[:1], runtime_candidate_receipt_a=receipt_a,
            runtime_candidate_receipt_b=receipt_b, runtime_candidate_comparison=comparison,
            effect_seams_ready_receipt_digest=rc._canonical_digest({"x": 1}),
            pg_readonly_identity_receipt_digest=rc._canonical_digest({"y": 1}),
            observation_time=OBS, ttl_seconds=900,
        )


def test_deferred_seam_in_probe_block_raises(base_dir):
    block = rc.probe_candidate(
        rc.CANDIDATE_OCI, base_dir + "/deferraise",
        started_at=OBS, completed_at=rc._plus_seconds(OBS, 30), observed_at=rc._plus_seconds(OBS, 40),
    )
    block["disposable_seams_proven"].append(
        {"seam_id": "cgroup_isolation", "verdict": "DISPOSABLE_PROVEN", "evidence_class": "LOCAL_REPRODUCIBLE"}
    )
    with pytest.raises(rc.DeferredSeamClaimError):
        rc._assert_no_deferred_in_proven(block)


def test_mutated_comparison_raises(base_dir):
    receipt_a, receipt_b, comparison = rc._hermetic_s14_dependencies(OBS, base_dir + "/cmpraise")
    mutated = copy.deepcopy(comparison)
    mutated["final_choice"] = "content_addressed_fixed_path"
    mutated["self_digest"] = spike.comparison_digest(mutated)
    probes = rc._reference_probe_blocks(OBS, base_dir + "/cmpraise_probes")
    with pytest.raises(rc.RuntimeChoiceProbeError):
        rc.build_learning_runtime_choice_receipt(
            caller="test", platform=rc.detect_platform(), target_class="disposable_local",
            candidate_probes=probes, runtime_candidate_receipt_a=receipt_a,
            runtime_candidate_receipt_b=receipt_b, runtime_candidate_comparison=mutated,
            effect_seams_ready_receipt_digest=rc._canonical_digest({"x": 1}),
            pg_readonly_identity_receipt_digest=rc._canonical_digest({"y": 1}),
            observation_time=OBS, ttl_seconds=900,
        )


def test_secret_ingress_raises(receipt):
    poisoned = copy.deepcopy(receipt)
    poisoned["unselected_path_removal"]["note"] = "authorization=Bearer plaintexthunter2exampletoken"
    with pytest.raises(rc.SecretLeakageError):
        rc._guard_no_secret({k: v for k, v in poisoned.items() if k != "secret_scan"})


# --------------------------------------------------------------------------- #
# §9 bypass-negatives: all twelve REALLY fail closed (non-vacuous)
# --------------------------------------------------------------------------- #
def test_all_bypass_negatives_fail_closed(base_dir):
    cases = rc.build_bypass_negative_cases(now=OBS, base_dir=base_dir + "/bypass")
    assert len(cases) == 12
    assert {case["bypass_kind"] for case in cases} == rc.BYPASS_KIND_SET
    assert all(case["observed_verdict"] == "REJECTED" for case in cases)
    assert all(case["expected"] == "FAIL_CLOSED" for case in cases)


def test_bypass_runner_is_non_vacuous(base_dir):
    # 一個「不會拒」的 kind 名 → run_bypass_negative 必 raise(不得蓋橡皮圖章)。
    with pytest.raises(rc.RuntimeChoiceProbeError):
        rc.run_bypass_negative("no_such_kind", now=OBS, base_dir=base_dir + "/vac")


def test_vacuous_rejection_reraises(base_dir, monkeypatch):
    # 把某 runner 換成 no-op(不 raise)→ run_bypass_negative 必偵測 vacuous 並 raise。
    monkeypatch.setitem(rc._BYPASS_RUNNERS, "matrix_digest_tamper", lambda now, base: None)
    with pytest.raises(rc.RuntimeChoiceProbeError):
        rc.run_bypass_negative("matrix_digest_tamper", now=OBS, base_dir=base_dir + "/vac2")


# --------------------------------------------------------------------------- #
# self-validating: NOT registered in the central AIML closure validator
# --------------------------------------------------------------------------- #
def test_choice_receipt_is_not_registered_in_central_validator():
    import aiml_gate_receipt_validator as validator
    assert "learning_runtime_choice_receipt_v1" not in validator.SCHEMA_FILES
