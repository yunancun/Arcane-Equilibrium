"""Structural + bypass-negative tests for the S1.5 per-component deploy Adapter.

Hermetic / stdlib-only (no server).  Covers: matrix-derived intent contract for
all six classes; the exact-restoration and applier!=verifier crux invariants;
the twelve §11 bypass-negatives (each REALLY fails closed); the rollup receipt
PASS/FAIL gate + field-set + self_digest; central-validator recognition + the
needs-``now`` freshness gate; and REAL disposable ``temp_dir_artifact`` /
``temp_dir_objects`` apply/rollback/postcheck (pure stdlib, so LOCAL_REPRODUCIBLE
everywhere) with pre==post-rollback digest and a DISTINCT verifier.  The
``disposable_pg`` LOCAL_REPRODUCIBLE proofs (real 42501/28P01) live in the
companion ``_disposable`` test.
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_component_effects as ce  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402

NOW = "2026-07-22T12:00:00+00:00"
LATER = "2026-07-22T12:01:00+00:00"
COMPLETED = "2026-07-22T12:00:30+00:00"
OBSERVED = "2026-07-22T12:00:40+00:00"
APPLY_ACTOR = "engine_scanner_deploy_actor"
VERIFIER = "engine_scanner_independent_verifier"


# --------------------------------------------------------------------------- #
# matrix-derived intent contract
# --------------------------------------------------------------------------- #
def test_all_six_classes_derive_matrix_intent_contract() -> None:
    for effect_class in ce.DEPLOY_COMPONENT_CLASSES:
        row = validator.AIML_COMPONENT_EFFECT_CLASS_MATRIX[effect_class]
        assert ce.required_intent_fields(effect_class) == list(row["required_intent_fields"])
        assert ce.adapter_id_for(effect_class) == row["adapter_id"]
        assert ce.recovery_contract_for(effect_class) == row["recovery_contract"]
        intent = ce.build_component_effect_intent(
            effect_class=effect_class, target_class="disposable_local",
            pre_state_digest=ce.canonical_digest({"pre": effect_class}),
            apply_actor_node=f"{effect_class.lower()}_actor",
            independent_postcheck_node=f"{effect_class.lower()}_postcheck",
            approved_by="operator:s1.5", approved_at=NOW, ttl_seconds=600,
            intent_id=f"component-effect-{effect_class.lower()}",
        )
        # 派生欄位不可被呼叫端提供:adapter/kind/invariants 皆自矩陣。
        assert intent["adapter_id"] == row["adapter_id"]
        assert intent["disposable_target_kind"] == ce.DISPOSABLE_TARGET_KIND_BY_CLASS[effect_class]
        assert intent["class_invariants"] == validator.AIML_COMPONENT_EFFECT_CLASS_INVARIANTS
        assert sorted(intent["intent_fields"]) == sorted(row["required_intent_fields"])
        assert ce.validate_component_effect_intent(intent, now=LATER) == []


def test_disposable_target_kind_mapping_is_exhaustive() -> None:
    assert set(ce.DISPOSABLE_TARGET_KIND_BY_CLASS) == set(ce.DEPLOY_COMPONENT_CLASSES)
    assert ce.DISPOSABLE_TARGET_KINDS == {"disposable_pg", "temp_dir_artifact", "temp_dir_objects"}


# --------------------------------------------------------------------------- #
# fail-closed crux: production / applier==verifier / rollback-not-exact / secret
# --------------------------------------------------------------------------- #
def test_production_target_intent_raises() -> None:
    with pytest.raises(ce.ProductionTargetRejected):
        ce.build_component_effect_intent(
            effect_class="ENGINE_SCANNER", target_class="production",
            pre_state_digest=ce.canonical_digest({"pre": "x"}),
            apply_actor_node=APPLY_ACTOR, independent_postcheck_node="p",
            approved_by="operator", approved_at=NOW, ttl_seconds=600,
            intent_id="component-effect-prod",
        )


@pytest.mark.parametrize("kwargs", [
    {"include_ops_preflight": False},
    {"include_approval": False},
    {"include_rollback_binding": False},
])
def test_missing_preflight_approval_or_rollback_is_refused(kwargs) -> None:
    intent = ce.build_component_effect_intent(
        effect_class="ENGINE_SCANNER", target_class="disposable_local",
        pre_state_digest=ce.canonical_digest({"pre": "x"}),
        apply_actor_node=APPLY_ACTOR, independent_postcheck_node="p",
        approved_by="operator", approved_at=NOW, ttl_seconds=600,
        intent_id="component-effect-missing", **kwargs,
    )
    with pytest.raises(ce.ComponentEffectError):
        ce.refuse_apply_without_contract(intent, now=LATER)


def test_rollback_not_exact_result_raises() -> None:
    intent = _honest_intent()
    with pytest.raises(ce.NonExactRollbackError):
        ce.build_component_effect_result(
            intent=intent, apply_status="APPLIED_ROLLED_BACK_EXACT",
            pre_state_digest=ce.canonical_digest({"pre": "A"}),
            applied_digest=ce.canonical_digest({"applied": "B"}),
            post_rollback_digest=ce.canonical_digest({"post": "C"}),
            apply_actor_node=APPLY_ACTOR, applied_observed=True,
            observation_window_stable=True, runtime_witness_kind="real_filesystem_atomic_swap",
            observed_sqlstate=None, evidence_class="LOCAL_REPRODUCIBLE",
            started_at=NOW, completed_at=COMPLETED,
        )


def test_not_restored_result_is_reported_fail_closed() -> None:
    # 非精確可以誠實回報 NOT_RESTORED_FAILED(fail closed),但絕不冒充乾淨 apply/rollback。
    intent = _honest_intent()
    result = ce.build_component_effect_result(
        intent=intent, apply_status="NOT_RESTORED_FAILED",
        pre_state_digest=ce.canonical_digest({"pre": "A"}),
        applied_digest=ce.canonical_digest({"applied": "B"}),
        post_rollback_digest=ce.canonical_digest({"post": "C"}),
        apply_actor_node=APPLY_ACTOR, applied_observed=True,
        observation_window_stable=True, runtime_witness_kind="real_filesystem_atomic_swap",
        observed_sqlstate=None, evidence_class="LOCAL_REPRODUCIBLE",
        started_at=NOW, completed_at=COMPLETED,
    )
    assert result["rollback_restored_exact"] is False
    assert result["failure_reason"]
    assert ce.validate_component_effect_result(result, now=LATER) == []


def test_applier_equals_verifier_attestation_raises() -> None:
    result = _exact_result(apply_actor_node=APPLY_ACTOR)
    with pytest.raises(ce.ApplierIsSoleVerifierError):
        ce.build_postcheck_attestation(
            result=result, verifier_node=APPLY_ACTOR,
            reobserved_post_rollback_digest=result["post_rollback_digest"],
            restoration_confirmed=True, evidence_class="STRUCTURAL_ONLY", observed_at=OBSERVED,
        )


def test_secret_in_intent_field_is_refused() -> None:
    with pytest.raises(ce.SecretLeakageError):
        ce.build_component_effect_intent(
            effect_class="ENGINE_SCANNER", target_class="disposable_local",
            pre_state_digest=ce.canonical_digest({"pre": "x"}),
            apply_actor_node=APPLY_ACTOR, independent_postcheck_node="p",
            approved_by="operator", approved_at=NOW, ttl_seconds=600,
            intent_id="component-effect-secret",
            intent_fields={f: "ok" for f in ce.required_intent_fields("ENGINE_SCANNER")[:-1]}
            | {"prior_bundle_rollback": "password=plaintexthunter2example"},
        )


# --------------------------------------------------------------------------- #
# REAL disposable temp_dir_artifact apply/rollback/postcheck (LOCAL_REPRODUCIBLE)
# --------------------------------------------------------------------------- #
def test_temp_dir_artifact_real_apply_rollback_exact_restoration(tmp_path) -> None:
    root = tmp_path / "deploy_root"
    prior = ce.artifact_deploy_root_init(
        str(root), prior_bundle_files={"bin/launch": b"generation-0"},
        unit_text=b"[Service]\nExecStart=/opt/aiml/bin/launch\n",
    )
    pre = ce.artifact_state_digest(str(root))
    new_hash, applied = ce.artifact_apply(str(root), new_bundle_files={"bin/launch": b"generation-1"})
    # 真實原子 pointer swap:active 指向新 bundle,狀態已改變。
    assert applied != pre
    assert new_hash != prior
    # committed 新 bundle 檔案為 0o444 immutable(S1.2 WORM 前例)。
    import os
    import stat as stat_mod
    bundle_file = root / "bundles" / new_hash / "bin" / "launch"
    assert stat_mod.S_IMODE(os.stat(bundle_file).st_mode) == 0o444
    post = ce.artifact_rollback(str(root), prior_hash=prior)
    assert post == pre  # EXACT restoration


def test_temp_dir_artifact_interrupted_apply_leaves_prior_active(tmp_path) -> None:
    root = tmp_path / "deploy_root"
    prior = ce.artifact_deploy_root_init(str(root), prior_bundle_files={"bin/x": b"gen0"})
    pre = ce.artifact_state_digest(str(root))
    # 中斷:staged 新 bundle 但從不 swap 指標 → 先前世代仍 active。
    after = ce.artifact_apply_interrupted(str(root), new_bundle_files={"bin/x": b"gen1"})
    assert after == pre
    assert (root / "active_generation").read_text() == prior


def test_temp_dir_artifact_full_lifecycle_receipt_is_local_reproducible(tmp_path) -> None:
    bundle = _run_artifact_lifecycle(tmp_path)
    result = bundle["result"]
    assert result["apply_status"] == "APPLIED_ROLLED_BACK_EXACT"
    assert result["pre_state_digest"] == result["post_rollback_digest"]
    assert result["evidence_class"] == "LOCAL_REPRODUCIBLE"
    assert result["production_apply_performed"] is False
    assert ce.validate_component_effect_result(result, now=LATER) == []
    attestation = bundle["attestation"]
    # 施加者 != 唯一驗證者;驗證者獨立重讀佈署根並重算 digest。
    assert attestation["verifier_node"] != result["apply_actor_node"]
    assert attestation["reobserved_post_rollback_digest"] == result["post_rollback_digest"]
    assert attestation["restoration_confirmed"] is True
    assert attestation["remote_platform_attested"] is False
    assert ce.validate_postcheck_attestation(attestation, result=result, now=LATER) == []


# --------------------------------------------------------------------------- #
# REAL disposable temp_dir_objects delete + restore (retention)
# --------------------------------------------------------------------------- #
def test_temp_dir_objects_real_delete_restore_exact_restoration(tmp_path) -> None:
    root = tmp_path / "objects_root"
    pre = ce.objects_root_init(str(root), objects={"a.bin": b"AAAA", "sub/b.bin": b"BBBB"})
    assert (root / "objects" / "a.bin").is_file()
    ce.objects_apply(str(root), tombstone_set=["a.bin"])
    assert not (root / "objects" / "a.bin").exists()  # 真實 os.unlink
    post = ce.objects_rollback(str(root), tombstone_set=["a.bin"])
    assert post == pre  # EXACT restoration from the throwaway copy
    assert (root / "objects" / "a.bin").read_bytes() == b"AAAA"


def test_objects_deleter_cannot_exceed_tombstone_set(tmp_path) -> None:
    root = tmp_path / "objects_root"
    ce.objects_root_init(str(root), objects={"a.bin": b"AAAA"})
    # 超出宣告集(路徑穿越)一律 fail-closed。
    with pytest.raises(ce.ComponentEffectError):
        ce.objects_apply(str(root), tombstone_set=["../restore_capacity/a.bin"])
    with pytest.raises(ce.ComponentEffectError):
        ce.objects_apply(str(root), tombstone_set=["missing.bin"])


# --------------------------------------------------------------------------- #
# twelve §11 bypass-negatives (each REALLY fails closed)
# --------------------------------------------------------------------------- #
def test_twelve_bypass_negatives_all_fail_closed() -> None:
    cases = ce.build_bypass_negative_cases(now=NOW)
    assert len(cases) == 12
    assert {case["bypass_kind"] for case in cases} == set(ce.BYPASS_KINDS)
    assert "apply_was_a_noop" in ce.BYPASS_KINDS
    assert all(case["observed_verdict"] == "REJECTED" for case in cases)
    assert all(case["expected"] == "FAIL_CLOSED" for case in cases)


def test_run_bypass_negative_is_not_vacuous_for_a_bad_kind() -> None:
    with pytest.raises(ce.ComponentEffectError):
        ce.run_bypass_negative("not_a_real_bypass_kind", now=NOW)


def test_run_bypass_negative_reraises_on_non_raising_runner(monkeypatch) -> None:
    # 反空轉自衛:runner 若「返回而不 raise」(對某個已知種類),run_bypass_negative 必以
    # vacuous rejection 再拋(不僅是 unknown-kind 分支)。
    monkeypatch.setitem(
        ce._BYPASS_RUNNERS, "source_only_route_of_effectful_class", lambda now: None
    )
    with pytest.raises(ce.ComponentEffectError, match="vacuous"):
        ce.run_bypass_negative("source_only_route_of_effectful_class", now=NOW)


@pytest.mark.parametrize("kind, needle", [
    ("source_only_route_of_effectful_class", "source-only"),
    ("generic_deploy_apply_enabled_without_per_class_contract", "disabled"),
    ("cross_class_adapter_substitution", "admitted adapter"),
    ("classifier_or_matrix_digest_tamper", "matrix digest"),
])
def test_specific_bypass_rejection_reason(kind, needle) -> None:
    # 對原本只被籠統 REJECTED 覆蓋的四個種類,斷言確切的拒絕理由(非泛泛 REJECTED)。
    case = ce.run_bypass_negative(kind, now=NOW)
    assert case["observed_verdict"] == "REJECTED"
    assert needle in case["reason"]


def test_apply_was_a_noop_bypass_fails_closed() -> None:
    # no-op apply(applied==pre==post)雖 pre==post 但未改變狀態 → 必 fail-closed。
    case = ce.run_bypass_negative("apply_was_a_noop", now=NOW)
    assert case["observed_verdict"] == "REJECTED"
    assert "no-op" in case["reason"] or "change state" in case["reason"]


# --------------------------------------------------------------------------- #
# rollup receipt PASS/FAIL gate + central-validator recognition
# --------------------------------------------------------------------------- #
def test_reference_rollup_receipt_passes_and_is_recognized() -> None:
    receipt = ce._reference_receipt(NOW)
    assert receipt["status"] == "PASS"
    assert receipt["sprint_gate_scope"] == "S1.5_CONTRIBUTION"
    assert receipt["boundary"]["production_apply_performed"] is False
    assert receipt["observation_seam"]["remote_platform_attested"] is False
    assert set(receipt) == ce.RECEIPT_FIELDS
    # module validator + central validator both recognize it.
    assert ce.validate_effect_seams_ready_receipt(receipt, now=LATER) == []
    assert validator.validate_aiml_artifact(receipt, now=LATER) == []


def test_rollup_requires_all_six_classes() -> None:
    receipt = ce._reference_receipt(NOW)
    forged = deepcopy(receipt)
    # 複製第一個項目蓋掉最後一個(維持 6 項滿足 schema minItems),使某 deploy 類缺席 +
    # 出現重複 → Python 層的「missing class」+「duplicate」檢查觸發。
    forged["admitted_classes"][-1] = deepcopy(forged["admitted_classes"][0])
    forged["self_digest"] = ce.receipt_digest(forged)
    errors = ce.validate_effect_seams_ready_receipt(forged, now=LATER)
    assert any("missing" in error and "class" in error for error in errors)
    assert any("duplicate" in error for error in errors)


def test_rollup_rejects_applier_equals_verifier_entry() -> None:
    receipt = ce._reference_receipt(NOW)
    forged = deepcopy(receipt)
    forged["admitted_classes"][0]["postcheck_verifier_node"] = (
        forged["admitted_classes"][0]["apply_actor_node"]
    )
    forged["self_digest"] = ce.receipt_digest(forged)
    errors = ce.validate_effect_seams_ready_receipt(forged, now=LATER)
    assert any("applier equals its verifier" in error for error in errors)


def test_central_validator_needs_now_for_freshness() -> None:
    receipt = ce._reference_receipt(NOW)
    errors = validator.validate_aiml_artifact(receipt)  # no now
    assert any("now" in error for error in errors)


def test_central_validator_recognizes_all_four_schemas() -> None:
    for schema_version in (
        "component_effect_intent_v1", "component_effect_result_v1",
        "component_effect_postcheck_attestation_v1", "effect_seams_ready_receipt_v1",
    ):
        assert schema_version in validator.SCHEMA_FILES
        assert (ce.SCHEMA_DIR / validator.SCHEMA_FILES[schema_version]).is_file()


# --------------------------------------------------------------------------- #
# registry wiring: six adapters registered; generic deploy stays disabled
# --------------------------------------------------------------------------- #
def test_registry_has_six_component_adapters_and_generic_deploy_stays_disabled() -> None:
    registry = json.loads((ROOT / ".codex/agent_registry_v1.json").read_text(encoding="utf-8"))
    adapters = registry["effect_adapters"]
    for effect_class in ce.DEPLOY_COMPONENT_CLASSES:
        adapter_id = ce.adapter_id_for(effect_class)
        assert adapter_id in adapters, adapter_id
        entry = adapters[adapter_id]
        assert entry["status"] == "declared_disposable_apply_rollback_postcheck_implemented"
        assert entry["authority"] and entry["invariant"]
    # 通用 deploy_adapter_v1 仍 apply-disabled;broker_probe 仍 fail-closed;S1.2 sink 不動。
    assert adapters["deploy_adapter_v1"]["status"] == (
        "declared_apply_disabled_until_recovery_controls_bound"
    )
    assert adapters["broker_probe_adapter_v1"]["status"] == "declared_fail_closed_unsupported"
    assert adapters["terminal_receipt_sink_v1"]["status"] == (
        "declared_disposable_worm_emulation_implemented"
    )


# --------------------------------------------------------------------------- #
# no-op apply must fail closed; interrupted apply with applied==pre stays legit
# --------------------------------------------------------------------------- #
def test_noop_apply_result_is_rejected() -> None:
    intent = _honest_intent()
    pre = ce.canonical_digest({"noop": "pre"})
    for applied in (pre, None):  # applied==pre 或缺失都算 no-op
        with pytest.raises(ce.NonExactRollbackError):
            ce.build_component_effect_result(
                intent=intent, apply_status="APPLIED_ROLLED_BACK_EXACT",
                pre_state_digest=pre, applied_digest=applied, post_rollback_digest=pre,
                apply_actor_node=APPLY_ACTOR, applied_observed=True,
                observation_window_stable=True, runtime_witness_kind="structural_contract",
                observed_sqlstate=None, evidence_class="STRUCTURAL_ONLY",
                started_at=NOW, completed_at=COMPLETED,
            )


def test_noop_apply_result_is_rejected_by_validator() -> None:
    # 繞過 builder 直接構造 applied==pre 的 result,確認消費端 validator 亦拒。
    result = _exact_result(apply_actor_node=APPLY_ACTOR)
    forged = deepcopy(result)
    forged["applied_digest"] = forged["pre_state_digest"]
    forged["result_digest"] = ce.result_digest(forged)
    errors = ce.validate_component_effect_result(forged, now=LATER)
    assert any("no-op apply" in error for error in errors)


def test_interrupted_apply_with_applied_equal_pre_is_legit() -> None:
    # ROLLED_BACK_INTERRUPTED 的 applied==pre 合法(指標從未 swap,先前世代仍 active)。
    intent = _honest_intent()
    pre = ce.canonical_digest({"interrupted": "pre"})
    result = ce.build_component_effect_result(
        intent=intent, apply_status="ROLLED_BACK_INTERRUPTED",
        pre_state_digest=pre, applied_digest=pre, post_rollback_digest=pre,
        apply_actor_node=APPLY_ACTOR, applied_observed=False,
        observation_window_stable=True, runtime_witness_kind="real_filesystem_atomic_swap",
        observed_sqlstate=None, evidence_class="LOCAL_REPRODUCIBLE",
        started_at=NOW, completed_at=COMPLETED,
    )
    assert result["rollback_restored_exact"] is True
    assert ce.validate_component_effect_result(result, now=LATER) == []


# --------------------------------------------------------------------------- #
# filesystem confinement: bundle keys, restore rels, pointer hex
# --------------------------------------------------------------------------- #
def test_stage_bundle_rejects_absolute_and_escaping_keys(tmp_path) -> None:
    abs_key = str(tmp_path / "escaped_abs.bin")
    with pytest.raises(ce.ComponentEffectError):
        ce.artifact_deploy_root_init(str(tmp_path / "root_a"), prior_bundle_files={abs_key: b"x"})
    assert not (tmp_path / "escaped_abs.bin").exists()  # 拒絕發生在任何寫入之前
    with pytest.raises(ce.ComponentEffectError):
        ce.artifact_deploy_root_init(str(tmp_path / "root_b"), prior_bundle_files={"../../evil.bin": b"x"})
    # 公開 artifact_apply 路徑同樣受限(不只 init)。
    good = tmp_path / "good_root"
    ce.artifact_deploy_root_init(str(good), prior_bundle_files={"bin/x": b"gen0"})
    with pytest.raises(ce.ComponentEffectError):
        ce.artifact_apply(str(good), new_bundle_files={"../../../evil.bin": b"x"})


def test_objects_rollback_rejects_escaping_restore_rel(tmp_path) -> None:
    root = tmp_path / "objects_root"
    ce.objects_root_init(str(root), objects={"a.bin": b"AAAA"})
    with pytest.raises(ce.ComponentEffectError):
        ce.objects_rollback(str(root), tombstone_set=["../../evil.bin"])
    abs_rel = str(tmp_path / "evil_abs.bin")
    with pytest.raises(ce.ComponentEffectError):
        ce.objects_rollback(str(root), tombstone_set=[abs_rel])
    assert not (tmp_path / "evil_abs.bin").exists()


def test_artifact_rollback_rejects_non_hex_pointer(tmp_path) -> None:
    root = tmp_path / "deploy_root"
    ce.artifact_deploy_root_init(str(root), prior_bundle_files={"bin/x": b"gen0"})
    for bad in ("../evil", "not-a-sha", ""):
        with pytest.raises(ce.ComponentEffectError):
            ce.artifact_rollback(str(root), prior_hash=bad)


# --------------------------------------------------------------------------- #
# independent postcheck is load-bearing (reobserved-digest crux)
# --------------------------------------------------------------------------- #
def test_attestation_fabricated_reobserved_digest_is_rejected() -> None:
    result = _exact_result(apply_actor_node=APPLY_ACTOR)
    with pytest.raises(ce.ComponentEffectError):
        ce.build_postcheck_attestation(
            result=result, verifier_node=VERIFIER,
            reobserved_post_rollback_digest=ce.canonical_digest({"fabricated": "x"}),
            restoration_confirmed=True,  # 宣稱 confirmed 但重算 digest 不符 → 拒
            evidence_class="STRUCTURAL_ONLY", observed_at=OBSERVED,
        )


def test_rollup_rejects_unconfirmed_restoration_attestation() -> None:
    result = _exact_result(apply_actor_node=APPLY_ACTOR)
    # confirmed=False 且 reobserved!=post 自洽 → attestation 可建,但 rollup 拒收未確認還原者。
    attestation = ce.build_postcheck_attestation(
        result=result, verifier_node=VERIFIER,
        reobserved_post_rollback_digest=ce.canonical_digest({"mismatch": "x"}),
        restoration_confirmed=False, evidence_class="STRUCTURAL_ONLY", observed_at=OBSERVED,
    )
    with pytest.raises(ce.ComponentEffectError):
        ce.build_admitted_class_entry(result=result, attestation=attestation)


def test_rollup_entry_rejects_forged_noop_exact_result() -> None:
    # 手工偽造 no-op EXACT result(applied==pre==post)並重新綁定一份自洽 attestation,使唯一
    # 拒收理由即 rollup entry builder 新增的「apply 必須真正改變狀態」防禦縱深檢查:誠實管線已在
    # result builder 擋掉,此為 S2.4 消費之 rollup 路徑的平價再核(對齊 pre==post/reobserved re-check)。
    forged = deepcopy(_exact_result(apply_actor_node=APPLY_ACTOR))
    forged["applied_digest"] = forged["pre_state_digest"]  # applied==pre → no-op apply
    forged["result_digest"] = ce.result_digest(forged)
    # post 未變 → reobserved==post 仍成立,attestation 可自洽重綁至偽造 result(排除綁定失敗干擾)。
    attestation = ce.build_postcheck_attestation(
        result=forged, verifier_node=VERIFIER,
        reobserved_post_rollback_digest=forged["post_rollback_digest"],
        restoration_confirmed=True, evidence_class="STRUCTURAL_ONLY", observed_at=OBSERVED,
    )
    with pytest.raises(ce.NonExactRollbackError) as excinfo:
        ce.build_admitted_class_entry(result=forged, attestation=attestation)
    assert "applied_digest must be present and differ" in str(excinfo.value)


def test_rollup_validator_rejects_tampered_reobserved_entry() -> None:
    receipt = ce._reference_receipt(NOW)
    forged = deepcopy(receipt)
    forged["admitted_classes"][0]["reobserved_post_rollback_digest"] = ce.canonical_digest({"tamper": "x"})
    forged["self_digest"] = ce.receipt_digest(forged)
    errors = ce.validate_effect_seams_ready_receipt(forged, now=LATER)
    assert any("re-derive the exact post digest" in error for error in errors)


# --------------------------------------------------------------------------- #
# S1.3 conformance is EXERCISED: non-least-privilege PG / credential intent rejected
# --------------------------------------------------------------------------- #
def test_pg_role_acl_intent_rejects_non_least_privilege_delta() -> None:
    fields = ce._disposable_intent_fields("PG_ROLE_ACL_MIGRATION")
    fields["role_acl_delta"]["pg_role_topology"][0]["is_superuser"] = True  # 過度授權
    intent = ce.build_component_effect_intent(
        effect_class="PG_ROLE_ACL_MIGRATION", target_class="disposable_local",
        pre_state_digest=ce.canonical_digest({"pre": "x"}),
        apply_actor_node="pg_role_acl_migration_actor", independent_postcheck_node="p",
        approved_by="operator", approved_at=NOW, ttl_seconds=600,
        intent_id="component-effect-pg-badrole", intent_fields=fields,
    )
    errors = ce.validate_component_effect_intent(intent, now=LATER)
    assert any("superuser_role" in error for error in errors)


def test_credential_intent_rejects_unsafe_rotation_order() -> None:
    fields = ce._disposable_intent_fields("CREDENTIAL_ROTATION")
    fields["rotation_order"] = ["revoke_old_secret", "stage_new_secret", "alter_role_credential"]
    intent = ce.build_component_effect_intent(
        effect_class="CREDENTIAL_ROTATION", target_class="disposable_local",
        pre_state_digest=ce.canonical_digest({"pre": "x"}),
        apply_actor_node="credential_rotation_actor", independent_postcheck_node="p",
        approved_by="operator", approved_at=NOW, ttl_seconds=600,
        intent_id="component-effect-cred-badorder", intent_fields=fields,
    )
    errors = ce.validate_component_effect_intent(intent, now=LATER)
    assert any("unsafe_rotation_order" in error for error in errors)


def test_credential_intent_rejects_mis_derived_fingerprint() -> None:
    fields = ce._disposable_intent_fields("CREDENTIAL_ROTATION")
    fields["old_fingerprint"] = ce.canonical_digest({"wrong": "fp"})  # 非 S1.3 槽指紋
    intent = ce.build_component_effect_intent(
        effect_class="CREDENTIAL_ROTATION", target_class="disposable_local",
        pre_state_digest=ce.canonical_digest({"pre": "x"}),
        apply_actor_node="credential_rotation_actor", independent_postcheck_node="p",
        approved_by="operator", approved_at=NOW, ttl_seconds=600,
        intent_id="component-effect-cred-badfp", intent_fields=fields,
    )
    errors = ce.validate_component_effect_intent(intent, now=LATER)
    assert any("old_fingerprint is not the S1.3 slot fingerprint" in error for error in errors)


# --------------------------------------------------------------------------- #
# validator forgery-negatives (behavior already correct; locked in)
# --------------------------------------------------------------------------- #
def test_attestation_forged_remote_platform_attested_is_rejected() -> None:
    result = _exact_result(apply_actor_node=APPLY_ACTOR)
    attestation = ce.build_postcheck_attestation(
        result=result, verifier_node=VERIFIER,
        reobserved_post_rollback_digest=result["post_rollback_digest"],
        restoration_confirmed=True, evidence_class="STRUCTURAL_ONLY", observed_at=OBSERVED,
    )
    forged = deepcopy(attestation)
    forged["remote_platform_attested"] = True
    forged["attestation_digest"] = ce.attestation_digest(forged)
    errors = ce.validate_postcheck_attestation(forged, result=result, now=LATER)
    assert any("remote_platform_attested" in error for error in errors)


def test_receipt_forged_observation_seam_remote_attested_is_rejected() -> None:
    receipt = ce._reference_receipt(NOW)
    forged = deepcopy(receipt)
    forged["observation_seam"]["remote_platform_attested"] = True
    forged["self_digest"] = ce.receipt_digest(forged)
    errors = ce.validate_effect_seams_ready_receipt(forged, now=LATER)
    assert any("remote_platform_attested" in error for error in errors)


def test_stale_self_digest_is_caught_for_rollup_and_children() -> None:
    # rollup:改欄位但不重算 self_digest → 捕獲。
    receipt = ce._reference_receipt(NOW)
    tampered_receipt = deepcopy(receipt)
    tampered_receipt["caller"] = "tampered_caller"
    assert any(
        "self_digest does not match" in error
        for error in ce.validate_effect_seams_ready_receipt(tampered_receipt, now=LATER)
    )
    # intent / result / attestation:改欄位但不重算各自 digest。
    intent = _honest_intent()
    tampered_intent = deepcopy(intent)
    tampered_intent["apply_actor_node"] = "tampered_actor"
    assert any(
        "intent_digest does not match" in error
        for error in ce.validate_component_effect_intent(tampered_intent, now=LATER)
    )
    result = _exact_result(apply_actor_node=APPLY_ACTOR)
    tampered_result = deepcopy(result)
    tampered_result["apply_actor_node"] = "tampered_actor"
    assert any(
        "result_digest does not match" in error
        for error in ce.validate_component_effect_result(tampered_result, now=LATER)
    )
    attestation = ce.build_postcheck_attestation(
        result=result, verifier_node=VERIFIER,
        reobserved_post_rollback_digest=result["post_rollback_digest"],
        restoration_confirmed=True, evidence_class="LOCAL_REPRODUCIBLE", observed_at=OBSERVED,
    )
    tampered_att = deepcopy(attestation)
    tampered_att["verifier_node"] = "tampered_verifier"
    assert any(
        "attestation_digest does not match" in error
        for error in ce.validate_postcheck_attestation(tampered_att, now=LATER)
    )


def test_rollup_validator_rejects_cross_class_adapter_or_kind_substitution() -> None:
    receipt = ce._reference_receipt(NOW)
    forged_adapter = deepcopy(receipt)
    forged_adapter["admitted_classes"][0]["adapter_id"] = "retention_apply_adapter_v1"  # 錯類 adapter
    forged_adapter["self_digest"] = ce.receipt_digest(forged_adapter)
    assert any(
        "adapter_id is not the matrix adapter" in error
        for error in ce.validate_effect_seams_ready_receipt(forged_adapter, now=LATER)
    )
    forged_kind = deepcopy(receipt)
    forged_kind["admitted_classes"][0]["disposable_target_kind"] = "disposable_pg"  # 錯 target kind
    forged_kind["self_digest"] = ce.receipt_digest(forged_kind)
    assert any(
        "disposable_target_kind is wrong" in error
        for error in ce.validate_effect_seams_ready_receipt(forged_kind, now=LATER)
    )


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _honest_intent() -> dict:
    return ce.build_component_effect_intent(
        effect_class="ENGINE_SCANNER", target_class="disposable_local",
        pre_state_digest=ce.canonical_digest({"pre": "seed"}),
        apply_actor_node=APPLY_ACTOR, independent_postcheck_node="engine_scanner_ops_postcheck",
        approved_by="operator:s1.5", approved_at=NOW, ttl_seconds=600,
        intent_id="component-effect-honest",
    )


def _exact_result(*, apply_actor_node: str) -> dict:
    intent = _honest_intent()
    pre = ce.canonical_digest({"exact": "pre"})
    return ce.build_component_effect_result(
        intent=intent, apply_status="APPLIED_ROLLED_BACK_EXACT",
        pre_state_digest=pre, applied_digest=ce.canonical_digest({"exact": "applied"}),
        post_rollback_digest=pre, apply_actor_node=apply_actor_node, applied_observed=True,
        observation_window_stable=True, runtime_witness_kind="real_filesystem_atomic_swap",
        observed_sqlstate=None, evidence_class="LOCAL_REPRODUCIBLE",
        started_at=NOW, completed_at=COMPLETED,
    )


def _run_artifact_lifecycle(tmp_path) -> dict:
    root = tmp_path / "deploy_root"
    prior = ce.artifact_deploy_root_init(
        str(root), prior_bundle_files={"bin/launch": b"generation-0"},
        unit_text=b"[Service]\nExecStart=/opt/aiml/bin/launch\n",
    )
    pre = ce.artifact_state_digest(str(root))
    intent = ce.build_component_effect_intent(
        effect_class="ENGINE_SCANNER", target_class="disposable_local",
        pre_state_digest=pre, apply_actor_node=APPLY_ACTOR,
        independent_postcheck_node="engine_scanner_ops_postcheck",
        approved_by="operator:s1.5", approved_at=NOW, ttl_seconds=600,
        intent_id="component-effect-artifact-lifecycle",
    )
    assert ce.validate_component_effect_intent(intent, now=LATER) == []
    ce.refuse_apply_without_contract(intent, now=LATER)  # admits the apply
    _new_hash, applied = ce.artifact_apply(str(root), new_bundle_files={"bin/launch": b"generation-1"})
    post = ce.artifact_rollback(str(root), prior_hash=prior)
    result = ce.build_component_effect_result(
        intent=intent, apply_status="APPLIED_ROLLED_BACK_EXACT", pre_state_digest=pre,
        applied_digest=applied, post_rollback_digest=post, apply_actor_node=APPLY_ACTOR,
        applied_observed=True, observation_window_stable=True,
        runtime_witness_kind="real_filesystem_atomic_swap", observed_sqlstate=None,
        evidence_class="LOCAL_REPRODUCIBLE", started_at=NOW, completed_at=COMPLETED,
    )
    reobserved = ce.artifact_state_digest(str(root))  # 獨立驗證者重讀
    attestation = ce.build_postcheck_attestation(
        result=result, verifier_node=VERIFIER,
        reobserved_post_rollback_digest=reobserved,
        restoration_confirmed=(reobserved == post), evidence_class="LOCAL_REPRODUCIBLE",
        observed_at=OBSERVED,
    )
    return {"pre": pre, "post": post, "result": result, "attestation": attestation}
