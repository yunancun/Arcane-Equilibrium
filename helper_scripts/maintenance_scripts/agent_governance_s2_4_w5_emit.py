#!/usr/bin/env python3
"""S2.4(WP4·W5)wave-exit 正式發射葉(鏡 ``agent_governance_s2_4_w4_emit``;install 上層 re-export)。

§10.3 首句「Every source wave emits ``s2_4_wave_exit_receipt_v1``」對 W5 一樣成立:
``build_w5_wave_exit_receipt`` 只回記憶體物件、不寫任何檔案,所以在本葉之前 W5 是全 WP4 唯一
沒有持久化 receipt 的 source wave。本葉補上那一段,四段鏈路與 W3/W4 完全同形:

1. 讀持久化的歷史 W4 receipts 作 lineage 記錄(其 source_head 屬歷史世代,**不**直接進
   derivation 鏈;self_digest 竄改即硬拒——屬停機調查事件);
2. 以同一批 builder 於記憶體內重發「當前世代」W0 admission + W0/W1/W2/W3/W4 wave-exit 並逐段
   導出 ADMITTED/PASS;
3. 構建 W5 wave-exit 綁定該鏈,由中央 validator 以
   ``predecessor_wave_receipt=<W4>`` + ``predecessor_wave_chain=(W0, W1, W2, W3)`` 遞迴導出 PASS;
4. 中央閘結構驗全過後才落盤(任一段非 ADMITTED/PASS → typed refusal 且零寫檔)。

與 W3/W4 的兩處刻意差異:

- **builder 不在本葉**:``build_w5_wave_exit_receipt`` 由中央 validator(W5 投影葉)擁有,本葉
  只呼叫它。W5 的 owned-path/ABI 投影都在該葉,發射器不得另建一份會漂移的副本;
- **derivation record 序列化義務帳本**(OPS W5 審計要求):``remaining_owned_obligations`` 逐列
  寫進 derivation record,且**由 ``_W5_EXPORTED_ABI`` 枚舉**而非手抄。W6 事故時,operator 的
  前置條件清單必須讀得到一份 artifact,而不是去 import 一個未合併分支上的 Python 模組。
  ``obligation_ledger_digest`` 讓 replay 端可與活 ABI 逐位元組比對,手改即現形。

receipt 恆 evidence-only:絕不自帶 status;九 authority / production_apply_performed /
running_attested 恆 false。install 模組於函式內延遲匯入(避免 import 循環)。

誠實邊界:一條綠色的 W0→W5 鏈只證明「該 head 上的 source 結構自洽」。evidence digest 是
形狀性的(鏈在 ``sha256:111…1`` 這種輸入上一樣導出 PASS),所以它**永遠不**證明測試跑過、
也不證明有人審過——那兩件事只能由實測 suite 與具名 review provenance 承擔。
"""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
PROGRAM_CODE_DIR = REPO_ROOT / "program_code"
for _candidate in (HELPER_DIR, ML_TRAINING_DIR, PROGRAM_CODE_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import aiml_gate_receipt_validator as central_validator  # noqa: E402
from agent_governance_s2_4_emit_sink import (  # noqa: E402
    emit_collision_refusal as _emit_collision_refusal,
    persist_emit_artifacts as _persist_emit_artifacts,
)

W4_RECEIPT_DIRNAME = "S2.4-WP4-W4"
W4_RECEIPT_DIR = (
    REPO_ROOT / "docs" / "execution_plan" / "ai_ml_landing" / "receipts" / W4_RECEIPT_DIRNAME
)
W5_RECEIPT_DIRNAME = "S2.4-WP4-W5"
W5_WAVE_EXIT_FILENAME = "S2.4-WP4-W5-wave-exit-receipt-v1.json"
W5_REGENERATED_W0_ADMISSION_FILENAME = (
    "S2.4-WP4-W5-regenerated-W0-source-admission-receipt-v1.json"
)
W5_REGENERATED_W0_WAVE_EXIT_FILENAME = "S2.4-WP4-W5-regenerated-W0-wave-exit-receipt-v1.json"
W5_REGENERATED_W1_WAVE_EXIT_FILENAME = "S2.4-WP4-W5-regenerated-W1-wave-exit-receipt-v1.json"
W5_REGENERATED_W2_WAVE_EXIT_FILENAME = "S2.4-WP4-W5-regenerated-W2-wave-exit-receipt-v1.json"
W5_REGENERATED_W3_WAVE_EXIT_FILENAME = "S2.4-WP4-W5-regenerated-W3-wave-exit-receipt-v1.json"
W5_REGENERATED_W4_WAVE_EXIT_FILENAME = "S2.4-WP4-W5-regenerated-W4-wave-exit-receipt-v1.json"
W5_DERIVATION_RECORD_FILENAME = "S2.4-WP4-W5-derivation-record.json"
# W4 側持久化物的檔名(只讀 lineage;與 w4_emit 的常量同值,發射器不改寫歷史 receipt)。
_W4_WAVE_EXIT_FILENAME = "S2.4-WP4-W4-wave-exit-receipt-v1.json"
_W4_REGENERATED_W0_ADMISSION_FILENAME = (
    "S2.4-WP4-W4-regenerated-W0-source-admission-receipt-v1.json"
)
_W4_REGENERATED_W0_WAVE_EXIT_FILENAME = "S2.4-WP4-W4-regenerated-W0-wave-exit-receipt-v1.json"
_W4_REGENERATED_W1_WAVE_EXIT_FILENAME = "S2.4-WP4-W4-regenerated-W1-wave-exit-receipt-v1.json"
_W4_REGENERATED_W2_WAVE_EXIT_FILENAME = "S2.4-WP4-W4-regenerated-W2-wave-exit-receipt-v1.json"
_W4_REGENERATED_W3_WAVE_EXIT_FILENAME = "S2.4-WP4-W4-regenerated-W3-wave-exit-receipt-v1.json"

# derivation record 內義務帳本的誠實說明(逐字入檔;讀 artifact 的人不必再翻設計文件)。
_OBLIGATION_LEDGER_NOTE = (
    "Enumerated from aiml_gate_receipt_wave_w5._W5_EXPORTED_ABI"
    "['remaining_owned_obligations'] at emission time, never hand-copied. This is the "
    "operator's W6 precondition list: at W6 incident time it must be readable from this "
    "artifact alone, without importing a Python module from any branch. Compare "
    "obligation_ledger_digest against canonical_digest over the live ABI list to detect a "
    "hand-edited copy. Every row is UNCLOSED at this source head; owner_wave names who "
    "must close it."
)
_REPLAY_NOTE = (
    "W5 re-derivation binds source_head == checkout HEAD; to replay, checkout source_head, "
    "rebuild the in-memory W0/W1/W2/W3/W4 chain with the same builders, then run "
    "derive_wave_exit_status(w5, source_admission_receipt=admission, "
    "predecessor_wave_receipt=w4_wave_exit, "
    "predecessor_wave_chain=(w0_wave_exit, w1_wave_exit, w2_wave_exit, w3_wave_exit)). "
    "A PASS here evidences source structure at this head only: the evidence digests are "
    "shape-only (the chain derives PASS on a literal sha256:111...1), so it never evidences "
    "that any test ran or that any review happened."
)


def w5_remaining_obligation_ledger() -> list[dict[str, Any]]:
    """由活 ABI 枚舉未關閉義務帳本(深拷貝;持久化面絕不與模組常量共用物件)。"""

    return deepcopy(
        list(central_validator._W5_EXPORTED_ABI["remaining_owned_obligations"])
    )


def load_persisted_w4_receipts(w4_receipt_dir: Path) -> dict[str, Any] | None:
    """讀持久化的歷史 W4 receipts(lineage 記錄用;讀不到/畸形回 None → 發射 fail-closed)。"""

    names = (
        _W4_WAVE_EXIT_FILENAME,
        _W4_REGENERATED_W0_ADMISSION_FILENAME,
        _W4_REGENERATED_W0_WAVE_EXIT_FILENAME,
        _W4_REGENERATED_W1_WAVE_EXIT_FILENAME,
        _W4_REGENERATED_W2_WAVE_EXIT_FILENAME,
        _W4_REGENERATED_W3_WAVE_EXIT_FILENAME,
    )
    try:
        loaded = [
            json.loads((w4_receipt_dir / name).read_text(encoding="utf-8")) for name in names
        ]
    except (OSError, json.JSONDecodeError):
        return None
    if not all(isinstance(item, dict) and item.get("self_digest") for item in loaded):
        return None
    (
        w4_wave_exit, w0_admission, w0_wave_exit, w1_wave_exit, w2_wave_exit, w3_wave_exit,
    ) = loaded
    integrity = (
        "VERIFIED"
        if all(
            item["self_digest"] == central_validator.artifact_self_digest(item)
            for item in loaded
        )
        else "SELF_DIGEST_MISMATCH"
    )
    return {
        "persisted_dir": str(w4_receipt_dir),
        "w4_wave_exit_self_digest": w4_wave_exit["self_digest"],
        "regenerated_w0_admission_self_digest": w0_admission["self_digest"],
        "regenerated_w0_wave_exit_self_digest": w0_wave_exit["self_digest"],
        "regenerated_w1_wave_exit_self_digest": w1_wave_exit["self_digest"],
        "regenerated_w2_wave_exit_self_digest": w2_wave_exit["self_digest"],
        "regenerated_w3_wave_exit_self_digest": w3_wave_exit["self_digest"],
        "historical_source_head": w4_wave_exit.get("source_head"),
        "historical_w4_integrity": integrity,
    }


def emit_w5_receipts(
    *,
    repo_root: Path = REPO_ROOT,
    out_dir: Path,
    test_evidence: dict[str, Any],
    review_provenance: list[dict[str, Any]],
    w4_receipt_dir: Path = W4_RECEIPT_DIR,
    allow_overwrite: bool = False,
) -> dict[str, Any]:
    """發射並持久化正式 W5 wave-exit receipt;任一導出非 ADMITTED/PASS 即 fail-closed 不寫檔。"""

    import agent_governance_s2_4_install as _install

    _install._validate_emit_evidence(test_evidence, review_provenance)

    historical_w4 = load_persisted_w4_receipts(w4_receipt_dir)
    if historical_w4 is None:
        return {
            "status": "W5_EMIT_REFUSED",
            "stage": "historical_w4_receipts",
            "reasons": [
                f"persisted W4 receipts are unreadable or malformed under {w4_receipt_dir}"
            ],
        }
    if historical_w4.get("historical_w4_integrity") != "VERIFIED":
        return {
            "status": "W5_EMIT_REFUSED",
            "stage": "historical_w4_receipts",
            "reasons": [
                "persisted W4 receipts fail self-digest verification "
                "(tampered governance history; investigate before any W5 emission)"
            ],
        }

    admission = _install.build_w0_source_admission_receipt(repo_root)
    admission_result = central_validator.derive_source_admission_status(
        admission, repo_root=repo_root
    )
    if admission_result["status"] != "ADMITTED":
        return {
            "status": "W5_EMIT_REFUSED",
            "stage": "regenerated_w0_admission",
            "reasons": admission_result["reasons"],
        }

    test_digests = [central_validator.canonical_digest(test_evidence)]
    capture_digests = [
        central_validator.canonical_digest(
            {"kind": "raw_local_test_capture", "record": test_evidence}
        )
    ]
    review_digests = [
        central_validator.canonical_digest(item) for item in review_provenance
    ]
    evidence = {
        "test_digests": test_digests,
        "capture_digests": capture_digests,
        "review_fragment_digests": review_digests,
    }

    w0_wave_exit = _install.build_w0_wave_exit_receipt(admission, **evidence)
    w0_result = central_validator.derive_wave_exit_status(
        w0_wave_exit, repo_root=repo_root, source_admission_receipt=admission
    )
    if w0_result["status"] != "PASS":
        return {
            "status": "W5_EMIT_REFUSED",
            "stage": "regenerated_w0_wave_exit",
            "reasons": w0_result["reasons"],
        }

    w1_wave_exit = _install.build_w1_wave_exit_receipt(admission, w0_wave_exit, **evidence)
    w1_result = central_validator.derive_wave_exit_status(
        w1_wave_exit,
        repo_root=repo_root,
        source_admission_receipt=admission,
        predecessor_wave_receipt=w0_wave_exit,
    )
    if w1_result["status"] != "PASS":
        return {
            "status": "W5_EMIT_REFUSED",
            "stage": "regenerated_w1_wave_exit",
            "reasons": w1_result["reasons"],
        }

    w2_wave_exit = _install.build_w2_wave_exit_receipt(admission, w1_wave_exit, **evidence)
    w2_result = central_validator.derive_wave_exit_status(
        w2_wave_exit,
        repo_root=repo_root,
        source_admission_receipt=admission,
        predecessor_wave_receipt=w1_wave_exit,
        predecessor_wave_chain=(w0_wave_exit,),
    )
    if w2_result["status"] != "PASS":
        return {
            "status": "W5_EMIT_REFUSED",
            "stage": "regenerated_w2_wave_exit",
            "reasons": w2_result["reasons"],
        }

    w3_wave_exit = _install.build_w3_wave_exit_receipt(admission, w2_wave_exit, **evidence)
    w3_result = central_validator.derive_wave_exit_status(
        w3_wave_exit,
        repo_root=repo_root,
        source_admission_receipt=admission,
        predecessor_wave_receipt=w2_wave_exit,
        predecessor_wave_chain=(w0_wave_exit, w1_wave_exit),
    )
    if w3_result["status"] != "PASS":
        return {
            "status": "W5_EMIT_REFUSED",
            "stage": "regenerated_w3_wave_exit",
            "reasons": w3_result["reasons"],
        }

    w4_wave_exit = _install.build_w4_wave_exit_receipt(admission, w3_wave_exit, **evidence)
    w4_result = central_validator.derive_wave_exit_status(
        w4_wave_exit,
        repo_root=repo_root,
        source_admission_receipt=admission,
        predecessor_wave_receipt=w3_wave_exit,
        predecessor_wave_chain=(w0_wave_exit, w1_wave_exit, w2_wave_exit),
    )
    if w4_result["status"] != "PASS":
        return {
            "status": "W5_EMIT_REFUSED",
            "stage": "regenerated_w4_wave_exit",
            "reasons": w4_result["reasons"],
        }

    # W5 builder 由中央 validator(W5 投影葉)擁有;發射器不另建副本。
    w5_wave_exit = central_validator.build_w5_wave_exit_receipt(
        admission, w4_wave_exit, **evidence
    )
    w5_result = central_validator.derive_wave_exit_status(
        w5_wave_exit,
        repo_root=repo_root,
        source_admission_receipt=admission,
        predecessor_wave_receipt=w4_wave_exit,
        predecessor_wave_chain=(
            w0_wave_exit, w1_wave_exit, w2_wave_exit, w3_wave_exit,
        ),
    )
    if w5_result["status"] != "PASS":
        return {
            "status": "W5_EMIT_REFUSED",
            "stage": "w5_wave_exit",
            "reasons": w5_result["reasons"],
        }

    central_errors: list[str] = []
    for artifact in (
        admission, w0_wave_exit, w1_wave_exit, w2_wave_exit, w3_wave_exit, w4_wave_exit,
        w5_wave_exit,
    ):
        central_errors += central_validator.validate_aiml_artifact(artifact)
    if central_errors:
        return {
            "status": "W5_EMIT_REFUSED",
            "stage": "central_gate",
            "reasons": central_errors,
        }

    obligation_ledger = w5_remaining_obligation_ledger()
    derivation_record = {
        "schema_version": "s2_4_w5_derivation_record_v1_informal",
        "source_head": admission["source_head"],
        "admission_derivation": admission_result,
        "regenerated_w0_wave_exit_derivation": w0_result,
        "regenerated_w1_wave_exit_derivation": w1_result,
        "regenerated_w2_wave_exit_derivation": w2_result,
        "regenerated_w3_wave_exit_derivation": w3_result,
        "regenerated_w4_wave_exit_derivation": w4_result,
        "w5_wave_exit_derivation": w5_result,
        "admission_self_digest": admission["self_digest"],
        "regenerated_w0_wave_exit_self_digest": w0_wave_exit["self_digest"],
        "regenerated_w1_wave_exit_self_digest": w1_wave_exit["self_digest"],
        "regenerated_w2_wave_exit_self_digest": w2_wave_exit["self_digest"],
        "regenerated_w3_wave_exit_self_digest": w3_wave_exit["self_digest"],
        "regenerated_w4_wave_exit_self_digest": w4_wave_exit["self_digest"],
        "w5_wave_exit_self_digest": w5_wave_exit["self_digest"],
        "historical_persisted_w4": historical_w4,
        "test_evidence": test_evidence,
        "review_provenance": review_provenance,
        # OPS W5 審計要求:未關閉義務帳本必須在 artifact 上讀得到,不得只活在 Python 模組裡。
        "remaining_owned_obligations": obligation_ledger,
        "remaining_owned_obligation_count": len(obligation_ledger),
        "obligation_ledger_digest": central_validator.canonical_digest(obligation_ledger),
        "obligation_ledger_note": _OBLIGATION_LEDGER_NOTE,
        "replay_note": _REPLAY_NOTE,
    }
    existing = _persist_emit_artifacts(
        out_dir,
        (
            (W5_WAVE_EXIT_FILENAME, w5_wave_exit),
            (W5_REGENERATED_W0_ADMISSION_FILENAME, admission),
            (W5_REGENERATED_W0_WAVE_EXIT_FILENAME, w0_wave_exit),
            (W5_REGENERATED_W1_WAVE_EXIT_FILENAME, w1_wave_exit),
            (W5_REGENERATED_W2_WAVE_EXIT_FILENAME, w2_wave_exit),
            (W5_REGENERATED_W3_WAVE_EXIT_FILENAME, w3_wave_exit),
            (W5_REGENERATED_W4_WAVE_EXIT_FILENAME, w4_wave_exit),
            (W5_DERIVATION_RECORD_FILENAME, derivation_record),
        ),
        allow_overwrite=allow_overwrite,
    )
    if existing is not None:
        return _emit_collision_refusal("W5_EMIT_REFUSED", existing)
    return {
        "status": "W5_RECEIPTS_EMITTED",
        "out_dir": str(out_dir),
        "source_head": admission["source_head"],
        "admission_self_digest": admission["self_digest"],
        "regenerated_w0_wave_exit_self_digest": w0_wave_exit["self_digest"],
        "regenerated_w1_wave_exit_self_digest": w1_wave_exit["self_digest"],
        "regenerated_w2_wave_exit_self_digest": w2_wave_exit["self_digest"],
        "regenerated_w3_wave_exit_self_digest": w3_wave_exit["self_digest"],
        "regenerated_w4_wave_exit_self_digest": w4_wave_exit["self_digest"],
        "w5_wave_exit_self_digest": w5_wave_exit["self_digest"],
        "obligation_ledger_digest": derivation_record["obligation_ledger_digest"],
        "remaining_owned_obligation_count": len(obligation_ledger),
        "historical_persisted_w4": historical_w4,
    }
