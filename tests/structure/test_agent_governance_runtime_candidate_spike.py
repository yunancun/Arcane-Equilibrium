"""Hermetic structural tests for the LR0C runtime-candidate spike (S1.4).

No subprocess is launched and no fixture tree is materialized here; these exercise
the builder/validator/schema roundtrip, the fail-closed rejections (target_host at
the gate, a runtime seam claimed OFFLINE_PROVEN, prohibition consts forced false,
ttl bound, tamper, secret injection) and the const-null ``final_choice`` guarantee
of the comparison.  The real offline evidence (content-addressing hashed twice, the
``python3 -I`` subprocess) is proven separately in the ``_disposable`` module.
"""

from __future__ import annotations

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

import agent_governance_runtime_candidate_spike as spike  # noqa: E402
from agent_governance_schema import schema_subset_errors  # noqa: E402


RECEIPT_SCHEMA_PATH = (
    ROOT / "program_code/ml_training/schemas/aiml_gate_receipts"
    / "runtime_candidate_receipt_v1.schema.json"
)
COMPARISON_SCHEMA_PATH = (
    ROOT / "program_code/ml_training/schemas/aiml_gate_receipts"
    / "runtime_candidate_comparison_v1.schema.json"
)
OBS = datetime(2026, 7, 22, 12, 0, 0, tzinfo=timezone.utc).isoformat()
NOW = (datetime(2026, 7, 22, 12, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=5)).isoformat()


def _digest(seed: str) -> str:
    return spike._sha256_bytes(seed.encode("utf-8"))


def _platform(**overrides) -> dict:
    plat = {
        "os": "darwin",
        "arch": "arm64",
        "python_version": "3.10.1",
        "container_runtime": "docker",
        "container_runtime_available": True,
        "buildx_available": False,
    }
    plat.update(overrides)
    return plat


def _isolation(**overrides) -> dict:
    # 結構測試用的合成 isolation(不跑子進程);真實 -I 子進程在 _disposable 模組。
    iso = {
        "isolated_flag": 1,
        "no_user_site_flag": 1,
        "injected_absent_under_isolated": True,
        "injected_present_without_isolated": True,
        "python_isolated_mode": True,
        "ignores_ambient_env": True,
        "system_python_fallback_possible": False,
        "launch_interpreter": "absolute_pinned",
        "evidence_class": "LOCAL_REPRODUCIBLE",
    }
    iso.update(overrides)
    return iso


def _dependency_closure(**overrides) -> dict:
    dep = {
        "lock_tool": "stdlib_sha256_closure",
        "lock_input_ref": "runtime_candidate_fixture_v1",
        "closure_hash": _digest("fixture-closure"),
        "hashed_input_count": 5,
    }
    dep.update(overrides)
    return dep


def _sealed() -> dict:
    return spike.build_sealed_input({
        "manifest": b'{"runtime":"fixture"}',
        "lock": b"# pinned lock placeholder",
        "closure": b"content-addressed-bundle",
    })


def _native() -> list:
    return [{"name": "placeholder_lightgbm", "origin": "fixture_vendored_placeholder", "sha256": _digest("lib-a")}]


def _build_b(**overrides):
    params = dict(
        caller="E1:S1.4",
        platform=_platform(),
        candidate_id=spike.CANDIDATE_FIXED_PATH,
        target_class="disposable_offline",
        dependency_closure=_dependency_closure(),
        native_library_inventory=_native(),
        isolation_mode=_isolation(),
        sealed_input=_sealed(),
        observation_time=OBS,
        ttl_seconds=3600,
    )
    params.update(overrides)
    return spike.build_runtime_candidate_receipt(**params)


def _build_a(**overrides):
    params = dict(
        caller="E1:S1.4",
        platform=_platform(),
        candidate_id=spike.CANDIDATE_OCI,
        target_class="disposable_offline",
        dependency_closure=_dependency_closure(closure_hash=_digest("oci-sealed"), hashed_input_count=4),
        native_library_inventory=_native(),
        isolation_mode=_isolation(),
        sealed_input=spike.oci_sealed_input(_digest("base"), spike.OCI_DOCKERFILE_SPEC, b"# lock"),
        observation_time=OBS,
        ttl_seconds=3600,
    )
    params.update(overrides)
    return spike.build_runtime_candidate_receipt(**params)


def _receipt_schema() -> dict:
    return json.loads(RECEIPT_SCHEMA_PATH.read_text(encoding="utf-8"))


def _comparison_schema() -> dict:
    return json.loads(COMPARISON_SCHEMA_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# builder -> validator -> schema PASS roundtrip (both candidates)
# --------------------------------------------------------------------------- #
def test_candidate_b_pass_roundtrips_validator_and_schema():
    receipt = _build_b()
    assert receipt["status"] == "PASS"
    assert receipt["candidate"]["id"] == "content_addressed_fixed_path"
    assert receipt["target_class"] == "disposable_offline"
    assert receipt["evidence_class"] == "LOCAL_REPRODUCIBLE"
    assert receipt["oci_build"] is None
    assert receipt["failure_reason"] is None
    assert set(receipt) == spike.RECEIPT_FIELDS
    assert spike.validate_runtime_candidate_receipt(receipt, require_success=True, now=NOW) == []
    schema = _receipt_schema()
    assert schema_subset_errors(receipt, schema, schema) == []


def test_candidate_a_pass_roundtrips_validator_and_schema():
    receipt = _build_a()
    assert receipt["status"] == "PASS"
    assert receipt["candidate"]["id"] == "exact_image_id_oci"
    assert receipt["evidence_class"] == "LOCAL_REPRODUCIBLE"
    # floor-only:不 pull/不 build/不觸網。
    assert receipt["oci_build"]["built"] is False
    assert receipt["oci_build"]["image_id"] is None
    assert receipt["oci_build"]["buildx_multiarch"] is False
    assert receipt["oci_build"]["target_arch_match_verified"] is False
    assert spike.validate_runtime_candidate_receipt(receipt, require_success=True, now=NOW) == []
    schema = _receipt_schema()
    assert schema_subset_errors(receipt, schema, schema) == []


def test_pass_receipt_binds_source_and_schema_and_self_digests():
    receipt = _build_b()
    assert receipt["source_sha256"] == spike.source_sha256()
    assert receipt["schema_sha256"] == spike.receipt_schema_sha256()
    assert receipt["self_digest"] == spike.receipt_digest(receipt)


def test_offline_seam_split_matches_design_for_each_candidate():
    a = {seam["seam_id"]: seam["verdict"] for seam in _build_a()["seams"]}
    b = {seam["seam_id"]: seam["verdict"] for seam in _build_b()["seams"]}
    # B 的關鍵優勢:no-system-python-fallback 與 non-relocatable 皆 OFFLINE_PROVEN。
    assert b["no_system_python_fallback"] == "OFFLINE_PROVEN"
    assert b["non_relocatable_no_mutable_alias"] == "OFFLINE_PROVEN"
    # A 這兩者只能 STRUCTURAL_DESIGN(image ENTRYPOINT / image-id 不變性)。
    assert a["no_system_python_fallback"] == "STRUCTURAL_DESIGN"
    assert a["non_relocatable_no_mutable_alias"] == "STRUCTURAL_DESIGN"
    # exact_image_id_pin 為 OCI 專屬,B 不含。
    assert "exact_image_id_pin" in a
    assert "exact_image_id_pin" not in b
    # 共通離線機制兩候選皆 OFFLINE_PROVEN。
    for seam_id in ("content_addressing_determinism", "sealed_build_input_digest",
                    "python_isolated_mode", "native_lib_inventory_origin"):
        assert a[seam_id] == "OFFLINE_PROVEN"
        assert b[seam_id] == "OFFLINE_PROVEN"


def test_ml_closure_and_output_bit_identity_are_structural_not_offline():
    for receipt in (_build_a(), _build_b()):
        verdicts = {seam["seam_id"]: seam["verdict"] for seam in receipt["seams"]}
        assert verdicts["real_ml_dep_closure_resolution"] == "STRUCTURAL_DESIGN"
        assert verdicts["reproducible_output_bit_identity"] == "STRUCTURAL_DESIGN"
        assert receipt["dependency_closure"]["real_ml_closure_resolved"] is False
        assert receipt["sealed_input"]["reproducible_output_verified"] is False


# --------------------------------------------------------------------------- #
# ttl / time ordering / tamper
# --------------------------------------------------------------------------- #
def test_ttl_and_time_ordering_are_bound():
    receipt = _build_b(ttl_seconds=1800)
    observed = datetime.fromisoformat(receipt["observation_time"])
    expires = datetime.fromisoformat(receipt["expires_at"])
    assert (expires - observed) == timedelta(seconds=1800)
    stale_now = (expires + timedelta(seconds=1)).isoformat()
    assert any("fresh" in e for e in spike.validate_runtime_candidate_receipt(receipt, now=stale_now))


def test_internal_temporal_consistency_enforced_without_now():
    receipt = _build_b(ttl_seconds=1800)
    tampered = deepcopy(receipt)
    observed = datetime.fromisoformat(tampered["observation_time"])
    tampered["expires_at"] = (observed + timedelta(seconds=1801)).isoformat()
    tampered["self_digest"] = spike.receipt_digest(tampered)
    errors = spike.validate_runtime_candidate_receipt(tampered, now=None)
    assert any("expires_at does not equal" in e for e in errors)


def test_tampered_field_breaks_self_digest():
    tampered = deepcopy(_build_b())
    tampered["caller"] = "someone-else"
    assert any("self_digest" in e for e in spike.validate_runtime_candidate_receipt(tampered))


def test_validator_rejects_mismatched_source_sha256():
    tampered = deepcopy(_build_b())
    tampered["source_sha256"] = "sha256:" + "0" * 64
    tampered["self_digest"] = spike.receipt_digest(tampered)
    assert any("source_sha256 does not bind" in e for e in spike.validate_runtime_candidate_receipt(tampered))


def test_validator_rejects_mismatched_schema_sha256():
    tampered = deepcopy(_build_b())
    tampered["schema_sha256"] = "sha256:" + "0" * 64
    tampered["self_digest"] = spike.receipt_digest(tampered)
    assert any("schema_sha256 does not bind" in e for e in spike.validate_runtime_candidate_receipt(tampered))


@pytest.mark.parametrize("ttl", [0, -1, 3601, 7200, True, 1.5])
def test_ttl_outside_bound_refuses_to_build(ttl):
    with pytest.raises(ValueError):
        _build_b(ttl_seconds=ttl)


# --------------------------------------------------------------------------- #
# fail-closed: target_host, runtime seam offline, prohibition consts
# --------------------------------------------------------------------------- #
def test_target_host_raises_fail_closed():
    # target_host 屬 S1.6,離線無從評估 → raise(不發 FAIL receipt)。
    with pytest.raises(spike.TargetHostRejectedError):
        _build_b(target_class="target_host")


def test_forged_target_host_pass_fails_schema_and_validator():
    forged = deepcopy(_build_b())
    forged["target_class"] = "target_host"
    forged["self_digest"] = spike.receipt_digest(forged)
    schema = _receipt_schema()
    assert schema_subset_errors(forged, schema, schema) != []
    assert any("disposable_offline" in e for e in spike.validate_runtime_candidate_receipt(forged))


@pytest.mark.parametrize("runtime_seam", list(spike.RUNTIME_ONLY_SEAMS))
def test_runtime_seam_marked_offline_is_rejected(runtime_seam):
    # 核心保證:PASS receipt 若把任一 runtime seam 標為 OFFLINE_PROVEN,schema 與
    # validator 皆拒絕(不可偽造 runtime seam 的離線證明)。
    forged = deepcopy(_build_b())
    for seam in forged["seams"]:
        if seam["seam_id"] == runtime_seam:
            seam["verdict"] = "OFFLINE_PROVEN"
            seam["evidence_class"] = "LOCAL_REPRODUCIBLE"
            seam["offline_evaluable"] = True
    forged["self_digest"] = spike.receipt_digest(forged)
    schema = _receipt_schema()
    assert schema_subset_errors(forged, schema, schema) != []
    assert any("DEFERRED_S1_6" in e for e in spike.validate_runtime_candidate_receipt(forged))


def test_seam_verdict_evidence_class_must_be_consistent():
    forged = deepcopy(_build_b())
    for seam in forged["seams"]:
        if seam["seam_id"] == "content_addressing_determinism":
            seam["evidence_class"] = "STRUCTURAL_ONLY"  # 與 OFFLINE_PROVEN 矛盾
    forged["self_digest"] = spike.receipt_digest(forged)
    assert any("evidence_class inconsistent" in e for e in spike.validate_runtime_candidate_receipt(forged))


@pytest.mark.parametrize(
    "forged_seam_id",
    [
        "network_denial_PROVEN_offline_haha",  # 憑空捏造的未列 id
        "cgroup_isolation ",                   # 真 runtime seam 的尾隨空白同形異義
    ],
)
def test_injected_extra_seam_id_is_rejected_by_validator(forged_seam_id):
    # 核心反偽造(E2 P2):seam-id 為封閉集。偽造 receipt 保留全部真 seam(五個 runtime
    # seam 仍為 DEFERRED,故通過 schema 的 PASS contains 檢查),再夾帶一個額外 seam 標成
    # OFFLINE_PROVEN 走私 runtime-only 能力的離線偽證。schema 對 seam_id 僅要求非空字串
    # → 擋不下;validator 必以 seam-id 集合不符拒絕。
    forged = deepcopy(_build_b())
    forged["seams"].append({
        "seam_id": forged_seam_id,
        "offline_evaluable": True,
        "verdict": "OFFLINE_PROVEN",
        "evidence_class": "LOCAL_REPRODUCIBLE",
        "detail_digest": _digest("forged-extra-seam"),
        "note": "fabricated offline proof of a runtime-only capability",
    })
    forged["self_digest"] = spike.receipt_digest(forged)
    # schema 擋不下憑空額外 seam(真 seam 全在,額外 seam 結構合法)——正是 validator 封閉集的守備範圍。
    schema = _receipt_schema()
    assert schema_subset_errors(forged, schema, schema) == []
    errors = spike.validate_runtime_candidate_receipt(forged)
    assert any("seam-id set mismatch" in e for e in errors)
    assert any(forged_seam_id in e for e in errors)


def test_renamed_runtime_seam_homoglyph_is_rejected():
    # 若把真 runtime seam 改名成尾隨空白同形異義(而非新增),則真 id 缺席:
    # schema(PASS contains 檢查缺 DEFERRED cgroup_isolation)與 validator(缺 runtime seam
    # + seam-id 集合不符)雙雙拒絕。
    forged = deepcopy(_build_b())
    for seam in forged["seams"]:
        if seam["seam_id"] == "cgroup_isolation":
            seam["seam_id"] = "cgroup_isolation "
    forged["self_digest"] = spike.receipt_digest(forged)
    schema = _receipt_schema()
    assert schema_subset_errors(forged, schema, schema) != []
    errors = spike.validate_runtime_candidate_receipt(forged)
    assert any("missing runtime seam: cgroup_isolation" in e for e in errors)
    assert any("seam-id set mismatch" in e for e in errors)


def test_empty_native_inventory_seam_is_structural_not_offline():
    # 承 E2 P3:native inventory 為空時無位元組可雜湊,native_lib_inventory_origin
    # 不得謊稱 OFFLINE_PROVEN → 降為 STRUCTURAL_DESIGN;其餘 OFFLINE seam 仍在,receipt 自洽。
    receipt = _build_b(native_library_inventory=[])
    verdicts = {seam["seam_id"]: seam["verdict"] for seam in receipt["seams"]}
    assert verdicts["native_lib_inventory_origin"] == "STRUCTURAL_DESIGN"
    assert receipt["native_library_inventory"] == []
    assert spike.validate_runtime_candidate_receipt(receipt) == []
    # 非空時仍為 OFFLINE_PROVEN(對照,證明降級只針對空 inventory)。
    non_empty = {seam["seam_id"]: seam["verdict"] for seam in _build_b()["seams"]}
    assert non_empty["native_lib_inventory_origin"] == "OFFLINE_PROVEN"


@pytest.mark.parametrize(
    "path,leaf",
    [
        (("immutability",), "mutable_tag_or_alias"),
        (("immutability",), "relocatable_renamed_venv"),
        (("rollback",), "mutable_current_symlink"),
        (("artifact_persistence",), "inside_immutable_image_or_bundle"),
        (("sealed_input",), "reproducible_output_verified"),
        (("dependency_closure",), "real_ml_closure_resolved"),
    ],
)
def test_prohibition_consts_are_forced_false(path, leaf):
    receipt = _build_b()
    node = receipt
    for key in path:
        node = node[key]
    assert node[leaf] is False


@pytest.mark.parametrize(
    "block,leaf",
    [
        ("immutability", "mutable_tag_or_alias"),
        ("immutability", "relocatable_renamed_venv"),
        ("rollback", "mutable_current_symlink"),
        # 承 E4 P2-1:先前未覆蓋的三個 const-false 不變量偽真後亦須被拒。
        ("artifact_persistence", "inside_immutable_image_or_bundle"),
        ("sealed_input", "reproducible_output_verified"),
        ("dependency_closure", "real_ml_closure_resolved"),
    ],
)
def test_forged_prohibition_true_fails_schema_and_validator(block, leaf):
    forged = deepcopy(_build_b())
    forged[block][leaf] = True
    forged["self_digest"] = spike.receipt_digest(forged)
    schema = _receipt_schema()
    assert schema_subset_errors(forged, schema, schema) != []
    assert spike.validate_runtime_candidate_receipt(forged) != []


def test_native_lib_load_verified_on_target_is_forced_false():
    receipt = _build_b()
    assert receipt["native_library_inventory"]
    for record in receipt["native_library_inventory"]:
        assert record["load_verified_on_target"] is False


def test_forged_native_lib_load_verified_true_fails_schema_and_validator():
    # 承 E4 P2-1:native_library_inventory[].load_verified_on_target 偽真 → schema 與 validator 皆拒。
    forged = deepcopy(_build_b())
    assert forged["native_library_inventory"]
    forged["native_library_inventory"][0]["load_verified_on_target"] = True
    forged["self_digest"] = spike.receipt_digest(forged)
    schema = _receipt_schema()
    assert schema_subset_errors(forged, schema, schema) != []
    assert any(
        "load_verified_on_target" in e
        for e in spike.validate_runtime_candidate_receipt(forged)
    )


# --------------------------------------------------------------------------- #
# evidence-class honesty floor + isolation gate
# --------------------------------------------------------------------------- #
def test_isolation_not_isolated_is_a_fail_not_a_pass():
    # python_isolated_mode 未證成 → FAIL receipt(非 raise),failure_reason 說明。
    receipt = _build_b(isolation_mode=_isolation(python_isolated_mode=False))
    assert receipt["status"] == "FAIL"
    assert "isolated" in receipt["failure_reason"]
    assert spike.validate_runtime_candidate_receipt(receipt, require_success=True)


def test_ambient_env_not_ignored_is_a_fail():
    receipt = _build_b(isolation_mode=_isolation(ignores_ambient_env=False))
    assert receipt["status"] == "FAIL"
    assert spike.validate_runtime_candidate_receipt(receipt, require_success=True)


def test_evidence_class_local_requires_an_offline_seam():
    forged = deepcopy(_build_b())
    forged["evidence_class"] = "STRUCTURAL_ONLY"  # 但仍有 OFFLINE_PROVEN seam → 矛盾
    forged["self_digest"] = spike.receipt_digest(forged)
    assert any("STRUCTURAL_ONLY contradicts" in e for e in spike.validate_runtime_candidate_receipt(forged))


def test_unknown_candidate_refuses_to_build():
    with pytest.raises(ValueError):
        _build_b(candidate_id="wasm_sandbox")


def test_content_addressed_candidate_must_carry_null_oci_build():
    forged = deepcopy(_build_b())
    forged["oci_build"] = {
        "builder": None, "built": False, "image_id": None, "image_platform": None,
        "buildx_multiarch": False, "target_arch_match_verified": False,
    }
    forged["self_digest"] = spike.receipt_digest(forged)
    assert any("oci_build=null" in e for e in spike.validate_runtime_candidate_receipt(forged))


def test_forged_oci_build_built_true_without_image_id_is_rejected():
    # 承 E4 P2-2:built=true 但無 image_id 為跨欄不一致(schema 無法察覺)→ validator 拒。
    forged = deepcopy(_build_a())
    forged["oci_build"]["built"] = True  # image_id 仍為 None
    forged["self_digest"] = spike.receipt_digest(forged)
    assert any(
        "built=true but has no image_id" in e
        for e in spike.validate_runtime_candidate_receipt(forged)
    )


def test_forged_oci_build_false_with_image_id_is_rejected():
    # 承 E4 P2-2:built=false 卻帶 image_id 為跨欄不一致 → validator 拒。
    forged = deepcopy(_build_a())
    forged["oci_build"]["image_id"] = "sha256:" + "a" * 64  # built 仍為 False
    forged["self_digest"] = spike.receipt_digest(forged)
    assert any(
        "built=false must not carry an image_id" in e
        for e in spike.validate_runtime_candidate_receipt(forged)
    )


@pytest.mark.parametrize("flag", ["buildx_multiarch", "target_arch_match_verified"])
def test_forged_oci_build_const_false_flag_fails_schema_and_validator(flag):
    # 承 E4 P2-2:buildx_multiarch / target_arch_match_verified 偽真 → schema(const false)
    # 與 validator 皆拒(離線無從證明跨架構建置 / 目標架相符)。
    forged = deepcopy(_build_a())
    forged["oci_build"][flag] = True
    forged["self_digest"] = spike.receipt_digest(forged)
    schema = _receipt_schema()
    assert schema_subset_errors(forged, schema, schema) != []
    assert spike.validate_runtime_candidate_receipt(forged) != []


def test_probe_python_isolated_mode_rejects_relative_interpreter():
    # FIX(P2):相對直譯器(如 "python")會由 subprocess 走繼承 PATH 查找,不得被回報成
    # absolute_pinned / system_python_fallback_possible=false。啟動前(isabs 檢查在 subprocess 之前)
    # 即 fail-closed 拒;因此本測試 hermetic,不會實跑任何子進程。
    for relative in ("python", "python3", "bin/python3", "./python"):
        with pytest.raises(RuntimeError, match="absolute"):
            spike.probe_python_isolated_mode(interpreter=relative)


def test_structural_isolation_contract_is_carried_into_receipt():
    # 承 E2 P3 / E4 P3-1:structural_isolation_contract()(不跑子進程,STRUCTURAL_ONLY)須被
    # builder 忠實搬入 isolation_mode 區塊——receipt 的 isolation 主張即對照此真實 contract 檢核。
    contract = spike.structural_isolation_contract()
    assert contract["evidence_class"] == "STRUCTURAL_ONLY"
    receipt = _build_b(isolation_mode=contract)
    iso = receipt["isolation_mode"]
    assert iso["python_isolated_mode"] is True
    assert iso["ignores_ambient_env"] is True
    assert iso["system_python_fallback_possible"] is False
    assert iso["launch_interpreter"] == "absolute_pinned"
    assert iso["evidence_class"] == "STRUCTURAL_ONLY"
    assert spike.validate_runtime_candidate_receipt(receipt) == []


# --------------------------------------------------------------------------- #
# secret scan
# --------------------------------------------------------------------------- #
def test_builder_refuses_to_serialize_an_injected_secret():
    with pytest.raises(spike.SecretLeakageError):
        _build_b(caller="password=hunter2supersecret")


def test_secret_guard_detects_github_and_auth_families():
    assert spike._contains_secret_like("github_pat_" + "A" * 22)
    assert spike._contains_secret_like("Bearer abcdef0123456789xyz")
    with pytest.raises(spike.SecretLeakageError):
        _build_b(caller="ghp_" + "C" * 20)


def test_validator_rescans_for_embedded_secret():
    poisoned = deepcopy(_build_b())
    poisoned["caller"] = "authorization: Bearer abcdef0123456789xyz"
    poisoned["self_digest"] = spike.receipt_digest(poisoned)
    assert any("secret-like" in e for e in spike.validate_runtime_candidate_receipt(poisoned))


def test_receipt_carries_no_hardcoded_host_paths():
    # 可攜性:receipt 不得嵌任何機器路徑(/Users、/home、machine-specific)。
    serialized = json.dumps(_build_a(), ensure_ascii=False)
    assert "/Users/" not in serialized
    assert "/home/" not in serialized


# --------------------------------------------------------------------------- #
# preliminary comparison — final_choice const null
# --------------------------------------------------------------------------- #
def _comparison():
    return spike.build_runtime_candidate_comparison(
        _build_a(), _build_b(), observation_time=OBS, ttl_seconds=3600
    )


def test_comparison_final_choice_is_null_and_roundtrips():
    comparison = _comparison()
    assert comparison["final_choice"] is None
    assert set(comparison) == spike.COMPARISON_FIELDS
    assert spike.validate_runtime_candidate_comparison(comparison, now=NOW) == []
    schema = _comparison_schema()
    assert schema_subset_errors(comparison, schema, schema) == []


def test_comparison_binds_both_receipt_self_digests():
    comparison = _comparison()
    assert comparison["candidate_a_digest"] == _build_a()["self_digest"]
    assert comparison["candidate_b_digest"] == _build_b()["self_digest"]
    assert comparison["self_digest"] == spike.comparison_digest(comparison)


def test_comparison_forged_final_choice_fails_schema_and_validator():
    forged = deepcopy(_comparison())
    forged["final_choice"] = "exact_image_id_oci"
    forged["self_digest"] = spike.comparison_digest(forged)
    schema = _comparison_schema()
    assert schema_subset_errors(forged, schema, schema) != []
    assert any("final_choice must be null" in e for e in spike.validate_runtime_candidate_comparison(forged))


def test_comparison_matrix_marks_oci_only_seam_na_for_candidate_b():
    matrix = {row["seam_id"]: row for row in _comparison()["seam_matrix"]}
    assert matrix["exact_image_id_pin"]["a_verdict"] == "STRUCTURAL_DESIGN"
    assert matrix["exact_image_id_pin"]["b_verdict"] == "N_A"
    # runtime seam 兩側皆 DEFERRED_S1_6,decisive_at=S1.6。
    assert matrix["cgroup_isolation"]["a_verdict"] == "DEFERRED_S1_6"
    assert matrix["cgroup_isolation"]["b_verdict"] == "DEFERRED_S1_6"
    assert matrix["cgroup_isolation"]["decisive_at"] == "S1.6"


def test_comparison_deferred_list_is_exactly_the_runtime_seams():
    assert _comparison()["deferred_to_s1_6"] == list(spike.RUNTIME_ONLY_SEAMS)


def test_comparison_rejects_swapped_candidate_order():
    with pytest.raises(ValueError):
        spike.build_runtime_candidate_comparison(
            _build_b(), _build_a(), observation_time=OBS, ttl_seconds=3600
        )


def test_comparison_preliminary_lean_is_non_binding_string():
    lean = _comparison()["preliminary_lean"]
    assert isinstance(lean, str) and "NON-BINDING" in lean


def test_comparison_both_pass_records_candidate_status():
    comparison = _comparison()
    assert comparison["candidate_status"] == {"a": "PASS", "b": "PASS"}


def test_comparison_surfaces_a_failing_candidate_status():
    # 承 E4 P2-3 / E2 P3:比較表不得把 FAIL 候選悄悄呈現為「兩者皆已評估」。
    # 一個 FAIL 候選 B 的 status 必顯性浮現於 candidate_status,且 final_choice 仍為 null。
    passing_a = _build_a()
    failing_b = _build_b(isolation_mode=_isolation(python_isolated_mode=False))
    assert failing_b["status"] == "FAIL"
    comparison = spike.build_runtime_candidate_comparison(
        passing_a, failing_b, observation_time=OBS, ttl_seconds=3600
    )
    assert comparison["candidate_status"] == {"a": "PASS", "b": "FAIL"}
    assert comparison["final_choice"] is None
    # 無 receipt:結構/enum 有效。
    assert spike.validate_runtime_candidate_comparison(comparison, now=NOW) == []
    # 有 receipt:記錄的 status 與 digest 交叉核對通過。
    assert spike.validate_runtime_candidate_comparison(
        comparison, now=NOW, receipt_a=passing_a, receipt_b=failing_b
    ) == []
    schema = _comparison_schema()
    assert schema_subset_errors(comparison, schema, schema) == []


def test_comparison_forged_candidate_status_is_caught_against_receipt():
    # 謊報 candidate_status 與真實 receipt 不符 → validator(帶 receipt 交叉核對)抓出。
    passing_a = _build_a()
    failing_b = _build_b(isolation_mode=_isolation(ignores_ambient_env=False))
    assert failing_b["status"] == "FAIL"
    comparison = spike.build_runtime_candidate_comparison(
        passing_a, failing_b, observation_time=OBS, ttl_seconds=3600
    )
    forged = deepcopy(comparison)
    forged["candidate_status"]["b"] = "PASS"  # 把 FAIL 謊報成 PASS
    forged["self_digest"] = spike.comparison_digest(forged)
    errors = spike.validate_runtime_candidate_comparison(
        forged, now=NOW, receipt_a=passing_a, receipt_b=failing_b
    )
    assert any("candidate_status.b does not match" in e for e in errors)


def test_comparison_missing_candidate_status_is_rejected():
    forged = deepcopy(_comparison())
    forged["candidate_status"] = {"a": "PASS"}  # 缺 b
    forged["self_digest"] = spike.comparison_digest(forged)
    assert any(
        "candidate_status must map a/b to PASS/FAIL" in e
        for e in spike.validate_runtime_candidate_comparison(forged)
    )


# --------------------------------------------------------------------------- #
# identity constants
# --------------------------------------------------------------------------- #
def test_harness_and_schema_ids_are_constants():
    assert spike.HARNESS_ID == "runtime_candidate_spike_v1"
    assert spike.RECEIPT_SCHEMA_VERSION == "runtime_candidate_receipt_v1"
    assert spike.COMPARISON_SCHEMA_VERSION == "runtime_candidate_comparison_v1"
    assert spike.TTL_CEILING_SECONDS == 3600
    assert spike.S1_TARGET_CLASS == "disposable_offline"
    assert set(spike.RUNTIME_ONLY_SEAMS) == {
        "native_lib_loading_target", "cgroup_isolation", "network_denial",
        "start_stop_failure_cleanup", "pg_identity_runtime",
    }
