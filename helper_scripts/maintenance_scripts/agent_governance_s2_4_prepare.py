#!/usr/bin/env python3
"""S2.4(WP4·W3b)typed PREPARE 主機 driver 葉(§5.1 / §8.1 / §10.5 #30/#33)。

提供 §10.2 凍結 ABI 的 ``prepare_s2_4_install_bundle(intent, authorization, driver)``。
姿態逐條鏡 W3a 的 ``run_s2_4_capability_probe``:

- **source lane 零 effect**:``driver=None``(Mac/源碼/測試)一律回 typed
  ``EXTERNAL_VERIFICATION_PENDING`` 且 ``mutation_performed=False``;真主機動作全部經
  **注入的** :class:`PrepareDriver`(真 Linux 實作屬 W6A,本葉不含);
- **發佈邊界硬封**(§5.1 #1):本葉只認一個可寫根——
  ``/var/lib/arcane-equilibrium/aiml/install/s2_4/prepared/<prepare_id>/``。target 路徑由
  ``prepare_id`` **導出**,caller 永不遞交路徑;``/opt`` / ``/etc`` / credstore /
  ``/etc/systemd/system`` / PG / UID / 已安裝 unit 全在 :data:`PREPARE_PUBLICATION_DENY_ROOTS`
  與 route-surface 的十三個 forbidden surface 兩層拒;
- **兩段 sandbox 子相**(§8.1/§10.5 #33):``FETCH_BYTES`` 只下載 hash-pinned wheels 且
  **不得** import/執行 artifact;``BUILD_AND_IMPORT`` 無網路、無 credential、無 state 目錄;
  root 全程**不**執行任何 dependency 程式碼。四個違規旗標任一為真即 typed 失敗並補償;
  resource/egress/path 上限逐一綁入 receipt(``sandbox_contract_digest``);
- **PREPARE_SANDBOX probe 前置**:必須帶一份 terminal 的 scope 相符 probe 證據
  (由 W3a :func:`derive_probe_phase_prerequisite_status` 再導出),且 intent 的
  ``prepare_sandbox_probe_receipt_digest`` 必須綁到**那一份** receipt;缺席/scope 替換即
  ``HOST_NETWORK_SANDBOX_CAPABILITY_UNSATISFIED``;
- **WAL 先於變更**(§5.2):``PREPARING`` 於**建立 staging 目錄之前**落盤 fsync;其後任何
  失敗都走「只補償本 journal 的 task-owned staging delta」並回 typed 非成功。

誠實界線:本葉「不」認證任何 runtime——九 authority / production_apply_performed /
running_attested 恆 false;帶真 driver 的 ``PREPARED`` 也只是 receipt 證據,真 EFFECT
(signed core / install lock / replay 消費落盤)屬 W4/W6A。
"""
from __future__ import annotations

import posixpath
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
PROGRAM_CODE_DIR = REPO_ROOT / "program_code"
for _candidate in (HELPER_DIR, ML_TRAINING_DIR, PROGRAM_CODE_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import aiml_gate_receipt_validator as central_validator  # noqa: E402
import agent_governance_s2_4_component as _component  # noqa: E402
import agent_governance_s2_4_probe as _probe  # noqa: E402

canonical_digest = central_validator.canonical_digest
artifact_self_digest = central_validator.artifact_self_digest
# §7/§10.5 #15:driver 例外紅字化與可序列化面秘密掃描的共用來源(component 葉)。
redact_driver_error = _component.redact_driver_error
scan_serializable_surface = _component.scan_serializable_surface
derive_recorded_evidence_class = _component.derive_recorded_evidence_class

# ── §5.1 / §9.1 code-owned 契約常量 ──────────────────────────────────────────────
PREPARE_ROUTE_CLASS = "s2_4_prepare_intent"
PREPARE_REQUIRED_EFFECT_CLASS = "LEARNING_RUNTIME_PREPARE"
PREPARE_SERVICE_SURFACE = "transient_builder_only"
PREPARE_AUTHORIZATION_PROFILE = "aiml-s2-install-prepare-operator-v1"
PREPARE_SIGNATURE_NAMESPACE = "arcane-equilibrium-aiml-s2-install-prepare"
PREPARE_ID_PREFIX = "s2-4-prepare-"
# §5.1 #1 / §5.2:唯一被授權的 staging parent(prepared/<prepare_id> 由 id 導出)。
PREPARE_STAGING_PARENT = "/var/lib/arcane-equilibrium/aiml/install/s2_4/prepared"
PREPARE_EVIDENCE_TTL_SECONDS = 900
# §5.1 #1 明列的「PREPARE 絕不觸碰」根;driver 若回報任何寫入落在其下即 fail-closed。
PREPARE_PUBLICATION_DENY_ROOTS = (
    "/etc/credstore.encrypted",
    "/etc/arcane-equilibrium",
    "/etc/systemd/system",
    "/opt/arcane-equilibrium",
)
# §4:prepare intent 的十三個 forbidden surface(schema 已 const false;此為再導出面)。
PREPARE_FORBIDDEN_SURFACES = (
    "apply_publish",
    "broker_or_order",
    "credential_install",
    "daemon_reload",
    "etc_write",
    "host_identity",
    "migration",
    "opt_publish",
    "persistent_unit_enable",
    "persistent_unit_start",
    "persistent_unit_write",
    "pg",
    "secret",
)
# §10.5 #33:PREPARE sandbox 的四個「必須為假」的能力旗標(receipt-bound)。
PREPARE_SANDBOX_VIOLATION_FLAGS = (
    "build_network_access",
    "build_credential_access",
    "build_state_access",
    "root_executed_dependency_code",
)

# ── typed 終端狀態(§10.2;無別名可把其一變成 success)──────────────────────────
PREPARE_STATUS_PREPARED = "PREPARED"
PREPARE_STATUS_PENDING = "EXTERNAL_VERIFICATION_PENDING"
PREPARE_STATUS_REQUEST_REJECTED = "PREPARE_REQUEST_REJECTED"
PREPARE_STATUS_AUTHORIZATION_REJECTED = "AUTHORIZATION_REJECTED"
PREPARE_STATUS_CAPABILITY_UNSATISFIED = "HOST_NETWORK_SANDBOX_CAPABILITY_UNSATISFIED"
PREPARE_STATUS_BUNDLE_INVALID = "PREPARED_BUNDLE_INVALID"
PREPARE_STATUS_PRECHECK_FAILED = "PRECHECK_FAILED"
PREPARE_STATUS_FAILED = "PREPARE_FAILED"
PREPARE_STATUS_RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
PREPARE_TYPED_STATUSES = (
    PREPARE_STATUS_AUTHORIZATION_REJECTED,
    PREPARE_STATUS_BUNDLE_INVALID,
    PREPARE_STATUS_CAPABILITY_UNSATISFIED,
    PREPARE_STATUS_FAILED,
    PREPARE_STATUS_PENDING,
    PREPARE_STATUS_PRECHECK_FAILED,
    PREPARE_STATUS_PREPARED,
    PREPARE_STATUS_RECOVERY_REQUIRED,
    PREPARE_STATUS_REQUEST_REJECTED,
)

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_HEAD_RE = re.compile(r"^[0-9a-f]{40}$")
_PREPARE_ID_RE = re.compile(r"^s2-4-prepare-[0-9a-f]{64}$")
_ALL_FALSE_PRODUCTION_FLAGS = {
    "nine_authorities_false": True,
    "production_apply_performed": False,
    "running_attested": False,
}
# §10.5 #38 / 硬邊界 4:caller 絕不得經任何鍵遞交 raw shell/SQL/unit 文本/任意路徑/秘密。
PREPARE_RAW_INGRESS_KEYS = (
    "argv",
    "command",
    "commands",
    "dsn",
    "password",
    "path",
    "paths",
    "script",
    "secret",
    "shell",
    "sql",
    "staging_root",
    "statements",
    "target_path",
    "target_root",
    "unit_text",
)


class PrepareContractError(ValueError):
    """PREPARE 契約層硬錯誤(帶 typed ``code``)。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# --------------------------------------------------------------------------- #
# 路徑/邊界:staging root 由 prepare_id **導出**,caller 永不遞交路徑。
# --------------------------------------------------------------------------- #
def prepared_staging_root(prepare_id: Any) -> str:
    """``/var/lib/.../prepared/<prepare_id>``;prepare_id 形狀不符即 typed 拒。"""

    if not isinstance(prepare_id, str) or _PREPARE_ID_RE.fullmatch(prepare_id) is None:
        raise PrepareContractError("prepare_id_invalid")
    return f"{PREPARE_STAGING_PARENT}/{prepare_id}"


def prepare_journal_path(prepare_id: Any) -> str:
    """§5.2 的 PREPARE WAL 路徑(同樣由 id 導出)。"""

    if not isinstance(prepare_id, str) or _PREPARE_ID_RE.fullmatch(prepare_id) is None:
        raise PrepareContractError("prepare_id_invalid")
    return f"{PREPARE_STAGING_PARENT}/{prepare_id}.prepare.journal.json"


def normalize_prepare_path(entry: Any) -> str | None:
    """把 driver 回報的路徑正規化成絕對 POSIX 形;不可接受的形狀回 ``None``。

    ``startswith`` 的文字比對可被 ``<staging_root>/../../../../opt/...`` 整個繞過——它同時
    「以 staging_root 開頭」且「不以任何 deny root 開頭」,兩道閘都放行(W3 review E3 P2-3)。
    故本函式在比對之前正規化,並把**任何** ``..`` 節段直接判為不可接受(不試圖解析它:
    符號連結存在時 ``normpath`` 的語意解析並不等於核心的真實解析)。
    """

    if not isinstance(entry, (str, Path)):
        return None
    text = str(entry)
    if not text or "\x00" in text:
        return None
    if not text.startswith("/"):
        return None
    segments = text.split("/")
    if any(segment == ".." for segment in segments):
        return None
    normalized = posixpath.normpath(text)
    return normalized if normalized.startswith("/") else None


def prepare_publication_boundary_reasons(paths: Any) -> list[str]:
    """任一 driver 回報的寫入路徑必須落在 staging root 之下,且不得碰 deny 根。"""

    reasons: list[str] = []
    for entry in list(paths or []):
        normalized = normalize_prepare_path(entry)
        if normalized is None:
            reasons.append(
                f"PREPARE reported a path that cannot be normalized to a traversal-free "
                f"absolute path: {entry!r} (a '..' segment is rejected outright)"
            )
            continue
        for deny in PREPARE_PUBLICATION_DENY_ROOTS:
            if normalized == deny or normalized.startswith(deny + "/"):
                reasons.append(
                    f"PREPARE wrote below the forbidden publication root {deny}: {normalized} "
                    "(PREPARE cannot publish into /opt, /etc, credstore or persistent units)"
                )
    return reasons


def prepare_containment_reasons(paths: Any, staging_root: str) -> list[str]:
    """所有寫入路徑必須(正規化後)落在**本 task 的** staging root 之下。"""

    reasons: list[str] = []
    root = normalize_prepare_path(staging_root)
    if root is None:
        return ["the derived staging root is not a traversal-free absolute path"]
    for entry in list(paths or []):
        normalized = normalize_prepare_path(entry)
        if normalized is None:
            reasons.append(
                f"PREPARE reported a path that cannot be normalized to a traversal-free "
                f"absolute path: {entry!r}"
            )
            continue
        if not (normalized == root or normalized.startswith(root + "/")):
            reasons.append(
                f"PREPARE wrote outside its task-owned staging root: {normalized}"
            )
    return reasons


def prepare_raw_ingress_reasons(*payloads: Any) -> list[str]:
    """§硬邊界 4:掃出 caller 夾帶的 raw shell/SQL/unit/path/secret 鍵即 typed 拒。"""

    reasons: list[str] = []

    def _walk(node: Any, trail: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if str(key) in PREPARE_RAW_INGRESS_KEYS:
                    reasons.append(
                        f"caller-provided raw ingress key {trail}{key!r} is rejected: the "
                        "PREPARE driver accepts only validated digests/budgets, never raw "
                        "shell, SQL, unit text, secrets or arbitrary paths"
                    )
                _walk(value, f"{trail}{key}.")
        elif isinstance(node, list):
            for item in node:
                _walk(item, trail)

    for payload in payloads:
        _walk(payload, "")
    return reasons


# --------------------------------------------------------------------------- #
# §8.1 / §10.5 #33:兩段 sandbox 子相契約(屬性集來自 W3a probe 葉的同一凍結面)。
# --------------------------------------------------------------------------- #
def prepare_sandbox_contract(*, artifact_mirror_allowlist: Any) -> dict[str, Any]:
    """FETCH/BUILD 屬性 + 四條「不可為真」的能力斷言 + 路徑邊界(receipt-bound)。"""

    properties = _probe.prepare_sandbox_property_set(
        artifact_mirror_allowlist=artifact_mirror_allowlist
    )
    return {
        "schema_version": "s2_4_prepare_sandbox_contract_v1_informal",
        "fetch_bytes": {
            "properties": properties["fetch_bytes"],
            # §8.1:fetch「下載但不 import/執行 dependency 程式碼」。
            "may_execute_artifacts": False,
            "credential_access": False,
            "state_directory_access": False,
        },
        "build_and_import": {
            "properties": properties["build_and_import"],
            "network_access": False,
            "credential_access": False,
            "state_directory_access": False,
            "root_executes_dependency_code": False,
        },
        "staging_parent": PREPARE_STAGING_PARENT,
        "publication_deny_roots": list(PREPARE_PUBLICATION_DENY_ROOTS),
    }


def prepare_sandbox_contract_digest(*, artifact_mirror_allowlist: Any) -> str:
    return canonical_digest(
        prepare_sandbox_contract(artifact_mirror_allowlist=artifact_mirror_allowlist)
    )


# --------------------------------------------------------------------------- #
# core / intent 建構(§5.1 unsigned core -> derived id)。
# --------------------------------------------------------------------------- #
def build_prepare_core(
    *,
    staging_parent_path: str = PREPARE_STAGING_PARENT,
    staging_parent_device: int,
    staging_parent_inode: int,
    max_bytes: int,
    max_seconds: int,
    max_fetch_bytes: int,
    max_fetch_seconds: int,
    max_artifacts: int,
    max_build_bytes: int,
    max_build_seconds: int,
    source_head: str,
    target_host: str,
    created_at: str,
) -> dict[str, Any]:
    """unsigned prepare core(不含 prepare_id/授權/self_digest;§5.1 無 digest 迴圈)。"""

    if not _HEAD_RE.fullmatch(str(source_head)):
        raise PrepareContractError("prepare_core_source_head_invalid")
    if staging_parent_path != PREPARE_STAGING_PARENT:
        # worker 不得選 journal/staging 位置(§10.4);唯一被授權的 parent 硬釘。
        raise PrepareContractError("prepare_core_staging_parent_not_authorized")
    return {
        "schema_version": "s2_4_prepare_core_v1",
        "staging_root_device_inode": {
            "staging_parent_path": staging_parent_path,
            "device": int(staging_parent_device),
            "inode": int(staging_parent_inode),
        },
        "resource_budget": {"max_bytes": int(max_bytes), "max_seconds": int(max_seconds)},
        "fetch_budget": {
            "max_fetch_bytes": int(max_fetch_bytes),
            "max_fetch_seconds": int(max_fetch_seconds),
            "max_artifacts": int(max_artifacts),
        },
        "build_budget": {
            "max_build_bytes": int(max_build_bytes),
            "max_build_seconds": int(max_build_seconds),
        },
        "source_head": source_head,
        "target_host": target_host,
        "created_at": created_at,
    }


def prepare_id_for_core(core: dict[str, Any]) -> str:
    """``prepare_id = 's2-4-prepare-' + hex(canonical_digest(core))``(§5.1)。"""

    return PREPARE_ID_PREFIX + canonical_digest(core).split(":", 1)[1]


def build_prepare_intent(
    core: dict[str, Any],
    *,
    source_compatibility_receipt_digest: str,
    sealed_build_receipt_digest: str,
    identity_contract_digest: str,
    application_manifest_digest: str,
    prepare_sandbox_probe_receipt_digest: str,
    expires_at: str,
    max_ttl_seconds: int = PREPARE_EVIDENCE_TTL_SECONDS,
) -> dict[str, Any]:
    """closed route-class intent:route surface 全 const、十三個 forbidden surface 全 false。"""

    core_digest = canonical_digest(core)
    intent = {
        "schema_version": "s2_4_prepare_intent_v1",
        "route_class": PREPARE_ROUTE_CLASS,
        "core": core,
        "core_digest": core_digest,
        "prepare_id": PREPARE_ID_PREFIX + core_digest.split(":", 1)[1],
        "route_surface": {
            "required_effect_class": PREPARE_REQUIRED_EFFECT_CLASS,
            "runtime_effect": True,
            "service": PREPARE_SERVICE_SURFACE,
            "risk": "high",
            "runtime_claim": True,
            "staging_budget_bound": True,
            "fetch_budget_bound": True,
            "build_budget_bound": True,
            "cleanup_budget_bound": True,
        },
        "forbidden_surfaces": {name: False for name in PREPARE_FORBIDDEN_SURFACES},
        "required_authorization": {
            "profile_identity": PREPARE_AUTHORIZATION_PROFILE,
            "signature_namespace": PREPARE_SIGNATURE_NAMESPACE,
            "max_ttl_seconds": int(max_ttl_seconds),
        },
        "source_lock_closure_identity": {
            "source_compatibility_receipt_digest": source_compatibility_receipt_digest,
            "sealed_build_receipt_digest": sealed_build_receipt_digest,
            "identity_contract_digest": identity_contract_digest,
        },
        "application_manifest_digest": application_manifest_digest,
        "prepare_sandbox_probe_receipt_digest": prepare_sandbox_probe_receipt_digest,
        "expires_at": expires_at,
    }
    intent["self_digest"] = artifact_self_digest(intent)
    return intent


def prepare_route_surface_contract() -> dict[str, Any]:
    """§4/§10.5 #38 的 code-owned route-surface 契約投影(wave ABI 折入面)。"""

    return {
        "route_class": PREPARE_ROUTE_CLASS,
        "required_effect_class": PREPARE_REQUIRED_EFFECT_CLASS,
        "service": PREPARE_SERVICE_SURFACE,
        "forbidden_surfaces": list(PREPARE_FORBIDDEN_SURFACES),
        "required_authorization": {
            "profile_identity": PREPARE_AUTHORIZATION_PROFILE,
            "signature_namespace": PREPARE_SIGNATURE_NAMESPACE,
            "max_ttl_seconds": PREPARE_EVIDENCE_TTL_SECONDS,
        },
        "staging_parent": PREPARE_STAGING_PARENT,
        "publication_deny_roots": list(PREPARE_PUBLICATION_DENY_ROOTS),
        "sandbox_violation_flags": list(PREPARE_SANDBOX_VIOLATION_FLAGS),
    }


def derive_prepare_route_surface_status(intent: Any) -> dict[str, Any]:
    """§10.5 #38:節點注入**之前**再導出 PREPARE 的 route surface;夾帶 APPLY 權限即拒。"""

    reasons: list[str] = []
    if not isinstance(intent, dict):
        return {
            "status": "PREPARE_ROUTE_SURFACE_REJECTED",
            "reasons": ["prepare intent must be an object"],
        }
    if intent.get("schema_version") != "s2_4_prepare_intent_v1":
        reasons.append("prepare intent schema_version is not s2_4_prepare_intent_v1")
    if intent.get("route_class") != PREPARE_ROUTE_CLASS:
        reasons.append(f"prepare intent route_class must be {PREPARE_ROUTE_CLASS}")
    surface = intent.get("route_surface")
    if not isinstance(surface, dict):
        reasons.append("prepare intent route_surface must be an object")
    else:
        if surface.get("required_effect_class") != PREPARE_REQUIRED_EFFECT_CLASS:
            reasons.append(
                "prepare route_surface required_effect_class must be "
                "LEARNING_RUNTIME_PREPARE (an APPLY effect class is rejected before "
                "node injection)"
            )
        if surface.get("service") != PREPARE_SERVICE_SURFACE:
            reasons.append(
                "prepare route_surface service must be transient_builder_only "
                "(a persistent-service surface is rejected before node injection)"
            )
        if surface.get("runtime_effect") is not True or surface.get("runtime_claim") is not True:
            reasons.append("prepare route_surface must declare runtime_effect/runtime_claim true")
        if surface.get("risk") != "high":
            reasons.append("prepare route_surface risk must be high")
        for flag in (
            "staging_budget_bound",
            "fetch_budget_bound",
            "build_budget_bound",
            "cleanup_budget_bound",
        ):
            if surface.get(flag) is not True:
                reasons.append(f"prepare route_surface must bind {flag}")
    forbidden = intent.get("forbidden_surfaces")
    if not isinstance(forbidden, dict):
        reasons.append("prepare intent forbidden_surfaces must be an object")
    else:
        if sorted(forbidden) != sorted(PREPARE_FORBIDDEN_SURFACES):
            reasons.append("prepare forbidden_surfaces is not the exact §4 thirteen-surface set")
        carried = sorted(name for name, value in forbidden.items() if value is not False)
        if carried:
            reasons.append(
                "PREPARE request carries persistent-service/PG/migration/secret/credential/"
                f"host APPLY authority surfaces {carried}; rejected before node injection "
                "(§10.5 #38)"
            )
    required = intent.get("required_authorization")
    if not isinstance(required, dict):
        reasons.append("prepare intent required_authorization must be an object")
    else:
        if required.get("profile_identity") != PREPARE_AUTHORIZATION_PROFILE:
            reasons.append(
                "prepare required_authorization profile_identity must be the PREPARE "
                "profile (probe/install/pg-migration profiles are rejected)"
            )
        if required.get("signature_namespace") != PREPARE_SIGNATURE_NAMESPACE:
            reasons.append(
                "prepare required_authorization signature_namespace is not the PREPARE namespace"
            )
        ttl = required.get("max_ttl_seconds")
        if not isinstance(ttl, int) or isinstance(ttl, bool) or not 1 <= ttl <= (
            PREPARE_EVIDENCE_TTL_SECONDS
        ):
            reasons.append(
                "prepare required_authorization max_ttl_seconds must be within the "
                f"{PREPARE_EVIDENCE_TTL_SECONDS}s §9.1 ceiling"
            )
    core = intent.get("core")
    if not isinstance(core, dict):
        reasons.append("prepare intent core must be an object")
    else:
        staging = core.get("staging_root_device_inode")
        if not isinstance(staging, dict) or staging.get("staging_parent_path") != (
            PREPARE_STAGING_PARENT
        ):
            reasons.append(
                "prepare core staging parent is not the authorized "
                f"{PREPARE_STAGING_PARENT} (worker-selected staging locations are rejected)"
            )
    reasons.extend(prepare_raw_ingress_reasons(intent.get("route_surface")))
    return {
        "status": "PASS" if not reasons else "PREPARE_ROUTE_SURFACE_REJECTED",
        "reasons": reasons,
    }


# --------------------------------------------------------------------------- #
# 注入式 driver protocol —— 真主機動作的唯一出口(真實作屬 W6A,本葉不含)。
# --------------------------------------------------------------------------- #
class PrepareDriver(Protocol):
    """PREPARE 的固定操作面;caller **永不**遞交 raw shell/路徑/wheel URL 字串。

    誠實界線:本 protocol 只宣告操作形狀。source lane 的 driver 恆為 ``None``;
    disposable/simulation driver 的 ``evidence_class`` 不是 PLATFORM_ATTESTED,故其結果
    永遠不能被當成 runtime 證據。
    """

    evidence_class: str

    def journal_transition(self, *, entry: dict[str, Any]) -> None:
        """把一筆 WAL transition 以 temp-create→fsync→atomic-rename→parent-fsync 落盤。"""
        ...

    def verify_staging_parent(self, *, staging_parent: str) -> dict[str, Any]:
        """``O_DIRECTORY|O_NOFOLLOW`` 開已驗 parent,回 ``{device, inode, mode, owner,
        is_symlink, link_count}``(絕不 join 未驗字串)。"""
        ...

    def create_staging_root(self, *, staging_root: str) -> dict[str, Any]:
        """``openat(O_NOFOLLOW|O_CREAT|O_EXCL)`` 建 task-owned staging root,回其 device/inode。"""
        ...

    def fetch_pinned_artifacts(
        self, *, staging_root: str, pinned_artifacts: list[dict[str, Any]], fetch_budget: dict[str, Any]
    ) -> dict[str, Any]:
        """FETCH_BYTES 子相:只下載 hash-pinned wheels。回
        ``{artifacts:[{locator, content_digest}], executed_artifacts, bytes_fetched,
        seconds_elapsed, written_paths}``。"""
        ...

    def build_and_import(
        self, *, staging_root: str, build_budget: dict[str, Any]
    ) -> dict[str, Any]:
        """BUILD_AND_IMPORT 子相(獨立 DynamicUser、無網路)。回
        ``{network_access, credential_access, state_access, root_executed_dependency_code,
        native_import_proof_digest, bytes_written, seconds_elapsed, written_paths}``。"""
        ...

    def freeze_and_rehash_staging(self, *, staging_root: str) -> dict[str, Any]:
        """凍結成 root-owned/non-writable 並獨立重算。回
        ``{root_owned_nonwritable, device, inode, base_runtime_tree_manifest_digest,
        base_runtime_tree_digest, application_bundle_manifest_digest,
        application_bundle_digest, launch_bundle_manifest_digest, launch_bundle_digest}``。"""
        ...

    def independent_residue_postcheck(
        self, *, staging_root: str, prepare_id: str, prepare_core_digest: str
    ) -> dict[str, Any]:
        """**相異** verifier 節點的獨立殘留 postcheck(applier 不得自證)。"""
        ...

    def compensate_staging(self, *, staging_root: str) -> dict[str, Any]:
        """只補償本 journal 的 task-owned staging delta。回
        ``{task_owned_only, staging_delta_removed, staging_absent}``。"""
        ...

    def trusted_host_time(self) -> str:
        """trusted-host 時鐘(receipt 的 ``trusted_host_time``;絕不用 caller 時鐘)。"""
        ...


class _PrepareAbort(Exception):
    """內部中止訊號(帶 typed status + reason)。"""

    def __init__(self, status: str, reason: str) -> None:
        super().__init__(reason)
        self.status = status
        self.reason = reason


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _resolve_now(now: str | datetime | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if isinstance(now, datetime):
        return now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return central_validator._parse_timestamp(now)


def _staging_state(staging_root: str, *, present: bool, device: Any = None, inode: Any = None) -> str:
    return canonical_digest({
        "staging_root": staging_root,
        "present": bool(present),
        "device": device,
        "inode": inode,
    })


def _verdict(
    status: str,
    reasons: list[str],
    *,
    prepare_id: str | None = None,
    staging_root: str | None = None,
    mutation_performed: bool = False,
    driver_engaged: bool = False,
    prepared_bundle: dict[str, Any] | None = None,
    effect_receipt: dict[str, Any] | None = None,
    journal: dict[str, Any] | None = None,
    rollback: dict[str, Any] | None = None,
    postcheck: dict[str, Any] | None = None,
) -> dict[str, Any]:
    verdict = {
        "schema_version": "s2_4_prepare_run_verdict_v1_informal",
        "status": status,
        "reasons": list(reasons),
        "prepare_id": prepare_id,
        "staging_root": staging_root,
        "mutation_performed": bool(mutation_performed),
        "driver_engaged": bool(driver_engaged),
        "blocks_apply": status != PREPARE_STATUS_PREPARED,
        "prepared_bundle": prepared_bundle,
        "effect_receipt": effect_receipt,
        "journal": journal,
        "rollback": rollback,
        "postcheck": postcheck,
        "production_authority_flags": dict(_ALL_FALSE_PRODUCTION_FLAGS),
        "secret_material_scanned": True,
    }
    # §10.5 #15:PREPARE 的唯一出境面。本 route 沒有秘密 ingress,但掃描仍是無條件的——
    # 任一 driver 回報值帶著進程內活哨兵的秘密即整份丟棄,fail-closed 回 RECOVERY_REQUIRED。
    leak_reasons = scan_serializable_surface(verdict)
    if not leak_reasons:
        return verdict
    return {
        **{key: None for key in ("prepared_bundle", "effect_receipt", "journal", "rollback",
                                 "postcheck")},
        "schema_version": "s2_4_prepare_run_verdict_v1_informal",
        "status": PREPARE_STATUS_RECOVERY_REQUIRED,
        "reasons": leak_reasons + [
            "the constructed PREPARE verdict carried secret material; every artifact and reason "
            "was dropped rather than returned (§7)"
        ],
        "prepare_id": prepare_id,
        "staging_root": staging_root,
        "mutation_performed": bool(mutation_performed),
        "driver_engaged": bool(driver_engaged),
        "blocks_apply": True,
        "production_authority_flags": dict(_ALL_FALSE_PRODUCTION_FLAGS),
        "secret_material_scanned": True,
    }


def _authorization_profile_errors(authorization: Any, intent: dict[str, Any]) -> list[str]:
    """PREPARE 授權只接受 PREPARE profile;probe/install/pg 授權挪用即拒。"""

    if not isinstance(authorization, dict):
        return ["prepare authorization must be an object"]
    reasons: list[str] = []
    if authorization.get("schema_version") != "s2_4_operator_authorization_v1":
        reasons.append("prepare authorization schema_version is not s2_4_operator_authorization_v1")
    if authorization.get("profile_identity") != PREPARE_AUTHORIZATION_PROFILE:
        reasons.append(
            "prepare authorization profile_identity is not the PREPARE profile "
            "(probe/aggregate-install/pg-migration authority cannot authorize PREPARE)"
        )
    if authorization.get("signature_namespace") != PREPARE_SIGNATURE_NAMESPACE:
        reasons.append("prepare authorization signature_namespace is not the PREPARE namespace")
    required = intent.get("required_authorization")
    if isinstance(required, dict):
        try:
            issued = central_validator._parse_timestamp(authorization["issued_at"])
            expires = central_validator._parse_timestamp(authorization["expires_at"])
            if (expires - issued).total_seconds() > int(required["max_ttl_seconds"]):
                reasons.append("prepare authorization TTL exceeds the intent's declared ceiling")
        except (KeyError, TypeError, ValueError):
            reasons.append("prepare authorization timestamps are invalid")
    return reasons


def _probe_prerequisite_reasons(
    intent: dict[str, Any], probe_evidence: Any, *, now: str | datetime | None
) -> list[str]:
    """PREPARE_SANDBOX 前置:scope 相符的 terminal probe receipt,且被 intent 逐 digest 綁定。"""

    verdict = _probe.derive_probe_phase_prerequisite_status("W6A", probe_evidence, now=now)
    if verdict["status"] != "PROBE_PREREQUISITE_SATISFIED":
        return list(verdict["reasons"])
    receipt = (probe_evidence or {}).get("PREPARE_SANDBOX", {}).get("effect_receipt", {})
    if receipt.get("self_digest") != intent.get("prepare_sandbox_probe_receipt_digest"):
        return [
            "prepare intent prepare_sandbox_probe_receipt_digest does not bind the supplied "
            "terminal PREPARE_SANDBOX probe receipt"
        ]
    return []


def prepare_s2_4_install_bundle(
    intent: Any,
    authorization: Any = None,
    driver: "PrepareDriver | None" = None,
    *,
    now: str | datetime | None = None,
    replay_ledger: Any = None,
    probe_evidence: Any = None,
    pinned_artifacts: Any = None,
    artifact_mirror_allowlist: Any = None,
    fault: Callable[[str], None] | None = None,
    clock: Callable[[], datetime] | None = None,
    applier_node: str = "s2-4-prepare-applier",
) -> dict[str, Any]:
    """§10.2 凍結 ABI:執行(或 fail-closed 拒絕)一次 typed PREPARE。

    固定順序,driver 呼叫**之前**零變更:

    1. intent 過中央閘 closed schema + §5.1 core/prepare_id 再導出;
    2. §10.5 #38 route-surface 再導出(APPLY 權限夾帶即拒,節點注入前);
    3. caller raw-ingress 掃描(shell/SQL/unit/path/secret 鍵一律拒);
    4. PREPARE_SANDBOX terminal probe 前置(scope 替換/缺席即 typed capability 未滿足);
    5. 授權:PREPARE profile/namespace/TTL + §9.1 SSHSIG/信任根 + replay 消費綁定;
    6. intent 自身新鮮窗;
    7. ``driver is None`` → ``EXTERNAL_VERIFICATION_PENDING``(零變更、零 driver 呼叫);
    8. driver 在場 → WAL(PREPARING,**建 staging 之前**)→ parent 驗 → 建 staging →
       FETCH_BYTES → BUILD_AND_IMPORT → 凍結重算 → bundle → 終端 journal → 獨立 postcheck
       → receipt。任一步失敗即補償 task-owned staging delta 並回 typed 非成功。
    """

    # step 1 —— intent 結構/身分再導出。
    if not isinstance(intent, dict):
        return _verdict(PREPARE_STATUS_REQUEST_REJECTED, ["prepare intent must be an object"])
    schema_errors = central_validator.validate_aiml_artifact(intent, now=None)
    if schema_errors:
        return _verdict(PREPARE_STATUS_REQUEST_REJECTED, schema_errors)
    core = intent["core"]
    prepare_id = intent["prepare_id"]
    core_digest = intent["core_digest"]
    staging_root = prepared_staging_root(prepare_id)
    # step 2 —— route surface(§10.5 #38)。
    surface = derive_prepare_route_surface_status(intent)
    if surface["status"] != "PASS":
        return _verdict(
            PREPARE_STATUS_REQUEST_REJECTED, surface["reasons"],
            prepare_id=prepare_id, staging_root=staging_root,
        )
    # step 3 —— caller raw ingress(shell/SQL/unit/path/secret)。
    ingress = prepare_raw_ingress_reasons(pinned_artifacts)
    if ingress:
        return _verdict(
            PREPARE_STATUS_REQUEST_REJECTED, ingress,
            prepare_id=prepare_id, staging_root=staging_root,
        )
    # step 4 —— PREPARE_SANDBOX terminal probe 前置(§8.3/§9.2)。
    probe_reasons = _probe_prerequisite_reasons(intent, probe_evidence, now=now)
    if probe_reasons:
        return _verdict(
            PREPARE_STATUS_CAPABILITY_UNSATISFIED, probe_reasons,
            prepare_id=prepare_id, staging_root=staging_root,
        )
    # step 5 —— 授權(profile/namespace/TTL + §9.1 SSHSIG/信任根 + replay 消費綁定)。
    reasons = _authorization_profile_errors(authorization, intent)
    if replay_ledger is None:
        reasons.append(
            "prepare authorization replay-consumption cannot be proved without the "
            "authorization replay ledger (fail-closed)"
        )
    if reasons:
        return _verdict(
            PREPARE_STATUS_AUTHORIZATION_REJECTED, reasons,
            prepare_id=prepare_id, staging_root=staging_root,
        )
    replay = central_validator.derive_authorization_replay_binding(
        authorization, replay_ledger, now=now
    )
    if replay["status"] != "UNCONSUMED_AUTHORIZATION_VALID":
        return _verdict(
            PREPARE_STATUS_AUTHORIZATION_REJECTED, replay["reasons"],
            prepare_id=prepare_id, staging_root=staging_root,
        )
    # step 6 —— intent 新鮮窗。
    now_dt = _resolve_now(now)
    try:
        intent_expires = central_validator._parse_timestamp(intent["expires_at"])
    except (KeyError, TypeError, ValueError):
        return _verdict(
            PREPARE_STATUS_REQUEST_REJECTED, ["prepare intent expires_at is invalid"],
            prepare_id=prepare_id, staging_root=staging_root,
        )
    if now_dt >= intent_expires:
        return _verdict(
            PREPARE_STATUS_REQUEST_REJECTED, ["prepare intent is expired"],
            prepare_id=prepare_id, staging_root=staging_root,
        )
    # step 7 —— 無 driver(Mac/源碼/測試):reachable 閘在,但沒有可執行的主機面。
    if driver is None:
        return _verdict(
            PREPARE_STATUS_PENDING,
            [
                "PREPARE is reachable but authority-locked: no host prepare driver is present "
                "(Mac/source/test lane); EXTERNAL_VERIFICATION_PENDING with zero mutation"
            ],
            prepare_id=prepare_id, staging_root=staging_root,
        )
    # step 8 —— driver 在場:完整 PREPARE 生命週期。
    return _run_prepare_with_driver(
        intent=intent, authorization=authorization, driver=driver, core=core,
        core_digest=core_digest, prepare_id=prepare_id, staging_root=staging_root,
        replay_ledger=replay_ledger, pinned_artifacts=list(pinned_artifacts or []),
        artifact_mirror_allowlist=artifact_mirror_allowlist, fault=fault,
        clock=clock or (lambda: datetime.now(timezone.utc)),
        applier_node=applier_node, now_dt=now_dt,
    )


def _run_prepare_with_driver(
    *,
    intent: dict[str, Any],
    authorization: dict[str, Any],
    driver: Any,
    core: dict[str, Any],
    core_digest: str,
    prepare_id: str,
    staging_root: str,
    replay_ledger: dict[str, Any],
    pinned_artifacts: list[dict[str, Any]],
    artifact_mirror_allowlist: Any,
    fault: Callable[[str], None] | None,
    clock: Callable[[], datetime],
    applier_node: str,
    now_dt: datetime,
) -> dict[str, Any]:
    """driver 在場的固定生命週期;PREPARING 入 WAL 後任何失敗都補償(fail-closed)。"""

    entries: list[dict[str, Any]] = []
    absent_state = _staging_state(staging_root, present=False)
    committed = False
    mutation_performed = False
    written_paths: list[str] = []
    locators: list[dict[str, Any]] = []
    frozen: dict[str, Any] = {}
    native_proof: str | None = None
    try:
        sandbox_digest = prepare_sandbox_contract_digest(
            artifact_mirror_allowlist=artifact_mirror_allowlist
        )
    except _probe.ProbeContractError as error:
        return _verdict(
            PREPARE_STATUS_REQUEST_REJECTED,
            [f"prepare sandbox contract is not derivable: {error.code}"],
            prepare_id=prepare_id, staging_root=staging_root, driver_engaged=False,
        )

    def _gate(label: str) -> None:
        if fault is not None:
            fault(label)

    def _journal(state: str, pre: str, post: str) -> None:
        entry = {
            "seq": len(entries),
            "state": state,
            "pre_state_digest": pre,
            "post_state_digest": post,
            "fsynced": True,
            "recorded_at": _iso(clock()),
        }
        driver.journal_transition(entry=entry)
        entries.append(entry)

    try:
        # §5.2:PREPARING 於**建立 staging 目錄之前**記錄並 fsync。
        _gate("pre_journal_preparing")
        _journal("PREPARING", absent_state, absent_state)
        committed = True
        _gate("post_journal_preparing")

        _gate("pre_verify_parent")
        parent = driver.verify_staging_parent(staging_parent=PREPARE_STAGING_PARENT)
        _gate("post_verify_parent")
        parent_reasons = _staging_parent_reasons(parent, core)
        if parent_reasons:
            raise _PrepareAbort(PREPARE_STATUS_PRECHECK_FAILED, "; ".join(parent_reasons))

        _gate("pre_create_staging")
        created = driver.create_staging_root(staging_root=staging_root)
        mutation_performed = True
        _gate("post_create_staging")
        if not isinstance(created, dict):
            raise _PrepareAbort(PREPARE_STATUS_FAILED, "staging creation did not return a locator")
        created_state = _staging_state(
            staging_root, present=True, device=created.get("device"), inode=created.get("inode")
        )
        _journal("APPLYING", absent_state, created_state)

        # ── FETCH_BYTES:只下載 hash-pinned wheels,且不得執行 artifact(§10.5 #33)──
        _gate("pre_fetch")
        fetched = driver.fetch_pinned_artifacts(
            staging_root=staging_root,
            pinned_artifacts=[dict(item) for item in pinned_artifacts],
            fetch_budget=dict(core["fetch_budget"]),
        )
        _gate("post_fetch")
        fetch_reasons, locators = _fetch_reasons(fetched, pinned_artifacts, core["fetch_budget"])
        written_paths.extend(list((fetched or {}).get("written_paths") or []))
        if fetch_reasons:
            raise _PrepareAbort(PREPARE_STATUS_FAILED, "; ".join(fetch_reasons))

        # ── BUILD_AND_IMPORT:無網路/無 credential/無 state;root 不執行 dependency 碼 ──
        _gate("pre_build")
        built = driver.build_and_import(
            staging_root=staging_root, build_budget=dict(core["build_budget"])
        )
        _gate("post_build")
        build_reasons = _build_reasons(built, core["build_budget"])
        written_paths.extend(list((built or {}).get("written_paths") or []))
        if build_reasons:
            raise _PrepareAbort(PREPARE_STATUS_FAILED, "; ".join(build_reasons))
        native_proof = str((built or {}).get("native_import_proof_digest") or "")

        boundary = prepare_publication_boundary_reasons(
            written_paths
        ) + prepare_containment_reasons(written_paths, staging_root)
        if boundary:
            raise _PrepareAbort(PREPARE_STATUS_FAILED, "; ".join(boundary))

        _gate("pre_freeze")
        frozen = driver.freeze_and_rehash_staging(staging_root=staging_root)
        _gate("post_freeze")
        frozen_reasons = _frozen_reasons(frozen, native_proof)
        if frozen_reasons:
            raise _PrepareAbort(PREPARE_STATUS_BUNDLE_INVALID, "; ".join(frozen_reasons))
        frozen_state = _staging_state(
            staging_root, present=True, device=frozen.get("device"), inode=frozen.get("inode")
        )
        _journal("APPLIED", created_state, frozen_state)
        _journal("VERIFYING", frozen_state, frozen_state)
    except _PrepareAbort as abort:
        return _abort_outcome(
            abort.status, abort.reason, committed=committed,
            mutation_performed=mutation_performed, driver=driver, prepare_id=prepare_id,
            staging_root=staging_root, core_digest=core_digest, entries=entries,
            clock=clock, sandbox_digest=sandbox_digest,
        )
    except Exception as error:  # noqa: BLE001 - 任何 driver/journal 逸出都 fail-closed
        return _abort_outcome(
            PREPARE_STATUS_RECOVERY_REQUIRED, f"PREPARE interrupted: {redact_driver_error(error)}",
            committed=committed, mutation_performed=mutation_performed, driver=driver,
            prepare_id=prepare_id, staging_root=staging_root, core_digest=core_digest,
            entries=entries, clock=clock, sandbox_digest=sandbox_digest,
        )

    trusted_time = str(driver.trusted_host_time())
    bundle = build_prepared_install_bundle(
        prepare_id=prepare_id, core=core, locators=locators, frozen=frozen,
        native_import_proof_digest=native_proof, staging_root=staging_root,
        created_at=trusted_time,
    )
    # bundle digest 固定之後才關 journal / 跑 postcheck(§5.1 #2 的次序)。
    try:
        _journal("VERIFIED", _staging_state(staging_root, present=True), _staging_state(
            staging_root, present=True, device=frozen.get("device"), inode=frozen.get("inode")
        ))
    except Exception as error:  # noqa: BLE001
        return _verdict(
            PREPARE_STATUS_RECOVERY_REQUIRED, [f"terminal journal transition failed: {redact_driver_error(error)}"],
            prepare_id=prepare_id, staging_root=staging_root,
            mutation_performed=mutation_performed, driver_engaged=True,
        )
    journal = _build_journal(
        prepare_id=prepare_id, staging_root=staging_root, entries=entries, terminal=True,
        sandbox_contract_digest=sandbox_digest,
    )
    postcheck, postcheck_reasons = _build_postcheck(
        driver=driver, staging_root=staging_root, prepare_id=prepare_id,
        core_digest=core_digest, applier_node=applier_node, clock=clock,
    )
    if postcheck is None or postcheck["status"] != "PASS":
        rollback = _compensate(
            driver=driver, prepare_id=prepare_id, staging_root=staging_root, clock=clock
        )
        return _verdict(
            PREPARE_STATUS_RECOVERY_REQUIRED,
            postcheck_reasons + [
                "PREPARE residue postcheck did not pass; RECOVERY_REQUIRED blocks APPLY"
            ],
            prepare_id=prepare_id, staging_root=staging_root,
            mutation_performed=mutation_performed, driver_engaged=True,
            journal=journal, rollback=rollback, postcheck=postcheck,
        )
    rollback = _rollback_authority(prepare_id=prepare_id, staging_root=staging_root, clock=clock)
    receipt = _build_effect_receipt(
        prepare_id=prepare_id, core=core, core_digest=core_digest, authorization=authorization,
        replay_ledger=replay_ledger, bundle=bundle, journal=journal, postcheck=postcheck,
        rollback=rollback, staging_root=staging_root, frozen=frozen,
        trusted_time=trusted_time, now_dt=now_dt,
        evidence_class=derive_recorded_evidence_class(driver)["recorded_evidence_class"],
        terminal_status="PREPARED",
    )
    central_errors = (
        central_validator.validate_aiml_artifact(bundle)
        + central_validator.validate_aiml_artifact(receipt)
        + central_validator.validate_aiml_artifact(journal)
        + central_validator.validate_aiml_artifact(postcheck)
        + central_validator.validate_aiml_artifact(rollback)
    )
    if central_errors:
        return _verdict(
            PREPARE_STATUS_BUNDLE_INVALID, central_errors,
            prepare_id=prepare_id, staging_root=staging_root,
            mutation_performed=mutation_performed, driver_engaged=True,
            journal=journal, rollback=rollback, postcheck=postcheck,
        )
    return _verdict(
        PREPARE_STATUS_PREPARED, [],
        prepare_id=prepare_id, staging_root=staging_root,
        mutation_performed=mutation_performed, driver_engaged=True,
        prepared_bundle=bundle, effect_receipt=receipt, journal=journal,
        rollback=rollback, postcheck=postcheck,
    )


def _staging_parent_reasons(parent: Any, core: dict[str, Any]) -> list[str]:
    """§5.2:parent 必須 root-owned、非 symlink,且 device/inode 等於被簽 core 的宣稱。"""

    if not isinstance(parent, dict):
        return ["staging parent observation is not an object"]
    reasons: list[str] = []
    declared = core["staging_root_device_inode"]
    if int(parent.get("device", -1)) != int(declared["device"]) or int(
        parent.get("inode", -1)
    ) != int(declared["inode"]):
        reasons.append(
            "staging parent device/inode does not equal the signed core identity "
            "(parent replacement rejected)"
        )
    if parent.get("is_symlink") is not False:
        reasons.append("staging parent is a symlink (PRECHECK_FAILED)")
    if str(parent.get("owner")) != "root":
        reasons.append("staging parent is not root-owned")
    if str(parent.get("mode")) != "0700":
        reasons.append("staging parent mode is not 0700")
    # link_count 只能證明「這是一個目錄」(自身 + ``.`` ≥ 2);每一個既存的
    # ``prepared/<prepare_id>/`` 子目錄都會再 +1,而每一次成功的 PREPARE 依設計都會留下
    # 一個。舊的 ``!= 2`` 因此要求 parent 底下**零**子目錄——任何主機上的第二次 PREPARE
    # 都必然永久失敗(W3 review E3 P2-5)。真正的反替換保證來自 device/inode 綁定 +
    # 非 symlink + root-owned + 0700 四條,不在 link 計數上。
    if int(parent.get("link_count", 0)) < 2:
        reasons.append(
            "staging parent link count is below the minimum for a directory "
            "(the observation is not a directory)"
        )
    return reasons


def _fetch_reasons(
    fetched: Any, pinned_artifacts: list[dict[str, Any]], fetch_budget: dict[str, Any]
) -> tuple[list[str], list[dict[str, Any]]]:
    """FETCH_BYTES 判準:hash-pin 逐一比對、絕不執行 artifact、預算不得超。"""

    if not isinstance(fetched, dict):
        return (["fetch subphase did not return an object"], [])
    reasons: list[str] = []
    if fetched.get("executed_artifacts") is not False:
        reasons.append(
            "the fetch subphase executed or imported a downloaded artifact; FETCH_BYTES "
            "downloads but must never import or execute dependency code (§8.1/§10.5 #33)"
        )
    observed = fetched.get("artifacts")
    if not isinstance(observed, list) or not observed:
        reasons.append("fetch subphase returned no artifact locators")
        return (reasons, [])
    pinned = {str(item.get("locator")): str(item.get("content_digest")) for item in pinned_artifacts}
    if not pinned:
        reasons.append("PREPARE requires a hash-pinned artifact set; none was supplied")
    locators: list[dict[str, Any]] = []
    for entry in observed:
        if not isinstance(entry, dict):
            reasons.append("fetch artifact entry is not an object")
            continue
        locator = str(entry.get("locator"))
        digest = str(entry.get("content_digest"))
        if _DIGEST_RE.fullmatch(digest) is None:
            reasons.append(f"fetched artifact {locator} has an invalid content digest")
            continue
        if pinned.get(locator) != digest:
            reasons.append(
                f"fetched artifact {locator} does not match its pinned hash "
                "(--require-hashes equivalent fail-closed)"
            )
            continue
        locators.append({"locator": locator, "content_digest": digest})
    if len(locators) != len(pinned):
        reasons.append("the fetched artifact set is not exactly the pinned artifact set")
    if int(fetched.get("bytes_fetched", 0)) > int(fetch_budget["max_fetch_bytes"]):
        reasons.append("fetch exceeded its receipt-bound byte budget")
    if int(fetched.get("seconds_elapsed", 0)) > int(fetch_budget["max_fetch_seconds"]):
        reasons.append("fetch exceeded its receipt-bound time budget")
    if len(locators) > int(fetch_budget["max_artifacts"]):
        reasons.append("fetch exceeded its receipt-bound artifact-count budget")
    return (reasons, sorted(locators, key=lambda item: item["locator"]))


def _build_reasons(built: Any, build_budget: dict[str, Any]) -> list[str]:
    """BUILD_AND_IMPORT 判準:四個違規旗標任一為真即失敗;預算不得超。"""

    if not isinstance(built, dict):
        return ["build/import subphase did not return an object"]
    reasons: list[str] = []
    violations = {
        "build_network_access": built.get("network_access"),
        "build_credential_access": built.get("credential_access"),
        "build_state_access": built.get("state_access"),
        "root_executed_dependency_code": built.get("root_executed_dependency_code"),
    }
    for flag in PREPARE_SANDBOX_VIOLATION_FLAGS:
        if violations.get(flag) is not False:
            reasons.append(
                f"PREPARE sandbox violation {flag}: BUILD_AND_IMPORT must have no network, "
                "no credential and no state-directory access, and root must never execute "
                "dependency code (§10.5 #33)"
            )
    proof = built.get("native_import_proof_digest")
    if not isinstance(proof, str) or _DIGEST_RE.fullmatch(proof) is None:
        reasons.append("build/import subphase returned no valid native import proof digest")
    if int(built.get("bytes_written", 0)) > int(build_budget["max_build_bytes"]):
        reasons.append("build/import exceeded its receipt-bound byte budget")
    if int(built.get("seconds_elapsed", 0)) > int(build_budget["max_build_seconds"]):
        reasons.append("build/import exceeded its receipt-bound time budget")
    return reasons


def _frozen_reasons(frozen: Any, native_proof: str | None) -> list[str]:
    """凍結重算判準:root-owned/non-writable + 四個 §8.1 內容身分皆可重算。"""

    if not isinstance(frozen, dict):
        return ["staging freeze/re-hash did not return an object"]
    reasons: list[str] = []
    if frozen.get("root_owned_nonwritable") is not True:
        reasons.append("staging root is not root-owned/non-writable after freeze")
    for field in (
        "base_runtime_tree_manifest_digest",
        "base_runtime_tree_digest",
        "application_bundle_manifest_digest",
        "application_bundle_digest",
        "launch_bundle_manifest_digest",
        "launch_bundle_digest",
    ):
        value = frozen.get(field)
        if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
            reasons.append(f"prepared bundle {field} is missing or malformed")
    distinct = {
        frozen.get("base_runtime_tree_digest"),
        frozen.get("application_bundle_digest"),
        frozen.get("launch_bundle_digest"),
    }
    if len(distinct) != 3:
        reasons.append(
            "the base-runtime, application and launch identities are not three "
            "non-interchangeable digests (§8.1)"
        )
    if not isinstance(native_proof, str) or _DIGEST_RE.fullmatch(native_proof) is None:
        reasons.append("prepared bundle native_import_proof_digest is missing")
    return reasons


def build_prepared_install_bundle(
    *,
    prepare_id: str,
    core: dict[str, Any],
    locators: list[dict[str, Any]],
    frozen: dict[str, Any],
    native_import_proof_digest: Any,
    staging_root: str,
    created_at: str,
    ttl_seconds: int = PREPARE_EVIDENCE_TTL_SECONDS,
) -> dict[str, Any]:
    """``s2_4_prepared_install_bundle_v1``:不可變 locator + 四身分 + staging locator + 到期。"""

    at = central_validator._parse_timestamp(created_at)
    bundle = {
        "schema_version": "s2_4_prepared_install_bundle_v1",
        "prepare_id": prepare_id,
        "artifact_locators": [dict(item) for item in locators],
        "base_runtime_tree_manifest_digest": frozen["base_runtime_tree_manifest_digest"],
        "base_runtime_tree_digest": frozen["base_runtime_tree_digest"],
        "application_bundle_manifest_digest": frozen["application_bundle_manifest_digest"],
        "application_bundle_digest": frozen["application_bundle_digest"],
        "launch_bundle_manifest_digest": frozen["launch_bundle_manifest_digest"],
        "launch_bundle_digest": frozen["launch_bundle_digest"],
        "native_import_proof_digest": str(native_import_proof_digest),
        "staging_locator": {
            "staging_root": staging_root,
            "device": int(frozen.get("device", 0)),
            "inode": int(frozen.get("inode", 0)),
        },
        "staging_root_owned_nonwritable": bool(frozen.get("root_owned_nonwritable")),
        "source_head": core["source_head"],
        "target_host": core["target_host"],
        "created_at": _iso(at),
        "expires_at": _iso(at + timedelta(seconds=int(ttl_seconds))),
    }
    bundle["self_digest"] = artifact_self_digest(bundle)
    return bundle


def _build_journal(
    *,
    prepare_id: str,
    staging_root: str,
    entries: list[dict[str, Any]],
    terminal: bool,
    sandbox_contract_digest: str,
) -> dict[str, Any] | None:
    if not entries:
        return None
    journal = {
        "schema_version": "s2_4_prepare_journal_v1",
        "prepare_id": prepare_id,
        "staging_root": staging_root,
        "entries": [dict(entry) for entry in entries],
        "terminal": bool(terminal),
        "journal_integrity": {
            # §5.2:PREPARING 於**建立 staging 目錄之前**記錄並 fsync(本葉的固定呼叫次序)。
            "preparing_fsynced_before_staging_create": True,
            "same_filesystem_atomic_rename": True,
            "file_fsynced": True,
            "parent_dir_fsynced": True,
        },
    }
    # outer_checksum 先於 self_digest(同 probe journal 的 inner/outer 兩道完整性面)。
    journal["outer_checksum"] = canonical_digest(
        {"journal": journal, "sandbox_contract_digest": sandbox_contract_digest}
    )
    journal["self_digest"] = artifact_self_digest(journal)
    return journal


def _build_postcheck(
    *,
    driver: Any,
    staging_root: str,
    prepare_id: str,
    core_digest: str,
    applier_node: str,
    clock: Callable[[], datetime],
) -> tuple[dict[str, Any] | None, list[str]]:
    """相異 verifier 節點的獨立殘留 postcheck(applier 不得自證)。"""

    try:
        observed = driver.independent_residue_postcheck(
            staging_root=staging_root, prepare_id=prepare_id, prepare_core_digest=core_digest
        )
    except Exception as error:  # noqa: BLE001
        return None, [f"independent prepare residue postcheck failed: {redact_driver_error(error)}"]
    if not isinstance(observed, dict):
        return None, ["independent prepare residue postcheck did not return an object"]
    verifier_node = str(observed.get("verifier_node", ""))
    if not verifier_node or verifier_node == applier_node:
        return None, ["independent prepare postcheck verifier_node must differ from the applier"]
    for field in ("residue_scan_digest", "verifier_capture_digest"):
        value = observed.get(field)
        if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
            return None, [f"independent prepare postcheck {field} is invalid"]
    at = clock()
    flags = {
        "zero_residue_outside_staging": bool(observed.get("zero_residue_outside_staging")),
        "staging_root_owned_nonwritable": bool(observed.get("staging_root_owned_nonwritable")),
    }
    postcheck = {
        "schema_version": "s2_4_prepare_postcheck_v1",
        "status": "PASS" if all(flags.values()) else "FAIL",
        "prepare_id": prepare_id,
        "prepare_core_digest": core_digest,
        "verifier_node": verifier_node,
        "applier_node": applier_node,
        **flags,
        "residue_scan_digest": observed["residue_scan_digest"],
        "verifier_capture_digest": observed["verifier_capture_digest"],
        "observed_at": _iso(at),
        "expires_at": _iso(at + timedelta(seconds=PREPARE_EVIDENCE_TTL_SECONDS)),
    }
    postcheck["self_digest"] = artifact_self_digest(postcheck)
    return postcheck, ([] if postcheck["status"] == "PASS" else ["prepare residue postcheck FAILED"])


def _rollback_authority(
    *, prepare_id: str, staging_root: str, clock: Callable[[], datetime]
) -> dict[str, Any]:
    """成功路徑的 rollback 契約:staging 仍在(APPLY 要用),故 NOT_CLEANED 是誠實值。

    其被簽 digest 是「即使 apply 授權過期,仍可補償這一份 staging delta」的權威(§5.1)。
    """

    at = clock()
    rollback = {
        "schema_version": "s2_4_prepare_rollback_v1",
        "status": "NOT_CLEANED",
        "prepare_id": prepare_id,
        "staging_root": staging_root,
        "pre_state_digest": _staging_state(staging_root, present=False),
        "post_state_digest": _staging_state(staging_root, present=True),
        "task_owned_only": True,
        "staging_delta_removed": False,
        "staging_absent": False,
        "observed_at": _iso(at),
        "expires_at": _iso(at + timedelta(seconds=PREPARE_EVIDENCE_TTL_SECONDS)),
    }
    rollback["self_digest"] = artifact_self_digest(rollback)
    return rollback


def _compensate(
    *, driver: Any, prepare_id: str, staging_root: str, clock: Callable[[], datetime]
) -> dict[str, Any]:
    """只補償本 journal 的 task-owned staging delta(無 age-scan、無 cleanup 捷徑)。"""

    observed: dict[str, Any] = {}
    try:
        result = driver.compensate_staging(staging_root=staging_root)
        if isinstance(result, dict):
            observed = result
    except Exception:  # noqa: BLE001 - 補償失敗即 NOT_CLEANED
        observed = {}
    at = clock()
    cleaned = bool(
        observed.get("task_owned_only")
        and observed.get("staging_delta_removed")
        and observed.get("staging_absent")
    )
    rollback = {
        "schema_version": "s2_4_prepare_rollback_v1",
        "status": "CLEANED_EXACT" if cleaned else "NOT_CLEANED",
        "prepare_id": prepare_id,
        "staging_root": staging_root,
        "pre_state_digest": _staging_state(staging_root, present=True),
        "post_state_digest": _staging_state(staging_root, present=not cleaned),
        "task_owned_only": bool(observed.get("task_owned_only")),
        "staging_delta_removed": bool(observed.get("staging_delta_removed")),
        "staging_absent": bool(observed.get("staging_absent")),
        "observed_at": _iso(at),
        "expires_at": _iso(at + timedelta(seconds=PREPARE_EVIDENCE_TTL_SECONDS)),
    }
    rollback["self_digest"] = artifact_self_digest(rollback)
    return rollback


def _build_effect_receipt(
    *,
    prepare_id: str,
    core: dict[str, Any],
    core_digest: str,
    authorization: dict[str, Any],
    replay_ledger: dict[str, Any],
    bundle: dict[str, Any],
    journal: dict[str, Any] | None,
    postcheck: dict[str, Any],
    rollback: dict[str, Any],
    staging_root: str,
    frozen: dict[str, Any],
    trusted_time: str,
    now_dt: datetime,
    evidence_class: str,
    terminal_status: str,
) -> dict[str, Any]:
    """終端 receipt:綁 intent/授權/bundle/journal/replay/postcheck/rollback(bundle 不反綁 receipt)。"""

    at = central_validator._parse_timestamp(trusted_time)
    consumed_entry = canonical_digest({
        "authorization_id": authorization["authorization_id"],
        "authorization_digest": authorization["self_digest"],
        "profile_identity": authorization["profile_identity"],
        "ledger_path": replay_ledger.get("ledger_path"),
        "ledger_head_entry_digest": (
            replay_ledger["entries"][-1]["entry_digest"] if replay_ledger.get("entries") else None
        ),
    })
    receipt = {
        "schema_version": "s2_4_prepare_effect_receipt_v1",
        "prepare_id": prepare_id,
        "prepare_core_digest": core_digest,
        "authorization_id": authorization["authorization_id"],
        "authorization_digest": authorization["self_digest"],
        "prepared_install_bundle_digest": bundle["self_digest"],
        "staging_locator": {
            "staging_root": staging_root,
            "device": int(frozen.get("device", 0)),
            "inode": int(frozen.get("inode", 0)),
        },
        "journal_digest": journal["self_digest"] if journal else canonical_digest(None),
        "consumed_replay_entry_digest": consumed_entry,
        "postcheck_digest": postcheck["self_digest"],
        "rollback_digest": rollback["self_digest"],
        "terminal_status": terminal_status,
        "evidence_class": (
            evidence_class
            if evidence_class in {"PLATFORM_ATTESTED", "PLATFORM_OR_EXTERNAL_ATTESTED", "STRUCTURAL_ONLY"}
            else "STRUCTURAL_ONLY"
        ),
        "source_head": core["source_head"],
        "target_host": core["target_host"],
        "trusted_host_time": _iso(at),
        "observed_at": _iso(now_dt),
        "expires_at": _iso(at + timedelta(seconds=PREPARE_EVIDENCE_TTL_SECONDS)),
        "production_authority_flags": dict(_ALL_FALSE_PRODUCTION_FLAGS),
    }
    receipt["self_digest"] = artifact_self_digest(receipt)
    return receipt


def _abort_outcome(
    status: str,
    reason: str,
    *,
    committed: bool,
    mutation_performed: bool,
    driver: Any,
    prepare_id: str,
    staging_root: str,
    core_digest: str,
    entries: list[dict[str, Any]],
    clock: Callable[[], datetime],
    sandbox_digest: str,
) -> dict[str, Any]:
    """PREPARING 之前中止 = 零變更 typed 失敗;之後中止 = 只補償 task-owned staging delta。"""

    if not committed:
        return _verdict(
            status, [reason, "no staging directory was created; zero mutation"],
            prepare_id=prepare_id, staging_root=staging_root, driver_engaged=True,
        )
    rollback = _compensate(
        driver=driver, prepare_id=prepare_id, staging_root=staging_root, clock=clock
    )
    try:
        entry = {
            "seq": len(entries),
            "state": "COMPENSATED" if rollback["status"] == "CLEANED_EXACT" else "FAILED",
            "pre_state_digest": _staging_state(staging_root, present=True),
            "post_state_digest": _staging_state(
                staging_root, present=rollback["status"] != "CLEANED_EXACT"
            ),
            "fsynced": True,
            "recorded_at": _iso(clock()),
        }
        driver.journal_transition(entry=entry)
        entries.append(entry)
    except Exception as error:  # noqa: BLE001
        reason = f"{reason}; compensation journal transition failed: {redact_driver_error(error)}"
    journal = _build_journal(
        prepare_id=prepare_id, staging_root=staging_root, entries=entries, terminal=False,
        sandbox_contract_digest=sandbox_digest,
    )
    reasons = [reason]
    if rollback["status"] != "CLEANED_EXACT":
        reasons.append(
            "the task-owned staging delta was not exactly compensated; "
            "RECOVERY_REQUIRED blocks APPLY"
        )
        status = PREPARE_STATUS_RECOVERY_REQUIRED
    return _verdict(
        status, reasons, prepare_id=prepare_id, staging_root=staging_root,
        mutation_performed=mutation_performed, driver_engaged=True,
        journal=journal, rollback=rollback,
    )


# --------------------------------------------------------------------------- #
# 消費者側:APPLY 對 PREPARE lineage 的再導出(§5.1 #3 / §6 step 5)。
# --------------------------------------------------------------------------- #
def derive_prepared_bundle_status(
    bundle: Any,
    effect_receipt: Any,
    *,
    now: str | datetime | None = None,
    expected_source_head: str | None = None,
    expected_target_host: str | None = None,
) -> dict[str, Any]:
    """APPLY 端:這份 prepared bundle 現在還能不能用?任一縫即 ``PREPARED_BUNDLE_INVALID``。"""

    reasons: list[str] = []
    if not isinstance(bundle, dict) or not isinstance(effect_receipt, dict):
        return {
            "status": PREPARE_STATUS_BUNDLE_INVALID,
            "reasons": ["prepared bundle and prepare effect receipt must both be objects"],
        }
    if bundle.get("schema_version") != "s2_4_prepared_install_bundle_v1":
        reasons.append("prepared bundle schema_version is not s2_4_prepared_install_bundle_v1")
    if effect_receipt.get("schema_version") != "s2_4_prepare_effect_receipt_v1":
        reasons.append("prepare effect receipt schema_version is not s2_4_prepare_effect_receipt_v1")
    if reasons:
        return {"status": PREPARE_STATUS_BUNDLE_INVALID, "reasons": reasons}
    if bundle.get("self_digest") != artifact_self_digest(bundle):
        reasons.append("prepared bundle self_digest is invalid")
    if effect_receipt.get("self_digest") != artifact_self_digest(effect_receipt):
        reasons.append("prepare effect receipt self_digest is invalid")
    if effect_receipt.get("prepared_install_bundle_digest") != bundle.get("self_digest"):
        reasons.append(
            "the prepare effect receipt does not bind this prepared bundle "
            "(a bundle without its terminal receipt is unusable)"
        )
    if effect_receipt.get("prepare_id") != bundle.get("prepare_id"):
        reasons.append("prepared bundle and prepare receipt bind different prepare identities")
    if effect_receipt.get("terminal_status") != "PREPARED":
        reasons.append(
            "the prepare receipt is not terminal PREPARED; a non-terminal or changed PREPARE "
            "lineage cannot authorize APPLY"
        )
    if bundle.get("staging_root_owned_nonwritable") is not True:
        reasons.append("prepared staging is not root-owned/non-writable")
    staging_root = str((bundle.get("staging_locator") or {}).get("staging_root"))
    try:
        if staging_root != prepared_staging_root(bundle.get("prepare_id")):
            reasons.append("prepared staging root is not the id-derived task-owned staging path")
    except PrepareContractError:
        reasons.append("prepared bundle prepare_id is malformed")
    receipt_locator = effect_receipt.get("staging_locator") or {}
    if receipt_locator != (bundle.get("staging_locator") or {}):
        reasons.append(
            "prepare receipt and bundle staging locators differ (cross-device or changed staging)"
        )
    if expected_source_head is not None and bundle.get("source_head") != expected_source_head:
        reasons.append("prepared bundle source_head does not match the APPLY plan source head")
    if expected_target_host is not None and bundle.get("target_host") != expected_target_host:
        reasons.append("prepared bundle target_host does not match the APPLY target host")
    now_text = central_validator._now_text(now)
    if now_text is not None:
        try:
            current = central_validator._parse_timestamp(now_text)
            for label, artifact in (("prepared bundle", bundle), ("prepare receipt", effect_receipt)):
                if current >= central_validator._parse_timestamp(artifact["expires_at"]):
                    reasons.append(
                        f"{label} is expired; rerun PREPARE (refresh-by-reference is forbidden)"
                    )
        except (KeyError, TypeError, ValueError):
            reasons.append("prepared bundle/receipt timestamps are invalid")
    return {
        "status": "PREPARED_BUNDLE_VALID" if not reasons else PREPARE_STATUS_BUNDLE_INVALID,
        "reasons": sorted(set(reasons)),
    }


# 供 W3 wave-exit exported-ABI 折入的 code-owned 探針欄位(與真 repo/runtime 無關)。
_ABI_PREPARE_MIRROR_ALLOWLIST = ("203.0.113.0/24",)


def prepare_abi_projection() -> dict[str, Any]:
    """W3 exported-ABI 的 PREPARE 面(code-owned 骨架 + sandbox 契約 digest 的活再導出)。"""

    try:
        sandbox_digest = prepare_sandbox_contract_digest(
            artifact_mirror_allowlist=list(_ABI_PREPARE_MIRROR_ALLOWLIST)
        )
    except Exception:  # noqa: BLE001 - 任何逸出 = fail-closed 未證
        sandbox_digest = None
    return {
        "prepare_driver_entrypoint": (
            "agent_governance_s2_4_prepare.prepare_s2_4_install_bundle(intent, authorization, driver)"
        ),
        "prepare_driver_protocol": "agent_governance_s2_4_prepare.PrepareDriver",
        "prepare_route_class": PREPARE_ROUTE_CLASS,
        "prepare_typed_statuses": list(PREPARE_TYPED_STATUSES),
        "prepare_route_surface_contract_digest": canonical_digest(prepare_route_surface_contract()),
        "prepare_sandbox_contract_digest": sandbox_digest,
        "prepare_staging_parent": PREPARE_STAGING_PARENT,
        "prepare_publication_deny_roots": list(PREPARE_PUBLICATION_DENY_ROOTS),
        "prepare_raw_ingress_keys": list(PREPARE_RAW_INGRESS_KEYS),
        "prepared_bundle_consumer_predicate": (
            "agent_governance_s2_4_prepare.derive_prepared_bundle_status"
        ),
        # §10.5 #33:路徑圍堵在比對之前正規化,``..`` 節段一律外拒(活再導出)。
        "path_normalizer": "agent_governance_s2_4_prepare.normalize_prepare_path",
        "traversal_segment_rejected": normalize_prepare_path(
            PREPARE_STAGING_PARENT + "/x/../../../../opt/arcane-equilibrium/aiml/runtimes/z"
        ) is None,
        "traversal_escape_reason_count": len(
            prepare_publication_boundary_reasons([
                PREPARE_STAGING_PARENT + "/x/../../../../opt/arcane-equilibrium/aiml/runtimes/z"
            ])
        ),
        "containment_predicate": "agent_governance_s2_4_prepare.prepare_containment_reasons",
        # §5.2:parent 的 link-count 契約只證「是目錄」;每一次成功 PREPARE 都會留下一個
        # ``prepared/<prepare_id>/`` 子目錄,故第二次 PREPARE 必須可通過。
        "staging_parent_minimum_link_count": 2,
        "second_prepare_on_the_same_host_is_satisfiable": not _staging_parent_reasons(
            {
                "device": 1, "inode": 2, "is_symlink": False, "owner": "root",
                "mode": "0700", "link_count": 3,
            },
            {"staging_root_device_inode": {"device": 1, "inode": 2}},
        ),
        "schema_ids": [
            "s2_4_prepare_core_v1",
            "s2_4_prepare_effect_receipt_v1",
            "s2_4_prepare_intent_v1",
            "s2_4_prepare_journal_v1",
            "s2_4_prepare_postcheck_v1",
            "s2_4_prepare_rollback_v1",
            "s2_4_prepared_install_bundle_v1",
        ],
    }
