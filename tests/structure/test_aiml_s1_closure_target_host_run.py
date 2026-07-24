"""Fail-closed source-generation binding for the S1 target-host run driver."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

import aiml_s1_closure_target_host_run as driver  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repository(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "s1-driver@example.invalid")
    _git(repo, "config", "user.name", "S1 Driver Test")
    (repo / "source.txt").write_text("generation one\n", encoding="utf-8")
    _git(repo, "add", "source.txt")
    _git(repo, "commit", "-q", "-m", "generation one")
    return repo, _git(repo, "rev-parse", "HEAD")


def test_driver_accepts_only_the_exact_clean_committed_head(tmp_path: Path) -> None:
    repo, head = _repository(tmp_path)

    assert driver._verified_committed_source_head(repo, head) == head


def test_driver_rejects_a_caller_forged_source_head(tmp_path: Path) -> None:
    repo, _head = _repository(tmp_path)

    with pytest.raises(SystemExit, match="differs from target-host worktree HEAD"):
        driver._verified_committed_source_head(repo, "f" * 40)


@pytest.mark.parametrize("dirty_kind", ["tracked", "untracked"])
def test_driver_rejects_a_dirty_effect_worktree(
    tmp_path: Path, dirty_kind: str,
) -> None:
    repo, head = _repository(tmp_path)
    if dirty_kind == "tracked":
        (repo / "source.txt").write_text("mutated\n", encoding="utf-8")
    else:
        (repo / "injected.py").write_text("raise SystemExit\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="must be clean"):
        driver._verified_committed_source_head(repo, head)


def test_driver_rejects_abbreviated_or_noncanonical_heads(tmp_path: Path) -> None:
    repo, head = _repository(tmp_path)

    for claimed in (head[:10], head.upper(), "not-a-head"):
        with pytest.raises(SystemExit, match="exact lowercase 40-hex"):
            driver._verified_committed_source_head(repo, claimed)
