#!/usr/bin/env python3
"""S2.4(WP4)install-session 治理模組——首片:W0 正式 receipt 發射器。

§10.3 要求 W0 以「持久、中央驗證」的 `s2_4_source_admission_receipt_v1(status=ADMITTED)`
與 `s2_4_wave_exit_receipt_v1(status=PASS)` 收尾;test fixture 或 schema 存在皆不可代替。
本模組是該正式出口的 production 發射器:

- receipt 只帶 evidence,「絕不」自帶 status——ADMITTED/PASS 一律由中央
  `aiml_gate_receipt_validator.derive_source_admission_status` /
  `derive_wave_exit_status` 從 repo 當前 checkout 再導出(§10.5 #27);
- 發射 fail-closed:任一導出非 ADMITTED/PASS 即拒絕寫檔並回 typed reason;
- 持久化物包含 derivation record(綁 source_head 與兩份 derive 結果),
  供之後任何世代 checkout 該 head 重放驗證(同 S2.0 checkout+rerun 慣例);
- 本片不含任何 install/probe/PREPARE/APPLY 面;W1-W4 逐波擴充本模組時
  不得回頭改寫已發射的歷史 receipt。

九 authority 恆 false;production_apply_performed / running_attested 恆 false。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
for _candidate in (HELPER_DIR, ML_TRAINING_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import aiml_gate_receipt_validator as central_validator  # noqa: E402

W0_RECEIPT_DIRNAME = "S2.4-WP4-W0"
W0_ADMISSION_FILENAME = "S2.4-WP4-W0-source-admission-receipt-v1.json"
W0_WAVE_EXIT_FILENAME = "S2.4-WP4-W0-wave-exit-receipt-v1.json"
W0_DERIVATION_RECORD_FILENAME = "S2.4-WP4-W0-derivation-record.json"


def _git_head(repo_root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def build_w0_source_admission_receipt(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """從活 repo bytes 重算 W0 admission receipt 的每一欄(evidence-only,無 status)。"""

    module_bytes = (repo_root / central_validator._TRUSTED_HOST_MODULE_PATH).read_bytes()
    test_bytes = (repo_root / central_validator._TRUSTED_HOST_TEST_PATH).read_bytes()
    receipt: dict[str, Any] = {
        "schema_version": "s2_4_source_admission_receipt_v1",
        "program_id": "AIML-LONG-LIVED-LANDING-V2",
        "work_package": "WP4",
        "wave": "W0",
        "source_head": _git_head(repo_root),
        "predecessor_heads": dict(central_validator._PREDECESSOR_HEADS),
        "three_head_projection_digest": central_validator.three_head_projection_digest(),
        "trust_pin_digests": {
            "trusted_host_module_blob": central_validator.git_blob_sha1(module_bytes),
            "trusted_host_module_sha256": "sha256:"
            + hashlib.sha256(module_bytes).hexdigest(),
            "independent_test_blob": central_validator.git_blob_sha1(test_bytes),
            "independent_test_sha256": "sha256:"
            + hashlib.sha256(test_bytes).hexdigest(),
            "operator_fingerprint": central_validator._OPERATOR_FINGERPRINT,
        },
        "s2_0_driver_reachability_proof": {
            "adapter_id": "pg_observer_bootstrap_adapter_v1",
            "registry_status": "AUTHORITY_LOCKED_PRODUCTION_CAPABLE",
            "unconditional_production_pending_removed": True,
            "driver_protocol_present": True,
            "production_success_status": "APPLIED",
        },
        "wp3_system_unit_alignment_proof": {
            "lifecycle_owner": "host_system_manager",
            "systemctl_user_absent": True,
            "role": "aiml_engine_scanner",
            "database": "trading_ai",
        },
        "frozen_classifier_digest": central_validator.aiml_effect_classifier_digest(),
        "component_classifier_v1_digest": (
            central_validator.aiml_component_effect_class_matrix_digest()
        ),
        "production_authority_flags": {
            "nine_authorities_false": True,
            "production_apply_performed": False,
            "running_attested": False,
        },
        "negative_tests_pass": central_validator.w0_negative_test_manifest_digest(),
    }
    receipt["self_digest"] = central_validator.artifact_self_digest(receipt)
    return receipt


def build_w0_wave_exit_receipt(
    admission: dict[str, Any],
    *,
    test_digests: list[str],
    capture_digests: list[str],
    review_fragment_digests: list[str],
) -> dict[str, Any]:
    """綁定 admission 與真實 test/capture/review 證據 digest 的 W0 wave-exit(無 status)。"""

    receipt: dict[str, Any] = {
        "schema_version": "s2_4_wave_exit_receipt_v1",
        "wave": "W0",
        "predecessor_wave_receipt_digest": None,
        "source_admission_receipt_digest": admission["self_digest"],
        "source_head": admission["source_head"],
        "owned_path_manifest_digest": central_validator.canonical_digest(
            sorted(central_validator._W0_OWNED_PATHS)
        ),
        "owned_path_diff_digest": central_validator.w0_owned_path_diff_digest(),
        "exported_abi_digest": central_validator.canonical_digest(
            central_validator._W0_EXPORTED_ABI
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


def emit_w0_receipts(
    *,
    repo_root: Path = REPO_ROOT,
    out_dir: Path,
    test_evidence: dict[str, Any],
    review_provenance: list[dict[str, Any]],
) -> dict[str, Any]:
    """發射並持久化正式 W0 receipts;導出非 ADMITTED/PASS 即 fail-closed 不寫檔。

    ``test_evidence`` 是實際測試執行的原始紀錄(command/exit/counts/head);
    ``review_provenance`` 是逐筆 review 事實紀錄(PR、merge head、verdict)。
    兩者都會原樣持久化,receipt 內的 digest 綁定其 canonical bytes,任何人可重驗。
    """

    if not isinstance(test_evidence, dict) or not test_evidence:
        raise ValueError("test_evidence must be a non-empty object")
    if not isinstance(review_provenance, list) or not review_provenance or not all(
        isinstance(item, dict) and item for item in review_provenance
    ):
        raise ValueError("review_provenance must be a non-empty list of objects")

    admission = build_w0_source_admission_receipt(repo_root)
    admission_result = central_validator.derive_source_admission_status(
        admission, repo_root=repo_root
    )
    if admission_result["status"] != "ADMITTED":
        return {
            "status": "W0_EMIT_REFUSED",
            "stage": "source_admission",
            "reasons": admission_result["reasons"],
        }

    wave_exit = build_w0_wave_exit_receipt(
        admission,
        test_digests=[central_validator.canonical_digest(test_evidence)],
        capture_digests=[
            central_validator.canonical_digest(
                {"kind": "raw_local_test_capture", "record": test_evidence}
            )
        ],
        review_fragment_digests=[
            central_validator.canonical_digest(item) for item in review_provenance
        ],
    )
    wave_result = central_validator.derive_wave_exit_status(
        wave_exit, repo_root=repo_root, source_admission_receipt=admission
    )
    if wave_result["status"] != "PASS":
        return {
            "status": "W0_EMIT_REFUSED",
            "stage": "wave_exit",
            "reasons": wave_result["reasons"],
        }

    central_errors = central_validator.validate_aiml_artifact(admission)
    central_errors += central_validator.validate_aiml_artifact(wave_exit)
    if central_errors:
        return {
            "status": "W0_EMIT_REFUSED",
            "stage": "central_gate",
            "reasons": central_errors,
        }

    out_dir.mkdir(parents=True, exist_ok=True)
    derivation_record = {
        "schema_version": "s2_4_w0_derivation_record_v1_informal",
        "source_head": admission["source_head"],
        "admission_derivation": admission_result,
        "wave_exit_derivation": wave_result,
        "admission_self_digest": admission["self_digest"],
        "wave_exit_self_digest": wave_exit["self_digest"],
        "test_evidence": test_evidence,
        "review_provenance": review_provenance,
        "replay_note": (
            "re-derivation binds source_head == checkout HEAD; to replay, checkout "
            "source_head and run derive_source_admission_status/derive_wave_exit_status"
        ),
    }
    for name, artifact in (
        (W0_ADMISSION_FILENAME, admission),
        (W0_WAVE_EXIT_FILENAME, wave_exit),
        (W0_DERIVATION_RECORD_FILENAME, derivation_record),
    ):
        (out_dir / name).write_text(
            json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return {
        "status": "W0_RECEIPTS_EMITTED",
        "out_dir": str(out_dir),
        "source_head": admission["source_head"],
        "admission_self_digest": admission["self_digest"],
        "wave_exit_self_digest": wave_exit["self_digest"],
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    emit = sub.add_parser("w0-emit", help="發射並持久化正式 W0 admission/wave-exit receipts")
    emit.add_argument("--out", required=True, type=Path)
    emit.add_argument("--test-evidence", required=True, type=Path)
    emit.add_argument("--review-provenance", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.action == "w0-emit":
        result = emit_w0_receipts(
            out_dir=args.out,
            test_evidence=json.loads(args.test_evidence.read_text(encoding="utf-8")),
            review_provenance=json.loads(
                args.review_provenance.read_text(encoding="utf-8")
            ),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result["status"] == "W0_RECEIPTS_EMITTED" else 2
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())
