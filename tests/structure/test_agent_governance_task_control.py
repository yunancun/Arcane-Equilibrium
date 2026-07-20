from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from agent_governance_task_control import (  # noqa: E402
    FileWriterLeaseStore,
    InMemoryWriterLeaseStore,
    WorktreeIdentity,
    acquire_writer_lease,
    adjudicate_continuation,
    is_dispatchable,
    next_action_may_be_null,
    progress_snapshot,
    queue_lane,
    release_writer_lease,
    renew_writer_lease,
    validate_writer_lease,
)


NOW = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
SHA = "a" * 40
DIGEST_A = "sha256:" + "1" * 64
DIGEST_B = "sha256:" + "2" * 64
DIGEST_C = "sha256:" + "3" * 64


def _snapshot(
    round_number: int,
    *,
    status: str = "IN_PROGRESS",
    external: str = DIGEST_B,
) -> dict:
    return progress_snapshot(
        round_number=round_number,
        work_status=status,
        source_head=SHA,
        context_digest=DIGEST_A,
        external_state_digest=external,
        work_digest=DIGEST_C,
        blocker_code="WAITING_FOR_EVIDENCE",
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


def test_finite_is_the_default_terminal_boundary_without_wakeup() -> None:
    decision = adjudicate_continuation(
        continuation_mode="finite", current=_snapshot(0)
    )
    assert decision["decision"] == "STOP_FINITE_TASK"
    assert decision["schedule_wakeup"] is False
    assert decision["policy"]["automatic_wakeup_admitted"] is False


def test_operator_loop_continues_only_on_a_real_progress_delta() -> None:
    previous = _snapshot(1)
    unchanged = _snapshot(2)
    assert previous["progress_digest"] == unchanged["progress_digest"]
    stopped = adjudicate_continuation(
        continuation_mode="operator_loop", previous=previous, current=unchanged
    )
    assert stopped["decision"] == "BLOCKED_NO_DELTA"
    assert stopped["terminal_work_status"] == "BLOCKED_NO_DELTA"
    assert stopped["schedule_wakeup"] is False

    changed = _snapshot(2, external="sha256:" + "4" * 64)
    continued = adjudicate_continuation(
        continuation_mode="operator_loop", previous=previous, current=changed
    )
    assert continued["decision"] == "CONTINUE_OPERATOR_LOOP"
    assert continued["schedule_wakeup"] is True

    forged = dict(changed)
    forged["progress_digest"] = DIGEST_A
    try:
        adjudicate_continuation(
            continuation_mode="operator_loop", previous=previous, current=forged
        )
    except ValueError as error:
        assert "does not match canonical content" in str(error)
    else:
        raise AssertionError("forged progress digest was admitted")


def test_terminal_status_stops_even_in_operator_loop() -> None:
    decision = adjudicate_continuation(
        continuation_mode="operator_loop", current=_snapshot(3, status="BLOCKED")
    )
    assert decision["decision"] == "STOP_TERMINAL"
    assert decision["schedule_wakeup"] is False


def test_queue_lanes_do_not_reopen_waiting_or_closed_work() -> None:
    assert queue_lane("ACTIVE") == "active"
    assert queue_lane("WAITING") == "waiting"
    assert queue_lane("BLOCKED_NO_DELTA") == "closed"
    assert is_dispatchable("ACTIVE") is True
    assert is_dispatchable("IN_PROGRESS") is True
    assert is_dispatchable("WAITING") is False
    assert is_dispatchable("DONE") is False
    assert next_action_may_be_null("DONE") is True
    assert next_action_may_be_null("BLOCKED_NO_DELTA") is True
    assert next_action_may_be_null("BLOCKED") is False


def test_writer_lease_is_exclusive_idempotent_and_fenced(tmp_path: Path) -> None:
    store = InMemoryWriterLeaseStore()
    identity = _identity(tmp_path)
    acquired = acquire_writer_lease(
        store, identity, task_id="task-a", owner="owner-a", now=NOW
    )
    assert acquired["status"] == "PASS"
    lease_id = acquired["lease"]["lease_id"]

    idempotent = acquire_writer_lease(
        store, identity, task_id="task-a", owner="owner-a", now=NOW
    )
    assert idempotent["lease"]["lease_id"] == lease_id

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
