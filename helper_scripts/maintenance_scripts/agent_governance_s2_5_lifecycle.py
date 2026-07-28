#!/usr/bin/env python3
"""S2.5(WP5)lifecycle 葉——start/final 兩 phase 的 builders、prechecks、appliers 與 WAL。

design §3/§5/§7 的 SSOT:``apply_s2_5_start``(S2.5A:precheck → authorization → WAL →
``enable --now`` → 五維觀測 → receipt/rollback)與 ``apply_s2_5_final``(S2.5B:S2.1 drill
綁定 → 五維再證 → **watchdog reset last** → receipt)。

固定順序,driver 呼叫之前零變更(形制鏡 ``agent_governance_s2_4_probe.run_s2_4_capability_probe``):

0. 未解 recovery → ``RECOVERY_REQUIRED``;
1. intent 過中央閘 closed schema + §5.1 core/start_id 再導出;
2. phase/route-surface 再導出(phase↔effect-class 綁定;builder/install 面夾帶即拒);
3. 靜態 precheck(§3.1):S2.4 APPLIED_INACTIVE receipt digest 綁定、native-loader closure
   重驗、S2.4 recovery clear、install lock free;S2.5B 另加 S2.1 drill receipt 與 S2.5A
   attestation 的 digest 綁定;
4. 授權:§5.6 permit 驗簽(payload 綁定 + TTL/skew + 域分離)+ replay ledger 消費綁定;
5. intent 自身新鮮窗;
6. ``driver is None`` → ``EXTERNAL_VERIFICATION_PENDING``(零變更、零 driver 呼叫;
   Mac/source/test lane 的誠實終點);
7. driver 在場 → §5.7 journal reconcile → 前態讀取 → WAL(APPLYING)→ effect → 觀測 →
   receipt;任一維 fail → rollback-to-disabled(S2.5A)/ typed 失敗(S2.5B),rollback 自身
   失敗 → ``NOT_RESTORED`` + ``RECOVERY_REQUIRED``,絕不把部分態轉成功。

⚠ 誠實邊界:simulated/disposable lane 的成功頂點是 ``SOURCE_SIMULATION_PASS``
(``LOCAL_REPRODUCIBLE``);``RUNNING_ATTESTED``/``FINAL_ATTESTED`` 唯一由驗簽通過的
trusted-host attestor 簽章解鎖(key custody 鎖產線)。本模組永不接觸真實 systemd/PG;
production driver 只在 S2.5 EFFECT session 由 OPS 注入。九項 authority 恆 false。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
for _candidate in (HELPER_DIR, ML_TRAINING_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import aiml_gate_receipt_validator as central_validator  # noqa: E402
import agent_governance_s2_5_attestation as attestation  # noqa: E402
from agent_governance_alr_quiesce_inventory import UNIT_NAME  # noqa: E402
from agent_governance_s2_5_driver import S2_5_UNIT_NAME  # noqa: E402
from aiml_gate_receipt_s2_5 import (  # noqa: E402
    S2_5_PHASE_EFFECT_CLASS,
    S2_5_START_ID_PREFIX,
    s2_5_running_dimension_verdicts,
)

# WP3 的 owner 確認尺與 driver 常量必須是同一個 unit——分歧即 import 期炸(縱深防禦)。
assert UNIT_NAME == S2_5_UNIT_NAME, "S2.5 unit constant drifted from the WP3 inventory"

# ── typed statuses ───────────────────────────────────────────────────────────
S2_5_STATUS_PENDING = "EXTERNAL_VERIFICATION_PENDING"
S2_5_STATUS_REQUEST_REJECTED = "REQUEST_REJECTED"
S2_5_STATUS_AUTHORIZATION_REJECTED = "AUTHORIZATION_REJECTED"
S2_5_STATUS_RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
S2_5_STATUS_SIMULATION_PASS = "SOURCE_SIMULATION_PASS"
S2_5_STATUS_RUNNING_ATTESTED = "RUNNING_ATTESTED"
S2_5_STATUS_FINAL_ATTESTED = "FINAL_ATTESTED"
S2_5_STATUS_ATTESTATION_FAILED = "ATTESTATION_FAILED"
S2_5_TARGET_CLASSES = ("simulated_harness", "disposable_local", "production")
# §5.7 journal 狀態(WAL:先寫 APPLYING 再動 effect;terminal 之外的殘留擋新 effect)。
_JOURNAL_TERMINAL_STATES = frozenset({
    "TERMINAL_SUCCESS", "TERMINAL_ROLLED_BACK", "TERMINAL_FAILED",
})
JOURNAL_CORRUPT = "JOURNAL_CORRUPT_RECOVERY_REQUIRED"


class S2_5RecoveryState:
    """跨 apply 的 in-process recovery 閂(未解 recovery 擋一切新 effect;§3.1c)。"""

    def __init__(self) -> None:
        self.unresolved: dict[str, Any] | None = None

    def record(self, *, start_id: str | None, reasons: list[str]) -> None:
        self.unresolved = {"start_id": start_id, "reasons": list(reasons)}

    def resolve(self, *, resolution_note: str) -> dict[str, Any] | None:
        resolved, self.unresolved = self.unresolved, None
        if resolved is not None:
            resolved["resolution_note"] = resolution_note
        return resolved


class S2_5RunningObserver(Protocol):
    """獨立 verifier node 的觀測面(五維 + persistence + post-reset;fixtures 注入)。"""

    verifier_node_id: str

    def observe_running_dimensions(self) -> dict[str, Any]: ...

    def observe_enabled_persistence(self) -> dict[str, Any]: ...

    def oldest_evidence_at(self) -> str: ...

    def observe_post_reset(self) -> dict[str, Any]: ...


# ── builders(§5.1)───────────────────────────────────────────────────────────
def build_s2_5_start_core(
    *,
    phase: str,
    target_host: str,
    expected_unit_fragment_digest: str,
    s2_4_install_effect_receipt_digest: str,
    expected_launch_bundle_digest: str,
    expected_application_bundle_digest: str,
    expected_base_runtime_tree_digest: str,
    native_loader_closure_digest: str,
    source_head: str,
    issued_at: str,
    expires_at: str,
    s2_1_drill_receipt_digest: str | None = None,
    pre_drill_attestation_digest: str | None = None,
    attestation_window: dict[str, int] | None = None,
    start_budget_seconds: int = 120,
    rollback_budget_seconds: int = 120,
    safety_margin_seconds: int = 30,
    max_ttl_seconds: int = attestation.MAX_S2_5_PERMIT_TTL_SECONDS,
) -> dict[str, Any]:
    """unsigned start core(排除導出 id/授權/self_digest;§5.6 profile 由 phase 決定)。"""

    profile = attestation.S2_5_PERMIT_PROFILES[phase]
    return {
        "schema_version": "s2_5_start_core_v1",
        "phase": phase,
        "target_host": target_host,
        "unit_name": S2_5_UNIT_NAME,
        "expected_unit_fragment_digest": expected_unit_fragment_digest,
        "s2_4_install_effect_receipt_digest": s2_4_install_effect_receipt_digest,
        "expected_launch_bundle_digest": expected_launch_bundle_digest,
        "expected_application_bundle_digest": expected_application_bundle_digest,
        "expected_base_runtime_tree_digest": expected_base_runtime_tree_digest,
        "native_loader_closure_digest": native_loader_closure_digest,
        "s2_1_drill_receipt_digest": s2_1_drill_receipt_digest,
        "pre_drill_attestation_digest": pre_drill_attestation_digest,
        "attestation_window": dict(attestation_window or {
            "max_evidence_age_seconds": 120,
            "min_samples": 3,
            "sample_interval_seconds": 5,
        }),
        "start_budget_seconds": int(start_budget_seconds),
        "rollback_budget_seconds": int(rollback_budget_seconds),
        "safety_margin_seconds": int(safety_margin_seconds),
        "authorization_profile": {
            "profile_identity": profile["profile_identity"],
            "signature_namespace": profile["signature_namespace"],
            "attestor_identity": attestation.S2_5_ATTESTOR_IDENTITY,
            "attestor_namespace": attestation.S2_5_ATTESTOR_NAMESPACE,
            "max_ttl_seconds": int(max_ttl_seconds),
        },
        "source_head": source_head,
        "issued_at": issued_at,
        "expires_at": expires_at,
    }


def build_s2_5_start_intent(
    core: dict[str, Any], *, expires_at: str, risk: str = "critical"
) -> dict[str, Any]:
    """closed route-class intent:phase↔effect-class 綁定 + 九個 forbidden surface 全 false。"""

    core_digest = central_validator.canonical_digest(core)
    intent: dict[str, Any] = {
        "schema_version": "s2_5_start_intent_v1",
        "route_class": "s2_5_start_intent",
        "core": core,
        "core_digest": core_digest,
        "start_id": S2_5_START_ID_PREFIX + core_digest.split(":", 1)[1],
        "route_surface": {
            "required_effect_class": S2_5_PHASE_EFFECT_CLASS[core["phase"]],
            "effect_lineage": "WATCHDOG_ROLLBACK_TEST",
            "runtime_effect": True,
            "service": "installed_unit_lifecycle_only",
            "risk": risk,
            "runtime_claim": True,
        },
        "forbidden_surfaces": {
            name: False
            for name in (
                "pg_write", "migration", "secret", "credential_install", "host_identity",
                "prepare_fetch_build", "unit_render_install", "daemon_reload",
                "broker_or_order",
            )
        },
        "expires_at": expires_at,
    }
    intent["self_digest"] = central_validator.artifact_self_digest(intent)
    return intent


# ── §5.7 WAL journal(source lane 只以 tmp-root 注入路徑觸碰)───────────────────
def _journal_write(journal_path: Path, payload: dict[str, Any]) -> None:
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = journal_path.with_name(journal_path.name + ".tmp")
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    fd = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temp_path, journal_path)


def _journal_transition(
    journal_path: Path, *, start_id: str, state: str, updated_at: str
) -> dict[str, Any]:
    history: list[dict[str, Any]] = []
    if journal_path.is_file():
        try:
            existing = json.loads(journal_path.read_text(encoding="utf-8"))
            history = list(existing.get("history") or [])
        except (OSError, ValueError):
            history = []
    entry = {"state": state, "updated_at": updated_at}
    payload = {
        "schema_version": "s2_5_start_journal_v1_informal",
        "start_id": start_id,
        "state": state,
        "updated_at": updated_at,
        "history": history + [entry],
    }
    _journal_write(journal_path, payload)
    return payload


def reconcile_s2_5_journal(journal_path: Path | None) -> dict[str, Any]:
    """§5.2 語義:非終端殘留/corrupt journal 一律擋新 effect(fail-closed)。"""

    if journal_path is None:
        return {
            "admits_new_work": False,
            "reasons": [
                "s2_5 journal surface is absent; a driver-present apply requires a durable "
                "WAL journal path (fail-closed)"
            ],
        }
    if not journal_path.is_file():
        return {"admits_new_work": True, "reasons": []}
    try:
        payload = json.loads(journal_path.read_text(encoding="utf-8"))
        state = payload["state"]
    except (OSError, ValueError, KeyError, TypeError):
        return {
            "admits_new_work": False,
            "reasons": [
                f"{JOURNAL_CORRUPT}: the s2_5 journal cannot be parsed; operator "
                "investigation is required before any new effect"
            ],
        }
    if state not in _JOURNAL_TERMINAL_STATES:
        return {
            "admits_new_work": False,
            "reasons": [
                f"s2_5 journal holds a non-terminal state {state!r}; §5.2 reconciles any "
                "non-terminal journal before a new effect is accepted"
            ],
        }
    return {"admits_new_work": True, "reasons": []}


# ── 內部小工具 ───────────────────────────────────────────────────────────────
def _verdict(status: str, reasons: list[str], **extra: Any) -> dict[str, Any]:
    verdict = {"status": status, "reasons": list(reasons)}
    verdict.update(extra)
    return verdict


def _resolve_now(now: Any) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if isinstance(now, datetime):
        return now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return central_validator._parse_timestamp(str(now))


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def _static_precheck_reasons(
    core: dict[str, Any],
    *,
    phase: str,
    s2_4_install_effect_receipt: Any,
    loader_closure_observation: Any,
    s2_4_recovery_clear: Any,
    install_lock_free: Any,
    s2_1_drill_receipt: Any,
    pre_drill_attestation: Any,
) -> list[str]:
    """§3.1 靜態 precheck(零 driver 接觸)。任一缺席/不符即 typed reason。"""

    reasons: list[str] = []
    # a. S2.4 APPLIED_INACTIVE receipt digest 綁定(#36 精神:綁 exact artifact 非名字)。
    if not (
        isinstance(s2_4_install_effect_receipt, dict)
        and s2_4_install_effect_receipt.get("status") == "APPLIED_INACTIVE"
        and s2_4_install_effect_receipt.get("self_digest")
        == core.get("s2_4_install_effect_receipt_digest")
    ):
        reasons.append(
            "S2.5 precheck: the exact s2_4_install_effect_receipt_v1(status="
            "APPLIED_INACTIVE) bound by the core digest is not in hand (fail-closed)"
        )
    # b. native-loader closure 重驗(§8.1:S2.5A 於 start 前重跑)。
    observed_closure = (
        loader_closure_observation.get("native_loader_closure_digest")
        if isinstance(loader_closure_observation, dict)
        else None
    )
    if observed_closure != core.get("native_loader_closure_digest"):
        reasons.append(
            "S2.5 precheck: the re-derived native-loader closure digest does not equal "
            "the base manifest closure (any new path or changed byte fails closed)"
        )
    # c. S2.4 recovery clear + install lock free(#39/#7)。
    if s2_4_recovery_clear is not True:
        reasons.append(
            "S2_4_RECOVERY_UNRESOLVED: the S2.4 probe/PREPARE/APPLY journals hold "
            "non-terminal residue or an unresolved recovery; S2.5 must not start"
        )
    if install_lock_free is not True:
        reasons.append(
            "S2.5 precheck: the S2.4 install lock is held (or unproven-free); S2.5 must "
            "not start under a live install transaction"
        )
    if phase == "S2_5B_FINAL":
        if not (
            isinstance(s2_1_drill_receipt, dict)
            and str(s2_1_drill_receipt.get("status", "")).startswith("QUIESCED")
            and s2_1_drill_receipt.get("self_digest")
            == core.get("s2_1_drill_receipt_digest")
        ):
            reasons.append(
                "S2.5B precheck: the exact quiesce_result_v1(status=QUIESCED_...) bound "
                "by s2_1_drill_receipt_digest is not in hand (the drill must have "
                "actually happened and restored)"
            )
        if not (
            isinstance(pre_drill_attestation, dict)
            and pre_drill_attestation.get("schema_version") == "s2_5_running_attestation_v1"
            and pre_drill_attestation.get("self_digest")
            == core.get("pre_drill_attestation_digest")
            and pre_drill_attestation.get("status")
            in {S2_5_STATUS_RUNNING_ATTESTED, S2_5_STATUS_SIMULATION_PASS}
        ):
            reasons.append(
                "S2.5B precheck: the exact S2.5A s2_5_running_attestation_v1 bound by "
                "pre_drill_attestation_digest is not in hand or was not successful"
            )
    return reasons


def _authorization_reasons(
    intent: dict[str, Any], authorization: Any, replay_ledger: Any, *, now_dt: datetime
) -> list[str]:
    reasons = attestation.verify_s2_5_operator_permit(
        authorization, intent, now=now_dt
    )
    replay = attestation.derive_s2_5_replay_binding(
        authorization, replay_ledger, start_id=intent.get("start_id")
    )
    if replay["status"] != attestation.REPLAY_STATUS_VALID:
        reasons = reasons + replay["reasons"]
    return reasons


def _observe_and_build(
    *,
    core: dict[str, Any],
    observers: Any,
    clock: Callable[[], datetime],
) -> dict[str, Any]:
    """讀五維 + persistence + observer gate(全由獨立 verifier 面採集)。"""

    dimensions = observers.observe_running_dimensions()
    persistence = dict(observers.observe_enabled_persistence())
    persistence.setdefault("reboot_survival_observed", None)
    gate = attestation.build_observer_gate(
        verifier_node_id=observers.verifier_node_id,
        max_evidence_age_seconds=core["attestation_window"]["max_evidence_age_seconds"],
        oldest_evidence_at=observers.oldest_evidence_at(),
        evaluated_at=_iso(clock()),
    )
    return {
        "dimensions": dimensions,
        "persistence": persistence,
        "observer_gate": gate,
        "verdicts": s2_5_running_dimension_verdicts(dimensions),
    }


def _base_receipt(
    *,
    schema_version: str,
    adapter_id: str,
    status: str,
    intent: dict[str, Any],
    core: dict[str, Any],
    target_class: str,
    owner_fingerprint: str,
    observation: dict[str, Any],
    precheck: dict[str, bool],
    rollback_record: Any,
    applier_node: str,
    verifier_node: str,
    trusted_host_attestation: Any,
    evidence_class: str,
    started_at: str,
    completed_at: str,
    failure_reason: str | None,
) -> dict[str, Any]:
    max_age = core["attestation_window"]["max_evidence_age_seconds"]
    receipt: dict[str, Any] = {
        "schema_version": schema_version,
        "adapter_id": adapter_id,
        "status": status,
        "intent_id": intent["start_id"],
        "intent_digest": intent["self_digest"],
        "target_class": target_class,
        "target_host": core["target_host"],
        "unit_name": S2_5_UNIT_NAME,
        "owner_fingerprint": owner_fingerprint,
        "running_dimensions": observation["dimensions"],
        "enabled_persistence": observation["persistence"],
        "observer_gate": observation["observer_gate"],
        "precheck": dict(precheck),
        "rollback_record": rollback_record,
        "apply_actor_node": applier_node,
        "independent_verifier_node": verifier_node,
        "verifier_capture_digest": None,
        "trusted_host_attestation": trusted_host_attestation,
        "evidence_class": evidence_class,
        "boundary": {
            "production_started_by_source_lane": False,
            "production_running_attested_without_attestor": False,
            "fixture_impersonates_platform_attested": False,
            "nine_authorities_false": True,
        },
        "started_at": started_at,
        "completed_at": completed_at,
        "evidence_expires_at": _iso(
            central_validator._parse_timestamp(completed_at)
            + timedelta(seconds=int(max_age))
        ),
        "failure_reason": failure_reason,
        "source_head": core["source_head"],
    }
    return receipt


def _seal(receipt: dict[str, Any], *, now_dt: datetime) -> tuple[dict[str, Any], list[str]]:
    receipt["self_digest"] = central_validator.artifact_self_digest(receipt)
    errors = central_validator.validate_aiml_artifact(receipt, now=_iso(now_dt))
    return receipt, errors


def _build_rollback_receipt(
    *,
    kind: str,
    status: str,
    intent: dict[str, Any],
    core: dict[str, Any],
    pre_state: dict[str, Any],
    post_state: dict[str, Any],
    s2_4_inactive_prestate_digest: str | None,
    watchdog_last: Any,
    observed_at: str,
) -> dict[str, Any]:
    receipt = {
        "schema_version": "s2_5_rollback_drill_receipt_v1",
        "kind": kind,
        "status": status,
        "intent_id": intent["start_id"],
        "unit_name": S2_5_UNIT_NAME,
        "pre_state": dict(pre_state),
        "post_state": dict(post_state),
        "operation": {
            "kind": "systemd_stop_disable"
            if kind == "ROLLBACK_TO_DISABLED"
            else "systemd_reset_failed"
        },
        "s2_4_inactive_prestate_digest": s2_4_inactive_prestate_digest,
        "watchdog_last": watchdog_last,
        "observed_at": observed_at,
        "expires_at": _iso(
            central_validator._parse_timestamp(observed_at)
            + timedelta(seconds=int(core["attestation_window"]["max_evidence_age_seconds"]))
        ),
        "source_head": core["source_head"],
    }
    receipt["self_digest"] = central_validator.artifact_self_digest(receipt)
    return receipt


def _unit_state_from_show(properties: dict[str, str]) -> dict[str, Any]:
    return {
        "active_state": str(properties.get("ActiveState", "")),
        "unit_file_state": str(properties.get("UnitFileState", "")),
        "n_restarts": int(properties.get("NRestarts", "0") or 0),
        "invocation_id": str(properties.get("InvocationID", "")) or "none",
    }


def _common_gate(
    intent: Any,
    authorization: Any,
    driver: Any,
    *,
    phase: str,
    now: Any,
    replay_ledger: Any,
    target_class: str,
    recovery_state: S2_5RecoveryState | None,
    precheck_inputs: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any], datetime]:
    """step 0-6 的共用閘。回 (提前終止的 verdict | None, 導出的 precheck 旗標, now)。"""

    now_dt = _resolve_now(now)
    precheck_flags = {
        "inactive_prestate_verified": False,
        "loader_closure_reverified": False,
        "s2_4_recovery_clear": False,
        "install_lock_free": False,
    }
    # step 0 —— recovery 閂。
    if recovery_state is not None and recovery_state.unresolved is not None:
        return (
            _verdict(
                S2_5_STATUS_RECOVERY_REQUIRED,
                [
                    "a prior S2.5 recovery is unresolved; no new lifecycle effect may "
                    f"start (blocked by {recovery_state.unresolved.get('start_id')})"
                ],
            ),
            precheck_flags,
            now_dt,
        )
    # step 1 —— intent 結構/身分(中央閘負責 core_digest/start_id/self_digest/新鮮窗)。
    if not isinstance(intent, dict):
        return (
            _verdict(S2_5_STATUS_REQUEST_REJECTED, ["s2_5 intent must be an object"]),
            precheck_flags,
            now_dt,
        )
    schema_errors = central_validator.validate_aiml_artifact(intent, now=_iso(now_dt))
    if schema_errors:
        return (
            _verdict(S2_5_STATUS_REQUEST_REJECTED, schema_errors),
            precheck_flags,
            now_dt,
        )
    core = intent["core"]
    # step 2 —— phase 綁定(apply_s2_5_start 只收 S2_5A_START;final 只收 S2_5B_FINAL)。
    if core["phase"] != phase:
        return (
            _verdict(
                S2_5_STATUS_REQUEST_REJECTED,
                [
                    f"this applier owns phase {phase} only; the intent declares "
                    f"{core['phase']!r} (phase substitution is rejected)"
                ],
            ),
            precheck_flags,
            now_dt,
        )
    if target_class not in S2_5_TARGET_CLASSES:
        return (
            _verdict(
                S2_5_STATUS_REQUEST_REJECTED,
                [f"unknown target_class {target_class!r} (closed enum)"],
            ),
            precheck_flags,
            now_dt,
        )
    # step 3 —— 靜態 precheck(零 driver 接觸)。
    static_reasons = _static_precheck_reasons(core, phase=phase, **precheck_inputs)
    precheck_flags["loader_closure_reverified"] = not any(
        "native-loader" in reason for reason in static_reasons
    )
    precheck_flags["s2_4_recovery_clear"] = not any(
        "S2_4_RECOVERY_UNRESOLVED" in reason for reason in static_reasons
    )
    precheck_flags["install_lock_free"] = not any(
        "install lock" in reason for reason in static_reasons
    )
    if static_reasons:
        status = (
            S2_5_STATUS_RECOVERY_REQUIRED
            if any("S2_4_RECOVERY_UNRESOLVED" in reason for reason in static_reasons)
            else S2_5_STATUS_REQUEST_REJECTED
        )
        return _verdict(status, static_reasons), precheck_flags, now_dt
    # step 4 —— 授權 + replay 消費綁定。
    authorization_reasons = _authorization_reasons(
        intent, authorization, replay_ledger, now_dt=now_dt
    )
    if authorization_reasons:
        return (
            _verdict(S2_5_STATUS_AUTHORIZATION_REJECTED, authorization_reasons),
            precheck_flags,
            now_dt,
        )
    # step 5 —— intent 新鮮窗已由中央閘擋(step 1 傳了 now);此處不重複。
    # step 6 —— driver 缺席:reachable 但 authority-locked(零變更、零 driver 呼叫)。
    if driver is None:
        return (
            _verdict(
                S2_5_STATUS_PENDING,
                [
                    "S2.5 lifecycle is reachable but authority-locked: no host service "
                    "driver is present (Mac/source/test lane); "
                    "EXTERNAL_VERIFICATION_PENDING with zero mutation"
                ],
            ),
            precheck_flags,
            now_dt,
        )
    return None, precheck_flags, now_dt


def apply_s2_5_start(
    intent: Any,
    authorization: Any = None,
    driver: Any = None,
    *,
    now: Any = None,
    replay_ledger: Any = None,
    target_class: str = "simulated_harness",
    s2_4_install_effect_receipt: Any = None,
    s2_4_inactive_prestate: Any = None,
    loader_closure_observation: Any = None,
    s2_4_recovery_clear: Any = None,
    install_lock_free: Any = None,
    recovery_state: S2_5RecoveryState | None = None,
    journal_path: Path | None = None,
    observers: Any = None,
    owner_fingerprint: str | None = None,
    applier_node: str = "s2-5-start-applier",
    trusted_host_attestation: Any = None,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """S2.5A:initial ``enable --now`` + 五維 running attestation(§3;固定順序見模組 docstring)。"""

    outcome, precheck_flags, now_dt = _common_gate(
        intent, authorization, driver,
        phase="S2_5A_START",
        now=now,
        replay_ledger=replay_ledger,
        target_class=target_class,
        recovery_state=recovery_state,
        precheck_inputs={
            "s2_4_install_effect_receipt": s2_4_install_effect_receipt,
            "loader_closure_observation": loader_closure_observation,
            "s2_4_recovery_clear": s2_4_recovery_clear,
            "install_lock_free": install_lock_free,
            "s2_1_drill_receipt": None,
            "pre_drill_attestation": None,
        },
    )
    if outcome is not None:
        return outcome
    core = intent["core"]
    clock = clock or (lambda: now_dt)
    # step 7 前置:driver 在場必須有 journal 面與獨立 observer/verifier。
    reconcile = reconcile_s2_5_journal(journal_path)
    if reconcile["admits_new_work"] is not True:
        return _verdict(S2_5_STATUS_RECOVERY_REQUIRED, reconcile["reasons"])
    if observers is None or not str(getattr(observers, "verifier_node_id", "")):
        return _verdict(
            S2_5_STATUS_REQUEST_REJECTED,
            ["S2.5 requires an independent verifier observation surface (fail-closed)"],
        )
    if observers.verifier_node_id == applier_node:
        return _verdict(
            S2_5_STATUS_REQUEST_REJECTED,
            ["S2.5 verifier node must differ from the applier node"],
        )
    if not owner_fingerprint:
        return _verdict(
            S2_5_STATUS_REQUEST_REJECTED,
            [
                "S2.5 requires the WP3 owner fingerprint (compute_owner_fingerprint) "
                "before any lifecycle effect (fail-closed)"
            ],
        )
    # 前態讀取(read-only):必須等於 S2.4 receipt 所證的 loaded/disabled/inactive。
    pre_properties = driver.show()
    pre_state = _unit_state_from_show(pre_properties)
    prestate_expected = (
        isinstance(s2_4_inactive_prestate, dict)
        and _unit_state_from_show({
            "ActiveState": s2_4_inactive_prestate.get("active_state", ""),
            "UnitFileState": s2_4_inactive_prestate.get("unit_file_state", ""),
            "NRestarts": str(s2_4_inactive_prestate.get("n_restarts", 0)),
            "InvocationID": s2_4_inactive_prestate.get("invocation_id", "none"),
        })
        == pre_state
        and pre_state["active_state"] == "inactive"
        and pre_state["unit_file_state"] == "disabled"
        and str(pre_properties.get("FragmentDigest", ""))
        == core["expected_unit_fragment_digest"]
        and str(pre_properties.get("DropInPaths", "")) == ""
        and str(pre_properties.get("NeedDaemonReload", "no")) == "no"
    )
    precheck_flags["inactive_prestate_verified"] = bool(prestate_expected)
    if not prestate_expected:
        return _verdict(
            S2_5_STATUS_REQUEST_REJECTED,
            [
                "S2.5 precheck: the live unit pre-state does not equal the S2.4 "
                "APPLIED_INACTIVE pre-state (loaded/disabled/inactive, exact fragment "
                "digest, no drop-ins, no pending daemon-reload); refusing to start a "
                "look-alike unit"
            ],
        )
    prestate_digest = central_validator.canonical_digest(dict(s2_4_inactive_prestate))
    started_at = _iso(clock())
    # WAL:先寫 APPLYING 再動 effect(§5.2 語義)。
    _journal_transition(
        journal_path, start_id=intent["start_id"], state="APPLYING", updated_at=started_at
    )
    consumed_at = started_at
    attestation.consume_s2_5_authorization(
        replay_ledger, authorization, start_id=intent["start_id"], consumed_at=consumed_at
    )
    try:
        driver.enable_now()
    except Exception as error:  # noqa: BLE001 —— effect 失敗必走 rollback,絕不轉成功。
        rollback = _rollback_to_disabled(
            intent=intent, core=core, driver=driver, pre_state=pre_state,
            prestate_digest=prestate_digest, clock=clock,
        )
        _journal_transition(
            journal_path, start_id=intent["start_id"],
            state="TERMINAL_ROLLED_BACK"
            if rollback["status"] == "RESTORED_INACTIVE"
            else "RECOVERY_REQUIRED",
            updated_at=_iso(clock()),
        )
        if rollback["status"] != "RESTORED_INACTIVE" and recovery_state is not None:
            recovery_state.record(
                start_id=intent["start_id"],
                reasons=[f"start failed and rollback did not restore: {error!r}"],
            )
        return _verdict(
            S2_5_STATUS_ATTESTATION_FAILED
            if rollback["status"] == "RESTORED_INACTIVE"
            else S2_5_STATUS_RECOVERY_REQUIRED,
            [f"enable --now failed: {error!r}"],
            rollback_receipt=rollback["receipt"],
        )
    observation = _observe_and_build(core=core, observers=observers, clock=clock)
    failing = sorted(
        name for name, ok in observation["verdicts"].items() if not ok
    )
    stale = observation["observer_gate"]["stale"] is not False
    if failing or stale:
        rollback = _rollback_to_disabled(
            intent=intent, core=core, driver=driver, pre_state=pre_state,
            prestate_digest=prestate_digest, clock=clock,
        )
        terminal = (
            "TERMINAL_ROLLED_BACK"
            if rollback["status"] == "RESTORED_INACTIVE"
            else "RECOVERY_REQUIRED"
        )
        _journal_transition(
            journal_path, start_id=intent["start_id"], state=terminal,
            updated_at=_iso(clock()),
        )
        reasons = (
            [f"running attestation failed on dimension(s): {failing}"]
            if failing
            else ["observer/dead-man gate is stale; a PASS cannot be derived"]
        )
        if rollback["status"] != "RESTORED_INACTIVE":
            if recovery_state is not None:
                recovery_state.record(start_id=intent["start_id"], reasons=reasons)
            return _verdict(
                S2_5_STATUS_RECOVERY_REQUIRED,
                reasons + ["rollback-to-disabled did not restore the S2.4 pre-state"],
                rollback_receipt=rollback["receipt"],
            )
        receipt = _base_receipt(
            schema_version="s2_5_running_attestation_v1",
            adapter_id="s2_5_runtime_start_adapter_v1",
            status=S2_5_STATUS_ATTESTATION_FAILED,
            intent=intent, core=core, target_class=target_class,
            owner_fingerprint=owner_fingerprint, observation=observation,
            precheck=precheck_flags, rollback_record=rollback["receipt"],
            applier_node=applier_node, verifier_node=observers.verifier_node_id,
            trusted_host_attestation=None,
            evidence_class="STRUCTURAL_ONLY",
            started_at=started_at, completed_at=_iso(clock()),
            failure_reason="; ".join(reasons),
        )
        receipt, errors = _seal(receipt, now_dt=now_dt)
        return _verdict(
            S2_5_STATUS_ATTESTATION_FAILED, reasons + errors, receipt=receipt,
            rollback_receipt=rollback["receipt"],
        )
    # 全維通過:成功語義按 lane 收斂(simulated/disposable 頂點是 SOURCE_SIMULATION_PASS)。
    completed_at = _iso(clock())
    if target_class == "production":
        attestation_errors = attestation.verify_s2_5_trusted_host_attestation(
            trusted_host_attestation,
            intent_digest=intent["self_digest"],
            running_dimensions=observation["dimensions"],
            observer_gate=observation["observer_gate"],
            now=now_dt,
        )
        status = (
            S2_5_STATUS_RUNNING_ATTESTED if not attestation_errors else S2_5_STATUS_PENDING
        )
        evidence_class = (
            "PLATFORM_OR_EXTERNAL_ATTESTED" if not attestation_errors else "STRUCTURAL_ONLY"
        )
        failure_reason = (
            None
            if not attestation_errors
            else "production running attestation is pending the trusted-host attestor: "
            + "; ".join(attestation_errors)
        )
        bound_attestation = trusted_host_attestation if not attestation_errors else None
    else:
        status = S2_5_STATUS_SIMULATION_PASS
        evidence_class = "LOCAL_REPRODUCIBLE"
        failure_reason = None
        bound_attestation = None
    receipt = _base_receipt(
        schema_version="s2_5_running_attestation_v1",
        adapter_id="s2_5_runtime_start_adapter_v1",
        status=status,
        intent=intent, core=core, target_class=target_class,
        owner_fingerprint=owner_fingerprint, observation=observation,
        precheck=precheck_flags, rollback_record=None,
        applier_node=applier_node, verifier_node=observers.verifier_node_id,
        trusted_host_attestation=bound_attestation,
        evidence_class=evidence_class,
        started_at=started_at, completed_at=completed_at,
        failure_reason=failure_reason,
    )
    receipt, errors = _seal(receipt, now_dt=now_dt)
    if errors:
        # 自產 receipt 過不了中央閘 = 實作缺陷,fail-closed 絕不回成功。
        return _verdict(S2_5_STATUS_ATTESTATION_FAILED, errors, receipt=receipt)
    _journal_transition(
        journal_path, start_id=intent["start_id"], state="TERMINAL_SUCCESS",
        updated_at=completed_at,
    )
    return _verdict(status, [], receipt=receipt)


def _rollback_to_disabled(
    *,
    intent: dict[str, Any],
    core: dict[str, Any],
    driver: Any,
    pre_state: dict[str, Any],
    prestate_digest: str,
    clock: Callable[[], datetime],
) -> dict[str, Any]:
    """失敗即 rollback-to-disabled(§8.3 末段):stop + disable + 驗證回 S2.4 前態。"""

    failure: str | None = None
    try:
        driver.stop()
        driver.disable()
    except Exception as error:  # noqa: BLE001
        failure = repr(error)
    try:
        post_state = _unit_state_from_show(driver.show())
    except Exception as error:  # noqa: BLE001
        failure = failure or repr(error)
        post_state = {
            "active_state": "unknown", "unit_file_state": "unknown",
            "n_restarts": 0, "invocation_id": "none",
        }
    restored = (
        failure is None
        and post_state["active_state"] == "inactive"
        and post_state["unit_file_state"] == "disabled"
        and post_state["active_state"] == pre_state["active_state"]
        and post_state["unit_file_state"] == pre_state["unit_file_state"]
    )
    status = "RESTORED_INACTIVE" if restored else "NOT_RESTORED"
    receipt = _build_rollback_receipt(
        kind="ROLLBACK_TO_DISABLED",
        status=status,
        intent=intent,
        core=core,
        pre_state=pre_state,
        post_state=post_state,
        s2_4_inactive_prestate_digest=prestate_digest,
        watchdog_last=None,
        observed_at=_iso(clock()),
    )
    return {"status": status, "receipt": receipt}


def apply_s2_5_final(
    intent: Any,
    authorization: Any = None,
    driver: Any = None,
    *,
    now: Any = None,
    replay_ledger: Any = None,
    target_class: str = "simulated_harness",
    s2_4_install_effect_receipt: Any = None,
    loader_closure_observation: Any = None,
    s2_4_recovery_clear: Any = None,
    install_lock_free: Any = None,
    s2_1_drill_receipt: Any = None,
    pre_drill_attestation: Any = None,
    recovery_state: S2_5RecoveryState | None = None,
    journal_path: Path | None = None,
    observers: Any = None,
    owner_fingerprint: str | None = None,
    applier_node: str = "s2-5-final-applier",
    trusted_host_attestation: Any = None,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """S2.5B:post-drill 五維再證 + **watchdog reset last**(§3;RESET 是最後一個 lifecycle 操作)。"""

    outcome, precheck_flags, now_dt = _common_gate(
        intent, authorization, driver,
        phase="S2_5B_FINAL",
        now=now,
        replay_ledger=replay_ledger,
        target_class=target_class,
        recovery_state=recovery_state,
        precheck_inputs={
            "s2_4_install_effect_receipt": s2_4_install_effect_receipt,
            "loader_closure_observation": loader_closure_observation,
            "s2_4_recovery_clear": s2_4_recovery_clear,
            "install_lock_free": install_lock_free,
            "s2_1_drill_receipt": s2_1_drill_receipt,
            "pre_drill_attestation": pre_drill_attestation,
        },
    )
    if outcome is not None:
        return outcome
    core = intent["core"]
    clock = clock or (lambda: now_dt)
    reconcile = reconcile_s2_5_journal(journal_path)
    if reconcile["admits_new_work"] is not True:
        return _verdict(S2_5_STATUS_RECOVERY_REQUIRED, reconcile["reasons"])
    if observers is None or not str(getattr(observers, "verifier_node_id", "")):
        return _verdict(
            S2_5_STATUS_REQUEST_REJECTED,
            ["S2.5 requires an independent verifier observation surface (fail-closed)"],
        )
    if observers.verifier_node_id == applier_node:
        return _verdict(
            S2_5_STATUS_REQUEST_REJECTED,
            ["S2.5 verifier node must differ from the applier node"],
        )
    if not owner_fingerprint:
        return _verdict(
            S2_5_STATUS_REQUEST_REJECTED,
            [
                "S2.5 requires the WP3 owner fingerprint (compute_owner_fingerprint) "
                "before any lifecycle effect (fail-closed)"
            ],
        )
    # S2.5B 的 drill 之後前態:unit 必須 enabled/active(drill restore 成功的活實例)。
    pre_properties = driver.show()
    pre_state = _unit_state_from_show(pre_properties)
    precheck_flags["inactive_prestate_verified"] = True  # S2.5B 消費的是 restore 後的活前態。
    if not (
        pre_state["active_state"] == "active"
        and pre_state["unit_file_state"] == "enabled"
        and str(pre_properties.get("FragmentDigest", ""))
        == core["expected_unit_fragment_digest"]
    ):
        return _verdict(
            S2_5_STATUS_REQUEST_REJECTED,
            [
                "S2.5B precheck: the post-drill unit is not the restored active/enabled "
                "instance bound to the exact fragment digest (fail-closed)"
            ],
        )
    started_at = _iso(clock())
    _journal_transition(
        journal_path, start_id=intent["start_id"], state="APPLYING", updated_at=started_at
    )
    attestation.consume_s2_5_authorization(
        replay_ledger, authorization, start_id=intent["start_id"], consumed_at=started_at
    )
    # 五維再證(drill 之後的新 PID/InvocationID;stable identity 的比對折在觀測面)。
    observation = _observe_and_build(core=core, observers=observers, clock=clock)
    failing = sorted(name for name, ok in observation["verdicts"].items() if not ok)
    stale = observation["observer_gate"]["stale"] is not False
    if failing or stale:
        _journal_transition(
            journal_path, start_id=intent["start_id"], state="TERMINAL_FAILED",
            updated_at=_iso(clock()),
        )
        reasons = (
            [f"final attestation failed on dimension(s): {failing}"]
            if failing
            else ["observer/dead-man gate is stale; a PASS cannot be derived"]
        )
        return _verdict(S2_5_STATUS_ATTESTATION_FAILED, reasons)
    # watchdog reset **last**:最後一個 lifecycle 操作是本 phase 的 reset 本身(§3/O-2)。
    try:
        driver.reset_failed()
    except Exception as error:  # noqa: BLE001
        _journal_transition(
            journal_path, start_id=intent["start_id"], state="RECOVERY_REQUIRED",
            updated_at=_iso(clock()),
        )
        if recovery_state is not None:
            recovery_state.record(
                start_id=intent["start_id"], reasons=[f"reset-failed failed: {error!r}"]
            )
        return _verdict(
            S2_5_STATUS_RECOVERY_REQUIRED, [f"watchdog reset failed: {error!r}"]
        )
    post_reset = observers.observe_post_reset()
    watchdog_last = attestation.build_watchdog_last(
        n_restarts_before=observation["dimensions"]["unit"]["n_restarts_baseline"],
        n_restarts_after=int(post_reset.get("n_restarts", 0)),
        invocation_id_before=observation["dimensions"]["pid_cgroup"]["invocation_id"],
        invocation_id_after=str(post_reset.get("invocation_id", "none")),
        last_lifecycle_operation_kind=str(
            post_reset.get("last_lifecycle_operation_kind", "")
        ),
        authorized_operation_kind="systemd_reset_failed",
        watchdog_usec="none",
    )
    reset_clean = (
        watchdog_last["unexplained_restart_detected"] is False
        and watchdog_last["last_transition_matches_authorized_op"] is True
        and watchdog_last["n_restarts_after"] == 0
    )
    reset_receipt = _build_rollback_receipt(
        kind="WATCHDOG_RESET_LAST",
        status="RESET_CLEAN" if reset_clean else "FAILED",
        intent=intent,
        core=core,
        pre_state=pre_state,
        post_state={
            "active_state": str(post_reset.get("active_state", "active")),
            "unit_file_state": str(post_reset.get("unit_file_state", "enabled")),
            "n_restarts": int(post_reset.get("n_restarts", 0)),
            "invocation_id": str(post_reset.get("invocation_id", "none")),
        },
        s2_4_inactive_prestate_digest=None,
        watchdog_last=watchdog_last,
        observed_at=_iso(clock()),
    )
    stable_identity_match = bool(post_reset.get("stable_identity_match", False))
    completed_at = _iso(clock())
    if not reset_clean or not stable_identity_match:
        _journal_transition(
            journal_path, start_id=intent["start_id"], state="TERMINAL_FAILED",
            updated_at=completed_at,
        )
        return _verdict(
            S2_5_STATUS_ATTESTATION_FAILED,
            [
                "watchdog reset last is not clean or the stable identity drifted "
                "(supervening restart / unauthorized transition makes RESET_CLEAN "
                "unreachable)"
            ],
            rollback_receipt=reset_receipt,
        )
    if target_class == "production":
        attestation_errors = attestation.verify_s2_5_trusted_host_attestation(
            trusted_host_attestation,
            intent_digest=intent["self_digest"],
            running_dimensions=observation["dimensions"],
            observer_gate=observation["observer_gate"],
            now=now_dt,
        )
        status = (
            S2_5_STATUS_FINAL_ATTESTED if not attestation_errors else S2_5_STATUS_PENDING
        )
        evidence_class = (
            "PLATFORM_OR_EXTERNAL_ATTESTED" if not attestation_errors else "STRUCTURAL_ONLY"
        )
        failure_reason = (
            None
            if not attestation_errors
            else "production final attestation is pending the trusted-host attestor: "
            + "; ".join(attestation_errors)
        )
        bound_attestation = trusted_host_attestation if not attestation_errors else None
    else:
        status = S2_5_STATUS_SIMULATION_PASS
        evidence_class = "LOCAL_REPRODUCIBLE"
        failure_reason = None
        bound_attestation = None
    receipt = _base_receipt(
        schema_version="s2_5_final_attestation_v1",
        adapter_id="s2_5_final_attestation_adapter_v1",
        status=status,
        intent=intent, core=core, target_class=target_class,
        owner_fingerprint=owner_fingerprint, observation=observation,
        precheck=precheck_flags, rollback_record=None,
        applier_node=applier_node, verifier_node=observers.verifier_node_id,
        trusted_host_attestation=bound_attestation,
        evidence_class=evidence_class,
        started_at=started_at, completed_at=completed_at,
        failure_reason=failure_reason,
    )
    receipt["s2_1_drill_receipt_digest"] = core["s2_1_drill_receipt_digest"]
    receipt["pre_drill_attestation_digest"] = core["pre_drill_attestation_digest"]
    receipt["watchdog_last"] = watchdog_last
    receipt["watchdog_reset_receipt_digest"] = reset_receipt["self_digest"]
    receipt["stable_identity_match"] = stable_identity_match
    receipt, errors = _seal(receipt, now_dt=now_dt)
    if errors:
        return _verdict(S2_5_STATUS_ATTESTATION_FAILED, errors, receipt=receipt)
    _journal_transition(
        journal_path, start_id=intent["start_id"], state="TERMINAL_SUCCESS",
        updated_at=completed_at,
    )
    return _verdict(status, [], receipt=receipt, reset_receipt=reset_receipt)
