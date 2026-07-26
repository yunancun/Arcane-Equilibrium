"""S2.4(WP4·W4)wave-exit 中央導出與 w4-emit 發射器的 focused 測試(§10.3 W4 row)。

證明:

- W0→W1→W2→W3→W4 完整鏈於當前 checkout 再導出(predecessor=W3 物件 +
  ``predecessor_wave_chain=(W0, W1, W2)``);髒 owned scope 會讓 W2 段先斷,故此處以
  「W4 自身的結構/綁定再導出」與「鏈斷即斷」兩面分別斷言,不假裝乾淨樹;
- 竄改鏈上任一環(W3 receipt / W4 predecessor digest / owned-path 或 ABI 投影 / 非當前 HEAD /
  caller 自證 status / 缺 chain)一律 NOT_PASS(§10.5 #27);
- W4 exported-ABI 投影折入的五組活裁決確實可再導出(permit↔plan 綁定、install lock、
  三本 WAL journal、§9 TTL 預算、獨立補償後 postcheck);
- W3 的 ``w4_owned_obligations`` 只留下 ``ENCRYPTED_BLOB_DIGEST_ORDERING``,W4a 交付的三項
  已移除,且 W4 自身未交付的義務以同一誠實形狀記在 ``remaining_owned_obligations``;
- W4 owned-path 集合每一條都真實存在(pin 不得腐化成死路徑);
- ``w4-emit`` CLI 的 ``--out`` 同樣受限於 repo receipts 目錄(**不實跑發射**)。
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
_TEST_EVIDENCE = {
    "command": "python3 -m pytest tests/structure/test_agent_governance_s2_4_journal.py -q",
    "exit_code": 0,
    "summary": "unit-test placeholder evidence for W4 emitter behaviour tests",
}
_REVIEW_PROVENANCE = [{"pr": 999, "merge_head": "f" * 40, "verdict": "test-fixture"}]


def _chain():
    admission = install.build_w0_source_admission_receipt(ROOT)
    w0 = install.build_w0_wave_exit_receipt(admission, **deepcopy(_EVID))
    w1 = install.build_w1_wave_exit_receipt(admission, w0, **deepcopy(_EVID))
    w2 = install.build_w2_wave_exit_receipt(admission, w1, **deepcopy(_EVID))
    w3 = install.build_w3_wave_exit_receipt(admission, w2, **deepcopy(_EVID))
    w4 = install.build_w4_wave_exit_receipt(admission, w3, **deepcopy(_EVID))
    return admission, w0, w1, w2, w3, w4


def _derive(w4, admission, w3, w0, w1, w2):
    return validator.derive_wave_exit_status(
        w4,
        source_admission_receipt=admission,
        predecessor_wave_receipt=w3,
        predecessor_wave_chain=(w0, w1, w2),
    )


# ── W4 自身的結構/綁定再導出(與 predecessor 鏈狀態無關)────────────────────────
def test_w4_structural_and_chain_binding_rederive_on_the_current_checkout() -> None:
    admission, w0, w1, w2, w3, w4 = _chain()
    assert validator.w4_structural_errors(w4) == []
    assert validator._wave_exit_structural_errors(w4) == []
    assert validator.w4_chain_binding_errors(
        w4, admission, w3, validator._git_head(ROOT)
    ) == []
    assert validator.validate_aiml_artifact(w4) == []
    assert w4["wave"] == "W4"
    assert not any(key in w4 for key in validator._CALLER_STATUS_KEYS)
    assert w4["production_authority_flags"] == {
        "nine_authorities_false": True,
        "production_apply_performed": False,
        "running_attested": False,
    }


def test_the_w4_derivation_is_wired_and_no_longer_the_unimplemented_branch() -> None:
    admission, w0, w1, w2, w3, w4 = _chain()
    result = _derive(w4, admission, w3, w0, w1, w2)
    assert not any(
        "only implemented for" in reason for reason in result["reasons"]
    ), result["reasons"]
    # 若 predecessor 鏈在此 checkout 為 PASS(乾淨 owned scope),W4 亦 PASS;
    # 否則唯一原因必是「predecessor 不 PASS」,而非任何 W4 自身的謂詞。
    predecessor = validator.derive_wave_exit_status(
        w3, source_admission_receipt=admission, predecessor_wave_receipt=w2,
        predecessor_wave_chain=(w0, w1),
    )
    if predecessor["status"] == "PASS":
        assert result == {"status": "PASS", "reasons": []}
    else:
        assert result["status"] == "NOT_PASS"
        assert all(
            reason.startswith("W4 wave-exit bound predecessor_wave_receipt does not derive PASS")
            for reason in result["reasons"]
        ), result["reasons"]


def test_tampered_w3_predecessor_breaks_the_w4_chain() -> None:
    admission, w0, w1, w2, w3, w4 = _chain()
    forged_w3 = deepcopy(w3)
    forged_w3["owned_path_diff_digest"] = "sha256:" + "e" * 64
    forged_w3["self_digest"] = validator.artifact_self_digest(forged_w3)
    result = _derive(w4, admission, forged_w3, w0, w1, w2)
    assert result["status"] == "NOT_PASS"
    assert any(
        "predecessor_wave_receipt does not derive PASS" in reason
        for reason in result["reasons"]
    )


def test_w4_requires_the_exact_three_element_predecessor_chain() -> None:
    admission, w0, w1, w2, w3, w4 = _chain()
    for chain in ((), (w0,), (w0, w1), (w0, w1, w2, w3)):
        result = validator.derive_wave_exit_status(
            w4,
            source_admission_receipt=admission,
            predecessor_wave_receipt=w3,
            predecessor_wave_chain=chain,
        )
        assert result["status"] == "NOT_PASS"
    # predecessor 物件缺席亦拒。
    assert validator.derive_wave_exit_status(
        w4, source_admission_receipt=admission, predecessor_wave_chain=(w0, w1, w2)
    )["status"] == "NOT_PASS"
    # 綁定的 admission 缺席亦拒。
    assert validator.derive_wave_exit_status(
        w4, predecessor_wave_receipt=w3, predecessor_wave_chain=(w0, w1, w2)
    )["status"] == "NOT_PASS"


def test_w4_predecessor_must_be_the_w3_receipt() -> None:
    admission, w0, w1, w2, w3, w4 = _chain()
    swapped = deepcopy(w4)
    swapped["predecessor_wave_receipt_digest"] = w2["self_digest"]
    swapped["self_digest"] = validator.artifact_self_digest(swapped)
    assert validator.w4_chain_binding_errors(
        swapped, admission, w2, validator._git_head(ROOT)
    )
    assert any(
        "predecessor must be the W3 wave-exit receipt" in reason
        for reason in validator.w4_chain_binding_errors(
            swapped, admission, w2, validator._git_head(ROOT)
        )
    )


def test_w4_self_declared_status_rejected_before_derivation() -> None:
    admission, w0, w1, w2, w3, w4 = _chain()
    for field, value in (("status", "PASS"), ("pass", True), ("done", True),
                         ("admitted", True)):
        forged = deepcopy(w4)
        forged[field] = value
        forged["self_digest"] = validator.artifact_self_digest(forged)
        result = _derive(forged, admission, w3, w0, w1, w2)
        assert result["status"] == "NOT_PASS"
        assert any("must not self-declare status" in reason for reason in result["reasons"])


@pytest.mark.parametrize("field", [
    "owned_path_manifest_digest", "owned_path_diff_digest", "exported_abi_digest",
])
def test_w4_projection_drift_is_not_pass(field) -> None:
    admission, w0, w1, w2, w3, w4 = _chain()
    forged = deepcopy(w4)
    forged[field] = "sha256:" + "a" * 64
    forged["self_digest"] = validator.artifact_self_digest(forged)
    assert validator.w4_structural_errors(forged)
    assert _derive(forged, admission, w3, w0, w1, w2)["status"] == "NOT_PASS"


def test_w4_null_predecessor_digest_is_structurally_rejected() -> None:
    admission, w0, w1, w2, w3, w4 = _chain()
    forged = deepcopy(w4)
    forged["predecessor_wave_receipt_digest"] = None
    forged["self_digest"] = validator.artifact_self_digest(forged)
    assert any(
        "non-null predecessor_wave_receipt_digest" in reason
        for reason in validator.w4_structural_errors(forged)
    )


def test_w4_source_head_must_be_the_current_checkout_head() -> None:
    admission, w0, w1, w2, w3, w4 = _chain()
    forged = deepcopy(w4)
    forged["source_head"] = "b" * 40
    forged["self_digest"] = validator.artifact_self_digest(forged)
    reasons = validator.w4_chain_binding_errors(
        forged, admission, w3, validator._git_head(ROOT)
    )
    assert any("source_head" in reason for reason in reasons)


@pytest.mark.parametrize("field", ["test_digests", "capture_digests", "review_fragment_digests"])
def test_w4_empty_evidence_lists_never_derive_pass(field) -> None:
    admission, w0, w1, w2, w3, _w4 = _chain()
    evidence = deepcopy(_EVID)
    evidence[field] = []
    forged = install.build_w4_wave_exit_receipt(admission, w3, **evidence)
    result = _derive(forged, admission, w3, w0, w1, w2)
    assert result["status"] == "NOT_PASS"


# ── owned paths / exported ABI ──────────────────────────────────────────────────
def test_w4_owned_paths_are_live_and_cover_the_w4a_surface() -> None:
    required = {
        "helper_scripts/maintenance_scripts/agent_governance_s2_4_journal.py",
        "helper_scripts/maintenance_scripts/agent_governance_s2_4_lock.py",
        "helper_scripts/maintenance_scripts/agent_governance_s2_4_permit.py",
        "helper_scripts/maintenance_scripts/agent_governance_s2_4_w4_emit.py",
        "program_code/ml_training/aiml_gate_receipt_s2_4_contracts.py",
        "program_code/ml_training/aiml_gate_receipt_wave_w4.py",
        "program_code/ml_training/schemas/aiml_gate_receipts/"
        "s2_4_operator_authorization_v1.schema.json",
        "tests/structure/test_agent_governance_s2_4_journal.py",
        "tests/structure/test_agent_governance_s2_4_lock.py",
        "tests/structure/test_agent_governance_s2_4_permit.py",
        "tests/structure/test_agent_governance_s2_4_install_w4.py",
    }
    missing = required - set(validator._W4_OWNED_PATHS)
    assert not missing, f"W4 owned-path binding misses W4a surface members: {sorted(missing)}"
    dead = [rel for rel in validator._W4_OWNED_PATHS if not (ROOT / rel).is_file()]
    assert not dead, f"W4 owned paths contain dead entries: {dead}"


def test_w4_exported_abi_projection_folds_the_five_live_verdict_groups() -> None:
    projection = validator.w4_exported_abi_projection()
    permit_live = projection["permit_binding_live"]
    assert permit_live["authorization_id_is_payload_derived"] is True
    assert permit_live["clean_plan_binding_status"] == "PERMIT_PLAN_BINDING_VERIFIED"
    assert permit_live["intent_substitution_status"] == "PERMIT_PLAN_BINDING_REJECTED"
    assert permit_live["legacy_permit_without_payload_binding_status"] == (
        "PERMIT_PLAN_BINDING_REJECTED"
    )
    assert permit_live["payload_binding_field_counts"] == {
        "apply_aggregate": 14, "capability_probe": 11, "pg_migration": 14, "prepare": 10,
    }
    lock_live = projection["lock_live"]
    assert lock_live["source_lane_status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert lock_live["source_lane_mutation_performed"] is False
    assert lock_live["source_lane_driver_engaged"] is False
    assert lock_live["lock_never_unlinked"] is True
    assert lock_live["unlink_surface_rejected"] is True
    journal_live = projection["journal_live"]
    assert journal_live["prepare_journal_path_matches_prepare_leaf"] is True
    assert journal_live["journal_integrity_reobserves"] is True
    assert journal_live["journal_self_and_outer_digests_differ"] is True
    assert journal_live["tampered_journal_breaks_digests"] is True
    assert journal_live["truncated_bytes_status"] == "JOURNAL_CORRUPT_RECOVERY_REQUIRED"
    assert journal_live["reconcile_resume_status"] == "RESUME_VERIFICATION"
    assert journal_live["reconcile_not_applied_status"] == "STEP_NOT_APPLIED_RESUME"
    assert journal_live["reconcile_ambiguous_status"] == "RECOVERY_REQUIRED"
    budget_live = projection["budget_live"]
    assert budget_live["apply_budget_satisfied_status"] == "TTL_BUDGET_SATISFIED"
    assert budget_live["apply_budget_exceeded_status"] == "TTL_BUDGET_EXCEEDED"
    assert budget_live["missing_term_status"] == "TTL_BUDGET_REJECTED"
    assert budget_live["post_expiry_cleanup_status"] == (
        "POST_EXPIRY_SAFETY_CLEANUP_AUTHORIZED"
    )
    assert budget_live["post_expiry_creation_status"] == "POST_EXPIRY_OPERATION_FORBIDDEN"
    assert budget_live["post_expiry_unknown_status"] == "UNKNOWN_OPERATION_FORBIDDEN"
    assert budget_live["expiry_during_apply_status"] == "EXPIRY_DURING_APPLY_COMPENSATE"
    compensation_live = projection["compensation_live"]
    assert compensation_live["applier_self_report_is_not_exact"] is True
    assert compensation_live["independent_confirmation_is_exact"] is True
    assert compensation_live["independent_disproof_is_recovery"] is True
    assert compensation_live["no_verifier_is_unavailable"] is True
    for name in ("journal_abi", "lock_abi", "permit_abi"):
        assert projection[name] is not None


def test_w4_typed_failures_include_the_new_lock_and_journal_statuses() -> None:
    typed = set(validator._W4_EXPORTED_ABI["typed_failures"])
    assert {"INSTALL_LOCK_HELD", "JOURNAL_CORRUPT_RECOVERY_REQUIRED", "PRECHECK_FAILED",
            "AUTHORIZATION_REJECTED", "RECOVERY_REQUIRED"} <= typed


# ── W3 obligation ledger 的誠實移交 ────────────────────────────────────────────
def test_w3_obligations_now_carry_only_the_open_design_question() -> None:
    obligations = validator._W3_EXPORTED_ABI["w4_owned_obligations"]
    assert [row["obligation_id"] for row in obligations] == [
        "ENCRYPTED_BLOB_DIGEST_ORDERING"
    ]
    assert obligations[0]["typed_status"] == "OPEN_DESIGN_QUESTION"
    # W4a 交付的三項不得再被記為「W3 未提供」。
    delivered = {
        "PERMIT_PLAN_BINDING", "REPLAY_LEDGER_APPEND",
        "INDEPENDENT_POST_COMPENSATION_POSTCHECK",
    }
    assert delivered & {row["obligation_id"] for row in obligations} == set()
    # 三項的當前契約明載於 W4 ABI。
    w4_abi = validator._W4_EXPORTED_ABI
    assert "authorization_id = canonical_digest(" in w4_abi["permit_plan_binding_contract"]
    assert "idempotent replay" in w4_abi["replay_append_contract"]
    assert "INDEPENDENT postcheck verifier" in w4_abi["compensation_exactness_contract"]
    # W3 的 compensation 契約文字亦已更新成 W4a 的實際行為(不留過期敘述)。
    assert "INDEPENDENT postcheck verifier" in (
        validator._W3_EXPORTED_ABI["compensation_exactness_contract"]
    )


def test_w4_records_its_own_remaining_obligations_in_the_same_honest_shape() -> None:
    remaining = validator._W4_EXPORTED_ABI["remaining_owned_obligations"]
    ids = [row["obligation_id"] for row in remaining]
    assert "ENCRYPTED_BLOB_DIGEST_ORDERING" in ids
    # W4b 交付的兩項不得再被記為未提供;剩下的每一項都帶 owner wave 與可關閉條件。
    assert {"AGGREGATE_PLAN_PAYLOAD_FULL_COMPARISON", "RUNNER_WAL_LOCK_WIRING"} & set(
        ids
    ) == set()
    assert {
        "OBSERVER_SPACE_PRE_STATE_DIGEST",
        "ATTESTED_EVIDENCE_CLASS_VERIFIER",
        "PRIOR_LINEAGE_ENTRY_IDENTITY",
        "STARTUP_RECONCILE_LANE_PATHS",
    } <= set(ids)
    for row in remaining:
        assert set(row) >= {
            "obligation_id", "typed_status", "owner_wave", "spec_refs", "statement",
            "w4_provides",
        }
        assert row["typed_status"] in {
            "OPEN_DESIGN_QUESTION", "NOT_PROVIDED_BY_W4A", "NOT_PROVIDED_BY_W4B",
            "NOT_PROVIDED_BY_W4", "PARTIALLY_PROVIDED_BY_W4B",
            # Fix-C:verifier 已在源碼線交付,待交付的是**取得**一份真背書(W6B);
            # 另有一條刻意保持開放的 W6-runner 前置,與一條誠實界線。
            "VERIFIER_PROVIDED_BY_W4B_ATTESTATION_PENDING",
            "OPEN_BY_DESIGN_W6_RUNNER_PRECONDITION",
            "OPEN_HONEST_BOUNDARY",
        }
        assert row["owner_wave"] and row["spec_refs"] and row["statement"]
    # OBSERVER_SPACE_PRE_STATE_DIGEST 現在必須說清楚「什麼才算關閉」。
    observer = next(
        row for row in remaining if row["obligation_id"] == "OBSERVER_SPACE_PRE_STATE_DIGEST"
    )
    assert "What would close it" in observer["statement"]
    assert observer["typed_status"] == "PARTIALLY_PROVIDED_BY_W4B"


def test_w4_abi_folds_the_w4b_aggregate_contracts() -> None:
    abi = validator._W4_EXPORTED_ABI
    assert "apply_s2_4_install_plan(plan, authorization_set, driver)" in (
        abi["aggregate_transaction_contract"]
    )
    assert "APPLIED_INACTIVE" in abi["success_identity_contract"]
    assert "SOURCE_SIMULATION_PASS" in abi["success_identity_contract"]
    assert "no digest/signature cycle".replace("no ", "") in (
        abi["plan_intent_binding_contract"]
    )
    assert "zero uncompared fields" in abi["aggregate_payload_comparison_contract"]
    assert "reverse order" in abi["reverse_compensation_contract"]
    assert "RECOVERY_REQUIRED with zero new mutation" in abi["startup_reconcile_contract"]
    assert "JournalRoutedDriver" in abi["runner_wal_lock_wiring_contract"]


def test_w4_projection_folds_the_aggregate_and_reconcile_live_groups() -> None:
    projection = validator.w4_exported_abi_projection()
    assert projection["install_driver_abi"] is not None
    aggregate = projection["aggregate_live"]
    assert aggregate["malformed_plan_status"] == "PRECHECK_FAILED"
    assert aggregate["malformed_plan_mutation_performed"] is False
    assert aggregate["success_identity"] == "APPLIED_INACTIVE"
    assert aggregate["source_lane_identity"] == "SOURCE_SIMULATION_PASS"
    assert aggregate["apply_row_step_index"] == {
        "HOST_IDENTITY_INSTALL": 0, "PG_ROLE_ACL_MIGRATION": 1, "CREDENTIAL_INSTALL": 2,
        "LEARNING_RUNTIME": 3, "ENGINE_SCANNER": 5,
    }
    assert aggregate["payload_comparison_complete"] == {
        "apply_aggregate": True, "pg_migration": True
    }
    assert aggregate["payload_uncompared_fields"] == {
        "apply_aggregate": [], "pg_migration": []
    }
    assert aggregate["binding_ignores_self_referential_fields"] is True
    assert aggregate["binding_pins_every_other_field"] is True
    assert aggregate["forbidden_aggregate_surface_rejected"] is True
    assert aggregate["typed_statuses_within_receipt_enum"] is True
    reconcile = projection["reconcile_live"]
    assert reconcile["lock_required_status"] == "INSTALL_LOCK_REQUIRED"
    assert reconcile["source_lane_status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert reconcile["source_lane_admits_new_work"] is False
    assert reconcile["no_paths_status"] == "RECOVERY_REQUIRED"
    assert reconcile["admits_new_work_only_for"] == [
        "STARTUP_RECONCILE_CLEAN", "STARTUP_RECONCILE_STEP_NOT_APPLIED"
    ]
    assert reconcile["routed_without_lock_refused"] is True


def test_w4_owned_paths_cover_the_w4b_surface() -> None:
    required = {
        "helper_scripts/maintenance_scripts/agent_governance_s2_4_install_driver.py",
        "helper_scripts/maintenance_scripts/agent_governance_s2_4_reconcile.py",
        "tests/structure/s2_4_w4b_testkit.py",
        "tests/structure/test_agent_governance_s2_4_install_driver.py",
        "tests/structure/test_agent_governance_s2_4_crash_matrix.py",
        "tests/structure/test_agent_governance_s2_4_pre_state_matrix.py",
    }
    missing = required - set(validator._W4_OWNED_PATHS)
    assert not missing, f"W4 owned-path binding misses W4b surface members: {sorted(missing)}"


# ── w4-emit(不實跑發射)────────────────────────────────────────────────────────
def test_w4_emit_cli_out_dir_is_constrained_to_the_receipts_directory(tmp_path, capsys) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(_TEST_EVIDENCE), encoding="utf-8")
    provenance = tmp_path / "provenance.json"
    provenance.write_text(json.dumps(_REVIEW_PROVENANCE), encoding="utf-8")
    exit_code = install._main([
        "w4-emit",
        "--out", str(tmp_path / "escaped"),
        "--test-evidence", str(evidence),
        "--review-provenance", str(provenance),
    ])
    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["stage"] == "out_dir"
    assert "receipts" in payload["reasons"][0]
    assert not (tmp_path / "escaped").exists()
    inside = install.RECEIPTS_ROOT / install.W4_RECEIPT_DIRNAME
    assert install._resolve_cli_out_dir(inside) == inside.resolve()


def test_w4_emit_refuses_when_persisted_w3_lineage_is_tampered(tmp_path) -> None:
    source_dir = install.W3_RECEIPT_DIR
    lineage = install._load_persisted_w3_receipts(source_dir)
    assert lineage is not None and lineage["historical_w3_integrity"] == "VERIFIED"
    for name in sorted(p.name for p in source_dir.glob("*.json")):
        (tmp_path / name).write_text(
            (source_dir / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    target = tmp_path / "S2.4-WP4-W3-wave-exit-receipt-v1.json"
    tampered = json.loads(target.read_text(encoding="utf-8"))
    tampered["source_head"] = "c" * 40
    target.write_text(json.dumps(tampered), encoding="utf-8")
    out_dir = tmp_path / "out"
    result = install.emit_w4_receipts(
        out_dir=out_dir,
        test_evidence=dict(_TEST_EVIDENCE),
        review_provenance=[dict(item) for item in _REVIEW_PROVENANCE],
        w3_receipt_dir=tmp_path,
    )
    assert result["status"] == "W4_EMIT_REFUSED"
    assert result["stage"] == "historical_w3_receipts"
    assert not out_dir.exists()


def test_w4_emit_refuses_when_the_persisted_w3_lineage_is_missing(tmp_path) -> None:
    out_dir = tmp_path / "out"
    result = install.emit_w4_receipts(
        out_dir=out_dir,
        test_evidence=dict(_TEST_EVIDENCE),
        review_provenance=[dict(item) for item in _REVIEW_PROVENANCE],
        w3_receipt_dir=tmp_path / "absent",
    )
    assert result["status"] == "W4_EMIT_REFUSED"
    assert result["stage"] == "historical_w3_receipts"
    assert not out_dir.exists()


def test_w4_emit_refuses_and_writes_nothing_when_the_chain_does_not_derive(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        validator,
        "derive_wave_exit_status",
        lambda receipt, **kwargs: {"status": "NOT_PASS", "reasons": ["forced-for-fail-closed"]},
    )
    out_dir = tmp_path / "out"
    result = install.emit_w4_receipts(
        out_dir=out_dir,
        test_evidence=dict(_TEST_EVIDENCE),
        review_provenance=[dict(item) for item in _REVIEW_PROVENANCE],
    )
    assert result["status"] == "W4_EMIT_REFUSED"
    assert result["reasons"] == ["forced-for-fail-closed"]
    assert not out_dir.exists()


def test_install_module_reexports_the_w4a_surface() -> None:
    for name in (
        "build_w4_wave_exit_receipt",
        "emit_w4_receipts",
        "W4_RECEIPT_DIRNAME",
        "W4_WAVE_EXIT_FILENAME",
        "W4_REGENERATED_W3_WAVE_EXIT_FILENAME",
    ):
        assert hasattr(install, name), name
    for name in (
        "_W4_OWNED_PATHS", "_W4_EXPORTED_ABI", "w4_structural_errors",
        "w4_chain_binding_errors", "w4_exported_abi_projection", "w4_owned_path_diff_digest",
        "derive_permit_plan_binding_status", "derive_authorization_id",
        "authorization_payload_binding_fields", "build_s2_4_operator_authorization",
        "s2_4_authorization_identity_digest",
    ):
        assert hasattr(validator, name), name


# ── E2:W4 ABI 對 attestation verifier 的 w4_provides 曾宣稱一件測試沒證明的事 ──
def test_w4_abi_no_longer_claims_the_positive_test_proves_the_only_half() -> None:
    """``w4_provides`` 曾寫「a throwaway-key positive test proving APPLIED_INACTIVE is
    reachable ONLY with a valid attestation」。正例證明的是**可達**;「只有」那一半在
    W4b 交付時沒有任何測試支持——六個負向全部改欄位再重簽,所以每個都被欄位比對抓住,
    ``_verify_ssh_signature`` 那一行零覆蓋。修正後的文字必須明載那兩支只有驗簽能擋的負向。
    """

    obligations = {
        item["obligation_id"]: item
        for item in validator._W4_EXPORTED_ABI["remaining_owned_obligations"]
    }
    provides = obligations["ATTESTED_EVIDENCE_CLASS_VERIFIER"]["w4_provides"]
    assert "POSITIVE test proving APPLIED_INACTIVE is REACHABLE" in provides
    assert "FOREIGN throwaway key" in provides
    assert "garbage SSHSIG bytes" in provides
    # 誠實的自我更正必須留在 ABI 上,而不是靜默改掉。
    assert "Correction" in provides and "ZERO coverage" in provides


@pytest.mark.parametrize("obligation_id", [
    "ATTESTOR_KEY_IS_NOT_SEPARATE_FROM_THE_PERMIT_KEY",
    "ATTESTATION_EXPIRY_AND_HOST_TIME_ARE_NOT_CROSS_CHECKED",
    "RECEIPT_EMISSION_PENDING_IS_NOT_A_RECEIPT_RETRY",
    "STARTUP_JOURNAL_PARENTS_MUST_PREEXIST",
    "STRANDED_WAL_TEMP_FILES_ARE_REPORT_ONLY",
])
def test_w4_records_the_new_open_obligations_in_the_same_honest_shape(obligation_id) -> None:
    """E2/E9/E17 + 兩則「記錄而非默默接受」的觀察必須以同一個 typed 形狀留在 ABI 上。"""

    obligations = {
        item["obligation_id"]: item
        for item in validator._W4_EXPORTED_ABI["remaining_owned_obligations"]
    }
    entry = obligations[obligation_id]
    assert entry["typed_status"] in {
        "NOT_PROVIDED_BY_W4B", "PARTIALLY_PROVIDED_BY_W4B",
    }
    assert entry["owner_wave"] == "W6B"
    assert entry["spec_refs"]
    assert len(entry["statement"]) > 200
    assert entry["w4_provides"]


def test_w4_abi_states_the_probe_core_binding_is_mandatory_for_the_w6_runner() -> None:
    """E8:綁定被略過必須可稽核,而「W6 runner 必須遞交」必須是白紙黑字的義務。"""

    obligations = {
        item["obligation_id"]: item
        for item in validator._W4_EXPORTED_ABI["remaining_owned_obligations"]
    }
    statement = obligations["INSTALLED_UNIT_PROBE_CORE_BINDING"]["statement"]
    assert "MANDATORY for the W6 runner" in statement
    assert "UNVERIFIED_NO_EXPECTED_VALUE_SUPPLIED" in statement


# ── E7:Registry 的 invariant 是 normative-policy 面,不得留下已不成立的敘述 ──
def test_registry_install_adapter_invariant_states_custody_not_unreachability() -> None:
    """E7:``a valid signature alone never yields an applied/production status in the source
    lane`` 在 ``derive_recorded_evidence_class`` 無條件拒收的時代是**構造性**為真的。W4b 之後
    ``APPLIED_INACTIVE`` 在 in-memory 線上只要 patch 兩個 facade 屬性並遞交一份合法簽章的
    attestation 就可達,真實世界的保證改由**金鑰保管**提供。Registry 是 normative-policy 面,
    所以那句話必須被重述,而不是留著。"""

    registry = json.loads(
        (ROOT / ".codex/agent_registry_v1.json").read_text(encoding="utf-8")
    )
    adapters = registry["effect_adapters"]
    entry = adapters["s2_4_install_adapter_v1"]
    assert entry["status"] == "AUTHORITY_LOCKED_PRODUCTION_CAPABLE"
    invariant = entry["invariant"]
    # 舊的、已不成立的敘述必須消失。
    assert (
        "a valid signature alone never yields an applied/production status in the source lane"
        not in invariant
    )
    # 新敘述必須同時說出兩件事:構造性不可達已不成立,以及真保證是金鑰保管。
    assert "NO LONGER structurally unreachable" in invariant
    assert "KEY CUSTODY" in invariant
    assert "a valid operator PERMIT signature alone never yields" in invariant
    assert "nine authorities stay false even on APPLIED_INACTIVE" in invariant
    assert "s2_4_install_apply_attestation_v1" in entry["authority"]
    # 另兩支 adapter 的構造性敘述**仍然**成立,不得被順手改掉。
    for other in ("s2_4_capability_probe_adapter_v1", "s2_4_prepare_adapter_v1"):
        assert adapters[other]["status"] == "AUTHORITY_LOCKED_PRODUCTION_CAPABLE"
        assert (
            "a valid signature alone never yields an applied/production status in the source "
            "lane" in adapters[other]["invariant"]
        ), other
