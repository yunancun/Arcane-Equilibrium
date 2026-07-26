"""S2.4(WP4·W3)wave-exit 中央導出與 w3-emit 發射器的 focused 測試(§10.3 W3 row)。

證明:
- W0→W1→W2→W3 完整鏈於當前 checkout 再導出 PASS(predecessor=W2 物件 +
  ``predecessor_wave_chain=(W0, W1)``);
- 竄改鏈上任一環(W2 receipt / W3 predecessor digest / owned-path 或 ABI 投影 /
  非當前 HEAD / caller 自證 status / 缺 chain)一律 NOT_PASS(§10.5 #27);
- W3 exported-ABI 投影折入的六個活裁決確實可再導出(probe source-lane 零變更、
  route-surface 拒 builder 權限、scope 替換拒、topology PROVEN/UNPROVEN、guard 欄位契約);
- W3 owned-path 集合每一條都真實存在(pin 不得腐化成死路徑);
- ``w3-emit`` CLI 的 ``--out`` 同樣受限於 repo receipts 目錄(不實跑發射)。
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
    "command": "python3 -m pytest tests/structure/test_agent_governance_s2_4_probe.py -q",
    "exit_code": 0,
    "summary": "unit-test placeholder evidence for W3 emitter behaviour tests",
}
_REVIEW_PROVENANCE = [{"pr": 999, "merge_head": "f" * 40, "verdict": "test-fixture"}]


def _chain():
    admission = install.build_w0_source_admission_receipt(ROOT)
    w0 = install.build_w0_wave_exit_receipt(admission, **deepcopy(_EVID))
    w1 = install.build_w1_wave_exit_receipt(admission, w0, **deepcopy(_EVID))
    w2 = install.build_w2_wave_exit_receipt(admission, w1, **deepcopy(_EVID))
    w3 = install.build_w3_wave_exit_receipt(admission, w2, **deepcopy(_EVID))
    return admission, w0, w1, w2, w3


def _derive(w3, admission, w2, w0, w1):
    return validator.derive_wave_exit_status(
        w3,
        source_admission_receipt=admission,
        predecessor_wave_receipt=w2,
        predecessor_wave_chain=(w0, w1),
    )


def test_w3_wave_exit_derives_pass_with_the_full_w0_w1_w2_chain() -> None:
    admission, w0, w1, w2, w3 = _chain()
    assert _derive(w3, admission, w2, w0, w1) == {"status": "PASS", "reasons": []}
    # evidence-only:無任何 caller-status 鍵;中央閘結構驗亦全過。
    assert not any(key in w3 for key in validator._CALLER_STATUS_KEYS)
    assert validator.validate_aiml_artifact(w3) == []
    assert w3["wave"] == "W3"
    assert w3["production_authority_flags"] == {
        "nine_authorities_false": True,
        "production_apply_performed": False,
        "running_attested": False,
    }


def test_tampered_w2_predecessor_breaks_the_w3_chain() -> None:
    admission, w0, w1, w2, w3 = _chain()
    forged_w2 = deepcopy(w2)
    forged_w2["owned_path_diff_digest"] = "sha256:" + "e" * 64
    forged_w2["self_digest"] = validator.artifact_self_digest(forged_w2)
    result = _derive(w3, admission, forged_w2, w0, w1)
    assert result["status"] == "NOT_PASS"
    assert any(
        "predecessor_wave_receipt does not derive PASS" in reason
        for reason in result["reasons"]
    )


def test_w3_requires_the_exact_two_element_predecessor_chain() -> None:
    admission, w0, w1, w2, w3 = _chain()
    for chain in ((), (w0,), (w0, w1, w2)):
        result = validator.derive_wave_exit_status(
            w3,
            source_admission_receipt=admission,
            predecessor_wave_receipt=w2,
            predecessor_wave_chain=chain,
        )
        assert result["status"] == "NOT_PASS"
    # predecessor 物件缺席亦拒。
    assert validator.derive_wave_exit_status(
        w3, source_admission_receipt=admission, predecessor_wave_chain=(w0, w1)
    )["status"] == "NOT_PASS"


def test_w3_predecessor_must_be_the_w2_receipt() -> None:
    admission, w0, w1, w2, w3 = _chain()
    swapped = deepcopy(w3)
    swapped["predecessor_wave_receipt_digest"] = w1["self_digest"]
    swapped["self_digest"] = validator.artifact_self_digest(swapped)
    result = validator.derive_wave_exit_status(
        swapped,
        source_admission_receipt=admission,
        predecessor_wave_receipt=w1,
        predecessor_wave_chain=(w0, w1),
    )
    assert result["status"] == "NOT_PASS"


def test_w3_self_declared_status_rejected_before_derivation() -> None:
    admission, w0, w1, w2, w3 = _chain()
    for field, value in (("status", "PASS"), ("pass", True), ("done", True)):
        forged = deepcopy(w3)
        forged[field] = value
        forged["self_digest"] = validator.artifact_self_digest(forged)
        result = _derive(forged, admission, w2, w0, w1)
        assert result["status"] == "NOT_PASS"
        assert any("must not self-declare status" in reason for reason in result["reasons"])


@pytest.mark.parametrize("field", [
    "owned_path_manifest_digest", "owned_path_diff_digest", "exported_abi_digest",
])
def test_w3_projection_drift_is_not_pass(field) -> None:
    admission, w0, w1, w2, w3 = _chain()
    forged = deepcopy(w3)
    forged[field] = "sha256:" + "a" * 64
    forged["self_digest"] = validator.artifact_self_digest(forged)
    assert _derive(forged, admission, w2, w0, w1)["status"] == "NOT_PASS"


def test_w3_source_head_must_be_the_current_checkout_head() -> None:
    admission, w0, w1, w2, w3 = _chain()
    forged = deepcopy(w3)
    forged["source_head"] = "b" * 40
    forged["self_digest"] = validator.artifact_self_digest(forged)
    result = _derive(forged, admission, w2, w0, w1)
    assert result["status"] == "NOT_PASS"
    assert any("source_head" in reason for reason in result["reasons"])


def test_w3_owned_paths_are_live_and_cover_the_w3a_surface() -> None:
    required = {
        "helper_scripts/maintenance_scripts/agent_governance_s2_4_probe.py",
        "helper_scripts/maintenance_scripts/agent_governance_s2_4_topology.py",
        "helper_scripts/maintenance_scripts/agent_governance_s2_4_w3_emit.py",
        "program_code/ml_training/aiml_gate_receipt_wave_w3.py",
        "program_code/ml_training/alr_consumer_resilience.py",
        "tests/structure/test_agent_governance_s2_4_probe.py",
        "tests/structure/test_agent_governance_s2_4_topology.py",
        "tests/structure/test_agent_governance_s2_4_install_w3.py",
    }
    missing = required - set(validator._W3_OWNED_PATHS)
    assert not missing, f"W3 owned-path binding misses W3a surface members: {sorted(missing)}"
    dead = [rel for rel in validator._W3_OWNED_PATHS if not (ROOT / rel).is_file()]
    assert not dead, f"W3 owned paths contain dead entries: {dead}"


def test_w3_exported_abi_projection_folds_the_six_live_verdicts() -> None:
    projection = validator.w3_exported_abi_projection()
    probe_live = projection["probe_live"]
    assert probe_live["source_lane_mutation_performed"] is False
    assert probe_live["source_lane_driver_engaged"] is False
    assert probe_live["source_lane_blocks_next_phase"] is True
    assert probe_live["source_lane_status"] in {
        "AUTHORIZATION_REJECTED", "EXTERNAL_VERIFICATION_PENDING", "PROBE_REQUEST_REJECTED"
    }
    assert probe_live["builder_authority_route_status"] == "PROBE_ROUTE_SURFACE_REJECTED"
    assert probe_live["scope_property_digests_differ"] is True
    assert probe_live["cross_scope_input_rejected"] is True
    topology_live = projection["topology_live"]
    assert topology_live["clean_status"] == "PG_TOPOLOGY_PROVEN"
    assert topology_live["listener_drift_status"] == "PG_TOPOLOGY_UNPROVEN"
    assert topology_live["guard_row_digest_matches_consumer_contract"] is True
    # §8.3:final-unit attestation 永非 W6A 前置。
    assert projection["probe_abi"]["w6a_prerequisite_probe_scopes"] == ["PREPARE_SANDBOX"]
    assert projection["probe_abi"]["w6b_prerequisite_probe_scopes"] == [
        "PREPARE_SANDBOX", "INSTALLED_UNIT"
    ]


def test_w4_and_beyond_remain_fail_closed() -> None:
    admission, w0, w1, w2, w3 = _chain()
    forged = deepcopy(w3)
    forged["wave"] = "W4"
    forged["self_digest"] = validator.artifact_self_digest(forged)
    result = _derive(forged, admission, w2, w0, w1)
    assert result["status"] == "NOT_PASS"
    assert any(
        "only implemented for W0/W1/W2/W3" in reason for reason in result["reasons"]
    )


def test_w3_emit_cli_out_dir_is_constrained_to_the_receipts_directory(tmp_path, capsys) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(_TEST_EVIDENCE), encoding="utf-8")
    provenance = tmp_path / "provenance.json"
    provenance.write_text(json.dumps(_REVIEW_PROVENANCE), encoding="utf-8")
    exit_code = install._main([
        "w3-emit",
        "--out", str(tmp_path / "escaped"),
        "--test-evidence", str(evidence),
        "--review-provenance", str(provenance),
    ])
    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["stage"] == "out_dir"
    assert "receipts" in payload["reasons"][0]
    assert not (tmp_path / "escaped").exists()
    inside = install.RECEIPTS_ROOT / install.W3_RECEIPT_DIRNAME
    assert install._resolve_cli_out_dir(inside) == inside.resolve()


def test_w3_emit_refuses_when_persisted_w2_lineage_is_tampered(tmp_path) -> None:
    source_dir = install.W2_RECEIPT_DIR
    lineage = install._load_persisted_w2_receipts(source_dir)
    assert lineage is not None and lineage["historical_w2_integrity"] == "VERIFIED"
    # 竄改一份持久化 W2 receipt → self-digest 驗證失敗 → 硬拒發射且零寫檔。
    for name in sorted(p.name for p in source_dir.glob("*.json")):
        (tmp_path / name).write_text(
            (source_dir / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    target = tmp_path / "S2.4-WP4-W2-wave-exit-receipt-v1.json"
    tampered = json.loads(target.read_text(encoding="utf-8"))
    tampered["source_head"] = "c" * 40
    target.write_text(json.dumps(tampered), encoding="utf-8")
    out_dir = tmp_path / "out"
    result = install.emit_w3_receipts(
        out_dir=out_dir,
        test_evidence=dict(_TEST_EVIDENCE),
        review_provenance=[dict(item) for item in _REVIEW_PROVENANCE],
        w2_receipt_dir=tmp_path,
    )
    assert result["status"] == "W3_EMIT_REFUSED"
    assert result["stage"] == "historical_w2_receipts"
    assert not out_dir.exists()


def test_w3_emit_refuses_and_writes_nothing_when_the_chain_does_not_derive(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        validator,
        "derive_wave_exit_status",
        lambda receipt, **kwargs: {"status": "NOT_PASS", "reasons": ["forced-for-fail-closed"]},
    )
    out_dir = tmp_path / "out"
    result = install.emit_w3_receipts(
        out_dir=out_dir,
        test_evidence=dict(_TEST_EVIDENCE),
        review_provenance=[dict(item) for item in _REVIEW_PROVENANCE],
    )
    assert result["status"] == "W3_EMIT_REFUSED"
    assert result["reasons"] == ["forced-for-fail-closed"]
    assert not out_dir.exists()


def test_install_module_reexports_the_w3a_surface() -> None:
    for name in (
        "run_s2_4_capability_probe",
        "CapabilityProbeDriver",
        "ProbeRecoveryState",
        "derive_scoped_capability_attestation_status",
        "derive_probe_phase_prerequisite_status",
        "observe_pg_topology",
        "derive_pg_topology_status",
        "build_pg_topology_runtime_guard",
        "build_w3_wave_exit_receipt",
        "emit_w3_receipts",
    ):
        assert hasattr(install, name), name
