"""S2.5(WP5)running-attestation seam 的中央委派葉(v3 分類器 + 五個 s2_5 schema 驗證)。

facade(``aiml_gate_receipt_validator``)在 2000 行治理門檻邊緣,故 S2.5 的中央閘分支下沉到
本葉:facade 只保留一個 ≤6 行的委派分支(``aiml_component_effect_classification_v3`` 與全部
``s2_5_*`` schema 進本葉的 :func:`validate_s2_5_artifact`)。

本葉承載三塊(design §5/§6):

1. **additive v3 component-effect 分類器** —— 兩個 class,同屬單一 ``WATCHDOG_ROLLBACK_TEST``
   effect lineage 的兩個 phase step(PM O-5 封閉裁定):
   ``ENGINE_SCANNER_SERVICE_START``(S2.5A)與 ``WATCHDOG_ROLLBACK_TEST``(S2.5B,兼 lineage
   名 = PROGRESS S2.5 row 的 Required effect 原名,不改)。v1/v2 矩陣與 frozen S0.3 classifier
   逐位元組不動,三個分類身分 digest 互相獨立。
2. **§9.2 never-refreshable 封閉表** —— S2.5 全部五個 artifact 屬 runtime 觀測類:證據只可
   重新觀測,永不可 refresh-by-reference(理由:running/attestation 證據描述的是一個活的
   runtime 瞬間,「引用刷新」等於宣稱舊瞬間仍然為真)。執法形制鏡
   ``derive_source_dependency_admission_status`` 的 never-refreshable 臂,typed status 常量
   直接複用 contracts 葉(不另造第二套詞彙)。
3. **中央閘的 s2_5 結構/整合/新鮮度驗** —— closed schema 之上補 schema 表達不了的比較:
   core_digest/start_id/self_digest 再導出、forbidden-intent-key 遞迴掃描、verifier≠applier、
   五維成功語義、observer/dead-man 新鮮窗、attested status 的 attestor SSHSIG 驗簽(唯一鑰匙;
   permit ≠ attestation)。

⚠ SOURCE-TRUTH 邊界:本葉的乾淨 ``[]`` 只證 receipt 的內部自洽 + 結構 + 離線驗簽結構,
「不」證明任何 unit 真的 enabled/running。production 的 RUNNING_ATTESTED/FINAL_ATTESTED 唯一
由驗簽通過的 trusted-host attestor 簽章解鎖,而 §9.1 私鑰不在 Mac 也不在 trade-core——
production 不可達的原因是 key custody,不是構造不可達。九項 authority 恆 false。
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiml_gate_receipt_schema_core import (
    SCHEMA_DIR,
    _load_schema,
    _now_text,
    _parse_timestamp,
    artifact_self_digest,
    canonical_digest,
)
from aiml_gate_receipt_s2_4_contracts import (
    DEPENDENCY_EVIDENCE_REOBSERVATION_REQUIRED,
    DEPENDENCY_REFRESH_BY_REFERENCE_FORBIDDEN,
    SOURCE_DEPENDENCY_STATUS_FRESH,
    SOURCE_DEPENDENCY_STATUS_REJECTED,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HELPER_DIR = _REPO_ROOT / "helper_scripts" / "maintenance_scripts"

# ── PM O-5 封閉裁定:phase → effect class 投影(單一 lineage 的兩個 phase step)────────
S2_5_EFFECT_LINEAGE = "WATCHDOG_ROLLBACK_TEST"
S2_5_PHASE_EFFECT_CLASS = {
    "S2_5A_START": "ENGINE_SCANNER_SERVICE_START",
    "S2_5B_FINAL": "WATCHDOG_ROLLBACK_TEST",
}
S2_5_UNIT_NAME = "arcane-equilibrium-aiml-engine-scanner.service"
S2_5_START_ID_PREFIX = "s2-5-"

# ── additive v3 component-effect 矩陣(design §6 O-5 表;v1/v2 bytes 不動)───────────
AIML_COMPONENT_EFFECT_CLASS_MATRIX_V3: dict[str, dict[str, Any]] = {
    "ENGINE_SCANNER_SERVICE_START": {
        "required_intent_fields": [
            "start_core", "s2_4_install_effect_receipt_digest", "attestation_window",
            "rollback_budget", "expiry",
        ],
        "recovery_contract": "s2_5_rollback_drill_receipt_v1(kind=ROLLBACK_TO_DISABLED)",
        "adapter_id": "s2_5_runtime_start_adapter_v1",
        "adapter_binding_status": "AUTHORITY_LOCKED_PRODUCTION_CAPABLE",
        "actor_node_id": "s2_5_host_service_actor",
        "independent_postcheck_node_id": "s2_5_running_postcheck_v1",
    },
    "WATCHDOG_ROLLBACK_TEST": {
        "required_intent_fields": [
            "start_core", "s2_1_drill_receipt_digest", "pre_drill_attestation_digest",
            "attestation_window", "rollback_budget", "expiry",
        ],
        "recovery_contract": "s2_5_rollback_drill_receipt_v1(kind=WATCHDOG_RESET_LAST)",
        "adapter_id": "s2_5_final_attestation_adapter_v1",
        "adapter_binding_status": "AUTHORITY_LOCKED_PRODUCTION_CAPABLE",
        "actor_node_id": "s2_5_host_service_actor",
        "independent_postcheck_node_id": "s2_5_final_postcheck_v1",
    },
}
# 與 v1/v2 相同的四條 OPS/PM/獨立性契約旗標:「施加 effect 的 actor 不能是其唯一驗證者」。
AIML_COMPONENT_EFFECT_CLASS_V3_INVARIANTS = {
    "requires_ops_preflight": True,
    "requires_pm_operator_approved_intent": True,
    "requires_independent_ops_postcheck": True,
    "applier_is_not_sole_verifier": True,
}


def aiml_component_effect_class_matrix_v3_digest() -> str:
    """v3 矩陣身分 digest——與 v1/v2/S0.3 全部獨立(sibling),三者保持 byte-frozen。"""

    return canonical_digest({
        "component_effect_class_matrix": AIML_COMPONENT_EFFECT_CLASS_MATRIX_V3,
        "class_invariants": AIML_COMPONENT_EFFECT_CLASS_V3_INVARIANTS,
        "effect_lineage": S2_5_EFFECT_LINEAGE,
        "phase_effect_class": S2_5_PHASE_EFFECT_CLASS,
    })


def _identity_digest(classification: dict[str, Any]) -> str:
    return canonical_digest({
        key: value
        for key, value in classification.items()
        if key not in {"classification_id", "self_digest"}
    })


def _surface_tokens_v3() -> frozenset[str]:
    tokens: set[str] = set()
    for row in AIML_COMPONENT_EFFECT_CLASS_MATRIX_V3.values():
        tokens.add(row["adapter_id"])
        tokens.add(row["actor_node_id"])
        tokens.add(row["independent_postcheck_node_id"])
    return frozenset(tokens)


def classify_component_required_effects_v3(
    work_package: Any, *, classified_at: str
) -> dict[str, Any]:
    """由 v3 矩陣導出 required effect;caller 不可自帶/降級(結構鏡 v1/v2 分類器)。

    fail-closed raise(絕不產 ``NONE`` 分類):NONE/缺失/未知類但 owned paths / direct
    interfaces 碰到任一 v3 component 面;declared_adapter_id 非矩陣 adapter;
    declared_intent_fields 非 exact 契約。
    """

    if not isinstance(work_package, dict):
        raise ValueError("component work_package is required")
    declared_class = work_package.get("component_effect_class")
    matrix_row = (
        AIML_COMPONENT_EFFECT_CLASS_MATRIX_V3.get(str(declared_class))
        if declared_class is not None
        else None
    )
    if matrix_row is None:
        touched = set()
        tokens = _surface_tokens_v3()
        for collection in (
            work_package.get("owned_path_manifest"),
            work_package.get("direct_interfaces"),
        ):
            if isinstance(collection, list):
                touched.update(
                    item for item in collection
                    if isinstance(item, str) and item in tokens
                )
        if touched:
            raise ValueError(
                "component work-package touches effectful component surface(s) "
                f"{sorted(touched)} but declares component_effect_class="
                f"{declared_class!r}; an effectful class cannot be source-only"
            )
        raise ValueError(f"unsupported component_effect_class: {declared_class!r}")
    declared_adapter = work_package.get("declared_adapter_id")
    if declared_adapter != matrix_row["adapter_id"]:
        raise ValueError(
            f"declared_adapter_id {declared_adapter!r} is not the admitted adapter "
            f"for {declared_class}"
        )
    declared_fields = work_package.get("declared_intent_fields")
    if not isinstance(declared_fields, list) or sorted(declared_fields) != sorted(
        matrix_row["required_intent_fields"]
    ):
        raise ValueError(
            f"declared_intent_fields do not match the exact {declared_class} "
            "intent contract"
        )
    required_effects = [{
        "effect_class": declared_class,
        "status": "REQUIRED_PENDING",
        "adapter_id": matrix_row["adapter_id"],
        "actor_node_id": matrix_row["actor_node_id"],
        "rollback_contract": matrix_row["recovery_contract"],
        "independent_postcheck_node_id": matrix_row["independent_postcheck_node_id"],
        "required_intent_fields": list(matrix_row["required_intent_fields"]),
        "adapter_binding_status": matrix_row["adapter_binding_status"],
    }]
    classification: dict[str, Any] = {
        "schema_version": "aiml_component_effect_classification_v3",
        "classification_id": "sha256:" + "0" * 64,
        "component_work_package_id": work_package.get("component_work_package_id"),
        "classified_inputs": json.loads(json.dumps(work_package)),
        "classifier_digest": aiml_component_effect_class_matrix_v3_digest(),
        "required_effects": required_effects,
        "classified_at": classified_at,
        "self_digest": "sha256:" + "0" * 64,
    }
    classification["classification_id"] = _identity_digest(classification)
    classification["self_digest"] = artifact_self_digest(classification)
    return classification


# ── §9.2 never-refreshable 封閉表(S2.5 全五類;additive,不動 S2.4 owned 表 bytes)────
S2_5_NEVER_REFRESHABLE_SCHEMAS: dict[str, tuple[str, ...]] = {
    "S2_5_START_CORE": ("s2_5_start_core_v1",),
    "S2_5_START_INTENT": ("s2_5_start_intent_v1",),
    "S2_5_RUNNING_ATTESTATION": ("s2_5_running_attestation_v1",),
    "S2_5_FINAL_ATTESTATION": ("s2_5_final_attestation_v1",),
    "S2_5_ROLLBACK_DRILL_RECEIPT": ("s2_5_rollback_drill_receipt_v1",),
}
S2_5_NEVER_REFRESHABLE_EVIDENCE: dict[str, str] = {
    "S2_5_START_CORE": (
        "an S2.5 start core is freshly issued for one exact permit window; it is never "
        "refreshed or chained"
    ),
    "S2_5_START_INTENT": (
        "an S2.5 start intent is freshly issued for one exact start; it is never "
        "refreshed or chained"
    ),
    "S2_5_RUNNING_ATTESTATION": (
        "a running attestation describes one live runtime moment and is always freshly "
        "re-observed; no refresh-by-reference"
    ),
    "S2_5_FINAL_ATTESTATION": (
        "a final attestation describes one live post-drill runtime moment and is always "
        "freshly re-observed; no refresh-by-reference"
    ),
    "S2_5_ROLLBACK_DRILL_RECEIPT": (
        "a rollback/reset drill receipt records one real lifecycle drill; rerun the drill "
        "if expired"
    ),
}


def derive_s2_5_source_dependency_admission_status(
    *,
    evidence_class: Any,
    receipt: Any,
    refresh: Any = None,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    """§9.2 的 S2.5 臂:五類 artifact 全屬 never-refreshable(鏡 S2.4 執法形制)。

    * 任何 refresh 一律 ``DEPENDENCY_REFRESH_BY_REFERENCE_FORBIDDEN``;
    * 未過期 ``SOURCE_DEPENDENCY_FRESH``;過期 ``DEPENDENCY_EVIDENCE_REOBSERVATION_REQUIRED``;
    * 未知類別/錯 schema/結構不合法 一律拒(封閉表,不預設放行)。
    """

    if now is None:
        now = datetime.now(timezone.utc)
    verdict: dict[str, Any] = {
        "status": SOURCE_DEPENDENCY_STATUS_REJECTED,
        "reasons": [],
        "evidence_class": evidence_class,
        "refresh_admitted": False,
    }
    refreshes = (
        list(refresh) if isinstance(refresh, (list, tuple))
        else [] if refresh is None else [refresh]
    )
    expected_schemas = S2_5_NEVER_REFRESHABLE_SCHEMAS.get(str(evidence_class))
    if expected_schemas is None:
        verdict["reasons"] = [
            f"{evidence_class!r} is not an S2.5 dependency-freshness class; the table is "
            "closed and an unknown class is never admitted"
        ]
        return verdict
    if refreshes:
        verdict["status"] = DEPENDENCY_REFRESH_BY_REFERENCE_FORBIDDEN
        verdict["reasons"] = [
            f"{evidence_class} can never be refreshed by reference: "
            f"{S2_5_NEVER_REFRESHABLE_EVIDENCE[str(evidence_class)]} (§9.2 / design §6)"
        ]
        return verdict
    if not isinstance(receipt, dict) or receipt.get("schema_version") not in expected_schemas:
        verdict["reasons"] = [
            f"{evidence_class} evidence is not the artifact this class names "
            f"(expected schema {expected_schemas})"
        ]
        return verdict
    expires = receipt.get("evidence_expires_at", receipt.get("expires_at"))
    try:
        if expires is None:
            raise ValueError("evidence carries no expiry")
        fresh = _parse_timestamp(str(expires)) > _parse_timestamp(
            _now_text(now) or str(now)
        )
    except (TypeError, ValueError) as error:
        verdict["reasons"] = [
            f"{evidence_class} freshness cannot be derived: {error} (fail-closed)"
        ]
        return verdict
    if fresh:
        verdict["status"] = SOURCE_DEPENDENCY_STATUS_FRESH
        return verdict
    verdict["status"] = DEPENDENCY_EVIDENCE_REOBSERVATION_REQUIRED
    verdict["reasons"] = [
        f"{evidence_class} is expired and cannot be refreshed by reference: "
        f"{S2_5_NEVER_REFRESHABLE_EVIDENCE[str(evidence_class)]}"
    ]
    return verdict


# ── 中央閘 s2_5 委派驗 ────────────────────────────────────────────────────────
# FORBIDDEN_INTENT_KEYS:closed schema 已擋未知鍵;此掃描是縱深防禦——任何巢狀層級出現
# raw-command/unit-text/signal/pid/kill/caller-路徑 類鍵名即拒(design §5.1)。
FORBIDDEN_INTENT_KEYS = frozenset({
    "argv", "command", "exec", "exec_start", "kill", "pid", "raw_command",
    "shell", "signal", "unit_text", "unit_path", "caller_path",
})
# E2 F9:attested 與 simulation 兩個成功語義**分開命名**——SOURCE_SIMULATION_PASS 永不是
# attested success,任何把 simulation 當 attested 消費的寫法在型別命名層就被擋下。
_S2_5_ATTESTED_STATUSES = frozenset({"RUNNING_ATTESTED", "FINAL_ATTESTED"})
_S2_5_SIMULATION_STATUSES = frozenset({"SOURCE_SIMULATION_PASS"})


def _forbidden_key_hits(value: Any, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key) in FORBIDDEN_INTENT_KEYS:
                hits.append(f"{path}.{key}")
            hits.extend(_forbidden_key_hits(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(_forbidden_key_hits(child, f"{path}[{index}]"))
    return hits


def s2_5_start_id_for_core(core: dict[str, Any]) -> str:
    """``start_id = 's2-5-' + hex(canonical_digest(core))``(design §5.1 導出身分)。"""

    return S2_5_START_ID_PREFIX + canonical_digest(core).split(":", 1)[1]


def s2_5_running_dimension_verdicts(dimensions: Any) -> dict[str, bool]:
    """五維各自的 pass 判準(design §3;lifecycle 模組與中央閘共用同一份判準)。"""

    if not isinstance(dimensions, dict):
        return {key: False for key in ("unit", "pid_cgroup", "mount", "network", "pg_identity")}
    unit = dimensions.get("unit") or {}
    pid_cgroup = dimensions.get("pid_cgroup") or {}
    mount = dimensions.get("mount") or {}
    network = dimensions.get("network") or {}
    pg_identity = dimensions.get("pg_identity") or {}
    return {
        "unit": (
            unit.get("active_state") == "active"
            and unit.get("sub_state") == "running"
            and unit.get("unit_file_state") == "enabled"
            and isinstance(unit.get("main_pid"), int)
            and unit.get("main_pid", 0) > 0
            and unit.get("fragment_digest_match") is True
        ),
        "pid_cgroup": pid_cgroup.get("control_group_match") is True,
        "mount": (
            mount.get("launch_root_match") is True
            and mount.get("loader_closure_match") is True
            and mount.get("executable_mappings_in_manifest") is True
        ),
        "network": (
            network.get("address_families_ok") is True
            and network.get("ip_allow_loopback_only") is True
            and network.get("listening_sockets_empty") is True
        ),
        "pg_identity": (
            pg_identity.get("advisory_lock_holder_count") == 1
            and pg_identity.get("session_started_seen") is True
            and pg_identity.get("unclosed_session_absent") is True
            and pg_identity.get("topology_guard_match") is True
        ),
    }


def _freshness_errors(label: str, expires: Any, now_text: str) -> list[str]:
    try:
        if _parse_timestamp(str(expires)) <= _parse_timestamp(now_text):
            return [f"{label} is expired at the central gate (fail-closed)"]
    except (TypeError, ValueError) as error:
        return [f"{label} expiry is unparseable: {error}"]
    return []


def _observer_gate_errors(receipt: dict[str, Any]) -> list[str]:
    """observer/dead-man gate:verifier≠applier(schema 表達不了)+ 證據年齡再導出。"""

    errors: list[str] = []
    gate = receipt.get("observer_gate") or {}
    if gate.get("verifier_node_id") == receipt.get("apply_actor_node"):
        errors.append(
            "observer_gate verifier_node_id must differ from apply_actor_node "
            "(the applier can never be its own dead-man verifier)"
        )
    if receipt.get("independent_verifier_node") == receipt.get("apply_actor_node"):
        errors.append(
            "independent_verifier_node must differ from apply_actor_node"
        )
    try:
        oldest = _parse_timestamp(str(gate.get("oldest_evidence_at")))
        evaluated = _parse_timestamp(str(gate.get("evaluated_at")))
        age = (evaluated - oldest).total_seconds()
        max_age = gate.get("max_evidence_age_seconds")
        if age < 0:
            errors.append("observer_gate evidence is sampled after evaluation (fail-closed)")
        elif isinstance(max_age, int) and age > max_age and gate.get("stale") is not True:
            errors.append(
                "observer_gate claims fresh evidence but the oldest sample exceeds "
                "max_evidence_age_seconds (dead-man: absent/over-age evidence is stale)"
            )
    except (TypeError, ValueError) as error:
        errors.append(f"observer_gate timestamps are unparseable: {error}")
    return errors


def _attestation_errors(
    receipt: dict[str, Any], now_text: str, *, expected_kind: str
) -> list[str]:
    """attested status 的唯一鑰匙:trusted-host attestor SSHSIG 驗簽(lazy import 驗簽葉)。

    ``expected_kind`` 由中央閘按 phase 傳入(A=running/B=final;E2 F3/E3 P2-1):
    B 簽章不可重放為 A,schema const 之上代碼級再驗一道(縱深防禦)。
    """

    if str(_HELPER_DIR) not in sys.path:
        sys.path.insert(0, str(_HELPER_DIR))
    import agent_governance_s2_5_attestation as _attestation

    return _attestation.verify_s2_5_trusted_host_attestation(
        receipt.get("trusted_host_attestation"),
        intent_digest=receipt.get("intent_digest"),
        running_dimensions=receipt.get("running_dimensions"),
        observer_gate=receipt.get("observer_gate"),
        now=now_text,
        expected_kind=expected_kind,
    )


def _attestation_receipt_errors(
    artifact: dict[str, Any], now_text: str, *, final: bool
) -> list[str]:
    errors: list[str] = []
    if artifact.get("self_digest") != artifact_self_digest(artifact):
        errors.append("s2_5 attestation self_digest does not bind the canonical receipt")
    errors.extend(_observer_gate_errors(artifact))
    errors.extend(
        _freshness_errors(
            "s2_5 attestation evidence", artifact.get("evidence_expires_at"), now_text
        )
    )
    status = artifact.get("status")
    if status in _S2_5_ATTESTED_STATUSES or status in _S2_5_SIMULATION_STATUSES:
        verdicts = s2_5_running_dimension_verdicts(artifact.get("running_dimensions"))
        failing = sorted(name for name, ok in verdicts.items() if not ok)
        if failing:
            errors.append(
                "s2_5 attestation success requires all five running dimensions to pass; "
                f"failing: {failing} (one failing dimension fails the whole attestation)"
            )
        precheck = artifact.get("precheck") or {}
        weak = sorted(name for name, ok in precheck.items() if ok is not True)
        if weak:
            errors.append(
                f"s2_5 attestation success requires every precheck to hold; failing: {weak}"
            )
        persistence = artifact.get("enabled_persistence") or {}
        if persistence.get("unit_file_state") != "enabled" or (
            persistence.get("wanted_by_link_present") is not True
        ):
            errors.append(
                "s2_5 attestation success requires UnitFileState=enabled and the "
                "WantedBy link present (PM O-6: the source-provable persistence half)"
            )
    if status in _S2_5_ATTESTED_STATUSES:
        errors.extend(
            _attestation_errors(artifact, now_text, expected_kind="B" if final else "A")
        )
    # E2 F2:PLATFORM 類 evidence_class ⇒ attested status + attestor artifact 在場。
    # 非成功 status(PENDING/REJECTED/FAILED)自稱 PLATFORM_OR_EXTERNAL_ATTESTED 一律拒。
    if artifact.get("evidence_class") == "PLATFORM_OR_EXTERNAL_ATTESTED" and (
        status not in _S2_5_ATTESTED_STATUSES
        or not isinstance(artifact.get("trusted_host_attestation"), dict)
    ):
        errors.append(
            "s2_5 evidence_class PLATFORM_OR_EXTERNAL_ATTESTED requires an attested "
            "status with the trusted-host attestor artifact in hand; a non-attested "
            "receipt never claims platform evidence (fail-closed)"
        )
    if final and (
        status in _S2_5_ATTESTED_STATUSES or status in _S2_5_SIMULATION_STATUSES
    ):
        watchdog = artifact.get("watchdog_last") or {}
        if watchdog.get("n_restarts_after") != 0:
            errors.append(
                "s2_5 final attestation success requires the post-reset NRestarts "
                "baseline to be zero (watchdog reset LAST)"
            )
    return errors


def validate_s2_5_artifact(artifact: Any, *, now: Any = None) -> list[str]:
    """facade 委派入口:closed schema 已過,此處補 schema 表達不了的整合/新鮮度/驗簽面。"""

    if not isinstance(artifact, dict):
        return ["s2_5 artifact must be an object"]
    schema_version = artifact.get("schema_version")
    if schema_version == "aiml_component_effect_classification_v3":
        errors: list[str] = []
        if artifact["classification_id"] != _identity_digest(artifact):
            errors.append("AIML component effect v3 classification_id is invalid")
        if artifact["self_digest"] != artifact_self_digest(artifact):
            errors.append("AIML component effect v3 classification self_digest is invalid")
        if artifact["classifier_digest"] != aiml_component_effect_class_matrix_v3_digest():
            errors.append("AIML component effect v3 classifier digest is not admitted")
        if artifact["component_work_package_id"] != artifact["classified_inputs"][
            "component_work_package_id"
        ]:
            errors.append("AIML component v3 classification work-package id is not bound")
        try:
            expected = classify_component_required_effects_v3(
                artifact["classified_inputs"],
                classified_at=artifact["classified_at"],
            )
        except ValueError as error:
            errors.append(
                f"AIML component effect v3 classification is not admitted: {error}"
            )
        else:
            if artifact["required_effects"] != expected["required_effects"]:
                errors.append(
                    "AIML component v3 required effects differ from classifier output"
                )
        return errors
    if schema_version == "s2_5_authorization_replay_ledger_v1":
        # P1-3:closed schema 之上,逐 entry hash-chain 重算(seq/prev/digest/fsynced)
        # + self_digest 反偽造重算(lazy import 驗簽葉的同一把尺;不另造第二套鏈驗)。
        # ledger 無新鮮度面(consume-once 由鏈與 head-anchor 執法),故不落在 now 臂內。
        if str(_HELPER_DIR) not in sys.path:
            sys.path.insert(0, str(_HELPER_DIR))
        import agent_governance_s2_5_attestation as _attestation

        errors = []
        if artifact.get("self_digest") != artifact_self_digest(artifact):
            errors.append(
                "s2_5 replay ledger self_digest does not bind the canonical ledger"
            )
        errors.extend(
            _attestation.s2_5_replay_ledger_entry_errors(artifact.get("entries"))
        )
        return errors
    now_text = _now_text(now)
    if now_text is None:
        return [
            "s2_5 artifact requires now for freshness at the central gate (fail-closed)"
        ]
    errors = []
    if schema_version == "s2_5_start_core_v1":
        errors.extend(_freshness_errors("s2_5 start core", artifact.get("expires_at"), now_text))
        try:
            if _parse_timestamp(str(artifact.get("issued_at"))) >= _parse_timestamp(
                str(artifact.get("expires_at"))
            ):
                errors.append("s2_5 start core issued_at must precede expires_at")
        except (TypeError, ValueError) as error:
            errors.append(f"s2_5 start core timestamps are unparseable: {error}")
    elif schema_version == "s2_5_start_intent_v1":
        core = artifact.get("core")
        core_digest = canonical_digest(core)
        if artifact.get("core_digest") != core_digest:
            errors.append("s2_5 start intent core_digest does not re-derive from the core")
        if artifact.get("start_id") != S2_5_START_ID_PREFIX + core_digest.split(":", 1)[1]:
            errors.append("s2_5 start intent start_id does not re-derive from core_digest")
        if artifact.get("self_digest") != artifact_self_digest(artifact):
            errors.append("s2_5 start intent self_digest does not bind the canonical intent")
        hits = _forbidden_key_hits(artifact)
        if hits:
            errors.append(
                "s2_5 start intent carries forbidden raw-command/unit-text/signal/pid "
                f"keys: {sorted(hits)} (design §5.1 FORBIDDEN_INTENT_KEYS)"
            )
        errors.extend(_freshness_errors("s2_5 start intent", artifact.get("expires_at"), now_text))
        if isinstance(core, dict):
            errors.extend(
                _freshness_errors("s2_5 start core", core.get("expires_at"), now_text)
            )
    elif schema_version == "s2_5_running_attestation_v1":
        errors.extend(_attestation_receipt_errors(artifact, now_text, final=False))
    elif schema_version == "s2_5_final_attestation_v1":
        errors.extend(_attestation_receipt_errors(artifact, now_text, final=True))
    elif schema_version == "s2_5_rollback_drill_receipt_v1":
        if artifact.get("self_digest") != artifact_self_digest(artifact):
            errors.append("s2_5 rollback drill self_digest does not bind the canonical receipt")
        errors.extend(
            _freshness_errors("s2_5 rollback drill", artifact.get("expires_at"), now_text)
        )
    else:
        errors.append(f"unsupported s2_5 schema_version: {schema_version!r}")
    return errors


# ── §6 closure binding(source-only;不接入 live dispatch)────────────────────────
S2_5_BINDING_VERIFIED = "S2_5_ATTESTATION_BINDING_VERIFIED"
S2_5_BINDING_REJECTED = "S2_5_ATTESTATION_BINDING_REJECTED"
S2_5_BINDING_PENDING = "EXTERNAL_VERIFICATION_PENDING"


def validate_s2_5_attestation_binding(
    *,
    intent: Any,
    ops_preflight: Any,
    receipt: Any,
    verifier_capture: Any = None,
    now: Any = None,
) -> dict[str, Any]:
    """§6 closure binding:intent digest × OPS preflight digest × receipt ×
    ``verifier_capture_digest`` 的三方交叉(鏡 ``validate_pg_observer_bootstrap_binding``)。

    source lane 的 ``verifier_capture_digest`` 可為 ``None``——那是 typed
    ``EXTERNAL_VERIFICATION_PENDING`` 分支(欄位契約與交叉邏輯照走),**不是跳過**;
    一側在場另一側缺席即拒。VERIFIED 只證結構綁定,不證任何 runtime(九 authority false)。
    """

    verdict: dict[str, Any] = {"status": S2_5_BINDING_REJECTED, "reasons": []}
    reasons = verdict["reasons"]
    if not isinstance(intent, dict) or not isinstance(receipt, dict):
        reasons.append("s2_5 attestation binding requires the intent and receipt objects")
        return verdict
    intent_errors = validate_s2_5_artifact(intent, now=now)
    if intent_errors or intent.get("schema_version") != "s2_5_start_intent_v1":
        reasons.append(
            "s2_5 attestation binding intent fails the central gate: "
            + "; ".join(intent_errors or ["not an s2_5_start_intent_v1"])
        )
    receipt_errors = validate_s2_5_artifact(receipt, now=now)
    if receipt_errors or receipt.get("schema_version") not in {
        "s2_5_running_attestation_v1", "s2_5_final_attestation_v1"
    }:
        reasons.append(
            "s2_5 attestation binding receipt fails the central gate: "
            + "; ".join(receipt_errors or ["not an s2_5 attestation receipt"])
        )
    # 1. receipt × intent digest(exact)。
    if receipt.get("intent_digest") != intent.get("self_digest") or (
        receipt.get("intent_id") != intent.get("start_id")
    ):
        reasons.append(
            "s2_5 attestation binding: the receipt does not bind the exact intent "
            "(intent_digest/intent_id mismatch)"
        )
    # 2. OPS preflight fragment:self_digest 反偽造重算 + intent digest 綁定。
    if not (
        isinstance(ops_preflight, dict)
        and bool(ops_preflight.get("self_digest"))
        and ops_preflight.get("self_digest") == artifact_self_digest(ops_preflight)
        and ops_preflight.get("intent_digest") == intent.get("self_digest")
    ):
        reasons.append(
            "s2_5 attestation binding: the OPS preflight fragment is absent, its "
            "self_digest does not re-derive, or it does not bind the exact intent"
        )
    # 3. verifier capture 三方交叉(capture node ≠ applier;record_digest 綁 receipt 欄)。
    receipt_capture_digest = receipt.get("verifier_capture_digest")
    if receipt_capture_digest is None and verifier_capture is None:
        if not reasons:
            verdict["status"] = S2_5_BINDING_PENDING
            reasons.append(
                "s2_5 attestation binding is structurally coherent but the independent "
                "verifier command_capture_v2 is not yet bound (source lane honest "
                "endpoint); EXTERNAL_VERIFICATION_PENDING, never a PASS"
            )
        return verdict
    if (receipt_capture_digest is None) != (verifier_capture is None):
        reasons.append(
            "s2_5 attestation binding: verifier_capture_digest and the verifier "
            "capture record must be present together (a one-sided claim is rejected)"
        )
        return verdict
    if not (
        isinstance(verifier_capture, dict)
        and str(verifier_capture.get("record_digest") or "") == str(receipt_capture_digest)
    ):
        reasons.append(
            "s2_5 attestation binding: the verifier command_capture_v2 record_digest "
            "is not the receipt-bound verifier_capture_digest"
        )
    if isinstance(verifier_capture, dict) and verifier_capture.get(
        "node_id"
    ) == receipt.get("apply_actor_node"):
        reasons.append(
            "s2_5 attestation binding: the verifier capture node must differ from the "
            "applier node (the applier can never verify itself)"
        )
    if not reasons:
        verdict["status"] = S2_5_BINDING_VERIFIED
    return verdict


def s2_5_abi_projection() -> dict[str, Any]:
    """WP5 seam 的 code-owned 投影(phase→class 映射投影測試與 registry 對賬共用)。"""

    return {
        "effect_lineage": S2_5_EFFECT_LINEAGE,
        "phase_effect_class": dict(S2_5_PHASE_EFFECT_CLASS),
        "component_classifier_v3_digest": aiml_component_effect_class_matrix_v3_digest(),
        "never_refreshable_classes": sorted(S2_5_NEVER_REFRESHABLE_EVIDENCE),
        "unit_name": S2_5_UNIT_NAME,
        "schema_files_present": sorted(
            name for name in (
                "s2_5_start_core_v1",
                "s2_5_start_intent_v1",
                "s2_5_running_attestation_v1",
                "s2_5_final_attestation_v1",
                "s2_5_rollback_drill_receipt_v1",
                "s2_5_authorization_replay_ledger_v1",
                "aiml_component_effect_classification_v3",
            )
            if (SCHEMA_DIR / f"{name}.schema.json").is_file()
        ),
    }
