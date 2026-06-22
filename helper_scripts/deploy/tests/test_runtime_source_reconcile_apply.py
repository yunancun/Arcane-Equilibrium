from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "runtime_source_reconcile_apply.py"
SPEC = importlib.util.spec_from_file_location("runtime_source_reconcile_apply", SCRIPT)
apply_mod = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(apply_mod)


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


def _fixture(tmp_path: Path) -> tuple[Path, Path, str, str, Path]:
    local_repo = tmp_path / "local_target"
    remote_repo = tmp_path / "remote_runtime"
    review_packet = tmp_path / "review_packet.md"

    _init_repo(local_repo)
    _write(local_repo / "tracked_equal.txt", "base\n")
    _write(local_repo / "tracked_diff.txt", "base\n")
    _git(local_repo, "add", ".")
    _git(local_repo, "commit", "-q", "-m", "base")
    _write(local_repo / "tracked_equal.txt", "target\n")
    _write(local_repo / "tracked_diff.txt", "target\n")
    _write(local_repo / "untracked_conflict.txt", "target\n")
    _git(local_repo, "add", ".")
    _git(local_repo, "commit", "-q", "-m", "target")
    target_sha = _git(local_repo, "rev-parse", "HEAD")

    _init_repo(remote_repo)
    _write(remote_repo / "tracked_equal.txt", "base\n")
    _write(remote_repo / "tracked_diff.txt", "base\n")
    _git(remote_repo, "add", ".")
    _git(remote_repo, "commit", "-q", "-m", "base")
    remote_head = _git(remote_repo, "rev-parse", "HEAD")
    _write(remote_repo / "tracked_equal.txt", "target\n")
    _write(remote_repo / "tracked_diff.txt", "runtime\n")
    _write(remote_repo / "untracked_conflict.txt", "runtime\n")
    review_packet.write_text("# reviewed\n", encoding="utf-8")
    return local_repo, remote_repo, target_sha, remote_head, review_packet


def _build_packet(
    tmp_path: Path,
    *,
    apply_requested: bool,
    apply_env_value: str | None,
    review_accepted: bool = True,
    confirm_target_wins: bool = True,
    review_packet: Path | None = None,
) -> dict:
    local_repo, remote_repo, target_sha, remote_head, default_packet = _fixture(tmp_path)
    packet = review_packet if review_packet is not None else default_packet
    return apply_mod.build_apply_plan(
        local_repo,
        target_ref=target_sha,
        remote_repo_root=str(remote_repo),
        remote_label="local-fixture",
        probe_client=apply_mod.remote_probe.LocalWorktreeClient(remote_repo),
        apply_requested=apply_requested,
        apply_env_value=apply_env_value,
        expected_target_commit=target_sha,
        expected_remote_head=remote_head,
        expected_dirty_count=3,
        expected_review_required_count=2,
        review_accepted=review_accepted,
        confirm_target_wins=confirm_target_wins,
        review_packet=packet,
        archive_dir=str(tmp_path / "archive"),
        fetch_ref="main",
    )


def test_apply_packet_dry_run_emits_commands_without_mutation(tmp_path: Path) -> None:
    plan = _build_packet(tmp_path, apply_requested=False, apply_env_value=None)

    assert plan["schema_version"] == "runtime_source_reconcile_apply_plan_v1"
    assert plan["status"] == "DRY_RUN_OPERATOR_APPROVAL_REQUIRED"
    assert plan["mutated_remote"] is False
    assert plan["apply_env_gate_open"] is False
    assert plan["dirty_path_count"] == 3
    assert plan["review_required_path_count"] == 2
    assert plan["blockers"] == []
    assert plan["answers"]["dry_run_only"] is True
    assert plan["answers"]["apply_ready"] is False
    steps = [row["step"] for row in plan["commands"]]
    assert "fetch_target_ref" in steps
    assert "archive_existing_worktree_paths" in steps
    assert "reset_to_target" in steps
    assert "clean_untracked_paths" in steps
    assert "verify_status" in steps


def test_apply_packet_blocks_apply_without_env_gate(tmp_path: Path) -> None:
    plan = _build_packet(tmp_path, apply_requested=True, apply_env_value=None)

    assert plan["status"] == "APPLY_BLOCKED"
    assert plan["mutated_remote"] is False
    assert "apply_env_gate_not_set" in plan["blockers"]
    assert plan["answers"]["apply_ready"] is False


def test_apply_packet_blocks_review_required_without_explicit_acceptance(
    tmp_path: Path,
) -> None:
    plan = _build_packet(
        tmp_path,
        apply_requested=True,
        apply_env_value="1",
        review_accepted=False,
        confirm_target_wins=False,
    )

    assert plan["status"] == "APPLY_BLOCKED"
    assert "review_required_paths_not_operator_accepted" in plan["blockers"]
    assert "target_wins_not_confirmed_for_review_required_paths" in plan["blockers"]


def test_apply_packet_cli_local_mode_writes_dry_run_json(tmp_path: Path) -> None:
    local_repo, remote_repo, target_sha, remote_head, review_packet = _fixture(tmp_path)
    out = tmp_path / "apply_plan.json"

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
            "--expected-target-commit",
            target_sha,
            "--expected-remote-head",
            remote_head,
            "--expected-dirty-count",
            "3",
            "--expected-review-required-count",
            "2",
            "--review-packet",
            str(review_packet),
            "--review-accepted",
            "--confirm-target-wins",
            "--json-output",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0
    stdout_payload = json.loads(proc.stdout)
    file_payload = json.loads(out.read_text(encoding="utf-8"))
    assert file_payload == stdout_payload
    assert stdout_payload["status"] == "DRY_RUN_OPERATOR_APPROVAL_REQUIRED"
    assert stdout_payload["blockers"] == []
