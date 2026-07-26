#!/usr/bin/env python3
"""S2.4(WP4·W3a)typed host capability-probe 葉(§8.3 兩 scope + §10.5 #36/#38/#39)。

由 install 模組 2000 行帽拆出的 W3a 面;install 上層逐名 re-export,消費者匯入面不變。
本葉提供 §10.2 凍結 ABI 的 ``run_s2_4_capability_probe(intent, authorization, driver)``:

- **source lane 零 effect**:``driver=None``(Mac/源碼/測試)一律回 typed
  ``EXTERNAL_VERIFICATION_PENDING`` 且 ``mutation_performed=False``——鏡 S2.0
  ``apply_observer_bootstrap`` 的 reachable-but-authority-locked 姿態;真主機動作全部
  經**注入的** :class:`CapabilityProbeDriver`(真 driver 屬 W3b/W6A,本葉不含);
- **兩個不可互換 scope**(§8.3 表):``PREPARE_SANDBOX`` 綁 host/systemd/cgroup 版本 +
  固定 FETCH/BUILD sandbox 屬性 digest + 實測 egress/deny;``INSTALLED_UNIT`` 綁
  host/systemd/cgroup 版本 + **W2c renderer 的 exact rendered-unit digest** + 實測
  loopback allow/deny。scope 替換在三層皆拒:schema const(core/intent/attestation/
  receipt/journal 的 enum)、core 導出(property digest 隨 scope 變 → probe_id 變)、
  receipt 綁定(:func:`derive_scoped_capability_attestation_status`);
- **final-unit attestation 永非 W6A 前置**(§8.3「no output-derived admission cycle」):
  :data:`W6A_PREREQUISITE_PROBE_SCOPES` 只含 ``PREPARE_SANDBOX``;
- **failure/ambiguous cleanup → ``RECOVERY_REQUIRED``** 並閂住 :class:`ProbeRecoveryState`,
  在 recovery 未解前**不得**起新 probe(§10.5 #39);
- **授權過期只剩 cleanup 權限**:過期後不再建立/觀測,但 stop→drain→reset-failed→remove
  的安全清理照跑(§5.2 / rollback schema 明文)。

誠實界線:本葉「不」認證任何 runtime——九 authority / production_apply_performed /
running_attested 恆 false;帶真 driver 的 TERMINAL_CLEAN 也只是 receipt 證據,真 EFFECT
(signed core / WAL / install lock / replay 消費落盤)屬 W4/W6A/W6B。
"""
from __future__ import annotations

import hashlib
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
import agent_governance_s2_4_render as _render  # noqa: E402

canonical_digest = central_validator.canonical_digest
artifact_self_digest = central_validator.artifact_self_digest
# §7/§10.5 #15:driver 例外紅字化與可序列化面秘密掃描的共用來源(component 葉)。
redact_driver_error = _component.redact_driver_error
scan_serializable_surface = _component.scan_serializable_surface
derive_recorded_evidence_class = _component.derive_recorded_evidence_class


def _recordable_evidence_class(declared: Any) -> str:
    """把任何傳入的 evidence_class 收斂成 W3 唯一可記錄的等級(E2 P2-B)。

    `derive_recorded_evidence_class` 只守住 governed entry point;但 attestation/receipt
    builder 是 public 且被 install 模組再匯出的,直接呼叫它們可以繞過那道閘,而
    `derive_scoped_capability_attestation_status` 不看 evidence_class——於是一份「直接
    建出來的 attested attestation」仍能充當 W6A/W6B 前置。這裡讓兩個 builder 走同一道
    拒絕:W3 沒有 trusted-host attestation 驗證面,任何 attested 等級一律降為
    STRUCTURAL_ONLY,因此**合法的 W3 artifact 永不帶 attested 等級**——消費側便可據此
    把帶 attested 的 artifact 判為偽造(見 derive_scoped_capability_attestation_status)。
    """

    value = str(declared)
    if value in _component.EVIDENCE_CLASS_ATTESTED:
        return _component.EVIDENCE_CLASS_STRUCTURAL_ONLY
    if value != _component.EVIDENCE_CLASS_STRUCTURAL_ONLY:
        return _component.EVIDENCE_CLASS_STRUCTURAL_ONLY
    return value

# ── §8.3 / §9.1 code-owned 契約常量 ──────────────────────────────────────────────
PROBE_SCOPES = ("PREPARE_SANDBOX", "INSTALLED_UNIT")
PROBE_ROUTE_CLASS = "s2_4_capability_probe_intent"
PROBE_REQUIRED_EFFECT_CLASS = "HOST_CAPABILITY_PROBE"
PROBE_SERVICE_SURFACE = "transient_probe_only"
PROBE_AUTHORIZATION_PROFILE = "aiml-s2-capability-probe-operator-v1"
PROBE_SIGNATURE_NAMESPACE = "arcane-equilibrium-aiml-s2-capability-probe"
PROBE_UNIT_NAME_PREFIX = "arcane-aiml-s2-4-probe-"
PROBE_UNIT_NAME_SUFFIX = ".service"
PROBE_ID_PREFIX = "s2-4-probe-"
# systemd InvocationID 恆為 32 位小寫十六進位(journal 的 expected pattern)。
PROBE_INVOCATION_ID_PATTERN = "^[0-9a-f]{32}$"
# probe 證據新鮮度:§9.1 全域 15 分鐘保守上限(真 per-probe 更緊預算屬 W6 收緊)。
PROBE_EVIDENCE_TTL_SECONDS = 900
PROBE_ATTESTED_EVIDENCE_CLASS = "PLATFORM_ATTESTED"
# §8.3:probe intent 十個 forbidden surface(schema 已 const false;此處為再導出面)。
PROBE_FORBIDDEN_SURFACES = (
    "broker_or_order",
    "credential_install",
    "daemon_reload",
    "host_identity",
    "migration",
    "persistent_unit_enable",
    "persistent_unit_start",
    "persistent_unit_write",
    "pg",
    "secret",
)
# §8.3:W6A 只需 PREPARE_SANDBOX;final-unit attestation 永不是 W6A 前置(無 output-derived
# admission cycle)。W6B 才同時需要兩個 scope。
W6A_PREREQUISITE_PROBE_SCOPES = ("PREPARE_SANDBOX",)
W6B_PREREQUISITE_PROBE_SCOPES = ("PREPARE_SANDBOX", "INSTALLED_UNIT")

# ── typed 終端狀態(§10.2;無別名可把其一變成 success)──────────────────────────
PROBE_STATUS_TERMINAL_CLEAN = "TERMINAL_CLEAN"
PROBE_STATUS_TERMINAL_FAILED = "TERMINAL_FAILED"
PROBE_STATUS_RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
PROBE_STATUS_PENDING = "EXTERNAL_VERIFICATION_PENDING"
PROBE_STATUS_AUTHORIZATION_REJECTED = "AUTHORIZATION_REJECTED"
PROBE_STATUS_REQUEST_REJECTED = "PROBE_REQUEST_REJECTED"
PROBE_STATUS_CAPABILITY_UNSATISFIED = "HOST_NETWORK_SANDBOX_CAPABILITY_UNSATISFIED"
PROBE_TYPED_STATUSES = (
    PROBE_STATUS_AUTHORIZATION_REJECTED,
    PROBE_STATUS_CAPABILITY_UNSATISFIED,
    PROBE_STATUS_PENDING,
    PROBE_STATUS_RECOVERY_REQUIRED,
    PROBE_STATUS_REQUEST_REJECTED,
    PROBE_STATUS_TERMINAL_CLEAN,
    PROBE_STATUS_TERMINAL_FAILED,
)

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_HEAD_RE = re.compile(r"^[0-9a-f]{40}$")
_CIDR_RE = re.compile(r"^[0-9a-fA-F:.]{2,45}/\d{1,3}$")
_ALL_FALSE_PRODUCTION_FLAGS = {
    "nine_authorities_false": True,
    "production_apply_performed": False,
    "running_attested": False,
}


class ProbeContractError(ValueError):
    """probe 契約層硬錯誤(scope/輸入不合法;帶 typed ``code``)。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# --------------------------------------------------------------------------- #
# §8.3 兩 scope 的 transient-unit 屬性集(property digest 即 scope 的內容身分)。
#
# PREPARE_SANDBOX:§8.1 的 FETCH_BYTES / BUILD_AND_IMPORT 兩個 sandbox 子相——fetch 走
# 封閉 artifact-mirror allowlist(可下載、不得 import/執行),build/import 完全無網路、
# 無 credential/state 目錄。兩者的屬性表在此 code-owned 凍結,mirror allowlist 由 caller
# 顯式供給(它是被 attest 的屬性之一,不是隱含預設)。
#
# INSTALLED_UNIT:**不**另抄一份 §8.3 常量,而是自 W2c renderer 的 canonical rendered
# unit 直接抽取 sandbox/network 設定——unit 渲染面漂移必然改變 probe property digest。
# --------------------------------------------------------------------------- #
PREPARE_SANDBOX_FETCH_PROPERTIES = {
    "AmbientCapabilities": "",
    "CapabilityBoundingSet": "",
    "DynamicUser": "yes",
    "IPAddressDeny": "any",
    "LockPersonality": "yes",
    "MemoryMax": "512M",
    "NoNewPrivileges": "yes",
    "PrivateDevices": "yes",
    "PrivateTmp": "yes",
    "ProtectClock": "yes",
    "ProtectControlGroups": "yes",
    "ProtectHome": "yes",
    "ProtectKernelModules": "yes",
    "ProtectKernelTunables": "yes",
    "ProtectSystem": "strict",
    "RestrictAddressFamilies": "AF_INET AF_INET6",
    "RestrictRealtime": "yes",
    "RestrictSUIDSGID": "yes",
    "RuntimeMaxSec": "300",
    "SupplementaryGroups": "",
    "SystemCallArchitectures": "native",
    "TasksMax": "32",
    "UMask": "0077",
}
PREPARE_SANDBOX_BUILD_PROPERTIES = {
    "AmbientCapabilities": "",
    "CapabilityBoundingSet": "",
    "DynamicUser": "yes",
    "IPAddressDeny": "any",
    "LockPersonality": "yes",
    "MemoryMax": "2G",
    "NoNewPrivileges": "yes",
    "PrivateDevices": "yes",
    "PrivateNetwork": "yes",
    "PrivateTmp": "yes",
    "ProtectClock": "yes",
    "ProtectControlGroups": "yes",
    "ProtectHome": "yes",
    "ProtectKernelModules": "yes",
    "ProtectKernelTunables": "yes",
    "ProtectSystem": "strict",
    "RestrictAddressFamilies": "AF_UNIX",
    "RestrictRealtime": "yes",
    "RestrictSUIDSGID": "yes",
    "RuntimeMaxSec": "600",
    "SupplementaryGroups": "",
    "SystemCallArchitectures": "native",
    "TasksMax": "64",
    "UMask": "0077",
}
# §8.3 rendered unit 中屬於 sandbox/network 面的設定鍵(INSTALLED_UNIT probe 必須逐一抽到)。
INSTALLED_UNIT_SANDBOX_KEYS = (
    "AmbientCapabilities",
    "CapabilityBoundingSet",
    "IPAddressAllow",
    "IPAddressDeny",
    "LimitCORE",
    "LockPersonality",
    "MemoryMax",
    "NoNewPrivileges",
    "PrivateDevices",
    "PrivateTmp",
    "ProtectClock",
    "ProtectControlGroups",
    "ProtectHome",
    "ProtectKernelModules",
    "ProtectKernelTunables",
    "ProtectSystem",
    "RestrictAddressFamilies",
    "RestrictRealtime",
    "RestrictSUIDSGID",
    "SystemCallArchitectures",
    "TasksMax",
    "UMask",
)


def prepare_sandbox_property_set(*, artifact_mirror_allowlist: Any) -> dict[str, Any]:
    """PREPARE_SANDBOX 的固定 FETCH/BUILD sandbox 屬性集(§8.1;mirror allowlist 顯式綁入)。"""

    allowlist = list(artifact_mirror_allowlist or [])
    if not allowlist or any(
        not isinstance(entry, str) or _CIDR_RE.fullmatch(entry) is None for entry in allowlist
    ):
        raise ProbeContractError("prepare_sandbox_mirror_allowlist_invalid")
    fetch = dict(PREPARE_SANDBOX_FETCH_PROPERTIES)
    fetch["IPAddressAllow"] = " ".join(sorted(set(allowlist)))
    return {
        "scope": "PREPARE_SANDBOX",
        "fetch_bytes": fetch,
        "build_and_import": dict(PREPARE_SANDBOX_BUILD_PROPERTIES),
    }


def installed_unit_property_set(rendered_unit: Any) -> dict[str, Any]:
    """INSTALLED_UNIT 的屬性集:exact rendered-unit digest + 自該 unit 抽出的 sandbox 設定。

    rendered unit 必須先通過 W2c 的 :func:`derive_rendered_unit_status`(§10.5 #22),
    故一份被削弱/夾帶 drop-in 的 unit 在此就 fail-closed,不可能換到 probe 屬性 digest。
    """

    if not isinstance(rendered_unit, str) or not rendered_unit:
        raise ProbeContractError("installed_unit_rendered_unit_invalid")
    verdict = _render.derive_rendered_unit_status(rendered_unit)
    if verdict["status"] != "PASS":
        raise ProbeContractError("installed_unit_rendered_unit_rejected")
    # 同一 governed 家族內共用 renderer 的解析點(install 亦以同姿態 re-export sql_scan 私名);
    # 另抄一份 unit 解析器會製造第二個真理來源。
    entries, parse_reasons = _render._parse_unit_entries(rendered_unit)
    if parse_reasons:
        raise ProbeContractError("installed_unit_rendered_unit_unparsable")
    collected: dict[str, list[str]] = {}
    for section, key, value in entries:
        if section == "Service" and key in INSTALLED_UNIT_SANDBOX_KEYS:
            collected.setdefault(key, []).append(value)
    if any(len(collected.get(key, [])) != 1 for key in INSTALLED_UNIT_SANDBOX_KEYS):
        raise ProbeContractError("installed_unit_sandbox_properties_incomplete")
    return {
        "scope": "INSTALLED_UNIT",
        "unit_name": _render.UNIT_NAME,
        "rendered_unit_digest": (
            "sha256:" + hashlib.sha256(rendered_unit.encode("utf-8")).hexdigest()
        ),
        "sandbox_properties": {key: collected[key][0] for key in INSTALLED_UNIT_SANDBOX_KEYS},
    }


def capability_probe_property_set(
    scope: Any,
    *,
    rendered_unit: Any = None,
    artifact_mirror_allowlist: Any = None,
) -> dict[str, Any]:
    """依 scope 導出屬性集;跨 scope 的輸入夾帶一律 typed 拒(scope 替換的第一道閘)。"""

    if scope == "PREPARE_SANDBOX":
        if rendered_unit is not None:
            raise ProbeContractError("prepare_sandbox_scope_rejects_rendered_unit")
        return prepare_sandbox_property_set(artifact_mirror_allowlist=artifact_mirror_allowlist)
    if scope == "INSTALLED_UNIT":
        if artifact_mirror_allowlist is not None:
            raise ProbeContractError("installed_unit_scope_rejects_mirror_allowlist")
        return installed_unit_property_set(rendered_unit)
    raise ProbeContractError("unknown_probe_scope")


def capability_probe_property_digest(scope: Any, **scope_inputs: Any) -> str:
    """scope 專屬 transient-unit 屬性集的 canonical digest(core 的被簽欄位)。"""

    return canonical_digest(capability_probe_property_set(scope, **scope_inputs))


def capability_probe_cleanup_contract(
    *, probe_id: str, derived_unit_name: str, cleanup_budget: dict[str, Any]
) -> dict[str, Any]:
    """§5.2:第一次 D-Bus 呼叫**之前**即寫入 WAL 的 cleanup 授權契約(stop→drain→reset→remove)。"""

    return {
        "schema_version": "s2_4_capability_probe_cleanup_contract_v1_informal",
        "probe_id": probe_id,
        "derived_unit_name": derived_unit_name,
        "operations": [
            "transient_unit_stop",
            "bounded_cgroup_drain",
            "reset_failed",
            "transient_unit_remove",
        ],
        "cleanup_budget": dict(cleanup_budget),
    }


# --------------------------------------------------------------------------- #
# core / intent 建構與再導出(§5.1 PREPARE->sign->APPLY 的 unsigned core)。
# --------------------------------------------------------------------------- #
def build_capability_probe_core(
    *,
    scope: str,
    host: str,
    cgroup_manager_scope: str,
    cgroup_root_pattern: str,
    source_head: str,
    target_host: str,
    created_at: str,
    max_cleanup_seconds: int,
    max_cgroup_drain_seconds: int,
    rendered_unit: Any = None,
    artifact_mirror_allowlist: Any = None,
) -> dict[str, Any]:
    """由 scope 專屬屬性 digest 組出 unsigned probe core(不含 probe_id/授權/self_digest)。"""

    if not _HEAD_RE.fullmatch(str(source_head)):
        raise ProbeContractError("probe_core_source_head_invalid")
    return {
        "schema_version": "s2_4_capability_probe_core_v1",
        "probe_scope": scope,
        "transient_unit_property_digest": capability_probe_property_digest(
            scope,
            rendered_unit=rendered_unit,
            artifact_mirror_allowlist=artifact_mirror_allowlist,
        ),
        "host_cgroup_identity": {
            "host": host,
            "cgroup_manager_scope": cgroup_manager_scope,
            "cgroup_root_pattern": cgroup_root_pattern,
        },
        "cleanup_budget": {
            "max_cleanup_seconds": int(max_cleanup_seconds),
            "max_cgroup_drain_seconds": int(max_cgroup_drain_seconds),
        },
        "source_head": source_head,
        "target_host": target_host,
        "created_at": created_at,
    }


def probe_id_for_core(core: dict[str, Any]) -> str:
    """``probe_id = 's2-4-probe-' + hex(canonical_digest(core))``(§5.1 導出身分)。"""

    return PROBE_ID_PREFIX + canonical_digest(core).split(":", 1)[1]


def derived_probe_unit_name(probe_id: str) -> str:
    """``arcane-aiml-s2-4-probe-<64hex>.service``——task-bound transient unit 的唯一名。"""

    if not isinstance(probe_id, str) or not probe_id.startswith(PROBE_ID_PREFIX):
        raise ProbeContractError("probe_id_invalid")
    return PROBE_UNIT_NAME_PREFIX + probe_id[len(PROBE_ID_PREFIX):] + PROBE_UNIT_NAME_SUFFIX


def build_capability_probe_intent(
    core: dict[str, Any], *, expires_at: str, max_ttl_seconds: int = PROBE_EVIDENCE_TTL_SECONDS
) -> dict[str, Any]:
    """closed route-class intent:route surface 全 const、十個 forbidden surface 全 false。"""

    core_digest = canonical_digest(core)
    intent = {
        "schema_version": "s2_4_capability_probe_intent_v1",
        "route_class": PROBE_ROUTE_CLASS,
        "core": core,
        "core_digest": core_digest,
        "probe_id": PROBE_ID_PREFIX + core_digest.split(":", 1)[1],
        "route_surface": {
            "required_effect_class": PROBE_REQUIRED_EFFECT_CLASS,
            "runtime_effect": True,
            "service": PROBE_SERVICE_SURFACE,
            "risk": "high",
            "runtime_claim": True,
            "probe_budget_bound": True,
            "cleanup_budget_bound": True,
        },
        "forbidden_surfaces": {name: False for name in PROBE_FORBIDDEN_SURFACES},
        "required_authorization": {
            "profile_identity": PROBE_AUTHORIZATION_PROFILE,
            "signature_namespace": PROBE_SIGNATURE_NAMESPACE,
            "max_ttl_seconds": int(max_ttl_seconds),
        },
        "expires_at": expires_at,
    }
    intent["self_digest"] = artifact_self_digest(intent)
    return intent


def probe_route_surface_contract() -> dict[str, Any]:
    """§4/§10.5 #38 的 code-owned route-surface 契約投影(wave ABI 折入的一面)。"""

    return {
        "route_class": PROBE_ROUTE_CLASS,
        "required_effect_class": PROBE_REQUIRED_EFFECT_CLASS,
        "service": PROBE_SERVICE_SURFACE,
        "forbidden_surfaces": list(PROBE_FORBIDDEN_SURFACES),
        "required_authorization": {
            "profile_identity": PROBE_AUTHORIZATION_PROFILE,
            "signature_namespace": PROBE_SIGNATURE_NAMESPACE,
            "max_ttl_seconds": PROBE_EVIDENCE_TTL_SECONDS,
        },
        "derived_unit_name_pattern": (
            PROBE_UNIT_NAME_PREFIX + "<64hex>" + PROBE_UNIT_NAME_SUFFIX
        ),
    }


def derive_probe_route_surface_status(intent: Any) -> dict[str, Any]:
    """§10.5 #38:節點注入**之前**再導出 probe 的 route surface;夾帶 builder/install 權限即拒。

    caller 不可自證:required_effect_class / service / 十個 forbidden surface / 授權 profile
    與 namespace / TTL 上限全部與 code-owned 契約逐位元組比對,任一漂移即
    ``PROBE_ROUTE_SURFACE_REJECTED``(絕不半通過)。
    """

    reasons: list[str] = []
    if not isinstance(intent, dict):
        return {"status": "PROBE_ROUTE_SURFACE_REJECTED", "reasons": ["probe intent must be an object"]}
    if intent.get("schema_version") != "s2_4_capability_probe_intent_v1":
        reasons.append("probe intent schema_version is not s2_4_capability_probe_intent_v1")
    if intent.get("route_class") != PROBE_ROUTE_CLASS:
        reasons.append(f"probe intent route_class must be {PROBE_ROUTE_CLASS}")
    surface = intent.get("route_surface")
    if not isinstance(surface, dict):
        reasons.append("probe intent route_surface must be an object")
    else:
        if surface.get("required_effect_class") != PROBE_REQUIRED_EFFECT_CLASS:
            reasons.append(
                "probe route_surface required_effect_class must be HOST_CAPABILITY_PROBE "
                "(a builder/install effect class is rejected before node injection)"
            )
        if surface.get("service") != PROBE_SERVICE_SURFACE:
            reasons.append(
                "probe route_surface service must be transient_probe_only "
                "(a persistent-service surface is rejected before node injection)"
            )
        if surface.get("runtime_effect") is not True or surface.get("runtime_claim") is not True:
            reasons.append("probe route_surface must declare runtime_effect/runtime_claim true")
        if surface.get("risk") not in {"high", "critical"}:
            reasons.append("probe route_surface risk must be high or critical")
        if surface.get("probe_budget_bound") is not True or (
            surface.get("cleanup_budget_bound") is not True
        ):
            reasons.append("probe route_surface must bind the probe and cleanup budgets")
    forbidden = intent.get("forbidden_surfaces")
    if not isinstance(forbidden, dict):
        reasons.append("probe intent forbidden_surfaces must be an object")
    else:
        if sorted(forbidden) != sorted(PROBE_FORBIDDEN_SURFACES):
            reasons.append(
                "probe forbidden_surfaces is not the exact §8.3 ten-surface set"
            )
        carried = sorted(name for name, value in forbidden.items() if value is not False)
        if carried:
            reasons.append(
                "probe request carries builder/install authority surfaces "
                f"{carried}; rejected before node injection (§10.5 #38)"
            )
    required = intent.get("required_authorization")
    if not isinstance(required, dict):
        reasons.append("probe intent required_authorization must be an object")
    else:
        if required.get("profile_identity") != PROBE_AUTHORIZATION_PROFILE:
            reasons.append(
                "probe required_authorization profile_identity must be the capability-probe "
                "profile (install/prepare/pg-migration profiles are rejected)"
            )
        if required.get("signature_namespace") != PROBE_SIGNATURE_NAMESPACE:
            reasons.append("probe required_authorization signature_namespace is not the probe namespace")
        ttl = required.get("max_ttl_seconds")
        if not isinstance(ttl, int) or isinstance(ttl, bool) or not 1 <= ttl <= PROBE_EVIDENCE_TTL_SECONDS:
            reasons.append(
                "probe required_authorization max_ttl_seconds must be within the "
                f"{PROBE_EVIDENCE_TTL_SECONDS}s §9.1 ceiling"
            )
    core = intent.get("core")
    if not isinstance(core, dict):
        reasons.append("probe intent core must be an object")
    elif core.get("probe_scope") not in PROBE_SCOPES:
        reasons.append("probe core probe_scope is not one of the two §8.3 scopes")
    return {
        "status": "PASS" if not reasons else "PROBE_ROUTE_SURFACE_REJECTED",
        "reasons": reasons,
    }


def verify_probe_core_scope_binding(core: Any, **scope_inputs: Any) -> list[str]:
    """core 的 transient_unit_property_digest 必須由**自身宣稱的 scope**重新導出(§10.5 #36)。

    一份宣稱 PREPARE_SANDBOX 卻攜帶 INSTALLED_UNIT 屬性 digest 的 core(或反之)在此即拒:
    property digest 進 core → core digest 導 probe_id,故 scope 替換無法保住同一身分。
    """

    if not isinstance(core, dict):
        return ["probe core must be an object"]
    scope = core.get("probe_scope")
    try:
        expected = capability_probe_property_digest(scope, **scope_inputs)
    except ProbeContractError as error:
        return [f"probe core scope binding is not re-derivable: {error.code}"]
    if core.get("transient_unit_property_digest") != expected:
        return [
            "probe core transient_unit_property_digest does not re-derive the "
            f"{scope} property set (scope/property substitution rejected)"
        ]
    return []


# --------------------------------------------------------------------------- #
# recovery 閂:未解的 recovery 期間**不得**起新 probe(§10.5 #39)。
# --------------------------------------------------------------------------- #
class ProbeRecoveryState:
    """注入式 recovery 閂(真持久化屬 W4 的 WAL/lock;此處只保語義)。"""

    def __init__(self) -> None:
        self.unresolved: dict[str, Any] | None = None

    def record(self, *, probe_id: str | None, derived_unit_name: str | None, reasons: list[str]) -> None:
        self.unresolved = {
            "probe_id": probe_id,
            "derived_unit_name": derived_unit_name,
            "reasons": list(reasons),
        }

    def resolve(self, *, probe_id: str | None, resolution_note: str) -> dict[str, Any] | None:
        """由 operator/W4 recovery 明示解閂(probe_id 不符即拒解,fail-closed)。"""

        if self.unresolved is None:
            return None
        if self.unresolved.get("probe_id") != probe_id:
            raise ProbeContractError("recovery_resolution_probe_id_mismatch")
        cleared, self.unresolved = self.unresolved, None
        cleared["resolution_note"] = resolution_note
        return cleared


# --------------------------------------------------------------------------- #
# 注入式 driver protocol —— 真主機動作的唯一出口(真實作屬 W3b/W6A,本葉不含)。
# --------------------------------------------------------------------------- #
class CapabilityProbeDriver(Protocol):
    """task-bound transient unit 的固定操作面;caller **永不**遞交 raw shell/D-Bus 字串。

    誠實界線:本 protocol 只宣告操作形狀。source lane 的 driver 恆為 ``None``。
    ``evidence_class`` 是**自報**欄位,in-process 無從分辨 fixture 與真主機 driver,
    所以 W3 的模型是「閘拒絕自證」而非「接受自證」:任何 attested 等級一律被
    `_recordable_evidence_class` 降為 ``STRUCTURAL_ONLY``(builder 與 governed entry
    point 兩層),因此合法的 W3 artifact 永不帶 attested 等級;真 attested 等級要等
    W4/W6 的 trusted-host attestation 驗證面(見 `w4_owned_obligations`)。
    """

    evidence_class: str

    def journal_transition(self, *, entry: dict[str, Any]) -> None:
        """把一筆 WAL transition 以 temp-create→fsync→atomic-rename→parent-fsync 落盤。"""
        ...

    def start_transient_unit(
        self, *, unit_name: str, scope: str, properties: dict[str, Any]
    ) -> str:
        """建立 task-bound transient unit(structured properties;回傳 InvocationID)。"""
        ...

    def read_unit_properties(self, *, unit_name: str) -> dict[str, Any]:
        """唯讀回 ``{invocation_id, cgroup, property_digest}``(D-Bus 屬性觀測)。"""
        ...

    def observe_egress(self, *, unit_name: str, scope: str) -> dict[str, Any]:
        """實測 egress/deny 行為,回
        ``{host_systemd_cgroup_versions, egress_observations, network_isolation_verified}``。"""
        ...

    def stop_transient_unit(self, *, unit_name: str, max_drain_seconds: int) -> None:
        """stop + 有界 cgroup drain(只對本 task 的 transient cgroup 發訊號)。"""
        ...

    def reset_failed(self, *, unit_name: str) -> None:
        """reset-failed(清掉 failed 狀態,絕不觸碰任何持久 unit)。"""
        ...

    def remove_transient_unit(self, *, unit_name: str) -> None:
        """移除 transient unit(絕不寫任何持久 unit 檔/drop-in)。"""
        ...

    def sweep_residue(self, *, unit_name: str) -> dict[str, Any]:
        """殘留掃描,回 ``{unit_absent, cgroup_absent, process_absent, task_files_absent}``。"""
        ...

    def independent_cleanup_postcheck(
        self, *, unit_name: str, probe_id: str, probe_core_digest: str
    ) -> dict[str, Any]:
        """**相異** verifier 節點的獨立清理 postcheck(applier 不得自證)。"""
        ...

    def trusted_host_time(self) -> str:
        """trusted-host 時鐘(receipt 的 ``trusted_host_time``;絕不用 caller 時鐘)。"""
        ...


class _ProbeAbort(Exception):
    """內部中止訊號(帶 typed reason 與是否為授權過期)。"""

    def __init__(self, reason: str, *, expired: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.expired = expired


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _state_projection(
    unit_name: str, *, present: bool, invocation_id: Any = None, cgroup: Any = None
) -> str:
    return canonical_digest({
        "unit_name": unit_name,
        "unit_present": bool(present),
        "invocation_id": invocation_id,
        "cgroup": cgroup,
    })


def _verdict(
    status: str,
    reasons: list[str],
    *,
    probe_id: str | None = None,
    probe_scope: str | None = None,
    derived_unit_name: str | None = None,
    mutation_performed: bool = False,
    driver_engaged: bool = False,
    effect_receipt: dict[str, Any] | None = None,
    attestation: dict[str, Any] | None = None,
    journal: dict[str, Any] | None = None,
    rollback: dict[str, Any] | None = None,
    postcheck: dict[str, Any] | None = None,
) -> dict[str, Any]:
    verdict = {
        "schema_version": "s2_4_capability_probe_run_verdict_v1_informal",
        "status": status,
        "reasons": list(reasons),
        "probe_id": probe_id,
        "probe_scope": probe_scope,
        "derived_unit_name": derived_unit_name,
        "mutation_performed": bool(mutation_performed),
        "driver_engaged": bool(driver_engaged),
        "blocks_next_phase": status != PROBE_STATUS_TERMINAL_CLEAN,
        "effect_receipt": effect_receipt,
        "attestation": attestation,
        "journal": journal,
        "rollback": rollback,
        "postcheck": postcheck,
        "production_authority_flags": dict(_ALL_FALSE_PRODUCTION_FLAGS),
        "secret_material_scanned": True,
    }
    # §10.5 #15:probe 的唯一出境面。本 route 沒有秘密 ingress,但掃描仍是無條件的。
    leak_reasons = scan_serializable_surface(verdict)
    if not leak_reasons:
        return verdict
    return {
        **{key: None for key in ("effect_receipt", "attestation", "journal", "rollback",
                                 "postcheck")},
        "schema_version": "s2_4_capability_probe_run_verdict_v1_informal",
        "status": PROBE_STATUS_RECOVERY_REQUIRED,
        "reasons": leak_reasons + [
            "the constructed capability-probe verdict carried secret material; every artifact "
            "and reason was dropped rather than returned (§7)"
        ],
        "probe_id": probe_id,
        "probe_scope": probe_scope,
        "derived_unit_name": derived_unit_name,
        "mutation_performed": bool(mutation_performed),
        "driver_engaged": bool(driver_engaged),
        "blocks_next_phase": True,
        "production_authority_flags": dict(_ALL_FALSE_PRODUCTION_FLAGS),
        "secret_material_scanned": True,
    }


def _authorization_profile_errors(authorization: Any, intent: dict[str, Any]) -> list[str]:
    """probe 授權只接受 capability-probe profile;install/prepare/pg 授權挪用即拒。"""

    if not isinstance(authorization, dict):
        return ["probe authorization must be an object"]
    reasons: list[str] = []
    if authorization.get("schema_version") != "s2_4_operator_authorization_v1":
        reasons.append("probe authorization schema_version is not s2_4_operator_authorization_v1")
    if authorization.get("profile_identity") != PROBE_AUTHORIZATION_PROFILE:
        reasons.append(
            "probe authorization profile_identity is not the capability-probe profile "
            "(builder/install/pg-migration authority cannot authorize a probe)"
        )
    if authorization.get("signature_namespace") != PROBE_SIGNATURE_NAMESPACE:
        reasons.append("probe authorization signature_namespace is not the probe namespace")
    required = intent.get("required_authorization")
    if isinstance(required, dict):
        try:
            issued = central_validator._parse_timestamp(authorization["issued_at"])
            expires = central_validator._parse_timestamp(authorization["expires_at"])
            if (expires - issued).total_seconds() > int(required["max_ttl_seconds"]):
                reasons.append("probe authorization TTL exceeds the intent's declared ceiling")
        except (KeyError, TypeError, ValueError):
            reasons.append("probe authorization timestamps are invalid")
    return reasons


def run_s2_4_capability_probe(
    intent: Any,
    authorization: Any = None,
    driver: "CapabilityProbeDriver | None" = None,
    *,
    now: str | datetime | None = None,
    replay_ledger: Any = None,
    recovery_state: ProbeRecoveryState | None = None,
    rendered_unit: Any = None,
    artifact_mirror_allowlist: Any = None,
    fault: Callable[[str], None] | None = None,
    clock: Callable[[], datetime] | None = None,
    applier_node: str = "s2-4-probe-applier",
) -> dict[str, Any]:
    """§10.2 凍結 ABI:執行(或 fail-closed 拒絕)一次 typed host capability probe。

    固定順序,driver 呼叫**之前**零變更:

    0. 未解 recovery → ``RECOVERY_REQUIRED``(§10.5 #39:recovery 未解不得起新 probe);
    1. intent 過中央閘 closed schema + §5.1 core/probe_id 再導出;
    2. §10.5 #38 route-surface 再導出(builder/install 權限夾帶即拒,節點注入前);
    3. core 的 scope↔property digest 再導出(§10.5 #36 scope/digest/property 替換拒);
    4. 授權:capability-probe profile/namespace/TTL + W1 的 §9.1 SSHSIG/信任根/新鮮度 +
       replay-ledger 消費綁定(``UNCONSUMED_AUTHORIZATION_VALID`` 才可進);
    5. intent 自身新鮮窗;
    6. ``driver is None`` → ``EXTERNAL_VERIFICATION_PENDING``(零變更、零 driver 呼叫);
    7. driver 在場 → WAL(APPLYING)→ 建立 → 屬性/InvocationID/cgroup 比對 → egress 實測 →
       stop/drain/reset-failed/remove → 殘留掃描 → 獨立 postcheck → attestation → receipt。

    任一步失敗回 typed 非成功;APPLYING 已入 WAL 之後的任何失敗一律走 cleanup 並回
    ``RECOVERY_REQUIRED``(§8.3「Probe failure or ambiguous cleanup returns RECOVERY_REQUIRED
    and blocks the next phase」),同時閂住 ``recovery_state``。
    """

    reasons: list[str] = []
    # step 0 —— recovery 閂(任何 driver 接觸之前)。
    if recovery_state is not None and recovery_state.unresolved is not None:
        return _verdict(
            PROBE_STATUS_RECOVERY_REQUIRED,
            [
                "a prior capability-probe recovery is unresolved; no new probe may start "
                f"(blocked by {recovery_state.unresolved.get('derived_unit_name')})"
            ],
        )
    # step 1 —— intent 結構/身分再導出(中央閘負責 core_digest/probe_id/self_digest)。
    if not isinstance(intent, dict):
        return _verdict(PROBE_STATUS_REQUEST_REJECTED, ["probe intent must be an object"])
    schema_errors = central_validator.validate_aiml_artifact(intent, now=None)
    if schema_errors:
        return _verdict(PROBE_STATUS_REQUEST_REJECTED, schema_errors)
    core = intent["core"]
    scope = core["probe_scope"]
    probe_id = intent["probe_id"]
    core_digest = intent["core_digest"]
    unit_name = derived_probe_unit_name(probe_id)
    # step 2 —— route surface(§10.5 #38)。
    surface = derive_probe_route_surface_status(intent)
    if surface["status"] != "PASS":
        return _verdict(
            PROBE_STATUS_REQUEST_REJECTED,
            surface["reasons"],
            probe_id=probe_id,
            probe_scope=scope,
            derived_unit_name=unit_name,
        )
    # step 3 —— scope ↔ property digest 再導出(§10.5 #36)。
    scope_inputs: dict[str, Any] = {}
    if scope == "INSTALLED_UNIT":
        if rendered_unit is None:
            return _verdict(
                PROBE_STATUS_REQUEST_REJECTED,
                [
                    "INSTALLED_UNIT probe requires the exact W2c rendered unit to re-derive "
                    "its property digest (§8.3); refusing to accept an opaque digest"
                ],
                probe_id=probe_id, probe_scope=scope, derived_unit_name=unit_name,
            )
        scope_inputs["rendered_unit"] = rendered_unit
    else:
        scope_inputs["artifact_mirror_allowlist"] = artifact_mirror_allowlist
    binding_errors = verify_probe_core_scope_binding(core, **scope_inputs)
    if binding_errors:
        return _verdict(
            PROBE_STATUS_REQUEST_REJECTED, binding_errors,
            probe_id=probe_id, probe_scope=scope, derived_unit_name=unit_name,
        )
    # step 4 —— 授權(profile/namespace/TTL + §9.1 SSHSIG/信任根 + replay 消費綁定)。
    reasons = _authorization_profile_errors(authorization, intent)
    if replay_ledger is None:
        reasons.append(
            "probe authorization replay-consumption cannot be proved without the "
            "authorization replay ledger (fail-closed)"
        )
    if reasons:
        return _verdict(
            PROBE_STATUS_AUTHORIZATION_REJECTED, reasons,
            probe_id=probe_id, probe_scope=scope, derived_unit_name=unit_name,
        )
    replay = central_validator.derive_authorization_replay_binding(
        authorization, replay_ledger, now=now
    )
    if replay["status"] != "UNCONSUMED_AUTHORIZATION_VALID":
        return _verdict(
            PROBE_STATUS_AUTHORIZATION_REJECTED, replay["reasons"],
            probe_id=probe_id, probe_scope=scope, derived_unit_name=unit_name,
        )
    # step 5 —— intent 新鮮窗(過期 intent 不得起 probe)。
    now_dt = _resolve_now(now)
    try:
        intent_expires = central_validator._parse_timestamp(intent["expires_at"])
    except (KeyError, TypeError, ValueError):
        return _verdict(
            PROBE_STATUS_REQUEST_REJECTED, ["probe intent expires_at is invalid"],
            probe_id=probe_id, probe_scope=scope, derived_unit_name=unit_name,
        )
    if now_dt >= intent_expires:
        return _verdict(
            PROBE_STATUS_REQUEST_REJECTED, ["probe intent is expired"],
            probe_id=probe_id, probe_scope=scope, derived_unit_name=unit_name,
        )
    # step 6 —— 無 driver(Mac/源碼/測試):reachable 閘在,但沒有可執行的主機面。
    if driver is None:
        return _verdict(
            PROBE_STATUS_PENDING,
            [
                "capability probe is reachable but authority-locked: no host probe driver is "
                "present (Mac/source/test lane); EXTERNAL_VERIFICATION_PENDING with zero mutation"
            ],
            probe_id=probe_id, probe_scope=scope, derived_unit_name=unit_name,
        )
    # step 7 —— driver 在場:完整 transient-unit 生命週期。
    return _run_probe_with_driver(
        intent=intent,
        authorization=authorization,
        driver=driver,
        core=core,
        core_digest=core_digest,
        probe_id=probe_id,
        scope=scope,
        unit_name=unit_name,
        replay_ledger=replay_ledger,
        recovery_state=recovery_state,
        scope_inputs=scope_inputs,
        fault=fault,
        clock=clock or (lambda: datetime.now(timezone.utc)),
        applier_node=applier_node,
        now_dt=now_dt,
    )


def _resolve_now(now: str | datetime | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if isinstance(now, datetime):
        return now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return central_validator._parse_timestamp(now)


def _run_probe_with_driver(
    *,
    intent: dict[str, Any],
    authorization: dict[str, Any],
    driver: Any,
    core: dict[str, Any],
    core_digest: str,
    probe_id: str,
    scope: str,
    unit_name: str,
    replay_ledger: dict[str, Any],
    recovery_state: ProbeRecoveryState | None,
    scope_inputs: dict[str, Any],
    fault: Callable[[str], None] | None,
    clock: Callable[[], datetime],
    applier_node: str,
    now_dt: datetime,
) -> dict[str, Any]:
    """driver 在場的固定生命週期;APPLYING 入 WAL 後任何失敗都走 cleanup(fail-closed)。"""

    cleanup_budget = core["cleanup_budget"]
    cleanup_contract = capability_probe_cleanup_contract(
        probe_id=probe_id, derived_unit_name=unit_name, cleanup_budget=cleanup_budget
    )
    cleanup_rollback_digest = canonical_digest(cleanup_contract)
    property_set = capability_probe_property_set(scope, **scope_inputs)
    authorization_expires = central_validator._parse_timestamp(authorization["expires_at"])
    entries: list[dict[str, Any]] = []
    lifecycle = {
        "invocation_id": "",
        "unit_created": False,
        "unit_observed": False,
        "stopped_after_grace": False,
        "reset_failed": False,
        "removed": False,
        "zero_residue_verified": False,
    }
    absent_state = _state_projection(unit_name, present=False)
    committed = False           # APPLYING 已入 WAL:此後不能再宣稱「必無 unit」
    mutation_performed = False
    egress: dict[str, Any] | None = None

    def _gate(label: str) -> None:
        if fault is not None:
            fault(label)

    def _require_live(operation: str) -> None:
        # 授權過期後只剩 cleanup 權限:新建立/觀測一律停手(§5.2 / rollback schema)。
        if clock() >= authorization_expires:
            raise _ProbeAbort(
                f"probe authorization expired during execution before {operation}; "
                "only the exact cleanup authority remains",
                expired=True,
            )

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
        _gate("pre_journal_applying")
        _journal("APPLYING", absent_state, absent_state)
        committed = True
        _gate("post_journal_applying")

        _require_live("transient unit creation")
        _gate("pre_start_unit")
        invocation_id = driver.start_transient_unit(
            unit_name=unit_name, scope=scope, properties=property_set
        )
        mutation_performed = True
        lifecycle["unit_created"] = True
        lifecycle["invocation_id"] = str(invocation_id)
        _gate("post_start_unit")

        created_state = _state_projection(
            unit_name, present=True, invocation_id=str(invocation_id)
        )
        _gate("pre_journal_applied")
        _journal("APPLIED", absent_state, created_state)
        _gate("post_journal_applied")

        _require_live("unit property observation")
        _gate("pre_read_properties")
        properties = driver.read_unit_properties(unit_name=unit_name)
        _gate("post_read_properties")
        mismatch = _property_mismatch_reasons(
            properties,
            invocation_id=str(invocation_id),
            core=core,
            unit_name=unit_name,
        )
        if mismatch:
            raise _ProbeAbort("; ".join(mismatch))
        lifecycle["unit_observed"] = True
        observed_state = _state_projection(
            unit_name,
            present=True,
            invocation_id=str(invocation_id),
            cgroup=properties.get("cgroup"),
        )
        _gate("pre_journal_verifying")
        _journal("VERIFYING", created_state, observed_state)
        _gate("post_journal_verifying")

        _require_live("egress observation")
        _gate("pre_observe_egress")
        egress = driver.observe_egress(unit_name=unit_name, scope=scope)
        _gate("post_observe_egress")
        if not isinstance(egress, dict):
            raise _ProbeAbort("probe driver egress observation is not an object")
    except _ProbeAbort as abort:
        return _abort_outcome(
            abort.reason,
            expired=abort.expired,
            committed=committed,
            mutation_performed=mutation_performed,
            driver=driver, unit_name=unit_name, probe_id=probe_id, scope=scope,
            core_digest=core_digest, cleanup_budget=cleanup_budget,
            cleanup_rollback_digest=cleanup_rollback_digest, entries=entries,
            lifecycle=lifecycle, clock=clock, fault=fault,
            recovery_state=recovery_state, property_digest=core["transient_unit_property_digest"],
        )
    except Exception as error:  # noqa: BLE001 - 任何 driver/journal 逸出都 fail-closed
        return _abort_outcome(
            f"capability probe interrupted: {redact_driver_error(error)}",
            expired=False,
            committed=committed,
            mutation_performed=mutation_performed,
            driver=driver, unit_name=unit_name, probe_id=probe_id, scope=scope,
            core_digest=core_digest, cleanup_budget=cleanup_budget,
            cleanup_rollback_digest=cleanup_rollback_digest, entries=entries,
            lifecycle=lifecycle, clock=clock, fault=fault,
            recovery_state=recovery_state, property_digest=core["transient_unit_property_digest"],
        )

    # ── cleanup(正常路徑亦必跑:transient unit 絕不存活)───────────────────────
    cleanup = _run_cleanup(
        driver=driver, unit_name=unit_name, cleanup_budget=cleanup_budget,
        fault=fault, lifecycle=lifecycle,
    )
    pre_cleanup_state = _state_projection(unit_name, present=True, invocation_id=lifecycle["invocation_id"])
    try:
        _journal("COMPENSATING", pre_cleanup_state, pre_cleanup_state)
        _journal("COMPENSATED", pre_cleanup_state, absent_state)
    except Exception as error:  # noqa: BLE001
        cleanup["reasons"].append(f"cleanup journal transition failed: {redact_driver_error(error)}")
        cleanup["cleaned"] = False
    rollback = _build_rollback(
        probe_id=probe_id, unit_name=unit_name, cleanup=cleanup,
        pre_state=pre_cleanup_state, post_state=absent_state, clock=clock,
    )
    postcheck, postcheck_reasons = _build_postcheck(
        driver=driver, unit_name=unit_name, probe_id=probe_id,
        core_digest=core_digest, applier_node=applier_node, clock=clock,
    )
    if not cleanup["cleaned"] or postcheck is None or postcheck["status"] != "PASS":
        combined = cleanup["reasons"] + postcheck_reasons + [
            "capability probe cleanup is ambiguous; RECOVERY_REQUIRED blocks the next phase"
        ]
        if recovery_state is not None:
            recovery_state.record(
                probe_id=probe_id, derived_unit_name=unit_name, reasons=combined
            )
        journal = _build_journal(
            probe_id=probe_id, unit_name=unit_name, scope=scope,
            property_digest=core["transient_unit_property_digest"],
            cleanup_rollback_digest=cleanup_rollback_digest, entries=entries, terminal=False,
        )
        return _verdict(
            PROBE_STATUS_RECOVERY_REQUIRED, combined,
            probe_id=probe_id, probe_scope=scope, derived_unit_name=unit_name,
            mutation_performed=mutation_performed, driver_engaged=True,
            journal=journal, rollback=rollback, postcheck=postcheck,
        )
    lifecycle["zero_residue_verified"] = True
    try:
        _journal("VERIFIED", absent_state, absent_state)
    except Exception as error:  # noqa: BLE001
        return _verdict(
            PROBE_STATUS_RECOVERY_REQUIRED,
            [f"terminal journal transition failed: {redact_driver_error(error)}"],
            probe_id=probe_id, probe_scope=scope, derived_unit_name=unit_name,
            mutation_performed=mutation_performed, driver_engaged=True,
            rollback=rollback, postcheck=postcheck,
        )
    journal = _build_journal(
        probe_id=probe_id, unit_name=unit_name, scope=scope,
        property_digest=core["transient_unit_property_digest"],
        cleanup_rollback_digest=cleanup_rollback_digest, entries=entries, terminal=True,
    )
    trusted_time = str(driver.trusted_host_time())
    attestation = build_network_sandbox_capability_attestation(
        scope=scope, probe_id=probe_id, probe_core_digest=core_digest,
        transient_unit_property_digest=core["transient_unit_property_digest"],
        egress=egress,
        evidence_class=derive_recorded_evidence_class(driver)["recorded_evidence_class"],
        observed_at=trusted_time,
    )
    capability_ok = bool(egress.get("network_isolation_verified")) is True
    receipt = _build_effect_receipt(
        probe_id=probe_id, core=core, core_digest=core_digest, scope=scope,
        authorization=authorization, replay_ledger=replay_ledger, unit_name=unit_name,
        lifecycle=lifecycle, journal=journal, postcheck=postcheck, rollback=rollback,
        attestation=attestation, trusted_time=trusted_time, now_dt=now_dt,
        evidence_class=derive_recorded_evidence_class(driver)["recorded_evidence_class"],
        terminal_status=(
            PROBE_STATUS_TERMINAL_CLEAN if capability_ok else PROBE_STATUS_TERMINAL_FAILED
        ),
    )
    central_errors = (
        central_validator.validate_aiml_artifact(attestation)
        + central_validator.validate_aiml_artifact(receipt)
        + central_validator.validate_aiml_artifact(journal)
        + central_validator.validate_aiml_artifact(postcheck)
        + central_validator.validate_aiml_artifact(rollback)
    )
    if central_errors:
        if recovery_state is not None:
            recovery_state.record(
                probe_id=probe_id, derived_unit_name=unit_name, reasons=central_errors
            )
        return _verdict(
            PROBE_STATUS_RECOVERY_REQUIRED, central_errors,
            probe_id=probe_id, probe_scope=scope, derived_unit_name=unit_name,
            mutation_performed=mutation_performed, driver_engaged=True,
            journal=journal, rollback=rollback, postcheck=postcheck,
        )
    if not capability_ok:
        return _verdict(
            PROBE_STATUS_CAPABILITY_UNSATISFIED,
            [
                "the required network/sandbox capability was not verified on this host; "
                "HOST_NETWORK_SANDBOX_CAPABILITY_UNSATISFIED blocks that phase (cleanup was exact)"
            ],
            probe_id=probe_id, probe_scope=scope, derived_unit_name=unit_name,
            mutation_performed=mutation_performed, driver_engaged=True,
            effect_receipt=receipt, attestation=attestation, journal=journal,
            rollback=rollback, postcheck=postcheck,
        )
    return _verdict(
        PROBE_STATUS_TERMINAL_CLEAN, [],
        probe_id=probe_id, probe_scope=scope, derived_unit_name=unit_name,
        mutation_performed=mutation_performed, driver_engaged=True,
        effect_receipt=receipt, attestation=attestation, journal=journal,
        rollback=rollback, postcheck=postcheck,
    )


def _property_mismatch_reasons(
    properties: Any, *, invocation_id: str, core: dict[str, Any], unit_name: str
) -> list[str]:
    """InvocationID / cgroup / property digest 三者必須與 core 與 start 回值一致(§10.5 #39)。"""

    if not isinstance(properties, dict):
        return ["probe driver unit properties are not an object"]
    reasons: list[str] = []
    observed_invocation = str(properties.get("invocation_id", ""))
    if observed_invocation != invocation_id:
        reasons.append("observed InvocationID does not match the created transient unit")
    if re.fullmatch(PROBE_INVOCATION_ID_PATTERN, observed_invocation) is None:
        reasons.append("observed InvocationID does not match the systemd InvocationID pattern")
    cgroup = str(properties.get("cgroup", ""))
    expected_root = str(core["host_cgroup_identity"]["cgroup_root_pattern"])
    if not cgroup.startswith(expected_root) or not cgroup.endswith(unit_name):
        reasons.append("observed cgroup is not the task-bound transient cgroup for this probe")
    if properties.get("property_digest") != core["transient_unit_property_digest"]:
        reasons.append("observed unit property digest does not match the signed core property digest")
    return reasons


def _run_cleanup(
    *,
    driver: Any,
    unit_name: str,
    cleanup_budget: dict[str, Any],
    fault: Callable[[str], None] | None,
    lifecycle: dict[str, Any],
) -> dict[str, Any]:
    """exact cleanup-only 授權面:stop → 有界 drain → reset-failed → remove → 殘留掃描。"""

    reasons: list[str] = []
    residue: dict[str, Any] = {
        "unit_absent": False,
        "cgroup_absent": False,
        "process_absent": False,
        "task_files_absent": False,
    }
    try:
        if fault is not None:
            fault("pre_stop")
        driver.stop_transient_unit(
            unit_name=unit_name,
            max_drain_seconds=int(cleanup_budget["max_cgroup_drain_seconds"]),
        )
        lifecycle["stopped_after_grace"] = True
        if fault is not None:
            fault("post_stop")
        if fault is not None:
            fault("pre_reset_failed")
        driver.reset_failed(unit_name=unit_name)
        lifecycle["reset_failed"] = True
        if fault is not None:
            fault("post_reset_failed")
        if fault is not None:
            fault("pre_remove")
        driver.remove_transient_unit(unit_name=unit_name)
        lifecycle["removed"] = True
        if fault is not None:
            fault("post_remove")
        if fault is not None:
            fault("pre_sweep")
        swept = driver.sweep_residue(unit_name=unit_name)
        if fault is not None:
            fault("post_sweep")
        if not isinstance(swept, dict):
            reasons.append("probe driver residue sweep is not an object")
        else:
            residue = {key: bool(swept.get(key)) for key in residue}
    except Exception as error:  # noqa: BLE001 - 清理失敗即 ambiguous cleanup
        reasons.append(f"capability probe cleanup did not complete: {redact_driver_error(error)}")
    missing = sorted(key for key, value in residue.items() if value is not True)
    if missing:
        reasons.append(f"capability probe residue survives: {missing}")
    cleaned = not reasons and all(
        lifecycle[key] for key in ("stopped_after_grace", "reset_failed", "removed")
    )
    return {"cleaned": cleaned, "reasons": reasons, "residue": residue}


def _build_rollback(
    *,
    probe_id: str,
    unit_name: str,
    cleanup: dict[str, Any],
    pre_state: str,
    post_state: str,
    clock: Callable[[], datetime],
) -> dict[str, Any]:
    observed = clock()
    rollback = {
        "schema_version": "s2_4_capability_probe_rollback_v1",
        "status": "CLEANED_EXACT" if cleanup["cleaned"] else "NOT_CLEANED",
        "probe_id": probe_id,
        "derived_unit_name": unit_name,
        "pre_state_digest": pre_state,
        "post_state_digest": post_state,
        "stop_operation": "transient_unit_stop",
        "cgroup_drain_operation": "bounded_cgroup_drain",
        "reset_failed_operation": "reset_failed",
        "remove_operation": "transient_unit_remove",
        "cgroup_drain_bounded": bool(cleanup["cleaned"]),
        "unit_absent": bool(cleanup["residue"]["unit_absent"]),
        "cgroup_absent": bool(cleanup["residue"]["cgroup_absent"]),
        "task_files_absent": bool(cleanup["residue"]["task_files_absent"]),
        "observed_at": _iso(observed),
        "expires_at": _iso(observed + timedelta(seconds=PROBE_EVIDENCE_TTL_SECONDS)),
    }
    rollback["self_digest"] = artifact_self_digest(rollback)
    return rollback


def _build_postcheck(
    *,
    driver: Any,
    unit_name: str,
    probe_id: str,
    core_digest: str,
    applier_node: str,
    clock: Callable[[], datetime],
) -> tuple[dict[str, Any] | None, list[str]]:
    """相異 verifier 節點的獨立 postcheck(applier 不得自證;逸出即 typed reasons)。"""

    try:
        observed = driver.independent_cleanup_postcheck(
            unit_name=unit_name, probe_id=probe_id, probe_core_digest=core_digest
        )
    except Exception as error:  # noqa: BLE001
        return None, [f"independent cleanup postcheck failed: {redact_driver_error(error)}"]
    if not isinstance(observed, dict):
        return None, ["independent cleanup postcheck did not return an object"]
    verifier_node = str(observed.get("verifier_node", ""))
    if not verifier_node or verifier_node == applier_node:
        return None, ["independent cleanup postcheck verifier_node must differ from the applier"]
    at = clock()
    flags = {
        key: bool(observed.get(key))
        for key in (
            "stopped_confirmed",
            "reset_failed_confirmed",
            "removed_confirmed",
            "no_surviving_unit",
            "no_surviving_cgroup",
            "no_surviving_process",
        )
    }
    capture = observed.get("verifier_capture_digest")
    if not isinstance(capture, str) or _DIGEST_RE.fullmatch(capture) is None:
        return None, ["independent cleanup postcheck verifier_capture_digest is invalid"]
    postcheck = {
        "schema_version": "s2_4_capability_probe_postcheck_v1",
        "status": "PASS" if all(flags.values()) else "FAIL",
        "probe_id": probe_id,
        "probe_core_digest": core_digest,
        "derived_unit_name": unit_name,
        "verifier_node": verifier_node,
        "applier_node": applier_node,
        **flags,
        "verifier_capture_digest": capture,
        "observed_at": _iso(at),
        "expires_at": _iso(at + timedelta(seconds=PROBE_EVIDENCE_TTL_SECONDS)),
    }
    postcheck["self_digest"] = artifact_self_digest(postcheck)
    return postcheck, ([] if postcheck["status"] == "PASS" else ["independent cleanup postcheck FAILED"])


def _build_journal(
    *,
    probe_id: str,
    unit_name: str,
    scope: str,
    property_digest: str,
    cleanup_rollback_digest: str,
    entries: list[dict[str, Any]],
    terminal: bool,
) -> dict[str, Any] | None:
    if not entries:
        return None
    journal = {
        "schema_version": "s2_4_capability_probe_journal_v1",
        "probe_id": probe_id,
        "derived_unit_name": unit_name,
        "scope": scope,
        "transient_unit_property_digest": property_digest,
        "expected_invocation_id_pattern": PROBE_INVOCATION_ID_PATTERN,
        "cleanup_rollback_digest": cleanup_rollback_digest,
        "entries": [dict(entry) for entry in entries],
        "terminal": bool(terminal),
        "journal_integrity": {
            "same_filesystem_atomic_rename": True,
            "file_fsynced": True,
            "parent_dir_fsynced": True,
        },
    }
    # outer_checksum 先於 self_digest:內層 canonical digest(self_digest)含 outer_checksum,
    # 兩者因此是可分辨的兩道完整性面(schema description 的 inner/outer 語義)。
    journal["outer_checksum"] = canonical_digest(journal)
    journal["self_digest"] = artifact_self_digest(journal)
    return journal


def build_network_sandbox_capability_attestation(
    *,
    scope: str,
    probe_id: str,
    probe_core_digest: str,
    transient_unit_property_digest: str,
    egress: dict[str, Any],
    evidence_class: str,
    observed_at: str,
) -> dict[str, Any]:
    """scope-bound sandbox 能力 attestation(§8.3 表;兩 scope 永不互換)。

    ``observed_sandbox_capability_digest`` 由本函式**折出**——scope + host/systemd/cgroup
    版本 + 實測 egress 觀測 + 該 scope 的 property digest 一起入折,故 driver 無從遞交一個
    裸 digest,scope 替換也必然改變 attestation 內容身分。
    """

    at = central_validator._parse_timestamp(observed_at)
    attestation = {
        "schema_version": "network_sandbox_capability_attestation_v1",
        "scope": scope,
        "probe_id": probe_id,
        "probe_core_digest": probe_core_digest,
        "transient_unit_property_digest": transient_unit_property_digest,
        "observed_sandbox_capability_digest": canonical_digest({
            "scope": scope,
            "transient_unit_property_digest": transient_unit_property_digest,
            "host_systemd_cgroup_versions": egress.get("host_systemd_cgroup_versions"),
            "egress_observations": egress.get("egress_observations"),
        }),
        "network_isolation_verified": bool(egress.get("network_isolation_verified")),
        # E2 P2-B:builder 自己也拒絕 attested 自證(本函式 public 且被再匯出,不能只靠
        # governed entry point 那道閘)。
        "evidence_class": _recordable_evidence_class(evidence_class),
        "production_posture": {
            "is_runtime_production_pass": False,
            "production_apply_performed": False,
            "running_attested": False,
            "nine_authorities_false": True,
        },
        "observed_at": _iso(at),
        "expires_at": _iso(at + timedelta(seconds=PROBE_EVIDENCE_TTL_SECONDS)),
    }
    attestation["self_digest"] = artifact_self_digest(attestation)
    return attestation


def _build_effect_receipt(
    *,
    probe_id: str,
    core: dict[str, Any],
    core_digest: str,
    scope: str,
    authorization: dict[str, Any],
    replay_ledger: dict[str, Any],
    unit_name: str,
    lifecycle: dict[str, Any],
    journal: dict[str, Any] | None,
    postcheck: dict[str, Any],
    rollback: dict[str, Any],
    attestation: dict[str, Any],
    trusted_time: str,
    now_dt: datetime,
    evidence_class: str,
    terminal_status: str,
) -> dict[str, Any]:
    """終端 receipt:綁 core/授權/transient unit/journal/replay/postcheck/rollback/attestation。"""

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
        "schema_version": "s2_4_capability_probe_effect_receipt_v1",
        "probe_id": probe_id,
        "probe_core_digest": core_digest,
        "probe_scope": scope,
        "authorization_id": authorization["authorization_id"],
        "authorization_digest": authorization["self_digest"],
        "derived_unit_name": unit_name,
        "transient_unit_lifecycle": dict(lifecycle),
        "journal_digest": journal["self_digest"] if journal else canonical_digest(None),
        "consumed_replay_entry_digest": consumed_entry,
        "postcheck_digest": postcheck["self_digest"],
        "rollback_digest": rollback["self_digest"],
        "network_sandbox_capability_attestation_digest": attestation["self_digest"],
        "terminal_status": terminal_status,
        # E2 P2-B:同 attestation builder,receipt 也在 builder 層拒絕 attested 自證。
        "evidence_class": _recordable_evidence_class(evidence_class),
        "source_head": core["source_head"],
        "target_host": core["target_host"],
        "trusted_host_time": _iso(at),
        "observed_at": _iso(now_dt),
        "expires_at": _iso(at + timedelta(seconds=PROBE_EVIDENCE_TTL_SECONDS)),
        "production_authority_flags": dict(_ALL_FALSE_PRODUCTION_FLAGS),
    }
    receipt["self_digest"] = artifact_self_digest(receipt)
    return receipt


def _abort_outcome(
    reason: str,
    *,
    expired: bool,
    committed: bool,
    mutation_performed: bool,
    driver: Any,
    unit_name: str,
    probe_id: str,
    scope: str,
    core_digest: str,
    cleanup_budget: dict[str, Any],
    cleanup_rollback_digest: str,
    entries: list[dict[str, Any]],
    lifecycle: dict[str, Any],
    clock: Callable[[], datetime],
    fault: Callable[[str], None] | None,
    recovery_state: ProbeRecoveryState | None,
    property_digest: str,
) -> dict[str, Any]:
    """APPLYING 之前中止 = 零變更 typed 失敗;之後中止 = cleanup-only → RECOVERY_REQUIRED。"""

    if not committed:
        # WAL 尚未記 APPLYING:沒有任何 D-Bus 呼叫發生過,無殘留可談。
        return _verdict(
            PROBE_STATUS_TERMINAL_FAILED,
            [reason, "no transient unit was created; zero mutation"],
            probe_id=probe_id, probe_scope=scope, derived_unit_name=unit_name,
            driver_engaged=True,
        )
    # 過期後只剩 exact cleanup 授權——照跑 stop/drain/reset/remove(安全清理永不被過期擋住)。
    cleanup = _run_cleanup(
        driver=driver, unit_name=unit_name, cleanup_budget=cleanup_budget,
        fault=None, lifecycle=lifecycle,
    )
    pre_state = _state_projection(
        unit_name, present=True, invocation_id=lifecycle["invocation_id"] or None
    )
    post_state = _state_projection(unit_name, present=False)
    rollback = _build_rollback(
        probe_id=probe_id, unit_name=unit_name, cleanup=cleanup,
        pre_state=pre_state, post_state=post_state, clock=clock,
    )
    try:
        entry = {
            "seq": len(entries),
            "state": "COMPENSATED" if cleanup["cleaned"] else "FAILED",
            "pre_state_digest": pre_state,
            "post_state_digest": post_state if cleanup["cleaned"] else pre_state,
            "fsynced": True,
            "recorded_at": _iso(clock()),
        }
        driver.journal_transition(entry=entry)
        entries.append(entry)
    except Exception as error:  # noqa: BLE001
        cleanup["reasons"].append(f"compensation journal transition failed: {redact_driver_error(error)}")
    reasons = [reason]
    if expired:
        reasons.append(
            "after authorization expiry only the exact cleanup authority remained; "
            "no new creation or observation was attempted"
        )
    reasons.extend(cleanup["reasons"])
    reasons.append(
        "capability probe failure returns RECOVERY_REQUIRED and blocks the next phase"
    )
    if recovery_state is not None:
        recovery_state.record(
            probe_id=probe_id, derived_unit_name=unit_name, reasons=reasons
        )
    journal = _build_journal(
        probe_id=probe_id, unit_name=unit_name, scope=scope,
        property_digest=property_digest, cleanup_rollback_digest=cleanup_rollback_digest,
        entries=entries, terminal=False,
    )
    return _verdict(
        PROBE_STATUS_RECOVERY_REQUIRED, reasons,
        probe_id=probe_id, probe_scope=scope, derived_unit_name=unit_name,
        mutation_performed=mutation_performed, driver_engaged=True,
        journal=journal, rollback=rollback,
    )


# --------------------------------------------------------------------------- #
# 消費者側:scope 綁定與 phase 前置(§8.3 兩 scope 不可互換 + W6A 不需 final-unit)。
# --------------------------------------------------------------------------- #
def derive_scoped_capability_attestation_status(
    attestation: Any,
    effect_receipt: Any,
    *,
    required_scope: str,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    """一份 attestation 能否滿足**這個 scope** 的消費者(§8.3;scope 替換三層第三層)。

    要求:required_scope 為兩 scope 之一;attestation.scope == receipt.probe_scope ==
    required_scope;receipt 綁定該 attestation 的 self_digest 與同一 probe_id/core digest;
    receipt.terminal_status == TERMINAL_CLEAN(「attestation 沒有那份終端 effect receipt
    即不可用」);network_isolation_verified 為真;兩者皆未過期。
    """

    reasons: list[str] = []
    if required_scope not in PROBE_SCOPES:
        return {"status": "SCOPE_SUBSTITUTION_REJECTED", "reasons": ["required_scope is not a §8.3 scope"]}
    if not isinstance(attestation, dict) or not isinstance(effect_receipt, dict):
        return {
            "status": "SCOPE_SUBSTITUTION_REJECTED",
            "reasons": ["attestation and effect receipt must both be objects"],
        }
    if attestation.get("schema_version") != "network_sandbox_capability_attestation_v1":
        reasons.append("attestation schema_version is not network_sandbox_capability_attestation_v1")
    if effect_receipt.get("schema_version") != "s2_4_capability_probe_effect_receipt_v1":
        reasons.append("effect receipt schema_version is not s2_4_capability_probe_effect_receipt_v1")
    if attestation.get("scope") != required_scope:
        reasons.append(
            f"attestation scope {attestation.get('scope')!r} cannot satisfy a "
            f"{required_scope} consumer (an attestation of one scope never satisfies the other)"
        )
    if effect_receipt.get("probe_scope") != required_scope:
        reasons.append(
            f"terminal probe receipt scope {effect_receipt.get('probe_scope')!r} cannot "
            f"satisfy a {required_scope} consumer"
        )
    if reasons:
        return {"status": "SCOPE_SUBSTITUTION_REJECTED", "reasons": reasons}
    if attestation.get("self_digest") != artifact_self_digest(attestation):
        reasons.append("attestation self_digest is invalid")
    if effect_receipt.get("self_digest") != artifact_self_digest(effect_receipt):
        reasons.append("terminal probe receipt self_digest is invalid")
    if effect_receipt.get("network_sandbox_capability_attestation_digest") != (
        attestation.get("self_digest")
    ):
        reasons.append(
            "terminal probe receipt does not bind this attestation "
            "(an attestation file without that terminal effect receipt is unusable)"
        )
    if attestation.get("probe_id") != effect_receipt.get("probe_id") or (
        attestation.get("probe_core_digest") != effect_receipt.get("probe_core_digest")
    ):
        reasons.append("attestation and terminal probe receipt bind different probe identities")
    # E2 P2-B:W3 的兩個 builder 都把 attested 等級降為 STRUCTURAL_ONLY,所以「合法的 W3
    # artifact 永不帶 attested 等級」。消費側據此把帶 attested 的 artifact 判為未經本閘
    # 產出的偽造品——這是 latent minting surface 的最後一道關,不是重複檢查。
    for label, artifact in (("attestation", attestation), ("terminal probe receipt", effect_receipt)):
        declared = str(artifact.get("evidence_class"))
        if declared in _component.EVIDENCE_CLASS_ATTESTED:
            reasons.append(
                f"{label} carries evidence_class={declared!r}; no W3-produced artifact can carry "
                "an attested class (the builders refuse self-declaration), so this artifact was "
                "not produced by the governed path and cannot satisfy a capability consumer"
            )
        elif declared != _component.EVIDENCE_CLASS_STRUCTURAL_ONLY:
            reasons.append(
                f"{label} evidence_class {declared!r} is not the STRUCTURAL_ONLY class W3 records"
            )
    if effect_receipt.get("terminal_status") != PROBE_STATUS_TERMINAL_CLEAN:
        reasons.append(
            "probe receipt is not TERMINAL_CLEAN; a failed or recovery-pending probe cannot "
            "satisfy a capability consumer"
        )
    if attestation.get("network_isolation_verified") is not True:
        reasons.append("attestation does not verify the required network isolation behaviour")
    now_text = central_validator._now_text(now)
    if now_text is not None:
        try:
            current = central_validator._parse_timestamp(now_text)
            for label, artifact in (("attestation", attestation), ("probe receipt", effect_receipt)):
                if current >= central_validator._parse_timestamp(artifact["expires_at"]):
                    reasons.append(f"{label} evidence is expired (refresh-by-reference is forbidden)")
        except (KeyError, TypeError, ValueError):
            reasons.append("attestation/receipt timestamps are invalid")
    if reasons:
        return {"status": "SCOPE_SUBSTITUTION_REJECTED", "reasons": reasons}
    return {"status": "SCOPE_SATISFIED", "reasons": []}


def derive_probe_phase_prerequisite_status(
    phase: str,
    scoped_evidence: Any,
    *,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    """W6A/W6B 的 probe 前置再導出(§8.3:final-unit attestation 永非 W6A 前置)。

    ``scoped_evidence`` 為 ``{scope: {"attestation": ..., "effect_receipt": ...}}``。W6A 只要求
    ``PREPARE_SANDBOX``——即使完全沒有 ``INSTALLED_UNIT`` 證據也 SATISFIED(無 output-derived
    admission cycle);W6B 兩個 scope 都要。多餘的 scope 不會使 W6A 失敗,但也**不能**替代。
    """

    required = {
        "W6A": W6A_PREREQUISITE_PROBE_SCOPES,
        "W6B": W6B_PREREQUISITE_PROBE_SCOPES,
    }.get(phase)
    if required is None:
        return {
            "status": "HOST_NETWORK_SANDBOX_CAPABILITY_UNSATISFIED",
            "reasons": [f"unknown probe phase {phase!r}"],
            "required_scopes": [],
        }
    if not isinstance(scoped_evidence, dict):
        return {
            "status": "HOST_NETWORK_SANDBOX_CAPABILITY_UNSATISFIED",
            "reasons": ["scoped probe evidence must be a mapping of scope -> evidence"],
            "required_scopes": list(required),
        }
    reasons: list[str] = []
    for scope in required:
        evidence = scoped_evidence.get(scope)
        if not isinstance(evidence, dict):
            reasons.append(f"{phase} requires terminal {scope} probe evidence; none was supplied")
            continue
        verdict = derive_scoped_capability_attestation_status(
            evidence.get("attestation"),
            evidence.get("effect_receipt"),
            required_scope=scope,
            now=now,
        )
        if verdict["status"] != "SCOPE_SATISFIED":
            reasons.extend(f"{scope}: {reason}" for reason in verdict["reasons"])
    return {
        "status": (
            "PROBE_PREREQUISITE_SATISFIED"
            if not reasons
            else "HOST_NETWORK_SANDBOX_CAPABILITY_UNSATISFIED"
        ),
        "reasons": reasons,
        "required_scopes": list(required),
    }


# 供 W3 wave-exit exported-ABI 折入的 code-owned 探針欄位(與真 repo/runtime 無關)。
_ABI_PROBE_MIRROR_ALLOWLIST = ("203.0.113.0/24",)
_ABI_PROBE_UNIT_FIELDS = {
    "source_head": "0" * 40,
    "learning_runtime_digest": "sha256:" + "0" * 64,
    "learning_runtime_digest_v2": "sha256:" + "1" * 64,
    "application_bundle_digest": "sha256:" + "2" * 64,
    "launch_bundle_digest": "sha256:" + "3" * 64,
}


def probe_abi_projection() -> dict[str, Any]:
    """W3 exported-ABI 的 probe 面(code-owned 骨架 + 兩 scope property digest 的活再導出)。"""

    try:
        prepare_digest = capability_probe_property_digest(
            "PREPARE_SANDBOX", artifact_mirror_allowlist=list(_ABI_PROBE_MIRROR_ALLOWLIST)
        )
    except Exception:  # noqa: BLE001 - 任何逸出 = fail-closed 未證
        prepare_digest = None
    try:
        installed_digest = capability_probe_property_digest(
            "INSTALLED_UNIT",
            rendered_unit=_render.render_engine_scanner_unit(dict(_ABI_PROBE_UNIT_FIELDS)),
        )
    except Exception:  # noqa: BLE001
        installed_digest = None
    return {
        "capability_probe": (
            "agent_governance_s2_4_probe.run_s2_4_capability_probe(intent, authorization, driver)"
        ),
        "capability_probe_driver": "agent_governance_s2_4_probe.CapabilityProbeDriver",
        "probe_route_class": PROBE_ROUTE_CLASS,
        "probe_scopes": list(PROBE_SCOPES),
        "probe_typed_statuses": list(PROBE_TYPED_STATUSES),
        "probe_route_surface_contract_digest": canonical_digest(probe_route_surface_contract()),
        "prepare_sandbox_property_digest": prepare_digest,
        "installed_unit_property_digest": installed_digest,
        "scope_consumer_predicate": (
            "agent_governance_s2_4_probe.derive_scoped_capability_attestation_status"
        ),
        "phase_prerequisite_predicate": (
            "agent_governance_s2_4_probe.derive_probe_phase_prerequisite_status"
        ),
        "w6a_prerequisite_probe_scopes": list(W6A_PREREQUISITE_PROBE_SCOPES),
        "w6b_prerequisite_probe_scopes": list(W6B_PREREQUISITE_PROBE_SCOPES),
        "recovery_latch": "agent_governance_s2_4_probe.ProbeRecoveryState",
        "schema_ids": [
            "network_sandbox_capability_attestation_v1",
            "s2_4_capability_probe_core_v1",
            "s2_4_capability_probe_effect_receipt_v1",
            "s2_4_capability_probe_intent_v1",
            "s2_4_capability_probe_journal_v1",
            "s2_4_capability_probe_postcheck_v1",
            "s2_4_capability_probe_rollback_v1",
        ],
    }
