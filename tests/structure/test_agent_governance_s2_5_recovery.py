"""S2E.LW1 S2.5 recovery contract: identity-bound, consume-once, fail-closed."""

from __future__ import annotations

import copy
import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2_5_lifecycle as lifecycle  # noqa: E402
import agent_governance_s2_5_recovery as recovery  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402


NOW = "2026-07-30T12:00:00Z"
LATER = "2026-07-30T12:10:00Z"
HEAD = "a" * 40
D1 = "sha256:" + "1" * 64
D2 = "sha256:" + "2" * 64


def _sealed(payload: dict, digest_key: str) -> dict:
    sealed = copy.deepcopy(payload)
    sealed[digest_key] = validator.canonical_digest(payload)
    return sealed


def _reseal_capture(capture: dict) -> None:
    capture["capture_digest"] = validator.canonical_digest({
        key: value for key, value in capture.items() if key != "capture_digest"
    })


def _reseal_result(result: dict) -> None:
    result["result_digest"] = validator.canonical_digest({
        key: value for key, value in result.items()
        if key not in {"result_digest", "self_digest"}
    })
    result["self_digest"] = validator.artifact_self_digest(result)


def _reseal_postcheck(postcheck: dict) -> None:
    postcheck["postcheck_id"] = validator.canonical_digest({
        key: value for key, value in postcheck.items()
        if key not in {"postcheck_id", "self_digest"}
    })
    postcheck["self_digest"] = validator.artifact_self_digest(postcheck)


def _kernel_binding() -> dict:
    return _sealed({
        "schema_version": "s2_5_recovery_kernel_binding_v1",
        "source_head": HEAD,
        "host_identity": "host:trade-core",
        "node_identity": {
            "node_id": "s2-5-recovery-actor",
            "role": "OPS_APPLIER",
            "permission": "effect",
        },
        "process_identity": {"uid": 4100, "cgroup": "/system.slice/recovery.service"},
    }, "binding_digest")


def _capture(*, verifier: bool = False) -> dict:
    payload = {
        "schema_version": "s2_5_recovery_capture_v1",
        "source_head": HEAD,
        "host_identity": "host:trade-core",
        "node_identity": {
            "node_id": "s2-5-independent-postcheck" if verifier else "s2-5-recovery-actor",
            "role": "OPS_VERIFIER" if verifier else "OPS_APPLIER",
            "permission": "read_only" if verifier else "effect",
        },
        "process_identity": {
            "uid": 4200 if verifier else 4100,
            "cgroup": (
                "/system.slice/recovery-postcheck.service"
                if verifier else "/system.slice/recovery.service"
            ),
        },
        "observed_at": NOW,
    }
    return _sealed(payload, "capture_digest")


def _admission(unresolved: dict) -> dict:
    payload = {
        "schema_version": "s2_5_recovery_admission_v1",
        "task_digest": D1,
        "unresolved_state_digest": unresolved["unresolved_state_digest"],
        "state_root_identity": {
            "root_id": "state-root:s2-5",
            "root_digest": D2,
            "generation": 7,
            "previous_root_digest": D1,
        },
        "journal_set": {"journal_digests": [D1, D2], "head_digest": D2},
        "replay_ledger_head": {"entry_count": 3, "tail_digest": D1},
        "pre_state": {
            "active_state": "active",
            "unit_file_state": "enabled",
            "n_restarts": 1,
            "invocation_id": "inv-before",
        },
        "source_head": HEAD,
        "host_identity": "host:trade-core",
    }
    return _sealed(payload, "admission_digest")


def _authorization() -> dict:
    payload = {
        "authorization_id": "s2-5-recovery-auth-" + "3" * 64,
        "issued_at": NOW,
        "expires_at": LATER,
        "consume_once": True,
    }
    return _sealed(payload, "authorization_digest")


def _trusted_anchor() -> dict:
    payload = {
        "schema_version": "s2_5_recovery_trusted_anchor_ref_v1",
        "anchor_id": "trusted-anchor:s2-5:7",
        "anchor_digest": D1,
        "storage_class": "INDEPENDENT_OFF_STATE_ROOT",
        "anchor_scope_id": "off-root:host-governance",
        "bound_state_root_id": "state-root:s2-5",
        "source_head": HEAD,
        "host_identity": "host:trade-core",
    }
    return _sealed(payload, "reference_digest")


def _chain(state: lifecycle.S2_5RecoveryState):
    intent = recovery.build_recovery_intent(
        unresolved_state=state.unresolved,
        kernel_binding=_kernel_binding(),
        admission=_admission(state.unresolved),
        authorization=_authorization(),
        trusted_anchor=_trusted_anchor(),
        action="ROLLBACK_TO_PRE_STATE",
    )
    rollback = recovery.build_recovery_rollback(
        intent=intent,
        actor_capture=_capture(),
        post_state={
            "active_state": "active",
            "unit_file_state": "enabled",
            "n_restarts": 1,
            "invocation_id": "inv-before",
        },
        status="ROLLBACK_APPLIED",
    )
    result = recovery.build_recovery_result(
        intent=intent,
        actor_capture=_capture(),
        rollback=rollback,
        post_state=rollback["post_state"],
        status="RECOVERY_APPLIED",
    )
    postcheck = recovery.build_recovery_postcheck(
        intent=intent,
        result=result,
        verifier_capture=_capture(verifier=True),
        observed_state=result["post_state"],
        status="RECOVERY_CLEARED",
    )
    return intent, rollback, result, postcheck


def test_four_closed_schemas_are_dispatched_through_the_central_validator():
    state = lifecycle.S2_5RecoveryState()
    state.record(start_id="s2-5-" + "4" * 64, reasons=["rollback could not be proven"])
    artifacts = _chain(state)
    assert [item["schema_version"] for item in artifacts] == [
        "s2_5_recovery_intent_v1",
        "s2_5_recovery_rollback_v1",
        "s2_5_recovery_result_v1",
        "s2_5_recovery_postcheck_v1",
    ]
    for artifact in artifacts:
        assert validator.validate_aiml_artifact(artifact, now=NOW) == []
        extra = dict(artifact, raw_command="systemctl restart anything")
        assert validator.validate_aiml_artifact(extra, now=NOW)


def test_public_builders_never_accept_caller_identity_or_nonce_strings():
    for builder in (
        recovery.build_recovery_intent,
        recovery.build_recovery_rollback,
        recovery.build_recovery_result,
        recovery.build_recovery_postcheck,
    ):
        parameters = set(inspect.signature(builder).parameters)
        assert not parameters & {
            "actor", "actor_node_id", "verifier", "verifier_node_id", "nonce",
        }


@pytest.mark.parametrize(
    "mutation",
    [
        "renamed_actor",
        "same_role",
        "same_node",
        "same_process",
        "cross_step_capture",
        "source_head",
        "host",
        "state_root",
        "journal_head",
        "replayed_authorization",
    ],
)
def test_identity_transition_and_replay_mutations_fail_closed(mutation):
    state = lifecycle.S2_5RecoveryState()
    state.record(start_id="s2-5-" + "4" * 64, reasons=["not restored"])
    _intent, _rollback, result, postcheck = _chain(state)
    if mutation == "renamed_actor":
        result["actor_identity"]["node_id"] = "renamed"
        result["actor_capture"]["node_identity"]["node_id"] = "renamed"
        _reseal_capture(result["actor_capture"])
        result["actor_capture_digest"] = result["actor_capture"]["capture_digest"]
        _reseal_result(result)
        postcheck["recovery_result_digest"] = result["result_digest"]
        _reseal_postcheck(postcheck)
    elif mutation == "same_role":
        postcheck["verifier_identity"]["role"] = result["actor_identity"]["role"]
        postcheck["verifier_capture"]["node_identity"]["role"] = result["actor_identity"]["role"]
        _reseal_capture(postcheck["verifier_capture"])
        postcheck["verifier_capture_digest"] = postcheck["verifier_capture"]["capture_digest"]
        _reseal_postcheck(postcheck)
    elif mutation == "same_node":
        postcheck["verifier_identity"]["node_id"] = result["actor_identity"]["node_id"]
        postcheck["verifier_capture"]["node_identity"]["node_id"] = result[
            "actor_identity"
        ]["node_id"]
        _reseal_capture(postcheck["verifier_capture"])
        postcheck["verifier_capture_digest"] = postcheck["verifier_capture"]["capture_digest"]
        _reseal_postcheck(postcheck)
    elif mutation == "same_process":
        postcheck["verifier_process"] = copy.deepcopy(result["actor_process"])
        postcheck["verifier_capture"]["process_identity"] = copy.deepcopy(
            result["actor_process"]
        )
        _reseal_capture(postcheck["verifier_capture"])
        postcheck["verifier_capture_digest"] = postcheck["verifier_capture"]["capture_digest"]
        _reseal_postcheck(postcheck)
    elif mutation == "cross_step_capture":
        result["actor_capture_digest"] = D2
        _reseal_result(result)
        postcheck["recovery_result_digest"] = result["result_digest"]
        _reseal_postcheck(postcheck)
    elif mutation == "source_head":
        postcheck["recovery_binding"]["source_head"] = "b" * 40
        _reseal_postcheck(postcheck)
    elif mutation == "host":
        postcheck["recovery_binding"]["host_identity"] = "host:imposter"
        _reseal_postcheck(postcheck)
    elif mutation == "state_root":
        postcheck["recovery_binding"]["state_root_identity"]["generation"] = 8
        _reseal_postcheck(postcheck)
    elif mutation == "journal_head":
        postcheck["recovery_binding"]["journal_set"]["head_digest"] = D1
        _reseal_postcheck(postcheck)
    elif mutation == "replayed_authorization":
        state._consumed_authorization_ids.add(
            result["recovery_binding"]["authorization"]["authorization_id"]
        )
    with pytest.raises(ValueError):
        state.resolve(
            recovery_result=result,
            independent_postcheck=postcheck,
            now=NOW,
        )
    assert state.unresolved is not None


def test_stale_authorization_and_replaceable_anchor_are_rejected():
    state = lifecycle.S2_5RecoveryState()
    state.record(start_id="s2-5-" + "4" * 64, reasons=["not restored"])
    admission = _admission(state.unresolved)
    stale = _authorization()
    stale["expires_at"] = "2026-07-30T11:59:59Z"
    stale["authorization_digest"] = validator.canonical_digest({
        key: value for key, value in stale.items() if key != "authorization_digest"
    })
    with pytest.raises(ValueError):
        recovery.build_recovery_intent(
            unresolved_state=state.unresolved,
            kernel_binding=_kernel_binding(),
            admission=admission,
            authorization=stale,
            trusted_anchor=_trusted_anchor(),
            action="ROLLBACK_TO_PRE_STATE",
            now=NOW,
        )
    anchor = _trusted_anchor()
    anchor["anchor_scope_id"] = anchor["bound_state_root_id"]
    anchor["reference_digest"] = validator.canonical_digest({
        key: value for key, value in anchor.items() if key != "reference_digest"
    })
    with pytest.raises(ValueError):
        recovery.build_recovery_intent(
            unresolved_state=state.unresolved,
            kernel_binding=_kernel_binding(),
            admission=admission,
            authorization=_authorization(),
            trusted_anchor=anchor,
            action="ROLLBACK_TO_PRE_STATE",
        )


def test_only_validated_result_plus_independent_postcheck_can_clear_the_latch():
    state = lifecycle.S2_5RecoveryState()
    state.record(start_id="s2-5-" + "4" * 64, reasons=["not restored"])
    assert "resolution_note" not in inspect.signature(state.resolve).parameters
    _intent, _rollback, result, postcheck = _chain(state)
    resolved = state.resolve(
        recovery_result=result,
        independent_postcheck=postcheck,
        now=NOW,
    )
    assert resolved["unresolved_state_digest"]
    assert state.unresolved is None
    state.record(start_id="s2-5-" + "5" * 64, reasons=["second latch"])
    with pytest.raises(ValueError, match="consumed"):
        state.resolve(
            recovery_result=result,
            independent_postcheck=postcheck,
            now=NOW,
        )
    assert state.unresolved is not None
