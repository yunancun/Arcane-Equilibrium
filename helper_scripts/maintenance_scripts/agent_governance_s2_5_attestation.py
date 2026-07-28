#!/usr/bin/env python3
"""S2.5(WP5)attestation 葉——permit/attestor SSHSIG 驗證、observer/watchdog 導出、replay ledger。

design §5.4/§5.6:三個 domain-separated profile 共用 §9.1 實體信任根(``ssh-keygen -Y verify``
綁 namespace,任一 S2.0/S2.1/S2.4 namespace 的簽章重放為 S2.5 permit/attestor 一律驗簽失敗):

* S2.5A start permit  —— identity ``aiml-s2-5a-start-operator-v1``,
  namespace ``arcane-equilibrium-aiml-s2-5a-start``;
* S2.5B final permit  —— identity ``aiml-s2-5b-final-operator-v1``,
  namespace ``arcane-equilibrium-aiml-s2-5b-final``;
* runtime attestor    —— identity ``aiml-s2-5-runtime-attestor-v1``,
  namespace ``arcane-equilibrium-aiml-s2-5-running-attestation``。

鐵則(鏡 W4b):``RUNNING_ATTESTED``/``FINAL_ATTESTED`` 的**唯一**鑰匙是驗簽通過的 attestor
artifact(applier ≠ attestor;freshness 只讀**已簽的** ``trusted_host_time``);driver 宣稱的
evidence_class 一律拒;operator permit 簽章單獨存在永不產生 attested status(permit ≠
attestation,namespace 分離使兩者不可互換)。private key 不在 Mac 也不在 trade-core 的 WP5
可及面——production 不可達的原因是 key custody,不是構造不可達。

本葉零 lifecycle 動詞、零主機動作;caller 提供的 status 不可自證(status 由 evidence 導出)。
九項 authority 恆 false。
"""
from __future__ import annotations

import hmac
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
for _candidate in (HELPER_DIR, ML_TRAINING_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import agent_governance_aiml_trusted_host as _trusted_host  # noqa: E402
from aiml_gate_receipt_schema_core import (  # noqa: E402
    _canonical_bytes,
    _parse_timestamp,
    artifact_self_digest,
    canonical_digest,
)

# ── §5.6 三個 domain-separated profile(namespace 不與 S2.0/S2.1/S2.4 任一重疊)──────
S2_5A_START_PERMIT_IDENTITY = "aiml-s2-5a-start-operator-v1"
S2_5A_START_PERMIT_NAMESPACE = "arcane-equilibrium-aiml-s2-5a-start"
S2_5B_FINAL_PERMIT_IDENTITY = "aiml-s2-5b-final-operator-v1"
S2_5B_FINAL_PERMIT_NAMESPACE = "arcane-equilibrium-aiml-s2-5b-final"
S2_5_ATTESTOR_IDENTITY = "aiml-s2-5-runtime-attestor-v1"
S2_5_ATTESTOR_NAMESPACE = "arcane-equilibrium-aiml-s2-5-running-attestation"
S2_5_PERMIT_PROFILES = {
    "S2_5A_START": {
        "profile_identity": S2_5A_START_PERMIT_IDENTITY,
        "signature_namespace": S2_5A_START_PERMIT_NAMESPACE,
    },
    "S2_5B_FINAL": {
        "profile_identity": S2_5B_FINAL_PERMIT_IDENTITY,
        "signature_namespace": S2_5B_FINAL_PERMIT_NAMESPACE,
    },
}
# §5.6:permit TTL ≤ 15 min、時鐘偏移 60s;attestation TTL 同 §9.1 上限。
MAX_S2_5_PERMIT_TTL_SECONDS = 900
S2_5_PERMIT_CLOCK_SKEW_SECONDS = 60
MAX_S2_5_ATTESTATION_TTL_SECONDS = 900
# attestation 的前向偏移上限:trusted_host_time 不得晚於 now + 60s(E3:未設上限時
# now+400d 的「未來簽章」可過——TTL 不等式只綁 trusted_host_time↔expires_at 自身)。
S2_5_ATTESTATION_FORWARD_SKEW_SECONDS = 60
S2_5_AUTHORIZATION_ID_PREFIX = "s2-5-auth-"
S2_5_REPLAY_LEDGER_SCHEMA_VERSION = "s2_5_authorization_replay_ledger_v1"

# §9.1 實體信任根複用(module-level 常量,測試以 throwaway key 成對 monkeypatch;
# 真私鑰不在 Mac 也不在 trade-core)。
S2_5_TRUST_ROOT_PUBLIC_KEY = _trusted_host.TRUSTED_EXECUTION_PUBLIC_KEY
S2_5_TRUST_ROOT_FINGERPRINT = "SHA256:uGJ9veN7PoE6BBgfsSP2aiMndrwgbt7o/7/YfdzNzCQ"

REPLAY_STATUS_VALID = "UNCONSUMED_AUTHORIZATION_VALID"
REPLAY_STATUS_REJECTED = "AUTHORIZATION_REJECTED"

# §5.6 permit payload 的 exact 欄位序(缺項/多項即拒——少一欄就等於少簽一個綁定)。
_S2_5A_PAYLOAD_FIELDS = (
    "domain",
    "authorization_id",
    "start_core_digest",
    "start_id",
    "source_head",
    "target_host",
    "s2_4_install_effect_receipt_digest",
    "expected_unit_fragment_digest",
    "rollback_budget_seconds",
    "issued_at",
    "expires_at",
)
_S2_5B_PAYLOAD_FIELDS = _S2_5A_PAYLOAD_FIELDS + (
    "s2_1_drill_receipt_digest",
    "pre_drill_attestation_digest",
)
_PERMIT_FIELDS = (
    "schema_version",
    "phase",
    "profile_identity",
    "signature_namespace",
    "payload_binding",
    "sshsig_armored",
)
S2_5_PERMIT_SCHEMA_VERSION = "s2_5_operator_permit_v1"


def non_finite_number_paths(value: Any, path: str = "$") -> list[str]:
    """遞迴找出 NaN/±Infinity(E3 P2-6:canonical bytes 的 ``allow_nan=False`` 會對它們
    raise ``ValueError``——載入面必須先給 typed reason,而不是讓例外從 fail-closed 閘逸出)。"""

    hits: list[str] = []
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return [path]
    if isinstance(value, dict):
        for key, child in value.items():
            hits.extend(non_finite_number_paths(child, f"{path}.{key}"))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            hits.extend(non_finite_number_paths(child, f"{path}[{index}]"))
    return hits


def s2_5_permit_payload_fields(phase: str) -> tuple[str, ...]:
    """該 phase 的 §5.6 exact payload 欄位序。"""

    if phase == "S2_5A_START":
        return _S2_5A_PAYLOAD_FIELDS
    if phase == "S2_5B_FINAL":
        return _S2_5B_PAYLOAD_FIELDS
    raise ValueError(f"unknown S2.5 phase: {phase!r}")


def derive_s2_5_authorization_id(payload_binding: dict[str, Any]) -> str:
    """authorization_id 由 payload(排除自身)導出——同 §5.1「digest 導 id」紀律。"""

    return S2_5_AUTHORIZATION_ID_PREFIX + canonical_digest(
        {k: v for k, v in payload_binding.items() if k != "authorization_id"}
    ).split(":", 1)[1]


def s2_5_permit_signed_bytes(permit: dict[str, Any]) -> bytes:
    """被簽 bytes = canonical(payload_binding)(域已折在 payload 的 domain 欄)。"""

    return _canonical_bytes(permit["payload_binding"])


def build_s2_5_operator_permit(intent: dict[str, Any]) -> dict[str, Any]:
    """由 exact intent 組出**未簽**permit(真簽章由 operator 在帶外簽;測試用 throwaway key)。"""

    core = intent["core"]
    phase = core["phase"]
    profile = S2_5_PERMIT_PROFILES[phase]
    payload: dict[str, Any] = {
        "domain": profile["signature_namespace"],
        "authorization_id": "",
        "start_core_digest": intent["core_digest"],
        "start_id": intent["start_id"],
        "source_head": core["source_head"],
        "target_host": core["target_host"],
        "s2_4_install_effect_receipt_digest": core["s2_4_install_effect_receipt_digest"],
        "expected_unit_fragment_digest": core["expected_unit_fragment_digest"],
        "rollback_budget_seconds": core["rollback_budget_seconds"],
        "issued_at": core["issued_at"],
        "expires_at": core["expires_at"],
    }
    if phase == "S2_5B_FINAL":
        payload["s2_1_drill_receipt_digest"] = core["s2_1_drill_receipt_digest"]
        payload["pre_drill_attestation_digest"] = core["pre_drill_attestation_digest"]
    payload["authorization_id"] = derive_s2_5_authorization_id(payload)
    return {
        "schema_version": S2_5_PERMIT_SCHEMA_VERSION,
        "phase": phase,
        "profile_identity": profile["profile_identity"],
        "signature_namespace": profile["signature_namespace"],
        "payload_binding": payload,
        "sshsig_armored": "",
    }


def verify_s2_5_operator_permit(
    permit: Any, intent: Any, *, now: Any
) -> list[str]:
    """permit 的 exact 驗證(shape + payload 綁定 + TTL/skew + 信任根 + 真 SSHSIG)。

    任一漂移即 typed reason;空 list 才算通過。permit 通過**永不**產生 attested status。
    """

    errors: list[str] = []
    if not isinstance(permit, dict) or not isinstance(intent, dict):
        return ["s2_5 permit and intent must be objects"]
    # E3 P2-6:NaN/Infinity 在 canonical bytes(allow_nan=False)上會炸;載入前先 typed 拒。
    non_finite = non_finite_number_paths(permit)
    if non_finite:
        return [
            f"s2_5 permit carries non-finite numbers at {non_finite}; NaN/Infinity have no "
            "canonical byte form and are rejected before any digest derivation (fail-closed)"
        ]
    if tuple(sorted(permit)) != tuple(sorted(_PERMIT_FIELDS)):
        return ["s2_5 permit fields do not match the exact contract"]
    core = intent.get("core") or {}
    phase = core.get("phase")
    profile = S2_5_PERMIT_PROFILES.get(str(phase))
    if profile is None:
        return [f"s2_5 permit cannot bind an unknown phase: {phase!r}"]
    if permit.get("schema_version") != S2_5_PERMIT_SCHEMA_VERSION:
        errors.append("s2_5 permit schema_version is invalid")
    if permit.get("phase") != phase:
        errors.append("s2_5 permit phase differs from the intent phase")
    if permit.get("profile_identity") != profile["profile_identity"]:
        errors.append("s2_5 permit profile_identity is not the phase profile")
    if permit.get("signature_namespace") != profile["signature_namespace"]:
        errors.append("s2_5 permit signature_namespace is not the phase namespace")
    payload = permit.get("payload_binding")
    if not isinstance(payload, dict):
        return errors + ["s2_5 permit payload_binding must be an object"]
    expected_fields = s2_5_permit_payload_fields(str(phase))
    if tuple(sorted(payload)) != tuple(sorted(expected_fields)):
        errors.append(
            "s2_5 permit payload_binding key set is not the exact §5.6 field list "
            "(a missing field silently unbinds part of the signature)"
        )
        return errors
    expected_payload: dict[str, Any] = {
        "domain": profile["signature_namespace"],
        "start_core_digest": intent.get("core_digest"),
        "start_id": intent.get("start_id"),
        "source_head": core.get("source_head"),
        "target_host": core.get("target_host"),
        "s2_4_install_effect_receipt_digest": core.get("s2_4_install_effect_receipt_digest"),
        "expected_unit_fragment_digest": core.get("expected_unit_fragment_digest"),
        "rollback_budget_seconds": core.get("rollback_budget_seconds"),
        "issued_at": core.get("issued_at"),
        "expires_at": core.get("expires_at"),
    }
    if phase == "S2_5B_FINAL":
        expected_payload["s2_1_drill_receipt_digest"] = core.get("s2_1_drill_receipt_digest")
        expected_payload["pre_drill_attestation_digest"] = core.get(
            "pre_drill_attestation_digest"
        )
    for field, expected in expected_payload.items():
        if payload.get(field) != expected:
            errors.append(f"s2_5 permit payload_binding.{field} differs from the exact intent")
    if payload.get("authorization_id") != derive_s2_5_authorization_id(payload):
        errors.append("s2_5 permit authorization_id does not re-derive from its payload")
    # TTL/skew/expiry(§5.6:TTL ≤ 15 min、skew 60s)。
    try:
        issued = _parse_timestamp(str(payload.get("issued_at")))
        expires = _parse_timestamp(str(payload.get("expires_at")))
        moment = _parse_timestamp(str(now)) if not isinstance(now, datetime) else (
            now if now.tzinfo else now.replace(tzinfo=timezone.utc)
        )
        if (expires - issued).total_seconds() > MAX_S2_5_PERMIT_TTL_SECONDS:
            errors.append("s2_5 permit TTL exceeds the 900s ceiling")
        if issued - moment > timedelta(seconds=S2_5_PERMIT_CLOCK_SKEW_SECONDS):
            errors.append("s2_5 permit issued_at is beyond the allowed clock skew")
        if moment >= expires:
            errors.append("s2_5 permit is expired")
    except (TypeError, ValueError) as error:
        errors.append(f"s2_5 permit timestamps are unparseable: {error}")
    # 信任根指紋綁定 + 真 SSHSIG(``ssh-keygen -Y verify`` 綁 namespace ⇒ 域分離)。
    try:
        actual_fingerprint = _trusted_host.ssh_public_key_fingerprint(
            S2_5_TRUST_ROOT_PUBLIC_KEY
        )
    except ValueError:
        actual_fingerprint = ""
    if not hmac.compare_digest(actual_fingerprint, str(S2_5_TRUST_ROOT_FINGERPRINT)):
        errors.append("s2_5 trust-root fingerprint mismatch")
    signature = str(permit.get("sshsig_armored") or "").encode("ascii", "replace")
    if not _trusted_host._verify_ssh_signature(
        s2_5_permit_signed_bytes(permit),
        signature,
        public_key=S2_5_TRUST_ROOT_PUBLIC_KEY,
        identity=profile["profile_identity"],
        namespace=profile["signature_namespace"],
    ):
        errors.append("s2_5 permit SSH signature is invalid")
    return errors


# ── replay ledger(hash-chained consume-once;§5.7 路徑上的持久化由 lifecycle 葉負責)──
def s2_5_replay_ledger_entry_errors(entries: Any) -> list[str]:
    """entries 的 exact hash-chain 重驗:seq 自 0 單調、prev 綁前一筆、entry_digest 重算、
    fsynced 恆 true(鏡 sibling ``s2_4_authorization_replay_ledger_v1`` 的 entry 契約)。

    seq 是 fork 偵測的判別欄:兩筆「同 prev」的併發雙寫在 append-only 鏈上必然使其中
    一筆的 seq/prev 至少一項與重算值不符——沒有 seq 時,截斷後重放的 prefix 仍是合法鏈。
    """

    if not isinstance(entries, list):
        return ["s2_5 replay ledger entries must be a list"]
    non_finite = non_finite_number_paths(entries)
    if non_finite:
        return [
            f"s2_5 replay ledger carries non-finite numbers at {non_finite}; NaN/Infinity "
            "have no canonical byte form and are rejected before any digest derivation"
        ]
    previous: str | None = None
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            return [f"s2_5 replay ledger entry {index} must be an object"]
        expected = canonical_digest(
            {key: value for key, value in entry.items() if key != "entry_digest"}
        )
        if (
            entry.get("seq") != index
            or entry.get("prev_entry_digest") != previous
            or entry.get("entry_digest") != expected
            or entry.get("fsynced") is not True
        ):
            return [
                f"s2_5 replay ledger hash chain is broken at entry {index} (seq/prev/"
                "digest/fsynced re-derivation failed; a truncated, forked or reordered "
                "ledger is rejected fail-closed)"
            ]
        previous = entry["entry_digest"]
    return []


def derive_s2_5_replay_binding(
    permit: Any, replay_ledger: Any, *, start_id: Any
) -> dict[str, Any]:
    """一張 permit 只可被消費一次,且只可綁一個 start_id(重複/斷鏈/換綁一律拒)。"""

    verdict: dict[str, Any] = {"status": REPLAY_STATUS_REJECTED, "reasons": []}
    if not isinstance(permit, dict):
        verdict["reasons"] = ["s2_5 replay binding requires the permit object"]
        return verdict
    authorization_id = (permit.get("payload_binding") or {}).get("authorization_id")
    if not authorization_id:
        verdict["reasons"] = ["s2_5 permit carries no authorization_id"]
        return verdict
    if not isinstance(replay_ledger, dict) or not isinstance(
        replay_ledger.get("entries"), list
    ):
        verdict["reasons"] = [
            "s2_5 authorization replay-consumption cannot be proved without the "
            "replay ledger (fail-closed)"
        ]
        return verdict
    entries = replay_ledger["entries"]
    chain_errors = s2_5_replay_ledger_entry_errors(entries)
    if chain_errors:
        verdict["reasons"] = chain_errors
        return verdict
    previous: str | None = None
    for entry in entries:
        if entry.get("authorization_id") == authorization_id:
            verdict["reasons"] = [
                "s2_5 authorization was already consumed; a consumed authorization is "
                "never released by rollback"
            ]
            return verdict
        previous = entry["entry_digest"]
    verdict["status"] = REPLAY_STATUS_VALID
    verdict["next_prev_entry_digest"] = previous
    verdict["next_seq"] = len(entries)
    verdict["authorization_id"] = authorization_id
    verdict["start_id"] = start_id
    return verdict


def consume_s2_5_authorization(
    replay_ledger: dict[str, Any], permit: dict[str, Any], *, start_id: str, consumed_at: str
) -> dict[str, Any]:
    """把一筆消費 append 進 hash chain(呼叫前必先過 :func:`derive_s2_5_replay_binding`)。"""

    binding = derive_s2_5_replay_binding(permit, replay_ledger, start_id=start_id)
    if binding["status"] != REPLAY_STATUS_VALID:
        raise ValueError("; ".join(binding["reasons"]))
    entry = {
        "seq": binding["next_seq"],
        "authorization_id": binding["authorization_id"],
        "start_id": start_id,
        "consumed_at": consumed_at,
        "prev_entry_digest": binding["next_prev_entry_digest"],
        "fsynced": True,
    }
    entry["entry_digest"] = canonical_digest(entry)
    replay_ledger["entries"].append(entry)
    return entry


def seal_s2_5_replay_ledger(
    replay_ledger: dict[str, Any], *, ledger_path: str
) -> dict[str, Any]:
    """把 in-memory chain 封成 closed ``s2_5_authorization_replay_ledger_v1`` artifact。

    ``ledger_path`` 一律取呼叫端實際要寫入的路徑(鏡 s2_4 lock 葉:被讀回物件自報的
    位置不可沿用)。``self_digest`` 是 integrity 證據,同時是 journal/receipt 釘 head 的錨。
    """

    sealed: dict[str, Any] = {
        "schema_version": S2_5_REPLAY_LEDGER_SCHEMA_VERSION,
        "ledger_path": str(ledger_path),
        "entries": [dict(entry) for entry in replay_ledger.get("entries") or []],
        "append_only": True,
    }
    sealed["self_digest"] = artifact_self_digest(sealed)
    return sealed


# ── observer/dead-man gate 與 watchdog-last 的**導出式** builder(caller 不可自證)────
def build_observer_gate(
    *,
    verifier_node_id: str,
    max_evidence_age_seconds: int,
    oldest_evidence_at: str,
    evaluated_at: str,
) -> dict[str, Any]:
    """``stale`` 由證據年齡導出——證據缺席/超齡 ⇒ stale=true,不存在 green-by-default。"""

    age = (
        _parse_timestamp(evaluated_at) - _parse_timestamp(oldest_evidence_at)
    ).total_seconds()
    return {
        "verifier_node_id": verifier_node_id,
        "db_evidence_via_observer_role": True,
        "max_evidence_age_seconds": int(max_evidence_age_seconds),
        "oldest_evidence_at": oldest_evidence_at,
        "evaluated_at": evaluated_at,
        "stale": not 0 <= age <= int(max_evidence_age_seconds),
    }


def build_watchdog_last(
    *,
    n_restarts_before: int,
    n_restarts_after: int,
    invocation_id_before: str,
    invocation_id_after: str,
    last_lifecycle_operation_kind: str,
    authorized_operation_kind: str,
    watchdog_usec: Any = "none",
) -> dict[str, Any]:
    """watchdog-last 謂詞的導出(design §3/§5.4;O-2:``watchdog_usec`` 誠實記 ``none``)。

    ``unexplained_restart_detected`` 由觀測導出:reset 之後 restart 計數 > 0 或最後一次
    lifecycle transition 不是已授權操作本身,即為 supervening/unexplained。
    """

    matches = last_lifecycle_operation_kind == authorized_operation_kind
    unexplained = (
        int(n_restarts_after) > 0
        if authorized_operation_kind == "systemd_reset_failed"
        else int(n_restarts_after) > int(n_restarts_before)
    ) or not matches
    return {
        "watchdog_usec": watchdog_usec,
        "n_restarts_before": int(n_restarts_before),
        "n_restarts_after": int(n_restarts_after),
        "invocation_id_before": invocation_id_before,
        "invocation_id_after": invocation_id_after,
        "last_lifecycle_operation": {"kind": last_lifecycle_operation_kind},
        "last_transition_matches_authorized_op": matches,
        "unexplained_restart_detected": unexplained,
    }


# ── trusted-host attestor(attested status 的唯一鑰匙)───────────────────────────
def s2_5_attestation_signed_bytes(attestation: dict[str, Any]) -> bytes:
    """被簽 bytes = canonical(attestation 排除 ``signature_armored``)。"""

    return _canonical_bytes(
        {k: v for k, v in attestation.items() if k != "signature_armored"}
    )


def build_s2_5_trusted_host_attestation(
    *,
    attestation_kind: str,
    intent_digest: str,
    running_dimensions: dict[str, Any],
    observer_gate: dict[str, Any],
    trusted_host_time: str,
    ttl_seconds: int = MAX_S2_5_ATTESTATION_TTL_SECONDS,
) -> dict[str, Any]:
    """組出**未簽**的 attestation(真簽章只可能出現在帶外受信主機;測試用 throwaway key)。"""

    moment = _parse_timestamp(str(trusted_host_time))
    return {
        "attestor_identity": S2_5_ATTESTOR_IDENTITY,
        "signature_namespace": S2_5_ATTESTOR_NAMESPACE,
        "attestation_kind": attestation_kind,
        "intent_digest": intent_digest,
        "running_dimensions_digest": canonical_digest(running_dimensions),
        "observer_gate_digest": canonical_digest(observer_gate),
        "trusted_host_time": moment.isoformat(),
        "expires_at": (moment + timedelta(seconds=int(ttl_seconds))).isoformat(),
        "signature_armored": "",
    }


def verify_s2_5_trusted_host_attestation(
    attestation: Any,
    *,
    intent_digest: Any,
    running_dimensions: Any,
    observer_gate: Any,
    now: Any,
    expected_kind: str | None = None,
) -> list[str]:
    """attested status 的唯一鑰匙:無簽/壞簽/錯 fingerprint/錯 namespace/過期 全部拒。

    freshness 只讀**已簽的** ``trusted_host_time``(caller 的 ``now`` 只用來擋整體過期與
    前向偏移,絕不反向放寬);``running_dimensions_digest``/``observer_gate_digest`` 由
    receipt 本體重算比對——attestor 簽的是 exact 觀測,不是一個名字。``expected_kind``
    由中央閘按 phase 傳入(A=running/B=final):kind 錯配即拒,B 簽章不可重放為 A。
    """

    if attestation is None:
        return [
            "attested status requires a trusted-host attestor artifact; none is present "
            "(an operator permit alone never yields an attested status)"
        ]
    if not isinstance(attestation, dict):
        return ["s2_5 trusted-host attestation must be an object"]
    errors: list[str] = []
    for field, expected in (
        ("attestor_identity", S2_5_ATTESTOR_IDENTITY),
        ("signature_namespace", S2_5_ATTESTOR_NAMESPACE),
    ):
        if attestation.get(field) != expected:
            errors.append(f"s2_5 attestation {field} is invalid")
    if expected_kind is not None and attestation.get("attestation_kind") != expected_kind:
        errors.append(
            f"s2_5 attestation attestation_kind {attestation.get('attestation_kind')!r} "
            f"does not match the phase-expected kind {expected_kind!r} (an A/B signature "
            "is never replayable across phases)"
        )
    if attestation.get("intent_digest") != intent_digest:
        errors.append("s2_5 attestation intent_digest does not bind the exact intent")
    if attestation.get("running_dimensions_digest") != canonical_digest(running_dimensions):
        errors.append(
            "s2_5 attestation running_dimensions_digest does not re-derive from the "
            "receipt's observed dimensions"
        )
    if attestation.get("observer_gate_digest") != canonical_digest(observer_gate):
        errors.append(
            "s2_5 attestation observer_gate_digest does not re-derive from the receipt's "
            "observer gate"
        )
    try:
        trusted_time = _parse_timestamp(str(attestation.get("trusted_host_time")))
        expires = _parse_timestamp(str(attestation.get("expires_at")))
        if not trusted_time < expires:
            errors.append("s2_5 attestation trusted_host_time must precede expires_at")
        if (expires - trusted_time).total_seconds() > MAX_S2_5_ATTESTATION_TTL_SECONDS:
            errors.append("s2_5 attestation TTL exceeds its ceiling")
        moment = _parse_timestamp(str(now)) if not isinstance(now, datetime) else (
            now if now.tzinfo else now.replace(tzinfo=timezone.utc)
        )
        if moment >= expires:
            errors.append("s2_5 attestation is expired")
        # 前向偏移上限:trusted_host_time 晚於 now+skew 的「未來簽章」拒(E3:無上限時
        # now+400d 的簽章可過——TTL 只綁 trusted_host_time↔expires_at 自身)。
        if trusted_time - moment > timedelta(
            seconds=S2_5_ATTESTATION_FORWARD_SKEW_SECONDS
        ):
            errors.append(
                "s2_5 attestation trusted_host_time is beyond the allowed forward clock "
                "skew (a future-dated attestation is rejected fail-closed)"
            )
    except (TypeError, ValueError) as error:
        errors.append(f"s2_5 attestation timestamps are unparseable: {error}")
    try:
        actual_fingerprint = _trusted_host.ssh_public_key_fingerprint(
            S2_5_TRUST_ROOT_PUBLIC_KEY
        )
    except ValueError:
        actual_fingerprint = ""
    if not hmac.compare_digest(actual_fingerprint, str(S2_5_TRUST_ROOT_FINGERPRINT)):
        errors.append("s2_5 trust-root fingerprint mismatch")
    signature = str(attestation.get("signature_armored") or "").encode("ascii", "replace")
    if not _trusted_host._verify_ssh_signature(
        s2_5_attestation_signed_bytes(attestation),
        signature,
        public_key=S2_5_TRUST_ROOT_PUBLIC_KEY,
        identity=S2_5_ATTESTOR_IDENTITY,
        namespace=S2_5_ATTESTOR_NAMESPACE,
    ):
        errors.append("s2_5 attestation SSH signature is invalid")
    return errors
