from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import io
import json
import inspect
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
import stat
import subprocess
import sys
import threading
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
ML_ROOT = ROOT / "program_code" / "ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2e_launch_receipts as launch  # noqa: E402
import aiml_gate_receipt_s2e_anchor_floor as anchor_floor  # noqa: E402
import aiml_gate_receipt_schema_core as schema_core  # noqa: E402
import aiml_gate_receipt_s2e_consumption as consumption_module  # noqa: E402
import aiml_gate_receipt_git_view as git_view  # noqa: E402
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
    # 同型處置:2026-08-09 拆分波的 view 葉。E2 round-6 P1-3 報「簽名不再涵蓋它」——
    # 那一半不對(import 閉包經 `schema_core` 的 top-level 匯入已涵蓋,實測在 175 條
    # closure 內),但顯式列名這一半是對的:涵蓋不該只靠某條 import 恰好存在。
    assert "program_code/ml_training/aiml_gate_receipt_git_view.py" in (
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


def _publish(repo: Path, commit: str | None = None) -> str:
    """把 commit 記到受保護 ref 上,模擬「這份 floor 已經過 PR 進 main」。

    P0-1 之後,floor 鏈尾必須是 `_PROTECTED_ANCESTOR_REFS` 某一支的祖先,否則判
    UNVERIFIED。ref 名單是 code-owned 常數,測試只能改 repo 的 ref 本身,不能傳參
    數指定——這正是該裁決要保住的性質。
    """

    target = commit or _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-ref", anchor_floor._PROTECTED_ANCESTOR_REFS[0], target)
    return target


def _commit_floor(
    repo: Path, floor: dict, message: str, *, publish: bool = True
) -> str:
    relative = anchor_floor.durability_anchor_floor_repo_path()
    target = repo / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_floor_bytes(floor))
    _git(repo, "add", relative)
    _git(repo, "commit", "-m", message)
    head = _git(repo, "rev-parse", "HEAD")
    if publish:
        _publish(repo, head)
    return head


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
    # 創世 floor 隨 schema carrier 進 repo,並同步進受保護 ref(P0-1)。
    _publish(repo, carrier)
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


def _signed_review_bundle(
    candidate: dict,
    *,
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    private_key: Path,
    fingerprint: str,
    external_trust: dict[str, object],
    issued_at: datetime,
    context_digest: str = "sha256:" + "6" * 64,
    predecessor_chain: list[dict] | None = None,
    consumed_predecessor_digests: list[str] | None = None,
    anchor_generation: int = 1,
    anchor_previous_head: str | None = None,
    anchor_issued_at: datetime | None = None,
) -> dict:
    """一份候選的完整、簽妥、anchor 已對綁的 acceptance review bundle。

    候選自己的 review anchor 綁的是 `s2e_acceptance_review_worm_payload(bundle)`,
    不是 receipt——production 的 `validate_s2e_launch_acceptance_review_bundle`
    與(PR #178 起)`validate_s2e_launch_transition` 都以此認證候選 anchor。
    """

    review_capture = _actual_capture(
        repo,
        carrier_path="schemas/launch.json",
        task_digest=candidate["generation_task_contract_digest"],
        context_digest=context_digest,
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
    source_blob_manifest = validator.s2e_review_source_blob_manifest(
        candidate, repo_root=repo
    )
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
        "source_blob_manifest": source_blob_manifest,
        "predicate_results": validator.s2e_review_predicate_results(
            candidate,
            source_blob_manifest=source_blob_manifest,
            governed_capture_record=review_capture,
            disposable_test_effect_chains=[disposable_chain],
            predecessor_chain=predecessor_chain or [],
            repo_root=repo,
        ),
        "consumed_predecessor_digests": consumed_predecessor_digests or [],
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
        issued_at=anchor_issued_at or issued_at,
        directory=tmp_path,
        generation=anchor_generation,
        previous_head=anchor_previous_head,
    )
    review_bundle["durability_anchor_binding"] = _anchor_binding(
        review_anchor_attestation
    )
    review_bundle["bundle_digest"] = (
        validator.s2e_acceptance_review_bundle_digest(review_bundle)
    )
    return {
        "bundle": review_bundle,
        "capture": review_capture,
        "chain": disposable_chain,
        "anchor": review_anchor_attestation,
    }


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
    signed_review = _signed_review_bundle(
        candidate,
        repo=repo,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        private_key=private_key,
        fingerprint=fingerprint,
        external_trust=external_trust,
        issued_at=issued_at,
    )
    review_bundle = signed_review["bundle"]
    review_capture = signed_review["capture"]
    disposable_chain = signed_review["chain"]
    review_anchor_attestation = signed_review["anchor"]
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

# 候選 anchor 的 observed_at 是 anchor_issued_at + 10s、expires_at 是 +5min,而
# transition gate 恆在 `case["now"] == issued_at + 3min` 判定。因此 anchor 必須在
# `now` **之前**鑄出,窗口才真的涵蓋判定時刻——production 對候選 anchor 要求當下
# 新鮮是對的,該動的是 fixture。全部相對凍結時鐘,無 wall-clock。
_CANDIDATE_ANCHOR_OFFSET = timedelta(minutes=2, seconds=30)


def _wave_review(
    case: dict, wave: dict, monkeypatch: pytest.MonkeyPatch
) -> dict:
    """Wave 候選自己的 signed review bundle + 它的 review anchor(gen 3)。"""

    return _signed_review_bundle(
        wave,
        repo=case["repo"],
        tmp_path=case["tmp_path"],
        monkeypatch=monkeypatch,
        private_key=case["private_key"],
        fingerprint=case["fingerprint"],
        external_trust=case["external_trust"],
        issued_at=case["issued_at"],
        context_digest="sha256:" + "a" * 64,
        predecessor_chain=[case["issued"]],
        anchor_generation=3,
        anchor_previous_head=case["carrier_anchor"]["anchor_head_digest"],
        anchor_issued_at=case["issued_at"] + _CANDIDATE_ANCHOR_OFFSET,
    )


def _candidate_review_anchor(
    case: dict,
    bundle: dict,
    *,
    generation: int = 3,
    previous_head: object = _INHERIT_CARRIER_HEAD,
) -> dict:
    """候選自己的 review anchor:必須嚴格晚於前一份的 carrier anchor。

    綁的 payload 是候選**自己那份 acceptance review bundle** 的 WORM payload,
    與 production 一致(`validate_s2e_launch_acceptance_review_bundle` 與 PR #178
    起的 `validate_s2e_launch_transition` 都以此認證)。舊 fixture 綁的是 wave
    receipt,只因當時沒有任何路徑認證這份 anchor 才會通過。
    """

    return _durability_anchor_attestation(
        validator.s2e_acceptance_review_worm_payload(bundle),
        trust=case["external_trust"],
        issued_at=case["issued_at"] + _CANDIDATE_ANCHOR_OFFSET,
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

    wave_review = _wave_review(case, wave, monkeypatch)
    wave_bundle = wave_review["bundle"]
    candidate_anchor = wave_review["anchor"]
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
        acceptance_review_bundle=wave_bundle,
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
        acceptance_review_bundle=wave_bundle,
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
        acceptance_review_bundle=wave_bundle,
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
        acceptance_review_bundle=wave_bundle,
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


def _expected_anchor_observations() -> dict[str, Any]:
    """CLI 在一次 ADVANCE 上必須輸出的 typed 觀察(兩處 floor + 一條 host identity)。

    host identity 那條逐字綁**本機真實狀態**(而不是列舉兩個可能值),因此在
    `/etc/ssh` 可讀與不可讀的主機上都是強斷言。
    """

    return {
        "host_identity": [
            "durability anchor replica host identity: "
            + s2e_external.local_ssh_host_key_fingerprints()[1]
        ],
        "floor_verdicts": [
            {
                "label": "acceptance review durability anchor floor",
                "verdict": anchor_floor.FLOOR_VERIFIED,
            },
            {
                "label": "transition durability anchor floor",
                "verdict": anchor_floor.FLOOR_VERIFIED,
            },
        ],
    }


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
        "not the current HEAD generation" in error
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
    wave_review = _wave_review(case, wave, monkeypatch)
    candidate_anchor_path = _json_file(
        tmp_path, "candidate-anchor.json", wave_review["anchor"]
    )
    candidate_bundle_path = _json_file(
        tmp_path, "candidate-review-bundle.json", wave_review["bundle"]
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
        "anchor_gate_observations": {"host_identity": [], "floor_verdicts": []},
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
    # anchor 有、bundle 缺 ⇒ 候選 anchor 無從認證(payload binding 只能從 bundle
    # 實值導出),因此與缺 anchor 同樣降級,絕不靜默 Advance。
    assert json.loads(capsys.readouterr().out) == {
        "status": "STRUCTURAL_PASS_NOT_ADVANCE",
        "anchor_gate_observations": {"host_identity": [], "floor_verdicts": []},
        "errors": [],
    }
    # anchor 與 bundle 都在 ⇒ 完整認證後才 Advance。
    assert launch.main([
        "validate",
        "--repo-root", str(repo),
        "--receipt", str(wave_path),
        "--predecessor-receipt", str(files["issued"]),
        "--predecessor-authority", str(authority_path),
        "--durability-anchor-attestation", str(candidate_anchor_path),
        "--acceptance-review-bundle", str(candidate_bundle_path),
    ]) == 0
    # E3-B/E3-E 的真消費者:verdict 與 host identity 觀察都是 typed 輸出的一格,
    # 下游不必再從錯誤字串裡撈 `"UNVERIFIED: "` 子字串。
    assert json.loads(capsys.readouterr().out) == {
        "status": "ADVANCE",
        "anchor_gate_observations": _expected_anchor_observations(),
        "errors": [],
    }
    assert clock_samples == [now, now, now, now, now, now]
    assert launch.main([
        "transition-gate",
        "--repo-root", str(repo),
        "--receipt", str(wave_path),
        "--predecessor-receipt", str(files["issued"]),
        "--predecessor-authority", str(authority_path),
        "--durability-anchor-attestation", str(candidate_anchor_path),
        "--acceptance-review-bundle", str(candidate_bundle_path),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "ADVANCE",
        "anchor_gate_observations": _expected_anchor_observations(),
        "errors": [],
    }
    assert clock_samples == [now, now, now, now, now, now, now]
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
    # E3-B:issuance 是 floor 判定的最高價值出口。VERIFIED 必須以 typed 形式出現,
    # 而不是靠「沒有錯誤訊息」這種由缺席推論來的證據。
    assert issuance["anchor_gate_observations"] == {
        "host_identity": [
            "durability anchor replica host identity: "
            + s2e_external.local_ssh_host_key_fingerprints()[1]
        ],
        "floor_verdicts": [
            {
                "label": "acceptance review durability anchor floor",
                "verdict": anchor_floor.FLOOR_VERIFIED,
            },
        ],
    }

    # 同一份 floor、同一份 bundle,只把受保護 ref 移開:這正是 operator 2026-08-03
    # 接受為誠實終態的那個情境(未 merge／未 fetch／CI shallow checkout)。它必須
    # ①仍然發不出 receipt ②在 typed 出口記成 UNVERIFIED 而不是 REJECTED——後者會
    # 把「誠實不可驗」誤報成「偽造被拒」。
    _git(repo, "update-ref", "-d", anchor_floor._PROTECTED_ANCESTOR_REFS[0])
    unverified = validator.issue_s2e_launch_receipt(
        candidate,
        acceptance_review_bundle=bundle,
        repo_root=repo,
        governed_capture_record=capture,
        durability_anchor_attestation=anchor_attestation,
        disposable_test_effect_chains=[disposable_chain],
    )
    assert unverified["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert unverified["issued_receipt"] is None
    assert unverified["next_durability_anchor_floor"] is None
    assert unverified["anchor_gate_observations"]["floor_verdicts"] == [
        {
            "label": "acceptance review durability anchor floor",
            "verdict": anchor_floor.FLOOR_UNVERIFIED,
        },
    ]
    assert (
        "acceptance review durability anchor floor: UNVERIFIED: no code-owned "
        "protected ref resolves in this repository, so the floor's history tail "
        "cannot be pinned to any code-owned ref"
    ) in unverified["errors"]


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
        "candidate, governed capture, fixed-root SSHSIG, and a trusted-host "
        "durability anchor attestation with its off-host latest-generation "
        "readback are required"
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

    wave_review = _wave_review(case, wave, monkeypatch)
    wave_bundle = wave_review["bundle"]

    def gate(
        *,
        predecessor_receipt=None,
        authority=None,
        candidate_anchor=None,
        bundle=None,
    ):
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
                else wave_review["anchor"]
            ),
            acceptance_review_bundle=(
                wave_bundle if bundle is None else bundle
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
        candidate_anchor=_candidate_review_anchor(case, wave_bundle, generation=2)
    )
    assert (
        "transition candidate review durability anchor generation does not "
        "strictly exceed transition predecessor carrier durability anchor"
    ) in stalled_errors, stalled_errors

    # 規則 4:相鄰世代必須 hash 連結。
    unlinked_errors = gate(
        candidate_anchor=_candidate_review_anchor(
            case, wave_bundle, previous_head="sha256:" + "e" * 64
        )
    )
    assert (
        "transition candidate review durability anchor does not hash-link to "
        "the immediately prior head"
    ) in unlinked_errors, unlinked_errors

    # 規則 5:c 不得無前手(P1-1 的原始 PoC:刪 ledger 尾部後重簽 gen=1/prev=null)。
    truncated_errors = gate(
        candidate_anchor=_candidate_review_anchor(
            case, wave_bundle, generation=1, previous_head=None
        )
    )
    assert (
        "transition candidate review durability anchor omits its previous head"
    ) in truncated_errors, truncated_errors


def test_transition_authenticates_the_candidate_anchor_and_binds_its_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PR #178 review P1:候選 anchor 必須被**認證**,不是只被排序。

    原本把候選的 SSHSIG 與 `attestation_digest` 換成任意值,`transition-gate` 仍印
    `ADVANCE`;排序檢查只證明世代數字遞增,不證明那份 attestation 是真的。
    `acceptance_review_bundle` 是這條認證的 payload binding 來源,因此它自己也必須
    與這張 receipt 對綁,否則呼叫端可以遞一份簽得過、但屬於別張 receipt 的 bundle。
    """

    case = _issued_genesis_authority_case(tmp_path, monkeypatch)
    repo = case["repo"]
    source_head = _commit(repo, "lw1-auth.txt", "LW1\n", "LW1 source")
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
    wave_review = _wave_review(case, wave, monkeypatch)
    wave_bundle = wave_review["bundle"]
    good_anchor = wave_review["anchor"]

    def gate(*, anchor=None, bundle=_INHERIT_CARRIER_HEAD):
        return validator.validate_s2e_launch_transition(
            wave,
            predecessor_receipt=case["issued"],
            predecessor_authority=case["authority"],
            repo_root=repo,
            now=case["now"],
            consumed_predecessor_digests=frozenset(),
            durability_anchor_attestation=anchor or good_anchor,
            acceptance_review_bundle=(
                wave_bundle if bundle is _INHERIT_CARRIER_HEAD else bundle
            ),
        )

    anchor_prefix = "transition candidate review durability anchor: "
    # 基準:完整、真簽、bundle 對綁 ⇒ 這條路徑確實抵達並通過 anchor 認證。
    assert gate() == []

    # 1) 換掉候選 anchor 的 SSHSIG(Codex 提的原始情境)。
    forged_signature = deepcopy(good_anchor)
    forged_signature["signature"]["signature"] = (
        "-----BEGIN SSH SIGNATURE-----\nQUJDRA==\n-----END SSH SIGNATURE-----"
    )
    forged_signature_errors = gate(anchor=forged_signature)
    assert (
        anchor_prefix + "durability anchor SSHSIG verification failed"
    ) in forged_signature_errors, forged_signature_errors

    # 2) 改掉候選 anchor 的 attestation_digest。
    forged_digest = deepcopy(good_anchor)
    forged_digest["attestation_digest"] = "sha256:" + "c" * 64
    forged_digest_errors = gate(anchor=forged_digest)
    assert (
        anchor_prefix + "durability anchor attestation digest is invalid"
    ) in forged_digest_errors, forged_digest_errors

    # 3) 一份格式完整、簽得過,但屬於**別張候選**的 bundle(genesis 那份)。
    foreign_errors = gate(bundle=case["review_bundle"])
    assert (
        "transition acceptance review bundle is not the one this receipt binds"
    ) in foreign_errors, foreign_errors

    # 4) 缺 bundle / 非 dict ⇒ 必須報錯,絕不是「沒傳就跳過這項檢查」。
    for absent in (None, "sha256:" + "d" * 64, [], 0):
        absent_errors = gate(bundle=absent)
        assert (
            "transition requires the exact candidate acceptance review bundle"
        ) in absent_errors, (absent, absent_errors)


def test_pending_candidate_bundle_binding_is_by_candidate_payload_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PENDING 候選的對綁只能走 `candidate_payload_digest`,不能是 digest-only 比對。

    `_common_payload_errors:428` 禁止 PENDING 候選攜帶 `acceptance_review_bundle_digest`,
    所以「拿 receipt 的該欄位跟 bundle digest 比對」對每一張 wave 候選都恆假——那正是
    本 PR 第一版把 gate 變成對 wave 永久 fail-closed(連 `issue_s2e_launch_receipt`
    的 pre-issuance 呼叫都過不了)的原因。若日後有人把它再收緊成 digest-only 比對,
    這個測試就是那道攔阻。
    """

    case = _issued_genesis_authority_case(tmp_path, monkeypatch)
    repo = case["repo"]
    source_head = _commit(repo, "lw1-pending.txt", "LW1\n", "LW1 source")
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
    wave_review = _wave_review(case, wave, monkeypatch)
    wave_bundle = wave_review["bundle"]

    def gate(bundle):
        return validator.validate_s2e_launch_transition(
            wave,
            predecessor_receipt=case["issued"],
            predecessor_authority=case["authority"],
            repo_root=repo,
            now=case["now"],
            consumed_predecessor_digests=frozenset(),
            durability_anchor_attestation=wave_review["anchor"],
            acceptance_review_bundle=bundle,
        )

    # 前提:PENDING 候選確實不帶 bundle digest,digest-only 比對必然恆假。
    assert wave["checkpoint_status"] == "PENDING_REVIEW"
    assert wave["acceptance_review_bundle_digest"] is None
    assert wave_bundle["candidate_payload_digest"] == wave["payload_digest"]

    # 對綁成立 ⇒ 抵達並通過候選 anchor 認證(零錯誤)。
    assert gate(wave_bundle) == []

    # candidate_payload_digest 對不上 ⇒ 擋下,而且是擋在對綁那一關。
    mismatched = deepcopy(wave_bundle)
    mismatched["candidate_payload_digest"] = "sha256:" + "b" * 64
    mismatched_errors = gate(mismatched)
    assert (
        "transition acceptance review bundle is not the one this receipt binds"
    ) in mismatched_errors, mismatched_errors


def _floor_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "floor-repo"
    repo.mkdir(parents=True)
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


def test_floor_gate_errors_never_returns_empty_for_a_non_verified_reading() -> None:
    """P1-3 在呼叫端的那一半:UNVERIFIED 不得被當成沒事。

    直接餵一個違反建構不變量的 reading(繞過 `_floor_reading`),證明呼叫端仍拿得到
    非空 errors——兩個 `if reading.floor is not None:` 呼叫點因此無法靜默放行。
    """

    silent = anchor_floor.CommittedFloorReading(
        anchor_floor.FLOOR_UNVERIFIED, None, []
    )
    assert anchor_floor.floor_gate_errors(silent, label="transition floor") == [
        "transition floor: verdict UNVERIFIED carried no stated reason"
    ]
    # 建構入口自己也不可能產出那個形狀。
    built = anchor_floor._floor_reading(anchor_floor.FLOOR_VERIFIED, None, [])
    assert built.verdict == anchor_floor.FLOOR_REJECTED
    assert built.floor is None
    assert built.errors == [
        "durability anchor floor is VERIFIED without a stated reason"
    ]


def test_absent_committed_floor_is_fail_closed(tmp_path: Path) -> None:
    """檔案不存在 ≠ genesis。讀不到 floor 一律 fail-closed。"""

    repo = _floor_repo(tmp_path)
    reading = anchor_floor.read_committed_durability_anchor_floor(
        repo, at_commit=_git(repo, "rev-parse", "HEAD")
    )
    assert reading.verdict == anchor_floor.FLOOR_REJECTED
    assert reading.floor is None
    assert reading.errors == [
        "durability anchor floor is absent from the reviewed commit history"
    ]


def test_committed_floor_history_accepts_a_strictly_increasing_chain(
    tmp_path: Path,
) -> None:
    repo = _floor_repo(tmp_path)
    _commit_floor(repo, _genesis_armed_floor(), "arm floor")
    expected = _advanced_floor(1)
    head = _commit_floor(repo, expected, "advance floor")
    reading = anchor_floor.read_committed_durability_anchor_floor(
        repo, at_commit=head
    )
    assert reading.errors == []
    assert reading.verdict == anchor_floor.FLOOR_VERIFIED
    assert reading.floor == expected


def test_committed_floor_off_a_protected_ref_is_unverified_not_pass(
    tmp_path: Path,
) -> None:
    """P0-1:同一 writer 用一條 local branch 鑄出的 floor 只能得 UNVERIFIED。

    §LW1「同一 writer 可 coherent rewrite ⇒ 只能得 UNVERIFIED」在此落地:內容完全
    合法(線性、嚴格遞增、單一 genesis),差別只在鏈尾不是受保護 ref 的祖先。
    """

    repo = _floor_repo(tmp_path)
    _commit_floor(repo, _genesis_armed_floor(), "arm floor", publish=False)
    head = _commit_floor(repo, _advanced_floor(1), "advance floor", publish=False)
    _publish(repo, _git(repo, "rev-parse", "HEAD~2"))
    reading = anchor_floor.read_committed_durability_anchor_floor(
        repo, at_commit=head
    )
    assert reading.verdict == anchor_floor.FLOOR_UNVERIFIED
    assert reading.floor is None
    assert reading.errors == [
        "UNVERIFIED: its history tail is not an ancestor of any code-owned "
        "protected ref, so a single writer could have authored it"
    ]


def test_committed_floor_without_any_protected_ref_is_unverified(
    tmp_path: Path,
) -> None:
    """受保護 ref 一支都解析不出來時不得 fail-open,同樣只能得 UNVERIFIED。"""

    repo = _floor_repo(tmp_path)
    _commit_floor(repo, _genesis_armed_floor(), "arm floor", publish=False)
    head = _commit_floor(repo, _advanced_floor(1), "advance floor", publish=False)
    reading = anchor_floor.read_committed_durability_anchor_floor(
        repo, at_commit=head
    )
    assert reading.verdict == anchor_floor.FLOOR_UNVERIFIED
    # E2 F-02:舊字串隱含「是祖先時就證明了需要第二組 capability」,那正是已撤回的
    # 宣稱(module docstring)。訊息只能講它真正能證的那件事。
    assert reading.errors == [
        "UNVERIFIED: no code-owned protected ref resolves in this repository, "
        "so the floor's history tail cannot be pinned to any code-owned ref"
    ]
    assert not any("second capability" in error for error in reading.errors)


def test_committed_floor_rejects_a_non_exact_commit(tmp_path: Path) -> None:
    """P1-2:`at_commit` 在任何 git 呼叫之前逐字驗形狀,不合格不進 subprocess。

    PM 於 git 2.55 實測 `--output=<path>` 這種單 token 會讓既有檔案被**截斷為 0
    bytes** 且 exit 0。這裡用同一個 payload,並斷言哨兵檔案原封不動。
    """

    repo = _floor_repo(tmp_path)
    _commit_floor(repo, _genesis_armed_floor(), "arm floor")
    victim = repo / "victim.txt"
    victim.write_text("SENTINEL-MUST-SURVIVE\n", encoding="ascii")
    # E2 F-04:`"a"*40 + "\n"` 曾經通過 `^[0-9a-f]{40}$`(Python 的 `$` 放行尾端
    # 換行)並真的進了 git argv。git 自己拒 ⇒ 當時仍 fail-closed,但本測試宣稱的
    # 不變量是假的。`fullmatch` + `\Z` 之後,它在碰 subprocess 之前就被拒。
    for injected in (
        "--output=victim.txt", "HEAD", "", "A" * 40, "abc", "a" * 40 + "\n",
        "\n" + "a" * 40, "a" * 40 + "\n" + "b" * 40,
    ):
        reading = anchor_floor.read_committed_durability_anchor_floor(
            repo, at_commit=injected
        )
        assert reading.verdict == anchor_floor.FLOOR_REJECTED
        assert reading.errors == [
            "durability anchor floor requires an exact 40-hex reviewed commit"
        ], injected
    assert victim.read_text(encoding="ascii") == "SENTINEL-MUST-SURVIVE\n"


def test_committed_zero_byte_floor_is_fail_closed(tmp_path: Path) -> None:
    """P1-3:已 commit 的 0-byte floor 曾經是零錯誤 fail-open,回 `(None, [])`。"""

    repo = _floor_repo(tmp_path)
    relative = anchor_floor.durability_anchor_floor_repo_path()
    target = repo / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"")
    _git(repo, "add", relative)
    _git(repo, "commit", "-m", "empty floor")
    head = _publish(repo)
    reading = anchor_floor.read_committed_durability_anchor_floor(
        repo, at_commit=head
    )
    assert reading.verdict == anchor_floor.FLOOR_REJECTED
    assert reading.floor is None
    assert reading.errors == [
        f"commit {head[:12]} durability anchor floor JSON is invalid: "
        "Expecting value: line 1 column 1 (char 0)"
    ]


def test_committed_floor_history_must_begin_with_genesis(tmp_path: Path) -> None:
    """P1-4:orphan branch 上單一 ADVANCED commit 不得鑄出任意世代。"""

    repo = _floor_repo(tmp_path)
    head = _commit_floor(repo, _advanced_floor(7), "forge an advanced floor")
    reading = anchor_floor.read_committed_durability_anchor_floor(
        repo, at_commit=head
    )
    assert reading.verdict == anchor_floor.FLOOR_REJECTED
    assert reading.errors == [
        "durability anchor floor history does not begin with its GENESIS_ARMED "
        "commit"
    ]


def test_committed_floor_rejects_a_non_increasing_generation(tmp_path: Path) -> None:
    # 鏈首必須是創世(P1-4);舊 fixture 直接從 `_advanced_floor(2)` 起頭,等於把
    # 「鏈首不必是 GENESIS_ARMED」這個洞固化成正常行為。
    repo = _floor_repo(tmp_path)
    _commit_floor(repo, _genesis_armed_floor(), "arm floor")
    _commit_floor(repo, _advanced_floor(2), "advance floor")
    head = _commit_floor(repo, _advanced_floor(2, head_suffix="4"), "replay floor")
    reading = anchor_floor.read_committed_durability_anchor_floor(
        repo, at_commit=head
    )
    assert reading.verdict == anchor_floor.FLOOR_REJECTED
    assert reading.floor is None
    assert reading.errors == [
        "durability anchor floor generation is not strictly increasing"
    ]


def test_committed_floor_rejects_a_changed_invariant_field(tmp_path: Path) -> None:
    """M11:`_FLOOR_INVARIANT_FIELDS` 跨歷史不可變。

    線性、嚴格遞增、單一 genesis 全部成立,唯一的違例是 locator 被換掉。
    """

    repo = _floor_repo(tmp_path)
    _commit_floor(repo, _genesis_armed_floor(), "arm floor")
    _commit_floor(repo, _advanced_floor(1), "advance floor")
    switched = _advanced_floor(2, head_suffix="5")
    switched["anchor_locator"] = ANCHOR_LOCATOR + "-switched"
    switched["floor_digest"] = anchor_floor.durability_anchor_floor_digest({
        key: value for key, value in switched.items() if key != "floor_digest"
    })
    head = _commit_floor(repo, switched, "switch the anchor locator")
    reading = anchor_floor.read_committed_durability_anchor_floor(
        repo, at_commit=head
    )
    assert reading.verdict == anchor_floor.FLOOR_REJECTED
    assert reading.errors == [
        "durability anchor floor anchor_locator changed across its history"
    ]


def test_committed_floor_rejects_a_shallow_object_store(tmp_path: Path) -> None:
    """P1-5:shallow clone 讓被 rollback 的那段歷史整段從走訪中消失。"""

    repo = _floor_repo(tmp_path)
    _commit_floor(repo, _genesis_armed_floor(), "arm floor")
    _commit_floor(repo, _advanced_floor(2), "advance floor")
    _commit_floor(repo, _advanced_floor(1, head_suffix="7"), "roll the floor back")
    shallow = tmp_path / "shallow"
    _git(repo, "clone", "-q", "--depth", "1", f"file://{repo}", str(shallow))
    _git(shallow, "update-ref", anchor_floor._PROTECTED_ANCESTOR_REFS[0], "HEAD")
    reading = anchor_floor.read_committed_durability_anchor_floor(
        shallow, at_commit=_git(shallow, "rev-parse", "HEAD")
    )
    assert reading.verdict == anchor_floor.FLOOR_REJECTED
    assert reading.errors == [
        "durability anchor floor cannot be read from a shallow repository"
    ]


def test_committed_floor_rejects_a_replace_ref_object_store(tmp_path: Path) -> None:
    """P1-5:replace ref 可以把任一 commit 的內容整個換掉。"""

    repo = _floor_repo(tmp_path)
    _commit_floor(repo, _genesis_armed_floor(), "arm floor")
    head = _commit_floor(repo, _advanced_floor(1), "advance floor")
    _git(repo, "update-ref", "refs/replace/" + head, head)
    reading = anchor_floor.read_committed_durability_anchor_floor(
        repo, at_commit=head
    )
    assert reading.verdict == anchor_floor.FLOOR_REJECTED
    assert reading.errors == [
        "durability anchor floor cannot be read from a repository that "
        "rewrites objects through replace refs"
    ]


def test_committed_floor_ignores_an_ambient_git_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1-6:ambient `GIT_DIR` 曾經蓋過 `-C`,讓驗證器讀到攻擊者 repo 且零錯誤。"""

    honest = _floor_repo(tmp_path / "honest")
    _commit_floor(honest, _genesis_armed_floor(), "arm floor")
    head = _commit_floor(honest, _advanced_floor(1), "advance floor")
    attacker = _floor_repo(tmp_path / "attacker")
    _commit_floor(attacker, _genesis_armed_floor(), "arm forged floor")
    _commit_floor(attacker, _advanced_floor(9, head_suffix="9"), "forge gen 9")
    monkeypatch.setenv("GIT_DIR", str(attacker / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(attacker))
    reading = anchor_floor.read_committed_durability_anchor_floor(
        honest, at_commit=head
    )
    assert reading.verdict == anchor_floor.FLOOR_VERIFIED
    assert reading.floor is not None
    assert reading.floor["floor_generation"] == 1


def test_committed_floor_rejects_a_second_genesis(tmp_path: Path) -> None:
    """想第二次進 genesis,必須 commit 一份把 generation 退回 0 的 floor。"""

    repo = _floor_repo(tmp_path)
    _commit_floor(repo, _genesis_armed_floor(), "arm floor")
    _commit_floor(repo, _advanced_floor(1), "advance floor")
    head = _commit_floor(repo, _genesis_armed_floor(), "re-arm floor")
    reading = anchor_floor.read_committed_durability_anchor_floor(
        repo, at_commit=head
    )
    assert reading.floor is None
    assert (
        "durability anchor floor re-enters GENESIS_ARMED after its first commit"
    ) in reading.errors, reading.errors


def test_committed_floor_rejects_a_forked_history(tmp_path: Path) -> None:
    """merge topology 下兩份互不為祖先的 floor commit ⇒ 順序歧義,fail-closed。"""

    repo = _floor_repo(tmp_path)
    _commit_floor(repo, _genesis_armed_floor(), "arm floor")
    base = _git(repo, "rev-parse", "HEAD")
    _commit_floor(repo, _advanced_floor(1), "floor on main")
    main_head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "-b", "sibling", base)
    _commit_floor(repo, _advanced_floor(2), "floor on sibling")
    _git(repo, "checkout", "-q", "-")
    _git(repo, "merge", "-q", "--no-edit", "-X", "theirs", "sibling")
    head = _publish(repo)
    assert head != main_head
    reading = anchor_floor.read_committed_durability_anchor_floor(
        repo, at_commit=head
    )
    assert reading.floor is None
    assert (
        "durability anchor floor history is not a single ancestor chain"
    ) in reading.errors, reading.errors


def test_committed_floor_tail_byte_check_is_reachable_through_its_seam(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M10:尾端 byte-for-byte 在祖先鏈為真時不可孤立觸發(defense-in-depth)。

    `at_commit` 選一個**不觸碰 floor** 的後續 commit,於是鏈內 `show` 用的是鏈尾
    SHA、尾端 `show` 用的是 `at_commit`,兩者可分辨;monkeypatch 只改後者。真實
    git 下兩次必然回同一份 blob,所以這條只能在 seam 層測——但它不是沉默的覆蓋債。
    """

    repo = _floor_repo(tmp_path)
    _commit_floor(repo, _genesis_armed_floor(), "arm floor")
    _commit_floor(repo, _advanced_floor(1), "advance floor")
    head = _commit(repo, "unrelated.txt", "unrelated\n", "unrelated change")
    _publish(repo, head)
    real_verified = anchor_floor._verified_bytes

    def tampered(repo_root: Path, path: str, *, at_commit: str) -> bytes:
        raw = real_verified(repo_root, path, at_commit=at_commit)
        return raw + b" " if at_commit.startswith(head) else raw

    # round-7:floor 的 blob 讀取由 `_git_bytes(..., "show", ...)` 改走
    # `_verified_bytes`(位元組必須對 tree 記錄的 object id 重算比對),所以縫在這裡。
    # 這也讓本測試的定位更清楚:真實路徑上這種分歧**已經不可能**——`show` 回不同位元組
    # 會被雜湊比對擋掉——所以尾端 byte-for-byte 純粹是 defense-in-depth,而本測試證的是
    # 它仍然可達、不是死碼。
    monkeypatch.setattr(anchor_floor, "_verified_bytes", tampered)
    reading = anchor_floor.read_committed_durability_anchor_floor(
        repo, at_commit=head
    )
    assert reading.verdict == anchor_floor.FLOOR_REJECTED
    assert reading.errors == [
        "durability anchor floor at the reviewed commit differs byte-for-byte "
        "from its own history tail"
    ]


def test_advanced_floor_rejects_a_replayed_generation(tmp_path: Path) -> None:
    """M14:ADVANCED floor 下 `anchor_generation == floor_generation` 是重放。

    genesis 分支另有 `generation != 1` 的硬檢查,只有 ADVANCED 這一支裸露。
    """

    floor = _advanced_floor(4)
    errors = anchor_floor.durability_anchor_floor_errors(
        {
            "anchor_locator": floor["anchor_locator"],
            "offhost_replica_locator": floor["offhost_replica_locator"],
            "anchor_generation": floor["floor_generation"],
            "previous_anchor_head_digest": "sha256:" + "8" * 64,
        },
        floor=floor,
        label="replayed anchor",
    )
    assert (
        "replayed anchor generation does not strictly exceed the committed floor"
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


def _graft_file(repo: Path) -> Path:
    common = Path(_git(repo, "rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = repo / common
    return common / "info" / "grafts"


def test_committed_floor_rejects_a_grafts_file(tmp_path: Path) -> None:
    """E2 F-01:grafts 是 replace ref 的前身,舊版只查後者。

    E2 與 E3 對此互相矛盾,E1 於 git 2.55 實測裁定 **E2 對**:
    - E2 形(`<rollback> <genesis>`)把中間那筆 gen=2 從 `--full-history` 走訪裡整個
      移除,同一份被 rollback 的 repo 由 REJECTED 翻成 **VERIFIED gen=1**,而且照樣
      通過受保護 ref 檢查——這才是危險形態。
    - E3 形(只把創世變成 root)不改動 floor 觸碰序,本來就 REJECTED。
    修法後兩種構造都必須 fail-closed,而且理由是 grafts 檔案本身而非某一種寫法。
    """

    repo = _floor_repo(tmp_path)
    genesis = _commit_floor(repo, _genesis_armed_floor(), "arm floor")
    _commit_floor(repo, _advanced_floor(2), "advance floor to 2")
    head = _commit_floor(repo, _advanced_floor(1, head_suffix="7"), "roll back to 1")
    # 控制組:沒有 grafts 時,回退是被 generation 規則抓到的。
    assert anchor_floor.read_committed_durability_anchor_floor(
        repo, at_commit=head
    ).errors == [
        "durability anchor floor generation is not strictly increasing"
    ]
    grafts = _graft_file(repo)
    grafts.parent.mkdir(parents=True, exist_ok=True)
    grafts.write_text(f"{head} {genesis}\n", encoding="ascii")
    grafted = anchor_floor.read_committed_durability_anchor_floor(
        repo, at_commit=head
    )
    assert grafted.verdict == anchor_floor.FLOOR_REJECTED
    assert grafted.floor is None
    assert (
        "durability anchor floor cannot be read from a repository that "
        "rewrites commit parentage through a grafts file"
    ) in grafted.errors, grafted.errors
    # E3 形:同一條檢查一樣擋得住,不需要辨認寫法。
    grafts.write_text(f"{genesis}\n", encoding="ascii")
    assert (
        "durability anchor floor cannot be read from a repository that "
        "rewrites commit parentage through a grafts file"
    ) in anchor_floor.read_committed_durability_anchor_floor(
        repo, at_commit=head
    ).errors


def test_committed_floor_rejects_a_promisor_partial_clone(tmp_path: Path) -> None:
    """E3-D:partial clone 不是 shallow,舊版放行後 `git show` 會走網路抓 blob。"""

    repo = _floor_repo(tmp_path)
    _commit_floor(repo, _genesis_armed_floor(), "arm floor")
    _commit_floor(repo, _advanced_floor(1), "advance floor")
    _git(repo, "config", "uploadpack.allowFilter", "true")
    partial = tmp_path / "partial"
    _git(
        repo, "clone", "-q", "--no-local", "--filter=blob:none",
        f"file://{repo}", str(partial),
    )
    _git(partial, "update-ref", anchor_floor._PROTECTED_ANCESTOR_REFS[0], "HEAD")
    # 前提:promisor clone 自報「不是 shallow」,所以舊的那條檢查守不住。
    assert _git(partial, "rev-parse", "--is-shallow-repository") == "false"
    reading = anchor_floor.read_committed_durability_anchor_floor(
        partial, at_commit=_git(partial, "rev-parse", "HEAD")
    )
    assert reading.verdict == anchor_floor.FLOOR_REJECTED
    assert (
        "durability anchor floor cannot be read from a promisor partial clone"
    ) in reading.errors, reading.errors


def test_committed_floor_never_resolves_git_from_the_ambient_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E3-A:ambient `PATH` 曾經決定哪個二進位被當成 `git` 執行(RCE)。

    PM 實測:把假 `git` 放到 PATH 最前面,`read_committed_durability_anchor_floor`
    會真的執行它(uid=501),E3 用完整 stub 應答 7 次呼叫後拿到 `VERIFIED gen=4242`
    且 repo_root 根本不存在。此處的哨兵檔案是唯一判準:被執行過就必然留下痕跡。
    """

    repo = _floor_repo(tmp_path)
    _commit_floor(repo, _genesis_armed_floor(), "arm floor")
    head = _commit_floor(repo, _advanced_floor(1), "advance floor")
    hostile = tmp_path / "hostile-bin"
    hostile.mkdir()
    sentinel = tmp_path / "hostile-git-was-executed"
    fake = hostile / "git"
    fake.write_text(
        "#!/bin/sh\n"
        f"echo executed >> {sentinel}\n"
        'case "$*" in *--is-shallow-repository*) echo false ;; esac\n'
        "exit 0\n",
        encoding="ascii",
    )
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{hostile}{os.pathsep}{os.environ.get('PATH', '')}")
    reading = anchor_floor.read_committed_durability_anchor_floor(
        repo, at_commit=head
    )
    assert not sentinel.exists(), sentinel.read_text(encoding="ascii")
    assert reading.verdict == anchor_floor.FLOOR_VERIFIED
    assert reading.floor is not None and reading.floor["floor_generation"] == 1
    # argv[0] 亦為 code-owned 絕對路徑,不只是靠 env 的 PATH。
    argv = schema_core.git_argv(repo, "rev-parse", "HEAD")
    assert argv[0].startswith("/") and str(hostile) not in argv[0]
    assert schema_core.git_subprocess_env()["PATH"] == os.pathsep.join(
        schema_core._GIT_SEARCH_PATH
    )
    assert str(hostile) not in schema_core.git_subprocess_env()["PATH"]
    assert schema_core.git_subprocess_env()["LC_ALL"] == "C"


def _arm_hostile_subject(repo: Path, tmp_path: Path) -> tuple[Path, Path]:
    """把被驗者的每一個可寫執行面都武裝起來,並讓 git **完全打不開**這個 repo。

    回 ``(fsmonitor 哨兵, clean-filter 哨兵)``。三件事一起做:

    - `core.fsmonitor` 與 `filter.<drv>.clean`(經已 commit 的 `.gitattributes`)——
      R4-1 記的兩條任意程式執行路徑。E1 於 git 2.55 實測:同 uid 下對這個 repo 跑
      `git status --porcelain=v1 --untracked-files=all`,兩個哨兵都會被寫出來。
    - `core.repositoryformatversion = 99` 封死 repo:此後任何把它當 repository 打開
      的 git 呼叫一律 `fatal: Expected git repo version <= 1, found 99`。

    最後這一條是本組測試的判準,也是為什麼不用 `GIT_TEST_ASSUME_DIFFERENT_OWNER`:
    那個 knob 對**每一個** repo 說謊,連驗證器自建的 code-owned view 都會被它毒到,
    所以它代表不了「被驗者屬於別的 uid」這個拓撲。而 version-99 與 dubious ownership
    **在同一步失敗**(repository discovery),且它連 protected 域的 `safe.directory`
    都救不回來——比差異 uid 更強。因此「事實仍然取得到」就證明了驗證面根本沒有把
    被驗者當 repository 打開,差異 uid 拓撲隨之成立。
    """

    fsmonitor_sentinel = tmp_path / "fsmonitor-was-executed"
    clean_sentinel = tmp_path / "clean-filter-was-executed"
    hook = tmp_path / "fsmonitor-hook.sh"
    hook.write_text(
        "#!/bin/sh\n" f"echo executed >> {fsmonitor_sentinel}\n" "exit 0\n",
        encoding="ascii",
    )
    hook.chmod(0o755)
    clean = tmp_path / "clean-filter.sh"
    clean.write_text(
        "#!/bin/sh\n" f"echo executed >> {clean_sentinel}\n" "cat\n", encoding="ascii"
    )
    clean.chmod(0o755)
    (repo / ".gitattributes").write_text("* filter=hostile\n", encoding="ascii")
    _git(repo, "add", ".gitattributes")
    _git(repo, "commit", "-qm", "arm hostile attributes")
    _git(repo, "config", "core.fsmonitor", str(hook))
    _git(repo, "config", "filter.hostile.clean", str(clean))
    _git(repo, "config", "filter.hostile.smudge", str(clean))
    # 髒一個受 attributes 覆蓋的追蹤檔:clean filter 只在 git 需要重新雜湊工作樹
    # 內容時才跑,乾淨的樹驗不到那條路。
    (repo / "seed.txt").write_text("dirtied by the subject\n", encoding="ascii")
    config = repo / ".git" / "config"
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "repositoryformatversion = 0", "repositoryformatversion = 99"
        ),
        encoding="utf-8",
    )
    probe = subprocess.run(
        [schema_core.git_executable(), "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        env=schema_core.git_subprocess_env(),
    )
    assert probe.returncode != 0, "the subject repo must be unopenable by git"
    assert "found 99" in probe.stderr, probe.stderr
    return fsmonitor_sentinel, clean_sentinel


def test_committed_floor_reads_a_repository_git_refuses_to_open(
    tmp_path: Path,
) -> None:
    """E3 round-5:差異 uid 拓撲底下**事實仍然取得到**,而且執行面一次都沒被碰。

    這是本輪的 fail-first。改動前:`_git_bytes`/`_git_ok` 直接 `git -C <被驗者>`,
    被封死的 repo 一句事實也讀不出來 ⇒ `FLOOR_REJECTED`。改動後:git 跑在
    `code_owned_object_view` 裡,被驗者只以 `objects/info/alternates` 提供物件,
    於是同一份 floor 照樣讀成 `FLOOR_VERIFIED`,而 `core.fsmonitor` 與
    `filter.<drv>.clean` 兩個哨兵都不存在——不是「沒被觸發」,是驗證面**沒有任何
    一條路**會去讀那份 config(見 `_arm_hostile_subject` 的判準說明)。
    """

    repo = _floor_repo(tmp_path)
    _commit_floor(repo, _genesis_armed_floor(), "arm floor")
    head = _commit_floor(repo, _advanced_floor(1), "advance floor")
    fsmonitor_sentinel, clean_sentinel = _arm_hostile_subject(repo, tmp_path)

    reading = anchor_floor.read_committed_durability_anchor_floor(
        repo, at_commit=head
    )
    assert reading.verdict == anchor_floor.FLOOR_VERIFIED, reading.errors
    assert reading.floor is not None and reading.floor["floor_generation"] == 1
    assert not fsmonitor_sentinel.exists(), fsmonitor_sentinel.read_text(
        encoding="ascii"
    )
    assert not clean_sentinel.exists(), clean_sentinel.read_text(encoding="ascii")


def test_review_manifest_reads_a_repository_git_refuses_to_open(
    tmp_path: Path,
) -> None:
    """同一條 fail-first 施加在 review 面:blob manifest 也必須走 view。

    `s2e_review` 每一條 revision 都是 candidate 的 `reviewed_head`,工作樹本來就不
    參與;改動前它仍然 `git -C <被驗者> ls-tree/show`,所以被驗者的 config 照樣進場。
    """

    repo = _floor_repo(tmp_path)
    (repo / "TODO.md").write_text("# todo\n", encoding="utf-8")
    _git(repo, "add", "TODO.md")
    _git(repo, "commit", "-qm", "add a governed path")
    head = _git(repo, "rev-parse", "HEAD")
    fsmonitor_sentinel, clean_sentinel = _arm_hostile_subject(repo, tmp_path)

    listing = s2e_review._git(
        repo, "ls-tree", "-r", "--name-only", head
    ).stdout.splitlines()
    assert "TODO.md" in listing, listing
    assert s2e_review._git_bytes(repo, "show", f"{head}:TODO.md") == b"# todo\n"
    assert not fsmonitor_sentinel.exists()
    assert not clean_sentinel.exists()


def test_verification_face_never_hands_the_subject_repository_to_git(
    tmp_path: Path,
) -> None:
    """驗證面的每一次 git 呼叫,repository 引數都必須是 code-owned view。

    `_arm_hostile_subject` 證的是「被驗者的 config 沒被讀」;這一條證的是更前面的
    那一步——**被驗者的路徑根本沒有出現在任何 repository 位置**。兩條合起來就是
    差異 uid 拓撲的完整主張:ownership 檢查只在 repository discovery 觸發,而我們
    從不 discover 被驗者。
    """

    repo = _floor_repo(tmp_path)
    _commit_floor(repo, _genesis_armed_floor(), "arm floor")
    head = _commit_floor(repo, _advanced_floor(1), "advance floor")
    resolved_repo = str(Path(repo).resolve())
    real_run = subprocess.run
    seen: list[list[str]] = []

    def spy(argv, *args, **kwargs):
        if isinstance(argv, (list, tuple)):
            seen.append([str(token) for token in argv])
        return real_run(argv, *args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(subprocess, "run", spy)
        reading = anchor_floor.read_committed_durability_anchor_floor(
            repo, at_commit=head
        )
    assert reading.verdict == anchor_floor.FLOOR_VERIFIED, reading.errors
    assert seen, "no git subprocess was observed"
    for argv in seen:
        assert "-C" in argv, argv
        repository = argv[argv.index("-C") + 1]
        assert repository != resolved_repo and not repository.startswith(
            resolved_repo + os.sep
        ), argv
        # `git status` 需要工作樹,view 沒有;`--git-dir`/`--work-tree` 是把被驗者
        # 從側門接回來的唯二形狀;`safe.directory` 是 round-4 移除的那條死路。
        assert "status" not in argv, argv
        assert not any(
            token.startswith(("--git-dir", "--work-tree")) for token in argv
        ), argv
        assert not any("safe.directory" in token for token in argv), argv


def test_object_view_is_private_and_carries_no_executable_surface(
    tmp_path: Path,
) -> None:
    """view 的每一項性質都是判定的前提,逐條釘住。"""

    repo = _floor_repo(tmp_path)
    objects = (Path(repo) / ".git" / "objects").resolve()
    with schema_core.code_owned_object_view(repo) as view:
        info = os.lstat(view)
        assert stat.S_ISDIR(info.st_mode)
        assert info.st_uid == os.geteuid()
        assert stat.S_IMODE(info.st_mode) == 0o700
        # config 逐位元組由代碼寫出:沒有 remote(promisor 抓不到網路)、沒有
        # fsmonitor、沒有 filter driver。
        assert (view / "config").read_text(
            encoding="utf-8"
        ) == schema_core._OBJECT_VIEW_CONFIG
        # round-5 拆分波:object store 是**物化**的,不是掛 alternates。裡面只有
        # fanout 目錄與 pack/*.{pack,idx} 的 symlink;沒有 `info/` 就沒有 alternates、
        # 沒有 commit-graph,沒有 midx/bitmap ⇒ P0-B 的競爭窗口與 P0-C 的圖偽造面
        # 在 view 裡**不存在**,不是被檢查掉。
        store = view / "objects"
        assert not (store / "info").exists(), "a materialized store must carry no info/"
        assert not (store / "pack" / "multi-pack-index").exists()
        linked = sorted(entry.name for entry in store.iterdir())
        assert linked, linked
        for name in linked:
            assert name == "pack" or re.fullmatch(r"[0-9a-f]{2}", name), name
            if name == "pack":
                continue
            # round-7:fanout 是 view 自己的**真目錄**,不是指向被驗者目錄的 symlink。
            # 逐目錄連結會讓 store 在 view 生命週期內保持活的,而且看不到目錄**內**
            # 的 symlink——E2/E3 各自實測那兩條都可利用。
            fanout = store / name
            assert fanout.is_dir() and not fanout.is_symlink(), name
            for entry in fanout.iterdir():
                assert entry.is_symlink(), entry
                assert entry.resolve() == (objects / name / entry.name).resolve()
        if (store / "pack").exists():
            for entry in (store / "pack").iterdir():
                assert entry.name.endswith((".pack", ".idx")), entry.name
                assert entry.is_symlink()
        assert not (view / "hooks").exists()
        assert not (view / "info" / "grafts").exists()
        assert list((view / "refs").iterdir()) == []

        def _in_view(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                schema_core.git_argv(view, *args),
                capture_output=True,
                text=True,
                env=schema_core.git_subprocess_env(),
            )

        # view 不替被驗者解析任何名字:HEAD 指向一個不存在的分支。
        # E1 於 git 2.55 實測:**裸** `rev-parse HEAD` 在解不出來時回 rc=0 並原樣印回
        # `HEAD`(fail-open 形狀),所以本家族每一條名字解析都走 `--verify`,或先由
        # `read_subject_ref` 換成 40-hex。這一條把該陷阱本身釘住。
        assert _in_view("rev-parse", "--verify", "HEAD").returncode != 0
        assert _in_view("rev-parse", "HEAD").stdout.strip() == "HEAD"
        # `git status` 在 view 裡是**結構上**跑不起來的,不是靠自律不去呼叫。
        status = _in_view("status", "--porcelain=v1")
        assert status.returncode != 0
        assert "work tree" in status.stderr, status.stderr
        captured = Path(view)
    assert not captured.exists(), "the view must not outlive its context"


def test_object_view_refuses_a_temp_ancestor_an_attacker_could_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`TMPDIR` 是 ambient 值;祖先鏈不安全時必須拒建 view,而不是照建。

    mkdtemp 的目錄本身永遠是 0700,但擁有父目錄的人可以把它整個換掉(TOCTOU),
    於是 view 的 `config` 在建立與使用之間被替換 ⇒ `core.fsmonitor` 從側門回來。
    這裡用「world-writable 且**沒有** sticky bit」的父目錄複現該形狀(`/tmp` 的
    1777 帶 sticky,所以正常路徑不受影響)。

    注意要改的是 `tempfile.tempdir` 而不是 `TMPDIR`:`gettempdir()` 只讀一次環境變數
    就把結果快取起來,行程中後來的 `setenv` 對 `mkdtemp` 沒有作用(初版就是這樣寫的,
    測試「通過」但根本沒走到那條路)。
    """

    import tempfile

    repo = _floor_repo(tmp_path)
    unsafe = tmp_path / "swappable-tmp"
    unsafe.mkdir()
    unsafe.chmod(0o777)
    monkeypatch.setattr(tempfile, "tempdir", str(unsafe))
    with pytest.raises(OSError) as failure:
        with schema_core.code_owned_object_view(repo):
            pass
    assert "sticky" in str(failure.value), str(failure.value)


def test_object_store_hygiene_is_decided_from_the_filesystem(tmp_path: Path) -> None:
    """五條衛生判定改由檔案系統得出,不再問被驗者的 git,typed reason 逐條保留。

    舊實作用 `git -C <被驗者> rev-parse/for-each-ref/config` 問這些,而那次呼叫本身就是
    「把外人的目錄當 repository 打開」——本輪要消掉的動作。改 stat 之後判定同樣完整。
    """

    repo = _floor_repo(tmp_path)
    git_dir = Path(repo) / ".git"
    assert anchor_floor._object_store_errors(repo) == []

    def _only_reason(fragment: str) -> None:
        reasons = anchor_floor._object_store_errors(repo)
        assert any(fragment in reason for reason in reasons), reasons

    (git_dir / "shallow").write_text("0" * 40 + "\n", encoding="ascii")
    _only_reason("shallow repository")
    (git_dir / "shallow").unlink()

    (git_dir / "info").mkdir(exist_ok=True)
    (git_dir / "info" / "grafts").write_text("", encoding="ascii")
    _only_reason("grafts file")
    (git_dir / "info" / "grafts").unlink()

    replace = git_dir / "refs" / "replace"
    replace.mkdir(parents=True)
    (replace / ("a" * 40)).write_text("b" * 40 + "\n", encoding="ascii")
    _only_reason("replace refs")
    (replace / ("a" * 40)).unlink()

    pack = git_dir / "objects" / "pack"
    pack.mkdir(parents=True, exist_ok=True)
    (pack / "pack-deadbeef.promisor").write_text("", encoding="ascii")
    _only_reason("promisor partial clone")
    (pack / "pack-deadbeef.promisor").unlink()

    # 巢狀 alternates 會被 git **遞移**跟隨,讓 root 驗證器去讀被驗者自己讀不到的
    # 物件庫(confused deputy 讀取放大)。物化之後 view 不再需要「拒建」——它根本
    # 不讀那個檔,所以照常建得起來(P0-B 的競爭測試正是靠這一點);typed reason 仍在,
    # 因為缺物件的失敗訊息遠不如具名理由有用。
    alternates = git_dir / "objects" / "info" / "alternates"
    alternates.parent.mkdir(parents=True, exist_ok=True)
    alternates.write_text("/somewhere/else/objects\n", encoding="ascii")
    _only_reason("chains to another store through alternates")
    with schema_core.code_owned_object_view(repo) as view:
        assert not (view / "objects" / "info").exists()
    alternates.unlink()

    # config 的 promisor 掃描只認 git 真正的鍵形:remote 名稱或 URL 裡的巧合字樣
    # 不得誤觸(否則衛生判定會把正常 repo 判紅)。
    _git(repo, "config", "remote.partialclone-mirror.url", "https://promisor.invalid/x")
    assert anchor_floor._object_store_errors(repo) == []


def test_only_the_generation_face_may_read_a_working_tree(tmp_path: Path) -> None:
    """`git status` 只准出現在 generation 面,且必須先過 own-checkout 閘。

    R4-1 的提權形狀是「驗證器對外人所有的樹跑 `git status`」。驗證面已無工作樹可讀
    (view 沒有 worktree);剩下的一處在 `_require_own_clean_checkout`,而它先呼叫
    `git_own_checkout_guard`。這條把「只有一處」與「那一處守著閘」一起釘住。
    """

    call_pattern = re.compile(r"git_argv\(\s*(\w+)\s*,")
    modules = (schema_core, git_view, anchor_floor, s2e_review, s2e, consumption_module)
    status_calls = [
        (module.__name__, line.strip())
        for module in modules
        for line in Path(module.__file__).read_text(encoding="utf-8").splitlines()
        if "git_argv(" in line and '"status"' in line
    ]
    assert len(status_calls) == 1, status_calls
    assert status_calls[0][1].startswith("git_argv(own,"), status_calls
    guarded = inspect.getsource(schema_core.require_own_clean_checkout)
    assert "git_own_checkout_guard" in guarded
    assert guarded.index("git_own_checkout_guard") < guarded.index('"status"')
    # 每一次 git 呼叫的 repository 引數都必須是 `view`;唯一的例外是 generation 面
    # 那一支 `own`(已由 `git_own_checkout_guard` 驗過同 uid)。view 沒有工作樹,
    # 所以驗證面跑不出 `git status`——那是結構上的不可能,不是自律。
    for module in modules:
        text = Path(module.__file__).read_text(encoding="utf-8")
        repositories = set(call_pattern.findall(text))
        assert repositories <= {"view", "own"}, (module.__name__, repositories)


def test_gitdir_pointer_redirect_is_pinned_to_the_subjects_own_uid(
    tmp_path: Path,
) -> None:
    """E3 round-5 P0-A:`.git` 檔的 `gitdir:` 指標曾能把驗證器帶去任何它讀得到的 repo。

    E3 實測 root 驗證器因此讀出 victim 的位元組,而 `s2e_consumption` 的 consume-once
    ledger 路徑由同一條指標導出 ⇒ 防重放帳本的位置也由被驗者選。git 的 ownership 檢查
    本來是那道意外屏障,移除它就得自己補。收法是 **owner pin**:指標目標必須屬於
    `repo_root` 自己的 owner。

    **這條測試同時釘住尚未收掉的那一半**,免得它躲在設計文件裡:owner pin 允許的目標
    恰好是被驗者所有的目錄,所以**同 uid 之間的重指仍然成立**。round-6 曾加一條
    linked-worktree 回指不變式想擋它,兩位複核者各以一行(把回指寫進目標)證明那是空的,
    而代價是拒絕 `--separate-git-dir` 與 submodule 工作樹,所以整條已移除。
    """

    subject = _floor_repo(tmp_path / "subject")
    (Path(subject) / ".git").rename(Path(subject) / ".git.real")

    # 跨 uid:被拒。`/usr` 屬 root,是這台機器上不需要提權就能指到的真實外人目錄。
    (Path(subject) / ".git").write_text("gitdir: /usr\n", encoding="ascii")
    with pytest.raises(OSError) as failure:
        git_view.subject_layout(subject)
    assert "not by the subject repository's owner uid" in str(failure.value)
    assert git_view.read_subject_ref(subject) is None
    assert git_view.subject_object_store_findings(subject) == [
        git_view.STORE_UNREADABLE
    ]

    # 同 uid:**目前仍然通得過**,這是具名未收的殘留(設計檔 §6 P0-A)。斷言它成立,
    # 是為了讓「收掉了」這件事必須靠改測試來宣告,不能靠改文件。
    peer = _floor_repo(tmp_path / "peer")
    (Path(subject) / ".git").write_text(
        f"gitdir: {Path(peer).resolve()}/.git\n", encoding="ascii"
    )
    assert git_view.subject_layout(subject).git_dir == (Path(peer).resolve() / ".git")

    # 合法佈局不得被誤殺——閘不能是把功能關掉。
    layout = git_view.subject_layout(ROOT)
    assert layout.git_dir.exists() and layout.objects.is_dir()
    assert git_view.read_subject_ref(ROOT) is not None


def test_materialized_store_excludes_the_graph_surfaces_git_does_not_verify(
    tmp_path: Path,
) -> None:
    """E3 round-5 P0-C:攻擊者撰寫的 commit-graph 不得改變 `--full-history` 的走訪。

    fail-first。掛 alternates 的初版會讓 git 從被驗者的 `objects/info/` 載入
    commit-graph——那**不是**內容定址面,git 不對物件複驗。E3 實測改 4 個位元組即可讓
    一筆 floor revision 從走訪中消失,而 `_object_store_errors` 回 `[]`、
    `merge-base --is-ancestor` 仍 True、`git commit-graph verify` 也 rc=0。

    物化之後 view 的 `objects/` 沒有 `info/`,那個面在 view 裡不存在。這裡不偽造圖
    (偽造要改 CDAT 的位元組偏移,脆弱),而是釘住更強的性質:**即使被驗者有
    commit-graph 與 multi-pack-index,view 都不會載入它們,走訪結果等於誠實歷史。**
    """

    repo = _floor_repo(tmp_path)
    heads = [
        _commit(repo, "docs/floor.txt", f"gen {index}\n", f"gen {index}")
        for index in range(4)
    ]
    subprocess.run(
        [schema_core.git_executable(), "-C", str(repo), "commit-graph", "write",
         "--reachable"],
        check=True, capture_output=True, env=schema_core.git_subprocess_env(),
    )
    assert (Path(repo) / ".git" / "objects" / "info" / "commit-graph").exists()

    with schema_core.code_owned_object_view(repo) as view:
        assert not (view / "objects" / "info").exists()
        walk = subprocess.run(
            schema_core.git_argv(
                view, "log", "--format=%H", "--reverse", "--topo-order",
                "--full-history", "--end-of-options", heads[-1], "--", "docs/floor.txt",
            ),
            capture_output=True, text=True, env=schema_core.git_subprocess_env(),
        )
    assert walk.returncode == 0, walk.stderr
    assert walk.stdout.split() == heads, (walk.stdout.split(), heads)


def test_materialized_store_has_no_window_for_injected_alternates(
    tmp_path: Path,
) -> None:
    """E3 round-5 P0-B:巢狀 alternates 的拒絕曾是 check-then-use,400 次 leaked 134。

    初版在 `exists()` 與 git 真的開檔之間隔著 mkdtemp、祖先驗證、三次寫入與 spawn,
    而被驗者擁有 `objects/info/`。物化之後 view 根本沒有 `info/`,所以沒有窗口可競爭
    ——這裡在被驗者持續寫入 alternates 的同時反覆建 view,斷言一次都不洩漏。
    """

    victim = _floor_repo(tmp_path / "victim")
    (Path(victim) / "SECRET.md").write_text("victim bytes\n", encoding="ascii")
    _git(victim, "add", "SECRET.md")
    victim_head = _commit(victim, "SECRET.md", "victim bytes\n", "victim secret")
    subject = _floor_repo(tmp_path / "subject")
    alternates = Path(subject) / ".git" / "objects" / "info" / "alternates"
    alternates.parent.mkdir(parents=True, exist_ok=True)
    victim_objects = str((Path(victim) / ".git" / "objects").resolve())

    stop = threading.Event()

    def racer() -> None:
        while not stop.is_set():
            try:
                alternates.write_text(victim_objects + "\n", encoding="ascii")
                alternates.unlink()
            except OSError:
                pass

    worker = threading.Thread(target=racer, daemon=True)
    worker.start()
    try:
        leaked = 0
        for _ in range(60):
            with schema_core.code_owned_object_view(subject) as view:
                assert not (view / "objects" / "info").exists()
                probe = subprocess.run(
                    schema_core.git_argv(
                        view, "cat-file", "-p", f"{victim_head}:SECRET.md"
                    ),
                    capture_output=True, text=True,
                    env=schema_core.git_subprocess_env(),
                )
                leaked += int("victim bytes" in probe.stdout)
    finally:
        stop.set()
        worker.join(timeout=5)
    assert leaked == 0, f"the foreign object store leaked through {leaked} times"


def _forge_loose_object(repo: Path, oid: str, payload: bytes) -> None:
    """把 `oid` 的**唯一**一份 loose 物件換成 `payload`(zlib blob 形)。

    git 只在 `fsck`/`verify-pack` 複驗物件雜湊,blob 讀取路徑不驗,所以這之後
    `git cat-file -p <oid>` 會照樣回 `payload`。loose 物件是 0444,所以先 chmod——
    被驗者擁有自己的 repo,這只是測試機制,不是額外能力。
    """

    import zlib

    target = Path(repo) / ".git" / "objects" / oid[:2] / oid[2:]
    target.chmod(0o644)
    target.unlink()
    target.write_bytes(zlib.compress(b"blob %d\x00" % len(payload) + payload))


def test_blob_bytes_must_hash_to_the_object_id_the_tree_records(
    tmp_path: Path,
) -> None:
    """E2/E3 round-6 NEW-P0-1:git 不複驗 blob 雜湊,所以本家族自己驗。

    fail-first。round-6 曾宣稱「剩下能換的只有物件位元組,而那是內容定址的」——兩位
    複核者各自實證推翻。改動前這裡會回攻擊者的位元組並一路進 digest 與 manifest;
    改動後 `commit_blob_bytes`(家族唯一的 blob 讀取原語)對 `cat-file --batch` 標頭裡
    那個 git 從 tree 解出的 object id 重算比對,對不上就當缺席。
    """

    repo = _floor_repo(tmp_path)
    head = _commit(repo, "governed.txt", "HONEST CONTENT\n", "add governed path")
    oid = _git(repo, "rev-parse", f"{head}:governed.txt")
    _forge_loose_object(repo, oid, b"FORGED CONTENT\n")

    # 前提:git 自己確實會把假位元組交出來,否則這條測試證不到東西。
    unverified = subprocess.run(
        [schema_core.git_executable(), "-C", str(repo), "cat-file", "-p", oid],
        capture_output=True, text=True, env=schema_core.git_subprocess_env(),
    )
    assert unverified.returncode == 0 and "FORGED" in unverified.stdout, unverified

    assert schema_core.commit_blob_bytes(
        repo, ["governed.txt"], source_head=head
    ) == {"governed.txt": None}
    assert schema_core.verified_blob_bytes(
        repo, "governed.txt", at_commit=head
    ) is None
    for module in (s2e_review, anchor_floor):
        with pytest.raises(OSError) as failure:
            module._verified_bytes(repo, "governed.txt", at_commit=head)
        assert "hash to the object id" in str(failure.value), module.__name__
    # 家族裡不得再有繞過該原語的 `git show <rev>:<path>`。只掃**代碼**:docstring 本來
    # 就會引用被取代的舊寫法,拿散文當執法面會在下一次改註解時假紅。
    for module in (schema_core, git_view, anchor_floor, s2e_review, s2e):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        literals = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        } - {
            ast.get_docstring(node) or ""
            for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
        }
        assert "show" not in literals, module.__name__


def test_materialized_store_links_objects_not_directories(tmp_path: Path) -> None:
    """E2/E3 round-6 NEW-P0-2:逐目錄 symlink 不夠,改逐物件。

    兩條 fail-first 向量:(a) 被驗者在自己的 fanout 目錄**內**放 symlink 指向別的物件庫
    ——round-6 只驗目錄不是 symlink、不看內容,E2 實測 100% 無競爭洩漏;(b) view 建好之後
    才寫進已鏡射的 fanout——round-6 是逐目錄連結,所以 store 在 view 生命週期內是活的,
    E3 靠預建 256 個空 fanout 讓它必然成立。逐物件物化把兩條都變成結構上不可能。
    """

    victim = _floor_repo(tmp_path / "victim")
    victim_head = _commit(victim, "s.txt", "VICTIM SECRET\n", "victim secret")
    victim_oid = _git(victim, "rev-parse", f"{victim_head}:s.txt")
    subject = _floor_repo(tmp_path / "subject")

    fanout = Path(subject) / ".git" / "objects" / victim_oid[:2]
    fanout.mkdir(parents=True, exist_ok=True)
    (fanout / victim_oid[2:]).symlink_to(
        Path(victim) / ".git" / "objects" / victim_oid[:2] / victim_oid[2:]
    )

    with schema_core.code_owned_object_view(subject) as view:
        mirrored = view / "objects" / victim_oid[:2]
        assert mirrored.is_dir() and not mirrored.is_symlink()
        assert not (mirrored / victim_oid[2:]).exists(), "an object symlink was linked"
        leak = subprocess.run(
            schema_core.git_argv(view, "cat-file", "-p", victim_oid),
            capture_output=True, text=True, env=schema_core.git_subprocess_env(),
        )
        assert leak.returncode != 0 and "VICTIM" not in leak.stdout, leak.stdout

        # 事後注入:view 已建好,對**已鏡射**的 fanout 寫入新物件,view 不得看見。
        # E2 round-8:舊寫法有兩個毛病——`... or True` 是無條件成立的假斷言,而且新物件
        # 的 oid 幾乎不會落在已鏡射的 fanout(實測 60 次 0 中),所以這一半根本沒測到。
        # 改成直接把物件寫進**一個確定已鏡射的** fanout,讓斷言必然承重。
        mirrored_fanouts = sorted(
            entry.name for entry in (view / "objects").iterdir() if entry.name != "pack"
        )
        assert mirrored_fanouts, "no fanout was mirrored, the vector is untestable"
        chosen = mirrored_fanouts[0]
        late = Path(subject) / ".git" / "objects" / chosen / ("f" * 38)
        late.write_bytes(b"late object planted after the view was built")
        assert late.exists()
        assert not (view / "objects" / chosen / ("f" * 38)).exists()


def test_consumption_ledger_resolves_its_common_dir_exactly_once(
    tmp_path: Path,
) -> None:
    """E3 round-6 NEW-P0-3:ledger 路徑曾經來自**未驗證**的第二次讀取。

    `_git_common_dir` 原本是 `subject_common_dir(subject_git_dir(repo_root))` ——同一個
    被驗者可寫的 `<gitdir>/commondir` 讀兩次,第二次無 owner pin、無佈局不變式。E3 racer
    3000 次把 consume-once ledger 重指到任意目錄 555 次(帳本空 ⇒ 重放繞過,且驗證器會
    在攻擊者指定的目錄裡建檔)。現在只解析一次,而且是驗過的那一次。
    """

    tree = ast.parse(inspect.getsource(consumption_module._git_common_dir).lstrip())
    called = [
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    # 恰好一次解析呼叫,而且是驗過的那一支——巢狀兩層即為 P0-3 的形狀。
    assert called == ["subject_common_dir"], called

    # 跨 uid 的 commondir 仍被 owner pin 擋住,且 ledger 面拿到的是同一個判定。
    repo = _floor_repo(tmp_path)
    (Path(repo) / ".git" / "commondir").write_text("/usr\n", encoding="ascii")
    with pytest.raises(OSError) as failure:
        consumption_module._git_common_dir(Path(repo))
    assert "owner uid" in str(failure.value), str(failure.value)

    # 真的 linked worktree 仍要解得出共用 gitdir。
    assert consumption_module._git_common_dir(ROOT) == (
        git_view.subject_layout(ROOT).common_dir
    )


def test_generation_face_refuses_a_foreign_owned_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """外人所有的 checkout 一律大聲拒,而且 git 一次都不會被執行。

    誠實邊界:generation 面**不是**「假設同 uid」——同 uid 是被驗證後才成立的前提。
    """

    repo = _floor_repo(tmp_path)
    real_run = subprocess.run
    calls: list[Any] = []

    def spy(*args, **kwargs):
        calls.append(args)
        return real_run(*args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(subprocess, "run", spy)
        patch.setattr(os, "geteuid", lambda: os.stat(repo).st_uid + 1)
        with pytest.raises(OSError) as failure:
            schema_core.require_own_clean_checkout(repo)
    assert "owned by another uid" in str(failure.value)
    assert calls == [], "a refused generation face must not execute git"


def test_committed_floor_git_calls_are_time_bounded(tmp_path: Path) -> None:
    """E3-D:本模組曾是同家族唯一沒有 `timeout=` 的 git 呼叫者。"""

    repo = _floor_repo(tmp_path)
    _commit_floor(repo, _genesis_armed_floor(), "arm floor")
    head = _commit_floor(repo, _advanced_floor(1), "advance floor")
    real_run = subprocess.run
    seen: list[Any] = []

    def spy(*args, **kwargs):
        seen.append(kwargs.get("timeout"))
        return real_run(*args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(subprocess, "run", spy)
        anchor_floor.read_committed_durability_anchor_floor(repo, at_commit=head)
    assert seen, "no git subprocess was observed"
    assert all(
        isinstance(timeout, (int, float)) and timeout > 0 for timeout in seen
    ), seen
    # 逾時必須被捕捉成 fail-closed 判定,不得裸逸出驗證函式。
    assert subprocess.TimeoutExpired in anchor_floor._GIT_FAILURES or issubclass(
        subprocess.TimeoutExpired, anchor_floor._GIT_FAILURES
    )


def test_committed_floor_admits_a_legitimate_back_merged_history(
    tmp_path: Path,
) -> None:
    """E3-C:`--full-history` 會列出 merge,舊的 32 上界誤殺合法歷史。

    E3 實測合法的 6 次推進在 3 次 back-merge 下列 31 筆、4 次下列 37 筆。此處直接
    構造出超過舊上界的合法歷史,並斷言它 **不是** 被上界擋掉的。
    """

    repo = _floor_repo(tmp_path)
    _git(repo, "branch", "-M", "main")
    _commit_floor(repo, _genesis_armed_floor(), "arm floor", publish=False)
    _git(repo, "checkout", "-q", "-b", "long-lived")
    rounds = 20
    for index in range(rounds):
        _commit_floor(
            repo, _advanced_floor(index + 1), f"branch advance {index}",
            publish=False,
        )
        if index == rounds - 1:
            break
        _git(repo, "checkout", "-q", "main")
        _git(repo, "merge", "-q", "--no-ff", "--no-edit", "long-lived")
        _git(repo, "checkout", "-q", "long-lived")
        _git(repo, "merge", "-q", "--no-ff", "--no-edit", "main")
    head = _publish(repo)
    listed = _git(
        repo, "log", "--format=%H", "--full-history", head, "--",
        anchor_floor.durability_anchor_floor_repo_path(),
    ).split()
    assert len(listed) > 32, len(listed)
    assert len(listed) <= anchor_floor.MAX_FLOOR_HISTORY_COMMITS, len(listed)
    reading = anchor_floor.read_committed_durability_anchor_floor(
        repo, at_commit=head
    )
    assert reading.verdict == anchor_floor.FLOOR_VERIFIED, reading.errors
    assert reading.floor is not None
    assert reading.floor["floor_generation"] == rounds


def test_committed_floor_rejects_a_history_beyond_its_admitted_length(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """上界本身仍必須是 fail-closed 的,只是位置改了。"""

    repo = _floor_repo(tmp_path)
    _commit_floor(repo, _genesis_armed_floor(), "arm floor")
    head = _commit_floor(repo, _advanced_floor(1), "advance floor")
    monkeypatch.setattr(anchor_floor, "MAX_FLOOR_HISTORY_COMMITS", 1)
    reading = anchor_floor.read_committed_durability_anchor_floor(
        repo, at_commit=head
    )
    assert reading.verdict == anchor_floor.FLOOR_REJECTED
    assert reading.errors == [
        "durability anchor floor history exceeds its admitted length"
    ]


def test_floor_verdict_is_typed_beyond_the_module_boundary(tmp_path: Path) -> None:
    """E3-B:出模組一步就只剩無型別 errors,REJECTED 與 UNVERIFIED 被壓成同一種。

    PM 2026-08-04 裁決:UNVERIFIED 仍然擋,但下游必須能區分「偽造的 floor 被拒」與
    「未 merge 因而誠實不可驗」,且不得靠 `"UNVERIFIED: "` 子字串。
    """

    honest = _floor_repo(tmp_path / "unmerged")
    _commit_floor(honest, _genesis_armed_floor(), "arm floor", publish=False)
    unmerged_head = _commit_floor(
        honest, _advanced_floor(1), "advance floor", publish=False
    )
    forged = _floor_repo(tmp_path / "forged")
    forged_head = _commit_floor(forged, _advanced_floor(7), "forge an advanced floor")

    observations = anchor_floor.AnchorGateObservations()
    unmerged_errors = anchor_floor.floor_gate_errors(
        anchor_floor.read_committed_durability_anchor_floor(
            honest, at_commit=unmerged_head
        ),
        label="acceptance review durability anchor floor",
        observations=observations,
    )
    forged_errors = anchor_floor.floor_gate_errors(
        anchor_floor.read_committed_durability_anchor_floor(
            forged, at_commit=forged_head
        ),
        label="transition durability anchor floor",
        observations=observations,
    )
    # 兩者都仍然擋(UNVERIFIED 不是 PASS),而且逐字釘住訊息:只斷言「errors 非空」
    # 會讓「UNVERIFIED 改判 PASS」這種變異在別處補一條無關錯誤時仍然綠。
    assert unmerged_errors == [
        "acceptance review durability anchor floor: UNVERIFIED: no code-owned "
        "protected ref resolves in this repository, so the floor's history tail "
        "cannot be pinned to any code-owned ref"
    ]
    assert forged_errors == [
        "transition durability anchor floor: durability anchor floor history "
        "does not begin with its GENESIS_ARMED commit"
    ]
    # 但 typed 輸出裡分得開,且不需要解析錯誤字串。
    assert observations.as_records() == {
        "host_identity": [],
        "floor_verdicts": [
            {
                "label": "acceptance review durability anchor floor",
                "verdict": anchor_floor.FLOOR_UNVERIFIED,
            },
            {
                "label": "transition durability anchor floor",
                "verdict": anchor_floor.FLOOR_REJECTED,
            },
        ],
    }
    assert anchor_floor.host_identity_sink(None) is None
    assert anchor_floor.host_identity_sink(observations) is (
        observations.host_identity
    )
    # 同一條路徑被重跑(issuance 就會)只是噪音,投影必須冪等;但**同一 label 兩個
    # 不同 verdict** 是真矛盾,不得被去重壓平。
    repeated = anchor_floor.AnchorGateObservations()
    for verdict in (
        anchor_floor.FLOOR_UNVERIFIED,
        anchor_floor.FLOOR_UNVERIFIED,
        anchor_floor.FLOOR_REJECTED,
    ):
        repeated.floor_verdicts.append(
            anchor_floor.FloorVerdictObservation("transition floor", verdict)
        )
    assert repeated.as_records()["floor_verdicts"] == [
        {"label": "transition floor", "verdict": anchor_floor.FLOOR_REJECTED},
        {"label": "transition floor", "verdict": anchor_floor.FLOOR_UNVERIFIED},
    ]
