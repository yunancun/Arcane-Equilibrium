"""Structural tests for the S1.2 (LR0B) WORM terminal-receipt sink Adapter and
its central-validator wiring, plus the S1.1 pg_readonly central wiring (CC-D2).

Hermetic / stdlib-only (no filesystem WORM store here — that is the disposable
proof in ``test_agent_governance_terminal_receipt_sink_disposable.py``).  Covers
intent derivation/validation, the ``external_worm`` fail-closed gate,
committed-vs-uncommitted result invariants, independent/same-actor readback ACK
rules, freshness, secret fail-closed, central ``validate_aiml_artifact``
dispatch for the three WORM schemas, and the pg_readonly central gate: mandates
``now``, rejects ``production`` / stale / hand-built wrong-binding receipts.
"""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_terminal_receipt_sink as worm  # noqa: E402
import agent_governance_pg_readonly_identity as pg_readonly  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402


DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
HEAD_A = "a" * 40
APPROVED_AT = "2026-07-22T09:00:00Z"
EXPIRES_AT = "2026-07-22T11:00:00Z"
NOW = "2026-07-22T10:00:00Z"


def _payload() -> dict:
    return {"kind": "disposable_proof_payload_v1", "note": "non-secret digests only"}


def _intent(**overrides: object) -> dict:
    payload_digest = worm.terminal_payload_digest(_payload())
    intent = worm.build_terminal_receipt_append_intent(
        intent_id="intent-worm-000001",
        terminal_receipt_type="disposable_proof_payload_v1",
        final_source_head=HEAD_A,
        landing_scope_id=DIGEST_A,
        learning_runtime_digest=DIGEST_B,
        terminal_payload_digest=payload_digest,
        append_actor_id="append-actor",
        approved_by="PM",
        approved_at=APPROVED_AT,
        expires_at=EXPIRES_AT,
    )
    intent.update(overrides)
    return intent


# --------------------------------------------------------------------------- #
# intent
# --------------------------------------------------------------------------- #
def test_build_intent_derives_idempotency_typed_confirm_and_digest() -> None:
    intent = _intent()
    assert intent["idempotency_key"] == worm.terminal_receipt_idempotency_key(
        intent["payload_binding"]
    )
    assert intent["typed_confirm"] == (
        f"terminal-append:{DIGEST_A}:DISPOSABLE_PROOF:intent-worm-000001"
    )
    assert intent["intent_digest"] == worm.terminal_receipt_intent_digest(intent)
    assert intent["target_class"] == "disposable_local_worm_emulation"
    assert worm.validate_terminal_receipt_append_intent(intent, now=NOW) == []


def test_external_worm_target_is_rejected_fail_closed() -> None:
    intent = worm.build_terminal_receipt_append_intent(
        intent_id="intent-worm-000002",
        terminal_receipt_type="aiml_module_landed_for_trading_receipt_v1",
        final_source_head=HEAD_A,
        landing_scope_id=DIGEST_A,
        learning_runtime_digest=DIGEST_B,
        terminal_payload_digest=worm.terminal_payload_digest(_payload()),
        append_actor_id="append-actor",
        approved_by="PM",
        approved_at=APPROVED_AT,
        expires_at=EXPIRES_AT,
        target_class="external_worm",
    )
    errors = worm.validate_terminal_receipt_append_intent(intent, now=NOW)
    assert any("external_worm is rejected fail-closed" in error for error in errors)


def test_intent_idempotency_key_tamper_is_rejected() -> None:
    intent = _intent()
    intent["idempotency_key"] = "sha256:" + "0" * 64
    intent["intent_digest"] = worm.terminal_receipt_intent_digest(intent)
    errors = worm.validate_terminal_receipt_append_intent(intent, now=NOW)
    assert any("idempotency_key is not derived" in error for error in errors)


def test_intent_typed_confirm_tamper_is_rejected() -> None:
    intent = _intent()
    intent["typed_confirm"] = "terminal-append:tampered"
    intent["intent_digest"] = worm.terminal_receipt_intent_digest(intent)
    errors = worm.validate_terminal_receipt_append_intent(intent, now=NOW)
    assert any("typed_confirm is not bound" in error for error in errors)


def test_intent_type_state_mismatch_is_rejected() -> None:
    intent = _intent()
    intent["payload_binding"]["terminal_state"] = "MODULE_LANDED_FOR_TRADING"
    intent["idempotency_key"] = worm.terminal_receipt_idempotency_key(
        intent["payload_binding"]
    )
    intent["typed_confirm"] = worm._typed_confirm(
        DIGEST_A, "MODULE_LANDED_FOR_TRADING", intent["intent_id"]
    )
    intent["intent_digest"] = worm.terminal_receipt_intent_digest(intent)
    errors = worm.validate_terminal_receipt_append_intent(intent, now=NOW)
    assert any("terminal_state are inconsistent" in error for error in errors)


def test_intent_stale_is_rejected_when_now_supplied() -> None:
    intent = _intent()
    errors = worm.validate_terminal_receipt_append_intent(
        intent, now="2026-07-22T12:00:00Z"
    )
    assert any("intent is not fresh" in error for error in errors)


def test_intent_missing_hard_stops_is_rejected() -> None:
    intent = _intent()
    intent["hard_stops"] = ["only one stop that is not the contract"]
    intent["intent_digest"] = worm.terminal_receipt_intent_digest(intent)
    errors = worm.validate_terminal_receipt_append_intent(intent, now=NOW)
    assert any("required hard stops are missing" in error for error in errors)


def test_intent_secret_like_content_fails_closed_at_build() -> None:
    with pytest.raises(worm.SecretLeakageError):
        worm.build_terminal_receipt_append_intent(
            intent_id="intent-worm-000003",
            terminal_receipt_type="disposable_proof_payload_v1",
            final_source_head=HEAD_A,
            landing_scope_id=DIGEST_A,
            learning_runtime_digest=DIGEST_B,
            terminal_payload_digest=worm.terminal_payload_digest(_payload()),
            append_actor_id="password=hunter2",
            approved_by="PM",
            approved_at=APPROVED_AT,
            expires_at=EXPIRES_AT,
        )


# --------------------------------------------------------------------------- #
# result (committed vs uncommitted invariants + intent cross-binding)
# --------------------------------------------------------------------------- #
def _appended_result(intent: dict) -> dict:
    result = {
        "schema_version": "terminal_receipt_append_result_v1",
        "sink_id": "terminal_receipt_sink_v1",
        "intent_id": intent["intent_id"],
        "intent_digest": intent["intent_digest"],
        "append_status": "APPENDED",
        "record_locator": "records/" + "d" * 64 + ".record",
        "persisted_payload_digest": worm.terminal_payload_digest(_payload()),
        "idempotency_key": intent["idempotency_key"],
        "append_actor_id": intent["append_actor_id"],
        "immutable_after_write": True,
        "started_at": "2026-07-22T10:00:00Z",
        "completed_at": "2026-07-22T10:00:01Z",
        "evidence_expires_at": "2026-07-22T10:30:01Z",
        "failure_reason": None,
        "result_digest": "sha256:" + "0" * 64,
    }
    result["result_digest"] = worm.terminal_receipt_result_digest(result)
    return result


def test_committed_result_is_valid_and_cross_binds_to_intent() -> None:
    intent = _intent()
    result = _appended_result(intent)
    assert worm.validate_terminal_receipt_append_result(
        result, intent=intent, now="2026-07-22T10:00:05Z"
    ) == []
    assert validator.validate_aiml_artifact(result, now="2026-07-22T10:00:05Z") == []


def test_committed_result_cannot_carry_failure_reason() -> None:
    intent = _intent()
    result = _appended_result(intent)
    result["failure_reason"] = "should not be here"
    result["result_digest"] = worm.terminal_receipt_result_digest(result)
    errors = worm.validate_terminal_receipt_append_result(result, intent=intent, now="2026-07-22T10:00:05Z")
    assert any("cannot carry a failure_reason" in error for error in errors)


def test_interrupted_result_cannot_claim_a_record() -> None:
    intent = _intent()
    result = _appended_result(intent)
    result["append_status"] = "ROLLED_BACK_INTERRUPTED"
    result["result_digest"] = worm.terminal_receipt_result_digest(result)
    errors = worm.validate_terminal_receipt_append_result(result, intent=intent, now="2026-07-22T10:00:05Z")
    assert any("cannot claim a committed record_locator" in error for error in errors)
    assert any("requires a failure_reason" in error for error in errors)


def test_result_not_bound_to_intent_is_rejected() -> None:
    intent = _intent()
    result = _appended_result(intent)
    other = _intent(intent_id="intent-worm-999999")
    errors = worm.validate_terminal_receipt_append_result(result, intent=other, now="2026-07-22T10:00:05Z")
    assert any("is not bound to the intent" in error for error in errors)


def test_committed_result_persisted_digest_must_bind_approved_digest() -> None:
    # P1-B:committed result 的 persisted digest 與 intent 核准的 terminal_payload_digest 不符
    # ⇒ 綁定驗證拒絕(idempotency key 由核准 digest 派生,持久內容不得與其脫鉤)。
    intent = _intent()
    result = _appended_result(intent)
    result["persisted_payload_digest"] = "sha256:" + "e" * 64
    result["result_digest"] = worm.terminal_receipt_result_digest(result)
    errors = worm.validate_terminal_receipt_append_result(
        result, intent=intent, now="2026-07-22T10:00:05Z"
    )
    assert any(
        "persisted digest is not bound to the approved intent payload digest" in e
        for e in errors
    )


def test_committed_result_non_shape_record_locator_is_rejected() -> None:
    # P2-A:committed result 的 record_locator 必須是 records/<64hex>.record 形狀。
    intent = _intent()
    result = _appended_result(intent)
    result["record_locator"] = "../../etc/passwd"
    result["result_digest"] = worm.terminal_receipt_result_digest(result)
    errors = worm.validate_terminal_receipt_append_result(
        result, intent=intent, now="2026-07-22T10:00:05Z"
    )
    assert any("records/<64hex>.record locator" in e for e in errors)


# --------------------------------------------------------------------------- #
# readback ACK (independence + payload digest match)
# --------------------------------------------------------------------------- #
def _readback_ack(result: dict, *, verifier: str, ack: bool, same_actor: bool) -> dict:
    obj = {
        "schema_version": "terminal_receipt_readback_ack_v1",
        "sink_id": "terminal_receipt_sink_v1",
        "intent_id": result["intent_id"],
        "result_digest": result["result_digest"],
        "readback_verifier_id": verifier,
        "read_record_locator": result["record_locator"] if not same_actor else None,
        "readback_payload_digest": result["persisted_payload_digest"] if ack else None,
        "ack": ack,
        "same_actor_violation": same_actor,
        "observed_at": "2026-07-22T10:00:05Z",
        "expires_at": "2026-07-22T10:30:05Z",
        "ack_digest": "sha256:" + "0" * 64,
    }
    obj["ack_digest"] = worm.terminal_receipt_ack_digest(obj)
    return obj


def test_distinct_actor_positive_ack_is_valid_only_when_bound_to_result() -> None:
    intent = _intent()
    result = _appended_result(intent)
    ack = _readback_ack(result, verifier="independent-verifier", ack=True, same_actor=False)
    # 綁定配對 result 時,獨立正向 ACK 有效。
    assert worm.validate_terminal_receipt_readback_ack(
        ack, result=result, now="2026-07-22T10:00:06Z"
    ) == []
    # P1-A:同一 ACK 於中央閘 standalone(無配對 result)無法證明獨立性 → fail-closed。
    errors = validator.validate_aiml_artifact(ack, now="2026-07-22T10:00:06Z")
    assert errors == [
        "readback ack independence cannot be verified without its paired result"
    ]


def test_central_gate_rejects_forged_standalone_positive_ack() -> None:
    # P1-A 偽造攻擊:自選 verifier 字串、任意 read_record_locator、複製 readback_payload_digest、
    # ack=true、same_actor_violation=false,結構/新鮮度全綠 —— 中央閘仍必須拒絕(獨立性未證)。
    intent = _intent()
    result = _appended_result(intent)
    forged = {
        "schema_version": "terminal_receipt_readback_ack_v1",
        "sink_id": "terminal_receipt_sink_v1",
        "intent_id": result["intent_id"],
        "result_digest": result["result_digest"],
        "readback_verifier_id": "attacker-self-chosen-verifier",
        "read_record_locator": "records/" + "e" * 64 + ".record",
        "readback_payload_digest": result["persisted_payload_digest"],
        "ack": True,
        "same_actor_violation": False,
        "observed_at": "2026-07-22T10:00:05Z",
        "expires_at": "2026-07-22T10:30:05Z",
        "ack_digest": "sha256:" + "0" * 64,
    }
    forged["ack_digest"] = worm.terminal_receipt_ack_digest(forged)
    errors = validator.validate_aiml_artifact(forged, now="2026-07-22T10:00:06Z")
    assert "readback ack independence cannot be verified without its paired result" in (
        errors
    )


def test_readback_ack_with_wrong_read_locator_is_rejected() -> None:
    # read_record_locator 與 result.record_locator 不符 ⇒ 綁定驗證拒絕(聲稱讀了別的 record)。
    intent = _intent()
    result = _appended_result(intent)
    ack = _readback_ack(result, verifier="independent-verifier", ack=True, same_actor=False)
    ack["read_record_locator"] = "records/" + "f" * 64 + ".record"
    ack["ack_digest"] = worm.terminal_receipt_ack_digest(ack)
    errors = worm.validate_terminal_receipt_readback_ack(
        ack, result=result, now="2026-07-22T10:00:06Z"
    )
    assert any("read_record_locator is not bound to the result record" in e for e in errors)


def test_bound_append_actor_positive_ack_is_rejected_regardless_of_boolean() -> None:
    # 綁定的 append actor 等於 verifier,但 caller 把 same_actor_violation 偽設為 false:
    # 獨立性由綁定身分推導 ⇒ 正向 ACK 一律拒絕(不信任 caller 布林)。
    intent = _intent()
    result = _appended_result(intent)
    ack = _readback_ack(
        result, verifier=intent["append_actor_id"], ack=True, same_actor=False
    )
    errors = worm.validate_terminal_receipt_readback_ack(
        ack, result=result, now="2026-07-22T10:00:06Z"
    )
    assert any("must set same_actor_violation=true" in e for e in errors)
    assert any("cannot be issued by the bound append actor" in e for e in errors)


def test_same_actor_readback_must_refuse_to_ack() -> None:
    intent = _intent()
    result = _appended_result(intent)
    # append actor 讀自己的 record:必須 same_actor_violation=true 且 ack=false。
    ack = _readback_ack(result, verifier=intent["append_actor_id"], ack=False, same_actor=True)
    assert worm.validate_terminal_receipt_readback_ack(
        ack, result=result, now="2026-07-22T10:00:06Z"
    ) == []


def test_forged_same_actor_positive_ack_is_rejected() -> None:
    intent = _intent()
    result = _appended_result(intent)
    # append actor 佯稱獨立並 ack=true → 拒絕(same_actor_allowed=false)。
    ack = _readback_ack(result, verifier=intent["append_actor_id"], ack=True, same_actor=False)
    errors = worm.validate_terminal_receipt_readback_ack(
        ack, result=result, now="2026-07-22T10:00:06Z"
    )
    assert any("must set same_actor_violation=true" in error for error in errors)


def test_positive_ack_with_wrong_payload_digest_is_rejected() -> None:
    intent = _intent()
    result = _appended_result(intent)
    ack = _readback_ack(result, verifier="independent-verifier", ack=True, same_actor=False)
    ack["readback_payload_digest"] = "sha256:" + "c" * 64
    ack["ack_digest"] = worm.terminal_receipt_ack_digest(ack)
    errors = worm.validate_terminal_receipt_readback_ack(
        ack, result=result, now="2026-07-22T10:00:06Z"
    )
    assert any("does not match the persisted record" in error for error in errors)


# --------------------------------------------------------------------------- #
# central validator dispatch recognizes the three WORM schemas
# --------------------------------------------------------------------------- #
def test_central_validator_recognizes_all_worm_schemas() -> None:
    for schema_version in (
        "terminal_receipt_append_intent_v1",
        "terminal_receipt_append_result_v1",
        "terminal_receipt_readback_ack_v1",
        "aiml_component_effect_classification_v1",
        "pg_readonly_identity_receipt_v1",
    ):
        assert schema_version in validator.SCHEMA_FILES


def test_central_gate_mandates_now_for_worm_artifacts() -> None:
    # SHOULD-FIX 5:三個 WORM 分支與 pg_readonly 一樣強制 now(否則無從判斷新鮮度)。
    intent = _intent()
    result = _appended_result(intent)
    for artifact in (intent, result):
        errors = validator.validate_aiml_artifact(artifact)
        assert (
            "terminal receipt WORM artifact requires now for freshness at the central gate"
            in errors
        )


def test_central_gate_rejects_stale_worm_intent_and_result() -> None:
    # SHOULD-FIX 5:陳舊 intent/result 經中央閘 fail-closed。
    intent = _intent()
    result = _appended_result(intent)
    intent_errors = validator.validate_aiml_artifact(intent, now="2026-07-22T12:00:00Z")
    assert any("intent is not fresh" in e for e in intent_errors)
    result_errors = validator.validate_aiml_artifact(result, now="2026-07-22T12:00:00Z")
    assert any("evidence is not fresh" in e for e in result_errors)


# --------------------------------------------------------------------------- #
# S1.1 pg_readonly central wiring (CC review note D2)
# --------------------------------------------------------------------------- #
def _pg_readonly_pass_receipt(*, target_class: str = "disposable_local") -> dict:
    role = "aiml_ro"
    queries = [
        pg_readonly.build_query_record(
            "pg_role_attributes_v1", [[role, False, False, False, True, False, False]]
        ),
        pg_readonly.build_query_record(
            "pg_session_readonly_state_v1", [["on", "pg_catalog", role]]
        ),
        pg_readonly.build_query_record(
            "pg_server_version_v1", [["PostgreSQL 16.14"]]
        ),
    ]
    probe = pg_readonly.ProbeResult(
        role_name=role,
        role_attributes={
            "rolsuper": False, "rolcreaterole": False, "rolcreatedb": False,
            "rolcanlogin": True, "rolreplication": False, "rolbypassrls": False,
        },
        server_version="16.14",
        session_read_only="on",
        session_search_path="pg_catalog",
        ambient_routing_scrubbed=pg_readonly.ambient_routing_scrubbed_record({}),
        queries=queries,
        write_denied={
            "attempted": "CREATE TEMP TABLE t(x int)", "expected_denial": True,
            "observed_sqlstate": "25006", "verdict": "DENIED",
        },
        role_escalation_denied={
            "attempted": "SET ROLE writer", "expected_denial": True,
            "observed_sqlstate": "42501", "verdict": "DENIED",
        },
        search_path_pinned={
            "attempted": "ALTER ROLE current_user SET search_path TO public",
            "effective_search_path": "pg_catalog", "observed_sqlstate": "25006",
            "pinned": True, "verdict": "DENIED",
        },
    )
    return pg_readonly.build_pg_readonly_identity_receipt(
        caller="e1-central-wiring-test",
        platform={"os": "darwin", "arch": "arm64", "postgres_version": "16.14"},
        endpoint={
            "endpoint_class": "unix_socket_allowlisted", "socket_dir": "/tmp/sock",
            "loopback_host": None, "port": None,
        },
        database="postgres", role=role, target_class=target_class,
        probe_result=probe, observation_time=NOW, ttl_seconds=3600,
        evidence_class="LOCAL_REPRODUCIBLE",
    )


def test_central_validator_accepts_disposable_pass_pg_readonly_with_now() -> None:
    receipt = _pg_readonly_pass_receipt()
    assert validator.validate_aiml_artifact(
        receipt, now="2026-07-22T10:30:00Z"
    ) == []


def test_central_validator_mandates_now_for_pg_readonly() -> None:
    receipt = _pg_readonly_pass_receipt()
    errors = validator.validate_aiml_artifact(receipt)
    assert "pg_readonly identity receipt requires now for freshness at the central gate" in (
        errors
    )


def test_central_validator_rejects_stale_pg_readonly() -> None:
    receipt = _pg_readonly_pass_receipt()
    errors = validator.validate_aiml_artifact(receipt, now="2026-07-22T12:30:00Z")
    assert any("is not fresh" in error for error in errors)


def test_central_validator_rejects_handbuilt_wrong_source_binding() -> None:
    receipt = _pg_readonly_pass_receipt()
    receipt["source_sha256"] = "sha256:" + "0" * 64
    receipt["self_digest"] = pg_readonly.receipt_digest(receipt)
    errors = validator.validate_aiml_artifact(receipt, now="2026-07-22T10:30:00Z")
    assert any("source_sha256 does not bind this module" in error for error in errors)


def test_central_validator_rejects_production_target_pg_readonly() -> None:
    # production 目標即使結構完好也在 S1.1 gate fail-closed(disposable-only)。
    receipt = _pg_readonly_pass_receipt(target_class="production")
    errors = validator.validate_aiml_artifact(receipt, now="2026-07-22T10:30:00Z")
    assert any("target_class must be disposable_local" in error for error in errors)
