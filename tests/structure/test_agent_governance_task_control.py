from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from agent_governance_task_control import (  # noqa: E402
    FileWriterLeaseStore,
    InMemoryWriterLeaseStore,
    WorktreeIdentity,
    acquire_writer_lease,
    filesystem_writer_lease_action,
    inspect_worktree,
    _adjudicate_continuation,
    compile_task_execution_policy,
    is_dispatchable,
    main as task_control_main,
    next_action_may_be_null,
    operator_loop_request_digest,
    progress_snapshot,
    queue_lane,
    release_writer_lease,
    renew_writer_lease,
    validate_writer_lease,
)
from agent_governance_task_admission import (  # noqa: E402
    acquire_task_admission,
    continue_admitted_task,
    release_task_admission,
)
from agent_governance import main as governance_main  # noqa: E402
from agent_governance_context import capture_repository_baseline  # noqa: E402
from agent_governance_routing import (  # noqa: E402
    route_task,
    task_contract_projection,
)


NOW = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
SHA = "a" * 40
DIGEST_A = "sha256:" + "1" * 64
DIGEST_B = "sha256:" + "2" * 64
DIGEST_C = "sha256:" + "3" * 64
DIGEST_D = "sha256:" + "4" * 64


def _contract(mode: str, prompt: str, *, dirty_scope: list[str] | None = None) -> dict:
    return {
        "schema_version": "test_task_contract_v1",
        "continuation_mode": mode,
        "task_prompt": prompt,
        "task_prompt_digest": "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "operator_loop_request_digest": (
            operator_loop_request_digest(prompt) if mode == "operator_loop" else None
        ),
        "dirty_scope": dirty_scope or [
            "tests/structure/test_agent_governance_task_control.py"
        ],
    }


def _admission_contract(repo: Path, mode: str, prompt: str) -> dict:
    routed = route_task({
        "task_shape": "implementation",
        "surfaces": ["python"],
        "risk": "low",
        "uncertainty": "low",
        "side_effect_class": "repo_write",
        "objective": prompt,
        "scope": ["owned.txt"],
        "dirty_scope": ["owned.txt"],
        "verification_scope": ["owned.txt"],
        "acceptance_criteria": ["owned bytes changed"],
        "hard_stops": ["no runtime effect"],
        "baseline": capture_repository_baseline(repo),
        "direct_interfaces": ["owned.txt"],
        "previous_failure": "none",
        "task_prompt": prompt,
        "continuation_mode": mode,
    })
    return task_contract_projection(routed["task_facts"])


FINITE_CONTRACT = _contract("finite", "answer this task once and stop")
LOOP_CONTRACT = _contract(
    "operator_loop", "/loop\nmonitor this task until a terminal gate"
)
FINITE_CONTROL = compile_task_execution_policy(FINITE_CONTRACT)
LOOP_CONTROL = compile_task_execution_policy(LOOP_CONTRACT)


def _snapshot(
    round_number: int,
    *,
    status: str = "IN_PROGRESS",
    contract: dict | None = None,
) -> dict:
    bound_contract = contract or LOOP_CONTRACT
    return progress_snapshot(
        round_number=round_number,
        work_status=status,
        repo=ROOT,
        task_contract=bound_contract,
        admitted_task_contract_digest=compile_task_execution_policy(
            bound_contract
        )["task_contract_digest"],
        blocker_code="WAITING_FOR_EVIDENCE",
    )


def _adjudicate(
    *,
    repo: Path = ROOT,
    contract: dict = LOOP_CONTRACT,
    control: dict = LOOP_CONTROL,
    admitted_digest: str | None = None,
    **kwargs,
) -> dict:
    return _adjudicate_continuation(
        repo=repo,
        task_contract=contract,
        admitted_task_contract_digest=(
            admitted_digest or control["task_contract_digest"]
        ),
        task_execution_control=control,
        **kwargs,
    )


def _identity(tmp_path: Path, *, dirty: bool = False) -> WorktreeIdentity:
    common = tmp_path / ".git"
    git_dir = common / "worktrees" / "task"
    return WorktreeIdentity(
        worktree=str((tmp_path / "linked-task").resolve()),
        branch="agent/task",
        head=SHA,
        common_dir=common,
        git_dir=git_dir,
        dirty=dirty,
    )


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Test User"], check=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "--allow-empty", "-m", "init"],
        check=True,
    )
    return repo


def _init_linked_repo(tmp_path: Path) -> Path:
    repo = _init_repo(tmp_path)
    owned = repo / "owned.txt"
    owned.write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "owned.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "owned"],
        check=True,
    )
    linked = tmp_path / "linked"
    subprocess.run(
        [
            "git", "-C", str(repo), "worktree", "add", "-q", "-b",
            "agent/ordinary-lease", str(linked), "main",
        ],
        check=True,
    )
    return linked


def test_finite_is_the_default_terminal_boundary_without_wakeup() -> None:
    decision = _adjudicate(
        contract=FINITE_CONTRACT,
        control=FINITE_CONTROL,
        current=_snapshot(0, contract=FINITE_CONTRACT),
    )
    assert decision["decision"] == "STOP_FINITE_TASK"
    assert decision["schedule_wakeup"] is False
    assert decision["policy"]["automatic_wakeup_admitted"] is False


def test_operator_loop_continues_only_on_a_real_progress_delta() -> None:
    previous = _snapshot(1)
    unchanged = _snapshot(2)
    assert previous["progress_digest"] == unchanged["progress_digest"]
    stopped = _adjudicate(
        previous=previous, current=unchanged
    )
    assert stopped["decision"] == "BLOCKED_NO_DELTA"
    assert stopped["terminal_work_status"] == "BLOCKED_NO_DELTA"
    assert stopped["schedule_wakeup"] is False

    changed = dict(unchanged)
    changed["task_source_manifest"] = [{"path": "forged", "kind": "absent"}]
    changed["task_source_digest"] = "sha256:" + hashlib.sha256(
        b'[{"kind":"absent","path":"forged"}]'
    ).hexdigest()
    changed["progress_digest"] = "sha256:" + hashlib.sha256(
        json.dumps(
            {"task_source_digest": changed["task_source_digest"]},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    try:
        _adjudicate(previous=previous, current=changed)
    except ValueError as error:
        assert "does not match task-owned repository bytes" in str(error)
    else:
        raise AssertionError("self-consistent forged source manifest was admitted")

    forged = dict(unchanged)
    forged["progress_digest"] = DIGEST_A
    try:
        _adjudicate(previous=previous, current=forged)
    except ValueError as error:
        assert "does not match canonical content" in str(error)
    else:
        raise AssertionError("forged progress digest was admitted")


def test_terminal_status_stops_even_in_operator_loop() -> None:
    decision = _adjudicate(
        current=_snapshot(3, status="BLOCKED")
    )
    assert decision["decision"] == "STOP_TERMINAL"
    assert decision["schedule_wakeup"] is False


def test_operator_loop_requires_previous_and_semantic_task_owned_delta() -> None:
    missing = _adjudicate(
        current=_snapshot(1, status="ACTIVE"),
    )
    assert missing["decision"] == "STOP_MISSING_PREVIOUS"
    assert missing["schedule_wakeup"] is False

    previous = _snapshot(1, status="ACTIVE")
    status_only = _snapshot(2, status="IN_PROGRESS")
    assert previous["progress_digest"] == status_only["progress_digest"]
    assert _adjudicate(
        previous=previous,
        current=status_only,
    )["decision"] == "BLOCKED_NO_DELTA"

    unrelated_head_only = dict(status_only)
    unrelated_head_only["source_head"] = "b" * 40
    assert previous["progress_digest"] == unrelated_head_only["progress_digest"]
    task_owned_change = _snapshot(2, status="IN_PROGRESS")
    assert _adjudicate(
        previous=previous,
        current=task_owned_change,
    )["decision"] == "BLOCKED_NO_DELTA"


def test_operator_loop_control_requires_exact_prompt_marker_and_cannot_flip() -> None:
    for prompt in (
        "answer once and stop; do not loop",
        "answer once and stop; do not /loop",
        "```\n/loop\n```",
        "Never execute this command:\n/loop do not continue",
        "/loop do not continue; answer once",
        "/loop is forbidden in this example",
    ):
        try:
            compile_task_execution_policy(_contract("operator_loop", prompt))
        except ValueError as error:
            assert "leading /loop control line" in str(error)
        else:
            raise AssertionError("operator loop without the Operator marker was admitted")

    replacement_contract = _contract("operator_loop", "/loop\ncontinue")
    replacement_control = compile_task_execution_policy(replacement_contract)
    try:
        _adjudicate(
            contract=replacement_contract,
            control=replacement_control,
            admitted_digest=FINITE_CONTROL["task_contract_digest"],
            previous=_snapshot(1, contract=replacement_contract),
            current=_snapshot(
                2, contract=replacement_contract
            ),
        )
    except ValueError as error:
        assert "admitted task contract digest" in str(error)
    else:
        raise AssertionError("caller-flipped continuation control was admitted")


def test_progress_snapshot_captures_owned_bytes_and_rejects_digest_only_delta(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    owned = repo / "owned.txt"
    owned.write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "owned.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "base"], check=True
    )
    contract = _contract(
        "operator_loop", "/loop\nverify owned bytes", dirty_scope=["owned.txt"]
    )
    control = compile_task_execution_policy(contract)

    def capture(round_number: int) -> dict:
        return progress_snapshot(
            round_number=round_number,
            work_status="ACTIVE",
            repo=repo,
            task_contract=contract,
            admitted_task_contract_digest=control["task_contract_digest"],
            blocker_code="WAITING_FOR_EVIDENCE",
        )

    previous = capture(1)
    forged = dict(capture(2))
    forged["task_source_digest"] = "sha256:" + "f" * 64
    try:
        _adjudicate(
            repo=repo,
            contract=contract,
            control=control,
            previous=previous,
            current=forged,
        )
    except ValueError as error:
        assert "does not match canonical content" in str(error)
    else:
        raise AssertionError("digest-only progress delta was admitted")

    owned.write_text("two\n", encoding="utf-8")
    changed = capture(2)
    assert changed["task_source_digest"] != previous["task_source_digest"]
    assert _adjudicate(
        repo=repo,
        contract=contract,
        control=control,
        previous=previous,
        current=changed,
    )["decision"] == "CONTINUE_OPERATOR_LOOP"


def test_governance_cli_uses_persisted_admission_and_previous_snapshot(
    tmp_path: Path, capsys,
) -> None:
    repo = _init_repo(tmp_path)
    owned = repo / "owned.txt"
    owned.write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "owned.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "base"], check=True)
    finite = _admission_contract(repo, "finite", "answer once")
    loop = _admission_contract(repo, "operator_loop", "/loop\ncontinue")

    assert governance_main([
        "task-admission", "--admission-action", "acquire",
        "--repo", str(repo), "--task-id", "forged", "--owner", "agent",
        "--task-contract", json.dumps(
            _contract("operator_loop", "/loop\ncontinue", dirty_scope=["owned.txt"])
        ),
    ]) == 2
    assert "exact normalized task contract" in json.loads(
        capsys.readouterr().out
    )["error"]

    assert governance_main([
        "task-admission", "--admission-action", "acquire",
        "--repo", str(repo), "--task-id", "task-a", "--owner", "operator",
        "--task-contract", json.dumps(finite),
    ]) == 0
    finite_admission = json.loads(capsys.readouterr().out)
    finite_id = finite_admission["admission_id"]

    assert governance_main([
        "task-admission", "--admission-action", "acquire",
        "--repo", str(repo), "--task-id", "task-b", "--owner", "agent",
        "--task-contract", json.dumps(loop),
    ]) == 2
    unattested = json.loads(capsys.readouterr().out)
    assert unattested["reasons"] == ["OPERATOR_REQUEST_ATTESTATION_REQUIRED"]
    assert unattested["admission_id"] is None

    forged_bundle = {
        "repo": str(repo),
        "task_id": "task-a",
        "owner": "operator",
        "admission_id": finite_id,
        "work_status": "ACTIVE",
        "task_contract": loop,
    }
    assert governance_main(["continuation", json.dumps(forged_bundle)]) == 2
    assert "fields are not exact" in json.loads(capsys.readouterr().out)["error"]

    finite_bundle = {
        "repo": str(repo),
        "task_id": "task-a",
        "owner": "operator",
        "admission_id": finite_id,
        "work_status": "ACTIVE",
    }
    assert governance_main(["continuation", json.dumps(finite_bundle)]) == 0
    finite_decision = json.loads(capsys.readouterr().out)["decision"]
    assert finite_decision["decision"] == "STOP_FINITE_TASK"
    assert finite_decision["schedule_wakeup"] is False

    assert governance_main([
        "task-admission", "--admission-action", "release",
        "--repo", str(repo), "--task-id", "task-a", "--owner", "operator",
        "--admission-id", finite_id,
    ]) == 0
    capsys.readouterr()

    loop_args = [
        "task-admission", "--admission-action", "acquire",
        "--repo", str(repo), "--task-id", "task-loop", "--owner", "operator",
        "--task-contract", json.dumps(loop),
    ]
    assert governance_main(loop_args) == 2
    assert json.loads(capsys.readouterr().out)["reasons"] == [
        "OPERATOR_REQUEST_ATTESTATION_REQUIRED"
    ]
    verification_requests = []

    def trusted_operator_request(request: dict) -> bool:
        verification_requests.append(request)
        return request["task_contract"] == loop

    assert governance_main(
        loop_args, operator_request_verifier=trusted_operator_request
    ) == 0
    loop_id = json.loads(capsys.readouterr().out)["admission_id"]
    assert verification_requests == [{
        "schema_version": "operator_loop_admission_request_v1",
        "task_id": "task-loop",
        "owner": "operator",
        "worktree": str(repo.resolve()),
        "task_contract": loop,
        "task_contract_digest": compile_task_execution_policy(loop)[
            "task_contract_digest"
        ],
        "task_prompt_digest": loop["task_prompt_digest"],
        "operator_loop_request_digest": loop["operator_loop_request_digest"],
    }]
    owned.write_text("two\n", encoding="utf-8")
    loop_bundle = {
        "repo": str(repo),
        "task_id": "task-loop",
        "owner": "operator",
        "admission_id": loop_id,
        "work_status": "ACTIVE",
    }
    assert governance_main(["continuation", json.dumps(loop_bundle)]) == 0
    loop_decision = json.loads(capsys.readouterr().out)["decision"]
    assert loop_decision["decision"] == "CONTINUE_OPERATOR_LOOP"
    assert loop_decision["schedule_wakeup"] is True

    assert governance_main(["continuation", json.dumps(loop_bundle)]) == 0
    stopped = json.loads(capsys.readouterr().out)["decision"]
    assert stopped["decision"] == "BLOCKED_NO_DELTA"
    assert stopped["schedule_wakeup"] is False


def test_task_source_manifest_rejects_git_symlink_ancestor_and_fifo(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret\n", encoding="utf-8")
    (repo / "linkdir").symlink_to(outside, target_is_directory=True)
    fifo = repo / "pipe"
    os.mkfifo(fifo)

    for scope in ([".git/config"], ["linkdir/secret.txt"], ["pipe"]):
        contract = _contract("finite", "inspect once", dirty_scope=scope)
        control = compile_task_execution_policy(contract)
        try:
            progress_snapshot(
                round_number=0,
                work_status="ACTIVE",
                repo=repo,
                task_contract=contract,
                admitted_task_contract_digest=control["task_contract_digest"],
            )
        except ValueError as error:
            assert any(
                phrase in str(error)
                for phrase in ("unsafe path", "symlink", "regular files only")
            )
        else:
            raise AssertionError(f"unsafe task-owned scope was captured: {scope}")


def test_queue_lanes_do_not_reopen_waiting_or_closed_work() -> None:
    assert queue_lane("ACTIVE") == "active"
    assert queue_lane("WAITING") == "waiting"
    assert queue_lane("BLOCKED_NO_DELTA") == "closed"
    assert is_dispatchable("ACTIVE") is True
    assert is_dispatchable("IN_PROGRESS") is False
    assert is_dispatchable("WAITING") is False
    assert is_dispatchable("DONE") is False
    assert next_action_may_be_null("DONE") is True
    assert next_action_may_be_null("BLOCKED_NO_DELTA") is True
    assert next_action_may_be_null("BLOCKED") is False


def test_writer_lease_is_exclusive_and_fenced(tmp_path: Path) -> None:
    store = InMemoryWriterLeaseStore()
    identity = _identity(tmp_path)
    acquired = acquire_writer_lease(
        store, identity, task_id="task-a", owner="owner-a", now=NOW
    )
    assert acquired["status"] == "PASS"
    assert set(acquired["lease"]) == {
        "lease_id", "task_id", "owner", "worktree", "branch",
        "acquired_at", "expires_at",
    }
    lease_id = acquired["lease"]["lease_id"]

    duplicate = acquire_writer_lease(
        store, identity, task_id="task-a", owner="owner-a", now=NOW
    )
    assert duplicate["status"] == "FAIL"
    assert duplicate["reasons"] == ["WORKTREE_WRITER_LEASE_HELD"]

    collision = acquire_writer_lease(
        store, identity, task_id="task-b", owner="owner-b", now=NOW
    )
    assert collision["status"] == "FAIL"
    assert collision["reasons"] == ["WORKTREE_WRITER_LEASE_HELD"]

    foreign = validate_writer_lease(
        store, identity, task_id="task-a", owner="owner-a", lease_id="foreign", now=NOW
    )
    assert foreign["status"] == "FAIL"
    assert "WRITER_LEASE_ID_MISMATCH" in foreign["reasons"]

    renewed = renew_writer_lease(
        store,
        identity,
        task_id="task-a",
        owner="owner-a",
        lease_id=lease_id,
        now=NOW + timedelta(minutes=1),
    )
    assert renewed["status"] == "PASS"
    released = release_writer_lease(
        store,
        identity,
        task_id="task-a",
        owner="owner-a",
        lease_id=lease_id,
        now=NOW + timedelta(minutes=2),
    )
    assert released["status"] == "PASS"
    assert store.read()["leases"] == {}


def test_filesystem_writer_acquire_requires_active_task_admission(
    tmp_path: Path,
    capsys,
) -> None:
    repo = _init_linked_repo(tmp_path)
    identity = inspect_worktree(repo)
    store = FileWriterLeaseStore(identity.common_dir)

    wrapper = filesystem_writer_lease_action(
        action="acquire", repo=repo, task_id="ordinary-task", owner="owner",
    )
    assert wrapper["status"] == "FAIL"
    assert wrapper["reasons"] == ["TASK_ADMISSION_ID_REQUIRED"]
    exported = acquire_writer_lease(
        store, identity, task_id="ordinary-task", owner="owner",
    )
    assert exported["status"] == "FAIL"
    assert exported["reasons"] == ["TASK_ADMISSION_ID_REQUIRED"]
    invalid = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="ordinary-task",
        owner="owner",
        admission_id="0" * 32,
    )
    assert invalid["status"] == "FAIL"
    assert invalid["reasons"] == ["TASK_ADMISSION_MISSING"]
    for cli, argv in (
        (
            governance_main,
            [
                "writer-lease", "--lease-action", "acquire",
                "--repo", str(repo), "--task-id", "ordinary-task",
                "--owner", "owner",
            ],
        ),
        (
            task_control_main,
            [
                "writer-lease", "--action", "acquire",
                "--repo", str(repo), "--task-id", "ordinary-task",
                "--owner", "owner",
            ],
        ),
    ):
        assert cli(argv) == 3
        packet = json.loads(capsys.readouterr().out)
        assert packet["reasons"] == ["TASK_ADMISSION_ID_REQUIRED"]
    assert store.read()["leases"] == {}


def test_ordinary_admission_authorizes_seven_field_filesystem_lease(
    tmp_path: Path,
) -> None:
    repo = _init_linked_repo(tmp_path)
    admission = acquire_task_admission(
        repo=repo,
        task_id="ordinary-task",
        owner="owner",
        task_contract=_admission_contract(repo, "finite", "ordinary write"),
    )
    identity = inspect_worktree(repo)
    wrong = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="ordinary-task",
        owner="owner",
        admission_id="0" * 32,
    )
    assert wrong["status"] == "FAIL"
    assert wrong["reasons"] == ["TASK_ADMISSION_ID_MISMATCH"]
    acquired = acquire_writer_lease(
        FileWriterLeaseStore(identity.common_dir),
        identity,
        task_id="ordinary-task",
        owner="owner",
        admission_id=admission["admission_id"],
    )

    assert acquired["status"] == "PASS"
    assert set(acquired["lease"]) == {
        "lease_id", "task_id", "owner", "worktree", "branch",
        "acquired_at", "expires_at",
    }


def test_ordinary_filesystem_lease_lifecycle_requires_exact_active_admission(
    tmp_path: Path,
) -> None:
    repo = _init_linked_repo(tmp_path)
    admission = acquire_task_admission(
        repo=repo,
        task_id="ordinary-task",
        owner="owner",
        task_contract=_admission_contract(repo, "finite", "ordinary write"),
    )
    acquired = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="ordinary-task",
        owner="owner",
        admission_id=admission["admission_id"],
    )
    lease_id = acquired["lease"]["lease_id"]
    assert filesystem_writer_lease_action(
        action="status",
        repo=repo,
        task_id="ordinary-task",
        owner="owner",
        lease_id=lease_id,
        admission_id=admission["admission_id"],
    )["status"] == "PASS"

    terminal = continue_admitted_task(
        repo=repo,
        task_id="ordinary-task",
        owner="owner",
        admission_id=admission["admission_id"],
        work_status="DONE",
    )
    assert terminal["admission"]["state"] == "TERMINAL"
    for action in ("status", "renew"):
        result = filesystem_writer_lease_action(
            action=action,
            repo=repo,
            task_id="ordinary-task",
            owner="owner",
            lease_id=lease_id,
            admission_id=admission["admission_id"],
        )
        assert result["status"] == "FAIL"
        assert result["reasons"] == ["TASK_ADMISSION_TERMINAL"]

    assert release_task_admission(
        repo=repo,
        task_id="ordinary-task",
        owner="owner",
        admission_id=admission["admission_id"],
    )["status"] == "PASS"
    for action in ("status", "renew"):
        result = filesystem_writer_lease_action(
            action=action,
            repo=repo,
            task_id="ordinary-task",
            owner="owner",
            lease_id=lease_id,
            admission_id=admission["admission_id"],
        )
        assert result["status"] == "FAIL"
        assert result["reasons"] == ["TASK_ADMISSION_MISSING"]
    released = filesystem_writer_lease_action(
        action="release",
        repo=repo,
        task_id="ordinary-task",
        owner="owner",
        lease_id=lease_id,
        admission_id=admission["admission_id"],
    )
    assert released["status"] == "PASS"


def test_publication_status_cli_preserves_ordinary_status_semantics(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _init_linked_repo(tmp_path)
    admission = acquire_task_admission(
        repo=repo,
        task_id="ordinary-task",
        owner="owner",
        task_contract=_admission_contract(repo, "finite", "ordinary write"),
    )
    acquired = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="ordinary-task",
        owner="owner",
        admission_id=admission["admission_id"],
    )
    lease_id = acquired["lease"]["lease_id"]
    store = FileWriterLeaseStore(inspect_worktree(repo).common_dir)
    persisted_before = (
        store.state_path.read_bytes(),
        store.binding_path.read_bytes(),
    )
    direct = filesystem_writer_lease_action(
        action="status",
        repo=repo,
        task_id="ordinary-task",
        owner="owner",
        lease_id=lease_id,
        admission_id=admission["admission_id"],
    )

    calls = (
        (
            governance_main,
            [
                "writer-lease", "--lease-action", "publication-status",
                "--repo", str(repo), "--task-id", "ordinary-task",
                "--owner", "owner", "--lease-id", lease_id,
                "--admission-id", admission["admission_id"],
            ],
        ),
        (
            task_control_main,
            [
                "writer-lease", "--action", "publication-status",
                "--repo", str(repo), "--task-id", "ordinary-task",
                "--owner", "owner", "--lease-id", lease_id,
                "--admission-id", admission["admission_id"],
            ],
        ),
    )
    for cli, argv in calls:
        assert cli(argv) == 0
        packet = json.loads(capsys.readouterr().out)
        assert packet["status"] == direct["status"] == "PASS"
        assert packet["reasons"] == direct["reasons"] == []
        assert packet["lease"] == direct["lease"]
        assert packet["admission_scope"] == direct["admission_scope"]
        assert "publication_status" not in packet
    assert persisted_before == (
        store.state_path.read_bytes(),
        store.binding_path.read_bytes(),
    )


def test_legacy_unbound_filesystem_lease_is_cleanup_only(tmp_path: Path) -> None:
    repo = _init_linked_repo(tmp_path)
    admission = acquire_task_admission(
        repo=repo,
        task_id="ordinary-task",
        owner="owner",
        task_contract=_admission_contract(repo, "finite", "ordinary write"),
    )
    acquired = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="ordinary-task",
        owner="owner",
        admission_id=admission["admission_id"],
    )
    identity = inspect_worktree(repo)
    store = FileWriterLeaseStore(identity.common_dir)
    store.binding_path.unlink()

    for action in ("status", "renew"):
        result = filesystem_writer_lease_action(
            action=action,
            repo=repo,
            task_id="ordinary-task",
            owner="owner",
            lease_id=acquired["lease"]["lease_id"],
            admission_id=admission["admission_id"],
        )
        assert result["status"] == "FAIL"
        assert result["reasons"] == [
            "WRITER_LEASE_ADMISSION_BINDING_MISSING"
        ]
    for direct in (
        validate_writer_lease(
            store,
            identity,
            task_id="ordinary-task",
            owner="owner",
            lease_id=acquired["lease"]["lease_id"],
        ),
        renew_writer_lease(
            store,
            identity,
            task_id="ordinary-task",
            owner="owner",
            lease_id=acquired["lease"]["lease_id"],
        ),
        release_writer_lease(
            store,
            identity,
            task_id="ordinary-task",
            owner="owner",
            lease_id=acquired["lease"]["lease_id"],
        ),
    ):
        assert direct["status"] == "FAIL"
        assert direct["reasons"] == ["TASK_ADMISSION_ACTION_REQUIRED"]
    cleanup = filesystem_writer_lease_action(
        action="release",
        repo=repo,
        task_id="ordinary-task",
        owner="owner",
        lease_id=acquired["lease"]["lease_id"],
        admission_id=admission["admission_id"],
    )
    assert cleanup["status"] == "PASS"
    assert store.read()["leases"] == {}


def test_new_admission_cannot_revive_an_old_ordinary_lease(tmp_path: Path) -> None:
    repo = _init_linked_repo(tmp_path)
    contract = _admission_contract(repo, "finite", "ordinary write")
    first_admission = acquire_task_admission(
        repo=repo,
        task_id="ordinary-task",
        owner="owner",
        task_contract=contract,
    )
    lease = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="ordinary-task",
        owner="owner",
        admission_id=first_admission["admission_id"],
    )["lease"]
    assert release_task_admission(
        repo=repo,
        task_id="ordinary-task",
        owner="owner",
        admission_id=first_admission["admission_id"],
    )["status"] == "PASS"
    second_admission = acquire_task_admission(
        repo=repo,
        task_id="ordinary-task",
        owner="owner",
        task_contract=contract,
    )

    revived = filesystem_writer_lease_action(
        action="status",
        repo=repo,
        task_id="ordinary-task",
        owner="owner",
        lease_id=lease["lease_id"],
        admission_id=second_admission["admission_id"],
    )
    assert revived["status"] == "FAIL"
    assert revived["reasons"] == [
        "WRITER_LEASE_ADMISSION_BINDING_MISMATCH"
    ]
    cleanup = filesystem_writer_lease_action(
        action="release",
        repo=repo,
        task_id="ordinary-task",
        owner="owner",
        lease_id=lease["lease_id"],
        admission_id=first_admission["admission_id"],
    )
    assert cleanup["status"] == "PASS"


def test_ordinary_filesystem_acquire_remains_clean_only(tmp_path: Path) -> None:
    repo = _init_linked_repo(tmp_path)
    admission = acquire_task_admission(
        repo=repo,
        task_id="ordinary-task",
        owner="owner",
        task_contract=_admission_contract(repo, "finite", "ordinary write"),
    )
    (repo / "owned.txt").write_text("dirty\n", encoding="utf-8")

    acquired = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="ordinary-task",
        owner="owner",
        admission_id=admission["admission_id"],
    )

    assert acquired["status"] == "FAIL"
    assert acquired["reasons"] == ["CLEAN_WORKTREE_REQUIRED"]


def test_interrupted_sidecar_persist_leaves_cleanup_only_lease(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _init_linked_repo(tmp_path)
    admission = acquire_task_admission(
        repo=repo,
        task_id="ordinary-task",
        owner="owner",
        task_contract=_admission_contract(repo, "finite", "ordinary write"),
    )
    identity = inspect_worktree(repo)
    store = FileWriterLeaseStore(identity.common_dir)
    original_replace = FileWriterLeaseStore._replace_json

    def interrupt_binding_replace(
        active_store: FileWriterLeaseStore,
        path: Path,
        prefix: str,
        value: dict[str, object],
    ) -> None:
        if path == active_store.binding_path:
            raise OSError("simulated interruption before binding replace")
        original_replace(active_store, path, prefix, value)

    with monkeypatch.context() as scoped:
        scoped.setattr(
            FileWriterLeaseStore, "_replace_json", interrupt_binding_replace
        )
        with pytest.raises(OSError, match="simulated interruption"):
            filesystem_writer_lease_action(
                action="acquire",
                repo=repo,
                task_id="ordinary-task",
                owner="owner",
                admission_id=admission["admission_id"],
            )

    lease = store.read()["leases"][identity.worktree]
    assert store.binding_path.exists() is False
    status = filesystem_writer_lease_action(
        action="status",
        repo=repo,
        task_id="ordinary-task",
        owner="owner",
        lease_id=lease["lease_id"],
        admission_id=admission["admission_id"],
    )
    assert status["status"] == "FAIL"
    assert status["reasons"] == ["WRITER_LEASE_ADMISSION_BINDING_MISSING"]
    cleanup = filesystem_writer_lease_action(
        action="release",
        repo=repo,
        task_id="ordinary-task",
        owner="owner",
        lease_id=lease["lease_id"],
        admission_id=admission["admission_id"],
    )
    assert cleanup["status"] == "PASS"


def test_stale_sidecar_from_expired_lease_cannot_block_new_lease_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _init_linked_repo(tmp_path)
    admission = acquire_task_admission(
        repo=repo,
        task_id="ordinary-task",
        owner="owner",
        task_contract=_admission_contract(repo, "finite", "ordinary write"),
    )
    first = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="ordinary-task",
        owner="owner",
        admission_id=admission["admission_id"],
        ttl_seconds=60,
        now=NOW,
    )["lease"]
    identity = inspect_worktree(repo)
    store = FileWriterLeaseStore(identity.common_dir)
    original_replace = FileWriterLeaseStore._replace_json

    def interrupt_replacement_binding(
        active_store: FileWriterLeaseStore,
        path: Path,
        prefix: str,
        value: dict[str, object],
    ) -> None:
        if path == active_store.binding_path:
            raise OSError("simulated interruption replacing stale binding")
        original_replace(active_store, path, prefix, value)

    reacquire_time = NOW + timedelta(seconds=61)
    with monkeypatch.context() as scoped:
        scoped.setattr(
            FileWriterLeaseStore,
            "_replace_json",
            interrupt_replacement_binding,
        )
        with pytest.raises(OSError, match="simulated interruption"):
            filesystem_writer_lease_action(
                action="acquire",
                repo=repo,
                task_id="ordinary-task",
                owner="owner",
                admission_id=admission["admission_id"],
                ttl_seconds=60,
                now=reacquire_time,
            )

    second = store.read()["leases"][identity.worktree]
    stale_binding = store.read_admission_bindings()["bindings"][
        identity.worktree
    ]
    assert second["lease_id"] != first["lease_id"]
    assert stale_binding["lease_id"] == first["lease_id"]
    for action in ("status", "renew"):
        result = filesystem_writer_lease_action(
            action=action,
            repo=repo,
            task_id="ordinary-task",
            owner="owner",
            lease_id=second["lease_id"],
            admission_id=admission["admission_id"],
            now=reacquire_time,
        )
        assert result["status"] == "FAIL"
        assert result["reasons"] == [
            "WRITER_LEASE_ADMISSION_BINDING_MISMATCH"
        ]

    cleanup = filesystem_writer_lease_action(
        action="release",
        repo=repo,
        task_id="ordinary-task",
        owner="owner",
        lease_id=second["lease_id"],
        admission_id=admission["admission_id"],
        now=reacquire_time,
    )
    assert cleanup["status"] == "PASS"
    assert store.read()["leases"] == {}
    assert store.read_admission_bindings()["bindings"] == {}


def test_writer_lease_rejects_primary_or_dirty_worktree(tmp_path: Path) -> None:
    store = InMemoryWriterLeaseStore()
    primary = _identity(tmp_path)
    primary = WorktreeIdentity(
        **{**primary.__dict__, "git_dir": primary.common_dir}
    )
    rejected = acquire_writer_lease(
        store, primary, task_id="task", owner="owner", now=NOW
    )
    assert "LINKED_WORKTREE_REQUIRED" in rejected["reasons"]

    dirty = _identity(tmp_path, dirty=True)
    rejected_dirty = acquire_writer_lease(
        store, dirty, task_id="task", owner="owner", now=NOW
    )
    assert "CLEAN_WORKTREE_REQUIRED" in rejected_dirty["reasons"]


def test_expired_lease_cannot_renew_but_can_be_fenced_by_a_new_task(tmp_path: Path) -> None:
    store = InMemoryWriterLeaseStore()
    identity = _identity(tmp_path)
    first = acquire_writer_lease(
        store, identity, task_id="old-task", owner="old-owner", ttl_seconds=60, now=NOW
    )
    old_id = first["lease"]["lease_id"]
    expired_renew = renew_writer_lease(
        store, identity, task_id="old-task", owner="old-owner", lease_id=old_id,
        now=NOW + timedelta(seconds=61),
    )
    assert "WRITER_LEASE_EXPIRED" in expired_renew["reasons"]

    replacement = acquire_writer_lease(
        store, identity, task_id="new-task", owner="new-owner",
        now=NOW + timedelta(seconds=61),
    )
    assert replacement["status"] == "PASS"
    assert replacement["lease"]["lease_id"] != old_id


def test_filesystem_store_rejects_symlink_state(tmp_path: Path) -> None:
    common = tmp_path / ".git"
    common.mkdir()
    target = tmp_path / "outside.json"
    target.write_text('{"schema_version":"writer_leases_v1","leases":{}}\n')
    store = FileWriterLeaseStore(common)
    store.state_path.symlink_to(target)
    try:
        store.read()
    except ValueError as error:
        assert "must not be a symlink" in str(error)
    else:
        raise AssertionError("symlink writer state was admitted")
