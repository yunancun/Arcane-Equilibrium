from __future__ import annotations

import ast
import importlib.util
import shlex
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "helper_scripts"
    / "maintenance_scripts"
    / "git_loop_guard.py"
)
ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))
import agent_governance_capture as governance_capture  # noqa: E402
from agent_governance_task_control import (  # noqa: E402
    FileWriterLeaseStore,
    acquire_writer_lease,
    filesystem_writer_lease_action,
    inspect_worktree,
)
from agent_governance_context import capture_repository_baseline  # noqa: E402
from agent_governance_routing import route_task, task_contract_projection  # noqa: E402
from agent_governance_task_admission import acquire_task_admission  # noqa: E402
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
GUI_LOOP = (ROOT / "docs/execution_plan/gui_redesign/LOOP-DRIVER.md").read_text(
    encoding="utf-8"
)
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


def _fixture(
    tmp_path: Path,
    *,
    extra_tracked: dict[str, str] | None = None,
    dirty_scope: list[str] | None = None,
) -> tuple[Path, Path, Path, dict[str, str]]:
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    _write(repo / "owned.txt", "base\n")
    for path, text in (extra_tracked or {}).items():
        _write(repo / path, text)
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "base")
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "-q", "-u", "origin", "main")
    _git(origin, "symbolic-ref", "HEAD", "refs/heads/main")
    feature = tmp_path / "feature"
    _git(repo, "worktree", "add", "-q", "-b", "agent/test-loop", str(feature), "main")
    routed = route_task({
        "task_shape": "implementation",
        "surfaces": ["python"],
        "risk": "low",
        "uncertainty": "low",
        "side_effect_class": "repo_write",
        "objective": "exercise the guarded writer loop",
        "scope": dirty_scope or ["owned.txt"],
        "dirty_scope": dirty_scope or ["owned.txt"],
        "verification_scope": dirty_scope or ["owned.txt"],
        "acceptance_criteria": ["guarded bytes changed"],
        "hard_stops": ["no runtime effect"],
        "baseline": capture_repository_baseline(feature),
        "direct_interfaces": ["owned.txt"],
        "previous_failure": "none",
        "task_prompt": "exercise the guarded writer loop",
        "continuation_mode": "finite",
    })
    admission = acquire_task_admission(
        repo=feature,
        task_id="guard-test",
        owner="pytest",
        task_contract=task_contract_projection(routed["task_facts"]),
    )
    identity = inspect_worktree(feature)
    acquired = acquire_writer_lease(
        FileWriterLeaseStore(identity.common_dir),
        identity,
        task_id="guard-test",
        owner="pytest",
        admission_id=admission["admission_id"],
    )
    assert acquired["status"] == "PASS"
    lease = {
        "writer_task_id": "guard-test",
        "writer_owner": "pytest",
        "writer_lease_id": acquired["lease"]["lease_id"],
        "writer_admission_id": admission["admission_id"],
    }
    return feature, origin, repo, lease


def test_canonical_remote_probe_ignores_repo_redirects_and_git_helper_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    attacker = tmp_path / "attacker.git"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "init", "-q", "--bare", str(attacker)], check=True)
    _git(repo, "config", "user.email", "attacker@example.invalid")
    _git(repo, "config", "user.name", "Attacker")
    _write(repo / "attacker.txt", "attacker\n")
    _git(repo, "add", "attacker.txt")
    _git(repo, "commit", "-q", "-m", "attacker")
    attacker_head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "push", "-q", str(attacker), "HEAD:refs/heads/main")
    canonical = "https://github.com/yunancun/Arcane-Equilibrium.git"
    _git(repo, "config", f"url.file://{attacker}/.insteadOf", canonical)
    redirected = subprocess.run(
        ["git", "-C", str(repo), "ls-remote", canonical, "refs/heads/main"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert redirected.stdout.split()[0] == attacker_head

    hostile_helper = tmp_path / "hostile-git-core"
    hostile_helper.mkdir()
    sentinel = tmp_path / "helper-executed"
    monkeypatch.setenv("GIT_EXEC_PATH", str(hostile_helper))
    monkeypatch.setenv("GIT_SSH_COMMAND", f"touch {sentinel}")
    monkeypatch.setenv("GIT_PROXY_COMMAND", f"touch {sentinel}")
    observed: list[tuple[list[str], dict[str, str], Path | None]] = []

    def no_network_run(command, **kwargs):
        environment = kwargs.get("env", {})
        cwd = Path(kwargs["cwd"]) if kwargs.get("cwd") is not None else None
        observed.append((list(command), dict(environment), cwd))
        projected = (
            "-C" in command
            or any(
                key in environment
                for key in ("GIT_EXEC_PATH", "GIT_SSH_COMMAND", "GIT_PROXY_COMMAND")
            )
        )
        return subprocess.CompletedProcess(
            command,
            0 if projected else 128,
            stdout=(f"{attacker_head}\trefs/heads/main\n".encode() if projected else b""),
            stderr=b"network disabled by regression harness",
        )

    monkeypatch.setattr(guard.subprocess, "run", no_network_run)
    assert guard._true_remote_head(repo, "refs/heads/main", canonical) is None
    assert len(observed) == 1
    command, environment, cwd = observed[0]
    assert "-C" not in command
    assert cwd is not None
    assert repo.resolve() not in (cwd, *cwd.parents)
    assert not {
        "GIT_EXEC_PATH", "GIT_SSH", "GIT_SSH_COMMAND", "GIT_PROXY_COMMAND",
        "GIT_ASKPASS", "SSH_ASKPASS",
    }.intersection(environment)
    assert not sentinel.exists()


def test_guard_authority_git_ignores_hostile_path_environment_and_fsmonitor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _, _, lease = _fixture(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    hostile_bin = tmp_path / "hostile-bin"
    hostile_bin.mkdir()
    path_sentinel = tmp_path / "path-git-executed"
    fsmonitor_sentinel = tmp_path / "fsmonitor-executed"
    inherited_environment = tmp_path / "ambient-environment-observed"
    hostile_git = hostile_bin / "git"
    hostile_git.write_text(
        "#!/bin/sh\n"
        f"touch {shlex.quote(str(path_sentinel))}\n"
        'exec /usr/bin/git "$@"\n',
        encoding="utf-8",
    )
    hostile_git.chmod(0o755)
    fsmonitor = tmp_path / "fsmonitor"
    fsmonitor.write_text(
        "#!/bin/sh\n"
        f"touch {shlex.quote(str(fsmonitor_sentinel))}\n"
        "if [ -n \"$HTTPS_PROXY$SSL_CERT_FILE$GIT_SSL_CAINFO"
        "$GIT_CREDENTIAL_HELPER$GIT_ASKPASS\" ]; then\n"
        f"  touch {shlex.quote(str(inherited_environment))}\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fsmonitor.chmod(0o755)
    _git(repo, "config", "core.fsmonitor", str(fsmonitor))

    monkeypatch.setenv("PATH", f"{hostile_bin}:/usr/bin:/bin")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("ALL_PROXY", "socks5://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "*")
    monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path / "hostile-cert.pem"))
    monkeypatch.setenv("CURL_CA_BUNDLE", str(tmp_path / "hostile-ca.pem"))
    monkeypatch.setenv("GIT_SSL_CAINFO", str(tmp_path / "hostile-git-ca.pem"))
    monkeypatch.setenv("GIT_SSL_CERT", str(tmp_path / "hostile-git-cert.pem"))
    monkeypatch.setenv("GIT_SSL_KEY", str(tmp_path / "hostile-git-key.pem"))
    monkeypatch.setenv("GIT_CREDENTIAL_HELPER", str(tmp_path / "credential"))
    monkeypatch.setenv("GIT_ASKPASS", str(tmp_path / "askpass"))

    packet = guard.evaluate(
        repo,
        phase="start",
        expected_branch="agent/test-loop",
        expected_head=head,
        **lease,
    )

    assert packet["status"] == "PASS"
    assert not path_sentinel.exists()
    assert not fsmonitor_sentinel.exists()
    assert not inherited_environment.exists()
    assert guard.native_git_environment() == {
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_PAGER": "cat",
        "GIT_TERMINAL_PROMPT": "0",
        "LANG": "C",
        "LC_ALL": "C",
        "PAGER": "cat",
        "PATH": "/usr/bin:/bin",
    }


def test_canonical_remote_probe_accepts_exactly_one_expected_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_ref = "refs/heads/main"
    expected_head = "a" * 40
    other_head = "b" * 40
    outputs = iter((
        f"{expected_head}\trefs/heads/other\n".encode(),
        (
            f"{expected_head}\t{expected_ref}\n"
            f"{other_head}\trefs/heads/other\n"
        ).encode(),
        f"{expected_head}\t{expected_ref}\textra\n".encode(),
        f"{expected_head}\t{expected_ref}\n".encode(),
    ))

    def no_network_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command, 0, stdout=next(outputs), stderr=b"network disabled"
        )

    monkeypatch.setattr(guard.subprocess, "run", no_network_run)
    results = [
        guard.native_remote_head(
            tmp_path, "https://example.invalid/repository.git", expected_ref
        )
        for _ in range(4)
    ]

    assert results == [None, None, None, expected_head]


@pytest.mark.parametrize("phase", ["publish", "post-push"])
def test_publish_remote_authority_is_observed_only_inside_publication_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    repo, origin, _, lease = _fixture(tmp_path)
    _write(repo / "owned.txt", "feature\n")
    _git(repo, "add", "owned.txt")
    _git(repo, "commit", "-q", "-m", "feature")
    head = _git(repo, "rev-parse", "HEAD")
    base = _git(repo, "rev-parse", "refs/remotes/origin/main")
    if phase == "post-push":
        _git(repo, "push", "-q", "-u", "origin", "agent/test-loop")
    helper_sentinel = tmp_path / f"pre-boundary-{phase}-helper-executed"
    remote_helper = tmp_path / "remote-helper"
    remote_helper.write_text(
        "#!/bin/sh\n"
        f"touch {shlex.quote(str(helper_sentinel))}\n"
        "exit 1\n",
        encoding="utf-8",
    )
    remote_helper.chmod(0o755)
    _git(repo, "config", "protocol.ext.allow", "always")
    _git(
        repo,
        "config",
        f"url.ext::{remote_helper}.insteadOf",
        str(origin),
    )
    boundary_calls: list[dict[str, object]] = []

    def publication_status(**kwargs):
        boundary_calls.append(kwargs)
        return {
            "status": "PASS",
            "reasons": [],
            "admission_scope": {"lw2_selected": False, "dirty_scope": ["owned.txt"]},
            "lease": {
                "task_id": lease["writer_task_id"],
                "owner": lease["writer_owner"],
                "expires_at": "2035-01-01T00:00:00+00:00",
            },
            "publication_boundary": {
                "publication_source_sha": head,
                "push_refspec": f"{head}:refs/heads/agent/test-loop",
                "local_origin_main": base,
                "true_origin_main": base,
                "true_remote_branch_head": head if phase == "post-push" else None,
                "observed_at": "2030-01-01T00:00:00+00:00",
            },
        }

    monkeypatch.setattr(
        guard, "filesystem_writer_lease_action", publication_status
    )
    packet = guard.evaluate(
        repo,
        phase=phase,
        expected_branch="agent/test-loop",
        expected_head=head,
        **lease,
    )

    assert packet["status"] == "PASS"
    assert packet["state"]["true_origin_main"] == base
    if phase == "post-push":
        assert packet["state"]["true_remote_branch_head"] == head
    assert len(boundary_calls) == 1
    assert not helper_sentinel.exists()


def test_direct_publication_status_requires_explicit_phase_branch_and_sha(
    tmp_path: Path,
) -> None:
    repo, _, _, lease = _fixture(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    base = {
        "action": "publication-status",
        "repo": repo,
        "task_id": lease["writer_task_id"],
        "owner": lease["writer_owner"],
        "lease_id": lease["writer_lease_id"],
        "admission_id": lease["writer_admission_id"],
        "publication_phase": "publish",
        "publication_expected_branch": "agent/test-loop",
        "publication_expected_head": head,
    }
    required = {
        "publication_phase": "PUBLICATION_PHASE_REQUIRED",
        "publication_expected_branch": "PUBLICATION_BRANCH_REQUIRED",
        "publication_expected_head": "PUBLICATION_SOURCE_SHA_REQUIRED",
    }

    for field, reason in required.items():
        arguments = dict(base)
        arguments.pop(field)
        result = filesystem_writer_lease_action(**arguments)
        assert result["status"] == "FAIL"
        assert result["reasons"] == [reason]
        assert "publication_boundary" not in result


def test_main_sync_remote_authority_ignores_local_redirect_and_protocol_helper(
    tmp_path: Path,
) -> None:
    _, origin, repo, _ = _fixture(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    sentinel = tmp_path / "main-sync-helper-executed"
    remote_helper = tmp_path / "main-sync-helper"
    remote_helper.write_text(
        "#!/bin/sh\n"
        f"touch {shlex.quote(str(sentinel))}\n"
        "exit 1\n",
        encoding="utf-8",
    )
    remote_helper.chmod(0o755)
    _git(repo, "config", "protocol.ext.allow", "always")
    _git(
        repo,
        "config",
        f"url.ext::{remote_helper}.insteadOf",
        str(origin),
    )

    packet = guard.evaluate(
        repo,
        phase="main-sync",
        expected_origin_head=head,
    )

    assert packet["status"] == "PASS"
    assert packet["state"]["true_origin_main"] == head
    assert not sentinel.exists()


def test_start_requires_exact_clean_feature_head(tmp_path: Path) -> None:
    repo, _, _, lease = _fixture(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    packet = guard.evaluate(
        repo,
        phase="start",
        expected_branch="agent/test-loop",
        expected_head=head,
        **lease,
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
        **lease,
    )
    assert dirty["status"] == "FAIL"
    assert "DIRTY_WORKTREE" in dirty["reasons"]


def test_dirty_inventory_failures_block_every_phase(
    tmp_path: Path, monkeypatch
) -> None:
    repo, _, _, lease = _fixture(tmp_path)
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
            **lease,
        )
        assert packet["status"] == "FAIL"
        assert {
            "TRACKED_DIRTY_STATE_UNAVAILABLE",
            "STAGED_STATE_UNAVAILABLE",
            "UNTRACKED_STATE_UNAVAILABLE",
            "DIFF_STATE_UNAVAILABLE",
        }.issubset(packet["reasons"])


def test_checkpoint_rejects_unowned_and_oversized_dirty_scope(tmp_path: Path) -> None:
    repo, _, _, lease = _fixture(tmp_path)
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
        **lease,
    )
    assert packet["status"] == "FAIL"
    assert "UNOWNED_DIRTY_PATH" in packet["reasons"]
    assert "DIRTY_FILE_BUDGET_EXCEEDED" in packet["reasons"]
    assert "DIFF_LINE_BUDGET_EXCEEDED" in packet["reasons"]


def test_start_rejects_feature_branch_tracking_origin_main(tmp_path: Path) -> None:
    repo, _, _, lease = _fixture(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "branch", "--set-upstream-to=origin/main", "agent/test-loop")
    packet = guard.evaluate(
        repo,
        phase="start",
        expected_branch="agent/test-loop",
        expected_head=head,
        **lease,
    )
    assert packet["status"] == "FAIL"
    assert "UPSTREAM_MISMATCH" in packet["reasons"]


def test_checkpoint_passes_exact_unstaged_allowlist(tmp_path: Path) -> None:
    repo, _, _, lease = _fixture(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    _write(repo / "owned.txt", "bounded change\n")
    packet = guard.evaluate(
        repo,
        phase="checkpoint",
        expected_branch="agent/test-loop",
        expected_head=head,
        allow_paths=["owned.txt"],
        **lease,
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
        **lease,
    )
    assert "PREEXISTING_STAGED_CHANGES" in staged["reasons"]


def test_checkpoint_never_executes_configured_textconv(tmp_path: Path) -> None:
    repo, _, _, lease = _fixture(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    sentinel = tmp_path / "guard-textconv-executed"
    attributes = Path(_git(repo, "rev-parse", "--git-path", "info/attributes"))
    if not attributes.is_absolute():
        attributes = repo / attributes
    _write(attributes, "owned.txt diff=sentinel\n")
    _git(repo, "config", "diff.sentinel.textconv", f"touch {sentinel}")
    _write(repo / "owned.txt", "bounded change\n")

    packet = guard.evaluate(
        repo,
        phase="checkpoint",
        expected_branch="agent/test-loop",
        expected_head=head,
        allow_paths=["owned.txt"],
        **lease,
    )

    assert packet["status"] == "PASS"
    assert not sentinel.exists()


def test_checkpoint_caller_allowlist_cannot_widen_admitted_dirty_scope(
    tmp_path: Path,
) -> None:
    repo, _, _, lease = _fixture(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    _write(repo / "outside.txt", "not admitted\n")

    packet = guard.evaluate(
        repo,
        phase="checkpoint",
        expected_branch="agent/test-loop",
        expected_head=head,
        allow_paths=["outside.txt"],
        **lease,
    )

    assert packet["status"] == "FAIL"
    assert "DIRTY_PATH_OUTSIDE_ADMITTED_SCOPE" in packet["reasons"]


def test_checkpoint_protected_path_requires_lw2_admission(tmp_path: Path) -> None:
    repo, _, _, lease = _fixture(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    protected = (
        "helper_scripts/maintenance_scripts/"
        "agent_governance_s2e_launch_receipts.py"
    )
    _write(repo / protected, "protected mutation\n")

    packet = guard.evaluate(
        repo,
        phase="checkpoint",
        expected_branch="agent/test-loop",
        expected_head=head,
        allow_paths=[protected],
        **lease,
    )

    assert packet["status"] == "FAIL"
    assert (
        "LW2_PROTECTED_PATH_REQUIRES_LW2_ADMISSION" in packet["reasons"]
    )


def test_checkpoint_rename_cannot_hide_protected_source_from_ordinary_scope(
    tmp_path: Path,
) -> None:
    protected = (
        "helper_scripts/maintenance_scripts/"
        "agent_governance_s2e_launch_receipts.py"
    )
    destination = "renamed.txt"
    repo, _, _, lease = _fixture(
        tmp_path,
        extra_tracked={
            protected: "protected source bytes\n",
        },
        dirty_scope=[destination],
    )
    head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "config", "diff.renames", "true")
    (repo / protected).rename(repo / destination)
    _git(repo, "add", "-N", "--", destination)
    assert _git(repo, "diff", "--cached", "--name-only", "--") == ""
    assert _git(repo, "diff", "--name-only", "HEAD", "--") == destination

    packet = guard.evaluate(
        repo,
        phase="checkpoint",
        expected_branch="agent/test-loop",
        expected_head=head,
        allow_paths=[destination],
        **lease,
    )

    assert packet["status"] == "FAIL"
    assert protected in packet["state"]["dirty_paths"]
    assert "DIRTY_PATH_OUTSIDE_ADMITTED_SCOPE" in packet["reasons"]
    assert "LW2_PROTECTED_PATH_REQUIRES_LW2_ADMISSION" in packet["reasons"]


def test_publish_and_post_push_bind_remote_branch_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, origin, _, lease = _fixture(tmp_path)
    _write(repo / "owned.txt", "feature\n")
    _git(repo, "add", "owned.txt")
    _git(repo, "commit", "-q", "-m", "feature")
    head = _git(repo, "rev-parse", "HEAD")
    public_origin = "https://github.com/example/guard-fixture.git"

    def fixture_remote_head(
        _repo: Path, repository_url: str, ref: str,
    ) -> str | None:
        assert repository_url == public_origin
        completed = subprocess.run(
            ["git", "-C", str(origin), "show-ref", "--verify", "--hash", ref],
            check=False,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip() if completed.returncode == 0 else None

    monkeypatch.setattr(
        governance_capture,
        "native_origin_urls",
        lambda _repo: ([public_origin], [public_origin]),
    )
    monkeypatch.setattr(
        governance_capture, "native_remote_head", fixture_remote_head
    )

    publish = guard.evaluate(
        repo,
        phase="publish",
        expected_branch="agent/test-loop",
        expected_head=head,
        **lease,
    )
    assert publish["status"] == "PASS"

    before_push = guard.evaluate(
        repo,
        phase="post-push",
        expected_branch="agent/test-loop",
        expected_head=head,
        **lease,
    )
    assert "REMOTE_BRANCH_HEAD_MISMATCH" in before_push["reasons"]

    _git(repo, "push", "-q", "origin", "agent/test-loop")
    without_upstream = guard.evaluate(
        repo,
        phase="post-push",
        expected_branch="agent/test-loop",
        expected_head=head,
        **lease,
    )
    assert without_upstream["state"]["true_remote_branch_head"] == head
    assert "UPSTREAM_MISMATCH" in without_upstream["reasons"]

    _git(repo, "branch", "--set-upstream-to=origin/agent/test-loop")
    after_push = guard.evaluate(
        repo,
        phase="post-push",
        expected_branch="agent/test-loop",
        expected_head=head,
        **lease,
    )
    assert after_push["status"] == "PASS"
    assert after_push["state"]["true_remote_branch_head"] == head


@pytest.mark.parametrize("phase", ["publish", "post-push"])
def test_publish_has_no_io_after_publication_status_finalization(
    tmp_path: Path, monkeypatch, phase: str,
) -> None:
    repo, _, _, lease = _fixture(tmp_path)
    _write(repo / "owned.txt", "feature\n")
    _git(repo, "add", "owned.txt")
    _git(repo, "commit", "-q", "-m", "feature")
    head = _git(repo, "rev-parse", "HEAD")
    base = _git(repo, "rev-parse", "refs/remotes/origin/main")
    advanced = "f" * 40
    calls: list[str] = []
    boundary_complete = False
    final_clock = datetime(2030, 1, 1, tzinfo=timezone.utc)
    native_git = guard._git

    def git_before_boundary(*args, **kwargs):
        assert not boundary_complete
        return native_git(*args, **kwargs)

    def live_main(_repo: Path, ref: str, remote: str = "origin") -> str:
        calls.append(f"remote:{remote}:{ref}")
        return head if ref != "refs/heads/main" else base

    def publication_status(**kwargs):
        nonlocal boundary_complete
        calls.append("publication-status")
        assert kwargs["publication_phase"] == phase
        assert kwargs["publication_expected_branch"] == "agent/test-loop"
        assert kwargs["publication_expected_head"] == head
        boundary_complete = True
        return {
            "status": "FAIL",
            "reasons": ["FINAL_TRUE_ORIGIN_MAIN_DRIFT"],
            "lease": {
                "task_id": lease["writer_task_id"],
                "owner": lease["writer_owner"],
                "expires_at": (
                    final_clock + timedelta(hours=1)
                ).isoformat(),
            },
            "admission_scope": {"lw2_selected": True, "dirty_scope": ["owned.txt"]},
            "publication_status": {
                "accepted_base": {"head": base},
            },
            "publication_boundary": {
                "publication_source_sha": head,
                "push_refspec": f"{head}:refs/heads/agent/test-loop",
                "local_origin_main": base,
                "true_origin_main": advanced,
                "observed_at": final_clock.isoformat(),
            },
        }

    monkeypatch.setattr(guard, "_git", git_before_boundary)
    monkeypatch.setattr(guard, "_true_remote_head", live_main)
    monkeypatch.setattr(
        guard, "filesystem_writer_lease_action", publication_status
    )
    monkeypatch.setattr(guard, "_utc_now", lambda: pytest.fail("clock after boundary"))

    packet = guard.evaluate(
        repo,
        phase=phase,
        expected_branch="agent/test-loop",
        expected_head=head,
        **lease,
    )

    assert packet["status"] == "FAIL"
    assert packet["state"]["true_origin_main"] == advanced
    assert packet["state"]["publication_boundary"]["true_origin_main"] == advanced
    assert "FINAL_TRUE_ORIGIN_MAIN_DRIFT" in packet["reasons"]
    assert calls == ["publication-status"]


def test_publish_rejects_lease_expiring_exactly_at_final_clock(
    tmp_path: Path, monkeypatch,
) -> None:
    repo, _, _, lease = _fixture(tmp_path)
    _write(repo / "owned.txt", "feature\n")
    _git(repo, "add", "owned.txt")
    _git(repo, "commit", "-q", "-m", "feature")
    head = _git(repo, "rev-parse", "HEAD")
    base = _git(repo, "rev-parse", "refs/remotes/origin/main")
    final_clock = datetime(2030, 1, 1, tzinfo=timezone.utc)

    monkeypatch.setattr(
        guard,
        "_true_remote_head",
        lambda _repo, ref, remote="origin": head
        if ref != "refs/heads/main"
        else base,
    )
    monkeypatch.setattr(
        guard,
        "filesystem_writer_lease_action",
        lambda **_kwargs: {
            "status": "FAIL",
            "reasons": ["WRITER_LEASE_EXPIRED"],
            "lease": {
                "task_id": lease["writer_task_id"],
                "owner": lease["writer_owner"],
                "expires_at": final_clock.isoformat(),
            },
            "admission_scope": {
                "lw2_selected": True,
                "dirty_scope": ["owned.txt"],
            },
            "publication_status": {"accepted_base": {"head": base}},
            "publication_boundary": {
                "publication_source_sha": head,
                "push_refspec": f"{head}:refs/heads/agent/test-loop",
                "local_origin_main": base,
                "true_origin_main": base,
                "observed_at": final_clock.isoformat(),
            },
        },
    )
    monkeypatch.setattr(
        guard, "_utc_now", lambda: pytest.fail("guard clock is outside seam")
    )

    packet = guard.evaluate(
        repo,
        phase="publish",
        expected_branch="agent/test-loop",
        expected_head=head,
        **lease,
    )

    assert packet["status"] == "FAIL"
    assert packet["reasons"] == ["WRITER_LEASE_EXPIRED"]


def test_main_sync_is_exact_head_and_fast_forward_only(tmp_path: Path) -> None:
    _, origin, repo, _ = _fixture(tmp_path)
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(origin), str(other)], check=True)
    _git(other, "config", "user.email", "other@example.invalid")
    _git(other, "config", "user.name", "Other User")
    _write(other / "remote.txt", "remote advance\n")
    _git(other, "add", "remote.txt")
    _git(other, "commit", "-q", "-m", "remote advance")
    _git(other, "push", "-q", "origin", "main")
    expected = _git(other, "rev-parse", "HEAD")

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


def test_feature_guard_requires_valid_lease_and_linked_worktree(tmp_path: Path) -> None:
    repo, _, primary, lease = _fixture(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    missing = guard.evaluate(
        repo,
        phase="start",
        expected_branch="agent/test-loop",
        expected_head=head,
    )
    assert "WRITER_LEASE_REQUIRED" in missing["reasons"]

    missing_admission = guard.evaluate(
        repo,
        phase="start",
        expected_branch="agent/test-loop",
        expected_head=head,
        **{
            field: value
            for field, value in lease.items()
            if field != "writer_admission_id"
        },
    )
    assert "WRITER_ADMISSION_ID_REQUIRED" in missing_admission["reasons"]

    missing_owner = guard.evaluate(
        repo,
        phase="start",
        expected_branch="agent/test-loop",
        expected_head=head,
        writer_task_id=lease["writer_task_id"],
        writer_lease_id=lease["writer_lease_id"],
    )
    assert "WRITER_LEASE_REQUIRED" in missing_owner["reasons"]

    foreign = guard.evaluate(
        repo,
        phase="start",
        expected_branch="agent/test-loop",
        expected_head=head,
        **{**lease, "writer_lease_id": "foreign"},
    )
    assert "WRITER_LEASE_ID_MISMATCH" in foreign["reasons"]

    _git(primary, "branch", "agent/primary-test")
    _git(primary, "switch", "-q", "agent/primary-test")
    primary_head = _git(primary, "rev-parse", "HEAD")
    primary_packet = guard.evaluate(
        primary,
        phase="start",
        expected_branch="agent/primary-test",
        expected_head=primary_head,
        **lease,
    )
    assert "LINKED_WORKTREE_REQUIRED" in primary_packet["reasons"]


def test_sync_contract_covers_exact_head_publication_merge_and_three_sides() -> None:
    for required in (
        "git_loop_guard.py",
        "--phase start",
        "--phase checkpoint",
        "--writer-admission-id",
        "--admission-id",
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

    writer_release_command = """python3 helper_scripts/maintenance_scripts/agent_governance.py writer-lease \\
  --lease-action release --repo . \\
  --task-id "$WRITER_TASK_ID" --owner "$WRITER_OWNER" \\
  --lease-id "$WRITER_LEASE_ID" \\
  --admission-id "$WRITER_ADMISSION_ID"""  # noqa: E501
    admission_release_command = """python3 helper_scripts/maintenance_scripts/agent_governance.py task-admission \\
  --admission-action release --repo . \\
  --task-id "$WRITER_TASK_ID" --owner "$WRITER_OWNER" \\
  --admission-id "$WRITER_ADMISSION_ID"""  # noqa: E501
    assert writer_release_command in SYNC
    assert admission_release_command in SYNC
    assert SYNC.index(writer_release_command) < SYNC.index(
        admission_release_command
    )
    normalized_sync = " ".join(SYNC.split())
    for required in (
        "Legitimate renames must admit and allow both",
        "deleted source and the added destination",
        "Bound cleanup verifies the exact admission ID",
        "cannot prove its historical admission binding",
        "exact task/owner/lease cleanup-only",
    ):
        assert required in normalized_sync


def test_sync_contract_documents_publish_only_lw2_authority_transition() -> None:
    normalized_sync = " ".join(SYNC.split())
    for required in (
        "publication-status",
        "read-only, nonrenewing, and nonpersisting",
        "exact ACTIVE task admission and its exact bound ACTIVE writer lease",
        "trusted entry and final recapture times",
        "accepted externally attested published-main base",
        "clean, strictly linear admitted native feature range",
        "native graph, provenance, committed paths, and generation",
        "only the `publish` and `post-push` guard phases",
        "generic `status`/`renew` and the `start`/`checkpoint` guard phases",
        "does not authorize further edits",
        "post-merge readmission is main-only",
    ):
        assert required in normalized_sync

    assert (
        "acquires a fresh bound lease before checkpoint/start/publication"
        not in normalized_sync
    )


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


def test_gui_loop_driver_uses_the_same_finite_execution_gate() -> None:
    for required in (
        "第一控制行精確等於",
        "exact `ACTIVE`",
        "`IN_PROGRESS` 不得重派",
        "persisted task-admission fencing",
        "preceding snapshot",
        "沒有 ACTIVE",
        "`BLOCKED_NO_DELTA`",
        "status、blocker、round/time、caller receipt",
    ):
        assert required in GUI_LOOP
    assert "does not itself grant a\nwakeup" in ALR_LOOP


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
