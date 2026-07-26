"""S2.4(WP4·W5)wave-exit 中央導出的 focused 測試(§10.3 W5 row / §10.5 #27)。

證明:

- W5 wave-exit 於當前 checkout 自足再導出(結構 + 鏈綁定),且中央閘接受它;
- 竄改鏈上任一環(W4 receipt / W5 predecessor digest / owned-path 或 ABI 投影 / 非當前
  HEAD / caller 自證 status / 缺 chain)一律 NOT_PASS;
- W5 exported-ABI 折入的六組活裁決確實可再導出——它們就是 W5 補上的六條 §10.5 覆蓋缺口,
  任何一條的 source 面被弱化,``w5_structural_errors`` 必然給出具名 reason;
- W4 交出的十二項義務逐條被帶到 W5 且 owner 不被偷偷降級;W5 自審新增的四項以同一誠實形狀
  記錄;
- W5 owned-path 集合每一條都真實存在(pin 不得腐化成死路徑);
- 「未實作 wave」的 fail-closed 邊界由 W5 推進到 W6。

誠實邊界:W5 的投影葉是 facade top-level import,因此進入 engine-scanner runtime import
閉包並被宣告在 ``application_bundle_runtime_closure_v1.json``。application-bundle builder
從**已提交 blob** 解析宣告路徑,所以在 PM 提交之前該 builder 會 typed 回
``APPLICATION_BUNDLE_TREE_INVALID``,W2 段因此不 PASS——那是 committed-blob 契約在正常運作,
不是缺陷。故本檔與 W4 的姿態一致:分別斷言「W5 自身再導出」與「鏈斷即斷」,不假裝乾淨樹。
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
for candidate in (HELPERS, ML_ROOT, PROGRAM_CODE):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2_4_install as install  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402

_EVID = {
    "test_digests": ["sha256:" + "1" * 64],
    "capture_digests": ["sha256:" + "2" * 64],
    "review_fragment_digests": ["sha256:" + "3" * 64],
}
# W4 匯出的十二項義務(§10.3 誠實面);W5 一項都不得靜默丟掉。
_W4_HANDOVER = (
    "ATTESTATION_EXPIRY_AND_HOST_TIME_ARE_NOT_CROSS_CHECKED",
    "ATTESTOR_KEY_IS_NOT_SEPARATE_FROM_THE_PERMIT_KEY",
    "EFFECT_RECEIPT_RECONCILE_BINDING",
    "ENCRYPTED_BLOB_DIGEST_ORDERING",
    "INSTALLED_UNIT_PROBE_CORE_BINDING",
    "OBSERVER_SPACE_PRE_STATE_DIGEST",
    "PLAN_EXPIRY_OUTSIDE_SIGNED_CORE",
    "PRIOR_LINEAGE_ENTRY_IDENTITY",
    "RECEIPT_EMISSION_PENDING_IS_NOT_A_RECEIPT_RETRY",
    "STARTUP_JOURNAL_PARENTS_MUST_PREEXIST",
    "STARTUP_RECONCILE_SURFACE_ABSENT",
    "STRANDED_WAL_TEMP_FILES_ARE_REPORT_ONLY",
)
_W5_NEW = (
    # W5 後半段(2026-07-27)實作了 §9.2 的閘,於是舊的「整份缺席」義務被關閉,換成兩條
    # 精確殘留:§3 的 receipt 綁定欄位不存在,以及 reproducer 節點獨立性只有宣告面。
    "DEPENDENCY_REFRESH_RECEIPT_BINDING_ABSENT",
    "DEPENDENCY_REFRESH_REPRODUCER_NODE_IS_DECLARATIVE",
    "OWNED_PATH_PROJECTION_RULER_IS_NOT_UNIFORM",
    "PR_SET_DUMPABLE_IS_DECLARED_NOT_ENFORCED",
    "S2_5_LIFECYCLE_FIXTURES_DO_NOT_EXIST",
)


@pytest.fixture(scope="module")
def chain():
    admission = install.build_w0_source_admission_receipt(ROOT)
    w0 = install.build_w0_wave_exit_receipt(admission, **deepcopy(_EVID))
    w1 = install.build_w1_wave_exit_receipt(admission, w0, **deepcopy(_EVID))
    w2 = install.build_w2_wave_exit_receipt(admission, w1, **deepcopy(_EVID))
    w3 = install.build_w3_wave_exit_receipt(admission, w2, **deepcopy(_EVID))
    w4 = install.build_w4_wave_exit_receipt(admission, w3, **deepcopy(_EVID))
    w5 = validator.build_w5_wave_exit_receipt(admission, w4, **deepcopy(_EVID))
    return admission, w0, w1, w2, w3, w4, w5


def _derive(w5, admission, w4, w0, w1, w2, w3):
    return validator.derive_wave_exit_status(
        w5,
        source_admission_receipt=admission,
        predecessor_wave_receipt=w4,
        predecessor_wave_chain=(w0, w1, w2, w3),
    )


# ── W5 自身的結構/綁定再導出(與 predecessor 鏈狀態無關)────────────────────────
def test_w5_structural_and_chain_binding_rederive_on_the_current_checkout(chain) -> None:
    admission, _w0, _w1, _w2, _w3, w4, w5 = chain
    assert validator.w5_structural_errors(w5) == []
    assert validator._wave_exit_structural_errors(w5) == []
    assert validator.w5_chain_binding_errors(
        w5, admission, w4, validator._git_head(ROOT)
    ) == []
    assert validator.validate_aiml_artifact(w5) == []
    assert w5["wave"] == "W5"
    assert not any(key in w5 for key in validator._CALLER_STATUS_KEYS)
    assert w5["production_authority_flags"] == {
        "nine_authorities_false": True,
        "production_apply_performed": False,
        "running_attested": False,
    }


def test_the_w5_derivation_is_wired_and_no_longer_the_unimplemented_branch(chain) -> None:
    admission, w0, w1, w2, w3, w4, w5 = chain
    result = _derive(w5, admission, w4, w0, w1, w2, w3)
    assert not any(
        "only implemented for" in reason for reason in result["reasons"]
    ), result["reasons"]
    predecessor = validator.derive_wave_exit_status(
        w4, source_admission_receipt=admission, predecessor_wave_receipt=w3,
        predecessor_wave_chain=(w0, w1, w2),
    )
    if predecessor["status"] == "PASS":
        assert result == {"status": "PASS", "reasons": []}
    else:
        assert result["status"] == "NOT_PASS"
        assert all(
            reason.startswith("W5 wave-exit bound predecessor_wave_receipt does not derive PASS")
            for reason in result["reasons"]
        ), result["reasons"]


def test_tampered_w4_predecessor_breaks_the_w5_chain(chain) -> None:
    admission, w0, w1, w2, w3, w4, w5 = chain
    forged_w4 = deepcopy(w4)
    forged_w4["owned_path_diff_digest"] = "sha256:" + "e" * 64
    forged_w4["self_digest"] = validator.artifact_self_digest(forged_w4)
    result = _derive(w5, admission, forged_w4, w0, w1, w2, w3)
    assert result["status"] == "NOT_PASS"
    assert any(
        "predecessor_wave_receipt does not derive PASS" in reason
        for reason in result["reasons"]
    )


def test_w5_requires_the_exact_four_element_predecessor_chain(chain) -> None:
    admission, w0, w1, w2, w3, w4, w5 = chain
    for bad in ((), (w0,), (w0, w1), (w0, w1, w2), (w0, w1, w2, w3, w4)):
        assert validator.derive_wave_exit_status(
            w5,
            source_admission_receipt=admission,
            predecessor_wave_receipt=w4,
            predecessor_wave_chain=bad,
        )["status"] == "NOT_PASS"
    assert validator.derive_wave_exit_status(
        w5, source_admission_receipt=admission, predecessor_wave_chain=(w0, w1, w2, w3)
    )["status"] == "NOT_PASS"
    assert validator.derive_wave_exit_status(
        w5, predecessor_wave_receipt=w4, predecessor_wave_chain=(w0, w1, w2, w3)
    )["status"] == "NOT_PASS"


def test_w5_predecessor_must_be_the_w4_receipt(chain) -> None:
    admission, _w0, _w1, _w2, w3, _w4, w5 = chain
    swapped = deepcopy(w5)
    swapped["predecessor_wave_receipt_digest"] = w3["self_digest"]
    swapped["self_digest"] = validator.artifact_self_digest(swapped)
    reasons = validator.w5_chain_binding_errors(
        swapped, admission, w3, validator._git_head(ROOT)
    )
    assert any("predecessor must be the W4 wave-exit receipt" in r for r in reasons)


@pytest.mark.parametrize("field,value", [
    ("status", "PASS"), ("pass", True), ("done", True), ("admitted", True),
])
def test_w5_self_declared_status_rejected_before_derivation(chain, field, value) -> None:
    admission, w0, w1, w2, w3, w4, w5 = chain
    forged = deepcopy(w5)
    forged[field] = value
    forged["self_digest"] = validator.artifact_self_digest(forged)
    result = _derive(forged, admission, w4, w0, w1, w2, w3)
    assert result["status"] == "NOT_PASS"
    assert any("must not self-declare status" in r for r in result["reasons"])


@pytest.mark.parametrize("field", [
    "owned_path_manifest_digest", "owned_path_diff_digest", "exported_abi_digest",
])
def test_w5_projection_drift_is_not_pass(chain, field) -> None:
    admission, w0, w1, w2, w3, w4, w5 = chain
    forged = deepcopy(w5)
    forged[field] = "sha256:" + "a" * 64
    forged["self_digest"] = validator.artifact_self_digest(forged)
    assert validator.w5_structural_errors(forged)
    assert _derive(forged, admission, w4, w0, w1, w2, w3)["status"] == "NOT_PASS"


def test_w5_null_predecessor_digest_is_structurally_rejected(chain) -> None:
    _admission, _w0, _w1, _w2, _w3, _w4, w5 = chain
    forged = deepcopy(w5)
    forged["predecessor_wave_receipt_digest"] = None
    forged["self_digest"] = validator.artifact_self_digest(forged)
    assert any(
        "non-null predecessor_wave_receipt_digest" in r
        for r in validator.w5_structural_errors(forged)
    )


def test_w5_source_head_must_be_the_current_checkout_head(chain) -> None:
    admission, _w0, _w1, _w2, _w3, w4, w5 = chain
    forged = deepcopy(w5)
    forged["source_head"] = "b" * 40
    forged["self_digest"] = validator.artifact_self_digest(forged)
    reasons = validator.w5_chain_binding_errors(
        forged, admission, w4, validator._git_head(ROOT)
    )
    assert any("source_head" in r for r in reasons)


@pytest.mark.parametrize("field", ["test_digests", "capture_digests", "review_fragment_digests"])
def test_w5_empty_evidence_lists_never_derive_pass(chain, field) -> None:
    admission, w0, w1, w2, w3, w4, _w5 = chain
    evidence = deepcopy(_EVID)
    evidence[field] = []
    forged = validator.build_w5_wave_exit_receipt(admission, w4, **evidence)
    assert _derive(forged, admission, w4, w0, w1, w2, w3)["status"] == "NOT_PASS"


# ── owned paths / exported ABI ──────────────────────────────────────────────────
def test_w5_owned_paths_are_live_and_cover_the_w5_surface() -> None:
    required = {
        "program_code/ml_training/aiml_gate_receipt_validator.py",
        "program_code/ml_training/aiml_gate_receipt_wave_w5.py",
        "program_code/ml_training/application_bundle_runtime_closure_v1.json",
        "tests/structure/test_agent_governance_s2_4_acceptance_matrix.py",
        "tests/structure/test_agent_governance_s2_4_install_w5.py",
    }
    missing = required - set(validator._W5_OWNED_PATHS)
    assert not missing, f"W5 owned-path binding misses W5 surface members: {sorted(missing)}"
    dead = [rel for rel in validator._W5_OWNED_PATHS if not (ROOT / rel).is_file()]
    assert not dead, f"W5 owned paths contain dead entries: {dead}"


def test_the_w5_projection_leaf_is_declared_in_the_runtime_import_closure() -> None:
    """facade top-level import ⇒ 進入 engine-scanner runtime import 閉包 ⇒ 必須被宣告。"""

    import json

    closure = json.loads(
        (ML_ROOT / "application_bundle_runtime_closure_v1.json").read_text(encoding="utf-8")
    )
    assert "program_code/ml_training/aiml_gate_receipt_wave_w5.py" in closure["python_modules"]
    assert closure["self_digest"] == validator.artifact_self_digest(
        {k: v for k, v in closure.items() if k != "self_digest"}
    )


def test_a_degraded_dependency_refresh_gate_breaks_the_w5_wave_exit_by_name(
    chain, monkeypatch
) -> None:
    """§9.2 的活裁決是**接進 wave-exit** 的,不只是投影裡的一個值。

    把 ``_dependency_refresh_live`` 換成一份「refresh-by-reference 被放行 + 復述舊 digest
    被採信」的退化投影,``w5_structural_errors`` 必須給出具名 reason。若有人把
    ``_dependency_refresh_reasons`` 的接線拿掉,本測試轉紅。
    """

    import aiml_gate_receipt_wave_w5 as wave_w5

    _admission, _w0, _w1, _w2, _w3, _w4, w5 = chain
    clean = wave_w5._dependency_refresh_live(ROOT)
    degraded = dict(clean)
    degraded["reasserted_original_digest_status"] = "DEPENDENCY_REFRESH_ADMITTED"
    degraded["never_refreshable_statuses"] = {
        name: "SOURCE_DEPENDENCY_ADMITTED_BY_REFRESH"
        for name in clean["never_refreshable_classes"]
    }
    monkeypatch.setattr(wave_w5, "_dependency_refresh_live", lambda *_a, **_k: degraded)
    reasons = validator.w5_structural_errors(w5)
    assert any("merely re-asserts the original digest" in r for r in reasons), reasons
    assert any("refresh-by-reference" in r for r in reasons), reasons


def test_w5_exported_abi_projection_folds_the_seven_live_verdict_groups() -> None:
    projection = validator.w5_exported_abi_projection()
    secret = projection["secret_scan_live"]
    assert secret["encoded_forms_detected"] == {
        "raw": True, "base64": True, "base16_upper": True, "base16_lower": True,
        "urlsafe_base64": True, "hex": True,
    }
    assert secret["dict_key_is_scanned"] is True
    assert secret["bytes_node_is_scanned"] is True
    assert secret["clean_artifact_passes"] is True
    assert secret["no_sentinel_is_a_noop"] is True
    pg = projection["pg_role_identity_live"]
    assert pg["manifest_role_name_const"] == "aiml_engine_scanner"
    assert pg["shipped_manifest_role_name"] == "aiml_engine_scanner"
    assert pg["observer_named_manifest_is_centrally_rejected"] is True
    assert pg["observer_absent_from_generated_sql"] is True
    assert pg["every_generated_statement_names_the_scanner_role_or_public"] is True
    assert pg["grantee_vocabulary"] == ['"aiml_engine_scanner"', "PUBLIC"]
    scope = projection["component_scope_live"]
    assert scope["row_count"] == 5
    assert all(scope["forbidden_component_identities_absent"].values())
    postcheck = projection["inactive_postcheck_live"]
    assert postcheck["postcheck_carries_no_lifecycle_claim"] is True
    assert postcheck["receipt_carries_no_lifecycle_claim"] is True
    assert postcheck["postcheck_additional_properties_closed"] is True
    assert all(postcheck["enable_and_start_are_forbidden"].values())
    unit = projection["rendered_unit_negative_live"]
    assert unit["clean_unit_status"] == "PASS"
    assert unit["system_interpreter_status"] == "ENGINE_SCANNER_UNIT_INVALID"
    assert unit["alr_shadow_identity_status"] == "ENGINE_SCANNER_UNIT_INVALID"
    assert unit["mutable_checkout_status"] == "ENGINE_SCANNER_UNIT_INVALID"
    schema = projection["schema_registration_live"]
    assert schema["unregistered_schema_keys"] == []
    assert schema["unresolvable_schema_keys"] == []
    assert schema["undeclared_on_disk_schema_keys"] == []
    # W5 後半段:§10.1 明列的那一份 schema 已存在且已註冊(缺口由「記錄」翻成「已建」)。
    assert schema["dependency_refresh_schema_file_exists"] is True
    assert schema["dependency_refresh_schema_registered"] is True
    refresh = projection["dependency_refresh_live"]
    assert refresh["positive_refresh_status"] == "DEPENDENCY_REFRESH_ADMITTED"
    assert refresh["positive_admission_status"] == "SOURCE_DEPENDENCY_ADMITTED_BY_REFRESH"
    assert refresh["expired_without_refresh_status"] == (
        "SOURCE_DEPENDENCY_EXPIRED_NO_REFRESH"
    )
    for key in (
        "reasserted_original_digest_status",
        "same_producer_node_status",
        "refresh_of_a_refresh_status",
        "self_declared_status_status",
        "substituted_original_status",
        "stale_head_status",
        "semantic_digest_drift_status",
    ):
        assert refresh[key] == "DEPENDENCY_REFRESH_REJECTED", key
    assert refresh["two_refreshes_status"] == "SOURCE_DEPENDENCY_REJECTED"
    assert all(
        status == "DEPENDENCY_REFRESH_BY_REFERENCE_FORBIDDEN"
        for status in refresh["never_refreshable_statuses"].values()
    )
    assert refresh["refresh_carries_no_signature_field"] is True
    assert all(refresh["reproducible_class_field_sets"].values())


def test_w5_abi_states_its_boundary_and_names_no_effect() -> None:
    abi = validator._W5_EXPORTED_ABI
    assert abi["wave"] == "W5"
    assert "no runtime, host, production-PostgreSQL or effect evidence" in (
        abi["boundary_contract"]
    )
    assert "SOURCE_READY only" in abi["boundary_contract"]
    assert "adds no production gate and performs no effect" in abi["wave_scope"]
    for contract in (
        "secret_scan_contract", "pg_role_identity_contract", "component_scope_contract",
        "inactive_postcheck_contract", "rendered_unit_identity_contract",
        "schema_registration_contract", "acceptance_map_contract",
    ):
        assert abi[contract] and len(abi[contract]) > 120, contract


# ── 義務移交:一項都不得靜默丟掉 ─────────────────────────────────────────────────
@pytest.mark.parametrize("obligation_id", _W4_HANDOVER)
def test_every_w4_obligation_is_carried_forward_with_an_owner(obligation_id) -> None:
    w4_ids = {
        row["obligation_id"]
        for row in validator._W4_EXPORTED_ABI["remaining_owned_obligations"]
    }
    assert obligation_id in w4_ids, "the W4 handover list drifted from the W4 ABI"
    rows = {
        row["obligation_id"]: row
        for row in validator._W5_EXPORTED_ABI["remaining_owned_obligations"]
    }
    entry = rows[obligation_id]
    assert entry["owner_wave"] and entry["spec_refs"] and entry["statement"]
    assert entry["w5_provides"]
    assert entry["typed_status"] in {
        "OPEN_DESIGN_QUESTION", "OPEN_BY_DESIGN_W6_RUNNER_PRECONDITION",
        "OPEN_HONEST_BOUNDARY", "PARTIALLY_PROVIDED_BY_W4B", "NOT_PROVIDED_BY_W5",
    }


def test_w5_records_its_own_new_findings_in_the_same_honest_shape() -> None:
    rows = {
        row["obligation_id"]: row
        for row in validator._W5_EXPORTED_ABI["remaining_owned_obligations"]
    }
    assert set(_W5_NEW) <= set(rows)
    for obligation_id in _W5_NEW:
        entry = rows[obligation_id]
        assert set(entry) >= {
            "obligation_id", "typed_status", "owner_wave", "spec_refs", "statement",
            "w5_provides",
        }
        assert len(entry["statement"]) > 200
    # W4 那條 ATTESTED_EVIDENCE_CLASS_VERIFIER 已由 W4b 在源碼線交付,不再是 W5 的未提供項。
    assert "ATTESTED_EVIDENCE_CLASS_VERIFIER" not in rows


def test_the_w5_obligation_ledger_has_no_duplicate_or_unowned_row() -> None:
    rows = validator._W5_EXPORTED_ABI["remaining_owned_obligations"]
    ids = [row["obligation_id"] for row in rows]
    assert len(ids) == len(set(ids))
    assert set(ids) == set(_W4_HANDOVER) | set(_W5_NEW) | {
        "REPLAY_LEDGER_CONSUME_ONCE_IS_A_FILESYSTEM_PROPERTY",
        "STARTUP_RECONCILE_LANE_PATHS",
    }
    for row in rows:
        assert row["owner_wave"] in {"PM", "S2.5A", "W6", "W6B"}, row["obligation_id"]


# ── 未實作 wave 的 fail-closed 邊界推進到 W6 ────────────────────────────────────
def test_w6_and_beyond_remain_fail_closed(chain) -> None:
    admission, w0, w1, w2, w3, w4, _w5 = chain
    forged = deepcopy(w4)
    forged["wave"] = "W5"  # schema enum 只到 W5;W6 需要先擴 enum,故以 W5-shaped W4 探測
    forged["self_digest"] = validator.artifact_self_digest(forged)
    # W4 的投影冒充 W5 → W5 的結構再導出必然拒(投影不對),而非被當成已實作而放行。
    result = validator.derive_wave_exit_status(
        forged, source_admission_receipt=admission, predecessor_wave_receipt=w4,
        predecessor_wave_chain=(w0, w1, w2, w3),
    )
    assert result["status"] == "NOT_PASS"
    assert any("W5 exported-ABI projection" in r for r in result["reasons"])
    # schema 的 wave enum 仍封閉在 W0..W5:W6 不可能被自證。
    schema = validator._load_schema("s2_4_wave_exit_receipt_v1")
    assert schema["properties"]["wave"]["enum"] == ["W0", "W1", "W2", "W3", "W4", "W5"]


def test_the_facade_reexports_the_w5_surface() -> None:
    for name in (
        "_W5_OWNED_PATHS", "_W5_EXPORTED_ABI", "w5_structural_errors",
        "w5_chain_binding_errors", "w5_exported_abi_projection", "w5_owned_path_diff_digest",
        "build_w5_wave_exit_receipt",
    ):
        assert hasattr(validator, name), name
    assert validator._WAVE_PREDECESSOR_CHAIN["W5"][0] == "W4"
    assert validator._WAVE_PREDECESSOR_CHAIN["W5"][1] == 4


def test_w5_builds_a_receipt_without_writing_anything(tmp_path, chain) -> None:
    """W5 不擁有發射器:``build_w5_wave_exit_receipt`` 只回記憶體物件、零檔案副作用。"""

    admission, _w0, _w1, _w2, _w3, w4, _w5 = chain
    before = sorted(p.name for p in tmp_path.iterdir())
    receipt = validator.build_w5_wave_exit_receipt(admission, w4, **deepcopy(_EVID))
    assert receipt["wave"] == "W5"
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    assert not hasattr(install, "emit_w5_receipts")
    assert not (
        ROOT / "docs/execution_plan/ai_ml_landing/receipts/S2.4-WP4-W5"
    ).exists()
