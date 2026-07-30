from __future__ import annotations

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


def _external_worm_triplet(
    payload: dict,
    *,
    source_head: str,
    landing_scope_id: str,
    learning_runtime_digest: str,
    issued_at: datetime,
    intent_id: str,
) -> tuple[dict, dict, dict]:
    append_actor = f"{intent_id}-writer"
    intent = external_sink.build_external_worm_append_intent(
        intent_id=intent_id,
        terminal_receipt_type="disposable_proof_payload_v1",
        final_source_head=source_head,
        landing_scope_id=landing_scope_id,
        learning_runtime_digest=learning_runtime_digest,
        terminal_payload_digest=terminal_sink.terminal_payload_digest(payload),
        append_actor_id=append_actor,
        approved_by="PM",
        approved_at=issued_at.isoformat(),
        expires_at=(issued_at + timedelta(hours=2)).isoformat(),
        endpoint="https://s3.us-east-1.amazonaws.com",
        region="us-east-1",
        bucket="s2e-disposable-object-lock",
        object_lock_mode="GOVERNANCE",
        retain_until=(issued_at + timedelta(days=30)).isoformat(),
        credential_channel_id="aws-profile:s2e-disposable",
        compliance_operator_approved=False,
        now=(issued_at + timedelta(minutes=1)).isoformat(),
    )
    client = _DisposableObjectLockS3()
    result = external_sink.apply_external_worm_append(
        intent,
        s3_client=client,
        append_actor_id=append_actor,
        terminal_payload=payload,
        started_at=issued_at.isoformat(),
        completed_at=(issued_at + timedelta(seconds=1)).isoformat(),
    )
    readback = external_sink.independent_readback_ack(
        result,
        intent,
        s3_client=client,
        verifier_actor_id=f"{intent_id}-independent-readback",
        observed_at=(issued_at + timedelta(seconds=5)).isoformat(),
    )
    return intent, result, readback


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
        if relative_path == "TODO.md":
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
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, genesis, attestation, _, issued_at = _carrier_case(tmp_path)
    receipt_path = tmp_path / "carrier-attestation.json"
    payload_path = tmp_path / "genesis-payload.json"
    receipt_path.write_text(json.dumps(attestation), encoding="utf-8")
    payload_path.write_text(json.dumps(genesis), encoding="utf-8")

    exit_code = launch.main([
        "validate",
        "--repo-root",
        str(repo),
        "--receipt",
        str(receipt_path),
        "--payload-receipt",
        str(payload_path),
        "--now",
        (issued_at + timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
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
        external_append_intent={"schema_version": "caller-shaped"},
        external_append_result={"schema_version": "caller-shaped"},
        external_readback_ack={"schema_version": "caller-shaped"},
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
    assert any("external worm" in error for error in result["errors"])


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
        external_append_intent=None,
        external_append_result=None,
        external_readback_ack=None,
    )

    assert result["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert result["external_result_digest"] is None
    assert result["external_readback_ack_digest"] is None
    assert result["errors"]


def test_independent_key_capture_and_worm_produce_verified_carrier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_key, _, fingerprint = _install_disposable_s2e_trust_root(
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
    intent, result, readback = _external_worm_triplet(
        worm_payload,
        source_head=attestation["carrier_head"],
        landing_scope_id=attestation["payload_digest"],
        learning_runtime_digest=attestation["launch_contract_digest"],
        issued_at=issued_at,
        intent_id="s2e-carrier-intent-0001",
    )
    attestation["immutable_readback"] = {
        "adapter": "EXTERNAL_WORM_V1",
        "object_id": result["record_locator"],
        "version_id": result["object_version_id"],
        "readback_digest": readback["ack_digest"],
    }
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
        external_append_intent=intent,
        external_append_result=result,
        external_readback_ack=readback,
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
        "external_worm_binding": None,
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
    review_intent, review_result, review_readback = _external_worm_triplet(
        validator.s2e_acceptance_review_worm_payload(review_bundle),
        source_head=schema_carrier,
        landing_scope_id=candidate["payload_digest"],
        learning_runtime_digest=candidate["launch_contract_digest"],
        issued_at=issued_at,
        intent_id="s2e-authority-review-0001",
    )
    review_bundle["external_worm_binding"] = {
        "result_digest": review_result["result_digest"],
        "readback_ack_digest": review_readback["ack_digest"],
        "record_locator": review_result["record_locator"],
        "object_version_id": review_result["object_version_id"],
        "checksum_sha256": review_result["checksum_sha256"],
    }
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
        external_append_intent=review_intent,
        external_append_result=review_result,
        external_readback_ack=review_readback,
    )
    assert issuance["status"] == "ISSUED"
    issued = issuance["issued_receipt"]
    assert issued is not None

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
    carrier_intent, carrier_result, carrier_readback = _external_worm_triplet(
        validator.s2e_carrier_worm_payload(
            carrier_attestation, payload_receipt=issued
        ),
        source_head=carrier_head,
        landing_scope_id=issued["payload_digest"],
        learning_runtime_digest=issued["launch_contract_digest"],
        issued_at=issued_at + timedelta(minutes=2),
        intent_id="s2e-authority-carrier-0001",
    )
    carrier_attestation["immutable_readback"] = {
        "adapter": "EXTERNAL_WORM_V1",
        "object_id": carrier_result["record_locator"],
        "version_id": carrier_result["object_version_id"],
        "readback_digest": carrier_readback["ack_digest"],
    }
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
        review_external_append_intent=review_intent,
        review_external_append_result=review_result,
        review_external_readback_ack=review_readback,
        carrier_attestation=carrier_attestation,
        carrier_governed_capture_record=carrier_capture,
        carrier_external_append_intent=carrier_intent,
        carrier_external_append_result=carrier_result,
        carrier_external_readback_ack=carrier_readback,
        repo_root=repo,
        now=issued_at + timedelta(minutes=3),
    )
    return {
        "repo": repo,
        "schema_carrier": schema_carrier,
        "issued": issued,
        "authority": authority,
        "now": issued_at + timedelta(minutes=3),
        "private_key": private_key,
        "fingerprint": fingerprint,
    }


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

    assert wave["checkpoint_status"] == "PENDING_REVIEW"
    assert wave["wave_exit_id"] == "S2E_2B_2A_SECURITY_RECOVERY_READY"
    assert validator.validate_s2e_launch_transition(
        wave,
        predecessor_receipt=case["issued"],
        predecessor_authority=case["authority"],
        repo_root=repo,
        now=case["now"],
        consumed_predecessor_digests=frozenset(),
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
        "review_intent": _json_file(
            tmp_path,
            "review-intent.json",
            authority["review_external_append_intent"],
        ),
        "review_result": _json_file(
            tmp_path,
            "review-result.json",
            authority["review_external_append_result"],
        ),
        "review_readback": _json_file(
            tmp_path,
            "review-readback.json",
            authority["review_external_readback_ack"],
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
        "carrier_intent": _json_file(
            tmp_path,
            "carrier-intent.json",
            authority["carrier_external_append_intent"],
        ),
        "carrier_result": _json_file(
            tmp_path,
            "carrier-result.json",
            authority["carrier_external_append_result"],
        ),
        "carrier_readback": _json_file(
            tmp_path,
            "carrier-readback.json",
            authority["carrier_external_readback_ack"],
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
        "--external-append-intent", str(files["review_intent"]),
        "--external-append-result", str(files["review_result"]),
        "--external-readback-ack", str(files["review_readback"]),
    ]) == 2
    stale_issue = json.loads(capsys.readouterr().out)
    assert stale_issue["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert any(
        "not the clean current HEAD" in error
        for error in stale_issue["errors"]
    )

    assert launch.main([
        "verify-carrier",
        "--repo-root", str(repo),
        "--attestation", str(files["carrier_attestation"]),
        "--payload-receipt", str(files["issued"]),
        "--governed-capture-record", str(files["carrier_capture"]),
        "--external-append-intent", str(files["carrier_intent"]),
        "--external-append-result", str(files["carrier_result"]),
        "--external-readback-ack", str(files["carrier_readback"]),
        "--now", now,
    ]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "VERIFIED"

    assert launch.main([
        "build-predecessor-authority",
        "--repo-root", str(repo),
        "--predecessor-receipt", str(files["issued"]),
        "--launch-chain-before-predecessor", str(files["empty_chain"]),
        "--acceptance-review-bundle", str(files["review_bundle"]),
        "--review-governed-capture-record", str(files["review_capture"]),
        "--review-disposable-test-effect-chains", str(files["review_chains"]),
        "--review-external-append-intent", str(files["review_intent"]),
        "--review-external-append-result", str(files["review_result"]),
        "--review-external-readback-ack", str(files["review_readback"]),
        "--carrier-attestation", str(files["carrier_attestation"]),
        "--carrier-governed-capture-record", str(files["carrier_capture"]),
        "--carrier-external-append-intent", str(files["carrier_intent"]),
        "--carrier-external-append-result", str(files["carrier_result"]),
        "--carrier-external-readback-ack", str(files["carrier_readback"]),
        "--now", now,
    ]) == 0
    rebuilt_authority = json.loads(capsys.readouterr().out)
    assert rebuilt_authority["authority_digest"] == authority["authority_digest"]

    source_head = _commit(repo, "lw1-cli.txt", "LW1\n", "LW1 CLI source")
    wave = launch.build_wave_candidate(
        repo_root=repo,
        wave="S2E-LW1",
        source_head=source_head,
        schema_carrier_head=case["schema_carrier"],
        predecessor_receipt=issued,
        predecessor_authority=authority,
        launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
        generation_task_contract_digest=NEXT_GENERATION_TASK_CONTRACT_DIGEST,
        now=case["now"],
    )
    wave_path = _json_file(tmp_path, "wave.json", wave)
    authority_path = _json_file(tmp_path, "authority.json", authority)
    assert launch.main([
        "transition-gate",
        "--repo-root", str(repo),
        "--receipt", str(wave_path),
        "--predecessor-receipt", str(files["issued"]),
        "--predecessor-authority", str(authority_path),
        "--now", now,
    ]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "ADVANCE",
        "errors": [],
    }


def test_verified_review_bundle_issues_ready_genesis_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_key, _, fingerprint = _install_disposable_s2e_trust_root(
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
        "external_worm_binding": None,
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
    intent, append_result, readback = _external_worm_triplet(
        worm_payload,
        source_head=carrier,
        landing_scope_id=candidate["payload_digest"],
        learning_runtime_digest=candidate["launch_contract_digest"],
        issued_at=issued_at,
        intent_id="s2e-review-intent-0001",
    )
    bundle["external_worm_binding"] = {
        "result_digest": append_result["result_digest"],
        "readback_ack_digest": readback["ack_digest"],
        "record_locator": append_result["record_locator"],
        "object_version_id": append_result["object_version_id"],
        "checksum_sha256": append_result["checksum_sha256"],
    }
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
        external_append_intent=intent,
        external_append_result=append_result,
        external_readback_ack=readback,
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
        external_append_intent=intent,
        external_append_result=append_result,
        external_readback_ack=readback,
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
        external_append_intent=intent,
        external_append_result=append_result,
        external_readback_ack=readback,
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
        external_append_intent=intent,
        external_append_result=append_result,
        external_readback_ack=readback,
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
                "EXTERNAL_WORM_IMMUTABLE_READBACK_VALID",
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
        "external_worm_binding": {
            "result_digest": digest,
            "readback_ack_digest": digest,
            "record_locator": "records/" + "a" * 64 + ".record",
            "object_version_id": "version-1",
            "checksum_sha256": digest,
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
