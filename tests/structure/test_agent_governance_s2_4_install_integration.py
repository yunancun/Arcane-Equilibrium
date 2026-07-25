"""S2.4(WP4·W1)w1-emit 整合測試——正式 W1 receipt 發射鏈的 happy path + 拒絕分支。

證明(鏡 w0-emit 測試姿態;mock 只用來「逼出拒絕」,絕不 mock 出成功):
- w1-emit 於活 repo 重算:記憶體重發「當前世代」W0 admission+wave-exit(同 builder)、
  綁定該鏈構建 W1 wave-exit、由中央 validator 導出 PASS 後才持久化四個檔;
- 歷史持久化 W0 receipts 的 digests 記入 derivation record 作 lineage(其 source_head 為
  歷史世代,「不」直接進 derivation 鏈);
- 任一段導出非 ADMITTED/PASS → typed refusal 且「不」寫任何檔(fail-closed);
- 歷史 W0 receipts 缺失/畸形 → typed refusal;
- 空/畸形 evidence 直接 ValueError。
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
    "command": "python3 -m pytest tests/structure/test_agent_governance_s2_4_install.py -q",
    "exit_code": 0,
    "summary": "unit-test placeholder evidence for w1 emitter behavior tests",
}
_REVIEW_PROVENANCE = [
    {"pr": 140, "merge_head": "e" * 40, "verdict": "test-fixture"},
]


def _emit(tmp_path, **overrides):
    kwargs = {
        "out_dir": tmp_path,
        "test_evidence": dict(_TEST_EVIDENCE),
        "review_provenance": [dict(item) for item in _REVIEW_PROVENANCE],
    }
    kwargs.update(overrides)
    return install.emit_w1_receipts(**kwargs)


def test_w1_emit_happy_path_persists_and_rederives(tmp_path) -> None:
    result = _emit(tmp_path)
    assert result["status"] == "W1_RECEIPTS_EMITTED", result
    w1 = json.loads(
        (tmp_path / install.W1_WAVE_EXIT_FILENAME).read_text(encoding="utf-8")
    )
    admission = json.loads(
        (tmp_path / install.W1_REGENERATED_W0_ADMISSION_FILENAME).read_text(
            encoding="utf-8"
        )
    )
    w0 = json.loads(
        (tmp_path / install.W1_REGENERATED_W0_WAVE_EXIT_FILENAME).read_text(
            encoding="utf-8"
        )
    )
    record = json.loads(
        (tmp_path / install.W1_DERIVATION_RECORD_FILENAME).read_text(encoding="utf-8")
    )
    # evidence-only:三份 receipt 皆無 caller-status 鍵。
    for receipt in (admission, w0, w1):
        assert not any(key in receipt for key in validator._CALLER_STATUS_KEYS)
    # 持久化後可獨立重驗完整 W1 鏈(predecessor + admission 雙綁定)。
    assert validator.derive_wave_exit_status(
        w1, source_admission_receipt=admission, predecessor_wave_receipt=w0
    ) == {"status": "PASS", "reasons": []}
    assert validator.validate_aiml_artifact(w1) == []
    # 世代分離:derivation 綁「當前」HEAD;歷史持久化 W0 只作 lineage 記錄。
    assert w1["wave"] == "W1"
    assert w1["predecessor_wave_receipt_digest"] == w0["self_digest"]
    assert w1["source_head"] == admission["source_head"] == record["source_head"]
    historical = record["historical_persisted_w0"]
    persisted_admission = json.loads(
        (install.W0_RECEIPT_DIR / install.W0_ADMISSION_FILENAME).read_text(
            encoding="utf-8"
        )
    )
    assert historical["admission_self_digest"] == persisted_admission["self_digest"]
    assert historical["historical_source_head"] == persisted_admission["source_head"]
    # production 授權旗標恆 false(source lane 無 runtime/production 宣稱)。
    assert w1["production_authority_flags"] == {
        "nine_authorities_false": True,
        "production_apply_performed": False,
        "running_attested": False,
    }
    # 真實證據原樣持久化且 digest 可重算。
    assert record["test_evidence"] == _TEST_EVIDENCE
    assert w1["test_digests"] == [validator.canonical_digest(_TEST_EVIDENCE)]


def test_w1_emit_refuses_when_regenerated_admission_not_admitted(
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
    result = _emit(tmp_path)
    assert result == {
        "status": "W1_EMIT_REFUSED",
        "stage": "regenerated_w0_admission",
        "reasons": ["forced-for-fail-closed-branch"],
    }
    assert list(tmp_path.iterdir()) == []


def test_w1_emit_refuses_when_regenerated_w0_wave_exit_not_pass(
    tmp_path, monkeypatch
) -> None:
    original = validator.derive_wave_exit_status

    def _fail_w0_only(receipt, **kwargs):
        if isinstance(receipt, dict) and receipt.get("wave") == "W0":
            return {"status": "NOT_PASS", "reasons": ["forced-w0-fail"]}
        return original(receipt, **kwargs)

    monkeypatch.setattr(validator, "derive_wave_exit_status", _fail_w0_only)
    result = _emit(tmp_path)
    assert result == {
        "status": "W1_EMIT_REFUSED",
        "stage": "regenerated_w0_wave_exit",
        "reasons": ["forced-w0-fail"],
    }
    assert list(tmp_path.iterdir()) == []


def test_w1_emit_refuses_when_w1_wave_exit_not_pass(tmp_path, monkeypatch) -> None:
    original = validator.derive_wave_exit_status

    def _fail_w1_only(receipt, **kwargs):
        if isinstance(receipt, dict) and receipt.get("wave") == "W1":
            return {"status": "NOT_PASS", "reasons": ["forced-w1-fail"]}
        return original(receipt, **kwargs)

    monkeypatch.setattr(validator, "derive_wave_exit_status", _fail_w1_only)
    result = _emit(tmp_path)
    assert result == {
        "status": "W1_EMIT_REFUSED",
        "stage": "w1_wave_exit",
        "reasons": ["forced-w1-fail"],
    }
    assert list(tmp_path.iterdir()) == []


def test_w1_emit_refuses_when_central_gate_rejects(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        validator,
        "validate_aiml_artifact",
        lambda artifact, *, now=None: ["forced-central-error"],
    )
    result = _emit(tmp_path)
    assert result["status"] == "W1_EMIT_REFUSED"
    assert result["stage"] == "central_gate"
    assert "forced-central-error" in result["reasons"]
    assert list(tmp_path.iterdir()) == []


def test_w1_emit_refuses_when_historical_w0_missing_or_malformed(tmp_path) -> None:
    # (a) 目錄不存在。
    result = _emit(tmp_path, w0_receipt_dir=tmp_path / "no-such-dir")
    assert result["status"] == "W1_EMIT_REFUSED"
    assert result["stage"] == "historical_w0_receipts"
    assert list(tmp_path.iterdir()) == []
    # (b) 檔在但畸形(非 JSON)。
    bad_dir = tmp_path / "bad-w0"
    bad_dir.mkdir()
    (bad_dir / install.W0_ADMISSION_FILENAME).write_text("not-json", encoding="utf-8")
    (bad_dir / install.W0_WAVE_EXIT_FILENAME).write_text("not-json", encoding="utf-8")
    out_dir = tmp_path / "out"
    result = _emit(out_dir, w0_receipt_dir=bad_dir)
    assert result["status"] == "W1_EMIT_REFUSED"
    assert result["stage"] == "historical_w0_receipts"
    assert not out_dir.exists()


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
def test_w1_emit_rejects_empty_or_malformed_evidence(
    tmp_path, test_evidence, review_provenance
) -> None:
    with pytest.raises(ValueError):
        install.emit_w1_receipts(
            out_dir=tmp_path,
            test_evidence=test_evidence,
            review_provenance=review_provenance,
        )
    assert list(tmp_path.iterdir()) == []
