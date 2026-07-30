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
        argv=["git", "rev-parse", "--is-inside-work-tree"],
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
    carrier = _commit(repo, "schemas/launch.json", "{}\n", "schema carrier")
    lw1 = _commit(repo, "lw1.txt", "LW1\n", "LW1 checkpoint")
    return repo, baseline, carrier, lw1


def _payload_digest(receipt: dict) -> str:
    return validator.canonical_digest(
        {key: value for key, value in receipt.items() if key != "payload_digest"}
    )


def test_re_admission_changes_generation_digest_without_forking_launch_lineage(
    tmp_path: Path,
) -> None:
    repo, baseline, carrier, lw1 = _repo(tmp_path)
    genesis = launch.build_genesis_candidate(
        repo_root=repo,
        baseline_head=baseline,
        schema_carrier_head=carrier,
        launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
        generation_task_contract_digest=GENERATION_TASK_CONTRACT_DIGEST,
    )
    wave = launch.build_wave_candidate(
        repo_root=repo,
        wave="S2E-LW1",
        source_head=lw1,
        schema_carrier_head=carrier,
        predecessor_receipt=genesis,
        launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
        generation_task_contract_digest=NEXT_GENERATION_TASK_CONTRACT_DIGEST,
    )

    assert genesis["launch_contract_digest"] == wave["launch_contract_digest"]
    assert genesis["generation_task_contract_digest"] != (
        wave["generation_task_contract_digest"]
    )
    assert validator.validate_s2e_launch_transition(
        wave, predecessor_receipt=genesis, repo_root=repo
    ) == []


def test_genesis_and_lw1_form_a_canonical_git_bound_chain(tmp_path: Path) -> None:
    repo, baseline, carrier, lw1 = _repo(tmp_path)

    genesis = launch.build_genesis_candidate(
        repo_root=repo,
        baseline_head=baseline,
        schema_carrier_head=carrier,
        launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
        generation_task_contract_digest=GENERATION_TASK_CONTRACT_DIGEST,
    )
    assert genesis["schema_version"] == "s2e_launch_genesis_receipt_v1"
    assert genesis["predecessor"] is None
    assert genesis["baseline_head"] == baseline
    assert genesis["baseline_tree"] == _git(repo, "rev-parse", f"{baseline}^{{tree}}")
    assert genesis["schema_carrier_head"] == carrier
    assert genesis["schema_carrier_tree"] == _git(
        repo, "rev-parse", f"{carrier}^{{tree}}"
    )
    assert baseline != carrier
    assert genesis["payload_digest"] == _payload_digest(genesis)
    assert validator.validate_s2e_launch_genesis_receipt(
        genesis, repo_root=repo
    ) == []

    wave = launch.build_wave_candidate(
        repo_root=repo,
        wave="S2E-LW1",
        source_head=lw1,
        schema_carrier_head=carrier,
        predecessor_receipt=genesis,
        launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
        generation_task_contract_digest=GENERATION_TASK_CONTRACT_DIGEST,
    )
    assert wave["schema_version"] == "s2e_launch_wave_receipt_v1"
    assert wave["predecessor"] == genesis["payload_digest"]
    assert wave["payload_digest"] == _payload_digest(wave)
    assert validator.validate_s2e_launch_transition(
        wave,
        predecessor_receipt=genesis,
        repo_root=repo,
    ) == []

    rendered = json.dumps(wave, ensure_ascii=False, sort_keys=True)
    assert "actor" not in rendered
    assert "verifier" not in rendered
    assert "nonce" not in rendered


def test_lw1_through_lw5_require_the_exact_unconsumed_prior_digest(
    tmp_path: Path,
) -> None:
    repo, baseline, carrier, _ = _repo(tmp_path)
    genesis = launch.build_genesis_candidate(
        repo_root=repo,
        baseline_head=baseline,
        schema_carrier_head=carrier,
        launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
        generation_task_contract_digest=GENERATION_TASK_CONTRACT_DIGEST,
    )
    predecessor = genesis
    receipts: list[dict] = []
    for wave in ("S2E-LW1", "S2E-LW2", "S2E-LW3", "S2E-LW4", "S2E-LW5"):
        head = _commit(repo, f"{wave}.txt", f"{wave}\n", wave)
        receipt = launch.build_wave_candidate(
            repo_root=repo,
            wave=wave,
            source_head=head,
            schema_carrier_head=carrier,
            predecessor_receipt=predecessor,
            launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
            generation_task_contract_digest=GENERATION_TASK_CONTRACT_DIGEST,
        )
        assert validator.validate_s2e_launch_transition(
            receipt,
            predecessor_receipt=predecessor,
            repo_root=repo,
            consumed_predecessor_digests=set(),
        ) == []
        receipts.append(receipt)
        predecessor = receipt

    skipped = dict(receipts[2])
    skipped["predecessor"] = receipts[0]["payload_digest"]
    skipped["payload_digest"] = _payload_digest(skipped)
    errors = validator.validate_s2e_launch_transition(
        skipped,
        predecessor_receipt=receipts[0],
        repo_root=repo,
        consumed_predecessor_digests=set(),
    )
    assert any("predecessor must be S2E-LW2" in error for error in errors)

    replay_errors = validator.validate_s2e_launch_transition(
        receipts[1],
        predecessor_receipt=receipts[0],
        repo_root=repo,
        consumed_predecessor_digests={receipts[0]["payload_digest"]},
    )
    assert any("already consumed" in error for error in replay_errors)


def test_lw2_rejects_a_predecessor_receipt_from_a_sibling_branch(
    tmp_path: Path,
) -> None:
    repo, baseline, carrier, lw1_head = _repo(tmp_path)
    genesis = launch.build_genesis_candidate(
        repo_root=repo,
        baseline_head=baseline,
        schema_carrier_head=carrier,
        launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
        generation_task_contract_digest=GENERATION_TASK_CONTRACT_DIGEST,
    )
    lw1 = launch.build_wave_candidate(
        repo_root=repo,
        wave="S2E-LW1",
        source_head=lw1_head,
        schema_carrier_head=carrier,
        predecessor_receipt=genesis,
        launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
        generation_task_contract_digest=GENERATION_TASK_CONTRACT_DIGEST,
    )
    _git(repo, "checkout", "-b", "sibling", carrier)
    sibling_head = _commit(repo, "sibling.txt", "sibling\n", "sibling checkpoint")

    with pytest.raises(ValueError, match="predecessor source head"):
        launch.build_wave_candidate(
            repo_root=repo,
            wave="S2E-LW2",
            source_head=sibling_head,
            schema_carrier_head=carrier,
            predecessor_receipt=lw1,
            launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
            generation_task_contract_digest=NEXT_GENERATION_TASK_CONTRACT_DIGEST,
        )


def test_generation_is_read_only_and_refuses_dirty_repository_bytes(
    tmp_path: Path,
) -> None:
    repo, baseline, carrier, _ = _repo(tmp_path)
    before_head = _git(repo, "rev-parse", "HEAD")
    before_tree = _git(repo, "rev-parse", "HEAD^{tree}")
    before_status = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")

    launch.build_genesis_candidate(
        repo_root=repo,
        baseline_head=baseline,
        schema_carrier_head=carrier,
        launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
        generation_task_contract_digest=GENERATION_TASK_CONTRACT_DIGEST,
    )

    assert _git(repo, "rev-parse", "HEAD") == before_head
    assert _git(repo, "rev-parse", "HEAD^{tree}") == before_tree
    assert _git(repo, "status", "--porcelain=v1", "--untracked-files=all") == (
        before_status
    )

    (repo / "uncommitted.txt").write_text("must not be laundered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="repository must be clean"):
        launch.build_genesis_candidate(
            repo_root=repo,
            baseline_head=baseline,
            schema_carrier_head=carrier,
            launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
            generation_task_contract_digest=GENERATION_TASK_CONTRACT_DIGEST,
        )


def _carrier_case(tmp_path: Path) -> tuple[Path, dict, dict, dict, datetime]:
    repo, baseline, schema_carrier, _ = _repo(tmp_path)
    genesis = launch.build_genesis_candidate(
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
    genesis = launch.build_genesis_candidate(
        repo_root=repo,
        baseline_head=baseline,
        schema_carrier_head=carrier,
        launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
        generation_task_contract_digest=GENERATION_TASK_CONTRACT_DIGEST,
    )
    wave = launch.build_wave_candidate(
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
    candidate = launch.build_genesis_candidate(
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
        now=datetime(2026, 7, 30, 12, 1, tzinfo=timezone.utc),
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


def test_verified_review_bundle_issues_ready_genesis_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_key, _, fingerprint = _install_disposable_s2e_trust_root(
        tmp_path, monkeypatch
    )
    repo, baseline, carrier, _ = _repo(tmp_path)
    candidate = launch.build_genesis_candidate(
        repo_root=repo,
        baseline_head=baseline,
        schema_carrier_head=carrier,
        launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
        generation_task_contract_digest=GENERATION_TASK_CONTRACT_DIGEST,
    )
    assert candidate["checkpoint_status"] == "PENDING_REVIEW"
    assert candidate["acceptance_review_bundle_digest"] is None
    _git(repo, "checkout", "--detach", carrier)
    issued_at = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
    review_task_digest = NEXT_GENERATION_TASK_CONTRACT_DIGEST
    review_context_digest = "sha256:" + "6" * 64
    capture = _actual_capture(
        repo,
        carrier_path="schemas/launch.json",
        task_digest=review_task_digest,
        context_digest=review_context_digest,
        monkeypatch=monkeypatch,
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
        "predicate_results": validator.s2e_review_predicate_results(
            candidate["wave"]
        ),
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

    issuance = validator.issue_s2e_launch_receipt(
        candidate,
        acceptance_review_bundle=bundle,
        repo_root=repo,
        now=issued_at + timedelta(minutes=1),
        governed_capture_record=capture,
        external_append_intent=intent,
        external_append_result=append_result,
        external_readback_ack=readback,
    )

    assert issuance["status"] == "ISSUED"
    issued = issuance["issued_receipt"]
    assert issued is not None
    assert issued["checkpoint_status"] == "W0_GENESIS_READY"
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
        "reviewed_source_head": "a" * 40,
        "reviewed_source_tree": "b" * 40,
        "generation_task_contract_digest": digest,
        "predicate_results": validator.s2e_review_predicate_results(
            "W0-GENESIS"
        ),
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
