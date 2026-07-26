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
    assert {
        "AGGREGATE_PLAN_PAYLOAD_FULL_COMPARISON",
        "OBSERVER_SPACE_PRE_STATE_DIGEST",
        "RUNNER_WAL_LOCK_WIRING",
    } <= set(ids)
    for row in remaining:
        assert set(row) >= {
            "obligation_id", "typed_status", "owner_wave", "spec_refs", "statement",
            "w4_provides",
        }
        assert row["typed_status"] in {"OPEN_DESIGN_QUESTION", "NOT_PROVIDED_BY_W4A"}
        assert row["owner_wave"] and row["spec_refs"] and row["statement"]


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
