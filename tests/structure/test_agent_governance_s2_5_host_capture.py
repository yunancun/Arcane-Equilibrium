"""S2E.LW1 BIND-001: signed, closed S2.5 recovery host-capture ABI."""

from __future__ import annotations

import copy
import ast
import importlib
import inspect
import sys
import weakref
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import aiml_gate_receipt_schema_core as schema_core  # noqa: E402
import aiml_gate_receipt_s2_5_host_capture as host_capture  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402
import agent_governance_s2_5_disposable_profile as disposable_profile  # noqa: E402
import agent_governance_s2_5_lifecycle as lifecycle  # noqa: E402
import agent_governance_s2_5_recovery_host_capture_producer as producer  # noqa: E402
import agent_governance_s2_host_kernel as host_kernel  # noqa: E402


HOST_CAPTURE_SCHEMA = "s2_5_recovery_host_capture_v1"
NOW = "2026-07-30T12:05:00Z"
OBSERVED = "2026-07-30T12:00:00Z"
EXPIRES = "2026-07-30T12:10:00Z"
HEAD = "a" * 40
DIGEST = "sha256:" + "1" * 64


def _fixed_loader(public_key: str):
    return lambda: public_key


@pytest.fixture
def signing_profile(tmp_path, monkeypatch):
    kit = __import__("s2_5_testkit")
    private_key, public_key, fingerprint = kit.mint_key(
        tmp_path, "s2-5-recovery-host-capture"
    )
    monkeypatch.setattr(
        host_capture,
        "_load_recovery_host_capture_trust_root_public_key",
        _fixed_loader(public_key),
    )
    monkeypatch.setattr(
        host_capture,
        "RECOVERY_HOST_CAPTURE_TRUST_ROOT_FINGERPRINT",
        fingerprint,
    )
    return private_key, public_key, fingerprint


def _signed_capture(
    state_root: Path,
    signing_profile,
    *,
    source_head: str = HEAD,
    observed_at: str = OBSERVED,
    expires_at: str = EXPIRES,
) -> dict:
    private_key, _public_key, fingerprint = signing_profile
    signed = {
        "schema_version": HOST_CAPTURE_SCHEMA,
        "capture_profile": host_capture.HOST_CAPTURE_PROFILE,
        "source_head": source_head,
        "stable_host_facts": {
            "machine_id_digest": DIGEST,
            "node_name": "trade-core-disposable",
            "os_id": "linux",
            "architecture": "x86_64",
        },
        "host_identity": "",
        "node_identity": {
            "node_id": host_capture.HOST_CAPTURE_NODE_ID,
            "role": "HOST_ATTESTOR",
            "permission": "read_only",
            "key_identity": host_capture.RECOVERY_HOST_CAPTURE_SIGNER_IDENTITY,
        },
        "process_identity": {
            "uid": disposable_profile.PROFILE_UID,
            "cgroup": disposable_profile.RECOVERY_RUNNER_CGROUP,
        },
        "boot_manager_facts": {
            "boot_id": "boot-disposable-1",
            "manager": "systemd",
            "manager_root": disposable_profile.USER_MANAGER_ROOT,
            "unit_name": disposable_profile.RECOVERY_RUNNER_UNIT,
            "canonical_state_root": str(state_root.resolve(strict=False)),
        },
        "admission_provenance": {
            "schema_version": host_capture.HOST_CAPTURE_ADMISSION_SCHEMA_VERSION,
            "admission_class": host_capture.HOST_CAPTURE_ADMISSION_CLASS,
            "capability_protocol": (
                host_capture.HOST_CAPTURE_SIGNER_CAPABILITY_PROTOCOL
            ),
            "capability_path": host_capture.HOST_CAPTURE_SIGNER_CAPABILITY_PATH,
            "node_id": host_capture.HOST_CAPTURE_NODE_ID,
            "role": "HOST_ATTESTOR",
            "permission": "read_only",
            "uid": disposable_profile.PROFILE_UID,
            "cgroup": disposable_profile.RECOVERY_RUNNER_CGROUP,
            "unit_name": disposable_profile.RECOVERY_RUNNER_UNIT,
            "canonical_state_root": str(state_root.resolve(strict=False)),
            "signer_identity": (
                host_capture.RECOVERY_HOST_CAPTURE_SIGNER_IDENTITY
            ),
            "signer_fingerprint": fingerprint,
        },
        "observed_at": observed_at,
        "expires_at": expires_at,
        "side_effect_class": "DISPOSABLE_TEST",
        "production_effect": False,
        "production_authority": False,
        "target_class": "disposable_systemd",
    }
    signed["host_identity"] = host_capture.derive_s2_5_recovery_host_identity(signed)
    artifact = {
        **signed,
        "signer_identity": host_capture.RECOVERY_HOST_CAPTURE_SIGNER_IDENTITY,
        "signer_fingerprint": fingerprint,
        "signature_namespace": (
            host_capture.RECOVERY_HOST_CAPTURE_SIGNATURE_NAMESPACE
        ),
        "signed_binding": copy.deepcopy(signed),
        "sshsig_armored": __import__("s2_5_testkit")._sign_bytes(
            private_key,
            validator._canonical_bytes(signed),
            namespace=host_capture.RECOVERY_HOST_CAPTURE_SIGNATURE_NAMESPACE,
        ),
    }
    artifact["self_digest"] = validator.artifact_self_digest(artifact)
    return artifact


def _reseal(artifact: dict) -> None:
    artifact["self_digest"] = validator.artifact_self_digest(artifact)


def _resign(artifact: dict, private_key: Path) -> None:
    artifact["sshsig_armored"] = __import__("s2_5_testkit")._sign_bytes(
        private_key,
        validator._canonical_bytes(artifact["signed_binding"]),
        namespace=host_capture.RECOVERY_HOST_CAPTURE_SIGNATURE_NAMESPACE,
    )
    _reseal(artifact)


def test_host_capture_schema_is_registered_before_recovery_artifact_validation():
    assert HOST_CAPTURE_SCHEMA in schema_core.SCHEMA_FILES
    leaf = importlib.import_module("aiml_gate_receipt_s2_5_host_capture")
    assert callable(leaf.validate_s2_5_recovery_host_capture)


def test_fixed_producer_captures_kernel_facts_and_uses_only_capability_signer(
    tmp_path, signing_profile, monkeypatch
):
    private_key, _public_key, fingerprint = signing_profile
    monkeypatch.setattr(producer.os, "geteuid", lambda: disposable_profile.PROFILE_UID)
    monkeypatch.setattr(
        producer,
        "_unified_cgroup",
        lambda: disposable_profile.RECOVERY_RUNNER_CGROUP,
    )
    monkeypatch.setattr(producer, "_git_source_head", lambda: HEAD)
    monkeypatch.setattr(producer, "_os_id", lambda: "linux")
    monkeypatch.setattr(producer.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        producer.os,
        "uname",
        lambda: type("Uname", (), {"nodename": "trade-core-disposable"})(),
    )

    def fixed_fact(path, *, label):
        del label
        if path == producer.MACHINE_ID_PATH:
            return b"machine-id-test\n"
        if path == producer.BOOT_ID_PATH:
            return b"boot-disposable-1\n"
        raise AssertionError(path)

    monkeypatch.setattr(producer, "_read_fixed_fact", fixed_fact)
    monkeypatch.setattr(
        producer,
        "_invoke_fixed_signer_capability",
        lambda payload: __import__("s2_5_testkit")._sign_bytes(
            private_key,
            payload,
            namespace=host_capture.RECOVERY_HOST_CAPTURE_SIGNATURE_NAMESPACE,
        ),
    )
    monkeypatch.setattr(
        producer,
        "RECOVERY_HOST_CAPTURE_TRUST_ROOT_FINGERPRINT",
        fingerprint,
    )
    artifact = producer.capture_s2_5_recovery_host()

    assert artifact["source_head"] == HEAD
    assert artifact["process_identity"] == {
        "uid": disposable_profile.PROFILE_UID,
        "cgroup": disposable_profile.RECOVERY_RUNNER_CGROUP,
    }
    assert artifact["admission_provenance"]["capability_path"] == (
        host_capture.HOST_CAPTURE_SIGNER_CAPABILITY_PATH
    )
    assert host_capture.validate_s2_5_recovery_host_capture(
        artifact, now=artifact["observed_at"]
    ) == []


@pytest.mark.parametrize(
    ("uid", "cgroup"),
    [
        (9999, disposable_profile.RECOVERY_RUNNER_CGROUP),
        (disposable_profile.PROFILE_UID, "/foreign.scope"),
    ],
)
def test_fixed_producer_rejects_uid_or_cgroup_drift(
    monkeypatch, uid, cgroup
):
    monkeypatch.setattr(producer.os, "geteuid", lambda: uid)
    monkeypatch.setattr(producer, "_unified_cgroup", lambda: cgroup)
    with pytest.raises(ValueError, match="fixed recovery-runner admission"):
        producer.capture_s2_5_recovery_host()


def test_fixed_signer_capability_rejects_symlink_and_untrusted_mode(
    tmp_path, monkeypatch
):
    target = tmp_path / "signer"
    target.write_text("#!/bin/sh\nexit 1\n", encoding="ascii")
    target.chmod(0o777)
    monkeypatch.setattr(producer, "HOST_CAPTURE_SIGNER_CAPABILITY_PATH", str(target))
    with pytest.raises(ValueError, match="not trusted"):
        producer._invoke_fixed_signer_capability(b"payload")

    link = tmp_path / "signer-link"
    link.symlink_to(target)
    monkeypatch.setattr(producer, "HOST_CAPTURE_SIGNER_CAPABILITY_PATH", str(link))
    with pytest.raises(ValueError, match="not trusted"):
        producer._invoke_fixed_signer_capability(b"payload")


def test_fixed_producer_delegates_source_head_to_exact_kernel_argv(monkeypatch):
    calls: list[tuple[str, ...]] = []

    class _Kernel:
        def __init__(self, *, session):
            assert session == host_kernel.SESSION_S2_5_RECOVERY_HOST_CAPTURE

        def run(self, argv):
            candidate = tuple(argv)
            calls.append(candidate)
            if candidate == host_kernel.RECOVERY_HOST_CAPTURE_HEAD_ARGV:
                return HEAD + "\n"
            return ""

    monkeypatch.setattr(producer.host_kernel, "HostExecutionKernel", _Kernel)
    assert producer._git_source_head() == HEAD
    assert calls == [
        *host_kernel.RECOVERY_HOST_CAPTURE_CLEAN_ARGV,
        host_kernel.RECOVERY_HOST_CAPTURE_STATUS_ARGV,
        host_kernel.RECOVERY_HOST_CAPTURE_HEAD_ARGV,
    ]


def test_fixed_producer_rejects_untracked_source_files(monkeypatch):
    class _Kernel:
        def __init__(self, *, session):
            assert session == host_kernel.SESSION_S2_5_RECOVERY_HOST_CAPTURE

        def run(self, argv):
            if tuple(argv) == host_kernel.RECOVERY_HOST_CAPTURE_STATUS_ARGV:
                return "?? helper_scripts/maintenance_scripts/hashlib.py\n"
            return ""

    monkeypatch.setattr(producer.host_kernel, "HostExecutionKernel", _Kernel)
    with pytest.raises(ValueError, match="not fully clean"):
        producer._git_source_head()


def test_kernel_signer_binding_equals_receipt_owner_constants():
    assert host_kernel.RECOVERY_HOST_CAPTURE_SIGNER_ARGV == (
        host_capture.HOST_CAPTURE_SIGNER_CAPABILITY_PATH,
        "--protocol",
        host_capture.HOST_CAPTURE_SIGNER_CAPABILITY_PROTOCOL,
    )

def test_producer_public_surface_has_no_caller_selected_identity_or_clock():
    assert list(inspect.signature(producer.capture_s2_5_recovery_host).parameters) == []
    with pytest.raises(SystemExit, match="accepts no arguments"):
        producer.main(["--now", NOW])


def test_valid_signed_host_capture_is_dispatched_by_the_central_validator(
    tmp_path, signing_profile
):
    artifact = _signed_capture(tmp_path / "state", signing_profile)
    assert host_capture.validate_s2_5_recovery_host_capture(
        artifact, now=NOW
    ) == []
    assert validator.validate_aiml_artifact(artifact, now=NOW) == []
    assert artifact["host_identity"] == (
        host_capture.derive_s2_5_recovery_host_identity(artifact)
    )
    assert any(
        "explicit trusted current time" in error
        for error in validator.validate_aiml_artifact(artifact)
    )


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
def test_direct_leaf_enforces_checked_in_schema_for_fully_resigned_capture(
    tmp_path, signing_profile, mutate, needle
):
    artifact = _signed_capture(tmp_path / "state", signing_profile)
    mutate(artifact)
    mutate(artifact["signed_binding"])
    _resign(artifact, signing_profile[0])
    errors = host_capture.validate_s2_5_recovery_host_capture(
        artifact, now=NOW
    )
    assert any(needle in error for error in errors), errors


def test_host_capture_has_no_caller_selected_trust_or_replay_seams():
    for public_function in (
        host_capture.validate_s2_5_recovery_host_capture,
        host_capture.derive_s2_5_recovery_host_identity,
        host_capture.recovery_host_capture_signed_bytes,
    ):
        assert not set(inspect.signature(public_function).parameters) & {
            "loader", "public_key", "private_key", "key_path", "profile", "nonce",
        }


@pytest.mark.parametrize(
    ("mutation", "needle"),
    [
        (lambda item: item.update(sshsig_armored=""), "sshsig"),
        (
            lambda item: item.update(
                signer_fingerprint="SHA256:" + "A" * 43
            ),
            "fingerprint",
        ),
        (
            lambda item: item.update(
                signature_namespace="arcane-equilibrium-wrong-capability"
            ),
            "namespace",
        ),
    ],
)
def test_unsigned_wrong_fingerprint_and_wrong_namespace_fail_closed(
    tmp_path, signing_profile, mutation, needle
):
    artifact = _signed_capture(tmp_path / "state", signing_profile)
    mutation(artifact)
    _reseal(artifact)
    errors = validator.validate_aiml_artifact(artifact, now=NOW)
    assert any(needle.lower() in error.lower() for error in errors), errors


def test_signature_from_a_different_capability_key_is_rejected(
    tmp_path, signing_profile
):
    artifact = _signed_capture(tmp_path / "state", signing_profile)
    wrong_key, _public_key, _fingerprint = __import__("s2_5_testkit").mint_key(
        tmp_path, "wrong-capability"
    )
    artifact["sshsig_armored"] = __import__("s2_5_testkit")._sign_bytes(
        wrong_key,
        validator._canonical_bytes(artifact["signed_binding"]),
        namespace=host_capture.RECOVERY_HOST_CAPTURE_SIGNATURE_NAMESPACE,
    )
    _reseal(artifact)
    errors = validator.validate_aiml_artifact(artifact, now=NOW)
    assert any("SSHSIG is invalid" in error for error in errors), errors


@pytest.mark.parametrize(
    ("observed_at", "expires_at", "now", "needle"),
    [
        (OBSERVED, EXPIRES, "2026-07-30T12:10:00Z", "stale"),
        (
            "2026-07-30T12:06:00Z",
            "2026-07-30T12:10:00Z",
            NOW,
            "future",
        ),
    ],
)
def test_stale_and_future_host_capture_windows_are_rejected(
    tmp_path, signing_profile, observed_at, expires_at, now, needle
):
    artifact = _signed_capture(
        tmp_path / "state",
        signing_profile,
        observed_at=observed_at,
        expires_at=expires_at,
    )
    errors = validator.validate_aiml_artifact(artifact, now=now)
    assert any(needle in error for error in errors), errors


def test_historical_integrity_rechecks_signature_without_reapplying_freshness(
    tmp_path, signing_profile
):
    artifact = _signed_capture(tmp_path / "state", signing_profile)

    assert host_capture.validate_s2_5_recovery_host_capture_integrity(
        artifact
    ) == []
    assert any(
        "stale" in error
        for error in host_capture.validate_s2_5_recovery_host_capture(
            artifact, now="2026-07-31T12:00:00Z"
        )
    )

    rewritten = copy.deepcopy(artifact)
    rewritten["stable_host_facts"]["node_name"] = "coherent-rewrite"
    rewritten["signed_binding"]["stable_host_facts"]["node_name"] = (
        "coherent-rewrite"
    )
    rewritten["host_identity"] = (
        host_capture.derive_s2_5_recovery_host_identity(rewritten)
    )
    rewritten["signed_binding"]["host_identity"] = rewritten["host_identity"]
    _reseal(rewritten)
    assert any(
        "SSHSIG is invalid" in error
        for error in (
            host_capture.validate_s2_5_recovery_host_capture_integrity(
                rewritten
            )
        )
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda signed: signed.update(source_head="b" * 40),
        lambda signed: signed["node_identity"].update(node_id="foreign-node"),
        lambda signed: signed["process_identity"].update(uid=9999),
        lambda signed: signed["boot_manager_facts"].update(
            canonical_state_root="/tmp/foreign-root"
        ),
    ],
)
def test_source_node_process_and_root_rewrite_cannot_survive_digest_reseal(
    tmp_path, signing_profile, mutate
):
    artifact = _signed_capture(tmp_path / "state", signing_profile)
    mutate(artifact)
    mutate(artifact["signed_binding"])
    _reseal(artifact)
    errors = validator.validate_aiml_artifact(artifact, now=NOW)
    assert errors
    assert any(
        "SSHSIG is invalid" in error or "expected const" in error
        for error in errors
    ), errors


def test_full_capture_omission_and_digest_only_substitute_fail_closed(
    tmp_path, signing_profile
):
    artifact = _signed_capture(tmp_path / "state", signing_profile)
    artifact.pop("stable_host_facts")
    artifact["signed_binding"].pop("stable_host_facts")
    _reseal(artifact)
    assert validator.validate_aiml_artifact(artifact, now=NOW)
    digest_only = {
        "schema_version": HOST_CAPTURE_SCHEMA,
        "self_digest": "sha256:" + "2" * 64,
    }
    assert validator.validate_aiml_artifact(digest_only, now=NOW)


def test_semantic_rewrite_plus_self_digest_reseal_still_needs_host_signature(
    tmp_path, signing_profile
):
    artifact = _signed_capture(tmp_path / "state", signing_profile)
    artifact["stable_host_facts"]["node_name"] = "impostor"
    artifact["signed_binding"]["stable_host_facts"]["node_name"] = "impostor"
    derived = host_capture.derive_s2_5_recovery_host_identity(artifact)
    artifact["host_identity"] = derived
    artifact["signed_binding"]["host_identity"] = derived
    _reseal(artifact)
    errors = validator.validate_aiml_artifact(artifact, now=NOW)
    assert any("SSHSIG is invalid" in error for error in errors), errors


def test_recovery_controller_requires_full_capture_and_rejects_raw_host_api(
    tmp_path, signing_profile
):
    state_root = tmp_path / "state"
    capture = _signed_capture(state_root, signing_profile)
    state = lifecycle.S2_5RecoveryState(
        state_root=state_root, host_capture=capture, now=NOW
    )
    assert state.host_capture == capture
    assert state.host_capture is not state.host_capture
    assert state.host_capture_digest == capture["self_digest"]
    assert state.host_identity == capture["host_identity"]
    assert state.state_root == state_root.resolve(strict=False)
    assert not hasattr(state, "__dict__")
    assert weakref.ref(state)() is state
    assert state.admission_errors(state_root) == []
    with pytest.raises(TypeError):
        lifecycle.S2_5RecoveryState(  # type: ignore[call-arg]
            state_root=state_root, host_identity=capture["host_identity"], now=NOW
        )
    with pytest.raises(ValueError, match="host capture"):
        lifecycle.S2_5RecoveryState(
            state_root=state_root,
            host_capture={"self_digest": capture["self_digest"]},
            now=NOW,
        )


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
def test_controller_rejects_fully_resigned_capture_outside_checked_in_schema(
    tmp_path, signing_profile, mutate, needle
):
    state_root = tmp_path / "state"
    artifact = _signed_capture(state_root, signing_profile)
    mutate(artifact)
    mutate(artifact["signed_binding"])
    _resign(artifact, signing_profile[0])
    with pytest.raises(ValueError, match=needle):
        lifecycle.S2_5RecoveryState(
            state_root=state_root, host_capture=artifact, now=NOW
        )


def test_recovery_controller_rejects_cross_root_capture_and_binds_root_to_host(
    tmp_path, signing_profile
):
    state_root = tmp_path / "state-a"
    capture = _signed_capture(state_root, signing_profile)
    state = lifecycle.S2_5RecoveryState(
        state_root=state_root, host_capture=capture, now=NOW
    )
    expected = validator.canonical_digest({
        "schema_version": "s2_5_state_root_identity_v1",
        "stable_host_identity": capture["host_identity"],
        "canonical_path": str(state_root.resolve(strict=False)),
    })
    assert state.root_id == expected
    with pytest.raises(ValueError, match="different canonical state_root"):
        lifecycle.S2_5RecoveryState(
            state_root=tmp_path / "state-b", host_capture=capture, now=NOW
        )


def test_recovery_state_is_split_and_identically_reexported_from_lifecycle():
    lifecycle_path = (
        HELPERS / "agent_governance_s2_5_lifecycle.py"
    )
    split_path = HELPERS / "agent_governance_s2_5_recovery_state.py"
    assert split_path.is_file()
    assert not any(
        isinstance(node, ast.ClassDef) and node.name == "S2_5RecoveryState"
        for node in ast.parse(lifecycle_path.read_text(encoding="utf-8")).body
    )
    split = importlib.import_module("agent_governance_s2_5_recovery_state")
    assert lifecycle.S2_5RecoveryState is split.S2_5RecoveryState
    assert sum(1 for _ in lifecycle_path.open(encoding="utf-8")) <= 2000
    assert sum(1 for _ in split_path.open(encoding="utf-8")) <= 2000
