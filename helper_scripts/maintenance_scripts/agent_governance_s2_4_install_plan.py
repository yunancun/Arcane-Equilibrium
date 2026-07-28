#!/usr/bin/env python3
"""S2.4(WP4·W4b)aggregate APPLY 的**純導出**葉——plan 組裝 / permit payload 綁定 / rollback 契約。

依 §10.1.1 的 2000 行治理規約自 :mod:`agent_governance_s2_4_install_driver` 拆出。此處**只有**
確定性的 digest 導出與 plan 形狀組裝:零 I/O、零 driver、零主機動作、零 authority。父模組
(``agent_governance_s2_4_install_driver``)逐名 re-export,消費者的匯入面與常量值皆不變。

三組內容:

1. §5.4 的逆向補償契約(``per_row_rollback_*`` / ``aggregate_rollback_*``)——rollback digest 由
   code + 身分導出,caller 無從遞交,故消費端可**獨立再導出**。
2. AGGREGATE_PLAN_PAYLOAD_FULL_COMPARISON——兩張 §9.1 permit 的**逐欄**期望 payload_binding,
   以及證明「每一欄都被比對到」的 :func:`derive_permit_payload_coverage`。
3. §5.1 的無環 plan↔intent 綁定與 :func:`build_s2_4_install_plan`。
4. §10.5 #24 的**輸入側/成功側**謂詞(兩份 scoped terminal probe receipt + PREPARE 結果 +
   五份 plan 釘住的 component intent → 五個相異 row 結果),含每一份證據的新鮮度檢查。
"""
from __future__ import annotations

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
import agent_governance_s2_4_component as _component  # noqa: E402
import agent_governance_s2_4_permit as _permit  # noqa: E402
from agent_governance_s2_4_reconcile import InstallDriverContractError  # noqa: E402

canonical_digest = central_validator.canonical_digest
artifact_self_digest = central_validator.artifact_self_digest
_DIGEST_RE = _component._DIGEST_RE
# §10.5 #24 的兩個 scoped probe(同一份 probe 不得充當兩個 scope)。
PROBE_SCOPES = ("PREPARE_SANDBOX", "INSTALLED_UNIT")
# §10.5 #36 probe-core 綁定的 typed 可見性(E8):caller 沒遞交期望值時,綁定只到「哪一份
# receipt」而不到「它探的是不是這一份 rendered unit」——那件事必須在 verdict 上留痕。
PROBE_CORE_BINDING_UNVERIFIED = "UNVERIFIED_NO_EXPECTED_VALUE_SUPPLIED"
PROBE_CORE_BINDING_VERIFIED = "VERIFIED_AGAINST_SUPPLIED_EXPECTED_DIGEST"

# ── §5.1 / §5.4 的 code-owned 次序面(worker 不得改,§10.4)──────────────────────
APPLY_ROW_ORDER = tuple(central_validator.S2_4_APPLY_ROW_CLASS_ORDER)
# §5.4:unit -> launch/application bundle -> base runtime -> credential -> auth/PG -> host。
REVERSE_COMPENSATION_ORDER = tuple(reversed(APPLY_ROW_ORDER))
# §5.4 逆向補償鏈契約的 domain(把它的 digest 與任何別的 digest 空間分開)。
AGGREGATE_ROLLBACK_CONTRACT_DOMAIN = (
    "arcane-equilibrium-aiml-s2-4-aggregate-reverse-compensation-chain-v1"
)
PER_ROW_ROLLBACK_CONTRACT_DOMAIN = (
    "arcane-equilibrium-aiml-s2-4-per-row-reverse-compensation-op-v1"
)
# W4b OBSERVER_SPACE_PRE_STATE_DIGEST 的 plan 側 domain(見 derive_plan_pre_state_projection)。
PLAN_PRE_STATE_PROJECTION_DOMAIN = (
    "arcane-equilibrium-aiml-s2-4-plan-pre-state-projection-v1"
)


# ── §5.4 逆向補償鏈契約(code-owned;plan 不攜帶 rollback digest,故它必須由 code 導出) ──
#
# 先例:W3a 的 probe ``cleanup_rollback_digest`` 亦是
# ``canonical_digest(capability_probe_cleanup_contract(...))``——rollback 契約由 code + 身分
# 導出,caller 無從遞交。此處逐字沿用同一機制,故 aggregate/PG permit 簽的
# ``aggregate_rollback_digest`` / ``pg_rollback_digest`` 皆可被消費端**獨立再導出**。
def per_row_rollback_contract(
    *, plan_id: str, component_effect_class: str
) -> dict[str, Any]:
    """單一 row 的逆向補償 op 契約(綁 plan 身分 + 凍結矩陣的 recovery_contract)。"""

    row_abi = _component.component_row_abi(component_effect_class)
    return {
        "domain": PER_ROW_ROLLBACK_CONTRACT_DOMAIN,
        "plan_id": plan_id,
        "component_effect_class": component_effect_class,
        "recovery_contract": row_abi["recovery_contract"],
        "adapter_id": row_abi["adapter_id"],
        "ownership_aware": True,
        "restores_exact_prior_bytes_or_removes_task_owned_delta_only": True,
        "never_drops_observer_role": True,
        "never_reconstructs_a_pre_existing_secret": True,
    }


def per_row_rollback_digest(*, plan_id: str, component_effect_class: str) -> str:
    return canonical_digest(
        per_row_rollback_contract(
            plan_id=plan_id, component_effect_class=component_effect_class
        )
    )


def aggregate_rollback_contract(*, plan_id: str) -> dict[str, Any]:
    """§5.4 的整條逆向補償鏈契約(次序 = 五 row 的逆序 + 兩條 reload 再斷言)。"""

    return {
        "domain": AGGREGATE_ROLLBACK_CONTRACT_DOMAIN,
        "plan_id": plan_id,
        "reverse_order": list(REVERSE_COMPENSATION_ORDER),
        "reverse_ops": [
            {
                "component_effect_class": name,
                "per_row_rollback_digest": per_row_rollback_digest(
                    plan_id=plan_id, component_effect_class=name
                ),
            }
            for name in REVERSE_COMPENSATION_ORDER
        ],
        "daemon_reload_reasserted_after_unit_bytes_rollback": True,
        "hba_reload_reasserted_after_hba_rollback": True,
        "observer_role_preserved": True,
        "no_secret_reconstructed": True,
    }


def aggregate_rollback_digest(*, plan_id: str) -> str:
    return canonical_digest(aggregate_rollback_contract(plan_id=plan_id))


# ── W4b AGGREGATE_PLAN_PAYLOAD_FULL_COMPARISON —— 兩張 permit 的**逐欄**期望 payload ──
# §9.1 payload 中「由 permit 自身的窗釘死、而非由 plan 導出」的兩欄:PERMIT_PLAN_BINDING 第 (a)
# 層已強制 payload_binding[issued_at/expires_at] == 頂層值,另有 §9.1 TTL 上限閘;故它們不由
# plan 導出,而是取 permit 自己記錄的窗(:func:`derive_permit_payload_coverage` 斷言覆蓋完整)。
PERMIT_WINDOW_FIELDS = ("issued_at", "expires_at")


def aggregate_permit_payload_binding(
    plan: dict[str, Any],
    *,
    installed_unit_probe_receipt: dict[str, Any],
    issued_at: Any,
    expires_at: Any,
) -> dict[str, Any]:
    """apply-aggregate permit 的**完整**期望 payload_binding(逐欄由 plan/證據獨立再導出)。"""

    core = plan["core"]
    plan_id = plan["plan_id"]
    profile = central_validator.S2_4_AUTHORIZATION_PROFILES["apply_aggregate"]
    return {
        "domain": profile["signature_namespace"],
        "plan_core_digest": canonical_digest(core),
        "plan_id": plan_id,
        "idempotency_key": plan_id,
        "source_head": core["source_head"],
        "target_host": core["target_host"],
        "prepare_receipt_digest": core["prepare_receipt_digest"],
        "topology_pre_digest": core["topology_pre_digest"],
        # plan core 不攜帶 probe receipt digest:它由 aggregate 手上那份 terminal
        # INSTALLED_UNIT probe receipt 獨立再導出(§6 step 3 的同一份證據)。
        "installed_unit_probe_receipt_digest": installed_unit_probe_receipt["self_digest"],
        "hba_delta_digest": core["hba_delta_digest"],
        "pre_state_digest": core["pre_state_digest"],
        "aggregate_rollback_digest": aggregate_rollback_digest(plan_id=plan_id),
        "issued_at": issued_at,
        "expires_at": expires_at,
    }


def pg_permit_payload_binding(
    plan: dict[str, Any],
    *,
    component_intents: dict[str, Any],
    installed_unit_probe_receipt: dict[str, Any],
    issued_at: Any,
    expires_at: Any,
) -> dict[str, Any]:
    """PG-migration permit 的**完整**期望 payload_binding(PG 兩欄由 PG row intent 導出)。

    ``pg_acl_digest`` / ``pg_pre_state_digest`` 來自 ``PG_ROLE_ACL_MIGRATION`` 的 component
    intent——那份 intent 的 digest 已被 plan core 的 ``apply_rows`` 釘住,故此導出仍錨在 plan。
    """

    core = plan["core"]
    plan_id = plan["plan_id"]
    profile = central_validator.S2_4_AUTHORIZATION_PROFILES["pg_migration"]
    pg_intent = component_intents["PG_ROLE_ACL_MIGRATION"]
    return {
        "domain": profile["signature_namespace"],
        "plan_core_digest": canonical_digest(core),
        "plan_id": plan_id,
        "idempotency_key": plan_id,
        "source_head": core["source_head"],
        "target_host": core["target_host"],
        "topology_pre_digest": core["topology_pre_digest"],
        "installed_unit_probe_receipt_digest": installed_unit_probe_receipt["self_digest"],
        "pg_acl_digest": pg_intent["required_intent_fields"]["acl_manifest_digest"],
        "hba_delta_digest": core["hba_delta_digest"],
        "pg_pre_state_digest": pg_intent["pre_state_digest"],
        "pg_rollback_digest": per_row_rollback_digest(
            plan_id=plan_id, component_effect_class="PG_ROLE_ACL_MIGRATION"
        ),
        "issued_at": issued_at,
        "expires_at": expires_at,
    }


def derive_permit_payload_coverage() -> dict[str, Any]:
    """證明兩張 permit 的**每一個** §9.1 payload 欄位都被比對到(或被明載為窗欄位)。

    AGGREGATE_PLAN_PAYLOAD_FULL_COMPARISON 的可測不變量:期望 binding 的鍵集 ∪
    ``{authorization_id}`` 必須恰等於 profile 的 ordered payload——未來新增而沒被覆蓋的欄位會
    讓此投影不再 ``complete``,W4 wave-exit 因而破。
    """

    coverage: dict[str, Any] = {}
    plan = _coverage_probe_plan()
    receipt = {"self_digest": "sha256:" + "5" * 64}
    intents = {
        "PG_ROLE_ACL_MIGRATION": {
            "pre_state_digest": plan["core"]["pre_state_digest"],
            "required_intent_fields": {"acl_manifest_digest": "sha256:" + "6" * 64},
        }
    }
    bindings = {
        "apply_aggregate": aggregate_permit_payload_binding(
            plan, installed_unit_probe_receipt=receipt,
            issued_at="2030-01-01T00:00:00+00:00", expires_at="2030-01-01T00:10:00+00:00",
        ),
        "pg_migration": pg_permit_payload_binding(
            plan, component_intents=intents, installed_unit_probe_receipt=receipt,
            issued_at="2030-01-01T00:00:00+00:00", expires_at="2030-01-01T00:10:00+00:00",
        ),
    }
    for profile_key, binding in bindings.items():
        expected = set(
            central_validator.authorization_payload_binding_fields(profile_key)
        )
        present = set(binding)
        coverage[profile_key] = {
            "compared_field_count": len(present),
            "payload_field_count": len(
                central_validator.S2_4_AUTHORIZATION_PROFILES[profile_key]["payload_fields"]
            ),
            "uncompared_fields": sorted(expected - present),
            "extra_fields": sorted(present - expected),
            "window_fields": list(PERMIT_WINDOW_FIELDS),
            "complete": present == expected,
        }
    return coverage


def _coverage_probe_plan() -> dict[str, Any]:
    """coverage 投影用的 code-owned plan 骨架(與任何真 plan 無關,只為導出鍵集)。"""

    return {
        "plan_id": "s2-4-" + "0" * 64,
        "core": {
            "schema_version": "s2_4_install_plan_core_v1",
            "apply_rows": [
                {"component_effect_class": name, "component_intent_digest": "sha256:" + "1" * 64}
                for name in APPLY_ROW_ORDER
            ],
            "prepare_receipt_digest": "sha256:" + "2" * 64,
            "topology_pre_digest": "sha256:" + "3" * 64,
            "hba_delta_digest": "sha256:" + "4" * 64,
            "pre_state_digest": "sha256:" + "7" * 64,
            "source_head": "0" * 40,
            "target_host": "trade-core",
            "created_at": "2030-01-01T00:00:00+00:00",
        },
    }


# ── W4b OBSERVER_SPACE_PRE_STATE_DIGEST(plan 側的一半:定義並執法) ──
def derive_plan_pre_state_projection(component_intents: dict[str, Any]) -> str:
    """§6 step 8 的 plan 側 pre-state digest 空間定義。

    W4a 記錄的縫是「plan 宣告的 ``pre_state_digest`` 與 verifier 的觀測 digest 不在同一
    digest 空間」。W4b 關掉**可關的那一半**:aggregate 的 ``core.pre_state_digest`` 自此
    **定義為**五 row 各自宣告 pre-state 的 domain-separated canonical 投影,故它不再是一個
    無定義的不透明值——任何一 row 的 pre-state 被換掉,plan 立刻不再自洽。

    仍未關的一半(見 W4 ABI 的 remaining obligations):把**獨立 verifier** 的
    ``observed_subject_digest`` 綁進同一空間需要真主機 observer(W6B),源碼線只能釘期望值。
    """

    return canonical_digest({
        "domain": PLAN_PRE_STATE_PROJECTION_DOMAIN,
        "rows": [
            {
                "component_effect_class": name,
                "pre_state_digest": component_intents[name]["pre_state_digest"],
            }
            for name in APPLY_ROW_ORDER
        ],
    })


# ── §5.1「There is no digest/signature cycle」—— plan ↔ component intent 的無環綁定 ──
#
# schema 同時要求 plan core 的 ``apply_rows[].component_intent_digest`` 與 component intent 的
# ``install_plan_digest``。若前者取 intent 的 ``self_digest``,兩者就互含彼此的 digest = 環,
# 構造上無解。W4b 依 §5.1 的明文把環剪開:
#
#   component_intent_digest = domain-separated canonical digest(intent 去掉**兩個**自指欄位:
#                             install_plan_digest 與 self_digest)
#   install_plan_digest     = plan 的 core_digest(另由 aggregate 逐一比對)
#
# 覆蓋不因此變窄:intent 的其餘每一欄(class / pre_state / class-specific digest / expiry)都被
# plan 釘死,而它指向哪一份 plan 由 aggregate 直接比對 core_digest——替換任一側皆被拒。
COMPONENT_INTENT_PLAN_BINDING_DOMAIN = (
    "arcane-equilibrium-aiml-s2-4-component-intent-plan-binding-v1"
)
_INTENT_SELF_REFERENTIAL_FIELDS = ("install_plan_digest", "self_digest")


def component_intent_plan_binding_digest(intent: Any) -> str:
    """plan core 用來釘住一份 component intent 的 digest(排除兩個自指欄位;§5.1 無環)。"""

    if not isinstance(intent, dict):
        raise InstallDriverContractError("component_effect_intent_not_an_object")
    return canonical_digest({
        "domain": COMPONENT_INTENT_PLAN_BINDING_DOMAIN,
        "intent": {
            key: value
            for key, value in intent.items()
            if key not in _INTENT_SELF_REFERENTIAL_FIELDS
        },
    })


# ── S2.4-AMEND-2(obligation 25):plan-derived expected_topology ─────────────────
# ``expected_topology`` 曾是 ROW_PAYLOAD_ALLOWLIST 裡唯一不被任何簽章綁定的 caller key;
# 正解是由簽章 plan 導出:core 已綁 ``topology_pre_digest``(簽章前觀測基線)與
# ``hba_delta_digest``(簽章 HBA delta),caller 自此不再供給任何基線鍵。
HBA_DELTA_PLAN_BINDING_DOMAIN = (
    "arcane-equilibrium-aiml-s2-4-hba-delta-plan-binding-v1"
)
# delta 帶 plan_id/plan_core_digest、core 帶 hba_delta_digest,互指必成環;core 綁的因此是
# **去自指投影**(鏡 :func:`component_intent_plan_binding_digest` 的 §5.1 剪環作法)。
_HBA_DELTA_SELF_REFERENTIAL_FIELDS = ("plan_id", "plan_core_digest", "self_digest")
PLAN_EXPECTED_TOPOLOGY_DERIVED = "PLAN_EXPECTED_TOPOLOGY_DERIVED"
PLAN_EXPECTED_TOPOLOGY_UNPROVEN = "PLAN_EXPECTED_TOPOLOGY_UNPROVEN"


def hba_delta_plan_binding_digest(delta: Any) -> str:
    """plan core 用來釘住一份 ``s2_4_pg_hba_delta_v1`` 的 digest(§5.1 no-cycle)。

    排除三個自指欄位後的 canonical digest:其餘每一欄(pre/post HBA digest、delta 操作、
    ``effective_rule``、reload 操作、rollback 投影、觀測窗、cluster ref)全被簽章 core 釘死。
    """

    if not isinstance(delta, dict):
        raise InstallDriverContractError("pg_hba_delta_not_an_object")
    return canonical_digest({
        "domain": HBA_DELTA_PLAN_BINDING_DOMAIN,
        "hba_delta": {
            key: value
            for key, value in delta.items()
            if key not in _HBA_DELTA_SELF_REFERENTIAL_FIELDS
        },
    })


def derive_plan_expected_topology(
    *, plan: Any, hba_delta: Any, topology_attestation: Any,
) -> dict[str, Any]:
    """由**簽章 plan**導出 PG row 的 ``expected_topology``(fail-closed;零 caller 基線鍵)。

    驗序:central closed-schema 驗 hba_delta → 去自指 binding digest 必等
    ``core.hba_delta_digest`` → 後綁回填的 ``plan_id``/``plan_core_digest`` 必等 plan 自身 →
    ``topology_attestation.self_digest`` 必等 ``core.topology_pre_digest``(presented 觀測
    必須**是**簽章前基線)。通過後回**全鍵** expected(經 (i) fail-closed 化後無鍵可省):
    三個內容 digest 取自基線 attestation、``hba_projection`` 取自簽章 delta 的
    ``effective_rule``、``source_head``/``target_host`` 取自 plan core。任一失敗回
    ``PLAN_EXPECTED_TOPOLOGY_UNPROVEN``,聚合層映為 ``PG_TOPOLOGY_UNPROVEN``(driver 未觸)。
    """

    outcome: dict[str, Any] = {
        "status": PLAN_EXPECTED_TOPOLOGY_UNPROVEN,
        "reasons": [],
        "expected_topology": None,
    }
    reasons: list[str] = outcome["reasons"]
    core = plan.get("core") if isinstance(plan, dict) else None
    if not isinstance(core, dict):
        reasons.append("the install plan carries no signed core object")
        return outcome
    if not isinstance(hba_delta, dict):
        reasons.append(
            "the PG row requires the signed s2_4_pg_hba_delta_v1 bound into the plan core "
            "(core.hba_delta_digest); none was supplied"
        )
        return outcome
    schema_errors = central_validator.validate_aiml_artifact(hba_delta)
    if schema_errors:
        reasons.extend(schema_errors)
        return outcome
    if hba_delta_plan_binding_digest(hba_delta) != core.get("hba_delta_digest"):
        reasons.append(
            "the supplied HBA delta does not re-derive the hba_delta_digest signed into the "
            "plan core; a substituted delta is not the one the operator signed"
        )
    if hba_delta.get("plan_id") != plan.get("plan_id"):
        reasons.append("the HBA delta names a different plan_id than this plan")
    if hba_delta.get("plan_core_digest") != plan.get("core_digest"):
        reasons.append("the HBA delta names a different plan_core_digest than this plan")
    if not isinstance(topology_attestation, dict) or topology_attestation.get(
        "self_digest"
    ) != core.get("topology_pre_digest"):
        reasons.append(
            "the presented pg_topology_attestation_v1 is not the signed pre-observation "
            "baseline (self_digest != core.topology_pre_digest); a different cluster's "
            "observation can never become its own expected baseline"
        )
    if reasons:
        return outcome
    entries = [dict(hba_delta["effective_rule"])]
    outcome["status"] = PLAN_EXPECTED_TOPOLOGY_DERIVED
    outcome["expected_topology"] = {
        "listener_config_digest": topology_attestation.get("listener_config_digest"),
        "proxy_config_digest": topology_attestation.get("proxy_config_digest"),
        "cluster_identity_digest": topology_attestation.get("cluster_identity_digest"),
        "hba_projection": {
            "entries": entries,
            "projection_digest": canonical_digest(entries),
        },
        "source_head": core.get("source_head"),
        "target_host": core.get("target_host"),
    }
    return outcome


# ── plan builder(§5.1:plan 於 PREPARE/probe 之後才被簽;此處只組 exact 形狀) ──
def build_s2_4_install_plan(
    *,
    component_intents: dict[str, Any],
    prepare_receipt_digest: str,
    topology_pre_digest: str,
    hba_delta_digest: str,
    source_head: str,
    target_host: str,
    created_at: str,
    expires_at: str,
    max_ttl_seconds: int = _permit.MAX_PERMIT_TTL_SECONDS,
) -> dict[str, Any]:
    """組出 ``s2_4_install_plan_v1`` 並把五份 component intent **重綁**到它的 core digest。

    回 ``{"plan": …, "component_intents": …}``:傳入的 intent 只需帶 class / pre_state /
    class-specific 欄位 / expiry(其 ``install_plan_digest`` 是 placeholder,因為 plan 還不存在);
    本函式先由「去自指欄位」的 binding digest 組出 core,再以 core digest 重建每一份 intent。
    重建**不改變** binding digest(那兩個欄位本就被排除),函式對此有 fail-closed 斷言。
    """

    missing = [name for name in APPLY_ROW_ORDER if name not in (component_intents or {})]
    if missing:
        raise InstallDriverContractError("install_plan_requires_all_five_component_intents")
    core = {
        "schema_version": "s2_4_install_plan_core_v1",
        "apply_rows": [
            {
                "component_effect_class": name,
                "component_intent_digest": component_intent_plan_binding_digest(
                    component_intents[name]
                ),
            }
            for name in APPLY_ROW_ORDER
        ],
        "prepare_receipt_digest": prepare_receipt_digest,
        "topology_pre_digest": topology_pre_digest,
        "hba_delta_digest": hba_delta_digest,
        "pre_state_digest": derive_plan_pre_state_projection(component_intents),
        "source_head": source_head,
        "target_host": target_host,
        "created_at": created_at,
    }
    core_digest = canonical_digest(core)
    plan_id = "s2-4-" + core_digest.split(":", 1)[1]
    plan = {
        "schema_version": "s2_4_install_plan_v1",
        "route_class": "s2_4_install_plan",
        "core": core,
        "core_digest": core_digest,
        "plan_id": plan_id,
        "idempotency_key": plan_id,
        "route_surface": {
            "aggregate_coordinator": True,
            "runtime_effect": True,
            "service": "system_unit_install_inactive",
            "pg": True,
            "migration": True,
            "secret": True,
            "risk": "critical",
            "runtime_claim": True,
            "apply_rows": list(APPLY_ROW_ORDER),
        },
        "forbidden_surfaces": {
            "prepare_fetch": False,
            "prepare_build": False,
            "arbitrary_shell": False,
            "arbitrary_sql": False,
            "arbitrary_path": False,
            "broker_or_order": False,
        },
        "required_authorization": {
            "aggregate": {
                "profile_identity": _component.APPLY_AGGREGATE_PROFILE,
                "signature_namespace": _component.APPLY_AGGREGATE_NAMESPACE,
                "max_ttl_seconds": int(max_ttl_seconds),
            },
            "pg_migration": {
                "profile_identity": _component.PG_MIGRATION_PROFILE,
                "signature_namespace": _component.PG_MIGRATION_NAMESPACE,
                "max_ttl_seconds": int(max_ttl_seconds),
            },
        },
        "expires_at": expires_at,
    }
    plan["self_digest"] = artifact_self_digest(plan)
    rebound: dict[str, Any] = {}
    for name in APPLY_ROW_ORDER:
        supplied = component_intents[name]
        intent = _component.build_component_effect_intent(
            component_effect_class=name,
            install_plan_digest=core_digest,
            pre_state_digest=supplied["pre_state_digest"],
            required_intent_fields=supplied["required_intent_fields"],
            expires_at=supplied["expires_at"],
        )
        if component_intent_plan_binding_digest(intent) != core["apply_rows"][
            APPLY_ROW_ORDER.index(name)
        ]["component_intent_digest"]:
            raise InstallDriverContractError("component_intent_plan_binding_digest_drifted")
        rebound[name] = intent
    return {"plan": plan, "component_intents": rebound}


# ── §10.5 #24 —— aggregate 輸入與成功謂詞 ──
def derive_aggregate_input_status(
    plan: Any,
    *,
    component_intents: Any,
    probe_receipts: Any,
    prepare_effect_receipt: Any,
    now: Any = None,
    expected_installed_unit_probe_core_digest: Any = None,
) -> dict[str, Any]:
    """§10.5 #24 的輸入側:兩個 scoped probe receipt + PREPARE 結果 + 五 row intent。

    每一項都被獨立再驗(中央 schema 閘 + terminal 狀態 + host/head 一致 + digest 綁 plan);
    兩個 scope 的 receipt digest 必相異(同一份 probe 不得充當兩個 scope)。

    **新鮮度**(W4b·Fix-C):``now`` 被逐一往下傳。過去每一份證據都以 ``now=None`` 送驗,於是
    「過期一年的 probe receipt」與「剛剛才簽出來的」在這道閘上完全相同——§9.2/§10.5 #28 明文
    禁止以引用刷新已過期的 runtime/topology/prepare/auth 證據,故它們的窗必須在**第一次變更
    之前**就被檢查。PREPARE receipt 亦然:§6 step 5 的 prepared-bundle 再雜湊排在 step 7 的
    consume 與 step 11 的 driver 之前,所以一份過期的 PREPARE lineage 必須是**零變更**的拒絕,
    而不是等到第 4 列(``LEARNING_RUNTIME``)才被抓到、然後補償前三列。
    """

    verdict: dict[str, Any] = {
        "schema_version": "s2_4_aggregate_input_verdict_v1_informal",
        "status": "AGGREGATE_INPUTS_REJECTED",
        "reasons": [],
        "probe_receipt_digests": {},
        "prepare_result_digest": None,
        "prepare_postcheck_digest": None,
        # §10.5 #36 的 probe-core 綁定是**選配**輸入,故「有沒有被檢查」必須是 verdict 上的
        # typed 事實,而不是靠讀者去推測(E8:略過不得無痕)。
        "probe_core_binding": (
            PROBE_CORE_BINDING_VERIFIED
            if expected_installed_unit_probe_core_digest is not None
            else PROBE_CORE_BINDING_UNVERIFIED
        ),
    }
    reasons: list[str] = []
    if not isinstance(plan, dict) or plan.get("schema_version") != "s2_4_install_plan_v1":
        verdict["reasons"] = ["the aggregate transaction requires an s2_4_install_plan_v1"]
        return verdict
    core = plan.get("core")
    if not isinstance(core, dict):
        verdict["reasons"] = ["install plan core must be an object"]
        return verdict
    # (1) 五 row intent:class 集合 exact、digest 逐一等於 plan core 的 apply_rows。
    if not isinstance(component_intents, dict) or sorted(component_intents) != sorted(
        APPLY_ROW_ORDER
    ):
        reasons.append(
            "the aggregate transaction requires exactly the five §5.1 APPLY component intents "
            f"{list(APPLY_ROW_ORDER)}"
        )
    else:
        rows = core.get("apply_rows") or []
        for index, name in enumerate(APPLY_ROW_ORDER):
            intent = component_intents[name]
            intent_errors = central_validator.validate_aiml_artifact(intent, now=now)
            if intent_errors:
                reasons.extend(f"{name} intent: {reason}" for reason in intent_errors)
                continue
            if intent.get("install_plan_digest") != plan.get("core_digest"):
                reasons.append(
                    f"{name} intent install_plan_digest is not this plan's core digest"
                )
            row = rows[index] if index < len(rows) and isinstance(rows[index], dict) else {}
            if row.get("component_intent_digest") != component_intent_plan_binding_digest(
                intent
            ):
                reasons.append(
                    f"{name} intent is not the one bound into the signed plan core at §5.1 "
                    f"position {index} (§5.1 no-cycle binding: the plan pins every intent field "
                    "except the two self-referential ones)"
                )
        if not reasons:
            projection = derive_plan_pre_state_projection(component_intents)
            if core.get("pre_state_digest") != projection:
                reasons.append(
                    "the plan's signed pre_state_digest does not re-derive the domain-separated "
                    "projection over the five rows' declared pre-states (§6 step 8)"
                )
    # (2) 兩個 scoped terminal capability-probe receipt。
    if not isinstance(probe_receipts, dict) or sorted(probe_receipts) != sorted(PROBE_SCOPES):
        reasons.append(
            "the aggregate transaction requires BOTH scoped terminal capability-probe receipts "
            f"{list(PROBE_SCOPES)} (§10.5 #24)"
        )
    else:
        for scope in PROBE_SCOPES:
            receipt = probe_receipts[scope]
            reasons.extend(
                f"{scope} probe receipt: {reason}"
                for reason in _probe_receipt_reasons(
                    receipt, scope=scope, core=core, now=now,
                    expected_probe_core_digest=(
                        expected_installed_unit_probe_core_digest
                        if scope == "INSTALLED_UNIT" else None
                    ),
                )
            )
        digests = {
            scope: (probe_receipts[scope] or {}).get("self_digest")
            if isinstance(probe_receipts[scope], dict) else None
            for scope in PROBE_SCOPES
        }
        verdict["probe_receipt_digests"] = digests
        if digests[PROBE_SCOPES[0]] is not None and (
            digests[PROBE_SCOPES[0]] == digests[PROBE_SCOPES[1]]
        ):
            reasons.append(
                "the two scoped probe receipts share one digest; PREPARE_SANDBOX and "
                "INSTALLED_UNIT must be two distinct terminal probes"
            )
    # (3) PREPARE 結果(§6 step 5 的再雜湊排在 consume/driver 之前 → 零變更拒絕)。
    prepare_reasons = _prepare_receipt_reasons(prepare_effect_receipt, core=core, now=now)
    reasons.extend(f"PREPARE receipt: {reason}" for reason in prepare_reasons)
    if not prepare_reasons and isinstance(prepare_effect_receipt, dict):
        verdict["prepare_result_digest"] = prepare_effect_receipt["self_digest"]
        verdict["prepare_postcheck_digest"] = prepare_effect_receipt["postcheck_digest"]
    if reasons:
        verdict["reasons"] = reasons
        return verdict
    verdict["status"] = "AGGREGATE_INPUTS_ADMITTED"
    return verdict


def _probe_receipt_reasons(
    receipt: Any,
    *,
    scope: str,
    core: dict[str, Any],
    now: Any = None,
    expected_probe_core_digest: Any = None,
) -> list[str]:
    """一份 scoped terminal probe receipt 對**這一份** plan 的可接受性(含新鮮度)。

    誠實界線(remaining obligation ``INSTALLED_UNIT_PROBE_CORE_BINDING``):receipt 攜帶的
    ``probe_core_digest`` 才是 probe permit 真正簽的東西(連同
    ``output_derived_unit_digest_or_null``),但 ``s2_4_install_plan_core_v1`` 沒有可放期望值的
    欄位,而新增 core 欄位是 §10.4 禁止 worker 自行選擇的 schema 變更。此處提供顯式的
    ``expected_probe_core_digest`` 閘(W6B runner 手上同時握有 probe 與 APPLY 兩段,可以遞交),
    給了就逐位元比對;沒給時,綁定仍只到「哪一份 receipt」(由 permit 的
    ``installed_unit_probe_receipt_digest`` 釘住)而不到「它探的是不是這一份 rendered unit」。
    """

    if not isinstance(receipt, dict) or receipt.get("schema_version") != (
        "s2_4_capability_probe_effect_receipt_v1"
    ):
        return ["must be an s2_4_capability_probe_effect_receipt_v1"]
    reasons = list(central_validator.validate_aiml_artifact(receipt, now=now))
    if expected_probe_core_digest is not None and receipt.get(
        "probe_core_digest"
    ) != expected_probe_core_digest:
        reasons.append(
            "probe_core_digest is not the expected probe core for this plan's rendered unit "
            "(§6 step 3 / §10.5 #36: a terminal probe receipt for one unit can never gate an "
            "APPLY that installs another)"
        )
    if receipt.get("probe_scope") != scope:
        reasons.append(f"probe_scope is {receipt.get('probe_scope')!r}, not {scope}")
    if receipt.get("terminal_status") != "TERMINAL_CLEAN":
        reasons.append(
            f"terminal_status is {receipt.get('terminal_status')!r}; a non-terminal or failed "
            "probe can never gate an APPLY transaction"
        )
    lifecycle = receipt.get("transient_unit_lifecycle")
    if not isinstance(lifecycle, dict) or lifecycle.get("zero_residue_verified") is not True:
        reasons.append(
            "the terminal probe receipt does not carry zero_residue_verified; no surviving "
            "probe unit must be proven before the aggregate transaction starts"
        )
    if receipt.get("target_host") != core.get("target_host"):
        reasons.append("target_host does not equal the plan's target host")
    if receipt.get("source_head") != core.get("source_head"):
        reasons.append("source_head does not equal the plan's source head")
    return reasons


def _prepare_receipt_reasons(
    receipt: Any, *, core: dict[str, Any], now: Any = None
) -> list[str]:
    if not isinstance(receipt, dict) or receipt.get("schema_version") != (
        "s2_4_prepare_effect_receipt_v1"
    ):
        return ["must be an s2_4_prepare_effect_receipt_v1"]
    reasons = list(central_validator.validate_aiml_artifact(receipt, now=now))
    if receipt.get("terminal_status") != "PREPARED":
        reasons.append(
            f"terminal_status is {receipt.get('terminal_status')!r}; APPLY rejects a "
            "non-terminal or changed PREPARE lineage (§10.5 #30)"
        )
    if receipt.get("self_digest") != core.get("prepare_receipt_digest"):
        reasons.append("self_digest is not the prepare_receipt_digest bound into the plan core")
    if receipt.get("target_host") != core.get("target_host"):
        reasons.append("target_host does not equal the plan's target host")
    if receipt.get("source_head") != core.get("source_head"):
        reasons.append("source_head does not equal the plan's source head")
    return reasons


def derive_aggregate_success_status(
    *,
    probe_receipt_digests: Any,
    prepare_result_digest: Any,
    row_results: Any,
) -> dict[str, Any]:
    """§10.5 #24 的成功側:兩個 scoped probe receipt + PREPARE 結果 + **五個相異** row 結果。

    ``row_results`` 是 ``{class: (result_digest, postcheck_digest)}``;缺一列、重複 digest、
    或任一 digest 形狀不符即 ``AGGREGATE_SUCCESS_NOT_SATISFIED``(絕不半通過)。
    """

    reasons: list[str] = []
    digests = probe_receipt_digests if isinstance(probe_receipt_digests, dict) else {}
    for scope in PROBE_SCOPES:
        if _DIGEST_RE.fullmatch(str(digests.get(scope))) is None:
            reasons.append(f"aggregate success requires the terminal {scope} probe receipt digest")
    if len({digests.get(scope) for scope in PROBE_SCOPES}) != len(PROBE_SCOPES):
        reasons.append("the two scoped probe receipt digests must be distinct")
    if _DIGEST_RE.fullmatch(str(prepare_result_digest)) is None:
        reasons.append("aggregate success requires the PREPARE result digest")
    results = row_results if isinstance(row_results, dict) else {}
    if sorted(results) != sorted(APPLY_ROW_ORDER):
        reasons.append(
            "aggregate success requires all five distinct APPLY component results "
            f"{list(APPLY_ROW_ORDER)} (got {sorted(results)})"
        )
    else:
        # 「五個相異結果」必須在**兩側**都成立:只去重 result digest 時,五 row 共用同一份
        # postcheck 仍能滿足 aggregate——那正是「一次獨立驗證被當成五次」的形狀。
        seen_results: set[str] = set()
        seen_postchecks: set[str] = set()
        for name in APPLY_ROW_ORDER:
            pair = results[name]
            if not isinstance(pair, (tuple, list)) or len(pair) != 2:
                reasons.append(f"{name} result must be a (result_digest, postcheck_digest) pair")
                continue
            for value in pair:
                if _DIGEST_RE.fullmatch(str(value)) is None:
                    reasons.append(f"{name} result carries an invalid digest")
            if pair[0] in seen_results:
                reasons.append(
                    f"{name} result_digest duplicates another row's result; five DISTINCT "
                    "component results are required"
                )
            if pair[1] in seen_postchecks:
                reasons.append(
                    f"{name} postcheck_digest duplicates another row's postcheck; five DISTINCT "
                    "independent component postchecks are required (one verification re-used "
                    "five times is one verification)"
                )
            seen_results.add(pair[0])
            seen_postchecks.add(pair[1])
    return {
        "status": "AGGREGATE_SUCCESS_SATISFIED" if not reasons else (
            "AGGREGATE_SUCCESS_NOT_SATISFIED"
        ),
        "reasons": reasons,
    }
