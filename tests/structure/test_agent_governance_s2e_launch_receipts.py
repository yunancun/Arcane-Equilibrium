from __future__ import annotations

from copy import deepcopy
import hashlib
import io
import json
import inspect
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
ML_ROOT = ROOT / "program_code" / "ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2e_launch_receipts as launch  # noqa: E402
import aiml_gate_receipt_s2e_anchor_floor as anchor_floor  # noqa: E402
import aiml_gate_receipt_s2e_dispatch as s2e_dispatch  # noqa: E402
import aiml_gate_receipt_s2e_external_evidence as s2e_external  # noqa: E402
import aiml_gate_receipt_s2e_launch as s2e  # noqa: E402
import aiml_gate_receipt_s2e_review as s2e_review  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402
import agent_governance_aiml_trusted_host as trusted_host  # noqa: E402
import agent_governance_command_capture_v2 as capture_v2  # noqa: E402
import agent_governance_terminal_receipt_external_sink as external_sink  # noqa: E402
import agent_governance_terminal_receipt_sink as terminal_sink  # noqa: E402


LAUNCH_CONTRACT_DIGEST = (
    "sha256:f8f8b1b9884aff421bf6ef52015837f2fd86447dbd67b4be5606d43afcffd2e0"
)
GENERATION_TASK_CONTRACT_DIGEST = (
    "sha256:fc295b09b791ba50a76dbf82223f14a4c26998cbf818b46e29c857e8e830e775"
)
NEXT_GENERATION_TASK_CONTRACT_DIGEST = "sha256:" + "4" * 64
# 兩台機器的 SSH host key 指紋(disposable fixture 值,形制與真實 keyscan 輸出相同)。
ANCHOR_HOST_FINGERPRINT = "SHA256:" + "A" * 43
REPLICA_HOST_FINGERPRINT = "SHA256:" + "B" * 43


def _install_disposable_s2e_trust_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, str, str]:
    private_key = tmp_path / "s2e-signer"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(private_key)],
        check=True,
    )
    public_parts = private_key.with_suffix(".pub").read_text(
        encoding="ascii"
    ).split()
    public_key = " ".join(public_parts[:2])
    fingerprint = trusted_host.ssh_public_key_fingerprint(public_key)
    assert fingerprint != trusted_host.EXPECTED_EXECUTION_SIGNER_FINGERPRINT
    trust_root_path = tmp_path / "s2e-receipt-trust-root.json"
    trust_root_path.write_text(
        json.dumps(
            {
                "schema_version": "s2e_receipt_signer_trust_root_v1",
                "signer_identity": s2e.S2E_RECEIPT_SIGNER_IDENTITY,
                "signature_namespace": s2e.S2E_RECEIPT_SIGNATURE_NAMESPACE,
                "algorithm": "SSH-ED25519",
                "key_generation": "independent_off_repo_ed25519_v1",
                "anchor": "fixed_off_repo_public_trust_root_v1",
                "public_key": public_key,
                "key_fingerprint": fingerprint,
                "governed_pytest_provider_profile_id": (
                    capture_v2.GOVERNED_PYTEST_PROVIDER_PROFILE_ID
                ),
                "governed_pytest_provider_lock_sha256": (
                    "sha256:"
                    + hashlib.sha256(
                        (
                            ROOT
                            / capture_v2.GOVERNED_PYTEST_PROVIDER_LOCK_PATH
                        ).read_bytes()
                    ).hexdigest()
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    trust_root_path.chmod(0o644)
    monkeypatch.setattr(s2e, "S2E_RECEIPT_TRUST_ROOT_PATH", trust_root_path)
    monkeypatch.setattr(s2e, "S2E_RECEIPT_TRUST_ROOT_OWNER_UID", os.getuid())
    return private_key, public_key, fingerprint


def _install_disposable_external_evidence_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    receipt_profile, receipt_errors = s2e.load_s2e_receipt_signer_trust_root()
    assert receipt_errors == []
    assert receipt_profile is not None

    def profile(
        name: str,
        identity: str,
        namespace: str,
        attestor_class: str,
        host_fingerprint: str | None = None,
    ) -> tuple[Path, dict[str, str]]:
        private, public, fingerprint = __import__("s2_5_testkit").mint_key(
            tmp_path, name
        )
        built = {
            "schema_version": name + "_trust_root_v1",
            "signer_identity": identity,
            "signature_namespace": namespace,
            "algorithm": "SSH-ED25519",
            "key_generation": "independent_off_repo_ed25519_v1",
            "anchor": "fixed_off_repo_public_trust_root_v1",
            "public_key": public,
            "key_fingerprint": fingerprint,
            "attestor_class": attestor_class,
        }
        if host_fingerprint is not None:
            built["host_fingerprint"] = host_fingerprint
        return private, built

    anchor_private, anchor_profile = profile(
        "s2e_durability_anchor",
        s2e_external.DURABILITY_ANCHOR_IDENTITY,
        s2e_external.DURABILITY_ANCHOR_NAMESPACE,
        "HOST_APPEND_ONLY_DURABILITY_ANCHOR_V1",
        host_fingerprint=ANCHOR_HOST_FINGERPRINT,
    )
    replica_private, replica_profile = profile(
        "s2e_offhost_replica",
        s2e_external.OFFHOST_REPLICA_IDENTITY,
        s2e_external.OFFHOST_REPLICA_NAMESPACE,
        "OFFHOST_APPEND_ONLY_REPLICA_READBACK_V1",
        host_fingerprint=REPLICA_HOST_FINGERPRINT,
    )
    registry_private, registry_profile = profile(
        "s2e_predecessor_registry",
        s2e_external.PREDECESSOR_REGISTRY_IDENTITY,
        s2e_external.PREDECESSOR_REGISTRY_NAMESPACE,
        "HOST_APPEND_ONLY_PREDECESSOR_REGISTRY_V1",
    )
    fingerprints = {
        receipt_profile["key_fingerprint"],
        anchor_profile["key_fingerprint"],
        replica_profile["key_fingerprint"],
        registry_profile["key_fingerprint"],
    }
    assert len(fingerprints) == 4
    monkeypatch.setattr(
        s2e_external,
        "_load_durability_anchor_trust_root",
        lambda: (anchor_profile, []),
    )
    monkeypatch.setattr(
        s2e_external,
        "_load_offhost_replica_trust_root",
        lambda: (replica_profile, []),
    )
    monkeypatch.setattr(
        s2e_external,
        "_load_predecessor_registry_trust_root",
        lambda: (registry_profile, []),
    )
    monkeypatch.setattr(
        s2e_external,
        "_load_s2e_receipt_signer_profile",
        lambda: (receipt_profile, []),
    )
    return {
        "anchor_private": anchor_private,
        "anchor_profile": anchor_profile,
        "replica_private": replica_private,
        "replica_profile": replica_profile,
        "registry_private": registry_private,
        "registry_profile": registry_profile,
    }


def test_code_owned_s2e_trust_root_loads_independent_disposable_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, public_key, fingerprint = _install_disposable_s2e_trust_root(
        tmp_path, monkeypatch
    )

    assert list(
        inspect.signature(validator.load_s2e_receipt_signer_trust_root).parameters
    ) == []
    profile, errors = validator.load_s2e_receipt_signer_trust_root()
    assert errors == []
    assert profile is not None
    assert profile["public_key"] == public_key
    assert profile["key_fingerprint"] == fingerprint
    assert profile["governed_pytest_provider_profile_id"] == (
        capture_v2.GOVERNED_PYTEST_PROVIDER_PROFILE_ID
    )
    assert profile["governed_pytest_provider_lock_sha256"] == (
        "sha256:"
        + hashlib.sha256(
            (ROOT / capture_v2.GOVERNED_PYTEST_PROVIDER_LOCK_PATH).read_bytes()
        ).hexdigest()
    )


def test_receipt_issuance_has_no_caller_controlled_time() -> None:
    assert "now" not in inspect.signature(
        validator.issue_s2e_launch_receipt
    ).parameters
    parser = launch._parser()
    action = next(
        item for item in parser._actions if item.dest == "action"
    )
    issue_parser = action.choices["issue"]
    assert all(item.dest != "now" for item in issue_parser._actions)


def test_authority_cli_parsers_reject_caller_controlled_time(
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser = launch._parser()
    action = next(item for item in parser._actions if item.dest == "action")
    for action_name in sorted(launch._HOST_CLOCK_ACTIONS):
        subparser = action.choices[action_name]
        argv = [action_name]
        for item in subparser._actions:
            if item.required:
                argv.extend([item.option_strings[0], "S2E-LW1"])
        argv.extend(["--now", "2026-08-02T12:00:00Z"])
        with pytest.raises(SystemExit):
            parser.parse_args(argv)
        assert "unrecognized arguments: --now" in capsys.readouterr().err


def test_s2e_dispatch_split_preserves_facade_abi_and_line_policy() -> None:
    exported = (
        "build_s2e_launch_consumption_bootstrap_authority_core",
        "build_s2e_launch_predecessor_authority",
        "build_s2e_predecessor_registry_request",
        "build_s2e_disposable_test_effect_chain",
        "canonical_launch_payload_bytes",
        "issue_s2e_launch_receipt",
        "launch_payload_digest",
        "load_s2e_receipt_signer_trust_root",
        "s2e_acceptance_review_bundle_digest",
        "s2e_acceptance_review_signed_bytes",
        "s2e_acceptance_review_worm_payload",
        "s2e_carrier_attestation_digest",
        "s2e_carrier_attested_core_digest",
        "s2e_carrier_signed_bytes",
        "s2e_carrier_verification_argv",
        "s2e_carrier_worm_payload",
        "s2e_launch_consumption_bootstrap_authority_digest",
        "s2e_launch_consumption_bootstrap_signed_bytes",
        "s2e_review_predicate_results",
        "s2e_review_source_blob_manifest",
        "s2e_review_test_argv",
        "validate_receipt_carrier_attestation",
        "validate_s2e_disposable_test_effect_chain",
        "validate_s2e_launch_acceptance_review_bundle",
        "validate_s2e_launch_consumption_bootstrap_authority",
        "validate_s2e_launch_genesis_receipt",
        "validate_s2e_launch_predecessor_authority",
        "validate_s2e_launch_transition",
        "validate_s2e_launch_transition_payload",
        "validate_s2e_launch_wave_receipt",
        "verify_receipt_carrier_attestation",
    )
    for name in exported:
        assert getattr(validator, name) is getattr(s2e, name)
    repository_policy_threshold = 2_000
    facade = ML_ROOT / "aiml_gate_receipt_validator.py"
    launch_leaf = ML_ROOT / "aiml_gate_receipt_s2e_launch.py"
    assert len(facade.read_text(encoding="utf-8").splitlines()) <= (
        repository_policy_threshold
    )
    assert len(launch_leaf.read_text(encoding="utf-8").splitlines()) <= (
        repository_policy_threshold
    )
    assert "def s2e_launch_artifact_errors(" not in launch_leaf.read_text(
        encoding="utf-8"
    )
    assert validator._s2e_launch_artifact_errors is (
        s2e_dispatch.s2e_launch_artifact_errors
    )
    assert "program_code/ml_training/aiml_gate_receipt_s2e_dispatch.py" in (
        s2e_review.S2E_REVIEW_BASE_PATHS
    )


def test_central_validator_delegates_s2e_branch_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = {"schema_version": "s2e_launch_genesis_receipt_v1"}
    captured: dict[str, object] = {}

    def dispatch(
        value: object,
        *,
        schema_version: str,
        repo_root: Path,
        now: object,
    ) -> list[str]:
        captured.update({
            "artifact": value,
            "schema_version": schema_version,
            "repo_root": repo_root,
            "now": now,
        })
        return ["S2E dispatch sentinel"]

    monkeypatch.setattr(validator, "_s2e_launch_artifact_errors", dispatch)
    monkeypatch.setattr(validator, "schema_subset_errors", lambda *args: [])
    errors = validator.validate_aiml_artifact(
        artifact, now="2026-08-02T12:00:00Z"
    )
    assert "S2E dispatch sentinel" in errors
    assert captured == {
        "artifact": artifact,
        "schema_version": artifact["schema_version"],
        "repo_root": validator.REPO_ROOT,
        "now": "2026-08-02T12:00:00Z",
    }


@pytest.mark.parametrize(
    ("schema_version", "expected"),
    (
        (
            "s2e_launch_acceptance_review_bundle_v1",
            "s2e acceptance review bundle EXTERNAL_VERIFICATION_PENDING",
        ),
        (
            "s2e_launch_consumption_bootstrap_authority_v1",
            "s2e consumption bootstrap authority EXTERNAL_VERIFICATION_PENDING",
        ),
    ),
)
def test_dispatch_preserves_fail_closed_context_boundaries(
    schema_version: str,
    expected: str,
) -> None:
    errors = s2e_dispatch.s2e_launch_artifact_errors(
        {},
        schema_version=schema_version,
        repo_root=ROOT,
        now="2026-08-02T12:00:00Z",
    )
    assert len(errors) == 1
    assert expected in errors[0]


class _NotFound(Exception):
    response = {"Error": {"Code": "404"}}


class _DisposableObjectLockS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], dict] = {}

    def head_object(self, *, Bucket, Key, ChecksumMode=None):
        try:
            value = self.objects[(Bucket, Key)]
        except KeyError as error:
            raise _NotFound from error
        return {
            "VersionId": value["VersionId"],
            "ChecksumSHA256": value["ChecksumSHA256"],
        }

    def put_object(
        self,
        *,
        Bucket,
        Key,
        Body,
        ChecksumSHA256,
        ObjectLockMode,
        ObjectLockRetainUntilDate,
    ):
        value = {
            "Body": bytes(Body),
            "ChecksumSHA256": ChecksumSHA256,
            "VersionId": "disposable-version-1",
            "Mode": ObjectLockMode,
            "RetainUntilDate": ObjectLockRetainUntilDate,
        }
        self.objects[(Bucket, Key)] = value
        return {
            "VersionId": value["VersionId"],
            "ChecksumSHA256": ChecksumSHA256,
        }

    def get_object(self, *, Bucket, Key, VersionId=None, ChecksumMode=None):
        value = self.objects[(Bucket, Key)]
        return {
            "Body": io.BytesIO(value["Body"]),
            "VersionId": value["VersionId"],
            "ChecksumSHA256": value["ChecksumSHA256"],
        }

    def get_object_retention(self, *, Bucket, Key, VersionId=None):
        value = self.objects[(Bucket, Key)]
        return {
            "Retention": {
                "Mode": value["Mode"],
                "RetainUntilDate": value["RetainUntilDate"],
            }
        }

    def get_object_lock_configuration(self, *, Bucket):
        return {"ObjectLockConfiguration": {"ObjectLockEnabled": "Enabled"}}


def _sign_sshsig(
    private_key: Path, message: bytes, *, namespace: str, directory: Path
) -> str:
    message_path = directory / f"signed-{hashlib.sha256(message).hexdigest()}.json"
    message_path.write_bytes(message)
    subprocess.run(
        [
            "ssh-keygen",
            "-Y",
            "sign",
            "-f",
            str(private_key),
            "-n",
            namespace,
            str(message_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    return message_path.with_suffix(".json.sig").read_text(encoding="ascii")


def _actual_capture(
    repo: Path,
    *,
    carrier_path: str,
    task_digest: str,
    context_digest: str,
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str] | None = None,
) -> dict:
    execution_task = {
        "node_id": "carrier_verification",
        "role": "E4",
        "native_agent": "E4-verifier",
        "node_class": "verification",
        "permission": "read_only",
        "requires": [],
        "path_scope": [carrier_path],
    }
    monkeypatch.setattr(
        capture_v2,
        "_bound_execution_task",
        lambda _context, _native, _node, _root: (
            execution_task,
            {"verification_scope": [carrier_path], "dirty_scope": []},
            [carrier_path],
        ),
    )
    record = capture_v2.capture_governed_command(
        native_agent="E4-verifier",
        node_id="carrier_verification",
        context_artifact={
            "artifact_digest": context_digest,
            "task_contract_digest": task_digest,
        },
        argv=argv or ["git", "rev-parse", "--is-inside-work-tree"],
        root=repo,
    )
    assert capture_v2.validate_governed_command_capture(
        record,
        expected_context_artifact_digest=context_digest,
        expected_task_contract_digest=task_digest,
        expected_source_head=_git(repo, "rev-parse", "HEAD"),
        root=repo,
    ) == []
    return record


ANCHOR_LOCATOR = "host:append-only-durability-anchor:s2e-aiml"
REPLICA_LOCATOR = "replica:offhost-append-only:nas-s2e-aiml"


def _offhost_replica_readback(
    artifact: dict,
    *,
    trust: dict[str, object],
    observed_at: datetime,
    directory: Path,
) -> dict:
    """第二把 key、第二個 host fingerprint 對同一個 head 的獨立回讀證言。"""

    readback = {
        "schema_version": s2e_external.OFFHOST_REPLICA_READBACK_SCHEMA,
        "replica_locator": artifact["offhost_replica_locator"],
        "replica_host_fingerprint": REPLICA_HOST_FINGERPRINT,
        "observed_anchor_locator": artifact["anchor_locator"],
        "replica_generation": artifact["anchor_generation"],
        "replica_previous_head_digest": artifact["previous_anchor_head_digest"],
        "replica_entry_digest": artifact["anchor_entry_digest"],
        "replica_head_digest": artifact["anchor_head_digest"],
        "observed_at": observed_at.isoformat(),
        "expires_at": (observed_at + timedelta(minutes=5)).isoformat(),
        "signer": {
            "role": "OFFHOST_REPLICA_READBACK_ATTESTOR",
            "identity": s2e_external.OFFHOST_REPLICA_IDENTITY,
            "namespace": s2e_external.OFFHOST_REPLICA_NAMESPACE,
            "key_generation": "independent_off_repo_ed25519_v1",
            "anchor": "fixed_off_repo_public_trust_root_v1",
            "key_fingerprint": trust["replica_profile"]["key_fingerprint"],
        },
    }
    signed = s2e_external.offhost_replica_readback_signed_bytes(readback)
    readback["signed_core_digest"] = "sha256:" + hashlib.sha256(signed).hexdigest()
    readback["signature"] = {
        "algorithm": "SSHSIG",
        "signed_digest": readback["signed_core_digest"],
        "signature": _sign_sshsig(
            trust["replica_private"],
            signed,
            namespace=s2e_external.OFFHOST_REPLICA_NAMESPACE,
            directory=directory,
        ),
    }
    return readback


def _durability_anchor_attestation(
    payload: dict,
    *,
    trust: dict[str, object],
    issued_at: datetime,
    directory: Path,
    generation: int = 1,
    previous_head: str | None = None,
) -> dict:
    """建一份 Tier 1 trusted-host durability anchor attestation(無外部服務)。"""

    artifact = {
        "schema_version": s2e_external.DURABILITY_ANCHOR_SCHEMA,
        "purpose": "ATTEST_S2E_APPEND_ONLY_DURABILITY_AND_OFFHOST_READBACK",
        "evidence_class": "PLATFORM_OR_EXTERNAL_ATTESTED",
        "anchor_class": "HOST_APPEND_ONLY_DURABILITY_ANCHOR_V1",
        "anchor_locator": ANCHOR_LOCATOR,
        "anchor_host_fingerprint": ANCHOR_HOST_FINGERPRINT,
        "launch_id": s2e_external.LAUNCH_ID,
        "terminal_payload_digest": terminal_sink.terminal_payload_digest(payload),
        "anchor_generation": generation,
        "previous_anchor_head_digest": previous_head,
        "anchor_entry_digest": "",
        "anchor_head_digest": "",
        "offhost_replica_locator": REPLICA_LOCATOR,
        "offhost_replica_readback": {},
        "observed_at": (issued_at + timedelta(seconds=10)).isoformat(),
        "expires_at": (issued_at + timedelta(minutes=5)).isoformat(),
        "signer": {
            "role": "DURABILITY_ANCHOR_ATTESTOR",
            "identity": s2e_external.DURABILITY_ANCHOR_IDENTITY,
            "namespace": s2e_external.DURABILITY_ANCHOR_NAMESPACE,
            "key_generation": "independent_off_repo_ed25519_v1",
            "anchor": "fixed_off_repo_public_trust_root_v1",
            "key_fingerprint": trust["anchor_profile"]["key_fingerprint"],
        },
    }
    artifact["anchor_entry_digest"] = s2e_external.durability_anchor_entry_digest(
        artifact
    )
    artifact["anchor_head_digest"] = s2e_external.durability_anchor_head_digest(
        artifact
    )
    artifact["offhost_replica_readback"] = _offhost_replica_readback(
        artifact,
        trust=trust,
        observed_at=issued_at + timedelta(seconds=5),
        directory=directory,
    )
    signed = s2e_external.durability_anchor_signed_bytes(artifact)
    artifact["signed_core_digest"] = "sha256:" + hashlib.sha256(signed).hexdigest()
    artifact["signature"] = {
        "algorithm": "SSHSIG",
        "signed_digest": artifact["signed_core_digest"],
        "signature": _sign_sshsig(
            trust["anchor_private"],
            signed,
            namespace=s2e_external.DURABILITY_ANCHOR_NAMESPACE,
            directory=directory,
        ),
    }
    artifact["attestation_digest"] = (
        s2e_external.durability_anchor_attestation_digest(artifact)
    )
    return artifact


def _anchor_immutable_readback(anchor: dict) -> dict:
    """carrier schema 早已宣告的 trusted-host adapter 投影。"""

    return {
        "adapter": "TRUSTED_HOST_SSHSIG_APPEND_ONLY_V1",
        "object_id": anchor["anchor_locator"],
        "version_id": str(anchor["anchor_generation"]),
        "readback_digest": anchor["anchor_head_digest"],
        "provider_attestation_digest": anchor["attestation_digest"],
    }


def _anchor_binding(anchor: dict) -> dict:
    return {
        "anchor_locator": anchor["anchor_locator"],
        "offhost_replica_locator": anchor["offhost_replica_locator"],
        "anchor_generation": anchor["anchor_generation"],
        "anchor_head_digest": anchor["anchor_head_digest"],
        "replica_head_digest": anchor["offhost_replica_readback"][
            "replica_head_digest"
        ],
        "anchor_attestation_digest": anchor["attestation_digest"],
    }


def _predecessor_registry_attestation(
    request: dict,
    *,
    trust: dict[str, object],
    issued_at: datetime,
    directory: Path,
) -> dict:
    artifact = {
        "schema_version": s2e_external.PREDECESSOR_REGISTRY_SCHEMA,
        "purpose": "ATTEST_S2E_PREDECESSOR_SINGLE_USE_GRANT",
        "evidence_class": "PLATFORM_OR_EXTERNAL_ATTESTED",
        "registry_class": "HOST_APPEND_ONLY_PREDECESSOR_REGISTRY_V1",
        "registry_locator": "registry:host-append-only:s2e",
        **{
            field: request[field]
            for field in (
                "launch_id",
                "slot_id",
                "predecessor_payload_digest",
                "successor_candidate_payload_digest",
                "successor_wave",
                "successor_source_head",
                "acceptance_review_bundle_digest",
                "prior_consumption_ledger_digest",
                "expected_consumption_entry_digest",
                "expected_result_ledger_digest",
            )
        },
        "decision": "GRANTED_ONCE",
        "conflicting_grant_absent": True,
        "registry_generation": 1,
        "previous_registry_head_digest": None,
        "registry_entry_digest": "",
        "registry_head_digest": "",
        "observed_at": issued_at.isoformat(),
        "expires_at": (issued_at + timedelta(minutes=5)).isoformat(),
        "signer": {
            "role": "PREDECESSOR_REGISTRY_ATTESTOR",
            "identity": s2e_external.PREDECESSOR_REGISTRY_IDENTITY,
            "namespace": s2e_external.PREDECESSOR_REGISTRY_NAMESPACE,
            "key_generation": "independent_off_repo_ed25519_v1",
            "anchor": "fixed_off_repo_public_trust_root_v1",
            "key_fingerprint": trust["registry_profile"]["key_fingerprint"],
        },
    }
    artifact["registry_entry_digest"] = (
        s2e_external.predecessor_registry_entry_digest(artifact)
    )
    artifact["registry_head_digest"] = (
        s2e_external.predecessor_registry_head_digest(artifact)
    )
    signed = s2e_external.predecessor_registry_signed_bytes(artifact)
    artifact["signed_core_digest"] = "sha256:" + hashlib.sha256(signed).hexdigest()
    artifact["signature"] = {
        "algorithm": "SSHSIG",
        "signed_digest": artifact["signed_core_digest"],
        "signature": _sign_sshsig(
            trust["registry_private"],
            signed,
            namespace=s2e_external.PREDECESSOR_REGISTRY_NAMESPACE,
            directory=directory,
        ),
    }
    artifact["attestation_digest"] = (
        s2e_external.predecessor_registry_attestation_digest(artifact)
    )
    return artifact


def _genesis_armed_floor() -> dict:
    """創世 floor:generation 0、無 head、無 bound receipt。只允許出現一次。"""

    floor = {
        "schema_version": anchor_floor.DURABILITY_ANCHOR_FLOOR_SCHEMA,
        "launch_id": s2e_external.LAUNCH_ID,
        "state": "GENESIS_ARMED",
        "anchor_locator": ANCHOR_LOCATOR,
        "offhost_replica_locator": REPLICA_LOCATOR,
        "floor_generation": 0,
        "floor_head_digest": None,
        "bound_receipt_payload_digest": None,
        "bound_acceptance_review_bundle_digest": None,
    }
    floor["floor_digest"] = anchor_floor.durability_anchor_floor_digest(floor)
    return floor


def _floor_bytes(floor: dict) -> bytes:
    return (
        json.dumps(floor, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _commit_floor(repo: Path, floor: dict, message: str) -> str:
    relative = anchor_floor.durability_anchor_floor_repo_path()
    target = repo / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_floor_bytes(floor))
    _git(repo, "add", relative)
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _commit(repo: Path, path: str, content: str, message: str) -> str:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git(repo, "add", path)
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _repo(tmp_path: Path) -> tuple[Path, str, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "s2e-launch@example.invalid")
    _git(repo, "config", "user.name", "S2E Launch Test")
    baseline = _commit(repo, "w0.txt", "W0\n", "W0 baseline")
    launch_carrier_files = {
        (
            "helper_scripts/maintenance_scripts/"
            "agent_governance_command_capture_v2.py"
        ): "# fixture governed capture blob\n",
        (
            "helper_scripts/maintenance_scripts/"
            "agent_governance_permissions.py"
        ): "# fixture command policy blob\n",
        "program_code/ml_training/aiml_gate_receipt_s2e_launch.py": (
            "# fixture launch validator blob\n"
        ),
        "program_code/ml_training/aiml_gate_receipt_s2e_review.py": (
            "# fixture launch review oracle blob\n"
        ),
        (
            "helper_scripts/maintenance_scripts/"
            "agent_governance_s2e_launch_receipts.py"
        ): "# fixture launch CLI blob\n",
        (
            "program_code/ml_training/schemas/aiml_gate_receipts/"
            "receipt_carrier_attestation_v1.schema.json"
        ): "{}\n",
        (
            "program_code/ml_training/schemas/aiml_gate_receipts/"
            "s2e_launch_acceptance_review_bundle_v1.schema.json"
        ): "{}\n",
        (
            "program_code/ml_training/schemas/aiml_gate_receipts/"
            "s2e_disposable_test_effect_chain_v1.schema.json"
        ): "{}\n",
        (
            "program_code/ml_training/schemas/aiml_gate_receipts/"
            "s2e_launch_genesis_receipt_v1.schema.json"
        ): "{}\n",
        (
            "program_code/ml_training/schemas/aiml_gate_receipts/"
            "s2e_launch_wave_receipt_v1.schema.json"
        ): "{}\n",
        "tests/structure/test_agent_governance_s2e_launch_receipts.py": (
            "def test_fixture_launch_review():\n"
            "    assert True\n"
        ),
        "schemas/launch.json": "{}\n",
    }
    representative_lw1_prefix_paths = (
        ".codex/schemas/s2_5_recovery_anchor_entry_v1.schema.json",
        ".codex/schemas/s2_5_recovery_lock_intent_v1.schema.json",
        ".codex/schemas/s2_5_recovery_store_intent_v1.schema.json",
        (
            "helper_scripts/maintenance_scripts/"
            "agent_governance_s2_5_recovery_anchor.py"
        ),
        (
            "helper_scripts/maintenance_scripts/"
            "agent_governance_s2_5_recovery_controller.py"
        ),
        (
            "helper_scripts/maintenance_scripts/"
            "agent_governance_s2_5_recovery_lock.py"
        ),
        (
            "helper_scripts/maintenance_scripts/"
            "agent_governance_s2_5_recovery_readback.py"
        ),
        (
            "helper_scripts/maintenance_scripts/"
            "agent_governance_s2_5_recovery_store.py"
        ),
        (
            "tests/structure/"
            "test_agent_governance_s2_5_recovery_anchor_private_guard.py"
        ),
        (
            "tests/structure/"
            "test_agent_governance_s2_5_recovery_lock_private_guard.py"
        ),
        (
            "tests/structure/"
            "test_agent_governance_s2_5_recovery_readback_socket_scan.py"
        ),
    )
    for relative_path in (
        *s2e_review.S2E_REVIEW_BASE_PATHS,
        *s2e_review.S2E_LW1_REVIEW_PATHS,
        *representative_lw1_prefix_paths,
    ):
        if relative_path in launch_carrier_files:
            continue
        if relative_path == anchor_floor.durability_anchor_floor_repo_path():
            content = _floor_bytes(_genesis_armed_floor()).decode("utf-8")
        elif relative_path == "TODO.md":
            content = (
                "| ID | Lane | Dependency | Work | Exit |\n"
                "|---|---|---|---|---|\n"
                "| `S2E.2b-2` | **ACTIVE / P0** | ready | LW1 | "
                "future publication may project `SOURCE_LANDED` |\n"
            )
        elif relative_path.endswith(".json"):
            content = "{}\n"
        elif Path(relative_path).name.startswith("test_"):
            content = "def test_fixture_lw1_evidence():\n    assert True\n"
        else:
            content = "# fixture LW1 Git blob\n"
        launch_carrier_files[relative_path] = content
    for relative_path, content in launch_carrier_files.items():
        target = repo / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    _git(repo, "add", *sorted(launch_carrier_files))
    _git(repo, "commit", "-m", "schema carrier")
    carrier = _git(repo, "rev-parse", "HEAD")
    lw1 = _commit(repo, "lw1.txt", "LW1\n", "LW1 checkpoint")
    return repo, baseline, carrier, lw1


def _payload_digest(receipt: dict) -> str:
    return validator.canonical_digest(
        {key: value for key, value in receipt.items() if key != "payload_digest"}
    )


def _json_file(tmp_path: Path, name: str, value: object) -> Path:
    path = tmp_path / name
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return path


def _carrier_case(tmp_path: Path) -> tuple[Path, dict, dict, dict, datetime]:
    repo, baseline, schema_carrier, _ = _repo(tmp_path)
    genesis = s2e._build_genesis_candidate_payload(
        repo_root=repo,
        baseline_head=baseline,
        schema_carrier_head=schema_carrier,
        launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
        generation_task_contract_digest=GENERATION_TASK_CONTRACT_DIGEST,
    )
    carrier_path = "receipts/S2E-W0-genesis.json"
    target = repo / carrier_path
    target.parent.mkdir(parents=True)
    target.write_bytes(validator.canonical_launch_payload_bytes(genesis))
    _git(repo, "add", carrier_path)
    _git(repo, "commit", "-m", "carry W0 genesis")
    carrier_head = _git(repo, "rev-parse", "HEAD")
    carrier_tree = _git(repo, "rev-parse", "HEAD^{tree}")
    carrier_blob = _git(repo, "rev-parse", f"HEAD:{carrier_path}")
    issued_at = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
    capture_identity = {
        "schema_version": "governed_capture_identity_v1",
        "record_digest": "sha256:" + "1" * 64,
        "context_artifact_digest": "sha256:" + "2" * 64,
        "task_contract_digest": NEXT_GENERATION_TASK_CONTRACT_DIGEST,
        "node_id": "carrier_verification",
        "role_id": "E4",
        "native_agent": "E4-verifier",
        "permission": "read_only",
    }
    attestation = {
        "schema_version": "receipt_carrier_attestation_v1",
        "payload_schema_version": genesis["schema_version"],
        "payload_digest": genesis["payload_digest"],
        "launch_contract_digest": genesis["launch_contract_digest"],
        "payload_generation_task_contract_digest": genesis[
            "generation_task_contract_digest"
        ],
        "verification_task_contract_digest": NEXT_GENERATION_TASK_CONTRACT_DIGEST,
        "schema_carrier_head": schema_carrier,
        "schema_carrier_tree": _git(
            repo, "rev-parse", f"{schema_carrier}^{{tree}}"
        ),
        "carrier_head": carrier_head,
        "carrier_tree": carrier_tree,
        "carrier_path": carrier_path,
        "carrier_blob": carrier_blob,
        "carrier_raw_digest": "sha256:"
        + __import__("hashlib").sha256(
            validator.canonical_launch_payload_bytes(genesis)
        ).hexdigest(),
        "governed_capture_identity": capture_identity,
        "issued_at": issued_at.isoformat().replace("+00:00", "Z"),
        "expires_at": (issued_at + timedelta(minutes=5)).isoformat().replace(
            "+00:00", "Z"
        ),
        "signer": {
            "role": "R4",
            "identity": s2e.S2E_RECEIPT_SIGNER_IDENTITY,
            "namespace": s2e.S2E_RECEIPT_SIGNATURE_NAMESPACE,
            "key_generation": "independent_off_repo_ed25519_v1",
            "anchor": "fixed_off_repo_public_trust_root_v1",
            "key_fingerprint": "SHA256:" + "A" * 43,
        },
        "immutable_readback": {
            "adapter": "EXTERNAL_WORM_V1",
            "object_id": "s2e/w0/genesis",
            "version_id": "v1",
            "readback_digest": "sha256:" + "3" * 64,
            "provider_attestation_digest": "sha256:" + "4" * 64,
        },
    }
    attestation["attested_core_digest"] = (
        validator.s2e_carrier_attested_core_digest(attestation)
    )
    attestation["signature"] = {
        "algorithm": "SSHSIG",
        "signed_digest": attestation["attested_core_digest"],
        "signature": "-----BEGIN SSH SIGNATURE-----\nQUJDRA==\n-----END SSH SIGNATURE-----",
    }
    attestation["attestation_digest"] = (
        validator.s2e_carrier_attestation_digest(attestation)
    )
    return repo, genesis, attestation, capture_identity, issued_at


def _carrier_errors(
    repo: Path,
    genesis: dict,
    attestation: dict,
    capture_identity: dict,
    now: datetime,
    *,
    consumed: set[str] | None = None,
) -> list[str]:
    return validator.validate_receipt_carrier_attestation(
        attestation,
        payload_receipt=genesis,
        repo_root=repo,
        now=now,
        consumed_attestation_digests=consumed or set(),
    )


def _reseal_carrier(attestation: dict) -> None:
    attestation["attested_core_digest"] = (
        validator.s2e_carrier_attested_core_digest(attestation)
    )
    attestation["signature"]["signed_digest"] = attestation[
        "attested_core_digest"
    ]
    attestation["attestation_digest"] = (
        validator.s2e_carrier_attestation_digest(attestation)
    )


def test_carrier_attestation_binds_exact_payload_blob_and_governed_capture(
    tmp_path: Path,
) -> None:
    repo, genesis, attestation, capture_identity, issued_at = _carrier_case(tmp_path)
    assert _carrier_errors(
        repo,
        genesis,
        attestation,
        capture_identity,
        issued_at + timedelta(minutes=1),
    ) == [
        "carrier attestation EXTERNAL_VERIFICATION_PENDING: trusted-host governed "
        "capture, independent SSHSIG, and immutable readback evidence are required"
    ]


def test_launch_payload_tampering_unknown_fields_and_secret_input_fail_closed(
    tmp_path: Path,
) -> None:
    repo, baseline, carrier, lw1 = _repo(tmp_path)
    genesis = s2e._build_genesis_candidate_payload(
        repo_root=repo,
        baseline_head=baseline,
        schema_carrier_head=carrier,
        launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
        generation_task_contract_digest=GENERATION_TASK_CONTRACT_DIGEST,
    )
    wave = s2e._build_wave_candidate_payload(
        repo_root=repo,
        wave="S2E-LW1",
        source_head=lw1,
        schema_carrier_head=carrier,
        predecessor_receipt=genesis,
        launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
        generation_task_contract_digest=GENERATION_TASK_CONTRACT_DIGEST,
    )

    non_null_genesis = dict(genesis)
    non_null_genesis["predecessor"] = "sha256:" + "9" * 64
    non_null_genesis["payload_digest"] = _payload_digest(non_null_genesis)
    assert validator.validate_s2e_launch_genesis_receipt(
        non_null_genesis, repo_root=repo
    )

    cross_tree = dict(wave)
    cross_tree["source_tree"] = genesis["baseline_tree"]
    cross_tree["payload_digest"] = _payload_digest(cross_tree)
    assert any(
        "tree does not match" in error
        for error in validator.validate_s2e_launch_wave_receipt(
            cross_tree, repo_root=repo
        )
    )

    noncanonical = dict(wave)
    noncanonical["payload_digest"] = "sha256:" + "8" * 64
    assert any(
        "not canonical" in error
        for error in validator.validate_s2e_launch_wave_receipt(
            noncanonical, repo_root=repo
        )
    )

    for forbidden in ("actor", "verifier", "nonce"):
        caller_authority = dict(wave)
        caller_authority[forbidden] = "caller-chosen"
        assert validator.validate_s2e_launch_wave_receipt(
            caller_authority, repo_root=repo
        )

    secret_like = dict(wave)
    secret_like["access_token"] = "github_pat_AAAAAAAAAAAAAAAAAAAA"
    assert validator.validate_s2e_launch_wave_receipt(
        secret_like, repo_root=repo
    )


def test_carrier_stale_cross_git_replay_and_identity_substitution_fail_closed(
    tmp_path: Path,
) -> None:
    repo, genesis, attestation, capture_identity, issued_at = _carrier_case(tmp_path)

    stale = _carrier_errors(
        repo,
        genesis,
        attestation,
        capture_identity,
        issued_at + timedelta(minutes=6),
    )
    assert any("stale" in error for error in stale)

    replay = _carrier_errors(
        repo,
        genesis,
        attestation,
        capture_identity,
        issued_at + timedelta(minutes=1),
        consumed={attestation["attestation_digest"]},
    )
    assert any("already consumed" in error for error in replay)

    wrong_tree = json.loads(json.dumps(attestation))
    wrong_tree["carrier_tree"] = genesis["baseline_tree"]
    _reseal_carrier(wrong_tree)
    assert any(
        "tree does not match" in error
        for error in _carrier_errors(
            repo,
            genesis,
            wrong_tree,
            capture_identity,
            issued_at + timedelta(minutes=1),
        )
    )

    wrong_blob = json.loads(json.dumps(attestation))
    wrong_blob["carrier_blob"] = "0" * 40
    _reseal_carrier(wrong_blob)
    assert any(
        "blob differs" in error
        for error in _carrier_errors(
            repo,
            genesis,
            wrong_blob,
            capture_identity,
            issued_at + timedelta(minutes=1),
        )
    )

    substituted_identity = json.loads(json.dumps(attestation))
    substituted_identity["governed_capture_identity"]["role_id"] = "caller"
    _reseal_carrier(substituted_identity)
    assert any(
        "EXTERNAL_VERIFICATION_PENDING" in error
        for error in _carrier_errors(
            repo,
            genesis,
            substituted_identity,
            capture_identity,
            issued_at + timedelta(minutes=1),
        )
    )

    unknown_actor = json.loads(json.dumps(attestation))
    unknown_actor["actor"] = "caller-chosen"
    assert _carrier_errors(
        repo,
        genesis,
        unknown_actor,
        capture_identity,
        issued_at + timedelta(minutes=1),
    )

    secret_like = json.loads(json.dumps(attestation))
    secret_like["immutable_readback"]["object_id"] = (
        "password=supersecretvalue123"
    )
    _reseal_carrier(secret_like)
    assert any(
        "secret-like" in error
        for error in _carrier_errors(
            repo,
            genesis,
            secret_like,
            capture_identity,
            issued_at + timedelta(minutes=1),
        )
    )


def test_carrier_rejects_duplicate_key_secret_hidden_by_json_parsing(
    tmp_path: Path,
) -> None:
    repo, genesis, attestation, capture_identity, issued_at = _carrier_case(tmp_path)
    canonical = validator.canonical_launch_payload_bytes(genesis)
    exploit = (
        b'{"launch_id":"password=supersecretvalue123",'
        + canonical.removeprefix(b"{")
    )
    carrier_path = attestation["carrier_path"]
    (repo / carrier_path).write_bytes(exploit)
    _git(repo, "add", carrier_path)
    _git(repo, "commit", "-m", "duplicate-key carrier exploit")
    attestation["carrier_head"] = _git(repo, "rev-parse", "HEAD")
    attestation["carrier_tree"] = _git(repo, "rev-parse", "HEAD^{tree}")
    attestation["carrier_blob"] = _git(repo, "rev-parse", f"HEAD:{carrier_path}")
    _reseal_carrier(attestation)

    errors = _carrier_errors(
        repo,
        genesis,
        attestation,
        capture_identity,
        issued_at + timedelta(minutes=1),
    )
    assert any(
        "duplicate JSON key" in error or "secret-like raw carrier" in error
        for error in errors
    )


def test_cli_recognizes_carrier_but_cannot_self_authenticate_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, genesis, attestation, _, issued_at = _carrier_case(tmp_path)
    receipt_path = tmp_path / "carrier-attestation.json"
    payload_path = tmp_path / "genesis-payload.json"
    receipt_path.write_text(json.dumps(attestation), encoding="utf-8")
    payload_path.write_text(json.dumps(genesis), encoding="utf-8")
    monkeypatch.setattr(
        launch,
        "_sample_utc_host_clock",
        lambda: (issued_at + timedelta(minutes=1)).isoformat(),
    )

    exit_code = launch.main([
        "validate",
        "--repo-root",
        str(repo),
        "--receipt",
        str(receipt_path),
        "--payload-receipt",
        str(payload_path),
    ])

    assert exit_code == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "FAIL"
    assert any(
        "EXTERNAL_VERIFICATION_PENDING" in error
        for error in result["errors"]
    )


def test_carrier_validator_has_no_bool_callback_authentication_channel(
    tmp_path: Path,
) -> None:
    repo, genesis, attestation, _, issued_at = _carrier_case(tmp_path)
    parameters = inspect.signature(
        validator.validate_receipt_carrier_attestation
    ).parameters
    assert "signature_verifier" not in parameters
    assert "governed_capture_identity_verifier" not in parameters
    assert "immutable_readback_verifier" not in parameters

    with pytest.raises(TypeError):
        validator.validate_receipt_carrier_attestation(
            attestation,
            payload_receipt=genesis,
            repo_root=repo,
            now=issued_at + timedelta(minutes=1),
            signature_verifier=lambda _: True,
        )


def test_fake_trusted_host_objects_return_typed_pending_not_pass(
    tmp_path: Path,
) -> None:
    repo, genesis, attestation, _, issued_at = _carrier_case(tmp_path)
    result = validator.verify_receipt_carrier_attestation(
        attestation,
        payload_receipt=genesis,
        repo_root=repo,
        now=issued_at + timedelta(minutes=1),
        governed_capture_record={"schema_version": "command_capture_v2"},
        durability_anchor_attestation={"schema_version": "caller-shaped"},
    )

    assert result["schema_version"] == "receipt_carrier_verification_result_v1"
    assert result["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert result["independent_signing_key_available"] is False
    assert result["verification_result_digest"] == validator.canonical_digest({
        key: value
        for key, value in result.items()
        if key != "verification_result_digest"
    })
    assert any("governed command capture" in error for error in result["errors"])
    assert any("durability anchor" in error for error in result["errors"])


def test_missing_trusted_host_objects_return_typed_pending_not_exception(
    tmp_path: Path,
) -> None:
    repo, genesis, attestation, _, issued_at = _carrier_case(tmp_path)

    result = validator.verify_receipt_carrier_attestation(
        attestation,
        payload_receipt=genesis,
        repo_root=repo,
        now=issued_at + timedelta(minutes=1),
        governed_capture_record=None,
        durability_anchor_attestation=None,
    )

    assert result["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert result["durability_anchor_head_digest"] is None
    assert result["durability_anchor_attestation_digest"] is None
    assert result["errors"]


def test_independent_key_capture_and_worm_produce_verified_carrier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_key, _, fingerprint = _install_disposable_s2e_trust_root(
        tmp_path, monkeypatch
    )
    external_trust = _install_disposable_external_evidence_roots(
        tmp_path, monkeypatch
    )
    repo, genesis, attestation, _, issued_at = _carrier_case(tmp_path)
    task_digest = NEXT_GENERATION_TASK_CONTRACT_DIGEST
    context_digest = "sha256:" + "2" * 64
    capture = _actual_capture(
        repo,
        carrier_path=attestation["carrier_path"],
        task_digest=task_digest,
        context_digest=context_digest,
        monkeypatch=monkeypatch,
        argv=validator.s2e_carrier_verification_argv(attestation),
    )
    attestation["verification_task_contract_digest"] = task_digest
    attestation["governed_capture_identity"] = {
        "schema_version": "governed_capture_identity_v1",
        "record_digest": capture["record_digest"],
        "context_artifact_digest": capture["context_artifact_digest"],
        "task_contract_digest": capture["task_contract_digest"],
        "node_id": capture["node_id"],
        "role_id": capture["role_id"],
        "native_agent": capture["native_agent"],
        "permission": capture["permission"],
    }
    attestation["signer"] = {
        "role": "S2E_SIGNER",
        "identity": s2e.S2E_RECEIPT_SIGNER_IDENTITY,
        "namespace": s2e.S2E_RECEIPT_SIGNATURE_NAMESPACE,
        "key_generation": "independent_off_repo_ed25519_v1",
        "anchor": "fixed_off_repo_public_trust_root_v1",
        "key_fingerprint": fingerprint,
    }
    worm_payload = validator.s2e_carrier_worm_payload(
        attestation, payload_receipt=genesis
    )
    anchor_attestation = _durability_anchor_attestation(
        worm_payload,
        trust=external_trust,
        issued_at=issued_at,
        directory=tmp_path,
    )
    attestation["immutable_readback"] = _anchor_immutable_readback(
        anchor_attestation
    )
    _reseal_carrier(attestation)
    attestation["signature"]["signature"] = _sign_sshsig(
        private_key,
        validator.s2e_carrier_signed_bytes(attestation),
        namespace=s2e.S2E_RECEIPT_SIGNATURE_NAMESPACE,
        directory=tmp_path,
    )
    attestation["attestation_digest"] = (
        validator.s2e_carrier_attestation_digest(attestation)
    )

    verified = validator.verify_receipt_carrier_attestation(
        attestation,
        payload_receipt=genesis,
        repo_root=repo,
        now=issued_at + timedelta(minutes=1),
        governed_capture_record=capture,
        durability_anchor_attestation=anchor_attestation,
    )

    assert fingerprint != trusted_host.EXPECTED_EXECUTION_SIGNER_FINGERPRINT
    assert attestation["signer"]["role"] != capture["role_id"]
    assert verified["status"] == "VERIFIED"
    assert verified["independent_signing_key_available"] is True
    assert verified["errors"] == []


def test_candidates_remain_pending_and_fake_review_bundle_cannot_issue(
    tmp_path: Path,
) -> None:
    repo, baseline, carrier, _ = _repo(tmp_path)
    candidate = s2e._build_genesis_candidate_payload(
        repo_root=repo,
        baseline_head=baseline,
        schema_carrier_head=carrier,
        launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
        generation_task_contract_digest=GENERATION_TASK_CONTRACT_DIGEST,
    )

    assert candidate["checkpoint_status"] == "PENDING_REVIEW"
    result = validator.issue_s2e_launch_receipt(
        candidate,
        acceptance_review_bundle={"schema_version": "caller-shaped"},
        repo_root=repo,
    )

    assert result["schema_version"] == "launch_receipt_issuance_result_v1"
    assert result["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert result["issued_receipt"] is None
    assert result["candidate_payload_digest"] == candidate["payload_digest"]
    assert result["issuance_result_digest"] == validator.canonical_digest({
        key: value
        for key, value in result.items()
        if key != "issuance_result_digest"
    })
    assert any("acceptance review bundle" in error for error in result["errors"])


def test_acceptance_review_rejects_generic_command_and_cross_generation_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, baseline, carrier, _ = _repo(tmp_path)
    candidate = s2e._build_genesis_candidate_payload(
        repo_root=repo,
        baseline_head=baseline,
        schema_carrier_head=carrier,
        launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
        generation_task_contract_digest=GENERATION_TASK_CONTRACT_DIGEST,
    )
    _git(repo, "checkout", "--detach", carrier)
    generic = _actual_capture(
        repo,
        carrier_path="schemas/launch.json",
        task_digest=candidate["generation_task_contract_digest"],
        context_digest="sha256:" + "5" * 64,
        monkeypatch=monkeypatch,
    )
    with pytest.raises(ValueError, match="code-owned S2E test profile"):
        validator.build_s2e_disposable_test_effect_chain(
            generic,
            candidate=candidate,
            repo_root=repo,
            observed_at="2026-07-30T12:00:01Z",
        )

    cross_generation = _actual_capture(
        repo,
        carrier_path="schemas/launch.json",
        task_digest=NEXT_GENERATION_TASK_CONTRACT_DIGEST,
        context_digest="sha256:" + "7" * 64,
        monkeypatch=monkeypatch,
        argv=validator.s2e_review_test_argv(candidate, repo_root=repo),
    )
    with pytest.raises(ValueError, match="task generation differs"):
        validator.build_s2e_disposable_test_effect_chain(
            cross_generation,
            candidate=candidate,
            repo_root=repo,
            observed_at="2026-07-30T12:00:01Z",
        )


def _issued_genesis_authority_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict:
    private_key, _, fingerprint = _install_disposable_s2e_trust_root(
        tmp_path, monkeypatch
    )
    external_trust = _install_disposable_external_evidence_roots(
        tmp_path, monkeypatch
    )
    repo, baseline, schema_carrier, _ = _repo(tmp_path)
    _git(repo, "checkout", "--detach", schema_carrier)
    candidate = launch.build_genesis_candidate(
        repo_root=repo,
        baseline_head=baseline,
        schema_carrier_head=schema_carrier,
        launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
        generation_task_contract_digest=GENERATION_TASK_CONTRACT_DIGEST,
    )
    issued_at = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
    review_capture = _actual_capture(
        repo,
        carrier_path="schemas/launch.json",
        task_digest=candidate["generation_task_contract_digest"],
        context_digest="sha256:" + "6" * 64,
        monkeypatch=monkeypatch,
        argv=validator.s2e_review_test_argv(candidate, repo_root=repo),
    )
    disposable_chain = validator.build_s2e_disposable_test_effect_chain(
        review_capture,
        candidate=candidate,
        repo_root=repo,
        observed_at=review_capture["completed_at"],
    )
    capture_identity = {
        "schema_version": "governed_capture_identity_v1",
        "record_digest": review_capture["record_digest"],
        "context_artifact_digest": review_capture["context_artifact_digest"],
        "task_contract_digest": review_capture["task_contract_digest"],
        "node_id": review_capture["node_id"],
        "role_id": review_capture["role_id"],
        "native_agent": review_capture["native_agent"],
        "permission": review_capture["permission"],
    }
    review_bundle = {
        "schema_version": "s2e_launch_acceptance_review_bundle_v1",
        "candidate_payload_digest": candidate["payload_digest"],
        "launch_id": candidate["launch_id"],
        "wave": candidate["wave"],
        "wave_exit_id": candidate["wave_exit_id"],
        "reviewed_source_head": candidate["schema_carrier_head"],
        "reviewed_source_tree": candidate["schema_carrier_tree"],
        "generation_task_contract_digest": candidate[
            "generation_task_contract_digest"
        ],
        "source_blob_manifest": validator.s2e_review_source_blob_manifest(
            candidate, repo_root=repo
        ),
        "predicate_results": validator.s2e_review_predicate_results(
            candidate,
            source_blob_manifest=validator.s2e_review_source_blob_manifest(
                candidate, repo_root=repo
            ),
            governed_capture_record=review_capture,
            disposable_test_effect_chains=[disposable_chain],
            predecessor_chain=[],
            repo_root=repo,
        ),
        "consumed_predecessor_digests": [],
        "disposable_test_effect_chain_digests": [
            disposable_chain["chain_digest"]
        ],
        "governed_capture_identity": capture_identity,
        "governed_capture_record_digest": review_capture["record_digest"],
        "reviewer_identity": {
            "node_id": review_capture["node_id"],
            "role_id": review_capture["role_id"],
            "native_agent": review_capture["native_agent"],
            "permission": review_capture["permission"],
        },
        "issued_at": issued_at.isoformat(),
        "expires_at": (issued_at + timedelta(minutes=5)).isoformat(),
        "signer": {
            "role": "S2E_SIGNER",
            "identity": s2e.S2E_RECEIPT_SIGNER_IDENTITY,
            "namespace": s2e.S2E_RECEIPT_SIGNATURE_NAMESPACE,
            "key_generation": "independent_off_repo_ed25519_v1",
            "anchor": "fixed_off_repo_public_trust_root_v1",
            "key_fingerprint": fingerprint,
        },
        "durability_anchor_binding": None,
    }
    signed_bytes = validator.s2e_acceptance_review_signed_bytes(review_bundle)
    review_bundle["signed_core_digest"] = "sha256:" + hashlib.sha256(
        signed_bytes
    ).hexdigest()
    review_bundle["signature"] = {
        "algorithm": "SSHSIG",
        "signed_digest": review_bundle["signed_core_digest"],
        "signature": _sign_sshsig(
            private_key,
            signed_bytes,
            namespace=s2e.S2E_RECEIPT_SIGNATURE_NAMESPACE,
            directory=tmp_path,
        ),
    }
    review_anchor_attestation = _durability_anchor_attestation(
        validator.s2e_acceptance_review_worm_payload(review_bundle),
        trust=external_trust,
        issued_at=issued_at,
        directory=tmp_path,
    )
    review_bundle["durability_anchor_binding"] = _anchor_binding(
        review_anchor_attestation
    )
    review_bundle["bundle_digest"] = (
        validator.s2e_acceptance_review_bundle_digest(review_bundle)
    )
    monkeypatch.setattr(
        s2e,
        "_trusted_issuance_now",
        lambda: issued_at + timedelta(minutes=1),
    )
    issuance = validator.issue_s2e_launch_receipt(
        candidate,
        acceptance_review_bundle=review_bundle,
        repo_root=repo,
        governed_capture_record=review_capture,
        disposable_test_effect_chains=[disposable_chain],
        durability_anchor_attestation=review_anchor_attestation,
    )
    assert issuance["status"] == "ISSUED"
    issued = issuance["issued_receipt"]
    assert issued is not None
    # issuance 只投影下一份 floor,永遠不寫檔;由 operator/E1 在同一個 PR 內 commit。
    advanced_floor = issuance["next_durability_anchor_floor"]
    assert advanced_floor == {
        "schema_version": anchor_floor.DURABILITY_ANCHOR_FLOOR_SCHEMA,
        "launch_id": s2e_external.LAUNCH_ID,
        "state": "ADVANCED",
        "anchor_locator": ANCHOR_LOCATOR,
        "offhost_replica_locator": REPLICA_LOCATOR,
        "floor_generation": review_anchor_attestation["anchor_generation"],
        "floor_head_digest": review_anchor_attestation["anchor_head_digest"],
        "bound_receipt_payload_digest": issued["payload_digest"],
        "bound_acceptance_review_bundle_digest": review_bundle["bundle_digest"],
        "floor_digest": anchor_floor.durability_anchor_floor_digest({
            key: value
            for key, value in advanced_floor.items()
            if key != "floor_digest"
        }),
    }
    _commit_floor(repo, advanced_floor, "advance durability anchor floor to W0")

    carrier_path = "receipts/S2E-W0-genesis-ready.json"
    target = repo / carrier_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(validator.canonical_launch_payload_bytes(issued))
    _git(repo, "add", carrier_path)
    _git(repo, "commit", "-m", "carry issued W0 genesis")
    carrier_head = _git(repo, "rev-parse", "HEAD")
    carrier_tree = _git(repo, "rev-parse", "HEAD^{tree}")
    carrier_blob = _git(repo, "rev-parse", f"HEAD:{carrier_path}")
    carrier_task_digest = "sha256:" + "8" * 64
    carrier_attestation = {
        "schema_version": "receipt_carrier_attestation_v1",
        "payload_schema_version": issued["schema_version"],
        "payload_digest": issued["payload_digest"],
        "launch_contract_digest": issued["launch_contract_digest"],
        "payload_generation_task_contract_digest": issued[
            "generation_task_contract_digest"
        ],
        "verification_task_contract_digest": carrier_task_digest,
        "schema_carrier_head": issued["schema_carrier_head"],
        "schema_carrier_tree": issued["schema_carrier_tree"],
        "carrier_head": carrier_head,
        "carrier_tree": carrier_tree,
        "carrier_path": carrier_path,
        "carrier_blob": carrier_blob,
        "carrier_raw_digest": "sha256:"
        + hashlib.sha256(
            validator.canonical_launch_payload_bytes(issued)
        ).hexdigest(),
        "governed_capture_identity": {
            "schema_version": "governed_capture_identity_v1",
            "record_digest": "sha256:" + "1" * 64,
            "context_artifact_digest": "sha256:" + "2" * 64,
            "task_contract_digest": carrier_task_digest,
            "node_id": "carrier_verification",
            "role_id": "E4",
            "native_agent": "E4-verifier",
            "permission": "read_only",
        },
        "issued_at": (issued_at + timedelta(minutes=2)).isoformat(),
        "expires_at": (issued_at + timedelta(minutes=5)).isoformat(),
        "signer": {
            "role": "S2E_SIGNER",
            "identity": s2e.S2E_RECEIPT_SIGNER_IDENTITY,
            "namespace": s2e.S2E_RECEIPT_SIGNATURE_NAMESPACE,
            "key_generation": "independent_off_repo_ed25519_v1",
            "anchor": "fixed_off_repo_public_trust_root_v1",
            "key_fingerprint": fingerprint,
        },
        "immutable_readback": {
            "adapter": "EXTERNAL_WORM_V1",
            "object_id": "records/" + "0" * 64 + ".record",
            "version_id": "pending",
            "readback_digest": "sha256:" + "0" * 64,
            "provider_attestation_digest": "sha256:" + "0" * 64,
        },
    }
    carrier_attestation["attested_core_digest"] = (
        validator.s2e_carrier_attested_core_digest(carrier_attestation)
    )
    carrier_attestation["signature"] = {
        "algorithm": "SSHSIG",
        "signed_digest": carrier_attestation["attested_core_digest"],
        "signature": (
            "-----BEGIN SSH SIGNATURE-----\n"
            "QUJDRA==\n"
            "-----END SSH SIGNATURE-----"
        ),
    }
    carrier_attestation["attestation_digest"] = (
        validator.s2e_carrier_attestation_digest(carrier_attestation)
    )
    carrier_capture = _actual_capture(
        repo,
        carrier_path=carrier_path,
        task_digest=carrier_task_digest,
        context_digest="sha256:" + "9" * 64,
        monkeypatch=monkeypatch,
        argv=validator.s2e_carrier_verification_argv(carrier_attestation),
    )
    carrier_attestation["governed_capture_identity"] = {
        "schema_version": "governed_capture_identity_v1",
        "record_digest": carrier_capture["record_digest"],
        "context_artifact_digest": carrier_capture["context_artifact_digest"],
        "task_contract_digest": carrier_capture["task_contract_digest"],
        "node_id": carrier_capture["node_id"],
        "role_id": carrier_capture["role_id"],
        "native_agent": carrier_capture["native_agent"],
        "permission": carrier_capture["permission"],
    }
    carrier_anchor_attestation = _durability_anchor_attestation(
        validator.s2e_carrier_worm_payload(
            carrier_attestation, payload_receipt=issued
        ),
        trust=external_trust,
        issued_at=issued_at + timedelta(minutes=2),
        directory=tmp_path,
        generation=2,
        previous_head=review_anchor_attestation["anchor_head_digest"],
    )
    carrier_attestation["immutable_readback"] = _anchor_immutable_readback(
        carrier_anchor_attestation
    )
    _reseal_carrier(carrier_attestation)
    carrier_attestation["signature"]["signature"] = _sign_sshsig(
        private_key,
        validator.s2e_carrier_signed_bytes(carrier_attestation),
        namespace=s2e.S2E_RECEIPT_SIGNATURE_NAMESPACE,
        directory=tmp_path,
    )
    carrier_attestation["attestation_digest"] = (
        validator.s2e_carrier_attestation_digest(carrier_attestation)
    )
    authority = validator.build_s2e_launch_predecessor_authority(
        predecessor_receipt=issued,
        launch_chain_before_predecessor=[],
        acceptance_review_bundle=review_bundle,
        review_governed_capture_record=review_capture,
        review_disposable_test_effect_chains=[disposable_chain],
        review_durability_anchor_attestation=review_anchor_attestation,
        carrier_attestation=carrier_attestation,
        carrier_governed_capture_record=carrier_capture,
        carrier_durability_anchor_attestation=carrier_anchor_attestation,
        repo_root=repo,
        now=issued_at + timedelta(minutes=3),
    )
    return {
        "repo": repo,
        "schema_carrier": schema_carrier,
        "issued": issued,
        "authority": authority,
        "now": issued_at + timedelta(minutes=3),
        "issued_at": issued_at,
        "private_key": private_key,
        "fingerprint": fingerprint,
        "external_trust": external_trust,
        "review_bundle": review_bundle,
        "review_anchor": review_anchor_attestation,
        "carrier_anchor": carrier_anchor_attestation,
        "advanced_floor": advanced_floor,
        "tmp_path": tmp_path,
    }


_INHERIT_CARRIER_HEAD = object()


def _candidate_review_anchor(
    case: dict,
    payload: dict,
    *,
    generation: int = 3,
    previous_head: object = _INHERIT_CARRIER_HEAD,
) -> dict:
    """候選自己的 review anchor:必須嚴格晚於前一份的 carrier anchor。"""

    return _durability_anchor_attestation(
        payload,
        trust=case["external_trust"],
        issued_at=case["issued_at"] + timedelta(minutes=3),
        directory=case["tmp_path"],
        generation=generation,
        previous_head=(
            case["carrier_anchor"]["anchor_head_digest"]
            if previous_head is _INHERIT_CARRIER_HEAD
            else previous_head
        ),
    )


def test_wave_generation_requires_ready_reviewed_attested_predecessor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _issued_genesis_authority_case(tmp_path, monkeypatch)
    repo = case["repo"]
    source_head = _commit(repo, "lw1-current.txt", "LW1\n", "LW1 source")
    wave = launch.build_wave_candidate(
        repo_root=repo,
        wave="S2E-LW1",
        source_head=source_head,
        schema_carrier_head=case["schema_carrier"],
        predecessor_receipt=case["issued"],
        predecessor_authority=case["authority"],
        launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
        generation_task_contract_digest=NEXT_GENERATION_TASK_CONTRACT_DIGEST,
        now=case["now"],
    )

    candidate_anchor = _candidate_review_anchor(case, wave)
    assert wave["checkpoint_status"] == "PENDING_REVIEW"
    assert wave["wave_exit_id"] == "S2E_2B_2A_SECURITY_RECOVERY_READY"
    assert validator.validate_s2e_launch_transition(
        wave,
        predecessor_receipt=case["issued"],
        predecessor_authority=case["authority"],
        repo_root=repo,
        now=case["now"],
        consumed_predecessor_digests=frozenset(),
        durability_anchor_attestation=candidate_anchor,
    ) == []
    mismatched_consumption = validator.validate_s2e_launch_transition(
        wave,
        predecessor_receipt=case["issued"],
        predecessor_authority=case["authority"],
        repo_root=repo,
        now=case["now"],
        consumed_predecessor_digests={
            case["issued"]["payload_digest"]
        },
        durability_anchor_attestation=candidate_anchor,
    )
    assert any(
        "consumed-predecessor set differs" in error
        for error in mismatched_consumption
    )

    pending_predecessor = s2e._pending_candidate_from_issued(
        case["issued"]
    )
    pending_errors = validator.validate_s2e_launch_transition(
        wave,
        predecessor_receipt=pending_predecessor,
        predecessor_authority=case["authority"],
        repo_root=repo,
        now=case["now"],
        consumed_predecessor_digests=frozenset(),
        durability_anchor_attestation=candidate_anchor,
    )
    assert any("not an issued READY" in error for error in pending_errors)

    forged = dict(case["issued"])
    forged["acceptance_review_bundle_digest"] = "sha256:" + "f" * 64
    forged["payload_digest"] = validator.launch_payload_digest(forged)
    forged_errors = validator.validate_s2e_launch_transition(
        wave,
        predecessor_receipt=forged,
        predecessor_authority=case["authority"],
        repo_root=repo,
        now=case["now"],
        consumed_predecessor_digests=frozenset(),
        durability_anchor_attestation=candidate_anchor,
    )
    assert any("review binding differs" in error for error in forged_errors)
    assert any(
        "stale or not yet valid" in error
        for error in validator.validate_s2e_launch_predecessor_authority(
            case["authority"],
            predecessor_receipt=case["issued"],
            repo_root=repo,
            now=case["now"] + timedelta(minutes=5),
        )
    )
    late_now = case["now"] + timedelta(minutes=5)
    late_errors = validator.validate_s2e_launch_predecessor_authority(
        case["authority"],
        predecessor_receipt=case["issued"],
        repo_root=repo,
        now=late_now,
    )
    assert late_errors == validator.validate_s2e_launch_predecessor_authority(
        case["authority"],
        predecessor_receipt=case["issued"],
        repo_root=repo,
        now=late_now,
    )
    early_errors = validator.validate_s2e_launch_predecessor_authority(
        case["authority"],
        predecessor_receipt=case["issued"],
        repo_root=repo,
        now=case["now"] - timedelta(minutes=10),
    )
    assert any("stale or not yet valid" in error for error in early_errors)

    disposable_label_only = dict(wave)
    disposable_label_only["side_effect_class"] = "DISPOSABLE_TEST"
    disposable_label_only["payload_digest"] = _payload_digest(
        disposable_label_only
    )
    assert any(
        "pending launch candidate must remain source-only" in error
        for error in validator.validate_s2e_launch_wave_receipt(
            disposable_label_only, repo_root=repo
        )
    )

    missing_authority = validator.issue_s2e_launch_receipt(
        wave,
        acceptance_review_bundle={"schema_version": "caller-shaped"},
        predecessor_receipt=case["issued"],
        predecessor_authority=None,
        repo_root=repo,
    )
    assert missing_authority["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert any(
        "requires exact predecessor authority" in error
        for error in missing_authority["errors"]
    )

    _commit(repo, "later.txt", "later\n", "later source")
    with pytest.raises(ValueError, match="source_head must equal current"):
        s2e._build_wave_candidate_payload(
            repo_root=repo,
            wave="S2E-LW1",
            source_head=source_head,
            schema_carrier_head=case["schema_carrier"],
            predecessor_receipt=case["issued"],
            launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
            generation_task_contract_digest=NEXT_GENERATION_TASK_CONTRACT_DIGEST,
        )


def test_lw1_predicate_oracle_replays_evidence_and_preserves_active_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _issued_genesis_authority_case(tmp_path, monkeypatch)
    repo = case["repo"]
    source_head = _commit(repo, "lw1-current.txt", "LW1\n", "LW1 source")
    candidate = launch.build_wave_candidate(
        repo_root=repo,
        wave="S2E-LW1",
        source_head=source_head,
        schema_carrier_head=case["schema_carrier"],
        predecessor_receipt=case["issued"],
        predecessor_authority=case["authority"],
        launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
        generation_task_contract_digest=NEXT_GENERATION_TASK_CONTRACT_DIGEST,
        now=case["now"],
    )
    capture = _actual_capture(
        repo,
        carrier_path="lw1-current.txt",
        task_digest=NEXT_GENERATION_TASK_CONTRACT_DIGEST,
        context_digest="sha256:" + "c" * 64,
        monkeypatch=monkeypatch,
        argv=validator.s2e_review_test_argv(candidate, repo_root=repo),
    )
    chain = validator.build_s2e_disposable_test_effect_chain(
        capture,
        candidate=candidate,
        repo_root=repo,
        observed_at=capture["completed_at"],
    )
    manifest = validator.s2e_review_source_blob_manifest(
        candidate, repo_root=repo
    )
    dispatch_path = (
        "program_code/ml_training/aiml_gate_receipt_s2e_dispatch.py"
    )
    dispatch_entry = next(
        entry for entry in manifest if entry["path"] == dispatch_path
    )
    assert dispatch_entry["git_blob"] == _git(
        repo, "rev-parse", f"{source_head}:{dispatch_path}"
    )
    results = validator.s2e_review_predicate_results(
        candidate,
        source_blob_manifest=manifest,
        governed_capture_record=capture,
        disposable_test_effect_chains=[chain],
        predecessor_chain=[case["issued"]],
        repo_root=repo,
    )
    assert len(results) == 15
    assert all(
        result["result"] == "PASS" and result["evidence_digests"]
        for result in results
    )
    assert results[-1]["predicate_id"] == "LW1_EXIT_BOUNDARY_VALID"

    todo = repo / "TODO.md"
    todo.write_text(
        todo.read_text(encoding="utf-8").replace(
            "**ACTIVE / P0**", "**SOURCE_LANDED**"
        ),
        encoding="utf-8",
    )
    _git(repo, "add", "TODO.md")
    _git(repo, "commit", "-m", "illegal LW1 package flip")
    forged_head = _git(repo, "rev-parse", "HEAD")
    forged_candidate = launch.build_wave_candidate(
        repo_root=repo,
        wave="S2E-LW1",
        source_head=forged_head,
        schema_carrier_head=case["schema_carrier"],
        predecessor_receipt=case["issued"],
        predecessor_authority=case["authority"],
        launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
        generation_task_contract_digest=NEXT_GENERATION_TASK_CONTRACT_DIGEST,
        now=case["now"],
    )
    forged_capture = _actual_capture(
        repo,
        carrier_path="lw1-current.txt",
        task_digest=NEXT_GENERATION_TASK_CONTRACT_DIGEST,
        context_digest="sha256:" + "d" * 64,
        monkeypatch=monkeypatch,
        argv=validator.s2e_review_test_argv(
            forged_candidate, repo_root=repo
        ),
    )
    forged_chain = validator.build_s2e_disposable_test_effect_chain(
        forged_capture,
        candidate=forged_candidate,
        repo_root=repo,
        observed_at=forged_capture["completed_at"],
    )
    with pytest.raises(ValueError, match="illegally flips S2E.2b-2"):
        validator.s2e_review_predicate_results(
            forged_candidate,
            source_blob_manifest=validator.s2e_review_source_blob_manifest(
                forged_candidate, repo_root=repo
            ),
            governed_capture_record=forged_capture,
            disposable_test_effect_chains=[forged_chain],
            predecessor_chain=[case["issued"]],
            repo_root=repo,
        )


def test_launch_cli_exposes_full_issue_carrier_authority_and_transition_gates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    case = _issued_genesis_authority_case(tmp_path, monkeypatch)
    repo = case["repo"]
    issued = case["issued"]
    authority = case["authority"]
    now = case["now"].isoformat()
    clock_samples: list[str] = []

    def sample_clock() -> str:
        clock_samples.append(now)
        return now

    monkeypatch.setattr(launch, "_sample_utc_host_clock", sample_clock)
    pending = s2e._pending_candidate_from_issued(issued)
    files = {
        "candidate": _json_file(tmp_path, "candidate.json", pending),
        "issued": _json_file(tmp_path, "issued.json", issued),
        "review_bundle": _json_file(
            tmp_path,
            "review-bundle.json",
            authority["acceptance_review_bundle"],
        ),
        "review_capture": _json_file(
            tmp_path,
            "review-capture.json",
            authority["review_governed_capture_record"],
        ),
        "review_chains": _json_file(
            tmp_path,
            "review-chains.json",
            authority["review_disposable_test_effect_chains"],
        ),
        "review_anchor": _json_file(
            tmp_path,
            "review-anchor.json",
            authority["review_durability_anchor_attestation"],
        ),
        "carrier_attestation": _json_file(
            tmp_path,
            "carrier-attestation.json",
            authority["carrier_attestation"],
        ),
        "carrier_capture": _json_file(
            tmp_path,
            "carrier-capture.json",
            authority["carrier_governed_capture_record"],
        ),
        "carrier_anchor": _json_file(
            tmp_path,
            "carrier-anchor.json",
            authority["carrier_durability_anchor_attestation"],
        ),
        "empty_chain": _json_file(tmp_path, "empty-chain.json", []),
    }
    assert launch.main([
        "issue",
        "--repo-root", str(repo),
        "--candidate", str(files["candidate"]),
        "--acceptance-review-bundle", str(files["review_bundle"]),
        "--governed-capture-record", str(files["review_capture"]),
        "--disposable-test-effect-chains", str(files["review_chains"]),
        "--durability-anchor-attestation", str(files["review_anchor"]),
    ]) == 2
    stale_issue = json.loads(capsys.readouterr().out)
    assert stale_issue["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert any(
        "not the clean current HEAD" in error
        for error in stale_issue["errors"]
    )
    assert clock_samples == []

    assert launch.main([
        "verify-carrier",
        "--repo-root", str(repo),
        "--attestation", str(files["carrier_attestation"]),
        "--payload-receipt", str(files["issued"]),
        "--governed-capture-record", str(files["carrier_capture"]),
        "--durability-anchor-attestation", str(files["carrier_anchor"]),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "VERIFIED"
    assert clock_samples == [now]

    assert launch.main([
        "build-predecessor-authority",
        "--repo-root", str(repo),
        "--predecessor-receipt", str(files["issued"]),
        "--launch-chain-before-predecessor", str(files["empty_chain"]),
        "--acceptance-review-bundle", str(files["review_bundle"]),
        "--review-governed-capture-record", str(files["review_capture"]),
        "--review-disposable-test-effect-chains", str(files["review_chains"]),
        "--review-durability-anchor-attestation", str(files["review_anchor"]),
        "--carrier-attestation", str(files["carrier_attestation"]),
        "--carrier-governed-capture-record", str(files["carrier_capture"]),
        "--carrier-durability-anchor-attestation", str(files["carrier_anchor"]),
    ]) == 0
    rebuilt_authority = json.loads(capsys.readouterr().out)
    assert rebuilt_authority["authority_digest"] == authority["authority_digest"]
    assert clock_samples == [now, now]

    source_head = _commit(repo, "lw1-cli.txt", "LW1\n", "LW1 CLI source")
    authority_path = _json_file(tmp_path, "authority.json", authority)
    assert launch.main([
        "generate-wave",
        "--repo-root", str(repo),
        "--wave", "S2E-LW1",
        "--source-head", source_head,
        "--schema-carrier-head", case["schema_carrier"],
        "--predecessor-receipt", str(files["issued"]),
        "--predecessor-authority", str(authority_path),
        "--launch-contract-digest", LAUNCH_CONTRACT_DIGEST,
        "--generation-task-contract-digest",
        NEXT_GENERATION_TASK_CONTRACT_DIGEST,
    ]) == 0
    wave = json.loads(capsys.readouterr().out)
    assert clock_samples == [now, now, now]
    wave_path = _json_file(tmp_path, "wave.json", wave)
    candidate_anchor_path = _json_file(
        tmp_path,
        "candidate-anchor.json",
        _candidate_review_anchor(case, wave),
    )
    # candidate 的 review anchor 缺席 ⇒ 只得結構性語義,絕不靜默 Advance。
    assert launch.main([
        "validate",
        "--repo-root", str(repo),
        "--receipt", str(wave_path),
        "--predecessor-receipt", str(files["issued"]),
        "--predecessor-authority", str(authority_path),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "STRUCTURAL_PASS_NOT_ADVANCE",
        "errors": [],
    }
    assert launch.main([
        "validate",
        "--repo-root", str(repo),
        "--receipt", str(wave_path),
        "--predecessor-receipt", str(files["issued"]),
        "--predecessor-authority", str(authority_path),
        "--durability-anchor-attestation", str(candidate_anchor_path),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "ADVANCE",
        "errors": [],
    }
    assert clock_samples == [now, now, now, now, now]
    assert launch.main([
        "transition-gate",
        "--repo-root", str(repo),
        "--receipt", str(wave_path),
        "--predecessor-receipt", str(files["issued"]),
        "--predecessor-authority", str(authority_path),
        "--durability-anchor-attestation", str(candidate_anchor_path),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "ADVANCE",
        "errors": [],
    }
    assert clock_samples == [now, now, now, now, now, now]
    # transition-gate 的新旗標為 required:缺它必須是 argparse 層的硬失敗。
    with pytest.raises(SystemExit):
        launch.main([
            "transition-gate",
            "--repo-root", str(repo),
            "--receipt", str(wave_path),
            "--predecessor-receipt", str(files["issued"]),
            "--predecessor-authority", str(authority_path),
        ])


def test_verified_review_bundle_issues_ready_genesis_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_key, _, fingerprint = _install_disposable_s2e_trust_root(
        tmp_path, monkeypatch
    )
    external_trust = _install_disposable_external_evidence_roots(
        tmp_path, monkeypatch
    )
    repo, baseline, carrier, _ = _repo(tmp_path)
    _git(repo, "checkout", "--detach", carrier)
    candidate = launch.build_genesis_candidate(
        repo_root=repo,
        baseline_head=baseline,
        schema_carrier_head=carrier,
        launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
        generation_task_contract_digest=GENERATION_TASK_CONTRACT_DIGEST,
    )
    assert candidate["checkpoint_status"] == "PENDING_REVIEW"
    assert candidate["acceptance_review_bundle_digest"] is None
    assert candidate["wave_exit_id"] == "W0_GENESIS_READY"
    issued_at = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
    review_task_digest = candidate["generation_task_contract_digest"]
    review_context_digest = "sha256:" + "6" * 64
    review_argv = validator.s2e_review_test_argv(
        candidate,
        repo_root=repo,
    )
    capture = _actual_capture(
        repo,
        carrier_path="schemas/launch.json",
        task_digest=review_task_digest,
        context_digest=review_context_digest,
        monkeypatch=monkeypatch,
        argv=review_argv,
    )
    disposable_chain = validator.build_s2e_disposable_test_effect_chain(
        capture,
        candidate=candidate,
        repo_root=repo,
        observed_at=capture["completed_at"],
    )
    capture_identity = {
        "schema_version": "governed_capture_identity_v1",
        "record_digest": capture["record_digest"],
        "context_artifact_digest": capture["context_artifact_digest"],
        "task_contract_digest": capture["task_contract_digest"],
        "node_id": capture["node_id"],
        "role_id": capture["role_id"],
        "native_agent": capture["native_agent"],
        "permission": capture["permission"],
    }
    bundle = {
        "schema_version": "s2e_launch_acceptance_review_bundle_v1",
        "candidate_payload_digest": candidate["payload_digest"],
        "launch_id": candidate["launch_id"],
        "wave": candidate["wave"],
        "reviewed_source_head": candidate["schema_carrier_head"],
        "reviewed_source_tree": candidate["schema_carrier_tree"],
        "generation_task_contract_digest": candidate[
            "generation_task_contract_digest"
        ],
        "wave_exit_id": candidate["wave_exit_id"],
        "source_blob_manifest": validator.s2e_review_source_blob_manifest(
            candidate,
            repo_root=repo,
        ),
        "predicate_results": validator.s2e_review_predicate_results(
            candidate,
            source_blob_manifest=validator.s2e_review_source_blob_manifest(
                candidate, repo_root=repo
            ),
            governed_capture_record=capture,
            disposable_test_effect_chains=[disposable_chain],
            predecessor_chain=[],
            repo_root=repo,
        ),
        "consumed_predecessor_digests": [],
        "disposable_test_effect_chain_digests": [
            disposable_chain["chain_digest"]
        ],
        "governed_capture_identity": capture_identity,
        "governed_capture_record_digest": capture["record_digest"],
        "reviewer_identity": {
            "node_id": capture["node_id"],
            "role_id": capture["role_id"],
            "native_agent": capture["native_agent"],
            "permission": capture["permission"],
        },
        "issued_at": issued_at.isoformat(),
        "expires_at": (issued_at + timedelta(minutes=5)).isoformat(),
        "signer": {
            "role": "S2E_SIGNER",
            "identity": s2e.S2E_RECEIPT_SIGNER_IDENTITY,
            "namespace": s2e.S2E_RECEIPT_SIGNATURE_NAMESPACE,
            "key_generation": "independent_off_repo_ed25519_v1",
            "anchor": "fixed_off_repo_public_trust_root_v1",
            "key_fingerprint": fingerprint,
        },
        "durability_anchor_binding": None,
    }
    signed_bytes = validator.s2e_acceptance_review_signed_bytes(bundle)
    bundle["signed_core_digest"] = "sha256:" + hashlib.sha256(
        signed_bytes
    ).hexdigest()
    bundle["signature"] = {
        "algorithm": "SSHSIG",
        "signed_digest": bundle["signed_core_digest"],
        "signature": _sign_sshsig(
            private_key,
            signed_bytes,
            namespace=s2e.S2E_RECEIPT_SIGNATURE_NAMESPACE,
            directory=tmp_path,
        ),
    }
    worm_payload = validator.s2e_acceptance_review_worm_payload(bundle)
    anchor_attestation = _durability_anchor_attestation(
        worm_payload,
        trust=external_trust,
        issued_at=issued_at,
        directory=tmp_path,
    )
    bundle["durability_anchor_binding"] = _anchor_binding(anchor_attestation)
    bundle["bundle_digest"] = validator.s2e_acceptance_review_bundle_digest(
        bundle
    )

    forged_manifest = json.loads(json.dumps(bundle))
    forged_manifest["source_blob_manifest"][0]["sha256"] = (
        "sha256:" + "0" * 64
    )
    forged_manifest["bundle_digest"] = (
        validator.s2e_acceptance_review_bundle_digest(forged_manifest)
    )
    manifest_errors = validator.validate_s2e_launch_acceptance_review_bundle(
        forged_manifest,
        candidate=candidate,
        governed_capture_record=capture,
        disposable_test_effect_chains=[disposable_chain],
        predecessor_chain=[],
        durability_anchor_attestation=anchor_attestation,
        repo_root=repo,
        now=issued_at + timedelta(minutes=1),
    )
    assert any("source blob manifest differs from Git" in error for error in manifest_errors)

    forged_predicate = json.loads(json.dumps(bundle))
    forged_predicate["predicate_results"][0]["evidence_digests"][0] = (
        "sha256:" + "0" * 64
    )
    forged_predicate["bundle_digest"] = (
        validator.s2e_acceptance_review_bundle_digest(forged_predicate)
    )
    predicate_errors = validator.validate_s2e_launch_acceptance_review_bundle(
        forged_predicate,
        candidate=candidate,
        governed_capture_record=capture,
        disposable_test_effect_chains=[disposable_chain],
        predecessor_chain=[],
        durability_anchor_attestation=anchor_attestation,
        repo_root=repo,
        now=issued_at + timedelta(minutes=1),
    )
    assert any(
        "predicate evidence is not the exact code-owned result" in error
        for error in predicate_errors
    )

    monkeypatch.setattr(
        s2e,
        "_trusted_issuance_now",
        lambda: issued_at + timedelta(minutes=1),
    )
    trust_root_path = s2e.S2E_RECEIPT_TRUST_ROOT_PATH
    trust_profile = json.loads(trust_root_path.read_text(encoding="utf-8"))
    trusted_provider_lock = trust_profile[
        "governed_pytest_provider_lock_sha256"
    ]
    trust_profile["governed_pytest_provider_lock_sha256"] = (
        "sha256:" + "0" * 64
    )
    trust_root_path.write_text(
        json.dumps(
            trust_profile,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    rejected = validator.issue_s2e_launch_receipt(
        candidate,
        acceptance_review_bundle=bundle,
        repo_root=repo,
        governed_capture_record=capture,
        durability_anchor_attestation=anchor_attestation,
        disposable_test_effect_chains=[disposable_chain],
    )
    assert rejected["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert any(
        "pytest provider lock differs from fixed off-repository trust root"
        in error
        for error in rejected["errors"]
    )
    trust_profile["governed_pytest_provider_lock_sha256"] = trusted_provider_lock
    trust_root_path.write_text(
        json.dumps(
            trust_profile,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )

    issuance = validator.issue_s2e_launch_receipt(
        candidate,
        acceptance_review_bundle=bundle,
        repo_root=repo,
        governed_capture_record=capture,
        durability_anchor_attestation=anchor_attestation,
        disposable_test_effect_chains=[disposable_chain],
    )

    assert issuance["status"] == "ISSUED"
    issued = issuance["issued_receipt"]
    assert issued is not None
    assert issued["checkpoint_status"] == "W0_GENESIS_READY"
    assert issued["wave_exit_id"] == "W0_GENESIS_READY"
    assert issued["side_effect_class"] == "DISPOSABLE_TEST"
    assert issued["disposable_effect_chain_digests"] == [
        disposable_chain["chain_digest"]
    ]
    assert issued["acceptance_review_bundle_digest"] == bundle["bundle_digest"]
    assert issued["payload_digest"] == validator.launch_payload_digest(issued)
    assert validator.validate_s2e_launch_genesis_receipt(
        issued, repo_root=repo
    ) == []


def test_generic_validator_never_schema_only_accepts_review_bundle() -> None:
    digest = "sha256:" + "a" * 64
    capture_identity = {
        "schema_version": "governed_capture_identity_v1",
        "record_digest": digest,
        "context_artifact_digest": digest,
        "task_contract_digest": digest,
        "node_id": "review",
        "role_id": "E4",
        "native_agent": "E4-verifier",
        "permission": "read_only",
    }
    bundle = {
        "schema_version": "s2e_launch_acceptance_review_bundle_v1",
        "candidate_payload_digest": digest,
        "launch_id": "S2E-LW1-LW5",
        "wave": "W0-GENESIS",
        "wave_exit_id": "W0_GENESIS_READY",
        "reviewed_source_head": "a" * 40,
        "reviewed_source_tree": "b" * 40,
        "generation_task_contract_digest": digest,
        "source_blob_manifest": [
            {
                "path": f"review/path-{index}.py",
                "mode": "100644",
                "git_blob": f"{index:x}" * 40,
                "sha256": "sha256:" + f"{index:x}" * 64,
            }
            for index in range(1, 9)
        ],
        "predicate_results": [
            {
                "predicate_id": predicate_id,
                "result": "PASS",
                "evidence_digests": [digest],
            }
            for predicate_id in (
                "CANDIDATE_SCHEMA_VALID",
                "EXACT_SOURCE_HEAD_TREE_VALID",
                "DURABILITY_ANCHOR_IMMUTABLE_READBACK_VALID",
                "INDEPENDENT_GOVERNED_REVIEW_VALID",
                "INDEPENDENT_SSHSIG_VALID",
            )
        ],
        "consumed_predecessor_digests": [],
        "disposable_test_effect_chain_digests": [digest],
        "governed_capture_identity": capture_identity,
        "governed_capture_record_digest": digest,
        "reviewer_identity": {
            "node_id": "review",
            "role_id": "E4",
            "native_agent": "E4-verifier",
            "permission": "read_only",
        },
        "issued_at": "2026-07-30T12:00:00Z",
        "expires_at": "2026-07-30T12:05:00Z",
        "signer": {
            "role": "S2E_SIGNER",
            "identity": s2e.S2E_RECEIPT_SIGNER_IDENTITY,
            "namespace": s2e.S2E_RECEIPT_SIGNATURE_NAMESPACE,
            "key_generation": "independent_off_repo_ed25519_v1",
            "anchor": "fixed_off_repo_public_trust_root_v1",
            "key_fingerprint": "SHA256:" + "A" * 43,
        },
        "signed_core_digest": digest,
        "signature": {
            "algorithm": "SSHSIG",
            "signed_digest": digest,
            "signature": "x" * 32,
        },
        "durability_anchor_binding": {
            "anchor_locator": ANCHOR_LOCATOR,
            "offhost_replica_locator": REPLICA_LOCATOR,
            "anchor_generation": 1,
            "anchor_head_digest": digest,
            "replica_head_digest": digest,
            "anchor_attestation_digest": digest,
        },
        "bundle_digest": digest,
    }

    assert validator.validate_aiml_artifact(
        bundle, now="2026-07-30T12:01:00Z"
    ) == [
        "s2e acceptance review bundle EXTERNAL_VERIFICATION_PENDING: exact "
        "candidate, governed capture, fixed-root SSHSIG, and external WORM "
        "evidence are required"
    ]


# ── Tier 1 remediation:committed anchor floor / 第二把簽章 / 600s 修法 ──────────


def _reviewed_bundle_arguments(case: dict) -> dict:
    """把已發行 W0 的 review bundle 還原成「歷史件」驗證所需的完整參數。"""

    authority = case["authority"]
    return {
        "candidate": s2e._pending_candidate_from_issued(case["issued"]),
        "governed_capture_record": authority["review_governed_capture_record"],
        "disposable_test_effect_chains": authority[
            "review_disposable_test_effect_chains"
        ],
        "predecessor_chain": [],
        "repo_root": case["repo"],
        "require_current_generation": False,
    }


def _resigned_review_bundle(
    case: dict, *, issued_at: datetime, window: timedelta
) -> tuple[dict, dict]:
    """以指定時間窗重簽同一份 review bundle,並重鑄綁它的 durability anchor。"""

    bundle = deepcopy(case["review_bundle"])
    bundle["issued_at"] = issued_at.isoformat()
    bundle["expires_at"] = (issued_at + window).isoformat()
    bundle["durability_anchor_binding"] = None
    signed_bytes = validator.s2e_acceptance_review_signed_bytes(bundle)
    bundle["signed_core_digest"] = "sha256:" + hashlib.sha256(
        signed_bytes
    ).hexdigest()
    bundle["signature"] = {
        "algorithm": "SSHSIG",
        "signed_digest": bundle["signed_core_digest"],
        "signature": _sign_sshsig(
            case["private_key"],
            signed_bytes,
            namespace=s2e.S2E_RECEIPT_SIGNATURE_NAMESPACE,
            directory=case["tmp_path"],
        ),
    }
    anchor = _durability_anchor_attestation(
        validator.s2e_acceptance_review_worm_payload(bundle),
        trust=case["external_trust"],
        issued_at=issued_at,
        directory=case["tmp_path"],
    )
    bundle["durability_anchor_binding"] = _anchor_binding(anchor)
    bundle["bundle_digest"] = validator.s2e_acceptance_review_bundle_digest(bundle)
    return bundle, anchor


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("anchor_locator", "host:append-only-durability-anchor:other-s2e"),
        ("offhost_replica_locator", "replica:offhost-append-only:other-s2e"),
        ("anchor_generation", 9),
        ("anchor_head_digest", "sha256:" + "e" * 64),
        ("replica_head_digest", "sha256:" + "e" * 64),
        ("anchor_attestation_digest", "sha256:" + "e" * 64),
    ),
)
def test_review_durability_anchor_binding_is_enforced_field_by_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: object
) -> None:
    """P1-4 regression:六欄逐欄篡改各一個 case,斷言逐字錯誤訊息。"""

    case = _issued_genesis_authority_case(tmp_path, monkeypatch)
    arguments = _reviewed_bundle_arguments(case)
    assert validator.validate_s2e_launch_acceptance_review_bundle(
        case["review_bundle"],
        durability_anchor_attestation=case["review_anchor"],
        now=case["now"],
        **arguments,
    ) == []
    forged = deepcopy(case["review_bundle"])
    forged["durability_anchor_binding"][field] = value
    errors = validator.validate_s2e_launch_acceptance_review_bundle(
        forged,
        durability_anchor_attestation=case["review_anchor"],
        now=case["now"],
        **arguments,
    )
    assert (
        f"acceptance review durability anchor {field} binding differs"
    ) in errors, errors


@pytest.mark.parametrize(
    "field",
    ("object_id", "version_id", "readback_digest", "provider_attestation_digest"),
)
def test_carrier_immutable_readback_binding_is_enforced_field_by_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    case = _issued_genesis_authority_case(tmp_path, monkeypatch)
    authority = case["authority"]
    forged = deepcopy(authority["carrier_attestation"])
    forged["immutable_readback"][field] = (
        "caller-chosen" if field in {"object_id", "version_id"}
        else "sha256:" + "e" * 64
    )
    result = validator.verify_receipt_carrier_attestation(
        forged,
        payload_receipt=case["issued"],
        repo_root=case["repo"],
        now=case["now"],
        governed_capture_record=authority["carrier_governed_capture_record"],
        durability_anchor_attestation=case["carrier_anchor"],
    )
    assert result["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert (
        f"carrier immutable readback {field} is not bound to durability anchor"
    ) in result["errors"], result["errors"]


def test_external_worm_adapter_is_a_named_typed_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§7.1:enum 的第二支留在 schema,但這一代沒有 evidence validator。"""

    case = _issued_genesis_authority_case(tmp_path, monkeypatch)
    authority = case["authority"]
    forged = deepcopy(authority["carrier_attestation"])
    forged["immutable_readback"]["adapter"] = "EXTERNAL_WORM_V1"
    result = validator.verify_receipt_carrier_attestation(
        forged,
        payload_receipt=case["issued"],
        repo_root=case["repo"],
        now=case["now"],
        governed_capture_record=authority["carrier_governed_capture_record"],
        durability_anchor_attestation=case["carrier_anchor"],
    )
    assert (
        "carrier immutable readback adapter EXTERNAL_WORM_V1 has no admitted "
        "evidence validator in this generation"
    ) in result["errors"], result["errors"]


def test_transition_floor_rules_bind_the_predecessor_to_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§3.3(b) 五條規則,每條斷言逐字錯誤訊息。"""

    case = _issued_genesis_authority_case(tmp_path, monkeypatch)
    repo = case["repo"]
    source_head = _commit(repo, "lw1-floor.txt", "LW1\n", "LW1 source")
    wave = launch.build_wave_candidate(
        repo_root=repo,
        wave="S2E-LW1",
        source_head=source_head,
        schema_carrier_head=case["schema_carrier"],
        predecessor_receipt=case["issued"],
        predecessor_authority=case["authority"],
        launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
        generation_task_contract_digest=NEXT_GENERATION_TASK_CONTRACT_DIGEST,
        now=case["now"],
    )

    def gate(*, predecessor_receipt=None, authority=None, candidate_anchor=None):
        return validator.validate_s2e_launch_transition(
            wave,
            predecessor_receipt=predecessor_receipt or case["issued"],
            predecessor_authority=authority or case["authority"],
            repo_root=repo,
            now=case["now"],
            consumed_predecessor_digests=frozenset(),
            durability_anchor_attestation=(
                candidate_anchor
                if candidate_anchor is not None
                else _candidate_review_anchor(case, wave)
            ),
        )

    assert gate() == []

    # 規則 1:caller 換一份 predecessor ⇒ 與 git 上唯一那份 floor 對不上。
    swapped = dict(case["issued"])
    swapped["acceptance_review_bundle_digest"] = "sha256:" + "f" * 64
    swapped["payload_digest"] = validator.launch_payload_digest(swapped)
    swapped_errors = gate(predecessor_receipt=swapped)
    assert (
        "transition predecessor is not the receipt bound by the committed "
        "durability anchor floor"
    ) in swapped_errors, swapped_errors
    assert (
        "transition predecessor review bundle is not the bundle bound by the "
        "committed durability anchor floor"
    ) in swapped_errors

    # 規則 2:caller 改寫前一份 anchor 的世代/head。
    regressed = deepcopy(case["authority"])
    regressed["review_durability_anchor_attestation"]["anchor_generation"] = 9
    regressed["review_durability_anchor_attestation"]["anchor_head_digest"] = (
        "sha256:" + "e" * 64
    )
    regressed_errors = gate(authority=regressed)
    assert (
        "transition predecessor review durability anchor generation differs "
        "from the committed floor"
    ) in regressed_errors, regressed_errors
    assert (
        "transition predecessor review durability anchor head differs from the "
        "committed floor"
    ) in regressed_errors

    # 規則 3a:b 未嚴格晚於 a。
    flattened = deepcopy(case["authority"])
    flattened["carrier_durability_anchor_attestation"]["anchor_generation"] = 1
    flattened_errors = gate(authority=flattened)
    assert (
        "transition predecessor carrier durability anchor generation does not "
        "strictly exceed transition predecessor review durability anchor"
    ) in flattened_errors, flattened_errors
    assert (
        "S2E predecessor carrier durability anchor generation does not strictly "
        "exceed its review durability anchor"
    ) in flattened_errors

    # 規則 3b:c 未嚴格晚於 b。
    stalled_errors = gate(
        candidate_anchor=_candidate_review_anchor(case, wave, generation=2)
    )
    assert (
        "transition candidate review durability anchor generation does not "
        "strictly exceed transition predecessor carrier durability anchor"
    ) in stalled_errors, stalled_errors

    # 規則 4:相鄰世代必須 hash 連結。
    unlinked_errors = gate(
        candidate_anchor=_candidate_review_anchor(
            case, wave, previous_head="sha256:" + "e" * 64
        )
    )
    assert (
        "transition candidate review durability anchor does not hash-link to "
        "the immediately prior head"
    ) in unlinked_errors, unlinked_errors

    # 規則 5:c 不得無前手(P1-1 的原始 PoC:刪 ledger 尾部後重簽 gen=1/prev=null)。
    truncated_errors = gate(
        candidate_anchor=_candidate_review_anchor(
            case, wave, generation=1, previous_head=None
        )
    )
    assert (
        "transition candidate review durability anchor omits its previous head"
    ) in truncated_errors, truncated_errors


def _floor_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "floor-repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "s2e-floor@example.invalid")
    _git(repo, "config", "user.name", "S2E Floor Test")
    (repo / "seed.txt").write_text("seed\n", encoding="ascii")
    _git(repo, "add", "seed.txt")
    _git(repo, "commit", "-qm", "seed")
    return repo


def _advanced_floor(generation: int, *, head_suffix: str = "1") -> dict:
    floor = {
        "schema_version": anchor_floor.DURABILITY_ANCHOR_FLOOR_SCHEMA,
        "launch_id": s2e_external.LAUNCH_ID,
        "state": "ADVANCED",
        "anchor_locator": ANCHOR_LOCATOR,
        "offhost_replica_locator": REPLICA_LOCATOR,
        "floor_generation": generation,
        "floor_head_digest": "sha256:" + head_suffix * 64,
        "bound_receipt_payload_digest": "sha256:" + "2" * 64,
        "bound_acceptance_review_bundle_digest": "sha256:" + "3" * 64,
    }
    floor["floor_digest"] = anchor_floor.durability_anchor_floor_digest(floor)
    return floor


def test_absent_committed_floor_is_fail_closed(tmp_path: Path) -> None:
    """檔案不存在 ≠ genesis。讀不到 floor 一律 fail-closed。"""

    repo = _floor_repo(tmp_path)
    floor, errors = anchor_floor.read_committed_durability_anchor_floor(
        repo, at_commit=_git(repo, "rev-parse", "HEAD")
    )
    assert floor is None
    assert errors == [
        "durability anchor floor is absent from the reviewed commit history"
    ]


def test_committed_floor_history_accepts_a_strictly_increasing_chain(
    tmp_path: Path,
) -> None:
    repo = _floor_repo(tmp_path)
    _commit_floor(repo, _genesis_armed_floor(), "arm floor")
    expected = _advanced_floor(1)
    head = _commit_floor(repo, expected, "advance floor")
    floor, errors = anchor_floor.read_committed_durability_anchor_floor(
        repo, at_commit=head
    )
    assert errors == []
    assert floor == expected


def test_committed_floor_rejects_a_non_increasing_generation(tmp_path: Path) -> None:
    repo = _floor_repo(tmp_path)
    _commit_floor(repo, _advanced_floor(2), "advance floor")
    head = _commit_floor(repo, _advanced_floor(2, head_suffix="4"), "replay floor")
    floor, errors = anchor_floor.read_committed_durability_anchor_floor(
        repo, at_commit=head
    )
    assert floor is None
    assert errors == [
        "durability anchor floor generation is not strictly increasing"
    ]


def test_committed_floor_rejects_a_second_genesis(tmp_path: Path) -> None:
    """想第二次進 genesis,必須 commit 一份把 generation 退回 0 的 floor。"""

    repo = _floor_repo(tmp_path)
    _commit_floor(repo, _genesis_armed_floor(), "arm floor")
    _commit_floor(repo, _advanced_floor(1), "advance floor")
    head = _commit_floor(repo, _genesis_armed_floor(), "re-arm floor")
    floor, errors = anchor_floor.read_committed_durability_anchor_floor(
        repo, at_commit=head
    )
    assert floor is None
    assert (
        "durability anchor floor re-enters GENESIS_ARMED after its first commit"
    ) in errors, errors


def test_committed_floor_rejects_a_forked_history(tmp_path: Path) -> None:
    """merge topology 下兩份互不為祖先的 floor commit ⇒ 順序歧義,fail-closed。"""

    repo = _floor_repo(tmp_path)
    base = _git(repo, "rev-parse", "HEAD")
    _commit_floor(repo, _advanced_floor(1), "floor on main")
    main_head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "-b", "sibling", base)
    _commit_floor(repo, _advanced_floor(2), "floor on sibling")
    _git(repo, "checkout", "-q", "-")
    _git(repo, "merge", "-q", "--no-edit", "-X", "theirs", "sibling")
    head = _git(repo, "rev-parse", "HEAD")
    assert head != main_head
    floor, errors = anchor_floor.read_committed_durability_anchor_floor(
        repo, at_commit=head
    )
    assert floor is None
    assert (
        "durability anchor floor history is not a single ancestor chain"
    ) in errors, errors


def test_historical_review_bundle_is_freed_from_wall_clock_but_not_from_its_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§7.4:被 digest 釘死的歷史件免除時鐘謂詞;窗長上界恆檢查。"""

    case = _issued_genesis_authority_case(tmp_path, monkeypatch)
    arguments = _reviewed_bundle_arguments(case)
    frozen_now = case["now"]
    long_past = case["issued_at"] - timedelta(days=365)

    # 1. 歷史件在遠早於凍結 now 的窗內 ⇒ 免除 wall-clock 後完全通過。
    historical, historical_anchor = _resigned_review_bundle(
        case, issued_at=long_past, window=timedelta(minutes=5)
    )
    assert validator.validate_s2e_launch_acceptance_review_bundle(
        historical,
        durability_anchor_attestation=historical_anchor,
        now=frozen_now,
        require_current_freshness=False,
        **arguments,
    ) == []

    # 2. 同一份歷史件把窗長改成 601 秒 ⇒ 必須仍然紅(鬆綁的是謂詞,不是上界)。
    over_window, over_window_anchor = _resigned_review_bundle(
        case, issued_at=long_past, window=timedelta(seconds=601)
    )
    over_window_errors = validator.validate_s2e_launch_acceptance_review_bundle(
        over_window,
        durability_anchor_attestation=over_window_anchor,
        now=frozen_now,
        require_current_freshness=False,
        **arguments,
    )
    assert (
        "acceptance review freshness window exceeds 600 seconds"
    ) in over_window_errors, over_window_errors

    # 3. 現時件(candidate 側,預設 True)過期 ⇒ 必須紅。
    current_errors = validator.validate_s2e_launch_acceptance_review_bundle(
        historical,
        durability_anchor_attestation=historical_anchor,
        now=frozen_now,
        **arguments,
    )
    assert (
        "acceptance review bundle is stale or not yet valid"
    ) in current_errors, current_errors
    assert (
        "acceptance review durability anchor: durability anchor is stale or not "
        "yet valid"
    ) in current_errors

    # 4. carrier 與 carrier anchor 恆維持 wall-clock。
    authority = case["authority"]
    late = frozen_now + timedelta(minutes=30)
    carrier_result = validator.verify_receipt_carrier_attestation(
        authority["carrier_attestation"],
        payload_receipt=case["issued"],
        repo_root=case["repo"],
        now=late,
        governed_capture_record=authority["carrier_governed_capture_record"],
        durability_anchor_attestation=case["carrier_anchor"],
    )
    assert carrier_result["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert (
        "durability anchor: durability anchor is stale or not yet valid"
    ) in carrier_result["errors"], carrier_result["errors"]
    assert any(
        "carrier attestation" in error and "stale" in error
        for error in carrier_result["errors"]
    ), carrier_result["errors"]
    late_authority_errors = validator.validate_s2e_launch_predecessor_authority(
        authority,
        predecessor_receipt=case["issued"],
        repo_root=case["repo"],
        now=late,
    )
    assert any(
        error.startswith("S2E predecessor carrier: ") and "stale" in error
        for error in late_authority_errors
    ), late_authority_errors
    # 5. 歷史側在同一次呼叫裡不得再貢獻任何 stale 錯誤。
    assert not any(
        error.startswith("S2E predecessor review: ") and "stale" in error
        for error in late_authority_errors
    ), late_authority_errors


def test_carrier_attestation_window_length_upper_bound_is_enforced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """carrier 是現時件,其 600 秒窗長上界與 review 側同樣是恆檢查。"""

    case = _issued_genesis_authority_case(tmp_path, monkeypatch)
    forged = deepcopy(case["authority"]["carrier_attestation"])
    issued_at = datetime.fromisoformat(forged["issued_at"])
    forged["expires_at"] = (issued_at + timedelta(seconds=601)).isoformat()
    errors = validator.validate_receipt_carrier_attestation(
        forged,
        payload_receipt=case["issued"],
        repo_root=case["repo"],
        now=(issued_at + timedelta(seconds=1)).isoformat(),
    )
    assert (
        "carrier attestation freshness window exceeds 600 seconds"
    ) in errors, errors
