"""S2.4(WP4·W1/W2)w1-emit + w2-emit 整合測試——正式 receipt 發射鏈的 happy path + 拒絕分支。

證明(鏡 w0-emit 測試姿態;mock 只用來「逼出拒絕」,絕不 mock 出成功):
- w1-emit 於活 repo 重算:記憶體重發「當前世代」W0 admission+wave-exit(同 builder)、
  綁定該鏈構建 W1 wave-exit、由中央 validator 導出 PASS 後才持久化四個檔;
- w2-emit 鏡 w1-emit:記憶體重發當前世代 W0+W1 鏈、構建 W2 wave-exit(predecessor=W1
  物件 + predecessor_wave_chain=(W0,) 遞迴鏈)、全段 PASS 後才持久化五個檔;
- 歷史持久化 W0/W1 receipts 的 digests 記入 derivation record 作 lineage(其 source_head
  為歷史世代,「不」直接進 derivation 鏈);竄改 → 硬拒;
- 任一段導出非 ADMITTED/PASS → typed refusal 且「不」寫任何檔(fail-closed);
- 歷史 receipts 缺失/畸形 → typed refusal;
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


@pytest.fixture()
def clean_owned_scope(monkeypatch):
    """把「owned scope 相對 bound commit 乾淨」當作**前提**,而不是當作被證的事。

    W5 對抗審計第三輪 P1-D 之後每一波的 wave-exit 都消費自己的 owned-scope 內容差異
    (``validator._owned_scope_delta_reasons``),所以在一棵**未提交**的開發樹上那條具名
    reason 是預期存在的。本檔這些斷言證的是鏈綁定 / 結構 / 發射路徑,不是這棵樹乾不乾淨;
    「髒 owned scope 必須弄破該波 wave exit」的正反兩向由
    ``test_agent_governance_s2_4_install_w5.py::
    test_every_wave_exit_consumes_its_own_owned_scope_delta`` 逐波釘住。
    """

    monkeypatch.setattr(validator, "_owned_scope_delta_reasons", lambda *_a, **_k: [])


def test_w1_emit_happy_path_persists_and_rederives(tmp_path, clean_owned_scope) -> None:
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


def test_w1_emit_refuses_when_w1_wave_exit_not_pass(tmp_path, monkeypatch, clean_owned_scope) -> None:
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


def test_w1_emit_refuses_when_central_gate_rejects(tmp_path, monkeypatch, clean_owned_scope) -> None:
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


# ═════════════════════════════ w2-emit(鏡 w1-emit)═════════════════════════════
def _emit_w2(tmp_path, **overrides):
    kwargs = {
        "out_dir": tmp_path,
        "test_evidence": dict(_TEST_EVIDENCE),
        "review_provenance": [dict(item) for item in _REVIEW_PROVENANCE],
    }
    kwargs.update(overrides)
    return install.emit_w2_receipts(**kwargs)


def test_w2_emit_happy_path_persists_and_rederives(tmp_path, clean_owned_scope) -> None:
    result = _emit_w2(tmp_path)
    assert result["status"] == "W2_RECEIPTS_EMITTED", result
    w2 = json.loads(
        (tmp_path / install.W2_WAVE_EXIT_FILENAME).read_text(encoding="utf-8")
    )
    admission = json.loads(
        (tmp_path / install.W2_REGENERATED_W0_ADMISSION_FILENAME).read_text(
            encoding="utf-8"
        )
    )
    w0 = json.loads(
        (tmp_path / install.W2_REGENERATED_W0_WAVE_EXIT_FILENAME).read_text(
            encoding="utf-8"
        )
    )
    w1 = json.loads(
        (tmp_path / install.W2_REGENERATED_W1_WAVE_EXIT_FILENAME).read_text(
            encoding="utf-8"
        )
    )
    record = json.loads(
        (tmp_path / install.W2_DERIVATION_RECORD_FILENAME).read_text(encoding="utf-8")
    )
    # evidence-only:四份 receipt 皆無 caller-status 鍵。
    for receipt in (admission, w0, w1, w2):
        assert not any(key in receipt for key in validator._CALLER_STATUS_KEYS)
    # 持久化後可獨立重驗完整 W2 鏈(W1 predecessor + W0 遞迴 chain + admission 三重綁定)。
    assert validator.derive_wave_exit_status(
        w2,
        source_admission_receipt=admission,
        predecessor_wave_receipt=w1,
        predecessor_wave_chain=(w0,),
    ) == {"status": "PASS", "reasons": []}
    assert validator.validate_aiml_artifact(w2) == []
    assert w2["wave"] == "W2"
    assert w2["predecessor_wave_receipt_digest"] == w1["self_digest"]
    assert w1["predecessor_wave_receipt_digest"] == w0["self_digest"]
    assert w2["source_head"] == admission["source_head"] == record["source_head"]
    # 世代分離:歷史持久化 W1 只作 lineage 記錄。
    historical = record["historical_persisted_w1"]
    persisted_w1 = json.loads(
        (install.W1_RECEIPT_DIR / install.W1_WAVE_EXIT_FILENAME).read_text(
            encoding="utf-8"
        )
    )
    assert historical["w1_wave_exit_self_digest"] == persisted_w1["self_digest"]
    assert historical["historical_source_head"] == persisted_w1["source_head"]
    assert w2["production_authority_flags"] == {
        "nine_authorities_false": True,
        "production_apply_performed": False,
        "running_attested": False,
    }
    assert w2["test_digests"] == [validator.canonical_digest(_TEST_EVIDENCE)]


def test_w2_emit_refuses_when_any_chain_segment_not_pass(tmp_path, monkeypatch, clean_owned_scope) -> None:
    original = validator.derive_wave_exit_status

    def _fail_wave(wave_name, reason):
        def _inner(receipt, **kwargs):
            if isinstance(receipt, dict) and receipt.get("wave") == wave_name:
                return {"status": "NOT_PASS", "reasons": [reason]}
            return original(receipt, **kwargs)

        return _inner

    for wave_name, stage in (
        ("W0", "regenerated_w0_wave_exit"),
        ("W1", "regenerated_w1_wave_exit"),
        ("W2", "w2_wave_exit"),
    ):
        monkeypatch.setattr(
            validator, "derive_wave_exit_status", _fail_wave(wave_name, f"forced-{wave_name}")
        )
        result = _emit_w2(tmp_path)
        assert result == {
            "status": "W2_EMIT_REFUSED",
            "stage": stage,
            "reasons": [f"forced-{wave_name}"],
        }
        assert list(tmp_path.iterdir()) == []
    monkeypatch.setattr(
        validator,
        "derive_source_admission_status",
        lambda receipt, *, repo_root=None, now=None: {
            "status": "NOT_ADMITTED",
            "reasons": ["forced-admission"],
        },
    )
    result = _emit_w2(tmp_path)
    assert result["stage"] == "regenerated_w0_admission"
    assert list(tmp_path.iterdir()) == []


def test_w2_emit_refuses_when_central_gate_rejects(tmp_path, monkeypatch, clean_owned_scope) -> None:
    # 只對 admission schema 逼出中央閘拒絕:全域拒會先毒化 W2 exported-ABI 的兩個活裁決
    # (它們也消費 validate_aiml_artifact),使拒絕發生在 w2_wave_exit 段而非 central_gate。
    original = validator.validate_aiml_artifact

    def _reject_admission_only(artifact, *, now=None):
        if (
            isinstance(artifact, dict)
            and artifact.get("schema_version") == "s2_4_source_admission_receipt_v1"
        ):
            return ["forced-central-error"]
        return original(artifact, now=now)

    monkeypatch.setattr(validator, "validate_aiml_artifact", _reject_admission_only)
    result = _emit_w2(tmp_path)
    assert result["status"] == "W2_EMIT_REFUSED"
    assert result["stage"] == "central_gate"
    assert "forced-central-error" in result["reasons"]
    assert list(tmp_path.iterdir()) == []


def test_w2_emit_refuses_missing_or_tampered_historical_w1(tmp_path) -> None:
    import shutil as _shutil

    # (a) 目錄不存在。
    result = _emit_w2(tmp_path, w1_receipt_dir=tmp_path / "no-such-dir")
    assert result["status"] == "W2_EMIT_REFUSED"
    assert result["stage"] == "historical_w1_receipts"
    assert list(tmp_path.iterdir()) == []
    # (b) 竄改歷史 W1(改 byte 不重封 self_digest)→ 硬拒且不落檔。
    poisoned_dir = tmp_path / "w1"
    poisoned_dir.mkdir()
    for name in (
        install.W1_WAVE_EXIT_FILENAME,
        install.W1_REGENERATED_W0_ADMISSION_FILENAME,
        install.W1_REGENERATED_W0_WAVE_EXIT_FILENAME,
    ):
        _shutil.copy(install.W1_RECEIPT_DIR / name, poisoned_dir / name)
    target = poisoned_dir / install.W1_WAVE_EXIT_FILENAME
    artifact = json.loads(target.read_text(encoding="utf-8"))
    artifact["source_head"] = "0" * 40
    target.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    out_dir = tmp_path / "out"
    result = _emit_w2(out_dir, w1_receipt_dir=poisoned_dir)
    assert result["status"] == "W2_EMIT_REFUSED"
    assert result["stage"] == "historical_w1_receipts"
    assert "self-digest" in result["reasons"][0]
    assert not out_dir.exists() or list(out_dir.iterdir()) == []


@pytest.mark.parametrize(
    "test_evidence,review_provenance",
    [({}, [{"pr": 1}]), ({"ok": 1}, [])],
)
def test_w2_emit_rejects_empty_or_malformed_evidence(
    tmp_path, test_evidence, review_provenance
) -> None:
    with pytest.raises(ValueError):
        install.emit_w2_receipts(
            out_dir=tmp_path,
            test_evidence=test_evidence,
            review_provenance=review_provenance,
        )
    assert list(tmp_path.iterdir()) == []


def test_w1_emit_hard_refuses_tampered_historical_w0(tmp_path) -> None:
    """PM 裁決回歸(E2 recheck P3):歷史 W0 receipt 竄改 → 硬拒 W1 發射且不落檔。"""

    import json as _json
    import shutil as _shutil

    poisoned_dir = tmp_path / "w0"
    poisoned_dir.mkdir()
    for name in (
        install.W0_ADMISSION_FILENAME,
        install.W0_WAVE_EXIT_FILENAME,
        install.W0_DERIVATION_RECORD_FILENAME,
    ):
        _shutil.copy(install.W0_RECEIPT_DIR / name, poisoned_dir / name)
    target = poisoned_dir / install.W0_ADMISSION_FILENAME
    artifact = _json.loads(target.read_text(encoding="utf-8"))
    artifact["source_head"] = "0" * 40  # 改 byte 不重封 self_digest
    target.write_text(_json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

    out_dir = tmp_path / "out"
    result = install.emit_w1_receipts(
        out_dir=out_dir,
        test_evidence={"command": "pytest -q", "exit_code": 0},
        review_provenance=[{"pr": 0, "verdict": "fixture"}],
        w0_receipt_dir=poisoned_dir,
    )
    assert result["status"] == "W1_EMIT_REFUSED"
    assert result["stage"] == "historical_w0_receipts"
    assert "self-digest" in result["reasons"][0]
    assert not out_dir.exists() or list(out_dir.iterdir()) == []
