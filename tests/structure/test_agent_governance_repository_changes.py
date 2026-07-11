"""Adversarial tests for before/after repository mutation provenance."""

from __future__ import annotations

from copy import deepcopy
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from agent_governance_capture import capture_repository  # noqa: E402
from agent_governance_repository_changes import (  # noqa: E402
    capture_repository_change,
    validate_repository_change_record,
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, text=True, capture_output=True
    ).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "change@example.invalid")
    _git(repo, "config", "user.name", "Change Test")
    (repo / "owned.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo, "add", "owned.py")
    _git(repo, "commit", "-qm", "fixture")
    return repo


def test_repository_change_requires_real_before_after_generation(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    before = capture_repository(["owned.py"], root=repo)
    (repo / "owned.py").write_text("VALUE = 2\n", encoding="utf-8")
    task_digest = "sha256:" + "a" * 64

    record = capture_repository_change(
        before=before,
        task_contract_digest=task_digest,
        node_id="implementation",
        role_id="E1",
        scope=["owned.py"],
        root=repo,
    )

    assert record["mutation_observed"] is True
    assert record["before_generation_digest"] != record["after_generation_digest"]
    assert record["affected_paths"] == ["owned.py"]
    assert validate_repository_change_record(
        record,
        expected_task_contract_digest=task_digest,
        expected_node_id="implementation",
        expected_role_id="E1",
        expected_scope=["owned.py"],
        expected_source_head=_git(repo, "rev-parse", "HEAD"),
        root=repo,
        require_after_current=True,
    ) == []


def test_snapshot_does_not_claim_causation_and_tamper_fails(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    before = capture_repository(["owned.py"], root=repo)
    unchanged = capture_repository_change(
        before=before,
        task_contract_digest="sha256:" + "b" * 64,
        node_id="independent_review",
        role_id="E2",
        scope=["owned.py"],
        root=repo,
    )
    assert unchanged["mutation_observed"] is False

    tampered = deepcopy(unchanged)
    tampered["mutation_observed"] = True
    tampered["affected_paths"] = ["outside.py"]
    errors = validate_repository_change_record(tampered, root=repo)
    assert "repository change mutation_observed is inconsistent" in errors
    assert "repository change affected_paths are inconsistent" in errors
    assert "repository change record self-digest is invalid" in errors
