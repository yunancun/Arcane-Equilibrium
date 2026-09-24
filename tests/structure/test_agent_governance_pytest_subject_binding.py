"""Public-entry regression tests for governed pytest subject binding."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
IMPLEMENTATION = ROOT / "helper_scripts/maintenance_scripts"
if str(IMPLEMENTATION) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION))

import agent_governance_command_capture_v2 as capture_v2  # noqa: E402
import agent_governance_capture_binding as capture_binding  # noqa: E402


def _git(repository: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *argv], cwd=repository, check=True,
        capture_output=True, text=True,
    )


def _repository(tmp_path: Path, *, assertion: str = "VALUE == 1") -> Path:
    repository = tmp_path / "repo"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.email", "binding@example.invalid")
    _git(repository, "config", "user.name", "Binding Test")
    (repository / "subject.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repository / "test_subject.py").write_text(
        "from subject import VALUE\n\n"
        f"def test_subject():\n    assert {assertion}\n",
        encoding="utf-8",
    )
    _git(repository, "add", "subject.py", "test_subject.py")
    _git(repository, "commit", "-qm", "fixture")
    return repository


def _bind_context(
    monkeypatch: pytest.MonkeyPatch,
    *,
    dirty_scope: list[str],
    verification_scope: list[str],
) -> None:
    task = {
        "node_id": "review", "role": "E2", "native_agent": "E2",
        "node_class": "verification", "permission": "read_only",
        "requires": [], "path_scope": [],
    }
    contract = {
        "dirty_scope": dirty_scope,
        "verification_scope": verification_scope,
    }
    monkeypatch.setattr(
        capture_v2, "_bound_execution_task",
        lambda _context, _native, _node, _root: (
            task, contract, verification_scope,
        ),
    )
    monkeypatch.setattr(
        capture_v2, "authorize_native_command",
        lambda native, _command: {
            "allowed": True, "policy_class": "repo_or_local_test_read",
            "reason": "test fixture", "native_agent": native,
            "role_id": "E2", "node_class": "verification",
            "effective_permission": "read_only",
        },
    )


def _capture(
    repository: Path,
    *,
    argv: list[str] | None = None,
) -> dict:
    return capture_v2.capture_governed_command(
        native_agent="E2",
        node_id="review",
        context_artifact={
            "artifact_digest": "sha256:" + "a" * 64,
            "task_contract_digest": "sha256:" + "b" * 64,
        },
        argv=argv or [
            *capture_v2.GOVERNED_PYTEST_PREFIX,
            *capture_v2.GOVERNED_PYTEST_REQUIRED_ARGS,
            "-q", "test_subject.py",
        ],
        root=repository,
        timeout_seconds=30,
    )


@pytest.mark.parametrize(
    ("mutation", "dirty_scope"),
    [
        ("unstaged", ["subject.py"]),
        ("staged", ["subject.py"]),
        ("new", ["new_subject.py"]),
        ("deleted", ["subject.py"]),
        ("renamed", ["subject.py", "renamed_subject.py"]),
    ],
)
def test_public_governed_pytest_rejects_changed_admitted_subject_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    dirty_scope: list[str],
) -> None:
    repository = _repository(tmp_path)
    if mutation == "unstaged":
        (repository / "subject.py").write_text("VALUE = 999\n", encoding="utf-8")
    elif mutation == "staged":
        (repository / "subject.py").write_text("VALUE = 999\n", encoding="utf-8")
        _git(repository, "add", "subject.py")
    elif mutation == "new":
        (repository / "new_subject.py").write_text("VALUE = 999\n", encoding="utf-8")
    elif mutation == "deleted":
        (repository / "subject.py").unlink()
    else:
        _git(repository, "mv", "subject.py", "renamed_subject.py")

    _bind_context(
        monkeypatch,
        dirty_scope=dirty_scope,
        verification_scope=["test_subject.py"],
    )
    executed: list[list[str]] = []
    real_execute = capture_v2._execute

    def observe_execute(argv: list[str], **kwargs: object) -> dict:
        executed.append(argv)
        return real_execute(argv, **kwargs)

    monkeypatch.setattr(capture_v2, "_execute", observe_execute)
    with pytest.raises(
        PermissionError,
        match="committed checkpoint.*fresh Context",
    ):
        _capture(repository)
    assert executed == []


@pytest.mark.parametrize(
    ("assertion", "expected"),
    [("VALUE == 1", "PASS"), ("VALUE == 2", "FAIL")],
)
def test_public_governed_pytest_executes_clean_exact_head_and_reports_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    assertion: str,
    expected: str,
) -> None:
    repository = _repository(tmp_path, assertion=assertion)
    _bind_context(
        monkeypatch,
        dirty_scope=["subject.py"],
        verification_scope=["test_subject.py"],
    )

    record = _capture(repository)

    assert record["result"] == expected
    # The union is an internal pytest subject preflight.  The public capture
    # scope retains its existing verification-scope meaning.
    assert record["path_scope"] == ["test_subject.py"]
    assert record["source_materialization"]["source_head"] == _git(
        repository, "rev-parse", "HEAD",
    ).stdout.strip()


def test_non_pytest_diff_remains_available_on_a_dirty_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    (repository / "subject.py").write_text("VALUE = 999\n", encoding="utf-8")
    _bind_context(
        monkeypatch,
        dirty_scope=["subject.py"],
        verification_scope=["test_subject.py"],
    )

    record = _capture(repository, argv=["git", "diff", "--", "subject.py"])

    assert record["result"] == "PASS"
    assert "VALUE = 999" in record["stdout"]["preview_text"]
    assert record["path_scope"] == ["test_subject.py"]


@pytest.mark.parametrize(
    "concealment",
    ["assume-unchanged", "ignored-new", "mode", "symlink"],
)
def test_public_subject_binding_is_not_hidden_by_git_or_filesystem_tricks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    concealment: str,
) -> None:
    repository = _repository(tmp_path)
    dirty_scope = ["subject.py"]
    if concealment == "assume-unchanged":
        _git(repository, "update-index", "--assume-unchanged", "subject.py")
        (repository / "subject.py").write_text("VALUE = 999\n", encoding="utf-8")
    elif concealment == "ignored-new":
        (repository / ".gitignore").write_text("ignored_subject.py\n", encoding="utf-8")
        _git(repository, "add", ".gitignore")
        _git(repository, "commit", "-qm", "ignore fixture subject")
        (repository / "ignored_subject.py").write_text(
            "VALUE = 999\n", encoding="utf-8",
        )
        dirty_scope = ["ignored_subject.py"]
    elif concealment == "mode":
        _git(repository, "config", "core.filemode", "false")
        (repository / "subject.py").chmod(0o755)
    else:
        outside = tmp_path / "outside-subject.py"
        outside.write_text("VALUE = 1\n", encoding="utf-8")
        (repository / "subject.py").unlink()
        (repository / "subject.py").symlink_to(outside)

    _bind_context(
        monkeypatch,
        dirty_scope=dirty_scope,
        verification_scope=["test_subject.py"],
    )
    with pytest.raises(PermissionError, match="committed checkpoint"):
        _capture(repository)


def test_public_subject_binding_rejects_invalid_dirty_scope_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    task = {
        "node_id": "review", "role": "E2", "native_agent": "E2",
        "node_class": "verification", "permission": "read_only",
        "requires": [], "path_scope": [],
    }
    monkeypatch.setattr(
        capture_v2, "_bound_execution_task",
        lambda _context, _native, _node, _root: (
            task, {"dirty_scope": "subject.py"}, ["test_subject.py"],
        ),
    )
    monkeypatch.setattr(
        capture_v2, "authorize_native_command",
        lambda native, _command: {
            "allowed": True, "policy_class": "repo_or_local_test_read",
            "reason": "test fixture", "native_agent": native,
            "role_id": "E2", "node_class": "verification",
            "effective_permission": "read_only",
        },
    )
    executed: list[list[str]] = []
    monkeypatch.setattr(
        capture_v2, "_execute",
        lambda argv, **_kwargs: executed.append(argv),
    )

    with pytest.raises(PermissionError, match="scopes are not canonical"):
        _capture(repository)
    assert executed == []


def test_public_subject_binding_never_traverses_a_replaced_subject_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    package = repository / "package"
    package.mkdir()
    (package / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repository, "add", "package/module.py")
    _git(repository, "commit", "-qm", "add package subject")

    outside = tmp_path / "outside-package"
    outside.mkdir()
    (outside / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "module.py").unlink()
    package.rmdir()
    package.symlink_to(outside, target_is_directory=True)
    _bind_context(
        monkeypatch,
        dirty_scope=["package"],
        verification_scope=["test_subject.py"],
    )

    with pytest.raises(PermissionError, match="committed checkpoint"):
        _capture(repository)


def test_plain_pytest_still_points_to_the_supported_canonical_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    _bind_context(
        monkeypatch,
        dirty_scope=["subject.py"],
        verification_scope=["test_subject.py"],
    )

    with pytest.raises(
        PermissionError,
        match="no-site governed bootstrap.*agent_governance.py capture-command",
    ):
        _capture(
            repository,
            argv=["python3", "-m", "pytest", "-q", "test_subject.py"],
        )


def test_trusted_replay_requires_the_admitted_subject_union_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    _bind_context(
        monkeypatch,
        dirty_scope=["subject.py"],
        verification_scope=["test_subject.py"],
    )
    record = _capture(repository)

    # Model a legacy/resealed record captured while the task-owned source was
    # dirty but the verification-only public path_scope remained clean.
    (repository / "subject.py").write_text("VALUE = 999\n", encoding="utf-8")
    record["repository_before"] = capture_v2._generation_summary(
        record["path_scope"], repository,
    )
    record["repository_after"] = record["repository_before"]
    record["whole_repository_before"] = capture_v2._generation_summary(
        ["."], repository,
    )
    record["whole_repository_after"] = record["whole_repository_before"]
    record["record_digest"] = capture_v2._self_digest(record)

    executed: list[list[str]] = []
    real_execute = capture_v2._execute

    def observe_execute(argv: list[str], **kwargs: object) -> dict:
        executed.append(argv)
        return real_execute(argv, **kwargs)

    monkeypatch.setattr(capture_v2, "_execute", observe_execute)
    errors = capture_v2.validate_governed_command_capture(
        record, root=repository, reexecute=True,
    )

    assert any("admitted pytest subject scope" in error for error in errors)
    assert executed == []


def test_trusted_replay_rejects_dirty_admitted_subject_union_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    _bind_context(
        monkeypatch,
        dirty_scope=["subject.py"],
        verification_scope=["test_subject.py"],
    )
    record = _capture(repository)
    (repository / "subject.py").write_text("VALUE = 999\n", encoding="utf-8")
    record["repository_before"] = capture_v2._generation_summary(
        record["path_scope"], repository,
    )
    record["repository_after"] = record["repository_before"]
    record["whole_repository_before"] = capture_v2._generation_summary(
        ["."], repository,
    )
    record["whole_repository_after"] = record["whole_repository_before"]
    record["record_digest"] = capture_v2._self_digest(record)
    executed: list[list[str]] = []
    real_execute = capture_v2._execute

    def observe_execute(argv: list[str], **kwargs: object) -> dict:
        executed.append(argv)
        return real_execute(argv, **kwargs)

    monkeypatch.setattr(capture_v2, "_execute", observe_execute)
    errors = capture_v2.validate_governed_command_capture(
        record,
        root=repository,
        reexecute=True,
        expected_subject_scope=["subject.py", "test_subject.py"],
    )

    assert any("differs from committed checkpoint" in error for error in errors)
    assert executed == []


def test_trusted_replay_executes_clean_admitted_subject_union(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    _bind_context(
        monkeypatch,
        dirty_scope=["subject.py"],
        verification_scope=["test_subject.py"],
    )
    record = _capture(repository)
    executed: list[list[str]] = []
    real_execute = capture_v2._execute

    def observe_execute(argv: list[str], **kwargs: object) -> dict:
        executed.append(argv)
        return real_execute(argv, **kwargs)

    monkeypatch.setattr(capture_v2, "_execute", observe_execute)
    errors = capture_v2.validate_governed_command_capture(
        record,
        root=repository,
        reexecute=True,
        expected_subject_scope=["subject.py", "test_subject.py"],
    )

    assert errors == []
    assert executed == [record["argv"]]


def test_closure_binding_passes_the_trusted_dirty_and_verification_union(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dirty_scope = [
        "helper_scripts/maintenance_scripts/runtime_environment_probe.py"
    ]
    verification_scope = [
        "tests/structure/test_agent_governance_command_capture_v2.py"
    ]
    _bind_context(
        monkeypatch,
        dirty_scope=dirty_scope,
        verification_scope=verification_scope,
    )
    record = _capture(
        ROOT,
        argv=[
            *capture_v2.GOVERNED_PYTEST_PREFIX,
            *capture_v2.GOVERNED_PYTEST_REQUIRED_ARGS,
            "-q",
            "tests/structure/test_agent_governance_command_capture_v2.py::"
            "test_governed_pytest_executes_the_exact_committed_tree_not_a_dirty_fix",
        ],
    )
    task = {
        "node_id": "review", "role": "E2", "native_agent": "E2",
        "node_class": "verification", "permission": "read_only",
        "requires": [], "path_scope": [],
    }
    wrapper = {
        "id": "command:review", "scope": "test",
        "kind": "command_capture_v2", "digest": record["record_digest"],
        "artifact": record,
    }

    captured = capture_binding.collect_capture_evidence(
        [wrapper],
        expected_scope=dirty_scope,
        expected_verification_scope=verification_scope,
        expected_source_head=_git(ROOT, "rev-parse", "HEAD").stdout.strip(),
        expected_task_contract_digest=record["task_contract_digest"],
        expected_context_artifact_digest=record["context_artifact_digest"],
        require_current_repository=False,
        expected_execution_tasks={"review": task},
    )

    assert captured["errors"] == []
    assert captured["commands"]["command:review"] == record


def test_lw2_clean_trusted_replay_receives_its_evidence_subject_scope(
    tmp_path: Path,
) -> None:
    fixture_path = (
        ROOT / "tests/structure/test_agent_governance_lw2_readmission.py"
    )
    spec = importlib.util.spec_from_file_location("w5_lw2_fixture", fixture_path)
    assert spec is not None and spec.loader is not None
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)

    repository = tmp_path / "lw2-replay-repo"
    fixture._clone_exact_head_as_main(ROOT, repository)
    subprocess.run(
        [
            "git", "remote", "set-url", "origin",
            fixture.LW2_REPOSITORY_URL,
        ],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", "HEAD"],
        cwd=repository,
        check=True,
    )
    claim_inputs, claim_payloads = fixture._real_claims(repository)

    assert fixture.validate_lw2_readmission_eligibility(
        admission_profile=fixture.LW2_ADMISSION_PROFILE,
        claim_inputs=claim_inputs,
        claim_payloads=claim_payloads,
        current_head=fixture._git_value(repository, "HEAD"),
        current_tree=fixture._git_value(repository, "HEAD^{tree}"),
        repo=repository,
        reexecute_capture=True,
        external_evidence_verifier=fixture._strict_external_verifier(
            claim_payloads
        ),
    ) is True


@pytest.mark.parametrize("replace_during_open", [False, True])
def test_fifo_subject_is_rejected_without_blocking(
    tmp_path: Path, replace_during_open: bool,
) -> None:
    probe = """
import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import agent_governance_pytest_subject_binding as binding
subject = Path(sys.argv[2])
if sys.argv[3] == "race":
    subject.write_text("regular source")
    native_open = os.open
    def replace_then_open(path, flags, *args, **kwargs):
        subject.unlink()
        os.mkfifo(subject)
        return native_open(path, flags, *args, **kwargs)
    binding.os.open = replace_then_open
else:
    os.mkfifo(subject)
try:
    binding._regular_blob(subject)
except ValueError as error:
    assert "not one regular file" in str(error)
else:
    raise AssertionError("FIFO subject was accepted")
"""
    result = subprocess.run(
        [sys.executable, "-c", probe, str(IMPLEMENTATION),
         str(tmp_path / "subject.py"), "race" if replace_during_open else "fifo"],
        capture_output=True, text=True, timeout=3, check=False,
    )
    assert result.returncode == 0, result.stderr
