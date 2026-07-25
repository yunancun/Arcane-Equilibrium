"""S2.4(WP4·W2b·§8.1/§8.3)application-bundle 身分與 production 前置驗證的 runtime 葉模組。

本模組是「隨 bundle 出貨」的 runtime 面(它自身在 runtime-closure allowlist 內):

- 定義 application_bundle_manifest_v1 的 canonical 文件形狀(builder 與 runtime 共用,
  兩側不可能分歧——§8.1 第 3 身分 application_bundle_digest 的唯一構造點);
- 從不可變 application root「整樹重算」bundle digest 並與 operator 期望硬比對
  (缺檔/多檔/改檔/symlink/mode 漂移全部 typed fail-closed);
- production 前置(§8.3 consumer ABI):--application-root 是 v1/v2 receipt 與相容性
  重算的唯一根;module-relative 預設與 Git 在 production 模式一律禁止;任何 permanent
  config/identity 失敗以 exit 78 收場(EX_CONFIG_EXIT_CODE);
- 缺失/不符的期望「絕不」回退到 ambient/Git/module-relative 來源。

硬邊界:source-only、零 DB、零網路、零 effect;九 authority 恆 false。本模組驗證通過
「不」認證任何 runtime/production 狀態——它只是 pre-DB 的 fail-closed 身分閘。
facade 依 2000 行治理拆分規約「只」經 schema_core.resolve_facade() 取得。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any, Mapping

from ml_training.aiml_gate_receipt_schema_core import resolve_facade
from ml_training.learning_runtime_manifest import (
    try_build_learning_runtime_manifest_v2,
)

# ── §8.1/§8.3 契約常量(builder 與 runtime 共用;W3+ 的 launch-tree 渲染器必須遵守) ──
APPLICATION_ENTRYPOINT = "ml_training.alr_event_consumer"
BUNDLE_LAYOUT_VERSION = "aiml_app_bundle_layout_v1"
MANIFEST_SCHEMA_VERSION = "application_bundle_manifest_v1"
CLOSURE_SCHEMA_VERSION = "application_bundle_runtime_closure_v1"
# checked-in、可審查的 runtime-closure allowlist(§8.1:manifest 由它產出;它自身入 bundle)。
RUNTIME_CLOSURE_REL = (
    "program_code/ml_training/application_bundle_runtime_closure_v1.json"
)
# §8.3:permanent pre-DB configuration/identity/credential-format 失敗一律 exit 78。
EX_CONFIG_EXIT_CODE = 78
# bundle 內僅允許兩種不可變 mode(§8.1:data 0444 / 可執行 0555)。
_BUNDLE_ENTRY_MODES = ("0444", "0555")
# §8.3:consumer 僅有的外部 application-data 讀取面(digest-bound 進 manifest)。
REQUIRED_RUNTIME_RESOURCES = {
    "dsn_credential_name": "pg-dsn",
    "candidate_policy_file": (
        "/etc/arcane-equilibrium/aiml/engine-scanner/candidate-policy.json"
    ),
    "topology_guard_file": (
        "/etc/arcane-equilibrium/aiml/engine-scanner/topology-runtime-guard.json"
    ),
    "candidate_evidence_directory": (
        "/var/lib/arcane-equilibrium/aiml/engine-scanner/candidate-evidence"
    ),
}
# §8.2/§8.3:production DSN 必須綁 S2.3 正確身分(aiml_engine_scanner,非 alr_shadow)。
PRODUCTION_DSN_IDENTITY = {
    "host": "127.0.0.1",
    "port": "5432",
    "dbname": "trading_ai",
    "user": "aiml_engine_scanner",
}
# in-repo pinned 相容性 receipt 的 bundle 內相對路徑(mirror alr_event_consumer 的
# _DEFAULT_COMPATIBILITY_RECEIPT[_V2]_REL;此處以 application root 為唯一根解析)。
COMPATIBILITY_RECEIPT_V1_REL = (
    "docs/execution_plan/ai_ml_landing/receipts/"
    "S2.2A-source-compatibility-receipt-v1.json"
)
COMPATIBILITY_RECEIPT_V2_REL = (
    "docs/execution_plan/ai_ml_landing/receipts/"
    "S2.2A-source-compatibility-receipt-v2.json"
)

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_HEAD_RE = re.compile(r"^[0-9a-f]{40}$")
# closure allowlist 中承載 repo 相對路徑的段名(closed schema 同步凍結此形狀)。
CLOSURE_PATH_SECTIONS = (
    "python_modules",
    "package_init_files",
    "compatibility_receipts",
    "learning_runtime_inputs",
    "sql_fingerprints",
    "dependency_lock_files",
    "schema_resources",
)
_CLOSURE_MAX_BYTES = 1_048_576


class AlrApplicationIdentityError(Exception):
    """typed、permanent 的 pre-DB 身分/組態失敗(production 模式 → exit 78)。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _read_bounded_json(path: Path, *, code_prefix: str, max_bytes: int) -> dict[str, Any]:
    """symlink/非常規檔/超大/畸形 JSON 一律 typed fail-closed 讀取。"""
    if path.is_symlink():
        raise AlrApplicationIdentityError(f"{code_prefix}_symlink")
    try:
        st = os.lstat(path)
    except OSError as exc:
        raise AlrApplicationIdentityError(f"{code_prefix}_missing") from exc
    if not stat.S_ISREG(st.st_mode):
        raise AlrApplicationIdentityError(f"{code_prefix}_not_regular")
    if st.st_size > max_bytes:
        raise AlrApplicationIdentityError(f"{code_prefix}_too_large")
    if st.st_mode & 0o002:
        raise AlrApplicationIdentityError(f"{code_prefix}_world_writable")
    try:
        loaded = json.loads(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise AlrApplicationIdentityError(f"{code_prefix}_unreadable") from exc
    if not isinstance(loaded, dict):
        raise AlrApplicationIdentityError(f"{code_prefix}_not_object")
    return loaded


def load_runtime_closure(path: Path) -> dict[str, Any]:
    """讀取 checked-in runtime-closure allowlist 並過中央閘(closed schema+self_digest)。"""
    closure = _read_bounded_json(
        path, code_prefix="runtime_closure", max_bytes=_CLOSURE_MAX_BYTES
    )
    if closure.get("schema_version") != CLOSURE_SCHEMA_VERSION:
        raise AlrApplicationIdentityError("runtime_closure_schema_invalid")
    if resolve_facade().validate_aiml_artifact(closure):
        raise AlrApplicationIdentityError("runtime_closure_rejected")
    return closure


def closure_declared_paths(closure: Mapping[str, Any]) -> list[str]:
    """allowlist 全段 union + policy template + allowlist 自身 → 已宣告 bundle 路徑集。"""
    declared: set[str] = {RUNTIME_CLOSURE_REL, closure["policy_template"]}
    for section in CLOSURE_PATH_SECTIONS:
        declared.update(closure[section])
    return sorted(declared)


def build_application_bundle_document(
    *,
    source_head: str,
    learning_runtime_digest_v2: str,
    runtime_closure_digest: str,
    entries: list[dict[str, str]],
) -> dict[str, Any]:
    """§8.1 #3 唯一構造點:application_bundle_manifest_v1(digest == self_digest)。"""
    facade = resolve_facade()
    document: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "program_id": "AIML-LONG-LIVED-LANDING-V2",
        "component": "engine_scanner",
        "bundle_layout_version": BUNDLE_LAYOUT_VERSION,
        "entrypoint": APPLICATION_ENTRYPOINT,
        "source_head": source_head,
        "learning_runtime_digest_v2": learning_runtime_digest_v2,
        "runtime_closure_digest": runtime_closure_digest,
        "required_runtime_resources": dict(REQUIRED_RUNTIME_RESOURCES),
        "entries": sorted(entries, key=lambda entry: entry["path"]),
    }
    document["self_digest"] = facade.artifact_self_digest(document)
    return document


def _entry_mode(mode_bits: int) -> str:
    return format(mode_bits & 0o7777, "04o")


def derive_tree_entries(root: Path, declared_paths: list[str]) -> list[dict[str, str]]:
    """對每個已宣告路徑做不可變樹檢查後取 {path, mode, sha256}(typed fail-closed)。"""
    entries: list[dict[str, str]] = []
    for rel in declared_paths:
        path = root / rel
        if path.is_symlink():
            raise AlrApplicationIdentityError(f"bundle_entry_symlink:{rel}")
        try:
            st = os.lstat(path)
        except OSError as exc:
            raise AlrApplicationIdentityError(f"bundle_entry_missing:{rel}") from exc
        if not stat.S_ISREG(st.st_mode):
            raise AlrApplicationIdentityError(f"bundle_entry_not_regular:{rel}")
        mode = _entry_mode(st.st_mode)
        if mode not in _BUNDLE_ENTRY_MODES:
            raise AlrApplicationIdentityError(f"bundle_entry_mode_invalid:{rel}:{mode}")
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise AlrApplicationIdentityError(f"bundle_entry_unreadable:{rel}") from exc
        entries.append({
            "path": rel,
            "mode": mode,
            "sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
        })
    return entries


def find_undeclared_paths(root: Path, declared_paths: list[str]) -> list[str]:
    """整樹走訪:未宣告的常規檔即 undeclared;任何 symlink 一律入列(fail-closed)。"""
    declared = set(declared_paths)
    undeclared: list[str] = []
    for current, dirnames, filenames in os.walk(root):
        current_path = Path(current)
        for name in sorted(dirnames):
            if (current_path / name).is_symlink():
                undeclared.append(
                    "symlink:" + str((current_path / name).relative_to(root))
                )
        for name in sorted(filenames):
            child = current_path / name
            rel = str(child.relative_to(root))
            if child.is_symlink():
                undeclared.append("symlink:" + rel)
            elif rel not in declared:
                undeclared.append(rel)
    return sorted(undeclared)


def recompute_application_bundle_digest(
    root: Path, *, source_head: str
) -> tuple[str, dict[str, Any]]:
    """從 application root「整樹」獨立重算 §8.1 #3 digest(不信任任何內嵌 manifest)。

    重算鏈:tree 內的 checked-in allowlist(過中央閘)→ 宣告路徑逐檔 hash + mode →
    以 root 為唯一根、以 pinned head 重算 learning_runtime_manifest_v2(零 Git)→
    canonical 文件 → self_digest。undeclared 檔/symlink 即 typed 拒絕。
    """
    if not _HEAD_RE.fullmatch(str(source_head)):
        raise AlrApplicationIdentityError("source_head_invalid")
    closure = load_runtime_closure(root / RUNTIME_CLOSURE_REL)
    declared = closure_declared_paths(closure)
    undeclared = find_undeclared_paths(root, declared)
    if undeclared:
        raise AlrApplicationIdentityError(
            "bundle_undeclared_paths:" + ",".join(undeclared[:8])
        )
    entries = derive_tree_entries(root, declared)
    v2_manifest, v2_errors = try_build_learning_runtime_manifest_v2(
        root, repo_source_head=source_head
    )
    if v2_manifest is None:
        raise AlrApplicationIdentityError(
            "learning_runtime_v2_unbuildable:" + ",".join(v2_errors)
        )
    document = build_application_bundle_document(
        source_head=source_head,
        learning_runtime_digest_v2=v2_manifest["self_digest"],
        runtime_closure_digest=resolve_facade().artifact_self_digest(closure),
        entries=entries,
    )
    return document["self_digest"], document


def verify_application_root(
    root: Path, *, source_head: str, expected_application_bundle_digest: str
) -> dict[str, Any]:
    """整樹重算後與 operator 期望硬比對;不符即 typed 拒絕(絕不回退)。"""
    if not _DIGEST_RE.fullmatch(str(expected_application_bundle_digest)):
        raise AlrApplicationIdentityError("expected_application_bundle_digest_invalid")
    digest, document = recompute_application_bundle_digest(
        root, source_head=source_head
    )
    if digest != expected_application_bundle_digest:
        raise AlrApplicationIdentityError("application_bundle_digest_mismatch")
    return document


def _contained_path(root: Path, candidate: Path, *, code: str) -> Path:
    """production 模式:receipt 路徑必須落在 application root 之內(唯一根)。"""
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise AlrApplicationIdentityError(code) from exc
    return resolved


def verify_pinned_v2_receipt(
    root: Path,
    receipt_path: Path,
    *,
    source_head: str,
    expected_learning_runtime_digest_v2: str,
) -> str:
    """v2 receipt 驗證(production):中央閘 + 以 root 重算 v2 身分 + operator pin 硬比對。

    mirror ``alr_event_consumer.resolve_pinned_learning_runtime_digest`` 的 fail-closed
    語義,但唯一根是 application root,且「不可」回退 module-relative 預設或 Git。
    """
    receipt = _read_bounded_json(
        receipt_path, code_prefix="compatibility_receipt_v2", max_bytes=_CLOSURE_MAX_BYTES
    )
    if receipt.get("schema_version") != "source_compatibility_receipt_v2":
        raise AlrApplicationIdentityError("compatibility_receipt_v2_schema_invalid")
    if resolve_facade().validate_aiml_artifact(receipt):
        raise AlrApplicationIdentityError("compatibility_receipt_v2_rejected")
    pinned = receipt.get("learning_runtime_digest")
    manifest, _errors = try_build_learning_runtime_manifest_v2(
        root, repo_source_head=source_head
    )
    if manifest is None or manifest.get("self_digest") != pinned:
        raise AlrApplicationIdentityError("compatibility_receipt_v2_recompute_mismatch")
    if pinned != expected_learning_runtime_digest_v2:
        raise AlrApplicationIdentityError("learning_runtime_digest_v2_pin_mismatch")
    return str(pinned)


def verify_topology_guard(path: Path) -> dict[str, Any]:
    """載入不可變 topology guard 並自我 digest 驗證(§8.3;結構由 closed schema 執法)。"""
    guard = _read_bounded_json(
        path, code_prefix="topology_guard", max_bytes=_CLOSURE_MAX_BYTES
    )
    if guard.get("schema_version") != "pg_topology_runtime_guard_v1":
        raise AlrApplicationIdentityError("topology_guard_schema_invalid")
    facade = resolve_facade()
    if facade.validate_aiml_artifact(guard):
        raise AlrApplicationIdentityError("topology_guard_rejected")
    if guard.get("self_digest") != facade.artifact_self_digest(guard):
        raise AlrApplicationIdentityError("topology_guard_self_digest_mismatch")
    return guard


def verify_launch_prefix(
    expected_launch_bundle_digest: str, *, interpreter_prefix: str | None = None
) -> str:
    """launch 身分消費:sys.prefix 葉名必須等於 launch digest 的 64-hex(§8.1 launches/<digest>)。

    W3+ 的 launch-tree 渲染器據此契約以 digest 的 64-hex 作葉目錄名(digest 內含 ':',
    不入路徑)。dev/test 經 interpreter_prefix 注入;production 用真 sys.prefix。
    """
    if not _DIGEST_RE.fullmatch(str(expected_launch_bundle_digest)):
        raise AlrApplicationIdentityError("expected_launch_bundle_digest_invalid")
    prefix = interpreter_prefix if interpreter_prefix is not None else sys.prefix
    expected_leaf = expected_launch_bundle_digest.split(":", 1)[1]
    if Path(prefix).name != expected_leaf:
        raise AlrApplicationIdentityError("launch_prefix_mismatch")
    return expected_leaf


def run_production_preflight(
    *,
    application_root: Path,
    source_head: Any,
    expected_compatibility_receipt_v2: Path | None,
    expected_application_bundle_digest: Any,
    expected_launch_bundle_digest: Any,
    topology_guard_file: Path | None,
    expected_learning_runtime_digest_v2: Any,
    expected_compatibility_receipt: Path | None = None,
    interpreter_prefix: str | None = None,
) -> dict[str, Any]:
    """§8.3 production 前置(pre-DB、fail-closed):全部期望必須顯式提供且硬比對通過。

    回傳的 ``run_kwargs`` 供 consumer 以 application root 為唯一根執行(pinned head、
    engine-scanner DSN 身分、root-scoped v1 receipt);``source_value_guard`` 供結果輸出。
    任何缺失/不符 → AlrApplicationIdentityError(exit 78),絕不回退 ambient/Git 來源。
    """
    root = Path(application_root)
    if not root.is_dir():
        raise AlrApplicationIdentityError("application_root_missing")
    if not isinstance(source_head, str) or not _HEAD_RE.fullmatch(source_head):
        raise AlrApplicationIdentityError("expectation_missing:source_head")
    for name, value in (
        ("expected_compatibility_receipt_v2", expected_compatibility_receipt_v2),
        ("expected_application_bundle_digest", expected_application_bundle_digest),
        ("expected_launch_bundle_digest", expected_launch_bundle_digest),
        ("topology_guard_file", topology_guard_file),
        ("expected_learning_runtime_digest_v2", expected_learning_runtime_digest_v2),
    ):
        if value is None:
            raise AlrApplicationIdentityError(f"expectation_missing:{name}")
    if not _DIGEST_RE.fullmatch(str(expected_learning_runtime_digest_v2)):
        raise AlrApplicationIdentityError("expected_learning_runtime_digest_v2_invalid")

    document = verify_application_root(
        root,
        source_head=source_head,
        expected_application_bundle_digest=str(expected_application_bundle_digest),
    )
    v2_receipt_path = _contained_path(
        root,
        Path(expected_compatibility_receipt_v2),
        code="compatibility_receipt_v2_outside_application_root",
    )
    resolved_v2 = verify_pinned_v2_receipt(
        root,
        v2_receipt_path,
        source_head=source_head,
        expected_learning_runtime_digest_v2=str(expected_learning_runtime_digest_v2),
    )
    # manifest 內綁的 v2 身分必須等於 receipt/pin 身分(同一樹、同一把尺)。
    if document["learning_runtime_digest_v2"] != resolved_v2:
        raise AlrApplicationIdentityError("learning_runtime_digest_v2_manifest_mismatch")
    verify_launch_prefix(
        str(expected_launch_bundle_digest), interpreter_prefix=interpreter_prefix
    )
    guard = verify_topology_guard(Path(topology_guard_file))
    v1_receipt_path = _contained_path(
        root,
        Path(expected_compatibility_receipt)
        if expected_compatibility_receipt is not None
        else root / COMPATIBILITY_RECEIPT_V1_REL,
        code="compatibility_receipt_outside_application_root",
    )
    summary = {
        "schema_version": "alr_production_identity_preflight_v1",
        "status": "PASS",
        "application_root": str(root),
        "source_head": source_head,
        "application_bundle_digest": document["self_digest"],
        "launch_bundle_digest": str(expected_launch_bundle_digest),
        "topology_guard_digest": guard["self_digest"],
    }
    return {
        **summary,
        "summary": summary,
        "source_value_guard": {
            "schema_version": "source_value_guard_v1",
            "status": "PASS",
            "learning_runtime_digest_v2": resolved_v2,
        },
        "run_kwargs": {
            "repo_root": root,
            "pinned_repo_source_head": source_head,
            "dsn_required_identity": dict(PRODUCTION_DSN_IDENTITY),
            "expected_compatibility_receipt": v1_receipt_path,
            # §8.3(W2 P1-A):每次(重)連線都要重載此 guard 並比對叢集身分列;
            # preflight 已證其可讀/自我 digest 一致,但 runtime 一律重讀不快取。
            "topology_guard_file": Path(topology_guard_file),
        },
    }


def production_failure_summary(code: str) -> dict[str, str]:
    """production 前置/pre-DB 失敗的 typed 輸出摘要(consumer 兩個 78 出口共用)。"""
    return {
        "schema_version": "alr_production_identity_preflight_v1",
        "status": "FAIL_CLOSED",
        "code": code,
    }


def run_production_preflight_from_args(arguments: Any) -> dict[str, Any]:
    """argparse 佈線 adapter:自 consumer 的 arguments 物件展開 §8.3 production 前置。"""
    return run_production_preflight(
        application_root=arguments.application_root,
        source_head=arguments.source_head,
        expected_compatibility_receipt_v2=arguments.expected_compatibility_receipt_v2,
        expected_application_bundle_digest=arguments.expected_application_bundle_digest,
        expected_launch_bundle_digest=arguments.expected_launch_bundle_digest,
        topology_guard_file=arguments.topology_guard_file,
        expected_learning_runtime_digest_v2=arguments.expected_learning_runtime_digest_v2,
        expected_compatibility_receipt=arguments.expected_compatibility_receipt,
    )


# production 模式下屬 permanent config/identity/credential-format 的 consumer 錯誤碼
# 前綴(§8.3 → exit 78);lock-busy 等 transient 類刻意不在列。
#
# E2 P2-1(W2):``psycopg2_unavailable``(runtime 相依缺失)與
# ``runtime_file_lock_unsupported``(平台無 fcntl)是永不自癒的組態失敗——留在列外會讓
# 單元以 Restart=on-failure 崩潰迴圈直到耗盡 start limit,而非一次 78 停下等 operator。
# ``topology_guard_``/``cluster_identity_`` 是 §8.3 重連身分閘的 permanent 不符(嚴格說
# 發生在連線之後,但語義同屬「不可重試的身分/組態失敗 → 78」)。
_PERMANENT_PRE_DB_PREFIXES = (
    "dsn_",
    "capture_surface_incompatible",
    "source_head_",
    "psycopg2_unavailable",
    "runtime_file_lock_unsupported",
    "candidate_board_inotify_unsupported",
    "topology_guard_",
    "cluster_identity_",
)
# 刻意「不」在列(可自癒/可由 operator 於運行中修復,或屬 host 競用):
# runtime_file_lock_busy / single_instance_lock_busy / candidate_board_directory_*。


def is_permanent_pre_db_error(error: Exception) -> bool:
    """AlrEventConsumerError 是否屬 §8.3 的 permanent 類(production → exit 78)。"""
    text = str(error)
    return any(text.startswith(prefix) for prefix in _PERMANENT_PRE_DB_PREFIXES)


# 供 consumer 引用避免重複 import 常量(alr_event_consumer 只讀此值輸出 telemetry)。
__all__ = [
    "APPLICATION_ENTRYPOINT",
    "AlrApplicationIdentityError",
    "BUNDLE_LAYOUT_VERSION",
    "CLOSURE_PATH_SECTIONS",
    "CLOSURE_SCHEMA_VERSION",
    "COMPATIBILITY_RECEIPT_V1_REL",
    "COMPATIBILITY_RECEIPT_V2_REL",
    "EX_CONFIG_EXIT_CODE",
    "MANIFEST_SCHEMA_VERSION",
    "PRODUCTION_DSN_IDENTITY",
    "REQUIRED_RUNTIME_RESOURCES",
    "RUNTIME_CLOSURE_REL",
    "build_application_bundle_document",
    "closure_declared_paths",
    "derive_tree_entries",
    "find_undeclared_paths",
    "is_permanent_pre_db_error",
    "load_runtime_closure",
    "production_failure_summary",
    "recompute_application_bundle_digest",
    "run_production_preflight",
    "run_production_preflight_from_args",
    "verify_application_root",
    "verify_launch_prefix",
    "verify_pinned_v2_receipt",
    "verify_topology_guard",
]
