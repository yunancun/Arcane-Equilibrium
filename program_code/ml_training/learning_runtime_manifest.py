"""
MODULE_NOTE
模塊用途：LR1「Scoped Compatibility Identity」的單一事實來源(SSOT)。用學習相關的
  正向 allowlist 計算 learning_runtime_digest,取代整倉 HEAD 的存活判定——docs-only
  提交只移動 repo_source_head(純遙測、永不入任何元件 digest),不再停 Scanner 擷取;
  training 契約漂移只 quarantine fit/promotion,相容的 capture 持續。
主要函數：build_learning_runtime_manifest、evaluate_compatibility、
  build_source_compatibility_receipt、resolve_repo_source_head。
依賴：標準庫 + 既有 canonical_digest/artifact_self_digest(aiml_gate_receipt_validator)
  + parquet_etl 的 feature schema 常量。硬邊界：source-only、NONE-effect;任何建置
  錯誤(缺檔/symlink/非常規檔/不可讀)一律 deny-by-default(fail-closed)。
"""

from __future__ import annotations

import hashlib
import json
import re
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# 重用既有 canonical identity helper——絕不重造 hashing/abstraction(依規範)。
from ml_training.aiml_gate_receipt_validator import (
    artifact_self_digest,
    canonical_digest,
)
from ml_training.parquet_etl import (
    EDGE_P3_FEATURE_NAMES,
    EDGE_P3_FEATURE_SCHEMA_VERSION,
    compute_feature_schema_hash,
)


SCHEMA_VERSION = "learning_runtime_manifest_v1"
RECEIPT_SCHEMA_VERSION = "source_compatibility_receipt_v1"
SESSION_ID = "S2.2A"
BOUNDARY = "source_only_none_effect"

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_HEAD_RE = re.compile(r"^[0-9a-f]{40}$")

# 被擷取快照的特徵 schema 版本;納入 capture 身分,快照特徵表示改版即 capture 漂移。
SNAPSHOT_FEATURE_SCHEMA_VERSION = "alr_scanner_novelty_features_v1"

# ── 凍結的正向輸入 allowlist(reviewed 常量;任何靜默增刪由 source-static 測試攔下) ──

# CAPTURE:最小化,讓 ingest 持續運轉。只含把 Rust scanner 快照落地為 ALR raw 證據的
# 純擷取面(row→cycle adapter、fresh/history drain 車道、raw 落地、consumer session
# 生命週期)。刻意「不」納入 alr_event_consumer.py(多職責 orchestrator,本 Session 正在
# 編輯它,納入會自我失效)與 alr_operational_repository.py(fit 側投影落地,非 raw 擷取)。
CAPTURE_INPUTS: tuple[str, ...] = (
    "program_code/ml_training/alr_consumer_repository.py",
    "program_code/ml_training/alr_freshness_runtime.py",
    "program_code/ml_training/alr_persistence_repository.py",
    "program_code/ml_training/alr_scanner_snapshot_adapter.py",
)

# TRAINING learning-code:漂移即 quarantine fit。含 4 個 _REQUIRED_MODULE_HASHES、
# challenger/candidate 學習模塊,以及 learning_engine 下的 fit/promotion 統計閘。
LEARNING_CODE_INPUTS: tuple[str, ...] = (
    "program_code/ml_training/pit_dataset_manifest.py",
    "program_code/ml_training/quantile_trainer.py",
    "program_code/ml_training/run_training_pipeline.py",
    "program_code/ml_training/model_registry.py",
    "program_code/ml_training/alr_challenger_training_contract.py",
    "program_code/ml_training/alr_challenger_training_result_contract.py",
    "program_code/ml_training/alr_challenger_fit_capture_attestation.py",
    "program_code/ml_training/alr_candidate_policy.py",
    "program_code/ml_training/alr_candidate_learning_arbiter.py",
    "program_code/ml_training/alr_candidate_learning_projection.py",
    "program_code/learning_engine/dsr_gate.py",
    "program_code/learning_engine/pbo_gate.py",
    "program_code/learning_engine/promotion_gate.py",
    "program_code/learning_engine/residual_alpha_gate.py",
)

# 剛好 V151..V160 這 10 支;建置時斷言無缺口。
MIGRATION_INPUTS: tuple[str, ...] = (
    "sql/migrations/V151__alr_persistence_foundation.sql",
    "sql/migrations/V152__alr_operational_artifacts.sql",
    "sql/migrations/V153__alr_outcome_feedback.sql",
    "sql/migrations/V154__alr_retention_guardian.sql",
    "sql/migrations/V155__alr_health_state.sql",
    "sql/migrations/V156__alr_consumer_freshness_state.sql",
    "sql/migrations/V157__model_registry_pit_lineage.sql",
    "sql/migrations/V158__alr_qualified_challenger_training.sql",
    "sql/migrations/V159__alr_durable_fit_attestation.sql",
    "sql/migrations/V160__alr_atomic_fit_consumption.sql",
)
_MIGRATION_SPAN = tuple(f"V{index}" for index in range(151, 161))

# label_contract:pit label-lineage 必填欄位(mirror pit_dataset_manifest.py:316-330)
# + regime OOS label 契約檔的整檔 sha256(取整檔以穩健涵蓋 SCHEMA_VERSION,且避免在
# runtime preflight import/執行研究模塊)。
LABEL_LINEAGE_REQUIRED_FIELDS: tuple[str, ...] = (
    "label_schema_hash",
    "label_config_hash",
    "outcome_cutoff_ts",
)
REGIME_OOS_LABEL_CONTRACT = (
    "helper_scripts/research/cost_gate_learning_lane/regime_oos_label_contract.py"
)

# action_policy / runtime_config:皆源自 in-repo 的 candidate arbiter policy template。
# systemd unit/env 非 in-repo(屬 S2.4 effect),刻意不涵蓋。
POLICY_TEMPLATE = "helper_scripts/deploy/openclaw-alr-candidate-policy.template.json"
# mirror alr_candidate_policy._POLICY_KEYS(policy_config_hash 邏輯的欄位面)。
POLICY_CONFIG_KEYS: tuple[str, ...] = (
    "algorithm_version",
    "byte_budget",
    "collection_window_days",
    "cooldown_seconds",
    "max_new_entries_per_window",
    "policy_config_hash",
    "q18_scale",
    "row_budget",
    "thresholds",
    "tie_break_version",
    "unknown_portfolio_penalty",
)
# runtime_config 只取 template 的 arbiter runtime 常量值。
_RUNTIME_CONFIG_TEMPLATE_KEYS: tuple[str, ...] = (
    "algorithm_version",
    "tie_break_version",
    "q18_scale",
    "thresholds",
    "cooldown_seconds",
    "unknown_portfolio_penalty",
)

# dependency_lock:LR1 身分取 requirements-ml.txt 的 spec 文字 sha256 即可;真正封存
# 的 sealed lock 屬 LR2/S2.3,此處不建。
DEPENDENCY_LOCK_FILE = "requirements-ml.txt"

_COMPATIBLE = "COMPATIBLE"
_INCOMPATIBLE = "INCOMPATIBLE"
_QUARANTINE = "QUARANTINE"
_INDETERMINATE = "INDETERMINATE"


class LearningRuntimeManifestError(ValueError):
    """學習 runtime 清單無法在此 checkout 上被安全建置(fail-closed)。"""


def resolve_repo_source_head(repo_root: str | Path) -> str:
    """讀取 checkout 的 HEAD(唯讀 rev-parse);此值僅供遙測,永不進元件 digest。"""
    root = Path(repo_root)
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise LearningRuntimeManifestError("repo_source_head_unavailable") from exc
    actual = completed.stdout.strip()
    if completed.returncode != 0 or not _GIT_HEAD_RE.fullmatch(actual):
        raise LearningRuntimeManifestError("repo_source_head_unavailable")
    return actual


def _hash_file(repo_root: Path, rel_path: str) -> str:
    """回傳一個 root-relative 常規檔的內容 sha256 hexdigest;任何異常一律 fail-closed。"""
    path = repo_root / rel_path
    if path.is_symlink():
        raise LearningRuntimeManifestError(f"symlink_input:{rel_path}")
    try:
        st = path.stat()
    except OSError as exc:
        raise LearningRuntimeManifestError(f"missing_input:{rel_path}") from exc
    if not stat.S_ISREG(st.st_mode):
        raise LearningRuntimeManifestError(f"non_regular_input:{rel_path}")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise LearningRuntimeManifestError(f"unreadable_input:{rel_path}") from exc
    return hashlib.sha256(data).hexdigest()


def _hash_inputs(repo_root: Path, rel_paths: tuple[str, ...]) -> dict[str, str]:
    return {rel: _hash_file(repo_root, rel) for rel in sorted(rel_paths)}


def _assert_migration_span(fingerprints: dict[str, str]) -> None:
    versions = sorted(name.split("__", 1)[0] for name in fingerprints)
    if versions != sorted(_MIGRATION_SPAN):
        raise LearningRuntimeManifestError("migration_span_incomplete")


def _capture_contract(repo_root: Path) -> dict[str, Any]:
    inputs = _hash_inputs(repo_root, CAPTURE_INPUTS)
    projection = {
        "inputs": inputs,
        "snapshot_feature_schema_version": SNAPSHOT_FEATURE_SCHEMA_VERSION,
    }
    return {
        "digest": canonical_digest(projection),
        "inputs": inputs,
        "snapshot_feature_schema_version": SNAPSHOT_FEATURE_SCHEMA_VERSION,
    }


def _feature_contract_digest() -> str:
    return canonical_digest(
        {
            "feature_schema_hash": compute_feature_schema_hash(EDGE_P3_FEATURE_NAMES),
            "feature_schema_version": EDGE_P3_FEATURE_SCHEMA_VERSION,
        }
    )


def _label_contract_digest(repo_root: Path) -> str:
    return canonical_digest(
        {
            "pit_label_lineage_required_fields": list(LABEL_LINEAGE_REQUIRED_FIELDS),
            "regime_oos_label_contract_sha256": _hash_file(
                repo_root, REGIME_OOS_LABEL_CONTRACT
            ),
        }
    )


def _load_policy_template(repo_root: Path) -> dict[str, Any]:
    path = repo_root / POLICY_TEMPLATE
    if path.is_symlink():
        raise LearningRuntimeManifestError(f"symlink_input:{POLICY_TEMPLATE}")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise LearningRuntimeManifestError(f"missing_input:{POLICY_TEMPLATE}") from exc
    try:
        template = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise LearningRuntimeManifestError("policy_template_undecodable") from exc
    if not isinstance(template, dict):
        raise LearningRuntimeManifestError("policy_template_not_object")
    return template


def _action_policy_digest(repo_root: Path) -> str:
    return canonical_digest(
        {
            "policy_template_sha256": _hash_file(repo_root, POLICY_TEMPLATE),
            "policy_config_keys": list(POLICY_CONFIG_KEYS),
        }
    )


def _runtime_config_digest(repo_root: Path, template: dict[str, Any]) -> str:
    return canonical_digest(
        {
            "policy_template_sha256": _hash_file(repo_root, POLICY_TEMPLATE),
            "arbiter_constants": {
                key: template.get(key) for key in _RUNTIME_CONFIG_TEMPLATE_KEYS
            },
        }
    )


def _training_contract(repo_root: Path) -> dict[str, Any]:
    learning_code_inputs = _hash_inputs(repo_root, LEARNING_CODE_INPUTS)
    fingerprints = {
        rel.split("/")[-1]: _hash_file(repo_root, rel) for rel in MIGRATION_INPUTS
    }
    _assert_migration_span(fingerprints)
    template = _load_policy_template(repo_root)
    components = {
        "learning_code_digest": canonical_digest(learning_code_inputs),
        "migration_fingerprints": dict(sorted(fingerprints.items())),
        "feature_contract_digest": _feature_contract_digest(),
        "label_contract_digest": _label_contract_digest(repo_root),
        "action_policy_digest": _action_policy_digest(repo_root),
        "dependency_lock_digest": "sha256:" + _hash_file(repo_root, DEPENDENCY_LOCK_FILE),
        "runtime_config_digest": _runtime_config_digest(repo_root, template),
    }
    return {
        "digest": canonical_digest(components),
        "components": components,
    }


def _self_digest(capture_digest: str, training_digest: str) -> str:
    # 身分只綁 schema + 兩個元件 digest + boundary;刻意排除 generated_at_utc 與
    # repo_source_head,才能在 docs-only 提交與重生成之間保持同一個 self_digest。
    return canonical_digest(
        {
            "schema_version": SCHEMA_VERSION,
            "boundary": BOUNDARY,
            "capture_contract_digest": capture_digest,
            "training_contract_digest": training_digest,
        }
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_learning_runtime_manifest(
    repo_root: str | Path,
    *,
    repo_source_head: str | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """在 repo_root checkout 上建置 learning_runtime_manifest_v1;任何輸入異常 fail-closed。"""
    root = Path(repo_root)
    head = repo_source_head if repo_source_head is not None else resolve_repo_source_head(root)
    if not _GIT_HEAD_RE.fullmatch(str(head)):
        raise LearningRuntimeManifestError("repo_source_head_invalid")

    capture_contract = _capture_contract(root)
    training_contract = _training_contract(root)
    self_digest = _self_digest(capture_contract["digest"], training_contract["digest"])
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated_at_utc or _utc_now(),
        "repo_source_head": str(head),
        "capture_contract": capture_contract,
        "training_contract": training_contract,
        "boundary": BOUNDARY,
        "self_digest": self_digest,
    }


def try_build_learning_runtime_manifest(
    repo_root: str | Path,
    *,
    repo_source_head: str | None = None,
    generated_at_utc: str | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """fail-closed 包裝:成功回 (manifest, []);任何建置錯誤回 (None, [reason])。"""
    try:
        manifest = build_learning_runtime_manifest(
            repo_root,
            repo_source_head=repo_source_head,
            generated_at_utc=generated_at_utc,
        )
    except LearningRuntimeManifestError as exc:
        return None, [str(exc)]
    return manifest, []


def _valid_manifest_or_none(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        return None
    capture = value.get("capture_contract")
    training = value.get("training_contract")
    if not isinstance(capture, dict) or not isinstance(training, dict):
        return None
    if not _DIGEST_RE.fullmatch(str(capture.get("digest"))):
        return None
    if not _DIGEST_RE.fullmatch(str(training.get("digest"))):
        return None
    if not _DIGEST_RE.fullmatch(str(value.get("self_digest"))):
        return None
    return value


def evaluate_compatibility(
    expected_manifest: Any,
    actual_manifest: Any,
) -> dict[str, Any]:
    """比較兩份清單:capture digest 相等→capture 相容;training digest 相等→fit 相容。

    Deny-by-default:任一份清單缺失/畸形(建置錯誤的哨兵 None 或非法結構)→兩者皆
    INDETERMINATE(fail-closed)。
    """
    expected = _valid_manifest_or_none(expected_manifest)
    actual = _valid_manifest_or_none(actual_manifest)
    if expected is None or actual is None:
        return {
            "capture_status": _INDETERMINATE,
            "fit_status": _INDETERMINATE,
            "manifest_identical": False,
            "quarantine_reasons": ["manifest_unavailable"],
            "capture_stop_reasons": ["manifest_unavailable"],
        }
    capture_equal = (
        expected["capture_contract"]["digest"] == actual["capture_contract"]["digest"]
    )
    training_equal = (
        expected["training_contract"]["digest"] == actual["training_contract"]["digest"]
    )
    identical = expected["self_digest"] == actual["self_digest"]
    return {
        "capture_status": _COMPATIBLE if capture_equal else _INCOMPATIBLE,
        "fit_status": _COMPATIBLE if training_equal else _QUARANTINE,
        "manifest_identical": identical,
        "quarantine_reasons": [] if training_equal else ["training_contract_digest_changed"],
        "capture_stop_reasons": [] if capture_equal else ["capture_contract_digest_changed"],
    }


def evaluate_runtime_digest_pin(
    expected_learning_runtime_digest: str | None,
    actual_manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    """以純量 pin(reviewed 的 learning_runtime_digest)判定 capture/fit。

    這是給 event-consumer preflight 的縮減版:operator 只持有 self_digest 純量 pin。
    - actual 建置失敗(None)→兩者 INDETERMINATE(fail-closed 停 capture)。
    - actual 建置成功 → capture 相容(擷取面本身健全);self_digest == pin 才 fit 相容,
      否則 quarantine fit。docs-only 提交不動 self_digest,故 fit 保持相容、capture 不停。
    - 未提供 pin → capture 續跑但 fit quarantine(無法確認 training 相容,fail-closed)。
    """
    actual = _valid_manifest_or_none(actual_manifest)
    if actual is None:
        return {
            "capture_status": _INDETERMINATE,
            "fit_status": _INDETERMINATE,
            "manifest_identical": False,
            "quarantine_reasons": ["manifest_unavailable"],
            "capture_stop_reasons": ["manifest_unavailable"],
        }
    if expected_learning_runtime_digest is None:
        return {
            "capture_status": _COMPATIBLE,
            "fit_status": _QUARANTINE,
            "manifest_identical": False,
            "quarantine_reasons": ["expected_learning_runtime_digest_absent"],
            "capture_stop_reasons": [],
        }
    identical = actual["self_digest"] == expected_learning_runtime_digest
    return {
        "capture_status": _COMPATIBLE,
        "fit_status": _COMPATIBLE if identical else _QUARANTINE,
        "manifest_identical": identical,
        "quarantine_reasons": [] if identical else ["learning_runtime_digest_pin_drift"],
        "capture_stop_reasons": [],
    }


BIND_POINTS: tuple[dict[str, str], ...] = (
    {
        "file": "program_code/ml_training/alr_event_consumer.py",
        "function": "run_event_consumer",
        "binds": "learning_runtime_digest",
    },
    {
        "file": "program_code/ml_training/alr_challenger_training_contract.py",
        "function": "build_alr_challenger_training_contract",
        "binds": "learning_runtime_digest",
    },
    {
        "file": "program_code/ml_training/alr_challenger_fit_capture_attestation.py",
        "function": "build_alr_challenger_fit_capture_attestation_contract",
        "binds": "learning_runtime_digest",
    },
)


def build_source_compatibility_receipt(
    repo_root: str | Path,
    *,
    repo_source_head: str | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """建置 SOURCE_READY 的 source_compatibility_receipt_v1(所有 digest 皆為真值)。"""
    manifest = build_learning_runtime_manifest(
        repo_root,
        repo_source_head=repo_source_head,
        generated_at_utc=generated_at_utc,
    )
    components = manifest["training_contract"]["components"]
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "session_id": SESSION_ID,
        "generated_at_utc": manifest["generated_at_utc"],
        "repo_source_head": manifest["repo_source_head"],
        "learning_runtime_manifest": manifest,
        "learning_runtime_digest": manifest["self_digest"],
        "capture_contract_digest": manifest["capture_contract"]["digest"],
        "training_contract_digest": manifest["training_contract"]["digest"],
        "migration_fingerprints": dict(components["migration_fingerprints"]),
        "bind_points": [dict(point) for point in BIND_POINTS],
        "status": "SOURCE_READY",
        "boundary": BOUNDARY,
    }
    receipt["self_digest"] = artifact_self_digest(receipt)
    return receipt
