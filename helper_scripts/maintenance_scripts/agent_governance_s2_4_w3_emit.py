#!/usr/bin/env python3
"""S2.4(WP4·W3)wave-exit 正式發射葉(由 install 模組 2000 行帽拆出;install 上層 re-export)。

鏡 ``emit_w2_receipts`` 的四段鏈路(§10.3 W3 row):

1. 讀持久化的歷史 W2 receipts 作 lineage 記錄(其 source_head 屬歷史世代,**不**直接進
   derivation 鏈;self_digest 竄改即硬拒——屬停機調查事件);
2. 以同一批 builder 於記憶體內重發「當前世代」W0 admission + W0/W1/W2 wave-exit 並逐段
   導出 ADMITTED/PASS;
3. 構建 W3 wave-exit 綁定該鏈,由中央 validator 以
   ``predecessor_wave_receipt=<W2>`` + ``predecessor_wave_chain=(W0, W1)`` 遞迴導出 PASS;
4. 中央閘結構驗全過後才落盤(任一段非 ADMITTED/PASS → typed refusal 且零寫檔)。

receipt 恆 evidence-only:絕不自帶 status;九 authority / production_apply_performed /
running_attested 恆 false。install 模組於函式內延遲匯入(避免 import 循環)。
"""
from __future__ import annotations

import json
import sys
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

W2_RECEIPT_DIRNAME = "S2.4-WP4-W2"
W2_RECEIPT_DIR = (
    REPO_ROOT / "docs" / "execution_plan" / "ai_ml_landing" / "receipts" / W2_RECEIPT_DIRNAME
)
W3_RECEIPT_DIRNAME = "S2.4-WP4-W3"
W3_WAVE_EXIT_FILENAME = "S2.4-WP4-W3-wave-exit-receipt-v1.json"
W3_REGENERATED_W0_ADMISSION_FILENAME = (
    "S2.4-WP4-W3-regenerated-W0-source-admission-receipt-v1.json"
)
W3_REGENERATED_W0_WAVE_EXIT_FILENAME = "S2.4-WP4-W3-regenerated-W0-wave-exit-receipt-v1.json"
W3_REGENERATED_W1_WAVE_EXIT_FILENAME = "S2.4-WP4-W3-regenerated-W1-wave-exit-receipt-v1.json"
W3_REGENERATED_W2_WAVE_EXIT_FILENAME = "S2.4-WP4-W3-regenerated-W2-wave-exit-receipt-v1.json"
W3_DERIVATION_RECORD_FILENAME = "S2.4-WP4-W3-derivation-record.json"
# W2 側持久化物的檔名(只讀 lineage;與 install 模組的常量同值,發射器不改寫歷史 receipt)。
_W2_WAVE_EXIT_FILENAME = "S2.4-WP4-W2-wave-exit-receipt-v1.json"
_W2_REGENERATED_W0_ADMISSION_FILENAME = (
    "S2.4-WP4-W2-regenerated-W0-source-admission-receipt-v1.json"
)
_W2_REGENERATED_W0_WAVE_EXIT_FILENAME = "S2.4-WP4-W2-regenerated-W0-wave-exit-receipt-v1.json"
_W2_REGENERATED_W1_WAVE_EXIT_FILENAME = "S2.4-WP4-W2-regenerated-W1-wave-exit-receipt-v1.json"


def build_w3_wave_exit_receipt(
    admission: dict[str, Any],
    predecessor_wave_exit: dict[str, Any],
    *,
    test_digests: list[str],
    capture_digests: list[str],
    review_fragment_digests: list[str],
) -> dict[str, Any]:
    """綁定當前世代 W0/W1/W2 鏈與真實 test/capture/review 證據 digest 的 W3 wave-exit(無 status)。

    W3 面(owned-path/diff/exported-ABI)全由中央 validator 的 code-owned W3 投影於活 repo
    重算(exported-ABI 折入 probe/topology 六個活裁決);predecessor 綁 W2 的 self_digest。
    """

    receipt: dict[str, Any] = {
        "schema_version": "s2_4_wave_exit_receipt_v1",
        "wave": "W3",
        "predecessor_wave_receipt_digest": predecessor_wave_exit["self_digest"],
        "source_admission_receipt_digest": admission["self_digest"],
        "source_head": admission["source_head"],
        "owned_path_manifest_digest": central_validator.canonical_digest(
            sorted(central_validator._W3_OWNED_PATHS)
        ),
        "owned_path_diff_digest": central_validator.w3_owned_path_diff_digest(),
        "exported_abi_digest": central_validator.canonical_digest(
            central_validator.w3_exported_abi_projection()
        ),
        "test_digests": list(test_digests),
        "capture_digests": list(capture_digests),
        "review_fragment_digests": list(review_fragment_digests),
        "production_authority_flags": {
            "nine_authorities_false": True,
            "production_apply_performed": False,
            "running_attested": False,
        },
    }
    receipt["self_digest"] = central_validator.artifact_self_digest(receipt)
    return receipt


def load_persisted_w2_receipts(w2_receipt_dir: Path) -> dict[str, Any] | None:
    """讀持久化的歷史 W2 receipts(lineage 記錄用;讀不到/畸形回 None → 發射 fail-closed)。

    同 W1/W2 發射器的姿態:四份 receipt 的 ``self_digest`` 就地重算比對,竄改即
    ``SELF_DIGEST_MISMATCH``(caller 硬拒發射)。
    """

    names = (
        _W2_WAVE_EXIT_FILENAME,
        _W2_REGENERATED_W0_ADMISSION_FILENAME,
        _W2_REGENERATED_W0_WAVE_EXIT_FILENAME,
        _W2_REGENERATED_W1_WAVE_EXIT_FILENAME,
    )
    try:
        loaded = [
            json.loads((w2_receipt_dir / name).read_text(encoding="utf-8")) for name in names
        ]
    except (OSError, json.JSONDecodeError):
        return None
    if not all(isinstance(item, dict) and item.get("self_digest") for item in loaded):
        return None
    w2_wave_exit, w0_admission, w0_wave_exit, w1_wave_exit = loaded
    integrity = (
        "VERIFIED"
        if all(
            item["self_digest"] == central_validator.artifact_self_digest(item)
            for item in loaded
        )
        else "SELF_DIGEST_MISMATCH"
    )
    return {
        "persisted_dir": str(w2_receipt_dir),
        "w2_wave_exit_self_digest": w2_wave_exit["self_digest"],
        "regenerated_w0_admission_self_digest": w0_admission["self_digest"],
        "regenerated_w0_wave_exit_self_digest": w0_wave_exit["self_digest"],
        "regenerated_w1_wave_exit_self_digest": w1_wave_exit["self_digest"],
        "historical_source_head": w2_wave_exit.get("source_head"),
        "historical_w2_integrity": integrity,
    }


def emit_w3_receipts(
    *,
    repo_root: Path = REPO_ROOT,
    out_dir: Path,
    test_evidence: dict[str, Any],
    review_provenance: list[dict[str, Any]],
    w2_receipt_dir: Path = W2_RECEIPT_DIR,
    allow_overwrite: bool = False,
) -> dict[str, Any]:
    """發射並持久化正式 W3 wave-exit receipt;任一導出非 ADMITTED/PASS 即 fail-closed 不寫檔。"""

    import agent_governance_s2_4_install as _install

    _install._validate_emit_evidence(test_evidence, review_provenance)

    historical_w2 = load_persisted_w2_receipts(w2_receipt_dir)
    if historical_w2 is None:
        return {
            "status": "W3_EMIT_REFUSED",
            "stage": "historical_w2_receipts",
            "reasons": [
                f"persisted W2 receipts are unreadable or malformed under {w2_receipt_dir}"
            ],
        }
    if historical_w2.get("historical_w2_integrity") != "VERIFIED":
        return {
            "status": "W3_EMIT_REFUSED",
            "stage": "historical_w2_receipts",
            "reasons": [
                "persisted W2 receipts fail self-digest verification "
                "(tampered governance history; investigate before any W3 emission)"
            ],
        }

    admission = _install.build_w0_source_admission_receipt(repo_root)
    admission_result = central_validator.derive_source_admission_status(
        admission, repo_root=repo_root
    )
    if admission_result["status"] != "ADMITTED":
        return {
            "status": "W3_EMIT_REFUSED",
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
            "status": "W3_EMIT_REFUSED",
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
            "status": "W3_EMIT_REFUSED",
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
            "status": "W3_EMIT_REFUSED",
            "stage": "regenerated_w2_wave_exit",
            "reasons": w2_result["reasons"],
        }

    w3_wave_exit = build_w3_wave_exit_receipt(admission, w2_wave_exit, **evidence)
    w3_result = central_validator.derive_wave_exit_status(
        w3_wave_exit,
        repo_root=repo_root,
        source_admission_receipt=admission,
        predecessor_wave_receipt=w2_wave_exit,
        predecessor_wave_chain=(w0_wave_exit, w1_wave_exit),
    )
    if w3_result["status"] != "PASS":
        return {
            "status": "W3_EMIT_REFUSED",
            "stage": "w3_wave_exit",
            "reasons": w3_result["reasons"],
        }

    central_errors: list[str] = []
    for artifact in (admission, w0_wave_exit, w1_wave_exit, w2_wave_exit, w3_wave_exit):
        central_errors += central_validator.validate_aiml_artifact(artifact)
    if central_errors:
        return {
            "status": "W3_EMIT_REFUSED",
            "stage": "central_gate",
            "reasons": central_errors,
        }

    derivation_record = {
        "schema_version": "s2_4_w3_derivation_record_v1_informal",
        "source_head": admission["source_head"],
        "admission_derivation": admission_result,
        "regenerated_w0_wave_exit_derivation": w0_result,
        "regenerated_w1_wave_exit_derivation": w1_result,
        "regenerated_w2_wave_exit_derivation": w2_result,
        "w3_wave_exit_derivation": w3_result,
        "admission_self_digest": admission["self_digest"],
        "regenerated_w0_wave_exit_self_digest": w0_wave_exit["self_digest"],
        "regenerated_w1_wave_exit_self_digest": w1_wave_exit["self_digest"],
        "regenerated_w2_wave_exit_self_digest": w2_wave_exit["self_digest"],
        "w3_wave_exit_self_digest": w3_wave_exit["self_digest"],
        "historical_persisted_w2": historical_w2,
        "test_evidence": test_evidence,
        "review_provenance": review_provenance,
        "replay_note": (
            "W3 re-derivation binds source_head == checkout HEAD; to replay, checkout "
            "source_head, rebuild the in-memory W0/W1/W2 chain with the same builders, then run "
            "derive_wave_exit_status(w3, source_admission_receipt=admission, "
            "predecessor_wave_receipt=w2_wave_exit, "
            "predecessor_wave_chain=(w0_wave_exit, w1_wave_exit))"
        ),
    }
    existing = _persist_emit_artifacts(
        out_dir,
        (
            (W3_WAVE_EXIT_FILENAME, w3_wave_exit),
            (W3_REGENERATED_W0_ADMISSION_FILENAME, admission),
            (W3_REGENERATED_W0_WAVE_EXIT_FILENAME, w0_wave_exit),
            (W3_REGENERATED_W1_WAVE_EXIT_FILENAME, w1_wave_exit),
            (W3_REGENERATED_W2_WAVE_EXIT_FILENAME, w2_wave_exit),
            (W3_DERIVATION_RECORD_FILENAME, derivation_record),
        ),
        allow_overwrite=allow_overwrite,
    )
    if existing is not None:
        return _emit_collision_refusal("W3_EMIT_REFUSED", existing)
    return {
        "status": "W3_RECEIPTS_EMITTED",
        "out_dir": str(out_dir),
        "source_head": admission["source_head"],
        "admission_self_digest": admission["self_digest"],
        "regenerated_w0_wave_exit_self_digest": w0_wave_exit["self_digest"],
        "regenerated_w1_wave_exit_self_digest": w1_wave_exit["self_digest"],
        "regenerated_w2_wave_exit_self_digest": w2_wave_exit["self_digest"],
        "w3_wave_exit_self_digest": w3_wave_exit["self_digest"],
        "historical_persisted_w2": historical_w2,
    }
