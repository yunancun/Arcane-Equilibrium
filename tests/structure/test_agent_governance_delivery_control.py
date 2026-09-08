"""Public regressions for durable local workflow delivery control."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from agent_governance_context import capture_repository_baseline  # noqa: E402
from agent_governance_review_control import (  # noqa: E402
    capture_review_generation,
    review_task_contract_digest,
)
from agent_governance_routing import route_task, task_contract_projection  # noqa: E402
from agent_governance_task_admission import (  # noqa: E402
    FileTaskAdmissionStore,
    acquire_task_admission,
    continue_admitted_task,
    release_task_admission,
    workflow_delivery_key,
)
from agent_governance_writer_lease import inspect_worktree  # noqa: E402


GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, env=GIT_ENV, check=True,
        capture_output=True, text=True,
    ).stdout.strip()


def _linked_worktrees(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.name", "Workflow Test")
    _git(repo, "config", "user.email", "workflow-test@example.invalid")
    (repo / "subject.py").write_text("value = 1\n", encoding="utf-8")
    _git(repo, "add", "subject.py")
    _git(repo, "commit", "-qm", "fixture")
    worktrees = []
    for name in ("one", "two"):
        worktree = tmp_path / name
        _git(repo, "worktree", "add", "-qb", name, str(worktree))
        worktrees.append(worktree)
    return worktrees[0], worktrees[1]


def _contract(
    repo: Path,
    *,
    scope: list[str] | None = None,
    surfaces: list[str] | None = None,
) -> dict:
    owned = scope or ["subject.py"]
    facts = {
        "task_shape": "implementation",
        "surfaces": surfaces or ["python", "agent_workflow"],
        "risk": "low",
        "uncertainty": "low",
        "side_effect_class": "repo_write",
        "runtime_claim": False,
        "end_to_end_claim": False,
        "task_prompt": "Repair the same workflow delivery",
        "objective": "One fixed delivery",
        "scope": owned,
        "dirty_scope": owned,
        "verification_scope": owned,
        "baseline": capture_repository_baseline(repo),
        "direct_interfaces": ["subject.py"],
        "previous_failure": "same unresolved blocker",
        "acceptance_criteria": ["fixed behavior"],
        "hard_stops": ["scope must not grow"],
        "continuation_mode": "finite",
        "work_item_id": "WF-DELIVERY-TEST",
        "lane_id": "workflow-local",
    }
    return task_contract_projection(route_task(facts)["task_facts"])


def _loop_contract(repo: Path) -> dict:
    facts = {
        **_contract(repo),
        "task_prompt": "/loop\nRepair the same workflow delivery",
        "continuation_mode": "operator_loop",
    }
    facts.pop("task_prompt_digest")
    facts.pop("operator_loop_request_digest")
    return task_contract_projection(route_task(facts)["task_facts"])


def _admission_cli(
    repo: Path,
    action: str,
    *,
    task_id: str,
    contract: dict | None = None,
    admission_id: str | None = None,
) -> tuple[int, dict]:
    argv = [
        sys.executable,
        str(HELPERS / "agent_governance.py"),
        "task-admission",
        "--repo", str(repo),
        "--task-id", task_id,
        "--owner", "workflow-test",
        "--admission-action", action,
    ]
    if contract is not None:
        argv.extend(["--task-contract", json.dumps(contract)])
    if admission_id is not None:
        argv.extend(["--admission-id", admission_id])
    completed = subprocess.run(
        argv, cwd=repo, env=GIT_ENV, check=False,
        capture_output=True, text=True,
    )
    return completed.returncode, json.loads(completed.stdout)


def _review_control(contract: dict, generation: dict) -> dict:
    finding = {
        "id": "same-blocker",
        "classification": "in_scope_blocker",
        "severity": "P1",
        "summary": "the fixed behavior is still missing",
        "paths": ["subject.py"],
        "evidence_refs": ["public-cli-regression"],
        "acceptance_criterion": "fixed behavior",
        "introduced_by_current_diff": False,
    }
    return {
        "schema_version": "review_control_v1",
        "task_contract_digest": review_task_contract_digest(contract),
        "non_goals": ["expand the workflow repair"],
        "final_generation": generation,
        "reviewers": [{
            "node_id": "independent_review",
            "rounds": [{
                "round": 1,
                "kind": "initial",
                "reviewed_generation": generation,
                "findings": [finding],
            }],
        }],
    }


def _review_cli(repo: Path, contract: dict, control: dict) -> tuple[int, dict]:
    completed = subprocess.run(
        [
            sys.executable,
            str(HELPERS / "agent_governance.py"),
            "review-control",
            json.dumps({"task_facts": contract, "review_control": control}),
            "--repo", str(repo),
        ],
        cwd=repo,
        env=GIT_ENV,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode, json.loads(completed.stdout)


def test_release_does_not_reset_same_delivery_across_processes_and_worktrees(
    tmp_path: Path,
) -> None:
    first, second = _linked_worktrees(tmp_path)
    _, admitted = _admission_cli(
        first, "acquire", task_id="delivery-task-one", contract=_contract(first)
    )
    assert admitted["status"] == "PASS"
    released_code, released = _admission_cli(
        first,
        "release",
        task_id="delivery-task-one",
        admission_id=admitted["admission_id"],
    )
    assert released_code == 0
    assert released["status"] == "PASS"

    restarted_code, restarted = _admission_cli(
        second, "acquire", task_id="delivery-task-two", contract=_contract(second)
    )

    assert restarted_code == 2
    assert restarted["status"] == "FAIL"
    assert restarted["reasons"] == ["DELIVERY_REPAIR_NOT_AUTHORIZED"]


def test_relocated_delivery_record_cannot_reset_same_key_budget(
    tmp_path: Path,
) -> None:
    first, second = _linked_worktrees(tmp_path)
    _, admitted = _admission_cli(
        first, "acquire", task_id="relocation-task-one", contract=_contract(first)
    )
    _, released = _admission_cli(
        first,
        "release",
        task_id="relocation-task-one",
        admission_id=admitted["admission_id"],
    )
    assert released["status"] == "PASS"
    store = FileTaskAdmissionStore(inspect_worktree(first).common_dir)
    journal = store.read_delivery_journal()
    original_key, record = journal["deliveries"].popitem()
    relocated_key = "f" * 64 if original_key != "f" * 64 else "e" * 64
    journal["deliveries"][relocated_key] = record
    store.delivery_path.write_text(
        json.dumps(journal, sort_keys=True) + "\n", encoding="utf-8"
    )

    retry_code, retry = _admission_cli(
        second,
        "acquire",
        task_id="relocation-task-two",
        contract=_contract(second),
    )

    assert retry_code == 2
    assert retry == {"status": "FAIL", "error": "DELIVERY_STATE_AMBIGUOUS"}


def test_review_replay_cannot_refill_one_cross_worktree_repair(
    tmp_path: Path,
) -> None:
    first, second = _linked_worktrees(tmp_path)
    first_contract = _contract(first)
    _, admitted = _admission_cli(
        first, "acquire", task_id="delivery-task-one", contract=first_contract
    )
    (first / "subject.py").write_text("value = 2\n", encoding="utf-8")
    _git(first, "add", "subject.py")
    _git(first, "commit", "-qm", "reviewed candidate")
    control = _review_control(first_contract, capture_review_generation(first))

    first_review_code, first_review = _review_cli(first, first_contract, control)
    replay_code, replay = _review_cli(first, first_contract, control)

    assert first_review_code == replay_code == 0
    assert first_review["action"] == replay["action"] == (
        "BATCH_REPAIR_THEN_EXACT_RECHECK"
    )
    reset = json.loads(json.dumps(control))
    reset["reviewers"][0]["node_id"] = "replacement-reviewer"
    reset_code, reset_result = _review_cli(first, first_contract, reset)
    assert reset_code == 2
    assert "reviewer" in reset_result["error"]

    _, released = _admission_cli(
        first,
        "release",
        task_id="delivery-task-one",
        admission_id=admitted["admission_id"],
    )
    assert released["status"] == "PASS"
    second_contract = _contract(second)
    repair_code, repair = _admission_cli(
        second,
        "acquire",
        task_id="delivery-task-two",
        contract=second_contract,
    )
    assert repair_code == 0
    assert repair["status"] == "PASS"
    (second / "subject.py").write_text("value = 3\n", encoding="utf-8")
    _git(second, "add", "subject.py")
    _git(second, "commit", "-qm", "bounded repair")
    repaired_generation = capture_review_generation(second)
    recheck = json.loads(json.dumps(control))
    recheck["task_contract_digest"] = review_task_contract_digest(second_contract)
    recheck["final_generation"] = repaired_generation
    recheck["reviewers"][0]["rounds"].append({
        "round": 2,
        "kind": "exact_recheck",
        "reviewed_generation": repaired_generation,
        "findings": [],
    })
    recheck_code, recheck_result = _review_cli(
        second, second_contract, recheck
    )
    recheck_replay_code, recheck_replay = _review_cli(
        second, second_contract, recheck
    )
    assert recheck_code == recheck_replay_code == 0
    assert recheck_result["action"] == recheck_replay["action"] == "CLOSE_REVIEW"
    _admission_cli(
        second,
        "release",
        task_id="delivery-task-two",
        admission_id=repair["admission_id"],
    )

    third_code, third = _admission_cli(
        first,
        "acquire",
        task_id="delivery-task-three",
        contract=_contract(first),
    )
    assert third_code == 2
    assert third["reasons"] == ["DELIVERY_REPAIR_NOT_AUTHORIZED"]


def test_delivery_scope_can_narrow_but_cannot_expand(tmp_path: Path) -> None:
    first, second = _linked_worktrees(tmp_path)
    first_contract = _contract(first)
    _, admitted = _admission_cli(
        first, "acquire", task_id="scope-task-one", contract=first_contract
    )
    _admission_cli(
        first,
        "release",
        task_id="scope-task-one",
        admission_id=admitted["admission_id"],
    )

    expanded_code, expanded = _admission_cli(
        second,
        "acquire",
        task_id="scope-task-two",
        contract=_contract(second, scope=["subject.py", "extra.py"]),
    )

    assert expanded_code == 2
    assert "DELIVERY_SCOPE_EXPANDED" in expanded["reasons"]
    assert "DELIVERY_DIRTY_SCOPE_EXPANDED" in expanded["reasons"]


def test_paired_agent_workflow_ids_opt_in_without_changing_legacy_callers(
    tmp_path: Path,
) -> None:
    first, second = _linked_worktrees(tmp_path)
    paired = _contract(first, surfaces=["python", "agent_workflow"])
    _, admitted = _admission_cli(
        first, "acquire", task_id="agent-workflow-one", contract=paired
    )
    _admission_cli(
        first,
        "release",
        task_id="agent-workflow-one",
        admission_id=admitted["admission_id"],
    )
    guarded_code, guarded = _admission_cli(
        second,
        "acquire",
        task_id="agent-workflow-two",
        contract=_contract(second, surfaces=["python", "agent_workflow"]),
    )
    assert guarded_code == 2
    assert guarded["reasons"] == ["DELIVERY_REPAIR_NOT_AUTHORIZED"]

    legacy = _contract(second, surfaces=["python", "agent_workflow"])
    legacy["work_item_id"] = None
    legacy["lane_id"] = None
    legacy_code, legacy_result = _admission_cli(
        second, "acquire", task_id="legacy-agent-workflow", contract=legacy
    )
    assert legacy_code == 0
    assert legacy_result["status"] == "PASS"
    store = FileTaskAdmissionStore(inspect_worktree(second).common_dir)
    store.delivery_path.write_text("{malformed\n", encoding="utf-8")
    legacy_release_code, legacy_release = _admission_cli(
        second,
        "release",
        task_id="legacy-agent-workflow",
        admission_id=legacy_result["admission_id"],
    )
    assert legacy_release_code == 0
    assert legacy_release["status"] == "PASS"


def test_future_current_workflow_selector_requires_paired_delivery_identity() -> None:
    with pytest.raises(ValueError, match="require paired work_item_id and lane_id"):
        workflow_delivery_key({
            "admission_profile": None,
            "surfaces": ["current_workflow_state"],
            "work_item_id": None,
            "lane_id": None,
        })


def test_pending_without_v1_resumes_only_the_exact_reserved_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, _ = _linked_worktrees(tmp_path)
    contract = _contract(first)
    store = FileTaskAdmissionStore(inspect_worktree(first).common_dir)
    original_replace = FileTaskAdmissionStore._replace_json

    def interrupt_before_v1(
        active_store: FileTaskAdmissionStore,
        path: Path,
        prefix: str,
        value: dict,
    ) -> None:
        if path == active_store.state_path:
            raise OSError("simulated crash before v1 authority")
        original_replace(active_store, path, prefix, value)

    with monkeypatch.context() as scoped:
        scoped.setattr(FileTaskAdmissionStore, "_replace_json", interrupt_before_v1)
        with pytest.raises(OSError, match="before v1 authority"):
            acquire_task_admission(
                repo=first,
                task_id="pending-task",
                owner="workflow-test",
                task_contract=contract,
            )
    pending = next(iter(store.read_delivery_journal()["deliveries"].values()))[
        "pending_admission"
    ]
    assert store.read()["admissions"] == {}

    mismatch = acquire_task_admission(
        repo=first,
        task_id="different-task",
        owner="workflow-test",
        task_contract=contract,
    )
    assert mismatch["status"] == "FAIL"
    assert mismatch["reasons"] == ["DELIVERY_STATE_AMBIGUOUS"]
    resumed = acquire_task_admission(
        repo=first,
        task_id="pending-task",
        owner="workflow-test",
        task_contract=contract,
    )
    assert resumed["status"] == "PASS"
    assert resumed["admission_id"] == pending["admission_id"]


def test_pending_with_matching_v1_reconciles_idempotently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, _ = _linked_worktrees(tmp_path)
    contract = _contract(first)
    store = FileTaskAdmissionStore(inspect_worktree(first).common_dir)
    original_replace = FileTaskAdmissionStore._replace_json
    delivery_writes = 0

    def interrupt_before_active(
        active_store: FileTaskAdmissionStore,
        path: Path,
        prefix: str,
        value: dict,
    ) -> None:
        nonlocal delivery_writes
        if path == active_store.delivery_path:
            delivery_writes += 1
            if delivery_writes == 2:
                raise OSError("simulated crash before ACTIVE finalization")
        original_replace(active_store, path, prefix, value)

    with monkeypatch.context() as scoped:
        scoped.setattr(FileTaskAdmissionStore, "_replace_json", interrupt_before_active)
        with pytest.raises(OSError, match="ACTIVE finalization"):
            acquire_task_admission(
                repo=first,
                task_id="matching-task",
                owner="workflow-test",
                task_contract=contract,
            )
    state_record = next(iter(store.read()["admissions"].values()))
    assert next(iter(store.read_delivery_journal()["deliveries"].values()))[
        "pending_admission"
    ]["admission_id"] == state_record["admission_id"]

    reconciled = acquire_task_admission(
        repo=first,
        task_id="matching-task",
        owner="workflow-test",
        task_contract=contract,
    )
    assert reconciled["status"] == "PASS"
    assert reconciled["admission_id"] == state_record["admission_id"]
    delivery = next(iter(store.read_delivery_journal()["deliveries"].values()))
    assert delivery["pending_admission"] is None
    assert len(delivery["admissions"]) == 1


def test_interrupted_repair_reserves_budget_before_v1_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, second = _linked_worktrees(tmp_path)
    first_contract = _contract(first)
    admitted = acquire_task_admission(
        repo=first,
        task_id="initial-task",
        owner="workflow-test",
        task_contract=first_contract,
    )
    initial_control = _review_control(
        first_contract, capture_review_generation(first)
    )
    review_code, review = _review_cli(first, first_contract, initial_control)
    assert review_code == 0
    assert review["action"] == "BATCH_REPAIR_THEN_EXACT_RECHECK"
    assert release_task_admission(
        repo=first,
        task_id="initial-task",
        owner="workflow-test",
        admission_id=admitted["admission_id"],
    )["status"] == "PASS"

    repair_contract = _contract(second)
    store = FileTaskAdmissionStore(inspect_worktree(second).common_dir)
    original_replace = FileTaskAdmissionStore._replace_json

    def interrupt_repair_v1(
        active_store: FileTaskAdmissionStore,
        path: Path,
        prefix: str,
        value: dict,
    ) -> None:
        if path == active_store.state_path:
            raise OSError("simulated repair crash before v1 authority")
        original_replace(active_store, path, prefix, value)

    with monkeypatch.context() as scoped:
        scoped.setattr(FileTaskAdmissionStore, "_replace_json", interrupt_repair_v1)
        with pytest.raises(OSError, match="repair crash"):
            acquire_task_admission(
                repo=second,
                task_id="repair-task",
                owner="workflow-test",
                task_contract=repair_contract,
            )
    delivery = next(iter(store.read_delivery_journal()["deliveries"].values()))
    assert delivery["repair_budget"] == {"authorized": False, "consumed": 1}

    resumed = acquire_task_admission(
        repo=second,
        task_id="repair-task",
        owner="workflow-test",
        task_contract=repair_contract,
    )
    assert resumed["status"] == "PASS"
    assert release_task_admission(
        repo=second,
        task_id="repair-task",
        owner="workflow-test",
        admission_id=resumed["admission_id"],
    )["status"] == "PASS"
    exhausted = acquire_task_admission(
        repo=first,
        task_id="third-task",
        owner="workflow-test",
        task_contract=_contract(first),
    )
    assert exhausted["status"] == "FAIL"
    assert exhausted["reasons"] == ["DELIVERY_REPAIR_NOT_AUTHORIZED"]


def test_same_declared_loop_blocker_stops_after_comment_only_delta(
    tmp_path: Path,
) -> None:
    first, _ = _linked_worktrees(tmp_path)
    contract = _loop_contract(first)
    admitted = acquire_task_admission(
        repo=first,
        task_id="loop-task",
        owner="workflow-test",
        task_contract=contract,
        operator_request_verifier=lambda request: True,
    )
    (first / "subject.py").write_text("value = 2\n", encoding="utf-8")
    continued = continue_admitted_task(
        repo=first,
        task_id="loop-task",
        owner="workflow-test",
        admission_id=admitted["admission_id"],
        work_status="IN_PROGRESS",
        blocker_code="SAME_BLOCKER",
    )
    assert continued["decision"]["decision"] == "CONTINUE_OPERATOR_LOOP"

    (first / "subject.py").write_text(
        "value = 2\n# comment-only churn\n", encoding="utf-8"
    )
    stopped = continue_admitted_task(
        repo=first,
        task_id="loop-task",
        owner="workflow-test",
        admission_id=admitted["admission_id"],
        work_status="IN_PROGRESS",
        blocker_code="SAME_BLOCKER",
    )
    assert stopped["decision"]["decision"] == "BLOCKED_NO_DELTA"
    assert stopped["decision"]["schedule_wakeup"] is False
