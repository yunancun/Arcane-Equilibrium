from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "runtime_source_remote_reconcile_probe.py"
SPEC = importlib.util.spec_from_file_location("runtime_source_remote_reconcile_probe", SCRIPT)
remote_probe = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(remote_probe)


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


def _write_base_files(repo: Path) -> None:
    for name in (
        "tracked_equal.txt",
        "tracked_diff.txt",
        "tracked_missing.txt",
        "target_removed_absent.txt",
        "target_removed_local.txt",
    ):
        _write(repo / name, "base\n")


def _make_local_target_and_remote_fixture(tmp_path: Path) -> tuple[Path, Path, str]:
    local_repo = tmp_path / "local_target"
    remote_repo = tmp_path / "remote_runtime"

    _init_repo(local_repo)
    _write_base_files(local_repo)
    _git(local_repo, "add", ".")
    _git(local_repo, "commit", "-q", "-m", "base")
    _write(local_repo / "tracked_equal.txt", "target\n")
    _write(local_repo / "tracked_diff.txt", "target\n")
    _write(local_repo / "tracked_missing.txt", "target\n")
    (local_repo / "target_removed_absent.txt").unlink()
    (local_repo / "target_removed_local.txt").unlink()
    _write(local_repo / "untracked_equal.txt", "target-added\n")
    _write(local_repo / "untracked_conflict.txt", "target-added\n")
    _write(local_repo / "newdir/equal.py", "target-dir\n")
    _write(local_repo / "newdir/conflict.py", "target-dir\n")
    _git(local_repo, "add", ".")
    _git(local_repo, "commit", "-q", "-m", "target")
    target_sha = _git(local_repo, "rev-parse", "HEAD")

    _init_repo(remote_repo)
    _write_base_files(remote_repo)
    _git(remote_repo, "add", ".")
    _git(remote_repo, "commit", "-q", "-m", "base")
    _write(remote_repo / "tracked_equal.txt", "target\n")
    _write(remote_repo / "tracked_diff.txt", "runtime\n")
    (remote_repo / "tracked_missing.txt").unlink()
    (remote_repo / "target_removed_absent.txt").unlink()
    _write(remote_repo / "target_removed_local.txt", "runtime-local\n")
    _write(remote_repo / "untracked_equal.txt", "target-added\n")
    _write(remote_repo / "untracked_conflict.txt", "runtime-added\n")
    _write(remote_repo / "local_only.txt", "runtime-only\n")
    _write(remote_repo / "newdir/equal.py", "target-dir\n")
    _write(remote_repo / "newdir/conflict.py", "runtime-dir\n")
    _write(remote_repo / "newdir/__pycache__/local.pyc", "runtime-cache\n")
    return local_repo, remote_repo, target_sha


def test_remote_probe_compares_remote_worktree_to_local_target_without_remote_object(
    tmp_path: Path,
) -> None:
    local_repo, remote_repo, target_sha = _make_local_target_and_remote_fixture(tmp_path)
    client = remote_probe.LocalWorktreeClient(remote_repo)

    plan = remote_probe.build_remote_plan(
        local_repo,
        target_ref=target_sha,
        remote_repo_root=str(remote_repo),
        remote_label="local-fixture",
        client=client,
        include_digests=True,
    )

    assert plan["schema_version"] == "runtime_source_remote_reconcile_plan_v1"
    assert plan["status"] == "REVIEW_REQUIRED_BEFORE_REMOTE_RECONCILE"
    assert plan["target_ref_status"] == "AVAILABLE_LOCALLY"
    assert plan["remote_target_object_available"] is False
    assert plan["mutated_remote"] is False
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
    assert plan["answers"]["remote_target_object_available"] is False
    assert plan["answers"]["review_required_before_reconcile"] is True

    assert plan["next_actions"][0] == (
        "make_target_commit_available_on_runtime_under_operator_approval_before_direct_runtime_planner"
    )
    assert {
        "tracked_diff.txt",
        "tracked_missing.txt",
        "target_removed_local.txt",
        "untracked_conflict.txt",
        "local_only.txt",
        "newdir/conflict.py",
        "newdir/__pycache__/local.pyc",
    } <= set(plan["review_required_paths"])
    equal_row = plan["classes"]["tracked_dirty_equals_target"][0]
    assert equal_row["remote_worktree_sha256"] == equal_row["target_sha256"]


def test_remote_probe_reports_equivalent_dirty_remote_tree(tmp_path: Path) -> None:
    local_repo = tmp_path / "local"
    remote_repo = tmp_path / "remote"
    _init_repo(local_repo)
    _write(local_repo / "tracked_equal.txt", "base\n")
    _git(local_repo, "add", ".")
    _git(local_repo, "commit", "-q", "-m", "base")
    _write(local_repo / "tracked_equal.txt", "target\n")
    _write(local_repo / "untracked_equal.txt", "target-added\n")
    _git(local_repo, "add", ".")
    _git(local_repo, "commit", "-q", "-m", "target")
    target_sha = _git(local_repo, "rev-parse", "HEAD")

    _init_repo(remote_repo)
    _write(remote_repo / "tracked_equal.txt", "base\n")
    _git(remote_repo, "add", ".")
    _git(remote_repo, "commit", "-q", "-m", "base")
    _write(remote_repo / "tracked_equal.txt", "target\n")
    _write(remote_repo / "untracked_equal.txt", "target-added\n")

    plan = remote_probe.build_remote_plan(
        local_repo,
        target_ref=target_sha,
        remote_repo_root=str(remote_repo),
        remote_label="local-fixture",
        client=remote_probe.LocalWorktreeClient(remote_repo),
    )

    assert plan["status"] == "REMOTE_DIRTY_CONTENT_EQUIVALENT_TO_TARGET"
    assert plan["review_required_path_count"] == 0
    assert plan["content_equivalent_path_count"] == 2
    assert plan["answers"]["can_reconcile_without_content_loss"] is True


def test_remote_probe_cli_local_mode_writes_json_and_fails_on_review(
    tmp_path: Path,
) -> None:
    local_repo, remote_repo, target_sha = _make_local_target_and_remote_fixture(tmp_path)
    out = tmp_path / "remote_plan.json"

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--remote-mode",
            "local",
            "--local-repo-root",
            str(local_repo),
            "--remote-repo-root",
            str(remote_repo),
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
    assert stdout_payload["status"] == "REVIEW_REQUIRED_BEFORE_REMOTE_RECONCILE"
    assert stdout_payload["boundary"].startswith("read-only local target-tree")
