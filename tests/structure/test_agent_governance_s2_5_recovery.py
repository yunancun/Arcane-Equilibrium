"""S2E.LW1 S2.5 recovery contract: identity-bound, consume-once, fail-closed."""

from __future__ import annotations

import ast
import copy
import inspect
import json
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
_RECOVERY_PRIVATE_KEY: Path | None = None
_ORIGINAL_RECOVERY_TRUST_LOADER = recovery._load_recovery_trust_root_public_key


@pytest.fixture(autouse=True)
def _install_independent_recovery_trust_root(tmp_path, monkeypatch):
    """Recovery uses a second key, never the S2.5 permit/attestor test key."""

    kit = __import__("s2_5_testkit")
    private_key, public_key, fingerprint = kit.mint_key(
        tmp_path, "s2-5-recovery-owner"
    )
    monkeypatch.setattr(
        recovery, "_load_recovery_trust_root_public_key", lambda: public_key
    )
    monkeypatch.setattr(recovery, "RECOVERY_TRUST_ROOT_FINGERPRINT", fingerprint)
    global _RECOVERY_PRIVATE_KEY
    _RECOVERY_PRIVATE_KEY = private_key
    yield
    _RECOVERY_PRIVATE_KEY = None


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
            "key_identity": "key:s2-5-recovery-actor",
        },
        "process_identity": {"uid": 4100, "cgroup": "/system.slice/recovery.service"},
    }, "binding_digest")


def _capture(
    *,
    intent: dict,
    observed_state: dict,
    result: dict | None = None,
    verifier: bool = False,
    observed_at: str = NOW,
) -> dict:
    assert _RECOVERY_PRIVATE_KEY is not None
    binding = intent["recovery_binding"]
    signed_binding = {
        "schema_version": "s2_5_recovery_capture_v1",
        "capture_kind": "INDEPENDENT_POSTCHECK" if verifier else "ACTOR_EFFECT",
        "source_head": HEAD,
        "host_identity": "host:trade-core",
        "bound_state_root_id": binding["state_root_identity"]["root_id"],
        "recovery_id": intent["recovery_id"],
        "recovery_intent_digest": intent["intent_digest"],
        "recovery_result_digest": result["result_digest"] if verifier else None,
        "observed_state": copy.deepcopy(observed_state),
        "observed_state_digest": validator.canonical_digest(observed_state),
        "node_identity": {
            "node_id": "s2-5-independent-postcheck" if verifier else "s2-5-recovery-actor",
            "role": "OPS_VERIFIER" if verifier else "OPS_APPLIER",
            "permission": "read_only" if verifier else "effect",
            "key_identity": (
                "key:s2-5-independent-postcheck"
                if verifier else "key:s2-5-recovery-actor"
            ),
        },
        "process_identity": {
            "uid": 4200 if verifier else 4100,
            "cgroup": (
                "/system.slice/recovery-postcheck.service"
                if verifier else "/system.slice/recovery.service"
            ),
        },
        "observed_at": observed_at,
    }
    signer_identity = (
        recovery.RECOVERY_VERIFIER_CAPTURE_SIGNER_IDENTITY
        if verifier else recovery.RECOVERY_ACTOR_CAPTURE_SIGNER_IDENTITY
    )
    namespace = (
        recovery.RECOVERY_VERIFIER_CAPTURE_SIGNATURE_NAMESPACE
        if verifier else recovery.RECOVERY_ACTOR_CAPTURE_SIGNATURE_NAMESPACE
    )
    payload = {
        **signed_binding,
        "signer_identity": signer_identity,
        "signer_fingerprint": recovery.RECOVERY_TRUST_ROOT_FINGERPRINT,
        "signature_namespace": namespace,
        "signed_binding": copy.deepcopy(signed_binding),
        "sshsig_armored": __import__("s2_5_testkit")._sign_bytes(
            _RECOVERY_PRIVATE_KEY,
            validator._canonical_bytes(signed_binding),
            namespace=namespace,
        ),
    }
    return _sealed(payload, "capture_digest")


def _admission(unresolved: dict) -> dict:
    payload = {
        "schema_version": "s2_5_recovery_admission_v1",
        "task_digest": D1,
        "unresolved_state_digest": unresolved["unresolved_state_digest"],
        "state_root_identity": copy.deepcopy(unresolved["state_root_identity"]),
        "journal_set": copy.deepcopy(unresolved["journal_set"]),
        "replay_ledger_head": copy.deepcopy(unresolved["replay_ledger_head"]),
        "pre_state": copy.deepcopy(unresolved["pre_state"]),
        "source_head": unresolved["source_head"],
        "host_identity": unresolved["host_identity"],
    }
    return _sealed(payload, "admission_digest")


def _authorization(
    unresolved: dict,
    *,
    action: str,
    kernel_binding: dict,
    admission: dict,
    trusted_anchor: dict,
) -> dict:
    assert _RECOVERY_PRIVATE_KEY is not None
    authorization_id = "s2-5-recovery-auth-" + "3" * 64
    signed_binding = {
        "action": action,
        "task_digest": admission["task_digest"],
        "unresolved_state_digest": unresolved["unresolved_state_digest"],
        "state_root_identity": copy.deepcopy(admission["state_root_identity"]),
        "journal_set": copy.deepcopy(admission["journal_set"]),
        "replay_ledger_head": copy.deepcopy(admission["replay_ledger_head"]),
        "pre_state": copy.deepcopy(admission["pre_state"]),
        "source_head": admission["source_head"],
        "host_identity": admission["host_identity"],
        "authorization_id": authorization_id,
        "issued_at": NOW,
        "expires_at": LATER,
        "trusted_anchor_digest": trusted_anchor["anchor_digest"],
        "actor_identity": copy.deepcopy(kernel_binding["node_identity"]),
        "actor_process": copy.deepcopy(kernel_binding["process_identity"]),
        "kernel_binding_digest": kernel_binding["binding_digest"],
        "admission_digest": admission["admission_digest"],
        "side_effect_class": unresolved["side_effect_class"],
        "production_effect": unresolved["production_effect"],
        "production_authority": unresolved["production_authority"],
        "target_class": unresolved["target_class"],
    }
    payload = {
        "schema_version": "s2_5_recovery_authorization_v1",
        "authorization_id": authorization_id,
        "issued_at": NOW,
        "expires_at": LATER,
        "consume_once": True,
        "signer_identity": recovery.RECOVERY_SIGNER_IDENTITY,
        "signer_fingerprint": recovery.RECOVERY_TRUST_ROOT_FINGERPRINT,
        "signature_namespace": recovery.RECOVERY_SIGNATURE_NAMESPACE,
        "signed_binding": signed_binding,
        "sshsig_armored": __import__("s2_5_testkit")._sign_bytes(
            _RECOVERY_PRIVATE_KEY,
            validator._canonical_bytes(signed_binding),
            namespace=recovery.RECOVERY_SIGNATURE_NAMESPACE,
        ),
    }
    return _sealed(payload, "authorization_digest")


def _trusted_anchor(unresolved: dict) -> dict:
    assert _RECOVERY_PRIVATE_KEY is not None
    append_entry_digest = validator.canonical_digest(unresolved)
    signed_binding = {
        "schema_version": "s2_5_recovery_trusted_anchor_ref_v1",
        "anchor_id": "trusted-anchor:s2-5:7",
        "storage_class": "INDEPENDENT_OFF_STATE_ROOT",
        "anchor_scope_id": "off-root:host-governance",
        "bound_state_root_id": unresolved["state_root_identity"]["root_id"],
        "source_head": HEAD,
        "host_identity": "host:trade-core",
        "external_sequence": 7,
        "previous_append_head_digest": D1,
        "append_entry_digest": append_entry_digest,
        "append_head_digest": validator.canonical_digest({
            "external_sequence": 7,
            "previous_append_head_digest": D1,
            "append_entry_digest": append_entry_digest,
        }),
        "append_only": True,
        "immutable_readback": True,
        "immutable_readback_digest": append_entry_digest,
        "append_actor_identity": "key:recovery-anchor-writer",
        "readback_verifier_identity": "key:recovery-anchor-reader",
        "evidence_class": "LOCAL_REPRODUCIBLE",
    }
    payload = {
        **signed_binding,
        "anchor_digest": validator.canonical_digest(signed_binding),
        "signer_identity": recovery.RECOVERY_ANCHOR_SIGNER_IDENTITY,
        "signer_fingerprint": recovery.RECOVERY_TRUST_ROOT_FINGERPRINT,
        "signature_namespace": recovery.RECOVERY_ANCHOR_SIGNATURE_NAMESPACE,
        "signed_binding": copy.deepcopy(signed_binding),
        "sshsig_armored": __import__("s2_5_testkit")._sign_bytes(
            _RECOVERY_PRIVATE_KEY,
            validator._canonical_bytes(signed_binding),
            namespace=recovery.RECOVERY_ANCHOR_SIGNATURE_NAMESPACE,
        ),
    }
    return _sealed(payload, "reference_digest")


def _consumption_proof(intent: dict, *, evidence_class: str = "LOCAL_REPRODUCIBLE"):
    assert _RECOVERY_PRIVATE_KEY is not None
    binding = intent["recovery_binding"]
    anchor = binding["trusted_anchor"]
    entry = validator.canonical_digest({
        "authorization_id": binding["authorization"]["authorization_id"],
        "recovery_id": intent["recovery_id"],
        "recovery_intent_digest": intent["intent_digest"],
        "bound_state_root_id": binding["state_root_identity"]["root_id"],
    })
    signed_binding = {
        "schema_version": "s2_5_recovery_authorization_consumption_v1",
        "authorization_id": binding["authorization"]["authorization_id"],
        "recovery_id": intent["recovery_id"],
        "recovery_intent_digest": intent["intent_digest"],
        "bound_state_root_id": binding["state_root_identity"]["root_id"],
        "external_sequence": anchor["external_sequence"] + 1,
        "previous_append_head_digest": anchor["append_head_digest"],
        "append_entry_digest": entry,
        "append_head_digest": validator.canonical_digest({
            "external_sequence": anchor["external_sequence"] + 1,
            "previous_append_head_digest": anchor["append_head_digest"],
            "append_entry_digest": entry,
        }),
        "append_only": True,
        "immutable_readback": True,
        "immutable_readback_digest": entry,
        "append_actor_identity": "key:recovery-consumption-writer",
        "readback_verifier_identity": "key:recovery-consumption-reader",
        "evidence_class": evidence_class,
    }
    proof = {
        **signed_binding,
        "signer_identity": recovery.RECOVERY_CONSUMPTION_SIGNER_IDENTITY,
        "signer_fingerprint": recovery.RECOVERY_TRUST_ROOT_FINGERPRINT,
        "signature_namespace": recovery.RECOVERY_CONSUMPTION_SIGNATURE_NAMESPACE,
        "signed_binding": copy.deepcopy(signed_binding),
        "sshsig_armored": __import__("s2_5_testkit")._sign_bytes(
            _RECOVERY_PRIVATE_KEY,
            validator._canonical_bytes(signed_binding),
            namespace=recovery.RECOVERY_CONSUMPTION_SIGNATURE_NAMESPACE,
        ),
    }
    return _sealed(proof, "proof_digest")


def _record_state(state: lifecycle.S2_5RecoveryState, *, start: str = "4") -> None:
    state.record(
        start_id="s2-5-" + start * 64,
        reasons=["rollback could not be proven"],
        task_digest=D1,
        journal_set={"journal_digests": [D1, D2], "head_digest": D2},
        replay_ledger_head={"entry_count": 3, "tail_digest": D1},
        pre_state={
            "active_state": "active",
            "unit_file_state": "enabled",
            "n_restarts": 1,
            "invocation_id": "inv-before",
        },
        source_head=HEAD,
        root_digest=D2,
    )


def _state(tmp_path: Path) -> lifecycle.S2_5RecoveryState:
    state = lifecycle.S2_5RecoveryState(
        state_root=tmp_path / "state",
        host_identity="host:trade-core",
    )
    _record_state(state)
    return state


def _chain(state: lifecycle.S2_5RecoveryState):
    kernel = _kernel_binding()
    admission = _admission(state.unresolved)
    anchor = _trusted_anchor(state.unresolved)
    intent = recovery.build_recovery_intent(
        unresolved_state=state.unresolved,
        kernel_binding=kernel,
        admission=admission,
        authorization=_authorization(
            state.unresolved,
            action="ROLLBACK_TO_PRE_STATE",
            kernel_binding=kernel,
            admission=admission,
            trusted_anchor=anchor,
        ),
        trusted_anchor=anchor,
        action="ROLLBACK_TO_PRE_STATE",
        now=NOW,
    )
    post_state = copy.deepcopy(intent["recovery_binding"]["pre_state"])
    actor_capture = _capture(intent=intent, observed_state=post_state)
    rollback = recovery.build_recovery_rollback(
        intent=intent,
        actor_capture=actor_capture,
        post_state=post_state,
        status="LATCH_PRESERVED",
    )
    result = recovery.build_recovery_result(
        intent=intent,
        actor_capture=actor_capture,
        rollback=rollback,
        post_state=rollback["post_state"],
        status="RECOVERY_ABORTED",
        authorization_consumption_proof=_consumption_proof(intent),
    )
    postcheck = recovery.build_recovery_postcheck(
        intent=intent,
        result=result,
        verifier_capture=_capture(
            intent=intent,
            result=result,
            observed_state=result["post_state"],
            verifier=True,
        ),
        observed_state=result["post_state"],
        status="RECOVERY_UNRESOLVED",
    )
    return intent, rollback, result, postcheck


def _intent_materials(
    state: lifecycle.S2_5RecoveryState,
    action: str = "ROLLBACK_TO_PRE_STATE",
) -> tuple[dict, dict, dict, dict]:
    kernel = _kernel_binding()
    admission = _admission(state.unresolved)
    anchor = _trusted_anchor(state.unresolved)
    authorization = _authorization(
        state.unresolved,
        action=action,
        kernel_binding=kernel,
        admission=admission,
        trusted_anchor=anchor,
    )
    return kernel, admission, anchor, authorization


def test_four_closed_schemas_are_dispatched_through_the_central_validator(tmp_path):
    state = _state(tmp_path)
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


def test_lifecycle_requires_one_state_root_bound_controller_before_any_other_gate(
    tmp_path, monkeypatch
):
    parameter = inspect.signature(lifecycle.apply_s2_5_start).parameters[
        "recovery_state"
    ]
    assert parameter.default is inspect.Parameter.empty
    _key, intent, permit, unit = __import__("s2_5_testkit").a_side_setup(
        tmp_path, monkeypatch
    )
    kit = __import__("s2_5_testkit")
    state_root = tmp_path / "state"
    kwargs = kit.apply_kwargs(tmp_path=tmp_path, unit=unit, state_root=state_root)
    assert kwargs["recovery_state"] is kit.apply_kwargs(
        tmp_path=tmp_path, unit=unit, state_root=state_root
    )["recovery_state"]
    verdict = lifecycle.apply_s2_5_start(
        intent,
        permit,
        unit,
        **{**kwargs, "recovery_state": None, "now": object()},
    )
    assert verdict["status"] == lifecycle.S2_5_STATUS_RECOVERY_REQUIRED
    assert unit.calls == []


def test_a_fresh_controller_cannot_replace_the_registered_controller_for_one_root(
    tmp_path, monkeypatch
):
    kit = __import__("s2_5_testkit")
    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    state_root = tmp_path / "state"
    shared = lifecycle.S2_5RecoveryState(
        state_root=state_root,
        host_identity="host:disposable-systemd:test",
    )
    first = lifecycle.apply_s2_5_start(
        intent,
        permit,
        None,
        **kit.apply_kwargs(
            tmp_path=tmp_path,
            unit=unit,
            state_root=state_root,
            recovery_state=shared,
        ),
    )
    assert first["status"] == lifecycle.S2_5_STATUS_PENDING
    substituted = lifecycle.S2_5RecoveryState(
        state_root=state_root,
        host_identity="host:disposable-systemd:test",
    )
    second = lifecycle.apply_s2_5_start(
        intent,
        permit,
        unit,
        **kit.apply_kwargs(
            tmp_path=tmp_path,
            unit=unit,
            state_root=state_root,
            recovery_state=substituted,
        ),
    )
    assert second["status"] == lifecycle.S2_5_STATUS_RECOVERY_REQUIRED
    assert unit.calls == []


def test_record_is_sticky_and_captures_failure_time_state_instead_of_posthoc_admission(
    tmp_path,
):
    state_root = tmp_path / "state"
    state = lifecycle.S2_5RecoveryState(
        state_root=state_root,
        host_identity="host:disposable-systemd:test",
    )
    failure = {
        "task_digest": D1,
        "root_digest": D2,
        "journal_set": {"journal_digests": [D1, D2], "head_digest": D2},
        "replay_ledger_head": {"entry_count": 3, "tail_digest": D1},
        "pre_state": {
            "active_state": "active",
            "unit_file_state": "enabled",
            "n_restarts": 1,
            "invocation_id": "inv-before",
        },
        "source_head": HEAD,
    }
    state.record(
        start_id="s2-5-" + "4" * 64,
        reasons=["rollback could not be proven"],
        **failure,
    )
    captured = copy.deepcopy(state.unresolved)
    assert captured["state_root_identity"]["generation"] == 1
    assert captured["state_root_identity"]["root_digest"] == D2
    assert captured["state_root_identity"]["previous_root_digest"].startswith("sha256:")
    assert captured["journal_set"] == failure["journal_set"]
    assert captured["replay_ledger_head"] == failure["replay_ledger_head"]
    assert captured["pre_state"] == failure["pre_state"]
    assert captured["source_head"] == HEAD
    assert captured["host_identity"] == "host:disposable-systemd:test"
    assert captured["side_effect_class"] == "DISPOSABLE_TEST"
    assert captured["production_effect"] is False
    assert captured["production_authority"] is False
    assert captured["target_class"] == "disposable_systemd"
    with pytest.raises(ValueError, match="unresolved"):
        state.record(
            start_id="s2-5-" + "5" * 64,
            reasons=["must not overwrite"],
            **failure,
        )
    assert state.unresolved == captured


@pytest.mark.parametrize(
    "mutation",
    [
        "renamed_actor",
        "same_role",
        "same_node",
        "same_process",
        "same_uid",
        "same_cgroup",
        "same_key_identity",
        "cross_step_capture",
        "source_head",
        "host",
        "state_root",
        "journal_head",
        "replayed_authorization",
    ],
)
def test_identity_transition_and_replay_mutations_fail_closed(mutation, tmp_path):
    state = _state(tmp_path)
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
    elif mutation == "same_uid":
        postcheck["verifier_process"]["uid"] = result["actor_process"]["uid"]
        postcheck["verifier_capture"]["process_identity"]["uid"] = result[
            "actor_process"
        ]["uid"]
        _reseal_capture(postcheck["verifier_capture"])
        postcheck["verifier_capture_digest"] = postcheck["verifier_capture"]["capture_digest"]
        _reseal_postcheck(postcheck)
    elif mutation == "same_cgroup":
        postcheck["verifier_process"]["cgroup"] = result["actor_process"]["cgroup"]
        postcheck["verifier_capture"]["process_identity"]["cgroup"] = result[
            "actor_process"
        ]["cgroup"]
        _reseal_capture(postcheck["verifier_capture"])
        postcheck["verifier_capture_digest"] = postcheck["verifier_capture"]["capture_digest"]
        _reseal_postcheck(postcheck)
    elif mutation == "same_key_identity":
        postcheck["verifier_identity"]["key_identity"] = result["actor_identity"][
            "key_identity"
        ]
        postcheck["verifier_capture"]["node_identity"]["key_identity"] = result[
            "actor_identity"
        ]["key_identity"]
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


def test_stale_authorization_and_replaceable_anchor_are_rejected(tmp_path):
    state = _state(tmp_path)
    kernel, admission, trusted_anchor, stale = _intent_materials(state)
    stale["expires_at"] = "2026-07-30T11:59:59Z"
    stale["authorization_digest"] = validator.canonical_digest({
        key: value for key, value in stale.items() if key != "authorization_digest"
    })
    with pytest.raises(ValueError):
        recovery.build_recovery_intent(
            unresolved_state=state.unresolved,
            kernel_binding=kernel,
            admission=admission,
            authorization=stale,
            trusted_anchor=trusted_anchor,
            action="ROLLBACK_TO_PRE_STATE",
            now=NOW,
        )
    anchor = _trusted_anchor(state.unresolved)
    anchor["anchor_scope_id"] = anchor["bound_state_root_id"]
    anchor["reference_digest"] = validator.canonical_digest({
        key: value for key, value in anchor.items() if key != "reference_digest"
    })
    with pytest.raises(ValueError):
        recovery.build_recovery_intent(
            unresolved_state=state.unresolved,
            kernel_binding=kernel,
            admission=admission,
            authorization=_authorization(
                state.unresolved,
                action="ROLLBACK_TO_PRE_STATE",
                kernel_binding=kernel,
                admission=admission,
                trusted_anchor=anchor,
            ),
            trusted_anchor=anchor,
            action="ROLLBACK_TO_PRE_STATE",
            now=NOW,
        )


def test_canonical_hash_only_authority_and_anchor_can_never_clear_recovery(tmp_path):
    """Self-digests are integrity only; the old hash-only pair must stay pending."""

    state = _state(tmp_path)
    old_authorization = _sealed({
        "authorization_id": "s2-5-recovery-auth-" + "3" * 64,
        "issued_at": NOW,
        "expires_at": LATER,
        "consume_once": True,
    }, "authorization_digest")
    old_anchor = _sealed({
        "schema_version": "s2_5_recovery_trusted_anchor_ref_v1",
        "anchor_id": "trusted-anchor:s2-5:7",
        "anchor_digest": D1,
        "storage_class": "INDEPENDENT_OFF_STATE_ROOT",
        "anchor_scope_id": "off-root:host-governance",
        "bound_state_root_id": state.unresolved["state_root_identity"]["root_id"],
        "source_head": HEAD,
        "host_identity": "host:trade-core",
    }, "reference_digest")
    with pytest.raises(ValueError, match="SSHSIG|authenticated|anchor"):
        recovery.build_recovery_intent(
            unresolved_state=state.unresolved,
            kernel_binding=_kernel_binding(),
            admission=_admission(state.unresolved),
            authorization=old_authorization,
            trusted_anchor=old_anchor,
            action="ROLLBACK_TO_PRE_STATE",
            now=NOW,
        )
    assert state.unresolved is not None


def test_source_only_chain_can_never_clear_the_latch(tmp_path):
    state = _state(tmp_path)
    assert "resolution_note" not in inspect.signature(state.resolve).parameters
    _intent, _rollback, result, postcheck = _chain(state)
    with pytest.raises(ValueError, match="RECOVERY_APPLIED|source-only"):
        state.resolve(
            recovery_result=result,
            independent_postcheck=postcheck,
            now=NOW,
        )
    assert state.unresolved is not None


def test_dedicated_recovery_root_has_no_caller_selected_path_or_shared_key():
    import agent_governance_s2_5_attestation as attestation

    assert recovery.RECOVERY_TRUST_ROOT_PUBLIC_KEY_PATH.is_absolute()
    assert recovery.RECOVERY_TRUST_ROOT_FINGERPRINT != (
        attestation.S2_5_TRUST_ROOT_FINGERPRINT
    )
    assert set(inspect.signature(
        recovery._load_recovery_trust_root_public_key
    ).parameters) == set()
    assert not hasattr(recovery, "RECOVERY_TRUST_ROOT_PUBLIC_KEY")


def test_recovery_trust_root_rejects_writable_or_multiply_linked_key(
    tmp_path, monkeypatch
):
    public_key = __import__("s2_5_testkit").mint_key(
        tmp_path, "loader-check"
    )[1]
    key_path = tmp_path / "recovery-owner.pub"
    key_path.write_text(public_key + "\n", encoding="ascii")
    monkeypatch.setattr(recovery, "RECOVERY_TRUST_ROOT_PUBLIC_KEY_PATH", key_path)
    key_path.chmod(0o666)
    with pytest.raises(ValueError, match="writable"):
        _ORIGINAL_RECOVERY_TRUST_LOADER()
    key_path.chmod(0o600)
    (tmp_path / "second-link.pub").hardlink_to(key_path)
    with pytest.raises(ValueError, match="hard link"):
        _ORIGINAL_RECOVERY_TRUST_LOADER()


def test_intent_requires_explicit_time_and_resolve_uses_closed_central_schema(tmp_path):
    assert inspect.signature(recovery.build_recovery_intent).parameters[
        "now"
    ].default is inspect.Parameter.empty
    state = _state(tmp_path)
    _intent, _rollback, result, postcheck = _chain(state)
    result["unexpected_root_field"] = "must be rejected by the closed schema"
    _reseal_result(result)
    with pytest.raises(ValueError):
        state.resolve(
            recovery_result=result,
            independent_postcheck=postcheck,
            now=NOW,
        )
    assert state.unresolved is not None


def test_signed_capture_timestamp_must_be_fresh_at_central_validation(tmp_path):
    state = _state(tmp_path)
    kernel, admission, anchor, authorization = _intent_materials(state)
    intent = recovery.build_recovery_intent(
        unresolved_state=state.unresolved,
        kernel_binding=kernel,
        admission=admission,
        authorization=authorization,
        trusted_anchor=anchor,
        action="ROLLBACK_TO_PRE_STATE",
        now=NOW,
    )
    post_state = copy.deepcopy(intent["recovery_binding"]["pre_state"])
    future_capture = _capture(
        intent=intent,
        observed_state=post_state,
        observed_at="2026-07-30T12:09:00Z",
    )
    rollback = recovery.build_recovery_rollback(
        intent=intent,
        actor_capture=future_capture,
        post_state=post_state,
        status="LATCH_PRESERVED",
    )
    assert any(
        "future" in error or "authorization window" in error
        for error in validator.validate_aiml_artifact(rollback, now=NOW)
    )


def test_recovery_schemas_are_resources_but_not_runtime_import_roots():
    closure = json.loads(
        (ML_ROOT / "application_bundle_runtime_closure_v1.json").read_text()
    )
    expected_resources = {
        "program_code/ml_training/schemas/aiml_gate_receipts/"
        f"s2_5_recovery_{kind}_v1.schema.json"
        for kind in ("intent", "postcheck", "result", "rollback")
    }
    assert expected_resources <= set(closure["schema_resources"])
    assert not any(
        path.endswith("agent_governance_s2_5_recovery.py")
        for path in closure["python_modules"]
    )
    assert not any(
        entry["module"] == "agent_governance_s2_5_recovery"
        for entry in closure["runtime_lazy_helper_roots"]
    )
    consumer_path = ML_ROOT / "alr_event_consumer.py"
    tree = ast.parse(consumer_path.read_text())
    callers = {
        node.name: ast.get_source_segment(consumer_path.read_text(), node) or ""
        for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        if any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "validate_aiml_artifact"
            for child in ast.walk(node)
        )
    }
    assert set(callers) == {
        "_load_expected_compatibility_manifest",
        "resolve_pinned_learning_runtime_digest",
    }
    assert "source_compatibility_receipt_v1" in callers[
        "_load_expected_compatibility_manifest"
    ]
    assert "source_compatibility_receipt_v2" in callers[
        "resolve_pinned_learning_runtime_digest"
    ]


def test_literal_consumed_boolean_and_nested_open_objects_are_rejected(tmp_path):
    state = _state(tmp_path)
    intent, rollback, result, postcheck = _chain(state)
    literal = copy.deepcopy(result)
    literal.pop("authorization_consumption_proof")
    literal["authorization_consumed"] = True
    _reseal_result(literal)
    assert validator.validate_aiml_artifact(literal, now=NOW)

    mutations = [
        (copy.deepcopy(intent), ("recovery_binding", "authorization")),
        (copy.deepcopy(rollback), ("actor_capture",)),
        (copy.deepcopy(result), ("recovery_intent",)),
        (copy.deepcopy(postcheck), ("verifier_capture",)),
    ]
    for artifact, path in mutations:
        target = artifact
        for key in path:
            target = target[key]
        target["unexpected_nested_field"] = "must fail closed"
        assert validator.validate_aiml_artifact(artifact, now=NOW)


def test_capture_signature_action_semantics_and_secret_values_fail_closed(tmp_path):
    state = _state(tmp_path)
    intent, rollback, _result, _postcheck = _chain(state)
    tampered = copy.deepcopy(rollback)
    tampered["actor_capture"]["observed_at"] = LATER
    tampered["actor_capture"]["signed_binding"]["observed_at"] = LATER
    _reseal_capture(tampered["actor_capture"])
    tampered["actor_capture_digest"] = tampered["actor_capture"]["capture_digest"]
    tampered["self_digest"] = validator.artifact_self_digest(tampered)
    assert any(
        "SSHSIG" in error
        for error in recovery.validate_recovery_artifact(tampered, now=NOW)
    )
    assert recovery._sensitive_key_hits({
        "innocent_label": "Bearer abcdefghijklmnopqrstuvwxyz"
    })

    for action in ("REPLAY_JOURNAL", "ABORT_AND_PRESERVE_LATCH"):
        action_state = _state(tmp_path / action.lower())
        kernel, admission, anchor, authorization = _intent_materials(
            action_state, action
        )
        action_intent = recovery.build_recovery_intent(
            unresolved_state=action_state.unresolved,
            kernel_binding=kernel,
            admission=admission,
            authorization=authorization,
            trusted_anchor=anchor,
            action=action,
            now=NOW,
        )
        post_state = copy.deepcopy(action_intent["recovery_binding"]["pre_state"])
        actor_capture = _capture(
            intent=action_intent, observed_state=post_state
        )
        with pytest.raises(ValueError, match="predicate|preserve"):
            recovery.build_recovery_rollback(
                intent=action_intent,
                actor_capture=actor_capture,
                post_state=post_state,
                status="ROLLBACK_APPLIED",
            )

    with pytest.raises(ValueError, match="explicit.*current time"):
        state.resolve(
            recovery_result=_result,
            independent_postcheck=_postcheck,
            now=None,
        )
    assert state.unresolved is not None
