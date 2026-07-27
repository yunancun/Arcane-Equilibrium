"""S2.4(WP4·W5)wave-exit **發射器**的 focused 測試(§10.3:1275 / §10.5 #27)。

2000 行治理拆分:本檔由 ``test_agent_governance_s2_4_install_w5.py`` 拆出——加入發射器測試
之後該檔越過 2000 行,而發射面是一個獨立可測的邊界,與 W3/W4 把 ``*_install_w{3,4}.py`` 與
``*_install_{engine_scanner,application_bundle,render}.py`` 分檔是同一個作法。

證明:

- CLI ``w5-emit`` 的 ``--out`` 受限於 repo receipts 目錄(越界即 typed 拒且零寫入);
- 歷史 W4 lineage 缺席/竄改一律硬拒(停機調查事件),且零寫檔;
- 記憶體重發鏈上**任何一段**非 PASS、或中央閘拒收任一 artifact,都 fail-closed 且零寫檔;
- 已存在的 receipt 集合不得被靜默覆蓋;
- 落盤的八件 artifact 綁定當前世代鏈,receipt 恆 evidence-only 且九 authority 恆 false;
- derivation record 逐列序列化未關閉義務帳本,且**由 ABI 枚舉**(ABI 多一列,落盤就多一列);
- derivation record 說得出「這份宣告立基於什麼」:source_head、每一波的 status 與 self_digest、
  replay_note、review_provenance、test_evidence;
- ``PROGRESS.md`` 的義務表逐 id 等於同一份活 ABI(OPS 量到的 13/28 手抄漂移不得再發生)。

誠實邊界:本檔**不**實跑正式發射(``receipts/S2.4-WP4-W5/`` 屬 PM 的收口投影)。落盤內容契約
的那幾支測試把中央導出強制為成功,只驗「發射器寫了什麼」;「鏈是否真的 PASS」由
``test_agent_governance_s2_4_install_w5.py`` 在未被 patch 的中央 validator 上證明。兩者刻意
分開,免得 patch 過的成功被誤當成鏈證據。
"""
from __future__ import annotations

import sys
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


# ── w5-emit(不實跑正式發射;正式 receipts 屬 PM 的收口投影)────────────────────
# W0-W4 每一波都有 receipts/S2.4-WP4-W{n}/,W5 在此之前是唯一沒有的——§10.3:1275
# 「Every source wave emits s2_4_wave_exit_receipt_v1」對 W5 一樣成立。本節鏡 W4 的
# 發射器測試姿態:只驗拒絕形狀、CLI 邊界、再導出面,以及 derivation record 的內容契約。
_EMIT_TEST_EVIDENCE = {
    "command": "python3 -m pytest tests/structure/test_agent_governance_s2_4_install_w5.py -q",
    "exit_code": 0,
    "summary": "unit-test placeholder evidence for W5 emitter behaviour tests",
}
_EMIT_REVIEW_PROVENANCE = [{"pr": 999, "merge_head": "f" * 40, "verdict": "test-fixture"}]


def _forced_pass(monkeypatch) -> None:
    """把三個中央導出強制為成功,好在**髒工作樹上**單獨驗證發射器的落盤內容契約。

    誠實邊界:這只測「發射器寫了什麼」,完全不測「鏈是否真的 PASS」——後者由本檔的鏈測試
    在未被 patch 的中央 validator 上證明。兩者刻意分開,免得 patch 過的成功被當成鏈證據。
    """

    monkeypatch.setattr(
        validator, "derive_source_admission_status",
        lambda receipt, **kwargs: {"status": "ADMITTED", "reasons": []},
    )
    monkeypatch.setattr(
        validator, "derive_wave_exit_status",
        lambda receipt, **kwargs: {"status": "PASS", "reasons": []},
    )
    monkeypatch.setattr(validator, "validate_aiml_artifact", lambda artifact: [])


def test_w5_emit_cli_out_dir_is_constrained_to_the_receipts_directory(
    tmp_path, capsys
) -> None:
    import json

    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(_EMIT_TEST_EVIDENCE), encoding="utf-8")
    provenance = tmp_path / "provenance.json"
    provenance.write_text(json.dumps(_EMIT_REVIEW_PROVENANCE), encoding="utf-8")
    exit_code = install._main([
        "w5-emit",
        "--out", str(tmp_path / "escaped"),
        "--test-evidence", str(evidence),
        "--review-provenance", str(provenance),
    ])
    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["stage"] == "out_dir"
    assert "receipts" in payload["reasons"][0]
    assert not (tmp_path / "escaped").exists()
    inside = install.RECEIPTS_ROOT / install.W5_RECEIPT_DIRNAME
    assert install._resolve_cli_out_dir(inside) == inside.resolve()


def test_w5_emit_refuses_when_persisted_w4_lineage_is_tampered(tmp_path) -> None:
    """歷史 W4 receipts 的 self_digest 竄改是停機調查事件:硬拒且零寫檔。"""

    import json

    source_dir = install.W4_RECEIPT_DIR
    lineage = install._load_persisted_w4_receipts(source_dir)
    assert lineage is not None and lineage["historical_w4_integrity"] == "VERIFIED"
    for name in sorted(p.name for p in source_dir.glob("*.json")):
        (tmp_path / name).write_text(
            (source_dir / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    target = tmp_path / "S2.4-WP4-W4-wave-exit-receipt-v1.json"
    tampered = json.loads(target.read_text(encoding="utf-8"))
    tampered["source_head"] = "c" * 40
    target.write_text(json.dumps(tampered), encoding="utf-8")
    out_dir = tmp_path / "out"
    result = install.emit_w5_receipts(
        out_dir=out_dir,
        test_evidence=dict(_EMIT_TEST_EVIDENCE),
        review_provenance=[dict(item) for item in _EMIT_REVIEW_PROVENANCE],
        w4_receipt_dir=tmp_path,
    )
    assert result["status"] == "W5_EMIT_REFUSED"
    assert result["stage"] == "historical_w4_receipts"
    assert not out_dir.exists()


def test_w5_emit_refuses_when_the_persisted_w4_lineage_is_missing(tmp_path) -> None:
    out_dir = tmp_path / "out"
    result = install.emit_w5_receipts(
        out_dir=out_dir,
        test_evidence=dict(_EMIT_TEST_EVIDENCE),
        review_provenance=[dict(item) for item in _EMIT_REVIEW_PROVENANCE],
        w4_receipt_dir=tmp_path / "absent",
    )
    assert result["status"] == "W5_EMIT_REFUSED"
    assert result["stage"] == "historical_w4_receipts"
    assert not out_dir.exists()


@pytest.mark.parametrize("failing_wave", ["W0", "W1", "W2", "W3", "W4", "W5"])
def test_w5_emit_refuses_and_writes_nothing_when_any_chain_link_does_not_derive(
    tmp_path, monkeypatch, failing_wave
) -> None:
    """鏈上**任何一段**非 PASS 都必須 fail-closed 且零寫檔——不只是 W5 自己那一段。"""

    _forced_pass(monkeypatch)
    real = {"status": "PASS", "reasons": []}
    monkeypatch.setattr(
        validator, "derive_wave_exit_status",
        lambda receipt, **kwargs: (
            {"status": "NOT_PASS", "reasons": ["forced-for-fail-closed"]}
            if receipt.get("wave") == failing_wave else dict(real)
        ),
    )
    out_dir = tmp_path / "out"
    result = install.emit_w5_receipts(
        out_dir=out_dir,
        test_evidence=dict(_EMIT_TEST_EVIDENCE),
        review_provenance=[dict(item) for item in _EMIT_REVIEW_PROVENANCE],
    )
    assert result["status"] == "W5_EMIT_REFUSED"
    assert result["reasons"] == ["forced-for-fail-closed"]
    expected_stage = (
        "w5_wave_exit" if failing_wave == "W5"
        else f"regenerated_{failing_wave.lower()}_wave_exit"
    )
    assert result["stage"] == expected_stage
    assert not out_dir.exists()


def test_w5_emit_refuses_when_the_central_gate_rejects_any_artifact(
    tmp_path, monkeypatch
) -> None:
    _forced_pass(monkeypatch)
    monkeypatch.setattr(
        validator, "validate_aiml_artifact", lambda artifact: ["forced-central-error"]
    )
    out_dir = tmp_path / "out"
    result = install.emit_w5_receipts(
        out_dir=out_dir,
        test_evidence=dict(_EMIT_TEST_EVIDENCE),
        review_provenance=[dict(item) for item in _EMIT_REVIEW_PROVENANCE],
    )
    assert result["status"] == "W5_EMIT_REFUSED"
    assert result["stage"] == "central_gate"
    assert not out_dir.exists()


def test_w5_emit_refuses_to_silently_overwrite_an_existing_receipt_set(
    tmp_path, monkeypatch
) -> None:
    _forced_pass(monkeypatch)
    out_dir = tmp_path / "out"
    kwargs = {
        "out_dir": out_dir,
        "test_evidence": dict(_EMIT_TEST_EVIDENCE),
        "review_provenance": [dict(item) for item in _EMIT_REVIEW_PROVENANCE],
    }
    first = install.emit_w5_receipts(**kwargs)
    assert first["status"] == "W5_RECEIPTS_EMITTED"
    before = {p.name: p.read_bytes() for p in out_dir.iterdir()}
    second = install.emit_w5_receipts(**kwargs)
    assert second["status"] == "W5_EMIT_REFUSED"
    assert second["stage"] == "output_collision"
    assert {p.name: p.read_bytes() for p in out_dir.iterdir()} == before


def test_w5_emit_writes_the_eight_artifact_set_and_binds_the_regenerated_chain(
    tmp_path, monkeypatch
) -> None:
    import json

    _forced_pass(monkeypatch)
    out_dir = tmp_path / "out"
    result = install.emit_w5_receipts(
        out_dir=out_dir,
        test_evidence=dict(_EMIT_TEST_EVIDENCE),
        review_provenance=[dict(item) for item in _EMIT_REVIEW_PROVENANCE],
    )
    assert result["status"] == "W5_RECEIPTS_EMITTED"
    assert sorted(p.name for p in out_dir.iterdir()) == sorted((
        install.W5_WAVE_EXIT_FILENAME,
        install.W5_REGENERATED_W0_ADMISSION_FILENAME,
        install.W5_REGENERATED_W0_WAVE_EXIT_FILENAME,
        install.W5_REGENERATED_W1_WAVE_EXIT_FILENAME,
        install.W5_REGENERATED_W2_WAVE_EXIT_FILENAME,
        install.W5_REGENERATED_W3_WAVE_EXIT_FILENAME,
        install.W5_REGENERATED_W4_WAVE_EXIT_FILENAME,
        install.W5_DERIVATION_RECORD_FILENAME,
    ))
    receipts = {
        name: json.loads((out_dir / name).read_text(encoding="utf-8"))
        for name in sorted(p.name for p in out_dir.iterdir())
    }
    w5 = receipts[install.W5_WAVE_EXIT_FILENAME]
    w4 = receipts[install.W5_REGENERATED_W4_WAVE_EXIT_FILENAME]
    admission = receipts[install.W5_REGENERATED_W0_ADMISSION_FILENAME]
    assert w5["wave"] == "W5"
    assert w5["predecessor_wave_receipt_digest"] == w4["self_digest"]
    assert w5["source_admission_receipt_digest"] == admission["self_digest"]
    # receipt 恆 evidence-only:絕不自帶 status;九 authority 恆 false。
    assert "status" not in w5
    assert w5["production_authority_flags"] == {
        "nine_authorities_false": True,
        "production_apply_performed": False,
        "running_attested": False,
    }
    assert w5["self_digest"] == validator.artifact_self_digest(
        {k: v for k, v in w5.items() if k != "self_digest"}
    )


def test_w5_derivation_record_serialises_the_whole_obligation_ledger(
    tmp_path, monkeypatch
) -> None:
    """OPS:W6 事故時,operator 的前置條件清單必須讀得到 artifact,而不是 import 一個模組。

    帳本必須**逐列等於**活 ABI(不是子集、不是摘要),且 ``obligation_ledger_digest`` 可與
    活 ABI 的 canonical digest 對上——手抄/截斷/軟化任一列都會讓這支測試變紅。
    """

    import json

    _forced_pass(monkeypatch)
    out_dir = tmp_path / "out"
    result = install.emit_w5_receipts(
        out_dir=out_dir,
        test_evidence=dict(_EMIT_TEST_EVIDENCE),
        review_provenance=[dict(item) for item in _EMIT_REVIEW_PROVENANCE],
    )
    assert result["status"] == "W5_RECEIPTS_EMITTED"
    record = json.loads(
        (out_dir / install.W5_DERIVATION_RECORD_FILENAME).read_text(encoding="utf-8")
    )
    live = list(validator._W5_EXPORTED_ABI["remaining_owned_obligations"])
    assert record["remaining_owned_obligations"] == live
    assert record["remaining_owned_obligation_count"] == len(live)
    assert record["obligation_ledger_digest"] == validator.canonical_digest(live)
    assert result["obligation_ledger_digest"] == record["obligation_ledger_digest"]
    # 每一列都保留 owner/typed_status/spec_refs——少了任一個,artifact 就不是可執行的前置清單。
    for row in record["remaining_owned_obligations"]:
        assert row["obligation_id"] and row["owner_wave"] and row["typed_status"]
        assert row["spec_refs"] and row["statement"]


def test_w5_derivation_record_ledger_is_enumerated_rather_than_hand_copied(
    tmp_path, monkeypatch
) -> None:
    """反漂移:ABI 多一列,落盤的帳本就必須多一列。手寫清單過不了這一關。"""

    import json

    import aiml_gate_receipt_wave_w5 as wave_w5

    _forced_pass(monkeypatch)
    synthetic = {
        "obligation_id": "SYNTHETIC_LEDGER_DRIFT_PROBE",
        "typed_status": "NOT_PROVIDED_BY_W5",
        "owner_wave": "W6B",
        "spec_refs": ["§10.3"],
        "statement": "synthetic row injected by the anti-drift test",
        "w5_provides": "nothing",
    }
    monkeypatch.setitem(
        wave_w5._W5_EXPORTED_ABI,
        "remaining_owned_obligations",
        list(wave_w5._W5_EXPORTED_ABI["remaining_owned_obligations"]) + [synthetic],
    )
    out_dir = tmp_path / "out"
    result = install.emit_w5_receipts(
        out_dir=out_dir,
        test_evidence=dict(_EMIT_TEST_EVIDENCE),
        review_provenance=[dict(item) for item in _EMIT_REVIEW_PROVENANCE],
    )
    assert result["status"] == "W5_RECEIPTS_EMITTED"
    record = json.loads(
        (out_dir / install.W5_DERIVATION_RECORD_FILENAME).read_text(encoding="utf-8")
    )
    assert synthetic in record["remaining_owned_obligations"]
    assert record["remaining_owned_obligation_count"] == len(
        wave_w5._W5_EXPORTED_ABI["remaining_owned_obligations"]
    )


def test_w5_derivation_record_states_what_the_declaration_rests_on(
    tmp_path, monkeypatch
) -> None:
    """OPS:再導出只說得出「commit 現在寫什麼」,永遠說不出「PM 當時看到什麼」。

    所以 record 必須逐字帶 source_head、每一波的 status 與 self_digest、replay_note、
    review_provenance 與 test_evidence——與 ``_w4_emit`` 同形。
    """

    import json

    _forced_pass(monkeypatch)
    out_dir = tmp_path / "out"
    result = install.emit_w5_receipts(
        out_dir=out_dir,
        test_evidence=dict(_EMIT_TEST_EVIDENCE),
        review_provenance=[dict(item) for item in _EMIT_REVIEW_PROVENANCE],
    )
    assert result["status"] == "W5_RECEIPTS_EMITTED"
    record = json.loads(
        (out_dir / install.W5_DERIVATION_RECORD_FILENAME).read_text(encoding="utf-8")
    )
    assert record["schema_version"] == "s2_4_w5_derivation_record_v1_informal"
    assert record["source_head"] == result["source_head"]
    assert record["test_evidence"] == _EMIT_TEST_EVIDENCE
    assert record["review_provenance"] == _EMIT_REVIEW_PROVENANCE
    assert record["admission_derivation"]["status"] == "ADMITTED"
    for wave in ("w0", "w1", "w2", "w3", "w4"):
        assert record[f"regenerated_{wave}_wave_exit_derivation"]["status"] == "PASS"
        assert record[f"regenerated_{wave}_wave_exit_self_digest"].startswith("sha256:")
    assert record["w5_wave_exit_derivation"]["status"] == "PASS"
    assert record["w5_wave_exit_self_digest"] == result["w5_wave_exit_self_digest"]
    assert record["historical_persisted_w4"]["historical_w4_integrity"] == "VERIFIED"
    # replay_note 必須同時給重放配方,以及「綠鏈不等於測試跑過/有人審過」的誠實界線。
    assert "predecessor_wave_chain=(w0_wave_exit, w1_wave_exit, w2_wave_exit, w3_wave_exit)" in (
        record["replay_note"]
    )
    assert "shape-only" in record["replay_note"]
    assert "never evidences" in record["replay_note"]


def test_progress_ledger_obligation_section_is_the_whole_live_abi() -> None:
    """OPS:PROGRESS.md 曾只帶 13/28 列。手抄的清單只會再漂一次,所以這裡把它釘死。

    PROGRESS.md 的義務表必須**逐 id 等於**活 ABI:少一列(靜默丟掉一項未關閉義務)或多一列
    (帳本上有、程式碼裡沒有的幽靈義務)都變紅。表內每列也必須帶上該列自己的 typed_status
    與 owner_wave,否則 W6 operator 讀到的是一份不能執行的清單。
    """

    import re

    progress = (
        ROOT / "docs/execution_plan/ai_ml_landing/PROGRESS.md"
    ).read_text(encoding="utf-8")
    heading = "## S2.4 (WP4) unclosed owned obligations"
    assert heading in progress, "PROGRESS.md is missing the generated obligation section"
    section = progress.split(heading, 1)[1].split("\n## ", 1)[0]
    live = {
        row["obligation_id"]: row
        for row in validator._W5_EXPORTED_ABI["remaining_owned_obligations"]
    }
    listed = {
        match.group(1)
        for match in re.finditer(r"^\| *\d+ *\| *`([A-Z0-9_]+)` *\|", section, re.MULTILINE)
    }
    assert listed == set(live), {
        "missing_from_progress": sorted(set(live) - listed),
        "not_in_the_live_abi": sorted(listed - set(live)),
    }
    for obligation_id, row in live.items():
        entry = next(
            line for line in section.splitlines()
            if f"`{obligation_id}`" in line and line.startswith("|")
        )
        assert f"`{row['typed_status']}`" in entry, obligation_id
        assert f"`{row['owner_wave']}`" in entry, obligation_id


def test_install_module_reexports_the_w5_emit_surface() -> None:
    for name in (
        "emit_w5_receipts",
        "_load_persisted_w4_receipts",
        "W4_RECEIPT_DIR",
        "W5_RECEIPT_DIRNAME",
        "W5_WAVE_EXIT_FILENAME",
        "W5_REGENERATED_W4_WAVE_EXIT_FILENAME",
        "W5_DERIVATION_RECORD_FILENAME",
    ):
        assert hasattr(install, name), name
    # 每一波的發射器都要能從同一個 CLI 派出;W5 不得是唯一沒有 verb 的那一波。
    import agent_governance_s2_4_w5_emit as w5_emit

    assert install.emit_w5_receipts is w5_emit.emit_w5_receipts
    assert install.W5_RECEIPT_DIRNAME == "S2.4-WP4-W5"
