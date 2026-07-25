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
import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
# W2b:alr_application_identity 以 ml_training.* 套件形匯入其 sibling,故 program_code
# 亦須入 path(單獨 CLI 執行時 pytest 的套件根注入不存在)。
PROGRAM_CODE_DIR = REPO_ROOT / "program_code"
for _candidate in (HELPER_DIR, ML_TRAINING_DIR, PROGRAM_CODE_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import aiml_gate_receipt_validator as central_validator  # noqa: E402

W0_RECEIPT_DIRNAME = "S2.4-WP4-W0"
W0_ADMISSION_FILENAME = "S2.4-WP4-W0-source-admission-receipt-v1.json"
W0_WAVE_EXIT_FILENAME = "S2.4-WP4-W0-wave-exit-receipt-v1.json"
W0_DERIVATION_RECORD_FILENAME = "S2.4-WP4-W0-derivation-record.json"
# ── W1(contracts/routing)wave-exit 發射面 ──────────────────────────────────────
# 歷史 W0 receipts 的持久化目錄(其 source_head 為歷史世代;W1 發射時只作 lineage 記錄,
# 「不」直接綁進 derivation 鏈——W0 再導出恆綁「當前」HEAD,故 w1-emit 以同一批 builder 於
# 記憶體內重發當前世代 W0 admission+wave-exit 並綁「那條」鏈)。
W0_RECEIPT_DIR = (
    REPO_ROOT / "docs" / "execution_plan" / "ai_ml_landing" / "receipts" / W0_RECEIPT_DIRNAME
)
W1_RECEIPT_DIRNAME = "S2.4-WP4-W1"
W1_WAVE_EXIT_FILENAME = "S2.4-WP4-W1-wave-exit-receipt-v1.json"
W1_REGENERATED_W0_ADMISSION_FILENAME = (
    "S2.4-WP4-W1-regenerated-W0-source-admission-receipt-v1.json"
)
W1_REGENERATED_W0_WAVE_EXIT_FILENAME = "S2.4-WP4-W1-regenerated-W0-wave-exit-receipt-v1.json"
W1_DERIVATION_RECORD_FILENAME = "S2.4-WP4-W1-derivation-record.json"


def _validate_emit_evidence(
    test_evidence: Any, review_provenance: Any
) -> None:
    """兩個發射器共用的 evidence 防呆(E3 P2-4 含 secret 深掃)。

    persisted evidence 會逐字進入 Git-committed receipt 檔;除形狀檢查外,以中央
    secret-like 內容掃描拒絕任何疑似機密的 evidence——寧可拒發射,不可把密鑰寫進 repo。
    """

    if not isinstance(test_evidence, dict) or not test_evidence:
        raise ValueError("test_evidence must be a non-empty object")
    if not isinstance(review_provenance, list) or not review_provenance or not all(
        isinstance(item, dict) and item for item in review_provenance
    ):
        raise ValueError("review_provenance must be a non-empty list of objects")
    if central_validator._contains_github_secret_like_content(
        test_evidence
    ) or central_validator._contains_github_secret_like_content(review_provenance):
        raise ValueError(
            "emit evidence contains secret-like content; refusing to persist"
        )


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

    _validate_emit_evidence(test_evidence, review_provenance)

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


def build_w1_wave_exit_receipt(
    admission: dict[str, Any],
    predecessor_wave_exit: dict[str, Any],
    *,
    test_digests: list[str],
    capture_digests: list[str],
    review_fragment_digests: list[str],
) -> dict[str, Any]:
    """綁定當前世代 W0 鏈與真實 test/capture/review 證據 digest 的 W1 wave-exit(無 status)。

    W1 面(owned-path/diff/exported-ABI)全由中央 validator 的 code-owned W1 投影於活 repo 重算;
    predecessor 綁 W0 wave-exit 的 self_digest,admission 綁 admission 的 self_digest。
    """

    receipt: dict[str, Any] = {
        "schema_version": "s2_4_wave_exit_receipt_v1",
        "wave": "W1",
        "predecessor_wave_receipt_digest": predecessor_wave_exit["self_digest"],
        "source_admission_receipt_digest": admission["self_digest"],
        "source_head": admission["source_head"],
        "owned_path_manifest_digest": central_validator.canonical_digest(
            sorted(central_validator._W1_OWNED_PATHS)
        ),
        "owned_path_diff_digest": central_validator.w1_owned_path_diff_digest(),
        "exported_abi_digest": central_validator.canonical_digest(
            central_validator.w1_exported_abi_projection()
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


def _load_persisted_w0_receipts(w0_receipt_dir: Path) -> dict[str, Any] | None:
    """讀持久化的歷史 W0 receipts(lineage 記錄用;讀不到/畸形回 None → 發射 fail-closed)。

    E2 P3-2:宣稱的 ``self_digest`` 不可照抄——就地以 ``artifact_self_digest`` 重算比對,
    lineage 記錄同時攜帶完整性判定,竄改過的持久化 receipt 無法把偽 digest 傳播進
    derivation record。
    """

    try:
        admission = json.loads(
            (w0_receipt_dir / W0_ADMISSION_FILENAME).read_text(encoding="utf-8")
        )
        wave_exit = json.loads(
            (w0_receipt_dir / W0_WAVE_EXIT_FILENAME).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(admission, dict) or not isinstance(wave_exit, dict):
        return None
    if not admission.get("self_digest") or not wave_exit.get("self_digest"):
        return None
    integrity = (
        "VERIFIED"
        if (
            admission["self_digest"]
            == central_validator.artifact_self_digest(admission)
            and wave_exit["self_digest"]
            == central_validator.artifact_self_digest(wave_exit)
        )
        else "SELF_DIGEST_MISMATCH"
    )
    return {
        "persisted_dir": str(w0_receipt_dir),
        "admission_self_digest": admission["self_digest"],
        "wave_exit_self_digest": wave_exit["self_digest"],
        "historical_source_head": admission.get("source_head"),
        "historical_w0_integrity": integrity,
    }


def emit_w1_receipts(
    *,
    repo_root: Path = REPO_ROOT,
    out_dir: Path,
    test_evidence: dict[str, Any],
    review_provenance: list[dict[str, Any]],
    w0_receipt_dir: Path = W0_RECEIPT_DIR,
) -> dict[str, Any]:
    """發射並持久化正式 W1 wave-exit receipt;任一導出非 ADMITTED/PASS 即 fail-closed 不寫檔。

    鏈路(鏡 w0-emit;§10.3 W1 row):
      1. 讀持久化的歷史 W0 receipts 作 lineage 記錄——其 source_head 為歷史世代,而 W0 再導出
         恆綁「當前」checkout HEAD,故「不可」直接綁進 derivation 鏈;
      2. 以同一批 builder 於記憶體內重發「當前世代」W0 admission + wave-exit 並逐段導出
         ADMITTED/PASS(admission 鏈不因跨波而鬆脫);
      3. 構建 W1 wave-exit 綁定該當前世代鏈,由中央 validator 導出 W1 PASS(predecessor +
         admission 雙綁定);
      4. 中央閘結構驗全過後,持久化 W1 receipt + 當前世代 W0 鏈 + derivation record(含歷史
         W0 digests 的 lineage)。
    """

    _validate_emit_evidence(test_evidence, review_provenance)

    historical_w0 = _load_persisted_w0_receipts(w0_receipt_dir)
    if historical_w0 is None:
        return {
            "status": "W1_EMIT_REFUSED",
            "stage": "historical_w0_receipts",
            "reasons": [
                f"persisted W0 receipts are unreadable or malformed under {w0_receipt_dir}"
            ],
        }
    # PM 裁決(E2 recheck P3):竄改過的歷史 lineage 不是「可註記後續行」的資訊——它意味
    # repo 內的治理 receipt 曾被改寫,屬停機調查事件;硬拒發射,對齊 fail-closed 文化。
    if historical_w0.get("historical_w0_integrity") != "VERIFIED":
        return {
            "status": "W1_EMIT_REFUSED",
            "stage": "historical_w0_receipts",
            "reasons": [
                "persisted W0 receipts fail self-digest verification "
                "(tampered governance history; investigate before any W1 emission)"
            ],
        }

    # 當前世代 W0 admission(記憶體重發;同 builder,綁當前 HEAD/repo bytes)。
    admission = build_w0_source_admission_receipt(repo_root)
    admission_result = central_validator.derive_source_admission_status(
        admission, repo_root=repo_root
    )
    if admission_result["status"] != "ADMITTED":
        return {
            "status": "W1_EMIT_REFUSED",
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

    w0_wave_exit = build_w0_wave_exit_receipt(
        admission,
        test_digests=test_digests,
        capture_digests=capture_digests,
        review_fragment_digests=review_digests,
    )
    w0_result = central_validator.derive_wave_exit_status(
        w0_wave_exit, repo_root=repo_root, source_admission_receipt=admission
    )
    if w0_result["status"] != "PASS":
        return {
            "status": "W1_EMIT_REFUSED",
            "stage": "regenerated_w0_wave_exit",
            "reasons": w0_result["reasons"],
        }

    w1_wave_exit = build_w1_wave_exit_receipt(
        admission,
        w0_wave_exit,
        test_digests=test_digests,
        capture_digests=capture_digests,
        review_fragment_digests=review_digests,
    )
    w1_result = central_validator.derive_wave_exit_status(
        w1_wave_exit,
        repo_root=repo_root,
        source_admission_receipt=admission,
        predecessor_wave_receipt=w0_wave_exit,
    )
    if w1_result["status"] != "PASS":
        return {
            "status": "W1_EMIT_REFUSED",
            "stage": "w1_wave_exit",
            "reasons": w1_result["reasons"],
        }

    central_errors = central_validator.validate_aiml_artifact(admission)
    central_errors += central_validator.validate_aiml_artifact(w0_wave_exit)
    central_errors += central_validator.validate_aiml_artifact(w1_wave_exit)
    if central_errors:
        return {
            "status": "W1_EMIT_REFUSED",
            "stage": "central_gate",
            "reasons": central_errors,
        }

    out_dir.mkdir(parents=True, exist_ok=True)
    derivation_record = {
        "schema_version": "s2_4_w1_derivation_record_v1_informal",
        "source_head": admission["source_head"],
        "admission_derivation": admission_result,
        "regenerated_w0_wave_exit_derivation": w0_result,
        "w1_wave_exit_derivation": w1_result,
        "admission_self_digest": admission["self_digest"],
        "regenerated_w0_wave_exit_self_digest": w0_wave_exit["self_digest"],
        "w1_wave_exit_self_digest": w1_wave_exit["self_digest"],
        # lineage:歷史持久化 W0 的 digests/世代(僅記錄;derivation 綁的是當前世代重發鏈)。
        "historical_persisted_w0": historical_w0,
        "test_evidence": test_evidence,
        "review_provenance": review_provenance,
        "replay_note": (
            "W1 re-derivation binds source_head == checkout HEAD; to replay, checkout "
            "source_head, rebuild the in-memory W0 chain with the same builders, then run "
            "derive_wave_exit_status(w1, source_admission_receipt=admission, "
            "predecessor_wave_receipt=w0_wave_exit)"
        ),
    }
    for name, artifact in (
        (W1_WAVE_EXIT_FILENAME, w1_wave_exit),
        (W1_REGENERATED_W0_ADMISSION_FILENAME, admission),
        (W1_REGENERATED_W0_WAVE_EXIT_FILENAME, w0_wave_exit),
        (W1_DERIVATION_RECORD_FILENAME, derivation_record),
    ):
        (out_dir / name).write_text(
            json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return {
        "status": "W1_RECEIPTS_EMITTED",
        "out_dir": str(out_dir),
        "source_head": admission["source_head"],
        "admission_self_digest": admission["self_digest"],
        "regenerated_w0_wave_exit_self_digest": w0_wave_exit["self_digest"],
        "w1_wave_exit_self_digest": w1_wave_exit["self_digest"],
        "historical_persisted_w0": historical_w0,
    }


# --------------------------------------------------------------------------- #
# W2a(§2.1/§10.5 #23)engine-scanner retention split + closed PG ACL 靜態執法。
#
# 契約:PASS 只能由本檔對 repo 當前 checkout 的三段再導出「同時」成立而導出——
#   (a) 靜態 AST import 閉包內,post-split consumer 對 retention apply 面零可達
#       (含 lazy/條件 import;閉包同時走 ml_training 與 maintenance_scripts 兩域);
#   (b) 靜態 SQL inventory(consumer 模組 + 其 PG data-plane repository 閉包)不含
#       任何 DELETE、任何 retention-table mutation、任何不可解析/不可分類語句;
#   (c) inventory 導出的必要權限與 pg_acl_manifest_v1.json 雙向 exact-match
#       (unlisted statement 或 over-grant 皆 fail),且 manifest 過中央閘結構驗。
# 任一不成立 → typed ENGINE_SCANNER_PRIVILEGE_SPLIT_REQUIRED(§10.2)。此為 SOURCE
# 靜態執法,「不」認證任何 runtime;disposable-PG trace 證明屬 sibling 測試。
# --------------------------------------------------------------------------- #
_ENGINE_SCANNER_ENTRY_MODULE = "alr_event_consumer"
_ENGINE_SCANNER_ROLE = "aiml_engine_scanner"
_PG_ACL_MANIFEST_REL = "program_code/ml_training/pg_acl_manifest_v1.json"
_ML_TRAINING_REL = "program_code/ml_training"
_HELPER_SCRIPTS_REL = "helper_scripts/maintenance_scripts"
# §2.1:retention apply 面(decision + repository)必須自 engine-scanner 進程不可達。
_RETENTION_FORBIDDEN_MODULES = ("alr_retention_guardian", "alr_retention_repository")
# retention-owned 資料表:consumer 對其只允許唯讀(health 計數);任何 mutation 即違規。
_RETENTION_TABLES = (
    "learning.alr_derived_cache_entries",
    "learning.alr_retention_events",
)
# SQL-scan 唯一排除(理由必須成立且入 verdict):parquet_etl 是 duckdb 本地 ETL 面——其
# execute 綁 duckdb 連線與動態檔案路徑,非本進程的 PG data-plane;server-side ACL 由
# manifest + disposable trace 執法,不受客戶端字串影響。排除「不」適用於 (a) 的 import
# 可達性檢查(closure 仍完整走訪)。
_ENGINE_SCANNER_SQL_SCAN_EXCLUDED = {
    "parquet_etl": "duckdb_local_etl_surface_not_pg_data_plane",
}
# 進 manifest functions 段的 pg_catalog advisory-lock 家族(PUBLIC-default EXECUTE)。
_ADVISORY_FUNCTION_NAMES = ("hashtext", "pg_advisory_unlock", "pg_try_advisory_lock")
_ADVISORY_FUNCTION_RE = re.compile(
    r"\b(hashtext|pg_advisory_unlock|pg_try_advisory_lock)\s*\("
)
_QUALIFIED_TABLE_RE = re.compile(r"\b(?:trading|learning)\.[a-z_][a-z0-9_]*")
_INSERT_TARGET_RE = re.compile(
    r"^\s*INSERT\s+INTO\s+((?:trading|learning)\.[a-z_][a-z0-9_]*)", re.IGNORECASE
)
_UPDATE_TARGET_RE = re.compile(
    r"^\s*UPDATE\s+((?:trading|learning)\.[a-z_][a-z0-9_]*)", re.IGNORECASE
)
_DELETE_TARGET_RE = re.compile(
    r"^\s*DELETE\s+FROM\s+((?:trading|learning)\.[a-z_][a-z0-9_]*)", re.IGNORECASE
)
_RELATION_KEYWORD_RE = re.compile(
    r"\b(?:FROM|JOIN|INTO|UPDATE)\s+([A-Za-z_][A-Za-z0-9_.]*)", re.IGNORECASE
)
_CTE_NAME_RE = re.compile(r"(?:\bWITH\s+|,\s*)([a-z_][a-z0-9_]*)\s+AS\s*\(", re.IGNORECASE)
_SAFE_SQL_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
_SAFE_SQL_QUALIFIED_RE = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$")


class _SqlUnresolvable(Exception):
    """一個 execute 第一參數無法靜態解析為常量 SQL(fail-closed 進 unresolved)。"""


def _engine_scanner_import_names(tree: ast.AST) -> set[str]:
    """收集模組內全部 import 名(含函式內 lazy import 與 `from ml_training import X`)。"""

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
            if node.module == "ml_training":
                for alias in node.names:
                    names.add("ml_training." + alias.name)
    return names


def _engine_scanner_resolve_module(repo_root: Path, name: str) -> tuple[str, Path] | None:
    """把 import 名解析為 repo 內檔案(ml_training 優先,再 maintenance_scripts)。"""

    short = name.split(".", 1)[1] if name.startswith("ml_training.") else name
    if "." in short:
        return None
    for base_rel in (_ML_TRAINING_REL, _HELPER_SCRIPTS_REL):
        candidate = repo_root / base_rel / f"{short}.py"
        if candidate.is_file():
            return short, candidate
    return None


def _engine_scanner_import_closure(repo_root: Path) -> dict[str, Path]:
    """自 consumer 起的完整靜態 import 閉包(fail-closed:解析錯誤即 raise)。"""

    closure: dict[str, Path] = {}
    stack = ["ml_training." + _ENGINE_SCANNER_ENTRY_MODULE]
    while stack:
        resolved = _engine_scanner_resolve_module(repo_root, stack.pop())
        if resolved is None:
            continue
        short, path = resolved
        if short in closure:
            continue
        closure[short] = path
        tree = ast.parse(path.read_text(encoding="utf-8"))
        stack.extend(sorted(_engine_scanner_import_names(tree)))
    return closure


def _resolve_sql_strings(
    node: ast.AST,
    module_consts: dict[str, str],
    local_consts: dict[str, set[str]],
) -> set[str]:
    """把 execute 第一參數解析為常量 SQL 變體集合(分支/條件展開;無法解析即 raise)。"""

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        lefts = _resolve_sql_strings(node.left, module_consts, local_consts)
        rights = _resolve_sql_strings(node.right, module_consts, local_consts)
        return {left + right for left in lefts for right in rights}
    if isinstance(node, ast.Name):
        if node.id in local_consts:
            return set(local_consts[node.id])
        if node.id in module_consts:
            return {module_consts[node.id]}
        raise _SqlUnresolvable(f"name:{node.id}")
    if isinstance(node, ast.IfExp):
        return _resolve_sql_strings(node.body, module_consts, local_consts) | (
            _resolve_sql_strings(node.orelse, module_consts, local_consts)
        )
    if isinstance(node, ast.JoinedStr):
        variants = {""}
        for value in node.values:
            parts = _resolve_sql_strings(value, module_consts, local_consts)
            variants = {variant + part for variant in variants for part in parts}
        return variants
    if isinstance(node, ast.FormattedValue):
        return _resolve_sql_strings(node.value, module_consts, local_consts)
    raise _SqlUnresolvable(f"node:{type(node).__name__}")


def _module_sql_statements(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """抽取一個模組內每個 ``*.execute(...)`` 的常量 SQL 變體(deterministic)。"""

    tree = ast.parse(path.read_text(encoding="utf-8"))
    module_consts: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            try:
                values = _resolve_sql_strings(node.value, module_consts, {})
            except _SqlUnresolvable:
                continue
            if len(values) == 1:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        module_consts[target.id] = next(iter(values))
    statements: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        local_consts: dict[str, set[str]] = {}
        for node in ast.walk(func):
            if isinstance(node, ast.Assign):
                try:
                    values = _resolve_sql_strings(node.value, module_consts, local_consts)
                except _SqlUnresolvable:
                    continue
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        local_consts.setdefault(target.id, set()).update(values)
        for node in ast.walk(func):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"execute", "executemany"}
                and node.args
            ):
                try:
                    values = _resolve_sql_strings(
                        node.args[0], module_consts, local_consts
                    )
                except _SqlUnresolvable as exc:
                    unresolved.append({
                        "function": func.name,
                        "line": node.lineno,
                        "reason": str(exc),
                    })
                    continue
                for statement in sorted(values):
                    statements.append({
                        "function": func.name,
                        "line": node.lineno,
                        "statement": statement,
                    })
    return statements, unresolved


def _statement_unqualified_relations(sql: str) -> list[str]:
    """找出未以 trading./learning. 限定、又非 CTE 名的關聯目標(fail-closed)。"""

    cte_names = {match.group(1).lower() for match in _CTE_NAME_RE.finditer(sql)}
    violations: list[str] = []
    for match in _RELATION_KEYWORD_RE.finditer(sql):
        name = match.group(1)
        if "." in name:
            if _QUALIFIED_TABLE_RE.fullmatch(name.lower()) is None:
                violations.append(name)
            continue
        # LATERAL 是 JOIN 後的結構關鍵字(如 JOIN LATERAL (subquery)),非關聯名。
        if name.lower() == "lateral":
            continue
        if name.lower() in cte_names:
            continue
        violations.append(name)
    return sorted(set(violations))


def _classify_sql_statement(sql: str) -> dict[str, Any]:
    """把一條常量 SQL 分類並導出必要權限;無法分類即回 errors(fail-closed)。"""

    head = sql.strip().split()[0].upper() if sql.strip() else ""
    tables: dict[str, set[str]] = {}
    errors: list[str] = []
    mutation = False
    referenced = sorted({match.lower() for match in _QUALIFIED_TABLE_RE.findall(sql)})
    if head in {"SELECT", "WITH"}:
        statement_class = "read"
        for table in referenced:
            tables.setdefault(table, set()).add("SELECT")
    elif head == "INSERT":
        statement_class = "insert"
        target_match = _INSERT_TARGET_RE.match(sql)
        if target_match is None:
            errors.append("insert_target_not_schema_qualified")
        else:
            target = target_match.group(1).lower()
            tables.setdefault(target, set()).add("INSERT")
            # PG 語義:INSERT .. ON CONFLICT 需讀 arbiter 欄位 → 目標表另需 SELECT
            # (disposable trace 以真 42501 實證;見 W2a 佐證測試)。
            if re.search(r"\bON\s+CONFLICT\b", sql, re.IGNORECASE):
                tables[target].add("SELECT")
            for table in referenced:
                if table != target:
                    tables.setdefault(table, set()).add("SELECT")
    elif head == "UPDATE":
        statement_class = "update"
        mutation = True
        target_match = _UPDATE_TARGET_RE.match(sql)
        if target_match is None:
            errors.append("update_target_not_schema_qualified")
        else:
            tables.setdefault(target_match.group(1).lower(), set()).add("UPDATE")
    elif head == "DELETE":
        statement_class = "delete"
        mutation = True
        target_match = _DELETE_TARGET_RE.match(sql)
        if target_match is None:
            errors.append("delete_target_not_schema_qualified")
        else:
            tables.setdefault(target_match.group(1).lower(), set()).add("DELETE")
    elif head == "LISTEN":
        statement_class = "listen"
    else:
        statement_class = "unrecognized"
        errors.append(f"unrecognized_statement_class:{head or 'EMPTY'}")
    if statement_class != "listen":
        for name in _statement_unqualified_relations(sql):
            errors.append(f"unqualified_relation:{name}")
    functions = sorted({match for match in _ADVISORY_FUNCTION_RE.findall(sql)})
    return {
        "statement_class": statement_class,
        "tables": {name: sorted(privileges) for name, privileges in tables.items()},
        "functions": [f"pg_catalog.{name}" for name in functions],
        "mutation": mutation,
        "errors": errors,
    }


def build_engine_scanner_sql_inventory(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """post-split consumer 的 deterministic 靜態 SQL inventory(§10.5 #23 的 SOURCE 面)。

    inventory 同時攜帶:完整 import 閉包(retention 可達性證據)、逐條語句的分類/
    權限導出、unresolved/violation 清單、與聚合 required_privileges。任何 caller
    不可自帶 PASS;裁決一律經 :func:`derive_engine_scanner_privilege_split`。
    """

    closure = _engine_scanner_import_closure(repo_root)
    retention_reachable = sorted(
        name for name in _RETENTION_FORBIDDEN_MODULES if name in closure
    )
    ml_dir = (repo_root / _ML_TRAINING_REL).resolve()
    statements: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    violations: list[str] = []
    scanned: list[str] = []
    for name in sorted(closure):
        path = closure[name]
        if path.resolve().parent != ml_dir:
            continue  # 治理 helper 域不屬 PG data-plane(import 可達性已在 closure 覆蓋)
        if name in _ENGINE_SCANNER_SQL_SCAN_EXCLUDED:
            continue
        scanned.append(name)
        module_statements, module_unresolved = _module_sql_statements(path)
        for entry in module_unresolved:
            unresolved.append({"module": name, **entry})
        for entry in module_statements:
            classified = _classify_sql_statement(entry["statement"])
            record = {"module": name, **entry, **classified}
            statements.append(record)
            for error in classified["errors"]:
                violations.append(
                    f"{name}:{entry['function']}:{entry['line']}:{error}"
                )
            if classified["statement_class"] == "delete":
                violations.append(
                    f"{name}:{entry['function']}:{entry['line']}:delete_statement_forbidden"
                )
            if classified["mutation"] and any(
                table in _RETENTION_TABLES for table in classified["tables"]
            ):
                violations.append(
                    f"{name}:{entry['function']}:{entry['line']}:retention_table_mutation"
                )
            if classified["statement_class"] == "insert" and any(
                table in _RETENTION_TABLES and "INSERT" in privileges
                for table, privileges in classified["tables"].items()
            ):
                violations.append(
                    f"{name}:{entry['function']}:{entry['line']}:retention_table_mutation"
                )
    statements.sort(key=lambda item: (item["module"], item["line"], item["statement"]))
    required_tables: dict[str, set[str]] = {}
    required_functions: set[str] = set()
    for record in statements:
        for table, privileges in record["tables"].items():
            required_tables.setdefault(table, set()).update(privileges)
        required_functions.update(record["functions"])
    required_schemas = sorted({table.split(".", 1)[0] for table in required_tables})
    return {
        "schema_version": "engine_scanner_sql_inventory_v1",
        "entry_module": f"ml_training.{_ENGINE_SCANNER_ENTRY_MODULE}",
        "import_closure": sorted(closure),
        "sql_scanned_modules": scanned,
        "sql_scan_excluded": dict(_ENGINE_SCANNER_SQL_SCAN_EXCLUDED),
        "retention_forbidden_reachable": retention_reachable,
        "statements": statements,
        "unresolved": sorted(
            unresolved, key=lambda item: (item["module"], item["line"], item["reason"])
        ),
        "violations": sorted(set(violations)),
        "required_privileges": {
            "schemas": required_schemas,
            "tables": {
                table: sorted(privileges)
                for table, privileges in sorted(required_tables.items())
            },
            "functions": sorted(required_functions),
        },
    }


def derive_engine_scanner_privilege_split(
    repo_root: Path = REPO_ROOT,
    *,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    """§2.1/§10.5 #23 的中央再導出裁決(typed;caller 不可自證 PASS)。

    PASS ⇔ (a) retention 面 import 不可達 ∧ (b) inventory 零 DELETE/零 retention
    mutation/零 unresolved/零 violation ∧ (c) inventory 必要權限與 manifest 雙向
    exact-match 且 manifest 過中央閘。否則 ENGINE_SCANNER_PRIVILEGE_SPLIT_REQUIRED
    (§10.2 typed terminal failure)+ 逐項 reasons。
    """

    reasons: list[str] = []
    inventory = build_engine_scanner_sql_inventory(repo_root)
    for module in inventory["retention_forbidden_reachable"]:
        reasons.append(f"retention module is import-reachable from the consumer: {module}")
    for entry in inventory["unresolved"]:
        reasons.append(
            "sql statement is not statically resolvable: "
            f"{entry['module']}:{entry['line']}:{entry['reason']}"
        )
    reasons.extend(
        f"sql inventory violation: {violation}" for violation in inventory["violations"]
    )

    manifest_file = manifest_path or (repo_root / _PG_ACL_MANIFEST_REL)
    manifest: dict[str, Any] | None = None
    try:
        loaded = json.loads(Path(manifest_file).read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            manifest = loaded
        else:
            reasons.append("pg acl manifest is not an object")
    except (OSError, json.JSONDecodeError) as error:
        reasons.append(f"pg acl manifest is unreadable: {error}")

    manifest_digest: str | None = None
    if manifest is not None:
        central_errors = central_validator.validate_aiml_artifact(manifest)
        reasons.extend(f"pg acl manifest rejected: {error}" for error in central_errors)
        if not central_errors:
            manifest_digest = manifest["self_digest"]
            expected_database = central_validator._consumer_authoritative_database(
                repo_root
            )
            if expected_database is None:
                reasons.append(
                    "consumer authoritative database cannot be re-derived from the checkout"
                )
            elif manifest["database"]["name"] != expected_database:
                reasons.append(
                    "pg acl manifest database differs from the consumer authoritative DSN"
                )
            if manifest["role_name"] != _ENGINE_SCANNER_ROLE:
                reasons.append("pg acl manifest role_name is not the engine-scanner role")
            required = inventory["required_privileges"]
            manifest_tables = {
                entry["name"]: sorted(entry["privileges"])
                for entry in manifest["tables"]
            }
            for table, privileges in required["tables"].items():
                granted = manifest_tables.get(table)
                if granted is None:
                    reasons.append(f"inventoried statement privilege is unlisted: {table}")
                    continue
                missing = sorted(set(privileges) - set(granted))
                if missing:
                    reasons.append(
                        f"inventoried statement privilege is unlisted: {table} "
                        f"{','.join(missing)}"
                    )
            for table, granted in manifest_tables.items():
                exercised = required["tables"].get(table, [])
                extra = sorted(set(granted) - set(exercised))
                if table not in required["tables"]:
                    reasons.append(f"manifest table grant is never exercised: {table}")
                elif extra:
                    reasons.append(
                        f"manifest table grant is never exercised: {table} "
                        f"{','.join(extra)}"
                    )
            manifest_schemas = sorted(entry["name"] for entry in manifest["schemas"])
            if manifest_schemas != required["schemas"]:
                reasons.append(
                    "manifest schemas differ from the inventoried schema set: "
                    f"manifest={manifest_schemas} required={required['schemas']}"
                )
            manifest_functions = sorted(entry["name"] for entry in manifest["functions"])
            if manifest_functions != required["functions"]:
                reasons.append(
                    "manifest functions differ from the inventoried function set: "
                    f"manifest={manifest_functions} required={required['functions']}"
                )
            if manifest["sequences"]:
                reasons.append("manifest sequences must stay empty (no sequence is exercised)")

    status = "PASS" if not reasons else "ENGINE_SCANNER_PRIVILEGE_SPLIT_REQUIRED"
    return {
        "schema_version": "engine_scanner_privilege_split_verdict_v1",
        "status": status,
        "reasons": reasons,
        "entry_module": inventory["entry_module"],
        "import_closure_size": len(inventory["import_closure"]),
        "statement_count": len(inventory["statements"]),
        "retention_forbidden_reachable": inventory["retention_forbidden_reachable"],
        "required_privileges": inventory["required_privileges"],
        "sql_scan_excluded": inventory["sql_scan_excluded"],
        "manifest_digest": manifest_digest,
        "sql_inventory_digest": central_validator.canonical_digest(inventory),
        "production_authority_flags": {
            "nine_authorities_false": True,
            "production_apply_performed": False,
            "running_attested": False,
        },
    }


def generate_engine_scanner_grant_sql(manifest: dict[str, Any]) -> list[str]:
    """由 manifest 生成 deterministic REVOKE/GRANT 序列(disposable trace 專用)。

    僅供 throwaway cluster 佐證:語句嚴格由 manifest 導出——無 ALL-on-schema
    wildcard、無 GRANT OPTION、無 role membership、無 CREATE/TEMP/OWNER。identifier
    先過白名單正則(拒注入),角色建立(含 credential)不在此生成器內。
    """

    errors = central_validator.validate_aiml_artifact(manifest)
    if errors:
        raise ValueError(f"pg acl manifest rejected: {errors[0]}")
    role = manifest["role_name"]
    database = manifest["database"]["name"]
    if not _SAFE_SQL_IDENT_RE.fullmatch(role) or not _SAFE_SQL_IDENT_RE.fullmatch(database):
        raise ValueError("pg acl manifest identifiers are not safe SQL identifiers")
    attributes = manifest["role_attributes"]
    statements = [
        f'ALTER ROLE "{role}" NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT '
        f'NOREPLICATION NOBYPASSRLS CONNECTION LIMIT {int(attributes["connection_limit"])}',
        f'REVOKE ALL PRIVILEGES ON DATABASE "{database}" FROM "{role}"',
        f'GRANT CONNECT ON DATABASE "{database}" TO "{role}"',
    ]
    for entry in manifest["schemas"]:
        schema = entry["name"]
        if not _SAFE_SQL_IDENT_RE.fullmatch(schema):
            raise ValueError("pg acl manifest schema name is not a safe SQL identifier")
        statements.append(f'REVOKE ALL ON SCHEMA "{schema}" FROM "{role}"')
        statements.append(f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}"')
    for entry in manifest["tables"]:
        table = entry["name"]
        if not _SAFE_SQL_QUALIFIED_RE.fullmatch(table):
            raise ValueError("pg acl manifest table name is not a safe SQL identifier")
        schema, relation = table.split(".", 1)
        qualified = f'"{schema}"."{relation}"'
        statements.append(f'REVOKE ALL ON TABLE {qualified} FROM "{role}"')
        statements.append(
            f'GRANT {", ".join(sorted(entry["privileges"]))} ON TABLE {qualified} TO "{role}"'
        )
    return statements


# --------------------------------------------------------------------------- #
# W2b(§8.1/§10.5 #17)application closure allowlist + application-bundle manifest
# builder。
#
# 契約:
#   (a) checked-in allowlist(application_bundle_runtime_closure_v1.json)必須與
#       「靜態 runtime import 閉包」雙向 exact-match——閉包 = entrypoint 起的 top-level
#       transitive 匯入 + allowlist 顯式宣告的 runtime-reachable lazy helper 根
#       (§8.1:undeclared runtime import 即 escape;declared-but-unreachable 即漂移);
#   (b) 每個宣告路徑過 deny 謂詞:tests/caches/.pyc/.git/mutable 產物、effect-capable
#       deploy/rollback driver、broker/order 模組、credential 材料、symlink、路徑逃逸;
#   (c) manifest 只從「bound source head 的 committed blobs」產出(git ls-tree/cat-file,
#       非 working tree);任一 allowlist 路徑 dirty/未提交 → typed 拒絕;
#   (d) canonical 文件構造點共用 ml_training.alr_application_identity(runtime 整樹重算
#       與 builder 不可能分歧);digest == application_bundle_digest(§8.1 #3)。
# 全部 SOURCE 靜態執法,「不」認證任何 runtime;九 authority 恆 false。
# --------------------------------------------------------------------------- #
import alr_application_identity as _app_identity  # noqa: E402(ml_training 已入 sys.path)
import learning_runtime_manifest as _lrm  # noqa: E402

_APP_CLOSURE_REL = _app_identity.RUNTIME_CLOSURE_REL
# effect-capable / broker-order / credential 的 deny 謂詞(§8.1 builder rejects)。
_BUNDLE_FORBIDDEN_PATH_MARKERS = ("/tests/", "/__pycache__/", "/.git/")
_BUNDLE_FORBIDDEN_PATH_PREFIXES = (
    ".git/",
    "docs/CCAgentWorkSpace/",
    "memory/",
    "program_code/api/",
    "rust/",
)
_BUNDLE_FORBIDDEN_SUFFIXES = (".pyc", ".pyo", ".pem", ".key", ".p12", ".pfx")
# helper_scripts/deploy 下只允許宣告過的非可執行 template 資源;任何 .py/.sh 都是
# effect-capable deployment driver。
_BUNDLE_FORBIDDEN_DEPLOY_CODE_SUFFIXES = (".py", ".sh")
_EFFECT_CAPABLE_MODULE_MARKERS = ("_effects", "_install_driver", "_deploy")
_EFFECT_CAPABLE_MODULE_NAMES = frozenset({
    "agent_governance_s2_4_install",
    "agent_governance_s2_4_install_driver",
    "agent_governance_pg_observer_bootstrap",
    "agent_governance_alr_quiesce_fence",
    "agent_governance_execution",
})
_BROKER_ORDER_MODULE_MARKERS = ("bybit", "ibkr", "broker", "order_", "_order")


def _toplevel_import_names(tree: ast.Module) -> set[str]:
    """只收 module top-level 的 import 名(runtime 啟動即載入的邊;lazy 邊另行顯式宣告)。"""
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
            if node.module == "ml_training":
                for alias in node.names:
                    names.add("ml_training." + alias.name)
    return names


def build_engine_scanner_runtime_import_closure(
    repo_root: Path = REPO_ROOT,
    *,
    lazy_helper_roots: tuple[str, ...] = (),
) -> dict[str, str]:
    """entrypoint 起的 top-level transitive 閉包 + 顯式 lazy helper 根 → {module: rel_path}。"""
    closure: dict[str, str] = {}
    stack = ["ml_training." + _ENGINE_SCANNER_ENTRY_MODULE, *lazy_helper_roots]
    while stack:
        resolved = _engine_scanner_resolve_module(repo_root, stack.pop())
        if resolved is None:
            continue
        short, path = resolved
        if short in closure:
            continue
        closure[short] = path.resolve().relative_to(repo_root.resolve()).as_posix()
        stack.extend(sorted(_toplevel_import_names(
            ast.parse(path.read_text(encoding="utf-8"))
        )))
    return closure


def _bundle_path_deny_reasons(rel: str) -> list[str]:
    """§8.1 deny 謂詞:單一宣告路徑的全部拒絕理由(空列表 = 通過)。"""
    reasons: list[str] = []
    probe = "/" + rel + "/"
    if rel.startswith("/") or ".." in rel.split("/"):
        reasons.append(f"path escapes the bundle root: {rel}")
    for marker in _BUNDLE_FORBIDDEN_PATH_MARKERS:
        if marker in probe:
            reasons.append(f"forbidden path family (tests/caches/git): {rel}")
            break
    for prefix in _BUNDLE_FORBIDDEN_PATH_PREFIXES:
        if rel.startswith(prefix):
            reasons.append(f"forbidden mutable/effect path prefix: {rel}")
            break
    if rel.endswith(_BUNDLE_FORBIDDEN_SUFFIXES):
        reasons.append(f"forbidden cache/credential material suffix: {rel}")
    if rel.startswith("helper_scripts/deploy/") and rel.endswith(
        _BUNDLE_FORBIDDEN_DEPLOY_CODE_SUFFIXES
    ):
        reasons.append(f"effect-capable deployment driver: {rel}")
    module_name = rel.rsplit("/", 1)[-1].removesuffix(".py")
    if rel.endswith(".py"):
        if module_name in _EFFECT_CAPABLE_MODULE_NAMES or any(
            marker in module_name for marker in _EFFECT_CAPABLE_MODULE_MARKERS
        ):
            reasons.append(f"effect-capable driver module: {rel}")
        if any(marker in module_name for marker in _BROKER_ORDER_MODULE_MARKERS):
            reasons.append(f"broker/order module: {rel}")
    return reasons


def derive_application_runtime_closure_status(
    repo_root: Path = REPO_ROOT,
    *,
    closure_path: Path | None = None,
) -> dict[str, Any]:
    """§8.1/§10.5 #17 的中央再導出裁決(typed;caller 不可自證 PASS)。

    PASS ⇔ (a) allowlist 過中央閘 ∧ (b) python_modules 與「靜態 runtime import 閉包 +
    package init」雙向 exact-match ∧ (c) 全部宣告路徑過 deny 謂詞且為 repo 內既存常規檔
    (非 symlink)∧ (d) 資源段與 SSOT 常量同步(learning_runtime_manifest 的 v2 輸入面、
    migration span、dependency lock 雙檔、policy template、SCHEMA_FILES 註冊表)。
    """
    reasons: list[str] = []
    file_path = closure_path or (repo_root / _APP_CLOSURE_REL)
    try:
        closure = _app_identity.load_runtime_closure(Path(file_path))
    except _app_identity.AlrApplicationIdentityError as error:
        return {
            "schema_version": "application_runtime_closure_verdict_v1",
            "status": "APPLICATION_BUNDLE_CLOSURE_INVALID",
            "reasons": [f"runtime closure allowlist rejected: {error.code}"],
            "closure_digest": None,
            "declared_path_count": 0,
            "production_authority_flags": {
                "nine_authorities_false": True,
                "production_apply_performed": False,
                "running_attested": False,
            },
        }

    lazy_roots = tuple(
        entry["module"] for entry in closure["runtime_lazy_helper_roots"]
    )
    derived = build_engine_scanner_runtime_import_closure(
        repo_root, lazy_helper_roots=lazy_roots
    )
    derived_paths = sorted(set(derived.values()))
    declared_modules = list(closure["python_modules"])
    for rel in sorted(set(derived_paths) - set(declared_modules)):
        reasons.append(f"runtime import escapes the declared closure: {rel}")
    for rel in sorted(set(declared_modules) - set(derived_paths)):
        reasons.append(f"declared module is not runtime-import-reachable: {rel}")

    declared_all = _app_identity.closure_declared_paths(closure)
    for rel in declared_all:
        reasons.extend(_bundle_path_deny_reasons(rel))
        path = repo_root / rel
        if path.is_symlink():
            reasons.append(f"declared path is a symlink: {rel}")
        elif not path.is_file():
            reasons.append(f"declared path is not an existing regular file: {rel}")

    # SSOT 常量同步:runtime preflight 的每個真實檔案讀取面必須被宣告(§8.1)。
    expected_inputs = sorted(
        set(_lrm.CAPTURE_INPUTS)
        | set(_lrm.LEARNING_CODE_INPUTS_V2)
        | {_lrm.REGIME_OOS_LABEL_CONTRACT}
    )
    if list(closure["learning_runtime_inputs"]) != expected_inputs:
        reasons.append(
            "learning_runtime_inputs differ from the learning_runtime_manifest v2 SSOT"
        )
    if list(closure["sql_fingerprints"]) != sorted(_lrm.MIGRATION_INPUTS):
        reasons.append("sql_fingerprints differ from the migration-span SSOT")
    if list(closure["dependency_lock_files"]) != sorted(
        {_lrm.DEPENDENCY_LOCK_SPEC_FILE, _lrm.DEPENDENCY_LOCK_LOCK_FILE}
    ):
        reasons.append("dependency_lock_files differ from the dependency-lock SSOT")
    if closure["policy_template"] != _lrm.POLICY_TEMPLATE:
        reasons.append("policy_template differs from the learning_runtime_manifest SSOT")
    expected_schemas = sorted(
        "program_code/ml_training/schemas/aiml_gate_receipts/" + name
        for name in set(central_validator.SCHEMA_FILES.values())
    )
    if list(closure["schema_resources"]) != expected_schemas:
        reasons.append("schema_resources differ from the registered SCHEMA_FILES set")
    if list(closure["compatibility_receipts"]) != sorted({
        _app_identity.COMPATIBILITY_RECEIPT_V1_REL,
        _app_identity.COMPATIBILITY_RECEIPT_V2_REL,
    }):
        reasons.append("compatibility_receipts differ from the pinned S2.2A receipt paths")

    status = "PASS" if not reasons else "APPLICATION_BUNDLE_CLOSURE_INVALID"
    return {
        "schema_version": "application_runtime_closure_verdict_v1",
        "status": status,
        "reasons": sorted(set(reasons)),
        "closure_digest": closure["self_digest"],
        "declared_path_count": len(declared_all),
        "runtime_import_closure_size": len(derived_paths),
        "production_authority_flags": {
            "nine_authorities_false": True,
            "production_apply_performed": False,
            "running_attested": False,
        },
    }


def _git_ls_tree_entries(
    repo_root: Path, source_head: str, paths: list[str]
) -> dict[str, tuple[str, str, str]]:
    """git ls-tree 於 bound head 取 {rel: (git_mode, object_type, blob_sha)}。"""
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "ls-tree", "-z", source_head, "--", *paths],
        capture_output=True,
        text=True,
        check=True,
    )
    entries: dict[str, tuple[str, str, str]] = {}
    for record in completed.stdout.split("\0"):
        if not record:
            continue
        meta, rel = record.split("\t", 1)
        git_mode, object_type, blob_sha = meta.split(" ")
        entries[rel] = (git_mode, object_type, blob_sha)
    return entries


def build_application_bundle_manifest(
    repo_root: Path = REPO_ROOT,
    source_head: str | None = None,
) -> dict[str, Any]:
    """§8.1 #3:從 bound source head 的 committed blobs 產出 application_bundle_manifest_v1。

    typed 拒絕(依序):source head 非當前 checkout HEAD、closure 裁決非 PASS、任一宣告
    路徑 dirty/未提交、head 樹缺檔/symlink/非 blob。成功回
    {status: "BUILT", application_bundle_digest, manifest};中央閘結構驗必過。
    """
    head = source_head if source_head is not None else _git_head(repo_root)
    if not re.fullmatch(r"[0-9a-f]{40}", str(head)):
        return {
            "status": "APPLICATION_BUNDLE_SOURCE_HEAD_MISMATCH",
            "reasons": [f"source_head is not a 40-hex commit: {head!r}"],
        }
    if head != _git_head(repo_root):
        # committed-blob 溯源 + working-tree clean 檢查要求兩者同世代(重放時 checkout 該 head)。
        return {
            "status": "APPLICATION_BUNDLE_SOURCE_HEAD_MISMATCH",
            "reasons": ["source_head is not the current checkout HEAD"],
        }
    closure_verdict = derive_application_runtime_closure_status(repo_root)
    if closure_verdict["status"] != "PASS":
        return {
            "status": "APPLICATION_BUNDLE_CLOSURE_INVALID",
            "reasons": closure_verdict["reasons"],
        }
    closure = _app_identity.load_runtime_closure(repo_root / _APP_CLOSURE_REL)
    declared = _app_identity.closure_declared_paths(closure)

    dirty = subprocess.run(
        [
            "git", "-C", str(repo_root), "status", "--porcelain", "-z", "--", *declared,
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    if dirty.strip("\0"):
        dirty_paths = sorted({
            record[3:] for record in dirty.split("\0") if len(record) > 3
        })
        return {
            "status": "APPLICATION_BUNDLE_SOURCE_DIRTY",
            "reasons": [
                f"declared allowlist path is dirty/uncommitted: {rel}"
                for rel in dirty_paths
            ],
        }

    tree = _git_ls_tree_entries(repo_root, head, declared)
    reasons: list[str] = []
    entries: list[dict[str, str]] = []
    for rel in declared:
        meta = tree.get(rel)
        if meta is None:
            reasons.append(f"declared path is absent from the bound head tree: {rel}")
            continue
        git_mode, object_type, blob_sha = meta
        if object_type != "blob" or git_mode == "120000":
            reasons.append(f"declared path is not a committed regular blob: {rel}")
            continue
        blob = subprocess.run(
            ["git", "-C", str(repo_root), "cat-file", "blob", blob_sha],
            capture_output=True,
            check=True,
        ).stdout
        entries.append({
            "path": rel,
            # §8.1:git 100755 → 0555 可執行;其餘一律 0444 不可變資料。
            "mode": "0555" if git_mode == "100755" else "0444",
            "sha256": "sha256:" + hashlib.sha256(blob).hexdigest(),
        })
    if reasons:
        return {"status": "APPLICATION_BUNDLE_TREE_INVALID", "reasons": reasons}

    # 宣告路徑已證 clean 且等於 head blobs → 以 checkout 重算 v2 身分(零 Git 依賴,
    # 注入 bound head 作 telemetry;其輸入面 ⊆ declared,已由 closure 裁決保證)。
    v2_manifest, v2_errors = _lrm.try_build_learning_runtime_manifest_v2(
        repo_root, repo_source_head=head
    )
    if v2_manifest is None:
        return {
            "status": "APPLICATION_BUNDLE_TREE_INVALID",
            "reasons": [f"learning runtime v2 identity unbuildable: {err}" for err in v2_errors],
        }
    manifest = _app_identity.build_application_bundle_document(
        source_head=head,
        learning_runtime_digest_v2=v2_manifest["self_digest"],
        runtime_closure_digest=central_validator.artifact_self_digest(closure),
        entries=entries,
    )
    central_errors = central_validator.validate_aiml_artifact(manifest)
    if central_errors:
        return {"status": "APPLICATION_BUNDLE_TREE_INVALID", "reasons": central_errors}
    return {
        "status": "BUILT",
        "source_head": head,
        "application_bundle_digest": manifest["self_digest"],
        "entry_count": len(entries),
        "closure_digest": closure["self_digest"],
        "manifest": manifest,
        "production_authority_flags": {
            "nine_authorities_false": True,
            "production_apply_performed": False,
            "running_attested": False,
        },
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    emit = sub.add_parser("w0-emit", help="發射並持久化正式 W0 admission/wave-exit receipts")
    emit.add_argument("--out", required=True, type=Path)
    emit.add_argument("--test-evidence", required=True, type=Path)
    emit.add_argument("--review-provenance", required=True, type=Path)
    w1_emit = sub.add_parser(
        "w1-emit",
        help="發射並持久化正式 W1 wave-exit receipt(記憶體重發當前世代 W0 鏈並綁定)",
    )
    w1_emit.add_argument("--out", required=True, type=Path)
    w1_emit.add_argument("--test-evidence", required=True, type=Path)
    w1_emit.add_argument("--review-provenance", required=True, type=Path)
    sub.add_parser(
        "engine-scanner-split",
        help="再導出 §2.1 engine-scanner privilege-split verdict(typed;不可自證)",
    )
    sub.add_parser(
        "application-closure",
        help="再導出 §8.1 runtime-closure allowlist verdict(typed;不可自證)",
    )
    bundle = sub.add_parser(
        "application-bundle-manifest",
        help="從 bound head 的 committed blobs 產出 application_bundle_manifest_v1",
    )
    bundle.add_argument("--source-head", default=None)
    args = parser.parse_args(argv)
    if args.action == "engine-scanner-split":
        verdict = derive_engine_scanner_privilege_split()
        print(json.dumps(verdict, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if verdict["status"] == "PASS" else 2
    if args.action == "application-closure":
        verdict = derive_application_runtime_closure_status()
        print(json.dumps(verdict, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if verdict["status"] == "PASS" else 2
    if args.action == "application-bundle-manifest":
        result = build_application_bundle_manifest(source_head=args.source_head)
        summary = {key: value for key, value in result.items() if key != "manifest"}
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result["status"] == "BUILT" else 2
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
    if args.action == "w1-emit":
        result = emit_w1_receipts(
            out_dir=args.out,
            test_evidence=json.loads(args.test_evidence.read_text(encoding="utf-8")),
            review_provenance=json.loads(
                args.review_provenance.read_text(encoding="utf-8")
            ),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result["status"] == "W1_RECEIPTS_EMITTED" else 2
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())
