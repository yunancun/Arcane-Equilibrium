from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "runtime_source_reconcile_planner.py"
SPEC = importlib.util.spec_from_file_location("runtime_source_reconcile_planner", SCRIPT)
planner = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(planner)


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _init_repo(repo: Path) -> None:
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")


def _make_reconcile_fixture(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    _init_repo(repo)
    for name in (
        "tracked_equal.txt",
        "tracked_diff.txt",
        "tracked_missing.txt",
        "target_removed_absent.txt",
        "target_removed_local.txt",
    ):
        _write(repo / name, "base\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "base")
    base_sha = _git(repo, "rev-parse", "HEAD")

    _write(repo / "tracked_equal.txt", "target\n")
    _write(repo / "tracked_diff.txt", "target\n")
    _write(repo / "tracked_missing.txt", "target\n")
    (repo / "target_removed_absent.txt").unlink()
    (repo / "target_removed_local.txt").unlink()
    _write(repo / "untracked_equal.txt", "target-added\n")
    _write(repo / "untracked_conflict.txt", "target-added\n")
    _write(repo / "newdir/equal.py", "target-dir\n")
    _write(repo / "newdir/conflict.py", "target-dir\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "target")
    target_sha = _git(repo, "rev-parse", "HEAD")

    _git(repo, "checkout", "-q", base_sha)
    _write(repo / "tracked_equal.txt", "target\n")
    _write(repo / "tracked_diff.txt", "runtime\n")
    (repo / "tracked_missing.txt").unlink()
    (repo / "target_removed_absent.txt").unlink()
    _write(repo / "target_removed_local.txt", "runtime-local\n")
    _write(repo / "untracked_equal.txt", "target-added\n")
    _write(repo / "untracked_conflict.txt", "runtime-added\n")
    _write(repo / "local_only.txt", "runtime-only\n")
    _write(repo / "newdir/equal.py", "target-dir\n")
    _write(repo / "newdir/conflict.py", "runtime-dir\n")
    _write(repo / "newdir/__pycache__/local.pyc", "runtime-cache\n")
    return repo, target_sha


def test_planner_classifies_dirty_and_untracked_paths_against_target(
    tmp_path: Path,
) -> None:
    repo, target_sha = _make_reconcile_fixture(tmp_path)

    plan = planner.build_plan(repo, target_ref=target_sha, include_digests=True)

    assert plan["schema_version"] == "runtime_source_reconcile_plan_v1"
    assert plan["status"] == "REVIEW_REQUIRED_BEFORE_RECONCILE"
    assert plan["target_ref_status"] == "AVAILABLE"
    assert plan["head_ancestor_of_target"] is True
    assert plan["mutated"] is False
    assert plan["class_counts"]["tracked_dirty_equals_target"] == 1
    assert plan["class_counts"]["tracked_dirty_differs_from_target"] == 1
    assert plan["class_counts"]["tracked_missing_or_nonfile"] == 1
    assert plan["class_counts"]["tracked_absent_equals_target_absent"] == 1
    assert plan["class_counts"]["tracked_path_absent_from_target"] == 1
    assert plan["class_counts"]["untracked_equals_target"] == 2
    assert plan["class_counts"]["untracked_conflicts_with_target_path"] == 2
    assert plan["class_counts"]["untracked_not_in_target"] == 2
    assert plan["review_required_path_count"] == 7
    assert plan["content_equivalent_path_count"] == 4
    assert plan["answers"]["review_required_before_reconcile"] is True
    assert plan["answers"]["can_reconcile_without_content_loss"] is False

    review_paths = set(plan["review_required_paths"])
    assert {
        "tracked_diff.txt",
        "tracked_missing.txt",
        "target_removed_local.txt",
        "untracked_conflict.txt",
        "local_only.txt",
        "newdir/conflict.py",
        "newdir/__pycache__/local.pyc",
    } <= review_paths
    equal_row = plan["classes"]["tracked_dirty_equals_target"][0]
    assert equal_row["path"] == "tracked_equal.txt"
    assert equal_row["worktree_sha256"] == equal_row["target_sha256"]


def test_planner_distinguishes_content_equivalent_dirty_tree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "tracked_equal.txt", "base\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "base")
    base_sha = _git(repo, "rev-parse", "HEAD")
    _write(repo / "tracked_equal.txt", "target\n")
    _write(repo / "untracked_equal.txt", "target-added\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "target")
    target_sha = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", base_sha)
    _write(repo / "tracked_equal.txt", "target\n")
    _write(repo / "untracked_equal.txt", "target-added\n")

    plan = planner.build_plan(repo, target_ref=target_sha)

    assert plan["status"] == "DIRTY_CONTENT_EQUIVALENT_TO_TARGET"
    assert plan["review_required_path_count"] == 0
    assert plan["content_equivalent_path_count"] == 2
    assert plan["answers"]["can_reconcile_without_content_loss"] is True
    assert plan["class_counts"]["tracked_dirty_equals_target"] == 1
    assert plan["class_counts"]["untracked_equals_target"] == 1


def test_planner_fails_closed_when_target_ref_is_unavailable(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "README.md", "fixture\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "base")

    plan = planner.build_plan(repo, target_ref="missing/ref")

    assert plan["status"] == "TARGET_REF_UNAVAILABLE"
    assert plan["target_ref_status"] == "UNAVAILABLE"
    assert plan["answers"]["target_ref_available"] is False
    assert plan["answers"]["review_required_before_reconcile"] is True
    assert plan["next_actions"] == [
        "sync_or_fetch_target_ref_under_operator_approval_before_reconcile_plan"
    ]


def test_cli_writes_json_and_can_fail_on_review_required(tmp_path: Path) -> None:
    repo, target_sha = _make_reconcile_fixture(tmp_path)
    out = tmp_path / "plan.json"

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(repo),
            "--target-ref",
            target_sha,
            "--json-output",
            str(out),
            "--fail-on-review-required",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 3
    stdout_payload = json.loads(proc.stdout)
    file_payload = json.loads(out.read_text(encoding="utf-8"))
    assert file_payload == stdout_payload
    assert stdout_payload["status"] == "REVIEW_REQUIRED_BEFORE_RECONCILE"
    assert stdout_payload["boundary"].startswith("read-only git/worktree planner")

