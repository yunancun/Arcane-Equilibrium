"""Persisted task admission and continuation state for agent governance.

The filesystem Adapter is the authority boundary for generic continuation.  A
caller may request a decision, but cannot replace the admitted task contract or
invent the previous progress snapshot at that boundary.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import secrets
import tempfile
from pathlib import Path
from typing import Any, Callable

from agent_governance_task_control import (
    _adjudicate_continuation,
    compile_task_execution_policy,
    progress_snapshot,
    validate_progress_snapshot,
)
from agent_governance_writer_lease import inspect_worktree


TASK_ADMISSION_SCHEMA_VERSION = "task_execution_admissions_v1"
TASK_ADMISSION_RECORD_FIELDS = {
    "admission_id",
    "task_id",
    "owner",
    "worktree",
    "task_contract",
    "task_contract_digest",
    "task_execution_control",
    "last_snapshot",
    "state",
}
TASK_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
OWNER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}")
ADMISSION_ID_RE = re.compile(r"[0-9a-f]{32}")


class FileTaskAdmissionStore:
    """Atomic task-admission state in Git's common directory."""

    def __init__(self, common_dir: Path) -> None:
        self.common_dir = common_dir.resolve()
        self.state_path = self.common_dir / "codex-task-admissions-v1.json"
        self.lock_path = self.common_dir / "codex-task-admissions-v1.lock"

    def read(self) -> dict[str, Any]:
        if self.state_path.is_symlink():
            raise ValueError("task admission state must not be a symlink")
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {
                "schema_version": TASK_ADMISSION_SCHEMA_VERSION,
                "admissions": {},
            }
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"task admission state is unreadable: {error}") from error
        _validate_state(state)
        return state

    def update(
        self, mutation: Callable[[dict[str, Any]], dict[str, Any]]
    ) -> dict[str, Any]:
        self.common_dir.mkdir(parents=True, exist_ok=True)
        if self.state_path.is_symlink() or self.lock_path.is_symlink():
            raise ValueError("task admission files must not be symlinks")
        with self.lock_path.open("a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            candidate = mutation(self.read())
            _validate_state(candidate)
            fd, temporary_name = tempfile.mkstemp(
                prefix="codex-task-admissions-v1.",
                suffix=".tmp",
                dir=self.common_dir,
            )
            temporary_path = Path(temporary_name)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(candidate, handle, ensure_ascii=False, sort_keys=True)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary_path, self.state_path)
            finally:
                temporary_path.unlink(missing_ok=True)
            return candidate


def _validate_record(record: Any, *, worktree: str) -> None:
    if not isinstance(record, dict) or set(record) != TASK_ADMISSION_RECORD_FIELDS:
        raise ValueError("task admission record fields are not exact")
    if record["worktree"] != worktree:
        raise ValueError("task admission key must match worktree")
    if not TASK_ID_RE.fullmatch(str(record["task_id"])):
        raise ValueError("task admission task_id is invalid")
    if not OWNER_RE.fullmatch(str(record["owner"])):
        raise ValueError("task admission owner is invalid")
    if not ADMISSION_ID_RE.fullmatch(str(record["admission_id"])):
        raise ValueError("task admission fencing token is invalid")
    if record["state"] not in {"ACTIVE", "TERMINAL"}:
        raise ValueError("task admission state is invalid")
    control = compile_task_execution_policy(record["task_contract"])
    if control != record["task_execution_control"]:
        raise ValueError("task admission control does not match contract")
    if control["task_contract_digest"] != record["task_contract_digest"]:
        raise ValueError("task admission contract digest is invalid")
    snapshot = validate_progress_snapshot(record["last_snapshot"])
    if snapshot["task_contract_digest"] != record["task_contract_digest"]:
        raise ValueError("task admission snapshot contract binding is invalid")


def _validate_state(state: Any) -> None:
    if not isinstance(state, dict) or set(state) != {"schema_version", "admissions"}:
        raise ValueError("task admission state fields are not exact")
    if state["schema_version"] != TASK_ADMISSION_SCHEMA_VERSION:
        raise ValueError("task admission state schema is invalid")
    if not isinstance(state["admissions"], dict):
        raise ValueError("task admission records must be an object")
    for worktree, record in state["admissions"].items():
        if not isinstance(worktree, str):
            raise ValueError("task admission worktree key is invalid")
        _validate_record(record, worktree=worktree)


def _projection(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": record["task_id"],
        "owner": record["owner"],
        "worktree": record["worktree"],
        "task_contract_digest": record["task_contract_digest"],
        "continuation_mode": record["task_execution_control"]["continuation_mode"],
        "state": record["state"],
        "last_round": record["last_snapshot"]["round"],
        "last_progress_digest": record["last_snapshot"]["progress_digest"],
    }


def _result(
    action: str,
    *,
    status: str,
    reasons: list[str],
    record: dict[str, Any] | None = None,
    admission_id: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "task_admission_result_v1",
        "action": action,
        "status": status,
        "reasons": reasons,
        "admission": _projection(record) if record is not None else None,
        "admission_id": admission_id,
    }


def _identity_reasons(
    record: dict[str, Any] | None,
    *,
    task_id: str,
    owner: str,
    admission_id: str,
) -> list[str]:
    if record is None:
        return ["TASK_ADMISSION_MISSING"]
    reasons: list[str] = []
    if record["task_id"] != task_id:
        reasons.append("TASK_ADMISSION_TASK_MISMATCH")
    if record["owner"] != owner:
        reasons.append("TASK_ADMISSION_OWNER_MISMATCH")
    if record["admission_id"] != admission_id:
        reasons.append("TASK_ADMISSION_ID_MISMATCH")
    return reasons


def acquire_task_admission(
    *,
    repo: Path,
    task_id: str,
    owner: str,
    task_contract: dict[str, Any],
) -> dict[str, Any]:
    """Persist the first task contract for one worktree and return its token once."""

    if not TASK_ID_RE.fullmatch(task_id) or not OWNER_RE.fullmatch(owner):
        return _result(
            "acquire",
            status="FAIL",
            reasons=["TASK_ID_AND_OWNER_REQUIRED"],
        )
    identity = inspect_worktree(repo)
    control = compile_task_execution_policy(task_contract)
    contract_digest = control["task_contract_digest"]
    baseline = progress_snapshot(
        round_number=0,
        work_status="ACTIVE",
        repo=Path(identity.worktree),
        task_contract=task_contract,
        admitted_task_contract_digest=contract_digest,
    )
    store = FileTaskAdmissionStore(identity.common_dir)
    result: dict[str, Any] = {}

    def mutation(state: dict[str, Any]) -> dict[str, Any]:
        if identity.worktree in state["admissions"]:
            result["collision"] = True
            return state
        admission_id = secrets.token_hex(16)
        record = {
            "admission_id": admission_id,
            "task_id": task_id,
            "owner": owner,
            "worktree": identity.worktree,
            "task_contract": task_contract,
            "task_contract_digest": contract_digest,
            "task_execution_control": control,
            "last_snapshot": baseline,
            "state": "ACTIVE",
        }
        state["admissions"][identity.worktree] = record
        result["record"] = record
        return state

    store.update(mutation)
    if result.get("collision"):
        return _result(
            "acquire",
            status="FAIL",
            reasons=["WORKTREE_TASK_ADMISSION_HELD"],
        )
    record = result["record"]
    return _result(
        "acquire",
        status="PASS",
        reasons=[],
        record=record,
        admission_id=record["admission_id"],
    )


def continue_admitted_task(
    *,
    repo: Path,
    task_id: str,
    owner: str,
    admission_id: str,
    work_status: str,
    blocker_code: str | None = None,
) -> dict[str, Any]:
    """Atomically compare current bytes with the persisted preceding snapshot."""

    identity = inspect_worktree(repo)
    store = FileTaskAdmissionStore(identity.common_dir)
    result: dict[str, Any] = {}

    def mutation(state: dict[str, Any]) -> dict[str, Any]:
        record = state["admissions"].get(identity.worktree)
        reasons = _identity_reasons(
            record,
            task_id=task_id,
            owner=owner,
            admission_id=admission_id,
        )
        if reasons:
            result["reasons"] = reasons
            return state
        if record["state"] != "ACTIVE":
            result["reasons"] = ["TASK_ADMISSION_TERMINAL"]
            return state
        previous = record["last_snapshot"]
        current = progress_snapshot(
            round_number=previous["round"] + 1,
            work_status=work_status,
            repo=Path(identity.worktree),
            task_contract=record["task_contract"],
            admitted_task_contract_digest=record["task_contract_digest"],
            blocker_code=blocker_code,
        )
        decision = _adjudicate_continuation(
            repo=Path(identity.worktree),
            task_contract=record["task_contract"],
            admitted_task_contract_digest=record["task_contract_digest"],
            task_execution_control=record["task_execution_control"],
            current=current,
            previous=previous,
        )
        record["last_snapshot"] = current
        if not decision["schedule_wakeup"]:
            record["state"] = "TERMINAL"
        result["record"] = record
        result["decision"] = decision
        return state

    store.update(mutation)
    if result.get("reasons"):
        return {
            **_result(
                "continuation",
                status="FAIL",
                reasons=result["reasons"],
            ),
            "decision": None,
        }
    return {
        **_result(
            "continuation",
            status="PASS",
            reasons=[],
            record=result["record"],
        ),
        "decision": result["decision"],
    }


def release_task_admission(
    *,
    repo: Path,
    task_id: str,
    owner: str,
    admission_id: str,
) -> dict[str, Any]:
    """Release only the exact task/owner/admission fencing tuple."""

    identity = inspect_worktree(repo)
    store = FileTaskAdmissionStore(identity.common_dir)
    result: dict[str, Any] = {}

    def mutation(state: dict[str, Any]) -> dict[str, Any]:
        record = state["admissions"].get(identity.worktree)
        reasons = _identity_reasons(
            record,
            task_id=task_id,
            owner=owner,
            admission_id=admission_id,
        )
        if reasons:
            result["reasons"] = reasons
            return state
        result["record"] = record
        del state["admissions"][identity.worktree]
        return state

    store.update(mutation)
    if result.get("reasons"):
        return _result(
            "release",
            status="FAIL",
            reasons=result["reasons"],
        )
    return _result(
        "release",
        status="PASS",
        reasons=[],
        record=result["record"],
    )
