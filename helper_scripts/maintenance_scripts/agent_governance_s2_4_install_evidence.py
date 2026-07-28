#!/usr/bin/env python3
"""S2.4(WP4·W4b)aggregate APPLY 的**證據**葉——新鮮度、平台背書、殘留觀測、durable 證據集。

依 §10.1.1 的 2000 行治理規約與 :mod:`agent_governance_s2_4_install_driver` 分家。四組內容:

1. **§9 證據新鮮度**(:func:`derive_apply_remaining_ttls`)——``remaining_ttls`` 自此由**每一份
   證據自己的** ``expires_at - now`` 導出;caller 遞交的值只能把界**收緊**,永遠不能放寬。
   過去它整包由 caller 自報,於是一份過期一年的 probe receipt 仍能換到 APPLY。
2. **§10.2 平台背書**(``s2_4_install_apply_attestation_v1``)——APPLIED_INACTIVE 的唯一鑰匙。
   鏡 S2.0 的 ``pg_observer_bootstrap_apply_attestation_v1``:專屬 attestor identity + namespace、
   同一把 §9.1 信任根、真 SSHSIG 驗證、exact-plan 綁定、``reobserved == applied``,新鮮度錨在
   **已簽的** ``trusted_host_time`` 而非 caller 的 ``now``。自報 ``evidence_class`` 不再是鑰匙。
3. **殘留觀測**(:func:`observe_install_residue`)——把「觀測不到」與「觀測到 inactive」拆成兩件
   事(``OBSERVATION_UNAVAILABLE`` vs ``OBSERVED_ACTIVE``/``OBSERVED_INACTIVE``),並在成功路徑
   要求 ``loaded and inactive and not enabled`` 的**正面**觀測。
4. **durable 證據集**(:func:`commit_install_evidence_set`)——把 step results / rollback /
   reconcile / residue 以同一套 temp→fsync→rename→parent-fsync 紀律落盤,於是「哪幾列施作過」
   在交易結束後仍是 durable 事實,而非只存在記憶體裡的 verdict 欄位。

零 authority:本葉不簽發任何 production 判定,九 authority 恆 false;所有主機動作經注入 driver。
"""
from __future__ import annotations

import hmac
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
PROGRAM_CODE_DIR = REPO_ROOT / "program_code"
for _candidate in (HELPER_DIR, ML_TRAINING_DIR, PROGRAM_CODE_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import aiml_gate_receipt_validator as central_validator  # noqa: E402
import agent_governance_aiml_trusted_host as _trusted_host  # noqa: E402
import agent_governance_s2_4_component as _component  # noqa: E402
import agent_governance_s2_4_journal as _journal  # noqa: E402
import agent_governance_s2_4_permit as _permit  # noqa: E402
from aiml_gate_receipt_schema_core import (  # noqa: E402
    S2_4_COMMITTED_SOURCE_IDENTITY_PATHS,
    commit_blob_bytes,
    resolve_facade,
)
from agent_governance_s2_4_install_plan import (  # noqa: E402
    APPLY_ROW_ORDER, aggregate_rollback_digest,
)
from agent_governance_s2_4_reconcile import InstallDriverContractError  # noqa: E402

canonical_digest = central_validator.canonical_digest
artifact_self_digest = central_validator.artifact_self_digest
redact_driver_error = _component.redact_driver_error
_DIGEST_RE = _component._DIGEST_RE
_ALL_FALSE_PRODUCTION_FLAGS = dict(_component._ALL_FALSE_PRODUCTION_FLAGS)
# aggregate 證據 artifact 的 TTL(§9 的觀測窗;與 install_driver 逐字同值)。
INSTALL_EVIDENCE_TTL_SECONDS = 900
# §5.1 六個 typed step ↔ 五個 v2 class(見 install_driver 的同名常量說明)。
APPLY_ROW_STEP_INDEX = {
    "HOST_IDENTITY_INSTALL": 0,
    "PG_ROLE_ACL_MIGRATION": 1,
    "CREDENTIAL_INSTALL": 2,
    "LEARNING_RUNTIME": 3,
    "ENGINE_SCANNER": 5,
}


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def resolve_now(now: Any) -> datetime | None:
    """把 caller 的 ``now`` 解析成 aware datetime;無法解析回 ``None``(呼叫端 fail-closed)。"""

    if now is None:
        return datetime.now(timezone.utc)
    if isinstance(now, datetime):
        return now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    try:
        return central_validator._parse_timestamp(str(now))
    except Exception:  # noqa: BLE001
        return None


def _expires_at(artifact: Any) -> datetime | None:
    if not isinstance(artifact, dict):
        return None
    try:
        return central_validator._parse_timestamp(str(artifact["expires_at"]))
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# 1) §9 證據新鮮度:remaining_ttls 由每一份證據自己的 expires_at 導出
# --------------------------------------------------------------------------- #
# §9 的 APPLY bound term ↔ 該 term 真正指的那一份證據。每一項都是 aggregate **手上就有**的
# artifact,故它們的剩餘 TTL 不需要(也不接受)caller 自報。
APPLY_TTL_TERM_EVIDENCE = {
    "dependency_effect_receipt_remaining_ttl": "PREPARE_SANDBOX capability-probe receipt",
    "install_intent_remaining_ttl": "the install plan and its five component intents",
    "installed_unit_probe_receipt_remaining_ttl": "INSTALLED_UNIT capability-probe receipt",
    "operator_authorization_remaining_ttl": "apply-aggregate operator permit",
    "pg_migration_authorization_remaining_ttl": "PG-migration operator permit",
    "prepared_bundle_remaining_ttl": "PREPARE effect receipt / prepared install bundle",
    "topology_attestation_remaining_ttl": "PG topology attestation",
}
TTL_DERIVATION_STATUS_DERIVED = "APPLY_EVIDENCE_TTLS_DERIVED"
TTL_DERIVATION_STATUS_REJECTED = "APPLY_EVIDENCE_TTLS_REJECTED"


def derive_apply_remaining_ttls(
    *,
    plan: Any,
    component_intents: Any,
    probe_receipts: Any,
    prepare_effect_receipt: Any,
    authorizations: Any,
    row_payloads: Any,
    now: Any,
    caller_remaining_ttls: Any = None,
) -> dict[str, Any]:
    """§9:由每一份證據的 ``expires_at - now`` 導出 APPLY 的 remaining TTL(caller 只能收緊)。

    E10:每一個 bound term **必須**有導出來源。``topology_attestation_remaining_ttl`` 是唯一一個
    來源只出現在 PG row 選配 payload 裡的 term,於是「不遞交 topology_attestation + 自報
    ``10**9``」過去能讓 §9 的預算不等式在一個**憑空捏造**的界上通過——而那個界正是
    ``PG_ROLE_ACL_MIGRATION`` 的governing TTL,它在 ``HOST_IDENTITY_INSTALL`` 已經動過主機之後
    才會被真正檢查。caller 的值只能把界收**緊**;沒有導出來源時它就不是「收緊」,而是那個界的
    **唯一**來源——那等於 caller 自證新鮮度。故此處 typed 拒,零變更。
    """

    outcome: dict[str, Any] = {
        "status": TTL_DERIVATION_STATUS_REJECTED,
        "reasons": [],
        "derived": {},
        "effective": {},
        "caller_supplied": {},
        "expired_evidence": [],
        "underived_terms": [],
    }
    moment = resolve_now(now)
    if moment is None:
        outcome["reasons"] = [
            "the APPLY evidence freshness window cannot be derived: `now` is unparseable"
        ]
        return outcome
    payloads = row_payloads if isinstance(row_payloads, dict) else {}
    pg_payload = payloads.get("PG_ROLE_ACL_MIGRATION")
    runtime_payload = payloads.get("LEARNING_RUNTIME")
    probes = probe_receipts if isinstance(probe_receipts, dict) else {}
    permits = authorizations if isinstance(authorizations, dict) else {}
    intents = component_intents if isinstance(component_intents, dict) else {}
    sources: dict[str, list[Any]] = {
        "dependency_effect_receipt_remaining_ttl": [probes.get("PREPARE_SANDBOX")],
        "install_intent_remaining_ttl": [plan] + [
            intents[key] for key in sorted(intents)
        ],
        "installed_unit_probe_receipt_remaining_ttl": [probes.get("INSTALLED_UNIT")],
        "operator_authorization_remaining_ttl": [permits.get("apply_aggregate")],
        "pg_migration_authorization_remaining_ttl": [permits.get("pg_migration")],
        "prepared_bundle_remaining_ttl": [
            prepare_effect_receipt,
            (runtime_payload or {}).get("prepared_bundle")
            if isinstance(runtime_payload, dict) else None,
        ],
        "topology_attestation_remaining_ttl": [
            (pg_payload or {}).get("topology_attestation")
            if isinstance(pg_payload, dict) else None
        ],
    }
    caller = caller_remaining_ttls if isinstance(caller_remaining_ttls, dict) else {}
    for term in _permit.APPLY_TTL_BOUND_TERMS:
        expiries = [_expires_at(item) for item in sources.get(term, [])]
        expiries = [value for value in expiries if value is not None]
        if expiries:
            seconds = int((min(expiries) - moment).total_seconds())
            outcome["derived"][term] = seconds
            if seconds <= 0:
                outcome["expired_evidence"].append(term)
                outcome["reasons"].append(
                    f"{APPLY_TTL_TERM_EVIDENCE.get(term, term)} is expired at the observed "
                    f"time ({seconds}s remaining); §9.2/§10.5 #28 forbid refreshing expired "
                    "runtime/topology/prepare/auth evidence by reference"
                )
        else:
            # E10:沒有導出來源 = 這個界沒有任何證據支持它。
            outcome["underived_terms"].append(term)
            outcome["reasons"].append(
                f"the §9 APPLY bound term {term!r} has no derived source: "
                f"{APPLY_TTL_TERM_EVIDENCE.get(term, term)} was not supplied, so its remaining "
                "TTL would come only from the caller. A caller-supplied value may only TIGHTEN "
                "a derived bound; it can never BE the bound (§6 step 9 / §9.2)"
            )
        if term in caller:
            try:
                outcome["caller_supplied"][term] = int(caller[term])
            except (TypeError, ValueError):
                outcome["reasons"].append(
                    f"caller-supplied remaining_ttls[{term!r}] is not an integer"
                )
                continue
    for term in _permit.APPLY_TTL_BOUND_TERMS:
        candidates = [
            value for value in (
                outcome["derived"].get(term), outcome["caller_supplied"].get(term)
            ) if value is not None
        ]
        if candidates:
            # caller 只能收緊(min);它永遠無法把一份過期證據講成還新鮮。
            outcome["effective"][term] = min(candidates)
    if outcome["reasons"]:
        return outcome
    outcome["status"] = TTL_DERIVATION_STATUS_DERIVED
    return outcome


# --------------------------------------------------------------------------- #
# 1b) §9.2 source-dependency ingress —— S2.4-AMEND-1(APPLY step (2b) 的唯一入口)
# --------------------------------------------------------------------------- #
# 進本閘的三族 = 有**已提交原身分**的 source-identity 族:原 receipt 由驗證端自 bound commit
# 的 S2_4_COMMITTED_SOURCE_IDENTITY_PATHS blob 讀出,caller 只遞交 refresh、無從替換原身分;
# forged refresh 不需要新機制——derive_dependency_refresh_status 的驗證端重算本身就使偽造
# 不可能(caller 遞交值不參與重算)。S1.3 無已提交原身分(表映到空 tuple),窗完全
# caller-authored;半吊子接線會製造「看似被閘、實則 caller 自選窗」的假保證,故 typed 記錄
# 缺口而不入閘(obligation DEPENDENCY_OBSERVATION_WINDOW_IS_CALLER_AUTHORED,owner=W6)。
S2_4_APPLY_GATED_DEPENDENCY_CLASSES = (
    "S2_2A_SOURCE_COMPATIBILITY", "S2_3_EXPECTED_IDENTITY", "S2_3_SEALED_BUILD",
)
S2_4_S1_3_NOT_GATED_REASON = (
    "S1_3_IDENTITY_CONTRACT has no committed original in this repository (its observation "
    "window is entirely caller-authored), so gating it here would assert a guarantee the "
    "verifier cannot derive; the gap stays typed under "
    "DEPENDENCY_OBSERVATION_WINDOW_IS_CALLER_AUTHORED (owner W6 key-custody)"
)
SOURCE_DEPENDENCIES_ADMITTED = "SOURCE_DEPENDENCIES_ADMITTED"
SOURCE_DEPENDENCIES_REJECTED = "SOURCE_DEPENDENCIES_REJECTED"


def load_committed_source_identity(
    dependency_class: str, *, repo_root: Path = REPO_ROOT,
) -> dict[str, Any] | None:
    """自 bound commit 讀回該族的**權威**已提交原身分(讀不回 ``None`` = fail-closed)。

    多版並存時取表序最末者(表序即版本序:S2.2A v1→v2,最新者為現行身分)——選擇是
    code-owned 的,caller 無從指定「用哪一份原身分」。
    """

    import json

    paths = S2_4_COMMITTED_SOURCE_IDENTITY_PATHS.get(dependency_class) or ()
    if not paths:
        return None
    authoritative = paths[-1]
    payload = commit_blob_bytes(Path(repo_root), [authoritative])[authoritative]
    if payload is None:
        return None
    try:
        loaded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def derive_apply_source_dependency_admissions(
    *, repo_root: Path = REPO_ROOT, now: Any = None, dependency_refreshes: Any = None,
) -> dict[str, Any]:
    """§9.2 進 APPLY 的唯一 ingress(step (2b);純 precheck,零 driver、零 mutation)。

    回 ``{"status": SOURCE_DEPENDENCIES_ADMITTED | SOURCE_DEPENDENCIES_REJECTED,
    "reasons": [...],
    "dependency_refresh_digests": {class: refresh self_digest | None},  # None = FRESH
    "s1_3_not_gated_reason": ...}``。``dependency_refresh_digests`` 恰為 terminal
    ``s2_4_install_effect_receipt_v1`` 的同名欄位值(§3 的 DEPENDENCY-REFRESH 綁定);
    EXPIRED_NO_REFRESH / REJECTED 不會有 receipt,故三值(null/digest/無 receipt)窮盡。
    §9.2 的細分 typed 狀態進 reasons;aggregate 終端沿用 PRECHECK_FAILED(§10.2 凍結
    enum 不加不減,PRECHECK_FAILED 精確表達「第一次變更之前的 typed 拒絕」)。
    """

    verdict: dict[str, Any] = {
        "status": SOURCE_DEPENDENCIES_REJECTED,
        "reasons": [],
        "dependency_refresh_digests": {
            cls: None for cls in S2_4_APPLY_GATED_DEPENDENCY_CLASSES
        },
        "s1_3_not_gated_reason": S2_4_S1_3_NOT_GATED_REASON,
    }
    reasons: list[str] = verdict["reasons"]
    if dependency_refreshes is not None and not isinstance(dependency_refreshes, dict):
        reasons.append(
            "dependency_refreshes must be a mapping of dependency class -> one refresh "
            "attestation (§9.2)"
        )
        return verdict
    supplied = dependency_refreshes if isinstance(dependency_refreshes, dict) else {}
    unknown = sorted(set(supplied) - set(S2_4_APPLY_GATED_DEPENDENCY_CLASSES))
    if unknown:
        reasons.append(
            f"dependency_refreshes names classes outside the closed APPLY-gated set "
            f"{unknown}; never-refreshable evidence takes no refresh and S1.3 is not gated "
            "here (§9.2 / §10.5 #28)"
        )
        return verdict
    digests: dict[str, Any] = {}
    facade = resolve_facade()
    for cls in S2_4_APPLY_GATED_DEPENDENCY_CLASSES:
        original = load_committed_source_identity(cls, repo_root=Path(repo_root))
        if original is None:
            digests[cls] = None
            reasons.append(
                f"{cls}: the committed source identity could not be read from the bound "
                "commit; a §9.2 verdict is only derived over the committed artifact "
                "(fail-closed)"
            )
            continue
        outcome = facade.derive_source_dependency_admission_status(
            evidence_class=cls, receipt=original, refresh=supplied.get(cls),
            now=now, repo_root=Path(repo_root),
        )
        if outcome["status"] == facade.SOURCE_DEPENDENCY_STATUS_FRESH:
            digests[cls] = None
        elif outcome["status"] == facade.SOURCE_DEPENDENCY_STATUS_ADMITTED_BY_REFRESH:
            digests[cls] = artifact_self_digest(supplied[cls])
        else:
            digests[cls] = None
            detail = "; ".join(outcome["reasons"]) or "§9.2 refused the source identity"
            reasons.append(f"{cls}: {outcome['status']} — {detail}")
    verdict["dependency_refresh_digests"] = digests
    if reasons:
        return verdict
    verdict["status"] = SOURCE_DEPENDENCIES_ADMITTED
    return verdict


# --------------------------------------------------------------------------- #
# 2) §10.2 apply-time platform attestation(APPLIED_INACTIVE 的唯一鑰匙)
# --------------------------------------------------------------------------- #
# pre-approval 的 operator permit 是「apply **之前**」對 exact plan 的簽核;apply attestation 則是
# 「apply **之後**」綁定實觀 row 結果 + 真 trusted_host_time 的 post-apply 證據(只有 apply 跑完
# 才可知)。共用一把 §9.1 實體信任根鑰,但以**專屬** attestor identity + namespace 做 domain
# separation:ssh-keygen -Y verify 綁 namespace,故一張 permit SSHSIG 不可被當成 attestation 重放。
APPLY_ATTESTATION_SCHEMA_VERSION = "s2_4_install_apply_attestation_v1"
APPLY_ATTESTOR_IDENTITY = "aiml-s2-4-install-attestor-v1"
APPLY_ATTESTATION_NAMESPACE = "arcane-equilibrium-aiml-s2-4-install-apply"
MAX_APPLY_ATTESTATION_TTL_SECONDS = 900
APPLY_ATTESTATION_FIELDS = (
    "schema_version",
    "attestor_identity",
    "attestor_fingerprint",
    "signature_namespace",
    "plan_id",
    "plan_core_digest",
    "idempotency_key",
    "source_head",
    "target_host",
    "applier_node",
    "verifier_node",
    "applied_row_results_digest",
    "reobserved_row_results_digest",
    "installed_unit_state_digest",
    "evidence_class",
    "trusted_host_time",
    "attestation_expires_at",
    "attestation_digest",
)
ATTESTATION_STATUS_VERIFIED = "APPLY_ATTESTATION_VERIFIED"
ATTESTATION_STATUS_ABSENT = "APPLY_ATTESTATION_ABSENT"
ATTESTATION_STATUS_REJECTED = "APPLY_ATTESTATION_REJECTED"


def apply_attestation_digest(attestation: dict[str, Any]) -> str:
    """attestation 的自指 digest(排除 ``attestation_digest`` 自身)。"""

    return canonical_digest(
        {key: value for key, value in attestation.items() if key != "attestation_digest"}
    )


def applied_row_results_digest(row_results: Any) -> str:
    """五 row 的 (result, postcheck) digest 對的 domain-separated 投影(attestation 綁的實觀)。"""

    results = row_results if isinstance(row_results, dict) else {}
    return canonical_digest({
        "domain": "arcane-equilibrium-aiml-s2-4-install-applied-row-results-v1",
        "rows": [
            {
                "component_effect_class": name,
                "result_digest": results[name][0],
                "postcheck_digest": results[name][1],
            }
            for name in sorted(results)
        ],
    })


def build_s2_4_install_apply_attestation(
    *,
    plan: dict[str, Any],
    applier_node: str,
    verifier_node: str,
    row_results: dict[str, Any],
    installed_unit_state: dict[str, Any],
    trusted_host_time: str,
    evidence_class: str = "PLATFORM_ATTESTED",
    ttl_seconds: int = MAX_APPLY_ATTESTATION_TTL_SECONDS,
) -> dict[str, Any]:
    """組出要簽的 canonical ``s2_4_install_apply_attestation_v1``(真簽章在受信主機上產生)。"""

    facade = resolve_facade()
    moment = central_validator._parse_timestamp(str(trusted_host_time))
    results_digest = applied_row_results_digest(row_results)
    attestation = {
        "schema_version": APPLY_ATTESTATION_SCHEMA_VERSION,
        "attestor_identity": APPLY_ATTESTOR_IDENTITY,
        "attestor_fingerprint": facade.S2_4_OPERATOR_TRUST_ROOT_FINGERPRINT,
        "signature_namespace": APPLY_ATTESTATION_NAMESPACE,
        "plan_id": plan["plan_id"],
        "plan_core_digest": plan["core_digest"],
        "idempotency_key": plan["idempotency_key"],
        "source_head": plan["core"]["source_head"],
        "target_host": plan["core"]["target_host"],
        "applier_node": applier_node,
        "verifier_node": verifier_node,
        "applied_row_results_digest": results_digest,
        # T2:相異 verifier 於 apply 之後**再觀測**到的同一組 row 結果。
        "reobserved_row_results_digest": results_digest,
        "installed_unit_state_digest": canonical_digest(dict(installed_unit_state)),
        "evidence_class": evidence_class,
        "trusted_host_time": _iso(moment),
        "attestation_expires_at": _iso(moment + timedelta(seconds=int(ttl_seconds))),
    }
    attestation["attestation_digest"] = apply_attestation_digest(attestation)
    return attestation


def _attestation_signed_bytes(attestation: dict[str, Any]) -> bytes:
    return central_validator._canonical_bytes(attestation)


def derive_apply_attestation_status(
    attestation: Any,
    signature: Any,
    *,
    plan: dict[str, Any],
    applier_node: str,
    verifier_node: str,
    row_results: dict[str, Any],
    installed_unit_state: dict[str, Any],
    authorizations: dict[str, Any],
) -> dict[str, Any]:
    """§10.2:``APPLIED_INACTIVE`` 的 apply-time 密碼學閘(全過才回 VERIFIED)。

    對應五道:exact 欄位契約 + domain-separation 常量 + ``attestation_digest``(T1);exact-plan
    綁定與 applier≠verifier(T1);``reobserved == applied == <本次實觀>``(T2);§9.1 信任根指紋
    綁定 + 對 ``canonical_bytes(attestation)`` 的**真** SSHSIG 驗證(T1);新鮮度只由**已簽的**
    ``trusted_host_time`` 導出——必須落在兩張 permit 的窗內且在有界 attestation TTL 內(T5),
    caller 的 ``now`` 永遠不參與。裸 ``evidence_class`` 屬性自此不再是任何東西的鑰匙。
    """

    outcome: dict[str, Any] = {
        "status": ATTESTATION_STATUS_ABSENT,
        "reasons": [],
        "attestation_digest": None,
        "evidence_class": _component.EVIDENCE_CLASS_STRUCTURAL_ONLY,
    }
    if attestation is None and signature is None:
        outcome["reasons"] = [
            "no s2_4_install_apply_attestation_v1 was produced by the driver; the source lane "
            "terminates at SOURCE_SIMULATION_PASS (§10.5 #13)"
        ]
        return outcome
    if not isinstance(attestation, dict):
        outcome["status"] = ATTESTATION_STATUS_REJECTED
        outcome["reasons"] = ["apply attestation must be an object"]
        return outcome
    if not isinstance(signature, (bytes, bytearray)):
        outcome["status"] = ATTESTATION_STATUS_REJECTED
        outcome["reasons"] = ["apply attestation signature must be raw SSHSIG bytes"]
        return outcome
    if tuple(sorted(attestation)) != tuple(sorted(APPLY_ATTESTATION_FIELDS)):
        outcome["status"] = ATTESTATION_STATUS_REJECTED
        outcome["reasons"] = ["apply attestation fields do not match the exact contract"]
        return outcome
    # E20:欄位名對了不代表**值**可 canonical 序列化。``apply_attestation_digest`` 與
    # ``_attestation_signed_bytes`` 都走 ``json.dumps(allow_nan=False)``,所以一個敵意 driver
    # 只要在 18 個正確鍵裡塞一個 ``NaN`` / ``inf`` / ``set`` / 自訂物件,就能讓 ValueError 或
    # TypeError 從 §10.2 的凍結 ABI 逸出——而這一刻主機已經完整變更且終端 journal 已 commit,
    # 正是最不能逸出的時刻。序列化能力在此先被證明,不能證明就是 typed 拒。
    try:
        _attestation_signed_bytes(attestation)
    except (TypeError, ValueError) as error:
        outcome["status"] = ATTESTATION_STATUS_REJECTED
        outcome["reasons"] = [
            "apply attestation is not canonically serializable "
            f"({redact_driver_error(error)}); it can neither be digested nor signature-checked"
        ]
        return outcome
    facade = resolve_facade()
    errors: list[str] = []
    for field, expected in (
        ("schema_version", APPLY_ATTESTATION_SCHEMA_VERSION),
        ("attestor_identity", APPLY_ATTESTOR_IDENTITY),
        ("signature_namespace", APPLY_ATTESTATION_NAMESPACE),
        ("attestor_fingerprint", facade.S2_4_OPERATOR_TRUST_ROOT_FINGERPRINT),
    ):
        if attestation.get(field) != expected:
            errors.append(f"apply attestation {field} is invalid")
    if attestation.get("evidence_class") not in _component.EVIDENCE_CLASS_ATTESTED:
        errors.append("apply attestation evidence_class is not an attested class")
    if attestation.get("attestation_digest") != apply_attestation_digest(attestation):
        errors.append("apply attestation digest mismatch")
    # T1 —— exact plan 綁定(一張 attestation 只認一份 plan)。
    for field, expected in (
        ("plan_id", plan.get("plan_id")),
        ("plan_core_digest", plan.get("core_digest")),
        ("idempotency_key", plan.get("idempotency_key")),
        ("source_head", (plan.get("core") or {}).get("source_head")),
        ("target_host", (plan.get("core") or {}).get("target_host")),
    ):
        if attestation.get(field) != expected:
            errors.append(f"apply attestation {field} differs from the exact install plan")
    if attestation.get("applier_node") != applier_node:
        errors.append("apply attestation applier_node differs from the applier that ran")
    if attestation.get("verifier_node") != verifier_node:
        errors.append(
            "apply attestation verifier_node differs from the independent aggregate verifier"
        )
    if not attestation.get("verifier_node") or (
        attestation.get("verifier_node") == attestation.get("applier_node")
    ):
        errors.append("apply attestation verifier_node must differ from the applier")
    # T2 —— reobserved == applied == 本次實觀。
    observed_digest = applied_row_results_digest(row_results)
    if not (
        attestation.get("reobserved_row_results_digest")
        == attestation.get("applied_row_results_digest")
        == observed_digest
    ):
        errors.append(
            "apply attestation reobserved_row_results_digest must equal "
            "applied_row_results_digest and the row results this transaction actually produced"
        )
    if attestation.get("installed_unit_state_digest") != canonical_digest(
        dict(installed_unit_state)
    ):
        errors.append(
            "apply attestation installed_unit_state_digest does not equal the observed "
            "installed unit state"
        )
    # T1 —— §9.1 信任根指紋綁定 + 真 SSHSIG。
    public_key = facade.S2_4_OPERATOR_TRUST_ROOT_PUBLIC_KEY
    try:
        actual_fingerprint = _trusted_host.ssh_public_key_fingerprint(public_key)
    except ValueError:
        actual_fingerprint = ""
    if not hmac.compare_digest(
        actual_fingerprint, str(facade.S2_4_OPERATOR_TRUST_ROOT_FINGERPRINT)
    ):
        errors.append("apply attestation trust-root fingerprint mismatch")
    if not _trusted_host._verify_ssh_signature(
        _attestation_signed_bytes(attestation),
        bytes(signature),
        public_key=public_key,
        identity=APPLY_ATTESTOR_IDENTITY,
        namespace=APPLY_ATTESTATION_NAMESPACE,
    ):
        errors.append("apply attestation SSH signature is invalid")
    # T5 —— 新鮮度只由**已簽的** trusted_host_time 導出(caller 的 now 永不參與)。
    try:
        trusted_time = central_validator._parse_timestamp(
            str(attestation["trusted_host_time"])
        )
        attestation_expires = central_validator._parse_timestamp(
            str(attestation["attestation_expires_at"])
        )
        if not trusted_time < attestation_expires:
            errors.append(
                "apply attestation trusted_host_time must precede attestation_expires_at"
            )
        if (attestation_expires - trusted_time).total_seconds() > (
            MAX_APPLY_ATTESTATION_TTL_SECONDS
        ):
            errors.append("apply attestation TTL exceeds its ceiling")
        for profile_key in ("apply_aggregate", "pg_migration"):
            permit = (authorizations or {}).get(profile_key)
            if not isinstance(permit, dict):
                errors.append(
                    f"apply attestation requires the {profile_key} permit window to anchor "
                    "its freshness"
                )
                continue
            issued = central_validator._parse_timestamp(str(permit["issued_at"]))
            expires = central_validator._parse_timestamp(str(permit["expires_at"]))
            if not issued <= trusted_time < expires:
                errors.append(
                    "apply attestation trusted_host_time is outside the "
                    f"{profile_key} permit window"
                )
    except (KeyError, TypeError, ValueError):
        errors.append("apply attestation timestamps are invalid")
    if errors:
        outcome["status"] = ATTESTATION_STATUS_REJECTED
        outcome["reasons"] = errors
        return outcome
    outcome["status"] = ATTESTATION_STATUS_VERIFIED
    outcome["attestation_digest"] = attestation["attestation_digest"]
    outcome["evidence_class"] = attestation["evidence_class"]
    return outcome


def collect_driver_apply_attestation(driver: Any) -> dict[str, Any]:
    """從注入 driver 取出 apply attestation(沒有該面 = 沒有背書,絕不當成通過)。"""

    surface = getattr(driver, "apply_attestation", None)
    if not callable(surface):
        return {"attestation": None, "signature": None, "reasons": []}
    try:
        produced = surface()
    except Exception as error:  # noqa: BLE001
        return {
            "attestation": None, "signature": None,
            "reasons": [
                f"the apply attestation could not be obtained: {redact_driver_error(error)}"
            ],
        }
    if not isinstance(produced, dict):
        return {
            "attestation": None, "signature": None,
            "reasons": ["the apply attestation surface did not return an object"],
        }
    return {
        "attestation": produced.get("attestation"),
        "signature": produced.get("signature"),
        "reasons": [],
    }


# --------------------------------------------------------------------------- #
# 3) 殘留觀測:「觀測不到」與「觀測到 inactive」是兩件事
# --------------------------------------------------------------------------- #
RESIDUE_OBSERVED_INACTIVE = "INSTALLED_UNIT_OBSERVED_INACTIVE"
RESIDUE_OBSERVED_ACTIVE = "INSTALLED_UNIT_OBSERVED_ACTIVE"
RESIDUE_OBSERVED_ABSENT = "INSTALLED_UNIT_OBSERVED_ABSENT"
RESIDUE_OBSERVATION_UNAVAILABLE = "INSTALLED_UNIT_OBSERVATION_UNAVAILABLE"
# 讀取失敗時的有界重試次數:一次瞬時 TimeoutError 不得把一筆已驗證完成的安裝拆掉。
RESIDUE_OBSERVATION_ATTEMPTS = 3


def observe_install_residue(
    driver: Any, probe_digests: dict[str, Any], *, attempts: int = RESIDUE_OBSERVATION_ATTEMPTS
) -> dict[str, Any]:
    """每一條終端路徑的殘留觀測(有界重試;讀不到**不等於**觀測到 active)。

    ``observation_status`` 是 typed 的四分:``OBSERVED_INACTIVE`` / ``OBSERVED_ACTIVE`` /
    ``OBSERVED_ABSENT`` / ``OBSERVATION_UNAVAILABLE``。呼叫端據此分流:讀不到即
    ``RECOVERY_REQUIRED`` 且**不補償**——把一份已完整驗證的安裝(PG role/ACL/HBA、credential
    slot、uid/gid、三棵 runtime 樹)因為一次讀取失敗而拆掉,嚴格劣於原封不動留著。
    """

    residue: dict[str, Any] = {
        # 「無倖存 probe unit」由兩份 terminal probe receipt 的 zero_residue_verified 在任何
        # 變更之前證明,且 aggregate 交易在構造上沒有 probe 生命週期面。此處只轉述那份證據,
        # 不再寫一個沒有讀者的 probe_unit_surviving 常量。
        "probe_receipt_digests": dict(probe_digests),
        "probe_residue_evidence": "terminal_probe_receipt_zero_residue_verified",
        "observation_status": RESIDUE_OBSERVATION_UNAVAILABLE,
        "installed_unit_inactive": None,
        "unit_state": {"loaded": False, "disabled": True, "inactive": True},
        "observation_attempts": 0,
        "reasons": [],
    }
    last_error: str | None = None
    observed: Any = None
    for _attempt in range(max(1, int(attempts))):
        residue["observation_attempts"] += 1
        try:
            observed = driver.observe_installed_unit_state()
        except _journal.JournalCrash:
            raise
        except Exception as error:  # noqa: BLE001
            last_error = redact_driver_error(error)
            continue
        last_error = None
        break
    if last_error is not None:
        residue["reasons"] = [
            "the installed unit state could not be observed after "
            f"{residue['observation_attempts']} bounded attempts: {last_error}; "
            "'could not observe' is NOT 'observed active' — the transaction terminates at "
            "RECOVERY_REQUIRED and compensates nothing (§5.4: never tear down a correct "
            "install on a read failure)"
        ]
        return residue
    if observed is None:
        residue["observation_status"] = RESIDUE_OBSERVED_ABSENT
        residue["installed_unit_inactive"] = True
        residue["unit_state"] = {"loaded": False, "disabled": True, "inactive": True}
        return residue
    if not isinstance(observed, dict):
        residue["reasons"] = ["the installed unit observation is not an object"]
        return residue
    active = bool(observed.get("active") or observed.get("ActiveState") == "active")
    enabled = bool(observed.get("enabled") or observed.get("UnitFileState") == "enabled")
    inactive = bool(observed.get("inactive") or observed.get("ActiveState") == "inactive")
    loaded = bool(observed.get("loaded") or observed.get("LoadState") == "loaded")
    residue["unit_state"] = {
        "loaded": loaded,
        "disabled": bool(
            observed.get("disabled") or observed.get("UnitFileState") == "disabled"
        ),
        "inactive": inactive,
    }
    residue["installed_unit_inactive"] = bool(inactive and not active and not enabled)
    residue["observation_status"] = (
        RESIDUE_OBSERVED_INACTIVE if residue["installed_unit_inactive"]
        else RESIDUE_OBSERVED_ACTIVE
    )
    if not residue["installed_unit_inactive"]:
        residue["reasons"] = [
            "the installed engine-scanner unit is not loaded/disabled/inactive "
            f"(active={active}, enabled={enabled}, inactive={inactive})"
        ]
    return residue


def success_path_residue_reasons(residue: dict[str, Any]) -> list[str]:
    """成功路徑要求的是**正面**觀測:``loaded`` 且 ``inactive`` 且未 enabled。

    ``absent ⇒ 絕不可能 active`` 只在補償路徑成立(補償把 unit 移除了)。放在成功路徑上,
    它讓一筆「什麼都沒裝」的交易也能被記成終端成功。
    """

    if residue.get("observation_status") == RESIDUE_OBSERVED_INACTIVE and (
        residue.get("unit_state", {}).get("loaded") is True
    ):
        return []
    if residue.get("observation_status") == RESIDUE_OBSERVATION_UNAVAILABLE:
        return list(residue.get("reasons") or []) + [
            "a successful S2.4 apply requires an observed loaded/disabled/inactive unit; an "
            "unobservable unit is never a success"
        ]
    return list(residue.get("reasons") or []) + [
        "the success path requires the installed unit to be OBSERVED loaded, disabled and "
        f"inactive (observation_status={residue.get('observation_status')!r}, "
        f"unit_state={residue.get('unit_state')!r}); an absent unit means the transaction "
        "installed nothing and can never be a terminal success"
    ]


# --------------------------------------------------------------------------- #
# 4) durable 證據集(§5.2 同一套 temp→fsync→rename→parent-fsync 紀律)
# --------------------------------------------------------------------------- #
EVIDENCE_SET_SCHEMA_VERSION = "s2_4_install_evidence_set_v1_informal"
EVIDENCE_SET_PARENT = _journal.INSTALL_JOURNAL_PARENT
EVIDENCE_SET_STATUS_COMMITTED = "INSTALL_EVIDENCE_SET_COMMITTED"
EVIDENCE_SET_STATUS_UNAVAILABLE = "INSTALL_EVIDENCE_SET_UNAVAILABLE"


def install_evidence_set_path(plan_id: Any) -> str:
    """證據集的 exact 路徑(basename 由 plan_id 導出;caller 字串永不 join 進 root)。"""

    plan_id = str(plan_id)
    if _journal._PLAN_ID_RE.fullmatch(plan_id) is None:
        raise _journal.JournalContractError("install_evidence_set_plan_id_invalid")
    return f"{EVIDENCE_SET_PARENT}/{plan_id}.evidence.json"


def build_install_evidence_set(
    *,
    plan: dict[str, Any],
    terminal_status: str,
    step_results: list[dict[str, Any]],
    rollback: dict[str, Any] | None,
    journal: dict[str, Any] | None,
    reconcile: dict[str, Any] | None,
    residue: dict[str, Any] | None,
    receipt: dict[str, Any] | None,
    applied_rows: list[str],
    observed_at: str,
) -> dict[str, Any]:
    """把一筆交易的 durable 證據集組成 canonical 形(inner self-digest + outer checksum)。"""

    evidence = {
        "schema_version": EVIDENCE_SET_SCHEMA_VERSION,
        "plan_id": plan["plan_id"],
        "plan_core_digest": plan["core_digest"],
        "idempotency_key": plan["idempotency_key"],
        "terminal_status": terminal_status,
        "applied_rows": list(applied_rows),
        "step_results": list(step_results or []),
        "rollback": rollback,
        "journal_digest": (journal or {}).get("self_digest"),
        # §5.2:「沒有任何殘留」這句話必須同時綁 terminal journal、獨立殘留 postcheck **與**
        # 啟動 reconcile 的裁決——三者缺一,下游就無法從證據本身驗證它。
        "startup_reconcile_status": (reconcile or {}).get("status"),
        "startup_reconcile_digest": canonical_digest(reconcile) if reconcile else None,
        "residue_digest": canonical_digest(residue) if residue else None,
        "installed_unit_observation_status": (residue or {}).get("observation_status"),
        "effect_receipt_digest": (receipt or {}).get("self_digest"),
        "observed_at": observed_at,
    }
    evidence["self_digest"] = canonical_digest(evidence)
    evidence["outer_checksum"] = canonical_digest(
        {"inner": evidence["self_digest"], "domain": EVIDENCE_SET_SCHEMA_VERSION}
    )
    return evidence


def commit_install_evidence_set(
    file_driver: Any, evidence: dict[str, Any]
) -> dict[str, Any]:
    """把證據集 durable 落盤(與 journal/ledger 逐字同一套紀律與 0600/0700 前置)。"""

    if file_driver is None:
        return {"status": EVIDENCE_SET_STATUS_UNAVAILABLE, "reasons": [
            "the durable evidence-set write is reachable but authority-locked: no host file "
            "driver is present; EXTERNAL_VERIFICATION_PENDING with zero mutation"
        ]}
    destructive = _journal.assert_no_journal_destructive_surface(file_driver)
    if destructive:
        return {"status": EVIDENCE_SET_STATUS_UNAVAILABLE, "reasons": destructive}
    store = _journal.JournalStore(
        file_driver, journal_path=install_evidence_set_path(evidence["plan_id"])
    )
    parent_fd = None
    temp_fd = None
    temp_basename = _journal.journal_temp_basename(store.basename, attempt=store.attempts)
    store.attempts += 1
    try:
        parent_fd, reasons = store._open_parent()
        if reasons:
            return {"status": EVIDENCE_SET_STATUS_UNAVAILABLE, "reasons": reasons}
        try:
            temp = file_driver.create_temp_file(
                parent_fd=parent_fd, basename=temp_basename,
                flags=_journal.JOURNAL_TEMP_OPEN_FLAGS, mode=_journal.JOURNAL_FILE_MODE_BITS,
            )
        except FileExistsError:
            return {
                "status": EVIDENCE_SET_STATUS_UNAVAILABLE,
                "reasons": [
                    _journal._temp_residue_reason(store.parent_path, temp_basename)
                ],
            }
        temp_reasons = _journal._temp_file_precheck_reasons(
            temp, expected_device=store.bound_parent["device"]
        )
        if temp_reasons:
            return {"status": EVIDENCE_SET_STATUS_UNAVAILABLE, "reasons": temp_reasons}
        temp_fd = temp["fd"]
        payload = central_validator._canonical_bytes(evidence)
        written = file_driver.write_bytes(fd=temp_fd, payload=payload)
        if int(written) != len(payload):
            return {
                "status": EVIDENCE_SET_STATUS_UNAVAILABLE,
                "reasons": ["evidence-set temp write was short; refusing to rename it"],
            }
        file_driver.fsync_file(fd=temp_fd)
        recheck_reasons = store._reresolve_parent_reasons()
        if recheck_reasons:
            return {"status": EVIDENCE_SET_STATUS_UNAVAILABLE, "reasons": recheck_reasons}
        file_driver.atomic_rename(
            parent_fd=parent_fd, from_basename=temp_basename, to_basename=store.basename
        )
        file_driver.fsync_parent_dir(fd=parent_fd)
    except _journal.JournalCrash:
        raise
    except Exception as error:  # noqa: BLE001
        return {
            "status": EVIDENCE_SET_STATUS_UNAVAILABLE,
            "reasons": [
                f"durable evidence-set write failed: {redact_driver_error(error)}"
            ],
        }
    finally:
        for fd in (temp_fd, parent_fd):
            if fd is None:
                continue
            try:
                file_driver.close(fd=fd)
            except Exception:  # noqa: BLE001
                pass
    return {"status": EVIDENCE_SET_STATUS_COMMITTED, "reasons": []}


def install_evidence_abi_projection() -> dict[str, Any]:
    """W4 exported-ABI 折入的證據面(新鮮度 / 平台背書 / 殘留 / durable 證據集)。"""

    return {
        "apply_ttl_term_evidence": dict(APPLY_TTL_TERM_EVIDENCE),
        "apply_attestation_schema_version": APPLY_ATTESTATION_SCHEMA_VERSION,
        "apply_attestor_identity": APPLY_ATTESTOR_IDENTITY,
        "apply_attestation_namespace": APPLY_ATTESTATION_NAMESPACE,
        "apply_attestation_fields": list(APPLY_ATTESTATION_FIELDS),
        "apply_attestation_max_ttl_seconds": MAX_APPLY_ATTESTATION_TTL_SECONDS,
        "residue_observation_statuses": [
            RESIDUE_OBSERVED_ABSENT, RESIDUE_OBSERVED_ACTIVE, RESIDUE_OBSERVED_INACTIVE,
            RESIDUE_OBSERVATION_UNAVAILABLE,
        ],
        "residue_observation_attempts": RESIDUE_OBSERVATION_ATTEMPTS,
        "evidence_set_schema_version": EVIDENCE_SET_SCHEMA_VERSION,
        "evidence_set_parent": EVIDENCE_SET_PARENT,
    }


# --------------------------------------------------------------------------- #
# 5) aggregate 的證據 artifact builders(step result / postcheck / receipt / rollback)
# --------------------------------------------------------------------------- #
def _row_observation_digest(
    *, component_effect_class: str, component_intent_digest: str, admitted: bool
) -> str:
    """一 row 完成投影的 digest(WAL 的期望/觀測 post-state 同一形)。

    ``admitted`` 只在該 row 的**獨立** postcheck 通過(SATISFIED)或零變更 NOOP_VERIFIED 時為
    真——故此觀測值不是 applier 的自報,而是 row 級獨立 verifier 裁決的投影。
    """

    return canonical_digest({
        "component_effect_class": component_effect_class,
        "component_intent_digest": component_intent_digest,
        "row_admitted": bool(admitted),
    })


def _build_step_result(
    *,
    plan_id: str,
    component_effect_class: str,
    state: str,
    pre_state_digest: str,
    post_state_digest: str,
    task_owned_delta_digest: str,
    apply_evidence_digest: str | None,
    postcheck_evidence_digest: str | None,
    compensation_intent_digest: str | None,
    compensation_result_digest: str | None,
    observed_at: str,
) -> dict[str, Any]:
    result = {
        "schema_version": "s2_4_install_step_result_v1",
        "plan_id": plan_id,
        "step_index": APPLY_ROW_STEP_INDEX[component_effect_class],
        "component_effect_class": component_effect_class,
        "state": state,
        "pre_state_digest": pre_state_digest,
        "post_state_digest": post_state_digest,
        "task_owned_delta_digest": task_owned_delta_digest,
        "apply_evidence_digest": apply_evidence_digest,
        "postcheck_evidence_digest": postcheck_evidence_digest,
        "compensation_intent_digest": compensation_intent_digest,
        "compensation_result_digest": compensation_result_digest,
        "observed_at": observed_at,
    }
    result["self_digest"] = artifact_self_digest(result)
    return result


def _build_aggregate_postcheck(
    *,
    driver: Any,
    plan: dict[str, Any],
    applier_node: str,
    all_rows_admitted: bool,
    clock: Callable[[], datetime],
) -> tuple[dict[str, Any] | None, list[str]]:
    """相異 verifier 節點的 aggregate lineage postcheck(applier 不得自證)。"""

    try:
        observed = driver.aggregate_independent_postcheck(
            plan_id=plan["plan_id"], plan_core_digest=plan["core_digest"],
            applier_node=applier_node,
        )
    except Exception as error:  # noqa: BLE001
        return None, [
            f"independent aggregate postcheck failed: {redact_driver_error(error)}"
        ]
    if not isinstance(observed, dict):
        return None, ["independent aggregate postcheck did not return an object"]
    verifier_node = str(observed.get("verifier_node", ""))
    if not verifier_node or verifier_node == applier_node:
        return None, [
            "independent aggregate postcheck verifier_node must differ from the applier"
        ]
    capture = observed.get("verifier_capture_digest")
    if _DIGEST_RE.fullmatch(str(capture)) is None:
        return None, ["independent aggregate postcheck verifier_capture_digest is invalid"]
    flags = {
        field: bool(observed.get(field))
        for field in (
            "probe_lineage_verified", "prepare_lineage_verified", "plan_lineage_verified",
            "idempotency_verified", "pre_state_lineage_verified", "all_apply_rows_satisfied",
        )
    }
    at = clock()
    postcheck = {
        "schema_version": "s2_4_install_postcheck_v1",
        "status": "PASS" if all(flags.values()) else "FAIL",
        "plan_id": plan["plan_id"],
        "plan_core_digest": plan["core_digest"],
        "verifier_node": verifier_node,
        "applier_node": applier_node,
        **flags,
        "verifier_capture_digest": capture,
        "observed_at": _iso(at),
        "expires_at": _iso(at + timedelta(seconds=INSTALL_EVIDENCE_TTL_SECONDS)),
    }
    postcheck["self_digest"] = artifact_self_digest(postcheck)
    reasons: list[str] = []
    if postcheck["status"] != "PASS":
        reasons.append(
            "the independent aggregate postcheck FAILED on "
            f"{sorted(name for name, value in flags.items() if not value)}"
        )
    if flags["all_apply_rows_satisfied"] and not all_rows_admitted:
        reasons.append(
            "the independent verifier claims all five APPLY rows are satisfied while the "
            "applier observed at least one non-admitted row; the claim is refused"
        )
    reasons.extend(central_validator.validate_aiml_artifact(postcheck))
    return postcheck, reasons


def _build_install_effect_receipt(
    *,
    plan: dict[str, Any],
    status: str,
    authorizations: dict[str, Any],
    probe_receipt_digests: dict[str, Any],
    prepare_result_digest: str,
    prepare_postcheck_digest: str,
    dependency_refresh_digests: dict[str, Any],
    row_results: dict[str, tuple[str, str]],
    journal_digest: str,
    unit_state: dict[str, Any],
    evidence_class: str,
    trusted_host_time: str,
    clock: Callable[[], datetime],
) -> dict[str, Any]:
    # P2-1(E2 對抗審查):silent-FRESH 預設關閉。builder 只在 step (2b) admission 之後
    # 可達,其輸入必須**恰為** admission 導出的三 gated-class 映射(值 = None|sha256
    # digest);None/缺鍵/多鍵/非 digest 值一律 typed 契約拒(鏡 install_evidence_set_path
    # 的契約錯機制)——絕不把 falsy 輸入靜默寫成「三族全 FRESH」的 receipt 宣稱。
    if not isinstance(dependency_refresh_digests, dict) or set(
        dependency_refresh_digests
    ) != set(S2_4_APPLY_GATED_DEPENDENCY_CLASSES) or not all(
        value is None or (isinstance(value, str) and _DIGEST_RE.fullmatch(value))
        for value in dependency_refresh_digests.values()
    ):
        raise InstallDriverContractError(
            "install_receipt_dependency_refresh_digests_invalid"
        )
    at = clock()
    receipt = {
        "schema_version": "s2_4_install_effect_receipt_v1",
        "plan_id": plan["plan_id"],
        "plan_core_digest": plan["core_digest"],
        "idempotency_key": plan["idempotency_key"],
        "status": status,
        "aggregate_authorization_id": authorizations["apply_aggregate"]["authorization_id"],
        "aggregate_authorization_digest": authorizations["apply_aggregate"]["self_digest"],
        "pg_authorization_id": authorizations["pg_migration"]["authorization_id"],
        "pg_authorization_digest": authorizations["pg_migration"]["self_digest"],
        "prepare_sandbox_probe_receipt_digest": probe_receipt_digests["PREPARE_SANDBOX"],
        "installed_unit_probe_receipt_digest": probe_receipt_digests["INSTALLED_UNIT"],
        "prepare_result_digest": prepare_result_digest,
        "prepare_postcheck_digest": prepare_postcheck_digest,
        # S2.4-AMEND-1(§3/§9.2):null = 該族於 admission 時 SOURCE_DEPENDENCY_FRESH;
        # digest = 採信該過期身分的**那一份** refresh 的 self_digest(step (2b) 導出;
        # 形狀已由上方契約閘 fail-closed 驗過,此處只定序)。
        "dependency_refresh_digests": {
            cls: dependency_refresh_digests[cls]
            for cls in S2_4_APPLY_GATED_DEPENDENCY_CLASSES
        },
        "apply_row_results": [
            {
                "component_effect_class": name,
                "result_digest": row_results[name][0],
                "postcheck_digest": row_results[name][1],
            }
            for name in APPLY_ROW_ORDER
        ],
        "reverse_compensation_chain_digest": aggregate_rollback_digest(
            plan_id=plan["plan_id"]
        ),
        "journal_digest": journal_digest,
        "unit_state": dict(unit_state),
        "service_flags": {
            "service_enabled": False, "service_active": False,
            "service_started_by_s2_4": False,
        },
        "evidence_class": evidence_class,
        "production_authority_flags": dict(_ALL_FALSE_PRODUCTION_FLAGS),
        "source_head": plan["core"]["source_head"],
        "target_host": plan["core"]["target_host"],
        "trusted_host_time": trusted_host_time,
        "observed_at": _iso(at),
        "expires_at": _iso(at + timedelta(seconds=INSTALL_EVIDENCE_TTL_SECONDS)),
    }
    receipt["self_digest"] = artifact_self_digest(receipt)
    return receipt


def _build_install_rollback(
    *,
    plan: dict[str, Any],
    reverse_ops: list[dict[str, Any]],
    exact: bool,
    post_state_digest: str,
    daemon_reload_reasserted: bool,
    hba_reload_reasserted: bool,
    clock: Callable[[], datetime],
) -> dict[str, Any]:
    at = clock()
    rollback = {
        "schema_version": "s2_4_install_rollback_v1",
        "status": (
            _component.COMPENSATION_STATUS_EXACT if exact
            else _component.COMPENSATION_STATUS_RECOVERY_REQUIRED
        ),
        "plan_id": plan["plan_id"],
        "plan_core_digest": plan["core_digest"],
        "pre_state_digest": plan["core"]["pre_state_digest"],
        "post_state_digest": post_state_digest,
        "reverse_ops": list(reverse_ops),
        "ownership_aware": True,
        "exact_pre_state_restored": bool(exact),
        "daemon_reload_reasserted": bool(daemon_reload_reasserted),
        "hba_reload_reasserted": bool(hba_reload_reasserted),
        "observer_role_preserved": True,
        "no_secret_reconstructed": True,
        "observed_at": _iso(at),
        "expires_at": _iso(at + timedelta(seconds=INSTALL_EVIDENCE_TTL_SECONDS)),
    }
    rollback["self_digest"] = artifact_self_digest(rollback)
    return rollback
