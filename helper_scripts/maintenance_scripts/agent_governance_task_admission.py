"""Persisted task admission and continuation state for agent governance.

The filesystem Adapter is the authority boundary for generic continuation.  A
caller may request a decision, but cannot replace the admitted task contract or
invent the previous progress snapshot at that boundary.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import secrets
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from agent_governance_capture import (
    NativeEvidenceMismatch,
    NativeEvidenceUnavailable,
    capture_native_head_tree,
    capture_native_protected_snapshot,
    capture_native_task_source_manifest,
    capture_repository,
    repository_generation_digest,
)
from agent_governance_task_control import (
    _adjudicate_continuation,
    compile_task_execution_policy,
    progress_snapshot,
    validate_progress_snapshot,
)
from agent_governance_writer_lease import inspect_worktree
from agent_governance_external_evidence import ExternalEvidenceVerifier
from agent_governance_lw2_readmission import (
    LW2_ADMISSION_PROFILE,
    capture_current_repository_identity,
    lw2_contract_selected,
    lw2_protected_path,
    validate_lw2_protected_inventory_scope,
    validate_lw2_contract_binding,
    validate_lw2_readmission_eligibility,
)
from agent_governance_routing import (
    TASK_CONTRACT_FIELDS,
    _normalize_task_facts,
    task_contract_projection,
)


TASK_ADMISSION_SCHEMA_VERSION = "task_execution_admissions_v1"
DELIVERY_JOURNAL_SCHEMA_VERSION = "workflow_delivery_journal_v1"
DELIVERY_RECORD_SCHEMA_VERSION = "workflow_delivery_record_v1"
LEGACY_TASK_ADMISSION_RECORD_FIELDS = {
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
LW2_TASK_ADMISSION_RECORD_FIELDS = LEGACY_TASK_ADMISSION_RECORD_FIELDS | {
    "accepted_generation",
}
ORDINARY_TASK_ADMISSION_RECORD_FIELDS = LEGACY_TASK_ADMISSION_RECORD_FIELDS | {
    "accepted_base",
}
ACCEPTED_GENERATION_FIELDS = {
    "schema_version", "source_head", "source_tree", "scope",
    "repository_generation_digest",
}
ACCEPTED_BASE_FIELDS = {"schema_version", "head", "tree"}
TASK_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
OWNER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}")
ADMISSION_ID_RE = re.compile(r"[0-9a-f]{32}")
LW2_TASK_ID = "S2E-LW2"
OperatorRequestVerifier = Callable[[dict[str, Any]], bool]


class FileTaskAdmissionStore:
    """Atomic task-admission state in Git's common directory."""

    def __init__(self, common_dir: Path) -> None:
        self.common_dir = common_dir.resolve()
        self.state_path = self.common_dir / "codex-task-admissions-v1.json"
        self.lock_path = self.common_dir / "codex-task-admissions-v1.lock"
        self.delivery_path = self.common_dir / "codex-workflow-deliveries-v1.json"

    def _replace_json(self, path: Path, prefix: str, value: dict[str, Any]) -> None:
        fd, temporary_name = tempfile.mkstemp(
            prefix=prefix, suffix=".tmp", dir=self.common_dir,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)

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
            self._replace_json(
                self.state_path, "codex-task-admissions-v1.", candidate
            )
            return candidate

    def read_delivery_journal(self) -> dict[str, Any]:
        if self.delivery_path.is_symlink():
            raise ValueError("workflow delivery journal must not be a symlink")
        try:
            journal = json.loads(self.delivery_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {
                "schema_version": DELIVERY_JOURNAL_SCHEMA_VERSION,
                "deliveries": {},
            }
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("DELIVERY_STATE_AMBIGUOUS") from error
        try:
            _validate_delivery_journal(journal)
        except ValueError as error:
            raise ValueError("DELIVERY_STATE_AMBIGUOUS") from error
        return journal

    def update_delivery_admission(
        self,
        mutation: Callable[
            [dict[str, Any], dict[str, Any]],
            tuple[dict[str, Any], dict[str, Any], dict[str, Any]],
        ],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Persist PENDING, v1 authority, then ACTIVE under the admission lock."""

        self.common_dir.mkdir(parents=True, exist_ok=True)
        if any(path.is_symlink() for path in (
            self.state_path, self.delivery_path, self.lock_path,
        )):
            raise ValueError("task admission files must not be symlinks")
        with self.lock_path.open("a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            state, pending, final = mutation(
                self.read(), self.read_delivery_journal()
            )
            _validate_state(state)
            _validate_delivery_journal(pending)
            _validate_delivery_journal(final)
            self._replace_json(
                self.delivery_path, "codex-workflow-deliveries-v1.", pending
            )
            self._replace_json(
                self.state_path, "codex-task-admissions-v1.", state
            )
            self._replace_json(
                self.delivery_path, "codex-workflow-deliveries-v1.", final
            )
            return state, final

    def update_state_and_delivery(
        self,
        mutation: Callable[
            [dict[str, Any], dict[str, Any]],
            tuple[dict[str, Any], dict[str, Any]],
        ],
        *,
        delivery_selector: Callable[[dict[str, Any]], bool],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Serialize a lifecycle transition with its retained delivery record."""

        self.common_dir.mkdir(parents=True, exist_ok=True)
        if any(path.is_symlink() for path in (
            self.state_path, self.delivery_path, self.lock_path,
        )):
            raise ValueError("task admission files must not be symlinks")
        with self.lock_path.open("a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            initial_state = self.read()
            delivery_required = delivery_selector(initial_state)
            initial_journal = (
                self.read_delivery_journal()
                if delivery_required
                else {
                    "schema_version": DELIVERY_JOURNAL_SCHEMA_VERSION,
                    "deliveries": {},
                }
            )
            state, journal = mutation(initial_state, initial_journal)
            _validate_state(state)
            _validate_delivery_journal(journal)
            self._replace_json(
                self.state_path, "codex-task-admissions-v1.", state
            )
            if delivery_required:
                self._replace_json(
                    self.delivery_path, "codex-workflow-deliveries-v1.", journal
                )
            return state, journal

    def update_delivery_journal(
        self, mutation: Callable[[dict[str, Any]], dict[str, Any]]
    ) -> dict[str, Any]:
        """Update delivery review state under the shared admission lock."""

        self.common_dir.mkdir(parents=True, exist_ok=True)
        if any(path.is_symlink() for path in (self.delivery_path, self.lock_path)):
            raise ValueError("task admission files must not be symlinks")
        with self.lock_path.open("a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            journal = mutation(self.read_delivery_journal())
            _validate_delivery_journal(journal)
            self._replace_json(
                self.delivery_path, "codex-workflow-deliveries-v1.", journal
            )
            return journal

    def serialized_read(
        self, action: Callable[[dict[str, Any]], dict[str, Any]]
    ) -> dict[str, Any]:
        """Run a read/decision while holding the admission serialization lock."""

        self.common_dir.mkdir(parents=True, exist_ok=True)
        if self.state_path.is_symlink() or self.lock_path.is_symlink():
            raise ValueError("task admission files must not be symlinks")
        with self.lock_path.open("a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            return action(self.read())


def _validate_record(record: Any, *, worktree: str) -> None:
    if not isinstance(record, dict) or frozenset(record) not in {
        frozenset(LEGACY_TASK_ADMISSION_RECORD_FIELDS),
        frozenset(LW2_TASK_ADMISSION_RECORD_FIELDS),
        frozenset(ORDINARY_TASK_ADMISSION_RECORD_FIELDS),
    }:
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
    selected_lw2 = lw2_contract_selected(
        record["task_contract"], task_id=record["task_id"]
    )
    generation = record.get("accepted_generation")
    accepted_base = record.get("accepted_base")
    if selected_lw2:
        validate_lw2_contract_binding(
            record["task_contract"], task_id=record["task_id"]
        )
        if not isinstance(generation, dict) or set(generation) != ACCEPTED_GENERATION_FIELDS:
            raise ValueError("LW2 task admission accepted_generation fields are not exact")
        if (
            generation["schema_version"]
            != "task_admission_repository_generation_v1"
            or not re.fullmatch(r"[0-9a-f]{40}", str(generation["source_head"]))
            or not re.fullmatch(r"[0-9a-f]{40}", str(generation["source_tree"]))
            or not re.fullmatch(
                r"sha256:[0-9a-f]{64}",
                str(generation["repository_generation_digest"]),
            )
        ):
            raise ValueError("LW2 task admission accepted_generation is invalid")
        validate_lw2_protected_inventory_scope(generation["scope"])
        if accepted_base is not None:
            raise ValueError("LW2 task admission accepted_base is forbidden")
    else:
        if generation is not None:
            raise ValueError("ordinary task admission accepted_generation is forbidden")
        if accepted_base is not None and (
            not isinstance(accepted_base, dict)
            or set(accepted_base) != ACCEPTED_BASE_FIELDS
            or accepted_base.get("schema_version")
            != "task_admission_accepted_base_v1"
            or not re.fullmatch(r"[0-9a-f]{40}", str(accepted_base.get("head")))
            or not re.fullmatch(r"[0-9a-f]{40}", str(accepted_base.get("tree")))
        ):
            raise ValueError("ordinary task admission accepted_base is invalid")


def capture_task_admission_generation(
    repo: Path,
    task_contract: dict[str, Any],
) -> dict[str, Any]:
    """Capture exact HEAD/tree plus task-owned repository generation."""

    generation, _ = capture_task_admission_generation_evidence(
        repo, task_contract
    )
    return generation


def capture_task_admission_generation_evidence(
    repo: Path,
    task_contract: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the generation and its final native protected snapshot."""

    dirty_scope = task_contract.get("dirty_scope")
    if not isinstance(dirty_scope, list) or not dirty_scope:
        raise ValueError("LW2 task admission generation requires dirty_scope")
    if any(not lw2_protected_path(path) for path in dirty_scope):
        raise ValueError("LW2 task admission dirty_scope is outside protected inventory")
    initial_snapshot = capture_native_protected_snapshot(
        repo, allowed_worktree_differences=dirty_scope
    )
    initial_protected = set(initial_snapshot["filesystem_scope"])
    # The accepted inventory includes task-owned paths that do not exist in the
    # baseline tree yet.  The native snapshot remains the authority for every
    # tracked baseline entry, while the broad protected selectors below ensure
    # that a later untracked/additional path under a protected prefix also
    # changes the generation instead of falling outside an enumerated snapshot.
    scope = sorted(
        set(initial_snapshot["scope"])
        | set(dirty_scope)
        | initial_protected
    )
    validate_lw2_protected_inventory_scope(scope)
    repository = capture_repository(scope, root=repo)
    source_head, source_tree = capture_current_repository_identity(repo)
    final_snapshot = capture_native_protected_snapshot(
        repo, allowed_worktree_differences=dirty_scope
    )
    final_protected = set(final_snapshot["filesystem_scope"])
    if (
        repository["source_head"] != source_head
        or final_protected != initial_protected
        or final_snapshot != initial_snapshot
    ):
        raise NativeEvidenceMismatch(
            "LW2 repository generation changed during capture"
        )
    return {
        "schema_version": "task_admission_repository_generation_v1",
        "source_head": source_head,
        "source_tree": source_tree,
        "scope": list(scope),
        "repository_generation_digest": repository_generation_digest(
            repository, native_protected_snapshot=final_snapshot
        ),
    }, final_snapshot


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


def _delivery_key_digest(work_item_id: str, lane_id: str) -> str:
    encoded = json.dumps(
        [work_item_id, lane_id], ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def workflow_delivery_key(task_contract: dict[str, Any]) -> str | None:
    """Return the explicit ordinary local-workflow key, if this contract has one."""

    if task_contract.get("admission_profile") is not None:
        return None
    surfaces = set(task_contract.get("surfaces", []))
    work_item_id = task_contract.get("work_item_id")
    lane_id = task_contract.get("lane_id")
    if "current_workflow_state" in surfaces and (
        work_item_id is None or lane_id is None
    ):
        raise ValueError(
            "current_workflow_state ordinary admissions require paired "
            "work_item_id and lane_id"
        )
    if "current_workflow_state" not in surfaces and not (
        "agent_workflow" in surfaces
        and work_item_id is not None
        and lane_id is not None
    ):
        return None
    return _delivery_key_digest(work_item_id, lane_id)


def _delivery_envelope(task_contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "objective": deepcopy(task_contract["objective"]),
        "scope": deepcopy(task_contract["scope"]),
        "acceptance_criteria": deepcopy(task_contract["acceptance_criteria"]),
        "hard_stops": deepcopy(task_contract["hard_stops"]),
        "dirty_scope": deepcopy(task_contract["dirty_scope"]),
        "verification_scope": deepcopy(task_contract["verification_scope"]),
    }


def _delivery_envelope_errors(
    frozen: dict[str, Any], task_contract: dict[str, Any]
) -> list[str]:
    current = _delivery_envelope(task_contract)
    errors: list[str] = []
    for field in ("objective", "acceptance_criteria", "hard_stops"):
        if current[field] != frozen[field]:
            errors.append(f"DELIVERY_{field.upper()}_CHANGED")
    frozen_scope = frozen["scope"]
    current_scope = current["scope"]
    if isinstance(frozen_scope, list) and isinstance(current_scope, list):
        if not set(current_scope).issubset(frozen_scope):
            errors.append("DELIVERY_SCOPE_EXPANDED")
    elif current_scope != frozen_scope:
        errors.append("DELIVERY_SCOPE_CHANGED")
    for field in ("dirty_scope", "verification_scope"):
        if not set(current[field]).issubset(frozen[field]):
            errors.append(f"DELIVERY_{field.upper()}_EXPANDED")
    return errors


def _delivery_request(
    *,
    admission_id: str,
    task_id: str,
    owner: str,
    worktree: str,
    task_contract_digest: str,
    accepted_base: dict[str, str],
) -> dict[str, Any]:
    return {
        "admission_id": admission_id,
        "task_id": task_id,
        "owner": owner,
        "worktree": worktree,
        "task_contract_digest": task_contract_digest,
        "accepted_base": deepcopy(accepted_base),
    }


def _new_delivery_record(task_contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": DELIVERY_RECORD_SCHEMA_VERSION,
        "delivery_key": {
            "work_item_id": task_contract["work_item_id"],
            "lane_id": task_contract["lane_id"],
        },
        "frozen_envelope": _delivery_envelope(task_contract),
        "admissions": [],
        "pending_admission": None,
        "repair_budget": {"authorized": False, "consumed": 0},
        "review": None,
        "terminal_history": [],
    }


def _validate_delivery_request(value: Any) -> None:
    fields = {
        "admission_id", "task_id", "owner", "worktree",
        "task_contract_digest", "accepted_base",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("workflow delivery admission fields are not exact")
    if not ADMISSION_ID_RE.fullmatch(str(value["admission_id"])):
        raise ValueError("workflow delivery admission id is invalid")
    if not TASK_ID_RE.fullmatch(str(value["task_id"])):
        raise ValueError("workflow delivery task id is invalid")
    if not OWNER_RE.fullmatch(str(value["owner"])):
        raise ValueError("workflow delivery owner is invalid")
    if not isinstance(value["worktree"], str) or not value["worktree"]:
        raise ValueError("workflow delivery worktree is invalid")
    if not re.fullmatch(
        r"sha256:[0-9a-f]{64}", str(value["task_contract_digest"])
    ):
        raise ValueError("workflow delivery contract digest is invalid")
    base = value["accepted_base"]
    if (
        not isinstance(base, dict)
        or set(base) != ACCEPTED_BASE_FIELDS
        or base.get("schema_version") != "task_admission_accepted_base_v1"
        or not re.fullmatch(r"[0-9a-f]{40}", str(base.get("head")))
        or not re.fullmatch(r"[0-9a-f]{40}", str(base.get("tree")))
    ):
        raise ValueError("workflow delivery accepted base is invalid")


def _validate_delivery_journal(journal: Any) -> None:
    if (
        not isinstance(journal, dict)
        or set(journal) != {"schema_version", "deliveries"}
        or journal.get("schema_version") != DELIVERY_JOURNAL_SCHEMA_VERSION
        or not isinstance(journal.get("deliveries"), dict)
    ):
        raise ValueError("workflow delivery journal fields are not exact")
    for key, record in journal["deliveries"].items():
        fields = {
            "schema_version", "delivery_key", "frozen_envelope", "admissions",
            "pending_admission", "repair_budget", "review", "terminal_history",
        }
        if (
            not re.fullmatch(r"[0-9a-f]{64}", str(key))
            or not isinstance(record, dict)
            or set(record) != fields
            or record.get("schema_version") != DELIVERY_RECORD_SCHEMA_VERSION
        ):
            raise ValueError("workflow delivery record fields are not exact")
        delivery_key = record["delivery_key"]
        if (
            not isinstance(delivery_key, dict)
            or set(delivery_key) != {"work_item_id", "lane_id"}
            or not all(
                isinstance(value, str) and value
                for value in delivery_key.values()
            )
        ):
            raise ValueError("workflow delivery key is invalid")
        if _delivery_key_digest(
            delivery_key["work_item_id"], delivery_key["lane_id"]
        ) != key:
            raise ValueError("workflow delivery map key does not match embedded key")
        envelope = record["frozen_envelope"]
        envelope_fields = {
            "objective", "scope", "acceptance_criteria", "hard_stops",
            "dirty_scope", "verification_scope",
        }
        if not isinstance(envelope, dict) or set(envelope) != envelope_fields:
            raise ValueError("workflow delivery envelope fields are not exact")
        admissions = record["admissions"]
        if not isinstance(admissions, list):
            raise ValueError("workflow delivery admissions must be a list")
        seen: set[str] = set()
        for admission in admissions:
            if (
                not isinstance(admission, dict)
                or set(admission) != {
                    "admission_id", "task_id", "owner", "worktree",
                    "task_contract_digest", "accepted_base", "state",
                }
            ):
                raise ValueError("workflow delivery history fields are not exact")
            state = admission["state"]
            _validate_delivery_request({
                field: value
                for field, value in admission.items()
                if field != "state"
            })
            if state not in {"ACTIVE", "TERMINAL", "RELEASED"}:
                raise ValueError("workflow delivery admission state is invalid")
            if admission["admission_id"] in seen:
                raise ValueError("workflow delivery admission id is duplicate")
            seen.add(admission["admission_id"])
        pending = record["pending_admission"]
        if pending is not None:
            _validate_delivery_request(pending)
        budget = record["repair_budget"]
        if (
            not isinstance(budget, dict)
            or set(budget) != {"authorized", "consumed"}
            or not isinstance(budget["authorized"], bool)
            or budget["consumed"] not in {0, 1}
        ):
            raise ValueError("workflow delivery repair budget is invalid")
        review = record["review"]
        if review is not None:
            review_fields = {
                "schema_version", "reviewer_set", "initial_prefix",
                "initial_control_digest", "initial_decision",
                "recheck_control_digest", "recheck_decision",
            }
            if (
                not isinstance(review, dict)
                or set(review) != review_fields
                or review.get("schema_version") != "workflow_delivery_review_v1"
                or not isinstance(review["reviewer_set"], list)
                or not isinstance(review["initial_prefix"], list)
                or not re.fullmatch(
                    r"sha256:[0-9a-f]{64}", str(review["initial_control_digest"])
                )
                or not isinstance(review["initial_decision"], dict)
                or (
                    review["recheck_control_digest"] is not None
                    and not re.fullmatch(
                        r"sha256:[0-9a-f]{64}",
                        str(review["recheck_control_digest"]),
                    )
                )
                or (
                    review["recheck_control_digest"] is None
                    and review["recheck_decision"] is not None
                )
                or (
                    review["recheck_control_digest"] is not None
                    and not isinstance(review["recheck_decision"], dict)
                )
            ):
                raise ValueError("workflow delivery review state is invalid")
        if not isinstance(record["terminal_history"], list):
            raise ValueError("workflow delivery terminal history must be a list")
        for terminal in record["terminal_history"]:
            if (
                not isinstance(terminal, dict)
                or set(terminal) != {
                    "admission_id", "terminal_work_status", "blocker_code",
                }
                or not ADMISSION_ID_RE.fullmatch(str(terminal["admission_id"]))
                or not isinstance(terminal["terminal_work_status"], str)
                or not terminal["terminal_work_status"]
                or (
                    terminal["blocker_code"] is not None
                    and not re.fullmatch(
                        r"[A-Z0-9][A-Z0-9_.:-]{0,127}",
                        str(terminal["blocker_code"]),
                    )
                )
            ):
                raise ValueError("workflow delivery terminal history is invalid")


def find_delivery_for_contract(
    journal: dict[str, Any], contract_digest: str
) -> tuple[str, dict[str, Any]] | None:
    """Find the one delivery whose retained admission used this contract."""

    matches = [
        (key, record)
        for key, record in journal["deliveries"].items()
        if any(
            admission["task_contract_digest"] == contract_digest
            for admission in record["admissions"]
        )
    ]
    if len(matches) > 1:
        raise ValueError("DELIVERY_STATE_AMBIGUOUS")
    return matches[0] if matches else None


def _state_record_has_delivery(
    state: dict[str, Any], worktree: str
) -> bool:
    record = state["admissions"].get(worktree)
    if record is None:
        return False
    try:
        return workflow_delivery_key(record["task_contract"]) is not None
    except ValueError:
        # A legacy record that predates paired delivery identity remains
        # available for its existing continuation/cleanup lifecycle.
        return False


def _existing_record_delivery_key(record: dict[str, Any]) -> str | None:
    try:
        return workflow_delivery_key(record["task_contract"])
    except ValueError:
        return None


def _projection(record: dict[str, Any]) -> dict[str, Any]:
    projection = {
        "task_id": record["task_id"],
        "owner": record["owner"],
        "worktree": record["worktree"],
        "task_contract_digest": record["task_contract_digest"],
        "continuation_mode": record["task_execution_control"]["continuation_mode"],
        "state": record["state"],
        "last_round": record["last_snapshot"]["round"],
        "last_progress_digest": record["last_snapshot"]["progress_digest"],
    }
    if "accepted_generation" in record:
        projection["accepted_generation"] = deepcopy(record["accepted_generation"])
    if "accepted_base" in record:
        projection["accepted_base"] = deepcopy(record["accepted_base"])
    return projection


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


def _normalized_task_contract(value: Any) -> dict[str, Any]:
    """Rebuild the exact routing projection before admission persists it."""

    if not isinstance(value, dict) or set(value) != set(TASK_CONTRACT_FIELDS):
        raise ValueError("task admission requires an exact normalized task contract")
    normalized = _normalize_task_facts({
        field: field_value
        for field, field_value in value.items()
        if field_value is not None
    })
    projected = task_contract_projection(normalized)
    if projected != value:
        raise ValueError("task admission contract is not the canonical routing projection")
    return projected


def acquire_task_admission(
    *,
    repo: Path,
    task_id: str,
    owner: str,
    task_contract: dict[str, Any],
    operator_request_verifier: OperatorRequestVerifier | None = None,
    external_evidence_verifier: ExternalEvidenceVerifier | None = None,
) -> dict[str, Any]:
    """Persist the first task contract for one worktree and return its token once."""

    if not TASK_ID_RE.fullmatch(task_id) or not OWNER_RE.fullmatch(owner):
        return _result(
            "acquire",
            status="FAIL",
            reasons=["TASK_ID_AND_OWNER_REQUIRED"],
        )
    identity = inspect_worktree(repo)
    task_contract = _normalized_task_contract(task_contract)
    delivery_key = workflow_delivery_key(task_contract)
    selected_lw2 = lw2_contract_selected(task_contract, task_id=task_id)
    clean_protected_snapshot = None
    if selected_lw2:
        validate_lw2_contract_binding(
            task_contract,
            task_id=task_id,
            repo=Path(identity.worktree),
        )
        current_head, current_tree = capture_current_repository_identity(
            Path(identity.worktree)
        )
        validate_lw2_readmission_eligibility(
            admission_profile=task_contract["admission_profile"],
            claim_inputs=task_contract["claim_inputs"],
            claim_payloads=task_contract["claim_payloads"],
            current_head=current_head,
            current_tree=current_tree,
            expected_writer_identity=owner,
            repo=Path(identity.worktree),
            reexecute_capture=True,
            external_evidence_verifier=external_evidence_verifier,
        )
        clean_protected_snapshot = capture_native_protected_snapshot(
            Path(identity.worktree)
        )
        accepted_generation = capture_task_admission_generation(
            Path(identity.worktree), task_contract
        )
        accepted_base = None
    else:
        accepted_generation = None
        if identity.dirty:
            raise ValueError("ordinary task admission requires a clean repository base")
        accepted_base = capture_native_head_tree(Path(identity.worktree))
    control = compile_task_execution_policy(task_contract)
    contract_digest = control["task_contract_digest"]
    if control["continuation_mode"] == "operator_loop":
        verification_request = {
            "schema_version": "operator_loop_admission_request_v1",
            "task_id": task_id,
            "owner": owner,
            "worktree": identity.worktree,
            "task_contract": deepcopy(task_contract),
            "task_contract_digest": contract_digest,
            "task_prompt_digest": control["task_prompt_digest"],
            "operator_loop_request_digest": control["operator_loop_request_digest"],
        }
        try:
            verified = (
                operator_request_verifier is not None
                and operator_request_verifier(verification_request) is True
            )
        except Exception:
            verified = False
        if not verified:
            return _result(
                "acquire",
                status="FAIL",
                reasons=["OPERATOR_REQUEST_ATTESTATION_REQUIRED"],
            )
    store = FileTaskAdmissionStore(identity.common_dir)
    result: dict[str, Any] = {}

    def mutation(
        state: dict[str, Any],
        journal: dict[str, Any] | None = None,
    ) -> Any:
        if selected_lw2:
            try:
                locked_clean_snapshot = capture_native_protected_snapshot(
                    Path(identity.worktree)
                )
                locked_generation = capture_task_admission_generation(
                    Path(identity.worktree), task_contract
                )
            except NativeEvidenceUnavailable as error:
                raise NativeEvidenceUnavailable(
                    "TASK_ADMISSION_GENERATION_UNAVAILABLE: LW2 repository "
                    "generation unavailable after replay before "
                    "admission store"
                ) from error
            except (NativeEvidenceMismatch, ValueError) as error:
                raise ValueError(
                    "LW2 repository generation changed after replay before "
                    "admission store"
                ) from error
            if locked_generation != accepted_generation:
                raise ValueError(
                    "LW2 repository generation changed after replay before admission store"
                )
            if locked_clean_snapshot != clean_protected_snapshot:
                raise ValueError(
                    "LW2 clean protected baseline changed before admission store"
                )
        else:
            locked_identity = inspect_worktree(Path(identity.worktree))
            if locked_identity.dirty:
                raise ValueError(
                    "ordinary task admission requires a clean repository base"
                )
            locked_base = capture_native_head_tree(Path(identity.worktree))
            if locked_base != accepted_base:
                raise ValueError(
                    "ordinary task admission base changed before admission store"
                )
        baseline = progress_snapshot(
            round_number=0,
            work_status="ACTIVE",
            repo=Path(identity.worktree),
            task_contract=task_contract,
            admitted_task_contract_digest=contract_digest,
        )
        if selected_lw2:
            final_clean_snapshot = capture_native_protected_snapshot(
                Path(identity.worktree)
            )
            final_head, final_tree = capture_current_repository_identity(
                Path(identity.worktree)
            )
            if (
                final_clean_snapshot != clean_protected_snapshot
                or (final_head, final_tree)
                != (
                    accepted_generation["source_head"],
                    accepted_generation["source_tree"],
                )
            ):
                raise ValueError(
                    "LW2 clean protected baseline changed during progress capture"
                )
        else:
            final_identity = inspect_worktree(Path(identity.worktree))
            final_base = capture_native_head_tree(Path(identity.worktree))
            if final_identity.dirty or final_base != accepted_base:
                raise ValueError(
                    "ordinary task admission base changed during progress capture"
                )
        accepted_head = (
            accepted_generation["source_head"]
            if selected_lw2 else accepted_base["head"]
        )
        accepted_tree = (
            accepted_generation["source_tree"]
            if selected_lw2 else accepted_base["tree"]
        )
        native_manifest = capture_native_task_source_manifest(
            Path(identity.worktree),
            accepted_head=accepted_head,
            accepted_tree=accepted_tree,
            scope=task_contract["dirty_scope"],
        )
        if (
            baseline["source_head"] != accepted_head
            or baseline["task_source_manifest"] != native_manifest
        ):
            raise ValueError(
                "task admission progress baseline does not match accepted tree"
            )
        if identity.worktree in state["admissions"] and delivery_key is None:
            result["collision"] = True
            return state
        admission_id = secrets.token_hex(16)
        pending_journal = None
        final_journal = None
        delivery_record = None
        repair_admission = False
        if delivery_key is not None:
            if journal is None:
                raise ValueError("workflow delivery journal is required")
            pending_journal = deepcopy(journal)
            delivery_record = pending_journal["deliveries"].get(delivery_key)
            if delivery_record is None:
                delivery_record = _new_delivery_record(task_contract)
                pending_journal["deliveries"][delivery_key] = delivery_record
            else:
                envelope_errors = _delivery_envelope_errors(
                    delivery_record["frozen_envelope"], task_contract
                )
                if envelope_errors:
                    result["delivery_reasons"] = envelope_errors
                    return state, journal, journal
                if (
                    delivery_record["admissions"]
                    and owner != delivery_record["admissions"][0]["owner"]
                ):
                    result["delivery_reasons"] = ["DELIVERY_OWNER_CHANGED"]
                    return state, journal, journal
            proposed_without_id = _delivery_request(
                admission_id="0" * 32,
                task_id=task_id,
                owner=owner,
                worktree=identity.worktree,
                task_contract_digest=contract_digest,
                accepted_base=accepted_base,
            )
            proposed_without_id.pop("admission_id")
            pending = delivery_record["pending_admission"]
            if pending is not None:
                pending_without_id = {
                    field: value
                    for field, value in pending.items()
                    if field != "admission_id"
                }
                if pending_without_id != proposed_without_id:
                    result["delivery_reasons"] = ["DELIVERY_STATE_AMBIGUOUS"]
                    return state, journal, journal
                admission_id = pending["admission_id"]
                pending_v1 = state["admissions"].get(pending["worktree"])
                if pending_v1 is not None:
                    if (
                        pending_v1["admission_id"] != admission_id
                        or pending_v1["task_contract_digest"] != contract_digest
                    ):
                        result["delivery_reasons"] = ["DELIVERY_STATE_AMBIGUOUS"]
                        return state, journal, journal
                    final_journal = deepcopy(pending_journal)
                    final_record = final_journal["deliveries"][delivery_key]
                    final_record["pending_admission"] = None
                    if not any(
                        item["admission_id"] == admission_id
                        for item in final_record["admissions"]
                    ):
                        final_record["admissions"].append({**pending, "state": "ACTIVE"})
                    result["record"] = pending_v1
                    result["reconciled"] = True
                    return state, pending_journal, final_journal
            else:
                active_history = [
                    item for item in delivery_record["admissions"]
                    if item["state"] in {"ACTIVE", "TERMINAL"}
                ]
                if active_history:
                    active = active_history[-1]
                    active_v1 = state["admissions"].get(active["worktree"])
                    reason = (
                        "DELIVERY_ADMISSION_HELD"
                        if active_v1 is not None
                        else "DELIVERY_STATE_AMBIGUOUS"
                    )
                    result["delivery_reasons"] = [reason]
                    return state, journal, journal
                if delivery_record["admissions"]:
                    budget = delivery_record["repair_budget"]
                    if not budget["authorized"] or budget["consumed"]:
                        result["delivery_reasons"] = [
                            "DELIVERY_REPAIR_NOT_AUTHORIZED"
                        ]
                        return state, journal, journal
                    repair_admission = True
            pending_request = _delivery_request(
                admission_id=admission_id,
                task_id=task_id,
                owner=owner,
                worktree=identity.worktree,
                task_contract_digest=contract_digest,
                accepted_base=accepted_base,
            )
            delivery_record["pending_admission"] = pending_request
            if repair_admission:
                delivery_record["repair_budget"] = {
                    "authorized": False,
                    "consumed": 1,
                }
        if identity.worktree in state["admissions"]:
            result["collision"] = True
            if delivery_key is None:
                return state
            return state, journal, journal
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
        if accepted_generation is not None:
            record["accepted_generation"] = accepted_generation
        if accepted_base is not None:
            record["accepted_base"] = accepted_base
        state["admissions"][identity.worktree] = record
        result["record"] = record
        if delivery_key is not None:
            if pending_journal is None or delivery_record is None:
                raise ValueError("workflow delivery reservation is missing")
            final_journal = deepcopy(pending_journal)
            final_record = final_journal["deliveries"][delivery_key]
            pending_request = final_record["pending_admission"]
            final_record["pending_admission"] = None
            final_record["admissions"].append({
                **pending_request, "state": "ACTIVE",
            })
            return state, pending_journal, final_journal
        return state

    if delivery_key is None:
        store.update(mutation)
    else:
        store.update_delivery_admission(mutation)
    if result.get("delivery_reasons"):
        return _result(
            "acquire",
            status="FAIL",
            reasons=result["delivery_reasons"],
        )
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

    def mutation(
        state: dict[str, Any], journal: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        record = state["admissions"].get(identity.worktree)
        reasons = _identity_reasons(
            record,
            task_id=task_id,
            owner=owner,
            admission_id=admission_id,
        )
        if reasons:
            result["reasons"] = reasons
            return state, journal
        if record["state"] != "ACTIVE":
            result["reasons"] = ["TASK_ADMISSION_TERMINAL"]
            return state, journal
        if lw2_contract_selected(
            record["task_contract"], task_id=record["task_id"]
        ):
            try:
                current_generation = capture_task_admission_generation(
                    Path(identity.worktree), record["task_contract"]
                )
            except NativeEvidenceUnavailable:
                result["reasons"] = ["TASK_ADMISSION_GENERATION_UNAVAILABLE"]
                return state, journal
            except (NativeEvidenceMismatch, ValueError):
                result["reasons"] = ["TASK_ADMISSION_GENERATION_MISMATCH"]
                return state, journal
            if current_generation != record.get("accepted_generation"):
                result["reasons"] = ["TASK_ADMISSION_GENERATION_MISMATCH"]
                return state, journal
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
        delivery_admission = None
        if not decision["schedule_wakeup"]:
            delivery_key = _existing_record_delivery_key(record)
            if delivery_key is not None:
                delivery = journal["deliveries"].get(delivery_key)
                if delivery is None:
                    result["reasons"] = ["DELIVERY_STATE_AMBIGUOUS"]
                    return state, journal
                matching = [
                    item for item in delivery["admissions"]
                    if item["admission_id"] == admission_id
                ]
                if len(matching) != 1 or matching[0]["state"] != "ACTIVE":
                    result["reasons"] = ["DELIVERY_STATE_AMBIGUOUS"]
                    return state, journal
                delivery_admission = matching[0]
        record["last_snapshot"] = current
        if not decision["schedule_wakeup"]:
            record["state"] = "TERMINAL"
            if delivery_admission is not None:
                delivery_admission["state"] = "TERMINAL"
                delivery["terminal_history"].append({
                    "admission_id": admission_id,
                    "terminal_work_status": decision["terminal_work_status"],
                    "blocker_code": current["blocker_code"],
                })
        result["record"] = record
        result["decision"] = decision
        return state, journal

    store.update_state_and_delivery(
        mutation,
        delivery_selector=lambda state: _state_record_has_delivery(
            state, identity.worktree
        ),
    )
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

    def mutation(
        state: dict[str, Any], journal: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        record = state["admissions"].get(identity.worktree)
        reasons = _identity_reasons(
            record,
            task_id=task_id,
            owner=owner,
            admission_id=admission_id,
        )
        if reasons:
            result["reasons"] = reasons
            return state, journal
        delivery_key = _existing_record_delivery_key(record)
        if delivery_key is not None:
            delivery = journal["deliveries"].get(delivery_key)
            if delivery is None:
                result["reasons"] = ["DELIVERY_STATE_AMBIGUOUS"]
                return state, journal
            matching = [
                item for item in delivery["admissions"]
                if item["admission_id"] == admission_id
            ]
            if len(matching) != 1 or matching[0]["state"] not in {
                "ACTIVE", "TERMINAL",
            }:
                result["reasons"] = ["DELIVERY_STATE_AMBIGUOUS"]
                return state, journal
            matching[0]["state"] = "RELEASED"
            delivery["terminal_history"].append({
                "admission_id": admission_id,
                "terminal_work_status": "RELEASED",
                "blocker_code": record["last_snapshot"]["blocker_code"],
            })
        result["record"] = record
        del state["admissions"][identity.worktree]
        return state, journal

    store.update_state_and_delivery(
        mutation,
        delivery_selector=lambda state: _state_record_has_delivery(
            state, identity.worktree
        ),
    )
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
