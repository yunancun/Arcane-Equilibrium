"""S2E.LW1 S2.5 recovery contract: identity-bound, consume-once, fail-closed."""

from __future__ import annotations

import ast
import copy
import inspect
import json
import sys
from datetime import datetime
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
import agent_governance_s2_5_recovery_readback as readback_adapter  # noqa: E402
import aiml_gate_receipt_s2_5_host_capture as host_capture_leaf  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402


NOW = "2026-07-30T12:00:00Z"
LATER = "2026-07-30T12:10:00Z"
HEAD = "a" * 40
D1 = "sha256:" + "1" * 64
D2 = "sha256:" + "2" * 64
_RECOVERY_PRIVATE_KEYS: dict[str, Path] = {}
_RECOVERY_FINGERPRINTS: dict[str, str] = {}
_CURRENT_ANCHOR_READBACK: dict = {}
_ORIGINAL_RECOVERY_PUBLIC_KEY_READER = recovery._read_fixed_recovery_public_key


def _fixed_loader(public_key: str):
    def load() -> str:
        return public_key

    return load


@pytest.fixture(autouse=True)
def _install_independent_recovery_trust_root(tmp_path, monkeypatch):
    """Install six independent disposable keys at the fixed loader seams."""

    kit = __import__("s2_5_testkit")
    profiles = (
        "authorization", "anchor", "anchor_readback", "consumption",
        "actor_capture", "verifier_capture",
    )
    for profile in profiles:
        private_key, public_key, fingerprint = kit.mint_key(
            tmp_path, "s2-5-recovery-" + profile.replace("_", "-")
        )
        monkeypatch.setattr(
            recovery,
            f"_load_recovery_{profile}_trust_root_public_key",
            _fixed_loader(public_key),
        )
        monkeypatch.setattr(
            recovery,
            f"RECOVERY_{profile.upper()}_TRUST_ROOT_FINGERPRINT",
            fingerprint,
        )
        _RECOVERY_PRIVATE_KEYS[profile] = private_key
        _RECOVERY_FINGERPRINTS[profile] = fingerprint
    private_key, public_key, fingerprint = kit.mint_key(
        tmp_path, "s2-5-recovery-host-capture"
    )
    monkeypatch.setattr(
        host_capture_leaf,
        "_load_recovery_host_capture_trust_root_public_key",
        _fixed_loader(public_key),
    )
    monkeypatch.setattr(
        host_capture_leaf,
        "RECOVERY_HOST_CAPTURE_TRUST_ROOT_FINGERPRINT",
        fingerprint,
    )
    _RECOVERY_PRIVATE_KEYS["host_capture"] = private_key
    _RECOVERY_FINGERPRINTS["host_capture"] = fingerprint
    nonce_counter = [0]

    def fresh_nonce() -> str:
        nonce_counter[0] += 1
        return "s2-5-readback-challenge-" + f"{nonce_counter[0]:064x}"

    monkeypatch.setattr(
        readback_adapter,
        "_trusted_now",
        lambda: datetime.fromisoformat(NOW.replace("Z", "+00:00")),
    )
    monkeypatch.setattr(
        readback_adapter,
        "_fresh_challenge_nonce",
        fresh_nonce,
    )
    monkeypatch.setattr(
        readback_adapter,
        "_fixed_transport_exchange",
        _fresh_current_readback_response,
    )
    yield
    _RECOVERY_PRIVATE_KEYS.clear()
    _RECOVERY_FINGERPRINTS.clear()
    _CURRENT_ANCHOR_READBACK.clear()


def _sealed(payload: dict, digest_key: str) -> dict:
    sealed = copy.deepcopy(payload)
    sealed[digest_key] = validator.canonical_digest(payload)
    return sealed


def _fresh_current_readback_response(request_bytes: bytes) -> dict:
    request = json.loads(request_bytes)
    current = _CURRENT_ANCHOR_READBACK
    signed_binding = {
        "schema_version": (
            "s2_5_recovery_anchor_current_readback_response_v1"
        ),
        "adapter_id": readback_adapter.ADAPTER_ID,
        "store_id": current["store_id"],
        "anchor_scope_id": current["anchor_scope_id"],
        "query_digest": request["self_digest"],
        "challenge_nonce": request["challenge_nonce"],
        **{
            field: copy.deepcopy(current[field])
            for field in recovery._ANCHOR_READBACK_STATE_FIELDS
            if field not in {"store_id", "anchor_scope_id"}
        },
        "observed_at": NOW,
        "expires_at": request["expires_at"],
    }
    return _sealed({
        **signed_binding,
        "signer_identity": recovery.RECOVERY_ANCHOR_READBACK_SIGNER_IDENTITY,
        "signer_fingerprint": _RECOVERY_FINGERPRINTS["anchor_readback"],
        "signature_namespace": (
            recovery.RECOVERY_ANCHOR_READBACK_SIGNATURE_NAMESPACE
        ),
        "signed_binding": copy.deepcopy(signed_binding),
        "sshsig_armored": __import__("s2_5_testkit")._sign_bytes(
            _RECOVERY_PRIVATE_KEYS["anchor_readback"],
            validator._canonical_bytes(signed_binding),
            namespace=recovery.RECOVERY_ANCHOR_READBACK_SIGNATURE_NAMESPACE,
        ),
    }, "readback_digest")


def _reseal_capture(capture: dict) -> None:
    capture["capture_digest"] = validator.canonical_digest({
        key: value for key, value in capture.items() if key != "capture_digest"
    })


def _reseal_rollback(rollback: dict) -> None:
    rollback["rollback_result_digest"] = validator.canonical_digest({
        "rollback_intent_digest": rollback["rollback_intent_digest"],
        "post_state": rollback["post_state"],
        "status": rollback["status"],
        "actor_capture_digest": rollback["actor_capture_digest"],
    })
    rollback["self_digest"] = validator.artifact_self_digest(rollback)


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


def _replace_signature_with_profile(artifact: dict, profile: str) -> None:
    artifact["sshsig_armored"] = __import__("s2_5_testkit")._sign_bytes(
        _RECOVERY_PRIVATE_KEYS[profile],
        validator._canonical_bytes(artifact["signed_binding"]),
        namespace=artifact["signature_namespace"],
    )


def _resign_anchor(anchor: dict) -> None:
    anchor["signed_binding"] = {
        key: copy.deepcopy(anchor[key])
        for key in recovery._ANCHOR_SIGNED_BINDING_KEYS
    }
    anchor["anchor_digest"] = validator.canonical_digest(
        anchor["signed_binding"]
    )
    _replace_signature_with_profile(anchor, "anchor")
    anchor["reference_digest"] = validator.canonical_digest({
        key: value for key, value in anchor.items()
        if key != "reference_digest"
    })


def _resign_current_readback(
    readback: dict,
    *,
    profile: str = "anchor_readback",
) -> None:
    readback["signed_binding"] = {
        key: copy.deepcopy(readback[key])
        for key in recovery._CURRENT_ANCHOR_READBACK_SIGNED_BINDING_KEYS
    }
    readback["signer_fingerprint"] = _RECOVERY_FINGERPRINTS[profile]
    readback["sshsig_armored"] = __import__("s2_5_testkit")._sign_bytes(
        _RECOVERY_PRIVATE_KEYS[profile],
        validator._canonical_bytes(readback["signed_binding"]),
        namespace=recovery.RECOVERY_ANCHOR_READBACK_SIGNATURE_NAMESPACE,
    )
    readback["readback_digest"] = validator.canonical_digest({
        key: value for key, value in readback.items()
        if key != "readback_digest"
    })


def _host_capture(state_root: Path, *, source_head: str = HEAD) -> dict:
    signed = {
        "schema_version": host_capture_leaf.HOST_CAPTURE_SCHEMA_VERSION,
        "capture_profile": host_capture_leaf.HOST_CAPTURE_PROFILE,
        "source_head": source_head,
        "stable_host_facts": {
            "machine_id_digest": "sha256:" + "8" * 64,
            "node_name": "trade-core",
            "os_id": "linux",
            "architecture": "x86_64",
        },
        "host_identity": "",
        "node_identity": {
            "node_id": "s2-5-host-attestor",
            "role": "HOST_ATTESTOR",
            "permission": "read_only",
            "key_identity": "key:s2-5-host-attestor",
        },
        "process_identity": {
            "uid": 4300,
            "cgroup": "/system.slice/s2-5-host-capture.service",
        },
        "boot_manager_facts": {
            "boot_id": "boot-disposable-1",
            "manager": "systemd",
            "manager_root": "/run/systemd/system",
            "unit_name": lifecycle.S2_5_UNIT_NAME,
            "canonical_state_root": str(state_root.resolve(strict=False)),
        },
        "observed_at": NOW,
        "expires_at": LATER,
        "side_effect_class": "DISPOSABLE_TEST",
        "production_effect": False,
        "production_authority": False,
        "target_class": "disposable_systemd",
    }
    signed["host_identity"] = (
        host_capture_leaf.derive_s2_5_recovery_host_identity(signed)
    )
    payload = {
        **signed,
        "signer_identity": (
            host_capture_leaf.RECOVERY_HOST_CAPTURE_SIGNER_IDENTITY
        ),
        "signer_fingerprint": _RECOVERY_FINGERPRINTS["host_capture"],
        "signature_namespace": (
            host_capture_leaf.RECOVERY_HOST_CAPTURE_SIGNATURE_NAMESPACE
        ),
        "signed_binding": copy.deepcopy(signed),
        "sshsig_armored": __import__("s2_5_testkit")._sign_bytes(
            _RECOVERY_PRIVATE_KEYS["host_capture"],
            validator._canonical_bytes(signed),
            namespace=host_capture_leaf.RECOVERY_HOST_CAPTURE_SIGNATURE_NAMESPACE,
        ),
    }
    payload["self_digest"] = validator.artifact_self_digest(payload)
    return payload


def _kernel_binding(unresolved: dict) -> dict:
    return _sealed({
        "schema_version": "s2_5_recovery_kernel_binding_v1",
        "source_head": unresolved["source_head"],
        "host_identity": unresolved["host_identity"],
        "host_capture_digest": unresolved["host_capture_digest"],
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
    profile = "verifier_capture" if verifier else "actor_capture"
    private_key = _RECOVERY_PRIVATE_KEYS[profile]
    binding = intent["recovery_binding"]
    signed_binding = {
        "schema_version": "s2_5_recovery_capture_v1",
        "capture_kind": "INDEPENDENT_POSTCHECK" if verifier else "ACTOR_EFFECT",
        "source_head": binding["source_head"],
        "host_identity": binding["host_identity"],
        "host_capture_digest": binding["host_capture_digest"],
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
        "signer_fingerprint": _RECOVERY_FINGERPRINTS[profile],
        "signature_namespace": namespace,
        "signed_binding": copy.deepcopy(signed_binding),
        "sshsig_armored": __import__("s2_5_testkit")._sign_bytes(
            private_key,
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
        "host_capture_digest": unresolved["host_capture_digest"],
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
    private_key = _RECOVERY_PRIVATE_KEYS["authorization"]
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
        "host_capture_digest": admission["host_capture_digest"],
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
        "signer_fingerprint": _RECOVERY_FINGERPRINTS["authorization"],
        "signature_namespace": recovery.RECOVERY_SIGNATURE_NAMESPACE,
        "signed_binding": signed_binding,
        "sshsig_armored": __import__("s2_5_testkit")._sign_bytes(
            private_key,
            validator._canonical_bytes(signed_binding),
            namespace=recovery.RECOVERY_SIGNATURE_NAMESPACE,
        ),
    }
    return _sealed(payload, "authorization_digest")


def _trusted_anchor(
    unresolved: dict,
    *,
    issued_at: str = NOW,
    expires_at: str = LATER,
    snapshot_version: int = 7,
    monotonic_floor: int = 7,
    latest_version: int = 7,
) -> dict:
    private_key = _RECOVERY_PRIVATE_KEYS["anchor"]
    append_entry_digest = unresolved["unresolved_state_digest"]
    append_head_digest = validator.canonical_digest({
        "external_sequence": snapshot_version,
        "previous_append_head_digest": D1,
        "append_entry_digest": append_entry_digest,
    })
    anchor_scope_id = "off-root:host-governance"
    readback_signed_binding = {
        "schema_version": "s2_5_recovery_anchor_external_readback_v2",
        "store_id": recovery.RECOVERY_ANCHOR_EXTERNAL_STORE_ID,
        "anchor_scope_id": anchor_scope_id,
        "snapshot_id": f"snapshot:s2-5:{snapshot_version}",
        "snapshot_version": snapshot_version,
        "monotonic_floor": monotonic_floor,
        "monotonic_floor_durable": True,
        "latest_version": latest_version,
        "latest_object_id": f"object:s2-5:{latest_version}",
        "latest_version_id": f"version:s2-5:{latest_version}",
        "latest_append_head_digest": append_head_digest,
        "latest_append_entry_digest": append_entry_digest,
        "immutable": True,
        "retention_mode": "COMPLIANCE_WORM",
        "full_chain_valid": True,
        "delete_denied": True,
        "evidence_class": "PLATFORM_OR_EXTERNAL_ATTESTED",
        "observed_at": issued_at,
        "expires_at": expires_at,
        "side_effect_class": "DISPOSABLE_TEST",
        "target_class": "disposable_systemd",
        "production_effect": False,
        "production_authority": False,
    }
    external_readback = _sealed({
        **readback_signed_binding,
        "signer_identity": recovery.RECOVERY_ANCHOR_READBACK_SIGNER_IDENTITY,
        "signer_fingerprint": _RECOVERY_FINGERPRINTS["anchor_readback"],
        "signature_namespace": (
            recovery.RECOVERY_ANCHOR_READBACK_SIGNATURE_NAMESPACE
        ),
        "signed_binding": copy.deepcopy(readback_signed_binding),
        "sshsig_armored": __import__("s2_5_testkit")._sign_bytes(
            _RECOVERY_PRIVATE_KEYS["anchor_readback"],
            validator._canonical_bytes(readback_signed_binding),
            namespace=recovery.RECOVERY_ANCHOR_READBACK_SIGNATURE_NAMESPACE,
        ),
    }, "readback_digest")
    signed_binding = {
        "schema_version": "s2_5_recovery_trusted_anchor_ref_v2",
        "anchor_id": "trusted-anchor:s2-5:7",
        "storage_class": "INDEPENDENT_OFF_STATE_ROOT",
        "anchor_scope_id": anchor_scope_id,
        "bound_unresolved_state_digest": unresolved["unresolved_state_digest"],
        "bound_state_root_id": unresolved["state_root_identity"]["root_id"],
        "bound_state_root_generation": unresolved["state_root_identity"][
            "generation"
        ],
        "bound_state_root_digest": unresolved["state_root_identity"][
            "root_digest"
        ],
        "source_head": unresolved["source_head"],
        "host_identity": unresolved["host_identity"],
        "host_capture_digest": unresolved["host_capture_digest"],
        "issued_at": issued_at,
        "expires_at": expires_at,
        "external_sequence": snapshot_version,
        "previous_append_head_digest": D1,
        "append_entry_digest": append_entry_digest,
        "append_head_digest": append_head_digest,
        "external_readback": external_readback,
        "append_only": True,
        "immutable_readback": True,
        "immutable_readback_digest": append_entry_digest,
        "append_actor_identity": "key:recovery-anchor-writer",
        "readback_verifier_identity": (
            recovery.RECOVERY_ANCHOR_READBACK_SIGNER_IDENTITY
        ),
        "evidence_class": "LOCAL_REPRODUCIBLE",
    }
    payload = {
        **signed_binding,
        "anchor_digest": validator.canonical_digest(signed_binding),
        "signer_identity": recovery.RECOVERY_ANCHOR_SIGNER_IDENTITY,
        "signer_fingerprint": _RECOVERY_FINGERPRINTS["anchor"],
        "signature_namespace": recovery.RECOVERY_ANCHOR_SIGNATURE_NAMESPACE,
        "signed_binding": copy.deepcopy(signed_binding),
        "sshsig_armored": __import__("s2_5_testkit")._sign_bytes(
            private_key,
            validator._canonical_bytes(signed_binding),
            namespace=recovery.RECOVERY_ANCHOR_SIGNATURE_NAMESPACE,
        ),
    }
    _CURRENT_ANCHOR_READBACK.clear()
    _CURRENT_ANCHOR_READBACK.update(
        copy.deepcopy(signed_binding["external_readback"])
    )
    return _sealed(payload, "reference_digest")


def _consumption_proof(intent: dict, *, evidence_class: str = "LOCAL_REPRODUCIBLE"):
    private_key = _RECOVERY_PRIVATE_KEYS["consumption"]
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
        "signer_fingerprint": _RECOVERY_FINGERPRINTS["consumption"],
        "signature_namespace": recovery.RECOVERY_CONSUMPTION_SIGNATURE_NAMESPACE,
        "signed_binding": copy.deepcopy(signed_binding),
        "sshsig_armored": __import__("s2_5_testkit")._sign_bytes(
            private_key,
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
    state_root = tmp_path / "state"
    state = lifecycle.S2_5RecoveryState(
        state_root=state_root,
        host_capture=_host_capture(state_root),
        now=NOW,
    )
    _record_state(state)
    return state


def _chain(state: lifecycle.S2_5RecoveryState):
    kernel = _kernel_binding(state.unresolved)
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
        now=NOW,
    )
    result = recovery.build_recovery_result(
        intent=intent,
        actor_capture=actor_capture,
        rollback=rollback,
        post_state=rollback["post_state"],
        status="RECOVERY_ABORTED",
        authorization_consumption_proof=_consumption_proof(intent),
        now=NOW,
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
        now=NOW,
    )
    return intent, rollback, result, postcheck


def _intent_materials(
    state: lifecycle.S2_5RecoveryState,
    action: str = "ROLLBACK_TO_PRE_STATE",
) -> tuple[dict, dict, dict, dict]:
    kernel = _kernel_binding(state.unresolved)
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
    intent, rollback, result, postcheck = artifacts
    binding = intent["recovery_binding"]
    assert binding["host_capture"] == state.host_capture
    assert binding["host_capture_digest"] == state.host_capture_digest
    assert binding["authorization"]["signed_binding"]["host_capture_digest"] == (
        state.host_capture_digest
    )
    assert binding["trusted_anchor"]["signed_binding"]["host_capture_digest"] == (
        state.host_capture_digest
    )
    assert rollback["actor_capture"]["signed_binding"]["host_capture_digest"] == (
        state.host_capture_digest
    )
    assert result["actor_capture"]["signed_binding"]["host_capture_digest"] == (
        state.host_capture_digest
    )
    assert postcheck["verifier_capture"]["signed_binding"][
        "host_capture_digest"
    ] == state.host_capture_digest
    kernel, admission, anchor, authorization = _intent_materials(state)
    assert kernel["host_capture_digest"] == state.host_capture_digest
    assert admission["host_capture_digest"] == state.host_capture_digest
    assert anchor["signed_binding"]["host_capture_digest"] == state.host_capture_digest
    assert authorization["signed_binding"]["host_capture_digest"] == (
        state.host_capture_digest
    )


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
            "current_readback", "readback_path", "monotonic_floor",
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
        host_capture=kit.signed_recovery_host_capture(state_root),
        now=kit.NOW,
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
        host_capture=kit.signed_recovery_host_capture(state_root),
        now=kit.NOW,
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
        host_capture=_host_capture(state_root),
        now=NOW,
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
    assert captured["host_identity"] == state.host_identity
    assert captured["host_capture"] == state.host_capture
    assert captured["host_capture_digest"] == state.host_capture_digest
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


def test_signed_anchor_for_an_unrelated_unresolved_generation_is_rejected(
    tmp_path,
):
    state = _state(tmp_path)
    kernel = _kernel_binding(state.unresolved)
    admission = _admission(state.unresolved)
    unrelated = copy.deepcopy(state.unresolved)
    unrelated["reasons"] = ["a different unresolved failure"]
    unrelated["state_root_identity"]["generation"] += 1
    unrelated["state_root_identity"]["root_digest"] = D1
    unrelated["unresolved_state_digest"] = validator.canonical_digest({
        key: value for key, value in unrelated.items()
        if key != "unresolved_state_digest"
    })
    unrelated_anchor = _trusted_anchor(unrelated)
    with pytest.raises(ValueError, match="unresolved|generation|latest"):
        recovery.build_recovery_intent(
            unresolved_state=state.unresolved,
            kernel_binding=kernel,
            admission=admission,
            authorization=_authorization(
                state.unresolved,
                action="ROLLBACK_TO_PRE_STATE",
                kernel_binding=kernel,
                admission=admission,
                trusted_anchor=unrelated_anchor,
            ),
            trusted_anchor=unrelated_anchor,
            action="ROLLBACK_TO_PRE_STATE",
            now=NOW,
        )


def test_signed_anchor_and_latest_readback_must_be_fresh(tmp_path):
    state = _state(tmp_path)
    kernel = _kernel_binding(state.unresolved)
    admission = _admission(state.unresolved)
    stale_anchor = _trusted_anchor(
        state.unresolved,
        issued_at="2026-07-30T11:40:00Z",
        expires_at="2026-07-30T11:50:00Z",
    )
    with pytest.raises(ValueError, match="stale|valid|expired|fresh"):
        recovery.build_recovery_intent(
            unresolved_state=state.unresolved,
            kernel_binding=kernel,
            admission=admission,
            authorization=_authorization(
                state.unresolved,
                action="ROLLBACK_TO_PRE_STATE",
                kernel_binding=kernel,
                admission=admission,
                trusted_anchor=stale_anchor,
            ),
            trusted_anchor=stale_anchor,
            action="ROLLBACK_TO_PRE_STATE",
            now=NOW,
        )


@pytest.mark.parametrize(
    ("mutation", "needle"),
    (
        (
            lambda anchor: anchor["external_readback"].update(
                latest_version=8
            ),
            "not the latest",
        ),
        (
            lambda anchor: anchor["external_readback"].update(
                monotonic_floor=8
            ),
            "monotonic floor",
        ),
        (
            lambda anchor: anchor["external_readback"].update(
                latest_append_head_digest=D2
            ),
            "latest head readback",
        ),
        (
            lambda anchor: anchor["external_readback"].update(
                latest_append_entry_digest=D2
            ),
            "latest entry readback",
        ),
        (
            lambda anchor: anchor["external_readback"].update(immutable=False),
            "not immutable",
        ),
    ),
)
def test_fully_resigned_anchor_cannot_forge_latest_immutable_readback(
    tmp_path,
    mutation,
    needle,
):
    state = _state(tmp_path)
    kernel = _kernel_binding(state.unresolved)
    admission = _admission(state.unresolved)
    anchor = _trusted_anchor(state.unresolved)
    mutation(anchor)
    _resign_anchor(anchor)
    with pytest.raises(ValueError, match=needle):
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


def test_fully_resigned_anchor_entry_rewrite_cannot_replace_current_state(
    tmp_path,
):
    state = _state(tmp_path)
    kernel = _kernel_binding(state.unresolved)
    admission = _admission(state.unresolved)
    anchor = _trusted_anchor(state.unresolved)
    anchor["append_entry_digest"] = D1
    anchor["append_head_digest"] = validator.canonical_digest({
        "external_sequence": anchor["external_sequence"],
        "previous_append_head_digest": anchor["previous_append_head_digest"],
        "append_entry_digest": D1,
    })
    anchor["immutable_readback_digest"] = D1
    anchor["external_readback"]["latest_append_entry_digest"] = D1
    anchor["external_readback"]["latest_append_head_digest"] = anchor[
        "append_head_digest"
    ]
    _resign_anchor(anchor)
    with pytest.raises(ValueError, match="current unresolved"):
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


@pytest.mark.parametrize("rewrite", ("sequence", "prior_head"))
def test_anchor_owner_cannot_coherently_rewrite_current_external_history(
    tmp_path,
    rewrite,
):
    state = _state(tmp_path)
    kernel = _kernel_binding(state.unresolved)
    admission = _admission(state.unresolved)
    anchor = _trusted_anchor(state.unresolved)
    if rewrite == "sequence":
        anchor["external_sequence"] = 8
        anchor["external_readback"]["snapshot_version"] = 8
        anchor["external_readback"]["monotonic_floor"] = 8
        anchor["external_readback"]["latest_version"] = 8
        anchor["anchor_id"] = "trusted-anchor:s2-5:8"
    else:
        anchor["previous_append_head_digest"] = D2
    anchor["append_head_digest"] = validator.canonical_digest({
        "external_sequence": anchor["external_sequence"],
        "previous_append_head_digest": anchor["previous_append_head_digest"],
        "append_entry_digest": anchor["append_entry_digest"],
    })
    anchor["external_readback"]["latest_append_head_digest"] = anchor[
        "append_head_digest"
    ]
    _resign_anchor(anchor)

    with pytest.raises(
        ValueError,
        match="external readback|independent readback|durable monotonic",
    ):
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


def test_old_legal_anchor_is_rejected_after_external_floor_advances(tmp_path):
    state = _state(tmp_path)
    kernel = _kernel_binding(state.unresolved)
    admission = _admission(state.unresolved)
    old_anchor = _trusted_anchor(state.unresolved)
    _trusted_anchor(
        state.unresolved,
        snapshot_version=8,
        monotonic_floor=8,
        latest_version=8,
    )

    with pytest.raises(
        ValueError,
        match="current external readback|durable monotonic",
    ):
        recovery.build_recovery_intent(
            unresolved_state=state.unresolved,
            kernel_binding=kernel,
            admission=admission,
            authorization=_authorization(
                state.unresolved,
                action="ROLLBACK_TO_PRE_STATE",
                kernel_binding=kernel,
                admission=admission,
                trusted_anchor=old_anchor,
            ),
            trusted_anchor=old_anchor,
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
            kernel_binding=_kernel_binding(state.unresolved),
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


def test_signed_actor_capture_from_chain_b_cannot_be_rewrapped_as_chain_a_rollback(
    tmp_path,
):
    _intent_a, rollback_a, _result_a, _postcheck_a = _chain(
        _state(tmp_path / "chain-a")
    )
    _intent_b, _rollback_b, result_b, _postcheck_b = _chain(
        _state(tmp_path / "chain-b")
    )
    forged = copy.deepcopy(rollback_a)
    forged["actor_capture"] = copy.deepcopy(result_b["actor_capture"])
    forged["actor_capture_digest"] = forged["actor_capture"]["capture_digest"]
    forged["actor_identity"] = copy.deepcopy(
        forged["actor_capture"]["node_identity"]
    )
    forged["actor_process"] = copy.deepcopy(
        forged["actor_capture"]["process_identity"]
    )
    _reseal_rollback(forged)
    errors = validator.validate_aiml_artifact(forged, now=NOW)
    assert any(
        "capture bound_state_root_id differs from the recovery intent" in error
        for error in errors
    ), errors
    assert any(
        "capture recovery_intent_digest differs from the recovery intent" in error
        for error in errors
    ), errors


def test_chain_b_actor_capture_is_checked_against_chain_a_result_intent_and_state(
    tmp_path,
):
    _intent_a, _rollback_a, result_a, _postcheck_a = _chain(
        _state(tmp_path / "result-chain-a")
    )
    _intent_b, _rollback_b, result_b, _postcheck_b = _chain(
        _state(tmp_path / "result-chain-b")
    )
    forged = copy.deepcopy(result_a)
    forged["actor_capture"] = copy.deepcopy(result_b["actor_capture"])
    forged["actor_capture_digest"] = forged["actor_capture"]["capture_digest"]
    forged["actor_identity"] = copy.deepcopy(
        forged["actor_capture"]["node_identity"]
    )
    forged["actor_process"] = copy.deepcopy(
        forged["actor_capture"]["process_identity"]
    )
    _reseal_result(forged)
    errors = validator.validate_aiml_artifact(forged, now=NOW)
    assert any(
        "capture bound_state_root_id differs from the recovery intent" in error
        for error in errors
    ), errors


def test_signed_verifier_capture_from_chain_b_cannot_be_rewrapped_in_chain_a(
    tmp_path,
):
    _intent_a, _rollback_a, _result_a, postcheck_a = _chain(
        _state(tmp_path / "postcheck-chain-a")
    )
    _intent_b, _rollback_b, _result_b, postcheck_b = _chain(
        _state(tmp_path / "postcheck-chain-b")
    )
    forged = copy.deepcopy(postcheck_a)
    forged["verifier_capture"] = copy.deepcopy(
        postcheck_b["verifier_capture"]
    )
    forged["verifier_capture_digest"] = forged["verifier_capture"][
        "capture_digest"
    ]
    forged["verifier_identity"] = copy.deepcopy(
        forged["verifier_capture"]["node_identity"]
    )
    forged["verifier_process"] = copy.deepcopy(
        forged["verifier_capture"]["process_identity"]
    )
    _reseal_postcheck(forged)
    errors = validator.validate_aiml_artifact(forged, now=NOW)
    assert any(
        "capture bound_state_root_id differs from the recovery intent" in error
        for error in errors
    ), errors
    assert any(
        "capture recovery_result_digest differs from result" in error
        for error in errors
    ), errors


def test_each_recovery_capability_has_a_distinct_fixed_trust_profile():
    import agent_governance_s2_5_attestation as attestation

    prefixes = (
        "RECOVERY_AUTHORIZATION", "RECOVERY_ANCHOR",
        "RECOVERY_ANCHOR_READBACK", "RECOVERY_CONSUMPTION",
        "RECOVERY_ACTOR_CAPTURE", "RECOVERY_VERIFIER_CAPTURE",
    )
    paths = [
        getattr(recovery, prefix + "_TRUST_ROOT_PUBLIC_KEY_PATH")
        for prefix in prefixes
    ]
    fingerprints = [
        getattr(recovery, prefix + "_TRUST_ROOT_FINGERPRINT")
        for prefix in prefixes
    ]
    assert all(path.is_absolute() for path in paths)
    assert len(set(paths)) == len(paths)
    assert len(set(fingerprints)) == len(fingerprints)
    assert attestation.S2_5_TRUST_ROOT_FINGERPRINT not in fingerprints
    for prefix in prefixes:
        loader = getattr(
            recovery,
            "_load_" + prefix.lower() + "_trust_root_public_key",
        )
        assert not inspect.signature(loader).parameters
    assert readback_adapter.FIXED_ATTESTOR_SOCKET_PATH.startswith("/")
    assert set(inspect.signature(
        readback_adapter._query_current_anchor_readback
    ).parameters) == {"anchor_scope_id"}
    assert not hasattr(recovery, "_load_recovery_trust_root_public_key")
    assert not hasattr(recovery, "RECOVERY_TRUST_ROOT_PUBLIC_KEY")


def test_authorization_key_cannot_forge_anchor_signature(tmp_path):
    state = _state(tmp_path)
    kernel, admission, anchor, authorization = _intent_materials(state)
    _replace_signature_with_profile(anchor, "authorization")
    anchor["reference_digest"] = validator.canonical_digest({
        key: value for key, value in anchor.items() if key != "reference_digest"
    })
    with pytest.raises(ValueError, match="trusted anchor SSHSIG"):
        recovery.build_recovery_intent(
            unresolved_state=state.unresolved,
            kernel_binding=kernel,
            admission=admission,
            authorization=authorization,
            trusted_anchor=anchor,
            action="ROLLBACK_TO_PRE_STATE",
            now=NOW,
        )


def test_anchor_owner_key_cannot_forge_current_readback_signature(tmp_path):
    state = _state(tmp_path)
    kernel, admission, anchor, _authorization_artifact = _intent_materials(state)
    readback = anchor["external_readback"]
    _replace_signature_with_profile(readback, "anchor")
    readback["readback_digest"] = validator.canonical_digest({
        key: value for key, value in readback.items()
        if key != "readback_digest"
    })
    _CURRENT_ANCHOR_READBACK.clear()
    _CURRENT_ANCHOR_READBACK.update(copy.deepcopy(readback))
    _resign_anchor(anchor)
    with pytest.raises(ValueError, match="external readback SSHSIG"):
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


def test_current_readback_unavailable_fails_closed(tmp_path, monkeypatch):
    state = _state(tmp_path)
    kernel, admission, anchor, authorization = _intent_materials(state)

    def unavailable(_request_bytes):
        raise readback_adapter.RecoveryAnchorReadbackError(
            "independent_current_witness_unavailable"
        )

    monkeypatch.setattr(
        readback_adapter,
        "_fixed_transport_exchange",
        unavailable,
    )
    with pytest.raises(ValueError, match="current readback.*unavailable"):
        recovery.build_recovery_intent(
            unresolved_state=state.unresolved,
            kernel_binding=kernel,
            admission=admission,
            authorization=authorization,
            trusted_anchor=anchor,
            action="ROLLBACK_TO_PRE_STATE",
            now=NOW,
        )


def test_anchor_owner_key_cannot_forge_fresh_challenge_response(
    tmp_path,
    monkeypatch,
):
    state = _state(tmp_path)
    kernel, admission, anchor, authorization = _intent_materials(state)

    def forged_response(request_bytes):
        response = _fresh_current_readback_response(request_bytes)
        _resign_current_readback(response, profile="anchor")
        return response

    monkeypatch.setattr(
        readback_adapter,
        "_fixed_transport_exchange",
        forged_response,
    )
    with pytest.raises(ValueError, match="current readback.*SSHSIG|fingerprint"):
        recovery.build_recovery_intent(
            unresolved_state=state.unresolved,
            kernel_binding=kernel,
            admission=admission,
            authorization=authorization,
            trusted_anchor=anchor,
            action="ROLLBACK_TO_PRE_STATE",
            now=NOW,
        )


def test_anchor_key_cannot_forge_authorization_signature(tmp_path):
    state = _state(tmp_path)
    kernel, admission, anchor, authorization = _intent_materials(state)
    _replace_signature_with_profile(authorization, "anchor")
    authorization["authorization_digest"] = validator.canonical_digest({
        key: value for key, value in authorization.items()
        if key != "authorization_digest"
    })
    with pytest.raises(ValueError, match="recovery authorization SSHSIG"):
        recovery.build_recovery_intent(
            unresolved_state=state.unresolved,
            kernel_binding=kernel,
            admission=admission,
            authorization=authorization,
            trusted_anchor=anchor,
            action="ROLLBACK_TO_PRE_STATE",
            now=NOW,
        )


def test_verifier_capture_key_cannot_forge_actor_capture(tmp_path):
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
    actor_capture = _capture(intent=intent, observed_state=post_state)
    _replace_signature_with_profile(actor_capture, "verifier_capture")
    _reseal_capture(actor_capture)
    with pytest.raises(ValueError, match="recovery capture SSHSIG"):
        recovery.build_recovery_rollback(
            intent=intent,
            actor_capture=actor_capture,
            post_state=post_state,
            status="LATCH_PRESERVED",
            now=NOW,
        )


def test_authorization_key_cannot_forge_consumption_signature(tmp_path):
    state = _state(tmp_path)
    intent, rollback, _result, _postcheck = _chain(state)
    actor_capture = copy.deepcopy(rollback["actor_capture"])
    proof = _consumption_proof(intent)
    _replace_signature_with_profile(proof, "authorization")
    proof["proof_digest"] = validator.canonical_digest({
        key: value for key, value in proof.items() if key != "proof_digest"
    })
    with pytest.raises(ValueError, match="authorization consumption SSHSIG"):
        recovery.build_recovery_result(
            intent=intent,
            actor_capture=actor_capture,
            rollback=rollback,
            post_state=rollback["post_state"],
            status="RECOVERY_ABORTED",
            authorization_consumption_proof=proof,
            now=NOW,
        )


def test_actor_capture_key_cannot_forge_verifier_capture(tmp_path):
    state = _state(tmp_path)
    intent, _rollback, result, _postcheck = _chain(state)
    verifier_capture = _capture(
        intent=intent,
        result=result,
        observed_state=result["post_state"],
        verifier=True,
    )
    _replace_signature_with_profile(verifier_capture, "actor_capture")
    _reseal_capture(verifier_capture)
    with pytest.raises(ValueError, match="recovery capture SSHSIG"):
        recovery.build_recovery_postcheck(
            intent=intent,
            result=result,
            verifier_capture=verifier_capture,
            observed_state=result["post_state"],
            status="RECOVERY_UNRESOLVED",
            now=NOW,
        )


def test_recovery_trust_root_reader_rejects_writable_or_multiply_linked_key(
    tmp_path,
):
    public_key = __import__("s2_5_testkit").mint_key(
        tmp_path, "loader-check"
    )[1]
    key_path = tmp_path / "recovery-owner.pub"
    key_path.write_text(public_key + "\n", encoding="ascii")
    key_path.chmod(0o666)
    with pytest.raises(ValueError, match="writable"):
        _ORIGINAL_RECOVERY_PUBLIC_KEY_READER(key_path)
    key_path.chmod(0o600)
    (tmp_path / "second-link.pub").hardlink_to(key_path)
    with pytest.raises(ValueError, match="hard link"):
        _ORIGINAL_RECOVERY_PUBLIC_KEY_READER(key_path)


def test_prior_signed_current_response_cannot_answer_a_fresh_challenge(
    tmp_path,
    monkeypatch,
):
    state = _state(tmp_path)
    kernel = _kernel_binding(state.unresolved)
    admission = _admission(state.unresolved)
    old_anchor = _trusted_anchor(state.unresolved)
    old_query = readback_adapter._query_current_anchor_readback(
        anchor_scope_id=old_anchor["anchor_scope_id"],
    )
    replayed_response = copy.deepcopy(old_query["result"]["response"])
    _trusted_anchor(
        state.unresolved,
        snapshot_version=8,
        monotonic_floor=8,
        latest_version=8,
    )
    monkeypatch.setattr(
        readback_adapter,
        "_fixed_transport_exchange",
        lambda _request_bytes: copy.deepcopy(replayed_response),
    )
    with pytest.raises(
        ValueError,
        match="fresh current readback|fresh_binding|challenge|query_digest",
    ):
        recovery.build_recovery_intent(
            unresolved_state=state.unresolved,
            kernel_binding=kernel,
            admission=admission,
            authorization=_authorization(
                state.unresolved,
                action="ROLLBACK_TO_PRE_STATE",
                kernel_binding=kernel,
                admission=admission,
                trusted_anchor=old_anchor,
            ),
            trusted_anchor=old_anchor,
            action="ROLLBACK_TO_PRE_STATE",
            now=NOW,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("store_id", "other-store"),
        ("anchor_scope_id", "other-scope"),
        ("snapshot_version", 8),
        ("monotonic_floor", 8),
        ("latest_version", 8),
        ("latest_object_id", "object:s2-5:8"),
        ("latest_version_id", "version:s2-5:8"),
        ("latest_append_head_digest", D2),
        ("latest_append_entry_digest", D2),
        ("monotonic_floor_durable", False),
        ("retention_mode", "GOVERNANCE"),
        ("full_chain_valid", False),
        ("delete_denied", False),
        ("production_effect", True),
        ("production_authority", True),
        ("expires_at", LATER),
    ),
)
def test_fresh_signed_current_response_mutations_fail_closed(
    tmp_path,
    monkeypatch,
    field,
    value,
):
    state = _state(tmp_path)
    kernel, admission, anchor, authorization = _intent_materials(state)

    def mutated_response(request_bytes):
        response = _fresh_current_readback_response(request_bytes)
        response[field] = value
        _resign_current_readback(response)
        return response

    monkeypatch.setattr(
        readback_adapter,
        "_fixed_transport_exchange",
        mutated_response,
    )
    with pytest.raises(ValueError):
        recovery.build_recovery_intent(
            unresolved_state=state.unresolved,
            kernel_binding=kernel,
            admission=admission,
            authorization=authorization,
            trusted_anchor=anchor,
            action="ROLLBACK_TO_PRE_STATE",
            now=NOW,
        )


def test_intent_requires_explicit_time_and_resolve_uses_closed_central_schema(tmp_path):
    for builder in (
        recovery.build_recovery_intent,
        recovery.build_recovery_rollback,
        recovery.build_recovery_result,
        recovery.build_recovery_postcheck,
    ):
        assert inspect.signature(builder).parameters[
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


@pytest.mark.parametrize(
    ("mutate", "needle"),
    [
        (
            lambda item: item.update(schema_version="foreign_host_capture_v1"),
            "schema_version",
        ),
        (lambda item: item.update(source_head="not-a-git-sha"), "source_head"),
        (lambda item: item["process_identity"].update(uid=True), "uid"),
        (lambda item: item["node_identity"].update(node_id=""), "node_id"),
    ],
)
def test_nested_recovery_chain_revalidates_fully_resigned_host_capture_schema(
    tmp_path, mutate, needle
):
    state = _state(tmp_path)
    intent, _rollback, _result, _postcheck = _chain(state)
    capture = intent["recovery_binding"]["host_capture"]
    mutate(capture)
    mutate(capture["signed_binding"])
    _replace_signature_with_profile(capture, "host_capture")
    capture["self_digest"] = validator.artifact_self_digest(capture)
    errors = validator.validate_aiml_artifact(intent, now=NOW)
    assert any(needle in error for error in errors), errors


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
    with pytest.raises(ValueError, match="future|authorization window"):
        recovery.build_recovery_rollback(
            intent=intent,
            actor_capture=future_capture,
            post_state=post_state,
            status="LATCH_PRESERVED",
            now=NOW,
        )


def test_result_and_postcheck_builders_reject_future_signed_capture(tmp_path):
    state = _state(tmp_path)
    intent, rollback, result, _postcheck = _chain(state)
    future_actor = _capture(
        intent=intent,
        observed_state=rollback["post_state"],
        observed_at="2026-07-30T12:09:00Z",
    )
    with pytest.raises(ValueError, match="future"):
        recovery.build_recovery_result(
            intent=intent,
            actor_capture=future_actor,
            rollback=rollback,
            post_state=rollback["post_state"],
            status="RECOVERY_ABORTED",
            authorization_consumption_proof=_consumption_proof(intent),
            now=NOW,
        )
    future_verifier = _capture(
        intent=intent,
        result=result,
        observed_state=result["post_state"],
        verifier=True,
        observed_at="2026-07-30T12:09:00Z",
    )
    with pytest.raises(ValueError, match="future"):
        recovery.build_recovery_postcheck(
            intent=intent,
            result=result,
            verifier_capture=future_verifier,
            observed_state=result["post_state"],
            status="RECOVERY_UNRESOLVED",
            now=NOW,
        )


def test_host_capture_leaf_and_schema_extend_closure_without_lifecycle_roots():
    closure = json.loads(
        (ML_ROOT / "application_bundle_runtime_closure_v1.json").read_text()
    )
    expected_resources = {
        "program_code/ml_training/schemas/aiml_gate_receipts/"
        f"s2_5_recovery_{kind}_v1.schema.json"
        for kind in ("host_capture", "intent", "postcheck", "result", "rollback")
    }
    assert expected_resources <= set(closure["schema_resources"])
    # The launch review oracle and its centrally registered disposable-test
    # chain are application-reachable; lifecycle roots remain excluded.
    assert len(closure["python_modules"]) == 55
    assert len(closure["schema_resources"]) == 90
    assert closure["runtime_lazy_helper_roots"] == [{
        "module": "agent_governance_sealed_build",
        "reason": (
            "learning_runtime_manifest._dependency_lock_v2 lazily imports "
            "verify_lock_closure/lock_target_platform at v2 preflight time; "
            "the import is runtime-reachable on every production start"
        ),
    }]
    assert (
        "program_code/ml_training/aiml_gate_receipt_s2_5_host_capture.py"
        in closure["python_modules"]
    )
    assert not any(
        path.endswith((
            "agent_governance_s2_5_recovery.py",
            "agent_governance_s2_5_recovery_state.py",
            "agent_governance_s2_5_lifecycle.py",
        ))
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
                now=NOW,
            )

    with pytest.raises(ValueError, match="explicit.*current time"):
        state.resolve(
            recovery_result=_result,
            independent_postcheck=_postcheck,
            now=None,
        )
    assert state.unresolved is not None
