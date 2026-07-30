#!/usr/bin/env python3
"""Fail-closed stdlib validation for AI/ML landing governance artifacts."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
if str(HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(HELPER_DIR))
# 2000 行治理拆分:facade 匯入 sibling 葉模組(aiml_gate_receipt_*),故把本模組目錄一併入
# path——無論本檔以 top-level 或 ml_training.* 套件形被匯入,葉模組都以 top-level 名解析為
# 同一單例(鏡射上方 HELPER_DIR 姿態)。
_ML_TRAINING_DIR = Path(__file__).resolve().parent
if str(_ML_TRAINING_DIR) not in sys.path:
    sys.path.insert(0, str(_ML_TRAINING_DIR))

from agent_governance_schema import schema_subset_errors  # noqa: E402
# 唯讀消費 S2.4 §9.1 SSHSIG 信任根與離線公鑰驗簽基元(_verify_ssh_signature /
# ssh_public_key_fingerprint)。此為葉層信任根 facade,不反向匯入本 validator(無循環);
# CP4 僅呼叫其驗證基元,「絕不」修改該模組或其測試(§9.1:trust-root 輪替屬獨立授權 session)。
import agent_governance_aiml_trusted_host as _trusted_host  # noqa: E402

# --------------------------------------------------------------------------- #
# 2000 行治理拆分(WP4 S2.4·操作者 P0):本 facade 是唯一公開匯入面;實作逐位元組下沉至
# 四個 sibling 葉模組並在此逐名 re-export,ABI 與行為不變(S0.3/v1/v2/§9.1/W0 五個身分
# digest 拆分前後重算相等)。
#   aiml_gate_receipt_schema_core    —— canonical digest 基元 / SCHEMA_FILES / S0 常量
#   aiml_gate_receipt_classifiers    —— S0.3 classifier + v1/v2 component-effect 矩陣
#   aiml_gate_receipt_s2_4_contracts —— S2.4 per-row ABI / install lineage / §9.1 授權 profile
#   aiml_gate_receipt_adoption       —— terminal sink 契約 / GitHub attestation / program adoption
# 葉模組 top-level 絕不反向匯入本 facade(僅函式內延遲匯入以保 monkeypatch 縫);W0
# admission/wave-exit 再導出與中央 dispatcher 留在本檔(測試 monkeypatch 的 facade 縫:
# derive_source_admission_status / derive_wave_exit_status / _consumer_authoritative_database /
# S2_4_OPERATOR_TRUST_ROOT_*)。
# --------------------------------------------------------------------------- #
from aiml_gate_receipt_schema_core import (  # noqa: E402,F401
    ExternalAttestationVerifier,
    GITHUB_SECRET_LIKE_RE,
    PROGRAM_DOCUMENT_PATHS,
    PROGRAM_GOVERNANCE_PATHS,
    PROGRAM_REVIEW_NODES,
    PROGRAM_SCHEMA_PATHS,
    S0_DEPENDENCY_DIGESTS, S0_PREDECESSOR_CONTRACTS, S2_3_SEALED_BUILD_RECEIPT_REL,
    S2_4_COMMITTED_SOURCE_IDENTITY_PATHS,
    S2_4_W5_REMAINING_OWNED_OBLIGATIONS,
    SCHEMA_DIR,
    SCHEMA_FILES,
    SourceManifestVerifier,
    _canonical_bytes,
    _canonical_list_is_sorted_unique,
    _contains_github_secret_like_content,
    _dependency_graph_errors,
    _directed_graph_has_cycle,
    _load_schema,
    _now_text,
    _parse_timestamp,
    artifact_self_digest,
    _git_head,
    _git_is_ancestor,
    canonical_digest, committed_source_identity_digests,
    dependency_semantic_subject_values,
    evidence_environment_identity_digest,
    git_blob_sha1,
    git_failure_detail,
    git_is_shallow_repository,
    landing_scope_identity_digest,
    owned_path_blob_projection,
    owned_path_blob_projection_digest,
    owned_scope_delta_reasons,
    owned_scope_reason_prefix,
    owned_scope_worktree_delta,
    resolve_commit_head, s1_3_identity_projection,
    session_attempt_identity_digest,
)
from aiml_gate_receipt_classifiers import (  # noqa: E402,F401
    AIML_COMPONENT_EFFECT_CLASS_INVARIANTS,
    AIML_COMPONENT_EFFECT_CLASS_MATRIX,
    AIML_COMPONENT_EFFECT_CLASS_MATRIX_V2,
    AIML_COMPONENT_EFFECT_CLASS_V2_INVARIANTS,
    AIML_EFFECT_CLASSIFIER_RULES,
    AIML_LANDING_SIDE_EFFECT_CLASSES,
    S0_3_DIRECT_INTERFACES_BY_PHASE,
    S0_3_EXACT_OWNED_PATHS,
    S0_3_FORBIDDEN_FACT_RE,
    S0_3_OWNED_PATH_PREFIXES,
    S0_3_SIDE_EFFECT_BY_PHASE,
    S0_3_WORK_PACKAGE_ID,
    _aiml_landing_owned_path,
    _aiml_landing_work_package_errors,
    _component_effect_class_identity_digest,
    _component_effect_surface_tokens,
    _component_effect_surface_tokens_v2,
    _component_surfaces_touched,
    _component_surfaces_touched_v2,
    _effect_classification_identity_digest,
    _s0_3_owned_path,
    _s0_3_work_package_errors,
    aiml_component_effect_class_matrix_digest,
    aiml_component_effect_class_matrix_v2_digest,
    aiml_effect_classifier_digest,
    classify_component_required_effects,
    classify_component_required_effects_v2,
    classify_required_effects,
)
from aiml_gate_receipt_s2_4_contracts import (  # noqa: E402,F401
    DEPENDENCY_EVIDENCE_REOBSERVATION_REQUIRED,
    DEPENDENCY_REFRESH_BY_REFERENCE_FORBIDDEN,
    DEPENDENCY_REFRESH_STATUS_ADMITTED,
    DEPENDENCY_REFRESH_STATUS_REJECTED,
    MAX_DEPENDENCY_REFRESH_TTL_SECONDS,
    PERMIT_PLAN_BINDING_STATUS_REJECTED,
    PERMIT_PLAN_BINDING_STATUS_VERIFIED,
    S2_2A_OBSERVATION_TTL_SECONDS,
    S2_4_APPLY_ROW_CLASS_ORDER,
    S2_4_AUTHORIZATION_ID_DOMAIN,
    S2_4_AUTHORIZATION_ID_SELF_FIELD,
    S2_4_AUTHORIZATION_PROFILES,
    S2_4_DEPENDENCY_REFRESH_CLASSES,
    S2_4_DEPENDENCY_REFRESH_METHOD,
    S2_4_DEPENDENCY_REFRESH_SCHEMA_VERSION,
    S2_4_NEVER_REFRESHABLE_EVIDENCE,
    S2_4_OPERATOR_AUTHORIZATION_SCHEMA_VERSION,
    S2_4_OPERATOR_TRUST_ROOT_FINGERPRINT,
    S2_4_OPERATOR_TRUST_ROOT_PUBLIC_KEY,
    S2_4_W1_SCHEMA_FILENAMES as _W1_SCHEMA_FILENAMES,
    SOURCE_DEPENDENCY_STATUS_ADMITTED_BY_REFRESH,
    SOURCE_DEPENDENCY_STATUS_EXPIRED_NO_REFRESH,
    SOURCE_DEPENDENCY_STATUS_FRESH,
    SOURCE_DEPENDENCY_STATUS_REJECTED,
    _S2_4_APPLY_INTENT_CLASS_TOKEN_FIELDS,
    _S2_4_APPLY_INTENT_COMMON_TOKEN_FIELDS,
    _S2_4_PROFILE_BY_IDENTITY,
    _SSH_SIGNATURE_ARMOR_MARKERS,
    _dependency_refresh_structural_errors,
    _install_lineage_plan_binding_errors,
    _s2_4_authorization_payload_binding_errors,
    _s2_4_install_plan_apply_rows_errors,
    _s2_4_operator_authorization_errors,
    _s2_4_operator_authorization_signed_bytes,
    _s2_4_replay_ledger_errors,
    _s2_4_route_core_rederivation_errors,
    _sshsig_armor_body_is_strict_base64,
    authorization_payload_binding_fields,
    build_s2_4_dependency_refresh_attestation,
    build_s2_4_operator_authorization,
    dependency_class_for_schema_version,
    dependency_evidence_schema_versions,
    dependency_producer_input_paths,
    dependency_original_observation_window,
    dependency_producer_identity,
    derive_authorization_id,
    derive_authorization_replay_binding,
    derive_component_intent_binding,
    derive_dependency_refresh_status,
    derive_install_lineage_status,
    derive_permit_plan_binding_status,
    derive_source_dependency_admission_status,
    reproduce_dependency_semantic_digests,
    s2_4_authorization_identity_digest,
    s2_4_authorization_profiles_digest, s2_4_replay_ledger_errors,
)
from aiml_gate_receipt_adoption import (  # noqa: E402,F401
    _github_policy_attestation_errors,
    _program_adoption_receipt_errors,
    _s0_predecessor_receipt_errors,
    _terminal_receipt_sink_body,
    github_policy_attestation_identity_digest,
    program_adoption_identity_digest,
    terminal_receipt_sink_contract,
    validate_program_adoption_receipt,
)
from aiml_gate_receipt_s2e_launch import (  # noqa: E402,F401
    canonical_launch_payload_bytes,
    issue_s2e_launch_receipt,
    launch_payload_digest,
    load_s2e_receipt_signer_trust_root,
    s2e_acceptance_review_bundle_digest,
    s2e_acceptance_review_signed_bytes,
    s2e_acceptance_review_worm_payload,
    s2e_carrier_attestation_digest,
    s2e_carrier_attested_core_digest,
    s2e_carrier_signed_bytes,
    s2e_carrier_worm_payload,
    s2e_review_predicate_results,
    validate_receipt_carrier_attestation,
    validate_s2e_launch_acceptance_review_bundle,
    verify_receipt_carrier_attestation,
    validate_s2e_launch_genesis_receipt,
    validate_s2e_launch_transition,
    validate_s2e_launch_wave_receipt,
)
from aiml_gate_receipt_source_compatibility import (  # noqa: E402,F401
    source_compatibility_receipt_errors as _source_compatibility_receipt_errors,
    source_compatibility_receipt_v2_dependency_lock_errors as
    _source_compatibility_receipt_v2_dependency_lock_errors,
)
# S2.4(WP4·W2/W3/W4/W5)四片 wave 投影葉(2000 行治理拆分):owned-path / exported-ABI /
# manifest 補充驗下沉至各葉,facade 逐名 re-export,對應 wave 的 derive 分支委派該葉。
# W2=runnable application,W3=typed host driver,W4=aggregate transaction,W5=source closure
# (W5 綁「§10.5 每一條驗收項到底被什麼證明」的六組活裁決)。
# 版式註記(W5):四塊 import 由逐行改為逐段,純格式、無語意變動——facade 於 W4 收口時恰為
# 2000 行(治理門檻上限),W5 的新增名若逐行排列即越線,§10.1.1 要求先擠出空間再擴充。
from aiml_gate_receipt_wave_w2 import (  # noqa: E402,F401
    _W2_ABI_PROBE_FIELDS, _W2_EXPORTED_ABI, _W2_OWNED_PATHS, w2_chain_binding_errors,
    w2_exported_abi_projection, w2_manifest_artifact_errors, w2_owned_path_diff_digest,
    w2_structural_errors,
)
from aiml_gate_receipt_wave_w3 import (  # noqa: E402,F401
    _W3_EXPORTED_ABI, _W3_OWNED_PATHS, w3_chain_binding_errors,
    w3_exported_abi_projection, w3_owned_path_diff_digest, w3_structural_errors,
)
from aiml_gate_receipt_wave_w4 import (  # noqa: E402,F401
    _W4_EXPORTED_ABI, _W4_OWNED_PATHS, w4_chain_binding_errors,
    w4_exported_abi_projection, w4_owned_path_diff_digest, w4_structural_errors,
)
from aiml_gate_receipt_wave_w5 import (  # noqa: E402,F401
    _W5_EXPORTED_ABI, _W5_OWNED_PATHS, _W5_OWNED_SCOPE_REASON,
    build_w5_wave_exit_receipt,
    w5_chain_binding_errors, w5_exported_abi_projection, w5_owned_path_diff_digest,
    w5_structural_errors,
)


# --------------------------------------------------------------------------- #
# S2.4 · WP4 · W0(W0b)source-admission / wave-exit 中央「再導出」機制。
#
# 契約鐵則:receipt 只帶 evidence,status「絕不」由 caller 宣告。derive_* 以 repo 內獨立重算
# 每一欄位——§1.2 effect-DAG 三投影、§9.1 四 trust pin、S2.0 driver-reachability seam、WP3
# system-level property(property 非 exact unit-name,PM §7#4)、frozen S0.3 classifier + v1
# component matrix——ADMITTED/PASS 由重算相符「導出」;caller 帶 status/admitted/pass/done 於
# derivation 前即拒(§10.5 #27)。此機制與 aiml_effect_classifier_digest() 的六個 S0.3 常量、
# PROGRAM_SCHEMA_PATHS、AIML_COMPONENT_EFFECT_CLASS_MATRIX 完全「只讀不改」,故分類身分保持
# byte-frozen(§0 凍結約束)。它證的是 source-seam 完整性,「不」認證任何 runtime——九 authority /
# production_apply_performed / running_attested 恆 false。
# --------------------------------------------------------------------------- #
_PROGRAM_EFFECT_DAG = "S2.0→S2.4→S2.5A→S2.1→S2.5B→S2.2B"
_THREE_HEAD_PROJECTION_PATHS = (
    "TODO.md",
    "docs/execution_plan/ai_ml_landing/PROGRESS.md",
    "docs/agents/ai-ml-landing-delivery-protocol.md",
)
# §1.2 的兩個 W0 predecessor merge(admission 的固定祖先);兩者皆須為 receipt.source_head 的
# 祖先(local-checkout 拓撲證,非 runtime)。PR#132 = effect-DAG 投影;PR#134 = WP3 system-unit 對齊。
_PREDECESSOR_HEADS = {
    "program_dag_projection_merge": "4915be30c4214f8a3d591b7f9259169cdb65c75b",
    "wp3_system_unit_merge": "e514f1e761ab9c1965a133f1f113e2e7ccd854df",
}
# §9.1 operator 信任根指紋(out-of-scope pin;W0 只再驗、絕不改 trusted-host 模組/測試/指紋)。
_OPERATOR_FINGERPRINT = "SHA256:uGJ9veN7PoE6BBgfsSP2aiMndrwgbt7o/7/YfdzNzCQ"
_TRUSTED_HOST_MODULE_PATH = (
    "helper_scripts/maintenance_scripts/agent_governance_aiml_trusted_host.py"
)
_TRUSTED_HOST_TEST_PATH = "tests/structure/test_agent_governance_aiml_trusted_host.py"
_S2_0_ADAPTER_ID = "pg_observer_bootstrap_adapter_v1"
_S2_0_EXPECTED_REGISTRY_STATUS = "AUTHORITY_LOCKED_PRODUCTION_CAPABLE"
# WP3 system-level PROPERTY:role / systemctl --user 缺席由 WP3 executable 常量 + allowlist 動態
# 再導出;database 則「不」硬編鏡像常量,改由消費端權威 DSN(alr_event_consumer._LOCAL_DSN_REQUIRED
# 的 dbname,§10.4 runtime-DB 不可變 + _validate_local_dsn 強制)於導出期再讀取——若消費端 DSN 漂移,
# admission 隨之失敗(T7)。見 _consumer_authoritative_database()。
_ALR_CONSUMER_MODULE_PATH = "program_code/ml_training/alr_event_consumer.py"
_ALL_FALSE_PRODUCTION_FLAGS = {
    "nine_authorities_false": True,
    "production_apply_performed": False,
    "running_attested": False,
}
# §4.1 W0 exported-ABI delta(wave-exit exported_abi_digest 綁定的固定投影)。
_W0_EXPORTED_ABI = {
    "s2_0_adapter_binding": "AUTHORITY_LOCKED_PRODUCTION_CAPABLE",
    "s2_0_production_success_status": "APPLIED",
    "s2_0_production_driver_protocol": "ObserverBootstrapProductionDriver",
    "source_admission": "s2_4_source_admission_receipt_v1(status=ADMITTED)",
    "wave_exit": "s2_4_wave_exit_receipt_v1(status=PASS)",
}
# §5 W0 owned-path allowlist(wave-exit owned_path_manifest_digest 綁定的固定投影)。
# 2026-07-25 2000 行治理拆分後擴列(E2 P1-2):validator 邏輯與主測試分居多檔,
# owned-path diff 綁定必須覆蓋拆分後全家族,否則對 leaf/測試 sibling 的削弱性
# 修改不會改變 wave-exit 的 owned_path_diff_digest(治理不變量覆蓋面靜默收窄)。
_W0_OWNED_PATHS = (
    ".codex/agent_registry_v1.json",
    "helper_scripts/maintenance_scripts/agent_governance_pg_observer_bootstrap.py",
    "program_code/ml_training/aiml_gate_receipt_adoption.py",
    "program_code/ml_training/aiml_gate_receipt_classifiers.py",
    "program_code/ml_training/aiml_gate_receipt_s2_4_contracts.py",
    "program_code/ml_training/aiml_gate_receipt_schema_core.py",
    "program_code/ml_training/aiml_gate_receipt_validator.py",
    "program_code/ml_training/schemas/aiml_gate_receipts/pg_observer_bootstrap_result_v1.schema.json",
    "program_code/ml_training/schemas/aiml_gate_receipts/s2_4_source_admission_receipt_v1.schema.json",
    "program_code/ml_training/schemas/aiml_gate_receipts/s2_4_wave_exit_receipt_v1.schema.json",
    "program_code/ml_training/tests/aiml_gate_receipt_validator_testkit.py",
    "program_code/ml_training/tests/test_aiml_gate_receipt_validator.py",
    "program_code/ml_training/tests/test_aiml_gate_receipt_validator_adoption.py",
    "program_code/ml_training/tests/test_aiml_gate_receipt_validator_s2_4.py",
    "tests/structure/test_agent_governance_pg_observer_bootstrap.py",
    "tests/structure/test_s2_4_w0_admission.py",
)
# §3.1 W0 負向測試清單:admission 的 negative_tests_pass 必須「重導出」等於本清單的正規
# digest,而非只通過形狀檢查(否則偽造 receipt 可帶任意 digest 仍導出 ADMITTED,verdict 便
# 暗示 W0 負向測試已驗,實則從未綁定)。此為 code-owned 常量——恰好列出
# tests/structure/test_s2_4_w0_admission.py 內每一支負向(reject_/tamper_)測試的確切函式名
# (舊 effect-chain / systemctl --user / 自證 status / 逐欄竄改拒絕),已排序去重。
_W0_NEGATIVE_TEST_MANIFEST = (
    "test_reject_old_effect_chain_if_reintroduced_into_a_projection",
    "test_reject_self_declared_admission_status",
    "test_reject_self_declared_wave_exit_status",
    "test_reject_wp3_systemctl_user_production_path_from_executable_constants",
    "test_tamper_component_classifier_v1_digest_breaks_admission",
    "test_tamper_driver_reachability_flag_breaks_admission",
    "test_tamper_frozen_classifier_digest_breaks_admission",
    "test_tamper_negative_tests_pass_breaks_admission",
    "test_tamper_non_ancestor_source_head_breaks_admission",
    "test_tamper_operator_fingerprint_breaks_admission",
    "test_tamper_predecessor_head_breaks_admission",
    "test_tamper_production_flag_true_breaks_admission",
    "test_tamper_projection_digest_breaks_admission",
    "test_tamper_trust_pin_breaks_admission",
)
_CALLER_STATUS_KEYS = ("admitted", "done", "pass", "status")


def w0_negative_test_manifest_digest() -> str:
    """W0 負向測試清單的正規 digest(admission negative_tests_pass 綁定的固定投影)。"""

    return canonical_digest(list(_W0_NEGATIVE_TEST_MANIFEST))


def _consumer_authoritative_database(repo_root: Path = REPO_ROOT) -> str | None:
    """由消費端權威 DSN 常量(alr_event_consumer._LOCAL_DSN_REQUIRED['dbname'])再導出期望 database(T7)。

    以 AST 解析 module 源碼取常量(而非硬編鏡像字面量,亦不重匯入其龐大依賴鏈/循環 import),故若消費端
    的 authoritative DSN 漂移(dbname 改動或 _validate_local_dsn 契約變更),admission 的 database 再導出
    隨之改變、令帶舊 database 的 receipt 失敗。fail-closed:讀不到常量回 None。
    """

    import ast

    try:
        source = (repo_root / _ALR_CONSUMER_MODULE_PATH).read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError, ValueError):
        return None
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "_LOCAL_DSN_REQUIRED"
            for target in node.targets
        ):
            continue
        for key, value in zip(node.value.keys, node.value.values):
            if (
                isinstance(key, ast.Constant)
                and key.value == "dbname"
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)
            ):
                return value.value
    return None


def _read_three_head_texts(repo_root: Path) -> dict[str, str]:
    return {
        rel: (repo_root / rel).read_text(encoding="utf-8")
        for rel in _THREE_HEAD_PROJECTION_PATHS
    }


def _projection_effect_dag_errors(texts: dict[str, str]) -> list[str]:
    """Require the canonical NEW apply-order in every projection text(§10.5 #20)。

    一份把 canonical apply-order 換回舊鏈(``S2.1@EFFECT_DONE``-before-``S2.4``)的 projection
    會因 NEW 鏈缺席而被拒。刻意「不」以「舊鏈子串出現」判拒——真 PROGRESS.md changelog 會同時
    載明舊→新兩鏈作歷史,單以子串判會誤傷。
    """

    return [
        f"three_head_projection missing the canonical §1.2 effect DAG in {path}"
        for path, text in sorted(texts.items())
        if _PROGRAM_EFFECT_DAG not in text
    ]


def three_head_projection_digest(repo_root: Path = REPO_ROOT) -> str:
    """Canonical digest of the §1.2 effect-DAG over the projections that carry it.

    數值依「再讀」而變:缺任一投影 → present set 縮小 → digest 改變(且 derivation 另以
    :func:`_projection_effect_dag_errors` 明確報缺)。
    """

    texts = _read_three_head_texts(repo_root)
    present = sorted(rel for rel, text in texts.items() if _PROGRAM_EFFECT_DAG in text)
    return canonical_digest({
        "effect_dag": _PROGRAM_EFFECT_DAG,
        "present_projections": present,
    })


def w0_owned_path_diff_digest(
    repo_root: Path = REPO_ROOT, *, source_head: str | None = None
) -> str:
    """W0 owned-path 內容投影 digest(wave-exit owned_path_diff_digest 綁定的再導出;T1)。

    P1-5(W2 review):每個 owned path 讀的是**被綁定 commit 的 blob**(預設 HEAD),
    不是工作樹當下的位元組。舊機制 hash 髒 checkout:receipt 記未變的 HEAD、投影卻綁
    髒位元組,驗證端 hash 同一棵髒樹照樣 PASS,而該 commit 的乾淨 checkout 重現不出
    這份 receipt。改綁 commit blob 後,投影是該 commit 的函數(缺檔/非 blob 記 None),
    任何世代 checkout 它都重算得出同值。此為 SOURCE-seam 內容綁定,非 runtime 認證。
    """

    return owned_path_blob_projection_digest(
        repo_root, _W0_OWNED_PATHS, source_head=source_head
    )


# --------------------------------------------------------------------------- #
# S2.4 · WP4 · W1(contracts/routing)wave-exit 綁定的 code-owned 投影(§10.3 W1 row)。
#
# 與 W0 同一機制:owned-path「路徑集合」digest + 「內容」投影 digest + exported-ABI digest,
# 全由 repo 當前 checkout 再導出;receipt 只帶 evidence,PASS 恆由 derive_wave_exit_status 導出。
# W1 的 PASS 另需前導 W0 wave-exit receipt 物件(predecessor_wave_receipt)連同其綁定 admission
# 「一起」再導出 PASS/ADMITTED——admission 鏈不因跨波而鬆脫(§10.5 #27)。
# --------------------------------------------------------------------------- #
_W1_SCHEMA_DIR_REL = "program_code/ml_training/schemas/aiml_gate_receipts"
# §10.1 W1 owned-path 投影:registry + routing/closure/component-effects 模組 + contracts 葉
# (與其 facade/classifiers sibling)+ schemas dir additions + install 模組與其測試。
_W1_OWNED_PATHS = tuple(sorted(
    (
        ".codex/agent_registry_v1.json",
        "helper_scripts/maintenance_scripts/agent_governance_closure.py",
        "helper_scripts/maintenance_scripts/agent_governance_component_effects.py",
        "helper_scripts/maintenance_scripts/agent_governance_routing.py",
        "helper_scripts/maintenance_scripts/agent_governance_s2_4_install.py",
        "program_code/ml_training/aiml_gate_receipt_classifiers.py",
        "program_code/ml_training/aiml_gate_receipt_s2_4_contracts.py",
        "program_code/ml_training/aiml_gate_receipt_validator.py",
        "program_code/ml_training/tests/test_aiml_gate_receipt_validator_s2_4.py",
        "tests/structure/test_agent_governance_s2_4_install.py",
        "tests/structure/test_agent_governance_s2_4_install_integration.py",
    )
    + tuple(f"{_W1_SCHEMA_DIR_REL}/{name}" for name in _W1_SCHEMA_FILENAMES)
))
# §10.2 凍結 ABI 的 W1 delta(exported_abi_digest 綁定的 code-owned 投影骨架;live 部分見
# w1_exported_abi_projection)。
_W1_EXPORTED_ABI = {
    "route_classes": [
        "s2_4_capability_probe_intent",
        "s2_4_prepare_intent",
        "s2_4_install_plan",
    ],
    "adapter_ids": [
        "s2_4_capability_probe_adapter_v1",
        "s2_4_prepare_adapter_v1",
        "s2_4_install_adapter_v1",
    ],
    "adapter_binding": "AUTHORITY_LOCKED_PRODUCTION_CAPABLE",
    "component_classifier_v2": "aiml_component_effect_classification_v2",
    "install_receipt_success": "s2_4_install_effect_receipt_v1(status=APPLIED_INACTIVE)",
    "source_admission": "s2_4_source_admission_receipt_v1(status=ADMITTED)",
}


def w1_exported_abi_projection(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """W1 exported-ABI 投影:code-owned §10.2 骨架 + live registry/classifier 再導出。

    折入兩個「活」再導出令 ABI-surface drift 必然破壞 W1 導出(§10.5 #3/#27/#36):
      * 三 adapter 的 registry status 逐 id 再讀(registry 身分替換/降級 → 投影變值);
      * v2 classifier 矩陣 digest 再算(v2→v1 降級/矩陣竄改 → 投影變值)。
    fail-closed:registry 不可讀時 status 記 None(投影仍變值 → 導出失敗)。
    """

    try:
        registry = json.loads(
            (repo_root / ".codex" / "agent_registry_v1.json").read_text(encoding="utf-8")
        )
        adapters = registry.get("effect_adapters", {})
    except (OSError, json.JSONDecodeError):
        adapters = {}
    return {
        **_W1_EXPORTED_ABI,
        "registry_adapter_status": {
            adapter_id: adapters.get(adapter_id, {}).get("status")
            for adapter_id in _W1_EXPORTED_ABI["adapter_ids"]
        },
        "component_classifier_v2_digest": aiml_component_effect_class_matrix_v2_digest(),
    }


def w1_owned_path_diff_digest(
    repo_root: Path = REPO_ROOT, *, source_head: str | None = None
) -> str:
    """W1 owned-path 內容投影 digest(同 :func:`w0_owned_path_diff_digest` 機制,綁 W1 面)。

    P1-5:同樣綁 bound commit 的 blob——W0/W1/W2 三波共用同一把尺,無一例外。
    """

    return owned_path_blob_projection_digest(
        repo_root, _W1_OWNED_PATHS, source_head=source_head
    )


def _trust_pin_errors(pins: Any, repo_root: Path) -> list[str]:
    if not isinstance(pins, dict):
        return ["admission trust_pin_digests must be an object"]
    try:
        module_bytes = (repo_root / _TRUSTED_HOST_MODULE_PATH).read_bytes()
        test_bytes = (repo_root / _TRUSTED_HOST_TEST_PATH).read_bytes()
    except OSError as error:
        return [f"admission trust-pin blobs unreadable: {error}"]
    expected = {
        "trusted_host_module_blob": git_blob_sha1(module_bytes),
        "trusted_host_module_sha256": "sha256:" + hashlib.sha256(module_bytes).hexdigest(),
        "independent_test_blob": git_blob_sha1(test_bytes),
        "independent_test_sha256": "sha256:" + hashlib.sha256(test_bytes).hexdigest(),
        "operator_fingerprint": _OPERATOR_FINGERPRINT,
    }
    errors = [
        f"admission trust pin {key} does not re-hash to the §9.1 trust root"
        for key, value in expected.items()
        if pins.get(key) != value
    ]
    # 交叉綁定:指紋必須真的釘在 trusted-host 模組源碼裡(而非只在 receipt 中自洽)。
    if _OPERATOR_FINGERPRINT not in module_bytes.decode("utf-8", "replace"):
        errors.append("admission operator_fingerprint is not pinned in the trusted-host module source")
    return errors


# T4 behavioral probe:合成 production intent 的固定自洽時鐘/來源(刻意「不」用牆鐘/真 HEAD——探針
# 只驗 reachable 閘的執行,非新鮮度;自洽 now==created_at 落在 TTL 內故非 time-bomb;source_head 為合成
# 40-hex,與真 repo 無關)。target_host="trade-core" 已知通過 step 2(非 Mac/dev/loopback 標記)。
_S2_0_PROBE_CLOCK = "2026-01-01T00:00:00+00:00"
_S2_0_PROBE_SOURCE_HEAD = "0" * 40


def _unconditional_production_pending_removed(observer: Any) -> bool:
    """行為+結構雙證 S2.0 生產閘為 reachable-but-authority-locked(取代 signature-only 檢查;T4)。

    Codex 指出:僅憑 ``driver`` 參數存在於簽章來導出此旗標,會被「保留參數卻重引入無條件 pending
    return」的回歸繞過。故改為:
      (a) BEHAVIORAL——以 ``driver=None`` + 合成 VALID production intent + 無 operator SSHSIG 實跑
          ``apply_observer_bootstrap``:reachable §6 閘真執行過 step 2/2.5 並抵達 step 3,回 typed
          ``EXTERNAL_VERIFICATION_PENDING``(``AUTHORIZATION_REJECTED`` class)、``production_apply_performed``
          恆 false、零變更(driver=None 從不 mutate;離線無法偽造 operator SSHSIG,故止於 step 3——這正是
          honesty boundary)。若閘被改成 pre-step-2 的無條件 pending,reason 便不再是 AUTHORIZATION_REJECTED
          → (a) 失敗。
      (b) STRUCTURAL——靜態確認 module 源碼帶 step 5 的 ``if driver is None:`` reachable 分支且回具體
          「reachable but authority-locked: no host production driver」pending。step 5 需先過 step 3
          (真 SSHSIG),離線不可達,故此步以「gate 結構」靜態兌現(fix 明允的 fallback)。
    兩者皆成立才回 True;任一例外一律 fail-closed 回 False。
    """

    try:
        intent = observer.build_pg_observer_bootstrap_intent(
            target_class="production",
            target_host="trade-core",
            database="openclaw",
            observer_role="aiml_observer_ro",
            observed_schema="learning",
            observed_relations=["alr_consumer_events"],
            socket_dir="/var/run/postgresql",
            auth_mapping="pg_hba_ident_local",
            applier_node_id="observer_apply_actor",
            postcheck_node_id="observer_ops_postcheck",
            created_at=_S2_0_PROBE_CLOCK,
            ttl_seconds=900,
            source_head=_S2_0_PROBE_SOURCE_HEAD,
        )
        result = observer.apply_observer_bootstrap(
            intent,
            None,
            None,
            now=_S2_0_PROBE_CLOCK,
            source_head=_S2_0_PROBE_SOURCE_HEAD,
            driver=None,
        )
    except Exception:  # noqa: BLE001 - 探針任何逸出 = fail-closed 未證
        return False
    if not isinstance(result, dict):
        return False
    boundary = result.get("boundary") or {}
    behavioral_ok = (
        result.get("status") == "EXTERNAL_VERIFICATION_PENDING"
        and boundary.get("production_apply_performed") is False
        and "AUTHORIZATION_REJECTED" in str(result.get("failure_reason"))
    )
    try:
        module_source = Path(observer.__file__).read_text(encoding="utf-8")
    except (OSError, TypeError, ValueError):
        return False
    structural_ok = (
        "if driver is None:" in module_source
        and "reachable but authority-locked: no host production driver" in module_source
    )
    return bool(behavioral_ok and structural_ok)


def _s2_0_reachability_errors(proof: Any, repo_root: Path) -> list[str]:
    if not isinstance(proof, dict):
        return ["admission s2_0_driver_reachability_proof must be an object"]
    errors: list[str] = []
    registry_status: Any = None
    try:
        registry = json.loads(
            (repo_root / ".codex" / "agent_registry_v1.json").read_text(encoding="utf-8")
        )
        registry_status = (
            registry.get("effect_adapters", {})
            .get(_S2_0_ADAPTER_ID, {})
            .get("status")
        )
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"admission S2.0 registry adapter unreadable: {error}")

    import agent_governance_pg_observer_bootstrap as _observer

    expected = {
        "adapter_id": _S2_0_ADAPTER_ID,
        "registry_status": registry_status,
        # T4:行為+結構探針(非僅簽章)證 reachable §6 閘真執行且 driver-None 分支 authority-locked。
        "unconditional_production_pending_removed": _unconditional_production_pending_removed(
            _observer
        ),
        "driver_protocol_present": hasattr(_observer, "ObserverBootstrapProductionDriver"),
        "production_success_status": "APPLIED"
        if "APPLIED" in _observer.RESULT_STATUSES
        else None,
    }
    if registry_status != _S2_0_EXPECTED_REGISTRY_STATUS:
        errors.append(
            "admission S2.0 adapter registry_status is not AUTHORITY_LOCKED_PRODUCTION_CAPABLE"
        )
    errors.extend(
        f"admission s2_0_driver_reachability_proof.{key} does not re-derive"
        for key, value in expected.items()
        if proof.get(key) != value
    )
    return errors


def _wp3_system_unit_property_errors(proof: Any, repo_root: Path = REPO_ROOT) -> list[str]:
    if not isinstance(proof, dict):
        return ["admission wp3_system_unit_alignment_proof must be an object"]
    import agent_governance_alr_quiesce_inventory as _inventory

    systemd_is_system_level = _inventory.SYSTEMD == "/usr/bin/systemctl"
    try:
        # executable 再導出:allowlist 對任何 ``--user`` 形一律拒(§8.3/PR#134 system-level 語意)。
        _inventory._assert_allowlisted_systemctl(
            [_inventory.SYSTEMD, "--user", "show", _inventory.UNIT_NAME]
        )
    except _inventory.QuiesceHostReadError:
        # T5:只有 allowlist 的「預期拒絕型」例外才算 --user 形被擋下(system-level 語意成立)。
        user_form_rejected = True
    except Exception as error:  # noqa: BLE001
        # T5:任何「非預期」例外(如回歸引入的 TypeError/AttributeError)不得被誤讀為「--user 被拒」的
        # 證據——否則壞掉的 allowlist 會偽證 system-level property。fail-closed:直接記非導出 reason。
        return [
            "admission wp3_system_unit_alignment_proof --user allowlist probe raised an "
            f"unexpected (non-allowlist) error: {error!r}"
        ]
    else:
        # allowlist 竟接受 ``--user`` 形 → 非系統級語意 → user_form_rejected=False(下方 property 導出失敗)。
        user_form_rejected = False
    systemctl_user_absent = systemd_is_system_level and user_form_rejected
    # T7:database 由消費端權威 DSN 常量再導出(非硬編鏡像);讀不到即 fail-closed。
    expected_database = _consumer_authoritative_database(repo_root)
    if expected_database is None:
        return [
            "admission wp3_system_unit_alignment_proof.database cannot be re-derived from the ALR "
            "consumer authoritative DSN (_LOCAL_DSN_REQUIRED)"
        ]
    # property 非 exact unit-name:刻意「不」綁 UNIT_NAME(§7#4 unit-name 分歧 defer 至 W2)。
    expected = {
        "lifecycle_owner": "host_system_manager" if systemctl_user_absent else "unknown",
        "systemctl_user_absent": systemctl_user_absent,
        "role": _inventory.ALR_CONNECTION_ROLE,
        "database": expected_database,
    }
    return [
        f"admission wp3_system_unit_alignment_proof.{key} does not re-derive the WP3 system-level property"
        for key, value in expected.items()
        if proof.get(key) != value
    ]


def derive_source_admission_status(
    receipt: Any,
    *,
    repo_root: Path = REPO_ROOT,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    """Independently re-derive the S2.4/WP4/W0 source-admission status (§3.1).

    回傳 ``{"status": "ADMITTED"|"NOT_ADMITTED", "reasons": [...]}``。每一欄位皆由 ``repo_root``
    重算並與 receipt 比對;全部相符且九 authority 全 false 才 ADMITTED,否則回 typed 非-ADMITTED
    reason list。caller 帶 status/admitted/pass/done 於 derivation 前即拒(§10.5 #27)。``now``
    刻意不作 wall-clock 新鮮度窗(source-admission 為 build-identity 證據,無 timestamp 欄位——
    以 wall-clock 判窗會變 time-bomb;真新鮮度由 wave/closure lane 綁 source_head 拓撲保證)。
    """

    if not isinstance(receipt, dict):
        return {"status": "NOT_ADMITTED", "reasons": ["admission receipt must be an object"]}
    declared = sorted(key for key in _CALLER_STATUS_KEYS if key in receipt)
    if declared:
        return {
            "status": "NOT_ADMITTED",
            "reasons": [
                "admission receipt must not self-declare status "
                f"({', '.join(declared)}); the central validator derives ADMITTED"
            ],
        }
    # T3:derive_source_admission_status 被 derive_wave_exit_status 「直接」呼叫(未經 validate_aiml_artifact),
    # 該路徑先前「不」施加 closed schema 的 additionalProperties:false。故在此(caller-status 預檢後、任何再導出前)
    # 自行跑一次 s2_4_source_admission_receipt_v1 的 closed-schema 子集驗——任一 forbidden property(self_digest 會把
    # 任意鍵一併雜湊,故不會被 self_digest 檢查抓到)即回 NOT_ADMITTED,杜絕帶額外欄位的 admission 導出 ADMITTED→PASS。
    try:
        _admission_schema = _load_schema("s2_4_source_admission_receipt_v1")
        _schema_errors = schema_subset_errors(receipt, _admission_schema, _admission_schema)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return {
            "status": "NOT_ADMITTED",
            "reasons": [f"admission closed-schema is unloadable: {error}"],
        }
    if _schema_errors:
        return {"status": "NOT_ADMITTED", "reasons": _schema_errors}
    reasons: list[str] = []
    if receipt.get("schema_version") != "s2_4_source_admission_receipt_v1":
        reasons.append("admission schema_version is not s2_4_source_admission_receipt_v1")
    if receipt.get("work_package") != "WP4" or receipt.get("wave") != "W0":
        reasons.append("admission work_package/wave must be WP4/W0")
    if receipt.get("self_digest") != artifact_self_digest(receipt):
        reasons.append("admission self_digest does not bind the canonical receipt")
    source_head = receipt.get("source_head")
    if receipt.get("predecessor_heads") != _PREDECESSOR_HEADS:
        reasons.append("admission predecessor_heads differ from the exact §1.2 W0 lineage")
    if not (isinstance(source_head, str) and re.fullmatch(r"[0-9a-f]{40}", source_head)):
        reasons.append("admission source_head must be a 40-hex commit")
    else:
        # T2:source_head 必須「等於」目前 checkout HEAD——所有證據皆由此 checkout 再導出,若 receipt 宣稱
        # 另一世代卻從當前樹導 ADMITTED 即為漂移。predecessor 祖裔檢查仍保留(下方),兩者並存。
        head = _git_head(repo_root)
        if head is None:
            reasons.append(
                "admission source_head cannot be bound: repo HEAD is unreadable (fail-closed)"
            )
        elif source_head != head:
            reasons.append(
                "admission source_head is not the current checkout HEAD "
                "(evidence is re-derived from HEAD; a claimed-generation mismatch is drift)"
            )
        # W5 對抗審計第三輪 P2:淺 clone(CI 的預設 fetch-depth:1)上這些 commit 根本不在
        # graft 裡,``git merge-base --is-ancestor`` 於是回非零。舊訊息說「不是祖先」,而真相
        # 是「這個物件不在這棵樹裡」——operator 會去查一個不存在的歷史問題。先問這棵 repo 是
        # 不是淺的,是的話把補救指令逐字說出來。
        is_shallow = git_is_shallow_repository(repo_root)
        for name, predecessor in _PREDECESSOR_HEADS.items():
            if not _git_is_ancestor(repo_root, predecessor, source_head):
                if is_shallow:
                    reasons.append(
                        f"admission predecessor {name} ({predecessor}) cannot be checked: "
                        "this is a SHALLOW repository and the object is not in the graft, so "
                        "ancestry is undecidable rather than false — re-run with "
                        "`fetch-depth: 0` (actions/checkout) or `git fetch --unshallow`"
                    )
                else:
                    reasons.append(
                        f"admission predecessor {name} is not an ancestor of source_head"
                    )
    try:
        texts = _read_three_head_texts(repo_root)
    except OSError as error:
        reasons.append(f"admission three-head projection unreadable: {error}")
    else:
        reasons.extend(_projection_effect_dag_errors(texts))
        if receipt.get("three_head_projection_digest") != three_head_projection_digest(
            repo_root
        ):
            reasons.append("admission three_head_projection_digest does not re-derive")
    reasons.extend(_trust_pin_errors(receipt.get("trust_pin_digests"), repo_root))
    reasons.extend(
        _s2_0_reachability_errors(receipt.get("s2_0_driver_reachability_proof"), repo_root)
    )
    reasons.extend(
        _wp3_system_unit_property_errors(
            receipt.get("wp3_system_unit_alignment_proof"), repo_root
        )
    )
    if receipt.get("frozen_classifier_digest") != aiml_effect_classifier_digest():
        reasons.append(
            "admission frozen_classifier_digest does not re-derive to the frozen S0.3 classifier"
        )
    if receipt.get("component_classifier_v1_digest") != aiml_component_effect_class_matrix_digest():
        reasons.append("admission component_classifier_v1_digest does not re-derive")
    if receipt.get("production_authority_flags") != _ALL_FALSE_PRODUCTION_FLAGS:
        reasons.append(
            "admission production_authority_flags must all be false (nine authorities / apply / running)"
        )
    # 綁定(而非只驗形狀):negative_tests_pass 必須重導出等於 code-owned W0 負向測試清單的
    # 正規 digest。任意形狀合法卻不符清單的 digest 一律拒——admission 因此真正背書 W0 負向測試
    # 身分,而非讓偽造 receipt 帶任意 digest 佯裝負向測試已驗。
    if receipt.get("negative_tests_pass") != w0_negative_test_manifest_digest():
        reasons.append(
            "admission negative_tests_pass does not re-derive to the W0 negative-test manifest"
        )
    return {
        "status": "ADMITTED" if not reasons else "NOT_ADMITTED",
        "reasons": reasons,
    }


_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _nonempty_digest_list_ok(value: Any) -> bool:
    # T1:非空 list 且每項皆為合法 sha256 digest(拒 empty/非 list/含畸形項)。
    return (
        isinstance(value, list)
        and len(value) > 0
        and all(isinstance(item, str) and _DIGEST_RE.fullmatch(item) for item in value)
    )


# W5 對抗審計第三輪 P1-D:owned-scope 的 fail-closed 消費原本只有 W5 有(measured:
# w2/w3/w4 consumed=0, w5 consumed=1)。逐波的 owned-path 集合在此登記,裁決本體
# (內容定址 + fail-closed 文案)住在 schema_core.owned_scope_delta_reasons。
_WAVE_OWNED_PATHS: dict[str, tuple[str, ...]] = {
    "W0": _W0_OWNED_PATHS,
    "W1": _W1_OWNED_PATHS,
    "W2": _W2_OWNED_PATHS,
    "W3": _W3_OWNED_PATHS,
    "W4": _W4_OWNED_PATHS,
    "W5": _W5_OWNED_PATHS,
}


def _owned_scope_delta_reasons(
    wave: str, receipt: dict[str, Any], repo_root: Path
) -> list[str]:
    paths = _WAVE_OWNED_PATHS.get(wave)
    if paths is None:
        return []
    return owned_scope_delta_reasons(
        wave, paths, repo_root, source_head=receipt.get("source_head")
    )


def _wave_exit_structural_errors(
    receipt: dict[str, Any], repo_root: Path = REPO_ROOT
) -> list[str]:
    """Self-contained wave-exit re-derivations(不需綁定 admission 物件即可在中央閘檢查)。"""

    reasons: list[str] = []
    if receipt.get("schema_version") != "s2_4_wave_exit_receipt_v1":
        reasons.append("wave-exit schema_version is not s2_4_wave_exit_receipt_v1")
    if receipt.get("self_digest") != artifact_self_digest(receipt):
        reasons.append("wave-exit self_digest does not bind the canonical receipt")
    if receipt.get("production_authority_flags") != _ALL_FALSE_PRODUCTION_FLAGS:
        reasons.append("wave-exit production_authority_flags must all be false")
    wave = receipt.get("wave")
    if wave == "W0":
        if receipt.get("predecessor_wave_receipt_digest") is not None:
            reasons.append(
                "W0 wave-exit has no predecessor wave (predecessor_wave_receipt_digest must be null)"
            )
        if receipt.get("exported_abi_digest") != canonical_digest(_W0_EXPORTED_ABI):
            reasons.append("wave-exit exported_abi_digest does not equal the W0 ABI delta")
        if receipt.get("owned_path_manifest_digest") != canonical_digest(sorted(_W0_OWNED_PATHS)):
            reasons.append("wave-exit owned_path_manifest_digest is not the exact W0 owned-path set")
        # T1(a):owned_path_diff_digest 綁定到 W0 owned-path 內容投影的再導出(同 owned_path_manifest_digest
        # 的 canonical_digest 機制),故 arbitrary/empty 值無法通過 W0 完成閘。
        if receipt.get("owned_path_diff_digest") != w0_owned_path_diff_digest(repo_root):
            reasons.append(
                "wave-exit owned_path_diff_digest does not re-derive the W0 owned-path content projection"
            )
    elif wave == "W1":
        # W1(contracts/routing):同 W0 機制,但綁 W1 面;另需非 null 的前導 W0 digest
        # (predecessor 物件鏈的完整驗在 derive_wave_exit_status,結構層先擋 null)。
        if receipt.get("predecessor_wave_receipt_digest") is None:
            reasons.append(
                "W1 wave-exit requires a non-null predecessor_wave_receipt_digest "
                "(the W0 wave-exit self_digest)"
            )
        abi_projection = w1_exported_abi_projection(repo_root)
        if receipt.get("exported_abi_digest") != canonical_digest(abi_projection):
            reasons.append(
                "wave-exit exported_abi_digest does not re-derive the W1 exported-ABI projection"
            )
        # ABI-surface 活再導出(不只 digest 等式):三 adapter 的 registry status 必真為凍結
        # binding 字串——registry 身分替換/降級即失敗(§10.5 #3/#36 的 adapter-substitution 縫)。
        for adapter_id, status in sorted(abi_projection["registry_adapter_status"].items()):
            if status != _W1_EXPORTED_ABI["adapter_binding"]:
                reasons.append(
                    f"W1 adapter {adapter_id} registry status does not re-derive "
                    "AUTHORITY_LOCKED_PRODUCTION_CAPABLE"
                )
        if receipt.get("owned_path_manifest_digest") != canonical_digest(sorted(_W1_OWNED_PATHS)):
            reasons.append("wave-exit owned_path_manifest_digest is not the exact W1 owned-path set")
        if receipt.get("owned_path_diff_digest") != w1_owned_path_diff_digest(repo_root):
            reasons.append(
                "wave-exit owned_path_diff_digest does not re-derive the W1 owned-path content projection"
            )
    elif wave == "W2":
        # W2(runnable application):同 W0/W1 機制,綁 W2 面;owned-path/exported-ABI/
        # 兩個活裁決(privilege-split / application-closure)委派 wave_w2 葉再導出。
        reasons.extend(w2_structural_errors(receipt, repo_root))
    elif wave == "W3":
        # W3(typed host driver·W3a):同 W0/W1/W2 機制,綁 W3 面;capability-probe 與
        # PG-topology 兩組活裁決(source-lane 零變更 / route-surface 拒 builder 權限 /
        # scope 替換拒 / topology PROVEN·UNPROVEN 雙向 / guard↔身分列欄位契約)委派
        # wave_w3 葉再導出。
        reasons.extend(w3_structural_errors(receipt, repo_root))
    elif wave == "W4":
        # W4(aggregate transaction·W4a):同一機制,綁 W4 面;permit↔plan 綁定、install lock、
        # 三本 WAL journal 的 durability/corrupt/reconcile、§9 TTL 不等式與獨立補償後 postcheck
        # 的活裁決委派 wave_w4 葉再導出。
        reasons.extend(w4_structural_errors(receipt, repo_root))
    elif wave == "W5":
        # W5(source closure):同一機制,綁 W5 面;§10.5 六組覆蓋缺口的活裁決委派 wave_w5 葉。
        reasons.extend(w5_structural_errors(receipt, repo_root))
    else:
        # W6+ 各 wave 於其自身 owned path 擴充 derivation;未實作的 wave 一律 fail-closed。
        reasons.append("wave-exit derivation is only implemented for W0/W1/W2/W3/W4/W5 so far")
        return reasons
    # P1-D:每一波都必須消費自己的 owned-scope delta,而不是只有 W5。
    reasons.extend(_owned_scope_delta_reasons(str(wave), receipt, repo_root))
    # T1(b):test/capture/review 三類證據必為「非空」的合法 digest list——empty/arbitrary 不得導出 PASS。
    # 誠實邊界:每一支 test/capture/review 的「PLATFORM-ATTESTED 綁定」屬下游 EFFECT/closure 關切(離線
    # 結構驗無法認證其真跑過);此處只擋「空/畸形證據仍導 PASS」的洞,不冒充已認證 runtime。
    for field in ("test_digests", "capture_digests", "review_fragment_digests"):
        if not _nonempty_digest_list_ok(receipt.get(field)):
            reasons.append(
                f"wave-exit {field} must be a non-empty list of sha256 digests "
                "(empty/arbitrary evidence must not derive PASS)"
            )
    return reasons


# W2/W3/W4/W5 predecessor-鏈規格 =(前導 wave, 必需 chain 長度, wave-specific 綁定謂詞);W0 無前導、W1 綁定為 inline(chain 必空),兩者不入表。
_WAVE_PREDECESSOR_CHAIN = {
    "W2": ("W1", 1, w2_chain_binding_errors),
    "W3": ("W2", 2, w3_chain_binding_errors),
    "W4": ("W3", 3, w4_chain_binding_errors),
    "W5": ("W4", 4, w5_chain_binding_errors),
}


def derive_wave_exit_status(
    receipt: Any,
    *,
    repo_root: Path = REPO_ROOT,
    now: str | datetime | None = None,
    source_admission_receipt: Any = None,
    predecessor_wave_receipt: Any = None,
    predecessor_wave_chain: Any = (),
) -> dict[str, Any]:
    """Independently re-derive the W0/W1/W2/W3/W4/W5 wave-exit status (§3.2/§10.3).

    回傳 ``{"status": "PASS"|"NOT_PASS", "reasons": [...]}``。W0 的 PASS 需:綁定的
    ``source_admission_receipt`` 再導出 ADMITTED 且其 self_digest == 本 receipt 綁定的
    ``source_admission_receipt_digest``、owned-path/ABI/flags 再導出相符、source_head 一致。
    W1 的 PASS 另需 caller 傳 ``predecessor_wave_receipt``(W0 wave-exit 物件,姿態同
    ``source_admission_receipt``):該 W0 receipt 必須「連同其綁定 admission」在此再導出 PASS、
    其 self_digest == 本 receipt 的 ``predecessor_wave_receipt_digest``、三方 source_head 一致
    且等於目前 checkout HEAD——admission 鏈不因跨波而鬆脫。W2 鏡 W1:predecessor 是 W1
    wave-exit 物件,且其「自身的鏈」必須先再導出 PASS——caller 另以
    ``predecessor_wave_chain=(regenerated W0 wave-exit,)`` 供 W1 遞迴綁其前導(次序=
    由舊到新、不含 ``predecessor_wave_receipt`` 本身;W0/W1 拒非空 chain)。W3 再鏡 W2:
    predecessor 是 W2 wave-exit 物件,``predecessor_wave_chain=(W0, W1)``;W4 再鏡 W3:
    predecessor 是 W3 wave-exit 物件,``predecessor_wave_chain=(W0, W1, W2)``;W5 再鏡 W4:
    predecessor 是 W4 wave-exit 物件,``predecessor_wave_chain=(W0, W1, W2, W3)``。caller 帶
    status/pass/done 於 derivation 前即拒(§10.3/§10.5 #27)。

    邊界(必要非充分):中央閘 :func:`validate_aiml_artifact` 對 wave-exit 只做 STRUCTURAL-ONLY
    再導出(不綁 admission/predecessor 物件),乾淨的 ``[]`` 結果「不」等於 PASS——它未驗
    ``source_admission_receipt_digest`` / ``predecessor_wave_receipt_digest`` 是否綁到真能再導出
    ADMITTED/PASS 的物件。真正的 PASS 只能由「本函式帶已導出物件」授予(鏡射 CLAUDE.md
    standalone-CLI / typed-authority 邊界:離線結構驗無法自證 PASS)。
    """

    if not isinstance(receipt, dict):
        return {"status": "NOT_PASS", "reasons": ["wave-exit receipt must be an object"]}
    declared = sorted(key for key in _CALLER_STATUS_KEYS if key in receipt)
    if declared:
        return {
            "status": "NOT_PASS",
            "reasons": [
                "wave-exit receipt must not self-declare status "
                f"({', '.join(declared)}); the central validator derives PASS"
            ],
        }
    # T3:此路徑亦不經 validate_aiml_artifact,故在此自行跑 wave-exit 的 closed-schema 子集驗
    # (additionalProperties:false + minItems),任一 forbidden property / 空證據 list 即回 NOT_PASS。
    try:
        _wave_schema = _load_schema("s2_4_wave_exit_receipt_v1")
        _schema_errors = schema_subset_errors(receipt, _wave_schema, _wave_schema)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return {
            "status": "NOT_PASS",
            "reasons": [f"wave-exit closed-schema is unloadable: {error}"],
        }
    if _schema_errors:
        return {"status": "NOT_PASS", "reasons": _schema_errors}
    reasons = _wave_exit_structural_errors(receipt, repo_root)
    wave = receipt.get("wave")
    if wave not in {"W0", "W1", "W2", "W3", "W4", "W5"}:
        return {"status": "NOT_PASS", "reasons": reasons}
    chain = tuple(predecessor_wave_chain) if predecessor_wave_chain else ()
    if wave in {"W0", "W1"} and chain:
        # fail-closed:W0/W1 不消費 chain——靜默忽略會讓 caller 誤信多綁了前導。
        reasons.append(f"{wave} wave-exit does not accept a predecessor_wave_chain")
        return {"status": "NOT_PASS", "reasons": reasons}
    if source_admission_receipt is None:
        reasons.append(
            f"{wave} wave-exit requires the bound source_admission_receipt to re-derive ADMITTED"
        )
        return {"status": "NOT_PASS", "reasons": reasons}
    admission = derive_source_admission_status(
        source_admission_receipt, repo_root=repo_root, now=now
    )
    # T6:綁定的 admission 若非 ADMITTED 或根本不是 dict(list/str/None),立即回 typed NOT_PASS——
    # 在任何 .get(...) 之前護欄,杜絕 non-dict 綁定物件觸發 AttributeError。
    if admission["status"] != "ADMITTED" or not isinstance(source_admission_receipt, dict):
        reasons.append(
            "wave-exit bound source_admission_receipt does not derive ADMITTED: "
            + "; ".join(admission["reasons"])
        )
        return {"status": "NOT_PASS", "reasons": reasons}
    if wave == "W0":
        if source_admission_receipt.get("self_digest") != receipt.get(
            "source_admission_receipt_digest"
        ):
            reasons.append(
                "wave-exit source_admission_receipt_digest does not bind the derived admission receipt"
            )
        if source_admission_receipt.get("source_head") != receipt.get("source_head"):
            reasons.append("wave-exit source_head differs from the bound admission receipt")
        return {
            "status": "PASS" if not reasons else "NOT_PASS",
            "reasons": reasons,
        }
    # ── W2/W3/W4:predecessor 鏈(前導 wave-exit 物件**連同其自身的鏈**再導出 PASS)。三者
    # 收斂同形,由 :data:`_WAVE_PREDECESSOR_CHAIN` 表驅動(行為逐字等同展開三次)。
    spec = _WAVE_PREDECESSOR_CHAIN.get(wave)
    if spec is not None:
        predecessor_wave, chain_length, binding_errors = spec
        if predecessor_wave_receipt is None:
            reasons.append(
                f"{wave} wave-exit requires the bound predecessor_wave_receipt (the "
                f"{predecessor_wave} wave-exit receipt object) to re-derive PASS with its bound "
                "predecessor/admission chain"
            )
            return {"status": "NOT_PASS", "reasons": reasons}
        if len(chain) != chain_length:
            reasons.append(
                f"{wave} wave-exit requires predecessor_wave_chain=(the {chain_length} "
                "regenerated W0.. wave-exit receipts, oldest first) so the "
                f"{predecessor_wave} predecessor can re-derive PASS"
            )
            return {"status": "NOT_PASS", "reasons": reasons}
        predecessor = derive_wave_exit_status(
            predecessor_wave_receipt,
            repo_root=repo_root,
            now=now,
            source_admission_receipt=source_admission_receipt,
            predecessor_wave_receipt=chain[-1],
            predecessor_wave_chain=tuple(chain[:-1]),
        )
        # 同 T6 護欄:非 dict / 非 PASS 的 predecessor 立即 typed NOT_PASS(鏈斷即斷)。
        if predecessor["status"] != "PASS" or not isinstance(predecessor_wave_receipt, dict):
            reasons.append(
                f"{wave} wave-exit bound predecessor_wave_receipt does not derive PASS: "
                + "; ".join(predecessor["reasons"])
            )
            return {"status": "NOT_PASS", "reasons": reasons}
        reasons.extend(
            binding_errors(
                receipt, source_admission_receipt, predecessor_wave_receipt, _git_head(repo_root)
            )
        )
        return {
            "status": "PASS" if not reasons else "NOT_PASS",
            "reasons": reasons,
        }
    # ── W1:predecessor 鏈(W0 wave-exit 物件連同其 admission 再導出 PASS)────────────
    if predecessor_wave_receipt is None:
        reasons.append(
            "W1 wave-exit requires the bound predecessor_wave_receipt (the W0 wave-exit "
            "receipt object) to re-derive PASS with its bound admission"
        )
        return {"status": "NOT_PASS", "reasons": reasons}
    predecessor = derive_wave_exit_status(
        predecessor_wave_receipt,
        repo_root=repo_root,
        now=now,
        source_admission_receipt=source_admission_receipt,
    )
    # 同 T6 護欄:非 dict / 非 PASS 的 predecessor 立即 typed NOT_PASS(admission 鏈斷即斷)。
    if predecessor["status"] != "PASS" or not isinstance(predecessor_wave_receipt, dict):
        reasons.append(
            "W1 wave-exit bound predecessor_wave_receipt does not derive PASS: "
            + "; ".join(predecessor["reasons"])
        )
        return {"status": "NOT_PASS", "reasons": reasons}
    if predecessor_wave_receipt.get("wave") != "W0":
        reasons.append("W1 wave-exit predecessor must be the W0 wave-exit receipt")
    if predecessor_wave_receipt.get("self_digest") != receipt.get(
        "predecessor_wave_receipt_digest"
    ):
        reasons.append(
            "W1 predecessor_wave_receipt_digest does not bind the derived W0 wave-exit receipt"
        )
    if source_admission_receipt.get("self_digest") != receipt.get(
        "source_admission_receipt_digest"
    ):
        reasons.append(
            "wave-exit source_admission_receipt_digest does not bind the derived admission receipt"
        )
    # source_head 三方一致 + 等於目前 checkout HEAD(admission 的 T2 已綁 HEAD;此處把 W1 receipt
    # 也直接釘住,杜絕「W1 receipt 宣稱另一世代卻由當前樹導 PASS」的漂移)。
    head = _git_head(repo_root)
    if head is None:
        reasons.append(
            "W1 wave-exit source_head cannot be bound: repo HEAD is unreadable (fail-closed)"
        )
    elif receipt.get("source_head") != head:
        reasons.append("W1 wave-exit source_head is not the current checkout HEAD")
    if receipt.get("source_head") != predecessor_wave_receipt.get("source_head"):
        reasons.append("W1 wave-exit source_head differs from the bound W0 wave-exit receipt")
    if receipt.get("source_head") != source_admission_receipt.get("source_head"):
        reasons.append("W1 wave-exit source_head differs from the bound admission receipt")
    return {
        "status": "PASS" if not reasons else "NOT_PASS",
        "reasons": reasons,
    }


def validate_aiml_artifact(
    artifact: Any, *, now: str | datetime | None = None
) -> list[str]:
    """Validate one typed artifact without third-party schema dependencies."""

    if not isinstance(artifact, dict):
        return ["AIML artifact must be an object"]
    schema_version = artifact.get("schema_version")
    if not isinstance(schema_version, str):
        return ["AIML artifact schema_version must be a string"]
    try:
        schema = _load_schema(schema_version)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return [str(error)]
    errors = schema_subset_errors(artifact, schema, schema)
    if errors:
        return errors
    if schema_version == "landing_scope_v1" and artifact["landing_scope_id"] != (
        landing_scope_identity_digest(artifact)
    ):
        errors.append("landing_scope_id does not bind the exact landing scope identity")
    if schema_version == "landing_scope_v1" and any(
        environment["environment_id"] != evidence_environment_identity_digest(
            environment
        )
        for environment in artifact["evidence_environments"]
    ):
        errors.append("evidence_environment identity digest is invalid")
    if schema_version == "landing_scope_v1" and not _canonical_list_is_sorted_unique(
        artifact["decision_cells"]
    ):
        errors.append("landing scope decision_cells must be sorted and unique")
    if schema_version == "landing_scope_v1":
        environment_ids = {
            environment["environment_id"]
            for environment in artifact["evidence_environments"]
        }
        if any(
            edge["from_environment_id"] not in environment_ids
            or edge["to_environment_id"] not in environment_ids
            for edge in artifact["promotion_edges"]
        ):
            errors.append(
                "landing scope promotion edge references an unknown environment"
            )
        if any(
            edge["from_environment_id"] == edge["to_environment_id"]
            for edge in artifact["promotion_edges"]
        ):
            errors.append("landing scope promotion edge cannot target itself")
        promotion_graph = {environment_id: set() for environment_id in environment_ids}
        for edge in artifact["promotion_edges"]:
            if (
                edge["from_environment_id"] in promotion_graph
                and edge["to_environment_id"] in promotion_graph
            ):
                promotion_graph[edge["from_environment_id"]].add(
                    edge["to_environment_id"]
                )
        if _directed_graph_has_cycle(promotion_graph):
            errors.append("landing scope promotion graph contains a cycle")
    if schema_version == "session_attempt_v1":
        scope_ref = artifact["scope_ref"]
        if artifact["session_id"].startswith("S0.") and scope_ref != {
            "kind": "PROGRAM",
            "landing_scope_id": None,
        }:
            errors.append("S0.x session attempt requires the PROGRAM null scope_ref")
        if (
            scope_ref["kind"] == "PROGRAM"
            and scope_ref["landing_scope_id"] is not None
        ) or (
            scope_ref["kind"] == "LANDING_SCOPE"
            and scope_ref["landing_scope_id"] is None
        ):
            errors.append("session attempt scope_ref kind and landing_scope_id disagree")
        if artifact["attempt_id"] != session_attempt_identity_digest(artifact):
            errors.append("attempt_id does not bind the exact Session attempt identity")
        if artifact["self_digest"] != artifact_self_digest(artifact):
            errors.append("session attempt self_digest is invalid")
        expected_attempt_key = {
            "session_id": artifact["session_id"],
            "scope_ref": artifact["scope_ref"],
            "cohort_epoch": artifact["cohort_epoch"],
            "attempt": artifact["attempt"],
        }
        if artifact["attempt_key"] != expected_attempt_key:
            errors.append("session attempt_key differs from its canonical row fields")
        bootstrap = artifact["bootstrap_admission"]
        attempt_phase = artifact["attempt_phase"]
        if bootstrap["baseline_head"] != artifact["source"]["baseline_head"]:
            errors.append("session bootstrap baseline differs from source baseline")
        # 只有 SOURCE_BUILD 持有 writer lease;此時 lease.lease_id 與
        # bootstrap.writer_lease_id 必須互綁。POST_MERGE 為唯讀收尾,schema 已禁止
        # 兩者出現,故此綁定僅在 SOURCE_BUILD 生效。
        if attempt_phase == "SOURCE_BUILD" and (
            bootstrap["writer_lease_id"] != artifact["lease"]["lease_id"]
        ):
            errors.append("session bootstrap writer lease binding is invalid")
        errors.extend(_s0_3_work_package_errors(
            artifact["work_package"],
            session_id=artifact["session_id"],
            attempt_phase=artifact["attempt_phase"],
            attempt_paths=artifact["path_manifest"],
        ))
        if artifact["path_manifest"] != sorted(set(artifact["path_manifest"])):
            errors.append("session attempt path_manifest must be sorted and unique")
        writer_paths = [
            path
            for node in artifact["dag_nodes"]
            for path in node["writer_paths"]
        ]
        writer_nodes = [
            node for node in artifact["dag_nodes"] if node["writer_paths"]
        ]
        if len(writer_nodes) > 2:
            errors.append("session attempt admits more than two writer nodes")
        if any(
            node["writer_paths"] != sorted(set(node["writer_paths"]))
            for node in writer_nodes
        ):
            errors.append("session attempt writer path ownership must be sorted and unique")
        if len(writer_paths) != len(set(writer_paths)):
            errors.append("session attempt writer path ownership overlaps")
        if not set(writer_paths).issubset(set(artifact["path_manifest"])):
            errors.append("session attempt writer paths exceed path_manifest")
        native = artifact["native_admission"]
        matching_native_nodes = [
            node
            for node in artifact["dag_nodes"]
            if node["node_id"] == native["node_id"]
            and node["node_class"] == native["node_class"]
            and node["permission"] == native["permission"]
        ]
        if len(matching_native_nodes) != 1:
            errors.append("session native admission does not match exactly one DAG node")
        if attempt_phase == "SOURCE_BUILD":
            try:
                acquired_at = _parse_timestamp(artifact["lease"]["acquired_at"])
                heartbeat_at = _parse_timestamp(artifact["lease"]["heartbeat_at"])
                expires_at = _parse_timestamp(artifact["lease"]["expires_at"])
                if not acquired_at <= heartbeat_at < expires_at:
                    errors.append("session attempt lease timestamps are out of order")
                if isinstance(now, str):
                    evaluated_at = _parse_timestamp(now)
                elif isinstance(now, datetime):
                    if now.tzinfo is None:
                        raise ValueError("now must be timezone-aware")
                    evaluated_at = now
                else:
                    evaluated_at = datetime.now(timezone.utc)
                if (
                    evaluated_at >= expires_at
                    and artifact["status"] in {"CLAIMED", "IN_PROGRESS"}
                ):
                    errors.append("expired session attempt must enter RECOVERY_REQUIRED")
            except (TypeError, ValueError) as error:
                errors.append(f"session attempt lease timestamp is invalid: {error}")
        elif attempt_phase == "POST_MERGE_FINALIZATION":
            # 收尾階段不得殘留任何 writer lease;唯讀 admission 必須 read_only=true,
            # 且 admitted_at <= heartbeat_at(心跳不得早於納入時刻)。schema 已強制
            # read_only_admission 存在,此處為防禦性複核。
            if "lease" in artifact:
                errors.append("post-merge finalization attempt cannot hold a writer lease")
            if "writer_lease_id" in bootstrap:
                errors.append(
                    "post-merge finalization bootstrap cannot hold a writer lease id"
                )
            read_only_admission = artifact["read_only_admission"]
            if read_only_admission["read_only"] is not True:
                errors.append("post-merge finalization requires a read-only admission")
            try:
                admitted_at = _parse_timestamp(read_only_admission["admitted_at"])
                heartbeat_at = _parse_timestamp(read_only_admission["heartbeat_at"])
                if not admitted_at <= heartbeat_at:
                    errors.append(
                        "post-merge read-only admission timestamps are out of order"
                    )
            except (TypeError, ValueError) as error:
                errors.append(
                    f"post-merge read-only admission timestamp is invalid: {error}"
                )
    if schema_version == "aiml_landing_session_attempt_v1":
        # S1 formal-closure Wave A:generalized S1+ attempt。結構鏡射 session_attempt_v1 但
        # 走 sibling _aiml_landing_work_package_errors(不含 S0.3 const 等式),並新增 classifier-
        # derived required_effects / actor!=verifier / closure_binding 綁定。§13 C6:session_id 為裸
        # "S0" 或起始 "S0." 一律拒(鏡射 S0 session 家族全集 {"S0"} ∪ {"S0.*"})——寬鬆的 S1 schema
        # 不得用來重表任何 S0.x attempt(裸 "S0" 亦不得漏網)。
        scope_ref = artifact["scope_ref"]
        if artifact["session_id"] == "S0" or artifact["session_id"].startswith("S0."):
            errors.append(
                "aiml_landing_session_attempt_v1 cannot re-express an S0.x session "
                "(S0.* attempts use the sealed session_attempt_v1 with frozen const pins)"
            )
        if (
            scope_ref["kind"] == "PROGRAM"
            and scope_ref["landing_scope_id"] is not None
        ) or (
            scope_ref["kind"] == "LANDING_SCOPE"
            and scope_ref["landing_scope_id"] is None
        ):
            errors.append("landing session attempt scope_ref kind and landing_scope_id disagree")
        if artifact["attempt_id"] != session_attempt_identity_digest(artifact):
            errors.append("landing attempt_id does not bind the exact Session attempt identity")
        if artifact["self_digest"] != artifact_self_digest(artifact):
            errors.append("landing session attempt self_digest is invalid")
        expected_attempt_key = {
            "session_id": artifact["session_id"],
            "scope_ref": artifact["scope_ref"],
            "cohort_epoch": artifact["cohort_epoch"],
            "attempt": artifact["attempt"],
        }
        if artifact["attempt_key"] != expected_attempt_key:
            errors.append("landing session attempt_key differs from its canonical row fields")
        bootstrap = artifact["bootstrap_admission"]
        attempt_phase = artifact["attempt_phase"]
        if bootstrap["baseline_head"] != artifact["source"]["baseline_head"]:
            errors.append("landing session bootstrap baseline differs from source baseline")
        if attempt_phase == "SOURCE_BUILD" and (
            bootstrap["writer_lease_id"] != artifact["lease"]["lease_id"]
        ):
            errors.append("landing session bootstrap writer lease binding is invalid")
        errors.extend(_aiml_landing_work_package_errors(
            artifact["work_package"],
            attempt_phase=artifact["attempt_phase"],
            attempt_paths=artifact["path_manifest"],
        ))
        if artifact["path_manifest"] != sorted(set(artifact["path_manifest"])):
            errors.append("landing session attempt path_manifest must be sorted and unique")
        writer_paths = [
            path
            for node in artifact["dag_nodes"]
            for path in node["writer_paths"]
        ]
        writer_nodes = [
            node for node in artifact["dag_nodes"] if node["writer_paths"]
        ]
        if len(writer_nodes) > 2:
            errors.append("landing session attempt admits more than two writer nodes")
        if any(
            node["writer_paths"] != sorted(set(node["writer_paths"]))
            for node in writer_nodes
        ):
            errors.append("landing session attempt writer path ownership must be sorted and unique")
        if len(writer_paths) != len(set(writer_paths)):
            errors.append("landing session attempt writer path ownership overlaps")
        if not set(writer_paths).issubset(set(artifact["path_manifest"])):
            errors.append("landing session attempt writer paths exceed path_manifest")
        native = artifact["native_admission"]
        matching_native_nodes = [
            node
            for node in artifact["dag_nodes"]
            if node["node_id"] == native["node_id"]
            and node["node_class"] == native["node_class"]
            and node["permission"] == native["permission"]
        ]
        if len(matching_native_nodes) != 1:
            errors.append("landing session native admission does not match exactly one DAG node")
        if attempt_phase == "SOURCE_BUILD":
            try:
                acquired_at = _parse_timestamp(artifact["lease"]["acquired_at"])
                heartbeat_at = _parse_timestamp(artifact["lease"]["heartbeat_at"])
                expires_at = _parse_timestamp(artifact["lease"]["expires_at"])
                if not acquired_at <= heartbeat_at < expires_at:
                    errors.append("landing session attempt lease timestamps are out of order")
                if isinstance(now, str):
                    evaluated_at = _parse_timestamp(now)
                elif isinstance(now, datetime):
                    if now.tzinfo is None:
                        raise ValueError("now must be timezone-aware")
                    evaluated_at = now
                else:
                    evaluated_at = datetime.now(timezone.utc)
                if (
                    evaluated_at >= expires_at
                    and artifact["status"] in {"CLAIMED", "IN_PROGRESS"}
                ):
                    errors.append("expired landing session attempt must enter RECOVERY_REQUIRED")
            except (TypeError, ValueError) as error:
                errors.append(f"landing session attempt lease timestamp is invalid: {error}")
        elif attempt_phase == "POST_MERGE_FINALIZATION":
            if "lease" in artifact:
                errors.append("landing post-merge finalization attempt cannot hold a writer lease")
            if "writer_lease_id" in bootstrap:
                errors.append(
                    "landing post-merge finalization bootstrap cannot hold a writer lease id"
                )
            read_only_admission = artifact["read_only_admission"]
            if read_only_admission["read_only"] is not True:
                errors.append("landing post-merge finalization requires a read-only admission")
        # --- S1 classifier-derived effect binding + explicit closure binding ---
        adapter_id = artifact["adapter_id"]
        if artifact["actor_node"] == artifact["independent_postcheck_node"]:
            errors.append(
                "landing session attempt actor_node must differ from independent_postcheck_node"
            )
        if any(
            effect.get("adapter_id") != adapter_id
            for effect in artifact["required_effects"]
        ):
            errors.append(
                "landing session attempt required_effects adapter_id must equal the attempt adapter_id"
            )
        closure_binding = artifact["closure_binding"]
        for digest_field in ("closure_packet_digest", "effect_receipt_digest"):
            if not re.fullmatch(
                r"sha256:[0-9a-f]{64}", str(closure_binding.get(digest_field, ""))
            ):
                errors.append(
                    f"landing session attempt closure_binding {digest_field} is not a sha256 digest"
                )
        if closure_binding.get("effect_adapter_id") != adapter_id:
            errors.append(
                "landing session attempt closure_binding effect_adapter_id must equal the attempt adapter_id"
            )
    if schema_version == "aiml_receipt_dependency_graph_v1":
        try:
            errors.extend(_dependency_graph_errors(artifact, now=now))
        except (TypeError, ValueError) as error:
            errors.append(f"receipt dependency graph timestamp is invalid: {error}")
    if schema_version == "aiml_required_effect_classification_v1":
        if artifact["classification_id"] != _effect_classification_identity_digest(
            artifact
        ):
            errors.append("AIML effect classification_id is invalid")
        if artifact["self_digest"] != artifact_self_digest(artifact):
            errors.append("AIML effect classification self_digest is invalid")
        if artifact["classifier_digest"] != aiml_effect_classifier_digest():
            errors.append("AIML effect classifier digest is not admitted")
        expected = classify_required_effects(
            {
                "session_id": artifact["session_id"],
                "attempt_id": artifact["session_attempt_id"],
                "attempt_phase": artifact["attempt_phase"],
                "path_manifest": artifact["classified_inputs"][
                    "owned_path_manifest"
                ],
                "work_package": artifact["classified_inputs"],
            },
            classified_at=artifact["classified_at"],
        )
        if artifact["required_effects"] != expected["required_effects"]:
            errors.append("AIML required effects differ from classifier output")
    if schema_version == "terminal_receipt_sink_v1":
        expected_contract = terminal_receipt_sink_contract()
        if artifact != expected_contract:
            errors.append(
                "terminal_receipt_sink_v1 must remain the exact S0.3 contract-only declaration"
            )
    if schema_version == "aiml_component_effect_classification_v1":
        # sibling 分類 artifact:重算 required_effects 並比對(拒偽造 required_effects
        # 或不符的 classifier_digest),結構等同 S0.3 分類分支但指向 sibling 分類器。
        if artifact["classification_id"] != _component_effect_class_identity_digest(
            artifact
        ):
            errors.append("AIML component effect classification_id is invalid")
        if artifact["self_digest"] != artifact_self_digest(artifact):
            errors.append("AIML component effect classification self_digest is invalid")
        if artifact["classifier_digest"] != aiml_component_effect_class_matrix_digest():
            errors.append("AIML component effect classifier digest is not admitted")
        if artifact["component_work_package_id"] != artifact["classified_inputs"][
            "component_work_package_id"
        ]:
            errors.append("AIML component classification work-package id is not bound")
        try:
            expected = classify_component_required_effects(
                artifact["classified_inputs"],
                classified_at=artifact["classified_at"],
            )
        except ValueError as error:
            # NONE-block / adapter-substitution / 缺欄位 → fail-closed。
            errors.append(f"AIML component effect classification is not admitted: {error}")
        else:
            if artifact["required_effects"] != expected["required_effects"]:
                errors.append(
                    "AIML component required effects differ from classifier output"
                )
    if schema_version == "aiml_component_effect_classification_v2":
        # S2.4(WP4·W1)v2 sibling 分類 artifact:結構等同 v1 分支但指向 v2 分類器與 v2
        # 矩陣 digest。跨版本互拒為自動性——v1 artifact 帶 v1 digest 而此分支要 v2 digest,
        # 反之亦然;classifier_digest 不符即 fail-closed(下方 negative test 另補顯式反例)。
        if artifact["classification_id"] != _component_effect_class_identity_digest(
            artifact
        ):
            errors.append("AIML component effect v2 classification_id is invalid")
        if artifact["self_digest"] != artifact_self_digest(artifact):
            errors.append("AIML component effect v2 classification self_digest is invalid")
        if artifact["classifier_digest"] != aiml_component_effect_class_matrix_v2_digest():
            errors.append("AIML component effect v2 classifier digest is not admitted")
        if artifact["component_work_package_id"] != artifact["classified_inputs"][
            "component_work_package_id"
        ]:
            errors.append("AIML component v2 classification work-package id is not bound")
        try:
            expected = classify_component_required_effects_v2(
                artifact["classified_inputs"],
                classified_at=artifact["classified_at"],
            )
        except ValueError as error:
            # NONE-block / adapter-substitution / 缺欄位 → fail-closed。
            errors.append(
                f"AIML component effect v2 classification is not admitted: {error}"
            )
        else:
            if artifact["required_effects"] != expected["required_effects"]:
                errors.append(
                    "AIML component v2 required effects differ from classifier output"
                )
    if schema_version == "pg_readonly_identity_receipt_v1":
        # S1.1 central-validator wiring(CC review note D2):委派給 S1.1 validator 並
        # 強制傳 now;只接受 disposable-real/attested receipt,結構手搭的 stub 由 S1.1
        # validator 拒絕(它重算 source/schema sha256、要求 disposable_local、PASS 需真
        # 25006 等 runtime facts)。
        now_text = _now_text(now)
        if now_text is None:
            errors.append(
                "pg_readonly identity receipt requires now for freshness at the central gate"
            )
        else:
            import agent_governance_pg_readonly_identity as _pg_readonly
            errors.extend(
                _pg_readonly.validate_pg_readonly_identity_receipt(
                    artifact, now=now_text
                )
            )
    if schema_version in {
        "terminal_receipt_append_intent_v1",
        "terminal_receipt_append_result_v1",
        "terminal_receipt_readback_ack_v1",
    }:
        # S1.2 WORM sink:委派給 disposable adapter 的 self-validated 結構/整合/新鮮度
        # 檢查(standalone;跨 intent/result/ack 綁定由 adapter 測試以成對 artifact 驗證)。
        # 與 pg_readonly 分支同樣強制 now:陳舊 intent/result/ack 於中央閘 fail-closed。
        now_text = _now_text(now)
        if now_text is None:
            errors.append(
                "terminal receipt WORM artifact requires now for freshness at the central gate"
            )
        else:
            import agent_governance_terminal_receipt_sink as _worm_sink
            if schema_version == "terminal_receipt_append_intent_v1":
                errors.extend(
                    _worm_sink.validate_terminal_receipt_append_intent(
                        artifact, now=now_text
                    )
                )
            elif schema_version == "terminal_receipt_append_result_v1":
                errors.extend(
                    _worm_sink.validate_terminal_receipt_append_result(
                        artifact, now=now_text
                    )
                )
            else:
                errors.extend(
                    _worm_sink.validate_terminal_receipt_readback_ack(
                        artifact, now=now_text
                    )
                )
                # P1-A:standalone(未配對 result)的 POSITIVE 獨立讀回 ACK,中央閘無配對
                # result 可綁定 verifier↔append actor,無法證明其獨立性 → fail-closed 拒絕。
                # 負向 ACK 或自陳 same_actor_violation=true 仍可 standalone 通過。
                if (
                    artifact.get("ack") is True
                    and artifact.get("same_actor_violation") is False
                ):
                    errors.append(
                        "readback ack independence cannot be verified without its "
                        "paired result"
                    )
    if schema_version in {
        "component_effect_intent_v1",
        "component_effect_result_v1",
        "component_effect_postcheck_attestation_v1",
        "effect_seams_ready_receipt_v1",
    }:
        # S1.5 每元件 deploy adapter:委派給 disposable module 的 self-validating 結構/整合/
        # 新鮮度檢查(standalone;跨 intent/result/attestation/rollup 綁定由 module 測試以成對
        # artifact 驗證)。與 pg_readonly / WORM 分支同樣強制 now:陳舊 artifact 於中央閘 fail-closed。
        now_text = _now_text(now)
        if now_text is None:
            errors.append(
                "component effect artifact requires now for freshness at the central gate"
            )
        else:
            import agent_governance_component_effects as _component_effects
            if schema_version == "component_effect_intent_v1":
                errors.extend(
                    _component_effects.validate_component_effect_intent(artifact, now=now_text)
                )
            elif schema_version == "component_effect_result_v1":
                errors.extend(
                    _component_effects.validate_component_effect_result(artifact, now=now_text)
                )
            elif schema_version == "component_effect_postcheck_attestation_v1":
                errors.extend(
                    _component_effects.validate_postcheck_attestation(artifact, now=now_text)
                )
            else:
                errors.extend(
                    _component_effects.validate_effect_seams_ready_receipt(artifact, now=now_text)
                )
    if schema_version in {
        "pg_observer_bootstrap_intent_v1",
        "pg_observer_bootstrap_result_v1",
        "pg_observer_bootstrap_postcheck_v1",
        "pg_observer_bootstrap_rollback_v1",
    }:
        # S2.0(WP2)生產唯讀 PG observer-bootstrap SOURCE adapter:委派給 SSOT module 的自驗
        # 結構/整合/新鮮度檢查(standalone;跨 intent/result/postcheck/rollback 綁定由 module 測試
        # 以成對 artifact 驗證)。與 pg_readonly / WORM / component-effect 分支同樣強制 now:陳舊
        # artifact 於中央閘 fail-closed。
        #
        # ⚠ SOURCE-TRUTH 邊界(S2.0 EFFECT session 消費者請注意):此委派只證 receipt 的「內部自洽
        # + 結構 + 離線 SSHSIG 結構」(offline-structure 模式);validate_aiml_artifact 通過「不」等於
        # 證明真對生產 PG apply 過。production apply 現為 reachable 但 authority-locked:source/Mac/test
        # lane(driver=None)恆回 EXTERNAL_VERIFICATION_PENDING 零 mutation;真 APPLIED 僅由 S2.0 EFFECT
        # session 的真 host driver + platform-attested 證據簽發,且需 out-of-band 信任主機驗證(離線通過
        # 仍「不」證明真 apply 過)。
        now_text = _now_text(now)
        if now_text is None:
            errors.append(
                "observer bootstrap artifact requires now for freshness at the central gate"
            )
        else:
            import agent_governance_pg_observer_bootstrap as _observer
            if schema_version == "pg_observer_bootstrap_intent_v1":
                errors.extend(_observer.validate_pg_observer_bootstrap_intent(artifact, now=now_text))
            elif schema_version == "pg_observer_bootstrap_result_v1":
                errors.extend(_observer.validate_pg_observer_bootstrap_result(artifact, now=now_text))
            elif schema_version == "pg_observer_bootstrap_postcheck_v1":
                errors.extend(_observer.validate_pg_observer_bootstrap_postcheck(artifact, now=now_text))
            else:
                errors.extend(_observer.validate_pg_observer_bootstrap_rollback(artifact, now=now_text))
    if schema_version in {
        "quiesce_intent_v1",
        "quiesce_observation_v1",
        "quiesce_result_v1",
        "quiesce_rollback_v1",
    }:
        # S2.1(WP3)ALR quiesce fence SOURCE adapter:委派給 SSOT module 的自驗結構/整合/新鮮度檢查
        # (standalone;跨 intent/observation/result/rollback 綁定由 module 測試以成對 artifact 驗證)。
        # 與 pg_observer / component-effect 分支同樣強制 now:陳舊 artifact 於中央閘 fail-closed。
        #
        # ⚠ SOURCE-TRUTH 邊界(S2.1 EFFECT session 消費者請注意):此委派只證 receipt 的「內部自洽 +
        # 結構 + 離線 SSHSIG 結構」;validate_aiml_artifact 通過「不」等於證明真對 live ALR 施加過 fence——
        # production/live fence 恆為 EXTERNAL_VERIFICATION_PENDING(fail-closed)直到 S2.0@EFFECT_DONE 與一張
        # platform-attested 的 out-of-band operator SSHSIG 存在,且 EFFECT fence 排在 S2.4/S2.5 之後。
        now_text = _now_text(now)
        if now_text is None:
            errors.append(
                "quiesce artifact requires now for freshness at the central gate"
            )
        else:
            import agent_governance_alr_quiesce_fence as _quiesce
            if schema_version == "quiesce_intent_v1":
                errors.extend(_quiesce.validate_quiesce_fence_intent(artifact, now=now_text))
            elif schema_version == "quiesce_observation_v1":
                errors.extend(_quiesce.validate_quiesce_observation(artifact, now=now_text))
            elif schema_version == "quiesce_result_v1":
                errors.extend(_quiesce.validate_quiesce_fence_result(artifact, now=now_text))
            else:
                errors.extend(_quiesce.validate_quiesce_rollback(artifact, now=now_text))
    if schema_version == "learning_runtime_choice_receipt_target_host_v1":
        # S1 formal-closure Wave A(S1.6B):把 target-host 選擇 receipt 加入中央 SCHEMA_FILES 委派
        # 登記,但中央離線閘只做「結構/整合/新鮮度」驗(require_target_host_attested=False)——CLAUDE.md
        # 明言 standalone CLI 無法認證 PASS。真「已背書」閘(EMBEDDED governed command_capture_v2)由
        # closure/trusted-host lane 以 require_target_host_attested=True 執行(見 target-host effect
        # sibling)。與 pg_readonly / WORM / component-effect 分支同樣強制 now:陳舊 receipt 於中央閘 fail-closed。
        now_text = _now_text(now)
        if now_text is None:
            errors.append(
                "target-host choice receipt requires now for freshness at the central gate"
            )
        else:
            import agent_governance_target_host_choice as _th_choice
            errors.extend(_th_choice.validate_target_host_choice_receipt(
                artifact, now=now_text, require_target_host_attested=False
            ))
    if schema_version == "target_host_effect_result_v1":
        # S1.6B 專屬 effect result(§13 C1):委派給 sibling module,對內嵌 choice receipt 以
        # require_target_host_attested=True 嚴格驗(§13 C4——這條 lane 的嚴格 attestation 是唯一
        # 真實執法)。中央閘無 closure baseline,故不傳 expected_source_head(結構+嵌入嚴格驗)。
        now_text = _now_text(now)
        if now_text is None:
            errors.append(
                "target-host effect result requires now for freshness at the central gate"
            )
        else:
            import agent_governance_target_host_effects as _th_effects
            errors.extend(_th_effects.validate_target_host_effect_result(
                artifact, now=now_text
            ))
    if schema_version == "target_host_disposable_runtime_probe_intent_v1":
        # S1.6B typed intent 為離線結構授權(SCHEMA_FILES 委派)。schema 無法比較兩欄位,故此處補上
        # schema description 已載明的 applier != independent verifier 不變量:applier_node_id 必須不同於
        # postcheck_node_id。其餘結構(const/pattern/enum/ttl 上限等)由上方 schema_subset_errors 強制。
        if artifact["applier_node_id"] == artifact["postcheck_node_id"]:
            errors.append(
                "target-host probe intent applier_node_id must differ from postcheck_node_id"
            )
    if schema_version == "github_repository_policy_attestation_v1":
        errors.extend(_github_policy_attestation_errors(artifact, now=now))
    if schema_version == "program_adoption_receipt_v1":
        errors.extend(_program_adoption_receipt_errors(artifact))
    if schema_version == "source_compatibility_receipt_v1":
        errors.extend(_source_compatibility_receipt_errors(artifact))
    if schema_version == "s2e_launch_genesis_receipt_v1":
        errors.extend(validate_s2e_launch_genesis_receipt(artifact, repo_root=REPO_ROOT))
    if schema_version == "s2e_launch_wave_receipt_v1":
        errors.extend(validate_s2e_launch_wave_receipt(artifact, repo_root=REPO_ROOT))
    if schema_version == "receipt_carrier_attestation_v1":
        errors.extend(validate_receipt_carrier_attestation(
            artifact, payload_receipt=None, repo_root=REPO_ROOT, now=now
        ))
    if schema_version in {"sealed_build_receipt_v1", "expected_identity_receipt_v1"}:
        # S2.3(LR2)sealed-build / expected-identity 是 BUILD-IDENTITY / source 產物
        # (content-addressed、可重算、production_running_attested=false、observation_owner=
        # S2.5_LR6)——與 source_compatibility receipt 同類、非 effect-class。故中央閘只做離線
        # 結構/整合/const-false/S1.3·S1.4 ground-truth 身分綁定/self_digest 委派驗,「刻意不施加
        # wall-clock 新鮮度窗」:committed build 證據帶固定 30-min TTL,若以真牆鐘 now 判窗會過期成
        # time-bomb,任何以 wall-clock now 呼叫中央閘的 closure/CI/S2.4 消費者都會誤拒 committed 證據。
        # 真正的 recency 證明留在既有綠燈 `learning-runtime-sealed-build` CI job。故傳 now=None
        # (mirror S2.3 CLI + offline 測試對這兩類 receipt 的既有處置);SSOT 內部仍驗 ttl 範圍與
        # observed<expires 等結構性時間不變量,只是不做 wall-clock 窗判。亦刻意不傳 lock_path 與配對
        # sealed(不重跑 lock 封閉 re-derivation、不做 F2c 配對):同屬 CI job 的 offline-install 證明。
        #
        # ⚠ SOURCE-TRUTH 邊界(WP4/WP5 消費者請注意):此委派(及下方 source_compatibility_receipt_v2
        # 分支)只證 receipt 的「內部自洽 + 結構」(offline-structure 模式);validate_aiml_artifact
        # 通過「不」等於證明 receipt 與真 repo/真 lock 相符。build-identity receipt 的 source-truth
        # 綁定在別處:(i) launcher 端的 recompute-from-checkout(alr_event_consumer.
        # try_build_learning_runtime_manifest_v2)+ operator pin,與 (ii) `learning-runtime-sealed-build`
        # CI job 內 verify_lock_closure(lock_path=) 對真 lock 的 re-derivation。
        import agent_governance_sealed_build as _sealed_build
        if schema_version == "sealed_build_receipt_v1":
            errors.extend(
                _sealed_build.validate_sealed_build_receipt(artifact, now=None)
            )
        else:
            errors.extend(
                _sealed_build.validate_expected_identity_receipt(artifact, now=None)
            )
    if schema_version == "source_compatibility_receipt_v2":
        # v2 沿用「版本無關」的內層反偽造重算:_source_compatibility_receipt_errors 由 manifest
        # 自身 schema_version 驅動 self_digest 重算,且 training_contract.digest 綁定整個
        # components(含 dependency_lock 物件)→ 偽造內層 dependency_lock 而只重封外層 self_digest
        # 必被抓。另補 v2 專屬 dependency_lock 物件形狀檢查(spec/lock 兩子 digest)。
        # ⚠ 同上 SOURCE-TRUTH 邊界:此為 internal-consistency + structure 驗,非 source-truth——
        # dependency_lock 的 spec/lock 子 digest 是內嵌值,離線閘無法重算真檔;真檔綁定在 launcher
        # recompute-from-checkout 與 sealed-build CI job 的 verify_lock_closure。
        errors.extend(_source_compatibility_receipt_errors(artifact))
        errors.extend(_source_compatibility_receipt_v2_dependency_lock_errors(artifact))
    if schema_version == "s2_4_source_admission_receipt_v1":
        # S2.4(WP4·W0)source-admission:closed schema 已禁 caller status;此處委派給
        # derive_source_admission_status 由 repo 完整再導出(source-seam 自足)。非 ADMITTED →
        # 把 typed reasons 併入 errors。此再導出只證 source-seam 完整性,「不」認證任何 runtime。
        result = derive_source_admission_status(artifact, repo_root=REPO_ROOT, now=now)
        if result["status"] != "ADMITTED":
            errors.extend(result["reasons"])
    if schema_version == "s2_4_wave_exit_receipt_v1":
        # S2.4(WP4·W0)wave-exit:此中央閘分支為 STRUCTURAL-ONLY——無綁定 admission 對象,故只驗
        # 「自足」再導出(caller-status 拒 + self_digest + flags + W0 的 ABI/owned-path/predecessor-null),
        # 「不」驗 source_admission_receipt_digest 是否綁到一份真能再導出 ADMITTED 的 admission。
        # ⚠ 乾淨的 [] 結果「不」等於 W0 PASS:帶 bogus source_admission_receipt_digest 的 wave-exit
        # 仍會回 []。完整 PASS 必須由 derive_wave_exit_status(source_admission_receipt=<已導 ADMITTED>)
        # 授予——mirror CLAUDE.md standalone-CLI / typed-authority 邊界(離線結構驗無法自證 PASS)。
        declared = sorted(key for key in _CALLER_STATUS_KEYS if key in artifact)
        if declared:
            errors.append(
                "wave-exit receipt must not self-declare status "
                f"({', '.join(declared)}); the central validator derives PASS"
            )
        else:
            errors.extend(_wave_exit_structural_errors(artifact))
    if schema_version == "s2_4_capability_probe_intent_v1":
        # S2.4(WP4·W1·CP3)§5.1 re-derivation:probe 是 route-class 載體,攜帶 unsigned probe core
        # → 中央閘再導出 core_digest / probe_id('s2-4-probe-'+hex(core_digest)) / self_digest。
        errors.extend(_s2_4_route_core_rederivation_errors(
            artifact, id_field="probe_id", id_prefix="s2-4-probe-"
        ))
    if schema_version == "s2_4_prepare_intent_v1":
        # 同上:prepare core → prepare_id = 's2-4-prepare-'+hex(core_digest)。
        errors.extend(_s2_4_route_core_rederivation_errors(
            artifact, id_field="prepare_id", id_prefix="s2-4-prepare-"
        ))
    if schema_version == "s2_4_install_plan_v1":
        # §5.1 re-derivation:aggregate plan 攜帶 unsigned plan core → plan_id = 's2-4-'+hex(core_digest)
        # 且 idempotency_key=plan_id(idempotency_key 在 plan 物件、非簽名 core;core 由 schema 排除)。
        # 另補 five APPLY row 的 exact 次序驗(JSON schema 無 prefixItems 無法表達)。
        errors.extend(_s2_4_route_core_rederivation_errors(
            artifact, id_field="plan_id", id_prefix="s2-4-"
        ))
        if artifact.get("idempotency_key") != artifact.get("plan_id"):
            errors.append("install plan idempotency_key must equal plan_id")
        core = artifact.get("core")
        if isinstance(core, dict) and (
            "plan_id" in core or "idempotency_key" in core
        ):
            errors.append(
                "install plan signed core must not carry plan_id/idempotency_key "
                "(derived ids live on the plan object)"
            )
        errors.extend(_s2_4_install_plan_apply_rows_errors(artifact))
    if schema_version == "s2_4_component_effect_intent_v1":
        # S2.4(WP4·W1·CP3)per-row ABI 綁定:closed schema(CP2b)之上,再導出 §4 逐行 ABI 綁定並
        # 強制 required_intent_fields 恰等於凍結矩陣列(關閉 schema 允許跨類夾帶額外 digest 鍵的縫,
        # 例如一份 PG intent 夾帶 host-identity 的 uid_gid_directory_manifest_digest)。
        if artifact["self_digest"] != artifact_self_digest(artifact):
            errors.append("component effect intent self_digest is invalid")
        try:
            derive_component_intent_binding(artifact)
        except ValueError as error:
            errors.append(f"component effect intent binding is not admitted: {error}")
    if schema_version == "s2_4_install_effect_receipt_v1":
        # S2.4(WP4·W1·CP3)aggregate-lineage:closed schema(CP2b)之上,再導出離線結構 lineage
        # (五 APPLY row exact 次序+unique、兩 scoped probe digest 相異、PREPARE 結果/postcheck、
        # 逆向補償鏈)。此為結構驗,「不」斷言 runtime PASS。self_digest 完整性另驗。
        if artifact["self_digest"] != artifact_self_digest(artifact):
            errors.append("install effect receipt self_digest is invalid")
        lineage = derive_install_lineage_status(artifact)
        if lineage["status"] != "SATISFIED":
            errors.extend(lineage["reasons"])
    if schema_version == "pg_acl_manifest_v1":
        # S2.4(WP4·W2a·§2.1)closed PG ACL manifest:closed schema(privilege 全面 enum 封閉)
        # 之上,再驗 self_digest 反偽造重算與 canonical 排序(schemas/tables/functions 按 name、
        # privileges 按字典序——排序唯一化令 manifest bytes 與 canonical digest 一一對應)。
        # ⚠ 乾淨的 [] 「不」等於 privilege-split PASS:與 post-split consumer 靜態 SQL inventory
        # 的雙向 exact-match 由 agent_governance_s2_4_install.derive_engine_scanner_privilege_split
        # 導出(unlisted statement 或 over-grant 皆 fail);中央閘此分支只證結構/完整性。
        if artifact["self_digest"] != artifact_self_digest(artifact):
            errors.append("pg acl manifest self_digest is invalid")
        for section in ("schemas", "tables", "functions"):
            names = [entry["name"] for entry in artifact[section]]
            if names != sorted(names) or len(names) != len(set(names)):
                errors.append(
                    f"pg acl manifest {section} must be sorted by name and unique"
                )
            if any(
                entry["privileges"] != sorted(set(entry["privileges"]))
                for entry in artifact[section]
            ):
                errors.append(
                    f"pg acl manifest {section} privileges must be sorted and unique"
                )
    if schema_version == "application_bundle_runtime_closure_v1":
        # S2.4(WP4·W2b·§8.1)checked-in runtime-closure allowlist:closed schema 之上,再驗
        # self_digest 反偽造重算與每個路徑段的 canonical 排序唯一化(bytes↔digest 一一對應)。
        # ⚠ 乾淨的 [] 「不」等於 closure PASS:與靜態 runtime import 閉包的雙向 exact-match、
        # effect-capable/broker/credential deny、SSOT 常量同步(learning_runtime_manifest/
        # SCHEMA_FILES)由 agent_governance_s2_4_install.derive_application_runtime_closure_status
        # 導出;中央閘此分支只證結構/完整性。
        if artifact["self_digest"] != artifact_self_digest(artifact):
            errors.append("application runtime closure self_digest is invalid")
        for section in (
            "python_modules",
            "package_init_files",
            "compatibility_receipts",
            "learning_runtime_inputs",
            "sql_fingerprints",
            "dependency_lock_files",
            "schema_resources",
        ):
            if artifact[section] != sorted(set(artifact[section])):
                errors.append(
                    f"application runtime closure {section} must be sorted and unique"
                )
    if schema_version == "application_bundle_manifest_v1":
        # S2.4(WP4·W2b·§8.1 #3)application_bundle_manifest:closed schema 之上,再驗
        # self_digest(== application_bundle_digest)反偽造重算與 entries 依 path 排序唯一。
        # ⚠ 乾淨的 [] 只證結構/完整性,「不」證 manifest 出自 committed blobs 或與某棵真樹
        # 相符——builder 溯源屬 agent_governance_s2_4_install.build_application_bundle_manifest,
        # runtime 整樹重算屬 ml_training.alr_application_identity.verify_application_root。
        if artifact["self_digest"] != artifact_self_digest(artifact):
            errors.append("application bundle manifest self_digest is invalid")
        entry_paths = [entry["path"] for entry in artifact["entries"]]
        if entry_paths != sorted(entry_paths) or len(entry_paths) != len(set(entry_paths)):
            errors.append(
                "application bundle manifest entries must be sorted by path and unique"
            )
    if schema_version in ("base_runtime_tree_manifest_v1", "launch_bundle_manifest_v1"):
        # S2.4(WP4·W2c·§8.1 #2/#4):closed schema 之上,再驗 self_digest 反偽造重算與
        # canonical 排序/file↔digest 一致(委派 wave_w2 葉)。⚠ 乾淨的 [] 只證結構/完整性,
        # 「不」證 manifest 與某棵真樹相符——樹走訪/builder 屬 agent_governance_s2_4_render。
        errors.extend(w2_manifest_artifact_errors(schema_version, artifact))
    if schema_version == S2_4_OPERATOR_AUTHORIZATION_SCHEMA_VERSION:
        # S2.4(WP4·W1·CP4)§9.1 四 trust profile:closed schema(CP2b)之上,再驗 profile 解析、
        # payload_fields == 該 profile 的 §9.1 ordered list、namespace/identity 綁定、armored SSHSIG
        # strict-base64/≤16 KiB、TTL≤profile 上限(now 若提供再驗 skew 新鮮度)、以及**信任根綁定**——
        # 呼叫 out-of-scope trusted-host 的 _verify_ssh_signature 對 pinned 公鑰做離線公鑰驗簽。此為離線
        # 結構/完整性/信任根綁定驗;「不」斷言 runtime 真偽(真 operator 對真語義 payload 的 runtime 簽署
        # + replay-ledger 消費 + 平台背書屬 W6A/W6B EFFECT)。
        # 註(W1):s2_4_authorization_replay_ledger_v1 的中央閘分支維持 CP2b 的 closed-schema
        # 驗(佔位 fixture 契約);逐 entry hash-chain 重算 + 消費語義(unconsumed/consuming-twice/
        # same-id-different-plan)由 facade-reachable 的 derive_authorization_replay_binding /
        # _s2_4_replay_ledger_errors 執法——消費是「授權↔ledger」裁決,非裸 ledger 結構。
        errors.extend(_s2_4_operator_authorization_errors(artifact, now=now))
    if schema_version == S2_4_DEPENDENCY_REFRESH_SCHEMA_VERSION:
        # S2.4(WP4·W5·§9.2)dependency refresh:closed schema 之上只作**自足**驗(caller-status
        # 拒 + self_digest + 封閉族表 + 復現值不得是原 digest 的複述 + producer 投影相異)——中央閘
        # 手上沒有原 receipt 物件。⚠ 乾淨的 [] 「不」等於 ADMITTED:真裁決恆由
        # derive_dependency_refresh_status(original_receipt=<原 receipt>) 於當前 head 重算後授予
        # (鏡 wave-exit 分支的同一條誠實界線)。
        declared = sorted(key for key in _CALLER_STATUS_KEYS if key in artifact)
        if declared:
            errors.append(
                "dependency refresh attestation must not self-declare status "
                f"({', '.join(declared)}); the central validator derives it"
            )
        else:
            errors.extend(_dependency_refresh_structural_errors(artifact))
    if schema_version == "aiml_component_effect_classification_v3" or (
        schema_version.startswith("s2_5_")
    ):
        # S2.5(WP5)委派葉:v3 分類重算 + 五個 s2_5 schema 的整合/新鮮度/attestor 驗簽面。
        # SOURCE-TRUTH 邊界與 never-refreshable 表在葉內(乾淨 [] 不證任何 runtime)。
        import aiml_gate_receipt_s2_5 as _s2_5_leaf
        errors.extend(_s2_5_leaf.validate_s2_5_artifact(artifact, now=now))
    if schema_version == "ingestion_compatibility_receipt_v1":
        # S2.2B(WP5 tranche 2)委派葉:S2.2A 三值鏈重算 + s2_5_final_attestation 全套
        # 重驗(含 attestor 驗簽)+ V151-V160 逐項 revalidation。乾淨 [] 不證任何 runtime。
        import aiml_gate_receipt_s2_2b as _s2_2b_leaf
        errors.extend(_s2_2b_leaf.validate_s2_2b_artifact(artifact, now=now))
    return errors
