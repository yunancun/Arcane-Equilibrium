"""S2.4(WP4)install 治理模組——W0 正式 receipt 發射器的 focused 測試。

證明:
- 發射器產出的 receipt 是 evidence-only(無任何 caller status 鍵),
  ADMITTED/PASS 恆由中央 validator 從 repo 再導出;
- 成功發射時三個持久化物落盤,且 admission/wave-exit 均可獨立重驗;
- 任一導出非 ADMITTED/PASS 時 fail-closed:回 typed refusal 且「不」寫任何檔;
- 空 evidence 直接拒絕(不能以空殼 digest 佯裝證據)。
"""
from __future__ import annotations

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

import agent_governance_s2_4_install as install  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402


_TEST_EVIDENCE = {
    "command": "python3 -m pytest tests/structure/test_s2_4_w0_admission.py -q",
    "exit_code": 0,
    "summary": "unit-test placeholder evidence for emitter behavior tests",
}
_REVIEW_PROVENANCE = [
    {"pr": 136, "merge_head": "f" * 40, "verdict": "test-fixture"},
]


def test_emitted_receipts_are_evidence_only_and_centrally_derivable(tmp_path) -> None:
    result = install.emit_w0_receipts(
        out_dir=tmp_path,
        test_evidence=dict(_TEST_EVIDENCE),
        review_provenance=[dict(item) for item in _REVIEW_PROVENANCE],
    )
    assert result["status"] == "W0_RECEIPTS_EMITTED"
    admission = json.loads(
        (tmp_path / install.W0_ADMISSION_FILENAME).read_text(encoding="utf-8")
    )
    wave_exit = json.loads(
        (tmp_path / install.W0_WAVE_EXIT_FILENAME).read_text(encoding="utf-8")
    )
    record = json.loads(
        (tmp_path / install.W0_DERIVATION_RECORD_FILENAME).read_text(encoding="utf-8")
    )
    # evidence-only:兩份 receipt 皆不含任何 caller-status 鍵
    for receipt in (admission, wave_exit):
        assert not any(key in receipt for key in validator._CALLER_STATUS_KEYS)
    # 中央再導出可獨立重驗
    assert validator.derive_source_admission_status(admission) == {
        "status": "ADMITTED",
        "reasons": [],
    }
    assert validator.derive_wave_exit_status(
        wave_exit, source_admission_receipt=admission
    ) == {"status": "PASS", "reasons": []}
    assert validator.validate_aiml_artifact(admission) == []
    assert validator.validate_aiml_artifact(wave_exit) == []
    # derivation record 綁定同一 head 與雙導出結果
    assert record["source_head"] == admission["source_head"]
    assert record["admission_derivation"]["status"] == "ADMITTED"
    assert record["wave_exit_derivation"]["status"] == "PASS"
    # 真實證據原樣持久化(digest 可重算)
    assert record["test_evidence"] == _TEST_EVIDENCE
    assert wave_exit["test_digests"] == [validator.canonical_digest(_TEST_EVIDENCE)]


def test_emit_refuses_and_writes_nothing_when_admission_not_admitted(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        validator,
        "derive_source_admission_status",
        lambda receipt, *, repo_root=None, now=None: {
            "status": "NOT_ADMITTED",
            "reasons": ["forced-for-fail-closed-branch"],
        },
    )
    result = install.emit_w0_receipts(
        out_dir=tmp_path,
        test_evidence=dict(_TEST_EVIDENCE),
        review_provenance=[dict(item) for item in _REVIEW_PROVENANCE],
    )
    assert result == {
        "status": "W0_EMIT_REFUSED",
        "stage": "source_admission",
        "reasons": ["forced-for-fail-closed-branch"],
    }
    assert list(tmp_path.iterdir()) == []


def test_emit_refuses_and_writes_nothing_when_wave_exit_not_pass(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        validator,
        "derive_wave_exit_status",
        lambda receipt, *, repo_root=None, now=None, source_admission_receipt=None: {
            "status": "NOT_PASS",
            "reasons": ["forced-for-fail-closed-branch"],
        },
    )
    result = install.emit_w0_receipts(
        out_dir=tmp_path,
        test_evidence=dict(_TEST_EVIDENCE),
        review_provenance=[dict(item) for item in _REVIEW_PROVENANCE],
    )
    assert result == {
        "status": "W0_EMIT_REFUSED",
        "stage": "wave_exit",
        "reasons": ["forced-for-fail-closed-branch"],
    }
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "test_evidence,review_provenance",
    [
        ({}, [{"pr": 1}]),
        (None, [{"pr": 1}]),
        ({"ok": 1}, []),
        ({"ok": 1}, [{}]),
        ({"ok": 1}, ["not-an-object"]),
    ],
)
def test_emit_rejects_empty_or_malformed_evidence(
    tmp_path, test_evidence, review_provenance
) -> None:
    with pytest.raises(ValueError):
        install.emit_w0_receipts(
            out_dir=tmp_path,
            test_evidence=test_evidence,
            review_provenance=review_provenance,
        )
    assert list(tmp_path.iterdir()) == []


def test_w0_owned_paths_cover_the_post_split_validator_family() -> None:
    """E2 P1-2 回歸:2000 行拆分後 W0 owned-path 綁定必須覆蓋 validator 全家族。

    否則對 leaf 模組或測試 sibling 的削弱性修改不會改變 wave-exit 的
    owned_path_diff_digest,治理不變量的覆蓋面被靜默收窄。
    """

    required = {
        "program_code/ml_training/aiml_gate_receipt_adoption.py",
        "program_code/ml_training/aiml_gate_receipt_classifiers.py",
        "program_code/ml_training/aiml_gate_receipt_s2_4_contracts.py",
        "program_code/ml_training/aiml_gate_receipt_schema_core.py",
        "program_code/ml_training/aiml_gate_receipt_validator.py",
        "program_code/ml_training/tests/aiml_gate_receipt_validator_testkit.py",
        "program_code/ml_training/tests/test_aiml_gate_receipt_validator.py",
        "program_code/ml_training/tests/test_aiml_gate_receipt_validator_adoption.py",
        "program_code/ml_training/tests/test_aiml_gate_receipt_validator_s2_4.py",
    }
    missing = required - set(validator._W0_OWNED_PATHS)
    assert not missing, f"W0 owned-path binding misses split family members: {sorted(missing)}"
    # 每一個 pinned 路徑都必須真實存在(防呆:改名/移動後 pin 變成死路徑)。
    dead = [p for p in validator._W0_OWNED_PATHS if not (ROOT / p).is_file()]
    assert not dead, f"W0 owned paths contain dead entries: {dead}"
