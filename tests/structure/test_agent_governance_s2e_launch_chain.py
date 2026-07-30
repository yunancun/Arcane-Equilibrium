"""Git lineage and current-generation tests for S2E launch payloads."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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


LAUNCH_CONTRACT_DIGEST = (
    "sha256:f8f8b1b9884aff421bf6ef52015837f2fd86447dbd67b4be5606d43afcffd2e0"
)
GENERATION_TASK_CONTRACT_DIGEST = (
    "sha256:fc295b09b791ba50a76dbf82223f14a4c26998cbf818b46e29c857e8e830e775"
)
NEXT_GENERATION_TASK_CONTRACT_DIGEST = "sha256:" + "4" * 64


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


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
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "s2e-chain@example.invalid")
    _git(repo, "config", "user.name", "S2E Chain Test")
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
        generation_task_contract_digest=NEXT_GENERATION_TASK_CONTRACT_DIGEST,
    )

    assert genesis["launch_contract_digest"] == wave["launch_contract_digest"]
    assert genesis["generation_task_contract_digest"] != (
        wave["generation_task_contract_digest"]
    )
    assert validator.validate_s2e_launch_transition_payload(
        wave,
        predecessor_receipt=genesis,
        repo_root=repo,
        consumed_predecessor_digests=frozenset(),
    ) == []


def test_genesis_and_lw1_form_a_canonical_git_bound_chain(tmp_path: Path) -> None:
    repo, baseline, carrier, lw1 = _repo(tmp_path)
    genesis = s2e._build_genesis_candidate_payload(
        repo_root=repo,
        baseline_head=baseline,
        schema_carrier_head=carrier,
        launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
        generation_task_contract_digest=GENERATION_TASK_CONTRACT_DIGEST,
    )
    assert genesis["predecessor"] is None
    assert genesis["baseline_head"] == baseline
    assert genesis["baseline_tree"] == _git(
        repo, "rev-parse", f"{baseline}^{{tree}}"
    )
    assert genesis["schema_carrier_head"] == carrier
    assert genesis["schema_carrier_tree"] == _git(
        repo, "rev-parse", f"{carrier}^{{tree}}"
    )
    assert genesis["payload_digest"] == _payload_digest(genesis)
    assert validator.validate_s2e_launch_genesis_receipt(
        genesis, repo_root=repo
    ) == []

    wave = s2e._build_wave_candidate_payload(
        repo_root=repo,
        wave="S2E-LW1",
        source_head=lw1,
        schema_carrier_head=carrier,
        predecessor_receipt=genesis,
        launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
        generation_task_contract_digest=GENERATION_TASK_CONTRACT_DIGEST,
    )
    assert wave["predecessor"] == genesis["payload_digest"]
    assert wave["payload_digest"] == _payload_digest(wave)
    assert validator.validate_s2e_launch_transition_payload(
        wave,
        predecessor_receipt=genesis,
        repo_root=repo,
        consumed_predecessor_digests=frozenset(),
    ) == []
    rendered = json.dumps(wave, ensure_ascii=False, sort_keys=True)
    assert "actor" not in rendered
    assert "verifier" not in rendered
    assert "nonce" not in rendered


def test_lw1_through_lw5_require_the_exact_unconsumed_prior_digest(
    tmp_path: Path,
) -> None:
    repo, baseline, carrier, _ = _repo(tmp_path)
    genesis = s2e._build_genesis_candidate_payload(
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
        receipt = s2e._build_wave_candidate_payload(
            repo_root=repo,
            wave=wave,
            source_head=head,
            schema_carrier_head=carrier,
            predecessor_receipt=predecessor,
            launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
            generation_task_contract_digest=GENERATION_TASK_CONTRACT_DIGEST,
        )
        assert validator.validate_s2e_launch_transition_payload(
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
    errors = validator.validate_s2e_launch_transition_payload(
        skipped,
        predecessor_receipt=receipts[0],
        repo_root=repo,
        consumed_predecessor_digests=set(),
    )
    assert any("predecessor must be S2E-LW2" in error for error in errors)
    replay_errors = validator.validate_s2e_launch_transition_payload(
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
    genesis = s2e._build_genesis_candidate_payload(
        repo_root=repo,
        baseline_head=baseline,
        schema_carrier_head=carrier,
        launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
        generation_task_contract_digest=GENERATION_TASK_CONTRACT_DIGEST,
    )
    lw1 = s2e._build_wave_candidate_payload(
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
        s2e._build_wave_candidate_payload(
            repo_root=repo,
            wave="S2E-LW2",
            source_head=sibling_head,
            schema_carrier_head=carrier,
            predecessor_receipt=lw1,
            launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
            generation_task_contract_digest=NEXT_GENERATION_TASK_CONTRACT_DIGEST,
        )


def test_generation_is_read_only_and_refuses_dirty_or_historical_bytes(
    tmp_path: Path,
) -> None:
    repo, baseline, carrier, _ = _repo(tmp_path)
    with pytest.raises(ValueError, match="must equal current repository HEAD"):
        launch.build_genesis_candidate(
            repo_root=repo,
            baseline_head=baseline,
            schema_carrier_head=carrier,
            launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
            generation_task_contract_digest=GENERATION_TASK_CONTRACT_DIGEST,
        )
    _git(repo, "checkout", "--detach", carrier)
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

    (repo / "uncommitted.txt").write_text(
        "must not be laundered\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="repository must be clean"):
        launch.build_genesis_candidate(
            repo_root=repo,
            baseline_head=baseline,
            schema_carrier_head=carrier,
            launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
            generation_task_contract_digest=GENERATION_TASK_CONTRACT_DIGEST,
        )
