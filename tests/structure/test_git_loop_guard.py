from __future__ import annotations

import ast
import importlib.util
import subprocess
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "helper_scripts"
    / "maintenance_scripts"
    / "git_loop_guard.py"
)
ROOT = Path(__file__).resolve().parents[2]
SYNC = (ROOT / ".codex/SYNC.md").read_text(encoding="utf-8")
SUBAGENT = (ROOT / ".codex/SUBAGENT_EXECUTION_RULES.md").read_text(
    encoding="utf-8"
)
PROFIT_LOOP = (ROOT / "docs/agents/profit-first-autonomy-loop.md").read_text(
    encoding="utf-8"
)
ALR_LOOP = (
    ROOT
    / "docs/CCAgentWorkSpace/PM/workspace/ai_ml_todo_stub/"
    "2026-07-09--scanner_driven_alr/loop_contract.md"
).read_text(encoding="utf-8")
ALR_STARTUP = (
    ROOT
    / "docs/CCAgentWorkSpace/PM/workspace/ai_ml_todo_stub/"
    "2026-07-09--scanner_driven_alr/startup_prompt.md"
).read_text(encoding="utf-8")
SPEC = importlib.util.spec_from_file_location("git_loop_guard", SCRIPT)
guard = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(guard)


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    _write(repo / "owned.txt", "base\n")
    _git(repo, "add", "owned.txt")
    _git(repo, "commit", "-q", "-m", "base")
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "-q", "-u", "origin", "main")
    _git(origin, "symbolic-ref", "HEAD", "refs/heads/main")
    _git(repo, "checkout", "-q", "-b", "agent/test-loop")
    return repo, origin


def test_start_requires_exact_clean_feature_head(tmp_path: Path) -> None:
    repo, _ = _fixture(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    packet = guard.evaluate(
        repo,
        phase="start",
        expected_branch="agent/test-loop",
        expected_head=head,
    )
    assert packet["status"] == "PASS"
    assert packet["mutated_local"] is False
    assert packet["mutated_remote"] is False

    _write(repo / "owned.txt", "dirty\n")
    dirty = guard.evaluate(
        repo,
        phase="start",
        expected_branch="agent/test-loop",
        expected_head=head,
    )
    assert dirty["status"] == "FAIL"
    assert "DIRTY_WORKTREE" in dirty["reasons"]


def test_dirty_inventory_failures_block_every_phase(
    tmp_path: Path, monkeypatch
) -> None:
    repo, _ = _fixture(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    monkeypatch.setattr(guard, "_nul_paths", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        guard, "_diff_lines", lambda *_args, **_kwargs: (0, False, True)
    )

    for phase in guard.PHASES:
        packet = guard.evaluate(
            repo,
            phase=phase,
            expected_branch="agent/test-loop",
            expected_head=head,
            expected_origin_head=head,
            allow_paths=["owned.txt"],
        )
        assert packet["status"] == "FAIL"
        assert {
            "TRACKED_DIRTY_STATE_UNAVAILABLE",
            "STAGED_STATE_UNAVAILABLE",
            "UNTRACKED_STATE_UNAVAILABLE",
            "DIFF_STATE_UNAVAILABLE",
        }.issubset(packet["reasons"])


def test_checkpoint_rejects_unowned_and_oversized_dirty_scope(tmp_path: Path) -> None:
    repo, _ = _fixture(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    _write(repo / "owned.txt", "one\ntwo\n")
    _write(repo / "outside.txt", "not owned\n")
    packet = guard.evaluate(
        repo,
        phase="checkpoint",
        expected_branch="agent/test-loop",
        expected_head=head,
        allow_paths=["owned.txt"],
        max_dirty_files=1,
        max_diff_lines=1,
    )
    assert packet["status"] == "FAIL"
    assert "UNOWNED_DIRTY_PATH" in packet["reasons"]
    assert "DIRTY_FILE_BUDGET_EXCEEDED" in packet["reasons"]
    assert "DIFF_LINE_BUDGET_EXCEEDED" in packet["reasons"]


def test_start_rejects_feature_branch_tracking_origin_main(tmp_path: Path) -> None:
    repo, _ = _fixture(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "branch", "--set-upstream-to=origin/main", "agent/test-loop")
    packet = guard.evaluate(
        repo,
        phase="start",
        expected_branch="agent/test-loop",
        expected_head=head,
    )
    assert packet["status"] == "FAIL"
    assert "UPSTREAM_MISMATCH" in packet["reasons"]


def test_checkpoint_passes_exact_unstaged_allowlist(tmp_path: Path) -> None:
    repo, _ = _fixture(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    _write(repo / "owned.txt", "bounded change\n")
    packet = guard.evaluate(
        repo,
        phase="checkpoint",
        expected_branch="agent/test-loop",
        expected_head=head,
        allow_paths=["owned.txt"],
    )
    assert packet["status"] == "PASS"
    assert packet["state"]["dirty_paths"] == ["owned.txt"]

    _git(repo, "add", "owned.txt")
    staged = guard.evaluate(
        repo,
        phase="checkpoint",
        expected_branch="agent/test-loop",
        expected_head=head,
        allow_paths=["owned.txt"],
    )
    assert "PREEXISTING_STAGED_CHANGES" in staged["reasons"]


def test_publish_and_post_push_bind_remote_branch_head(tmp_path: Path) -> None:
    repo, _ = _fixture(tmp_path)
    _write(repo / "owned.txt", "feature\n")
    _git(repo, "add", "owned.txt")
    _git(repo, "commit", "-q", "-m", "feature")
    head = _git(repo, "rev-parse", "HEAD")

    publish = guard.evaluate(
        repo,
        phase="publish",
        expected_branch="agent/test-loop",
        expected_head=head,
    )
    assert publish["status"] == "PASS"

    before_push = guard.evaluate(
        repo,
        phase="post-push",
        expected_branch="agent/test-loop",
        expected_head=head,
    )
    assert "REMOTE_BRANCH_HEAD_MISMATCH" in before_push["reasons"]

    _git(repo, "push", "-q", "origin", "agent/test-loop")
    without_upstream = guard.evaluate(
        repo,
        phase="post-push",
        expected_branch="agent/test-loop",
        expected_head=head,
    )
    assert without_upstream["state"]["true_remote_branch_head"] == head
    assert "UPSTREAM_MISMATCH" in without_upstream["reasons"]

    _git(repo, "branch", "--set-upstream-to=origin/agent/test-loop")
    after_push = guard.evaluate(
        repo,
        phase="post-push",
        expected_branch="agent/test-loop",
        expected_head=head,
    )
    assert after_push["status"] == "PASS"
    assert after_push["state"]["true_remote_branch_head"] == head


def test_main_sync_is_exact_head_and_fast_forward_only(tmp_path: Path) -> None:
    repo, origin = _fixture(tmp_path)
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(origin), str(other)], check=True)
    _git(other, "config", "user.email", "other@example.invalid")
    _git(other, "config", "user.name", "Other User")
    _write(other / "remote.txt", "remote advance\n")
    _git(other, "add", "remote.txt")
    _git(other, "commit", "-q", "-m", "remote advance")
    _git(other, "push", "-q", "origin", "main")
    expected = _git(other, "rev-parse", "HEAD")

    _git(repo, "checkout", "-q", "main")
    stale = guard.evaluate(
        repo,
        phase="main-sync",
        expected_origin_head=expected,
    )
    assert "REMOTE_TRACKING_STALE" in stale["reasons"]

    _git(repo, "fetch", "-q", "origin", "main")
    ready = guard.evaluate(
        repo,
        phase="main-sync",
        expected_origin_head=expected,
    )
    assert ready["status"] == "PASS"

    _git(repo, "merge", "-q", "--ff-only", "origin/main")
    done = guard.evaluate(
        repo,
        phase="main-post-sync",
        expected_origin_head=expected,
    )
    assert done["status"] == "PASS"
    assert done["state"]["head"] == expected


def test_sync_contract_covers_exact_head_publication_merge_and_three_sides() -> None:
    for required in (
        "git_loop_guard.py",
        "--phase start",
        "--phase checkpoint",
        "--phase publish",
        "--phase post-push",
        "--phase main-sync",
        "--phase main-post-sync",
        "--match-head-commit",
        "--ff-only",
        "git ls-remote origin refs/heads/main",
        "four_head_reconcile_probe.py",
        "STOP_MERGE_HEAD_DRIFT",
        "SOURCE_SYNCED_RUNTIME_PENDING",
        "EXTERNAL_ADMIN_VERIFICATION_PENDING",
    ):
        assert required in SYNC
    for source in (SYNC, ALR_LOOP, ALR_STARTUP):
        assert "persisted" in source
        assert "loop_branch" in source
        assert "checkpoint_head" in source
        assert "must not recapture" in source
    assert "upstream absent or\n  correct" in SYNC
    assert "upstream is exactly `origin/<branch>`" in SYNC


def test_loop_contract_cannot_advance_with_unbounded_dirty_or_unsynced_heads() -> None:
    for source in (SUBAGENT, PROFIT_LOOP, ALR_LOOP):
        assert "git_loop_guard.py" in source
        assert "checkpoint" in source
        assert "--match-head-commit" in source
        assert "Mac" in source
        assert "Linux" in source
    for required in (
        "STOP_GIT_START_STATE",
        "STOP_CHECKPOINT_SCOPE",
        "STOP_PUSH_VERIFY",
        "STOP_MERGE_HEAD_DRIFT",
        "STOP_SYNC_AUTH_REQUIRED",
        "STOP_MAC_MAIN_SYNC",
        "STOP_LINUX_SYNC",
        "three_side_source_sync_status",
    ):
        assert required in ALR_LOOP


def test_guard_is_read_only_by_construction() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"), filename=str(SCRIPT))
    forbidden_git_subcommands = {
        "add",
        "commit",
        "fetch",
        "merge",
        "pull",
        "push",
        "rebase",
        "reset",
        "restore",
        "stash",
        "switch",
        "worktree",
        "clean",
    }
    literal_values = {
        node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)
    }
    assert not (forbidden_git_subcommands & literal_values)
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"mutated_local": False' in source
    assert '"mutated_remote": False' in source


def test_sync_contract_forbids_dangerous_fallbacks() -> None:
    for required in (
        "No force push",
        "reset/clean",
        "automatic stash",
        "Never use `--admin`",
        "Do not automatically delete",
        "Never reset/clean the Linux checkout",
    ):
        assert required in SYNC
